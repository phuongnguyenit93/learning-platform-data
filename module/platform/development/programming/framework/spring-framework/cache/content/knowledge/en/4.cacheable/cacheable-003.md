# Execution Flow When a Cache Entry Exists or Is Absent for a Key in @Cacheable

## Learning Objectives

Understand the exact sequence of operations Spring Cache performs when a method annotated with `@Cacheable` is called: generating the cache key, checking whether an entry already exists, distinguishing a **cache hit** from a **cache miss**, when the real method runs, and writing the result back into the cache. This lesson also explains the case where the annotation omits `key`, the effects of `condition`/`unless`, invalidation, and considerations for concurrent invocations.

## 1. What Does "Key Present or Absent" Mean?

In the context of `@Cacheable`, a **key** is the identifier of an entry in a cache. Each entry maps **key → stored result**. For example:

~~~text
Cache named "products"
┌─────────────┬─────────────────────────────┐
│ Key         │ Cached value                │
├─────────────┼─────────────────────────────┤
│ "SKU-01"    │ "Ballpoint pen - 12000 VND" │
│ "SKU-02"    │ "Notebook - 25000 VND"      │
└─────────────┴─────────────────────────────┘
~~~

When `findProduct("SKU-01")` is called, Spring computes the corresponding key and queries the cache:

- **Entry already exists for that key (cache hit):** returns the stored value; the body of `findProduct` does not run.
- **No entry exists for that key (cache miss):** runs the body of `findProduct`; if it succeeds and caching is permitted, stores the result under that key and then returns it.

**Terminology note:** "key" here refers to a *cache key*, not a thread-synchronization *lock*. Caching still involves a key even when no corresponding entry exists yet; saying "there is no key" colloquially is more accurately understood as **"there is no entry matching the key being looked up"**. Locking when multiple threads miss simultaneously is explained in section 8.

Another distinction to make: **omitting the `key` attribute in `@Cacheable`** does not mean the cache uses no key. Spring still generates a default key from the arguments; see section 5.

## 2. Components Involved in the Flow

| Component | Role in cache hit/miss |
| --- | --- |
| `@Cacheable` | Declares cache region (`cacheNames`), key generation, and conditions |
| Spring AOP proxy and `CacheInterceptor` | Intercepts external calls through the proxy and orchestrates lookup/storage steps |
| `CacheManager` / `CacheResolver` | Determines the cache region(s) to use |
| `KeyGenerator` or SpEL `key` expression | Computes the key for the invocation |
| `Cache` | Contract for `get`/`put`/`evict`/`clear` operations |
| Providers such as ConcurrentMap, Caffeine, Redis | Store and look up actual entries, applying lifetime/eviction policies |
| Business method | Runs only when needed to compute/load the result, such as on a miss |

Example declaration:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public String findProduct(String sku) {
    return repository.loadName(sku);
}
~~~

The snippet above is illustrative only; `repository` is not defined. `#p0` is the first parameter (`sku`). `cacheNames = "products"` selects the cache region, while the key identifies **the entry within that region**. Combining both factors gives the logical lookup:

~~~text
cacheName = "products"
key       = "SKU-01"
             |
             v
CacheManager -> Cache("products") -> get("SKU-01")
~~~

The cache name and key have separate responsibilities: the same key `"SKU-01"` in the `products` cache and the `stocks` cache does not automatically point to the same entry.

## 3. Complete Flow from Call to Result

For standard proxy caching, the flow can be depicted as:

~~~text
Caller invokes service.findProduct("SKU-01")
                   |
                   v
       Spring proxy / CacheInterceptor
                   |
                   v
       Read @Cacheable and resolve Cache
                   |
                   v
       Evaluate condition (if any)
                   |
             false | true
                   |   |
                   |   v
                   | Compute cache key
                   |   |
                   |   v
                   | Cache.get(key)
                   |   |
                   |   +---- HIT ------------------+
                   |   |                           |
                   |   +---- MISS ----+            |
                   |                  |            |
                   v                  v            |
            Invoke real          Invoke real       |
               method               method         |
                   |                  |            |
                   |                  v            |
                   |        Evaluate unless        |
                   |           after execution     |
                   |                  |            |
                   |          Allowed to store?    |
                   |           /          \        |
                   |         Yes           No      |
                   |          |             |      |
                   |          v             |      |
                   |     Cache.put(key, val)|      |
                   |          |             |      |
                   +----------+-------------+------+
                              |
                              v
                    Return result to caller
