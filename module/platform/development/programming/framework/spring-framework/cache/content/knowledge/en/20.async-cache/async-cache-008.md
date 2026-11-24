# Timing of `@CachePut` and `@CacheEvict` for Asynchronous Results

## Objective

This lesson belongs to the **Asynchronous** group of Spring Framework Cache. After this lesson, you will:

- Distinguish the moment a Java method **returns** a `CompletableFuture<T>` from the moment the future **completes** successfully or fails.
- Explain accurately when `@CachePut` writes to the cache and `@CacheEvict` removes from the cache in Spring-supported asynchronous result processing paths.
- Distinguish default `@CacheEvict` (after invocation and after a successful result) from `beforeInvocation = true` (issuing the eviction before running the method).
- Verify cache state **while the future is still pending**, after `complete(...)`, and after `completeExceptionally(...)`.
- Recognize key limitations of Reactor `Mono`/`Flux`, Spring `@Async`, AOP proxies, transactions, cancellation, race conditions, and cache providers.
- Build tests without relying on `Thread.sleep` on Spring Boot + Java 17+.

**Main point:** in Spring Framework **6.1+**, Spring Cache supports adapting to `CompletableFuture` and recognized reactive types. For result-based operations, **a method returning a future does not mean the background operation has succeeded**. `@CachePut` uses the successfully completed value, while after-invocation `@CacheEvict` waits for successful completion; `beforeInvocation=true` evicts upfront without waiting for the outcome. Verify your actual Spring version and backend before relying on this timing.

## 1. Three Timestamps to Distinguish

Suppose a document update method:

~~~java
@CachePut(cacheNames = "documents", key = "#p0")
public CompletableFuture<String> update(String id) {
    return remoteRepository.updateAsync(id);
}
~~~

This is an **illustrative snippet**, where `remoteRepository` is a business dependency.

There are three timestamps:

1. **T0 — Interceptor receives the call:** caller invokes the Spring bean through the proxy; Spring cache advice resolves the cache operation and key.
2. **T1 — Method returns an incomplete handle:** Java has returned to the caller with `CompletableFuture<String>`, while I/O or background work is still pending.
3. **T2 — Completion signal:** the future may complete successfully with `String`, complete exceptionally, be canceled, or never complete.

~~~text
T0                           T1                            T2
|----------------------------|-----------------------------|
call update("D1")            returns PENDING future        future success("new")
                             cache still holds "old"       cache gets put "new"

If T2 = exceptional completion: no new successful value to put.
~~~

**Do not merge T1 and T2 into one.** Reaching the end of the method body does not equate to business success if the returned result is still pending. Moreover, future completion does not by default equal **database transaction commit** or completion of all side effects in external systems.

## 2. `@CachePut` with Asynchronous Results

`@CachePut` differs from `@Cacheable`: it requires executing the method and, when the caching operation applies, puts the appropriate result into the cache. It **does not skip** the method body just because an entry with the same key already exists.

### 2.1. Success After Future Completion

~~~java
@CachePut(cacheNames = "documents", key = "#p0")
public CompletableFuture<String> update(String id) {
    return serviceClient.updateAsync(id);
}
~~~

Suppose `documents["D1"] = "old"`:

~~~text
Before call                cache["D1"] = "old"
Method returns PENDING     cache["D1"] still = "old"
Future success("new")      Spring handles putting value "new"
After completion           cache["D1"] = "new"
~~~

With async-aware support, the value placed into the cache is the **completed business value**, rather than the annotation trying to store an unfinished `CompletableFuture` as if it were a `String`.

### 2.2. If the Future Fails

~~~text
T0: cache["D1"] = "old"
T1: update("D1") returns incomplete future
T2: future.completeExceptionally(error)
    → no new successful value
    → cache still holds "old" in a single-writer scenario
~~~

In the error case, the caller must still handle the failed future. Distinguish **not putting due to an error** from another concurrent request having modified the same cache key.

### 2.3. `unless` and `#result`

~~~java
@CachePut(
    cacheNames = "documents",
    key = "#p0",
    unless = "#result == null")
public CompletableFuture<String> update(String id) {
    return serviceClient.updateAsync(id);
}
~~~

`unless` is a condition evaluated after a result is obtained; when Spring properly adapts the future, `#result` can reflect the **completed value** to decide whether to skip the put. `condition` typically uses arguments to decide whether to perform the cache operation at all. If the future completes successfully with `null`, the `unless` policy and the backend's cached-null capability decide whether a new entry is stored.

