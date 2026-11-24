# Spring In-Memory Cache: Configuring Static Cache Names or Dynamic Creation Mode

## 1. The Problem: Cache Region Name vs. Entry Key

Spring Cache lets you declare how data is stored and read through annotations such as `@Cacheable`, `@CachePut`, and `@CacheEvict`. A cache operation has at least two distinct pieces of information:

- **Cache name (cache region):** Selects the storage region, for example `books` or `authors`.
- **Cache key:** Selects an entry within that region, for example ISBN `"B42"`.

Example of a book retrieval method:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public String findBook(String isbn) {
    // Illustrative example: returns book information from the data source.
    return "Book(" + isbn + ")";
}
~~~

In this illustrative snippet, `books` is the *cache name* while `#p0` takes the first argument as the *key*. The `books` cache can hold many different keys. **A static list of cache names does not mean a static list of keys.**

Spring uses `CacheManager` to look up the `Cache` object by name. With Spring Framework's `ConcurrentMapCacheManager`, developers can decide whether **cache region names are declared upfront** or **created on demand when requested**.

## 2. What Is `ConcurrentMapCacheManager`?

`org.springframework.cache.concurrent.ConcurrentMapCacheManager` provides in-memory cache regions backed by Java's concurrent map structures. It is a lightweight implementation suitable for demos, testing, or applications with minimal storage policy requirements.

The manager allows you to:

- Retrieve a cache region using `getCache(String name)`.
- Inspect the managed cache names using `getCacheNames()`.
- Declare a set of names via the constructor or `setCacheNames(Collection<String>)`.
- Switch between **static mode** and **dynamic mode** depending on how `setCacheNames(...)` is configured.

It **does not inherently provide TTL, size limits, or distributed caching** like dedicated providers. Data resides inside the JVM process; two different application instances do not share the same map unless you build another coordination mechanism.

| Criterion | Static mode | Dynamic mode |
| --- | --- | --- |
| Cache regions created | Names declared upfront. | Created on demand upon `getCache(name)`. |
| A nonexistent name | Returns `null`; does not auto-create. | Can create a new cache region for that name. |
| Common configuration | Constructor with names or `setCacheNames(collection)`. | No-arg constructor or `setCacheNames(null)`. |
| Benefits | Easy to audit, catches unlisted names. | Flexible when cache regions arise at runtime. |
| Risks to control | Adding new names requires changing configuration. | Misspelled names can also create new regions, increasing memory usage. |

## 3. Dynamic Mode: Creating Cache Names on Demand

The no-arg constructor creates a `ConcurrentMapCacheManager` in **dynamic mode**:

~~~java
ConcurrentMapCacheManager manager = new ConcurrentMapCacheManager();

System.out.println(manager.getCacheNames()); // Initially: []
Cache books = manager.getCache("books");      // Creates the books region
Cache authors = manager.getCache("authors");  // Creates the authors region
~~~

This is an API illustration snippet; to compile in a program, you need to import `ConcurrentMapCacheManager` and `Cache`. A complete example is in section 6.

When a component calls `getCache("books")` for the first time, the manager does not find the name in its internal map, so it initializes a new `ConcurrentMapCache` and remembers it. Subsequent calls with the same name reuse the existing region.

~~~text
new ConcurrentMapCacheManager()
          |
          v
    dynamic mode
    getCacheNames = []
          |
          v
    getCache("books")
          |
          v
    create "books" region
          |
          v
    getCacheNames contains "books"
          |
          v
    getCache("authors")
          |
          v
    create additional "authors" region
~~~

Points to remember:

1. **Dynamically creating cache regions** does not mean entry keys must change dynamically. A single `books` region can still hold many ISBNs.
2. `getCacheNames()` reports the regions the manager is **currently managing**, not the entry keys inside a region.
3. Dynamic mode **does not automatically infer** names from method arguments. It only creates regions for names that `CacheResolver`/application code actually requests.
4. If you accidentally type `boooks` instead of `books`, the manager can create a region with the wrong name without throwing an error: this is an advantage in flexibility, but also makes configuration mistakes harder to spot.

**Operational limit:** Do not turn every request ID or arbitrary input value into a new cache name. With `ConcurrentMapCacheManager`, the number of regions can grow with the number of distinct names, and the data inside each region can also grow. Limit or validate the source of generated names; for large workloads, consider Caffeine/Redis and appropriate eviction policies.

## 4. Static Mode: Managing Only Predeclared Names

Static mode is useful when the system knows its cache regions upfront, such as `books`, `authors`, and `categories`. There are two ways to configure it.

### 4.1. Declaring via Constructor

~~~java
ConcurrentMapCacheManager manager =
        new ConcurrentMapCacheManager("books", "authors");
