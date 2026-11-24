# Using Spring Annotations on a JCache-Compliant Store (JSR-107)

## 1. The Problem: Keeping Spring Annotations While Swapping the Backing Cache to JCache

Spring Framework provides two things with similar names that are **not identical**:

- **Spring Cache abstraction:** the interfaces `org.springframework.cache.Cache`, `org.springframework.cache.CacheManager`, and the annotations `@Cacheable`, `@CachePut`, `@CacheEvict`, `@Caching`, and `@CacheConfig`. These annotations belong to `org.springframework.cache.annotation`.
- **JCache (JSR-107):** Java's standard caching API with `javax.cache.Cache`, `javax.cache.CacheManager`, `javax.cache.spi.CachingProvider`, and standard annotations such as `javax.cache.annotation.CacheResult`, `CachePut`, `CacheRemove`, and `CacheRemoveAll`.

The topic **"Using Spring annotations on a JCache-compliant store"** means: **keep Spring's `@Cacheable`, `@CachePut`, and `@CacheEvict` on business methods**, while configuring the Spring `CacheManager` with a **`JCacheCacheManager` adapter** pointing to an actual `javax.cache.CacheManager` created by a JSR-107-compliant provider.

Example provider names: **Ehcache 3** or **Caffeine JCache**. Both provide `javax.cache.*` implementations; in this guide we choose Caffeine JCache so the example needs no Redis, XML file, or external server. JCache is an **API contract**, not the name of a single cache server.

Learning objectives:

1. Clearly distinguish the Spring and `javax.cache` namespaces and know where the adapter sits.
2. Prepare the provider, `javax.cache.CacheManager`, and cache names before initializing Spring's caching infrastructure.
3. Use Spring annotations to read, update, and evict data on a native JCache store.
4. Verify cache hits/misses, keys, `unless`, nulls, expiry, and provider characteristics.
5. Avoid confusing Spring annotations with JCache annotations and understand their interoperability limits.
6. Run a Java 17+, Maven, and Spring context example and know how to test against a real backend.

## 2. Architecture Diagram: Two CacheManager Layers

~~~mermaid
flowchart TD
    Caller[Caller invokes Spring-managed bean through proxy] --> Interceptor[Spring CacheInterceptor]
    Interceptor --> Operation[Evaluate @Cacheable / @CachePut / @CacheEvict]
    Operation --> SpringManager[Spring CacheManager: JCacheCacheManager]
    SpringManager --> Adapter[Spring JCacheCache adapter]
    Adapter --> JManager[javax.cache.CacheManager]
    JManager --> JCache[javax.cache.Cache by cache name]
    JCache --> Provider[JCache CachingProvider]
    Provider --> Store[Native store: Caffeine / Ehcache / other vendor]
~~~

Main flow:

- A Spring annotation produces a **cache operation** based on the method, parameters, SpEL, and return value.
- `CacheInterceptor` calls the Spring `CacheManager` to obtain a Spring `Cache` for `cacheNames`.
- `org.springframework.cache.jcache.JCacheCacheManager` returns a Spring `JCacheCache` adapter for the corresponding JSR-107 cache.
- The adapter calls `javax.cache.Cache<K,V>` managed by the JCache provider.
- The provider handles storage, size/expiry eviction, key/value types, store-by-value, and vendor-specific features.

**Two `CacheManager` interfaces belong to different packages despite sharing the same name.** Do not import the wrong one or register `javax.cache.CacheManager` expecting `@EnableCaching` to automatically turn it into a Spring `CacheManager` in a manually configured application. Without specialized auto-configuration, you must declare **a Spring `CacheManager` bean** (such as `JCacheCacheManager`) as shown below.

### Viewing via Java Types

~~~java
javax.cache.CacheManager nativeJCacheManager = provider.getCacheManager();

org.springframework.cache.CacheManager springCacheManager =
        new org.springframework.cache.jcache.JCacheCacheManager(
                nativeJCacheManager);
~~~

This snippet requires a `provider` variable of type `javax.cache.spi.CachingProvider`. Do not cast one manager to the other; they are two separate contracts **connected by an adapter**.

## 3. Dependencies, Package Names, and Versions

To use Spring annotations on a JCache store, you typically need:

| Component | Role |
| --- | --- |
| `spring-context` | Spring's core caching abstraction, annotations, and infrastructure |
| `spring-context-support` | `JCacheCacheManager`, `JCacheCache`, and provider integration support |
| `javax.cache:cache-api` | JSR-107 interfaces, `javax.cache.CacheManager`, and `CachingProvider` |
| JCache implementation, e.g., `com.github.ben-manes.caffeine:jcache` | Concrete provider supplying storage and JCache implementation |
| Spring-managed bean with `@EnableCaching` | Activates cache interception for Spring annotations |

