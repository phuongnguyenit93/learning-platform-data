# Null Support and Default Store-by-Reference in Spring In-Memory Cache

## 1. Two Defaults You Must Master

When an application uses `ConcurrentMapCacheManager`/`ConcurrentMapCache`, Spring Cache provides a simple cache backed by a JDK `ConcurrentMap`, usually with `ConcurrentHashMap` underneath. Two important default characteristics apply:

- **`allowNullValues = true`:** Spring accepts caching `null` business results. Because native `ConcurrentHashMap` does not allow `null` values, the cache adapter converts `null` into an **internal marker object**, then decodes it upon reading.
- **`storeByValue = false`:** value objects are stored **by reference** (*store-by-reference*). The cache and calling code can hold references to **the same mutable object**, so mutating the object's state can alter cached data without a new `put` command.

These are characteristics of **the specific implementation and configuration**. You must not assume that every Spring Cache provider — Redis, Caffeine, JCache, or a custom provider — shares the same mechanism or the same defaults.

### Learning Objectives

After this lesson, you will be able to explain:

1. Why Spring Cache accepts cached-null values while `ConcurrentHashMap` does not.
2. How to distinguish a missing entry from an entry holding a null value via `Cache.ValueWrapper`.
3. How `@Cacheable` behaves when a method returns null and how to use `unless = "#result == null"`.
4. What store-by-reference means, the *aliasing* phenomenon, and the risk of mutating shared objects.
5. How to toggle `setAllowNullValues` and `setStoreByValue`.
6. The role of `Serializable` under store-by-value; trade-offs in CPU, memory, and consistency.
7. How to verify these behaviors using a Java 17 program running with Spring Framework.

## 2. Cache Abstraction, Manager, and Native Map

Diagram:

~~~text
Caller / @Cacheable / Cache API
               |
               v
         CacheManager
               |
        getCache("items")
               |
               v
      ConcurrentMapCache
               |
           Key -> Value
               |
               v
    ConcurrentMap<Object, Object>
       (typically JDK ConcurrentHashMap)
~~~

`CacheManager` manages named caches. `Cache` manages entries by key. `ConcurrentMapCache` adapts between Spring's `Cache` interface and the `ConcurrentMap` storage type.

Configuration example:

~~~java
@Bean
public CacheManager cacheManager() {
    return new ConcurrentMapCacheManager("items");
}
~~~

This is an illustrative snippet inside a Spring `@Configuration`; it is not a standalone Java file yet. When using the programmatic API:

~~~java
Cache cache = Objects.requireNonNull(
        cacheManager.getCache("items"));

Cache.ValueWrapper entry = cache.get("P1");
~~~

The `getCache("items")` level selects the **region**, whereas `get("P1")` looks up the **entry**. If `getCache` returns `null`, the cache region is not provided; if `get` returns `null`, **the entry has no mapping**. These two nulls do not mean the same thing.

### Do Not Confuse Null Values with Null Keys

`ConcurrentHashMap` forbids both `null` keys and `null` values. Spring's `allowNullValues` only handles **user-level null values**; it does not mean the API will support `cache.put(null, value)`. Use stable, non-null keys with proper `equals/hashCode`.

## 3. Why Does ConcurrentMapCache Support Null?

### 3.1. Native ConcurrentHashMap Does Not Accept Null

Standard Java code:

~~~java
Map<String, Object> raw = new ConcurrentHashMap<>();
raw.put("missing", null); // throws NullPointerException
~~~

This snippet requires importing `Map` and `ConcurrentHashMap`. In a native map, `get(key) == null` signals that no mapping was found. Hence `null` cannot be used directly as a value.

### 3.2. Spring Uses a Marker

With the default `ConcurrentMapCacheManager`:

~~~java
Cache cache = manager.getCache("items");
cache.put("missing", null);
~~~

Spring goes through these conceptual steps:

~~~text
Application calls Cache.put("missing", null)
                 |
                 v
    Spring converts user-level null
    into a marker object
                 |
                 v
 ConcurrentHashMap["missing"] = marker
                 |
                 v
  Cache.get("missing") returns ValueWrapper
                 |
                 v
  ValueWrapper.get() returns user-level null
