# Criteria for Selecting Suitable Methods to Cache in Spring Cache

## Objectives

This lesson helps you determine which Java methods are worth caching with Spring Cache, when not to cache, how to choose keys and refresh policies, how to use @Cacheable/@CachePut/@CacheEvict, and how to verify benefits and correctness before deployment.

**Scope:** Spring Framework Cache Abstraction caches results **at the method invocation level**, based on keys. With @Cacheable, a call through a Spring proxy checks the cache first: if a value exists (cache hit), the method may not be executed; if absent (cache miss), Spring invokes the method and may cache the return value. The framework provides the Cache/CacheManager contract, while TTL, capacity limits, distribution, and size-based eviction are decided by the cache provider.

## 1. When Is Caching Results Actually Beneficial?

A good cache candidate must simultaneously satisfy two sets of conditions:

- **Correctness:** calls with the same key must be allowed to reuse the same result within a defined time window; skipping execution must not lose important side effects.
- **Benefit:** the cost of accessing and maintaining the cache is smaller than the avoided work; there are enough repeated calls and a sufficiently high hit ratio.

For example, `findProductById(42)` looking up a product from the database may be called many times, has relatively stable output, and incurs query cost: usually a good candidate. Conversely, `chargeCard()` must record a transaction every time it is called: `@Cacheable` could prevent the method from running on a cache hit, so it is **unsuitable for ensuring payment business logic**.

Do not decide simply because a method "runs slowly". Ask carefully: can the result be reused, do calls share keys, can users tolerate stale data, and when the source changes, who refreshes the cache?

## 2. Seven Core Criteria for Selecting Methods

### 2.1. Result Stability by Key and Context

The result must be relatively deterministic: the same parameters and relevant business conditions produce the same value within the cache window. Beyond parameters present in the Java signature, results sometimes depend on tenant, logged-in user, locale, configuration, access permissions, rule versions, or time.

If the cache key contains only `productId` while results are customized by tenant or locale, two calls in different contexts can receive the wrong data. The solution is choosing complete keys, designing proper namespaces, or not caching when safe isolation is impossible. Conversely, putting a millisecond-changing timestamp into the key usually causes the cache to get almost zero hits.

### 2.2. Cost of the Origin Call

Worthwhile candidates typically include: expensive database queries, HTTP/gRPC calls to other systems, aggregating data from multiple sources, or CPU-heavy calculations. A method that merely reads a variable, adds two numbers, or does an already cheap operation may incur more overhead going through a cache.

Measure latency without caching (p50/p95/p99) and the fraction of requests sharing the same key. **Hypothetical** example: origin takes 90 ms, cache hit takes 3 ms, hit ratio is 70%; average latency is roughly 0.7 × 3 + 0.3 × 90 = **29.1 ms**, excluding cache miss overhead, cache writes, network, and invalidation. If the hit rate is only 1%, the outcome looks completely different.

### 2.3. Repetition Level and Key Cardinality

A cache has value when the same keys appear frequently enough. Public catalog lookups or region-based config usually have high repetition. Free-form search with arbitrary query/page/sort/filter combinations, timestamped reports, or deeply personalized data can generate millions of rarely repeated keys, consuming resources without raising the hit ratio.

Count distinct keys, access distribution, percentage of one-off keys, and entry growth rate before choosing to cache.

### 2.4. Tolerance for Stale Data

Define the **maximum acceptable update lag** for the business domain. Product catalogs may tolerate being stale for a few minutes; inventory may need fast synchronization; account balances for confirming transactions or current authorization checks may require reading directly from the source.

TTL does not mean data is immediately accurate after an update. An entry can still be stale until it expires or is proactively deleted. Spring has no standard TTL attribute on `@Cacheable`; TTL is configured on the provider such as Caffeine/Redis or the respective provider.

### 2.5. Refreshability and Cache Eviction

Every cached read method must answer the question: "When the source changes, how is the cache updated?"

- **TTL:** entries expire after a configured duration—easy to operate, but has a stale window.
- **@CacheEvict:** deletes a key or entire region once the source-updating method succeeds.
- **@CachePut:** always executes the method and writes the new result into cache; suitable when the return value is the exact version to keep.
- **Events or distributed invalidation:** needed if multiple instances maintain separate local caches.

