# @CachePut: Update Conditions and When the Result Is Available

## Learning Objectives

In Spring Framework Cache Abstraction, **@CachePut** is used to write or replace an entry with **the value the method just returned**. This lesson helps you master: (1) when the method still executes; (2) when **condition** and **unless** are evaluated; (3) when **#result** is available to build a key or veto an update; (4) the effect on an existing entry; and (5) how to test actual behavior without confusing data-source updates with cache updates.

Context: Spring Framework 6.x with annotation caching via Spring AOP proxies. The standalone runnable example uses Java 17, Maven, and ConcurrentMapCacheManager; ordering statements are separated from provider-specific TTL, eviction, or distribution policies.

## 1. Distinguishing the business method from the cache write operation

Consider a command to update a product. The method may modify the data source, return the updated object, and then Spring decides whether to put that object into the cache.

~~~text
Caller invokes bean via Spring proxy
          |
          v
Spring reads @CachePut and evaluates condition (before #result exists)
          |
          v
Business method ALWAYS runs in a normal @CachePut call
          |
          +-- Throws exception --> no successful result to put
          |
          +-- Returns result
                   |
                   v
             If condition allows, evaluate unless
                   |
           +-------+--------+
           |                |
      unless = true    unless = false
       skip cache       compute key (can
       put operation    use #result) and put
           |                |
           +-------+--------+
                   |
                   v
          Return result to caller
~~~

The diagram depicts a **synchronous method returning normally**, where the operation has no special asynchronous handling. Spring Framework 6.1+ also supports CompletableFuture and reactive return types; how completion timing is determined is covered in section 10.

Key points:

- **@CachePut always executes the target method when the call goes through the caching interceptor.** An existing cache hit does not prevent execution as with @Cacheable.
- **condition** only determines whether the operation **is eligible for cache writing** based on pre-invocation context. When false, **the method still runs**, but Spring skips that annotation's put operation.
- **unless** is a condition that **vetoes** the write operation: after obtaining the result, if the expression returns true, **no put occurs**.
- If condition allows and unless does not veto, Spring places **the method result** into the cache under the generated key.
- Skipping a put **does not mean deleting an old entry**. A cache may continue holding stale data under that same key.

This helps you place conditions in the right spot: you can rely on inputs to choose condition; if the condition depends on the created/updated object, use unless.

## 2. Timing table: condition, unless, key, and #result

| @CachePut component | When is it evaluated? | Accesses #result? | Purpose |
| --- | --- | --- | --- |
| **condition** | Before executing the method | **No** | Allow put only if input condition is true |
| **unless** | After method returns a successful result | **Yes** | Veto put based on the result |
| **SpEL key** | When preparing to write cache, after result is available | **Yes** | Choose the identity of the entry to update |
| **keyGenerator** | When Spring needs a key and no SpEL key is chosen | Receives target, method, params; does **not** receive result via signature | Compute key in Java |
| **Method result** | After the method completes | Is itself the data being put | Cache value |

**#result** is a special variable in the caching SpEL context; it is **not** a Java local variable. Spring allows `#result` in **@CachePut key** and **unless** because at that point the method has already produced a return value. For **condition**, no result exists yet to evaluate: using `#result` in condition is a timing design error.

Some SpEL expressions:

~~~java
// Illustrative annotation snippets. Each @CachePut belongs to a separate method.
@CachePut(cacheNames = "products", condition = "#p1")
@CachePut(cacheNames = "products", unless = "#result == null")
@CachePut(cacheNames = "products", key = "#result.id()")
~~~

Here **#p1** is the second argument (index 1), and **#result.id()** calls the return value's accessor using SpEL syntax. The lines above show **three attributes on independent examples**. On a single method, you can combine them in **one annotation** when attributes and keys are consistent.

### Easy-to-confuse true/false rules

- **condition = true:** allows the put workflow to proceed; can still be vetoed by **unless**.
- **condition = false:** skips the put; **does not skip** the method.
- **unless = true:** **does not write to cache**.
- **unless = false:** **writes to cache** if condition allows and no other error occurs.

Thus, **unless is not a second condition with the same polarity**; it is negating and runs after the invocation.

## 3. condition: checked before the method runs

Example of an API that only allows caching public data:

~~~java
@CachePut(cacheNames = "products", key = "#p0",
          condition = "#p2")
public Product save(String productId, ProductData data, boolean cacheAllowed) {
    return repository.save(productId, data);
}
~~~

This is an illustrative snippet depending on application-defined `Product`, `ProductData`, and `repository` classes. Here:

1. **#p2** is the boolean `cacheAllowed` parameter.
2. If **cacheAllowed = true**, Spring proceeds with the put after the method returns successfully.
3. If **cacheAllowed = false**, **repository.save still runs**, source data can still be updated, but @CachePut **does not write the result** to the cache.
4. If the cache already held a matching entry beforehand, that entry **does not vanish automatically** just because condition is false.

Another example, caching only for non-sensitive visibility:

~~~java
@CachePut(cacheNames = "publicProfiles",
          key = "#p0",
          condition = "#p1 == 'PUBLIC'")
public Profile update(String id, String visibility) {
    return updateInStore(id, visibility);
}
~~~

This is illustrative, not standalone runnable code. Expressions comparing inputs can run before calling the method. However, for sensitive data, using condition alone to skip putting is **not enough**: if an entry was previously cached, you need a corresponding invalidation strategy to avoid keeping an old profile.

### Wrong: trying to use #result in condition

~~~java
// WRONG: condition is evaluated before a result exists.
@CachePut(cacheNames = "products",
          condition = "#result.approved()")
public Product save(ProductInput input) { ... }
~~~

This intentionally wrong snippet cannot satisfy the requirement of checking the returned status in the right order. When you need to inspect the **result's** `approved` field, move that logic to **unless**.

## 4. unless: vetoing after the result is available

Suppose a method returns a product record with an `approved` flag. You only want to cache results with `approved = true`:

~~~java
@CachePut(
    cacheNames = "products",
    key = "#result.id()",
    unless = "#result == null || !#result.approved()"
)
public Product save(ProductInput input) {
    return repository.save(input);
}
~~~

This is an illustrative snippet; `Product` provides `id()` and `approved()` methods, such as a Java record. Processing order:

1. Call the **save** method to mutate the data source.
2. If the call succeeds, receive `result`.
3. Evaluate **unless** on `result`. If null or `approved = false`, do not write.
4. If `approved = true`, compute key from `result.id()`, then update the entry with `result`.

Checking **#result == null** first prevents the expression from invoking `approved()` on null. For nullable return types, choose an appropriate policy yourself; if the provider allows caching nulls, whether to cache null also needs deliberate thought.

**Note:** `unless` only vetoes **the current put attempt**. If the cache previously held a product with `approved = true`, and a new update returns `approved = false`, the old `approved = true` entry **may still remain in the cache**. If policy requires that “unapproved data must not appear in the cache,” you must **evict the old entry** after the change, rather than merely skipping the new put.

### Comparing with @Cacheable's unless

Both @CachePut and @Cacheable have `unless` running after a result is obtained, yet:

| Annotation | Before running method | After getting result |
| --- | --- | --- |
| **@Cacheable** | Usually looks up cache and may return immediately on hit | If miss and unless is false, stores result in cache |
| **@CachePut** | Does not use hit to skip method | If condition allows and unless is false, **puts/replaces** with new result |

Do not use @CachePut as a way to speed up read methods. It is typically suited for **data creation/update methods** where every call must genuinely execute.

## 5. key using #result: knowing the key once the result exists

A common case: when creating a new product, the ID is generated **after** writing to the database. Before the call, that ID cannot be known; once the `Product` result is available, the key can be set:

~~~java
@CachePut(cacheNames = "products", key = "#result.id()")
public Product create(ProductRequest request) {
    return repository.insert(request);
}
~~~

This is an illustrative snippet; `ProductRequest` and `repository` must be provided by the application. With a `Product` record having an `id()` accessor, the key expression points to the **final ID** returned by the method.

Example using a normalized code:

~~~java
@CachePut(
    cacheNames = "products",
    key = "#result.normalizedSku()",
    condition = "#p1",
    unless = "#result == null || !#result.visible()"
)
public Product update(String submittedSku, boolean cacheAllowed) {
    return repository.updateAndReturnNormalized(submittedSku);
}
~~~

**condition** checks only `cacheAllowed` from input. **unless** checks `visible` on output. **key** picks `normalizedSku` from output. All three can sit on the same @CachePut because they serve different roles and execute at the appropriate moments.

For a **@Cacheable** read method to find the exact entry @CachePut wrote, both operations must use **the same cache name** and **the same logical key**. For example:
- @CachePut writes using **#result.normalizedSku()**.
- @Cacheable reads using **#p0** if the first parameter is already a normalized SKU.
- If @Cacheable accepts a raw SKU, it must normalize it **equivalently**; otherwise it will miss even though the record was put.

### Do not use #result in @Cacheable(key=...)

@Cacheable needs to compute the key **before looking up the cache**. Therefore, **#result** is not a valid source for choosing a lookup key in @Cacheable. This difference is one reason this lesson separates “when the result is available” per annotation rather than applying one blanket rule.

## 6. Runnable example: Spring Framework + Java 17

The demo directly proves:
- The **save** method always runs even when `condition=false` or `unless=true`.
- `condition=true` and `unless=false` write `result` into the cache under the key taken from **#result.id()**.
- `condition=false` skips the put, yet **does not delete previously cached data**.
- `unless=true` skips the put, yet **the old entry can remain**.
- @Cacheable reading the same cache name/key can hit the entry created by @CachePut.

The example uses `ConcurrentMapCacheManager` in **a single JVM**. It does not simulate transactions or TTL.

Structure:

~~~text
cache-put-timing/
├── pom.xml
└── src/main/java/demo/CachePutTimingDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cache-put-timing</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.13</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/CachePutTimingDemo.java**:

~~~java
package demo;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.Locale;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

public class CachePutTimingDemo {
    public record Item(String id, int amount, boolean approved) {}

    public static class ItemService {
        private final ConcurrentMap<String, Item> database =
            new ConcurrentHashMap<>();
        private final AtomicInteger updates = new AtomicInteger();
        private final AtomicInteger loads = new AtomicInteger();

        @CachePut(
            cacheNames = "items",
            condition = "#p2",
            unless = "!#result.approved()",
            key = "#result.id()"
        )
        public Item save(String submittedId, int amount,
                         boolean allowCachePut) {
            updates.incrementAndGet(); // Method always runs.
            String id = submittedId.trim()
                .toUpperCase(Locale.ROOT);
            Item item = new Item(id, amount, amount >= 0);
            database.put(id, item);
            return item;
        }

        @Cacheable(cacheNames = "items", key = "#p0")
        public Item find(String normalizedId) {
            loads.incrementAndGet(); // Runs only on cache miss.
            return database.get(normalizedId);
        }

        public int updateCalls() { return updates.get(); }
        public int loadCalls() { return loads.get(); }
    }

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("items");
        }

        @Bean
        public ItemService itemService() {
            return new ItemService();
        }
    }

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(Config.class)) {
            ItemService service = context.getBean(ItemService.class);
            Cache cache = context.getBean(CacheManager.class)
                .getCache("items");

            System.out.println("A1=" + service.save("a", 10, true));
            System.out.println("A find=" + service.find("A"));

            System.out.println("B1=" + service.save("b", 20, false));
            System.out.println("B in cache=" + (cache.get("B") != null));
            System.out.println("B find=" + service.find("B"));
            System.out.println("B2=" + service.save("b", 21, false));
            System.out.println("B find again=" + service.find("B"));

            System.out.println("C1=" + service.save("c", 5, true));
            System.out.println("C2=" + service.save("c", -1, true));
            System.out.println("C cached="
                + cache.get("C", Item.class));

            System.out.println("A2=" + service.save("a", 11, true));
            System.out.println("A find again=" + service.find("A"));
            System.out.println("updateCalls=" + service.updateCalls()
                + ", loadCalls=" + service.loadCalls());
        }
    }
}
~~~

