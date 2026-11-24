# Store-by-Value Option and Serialization Requirements in Spring Cache

## Lesson Objectives

In an in-memory cache, a Java object can be stored **by reference (store-by-reference)** or **by value/copy (store-by-value)**. This difference is not merely a performance optimization: it determines whether modifying an object that a caller receives from the cache can accidentally **alter the cached data**.

Spring Framework has a specific option on `ConcurrentMapCacheManager`: `setStoreByValue(true)`. When enabled, `ConcurrentMapCache` uses a serialization mechanism to store a copy of the **cache value**. This introduces an important requirement: cached objects must be validly serializable, including all components in the object graph.

After this lesson, you will be able to:

- Distinguish **store-by-reference** and **store-by-value** using object identity, state, and mutation.
- Understand the default of `ConcurrentMapCacheManager` and how to enable `setStoreByValue(true)`.
- Explain why `Serializable` does not mean "every field is automatically serializable."
- Recognize runtime errors when caching a non-serializable object, instead of mistaking them for `@Cacheable` bugs or cache misses.
- Run a Java 17 + Spring Framework program demonstrating object mutation before and after a cache hit.
- Know when to use immutable DTOs, defensive copies, store-by-value, Redis, or another cache provider.
- Identify CPU/memory overhead, serialization compatibility, class loader, transaction, and security risks.

> **Core point:** `@Cacheable` does not determine whether a reference or a copy is returned. For `ConcurrentMapCacheManager`, the default is **store-by-reference**. Enabling `setStoreByValue(true)` makes the manager store a **serialized copy**, and each read produces a corresponding deserialized value; **values must be serializable**.

## 1. Why Do the Two Storage Modes Matter?

Suppose we have a product query method:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public MutableProduct getProduct(long id) {
    return repository.findProduct(id);
}
~~~

This is an illustrative snippet; `MutableProduct` and the repository need to be defined in a real application.

On the first `getProduct(42)` cache miss, Spring runs the method and caches the result. The caller receives a `MutableProduct` object. If that object has a setter:

~~~java
MutableProduct p = service.getProduct(42);
p.setName("Temporarily edited UI name");
~~~

What happens on the next `service.getProduct(42)` call?

- With **store-by-reference**, the cache may hold **the exact reference** to object `p`. The setter modifies the object the cache points to. Subsequent reads may see `"Temporarily edited UI name"` **even though the repository was never updated**.
- With **store-by-value**, the cache holds a copy detached from `p`. The setter mutates the caller's `p` without changing the copy stored in the cache. Subsequent reads receive a deserialized copy from the stored data, so it still has the original name.

Both modes can produce cache hits and avoid re-querying. The difference is **ownership and sharing of object identity**, not key lookup speed.

### Memory Illustration

~~~text
STORE-BY-REFERENCE

Cache["42"] ---------+
                     |
                     v
                 Product A
                 name="Book"
                     ^
                     |
Caller variable -----+

Caller invokes A.setName("Changed")
=> Cache["42"] still points to Product A, so it sees "Changed".


STORE-BY-VALUE

Caller variable ----> Product A
                       name="Book"
                          |
                    serializable copy
                          |
                          v
Cache["42"] ---------- serialized snapshot ("Book")

Caller invokes A.setName("Changed")
=> Snapshot still holds "Book".

Next read:
snapshot -> deserialize -> Product B, name="Book"
~~~

**Very important note:** store-by-value does not mean the cache automatically knows when the real data source changes. It only establishes a **copy boundary** between callers and cached contents. When the database changes, you still need an invalidation strategy such as `@CacheEvict`, `@CachePut`, or an appropriate TTL.

## 2. Which APIs Support Store-by-Value in Spring?

### 2.1. ConcurrentMapCacheManager

In Spring Framework, `ConcurrentMapCacheManager` manages `ConcurrentMapCache` instances backed by `ConcurrentHashMap`. Notable APIs:

~~~java
void setStoreByValue(boolean storeByValue);
boolean isStoreByValue();
~~~

These are **abbreviated API signatures** of the manager, not a custom class to write.

Key contract:

- `setStoreByValue(false)` — **default**: stores object references, does not require cached objects to implement `Serializable`.
- `setStoreByValue(true)`: stores a **copy** of each cache value; every stored value must be serializable.
- `isStoreByValue()`: checks the current mode.
- When **changing** the store-by-value option on a manager that already has caches, Spring may **reset existing caches** to reconfigure them. Therefore, set the mode **once during configuration**, before the application serves traffic, rather than toggling it at runtime.