~~~

Spring has `org.springframework.cache.support.NullValue` to internally represent null. You **should not interact with the marker** as a business data type, and should not fetch the raw value and cast it directly to a DTO; use the `Cache` API so Spring performs the conversion.

According to the `ConcurrentMapCacheManager` Javadoc, `setAllowNullValues(boolean)` defaults to `true`; an internal holder is used because native `ConcurrentHashMap` does not support null.

### 3.3. Distinguishing Miss from Cached-Null

~~~java
Cache.ValueWrapper missing = cache.get("P1"); // not put yet -> null

cache.put("P1", null);
Cache.ValueWrapper cachedNull = cache.get("P1");

// cachedNull != null: entry exists.
// cachedNull.get() == null: business value is null.
~~~

Comparison table:

| State | `cache.get(key)` | `wrapper.get()` | Conclusion |
| --- | --- | --- | --- |
| No entry yet | `null` | Cannot call | Cache miss |
| Entry with user-level null | Non-`null` wrapper | `null` | Cache hit with null |
| Entry with `"item-A"` | Non-`null` wrapper | `"item-A"` | Normal cache hit |

Unambiguous check:

~~~java
Cache.ValueWrapper wrapper = cache.get(key);
if (wrapper == null) {
    // No entry yet.
} else if (wrapper.get() == null) {
    // Entry exists, cached value is null.
} else {
    // Entry exists, non-null value.
}
~~~

The snippets above assume variables `cache` and `key` are already declared.

### 3.4. Typed Lookup Cannot Distinguish Them

~~~java
String value = cache.get("P1", String.class);
~~~

`value == null` **does not prove** a cache miss: it could be a cached-null. When you need to tell them apart, use the `Cache.ValueWrapper` from `get(Object)`. This is a practical difference when writing fallback logic, hit/miss statistics, and not-found handling.

## 4. Spring @Cacheable and Negative Caching

A method that can return null:

~~~java
@Cacheable(cacheNames = "items", key = "#p0")
public String findDescription(String sku) {
    return repository.findDescription(sku); // may be null
}
~~~

This is an illustrative snippet, not standalone because it needs `repository` and Spring configuration.

With a manager that allows null, suppose SKU `"P404"` does not exist:

~~~text
1st call findDescription("P404")
  -> Cache MISS
  -> runs repository.findDescription
  -> receives null
  -> Spring writes null-marker for key P404
  -> caller receives null

2nd call findDescription("P404")
  -> Cache HIT with null-marker
  -> caller receives null
  -> DOES NOT run repository.findDescription
~~~

This is **negative caching**: caching the absence of data. The benefit is reduced load when a nonexistent key is queried repeatedly. The risk: if a record is newly created in the database while the cached-null has not been evicted/expired yet, the application still returns null.

### 4.1. Skipping Null Results with unless

~~~java
@Cacheable(
    cacheNames = "items",
    key = "#p0",
    unless = "#result == null"
)
public String findDescription(String sku) {
    return repository.findDescription(sku);
}
~~~

`unless` is evaluated **after the method returns its result**; when the result is null, Spring skips the put. The next call has to reload. In contrast, `condition` checks the condition **before invocation** and does not use the return value as its basis.

| Option | First call returning null | Subsequent call with same key |
| --- | --- | --- |
| Default, provider allows null | Stores null-marker | Cache hit, method may be skipped |
| `unless = "#result == null"` | Does not store | Miss, method runs again |
| `setAllowNullValues(false)` without veto | May fail when writing null | Should not rely on succeeding |
| `setAllowNullValues(false)` with null veto | Does not store null | Next call misses, method runs again |

If the return type is `Optional<T>`, Spring Cache normally unwraps `Optional`: `Optional.empty()` is represented as a user-level null in the cache. Thus the decision on caching null remains important when methods use `Optional`.

### 4.2. When to Cache Null and When Not To

Caching null makes sense when "not found" is relatively stable, lookup cost is high, and there is a TTL/invalidation plan. You should not cache null for too long if new records appear frequently, or if null is being used to represent **timeouts, insufficient permissions, or temporary service outages**.

