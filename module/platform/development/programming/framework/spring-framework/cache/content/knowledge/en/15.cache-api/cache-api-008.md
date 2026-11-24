# Deferred Operations and Immediate Visibility Expectations in Spring Cache

## 1. Core problem: returning from the API does not always mean new data is visible

`org.springframework.cache.Cache` is the abstraction Spring Framework uses to read, write, and invalidate cache entries. A call to `cache.put(key, value)`, `cache.evict(key)`, or `cache.clear()` **may return before the write/removal actually takes effect for the next lookup**. The Spring Cache Javadoc allows these operations to be implemented asynchronously or in a deferred manner.

Conversely, `putIfAbsent`, `evictIfPresent`, and `invalidate` are designed with **an expectation of immediate effect**. The practical significance goes beyond having a return value: these methods carry a different contract regarding when the change becomes observable.

This matters in the **programmatic API** group, especially when an application uses Spring-managed transactions, `TransactionAwareCacheDecorator`, Redis/remote caches, Caffeine, concurrent readers, or asynchronous work.

Questions to answer before using them:

- After `put` returns, will a `get` for the same key see the new value immediately?
- After `evict` returns, can another request still retrieve the old entry?
- Does `evictIfPresent` or `invalidate` returning `false` mean failure?
- When a transaction rolls back, are requested cache write/evict commands executed?
- Does using an immediate API guarantee atomic synchronization with the database and all nodes?
- Why is `@CacheEvict(beforeInvocation=true)` still not enough to guarantee immediate physical cache deletion?

The goal of this lesson is to understand the **API contract, visibility timing, transaction-aware behavior, and provider limits**, and then verify them yourself with a Java 17 + Spring Cache program.

## 2. Comparison table of Cache operations

| API | Purpose | Timing contract | Return value |
| --- | --- | --- | --- |
| `void put(Object key, Object value)` | Write or replace a value | **May** be async/deferred; immediate lookup might not see the entry yet | None |
| `Cache.ValueWrapper putIfAbsent(key, value)` | Write only if the key does not exist | Designed for **immediate registration** | Wrapper of the old value, or `null` if no prior mapping existed |
| `void evict(Object key)` | Remove one mapping | **May** be async/deferred; immediate lookup might still see the entry | None |
| `boolean evictIfPresent(Object key)` | Remove one mapping expecting it to vanish immediately | **Immediate visibility expectation** | `true` if the key was known to have a mapping, `false` if absent or unknown |
| `void clear()` | Remove all mappings in this cache | **May** be async/deferred | None |
| `boolean invalidate()` | Make the entire cache have no visible entries immediately | **Immediate visibility expectation** | `true` if the cache was known to have mappings, `false` if empty or unknown |

`get(key)` is the read operation: it returns `Cache.ValueWrapper` when a mapping exists or `null` on a miss. `ValueWrapper` itself can hold a business `null` value; **hit-null differs from miss**. When testing eviction, verify `cache.get(key) == null` rather than merely checking `wrapper.get() == null`.

A contrasting pair of examples:

~~~java
cache.evict("u:42");             // May not have finished evicting at return time.
cache.evictIfPresent("u:42");    // Expects post-call lookups to no longer see the mapping.

cache.clear();                  // May be deferred.
cache.invalidate();             // Expects all mappings to become invisible immediately.
~~~

This is a **snippet** requiring a `Cache cache` variable. Do not call both lines in the same test and then try to deduce which line actually removed the entry; create independent test cases.

## 3. "Immediate" is a local visibility contract, not system-wide ACID

Distinguish three milestones:

1. **Command invoked:** business code called `Cache.evict` or `Cache.put`.
2. **Command completed in the cache implementation:** the native store/decorator executed the corresponding operation.
3. **Result observed by readers:** lookups from the same cache instance or across multiple nodes/near caches see the post-change state.

A method returning at milestone 1 does not always mean milestones 2 and 3 have occurred. Immediate-style methods impose a stronger expectation on milestone 3, but **you must check whether the provider actually implements it**.

"Immediate" does not automatically guarantee that every replica, L1/L2 cache tier, database transaction, and reader across every region are synchronized. While one key is evicted, another thread can still write that key back right after the operation finishes. That is a **race condition**, not necessarily a bug in `evictIfPresent`.

