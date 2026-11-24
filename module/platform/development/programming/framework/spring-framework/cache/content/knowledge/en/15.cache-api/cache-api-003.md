# Cache.ValueWrapper and the Typed get Variant in Spring Cache

## Objectives

When working directly with **org.springframework.cache.Cache**, there are two read methods that are easily confused:

- **Cache.ValueWrapper get(Object key)**: returns a *wrapper* if the key has an entry; returns **null** if the key has no entry. The wrapper itself may still hold a **null value**.
- **<T> T get(Object key, Class<T> type)**: returns the value checked against the requested runtime type; returns **null** if there is no entry **or** if the entry has a null value. Therefore, this API **does not distinguish those two cases**.

Spring also provides **<T> T get(Object key, Callable<T> valueLoader)** to *read or load on miss*. This is a different overload: the second parameter is a **loader function**, not **Class<T>**. This lesson dives into the differences, null handling, type safety, exceptions, the null sentinel, generic pitfalls, and a runnable example on Java 17.

After this lesson, you will be able to:
1. Accurately distinguish **MISS**, **HIT with null**, and **HIT with a non-null value** using Cache.ValueWrapper.
2. Choose **get(key, User.class)** when you only want a type-safe value and do not need to distinguish missing from cached-null.
3. Explain when **IllegalStateException** occurs if an entry does not match the type, and why generic `List<User>` is not checked by `List.class`.
4. Know that `get(key, Callable<T>)` **is not a typed-get**, and understand load-on-miss and `Cache.ValueRetrievalException`.
5. Understand `ConcurrentMapCacheManager.setAllowNullValues(true/false)`, the effect of a null cache entry, and differences from Java `Map.get`.
6. Run the demonstration program yourself with **JDK 17 + Spring Framework 6.2.19** to inspect each state.

Context: Spring Cache Abstraction, using the **programmatic Cache API** instead of relying solely on the `@Cacheable` annotation. The example uses **ConcurrentMapCacheManager** within a single JVM; null and concurrency policies of other providers must be verified separately.

---

## 1. A cache entry has three observable states

For key `user:42`, the logical state can be:

| State | Mapping exists for key? | Logical value of entry |
| --- | --- | --- |
| **MISS** | No | No value |
| **HIT–NULL** | Yes | `null` |
| **HIT–VALUE** | Yes | Non-null object, e.g., `User("42","Lan")` |

Why distinguish them? In an application, `null` is sometimes a **valid business result**, such as "looked up and confirmed no record exists" (negative caching). A key that has never been looked up has **no entry**. If they are conflated, code may reload data even though a null result was already cached, or assume a value is cached when the key does not exist at all.

**Cache.ValueWrapper** is designed to separate **the presence of an entry** from **the value inside the entry**.

~~~text
cache.get(key)   // single-parameter overload
       |
       +-- returns Java null     => No mapping / MISS
       |
       +-- returns ValueWrapper  => Mapping exists / HIT
                  |
                  +-- wrapper.get() == null  => cached-null
                  |
                  +-- wrapper.get() != null  => cached-value
~~~

**Note:** `Cache.ValueWrapper` is a nested interface inside `Cache`, not a generic type `ValueWrapper<T>`. The wrapper's `get()` method returns **Object**, so you need to check the type or cast appropriately.

## 2. get(key): checking ValueWrapper properly

Declaration in the Cache interface (nullable annotations simplified):

~~~java
Cache.ValueWrapper get(Object key);
~~~

Contract:
- **Returns null**: no corresponding mapping exists (cache miss).
- **Returns a ValueWrapper**: an entry exists, even when the cached logical value is null.
- **wrapper.get()**: returns the payload after Spring/the provider converts from the store representation back to the application value; the payload may be null.

Handling code should start by **checking the wrapper**, not calling wrapper.get() right away:

~~~java
Cache.ValueWrapper wrapper = cache.get("user:42");

if (wrapper == null) {
    System.out.println("MISS");
} else if (wrapper.get() == null) {
    System.out.println("HIT_NULL");
} else {
    System.out.println("HIT_VALUE=" + wrapper.get());
}
~~~