This is an option of the **`ConcurrentMapCacheManager` implementation**, not a standard property of every `CacheManager`.

### 2.2. Java Configuration in Spring

~~~java
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CacheConfiguration {

    @Bean
    CacheManager cacheManager() {
        ConcurrentMapCacheManager manager =
            new ConcurrentMapCacheManager("products");
        manager.setStoreByValue(true);
        return manager;
    }
}
~~~

This is configuration code that can be integrated into a Spring application with `@EnableCaching`. When using `@Cacheable(cacheNames = "products")`, cache operations use `products` in the store-by-value-enabled manager.

There is no standard attribute:

~~~java
@Cacheable(cacheNames = "products", storeByValue = true)
~~~

**The line above is an invalid-syntax counterexample** for standard Spring `@Cacheable`: the annotation has no `storeByValue` attribute. Do not copy it into a runnable program.

### 2.3. There Is No Single Switch Applying to All Providers

`CacheManager` is an interface. The `setStoreByValue` API described above is specific to `ConcurrentMapCacheManager`:

- With a typical local **Caffeine** cache, object values placed by the application are normally accessed by JVM reference. Caffeine does not automatically serialization-copy values on every `get`/`put`.
- With a **Redis cache**, data must be encoded/serialized into bytes or another format to store on the backend. On read, data is deserialized using the configured serializer. This **does not mean** Redis uses the same API or native Java serialization as `ConcurrentMapCacheManager`.
- With **JCache (JSR-107)**, store-by-value/store-by-reference is a concept in cache configuration, but capabilities and defaults must be checked against the provider and Spring's integration with it.
- With a custom `Cache`, the implementer may choose a different policy, as long as it fulfills the Spring Cache contract.

Do not infer that every backend supports `setStoreByValue(true)` merely because the same `@Cacheable` annotation is used.

## 3. How Does Spring Create Copies?

### 3.1. Not Simply Calling clone()

In `ConcurrentMapCache`, store-by-value mode is backed by a `SerializationDelegate` supplied by the manager. A high-level view:

~~~text
PUT ("42", MutableProduct A)
               |
          serialize A
               |
         byte[] snapshot
               |
   ConcurrentHashMap["42"] = snapshot


GET ("42")
    |
fetch byte[] snapshot
    |
deserialize snapshot
    |
return MutableProduct B
~~~

Object `B` is a new instance carrying the state saved at serialization time. Modifying `B` in the caller does not directly mutate the bytes stored in the cache. Subsequent `get` calls can produce distinct new objects.

**Do not call this a shallow copy.** If every object in the graph is serializable and serialization succeeds, child objects written to the serialization stream are also reconstructed across the graph. That is a major difference from a simple `clone()` or a copy constructor that only copies a few fields.

### 3.2. Default Mode Keeps the Same Reference

When store-by-value is off:

~~~text
Cache.put("42", objectA)
Cache.get("42") --> objectA
~~~

For a normal value, `ConcurrentMapCache` returns the corresponding object reference via the wrapper without making a copy. Two retrievals of the same key generally point to the same instance if the entry has not been replaced/evicted.

**Wording exception:** if `null` caching is active, Spring may store an internal null marker because `ConcurrentHashMap` does not accept null. The null marker mechanism does not alter the store-by-reference semantics of regular object values.

### 3.3. First Return on @Cacheable

On a cache miss, Spring calls the real method, receives result `A`, requests a cache `put`, and returns the result to the caller. In store-by-value mode, the `put` creates a snapshot, but **there is no rule requiring the initial result `A` to be replaced with another copy before returning to the caller**.

This leads to a very useful test:

1. Call the first time, receive `A`, cache stores a snapshot of `A`.
2. Mutate `A` in the caller.
3. Call again with the same key to trigger a cache hit, receive `B`.
4. `B` reflects the snapshot at `put` time, not subsequent mutations to `A`.

If you also need to isolate the very first result from internal state of a repository/domain entity, you must design DTOs, defensive copies, or proper mapping boundaries. Store-by-value is a cache property, not a mechanism guaranteeing every object across the entire system is immutable.

## 4. Comparison Table for Decision-Making