Do not treat an exception or canceled future as a normal `#result` to cache. The snippet above is illustrative only, not a standalone Java file.

## 3. `@CacheEvict`: After Success or Before Calling the Method?

### 3.1. Default: `afterInvocation`

~~~java
@CacheEvict(cacheNames = "documents", key = "#p0")
public CompletableFuture<Void> delete(String id) {
    return serviceClient.deleteAsync(id);
}
~~~

The default is `beforeInvocation = false`. For Spring-supported asynchronous results, after-invocation eviction attaches to **successful completion**, not merely returning the future.

~~~text
Initial cache                documents["D1"] = "old"
Method returns pending       documents["D1"] = "old"

If future complete(null) succeeds:
  → evict key D1
  → documents["D1"] absent

If future completeExceptionally(error):
  → do not perform post-success eviction
  → "old" entry retained (assuming no other writer)
~~~

A `CompletableFuture<Void>` **completing successfully with null** is still a success. Do not confuse `Void`'s `null` with an exception or cancellation.

### 3.2. `beforeInvocation=true`

~~~java
@CacheEvict(
    cacheNames = "documents",
    key = "#p0",
    beforeInvocation = true)
public CompletableFuture<Void> delete(String id) {
    return serviceClient.deleteAsync(id);
}
~~~

In this mode, the cache interceptor issues the `evict` command **before the method is invoked**:

~~~text
T0: cache["D1"] = "old"
T1: call delete("D1") via proxy
    → issue evict("D1") before running method
T2: method returns PENDING future; entry already requested to be removed
T3: future FAILS; pre-invocation eviction does NOT auto-rollback
~~~

This is an intentional choice when you want to proactively stop serving stale data from the very start of the operation, regardless of outcome. It can cause cache misses and reloads even if the update/delete ultimately fails.

**Transaction exception:** if the underlying Spring `Cache` is wrapped by `TransactionAwareCacheManagerProxy` or a transaction-aware decorator, the `evict` command is *issued* before invocation yet **may actually execute after transaction commit**. `beforeInvocation` only specifies ordering relative to the method call; it does not override the deferral policy of a cache decorator.

### 3.3. Timeline Comparison Table

| Annotation | Method returns incomplete future | Future success | Future exceptional/cancel |
| --- | --- | --- | --- |
| `@CachePut` | No completed value to put yet | Puts actual result if conditions allow | Does not put failed result |
| Default `@CacheEvict` | Keeps entry while pending | Evicts entry/region per config | Does not perform post-success eviction |
| `@CacheEvict(beforeInvocation=true)` | Already issued evict before method starts | Does not need to wait to evict | Early eviction is not auto-restored |
| `@Cacheable` (for comparison) | Lookup/miss/hit per provider | Can cache completed value | No successful value to write |

The table describes **Spring Framework 6.1+** with supported return types and without a deferred transaction adapter; older versions or other providers may have different semantics.

## 4. Versions, Return Types, and Providers

Spring Framework 6.1 extends cache annotation adaptation to `CompletableFuture` and Reactor types. To apply this lesson, verify:

- **Version:** Spring Framework 6.1+ (for instance Spring Boot 3.2+ with compatible configuration). Java 17 alone does not bring async-aware annotation capabilities.
- **Return type:** `CompletableFuture<T>` is supported; do not assume arbitrary custom `java.util.concurrent.Future<T>` types or any callback library are treated identically.
- **Provider:** the manager must supply the named region and support operations executed by the caching infrastructure. For async `@Cacheable`/`Cache.retrieve` or reactive caching, the provider's async retrieval capability is especially critical.
- **Proxy:** `@EnableCaching` is enabled and the method is called through a Spring-managed proxy. `this.method()` calls typically bypass cache advice in proxy mode.
- **Completion:** success, failure, cancel, null, timeout, and empty reactive publishers are distinct cases that must be tested separately.

The example uses `ConcurrentMapCacheManager` to test `put/evict`. For Caffeine, Redis, or JCache, run integration tests against the real backend. TTL, durability, and cross-replica synchronization are **not** defined by `@CachePut` or `@CacheEvict`.

## 5. Java 17+ Demo: Verifying Exact Timing with a Manually Controlled `CompletableFuture`

