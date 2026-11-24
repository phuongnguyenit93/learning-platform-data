# Monitoring Cache Hits, Misses, Size, and Cache Provider Support Conditions

## 1. What Are We Measuring in a Cached System?

A cache retains results so subsequent reads can reuse them. For example, querying product `A` the first time requires the application to compute or query the database; later calls can return the stored result. However, having a cache configured does not prove the cache is helping the application. You need to observe both lookups and retained entries:

- **Hit:** a lookup operation finds a stored value for the requested key.
- **Miss:** a lookup operation finds no usable value; the application may have to load the data or return an empty result.
- **Size:** the number of entries reported by the cache provider at measurement time.

This leads to three distinct questions: is data being reused, is the backing data source still being hit heavily, and how many entries is the cache holding? One number cannot answer all three.

In Spring Boot Actuator, the measurement pipeline is typically:

```text
Cache read/write operations
        ↓
Cache provider statistics
        ↓
Meter binder
        ↓
Micrometer MeterRegistry
        ↓
/actuator/metrics or a monitoring system such as Prometheus
```

`CacheManager` manages caches; libraries like Caffeine or Redis perform storage and supply statistics. Micrometer maps statistics into uniform meters. Actuator helps register, query, and export them. Exposing an endpoint does not generate data that the provider has not collected.

This lesson uses Spring Boot **3.3.x**, Java **17 or higher**; projects using Java 21 can run the example unchanged. Library-specific details are noted explicitly to avoid treating every cache as having identical measurement capabilities.

## 2. Metric Names, Types, and Interpretation Limits

Micrometer's cache binders use the baseline names below, yet register only the capabilities provided by the corresponding binder. In particular, do not infer from having `cache.gets` that `cache.size` must also exist. [Micrometer 1.13 CacheMeterBinder reference](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/binder/cache/CacheMeterBinder.java).

| Micrometer Name | Type | How to Read |
| --- | --- | --- |
| `cache.gets` with `result=hit` | FunctionCounter | Lookups that found data per cache statistics |
| `cache.gets` with `result=miss` | FunctionCounter, if supported | Lookups that did not find data |
| `cache.size` | Gauge, if supported | Entry count reported at sampling time |
| `cache.puts` | FunctionCounter | Additions/loads mapped by the binder from the library; verify exact semantics |
| `cache.evictions` | FunctionCounter, if supported | Evictions per the library's eviction statistics |

**FunctionCounter** reads a cumulative counter from the tracked object. **Gauge** reads a current value that can rise or fall. Thus, taking a growth rate of hits/misses makes sense; taking `rate(cache_size[5m])` and calling it "cache size" asks the wrong kind of question.

Tags distinguish same-named caches across different managers. With Boot 3.3 auto-configuration, watch `cache`, `name`, `cache.manager`, and specifically `result` on `cache.gets`. The `cache.manager` value is derived from the bean name and follows a rule stripping the `cacheManager` suffix in some names; do not guess the value on a live system. [Spring Boot registration and tagging code](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/metrics/cache/CacheMetricsRegistrarConfiguration.java).

One hit is not necessarily one successful HTTP request. One request may skip the cache, access multiple keys, or traverse multiple cache tiers. Nor is a miss automatically an error: new keys, expired entries, or explicitly evicted entries all cause normal misses.

### Size Is Not Memory Footprint

`cache.size = 1,000` means roughly one thousand entries as reported by the library, **not 1,000 bytes**. Two caches with the same entry count can consume vastly different memory due to key sizes, value sizes, and internal management structures.

With Caffeine, this metric relies on `estimatedSize()`. Expiring cleanup or maintenance tasks can cause the reported count not to reflect every change immediately. When investigating expiration, distinguish "no longer returned on read" from "removed from all internal structures." Do not treat a single gauge reading as absolute proof of how many objects remain on the heap.

### `cache.puts` and Evictions Depend on the Library

