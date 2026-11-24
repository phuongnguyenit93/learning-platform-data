# @Cacheable: When Results Are Stored After a Successful Invocation

## Lesson Objectives

This lesson explains precisely **when Spring writes a result into the cache** for a method annotated with @Cacheable, what happens when the method succeeds, throws an exception, returns null, or completes asynchronously, and how to verify that behavior using Java 17+. After this lesson, you will be able to distinguish **when the method returns**, **when the cache writes the value**, **when a database transaction commits**, and **when an asynchronous task completes**.

> Core rule: For a synchronous invocation going through the Spring Cache proxy, only on a **cache miss** when the method **returns normally** does Spring consider writing the result into the cache. Storing also depends on condition, unless, and the actual capabilities of the cache provider. When a method throws an exception outward, Spring does not treat that exception as a result to cache with @Cacheable.

## 1. At What Points Does @Cacheable Process an Invocation?

Spring Cache is a method-result caching mechanism. Configuring @EnableCaching activates processing of cache annotations on Spring beans; by default Spring uses a proxy/AOP mechanism to wrap method calls.

Consider an example in a Spring-managed service:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product findProduct(long productId) {
    return repository.findById(productId);
}
~~~

This is an **illustrative code snippet**, assuming Product and repository already exist; it is not a standalone program.

### 1.1. First call: cache miss

1. The client calls findProduct(42) **through the Spring proxy**.
2. Spring resolves the "products" cache region and key 42; if condition is present, it evaluates the condition first.
3. Spring looks up key 42. No entry exists → cache miss.
4. Spring invokes the **real method**. The database is queried; the method returns a Product object normally.
5. Spring evaluates unless if present. If not vetoed, Spring asks the cache provider to store the result under key 42.
6. The proxied call completes and the client receives the Product.

For the normal synchronous path, putting the result into the cache happens **after the target method returns successfully** and **during the completion of the proxied call**. Do not think of this as "waiting until the HTTP response is sent," "waiting until the database transaction commits," or "waiting for another request."

~~~text
Client -> Spring proxy -> Cache.get(42)
                              |
                           cache miss
                              |
                         findProduct(42)
                              |
                    returns Product normally
                              |
                   evaluate unless (if any)
                              |
                           Cache.put(42, Product)
                              |
                        return result to client
~~~

The diagram above depicts the logical flow of a **synchronous** method, assuming valid cache operations and no provider errors.

### 1.2. Subsequent call: cache hit

Spring reads the stored value under key 42 and returns it **without calling the method body again**. Thus a cache hit is not a re-execution of the query logic followed by a cache write. If multiple cache regions are declared in the same @Cacheable, Spring can populate regions missing the entry after finding a hit in another region; that is multi-cache coordination behavior, not re-executing the source method.

~~~text
Client -> Spring proxy -> Cache.get(42)
                              |
                           cache hit
                              |
                    return Product from cache
                     (does not run repository)
~~~

### 1.3. Method throws an exception

If the target method throws an exception that propagates outward instead of returning normally, the @Cacheable flow **does not create a new cache entry from that failed invocation**. A later call with the same key can continue to be a cache miss and retry the source.

~~~text
Cache miss -> findProduct(42) -> throw IllegalStateException
                                          |
                              exception propagates to client
                              NO Cache.put of a result
~~~

Distinguish the case where the method **catches the exception internally and returns a fallback value**: in that situation, from Spring's perspective, the method returned normally. The fallback value **may be cached** if there is no unless clause or corresponding policy preventing it.

## 2. What Does a "Successful Invocation" Actually Mean?

In a synchronous @Cacheable context, "successful" primarily means the target method **terminates normally and produces a processable result**, rather than letting an exception escape. This **does not automatically mean** any of the following statements:

- **Does not mean business success:** an object like Result(success=false, error="NOT_FOUND") is still a normal return value. Without a filtering condition, it can be cached.
- **Does not mean HTTP 2xx:** the cache interceptor operates at the Spring bean method invocation boundary; the HTTP status may be decided at a later layer.
- **Does not mean database changes have committed:** transaction advice and cache advice are two separate mechanisms; AOP ordering, transaction boundaries, and cache configuration determine the actual relationship.
- **Does not mean the cache definitely succeeded in writing:** unless may reject the result; the provider may encounter an error; or the value may be evicted immediately due to TTL, capacity limits, or a concurrent invocation.

Therefore, the accurate statement is: **Spring considers storing the result after the method returns normally; actual storage occurs only when cache conditions allow it and the put operation succeeds.**

## 3. condition and unless: Checks Before and After Method Execution

