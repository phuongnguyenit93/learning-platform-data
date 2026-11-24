# TransactionAwareCacheManagerProxy: Synchronizing Cache Operations With Transaction Commit

## 1. Objectives and Use Cases

This lesson belongs to the **Transactions** group of Spring Framework Cache. After this lesson, you will:

- Understand why database updates and cache changes do not automatically happen at the same moment.
- Explain the roles of `org.springframework.cache.transaction.TransactionAwareCacheManagerProxy` and `TransactionAwareCacheDecorator`.
- Configure a target `CacheManager` and expose a transaction-aware wrapped `CacheManager` to the application.
- Know precisely which operations (**`put`, `evict`, `clear` are deferred until after commit**) and which operations requiring immediate effect **are not deferred**.
- Distinguish commit, rollback, no transaction, concurrent requests, and transaction callbacks from true atomicity.
- Run a **Spring Boot + H2 + Java 17+** example demonstrating database data, stale cache inside a transaction, post-commit eviction, and skipped cache updates on rollback.

**Key takeaway:** `TransactionAwareCacheManagerProxy` does not turn the cache into part of a database transaction. It **decorates cache regions** so that certain cache-mutating commands are **executed in a callback after the Spring transaction commits successfully**, instead of executing immediately when code invokes the command.

## 2. The Problem: Database Rolls Back While Cache Is Already Modified

Suppose an application caches product names:

~~~text
database["P1"] = "Original"
cache["P1"]    = "Original"
~~~

A business operation executes:

~~~java
@Transactional
public void renameProduct(String id, String newName) {
    repository.updateName(id, newName);
    cache.evict(id);
    performAnotherOperationThatMayFail();
}
~~~

This is **illustrative code** inside a service; `repository`, `cache`, and `performAnotherOperationThatMayFail` must be defined in a real application.

If `cache.evict(id)` takes effect immediately and the final step throws an exception, the database rolls back yet the cache has already been cleared. That typically causes unnecessary cache misses and reloads. Worse, a `cache.put(id, newName)` path executed **before commit** can leave a value **never committed by the database** in the cache after rollback.

A common race:

~~~text
T0: database = Old, cache = Old
T1: transaction A updates DB to New (uncommitted)
T2: A calls cache.put(key, New) if cache PUTs immediately
T3: request B reads cache → New (not yet committed data)
T4: A rolls back DB → Old
T5: cache still has New → wrong data
~~~

`TransactionAwareCacheManagerProxy` helps avoid **this class of consistency bugs**: when a `put` command goes through a decorated cache with active transaction synchronization, it waits for **`afterCommit`**. If the transaction rolls back, the `afterCommit` callback does not run, so the cache never receives the uncommitted value.

For `evict` and `clear`, deferral also prevents losing entries when the DB transaction does not succeed.

## 3. Structure of TransactionAwareCacheManagerProxy

`TransactionAwareCacheManagerProxy` is an implementation of the `CacheManager` interface. It **wraps an existing `CacheManager`**, rather than creating its own backend.

~~~text
Service / @Cacheable / @CacheEvict / Cache API
                     |
                     v
      TransactionAwareCacheManagerProxy
                     |
                getCache(name)
                     |
                     v
       TransactionAwareCacheDecorator
                     |
                     v
       Cache from target CacheManager
          (ConcurrentMapCache, ...)
                     |
                actual backend
~~~

When a cache named `products` is requested, the wrapper fetches the cache from the target manager and returns a `Cache` object wrapped by the transaction-aware decorator. Normal lookup operations are forwarded to the target cache; supported write/delete operations can be registered as callbacks with `TransactionSynchronizationManager`.

### Who Is Responsible for What?