This is an **illustrative snippet**, with the `cache` variable already assigned a Spring Cache. Note that `wrapper == null` and `wrapper.get() == null` are **two different conditions**.

### Wrong: dereferencing the wrapper directly

~~~java
// WRONG if the key has not been stored yet:
Object result = cache.get("missing").get();
~~~

When `get("missing")` returns null, the statement throws a **NullPointerException** before retrieving the payload. Fix: check the wrapper for null first.

### Wrong: inspecting only the payload to conclude a miss

~~~java
// Semantically WRONG if the cache allows cached-null:
Cache.ValueWrapper wrapper = cache.get("user:42");
Object value = wrapper == null ? null : wrapper.get();

if (value == null) {
    // Cannot confirm this is a MISS.
}
~~~

Here `value == null` could mean **no mapping exists** or **a mapping containing null exists**. If business decisions need to know both states, retain the information from the wrapper.

### Building a clearer result type yourself

For larger logic, you can convert the read state into a simple domain type:

~~~java
// Java 17 illustrative snippet; members belong inside an appropriate class.
enum LookupState { MISS, HIT_NULL, HIT_VALUE }

static LookupState stateOf(Cache cache, Object key) {
    Cache.ValueWrapper w = cache.get(key);
    if (w == null) return LookupState.MISS;
    return w.get() == null
        ? LookupState.HIT_NULL
        : LookupState.HIT_VALUE;
}
~~~

There is no need to access `getNativeCache()` or a custom sentinel to distinguish the three states. This is why Spring Cache provides the wrapper.

**Note on concurrency:** `stateOf` reflects the state observed at the moment `get` returns. Another thread may `put` or `evict` immediately afterward. A wrapper read is not a transaction or a long-lived guaranteed snapshot.

## 3. get(key, Class<T>): retrieving a value with runtime type checking

Equivalent declaration:

~~~java
<T> T get(Object key, Class<T> type);
~~~

Example:

~~~java
User user = cache.get("user:42", User.class);
~~~

This is an illustrative snippet; `User` and `cache` must be defined by the application. Spring returns:
- `User` if the entry contains a value compatible with `User.class`.
- `null` if **there is no entry**.
- `null` if there is an entry but the stored logical value is **null**.
- **IllegalStateException** if the entry exists, the value is non-null, and it **does not match the requested type**.

The typed get API is convenient when code only needs a properly typed object and does not need to distinguish hit-null from miss. It is **not** a call that triggers loading from the database on a cache miss.

### Two different get calls, same key

~~~java
Cache.ValueWrapper raw = cache.get("user:42");
User typed = cache.get("user:42", User.class);
~~~

If the entry holds `null`:
- `raw` is **non-null**, `raw.get()` is null.
- `typed` is null.

If there is no entry:
- `raw` is null.
- `typed` is also null.

Thus **typed get discards an important bit of information: whether the entry exists**. If you need *negative caching* or existence checks, prefer the wrapper.

### On type mismatch: IllegalStateException, not a miss

For example, the cache stores `User` but the caller requests `String`:

~~~java
cache.put("user:42", new User("42", "Lan"));
String text = cache.get("user:42", String.class);
// IllegalStateException: value is incompatible with String.class.
~~~

This snippet is illustrative and requires the User class/record and cache variable. Do not write:

~~~java
// Conceptually WRONG: treating all type errors as a cache miss.
try {
    return cache.get(key, String.class);
} catch (IllegalStateException ignored) {
    return loadAndOverwriteFromSource(key);
}
~~~

This is intentionally incomplete illustrative code. A type mismatch error usually indicates a **conflict between the cache schema and the cache-consuming logic**: sharing the same cacheName/key for different types, stale versioned data, wrong serializer/config, or unchecked casts. Catching it and blindly reloading can mask bugs and overwrite another workflow's entry.

**Type checking does not mean safe deserialization.** In a distributed cache, the provider may fail right during deserialization or value conversion, even before typed get performs the Class check. Test on the actual provider.

### Class<T> does not deeply check generic parameters

~~~java
// List.class only represents the runtime type List, not List<User>.
List<?> items = cache.get("users:list", List.class);
~~~

If the entry actually contains `List<String>`, it is still a `List` at runtime. `List.class` **does not detect** that the caller wanted `List<User>`. Information about `<User>` is removed by **type erasure** in Java, so you cannot write `List<User>.class`.

