# Limiting Data Size or Weight with Caffeine in Spring Cache

> **Topic:** Spring Framework – Cache · **Group:** Caffeine Integration.  
> **Problem:** You cannot let an in-JVM cache grow without bound. When entries are roughly uniform in size, limit the **entry count** with `maximumSize`. When entries consume vastly different amounts of resources, limit the **estimated total weight** with `maximumWeight` combined with `weigher`. This lesson explains the mechanism, proper configuration for Spring Cache, memory limits, and a self-contained Java 17+ example.

## 1. Why Must Caffeine Caches Be Bounded?

`@Cacheable` avoids re-executing an expensive method on a cache hit, but the cache retains objects in the JVM. If data or key counts grow continuously, the application can face several issues:

- **Excessive heap usage:** query records, JSON payloads, small images, collections, and object graphs hold references to large memory areas.
- **Increased GC pressure:** many objects survive multiple garbage collection cycles, increasing CPU usage and latency.
- **Uncontrolled cardinality:** every filter/tenant/page parameter creates a new cache key, causing entry counts to surge.
- **Non-uniform data sizes:** 1,000 records of a few hundred bytes are vastly different from 1,000 graphs with millions of nodes.
- **Cold misses and cache churn:** setting the limit too low causes keys to be evicted and reloaded from the database repeatedly, potentially overloading the source.
- **Per-instance differences:** when running multiple pods with local Caffeine caches, each pod has its **own budget**, not a cluster-wide shared budget.

Spring Cache abstraction **does not have a `@Cacheable(maximumSize=...)` annotation attribute**. Size or weight limits are configured on the **Caffeine provider / `CaffeineCacheManager`**, not in Spring's caching annotations.

Two basic options:

```java
// A. Limit entry count.
Caffeine.newBuilder().maximumSize(10_000);

// B. Limit estimated total weight.
Caffeine.newBuilder()
        .maximumWeight(100_000)
        .weigher((Object key, Object value) -> estimateWeight(value));
```

This is an illustrative snippet; `estimateWeight` is a business function that must be defined. Do **not** declare both `maximumSize` and `maximumWeight` on the same builder. Each option is a separate capacity policy.

## 2. `maximumSize`: Limiting by Entry Count

### 2.1. How to Understand It

`maximumSize(long maximum)` asks Caffeine to keep the number of entries within roughly the configured limit. When the cache needs space for a new value or runs maintenance, Caffeine can evict entries that have not been accessed recently or are used infrequently.

Example:

```java
com.github.benmanes.caffeine.cache.Cache<String, String> catalog =
        Caffeine.newBuilder()
                .maximumSize(500)
                .build();
```

The snippet above requires `import com.github.benmanes.caffeine.cache.Caffeine` inside a valid Java class/method. This is the **native Caffeine API**, not yet using Spring annotations.

Conceptually, the cache aims to keep around 500 keys; an entry holding a 20-byte string and an entry holding a 20 MB object graph **both count as one entry**. Thus `maximumSize` is very easy to configure, yet it does not directly represent heap usage.

### 2.2. What It Does Not Guarantee

- **Not a byte limit.** `maximumSize(500)` does not mean 500 KB or 500 MB.
- **Does not guarantee the oldest key is removed.** Caffeine uses an admission/eviction policy that favors a combination of frequency and recency; it is not simple FIFO.
- **Not an instantaneous hard cap at every line of code.** Eviction/maintenance work may be batched; `estimatedSize()` is an estimate and may temporarily not reflect all pending cleanup. In tests, call `cleanUp()` before observing rather than checking immediately after `put`.
- **Does not control memory outside entries.** The heap also holds threads, buffers, frameworks, objects retained elsewhere, in-flight query results during loads, and the cache's own overhead.
- **Not a TTL.** Entries may be evicted due to capacity pressure even before expiring; conversely, with few keys and rare changes, they may stay very long without an expiration policy.

### 2.3. When Is `maximumSize` Suitable?

- Records of relatively uniform size: e.g., small profiles, simple aggregate metrics, short metadata.
- Primary goal is preventing unbounded cardinality without needing a per-entry cost model.
- Preference for simple configuration, easy hit-rate observation, and straightforward tuning under changing load.
- No reliable way to measure value weight yet: **an entry-count limit is still better than an inaccurate weigher**.

Example including time-based expiration:

```java
Caffeine.newBuilder()
        .maximumSize(5_000)
        .expireAfterWrite(java.time.Duration.ofMinutes(10))
        .recordStats();
```

`maximumSize` guards capacity; `expireAfterWrite` bounds entry age; `recordStats` enables metrics. These are **three independent roles** and can be combined.

## 3. `maximumWeight` and `weigher`: Limiting by Estimated Weight

### 3.1. How It Works

When values vary widely in size, you can supply a **`Weigher<K,V>`** to determine the cost of each entry, and set **`maximumWeight(long)`** as the total budget.

Native Caffeine example with byte array payloads:

```java
com.github.benmanes.caffeine.cache.Cache<String, byte[]> payloads =
        Caffeine.newBuilder()
                .maximumWeight(4L * 1024 * 1024)
                .weigher((String key, byte[] bytes) -> bytes.length)
                .build();
```

This snippet requires importing `Caffeine` and placing it in an appropriate class/method. The convention above counts **the number of bytes in the payload array**, capping total payload at roughly 4 MiB. However, this is **not total actual heap** because it excludes keys, headers, map nodes, Java object overhead, alignment, metadata, and other references.

