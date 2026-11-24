# Distinguishing `cacheManager` from `cacheResolver` and the Mutual Exclusion Constraint

## 1. Core takeaway

In Spring Cache, **`cacheManager` and `cacheResolver` are both involved in identifying cache regions**, yet they play two different roles:

- **`CacheManager`** is the component that manages/looks up `Cache` objects by name. You typically configure a `CacheManager` bean representing a backend or a group of caches, then let Spring use the default cache resolution mechanism.
- **`CacheResolver`** is the strategy that **determines the set of `Cache` objects actually applied to a cache operation**. It receives the invocation context and can select caches based on runtime arguments, method, and operation metadata. The default `CacheResolver` usually relies on a `CacheManager`.
- **`cacheManager = "..."`** and **`cacheResolver = "..."`** are **two attributes for choosing the cache resolution strategy** on a cache annotation. They hold **bean names in the Spring context**, not cache names or Redis connections.
- **Do not specify both attributes on *the same cache operation*.** Spring defines them as *mutually exclusive*; attempting to specify both on the same `@Cacheable`, `@CachePut`, or `@CacheEvict` is an invalid configuration and leads to an exception when Spring processes the operation.
- `@CacheConfig` can provide defaults **at the class level**; a specific choice on an operation takes higher precedence than the class-level default. Therefore, **`@CacheConfig(cacheManager = "...")` combined with a method `@Cacheable(cacheResolver = "...")` is a valid override**, not a simultaneous declaration of both attributes *on the same operation*.

The practical question to ask is: **“Do I just need to use one known CacheManager, or do I need to compute the target cache dynamically for each invocation?”** If you only need one manager, `cacheManager` is simpler; if you need dynamic routing, write a `CacheResolver`.

## 2. How do Cache, CacheManager, and CacheResolver differ?

Let us distinguish the three objects:

| Concept | Role | Typical API | Example |
| --- | --- | --- | --- |
| `Cache` | Performs entry store/retrieve/evict operations | `get(key)`, `put(key, value)`, `evict(key)` | A cache named `books` |
| `CacheManager` | Looks up `Cache` instances managed by the manager | `getCache(name)`, `getCacheNames()` | `ConcurrentMapCacheManager` or a Redis manager |
| `CacheResolver` | Returns the set of caches to use for a specific operation | `resolveCaches(context)` | Selects a tenant/customer-tier cache at runtime |

Common relationship:

```text
@Cacheable(cacheNames = "books", cacheManager = "libraryManager")
      |
      v
Spring cache interceptor
      |
      v
Default resolver / SimpleCacheResolver
      |
      v
libraryManager.getCache("books")
      |
      v
Cache object -> lookup/put/evict per operation
```

With a custom resolver:

```text
@Cacheable(cacheResolver = "routingResolver")
      |
      v
Spring cache interceptor
      |
      v
routingResolver.resolveCaches(invocationContext)
      |
      +-- context.getArgs()
      +-- context.getMethod()
      +-- context.getTarget()
      +-- context.getOperation()
      |
      '-- selects 1 or more Cache objects at call time
                 |
                 v
           lookup / put / evict
```

**Common confusion:** `cacheNames = "books"` is the cache name, whereas `cacheManager = "libraryManager"` is the **CacheManager bean name**. They do not mean the same thing. Whether a manager supports the `"books"` cache depends on provider configuration.

`CacheManager` and `CacheResolver` are not competing backends either. A custom resolver can perfectly well **use one or more CacheManagers internally**. It decides which manager to call `getCache(...)` on and which set of caches to return.

## 3. `cacheManager`: selecting a specific manager

When an application has multiple `CacheManager`s, you can explicitly specify which manager an operation uses:

```java
@Cacheable(
    cacheNames = "books",
    cacheManager = "libraryCacheManager",
    key = "#p0"
)
public Book findBook(String id) {
    return repository.find(id);
}
```

*Illustrative snippet; `Book` and `repository` need to be defined.*

How to read this:

