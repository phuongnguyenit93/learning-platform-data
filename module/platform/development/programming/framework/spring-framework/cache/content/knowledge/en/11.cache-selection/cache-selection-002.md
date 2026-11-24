# Multiple CacheManagers in the Same ApplicationContext — Cache Region Selection in Spring

## 1. Overview

In the Spring Framework, `CacheManager` is the interface that manages `Cache` regions. Every `@Cacheable`, `@CachePut`, and `@CacheEvict` must be bound to specific cache regions. An application can have **multiple CacheManager beans in the same ApplicationContext**: for example, caching lookup data with Caffeine per JVM, and caching shared data with Redis; or two managers using the same provider with different policies.

**Key takeaway: `cacheNames = "books"` does not by itself determine which CacheManager will be used.** The name `books` only has meaning inside the selected manager. Using a cache properly requires specifying the triple:

1. **CacheManager** — the bean/provider responsible for managing cache regions.
2. **Cache name** — the logical region, such as `books`, `prices`, `reports`.
3. **Cache key** — the specific entry, such as `"ISBN-7"` or `ProductId(7)`.

With two managers having same-named cache regions, `managerA.getCache("books")` and `managerB.getCache("books")` can be two independent data stores. If two managers are configured with the same backend, endpoint, namespace, prefix, and serializer, they can instead share data. **Independence or sharing is a result of provider configuration**, not bean names alone.

This lesson focuses on static manager selection, default manager selection, `@CacheConfig`, dynamic selection with `CacheResolver`, `CompositeCacheManager`, Spring Boot, and common consistency pitfalls.

## 2. Three distinct names that are often confused

~~~java
@Cacheable(cacheNames = "books",
           cacheManager = "fastCacheManager",
           key = "#p0")
public Book findByIsbn(String isbn) {
    return repository.findByIsbn(isbn);
}
~~~

This is **Spring illustrative code**, not runnable on its own with `javac` because `Book`, `repository`, and the configurations are not provided.

| Attribute/object | Meaning | Value in example |
|---|---|---|
| `cacheManager` | Name of the `CacheManager` bean registered with Spring | `fastCacheManager` |
| `cacheNames` | Name of the `Cache` resolved by the manager | `books` |
| `key` | SpEL expression to select the entry | `#p0`, the first parameter |
| Cache value | Result being stored | `Book` |

Conceptual diagram:

~~~text
Spring ApplicationContext
│
├── "fastCacheManager"     : CacheManager A
│   ├── Cache "books"      : {"ISBN-7" → Book A}
│   └── Cache "authors"    : {...}
│
└── "durableCacheManager"  : CacheManager B
    ├── Cache "books"      : {"ISBN-7" → Book B}
    └── Cache "reports"    : {...}
~~~

The name `durable` is just an illustrative label; **not every bean named durable has persistence**. If A and B are independent, calling evict on `fastCacheManager/books/ISBN-7` does not automatically delete `durableCacheManager/books/ISBN-7`.

Also do not confuse `@Cacheable(cacheNames = {"books", "authors"})` with selecting multiple managers: this list only refers to **multiple cache regions returned by the current cache resolver**, usually via the same manager.

## 3. Which CacheManager does Spring pick when none is specified?

`@EnableCaching` enables annotation-driven caching via a cache interceptor and proxy/advice. When there is only one `CacheManager` bean, Spring can look up the bean by type and use it as the default. When **multiple beans** coexist, an operation that does not declare a manager must have a valid default selection mechanism.

You cannot assume Spring will:
- search for a manager that has a cache name matching `cacheNames`;
- pick a bean by `@Bean` declaration order or package scanning order;
- load-balance cache operations across multiple managers;
- pick the manager that hits cached data first.

An ambiguous configuration can cause initialization or cache calls to fail (timing depends on version and wiring). You should **define an explicit policy**, rather than relying on arbitrary ordering.