Run from the directory containing pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CachePutTimingDemo
~~~

**Stdout from the println statements in the program** (excluding any Maven logs printed by the environment):

~~~text
A1=Item[id=A, amount=10, approved=true]
A find=Item[id=A, amount=10, approved=true]
B1=Item[id=B, amount=20, approved=true]
B in cache=false
B find=Item[id=B, amount=20, approved=true]
B2=Item[id=B, amount=21, approved=true]
B find again=Item[id=B, amount=20, approved=true]
C1=Item[id=C, amount=5, approved=true]
C2=Item[id=C, amount=-1, approved=false]
C cached=Item[id=C, amount=5, approved=true]
A2=Item[id=A, amount=11, approved=true]
A find again=Item[id=A, amount=11, approved=true]
updateCalls=6, loadCalls=1
~~~

Explanation:

1. **A1:** `allowCachePut=true`, valid amount → condition true, unless false; result id `"A"` is written to cache. **find("A")** hits so `loads` does not increment.
2. **B1:** `allowCachePut=false` → condition false; method still writes Item B20 to database, **without putting**. Direct cache inspection confirms B is not present yet. **find("B")** misses, loads B20, and increments `loads` to 1; @Cacheable stores B20.
3. **B2:** `allowCachePut=false`, so the database is updated to B21 while @CachePut still **skips writing**. The B20 entry previously stored by @Cacheable is not deleted; **find("B")** continues hitting B20. This demonstrates **stale cache** caused by skipping a put without invalidation.
4. **C1:** `amount=5` → `approved=true`, C5 is written to cache. **C2:** `amount=-1` → `approved=false`, fails the `unless` check (unless is true so it vetoes the put); entry C5 remains in the cache, even though the database changed to C-1.
5. **A2:** updates A11 with conditions allowing it; cache entry A10 is **replaced** with A11. **find("A")** returns A11 from the cache.
6. There are **six** calls to `save`, so `updateCalls=6`, including cases where `condition=false` or `unless=true`. Only **one** `find` call missed (B's first read), so `loadCalls=1`.

The demo intentionally keeps the old entry to **clearly expose the staleness bug when skipping a put**. Real applications need appropriate invalidation design to avoid returning stale data or data no longer permitted to be shown.

### Why doesn't @CachePut read the cache first?

The annotation does not use a cache hit to skip the call. An update method needs to execute the business operation, so Spring must not replace the update action with a value from the cache as with @Cacheable. Direct `Cache` gets in the demo are strictly for **testing**; this is not an automatic operation of @CachePut.

## 7. Update conditions are not a cache eviction mechanism

Comparison table of scenarios when **an entry already exists**:

| Scenario | Method runs? | Does Spring @CachePut write new value? | Old entry |
| --- | --- | --- | --- |
| condition=true, unless=false, method succeeds | Yes | Yes, writes/replaces | Updated under key |
| condition=false | Yes | No | **May remain** |
| condition=true, unless=true | Yes | No | **May remain** |
| Method throws exception before returning result | Yes and errors | No successful result to put | Usually remains unless something else deletes it |
| condition=true, method returns null, unless does not block | Yes | Depends on Cache implementation's null handling | May become null/value wrapper or hit provider error |

To remove an entry when data is no longer allowed to be cached, an explicit deletion action is required, such as **@CacheEvict**, or consistent cache updates under another strategy. @CacheEvict has a **beforeInvocation** attribute to choose deleting before/after the call, whereas **@CachePut has no beforeInvocation**.

Example of an explicit delete operation:

~~~java
@CacheEvict(cacheNames = "items", key = "#p0")
public void invalidate(String normalizedId) {
    // Method handling the invalidation request.
}
~~~

The snippet above is not standalone; it must reside in a Spring bean with `@EnableCaching`. When `invalidate` is called through the proxy, the `"items"` cache removes the entry with key `normalizedId` after the method succeeds, per @CacheEvict's default. If the database also needs changes, the business operation and invalidation timing must be designed appropriately.

**Do not automatically add @CacheEvict alongside @CachePut on every method** without analyzing AOP ordering, conditions, consistency, and transactions. What matters is ensuring every source mutation has a strategy to refresh or invalidate corresponding cached data.

## 8. Typical SpEL errors regarding #result timing

| Declaration | Assessment |
| --- | --- |
| **@CachePut(condition="#p0 != null")** | Valid: checks input before invocation |
| **@CachePut(unless="#result == null")** | Valid: blocks caching null results after invocation |
| **@CachePut(key="#result.id()")** | Valid if result is non-null and has `id()` |
| **@CachePut(condition="#result.approved()")** | **Wrong timing:** condition has no result |
| **@CachePut(unless="#p1 == false")** | Syntactically valid: can inspect input after invocation; usually condition is clearer |
| **@Cacheable(key="#result.id()")** | **Wrong timing:** key is needed before cache lookup |
| **@CacheEvict(beforeInvocation=true, key="#result.id()")** | **Wrong timing:** evicts before result exists |
| **@CacheEvict(beforeInvocation=false, key="#result.id()")** | Can be valid: defaults to evicting after invocation, when result exists |

If a SpEL expression requests a non-existent property/method or tries to invoke a property on null, the operation may throw an expression evaluation error. These errors do not prove the business method itself is broken; check the exact context Spring provides at evaluation time.

**Do not confuse #result with a parameter named `result`.** If a real method has a parameter named `result`, you can reference it via **#p0**, **#p1**... or the name retained by the compiler. In caching SpEL, **#result** is the special variable representing the method's return value in supported phases.

For parameter names like **#productId**, the compiler may need the **-parameters** flag. **#p0**, **#a0**, and **#root.args[0]** avoid depending on variable names in bytecode.

## 9. Ordering relative to transactions and asynchronous behavior

### Transactions: “method returned” does not always mean “committed”

When `@Transactional` is present, Spring Cache and Transaction are separate advice layers. **Advice ordering and how the CacheManager integrates with transactions affect whether the cache put happens before or after commit**. If the cache writes the result but the transaction subsequently rolls back, the cache may not reflect the database.

Distinguish between:
- **Method returns successfully**: Spring now has a result to evaluate `unless` and `key`.
- **Transaction has committed**: source data has been durably accepted according to transaction policy.

These two moments **do not automatically coincide**. For businesses requiring high consistency, consider updating/invalidating **after commit**, configuring a transaction-aware cache (where appropriate), or post-commit events/outbox patterns, then test rollback scenarios. Do not assume @CachePut automatically guarantees atomicity between database and cache store.

### Future/Reactive (Spring Framework 6.1+)

For supported return types like **CompletableFuture** and reactive types, Spring Framework 6.1+ can perform the put **when the result object is produced/completes**, instead of merely storing a pending wrapper. When interpreting `#result`, examine the actual result type Spring provides and the framework version/configuration in use. Do not assume the put callback has succeeded immediately after the method returns a still-pending CompletableFuture.

A common mistake is testing an async method as though the result were already cached as soon as the wrapper is returned. Wait for completion before inspecting the cache, and handle exceptional future completion. The example in section 6 uses synchronous methods to verify `condition`/`unless`/`key` ordering reliably.

## 10. Choosing condition vs unless in practice

| Requirement | Usually appropriate expression | Why |
| --- | --- | --- |
| Allow put only for cache-enabled requests | **condition="#p2"** | Input is available before the call |
| Put only if result is approved | **unless="!#result.approved()"** | `approved` resides on result |
| Skip put on null result | **unless="#result == null"** | Result does not exist before the call |
| Key is database-assigned ID | **key="#result.id()"** | ID is known only after insert |
| Do not cache for a special tenant | **condition="#p0 != 'PRIVATE'"** | Tenant is an input |
| Can return null, key based on result | **unless="#result == null"** and key `"#result.id()"` | Avoids computing key from null when put is vetoed |
| Want to delete cache when source changes | **@CacheEvict / appropriate post-commit invalidation** | Skipping put does not remove old entry |

The expressions above are guiding examples; adjust `#pN` to match your method signature and business definition. **Cache keys must align** across @CachePut, @Cacheable, and @CacheEvict if they operate on the same entry. Building String keys via unnormalized concatenation, omitting tenant/currency, or missing namespaces can cause cache misses or wrong hits.

### Self-verification checklist

1. Confirm the method is called **through a Spring proxy**; self-invocation is usually not intercepted in default proxy mode.
2. Observe **actual method execution counts**, rather than using a cache hit to infer @CachePut skipped calling.
3. Verify **condition** relies only on data available before the invocation.
4. Verify **unless** evaluates the right result and boolean veto value.
5. Verify **key** with actual results, especially when IDs are generated or normalized inside the method.
6. Verify **pre-existing entries** when `condition` is false or `unless` is true; do not test only with an initially empty cache.
7. Test behavior on **exceptions, rollbacks, and failed futures** if your business domain has those cases.
8. When using multiple instances/providers, verify serialization and cross-node invalidation; local caches per JVM keep separate copies.

## 11. Self-check questions

**1.** A method annotated with @CachePut has `condition=false`. Does the method run?

**Yes.** @CachePut does not skip the method just because `condition` is false. That condition skips the cache annotation's put operation.

**2.** Why shouldn't “store only when `result.approved=true`” be written in `condition`?

Because **condition is evaluated before a result exists**. Use **unless="!#result.approved()"** after the method returns, while checking for null if the result can be null.

**3.** Creating a new product with a database-assigned ID: can @CachePut use `key="#result.id()"`?

**Yes**, when `result` is non-null and has a valid `id()` method. @CachePut allows computing the key after the result is available.

**4.** The cache holds Product version 1. An update method produces version 2, but `unless=true`. Does the cache automatically delete version 1?

**No.** Skipping this put does not mean evicting. Version 1 may remain until it expires or is explicitly invalidated.

**5.** Reads use @Cacheable with the same key, while updates use @CachePut. Can the two annotations work together?

**Yes**, on **separate appropriate methods**, sharing the same cache name and key logic. @Cacheable can take advantage of entries written by @CachePut. Putting both @Cacheable and @CachePut on **the same method** is generally discouraged because their semantics differ and can cause unpredictable behavior.

**6.** Does an update method returning successfully guarantee the cache reflects a committed transaction?

**Not by default.** Verify advice ordering and commit-aligned transaction-aware/invalidation mechanisms.

## Summary

**@CachePut always executes the method. condition is evaluated before, unless is evaluated after; #result can be used in unless and key of @CachePut once the result is available.** A skipped put does not remove an old entry. Correctness requires **write conditions**, **aligned keys**, and **a refresh/eviction strategy when source data changes**.

### References

- Spring Framework – Annotation-based caching (condition, unless, #result, @CachePut): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework – @CachePut API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CachePut.html
- Spring Framework – SpEL: https://docs.spring.io/spring-framework/reference/core/expressions.html
- Spring Framework – Transaction-aware Cache Decorator: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html
