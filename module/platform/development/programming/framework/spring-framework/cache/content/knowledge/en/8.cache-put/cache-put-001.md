# @CachePut: Always Execute the Method and Update the Result in Cache

## 1. What problem does @CachePut solve?

When a Spring application uses a cache to reduce data reads, cached read results can remain in the cache even after the source data has changed. `@CachePut` helps **write a method's new result into the cache**. The key point is that **the called method actually still executes**: Spring does not take the old cached value to skip the method invocation like `@Cacheable` does.

Suppose a product management application has:

- `getProduct(7)` reads the product with ID 7, and can leverage the cache on subsequent reads.
- `renameProduct(7, "New Name")` must execute the data update logic and return the updated product.
- `@CachePut` on `renameProduct` can write the returned product to the **exact key that `getProduct` uses**.
- The next `getProduct(7)` call can retrieve the new product from the cache without reading the database.

Remember the annotation's contract: **execute the method first, then put the return value into the cache when conditions allow**. Its main purpose is *synchronizing/populating a cache value from a computed or saved result*, not avoiding execution of the update method.

## 2. Comparing @CachePut, @Cacheable, and @CacheEvict

| Annotation | When the cache already has an entry with the same key | Action on the cache | Purpose |
|---|---|---|---|
| `@Cacheable` | Can immediately return the cached value, **without calling the method body** | Cache miss: runs the method and may cache the result | Optimize repeated **reads/computations** |
| `@CachePut` | **Still calls the method body** | After getting the result, **writes/replaces** the entry under the key if allowed | Refresh or populate the cache value from a fresh execution |
| `@CacheEvict` | The method is not skipped just because of a cache hit | Deletes a key or the entire cache as configured | Remove stale or no-longer-usable values |

The same dataset can use all three annotations, but **on methods with different responsibilities**:

~~~text
READ:  @Cacheable
client ──► get(id) ──► cache hit ──► return result, may skip database
                   └─► cache miss ─► read database ─► write cache ─► return result

WRITE: @CachePut
client ──► update(id, newValue)
                ├─► always run update logic (even if cache has key id)
                ├─► return the successfully saved record
                └─► put(cacheName, key=id, value=result)

DELETE: @CacheEvict
client ──► delete(id) ─► perform delete at source ─► evict(cacheName, id)
~~~

**“Always runs” has a contextual condition:** this statement describes **a method call handled by the Spring cache interceptor**. If one method calls another method on `this` in default proxy mode, the annotation may not be intercepted; the method body still executes like normal Java, but there will be **no automatic cache operation**.

## 3. Mechanics of a @CachePut call

Suppose the annotation is:

~~~java
@CachePut(cacheNames = "products", key = "#p0")
public Product renameProduct(long id, String newName) {
    return repository.save(new Product(id, newName));
}
~~~

The snippet above is **illustrative Spring integration code**. `Product` and `repository` represent the domain and data persistence layer; bean/cache configuration will be added in a later section.

A call to `renameProduct(7L, "New Version")` is understood in the following steps:

1. The client calls the method **through a Spring bean/proxy**.
2. The logic of `renameProduct` still runs, **without checking the cache to decide whether to skip the method body**.
3. The repository handles saving the data. The method returns the saved `Product`.
4. Upon successful execution and when cache conditions allow, Spring computes the key using SpEL `#p0` = `7L`, selects the `products` cache, and invokes a value-write operation equivalent to `Cache.put(7L, savedProduct)`.
5. The call returns the same result value from the method. If there was previously an old entry at key 7, the entry is replaced with the new value according to the cache provider's semantics.

The example below illustrates the state of the same key:

| Time | Source data | Cache `products[7]` | Result |
|---|---|---|---|
| Initial | `Product(7, "Old")` | None | Not yet read |
| First `getProduct(7)` | `"Old"` | `"Old"` | Cache miss, loads data |
| Second `getProduct(7)` | `"Old"` | `"Old"` | Cache hit |
| `renameProduct(7, "New")` | `"New"` | `"New"` | Executes method and puts new value |
| Next `getProduct(7)` | `"New"` | `"New"` | Can cache hit with the new value |