| Level | API | Meaning |
|---|---|---|
| On operation | `@Cacheable(cacheManager = "beanName")` | Select a fixed manager for the method |
| On class | `@CacheConfig(cacheManager = "beanName")` | Share selection for operations in the same class |
| System-wide annotation cache default | `CachingConfigurer.cacheManager()` | Default manager for operations that do not override |
| Dynamic selection at runtime | `cacheResolver = "beanName"` | Select one or more caches per invocation |
| Fallback by cache name | `CompositeCacheManager` | Pick delegates in order, does not fan-out automatically |

`@Primary` prioritizes a bean when Spring injects by type in certain situations, **not as a business cache router**. If the system has multiple managers, configuring a default via `CachingConfigurer` and overriding explicitly by bean name is easier to understand.

## 4. Registering two CacheManagers and setting an explicit default with CachingConfigurer

In a Spring application's `CacheManagersConfiguration.java` file:

~~~java
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CachingConfigurer;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheManagersConfiguration implements CachingConfigurer {

    @Bean("fastCacheManager")
    @Override
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("books", "authors");
    }

    @Bean("durableCacheManager")
    public CacheManager durableCacheManager() {
        return new ConcurrentMapCacheManager("books", "reports");
    }
}
~~~

This is a **configuration snippet requiring Spring Framework**, not plain Java. Both managers are `ConcurrentMapCacheManager` with separate in-JVM memory: not shared across instances and without built-in TTL. Do not infer that `durableCacheManager` in the example uses a persistent store.

Explanation:

- `@Bean("fastCacheManager")` and `@Bean("durableCacheManager")` register two distinct bean names.
- `@EnableCaching` turns on annotation caching; declaring a CacheManager alone is not enough to ensure calls are intercepted.
- `CachingConfigurer.cacheManager()` returns the default manager; Spring can build a default cache resolver based on this manager.
- The `cacheManager()` method also carries `@Bean` so the manager's lifecycle is managed by the container. This pattern is recommended in the Spring Javadoc.
- `ConcurrentMapCacheManager("books", ...)` declares separate cache region names; the two instances remain independent even though `books` exists in both.

**Lifecycle warning:** `CachingConfigurer` is initialized early. Avoid complex dependencies via field injection directly inside the configurer; if dependencies are needed, see guidance on `ObjectProvider`/lazy access. With `@Configuration(proxyBeanMethods=false)`, **do not call `cacheManager()` directly as a Java method to retrieve the bean again**: there is a risk of creating unintended instances. Inject the bean by name or let the framework manage it.

In production, you can swap in Caffeine/Redis/another provider, but you must configure each manager for TTL, serializer, key-prefix, capacity, and connections. Bean names do not dictate provider policies.

## 5. Static selection on @Cacheable, @CachePut, and @CacheEvict

Two read methods using the same cache name but different managers:

~~~java
@Cacheable(cacheNames = "books",
           cacheManager = "fastCacheManager",
           key = "#p0")
public Book findFast(String isbn) {
    return repository.findByIsbn(isbn);
}

@Cacheable(cacheNames = "books",
           cacheManager = "durableCacheManager",
           key = "#p0")
public Book findDurable(String isbn) {
    return repository.findByIsbn(isbn);
}
~~~

If the two managers are truly independent, the first call to `findFast("ISBN-7")` is a cache miss in A; the first call to `findDurable("ISBN-7")` can still miss in B. A cache hit in A does not automatically create a cache hit in B.

To keep reads and evictions consistent:

~~~java
@Cacheable(cacheNames = "books",
           cacheManager = "fastCacheManager",
           key = "#p0")
public Book get(String isbn) {
    return repository.findByIsbn(isbn);
}

@CacheEvict(cacheNames = "books",
            cacheManager = "fastCacheManager",
            key = "#p0")
public void delete(String isbn) {
    repository.deleteByIsbn(isbn);
}
~~~

`@CachePut` also has the `cacheManager` attribute. All methods that read, write, and evict the **same entry** must align on **manager + cacheName + key**; if you evict in B while reading from A, the stale entry in A can remain.

`#p0` accesses the first parameter by position, so it does not depend on Java `-parameters` name metadata. However, **the key must include all data affecting the result**: tenant, locale, version, permissions where appropriate. The right manager still cannot save a key missing the tenant.