1. Spring identifies the cache operation as `@Cacheable`.
2. The `cacheManager` attribute requests using the `CacheManager` bean named `libraryCacheManager`.
3. The default resolver mechanism uses this manager to look up caches named `books`.
4. With the key from `#p0`, Spring checks cache hit/miss and executes `@Cacheable` behavior.

Selecting a manager is generally **static per operation configuration**. If the same method must choose a backend by `tenantId`, `region`, or data type on **each invocation**, merely writing `cacheManager = "..."` will not perform that runtime routing.

### 3.1. Example manager bean

```java
@Bean("libraryCacheManager")
CacheManager libraryCacheManager() {
    return new ConcurrentMapCacheManager("books");
}
```

*Illustrative snippet inside a Spring configuration class; requires importing `CacheManager`, `ConcurrentMapCacheManager`, and `@Bean`.*

In this example, the bean named `libraryCacheManager` manages a local `books` cache. The name `books` is not the manager bean name. How the actual cache is created and configured for TTL, serialization, size, or backend connections is the responsibility of the CacheManager/provider.

### 3.2. When to specify `cacheManager`?

Use it when:

- An application has **multiple managers** (such as local RAM and Redis), yet each method uses one fixed manager.
- Method A needs one manager and method B needs another without runtime conditions.
- You need to override the default manager configuration on a specific operation or class.

There is no need for a custom `CacheResolver` if the requirement is simply to pick a fixed manager bean. Avoid adding complexity just to replace direct manager selection.

## 4. `cacheResolver`: resolving caches per invocation

`CacheResolver` is an interface in the `org.springframework.cache.interceptor` package. Core method:

```java
Collection<? extends Cache> resolveCaches(
    CacheOperationInvocationContext<?> context
);
```

*This is an API signature for explanation; not a standalone Java class.*

`context` provides operation and invocation details. A custom resolver can rely on:

- `context.getArgs()`: input arguments, such as `tenantId`, `region`, `premium`.
- `context.getOperation()`: cache operation metadata, including declared cache names (if any).
- `context.getMethod()` and `context.getTarget()`: target method and object.
- Environment configuration, routing policies, or an application manager registry.

Example using a registered resolver:

```java
@Cacheable(
    cacheResolver = "routingResolver",
    key = "#p0"
)
public Book findBook(String id, String region) {
    return repository.find(id, region);
}
```

*Illustrative snippet; `Book` and `repository` are not yet defined.*

Here, **specifying `cacheNames` on the annotation is not mandatory** if the custom resolver picks appropriate caches on its own. Spring has supported this since Spring Framework 4.1. However, this **does not mean all configuration can be omitted**: the resolver must still return genuinely valid `Cache` objects and ensure keys/scopes fit the data.

A resolver may select **multiple caches** for an operation; lookup/put and consistency across caches follow Spring Cache mechanics, so do not return an arbitrary list if regions have different semantics. With multi-tenancy, ensure cache resolution never leaks results from one tenant to another.

### 4.1. The default mechanism actually still uses a resolver

Using `cacheManager` **does not mean Spring skips `CacheResolver`**. Spring Cache normally creates a `SimpleCacheResolver` using the configured manager to look up caches by the operation's `cacheNames`. A custom resolver is only needed when you want to **replace that selection logic**.

So the accurate picture is:

```text
Has cacheManager?
    '-- Spring builds/uses the default resolver backed by the manager

Has custom cacheResolver?
    '-- Spring uses that resolver to select Cache objects directly
```

Not:

```text
cacheManager -> one cache implementation
cacheResolver -> a completely independent cache implementation
```

A resolver can use CacheManagers themselves as dependencies. The difference is **who decides the target cache, when, and based on what data**.

## 5. Mutual exclusion constraint: do not declare both on the same operation

### 5.1. **WRONG** example

```java
// WRONG: a single @Cacheable declares both resolution mechanisms at once
@Cacheable(
    cacheNames = "books",
    cacheManager = "libraryCacheManager",
    cacheResolver = "routingResolver",
    key = "#p0"
)
public Book findBook(String id) {
    return repository.find(id);
}
```

*The snippet above is an intentionally invalid Spring configuration, not for use in a runnable demo.*