| Criterion | Store-by-reference | Store-by-value |
| --- | --- | --- |
| Storage in `ConcurrentMapCache` | Object reference | Serialized snapshot of the value |
| Default in `ConcurrentMapCacheManager` | **Yes** | No; must be enabled |
| Requires `Serializable` on cached value | Not solely for the cache | **Yes** |
| Caller mutates object retrieved from cache | Can affect the shared entry | Does not alter stored snapshot |
| Object identity across hits | May be the same instance | Usually different instances |
| `get`/`put` overhead | Lower, no serialization-copy | Must serialize/deserialize; CPU and allocation cost |
| Deep copy of object graph | No | Follows serializable graph |
| Suitable for mutable objects used by multiple callers | Risk of shared mutation | Reduces cache-induced aliasing risk |
| Correctness after database update | Still requires invalidation | Still requires invalidation |
| Multi-node availability | Local memory only | **Still local memory only** |
| Serialization compatibility risk | Does not arise from reference storage | Yes: class version, field types, class loader |
| TTL/max size | Not built-in | **Also not built-in** in ConcurrentMapCacheManager |

**Store-by-value is not free.** It is a performance trade-off to isolate cached values from object mutations by different callers holding them.

## 5. Serializable Requirement: Understand Properly Before Enabling

### 5.1. Cached Class Must Be Serializable

Simple example with Java 17:

~~~java
import java.io.Serializable;

public record ProductDto(
    long id,
    String name,
    long priceCents
) implements Serializable {}
~~~

Records **do not automatically implement Serializable by default**; you must declare `implements Serializable` if you want to use Java serialization. In the example above, the `long` and `String` components are serializable, so the record can be serialized.

Traditional class:

~~~java
import java.io.Serializable;

public class ProductDto implements Serializable {
    private static final long serialVersionUID = 1L;

    private final long id;
    private final String name;

    public ProductDto(long id, String name) {
        this.id = id;
        this.name = name;
    }

    public long getId() { return id; }
    public String getName() { return name; }
}
~~~

This is a complete sample class declaration, though without `main`; the full runnable example is in section 6.

### 5.2. Every Field in the Object Graph Matters Too

A class implementing `Serializable` **does not guarantee every field inside is serializable**:

~~~java
import java.io.Serializable;
import java.util.concurrent.ExecutorService;

public class BadCachedResult implements Serializable {
    private static final long serialVersionUID = 1L;

    private String title;
    private ExecutorService workerPool;
}
~~~

This snippet is a **counterexample**: `workerPool` is not business data that should be stored and typically cannot be serialized. Even though the outer class implements `Serializable`, writing the object graph can fail with `NotSerializableException`.

Fields referencing objects directly or indirectly such as `InputStream`, `DataSource`, `EntityManager`, HTTP requests, service beans, threads, executors, security contexts, or OS resources generally should not reside in cache values. Store **the data you need**, not live infrastructure.

You can mark a field that does not need saving as `transient`, but you must understand that after deserialization, that field **will not regain its old value** unless you explicitly reinitialize it. Using `transient` carelessly can produce business-invalid objects.

### 5.3. serialVersionUID and Class Upgrades

For standard `Serializable` classes, `serialVersionUID` helps Java check version compatibility during deserialization. When a class or object graph changes, old serialized bytes may no longer be readable and throw errors such as `InvalidClassException`, even if the fields look similar at a glance.

`ConcurrentMapCache` lives in local RAM so data is normally lost after restart; thus version impact differs from caches persisted on disk/Redis. Still, during library upgrades, hot reloads, or classloader changes, deserialization compatibility must still be considered.

Java records have distinct serialization semantics. A record implementing `Serializable` uses its canonical constructor upon deserialization; do not apply all assumptions about custom `readObject` in regular classes to records.

### 5.4. Serializable Does Not Mean Immutable or Safe

- `Serializable` **does not make an object immutable**; setters can still mutate the deserialized object.
- `Serializable` **does not guarantee thread safety**; if multiple threads hold the same mutable object, they can still race to mutate its state.
- `Serializable` **does not guarantee all data is safe**; native Java deserialization from **untrusted** byte sources can pose severe security risks.
- `Serializable` **does not mean cache values should hold sensitive data**. You still need authorization, tenant-safe keys, and dedicated data policies.

Store-by-value in local `ConcurrentMapCache` is for value isolation, not encryption, authorization, or secure network transmission.

### 5.5. If Serializable Is Not Implemented, When Does the Error Occur?

The error occurs when **actually serializing the value to put it into the cache**, not when the JVM loads the class or immediately when Spring reads the annotation. A `@Cacheable` method returning a non-serializable value can execute its body, and then the subsequent cache `put` step fails.

With `ConcurrentMapCache`, you typically encounter an `IllegalArgumentException` thrown when serialization fails, wrapping a serialization cause such as `NotSerializableException`. Do not rely on exact message text or stack trace strings in business logic; handle the appropriate error type, log the cause, and fix the DTO.