**Watch out for default keys:** `get(long id)` has one parameter so the default key is usually `id`; `update(long id, String name)` has two parameters which usually produces `SimpleKey(id, name)`. If `@CachePut` on update omits `key`, it may fail to update the entry with the same key as `get`. Do not align only the manager and forget the key.

## 6. @CacheConfig — sharing selection at the class level

When most methods of a service use one manager:

~~~java
import org.springframework.cache.annotation.CacheConfig;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
@CacheConfig(cacheNames = "books",
             cacheManager = "durableCacheManager")
class DurableBookService {

    @Cacheable(key = "#p0")
    public Book get(String isbn) {
        return repository.findByIsbn(isbn);
    }

    @CacheEvict(key = "#p0")
    public void invalidate(String isbn) {
        repository.invalidate(isbn);
    }

    @Cacheable(cacheManager = "fastCacheManager", key = "#p0")
    public Book preview(String isbn) {
        return repository.findPreview(isbn);
    }
}
~~~

This code requires `Book`, a repository, and other Spring beans. `@CacheConfig` applies default values to **the class's cache operations**, without automatically attaching `@Cacheable` to every method.

The precedence order documented by Spring:

1. Global defaults (for example `CachingConfigurer`).
2. `@CacheConfig` on the class.
3. Customization directly on the method annotation — **highest priority**.

Thus, `get` and `invalidate` in the example use `durableCacheManager`; `preview` overrides it to `fastCacheManager`. If a method does not state its own `cacheNames`, it can inherit `books` from the class.

## 7. CacheResolver — dynamic selection per invocation

`cacheManager` on an annotation is a **static** choice. If you need to resolve caches based on runtime arguments, domain context, or tenant routing, use `CacheResolver`.

Contract:

~~~java
Collection<? extends Cache> resolveCaches(
        CacheOperationInvocationContext<?> context);
~~~

The resolver receives the operation metadata and args, returning a `Collection` of `Cache`s. Implementations **must be thread-safe**.

Example routing by the first parameter `channel` (assuming this is a trusted business value, already authenticated/authorized):

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.interceptor.CacheOperationInvocationContext;
import org.springframework.cache.interceptor.CacheResolver;
import org.springframework.stereotype.Component;

@Component("channelCacheResolver")
class ChannelCacheResolver implements CacheResolver {

    private final CacheManager fastManager;
    private final CacheManager internalManager;

    ChannelCacheResolver(
            @Qualifier("fastCacheManager") CacheManager fastManager,
            @Qualifier("durableCacheManager") CacheManager internalManager) {
        this.fastManager = fastManager;
        this.internalManager = internalManager;
    }

    @Override
    public Collection<? extends Cache> resolveCaches(
            CacheOperationInvocationContext<?> context) {

        Object firstArg = context.getArgs()[0];
        if (!(firstArg instanceof String channel)) {
            throw new IllegalStateException("Expected channel argument");
        }
        CacheManager selected = "public".equals(channel)
                ? fastManager : internalManager;

        List<Cache> found = new ArrayList<>();
        for (String name : context.getOperation().getCacheNames()) {
            Cache cache = selected.getCache(name);
            if (cache == null) {
                throw new IllegalStateException(
                        "Missing cache " + name + " in selected manager");
            }
            found.add(cache);
        }
        return found;
    }
}
~~~

Annotation using the resolver:

~~~java
@Cacheable(cacheNames = "books",
           cacheResolver = "channelCacheResolver",
           key = "#p1")
public Book load(String channel, String isbn) {
    return repository.load(channel, isbn);
}
~~~

The resolver selects the manager based on `channel` (the first argument), while `#p1` selects ISBN (the second argument). When channels share a manager or there are multiple distinct tenants, design keys/names so data never mixes. Choosing channels by string is for illustration only; production code should validate enums/domain context and never let raw client strings pick a region containing sensitive data.

