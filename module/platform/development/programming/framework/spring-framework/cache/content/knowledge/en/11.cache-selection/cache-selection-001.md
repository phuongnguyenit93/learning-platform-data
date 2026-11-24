# Selecting a CacheManager by Bean Name on Operations in Spring Cache

> **Context:** Spring Framework – Cache · **Group:** Cache region selection.  
> **Objective:** distinguish `CacheManager` from `Cache`; specify the right `CacheManager` bean on `@Cacheable`, `@CachePut`, and `@CacheEvict`; understand the precedence of method-level, class-level, and global configurations; implement, run, and verify an application with multiple managers.

## 1. Selecting a manager differs from selecting a cache region

The Spring Cache abstraction uses two objects with different responsibilities:

- **`CacheManager`:** the component that manages cache regions, providing the `Cache getCache(String name)` API and a list of cache names. A manager can be `ConcurrentMapCacheManager`, `CaffeineCacheManager`, `RedisCacheManager`, or a custom implementation.
- **`Cache`:** the specific region that stores data by key. For example, a region named `products` has an entry with key `"P42"` and its corresponding value.

With the annotation:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public Product getProduct(String id) {
    return repository.find(id);
}
```

Spring retrieves the `products` region through the **default manager/resolver**. If the ApplicationContext has a single suitable manager, this syntax is usually sufficient. However, when an application has **two or more managers**, you must know which manager the operation will retrieve `products` from.

Explicit specification:

```java
@Cacheable(
    cacheNames = "products",
    cacheManager = "redisCacheManager",
    key = "#p0"
)
public Product getProduct(String id) {
    return repository.find(id);
}
```

This is a snippet inside a Spring-managed service that has `Product` and a repository, **not a standalone Java file**.

The three values in the annotation have distinct meanings:

| Attribute | Question answered | Illustrative value |
|---|---|---|
| `cacheManager` | Which **manager bean** in the Spring context should be used? | `"redisCacheManager"` |
| `cacheNames` (alias: `value`) | Within the selected manager, which **region** should be used? | `"products"` |
| `key` | Within that region, which **entry** should be accessed? | `#p0`, e.g. `"P42"` |

**`cacheManager` is a bean name string, not SpEL.** `cacheManager="#p0"` is not understood by Spring as selecting a manager by argument. If you need dynamic selection per request, use `CacheResolver` (Section 7).

The bean name also does not guarantee the backend type. A bean named `redisCacheManager` but declared from `ConcurrentMapCacheManager` is still an in-memory manager; verify the actual implementation and configuration.

### Two caches with the same name do not necessarily share data

Two manager beans can both provide a `products` region, yet each region is completely independent:

```text
Spring ApplicationContext
├── fastCacheManager    (Caffeine or ConcurrentMap)
│   └── products
│       └── key=P42 → value=A
└── sharedCacheManager  (Redis or another backend)
    └── products
        └── key=P42 → value=B
```

If method A uses `cacheManager="fastCacheManager"` while method B uses `cacheManager="sharedCacheManager"`, the two methods do not automatically cross-read the cache. **Matching `cacheNames` does not link two backends**; only when the implementations of both beans actually point to the same store/namespace can data overlap.

## 2. Which annotations support `cacheManager`?

All three core Spring Cache operations allow selecting a manager by bean name:

**`@Cacheable` — check the cache first, compute and store on a miss:**

```java
@Cacheable(cacheNames = "books", cacheManager = "fastCacheManager",
           key = "#p0")
public Book findBook(String isbn) {
    return repository.findByIsbn(isbn);
}
```

**`@CachePut` — always invoke the method, then put the result into the cache:**

```java
@CachePut(cacheNames = "books", cacheManager = "fastCacheManager",
          key = "#p0")
public Book reloadBook(String isbn) {
    return repository.reload(isbn);
}
```

**`@CacheEvict` — request deletion of an entry or cache region:**

```java
@CacheEvict(cacheNames = "books", cacheManager = "fastCacheManager",
            key = "#p0")
public void deleteBook(String isbn) {
    repository.delete(isbn);
}
```

These snippets illustrate usage on a service that already has a repository; they are not a separately compilable program. When evicting, `@CacheEvict` executes by default **after the method completes successfully**, unless `beforeInvocation=true` is used.

