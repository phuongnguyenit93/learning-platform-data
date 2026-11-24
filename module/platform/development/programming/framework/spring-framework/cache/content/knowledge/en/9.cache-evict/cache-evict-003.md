# @CacheEvict: beforeInvocation=false and evicting after a successful invocation

## 1. Objective

In Spring Framework Cache, `@CacheEvict` marks a method as invalidating stored data. The `beforeInvocation` attribute determines **when eviction is triggered relative to the invocation intercepted by caching advice**. The default value is `false`: the cache eviction request is performed **after the target method completes normally**, with no exception escaping.

~~~java
@CacheEvict(cacheNames = "products", key = "#p0", beforeInvocation = false)
public void rename(long id, String newName) {
    repository.rename(id, newName);
}
~~~

The example above is a snippet requiring a real Spring bean and repository. When `rename` completes normally, the interceptor handles eviction for the first parameter's key. When the method throws an exception outward, the annotation's post-invocation eviction does not run.

Three concepts must be kept distinct:

- **Method invocation success**: the method observed by the advice returned normally. Returning `false`, `null`, or a business status `FAILED` can still be a normal return.
- **Business success**: the database or domain was actually updated as expected. Spring does not infer this automatically from a status inside the result.
- **Transaction/commit success**: the data has committed and is observable by readers. `beforeInvocation=false` does not automatically guarantee eviction occurs after DB commit.

The objective of this lesson is to understand exact behavior when exceptions occur, how to use `condition`/`#result`, key or `allEntries`, impacts on transactions and concurrency, and how to test with a runnable Java 17 example.

## 2. When does CacheInterceptor handle eviction?

When an application has `@EnableCaching` and a bean is invoked through a Spring AOP proxy, `CacheInterceptor` receives the call and uses `CacheAspectSupport` to coordinate the cache operations discovered from annotation metadata. With `beforeInvocation=false`, the simple synchronous flow is:

~~~mermaid
flowchart TD
    A[Caller invokes Spring bean through proxy] --> B[CacheInterceptor]
    B --> C[Execute target method]
    C --> D{How did it finish?}
    D -- Exception escapes --> E[Propagate exception; no after-evict]
    D -- Normal return --> F[Evaluate condition after invocation]
    F --> G{condition true or omitted?}
    G -- No --> H[Do not evict; return result]
    G -- Yes --> I[Resolve cache and key or allEntries]
    I --> J[Cache.evict or Cache.clear]
    J --> K[Return result]
~~~

The diagram depicts **a single synchronous operation**, excluding futures/reactive types, multiple annotations, transaction-aware decorators, or provider errors. An eviction is requested after the method returns normally; the physical removal time may be executed later by the backend/decorator.

`CacheInterceptor` does not modify the database directly. It coordinates `Cache.evict(key)` or `Cache.clear()` after the business method finishes. `@CacheEvict` only performs invalidation, not computing/writing a new value into the cache. If the next read goes through `@Cacheable`, a cache miss usually leads to re-reading source data.

## 3. When does eviction happen and when does it not?

| Method scenario | Eviction with `beforeInvocation=false` | Explanation |
| --- | --- | --- |
| `void` returns normally | Yes, if condition allows | No return value needed |
| Returns an object or string | Yes, if condition allows | Normal invocation |
| Returns `false` | Still yes by default | `false` is not an exception |
| Returns `null` | Still yes by default | Null is not automatically treated as failure |
| Returns `FAILED` status without throwing | Still yes by default | Spring does not interpret business statuses |
| Throws an unchecked exception | No | Target method did not complete normally |
| Throws a checked exception | No | Exception escapes the invocation |
| Catches error internally and returns | May occur | Advice only sees a normal return |
| Modifies data then throws exception | No | Risk of stale cache if data was durably changed |
| Returns normally but `condition` is false | No | Operation skipped by condition |
| Internal call bypassing proxy | No | Cache advice is not invoked |

**Notable point:** if the business method succeeds but `Cache.evict` fails, the caller may still receive an exception from the cache layer (under the default `CacheErrorHandler`). Target method errors and errors occurring **after** the method must be separated when coordinating caching.

