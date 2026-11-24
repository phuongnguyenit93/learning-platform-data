# @CacheEvict: Cache eviction timing when a method throws an exception

## 1. Why do exceptions change cache eviction outcomes?

In Spring Framework, `@CacheEvict` marks a method capable of **evicting cached data**. An important scenario arises when a method is called to modify or delete data and **throws an exception**: does the old entry in the cache still exist or has it already been removed?

The answer depends primarily on the **`beforeInvocation`** attribute:

- **Default: `beforeInvocation = false`** — Spring performs eviction **after the method completes successfully**. If the method throws an exception outward, the post-invocation eviction operation **does not occur**.
- **`beforeInvocation = true`** — Spring performs eviction **before invoking the method body**. If the method subsequently throws an exception, the entry has already been requested for removal; Spring does not restore the entry simply because the call failed.

Both approaches have value. Which one to choose depends on whether **the old cached data is still valid when the business operation fails**, rather than merely wanting to "always evict" or "only evict on success".

> The scope of the guarantee above is an invocation **handled by the Spring caching interceptor**, satisfying `condition`, resolving the cache/key, and with the corresponding cache operation able to execute. If the call bypasses the Spring proxy or the cache provider reports an error, the observed behavior can differ.

## 2. Behavior table to memorize

Suppose the `products` cache already holds key `7` with value `Product(7, "Old")`. Method `rename(7, "New")` has `@CacheEvict` with the same key.

| Configuration | Method termination | Eviction request timing | Old entry after invocation* |
|---|---|---|---|
| `beforeInvocation=false` (default) | Returns normally | After method completes | Removed |
| `beforeInvocation=false` | Throws exception outward | **Does not perform post-invocation eviction** | Still present |
| `beforeInvocation=true` | Returns normally | Before running method body | Already removed |
| `beforeInvocation=true` | Throws exception outward | Before running method body | Already removed |

\* The table assumes no other request re-populates the key, `condition` allows eviction, the delete operation succeeds, no transaction-aware cache defers changes, and the cache is unaffected by other mechanisms.

An easily confused point: **`beforeInvocation=false` does not mean waiting until the database transaction commits successfully in every configuration**. It describes the ordering relative to the invocation observed by Spring caching advice. Advice ordering with `@Transactional` and `CacheManager` behavior can affect physical removal timing.

## 3. Execution flow with the default value

Annotation:

~~~java
@CacheEvict(cacheNames = "products", key = "#p0")
public void rename(long id, String newName) {
    repository.rename(id, newName);
}
~~~

This is **illustrative code for Spring integration**, requiring a service bean, repository, cache manager, and appropriate `@EnableCaching`. `#p0` points to the first parameter (`id`); this syntax does not require preserving Java parameter names via `-parameters`.

Flow when the repository succeeds:

~~~text
Client → Spring proxy
       → invoke rename(7, "New")
       → repository.rename(...) succeeds
       → method returns normally
       → @CacheEvict locates products[7] and requests eviction
       → caller receives success result
~~~

Flow when the repository throws an exception:

~~~text
Client → Spring proxy
       → invoke rename(7, "New")
       → repository.rename(...) throws exception
       → exception propagates back out to proxy/caller
       → DOES NOT run post-invocation @CacheEvict operation
       → products[7] may still contain old version
~~~

For a method that only **modifies data in an atomic transaction**, the default value usually makes sense: if the update truly fails and source data remains unchanged, the old cached copy can still be accurate. Not evicting the cache avoids an unnecessary database re-read.

However, this is **not a guarantee that cached data is always correct** after an error. An exception can occur **after some side effects have already completed**, or the transaction/external source may not roll back synchronously. In that case, the method throws an error while source data has partially changed; keeping the old entry can make it stale.

## 4. Execution flow when beforeInvocation=true

Annotation:

~~~java
@CacheEvict(
    cacheNames = "products",
    key = "#p0",
    beforeInvocation = true
)
public void synchronizeProduct(long id) {
    externalProductGateway.synchronize(id);
}
~~~

This is also **integration code**, where `externalProductGateway` is a business dependency. This example fits when a sync operation may alter external source data and then fail at a later step, making the prior cached value no longer trustworthy.

Flow:

~~~text
Client → Spring proxy
       → resolve key 7 and check condition if any
       → request eviction of products[7]
       → invoke synchronizeProduct(7)
       → execute sync operation
       → method succeeds OR throws exception
       → does not "undo" eviction because method failed
~~~

If synchronization fails, the next read will experience a cache miss and query the source. This is the practical reason to use `beforeInvocation=true` when the requirement is **never continue serving a cached copy that is at risk of being wrong**, even if the task fails.

