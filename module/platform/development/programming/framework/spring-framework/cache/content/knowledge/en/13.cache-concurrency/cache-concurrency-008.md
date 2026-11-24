# Designing Processing So Duplicate Computation Causes No Business Errors — Spring Cache and Concurrency

## 1. The root scenario: same cache key, multiple concurrent misses

In Spring Framework, `@Cacheable` skips the method body if a cached value already exists for the requested key. However, when **two or more concurrent requests** observe a cache miss together, the Spring Cache abstraction **does not lock the entire get -> compute -> put sequence by default**. Multiple requests can all run the same loader:

~~~text
             Thread A                 Thread B                 Cache
t0       get("sku-7")              get("sku-7")               miss
t1       cache miss                cache miss                 empty
t2       compute("sku-7")          compute("sku-7")           empty
t3       return result 100         return result 100          empty
t4       put("sku-7",100)          put("sku-7",100)           100
~~~

This is **duplicate computation** on concurrent cache misses, often associated with a *cache stampede*. One final entry may be valid yet **does not prove the method ran only once**.

Distinguish two classes of consequences:

- **Duplicate computation without business errors:** two conversions, data aggregations, or reads of an immutable snapshot with no side effects; mainly wastes compute resources.
- **Duplicate computation causing business errors:** methods deducting inventory, charging payments, issuing vouchers, awarding points, sending notifications, or calling side-effecting services. Two executions can double the business effect, regardless of the cache holding a single final value.

**Design principle:** make **duplicate execution harmless first**, then reduce execution count for performance. Never reverse these two priorities.

## 2. Caching does not guarantee exactly-once

Example to avoid:

~~~java
// WRONG: cache miss/retry can cause payment transactions to happen multiple times.
@Cacheable(cacheNames = "payments", key = "#p0")
public Receipt charge(String orderId) {
    return paymentGateway.charge(orderId);
}
~~~

This is illustrative Spring code, incomplete in types/beans. If two nodes miss together, the entry hits TTL, the cache provider drops out, or the request retries, `charge()` can be invoked again. `@Cacheable` is not a double-payment guard.

Better design:

~~~text
POST /orders/{id}/pay
 → PaymentCommandService.pay(orderId, idempotencyKey)
 → authorization + state check
 → idempotency record/unique constraint in durable store
 → call payment provider per idempotency contract
 → persist business outcome, reconcile on failure
 → invalidate read cache after commit per policy

GET /orders/{id}
 → OrderQueryService.findById(id)
 → @Cacheable only for recomputable read queries
~~~

A cache is an acceleration copy, **not proof of how many transactions were executed**.

## 3. Pure, idempotent, and single-flight are different

| Mechanism | Meaning | What it protects |
|---|---|---|
| **Pure computation** | Same input and snapshot yield same output, no observable side effects | Re-running creates no extra business effects |
| **Idempotent command** | Re-executing the same logical request does not duplicate the final effect | Retries, duplicate delivery, duplicate submissions |
| **Atomic update** | Updates and guards have proper atomic scope | Prevents read-modify-write races |
| **Single-flight** | Shares one in-flight computation for the same key | Reduces duplicate work within a coordination scope |
| **`@Cacheable(sync=true)`** | Asks the cache provider to synchronize key loading | Reduces duplicate cache loads if supported by provider |
| **Exactly-once effect** | Business effect occurs once per operation | Needs durable contracts/state/constraints, not caching |

Example of a value-computing-only operation:

~~~java
public long calculateVat(long amountVnd, int rateBasisPoints) {
    return Math.multiplyExact(amountVnd, rateBasisPoints) / 10_000L;
}
~~~

Running twice creates no order, deducts no stock, and sends no payment. This is pure Java; rounding/bounds rules must still follow real business requirements.

Conversely, `repository.incrementRewardPoints(userId, 10)` has a side effect. Even if two requests return the same points value from the cache, the ledger may have been credited twice.

