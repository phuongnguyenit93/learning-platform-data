# Distinguishing @CachePut from @Cacheable in Spring Cache

## Lesson Objectives

Both `@Cacheable` and `@CachePut` annotations can write a method's result into a cache, but they **differ in whether they execute the method**. Understanding this difference accurately helps you choose the right annotation for read flows and data-update flows, avoiding stale caches, lost side effects, or caching the wrong values.

After this lesson, you will be able to:

- Accurately explain the behavior of `@Cacheable` on cache hits and cache misses.
- Explain why `@CachePut` **always executes the method** and updates the cache with the post-execution result.
- Choose the right annotation for read, update, and delete methods.
- Keep `cacheNames` and `key` consistent between read and update operations.
- Understand the impact of `condition`, `unless`, exceptions, `null`, transactions, Spring proxies, and asynchronous calls.
- Run a Java 17 example with Spring Cache and verify method execution counters.

> **Core Rule:** `@Cacheable` is a tool for **reusing results to avoid re-running a method on a cache hit**. `@CachePut` is a tool for **always running a method and then writing the new result to the cache**, even when the corresponding key already holds data.

## 1. Both are cache annotations, but with two different goals

Suppose `findProduct(id)` queries the database to return a product. If 100 consecutive requests ask for the same ID and the data has not changed, running 100 queries can be wasteful. This is a case where `@Cacheable` can be used: read the source the first time, and return the stored result on subsequent calls.

Meanwhile, `renameProduct(id, newName)` has the job of **actually changing the product name**. Even if a cache entry for that ID already exists, the rename operation must still execute. If the update method returns the **complete new value** matching the cache used by reads, `@CachePut` can use that result to update the entry.

Illustrative example, assuming `ProductRepository` and `Product` are already defined:

~~~java
// Reads can return the stored result, skipping source queries on a hit.
@Cacheable(cacheNames = "products", key = "#p0")
public Product findProduct(long id) {
    return repository.findById(id);
}

// Writes must run; the return value is placed into the same cache/key.
@CachePut(cacheNames = "products", key = "#p0")
public Product renameProduct(long id, String newName) {
    repository.rename(id, newName);
    return repository.findById(id);
}
~~~

This is an **illustrative snippet in a Spring-managed service**, not a standalone Java program. `@CachePut` does not perform database writes for you: the code inside the method must still call the repository.

## 2. Behavior comparison table

| Criterion | `@Cacheable` | `@CachePut` |
| --- | --- | --- |
| Primary goal | Speed up reads by reusing results | Refresh/add a result in the cache after running the method |
| Cache hit, same key | Usually **does not call target method**; returns cached value | **Still calls target method**; overwrites entry with new result if conditions allow |
| Cache miss | Calls method, considers storing result | Still calls method and considers storing result |
| Relies on cache hit to skip execution? | Yes | No |
| Suitable for write operations with side effects? | Unsuitable when every call must execute | Can be suitable if the method must always run and returns the right value for the cache |
| Result when method throws an exception | No new successful value to write | No new successful value to write |
| `condition` / `unless` | Can control whether caching applies and stores | Can control cache writing, but does not cause the method to be skipped |
| Requires a proper cache key | Yes | Yes; if refreshing a `@Cacheable` entry, must use the exact same cache name and key |
| When not to use | When the method body has mandatory side effects on every call | When you only want to return existing cached data without running the method |

Do not think of `@CachePut` as a “stronger `@Cacheable`”. The two solve different needs.

## 3. Processing flow of @Cacheable

Suppose `getProduct(42)` is annotated with `@Cacheable(cacheNames = "products", key = "#p0")`.

~~~text
Client
  |
  v
Spring caching proxy
  |
  +--> compute key from id = 42
  |
  +--> check products[42]
         |
         +--> HIT --> return stored value
         |            (do not run getProduct)
         |
         +--> MISS --> run getProduct(42)
                      |
                      +--> method returns normally
                      |
                      +--> evaluate unless / related conditions
                      |
                      +--> if allowed: put products[42] = result
                      |
                      +--> return result to client
~~~

**Key takeaway:** on a cache hit, the code inside `getProduct` may not run at all. That works well for a side-effect-free read, but is dangerous if placed on an operation that must write data or trigger business events on every call.

Unsuitable example:

~~~java
@Cacheable(cacheNames = "payments", key = "#p0")
public Receipt chargeCard(String idempotencyKey, Payment payment) {
    return paymentGateway.charge(payment);
}
~~~