This is a Java 17+ Spring Boot example **without a real database**. Futures are created by a controllable bean, allowing cache checks before/after success and failure without relying on `Thread.sleep`, thread schedulers, or the network. Use a Spring Boot Gradle project with a compatible Spring 6.1+ plugin/version, adding the dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
}
~~~

The four Java files below belong to package `example.asyncresultcache`.

### 5.1. `PendingSignals.java`

Placed at `src/main/java/example/asyncresultcache/PendingSignals.java`:

~~~java
package example.asyncresultcache;

import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Component;

@Component
public class PendingSignals {
    private CompletableFuture<String> pendingWrite;
    private CompletableFuture<Void> pendingDelete;
    private CompletableFuture<Void> pendingEarlyDelete;

    public CompletableFuture<String> beginWrite() {
        pendingWrite = new CompletableFuture<>();
        return pendingWrite;
    }

    public void succeedWrite(String value) {
        pendingWrite.complete(value);
    }

    public void failWrite() {
        pendingWrite.completeExceptionally(
                new IllegalStateException("write failed"));
    }

    public CompletableFuture<Void> beginDelete() {
        pendingDelete = new CompletableFuture<>();
        return pendingDelete;
    }

    public void succeedDelete() {
        pendingDelete.complete(null);
    }

    public void failDelete() {
        pendingDelete.completeExceptionally(
                new IllegalStateException("delete failed"));
    }

    public CompletableFuture<Void> beginEarlyDelete() {
        pendingEarlyDelete = new CompletableFuture<>();
        return pendingEarlyDelete;
    }

    public void failEarlyDelete() {
        pendingEarlyDelete.completeExceptionally(
                new IllegalStateException("early delete failed"));
    }
}
~~~

This bean is **for sequential demo use only**: it holds only one pending future at a time per operation type. Do not use global pending fields like these in production with concurrent requests.

### 5.2. `AsyncDocumentService.java`

Placed at `src/main/java/example/asyncresultcache/AsyncDocumentService.java`:

~~~java
package example.asyncresultcache;

import java.util.concurrent.CompletableFuture;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.stereotype.Service;

@Service
public class AsyncDocumentService {
    private final PendingSignals signals;

    public AsyncDocumentService(PendingSignals signals) {
        this.signals = signals;
    }

    @CachePut(cacheNames = "documents", key = "#p0")
    public CompletableFuture<String> update(String id) {
        return signals.beginWrite();
    }

    @CacheEvict(cacheNames = "documents", key = "#p0")
    public CompletableFuture<Void> delete(String id) {
        return signals.beginDelete();
    }

    @CacheEvict(
            cacheNames = "documents",
            key = "#p0",
            beforeInvocation = true)
    public CompletableFuture<Void> deleteBefore(String id) {
        return signals.beginEarlyDelete();
    }
}
~~~

The methods are `public`, on a Spring bean, and invoked from another bean in the demo, so the AOP caching interceptor can apply. `key = "#p0"` builds the key from the first parameter, matching the `"D1"` key we manually put into the cache.

### 5.3. `CacheConfiguration.java`

Placed at `src/main/java/example/asyncresultcache/CacheConfiguration.java`:

~~~java
package example.asyncresultcache;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("documents");
    }
}
~~~

`@EnableCaching` is needed for annotation processing; it does not automatically provide TTL, distributed caching, or database transactions. The demo uses a single cache region named `documents`, stored in the JVM.

### 5.4. `AsyncCacheDemoApplication.java`

Placed at `src/main/java/example/asyncresultcache/AsyncCacheDemoApplication.java`:

~~~java
package example.asyncresultcache;