In Micrometer 1.13's Caffeine binder, `cache.puts` reads `CacheStats.loadCount()`. A manual `put` call is not counted by that statistic as a load through a loading function. This explains why a cache can already hold entries while `cache.puts` stays 0. `cache.size` likewise uses Caffeine's estimated count. [CaffeineCacheMetrics reference](https://raw.githubusercontent.com/micrometer-metrics/micrometer/v1.13.0/micrometer-core/src/main/java/io/micrometer/core/instrument/binder/cache/CaffeineCacheMetrics.java).

Similarly, explicit removal does not necessarily increment `cache.evictions`. Distinguish application-requested removals, expirations, and capacity-based evictions. Do not impose a rule that "whenever size drops, eviction must rise" across every provider.

## 3. Conditions for Spring Boot to Automatically Record Cache Metrics

Before looking at charts, check every link in the chain:

1. Actuator and an active `MeterRegistry` are present.
2. A `CacheManager` and actual caches used by the application exist.
3. A compatible meter binder exists for that cache type.
4. Provider statistics are enabled if required by the library.
5. The cache exists when Boot registers metrics, or is registered explicitly if created late.
6. Operations actually go through the monitored cache.

In Boot 3.3, the auto-instrumented list includes **Cache2k, Caffeine, Hazelcast, JSR-107-compliant JCache, and Redis**. Caches known at startup are registered automatically; caches created later require explicit registration. [Spring Boot 3.3 cache metrics docs](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.cache).

| Cache Type | Conditions or Limits to Check |
| --- | --- |
| Caffeine | Enable `recordStats` before building the cache; entry count is an estimate |
| Redis via Spring Data Redis | Enable application-side statistics; do not treat these counts as all activity on the Redis server |
| JCache, e.g. Ehcache 3 via JCache | Check provider statistics configuration and active JCache integration path |
| Hazelcast, Cache2k | Check integration type and statistics support in the actual library version |
| Simple `ConcurrentMapCacheManager` | Not in the auto-instrumented list above; having a working cache does not guarantee standard hit/miss meters appear |
| Custom cache or custom wrapper | May need a custom binder; must understand statistics and how to unwrap the underlying cache |

The list of providers Spring Boot can **configure for caching** is broader than the list **auto-instrumented for cache metrics**. Those two capabilities are not identical. If multiple libraries are on the classpath, verify the actual `CacheManager` type; `spring.cache.type` helps when Boot auto-configures the manager. [Boot 3.3 caching configuration docs](https://docs.spring.io/spring-boot/3.3/reference/io/caching.html).

With Caffeine, `recordStats()` is the statistics collection switch. If forgotten, meters may still be registered yet hits/misses fail to reflect traffic as expected; seeing meter names is not enough to confirm the measurement pipeline is working. [Caffeine Statistics guide](https://github.com/ben-manes/caffeine/wiki/Statistics).

## 4. Complete Experiment With Caffeine and Actuator

The experiment below calls a service four times through a Spring proxy to create a predictable lookup sequence. No database, Redis server, or business API is needed to generate traffic.

### 4.1. Creating a Standalone Project

This is an independent demo project, not a request to edit Gradle files in the repository you are studying. Use Gradle supporting Java 21, such as Gradle 8.5, with this structure:

```text
cache-metrics-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/cachemetrics/CacheMetricsDemoApplication.java
    └── resources/application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'cache-metrics-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'com.github.ben-manes.caffeine:caffeine'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Let Boot's BOM manage Micrometer and Caffeine versions, avoiding arbitrary version mixes. `spring-boot-starter-cache` brings in Spring's cache support; Caffeine remains the implementation library to declare. The Prometheus registry is only needed if you want Prometheus export format.

`src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health,metrics,prometheus
```

This configuration is for a local machine experiment. In a secured system, endpoint access still obeys the application's security configuration.

### 4.2. Java Program

Save the exact content below into `CacheMetricsDemoApplication.java` in the directory specified:

```java
package example.cachemetrics;

import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import com.github.benmanes.caffeine.cache.Caffeine;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class CacheMetricsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CacheMetricsDemoApplication.class, args);
    }

    @Bean
    CaffeineCacheManager cacheManager() {
        CaffeineCacheManager manager = new CaffeineCacheManager("products");
        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(100)
                .recordStats());
        return manager;
    }

    @Bean
    ProductService productService() {
        return new ProductService();
    }

    @Bean
    ApplicationRunner sample(ProductService service, CacheManager cacheManager,
            MeterRegistry registry) {
        return args -> {
            System.out.println("DEMO value=" + service.find("A"));
            System.out.println("DEMO value=" + service.find("A"));
            System.out.println("DEMO value=" + service.find("B"));
            System.out.println("DEMO value=" + service.find("B"));

            double hits = registry.get("cache.gets")
                    .tags("cache", "products", "result", "hit")
                    .functionCounter().count();
            double misses = registry.get("cache.gets")
                    .tags("cache", "products", "result", "miss")
                    .functionCounter().count();
            double size = registry.get("cache.size")
                    .tag("cache", "products").gauge().value();
            double puts = registry.get("cache.puts")
                    .tag("cache", "products").functionCounter().count();

            System.out.printf(Locale.ROOT,
                    "DEMO loads=%d hits=%.0f misses=%.0f size=%.0f puts=%.0f%n",
                    service.loads(), hits, misses, size, puts);

            var cache = Objects.requireNonNull(cacheManager.getCache("products"));
            cache.evict("A");
            double afterEvict = registry.get("cache.size")
                    .tag("cache", "products").gauge().value();
            double evictions = registry.get("cache.evictions")
                    .tag("cache", "products").functionCounter().count();
            System.out.printf(Locale.ROOT,
                    "DEMO after-explicit-evict size=%.0f evictions=%.0f%n",
                    afterEvict, evictions);
        };
    }

    public static class ProductService {
        private final AtomicInteger calls = new AtomicInteger();

        @Cacheable(cacheNames = "products", key = "#p0")
        public String find(String id) {
            calls.incrementAndGet();
            return "product-" + id;
        }

        public int loads() {
            return calls.get();
        }
    }
}
```

The manager bean is named `cacheManager` and pre-declares the `products` cache. `recordStats()` is configured before the manager bean enters service. There are no custom counters faking hits/misses; values are read from Boot-registered meters.

`ProductService` is a separate bean. The runner receives the bean via Spring and calls `find`, so calls go through the cache proxy. Do not instantiate the service with `new ProductService()` inside the runner or replace it with an internal `this.find()` call inside the service itself. `key = "#p0"` selects the first parameter without depending on whether compilation retains Java parameter names. [Cacheable semantics and key expressions](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/annotation/Cacheable.html).

### 4.3. Running and Verifying Stdout

If a Gradle wrapper is present, run:

```powershell
.\gradlew.bat bootRun
```

Or if a suitable Gradle installation is available:

```powershell
gradle bootRun
```

The first run needs access to dependency repositories to download plugins and libraries. Lines prefixed with `DEMO` must be:

```text
DEMO value=product-A
DEMO value=product-A
DEMO value=product-B
DEMO value=product-B
DEMO loads=2 hits=2 misses=2 size=2 puts=0
DEMO after-explicit-evict size=1 evictions=0
```

This is the experiment's stdout subset, not the entire Spring Boot startup log. The output assumes a fresh startup, sequential execution, no other task touching the cache, and no binder customizations.

| Operation | Lookup Result | Did `find` Body Run? | Entries After Operation |
| --- | --- | --- | --- |
| `find("A")` 1st time | Miss | Yes | 1 |
| `find("A")` 2nd time | Hit | No | 1 |
| `find("B")` 1st time | Miss | Yes | 2 |
| `find("B")` 2nd time | Hit | No | 2 |
| `cache.evict("A")` | Not a lookup | No | 1 |

Two misses lead to two method executions. With default `@Cacheable` in the example, Spring looks up the cache and then writes the return value; these are not loads counted by Caffeine's `CacheStats.loadCount()`. Hence `puts=0` remains consistent with `size=2` on the line before eviction.

`cache.evict("A")` is an explicit removal, so the experiment shows size dropping to 1 while `evictions` stays 0. Do not generalize this result to "Caffeine has no evictions": when entries are evicted by library policy, statistics differ.

You can run the experiment without opening HTTP using the command below; in that case use stdout to verify rather than the `curl` commands in the next section:

```powershell
.\gradlew.bat bootRun --args="--spring.main.web-application-type=none"
```

## 5. Reading Individual Series via Actuator

When the app runs in default web mode, use `curl.exe` in PowerShell to avoid colliding with PowerShell's `curl` alias:

```powershell
curl.exe "http://localhost:8080/actuator/metrics"
curl.exe "http://localhost:8080/actuator/metrics/cache.gets"
curl.exe "http://localhost:8080/actuator/metrics/cache.gets?tag=cache:products&tag=cache.manager:cacheManager&tag=result:hit"
curl.exe "http://localhost:8080/actuator/metrics/cache.gets?tag=cache:products&tag=cache.manager:cacheManager&tag=result:miss"
curl.exe "http://localhost:8080/actuator/metrics/cache.size?tag=cache:products&tag=cache.manager:cacheManager"
```

Inspect `availableTags` before filtering, especially if the app has multiple managers. In the example there is only one cache `products` and bean named `cacheManager`, so the filters above isolate the exact series.

After the runner completes:

- The hit series has `COUNT = 2.0`.
- The miss series has `COUNT = 2.0`.
- `cache.size` has `VALUE = 1.0`, because the end of the runner evicted `A`.

If you read `cache.gets` without filtering `result`, the aggregated value can combine both hits and misses. Do not call that sum the hit count. In an app with multiple caches, also filter by cache and manager; do not use a system-wide sum to draw conclusions about one cache.

Reading the metrics endpoint does not call `find` again, so refreshing the endpoint does not generate new hits/misses. Generating new traffic requires new operations going through the observed cache.

## 6. Computing Hit/Miss Ratios Over a Time Interval

Let `H` be hits and `M` be misses. Over an observation interval without restarts or counter resets:

```text
ΔH = H_end − H_start
ΔM = M_end − M_start
Lookups in interval = ΔH + ΔM
Hit ratio = ΔH / (ΔH + ΔM)
Miss ratio = ΔM / (ΔH + ΔM)
```

If the total is 0, there were no lookups to compute a ratio. Display "no traffic" instead of concluding the cache is 100% effective or 100% broken. In the experiment, before the explicit eviction there were 2 hits and 2 misses, giving a 50% hit ratio; the eviction operation did not alter the lookup count.

Hypothetical figures: start of interval has 900 hits and 100 misses, end of interval has 990 hits and 110 misses. Hit ratio over the interval is `90 / (90 + 10) = 90%`. This operates on deltas, not by dividing current hits by cache entry count.

### 6.1. Prometheus Names and Sample Queries

With standard Prometheus registry naming, `cache.gets` exports as `cache_gets_total`, `cache.size` as `cache_size`, and tag `cache.manager` as `cache_manager`. Inspect actual output before writing queries:

```powershell
curl.exe "http://localhost:8080/actuator/prometheus" | Select-String "cache_gets_total|cache_size|cache_puts_total|cache_evictions_total"
```

Example miss rate per cache and manager, summing traffic across instances in the same `job`:

```promql
sum by (job, cache, cache_manager) (
  rate(cache_gets_total{result="miss"}[5m])
)
```

Hit ratio using the same grouping:

```promql
sum by (job, cache, cache_manager) (
  rate(cache_gets_total{result="hit"}[5m])
)
/
sum by (job, cache, cache_manager) (
  rate(cache_gets_total{result=~"hit|miss"}[5m])
)
```

The denominator intentionally selects `hit|miss`: a provider might add another `result` value. Do not blindly include every auxiliary result in the count of resolved hits or misses.

Applying `rate` on each series before summing handles process restarts with fresh counters. `increase` suits measuring increments over an interval; do not blindly subtract two cumulative snapshots across a restart. [rate and increase semantics in Prometheus](https://prometheus.io/docs/prometheus/latest/querying/functions/).

Sufficient scrape samples are needed to compute a rate. The experiment generates four lookups and then stops touching the cache, so after some time the observation window will see no new activity; that does not reset cumulative counters to 0. When a ratio's denominator is 0, the query can return `NaN`; dashboards must represent the no-traffic state clearly.

### 6.2. Do Not Take a Simple Average of Ratios

Suppose instance one has 90 hits out of 100 lookups; instance two has 1 hit out of 1 lookup. The combined ratio is `91 / 101`, about **90.10%**, not the simple average `(90% + 100%) / 2 = 95%`.

Similarly, summing `size` across two local Caffeine caches yields the total entries held across both processes; that is not necessarily the number of unique keys because the same key can exist in both. For a distributed cache, summing gauges also requires checking whether they describe local partitions or the same cluster-wide dataset.

A high hit ratio alone does not prove good performance. Cross-check latency, actual calls to the data source, computation cost, and data freshness requirements. A cache returning stale data fast does not automatically make a sound design.

## 7. Caches Created After Startup

When the list of cache names is fixed, declare them upfront. The Java example used `new CaffeineCacheManager("products")`; that manager runs in static-names mode and does not dynamically create arbitrary cache names.

If Boot auto-configures Caffeine instead of a custom Java bean, an equivalent configuration is:

```properties
spring.cache.type=caffeine
spring.cache.cache-names=products
spring.cache.caffeine.spec=maximumSize=100,recordStats
```

This is an **alternative** to the `cacheManager()` bean in the example. Do not add these properties and expect them to override a `CacheManager` bean you created yourself.

If an application genuinely needs late-created caches, wire each cache to the registry where its lifecycle is controlled. The snippet below is an illustrative configuration method, not a standalone program and not meant to be added to the static-names example above:

```java
import java.util.Objects;