If objects are graphs or contain many strings, define `weigher` based on domain logic, such as node count, record count, serialized byte count, or another consistent resource unit.

### 3.2. Data Types and Rules for `Weigher`

- The function receives **key and value**, returning a **non-negative** `int`.
- Weight **may be 0**, though many zero-weight entries can distort the budget because they consume no weight quota.
- Never return negative values: Caffeine rejects negative weights.
- `maximumWeight` is a `long`, whereas each `weigh` return is an `int`; for very large data or byte units, guard against `int` overflow in calculations.
- The function should be **fast, deterministic, side-effect-free, and free of IO**. Caffeine computes weight when an entry is created or updated; a slow `weigher` slows down the cache write path.
- If values can be `null` via Spring Cache, check `allowNullValues` and the possibility of Caffeine wrapper sentinels. Do not blindly cast every value to the business type without controlling the configuration.

### 3.3. Weight Is Calculated on Entry Creation or Update

An easily overlooked point: **weight is computed when an entry is inserted or updated and remains fixed until the next update**. Caffeine does not periodically re-measure objects already sitting in the cache.

Example:

```java
java.util.List<String> items = new java.util.ArrayList<>();
items.add("A");
cache.put("products", items);   // weigher sees size = 1
items.add("B");                 // object mutated without another put
```

If `weigher` evaluates `value.size()`, the cache still retains the weight computed at `put` time even though the object's real size has grown. This is why **immutable** DTOs or taking snapshots before caching are preferred. When a value must be updated, replace the entry with the new value so Caffeine recalculates its weight.

**Also distinguish cost from victim selection policy:** Caffeine uses weight to enforce the total budget, but **the relative weight ratio of individual entries does not directly dictate eviction priority**. Do not assume the heaviest entry is always evicted first.

### 3.4. Entries Whose Weight Exceeds the Budget

A value for which the weigher returns a weight greater than `maximumWeight` cannot be stably retained in that cache. When `@Cacheable` calls the loader, the method can still return the value to the caller, yet the oversized value may **not be retained**; subsequent calls with the same key will miss and invoke the loader again.

This is usually a design signal: if most hot values exceed the quota, raise the budget or split caches by value type. Do not repeatedly hit the backend to compute an expensive object that cannot stay in the cache.

### 3.5. "Weight" Does Not Default to Bytes or MB

Some weighting strategies:

| Value type | Suggested weight | Measurement limitation |
|---|---|---|
| `byte[]` | `bytes.length` | Excludes headers, keys, and overhead |
| `String` | `string.length()` | Counts UTF-16 code units, **not bytes or heap size** |
| `List<Product>` | `list.size()` | Record count only; does not reflect varying item sizes |
| Graph | Vertex/edge count | Good for algorithmic cost, not actual heap |
| Serialized JSON | Serialization output byte count | Incurs serialization cost and usually misses object graph overhead |
| Large DTO | Normalized weight by group or buckets | Approximate; must be calibrated by measurement |
| Data sharing many references | Logical payload size | May double-count shared memory |

**Unit names must be explicit.** `maximumWeight(100_000)` with a weigher counting **records** must not be described as 100 KB. If a team uses KiB units, both capacity and weight must be in KiB.

## 4. `maximumSize` and `maximumWeight` Cannot Be Used on the Same Cache

| Property | `maximumSize` | `maximumWeight` + `weigher` |
|---|---|---|
| Quota unit | Number of entries | Sum of application-defined weights |
| When values are uniform | Easy to apply | Likely unnecessary effort |
| When values vary widely | Does not tightly bound total payload | Better fit if weight is reasonable |
| Requires custom code | No | Yes: `Weigher` |
| Expressible via simple spec string | Yes | `maximumWeight` needs an actual `weigher`; spec strings cannot define custom Java logic |
| Quota computation cost | Low | Depends on `weigher` cost |
| Risk from mutable values | Still risky if values change | **Especially severe** because weight is not recalculated automatically |
| Absolute heap limit | No | Also no |
| Eviction order | Caffeine policy | Caffeine policy; weight is not "evict first" priority |
| Combined with TTL | Yes | Yes |

**Invalid on a single builder:**

```java
Caffeine.newBuilder()
        .maximumSize(1000)
        .maximumWeight(10_000)
        .weigher((Object key, Object value) -> 1);
```

This configuration is **solely to illustrate an error**; do not put it into a runnable project. Caffeine enforces choosing **one** primary capacity limit: count or weight. There is no default property guaranteeing "at most 1,000 entries **and** at most 10 MB" on the same instance by calling both builder methods.

If two independent constraints are needed simultaneously, add an application-level quota layer, split into multiple caches by data type, or design a combined admission policy, measuring and testing concurrency carefully. Do not rely on an API the builder does not support.

### 4.1. What Happens When Eviction Is Triggered?

Caffeine does not simply evict the oldest or the largest entry. Its eviction policy considers access recency and frequency to protect frequently used values; Caffeine documentation describes W-TinyLFU-like behavior.

For example, if a cache has a 3-entry quota and every minute receives 100 accesses for key A, 50 for B, and just one for keys C, D, E, it is reasonable for A/B to be favored for retention, yet **no exact eviction victim is guaranteed for every sequence of operations**. Policy behavior can be influenced by sampling, maintenance, history, and concurrency.

