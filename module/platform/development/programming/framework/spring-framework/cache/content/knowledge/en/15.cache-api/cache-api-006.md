# evict vs. evictIfPresent in Spring Cache

> **Spring Framework – Cache Abstraction · Group: Programmatic API.** This lesson compares `Cache.evict(Object key)` and `Cache.evictIfPresent(Object key)` when invalidating a cache entry. The most important differences lie in **when the removal becomes visible** and **the meaning of the returned boolean**, especially when the cache is wrapped in a transaction-aware decorator.

## 1. Both delete a key, but their contracts are not identical

Suppose the `books` cache currently holds:

~~~text
books["ISBN-A"] = "Java Basics"
books["ISBN-B"] = "Spring Basics"
~~~

When the source data for ISBN-A changes, the program wants to drop the corresponding entry so subsequent reads do not use the stale version. Two common APIs:

~~~java
cache.evict("ISBN-A");
boolean knownPresent = cache.evictIfPresent("ISBN-A");
~~~

This snippet only illustrates calls inside a method that already has a `cache` variable of type `org.springframework.cache.Cache`. A runnable example is in section 6.

Both request **removing the mapping for one key**; neither updates the database nor clears the entire cache region. However:

- `evict(key)` has return type **`void`**; the implementation may evict immediately, asynchronously, or **defer** the operation. The call does not report whether the key existed beforehand.
- `evictIfPresent(key)` has return type **`boolean`**; the contract expects the key to become **immediately invisible to the next lookup**. The return value indicates whether the implementation knew a mapping existed prior to eviction.
- System-level guarantees still depend on the backend, decorators, and concurrent writers. **Completing an eviction does not prevent another thread from putting the same key back.**

### Comparison table

| Criterion | `evict(Object key)` | `evictIfPresent(Object key)` |
| --- | --- | --- |
| Scope | Single key | Single key |
| Return type | `void` | `boolean` |
| Reports whether entry existed? | No | Yes, if the provider can determine it |
| Eviction timing | May be immediate, delayed, or asynchronous | API expects immediate visibility |
| With transaction-aware decorator | May defer until **after-commit** | Immediate, **does not defer** to after-commit |
| When key does not exist | No return value | Typically returns `false` |
| When provider does not know prior presence | Not applicable | May return `false` |
| Best suited for | Routine invalidation where presence feedback is unneeded | Immediate eviction and knowing prior presence when supported by provider |

**The name `evictIfPresent` does not mean `evict` removes an absent key while the other only removes when present.** Both target the mapping if a mapping is present. The "IfPresent" part expresses the additional boolean contract.

## 2. Interpreting true and false from evictIfPresent accurately

Spring Cache API definition:

~~~java
void evict(Object key);
default boolean evictIfPresent(Object key);
~~~

For `evictIfPresent`:

- Returns **`true`** when the cache implementation **knows there was a mapping** for the key before removal.
- Returns **`false`** when the implementation knows there was no mapping **or cannot determine** the prior presence state.

Therefore, do not use a `false` result to assert that the business record does not exist in the database, or to assert that no cache entry ever existed beforehand.

Example:

~~~java
public boolean removeKnownCacheEntry(Cache cache, String isbn) {
    return cache.evictIfPresent(isbn);
}
~~~

This is an illustrative Java method requiring `import org.springframework.cache.Cache`. The boolean should be interpreted as **known prior cache presence**, not as a check of record existence in the underlying data store.

### Why can it return false even if the key had an entry?

Since Spring Framework **5.2**, `evictIfPresent` is a **default method** on the `Cache` interface. The default implementation delegates to `evict(key)` and then returns `false` because **prior presence cannot be determined**.

Providers/decorators are encouraged to override this method to support immediate eviction and accurate status reporting. Spring's `ConcurrentMapCache` provides its own implementation and is used in the following example.

**Design implication:** the API contract targets immediate eviction, but if a custom provider only relies on the default implementation, the caller cannot infer stronger immediate guarantees than `evict`. Before relying on the boolean or timing behavior, inspect the actual `Cache` implementation class, not just the interface signature.

## 3. Immediate visibility is not system-wide consistency

`evictIfPresent(key)` expresses the expectation that **the key is no longer visible in subsequent lookups on that cache implementation**. It does not mean:

- The database has committed the update.
- No other request is currently reading the old version.
- No concurrent writer puts the key back right after eviction.
- Nodes using separate local caches have received an invalidation message.
- All copies across multiple cache layers are instantaneously synchronized.

Example race:

~~~text
Reader R1 reads "old" from database (not yet put into cache)
                   |
Writer W updates database to "new"
                   |
Writer W evictIfPresent("ISBN-A")
                   |
