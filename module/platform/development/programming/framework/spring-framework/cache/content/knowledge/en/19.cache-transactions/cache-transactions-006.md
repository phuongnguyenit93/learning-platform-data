# Cache Advice Ordering vs. Transaction Advice in Spring Framework

## 1. Why Does Advice Ordering Matter?

A service method can carry both `@Cacheable`, `@CachePut`, or `@CacheEvict` and `@Transactional`. When an application enables Spring Cache and Spring Transaction Management, both mechanisms can create **AOP advice** wrapping the same call through a Spring proxy.

Example:

```java
@Transactional
@CacheEvict(cacheNames = "products", key = "#p0")
public void updateProduct(String productId) {
    repository.update(productId);
}
```

This is an **illustrative method**, not a standalone Java program. There are two completely different moments when cache eviction can occur:
- **After the transaction advice has committed**: the cache is evicted once the data-source change has been finalized by the transaction advice.
- **Before the transaction advice commits**: the cache is evicted when the method returns while the transaction is still uncommitted. A concurrent request can miss the cache, read old DB data, and write it back to the cache; if the commit later fails, the cache has also been cleared unnecessarily.

**Core point:** annotation ordering on a method is not a reliable mechanism for ordering cache advice and transaction advice. Execution order is governed by the AOP advisor infrastructure, `order` configuration, and actual proxy/interceptor classes.

Lesson objectives:
1. Understand `@EnableCaching(order = ...)` and `@EnableTransactionManagement(order = ...)`.
2. Recognize the two nesting patterns: **Cache outside / Transaction inside** and **Transaction outside / Cache inside**.
3. Predict cache hit, cache miss, cache put, cache evict, commit, and rollback under each ordering.
4. Distinguish AOP ordering from post-commit cache synchronization via `TransactionAwareCacheDecorator`.
5. Run a Java 17+ example with two order configurations and a tracing transaction manager, then verify stdout.
6. Design tests with real transactions, concurrent requests, outer transactions, and cache backends.

## 2. Recap: AOP Advices Execute in a Nested Chain

An interceptor chain takes the form:

```text
Client
  -> Advice A (outer)
      -> Advice B (inner)
          -> target service method
      <- Advice B exits
  <- Advice A exits
Client receives result
```

In Spring AOP, **a smaller order value means higher precedence**: an advice with order 100 sits **outside** an advice with order 200. It runs earlier on the way in and later on the way out. Nesting determines when cache put/evict and transaction commit occur relative to each other.

Distinguish:
- **Advice order**: ordering within the proxy/interceptor chain.
- **Transaction propagation**: `REQUIRED`, `REQUIRES_NEW`, etc., deciding whether a transaction actually starts or joins an existing one.
- **When the backend writes/deletes cache**: the cache implementation may write/delete immediately or defer via a transaction-aware decorator.

These are three independent concerns; changing `order` does not turn the cache and database into a shared ACID transaction.

### 2.1. Two Places to Configure Order

```java
@Configuration
@EnableCaching(order = 100)
@EnableTransactionManagement(order = 200)
class CacheOutsideConfig {
    // Cache advisor has higher precedence -> sits on the outside.
}
```

Conversely:

```java
@Configuration
@EnableCaching(order = 200)
@EnableTransactionManagement(order = 100)
class TransactionOutsideConfig {
    // Transaction advisor has higher precedence -> sits on the outside.
}
```

These are **two illustrative configuration snippets**; choose one per `ApplicationContext`. Section 5 includes a runnable version with two separate contexts.

According to Spring documentation, both `@EnableCaching.order` and `@EnableTransactionManagement.order` default to `Ordered.LOWEST_PRECEDENCE`. When they share the same precedence without additional rules, **do not rely on whatever order happens to be observed**. Set two explicit, distinct values when business requirements depend on advice ordering.

`@Order` on the service class or placing `@Transactional` above `@CacheEvict` in source code **does not replace** configuring the order of the respective infrastructure advisors.

## 3. Case A: Cache Advice OUTSIDE Transaction Advice

