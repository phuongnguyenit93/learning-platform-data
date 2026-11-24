# Risks of Mutating a Mutable Object After Retrieving It from Cache

## Objectives

This lesson belongs to the **Data and Lifecycle** group of Spring Framework Cache. After completing this lesson, you will:

- Understand why a value returned from `@Cacheable` can be **the exact same object stored in the cache**, rather than an independent copy.
- Recognize the **shared mutable state** bug: one caller mutates a `List`, `Map`, or DTO property, causing subsequent callers to receive unexpectedly modified data.
- Distinguish between **changes in the cache**, **changes in the data source**, and **cache invalidation**; never confuse mutating a Java object with updating the database.
- Prevent this issue with immutable DTOs, defensive copies at the proper boundaries, controlling provider store-by-reference/store-by-value behavior, and invalidating when source data changes.
- Run a Spring Boot Java 17+ example that reproduces the bug, compare the safe fix, and verify cache hits/misses accurately.

**Key principle:** `@Cacheable` ensures that a computation can be reused by key; it **does not guarantee that the returned object is independent, immutable, thread-safe, or automatically synchronized with the database**. How objects are stored and returned depends on the `Cache`/backend.

## 1. Why is mutating an object after retrieving it from cache dangerous?

Consider a service that returns user profiles:

~~~java
@Cacheable(cacheNames = "profiles", key = "#p0")
public UserProfile findProfile(String userId) {
    return repository.find(userId);
}
~~~

This snippet is illustrative, with `UserProfile` and `repository` defined by the application. Suppose the result has a mutable list of roles:

~~~java
UserProfile p = profileService.findProfile("u1");
p.getRoles().add("admin");
~~~

The author may think they are only adjusting the result for the current screen. However, if the provider holds a **reference to the cached Java object itself**, calling `add("admin")` mutates the state held by the cache. Another call:

~~~java
UserProfile q = profileService.findProfile("u1");
~~~

can receive the same instance and see the `admin` role, **even though `findProfile` never ran again, the database was not updated, and no one called `@CachePut`**.

### Shared-reference bug diagram

~~~text
First call:
  Controller A ──findProfile("u1")──> cache MISS
                          │
                          └─ repository → object X
                                            ├─ roles: ["reader"]
                                            └─ stored by reference
  cache["u1"] ───────────────────────────────┘
  Controller A receives object X itself

A executes: X.roles.add("admin")

Next call:
  Controller B ──findProfile("u1")──> cache HIT
                           └──────> object X
                                      roles: ["reader","admin"]
                                      (NO source query)
~~~

This is especially clear with the default `ConcurrentMapCache`: Spring's official API states that `isStoreByValue() == false` is the default mode, meaning the cache stores a **reference**. Consequently, a cache hit typically hands back the same stored object in the JVM without cloning it.

**Do not generalize to every backend:** Redis and providers that use serialization typically work with bytes and deserialize a new object on each read; different providers and local caches may have different copy policies. Always verify the actual configuration instead of assuming “cache” always means a copy or always means a reference.

## 2. In what situations does the risk occur?

### 2.1. Data is mutated across requests

Request A adds an element to a cached list; Request B reads that same key and sees the newly added element. If this is permissions, pricing, or a user's private shopping cart, the consequences can be severe. State is no longer determined solely by the data source.

### 2.2. Cache and database drift apart

In an in-memory cache demo, mutating an object in the cache is **not equivalent** to updating the database. The cached `cached.roles()` value might be `["reader","admin"]` while the source remains `["reader"]`. When `@CacheEvict` runs or the TTL expires, the application reloads from the source and “loses” the unintended change.

Conversely, if the cached value is a JPA entity still managed by a persistence context, mutating a property may participate in **dirty checking** and trigger a database update upon flush. That depends on the transaction/EntityManager rather than `@Cacheable`'s default behavior. For this reason, caching mutable JPA entities directly is risky and needs careful review.

### 2.3. Race conditions across multiple threads

