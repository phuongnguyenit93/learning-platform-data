# Preventing Cache Stampedes When Multiple Requests Reload Data Simultaneously

A **cache stampede** occurs when many concurrent requests need the same data that is absent from the cache or has just expired. Instead of a single request reloading data from the source database/API and populating the cache, **many requests perform the reload simultaneously**. A "hot" key accessed by thousands of requests can hit the database with thousands of identical queries in a very short window.

In **Spring Data Redis**, Redis is typically a shared cache across multiple application instances. Sharing results is very helpful, yet Redis **does not automatically coalesce concurrent cache misses into a single source load**. Consequently, merely adding `@Cacheable` or a `GET` then `SET` is not enough to prevent a stampede.

The goal of this lesson is to design the read path so cache misses do not turn into a "source query storm", while keeping staleness bounds, latency, consistency, and failure recovery clear.

## 1. How does a cache stampede unfold?

Suppose an e-commerce site has a very popular product `p-100`. State at 10:00:

```text
Redis:
    cache:product:p-100  -> exists, 1 second TTL remaining

Database:
    products(id=p-100)   -> one record
```

Right as the TTL expires, 500 requests arrive together:

```text
                500 HTTP requests
                      |
                      v
             GET cache:product:p-100
                      |
                      v
                 CACHE MISS
                      |
       +--------------+--------------+
       |              |              |
   Request 1      Request 2      Request 500
       |              |              |
       v              v              v
   SELECT DB       SELECT DB       SELECT DB
       |              |              |
       +--------------+--------------+
                      |
                      v
         Many identical results
         written back to the same key
```

Every request sees a miss before any request finishes writing the new value into Redis. If each source query takes 100 ms, the redundant queries can exhaust connection pools, raise latency, and pile up waiting requests. A slower source widens the miss window, letting even more requests slip through.

This creates a **load amplification loop**:

```text
Hot key expires
       |
       v
Many requests miss
       |
       v
Database/API gets overloaded
       |
       v
Source load time increases
       |
       v
More requests keep missing
       |
       +----> Source load rises further
```

### Rough estimate

Suppose an endpoint receives 1,000 requests/second for the same key and source load time is 200 ms. During that 200 ms window, roughly **200 requests** can all observe a miss before the first entry is populated; this is only an approximate model assuming relatively steady traffic, not a fixed measurement.

If the system runs 10 instances, and each instance queries the database on a miss, a shared Redis alone does not solve it. A mechanism is needed to reduce **recomputations** across the entire request group.

## 2. Distinguishing stampede, avalanche, and cache penetration

These three issues often appear together, though their causes and remedies differ.

| Phenomenon | Symptom | Primary cause | Measures to consider |
|---|---|---|---|
| **Cache stampede** | Many requests concurrently reload one hot key | Simultaneous miss/expiration on the same key | Request coalescing, single-flight, locks, stale-while-revalidate |
| **Cache avalanche** | Many keys expire together or the cache stops working | Synchronized TTLs, Redis outage, or broad invalidation | TTL jitter, staggered reloads, source protection, cache recovery |
| **Cache penetration** | Many requests query non-existent keys and always miss | Invalid IDs, missing data, abusive traffic | Negative caching, ID validation, rate limiting, app-level filtering |

Examples:

- One ultra-hot product expires and 500 requests query the database at once: **stampede**.
- 100,000 products are cached together with a 5-minute TTL and all expire together: **avalanche**.
- A bot repeatedly requests non-existent products, hitting the database every time: **penetration**.

A system can suffer both an avalanche and a stampede at once: waves of keys expire together, and several ultra-hot keys among them trigger heavy duplicate queries. Protection strategies must account for both levels.

## 3. Determining required guarantees first

Not all data tolerates the same stampede-mitigation approach. Classify by business requirements:

| Data type | Can serve a stale copy? | Acceptable staleness | Handling approach |
|---|---|---|---|
| Articles, catalog metadata | Usually yes | Several minutes per business rules | TTL + single-flight + stale-while-revalidate |
| Reference prices, promotions | Conditionally | Short, must clearly define pricing point | Event-driven invalidation, tuned TTL, re-check at checkout |
| Displayed stock count | Conditionally | May differ from transactional inventory | Cache reads but re-verify when reserving stock |
| Access permissions, account lock state | Generally should not rely on arbitrary stale | Very low | Authoritative source, reliable invalidation |
| Balances/financial transaction records | Never use stale as final basis | Strict consistency rules | Transact at the appropriate data source |

Key question: when Redis misses or the source is slow, is the application allowed to **wait**, **return a stale copy**, **reject cleanly**, or **return a fallback value**?

If real-time accuracy is mandatory, do not serve stale data just to reduce load. You can accept higher latency or protect the source with concurrency limits and return an explicit error.

## 4. Why `@Cacheable` alone is not enough

Spring Cache allows:

```java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogQueryService {

    private final ProductStore store;

    public CatalogQueryService(ProductStore store) {
        this.store = store;
    }

    @Cacheable(cacheNames = "productById", key = "#p0")
    public ProductView findById(String productId) {
        return store.findById(productId);
    }
}
```

Execution flow:

1. Spring Cache checks the key in the `productById` cache.
2. On a hit, returns the cached value without calling `store.findById`.
3. On a miss, runs the source-loading method and puts the result into the cache.