Setup:

```java
@EnableCaching(order = 100)
@EnableTransactionManagement(order = 200)
```

Logical flow of `@Cacheable` on a **cache miss**:

```text
Client
  CacheInterceptor (outer): lookup key -> MISS
    TransactionInterceptor (inner): begin/join transaction
      Service method: read DB or compute result
    TransactionInterceptor: commit/complete transaction scope
  CacheInterceptor: put value into cache
Client receives result
```

If the target genuinely opens a new transaction and commits successfully before returning to the cache advice, the cache put normally runs **after commit** (on a plain, non-deferred cache).

With `@CacheEvict(beforeInvocation=false)` (default):

```text
Cache advice
  Transaction advice: begin
    target: update DB
  Transaction advice: commit
Cache advice: evict key
```

A commit failure happens before the cache advice performs post-invocation handling; because the exception propagates out of the transaction advice, the after-success cache operation usually **does not execute**.

### 3.1. What About on a Cache HIT?

With `@Cacheable`, the outer cache checks the key **before entering the transaction advice**. On a hit:

```text
Cache advice: lookup -> HIT -> return cached value
Transaction advice: NOT INVOKED
Target method: NOT INVOKED
```

This avoids opening an unnecessary transaction for a cache-hit read. However, it also means **any logic triggered solely by the transaction advice will not run** on that hit. Do not cache a method where every call must execute business logic or non-skippable security checks/side effects.

### 3.2. Not a System-Wide After-Commit Guarantee

If the annotated method joins an **existing outer transaction** (`Propagation.REQUIRED`), the inner method's transaction advice may only complete its **participating scope** without committing the root transaction. The cache advice wrapping that method can still put/evict **before the larger transaction commits**.

Thus the claim "cache outer = always after every database commit" is **false**. You must inspect which real transaction sits on the call stack, whether `REQUIRES_NEW` is used, whether synchronization is active, and when the cache backend processes puts/evicts.

## 4. Case B: Transaction Advice OUTSIDE Cache Advice

Setup:

```java
@EnableCaching(order = 200)
@EnableTransactionManagement(order = 100)
```

Flow of `@Cacheable` on a **cache miss**:

```text
Client
  Transaction advice (outer): begin/join transaction
    Cache advice (inner): lookup key -> MISS
      target: read DB or compute result
    Cache advice: put value into cache
  Transaction advice: commit
Client receives result
```

With a plain cache, the cache put can happen **before the DB commits successfully**. If the commit subsequently fails, the cache may already contain data from an uncommitted transaction.

With `@CacheEvict(beforeInvocation=false)`:

```text
Transaction advice: begin
  Cache advice
    target: update DB
  Cache advice: evict key
Transaction advice: commit
```

Dangerous situation: another request sees a cache miss between eviction and commit, queries an older version of the DB, and writes the old value back into the cache. When the transaction commits, the cache still risks being stale.

### 4.1. On a Cache HIT

The transaction advice sits on the outside and **already ran before the cache lookup**. Even though a cache hit skips the target method, the transaction advice may still open or join a transaction:

```text
Transaction advice: begin/join
  Cache advice: HIT -> return cached value
Transaction advice: commit/complete
```

This is a performance and semantic difference from cache-outer. With a real transaction manager, a cache hit may still pay transaction overhead; depending on implementation and propagation, "begin" here does not necessarily open a brand-new physical DB transaction.

### 4.2. What If the Method Throws an Exception?

With default `@CacheEvict` (`beforeInvocation=false`), an exception from the target prevents after-success eviction from running, regardless of whether the outer advisor is cache or transaction. The transaction advice typically rolls back on unchecked exceptions per default `@Transactional` policy.

If `beforeInvocation=true`, eviction is requested **before the target runs**, even if the target later fails. Without a transaction-aware decorator, the entry may already be deleted even though the transaction rolls back. With a transaction-aware cache, the actual result still depends on whether eviction is deferred until after-commit.