~~~

The diagram represents the conceptual flow for **a single synchronous `@Cacheable`, one cache region, and a successful call**. Asynchronous providers, reactive return types, multiple caches, or additional rules may differ in execution details; do not treat this diagram as a line-by-line representation of internal source code.

### Step 1 — The call must go through the caching mechanism

Annotations do not automatically alter the bytecode of arbitrary Java objects. With Spring's common proxy mode, the container creates a proxy/advice around the cached bean. Callers must invoke through the bean proxy and caching must be enabled, e.g., with `@EnableCaching`. Calling `new MyService()` outside the container or `this.findProduct(...)` from within the same object can bypass the proxy, causing the method body to run every time.

### Step 2 — Resolve the cache region and pre-invocation condition

Spring reads `cacheNames` or equivalent configuration to locate the `Cache`. If `condition` is present, the expression is evaluated against the invocation context **before accessing the cache**:

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()"
)
~~~

If `sku` is null or blank, the condition evaluates to false; Spring skips cache lookup and storage for this operation and calls the business method normally. This is a **bypass**, not a cache miss, because no entry lookup is actually performed for that operation.

### Step 3 — Compute the key and check the entry

For instance, `key = "#p0"` produces key `"SKU-01"` when the first argument is that string. The provider is queried to see whether an entry with that key exists. An entry may be missing because it was never loaded, was evicted/cleared, exceeded its TTL, or does not exist in the specific cache instance being queried.

Distinguish "entry not found" from "cache storing a null result." The `Cache.get(key)` interface returns a `ValueWrapper` when an entry is found and `null` when there is no mapping; `ValueWrapper.get()` can contain null if the implementation supports caching null values. At the annotation layer, how `null`/`Optional.empty()` are stored also depends on provider support.

### Step 4A — Cache hit: return the stored result

If the entry exists, the interceptor retrieves the value and returns it to the caller. **The method body does not run**, avoiding expensive repository/API calls. This is where the primary resource savings come from.

~~~text
Call 1: findProduct("SKU-01")
Cache["SKU-01"] = "Ballpoint pen" -> HIT -> return "Ballpoint pen"
No new database query.
~~~

This also means any side effects inside the body are skipped. Do not place `@Cacheable` on methods that must execute a transaction, send an email, or perform mandatory state checks on **every** invocation.

### Step 4B — Cache miss: run the method, optionally write back

If no entry exists, the interceptor delegates the call to the real method. When the method returns successfully, Spring evaluates `unless` (if declared). If not vetoed, the result is put into the cache under the corresponding key and returned to the caller.

~~~text
Call 1: findProduct("SKU-02")
Cache["SKU-02"] absent -> MISS
  -> repository.loadName("SKU-02")
  -> receives "Notebook"
  -> Cache.put("SKU-02", "Notebook")
  -> return "Notebook"

Call 2: findProduct("SKU-02")
Cache["SKU-02"] exists -> HIT -> return "Notebook"
Method body does not run the second time.
~~~

When the method throws an exception, it is not a successful result for `@Cacheable` to cache by default. If reading or writing the cache itself fails, the application may need a dedicated error-handling policy (`CacheErrorHandler`) and must consider the provider's capabilities.

## 4. Comparison Table: Cache Hit, Miss, and Bypass

| Scenario | Lookup cache? | Run method body? | Write to cache? |
| --- | --- | --- | --- |
| Entry already exists (**hit**) | Yes | No | Not needed |
| Entry absent (**miss**) and method succeeds | Yes | Yes | Yes, unless rejected by `unless` |
| `condition` evaluates to false (**bypass**) | Not for this operation | Yes | No |
| Miss, result satisfies `unless` | Yes | Yes | No |
| Miss, method throws exception | Yes | Yes | Does not cache a successful result |
| Entry removed by `@CacheEvict`, called again | Yes | Yes on the next call if still a miss | Can be cached again |

"Not in the cache" does not mean "returns nothing": a **cache miss still returns the result of the underlying method** if it executes successfully. The cache only decides whether to reuse a known result or compute/load it fresh.

## 5. Omitting the key Attribute: Spring Still Generates a Key