## 4. Differences between beforeInvocation=false and true

| Characteristic | `beforeInvocation=false` (default) | `beforeInvocation=true` |
| --- | --- | --- |
| Advice requests eviction | After target returns normally | Before invoking target |
| Target throws exception | Does not evict for that operation | Eviction was already requested beforehand |
| Is `#result` available for SpEL `key`/`condition`? | Yes | No, because no result exists yet |
| Method returns false normally | Can still evict | Eviction was already requested before knowing the result |
| Risk | Does not evict if side effects occurred before exception; transaction commit may come later | Can cause a cache miss and reload old data while the update is still in progress |
| Common purpose | Tie invalidation to an update command completing normally | Want eviction regardless of the update command's outcome |

Both depend on the cache backend's capabilities. With a transaction-aware cache, the physical action may be deferred; `beforeInvocation` determines the **advice trigger point**, not every synchronization detail of the provider.

## 5. Single-key eviction: must be symmetric with the read path

A cache-aside system typically uses `@Cacheable` to cache queries and `@CacheEvict` to remove the entry after an update:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product find(long id) {
    return repository.find(id);
}

@CacheEvict(cacheNames = "products", key = "#p0",
            beforeInvocation = false)
public void update(long id, ProductUpdate changes) {
    repository.update(id, changes);
}
~~~

This is a snippet inside a service, not a standalone Java file yet. When `find(42)` has cached the old product, `update(42, changes)` returning normally will evict key `42` in the `products` cache. The next `find(42)` must miss and load fresh data.

**Important pitfalls:**

- The read path uses `tenantId:productId`, while the evict path only uses `productId`, causing the stale entry not to be removed.
- The read path uses cache `products`, while the evict path uses cache `product`—two different caches.
- The read path generates keys using a custom `KeyGenerator`, while the evict path builds keys with SpEL using a different normalization rule.
- Keys missing tenant, locale, status, permission scope, or query filters affecting the result can return wrong data or evict the wrong scope.
- Parameter name `#id` is absent from compiled metadata: `#p0` or `#a0` can be more convenient when uncertain about the `-parameters` flag.

`key` and `keyGenerator` are **mutually exclusive** in the same operation. `cacheManager` and `cacheResolver` are also two cache-selection configurations not used simultaneously. Exact keys and cache names must be tested across GET/UPDATE/DELETE.

## 6. condition and #result after invocation

`@CacheEvict` has `condition` but **does not have `unless`**. With `beforeInvocation=false`, `condition` and `key` can reference `#result`, because the method has already completed.

Example: a method returns the number of updated rows, evicting only when rows actually changed:

~~~java
@CacheEvict(
    cacheNames = "products",
    key = "#p0",
    condition = "#result > 0",
    beforeInvocation = false
)
public int updatePrice(long id, long newPrice) {
    return repository.updatePrice(id, newPrice);
}
~~~

If the method returns `0` (no update), no eviction occurs; returning `1` evicts. This is a snippet assuming the repository returns the number of affected rows.

Another example with a boolean:

~~~java
@CacheEvict(
    cacheNames = "products",
    key = "#p0",
    condition = "#result == true",
    beforeInvocation = false
)
public boolean changeStatus(long id, String status) {
    return repository.changeStatus(id, status);
}
~~~

If the method returns `false` normally, `condition` is not satisfied so it does not evict; without `condition`, it would still evict by default. If the method throws an exception, the post-invocation operation does not execute.

When a method returns `Optional<T>`, `#result` in Spring Cache's supported context references the inner element or `null` if `Optional.empty()`. Null checks are needed when an expression depends on the result. It is usually safer to compute keys from stable inputs and use `#result` to decide the condition:

~~~java
@CacheEvict(
    cacheNames = "products",
    key = "#p0",
    condition = "#result != null",
    beforeInvocation = false
)
public Optional<Product> tryUpdate(long id, String value) {
    return repository.tryUpdate(id, value);
}
~~~

