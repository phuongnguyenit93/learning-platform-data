# Configuring Memory Limits and Purpose-Driven Eviction Policies in Spring Data Redis

## 1. The Deployment Problem: What Happens When Redis Runs Out of Memory?

Redis keeps most of its active data in RAM. As the number of keys, value sizes, or traffic grows, a Redis instance can hit its memory threshold. Without a clear policy, a Spring Boot application can run into hard-to-handle situations:

- The cache fails to write new data.
- Frequently accessed cache entries get pushed out, increasing database load.
- User sessions disappear early, even though their TTL has not expired.
- Rate limits, idempotency keys, or distributed locks are evicted, breaking business guarantees.
- The Redis process is OOM-killed by the OS/container because total RSS memory exceeds the limit, even when `maxmemory` is set.
- One Redis Cluster shard runs out of space while other shards still have plenty of RAM.
- A replica promoted to primary behaves differently on writes/eviction because configurations are inconsistent across nodes.

Consider a Spring Boot service with four types of keys:

```text
Spring Boot
   |
   +-- cache:product:42         -> can be reloaded from PostgreSQL
   +-- session:user:1001        -> login state
   +-- ratelimit:user:1001      -> request rate limit
   +-- idempotency:order:9001   -> prevents duplicate order processing
   |
   v
Redis (finite RAM)
```

If configured with `allkeys-lru`, **all four types of keys can become eviction candidates** when Redis is under memory pressure. All keys have different prefixes, but prefixes do not provide memory protection.

This is why you cannot simply ask: “Which eviction policy is best for Redis?” The better question is:

> **Which data is allowed to disappear early, which data must be kept until its TTL expires or it is explicitly deleted, and when RAM is full, does the application accept losing keys or accept write errors?**

This guide covers configuring `maxmemory`, choosing `maxmemory-policy`, applying it alongside Spring Data Redis/Spring Cache, monitoring, and testing before production deployment.

## 2. Three Concepts That Must Be Distinguished

| Concept | Question | Mechanism |
| --- | --- | --- |
| Memory limit | How much memory can Redis use for data counted in eviction accounting? | `maxmemory` |
| Eviction | When exceeding the memory threshold, which keys is Redis allowed to remove to make room for the next operation? | `maxmemory-policy` |
| Expiration/TTL | At what point is a key considered expired? | `EXPIRE`, `SET EX/PX`, Spring `Duration` |

An example:

```redis
SET cache:product:42 "{...}" EX 300
```

A 300-second TTL means the key expires according to the configured time. However, if Redis uses `allkeys-lru` and runs low on RAM, the key can be **evicted before 300 seconds**.

Conversely, a key without a TTL can still be evicted under `allkeys-lru` or `allkeys-lfu`.

**TTL is not a promise of minimum lifetime.** It is an upper bound on existence under the expiration policy, whereas eviction can end a key's existence earlier under certain policies.

## 3. What Is `maxmemory`?

Redis has the parameter:

```conf
maxmemory 768mb
```

This is the threshold Redis uses to make memory-control and eviction decisions—it is not a guarantee that the **Redis process's RAM/RSS is always less than 768 MB**.

Redis also has:

- Memory overhead from objects, dictionaries, and the allocator.
- Memory allocator fragmentation.
- Client and replication buffers.
- RDB/AOF persistence mechanisms, background save/rewrite, and copy-on-write.
- OS memory, shared libraries, and other processes/runtimes.
- Components excluded from eviction memory accounting in certain versions/configurations.

Therefore, distinguish:

```text
Redis maxmemory threshold
          !=
Redis process resident memory (RSS)
          !=
Container memory limit
          !=
Total host memory
```

Do not set `maxmemory` equal to the container's RAM limit and assume OOM-kill will never occur.

### What If Redis Has No `maxmemory`?

In many 64-bit Redis OSS environments, `maxmemory 0` means no data limit imposed by this specific option. However, Redis is still constrained by physical RAM, cgroups/containers, cloud provider quotas, and OS limits.

Without capacity control, the process can still be killed when out of memory, causing downtime and data risk depending on persistence and replication settings.

Managed Redis may enforce limits via instance size or its own control plane; check the provider's policy rather than assuming `CONFIG SET` is permitted.

## 4. Why Not Set `maxmemory` to Total RAM?

Suppose a Redis container has a 4 GiB memory limit and the dataset can grow rapidly.

An overly tight configuration:

```conf
maxmemory 4gb
```

is risky because Redis also uses memory outside dataset/eviction accounting; RDB/AOF background work or COW pages also require headroom.

An illustrative example with headroom:

```text
Container memory limit: 4 GiB
maxmemory:             2.5 GiB
remaining headroom:    for RSS overhead, buffers,
                       fragmentation, fork/COW, and spikes
```

**2.5 GiB is not a mandatory standard ratio.** The actual threshold must be based on:

1. Redis version and memory accounting.
2. Dataset size, data types, and key/value overhead.
3. Peak read/write traffic.
4. Persistence settings and snapshot/rewrite frequency.
5. Replication topology and client output buffers.
6. Container/cgroup memory limit.
7. Fragmentation/RSS and fluctuations during deploys/scaling.
8. Memory reserved for the OS and other processes if sharing a host.

The goal is **measured headroom**, not relying on a guessed ratio like “always reserve 10%.”

## 5. Configuring `maxmemory` in `redis.conf`

Example of a Redis instance dedicated to caching:

```conf
port 6379
maxmemory 768mb
maxmemory-policy allkeys-lfu
maxmemory-samples 10
```

Here:

- `maxmemory 768mb`: Redis's memory threshold.
- `maxmemory-policy allkeys-lfu`: when low on RAM, selects candidates across the entire keyspace based on estimated usage frequency.
- `maxmemory-samples 10`: number of samples used by the approximation algorithm in applicable policies; higher numbers can increase CPU cost for key selection.

If Redis only holds rebuildable cache data, allowing eviction may be appropriate. If the same instance also stores critical tokens/locks/idempotency keys, this configuration **may be inappropriate**.

### Checking the Active Configuration

```bash
redis-cli -h redis.internal -p 6379 CONFIG GET maxmemory
redis-cli -h redis.internal -p 6379 CONFIG GET maxmemory-policy
redis-cli -h redis.internal -p 6379 CONFIG GET maxmemory-samples
```

In managed Redis, `CONFIG GET` may be restricted, and configuration is viewed via the provider's portal or API.

## 6. Common Redis Eviction Policies

Redis supports the core policies below:

| Policy | Keys Eligible for Eviction | Selection Strategy |
| --- | --- | --- |
| `noeviction` | No proactive eviction to free data keys | Rejects writes requiring more memory when unable to serve |
| `allkeys-lru` | All keys | Approximates least recently accessed keys |
| `allkeys-lfu` | All keys | Approximates least frequently used keys |
| `allkeys-random` | All keys | Random selection |
| `volatile-lru` | Only keys with an expiration | Approximates least recently accessed |
| `volatile-lfu` | Only keys with an expiration | Approximates low usage frequency |
| `volatile-random` | Only keys with an expiration | Random among keys with TTL |
| `volatile-ttl` | Only keys with an expiration | Prefers keys with shorter remaining TTL |

**Do not interpret `volatile-*` as removing only already-expired keys.** It performs *early* eviction among keys that have an expiration set in order to free memory under space pressure.

Some policy names and implementation details can evolve across Redis versions, but these categories form the common baseline for deployment design.

## 7. `noeviction`: Prioritizing Key Retention Over Write Availability

Example:

```conf
maxmemory 1gb
maxmemory-policy noeviction
```

When accounted memory exceeds the threshold and a command needs to allocate more memory, Redis may reject the command with an error like:

```text
OOM command not allowed when used memory > 'maxmemory'
```

The exact message may vary by Redis version and command.

Consequences:

- Redis does not proactively evict existing keys under an eviction policy to accept new writes.
- Keys with a TTL **still expire** via expiration.
- Some read commands or commands that do not increase memory may still succeed depending on command semantics and server state.
- Applications must not assume every write succeeds just because Redis responds to `PING`.
- The Redis process can still suffer OS OOM if memory headroom, storage, or buffers are poorly managed.

### When Is `noeviction` Appropriate?

It can be suitable for workloads that cannot tolerate early key loss and want **explicit errors when capacity runs out**, such as a coordination layer with a strict failure policy.

Still, `noeviction` **does not by itself turn Redis into a durable data store**: restarts, failovers, asynchronous replication, disk loss, or TTL expiration can still cause state to disappear.

If Redis stores authoritative monetary or payment state, you still need an appropriate database/ledger—not just `noeviction`.

## 8. `allkeys-lru`: Prioritizing Recently Used Keys

Example:

```conf
maxmemory 2gb
maxmemory-policy allkeys-lru
```

This policy approximates least-recently-used across **all keys**.

Suitable when:

- Most data is rebuildable cache.
- Recently accessed keys are likely to be accessed again.
- Many keys are rarely used after creation.
- Eviction prior to TTL is acceptable.
- Misses are safely handled by the authoritative data source.

### Redis LRU Is Approximate

Redis uses a sample-based approximation mechanism rather than an exact LRU list that updates every key on every access like a textbook model.

Therefore, do not write tests assuming “the oldest-accessed key is always guaranteed to be evicted first.”

When hitting the limit, recently used keys have a higher probability of survival, though exact outcomes depend on sampling, memory usage, and workload.

## 9. `allkeys-lfu`: Prioritizing Usage Frequency

Example:

```conf
maxmemory 2gb
maxmemory-policy allkeys-lfu
```

LFU stands for least-frequently-used based on Redis's approximate counter and timing mechanism.

Suitable when:

- Certain “hot” keys are accessed repeatedly at high volume.
- Performance-critical keys should stay cached longer despite brief gaps between accesses.
- The cache has a skewed access distribution, such as popular products or shared configuration.
- Workload and update patterns align with frequency estimation.

### LFU Does Not Count Every Access Exactly

Redis LFU uses a probabilistic counter with time-based decay. Do not infer from LFU metadata that a key was read exactly 10,000 times.

Related settings:

```conf
lfu-log-factor 10
lfu-decay-time 1
```

`lfu-log-factor` affects how the LFU counter grows with frequency; `lfu-decay-time` tunes the decay rate over time. Values must be tested against your real workload rather than copied blindly from an example.

## 10. How Do LRU and LFU Differ?

Consider a product cache:

```text
Product A: read 5,000 times yesterday, not read today
Product B: read once a minute ago
Product C: read steadily 100 times/hour
```

LRU cares more about **recency** of access. LFU tries to retain keys with **high frequency** subject to decay.

| Scenario | LRU Likely Suitable | LFU Likely Suitable |
| --- | --- | --- |
| Session-oriented data access | Yes | Possibly |
| Short-lived news burst | Possibly | May need tuning |
| Catalog with a few very popular products | Yes | Often worth testing |
| Workload rotating across many keys | Yes | Needs testing |
| One-off keys never read again | Easily evicted when newer accesses arrive | Can be deprioritized |
| Access patterns shifting by season/day | Needs measurement | Needs decay review |

No single policy is always best. Measure hit ratio, evictions, DB fallback load, Redis CPU, and latency under realistic workloads.

## 11. `allkeys-random`: Random Eviction Across All Keys

Example:

```conf
maxmemory-policy allkeys-random
```

Pros: simple and relies little on assumptions about locality or frequency.

Cons: can evict heavily used keys because it does not consider recency or frequency.

Consider when:

- Keys have roughly equal access probabilities.
- The workload has no clear locality.
- Simplicity of candidate selection matters more than optimizing hit ratio.
- Benchmark results demonstrate suitability.

For caches with skewed access distributions, LRU/LFU are usually worth evaluating before random. However, production choices should be driven by metrics, not intuition alone.

## 12. `volatile-lru` and `volatile-lfu`: Selecting Only Keys with TTL

Example:

```conf
maxmemory 1gb
maxmemory-policy volatile-lru
```

This policy **is only permitted to evict keys that have an expiration**, never selecting keys without a TTL as candidates.

Example:

```text
config:global       -> no TTL
cache:product:42    -> 5-minute TTL
cache:product:99    -> 5-minute TTL
```

When memory runs low, keys with a TTL are eviction candidates; `config:global` is excluded from candidate selection.

### Important Trap

If the same instance holds:

```text
lock:order:42             30-second TTL
idempotency:payment:9001  24-hour TTL
session:user:1001         20-minute TTL
cache:product:42          5-minute TTL
```

then **locks, idempotency keys, sessions, and caches are all eligible for eviction** under `volatile-lru`/`volatile-lfu`.

Thus `volatile-*` cannot distinguish between “a TTL key that is merely cache” and “a TTL key protecting business logic.”

**Having a TTL does not mean a key is allowed to be lost before its TTL expires.** This is a very serious deployment mistake.

## 13. `volatile-random` and `volatile-ttl`

### `volatile-random`

```conf
maxmemory-policy volatile-random
```

Redis selects randomly among keys with an expiration. It does not automatically prioritize cache keys, sessions, or tokens.

### `volatile-ttl`

```conf
maxmemory-policy volatile-ttl
```

This policy prioritizes keys with shorter remaining TTLs among keys that have an expiration. The idea is to pick keys that are about to expire soon to free space.

However, it **does not guarantee**:

- Only truly expired keys are deleted.
- A session with a short TTL will not be pushed out early.
- An important key with a long TTL is guaranteed safe.
- Every key has a TTL.
- When there are no TTL candidates, Redis can always free enough RAM.

`volatile-ttl` can work when all expiring keys are acceptable to drop early and remaining TTL is a useful priority signal. It is not a solution for protecting critical business state merely by key prefix.

## 14. When a Volatile Policy Has No Keys with TTL Left

A scenario:

```text
maxmemory 512mb
maxmemory-policy volatile-lru

Key A: 250 MB, no TTL
Key B: 250 MB, no TTL
```

When there are no eligible keys to evict, Redis cannot evict non-TTL keys under `volatile-lru`. If an operation needs to grow memory beyond the limit, Redis may reject writes with behavior similar to `noeviction`.

This can happen when:

- A cache adapter forgets to attach a TTL.
- Many non-TTL keys consume almost all memory.
- All keys with TTL have already been evicted.
- Data is written via another path that omits expiration.

Do not treat `volatile-*` as a guarantee that the system always has room for new keys. Monitor the ratio of keys with TTL and check which producers create keys without TTL.

## 15. TTL and Eviction Are Not the Same Event

Redis has different reasons why a key disappears:

- **Expiration:** the TTL ran out.
- **Eviction:** Redis proactively removed the key early per the memory policy.
- **Application delete:** `DEL`, `UNLINK`, or Spring Cache removal.
- **Logical overwrite:** the application overwrote or changed the state.
- **Failover/replication loss:** state changed due to promotion and lag.
- **Restart without full persistence:** data was not recovered.
- **Admin operation:** data deletion, flush, or topology change.

Do not see a cache miss and immediately conclude “the TTL expired.” Check `evicted_keys`, `expired_keys`, write timestamps, Redis metrics, and logs.

### Keyspace Notifications

Redis can emit `expired` or `evicted` events if keyspace notifications are appropriately configured, but Pub/Sub events can be lost when a subscriber is offline.

Do not use Redis expired/evicted notifications as the sole business trigger for work that must reliably execute. If durable deadlines are required, use a scheduler, queue, or ledger with reconciliation.

## 16. Rules for Choosing a Policy by Data Purpose