This is a **counter-example**, not a usage recommendation. Idempotency management and preventing duplicate charges require dedicated business/transaction design; `@Cacheable` cannot be treated as a mechanism to guarantee exactly-once payment.

## 4. Processing flow of @CachePut

Suppose `renameProduct(42, "New Name")` is annotated with `@CachePut(cacheNames = "products", key = "#p0")`.

~~~text
Client
  |
  v
Spring caching proxy
  |
  +--> always call renameProduct(42, "New Name")
           |
           +--> execute actual update logic
           |
           +--> return new Product object
           |
           +--> evaluate condition/unless per configuration
           |
           +--> if allowed: put products[42] = new Product
           |
           +--> return new Product to client
~~~

There is no branch saying “if key 42 already exists, skip renaming” as with `@Cacheable`. When the method returns successfully, Spring considers putting the result into the cache region under the configured key.

**Important limitation:** `@CachePut` stores **what the method returns**; it does not automatically reload data via another `@Cacheable` method. If `renameProduct` returns `boolean`, `void`, a status code, or a DTO with only partial data, putting that result directly into a cache intended for `Product` can corrupt the entry's type or content. When there is no suitable return value to update the cache accurately, consider **`@CacheEvict`** and let the next read reload the full data.

## 5. Runnable Java 17 example: comparing hit, miss, and update

The following console application uses **Spring Framework 6.2.10**, Java 17+, Maven, `@EnableCaching`, and `ConcurrentMapCacheManager`. An in-memory repository simulates the data source. Two counters show that:

- `@Cacheable` executes the method body only on a cache miss.
- `@CachePut` executes the method body on every call, even when the key already has an entry.
- When `@CachePut` uses the same cache name and key as `@Cacheable`, the next read receives the new value without reading the repository again.
- When the update method throws an exception before writing to the source, the old cached value is not replaced by a result from the failed call.

### 5.1. Directory structure

~~~text
cacheable-vs-cacheput/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── CacheableVsCachePutDemo.java
~~~

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>cacheable-vs-cacheput</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.10</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <version>3.14.0</version>
        <artifactId>maven-compiler-plugin</artifactId>
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

### 5.3. src/main/java/demo/CacheableVsCachePutDemo.java

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheableVsCachePutDemo {

    @Configuration
    @EnableCaching
    public static class Config {

        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("productNames");
        }

        @Bean
        public ProductRepository productRepository() {
            return new ProductRepository();
        }

        @Bean
        public ProductService productService(ProductRepository repository) {
            return new ProductService(repository);
        }
    }

    public static class ProductRepository {
        private final Map<Long, String> names = new ConcurrentHashMap<>();

        public ProductRepository() {
            names.put(42L, "Book");
        }

        public String findName(long id) {
            return names.get(id);
        }

        public String saveName(long id, String newName) {
            names.put(id, newName);
            return newName;
        }
    }

    public static class ProductService {
        private final ProductRepository repository;
        private final AtomicInteger sourceReads = new AtomicInteger();
        private final AtomicInteger sourceWrites = new AtomicInteger();

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        @Cacheable(cacheNames = "productNames", key = "#p0",
                   unless = "#result == null")
        public String getName(long productId) {
            sourceReads.incrementAndGet();
            return repository.findName(productId);
        }

        @CachePut(cacheNames = "productNames", key = "#p0",
                  unless = "#result == null")
        public String rename(long productId, String newName) {
            if ("INVALID".equals(newName)) {
                throw new IllegalArgumentException("invalid product name");
            }
            sourceWrites.incrementAndGet();
            return repository.saveName(productId, newName);
        }

        public int sourceReads() {
            return sourceReads.get();
        }

        public int sourceWrites() {
            return sourceWrites.get();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            ProductService service = context.getBean(ProductService.class);

            System.out.println("Read #1: " + service.getName(42L));
            System.out.println("Read #2: " + service.getName(42L));
            System.out.println("Source reads: " + service.sourceReads());

            System.out.println("Rename #1: " +
                    service.rename(42L, "Notebook"));
            System.out.println("Read #3: " + service.getName(42L));
            System.out.println("Source reads: " + service.sourceReads());

            System.out.println("Rename #2: " +
                    service.rename(42L, "Guide"));
            System.out.println("Source writes: " + service.sourceWrites());
            System.out.println("Read #4: " + service.getName(42L));

            try {
                service.rename(42L, "INVALID");
            } catch (IllegalArgumentException ex) {
                System.out.println("Failure: " + ex.getMessage());
            }

            System.out.println("Read after failure: " +
                    service.getName(42L));
            System.out.println("Final source reads: " + service.sourceReads());
            System.out.println("Final source writes: " + service.sourceWrites());
        }
    }
}
~~~