Reader R1 put("ISBN-A", "old")
                   |
Subsequent read hits stale cache again
~~~

Immediate eviction resolves **the mapping state at the moment of the call**, but does not create an atomic transaction between cache and database. When high consistency is required, consider versioned keys, transaction coordination, TTL, event invalidation, and mechanisms preventing stale writes.

## 4. TransactionAwareCacheDecorator makes the two APIs behave markedly differently

Spring's `TransactionAwareCacheDecorator` can synchronize `put`, `evict`, and `clear` operations with a **Spring-managed transaction**. When a matching transaction is active, the actual operation runs in the **after-commit** phase after a successful commit; when no transaction is active, they typically run immediately.

### Calling evict inside a transaction

~~~text
Transaction starts
        |
Update row in database (uncommitted)
        |
cache.evict("ISBN-A")
        |
Transaction-aware decorator schedules eviction
        |
Commit succeeds
        |
After-commit: actually removes entry ISBN-A
~~~

Between calling `evict` and commit, the cache may **still show the old mapping**. This is not necessarily a bug; waiting for commit prevents pointless cache eviction when a transaction rolls back.

### Calling evictIfPresent inside a transaction

~~~text
Transaction starts
        |
Update row in database (uncommitted)
        |
cache.evictIfPresent("ISBN-A")
        |
Decorator invokes immediate eviction right away
        |
Another reader may miss cache before DB commits
        |
Commit or rollback happens afterward
~~~

Spring explicitly states that immediate operations like `evictIfPresent` **cannot be deferred until after-commit** on this decorator. Be careful: evicting the cache before the transaction truly succeeds can cause a reader to reload old DB data; if the transaction rolls back, the eviction has already occurred.

**Recommendation:** do not switch `evict` to `evictIfPresent` inside a transaction just to receive a boolean. If what you need is invalidation *after commit*, design the transaction boundary, cache manager, and provider behavior properly. If the requirement is for the key to disappear immediately, accept and handle the corresponding consistency risk.

Note: transaction awareness is a specific decorator layer. Standalone cache backends do not automatically have the same policy; adding `@Transactional` to any method does not automatically make every cache transaction-aware.

## 5. Cache miss differs from cached null

When checking a key after eviction, `Cache.get(key)` (the variant returning `ValueWrapper`) is the right tool.

~~~java
Cache.ValueWrapper wrapper = cache.get("ISBN-A");
boolean entryVisible = wrapper != null;
~~~

This snippet illustrates code inside a method with a `cache` variable. Spring distinguishes:

| Result | Interpretation |
| --- | --- |
| `cache.get(key) == null` | **Cache miss**, no mapping visible |
| `cache.get(key) != null` and `wrapper.get() == null` | Mapping exists, but **logical value is null** |
| `wrapper.get()` is non-null | Mapping exists with a logical value |

Because some cache backends allow cached null, `cache.get(key, String.class) == null` is **not sufficient** to conclude a cache miss. The example in section 6 verifies that `evictIfPresent` still returns true when an entry has a cached-null value and the provider knows the mapping exists.

## 6. Complete Java 17+ example: testing both APIs

The example uses **Java 17**, **Spring Framework 6.2.14**, and local `ConcurrentMapCacheManager`. In this backend, both `evict` and `evictIfPresent` remove entries immediately. The most clearly observable difference is the **return value** of `evictIfPresent`.

Create two files at the exact paths below.

**File `build.gradle`**

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.EvictMethodsDemo'
}
~~~

**File `src/main/java/demo/EvictMethodsDemo.java`**

~~~java
package demo;

import java.util.Objects;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;

public class EvictMethodsDemo {

    public static void main(String[] args) {
        CacheManager manager = new ConcurrentMapCacheManager("books");
        Cache cache = Objects.requireNonNull(manager.getCache("books"));

        cache.put("A", "first-edition");
        cache.put("B", "stable-edition");

        System.out.println("A initially present: " + (cache.get("A") != null));
        System.out.println("B initially present: " + (cache.get("B") != null));

        cache.evict("A");
        System.out.println("A after evict: " + (cache.get("A") != null));
        System.out.println("B after evict: " + (cache.get("B") != null));

        cache.put("A", "second-edition");
        boolean first = cache.evictIfPresent("A");
        System.out.println("first evictIfPresent: " + first);
        System.out.println("A after evictIfPresent: " +
                (cache.get("A") != null));

        boolean second = cache.evictIfPresent("A");
        System.out.println("second evictIfPresent: " + second);

        // ConcurrentMapCacheManager allows cached null by default.
        cache.put("EMPTY", null);
        Cache.ValueWrapper nullEntry = cache.get("EMPTY");
        System.out.println("cached null entry exists: " +
                (nullEntry != null));
        System.out.println("cached null value: " +
                Objects.requireNonNull(nullEntry).get());

        System.out.println("evict cached null: " +
                cache.evictIfPresent("EMPTY"));
        System.out.println("null entry after eviction: " +
                (cache.get("EMPTY") != null));

        cache.evict("MISSING");
        System.out.println("B final value: " +
                Objects.requireNonNull(cache.get("B")).get());
    }
}
~~~

