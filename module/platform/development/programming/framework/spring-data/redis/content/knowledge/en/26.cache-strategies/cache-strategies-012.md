# Verifying Consistency Instead of Assuming Cache Always Holds the Latest Data

When using **Spring Data Redis** and **Spring Cache**, applications routinely store data copies in Redis to lower latency and cut database queries. Fast cache hits, successful Redis responses, and remaining TTLs are useful operational signals. However, **they do not prove the data is the latest version**.

Suppose the database committed a new product price while Redis still holds the previous price. Users reading from cache receive stale data with no exception thrown. Even with `@CacheEvict`, post-commit sync, or short TTLs, failure windows and race conditions can leave old copies behind or repopulate them.

Consequently, a caching strategy must be **verified**: what is the source of truth, how much staleness is acceptable, which version does each entry carry, how long do discrepancies persist, and does the system converge automatically when Redis or application processes fail?

This lesson walks from defining a consistency contract to measurement techniques, concurrency testing, stale-cache detection, and controlled remediation.

## 1. What does a consistent cache mean?

Suppose the system holds:

```text
Database (authoritative source):
  productId = 42
  price     = 950000
  version   = 12

Redis cache:
  key       = productsById::42
  price     = 900000
  version   = 11
  ttl       = 180 seconds
```

Redis has the key with remaining lifetime, yet the cache is at **version 11** while the source has moved to **version 12**.

Distinguish clearly:

- **Source of truth:** the authoritative system defining business state, typically a database or origin service.
- **Cache entry:** a copy optimizing reads whose lifecycle can diverge from the source.
- **Freshness:** how closely the cache reflects the source state at observation time.
- **Stale read:** a read returning an older snapshot than the acknowledged source state.
- **Convergence:** the process by which cache state catches up once writes and sync stabilize.
- **Consistency contract:** the guarantee an application promises to readers.

Each feature may require a different contract:

| Requirement | Meaning | How to verify |
|---|---|---|
| **Eventual consistency** | When writes stop and sync runs, cache eventually catches up | Track versions until aligned and detect non-converging keys |
| **Bounded staleness** | Cache is never older than a defined limit, e.g., a few seconds | Measure from source commit until the read path reflects the new version |
| **Read-your-writes** | A writer immediately sees their own change on subsequent reads | Update and immediately GET through the real API path |
| **Monotonic reads** | A session that observed v12 never regresses to v11 later | Track versions across sequential requests within a session |
| **Strict correctness for critical decisions** | Never decide solely from potentially stale caches | Test with stale cache, Redis errors, and recent permission/balance changes |

Never claim "the cache is always accurate" without specifying which consistency level is guaranteed.

## 2. Redis does not automatically know when the database commits

In **cache-aside**, the application coordinates reads and writes:

```text
READ:
Client -> Redis GET
           |
           +-- HIT --> Return cache
           |
           +-- MISS --> Read database
                          |
                          +--> Write Redis with TTL
                          |
                          +--> Return data

WRITE:
Client -> UPDATE database -> COMMIT
                                |
                                +--> UPDATE / EVICT Redis
```

Redis does not listen to SQL transactions on its own. After the database commits, the application must proactively invalidate or update the cache. Both systems maintain separate connections and transactions; one step can succeed while the other fails.

Example:

```java
@Transactional
public void updatePrice(long id, BigDecimal price) {
    Product product = repository.findById(id).orElseThrow();
    product.setPrice(price);
    cacheManager.getCache("productsById").evict(id);
}
```

Looking at this method alone does not tell you whether eviction executes before or after commit, because it depends on the cache manager, transaction synchronization, and actual invocation timing.

## 3. What does not count as proof of cache freshness?

| Observation | What is known | What remains unproven |
|---|---|---|
| Redis `GET` returns a value | Key is readable | Value matches the newest source state |
| `EXISTS key = 1` | Key exists | Key is not stale |
| `TTL key = 180` | Redis still retains the key | Database did not change during those 180 seconds |
| 98% hit ratio | Most requests avoided querying the DB | 98% of requests received accurate data |
| `@CacheEvict` was called | App requested deletion | Deletion succeeded post-commit without stale repopulation |
| Event was published | Producer emitted message | Consumer applied it to Redis in proper order |
| HTTP 200 | API responded normally | Payload matches the consistency contract |