Use matching versions of `spring-context` and `spring-context-support`; with Spring Boot, let the BOM/Dependency Management control Spring versions rather than mixing versions manually.

**Namespace note:** JCache 1.1 (JSR-107) uses `javax.cache.*` even when the project uses Jakarta EE libraries such as `jakarta.persistence.*` or `jakarta.servlet.*`. Do not change imports to `jakarta.cache` when your API and provider are `javax.cache:cache-api:1.1.1`.

Adding `javax.cache:cache-api` alone **is not enough** to run a cache: an available, properly configured **CachingProvider** is required. Conversely, adding native Caffeine `com.github.ben-manes.caffeine:caffeine` alone does not provide a JCache provider; demonstrating JSR-107 requires the `jcache` artifact.

JCache discovers providers via `ServiceLoader`. When the classpath contains **multiple providers**, parameterless `Caching.getCachingProvider()` can become ambiguous. Specify the implementation class name when you want deterministic results in examples or tests:

~~~java
CachingProvider provider = Caching.getCachingProvider(
    "com.github.benmanes.caffeine.jcache.spi.CaffeineCachingProvider");
~~~

This snippet is for **Caffeine JCache**. For Ehcache 3, the provider class is `org.ehcache.jsr107.EhcacheCachingProvider`. Do not pair vendor A's provider class name with vendor B's artifact.

## 4. Initializing Native JCache Before Spring Cache Annotations Run

Standard manual configuration sequence:

1. Select a `CachingProvider`.
2. Obtain `javax.cache.CacheManager` from the provider.
3. Create JSR-107 caches via `createCache(cacheName, MutableConfiguration)` or vendor configuration (XML, programmatic).
4. Wrap the native manager with `org.springframework.cache.jcache.JCacheCacheManager`.
5. Register the Spring manager as the `cacheManager` bean, or provide a `CachingConfigurer` when multiple Spring managers exist.
6. Enable `@EnableCaching` and invoke business beans through Spring proxies.

Condensed configuration example:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableCaching
class CacheConfiguration {

    @Bean(destroyMethod = "close")
    javax.cache.CacheManager jCacheManager() {
        CachingProvider provider = Caching.getCachingProvider(
            "com.github.benmanes.caffeine.jcache.spi.CaffeineCachingProvider");
        javax.cache.CacheManager manager = provider.getCacheManager();

        if (manager.getCache("books") == null) {
            MutableConfiguration<String, String> config =
                new MutableConfiguration<String, String>()
                    .setTypes(String.class, String.class)
                    .setStoreByValue(false);
            manager.createCache("books", config);
        }

        return manager;
    }

    @Bean
    org.springframework.cache.CacheManager cacheManager(
            javax.cache.CacheManager jCacheManager) {
        JCacheCacheManager adapter = new JCacheCacheManager(jCacheManager);
        adapter.setAllowNullValues(false);
        return adapter;
    }
}
~~~

This is a **configuration snippet**: it requires valid Spring/JCache imports, a suitable Java class, and the dependencies from section 3. `destroyMethod="close"` lets Spring call `close()` on the JCache manager when the context shuts down; provider lifecycle management should match your application topology. The complete example in section 6 includes all imports.

Key points to know:

- `getCache("books") == null` before calling `createCache`: checks that no cache with that name exists yet.
- `setTypes(String.class,String.class)` selects native key/value types; if a Spring key expression yields a `SimpleKey` or `Long` instead of a `String`, the provider may throw `ClassCastException` or `CacheException` on access.
- `setStoreByValue(false)` selects **reference semantics** for this local example. For production, store-by-value, serializers, mutability, expiry, and topology must be evaluated for your provider rather than copying this setting blindly.
- Do not declare only a `javax.cache.CacheManager` bean and omit the Spring `CacheManager` bean unless framework auto-configuration actually creates the corresponding adapter.
- `@EnableCaching` only activates advice; without an appropriate Spring `CacheManager` bean or existing cache names, runtime calls will fail rather than inventing native caches arbitrarily.
- In applications with multiple providers, specify provider class, cache URI, and classloader explicitly to avoid "same-named" caches belonging to different managers.

## 5. Keeping Spring Annotations: Vendor-Independent Business Logic

A service already using:

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#p0",
    unless = "#result == null"
)
public String findTitle(String isbn) {
    return repository.findTitle(isbn);
}

@CacheEvict(cacheNames = "books", key = "#p0")
public void rename(String isbn, String newTitle) {
    repository.rename(isbn, newTitle);
}
~~~

This is a snippet: it requires a repository and a Spring-managed bean. There are no `javax.cache.annotation.*` imports on the methods. The annotations remain Spring's; **only the CacheManager configuration changes**.

