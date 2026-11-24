# CacheInterceptor, Annotation Metadata, and Invocation Flow in Spring Framework

## 1. Goal and Big Picture

Spring Cache is an **abstraction layer** for applying caching to method invocations. Annotations declare *when to read/write/evict the cache*; Spring AOP intercepts calls and communicates with the cache provider through Spring interfaces. Spring does not itself define time-to-live (TTL), capacity-based eviction policies, persistence, or data distribution: those capabilities belong to the cache backend (ConcurrentMap, Caffeine, Redis, etc.).

Focus on three questions:

1. Why can a call to `service.findById(42)` return a result without executing the method body?
2. How does Spring discover and interpret metadata from `@Cacheable`, `@CachePut`, `@CacheEvict`, `@Caching`, and `@CacheConfig`?
3. During an actual invocation, how does `CacheInterceptor` decide the order of cache lookup, business method execution, and cache update?

**Core distinctions:** `CacheInterceptor` is the advice intercepting the method; `CacheOperationSource` returns the *operation definitions* from annotations; `CacheAspectSupport` handles the execution flow; `CacheResolver` selects the concrete caches; `KeyGenerator` or SpEL chooses the key; `CacheManager` and `Cache` provide the data storage.

## 2. Components and Responsibilities

| Component | Role | Key points to remember |
| --- | --- | --- |
| `@EnableCaching` | Activates annotation-based caching infrastructure in the Spring context. | Having annotations on methods alone is not enough; caching configuration and an appropriate cache must be present. |
| `BeanFactoryCacheOperationSourceAdvisor` and pointcut | Tells Spring AOP which methods have cache operations and need advice. | Relies on `CacheOperationSource`; only calls passing through the proxy are intercepted in default proxy mode. |
| `CacheInterceptor` | AOP Alliance `MethodInterceptor` receiving `MethodInvocation` and delegating to the caching handler. | Extends `CacheAspectSupport`; caching logic resides mainly in the superclass, not in the business method. |
| `CacheOperationSource` | Looks up metadata matching a method and target class. | The common annotation implementation is `AnnotationCacheOperationSource`. |
| `SpringCacheAnnotationParser` | Converts annotations/configurations into objects describing cache operations. | Supports composed annotations and meta-annotations; `@Caching` can declare multiple operations. |
| `CacheOperation` | Immutable metadata model for an operation: cache names, key, condition, resolver, etc. | Variants include `CacheableOperation`, `CachePutOperation`, `CacheEvictOperation`. |
| `CacheAspectSupport` | Builds per-invocation context, checks hit/miss and conditions, and coordinates invoke/put/evict. | Processes metadata and SpEL, including some synchronous/asynchronous branches. |
| `CacheResolver` | Determines the set of `Cache` instances used for the operation. | `SimpleCacheResolver` typically resolves caches by name from `CacheManager`. |
| `KeyGenerator` | Generates the key from target, method, and arguments when no SpEL `key` is given. | Defaults to `SimpleKeyGenerator`. |
| `CacheManager` / `Cache` | Provides cache regions and `get`, `put`, `evict`, `clear` operations. | TTL, serialization, cross-node sharing, and atomicity depend on the provider. |
| `CacheErrorHandler` | Error handling policy when interacting with the cache. | Defaults to `SimpleCacheErrorHandler`, which rethrows cache errors to the caller. |

### Two Phases to Distinguish

**Configuration phase:** Spring processes `@EnableCaching`, creates `CacheOperationSource`, the interceptor, and the advisor; AOP decides which beans/methods need proxying. The main machinery in proxy mode includes `ProxyCachingConfiguration`, `CacheInterceptor`, and the advisor. Spring can inspect cache metadata to match the pointcut.

**Method invocation phase:** The caller invokes the bean through its proxy. The interceptor grabs the method, target, and arguments, queries `CacheOperationSource`, and executes according to the operation. Annotation scanning does not necessarily repeat from scratch on every request: `AbstractFallbackCacheOperationSource` caches resolution results per method/target class; `CacheAspectSupport` also retains prepared metadata such as key generators and resolvers.

## 3. From Annotation to Executable Metadata

Example declaration:

~~~java
@CacheConfig(cacheNames = "products")
public class ProductService {
    @Cacheable(key = "#p0", condition = "#p0 > 0",
               unless = "#result == null")
    public Product find(long id) {
        // Read from data store
        return repository.findById(id).orElse(null);
    }
}
~~~

This snippet is an **illustration inside a Spring application that already has `Product`, `repository`, and cache configuration**, not a standalone Java file.