| Component | Responsibility |
| --- | --- |
| `PlatformTransactionManager` | Manages the real transaction, commits/rolls back the database or corresponding resource |
| `TransactionSynchronizationManager` | Tracks synchronization in the current Spring transaction context and invokes lifecycle callbacks |
| `TransactionAwareCacheManagerProxy` | Wraps the target manager to expose transaction-aware caches |
| `TransactionAwareCacheDecorator` | Defers certain cache-mutating commands until after-commit |
| Underlying `CacheManager` | Determines whether a cache region exists, backend type, and per-region settings |
| Underlying `Cache`/provider | Executes reads, writes, evictions, TTL, serialization, capacity per its own policies |

**Do not confuse the two proxy layers:** A Spring AOP proxy can intercept `@Transactional` or `@Cacheable` calls on a service method. `TransactionAwareCacheManagerProxy`, by contrast, is **a proxy for `CacheManager`**; it does not require every method accessing the cache to be an AOP-advised service method, as long as operations go through the decorated `Cache` within a synchronized transaction.

## 4. Exact Behavior on Commit, Rollback, and Outside a Transaction

According to Spring's Javadoc, `TransactionAwareCacheDecorator` synchronizes the following operations with a Spring transaction:

| Cache API | Inside a transaction with synchronization | After commit | On rollback |
| --- | --- | --- | --- |
| `put(key, value)` | Schedules write; does not write to target cache immediately | Writes value to target cache | Does not execute scheduled put |
| `evict(key)` | Schedules entry removal | Removes entry from target cache | Does not execute scheduled evict |
| `clear()` | Schedules region clear | Clears entries in target cache | Does not execute scheduled clear |
| `get(key)`, `get(key, Class)` | Reads live cache; does not "read pending writes" | No separate action | No separate action |
| `putIfAbsent(key, value)` | Requires immediate effect; **not deferred** | Already applied before commit | May still remain in effect after rollback |
| `evictIfPresent(key)` | Requires immediate key removal; **not deferred** | Already applied before commit | Does not automatically restore entry |
| `invalidate()` | Requires immediate region invalidation; **not deferred** | Already applied before commit | Does not automatically restore region |

**Two easily overlooked points:**

1. **`put`/`evict`/`clear` are deferred only when suitable transaction synchronization is active.** Outside a transaction, they execute immediately like a regular cache. Simply writing `@Transactional` in source code when the call does not go through a Spring proxy is not enough to create a transaction.
2. **`get` has no guaranteed read-your-writes.** If inside a transaction you call `cache.put("P1","New")` and immediately call `cache.get("P1")`, you may still see `Old` (or `null` on a prior miss), because `New` has not yet been transferred to the target cache.

The APIs `putIfAbsent`, `evictIfPresent`, and `invalidate` are defined with the expectation of **immediate visibility**, so they cannot be deferred like `put`/`evict`/`clear`. Do not replace `evict` with `evictIfPresent` inside a transaction and assume rollback will undo the deletion.

### Memorable Timeline

~~~text
TX BEGINS
  |
  +-- update database in transaction
  |
  +-- decoratedCache.evict("P1")
  |       └── registers afterCommit callback; cache still holds Old
  |
  +-- reading raw cache may return Old
  |
  +-- DB COMMIT succeeds
          |
          +-- afterCommit callback executes evict("P1")
                   |
                   +-- next read → cache miss → loads new DB value
~~~

If the transaction rolls back, the `afterCommit` callback for eviction **does not run**, and the target cache retains the old entry in this sequential example.

## 5. Spring Boot Configuration: Wrapping an Existing `CacheManager`

Example with an in-memory cache:

~~~java
@Bean("rawCacheManager")
CacheManager rawCacheManager() {
    return new ConcurrentMapCacheManager("products");
}

@Bean("cacheManager")
@Primary
CacheManager cacheManager(
        @Qualifier("rawCacheManager") CacheManager raw) {
    return new TransactionAwareCacheManagerProxy(raw);
}
~~~

This is an **illustrative configuration snippet**: annotations and classes must be imported; see the complete Java file in Section 6. Meaning:

- `rawCacheManager` is the real provider/manager. It manages the `products` region and has no transaction-deferred behavior of its own.
- `cacheManager` is the bean exposed to most of the application. `@Primary` ensures that when injecting by the `CacheManager` interface without a qualifier, Spring picks the wrapper.
- `@Qualifier` on the configuration parameter prevents circular dependencies or accidentally injecting the wrapper into itself.
- From here on, use `manager.getCache("products")` from the **wrapper** to obtain decorated caches. If you inject `rawCacheManager` and write directly to it, you **bypass** the transaction-aware layer.
- For `@Cacheable`/`@CacheEvict` annotations, ensure the cache interceptor uses the decorated manager; when multiple `CacheManager`s exist, control selection via `@Primary` or specify the manager/configuration explicitly per application.

There is no need to swap the underlying provider for a special "transactional" cache. This mechanism operates at the Spring Cache abstraction layer; however, transaction synchronization limits must still be respected.

## 6. Runnable Example: Rollback Keeps Old Cache; Commit Evicts Cache

This example builds a **Spring Boot Java 17+** project using H2, JDBC, and Spring Cache; no Redis or Caffeine is required, making behavior easy to observe. All cache operations in the demo use the **direct API**. `TransactionTemplate` is used instead of `@Transactional` to make begin/commit/rollback boundaries explicit; the `afterCommit` mechanism used by the decorator is still standard Spring transaction infrastructure.

### 6.1. Dependencies

In a Spring Boot Gradle project with Java 17+ compatible plugins/versions, keep the existing build configuration and add:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    runtimeOnly 'com.h2database:h2'
}
~~~

`spring-boot-starter-jdbc` provides `JdbcTemplate` along with Spring's transaction infrastructure. H2 is an in-memory database supporting rollback. `spring-boot-starter-cache` provides the Spring Cache abstraction and `ConcurrentMapCacheManager`. Run the example via `bootRun` in the Spring Boot project; do not use bare `javac` since external libraries beyond the JDK are needed.

### 6.2. Create Table and Seed Data