Therefore, functional tests should verify **the budget after maintenance**, hit rate, and loader count, rather than writing brittle assertions like "after adding D, key C must definitely be evicted" under an adaptive policy.

## 5. Native Caffeine Configuration Before Spring Integration

### 5.1. Using Entry Count

```java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import java.time.Duration;

Cache<String, String> cache = Caffeine.newBuilder()
        .maximumSize(10_000)
        .expireAfterWrite(Duration.ofMinutes(15))
        .recordStats()
        .build();
```

This is a declaration snippet inside a Java scope where local variables are allowed, not a standalone source file. With a 10,000-entry limit, the budget is by **mapping count**, not byte measurement.

### 5.2. Using Weight Calculated in Bytes

```java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;

Cache<String, byte[]> bytesCache = Caffeine.newBuilder()
        .maximumWeight(64L * 1024 * 1024)
        .weigher((String key, byte[] value) -> value.length)
        .recordStats()
        .build();
```

If one value contains a 50 MB payload and the cache has a 64 MB budget, little quota remains; eviction may occur depending on other entries. A value > 64 MB will typically not be retained. This is a logical budget of **payload bytes**, not an exact RSS or heap cap.

### 5.3. Scaling Weigher to KiB to Avoid `int` Overflow

In a system where payloads can be huge, an `int` weight in bytes risks overflow when combining calculations. You can choose KiB units:

```java
static int kibWeight(byte[] bytes) {
    long kib = (bytes.length + 1023L) / 1024L;
    return (int) Math.max(1L, Math.min(kib, Integer.MAX_VALUE));
}
```

This is a syntactically standalone Java method when placed in a class. KiB units round up; tiny payloads still occupy at least one unit. For example, 1 byte → 1 KiB, 1,025 bytes → 2 KiB. When using this function, the quota must also be expressed in **KiB**: `maximumWeight(64L * 1024)` means roughly 64 MiB of scaled payload, not 64 KiB or 64 bytes.

### 5.4. Avoid Heavy Weighers

Avoid:

```java
.weigher((key, value) -> {
    // Anti-pattern: re-serializing the object and calling an external service
    // every time an entry is added or updated.
    return remoteSizingService.estimateBytes(value);
})
```

The function above is an **anti-pattern illustration** since `remoteSizingService` is an imaginary dependency, not standalone runnable code. A weigher performing network IO or heavy serialization slows down the cache population path. If real serialized size is needed, it is better to capture metadata when constructing the value and then weigh it with a fast field read.

## 6. Integrating into Spring Framework via `CaffeineCacheManager`

### 6.1. Using One Builder as a Shared Policy

When Spring Cache uses Caffeine, Spring Framework provides `org.springframework.cache.caffeine.CaffeineCacheManager` in the **`spring-context-support`** module.

```java
@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {

    @Bean
    public CacheManager cacheManager() {
        CaffeineCacheManager manager =
                new CaffeineCacheManager("products", "categories");

        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(5_000)
                .expireAfterWrite(Duration.ofMinutes(10))
                .recordStats());

        return manager;
    }
}
```

The snippet above needs imports for `CacheManager`, `CaffeineCacheManager`, `Caffeine`, `Duration`, `@Configuration`, `@EnableCaching`, and `@Bean`; see section 8 for a standalone runnable example.

An important point: the builder passed to `setCaffeine` is the **shared configuration for caches created by the manager**. Each region `products` and `categories` has its own `maximumSize(5000)` budget, rather than sharing a combined 5,000-entry quota.

`@Cacheable` on the service stays the same:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product load(String productId) {
    return repository.find(productId);
}
```

This service snippet requires a real repository; the method only selects the cache region. **Do not put `maximumSize` in the annotation** because size is determined by the manager/provider.

### 6.2. Different Policies per Region Using `registerCustomCache`

If `products` holds only a few thousand small records while `largeDocuments` holds huge byte arrays, a single builder for all caches may not make sense.

`CaffeineCacheManager.registerCustomCache(name, nativeCache)` lets you register an individually configured native Caffeine cache with the manager:

```java
CaffeineCacheManager manager = new CaffeineCacheManager("products");
manager.setCaffeine(Caffeine.newBuilder().maximumSize(5_000));

com.github.benmanes.caffeine.cache.Cache<Object, Object> documents =
        Caffeine.newBuilder()
                .maximumWeight(64L * 1024 * 1024)
                .weigher((Object key, Object value) ->
                        ((byte[]) value).length)
                .build();

manager.setAllowNullValues(false);
manager.registerCustomCache("largeDocuments", documents);
```

This is a Java snippet within a scope that already has imports; it is only safe if values in `largeDocuments` are truly non-null `byte[]`. Calling `setAllowNullValues(false)` avoids null-sentinel wrappers on the manager. If a method returns a different type, the cast in `weigher` can throw `ClassCastException`.

Result:

- `products`: quota by **entry count**.
- `largeDocuments`: quota by **total byte[] length**.
- Both caches have independent lifecycles and eviction.
- Quotas do not automatically apply to other managers or other pods.

### 6.3. One Manager for Multiple Cache Names: Total Budget Does Not Pool

Suppose a manager creates:

```java
new CaffeineCacheManager("products", "categories", "users")
```

and uses `maximumSize(5000)`. This does not mean the whole JVM holds at most 5,000 entries; **each Cache** has its own policy. In entry count, the total can approach 15,000 if all three regions are full, not counting other caches and overhead.

When budgeting heap, calculate:

```text
Approximate total cache memory
    ≈ Σ (entries in region i × average cost per entry i)
      + cache overhead, keys, JVM, object graphs, buffers ...