The annotation does not automatically know which database to update. **All business mutations belong inside the method body**; `@CachePut` only works with the result and the cache according to the declared policy.

## 4. Spring integration example: reading with @Cacheable, updating with @CachePut

The example below uses two different methods but the **same cache name** and **same key generation**. It is an illustrative snippet for a Spring Framework application; to run it, a `ProductRepository` implementation and corresponding dependency/bean configuration are needed.

~~~java
import java.util.Optional;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

record Product(long id, String name) {}

interface ProductRepository {
    Optional<Product> findById(long id);
    Product save(Product product);
}

@Service
class ProductService {
    private final ProductRepository repository;

    ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "products", key = "#p0")
    public Product getProduct(long id) {
        return repository.findById(id).orElseThrow();
    }

    @CachePut(cacheNames = "products", key = "#p0")
    public Product renameProduct(long id, String newName) {
        Product current = repository.findById(id).orElseThrow();
        return repository.save(new Product(current.id(), newName));
    }
}
~~~

With `getProduct(7)`, `#p0` points to the `id` argument. With `renameProduct(7, "New")`, `#p0` is also `id`, even though the update method has an extra `newName` parameter. **Because both keys equal 7 and both cache names are `products`, the write method updates the exact entry that the read method looks up.**

Why must `key = "#p0"` be explicitly specified on the update method? If you omit the `key` attribute:

- `getProduct(long id)` has one parameter, so the default key is usually the `id` value itself.
- `renameProduct(long id, String newName)` has two parameters, so the default key is `SimpleKey(id, newName)`.
- The two keys are **different**. The cache may hold an entry with the composite key while `getProduct(7)` continues reading the old entry under key `7`.

Having the same cache name is **not enough**. You must align **the key, key type, namespace/tenant, and cache provider** across methods interacting with the same entry.

### Enabling caching and configuring the cache manager

An illustrative configuration using Spring's in-memory cache:

~~~java
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
class CacheConfiguration {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }
}
~~~

`@EnableCaching` activates cache annotation support; `CacheManager` manages the cache named `products`. When running Spring Boot, you need the appropriate dependency/cache provider for the project (e.g., Spring cache abstraction via the corresponding starter). `ConcurrentMapCacheManager` is convenient for simple examples, but it stores data in each instance's memory and **has no built-in TTL**. Production systems need to choose a provider (such as Caffeine or Redis) and configure expiration, capacity, serialization, and invalidation strategies appropriately.

### Same key also means same data semantics

The example is only safe if `Product` data for ID 7 has consistent meaning across calls. If multi-tenancy, language, product version, or access permissions affect the result, the key must include sufficient context. You should not use just the ID as the key when two tenants can share ID 7 with different data.

## 5. CachePut writes the **return value**, not the parameter by default

Consider this method:

~~~java
@CachePut(cacheNames = "products", key = "#p0")
public Product renameProduct(long id, String proposedName) {
    return repository.renameAndReturnSaved(id, proposedName);
}
~~~

The database might normalize the name, update a timestamp, or generate a new version. The value placed in the cache is the **`Product` returned by the method**, not automatically `proposedName` or an old entity the caller held.

This is why an update method should generally return **the final persisted state**. If it writes to the database but returns an out-of-sync value, the cache may also receive business-incorrect data.

### When the ID is database-generated: the key can come from the result

Sometimes a creation method does not receive an ID because the database generates the ID upon saving. In that case, `@CachePut` can use `#result` to determine the key after the method returns:

~~~java
@CachePut(cacheNames = "products", key = "#result.id")
public Product createProduct(CreateProductCommand command) {
    return repository.insertAndReturnSaved(command);
}
~~~

This is illustrative integration code; `CreateProductCommand`, `Product`, and `repository` are application types/beans. The example assumes the returned `Product` is non-null and Spring SpEL can read the entity's `id` property. If using a JavaBean, a `getId()` getter is the explicit way. When the ID is `7`, the entry is written under key 7 and can be read by `getProduct(7)`.

**Essential difference:** `@CachePut` can use `#result` in its key expression because the put happens after the result is available. `@Cacheable` must determine the key to **look up the cache before deciding whether to run**; `#result` cannot be used for the key in this way.

