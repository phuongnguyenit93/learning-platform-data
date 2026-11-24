# Spring Cache: Store-by-Reference and Store-by-Value

## 1. Why can the same cache key still produce different behaviors?

In the Spring Framework, `@Cacheable` can avoid re-executing a method by returning the value stored for a key. However, whether the cache **keeps the same Java object or creates a copy of the object** is not decided by the annotation; it depends on the cache provider and storage configuration.

Suppose a method returns a `Book` object with a mutable `title` property. A caller retrieves `Book("Original")` from the cache and then calls `setTitle("Edited")`. Will another caller accessing the same key see `Edited`? That is the difference between the two models:

- **Store-by-reference:** the cache holds a reference to the Java instance itself. With an internal cache in the same JVM, both the writer and the reader can hold a reference to that same object. Mutating the object can change the cache entry without any new `Cache.put` operation.
- **Store-by-value:** the cache stores a copy/snapshot and returns a copied value according to the backend's contract. A caller mutating the returned object does not alter the snapshot inside the cache. With Spring's `ConcurrentMapCacheManager`, this mode is implemented via Java serialization.

Illustration of the flow:

~~~text
STORE-BY-REFERENCE:
Caller A ------+
               v
          [Book instance X, title="Original"] <---- Cache["b1"]
               ^
Caller B ------+
Caller A mutates X.title="Edited"
=> Caller B reads the same object X and sees "Edited"


STORE-BY-VALUE:
Book X ("Original") -- copy on put --> Cache snapshot ("Original")
                                         |
                                      copy on get
                                         v
                                    Book Y ("Original")
                                    Caller mutates Y
=> Snapshot in cache remains "Original"
~~~

**Two important notes:** A cache hit is not required to return **the same object identity**; and having a snapshot does not mean that snapshot is up to date with the database. Both models still require managing cache invalidation and data lifecycle.

## 2. Comparing the storage mechanisms

| Criterion | Store-by-reference | Store-by-value |
| --- | --- | --- |
| Stored value | Reference to an instance in the JVM. | Copy/representation of the value. |
| Reading the same key | With an in-memory reference cache, may return the exact stored instance. | May reconstruct a new instance from the snapshot. |
| Caller mutates the returned object | May accidentally mutate the object in the cache. | Does not directly mutate the stored snapshot. |
| Caller mutates the object after `put` | May see the change on subsequent `get` calls. | The snapshot copied at store time does not change with the original object. |
| Cost | Little copying, low CPU/GC, suitable for immutable data. | Copying/serialization increases CPU, memory, allocations, and latency. |
| Limitations | Mutable aliasing, race conditions, silent mutations. | Serialization errors, complex object graphs, snapshots can still become stale. |
| Data in backend | Commonly used with local in-process caches. | May be a local copy or serialized data in a remote cache. |

Spring Cache only defines an **abstraction**. How `ConcurrentMapCache` stores entries does not automatically apply to Caffeine, Redis, or every JCache provider. When switching backends, check the specific semantics rather than assuming two `get` calls always return the same instance or always return a copy.

### 2.1. Shared reference and aliasing

Aliasing means multiple variables hold the same reference. Suppose `cache` is an `org.springframework.cache.Cache` using reference mode, and `Book` is a mutable class:

~~~java
Book book = new Book("Original");
cache.put("b1", book);
Book cachedBook = cache.get("b1", Book.class);

System.out.println(book == cachedBook); // true for a local reference-based cache
cachedBook.setTitle("Edited");
System.out.println(book.getTitle());    // Edited
~~~

This is **only a snippet**; it is not yet a standalone Java program. When `cache.put` does not copy the value, both the writer and the reader hold the same instance. Therefore, it is not only a caller mutating after `get` that causes changes; the writer mutating the original object **after `put`** can also affect the cache without actively updating the cache.

If the database still stores `Original` while the reference cache displays `Edited`, this is a change **out of sync with the data source**. Such a phenomenon can cause hard-to-reproduce bugs or make the system return inconsistent data.

### 2.2. Snapshot and copy-on-write/copy-on-read

A true store-by-value backend can create copies at the storage boundary and the retrieval boundary:

~~~text
T0: source object has title="Original"
T1: cache.put(key, object) -> stores snapshot="Original"
T2: source object changes to "Edited"
T3: cache.get(key) -> returns copy="Original"
T4: caller mutates copy to "Other"
T5: cache.get(key) -> new copy is still="Original"
~~~

Copying helps **isolate mutations on objects**, rather than tracking changes in the database. If the data source is validly updated, the old snapshot still needs to be evicted, replaced, or expired so subsequent reads retrieve fresh data.

### 2.3. Special case: a `@Cacheable` miss

In Spring Cache's synchronous flow, a miss executes the method, stores the value, and returns the newly created result. With `ConcurrentMapCache` in copy mode, storing creates a snapshot, yet the object returned **on the miss** is typically still the original object just returned by the method, not necessarily a deserialized copy.

This does not break isolation: mutating the object held by the caller **after the miss** does not mutate the snapshot stored via serialization. The next hit receives a different copy. The example in section 4 shows `value1 == value2` is `false`, even though both calls use the same key.

## 3. Configuring Spring's `ConcurrentMapCacheManager`

`ConcurrentMapCacheManager` is an in-process cache manager built on Java's concurrent map mechanism. It is suitable for demos or simple applications, and **does not provide TTL, persistence, or cross-JVM data synchronization by default**.

According to the Spring Framework 6.x Javadoc:

- `setStoreByValue(false)`: stores by reference; the **default** is `false`.
- `setStoreByValue(true)`: stores copies, using serialization for cache entries.
- `isStoreByValue()`: checks the currently configured mode.
- When store-by-value is enabled, values must be **serializable**.
- Changing the store-by-value setting after caches have been created can **reset existing caches**, so set it during initialization and do not toggle it arbitrarily while the system is running.

Spring configuration example:

~~~java
@Bean
ConcurrentMapCacheManager cacheManager() {
    ConcurrentMapCacheManager manager =
            new ConcurrentMapCacheManager("books");
    manager.setStoreByValue(true);
    return manager;
}
~~~

This snippet assumes it resides inside a `@Configuration` class with `@Bean` and `ConcurrentMapCacheManager` imported. It enables copy mode for the manager's caches; this is **not an attribute of `@Cacheable`**. There is no universal `@Cacheable(storeByValue=true)` flag across all providers.

### 3.1. What does serialization require?

For `ConcurrentMapCacheManager`'s copy mode, the value class generally needs to `implements java.io.Serializable`. Not only the outer object: related objects in the graph must also be serializable, or be handled with `transient`/custom serialization.

Potential issues include:

1. A field holding a non-`Serializable` object causes cache writes to fail.
2. `transient` fields are not serialized, so the restored object may lack expected data.
3. Objects holding sockets, threads, file handles, DB connections, or lazy-loading proxies are usually not suitable cache values.
4. Overly large object graphs make serialization/deserialization costly in time and memory.
5. If a backend stores serialized data across multiple deployment versions, schema/class changes can cause compatibility errors; explicit versioning rules are required.

`Serializable` **does not make an object immutable**. It only allows the provider to copy/represent state according to its corresponding mechanism.

## 4. Java 17+ and Spring Boot 3 example: same key, different modes

The application below creates **two separate managers**:

- `referenceCacheManager` manages the `byReference` region with `storeByValue=false`.
- `copyCacheManager` manages the `byValue` region with `storeByValue=true`.

Both methods take ID `"b1"` and create a `MutableBook("Original")` object on a miss. The program then mutates the returned instance and calls the method again. `MutableBook` implements `Serializable` so the copy cache can use Java serialization.