Similarly, an immediate cache eviction before DB commit can cause a reader to miss, read the **old** value from the DB, and re-cache it, leaving stale data after commit. Commit timing and reader races must be addressed separately.

## 4. Why are put/evict/clear allowed to be deferred?

**Transaction synchronization.** `TransactionAwareCacheDecorator` can defer `put`, `evict`, and `clear` so that the native cache is modified only in the **after-commit** phase of a successful Spring transaction. Before commit, the cache can retain the old entry; on rollback, the after-commit callback will not run.

**Async backend.** Caches supporting non-blocking or remote write-through may enqueue requests or invoke the backend asynchronously. When the method returns, readers may not yet observe the change.

**Distributed/near cache.** Deleting a local mapping and broadcasting invalidations to other nodes may not happen at the same instant. Backends may have their own consistency policies.

This does **not** mean every `put/evict/clear` is always slow or always deferred. Standard `ConcurrentMapCache` uses an in-JVM map where operations can take effect immediately. However, code built on the Spring `Cache` abstraction **must not generalize a universal guarantee** from a local implementation.

### Timeline: deferred eviction

~~~text
T0  Cache["product:42"] = old
T1  Transaction starts
T2  cache.evict("product:42")       => registers after-commit
T3  cache.get("product:42")         => may still see old
T4  Database transaction commits
T5  Cache callback afterCommit()   => actual eviction
T6  cache.get("product:42")         => MISS if no other writer
~~~

The timeline above is an **example of a transaction-aware cache**, not a mandatory rule for every cache.

## 5. evictIfPresent and invalidate: interpreting boolean values properly

With a cache that properly implements immediate semantics:

~~~java
boolean wasPresent = cache.evictIfPresent(key);
Cache.ValueWrapper after = cache.get(key);
// No concurrent writer: after eviction, expect after == null.
~~~

`wasPresent == true` means the cache **knew a mapping existed beforehand**; `false` can mean **no mapping existed**, or the implementation **could not determine** previous presence. Do not treat `false` as an error code.

Similarly:

~~~java
boolean hadEntries = cache.invalidate();
// hadEntries=false does not prove the invalidate operation failed.
~~~

`invalidate()` operates on **that cache instance/cached region**, not automatically across every cache name in `CacheManager`. `true` is also neither the count of deleted entries nor proof that every node in the system acknowledged it.

**An anti-pattern:**

~~~java
if (!cache.evictIfPresent(id)) {
    throw new IllegalStateException("Eviction failed");
}
~~~

The exception branch above is semantically wrong: "the key was not in the cache" is not an error. Backend failures are typically represented by dedicated exceptions or provider error handling; under the contract, `false` has normal meanings.

## 6. Limitations of default implementations

A stronger method name does not always mean a stronger actual implementation:

- `Cache.evictIfPresent(key)` is a **default method**. Per the Javadoc, the default may delegate to `evict(key)` and return `false` because previous presence cannot be determined. When `evict` is deferred, you cannot assume this default provides immediate visibility.
- `Cache.invalidate()` has a contract expecting immediate clearing, but custom caches relying on the default method still need checking to see whether native entries are cleared right away.
- `Cache.putIfAbsent` has a **conditional insert** contract aimed at atomicity/immediate registration. However, the default implementation may perform `get(key)` followed by `put(key,value)`, which is inherently non-atomic under concurrent contention. The Javadoc directs you to check provider-specific semantics.

For custom `Cache` implementations, override them properly if the system requires immediate behavior or atomic conditional insert. For existing providers, inspect the runtime class and implementation docs; **do not** verify solely from method names.

**Version milestone:** `evictIfPresent` and `invalidate` were introduced to the Spring Cache API in Spring Framework 5.2. Async `retrieve` methods belong to a newer API and carry their own semantics.

## 7. TransactionAwareCacheDecorator and post-commit synchronization

Spring provides `org.springframework.cache.transaction.TransactionAwareCacheDecorator` to wrap a `Cache`, as well as `TransactionAwareCacheManagerProxy` to decorate caches obtained from a `CacheManager`.

According to the Javadoc, when a **Spring transaction is active**, the decorator synchronizes `put`, `evict`, and `clear` via `TransactionSynchronizationManager`, executing the native operation in **after-commit**. When **no** transaction is active, operations are delegated for immediate normal execution.