Do not share cached nulls across users/tenants when access permissions affect the result. A user who is unauthorized to view data should not cause an authorized user to receive a cached-null just because two requests share the same key.

## 5. What Is Default Store-by-Reference?

With the default `ConcurrentMapCacheManager`:

~~~java
manager.isStoreByValue(); // false
~~~

`storeByValue=false` means values are held by **reference**, without creating copies of the object. If other code holds the same reference and the value is mutable, modifying the object **changes the state visible to the cache**.

~~~text
Caller
  local variable "box"
            |
            v
     +--------------+
     | MutableBox   |
     | amount = 100 |
     +--------------+
            ^
            |
   Cache["box"] holds a reference
   to the exact object above
~~~

Example:

~~~java
final class MutableBox {
    int amount;
    MutableBox(int amount) { this.amount = amount; }
}

MutableBox box = new MutableBox(100);
cache.put("box", box);

box.amount = 150;
MutableBox fromCache = cache.get("box", MutableBox.class);

System.out.println(fromCache.amount);  // 150
System.out.println(fromCache == box);   // true
~~~

This snippet illustrates a cache configured as store-by-reference with variable `cache` already declared. There is no second `cache.put`; the object is mutated through an external reference outside the cache.

### 5.1. Mutating an Object Returned from Cache Can Affect Every Caller

~~~java
MutableBox first = cache.get("box", MutableBox.class);
first.amount = 999;

MutableBox second = cache.get("box", MutableBox.class);
System.out.println(second.amount); // 999 if same reference
~~~

An endpoint might receive a mutable DTO from `@Cacheable` and then modify a field for display. If that is the exact cached object, another request will see the modified field — even though no database write, transaction, or `@CachePut` ran. This is **cache pollution** caused by shared references.

### 5.2. Does Not Automatically Synchronize the Database

Seeing a cached object's field change from 100 to 150 does not mean the database saved 150. The cache merely sees the same object. Conversely, the database can change while the cached reference still holds old data if there is no invalidation/reload logic. Do not use mutable references as a mechanism for updating the underlying source of truth.

### 5.3. ConcurrentMap Does Not Make Values Thread-Safe

`ConcurrentHashMap` protects the map structure during concurrent operations, **it does not guarantee thread safety of stored objects**. If a value contains an `ArrayList`, `HashMap`, or multiple mutable fields, readers/writers may observe intermediate states or races.

For consistent updates, store an **immutable snapshot** and replace the entire entry. A `record` containing mutable components (arrays/lists) is still not deep-immutable; copy the whole object graph when data protection is needed.

### 5.4. Do Not Use Mutable Keys

Although the topic is *value references*, keys carry their own risk: a key object whose `hashCode()/equals()` changes after `put` can cause lookups to fail. Use keys like `String`, `UUID`, or records composed of immutable fields; do not use mutable DTOs as keys.

## 6. Two Independent Configuration Flags

`ConcurrentMapCacheManager` provides:

~~~java
ConcurrentMapCacheManager manager =
        new ConcurrentMapCacheManager("items");

manager.setAllowNullValues(false); // Reject user-level null.
manager.setStoreByValue(true);    // Copy values using serialization.
~~~

You do not have to toggle both; they solve two different problems:

| Flag | Default | When changed | Meaning |
| --- | --- | --- | --- |
| `allowNullValues` | `true` | `false` | Disallow caching user-level null |
| `storeByValue` | `false` | `true` | Serialize/copy values instead of sharing references |

### 6.1. Disabling Cached-Null

~~~java
@Bean
public CacheManager cacheManager() {
    ConcurrentMapCacheManager manager =
            new ConcurrentMapCacheManager("items");
    manager.setAllowNullValues(false);
    return manager;
}
~~~

If `cache.put("A", null)` is subsequently called, `ConcurrentMapCache` rejects the null value (typically throwing `IllegalArgumentException`). When using `@Cacheable` on a method that may return null, combine with `unless = "#result == null"` or design it to return a non-null business value.