```

Even with `maximumWeight`, totals across different cache regions and multiple Spring contexts must be summed separately during capacity planning.

## 7. Spring Boot: Quick Configuration and Limitations of `spring.cache.caffeine.spec`

In a Spring Boot application with `@EnableCaching` enabled and `spring-boot-starter-cache` plus the Caffeine library, Boot can auto-configure `CaffeineCacheManager` when no overriding manager/resolver bean satisfies auto-configuration conditions.

### 7.1. Entry-Count Limits via Properties

**`application.properties`:**

```properties
spring.cache.type=caffeine
spring.cache.cache-names=products,categories
spring.cache.caffeine.spec=maximumSize=5000,expireAfterWrite=10m,recordStats
```

Here each region in `cache-names` uses the specified policy; `recordStats` enables native statistics. This is a concise way to configure **maximumSize** along with TTL.

**Important:** `spring.cache.caffeine.spec` cannot instantiate a custom Java `Weigher` object from a string. If value-dependent weighting is required, configure a **Caffeine builder bean or CaffeineCacheManager bean in Java** with `weigher`, and check Boot's precedence rules.

According to Boot documentation, when Caffeine auto-configuration is active, configuration is evaluated in order: `spring.cache.caffeine.spec`, `CaffeineSpec` bean, `Caffeine` bean. Thus a `spec` property can take precedence over a builder bean you declared. Do not let `maximumSize` in properties accidentally override your intent to apply `maximumWeight` from a builder.

### 7.2. Using a Builder Bean in Boot

Example using a builder only when no higher-precedence spec configuration exists:

```java
@Configuration(proxyBeanMethods = false)
class CaffeinePolicyConfig {

    @Bean
    Caffeine<Object, Object> caffeine() {
        return Caffeine.newBuilder()
                .maximumWeight(20_000)
                .weigher((Object key, Object value) ->
                        ((CachePayload) value).unitWeight())
                .recordStats();
    }
}
```

This is an illustrative snippet in a project with a real `CachePayload` class, not a standalone runnable source file. If the manager needs to store multiple value types, a hard cast to `CachePayload` will not work; split caches/managers by type or write a type-safe weighting rule.

If the application **registers its own `CacheManager` bean**, Spring Boot may back off from creating an automatic manager, and `spring.cache.*` properties will not automatically apply to the bean you constructed manually. Read the auto-configuration conditions and verify the bean type in the context rather than assuming.

### 7.3. Be Careful with `maximumWeight` in CaffeineSpec

The setting `maximumWeight=100000` by itself **does not describe how to compute weight for values**. Caffeine requires a valid `Weigher`; there is no simple spec syntax to express custom Java logic like `v -> v.getPayloadBytes()`.

Do not try to use:

```properties
# Not a complete configuration for custom weighted eviction:
spring.cache.caffeine.spec=maximumWeight=100000
```

This snippet illustrates an omission and is **not a recommended runnable configuration**. Declare a builder with `weigher`, choose the backend explicitly, and test that the manager actually uses the weighted policy.

## 8. Standalone Runnable Java 17+ Demo: Size Cache and Weighted Cache in One Spring Application

This example pins **Java 17+**, **Spring Framework 6.2.12**, **Caffeine 3.2.2**, and Maven. It demonstrates:

1. `maximumSize(2)` bounds the `boundedItems` region by entry count while `@Cacheable` hits on repeat calls.
2. `maximumWeight(5)` with a weigher computing `String.length()` retains A with weight 2 and B with weight 3.
3. A value with weight 6 exceeding the budget of 5 **is not retained**; the method still returns the data, yet calling it again forces a reload.
4. Using `registerCustomCache` to apply different policies to two regions within the same manager.
5. Observing `estimatedSize()` and `policy().eviction().weightedSize()` without relying on which exact key Caffeine evicts under capacity pressure.

### 8.1. Directory Structure

```text
spring-caffeine-capacity/
├── pom.xml
└── src/main/java/dev/example/capacity/CaffeineCapacityDemo.java
```

### 8.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example</groupId>
    <artifactId>spring-caffeine-capacity</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context-support</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>caffeine</artifactId>
            <version>3.2.2</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>dev.example.capacity.CaffeineCapacityDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context-support` pulls in the Spring Context components needed for annotation caching, while also containing the Caffeine integration. This project uses no Boot, database, or Redis.

### 8.3. Complete Java Source

**`src/main/java/dev/example/capacity/CaffeineCapacityDemo.java`**