## 6. Runnable Java 17 Example: Reference, Value, and Serialization Error

This example uses Maven + Java 17 + Spring Framework 6.2.10. Two independent Spring contexts use `ConcurrentMapCacheManager` on the `products` cache:

1. The first context uses the default **store-by-reference**.
2. The second context enables **store-by-value**.
3. Both use `@Cacheable` with the same key; a counter measures how many times the source method body runs.
4. The code intentionally mutates the first object and compares cache hits.
5. Finally, the code directly attempts to put a **non-Serializable** object into the value-mode cache to observe the error.

### 6.1. Project Structure

~~~text
spring-store-by-value/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── StoreByValueDemo.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-store-by-value</artifactId>
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

No Redis or Caffeine is needed. `spring-context` provides `ConcurrentMapCacheManager` and the Spring Cache/proxy components required for the Java Config example.

### 6.3. src/main/java/demo/StoreByValueDemo.java

~~~java
package demo;

import java.io.Serializable;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class StoreByValueDemo {

    // A value that is mutable and serializable.
    public static final class MutableProduct implements Serializable {
        private static final long serialVersionUID = 1L;

        private String name;

        public MutableProduct(String name) {
            this.name = name;
        }

        public String name() {
            return name;
        }

        public void setName(String newName) {
            this.name = newName;
        }
    }

    // Intentionally does not implement Serializable.
    public static final class NotSerializableValue {
        private final String text;

        public NotSerializableValue(String text) {
            this.text = text;
        }

        public String text() {
            return text;
        }
    }

    public static class ProductService {
        private final AtomicInteger loads = new AtomicInteger();

        @Cacheable(cacheNames = "products", key = "#p0")
        public MutableProduct load(String sku) {
            loads.incrementAndGet();
            return new MutableProduct("Book");
        }

        public int loads() {
            return loads.get();
        }
    }

    @Configuration
    @EnableCaching
    public static class ReferenceConfig {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("products");
        }

        @Bean
        public ProductService productService() {
            return new ProductService();
        }
    }

    @Configuration
    @EnableCaching
    public static class ValueConfig {
        @Bean
        public CacheManager cacheManager() {
            ConcurrentMapCacheManager manager =
                new ConcurrentMapCacheManager("products");
            manager.setStoreByValue(true);
            return manager;
        }

        @Bean
        public ProductService productService() {
            return new ProductService();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(
                    ReferenceConfig.class)) {
            ProductService service =
                context.getBean(ProductService.class);

            MutableProduct first = service.load("42");
            System.out.println("REFERENCE:");
            System.out.println("First: " + first.name());
            first.setName("Changed");
            MutableProduct second = service.load("42");
            System.out.println(
                "After caller mutation: " + second.name());
            System.out.println(
                "Same instance: " + (first == second));
            System.out.println("Loads: " + service.loads());
        }

        try (var context =
                new AnnotationConfigApplicationContext(
                    ValueConfig.class)) {
            ProductService service =
                context.getBean(ProductService.class);
            CacheManager manager =
                context.getBean(CacheManager.class);

            MutableProduct first = service.load("42");
            System.out.println("VALUE:");
            System.out.println("First: " + first.name());
            first.setName("Changed");
            MutableProduct second = service.load("42");
            System.out.println(
                "After caller mutation: " + second.name());
            System.out.println(
                "Same instance: " + (first == second));

            second.setName("Changed again");
            MutableProduct third = service.load("42");
            System.out.println(
                "After second mutation: " + third.name());
            System.out.println(
                "Second and third same: " + (second == third));
            System.out.println("Loads: " + service.loads());

            Cache cache = Objects.requireNonNull(
                manager.getCache("products"));

            boolean rejected = false;
            try {
                cache.put("bad", new NotSerializableValue("Oops"));
            } catch (IllegalArgumentException ex) {
                rejected = true;
            }
            System.out.println(
                "Reject non-serializable: " + rejected);
        }
    }
}
~~~

**How the example is designed:**

- `MutableProduct` has a setter and implements `Serializable`; the `String name` field is serializable.
- `NotSerializableValue` intentionally does not implement `Serializable`.
- `@Cacheable` is placed on a public method of a Spring bean. Calls to `load` go through the bean retrieved from `ApplicationContext`, not `new ProductService()` outside the container.
- The two contexts do not share caches. This prevents the store-by-reference test from affecting the store-by-value test.
- `load("42")` returns `"Book"` when actually executed; `loads` measures cache misses reaching the method body.
- The `cache.put` check for the non-serializable type uses the same cache region in value mode and catches this implementation's `IllegalArgumentException`. Other providers may use different exceptions.

