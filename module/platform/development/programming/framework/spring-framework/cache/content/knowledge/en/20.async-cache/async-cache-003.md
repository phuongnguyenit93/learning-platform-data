# Mono: Storing the Emitted Value Instead of Retaining the Publisher as Data

## 1. Objective

With Spring Framework 6.1 and later, `@Cacheable` can adapt to methods returning Reactor `Mono<T>`: the cache stores **the value `T` emitted by the publisher** rather than storing the `Mono` object itself as a business object. The caller still sees `Mono<T>`, but on a cache hit, Spring can create a stream replaying the cached `T` value without re-executing the business logic.

This point is especially important for cold publishers. If a `Mono` object encapsulates a database query and is merely stored in a Map, each subscription can still execute the query. When Spring Cache stores the emitted value `T`, subsequent calls with the same key after a cache hit do not need to re-subscribe to that source.

Objectives of this lesson:

- Distinguish the **publisher** from the **emitted value**.
- Understand the Spring proxy, cache lookup, subscription, cache miss, and cache hit.
- Configure a cache with asynchronous support, such as `CaffeineCacheManager#setAsyncCacheMode(true)`.
- Run Java 17 with `Mono<String>` and inspect the native business value stored in Spring `Cache`.
- Distinguish `Mono.empty()`, `Mono.error`, cancellation, retry, concurrent misses, TTL, and key scope.
- Know the limitations of `sync=true`, reactive transactions, and blocking sources.

This lesson belongs to the **Asynchronous** group of the Spring Framework Cache module. Knowledge of `Flux` and `CompletableFuture` is presented for comparison, without replacing the focus on Mono.

## 2. Why Is Caching a Mono Object Not Equivalent to Caching the Result?

Code snippet:

~~~java
Mono<String> publisher = Mono.fromSupplier(() -> {
    System.out.println("DB read");
    return "Product-A";
});
~~~

This snippet requires importing `reactor.core.publisher.Mono`. `fromSupplier` creates a **cold Mono**: the supplier runs when the publisher is subscribed to, not necessarily when Java constructs the object.

~~~java
publisher.block(); // prints "DB read"
publisher.block(); // prints "DB read" again
~~~

If you write a manual cache:

~~~java
Map<String, Mono<String>> wrongCache = new ConcurrentHashMap<>();
wrongCache.put("A",
    Mono.fromSupplier(() -> database.findTitle("A")));
~~~

This snippet requires imports/database. The Map having key `A` does not mean the query result has been cached. The Map only holds a recipe that is re-executed whenever the cold Mono is subscribed to.

Spring Cache 6.1+ aims for:

~~~text
"SKU-1"  -->  @Cacheable method: Mono<Product>
     |
     +-- Miss --> subscribe/load --> onNext(Product) --> store Product
     |
     +-- Hit  --> read Product from Cache --> Mono emits Product
~~~

**The cache value is `Product`, not `Mono<Product>`.** A cache hit does not need to run the source pipeline containing an HTTP request or repository query. However, TTL, authorization, keys, and invalidation must be designed specifically for the stored `Product` value.

## 3. Two Type Layers in Spring Cache

| Location | Type | Meaning |
| --- | --- | --- |
| Java method contract | `Mono<Product>` | Caller expects a computation/reactive stream |
| Cache entry after successful source emission | `Product` | Business value retained under the cache key |
| Cache hit returned to caller | `Mono<Product>` | Spring adapts `Product` back into the reactive return type |
| Native async cache implementation | May use an internal future/stage | Provider mechanism managing lookup/load timing; not the business type |

Do not confuse an **internal cache future** with business data: an async provider may store/coordinate `CompletableFuture` instances, but at the Spring `Cache` level, the expected business value of `Mono<Product>` is `Product`.

Business code example:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Mono<Product> findProduct(String sku) {
    return reactiveRepository.findBySku(sku);
}
~~~

This is not a standalone snippet: it requires `Product`, a repository, a Spring-managed bean, and `@EnableCaching`. The annotation is still from **Spring** (`org.springframework.cache.annotation.Cacheable`), not from Reactor.