```java
package dev.example.capacity;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCache;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CaffeineCapacityDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(CacheConfig.class)) {

            SampleService service = context.getBean(SampleService.class);
            CacheManager manager = context.getBean(CacheManager.class);

            Cache boundedSpring =
                    Objects.requireNonNull(manager.getCache("boundedItems"));
            Cache weightedSpring =
                    Objects.requireNonNull(manager.getCache("weightedItems"));

            com.github.benmanes.caffeine.cache.Cache<Object, Object> bounded =
                    ((CaffeineCache) boundedSpring).getNativeCache();
            com.github.benmanes.caffeine.cache.Cache<Object, Object> weighted =
                    ((CaffeineCache) weightedSpring).getNativeCache();

            // Each @Cacheable lookup uses the first String argument as its key.
            System.out.println("boundedA1=" + service.loadBounded("A"));
            System.out.println("boundedA2=" + service.loadBounded("A"));
            System.out.println("boundedLoadsBeforePressure=" +
                    service.boundedLoadCount());

            // Three keys exist, but the quota retains at most two entries.
            System.out.println("boundedB=" + service.loadBounded("B"));
            System.out.println("boundedC=" + service.loadBounded("C"));
            bounded.cleanUp();
            System.out.println("boundedEntriesAfterCleanup=" +
                    bounded.estimatedSize());

            // In weightedItems: A = 2 chars, B = 3 chars.
            System.out.println("weightedA=" + service.loadWeighted("A"));
            System.out.println("weightedB=" + service.loadWeighted("B"));
            weighted.cleanUp();
            long knownWeight = weighted.policy().eviction()
                    .orElseThrow().weightedSize().orElseThrow();
            System.out.println("weightedKnownWeight=" + knownWeight);

            // H has weight = 6, greater than maximumWeight(5).
            System.out.println("heavy1=" + service.loadWeighted("H"));
            System.out.println("heavy2=" + service.loadWeighted("H"));
            weighted.cleanUp();
            System.out.println("heavyCached=" +
                    (weighted.getIfPresent("H") != null));
            System.out.println("heavyLoads=" + service.heavyLoadCount());

            System.out.println("weightedMaximum=" +
                    weighted.policy().eviction().orElseThrow().getMaximum());
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class CacheConfig {

        @Bean
        public CacheManager cacheManager() {
            CaffeineCacheManager manager =
                    new CaffeineCacheManager("boundedItems");

            manager.setAllowNullValues(false);
            manager.setCaffeine(Caffeine.newBuilder()
                    .maximumSize(2)
                    .recordStats());

            com.github.benmanes.caffeine.cache.Cache<Object, Object>
                    weighted = Caffeine.newBuilder()
                    .maximumWeight(5)
                    .weigher((Object key, Object value) ->
                            ((String) value).length())
                    .recordStats()
                    .build();

            manager.registerCustomCache("weightedItems", weighted);
            return manager;
        }

        @Bean
        public SampleService sampleService() {
            return new SampleService();
        }
    }

    public static class SampleService {
        private final AtomicInteger boundedLoads = new AtomicInteger();
        private final AtomicInteger heavyLoads = new AtomicInteger();

        @Cacheable(cacheNames = "boundedItems", key = "#p0")
        public String loadBounded(String key) {
            return "bounded-" + key + "#" + boundedLoads.incrementAndGet();
        }

        @Cacheable(cacheNames = "weightedItems", key = "#p0")
        public String loadWeighted(String key) {
            return switch (key) {
                case "A" -> "AA";
                case "B" -> "BBB";
                case "H" -> {
                    heavyLoads.incrementAndGet();
                    yield "XXXXXX";
                }
                default -> "Z";
            };
        }

        public int boundedLoadCount() {
            return boundedLoads.get();
        }

        public int heavyLoadCount() {
            return heavyLoads.get();
        }
    }
}
```

In the `spring-caffeine-capacity` directory, run:

```bash
mvn -q compile exec:java
```

**Stdout from `System.out.println`** with a fresh context and caches (excluding extra Maven logs):

```text
boundedA1=bounded-A#1
boundedA2=bounded-A#1
boundedLoadsBeforePressure=1
boundedB=bounded-B#2
boundedC=bounded-C#3
boundedEntriesAfterCleanup=2
weightedA=AA
weightedB=BBB
weightedKnownWeight=5
heavy1=XXXXXX
heavy2=XXXXXX
heavyCached=false
heavyLoads=2
weightedMaximum=5
```

### 8.4. What Does This Prove?

**`boundedItems` branch:**

- The second call to `A` hits, so `boundedLoadsBeforePressure=1`.
- `B` and `C` bring the total keys inserted into the cache to three, exceeding the quota of 2.
- After `cleanUp()`, the cache holds **two mappings**. The test does not predict which of A/B/C remains because eviction order depends on policy.

**`weightedItems` branch:**

- `A` has value `"AA"`, weight 2; `B` has `"BBB"`, weight 3. Total within quota 5, hence `weightedKnownWeight=5`.
- `H` produces `"XXXXXX"` with weight 6, exceeding quota 5, so this entry is not retained. The caller still receives the value, yet the next call runs the method again; `heavyLoads=2` and `heavyCached=false`.
- `weightedMaximum=5` confirms the native eviction policy enforces a weight quota of 5, not a size of 5.
- Both cache regions have independent policies despite being managed by the same `CaffeineCacheManager`.

**Note:** Only use `cleanUp()` to trigger maintenance in tests or intentional operational tasks; do not call `cleanUp()` after every production request. `estimatedSize()` remains an approximation, and business logic must never depend on eviction victim ordering.

### 8.5. Why Is There No `new SampleService()` in `main`?

`@Cacheable` is processed by Spring via proxies when `@EnableCaching` is active. `context.getBean(SampleService.class)` returns the Spring-managed object so method invocations pass through the interceptor. If you write `new SampleService().loadBounded("A")` outside the context or call `this.loadBounded(...)` from the same bean in proxy mode, caching can be bypassed.

### 8.6. Why Does `setAllowNullValues(false)` Appear?