### 6.2. Store-by-Value: storeByValue=true

~~~java
@Bean
public CacheManager cacheManager() {
    ConcurrentMapCacheManager manager =
            new ConcurrentMapCacheManager("items");
    manager.setStoreByValue(true);
    return manager;
}
~~~

When `storeByValue=true` is enabled, `ConcurrentMapCacheManager` uses serialization to create a **copy on store** and return a **copy on retrieval**. Cached values must implement `Serializable`; nested fields in the object graph must also be serializable. Otherwise, cache operations may throw runtime errors.

Example of a suitable class:

~~~java
public static final class MutableBox implements Serializable {
    private static final long serialVersionUID = 1L;
    private int amount;

    public MutableBox(int amount) { this.amount = amount; }
    public int getAmount() { return amount; }
    public void setAmount(int amount) { this.amount = amount; }
}
~~~

This snippet requires importing `java.io.Serializable` and must sit in a valid location in Java code. Copies isolate references; modifying the original object after `put` **does not** affect the stored snapshot, and modifying the retrieved copy after `get` **does not** alter the cache.

### 6.3. Enabling Store-by-Value Does Not Automatically Give TTL, Redis, or Persistence

Serialization in `ConcurrentMapCacheManager` still operates **within the current JVM**. It does not mean data is shared over the network, saved to disk, persisted across restarts, or expired by TTL.

Trade-off: store-by-value requires serialization/deserialization, consuming CPU, allocating memory, and risking class/schema compatibility issues. If values are already immutable, store-by-reference is usually cheaper while remaining safe against mutation.

### 6.4. Configure Before Use, Do Not Flip Flags Live

According to the Javadoc, changing `setAllowNullValues` or `setStoreByValue` may **reset already-created caches** to reconfigure them. This can lose entries and replace `Cache` objects held elsewhere.

Configure both flags when building the `CacheManager` bean, before putting the cache into service for requests. Do not use them as runtime switches to toggle policies on an active cache.

## 7. Complete Java 17 Demo: Null Marker and Reference/Copy

The project below uses **Spring Framework 6.2.16**, Java 17, and Maven. No Spring Boot, database, or Redis is needed. The demo verifies:

1. Default manager has `allowNullValues=true`, `storeByValue=false`.
2. `get(key)` returns null on miss, but a non-null `ValueWrapper` if null was cached.
3. The native `ConcurrentMap` holds a non-null marker.
4. Mutable objects are stored with the same reference.
5. `@Cacheable` caches null results, while `unless` prevents storing null.
6. A manager configured with `setAllowNullValues(false)` rejects null.
7. Another manager configured with `setStoreByValue(true)` creates serializable copies.

### 7.1. Structure

~~~text
in-memory-null-reference/
├── pom.xml
└── src/main/java/demo/InMemoryCacheDemo.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>in-memory-null-reference</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.16</version>
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

### 7.3. src/main/java/demo/InMemoryCacheDemo.java

~~~java
package demo;