`ConcurrentHashMap` provides thread-safe operations for **map entries**; that **does not make the objects inside it thread-safe**. Two requests can concurrently mutate a cached `ArrayList` or Java bean and cause lost updates, inconsistent observed data, or errors during collection iteration. `@Cacheable(sync=true)` only helps coordinate **loading the same key on a miss** when supported by the provider; it does not lock every subsequent mutation of the object after it is returned.

### 2.4. “Hidden” side effects of read methods

A function preparing a response like this is dangerous if its input is an object retrieved from cache:

~~~java
// Illustrates an anti-pattern; returns a mutable DTO/collection.
public UserProfile personalize(UserProfile cached) {
    cached.getRoles().remove("internal");
    cached.setDisplayName("Hello " + cached.getDisplayName());
    return cached;
}
~~~

Even though the method is named `personalize`, it directly mutates the shared instance. Another request may receive a name with `"Hello"` prepended multiple times or a filtered role list. **View/model transformations must create new data rather than mutating shared source data.**

### 2.5. “Records are immutable” yet contain mutable references

~~~java
public record BookView(String id, List<String> tags) {}
~~~

You cannot reassign the `tags` field after the record is created, yet you can still call `view.tags().add("changed")` if the underlying list is an `ArrayList`. A record only guarantees **fixed field references**; it does not automatically freeze the entire object graph. Immutability is needed from the root down to nested objects.

## 3. Contracts to remember: store-by-reference and store-by-value

| Aspect | Store-by-reference | Store-by-value / serialization |
| --- | --- | --- |
| Stored value | Usually holds a reference to the Java object. | Usually writes a copy/serialized representation. |
| What do readers receive? | May be the same instance in the JVM shared with other callers. | Usually receives a new object after decoding/copying on hit. |
| Mutating the returned DTO | May alter the cached content itself. | Usually does not directly mutate the serialized entry, though this still depends on the provider and boundaries. |
| Concurrency risk | Shared mutable instances are easily accessed concurrently. | Can reduce reference sharing, but does not eliminate logic bugs or staleness. |
| Trade-off | Little copying, fast, but aliasing risk. | Serialization/CPU/memory cost; requires serializer-compatible data. |
| Example | Default `ConcurrentMapCache`. | Caches with explicit copy/serialization policies; many Redis use cases. |

In Spring, `ConcurrentMapCache.isStoreByValue()` reports that implementation's policy. `ConcurrentMapCacheManager` can be configured for store-by-value on supported versions, though enabling it typically requires serializable values and incurs copy overhead. **Do not treat that as system-wide immutability design:** an API returning mutable objects can still be mutated by callers at another layer; what matters is the ownership contract and how data is exposed.

**Even on a cache miss:** Spring can return the object just produced by the method directly to the caller while also placing that same object into the cache. Therefore, copying only on the cache-hit path (or only when reading via a secondary method) may not be enough. Protect **both on write and on return**, or use immutable DTOs from the start.

## 4. Runnable example: mutable reference “polluting” the cache

The demo intentionally uses `ConcurrentMapCacheManager` with its default store-by-reference mode, Java 17+, and Spring Boot. The “database” is a `ConcurrentHashMap` holding immutable source lists so you can clearly observe that caller mutations on the cache **do not alter the source**.

In an existing Spring Boot Gradle project, keep compatible plugins/versions and ensure these dependencies are present:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

Create the following Java files under `src/main/java/example/mutablecache/`.

### 4.1. MutableProfile.java — object with a mutable collection

~~~java
package example.mutablecache;

import java.util.List;
import java.util.Objects;

public final class MutableProfile {
    private final String id;
    private final List<String> roles;

    public MutableProfile(String id, List<String> roles) {
        this.id = Objects.requireNonNull(id, "id");
        this.roles = Objects.requireNonNull(roles, "roles");
    }

    public String id() {
        return id;
    }

    // Intentionally returns a mutable list directly to illustrate the bug.
    public List<String> roles() {
        return roles;
    }
}
~~~

In `MutableProfile`, the `roles` field is `final`, yet **the elements of the List can still change** if callers hold a reference to a mutable list. `final` does not mean deep immutability.

### 4.2. ProfileSnapshot.java — record with defensive copy

~~~java
package example.mutablecache;