The example uses `weigher((Object key, Object value) -> ((String) value).length())`. If the cache allowed Spring to wrap null into a sentinel, casting to `String` would fail. Enabling `setAllowNullValues(false)` and ensuring cacheable methods return non-null Strings keeps the `weigher` data type consistent. Real systems should evaluate their null policy separately, or write a weigher that safely handles every value type.

## 9. Observing Capacity, Eviction, and Hit Rate

Good tuning requires measurement rather than just picking a nice number in properties.

### 9.1. Native Caffeine Stats

Enable `recordStats()` on the native cache and inspect:

```java
com.github.benmanes.caffeine.cache.Cache<Object, Object> nativeCache =
        ((CaffeineCache) springCache).getNativeCache();

nativeCache.cleanUp(); // Use only in tests or intentional measurement.
System.out.println(nativeCache.estimatedSize());
System.out.println(nativeCache.stats().hitRate());
System.out.println(nativeCache.stats().evictionCount());
System.out.println(nativeCache.stats().evictionWeight());
```

This snippet assumes a `springCache` variable of Spring's `Cache` type; the methods return native Caffeine metrics. `hitRate()` is meaningful only after many lookups with `recordStats`; with few samples, the metric is noisy.

**`evictionCount` is not the number of `@CacheEvict` calls**, and `evictionWeight` is not current usage. Eviction metrics describe policy-driven entry removals and cost; distinguish them from explicit invalidation/removal and TTL expiration.

### 9.2. Reading the Actual Budget from Policy

`Caffeine` exposes the optional eviction policy for inspection:

```java
var policy = nativeCache.policy().eviction().orElseThrow();

long configuredMaximum = policy.getMaximum();
java.util.OptionalLong currentWeightedSize = policy.weightedSize();
```

- `getMaximum()` is the policy's current quota, in **entry count** if size-based or in **weight units** if weighted.
- `weightedSize()` is meaningful only for weighted policies; for `maximumSize` caches, weighted-size information may be absent.
- `estimatedSize()` is the mapping count, not weight and not byte count.
- For caches with multiple regions, retrieve each region's native cache separately by `cacheName`.

Always report the **unit** alongside every chart: `maximumWeight=50_000 records` is completely different from `maximumWeight=50_000 KiB`.

### 9.3. Application Metrics to Monitor

| Metric | Why is it useful? |
|---|---|
| Cache hit rate / miss rate | Measures cache effectiveness and churn |
| Eviction count by cause/policy | Detects too-small budgets or growing key cardinality |
| Estimated entry count | Tracks how many keys are actually retained |
| Current weighted size if applicable | Compares against the defined weight budget |
| Load time and loader calls | Measures miss impact on databases/APIs |
| GC pauses / heap used / old-gen | Verifies whether cache bounds stabilize memory |
| P95/P99 latency of cacheable methods | Reveals consequences of eviction and stampedes |
| Key cardinality by tenant/query group | Detects unbounded or overlooked key dimensions |
| Instance/pod count and heap used per pod | Local caches multiply memory cost with cluster scale |

When using Spring Boot Actuator + Micrometer with proper configuration, cache metrics can be collected, though **not all weightedSize metrics are guaranteed out of the box**. Native policy introspection or custom metrics may be needed.

## 10. Choosing a Budget and Performance Trade-offs

### 10.1. From Heap Budget to `maximumSize`

An initial planning approach:

1. Determine the JVM heap limit, e.g., `-Xmx`, and the memory needed for the rest of the application.
2. Measure the average **retained** cost of one entry using a profiler, heap dump, or reasonably accurate benchmark.
3. Set a cache budget fitting within safe heap headroom, accounting for keys, values, and cache metadata overhead.
4. Estimate entry capacity: `targetEntries ≈ budgetBytes / meanRetainedBytesPerEntry`.
5. Use `maximumSize` as a starting point, then load test with realistic data and realistic key distributions.

Illustrative example, not an absolute sizing formula:

```text
Planned heap budget for one region: 128 MiB
Average retained cost per entry: 16 KiB
Estimated entry count: 128 × 1024 / 16 = 8192
Initial test starting point: maximumSize around 8000
```

Retained memory ratios can deviate significantly when object graphs share references, with string deduplication, class metadata, direct buffers, or unusually heavy outlier values. Re-measuring under real load is mandatory.

### 10.2. From Payload Distribution to `maximumWeight`

If 90% of entries are 1 KiB while 10% are 1 MiB, a `maximumSize(1000)` limit can make heap usage highly unpredictable. Setting `maximumWeight` and a weigher based on logical payload size is usually more helpful.

Example:

```text
Weigher(value) = payload KiB (rounded up)
maximumWeight = 65536
Budget unit = 65536 KiB ≈ 64 MiB logical payload
```

A 1 MiB record costs about 1024 units; a 1 KiB record costs 1 unit. This is a better cost model than counting every entry as 1, though it still **does not directly measure heap**.

### 10.3. When the Budget Is Too Small

A cache with a 10-entry quota receiving sequential accesses across 100 keys will miss almost every time. The result can be worse than no cache because management overhead is paid while the database still takes full load.

Break down hit rate by traffic pattern: misses on cold keys may be acceptable, whereas misses on hot keys due to churn indicate a need to raise the quota, split regions, or optimize key granularity.

### 10.4. When the Budget Is Too Large