The common principle is that **the manager is chosen at each cache operation**, not based on the return type or inferred from the method name. Therefore, the same class can have a method that reads from a local cache and a method that reads from Redis by specifying two different bean names.

### Valid and invalid syntax

Valid:

```java
@Cacheable(cacheNames = "books", cacheManager = "fastCacheManager",
           key = "#p0")
public Book find(String isbn) { /* ... */ }
```

Invalid because **two ways of resolving the cache are specified on the same operation**:

```java
@Cacheable(
    cacheNames = "books",
    cacheManager = "fastCacheManager",
    cacheResolver = "dynamicCacheResolver")
public Book find(String isbn) { /* ... */ }
```

`cacheManager` and `cacheResolver` are **mutually exclusive**. A custom `CacheResolver` already decides which cache regions to use on its own; Spring does not allow attaching a separate manager on the same operation at the same time because it easily creates false expectations.

Similarly, `key` and `keyGenerator` must not be declared together on one operation. Selecting a manager does not automatically change how Spring generates keys.

## 3. Declaring `CacheManager` beans properly in Spring configuration

### 3.1. Naming beans explicitly

When using Java configuration, declaring `@Bean("...")` makes the name used in annotations clear and stable:

```java
@Configuration(proxyBeanMethods = false)
@EnableCaching
class CacheConfiguration {

    @Bean("fastCacheManager")
    CacheManager fastCacheManager() {
        return new ConcurrentMapCacheManager("books");
    }

    @Bean("archiveCacheManager")
    CacheManager archiveCacheManager() {
        return new ConcurrentMapCacheManager("books");
    }
}
```

This is an illustrative configuration requiring the corresponding Spring imports; a full runnable example is in Section 5.

Meaning:

- There are **two `CacheManager` beans**: `fastCacheManager` and `archiveCacheManager`.
- Both managers create a region named `books`, but the data is independent because `ConcurrentMapCacheManager` uses each instance's own in-memory cache.
- A method declaring `cacheManager="archiveCacheManager"` will select the archive bean, even though a region named `books` also exists in fast.
- To use annotation caching, `@EnableCaching` must be enabled and methods must be invoked through the Spring proxy under the default configuration.

If no name is specified in `@Bean`, Spring usually uses the method name as the bean name. However, when renaming a method or declaring aliases, annotations depend on the exact **registered bean name**, not the Java class name.

### 3.2. Multiple CacheManagers and the default choice

When there are multiple managers but some operations do not declare `cacheManager`, the **default manager/default CacheResolver** configuration must be clear. Common approaches:

- Mark one bean as `@Primary` to resolve injection by type in the default infrastructure.
- Implement `CachingConfigurer`, providing a default `cacheManager()` or `cacheResolver()`.
- Specify the manager on each operation or set a class-level default on `@CacheConfig` when appropriate.

Example:

```java
@Bean("fastCacheManager")
@Primary
CacheManager fastCacheManager() {
    return new ConcurrentMapCacheManager("books", "defaults");
}

@Bean("archiveCacheManager")
CacheManager archiveCacheManager() {
    return new ConcurrentMapCacheManager("books");
}
```

These two methods are snippets inside a configuration class, not a standalone file. `@Primary` **does not block** a method from specifying `cacheManager="archiveCacheManager"`. It only clarifies the default choice when Spring needs a suitable `CacheManager` bean and no more specific choice is given.

When an application has multiple cache configurations or `CachingConfigurer`, do not assume that every operation without an explicit manager always picks `@Primary` in an invariant way; verify the actual default resolver with an integration test.

### 3.3. Common errors with bean names

`"fastCacheManager"` in the annotation must match **exactly** a bean name or alias visible from the context. If the bean was renamed to `caffeineManager` while the annotation still points to `fastCacheManager`, Spring may throw a bean lookup error when the cache operation is initialized/executed.

You cannot fix the error by creating a region with the same name in the other manager: a wrong manager name is a **routing issue** even before the cache name lookup step. Use reference search in the source code, inspect `@Bean`/`@Profile`, and inspect the actual beans in the context.

## 4. Precedence among global configuration, `@CacheConfig`, and methods

Spring allows customization at three tiers:

1. **Global tier:** `@EnableCaching` infrastructure configuration with a default manager/resolver; `CachingConfigurer` can be used.
2. **Class tier:** `@CacheConfig(cacheNames=..., cacheManager=..., keyGenerator=..., cacheResolver=...)` provides default values for cache methods in the class.
3. **Method tier:** `@Cacheable`/`@CachePut`/`@CacheEvict` overrides the corresponding defaults if it specifies its own attributes.

Example:

```java
@Service
@CacheConfig(cacheNames = "books", cacheManager = "fastCacheManager")
class BookService {

    @Cacheable(key = "#p0")
    public Book findFast(String isbn) {
        return repository.findByIsbn(isbn);
    }

    @Cacheable(key = "#p0", cacheManager = "archiveCacheManager")
    public Book findArchive(String isbn) {
        return repository.findByIsbn(isbn);
    }

    @CacheEvict(key = "#p0", cacheManager = "archiveCacheManager")
    public void clearArchive(String isbn) {
        // Does not interfere with the books region of fastCacheManager.
    }
}
```

This is a snippet explaining precedence, not a standalone class (it requires `repository` and `Book`).

- `findFast` does not have its own `cacheNames` or `cacheManager`, so it uses the `books` region on `fastCacheManager` from `@CacheConfig`.
- `findArchive` **overrides only the manager** to `archiveCacheManager` while still using the cache name `books` provided by the class.
- `clearArchive` also selects archive to evict the exact entry created by `findArchive`.
- If you add a `@Cacheable(cacheNames="editions")` method in the class without declaring a manager, it uses the class-level manager `fastCacheManager` with the overridden cache name `editions`; that manager must have or allow creating the corresponding region.

**`@CacheConfig` does not enable caching**, does not create a CacheManager bean, and does not attach `@Cacheable` to all methods; it only holds *defaults*. When specific routing is needed for one method, put the attribute directly on the operation.

### Comparing the three tiers

| Configuration | Scope of application | Example |
|---|---|---|
| Application-wide default | Operations with no other choice | `CachingConfigurer.cacheManager()` |
| `@CacheConfig(cacheManager="fastCacheManager")` | Cache operations in the class that do not override | Most methods of `BookService` |
| `@Cacheable(cacheManager="archiveCacheManager")` | Only that operation | A special archive-reading method |

The class-level feature helps avoid repeating bean names, but **does not replace `@Primary`** and does not act as the default for other classes.

## 5. Standalone runnable Java 17+ demo: two managers, same region, independent values

The example uses **Java 17**, **Maven**, and **Spring Framework 6.2.12**, without needing Spring Boot or a Redis server. Two separate `ConcurrentMapCacheManager` instances prove exactly how selection by bean name works.

**Components:**

- `fastCacheManager`: the `@Primary` default manager, containing regions `books` and `defaults`.
- `archiveCacheManager`: the secondary manager, containing region `books`.
- `Books`: uses `@CacheConfig` to choose fast by default, then overrides the manager on the archive and evict methods.
- `DefaultBooks`: method without a specified manager, to verify the default.

### 5.1. Directory structure

```text
cache-manager-routing/
├── pom.xml
└── src/main/java/dev/example/routing/CacheManagerRoutingDemo.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example</groupId>
    <artifactId>cache-manager-routing</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>dev.example.routing.CacheManagerRoutingDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/dev/example/routing/CacheManagerRoutingDemo.java`**