This is a snippet assuming the method returns `Optional<Product>`. Do not assume every custom result wrapper is unwrapped like `Optional`.

With `beforeInvocation=true`, do not use `#result` in `key`/`condition`: the method has no result yet at eviction time.

## 7. allEntries=true: clearing the entire cache after success

If a batch modifies many keys and it is difficult to determine all affected keys:

~~~java
@CacheEvict(cacheNames = "catalog",
            allEntries = true,
            beforeInvocation = false)
public void rebuildCatalog() {
    repository.rebuild();
}
~~~

After `rebuildCatalog()` returns normally, Spring requests clearing **the entire `catalog` cache**. If the method throws an exception, the post-invocation clear operation does not run.

**Do not declare `key` when `allEntries=true`**. These are two mutually exclusive mechanisms: evicting one entry by key versus clearing the entire cache region. With multi-tenant or multi-node caches, a full clear can trigger a cache stampede and increase database hits. Choose it only when truly needed.

For multiple caches with different keys, `@Caching(evict={...})` can declare them separately, though multiple operations do not form a distributed transaction across cache providers. When one provider fails, partial invalidation can occur.

## 8. Runnable example with Java 17, Maven, and Spring Framework

This example demonstrates three branches: first read causes a cache miss, an update throwing an exception keeps the old entry, and a successful update evicts the entry so the next read loads fresh data. It uses `ConcurrentMapCacheManager` and an in-memory store to eliminate real database dependencies.

**File `pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>evict-after-success</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.18</version>
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

**File `src/main/java/demo/EvictAfterSuccessDemo.java`**

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class EvictAfterSuccessDemo {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }

    @Bean
    Store store() {
        return new Store();
    }

    @Bean
    ProductService productService(Store store) {
        return new ProductService(store);
    }

    public static class Store {
        private final Map<Long, String> values =
                new ConcurrentHashMap<>(Map.of(7L, "v1"));

        public String get(long id) {
            return values.get(id);
        }

        public void put(long id, String value) {
            values.put(id, value);
        }
    }

    public static class ProductService {
        private final Store store;
        private int loads;

        public ProductService(Store store) {
            this.store = store;
        }

        @Cacheable(cacheNames = "products", key = "#p0")
        public String find(long id) {
            System.out.println("read source #" + (++loads));
            return store.get(id);
        }

        @CacheEvict(
            cacheNames = "products",
            key = "#p0",
            beforeInvocation = false
        )
        public void update(long id, String value, boolean fail) {
            System.out.println("update begin: " + value);
            if (fail) {
                throw new IllegalStateException("update rejected");
            }
            store.put(id, value);
            System.out.println("update stored: " + value);
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                EvictAfterSuccessDemo.class)) {
            ProductService service = context.getBean(ProductService.class);

            System.out.println("first = " + service.find(7));
            System.out.println("cached = " + service.find(7));

            try {
                service.update(7, "v2", true);
            } catch (IllegalStateException ex) {
                System.out.println("failed = " + ex.getMessage());
            }
            System.out.println("after failure = " + service.find(7));

            service.update(7, "v2", false);
            System.out.println("after success = " + service.find(7));
            System.out.println("again = " + service.find(7));
        }
    }
}
~~~

**Command to run** from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.EvictAfterSuccessDemo
~~~

**Output printed by the program in exact order**, omitting Maven/framework logs:

~~~text
read source #1
first = v1
cached = v1
update begin: v2
failed = update rejected
after failure = v1
update begin: v2
update stored: v2
read source #2
after success = v2
again = v2
~~~

Explanation:

1. `find(7)` misses the first time, prints `read source #1`, and caches `v1`. The second call hits without calling `store`.
2. `update(7, "v2", true)` throws an exception **before** modifying `store`. Eviction does not run; the next `find(7)` still hits `v1`.
3. `update(7, "v2", false)` updates `store` to `v2` and returns normally; Spring evicts key `7`.
4. The next `find(7)` misses, prints `read source #2`, loads `v2`, and caches it. The subsequent read returns `v2` from the cache.