Inside a transaction, deleting the cache before the database commits can cause races or stale repopulation; if the transaction rolls back, cache state can also diverge from the source. For consistency-sensitive data, design **post-commit** invalidation timing or an appropriate transaction-aware mechanism.

### 2.6. Size and Storability

An ideal cached value is small, frequently read, and rarely mutable. Avoid arbitrarily caching large blobs, streams, objects holding request state, JPA entities tied to a persistence context/lazy proxies, or sensitive data lacking isolation policies. Immutable DTOs are generally easier to manage than live entities.

Check RAM budgets, max entries, TTL, eviction policies, serializer/schema versions, network transfer times, and how to clean up when deploying a new version. `ConcurrentMapCacheManager` is handy for examples and small apps, but lacks production-ready TTL/max-size controls.

### 2.7. Safety of Skipping the Method Body

`@Cacheable` is unsuitable for methods where **every invocation must perform a side effect**: creating orders, sending emails, writing mandatory audit logs, charging payments, incrementing business counters, or checking current permissions under zero-staleness policies. Caching a side-effecting method can prevent the side effect from happening.

Read methods must also be checked for time or randomness dependencies. Computing results from stable inputs is cacheable; generating random OTP codes or reading live status likely is not.

## 3. Example Matrix for Selecting Candidates

| Method | Recommendation | Explanation/Conditions |
| --- | --- | --- |
| findProductById(id) | Usually cache | Repeated lookups; needs invalidation when product is edited/deleted |
| listCategories(locale) | Usually cache | Infrequently changes; key includes locale; TTL per acceptable freshness |
| calculateQuote(ruleVersion, country, input) | Cacheable | Deterministic output, but must include rule version |
| search(query, page, sort, filter) | Consider carefully | Many key combinations; measure repetition and cap entries |
| getInventory(productId) | Consider carefully | Changes frequently; short TTL/invalidation or read from source |
| getUserDashboard(userId, tenantId) | Conditional | Requires key isolating user/tenant and refresh on permission/data changes |
| chargeCard(), createOrder() | Do not use @Cacheable | Write operations with side effects; handle idempotency at business layer |
| now(), generateRandomToken() | Usually do not cache | Values change with time/randomness |
| add(int a, int b) | Usually not worth it | Computation cost is too small |

**Selection summary:** methods that are **reads + expensive + repeated on same keys + tolerate controlled staleness + safe to skip execution** are the best starting points.

## 4. Choosing Accurate Cache Keys

By default Spring uses `SimpleKeyGenerator`:

- No parameters → `SimpleKey.EMPTY`.
- One parameter → that parameter object itself as the key.
- Multiple parameters → `SimpleKey` combining all parameters.

This relies on `equals/hashCode` of the input objects. If the signature has parameters unrelated to the result, or the result depends on context outside parameters, use the `key` attribute (SpEL) or a custom `KeyGenerator`. Example:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public ProductDto findById(long productId) {
    return repository.findDtoById(productId);
}
~~~

**This is an illustrative snippet inside a Spring service**, assuming `repository` and `ProductDto` exist; it is not a standalone program. The expression `#p0` extracts the first parameter so the key is `productId`.

If the method requires `tenantId`:

~~~java
@Cacheable(cacheNames = "productsByTenant")
public ProductDto findByTenantAndId(String tenantId, long productId) {
    return repository.findForTenant(tenantId, productId);
}
~~~

With two parameters, the default key includes both `tenantId` and `productId`. This **does not replace authorization checks**: cache hits must still adhere to the security model, and delete/update operations must use the exact same key logic. With distributed caches, check serializers, cache region names, and collision risk when converting types to strings.

## 5. Matching Annotations to Behavior

| Need | Annotation | Key Point |
| --- | --- | --- |
| Return stored result on cache hit | @Cacheable | May skip the entire method body |
| Execute method then write new result | @CachePut | Method body always executes |
| Remove entry/region after source change | @CacheEvict | Evicts after successful completion by default |
| Group multiple cache operations | @Caching | Declares multiple operations on the same method |
| Share configuration at class level | @CacheConfig | Shares cacheNames, keyGenerator, etc. |