What is missing is **coordination across concurrent misses**. If 200 requests arrive before the first load finishes, they can all take the miss branch and invoke the method simultaneously.

### 4.1. How can `@Cacheable(sync = true)` help?

```java
@Cacheable(
        cacheNames = "productById",
        key = "#p0",
        sync = true)
public ProductView findById(String productId) {
    return store.findById(productId);
}
```

`sync = true` asks Spring Cache to synchronize value loading for the same key if the cache provider implements it. The goal is avoiding multiple threads computing the same value within whatever scope the provider guarantees.

However, **do not assume `sync = true` guarantees only one database request across all 10 application instances**. Whether locking is local or distributed, lock granularity, concurrent load behavior, and timeouts depend on the `Cache` implementation, Redis cache writer, and your library version's configuration.

Limitations of `sync = true` in Spring Cache to note:

- Only **one cache** may be declared for that operation.
- Cannot be combined with `unless` because loading is synchronized under the cache loader contract.
- Do not treat the annotation as a distributed lease, fencing token, or business consistency lock.
- When using locking at the Redis cache writer level, understand that **lock scope** may be wider than a single entry; cache-name-level locking reduces duplicate loads while making independent keys wait on each other.

Measure in a multi-instance deployment before choosing this as your sole hot-key solution.

## 5. Defense-in-depth layers against stampedes

Do not depend on a single technique. A resilient strategy typically combines multiple layers:

```text
           Read data request
                  |
                  v
              Redis GET
                  |
           +------+------+
           |             |
         HIT            MISS
           |             |
           v             v
      Return value   Stampede-prevention layer
                         |
                +--------+--------+
                |                 |
            Someone is        Nobody is
            loading           loading yet
                |                 |
                v                 v
         Wait with bound      Acquire load right
         or return stale          |
                |                 v
                |             Call source
                |                 |
                +---------+-------+
                          |
                          v
                     Cache value
                          |
                          v
                     Return result
```

Layers that can work together:

1. **Sensible TTL and TTL jitter** to reduce mass expirations.
2. **In-JVM single-flight** to coalesce duplicate requests within one instance.
3. **Redis distributed lock/lease** if loads must be coalesced across multiple instances.
4. **Stale-while-revalidate** if business rules allow serving slightly stale data briefly.
5. **Refresh-ahead / prewarming** for predictable hot keys.
6. **Concurrency limits, timeouts, and circuit breakers** to protect the source when cache cannot help.
7. **Negative caching** to cut repeated queries for non-existent IDs.
8. **Measurement and tuning** because raising hit rate alone does not guarantee stampedes are gone.

Not everything needs to be enabled at once. Choose techniques based on key hotness, instance count, source load cost, and freshness needs.

## 6. TTL jitter: spreading out expiration times

If many cache keys are populated in the same minute with identical TTLs, they tend to expire together. Jitter adds randomness to lifetimes to stagger expirations.

Spring Data Redis example with `StringRedisTemplate`:

```java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public void cacheProduct(
        String productId,
        String jsonValue,
        StringRedisTemplate redis) {

    String key = "cache:product:v1:" + productId;

    // Example: TTL from 240 to 300 seconds, never exceeding the 300s ceiling.
    long seconds = ThreadLocalRandom.current().nextLong(240, 301);

    redis.opsForValue().set(
            key,
            jsonValue,
            Duration.ofSeconds(seconds));
}
```

Instead of an expiration pattern like:

```text
Create 10,000 keys at 10:00:00
Fixed TTL 300s
=> almost all expire together at 10:05:00
```

it becomes:

```text
10:04:00 ├───── many keys expire staggered ─────┤ 10:05:00
```

**Important note:** TTL jitter is very effective against avalanches, yet **does not solve a stampede on a single ultra-hot key**. When `cache:product:v1:p-hot` expires and hundreds of requests arrive together, they still need coordination.

If business rules impose a hard 5-minute staleness cap, do not use "300 ± 60 seconds" jitter that lets TTL reach 360 seconds past the limit. One option is sampling randomly **below the cap**, or designing refresh/invalidation that keeps data within SLA.

## 7. In-app single-flight: coalescing concurrent requests for the same key

**Single-flight** (request coalescing) works on this principle:

- The first request encountering a miss becomes the data loader.
- Other requests for the same key **share the in-progress computation result** instead of calling the source again.
- Once complete, the in-flight state must be cleared so future misses can reload.

If one instance receives 100 concurrent requests for key `p-hot`, single-flight lets that instance hit the source just once during that reload window.

### 7.1. Java example with ConcurrentHashMap and CompletableFuture

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.function.Supplier;

public final class LocalSingleFlight<V> {

    private final ConcurrentMap<String, CompletableFuture<V>> inFlight =
            new ConcurrentHashMap<>();