The following two cases can both use a key derived from the `sku` parameter, despite being written differently:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public String load(String sku) { /* ... */ return sku; }

@Cacheable(cacheNames = "products")
public String loadDefaultKey(String sku) { /* ... */ return sku; }
~~~

These are snippets illustrating annotation rules; two methods sharing the same cache name and key should not be treated as safe independent examples in a real application, as they could accidentally **share entries**.

When neither a `key` expression nor a custom `keyGenerator` is provided, Spring uses the default `SimpleKeyGenerator`:

| Invocation parameter list | Default key |
| --- | --- |
| No parameters | `SimpleKey.EMPTY` |
| Single non-null parameter | The parameter object itself |
| Multiple parameters, or a single null parameter | `SimpleKey` wrapping the parameter values |

For example, with `@Cacheable("products")`: `load("SKU-01")` typically uses the key `"SKU-01"`; with `loadByPair("SKU-01", "vi")`, the key is the combination of both parameters. Because keys rely on arguments, you must verify `equals()`/`hashCode()` of objects used as keys and avoid mutable objects whose instability breaks key matching.

Notably, the default key **does not automatically include the method name**. Two different methods sharing the same `cacheNames`, parameters, and key values can collide on entries even though their results have different meanings. Use separate cache names or design appropriately namespaced keys.

## 6. Runnable Spring Framework Example — Observing Entry Presence and Absence

This Java 17 example uses Spring Framework 6.2.10, Maven, and `ConcurrentMapCacheManager` (in-memory cache). It uses `CacheManager.getCache("products").get(...)` to inspect entry state directly and uses a counter to prove whether the body ran.

Project structure:

~~~text
spring-cache-flow/
├── pom.xml
└── src/main/java/demo/CacheFlowDemo.java
~~~

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-cache-flow</artifactId>
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

Create `src/main/java/demo/CacheFlowDemo.java`:

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class CacheFlowDemo {

    @Configuration(proxyBeanMethods = false)
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
        private final AtomicInteger loads = new AtomicInteger();

        @Cacheable(cacheNames = "products", key = "#p0")
        public String getProduct(String sku) {
            int call = loads.incrementAndGet();
            System.out.println("LOAD " + sku + " #" + call);
            return "value-" + sku;
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public void evict(String sku) {
            System.out.println("EVICT " + sku);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            var service = context.getBean(ProductService.class);
            var cache = context.getBean(CacheManager.class)
                               .getCache("products");

            System.out.println("Before A: " + (cache.get("A") != null));
            System.out.println("1: " + service.getProduct("A"));
            System.out.println("After A: " + (cache.get("A") != null));
            System.out.println("2: " + service.getProduct("A"));
            System.out.println("3: " + service.getProduct("B"));

            service.evict("A");
            System.out.println("A after evict: "
                               + (cache.get("A") != null));
            System.out.println("4: " + service.getProduct("A"));
        }
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheFlowDemo
~~~

Stdout printed by the program (Maven may print separate messages depending on the environment):

~~~text
Before A: false
LOAD A #1
1: value-A
After A: true
2: value-A
LOAD B #2
3: value-B
EVICT A
A after evict: false
LOAD A #3
4: value-A
~~~

Trace-by-trace breakdown:

| Line | State | Mechanism |
| --- | --- | --- |
| `Before A: false` | Cache does not have `A` yet | `Cache.get("A")` has no entry |
| `LOAD A #1` and `1: value-A` | First miss | Spring runs the method, then stores the result |
| `After A: true` | Entry exists | Cache actually holds key `A` |
| `2: value-A`, no `LOAD A #2` | Hit | Method body is skipped |
| `LOAD B #2` | Different key so miss | `B` is independent of `A` |
| `EVICT A`, `A after evict: false` | Removes entry `A` | `@CacheEvict` evicts after the method succeeds |
| `LOAD A #3` | Misses again after eviction | Spring reloads and caches again |

To reason accurately about the output, follow the call sequence. After the second-call hit, the `loads` counter stays at 1; calling key `B` advances it to 2; evicting `A` does not increment the counter; reloading `A` brings it to 3.

In this demo, updating the cache contents is handled by the Spring interceptor working with `ConcurrentMapCache`. `@Cacheable` does not create a database nor store data forever; the manager determines where data is kept.

### Why does the example retrieve the bean through ApplicationContext?

Calling `context.getBean(ProductService.class)` obtains the Spring-managed bean, which has the proxy/interceptor handling annotations. Replacing it with `new ProductService()` and calling directly would leave the annotations ineffective: every call would run `getProduct`, even though the annotation syntax remains in the code. In proxy mode, internal calls like `this.getProduct("A")` also bypass the proxy, so avoid them when expecting caching.

## 7. Conditions That Prevent a Miss from Writing the Result

### `condition`: decides whether to enter the caching mechanism

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()"
)
public String find(String sku) {
    return repository.loadName(sku);
}
~~~

The snippet assumes `repository` exists. With `sku = ""`, the condition is false: the cache is neither queried nor written. With `sku = "A"`, the condition is true: Spring proceeds to look up key `A` and then hits or misses depending on current data.

### `unless`: evaluated only after the method has executed

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    unless = "#result == null || #result.isBlank()"
)
public String find(String sku) {
    return repository.loadName(sku);
}
~~~