### 6.4. How to Run

In the directory containing `pom.xml`, with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.StoreByValueDemo
~~~

Output **printed by the program** (excluding Maven logs):

~~~text
REFERENCE:
First: Book
After caller mutation: Changed
Same instance: true
Loads: 1
VALUE:
First: Book
After caller mutation: Book
Same instance: false
After second mutation: Book
Second and third same: false
Loads: 1
Reject non-serializable: true
~~~

### 6.5. Analyzing Each Output Section

**REFERENCE:**

1. The first `load("42")` is a cache miss; the method creates a `MutableProduct("Book")` and the cache keeps a **reference** to this object.
2. The caller mutates `first.name` to `"Changed"`. Because `first` is the exact object inside the cache, the cached entry also contains the new name.
3. The second `load("42")` is a cache hit; it returns the old object without running the method body. Hence `After caller mutation: Changed`, `Same instance: true`, and `Loads: 1`.

**VALUE:**

1. The first cache miss returns `first`, while Spring stores a serializable snapshot in the cache.
2. The caller mutates `first` to `"Changed"`, but the snapshot in the cache was saved before the mutation so it still holds `"Book"`.
3. The second read hits and deserializes the snapshot into `second`. It is **not the same instance** as `first`.
4. The caller mutates `second` again to `"Changed again"`. The snapshot remains unchanged; the next hit creates `third` with name `"Book"`, not the same instance as `second`.
5. The counter stays at 1: the two cache hits do not execute the real `load`.
6. When putting `NotSerializableValue`, `ConcurrentMapCache` cannot convert it into a snapshot, so the operation is rejected and `rejected` becomes `true`.

**The output does not prove fresh data from the repository.** Both modes cache the state as of store time; if the source data changes, the application needs separate invalidation/reload.

## 7. Why Is Simply Implementing Serializable Not Enough?

### 7.1. Nested Object Graphs

A DTO may contain lists, maps, child objects, and cyclic references:

~~~java
public class CatalogSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;
    private List<ProductSnapshot> products;
}
~~~

This is an **illustrative snippet**, without imports/constructors. If the `ProductSnapshot` objects inside are not serializable or contain non-serializable fields that are not properly excluded, serialization can still fail. A serializable `ArrayList` does not make all its elements serializable.

Java serialization handles object graphs, shared references, and circular references within the same stream; it should not be viewed as merely "copying each field via reflection." Still, you must control what kinds of objects enter the graph.

### 7.2. Lazy-Loaded Entities and ORM Proxies

JPA/Hibernate entities may carry lazy proxies, unloaded relationships, or circular references. Serializing entities directly for caching can:

- trigger unexpected data access;
- fail due to proxies or non-serializable fields;
- produce oversized snapshots;
- store state that is no longer valid once the entity is detached;
- expose information you did not intend to return to callers.

Good practice is usually to cache **DTOs/snapshots with a clear data contract** rather than caching managed entities directly. DTOs let you define which fields are kept, shrink the graph, and simplify testing.

### 7.3. transient and Data Lost After Deserialization

~~~java
public class SessionView implements Serializable {
    private static final long serialVersionUID = 1L;
    private String displayName;
    private transient Object computedHelper;
}
~~~

In the illustrative class above, `computedHelper` is not written by the default serialization mechanism. After deserialization, it normally defaults to `null`. If other methods assume `computedHelper` is always present, cached values can cause `NullPointerException` or business errors.

Therefore, do not use `transient` just to "make serialization errors go away" if the field is actually needed for correctness.

### 7.4. Be Careful About Write Timing

Store-by-value takes a snapshot at **put** time, not via a mechanism tracking live objects. If a method returns an object and another thread modifies it before or during serialization, the snapshot can reflect an inconsistent state if the object is not protected against concurrency.

When data is mutable and shared across threads, use an immutable snapshot or synchronize at the source. Store-by-value **does not automatically fix race conditions** during value construction.

## 8. Does Store-by-Value Affect Keys?

A cache entry has two parts: **key** and **value**.

With `ConcurrentMapCache`, the mode described here uses serialization when moving **values** into and out of the store. This is **not a promise that every key is also cloned/serialized**. Keys in `ConcurrentHashMap` must still maintain stable `equals`/`hashCode` throughout their lifetime in the map.

Dangerous example:

~~~java
public final class MutableKey {
    private long id;