    public V call(String key, Supplier<V> loader) {
        CompletableFuture<V> mine = new CompletableFuture<>();
        CompletableFuture<V> existing =
                inFlight.putIfAbsent(key, mine);

        // Another request is already loading the same key.
        if (existing != null) {
            return existing.join();
        }

        try {
            V value = loader.get();
            mine.complete(value);
            return value;
        } catch (Throwable error) {
            mine.completeExceptionally(error);
            throw error;
        } finally {
            inFlight.remove(key, mine);
        }
    }
}
```

This pattern shows the coordination structure: only one request per key in the same JVM executes `loader` at a time; requests arriving mid-load wait on the leader's `CompletableFuture`.

In production code, add policies for:

- **Timeouts and wait bounds:** `join()` has no timeout. For HTTP requests, avoid blocking threads indefinitely; use timed futures or async APIs.
- **Bounding in-flight key count:** `ConcurrentHashMap` can grow huge if millions of distinct keys miss together.
- **Not caching errors indefinitely:** when the leader fails, the map entry must be removed for controlled retries while avoiding immediate retry storms.
- **Follower exception semantics:** followers may receive `CompletionException` rather than the original exception; the service layer must classify and map errors.
- **Instance lifecycle:** restarting the app wipes the `inFlight` map; there is no cross-process coordination state.

Usage example:

```java
private final LocalSingleFlight<ProductView> singleFlight =
        new LocalSingleFlight<>();

public ProductView loadProduct(String id) {
    return singleFlight.call(id, () -> productStore.findById(id));
}
```

With shared Redis, multiple instances can still load `p-hot` concurrently, once per instance. Across 8 replicas, local single-flight can cut 500 duplicate queries down to ~8 queries, yet **does not promise strictly 1 system-wide query**.

## 8. Distributed lock on Redis: only one instance reloads

When multiple instances share Redis, one coordination approach uses a key with a TTL:

```text
cache:product:v1:p-hot      -> cache data
lock:cache:product:v1:p-hot -> temporary reload right
```

Request handling flow:

1. Try reading the cache.
2. On miss, run Redis `SET lockKey token NX PX leaseMs` to claim the right.
3. If the lock is acquired, **re-read the cache**: another request may have just finished populating it.
4. If still missing, call the source and write data to cache.
5. Release the lock **only if your token is still the owner**.
6. If the lock was not acquired, wait with a bound then re-read the cache, or return stale data per policy.

### 8.1. Why use SET NX and TTL?

`SET ... NX` creates the lock only if absent. The lock's TTL (lease) prevents holding the lock forever if a process crashes mid-flight.

Redis example:

```redis
SET lock:cache:product:v1:p-hot "unique-token" NX PX 15000
```

If successful, the current request holds a 15-second lease; if the lock already exists, the command creates no new lock.

**Never use `SETNX` followed by `EXPIRE` as two separate commands** when `SET ... NX PX` is available. If the process dies between the two commands, the lock can survive without a TTL.

**Never release a lock with an unconditional `DEL lockKey`.** An old lock may have expired and another request may have acquired it with a new token. Unconditional deletion deletes someone else's lock.

### 8.2. Lua script for safe token-checked lock release

```lua
-- KEYS[1]: lock key
-- ARGV[1]: token of the request holding the lock
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
```

The script executes as a single unit on Redis: it deletes only if the token still matches, preventing a gap between checking `GET` and running `DEL`.

In Redis versions supporting a dedicated compare-and-delete operation, the corresponding API can be considered. In Java code with Spring Data Redis, a token-comparing Lua script is a common, explicit way to express the contract.

## 9. Spring Data Redis example: loading a value with a Redis lease

The example below illustrates a read path using `StringRedisTemplate`. Data is represented as JSON strings to keep the focus on cache coordination; JSON serialization and source querying belong to `ProductSource`.

### 9.1. Defining the data source

```java
public interface ProductSource {