This is a standalone application run with Maven, obtaining the Spring bean from `ApplicationContext` so calls pass through the proxy. The simulated store **does not have transaction rollback** and the failure example intentionally occurs before the update; do not infer from this that every real application error automatically rolls back data.

## 9. Exceptions after data has already changed

With `beforeInvocation=false`, if the method throws an exception, Spring does not run the annotation's eviction. This can leave stale data if the source was already durably modified before the error:

~~~java
@CacheEvict(cacheNames = "products", key = "#p0",
            beforeInvocation = false)
public void updateAndNotify(long id, String name) {
    repository.update(id, name);  // may have already committed
    notifier.notify(id);          // may throw an exception
}
~~~

The snippet assumes repository/notifier exist. If the update already committed and then the notifier throws an error, the cache may still contain the old product. Real transaction rollback, outbox/event design, or independent invalidation is required when a mutation is already durable.

If the method **catches** the exception and then returns normally, eviction can still happen. Therefore, define policy on the final outcome seen by the proxy, not on whether "an error occurred deep inside".

## 10. after invocation does not automatically mean after commit

When combining `@Transactional` and `@CacheEvict`:

~~~java
@Transactional
@CacheEvict(cacheNames = "products", key = "#p0",
            beforeInvocation = false)
public void changePrice(long id, long newPrice) {
    repository.changePrice(id, newPrice);
}
~~~

This is a snippet requiring a real transaction manager and repository. Due to transaction advice/cache advice ordering and possible outer transactions, eviction may be requested **before DB commit**. If another reader misses right at that moment, it can read the old version and write it back to the cache; after commit, the cached entry remains stale. An outer transaction can also roll back **after** the annotated method has already returned.

If post-commit eviction is needed, consider `TransactionAwareCacheManagerProxy` or `TransactionAwareCacheDecorator`. When a Spring transaction is active, they can defer `put`, `evict`, and `clear` until **after-commit** of a successful transaction; if there is no active transaction, they execute immediately. APIs requiring immediate effect such as `evictIfPresent` are not deferred in the same way.

Test advisor ordering, transaction propagation, database commit, and the actual cache provider. Another option is publishing an event and handling invalidation in `@TransactionalEventListener(phase = AFTER_COMMIT)` or an outbox when synchronizing across multiple services.

**Remember:** `beforeInvocation=false` only guarantees timing relative to the invocation observed by caching advice; it does not automatically synchronize with database transactions.

## 11. When the cache provider fails during evict

If the business method has already returned but `Cache.evict` fails (timeout, network, permission, serializer), the default `SimpleCacheErrorHandler` may propagate the exception to the caller. The data source may have changed even though the API returned an error.

A `CacheErrorHandler` can be configured to ignore certain cache errors so business execution continues, but when eviction fails, the old entry can become stale. TTLs, metrics, alerts, and safe retry/invalidation strategies must be in place. Do not silently swallow eviction errors and claim the cache is always consistent.

Distinguish when debugging:

- **Target method error**: after-invocation eviction does not run.
- **SpEL/cache configuration evaluation error** after the method: fails to remove the right entry, may propagate to caller.
- **Cache provider error** during evict: method succeeded yet eviction failed, caller may receive an exception.

## 12. Async/reactive and fire-and-forget

Since Spring Framework 6.1, some cache operations support `CompletableFuture` return types and reactive publishers. With `@CacheEvict(beforeInvocation=false)`, eviction can be performed when **asynchronous processing completes**, rather than immediately when the method merely returns a future/publisher. With `Flux`, Spring can collect emitted values into a `List` to serve `#result` in appropriate contexts.

~~~java
@CacheEvict(cacheNames = "products", key = "#p0",
            beforeInvocation = false)
public CompletableFuture<Void> updateAsync(long id) {
    return asyncRepository.update(id);
}
~~~

The snippet above requires an asynchronous repository. Successful completion, exceptional completion, and the cache provider must be tested. If a method merely launches a background job and returns `void` immediately (*fire-and-forget*), "after invocation" can arrive before the job finishes. In that case, tie eviction to the actual completion/commit point, not just when the launcher method returns.