| Redis Purpose | Allow Early Key Loss? | Policy Direction |
| --- | --- | --- |
| Rebuildable product page cache | Yes | `allkeys-lfu` or `allkeys-lru` |
| Read-heavy query cache backed by DB | Yes | `allkeys-lru`/`allkeys-lfu`, benchmark |
| One-off transient cache | Yes | Consider `allkeys-random` if workload fits |
| Login sessions | Usually undesirable before TTL | Isolate instance or choose protective policy |
| Idempotency keys | No if preventing duplicate processing | Prefer no eviction, capacity/TTL/authoritative source |
| Distributed locks | Must not be evicted before TTL | Isolate instance/no eviction, review full lock semantics |
| Critical rate limiter | Must not fail-open uncontrollably | Isolate instance, explicit error policy |
| Critical queue/Redis Streams | Must not lose data via eviction | Evaluate durability, retention, `noeviction`/other architecture |
| Redis as source of truth | Losing unrebuildable keys is high risk | Do not rely on eviction alone; proper storage architecture |

This table provides design guidance. `noeviction` does not by itself solve persistence or RPO, and caches may have specific miss-rate and latency requirements.

## 17. Why Mixing Cache and Critical State Is Dangerous

A single instance holding:

```text
cache:catalog:*          700 MB
session:*                100 MB
lock:*                     5 MB
idempotency:*             25 MB
```

If you pick `allkeys-lru`, any key can be evicted, including locks and idempotency keys.

If you pick `volatile-lru`, locks/sessions/idempotency keys usually **also have TTLs**, so they remain candidates.

If you pick `noeviction`, cache growth will cause critical writes to fail with OOM once the memory threshold is reached.

Thus a shared pool can leave all three options with unacceptable trade-offs.

### Solution: Separate Redis Deployments by Data Class

Example:

```text
Spring Boot
    |
    +--> Redis Cache Pool
    |      maxmemory-policy allkeys-lfu
    |      can evict before TTL
    |      cache miss -> source of truth
    |
    +--> Redis Coordination Pool
           maxmemory-policy noeviction
           capacity tightly monitored
           explicit policy on write failure
```

This is an architectural example—it does not mean every key type needs its own dedicated Redis cluster. The degree of isolation depends on cost, risk, and operations.

**Redis logical databases (`SELECT 0`, `SELECT 1`) or key prefixes do not create independent RAM limits or eviction policies** within the same Redis instance. If different policies are required, you normally need separate Redis instances/deployments (or verified platform-provided isolation capabilities).

## 18. Pure Cache: Example of Choosing `allkeys-lfu`

Requirements:

- PostgreSQL is the authoritative source.
- Redis only stores products, articles, and query results.
- Cache misses can be recomputed.
- A small set of hot keys is read repeatedly.
- A 1.5 GiB RAM limit was chosen after capacity testing.

Illustrative configuration:

```conf
maxmemory 1536mb
maxmemory-policy allkeys-lfu
maxmemory-samples 10
lfu-log-factor 10
lfu-decay-time 1
```

The Spring app still needs:

- TTL for stale-data control.
- Stable serialization/versioning.
- Cache stampede protection during heavy evictions.
- Bounded database fallback load.
- Tracking of hit ratio and eviction counts.
- Capacity planning and experiments comparing against LRU.

LFU does not guarantee hot keys live forever; it only changes prioritization under memory pressure.

## 19. Sessions: Eviction Before TTL Is a UX or Security Bug

A session might be given a TTL:

```redis
SET session:user:1001 "..." EX 1800
```

If sessions live in a Redis cache pool with `allkeys-*`, Redis can evict them before 30 minutes when space runs tight.

Consequences:

- Users get abruptly logged out.
- Partial session state is lost, causing inconsistent errors.
- Re-authentication flows can generate extra load.
- If the session carries security context, evaluate missing-key behavior: usually deny and require re-login, never reconstruct privileges from untrusted data.

A Redis session deployment should have memory headroom and a policy chosen with the goal of **not losing sessions before TTL**, or explicitly accept session loss if the business allows it.

`noeviction` is one direction, though creating/updating new sessions can fail when RAM runs out. The application must handle that error explicitly rather than “faking a successful session.”

## 20. Distributed Locks: Eviction Can Break Correctness

Suppose:

```redis
SET lock:order:42 worker-A NX PX 30000
```

Worker A believes it holds a 30-second lock. If Redis allows the lock key to be evicted after 3 seconds:

```text
T0 Worker A acquires lock and starts processing
T3 Redis evicts lock due to memory pressure
T4 Worker B acquires lock with same name and starts processing
T5 Both A and B mutate the resource concurrently
```

This creates a risk of double processing or a race condition.

**A lock's TTL is a time-safety bound, not permission for early eviction.** For critical locks, isolate data, manage capacity, and use owner tokens/fencing or a coordination mechanism with appropriate guarantees.

Even with `noeviction`, Redis failover and asynchronous replication have their own failure cases for locks. Do not use an eviction policy as an absolute guarantee of distributed lock correctness.

## 21. Idempotency Keys: Eviction Can Cause Duplicate Side Effects

A payment service processes a request ID:

```text
idempotency:payment:req-123 -> ALREADY_PROCESSED
24-hour TTL
```

If the key is evicted after 2 hours due to cache pressure, the same request ID sent again may be treated as a new request.

This can lead to:

- Executing a side effect a second time.
- Creating duplicate orders/jobs/messages.
- Counter drift or double charges without an independent ledger.

Therefore, critical idempotency state should not reside solely in an evicting Redis pool; you may need to persist result records in an authoritative database and synchronize cache entries for speed.

`volatile-*` does not protect idempotency keys either because they have a TTL. Policies must be based on **data semantics**, not the mere presence of an expiration.

## 22. Rate Limiting: Choose Fail-Open or Fail-Closed Intentionally

Redis rate limiters often use TTL counters/windows:

```text
rate:user-42:window-123 -> 40
60-second TTL
```

With `allkeys-*` or `volatile-*`, the key can be evicted early, resetting the counter to 0 and granting the user unintended extra quota.

This may be acceptable for a soft load-shedding limiter, and unacceptable for strict abuse controls.

If using `noeviction`, commands incrementing the counter may be rejected when out of memory.

The application must define:

| Redis Failure | Priority Goal | Policy to Consider |
| --- | --- | --- |
| Product cache | Read availability | Controlled DB fallback |
| Soft rate limit | User experience | Bounded fail-open with monitoring |
| Anti-abuse rate limit | Prevent quota bypass | Fail-closed or alternative mechanism |
| OTP/login attempts | Security correctness | Do not accept requests by default |
| Lock/coordination | Synchronization correctness | Do not treat absent Redis key as proof of safety |

There is no single failure policy for all Redis use cases.

## 23. Redis Streams and Queues

Redis Streams or lists can be used as queues. If queued data cannot be lost, do not pick an eviction policy just because you want “Redis to always keep accepting messages.”

Dangerous example: `allkeys-lru` can make keys holding queue data vanish under RAM shortage, breaking complete processing. Pending entries, consumer groups, and retries do not replace durable storage or backups.

Consider:

- `noeviction` and capacity/quotas.
- Intentional stream trimming/retention policies.
- Appropriate persistence and replication.
- Consumer idempotency.
- External durable outbox/queue if zero message loss is required.
- Alerting when writes are rejected due to memory.
- Clear RPO/RTO targets.

**Policy-based queue trimming** is not the same as arbitrary Redis memory eviction. A queue with intentional retention must define what is deleted and when.

## 24. `maxmemory` and Spring Boot Are Two Different Configuration Layers

Spring Data Redis/Spring Boot determines **how the application connects and operates**:

```yaml
spring:
  data:
    redis:
      host: redis-cache.internal
      port: 6379
      timeout: 3s
```

The Redis server determines memory limits and eviction:

```conf
maxmemory 768mb
maxmemory-policy allkeys-lru
```

