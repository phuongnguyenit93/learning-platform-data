# Memory Limits, Durability, and Consistency to Understand from the Start

Redis is often introduced as a very fast data store because most operations happen in memory. When using **Spring Data Redis**, access speed is only part of the story. Before putting Redis into a real system, three independent questions must be answered:

1. **Memory:** How much RAM can the data consume? What happens when Redis runs out of space?
2. **Durability:** Will a value just written still exist after a process, server, or disk failure?
3. **Consistency:** After an update, are subsequent reads guaranteed to see the latest data?

These three properties interact with one another yet do not substitute for one another. A key with a TTL can still be evicted early due to insufficient RAM; a write command that returned success can still be lost during failover; and a record saved durably can still be stale compared to the database.

## 1. Distinguishing the Concepts from the Start

| Concept | Primary Mechanism | What Is **Not** Guaranteed |
|---|---|---|
| TTL / expiration | Deletes keys when their lifetime expires | Does not guarantee a key survives until TTL expires |
| Eviction | Removes keys by policy when Redis faces memory pressure | Not a storage or backup mechanism |
| RDB / AOF | Saves Redis data to disk for recovery | Does not automatically create a zero-data-loss system |
| Replication | Copies data from primary to replicas | Not automatically synchronous or a replacement for backups |
| Atomic command | A single Redis command executes atomically on the server | Does not turn an entire application command sequence into a transaction |
| Cache invalidation | Deletes/updates cached entries after origin changes | Does not automatically eliminate all race conditions |

A useful mental model is: **TTL/eviction determines whether a key stays in RAM; persistence determines what can be recovered; replication and operation ordering determine which version a client can observe.**

## 2. Memory Limits: Redis Is Fast, but RAM Is Finite

### 2.1. What Does `maxmemory` Limit?

Redis stores data structures in RAM. You can configure a memory management cap with `maxmemory` and choose behavior when the threshold is reached via `maxmemory-policy`:

~~~conf
maxmemory 1gb
maxmemory-policy allkeys-lfu
~~~

This is only an **illustrative configuration for a Redis instance used as a cache**. Do not treat `1gb` as a default setting for every machine.

Key distinctions:

- `used_memory`: memory Redis has allocated through its allocator.
- `used_memory_dataset`: estimated portion used by actual dataset entries, after subtracting certain overheads.
- `used_memory_rss`: resident set size of the process as reported by the operating system.
- `mem_not_counted_for_evict`: memory excluded from eviction calculations, which may include buffers related to replication/persistence depending on version and configuration.

**`maxmemory` is not a hard cap on total RAM used by the process or container.** Actual RAM is also used for internal management structures, client/output buffers, replication backlog, allocator fragmentation, and extra memory during snapshots or AOF rewrites. When running in a container, leave headroom inside the container's RAM limit; if OOM-killed, Redis may crash before handling the expected load.

With Redis Cluster, memory thresholds and monitoring apply **per node**, not as a single shared RAM budget for the entire cluster.

### 2.2. TTL, Eviction, and Manual Deletion Are Three Different Actions

~~~text
SET session:42 "..." EX 1800
                │
                ├── After 1,800 seconds → key eligible for expiration deletion
                ├── Low RAM + matching policy → may be evicted early
                └── DEL session:42 → application actively deletes immediately
~~~

Redis handles expiration by checking on access and actively scanning expired keys. Consequently, the exact millisecond memory is reclaimed may not match the exact moment TTL hits zero. Logically, an expired key is no longer treated as a valid value when accessed.

TTL also has subtle details that are easy to miss:

~~~bash
SET demo:token "abc" EX 60
TTL demo:token          # remaining seconds
SET demo:token "xyz"    # plain SET drops the previous TTL
TTL demo:token          # -1: key exists without an expiration
DEL demo:token
TTL demo:token          # -2: key does not exist
~~~

- A plain `SET` discards a key's existing TTL unless an option to preserve TTL is specified.
- `EXPIRE` sets an expiration in a separate command; if `SET` succeeds and the application fails before `EXPIRE`, the key can live forever.
- Use a single write command **with TTL included** whenever expiration is mandatory.
- TTL is not a fallback capacity-limiting mechanism. If key creation outpaces expiration, RAM can still fill up.

### 2.3. Choosing an Eviction Policy Based on Redis's Role