Flow:

- First call to `findTitle("ISBN-A")` through the proxy: Spring looks up the `books` cache, builds the key via SpEL `#p0`, and the JCache adapter reads the native cache. On a miss, it executes the method, then Spring puts the result into JCache.
- Second call with the same key: hit, Spring retrieves the value from the JCache adapter and returns immediately; the repository is not called.
- `rename("ISBN-A", "...")` returns normally: Spring `@CacheEvict` deletes the `"ISBN-A"` entry from the `books` cache.
- Subsequent read: miss, the method queries the source to fetch the updated title.
- If the method returns null, `unless="#result == null"` skips caching the null result. Because null support in JCache is conditional, this explicit policy is clearer and easier to test than relying on provider defaults.

**You do not need to rewrite `@Cacheable` to `@CacheResult` just because the storage uses JCache.** That is the main benefit of Spring's caching abstraction: teams can swap the underlying implementation while keeping most service annotations intact.

## 6. Complete Example: Spring @Cacheable/@CachePut/@CacheEvict on Caffeine JCache

This program uses **JDK 17+**, Maven, Spring Framework **6.2.19**, the `javax.cache` 1.1.1 API, and **Caffeine JCache 3.2.4**. It is a local in-JVM JCache provider; no Redis, external server, or XML is needed.

Three Spring annotations are used:

- `@Cacheable`: read from cache if present; on miss, execute `findTitle`.
- `@CachePut`: always execute the method, then write the new result to the entry.
- `@CacheEvict`: after the method updates the source data successfully, remove the stale entry.

### 6.1. File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-annotations-jcache-provider</artifactId>
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
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context-support</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>javax.cache</groupId>
            <artifactId>cache-api</artifactId>
            <version>1.1.1</version>
        </dependency>
        <dependency>
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>jcache</artifactId>
            <version>3.2.4</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

These are the **complete direct dependencies** for the example. `spring-context-support` contains `JCacheCacheManager`. Do not use `CaffeineCacheManager` in this example: that class is Spring's native Caffeine adapter, not JSR-107's `JCacheCacheManager`.

### 6.2. File src/main/java/demo/SpringJCacheDemo.java

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import javax.cache.Caching;
import javax.cache.configuration.MutableConfiguration;
import javax.cache.spi.CachingProvider;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.jcache.JCacheCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class SpringJCacheDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {

        @Bean(destroyMethod = "close")
        public javax.cache.CacheManager jCacheManager() {
            CachingProvider provider = Caching.getCachingProvider(
                "com.github.benmanes.caffeine.jcache.spi.CaffeineCachingProvider");
            javax.cache.CacheManager manager = provider.getCacheManager();

            if (manager.getCache("books") == null) {
                MutableConfiguration<String, String> config =
                    new MutableConfiguration<String, String>()
                        .setTypes(String.class, String.class)
                        .setStoreByValue(false);
                manager.createCache("books", config);
            }
            return manager;
        }

        @Bean
        public org.springframework.cache.CacheManager cacheManager(
                javax.cache.CacheManager jCacheManager) {
            JCacheCacheManager adapter = new JCacheCacheManager(jCacheManager);
            adapter.setAllowNullValues(false);
            return adapter;
        }

        @Bean
        public BookService bookService() {
            return new BookService();
        }
    }

    public static class BookService {
        private final Map<String, String> database =
                new ConcurrentHashMap<>(Map.of("ISBN-A", "Old edition"));
        private int sourceReads = 0;

        @Cacheable(cacheNames = "books", key = "#p0",
                   unless = "#result == null")
        public String findTitle(String isbn) {
            System.out.println("DB read #" + (++sourceReads));
            return database.get(isbn);
        }

        @CacheEvict(cacheNames = "books", key = "#p0")
        public void renameAndInvalidate(String isbn, String title) {
            database.put(isbn, title);
        }

        @CachePut(cacheNames = "books", key = "#p0")
        public String replaceAndRefresh(String isbn, String title) {
            database.put(isbn, title);
            return title;
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            BookService service = context.getBean(BookService.class);
            javax.cache.CacheManager nativeManager =
                    context.getBean(javax.cache.CacheManager.class);
            javax.cache.Cache<String, String> nativeBooks =
                    nativeManager.getCache(
                        "books", String.class, String.class);

            System.out.println("first=" + service.findTitle("ISBN-A"));
            System.out.println("second=" + service.findTitle("ISBN-A"));
            System.out.println("native hit="
                    + nativeBooks.containsKey("ISBN-A"));

            service.renameAndInvalidate("ISBN-A", "New edition");
            System.out.println("native after evict="
                    + nativeBooks.containsKey("ISBN-A"));
            System.out.println("after evict="
                    + service.findTitle("ISBN-A"));

            service.replaceAndRefresh("ISBN-A", "Updated edition");
            System.out.println("native after put="
                    + nativeBooks.get("ISBN-A"));
            System.out.println("after put="
                    + service.findTitle("ISBN-A"));

            System.out.println("missing1="
                    + service.findTitle("NONE"));
            System.out.println("missing2="
                    + service.findTitle("NONE"));
            System.out.println("native missing="
                    + nativeBooks.containsKey("NONE"));
        }
    }
}
~~~