~~~

The constructor taking a list of names creates the requested regions and **disables automatic creation of additional names**. Therefore:

~~~java
Cache books = manager.getCache("books");       // non-null
Cache unknown = manager.getCache("invoices");   // null
~~~

The two snippets above illustrate using the same manager. `getCache("invoices")` returns `null` instead of creating a new region. If a method with `@Cacheable(cacheNames="invoices")` uses this manager, Spring cannot resolve the region requested by the annotation and may raise a configuration/runtime error when the operation is invoked. Therefore, the static list must match the names on annotations.

### 4.2. Configuring via `setCacheNames(...)`

A manager created with the no-arg constructor can be configured further:

~~~java
ConcurrentMapCacheManager manager = new ConcurrentMapCacheManager();
manager.setCacheNames(List.of("books", "authors"));
~~~

If a **non-`null`** collection is passed, the manager registers the caches with the corresponding names and operates in static mode. No new caches outside the list are created on demand.

If `null` is passed:

~~~java
manager.setCacheNames(null);
~~~

the manager returns to **dynamic mode** and is allowed to create additional regions on demand afterward.

### 4.3. Do Not Confuse `setCacheNames(null)` with Clearing Caches

`setCacheNames(null)` is a **mode-switching** operation, not a `clear()` command that deletes all entries. Caches already managed by the manager can still remain when dynamic mode is re-enabled.

Conversely, when calling `setCacheNames(collection)`, caches corresponding to names in the collection may be **recreated/replaced** to apply the configuration. Other existing caches are not necessarily removed from the map merely by this call. Therefore, do not adjust configuration while serving traffic and assume cached data remains intact. Configure at startup; if runtime changes are needed, design a migration and test the behavior of the actual Spring version in use.

| Call | Mode/Result |
| --- | --- |
| `new ConcurrentMapCacheManager()` | Dynamic mode, no regions pre-created yet. |
| `new ConcurrentMapCacheManager("books","authors")` | Static mode, two names registered. |
| `setCacheNames(List.of("books","authors"))` | Static mode, registers the declared names. |
| `setCacheNames(null)` | Dynamic mode, allows creating additional regions. |
| `getCacheNames()` | Inspect the set of names currently managed by the manager. |
| `getCache("missing")` | Dynamic: creates a new name; static: returns `null` if the name is not managed. |

## 5. Using in a Spring Application with `@Cacheable`

When `@EnableCaching` is enabled, Spring intercepts calls passing through the proxy and applies annotations. A common static manager configuration:

~~~java
@Configuration
@EnableCaching
public class CacheConfiguration {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books", "authors");
    }
}
~~~

The types above belong to Spring Framework (`@Configuration`, `@EnableCaching`, `@Bean`, `CacheManager`, `ConcurrentMapCacheManager`). This is a configuration snippet; a runnable example with full imports is in section 6.

A service can use:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public String getBook(String isbn) {
    return bookRepository.load(isbn);
}
~~~

Result:

- First call with a given ISBN: cache miss, executes the method, stores the entry.
- Subsequent call with the same ISBN while the entry is still valid: can hit and skip the method body.
- Static mode does not restrict the number of ISBNs inside `books`.
- If an annotation specifies an undeclared name like `booooks`, the static manager does not automatically open a new region for that typo.

**Important distinction:** `@Cacheable` handles entries on method calls; `CacheManager` controls retrieving regions. Calling `manager.getCache("books")` directly does not require `@EnableCaching`; if you want annotations to work automatically, you must enable caching and invoke methods through the Spring-managed bean/proxy properly.

## 6. Spring Boot 3 / Java 17 Demo: Testing Static and Dynamic

The demo uses two independent managers: `dynamicCacheManager` created with no arguments and `staticCacheManager` created with names `books` and `authors`. The program also switches one manager from dynamic to static and back again, observing via `getCacheNames()` and the result of `getCache(name)`.

**Create file `build.gradle`:**

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

**Create file `src/main/java/demo/CacheNamesApplication.java`:**

~~~java
package demo;

