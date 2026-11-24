# Cache and Per-Region Operation Contracts in Spring Framework

## 1. Problem to Solve

When a feature must read expensive data (databases, external services, heavy computations), caching helps reuse results for equivalent calls. However, the key architectural question is not just "to cache or not to cache", but also: **which data belongs to which cache region, which key represents a result, when is it read/written/deleted, and who is responsible for keeping the data accurate after the source changes?**

In Spring Framework, each **cache region** is accessed by a logical name, such as `products`, `productPrices`, or `categorySummary`. This region is not a heap/JVM region: it is a `key → value` mapping space managed by a specific `Cache`. The cache provider determines physical storage (in-process memory, distributed memory, etc.), lifetime, synchronization capabilities, and eviction policies.

Lesson objectives:

- Distinguish `CacheManager`, a `Cache`/region, and individual entries by key.
- Understand the contract for reading, loading on miss, overwriting, evicting a single key, and clearing an entire region.
- Map that contract to `@Cacheable`, `@CachePut`, `@CacheEvict`, and data lifecycle management.
- Design keys, invalidation, concurrency, and transaction boundaries to avoid returning stale results or colliding data.

## 2. Region Model and Request Flow

```text
Client → Spring bean proxy / CacheInterceptor
               │
               ├─ Resolve cache name / CacheManager / CacheResolver
               ├─ Compute key (KeyGenerator or SpEL expression)
               └─ Cache("products") ── key "P1" ──> Product(P1, "Pen")
                       │ miss
                       └─ Invoke real method → data source → store result → return
```

Example with the same key `"P1"` across different regions:

| Region | Key | Value meaning |
| --- | --- | --- |
| `products` | `"P1"` | Product details |
| `productPrices` | `"P1"` | Calculated selling price |
| `productStock` | `"P1"` | Inventory or inventory snapshot |

Evicting `"P1"` in `products` **does not automatically evict** the corresponding entry in the other two regions. Two regions with different names are two logical spaces; this does not automatically guarantee two independent physical stores. A source update may invalidate multiple regions at once, so data dependency relationships must be explicitly described.

The architecture consists of two complementary contracts:

1. **Access contract:** the same region name and key generation strategy must lead to the expected data type; operations have clear semantics.
2. **Consistency contract:** when source data is created/updated/deleted, the program must update or invalidate all affected caches; TTL is only an additional safety net, not a default substitute for refreshing data.

A cache is a regenerable copy, **not a source of truth**. Business data must be stored somewhere with its own durable contract, such as a database.

## 3. Two Core Interfaces

`org.springframework.cache.CacheManager` provides `getCache(String name)` and `getCacheNames()`. `getCache(name)` returns the corresponding `Cache` or `null` if that region does not exist; whether a new region is created dynamically by name or only pre-declared names are accepted depends on the implementation/configuration. `CacheManager` is not the store containing individual entries itself.

`org.springframework.cache.Cache` is the operation contract **within a single region**:

| API | Notable contract |
| --- | --- |
| `get(key)` | Returns `Cache.ValueWrapper` if a mapping exists, or `null` on a miss. The wrapper can hold a `null` value, so it distinguishes "cached null" from "no entry". |
| `get(key, Type.class)` | Retrieves the value by type; a `null` result cannot distinguish cached-null from a miss. A type mismatch can cause an error. |
| `get(key, Callable<T> loader)` | On a miss, invokes the loader and stores the result; the provider may synchronize loading for the same key, but you must check the actual capabilities of the backend. |
| `put(key, value)` | Associates/replaces the mapping in the region; visibility may be delayed with decorators or asynchronous backends. |
| `putIfAbsent(key, value)` | Adds only when no mapping exists; an atomic operation is desired, but you must check the guarantees of the specific provider. |
| `evict(key)` | Removes the mapping for the exact key; may be performed lazily. |
| `evictIfPresent(key)` | Requests eviction such that subsequent lookups immediately stop seeing the entry; the `boolean` indicates whether a mapping previously existed when determinable. |
| `clear()` | Empties the **entire region**, which may involve latency. |
| `invalidate()` | Requests that all entries in the region immediately become invisible; returns whether it previously contained any entries when determinable. |
| `getName()`, `getNativeCache()` | Inspects the logical name and the underlying provider object. |