import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class AsyncCacheDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AsyncCacheDemoApplication.class, args);
    }

    private static void expectFailure(CompletableFuture<?> future) {
        try {
            future.join();
            throw new AssertionError("Expected exceptional completion");
        } catch (CompletionException expected) {
            // Exception has been observed.
        }
    }

    @Bean
    CommandLineRunner demo(
            AsyncDocumentService service,
            PendingSignals signals,
            CacheManager manager) {

        return args -> {
            Cache cache = Objects.requireNonNull(
                    manager.getCache("documents"),
                    "documents cache missing");

            // 1) @CachePut: while not completed, cache remains "old".
            cache.put("D1", "old");
            CompletableFuture<String> pendingPut =
                    service.update("D1");
            System.out.println("put future pending = " +
                    !pendingPut.isDone());
            System.out.println("put before success = " +
                    cache.get("D1", String.class));
            signals.succeedWrite("new");
            pendingPut.join();
            System.out.println("put after success = " +
                    cache.get("D1", String.class));

            // 2) Failed update future: no value to put.
            CompletableFuture<String> failedPut = service.update("D1");
            signals.failWrite();
            expectFailure(failedPut);
            System.out.println("put after failure = " +
                    cache.get("D1", String.class));

            // 3) @CacheEvict after-invocation waits for completion.
            CompletableFuture<Void> pendingDelete =
                    service.delete("D1");
            System.out.println("evict before success = " +
                    cache.get("D1", String.class));
            signals.succeedDelete();
            pendingDelete.join();
            System.out.println("evict after success = " +
                    cache.get("D1", String.class));

            // 4) Failed delete future: old entry is retained.
            cache.put("D1", "seed");
            CompletableFuture<Void> failedDelete = service.delete("D1");
            signals.failDelete();
            expectFailure(failedDelete);
            System.out.println("evict after failure = " +
                    cache.get("D1", String.class));

            // 5) Evict before invocation: already removed while pending.
            CompletableFuture<Void> early = service.deleteBefore("D1");
            System.out.println("early evict pending = " +
                    cache.get("D1", String.class));
            signals.failEarlyDelete();
            expectFailure(early);
            System.out.println("early evict after failure = " +
                    cache.get("D1", String.class));
        };
    }
}
~~~

Run in the project directory:

~~~bash
./gradlew bootRun
# Windows PowerShell: .\gradlew.bat bootRun
~~~

**Lines printed by the program via `System.out`, in order** (excluding Spring Boot/Gradle logs):

~~~text
put future pending = true
put before success = old
put after success = new
put after failure = new
evict before success = new
evict after success = null
evict after failure = seed
early evict pending = null
early evict after failure = null
~~~

**Exact milestone analysis:**

1. `pendingPut` has not completed yet, so `!pendingPut.isDone()` is true. While Spring watches the future, the cache stays `old` instead of immediately containing `new`.
2. `signals.succeedWrite("new")` completes the future successfully. The cache operation updates `documents["D1"]` to `new`; `pendingPut.join()` ensures the result path has finished when inspected.
3. `failedPut` completes exceptionally, so no additional put occurs; the cache remains `new`. The demo uses `expectFailure` to observe the failed outcome without crashing the application.
4. `service.delete("D1")` with the default annotation returns an incomplete future; the cache remains `new`. After `succeedDelete()`, the future completes successfully with null (since `Void`), so the entry is evicted; `cache.get("D1", String.class)` returns `null`.
5. For the failed delete, the cache is seeded with `seed` before calling. Future failure prevents after-invocation eviction from happening, so `seed` remains.
6. With `deleteBefore`, the cache is evicted as soon as the method is called through the proxy. While the future is still pending, reading already sees `null`. Exceptional completion later **does not restore** the entry.

The strength of this example is zero dependence on real delays. It proves completion timing, **not** transaction commit or actual effects on a DB/remote system. If run on an older Spring version, expected output may differ; that is precisely why version verification matters.

## 6. Failed, Canceled, and Null-Returning `CompletableFuture`

### Exceptional Completion

~~~java
CompletableFuture<String> pending = new CompletableFuture<>();
pending.completeExceptionally(
        new IllegalStateException("remote write failed"));
~~~

The method may still have **returned a future normally**, yet the future later fails. Callers may observe `CompletionException` on `join()`, or handle via `handle`/`whenComplete`. `@CachePut` has no successful business result to write, and after-invocation `@CacheEvict` has no successful completion to evict. However, the remote service might **have already committed before timing out**; a failure signal does not guarantee the database remained unchanged.

### Cancellation

~~~java
CompletableFuture<String> pending = new CompletableFuture<>();
pending.cancel(true);
~~~

Cancellation is an abnormal completion and should not be treated as a "successful update" to put or evict after invocation. Yet canceling a future handle **does not necessarily** stop actual I/O. If remote side effects occurred despite caller cancellation, the system must reconcile the cache with the source.

### Null and `CompletableFuture<Void>`

`CompletableFuture<Void>` succeeding with `complete(null)` is a normal completion, suitable for after-invocation `@CacheEvict` to perform eviction. With `@CachePut`, a `CompletableFuture<String>` with value `null` is a normal success, though whether null is written depends on `unless` and the cache provider's cached-null support. Do not confuse **no value** with **exception**.

### Futures That Never Complete