**A read-only loader still risks stale results:** if the origin changes between two computations, an older result can be put after a newer one. Use versioning/invalidation/TTL when freshness is required.

## 4. Check-then-act bugs are not fixed by caching

Suppose stock has one unit:

~~~text
Request A: SELECT quantity → 1
Request B: SELECT quantity → 1
A: if quantity > 0 → proceed
B: if quantity > 0 → proceed
A: deduct one unit
B: deduct one unit
=> can confirm two orders for a single unit of inventory
~~~

If stock is read from cache, two requests are even more likely to see the same stale positive count. **Invariants must be enforced at the authoritative data source**, such as a conditional update:

~~~sql
UPDATE inventory
SET quantity = quantity - 1
WHERE sku = :sku
  AND quantity >= 1;
~~~

Inside an appropriate transaction, check the **updated row count**; consider a unit reserved only when the count equals 1. If order creation and stock deduction span multiple tables/services, design transactions/workflows with constraints or sagas/compensation.

Other mechanisms: optimistic locking with a version column, row locks, unique constraints, conditional state transitions. `@Transactional` by itself does not make arbitrary `SELECT`-then-`UPDATE` sequences safe; Java `synchronized` locks only within one JVM/object and does not block other nodes.

## 5. Default @Cacheable does not lock loaders

~~~java
@Cacheable(cacheNames = "reports", key = "#p0")
public Report buildReport(String reportId) {
    return reportRepository.calculate(reportId);
}
~~~

This is illustrative Spring integration code requiring `@EnableCaching`, a `CacheManager`, and domain beans. On a cache miss, Spring executes the method and stores the result. When two threads miss together, **both can call `calculate`**.

That remains valid if the loader:
- only reads or computes without side effects;
- is accurate for the snapshot used;
- does not create unique resources;
- does not depend on running only once;
- handles retries after failures.

Never attach business commands like payment/stock/redeem here and rely on the cache to stop duplicate calls.

## 6. @Cacheable(sync=true): reduces duplicate work without guaranteeing business semantics

You can request synchronized cache loading:

~~~java
@Cacheable(cacheNames = "reports",
           key = "#p0",
           sync = true)
public Report buildReport(String reportId) {
    return reportRepository.calculate(reportId);
}
~~~

When supported by the provider, Spring can use the `Cache.get(key, Callable)` contract to coordinate threads loading the same key, cutting loader runs. This is a **hint to the cache provider**, not a distributed lock or an exactly-once command.

Per Spring Javadoc, `@Cacheable(sync=true)` has **three constraints**:

1. **`unless` is not supported**.
2. Only **one cache region** may be declared for the synchronized operation.
3. No other cache-related operation may be combined on the same method.

**Invalid** example:

~~~java
// Invalid: sync=true combined with unless.
@Cacheable(cacheNames = "reports",
           sync = true,
           unless = "#result == null")
public Report invalidExample(String reportId) {
    return reportRepository.calculate(reportId);
}
~~~

Synchronization scope must be verified:

- Threads in **one JVM** with a supporting provider can be coordinated per key.
- Two JVMs with **separate local caches** share no locks; two loaders can still run.
- Having Redis or a distributed cache **does not automatically imply** distributed locking for loaders. Check the specific provider.
- TTL, eviction, loader exceptions, backend unavailability, or subsequent misses can still cause the loader to run again.

**`sync=true` is an optimization for a loader that is already safe to re-run**, not a fix for a command lacking idempotency.

## 7. Standalone Java 17: demonstrating duplicate side effects

The following example **simulates** a cache with `ConcurrentHashMap`; it uses neither real Spring annotations nor a payment/database system. `CountDownLatch` forces both threads to see a cache miss before proceeding so results do not depend on scheduler luck.