**Note:** checked exceptions do not roll back automatically by default in many Spring versions/configurations. Check `rollbackFor`/`noRollbackFor` and application-wide rules rather than claiming "every exception rolls back".

## 5. Complete Java 17+ Example: Observing Both Orders on the Same Service

To isolate **AOP ordering** from database details, the example uses a minimal `PlatformTransactionManager` that only logs `TX_BEGIN`, `TX_COMMIT`, and `TX_ROLLBACK` events. It **does not perform real DB transactions**. A `ConcurrentMapCache` is extended to log `CACHE_GET`, `CACHE_PUT`, and `CACHE_EVICT` events; the service method logs `TARGET_LOAD` or `TARGET_CHANGE`.

This verifies exact interceptor ordering without depending on JDBC configuration, and does not demonstrate ACID guarantees. Two separate Spring `ApplicationContext` instances are created so the two experiments do not share a cache.

### 5.1. Project Structure and Gradle

```text
cache-tx-advice-order/
  settings.gradle
  build.gradle
  src/main/java/demo/advice/AdviceOrderDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'cache-tx-advice-order'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'org.springframework:spring-tx'
}

application {
    mainClass = 'demo.advice.AdviceOrderDemo'
}
```

### 5.2. Complete Program

`src/main/java/demo/advice/AdviceOrderDemo.java`:

```java
package demo.advice;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.cache.support.SimpleCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.SimpleTransactionStatus;

public class AdviceOrderDemo {

    // Each context has its own event log.
    public static class Events {
        private final List<String> entries = new ArrayList<>();

        public void add(String event) {
            entries.add(event);
        }

        public String drain() {
            String trace = String.join(" > ", entries);
            entries.clear();
            return trace;
        }
    }

    // This manager only simulates begin/commit/rollback to measure AOP ordering.
    // It opens no connections and provides no real database transactions.
    public static class TraceTransactionManager
            implements PlatformTransactionManager {

        private final Events events;

        public TraceTransactionManager(Events events) {
            this.events = events;
        }

        @Override
        public TransactionStatus getTransaction(TransactionDefinition definition) {
            events.add("TX_BEGIN");
            return new SimpleTransactionStatus();
        }

        @Override
        public void commit(TransactionStatus status) {
            events.add("TX_COMMIT");
        }

        @Override
        public void rollback(TransactionStatus status) {
            events.add("TX_ROLLBACK");
        }
    }

    public static class TraceCache extends ConcurrentMapCache {
        private final Events events;

        public TraceCache(Events events) {
            super("items", true);
            this.events = events;
        }

        @Override
        public ValueWrapper get(Object key) {
            events.add("CACHE_GET(" + key + ")");
            return super.get(key);
        }

        @Override
        public void put(Object key, Object value) {
            events.add("CACHE_PUT(" + key + ")");
            super.put(key, value);
        }

        @Override
        public void evict(Object key) {
            events.add("CACHE_EVICT(" + key + ")");
            super.evict(key);
        }
    }

    public static class ItemService {
        private final Events events;
        private final AtomicInteger loadCount = new AtomicInteger();

        public ItemService(Events events) {
            this.events = events;
        }

        @Transactional
        @Cacheable(cacheNames = "items", key = "#p0")
        public String load(String key) {
            events.add("TARGET_LOAD(" + key + ")");
            return key + "-v" + loadCount.incrementAndGet();
        }

        @Transactional
        @CacheEvict(cacheNames = "items", key = "#p0")
        public void change(String key) {
            events.add("TARGET_CHANGE(" + key + ")");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class SharedBeans {
        @Bean
        Events events() {
            return new Events();
        }

        @Bean
        PlatformTransactionManager transactionManager(Events events) {
            return new TraceTransactionManager(events);
        }

        @Bean
        CacheManager cacheManager(Events events) {
            SimpleCacheManager manager = new SimpleCacheManager();
            manager.setCaches(List.of(new TraceCache(events)));
            return manager;
        }

        @Bean
        ItemService itemService(Events events) {
            return new ItemService(events);
        }
    }

    // Smaller cache order: Cache advice sits outside Transaction advice.
    @Configuration(proxyBeanMethods = false)
    @EnableCaching(order = 100)
    @EnableTransactionManagement(order = 200)
    @Import(SharedBeans.class)
    public static class CacheOuterConfig {
    }

    // Smaller transaction order: Transaction advice sits outside Cache advice.
    @Configuration(proxyBeanMethods = false)
    @EnableCaching(order = 200)
    @EnableTransactionManagement(order = 100)
    @Import(SharedBeans.class)
    public static class TransactionOuterConfig {
    }

    private static void runCase(String label, Class<?> config) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(config)) {
            ItemService service = context.getBean(ItemService.class);
            Events events = context.getBean(Events.class);

            System.out.println("== " + label + " ==");
            System.out.println("first=" + service.load("SKU-1"));
            System.out.println("missTrace=" + events.drain());

            System.out.println("second=" + service.load("SKU-1"));
            System.out.println("hitTrace=" + events.drain());

            service.change("SKU-1");
            System.out.println("evictTrace=" + events.drain());
        }
    }

    public static void main(String[] args) {
        runCase("CACHE_OUTER", CacheOuterConfig.class);
        runCase("TX_OUTER", TransactionOuterConfig.class);
    }
}
```