For `@Cacheable`:

- **cacheNames:** specifies logical cache regions.
- **key:** SpEL defining the key; `#p0`, `#p1` are the first and second parameters respectively.
- **condition:** decides whether caching applies based on data available before calling the method.
- **unless:** after computing the result, can veto storing it; e.g., `unless = "#result == null"`.
- **sync = true:** can coordinate requests missing the same key concurrently to reduce duplicate computation if supported by the cache provider; does not automatically guarantee distributed locking across all instances.

Do not arbitrarily combine `@Cacheable` and `@CachePut` on the same method because one annotation can suppress execution while the other requires execution. When updates are needed after writes, typically choose `@CacheEvict` or `@CachePut` on the **write** method and keep `@Cacheable` on the **read** method.

## 6. Runnable Example with Spring Framework and Java 17

This example creates a small console application using Spring Framework 6.2.19. The `findProductName(id)` method simulates querying a source: each time the body runs, a counter increments. Calling ID 42 twice demonstrates a cache hit.

**Project structure:**

~~~text
cache-selection-demo/
├── pom.xml
└── src/main/java/demo/CacheSelectionDemo.java
~~~

**pom.xml:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>cache-selection-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.19</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.1</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**src/main/java/demo/CacheSelectionDemo.java:**

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheSelectionDemo {

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("products");
        }

        @Bean
        public ProductService productService() {
            return new ProductService();
        }
    }

    public static class ProductService {
        private final AtomicInteger loadCounter = new AtomicInteger();

        @Cacheable(cacheNames = "products", key = "#p0",
                   unless = "#result == null")
        public String findProductName(long productId) {
            int n = loadCounter.incrementAndGet();
            return "Product-" + productId + " [load " + n + "]";
        }

        public int sourceLoadCount() {
            return loadCounter.get();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            ProductService service = context.getBean(ProductService.class);

            System.out.println(service.findProductName(42));
            System.out.println(service.findProductName(42));
            System.out.println("Source loads: " + service.sourceLoadCount());
            System.out.println(service.findProductName(7));
            System.out.println("Source loads: " + service.sourceLoadCount());
        }
    }
}
~~~

Run from the project directory with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheSelectionDemo
~~~

**Program stdout:**

~~~text
Product-42 [load 1]
Product-42 [load 1]
Source loads: 1
Product-7 [load 2]
Source loads: 2
~~~

For ID 42, the first call misses so the method body runs and caches `"Product-42 [load 1]"`; the second call hits so the counter does not increment. ID 7 has a different key, triggering a second load. `@EnableCaching` activates annotation processing; `ConcurrentMapCacheManager` stores in process RAM for illustration and does not represent a production setup with TTL/size limits.

**Proxy note:** caching annotations in default proxy mode apply only to calls passing through a Spring proxy. If another method in the same class calls `this.findProductName(42)`, Spring does not intercept that self-invocation under default proxy mechanics. Avoid manually calling `new` on an object and expecting `@Cacheable` to work; invoke Spring-managed beans from other beans or design appropriate service boundaries. `private`/`final` methods are also unsuitable proxy interception points.

## 7. When the Source Changes: Align Read Keys and Evict Keys

This is an **illustrative snippet** for a Spring-managed service (assuming `repository` and `ProductDto` exist):

~~~java
@Cacheable(cacheNames = "productById", key = "#p0")
public ProductDto getProduct(long id) {
    return repository.findDtoById(id);
}

@CacheEvict(cacheNames = "productById", key = "#p0")
public void renameProduct(long id, String newName) {
    repository.rename(id, newName);
}
~~~

Both operations use the same `cacheNames` and the same ID key. After `renameProduct` finishes successfully, Spring evicts the entry by default; the next read reloads the data. If updates run inside a transaction, check commit timing before deciding on an invalidation strategy. If the write method returns the new DTO for that key directly, `@CachePut` may fit better, provided the returned data is complete and accurate.