Create **`ConcurrentCacheSafetyDemo.java`**:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentCacheSafetyDemo {
    record Stats(int loads, int sideEffects, int cachedValue) {}

    private static Stats race(boolean withSideEffect) throws Exception {
        ConcurrentMap<String, Integer> cache = new ConcurrentHashMap<>();
        AtomicInteger loads = new AtomicInteger();
        AtomicInteger sideEffects = new AtomicInteger();
        CountDownLatch bothSawMiss = new CountDownLatch(2);

        Callable<Integer> job = () -> {
            Integer hit = cache.get("sku-7");
            if (hit != null) {
                return hit;
            }
            bothSawMiss.countDown();
            bothSawMiss.await();
            loads.incrementAndGet();
            if (withSideEffect) {
                sideEffects.incrementAndGet();
            }
            cache.putIfAbsent("sku-7", 100);
            return cache.get("sku-7");
        };

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> first = pool.submit(job);
            Future<Integer> second = pool.submit(job);
            if (first.get() != 100 || second.get() != 100) {
                throw new IllegalStateException("unexpected result");
            }
            return new Stats(loads.get(), sideEffects.get(), cache.get("sku-7"));
        } finally {
            pool.shutdownNow();
        }
    }

    private static Stats singleFlight() throws Exception {
        ConcurrentMap<String, Integer> cache = new ConcurrentHashMap<>();
        AtomicInteger loads = new AtomicInteger();
        CountDownLatch start = new CountDownLatch(1);

        Callable<Integer> job = () -> {
            start.await();
            return cache.computeIfAbsent("sku-7", key -> {
                loads.incrementAndGet();
                return 100;
            });
        };

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> first = pool.submit(job);
            Future<Integer> second = pool.submit(job);
            start.countDown();
            if (first.get() != 100 || second.get() != 100) {
                throw new IllegalStateException("unexpected result");
            }
            return new Stats(loads.get(), 0, cache.get("sku-7"));
        } finally {
            pool.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        Stats unsafe = race(true);
        Stats pure = race(false);
        Stats guarded = singleFlight();

        System.out.printf("unsafe: loads=%d, sideEffects=%d, cached=%d%n",
                unsafe.loads(), unsafe.sideEffects(), unsafe.cachedValue());
        System.out.printf("pure: loads=%d, sideEffects=%d, cached=%d%n",
                pure.loads(), pure.sideEffects(), pure.cachedValue());
        System.out.printf("singleFlight: loads=%d, sideEffects=%d, cached=%d%n",
                guarded.loads(), guarded.sideEffects(), guarded.cachedValue());
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac --release 17 ConcurrentCacheSafetyDemo.java
java ConcurrentCacheSafetyDemo
~~~

**Exact** stdout:

~~~text
unsafe: loads=2, sideEffects=2, cached=100
pure: loads=2, sideEffects=0, cached=100
singleFlight: loads=1, sideEffects=0, cached=100
~~~

Conclusions from the program:

- `unsafe` case: both threads miss and execute the simulated side effect **twice**, even though `putIfAbsent` preserves only a single entry.
- `pure` case: also computes twice, but has **no** side effects, so it only wastes compute work.
- `singleFlight` case: `computeIfAbsent` on **the same ConcurrentHashMap in one JVM** coordinates creating the mapping; the successful loader executes only once.
- Never put business side-effect logic inside a mapping function and assume it becomes exactly-once. A Java map provides neither persistent transactions nor distributed locks.

## 8. Designing loaders safe for re-execution

~~~java
@Service
public class PriceQueryService {
    private final PriceRepository repository;

    public PriceQueryService(PriceRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "priceSnapshots",
               key = "#p0",
               sync = true)
    public PriceSnapshot getSnapshot(String sku) {
        return repository.fetchSnapshot(sku);
    }
}
~~~

This is illustrative Spring code requiring `PriceSnapshot`, `PriceRepository`, and project imports.

Loader checklist:

1. **Do not mutate business state.** Never create invoices, charge payments, or issue vouchers inside a cache-read method.
2. **Keys include full context:** tenant, currency, locale, effective date, role, filters, and version when they affect results.
3. **Clear freshness policy:** TTL, after-commit invalidation, versioned keys, or appropriate snapshots.
4. **Return data callers cannot jointly mutate:** use immutable DTOs/records or defensive copies.
5. **Safe to re-run after errors:** cache backend timeouts or thrown loader exceptions can trigger recomputation next time.
6. **Do not confuse metrics with business state:** loader run count is not transaction execution count.
7. **Bound resources** during cache stampedes: timeouts, rate limits, bulkheads, and query budgets.

A method named `getSomething()` is not guaranteed pure: it might call a billed API, consume quota, or emit business-significant events. Inspect the actual dependency contracts.

## 9. Side effects require idempotency keys and durable state

For payment/redeem/command operations, identify the **logical operation** with its own key instead of a cache key to block duplicates:

~~~text
Client → POST /orders/O-7/pay
             idempotencyKey=PAY-7
        |
        v
     Auth + validate payload
        |
        v
     DB UNIQUE(tenant_id, idempotency_key)
        |
        +-- COMPLETED same payload → return stored result
        +-- PROCESSING            → return status/wait per policy
        +-- key differs payload   → reject explicitly
        +-- new key               → reserve durable operation
                                        |
                                        v
                               call payment provider per
                               their idempotency contract
                                        |
                                        v
                               save result/status + reconcile
                                        |
                                        v
                               invalidate query cache
~~~

**No single DB transaction can be atomic with an HTTP call to a payment provider.** If the service crashes after the provider processed the request but before saving `COMPLETED`, reconcile or retry via the provider's idempotency contract—never blindly send a new charge.

Details to design:
- **Uniqueness** in the DB or durable state store; `SELECT` then `INSERT` without a unique constraint still races.
- Keys **scoped by tenant and operation**; the same key with a different payload must error or follow a defined policy.
- Persist results for retries, and handle in-progress states, timeouts, crashes, and reconciliation.
- Idempotency record TTL follows the retry contract; it is **distinct** from read-cache TTL.
- Verify how the provider supports idempotency, whether it returns old results, and how long it retains keys.

Caching can speed up reading operation status, yet **never replaces a durable uniqueness barrier**.

## 10. Which invariants does the database protect?

| Invariant | Appropriate mechanism | Why cache is insufficient |
|---|---|---|
| One operation per idempotency key | Unique constraint + durable state | Misses, expiry, eviction, multi-node |
| Non-negative stock | Atomic conditional UPDATE/locks/isolation | Two requests can both observe positive stock |
| A voucher is redeemed only once | Unique redemption record/compare-and-swap | Cache put is not atomic with DB |
| Never overwrite newer data with stale data | Optimistic version/conditional write | Last writer wins can be stale |
| Messages do not duplicate side effects | Transactional outbox + consumer idempotency | Messages can be redelivered |
| Issue a unique identifier only once | Sequence/unique key | Cache can be lost or rebuilt |

`@Transactional` defines transaction boundaries, but does not enforce every invariant automatically. Design isolation, constraints, conditional updates, or row locks per business contract.

Never treat `synchronized` or `ReentrantLock` in a single service instance as a cluster-wide guard; other servers can still write the same DB.

## 11. Distributed locks do not mean exactly-once

Distributed locks/leases can reduce contention, yet failure modes remain:

- Worker A holds a lease and pauses; the lease expires, and B acquires the lock.
- A wakes up and writes late despite no longer owning the lock.
- A calls an external API successfully and crashes before saving local state.
- Retries cannot tell whether the previous attempt completed.

For strict updates, use **fencing tokens or monotonic versions** checked at the origin write, plus idempotency state and reconciliation. Distributed locks are supporting tools, not the sole guardian of business invariants.

## 12. Optimizing cache stampedes after ensuring business correctness

| Technique | Effect | Limitation |
|---|---|---|
| `@Cacheable(sync=true)` | Coordinates same-key loaders when supported by provider | No cross-JVM guarantee, annotation constraints |
| Per-key single-flight | Shares in-flight `Future` | Usually local; needs timeout/cleanup handling |
| TTL jitter | Avoids many keys expiring simultaneously | Does not eliminate single-key races |
| Cache warming | Preloads data before traffic peaks | Can waste work and load stale data |
| Stale-while-revalidate | Serves old copy temporarily while refreshing in background | Only when business tolerates staleness |
| Bulkhead/rate limit | Protects DB/APIs from bursts | Increases latency or rejects requests |
| Versioned keys | Separates data generations | Needs version progression/cleanup policy |

**Loader failures and nulls:** throwing loaders may be re-invoked; do not assume exceptions are cached like successful values. `sync=true` disallows `unless`, so null/empty storage depends on the CacheManager/provider; test negative caching explicitly. Repeated misses for "not found" can also cause stampedes.

## 13. Wrong keys return wrong data even with sync enabled

Example of pricing by tenant, SKU, and currency:

~~~java
@Cacheable(cacheNames = "prices", sync = true)
public PriceSnapshot getPrice(String tenant, String sku, String currency) {
    return repository.fetchPrice(tenant, sku, currency);
}
~~~

By default with multiple parameters, Spring uses `SimpleKey` containing all arguments. If replaced with `key="#p1"` (SKU only), two tenants sharing an SKU with different prices can wrongly share one entry; `sync=true` even forces threads to wait on and share that wrong result.

Manual string concatenation like `tenant + ":" + sku` must avoid collisions if inputs can contain the delimiter; consider immutable key objects or normalized generators and proper serializers. Authorization must still be handled separately; never substitute cache names/keys for access control checks.

## 14. Pure loaders can still write stale data after newer commits

~~~text
t0  Request A cache misses, reads snapshot version 10
t1  Request B updates DB to version 11, commits
t2  Request B evicts cache
t3  A finishes late and puts version 10
t4  Request C hits cache but sees stale version 10
~~~

`sync=true` mainly coordinates loaders for a key, **without atomically linking to database transactions**. When correctness requires freshness:

- Invalidate after commit with clear ordering.
- Use versioned cache keys/generations or pre-put version comparisons if supported.
- Keep TTL and reconciliation if bounded staleness is acceptable.
- Test races between writers and slow loaders; do not test only concurrent readers.

`@CacheEvict` by default evicts after the cache-intercepted method completes successfully, **without automatically guaranteeing the DB has committed** under every advice ordering. `@CachePut` always executes the method and caches the result; it **does not** protect commands from running multiple times.

## 15. Two JVMs and local locks

~~~text
Client A → Pod A → local cache miss → loader runs
Client B → Pod B → local cache miss → loader runs
                                 |
                             shared DB
~~~

Two JVMs using separate `ConcurrentMapCacheManager` instances can still each compute once despite `sync=true`. Distributed caches do not automatically offer distributed single-flight; inspect the provider's actual contract. A two-thread unit test in one JVM **does not prove** multi-node production safety.

## 16. Testing concurrency across four layers

**Safe duplicate execution:** use `CountDownLatch`/barriers to force two same-key misses, and check both results, loader count, and zero side effects.

**Spring sync:** test with a real Spring bean through its proxy, real provider, and `@Cacheable(sync=true)`, measuring loader invocation counts. Test exceptions, nulls, TTL, and eviction. Passing on one provider does not prove every provider behaves identically.

**Business commands:** two concurrent requests with the same idempotency key and payload must yield only one business effect and one logical operation in durable storage. **Clear the cache and retry**: invariants must still hold. Test retries after timeouts, crashes after external calls, and mismatched payloads with the same key.

**Stale data and multi-node:** have A hold an old version, B commit a new version and evict, and A put late. Test multiple pods, cache backend failures, transaction rollbacks, message replays, and expired distributed leases.

Track separate metrics: cache hits/misses, loader invocations, business side-effect counts, constraint violations/deduplication, and stale reads. **Cache put count is not created payment count.**

## 17. Common pitfalls

- "`@Cacheable` makes the method run only once." **False** under concurrent misses, TTL, eviction, retries, and restarts.
- "`sync=true` is a distributed mutex." **False** unless guaranteed by the provider.
- "`putIfAbsent` prevents side effects." **False** if the side effect occurs before the cache put.
- "Two identical outputs mean there was no double charge." **False** if the external action executed twice.
- "`synchronized` protects multiple pods." **False**: applies only within one JVM/object.
- "`@Transactional` automatically prevents double-selling." **False** without proper isolation/constraints/conditional updates.
- "Pure loaders keep the cache always fresh." **False** when origin data changes or puts arrive late.
- "SKU alone is enough as a key for multi-tenant systems." **False** when prices/permissions/locales differ.
- "Passing a two-thread unit test means cluster safety." **False**.
- "Cache unavailability is allowed to break business invariants." **False**: correctness must not depend on the cache.

## 18. Pre-production checklist

1. If the method re-runs 10 times, **can business state be mutated multiple times**?
2. For side effects, are commands separated and protected by idempotency in durable records?
3. Are invariants encoded via DB constraints, conditional writes, or suitable locks/transactions?
4. Do keys include tenant, currency, role, version, and all inputs affecting output?
5. Does the provider support `sync=true` at the JVM or cluster scope you require?
6. Are any `sync=true` limits violated: multiple caches, `unless`, combined operations?
7. Are nulls/exceptions/retries, TTL expiry, and cache backend outages handled?
8. Is there a strategy against stale puts after commits/invalidations?
9. Do tests cover two threads, two instances, and fault injection?
10. Do metrics distinguish loader counts from **actual business effects**?

**Short rule:** *Design so re-execution stays business-correct; only then optimize to execute fewer times.*

## 19. Self-check

**Q1.** Two cache misses both run a pure computation and return the same result. What is the main issue?

**Q2.** Does `sync=true` guarantee charging a payment exactly once across multiple JVMs?

**Q3.** Is `@Cacheable(sync=true, unless="#result == null")` valid?

**Q4.** With two pods using separate local caches, does `sync=true` guarantee one loader cluster-wide?

**Q5.** Why can `putIfAbsent` after deducting inventory fail to stop double deduction?

**Q6.** Two transactions both see stock=1. How do you protect the invariant?

**Q7.** Why must idempotency records be more durable than a cache?

**Q8.** What can happen if a pure loader reads version 10 and puts after version 11 already committed?

**Answers:**

1. **Wasted compute/DB**, not necessarily a business correctness error.
2. **No**. You need idempotency state, provider contracts, and DB constraints.
3. **No**, `sync=true` does not support `unless`.
4. **No**, each JVM owns its own cache/locks.
5. Because the side effect occurs before the put; the cache only controls the entry.
6. Use atomic conditional updates, proper isolation/locks, or versioning/constraints.
7. Caches can expire/miss/evict and span multiple nodes; invariants must never depend on caching.
8. **Stale cache**; requires versioned keys, invalidation/validation, and freshness policies.

## 20. References

- Spring Framework Reference — *Synchronized Caching*, *Default Key Generation*: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Javadoc — `Cacheable.sync` and constraints: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Cacheable.html
- Spring Javadoc — `Cache.get(Object, Callable)`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html
- Java 17 Javadoc — `ConcurrentHashMap.computeIfAbsent`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html

**Conclusion:** Duplicate computation on cache misses is normal. **Never let business correctness depend on cache hits.** Separate pure queries from idempotent commands, enforce invariants in durable storage, and use `@Cacheable(sync=true)` or single-flight only as a verified optimization.