# TransactionAwareCacheDecorator and Post-Commit Operations in Spring Cache

## 1. What Problem Does This Lesson Solve?

In Spring Framework, a method updating the data source and a call to `Cache.put`, `Cache.evict`, or `Cache.clear` are **operations against two separate state systems**. If the database transaction has not yet committed while the cache is already updated, other requests can observe a version that does not match the actually committed data.

Classic example:

1. Transaction T1 updates a product price from `100` to `120` but **has not committed**.
2. Spring deletes cache entry `products[42]` immediately.
3. Request T2 misses the cache, reads the database under standard isolation, and still sees price `100`.
4. T2 writes `100` back into the cache.
5. T1 commits `120`; the cache now holds `100` again and can be stale.

One coordination approach is to **defer deferrable cache changes until after the database transaction commits successfully**. Spring supports this via:

- `org.springframework.cache.transaction.TransactionAwareCacheDecorator`: wraps **an existing Spring `Cache`**.
- `org.springframework.cache.transaction.TransactionAwareCacheManagerProxy`: wraps **a Spring `CacheManager`**, so retrieved `Cache` instances exhibit transaction-aware behavior.
- Some `CacheManager` implementations extending `AbstractTransactionSupportingCacheManager`, which can support similar behavior through that manager's own `transactionAware` configuration.

Point to remember: the decorator **does not turn the cache into an ACID participant of the database transaction**. It uses **transaction synchronization callbacks** to execute `put`/`evict`/`clear` only when Spring signals the transaction has committed. This is lifecycle coordination, not two-phase commit; it provides neither a transaction-local cache view nor automatic rollback of an already-executed cache write.

Within the **Transactions** group, this lesson clarifies the lifecycle, post-commit policy, pre-commit/rollback behavior, proper manager configuration, advice ordering risks, and testing with Java 17+.

## 2. Exact Role of `TransactionAwareCacheDecorator`

Spring's Javadoc describes `TransactionAwareCacheDecorator` as a `Cache` decorator that takes a `Cache targetCache` and **delegates reads**, while synchronizing three state-mutating operations with Spring-managed transactions:

| Operation via decorated Cache | If suitable transaction synchronization is active | If no transaction synchronization is active |
| --- | --- | --- |
| `put(key, value)` | Registers callback; actual cache put runs in `afterCommit` | Delegates immediately to native cache |
| `evict(key)` | Registers callback; actual evict runs in `afterCommit` | Delegates immediately |
| `clear()` | Registers callback; actual clear runs in `afterCommit` | Delegates immediately |
| `get(key)` | Reads live cache, **does not read pending puts/evicts** | Reads live cache |
| `putIfAbsent(key, value)` | **Immediate**, not deferred like `put` | Immediate per backend capability |
| `evictIfPresent(key)` | **Immediate**, not deferred like `evict` | Immediate per backend capability |
| `invalidate()` | **Immediate**, not deferred like `clear` | Immediate per backend capability |

The implementation uses `TransactionSynchronizationManager`. At the implementation level, the critical check is **whether transaction synchronization is currently active**, not merely whether `@Transactional` appears in source code. A transaction manager may enable synchronization under certain propagation modes; therefore, never infer callback timing merely by looking at a method signature.

### Distinguishing Request From Effect

With a decorated `Cache`:

~~~java
cache.put("p:42", "new");
System.out.println(cache.get("p:42"));
~~~

This is a snippet, not a standalone file. If the code runs inside a synchronized Spring transaction and the key did not exist beforehand, `cache.get("p:42")` right after `put` may still return `null` (miss). The put command has only **been scheduled for after-commit**; the decorator does not create a temporary record for the transaction itself to read.

Similarly, if the key currently stores `old` and `cache.evict(key)` is called inside a transaction, `cache.get(key)` before commit **may still hit `old`**. Do not treat this as a Spring bug: it is the intentional consequence of a deferred operation.

## 3. Commit Timeline: DB Update, Cache Registration, and Callback