## 4. Processing Flow on Miss and Hit

Spring caching operates via proxy/AOP in the default configuration:

1. Caller invokes `findProduct("SKU-1")` through the **Spring proxy**; the interceptor analyzes `@Cacheable`.
2. Spring resolves the `products` cache and the key from SpEL `#p0`.
3. The cache infrastructure queries the cache manager. With an implementation supporting async retrieval, `Cache.retrieve(...)`/`CompletableFuture` can be used to coordinate lookup/loading.
4. On a hit, Spring gives the caller a `Mono` emitting the existing business value `T`.
5. On a miss, the source method returns a `Mono`. When downstream subscribes, the source can perform the work and emit `T`.
6. When `T` completes successfully and satisfies policies, Spring places `T` into the cache. Subsequent calls with the same key will not execute the source while the entry remains valid.

~~~mermaid
sequenceDiagram
    participant Caller
    participant Proxy as Spring CacheInterceptor
    participant Cache as Async Cache
    participant Source as Mono source
    Caller->>Proxy: findProduct(key)
    Proxy->>Cache: lookup(key)
    alt hit
        Cache-->>Proxy: T
        Proxy-->>Caller: Mono emits T
    else miss
        Proxy->>Source: obtain Mono<T>
        Caller->>Proxy: subscribe
        Proxy->>Source: subscribe / await
        Source-->>Proxy: onNext(T), onComplete
        Proxy->>Cache: store T
        Proxy-->>Caller: onNext(T), onComplete
    end
~~~

The diagram conveys intent, not a single internal ordering mandated for every provider. Cache lookup can occur before subscription; source execution also depends on whether the `Mono` is lazy. With remote caches, futures and schedulers introduce additional observation points.

## 5. Versions Since Spring Framework 6.1 and Compatibility Switch

| System | What to Understand |
| --- | --- |
| Spring Framework before 6.1 | Reactive `Publisher` could be treated as an ordinary return object and cached as the object itself |
| Spring Framework 6.1+ default | Understands the `Mono` return type and caches the emitted value, rather than simply caching the `Publisher` |
| System with `spring.cache.reactivestreams.ignore=true` | Can bypass reactive adaptation to preserve legacy behavior in versions supporting the switch |

This behavior is a significant change during version upgrades. Do not apply advice meant for Spring 6.0 to a Spring 6.2 project and expect the cache to store the publisher.

To verify the current state, check:

- The actual `spring-context` version at runtime.
- Caching configuration, compatibility system properties, and `CacheManager` selection.
- Whether the source method actually passes through a Spring proxy.
- The value read from Spring `Cache` after the publisher completes: `T` or publisher.
- How many times the source runs when called twice with the same key.

Do not assume having the Reactor dependency on the classpath is enough to automatically enable caching; `@EnableCaching` or equivalent configuration is still required.

## 6. Caffeine Async Mode and `Cache.retrieve`

Spring Cache adds asynchronous retrieval capabilities through operations such as:

~~~java
CompletableFuture<?> asyncHitOrMiss = cache.retrieve(key);
~~~

This snippet requires `Cache cache`, `key`, and importing `CompletableFuture`. Not every provider implements async retrieval the same way; the future may complete later, and may wrap a `Cache.ValueWrapper` depending on the overload contract.

For Caffeine, Spring provides the manager:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableCaching
class CacheConfig {
    @Bean
    CacheManager cacheManager() {
        CaffeineCacheManager manager = new CaffeineCacheManager();
        manager.setAsyncCacheMode(true);
        manager.setCacheNames(List.of("products"));
        return manager;
    }
}
~~~

This snippet requires Spring annotations/imports, `java.util.List`, `CaffeineCacheManager`, and the Caffeine dependency. `setAsyncCacheMode(true)` uses async Caffeine caches, which is a suitable choice for reactive return types starting in Spring 6.1.

Note that native Caffeine is a local in-memory cache; this configuration does not automatically provide distributed coherence, does not turn blocking JDBC into non-blocking, and does not define a TTL by itself. In Spring Boot, check which `CacheManager` bean auto-configuration actually creates instead of assuming async mode is always on.