Create `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE books (
    id VARCHAR(20) PRIMARY KEY,
    title VARCHAR(100) NOT NULL
);
~~~

Create `src/main/resources/data.sql`:

~~~sql
INSERT INTO books (id, title) VALUES ('B1', 'Original');
~~~

Spring Boot initializes the SQL scripts for the embedded H2 database before running `CommandLineRunner` (under appropriate default SQL init configuration).

### 6.3. One Complete Java Class

Create `src/main/java/example/txcache/TransactionAwareDemoApplication.java`:

~~~java
package example.txcache;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.transaction.TransactionAwareCacheManagerProxy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootApplication
public class TransactionAwareDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(TransactionAwareDemoApplication.class, args);
    }

    @Bean("rawCacheManager")
    CacheManager rawCacheManager() {
        return new ConcurrentMapCacheManager("books");
    }

    @Bean("cacheManager")
    @Primary
    CacheManager cacheManager(
            @Qualifier("rawCacheManager") CacheManager rawManager) {
        return new TransactionAwareCacheManagerProxy(rawManager);
    }

    @Bean
    CommandLineRunner demo(
            JdbcTemplate jdbc,
            PlatformTransactionManager txManager,
            @Qualifier("cacheManager") CacheManager exposed,
            @Qualifier("rawCacheManager") CacheManager rawManager) {

        return args -> {
            Cache cache = Objects.requireNonNull(
                    exposed.getCache("books"), "wrapped cache missing");
            Cache raw = Objects.requireNonNull(
                    rawManager.getCache("books"), "raw cache missing");

            AtomicInteger loads = new AtomicInteger();
            Supplier<String> read = () -> {
                String hit = cache.get("B1", String.class);
                if (hit != null) {
                    return hit;
                }
                String fromDb = jdbc.queryForObject(
                        "SELECT title FROM books WHERE id = ?",
                        String.class, "B1");
                System.out.println("DB_LOAD #" + loads.incrementAndGet());
                cache.put("B1", fromDb);
                return fromDb;
            };

            TransactionTemplate tx = new TransactionTemplate(txManager);

            // Outside transaction: put takes effect immediately.
            System.out.println("initial = " + read.get());
            System.out.println("cached = " + read.get());

            // Transaction #1: update DB then request evict,
            // but intentionally roll back to verify cache is not deleted.
            tx.executeWithoutResult(status -> {
                jdbc.update("UPDATE books SET title = ? WHERE id = ?",
                        "RolledBack", "B1");
                cache.evict("B1");
                System.out.println("rollback tx raw = " +
                        raw.get("B1", String.class));
                status.setRollbackOnly();
            });
            System.out.println("after rollback = " + read.get());

            // Transaction #2: commit DB, evict only after commit.
            tx.executeWithoutResult(status -> {
                jdbc.update("UPDATE books SET title = ? WHERE id = ?",
                        "Committed", "B1");
                cache.evict("B1");
                System.out.println("commit tx raw = " +
                        raw.get("B1", String.class));
            });
            System.out.println("after commit = " + read.get());
            System.out.println("hit after commit = " + read.get());

            // put is also deferred until afterCommit.
            tx.executeWithoutResult(status -> {
                cache.put("manual", "ready");
                System.out.println("during put raw = " +
                        raw.get("manual", String.class));
            });
            System.out.println("after put raw = " +
                    raw.get("manual", String.class));

            // put inside a rolling-back transaction is skipped.
            tx.executeWithoutResult(status -> {
                cache.put("rolled", "ghost");
                System.out.println("during rolled put raw = " +
                        raw.get("rolled", String.class));
                status.setRollbackOnly();
            });
            System.out.println("after rolled-back put = " +
                    raw.get("rolled", String.class));

            // No transaction: decorated cache puts immediately.
            cache.put("outside", "immediate");
            System.out.println("outside transaction = " +
                    raw.get("outside", String.class));
        };
    }
}
~~~

**Explanation of bean selection:**

- There are two `CacheManager`s: `rawCacheManager` is the real manager; `cacheManager` holds `TransactionAwareCacheManagerProxy` and is marked `@Primary`.
- The `cache` variable is obtained from the **wrapper**, so `put`/`evict` pass through `TransactionAwareCacheDecorator`. The `raw` variable is used solely to **observe the target cache** before deferred operations run.
- `TransactionTemplate` uses the `PlatformTransactionManager` configured by Spring Boot for the H2 `DataSource`. The `executeWithoutResult` callback participates in a synchronized transaction; at the end of the callback, the template commits or rolls back according to `status`.
- `Supplier<String> read` exists purely for the demo to provide an explicit read/put path. It reads `cache.get("B1", String.class)`, queries H2 on miss, and calls `cache.put(...)`. Under concurrent workloads, this check-then-act path has its own races; the example runs sequentially on purpose and should not be used as production cache loader code.
- The cache is a local `ConcurrentMapCache`. This is not an example of distributed transaction management and does not require `@EnableCaching`, because all cache operations in the program are invoked through the direct API.

### 6.4. Running and Results

In the Spring Boot project directory:

~~~bash
./gradlew bootRun
# Windows PowerShell: .\gradlew.bat bootRun
~~~

**Lines printed by the example via `System.out`, in order** (excluding Boot/Gradle logs):

~~~text
DB_LOAD #1
initial = Original
cached = Original
rollback tx raw = Original
after rollback = Original
commit tx raw = Original
DB_LOAD #2
after commit = Committed
hit after commit = Committed
during put raw = null
after put raw = ready
during rolled put raw = null
after rolled-back put = null
outside transaction = immediate
~~~

Cross-check:

1. On the first read, the cache misses; JDBC reads `Original` and prints `DB_LOAD #1`. Because no transaction is active, `cache.put("B1", "Original")` takes effect immediately. The second read hits without printing another `DB_LOAD`.
2. In the rollback transaction, the database temporarily updates to `RolledBack`; `cache.evict("B1")` **only registers post-commit eviction**. The raw cache still holds `Original`. `status.setRollbackOnly()` causes H2 to roll back and the `afterCommit` callback does not run. The next read still hits `Original`.
3. In the commit transaction, the database changes to `Committed`. Eviction is scheduled again; **before commit**, the raw cache still holds `Original`. When the transaction commits successfully, the callback removes entry `B1`. The next read misses, JDBC prints `DB_LOAD #2`, returns `Committed`, and caches it; the following read hits.
4. `cache.put("manual", "ready")` inside the transaction does not appear in the raw cache yet; hence `during put raw = null`. After commit, the callback writes it and the value becomes `ready`.
5. `cache.put("rolled", "ghost")` in a rolling-back transaction does not appear in the raw cache immediately, nor after rollback. This demonstrates **not caching uncommitted data**.
6. `cache.put("outside", "immediate")` occurs outside any transaction, so it takes effect immediately and the raw cache reads `immediate`.