~~~mermaid
sequenceDiagram
    participant Client as Caller
    participant Tx as Transaction Manager
    participant Service as Business Service
    participant Decorator as TransactionAwareCacheDecorator
    participant DB as Database
    participant Cache as Native Cache

    Client->>Tx: begin transaction
    Tx->>Service: invoke updateProduct()
    Service->>DB: update product
    Service->>Decorator: evict(productKey)
    Decorator->>Tx: register afterCommit synchronization
    Decorator-->>Service: return (eviction has not run)
    Service-->>Tx: business method returns
    Tx->>DB: commit transaction
    alt commit succeeds
        Tx->>Decorator: afterCommit()
        Decorator->>Cache: evict(productKey)
        Cache-->>Decorator: applied
        Tx-->>Client: transaction finished
    else commit/transaction fails
        Tx-->>Client: rollback / exception
        Note over Cache: afterCommit callback is not executed
    end
~~~

This diagram illustrates the idea; it is **not a guarantee** that every `@Transactional` + `@CacheEvict` produces this exact sequence. When caching and transaction advices reside on different proxy layers, `@CacheEvict` can issue its command after the transaction interceptor has finished. At that moment synchronization is no longer active, and the decorator may execute eviction immediately. The **advice ordering** section (Section 10) is crucial.

### Timestamps to Distinguish

- **Before invocation:** `@CacheEvict(beforeInvocation=true)` requests eviction before invoking the business method.
- **After invocation:** `@CacheEvict(beforeInvocation=false)` requests eviction when the business method finishes normally.
- **After commit:** `TransactionAwareCacheDecorator` executes the native cache command in `afterCommit` if valid synchronization was registered.

**"After invocation" is not equal to "after commit".** They are two different moments belonging to two different mechanisms. Likewise, "called `cache.evict`" should not be read as "entry was physically deleted".

## 4. The Three Deferrable Operations: `put`, `evict`, and `clear`

### 4.1. `put(key, value)`

`Cache.put` inserts or replaces an entry. With a transaction-aware decorator and active synchronization, the native put is deferred until after-commit.

~~~java
cache.put("product:42", newProduct);
~~~

This is a snippet with a decorated `cache` where `newProduct` is a business DTO. Notable points:

- If the transaction rolls back, the registered put command **does not run**.
- `cache.get("product:42")` before commit may still see the **old** DTO or miss.
- The `newProduct` object reference is retained for the callback to use. Avoid mutating objects that might change while waiting for commit; prefer immutable DTOs or appropriate copies.
- A transaction may issue **multiple put commands** for the same key. Native operation results and ordering should be verified with integration tests; do not use this mechanism as a transactional write buffer with DB-grade coalescing or isolation.
- When the put callback errors **after the DB has committed**, the cache error cannot automatically roll back the DB. Consistency must be handled according to system policy.

### 4.2. `evict(key)`

`Cache.evict` requests removal of a key. Only after a successful commit does the native cache receive the deletion command:

~~~java
cache.evict("product:42");
~~~

The main benefit is limiting cases where another reader **misses and reloads old DB data** before commit. Still, a post-commit evict does not eliminate every race: an older loader that started earlier can finish late and write a stale value back. When data demands strong consistency, combine with versioned keys, invalidation events, loader coordination, or TTLs.

### 4.3. `clear()`

`Cache.clear` deletes the entire selected cache region:

~~~java
cache.clear();
~~~

In a transaction-aware decorator, `clear` is deferred until after-commit. This avoids wiping a large region for a change that rolled back, yet it still carries a cost: a **cache stampede** when many requests miss after commit, spiking DB load and cold-cache latency. Pinpoint exact cache names/tenant scopes and avoid clearing the entire cache just because one key changed.

### Deferrable Commands Do Not Mean Never Effective

If no synchronization is active, the decorator **delegates immediately** to `targetCache`. Afterward, how immediately it takes physical effect still depends on the native implementation (e.g., remote cache/asynchronous writes). The decorator does not enforce an after-commit wait layer when there is no synchronization cycle to register with.