import java.util.List;
import java.util.Objects;

public record ProfileSnapshot(String id, List<String> roles) {
    public ProfileSnapshot {
        Objects.requireNonNull(id, "id");
        roles = List.copyOf(roles);
    }
}
~~~

`List.copyOf(roles)` creates an unmodifiable list detached from the source **when needed**; if the source is a mutable list, the snapshot is unaffected by later changes to the source list. In this demo, each element is a `String` — an immutable type — so both the list layer and its elements are safe. For a `List<MutableAddress>`, `List.copyOf` only copies the **list structure**, without cloning each `MutableAddress`; each element must be converted into an immutable value object.

### 4.3. CacheConfiguration.java — enabling Spring Cache

~~~java
package example.mutablecache;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager(
                "mutableProfiles", "snapshotProfiles");
    }
}
~~~

The two cache regions have distinct names so we can compare them on the same ID without cross-contaminating results. There is no TTL, distributed cache, or automatic object copying in this configuration.

### 4.4. ProfileService.java — two ways of returning results

~~~java
package example.mutablecache;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.Caching;
import org.springframework.stereotype.Service;

@Service
public class ProfileService {
    private final Map<String, List<String>> source =
            new ConcurrentHashMap<>(Map.of(
                    "u1", List.of("reader")));

    private final AtomicInteger mutableLoads = new AtomicInteger();
    private final AtomicInteger snapshotLoads = new AtomicInteger();

    @Cacheable(cacheNames = "mutableProfiles", key = "#p0")
    public MutableProfile mutable(String id) {
        System.out.println("MUTABLE_LOAD #" +
                mutableLoads.incrementAndGet());
        return new MutableProfile(
                id, new ArrayList<>(loadRoles(id)));
    }

    @Cacheable(cacheNames = "snapshotProfiles", key = "#p0")
    public ProfileSnapshot snapshot(String id) {
        System.out.println("SNAPSHOT_LOAD #" +
                snapshotLoads.incrementAndGet());
        return new ProfileSnapshot(id, loadRoles(id));
    }

    // Returns an immutable copy of the source list for verification.
    public List<String> sourceRoles(String id) {
        return List.copyOf(loadRoles(id));
    }

    public int mutableReadCount() {
        return mutableLoads.get();
    }

    public int snapshotReadCount() {
        return snapshotLoads.get();
    }

    // When SOURCE is legitimately updated, explicitly evict entries
    // from both regions so the next read loads a fresh snapshot.
    @Caching(evict = {
            @CacheEvict(cacheNames = "mutableProfiles", key = "#p0"),
            @CacheEvict(cacheNames = "snapshotProfiles", key = "#p0")
    })
    public void updateRoles(String id, List<String> newRoles) {
        if (!source.containsKey(id)) {
            throw new IllegalArgumentException("Unknown id: " + id);
        }
        source.put(id, List.copyOf(newRoles));
    }

    private List<String> loadRoles(String id) {
        List<String> roles = source.get(id);
        if (roles == null) {
            throw new IllegalArgumentException("Unknown id: " + id);
        }
        return roles;
    }
}
~~~

Explanation of the branches:

- `mutable("u1")` returns a new `MutableProfile` with a mutable `ArrayList`. The result is held in `mutableProfiles["u1"]` by reference.
- `snapshot("u1")` returns a `ProfileSnapshot` with an unmodifiable role list; even though the cache holds a reference, callers have no normal API to mutate state in the cache.
- `sourceRoles("u1")` reads the source directly and returns an immutable list to prove that mutating the cache does not automatically write back to the source.
- `updateRoles(...)` is an **intentional** update path: it updates the source and uses `@Caching` combining two `@CacheEvict` annotations to remove the corresponding entries after the method succeeds. This is the solution for source changes, **not a reason to let callers mutate cached objects**.

### 4.5. MutableCacheApplication.java — observing the results