**In return**, early eviction has a side effect: if the task fails completely before changing the source, you have discarded a cached copy that was still valid. This can increase unnecessary queries/latency. In addition, a concurrent read request can cache-miss right after eviction, fetch the old data from the database **while the update task has not finished**, and write the old data back into the cache. `beforeInvocation=true` is therefore **not an absolute consistency solution for race conditions**.

## 5. Spring illustration: two strategies for two different operations

The service example below separates a data-editing method expected to succeed atomically from an external synchronization method that may leave partial side effects.

~~~java
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final ProductRepository repository;
    private final ExternalProductGateway gateway;

    public ProductService(ProductRepository repository,
                          ExternalProductGateway gateway) {
        this.repository = repository;
        this.gateway = gateway;
    }

    @Cacheable(cacheNames = "products", key = "#p0")
    public Product getProduct(long id) {
        return repository.findById(id);
    }

    // Strategy 1: only evict if the method does not throw an exception.
    @CacheEvict(cacheNames = "products", key = "#p0")
    public void rename(long id, String name) {
        repository.rename(id, name);
    }

    // Strategy 2: evict even before invoking the sync operation.
    @CacheEvict(cacheNames = "products",
                key = "#p0",
                beforeInvocation = true)
    public void syncFromExternal(long id) {
        gateway.synchronize(id);
    }
}
~~~

The types `Product`, `ProductRepository`, and `ExternalProductGateway` are **hypothetical dependencies**; this snippet illustrates the Spring mechanism, not a standalone Java file. In a real project, install dependencies, define the corresponding beans, and enable caching support:

~~~java
@Configuration
@EnableCaching
public class CachingConfiguration {
    // Configure an appropriate CacheManager/provider here.
}
~~~

You must import `org.springframework.context.annotation.Configuration` and `org.springframework.cache.annotation.EnableCaching` in the actual configuration class. For both methods, note that the cache name `products` and key `#p0` must match how `getProduct(id)` stores its results.

If the service is multi-tenant, `id` alone may not suffice as a key. For example, if two tenants both use ID 7, the cache must be separated by tenant or use keys containing the tenant. Evicting the wrong key leaves the stale entry alive regardless of which `beforeInvocation` setting you choose.

## 6. Standalone runnable Java 17 example: proving the difference in four scenarios

To clearly see the ordering without depending on a Spring setup, the program below **simulates** the interceptor with a `HashMap`. It does not run real annotations, nor does it simulate transactions or concurrent cache re-population.