    // Returns JSON formatted according to the cache contract.
    // May throw an exception if the source is unavailable.
    String loadProductJson(String productId);
}
```

### 9.2. Read service preventing duplicate loads

```java
import java.time.Duration;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheLoader {

    private static final Duration CACHE_TTL = Duration.ofMinutes(5);
    private static final Duration LOCK_LEASE = Duration.ofSeconds(15);

    // Cap how long a non-lock-holding request waits for the result.
    private static final long MAX_WAIT_MS = 600;

    private static final RedisScript<Long> UNLOCK_SCRIPT = unlockScript();

    private final StringRedisTemplate redis;
    private final ProductSource source;

    public ProductCacheLoader(
            StringRedisTemplate redis,
            ProductSource source) {
        this.redis = redis;
        this.source = source;
    }

    public String getProductJson(String productId) {
        String dataKey = "cache:product:v1:" + productId;
        String lockKey = "lock:cache:product:v1:" + productId;

        String cached = redis.opsForValue().get(dataKey);
        if (cached != null) {
            return cached;
        }

        String token = UUID.randomUUID().toString();
        Boolean locked =
                redis.opsForValue().setIfAbsent(lockKey, token, LOCK_LEASE);

        if (Boolean.TRUE.equals(locked)) {
            try {
                // Double-check: avoid loading if another request just wrote the cache.
                String again = redis.opsForValue().get(dataKey);
                if (again != null) {
                    return again;
                }

                String fresh = source.loadProductJson(productId);
                if (fresh == null) {
                    // Example skips caching null; production needs negative caching.
                    return null;
                }

                redis.opsForValue().set(dataKey, fresh, CACHE_TTL);
                return fresh;
            } finally {
                // Delete the lock only if the token is still ours.
                redis.execute(UNLOCK_SCRIPT, List.of(lockKey), token);
            }
        }

        // Another request is loading. Wait with a bound then re-read cache.
        return waitForCachedValue(dataKey);
    }

    private String waitForCachedValue(String dataKey) {
        long deadline = System.nanoTime()
                + TimeUnit.MILLISECONDS.toNanos(MAX_WAIT_MS);

        while (System.nanoTime() < deadline) {
            String value = redis.opsForValue().get(dataKey);
            if (value != null) {
                return value;
            }

            long pauseMs = ThreadLocalRandom.current().nextLong(20, 61);
            try {
                Thread.sleep(pauseMs);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                        "Interrupted while waiting for cache", interrupted);
            }
        }

        throw new CacheBusyException(
                "Timed out waiting for another cache loader");
    }

    private static RedisScript<Long> unlockScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setScriptText(
                "if redis.call('GET', KEYS[1]) == ARGV[1] then " +
                "return redis.call('DEL', KEYS[1]) " +
                "else return 0 end");
        script.setResultType(Long.class);
        return script;
    }

    public static class CacheBusyException extends RuntimeException {
        public CacheBusyException(String message) {
            super(message);
        }
    }
}
```

Highlights:

- Reads cache first to avoid lock overhead on hits.
- `setIfAbsent(lockKey, token, duration)` corresponds to `SET NX` with a lease duration.
- **Double-check** after acquiring the lock avoids querying the source if the value has already appeared.
- Only the lock-holding request calls the source; other requests wait and re-read Redis.
- Uses a unique token and Lua compare-delete to avoid deleting another request's lock.
- Wait time is bounded; instead of flooding the database after a timeout, the example throws a meaningful error so the API layer can return `503` or fall back.

### 9.3. This is a coordination example, not an absolute distributed lock guarantee

Several limitations must be addressed before using this for critical business flows:

1. If loading from the source takes **longer than 15 seconds**, the lease expires and another instance can claim the lock and load the same key; two loaders can then run concurrently.
2. An older loader finishing after a newer loader can overwrite fresher data with an older result. A Redis lease alone **does not protect data version ordering**.
3. Redis failover/replication can leave lock state inconsistent with both sides' expectations.
4. If Redis fails after the source loads but before writing cache, the caller can receive an error; do not retry the source endlessly.
5. If the source returns `null` or throws an exception, followers never see the cache key created and may wait until the deadline. Negative caching or failure signaling is needed when missing keys are common.
6. `Thread.sleep` blocks the waiting HTTP thread. Under heavy load, this can exhaust thread pools; reactive apps should use appropriate non-blocking mechanisms and strictly avoid `block()` on the event loop.
7. The example has no lock renewal. If longer leases are needed, renew only while checking the token, or cap source load time and recover cleanly on lease expiry.
8. Results returned after writing to the cache must still satisfy the application's freshness and authorization requirements.

**Principle:** a Redis lock for stampede prevention is a load optimization mechanism, and should not double as an absolute consistency lock for payments, balance recording, or final stock decisions.

## 10. Lease length, tokens, and fencing: why can a lock expire while the loader is still running?

Consider two instances:

```text
10:00:00  A acquires lock, TTL 10s
10:00:01  A starts calling database but is slow
10:00:10  A's lock expires
10:00:11  B acquires a new lock and calls database
10:00:12  B writes cache with new data version
10:00:15  A finishes and writes old copy to cache
```

Token-checked Lua unlock prevents **A from deleting B's lock**, yet does not stop **A from writing stale data to the data key**. These are two distinct problems:

- **Lock ownership:** who is allowed to release or renew the lock?
- **Write ordering:** which loader's result is still valid to store in the cache?

Mitigations depending on risk level:

- Pick a lease longer than **p99 source load time** under normal conditions, paired with timeouts on source calls.
- Renew the lease only when truly needed and only while the token still matches. Never renew indefinitely.
- Use a **source version** (e.g., record version number or a reliable monotonic timestamp) and write to cache only if the new version is not older than the current version.
- Use a fencing token issued by a reliable monotonic generator, with the receiving storage actually checking the token. Issuing a token that storage never validates **provides zero fencing**.
- For cached data tolerating brief staleness, TTL can bound stale windows while keeping overwrite risk in mind; for strongly consistent data, revise the update design or source of truth.

Do not choose `lock TTL = 5 seconds` just because "the database is usually fast." Account for connections, GC pauses, timeouts, high load, and failover.

## 11. Stale-while-revalidate: returning old data while loading a fresh copy

In many systems, users accept catalog information being one or two minutes stale in exchange for steady API latency. In that case, you can use a **logical TTL** instead of letting Redis delete the data outright when refresh is needed.

An entry carries both its content and logical deadlines:

```json
{
  "value": {
    "id": "p-100",
    "name": "Wireless Mouse",
    "price": 199000
  },
  "refreshAfterEpochMs": 1780000000000,
  "hardExpireAtEpochMs": 1780000120000,
  "version": 42
}
```

This is a **format example**, not a mandatory Spring Data Redis payload. The timestamps illustrate two milestones; in real apps compute them from current time with proper clock/skew policies.

- Before `refreshAfterEpochMs`: data is **fresh**, return directly.
- After `refreshAfterEpochMs` but before `hardExpireAtEpochMs`: data is **stale yet within the allowed window**; return it immediately while one worker runs a refresh.
- After `hardExpireAtEpochMs`: data is **no longer permitted to be served**; requests must wait for a fresh load or handle error/fallback.

The physical Redis key TTL must be long enough to retain the entry through the stale window, yet no longer than required by retention policy. For example, logical refresh after 5 minutes, max stale 2 minutes, physical Redis TTL around 7 minutes or designed accordingly.

### 11.1. Read flow with soft TTL and hard TTL

```text
          GET cache:product:p-100
                    |
              +-----+-----+
              |           |
           Absent       Present
              |           |
              v           v
       Cold miss flow   Check timestamps
                          |
                +---------+---------+
                |         |         |
             Fresh      Stale     Past hard TTL
                |         |         |
                v         v         v
          Return now  Return old  Do not serve stale
                         |           |
                         v           v
                   Try to claim   Controlled wait/
                   refresh lock   fresh load
                         |
                   +-----+-----+
                   |           |
                 Leader      Follower
                   |           |
                   v           v
            Background      Do not call source
             refresh
                   |
                   v
              Write new copy