import java.io.Serializable;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class InMemoryCacheDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        public ConcurrentMapCacheManager cacheManager() {
            return new ConcurrentMapCacheManager("items");
        }

        @Bean
        public LookupService lookupService() {
            return new LookupService();
        }
    }

    public static class LookupService {
        private final AtomicInteger loads = new AtomicInteger();
        private final AtomicInteger vetoLoads = new AtomicInteger();

        @Cacheable(cacheNames = "items", key = "#p0")
        public String find(String key) {
            int n = loads.incrementAndGet();
            System.out.println("LOAD " + key + " #" + n);
            return null;
        }

        @Cacheable(
                cacheNames = "items",
                key = "'skip:' + #p0",
                unless = "#result == null")
        public String findWithoutNullCache(String key) {
            int n = vetoLoads.incrementAndGet();
            System.out.println("VETO_LOAD " + key + " #" + n);
            return null;
        }

        public int loadCount() {
            return loads.get();
        }
    }

    public static final class MutableBox implements Serializable {
        private static final long serialVersionUID = 1L;
        private int amount;

        public MutableBox(int amount) {
            this.amount = amount;
        }

        public int getAmount() {
            return amount;
        }

        public void setAmount(int amount) {
            this.amount = amount;
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            ConcurrentMapCacheManager manager =
                    context.getBean(ConcurrentMapCacheManager.class);
            LookupService service =
                    context.getBean(LookupService.class);
            Cache cache = Objects.requireNonNull(
                    manager.getCache("items"));

            System.out.println("allowNull="
                    + manager.isAllowNullValues());
            System.out.println("storeByValue="
                    + manager.isStoreByValue());

            // A miss entry differs from an entry with a cached null.
            System.out.println("initialMiss="
                    + (cache.get("nil") == null));
            cache.put("nil", null);
            Cache.ValueWrapper wrapper = cache.get("nil");
            System.out.println("nullEntry="
                    + (wrapper != null));
            System.out.println("nullValue="
                    + (wrapper != null && wrapper.get() == null));

            ConcurrentMapCache nativeCache =
                    (ConcurrentMapCache) cache;
            System.out.println("nativeHasMarker="
                    + (nativeCache.getNativeCache().get("nil") != null));

            // Store-by-reference: same mutable object.
            MutableBox shared = new MutableBox(1);
            cache.put("box", shared);
            System.out.println("sameReference="
                    + (cache.get("box", MutableBox.class) == shared));
            shared.setAmount(7);
            System.out.println("afterExternalMutation="
                    + Objects.requireNonNull(
                            cache.get("box", MutableBox.class))
                            .getAmount());

            // @Cacheable: null is stored as a cached-null.
            System.out.println("lookup1=" + service.find("X"));
            System.out.println("lookup2=" + service.find("X"));
            System.out.println("loadCount=" + service.loadCount());
            System.out.println("annotatedNullEntry="
                    + (cache.get("X") != null));

            // unless: do not store null results.
            System.out.println("veto1="
                    + service.findWithoutNullCache("X"));
            System.out.println("veto2="
                    + service.findWithoutNullCache("X"));
            System.out.println("vetoHasEntry="
                    + (cache.get("skip:X") != null));

            // Another manager: reject storing null.
            ConcurrentMapCacheManager strict =
                    new ConcurrentMapCacheManager("strict");
            strict.setAllowNullValues(false);
            Cache strictCache = Objects.requireNonNull(
                    strict.getCache("strict"));
            System.out.println("strictAllowNull="
                    + strict.isAllowNullValues());

            boolean strictRejected = false;
            try {
                strictCache.put("nil", null);
            } catch (IllegalArgumentException expected) {
                strictRejected = true;
            }
            System.out.println("strictRejected=" + strictRejected);

            // Store-by-value manager: values must be Serializable.
            ConcurrentMapCacheManager copies =
                    new ConcurrentMapCacheManager("copies");
            copies.setStoreByValue(true);
            Cache copyCache = Objects.requireNonNull(
                    copies.getCache("copies"));
            MutableBox original = new MutableBox(1);
            copyCache.put("box", original);

            System.out.println("copyMode="
                    + copies.isStoreByValue());
            System.out.println("copySameReference="
                    + (copyCache.get("box", MutableBox.class)
                            == original));

            original.setAmount(9);
            System.out.println("copyAfterOriginalMutation="
                    + Objects.requireNonNull(
                            copyCache.get("box", MutableBox.class))
                            .getAmount());

            MutableBox returned = Objects.requireNonNull(
                    copyCache.get("box", MutableBox.class));
            returned.setAmount(6);
            System.out.println("copyAfterReturnedMutation="
                    + Objects.requireNonNull(
                            copyCache.get("box", MutableBox.class))
                            .getAmount());
        }
    }
}
~~~

### 7.4. Running with Maven

In the `in-memory-null-reference` directory, JDK 17+ and Maven are required:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.InMemoryCacheDemo
~~~

Expected stdout printed by **the program** (excluding Maven/JVM messages):