Conceptually, the metadata resolution steps are:

1. `CacheOperationSource` receives the pair `(Method, targetClass)`, locating the concrete implementation method and applicable declarations on the method/class according to Spring's rules.
2. `AnnotationCacheOperationSource` uses a parser that understands `@Cacheable` and related annotations, merging class-level defaults from `@CacheConfig` when appropriate.
3. Spring builds a `CacheableOperation` object containing the cache name `products`, the SpEL string `#p0`, `condition`, and `unless`—not the evaluated SpEL result of any specific call.
4. `CacheAspectSupport` resolves and may cache `CacheOperationMetadata`, including the `CacheResolver`/`KeyGenerator` configuration for the operation; each invocation then builds a context to evaluate against the current arguments, target, and result.
5. `@CacheConfig` is only default configuration; **by itself it creates no cache operation**. Values on the method annotation take precedence over class-level defaults; global configuration set via `CachingConfigurer` or cache infrastructure forms the remaining tier.

For example, `@Cacheable(cacheNames = "products", key = "#p0")` declares how to compute the key; only at runtime is `#p0` substituted with the first argument of the call, such as `42`. Therefore, **stable annotation metadata** and **per-invocation key/condition values** are two distinct things.

### Which Annotations Correspond to Which Operations?

| Annotation | Primary handling | Meaningful timing |
| --- | --- | --- |
| `@Cacheable` | Reads cache first; on a valid hit, can skip calling the method; on a miss, calls the method then puts. | `condition` before reading; `unless` after obtaining the result, before putting. |
| `@CachePut` | Still runs the method; then writes the result to cache if conditions pass. | Suitable for updating or refreshing data, not for skipping method execution. |
| `@CacheEvict` | Evicts one key or all entries of a cache region. | By default after the method succeeds; `beforeInvocation = true` evicts beforehand. |
| `@Caching` | Groups multiple cache operation declarations on one method. | Each operation has its own cache name/key/condition. |
| `@CacheConfig` | Declares class-level defaults: cache names, manager, resolver, key generator. | Does not execute get/put/evict if operation annotations are missing. |

You can define a **meta-annotation** by placing `@Cacheable` on a custom annotation to reuse policies, e.g., `@Retention(RUNTIME)` and `@Target(METHOD)` combined with `@Cacheable("products")`. Do not confuse annotation metadata with cached data: metadata describes *rules*, whereas `Cache` stores *computed values*.

## 4. Detailed Invocation Flow of CacheInterceptor

### 4.1. Typical Path of `@Cacheable`

~~~mermaid
sequenceDiagram
    participant Caller
    participant Proxy as Spring AOP proxy
    participant I as CacheInterceptor
    participant S as CacheOperationSource
    participant R as CacheResolver/Key logic
    participant C as Cache
    participant T as Target method

    Caller->>Proxy: find(42)
    Proxy->>I: invoke(MethodInvocation)
    I->>S: getCacheOperations(method, targetClass)
    S-->>I: CacheableOperation
    I->>R: evaluate condition, resolve caches and key
    R-->>I: cache products, key 42
    I->>C: get(42)
    alt Cache hit
        C-->>I: cached value
        I-->>Proxy: cached value
    else Cache miss
        C-->>I: missing entry
        I->>T: invocation.proceed()
        T-->>I: computed value
        I->>I: evaluate unless against result
        opt Put is allowed
            I->>C: put(42, computed value)
        end
        I-->>Proxy: computed value
    end
    Proxy-->>Caller: return value
~~~

The diagram depicts the basic branch of a synchronous, single-cache `@Cacheable` without other combined operations; the internal implementation has numerous optimization branches and edge cases. If `condition` is false, the method still executes without applying caching for that `@Cacheable`. On a hit, `unless` is not a re-check of the old entry: it uses the **new result after invocation** to decide whether to put.

At the internal API level:

- `CacheInterceptor.invoke(MethodInvocation)` supplies a business method invoker wrapping `invocation.proceed()`, then delegates to `CacheAspectSupport.execute(...)`.
- `execute` collects applicable operations and constructs a `CacheOperationContext` with the method, args, target, caches, and metadata. `CacheAspectSupport` uses `invokeOperation` when it needs to invoke the target.
- For `@Cacheable`, execution checks conditions first, looks up the cached value, and distinguishes a miss from a valid cached value; on a miss, it invokes the target, evaluates `unless`, and writes to the cache if permitted.
- Beyond that path, there is handling for pre/post eviction, put requests, `sync=true` synchronization, asynchronous return types, cache errors, and coordinating multiple operations. You should not oversimplify the algorithm into a single sentence like "the interceptor always does get → invoke → put".