Spring will **report an error when processing the cache operation**, because a custom resolver has authority to decide the target cache; if a separate manager were still declared on the same operation, that manager might be ignored, causing confusion. Spring does not silently mix the two strategies.

**Do not assert a single fixed exception timing in all cases:** depending on metadata parsing, bean initialization, and when the operation is triggered, the error may surface during startup or on the first invocation passing through cache advice. The key point is that this is **not a valid configuration** to deploy.

### 5.2. Fix 1 — Use only `cacheManager`

```java
@Cacheable(cacheNames = "books", cacheManager = "libraryCacheManager",
           key = "#p0")
public Book findBook(String id) {
    return repository.find(id);
}
```

If every call uses the `libraryCacheManager` manager and the `books` cache, this approach is the cleanest.

### 5.3. Fix 2 — Use only `cacheResolver`

```java
@Cacheable(cacheResolver = "routingResolver", key = "#p0")
public Book findBook(String id) {
    return repository.find(id);
}
```

The resolver is responsible for supplying the cache. If the name `books` is needed, you can declare `cacheNames = "books"` for the resolver to read from the operation, or let the resolver select based on internal rules.

### 5.4. “Both attributes appearing in the same codebase” can still be valid

The constraint applies to **the same operation**, not "the entire application may only have one of the two". **Valid** example:

```java
@Service
public class BookService {
    @Cacheable(cacheNames = "books", cacheManager = "fastCacheManager")
    public Book findFast(String id) {
        return repository.find(id);
    }

    @Cacheable(cacheResolver = "routingResolver")
    public Book findRouted(String id) {
        return repository.find(id);
    }
}
```

*Illustrative snippet; `Book` and `repository` are not defined.*

The two methods declare **two separate cache operations**, each choosing **one** strategy; mutual exclusion is not violated.

Note also that `key` and `keyGenerator` form a similarly mutually exclusive pair at the operation level, though that concerns **key generation**, not manager/resolver selection.

## 6. `@CacheConfig` and class-level vs. method-level precedence

`@CacheConfig` can set defaults for `cacheNames`, `keyGenerator`, `cacheManager`, and `cacheResolver`. It **does not activate cache operations on its own**. Spring allows overriding class-level defaults with specific configuration on the operation.

Example:

```java
@Service
@CacheConfig(
    cacheNames = "books",
    cacheManager = "libraryCacheManager"
)
public class BookService {
    @Cacheable(key = "#p0")
    public Book findById(String id) {
        return repository.find(id);
    }

    @Cacheable(cacheResolver = "routingResolver", key = "#p0")
    public Book findForRegion(String id, String region) {
        return repository.findForRegion(id, region);
    }
}
```

*Illustrative snippet; types/domain classes are not declared.*

- `findById` does not specify a resolver/manager on the operation, so it uses the **class-level default**: manager `libraryCacheManager` and cache name `books`.
- `findForRegion` specifies **`cacheResolver = "routingResolver"` on the operation**; the custom resolver **overrides the default manager choice from `@CacheConfig`**. This is **not** "both `cacheManager` and `cacheResolver` on the same annotation".
- For the method using a custom resolver, the cache name `books` inherited from the class is merely metadata that the resolver may use; **the custom resolver decides the actual cache object**.

The reverse direction is also valid regarding override semantics:

```java
@CacheConfig(cacheResolver = "routingResolver")
public class BookService {
    @Cacheable(cacheNames = "books", cacheManager = "libraryCacheManager")
    public Book findFixed(String id) {
        return repository.find(id);
    }
}
```

Here, the operation-level `cacheManager` overrides the class-level default resolver. The precedence rule is **operation → class → global**. Do not place both manager and resolver side by side in **one operation**; when an override is needed, state it clearly at the operation level.

| Declaration level | Example | Interpretation |
| --- | --- | --- |
| Global | `CachingConfigurer` supplies default manager/resolver | Used when class/operation does not override |
| Class | `@CacheConfig(cacheManager = "libraryCacheManager")` | Default values for cache operations in the class |
| Operation | `@Cacheable(cacheResolver = "routingResolver")` | Dedicated choice, takes precedence over class default |
| Same operation | `@Cacheable(cacheManager = "x", cacheResolver = "y")` | **Invalid** |