**File `build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

**File `src/main/java/demo/StoreSemanticsApplication.java`:**

~~~java
package demo;

import java.io.Serial;
import java.io.Serializable;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@SpringBootApplication
@EnableCaching
public class StoreSemanticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(StoreSemanticsApplication.class, args);
    }

    @Bean("referenceCacheManager")
    @Primary
    CacheManager referenceCacheManager() {
        ConcurrentMapCacheManager manager =
                new ConcurrentMapCacheManager("byReference");
        manager.setStoreByValue(false);
        return manager;
    }

    @Bean("copyCacheManager")
    CacheManager copyCacheManager() {
        ConcurrentMapCacheManager manager =
                new ConcurrentMapCacheManager("byValue");
        manager.setStoreByValue(true);
        return manager;
    }

    @Bean
    BookService bookService() {
        return new BookService();
    }

    @Bean
    CommandLineRunner demo(BookService service) {
        return args -> {
            MutableBook ref1 = service.loadReference("b1");
            System.out.println("ref first = " + ref1.title());

            ref1.rename("Edited by caller");
            MutableBook ref2 = service.loadReference("b1");
            System.out.println("ref same instance = " + (ref1 == ref2));
            System.out.println("ref second = " + ref2.title());

            MutableBook value1 = service.loadValue("b1");
            System.out.println("value first = " + value1.title());

            value1.rename("Edited by caller");
            MutableBook value2 = service.loadValue("b1");
            System.out.println("value same instance = "
                    + (value1 == value2));
            System.out.println("value second = " + value2.title());

            value2.rename("Edited after hit");
            MutableBook value3 = service.loadValue("b1");
            System.out.println("value third = " + value3.title());
        };
    }

    public static class BookService {
        @Cacheable(
                cacheNames = "byReference",
                cacheManager = "referenceCacheManager",
                key = "#p0")
        public MutableBook loadReference(String id) {
            System.out.println("LOAD reference " + id);
            return new MutableBook("Original");
        }

        @Cacheable(
                cacheNames = "byValue",
                cacheManager = "copyCacheManager",
                key = "#p0")
        public MutableBook loadValue(String id) {
            System.out.println("LOAD value " + id);
            return new MutableBook("Original");
        }
    }

    public static final class MutableBook implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private String title;

        public MutableBook(String title) {
            this.title = title;
        }

        public String title() {
            return title;
        }

        public void rename(String newTitle) {
            this.title = newTitle;
        }
    }
}
~~~

**How to run:** use `./gradlew bootRun` if the project has the Gradle Wrapper (Windows: `gradlew.bat bootRun`), or `gradle bootRun` if a compatible Gradle version is installed. JDK 17+ is required, and dependencies are downloaded on the first run. The Gradle/Spring Boot versions here are illustrative; production projects should choose supported releases with security updates.

Ignoring Spring Boot's startup banner and logs, **the lines explicitly printed by the demo** in order are:

~~~text
LOAD reference b1
ref first = Original
ref same instance = true
ref second = Edited by caller
LOAD value b1
value first = Original
value same instance = false
value second = Original
value third = Original
~~~

**Line-by-line explanation:**

1. The first call to `loadReference("b1")` misses, creates `MutableBook("Original")`, and stores the same instance in the `byReference` cache.
2. `ref1.rename(...)` changes the title of the cached instance. The second call hits, `ref1 == ref2` is `true`, and the title shows `Edited by caller`. There is no additional `LOAD reference b1`.
3. The first call to `loadValue("b1")` misses and creates the `Original` object; the copy manager stores a serializable snapshot.
4. The caller mutates `value1` after the miss. The snapshot remains `Original`. The second hit deserializes into a different object: `value1 == value2` is `false`.
5. The caller mutates `value2` after the hit and calls again. `value3` again receives the title `Original` because the cache still holds the snapshot; there is no second `LOAD value b1`.

The two different cache names are intentional: the same key `"b1"` does not mean the two cache regions share entries. The `@Cacheable` methods specify `cacheManager` by bean name; `@Primary` designates the default manager when Spring needs to resolve multiple candidates. `CommandLineRunner` invokes through the Spring-managed `BookService` so the cache interceptor works; internal self-invocation via `this.loadValue(...)` inside the same service would bypass the proxy in standard proxy mode.

The `==` comparison in this example only illustrates **identity in the `ConcurrentMapCache` implementation**. Do not treat `==` as a general check across all cache providers: immutable objects may be reused, and serializers and copy mechanisms may differ.

## 5. How does a “copy” differ from reassigning a variable or a shallow copy?

| Operation | Does it separate the objects? |
| --- | --- |
| `Book b = a;` | No, only copies the reference. |
| Creating a shallow copy sharing the same internal mutable list | Outer object differs, but nested lists can still be shared. |
| Copying via appropriate serialization | Can reconstruct a serializable object graph as a new object. |
| Immutable DTO | No copying is needed to prevent callers from mutating state if all observable state is immutable. |

A `Book` object with a `List<Chapter>` field: if you only clone the outer layer while keeping the same `List` or mutable `Chapter` objects, mutating nested objects can still affect the original. Your handling must consider **the entire object graph**, not just the top-level reference.

With Java 17+, an immutable DTO can be:

~~~java
public record BookView(String id, String title)
        implements java.io.Serializable {
}
~~~

This is a **syntactically standalone Java snippet** that should be placed in `BookView.java` if used at top level. When it consists solely of immutable `String` fields, sharing an instance generally carries little risk. For records containing collections or mutable components, a record is only **shallowly** immutable; defensively copy collections (for example, `List.copyOf`) and use immutable elements.

Another option is a `final` class DTO with `final` fields, no setters, and validation upon construction. “Immutable by design” is usually clearer than expecting every consumer to remember not to mutate objects from the cache.

## 6. Performance, concurrency, and data lifecycle

### 6.1. A thread-safe map does not mean thread-safe values

`ConcurrentMapCache` is built on a concurrent map structure. Operations to put/get entries are synchronized according to the map's mechanics, but **mutable objects sitting inside the value are not automatically protected from race conditions**.

For example, one thread reads two fields `price` and `currency` from a shared object while another thread updates them in two steps. The reading thread can observe values from inconsistent versions if there is no synchronization or immutable snapshot. Do not use store-by-reference for broadly shared mutable objects without a thread-safety contract.

Store-by-value gives each caller its own copy, reducing the chance that one caller's mutation immediately affects another caller. However, serializing a snapshot while another thread **is actively mutating the source object** does not guarantee consistency either: you must construct the snapshot from a stable state.

### 6.2. Copy overhead

Store-by-reference saves CPU and allocations because it avoids serializing on every cache get/put. Store-by-value can increase CPU, memory, GC pressure, latency, and serialized payload size. If the object graph is large or the hit rate is high, this cost can erode caching performance gains. Benchmark with realistic data and monitor hit rate, latency, throughput, and GC.

Choosing an **immutable DTO + local reference cache** is often a strong option when performance is a priority, while still requiring proper TTL and invalidation management.

### 6.3. Copying does not mean data is always fresh

~~~text
T0: Database title="Original"; cache snapshot="Original"
T1: Database is updated to "Updated"
T2: Cache hit -> still returns "Original" if there has been no invalidation
T3: @CacheEvict on the right key or @CachePut stores the new value
T4: Read again -> "Updated" per caching logic
~~~

Store-by-value protects the snapshot from caller-side object mutation, but the snapshot can still be **stale** relative to the data source. Store-by-reference does not automatically handle external database changes either; sometimes it merely makes the cache look fresh because someone mutated a shared object, even though the database has not committed.

Policies for `@CacheEvict`, `@CachePut`, TTL, multi-instance synchronization, and transaction commit timing must be designed independently of store-by-value semantics. A local `ConcurrentMapCacheManager` does not share entries across JVMs.

### 6.4. Mutable keys are a separate problem

If a mutable object is used as a cache key, mutating a property involved in `equals` or `hashCode` after inserting it into a hash map can cause incorrect lookups or make the entry unreachable. Copying the **value** does not fix a mutable key. Prefer stable IDs such as `String`, `UUID`, or immutable key records with consistent `hashCode`/`equals`.

## 7. Do not generalize arbitrarily to other cache providers

| Provider / model | What to verify |
| --- | --- |
| Spring `ConcurrentMapCacheManager` | Defaults to store-by-reference; enable copying with `setStoreByValue(true)` and require serializability. |
| Typical local Caffeine | Usually holds the same object in the JVM; do not assume every `get` automatically deep-copies. |
| Redis / remote serialized cache | Data typically goes through a serializer over the network; Java objects in two processes cannot directly share local references. |
| JCache (JSR-107) / other backends | Check the `storeByValue` configuration, implementation, serializer, and respective contract. |

Remote serialization typically causes two reads to reconstruct two distinct Java instances, yet that **does not prove the data is fresh**. If Redis holds an old snapshot, deserializing it any number of times still returns the old value. When switching providers, test serialization, schema compatibility, TTL, eviction, and behavior when the backend loses connectivity.

## 8. Common pitfalls and fixes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| A caller mutates a cached object and others see the change with no database write. | Shared reference to a mutable value. | Use immutable DTOs, defensive copies, or store-by-value. |
| Enabling store-by-value causes cache operations to fail. | Value or nested field is not serializable. | Cache an appropriate serializable DTO; inspect the object graph and transient fields. |
| A caller mutates an object after a cache hit, but subsequent calls do not show the update. | Only the copy was mutated without writing to the source or updating the cache. | Update the authoritative source alongside `@CachePut` or `@CacheEvict`. |
| Cache reads still return stale data even with copying enabled. | Snapshots do not track database changes automatically. | Configure TTL, eviction, or key-accurate updates, accounting for transactions. |
| Local cache is thread-safe, yet values get overwritten or have mixed state. | The map is thread-safe, but mutable value objects are not. | Use immutable snapshots, synchronization, or clear ownership rules. |
| Changing `setStoreByValue` at runtime makes entries disappear. | The manager resets caches to change mode. | Configure at startup; plan changes intentionally. |
| A previously used key suddenly cannot be found. | A mutable key changed its `hashCode/equals`. | Use immutable keys with clear identifiers. |
| Remote cache returns a new object every time, yet values are still wrong. | Deserialization reconstructs objects from an old snapshot. | Verify the source data and invalidation logic. |

## 9. Implementation checklist and self-check

**Practical checklist:**

1. Verify the actual backend in use and the provider's documentation on reference/value semantics rather than relying solely on annotations.
2. Call a `@Cacheable` method twice with the same key; distinguish hits from misses via method-body logs.
3. After a miss, mutate the returned object and read again; observe both state and object identity.
4. After a hit, mutate the returned object and read a third time; verify snapshot isolation.
5. If using copy mode, test nested objects, nulls, transient fields, and the serializable contract.
6. When source data changes, verify the `@CacheEvict`/`@CachePut` path or TTL.
7. Test with multiple threads to detect shared mutable values, and measure latency/GC under copy mode.

**Question 1:** Why is `ref1 == ref2` `true` in the demo?

**Answer:** Because `ConcurrentMapCacheManager` in reference mode stores and retrieves the same Java object in the JVM, and the same key `b1` resolves to the same entry.

**Question 2:** Why does mutating `value1` after a miss not alter the data on a cache hit?

**Answer:** While handling the miss, the cache serialized a copy of the original value. Mutating `value1` does not modify that snapshot; the subsequent hit deserializes an independent copy.

**Question 3:** Does enabling `setStoreByValue(true)` solve stale cache data?

**Answer:** No. Copying only isolates object mutations; changes to the source data still require TTL, eviction, or appropriate cache updates.

**Question 4:** Does a thread-safe `ConcurrentHashMap` automatically make `MutableBook` inside it thread-safe?

**Answer:** No. The map's thread safety does not protect mutable fields on the value object.

**Question 5:** Can a non-`Serializable` object be used with copy mode in `ConcurrentMapCacheManager`?

**Answer:** Not with this default serialization mechanism; you need a serializable value/object graph or a different storage/provider design.

**Key Takeaway:** In Spring Cache, how keys are chosen and how values are stored are two separate concerns. With `ConcurrentMapCacheManager`, **store-by-reference is the default**, whereas **store-by-value must be enabled and incurs serialization overhead**. Prefer immutable objects, design key-accurate invalidation, and verify backend behavior before going to production.

## References

- [Spring Framework 6.2 — ConcurrentMapCacheManager Javadoc](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html).
- [Spring Framework 6.2 — ConcurrentMapCache Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html).
- [Spring Framework — Configuring the Cache Storage](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html).
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html).