### 4.2. How Do Hit and Miss Differ?

| Aspect | Valid cache hit | Cache miss |
| --- | --- | --- |
| Metadata lookup / condition check | Yes | Yes |
| Key computation and cache lookup | Yes | Yes |
| Body of `find(...)` | **Does not run** in normal cacheable flow | **Runs** |
| Returned result | From cache | From target method |
| Cache write | Not needed when a single cache already hit; with multiple caches, missing caches may be populated | Written after invocation unless blocked by `unless` |

A `@Cacheable` is truly beneficial only when calls pass through caching advice, the key reflects all data that must be distinguished, the cached value remains valid, and the cache backend meets the desired consistency guarantees.

### 4.3. `@CachePut` and `@CacheEvict` on the Same Path

- **`@CachePut`:** does not use a cache hit to skip the business method; the method still executes, and the final result is put if the operation applies. For example, updating an entity and using `@CachePut(cacheNames = "products", key = "#result.id")` to refresh the newly saved record. `#result` is available after invocation and null results must be handled.
- **Default `@CacheEvict`:** runs the method first, and if it succeeds, evicts the key; if the method throws an exception, post-invocation eviction generally does not run. `@CacheEvict(beforeInvocation = true)` performs eviction **before** running the method, even if the method subsequently fails.
- **`allEntries = true`:** removes all entries in the selected cache, ignoring the key for this eviction operation; consider the impact on all callers.
- **Multiple operations:** `@Caching` allows declaring multiple puts/evictions, though combining `@Cacheable` and `@CachePut` on the same method typically creates conflicting expectations: one can skip invocation while the other requires invocation. Use it only after analyzing and testing mutually exclusive conditions.

## 5. Key, Cache Resolution, and SpEL During Invocation

### 5.1. Key Generation

If neither `key` nor `keyGenerator` is set, `SimpleKeyGenerator` defaults to generating:

- No arguments: `SimpleKey.EMPTY`.
- Single argument: the argument itself (with special handling for arrays).
- Multiple arguments: a `SimpleKey` holding the arguments in order.

Keys must be stable and meaningful with respect to `equals()/hashCode()`. If an object's state mutates after being used as a key, or if the key omits tenant, locale, user role, pagination, or any parameter affecting the result, the cache can return wrong data or leak data across contexts. The cache name does not automatically add those factors to the key.

Illustrative SpEL syntax:

~~~java
@Cacheable(cacheNames = "catalog", key = "#p0 + ':' + #p1")
public Product lookup(String tenantId, String sku) {
    // ...
}

@Cacheable(cacheNames = "catalog", key = "#root.methodName + ':' + #p0")
public Product lookupById(long id) {
    // ...
}
~~~

These are **illustrative methods** that must reside in a Spring bean with a proper implementation. You can use positional `#a0` or `#p0`; use `#argumentName` only when parameter names are actually present in compiled metadata, typically requiring `-parameters`. `#root.methodName`, `#root.targetClass`, `#root.args`, and `#root.caches` provide context to SpEL.

`key = "..."` and `keyGenerator = "beanName"` are mutually exclusive. Specify one clear policy; if creating a custom `KeyGenerator`, test key stability across multiple nodes and code versions.

### 5.2. Cache Selection

`cacheNames = "products"` specifies the cache region name. `CacheResolver` selects the concrete `Cache` objects; by default the resolver uses the configured `CacheManager`. You can select `cacheManager` or `cacheResolver` on an operation, but never declare both mutually exclusive attributes at once. Multi-tenant/multi-region setups may need a custom resolver, while ensuring every request is routed to the right cache.

If `@Cacheable` configures **multiple caches**, Spring can check each cache for a hit and populate caches that were missing the entry; do not assume all providers share identical lookup characteristics, especially with asynchronous caches.

### 5.3. `condition`, `unless`, and `#result`

~~~java
@Cacheable(cacheNames = "catalog",
           key = "#p0",
           condition = "#p0 > 0",
           unless = "#result == null")
public Product find(long id) {
    // ...
}
~~~

- `condition` is checked before lookup: when `id <= 0`, the caching operation is skipped.
- `unless` is checked after the method returns a result: e.g., do not store a `null` result.
- `#result` is available in `unless` and certain post-invocation expressions of `@CachePut` and `@CacheEvict`; do not treat `#result` as available in `condition` before the method runs.
- For `Optional<T>` return types supported by Spring, `#result` represents the unwrapped inner value rather than the `Optional` wrapper.

## 6. Runnable Example: Observing Hit, Put, and Evict