Create the file **`CacheEvictTimingDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class CacheEvictTimingDemo {
    private static void update(boolean fail) {
        System.out.println("method: start");
        if (fail) {
            throw new IllegalStateException("update failed");
        }
        System.out.println("method: success");
    }

    private static void call(Map<Long, String> cache, boolean beforeInvocation, boolean fail) {
        long id = 7L;
        if (beforeInvocation) {
            cache.remove(id);
            System.out.println("evict: before");
        }
        try {
            update(fail);
            if (!beforeInvocation) {
                cache.remove(id);
                System.out.println("evict: after");
            }
        } catch (IllegalStateException exception) {
            System.out.println("caught: " + exception.getMessage());
        }
        System.out.println("cache[7]: " + cache.get(id));
    }

    private static void scenario(boolean beforeInvocation, boolean fail) {
        Map<Long, String> cache = new HashMap<>();
        cache.put(7L, "old");
        System.out.println("case: before=" + beforeInvocation + ", fail=" + fail);
        call(cache, beforeInvocation, fail);
    }

    public static void main(String[] args) {
        scenario(false, true);
        scenario(true, true);
        scenario(false, false);
        scenario(true, false);
    }
}
~~~

Compile with Java 17+:

~~~bash
javac --release 17 CacheEvictTimingDemo.java
java CacheEvictTimingDemo
~~~

**Exact stdout:**

~~~text
case: before=false, fail=true
method: start
caught: update failed
cache[7]: old
case: before=true, fail=true
evict: before
method: start
caught: update failed
cache[7]: null
case: before=false, fail=false
method: start
method: success
evict: after
cache[7]: null
case: before=true, fail=false
evict: before
method: start
method: success
cache[7]: null
~~~

Interpretation:

1. Default + exception: the `remove` call is **after** `update(fail)` so it does not run; entry `"old"` remains in the map.
2. Evict before + exception: `remove` already ran before `update` threw an error; reading the key again returns `null`.
3. Default + success: the method completes and then `remove` runs, removing the entry.
4. Evict before + success: `remove` runs first and the method is still invoked.

In the Java simulation, the exception is caught outside the `update` call so printing results can continue easily. For real Spring annotations, what matters is **whether the exception from the method propagates out to the caching interceptor**. The next section clarifies caught exceptions inside the method.

## 7. Exceptions caught inside the method: does Spring see the failure?

A common mistake is thinking that "because an error happened", `beforeInvocation=false` definitely will not evict.

~~~java
@CacheEvict(cacheNames = "products", key = "#p0")
public boolean tryRename(long id, String newName) {
    try {
        repository.rename(id, newName);
        return true;
    } catch (RuntimeException ex) {
        logger.warn("Rename failed", ex);
        return false;
    }
}
~~~

This is **illustrative integration code**, with `logger` and `repository` supplied by the application. When the repository throws an exception but the method **catches it and returns `false` normally**, from the perspective of Spring caching advice, the invocation **finished without throwing an exception**. Therefore, post-invocation eviction can still happen even though the business logic returned a failure status.

Comparison:

| Behavior inside the method body | Observed by Spring caching advice | Default post-invocation eviction |
|---|---|---|
| `repository.rename(...)` succeeds, method returns | Success | Yes |
| `repository.rename(...)` throws exception, uncaught | Exception propagates out | No |
| Catches exception and `return false` | Method returns normally | Yes |
| Catches exception and re-`throw`s | Exception propagates out | No |
| Catches error and returns failure object | Method returns normally | Yes |

This holds for **both checked and unchecked exceptions** if the exception actually escapes the invocation; the Spring cache interceptor's criterion is *whether the invocation finished normally*, not which exception class the JVM threw.

If a business API uses a `boolean` return value or a status object to indicate success, design eviction around the **business outcome**, rather than relying blindly on the assumption "returning false won't evict". The `@CacheEvict` annotation has `condition` for making decisions based on supported context; it **does not have an `unless` attribute** like `@Cacheable`/`@CachePut`. When post-checking a complex result or handling specific error branches is required, use programmatic cache management, split services, or publish post-commit events.

## 8. How are condition, key, allEntries, and #result related?

### 8.1. `beforeInvocation=true` does not mean "every call gets evicted"

~~~java
@CacheEvict(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 > 0",
    beforeInvocation = true
)
public void synchronize(long id) {
    gateway.synchronize(id);
}
~~~

If `id <= 0`, `condition` is false: **no eviction**, even though `beforeInvocation` equals true. That is an intentional way to add conditions. Remember that `condition` controls the **cache operation**, it does not stop the method logic from running.

When the condition is true and metadata/cache provider work normally, eviction occurs prior to invocation and thus does not depend on whether the call later throws an exception or returns.

### 8.2. Choosing keys from arguments or results

- `#p0`, `#a0`, and `#root.args[0]` reference the first argument and can always be used in both modes.
- `#id` references the Java parameter name if Spring can discover it; requires a build preserving names, such as `javac -parameters`.
- `#result` can only be used in Spring-supported **post-invocation eviction contexts** (`beforeInvocation=false`). Before the method runs there is no result yet, so do not pick the pre-eviction key with `#result.id`.

Example of evicting the cache by an ID provided by the return value:

~~~java
@CacheEvict(cacheNames = "products",
            key = "#result.id",
            beforeInvocation = false)
public Product updateAndReturn(long id, String name) {
    return repository.updateAndReturn(id, name);
}
~~~

This code assumes the method returns a non-null `Product` and SpEL can access `id`. If the method throws an exception, by default there is no post-invocation eviction to evaluate the key. If the result can be null or another wrapper type, the expression must be handled and tested appropriately.

### 8.3. Clearing the entire cache with `allEntries=true`

~~~java
@CacheEvict(
    cacheNames = "productCatalog",
    allEntries = true,
    beforeInvocation = true
)
public void refreshCatalog() {
    catalogGateway.refresh();
}
~~~

Here, the goal is removing **every entry** in the `productCatalog` cache before refreshing. When refresh throws an exception, the clear operation has already been requested. However, if other requests access it during the refresh, they can still load old data back in.

**Do not combine `allEntries=true` with a `key` expression**: clearing the entire region has no single-key meaning. Also carefully weigh the impact of clearing an entire cache when only one record changes, especially in high-traffic systems.

## 9. Transactions: "method succeeded" and "commit succeeded" are different

Choosing `beforeInvocation` is an important decision, but it **does not automatically guarantee cache synchronization with transactions**.

Consider the flow:

~~~text
@Transactional update
    ├─ modify data inside database transaction
    ├─ method may return normally
    ├─ transaction interceptor performs commit or rollback
    └─ caching interceptor evicts per actual advice order
~~~