If a future hangs, post-success operations never reach a trigger point either. Configure timeouts/circuit breakers, monitor pending future counts, and avoid retaining closures/contexts indefinitely. Do not use caching annotations to manage the lifecycle of remote I/O.

## 7. Reactive: `Mono`/`Flux` Are Not Like Plain Java Method Returns

Spring Framework 6.1+ can also adapt to common reactive types when Reactor is present:

- `Mono<T>` represents zero or one value. A Java method returning `Mono` usually only constructs a **lazy** publisher; the actual value appears in the pipeline when subscribed to.
- `Flux<T>` can emit multiple items. Spring's Cache abstraction can collect emitted items into a list to cache as **one aggregate**, rather than creating a separate entry for each `onNext`.
- `@CachePut` on a reactive return must evaluate the **materialized result/pipeline**, rather than assuming returning a publisher equals a successful cache write.
- Supported reactive after-invocation `@CacheEvict` attaches to a **successful terminal signal**, not publisher creation.
- `Mono.empty()` and `Flux.empty()` are successful completions **with zero items**, distinct from `onError`. Test empty/null policy and provider behavior separately.
- Subscription cancellation does not prove remote side effects were rolled back.

~~~java
// Reactor illustration; requires Reactor dependency and a real remoteClient.
@CachePut(cacheNames = "documents", key = "#p0")
public reactor.core.publisher.Mono<String> updateReactive(String id) {
    return remoteClient.update(id);
}

@CacheEvict(cacheNames = "documents", key = "#p0")
public reactor.core.publisher.Mono<Void> deleteReactive(String id) {
    return remoteClient.delete(id);
}
~~~

This code is **not part of the demo project in Section 5** and is not standalone Java. For large or infinite streams, do not use automatic `Flux`-to-list caching without considering memory/backpressure.

With backends providing asynchronous retrieval, such as `CaffeineCacheManager.setAsyncCacheMode(true)` where appropriate, Spring can coordinate `@Cacheable`/`Cache.retrieve` read paths better. This lesson's demo focuses on **put/evict after completion**, so it uses a simple manager to isolate that behavior.

## 8. `@Async`, AOP Proxies, and `@Transactional`

### 8.1. `@Async` Changes Threads, Not Completion Checks

~~~java
@Async
@CachePut(cacheNames = "documents", key = "#p0")
public CompletableFuture<String> update(String id) {
    String updated = repository.writeAndReturn(id);
    return CompletableFuture.completedFuture(updated);
}
~~~

This is illustrative code requiring `@EnableAsync`, a bean, and a real `repository`. `@Async` can shift execution onto another executor; the caller sees an outer future, and cache advice may run in a different interceptor order than expected unless tested. Do not assume that because the method body returns a completed future, the caller receives final completion immediately.

- `@EnableCaching` and `@EnableAsync` are two separate configurations.
- Calls must go through the Spring proxy; `this.update(...)` inside the same bean typically bypasses proxy mode.
- A future may complete on a worker thread, while the cache completion callback may also run on that thread; do not rely on thread-local context without checking.
- Test actual timing with the deployed executor/configuration, not just the happy path in isolation.

### 8.2. `TransactionAwareCacheManagerProxy` Is Not an Async Adapter

| Aspect | Async-aware cache annotation | Transaction-aware cache decorator |
| --- | --- | --- |
| Primary event | Future/reactive result completes successfully | Spring transaction commits successfully |
| Goal | Act based on async task outcome | Defer `put`, `evict`, `clear` until `afterCommit` |
| Does not guarantee | Whether DB has committed yet | Whether async operation has completed yet |
| When future runs on another thread | Callback may run outside transaction context | Thread-bound transaction synchronization does not auto-propagate to callbacks |
| Is it a distributed transaction? | No | No |

`@Transactional` on a future-returning method may commit the transaction scoped to the **method invocation**, while the future completes later. Do not assume future return success and database commit are the same milestone. When combining async caching with `TransactionAwareCacheManagerProxy`, final timing also depends on AOP ordering, thread completion, and whether transaction synchronization exists when the cache operation runs.

If strong consistency is required, design after-commit events, outbox patterns, or versioned keys; do not merely stack annotations assuming atomic DB+cache behavior.

## 9. Race Conditions That Correct Timing Still Doesn't Solve

### 9.1. Out-of-Order Put Completion