~~~text
allowNull=true
storeByValue=false
initialMiss=true
nullEntry=true
nullValue=true
nativeHasMarker=true
sameReference=true
afterExternalMutation=7
LOAD X #1
lookup1=null
lookup2=null
loadCount=1
annotatedNullEntry=true
VETO_LOAD X #1
veto1=null
VETO_LOAD X #2
veto2=null
vetoHasEntry=false
strictAllowNull=false
strictRejected=true
copyMode=true
copySameReference=false
copyAfterOriginalMutation=1
copyAfterReturnedMutation=1
~~~

### 7.5. Comparing Behavior Groups

**Null and marker:** `initialMiss=true` because the key does not exist yet. After `put("nil", null)`, `nullEntry=true` while `nullValue=true`; the native map holds the marker so `nativeHasMarker=true`. The caller does not need to know which class the marker is.

**Reference:** `sameReference=true` shows the cache holds the same instance as `shared`. After calling `shared.setAmount(7)`, the getter yields amount 7 even without putting again.

**Cache annotation:** `LOAD X #1` prints only once. The `lookup2` call returns null via a cache hit. `annotatedNullEntry=true` confirms the entry exists. Conversely, `VETO_LOAD` prints twice and `vetoHasEntry=false` because `unless` prevents storing null.

**Strict configuration:** `strictAllowNull=false` and `strictRejected=true` prove the other cache rejects null. The configuration flags do not retroactively affect the Spring context's default manager.

**Store-by-value:** `copyMode=true` and `copySameReference=false` because the cache stores/returns copies. Mutating `original` or the retrieved object does not change the cached snapshot: both `copyAfter...` lines print 1.

**Proxy:** the `find` method lives in a Spring-managed bean retrieved from the context, so `@Cacheable` takes effect. If you instantiate `new LookupService()` outside Spring, the annotation will not perform cache lookups automatically.

## 8. Designing Safely for Production

### 8.1. Choose an Intentional Null Policy

If "not found" is relatively stable and queries are expensive, cached-null can be helpful. If new records may appear right afterward, the null marker easily becomes stale. Ways to handle this:

- Use `unless = "#result == null"` to avoid storing null.
- Explicitly evict the exact key when creating a new record.
- Use a provider with TTL and appropriate cache size limits.
- Separate technical errors from "no data" results; do not cache timeout errors as valid nulls.

A plain `ConcurrentMapCache` **does not provide automatic TTL**; a cached-null can persist until evicted/cleared or the JVM exits.

### 8.2. Return Immutable DTOs When Possible

With store-by-reference, prefer DTOs without setters and with deeply immutable structures. A `record` holding a mutable collection can still be mutated through that collection. If callers cannot be controlled, return defensive copies or choose store-by-value when serialization is suitable.

### 8.3. Thread Safety and Consistency

`ConcurrentHashMap` does not protect the invariants of mutable values. If readers/writers run across multiple threads, replace the entire value with an immutable snapshot rather than mutating individual fields of a shared object.

### 8.4. Verify the Actual Manager in Use

In Spring Boot, the auto-configured manager depends on the classpath and configuration; never assume every Boot application uses `ConcurrentMapCacheManager`. Inspect the actual `CacheManager` bean being injected, its provider, and its flags before inferring null/reference semantics.

### 8.5. Do Not Treat an In-Memory Cache as a Distributed Cache

A local manager on instance A does not share references with a manager on instance B. When running multiple replicas, cache TTL, eviction, memory, and consistency must be designed separately; store-by-value does not automatically create replication.

### 8.6. Do Not Change Flags During Live Traffic

`setAllowNullValues` and `setStoreByValue` can reset existing caches. Declare configuration once when creating the bean; if you must change policy in production, account for cached entry migration, downtime, warm-up, and testing.

## 9. Testing Checklist