A system can boast ultra-low latency while serving stale copies for hours if its invalidation path is broken.

## 4. The authoritative source must be read properly

Suppose you have a primary database and a read replica:

```text
DB primary:       product 42 version 12
DB read replica:  product 42 version 11
Redis cache:      product 42 version 12
```

If a reconciliation tool treats the lagging read replica as the "authoritative answer", it will falsely conclude Redis holds an invalid version.

To verify properly, pick the right read target matching the source contract—usually the primary after transaction commit. Also separate three states:

1. **Source state:** committed data in the authoritative source.
2. **Redis state:** data currently sitting in cache.
3. **Response state:** data clients actually receive from controllers, which may pass through local caches, CDNs, or other service instances.

Two consecutive reads of Redis and the database **do not form a cross-system atomic snapshot**. If concurrent writes occur between the two reads, differences may simply reflect transient states permitted by eventual consistency. Record versions, observation timestamps, and event history.

## 5. Embedding source version into cached DTOs

You can use JPA `@Version` on entities when all writers adhere to optimistic locking and version increment rules.

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;
import java.math.BigDecimal;

@Entity
public class Product {
    @Id
    private Long id;

    private String name;
    private BigDecimal price;

    @Version
    private Long version;

    protected Product() {}

    // Application constructors, getters/setters.
}
```

DTO stored in cache:

```java
import java.math.BigDecimal;

public record ProductView(
        Long id,
        String name,
        BigDecimal price,
        Long version
) {
    public static ProductView from(Product product) {
        return new ProductView(
                product.getId(),
                product.getName(),
                product.getPrice(),
                product.getVersion());
    }
}
```

Reading via Spring Cache:

```java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductQueryService {
    private final ProductRepository repository;

    public ProductQueryService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "productsById", key = "#productId")
    @Transactional(readOnly = true)
    public ProductView getById(long productId) {
        Product product = repository.findById(productId)
                .orElseThrow();
        return ProductView.from(product);
    }
}
```

On a cache hit, Spring returns the DTO from Redis **without invoking the database read method**. The version inside the DTO is the cached snapshot's version; it does not update automatically when the database commits a newer version.

`@Version` is a trustworthy version source only if every authoritative write path updates versions consistently. Raw SQL statements or external writers can bypass it. Versions also apply only per entity, not as a system-wide global order.

### Configuring `RedisCacheManager`

```java
import java.time.Duration;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class CacheConfiguration {
    @Bean
    public RedisCacheManager cacheManager(
            RedisConnectionFactory factory) {

        RedisCacheConfiguration productCache =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(5))
                        .disableCachingNullValues();

        return RedisCacheManager.builder(factory)
                .withCacheConfiguration("productsById", productCache)
                .transactionAware()
                .build();
    }
}
```

`transactionAware()` allows supported cache mutations to defer until after a Spring transaction commits, **provided** the operation runs inside an active transaction synchronization context. It does not create an atomic transaction across database and Redis.

Serializers must match DTOs and deployment environments. With JSON, define formats and schemas explicitly; avoid treating deserialization errors as ordinary cache misses without inspecting root causes.

## 6. Post-commit invalidation can still be missed

An update service:

```java
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductCommandService {
    private final ProductRepository repository;

    public ProductCommandService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(transactionManager = "transactionManager")
    @CacheEvict(cacheNames = "productsById", key = "#productId")
    public void changePrice(long productId, BigDecimal newPrice) {
        Product product = repository.findById(productId)
                .orElseThrow();
        product.setPrice(newPrice);
    }
}
```

This assumes `transactionManager` is the application's database manager. Placing `@CacheEvict` alongside `@Transactional` does not prove cache advice ordering relative to transaction advice. Confirm when the cache operation runs and which cache manager actually handles it.

Even when eviction runs after commit, failures still occur:

```text
DB COMMIT succeeds
       |
       +--> App crashes before evict callback
       |
       +--> Redis timeout/disconnect
       |
       +--> Invalidation event lost
       |
       +--> Another request writes back old payload
       |
       v