To avoid ambiguity about mutual exclusion, always evaluate the **effective configuration of each operation**, rather than merely counting where the strings `cacheManager` and `cacheResolver` appear in the source code.

## 7. Runnable Java 17+ example with two CacheManagers and one custom CacheResolver

The following example uses Java 17+, Maven, Spring Boot **3.3.5**, and two independent `ConcurrentMapCacheManager`s. No Redis installation is needed; the goal is to see how a **fixed manager** differs from a **resolver picking a manager by runtime argument**.

Design:

- `cacheManager`: base manager, containing `books` and `routedBooks`.
- `premiumCacheManager`: manager for premium, containing a **separate** `routedBooks` cache.
- `@CacheConfig(cacheNames="books", cacheManager="cacheManager")`: class default.
- `standard(id)`: `@Cacheable` uses the class default manager.
- `bySegment(id, premium)`: `@Cacheable(cacheNames="routedBooks", cacheResolver="routingResolver")` overrides the class manager. The resolver selects **a cache with the same name `routedBooks`** on one of the two managers based on the second argument.
- All calls go through the Spring bean proxy so the annotations take effect.

### 7.1. Structure

```text
cache-resolution-demo/
├── pom.xml
└── src/main/java/example/resolution/
    ├── ResolutionApplication.java
    └── BookLookupService.java
```

### 7.2. File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>cache-resolution-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. File `src/main/java/example/resolution/BookLookupService.java`

```java
package example.resolution;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.annotation.CacheConfig;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
@CacheConfig(cacheNames = "books", cacheManager = "cacheManager")
public class BookLookupService {
    private final AtomicInteger standardReads = new AtomicInteger();
    private final AtomicInteger routedReads = new AtomicInteger();

    // Uses manager and cache name from @CacheConfig.
    @Cacheable(key = "#p0")
    public String standard(String id) {
        System.out.println(
            "BODY standard #" + standardReads.incrementAndGet() + " " + id
        );
        return "STD:" + id;
    }

    // Custom resolver overrides the class-level default manager.
    @Cacheable(
        cacheNames = "routedBooks",
        cacheResolver = "routingResolver",
        key = "#p0"
    )
    public String bySegment(String id, boolean premium) {
        String segment = premium ? "VIP" : "BASE";
        System.out.println(
            "BODY routed #" + routedReads.incrementAndGet()
            + " " + id + " " + segment
        );
        return segment + ":" + id;
    }
}
```

### 7.4. File `src/main/java/example/resolution/ResolutionApplication.java`

```java
package example.resolution;

import java.util.Collection;
import java.util.List;
import java.util.Objects;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.CacheResolver;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class ResolutionApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResolutionApplication.class, args);
    }

    @Bean("cacheManager")
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books", "routedBooks");
    }

    @Bean("premiumCacheManager")
    CacheManager premiumCacheManager() {
        return new ConcurrentMapCacheManager("routedBooks");
    }

    @Bean("routingResolver")
    CacheResolver routingResolver(
        @Qualifier("cacheManager") CacheManager baseManager,
        @Qualifier("premiumCacheManager") CacheManager premiumManager
    ) {
        return context -> {
            // This resolver is used only for method bySegment(id, premium).
            boolean premium = Boolean.TRUE.equals(context.getArgs()[1]);

            // Name is taken from @Cacheable(cacheNames="routedBooks").
            String cacheName = context.getOperation()
                                      .getCacheNames()
                                      .iterator()
                                      .next();

            CacheManager selected = premium ? premiumManager : baseManager;
            Cache selectedCache = Objects.requireNonNull(
                selected.getCache(cacheName),
                "Missing cache: " + cacheName
            );
            return List.of(selectedCache);
        };
    }

    @Bean
    CommandLineRunner demo(
        BookLookupService books,
        @Qualifier("cacheManager") CacheManager baseManager,
        @Qualifier("premiumCacheManager") CacheManager premiumManager
    ) {
        return args -> {
            System.out.println("STANDARD1 => " + books.standard("A"));
            System.out.println("STANDARD2 => " + books.standard("A"));

            System.out.println("BASE1 => " + books.bySegment("R", false));
            System.out.println("BASE2 => " + books.bySegment("R", false));

            System.out.println("VIP1 => " + books.bySegment("R", true));
            System.out.println("VIP2 => " + books.bySegment("R", true));

            Cache baseCache = Objects.requireNonNull(
                baseManager.getCache("routedBooks")
            );
            Cache premiumCache = Objects.requireNonNull(
                premiumManager.getCache("routedBooks")
            );

            System.out.println(
                "BASE_ENTRY => " +
                Objects.requireNonNull(baseCache.get("R")).get()
            );
            System.out.println(
                "VIP_ENTRY => " +
                Objects.requireNonNull(premiumCache.get("R")).get()
            );
        };
    }
}
```