## 5. Rollback: The `afterCommit` Callback Does Not Run

When a transaction rolls back, `afterCommit` **is not called**. Effect on the three registered operations:

| Operation requested in transaction | When commit succeeds | When rolled back |
| --- | --- | --- |
| `put("x", newValue)` | Dispatched to cache after commit | Registered put command is not dispatched |
| `evict("x")` | Dispatched to cache after commit | Registered evict command is not dispatched |
| `clear()` | Dispatched to cache after commit | Does not clear via that callback |

This keeps the cache compatible with the database **provided** the business changes also genuinely rolled back with the transaction. However, do not conclude that an exception guarantees the DB did not change: resources outside the transaction (HTTP, message brokers, files, another DB, or a `REQUIRES_NEW` transaction) may have committed independently.

### Three Completion Outcomes to Test

1. **Normal return + commit succeeds:** deferred commands execute.
2. **Method throws exception and transaction rolls back:** deferred commands do not run, if registered before the exception.
3. **Method returns normally but outer transaction is marked rollback-only:** after-commit still does not run; caller may receive `UnexpectedRollbackException` depending on the situation.

Therefore, **the decisive milestone is the actual commit outcome**, not merely whether the method returned or reached a `cache.evict` line in code.

## 6. No Read-Your-Writes and No Transaction-Local Cache View

A common misconception: "Using transaction-aware means inside the transaction you can read the new values pending put."

False. The decorator performs `get` against the target cache; it **does not provide a staging table of pending changes** like a JPA persistence context.

| Situation | Inside transaction, before commit | After commit (no other writers) |
| --- | --- | --- |
| Empty key, call `put(K, "v2")` | `get(K)` may still miss | `get(K)` hits `v2` |
| Key is `v1`, call `put(K, "v2")` | `get(K)` may still return `v1` | `get(K)` hits `v2` |
| Key is `v1`, call `evict(K)` | `get(K)` may still return `v1` | `get(K)` misses |
| Cache has entries, call `clear()` | May still see old entries | Entries are cleared |

When a business method needs to read data it just updated **within the same DB transaction**, read through the repository/persistence context with suitable isolation rather than relying on the decorated cache to reflect uncommitted state.

Additionally, `Cache.get(Object)` distinguishes a cache miss (`ValueWrapper` is null) from a hit containing null (`ValueWrapper` is non-null while `get()` returns null). This matters when writing tests verifying deferred put/evict; typed `Cache.get(key, Type.class)` does not distinguish these two cases.

## 7. Configuring a Single `Cache` Directly vs. Wrapping the Whole `CacheManager`

### 7.1. Wrapping One `Cache`

~~~java
Cache nativeCache = new ConcurrentMapCache("products");
Cache transactionAware = new TransactionAwareCacheDecorator(nativeCache);
~~~

This snippet requires importing `org.springframework.cache.Cache`, `ConcurrentMapCache`, and `TransactionAwareCacheDecorator`. It fits when you use `Cache` directly via the programmatic API, or want to test the lifecycle on a single cache.

`transactionAware.getTargetCache()` grants access to the target cache for testing/diagnostics, but business code **should not use the target native cache for writes/deletes** if it wants after-commit guarantees. A direct `nativeCache.evict` call bypasses the decorator and does not defer.

### 7.2. Wrapping the Entire `CacheManager`

~~~java
@Bean
org.springframework.cache.CacheManager cacheManager() {
    ConcurrentMapCacheManager nativeManager =
            new ConcurrentMapCacheManager("products", "priceBySku");
    return new TransactionAwareCacheManagerProxy(nativeManager);
}
~~~

This is a snippet inside a `@Configuration` class. The manager proxy returns decorated `Cache` instances whenever Spring annotations or code call `getCache(name)`. That keeps all `@Cacheable`/`@CachePut`/`@CacheEvict` operations under **the same policy**, instead of some methods using a wrapped cache and others using a raw cache.