~~~text
T0: Future A starts updating the same key K (older result A)
T1: Future B starts updating key K (newer result B)
T2: Future B succeeds → @CachePut writes B
T3: Future A succeeds → @CachePut writes A
Result: cache holds A (stale) even though future A finished last.
~~~

`@CachePut` does not arbitrate which version/update is newest. Use versioned records, optimistic locking with version comparison, or serialize writers per key when required by the domain.

### 9.2. Evict Followed by Another Request Reloading Stale Data

A `@Cacheable` request may start loading from an old source before commit and stay pending. The update future completes and eviction removes the key, yet the older loader finishes after eviction and puts stale data into the cache. This is a race between **invalidation** and **repopulation**. Handle it with version-aware keys, locking, or an appropriate consistency model.

### 9.3. Local Cache Does Not Sync Across a Cluster

`ConcurrentMapCacheManager`/local Caffeine in JVM A does not automatically evict JVM B. After successful completion on A, a request on B can still observe a stale entry. TTL is an age limit, not a broadcast invalidation. With Redis/shared caches, you must still account for network errors and transaction/provider semantics.

### 9.4. Mutable Cache Values

If the completed value is a mutable Java object and the backend stores by reference, callers can mutate the shared entry. Future completion only determines **when to put**, not immutability of the data. Prefer immutable DTOs and defensive copies.

## 10. Common Mistakes

1. **Confusing method return with future success:** leads to premature eviction/put or tests that fail to verify pending state.
2. **Setting `beforeInvocation=true` while expecting to keep cache on delete failure:** this evicts before the method, with no automatic rollback.
3. **Using an older Spring version while applying Spring 6.1+ assumptions:** check the dependency tree/runtime version.
4. **Calling `cache.put(key, future)` manually and expecting annotation semantics:** imperative put is not automatically equivalent to future-aware `@CachePut`.
5. **Thinking `@CachePut` is a cache lookup:** it executes the method and uses the result to update, never skipping on a hit.
6. **Forgetting `@EnableCaching` or using self-invocation:** the caching interceptor does not run as expected.
7. **Testing only `CompletableFuture.completedFuture(...)`:** fails to observe pre-completion state; test incomplete futures too.
8. **Ignoring exceptions/cancellation:** failed futures are not successful completions, yet source side effects may still have occurred.
9. **Confusing `Mono.empty()` with `onError`:** successful empty and failure have different semantics.
10. **Believing `@Async` automatically propagates transactions to completion callbacks:** check thread context and transaction boundaries.
11. **Ignoring multiple futures for the same key:** out-of-order completion can overwrite the cache with stale values.
12. **Not bounding timeouts/pending tasks:** hanging tasks can prevent expected cache updates/evictions.
13. **Inconsistent keys and tenants:** cache hits can return wrong data; never put authorization checks solely inside a loader skipped on hits.

## 11. Exercises and Testing

| Scenario | Action | Expected Observation |
| --- | --- | --- |
| `@CachePut` pending | Return incomplete `CompletableFuture` | Cache still holds old value |
| Put success | Complete with `"new"` | Cache contains `"new"` |
| Put failure | Complete exceptionally | Old entry not replaced by failed result |
| `@CacheEvict` pending | Return incomplete future | Key still has entry |
| Evict success | Complete `CompletableFuture<Void>` with null | Key is evicted |
| Evict failure | Complete exceptionally | Old entry remains in sequential scenario |
| Early eviction | `beforeInvocation=true` | Eviction issued before method runs |
| Early evict + future fail | Exception after method return | No default cache undo |
| Null put result | Complete successfully with null | Check `unless` and null policy |
| Reactive empty/error | `Mono.empty()`/`Mono.error(...)` | Test successful terminal vs failure |
| Multi-writer | Two futures complete out of order | Analyze stale overwrite and guard with version |
| Transaction | Combine DB commit and async completion | Identify two distinct milestones, test `afterCommit` |
| Multi-instance | Two JVMs with local caches | Evict on A does not auto-sync to B |

**Pre-production checklist:** verify Spring version; configure `CacheManager`/proxy; test pending, success, exceptional, cancel, and null states; choose `beforeInvocation` intentionally; separate cache operations from DB commit; handle races, versions, and multiple replicas; observe timeouts and failures; never assume future completion is an atomic transaction.

## Official Documentation

- Spring Framework — Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — `CachePut` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CachePut.html
- Spring Framework — `CacheEvict` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CacheEvict.html
- Spring Framework — Cache abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Proxying mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — TransactionAwareCacheManagerProxy: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html