Redis may still hold old version
```

A committed database transaction never automatically rolls back just because a post-commit Redis operation failed.

## 7. Race: stale data returns after successful eviction

This is a key scenario when verifying cache-aside:

```text
Time         Request A (read)             Request B (write)
----------------------------------------------------------------
T0           Redis MISS
T1           SQL SELECT -> v11
T2                                        UPDATE -> v12
T3                                        DB COMMIT
T4                                        Redis EVICT key
T5           Redis PUT v11
T6           API returns v11
T7           Request C cache HIT v11
```

A read old data **before** B committed, yet executed cache put **after** B evicted. Both individual operations succeeded, yet Redis ends up holding v11 while the database is at v12.

**TTL does not prevent this race**: it simply starts v11's countdown at T5. If stale refills recur, the stale window stretches on.

Verification must reproduce the T1 → T3 → T4 → T5 interleaving deliberately rather than firing lots of requests and hoping bugs show up.

## 8. Race: update events execute out of order

Suppose the system uses events:

```text
DB commit v12 -> E12
DB commit v13 -> E13

Consumer processes:
  E13 -> cache v13
  E12 -> cache v12  (older event retried late)
```

Redis **regresses in version** even though every event is valid. A defensive policy:

```text
incomingVersion < cachedVersion -> ignore
incomingVersion = cachedVersion -> idempotent handling
incomingVersion > cachedVersion -> accept
```

If two consumers check versions with `GET` and write with `SET` as two separate commands, they can still interleave. Comparison and writing must be atomic within the valid key/slot scope, or a single writer must serialize updates per entity.

Once a key has been deleted and no `cachedVersion` remains, an older event can still recreate a stale entry. A watermark/tombstone version or tighter synchronization protocol may be required.

## 9. Measuring version lag and convergence latency

Two distinct questions:

- **How many updates behind?** Compare `sourceVersion` and `cacheVersion` for the same entity.
- **How long behind?** Measure elapsed time from DB commit until the defined read path returns the new version.

A cache envelope can contain:

```java
import java.math.BigDecimal;
import java.time.Instant;