Words like "immediately" or "atomic" above are expectations in the API contract; the backend, transaction decorator, and deployment configuration determine the actual level of guarantees. Do not assume that `put`, `evict`, and `clear` participate in an atomic transaction with the database. Spring Cache also provides `retrieve(...)` variants based on `CompletableFuture` for caches supporting asynchronous access (Spring Framework 6.1+).

Reading directly in Java when programmatic operations are genuinely needed:

```java
Cache products = cacheManager.getCache("products");
if (products == null) {
    throw new IllegalStateException("Missing cache region: products");
}

Cache.ValueWrapper entry = products.get("P1");
if (entry == null) {
    // Key P1 does not exist yet (cache miss).
} else {
    Object value = entry.get(); // May be null: this is still a cache hit.
}

products.evict("P1"); // Only entry P1 in region products.
products.clear();     // All entries in region products.
```

The snippet above is an illustration in a context where the `cacheManager` variable already exists, not a standalone runnable Java file.

## 4. Design Contract for Each Region

Before adding annotations, answer all of the following questions for **each region**.

| Attribute | Needs decision | Example |
| --- | --- | --- |
| Name and purpose | What data does the region represent, and who owns it? | `products` only stores `Product` by SKU |
| Key | Which parameters cause the result to differ? | `tenantId + ":" + sku` if data is per-tenant |
| Value | Type, immutability, shareability | Immutable `Product`/record instead of mutable entity |
| Source of truth | Where does the result originate? | `products` table in the database |
| Read and load | What to do on a cache miss? | Query database, store on success |
| Update | Write-through with `@CachePut` or evict to reload next time? | Save to database then put new entry |
| Evict and clear | Which keys are affected, are multiple regions needed? | Updating price also evicts `productPrices` |
| Expiration/capacity | Where are TTL, max size, and eviction policy set? | Caffeine/Redis config, not in the generic `Cache` API |
| Consistency | How much staleness is acceptable? Multi-node? | Price data is more sensitive than catalog |
| Observability and errors | How to measure hit/miss, eviction, latency, backend errors? | Metrics per region, alert on rising misses |

**Keys must be stable, complete, and properly scoped.** If the result depends on user, tenant, language, filter, version, or access permissions, omitting that component from the key can return the wrong data. Do not use only the method name or a single parameter if other factors also affect the result. For multiple parameters, Spring defaults to `SimpleKeyGenerator`; if you want a shared or uniform format across methods, declare the key explicitly or use a shared `KeyGenerator`.

Do not force two incompatible data types into the same region/key. Avoid storing objects that can be mutated in place: caching a mutable instance and modifying it directly can alter observed results even without calling `put`. Use immutable DTOs/records or copy/serialize intentionally.

## 5. Annotation Contract: Read, Write, Evict on a Region

| Annotation | Does the real method run? | Cache effect |
| --- | --- | --- |
| `@Cacheable(cacheNames="products", key="#p0")` | Miss: yes; hit: normally no | Hit returns cached data; miss runs method and caches result |
| `@CachePut(cacheNames="products", key="#p0.sku()")` | **Always runs** | After the method succeeds, puts the return value into cache |
| `@CacheEvict(cacheNames="products", key="#p0")` | Yes | By default evicts one entry **after** the method completes successfully |
| `@CacheEvict(cacheNames="products", allEntries=true)` | Yes | Evicts all entries in a region, ignoring key |
| `@Caching(evict={...})` | According to inner annotations | Groups operations, e.g., evicting two regions simultaneously |
| `@CacheConfig(cacheNames="products")` | Only sets shared class-level config | Reduces repetition of region name/key generator/manager; does not cache by itself |