**Factors keeping the example strictly scoped:**

- All three annotations are imported from `org.springframework.cache.annotation.*`, **not** `javax.cache.annotation.*`.
- Both managers coexist as distinct interfaces; the Spring `cacheManager` bean acts as the adapter.
- The native `books` cache is **created beforehand** with String key/value types compatible with `key="#p0"`.
- `BookService` is a Spring bean with public/non-final methods, and the caller invokes it through the instance obtained from the context so caching advice intercepts calls.
- `unless="#result == null"` prevents putting nulls into a cache configured with `allowNullValues(false)`.
- The first two reads and the read after `@CachePut` prove cache hits; `@CacheEvict` removes the mapping so the next read reloads from the source.
- The native `javax.cache.Cache<String,String>` is read **solely to observe** the same underlying store, not used directly as a repository.

### 6.3. Run Command

From the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SpringJCacheDemo
~~~

### 6.4. Expected Output

Lines printed by the program, excluding Maven/provider logs:

~~~text
DB read #1
first=Old edition
second=Old edition
native hit=true
native after evict=false
DB read #2
after evict=New edition
native after put=Updated edition
after put=Updated edition
DB read #3
missing1=null
DB read #4
missing2=null
native missing=false
~~~

Sequential explanation:

1. The first `findTitle("ISBN-A")` misses, triggering `DB read #1`, returning `Old edition`, and Spring stores it via `JCacheCacheManager`.
2. The second call hits and prints no additional `DB read`.
3. `nativeBooks.containsKey("ISBN-A")` returns true: the data actually resides in the configured **javax.cache store**, not a separate map cache created by Spring.
4. `renameAndInvalidate` updates the source and `@CacheEvict` removes the key; `containsKey` becomes false.
5. The lookup after eviction misses and prints `DB read #2`, fetching `New edition` and caching it.
6. `replaceAndRefresh` runs the method even though a cached entry exists; `@CachePut` writes `Updated edition` to the native entry. The subsequent `findTitle` hits with no extra `DB read`.
7. `findTitle("NONE")` returns null; `unless` prevents writing. Thus both calls hit the source (`#3` and `#4`); the native cache has no `NONE` key.

**Confidence note:** this example does not depend on an external database; the output is inferred from Spring contracts and the code, though the source **was not compiled or executed in this Knowledge document**. While learning, run the command in a Maven/JDK 17 environment with the declared dependencies to verify provider version and runtime behavior. If a different provider changes behavior, re-verify accordingly.

## 7. Reading Spring Cache API and Native JCache Side by Side

Two valid paths when inspection is needed:

~~~java
// Spring abstraction, used with annotations and any Spring CacheManager.
org.springframework.cache.Cache springBooks =
    springManager.getCache("books");
org.springframework.cache.Cache.ValueWrapper wrapped =
    springBooks.get("ISBN-A");

// Native JSR-107, only when the provider is JCache.
javax.cache.Cache<String, String> nativeBooks =
    jCacheManager.getCache("books", String.class, String.class);
String value = nativeBooks.get("ISBN-A");
~~~

This snippet assumes `springManager` and `jCacheManager` already exist. The same cache name `books` in properly wired managers points to the same underlying store.

Note the contract differences:

| Aspect | Spring Cache API | Native JCache API |
| --- | --- | --- |
| Manager | `org.springframework.cache.CacheManager` | `javax.cache.CacheManager` |
| Cache | `org.springframework.cache.Cache` | `javax.cache.Cache<K,V>` |
| Read key | `get(key)` returns `Cache.ValueWrapper` or null | `get(key)` returns V or null |
| Check key existence | Distinguish null wrapper / wrapper holding null | `containsKey(key)` |
| Write | `put(key,value)` | `put(K,V)` |
| Evict by key | `evict(key)` | `remove(key)` |
| Clear entire cache | `clear()` | `removeAll()` (or appropriate provider API) |
| Key typing | Spring accepts Object; provider decides | Native cache declares K/V types and may enforce at runtime |
| Lifetime | Depends on Spring cache manager and cache instance | Depends on native manager, `Configuration`, and provider |