## 6. condition and unless: controlling *cache writes*, not *method execution*

`@CachePut` also supports SpEL attributes such as `condition` and `unless`.

~~~java
@CachePut(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 > 0",
    unless = "#result == null"
)
public Product refreshProduct(long id) {
    return repository.findById(id).orElse(null);
}
~~~

- **`condition`:** allows the cache operation only if the expression evaluates to true. With `@CachePut`, the conditional expression is evaluated after the method is invoked according to the nature of the put operation; **it does not turn `@CachePut` into `@Cacheable`**.
- **`unless`:** vetoes writing to the cache when the expression evaluates to true. Here, returning `null` skips the put. Without `unless`, `null` caching behavior depends on how the cache/provider handles nulls and its specific configuration.
- **`key`:** computes the key to write. `#p0` accesses the first argument by index.
- **`#result`:** accesses the return value after the method completes. For supported wrappers such as `Optional<T>`, Spring can use the unwrapped business value according to the cache abstraction's rules.

If `condition` is `false`, Spring does not perform the cache put, but **`refreshProduct` still runs**. If `unless` is `true`, Spring also skips writing to the cache without “undoing” the logic that already ran. Do not use these conditions as a mechanism for transaction control, user authentication, or preventing update execution.

### Parameter syntax in SpEL

| Expression | Meaning | Depends on parameter name metadata |
|---|---|---|
| `#id` | Java parameter named `id` | Yes, when Spring needs to discover the name |
| `#p0` or `#a0` | First parameter | No |
| `#p1` or `#a1` | Second parameter | No |
| `#root.args[0]` | First parameter via root object | No |
| `#result` | Return value after execution, in supported contexts | Does not depend on parameter names |

In Java, compiling with `javac -parameters` may be required for `#id` to work reliably. Examples in this lesson prefer `#p0` to avoid depending on parameter name metadata.

## 7. When the method throws, returns void, returns null, or runs asynchronously

**Throwing an exception:** if the method body throws an error before producing a successful result, Spring has no successful return value to write via `@CachePut`. Still, check carefully what data mutations occurred before the exception: if the update logic is not rolled back while the old cache remains, the application may see stale reads. An exception does not automatically undo all side effects.

**Returning `void`:** `@CachePut` is unsuitable for “writing the newly saved entity” because there is no entity return value. If a method only signals a mutation without being able to return the new entity, consider `@CacheEvict` to delete the entry and reload it on the next read, or design the update API to return the final entity.

**Returning `null`:** the policy for caching null depends on the provider and configuration; some providers store it via a sentinel, while others disallow it. You can use `unless = "#result == null"` if the use case wants to skip caching null results. Avoid setting `key = "#result.id"` if the result can be null without handling this safely.

**Asynchronous/reactive results:** starting in Spring Framework 6.1, cache annotations support adapting `CompletableFuture` and supported reactive return types; `@CachePut` performs the put when the value is produced, according to provider support and capabilities. Do not assume that calling a method returning `Mono<T>` always writes the `Mono` object itself directly into the cache. Mechanics depend on return type, version, and cache configuration, so test against your actual stack.

## 8. Standalone runnable Java 17 example: simulating read and put behavior

This example **simulates the semantics** of `@Cacheable` and `@CachePut` using two `Map`s. It **does not execute a real Spring proxy or real annotations**; the goal is to clearly observe that **update always runs** even when the key is already in the cache, and the update result is written back under the same key.