**Why does it run?** `@EnableCaching` turns on Spring cache interception; `ProductService` is created as a Spring bean, and public methods are called through the bean retrieved from `ApplicationContext`. `spring-context` pulls in the required Spring dependencies for the cache abstraction and proxies in this setup. To make the example easy to verify, the source is simulated with a `ConcurrentHashMap`; this is not a production database update method.

### 5.4. How to run

From the directory containing `pom.xml`, with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheableVsCachePutDemo
~~~

The lines **printed by the program** will be:

~~~text
Read #1: Book
Read #2: Book
Source reads: 1
Rename #1: Notebook
Read #3: Notebook
Source reads: 1
Rename #2: Guide
Source writes: 2
Read #4: Guide
Failure: invalid product name
Read after failure: Guide
Final source reads: 1
Final source writes: 2
~~~

### 5.5. Step-by-step explanation

**First two reads:** the first `getName(42L)` is a cache miss, runs the repository, and writes "Book" into `productNames[42L]`. The second call is a hit, so Spring returns "Book" from the cache; the source read counter remains 1.

**First rename:** `rename(42L, "Notebook")` actually runs, the repository updates the name and returns "Notebook". `@CachePut` writes "Notebook" to **the same key 42L** in `productNames`, replacing the previous content.

**Third read:** `getName(42L)` receives "Notebook" from the cache; the source read count does not increase. This only holds because both annotations use the exact **same cache region name and same key**.

**Second rename:** even though key 42L is already cached and the previous read was a cache hit, `rename(42L, "Guide")` **still executes**. The source write counter becomes 2 and the cache is updated to "Guide".

**Failed operation:** `rename(42L, "INVALID")` throws an exception before modifying the repository. There is no new successful result for `@CachePut` to store; the cache still holds "Guide". The `sourceWrites` counter does not increment because the validation branch prevented the write operation.

**Limitation of the example:** if a database write has already executed and **then an exception is thrown**, Spring does not automatically roll back side effects or the entire transaction for you. You need separate transaction and recovery design. A cache provider can also throw an error after business logic finishes; `@CachePut` is not an atomic transaction between cache and database.

## 6. Why must cacheNames and key match between read and update?

In the demo, the two methods have different signatures:

~~~java
getName(long productId)
rename(long productId, String newName)
~~~

If you let Spring use default keys:

- `getName(42L)` has one parameter → key is `42L`.
- `rename(42L, "Notebook")` has two parameters → key is `SimpleKey(42L, "Notebook")`.

Then `@CachePut` will write to **a different entry**. The old entry under key `42L` can still hold "Book", causing `getName(42L)` to keep receiving stale data.

Therefore, the example uses the same `key = "#p0"`: both select the first parameter, `productId`. At the same time, both use `cacheNames = "productNames"`.

**Not only must the key match; the cache name must match as well.** The pair `(cacheName, key)` identifies the exact entry to update.

For multi-tenant data, keying solely on `productId` may not be enough: if the result depends on `tenantId`, `locale`, `currency`, or authorization policy, every factor affecting the value must be considered in the key, namespace, and access control. In particular, caching does not replace per-request authorization.

If multiple methods share a common key rule, consider a Spring-managed `KeyGenerator` or `@CacheConfig` to avoid copy-pasting key expressions.

## 7. When to choose @Cacheable, @CachePut, or @CacheEvict?

| Scenario | Suggestion |
| --- | --- |
| `findById(id)` read-only, reusable result | `@Cacheable` |
| `getCategories(locale)` called repeatedly, rarely changing data | `@Cacheable` with appropriate TTL |
| `updateProduct(id, input)` must always write DB and return **full new Product** | `@CachePut` if the result matches the read path's cached value |
| `renameProduct(id, name)` returns `void` or `boolean` | `@CacheEvict` is usually safer than putting an incompatible value |
| Deleting a product and removing the stale read entry | `@CacheEvict` |
| Updating a product affects lists, stats, or filters | Must evict or update **dependent caches** by design |
| Charging payment, sending email, creating orders with mandatory side effects | Do not use `@Cacheable` to skip the operation; consider transactions and business idempotency |
| Expensive computation with non-repeating inputs | Consider not caching or caching only a popular subset |

A single update can affect multiple cache regions: for example, changing a product's price affects `productById`, `productList`, and `priceSummary`. `@CachePut` only puts **one result** into the declared regions/keys; it does not automatically discover every dependent query. Other regions need their own invalidation or update policy.