JCache `get(key) == null` does not always prove there is no mapping if an adapter stores a null marker under Spring's mechanism, though raw Java nulls are unsupported in the native JCache API. Use `containsKey` to check existence when genuinely required. Avoid depending on Spring's internal null marker or serializer in business logic.

**Do not mix two unrelated managers as if they shared one store.** If Spring manager A wraps JCache manager X while code queries native manager Y, results will not reflect the same cache even with identical cache names. Verify provider, URI, classloader, and lifecycle, especially when multiple JCache providers are on the classpath.

## 8. Spring Annotations vs. JCache Standard Annotations: Two Different Questions

This guide covers **Spring annotations** with **JCache storage**. Do not confuse this with **JSR-107 annotations on Spring infrastructure**; Spring also supports the reverse direction when the JCache API and `spring-context-support` are present.

| Intent | Annotations | Orchestration Infrastructure | Data Store |
| --- | --- | --- | --- |
| Keep Spring API, switch provider to JCache | `@Cacheable` / `@CachePut` / `@CacheEvict` | Spring caching infrastructure | `JCacheCacheManager` wrapping a JSR-107 provider |
| Use standard JCache annotations | `@CacheResult` / `@CachePut` / `@CacheRemove` / `@CacheRemoveAll` | Spring supports JCache annotation semantics with proper dependencies | **Can be** a JCache provider or another Spring CacheManager |
| Use native JCache manually | No annotations needed | Java code directly calling `javax.cache.Cache` | JCache provider |
| Use native Caffeine via Spring | Spring annotations | `CaffeineCacheManager` | Native Caffeine, **no JCache adapter needed** |

The annotations do not have an exact 1-to-1 mapping:

- Spring `@Cacheable` and JCache `@CacheResult` are similar, but JCache `@CacheResult` includes options for **exception caching** and `skipGet`.
- Spring `@CachePut` updates the cache using the **return value**. JCache `javax.cache.annotation.CachePut` typically uses a parameter marked `@CacheValue`; same annotation name, different semantics.
- Spring `@CacheEvict` maps closest to `@CacheRemove`; JCache has its own exception-handling rules.
- Spring `@CacheEvict(allEntries=true)` maps closest to JCache `@CacheRemoveAll`.
- `@CacheConfig` (Spring) and `@CacheDefaults` (JSR-107) both provide class-level defaults under their respective contracts.

When migrating annotations between the two standards, **do not just swap imports and keep the same arguments**. Re-examine key generation, conditions, exception semantics, return/parameter values, and cache names.

## 9. Key Generation: A Common Source of Bugs When Sharing a JCache Store

Even with the same provider, two operations can **fail to target the same entry** if keys are generated differently.

Example:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public String load(String isbn, boolean includeOutOfPrint) { ... }

@CacheEvict(cacheNames = "books", key = "#p0")
public void invalidate(String isbn) { ... }
~~~

This is not a standalone snippet. Under SpEL, both use the String `isbn` as the key. That works if variations of `includeOutOfPrint` truly do not alter the result, **but is wrong** if the boolean changes the value: two distinct business calls overwrite the same key and can return incorrect data.

**Another common pitfall:** omitting `key` in Spring causes the default `SimpleKeyGenerator` to combine all method arguments using its own rules, which is not always a String. On a JCache cache configured with `setTypes(String.class, String.class)`, a `SimpleKey` or mismatched argument type may be rejected by the native provider.

Meanwhile, with JCache `@CacheResult`, the JCache key generator follows JSR-107; by default it uses non-excluded parameters or parameters annotated with `@CacheKey`. The two key generators **must not be assumed equivalent**. If methods using both annotation sets operate on the `books` cache, design consistent key generation or separate cache names.

Recommendations:

1. Use SpEL `key = "#p0"` when the business key is genuinely just the first parameter.
2. For composite keys, use immutable types with stable `equals/hashCode` that are compatible with the provider (store-by-value may serialize keys).
3. Align `@Cacheable`, `@CachePut`, and `@CacheEvict` methods on the same cache name and key schema.
4. If tenant/locale/security scopes or query filters affect output, include them in the key or avoid sharing that cache entry across scopes.
5. Test directly whether native `javax.cache.Cache<K,V>` accepts the key/value types produced by Spring's interceptor.
6. Do not assume identical Java key handling across vendors; providers may differ in serialization, typing, and expiry behavior.

## 10. Configuring the JCache Provider: Expiry, Size, Types, and Store-by-Value

`javax.cache`'s `MutableConfiguration<K,V>` supports minimal portable settings such as key/value types, store-by-value, statistics, management, expiry policies, and listeners. Example changing expiry:

~~~java
MutableConfiguration<String, String> config =
    new MutableConfiguration<String, String>()
        .setTypes(String.class, String.class)
        .setStoreByValue(false)
        .setExpiryPolicyFactory(
            CreatedExpiryPolicy.factoryOf(
                new Duration(TimeUnit.MINUTES, 5)));
~~~

This snippet requires importing `javax.cache.expiry.CreatedExpiryPolicy`, `javax.cache.expiry.Duration`, and `java.util.concurrent.TimeUnit`. Five minutes is only an example; do not treat it as a universal default for all data.

**Do not look for a TTL attribute on Spring's `@Cacheable`—the annotation has none.** Expiry and maximum size belong to the cache provider configuration. To configure capacity, off-heap/disk tiers, persistence, cluster replication, or eviction policies, use the provider's native features or vendor configuration files; the JCache specification standardizes only a baseline set.

In particular:

- **Store-by-value:** the provider may copy values on put/get rather than keeping the same object reference. DTOs must satisfy the vendor's actual serialization or copying mechanism. Immutable types like `String` are safe for most cases.
- **Store-by-reference:** callers may see mutations on mutable objects, undermining cache correctness. Avoid returning mutable objects that consumers can modify directly.
- **Type safety:** if a cache is defined as `<String, String>`, do not pass `Long` or `SimpleKey` as keys; this causes errors or failed lookups.
- **Expiry:** a second call past TTL will miss even when annotations and proxies are configured properly; for deterministic hit tests, keep test durations short with sufficient TTL or use non-expiring config in demos.
- **Concurrency and eviction:** depending on the provider, methods may throw provider-specific `CacheException` or have distinct write-through/loader semantics.

## 11. Null, Optional.empty, and Cache Exceptions

Standard JCache **does not support null keys or null values** the way a `Map` might. Spring's `JCacheCacheManager` can **adapt nulls** via an internal holder when `allowNullValues=true` (Spring manager's default in documented versions). That means **Spring may wrap null** in a marker rather than passing a raw Java null to the native JCache store.

However, **do not assume every provider serializes that marker identically**, especially with store-by-value, type-restricted serializers, or persistence. If you do not want to cache nulls, be explicit:

~~~java
@Cacheable(cacheNames = "books",
           key = "#p0",
           unless = "#result == null")
public Book find(String isbn) {
    return repository.findOrNull(isbn);
}
~~~

This snippet requires a concrete `Book` type and repository.

- `unless` is evaluated by Spring after obtaining the result, preventing **putting** null.
- `JCacheCacheManager#setAllowNullValues(false)` causes the adapter to **reject** null puts; it does not silently skip null puts without error.
- If the method returns `Optional<Book>`, `#result` in Spring's `unless` refers to the unwrapped `Book` or `null` when `Optional.empty()`; do not call `#result.isEmpty()` as on an `Optional`.
- Catching exceptions and returning null makes Spring treat the failure as a business miss; without `unless`, this can negative-cache network or backend errors. Distinguish NotFound from Timeout/ServiceUnavailable.

### What About Exception Caching?

JSR-107's `@CacheResult` annotation has a feature to **cache selected exceptions** per its contract. Spring's `@Cacheable` **does not automatically** gain the same semantics simply because the backing store is JCache. The storage provider is only the storage layer—it does not carry JCache annotation attributes into Spring annotations. If you need exception caching, design dedicated error/idempotency policies and infrastructure, or consider using JCache annotations per the spec.

## 12. Updates, Eviction, and Consistency with a JCache Backend

`@CacheEvict(cacheNames="books", key="#p0")` invokes Spring's Cache `evict` API after the method completes normally (`beforeInvocation=false` by default), and the adapter performs the corresponding removal in JCache. It does **not** make the database and cache an atomic transaction.

A race condition can occur:

~~~text
T1  Transaction updates DB but has not committed yet
T2  Cache entry is evicted
T3  Another reader gets a cache miss; DB still returns the old value
T4  Reader populates JCache with the old value
T5  DB commits the new value
T6  Subsequent readers may still hit the stale value
~~~

This is an illustrative scenario depending on AOP advice ordering, transaction propagation, provider consistency, and network timing. To mitigate it, you can use **post-commit invalidation** via Spring's transaction-aware cache decorator/manager or transactional events. Always test with your actual JCache adapter, transaction manager, callbacks, and cache vendor; do not infer from `@Transactional` that cache eviction automatically waits for commit.

**If an update fails:** with `beforeInvocation=false`, an exception escaping the method skips annotation-driven eviction. If the underlying source was already modified outside a transaction before the exception occurred, the cached entry can become stale. Establish proper commit boundaries, outbox patterns, or reliable invalidation mechanisms.

**If the provider fails:** native JCache may throw `javax.cache.CacheException`, and Spring caching advice propagates the error to the caller under the default `CacheErrorHandler`. Put appropriate logging, metrics, and degradation policies in place; ignoring eviction failures can leave stale data behind.