**Do not assume the Spring Boot property `spring.data.redis.*` sets `maxmemory` on the Redis server.**

Even if Java had permission to send `CONFIG SET`, changing global Redis policies from one application service can affect other services. Memory configuration should belong to the **infrastructure/ops** layer such as Redis config, Helm charts, Operators, Terraform, or managed-service parameter groups.

## 25. Spring Data Redis: Always Set Appropriate TTLs for Caches

A service using `StringRedisTemplate`:

```java
package com.example.cache;

import java.time.Duration;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheWriter {

    private final StringRedisTemplate redis;

    public ProductCacheWriter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void put(String productId, String json) {
        redis.opsForValue().set(
            "cache:product:" + productId,
            json,
            Duration.ofMinutes(5)
        );
    }

    public String get(String productId) {
        return redis.opsForValue().get(
            "cache:product:" + productId
        );
    }
}
```

A 5-minute TTL handles freshness and eventual cleanup. It **does not guarantee the key stays for at least 5 minutes** if the server has `allkeys-*`/`volatile-*` enabled for that key.

For cache-aside applications:

```text
GET cache -> hit -> return snapshot
          -> miss -> read database -> write cache with TTL -> return snapshot
```

The application must tolerate cache misses caused by TTL **or** eviction and design an appropriate fallback path.

## 26. Spring Cache with Default TTL Configuration

When using the Spring Cache abstraction:

```java
@Service
public class ProductQueryService {

    private final ProductRepository products;

    public ProductQueryService(ProductRepository products) {
        this.products = products;
    }

    @Cacheable(cacheNames = "productById", key = "#id")
    public ProductView findById(String id) {
        return products.findById(id).orElseThrow();
    }
}
```

When Spring Boot uses Redis `CacheManager`, you can set a default TTL in supported versions:

```yaml
spring:
  cache:
    type: redis
    redis:
      time-to-live: 10m
      cache-null-values: false
```

**Note:** This is the **TTL that Spring Cache sets on entries**, not server `maxmemory`. Redis eviction configuration is still managed on the Redis server side.

Appropriate caching/proxying must be enabled, such as `@EnableCaching` when required by the project; annotations do not automatically take effect on objects instantiated with `new` outside a Spring proxy.

## 27. Per-Cache TTL Using `RedisCacheManager`

Different cache types have different freshness needs.

Example:

```java
package com.example.cache;

import java.time.Duration;
import java.util.Map;

import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class RedisCachingConfig {

    @Bean
    public RedisCacheManager redisCacheManager(
            RedisConnectionFactory factory) {

        RedisCacheConfiguration defaults =
            RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(10))
                .disableCachingNullValues();

        Map<String, RedisCacheConfiguration> perCache =
            Map.of(
                "productById",
                defaults.entryTtl(Duration.ofMinutes(5)),
                "publicConfig",
                defaults.entryTtl(Duration.ofMinutes(30))
            );

        return RedisCacheManager.builder(factory)
            .cacheDefaults(defaults)
            .withInitialCacheConfigurations(perCache)
            .build();
    }
}
```

If the application needs to store JSON objects, configure a value serializer suited to the DTO/schema and data security; the default serializer in some Spring Data Redis configurations may not fit polyglot environments or multi-version deployments.

Cache entries with different TTLs **do not have separate memory quotas**. The Redis eviction policy still applies across the shared instance.

If you both define a custom `RedisCacheManager` and set `spring.cache.redis.*` properties, note that auto-configuration does not automatically guarantee all properties are applied to a custom bean.

## 28. Do Not Confuse Key Prefixes with Memory Quotas

Spring Cache can generate keys like:

```text
productById::42
publicConfig::feature-x
```

While `StringRedisTemplate` might use:

```text
cache:product:42
cache:config:feature-x
```

Prefixes help:

- Avoid key collisions.
- Group keys for controlled cleanup.
- Identify which source created a key.
- Version schemas/serializers.
- Separate environments/tenants when needed.

However, prefixes **do not**:

- Provide per-namespace memory caps.
- Apply separate eviction policies.
- Protect keys from `allkeys-*`.
- Guarantee one cache name is retained in preference over another.
- Provide isolation equivalent to a separate Redis process.

If two data groups need different eviction policies, separate the deployments/instances or use verified isolation capabilities provided by the platform.

## 29. Containers/Kubernetes: cgroups and Memory Headroom

In Kubernetes, a Redis container might have:

```yaml
resources:
  requests:
    memory: "2Gi"
  limits:
    memory: "3Gi"
```

That is the container's infrastructure limit, not Redis `maxmemory`.

A separate Redis config might specify:

```conf
maxmemory 2gb
maxmemory-policy allkeys-lru
```

**These numbers are illustrative, not a safe template for every workload.** Measure RSS, allocator fragmentation, replication buffers, client buffers, and persistence fork/COW.

A diagram:

```text
Container memory limit
    |
    +-- Redis managed data / maxmemory accounting
    +-- Redis process overhead
    +-- client/output/replication buffers
    +-- memory allocator fragmentation
    +-- persistence background activity (fork/COW)
    +-- OS/runtime overhead within the relevant limit
```

If the container limit is too low, the process can be OOM-killed before Redis eviction frees enough memory or during a background save.

### Ephemeral Filesystems and Persistence

Eviction handles RAM pressure; it does not replace RDB/AOF/persistence. If Redis stores data that must survive restarts, manage disks/volumes and backups separately. A `PersistentVolume` does not replace memory headroom or the right policy either.

## 30. Replication Complicates `maxmemory`

In a primary–replicas topology:

```text
Redis primary A ----replication----> Replica B
       |                                  |
   maxmemory A                        maxmemory B
   policy A                           policy B
```

Each Redis process has its own configuration and memory usage. Replication sends changes from primary to replicas, which does not mean memory/RSS on the two nodes is identical at every moment.

When the primary evicts a key, the deletion effect is propagated to replicas via the corresponding replication mechanism. Replicas may still lag due to asynchronous replication.

Some Redis versions/configurations have `replica-ignore-maxmemory`, causing replicas to typically ignore local maxmemory eviction decisions while acting as replicas. After failover, the promoted node becomes primary and may start enforcing **that process's own** eviction policy.

Therefore, you must:

- Intentionally align memory policy configurations across all promotable nodes.
- Monitor used memory/RSS on both primary and replicas.
- Verify your Redis version's behavior regarding `replica-ignore-maxmemory`.
- Avoid testing memory pressure only on the initial primary.
- Verify that the promoted node still has sufficient headroom and the right policy.

## 31. Sentinel Failover and Memory Policies

Redis Sentinel promotes a replica to master when quorum/election conditions are met. It **does not automatically rewrite the replica's maxmemory policy to match the old primary's policy**.

Example:

```text
Before:
  Redis A primary: maxmemory 1gb / allkeys-lfu
  Redis B replica: maxmemory 512mb / noeviction

Failover:
  B is promoted to primary
```

If B is not configured appropriately for the post-promotion load and dataset, the application may see write failures or different eviction behavior.

Monitoring should track:

- Current master identity.
- `CONFIG GET maxmemory` and `maxmemory-policy` on the current node.
- Used memory/RSS after promotion.
- Eviction/write error rate after failover.
- Read fallback/database load.
- Replica sync and persistence.

**Do not treat a `SENTINEL switch-master` event as proof that the application continues running smoothly under the same memory budget.**

## 32. Redis Cluster: `maxmemory` Per Primary/Shard

Redis Cluster shards the keyspace across 16,384 hash slots. Suppose there are three primaries:

```text
Primary A: 1 GiB memory limit, slots A
Primary B: 1 GiB memory limit, slots B
Primary C: 1 GiB memory limit, slots C
```

`maxmemory` is typically configured on **each Redis node**, not as a global 3 GiB pool that automatically balances all keys.