**The output is derived from the sequential scenario** and the contract of Spring's `TransactionAwareCacheDecorator` with `TransactionTemplate` and H2. In a real application, run integration tests with your exact Spring/Boot version, transaction manager configuration, and actual backend.

## 7. Using With `@Transactional`, `@Cacheable`, and `@CacheEvict`

In a typical service application:

~~~java
@Service
public class BookWriteService {

    private final BookRepository repository;

    public BookWriteService(BookRepository repository) {
        this.repository = repository;
    }

    @Transactional
    @CacheEvict(cacheNames = "books", key = "#p0")
    public void rename(String id, String newTitle) {
        repository.rename(id, newTitle);
    }
}
~~~

This is an **illustrative snippet**, not a standalone Java file: `BookRepository` and imports for `@Service`, `@Transactional`, and `@CacheEvict` must be declared. For cache annotations to take effect, enable `@EnableCaching` and configure the interceptor to use the wrapped `CacheManager`. `@Transactional` must be applied when calls pass through a Spring-managed proxy (or equivalent mechanism).

When a caching operation performs `evict` inside a transaction with active synchronization, the decorator **defers deletion until `afterCommit`**. However, **the ordering between transaction advice and caching advice also matters**: if cache advice runs after the transaction has already finished, the out-of-transaction cache operation executes immediately (though at that point the commit is already done); do not rely on an implicit ordering to prove complex consistency.

Similarly, `@CachePut` can lead to a `Cache.put` command that is deferred until after commit if it goes through a decorated cache inside a synchronized transaction. `@Cacheable` on a miss normally performs a put; reading again inside the same transaction **may not see the new entry yet**, because a pending put is not yet a written cache value. Paths using `@Cacheable(sync=true)` or cache loading APIs (`get(key, Callable)`/async retrieval) must be checked individually: they may go through native loader semantics, and you **should not assume** they are all deferred like a normal `Cache.put` call.

### Difference With `beforeInvocation=true`

~~~java
@CacheEvict(cacheNames = "books",
            key = "#p0",
            beforeInvocation = true)
public void rename(String id, String title) {
    // ...
}
~~~

This snippet illustrates code inside a Spring bean. `beforeInvocation=true` controls **when the Spring caching interceptor issues the evict command relative to running the method**. If the `evict` command is issued while transaction synchronization is active and the manager is transaction-aware, **the actual effect on the target cache may still be deferred**. If no transaction/synchronization exists yet, eviction can happen immediately. Do not equate this annotation attribute with a guarantee of "definitely deletes before/after database commit".

## 8. Important Limitations: Not an XA Transaction

`TransactionAwareCacheManagerProxy` **does not perform a two-phase commit** across database and cache. It does not guarantee "either both database and cache commit or both roll back" atomicity in every situation.

### 8.1. Database Commits, Cache Callback Can Still Fail

The actual sequence can be: database commit succeeds → `afterCommit` callback attempts evict/put → cache provider loses connection or errors. The database cannot be "uncommitted" just because the post-commit eviction failed. Design retries, events/outbox, monitoring, and error handling according to consistency requirements; do not treat the decorator as a Redis/Caffeine transaction manager.

### 8.2. Stale Data Window Before Commit