**Do not declare `cacheManager` and `cacheResolver` on the same operation.** Both attributes are mutually exclusive; Spring reports a configuration error because the custom resolver already decides which actual `Cache` instances will be used. Similarly, when using a custom default `CachingConfigurer.cacheResolver()`, the resolver takes precedence over `cacheManager()` on the configurer.

The resolver must be used consistently for read, put, and evict methods touching the same entry. Specifying a resolver for reads while leaving eviction on the default manager typically produces stale data.

## 8. CompositeCacheManager: fallback by cache region, not multi-write

`CompositeCacheManager` lets you declare a composite manager wrapping delegates:

~~~java
import org.springframework.cache.CacheManager;
import org.springframework.cache.support.CompositeCacheManager;

// managerA and managerB are configured and provided by the application.
CacheManager combined =
        new CompositeCacheManager(managerA, managerB);
~~~

The composite iterates delegates **in order**, picking the first manager that returns a `Cache` for the requested name. **It does not automatically fan-out get/put/evict to all delegates**, nor does it fall back to manager B when a cache key misses in A: it resolves **cache region names**, not entries by key across backends.

**Important trap:** many CacheManager implementations auto-create a cache when encountering a new name; if the first delegate always returns a `Cache` for any name, the second delegate is almost never reached. The Javadoc requires delegates to return `null` when a cache name is unknown; with supported providers, configure static cache names and verify the order.

If the goal is **routing by runtime arguments**, use `CacheResolver`. If the goal is **evicting two managers**, use two specifically targeted operations or an appropriate orchestration layer, rather than relying on `CompositeCacheManager`.

## 9. Need to evict data in two managers after a single update?

When an entity is cached independently in both managers, a single source update may need to invalidate two regions:

~~~java
@Caching(evict = {
    @CacheEvict(cacheNames = "books",
                cacheManager = "fastCacheManager",
                key = "#p0"),
    @CacheEvict(cacheNames = "books",
                cacheManager = "durableCacheManager",
                key = "#p0")
})
public void renameBook(String isbn, String newTitle) {
    repository.renameBook(isbn, newTitle);
}
~~~

This is illustrative Spring integration code; it requires importing `org.springframework.cache.annotation.Caching` and `CacheEvict`.

Limitations:

- With default `@CacheEvict`, if the method throws an exception, after-invocation eviction does not happen.
- **Two evictions do not form an atomic distributed transaction**: one backend may succeed in evicting while the other fails.
- The ordering between database transaction commit and cache eviction is affected by advice order, transaction-aware caches, and providers; do not assume by default that both caches evict only after commit.
- If two managers share the same physical namespace, evicting twice may be redundant.
- `@CacheEvict(cacheNames={"books","authors"}, cacheManager="fastCacheManager")` only deletes regions **resolved by fastCacheManager**, not in manager B.

For data requiring strict consistency, design after-commit invalidation, retry/outbox, or a reconciliation mechanism when a provider fails.

## 10. Standalone runnable Java 17 example — two managers with same-named caches

The example below **simulates** two separate CacheManagers using `Map`, without running Spring annotations. It proves that the same cache name/key can hit/miss independently.