    public MutableKey(long id) {
        this.id = id;
    }

    // Suppose equals/hashCode depend on id.
    public void setId(long id) {
        this.id = id;
    }
}
~~~

This is a **counterexample**, without an `equals/hashCode` implementation provided. If a key object is placed into the map and then mutated so its `hashCode` changes, lookups may no longer find the entry. `setStoreByValue(true)` is not guaranteed to rescue a poorly designed key.

**Advice:** use `String`, `Long`, or immutable records/composite keys with valid `equals/hashCode`; with distributed caches, you also need consistent serialization/key formats across instances.

### Null Values

`ConcurrentMapCacheManager` also has `setAllowNullValues(boolean)`. By default the manager may use an internal marker to represent user-level null because `ConcurrentHashMap` does not store null directly. This is a **different** configuration from store-by-value.

If you use `@Cacheable(unless = "#result == null")`, Spring can veto writing null right at the caching advice level. `unless` addresses **whether to cache null**, not whether values are cached by reference or serialized snapshot.

## 9. When Should You Use Store-by-Reference?

The default store-by-reference is appropriate when:

- Values are **immutable DTOs** (or genuinely treated as immutable).
- Objects are never mutated by callers after being cached.
- Low-latency local caching is needed, avoiding serialize/deserialize cost.
- Some values are not serializable yet can still be safely shared by reference.
- Thread interactions when reading object state are under control.

Example of a record with suitable immutable components:

~~~java
public record PriceView(
    String sku,
    long priceCents,
    String currency
) {}
~~~

This record does not implement `Serializable` yet **can still be cached by reference** in the default `ConcurrentMapCacheManager`. With `String` and primitive components here, there are no setters for callers to mutate the contents. However, not every record is deeply immutable: a record holding a mutable `List` can still be modified through the list reference.

Do not view store-by-reference as a bug in all cases. It is an effective mechanism when cached values are designed to be immutable or non-mutating usage conventions are enforced by code and tests.

## 10. When Should You Use Store-by-Value?

Store-by-value mode is useful if:

- Callers might mutate returned objects and those changes **must not affect the cache**.
- You need to simulate snapshot semantics similar to data passing through a serialization layer.
- You want to test `Serializable` requirements of values early before moving to a provider that serializes entries.
- Cached data is relatively small and read/write frequency can tolerate the overhead.

However, it is **not automatically** the best choice for every cache:

- Serialization/deserialization on every read/write creates allocation and CPU costs.
- Large object graphs can consume more bytes and increase GC pressure.
- Native Java serialization carries its own compatibility and security costs.
- Cached values remain in local RAM, without becoming durable or shared caches.
- There is no automatic TTL, max size, or capacity-based eviction when using plain `ConcurrentMapCache`.
- Deserialized values may need derived/transient state rebuilt.

When immutable DTOs are sufficient, keeping the by-reference default is usually simpler and more efficient.

## 11. Caffeine, Redis, and JCache: Do Not Apply Mechanically

### 11.1. Local Caffeine

Caffeine typically uses JVM in-memory caching and returns the same stored object reference, without using native Java serialization-copying on every cache hit. Enabling `setStoreByValue(true)` on **`ConcurrentMapCacheManager`** does not alter the behavior of a separate `CaffeineCacheManager`.

If copying is needed with Caffeine, you can design immutable DTOs or write an adapter that makes controlled defensive copies; do not expect the `@Cacheable` annotation to generate copies automatically. When data can change, remember dedicated TTL/eviction policies.

### 11.2. Redis Cache

Redis stores encoded bytes/values on the backend. In Spring Data Redis, `RedisCacheConfiguration` lets you configure key/value serialization (such as serializers for JSON or other formats).

Requirements to consider:

- Object values must **actually be supported** by the serializer; not every serializer uses `java.io.Serializable`.
- Formats must remain compatible across application versions and between reading/writing instances.
- You must manage type metadata, deserialization security, and avoid dangerous deserialization on untrusted data.
- Redis serialization does not mean Spring offers the same `setStoreByValue` option as the ConcurrentMap manager.
- With Redis, network latency, clustering, and TTL are separate factors compared to local caches.

If you choose a JSON serializer, a DTO that does not `implements Serializable` can still be stored, provided the serializer understands and reconstructs it. Therefore, the claim "every cache requires implementing Serializable" is **false**. What is required in this lesson is **ConcurrentMapCache store-by-value based on Java serialization**.

### 11.3. JCache and Other Providers