Increasing the quota generally improves hit rate up to a point, yet can introduce:

- Heap usage approaching `-Xmx` and longer GC pauses.
- Longer warmup or restart times.
- Many stale objects retained longer if TTL is inappropriate.
- Large duplicated footprints when scaling from 3 to 30 pods.
- Harder detection of memory leaks elsewhere in the application.

Do not chase maximum hit rate while ignoring P99 latency, memory pressure, and downstream QPS.

## 11. Notes on Thread Safety, Mutation, and Combined Factors

### 11.1. Mutable Values Do Not Suit Static Weighers

If a `value` object grows after being cached, `weigher` is not invoked again just because of mutation. This makes reported total weight **smaller than actual cost**.

Solutions:

- Use `record`/immutable DTOs or collection snapshots.
- When a value needs to change, create a new value and `put`/`@CachePut` to trigger weight recalculation.
- Do not share a mutable object and mutate it from another thread without proper synchronization.
- If sizes change unpredictably and snapshots are impractical, consider caching a serialized form or building a different cache policy.

### 11.2. Correct Keys Still Matter

`maximumSize` and `maximumWeight` only govern eviction; they **do not fix broken cache keys**. If a method returns tenant- and user-scoped data while the key is only `productId`, the cache can return wrong data regardless of quota.

Requests with ever-changing filter/locale/page parameters drive high cardinality; canonical key design reduces false misses and avoids wasting quota on equivalent keys.

### 11.3. Expiration and Capacity Eviction Are Different

`expireAfterWrite` removes entries by time since write; `expireAfterAccess` relies on idle time without access; `maximumSize`/`maximumWeight` relies on entry count or weight pressure. An entry can be removed for **whichever applicable reason triggers**.

A long TTL does not mean the cache will keep a value for the full TTL if capacity is exceeded. Conversely, a large quota does not keep data fresh without expiry or invalidation when the source changes.

### 11.4. Concurrency and Hot Keys

When a cache is full and evicts a very hot key, multiple requests may miss simultaneously. `@Cacheable(sync=true)` asks the provider to coordinate loading per key when supported, yet it does not alter quota and carries its own restrictions: one cache per operation, no `unless`, and no combining other cache operations on the same method.

Illustrative example:

```java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public Product load(String id) {
    return repository.find(id);
}
```

Caffeine provides atomic get/load mechanics within a native cache instance. However, across multiple JVMs where each JVM has its own Caffeine cache, `sync=true` does **not** guarantee a single DB request cluster-wide.

### 11.5. Local Caffeine Is Not a Shared Distributed Cache

- Each JVM has its own cache instances and quotas.
- Pod A evicting a key under capacity pressure does not mean Pod B removes that key.
- Restarting a pod starts with an empty cache; warmup can spike source load.
- If a multi-node shared cache is needed, use a suitable provider such as Redis/JCache and design consistency/invalidation; Caffeine can still serve as an L1 cache, yet it does not automatically become Redis.

### 11.6. `maximumWeight` Is Not a Strict Hard Cap for RSS

Even when `weightedSize() <= maximumWeight`, heap/RSS can exceed the logical budget due to overhead, shared objects, serialization buffers, in-flight loading threads, native memory, and maintenance timing. For systems that must avoid OutOfMemory errors, leave headroom, set container memory limits, monitor heap, and run load tests; never treat a weigher as an exact heap profiler.

## 12. Common Errors and Diagnostics

| Symptom | Common Cause | How to Check and Fix |
|---|---|---|
| `@Cacheable` caches, yet RAM keeps growing | No quota or too many cache regions | Verify `CaffeineCacheManager`, `maximumSize/Weight`, and cache names count |
| `maximumSize(1000)` set, yet heap stays too high | Very large entries exist; quota counts entries, not bytes | Switch to weighted policy or split caches |
| Configuring both `maximumSize` and `maximumWeight` fails | Two capacity policies are mutually exclusive | Choose one policy per cache |
| `maximumWeight` has no effect | Missing `weigher` or overridden by another spec | Check actual builder, Boot precedence, and native policy |
| Weigher frequently throws `ClassCastException` | Spring cache holds multiple value types, null sentinels, or unsafe cast | Split caches by type, control nulls, write a safe weigher |
| Cache returns value, yet next call still misses | Entry weight > quota; cache does not retain entry | Measure real weight, raise budget reasonably, or split data |
| Weighted size reports very low while heap is high | Mutable object grew after put or weight omits overhead | Switch to snapshots/immutable objects; improve estimation |
| Configured `maximumWeight=100000` and assumed it means 100 KB | Weigher unit was not specified | Explicitly document units (bytes, KiB, records, vertices) |
| Increasing size still leaves hit rate low | Key cardinality too large or TTL too short | Measure key distribution, expiration, and query parameters |
| Test asserting key A must be evicted fails | Caffeine chooses victims via adaptive eviction | Assert budget after maintenance, do not hardcode order |
| `estimatedSize()` temporarily exceeds target | Maintenance has not finished | Call `cleanUp()` in tests; avoid instant assertions |
| Boot properties do not affect configured bean | Custom `CacheManager` exists or spec takes precedence | Inspect bean type and auto-config conditions |
| One region is weighted, another region's policy changes unexpectedly | `setCaffeine` applies manager-wide | Use `registerCustomCache` or separate managers |
| Adding Caffeine dependency still does not cache | `@EnableCaching` missing or self-invocation | Verify Spring proxy and bean lifecycle |
| Heavy eviction spikes DB QPS | Quota too small; hot keys constantly replaced | Tune by hit rate, set proper capacity, use sync/throttling |
| Multiple pods together consume too much heap | Local Caffeine is a **per-instance** quota | Plan cluster-wide budget by replica count |
| `recordStats()` shows no data | Stats not enabled on the corresponding native cache | Confirm active manager/backend and enable recordStats |