Run from the project directory with JDK 17+ and a compatible Gradle version:

```bash
gradle run --quiet
```

If you have the Gradle Wrapper, use `./gradlew run --quiet` (Windows: `gradlew.bat run --quiet`).

**Expected output from the program**, excluding startup/build logs:

```text
== CACHE_OUTER ==
first=SKU-1-v1
missTrace=CACHE_GET(SKU-1) > TX_BEGIN > TARGET_LOAD(SKU-1) > TX_COMMIT > CACHE_PUT(SKU-1)
second=SKU-1-v1
hitTrace=CACHE_GET(SKU-1)
evictTrace=TX_BEGIN > TARGET_CHANGE(SKU-1) > TX_COMMIT > CACHE_EVICT(SKU-1)
== TX_OUTER ==
first=SKU-1-v1
missTrace=TX_BEGIN > CACHE_GET(SKU-1) > TARGET_LOAD(SKU-1) > CACHE_PUT(SKU-1) > TX_COMMIT
second=SKU-1-v1
hitTrace=TX_BEGIN > CACHE_GET(SKU-1) > TX_COMMIT
evictTrace=TX_BEGIN > TARGET_CHANGE(SKU-1) > CACHE_EVICT(SKU-1) > TX_COMMIT
```

### 5.3. How to Read the Output

**CASE CACHE_OUTER**:
- On a cache miss, `CACHE_GET` precedes `TX_BEGIN`; `CACHE_PUT` follows `TX_COMMIT`.
- On a cache hit, the trace contains only `CACHE_GET`. Cache advice returns the value immediately; transaction advice is never entered.
- `CACHE_EVICT` runs after `TX_COMMIT` because default `@CacheEvict` runs after the method and sits outside the transaction advice.

**CASE TX_OUTER**:
- `TX_BEGIN` precedes `CACHE_GET`.
- `CACHE_PUT` and `CACHE_EVICT` happen before `TX_COMMIT` on a non-transaction-aware in-memory cache.
- On a cache hit, the transaction advice is still entered, even though the method body does not execute.

**Important limitation:** `TraceTransactionManager` only logs events and returns status; it does not work with JDBC, ORM, or real transaction synchronization. Thus the output is an **illustration of advice ordering**, not proof of DB rollback behavior or post-commit cache consistency in a production project.

## 6. Combining With a Transaction-Aware Cache

AOP ordering only tells you **when Spring invokes** `put/evict/clear`. If you need to synchronize cache writes/evictions with a Spring-managed transaction, you can use `TransactionAwareCacheManagerProxy` or a transaction-aware compatible cache implementation/manager.

Illustrative configuration example:

```java
@Bean
CacheManager cacheManager() {
    CacheManager underlying =
            new ConcurrentMapCacheManager("items");
    return new TransactionAwareCacheManagerProxy(underlying);
}
```

Required imports:
- `org.springframework.cache.CacheManager`;
- `org.springframework.cache.concurrent.ConcurrentMapCacheManager`;
- `org.springframework.cache.transaction.TransactionAwareCacheManagerProxy`.

This snippet only illustrates the bean; it is not part of the tracing example in Section 5.

Per Spring, `TransactionAwareCacheDecorator` synchronizes **`put`, `evict`, and `clear`** operations with the current transaction via `TransactionSynchronizationManager`. When a suitable Spring-managed transaction is active, the actual action can be **deferred until after-commit of a successful transaction**. Without an active transaction, the action executes immediately as usual.

Consequences:
- If the outer transaction calls `cache.evict(...)` before commit, the decorator can **register the deletion request** rather than deleting from the native cache right away.
- When the transaction commits successfully, the deletion executes in the after-commit phase.
- If the transaction rolls back, the deferred operation is not executed as an after-commit action of a successful transaction.
- If an outer cache advice calls put/evict after the entire transaction has finished, the decorator no longer has a running transaction to defer against, so it may execute immediately.

**Crucial:** operations requiring immediate results such as `putIfAbsent` or `evictIfPresent` cannot be deferred like `put/evict/clear`. With `@Cacheable(sync=true)`, Spring may use the `Cache.get(key, Callable)` path instead of a standard put; check the provider/decorator properties rather than assuming everything is deferred.

### 6.1. Transaction-Aware Does Not Mean Atomic Between DB and Cache

Even when cache eviction runs in after-commit, the database may have already committed when the cache backend errors. The Spring cache abstraction does not turn those two resources into a distributed two-phase commit.

For business flows that cannot lose invalidations:
- Design retries or a durable outbox/event mechanism.
- Include versions in cache keys so older loaders cannot pollute newer versions.
- Monitor backend failures and have appropriate fallbacks.
- Check the possibility of stale results being written back by a request that missed **before eviction**.

Transaction-aware helps align timing, not guarantee that every reader across every node sees the new state instantaneously.

## 7. Special Case: Outer Transactions and Propagation

Consider two services:

```java
@Service
public class OrderService {
    private final ProductService products;

    public OrderService(ProductService products) {
        this.products = products;
    }

    @Transactional
    public void processOrder(String id) {
        products.updateProduct(id);
        // Other steps remain; the overall transaction has not committed yet.
    }
}
```

This illustrative snippet depends on `ProductService`. Suppose `products.updateProduct` also uses default `@Transactional` (`REQUIRED`), and cache advice sits outside the child method's transaction advice. The child method can finish while `processOrder`'s **overall** transaction is still open. In that case, the child method's cache eviction can still execute before the outer transaction commits.

Simply changing `@EnableCaching(order=100)` does not completely solve this. You must determine:
- Where is the transaction opened, and which advisors wrap the top-level call?
- Does the child method join the existing transaction or open a separate one (`REQUIRES_NEW`)?
- Should eviction happen immediately or after which transaction commits?
- Does the cache manager have a transaction-aware decorator?
- Are calls passing through Spring proxies for both the outer and inner services?

One design direction is emitting a business event and performing invalidation in the after-commit phase, such as `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` for synchronous transaction-managed events. When high durability across services/processes is required, use an outbox/queue and retries; in-memory after-commit callbacks do not replace durable messaging.

## 8. What Happens When Exceptions or Commit Failures Occur

### 8.1. Method Throws an Exception

Illustrative example:

```java
@Transactional
@CacheEvict(cacheNames = "items", key = "#p0")
public void update(String id) {
    repository.change(id);
    throw new IllegalStateException("failed");
}
```

With default `beforeInvocation=false` and an unchecked exception:
- Spring transaction advice normally rolls back under default rules unless configured otherwise.
- After-success cache eviction **does not run** because the invocation ended in an exception.
- This holds under both standard advice nestings, though out-of-transaction side effects, other advisors, and provider-specific behaviors must be analyzed separately.