JSR-107/JCache defines store-by-value concepts and cache configuration. However, actual providers can differ in behavior, limitations, and serialization mechanisms. Check the API/documentation of the specific implementation in use and write integration tests verifying object identity and mutation.

Similarly, Ehcache or caching frameworks with memory/disk tiers may use their own copiers/serializers. Do not assume "all in-memory caches store by reference" or "all distributed caches use Java Serializable."

## 12. Performance, Correctness, and Safety

### 12.1. Cost of Creating Copies

Consider a cache region frequently returning 100,000 DTOs/second:

- By-reference only needs a map lookup and returns the held object.
- By-value must deserialize a snapshot on every hit and serialize the value on put. If the object graph is large, the cost can impact P95/P99 latency, throughput, and GC.
- If callers only read truly immutable objects, repeated serialize-copying can be wasteful.

Do not estimate overhead using a fixed percentage. Benchmark with realistic payloads and profiles, observing allocations, GC, CPU, and data sizes.

### 12.2. Not a Replacement for Concurrency Control

With store-by-reference, two threads can see the same mutable object and race when mutating it. Store-by-value reduces value sharing across `get` calls, but it does not turn the whole update flow into a transaction, nor does it provide a distributed lock.

When you need versioned cache updates and protection against lost updates, use versioning/atomic operations actually supported by the system. `@CachePut` and `@CacheEvict` may still be necessary after the data source changes.

### 12.3. Not a Replacement for Authorization

A value serialized into bytes in local memory can still contain sensitive information. If the cache key lacks tenant/user scoping or the result depends on request permissions, a caller can see data outside their scope. Store-by-value does not prevent this kind of leak.

Design keys, cache regions, lifetimes, and authorization checks according to business data. Do not place credentials, tokens, raw sessions, or objects containing secrets into the cache without proper justification and safeguards.

### 12.4. Caution with Native Java Serialization

Java deserialization from untrusted sources is a security risk. For local cache contents produced by the application itself, the threat model differs from data received over the network, yet serialized bytes should still not be treated as unconditionally harmless. Use allow-lists/filters, appropriate serializers, and control data sources; avoid exposing paths that deserialize arbitrary bytes from clients.

## 13. Troubleshooting Common Issues

| Symptom | Possible Cause | How to Fix |
| --- | --- | --- |
| Cache hit returns object mutated elsewhere by caller | Store-by-reference holds the same mutable instance | Use immutable DTOs, defensive copies, or store-by-value as appropriate |
| `Failed to serialize cache value` | Cached value or a nested field is not serializable | Identify `NotSerializableException`, slim down object graph/DTO |
| Class implements Serializable but still fails | A child object in the graph is not Serializable | Locate the failing field/element; don't just add Serializable to outer class |
| Field becomes null after deserialization | `transient` field or un-restored initialization logic | Design reinitialization/mapping, do not store live resources |
| High cache hits but CPU/GC spikes | Serializing/deserializing on every hit | Benchmark, use immutable values by reference or another provider |
| Data source changed but cache stays stale | Missing invalidation/TTL, unrelated to store-by-value | Add `@CacheEvict`, `@CachePut`, and lifecycle policies |
| Changing `setStoreByValue` makes old entries vanish | Manager resets caches when switching mode | Choose mode before traffic, avoid changing at runtime |
| Another `CacheManager` lacks `setStoreByValue` | Not an API on the common interface | Configure the specific provider |
| Cache key cannot be found after mutating key object | Mutable key had its hashCode changed | Use immutable keys with stable equals/hashCode |
| Redis JSON caches DTOs without Serializable | JSON serializer does not require Java Serializable interface | Check serializer contract instead of enforcing a blanket rule |
| No cache hits despite correct annotation | Self-invocation or caching not enabled | Enable `@EnableCaching`, call through Spring proxy, verify key |
| Deserialization errors after deployment | Incompatible class/version/serializer/class loader | Design migration, invalidation, versioned cache namespaces |

### How to Debug in a Real Application

1. Identify the **actual CacheManager being used**, instead of guessing from bean names.
2. Verify `isStoreByValue()` if it is a `ConcurrentMapCacheManager`; do not call this API on other managers.
3. Read the root cause exception from `Cache.put`/`@Cacheable`, especially serialization causes.
4. Inspect the returned value type: DTO, JPA entity, proxy, collection, or resource-holding class.
5. Check every element in the object graph and any `transient` fields.
6. Use integration tests through the Spring bean to observe hits/misses and object identity.
7. Compare values at cache put time, after caller mutation, and at cache hit time.
8. With multiple instances, separate local shared-reference bugs from cross-node invalidation issues.
9. Measure performance with representative payloads; do not enable store-by-value while ignoring cost.
10. Define a migration policy for serialized values if changing types or serializers.