If you need to guarantee each element is a User, validate the elements yourself, use a strongly typed wrapper DTO, or let the serializer/type metadata handle it in a dedicated layer.

### type can be null, but should not be abused

Spring's contract allows the `Class<T> type` parameter to be null to **skip type checking**:

~~~java
Object value = cache.get("user:42", (Class<Object>) null);
~~~

This illustrates a semantically valid API call; in modern Java, it is usually more readable and safer to pass an actual `Class` or use the wrapper. `type=null` does **not** make the cache infer a generic type from the left-hand side variable assignment. It only skips the runtime type verification step.

**A notable overload error:** `cache.get(key, null)` may fail to compile because Java cannot tell whether to choose the `Class<T>` or `Callable<T>` overload. Specify the type/cast explicitly if truly intentional; best not to pass an ambiguous null.

## 4. Decision table: wrapper or typed get?

| Purpose | Choose API | Reason |
| --- | --- | --- |
| Need to know if a key has an entry | **get(key)** | A null wrapper means miss |
| Need to distinguish cached-null from miss | **get(key)** | Wrapper is present even if payload is null |
| Only want a valid `User` or null | **get(key, User.class)** | Checks type and returns directly |
| Need to detect wrong-typed values | **get(key, Class<T>)** | Throws IllegalStateException on mismatch |
| Want to deeply check `List<User>` | **Insufficient with get(key, List.class)** | Class only checks raw List |
| Want to compute a value on miss | **get(key, Callable<T>)** | Dedicated loader overload |
| Want to prevent duplicate loads in the cache provider | **get(key, Callable<T>)** + check provider | Some implementations coordinate the loader atomically |
| Want to handle asynchronous retrieval | **retrieve(...)** if provider supports it | Different API, CompletableFuture result |

All variants require **the right cacheName and key**. Typed get does not automatically pick the right cache and does not create a new entry without a loader.

## 5. How is null stored in ConcurrentMapCache?

A standard `ConcurrentHashMap` **does not allow null values**. However, Spring's `ConcurrentMapCacheManager` **allows logical null values by default** by storing an **internal placeholder value** (a null sentinel, typically based on NullValue) in the map and converting it back when returning through the Cache API.

With default configuration:

~~~java
ConcurrentMapCacheManager manager =
    new ConcurrentMapCacheManager("users");

Cache cache = manager.getCache("users");
cache.put("u:null", null);

Cache.ValueWrapper wrapper = cache.get("u:null");
// wrapper != null, wrapper.get() == null.
~~~

The illustrative snippet assumes no Cache initialization error and `manager.getCache("users")` is non-null. In the runnable example below, we use `Objects.requireNonNull` to check explicitly.

**Why not return null directly when the cache has a cached-null?** Because if raw Java null were returned, the caller could not distinguish "key does not exist" from "key exists containing null". Spring uses ValueWrapper to preserve that distinction in the single-argument overload.

### Disabling null caching

~~~java
ConcurrentMapCacheManager manager =
    new ConcurrentMapCacheManager("users");
manager.setAllowNullValues(false);
~~~

With `allowNullValues=false`, the cache does not accept storing null through that mechanism; depending on the call path, attempting to put null may result in an error or be handled by specific integration rules. **Do not assume `put(key, null)` will silently delete the entry**.

Remember:
- `setAllowNullValues(true)` **is the default of ConcurrentMapCacheManager**, not a mandatory property of every cache provider.
- Changing the null configuration on this manager may **reset already-created caches** to apply the new policy; do not perform this operation arbitrarily in production.
- Another provider may not support caching null, or may have its own serialization/negative caching rules.
- `get(key, User.class)` still returns null for both **cached-null** and **miss**, regardless of how the implementation stores the internal sentinel.

### Cached-null is not the same as Optional.empty()

Some applications prefer storing `Optional.empty()` or a domain value such as `NotFound`. Those are **non-null objects** at the Java API level, different from storing `null`.