## 7. Runnable Java 17 Example: `Mono<String>` Stored as `String`

The demo uses Spring Framework 6.2.14, Reactor Core 3.7.12, and Caffeine 3.1.8. No database or server is needed. A counter increments each time the source is subscribed to in order to distinguish misses from hits.

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-mono-emitted-cache</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.14</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context-support</artifactId>
      <version>6.2.14</version>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core</artifactId>
      <version>3.7.12</version>
    </dependency>
    <dependency>
      <groupId>com.github.ben-manes.caffeine</groupId>
      <artifactId>caffeine</artifactId>
      <version>3.1.8</version>
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

`spring-context-support` contains the Caffeine adapter, `spring-context` contains the annotation/bean infrastructure, and Reactor Core contains `Mono`. The demo versions are deliberate choices, not an upgrade rule for every production application.

### 7.2. src/main/java/demo/MonoCacheDemo.java

~~~java
package demo;

import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Mono;

public final class MonoCacheDemo {
    private MonoCacheDemo() {}

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        CacheManager cacheManager() {
            CaffeineCacheManager manager = new CaffeineCacheManager();
            manager.setAsyncCacheMode(true);
            manager.setCacheNames(List.of("products"));
            return manager;
        }

        @Bean
        CatalogService catalogService() {
            return new CatalogService();
        }
    }

    public static class CatalogService {
        private final AtomicInteger loads = new AtomicInteger();

        @Cacheable(cacheNames = "products", key = "#p0")
        public Mono<String> find(String sku) {
            return Mono.fromSupplier(() -> {
                int n = loads.incrementAndGet();
                System.out.println("source #" + n);
                return "product:" + sku + ":v" + n;
            });
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public void evict(String sku) {
            // No database in this demo.
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            CatalogService service = context.getBean(CatalogService.class);

            System.out.println("first=" + service.find("SKU-1").block());
            System.out.println("second=" + service.find("SKU-1").block());

            CacheManager manager = context.getBean(CacheManager.class);
            Cache cache = Objects.requireNonNull(
                    manager.getCache("products"));
            Cache.ValueWrapper wrapper = Objects.requireNonNull(
                    cache.get("SKU-1"));
            Object value = Objects.requireNonNull(wrapper.get());

            System.out.println("stored type=" + value.getClass().getName());
            System.out.println("stored publisher=" + (value instanceof Mono));

            service.evict("SKU-1");
            System.out.println("after evict="
                    + service.find("SKU-1").block());
        }
    }
}
~~~

Important conditions: the service must be Spring-managed, methods must be public and non-final, `@EnableCaching` must be present, and the caller must invoke the proxy. `Mono.fromSupplier` creates a lazy source. The key is the `String` `"SKU-1"` in the `products` cache; the Caffeine manager has async mode enabled.

### 7.3. Run Command

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.MonoCacheDemo
~~~

Expected stdout from the program (excluding Maven/Spring logs):

~~~text
source #1
first=product:SKU-1:v1
second=product:SKU-1:v1
stored type=java.lang.String
stored publisher=false
source #2
after evict=product:SKU-1:v2
~~~

The first call misses, so the supplier runs and prints `source #1`. The second call hits, printing no additional source call. `Cache.ValueWrapper` holds a `String` value rather than a `Mono`. After evicting the key, the next read misses, the source runs again, and v2 is produced.

The example has been reviewed against Spring/Reactor APIs, though **not compiled or executed live** during authoring. When studying, run it with the stated dependencies/versions and verify the policy of the adapter in use. `block()` here serves the console demo; do not use `block()` on the WebFlux event-loop in production.

## 8. Cold Publisher, Hot Publisher, and `Mono.cache()`

`Mono.cache()` is a Reactor operator that memoizes signals of **a single Publisher instance**, not the same layer as Spring's `@Cacheable`.

~~~java
Mono<String> shared = remoteLookup("SKU-1").cache();
~~~

This snippet requires `remoteLookup`. Multiple subscribers to `shared` can reuse one memoized result. However, if every method call creates a new `remoteLookup(...).cache()`, each instance has its own state. Meanwhile, `@Cacheable` has a cache name/key/manager and shares results across method calls per cache policy.