## 13. Self-Practice Exercises

### Exercise 1 — Choosing Size vs. Weight

A system stores two types of data:

- `Cache A`: small String/DTO profiles with roughly similar retained cost.
- `Cache B`: file metadata or binary payloads ranging from 1 KiB to several MB.

**Choice guide:** for A try `maximumSize`; for B consider `maximumWeight` and a weigher based on payload units. Still measure actual heap, because weight is not heap bytes.

### Exercise 2 — Mutable Value

`weigher` computes `List.size()`, and a list with 10 elements is cached. The caller adds 500 elements to the same object without calling `put` again. Does `weightedSize()` automatically increase to reflect the new size?

**Answer:** No. Weight is recorded when an entry is created or updated through the cache; mutating the object outside the cache does not trigger re-weighing. Use immutable snapshots or re-put the value.

### Exercise 3 — Over Budget

A weighted cache has a quota of 5 units, and a new entry has weight 6. The `@Cacheable` method is called twice. Is the second call guaranteed to hit?

**Answer:** No. An over-quota entry may be rejected from retention or evicted; the second call will miss. Do not equate the method returning a value with the provider retaining the entry.

### Exercise 4 — Two Caches Sharing One Manager

A manager uses `maximumSize(1000)` for regions `users` and `products`. Is the combined maximum across both regions 1,000 entries, or does each region get 1,000 entries?

**Answer:** The policy applies to each Cache created by the manager; the two regions have independent quotas. Estimate total capacity across all regions.

### Exercise 5 — Test Design

With `maximumSize(2)`, call A, B, C, then `cleanUp()`. Should a test assert that A is definitely evicted?

**Answer:** No. Tests should verify the entry count within quota after maintenance, loader call counts, and expected hits/misses; Caffeine does not guarantee FIFO eviction order in the general case.

## 14. Project Adoption Checklist

1. **Is the problem cardinality or memory footprint?** If values are fairly uniform, start with `maximumSize`; if they vary widely, evaluate a weighted policy.
2. **Does each cache region have its own budget?** `setCaffeine` applies across manager-created caches; use `registerCustomCache` for exceptions.
3. **What is the weight unit?** Bytes, KiB, record count, or computed cost? Document it clearly in code and dashboards.
4. **Is `Weigher` fast and deterministic?** No IO, no negative values, no overflow, no reliance on post-put mutations.
5. **Are values immutable?** If mutable, can weight become stale? Are snapshots needed?
6. **Have two limits on one builder been avoided?** `maximumSize` and `maximumWeight` must not be combined.
7. **Are dependencies right?** Plain Spring Framework uses `spring-context-support` for `CaffeineCacheManager`; Boot's starter cache can pull in this module.
8. **Are `@EnableCaching` and proxies working?** Do not evaluate effectiveness if annotations are not actually intercepted.
9. **Is Boot precedence right?** `spring.cache.caffeine.spec` can override builder beans; custom managers do not automatically apply all properties.
10. **Have the actual provider and policy been verified?** Grab the native cache, check `policy().eviction()`, and inspect `estimatedSize()/weightedSize`.
11. **Have hit rate + data source + GC been measured?** Never tune solely by a single quota number.
12. **Have oversized keys, 0 weight, nulls, and mutable objects been tested?** Cover edge cases matching your real model.
13. **Have multiple regions and multiple pods been tested?** Quotas are per Cache instance, not system-wide totals.
14. **Have expiration and invalidation been designed separately?** Capacity does not replace TTL; TTL does not solve capacity budgets.
15. **Have miss/stampede consequences been anticipated?** Small quotas can cause churn; consider `sync=true`, load shedding, and load testing.

### Conclusion

**`maximumSize(N)` bounds entry count; `maximumWeight(W)` paired with `weigher` bounds the estimated total cost of entries.** The two options cannot be used together on the same cache builder. Weight is computed when entries are inserted or updated, does not automatically adjust when mutable objects change, and is not an exact heap measurement. When integrating with Spring, configure policies on `CaffeineCacheManager` or custom native caches, leaving `@Cacheable` focused on cache regions and keys. Evaluate against real workloads: hit rate, per-region quotas, heap/GC, loader counts, and downstream source impact.

### Reference Documentation

- Caffeine Wiki — Eviction, maximumSize, maximumWeight, weigher, and weight semantics: https://github.com/ben-manes/caffeine/wiki/Eviction
- Caffeine Wiki — Statistics: https://github.com/ben-manes/caffeine/wiki/Statistics
- Caffeine Javadoc — Caffeine builder: https://javadoc.io/doc/com.github.ben-manes.caffeine/caffeine/3.2.2/com.github.benmanes.caffeine/com/github/benmanes/caffeine/cache/Caffeine.html
- Spring Framework 6.2 — `CaffeineCacheManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Spring Framework — Cache abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Boot — Caching / Caffeine configuration: https://docs.spring.io/spring-boot/reference/io/caching.html