The actual order between caching advice and transaction advice depends on configuration and interceptor ordering. Furthermore, with a `CacheManager` supporting transaction awareness or an appropriate wrapper, cache changes can be deferred. Therefore:

- `beforeInvocation=false` only guarantees eviction is scheduled/executed **after the method called by the cache interceptor completes normally**, per Spring Cache semantics. It is **not a general promise** that every eviction waited for database commit.
- If the transaction later rolls back yet the cache was already evicted, cached data may simply be reloaded even though the source did not change. Usually this only costs performance; however, correctness and concurrency still need evaluation.
- If the database partially changed and then an external system error caused the method to throw an exception, `beforeInvocation=false` can retain an old entry that is no longer accurate.
- For strict requirements to "only invalidate after a successful commit", design an explicit **after-commit** mechanism, transaction synchronization/events, or an appropriate transaction-aware cache manager; test ordering and rollback behavior in the real project.

Specifically, using `beforeInvocation=true` on a method **about to start a transaction** can create a cache gap before new data commits. Other readers reading during this gap may reload the old version. When high consistency is needed, versioning, per-key locking, post-commit invalidation, events/outbox, or other transaction/cache coordination strategies may fit better.

## 10. Cases where "evict before/after" does not behave as expected

### Proxy and self-invocation

In default Spring proxy mode, annotations only take effect when calls **go through the Spring proxy**. For example:

~~~java
@Service
class ProductService {
    public void caller(long id) {
        evictProduct(id); // same-instance call: may bypass proxy
    }

    @CacheEvict(cacheNames = "products",
                key = "#p0",
                beforeInvocation = true)
    public void evictProduct(long id) {
        // A business operation.
    }
}
~~~

`caller` calls `evictProduct` directly on the same object; bypassing proxy advice does not mean the wrong `beforeInvocation` was chosen. Call through a Spring-intercepted bean or redesign method boundaries. AspectJ mode has different characteristics; the above applies to **the common proxy mode**.

### Cache provider encounters an error

- If pre-eviction throws an exception from key resolution/the cache provider **before entering the method**, the business call may not have executed yet.
- If the method already succeeded yet post-eviction fails, the caller may observe a cache error after source data has already changed; do not assume the transaction or database rolled back.
- Providers or distributed caches have differing replication, transaction-awareness, and eventual consistency mechanisms. `@CacheEvict` describes the request sent to the cache abstraction; test when the entry actually becomes unavailable.

### Multiple caches, multiple services, HTTP caches

`@CacheEvict(cacheNames="products")` only affects the cache selected by the cache manager/resolver; it does not automatically clear browser HTTP caches, CDNs, in-memory caches of other JVMs, or entries in other regions. Even when pre-eviction succeeds, another caller can reload the old version during the update.

### Asynchronous methods

In Spring Framework 6.1+, cache annotations have special support for `CompletableFuture` and supported reactive return types. With post-invocation eviction, processing timing can depend on asynchronous completion rather than simply when the method returns a handle. Verify specifically how **exceptional completion** is handled for your version and cache provider; do not mechanically apply synchronous example ordering to reactive pipelines.

## 11. Which configuration to choose by business objective?

| Scenario | Usually suitable configuration | Rationale and limitations |
|---|---|---|
| Editing an entity in a transaction, errors guarantee full rollback | Default `beforeInvocation=false` | If update fails and source remains intact, old cache stays usable; still check commit timing |
| External sync outside DB may create partial side effects before failing | Consider `beforeInvocation=true` or explicit invalidation | Avoids keeping a potentially wrong stale copy; still must handle race/refill |
| Deleting a resource, only want to evict when source deletion succeeds | Default `false` | Minimizes cache misses from failed deletions |
| Want cache evicted even if method fails because cache is no longer reliable | `true` when policy permits | Eviction happens upfront; causes misses even if method didn't alter source |
| Method swallows exception and returns failure status | Redesign result/error handling and cache logic | Spring sees a normal return so post-invocation eviction can still run |
| Need invalidation right at database commit | Explicit transactional after-commit invalidation | `beforeInvocation=false` alone does not guarantee exact commit timing |
| Only want to evict one product, not the whole catalog | Exact `key`, `allEntries=false` | Avoids unnecessary impact on other entries |

**Decision question:** "If this operation fails, is the old data in the cache still trustworthy?" If **still accurate** and there are no side effects, evicting after the method succeeds is usually reasonable. If **not guaranteed accurate** even on failure, an early/post-checked invalidation plan aligned with business logic is needed, combined with a consistency strategy to prevent reloading stale copies.

## 12. Testing @CacheEvict when exceptions occur