```

Key trait: while a stale entry is still usable, follower requests **do not wait** on the database; they receive the older copy within a business-approved window.

### 11.2. Implementation pseudocode pattern

```text
read(key):
    entry = redis.get(key)

    if entry exists and now < entry.refreshAfter:
        return entry.value

    if entry exists and now < entry.hardExpireAt:
        if tryAcquireRefreshLease(key):
            scheduleRefreshWithoutBlockingRequest(key, entry.version)
        return entry.value

    // Missing entry or past hard deadline.
    return loadThroughSingleFlightOrLock(key)
```

`scheduleRefreshWithoutBlockingRequest` must use a bounded executor/queue with error handling. **Never spawn a new thread for every stale request.** Even with a Redis lock, if every request queues a refresh task in an executor, queues can blow up even for tasks that will lose the lock; deduplicate at the scheduling layer or try acquiring the lock first.

### 11.3. Conditions where stale data must not be served

Do not use stale-while-revalidate when old data causes unacceptable harm, such as:

- Access permissions were just revoked.
- An account has been locked.
- Final checkout price is not confirmed at the source.
- Data directly drives transactional decisions with no re-check mechanism.

Stale data needs explicit time bounds and, where useful, observational metadata like `dataAgeSeconds`. Do not turn hard TTL into "serve stale forever until the source recovers" unless the business explicitly permits it.

## 12. Refresh-ahead and prewarming for hot keys

Another approach is **not waiting until an entry expires before reloading it**.

- **Refresh-ahead:** when an entry has little TTL remaining or passes a soft TTL mark, proactively load a fresh copy.
- **Scheduled warming:** a periodic job preloads keys predicted to receive heavy traffic.
- **Event-driven invalidation/refresh:** when the source changes, emit an event to refresh the cache.

For example, a product catalog has frequently queried keys:

```text
cache:product:p-hot-1
cache:product:p-hot-2
cache:product:p-hot-3
```

A job can iterate a known hot-key list and refresh in batches with bounded concurrency. Avoid running `KEYS *` on production Redis to "discover all hot keys"; use top-key lists from access metrics or a dedicated registry instead.

For refresh-ahead, decide:

1. **How to identify keys worth refreshing?** Do not refresh rarely used keys.
2. **How many keys refresh in parallel?** Cap it so the job doesn't become a massive background load.
3. **What if refresh fails?** Keep serving bounded stale data or not?
4. **What if multiple instances run the scheduler?** Use proper ownership/leases.
5. **What if the source emits a change event?** Ensure refresh cannot overwrite a newer version with data read before the event.

Refresh-ahead cuts cold misses, yet still requires fallback when caches start empty after fresh deploys, Redis evictions, or failover.

## 13. Negative caching: preventing storms on non-existent keys

If `productStore.findById("missing-id")` always returns `null`, standard caching may **not store the miss result**. Subsequent requests keep querying the source.

One strategy is storing a **sentinel** or "not found" result DTO with a short TTL:

```text
cache:product:v1:p-404
    -> {"found":false}
    -> TTL 15 seconds
```

Rules:

- Distinguish "does not exist" from "source error" or "access denied".
- Keep negative TTL short if the record might soon be created.
- When an entity is created or changes state, proactively delete or overwrite the negative cache.
- Never cache 5xx responses or timeouts as "does not exist".
- Limit unknown keys to stop users or bots from creating unbounded sentinels.

In the distributed lock example earlier, the leader returned `null` without writing anything to Redis. Followers waiting on cache never see a value appear either; if this flow is common, a negative sentinel lets the leader inform followers of the miss and avoid repeated queries.

**Spring Cache `unless = "#result == null"`** prevents caching null. For negative caching, explicitly design how null/`Optional` or a result wrapper is stored, and verify serializer/cache manager support.

## 14. Concurrency limits, timeouts, and backpressure

Single-flight and locks reduce duplicate queries for **the same key**, yet do not solve thousands of distinct keys missing simultaneously—for instance when Redis is wiped and every key needs the database.

Therefore, add a **cap on total concurrent loaders**:

```text
Total cache misses
     |
     v
Semaphore / bulkhead (e.g. max 30 DB loaders)
     |
  +--+----------------+
  |                   |
Slot granted       No slot
  |                   |
  v                   v