~~~mermaid
sequenceDiagram
    participant Caller
    participant Tx as Spring Transaction
    participant C as TransactionAwareCacheDecorator
    participant Native as Native Cache

    Caller->>Tx: begin
    Caller->>C: evict(K)
    C->>Tx: register afterCommit callback
    Caller->>C: get(K)
    C->>Native: get(K)
    Native-->>Caller: old is still present
    alt Commit succeeds
        Tx->>C: afterCommit()
        C->>Native: evict(K)
    else Rollback
        Note over Tx,Native: no afterCommit eviction
    end
~~~

Consequences to remember:

1. Inside a transaction, `cache.put(K,new)` may **not yet be visible** to a `cache.get(K)` call immediately afterward. The decorator does not necessarily provide a *transaction-local overlay* or "read your uncommitted cache writes".
2. If the transaction rolls back, deferred `put/evict/clear` calls do not run their after-commit callbacks; the cache retains its prior state (barring other changes).
3. If the transaction was opened by an outer caller, after-commit can arrive **later** than when the business method returns.
4. `TransactionAwareCacheDecorator` does not turn the database and cache into a distributed ACID transaction. If the cache provider fails when the after-commit callback runs, a dedicated error/recovery mechanism is needed.
5. Transaction propagation (`REQUIRES_NEW`, outer rollback, nested savepoints) and advice order determine which transaction is active when the command is issued; test actual boundaries.

### Why are immediate methods not deferred like that?

`putIfAbsent`, `evictIfPresent`, and `invalidate` carry immediate feedback/effect semantics, so they cannot simply be queued into an after-commit callback while honoring their contracts. If you use an immediate operation inside a transaction, you accept that the cache can change **before knowing whether the DB will commit or roll back**.

For example, calling `evictIfPresent(K)` followed by a transaction rollback leaves the entry evicted even though the database did not change. Calling `putIfAbsent(K,new)` followed by a rollback can leave behind a value not reflecting committed DB state. This is the trade-off between *immediate visibility* and *commit-consistent cache updates*.

## 8. Runnable example: Java 17, Maven, and TransactionTemplate

This example uses a native `ConcurrentMapCache` and a `TransactionAwareCacheDecorator`. Transactions are driven by `TransactionTemplate` with a minimal implementation of `AbstractPlatformTransactionManager` to produce **real Spring transaction synchronization**.

**Mandatory note:** the transaction manager in the example **does not manage a database**, lock resources, or roll back business data. It only simulates begin/commit/rollback to observe callbacks. Do not use this demo class in production.

### 8.1. Maven pom.xml

Uses Spring Framework 6.2.14, Java 17+:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>cache-visibility-demo</artifactId>
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
      <artifactId>spring-tx</artifactId>
      <version>6.2.14</version>
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

### 8.2. File src/main/java/demo/CacheVisibilityDemo.java

~~~java
package demo;

import org.springframework.cache.Cache;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.cache.transaction.TransactionAwareCacheDecorator;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;
import org.springframework.transaction.support.DefaultTransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;

public final class CacheVisibilityDemo {

    private CacheVisibilityDemo() { }

    // Used to demonstrate Spring transaction synchronization.
    // Not a transaction manager for a real database.
    static final class DemoTransactionManager
            extends AbstractPlatformTransactionManager {
        private static final long serialVersionUID = 1L;

        @Override
        protected Object doGetTransaction() {
            return new Object();
        }

        @Override
        protected void doBegin(Object transaction,
                               TransactionDefinition definition) { }

        @Override
        protected void doCommit(DefaultTransactionStatus status) { }

        @Override
        protected void doRollback(DefaultTransactionStatus status) { }
    }

    private static String lookup(Cache cache, String key) {
        Cache.ValueWrapper wrapper = cache.get(key);
        return wrapper == null ? "MISS" : String.valueOf(wrapper.get());
    }