If using `Optional<User>` as the return type of `@Cacheable`, Spring annotation caching has its own adaptation rules for Optional. Do not assume `Cache.put(key, Optional.empty())`, `Cache.put(key, null)`, and `@Cacheable` returning Optional.empty are stored identically across every provider. Design and test directly against the abstraction/annotation you use.

## 6. The third API: get(key, Callable<T> valueLoader)

Besides the two main overloads, Cache has:

~~~java
<T> T get(Object key, java.util.concurrent.Callable<T> valueLoader);
~~~

Contract:
1. If the key already has a valid mapping, return the cached value.
2. On miss, invoke `valueLoader.call()` to compute the value.
3. Store the loader's result in the cache according to provider capabilities, then return the result.
4. If the loader throws an exception, the Spring Cache API provides **Cache.ValueRetrievalException** wrapping the source error.
5. Coordinating concurrent loads for the same key depends on the implementation; do not treat this as a distributed lock protecting an entire workflow.

Example:

~~~java
AtomicInteger loads = new AtomicInteger();

String first = cache.get("greeting", () ->
    "hello-" + loads.incrementAndGet());

String second = cache.get("greeting", () ->
    "hello-" + loads.incrementAndGet());
~~~

In a normally functioning cache without eviction/concurrent writers, both `first` and `second` are "hello-1"; the loads counter is 1. **This is not a Class<T>-checking overload**: the compiler infers T from Callable, but at runtime no `Class<T>` is passed to verify the cached type like typed get.

### When does the loader not run?

If an entry already exists, including a **cached-null** entry in a null-supporting provider, the loader may **not be called**. This preserves negative caching. Do not write code assuming `get(key, Callable)` will invoke the loader again whenever the returned result is null.

### If the loader throws a checked exception

~~~java
try {
    cache.get("remote", () -> {
        throw new java.io.IOException("Remote service down");
    });
} catch (Cache.ValueRetrievalException ex) {
    Throwable root = ex.getCause();
    // Handle root or classify infrastructure errors here.
}
~~~

Illustrative snippet. In concurrent implementations or remote providers, cache store/network errors may not be represented the same way as errors from valueLoader; distinguish exceptions from the **loader** from errors from the **cache provider**.

### Relationship to @Cacheable(sync=true)

When the `@Cacheable(sync=true)` annotation is used, the Spring cache interceptor asks the Cache implementation to coordinate loading for the same key via the appropriate loader APIs. However:
- Not every provider guarantees single-flight equally.
- It does not serialize `@CachePut`, `@CacheEvict`, and database transactions.
- `@Cacheable(sync=true)` has its own annotation restrictions (e.g., cannot be combined with `unless`); do not apply those restrictions to all programmatic `get(key, Callable)` calls.

## 7. Runnable Java 17 example: observing all three states and all three overloads

The following example **does not require Spring Boot**, nor `@EnableCaching`, because we call the **Cache API directly**. Using CacheManager from Spring Framework only requires adding the `spring-context` dependency in Maven.

### 7.1. Directory structure

~~~text
cache-get-variants/
├── pom.xml
└── src/main/java/demo/CacheGetVariantsDemo.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cache-get-variants</artifactId>
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

### 7.3. src/main/java/demo/CacheGetVariantsDemo.java

~~~java
package demo;

import org.springframework.cache.Cache;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;