## 13. Proxy Boundaries Still Apply Even with JSR-107 Storage

Changing the backing store does not change how Spring annotations are triggered:

~~~java
@Service
public class BookFacade {
    public String readTwice(String isbn) {
        return findCached(isbn); // internal self-invocation on the same instance
    }

    @Cacheable(cacheNames = "books", key = "#p0")
    public String findCached(String isbn) {
        return repository.find(isbn);
    }
}
~~~

This is a snippet lacking full repository/imports. In default proxy mode, calling `this.findCached(...)` inside the target **bypasses the Spring caching proxy**, so the annotation may not run. The JCache provider has no knowledge of annotations on internally invoked Java methods; it only acts when the adapter sends a request.

Therefore:

- Place cached methods in a separate bean and call them via a Spring-managed reference, or call the public cached method directly from an external caller through the proxy.
- Do not instantiate services with `new` when AOP interception is needed.
- Place annotations on public implementation methods, avoiding private/final methods excluded by class-based proxies.
- Verify `@EnableCaching`, proxy type, \`AopUtils.isAopProxy(bean)\`, `cacheNames`, keys, and the active Spring manager.
- Do not assume switching storage to JCache "fixes proxy issues automatically".

## 14. Spring Boot: Auto-Configuration vs. Plain Spring Configuration

When Spring Boot has the caching starter and a JCache provider on the classpath, Boot can **auto-detect JCache** and create a corresponding Spring `CacheManager` depending on version, properties, and declared application beans. In the plain Spring configuration of section 6, we **manually create both managers** so the entire pipeline is explicit.

Do not mix manual configuration with auto-configuration unwittingly: if multiple Spring `CacheManager` beans exist, Spring cannot guess which manager a method intends to use. Select beans explicitly, use `CachingConfigurer`, name cache managers, or specify `@Cacheable(cacheManager="...")` when multiple managers are genuinely needed.

Boot properties related to JCache, such as `spring.cache.jcache.config` or `spring.cache.type=jcache`, depend on the Boot version and supported providers. Always consult documentation for your running version; Boot properties placed in a plain Spring project will not create caches on their own.

**Boot's provider selection does not change the core lesson:** business methods still use Spring's `@Cacheable`; the Spring `CacheManager` adapter connects to the vendor's `javax.cache.CacheManager`.

## 15. Migrating from ConcurrentMap/Ehcache to JCache: A Safe Plan

When migrating a service from Spring's `ConcurrentMapCacheManager` to `JCacheCacheManager`, or switching JCache providers from Ehcache to Caffeine:

1. **Inventory cache names and key contracts** across all `@Cacheable`, `@CachePut`, and `@CacheEvict` methods. Do not just swap dependency coordinates.
2. **Select one JCache provider** and remove unused providers from the classpath to prevent ambiguous discovery.
3. **Create/configure caches:** initialize regions with exact names, key/value types, expiry, capacity, store-by-reference/value, and serialization.
4. **Configure the adapter:** verify that the Spring `CacheManager` bean and native JCache manager point to the exact same store.
5. **Test null/Optional handling:** default `allowNullValues` or custom serializers may behave differently than the previous provider.
6. **Test hit/evict/put:** the same key must share the same entry and reflect updated values after mutations.
7. **Evaluate concurrency:** cache loaders, expiry, stale refresh, transaction commits, and provider exception handling.
8. **Monitor metrics:** native JCache statistics/management may need explicit enabling; do not confuse Spring cache hit rates with DB query rates.
9. **Rollout:** watch out for cold caches, cache stampedes, classloader/URI mismatches, and the fact that identically named caches across nodes may be local rather than a shared distributed store.
10. **Rollback plan:** if the new provider fails latency, correctness, or serialization requirements, have a clean path back to the prior manager without serving incompatible cached data.

Do not just assert `context.getBean("cacheManager") instanceof JCacheCacheManager` and declare migration complete. Verify **actual method invocations**, native cache mappings, key/value typing, and update/eviction paths.

## 16. Common Errors and Remedies

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Cache not found | Missing `createCache("books", ...)` in native manager | Create the cache upfront or configure the provider with the right cache name |
| `@Cacheable` has no effect | Missing `@EnableCaching`, non-proxied bean, self-invocation | Enable caching infrastructure and invoke the Spring bean via proxy |
| Class `JCacheCacheManager` unresolved | Missing `spring-context-support` | Add the matching Spring module version |
| `javax.cache.Caching` missing | Missing `javax.cache:cache-api` | Add JSR-107 API 1.1.x |
| No provider found | API-only JAR without a provider JAR; wrong provider class | Add the concrete JCache provider artifact |
| Multiple CachingProviders | Ambiguous `ServiceLoader` discovery | Specify provider FQCN explicitly and audit the dependency tree |
| Native cache lacks data despite Spring hits | Querying a different `javax.cache.CacheManager` | Check provider, URI, classloader, and the Spring adapter |
| Key type mismatch | Spring produces `SimpleKey`/`Long` while native cache expects `String` | Standardize SpEL keys or configure matching key types |
| Constant cache misses | TTL too short, changing keys, `condition=false`/`unless=true` | Check annotations, keys, expiry, and source-read counters |
| Stale data returned after updates | Missing `@CacheEvict`, wrong cache name/key, transaction race | Check eviction path and after-commit semantics |
| Exception when putting null | JCache forbids raw nulls; adapter disallows nulls or serialization fails | Use `unless` or test null adaptation explicitly |
| Switched to JCache annotations and behavior changed | `@CachePut`/`@CacheResult` are not 1-to-1 equivalents | Review return/argument handling, keys, and exception semantics |
| Local hits while other nodes miss | Provider is local-only without clustering | Choose an appropriate topology; do not assume JCache implies distributed caching |
| Errors on application shutdown | Native cache manager/provider lifecycle unmanaged | Review `close()`/destroy methods and provider ownership |

## 17. Pre-Production Testing Checklist

A solid integration test suite should cover:

- [ ] Test Spring `@Cacheable` called twice with the same key: repository runs only once on cache hit.
- [ ] Test `@CachePut` writes the new result: subsequent `@Cacheable` call receives the updated value without hitting the source.
- [ ] Test `@CacheEvict`: after the update method returns normally, native `containsKey` is false and the next read reloads from source.
- [ ] Test exception during update: post-invocation eviction does not run, and transaction rollback respects boundaries.
- [ ] Test missing values: `unless="#result == null"` avoids storing nulls; a provider disallowing nulls does not break calls.
- [ ] Test exact key/value types in native JCache, especially when relying on multi-argument default keys.
- [ ] Test key/tenant/locale/permission scoping so data is never leaked across users.
- [ ] Test expiry, size-based eviction, store-by-value, and vendor serialization.
- [ ] Test when the provider is unavailable or throws `CacheException`: logging, fallback, and error handler behavior.
- [ ] Test self-invocation and proxy types; verify annotations do not run when bypassing Spring AOP.
- [ ] Test migrations with multiple providers on the classpath, URI/classloader settings, and colliding cache names.
- [ ] Test concurrency and cache consistency under your actual topology (local or distributed).
- [ ] Test lifecycle cleanup: closing `javax.cache.CacheManager` and provider resources cleanly.

**QA gate:** once native caches are initialized, the Spring adapter works, real cache hits occur, updates/evictions target the right keys, and error/expiry policies are verified, Spring annotations can be used effectively on a JCache store without rewriting business services to JSR-107 annotations.

## 18. References

- [Spring Framework — Configuring the Cache Storage](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html): configuring `JCacheCacheManager` from `javax.cache.CacheManager`; Ehcache 3 via JSR-107.
- [Spring Framework — JCache (JSR-107) Annotations](https://docs.spring.io/spring-framework/reference/integration/cache/jsr-107.html): comparing the two annotation sets, key/exception semantics, and Spring's support for JCache annotations.
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@Cacheable`, `@CachePut`, `@CacheEvict`, SpEL keys, proxies, and `unless`.
- [Spring JCacheCacheManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/jcache/JCacheCacheManager.html): manager adapter and `allowNullValues` policy.
- [Spring JCacheCache Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/jcache/JCacheCache.html): wrapper between Spring `Cache` and native JCache.
- [Ehcache 3 — JSR-107 Provider](https://www.ehcache.org/documentation/3.9/107.html): `CachingProvider`/`CacheManager` APIs and provider configuration.
- [Caffeine — JCache Provider](https://www.javadoc.io/doc/com.github.ben-manes.caffeine/jcache/3.2.4/index.html): JSR-107-compliant provider for Caffeine, `CaffeineCachingProvider` class.
- [Maven Central — Caffeine JCache](https://central.sonatype.com/artifact/com.github.ben-manes.caffeine/jcache/3.2.4): dependency coordinates and transitive JCache API.

**Key takeaway:** **Spring annotations + JCache store** = keep Spring's `@Cacheable`/`@CachePut`/`@CacheEvict` and register `org.springframework.cache.jcache.JCacheCacheManager` wrapping the provider's `javax.cache.CacheManager`. These two API layers combine cleanly without altering business annotations; the critical areas to verify carefully are **cache names, keys/types, provider setup, nulls/expiry, lifecycle, and proxy boundaries**.