```java
package dev.example.routing;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheConfig;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

public class CacheManagerRoutingDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            Books books = context.getBean(Books.class);
            DefaultBooks defaults = context.getBean(DefaultBooks.class);

            CacheManager fast =
                    context.getBean("fastCacheManager", CacheManager.class);
            CacheManager archive =
                    context.getBean("archiveCacheManager", CacheManager.class);

            System.out.println("separateBooks=" +
                    (fast.getCache("books") != archive.getCache("books")));

            System.out.println("fast1=" + books.fast("42"));
            System.out.println("fast2=" + books.fast("42"));

            System.out.println("archive1=" + books.archive("42"));
            System.out.println("archive2=" + books.archive("42"));

            System.out.println("default1=" + defaults.read("42"));
            System.out.println("default2=" + defaults.read("42"));

            System.out.println("putFast=" + books.updateFast("42"));
            System.out.println("fastAfterPut=" + books.fast("42"));
            System.out.println("archiveStill=" + books.archive("42"));

            books.evictArchive("42");
            System.out.println("archiveAfterEvict=" + books.archive("42"));
            System.out.println("fastStill=" + books.fast("42"));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class AppConfig {
        @Bean("fastCacheManager")
        @Primary
        public CacheManager fastCacheManager() {
            return new ConcurrentMapCacheManager("books", "defaults");
        }

        @Bean("archiveCacheManager")
        public CacheManager archiveCacheManager() {
            return new ConcurrentMapCacheManager("books");
        }

        @Bean
        public Books books() {
            return new Books();
        }

        @Bean
        public DefaultBooks defaultBooks() {
            return new DefaultBooks();
        }
    }

    @CacheConfig(cacheNames = "books", cacheManager = "fastCacheManager")
    public static class Books {
        private final AtomicInteger fastLoads = new AtomicInteger();
        private final AtomicInteger archiveLoads = new AtomicInteger();

        @Cacheable(key = "#p0")
        public String fast(String id) {
            return "fast-" + id + "#" + fastLoads.incrementAndGet();
        }

        @Cacheable(key = "#p0", cacheManager = "archiveCacheManager")
        public String archive(String id) {
            return "archive-" + id + "#" + archiveLoads.incrementAndGet();
        }

        @CachePut(key = "#p0")
        public String updateFast(String id) {
            return "new-" + id;
        }

        @CacheEvict(key = "#p0", cacheManager = "archiveCacheManager")
        public void evictArchive(String id) {
            // Does not automatically delete other caches: only runs when the method completes successfully.
        }
    }

    public static class DefaultBooks {
        private final AtomicInteger loads = new AtomicInteger();

        @Cacheable(cacheNames = "defaults", key = "#p0")
        public String read(String id) {
            return "default-" + id + "#" + loads.incrementAndGet();
        }
    }
}
```

To run, open a terminal in the `cache-manager-routing` directory:

```bash
mvn -q compile exec:java
```

The `System.out.println` lines in a fresh run, **excluding Maven/environment secondary logs**:

```text
separateBooks=true
fast1=fast-42#1
fast2=fast-42#1
archive1=archive-42#1
archive2=archive-42#1
default1=default-42#1
default2=default-42#1
putFast=new-42
fastAfterPut=new-42
archiveStill=archive-42#1
archiveAfterEvict=archive-42#2
fastStill=new-42
```

### 5.2. Interpreting the output

1. `separateBooks=true`: the two managers have two distinct `Cache("books")` objects.
2. `fast1/fast2`: `@Cacheable` on `fast` inherits `cacheManager="fastCacheManager"` from `@CacheConfig`, so the second call hits.
3. `archive1/archive2`: `archive` overrides the manager with bean name `archiveCacheManager`, still using the `books` region, without sharing entries with fast.
4. `default1/default2`: `DefaultBooks` has no `@CacheConfig`; the context default configuration selects fast manager, which has the `defaults` region.
5. `putFast=new-42`: `@CachePut` always executes the method, writing the new value into `books` of fast manager because it inherits the class-level default.
6. `fastAfterPut=new-42`: `@Cacheable` hits the value just updated by `@CachePut`.
7. `archiveStill=archive-42#1`: updating fast does not affect archive despite having the same cache name and key.
8. After `evictArchive("42")`, `archiveAfterEvict=archive-42#2` because the archive entry was evicted and the loader ran again.
9. `fastStill=new-42`: evicting archive does not evict fast.

**Proxying is a critical condition.** Methods must be invoked through the bean obtained from `AnnotationConfigApplicationContext`. If you directly instantiate `new Books()` or call `this.fast("42")` from inside the same class in default proxy mode, the interceptor may not be invoked; in that case the demo no longer proves annotation-based cache routing.

## 6. Spring Boot: multiple managers and bean names

Spring Boot also uses the Spring Framework Cache Abstraction. Boot can auto-configure a default `CacheManager` from dependencies and `spring.cache.*`, but when you define one or more manager beans yourself, the relevant auto-configuration branch typically **backs off**. Therefore, do not expect `spring.cache.type=redis` to automatically change a choice explicitly written as `cacheManager="localCacheManager"`.

An **illustrative configuration example in a Spring Boot project with Caffeine and Spring Data Redis**:

```java
@Configuration(proxyBeanMethods = false)
@EnableCaching
class MultiCacheConfig {

    @Bean("localCacheManager")
    @Primary
    CacheManager localCacheManager() {
        return new CaffeineCacheManager("products");
    }

    @Bean("sharedCacheManager")
    CacheManager sharedCacheManager(RedisConnectionFactory connectionFactory) {
        return RedisCacheManager.builder(connectionFactory).build();
    }
}
```

This requires imports from `org.springframework.cache.CacheManager`, `org.springframework.cache.caffeine.CaffeineCacheManager`, `org.springframework.data.redis.cache.RedisCacheManager`, `org.springframework.data.redis.connection.RedisConnectionFactory`, and the Spring annotations. This is **not a standalone runnable program**, because it needs dependencies, a Redis server, connection properties, serialization, and appropriate TTL/namespace settings.

On the service:

```java
@Cacheable(cacheNames = "products", cacheManager = "localCacheManager",
           key = "#p0")
public Product readLocal(String id) {
    return repository.find(id);
}

@Cacheable(cacheNames = "products", cacheManager = "sharedCacheManager",
           key = "#p0")
public Product readShared(String id) {
    return repository.find(id);
}
```

Both calls may return the same business data when the cache is fresh, yet one local region lives in the JVM and one shared region lives in Redis. When a node updates data, **they do not invalidate each other automatically**; the author must organize an appropriate eviction/invalidation flow or consistency strategy.

Things to verify at runtime:

- What are the actual `CacheManager` bean names?
- Does local Caffeine have the right TTL, size limit, and null policy?
- Does Redis have a dedicated key prefix, serializer, and valid connection?
- Do read/write/evict methods choose the **same** manager when they must operate on the same entry?
- Does the cache adapter auto-create regions by name or only allow a static list?

## 7. When to use `CacheResolver` instead of `cacheManager`?

`cacheManager="sharedCacheManager"` is a **static** manager selection for the annotation. If the logic needs to vary by tenant, region, feature flag, or arguments on each invocation, use `CacheResolver`.

Example (advanced snippet, not part of the runnable source in Section 5):

```java
@Bean("tenantCacheResolver")
CacheResolver tenantCacheResolver(
        @Qualifier("localCacheManager") CacheManager local,
        @Qualifier("sharedCacheManager") CacheManager shared) {
    return context -> {
        String tenant = (String) context.getArgs()[0];
        CacheManager selected =
                tenant.startsWith("LOCAL-") ? local : shared;
        Cache cache = selected.getCache("profiles");
        return java.util.List.of(
                java.util.Objects.requireNonNull(
                        cache, "profiles cache missing"));
    };
}
```

This snippet requires importing `CacheResolver`, `Cache`, `CacheManager`, `@Qualifier`, and `@Bean`. The demo assumes the first argument is a valid String tenant; production code must handle null inputs, access permissions, and data partitioning policies.

Usage:

```java
@Cacheable(cacheNames = "profiles", cacheResolver = "tenantCacheResolver")
public Profile findProfile(String tenantId, String userId) {
    return repository.load(tenantId, userId);
}
```

At this point, you must not add `cacheManager="localCacheManager"` to the same annotation. The resolver is the object responsible for returning the appropriate `Cache`; you must control what it returns and write tests for all branches. Do not let different tenants point to the same cache with the same `userId` key if results are isolated per tenant.

**Distinction:** `cacheResolver` selects a **set of Caches** based on the invocation; `cacheManager` specifies **one static manager bean** and Spring uses the default resolver to fetch cache names from that manager.

## 8. Read, put, and evict must align on manager, cache name, and key

### 8.1. Bug: evicting from the wrong manager

Suppose reading uses the shared manager:

```java
@Cacheable(cacheNames = "products", cacheManager = "sharedCacheManager",
           key = "#p0")
public Product read(String productId) {
    return repository.find(productId);
}
```

But the update method forgets to specify the manager:

```java
@CacheEvict(cacheNames = "products", key = "#p0")
public void update(String productId, ProductPatch patch) {
    repository.update(productId, patch);
}
```

If the default manager is local, the update operation evicts from local and **does not delete the entry sitting in the shared manager**. The system may keep returning stale data even though the update method succeeded.

The fix:

```java
@CacheEvict(cacheNames = "products", cacheManager = "sharedCacheManager",
            key = "#p0")
public void update(String productId, ProductPatch patch) {
    repository.update(productId, patch);
}
```

These are all illustrative methods requiring a real repository and business types. When using `@CachePut` to update a value, it must also point to the same manager if the goal is to update the entry used by the read method.

### 8.2. Evicting across multiple managers

If the same entity is cached in both local and shared, you can use `@Caching` with two `@CacheEvict` operations:

```java
@Caching(evict = {
    @CacheEvict(cacheNames = "products",
                cacheManager = "localCacheManager", key = "#p0"),
    @CacheEvict(cacheNames = "products",
                cacheManager = "sharedCacheManager", key = "#p0")
})
public void update(String productId, ProductPatch patch) {
    repository.update(productId, patch);
}
```

These evictions are still **not combined into an atomic transaction across the two cache backends**. One eviction may fail after the other has succeeded; design retries, after-commit events, versioned keys, or TTLs according to consistency needs.

Do not interpret `@Cacheable(cacheNames={"local","shared"},cacheManager="someManager")` as specifying two managers: in that annotation, both cache names are resolved through the **selected manager**, unless you intentionally use a custom resolver with different semantics.

### 8.3. Avoiding cache collisions and cross-permission data leaks

When routing to Redis/shared cache:

- Include `tenantId`, region, and permission scope in the key if they affect the result. Picking the right manager with a key missing the tenant can still cause severe false hits.
- Keys from `SimpleKeyGenerator` or custom objects may need a dedicated converter/serializer in Redis; do not assume that what works in a local Map behaves identically in a remote cache.
- TTL/eviction/null handling/serialization are configured on each backend. `cacheManager` only selects the access path; it does not set TTL by itself.
- If manager beans point to the same Redis namespace with different serializers, having "different beans" **does not guarantee data isolation**.

## 9. How to verify configuration and troubleshoot issues

### 9.1. Inspecting actual `CacheManager` beans

In code with an available `ApplicationContext context`:

```java
String[] names = context.getBeanNamesForType(CacheManager.class);
System.out.println(java.util.Arrays.toString(names));
```

The command above is a snippet requiring the `CacheManager` import, not a standalone class. When needed:

```java
CacheManager selected =
        context.getBean("sharedCacheManager", CacheManager.class);
System.out.println(selected.getClass().getName());
System.out.println(selected.getCacheNames());
```

The presence of the manager class does not guarantee a `Cache` region contains data; to verify specifically, call `getCache("products")` and observe hits/misses.

### 9.2. Common troubleshooting table

| Symptom | Likely cause | What to check |
|---|---|---|
| Error finding manager bean | Wrong `cacheManager` name, bean not registered, profile not active | List bean names, inspect `@Bean("...")` and context |
| “Cannot find cache named ...” | Selected manager does not manage that cache name and does not create it dynamically | Inspect `getCache(name)` and `cacheNames` of each manager |
| Method always executes despite `@Cacheable` | Missing `@EnableCaching`, self-invocation, call bypassing proxy, different key | Inspect proxy path, key/condition, hit/miss |
| Adding a manager breaks methods that omit `cacheManager` | Default CacheResolver/CacheManager became ambiguous | Declare `@Primary` or `CachingConfigurer`, test default |
| Adding `@CacheConfig` has no effect | Method is not intercepted or has a method-level override | Inspect proxy and direct annotation |
| Same `cacheNames` yields different results | Two managers have two different stores/namespaces | Inspect bean name, backend, prefix, and actual cached value |
| `@CacheEvict` does not remove entry read by `@Cacheable` | Both annotations select different manager/cache/key | Compare all three pieces of information |
| `cacheManager="#p0"` does not select by argument | Attribute takes a literal bean name | Use `CacheResolver` if runtime routing is needed |
| Error when combining `cacheManager` and `cacheResolver` | Both options are mutually exclusive | Specify only one option |
| Changing `spring.cache.type` leaves the old manager | A manual CacheManager bean causes Boot auto-config to back off | Inspect bean definitions/condition report |
| Local cache still hits after clearing Redis | Two independent managers, local not yet invalidated | Design real multi-cache invalidation |
| Shared cache returns data across tenants | Key lacks tenant/permission scope | Partition namespace and key by permissions |