These two attributes often explain why a method **runs successfully yet leaves no entry in the cache**.

| Attribute | Evaluation timing | Can read #result? | Effect |
| --- | --- | --- | --- |
| condition | Before method execution / before caching operations | No | False → skips caching behavior, still executes the method |
| unless | After the method has been called and produced a result | Yes | True → vetoes storing the newly computed result |

Example:

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 > 0",
    unless = "#result == null"
)
public Product findProduct(long id) {
    return repository.findById(id);
}
~~~

This is an **illustrative code snippet**; repository and Product must be defined in a real application.

- When id <= 0, condition is false so Spring applies no caching to that call, regardless of what the method returns.
- When id > 0, cache miss, and the method returns a Product: unless is false, so the result can be written.
- When id > 0, cache miss, and the method returns null: unless is true, so Spring **does not store null**.
- When id > 0 and the method throws an exception: there is no normal return value to put into the cache.

**Note on null:** Without unless, whether a null value can be cached depends on the configuration and capabilities of the Cache provider. For example, ConcurrentMapCache supports null values by default via an internal placeholder value. Thus, "not found" does **not automatically** mean a cache miss on the next call.

**Note on Optional:** Spring supports Optional in cache results: a present Optional is handled via its inner value; Optional.empty() corresponds to null under Spring Cache's mechanism, if the provider permits storing it. Inside an unless expression, #result represents the unwrapped business object; for Optional.empty(), #result is null. To prevent unintended negative caching, you can use unless = "#result == null".

## 4. Runnable Java 17 Example: Observing Immediately Before and After Storage

The following program uses **Spring Framework 6.2.10**, Java 17+, and Maven. There are three scenarios: the method returns normally, throws an exception, and returns null vetoed by unless. ConcurrentMapCacheManager is used for easy observation; this is an illustrative in-memory cache and does not provide production TTL/max-size policies by default.

### 4.1. File structure

~~~text
cache-write-timing/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── CacheWriteTimingDemo.java
~~~

### 4.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cache-write-timing</artifactId>
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

### 4.3. CacheWriteTimingDemo.java

~~~java
package demo;

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

public class CacheWriteTimingDemo {

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("products");
        }

        @Bean
        public ProductService productService() {
            return new ProductService();
        }
    }

    public static class ProductService {
        private final AtomicInteger sourceCalls = new AtomicInteger();

        @Cacheable(cacheNames = "products",
                   key = "#p0",
                   unless = "#result == null")
        public String load(String sku) {
            int call = sourceCalls.incrementAndGet();

            if ("ERR".equals(sku)) {
                throw new IllegalStateException("simulated failure");
            }
            if ("NONE".equals(sku)) {
                return null;
            }
            return sku + "|load=" + call;
        }

        public int sourceCalls() {
            return sourceCalls.get();
        }
    }

    private static boolean isCached(Cache cache, String key) {
        return cache.get(key) != null;
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            ProductService service = context.getBean(ProductService.class);
            Cache cache = Objects.requireNonNull(
                context.getBean(CacheManager.class).getCache("products"));

            System.out.println("A before: " + isCached(cache, "A"));
            System.out.println("A first: " + service.load("A"));
            System.out.println("A after: " + isCached(cache, "A"));
            System.out.println("A second: " + service.load("A"));
            System.out.println("Calls after hit: " + service.sourceCalls());

            try {
                service.load("ERR");
            } catch (IllegalStateException exception) {
                System.out.println("Error: " + exception.getMessage());
            }
            System.out.println("ERR cached: " + isCached(cache, "ERR"));

            System.out.println("NONE first: " + service.load("NONE"));
            System.out.println("NONE cached: " + isCached(cache, "NONE"));
            System.out.println("NONE second: " + service.load("NONE"));
            System.out.println("Source calls: " + service.sourceCalls());
        }
    }
}
~~~

### 4.4. Running the program

In the directory containing pom.xml, using JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheWriteTimingDemo
~~~

Lines **printed by the program** (Maven logs, if any, are excluded here):

~~~text
A before: false
A first: A|load=1
A after: true
A second: A|load=1
Calls after hit: 1
Error: simulated failure
ERR cached: false
NONE first: null
NONE cached: false
NONE second: null
Source calls: 4
~~~

### 4.5. Explaining the output in order