import java.io.IOException;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public class CacheGetVariantsDemo {

    public record User(String id, String name) {}

    public static void main(String[] args) {
        ConcurrentMapCacheManager manager =
            new ConcurrentMapCacheManager("users");
        manager.setAllowNullValues(true);

        Cache cache = Objects.requireNonNull(
            manager.getCache("users"), "Cache 'users' not found");

        cache.put("u1", new User("u1", "Lan"));
        cache.put("nil", null); // True cached-null.
        // Do not put key "missing" -> MISS.

        Cache.ValueWrapper wrappedUser = cache.get("u1");
        Cache.ValueWrapper wrappedNull = cache.get("nil");
        Cache.ValueWrapper wrappedMissing = cache.get("missing");

        System.out.println("raw-user-present="
            + (wrappedUser != null));
        System.out.println("raw-user-value="
            + wrappedUser.get());
        System.out.println("raw-null-present="
            + (wrappedNull != null));
        System.out.println("raw-null-payload="
            + wrappedNull.get());
        System.out.println("raw-missing=" + wrappedMissing);

        System.out.println("typed-user="
            + cache.get("u1", User.class));
        System.out.println("typed-null="
            + cache.get("nil", User.class));
        System.out.println("typed-missing="
            + cache.get("missing", User.class));

        try {
            cache.get("u1", String.class);
            System.out.println("typed-wrong=unexpected");
        } catch (IllegalStateException ex) {
            System.out.println("typed-wrong="
                + ex.getClass().getSimpleName());
        }

        AtomicInteger computeCount = new AtomicInteger();
        String computed1 = cache.get("computed", () ->
            "computed-" + computeCount.incrementAndGet());
        String computed2 = cache.get("computed", () ->
            "computed-" + computeCount.incrementAndGet());

        System.out.println("computed-1=" + computed1);
        System.out.println("computed-2=" + computed2);
        System.out.println("compute-calls="
            + computeCount.get());

        AtomicInteger nullLoaderCount = new AtomicInteger();
        String fromCachedNull = cache.get("nil", () -> {
            nullLoaderCount.incrementAndGet();
            return "should-not-run";
        });
        System.out.println("cached-null-loader="
            + fromCachedNull);
        System.out.println("cached-null-loader-calls="
            + nullLoaderCount.get());

        try {
            cache.get("error", () -> {
                throw new IOException("boom");
            });
            System.out.println("loader-error=unexpected");
        } catch (Cache.ValueRetrievalException ex) {
            System.out.println("loader-error="
                + ex.getCause().getClass().getSimpleName());
        }

        cache.evict("nil");
        System.out.println("after-evict-null="
            + cache.get("nil"));
    }
}
~~~

**Characteristics of the example:**
- `cache.put("nil", null)` is accepted because the manager supports cached-null. Even though the underlying ConcurrentHashMap does not store Java null directly, the API returns a wrapper with a null payload.
- Record `User` has a stable auto-generated `toString()` formatted as `User[id=..., name=...]`.
- Mismatched typed get `String.class` is caught as `IllegalStateException`.
- Two `get("computed", Callable)` calls without intervening writers/evict result in the loader running once.
- `get("nil", Callable)` does not run the loader because the key has a cached-null; the result remains null.
- The loader throwing `IOException` is represented via `Cache.ValueRetrievalException`; `getCause()` is IOException.
- After `evict("nil")`, the single-parameter overload returns Java null because the entry is gone.

### 7.4. Run command

From the directory containing `pom.xml` (with JDK 17+ and Maven installed):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheGetVariantsDemo
~~~

**Stdout produced by the program's System.out.println calls** (excluding Maven or library logs):

~~~text
raw-user-present=true
raw-user-value=User[id=u1, name=Lan]
raw-null-present=true
raw-null-payload=null
raw-missing=null
typed-user=User[id=u1, name=Lan]
typed-null=null
typed-missing=null
typed-wrong=IllegalStateException
computed-1=computed-1
computed-2=computed-1
compute-calls=1
cached-null-loader=null
cached-null-loader-calls=0
loader-error=IOException
after-evict-null=null
~~~

### 7.5. Reading the output according to Cache API semantics

1. **raw-user-present=true**: `get("u1")` has a ValueWrapper because the key was put. Payload is the User record.
2. **raw-null-present=true** along with **raw-null-payload=null**: key `nil` is **HIT–NULL**, not a miss.
3. **raw-missing=null**: the key has never been put, so the wrapper itself is null.
4. **typed-null=null** and **typed-missing=null**: typed get conflates both states, per the API contract.
5. **typed-wrong=IllegalStateException**: Spring detects that the User value is incompatible with type String.
6. **compute-calls=1**: the loader runs on the first miss; the second call receives the cached value.
7. **cached-null-loader-calls=0**: with a cached-null having a valid mapping, the provider does not call the loader even though the returned value is null.
8. **loader-error=IOException**: IOException is the root cause inside ValueRetrievalException.
9. **after-evict-null=null**: after deleting the key, single-parameter `get("nil")` shows a miss.

This example uses an in-memory cache **in a single thread and creates no concurrent race**. With Redis, JCache, or other providers, verify null handling, serialization, and their own error contracts; do not use this output to assert all providers behave identically in internal details.

