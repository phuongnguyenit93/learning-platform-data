# Choosing a Simple Cache for Testing and Appropriate Environments in Spring

## 1. Objectives and Implementations to Distinguish

Spring Cache provides an abstraction to attach caching behavior to methods; data storage is handled by `CacheManager` and `Cache`. For testing, demos, local development, or small applications running in a single JVM, a `ConcurrentMap`-based cache is usually easy to configure and observe.

Classes with similar-sounding names have different responsibilities:

- **`ConcurrentMapCache`**: a specific cache region storing key/value pairs backed by a `ConcurrentMap`.
- **`ConcurrentMapCacheManager`**: creates and manages `ConcurrentMapCache` instances by name; supports dynamic cache creation mode or a predeclared list of caches.
- **`SimpleCacheManager`**: manages a collection of pre-created `Cache` objects. It does not choose storage itself or auto-create caches by name.
- **`NoOpCacheManager`**: a cache that does not store data; typically used to disable caching in certain tests or environments.

| Implementation | How it manages | Suitable when | Main limitation |
|---|---|---|---|
| `ConcurrentMapCacheManager` | Creates `ConcurrentMapCache` by name; dynamic or static | Demos, hit/miss tests, local development | No automatic TTL/size policy, persistence, or multi-JVM sharing |
| `SimpleCacheManager` | Accepts pre-created `Cache` collection via `setCaches` | Want to declare each cache object explicitly | Must create each cache yourself; manager is not a storage engine |
| `NoOpCacheManager` | Returns no-op caches, does not store entries | Testing logic independent of caching | Cannot verify hits, eviction, or reuse |

**Distinction:** Spring Boot calls the simple auto-configured provider *Simple*; that provider is normally backed by `ConcurrentMapCacheManager`. It is **not synonymous** with the `SimpleCacheManager` class. When debugging, inspect the actual class of the `CacheManager` bean.

## 2. ConcurrentMapCacheManager: The Simplest Way to Get Started

`ConcurrentMapCacheManager` uses `ConcurrentMapCache` instances and creates caches on demand. The no-argument constructor selects **dynamic** mode:

~~~java
@Bean
CacheManager cacheManager() {
    return new ConcurrentMapCacheManager();
}
~~~

When code calls `getCache("books")`, the manager creates the `books` cache if it does not exist yet. This is convenient for demos or when the list of caches is not fixed upfront.

If you want to allow only a known set of cache names, use the constructor that takes names:

~~~java
@Bean
CacheManager cacheManager() {
    return new ConcurrentMapCacheManager("books", "authors");
}
~~~

This is **static mode**: the manager only manages declared names and does not auto-create new cache regions for unlisted names. For instance, `@Cacheable("book")` misspelled when only `books` is registered can lead to an error when the cache operation needs the `book` region. Static configuration helps catch cache name typos instead of silently creating new regions.

Both examples above are Spring configuration snippets, requiring imports for `CacheManager`, `ConcurrentMapCacheManager`, registering the `@Bean` in a configuration class, and enabling annotation caching with `@EnableCaching` when using `@Cacheable`.

### Using @Cacheable with an In-Memory Cache

~~~java
@Service
public class BookService {
    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "books", key = "#p0")
    public Book findByIsbn(String isbn) {
        return repository.findByIsbn(isbn);
    }
}
~~~

This is an illustrative Spring integration snippet; `Book` and `BookRepository` are application domain types. On the first call for an ISBN not yet in the cache, the method executes and the result is stored. Subsequent calls with the same key can receive the result from the cache without querying the repository.

The application still needs `@EnableCaching` and the method must be invoked through Spring's interception mechanism. Under the default proxy mode, self-invocation (a method calling `this.findByIsbn(...)` inside the same bean) usually bypasses the proxy and therefore does not trigger cache advice.

## 3. SimpleCacheManager: Declaring Each Cache Object

Unlike `ConcurrentMapCacheManager`, `SimpleCacheManager` accepts **existing `Cache` objects**:

~~~java
import java.util.List;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.cache.support.SimpleCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SimpleCacheConfiguration {
    @Bean
    CacheManager cacheManager() {
        SimpleCacheManager manager = new SimpleCacheManager();
        manager.setCaches(List.of(
                new ConcurrentMapCache("books"),
                new ConcurrentMapCache("authors")
        ));
        return manager;
    }
}
~~~

This is a Spring configuration, not a standalone Java program. When the bean is managed by Spring, the `InitializingBean`/`afterPropertiesSet()` lifecycle helps `SimpleCacheManager` initialize the supplied cache list. If instantiating the manager manually outside a Spring container, call the initialization mechanism per the Javadoc before use.

`SimpleCacheManager` has no storage map of its own. In the example, **`ConcurrentMapCache` is the actual cache object**; the manager only manages that collection. Different `Cache` implementations can be supplied as long as they fulfill the Spring Cache contract.

- Choose `ConcurrentMapCacheManager` when you want the manager to create caches by name, or want static mode via a list of names.
- Choose `SimpleCacheManager` when you already have concrete `Cache` objects and want to register them explicitly.
- If you need TTL, capacity limits, eviction policies, metrics, or persistence, choose a provider offering those features.

## 4. Where Is an In-Memory Cache Stored and What Are Its Limits?

`ConcurrentMapCache` uses `ConcurrentMap` as its storage structure; the default implementation is backed by `ConcurrentHashMap`. The cache resides **in the memory of the running process/JVM**:

~~~text
Spring Bean → CacheInterceptor → CacheManager
                                  |
                                  v
                         ConcurrentMapCache
                                  |
                                  v
                         ConcurrentMap<Key, Value>
                                  |
                                  v
                               JVM RAM
~~~

This has the following consequences:

1. **Restarts lose the cache:** data is not automatically persisted to a database or file.
2. **Each JVM has its own cache:** two application instances do not automatically share entries. Pod A loading `books[7]` does not mean pod B has that entry.
3. **No advanced TTL/size policies:** entries do not automatically expire over time or get evicted by capacity like Caffeine unless you add separate mechanisms.
4. **Memory can grow:** if keys are generated continuously without invalidation/clear, the map can retain many entries throughout the process's lifetime.
5. **Values are stored by reference by default:** `ConcurrentMapCacheManager` defaults to `storeByValue=false`. If callers mutate a retrieved mutable object, the cached content can be changed unintentionally.
6. **A thread-safe map does not mean atomic business logic:** ConcurrentHashMap supports concurrent map operations; it does not automatically protect multi-step transactions, side effects, or consistency across multiple services.

Prefer immutable DTOs/records or defensive copies when callers might mutate objects. If store-by-value is enabled, values must satisfy the implementation's serialization requirements.

`ConcurrentMapCacheManager` allows storing `null` by default through an internal wrapper because `ConcurrentHashMap` does not allow null values directly. This can be changed with `setAllowNullValues(false)`; when changing this setting, existing caches may be reset. Distinguish a cache miss from an entry representing null and from a NoOp cache that stores nothing.

## 5. Simple Cache Configuration in Spring Boot

If using Spring Boot with no other specific cache provider/library on the classpath, Boot can auto-configure the **Simple provider using an in-memory ConcurrentHashMap**. Cache names can be declared in `application.properties`:

~~~properties
spring.cache.cache-names=books,authors
~~~

Or YAML:

~~~yaml
spring:
  cache:
    cache-names:
      - books
      - authors
~~~

When setting a static list of names, if the application requests an undeclared cache, an error may surface only when a cache operation actually needs that region. Therefore, verify cache names in integration tests.

Notes:

- Caching must be enabled with `@EnableCaching` (or an equivalent configuration).
- Boot auto-configures a manager via provider detection when the application provides no `CacheManager` bean or matching resolver.
- `spring.cache.cache-names` is not where you configure TTL or max-size for `ConcurrentMapCacheManager`.
- Boot's `CacheManagerCustomizer` applies to managers auto-configured by Boot; if you declare your own manager bean, do not assume customizers configure it automatically.
- `spring.cache.type` can force the provider type for Boot's auto-configured manager; do not treat this property as overriding any custom cache manager bean.