*Note:* The `java.util.Collection` import here is not needed to compile the example; Java permits unused imports. You can remove that import when formatting code according to project conventions.

### 7.5. Running the application

Requires JDK 17+, Maven, and connectivity to a Maven repository if dependencies are not already cached:

```bash
mvn spring-boot:run
```

The lines printed by the example in order appear below; Spring Boot also prints its own startup logs:

```text
BODY standard #1 A
STANDARD1 => STD:A
STANDARD2 => STD:A
BODY routed #1 R BASE
BASE1 => BASE:R
BASE2 => BASE:R
BODY routed #2 R VIP
VIP1 => VIP:R
VIP2 => VIP:R
BASE_ENTRY => BASE:R
VIP_ENTRY => VIP:R
```

### 7.6. Why does the output demonstrate both strategies?

**STANDARD1:** method `standard("A")` gets cache name `books` and manager `cacheManager` from `@CacheConfig`. The first call misses, so the method runs, prints `BODY standard #1 A`, returns `STD:A`, and stores it in the cache.

**STANDARD2:** same cache/key, hit. The method body does not run, so there is no `BODY standard #2 A` line.

**BASE1:** `bySegment("R", false)` picks operation-level `routingResolver`, so it does not use the class-level manager as a fixed choice. The resolver sees `premium=false` and returns `baseManager.getCache("routedBooks")`. That cache does not yet have key `R`, so the method runs and returns `BASE:R`.

**BASE2:** the resolver picks the base cache again; key `R` is already present so it hits, without re-running the method.

**VIP1:** the `premium=true` parameter makes the resolver pick **another manager**: `premiumCacheManager`. Even though the cache name is still `routedBooks` and the key is still `R`, this is a **different** cache object. Therefore it misses and the method runs, returning `VIP:R`.

**VIP2:** the resolver selects the same premium cache so it hits without running the method. The `BASE_ENTRY` and `VIP_ENTRY` lines prove that key `R` exists independently in two caches managed by two different managers.

**Conditions for the demo to work:** `@EnableCaching` enables Spring cache advice; the `routingResolver` bean name matches the annotation; both managers have the `routedBooks` cache; `CommandLineRunner` invokes the Spring-injected `BookLookupService` bean so calls go through the proxy; `#p0` is the `id` parameter. The program uses `ConcurrentMapCacheManager` to demonstrate within a single JVM, without implying Redis or multi-node caching.

If bringing this mechanism into a real system, **the boolean `premium` is not an authorization credential**. Classification/tenant routing must come from a trusted source and have permission checks at the appropriate layer; cache routing does not replace authorization.

## 8. Why is choosing a cache name insufficient when there are multiple CacheManagers?

In the demo, both managers have a cache named `routedBooks`:

```text
cacheManager
    '-- routedBooks["R"] = "BASE:R"

premiumCacheManager
    '-- routedBooks["R"] = "VIP:R"
```

The two entries have the **same cache name** and the **same key**, yet belong to **two different instances** because their managers/backends differ. That is why when debugging, you should not only ask "what is the cache name?", but also determine:

- Which `CacheManager` bean is actually being used?
- If using a custom resolver: which cache instance does it select on this call?
- Is the backend/namespace shared across managers?
- Does the key include sufficient tenant, data type, version, and access-permission details?