~~~java
package example.mutablecache;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class MutableCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(MutableCacheApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(ProfileService service) {
        return args -> {
            MutableProfile first = service.mutable("u1");
            MutableProfile second = service.mutable("u1");
            System.out.println("same reference = " + (first == second));

            first.roles().add("admin");
            System.out.println("unsafe cached roles = " +
                    service.mutable("u1").roles());
            System.out.println("source roles = " +
                    service.sourceRoles("u1"));
            System.out.println("mutable loads = " +
                    service.mutableReadCount());

            ProfileSnapshot safe = service.snapshot("u1");
            try {
                safe.roles().add("admin");
            } catch (UnsupportedOperationException ex) {
                System.out.println("snapshot mutation blocked");
            }
            System.out.println("safe cached roles = " +
                    service.snapshot("u1").roles());
            System.out.println("snapshot loads = " +
                    service.snapshotReadCount());

            service.updateRoles("u1", List.of("reader", "editor"));
            System.out.println("after update mutable = " +
                    service.mutable("u1").roles());
            System.out.println("after update snapshot = " +
                    service.snapshot("u1").roles());
        };
    }
}
~~~

Run from the project directory:

~~~bash
./gradlew bootRun
# Windows PowerShell: .\gradlew.bat bootRun
~~~

**`System.out` lines from the demo, in order** (ignoring Spring Boot/Gradle logs):

~~~text
MUTABLE_LOAD #1
same reference = true
unsafe cached roles = [reader, admin]
source roles = [reader]
mutable loads = 1
SNAPSHOT_LOAD #1
snapshot mutation blocked
safe cached roles = [reader]
snapshot loads = 1
MUTABLE_LOAD #2
after update mutable = [reader, editor]
SNAPSHOT_LOAD #2
after update snapshot = [reader, editor]
~~~

**Why is this output expected?**

1. The first call to `mutable("u1")` is a cache miss → prints `MUTABLE_LOAD #1`, creates object A, and stores A in `mutableProfiles`.
2. The second call with the same ID is a hit; `first == second` is `true` because the default provider holds references. No additional `MUTABLE_LOAD` is printed.
3. `first.roles().add("admin")` directly mutates A's list. The next hit still returns A and shows `[reader, admin]`, **while the source is `[reader]`**. `mutable loads = 1` proves the method did not run again.
4. The first call to `snapshot("u1")` misses in its independent region; the Java record `ProfileSnapshot` contains an immutable list so `add("admin")` throws `UnsupportedOperationException`, which the demo catches and prints `snapshot mutation blocked`. The next hit still returns `[reader]`; `snapshot loads = 1`.
5. `updateRoles` updates the source to `[reader, editor]` and evicts both regions. The next `mutable` and `snapshot` calls both miss, print `...LOAD #2`, and load the new value.

Calls go from `CommandLineRunner` to the Spring bean `ProfileService`, so they pass through the caching interceptor proxy. Calling `this.mutable(...)` internally inside the same `ProfileService` bean in default proxy mode would bypass the annotation; the example would fail to demonstrate caching mechanics.

**Demo scope:** the “database” is just an in-process map with no transactions or replicas. Updating the source and evicting are two operations that do not commit atomically with an external database. Additional design for transactions and multiple instances is needed in production.

## 5. Four practical prevention approaches

### 5.1. Prefer immutable DTOs / snapshots

For shared cached data, return a **read-only snapshot**:

~~~java
public record CatalogItem(
        String id,
        String name,
        List<String> labels
) {
    public CatalogItem {
        labels = List.copyOf(labels);
    }
}
~~~

Callers cannot successfully invoke `snapshot.labels().add(...)`. Cached data is not an entity to be updated in place. For nested components, every element must also be immutable or converted into an immutable snapshot; `Collections.unmodifiableList(original)` is only a **view** of `original`, so if `original` is still mutated elsewhere, the view reflects those changes. `List.copyOf(original)` detaches from a mutable list, though it does not deep-copy mutable elements.

When a change is needed, create a new instance, such as `new CatalogItem(old.id(), "New", old.labels())`, and update the source of truth via a write service.

### 5.2. Defensive copying on both input and output paths

If the API cannot be changed to immutable types, define ownership boundaries and create copies:

~~~java
// Assume CacheSnapshot is an immutable type used internally
// and MutableView is a mutable type intended for callers.
public MutableView findForEditing(String id) {
    CacheSnapshot cached = cacheReader.findSnapshot(id);
    return toMutableView(cached);
}
~~~

The code above only illustrates the design; `cacheReader` and `toMutableView` are application dependencies/functions. **The idea:** the cache holds an immutable object; each caller receives a **fresh** mutable view. Mutating the view cannot alter the cache. If the cache is forced to store mutable objects, you must enforce **copying before put** and **copying after get**, including on the initial miss path; copying only in the controller does not protect other callers or already-exposed references.

A defensive copy must be deep enough for any mutable fields. Copying the outer object while continuing to share a `List<Address>` and mutable `Address` objects still causes aliasing.

### 5.3. Configure a store-by-value provider when needed, and test it

If the system caches mutable objects, a serializing/deserializing or store-by-value backend can reduce the risk of callers directly mutating cache entries. However:

- It consumes resources and carries serialization/schema/version constraints.
- Not every provider performs deep copying identically, and object identity across two reads should not be assumed.
- The miss path and write/auxiliary paths still need checks: callers may retain a reference to the object before serialization, or there may be shared state outside the cache.
- It does not solve the case where **the data source has changed** while the cache has not evicted or expired.
- It does not automatically make data access logic or mutable DTOs thread-safe.

To avoid surprises, run integration tests against **the actual production backend and configuration**, rather than relying solely on `ConcurrentMapCacheManager` results in tests.

### 5.4. Separate the read model from the write model

An easy-to-manage design is:

~~~text
Database / Repository (source of truth)
           │
           ├── read → Immutable ProfileSnapshot → Cache → clients (read-only)
           │
           └── update command → validate → transaction → database
                                             │
                                             └── invalidate/update cache
~~~

**Do not let callers “mutate a cached entity to save it.”** Update methods should have an explicit contract, verify permissions, write to the database, and coordinate `@CacheEvict`/`@CachePut` or post-commit refresh according to system requirements. Read-only DTOs also reduce exposure of lazy-loading entities, persistence contexts, and internal state.

## 6. Why `@CacheEvict` or TTL alone is not enough

`@CacheEvict` and TTL address **entry lifecycle**; they do not protect a live object from in-place mutation.

For example, suppose a caller just executed `roles.add("admin")` and the TTL still has 30 minutes remaining: for those 30 minutes, requests hitting the same key may see the mutated state. Shortening the TTL narrows the window without guaranteeing every request is correct, while increasing source reads. Evicting after an **intentional** update reloads the true source, yet no annotation automatically detects arbitrary `List.add` calls by callers and evicts the key.

When the database changes, **even an immutable cached snapshot can become stale**. Hence both layers of protection are needed:

- **Immutability/copying:** prevents unintended side effects from callers on cached values.
- **Invalidation/expiration:** maintains freshness when the source of truth changes.

With `@CachePut`, if code updates the cache with a mutable object still held by the caller, that object can continue to be mutated **after the put** when the provider stores references. To stay safe, put immutable snapshots into the cache or copy at both the storage and return boundaries.

## 7. Advanced scenarios to review

### JPA entities and the persistence context

- Do not assume entities returned from `@Cacheable` remain managed by an EntityManager on every hit. Managed/detached state, lazy loading, and dirty checking change across transaction boundaries and depend on how the provider stores/restores values.
- Caching mutable JPA entities directly easily causes detached proxy errors, lazy access outside a session, unintended mutations, or returning state out of sync with the database.
- A common approach is mapping entities to immutable DTOs **before placing them in the cache**, rather than caching objects meant to be managed/mutated by the ORM.

### Key parameters can also be mutable

This lesson focuses on **values**, yet a related pitfall exists: if a mutable object is used as a **cache key** (especially in a hash-based map), mutating fields involved in `equals/hashCode` after `put` can cause lookups or evictions to fail. Use immutable keys such as `String`, `Long`, or a Java `record` with immutable components.

### Nested objects, arrays, Maps, and collection views