    public static void main(String[] args) {
        Cache nativeCache = new ConcurrentMapCache("examples");
        Cache cache = new TransactionAwareCacheDecorator(nativeCache);
        TransactionTemplate tx =
                new TransactionTemplate(new DemoTransactionManager());

        nativeCache.put("a", "v1");
        tx.execute(status -> {
            cache.evict("a");
            System.out.println("evict inside=" + lookup(cache, "a"));
            return null;
        });
        System.out.println("evict after commit=" + lookup(cache, "a"));

        nativeCache.put("b", "v2");
        tx.execute(status -> {
            boolean wasPresent = cache.evictIfPresent("b");
            System.out.println("evictIfPresent wasPresent=" + wasPresent);
            System.out.println("evictIfPresent inside=" + lookup(cache, "b"));
            return null;
        });

        tx.execute(status -> {
            cache.put("c", "v3");
            System.out.println("put inside=" + lookup(cache, "c"));
            return null;
        });
        System.out.println("put after commit=" + lookup(cache, "c"));

        tx.execute(status -> {
            boolean inserted = cache.putIfAbsent("d", "v4") == null;
            System.out.println("putIfAbsent inserted=" + inserted);
            System.out.println("putIfAbsent inside=" + lookup(cache, "d"));
            return null;
        });

        nativeCache.put("e", "v5");
        tx.execute(status -> {
            cache.clear();
            System.out.println("clear inside=" + lookup(cache, "e"));
            return null;
        });
        System.out.println("clear after commit=" + lookup(cache, "e"));

        nativeCache.put("f", "v6");
        tx.execute(status -> {
            boolean hadEntries = cache.invalidate();
            System.out.println("invalidate hadEntries=" + hadEntries);
            System.out.println("invalidate inside=" + lookup(cache, "f"));
            return null;
        });

        nativeCache.put("g", "v7");
        tx.execute(status -> {
            cache.evict("g");
            status.setRollbackOnly();
            System.out.println("rollback inside=" + lookup(cache, "g"));
            return null;
        });
        System.out.println("rollback after=" + lookup(cache, "g"));
    }
}
~~~

### 8.3. Running and observing

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheVisibilityDemo
~~~

Lines printed by the program (excluding Maven/Spring logs):

~~~text
evict inside=v1
evict after commit=MISS
evictIfPresent wasPresent=true
evictIfPresent inside=MISS
put inside=MISS
put after commit=v3
putIfAbsent inserted=true
putIfAbsent inside=v4
clear inside=v5
clear after commit=MISS
invalidate hadEntries=true
invalidate inside=MISS
rollback inside=v7
rollback after=v7
~~~

Interpretation:

1. `evict("a")` only registers a callback: inside the transaction `v1` is still visible; after commit it is a miss.
2. `evictIfPresent("b")` is immediate on `ConcurrentMapCache`, returns `true` because the mapping existed beforehand, and an immediate lookup inside the transaction is a miss.
3. `put("c","v3")` is not yet visible inside the transaction; after commit `v3` is seen.
4. `putIfAbsent("d","v4")` writes immediately, returns `null` because the key did not exist, and a subsequent lookup sees `v4`.
5. `clear()` defers until commit so inside the transaction `e=v5` is still seen; after commit it is a miss.
6. `invalidate()` immediately clears the whole cache at call time in the demo; `true` because the cache had entries beforehand.
7. `evict("g")` was requested, but the transaction rolled back, so the after-commit callback did not run; `g=v7` remains intact.

The results are derived from the contract and code logic; the Java example **has not actually been executed in the documentation's environment**. When applying it in a project, run it with your chosen dependency/version and add tests against a real transaction manager/provider.

## 9. putIfAbsent: immediate differs from overwrite and atomicity

`putIfAbsent(key,value)` is not a "faster" version of `put`:

- If the key **has no entry yet**, the provider attempts to insert and typically returns `null` since there was no previous value.
- If the key **already has an entry**, the operation preserves the old mapping and returns the `Cache.ValueWrapper` of the old value. If the old mapping stored a **cached null**, the wrapper can still be non-null even though `wrapper.get()==null`.
- If the application needs to update an old value to a new one, **do not replace `put` with `putIfAbsent`**; if the key already exists, the new value will not be written.
- Atomicity in a multi-threaded environment must be verified in the implementation. The Javadoc notes the default may delegate to `get` then `put` and does not guarantee atomicity equivalent to native compute-if-absent.

~~~java
Cache.ValueWrapper previous = cache.putIfAbsent(key, candidate);
if (previous == null) {
    // No entry existed before the operation: attempt insert.
} else {
    Object oldValue = previous.get(); // May itself be cached null.
    // candidate was not written to replace the prior value.
}
~~~

The snippet above requires `Cache cache` and defined key/candidate variables. Do not conclude that a transaction rollback will delete a candidate that was immediately put; design separately if needed.