### 9.3. Recommended tests

1. Test that a method with `cacheManager="fastCacheManager"` returns a hit on the second call from the right manager.
2. Test that the same key and cache name in `archiveCacheManager` keeps an independent entry.
3. Test that `@CachePut` updates only the selected manager.
4. Test that `@CacheEvict` deletes from the right backend and does not mistakenly delete from another backend.
5. Test `@CacheConfig` default and an override on a method in the same class.
6. Test that an operation without a declared manager has a clear default.
7. Test missing referenced manager bean, missing cache name, and combining `cacheManager`/`cacheResolver`.
8. For production Redis/Caffeine, test the real provider, TTL configuration, serializer, key prefix, exceptions, and after-commit eviction.
9. For multiple instances, test cross-node invalidation and stale data risks under concurrent reads/updates.
10. Verify hit/miss metrics and bean names at runtime; do not rely solely on the application starting without errors.

## 10. Which configuration approach should you choose?

| Problem | Simple choice | What to watch out for |
|---|---|---|
| Single cache backend | Default manager + cache names | `@EnableCaching` and proper key |
| Multiple backends, each method uses a fixed backend | `cacheManager="beanName"` on operation | Read/put/evict must align |
| One service mostly uses one manager | `@CacheConfig(cacheManager=...)` | Exception methods override it |
| Multiple managers and one default | `@Primary` or `CachingConfigurer` | Test operations that omit manager |
| Choose backend by tenant/argument per invocation | `CacheResolver` | Do not combine with `cacheManager` on the same operation |
| Need to evict multiple backends on update | `@Caching` with separate `@CacheEvict` annotations | No cross-backend atomicity |
| Using Boot and defining multiple managers manually | Define `@Bean`s and cache settings explicitly | Do not expect all auto-config properties to apply to manual beans |

**Remember:** the bean name is a way to *route* the operation. It does not automatically guarantee key correctness, consistency, TTL, serializer, transactions, or distributed locking support. When the architecture grows complex, a clean configuration bean and clear integration tests are far more valuable than scattering unchecked literal bean names across the codebase.

## 11. Pre-completion checklist

1. Is `@EnableCaching` present and is the method invoked through a Spring-managed proxy?
2. Do manager bean names match the `@Bean`/alias declarations and exist in the context?
3. Does the operation use a fixed manager or require a dynamic `CacheResolver`?
4. Does `cacheNames` exist in the selected manager (or is dynamic creation allowed)?
5. Does `key` include all fields affecting the result, especially tenant and permission scope?
6. Is there a clear default manager for operations that do not specify `cacheManager`?
7. Are class-level `@CacheConfig` and method-level overrides behaving as intended?
8. Do `@CachePut`/`@CacheEvict` use the **same manager, cache name, and key** as the read path they need to update?
9. Are cache backend errors, transactions, invalidation, and multi-node behavior handled?
10. Are there tests proving actual manager selection rather than only checking annotation names?

### One-sentence summary

`@Cacheable(cacheNames="books", cacheManager="archiveCacheManager", key="#p0")` means: **get the `archiveCacheManager` bean, find the `books` region inside it, then access the entry keyed by the first parameter**. If you want to select the manager per call, use `CacheResolver` rather than passing SpEL to `cacheManager`.

### Official references

- Spring Framework 6.2 — Declarative annotation-based caching; Custom Cache Resolution and `@CacheConfig`: https://www.springframework.org/spring/reference/6.2/integration/cache/annotations.html
- Spring Framework — `CacheConfig` Javadoc: https://www.springframework.org/spring/docs/6.2.x/javadoc-api/org/springframework/cache/annotation/CacheConfig.html
- Spring Framework — `Cacheable` Javadoc: https://www.springframework.org/spring/docs/6.2.x/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework — `CacheManager` Javadoc: https://www.springframework.org/spring/docs/6.2.x/javadoc-api/org/springframework/cache/CacheManager.html
- Spring Framework — `CachingConfigurer` Javadoc: https://www.springframework.org/spring/docs/6.2.x/javadoc-api/org/springframework/cache/annotation/CachingConfigurer.html
- Spring Boot — Cache auto-configuration: https://docs.spring.io/spring-boot/reference/io/caching.html