Because eviction is deferred, another request can read the **old entry** while the DB update transaction has not yet committed. This aligns with not exposing uncommitted new data. However, around commit time, concurrent requests can create cache-loading races—for instance, a request begins loading the old source before commit and finishes putting it after eviction. The decorator **does not solve all of these races automatically**.

If very strong consistency is required, consider versioned cache keys, concurrency/invalidation control, transactional outbox/events, or not caching strongly consistent data.

### 8.3. `put`/`evict` Has No Read-Your-Writes

`cache.put(key, newValue)` is scheduled but has not yet replaced the target cache. Inside the same transaction, `cache.get(key)` can still return the old entry. Do not write business logic assuming "call put then get immediately must return newValue" when using a decorated cache. If the new value is needed inside the transaction, use the just-computed business variable/object or read the database within the appropriate transaction—do not read the cache to verify a pending put.

### 8.4. Immediate Operations Are Not Rolled Back

`putIfAbsent`, `evictIfPresent`, and `invalidate` demand immediate effect. They are not deferred like `put`/`evict`/`clear`, so a DB rollback does not automatically undo those cache changes. Evaluate the API's semantics before using it inside a transaction.

### 8.5. No Transaction Synchronization

Having `@Transactional` on a method is not enough if the call goes via `this.method()` and bypasses the proxy, or if the actual transaction manager does not open synchronization. When there is no Spring-managed transaction synchronization, cache operations are executed immediately by the decorator. For async threads, reactive flows, or code running outside the transaction's thread context, verify context propagation; **do not assume** a new thread inherits the transaction and callbacks.

### 8.6. Multiple Cache Managers and Multiple Replicas

If two `CacheManager`s exist and annotations still use the **raw** manager, the transaction-aware layer has no effect. Verify the injected bean and the caching interceptor's default `cacheManager`. With local Caffeine caches, each JVM has its own cache: an after-commit evict on JVM A does not automatically clear JVM B's cache. With a shared Redis cache, understand the backend's transaction and network policies as well as any extra local cache layers.

## 9. When to Use? Comparing the Options

| Need | Suitable solution |
| --- | --- |
| App already has a `CacheManager` and wants to defer `put/evict/clear` until after commit | Wrap with `TransactionAwareCacheManagerProxy` |
| Only one specific `Cache` needs decorating | Can use `new TransactionAwareCacheDecorator(cache)` if all access paths are controlled |
| A manager already has built-in transaction-aware support | Check **that manager's** API to enable it, if supported; avoid pointless double wrapping |
| Caching outside transactions or read-only data | Plain manager may suffice |
| Distributed updates, event loss, or ultra-high consistency requirements | Add outbox, event invalidation, versioning, retries, monitoring, or skip caching |
| Need exactly-once / atomic DB + cache as one resource | `TransactionAwareCacheManagerProxy` **does not** provide this guarantee |

Note on `AbstractTransactionSupportingCacheManager`: Spring's base class offers `setTransactionAware(true)` for managers that actually extend it. **Do not assume every manager type**, especially Caffeine/Redis across all versions, has this method. `TransactionAwareCacheManagerProxy` can be an explicit option to wrap an existing manager.

## 10. Common Mistakes and How to Spot Them

1. **Wrapping the manager while code still uses the raw manager:** deferred operations do not happen. Check `@Primary`, `@Qualifier`, and caching configuration.
2. **Assuming the proxy creates a transaction:** this class only observes existing synchronization; a transaction manager must be executing a transaction.
3. **Assuming `@Transactional` runs on self-invocation:** calling `this.rename(...)` typically bypasses AOP advice in proxy mode.
4. **Confusing deferred put with a database write:** it has no control over cache backend commits like an XA participant.
5. **Assuming `evictIfPresent` is deferred:** it is an immediate operation, unlike `evict`.
6. **Assuming pending puts can be read back:** cache hits/misses depend on the target cache; verify read-your-writes with tests.
7. **Using `@Cacheable(sync=true)` and assuming all puts are `afterCommit`:** the loader path has its own semantics; check the real provider.
8. **Not handling failed cache callbacks after commit:** the DB may already be committed while the cache remains wrong/stale; observability and recovery strategies are needed.
9. **Testing only the happy path:** rollback is the case that proves the critical difference.
10. **Using post-commit eviction without synchronizing other replicas:** local caches across multiple processes remain independent.
11. **Forgetting namespace and key:** evicting `books["B1"]` does not remove `searchResults["B1"]`; cache names/keys must align.
12. **Assuming cache stats or TTL are configured automatically:** the decorator adds no TTL/size/metrics; those belong to the provider.