Create file **`MultipleCacheManagersDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.function.Supplier;

public class MultipleCacheManagersDemo {
    static final class MiniCacheManager {
        final String beanName;
        final Map<String, Map<String, String>> regions = new HashMap<>();

        MiniCacheManager(String beanName) {
            this.beanName = beanName;
        }

        String cached(String cacheName, String key, Supplier<String> loader) {
            Map<String, String> region =
                    regions.computeIfAbsent(cacheName, name -> new HashMap<>());
            if (region.containsKey(key)) {
                System.out.println(beanName + "/" + cacheName + ": HIT");
                return region.get(key);
            }
            System.out.println(beanName + "/" + cacheName + ": MISS");
            String value = loader.get();
            region.put(key, value);
            return value;
        }

        void evict(String cacheName, String key) {
            Map<String, String> region = regions.get(cacheName);
            if (region != null) {
                region.remove(key);
            }
            System.out.println(beanName + "/" + cacheName + ": EVICT");
        }
    }

    public static void main(String[] args) {
        MiniCacheManager fast = new MiniCacheManager("fastCacheManager");
        MiniCacheManager durable = new MiniCacheManager("durableCacheManager");

        System.out.println(fast.cached("books", "7", () -> "fast-v1"));
        System.out.println(fast.cached("books", "7", () -> "unused"));
        System.out.println(durable.cached("books", "7", () -> "durable-v1"));
        fast.evict("books", "7");
        System.out.println(durable.cached("books", "7", () -> "unused"));
        System.out.println(fast.cached("books", "7", () -> "fast-v2"));
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac --release 17 MultipleCacheManagersDemo.java
java MultipleCacheManagersDemo
~~~

**Exact** stdout:

~~~text
fastCacheManager/books: MISS
fast-v1
fastCacheManager/books: HIT
fast-v1
durableCacheManager/books: MISS
durable-v1
fastCacheManager/books: EVICT
durableCacheManager/books: HIT
durable-v1
fastCacheManager/books: MISS
fast-v2
~~~

Explanation:

1. The fast manager misses the first time, then hits the same key `7` in the `books` region.
2. The durable manager still misses on the first call, even though the cache name `books` and key `7` match fast.
3. Evicting the key in fast **does not evict** the entry in durable.
4. Reading fast again after eviction is a miss; the loader loads `fast-v2`.
5. Both managers in the program are in-memory `HashMap`s; the name `durable` **does not imply real persistence**.

This Java code has been verified to compile targeting Java 17. It helps understand key flow, though verifying real Spring `@Cacheable` execution requires testing through a Spring proxy.

## 11. Integration testing in the same ApplicationContext

To QA the real configuration, tests must use the service bean obtained from the context, not just `new Service()`. In default proxy mode, calling `this.cachedMethod()` inside the same instance typically **bypasses the proxy**, even when the annotation specifies the right manager.

Checklist:

1. Verify the context contains the exact beans `fastCacheManager` and `durableCacheManager` (not two aliases accidentally pointing to the same bean).
2. With `CacheManager fast = context.getBean("fastCacheManager", CacheManager.class)`, verify `fast.getCache("books")` exists and uses the right backend.
3. Establish a baseline and call `findFast` twice. Verify the second call hits and the repository does not run again.
4. Call `findDurable` with the same ISBN. If the two managers are independent, the first call on durable must not rely on fast's entry.
5. Evict in A then read A/B again and compare states.
6. Test a method that does not declare a manager, confirming the `CachingConfigurer` default actually chooses the right one.
7. Test `@CacheConfig` and method-level overrides; verify cache name and key.
8. Test `CacheResolver` across runtime branches, missing cache name cases, and invalid tenants.
9. Test provider failures, rollbacks, concurrency, and clustering according to criticality.

Example assertions **placed inside a Spring/JUnit test** (incomplete imports/test fixture to run standalone):

~~~java
CacheManager fast =
        context.getBean("fastCacheManager", CacheManager.class);
CacheManager durable =
        context.getBean("durableCacheManager", CacheManager.class);

Cache first = fast.getCache("books");
Cache second = durable.getCache("books");

assertNotNull(first);
assertNotNull(second);
assertNotSame(first, second);
~~~

Two distinct `Cache` object identities are not enough to prove the backends are not shared. If using Redis, verify the endpoint, Redis namespace/key-prefix, and actual data.

## 12. Common pitfalls

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Two CacheManagers exist, method fails to select one | No clear default, ambiguous bean lookup | Use `CachingConfigurer`, `@CacheConfig`, or `cacheManager` |
| `cacheNames="books"` runs on an unexpected manager | Cache name does not determine the manager bean | Specify bean name explicitly or use a resolver |
| Evicted, yet reads still see stale data | Evicted on wrong manager/cacheName/key | Compare the triple on read and evict methods |
| Composite never uses the second delegate | First delegate auto-creates every cache name | Configure static cache names and fallback order |
| Using both `cacheManager` and `cacheResolver` | The two attributes are mutually exclusive | Use only one mechanism |
| Right manager, yet tenant receives wrong data | Key lacks tenant or resolver routing is wrong | Design keys properly and enforce access controls |
| `@CacheConfig` does not make caching work | No cache operation present or interceptor/proxy inactive | Check `@EnableCaching`, annotations, call path |
| Works locally, fails in production | Different auto-config/profile/provider | Test against real context and production config |
| `@Primary` does not distribute methods as desired | `@Primary` does not route per operation | Specify `cacheManager` or create a `CacheResolver` |
| Cache provider hits serialization error | Inconsistent key/value types, prefix, TTL, serializer | Test real provider and log per manager |
| Managers share cache name so assumed to share data | Two separate instances/namespaces | Inspect actual backend, not just names |

## 13. Production checklist

- Choose stable **bean names** that accurately describe the provider and data scope.
- List every cache name, key generator/SpEL, tenant, TTL, and provider of each corresponding manager.
- Synchronize **manager + cacheName + key** selection across reads, updates, and evictions.
- Configure an explicit default via `CachingConfigurer` if there are annotations omitting the manager.
- Use `@CacheConfig` to reduce repetition; override on methods when genuinely needed.
- Use `CacheResolver` when selection depends on runtime context, ensuring thread-safety and validating routing inputs.
- Verify `CompositeCacheManager` falls back as expected when a provider auto-creates cache names.
- Do not treat `spring.cache.type` or Boot auto-configuration as a router between two manually declared CacheManager beans.
- Set up metrics by **manager and cache name**, not just cache name.
- Test backend failures, partial evictions, rollbacks, concurrent reads/writes, and multi-node behavior when consistency is required.
- Authorization is separate security logic: do not treat manager partitioning as a substitute for access control checks.

## 14. Self-check questions

**1.** Two CacheManagers both provide `"books"`. Does `@Cacheable("books")` automatically know which manager is right?

**2.** Does `cacheManager="fastCacheManager"` reference a cache name or a Spring bean name?

**3.** A class uses `@CacheConfig(cacheManager="durableCacheManager")`, and a method overrides with `@Cacheable(cacheManager="fastCacheManager")`: which manager is used?

**4.** When selecting a manager based on runtime parameters, use `cacheManager` or `cacheResolver`?

**5.** Can both attributes be declared on the same annotation?

**6.** Why might `CompositeCacheManager` never consult its second delegate?

**7.** Does evicting `books[7]` in manager A guarantee deleting `books[7]` in manager B?

**Answers:**

1. **Not yet.** You must examine the default resolver/`CachingConfigurer` and specific wiring.
2. **The bean name** of the `CacheManager`; `"books"` is the cache region name.
3. **fastCacheManager**, because method-level overrides take precedence over class-level.
4. Use **`CacheResolver`** when routing truly depends on invocation.
5. **No.** The two mechanisms are mutually exclusive.
6. The first delegate may always return a cache (due to auto-creating new caches), so the composite never falls through to the next delegate.
7. **Not by default**; only when two beans point to a shared physical region can they interact, which requires separate verification.

## 15. References

- Spring Framework — annotation-based caching, cache resolution, and `@CacheConfig`: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — `EnableCaching` Javadoc (default selection, multiple CacheManagers): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/EnableCaching.html
- Spring Framework — `CachingConfigurer`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CachingConfigurer.html
- Spring Framework — `CacheResolver`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/CacheResolver.html
- Spring Framework — `CompositeCacheManager`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/support/CompositeCacheManager.html
- Spring Boot Reference — caching auto-configuration and cache providers: https://docs.spring.io/spring-boot/reference/io/caching.html

**Remember:** Having multiple CacheManagers in the same ApplicationContext is normal, yet **cache names do not select the manager automatically**. Choose a clear default with `CachingConfigurer`, choose statically with `cacheManager`, set class defaults with `@CacheConfig`, choose dynamically with `CacheResolver`, and do not mistake `CompositeCacheManager` for broadcast writes/evictions. Most importantly, the same data must have consistent policies for **manager, cache name, key, provider, invalidation, and access control**.