import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CacheNamesApplication {

    public static void main(String[] args) {
        SpringApplication.run(CacheNamesApplication.class, args);
    }

    @Bean("dynamicCacheManager")
    ConcurrentMapCacheManager dynamicCacheManager() {
        return new ConcurrentMapCacheManager();
    }

    @Bean("staticCacheManager")
    ConcurrentMapCacheManager staticCacheManager() {
        return new ConcurrentMapCacheManager("books", "authors");
    }

    @Bean
    CommandLineRunner demo(
            @Qualifier("dynamicCacheManager")
            ConcurrentMapCacheManager dynamic,
            @Qualifier("staticCacheManager")
            ConcurrentMapCacheManager fixed) {

        return args -> {
            System.out.println("dynamic initial = " + names(dynamic));
            System.out.println("dynamic books created = "
                    + (dynamic.getCache("books") != null));
            System.out.println("dynamic names = " + names(dynamic));

            System.out.println("static names = " + names(fixed));
            System.out.println("static books exists = "
                    + (fixed.getCache("books") != null));
            System.out.println("static invoices exists = "
                    + (fixed.getCache("invoices") != null));

            dynamic.setCacheNames(List.of("books", "authors"));
            System.out.println("static mode rejects invoices = "
                    + (dynamic.getCache("invoices") == null));

            dynamic.setCacheNames(null);
            System.out.println("dynamic mode creates invoices = "
                    + (dynamic.getCache("invoices") != null));
            System.out.println("dynamic final names = " + names(dynamic));
        };
    }

    private static String names(CacheManager manager) {
        return manager.getCacheNames().stream()
                .sorted()
                .toList()
                .toString();
    }
}
~~~