| Policy | Behavior at `maxmemory` | When to Consider |
|---|---|---|
| `noeviction` | Rejects write commands that increase memory usage per Redis's checks; reads can continue | Data must not be silently dropped; application must handle write errors |
| `allkeys-lru` | Prefers evicting least-recently-used keys across the entire keyspace | Caches accessed by recency |
| `allkeys-lfu` | Prefers evicting least-frequently-used keys using an approximation algorithm | Caches with long-lived "hot" key sets |
| `allkeys-random` | Picks randomly across all keys | Certain caches with special access distributions |
| `volatile-lru` / `volatile-lfu` | Chooses only among keys **with a TTL** | When intentionally protecting non-TTL keys from eviction |
| `volatile-ttl` | Prefers keys with the nearest expiration time | When TTL reflects eviction priority |
| `volatile-random` | Picks randomly among keys with a TTL | Little need to optimize eviction order |

LRU/LFU variants use approximation algorithms rather than a strict global ranking over all keys. With `volatile-*` policies, if no eligible keys remain, behavior under memory pressure resembles `noeviction`; keys without TTLs can cause writes to fail even when an eviction policy is set.

**Design rule:** If all keys are regenerable cache entries, `allkeys-lru` or `allkeys-lfu` is usually worth considering. If Redis holds critical business state that must not be lost, do not rely on an eviction policy to turn Redis into a database with transactional guarantees.

### 2.4. Sizing Capacity from Real Measurements

Suppose a system stores 2 million keys, with each key and value occupying roughly 600 bytes on average **according to `MEMORY USAGE`** under test load. The measured dataset portion is approximately:

`2,000,000 × 600 = 1,200,000,000 bytes`, or about **1.2 GB (decimal)**.

That is not yet the total RAM to provision on the server. You must budget extra for dataset growth, buffers, fragmentation, persistence/forking, traffic spikes, and a safety margin based on actual measurements. Raw JSON payload size or key character count is insufficient to estimate Redis memory overhead.

Useful inspection commands:

~~~bash
redis-cli INFO memory
redis-cli INFO stats
redis-cli CONFIG GET maxmemory
redis-cli CONFIG GET maxmemory-policy
redis-cli MEMORY USAGE cache:product:42
redis-cli TTL cache:product:42
~~~

Metrics to monitor together include `used_memory`, `used_memory_rss`, `mem_not_counted_for_evict`, `evicted_keys`, `expired_keys`, latency, and cache hit/miss ratios. Rising `evicted_keys` indicates RAM/cache policies are affecting data retention; rising `expired_keys` may simply reflect normal TTL expiration.

Avoid oversized keys (big keys), unbounded growing lists/hashes/sets, or running `KEYS *` on systems with many keys. Use `SCAN` for incremental traversal and enforce size limits in the application layer.

### 2.5. Applying TTL with Spring Data Redis

With Spring Boot and `StringRedisTemplate`, set expiration in the **same write operation**:

~~~java
@Service
public class VerificationCodeStore {

    private final StringRedisTemplate redis;

    public VerificationCodeStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String requestId, String code) {
        String key = "verification:" + requestId;
        redis.opsForValue().set(key, code, Duration.ofMinutes(3));
    }

    public String find(String requestId) {
        return redis.opsForValue().get("verification:" + requestId);
    }
}
~~~

This example only illustrates saving a value with a TTL; a real verification-code system also needs attempt limits, deletion after use, error handling, and protection for sensitive data.

When using Spring Cache, **the TTL of `RedisCacheManager` must be explicitly decided**. A basic configuration:

~~~java
@Configuration
@EnableCaching
public class CacheConfig {

    @Bean
    RedisCacheManager cacheManager(RedisConnectionFactory connectionFactory) {
        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(5))
                        .disableCachingNullValues();

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(defaults)
                .build();
    }
}
~~~

`@Cacheable` only expresses how to cache method results; it does not automatically ensure each cache has a business-appropriate expiration. Data groups with different lifecycles should be given distinct TTLs instead of assigning one TTL to all data.

## 3. Data Durability: A Successful Write Does Not Mean Safe on Disk

### 3.1. Three Common Operating Modes