1. **A before: false:** no entry exists yet for key "A".
2. **A first: A|load=1:** cache miss, the body of load("A") executes and returns normally.
3. **A after: true:** immediately after the proxied call finishes, checking the cache shows the entry has been written. This is observable on the same thread, without having to wait for another request.
4. **A second: A|load=1:** cache hit; the returned string keeps load number 1 because the source method does not re-run.
5. **Calls after hit: 1:** confirms the hit avoided a second execution.
6. **Error: simulated failure / ERR cached: false:** the source method throws an exception; @Cacheable does not store a new result for key "ERR".
7. **NONE first: null / NONE cached: false:** the method returns normally, but unless sees #result == null and prevents storage.
8. **NONE second: null / Source calls: 4:** key "NONE" misses again so the source runs once more. Total source executions: once for A + once for ERR + twice for NONE = 4.

In the example, @EnableCaching activates cache advice; service is retrieved from ApplicationContext so calls pass through the Spring proxy. The load method is public, the ProductService class is not final, and it is not invoked via this.load(...) from within the bean itself.

## 5. Exceptions, Business-Error Results, and Storage Policies

### 5.1. Exception escaping the method

~~~java
@Cacheable("profiles")
public Profile getProfile(long id) {
    return remoteClient.fetchProfile(id); // may throw
}
~~~

If fetchProfile throws an exception and the method does not catch it, the invocation produces no successful result for the cache. Subsequent calls typically continue querying the source. This is an **illustrative code snippet** depending on Profile/remoteClient and does not run standalone.

### 5.2. Exception caught and converted into a fallback value

~~~java
@Cacheable(cacheNames = "rates",
           unless = "#result == null")
public Rate getRate(String currency) {
    try {
        return exchangeProvider.fetch(currency);
    } catch (RuntimeException failure) {
        return null; // unless will reject caching null
    }
}
~~~

The method **returned normally** after catching the exception. If it returns a DTO representing an error and there is no veto condition, that DTO can be cached. Therefore, you must define clearly whether error results should be cached; if negative caching is desired, manage short TTLs, retries, and upstream service recovery deliberately.

### 5.3. Output mutated after cache put

The cache stores either a reference or a copy/serialization depending on the provider. Returning a mutable object and modifying it elsewhere can cause unpredictable behavior with in-memory caches; distributed providers may instead return a deserialized object. Prefer immutable DTOs or define clear data ownership. The Cache abstraction does not automatically guarantee an immutable snapshot of a value.

## 6. Asynchronous Storage Timing: CompletableFuture and Reactor

Since **Spring Framework 6.1**, @Cacheable understands CompletableFuture and supported Reactor reactive return types; the moment "a result is available" is **no longer simply when the Java method returns the wrapper**.

| Return type | When the value can be put into the cache |
| --- | --- |
| Product (synchronous) | After the method returns Product normally |
| CompletableFuture<Product> | When the future completes successfully with a value |
| Mono<Product> | When the publisher emits a supported storable value |
| Flux<Product> | When the sequence of elements completes; Spring collects them into a List and caches the list |

Example asynchronous method declaration (**illustrative code**, requires backend and Product):

~~~java
@Cacheable(cacheNames = "productsAsync", key = "#p0")
public CompletableFuture<Product> getProductAsync(long id) {
    return backend.fetchAsync(id);
}
~~~

A CompletableFuture returned while the task is still running **does not mean the Product result has been cached yet**. Spring processes the result when the future completes; a future completing exceptionally does not produce a successful Product result to store. Likewise, a Flux must complete in full before the resulting list is used as the cache value; this is unsuitable for infinite streams or reactive flows requiring fine-grained backpressure.

These mechanisms require a cache provider with suitable asynchronous retrieval/put capabilities. Spring's ConcurrentMapCacheManager supports an adapter for CompletableFuture; CaffeineCacheManager requires configuring the corresponding async cache mode to leverage native support. **Do not assume "already cached" the moment the return CompletableFuture statement executes.**

## 7. Caching After a Successful Call Is Not Necessarily After Transaction Commit

Suppose a method reads/writes data within @Transactional while also using a cache annotation:

~~~java
@Transactional
@Cacheable(cacheNames = "accountSummary", key = "#p0")
public AccountSummary calculateSummary(long accountId) {
    return repository.buildSummary(accountId);
}
~~~

This is **illustrative code**; AccountSummary and repository are not defined.

Two distinct milestones must be checked: (1) the target method returns an AccountSummary; (2) the transaction actually commits. Both Spring Cache advice and transaction advice can wrap the method via AOP, with an order determined by configuration. **@Cacheable does not automatically guarantee "cache put always happens after commit."** If the cache writes data before a transaction that later rolls back, there is a risk the cache no longer reflects the database.

When strict consistency is required, consider:
- Configuring a transaction-aware cache or deferring cache operations until after commit when appropriate for the provider and operation type.
- Placing evict/put operations in an appropriate after-commit step.
- Testing rollbacks, concurrent reads, multiple instances, and actual transaction boundaries.