`Mono.just(value)` holds an already-computed value; if the argument to `just` is a blocking DB call, that call runs immediately when constructing the `Mono`. `Mono.fromSupplier` and `Mono.defer` defer evaluation until subscription. A publisher connected to a future/hot source has different semantics. Caching the emitted value avoids depending on the source publisher type during hits, but does not remove the need to clarify timing on misses.

## 9. `Mono.empty()` and Cached Null

A `Mono.empty()` completes **without emitting a `T` element**. Reactor does not allow `Mono.just(null)` or `onNext(null)`.

~~~java
Mono<String> notFound = Mono.empty();
~~~

For Spring reactive caching, an empty completion is not identical to a successful `onNext(T)`. An adapter may represent empty via null/absent state, and providers may have different policies on caching null. **Do not assume unconditionally that empty is always negative-cached or always a miss.**

How to test:

1. Write a `@Cacheable` method returning `Mono.empty()`, with a counter incremented when the source is subscribed to.
2. Call twice with the same key and await completion.
3. Measure the counter and read `Cache.get(key)`, distinguishing a null wrapper (miss) from a non-null wrapper containing a null value (hit-null).
4. Test `unless` and the `allowNullValues` policy if supported by the provider.
5. Repeat whenever changing `CacheManager` or Spring version.

If you need to distinguish NotFound/Forbidden/Timeout, use an explicit domain result rather than treating all of them as empty completions.

## 10. `Mono.error`, Retry, and Cancellation

`Mono.error(e)` is an error signal and **does not emit a successful business value `T`**. Do not design caching of an error response as if it were a valid `Product` merely because the method return type is `Mono`.

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Mono<Product> get(String sku) {
    return webClient.get()
        .uri("/products/{sku}", sku)
        .retrieve()
        .bodyToMono(Product.class);
}
~~~

This snippet requires Spring `WebClient` and a `Product` class. On timeouts/HTTP errors, handle according to domain policy.

- `onErrorResume(e -> Mono.empty())` turns errors into empty completions; if negative caching is on, this can accidentally record an outage as NotFound.
- `retry` inside the source differs from retrying subscription outside the method. Verify how many remote calls occur on a miss.
- One subscriber canceling its subscription does not guarantee canceling every future/loader shared with other subscribers.
- With async caches, failed futures may have their own lifecycle/cleanup. Test errors and retries on the actual provider.
- Do not run only a happy-path test and extrapolate error/cancellation behavior.

## 11. `condition`, `unless`, and `sync=true`

Annotation example:

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 != null",
    unless = "#result == null"
)
public Mono<Product> find(String sku) {
    return repository.findBySku(sku);
}
~~~

This is an illustrative snippet requiring a repository and `Product`. `condition` evaluates before the result is produced based on inputs; `unless` is a veto once a result exists. With reactive support in newer Spring versions, understand `#result` in terms of the **emitted value** rather than assuming it is always the `Mono` object. With `Mono.empty()`, execution and null adaptation must be tested.

`@Cacheable(sync=true)` helps coordinate loads for the same key when supported by the backend; **do not combine it with `unless`** per Spring's contract. Do not try to combine both hoping the cache will handle empty results automatically.

## 12. Keys Must Describe the Value, Not the Subscription

If a source depends on `sku`, `currency`, and `tenant`:

~~~java
@Cacheable(cacheNames = "prices", key = "#p0")
public Mono<Price> getPrice(
        String sku, String currency, String tenant) {
    return pricingClient.getPrice(sku, currency, tenant);
}
~~~

This snippet requires `Price`/client. A key containing only `sku` is **wrong** if `currency`/`tenant` affect the price. On a cache hit, the old emitted `Price` is reused **without re-running the source** where tenant selection logic might reside.

Design keys to include all dimensions affecting output (tenant, user scope, permissions, currency, locale, version). Do not use `Mono` identity or per-subscription state as the key. If critical information only lives in the Reactor Context, pass it via method arguments or a testable custom key strategy; SpEL generating keys at the invocation boundary does not automatically read everything that only appears at subscription time.