On a miss where the method returns an empty string, `unless` evaluates to true so **no entry is written**. Consequently, the next call with the same key will still miss and run the method again. If the method returns a valid non-blank string, the result can be stored.

On a **hit**, the method is already skipped; `unless` is not a way to force the method to run to verify the latest data. If you need to ensure changed data is visible, establish an invalidation/TTL strategy.

Do not confuse a **miss** with being "vetoed by `unless`": a miss describes the **entry state before execution**, whereas `unless` decides **whether to store the newly computed result**.

## 8. What Happens When Multiple Threads Look Up an Absent Key Simultaneously?

Although the main topic is *cache keys*, the term "key" is sometimes confused with a **lock** in concurrency. These are two distinct concepts:

- **Cache key:** identifies a result, such as `"SKU-01"`; it exists even without any lock.
- **Lock/synchronization:** coordinates multiple threads so they do not simultaneously compute expensive data for the same key.

Suppose threads T1 and T2 both call `getProduct("A")` when the cache is empty:

~~~text
T1: Cache.get("A") -> MISS -> starts loading A ----- put("A")
T2: Cache.get("A") -> MISS -> starts loading A ----- put("A")
~~~

With default `@Cacheable`, two loads can happen concurrently. This effect is called a **cache stampede** (multiple requests piling onto a slow source). Having the same cache key **does not automatically create a lock** protecting data loading.

Spring supports:

~~~java
@Cacheable(cacheNames = "products", key = "#p0", sync = true)
public String getProduct(String sku) {
    return repository.loadName(sku);
}
~~~

`sync = true` asks the provider to synchronize value loading for the corresponding key. This is an **implementation-dependent capability**; it is not a guarantee of a distributed lock across JVMs. Spring restricts synchronized usage: only a single cache, `unless` is not supported, and no other cache operations may be combined on the same method. You must test the chosen provider and real data-loading path under concurrency.

Common situations:

| State | `sync = false` (default) | `sync = true` |
| --- | --- | --- |
| Key already has an entry | Returns from cache | Returns from cache |
| Key absent, single caller | Calls method, can cache | Calls method, can cache |
| Multiple callers miss simultaneously | May all call the method | Provider is asked to coordinate loading per key |
| Multiple independent instances | Backend-dependent | Does not automatically become a global lock |

Do not pick `sync = true` just so "the cache has a lock." Frame the problem accurately: if recomputing the result is fast, duplicate loads may be acceptable; if loading is very expensive, evaluate provider support, latency, timeouts, and failure behavior when a loading request throws.

## 9. Invalidation: Returning from Hit to Miss

A cache hit does not guarantee fresh data. If the database updates a product while entry `A` has not been removed, lookups can still hit and return the stale version. A common strategy is **write to the source of truth, then evict the related entry**:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product read(String sku) {
    return repository.findBySku(sku);
}

@CacheEvict(cacheNames = "products", key = "#p0")
public void update(String sku, Product newValue) {
    repository.save(sku, newValue);
}
~~~

This is an illustrative snippet, not a standalone program; `Product`, `repository`, and transaction configuration must be defined. By default, `@CacheEvict` removes the entry after the method completes successfully. `beforeInvocation = true` can evict before the invocation, but you must understand the consequences if updating the source fails.