## 8. When to use the Cache API directly vs. annotations?

Spring Cache has two common approaches:

**1. Declarative approach using annotations**:

~~~java
@Cacheable(cacheNames = "users", key = "#p0")
public User findById(String id) {
    return repository.findById(id);
}
~~~

This is an illustrative method, not standalone. The Spring cache interceptor handles lookup and putting the result based on the annotation, provided `@EnableCaching` is configured and calls pass properly through the Spring proxy. Business code does not need to call `Cache.get` or `Cache.put` directly.

**2. Programmatic approach via the Cache API**:

~~~java
Cache users = Objects.requireNonNull(
    cacheManager.getCache("users"));

Cache.ValueWrapper wrapper = users.get(id);
if (wrapper != null) {
    return (User) wrapper.get();
}
User result = repository.findById(id);
users.put(id, result);
return result;
~~~

This is an illustrative example that needs a surrounding class context, the `id` variable, `cacheManager`, repository, and valid casts. It **does not automatically synchronize** the entire check–load–put sequence across threads. In real systems, `get(key, Callable)` can simplify load-on-miss and provide provider-level coordination, though you must still consider types/nulls/concurrency.

**Choose annotations** if the cache operation aligns with a method boundary, key/condition rules are fairly clear, and you want to separate cross-cutting concerns from business code. **Choose the Cache API** if you need to make decisions based on the wrapper, manage negative caches, invalidate a specific key, or actively control multi-step caching.

### A mistake: using Cache.get without controlling cacheName/key

~~~java
Cache cache = cacheManager.getCache("users");
Cache.ValueWrapper wrapper = cache.get(id);
~~~

Whether using the wrapper or typed get, data only matches if **cacheName** and **key** match where the producer called `put`. If `@Cacheable` uses SpEL key `#p0.toLowerCase()` while programmatic code uses the raw input string, it will miss even though the entry exists under another key.

Similarly, if the producer uses `@CacheConfig(cacheManager="redisManager")` while programmatic code reads `localManager`, the two sides may access two different stores. The wrapper cannot fix cache identification mistakes on its own.

## 9. Common errors and how to fix them

### Error 1: `cache.get(key).get()` throws NullPointerException

**Cause:** key missed, so ValueWrapper is null.

**Fix:**

~~~java
Cache.ValueWrapper w = cache.get(key);
if (w == null) {
    // Miss -> can load or return absent.
} else {
    Object payload = w.get(); // Payload can still be null.
}
~~~

### Error 2: `get(key, User.class) == null` is assumed to definitely be a miss

**Cause:** typed get does not distinguish cached-null from miss.

**Fix:** Use `Cache.ValueWrapper` to detect entry presence; or design a dedicated business marker/DTO if you do not want to cache null.

### Error 3: Type mismatch is swallowed as a cache miss

**Cause:** the same cacheName/key is used by multiple data types, or cached entries persist after code/schema changes.

**Fix:** fix the key namespace and type contract, plan versioning/invalidation on deployment; avoid catching IllegalStateException and silently overwriting the entry.

### Error 4: Believing `List.class` checks `List<User>`

**Cause:** Java generics have their type arguments erased at runtime.

**Fix:** Use a dedicated wrapper DTO, validate each element, or use serialization with appropriate type metadata. `Class<List<User>>` cannot be written directly as `List<User>.class`.

### Error 5: Confusing `get(key, Callable)` with typed get

**Cause:** both overloads take two parameters and are named `get`.

**Fix:** Look at the second parameter:
- `User.class` → requests type checking, **does not load**.
- `() -> repository.load(id)` → **loader on miss**, does not pass a runtime Class.

### Error 6: `get(key, Callable)` calls the loader multiple times on concurrent misses

**Possible causes:** provider does not coordinate the loader on the same key as expected, unstable keys, multiple separate instances/caches, entry gets evicted/expires, or loader encounters errors.

**Fix:** test on the actual provider, observe keys and cacheName, check single-flight guarantees; if cross-node consistency is required, you need a stronger strategy than a loader API alone.

### Error 7: `put(key, null)` fails on another provider

**Cause:** only some implementations support cached-null, possibly via a sentinel.