| Scenario | Verification |
| --- | --- |
| Manager defaults | `isAllowNullValues()==true`; `isStoreByValue()==false` |
| Cache miss | `cache.get(key)==null` |
| Cached-null | `cache.put(key,null)` then non-null wrapper and `get()==null` |
| Typed get | `cache.get(key, String.class)==null` is insufficient to conclude a miss |
| Native map | Marker is stored instead of Java null |
| Reference | Original object and cached object are the same instance |
| Mutation | Mutating the original object changes `get` result under store-by-reference |
| @Cacheable null | Two calls with same key, body runs only once |
| unless null | Two calls with same key, body runs twice |
| Reject null | `setAllowNullValues(false)` before `put`, null is rejected |
| Copy mode | `setStoreByValue(true)` with Serializable value, `get` does not return same reference |
| Serializability | Non-serializable values can cause errors |
| Changing flags | Confirm cached entries may be reset |
| Multiple instances | No automatic synchronization across other JVMs |

Unit tests that only compare `equals` are insufficient to determine copy vs. reference; check object identity with `==`/`assertSame` and mutate state in the test. When testing cached-null, check `ValueWrapper` rather than only comparing the method's return value.

## 10. Common Misconceptions

**"ConcurrentHashMap does not accept null, so @Cacheable cannot cache null."** False in default `ConcurrentMapCacheManager`: Spring uses an internal holder for null values.

**"Cache.get(key) returning null means the entry contains null."** False for the `ValueWrapper`-returning method: a `null` wrapper is a miss; a non-null wrapper may contain null.

**"Cache.get(key, Type.class) returning null is definitely a miss."** Not necessarily: typed lookup does not distinguish cached-null from a miss.

**"Mutating a DTO returned from the cache only affects the current request."** Incorrect if the cache holds the same reference. Use immutable snapshots, defensive copies, or store-by-value.

**"ConcurrentMapCache being thread-safe means every value is also thread-safe."** False: map-level concurrency does not make mutable objects inside safe.

**"Enabling storeByValue=true gives Redis/TTL/persistence."** False: it is only a copy-via-serialization strategy in the local cache.

**"Disabling allowNullValues is enough for methods returning null to be skipped."** Not automatically; use `unless` or ensure the method does not produce null results that would be put.

**"Changing flags after the cache already has data has no side effects."** False. The manager may reset caches and entries when changing these flags.

## 11. Self-Check Questions

1. **Why can Spring store user-level null in a native ConcurrentHashMap?** Because the adapter converts null into a non-null marker and decodes it on read.
2. **What is the difference between `cache.get("A")==null` and `wrapper.get()==null`?** The first is a miss; the second, if a wrapper exists, is a cached-null hit.
3. **Why can a @Cacheable method returning null run only once?** Because null was cached as an entry with a marker, so subsequent calls hit.
4. **What changes when using `unless="#result == null"`?** Spring does not put null results; subsequent calls can still miss.
5. **Why does mutating an object outside the cache change the cached value?** Because by default the cache holds the same reference to the mutable object.
6. **What is required to enable `setStoreByValue(true)`?** Values must be serializable, and you must accept copy overhead and check schema compatibility.
7. **Does `setAllowNullValues(false)` stop objects from sharing references?** No. The two flags are independent.
8. **Is store-by-value automatically cluster-safe?** No; it does not replace a distributed backend, TTL, or invalidation.

## 12. Conclusion

With in-memory caches based on `ConcurrentMapCacheManager`, two defaults must be treated as technical decisions that affect business behavior:

- **`allowNullValues=true`:** null results are cached via a marker; you must use `Cache.ValueWrapper` to distinguish a null hit from a miss.
- **`storeByValue=false`:** values are kept by reference; callers mutating objects can unintentionally alter cached data.

Choose a null policy while accounting for negative-cache staleness, and choose a value storage model while accounting for mutability, concurrency, serialization, and operational cost. The cache abstraction simplifies the API, but it does not eliminate provider-specific characteristics.

## Official Documentation

- Spring Framework 6.2 — Cache Abstraction: https://docs.spring.io/spring-framework/reference/6.2/integration/cache.html
- Spring Framework 6.2 — Configuring Cache Storage: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/store-configuration.html
- ConcurrentMapCacheManager Javadoc (6.2.16): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html
- ConcurrentMapCache Javadoc (6.2.18): https://www.springframework.org/spring/docs/6.2.18/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html
- Spring Cache API Javadoc (6.2.16): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/cache/Cache.html
- Declarative Caching (6.2): https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html