In multi-instance systems, a local cache on machine A does not automatically know machine B just evicted or updated an entry. When cross-node consistency is required, use a shared cache or a multi-node invalidation channel; merely placing `@CacheEvict` on each process may be insufficient.

## 8. Decision Process in a Project

1. **Find candidates:** use tracing/profiling to identify read methods with significant latency, QPS, or source cost.
2. **Measure repetition:** collect stats on keys, potential hit ratio, distinct key count, and parameters shaping the output.
3. **Define the correctness contract:** maximum staleness, access permissions, user/tenant context, size, and whether skipping the body is safe.
4. **Design keys and cache regions:** include sufficient parameters; clear region names, serialization/versioning rules, and consistent keys across reads and writes.
5. **Design refresh strategy:** TTL for tolerably stale data, eviction or put on write flows, transaction handling, and multi-node behavior.
6. **Pick a provider:** local in-memory or shared/distributed depending on topology, max size, eviction, infrastructure failure modes, and network cost.
7. **Test:** calling twice with the same key must hit; different keys must miss; updates must honor allowed staleness; tenant/user isolation must hold; test concurrency and provider failures.
8. **Measure post-deployment:** hit/miss, p95/p99, origin QPS, memory/entries, evictions, stale data, and provider errors. If there is no net benefit or correctness is hard to guarantee, remove caching from that candidate.

### Checklist Before Enabling @Cacheable

- [ ] The method is primarily a **read**, with no mandatory side effects on every call.
- [ ] Results for the same key can be safely reused for a defined duration.
- [ ] Metrics exist for origin cost and repetition on the same keys.
- [ ] The key includes ID, tenant, locale, permissions, filters, and version whenever they affect the result.
- [ ] Acceptable staleness, TTL, and/or invalidation mechanisms are defined.
- [ ] Values are suitable for storage, with size and cardinality controlled.
- [ ] Calls pass through a Spring proxy.
- [ ] Cache hit/miss, data writes, multi-instance behavior, and authorization have been tested.
- [ ] Metrics exist to confirm actual improvement.

## 9. Common Mistakes and How to Avoid Them

**Caching every read query.** High read volume with a different key every time yields no hits; measure repetition first.

**Forgetting context in keys.** Tenant/user-specific results cached solely by `productId` can leak data; design keys and permission checks explicitly.

**Failing to evict after modifying the source.** Stale data persists until TTL or longer if the provider lacks TTL; tie write paths to proper invalidation.

**Assuming `@Cacheable` controls TTL.** The framework only abstracts operations; select and configure the provider for capacity, TTL, eviction, and topology.

**Calling internal methods within the same bean.** Self-invocation bypasses the proxy so caching annotations may not take effect; extract a service or use an appropriate interception mechanism.

**Unintentionally caching errors or nulls.** Consider `unless`/`condition` and dedicated short-TTL negative caching when appropriate.

**Ignoring cache stampedes.** Many requests missing the same key concurrently can overwhelm the source; `sync=true` reduces duplicate computation when supported by the provider, though it does not distribute locks across nodes by default.

**Looking only at cache-hit latency.** Account for misses, entry counts, serialization/network cost, staleness, and cache-failure risks.

## 10. Self-Check Questions

1. Is a fast-computing method whose every request has completely different inputs worth caching? **Usually no**: low hit rate and extra storage overhead.
2. Why should a method fetching tenant-specific configuration not be cached solely by ID? **Because** tenants may receive different results; the key lacks context.
3. Does `@CachePut` skip the method body on a hit like `@Cacheable`? **No**: `@CachePut` always executes the method.
4. Can TTL be configured using a standard attribute on `@Cacheable`? **No**: configure TTL on the cache provider.
5. When the same key misses concurrently, does `@Cacheable` guarantee computing only once by default? **No**; consider `sync=true` and provider capabilities.
6. Does calling `this.getProduct(id)` from inside the same bean reliably go through the cache proxy? **No** in default proxy mode.

## References

- Spring Framework — Understanding the Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache/strategies.html
- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Configuring the Cache Storage: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework — TTL/TTI/Eviction policy: https://docs.spring.io/spring-framework/reference/integration/cache/specific-config.html