## 11. Exercises and Test Plan

### 11.1. Exercises From the Demo

1. Remove `TransactionAwareCacheManagerProxy` and inject `rawCacheManager` directly into `Cache cache`: in the rollback transaction, `cache.evict("B1")` deletes the entry immediately. Compare outputs and note why rollback does not automatically restore the cache entry.
2. In the commit transaction, try `cache.put("manual", "ready")` and read the raw cache **before** commit: raw does not have the entry yet. After commit: raw now has `ready`.
3. Change `status.setRollbackOnly()` to throwing `IllegalStateException`: using exception handling outside `TransactionTemplate`, verify the database rolls back and pending cache operations are not applied.
4. Move `cache.evict("B1")` outside `TransactionTemplate`: the operation runs immediately. Explain the difference from evicting inside a transaction.
5. Create a `temporary` key, call `evictIfPresent` or `putIfAbsent` inside a transaction, then roll back; observe the immediate behavior and contrast it with `evict`/`put`.
6. Add a Spring service with `@Transactional` and `@CacheEvict`, enable `@EnableCaching`, and verify the decorated manager is actually used by the Spring cache interceptor.
7. Try running two concurrent transactions in a test to expose races around commit/`afterCommit` time and propose versioned keys or invalidation events.

### 11.2. Test Matrix to Have

| Case | Action | Expected result |
| --- | --- | --- |
| No transaction | `cache.put(k,v)` via decorated cache | Target cache sees value immediately |
| Rollback + `put` | Write pending value then roll back | Target does not contain new value |
| Commit + `put` | Write pending value then commit | Target sees value after commit |
| Rollback + `evict` | Schedule evict then roll back | Target retains old entry |
| Commit + `evict` | Schedule evict then commit | Target entry deleted; next read misses |
| Commit + `clear` | Pending clear then commit | Target region entries cleared after commit |
| Immediate API | `putIfAbsent` or `evictIfPresent` | Immediate effect; rollback does not undo |
| Read after pending put | `put` then `get` inside transaction | May not see new value yet |
| Swap manager injection | Inject raw instead of wrapper | Deferred behavior disappears |
| Cache backend error at afterCommit | Simulate error during evict | DB already committed; recovery mechanism needed |
| Concurrency | Load cache around commit | Do not assume zero staleness |
| Multi-instance | Evict local JVM A | JVM B's local cache does not change automatically |

### Pre-Deployment Checklist

- [ ] Target `CacheManager` has cache names, TTL, capacity, and backend properly configured.
- [ ] The `TransactionAwareCacheManagerProxy` bean is the manager actually used by services/interceptors.
- [ ] Transaction manager and synchronization operate on the right context/thread.
- [ ] Understand `put/evict/clear` are deferred while `putIfAbsent/evictIfPresent/invalidate` are immediate.
- [ ] No expectation of read-your-writes for pending puts.
- [ ] Commit/rollback tests exist against a real (or embedded) database and the cache backend in use.
- [ ] Plans exist for races, `afterCommit` failures, multiple replicas, retries, and invalidation.
- [ ] Do not treat the decorator as a replacement for a transactional outbox or distributed transactions.

## 12. Official References

- Spring Framework — TransactionAwareCacheManagerProxy JavaDoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html
- Spring Framework — TransactionAwareCacheDecorator JavaDoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html
- Spring Framework — TransactionSynchronizationManager JavaDoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Framework — TransactionTemplate: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