If shard A receives many hot keys or large payloads, it can hit memory pressure while B and C still have free space.

Things to monitor:

- Used memory / maxmemory **per primary**.
- Eviction rate per shard.
- Hit/miss/fallback rate for keys belonging to each shard.
- Redis Cluster slot ownership.
- Hot keys or hot hash tags.
- Memory pressure on replicas after failover.
- Reshard/scale-out capability and migration impact.

Adding replicas **does not increase the logical dataset capacity** of a shard; replicas duplicate data rather than splitting the keyspace into new shards.

Adding primaries and resharding can redistribute slots, but a single hot key still belongs to one slot and cannot be split across multiple nodes automatically.

## 33. Hash Tags Can Exhaust One Shard's RAM Early

Redis Cluster supports hash tags:

```text
cart:{user-42}:items
cart:{user-42}:total
```

Both keys land in the same hash slot. This is useful for multi-key operations or Lua scripts requiring the same slot.

However, if every key uses the same tag:

```text
cache:{global}:product:1
cache:{global}:product:2
cache:{global}:product:3
```

the entire workload can funnel into a single slot/shard, causing memory imbalance and concentrated evictions.

**Do not use a single global hash tag just to avoid `CROSSSLOT`.** Scope hash tags to aggregates that truly need atomicity, while monitoring slot distribution and hotspots.

## 34. Memory Metrics: `INFO memory`

Command:

```bash
redis-cli -h redis-cache.internal -p 6379 INFO memory
```

Common important fields:

| Field | Meaning |
| --- | --- |
| `used_memory` | Memory allocated by the Redis allocator per internal accounting |
| `used_memory_human` | Human-readable form of `used_memory` |
| `used_memory_rss` | Resident memory reported by the OS |
| `used_memory_peak` | Peak internal allocation recorded |
| `maxmemory` | Configured threshold |
| `maxmemory_policy` | Active eviction policy |
| `used_memory_dataset` | Estimated dataset portion |
| `used_memory_overhead` | Overhead portion per Redis metrics |
| `mem_fragmentation_ratio` | Metric related to fragmentation/RSS; interpret with care |
| `mem_not_counted_for_evict` | Memory excluded from Redis's eviction budget |
| `allocator_frag_ratio` | Allocator fragmentation signal in supported versions |

Not every Redis version exposes the exact same set of fields.

### Is RSS Larger Than `maxmemory` an Error?

Not necessarily. `maxmemory` is not a hard cap on RSS. Fragmentation, client/replication buffers, persistence activity, and memory accounting can all push RSS higher.

**However, RSS approaching or exceeding the container memory limit is a risk requiring action**, even when data memory is still below `maxmemory`.

Monitor all of:

```text
used_memory
used_memory_rss
maxmemory
used_memory_peak
mem_not_counted_for_evict
container_working_set / cgroup memory
```

## 35. `INFO stats`: Tracking Evictions and Cache Misses

Command:

```bash
redis-cli -h redis-cache.internal -p 6379 INFO stats
```

Commonly needed fields:

- `evicted_keys`: number of keys evicted due to the memory policy, usually a cumulative counter since process/metric reset.
- `expired_keys`: number of keys expired by Redis expiration.
- `keyspace_hits`: successful key lookups as defined by Redis stats.
- `keyspace_misses`: key lookups where the key was not found.
- Other connection/command/latency counters helpful for diagnostics.

**Distinguish eviction from expiration:**

```text
evicted_keys rising -> Redis is removing keys due to memory pressure
expired_keys rising -> keys are reaching TTL via expiration
```

Do not rely solely on `keyspace_hits/misses` to determine exact business cache-aside hit ratios, because Redis handles many key lookups from different consumers and command semantics affect how stats are counted.

At the Spring Boot layer, measure cache hit/miss **per cache name/use case** if you need to manage downstream load.

## 36. Other Memory Inspection Tools

Useful commands:

```bash
redis-cli -h redis.internal -p 6379 MEMORY STATS
redis-cli -h redis.internal -p 6379 MEMORY USAGE cache:product:42
redis-cli -h redis.internal -p 6379 MEMORY DOCTOR
redis-cli -h redis.internal -p 6379 INFO keyspace
```

Purpose:

- `MEMORY STATS`: memory usage breakdown.
- `MEMORY USAGE`: estimates memory for a specific key, with optional sampling for certain data types.
- `MEMORY DOCTOR`: diagnostic suggestions based on Redis heuristics.
- `INFO keyspace`: key counts and keys with expirations per database.

Do not scan the entire production keyspace by looping `MEMORY USAGE` over every key during peak load without accounting for cost. `KEYS *` can disrupt large datasets; if iterating keys is needed, use `SCAN` in a controlled manner and understand consistency semantics as the keyspace mutates.

## 37. Cache Memory Dashboard

A practical dashboard has at least four sections.

### Capacity

```text
used_memory / maxmemory
used_memory_rss / container_limit
used_memory_peak
mem_not_counted_for_evict
```

### Eviction and Expiration

```text
evicted_keys rate
expired_keys rate
cache key count
keys-with-expiration ratio
```

### Impact on the Spring App

```text
cache hit ratio by cache
cache miss rate
database fallback rate
Redis command latency p95/p99
Redis write errors / OOM exceptions
HTTP latency / error rate
```

### Topology and Recovery

```text
node role / master identity
replication lag
memory per Redis Cluster shard
failover event count
eviction spike after promotion
```

The metric names above describe semantics and do not automatically exist verbatim in every exporter. Verify the exact metric names and labels of your Redis exporter and Micrometer setup.

## 38. Alerting When Evictions Rise

An alert like:

```text
evicted_keys rate > 0
```

is not always an incident. In a cache pool configured with `allkeys-*`, eviction **can be normal by design**.

What matters is the **impact**:

- Is the eviction rate abnormally high compared to baseline?
- Has the cache hit ratio dropped sharply?
- Has database fallback traffic increased?
- Is API p95/p99 latency rising?
- Is Redis CPU high during eviction sampling?
- Is memory RSS approaching the container limit?
- Were critical keys mistakenly placed in the cache pool?

For a coordination pool using `noeviction`, rising `evicted_keys` can signal an altered configuration or misrouted instance, requiring immediate investigation.

### Write OOM Alerts

If Redis rejects a write due to memory, the application must record that error type clearly. Do not lump Redis OOM errors in with timeouts or cache misses.

For keys that must not be lost, write rejections must follow a **fail-request or conditional-retry** policy—never treat the operation as having succeeded.

## 39. Measuring Cache Hit Ratio Correctly

A ratio can be defined as:

```text
hit_ratio =
    hits / (hits + misses)
```

But you must know where “hits/misses” come from:

- Redis `INFO stats` per keyspace command lookup.
- Spring Cache abstraction/cache manager metrics.
- Business services measuring cache-aside hit/miss directly.

They can differ because:

- A single request issues multiple Redis commands.
- Redis stores keys other than cache entries.
- A single cache miss can trigger multiple Redis lookups.
- Local Spring caches sit in front of Redis.
- Application fallbacks or Redis bypasses occur.
- An evicted key can be rewarmed quickly.

To tune `allkeys-lru`/`allkeys-lfu`, use metrics close to **application workload and miss cost**, not just a single instance-wide Redis number.

## 40. Eviction and Cache Stampede

Suppose the hot key `cache:product:42` is evicted:

```text
1,000 near-simultaneous requests
    |
    v
GET cache:product:42 -> MISS
    |
    +--> 1,000 PostgreSQL queries
```

This causes a **cache stampede**, even when the database is the authoritative source.

Measures to consider:

- Per-key request coalescing/single-flight.
- Short-lived local caching for consistency-tolerant data.
- TTL jitter to reduce simultaneous expirations.
- Stale-while-revalidate when permitted by the data contract.
- Warming hot keys after deploys/failovers.
- Limiting fallback request concurrency.
- Short-lived caching of negative results if business rules allow.
- Scaling Redis or increasing headroom if eviction is caused by insufficient capacity.