### Example pairing Cacheable with CacheEvict

This is **illustrative code** in a Spring service with a repository and `ProductDto`:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public ProductDto getProduct(long id) {
    return repository.findDtoById(id);
}

@CacheEvict(cacheNames = "products", key = "#p0")
public void updateProduct(long id, ProductUpdateRequest request) {
    repository.update(id, request);
}
~~~

When `updateProduct` completes successfully, Spring removes the entry by key by default. The next read will produce a fresh value. If strict synchronization after transaction commit is needed, you must consider eviction timing relative to the transaction, not just look at the annotations.

## 8. Write conditions: condition, unless, null, and exceptions

Both annotations can use `condition` and `unless`, yet their **implications for method execution still differ**.

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 > 0",
    unless = "#result == null"
)
public Product findProduct(long id) {
    return repository.find(id);
}

@CachePut(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 > 0",
    unless = "#result == null"
)
public Product updateProduct(long id, ProductUpdateRequest request) {
    return repository.updateAndReturn(id, request);
}
~~~

These are illustrative snippets, not a complete program.

- **`condition`:** determines whether caching behavior applies to the call based on the expression. With `@Cacheable`, if caching is not applied, the method still runs; with `@CachePut`, the method always runs regardless of whether a put happens.
- **`unless`:** checked after a result is obtained to veto storing, such as refusing to store `null`. `#result` is used in `unless`; on a cache put it can also be used to compute the key when needed.
- **Returning `null`:** without `unless`, whether `null` is stored depends on the configuration/cache provider. Do not assume `null` is always treated as a cache miss later.
- **Throwing an exception:** when the target method does not return normally, the cache put operation for that successful result is not performed. However, if the method catches the error internally and returns an error-containing DTO, the DTO may still be cached if conditions allow.

### Difference when an old result is already cached

`@Cacheable` for a key that **already holds a value** typically does not run the method; hence `unless` is not a way to force Spring to re-query the source on a cache hit. By contrast, `@CachePut` always runs the method body and only uses `unless` to decide **whether to write the newly produced result** to the cache. If `unless` vetoes the store, the old entry may remain; Spring does not automatically delete it.

### Notes on Optional and asynchronous execution

Spring has built-in handling for `Optional<T>`: a present value is stored as the inner value, while `Optional.empty()` corresponds to `null` if the provider allows it. In `unless` expressions, `#result` represents the unwrapped business value. Starting in Spring Framework 6.1, support for `CompletableFuture` and reactive return types lets `@Cacheable`/`@CachePut` process results when values complete; do not equate the moment the wrapper is returned with the moment the cache holds the final result.

## 9. What Spring proxies and transactions do not guarantee automatically

### 9.1. Self-invocation

In **default proxy mode**, caching annotations apply only if the call goes through the Spring proxy. An internal call like `this.rename(id, name)` from another method in the same bean bypasses the interceptor, so `@CachePut` may **not update the cache** even though the database changed.

Similarly, `this.getName(id)` can bypass `@Cacheable`. Place entry points at appropriate bean boundaries or use another interception mechanism when genuinely needed; test using a bean retrieved from `ApplicationContext`.

### 9.2. Transaction commit

`@CachePut` normally considers writing to the cache after the target method returns successfully. This **does not automatically prove the database transaction has committed**. The ordering of cache advice/transaction advice and transaction-aware caches determine the actual timing. If the cache is updated before commit and the transaction then rolls back, cached data may not reflect source state.

For critical business updates, design after-commit behavior, transaction-aware caching, or an appropriate evict/reload policy; explicitly test commit, rollback, and concurrent read cases. Cache and database do not form a distributed atomic transaction by default.

### 9.3. Multiple instances and freshness

`ConcurrentMapCacheManager` in the example stores data only in process RAM. If the application runs multiple instances with separate local caches, a `@CachePut` on instance A **does not automatically update** instance B's cache. When all nodes must see the same updated data, choose a shared cache (e.g., Redis) or an invalidation event mechanism with an appropriate consistency contract.

`@CachePut` also does not specify TTL, entry limits, or how long data lives; those belong to the cache provider.

### 9.4. Cache provider errors

After the method succeeds in writing to the database, a `Cache.put` error may occur. Depending on the `CacheErrorHandler` configuration, the cache error may propagate to the caller or be handled separately. Therefore, do not rely on `@CachePut` as proof that both the cache and source operations succeeded atomically.

## 10. Why should you not put @Cacheable and @CachePut on the same method?