Attributes to read carefully:

- `cacheNames` (alias `value`) specifies region names; multiple can be declared, but writing to multiple regions should not be treated as a transaction.
- `key` is a SpEL expression. `#p0` is the first parameter, independent of whether parameter names are retained at compile time; `#result` can be used where Spring supports it **after** invocation (e.g., `unless`, `@CachePut` key).
- `condition` is evaluated beforehand to decide whether to apply caching; `unless` is evaluated after the method runs to veto caching the result, e.g., `unless="#result == null"`.
- `@CacheEvict(beforeInvocation=true)` evicts **before** method execution, even if the method later throws an error. The default `false` evicts after the method succeeds, which is better when old data should be preserved if an update fails.
- `@Cacheable(sync=true)` requests coordination for loading the same key to reduce concurrent duplicate loads; the provider must support it. When using `sync=true`, declare only one cache, do not use `unless`, and do not combine with other caching operations on the same method.
- `cacheManager` selects a manager when there are multiple backends; `cacheResolver` customizes dynamic cache selection. Do not specify both attributes on the same operation.

**Common CRUD convention:** read with `@Cacheable`; create/update with `@CachePut` **if you are certain the returned value matches the exact cache representation**, or `@CacheEvict` **if reloading is needed due to multiple dependent data items**; delete the source record with `@CacheEvict`. Do not combine `@Cacheable` and `@CachePut` on the same method: one annotation wants to skip invocation on a hit, while the other always wants to run.

## 6. Complete Example: Single Region, Read → Update → Delete Cycle