TTL jitter addresses synchronized expirations; **it does not eliminate memory pressure when the total dataset exceeds the threshold**.

## 41. TTL Jitter Is Not a Substitute for Capacity Planning

Example Spring code adding TTL jitter:

```java
package com.example.cache;

import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CatalogCacheWriter {

    private final StringRedisTemplate redis;

    public CatalogCacheWriter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void cache(String id, String json) {
        long extraSeconds =
            ThreadLocalRandom.current().nextLong(0, 31);

        Duration ttl =
            Duration.ofSeconds(300 + extraSeconds);

        redis.opsForValue().set(
            "cache:catalog:" + id,
            json,
            ttl
        );
    }
}
```

This example spreads TTLs between 5 minutes and 5 minutes 30 seconds to prevent many keys from sharing the same expiration deadline.

Do not apply jitter arbitrarily to tokens, OTPs, idempotency keys, or locks where the expiration time carries strict business meaning.

Changing TTLs also does not increase Redis capacity; ensure the working set fits within memory limits.

## 42. Choosing TTL Based on Freshness and Rebuild Cost

For evictable caches:

| Data Type | Considerations When Choosing TTL |
| --- | --- |
| Product catalog | Staleness tolerance, update frequency |
| Product pricing | Must verify authoritative source at checkout |
| Feature flags | Propagation delay for changes, fallback |
| Static public data | Longer TTL possible if invalidation is reliable |
| Expensive query results | Recompute cost, input data churn |
| Negative cache | Avoid caching “not found” too long when new entities appear |

TTL is a consistency/freshness choice; eviction policy is a memory-pressure response choice. They work together without replacing one another.

For example, a 30-minute TTL + `allkeys-lfu`: an entry can expire after 30 minutes or be evicted earlier when memory is scarce.

## 43. Redis Eviction Does Not Protect Authoritative Source Correctness

A safe cache architecture:

```text
Spring API
    |
    +-- GET Redis cache
    |      |
    |      +-- hit -> return snapshot per policy
    |      |
    |      +-- miss / evicted
    |             |
    |             v
    +---------- PostgreSQL source of truth
                  |
                  v
             SET Redis cache TTL
```

If the Redis cache loses all data, business state remains in the database, though warm-up costs may occur.

If Redis is the sole store for carts, sessions, or reservations, eviction becomes **state loss**, not just degraded performance. Define the “source of truth” clearly before selecting a policy.

## 44. Why `noeviction` Still Needs an Out-of-RAM Plan

A Redis coordination pool:

```conf
maxmemory 512mb
maxmemory-policy noeviction
```

When memory exceeds the threshold:

- Writes creating new keys can fail.
- Incrementing counters or updating data structures can error depending on the command.
- Some reads may still succeed.
- Keys with TTL still expire.
- If the application mishandles errors, business behavior can break.

Design:

1. **Capacity alerts before hitting the threshold**.
2. **Quotas or admission control** at the application tier if needed.
3. **Do not proceed with business actions when a required write fails**.
4. **Idempotent retries**, never unbounded retries.
5. **Valid scaling/sharding/cleanup** per policy—never delete critical keys arbitrarily.
6. **Runbooks** for memory pressure and recovery procedures.

Preserving keys with `noeviction` means potentially sacrificing write availability when capacity is exhausted. That is an intentional trade-off.

## 45. Redis ACLs and Permission to Change Configuration

Commands:

```redis
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
CONFIG SET maxmemory-policy allkeys-lru
CONFIG REWRITE
```

may require corresponding Redis administrative privileges. Do not grant `CONFIG SET` to every business service just to “self-heal” memory pressure.

Some managed Redis services forbid changing configuration via `CONFIG SET`; you must use the control plane or provider parameters.

Do not let application startup arbitrarily override global Redis eviction policies if multiple teams share the instance, as a single deployment could unexpectedly cause critical state loss.

## 46. Changing `maxmemory-policy` at Runtime

Redis supports changing certain settings at runtime:

```bash
redis-cli -h redis-test.internal -p 6379 \
  CONFIG SET maxmemory-policy allkeys-lfu

redis-cli -h redis-test.internal -p 6379 \
  CONFIG SET maxmemory 768mb
```

**Use only in test environments or under an approved change procedure.**

Notes:

- Runtime `CONFIG SET` may not persist across restarts without appropriate persistence/config management.
- `CONFIG REWRITE` depends on permissions and file-write capability; do not treat it as a replacement for infrastructure-managed declarative configuration.
- If automation manages `redis.conf`, manual changes may be overwritten on the next deploy.
- Suddenly lowering `maxmemory` can trigger heavy evictions or write errors.
- Switching from `noeviction` to `allkeys-*` can drop critical keys before their TTL expires.

Treat this change as a **data contract change**, not just performance tuning.

## 47. Designing Memory Pressure Tests on Test Redis

Use a dedicated test Redis instance/container, never production.

A small-limit configuration for observation:

```conf
maxmemory 32mb
maxmemory-policy allkeys-lru
```

Scenario:

1. Ensure test Redis uses a dedicated namespace and holds no data that must be kept.
2. Write keys with known payload sizes.
3. Observe `INFO memory` and `INFO stats`.
4. Increase key count until eviction begins.
5. Verify `evicted_keys` increments.
6. Verify cache misses still fall back to the authoritative source.
7. Record memory/RSS and command latency.
8. Switch the policy to `noeviction` in the **test environment**.
9. Attempt further writes and record OOM errors.
10. Do not treat a small test run as proof of production safety.

To compare LRU vs. LFU, use an access workload with specific characteristics (hot keys, cold keys, bursts) and measure hit ratio and DB fallbacks under the same memory limit.

## 48. Creating a Controlled Test Workload

An application-level test algorithm:

```text
for i = 1..N:
    SET cache:test:i payload EX 300

for request in workload:
    GET cache:test:hot-key
    GET cache:test:random-key

periodically:
    INFO memory
    INFO stats
    collect API latency and DB fallback
```

Do not fire millions of commands at production Redis just to observe eviction.

### When Comparing Policies

Keep constant:

- Redis version.
- Dataset and size distribution.
- Client count and concurrency.
- Command mix.
- TTL distribution.
- Memory limit.
- Replication/persistence config.
- Warm-up period.
- p95/p99 measurements and total CPU.

If you change data, load, `maxmemory`, and policy simultaneously, it becomes very hard to isolate why the hit ratio changed.

## 49. Testing Volatile Policies When No Keys Have TTL

An important test:

```conf
maxmemory 32mb
maxmemory-policy volatile-lru
```

Test steps in test Redis:

1. Write many keys without TTL.
2. Write a group of keys with TTL.
3. Push memory pressure close to and past the limit.
4. Observe keys with TTL being evicted.
5. Once no TTL candidates remain and memory is still needed, observe write errors.
6. Compare `evicted_keys` and `expired_keys`.

This exercise clarifies that `volatile-*` **is not** an algorithm that automatically frees any available key; it is restricted to keys with an expiration.

Never run this test on a Redis instance holding real sessions or locks.

## 50. Testing Eviction Events

You can configure Redis keyspace notifications to listen for relevant events in a test environment. However:

- `notify-keyspace-events` must be enabled with the proper flags.
- Event delivery relies on Pub/Sub and is therefore at-most-once.
- Offline subscribers can miss events.
- Notifications arrive after the fact; they should not be used to prevent key loss.
- High eviction rates can produce high event/log volume.
- Do not rely solely on eviction listeners to count lost keys; Redis metrics are still required.

Example verification in an integration test: write a key with a long TTL, induce memory pressure, and verify the key disappears **before its TTL** alongside an increase in `evicted_keys`. You do not need to depend on notification timing to prove eviction behavior.

## 51. Common Configuration Mistakes