The Simple provider is great for getting started and learning caching. When production caching is needed, select a provider with the required capabilities and read its configuration documentation.

## 6. Testing with a Real Cache vs. Testing Without Cache

Two testing goals are often mixed up:

| Goal | What to use | What you want to verify |
|---|---|---|
| Test service logic independently of caching | `NoOpCacheManager` or Boot no-op configuration | Business method still runs and returns the right result |
| Test `@Cacheable` hit/miss, `@CacheEvict`, `@CachePut` | Real `ConcurrentMapCacheManager` or `SimpleCacheManager` | Entries are stored, reused, updated, and evicted properly |
| Test production provider | Real provider or matching integration environment | TTL, serialization, network, cluster, and eviction |
| Test mocking only repository/service | Appropriately scoped mocks | Focuses on component contracts; does not prove cache proxy works |

### NoOpCacheManager

`NoOpCacheManager` is an implementation that stores no entries. It still satisfies the cache API so annotated code can run, yet `put` does not retain values for subsequent reuse. Methods annotated with `@Cacheable` are therefore invoked again on every call.

This is a useful option when testing logic without verifying caching or when disabling cache in a specific test profile. **Do not use `NoOpCacheManager` to test cache hits** because it is designed not to store entries.

### Spring Boot Tests Can Disable Caching Automatically

If the manager is auto-configured by Boot, you can use `@AutoConfigureCache` in Spring Boot tests to swap in a no-op implementation (depending on Boot version and test starter). Another option is configuring:

~~~properties
spring.cache.type=none
~~~

These approaches target **Boot's cache auto-configuration**. If the application defines its own `CacheManager`, isolate cache configuration into a separate class and supply an appropriate replacement test configuration; do not assume the no-op property overrides custom beans.

### Tests Verifying Caching Must Use a Storing Manager

~~~java
@SpringBootTest
class BookServiceCacheTest {
    @Autowired
    BookService service;

    @Autowired
    CacheManager cacheManager;

    @BeforeEach
    void clearCache() {
        Cache cache = cacheManager.getCache("books");
        if (cache != null) {
            cache.clear();
        }
    }

    @Test
    void reusesCachedBook() {
        Book first = service.findByIsbn("ISBN-7");
        Book second = service.findByIsbn("ISBN-7");

        assertEquals(first, second);
        assertEquals(1, service.getRepositoryCallCount());
    }
}
~~~

This is an illustrative test snippet requiring the project to provide `BookService`, the counter, and JUnit/Spring imports. `service` must be a bean retrieved from the Spring context so calls go through the proxy; creating `new BookService(...)` manually will not activate caching advice. Clear the cache between tests so results do not depend on test execution order or reused contexts. Hit/miss tests must verify how many times the repository/loader was called, not merely assert that two return values are equal.

## 7. Standalone Java 17: In-Memory Cache and No-Op

The following program simulates both policies using the JDK, **without using Spring annotations or Spring Cache classes**. It helps visualize the difference between a map-backed cache and a no-op cache.