The example uses Java 17+, Spring Framework 7.0.9, and `ConcurrentMapCacheManager` (an in-process in-memory cache). Only JDK 17+ and Maven are required. Create the following two files.

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cache-interceptor-flow</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
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

**`src/main/java/demo/CacheFlowDemo.java`**

~~~java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheFlowDemo {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("items");
    }

    @Bean
    ItemService itemService() {
        return new ItemService();
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(CacheFlowDemo.class)) {
            ItemService service = context.getBean(ItemService.class);

            System.out.println(service.find(42));
            System.out.println(service.find(42));
            System.out.println(service.refresh(42));
            System.out.println(service.find(42));
            service.evict(42);
            System.out.println(service.find(42));
        }
    }

    public static class ItemService {
        private int calls;

        @Cacheable(cacheNames = "items", key = "#p0")
        public String find(int id) {
            System.out.println("DB read " + id + " #" + (++calls));
            return "item-" + id + "-v" + calls;
        }

        @CachePut(cacheNames = "items", key = "#p0")
        public String refresh(int id) {
            System.out.println("refresh " + id + " #" + (++calls));
            return "item-" + id + "-v" + calls;
        }

        @CacheEvict(cacheNames = "items", key = "#p0")
        public void evict(int id) {
            System.out.println("evict " + id);
        }
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheFlowDemo
~~~

Lines printed by the program in order (excluding environment-dependent logs):

~~~text
DB read 42 #1
item-42-v1
item-42-v1
refresh 42 #2
item-42-v2
item-42-v2
evict 42
DB read 42 #3
item-42-v3
~~~

**Stage-by-stage explanation:**

1. First `find(42)` misses, the interceptor calls `ItemService.find`, prints `DB read 42 #1`, and writes key `42` into `items`.
2. Second `find(42)` hits, so `DB read` does **not** appear again.
3. `refresh(42)` always executes, produces `item-42-v2`, and updates the cache via `@CachePut`.
4. Subsequent `find(42)` retrieves `item-42-v2` from cache; `calls` does not increment.
5. `evict(42)` completes and deletes the key; the next `find(42)` misses and runs the method body to produce version `v3`.

The example intentionally retrieves the bean from `context.getBean(...)` so calls pass through the proxy. Replacing it with `new ItemService().find(42)` creates an object outside the Spring context with no caching advice; calling `this.find(42)` from another method inside `ItemService` itself is also a self-invocation case that bypasses the proxy.

## 7. Real-World Limitations and Tricky Scenarios

### 7.1. Proxies and Internal Calls

With default `@EnableCaching` (`mode = PROXY`), Spring only intercepts calls **passing through the bean proxy**. Common situations where annotations seem "not to run":

- Instantiating manually with `new` instead of obtaining a Spring bean.
- One method calling another method on the same instance via `this.method()` (self-invocation), even if the target method has `@Cacheable`.
- Placing annotations on private methods or methods that cannot be intercepted by the proxy under the current configuration.
- Caching is not enabled, the bean is not in the configured context, or the class/method and proxy mode are incompatible.
- Expecting the interceptor to run during bean initialization before the proxy is ready, e.g., calling from `@PostConstruct`.

The usual fix is moving the cacheable method to a separate Spring bean and calling that bean via dependency injection. `mode = ASPECTJ` can intercept self-invocation via weaving, though it requires corresponding AspectJ setup; do not enable it merely for one minor call. Prefer placing cache annotations on public methods of concrete classes for predictability.

### 7.2. Concurrent Misses and `sync = true`

By default, two concurrent requests missing the same key can **both recompute** the data. `@Cacheable(sync = true)` instructs the cache provider to coordinate so one request computes while others wait for the value; actual support depends on the provider. This is not a global lock maintained by `CacheInterceptor` itself.

`sync = true` has limitations: only a single cache; no `unless`; no combining with other cache operations on the same method along this synchronized path. Verify provider support before relying on it to prevent cache stampedes.

### 7.3. Cache Errors, Business Exceptions, and Null Values

- Business method throws an exception: a normal `@Cacheable` call produces no successful result to cache. Do not assume Spring caches exceptions.
- Cache backend errors: `SimpleCacheErrorHandler` by default propagates errors to the caller; a custom `CacheErrorHandler` may choose to ignore cache access errors and proceed to compute the value, while weighing consistency risks and observability.
- Providers may support caching `null`; a cache hit holding a null value must be distinguished from a miss. Check the null policy of each `Cache`/provider.
- `@CacheEvict(beforeInvocation = true)` evicts beforehand even if the business method subsequently fails; use only when that behavior is truly acceptable.

### 7.4. Synchronizing Cache with Data Changes

A cache is a derived copy of a data source. `@CachePut` and `@CacheEvict` require the right key, right cache name, and right timing when data changes. With database transactions, pay attention to `@Transactional`/cache advice ordering: evicting or writing to the cache before commit can cause another request to observe stale data. Consider transaction-aware caching, post-commit invalidation, or a consistency strategy appropriate for your system.

Spring Cache does not automatically provide TTLs, database write-through, cross-node invalidation, or transactional guarantees between database and cache. These must be designed alongside the provider and data update paths.

### 7.5. Async and Reactive

Since Spring Framework 6.1, caching annotations adapt to `CompletableFuture` and certain reactive return types: retrieving/storing in cache attaches to the completed value, rather than naively assuming the raw `Mono`/`Flux` wrapper is always stored. Specific behavior still depends on the cache provider and configuration; test async cases specifically instead of mechanically applying the synchronous diagram in Section 4.

## 8. How to Verify and Troubleshoot

When a method annotated with `@Cacheable` still hits the database repeatedly, check in order:

1. **Is there a proxy?** Obtain the bean from Spring and check whether calls enter from outside the bean through the proxy. Distinguish self-invocation from direct construction.
2. **Is the operation metadata right?** Check `@EnableCaching`, class/method names, annotations, `@CacheConfig`, public visibility, and pointcut matching.
3. **Is the key repeating consistently?** Verify `#p0`, all parameters that actually affect the result, data types, and `equals()/hashCode()`. Different tenants/locales/permissions need distinct keys when the output depends on them.
4. **Is the right cache selected?** Review `cacheNames`, `CacheManager`/`CacheResolver`, bean names, and provider configuration.
5. **Are conditions preventing caching?** A false `condition` skips caching; a true `unless` blocks the put. Watch out for `#result` and nulls.
6. **Is there a writer/eviction?** `@CachePut`, `@CacheEvict`, provider TTL/eviction policies, or application restarts may explain the next miss.
7. **Are there multiple nodes or concurrent calls?** `ConcurrentMapCacheManager` keeps separate data per process; test concurrent misses to see whether `sync=true` or an external mechanism is needed.
8. **Are there backend or transaction errors?** Check cache error handling, serialization, latency, uncommitted data, and invalidation timing.

A small behavioral test suite should prove: the first call misses (method runs once), the second call hits (method does not run), `@CachePut` refreshes the value, `@CacheEvict` causes the next read to miss, `condition/unless` take the right branches, and self-invocation is handled as designed. Avoid testing merely by reading annotations; observe how many times the **target method actually executes** and inspect cache contents.

## 9. Common Misconceptions

- **"With `@Cacheable`, all calls are cached."** False for self-invocation, non-Spring-bean objects, missing AOP configuration, or false `condition`.
- **"`CacheInterceptor` reads annotations via reflection on every request."** Inaccurate: Spring resolves and caches metadata per method/target class; keys and conditions are still evaluated for each specific call.
- **"`@CachePut` is just like `@Cacheable`."** `@CachePut` does not skip the method; `@Cacheable` can skip it.
- **"`unless` decides whether to call the method."** On `@Cacheable`, `unless` decides whether to **store the new result** after the method; `condition` controls whether caching applies beforehand.
- **"A cache hit guarantees the freshest data."** There is no such guarantee if TTL/invalidation/transaction strategies are flawed.
- **"`sync=true` eliminates all race conditions."** It only coordinates loading a single entry according to provider capabilities, and does not replace data consistency mechanisms.
- **"If the cache fails, Spring automatically falls back to the DB."** By default errors may be thrown; a dedicated `CacheErrorHandler` policy is required to degrade gracefully.

## 10. Reference Documentation

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): annotations, cache keys, SpEL, sync, proxy mode, and conditional rules.
- [CacheInterceptor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/CacheInterceptor.html): `MethodInterceptor` implementation extending `CacheAspectSupport`.
- [CacheAspectSupport Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/CacheAspectSupport.html): `execute(...)`, `invokeOperation(...)`, metadata/context flow.
- [AnnotationCacheOperationSource Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/AnnotationCacheOperationSource.html): converts cache annotations into `CacheOperation`.

**Key takeaway:** `annotation → CacheOperation metadata → AOP proxy/CacheInterceptor → select cache and key → hit/miss → (if needed) invoke target → put/evict`. When debugging, always identify whether you are in the **metadata resolution**, **key computation**, **cache lookup**, or **business method execution** phase.