| Symptom | Causes to Check |
| --- | --- |
| Redis OOM despite `allkeys-*` | Memory accounting, evictions not keeping up, command overhead, actual active policy |
| Redis OOM under `volatile-*` | Not enough keys with TTL available to evict |
| Redis process OOM-killed | RSS/cgroup pressure outside `maxmemory` |
| Sessions log out early | Session keys evicted or wrong TTL |
| Idempotency duplicates occur | Keys evicted or state lost prematurely |
| Cache misses spike sharply | Evictions, synchronized TTL expiry, deploy/flush, topology |
| Database latency rises | Cache stampede following eviction |
| Evicted keys rise but hit ratio is stable | Likely normal cache behavior |
| Write errors spike after primary switch | Different config/headroom on promoted replica |
| One Cluster shard repeatedly OOMs | Hot slot, imbalance, per-node `maxmemory` |
| Keys do not expire as expected | TTL omitted or overwritten by update clearing expiration |
| Cache unchanged despite edited TTL property | Custom cache manager override, bean configuration |
| Read replica shows stale data | Replication lag, not eviction |
| `expired_keys` increases | TTL expiration, not eviction |

### Diagnostic Approach

1. Check actual `maxmemory` and policy.
2. Check `INFO memory`/RSS and cgroups.
3. Check `INFO stats` for eviction/expiration/hit/miss.
4. Identify what data resides on the instance.
5. Check Spring Cache TTL and key prefixes.
6. Check replicas/Cluster shards.
7. Cross-reference application and database metrics.
8. Review deployment changes near the incident timestamp.

Do not fix issues by arbitrarily raising `maxmemory` if the container lacks headroom.

## 52. Runbook: `used_memory` Approaching `maxmemory`

### Step 1 — Verify Telemetry

```bash
redis-cli -h redis.internal -p 6379 INFO memory
redis-cli -h redis.internal -p 6379 INFO stats
redis-cli -h redis.internal -p 6379 CONFIG GET maxmemory
redis-cli -h redis.internal -p 6379 CONFIG GET maxmemory-policy
```

### Step 2 — Classify the Instance

- Purely rebuildable cache?
- Holds sessions/locks/idempotency?
- Holds critical queues/Streams?
- Part of a Redis Cluster shard?
- Has replicas and persistence?

### Step 3 — Assess Current Risk

- Are evictions occurring?
- Are write errors rising?
- Is RSS near the cgroup limit?
- What are the cache hit ratio and DB fallback rate?
- Is there an abnormal hot key or hot shard?
- Does a replica have enough headroom if failover occurs?

### Step 4 — Choose Action Based on Data

For a **cache pool**:

- Increase capacity/scale/reshard if appropriate.
- Evaluate whether LRU or LFU fits better.
- Trim unnecessarily large payloads.
- Tune TTL/freshness and invalidation.
- Mitigate stampedes and fallback spikes.
- Do not wipe the entire cache unnecessarily.

For a **critical state pool**:

- Do not rashly switch to `allkeys-*`.
- Throttle or shed write load if necessary.
- Handle write failures intentionally.
- Scale or migrate workloads in a controlled way.
- Do not delete active coordination keys.
- Assess RPO/RTO and the authoritative source.

### Step 5 — Confirm Recovery

- Memory/RSS stabilizes with headroom.
- Eviction/write error rates return to expected ranges.
- Cache hit ratio and DB latency recover.
- Redis roles/replication are healthy.
- No critical state remains misplaced on the cache pool.
- Alerts and runbooks are updated.

## 53. When the Eviction Policy Changes During Failover

A subtle failure scenario:

```text
T0 Primary A: allkeys-lru / maxmemory 2gb
T1 Replica B: noeviction / maxmemory 1gb
T2 A fails, B is promoted
T3 Spring writes surge; B rejects writes due to memory exhaustion
```

Operational safeguards:

1. Manage Redis configuration consistently across all promotable nodes.
2. Attach a version/config checksum to deployments.
3. Collect `maxmemory` and `maxmemory-policy` per node.
4. Practice failovers in a test environment.
5. Verify a replica's memory budget for when it becomes primary.
6. Verify application error handling on Redis OOM.
7. Do not monitor only the initial primary while ignoring replicas.

Redis HA handles role switching; it does not automatically ensure replacement nodes have sufficient RAM or consistent policies.

## 54. Do Not Use Eviction as a Business-Ordered Data Deletion Mechanism

Eviction chooses keys based on memory policy, not by:

- Order creation date.
- Message processed status.
- Business priority.
- Recoverability of critical data.
- Minimum required token lifetime.
- Database commit order.
- Active user transaction state.

If intentional deletion is needed, design expiration, retention, trimming, or garbage collection according to business schema rules.

For example, Redis Stream `XTRIM` has its own retention logic; do not rely on global key eviction as a substitute for retaining acknowledged messages.

## 55. Capacity Planning Principles

### Estimate the Logical Dataset

Know:

```text
average and peak key counts
value size distribution
data types: String, Hash, Set, ZSet, Stream
key/prefix overhead
TTL and arrival rate
read/write distribution
```

An overly rough estimate:

```text
1 million keys x 200 bytes payload = 200 MB
```

is insufficient for real RAM, because Redis object overhead, key names, allocator behavior, and data structures can make total memory usage significantly larger.

### Measure with Realistic Workloads

Use `MEMORY USAGE` on representative keys and `INFO memory` under test workloads to obtain realistic figures.

### Account for Replicas

Logical dataset capacity resides on primaries/shards; replicas need their own memory to mirror the same data.

### Account for Growth

Measuring averages is not enough; account for peak traffic, promotion events, restart cache warm-ups, burst writes, and resharding.

### Consider Memory vs. Latency

A dataset sitting just below `maxmemory` might avoid eviction normally, yet a single burst can cause spikes. Leave headroom for variable activity.

## 56. Deployment Checklist

**Redis server**

- `maxmemory` chosen from RAM/RSS measurements, not set equal to the cgroup limit.
- `maxmemory-policy` matches the workload's key-loss tolerance.
- `maxmemory-samples`/LFU tuning applied if needed and load-tested.
- Memory headroom reserved for replication, client buffers, AOF/RDB, and COW.
- Monitoring in place for `INFO memory`, `INFO stats`, RSS, and cgroup memory.
- Alerts configured for write OOMs and process OOM-kills.
- Policies consistent across all promotable nodes.
- Capacity/scaling plan ready if cache growth exceeds projections.

**Spring Data Redis**

- Cache keys have TTLs suited for freshness; TTL is not treated as a minimum retention guarantee.
- `RedisCacheManager` configured with per-cache TTLs if needed.
- Serializers are compatible and key prefixes are clear.
- Cache misses fall back to the authoritative source.
- Cache stampede mitigation is in place.
- Redis errors and OOMs are not masked as cache misses when inappropriate.
- Idempotency/locks/rate limiters have explicit failure policies.
- Application startup does not arbitrarily mutate global Redis policies.

**Architecture**

- Rebuildable caches are separated from critical state when different policies are needed.
- Logical Redis DBs/prefixes are not treated as memory isolation.
- Redis Cluster is monitored per shard.
- Replica failover is tested with the target config and capacity.
- Backup/persistence is not confused with eviction.
- A runbook exists for memory pressure.

## 57. Exercise A — Choosing a Policy for a Product Catalog Cache

A service has:

```text
3 million product cache keys
a small subset of very hot products
PostgreSQL source of truth
cache misses can be tolerated and rebuilt
```

Tasks:

1. Choose `allkeys-lru` or `allkeys-lfu` and justify your choice.
2. Select a TTL based on freshness.
3. Identify metrics to compare the two policies.
4. Describe the cache stampede risk when a hot key is evicted.
5. Design a dedicated Redis load test with the same dataset and traffic pattern.

## 58. Exercise B — Distinguishing TTL from Eviction