Two different managers can point to **the same backend/namespace** depending on configuration; conversely, two caches with the same name in two local managers can be completely independent. Never assume that "same name" = "same storage", or "different bean" = "secure data isolation".

## 9. Constraint scenarios and common mistakes

### 9.1. Using both attributes on the same annotation

```java
// INVALID
@CachePut(
    cacheNames = "books",
    cacheManager = "libraryCacheManager",
    cacheResolver = "routingResolver"
)
public Book save(Book book) {
    return repository.save(book);
}
```

`@CachePut` here merely illustrates that mutual exclusion does not apply only to `@Cacheable`. Do not use this pattern on `@CacheEvict` or other operations with the same pair of attributes.

### 9.2. Confusing `cacheNames` with `cacheManager`

```java
// "books" is cache name, "libraryCacheManager" is manager bean
@Cacheable(cacheNames = "books", cacheManager = "libraryCacheManager")
public Book find(String id) {
    return repository.find(id);
}
```

If the `libraryCacheManager` bean does not exist or the manager does not have a `books` cache, Spring may report a runtime error. Do not fix it by swapping the two values with each other.

### 9.3. Assuming a resolver must return exactly one cache

`CacheResolver` returns a **collection** of caches; it can be multiple caches if the operation and application genuinely need them. However, a resolver should not return an empty set of caches or semantically mismatched regions; many operations require at least one cache and Spring may fail if no required cache is resolved.

### 9.4. Using a custom resolver while thinking `cacheNames` is required

Spring allows omitting `cacheNames` when a custom resolver selects regions itself. However, if **the resolver is written to read `context.getOperation().getCacheNames()`**, as in the demo, the method **must provide a cache name** or the resolver must have a safe fallback; do not call `iterator().next()` on an empty collection.

### 9.5. Custom resolver ignoring arguments that affect the result

Suppose a method returns data by `region` and `locale`, yet the resolver only chooses a region by `region` while the key is only `id`; calls with different locales can retrieve the wrong result. You must design **cache routing and cache keys** together to reflect every data dimension affecting the output.

### 9.6. Internal method calls bypassing the proxy

`@Cacheable`/`@CachePut`/`@CacheEvict` must be intercepted by Spring. In default **proxy mode**, calls from the same object via `this.method()` bypass the proxy, regardless of how properly the manager/resolver is configured.

### 9.7. Thinking `cacheManager` or `cacheResolver` enables caching automatically

Both attributes are merely configuration for a cache operation. You need an operation annotation, `@EnableCaching` infrastructure (or equivalent), an existing resolver/manager bean, and an actual call through a Spring proxy. `@CacheConfig(cacheManager="...")` placed alone on a class also **does not turn methods into cacheable operations**.

### 9.8. Choosing the wrong evaluation phase

A custom resolver receives the **invocation arguments** context. Do not assume the resolver has access to `#result` as an expression after the method returns; `CacheOperationInvocationContext` is not a SpEL evaluation context holding the return value. If selecting a region depends on data that only exists after the method runs, redesign the architecture or choose a suitable operation instead of relying on an `#result` that does not exist at cache-lookup time.

### 9.9. Confusing a cache provider error with a mutual exclusion configuration error

An operation specifying both manager and resolver is a **configuration error**. By contrast, an operation specifying only a valid resolver whose `getCache(name)` returns null is a **resolution/backend error**. Read the actual stack trace and metadata instead of treating them as the same root cause.

## 10. Proper design and testing for real systems

When selecting cache regions, you can use this checklist:

1. **Is one fixed manager enough?** If yes, use `cacheNames` along with `cacheManager` when the bean needs to be explicit.
2. **Are there multiple managers, with each method always tied to one manager?** Use `cacheManager` per operation or `@CacheConfig` as a class default.
3. **Must the cache vary by runtime parameters?** Use an explicit `CacheResolver`; do not also assign `cacheManager` on the same operation.
4. **Does the bean exist and have the right type?** `cacheManager` needs a `CacheManager` bean; `cacheResolver` needs a `CacheResolver` bean.
5. **Is the cache name actually resolved?** With the default resolver, verify `cacheNames`; with a custom resolver, verify the returned `Cache` collection.
6. **Does the key have enough dimensions to separate data?** Tenant, customer tier, locale, region, version, etc. must be included whenever they affect the result.
7. **Do calls go through the proxy?** Avoid self-invocation under default configuration; watch out for non-public methods and beans instantiated outside the context.
8. **Do read/write/delete paths share the same strategy?** `@Cacheable`, `@CachePut`, and `@CacheEvict` must resolve the exact same data region when business logic requires consistency.
9. **What about concurrency and invalidation?** If writing via manager A while reading via manager B, the two caches may not stay in sync automatically; design invalidation for the right backend/scope.
10. **Test cache hits/misses on every routing branch:** check both how many times the method body executes and the contents inside each cache instance.

### Option selection table

| Requirement | Option |
| --- | --- |
| One shared manager for the application | Global default CacheManager/CacheResolver |
| Select a fixed manager for one method | `@Cacheable(cacheManager="...")` or corresponding operation annotation |
| Multiple methods in a class share one manager | `@CacheConfig(cacheManager="...")` plus method-level operations |
| Select region by tenant/region/feature flag at runtime | `@Cacheable(cacheResolver="...")` with a custom resolver |
| Specify both manager and resolver on the same operation | **Not allowed**; choose one |
| Method has no cache operation | Will not be cached merely because `@CacheConfig` or a manager bean exists |

## 11. Self-check questions

**Question 1.** How does `cacheNames = "books"` differ from `cacheManager = "libraryManager"`?

**Answer:** `books` is the logical cache name needed by the operation; `libraryManager` is the name of the manager bean that can look up that cache. The manager is not the entry itself or the cache name.

**Question 2.** When is a custom `CacheResolver` needed instead of `cacheManager`?

**Answer:** When selecting a `Cache` depends on runtime context or complex logic that the default resolver based on cache names and a fixed manager cannot satisfy.

**Question 3.** Why is `@Cacheable(cacheManager="x", cacheResolver="y")` invalid?

**Answer:** Both attributes are mutually exclusive ways to choose caches on **the same operation**. A custom resolver could ignore manager x, so Spring rejects the ambiguous configuration.

**Question 4.** A class declares `@CacheConfig(cacheManager="x")`, and a method has `@Cacheable(cacheResolver="y")`. Is that a misconfiguration?

**Answer:** No. `@CacheConfig` is only a **class-level default**; the `cacheResolver` choice at the **operation level** overrides that default manager selection. That differs from putting both attributes on `@Cacheable` itself.

**Question 5.** A custom resolver returns a `Cache` from manager A or manager B depending on `premium`. Both caches are named `routedBooks` and have key `R`. Are they guaranteed to be the same entry?

**Answer:** No. Matching names alone do not mean identical cache instances; it depends on backend, namespace, and manager. In the demo, two `ConcurrentMapCacheManager`s are independent so their data is isolated.

**Question 6.** If an operation omits `cacheNames` while a custom resolver knows how to pick the cache, is that valid?

**Answer:** It can be valid. Spring allows a resolver to determine caches without a cache name on the annotation. Even so, the resolver must actually provide valid caches; if the resolver code reads `cacheNames` itself, it must handle an empty list.

**Question 7.** Does configuring `@CacheConfig(cacheResolver="routingResolver")` on a class with no method-level cache operations automatically cache its methods?

**Answer:** No. `@CacheConfig` only supplies default metadata for declared operations; it does not create caching behavior by itself.

## Official references

- Spring Framework Reference — *Default Cache Resolution* and *Custom Cache Resolution*, explaining `cacheManager`, `cacheResolver`, and mutual exclusion: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Javadoc — `@Cacheable`, attributes `cacheManager` and `cacheResolver`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Framework Javadoc — `@CacheConfig`, defaults and operation-level precedence: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/annotation/CacheConfig.html
- Spring Framework Javadoc — `CacheResolver`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/interceptor/CacheResolver.html
- Spring Framework Javadoc — `SimpleCacheResolver`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/interceptor/SimpleCacheResolver.html