## 10. evictIfPresent does not eliminate races with loaders

Suppose a reader is loading an old value from the database while a writer evicts:

~~~text
Reader A: Cache miss; starts DB read, result not back yet
Writer B: DB update; evictIfPresent(K) => entry K gone
Reader A: Old DB read completes; put(K, oldValue)
Reader C: Cache hit K=oldValue
~~~

This sequence can happen even when `evictIfPresent(K)` completes with true immediate semantics on a cache instance. It does not stop Reader A from **writing stale data back** after eviction.

Ways to reduce risk depending on the required consistency level:

- Invalidation **after DB commit** or a reliable after-commit mechanism.
- Versioned cache keys or version/generation checks so an old loader cannot write into the current namespace.
- Timeouts/TTLs and telemetry for stale reads.
- Appropriate synchronization/CAS/locking when data is highly sensitive to concurrency.
- Sending invalidation events to near caches and other nodes with an appropriate delivery guarantee.

Do not use the cache as the sole source of truth for invariants that must be enforced by the database/transaction.

## 11. clear and invalidate: scope, cost, contention

`clear()` and `invalidate()` affect **all entries of a single selected cache**; they do not automatically clean every cache name in `CacheManager` or every local/remote layer in other applications.

- `clear()` may defer and allow immediate lookups to still see old entries.
- `invalidate()` expects entries to become invisible immediately under implementation semantics.
- `invalidate() == false` is not a failure. The cache may be empty, or it may be unknown whether entries existed beforehand.
- Clearing/invalidating an entire cache can trigger a **cache stampede**: many requests miss simultaneously and hit the DB/upstream. Capacity planning and sometimes background warming are needed.
- If multiple caches have different key schemas, invalidate the right cache names; do not broaden clearing system-wide just to handle one key.

With `@CacheEvict(allEntries=true)`, the annotation carries cache-clearing semantics per `Cache` operation, **and does not automatically pick `invalidate()` just because the caller needs immediate visibility**. If immediate is a strict business requirement, use the direct API with a verified provider or design a dedicated invalidation mechanism.

## 12. Annotations and transactions: two independent timing layers

A common case:

~~~java
@Transactional
@CacheEvict(cacheNames = "products", key = "#p0",
            beforeInvocation = false)
public void updateProduct(long id, String name) {
    repository.rename(id, name);
}
~~~

This is a snippet inside a Spring bean with a repository/transaction manager, not a standalone program. There are two layers:

1. **Cache annotation timing:** `beforeInvocation=false` means the annotation requests eviction after the method observed by cache advice returns normally.
2. **Cache provider/decorator timing:** once eviction is requested, `Cache.evict` may run immediately, defer until after-commit, or run asynchronously depending on the active cache.

**Therefore, do not equate** `@CacheEvict(beforeInvocation=true)` with "the native entry is physically deleted before the business method" if a transaction-aware cache is active. Changing only annotation advice ordering without considering transaction boundaries and cache decorators can cause bugs.

If the transaction rolls back after the method returns, deferred eviction may not run. If the method throws an exception before post-invocation eviction is requested, that operation will not run either. Both cases must be understood accurately before using cache state as a business state signal.

## 13. Async APIs and remote providers

Spring Framework 6.1 added `Cache.retrieve(key)` and `Cache.retrieve(key, Supplier<CompletableFuture<T>>)` for implementations supporting async retrieval. For caches needing `CompletableFuture`/reactive support, the Javadoc states `put`/`evict`/`clear` should be **effectively non-blocking**, with backend write-through potentially running asynchronously.

Do not confuse:

- A `CompletableFuture` from `retrieve` is a **result-returning** contract, not proof that `put`/`evict` has applied on every replica.
- Native Redis/Caffeine cache APIs may have their own semantics differing from Spring `Cache`.
- "Immediate evict" on one node does not necessarily mean every node's near cache is updated, if the provider offers no such guarantee.
- A single-threaded runtime test with `ConcurrentMapCache` cannot prove a distributed design using Redis, a transaction-aware decorator, and multiple service instances.

When concurrency/async is involved, test the milestones: call return, native change, local get, remote get, loader completion, and database commit.

## 14. API selection matrix