Create the file **`CachePutDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class CachePutDemo {
    record Product(long id, String name) {}

    private final Map<Long, Product> database = new HashMap<>();
    private final Map<Long, Product> cache = new HashMap<>();
    private int readFromDatabaseCount = 0;
    private int updateCount = 0;

    CachePutDemo() {
        database.put(7L, new Product(7L, "Original"));
    }

    Product findById(long id) {
        Product cached = cache.get(id);
        if (cached != null) {
            System.out.println("READ: cache hit");
            return cached;
        }
        System.out.println("READ: cache miss");
        readFromDatabaseCount++;
        Product result = database.get(id);
        if (result != null) {
            cache.put(id, result);
        }
        return result;
    }

    Product update(long id, String name) {
        updateCount++;
        System.out.println("UPDATE: method executed " + updateCount);
        Product saved = new Product(id, name);
        database.put(id, saved);
        cache.put(id, saved);
        return saved;
    }

    public static void main(String[] args) {
        CachePutDemo demo = new CachePutDemo();
        System.out.println("Name: " + demo.findById(7L).name());
        System.out.println("Name: " + demo.findById(7L).name());

        demo.update(7L, "Version A");
        demo.update(7L, "Version B");
        System.out.println("Name: " + demo.findById(7L).name());

        System.out.println("Database reads: " + demo.readFromDatabaseCount);
        System.out.println("Method updates: " + demo.updateCount);
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 CachePutDemo.java
java CachePutDemo
~~~

Exact stdout output:

~~~text
READ: cache miss
Name: Original
READ: cache hit
Name: Original
UPDATE: method executed 1
UPDATE: method executed 2
READ: cache hit
Name: Version B
Database reads: 1
Method updates: 2
~~~

**Analysis:**

1. The first read has to look up the simulated “database” and populate the cache. The second read retrieves the already available data.
2. Both `update(7, ...)` calls **execute**, printing two messages; the code does not use a cache hit to skip the update.
3. Each update writes the new data to the source and replaces `cache[7]`; the final read is a cache hit but returns **“Version B”**.
4. The counters show the database was read only once, while the update method ran twice.
5. This is a single-threaded simulation; it does not demonstrate transactions, race conditions, HTTP caching, or real database durability.

## 9. When to use @CachePut in real applications?

**Suitable:**

- An entity save/edit method **must run** and return the record after persistence succeeds.
- A refresh method for an important value must recompute every time it is called, while populating the new result so other read APIs benefit.
- An entity creation method returns a new ID; the put key is computed from the result if the system wants to warm the cache immediately after creation.
- An import or sync flow returns a normalized value and you know for certain how to map it to the read cache's key.

**Consider `@CacheEvict` instead:**

- There is no reliable return value to populate the cache, or multiple related records may change without a complete representation available.
- A delete operation leaves no entity to cache.
- An update affects multiple keys/cache views without a complete put strategy for every variant; evicting and reloading can be safer.

**Consider using only `@Cacheable`:**

- The goal is solely to optimize repeated reads or computations, with no need to force re-execution on every call.
- You want to return cached hits instead of re-querying; `@CachePut` will not reduce the number of computations of the annotated method itself.

Placing `@Cacheable` and `@CachePut` **on the same method** usually causes semantic conflict: one annotation can skip the call on a hit, while the other needs to call it to update. Spring advises avoiding this combination, except in very narrow cases with clearly designed and tested mutually exclusive conditions.

## 10. Limitations regarding consistency, transactions, and multiple instances

`@CachePut` updates a copy of a value. It **does not automatically turn the database and cache into an atomic transaction**.

- **Commit ordering:** if an update method uses `@Transactional`, verify when the cache write occurs relative to transaction commit and rollback; interceptor order or a transaction-aware cache can affect behavior. Do not assume the cache only changes after commit just because the method has both annotations.
- **Cache provider failures:** the database save may succeed while the put operation fails; retry strategy, error handling, and reconciliation must be designed for the business domain.
- **Multiple instances:** `ConcurrentMapCacheManager` has a separate map per process. One instance updating an entry does not automatically synchronize other instances' maps. Distributed caching or cross-instance invalidation mechanisms are separate architectural choices.
- **Concurrent reads and writes:** a cache-miss read can query stale data and put late **after** an update operation has already put newer data. Therefore, “having `@CachePut`” does not guarantee linearizable consistency for every read; you may need data versioning, locking, TTL/invalidation, and appropriate concurrency design.
- **TTL/eviction:** `@CachePut` is a write command at the cache abstraction API level. Time-to-live, eviction policies, persistence, and serialization are managed by the provider; the annotation does not define TTL itself.
- **Authorized results:** the same ID is not enough if the result also depends on tenant, role, locale, or other options. Cache names/keys must distinguish genuinely different contexts to prevent data leaks across users.

When data is sensitive to correctness—such as inventory, transaction pricing, or access permissions—define the **acceptable staleness level** and test failure/concurrency scenarios before relying on the cache.

## 11. Common implementation pitfalls and how to check them

| Symptom | Possible cause | How to check/fix |
|---|---|---|
| Update runs, but reads still return the old version | `@CachePut` writes a different key than `@Cacheable`; or uses a different cache/provider | Log/compare cache name, SpEL key, and key type of both methods |
| `@CachePut` is attached, but cache does not change | `@EnableCaching` not enabled, missing `CacheManager`, call bypasses proxy | Check beans, configuration, and actual call path |
| Calling `this.renameProduct(...)` runs, but does not put | Self-invocation bypasses proxy in default mode | Call through an intercepted Spring bean or redesign service boundaries |
| Database updated, but cache gets populated with old value | Method returns object before saving or does not reflect final state | Return the persistence-confirmed entity/result |
| Switching from `#p0` to default key stops updating read cache | Multi-parameter write method produces a `SimpleKey` different from read method | Declare compatible keys aligned with business identity |
| Runtime error on null key or SpEL error | `#result`/`#id` unavailable or null; parameter names not retained in bytecode | Check `-parameters`, use `#p0`, handle null appropriately |
| No speed improvement on the update method | `@CachePut` **always runs** the update logic | Measure cost on the read side; use `@Cacheable` for queries you want to skip |
| Fails in cluster even though local machine works | Per-instance local cache, race conditions, or different provider | Check topology, invalidation, and inspect logs/cache metrics |