Security warning: authorization must be enforced at the proper boundary; a cache hit must not accidentally bypass permission checks owned by the business source.

## 13. Concurrent Misses and Single-Flight

Two callers can both observe a cache miss and both execute the source before a result is stored. `sync=true` can help the provider perform a single load for the same key when it supports this mechanism.

~~~java
Mono<String> a = service.find("SKU-1");
Mono<String> b = service.find("SKU-1");
Mono.zip(a, b).block();
~~~

This snippet only illustrates the idea; it is unlikely to produce a true concurrent miss if the source is synchronous on one thread. To measure it, use an asynchronous source with a controllable delay/latch and a counter.

Remember:

- Sync loading requires `CacheManager` support; a local guarantee is not necessarily distributed single-flight.
- `sync=true` and `unless` cannot be combined as a valid configuration.
- Error/timeout/cancellation of a shared load can affect multiple consumers; test separately.
- A duplicate load is not necessarily a bug if the application does not require strict single-flight.

## 14. TTL, Invalidation, and Stale Emitted Values

Once Spring has cached `T`, a cache hit emits the stored `T`; it **does not automatically re-call** the repository to check for a newer version. Freshness depends on:

- Provider TTL/size/eviction, not `Mono.cache(Duration)`.
- `@CacheEvict` or direct `Cache.evict` when source data changes.
- Versioned keys, invalidation events, and guarding against races with in-flight loaders.
- Transaction boundaries: do not assume cache eviction after a Java method returns means after a database commit.
- Remote cache replication and serializers when the application runs across multiple nodes.

A reactive source completing after an entry was invalidated can put stale data back into the cache. For sensitive data, use version/generation keys or an appropriate coordination mechanism.

For commands returning `Mono<Void>`, completion emits no business element; do not attach "cache emitted value" logic as if a `Void` were emitted. When using reactive transactions, verify transaction commit timing and cache invalidation against the Reactor Context; do not assume a thread-local transaction-aware decorator applies verbatim to every reactive flow.

## 15. Avoiding Blocking I/O in the Source

Mistake:

~~~java
public Mono<Product> wrong(String sku) {
    return Mono.just(jdbcRepository.findBySku(sku));
}
~~~

`jdbcRepository.findBySku` already executed before the `Mono` finished constructing; when called on a WebFlux event-loop it can block the thread. Cache hits may reduce how often the source is called, but misses remain dangerous.

If you must call a blocking API:

~~~java
public Mono<Product> withBlockingSource(String sku) {
    return Mono.fromCallable(() -> jdbcRepository.findBySku(sku))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

This snippet requires imports and a repository. `boundedElastic` offloads blocking work to a suitable scheduler; it **does not turn I/O into non-blocking**. If a true reactive repository/driver is available, use it instead.

## 16. Testing Layer by Layer

**Checking emitted values and source execution counts:**

~~~java
String first = service.find("SKU-1").block();
String second = service.find("SKU-1").block();
// Assert first.equals(second) AND source counter incremented once.
~~~

Two equal values do not prove a hit by themselves, since the database could return the same data twice. The counter must measure **inside the source**, not just a downstream `doOnNext`, because subscribers receive cache hits too.

**Checking the value type in the cache:**

~~~java
Cache.ValueWrapper wrapper = cache.get("SKU-1");
Object stored = wrapper == null ? null : wrapper.get();
System.out.println(stored == null ? "MISS" : stored.getClass().getName());
~~~

The Spring `Cache` API helps inspect the real stored value. The demo uses `String`. Remember to distinguish a null wrapper from a wrapper containing null.

**Checking eviction:**

~~~java
service.evict("SKU-1");
String fresh = service.find("SKU-1").block();
// Source counter increments and the value version changes.
~~~

If the project already includes `reactor-test`, you can use:

~~~java
StepVerifier.create(service.find("SKU-1"))
    .expectNext("product:SKU-1:v1")
    .verifyComplete();
~~~

This snippet requires adding `io.projectreactor:reactor-test` and importing `reactor.test.StepVerifier`; it is **not in the Maven demo**.

### Case Matrix

| Case | What to Verify |
| --- | --- |
| `Mono` emits `T` | Cache stores `T`, source runs only on miss |
| Cache hit | Caller still receives `Mono<T>`, source does not run |
| `Mono.empty` | Negative-cache policy is explicit |
| `Mono.error`/timeout | Errors do not turn into cached successes |
| Cancel | Future/source state does not produce invalid cache entries |
| Concurrent miss | Duplicate loads or single-flight matches requirements |
| TTL expiration | Reloads at the right time |
| Evict | After eviction, source produces a new version |
| Multi-tenant | Key scope and permissions do not leak |
| Upgrading Spring/provider | Caching cold `Publisher` objects does not regress |

## 17. Common Pitfalls

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Storing a cold `Mono` in a Map and assuming data is cached | Subscribing still hits the DB | Cache emitted values via Spring 6.1+ |
| Assuming Spring 6.0 handles `Mono` identically to 6.2 | Version behavior mismatch | Verify versions and test |
| Accidentally enabling `spring.cache.reactivestreams.ignore=true` | Reverts to caching the `Publisher` | Disable the compatibility switch when reactive adaptation is desired |
| Forgetting `@EnableCaching` or instantiating service with `new` | No proxy | Obtain bean from Spring context |
| Calling `this.find(...)` inside the same class | Self-invocation bypasses caching | Call through Spring bean/proxy |
| `CacheManager` lacks proper async support | Async retrieval violates expectations | Use a supporting provider, try Caffeine async mode |
| Counting downstream `doOnNext` as DB hit count | Counts cache hits too | Measure at supplier/repository |
| `Mono.just(blockingCall())` | Blocks thread at assembly time | Use reactive API or defer + `boundedElastic` |
| Confusing `Mono.cache()` with `@Cacheable` | Different scope/key/TTL/error policies | Choose the right cache layer |
| Key has only SKU while data is per-tenant | Wrong results or data leak | Include full tenant/permission in key |
| Assuming `Mono.empty` is always cached | Ignores null/provider/version rules | Test negative caching separately |
| Combining `sync=true` and `unless` | Unsupported | Redesign policy |
| Caching an infinite `Flux` like a `Mono` | Unbounded collection, RAM risk | Do not cache unbounded streams |
| Thinking reactive `Mono` means non-blocking I/O | Misses still block the DB | Fix the underlying source |

## 18. Checklist and Official Documentation

Pre-production checklist:

- [ ] Verified Spring 6.1+ and compatibility switches?
- [ ] Annotated methods invoked through Spring proxy, not self-invocation?
- [ ] `CacheManager` supports async retrieval properly and provider is configured?
- [ ] Tests prove the cache stores `T` rather than `Mono`, with a source counter?
- [ ] Empty/error/cancellation and negative-caching policies handled properly?
- [ ] Cache keys cover tenant, currency, locale, and permission scope?
- [ ] `sync=true`, `condition`, and `unless` combined validly?
- [ ] TTL, eviction, concurrent loaders, and transaction consistency tested?
- [ ] In WebFlux, code never calls `block()` on the event loop?
- [ ] Re-ran the integration tests above when changing providers/versions?

References:

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): support for reactive return types and caching annotations.
- [Spring Framework — Cache Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html): `get`, `ValueWrapper`, and `retrieve`.
- [Spring Framework — CaffeineCacheManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html): async cache mode.
- [Spring Framework — CacheAspectSupport Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/CacheAspectSupport.html): cache interception and compatibility property.
- [Project Reactor — Mono Javadoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): publisher semantics, empty/error, `fromSupplier`, `defer`, and `cache`.
- [Project Reactor — Reference](https://projectreactor.io/docs/core/release/reference/): scheduling, backpressure, testing.

**Conclusion:** in a properly configured Spring Cache 6.1+, `@Cacheable` on `Mono<T>` caches **the emitted `T` value**. A cache hit returns a `Mono` emitting `T` without re-running the source. Verify with a counter, `Cache.ValueWrapper`, and eviction; do not extrapolate empty/error, multi-node, or transaction behavior without testing.