### 8.2. Method Completes Yet Commit Fails

Example with transaction-outer configuration:

```text
TX_BEGIN
  CACHE_MISS
  TARGET_METHOD_RETURNS
  CACHE_PUT
TX_COMMIT_FAIL
```

If the cache is written immediately and transaction commit fails, the cache can hold a result not reflected in the committed DB. This is why a successful method return cannot be taken as sufficient to write a DB-consistent cache entry.

With cache-outer and transaction advice inside (new transaction):
```text
CACHE_MISS
  TX_BEGIN
  TARGET_METHOD_RETURNS
  TX_COMMIT_FAIL
CACHE_PUT does not run because inner advice threw an exception
```

Yet remember the outer-transaction participation exception from Section 7: cache outside a child method can still write before the root transaction commits. A transaction-aware decorator and proper transaction boundaries are usually more reliable than merely flipping order.

### 8.3. `beforeInvocation=true` Changes Eviction Timing

```java
@Transactional
@CacheEvict(
    cacheNames = "items",
    key = "#p0",
    beforeInvocation = true
)
public void delete(String id) {
    repository.delete(id);
}
```

In a cache-outer configuration, pre-invocation eviction can occur **before transaction advice even begins**. In a transaction-outer configuration, eviction is requested after the transaction begins but before the target runs. If a transaction-aware decorator is present, the eviction request may be deferred, yielding semantics different from an immediate native operation.

Only use `beforeInvocation=true` if business requirements accept the cache being cleared even if the method later fails, or if transaction-aware behavior has been verified. Do not treat it as a "safer" default option.

## 9. Checklist for Configuring and Verifying Ordering

1. **Check Spring version** and mode of both annotations: default proxy mode or AspectJ weaving; this lesson focuses on proxy mode.
2. **Explicitly specify `order`** on `@EnableCaching` and `@EnableTransactionManagement` when stable ordering is required. Smaller number -> outer advice.
3. **Verify ordering via logs/tests**; do not infer from source annotation order or bean declaration order.
4. **Test cache miss:** capture trace of Cache GET, transaction begin, target, cache PUT, commit.
5. **Test cache hit:** confirm whether a transaction is opened as desired, and whether skipping the method is allowed.
6. **Test post-update eviction:** verify when `@CacheEvict` runs relative to commit.
7. **Test exceptions:** test checked/unchecked exceptions and rollback rules; inspect cache entries before/after.
8. **Test commit failures:** intentionally induce transaction rollback/commit failure against a real DB; verify the entry does not hold uncommitted data.
9. **Test outer transactions:** a child `REQUIRED` method can join a larger transaction; do not assume "inner advice finished = physical commit".
10. **Test transaction-aware cache:** confirm the cache delegate actually only puts/evicts/clears after-commit when transaction synchronization is active.
11. **Test concurrency:** one request misses while another updates/evicts; check for stale puts.
12. **Test multiple instances/backends:** understand provider-specific propagation, consistency, null policies, and transaction behavior.
13. **Test proxy/self-invocation:** `this.update(...)` in the same class can bypass both cache and transaction advice in proxy mode; invoke the service through a Spring bean.
14. **Monitor metrics:** cache hits/misses, real transaction counts, rollbacks, cache backend errors, and queue/outbox health if used.

### 9.1. Quick Debugging Questions

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Cache hit still opens a transaction | Transaction advice is outside cache advice | Compare orders, trace actual advice |
| Cache hit does not open a transaction | Cache advice is outside and returns before reaching transaction | Check if any mandatory business step requires a transaction |
| Cache evicts before DB commit | Transaction outer, plain cache, no deferral | Set order intentionally or use transaction-aware |
| Set cache outer yet still evicts before commit | Method joins an uncommitted outer transaction | Inspect propagation and transaction boundaries |
| Cache holds uncommitted data | Cache put ran before failed commit | Test rollback/commit failure, use after-commit policy |
| Evict does not run when method throws | `@CacheEvict` defaults to after-success only | Verify `beforeInvocation` and rules |
| Evict runs even when method fails | `beforeInvocation=true` or cache operation outside transaction | Revisit intent and decorator |
| Order configuration has no effect | Wrong context, wrong annotation mode, self-invocation, or another advisor | Check proxy chain, context, and advisor ordering |