## 13. AOP proxy and self-invocation

In default proxy mode, the annotation only works when the call goes through the proxy:

~~~java
@Service
public class ProductService {
    public void batch(long id) {
        update(id); // self-invocation, may bypass caching advice
    }

    @CacheEvict(cacheNames = "products", key = "#p0")
    public void update(long id) {
        // update data
    }
}
~~~

This snippet needs a Spring `@Service` and real implementation. An internal call from `batch` to `update` via `this` is not intercepted by the proxy; even though `update` returns normally, the cache is not evicted by the annotation. The common fix is moving the annotated method to another bean, injecting it, and calling it through that bean.

Other cases to check: objects instantiated with `new`, missing `@EnableCaching`, beans in a different context, private/final methods incompatible with the proxy type, non-matching pointcuts, mismatched cache/key, and annotation combinations that cause the business method to be skipped. Separate `@Cacheable` queries and `@CacheEvict` commands into clear methods.

## 14. Testing and diagnostics

A properly scoped test suite should prove:

1. Calling `@Cacheable` twice: first call misses, second call hits.
2. Calling a command annotated with `@CacheEvict(beforeInvocation=false)` successfully: next read misses and loads the new value.
3. Command throws an exception before changing the source: cache still hits the old value.
4. Method returns `false` without throwing an exception: default eviction still occurs.
5. Adding `condition="#result == true"`: a `false` result does not evict.
6. Catching an exception and returning normally: eviction can still happen.
7. Two different keys: evicting key A does not delete key B.
8. `allEntries=true`: successful command clears the entire cache; failing command does not clear.
9. Transaction rollback/commit: verify eviction and commit ordering with a real transaction.
10. Concurrent readers and multiple nodes: test stale-cache races between update, commit, and eviction.
11. Cache backend failure: verify `CacheErrorHandler` and the business update outcome.
12. Async completion, proxy boundaries, and self-invocation: test with a real Spring context.

When testing caching, obtain the service from `ApplicationContext` instead of `new`. Using a business-method execution counter and checking cached values helps distinguish hits from misses. For cache providers with deferred eviction, wait for or observe the exact moment the backend actually removes the entry.

## 15. Common misconceptions

- **"`beforeInvocation=false` means evict after DB commit."** False; invocation timing and commit are two distinct points.
- **"If the method returns false, Spring won't evict."** False if there is no `condition`.
- **"If there is an exception, the database definitely didn't change."** False for already-committed side effects or non-transactional resources.
- **"`@CacheEvict` always creates a new cache value."** False; it invalidates, whereas `@CachePut` is used to write a new result.
- **"`@CacheEvict` cannot be used with void."** False; void methods are very common.
- **"`allEntries=true` combined with key will evict a few entries."** False; full-region eviction is a separate mode.
- **"`beforeInvocation=true` is always safer."** False; evicting before the update can cause readers to reload stale data.
- **"Providers always physically delete immediately."** Not necessarily; transaction-aware/deferred eviction exists.
- **"Self-calling a method in the same bean still gets cache advice."** Incorrect in default proxy mode.
- **"Ignoring cache errors has no effect on consistency."** False; stale cache entries can persist until TTL or the next invalidation.

## 16. Official documentation

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@CacheEvict`, `beforeInvocation`, `condition`, `allEntries`, `#result`, async/reactive.
- [Spring Framework — CacheEvict Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CacheEvict.html): annotation contract and defaults.
- [Spring Framework — CacheAspectSupport Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/CacheAspectSupport.html): handling cache operations per invocation.
- [Spring Framework — TransactionAwareCacheDecorator Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html): deferring put/evict/clear to after-commit in supporting transactions.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction boundaries and rollback.

**Takeaway:** `@CacheEvict(beforeInvocation=false)` requests eviction after the target method completes normally; an exception escaping the method prevents after-invocation eviction. Achieving consistent caching requires the right cache/key, conditions, side-effect handling, transaction commit alignment, and awareness of backend behavior.