With database transactions, **cache eviction and transaction commit times can differ**. If the cache is evicted before the transaction commits, another reader may miss and reload the old data. Applications must consider after-commit/transaction-aware cache policies and consistency requirements. Having `@Cacheable` does not turn the cache and database into a single atomic transaction.

Entry freshness also depends on provider TTL/eviction. Spring's Cache abstraction does not define a single default TTL across all backends; Caffeine/Redis have their own storage mechanisms and policies. Once an entry expires, the next invocation is handled as a **miss** and can reload fresh data.

## 10. Common Mistakes When Explaining or Debugging the Flow

**Mistake 1: "If `key` isn't specified, Spring has no key."** False; by default Spring generates a key from the parameters via `SimpleKeyGenerator`. To inspect accurately, determine which parameters the method receives and which cache name is used.

**Mistake 2: "A cache miss returns null."** False; a miss normally executes the underlying method and returns its result. Null might be a **business return value**, but it is not the definition of a miss.

**Mistake 3: "A hit still runs the body to check the latest DB state."** False; a cache hit returns the previously stored data unless appropriate invalidation/expiry or bypass mechanisms are in place. Freshness requirements belong to business design.

**Mistake 4: "Adding `@Cacheable` means every call is intercepted."** False for calls on manually instantiated objects, self-invocation in proxy mode, or when caching is not enabled. Always verify the call path goes through the bean/proxy.

**Mistake 5: "If two requests share a key, only one ever loads."** False by default. `sync = true` with a supporting provider can curb redundant computations; it is not a universal distributed locking mechanism.

**Mistake 6: "Sharing the same key across multiple methods is always safe."** False; keys do not include the method name by default. Separate cache names or use a proper namespace/key strategy for distinct value types.

### Ordered Debugging Checklist

1. Verify caching is enabled in the application and the call passes through the Spring bean proxy.
2. Read `cacheNames` accurately; avoid confusing the cache name with the entry key.
3. Compute the key from the actual invocation: explicit `key`/`keyGenerator` or default `SimpleKeyGenerator`.
4. Check `condition`: was the operation bypassed up front?
5. Observe entry existence in the **exact provider/instance** serving the request.
6. On a miss, check what the method returns, whether it throws an exception, and whether `unless` prevents caching.
7. If subsequent calls still miss, check `@CacheEvict`, TTL, eviction, cache managers, multiple instances, and backend serialization/key-mapping rules.
8. If multiple requests miss concurrently, check concurrency behavior and the provider's support level for `sync = true`.

## 11. Self-Check Exercises

**Exercise 1.** The cache is empty. Call `load("A")`, `load("A")`, `load("B")`, `load("A")` sequentially with `@Cacheable(cacheNames="items", key="#p0")`, with calls passing through the proxy and no eviction/expiry. How many times does the underlying method run? **Twice:** the first miss for A and the first miss for B; the remaining two calls for A are hits.

**Exercise 2.** A method has `@Cacheable(cacheNames="items", unless="#result == null")`, and the first call returns null. Will calling the same key again automatically hit? **No:** unless an entry was written from elsewhere, the null result was blocked from being cached by `unless`, so the next call misses again.

**Exercise 3.** `@Cacheable(cacheNames="items")` omits `key` and takes a single String parameter `"A"`. Does a lookup occur? **Yes.** Spring automatically uses the default key `"A"`, so hit/miss operates normally.

**Exercise 4.** After calling `evict("A")`, how is the next `load("A")` handled? **Miss** if the entry was actually removed from the right cache region and no other request has reloaded it; the underlying method runs and can write a new entry.

**Exercise 5.** Two threads miss key A simultaneously; is only one thread guaranteed to enter the method? **No** by default. To coordinate loading, investigate `sync = true` and the specific provider's capabilities.

## Conclusion

With `@Cacheable`, follow **cache name → key → entry state → action**. If an entry already exists, Spring can return the value immediately without running the method. If absent, the underlying method executes and its result can be stored for future hits. Omitting `key` still yields a default key; a cache key identifies an entry, whereas locking is a matter of coordinating concurrent access. Understanding this sequence helps debug unexpected cache misses, stale data, and duplicate computations.

## Official Documentation

- Spring Framework Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Default Key Generation: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html#cache-annotations-cacheable-default-key
- Synchronized Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html#cache-annotations-cacheable-synchronized
- Spring Cache API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html