## 10. Mental Model for Choosing an Approach

**If the goal is optimizing read performance** and cache hits need no transaction: placing the cache advisor on the outside often makes sense. Still, consider this only for **pure-read** methods where the cache key includes all authorization/tenant dimensions and no mandatory per-call side effects exist.

**If the goal is tying cache updates to data commits**: look at transaction-aware caches, after-commit events, and retry/durability guarantees rather than relying solely on annotation ordering.

**If the system has large transactions or nested calls**: invalidation decisions must be anchored on **the transaction that actually commits**, not merely the child method completing. Advice ordering is a factor to control, not the complete consistency solution.

**If multiple other advisors exist** such as retry/security/async: read the real chain. A `@Retryable` outside a transaction can start a new transaction per attempt; `@Async` switching threads can change transaction context. Do not apply a two-advisor diagram verbatim to a multi-layered chain without verifying.

## 11. Self-Check Questions

**Q1.** Cache advisor order 100, transaction advisor order 200. Which advisor is on the outside?

**Answer:** Cache advisor, because a smaller order number has higher precedence.

**Q2.** With `@Cacheable` cache-outer, does a cache hit enter the transaction advisor?

**Answer:** No, if `CacheInterceptor` returns the cached result without invoking the rest of the inner chain.

**Q3.** With transaction-outer and a plain cache, when does `@CacheEvict(beforeInvocation=false)` occur?

**Answer:** After the target method succeeds, yet potentially **before the transaction advice commits**.

**Q4.** If both enabling annotations leave order at default, should you rely on the current observed ordering?

**Answer:** No. Both default to `LOWEST_PRECEDENCE`; if order matters, configure distinct explicit order values.

**Q5.** Does cache-outer guarantee eviction is always after database commit?

**Answer:** No; when the method joins an active outer transaction, completing the inner transaction advice does not necessarily mean physical commit of the root transaction.

**Q6.** Which operations does `TransactionAwareCacheDecorator` defer?

**Answer:** Primarily `put`, `evict`, and `clear` until after-commit when a suitable Spring-managed transaction is active; APIs requiring immediate effect like `putIfAbsent` and `evictIfPresent` are not similarly deferred.

**Q7.** Why can writing to the cache before commit cause bugs?

**Answer:** The transaction may fail at commit, or another request may read old DB data during the eviction–commit gap and load a stale entry.

## 12. Takeaways

- **Cache advice and transaction advice are two AOP interceptors** that can wrap each other in either order; the order determines when cache lookup/put/evict runs relative to transaction begin/commit.
- `@EnableCaching(order=...)` and `@EnableTransactionManagement(order=...)` are the two places to set order. **Smaller number -> outer advice -> runs first on entry, last on exit**.
- **Cache outer:** hits can avoid transactions; misses/after-invocation evictions normally run after inner transaction advice.
- **Transaction outer:** hits still enter transaction advice; cache put/evict normally run before outer commit if the cache is not transaction-aware.
- **An outer transaction can shift the entire physical commit boundary.** Do not infer from a child method returning successfully.
- `TransactionAwareCacheDecorator` helps defer `put/evict/clear` until appropriate after-commit, but is not a distributed transaction or automatic cure for all race conditions.
- **Always test with a real transaction manager/database/cache provider** when consistency matters to the business.

### Official References

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Advice Ordering](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html)
- [Spring Framework — @EnableCaching Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/annotation/EnableCaching.html)
- [Spring Framework — @EnableTransactionManagement Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/transaction/annotation/EnableTransactionManagement.html)
- [Spring Framework — TransactionAwareCacheDecorator Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html)
- [Spring Framework — TransactionAwareCacheManagerProxy Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