A key:

```redis
SET cache:item:42 "v1" EX 600
```

Redis has `maxmemory-policy allkeys-lru`, and memory pressure begins after 60 seconds.

Questions:

1. Can the key disappear before 600 seconds?
2. If the key disappears at second 80, could it be due to TTL?
3. What can Redis `INFO stats` help distinguish?
4. Can you rely solely on keyspace notifications to determine the cause?
5. How should the Spring service handle the cache miss?

## 59. Exercise C — Why `volatile-lru` Does Not Protect Sessions

Redis contains:

```text
cache:product:42         5-minute TTL
session:user:1001        30-minute TTL
lock:order:42            30-second TTL
idempotency:order:9001   24-hour TTL
```

Policy is `volatile-lru`.

Tasks:

1. List all keys eligible for eviction.
2. Explain why having a TTL does not mean a key may be lost early.
3. Propose how to isolate cache and critical state.
4. State the policy for when the critical pool runs out of memory.
5. Explain why `noeviction` still requires idempotency and recovery.

## 60. Exercise D — Container OOM Before `maxmemory` Is Reached

Redis container:

```text
container limit: 2 GiB
maxmemory:      1.8 GiB
```

During an RDB snapshot, the process is OOM-killed.

Tasks:

1. Explain why `maxmemory` does not strictly bound RSS.
2. Identify the metrics to collect.
3. Identify fork/COW, buffer, and fragmentation factors.
4. Design new headroom based on measurements.
5. Retest under equivalent workload and persistence conditions.

## 61. Exercise E — Redis Cluster Running Out of RAM on One Shard

A Redis Cluster has three primaries:

```text
A: 95% maxmemory, evictions rising sharply
B: 40% maxmemory
C: 35% maxmemory
```

Tasks:

1. Investigate slot/key distribution and hot hash tags.
2. Explain why `maxmemory` is not a cluster-wide budget.
3. Propose controlled scaling/resharding.
4. Explain the limitations of adding replicas.
5. Identify per-shard metrics to check before and after the change.

## 62. Exercise F — `noeviction` Causing Write Failures

A Redis coordination pool uses `noeviction`. The application sends `SET idempotency:order:9001 ...` and receives a memory error.

Tasks:

1. Design the error response/failure policy.
2. Explain why the request must not be assumed to have idempotency protection.
3. Determine which request IDs can be safely retried.
4. Choose valid scaling/cleanup actions.
5. Design alerts to catch pressure before all writes are rejected.

## 63. Frequently Asked Questions

**Does Redis `maxmemory` limit process RSS?**  
Not strictly. Memory RSS can exceed `maxmemory` due to fragmentation, buffers, persistence activity, and other memory accounting components.

**Should `allkeys-lru` be chosen for every Redis instance?**  
No. It allows evicting any key, including sessions, locks, and idempotency keys. It is only reasonable when every key may be lost early or the system accepts the consequences.

**What is the difference between `allkeys-lru` and `allkeys-lfu`?**  
LRU prioritizes recently used keys; LFU estimates usage frequency with a decay mechanism. Measure both against your real workload.

**Does `volatile-lru` only delete expired keys?**  
No. It can evict **unexpired** keys as long as they have an expiration set.

**Does `volatile-ttl` protect sessions longer than cache entries?**  
There is no guarantee by data type. It only favors keys with shorter remaining TTL, and sessions remain candidates if they have a TTL.

**What happens if a volatile policy has no keys with TTL?**  
Redis may be unable to free memory via eviction and will reject writes that require more memory.

**Does `noeviction` mean keys are never lost?**  
No. Keys still expire by TTL, get deleted by the application, or can be lost due to persistence/failover failures or other causes. It only disables proactive memory-policy eviction.

**Should a TTL be set on every cache entry?**  
TTLs are usually helpful to bound staleness and data lifecycle, though specific policies depend on freshness/invalidation needs. `allkeys-*` can still evict caches without TTL; `volatile-*` only considers keys with TTL.

**Does Spring Boot automatically configure Redis `maxmemory` via `spring.data.redis`?**  
Not via standard connection properties. `maxmemory` is a Redis server or managed-service configuration.

**Can different `maxmemory-policy` values be assigned to Redis DB 0 and DB 1?**  
Not within a single Redis instance in that way. Redis logical DBs do not create separate memory policies.

**Why are evictions rising while Redis still operates normally?**  
In a cache pool, eviction can be expected design behavior to stay within the memory budget. Check hit ratio, database fallbacks, and latency.

**Why are write OOMs happening while the process is still alive?**  
`noeviction`, or `volatile-*` with no eligible candidates left, can cause Redis to reject memory-allocating writes even while `PING` succeeds.

**Does Redis Cluster have a shared `maxmemory` across all nodes?**  
Normally no. `maxmemory` is managed per node; monitor each shard individually.

**Will a replica have the same policy as the primary after failover?**  
Only if you manage configurations and versions consistently. Do not assume Sentinel or Cluster automatically copies the old primary's policy to the newly promoted node.

**Can eviction affect distributed locks?**  
Yes. If a lock key is evicted before its TTL, another worker can acquire the lock; isolation and appropriate business safeguards are required.

**Can eviction break idempotency?**  
Yes, because removing a deduplication key before its retention window expires can cause a retry to be treated as a new request.

**Do AOF or replication recover evicted keys?**  
Eviction is a keyspace mutation propagated/persisted according to Redis mechanisms; persistence and replication are not mechanisms to restore historical keys evicted by policy.

**If the cache hit ratio drops, can we just increase `maxmemory`?**  
Not always. Check RAM/RSS headroom, hot keys, TTLs, workload patterns, serialization size, cache stampedes, and scaling limits.

## 64. Summary

Configuring memory limits and eviction in Spring Data Redis must start from **data purpose**, not a default policy:

1. `maxmemory` sets the Redis memory threshold for eviction/write decisions; it is **not an absolute RSS limit**.
2. `allkeys-lru` and `allkeys-lfu` fit many **rebuildable caches**; choose based on working set and benchmarks.
3. `volatile-*` only evicts keys with TTL, yet **does not protect sessions, locks, or idempotency keys that also carry TTLs**.
4. `noeviction` avoids losing keys early under memory pressure, at the trade-off that **writes can fail** when memory runs out.
5. TTL controls **expiration/freshness**, not a promise that a key survives until the TTL deadline.
6. Redis server memory policy is distinct from Spring Cache TTL; a Spring Boot application should not arbitrarily alter global server policies.
7. Key prefixes and Redis logical DBs do not create memory-policy isolation; separate instances/deployments when data classes have different contracts.
8. Monitor `used_memory`, `used_memory_rss`, `evicted_keys`, `expired_keys`, cache hit/miss, DB fallback, and application errors.
9. With Sentinel/Cluster, track per-node/per-shard config, memory headroom, and post-failover behavior.
10. Build runbooks and run memory-pressure tests in an isolated environment before production deployment.

**A sound policy ensures Redis frees only the keys permitted to be lost under resource pressure, while the application behaves deterministically on cache misses or write errors.**

## References

- [Redis – Key eviction](https://redis.io/docs/latest/develop/reference/eviction/)
- [Redis – Redis configuration](https://redis.io/docs/latest/operate/oss_and_stack/management/config/)
- [Redis – INFO](https://redis.io/docs/latest/commands/info/)
- [Redis – MEMORY STATS](https://redis.io/docs/latest/commands/memory-stats/)
- [Redis – MEMORY USAGE](https://redis.io/docs/latest/commands/memory-usage/)
- [Redis – EXPIRE](https://redis.io/docs/latest/commands/expire/)
- [Redis – SET](https://redis.io/docs/latest/commands/set/)
- [Redis – Redis replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Redis – Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
- [Redis – Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
- [Spring Data Redis – Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis – RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Boot – Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)
- [Spring Boot – Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