| Mode | What Redis Saves for Recovery | Risk of Data Loss on Failure |
|---|---|---|
| No persistence | Only data currently in memory | Data is lost on process restart if there is no external recovery source |
| RDB snapshot | Point-in-time snapshot of data when a snapshot succeeds | Changes since the most recent snapshot can be lost |
| AOF | Log of data-modifying commands, written and synced to disk per configuration | Depends on `fsync` interval, OS/disk state, and recovery process |
| RDB + AOF | Combines snapshots and AOF | Reduces some recovery risks, though backups, monitoring, and restore drills are still required |

**RDB** creates point-in-time snapshots of the dataset. This is useful for backups and relatively fast restarts, but writes after a snapshot can disappear if Redis crashes before the next snapshot. Background snapshotting typically uses `fork` and copy-on-write, which can increase RAM pressure while data continues to change.

**AOF** records the sequence of data-modifying operations to replay on startup. Common `appendfsync` options:

- `always`: requests frequent synchronization for every AOF write; higher I/O cost, still subject to hardware/OS limits.
- `everysec`: typically syncs roughly every second; a common balanced default, **not an absolute guarantee of losing at most one second** in every disaster.
- `no`: lets the OS decide when to flush; the data-loss window can be larger.

Modern Redis versions can organize AOF across multiple files and perform AOF rewrites to keep the log from growing without bound. Rewrites change internal storage layout; they do not turn AOF into a distributed transaction with an external database.

An example for an instance that needs to preserve data across restarts:

~~~conf
maxmemory 1gb
maxmemory-policy noeviction

appendonly yes
appendfsync everysec
save 300 10
~~~

This configuration only illustrates combining memory limits with AOF/RDB. The `save 300 10` directive triggers considering a snapshot when at least 10 changes occur within 300 seconds; it does not mean Redis snapshots strictly every 300 seconds. Tune settings for your actual workload, Redis version, and storage capabilities.

Do not pick `noeviction` and mistakenly think it means "completely safe": when RAM runs out, the application can still receive write errors; on power loss, durability depends on whether persistence files were actually flushed and the storage device remains intact.

### 3.2. Restarts, Failover, and Losing the Entire Machine Are Different Scenarios

Suppose the client receives a success response after `SET order:42 "PAID"`:

1. **Redis process crashes while disk stays healthy:** Redis can recover what RDB/AOF saved; unpersisted recent changes may be lost.
2. **Primary loses connection and a replica is promoted:** If the write had not reached the promoted replica, the value can disappear from the dataset after failover.
3. **Volume loss or storage corruption:** RDB/AOF stored on that same volume is no longer enough for recovery; independent backups and rehearsed restore procedures are needed.
4. **Memory full:** Writes can be rejected according to eviction policy; persistence does not make a failed write succeed.

**A replica is not a backup.** Accidental key deletions or bad writes replicate rapidly to replicas. Backups must offer separate point-in-time recovery and be tested periodically.

### 3.3. Replication Is Typically Asynchronous

In a standard primary-replica setup, Redis acknowledges writes on the primary without waiting for every replica to confirm applying the change. Therefore, a brief window can exist:

~~~text
Client A             Primary                    Replica
   | SET k=v2 ---------> |                          |
   | <----------- OK     | ---- sends async cmd ---> |
   |                     |                          |
Client B reads stale replica ----------------------> GET k = v1
~~~

Redis provides the `WAIT` command so a client can wait for a number of replicas to acknowledge receiving prior writes, subject to a timeout. However, **`WAIT` does not turn replication into strong consensus**: acknowledging receipt does not mean data is durably flushed on all machines or guaranteed to survive every primary selection during failover. If you need to check AOF synchronization in supported versions, look into `WAITAOF` and the specific limits of your deployed version.

## 4. Consistency: Atomic Per Command, Not Automatically Atomic Across a Business Flow

### 4.1. A Single Redis Command Differs from a Sequence of Operations

Single commands like `INCR counter`, `SET key value`, or `HSET` execute atomically on a Redis server for their respective operations. Now consider the flow:

~~~text
GET stock:42       → 10
Compute 10 - 1     → 9
SET stock:42 9
~~~

If two requests both read 10 and both write 9, the system can lose an inventory deduction. Replace this with an appropriate atomic update (e.g. `DECR` if the problem allows), or use `WATCH` with `MULTI/EXEC`, or a well-designed Lua script instead of chaining independent read-modify-write commands.

Distinguish the mechanisms:

| Mechanism | What Does It Help With? | Important Limitation |
|---|---|---|
| Single command (`INCR`, `SET ... NX EX`, …) | Executes one operation atomically | Does not cover logic in another database |
| Pipeline | Reduces network round trips for multiple commands | **Does not** make the batch a transaction |
| `MULTI/EXEC` | Groups commands to run sequentially without interleaving from other clients | No SQL-style rollback when a command fails during execution |
| `WATCH` + `MULTI/EXEC` | Aborts the transaction if a watched key changes before `EXEC` | Application must retry and handle conflicts |
| Lua script | Runs logic server-side as a unit atomic with respect to other Redis commands | Long scripts can block the server; mid-script errors do not undo already-executed writes |

On Redis Cluster, multi-key operations must also obey slot distribution constraints (e.g. keys must share the same hash slot when commands require it); do not assume an arbitrary transaction or Lua script can span keys across multiple shards.

### 4.2. The Database and Redis Are Two Separate Systems

Spring applications typically use a relational database as the **canonical data source** and Redis as a cache layer:

~~~mermaid
flowchart LR
    U[Request] --> S[Spring Service]
    S -->|1. Look up in cache| R[(Redis)]
    R -->|Cache hit| S
    S -->|2. Cache miss| D[(Database)]
    D -->|Record| S
    S -->|3. Cache with TTL| R
    S -->|Return result| U
~~~

This strategy is called **cache-aside**. When updating data, a common approach is committing the database change and then deleting the corresponding cache key. However, a race condition still exists:

~~~text
Time         Request A (read)          Request B (write)
   t1        Cache miss
   t2        Read DB → old value V1
   t3                                  Write DB → V2, commit
   t4                                  Delete cache succeeds
   t5        Write V1 into cache
   t6        Later request reads V1 from cache, though DB has V2
~~~

TTL prevents the stale value from living forever from **that cache write**, yet does not prove every read immediately sees fresh data. Advanced mechanisms like versioning, event-based invalidation, coordinated locking, or mandatory reads from the canonical source must be chosen per business consistency needs; each carries its own cost and races.

An important Spring note:

- Database `@Transactional` does not automatically create an atomic transaction across JDBC and Redis.
- `@Cacheable` / `@CacheEvict` declare cache behavior; **the ordering between cache eviction and database commit** must be explicitly designed.
- `RedisCacheManager.transactionAware()` can defer cache put/evict/clear operations until after a Spring transaction commits successfully in an appropriate context. Redis failing after commit can still leave the cache wrong or stale; do not treat this as a guaranteed distributed commit.

If business logic needs accurate transfers, payments, or inventory adjustments, enforce invariants in a data store with proper transactions. Redis remains very useful for accelerating reads or performing local atomic operations, provided the canonical source and recovery plan are clear.

### 4.3. Replica Reads Can Observe Stale Data

Even when data on the primary has changed, replicas may lag behind. For flows requiring **read-your-writes** (a user editing their profile must immediately see the change), you can:

- Read from the primary during the window requiring high consistency.
- Bypass stale caches/replicas after a sensitive update action.
- Apply a version/token to reject data older than the version the application already knows.
- Monitor replication lag and define a fallback rule to the primary per SLA.

Each choice must be weighed against latency, primary load, and failover behavior. Reading from the primary solves normal replica lag, yet **does not** guarantee zero lost writes across an asynchronous failover.

## 5. Common Scenarios When Developing with Spring Data Redis

### Scenario A: Product Catalog Cache

- **Memory:** TTL of a few minutes per freshness needs; early eviction is acceptable.
- **Durability:** Persistence may be turned off for pure caches if the database can rebuild all data and the application tolerates a cold cache start.
- **Consistency:** Short staleness acceptable; delete keys after updates and keep TTL as a safety net.
- **When Redis fails:** Explicitly decide whether to read the database directly with load limits or return a temporary error.

### Scenario B: Login Sessions

- **Memory:** TTL must match session lifecycle; eviction policies can log users out prematurely.
- **Durability:** If Redis is the sole session store, restarts/failover can drop sessions; design according to real tolerance.
- **Consistency:** Logout, token revocation, and permission changes need explicit invalidation rules rather than waiting for TTL expiry.

### Scenario C: Request Rate Limiting

- **Memory:** Many short-lived keys; needs TTLs and cleanup.
- **Durability:** Losing some counters after an incident is often acceptable, depending on protection severity.
- **Consistency:** Two separate `INCR` then `EXPIRE` commands have an error window between them; use a Lua script or atomic mechanism designed for the rate-limiting algorithm. Across multiple independent Redis nodes, do not assume a global counter is consistent.