Also do not confuse @Cacheable with @CacheEvict: for @CacheEvict, eviction runs by default **after the method finishes successfully**; beforeInvocation = true proactively evicts before running regardless of the method outcome. Choosing an update strategy is a separate business decision from query-result caching mechanics.

## 8. Comparing Execution Timing of Three Common Annotations

| Annotation | Does the source method always run? | Cache interaction timing |
| --- | --- | --- |
| @Cacheable | No; hits can skip it | Miss + normal return, then evaluates unless and puts the result into cache if eligible |
| @CachePut | Yes | After the method produces a result, writes the new result as configured |
| @CacheEvict | Yes in the normal flow | By default evicts after the method runs successfully; can use beforeInvocation=true to evict beforehand |

Essential difference: @Cacheable optimizes the read path by **skipping execution on a hit**; @CachePut fits operations that must **always execute and then update the cache**. Do not arbitrarily place both @Cacheable and @CachePut on the same method because their execution goals conflict.

## 9. Why Does "The Method Run Successfully Yet the Cache Remains Empty"?

Use the following checks in order:

1. **Did it go through the proxy?** @EnableCaching must be enabled, the bean must be Spring-managed, and the call must pass through the proxy. Self-invocation such as this.load(id) bypasses cache advice in default proxy mode.
2. **Was condition false?** If false, Spring skips caching behavior for that invocation even though the method runs normally.
3. **Was unless true?** A normal return such as null or an error DTO may be vetoed from storage.
4. **Is the key right?** Calling the same method with a different generated key (locale/tenant/parameter/equals-hashCode) can make it look as though the cache is empty.
5. **Did the cache provider accept the put?** Check CacheManager configuration, cache type, serialization, capacity, TTL, eviction, and error handler. By default, cache operation errors can propagate to the caller.
6. **Was the entry concurrently modified or removed?** @CacheEvict from another thread, short TTL, or put/evict races can make the entry disappear right away.
7. **Is async being used?** With CompletableFuture/Mono/Flux, the moment a complete result is available may be later than the Java return statement.
8. **Is it waiting on a transaction commit?** Check AOP advisor ordering and transaction-aware cache settings if the system requires post-commit storage.

To observe accurately, count method body executions, provider hits/misses/puts, and query entries via CacheManager in tests. Do not determine outcomes solely from application-layer "method completed" logs.

## 10. Recommended Tests

A cache behavior test is valuable when it verifies at least these scenarios:

- **Miss → success → hit:** first call runs the method body, then the entry exists; second call with the same key does not re-run the body.
- **Miss → throw:** no new result is written; a subsequent call with the same key can run again.
- **Miss → return null + unless true:** null is not cached; the next call continues to miss.
- **condition false:** the method executes normally, with no cache lookup/put applied.
- **Result carrying a business error:** verify unless prevents storage if policy forbids negative caching.
- **Async completion success/failure:** evaluate cache state only after the future/publisher actually yields a value or completes with an error.
- **Transaction rollback:** final cache state must remain consistent with the designed transaction policy.
- **Concurrent misses:** default @Cacheable does not guarantee a single computation; when needed, evaluate sync = true alongside provider support and constraints.

### Self-Check

**1.** A @Cacheable method has no entry yet, runs, and returns String "OK". When does Spring consider putting it into the cache?  
**Answer:** After the method body returns normally, then evaluating unless if present.

**2.** The method throws IllegalStateException outward. Does Spring store the exception as a cache value?  
**Answer:** No under normal @Cacheable behavior.

**3.** The method returns null with no unless clause. Is the next call guaranteed to miss?  
**Answer:** No; some providers allow caching null. Check the configuration.

**4.** A call returns an incomplete CompletableFuture. Is the Product guaranteed to be cached already?  
**Answer:** No; the result is processed when the future completes.

**5.** Does @Transactional + @Cacheable guarantee cache put always happens after database commit?  
**Answer:** No. AOP advice ordering, transaction boundaries, and cache configuration must be examined.

**6.** Another method in the same service calls this.findProduct(42). Is @Cacheable guaranteed to apply?  
**Answer:** No in default proxy mode; the call must pass through the proxy.

## References

- Spring Framework Reference — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework Reference — Understanding the Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache/strategies.html
- Spring Framework Reference — Configuring Cache Storage: https://docs.spring.io/spring-framework/reference/integration/cache/store-configuration.html
- Spring Framework Reference — Cache TTL/TTI/Eviction: https://docs.spring.io/spring-framework/reference/integration/cache/specific-config.html