Run in the directory containing `build.gradle`, with JDK 17+ and a compatible Gradle version:

~~~bash
gradle run --quiet
~~~

**Expected stdout of the application** (excluding Gradle logs):

~~~text
A initially present: true
B initially present: true
A after evict: false
B after evict: true
first evictIfPresent: true
A after evictIfPresent: false
second evictIfPresent: false
cached null entry exists: true
cached null value: null
evict cached null: true
null entry after eviction: false
B final value: stable-edition
~~~

### Output analysis

1. The first two `put` calls create entries A and B. Since `Cache.get(key)` returns a wrapper, the first two lines print true.
2. `cache.evict("A")` removes A in the local `ConcurrentMapCache`; B remains present. Calling `evict` does not report how many mappings were removed.
3. After putting A again, the first `evictIfPresent("A")` returns true (knew a mapping existed), after which A is gone. The second call returns false because A is absent by then.
4. `cache.put("EMPTY", null)` creates **an entry containing a logical null value** via the internal null holder; `Cache.get("EMPTY")` returns a non-null wrapper.
5. `evictIfPresent("EMPTY")` returns true because the entry previously existed, even though its logical content is null.
6. Evicting key `MISSING` via `evict` does not affect B; B's final value remains `stable-edition`.

**Demo limitations:** this is a single JVM without a transaction decorator. Do not use the output to conclude every remote provider returns the same booleans and has the same immediate-visibility level. The output is derived from the code and API behavior in this configuration; in real deployments, run tests against the actual cache provider.

The program only calls `Cache` directly. It **does not need `@EnableCaching`** or Spring AOP proxies for `cache.evict` and `cache.evictIfPresent` calls to work.

## 7. Should you use evict or evictIfPresent?

### Prefer `evict(key)` when

- You only need to issue a key deletion, with no logic depending on prior presence.
- You want to combine with a transaction-aware cache so the operation can wait until after-commit.
- The Cache API is part of a routine update workflow where business correctness does not rely on a boolean value.
- Potentially asynchronous backend semantics are acceptable, provided TTL and consistency policies are defined.

Example:

~~~java
public void invalidate(Cache cache, String isbn) {
    cache.evict(isbn);
}
~~~

This method does not prove the cache ever held the key. It simply instructs the backend to perform invalidation.

### Prefer `evictIfPresent(key)` when

- You require the **immediate visibility** contract and have verified the provider implements it accordingly.
- You want to know that a mapping was **confirmed to exist before the call**, for instance to record provider-level metrics.
- You accept that this invocation may not wait for transaction commit.
- You do not treat `false` as definitive proof about the database or prior presence with a custom backend.

Example:

~~~java
public boolean invalidateImmediately(Cache cache, String isbn) {
    return cache.evictIfPresent(isbn);
}
~~~

**Note:** the boolean here is **known prior presence**, not confirmation that the source record was deleted or that all cache instances are consistent.

| Scenario | Choice to consider |
| --- | --- |
| Update DB, transaction-aware cache should evict after commit | `evict` |
| Need the key to vanish immediately in the current cache | `evictIfPresent` on a supporting backend |
| Want to distinguish hit/miss before invalidation | `evictIfPresent`, while respecting false = absent/unknown |
| Legacy code uses custom `Cache` that has not overridden the default method | Verify the implementation before relying on the boolean |
| Need multi-key/region-wide invalidation | Design multi-key logic or use region-wide APIs; do not force a single-key API |

## 8. Relationship with @CacheEvict

`@CacheEvict` is a declarative annotation on business methods; `Cache.evict` and `Cache.evictIfPresent` are direct Java calls. These two API layers are related but **not identical**.

~~~java
@CacheEvict(cacheNames = "books", key = "#p0")
public void renameBook(String isbn, String newTitle) {
    repository.updateTitle(isbn, newTitle);
}
~~~

This is an integration example requiring a real repository, a Spring-managed bean, and caching infrastructure. With the default `beforeInvocation = false`, Spring evicts after the method finishes successfully; if an exception is thrown, eviction does not run by default.