Call database      Short wait / stale /
with timeout       503 / fallback
  |
  v
Write cache
```

Illustrative Java pattern:

```java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

public class LoadBulkhead {

    private final Semaphore slots = new Semaphore(30);

    public <T> T withPermit(Supplier<T> loader) {
        boolean acquired;
        try {
            acquired = slots.tryAcquire(100, TimeUnit.MILLISECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", e);
        }

        if (!acquired) {
            throw new IllegalStateException("Cache source is busy");
        }

        try {
            return loader.get();
        } finally {
            slots.release();
        }
    }
}
```

`30` and `100 ms` are only example parameters. Tune them to database capacity, source call duration, instance count, and endpoint SLOs.

When combining techniques, place the bulkhead right before **actually calling the source**, rather than gating every cache hit. If a request waiting on a lock holds a bulkhead slot, true loaders can get blocked by followers.

Beyond semaphores:

- Limit waiting request counts (queue length) and deadlines.
- Set source timeouts shorter than the overall API timeout.
- Enable circuit breakers when the database/API suffers sustained errors.
- Use bounded retries with jittered backoff; avoid synchronized retry storms.
- For reactive APIs, use non-blocking concurrency controls.
- When the cache server goes down, decide fail-open to source vs. fail-closed based on overload risk and data criticality.

## 15. Cache expiration and eviction are not the same

In Redis:

- **Expiration:** key is removed when TTL runs out.
- **Eviction:** Redis drops keys under `maxmemory-policy` when under memory pressure.
- **Explicit invalidation:** application calls `DEL` or Spring Cache eviction when source data changes.

A request seeing a miss cannot reliably distinguish these causes without metrics or extra context. Stampede defense must cover all three:

| Miss cause | Behavior to consider |
|---|---|
| Hot key TTL just expired | Single-flight/lease, stale-while-revalidate, refresh-ahead |
| Redis eviction due to low memory | Shrink value size, tune cache policy, keep bulkheads |
| New deploy leaves cache cold | Prewarm and rate-limit batch loads |
| Database updated and evicted cache | Coordinated reload, do not serve stale if forbidden |
| Redis outage | Circuit breaker, cap source load, policy-driven fallback |
| Key does not exist | Negative caching and validation |

Raising TTL to dodge stampedes cuts miss frequency yet increases staleness and memory usage. Only raise TTL when freshness allows it; never treat it as a substitute for coordination.

## 16. Spring Cache decision: `sync=true` or distributed lease?

If the app uses `@Cacheable` with `RedisCacheManager`, you can try `sync = true` for minimal boilerplate. Still, verify the coordination scope in **your exact Spring Data Redis and RedisCacheWriter version**.

### 16.1. Simple case

```java
@Cacheable(
        cacheNames = "catalogDetail",
        key = "#p0",
        sync = true)
public CatalogDetail getDetail(String productId) {
    return source.loadDetail(productId);
}
```

Works when the app has few instances, the source tolerates occasional duplicate loads, and measurements confirm the cache setup sufficiently reduces concurrency.

### 16.2. When is an explicit coordination mechanism needed?

Consider a dedicated Redis lease/soft-TTL flow when:

- Many replicas share the same hot keys.
- The source handles load poorly and one stampede can cause an outage.
- You need precise control over follower wait times or stale serving.
- You want metrics on lock owners, follower counts, refresh duration, and stale responses.
- You need soft/hard TTL splits or per-entry TTLs that don't fit existing config.
- You must avoid unrelated keys locking one another due to overly broad lock scope.

**Do not stack locking mechanisms blindly:** combining `@Cacheable(sync = true)`, a manual Redis lock, and local single-flight can create layered waits and hard-to-debug stalls. Each layer needs a clear role, ordered deadlines, and distinct metrics.

### 16.3. Self-invocation remains a trap

With proxy-based Spring Cache, calling one method from another **inside the same bean** generally bypasses cache advice:

```java
@Service
public class CatalogService {

    @Cacheable(cacheNames = "catalogDetail", key = "#p0", sync = true)
    public CatalogDetail getDetail(String id) {
        return source.loadDetail(id);
    }