If multiple Spring `CacheManager` beans exist, explicitly identify the manager used by caching advice—for example via `CachingConfigurer` or the annotation's `cacheManager` attribute. Identical class names do not guarantee the right bean.

### 7.3. `CacheManager` With Built-In Transaction-Aware Support

Some Spring managers extend `AbstractTransactionSupportingCacheManager` and provide their own transaction-awareness configuration. For these managers, check the Javadoc for `setTransactionAware(true)` along with the manager lifecycle. Avoid double-wrapping with a decorator/proxy or accidentally referencing another raw bean; doing so makes the policy harder to observe and can cause duplicate callbacks.

**Spring Boot configuration:** do not assume merely from having `spring-boot-starter-cache` that the cache manager is automatically transaction-aware. Inspect the actual bean, customizers, provider, and Boot version. No single universal flag replaces checking which `CacheManager` is being injected.

## 8. Standalone Java 17+ Example With Transaction Synchronization

To observe after-commit **without needing an external database**, the following example uses:

- Spring Framework 6.2.14.
- `ConcurrentMapCache` as an in-memory native cache.
- `TransactionAwareCacheDecorator` wrapping that cache.
- `TransactionTemplate` to drive commit/rollback branches.
- A small subclass of `AbstractPlatformTransactionManager` strictly for **lifecycle simulation**.

The simulated transaction manager **does not perform database transactions**. It merely lets Spring fire transaction synchronization callbacks for demonstration. Never use this manager class in production; when you need to prove DB consistency, use `DataSourceTransactionManager`/`JpaTransactionManager` and a real DB.

### 8.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>transaction-aware-cache-demo</artifactId>
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

### 8.2. src/main/java/demo/TransactionAwareCacheDemo.java

~~~java
package demo;

import org.springframework.cache.Cache;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.cache.transaction.TransactionAwareCacheDecorator;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;
import org.springframework.transaction.support.DefaultTransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;

public final class TransactionAwareCacheDemo {
    private TransactionAwareCacheDemo() { }

    // Creates only the Spring transaction synchronization lifecycle.
    // Does not manage DB, connections, locks, or real data commits.
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
        Cache nativeCache = new ConcurrentMapCache("products");
        Cache cache = new TransactionAwareCacheDecorator(nativeCache);
        TransactionTemplate tx =
                new TransactionTemplate(new DemoTransactionManager());

        nativeCache.put("a", "v1");
        tx.execute(status -> {
            cache.evict("a");
            System.out.println("before commit evict=" + lookup(cache, "a"));
            return null;
        });
        System.out.println("after commit evict=" + lookup(cache, "a"));

        tx.execute(status -> {
            cache.put("b", "v2");
            System.out.println("before commit put=" + lookup(cache, "b"));
            return null;
        });
        System.out.println("after commit put=" + lookup(cache, "b"));

        nativeCache.put("c", "v3");
        tx.execute(status -> {
            cache.clear();
            System.out.println("before commit clear=" + lookup(cache, "c"));
            return null;
        });
        System.out.println("after commit clear=" + lookup(cache, "c"));

        nativeCache.put("d", "v4");
        tx.execute(status -> {
            cache.evict("d");
            status.setRollbackOnly();
            System.out.println("inside rollback=" + lookup(cache, "d"));
            return null;
        });
        System.out.println("after rollback=" + lookup(cache, "d"));

        nativeCache.put("e", "v5");
        tx.execute(status -> {
            boolean existed = cache.evictIfPresent("e");
            System.out.println("immediate existed=" + existed);
            System.out.println("immediate inside=" + lookup(cache, "e"));
            status.setRollbackOnly();
            return null;
        });
        System.out.println("immediate after rollback=" + lookup(cache, "e"));

        cache.put("outside", "v6");
        System.out.println("without transaction=" + lookup(cache, "outside"));
    }
}
~~~

### 8.3. Running the Program

From the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.TransactionAwareCacheDemo
~~~

### 8.4. Expected Stdout

Ignoring Maven/Spring logs (if any), the lines printed by the program in order:

~~~text
before commit evict=v1
after commit evict=MISS
before commit put=MISS
after commit put=v2
before commit clear=v3
after commit clear=MISS
inside rollback=v4
after rollback=v4
immediate existed=true
immediate inside=MISS
immediate after rollback=MISS
without transaction=v6
~~~

Explanation:

1. `evict("a")` is deferred; inside the transaction it is still `v1`; after commit entry `a` is deleted.
2. `put("b","v2")` is deferred; inside the transaction `b` still misses; after commit the cache holds `v2`.
3. `clear()` is deferred; `c` remains visible before commit, and misses after commit.
4. `evict("d")` is registered, yet the transaction is marked rollback-only; the after-commit callback does not run, so `d=v4` persists.
5. `evictIfPresent("e")` is an immediate operation; it removes `e` immediately, returning `true` because the key existed; **subsequent rollback does not restore the entry**.
6. `put("outside","v6")` is called with no active transaction synchronization, so it delegates immediately to the in-RAM cache.

**What the example proves:** the behavior of `TransactionAwareCacheDecorator` with Spring transaction synchronization and a local cache. **What the example does not prove:** database rollback, advice order in a real Spring service, distributed cache coherence, or recovery when the provider fails after commit. Stdout is derived from the code and Javadoc; the program should be run with the declared dependencies to verify directly on the learner's machine.

## 9. Immediate Operations Inside Transactions: Use With Intent

Spring Cache also provides operations expecting immediate change, such as:

| Method | Meaning | Caution when a transaction is active |
| --- | --- | --- |
| `putIfAbsent(K, V)` | Writes if no mapping exists and returns previous wrapper | Can write **before commit**, even if the transaction later rolls back |
| `evictIfPresent(K)` | Deletes key expecting immediate invisibility after call | DB rollback does not automatically restore the deleted entry |
| `invalidate()` | Clears entire cache with immediate visibility expectation | Can wipe many entries before knowing whether the DB transaction succeeds |

The `TransactionAwareCacheDecorator` Javadoc states that `putIfAbsent` and `evictIfPresent` **cannot be deferred** to `afterCommit` while preserving their immediate semantics. `invalidate` is a clear variant expecting immediate effect, and must likewise be evaluated as an immediate operation.

Distinguish return values:

- `evictIfPresent(K)==false` is not necessarily an error. The key might not exist, or the provider might not determine prior presence.
- `invalidate()==false` may mean the cache was already empty or prior entries could not be determined.
- `putIfAbsent(K,V)` **does not overwrite** an existing value. If the cache already has K, the operation returns the old entry's wrapper; the new value might not be written.
- Custom implementations might use default methods that do not achieve the same atomicity/immediacy as native caches. Check the specific provider before relying on strong guarantees.

**Design rule:** choose deferred `put/evict/clear` when the goal is to **change the cache only after a successful commit**; choose immediate methods when the application truly needs pre-commit visibility and understands the rollback/race risks. Do not switch `evict` to `evictIfPresent` just to fix a cache miss without understanding transaction semantics.

## 10. Combining `@Transactional` and `@CacheEvict`: AOP Advice Ordering

Example:

~~~java
@Transactional
@CacheEvict(cacheNames = "products", key = "#p0",
            beforeInvocation = false)
public void changePrice(long id, long newPrice) {
    repository.changePrice(id, newPrice);
}
~~~

This is a **snippet inside a Spring-managed bean**; a real repository, transaction manager, and cache manager are required. When called through a proxy, both cache advice and transaction advice participate. Depending on advisor order, which wraps which, and transaction propagation:

**Case A – eviction is requested while the transaction is still active:**

~~~text
TransactionInterceptor: begin
  CacheInterceptor:
    changePrice(...)
    Cache.evict(K) -> decorator registers afterCommit
TransactionInterceptor: DB commit
TransactionAwareCacheDecorator: native evict(K)
~~~

With this arrangement, the cache decorator actually has synchronization to register the command for after commit.

**Case B – eviction is requested after transaction advice has already completed:**