### Scenario D: Order Status or Account Balances

- **Memory:** Canonical data cannot be arbitrarily evicted.
- **Durability:** Requires clear RPO (maximum acceptable data loss) and RTO (recovery time), durable storage, backup/restore, and error handling.
- **Consistency:** Invariants must be protected across requests and transactions; Redis cache is only a read-optimized projection when the transactional database is the canonical source.

The deciding factor is not the Redis data type name, but **the business consequence if a key disappears, a write is lost, or a client sees a stale value**.

## 6. Observing Incidents and Testing Operational Assumptions

| Observation | Question to Answer | Action |
|---|---|---|
| `used_memory` close to `maxmemory` | Unusual key growth rate, missing TTLs, or big keys? | Measure sizes/key counts; adjust data structures, TTLs, capacity, and policies |
| `evicted_keys` rising, hit rate dropping | Is the cache being evicted too early, increasing DB load? | Review working set, `allkeys-lru/lfu`, capacity, and origin load |
| OOM errors from Redis | Using `noeviction`, or no keys eligible for eviction? | Handle write errors in the app and fix memory budget/policy |
| `used_memory_rss` significantly higher than `used_memory` | Fragmentation, background/buffer memory, or persistence activity? | Check allocator and OS metrics; do not conclude from one ratio alone |
| Abnormal `aof_last_write_status` or `rdb_last_bgsave_status` | Disk full, write permissions, fsync, or snapshot failure? | Check logs, disk space, volume permissions, and recovery procedures |
| Replica lag or link down | Are replica reads stale, or is there risk of losing writes on failover? | Check topology, network, read policy, and test failover scenarios |
| Cache returns stale data | Wrong invalidation timing, race, overly long TTL, or replica reads? | Trace DB commit → evict → refill flow and compare versions |

Initial inspection commands:

~~~bash
redis-cli INFO memory
redis-cli INFO stats
redis-cli INFO persistence
redis-cli INFO replication
redis-cli INFO clients
redis-cli CONFIG GET maxmemory
redis-cli CONFIG GET maxmemory-policy
redis-cli TTL cache:product:42
~~~

For example, `INFO persistence` shows RDB/AOF persistence status at inspection time; `INFO replication` shows replica roles and link state. Combine this output with application logs, latency metrics, and restore tests rather than relying on a single command run.

### 6.1. Test Failure Scenarios Before Production

A Redis system should be tested against **observable application behavior**:

1. As memory approaches its limit, does the app see cache misses or write errors? Does it overload the origin database?
2. When Redis restarts, which keys survive, which are lost, and can the app recover automatically?
3. When the primary fails over, does an operation acknowledged moments earlier still exist on the new primary?
4. When cache deletion fails after the database commits, how long can customers see stale data?
5. When a replica lags behind, does a screen right after an update mistakenly read an older version?

Tolerance must be defined in business terms—for instance, "product cache may be stale for at most a controlled interval," which is entirely different from "payment status must never be processed twice."

## 7. Design Principles to Carry into Subsequent Spring Data Redis Lessons

1. **Define the role of each key group**: regenerable cache, session, counter, or business state. Do not apply one eviction/persistence policy to every data type just because they share Redis.
2. **Set TTL at write time** whenever a key must expire; do not rely on two separate commands while ignoring the failure gap between them.
3. **Estimate RAM using measured data** and reserve headroom beyond raw keys/values; monitor evictions, RSS, buffers, and persistence impact.
4. **Choose RDB/AOF according to RPO/RTO and rehearse restores**. Replication, AOF, and backups handle different failure modes.
5. **Evaluate consistency across the entire request path**: database commit, cache invalidation, refill, replica reads, and failover. One atomic Redis command does not make an entire Spring flow atomic.
6. **Design for Redis unavailability**: fallbacks, timeouts, load limits, controlled error responses, and self-recovery must match the criticality of the data.

Redis is a powerful tool when you clearly know **when data is allowed to disappear, how much can be lost in an incident, and how stale a version a client is allowed to read**. Those three answers must come before picking annotations, `RedisTemplate` operations, or deployment parameters.

## Further Reading

- [Redis — Key eviction](https://redis.io/docs/latest/develop/reference/eviction/)
- [Redis — Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