To verify **real Spring behavior** (unlike the simulated Java example), use a test that loads a Spring application context, enables caching, retrieves the service bean from the context, and uses an inspectable cache manager.

Suggested test sequence:

1. Populate `products[7] = "old"`.
2. With `beforeInvocation=false`, make the repository throw `IllegalStateException` out of the method. Verify the caller receives the error while `products[7]` remains.
3. Reset cache to `"old"`. With `beforeInvocation=true`, make the method throw an error. Verify the caller still receives the error yet the entry was evicted.
4. Run both methods successfully, verifying the entry is evicted after/before respectively; use a spy/mock cache if you want to verify **ordering**.
5. Test the case where the method **catches the exception and returns false**: by default it still evicts because the invocation returns normally.
6. Add `condition=false`, wrong-key cases, `allEntries`, and self-invocation to distinguish configuration bugs from timing.
7. If using `@Transactional`, test both commit and rollback; if using multiple instances or async, test the actual provider and concurrency.

For example, assertions that only check whether the key is gone after the method finishes are **not sufficient to prove before/after** when both succeed. To prove timing, observe inside the method or record invocation/`Cache.evict` order via a spy. For exceptions, the difference in whether the key remains or is missing after the call is the clearest evidence under controlled test conditions.

## 13. Common pitfalls

- **Assuming `@CacheEvict` always evicts, even if the method throws an exception:** by default **no**, because `beforeInvocation=false`.
- **Assuming `beforeInvocation=true` waits until after the method fails to evict:** in reality eviction already occurred **before the method started**.
- **Treating a `false` return value as an exception:** Spring still treats the invocation as successful if the method returns normally.
- **Confusing `condition` with skipping the method:** it only controls eviction, not whether the method runs.
- **Assuming `#result` can be used in pre-eviction:** before the method runs there is no result yet; use parameters or a stable key from the request.
- **Forgetting key/cache name:** successful eviction on a key different from the read key will not remove stale data.
- **Using `allEntries=true` without weighing consequences:** a single task failure can wipe the whole cache with pre-eviction.
- **Assuming cache and transaction synchronize automatically:** advice order, commit, rollback, and provider deferral must be verified.
- **Using pre-eviction as the sole solution for races:** concurrent reads can reload the old version between eviction and update.
- **Self-calling a method in the same bean:** in proxy mode, the annotation may not be applied.
- **Ignoring cache provider errors:** exceptions during eviction and exceptions from business logic are **two separate error sources**, with different consequences and timing.

## 14. Self-check questions

**Question 1.** `@CacheEvict(cacheNames="products", key="#p0")` is on `void rename(long id)`. The method throws `IllegalStateException` outward. If the key already exists, does default eviction run after the method?

**Question 2.** Switching to `beforeInvocation=true`, the method still throws an exception. Can we state the entry was requested to be removed before the method ran, assuming proxy/provider work properly?

**Question 3.** The method catches a database exception and returns `false`. With default eviction and no `condition`, is the cache evicted?

**Question 4.** `beforeInvocation=true` combined with `condition="#p0 > 0"`, called with id `-1`. Is the cache evicted? Is the method skipped?

**Question 5.** Why does `beforeInvocation=false` not necessarily mean "database committed first and then evicted"?

**Question 6.** One request pre-evicted the cache, a second request reads the DB before the update transaction commits and reloads the old version. Does `beforeInvocation=true` prevent this phenomenon?

**Answers & explanations:**

1. **No.** When the method throws an error out to the caching interceptor, post-invocation eviction does not run.
2. **Yes, per the annotation's semantics**, provided the condition and cache operation executed successfully; a subsequent exception does not restore the entry.
3. **Likely yes**: the method returned normally (even though `false`), so the advice can perform post-invocation eviction.
4. `condition` is false so **no eviction occurs**. The method still executes per normal Java logic.
5. Because caching/transaction advice ordering, commit/rollback timing, and transaction-aware cache behavior also play a role.
6. **No.** Early eviction does not block concurrent refills; tighter coordination is needed if consistency demands it.

## 15. References

- Spring Framework Reference — Annotation-based Caching, `@CacheEvict`, and `beforeInvocation`: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Javadoc — `CacheEvict.beforeInvocation`, `condition`, `allEntries`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CacheEvict.html
- Spring Framework Reference — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html

**Takeaway:** With `@CacheEvict`, **by default the cache is evicted only after the method completes without throwing an exception**. `beforeInvocation=true` evicts **beforehand**, so if the method later fails the entry is not automatically restored. Choosing rightly requires considering update atomicity, whether exceptions escape or are caught, transaction commits, key/cache names, and concurrent read–write behavior.