**Fix:** determine the null policy of the provider/cache manager; when negative caching is needed across environments, consider a dedicated marker DTO rather than relying on null storage support.

### Error 8: Using `getNativeCache()` to infer cached-null

**Cause:** inspecting the map/Redis store directly and seeing a sentinel, serialized value, or provider wrapper.

**Fix:** Prefer the **Cache API** for uniform semantics. `getNativeCache()` returns the provider-specific object whose internal details may change; do not rely on NullValue or internal representation to detect a miss.

### Error 9: Assuming a value retrieved from cache is an immutable snapshot

**Cause:** some caches store object references; the caller may mutate the object, or a writer may alter the entry right after the get call.

**Fix:** for data that must remain stable, use immutable records/DTOs, defensive copies where appropriate, versions, and synchronization protocols. **Typed get only checks the type when retrieving the value**, and does not guarantee snapshot isolation.

## 10. Advanced limitations to keep in mind

### 10.1. Wrapper does not create a transaction across two operations

The snippet:

~~~java
Cache.ValueWrapper w = cache.get(key);
if (w == null) {
    cache.put(key, load());
}
~~~

has a **window between get and put**: two threads both seeing a miss may both load. If the cache operation must coordinate the loader, consider `get(key, Callable)` and test on the specific provider. If other reads/writes also update the source/cache concurrently, you still need additional consistency/versioning mechanisms; a coordinated cache loader does not replace a transaction.

### 10.2. ValueWrapper is not equivalent to `Optional<T>`

`Optional<T>` represents presence/absence of a value, but does not carry the three states **miss / cached-null / cached-value** the way ValueWrapper does. `Optional.empty()` is not enough to state an entry never existed, unless you enforce an explicit business convention.

### 10.3. Null caching needs business boundaries

Caching null may fit relatively stable **not found** results, but may be inappropriate if:
- A new record is created shortly after the initial miss.
- Not seeing the record is a transient state caused by network errors.
- Data involves permissions or user state that changes rapidly.
- The provider has a long TTL causing the negative cache to linger too long.

When caching negative results, set an appropriate TTL/invalidation; `ValueWrapper` does not provide its own TTL, and `Cache.get` does not tell you when the entry was created.

### 10.4. The async `retrieve` API is a different mechanism

Spring Framework 6.1+ includes APIs such as `retrieve(key)` using `CompletableFuture` when supported by the cache implementation. The asynchronous retrieval contract must represent **early miss, late miss, and nullable cached value**; there may be a `ValueWrapper` inside the future result depending on the case. **Do not mechanically apply `get(key, Class<T>)` rules to `retrieve`**.

This lesson focuses on the synchronous `get` overloads. When async programming is needed, read the `retrieve` contract separately and check provider support/exception behavior.

### 10.5. CacheManager may fail to find cacheName

~~~java
Cache cache = cacheManager.getCache("not-configured");
~~~

Per the `CacheManager` interface, the result may be null if the manager does not resolve the cache. If code calls `cache.get(...)` afterward, that is a **NullPointerException from a null cache reference**, distinct from a **null ValueWrapper from a key miss**. Both layers of null must be handled separately.

Example:

~~~java
Cache cache = Objects.requireNonNull(
    cacheManager.getCache("users"),
    "Cache 'users' is not configured");

Cache.ValueWrapper wrapper = cache.get("u1");
~~~

This is illustrative; `Objects` is in java.util. Even when the cache object exists, a distributed provider can still encounter timeouts, network errors, or serialization failures when executing get. The wrapper does not absorb all errors.

## 11. Intentional testing

To test the contract between the application and the provider, include the following test cases:

| Test | Setup | Expected result to verify |
| --- | --- | --- |
| **MISS** | Key not written | `get(key) == null`; `get(key, User.class) == null` |
| **HIT–VALUE** | `put(key, User)` | Non-null wrapper, matching value; typed get returns User |
| **HIT–NULL** | `put(key, null)`, provider allows | Non-null wrapper, `wrapper.get()==null`; typed get returns null |
| **TYPE MISMATCH** | Value User, get String.class | `IllegalStateException` |
| **LOADER MISS** | Empty key, Callable counts calls | Value created/stored, loader runs once in sequential calls |
| **LOADER HIT** | Key already has value | Callable does not run |
| **LOADER HIT–NULL** | Key stores valid null | Callable does not run in supporting provider |
| **LOADER ERROR** | Callable throws checked exception | Exception wrapped in Cache.ValueRetrievalException |
| **EVICT** | Delete existing key | `get(key)` transitions to null wrapper/miss |
| **GENERIC COLLECTION** | `List<String>`, read List.class | Runtime recognizes List without checking element type |
| **CONCURRENT MISS** | Two threads call get-loader on one key | Record loader call count per provider guarantee |
| **CROSS-PROVIDER** | Repeat tests with Redis/Caffeine/... | Verify actual nulls, types, serialization, and errors |

Write integration tests using the application's actual cache manager. **Do not just mock `Cache.get` to return null**, because such a mock cannot simulate the most important difference between a miss and a cached-null.

## 12. Self-check questions

**Question 1:** `cache.get("x")` returns null. Does that mean the cache has an entry containing null?

**No.** The single-parameter overload returning Java null means **there is no mapping** for the key. A cached-null entry is represented by a **non-null ValueWrapper**, whose inner `get()` returns null.

**Question 2:** `cache.get("x", User.class)` returns null. Can you conclude it is a miss?

**No.** Typed get returns null in **both** miss and cached-null cases.

**Question 3:** The cache contains a User, but we call `cache.get("x", String.class)`. What happens?

**IllegalStateException** when a non-null value is not of the requested type. This is a type-contract error, not a cache miss.

**Question 4:** Is `Cache.ValueWrapper` a `ValueWrapper<User>`?

**No.** It is a nested interface of Cache returning an Object payload; the caller must check/cast or use typed get when appropriate.

**Question 5:** Does `get("x", List.class)` guarantee every element is a User?

**No.** It only checks the runtime raw type List; generic element types are not represented by Class<List>.

**Question 6:** Which overload should be used when you want a loader to run on a cache miss?

**get(key, Callable<T>)**, not `get(key, User.class)`.

**Question 7:** A cached-null is stored, then `get(key, Callable)` is called. Must the loader run?

**No.** With a provider supporting cached-null like ConcurrentMapCache in the demo, the key already has a mapping, so the loader **does not run**.

**Question 8:** ValueLoader throws IOException. How is the error typically represented by the API?

Via **Cache.ValueRetrievalException** wrapping the IOException. When handling it, inspect `getCause()` to classify the error source.

**Question 9:** Do `CacheManager.getCache("missing") == null` and `Cache.get("missingKey") == null` have the same meaning?

**No.** The first means **no cache object could be retrieved by that name**; the second means **the cache exists, but the key has no mapping**.

## Summary

- **`Cache.get(key)`** returns **`Cache.ValueWrapper`** if the key has a mapping. The wrapper may hold a null payload; a Java null from the method itself is a **MISS**.
- **`Cache.get(key, Class<T>)`** directly returns the value matching the runtime type or null. **It does not distinguish cached-null from miss**, and throws **IllegalStateException** if a non-null value has the wrong type.
- **`Cache.get(key, Callable<T>)`** is the loader overload that may call the loader on a miss; errors in the loader are wrapped by **Cache.ValueRetrievalException**. Concurrent load coordination depends on the provider.
- **ConcurrentMapCacheManager allows cached-null by default** via an internal sentinel; this capability is not a universal guarantee across all providers.
- When you need to distinguish **entry presence** from **content value**, use **ValueWrapper**; when you only need a typed value, use **typed get**; when you need load-on-miss, use **Callable**.
- Regardless of the overload chosen, keep cacheName/keys consistent, check the type contract, null policy, and consistency when concurrent writers exist.

### Official references

- Spring Framework – Cache API (three get overloads, ValueWrapper, and retrieve): https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/Cache.html
- Spring Framework – Cache.ValueWrapper: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/Cache.ValueWrapper.html
- Spring Framework – Cache.ValueRetrievalException: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/Cache.ValueRetrievalException.html
- Spring Framework – ConcurrentMapCacheManager null-value policy: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html
- Spring Framework – Annotation-based caching: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