~~~text
CacheInterceptor:
  TransactionInterceptor: begin
    changePrice(...)
  TransactionInterceptor: DB commit + cleanup
  Cache.evict(K) -> no active sync left, delegates immediately
~~~

Case B can also achieve an "after DB commit" ordering for a simple synchronous call, but the crucial difference is that **the command is not registered in a post-commit callback**, and the ordering can change if an outer transaction or other advice is present.

**There is no universal answer like "just add both annotations to guarantee after-commit".** Spring cache advice has the `order` attribute on `@EnableCaching`; transaction advice has `@EnableTransactionManagement(order=...)`. If neither has controlled ordering, test with a real transaction manager and identify the outer/inner boundaries.

An outer transaction may wrap the annotated method call; a `REQUIRES_NEW` transaction has its own commit. The cache command registers with the synchronization of the transaction active **at the time of invocation**; it does not automatically attach to "the final business transaction" by method name.

### Self-Invocation Is Still an Issue

In default proxy mode:

~~~java
public void outer(long id) {
    this.changePrice(id, 123L); // self-invocation bypasses proxy
}
~~~

If invoked internally from the target rather than through the Spring proxy, both `@CacheEvict` and `@Transactional` on `changePrice` can be bypassed. Reorganize bean/call boundaries or use AspectJ weaving when internal interception is truly required. Do not blame the decorator if the caching operation was never invoked.

## 11. `afterCommit` Is Not a Distributed Transaction

The decorator provides practical value, yet **cannot guarantee DB/cache atomicity**:

1. **DB commit succeeds, cache put/evict fails:** the DB has committed; the transaction cannot be rolled back retroactively just because the cache later failed. Stale entries may remain; TTL, retries, outbox, or reconciliation are required.
2. **Concurrent loader can still re-store stale values:** a reader that started before commit may finish after the callback and write a stale value back. Versioned keys, loader coordination, or a consistency protocol are needed.
3. **`TransactionAwareCacheDecorator` does not keep pending state for reads:** `get` before commit still uses the native cache and does not see pending `put`s.
4. **Local vs. distributed:** a post-commit callback does not give cache providers on every node immediate/linearizable replication. Inspect backend consistency and near-cache behavior.
5. **Background jobs or message brokers:** side effects outside the DB transaction can finish failing or commit before the DB commits; the cache decorator does not reorder every resource.
6. **Application crash:** the DB may commit yet the process terminates before or during the after-commit callback. An in-process callback is not durable messaging. If eventual yet reliable invalidation is mandatory, use an outbox/invalidation event with retries.
7. **Cache stampede:** post-commit `clear` can trigger a wave of simultaneous cache misses. Consider key-level eviction rather than full-region clearing.

Accurate phrasing: **a transaction-aware cache is a mechanism for deferring cache operations until after a Spring synchronization commits**, not a transaction coordinator able to guarantee every cache entry across every system stays synchronized at the exact moment.

## 12. When an `afterCommit` Callback Fails

A transaction callback can execute after the data source has already committed. Suppose:

~~~java
@Override
public void afterCommit() {
    cache.evict("product:42"); // provider may throw an exception
}
~~~

This snippet describes a callback, not a standalone Java file. If the provider throws an error, the outcome depends on the transaction manager, error propagation, and `CacheErrorHandler` when invoked via caching advice. What does not change is that **the DB commit already happened**; the caller receiving an exception after commit does not mean the DB will automatically roll back.

Operationally:

- Track eviction/put errors via metrics, logs, and alerts; avoid silently swallowing them.
- For caches with TTLs, evaluate the maximum stale window if a callback is lost or fails.
- If delivery guarantees are needed, use a **transactional outbox** or reliable event queue to retry invalidation after commit.
- For remote caches, distinguish timeouts before the provider receives the command from timeouts after execution when the response was not returned. Retries may be safer for key-idempotent eviction than for some other updates, though ordering/versioning must still be defined.
- Do not write extra data to the database inside `afterCommit` assuming it belongs to the just-committed transaction. If a new DB transaction is genuinely needed, explicitly use `REQUIRES_NEW` propagation with the appropriate manager.