**Run:** in the project directory that already has the Gradle Wrapper, use `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows. If a compatible Gradle is installed on the machine, use `gradle bootRun`. JDK 17+ is required for the project; on the first run it may need to download dependencies from Maven Central.

Ignoring the Spring Boot banner and startup logs, **the lines intentionally printed by the demo** will appear in this order:

~~~text
dynamic initial = []
dynamic books created = true
dynamic names = [books]
static names = [authors, books]
static books exists = true
static invoices exists = false
static mode rejects invoices = true
dynamic mode creates invoices = true
dynamic final names = [authors, books, invoices]
~~~

Explanation of results:

1. The dynamic manager initially has no caches, so the list is empty.
2. `getCache("books")` creates the `books` region and makes this name appear in the list.
3. The static manager comes with two names; `invoices` has not been declared, so `getCache("invoices")` returns `null`.
4. `setCacheNames(List.of("books", "authors"))` switches the first manager to static mode, so `invoices` cannot be auto-created.
5. `setCacheNames(null)` switches back to dynamic mode. At this point `getCache("invoices")` creates a new region and the final list has `authors`, `books`, `invoices`.

The `names` helper intentionally sorts the names so stdout is deterministic and does not depend on map iteration order. The demo calls `CacheManager` directly so it does not need `@EnableCaching`; an application using `@Cacheable` still needs annotation processing enabled and methods called through a bean/proxy.

## 7. When Do You Need `CacheResolver` to Select Names at Runtime?

Dynamic mode **allows creating caches for requested names**, but it **does not automatically decide names based on method parameters**. To route caches by tenant, region, or data type, you can implement `CacheResolver`.

### 7.1. One Fixed Name, Key Contains the Tenant

If all tenants share the `tenant-books` region, you must include the tenant in the key to avoid key collisions across tenants:

~~~java
@Cacheable(cacheNames = "tenant-books",
           key = "#p0 + ':' + #p1")
public Book findForTenant(String tenantId, String bookId) {
    return repository.findForTenant(tenantId, bookId);
}
~~~

This is an illustration, depending on the application's `Book`/`repository`. The region name remains fixed as `tenant-books`; the new key is `tenantId:bookId`. The key formatting rule needs to avoid collisions when inputs contain separator characters and must ensure the tenant has already been authenticated at the business layer.

### 7.2. Each Tenant Uses a Separate Cache Region

If business requirements genuinely need a separate region per tenant, a resolver can use runtime parameters to choose the name. The **configuration snippet** below requires importing `CacheResolver`, `Cache`, `CacheManager`, `CacheOperationInvocationContext`, `Collection`, `List`, and Spring annotations if used directly:

~~~java
@Component("tenantCacheResolver")
public class TenantCacheResolver implements CacheResolver {

    private final CacheManager manager;

    public TenantCacheResolver(
            @Qualifier("dynamicCacheManager") CacheManager manager) {
        this.manager = manager;
    }

    @Override
    public Collection<? extends Cache> resolveCaches(
            CacheOperationInvocationContext<?> context) {
        Object[] args = context.getArgs();
        if (args.length < 2 || !(args[0] instanceof String tenantId)) {
            throw new IllegalArgumentException("Missing tenant id");
        }
        if (!tenantId.matches("[A-Za-z0-9_-]{1,40}")) {
            throw new IllegalArgumentException("Invalid tenant id");
        }

        Cache cache = manager.getCache("tenant-" + tenantId);
        if (cache == null) {
            throw new IllegalStateException("Cannot resolve tenant cache");
        }
        return List.of(cache);
    }
}
~~~

With the service:

~~~java
@Cacheable(cacheResolver = "tenantCacheResolver", key = "#p1")
public Book findForTenant(String tenantId, String bookId) {
    return repository.findForTenant(tenantId, bookId);
}
~~~

At this point:
- `tenantId` determines the **region name**, for instance `tenant-a`.
- `bookId` determines the **key** inside that tenant's region.
- The region can be created when the resolver calls `getCache` on the dynamic manager.

The resolver is what decides which cache to use for an invocation. Do not declare both `cacheManager` and `cacheResolver` on the same operation because these two attributes are mutually exclusive. The resolver also needs to be registered as a Spring bean under the referenced name. If you only have fixed regions like `books` and `authors`, a custom resolver solution is usually unnecessary.

**Warning:** Cache names are not a security layer. You must enforce tenant authorization independently, validate names before creating them, limit the number of regions, and monitor memory. If users can arbitrarily create new `tenant-id` values, the local map can grow indefinitely.

## 8. Choosing Static vs. Dynamic and Operational Pitfalls

| Scenario | Recommendation |
| --- | --- |
| Three fixed regions: `books`, `authors`, `orders`. | Choose static mode to control names. |
| Many ISBN keys but only one `books` region. | Still use static mode; keys are not regions. |
| Region names generated per controlled runtime tenant. | Dynamic manager + appropriate resolver; cap the number of regions. |
| Want to catch misspelled cache names early. | Static mode and integration tests against annotation names. |
| Want TTL, max-size, or good eviction statistics. | Consider a dedicated cache provider like Caffeine. |
| Need to share cache across multiple JVMs. | Use an appropriate shared backend like Redis, do not rely on local ConcurrentMap. |

### Common Mistakes

1. **Accessing an unfamiliar name returns `null`:** The static manager might not include that name; check the constructor/`setCacheNames` and `@Cacheable(cacheNames=...)`.
2. **A misspelled name becomes a real region:** Dynamic mode creates new regions on demand; use constants, tests, and static mode where appropriate.
3. **Confusing cache names with keys:** A single fixed region still holds many entries; use `key`/`KeyGenerator` to design entry keys.
4. **Using `setCacheNames(collection)` as a command to clear all caches:** This is region configuration, not an API to clear all entries; some regions are reinitialized, others may remain.
5. **Creating a region for every request ID:** Uncontrolled name growth consumes memory, especially with a map cache that has no TTL.
6. **Using region names as a substitute for tenant security:** A cache only holds data; access permissions must be checked at the business layer.
7. **Assuming dynamic mode builds names from method parameters:** A `CacheResolver` or cache management logic must determine the name; the manager's mode only supplies a region for the requested name.
8. **Thinking in-memory caches auto-share across instances:** `ConcurrentMapCacheManager` keeps state per JVM and does not synchronize across multiple nodes.

## 9. Self-Check Questions

**Question 1.** What mode does `new ConcurrentMapCacheManager()` create the manager in?

**Answer:** Dynamic mode, which can create new cache regions when `getCache(name)` is called.

**Question 2.** How does `new ConcurrentMapCacheManager("books", "authors")` handle `getCache("invoices")`?

**Answer:** Static mode does not auto-create the undeclared `invoices` region; the method returns `null`.

**Question 3.** Does `setCacheNames(null)` delete all entries in the cache?

**Answer:** No. It switches the manager to dynamic mode; evicting/clearing entries is a separate operation.

**Question 4.** Can a cache named `books` hold 10,000 different entry keys even when the manager is in static mode?

**Answer:** Yes. Static mode restricts cache region names, not the number of keys.

**Question 5.** If you want to create a region per tenant ID at runtime, is `@Cacheable(cacheNames="tenant-" + id)` sufficient?

**Answer:** No. Annotations do not allow concatenating names as runtime Java expressions like that. Use a single fixed name with the tenant in the key, or use a custom `CacheResolver` to select the region dynamically.

**Question 6.** Why does dynamic mode need rules to limit the number of cache names?

**Answer:** Each new name can create an in-memory cache region; if names are unbounded, the number of regions and the amount of data kept in RAM can also grow uncontrollably.

**Key Takeaway:** With `ConcurrentMapCacheManager`, the no-arg constructor defaults to allowing **dynamic cache region creation**; the constructor with a list of names or `setCacheNames(collection)` sets a **static list of regions**. `setCacheNames(null)` allows creating additional dynamic regions again. Always distinguish cache region names from keys, and never use dynamic mode as a source of unbounded in-memory regions.

## References

- [Spring Framework — ConcurrentMapCacheManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html) — constructor, `setCacheNames`, `getCache`, `getCacheNames`.
- [Spring Framework — Configuring the Cache Storage](https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html).
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html) — cache names, cache resolver, and entry keys.