public record VersionedProductCache(
        long productId,
        BigDecimal price,
        long sourceVersion,
        Instant cachedAt
) {}
```

`sourceVersion` tracks source ordering while `cachedAt` records cache write time. They mean different things. Clocks across servers can skew, so timestamps never replace versions for determining update order.

Sample observation record:

```text
productId           = 42
sourceVersion       = 13
cacheVersion        = 12
cacheObservedAt     = 2026-11-13T03:00:04Z
lastCommittedEvent  = product-42-v13
eventStatus         = waiting-retry
```

Timestamps and IDs here only illustrate format. In real measurements, anchor timing to commit timestamps supplied by the source system or a reliable time-tracking mechanism.

## 10. Comparing cache against an independent source read

Never call a `@Cacheable` `getById()` method as your "verification source", because you may read the same Redis entry twice and falsely conclude they match.

Create an independent source reader:

```java
import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductSourceReader {
    private final ProductRepository repository;

    public ProductSourceReader(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Optional<ProductView> readFromSource(long productId) {
        return repository.findById(productId)
                .map(ProductView::from);
    }
}
```

Configure this service to read from the authoritative datasource—such as the primary when read replicas lag.

Read through the same Spring Cache abstraction serving the application:

```java
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;

Cache cache = cacheManager.getCache("productsById");
if (cache == null) {
    throw new IllegalStateException("Cache missing");
}
ProductView cached = cache.get(42L, ProductView.class);
```

This avoids guessing Redis key prefixes or serializers. When raw bytes and actual TTLs are needed, supplement with Redis CLI or `RedisTemplate` using matching serializers.

| Authoritative source | Cache | Initial assessment |
|---|---|---|
| v13 | v13, fields match | Match at observation time |
| v13 | v12 | Stale |
| v13 | No entry | Cache miss, may be normal |
| Entity deleted | Entry present | Stale orphan, needs verification |
| v13 | v14 | Check replica lag or wrong source/writer |
| v13 | v13, fields differ | Version/mapping/serializer bug |
| Source readable | Cache undecodable | Cache schema/serialization error |

Sequential reads never form an atomic cross-system snapshot across Redis and the database. Under concurrent writes, check whether a commit happened between the two reads and whether eventual consistency bounds are still met.

## 11. Verifying on the real API path

A Redis entry may already be accurate while users still receive stale data if other cache layers sit in front:

```text
Browser / CDN
      |
      v
Controller
      |
      v
Service / local cache
      |
      v
Spring Redis Cache
      |
      v
Database primary / read replica
```

When **read-your-writes** is required, test end-to-end along the user's real path:

1. Client updates product 42 and receives confirmation that the transaction committed.
2. Client immediately calls GET product 42 via the HTTP API.
3. Verify the response version or fields match the newly committed update.
4. Repeat across multiple application instances and when Redis or read replicas experience lag.
5. Identify which read layer returned stale data if a check fails.

When Redis is already at v13 while HTTP returns v12, inspect local in-memory caches, CDNs, serializers, response mappers, or other instances running old code. Do not blame or tweak Redis if the bug lives upstream.

## 12. Sampling verification without destroying cache benefits

If every cache hit queried the database to verify freshness, the application would lose nearly all caching load savings.

Controlled verification approaches:

- **Sampling:** sample a tiny percentage of cache-hit requests asynchronously without affecting main responses.
- **Batch reconciliation:** scan a subset of entities/keys periodically using pagination or `SCAN`.
- **Change-triggered checks:** after commit, verify recently mutated keys within a target window.
- **Alert-triggered checks:** raise sampling rates when consumer lag, Redis errors, or event retries climb.
- **Per-session checks:** record read-your-writes violations or version regressions observed within user sessions.

For example, at 20,000 cache hits/second, 0.5% sampling adds ~100 source reads per second. Verify the database can absorb that verification load.

Random sampling can skew toward rarely modified keys, whereas high-writer keys go stale more often. To measure stale rates reliably, stratify samples by namespace, update frequency, instance, and business criticality.

A verification job should prioritize **reading and detecting discrepancies**, keeping repair in a separate mechanism. If multiple instances independently detect and overwrite caches concurrently, monitoring itself can introduce races or mask root causes.

## 13. Metrics showing how consistent the cache really is

| Metric | Interpretation | Limitation |
|---|---|---|
| Cache hit ratio | Hits / (hits + misses) | Measures performance only, not correctness |
| Sample stale rate | Samples with `cacheVersion < sourceVersion` / valid samples | Depends on sampling method |
| Version lag | `sourceVersion - cacheVersion` | Valid only within the same domain/version contract |
| Convergence latency | Time from commit until cache/read path reaches new version | Requires consistent measurement points |
| Invalidation failures | Count of failed `evict`/update calls | Misses callbacks lost without durable events |
| Outbox/event lag | Time updates wait to be processed | Signals risk of prolonged cache staleness |
| Orphan cache entries | Cache holds entities already deleted at source | Can cause business errors |
| Serialization errors | Entries failing decoding | Must distinguish schema bugs from misses |
| Redis timeout/latency | Redis infrastructure health | Does not prove every key is wrong |
| Source replica lag | Data lag on read replicas | Prevents misdiagnosing source issues |
| TTL remaining | Remaining lifetime of entries | Not data age since source commit |

Example measurable contract (illustrative only):

> Under normal operating conditions, 99.9% of committed product changes will be reflected on the product GET path within at most 5 seconds.

To verify such a requirement, specify:

- Start timestamp is database commit, not when the app started the update.
- End timestamp is **the read path returning the right version**, not merely Redis eviction.
- Handling when an entity updates across multiple versions back-to-back.
- Measurement rules during Redis/DB outages and whether error periods count in the SLO.
- Scope across tenants, instances, read replicas, and sampling intervals.

Counts of published events or sent Redis commands never replace measuring **what users actually receive**.

## 14. Controlled concurrency testing instead of waiting on luck

Rare races seldom appear in sequential tests. Rather than spawning dozens of threads hoping for failures, pin the exact execution order of critical steps.

### Scenario A — Stale refill after eviction

```text
1. Delete cache entry for product 42.
2. Set DB at version 11.
3. Request A cache MISSES then SELECTs version 11.
4. Pause A right before cache PUT.
5. Request B UPDATEs to version 12 and COMMITs.
6. Request B EVICTs cache key; confirm eviction succeeded.
7. Resume A to PUT version 11.
8. Inspect which version cache and HTTP GET return.
9. Observe whether defensive mechanisms block or heal stale v11.
```

Integration tests can use `CountDownLatch` or a test gateway inserting a pause right after SQL read / before cache put. If intercepting Spring Cache directly is awkward, wrap a test cache-aside harness solely to reproduce this schedule.

### Scenario B — Redis fails after DB commit

```text
1. Cache holds version 11.
2. Transaction updates source to version 12.
3. SQL COMMIT succeeds.
4. Inject Redis timeout right during invalidation/update.
5. Confirm DB remains at version 12.
6. Observe whether Redis still holds v11.
7. Restore Redis.
8. Watch retry, TTL, event/outbox, or reconciliation.
9. Measure until GET returns version 12.
```

Run fault injection in test environments. When post-commit callbacks fail, committed database state **does not automatically roll back**.

### Scenario C — Out-of-order events

```text
1. Commit DB v12 and emit event E12.
2. Commit DB v13 and emit event E13.
3. Deliver E13 to consumer first.
4. Deliver retried E12 late.
5. Assert Redis does not regress to v12 if monotonic updates are promised.
```

Without version gating, this test exposes backward cache overwrites. With evict-only strategies, test stale-refill exposure and read paths after events settle.

### Scenario D — SQL rollback

```text
1. Start transaction.
2. Update entity and request cache mutation.
3. Throw RuntimeException before commit.
4. Confirm database rolled back.
5. Verify Redis does not contain uncommitted data.
```

Verify cache operations run under transaction synchronization, Spring AOP advisors apply properly, and `RedisCacheManager` truly has `transactionAware()`.

### Scenario E — Reading from a lagging database replica

```text
1. Primary DB is already at version 12.
2. Read replica is still at version 11.
3. Redis is evicted.
4. Cache miss reads v11 from replica.
5. Application stores v11 in Redis.
6. Compare Redis against primary and verify eventual convergence.
```

This test separates cache staleness bugs from source-read lag.

## 15. Version gating can block backward updates

When the application **manages cache entries directly** (unlike default `RedisCacheManager`), version and payload can be stored together in a Redis Hash:

```text
product-cache:42 (HASH)
  version = 13
  payload = {"id":42,"price":950000}
```

Lua script checking and writing atomically on the same key:

```lua
-- KEYS[1] = cache key
-- ARGV[1] = incoming version
-- ARGV[2] = serialized payload
-- ARGV[3] = TTL seconds, positive integer

local incoming = tonumber(ARGV[1])
local ttl = tonumber(ARGV[3])

if not incoming or not ttl or ttl <= 0 then
    return -1
end

local oldRaw = redis.call('HGET', KEYS[1], 'version')
local oldVersion = tonumber(oldRaw)

if oldRaw and not oldVersion then
    return -2
end

if oldVersion and incoming < oldVersion then
    return 0
end

redis.call('HSET', KEYS[1],
           'version', ARGV[1],
           'payload', ARGV[2])
redis.call('EXPIRE', KEYS[1], ttl)
return 1
```

Return convention: `1` accepted write, `0` rejected stale version, `-1` invalid input, `-2` malformed existing version. Spring Data Redis can run this single-key script via `DefaultRedisScript<Long>` and `StringRedisTemplate.execute(...)`.

Understand the limitations clearly:

- This is a **custom Hash cache**, incompatible by default with entries serialized in other formats by `RedisCacheManager`.
- Once a key is deleted, no version remains to stop a stale event from recreating the cache. A watermark/tombstone or alternative source check may be needed.
- If two events share the same version yet differ in payload, define proper rules instead of allowing arbitrary overwrites.
- Versions must advance consistently at the source; raw SQL writers must never bypass them.
- Lua has integer precision bounds, and Redis Cluster imposes hash-slot rules.
- Atomicity on a Redis key never creates an atomic commit across SQL and Redis.

Version gating guards against stale overwrites, **not replacing end-to-end verification and recovery strategies**.

## 16. TTL alone cannot bound staleness measured from commit

Suppose a cache entry has a 300-second TTL:

```text
T0  Database COMMIT version 12
T1  Old request PUTs version 11, TTL 300s
T2  Another worker PUTs version 11 again, resetting TTL
T3  Redis still returns version 11
```

TTL bounds the lifetime of **each cache write**, not necessarily elapsed time since source commit. If slow readers or old events keep rewriting stale data, TTL keeps resetting.

Thus, enforcing bounded staleness requires checking:

- Does cache refill read the primary or a read replica?
- Can any writer overwrite backward?
- Do failed invalidations retry?
- Does reconciliation catch lingering entries?
- Do cache refreshes reset TTL?
- Is the SLO measured from source commit or cache write?

Lowering TTL increases miss rates and database load without eliminating underlying races.

## 17. Evict or update cache directly?

Two common strategies:

**Invalidate on write:** after DB commit, delete the cache entry so the next read fetches from the source.

```text
DB COMMIT v13
     |
     v
EVICT cache
     |
     v
Next GET MISS -> SELECT v13 -> cache v13
```

**Update on write:** after DB commit, write the new payload straight into Redis.

```text
DB COMMIT v13
     |
     v
PUT cache payload v13
     |
     v
Next GET HIT v13
```

| Criterion | Evict | Update |
|---|---|---|
| Sent to Redis | Key to delete | Payload and version |
| Next read | Usually miss | Usually hit |
| Primary risk | Evict fails, stale refill | Out-of-order events, stale overwrite |
| Safeguards | TTL, retries, reconciliation | Version gating, ordering, idempotency |
| Atomic with DB | No | No |

Evict is usually simpler when the database is the source of truth; update fits when keeping caches hot matters. Both must be verified against infrastructure faults and concurrent updates.

## 18. Transactional outbox keeps sync requests from disappearing

Relying only on an in-memory `@TransactionalEventListener(AFTER_COMMIT)` callback risks losing events if the process dies after DB commit yet before the callback runs. That event is never saved for replay.

**Transactional outbox** persists business changes and sync requests inside **the same database transaction**:

```text
Request
   |
   v
DB transaction
  /           \
 v             v
UPDATE entity  INSERT outbox event
  \           /
     COMMIT
        |
        v
Durable pending event
        |
        v
Worker -> Redis update/evict
       /      \
    Success   Failure
      |         |
   Mark done   Retry
```

Workflow:

1. Persist data updates and the outbox row inside one SQL transaction.
2. Commit successfully so the event is durable.
3. Consumers read unprocessed events and update Redis.
4. Retry on error; mark processed on success.
5. Use event IDs/versions to guard against duplicate or out-of-order processing.
6. Monitor lag from DB commit until Redis sync completes.

Conceptual example:

```java
@Transactional
public void changePrice(long productId, BigDecimal price) {
    Product product = repository.findById(productId).orElseThrow();
    product.setPrice(price);

    outboxRepository.save(
            OutboxEvent.productChanged(productId));
}
```

If events must carry the post-update version, verify when JPA updates `@Version` (flush/commit) and read it reliably. Never assume an in-memory version incremented before flush.

Outbox gives **crash recovery**, though caches remain eventually consistent and consumers can receive duplicate events. Design idempotency, retries, and ordering.

## 19. Remediating a stale entry safely

A structured remediation workflow when a cache mismatch is discovered:

1. **Confirm the source:** read the committed version at the primary or authoritative store.
2. **Capture evidence:** ID, sourceVersion, cacheVersion, TTL, timestamps, event ID/offset; avoid logging sensitive payloads.
3. **Identify root cause:** lost/delayed event, stale refill, out-of-band writer, serializer bug, local cache, or DB replica lag.
4. **Stop ongoing corruption:** fix misbehaving writers or out-of-order consumers before patching many keys.
5. **Repair within scope:** evict or version-refresh affected keys, replay outbox events, or reconcile in bounded batches.
6. **Re-verify the real read path:** confirm HTTP GET and cache state converged and stale versions do not return.
7. **Monitor afterward:** watch mismatch metrics, event lag, Redis errors, and convergence latency.

Never run `FLUSHDB` or `KEYS *` in production just to fix one stale entry. When auditing many keys, use rate-limited `SCAN` per appropriate node/primary. Redis Cluster has no cluster-wide cursor, and scanning during mutations never yields a consistent snapshot.

## 20. Multiple cache layers and Redis Cluster

```text
Client
  |
  v
Browser / CDN cache
  |
  v
Spring application local cache (if any)
  |
  v
Redis Cluster / Redis replicas
  |
  v
Database primary / read replicas
```

Redis may already hold v13 while HTTP still serves v12 from a CDN or an app instance holding stale local memory. Conversely, a Redis reader may read from a lagging Redis replica, or a cache miss may load v11 from a lagging database replica while the primary holds v12.

In Redis Cluster, keys belong to hash slots; querying one node does not represent the entire cluster. When reconciling, verify which node serves the key, failover/resharding status, and client primary/replica routing.

When logging mismatches, record read route, cache name, key/version, instance, and observed source. Without knowing which layer served the entry, teams often blame or purge Redis when the bug lives elsewhere.

## 21. Self-check practice questions

**1.** Redis returns `TTL=200`. Can we conclude the cache is fresh?  
**No.** TTL only indicates remaining lifetime, not the source version.

**2.** If `@CacheEvict` runs after successful commit, are all races gone?  
**No.** A reader that loaded old data before commit can still PUT it back after eviction ran.

**3.** Why is `@Version` better for comparison than `cachedAt` alone?  
**Version** tracks source update order when writers follow the protocol, whereas `cachedAt` records when cache was populated and suffers from clock skew.

**4.** If event v13 runs before v12, what stops the cache from regressing?  
**Version-aware conditional updates** performing atomic check-and-write within valid key scope, combined with idempotency and ordering.

**5.** If DB commits successfully yet Redis times out during eviction, does `@Transactional` roll back the database?  
**No.** That is a cross-resource partial failure; retries, outbox, or reconciliation are needed.

**6.** Why is calling a `@Cacheable` method unsuitable as the verification source during reconciliation?  
It may return the very cache entry under inspection, breaking independent comparison.

**7.** Why aren't cache version 14 and read-replica version 13 proof that the cache is wrong?  
The replica may be lagging; inspect the primary or authoritative source.

**8.** Can a 5-minute TTL guarantee staleness never exceeds 5 minutes?  
Not if refills/refreshes keep writing stale snapshots and resetting TTL.

**9.** Why is an outbox safer than an in-memory after-commit callback when Redis fails?  
Events are persisted durably in the DB transaction and can replay once workers recover.

**10.** Once the Redis key is verified accurate, is that proof users receive accurate data?  
Not yet. Test through real HTTP/service paths because local caches, CDNs, or alternate read paths may still serve stale state.

## 22. Takeaways for implementation

- Define the **source of truth** and exact consistency level each feature needs.
- Embed **source versions** into cache payloads or metadata where appropriate.
- Measure **correctness** alongside hit ratio and latency: stale rate, version lag, convergence latency, and invalidation errors.
- Verify against an **independent source-read path**, never by calling the same `@Cacheable` method.
- Reproduce races deterministically: stale refills, out-of-order events, rollbacks, and post-commit Redis failures.
- Use TTL as a safety net, **never as proof of freshness**.
- Use `transactionAware()` and after-commit callbacks to avoid pre-commit updates, understanding they do not make SQL + Redis atomic.
- For reliable crash recovery, pair outbox/retries/idempotency with read-path verification.
- When fixing stale caches, scope repairs tightly and re-verify **what HTTP clients actually receive**.

The central question to answer is: **"After the source commits a new version, what evidence proves users will read the right version within the business's allowed time budget?"** Every solid caching strategy must measure and test that answer.

## References

- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): `RedisCacheManager`, `RedisCacheConfiguration`, TTLs, and cache organization.
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html): `@Cacheable`, `@CachePut`, `@CacheEvict`, and cache interceptors.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, proxies, and rollbacks.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` and `AFTER_COMMIT`.
- [Spring Framework — Transaction-aware Cache Decorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheDecorator.html): cache operations deferred until after commit.
- [Spring Data Redis — Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html): `RedisTemplate` and Spring transaction synchronization.
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/): TTL semantics.
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/): cursor-based keyspace iteration for bounded verification.