One annotation tries to **skip execution on a cache hit**; the other requires **always executing to produce a new value**. Mixing both on the same method makes the execution semantics hard to predict and prone to surprising outcomes.

**Pattern to avoid:**

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
@CachePut(cacheNames = "products", key = "#p0")
public Product updateAndRead(long id) {
    return repository.updateAndRead(id);
}
~~~

This is a **counter-example**, not a recommendation. Spring documentation strongly warns against combining both on the same method; only certain special cases with mutually exclusive conditions are considered, and those conditions must not depend on `#result` when Spring needs to evaluate upfront.

**Clearer approach:** `@Cacheable` on read methods; `@CachePut` on update methods returning the right DTO; or `@CacheEvict` if you need to clear the cache so the next read reloads it. Each method has a transparent execution contract.

## 11. Common pitfalls and fixes

1. **Using `@Cacheable` on a write method.** On a cache hit, the method may be skipped and data will not be updated. Separate read and write paths; use `@CachePut` or `@CacheEvict` on the write path depending on the return value.
2. **Using `@CachePut` to speed up a read method.** The method still runs every time, saving no source queries. Use `@Cacheable` if the goal is reusing results.
3. **Leaving default keys on two methods with different parameter counts.** `@Cacheable` and `@CachePut` produce two different keys, leading to staleness. Declare consistent keys or a shared `KeyGenerator`.
4. **Same key but different cache name.** Putting into one region does not update an entry in another region. Specify the right `cacheNames` and dependent regions.
5. **CachePut returning `void`/boolean into a cache meant for DTOs.** The stored value does not match the type expected by read methods. Use `@CacheEvict` or return a complete DTO.
6. **Forgetting `unless` on invalid results.** A null/error DTO may be cached depending on the provider. Define an explicit negative caching policy.
7. **Assuming `condition=false` skips a `@CachePut` method.** The condition only affects caching; the method body is still called.
8. **Calling from the same bean via `this`.** Default proxy mode does not intercept self-invocation. Split beans or call boundaries appropriately.
9. **Assuming cache updates happen after commit.** Design cache put/evict timing around the actual transaction and test rollbacks.
10. **Forgetting multiple instances or dependent caches.** A single put does not update every local copy or all other query caches.
11. **Confusing business errors with Java exceptions.** If a method catches an exception and returns an error DTO, Spring may treat that as a normal return value to cache unless vetoed.
12. **Measuring only hit ratio while ignoring correctness.** A high cache hit rate is meaningless if users receive stale data or cross-tenant leaks. Test results after updates.

## 12. Self-check questions

**1.** Key 42 is already in the cache. When calling a `@Cacheable` method with that key, does Spring necessarily run the method body?  
**Answer:** No. On a valid cache hit, Spring usually returns the cached value and skips the method body.

**2.** Key 42 is already in the cache. When calling a `@CachePut` method with that key, is the method skipped?  
**Answer:** No. The method still runs; the result can replace the old entry if conditions allow.

**3.** Why do `@Cacheable get(long id)` and `@CachePut update(long id, String name)` easily generate different keys when no key is declared?  
**Answer:** Spring defaults to using a single parameter directly as the key, whereas it uses a `SimpleKey` containing both parameters for the update method.

**4.** `updateProduct` returns `boolean`, while the cache stores `ProductDto`. What should you choose?  
**Answer:** Usually choose `@CacheEvict` to remove the entry and re-read the DTO afterward, or change the contract so the update method returns the full DTO matching the cache.

**5.** Does `@CachePut(unless = "#result == null")` when a method returns null mean the method did not run?  
**Answer:** No. The method ran and returned null; `unless` only vetoed the cache put.

**6.** Why doesn't `@CachePut` automatically guarantee consistency with the database in a transaction that rolls back?  
**Answer:** Cache advice is not atomic with the database by default; commit order and transaction-aware policies must be considered.

**7.** Should you place both `@Cacheable` and `@CachePut` on a single method to “get both benefits”?  
**Answer:** Generally no. The two annotations have conflicting execution goals; separate read and update methods instead.

**8.** Does a successful `@CachePut` on instance A automatically update instance B's local cache?  
**Answer:** No. You need a shared cache or a multi-node synchronization/invalidation mechanism.

## References

- Spring Framework Reference — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Reference — Understanding the Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache/strategies.html
- Spring Framework Reference — Configuring the Cache Storage: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework Javadoc — CachePut: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CachePut.html
- Spring Framework Javadoc — Cacheable: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Cacheable.html