    public CatalogDetail exportOne(String id) {
        return getDetail(id); // self-invocation: can bypass cache advice.
    }
}
```

The straightforward fix is extracting `getDetail` into a Spring bean injected into the caller service. If no proxy runs, `sync = true` has no effect either.

## 17. Invalidation when source data changes

Stampedes are often discussed around TTL expiration, yet **explicit invalidation** can also trigger mass misses. For example, after updating a hot product, the system runs:

```java
@CacheEvict(cacheNames = "productById", key = "#p0")
public void updateProduct(String id, UpdateCommand command) {
    productStore.update(id, command);
}
```

Right after eviction, hundreds of requests can ask for that ID at once. A coordinated reload path is still required.

Two tensions must be resolved:

1. **Freshness:** never serve an old copy after data changed if business rules forbid it.
2. **Load:** don't let every request hit the source during the reload window.

Options include:

- After commit, write-through the cache with the new copy if the exact value can be computed/read.
- Emit an invalidation event with version, then refresh via single-flight.
- Temporarily serve bounded stale data, **never** serving stale invalidated by sensitive changes.
- For APIs with multiple dependent caches, identify all affected keys so some don't stay stale longer than expected.
- Use versioned keys to keep stale loaders from overwriting newer versions.

Setting a very long TTL without invalidation reduces misses at the cost of unbounded stale data.

## 18. Load testing: evaluating stampede protection by source call count

Measuring normal cache performance at high hit rates is not enough. You must **reproduce many requests missing the exact same key**.

### 18.1. Test scenarios

Prepare a test key `p-hot` and an endpoint loading source data with a steady simulated latency. Run multiple application instances if production uses multiple instances.

Steps:

1. **Warm cache:** populate `p-hot` and verify hit requests never query the source.
2. **Cold burst:** delete that exact test key and fire 100–1,000 concurrent requests.
3. **Expiration burst:** use a controlled short TTL so many requests land right as the entry expires.
4. **Slow source:** increase source query latency to observe the miss window.
5. **Leader failure:** make the loader throw an exception or time out; check whether followers stampede.
6. **Lease expiry:** make load time exceed the lease; observe a second loader appearing and overwrite risks.
7. **Redis outage:** check how the application protects the database.
8. **Multiple-key miss:** miss many distinct keys together to validate bulkheads, not just single-flight.

### 18.2. Metrics to monitor

| Metric | Question to answer |
|---|---|
| `cache_hit_total` / `cache_miss_total` | How do hits and misses shift? |
| `source_load_total` tagged by key/category | How many real source calls did a burst produce? |
| `inflight_loads` | How many loaders are running concurrently? |
| `coalesced_requests_total` | How many requests shared a leader's result? |
| `lock_acquired_total` / `lock_contended_total` | How many lock acquisitions succeeded vs. contended? |
| `lock_wait_duration` | How long did followers wait? |
| `lock_lease_expired_total` | Did loaders outlive their lease? |
| `stale_served_total` and `data_age_seconds` | How often was stale served, and how old was it? |
| `source_load_duration` p50/p95/p99 | Do slow loaders widen miss windows? |
| `source_bulkhead_rejected_total` | How many requests were shed to protect the source? |
| `cache_reload_error_total` | Reload failure rate and recovery behavior |
| Redis memory/evictions/command rate | Did Redis load spike or evict unexpectedly? |

Set thresholds per business goals. For example, with 500 concurrent requests for **one key**, the target might be 1 to a few source calls per load window; the exact count depends on coordination scope, leases, and errors, so never promise an absolute number architecturally before testing.

### 18.3. Observing Redis

```bash
redis-cli INFO stats
redis-cli INFO commandstats
redis-cli INFO memory
redis-cli SLOWLOG GET 10
```

`INFO` reports instance-wide metrics and does not isolate cache misses of one endpoint. `SLOWLOG` tracks Redis command execution time, excluding time waiting on external data sources. Successful stampede mitigation can produce **more Redis reads** from follower polling while generating **far fewer database queries**; evaluate the whole picture rather than Redis command count alone.

To watch for overly long locks, inspect a specific lock key's TTL in a suitable environment:

```bash
redis-cli PTTL 'lock:cache:product:v1:p-hot'
```

Avoid running `MONITOR` continuously on busy production Redis to capture every command; it adds load and risks exposing command payloads.

## 19. Design patterns and trade-offs

| Technique | Reduces concurrent loads of one key? | Across multiple instances? | Follower latency | Main trade-off |
|---|---|---|---|---|
| TTL jitter | Not guaranteed | Applies to expiration schedule | Unchanged on miss | Mitigates avalanches more than single-key stampedes |
| `@Cacheable(sync = true)` | Possibly, per cache provider | Not guaranteed cluster-wide by default | Waits on loader | Depends on implementation/lock scope |
| Local single-flight | Yes within JVM | No | Waits on leader future | No protection across replicas |
| Redis lease/lock | Yes while lease is valid | Yes, via shared Redis | Bounded wait or fallback | Lease, token, error, and version management |
| Stale-while-revalidate | Yes, followers get stale | Yes if refresh is coordinated | Typically very low | Must allow stale data |
| Refresh-ahead/prewarm | Cuts chance of misses | Yes if jobs are coordinated | Low when warm succeeds | Background load and refresh scheduling |
| Negative caching | Cuts misses for missing data | Yes when stored in shared Redis | Low once sentinel exists | Risk of returning "not found" during TTL |
| Bulkhead/queue limit | Protects overall source | Per deployment scope | May reject or wait | Does not generate cache hits on its own |

When layering mechanisms, align deadlines:

```text
Total HTTP timeout:       1,000 ms
Redis cache GET:             50 ms (illustrative budget)
Max lock wait:              300 ms
Max source load:            500 ms
Processing/serialize buffer: remainder
```

These numbers only illustrate budget splitting; real timeouts depend on infrastructure. Never set three independent 2-second timeouts and expect the endpoint to meet a 1-second SLO.

## 20. Operational scenario: 8 instances and one ultra-hot product

An application runs 8 instances using Redis cache for product `p-top`. At one moment 800 nearly concurrent requests arrive. The database takes 150 ms to load the product.

### Design A — Plain cache-aside only

```text
800 requests -> all see MISS
             -> many requests query database independently
             -> almost all SET cache
```

Source queries can spike dramatically if many requests enter the miss window before the cache is populated. The database overloads easily; the slower the load time, the more requests pile up.

### Design B — Per-instance local single-flight

```text
800 requests
  |
  +-- Instance 1 -> one loader, followers wait
  +-- Instance 2 -> one loader, followers wait
  ...
  +-- Instance 8 -> one loader, followers wait
```

If requests balance evenly and each instance coalesces misses per key, source queries in the window can drop from huge numbers down to around **8 queries**. Yet multiple instances still duplicate work.

### Design C — Per-key Redis lease + cache recheck

```text
800 requests
  |
  +-- Multiple instances see MISS
         |
         +-- One instance wins the lease
         |      |
         |      +-- re-read cache
         |      +-- query database
         |      +-- SET cache
         |      +-- release lock by token
         |
         +-- Remaining instances wait briefly and re-GET
```

Under normal conditions, source loads per miss cycle drop close to one. Still, if the lease expires early, the source errors, a process dies, or Redis fails over, multiple loaders can still run. This is a **load-reduction target**, not an exactly-once proof.

### Design D — Stale-while-revalidate

Upon reaching the soft TTL mark:

```text
800 requests -> read stale entry within bounds
             -> return immediately to client
             -> one leader refreshes in background
             -> updates cache on success
```

Read latency stays steadier if stale data is permitted. Once past the hard TTL without a successful refresh, the system must fall back to the cold-miss flow or error/fallback per policy; never serve stale indefinitely.

### Recommended combined design

- Redis stores entries with soft/hard TTL for data permitting staleness.
- Per-key coordination for refreshes and cold misses.
- TTL jitter so many keys do not hit hard misses together.
- Bulkheads around all loaders calling the database.
- Negative caching for non-existent IDs where appropriate.
- Invalidation on source changes, guarded against overwriting newer versions.
- Metrics for source queries per burst, wait duration, and stale responses.

## 21. Common pitfalls in stampede prevention

### 21.1. Using a Redis lock without a TTL

If the leader crashes, the lock stays forever; followers wait or fail. Always enforce a bounded lease or proper recovery.

### 21.2. Deleting a lock with unconditional DEL

A request whose old lock expired can delete a new request's lock. Use owner tokens and atomic compare-and-delete.

### 21.3. Skipping cache double-check after acquiring the lock

While the request waited for the lock, someone else already populated the key. Without re-reading, the app runs redundant source queries.

### 21.4. Using a lock with no follower timeout

When the leader stalls or dies, followers wait endlessly and exhaust thread pools. Enforce deadlines, fallbacks, or clean error responses.

### 21.5. Lease shorter than source load time

The lock expires, a second loader enters, and stale results can overwrite fresh ones. Account for p99 load times, conditional renewal, and versioning/fencing where needed.

### 21.6. Retrying the source immediately when lock acquisition fails

The point of the lock is stopping every request from calling the source. If followers fail to get the lock and query the database immediately anyway, stampede protection is defeated.

### 21.7. Relying solely on TTL jitter

Jitter staggers expiration across **many keys**, not a stampede on **a single hot key** when it expires.

### 21.8. Serving stale for data that cannot be outdated

Never serve stale for financial, security, or final inventory decisions without explicit re-verification rules.

### 21.9. Scheduling an async refresh task per stale request

Even if a Redis lock lets only one task call the source, the executor can still receive thousands of queued tasks for the same key. Deduplicate scheduling and bound queues.

### 21.10. Failing to distinguish source null from source error

Without valid negative caching, all requests for missing IDs wait and re-query. Conversely, caching timeouts as "not found" returns false errors for real data.

### 21.11. Relying on sync=true without testing multiple replicas

Synchronization scope and guarantees depend on the provider. Measure in a real deployment instead of inferring from the annotation name.

### 21.12. Sending all traffic to the database during a Redis outage

A Redis outage can trigger a system-wide avalanche. If every request fails open simultaneously, the database becomes the second failure point. Enforce bulkheads, rate limits, circuit breakers, and graceful degradation.

## 22. Strategy selection workflow

```text
Cache miss occurred?
        |
        v
Is it a hot key or many keys missing together?
        |
  +-----+-----+
  |           |
Hot key     Many keys
  |           |
  v           v
Single-flight/ TTL jitter +
per-key lock   bulkhead/prewarm
  |           |
  +-----+-----+
        |
        v
Can bounded stale data be returned?
        |
   +----+----+
   |         |
  Yes        No
   |         |
   v         v
Soft/hard  Wait for loader with
TTL + SWR  explicit deadline
   |         |
   +----+----+
        |
        v
Source returns null or error?
        |
   +----+----+
   |         |
  Null     Error
   |         |
   v         v
Short-TTL  Bounded retry /
negative   circuit breaker /
cache      avoid load storm
   |         |
   +----+----+
        |
        v
Measure real source calls,
p95/p99, lock wait, and stale age
```

**Conclusion:** Preventing cache stampedes is not simply setting a longer TTL. In Spring Data Redis, you must **coordinate requests loading the same key**, pick clear wait limits and fallbacks, and protect the database when many keys miss together. `@Cacheable(sync = true)`, in-JVM single-flight, Redis leases, stale-while-revalidate, and refresh-ahead are tools with distinct scopes and trade-offs. A solid design reduces real source calls, stays within staleness limits, avoids self-inflicted retry storms, and remains observable when leaders fail, leases expire, or Redis is temporarily unavailable.