## 14. Design and Testing Checklist

### Before Choosing a Mode

- [ ] Is the cached value truly immutable or just "hoped nobody mutates it"?
- [ ] Can callers mutate the object after a cache hit?
- [ ] Can you return an immutable DTO instead of caching a managed entity?
- [ ] Which copy boundaries are needed: on write, on read, or both?
- [ ] What copy semantics does the provider support; do not assume all managers are alike.
- [ ] Have CPU, allocations, GC, and memory for serialization/deserialization been evaluated?
- [ ] Is there a separate TTL/invalidation policy to handle source data updates?

### If Enabling ConcurrentMap Store-by-Value

- [ ] Configure `setStoreByValue(true)` before using the manager.
- [ ] All cache values can be Java-serialized.
- [ ] Every element in the object graph that must be saved is also serializable or handled properly.
- [ ] Do not cache live resources like streams, connections, executors, or entire Spring beans.
- [ ] Have tests for non-serializable values and expected error paths.
- [ ] Have tests proving caller mutation does not alter the stored snapshot.
- [ ] Cache keys are immutable and have stable equals/hashCode.
- [ ] Have a versioning/migration policy if serialized payloads outlive deployments.
- [ ] Have authorization/key scoping when data contains sensitive information.
- [ ] Monitor cache size, hit ratio, error rate, and memory.
- [ ] Do not confuse store-by-value with distributed caching or durable storage.

## 15. Self-Check Questions

**1.** Does `ConcurrentMapCacheManager` store by value or by reference by default?  
**Answer:** By reference (`setStoreByValue(false)`).

**2.** Why can a caller mutating a returned object alter the cache under store-by-reference?  
**Answer:** The caller and the cache reference the same mutable instance.

**3.** Does `setStoreByValue(true)` copy via `Object.clone()` or via serialization?  
**Answer:** With `ConcurrentMapCache`, it uses serialization/deserialization via the `SerializationDelegate` infrastructure.

**4.** When store-by-value is enabled, why does the cached DTO need `Serializable`?  
**Answer:** The implementation must serialize the object to create the snapshot stored in the map. The object graph must also satisfy serialization requirements.

**5.** Do Java records automatically implement `Serializable`?  
**Answer:** No. If using Java serialization, declare `implements Serializable`.

**6.** Does store-by-value automatically replace `@CacheEvict` when the database changes?  
**Answer:** No. It only protects the snapshot from caller mutations; data freshness still requires invalidation/TTL.

**7.** If a Serializable DTO contains an `ExecutorService`, will serialization definitely succeed?  
**Answer:** No. Non-serializable fields can cause the entire graph to fail; split the DTO or handle the field properly.

**8.** Does the first cache miss in `@Cacheable` return the original object or necessarily a cache copy?  
**Answer:** Normally Spring returns the target method's result; the snapshot is created during cache put, so the first result is not by default a deserialized copy from the cache.

**9.** Why is `@Cacheable(storeByValue=true)` invalid?  
**Answer:** The standard annotation has no such attribute; copy behavior belongs to the provider/CacheManager.

**10.** When using Redis with a JSON serializer, is a non-`Serializable` DTO always rejected?  
**Answer:** No; it depends on the JSON serializer's contract and its ability to encode/decode that type.

**11.** Does store-by-value guarantee that mutable cache keys will work safely?  
**Answer:** No. With ConcurrentMap, keys still need stable hashCode/equals.

**12.** Why shouldn't you enable store-by-value application-wide without measuring?  
**Answer:** Serialization/deserialization incurs CPU, allocation, and GC overhead, along with compatibility and runtime error risks.

**13.** When switching from store-by-reference to store-by-value on a running manager, what can happen to old caches?  
**Answer:** The manager may reset already-created caches to apply the policy change; you should not arbitrarily switch modes under live traffic.

## References

- Spring Framework 6.2 — `ConcurrentMapCacheManager` Javadoc (setStoreByValue/isStoreByValue): https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html
- Spring Framework 6.2 — `ConcurrentMapCache` Javadoc (store-by-value and SerializationDelegate): https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html
- Spring Framework — Understanding the Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache/strategies.html
- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Oracle Java — Serializable interface: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html
- Oracle Java — Serialization of Records: https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html
- Spring Data Redis — RedisCacheConfiguration Javadoc: https://docs.spring.io/spring-data/redis/reference/cache.html