## 13. How Does `@TransactionalEventListener(AFTER_COMMIT)` Differ From the Decorator?

Another option is publishing a domain event inside the transaction and processing it after commit:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onProductChanged(ProductChangedEvent event) {
    cacheManager.getCache("products").evict(event.productId());
}
~~~

This is a **Spring bean snippet** requiring the event type, cache manager, annotation imports, and an event published while a transaction is active. `@TransactionalEventListener` binds the listener to the transaction lifecycle, supporting phases such as `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`.

Comparison:

| Mechanism | Idea | Pros | Limits |
| --- | --- | --- | --- |
| `TransactionAwareCacheDecorator` | Intercepts `put/evict/clear` on Cache and defers | No need to write listeners per method; wraps Cache API | Applies only to operations going through the decorator; not durable messaging |
| `@TransactionalEventListener(AFTER_COMMIT)` | Listens for events when transaction commits | Decouples domain events from invalidation policy; easy to add consumers | In-process listener can fail/be lost on crash; requires defining event publish/transaction |
| Transactional outbox | Writes event in same DB transaction, worker delivers later | Supports retries and recovery if process dies | More complex; requires idempotency, consumer handling, and backlog monitoring |

Do not forget the `AFTER_COMMIT` listener caveat that transaction resources may still remain bound during the callback; new DB writes wanting their own commit require a new transaction. When using an async event listener, execution timing and visibility introduce their own latency.

For multiple services or multiple cache regions, events/outbox may fit better than calling caches directly from the update site. For a synchronous Spring application with moderate requirements, the decorator is a straightforward choice.

## 14. Common Mistakes

**Mistake 1 – "`@Transactional` automatically makes caching after-commit."** Not necessarily; you also need a transaction-aware `CacheManager`, active synchronization, and proper advice ordering.

**Mistake 2 – "`@CacheEvict(beforeInvocation=false)` is always after commit."** False; it is after method invocation in caching advice, not necessarily after DB commit.

**Mistake 3 – "Once `cache.put` is called, the current transaction can read the new value."** False with the decorator: there is no transaction-local write buffer; `get` can still miss or return the old value.

**Mistake 4 – "Rollback will undo `evictIfPresent`."** False: the immediate operation already mutated the cache before the DB decided to commit or roll back.

**Mistake 5 – "`TransactionAwareCacheManagerProxy` creates a database transaction itself."** False; it only wraps the cache and receives callbacks from existing transaction infrastructure.

**Mistake 6 – "Calling the raw cache is fine too."** Not if you want after-commit; the raw native cache bypasses the decorator and can mutate immediately.

**Mistake 7 – "Deleting cache after commit guarantees no staleness."** Concurrent loaders, distributed replicas, and callback failures can still cause staleness.

**Mistake 8 – "On rollback, every side effect disappears."** Resources outside the DB transaction may have committed separately; the decorator does not roll back HTTP/messages/files.

**Mistake 9 – "If the post-commit cache callback fails, the DB rolls back too."** False: the DB commit already completed. Remediation is required.

**Mistake 10 – "Just put `@CacheEvict` on a private method."** Caching proxy mode does not intercept normal private/self-invocation calls.

**Mistake 11 – "Every `CacheManager` has transaction-aware enabled automatically."** Cannot be assumed; check the concrete bean, inheritance/config, and wrapper.

**Mistake 12 – "A local ConcurrentMap test proves Redis cluster consistency."** False; integration testing with the native provider and multiple nodes is a separate step.

## 15. Testing and Diagnostics

A thorough test suite should verify the following checkpoints:

| Test | Setup | Expected |
| --- | --- | --- |
| Deferred put | Transaction active, key empty | Before commit still misses; after commit hits new value |
| Deferred evict | Key already exists | Before commit old entry remains; after commit misses |
| Deferred clear | Cache holds multiple keys | Before commit entries remain; after commit cleared |
| Rollback after put | Register put then roll back | No new entry added via callback |
| Rollback after evict | Register evict then roll back | Old entry not removed via callback |
| Immediate evict | `evictIfPresent` in transaction | Native key removed immediately if provider supports it; rollback does not restore |
| No transaction | Call decorated put/evict | Delegates immediately per provider contract |
| Outer transaction | Method returns while outer txn still open | Operation may stay pending until outer commit |
| `REQUIRES_NEW` | Inner transaction commits separately | Inner transaction's callback can run before outer commit |
| Cache exception | Native provider throws in callback | DB commit does not auto-rollback; must log/recover |
| Concurrent reader | Reader misses before/right at commit | Check stale reload race |
| Multi-node | Multiple instances sharing remote cache | Measure invalidation latency and real consistency |

How to observe:

~~~java
boolean synchronizationActive =
        TransactionSynchronizationManager.isSynchronizationActive();
boolean actualTransactionActive =
        TransactionSynchronizationManager.isActualTransactionActive();
~~~

This snippet requires importing `org.springframework.transaction.support.TransactionSynchronizationManager`. The two booleans refer to **two distinct concepts**: whether synchronization callbacks can be registered and whether an actual transaction is active. Do not use these two flags as a substitute for verifying committed data in the DB.

When using a logger, you can enable Spring transaction/cache DEBUG logs in test environments to inspect advisor/callback ordering. Still, a single log sequence does not prove distributed visibility. Verify with concrete assertions after commit/rollback and on the target providers to be supported.

## 16. Production Design Checklist

Before enabling transaction-aware caching in a system:

- Is the `CacheManager` bean injected into the Spring caching advisor actually a transaction-aware proxy or a manager supporting `setTransactionAware(true)`?
- Do annotated methods run through a **Spring AOP proxy**, and does the transaction have active synchronization when `put/evict/clear` are invoked?
- Is there any code path writing directly to the native cache and bypassing the decorator?
- For cache reads inside a transaction, is **no read-your-writes** acceptable?
- If an outer transaction rolls back, are registered cache callbacks skipped as expected?
- Are immediate `putIfAbsent`/`evictIfPresent`/`invalidate` used inside transactions? Are pre-commit cache changes acceptable?
- Have advisor ordering and propagation between `@CacheEvict`/`@Transactional` been integration-tested on the real application?
- What if the DB commits yet the cache callback fails or the process crashes? Are TTL/retries/outbox/monitoring in place?
- Are there multiple nodes/remote caches and concurrent loaders? Has the stale window SLA been defined?
- Can key-level eviction be used instead of full cache clear to avoid cache stampedes?
- Have commit, rollback-only, DB exception, cache-provider exception, and `REQUIRES_NEW` branches all been tested?

## 17. Official References

- [Spring Framework — TransactionAwareCacheDecorator Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html): describes post-commit `put`, `evict`, `clear` and immediate operations.
- [Spring Framework — TransactionAwareCacheManagerProxy Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html): wrapper for `CacheManager` and lifecycle.
- [Spring Framework — AbstractTransactionSupportingCacheManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/AbstractTransactionSupportingCacheManager.html): base manager mechanism supporting transaction-aware configuration.
- [Spring Framework — TransactionSynchronizationManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html): synchronization registration and state queries.
- [Spring Framework — TransactionSynchronization Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html): `afterCommit`, `afterCompletion`, and ordering.
- [Spring Framework — Cache API Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html): value/timing of `put`, `evict`, `clear`, `evictIfPresent`, and `putIfAbsent`.
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@Cacheable`, `@CachePut`, `@CacheEvict`, proxies, and before/after invocation.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener(AFTER_COMMIT)` and callback phases.

**Conclusion:** `TransactionAwareCacheDecorator` is Spring Cache's adapter allowing `put`, `evict`, and `clear` to **wait until after-commit when suitable transaction synchronization is active**; rollback skips running those callbacks. In return, cache reads within a transaction can still see old state, immediate operations are not deferred, and post-commit failures/races must still be designed for explicitly.