### Integration testing checklist

In a Spring test using **beans from the application context**, you can design the following sequence:

1. Initialize the source with `Product(7, "Old")` and a clean `products` cache.
2. Call `getProduct(7)` twice; verify the repository reads once on the first cache miss and hits on the second call.
3. Call `renameProduct(7, "New")`; verify the repository **actually saves** once and the method returns the new version.
4. Call `getProduct(7)` again; verify the result is **“New”** and no unexpected read query occurs.
5. Call `renameProduct(7, "Newer")` again; verify save executes again even though the cache already has the key.
6. Separately test exception/rollback cases, cache provider failures, multiple instances, and concurrency according to business criticality.

Do not test only the method return value: inspect cache entries, repository invocation counts, and proxy/transaction boundaries. Avoid self-invocation in tests if the goal is to prove caching advice is active.

## 12. Self-check questions

**Question 1.** Does `@CachePut(cacheNames="products", key="#p0")` skip the method body when the key already exists and return a cache hit?

**Question 2.** `getProduct(long id)` uses key `#p0`, while `renameProduct(long id, String name)` omits `key`. Is `renameProduct` guaranteed to update the same entry?

**Question 3.** When creating an entity whose ID is assigned by the database, why can `@CachePut(key="#result.id")` be more suitable than an input-based key?

**Question 4.** True or false: `unless="#result == null"` prevents the method from running when a null result is expected.

**Question 5.** Is `@CachePut` on a `void delete(long id)` method a good choice for removing stale cached data?

**Question 6.** In a three-instance application using independent in-memory caches, does one instance calling `@CachePut` automatically update the entry on the other two instances?

**Answers:**

1. **No.** The method still runs; the result may be put afterward.
2. **No.** Default keys for two methods with different parameter counts will differ; keys must be aligned.
3. Because `#result` references the result after the ID has been generated and the method has completed successfully.
4. **False.** `unless` only vetoes the put; the method logic still executes.
5. Usually **no**. Using `@CacheEvict` is more appropriate for removing a key after deleting source data.
6. **No.** Each process owns its own map; synchronizing requires a shared cache or invalidation design.

## 13. References

- Spring Framework Reference — Declarative Annotation-based Caching (`@Cacheable`, `@CachePut`, `@CacheEvict`, SpEL, proxy): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Reference — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework Javadoc — `CachePut` and annotation attributes: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CachePut.html
- Spring Framework Javadoc — `Cache`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html

**Remember:** **`@CachePut` is used when a method must execute and its return value needs to be placed in the cache**. The new result only improves accuracy for later reads when read and write methods share **the same cache, same key, and same data semantics**. Pair it with `@Cacheable` for reads, `@CacheEvict` for deletes, and handle transactions, concurrency, and cache providers explicitly.