import io.micrometer.core.instrument.Tag;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.actuate.metrics.cache.CacheMetricsRegistrar;
import org.springframework.cache.Cache;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;

// Assumes cacheManager bean uses new CaffeineCacheManager(),
// has recordStats enabled, and allows creating caches by name at runtime.
@Bean
ApplicationRunner registerLateCache(CaffeineCacheManager cacheManager,
        CacheMetricsRegistrar registrar) {
    return args -> {
        Cache lateCache = Objects.requireNonNull(cacheManager.getCache("prices"));
        boolean bound = registrar.bindCacheToRegistry(
                lateCache, Tag.of("cache.manager", "cacheManager"));
        if (!bound) {
            throw new IllegalStateException("No compatible cache metrics binder");
        }
    };
}
```

`bindCacheToRegistry` returns `false` if no compatible binder is found; calling this method does not magically supply missing statistics for every cache type. [CacheMetricsRegistrar contract](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/metrics/cache/CacheMetricsRegistrar.java).

Register once per cache lifecycle, not on every request. Keep the same tagging convention as existing caches. If you destroy and recreate a cache object with the same name, handle replacing meters pointing at the old object; re-registering with the same name and tags does not guarantee switching the underlying data source to the new object.

Also avoid creating cache names per user or per request just for convenience of tracking. Growing tag combinations can expand time-series counts unexpectedly.

## 8. Redis: Application Statistics vs. Server Figures

When using Redis, establish **where measurements occur**. `RedisCache` statistics in the application are not global counters of the Redis server. Other applications, direct Redis client operations, or admin tools do not necessarily pass through the cache object monitored by Actuator.

Spring Data Redis does not enable `RedisCache` statistics by default; `RedisCacheManagerBuilder.enableStatistics()` enables local application-side hit/miss collection. [Redis Cache docs on statistics scope](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html).

If Boot auto-configures the Redis cache manager, a matching customizer in a configuration class is:

```java
import org.springframework.boot.autoconfigure.cache.RedisCacheManagerBuilderCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
RedisCacheManagerBuilderCustomizer enableRedisCacheStatistics() {
    return builder -> builder.enableStatistics();
}
```

This is an option for a project that already has Redis configuration and libraries, not code to add to the Caffeine experiment. If building `RedisCacheManager` manually, enable statistics directly on that manager's builder and verify the actual bean in use.

In Boot **3.3**'s Redis binder, `size()` and `evictionCount()` do not supply values, so `cache.size` and `cache.evictions` meters are not registered by this binder. Having Redis hits/misses without those two meters can be expected support behavior, not an endpoint bug. [Boot 3.3 RedisCacheMetrics source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/metrics/cache/RedisCacheMetrics.java).

Therefore, do not substitute 0 for missing metrics to claim Redis is empty. To know server-side memory, key counts, or evictions, use an appropriate Redis server observation source and define the scope accurately: entire server, logical database, or a cache key prefix. Do not treat total keys across all of Redis as the entry count of the `products` cache alone.

## 9. Diagnosing by Symptom

| Symptom | Grounded Verification Steps |
| --- | --- |
| `cache.gets` name missing | Verify Actuator/registry, cache type, compatible binder, and whether the cache existed at registration time |
| Meter name exists, yet hits/misses stay at 0 | Check statistics toggle and verify operations go through the right cache/instance |
| Method called repeatedly, yet body always runs | Check Spring proxy invocation, keys, cache conditions, and whether data is evicted between calls |
| Hits/misses present, yet `cache.size` missing | Check binder capabilities first; Boot 3.3 Redis specifically does not provide size |
| Size grows while `cache.puts` stays flat | Check how the library defines put/load; the Caffeine experiment illustrates this case |
| Unfiltered read shows surprisingly high counts | Filter by `result`, cache, manager, and instance; check whether multiple series are summed |
| Cannot access `/actuator/metrics` | Check exposed endpoints, management path, port, and authorization; do not immediately blame cache stats |
| Hit ratio drops after deployment | Correlate with fresh startup time and cache warmup period before resizing capacity |
| Hit ratio stays low despite repeated access | Check key stability, expiration time, capacity policy, and evictions; confirm with representative traffic |
| High size yet latency does not improve | Measure source access paths and actual latency; retained entries may rarely be reused or the cache is not on the expensive path |

When comparing two configurations, keep the problem and traffic comparable. Changing capacity, TTL, key design, and access patterns all at once makes it hard to tell which factor caused the difference. No single hit-ratio threshold fits every cache.

## 10. Practice and Self-Check

Apply each change on a fresh run of the demo project:

1. **Switch to four distinct keys:** call `A`, `B`, `C`, `D` once each. Before the final eviction, predict hit = 0, miss = 4, service body executions = 4, size = 4. Verify against output rather than guessing from HTTP calls.
2. **Call only `A` four times:** before the final eviction, predict hit = 3, miss = 1, service body executions = 1, size = 1. After evicting `A`, size should drop to 0 in this experiment.
3. **Remove `recordStats()` and rerun:** compare return values and service execution counts against hits/misses. The goal is seeing the cache still reuse values while the stats pipeline yields no useful counts. Restore the setting afterward.
4. **Compare snapshots vs. intervals:** use the hypothetical numbers in Section 6 to compute deltas yourself. Explain why a ratio cannot be derived from `cache.size`.
5. **Explain missing data:** if Redis has `cache.gets` without `cache.size`, explain binder capability limits before proposing configuration edits.

When reading a cache dashboard, you should be able to answer: **which cache, which manager, which process or cluster, which time interval, and which metrics does the provider actually support?** Only then do hit, miss, and size numbers carry enough context for decisions.