Create file **`SimpleCacheDemo.java`**:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class SimpleCacheDemo {
    static final class InMemoryCache {
        private final ConcurrentMap<String, String> values =
                new ConcurrentHashMap<>();

        String getOrLoad(String key, Supplier<String> loader) {
            return values.computeIfAbsent(key, ignored -> loader.get());
        }

        void clear() {
            values.clear();
        }

        int size() {
            return values.size();
        }
    }

    static final class NoOpCache {
        String getOrLoad(String key, Supplier<String> loader) {
            return loader.get();
        }
    }

    public static void main(String[] args) {
        AtomicInteger loads = new AtomicInteger();
        InMemoryCache cache = new InMemoryCache();

        String first = cache.getOrLoad("ISBN-7", () -> {
            loads.incrementAndGet();
            return "Java";
        });
        String second = cache.getOrLoad("ISBN-7", () -> {
            loads.incrementAndGet();
            return "unused";
        });
        System.out.printf(
                "simple: first=%s, second=%s, loaderCalls=%d, entries=%d%n",
                first, second, loads.get(), cache.size());

        cache.clear();
        String afterClear = cache.getOrLoad("ISBN-7", () -> {
            loads.incrementAndGet();
            return "Java";
        });
        System.out.printf(
                "simple after clear: value=%s, loaderCalls=%d, entries=%d%n",
                afterClear, loads.get(), cache.size());

        AtomicInteger noOpLoads = new AtomicInteger();
        NoOpCache noOp = new NoOpCache();
        String noOpFirst = noOp.getOrLoad("ISBN-7", () -> {
            noOpLoads.incrementAndGet();
            return "Java";
        });
        String noOpSecond = noOp.getOrLoad("ISBN-7", () -> {
            noOpLoads.incrementAndGet();
            return "Java";
        });
        System.out.printf(
                "no-op: first=%s, second=%s, loaderCalls=%d%n",
                noOpFirst, noOpSecond, noOpLoads.get());
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac --release 17 SimpleCacheDemo.java
java SimpleCacheDemo
~~~

**Exact** stdout:

~~~text
simple: first=Java, second=Java, loaderCalls=1, entries=1
simple after clear: value=Java, loaderCalls=2, entries=1
no-op: first=Java, second=Java, loaderCalls=2
~~~

Analysis:

1. Initially the cache is empty; the loader runs and stores `Java` under key `ISBN-7`.
2. The second call with the same key returns the stored value; the loader does not run again.
3. After `clear()`, the entry is removed; the next call runs the loader again and the cache holds one new entry.
4. `NoOpCache` stores nothing, so both calls execute the loader.
5. `ConcurrentHashMap.computeIfAbsent` is a JDK mechanism; **do not infer that every Spring `CacheManager`/provider shares the exact same locking semantics**.

This demo uses a single process, a single key, and sequential single-threaded calls. It does not simulate TTL, eviction policies, persistence, clustered caching, or Spring proxies.

## 8. Choosing Cache Types by Environment

| Environment/Need | Suggested Choice | Notes |
|---|---|---|
| Unit tests not verifying caching | `NoOpCacheManager` | Every invocation runs the method; do not assert cache hits |
| Integration tests verifying annotations | `ConcurrentMapCacheManager` or `SimpleCacheManager` | Clear caches between tests; invoke through Spring beans |
| Demos, learning, local development | `ConcurrentMapCacheManager` | Easy to configure; cache lost when JVM stops |
| Small internal apps, single JVM, rebuildable data, no TTL needed | Can use ConcurrentMap cache | Monitor memory; confirm operational requirements |
| Production local cache needing TTL, max size, and eviction | Consider Caffeine | Configure expiry/size/metrics |
| Multiple application instances needing shared cache | Redis or appropriate distributed provider | Design serialization, key prefixes, network, and invalidation |
| Need persistence or specialized policies | Provider with corresponding features | Check failure modes, durability, and consistency |

There is no universal request-count threshold to decide whether an in-memory cache is sufficient. Evaluate **key count, value size, data mutation rate, instance count, acceptable staleness, RAM, and observability**.

Do not choose a simple cache if data must survive restarts, multiple instances must share entries, or you need TTL/TTI, maximum size, automatic eviction policies, metrics, or operational SLAs. Once requirements exceed what a simple map cache can offer, switch to an appropriate provider.

## 9. Common Mistakes

- **Confusing `SimpleCacheManager` with Boot's Simple provider:** a class managing pre-built cache objects differs from the auto-configured concurrent-map provider.
- **Using `NoOpCacheManager` and expecting cache hits:** no-op stores no entries; every call enters the method.
- **Using a simple cache in a cluster:** each JVM holds its own map; other nodes do not automatically see entries or evictions.
- **Forgetting to clear caches between tests:** tests become order-dependent, polluted by prior test data or reused Spring contexts.
- **Testing by instantiating services with `new`:** bypasses the proxy, preventing cache annotations from executing.
- **Misspelling cache names in static mode:** unregistered names can fail when operations need that region.
- **Assuming `ConcurrentMapCacheManager` has a default TTL:** it does not automatically set lifetimes or size policies.
- **Returning mutable objects to multiple callers:** the cache keeps references by default; callers can accidentally mutate cached data.
- **Caching everything without measurement:** unbounded key/value growth causes heap and GC pressure.
- **Using the cache to replace the data source:** in-memory caches can be lost on restart or eviction; business data needs a separate source of truth.
- **Confusing a thread-safe map with transaction-safe business logic:** multi-step business operations still need transactions, constraints, or dedicated synchronization.

## 10. Pre-Selection Checklist

1. Does the test need to **disable caching** or **verify real hit/miss behavior**?
2. How many cache names exist; do you need dynamic creation or a fixed list?
3. Can cached data afford to be lost on restart?
4. Is there only a single JVM, or must multiple instances share data?
5. Are TTL, maximum size, eviction policies, or metrics needed?
6. Are values mutable; is store-by-reference acceptable?
7. Do tests clear caches and call services through Spring proxies?
8. Is Boot auto-configuring the manager, or has the application declared its own bean?
9. Has the cache provider been tested for failures, stale data, and concurrency?
10. When the cache is unavailable or empty, can business logic still read from the authoritative source?

**Quick selection rule:** use `NoOpCacheManager` when disabling caching; use `ConcurrentMapCacheManager` when you want in-memory caches created by name; use `SimpleCacheManager` when you want to provide an explicit list of `Cache` objects. When TTL/size/distributed sharing is required, choose a provider built for those requirements.

## 11. Self-Check Questions

**Question 1.** How do `ConcurrentMapCacheManager()` (with no cache names) and `ConcurrentMapCacheManager("books")` differ in cache creation mode?

**Question 2.** Does `SimpleCacheManager` automatically create a `ConcurrentMapCache` when given an arbitrary name?

**Question 3.** Why is `NoOpCacheManager` suitable for some tests yet unsuitable for testing `@Cacheable` hits?

**Question 4.** Do two pods both using local `ConcurrentMapCacheManager` share entries?

**Question 5.** In `ConcurrentMapCacheManager`, why can a mutable cache value be altered by callers?

**Question 6.** When should you switch from a concurrent-map cache to Caffeine or Redis?

**Answers:**

1. Passing no names is **dynamic mode**, creating caches lazily on demand; passing names is **static mode**, managing only declared names.
2. **No.** `SimpleCacheManager` accepts a collection of pre-created cache objects via `setCaches`.
3. No-op retains no entries so methods run every time; hit tests require a manager that actually stores entries.
4. **No.** Each JVM has its own map unless a shared backend is configured.
5. By default `storeByValue=false` so the cache holds references; mutating an object can mutate the object inside the cache.
6. Caffeine when you need a local cache with advanced TTL/size/eviction; Redis or a distributed provider when multiple instances must share data.

## 12. References

- Spring Framework Reference — Configuring the Cache Storage, JDK ConcurrentMap-based Cache: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework Javadoc — `SimpleCacheManager`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/support/SimpleCacheManager.html
- Spring Framework Javadoc — `ConcurrentMapCacheManager` (dynamic/static mode, null and store-by-value): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html
- Spring Framework Javadoc — `NoOpCacheManager`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/support/NoOpCacheManager.html
- Spring Boot Reference — Caching auto-configuration, Simple provider, and Testing: https://docs.spring.io/spring-boot/reference/io/caching.html

**Key Takeaway:** `ConcurrentMapCacheManager` is an easy starting point for in-memory caching; `SimpleCacheManager` fits when registering pre-built cache objects; `NoOpCacheManager` is for disabling cache storage in tests. Use simple map caches when data is rebuildable, scope is appropriate, and advanced policies are unnecessary. When TTL, capacity limits, persistence, or multi-instance sharing are required, switch to an appropriate provider and test its behavior.