~~~java
@CacheEvict(
    cacheNames = "books",
    key = "#p0",
    beforeInvocation = true
)
public void renameBook(String isbn, String newTitle) {
    repository.updateTitle(isbn, newTitle);
}
~~~

In before-invocation mode, Spring performs eviction before invoking the method, even if the body later throws an exception. Inside the caching interceptor, the immediate branch of `AbstractCacheInvoker` uses `evictIfPresent`, whereas the normal branch uses `evict`.

**Do not misunderstand:** the annotation does not return the boolean from `evictIfPresent` to the method caller. The `beforeInvocation` attribute primarily expresses the choice of **evicting before or after business logic**, not a flag for "whether to return true/false".

If the application updates the database inside a transaction, evaluate races and commit boundaries before switching to before-invocation eviction. The immediate API style is not automatically better than the deferred style when the goal is preserving consistency.

## 9. Do not confuse with clearing the entire region

Both methods covered here remove **a single entry key**. Spring also has a pair of methods that apply to the entire region:

| Single key | Entire cache region | Key difference |
| --- | --- | --- |
| `evict(key)` | `clear()` | May have deferred/asynchronous semantics |
| `evictIfPresent(key)` | `invalidate()` | Aims for immediate visibility, provides boolean information |

If only one product is updated, clearing the whole region can force every key to reload. Only use `clear` or `invalidate` when you genuinely need to invalidate **every entry** in that cache region.

## 10. Common mistakes and how to check them

| Mistake | Consequence | How to handle |
| --- | --- | --- |
| Assuming `evict` always deletes immediately | Deferred decorator still shows the old entry before commit | Check backend / transaction-aware decorator |
| Assuming `false` from `evictIfPresent` proves the key never existed | Default implementation may return false for unknown | Distinguish known presence from absent/unknown |
| Using `evictIfPresent` inside a transaction while expecting after-commit | Cache is cleared before commit, risking stale reloads | Use semantics matching the transaction boundary |
| Using null from `Cache.get(key, type)` to conclude a miss | Confuses cached null with missing entry | Check `Cache.ValueWrapper` |
| Evicting a key yet data stays stale afterward | Concurrent reader puts old data back; wrong key or wrong manager | Verify key, put/evict timing, provider, and readers |
| Using a region-wide API to delete one SKU | Drops unrelated entries | Use a single-key API |
| Calling `@CacheEvict` from another method on the same bean | Self-invocation bypasses the cache proxy | Call through a valid Spring bean/proxy |
| Using `true` as proof the record exists in the DB | Cache entries are separate from business source data | Query the source to verify existence |

When debugging, verify in sequence: **correct cache instance → correct key → specific implementation → whether a transaction decorator is present → ValueWrapper state after eviction → whether any concurrent writer puts the key back**.

## 11. Self-check exercises

**Exercise 1.** Does `cache.evict("A")` return true when A previously existed?

**Answer:** No. The method returns `void`.

**Exercise 2.** Does `cache.evictIfPresent("A")` returning false mean the cache definitely never held A?

**Answer:** No. Either the key is absent or the provider **does not know** prior presence.

**Exercise 3.** The cache has mapping `"N"` with a logical null value. Can `evictIfPresent("N")` return true?

**Answer:** Yes, if the provider knows the mapping exists, such as `ConcurrentMapCache` in the example.

**Exercise 4.** A transaction-aware decorator is deferring `evict` until after-commit. Will switching to `evictIfPresent` preserve after-commit behavior?

**Answer:** No. This is an immediate API and cannot be deferred by that decorator.

**Exercise 5.** Why can immediate deletion still lead to stale data?

**Answer:** Another reader can load the old version before the database commits and then put the key back into the cache. Eviction does not create atomicity between two systems.

## 12. Summary and official documentation

- `evict(key)` = deletes one mapping, returns **void**, may be deferred.
- `evictIfPresent(key)` = deletes one mapping with an expectation of **immediate** effect, returns a boolean for *known prior presence*.
- **`false` can mean absent or unknown**; the default method can delegate to `evict` and return false.
- A transaction-aware decorator can defer `evict` after commit; it does not defer `evictIfPresent`.
- Cache miss differs from cached null; check using `Cache.ValueWrapper`.
- Immediate eviction does not eliminate races and does not replace synchronization with the database.

**Spring Documentation:**

- [Spring 6.2.14 – Cache API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/Cache.html)
- [Spring 6.2.14 – ConcurrentMapCache](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html)
- [Spring 6.2.14 – TransactionAwareCacheDecorator](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html)
- [Spring 6.2.14 – AbstractCacheInvoker](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/interceptor/AbstractCacheInvoker.html)
- [Spring Framework 6.2 – Annotation-based Caching](https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html)