The minimal example below uses Java 17, Spring Framework 6.2.x, and an in-process `ConcurrentMapCacheManager`. Source data is simulated by a repository; production code replaces that repository with a database. There is only one region `products`; each SKU is a key. The service class is a Spring bean invoked from outside the proxy, so annotations take effect.

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cache-region-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Create `src/main/java/CacheRegionDemo.java`:

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheRegionDemo {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }

    @Bean
    ProductRepository productRepository() {
        return new ProductRepository();
    }

    @Bean
    ProductService productService(ProductRepository repository) {
        return new ProductService(repository);
    }

    public record Product(String sku, String name) {}

    public static class ProductRepository {
        private final Map<String, Product> data = new ConcurrentHashMap<>();
        private final AtomicInteger loads = new AtomicInteger();

        public ProductRepository() {
            data.put("P1", new Product("P1", "Pen"));
        }

        public Product find(String sku) {
            loads.incrementAndGet();
            return data.get(sku);
        }

        public Product save(Product product) {
            data.put(product.sku(), product);
            return product;
        }

        public void delete(String sku) {
            data.remove(sku);
        }

        public int loadCount() {
            return loads.get();
        }
    }

    public static class ProductService {
        private final ProductRepository repository;

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        @Cacheable(cacheNames = "products", key = "#p0",
                   unless = "#result == null")
        public Product find(String sku) {
            return repository.find(sku);
        }

        @CachePut(cacheNames = "products", key = "#p0.sku()")
        public Product save(Product product) {
            return repository.save(product);
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public void delete(String sku) {
            repository.delete(sku);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(CacheRegionDemo.class)) {
            var repository = context.getBean(ProductRepository.class);
            var service = context.getBean(ProductService.class);

            System.out.println("Read 1: " + service.find("P1"));
            System.out.println("Read 2: " + service.find("P1"));
            System.out.println("Source loads: " + repository.loadCount());

            service.save(new Product("P1", "Blue pen"));
            System.out.println("After update: " + service.find("P1"));
            System.out.println("Source loads: " + repository.loadCount());

            service.delete("P1");
            System.out.println("After delete: " + service.find("P1"));
            System.out.println("Source loads: " + repository.loadCount());
        }
    }
}
```

Run from the directory containing `pom.xml` (with JDK 17+ and Maven installed):

```bash
mvn -q compile exec:java -Dexec.mainClass=CacheRegionDemo
```

Output lines printed by the program (excluding Maven's own logs if logging is enabled in the environment):

```text
Read 1: Product[sku=P1, name=Pen]
Read 2: Product[sku=P1, name=Pen]
Source loads: 1
After update: Product[sku=P1, name=Blue pen]
Source loads: 1
After delete: null
Source loads: 2
```

Step-by-step explanation:

1. First `find("P1")` misses: Spring executes the repository once, then stores the result `Product(P1, "Pen")`.
2. Second call hits: the repository is not called, and the counter remains 1.
3. `save(...)` always executes the source update, then `@CachePut` replaces entry `products/P1` with the new product. The subsequent `find` hits the new value.
4. `delete("P1")` deletes from the source and evicts the exact entry. The subsequent `find` misses and calls the repository, so the counter becomes 2. The `null` result is not cached due to `unless`.

`ConcurrentMapCacheManager` is suitable for demos/tests; it does not configure TTL, memory limits, or invalidation propagation across JVMs. If the `save` method returns a DTO of a different type than the cached value or needs to update multiple related regions, choose to evict the regions rather than putting a value that violates the contract.

## 7. Extending the Contract When One Edit Affects Multiple Regions

Suppose the product detail page uses the `products` region, while the category page uses `productListByCategory`. Editing a product name changes both the detail record and the category list. Evicting a single key in `products` does not automatically refresh the list.

Illustrative example (methods/objects in a real system must be defined accordingly):

```java
@Caching(evict = {
    @CacheEvict(cacheNames = "products", key = "#p0.sku()"),
    @CacheEvict(cacheNames = "productListByCategory", allEntries = true)
})
public Product rename(Product changedProduct) {
    return repository.save(changedProduct);
}
```

This is an **illustrative snippet, not a standalone addition** to the `CacheRegionDemo.java` file above. Clearing the entire list can be costly under high traffic; if you already know the exact old/new category and list keys, evict only those keys. Especially when changing tenant or moving category, you must account for cache keys based on values **both before and after** the update.

Choosing a policy by data pattern:

| Scenario | Typical approach | Trade-off |
| --- | --- | --- |
| Detail by id, write result is already the final DTO | `@CachePut` with the same key | Next read is fast, but must ensure the value is accurate |
| Write changes multiple projections/lists | `@CacheEvict` affected keys/regions | Next miss must reload, but lower risk of wrong value |
| Batch operation alters most of a region | Intentional `allEntries=true` | Easy to get right, may cause many simultaneous misses |
| Data may only live for at most a bounded period | TTL on the provider | TTL bounds lifetime, does not guarantee immediate visibility of updates |
| Reading nearly immutable data | `@Cacheable` with a complete key | High efficiency, still needs a policy when the source changes |

## 8. Consistency, Transactions, and Concurrency

**A cache miss is not automatically safe from race conditions.** When two requests miss `products/P1` simultaneously, both may call the source; one request can read stale data and write it to the cache after another request has already updated or evicted it. `@Cacheable(sync=true)` helps reduce duplicate loads for the same key if supported by the provider, but does not solve all races between reads and writes. Data-level controls (versioning, transactions, event ordering, invalidation policies) are needed according to consistency requirements.

**Transaction boundaries:** `@CacheEvict` by default runs after the method returns successfully; that does not automatically mean "the database has committed" under every AOP/transaction ordering. If you need to update the cache after commit, you can use `TransactionAwareCacheManagerProxy` or post-commit event mechanisms (`@TransactionalEventListener(phase = AFTER_COMMIT)`), though you must still account for cache errors, nested transactions, and multiple nodes. Cache and database do not automatically participate in a shared atomic commit.

**Multiple processes:** `ConcurrentMapCacheManager` is a local cache; node A evicting an entry does not delete the copy on node B. For multi-instance systems, choose a shared cache like Redis or an invalidation broadcast mechanism, and plan for delayed/lost events. Consistency scope must be defined per region: a catalog may tolerate brief staleness, while permissions/balances/inventory often require source checks or stricter workflows.

**TTL and capacity:** The standard Spring Cache API has no universal switch to enable TTL across all providers. Configure `expireAfterWrite`/`maximumSize` (e.g., Caffeine) or Redis TTL in the cache storage configuration. Do not assume `@Cacheable` sets a TTL on its own; and do not treat expiration as an instant synchronization mechanism across nodes.

**Backend/cache errors:** Decide whether get/put/evict failures should fail the request or simply fall back to the source. `CacheErrorHandler` can customize error handling, but swallowing an evict error when the source has changed can leave stale data behind. Monitor hit/miss counts, source load latency, eviction counts, provider errors, and size per region to detect loss of effectiveness or consistency bugs.

## 9. Common Real-World Mistakes

1. **Forgetting `@EnableCaching` or calling within the same class:** annotations are not applied in the default proxy mode if calling `this.find(...)` internally, calling methods outside a Spring bean, or running too early before the proxy is ready. Design methods to be called through a Spring bean; proxies have limitations regarding `private`/`final` methods and self-invocation.
2. **Using keys lacking context:** `findPrice(sku, currency)` keyed only by `sku` mixes up currencies. Include `currency` (and tenant/user if needed) in the key.
3. **Mismatched keys between reads and writes:** `@Cacheable(key="#p0")` while `@CacheEvict(key="#p0.id")` with `p0` of a different type causes keys not to match and stale entries to remain.
4. **Believing `@CachePut` skips the method:** in reality it **always executes**. Use it to refresh the cache after business logic, not to save a read.
5. **Evicting one region while dependent data lives in another:** stale lists, searches, aggregations. Build a matrix of write operations → regions requiring invalidation.
6. **Treating cached-null as a miss:** `Cache.get(key)` returns a wrapper when null is cached; `Cache.get(key, Type.class)` cannot distinguish the two cases.
7. **Caching rapidly changing or highly sensitive data:** the cache can return stale data. Require clear consistency levels and consider reading directly from the source at critical decision steps.
8. **Assuming clear/evict are system-wide operations:** they only affect the region on the current backend/manager; they do not automatically refresh caches across all instances or dependent caches.
9. **Ignoring mutable objects, capacity, and TTL:** storing mutable references easily causes unpredictable behavior; unbounded local caches can retain data long-term and increase memory pressure.
10. **Relying on post-method eviction as a commit guarantee:** review AOP and transaction ordering; consider emitting invalidations after commit when needed.

## 10. Pre-Deployment Contract Checklist

For each region, verify via tests or real observation:

- **Hit/miss:** calling the same key twice increases the source call count only on the first call; calling a different key creates a separate entry.
- **Write:** modifying the source and reading again must return the correct value; dependent projections must also be refreshed as designed.
- **Delete:** deleting a specific key must not accidentally remove other keys; `allEntries=true` is used only when truly intending to clear the entire region.
- **Boundary:** two different tenants, currencies, or locales must not share a key; access control must not rely on stale caches to bypass checks.
- **Failure:** does a failed source operation still evict the cache? How does losing provider connectivity fall back? Does a rolled-back transaction leave a new value in the cache?
- **Concurrency/multi-node:** test concurrent reads and writes; verify how fast each instance recovers after invalidation and what level of staleness is acceptable.
- **Policy:** measure TTL, hit ratio, entry count, miss cost, and cache stampede; ensure memory/latency fit real traffic.

A good cache design can be stated in one sentence per region: **"This region stores what data type by which key, who loads it, who updates/evicts it, when it expires, and how much staleness is acceptable."** If you cannot answer that yet, annotations easily make the program run faster while making correctness hard to prove.

## Official References

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Cache Annotations: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Cache Storage Configuration: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework — TTL/TTI and provider-specific policies: https://docs.spring.io/spring-framework/reference/integration/cache/specific-config.html
- Spring Framework — `Cache` API contract: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html