- `List.copyOf` does not deep-copy mutable elements.
- `Map.copyOf` does not deep-copy mutable values.
- `byte[]`/arrays always have mutable contents even if the reference is `final`; return `array.clone()` at boundaries when protection is required.
- `Collections.unmodifiableList(list)` blocks mutation **through the view**, not mutations made by whoever owns the original `list`.
- `Stream`/iterators over mutable collections can observe concurrent changes or throw exceptions; do not treat them as snapshots.

### Multi-tenancy and security

If an entry holds user- or tenant-specific authorization data, using a cache key with only `id` is already a separate bug. Shared mutable objects make the situation even more dangerous: one request can mutate an object used by another request. Keys must include all context that affects the result, and authorization must be enforced on the active call path **even on a cache hit**. Never treat a cache or a `roles` collection that might be mutated from a response as the authority for access control.

### Local cache, distributed cache, and multiple replicas

If the cache stores references in the JVM, two requests in the **same JVM** can share an object directly; another replica has its own local cache. A Redis serialized cache typically does not share the same Java object reference across JVMs, yet still faces stale data, out-of-sync eviction, serialization schema issues, and mutable objects at the application layer. Do not rely on an in-memory demo to conclude how another backend behaves.

### Object identity is not the value contract

In the demo, `first == second` is `true` to expose the bug. In real applications, `==` is not the sole criterion: a store-by-value backend can return two distinct instances with identical contents. Tests should check **contents after mutation**, **number of source loads**, and **business semantics**, not just identity.

## 8. Testing strategy

| Scenario | Action | Expected outcome |
| --- | --- | --- |
| Two reads of the same key | Call `@Cacheable` twice | First misses, second hits; source runs once. |
| Attempt to mutate immutable result | Call `snapshot.roles().add(...)` | `UnsupportedOperationException`; entry stays unchanged. |
| Mutate local mutable object | Call `mutable.roles().add(...)` | Demo reproduces cached object mutation to illustrate the risk. |
| Verify source of truth | After mutating mutable cache, read source independently | Source remains intact; do not confuse cache mutation with DB writes. |
| Valid data update | Call write service, evict/put appropriately | Next read gets fresh data; no staleness outside the contract. |
| Nested collection | Try mutating a field of a `List<Address>` element | Immutable DTO must protect elements too, not just the list. |
| Two concurrent requests | Multiple threads read/mutate the same value | No data race because the API does not expose shared mutable references. |
| Production backend | Run on Redis/Caffeine/JCache with real configuration | Verify actual copy behavior, serializer, object identity, and TTL. |
| Different key/tenant | Use the same ID across different tenants | No cross-tenant cache entry or state bleed. |

An integration test following this idea will catch unsafe designs:

~~~java
// Illustrates test logic, not a standalone file.
ProfileSnapshot first = service.snapshot("u1");
assertThrows(UnsupportedOperationException.class,
        () -> first.roles().add("admin"));
assertEquals(List.of("reader"), service.snapshot("u1").roles());
~~~

This is JUnit 5-style pseudocode; test dependencies and `assertThrows`/`assertEquals` imports are needed if added to a project. The Spring Boot demo in section 4 already provides a complete runnable path and corresponding stdout.

### Pre-merge checklist

1. [ ] Confirmed whether the `Cache`/provider stores references or values, rather than guessing from the word “cache”.
2. [ ] `@Cacheable` results are immutable snapshots or defensively copied at the appropriate boundaries.
3. [ ] All collections, arrays, and nested objects are evaluated for mutability; a record + mutable list is not yet safe.
4. [ ] Cached JPA entities are not returned directly for controllers to mutate when the business flow only needs a read model.
5. [ ] Write operations have a dedicated update path; evict/put/TTL and transaction boundaries are coordinated.
6. [ ] Cache is not used as an authorization mechanism; keys, tenants, and access checks are properly defined.
7. [ ] Tested cache hits/misses, caller mutation attempts, source data integrity, concurrent requests, and the real backend.
8. [ ] Monitored stale data, load counts, TTL, and consistency; high hit rate alone is not proof of correctness.

## Official Documentation

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — ConcurrentMapCache API (`isStoreByValue`): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html
- Spring Framework — Configuring Cache Storage: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