| Need | API / mechanism to consider | What to verify |
| --- | --- | --- |
| Write new value, overwrite allowed | `put` | Is it deferred? Is read-your-writes guaranteed? |
| Write only if key does not exist | `putIfAbsent` | Atomicity, previous wrapper, rollback risk |
| Evict a key, can wait for commit | `evict` via transaction-aware cache | Active transaction and after-commit callback |
| Delete a key and expect post-call lookups to miss | `evictIfPresent` | Provider override, concurrent writers, DB race |
| Invalidate entire cache and deferral is acceptable | `clear` | Reload cost and transaction boundary |
| Invalidate entire cache with immediate expectation | `invalidate` | Provider semantics, distributed visibility, boolean |
| Avoid caching uncommitted data | Deferred `put` after commit | Do not expect pre-commit gets to see the new value |
| Ensure strong database + cache consistency | Dedicated transaction/consistency design | Cache operations do not replace DB transactions |
| Optimize latency for async backend | Non-blocking cache operations | Completion/visibility and exception handling |

For critical business requirements, specify **when success is defined** and **which readers must observe the change** rather than choosing a method merely because its name contains `Present` or `invalidate`.

## 15. Common errors

**Error 1.** "Once `put` returns, `get` sees the new value immediately." False for deferred/async caches.

**Error 2.** "Once `evict` returns, the key is definitely gone." False if the provider defers.

**Error 3.** "`evictIfPresent` returning `false` is a deletion error." False; the key may not have existed beforehand or presence was unknown.

**Error 4.** "`invalidate` returning `false` means entries remain." False per the boolean contract.

**Error 5.** "`putIfAbsent` updates an old value faster than `put`." False: it does not overwrite.

**Error 6.** "The default `putIfAbsent` implementation is always atomic." Do not assume; the Javadoc allows the default to be equivalent to get then put.

**Error 7.** "Just calling an immediate API in a transaction makes DB/cache roll back together." False: the immediate operation may have completed before DB rollback.

**Error 8.** "TransactionAwareCacheDecorator automatically creates a distributed transaction." False: it coordinates callbacks, not a 2-phase commit between DB and cache.

**Error 9.** "`@CacheEvict(beforeInvocation=true)` guarantees immediate native eviction." False if a cache/decorator layer still defers.

**Error 10.** "Immediate eviction prevents all stale reads." Concurrent loaders/near caches can still write or return stale values.

**Error 11.** "`invalidate` affects every cache name." It clears mappings of the specific cache instance it is called on.

**Error 12.** "Testing `ConcurrentMapCache` suffices to prove production Redis." Insufficient; test the real implementation, transactions, and network.

## 16. Testing and documentation checklist

An integration test should verify in order:

1. In a transaction-aware cache, `put/evict/clear` are not visible before commit, and become visible after commit.
2. Rollback does not execute after-commit callbacks.
3. `putIfAbsent` writes immediately when the key is empty and does not overwrite when the key exists.
4. `evictIfPresent` and `invalidate` exhibit immediate behavior per the chosen implementation.
5. Boolean return values are interpreted properly when entries do not exist.
6. Cached-null and cache miss are not confused when inspecting `Cache.ValueWrapper`.
7. Multiple threads/loaders do not recreate stale entries after critical invalidations.
8. Transaction manager, advice order, and outer/inner transactions are tested with a real DB when consistency is required.
9. Cross-node/near caches actually meet visibility targets if the product has an SLA.
10. Error handlers, timeouts, and backend outages do not cause stale data to be silently ignored.

Official reading sources:

- [Spring Cache API Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html) — `put`, `putIfAbsent`, `evict`, `evictIfPresent`, `clear`, `invalidate`, `retrieve`.
- [TransactionAwareCacheDecorator Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html) — after-commit synchronization and immediate methods.
- [TransactionAwareCacheManagerProxy Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html) — wrapping `CacheManager`.
- [ConcurrentMapCache Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCache.html) — in-JVM cache, overriding immediate operations.
- [Spring Framework Cache Annotations](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html) — annotation timing compared to cache operations.
- [TransactionTemplate Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html) — transaction callback API.

**Summary:** `put`, `evict`, and `clear` may be deferred; `putIfAbsent`, `evictIfPresent`, and `invalidate` express expectations of immediate effect. Read the contract/provider implementation, define transaction boundaries, and test concurrency to turn those expectations into real correctness.
