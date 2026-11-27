# Evaluating the Need for Sharding, Replication, and Local Caching

In a system using **Spring Data Redis**, Redis typically sits between the Java application and the database to cut read latency, limit queries to the source of truth, and support fast data structures. As traffic grows, three options usually come to the table:

1. **Sharding:** partitioning the keyspace and processing load across multiple Redis primaries, typically via Redis Cluster.
2. **Replication:** maintaining replicas of a primary for high availability, recovery, and in certain cases read load distribution.
3. **Local caching (L1 cache):** keeping a subset of data inside each instance's JVM—for example with Caffeine—to skip Redis round trips for frequently read keys.

These three techniques **solve different bottlenecks**. Sharding expands data capacity and write throughput across primaries; replication adds copies without splitting write load; local caching reduces Redis calls from the application at the cost of per-instance heap and stale-data risk.

This lesson focuses on **how to evaluate when each solution is warranted**, how to measure performance and cost, consistency boundaries, Spring Data Redis integration examples, and a rollout testing process before production.

## 1. Start With the Question: Where Is the System Slow?

Do not switch to Redis Cluster simply because HTTP requests increased. Locate the real bottleneck first.

A read request may pass through:

```text
Browser / API client
         |
         v
Load balancer
         |
         v
Spring Boot instance
         |
         +----> In-JVM L1 cache (if present)
         |           |
         |        Hit? -> return immediately
         |
         +----> Spring Data Redis
         |           |
         |        Redis GET
         |           |
         |        Hit? -> return data
         |
         +----> Database / source of truth
                     |
                     v
              Return result and populate cache
```

Request latency also depends on:

- Connection setup, TLS, and network RTT between the application and Redis.
- How many Redis commands a single request actually invokes.
- JSON or JDK serialization/deserialization.
- Redis primary CPU and memory, command length, and big/hot keys.
- Java application CPU, thread pools, event loops, and connections.
- Cache hit/miss ratio and database query time on misses.
- Timeouts, retries, failovers, or GC pauses.
- Instance count and how requests distribute across instances.

A request slowed by a bad SQL query or oversized Java object deserialization **will not necessarily improve by adding Redis replicas**. Conversely, if Redis network/CPU is overloaded by millions of `GET`s on a tiny set of keys, an L1 cache can help far more than sharding keys across nodes.

### Symptom Identification Table

| Prominent Symptom | Hypothesis to Verify | Potentially Appropriate Solution |
|---|---|---|
| Redis primary near RAM limit and keys keep growing | Large working set, unsuitable TTL/eviction | Clean up data, optimize keys/values, then consider sharding |
| High Redis primary CPU despite high cache hit rate | High command QPS, big keys, Lua/scripts, hot keys | Optimize commands; shard if load spans many keys; L1 if read-hot |
| High app–Redis network RTT, many round trips per request | Network topology, command count, Redis placement | Batch/pipeline appropriately; L1 for repeated reads |
| Database load spikes on Redis misses | Low hit rate, short TTL, cache stampede | Redesign cache keys/TTLs, request coalescing, warming |
| Need tolerance for primary failure | Availability and failover | Replication/Sentinel or Redis Cluster HA |
| Heavy GETs, light writes, replicas able to serve reads | Primary read bottleneck | Read replicas if eventual consistency is acceptable |
| One extremely hot key, many requests hitting one key | Hot key pinned to one slot | L1, request coalescing, shrink payload; standard sharding rarely helps |
| Latency spikes only during app deploys/GC | JVM, thread pools, cold start | Optimize application; hold off changing Redis topology |

**Principle:** choose solutions based on **metrics showing the bottleneck**, not the number of architectural layers available.

## 2. Establish a Baseline Before Changing Anything

A minimal baseline should capture both normal and peak hours:

| Category | Metric | Meaning |
|---|---|---|
| HTTP | QPS, errors, p50/p95/p99 latency | User experience |
| Redis | GET/SET/DEL/EVAL ops/s | Command types and rates |
| Redis | Command latency, slowlog | Whether the node is stalled by slow commands |
| Redis | CPU, memory, fragmentation, eviction | Resource bottlenecks |
| Redis | Network ingress/egress | Data transfer limits |
| App | Connection pool, timeouts, retries | Client wait cost on Redis |
| Cache | Hit/miss per cache name | How many origin queries Redis saves |
| Payload | Average and tail key/value sizes | Big keys, network, and serialization |
| DB | QPS, connection utilization, p95 query | Capacity during cache misses |
| HA | Replica lag, reconnects, failover time | Reliability across topology changes |

Redis CLI commands in an authorized observation environment:

```bash
redis-cli INFO stats
redis-cli INFO commandstats
redis-cli INFO memory
redis-cli INFO clients
redis-cli INFO replication
redis-cli SLOWLOG GET 10
```

Notes:

- `SLOWLOG` measures server-side Redis command execution time, **excluding** full network transit, connection wait, and Java deserialization.
- `INFO` from one Redis node does not represent an entire Redis Cluster.
- Time-series metrics capture peaks; a single `INFO` snapshot during idle hours is insufficient.
- Do not run `KEYS *` or prolonged `MONITOR` in production just to gather metrics.

### Separating Throughput and Latency

Redis can execute many commands/second while p99 still climbs if expensive commands, network congestion, or traffic bursts occur. Examine both **successful commands per second** and the **response-time distribution**.

For concurrent workloads, a useful sanity check is Little's Law:

```text
Average in-flight tasks
    ≈ throughput (tasks/second) × average completion time (seconds)
```

If the system serves 10,000 requests/s and each request holds a resource for 20 ms on average, average concurrency is roughly 200. This estimates steady-state capacity; it does not guarantee Redis meets that exact figure under bursts or tail latency.

## 3. Three Solutions for Three Problem Classes

```text
Performance and availability needs
             |
   +---------+----------+
   |         |          |
   v         v          v
Sharding  Replication  Local cache
   |         |          |
   v         v          v
Split keys Replicas /   Cut GETs from
and write  failover /   application to
load       stale reads  Redis
   |         |          |
   +---------+----------+
             |
             v
   Verify consistency,
   operations, cost, tests
```

### Comparison Matrix

| Criterion | Sharding / Redis Cluster | Replication | Local Cache |
|---|---|---|---|
| Increases total data capacity | Yes, splits data across primaries | No, replicas copy the same dataset | Caches only a subset per JVM |
| Distributes write load | Yes, if keys span slots | Does not increase single-primary write capacity | Does not offload write load |
| Distributes read load | Yes across primaries; can add replicas | Yes, if reads route to replicas | Yes, on L1 hits |
| Improves availability | Requires per-shard replicas/failover | Primary purpose | L1 masks some read outages, does not replace Redis HA |
| Cuts network RTT to Redis | Not necessarily | Not necessarily | Yes on local hits |
| Stale data risk | Cross-key/reshard/routing, or replicas if used | Replica lag | Per-instance L1 can lag behind |
| Multi-key/transaction limits | Hash slot / cross-slot rules | Still tied to primary | Must sync manually with Redis/DB |
| Operational cost | Topology/resharding complexity | Memory/replication/failover | JVM heap/invalidation/cold start |
| Best suited when | One primary runs out of CPU/RAM/distributed throughput | Need HA or stale-tolerant read scaling | High repeat reads, bounded TTL/staleness acceptable |

There is no rule requiring all three. One system may need only Redis Standalone + replica; another uses Redis Cluster without L1; another with small static lookup data benefits from L1 without a cluster.

## 4. What Is Sharding?

**Sharding** divides the keyset into partitions managed by different Redis primaries. In **Redis Cluster**, the keyspace is divided into **16,384 hash slots**; each primary owns a subset of slots.

```text
                 Spring Boot clients
                         |
                         v
                Lettuce Cluster client
                         |
       +-----------------+-----------------+
       |                 |                 |
       v                 v                 v
    Primary A         Primary B         Primary C
   slots 0..5000    slots 5001..11000  slots 11001..16383
       |                 |                 |
    Replica A         Replica B         Replica C
```

These slot ranges are illustrative only. In practice, slot assignments follow your Redis Cluster topology and shift during scaling or rebalancing.

The application does not hardcode a fixed primary per key. A cluster-aware client like Lettuce computes the slot from key bytes, locates the owning node, and handles cluster redirections.

### When Sharding Truly Helps

Sharding is worth considering when:

- **One Redis primary lacks enough memory** for the working set and you cannot simply trim data, TTLs, or value sizes.
- **Aggregate read/write load spans many keys**, saturating one primary's CPU or network.
- You need horizontal scaling by adding primaries and rebalancing slots.
- Workload keys are designed so aggregates/tenants span slots instead of piling onto one slot.

Illustrative estimate (not a benchmark):

```text
Redis working set: 90 GiB
One primary safe capacity: ~35 GiB usable memory
Headroom requirement: already factored into usable memory
Conclusion: need multiple primaries or a smaller working set
```

Spreading evenly across 3 primaries averages ~30 GiB/primary. However, you must also budget for **replication, fragmentation, index overhead, big keys, skew, and resharding time**. Never treat an ideal even split as final capacity planning.

### Sharding Does Not Fix a Hot Key

If 40% of GET requests target the same `config:global`, that key sits in **one slot** served by one primary. Adding primaries does not split one hot key across multiple nodes.

Better options may include:

- L1 local cache with suitable TTL.
- Shrinking payload size.
- Eliminating duplicate GETs within the same HTTP request.
- Request coalescing/single-flight on cache miss.
- Partitionable data design if semantics allow.
- Replication read scaling when eventual consistency is acceptable.

Merely "cloning key names" into multiple read copies complicates invalidation and consistency; design and benchmark it deliberately.

## 5. Redis Cluster: Slots, Hash Tags, and Spring Data Redis Impact

Redis Cluster computes a key's slot from its bytes via the hash function. Keys sharing the same **hash tag** land in the same slot.

```text
cart:{user-42}:items
cart:{user-42}:total
cart:{user-42}:version
```

All three use `{user-42}` to compute the slot, supporting multi-key operations that require same-slot placement.

Conversely:

```text
cart:user-42:items
cart:user-42:total
```

are not guaranteed to share a slot even though both belong to the same user.

### 5.1. Multi-Key Commands and CROSSSLOT

Commands like `MGET`, `MSET`, multi-key Lua scripts, and `MULTI`/`EXEC` transactions are subject to slot/topology constraints. If keys span slots, Redis can reject them with `CROSSSLOT`, or some client APIs may split operations into independent commands where supported.

**Client-side command splitting does not provide cluster-wide atomicity.**

Example:

```text
Primary A: order:{42}:status
Primary B: stock:{sku-1}:available

SET status succeeds on A
DECRBY stock fails on B

=> Partial state can occur
```

For invariants requiring atomicity, group truly coupled keys into the same slot when architecture allows, or keep authoritative transactions in an appropriate database.

### 5.2. Avoid Overly Broad Hash Tags

Do not wrap every key in `{global}` just so multi-key commands work:

```text
product:{global}:1
product:{global}:2
user:{global}:100
order:{global}:500
```

That funnels most data into one slot and one primary, defeating sharding. Scope hash tags to the **aggregate requiring atomic operations**, never the whole system.

### 5.3. Serializers Affect Physical Keys

`StringRedisTemplate` uses a String key serializer. A `RedisTemplate` with a different key serializer produces different key bytes, yielding different hash slots. Never compute slots from Java Strings while ignoring the active serializer.

When migrating from Standalone to Cluster, verify that namespaces, serializers, key patterns, and Lua/multi-key operations are all compatible.

## 6. Configuring Spring Data Redis for Redis Cluster

With Spring Boot using Lettuce, configuration can look like:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-1.example.internal:6379
          - redis-2.example.internal:6379
          - redis-3.example.internal:6379
        max-redirects: 5
      timeout: 2s
```

These are example values, not real server addresses. Listed nodes act as **seed nodes**; the driver discovers topology and connects to other nodes advertised by Redis Cluster.

Points to verify in production:

- Every cluster-advertised node address is reachable from the application network.
- TLS and ACLs/credentials are configured properly.
- Lettuce cluster topology refresh handles node changes, `MOVED`/`ASK`, and failovers.
- The application never hardcodes primary IPs per key.
- `RedisCacheManager`, templates, and script executors all target the intended deployment.
- Connect timeouts, command timeouts, and retry budgets are deliberate.
- Replica read preferences are enabled only when stale reads are acceptable.

For single-key commands, `RedisTemplate` is usually sufficient; the driver routes by slot automatically. `RedisClusterConnection` is needed mainly for node/slot inspection, per-primary scans, and cluster administration.

### Do Not Expect Sharding Alone to Cut Latency

A single-key GET before and after moving to Cluster still incurs network round trips and deserialization. Cluster can improve tail latency **if the old primary was overloaded**, yet can also add redirects, topology overhead, and extra connections.

Always benchmark under the same workload and network conditions. Sharding's core benefit is **capacity/throughput scale-out**, not making every individual command faster.

## 7. Evaluating Load Distribution and Hot Slots

Data rarely distributes perfectly evenly. One large tenant, a promotion, or a dashboard key can create a hot slot.

Example:

```text
Primary A: 30% of keys, 70% of GET QPS
Primary B: 35% of keys, 15% of GET QPS
Primary C: 35% of keys, 15% of GET QPS
```

Even with balanced memory, Primary A can still saturate CPU/network.

Questions to measure:

1. Do value sizes vary wildly across keys?
2. Do a handful of keys receive vastly higher read QPS than the rest?
3. Are expensive commands like large `ZRANGE` or long Lua scripts concentrated on one shard?
4. Do hash tags cram all data of a huge tenant into one slot?
5. Do cluster-wide scans or batch jobs create skewed node load?
6. Do scatter/gather multi-key `MGET`s multiply total command count?

Sharding succeeds only when it **distributes both data and load**, not merely adds nodes to an architecture diagram.

### 7.1. Big Keys Do Not Disappear Automatically

A Redis Hash with millions of fields is still **one key** living on one slot. Adding primaries to a cluster does not split that key's contents.

If needed, redesign keys:

```text
user-events:{user-42}:2026-01
user-events:{user-42}:2026-02
...
```

Key redesign must consider queries, retention, and atomicity; keeping the same `{user-42}` hash tag still pins them to one slot. To spread across months or buckets, adjust hash tags along permitted consistency boundaries.

### 7.2. Resharding Also Requires Spare Capacity

During slot migration, Redis handles extra network and I/O; clients see redirects; cache misses or retries may rise. When sizing Cluster, reserve headroom beyond normal load for:

- Failover / losing a node.
- Resharding / key migration.
- Replication catch-up.
- Traffic peaks during rolling deployments.
- Rebalancing when hot slots emerge.

## 8. Replication: What Problems Do Replicas Solve?

**Redis replication** copies data from a primary to one or more replicas. Typical goals include:

- Improving resilience when a primary fails.
- Allowing Sentinel or Redis Cluster to promote a replica per configuration.
- Serving part of **read traffic** on replicas when consistency policy permits.
- Offloading certain read/reporting queries from the primary.

```text
               Spring Data Redis
                       |
                 Write to primary
                       |
                       v
                    Primary
                       |
            Async replication
                 /         \
                v           v
            Replica A    Replica B
                |           |
       Read traffic?   Read traffic?
        (if enabled)    (if enabled)
```

Replicas **duplicate the same dataset**. If the primary holds a 40 GiB working set, adding two replicas does not shrink the primary to 13.3 GiB. Each copy needs matching memory and resources.

Replication also does not distribute **writes**: writes still hit the owning primary, and replication adds network and synchronization work.

### 8.1. Replication Does Not Mean Synchronous Consistency

Standard Redis replication is **asynchronous**. A write acknowledged by the primary may not yet exist on a replica when a client reads.

```text
T0: App A SET order:42 PAID on primary
T1: Primary returns success
T2: App B GET order:42 from lagging replica
T3: Replica returns PENDING
T4: Replica applies update and returns PAID
```

If reading from replicas, the application must **tolerate eventual consistency** or route reads to the primary whenever staleness is unacceptable.

### 8.2. Read-Your-Writes Is Not Guaranteed by Default

In Reactor or synchronous Java:

```java
redis.opsForValue()
        .set("order:42:status", "PAID");

String state = redis.opsForValue()
        .get("order:42:status");
```

Sequential client calls do not guarantee `GET` reads the just-written value if reads route to a lagging replica.

Options:

- Read from **primary** for operations requiring freshness.
- Return the result of the write/script directly where suitable.
- Embed a data version and check minimum required version on read.
- Use bounded read retries when stale reads are detected—never infinite retries.
- Never enable replica reads for security, balance, or inventory decisions without a valid consistency contract.

## 9. Sentinel, Redis Cluster HA, and Replica Count

Two common topologies:

### 9.1. Standalone Primary + Replicas + Sentinel

```text
                 Application
                      |
               Sentinel discovery
                      |
                      v
                   Primary
                  /       \
                 v         v
             Replica A  Replica B

Primary fails
    |
    v
Sentinel promotes one replica as new primary
```

Sentinel handles monitoring and failover orchestration; it does not shard the keyspace across multiple primaries holding distinct key subsets.

### 9.2. Redis Cluster with Replicas Per Shard

```text
                 Redis Cluster
          +------------+------------+
          |            |            |
       Primary A    Primary B    Primary C
          |            |            |
       Replica A    Replica B    Replica C
```

Cluster partitions keys by slot across primaries; each primary's replica holds a copy of that shard. This combines **sharding and replication**.

Adding primaries scales out working set and command load; adding replicas gives each shard failover redundancy or read scaling if enabled. Base replica counts and AZ/host placement on availability requirements rather than bare minimum node counts.

### 9.3. Failover Can Lose Writes or Duplicate Effects

Redis does not guarantee every write acknowledged by a primary reached a replica prior to failover. If a primary crashes after acknowledging a write before replicating it, the promoted primary may lack that update.

Furthermore, network timeouts leave clients unsure whether an `INCR` executed. Retrying non-idempotent side-effecting commands can run them twice.

Thus, replication provides HA yet **does not provide exactly-once business semantics or absolute durability**. Critical data still needs an authoritative transactional store and idempotency/reconciliation workflows.

## 10. Replication and Read Scaling: Consistency Trade-Offs

If a primary receives heavy `GET` load across many keys, offloading some reads to replicas can be tested.

Load example:

```text
Primary:
    60,000 GET/s
    4,000 writes/s

Adding replicas:
    Offload part of GETs to replicas
    Primary still handles writes
```

Benefits materialize only when:

1. The driver/client actually routes part of reads to replicas.
2. Replicas have sufficient CPU, memory, and network capacity.
3. The application tolerates stale data within measured replication lag.
4. Write rate and replication traffic do not further saturate the primary.
5. Failover, reconnect, and read preference behavior are thoroughly tested.

**Adding replicas while all GETs still hit the primary will not raise read throughput** as intended. Verify with per-node command metrics.

### 10.1. Lettuce Read Preference

Lettuce configures primary/replica read routing via client settings. Directional example when configuring `LettuceClientConfiguration` explicitly:

```java
import io.lettuce.core.ReadFrom;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;

LettuceClientConfiguration clientConfig =
        LettuceClientConfiguration.builder()
                .readFrom(ReadFrom.REPLICA_PREFERRED)
                .build();
```

This is **only part of the client config**, not a complete factory configuration. You still must construct `LettuceConnectionFactory` with the appropriate Redis topology and client config; Standalone, Sentinel, and Cluster discover replicas differently. Do not assume adding `ReadFrom.REPLICA_PREFERRED` alone enables replica reads in every deployment.

When using Spring Boot auto-configuration, align configuration with your Boot/Lettuce version and avoid creating duplicate connection factory beans.

### 10.2. WAIT and Durability Limits

Redis `WAIT` blocks until a specified number of replicas acknowledge prior writes on that connection. It can mitigate some replication lag risks within a sequence, yet **does not turn Redis replication into a synchronous durable transaction or guarantee survival across all failover/persistence failures**.

Never treat `WAIT` as an "absolute durable commit" promise; examine timeouts, actual responding replicas, and failover/persistence edge cases.

### 10.3. Data That Should Not Be Read Stale

Read paths requiring special care:

- Login sessions and session revocation.
- Recently revoked permissions/roles.
- Idempotency keys, nonces, and anti-replay tokens.
- Distributed lock state.
- Balances, quotas, and inventory used for write decisions.
- Business state immediately post-commit.

Using read replicas for dashboards, catalogs, or lag-tolerant metrics is far safer than using them for sensitive access decisions.

## 11. Local Caching: L1 in Front of Redis L2

A **local cache** resides directly in the memory of each Java instance—commonly implemented with Caffeine.

```text
                   HTTP request
                        |
                        v
                Spring Boot instance
                        |
                        v
                 L1 Caffeine
                 /          \
              HIT           MISS
               |             |
               v             v
           Return          L2 Redis
                           /      \
                        HIT       MISS
                         |          |
                         v          v
                     Populate L1   Database
                                    |
                                    v
                              Populate L2 + L1
```

L1 delivers ultra-low latency with zero network round trips. Redis remains the shared L2 across instances; the database remains the authoritative source if Redis is only a cache.

However, L1 gives each instance **its own private copy**:

```text
App A: L1 product:42 = version 5
App B: L1 product:42 = version 5
App C: L1 product:42 = version 5

Database/Redis updated to version 6.

Without proper invalidation:
App A/B/C may still serve version 5 until L1 TTL expires.
```

Thus, L1 is not just a speedup—it introduces **another consistency layer** that must be managed.

## 12. Evaluating L1 Benefit via Hit Rate

Suppose a system sees:

- Cacheable reads: 20,000 requests/second.
- L1 hit rate: 80%.
- On requests that miss L1, Redis L2 hit rate: 90%.
- Assume at most one cache lookup per request in this simplified example.

Estimated Redis GETs:

```text
Redis GET/s = 20,000 × (1 - 0.80)
            = 4,000 GET/s
```

Database reads caused by missing both layers:

```text
DB reads/s = 20,000 × (1 - 0.80) × (1 - 0.90)
           = 400 reads/s
```

Here **L2 hit rate is conditional on requests that missed L1**. Do not add 80% + 90% into 170%.

Before L1, assuming Redis hit rate was 90% across all 20,000 requests/s, the database saw roughly 2,000 reads/s. Adding L1 also shifts the key distribution and effective TTL seen by Redis, so **do not assume L2 hit rate stays unchanged**. These numbers are planning estimates for designing benchmarks.

### 12.1. When Does L1 Pay Off Most?

- Data is read repeatedly on the **same instance**.
- Redis serialization/network cost is high relative to a local lookup.
- Values are small with clear memory caps.
- Data changes infrequently or tolerates staleness up to TTL.
- Invalidation exists when fresher reads than TTL are needed.
- Telemetry measures hit/miss per tier, not just a blended total.

If traffic spreads across millions of one-off keys, L1 hit rate will be low. Caffeine then just burns heap and increases GC with little gain.

### 12.2. Local Cache Lives Across All Instances

With 20 Java instances each caching up to 200 MiB, aggregate L1 memory across the fleet reaches roughly 4 GiB (before overhead and variance). This memory is **per-app-instance**, not a shared pool expanding Redis capacity.

If a hot key appears on every instance, it exists in 20 copies. That cuts Redis reads while requiring multi-instance invalidation and risking simultaneous stale copies.

## 13. Example: Caffeine L1 + Spring Data Redis L2

Example using **Spring Boot + Caffeine + StringRedisTemplate** with cache-aside for a product catalog. The database is the source of truth. Caffeine holds a small subset, while Redis holds the cross-instance shared cache.

Dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
```

In reactive WebFlux apps, never call blocking `StringRedisTemplate` on the event loop; the example below targets synchronous Java/Spring MVC apps. For reactive stacks, use `ReactiveRedisTemplate` and matching non-blocking cache coordination.

### 13.1. Model and Data Source

```java
public record ProductView(
        String id,
        String name,
        long priceInCents,
        long version) {
}
```

```java
import java.util.Optional;

public interface ProductSource {
    Optional<ProductView> findById(String productId);
}
```

`version` is a business version managed by the data source, not Redis TTL or local lookup time. It helps detect and avoid overwriting newer snapshots with older ones.

### 13.2. Declaring Bounded L1

```java
import java.time.Duration;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ProductLocalCacheConfiguration {

    @Bean
    Cache<String, ProductView> localProductCache() {
        return Caffeine.newBuilder()
                .maximumSize(10_000)
                .expireAfterWrite(Duration.ofSeconds(10))
                .recordStats()
                .build();
    }
}
```

`maximumSize(10_000)` bounds **entry count**, not fixed bytes. If some values are hundreds of times larger than others, consider `maximumWeight` with a custom `weigher`. Always measure heap footprint and GC under real workloads.

`expireAfterWrite(10s)` sets the max local retention since write per Caffeine policy. Do not treat it as a nanosecond-exact guarantee or end-to-end freshness bound: a snapshot could already be stale when loaded into L1 from a stale L2.

### 13.3. Read Service Following L1 → L2 → Origin

```java
import java.time.Duration;
import java.util.Optional;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.github.benmanes.caffeine.cache.Cache;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductReadService {

    private static final Logger log =
            LoggerFactory.getLogger(ProductReadService.class);

    private static final Duration REDIS_TTL =
            Duration.ofMinutes(5);

    private final Cache<String, ProductView> l1;
    private final StringRedisTemplate redis;
    private final ProductSource source;
    private final ObjectMapper mapper;

    public ProductReadService(
            Cache<String, ProductView> localProductCache,
            StringRedisTemplate redis,
            ProductSource source,
            ObjectMapper mapper) {

        this.l1 = localProductCache;
        this.redis = redis;
        this.source = source;
        this.mapper = mapper;
    }

    public Optional<ProductView> findById(String id) {
        ProductView local = l1.getIfPresent(id);
        if (local != null) {
            return Optional.of(local);
        }

        String key = redisKey(id);

        try {
            String json = redis.opsForValue().get(key);

            if (json != null) {
                ProductView fromRedis =
                        mapper.readValue(json, ProductView.class);

                if (fromRedis == null) {
                    throw new IllegalStateException(
                            "Unexpected null cache payload");
                }

                l1.put(id, fromRedis);
                return Optional.of(fromRedis);
            }
        } catch (DataAccessException redisError) {
            // Redis errors must not be counted as normal cache MISSes.
            log.warn("Redis product cache unavailable", redisError);
        } catch (JsonProcessingException invalidPayload) {
            // Schema/payload error, not a key miss.
            log.warn("Invalid cached product JSON", invalidPayload);
        }

        Optional<ProductView> authoritative = source.findById(id);

        authoritative.ifPresent(product -> {
            try {
                String json = mapper.writeValueAsString(product);
                redis.opsForValue().set(key, json, REDIS_TTL);
            } catch (DataAccessException | JsonProcessingException error) {
                // Cache is an optimization; caller still receives origin data.
                log.warn("Unable to refresh product Redis cache", error);
            }

            l1.put(id, product);
        });

        return authoritative;
    }

    public void evictLocal(String productId) {
        l1.invalidate(productId);
    }

    public String redisKey(String productId) {
        return "cache:product:v1:" + productId;
    }
}
```

Key takeaways from this example:

- L1 hits never touch Redis.
- L1 misses + L2 hits read Redis and populate L1.
- L1/L2 misses query the origin.
- Redis errors are logged separately rather than conflated with cache misses.
- When the origin has no product, this example omits negative caching.
- L1 TTL (10 seconds) is shorter than L2 TTL (5 minutes); these are illustrative values that must match data freshness requirements.
- Updating/invalidating when the origin changes requires a separate path not shown in this read service.
- If many concurrent requests miss the same key, this code can still trigger a cache stampede; production systems need coalescing or loading-cache policies under high load.

**This is cache-aside with eventual consistency**, unsuitable directly for balances, access control, or data requiring the latest write on every read.

## 14. Consistency Challenges with Multi-Instance L1

Suppose product `p-42` updates from version 5 to 6:

```text
DB:     Product version 6
Redis:  Product version 6
App A L1: version 5
App B L1: version 5
App C L1: version 6
```

Updating Redis alone leaves A and B serving stale data until their L1 TTL expires. Fixing L2 does not automatically refresh L1.

Three common strategies:

1. **TTL-only**: accept bounded staleness per TTL and load path.
2. **Explicit invalidation**: emit an event on origin change so instances evict L1 by key.
3. **Version/validation**: carry versions, check or reconcile with the authoritative source where freshness is required.

In practice, combining all three lowers risk.

### 14.1. TTL-Only: Simple Yet Requires a Defined Stale Budget

Example:

```text
L1 TTL = 10 seconds
L2 TTL = 5 minutes
Source updates at T0
```

With TTL alone and no L2 invalidation, an L1 entry populated from a nearly-expired L2 entry can keep serving stale data for another L1 TTL window. Hence, **end-to-end staleness does not equal L1 TTL alone**.

Trace how L2 refreshes, when origin is re-read, and whether requests can reload stale values from L2 after L1 expires.

If the requirement is "never honor revoked permissions," TTL-only is generally insufficient.

### 14.2. Invalidation via Redis Pub/Sub

A fast-reaction optimization:

```text
Product service commits DB update
                 |
                 v
Delete/update Redis L2 per policy
                 |
                 v
PUBLISH product.changed: p-42, version 6
                 |
       +---------+---------+
       |         |         |
       v         v         v
     App A     App B     App C
    evict L1  evict L1  evict L1
```

Spring Data Redis provides `RedisMessageListenerContainer` to subscribe to channels. Each instance receives the notification and calls `l1.invalidate(productId)`.

**However, Redis Pub/Sub does not buffer messages for offline subscribers.** An instance restarting or briefly disconnected misses invalidations. Therefore, Pub/Sub should only serve as a **latency optimization for invalidation**, paired with TTLs or reconciliation/versioning when updates must not be missed.

Never rely on Pub/Sub alone to guarantee immediate session/permission revocation or financial state invalidation.

### 14.3. Example Listener Invalidating L1

```java
import java.nio.charset.StandardCharsets;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class ProductInvalidationListenerConfig {

    @Bean
    MessageListener productInvalidationListener(
            ProductReadService products) {

        return (message, pattern) -> {
            String productId = new String(
                    message.getBody(), StandardCharsets.UTF_8);
            products.evictLocal(productId);
        };
    }

    @Bean
    RedisMessageListenerContainer productInvalidationContainer(
            RedisConnectionFactory connectionFactory,
            MessageListener productInvalidationListener) {

        RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.addMessageListener(
                productInvalidationListener,
                new ChannelTopic("product.cache.invalidate.v1"));
        return container;
    }
}
```

This is an illustrative snippet. In production, version payloads and include scope like tenant, product ID, version, and event ID as needed. Never accept arbitrary identifiers to wipe entire key prefixes unchecked.

### 14.4. Ordering of DB Update, L2, and Notification

Wrong ordering creates stale caches:

```text
T0: Publish invalidation
T1: App A clears L1, immediately reads stale L2
T2: App A reloads version 5 into L1
T3: Database commits version 6
```

Invalidation must generally **follow the origin commit**, and L2 must be updated/evicted appropriately as well. Still, a **dual-write** failure window exists between DB commit and Redis evict/publish.

If missed invalidations are unacceptable, use a transactional outbox or durable event stream with retrying workers, backed by TTL and versioning. Never treat a successful `convertAndSend(...)` call as confirmation that every JVM evicted L1: Redis's returned subscriber count is not a processing ACK.

## 15. Race Condition Between Cache Fill and Invalidation

Even with Pub/Sub, a race can occur:

```text
T0: App A reads version 5 from L2, prepares to put into L1
T1: DB commits version 6
T2: Invalidation reaches App A, evicts L1
T3: App A puts version 5 into L1 after invalidation ran
```

Stale data is **re-inserted** even though invalidation delivered cleanly.

Mitigations depending on requirements:

- Include version in payloads and accept updates only when version is newer.
- Key-scoped coalescing/coordination for read fills.
- Reject putting older versions when a higher local minimum-version watermark was observed.
- Short TTLs bounding worst-case race staleness.
- Query the authoritative source directly when strict consistency is required.
- Avoid caching security-critical mutable state in L1 alone.

A Pub/Sub invalidation system lacking versioning or reconciliation can still serve stale data after races; delivery alone is not enough.

## 16. Negative Caching and Cache Stampedes

When a key is missing in both L1 and L2, concurrent requests can hammer the database:

```text
1,000 requests ask for product p-404
             |
             v
L1 miss across multiple instances
             |
             v
L2 miss
             |
             v
1,000 database reads without coalescing
```

Mitigations:

- **Single-flight / request coalescing** per key within each JVM.
- Bounded Redis lock/lease only when distributed coordination is truly needed.
- **Negative caching** with short TTL for confirmed missing items.
- TTL jitter to avoid simultaneous key expirations.
- Refresh-ahead or stale-while-revalidate when brief staleness is acceptable.
- Concurrency limits and bulkheads protecting the database.

Distinguish clearly:

- **Cache miss**: Redis confirmed no entry exists.
- **Negative cache hit**: Redis holds a marker stating "origin has no record."
- **Redis access error**: failed to query Redis; never assume "record does not exist."

When L1 holds a negative entry, a newly created product can still return "not found" until negative TTL expires unless invalidated. Size negative TTLs to match how quickly new records appear.

## 17. Local Cache and JVM Memory/GC

L1 is not free. With large values, entry-count `maximumSize` alone does not protect the heap.

Example:

```text
10,000 entries
× 8 KiB average payload
≈ 80 MiB payload before Java object and cache metadata overhead
```

This counts payload bytes only; real heap usage can be much higher due to Strings, object graphs, metadata, and fragmentation. Across 30 JVM replicas, duplicated caches consume substantial cluster RAM.

Monitor:

- Heap used and GC pause p99.
- Caffeine `estimatedSize`, evictions, hits/misses, load duration.
- Value size distribution, not just averages.
- Memory during cold start and rapid warm-up.
- Duplicate entries across JVMs.
- L1's effect on autoscaling and Kubernetes memory requests/limits.

If local caching causes JVM OOMs or long GC pauses, HTTP p99 can **degrade** even though Redis GETs dropped.

### 17.1. Never Store Uncontrolled Mutable Entities in L1

If a thread mutates a cached object in place:

```java
ProductView product = cache.getIfPresent(id);
// Avoid mutating shared cached objects if mutable.
```

other requests in the same JVM observe unintended mutations. Prefer immutable DTOs/records, copy-on-write, or dedicated response mapping.

Caffeine provides thread-safe cache structures, but does not make mutable application objects immutable.

## 18. Cache Coherence in Multi-Tier Architectures

A two-tier model spans three sources:

```text
Database = authoritative source
    |
    v
Redis L2 = shared replica, longer TTL
    |
    v
Caffeine L1 = per-instance replica, shorter TTL
```

Consistency goals may include:

- **Eventual consistency with a stale budget**: tolerates staleness up to an agreed bound.
- **Read-your-writes for the updater**: after updating, the caller immediately sees the new version.
- **Monotonic reads**: once version N is observed, never regress to an older version.
- **Strong consistency at decision points**: read directly from the authoritative transactional store.

A 10-second L1 TTL only puts a simple cap on local entries; it does not automatically guarantee all four properties.

### 18.1. Versions Prevent Regressing Backward

Example cached value:

```json
{
  "id": "p-42",
  "priceInCents": 450000,
  "version": 107
}
```

If an instance has seen version 107, reading version 106 from a lagging replica or stale L2 should not overwrite a newer cached version.

You can track a min-observed-version per key or query the database when freshness is vital. Versions must be issued monotonically by an authoritative source—never rely arbitrarily on unsynchronized JVM timestamps as strong versions.

### 18.2. TTL Does Not Replace Event Invalidation

- TTL caps stale exposure when notifications are lost.
- Invalidation shrinks staleness immediately after updates.
- Versioning/validation blocks stale writes after races.
- Outbox/reconciliation recovers lost or out-of-order events.

Each mechanism solves a different piece; combine them based on business SLOs.

## 19. Choosing Cache Strategies by Data Category

| Data Category | Local Cache | Redis Replica Read | Sharding | Key Conditions |
|---|---|---|---|---|
| Infrequently changing versioned feature flags | Usually suitable | Possible | Only if massive data/load | Needs invalidation or refresh policy |
| Product catalog | Good for hot keys | Possible if staleness tolerated | When working set/load is large | TTL, prices/promotions, invalidation |
| Display prices (non-checkout) | Possible | Possible | Load-dependent | Never use stale cached price for final billing |
| Dashboard metrics | Possible | Suitable when lag tolerated | When data is large | Disclose display lag |
| Login sessions | Cautious | Very cautious | Suitable for many sessions | Revocation and security consistency |
| Immediately revocable roles/permissions | Usually avoid L1 alone | Never read stale | Data-dependent | Authoritative source and revocation policy |
| Transaction-deciding balances/inventory | Never use L1 as decision source | Never read stale replica | Can co-locate in slot by aggregate | Atomic command/Lua/DB transaction |
| Idempotency/nonces | Usually no | Never read stale | Can shard by slot | Must remain correct under retries/failover |
| CPU-heavy reconstructible computations | Very suitable if high hit rate | Optional | Size-dependent | Coalescing and bounded memory |

This table offers architectural guidance, not absolute bans. With specialized consistency and invalidation protocols, L1 can still serve sensitive data—proven via concurrency tests and threat modeling, not cache hit rate alone.

## 20. Combining Sharding, Replication, and L1

Large architectures may combine all three:

```text
                       API Clients
                            |
                        Load Balancer
                            |
             +--------------+--------------+
             |              |              |
             v              v              v
           App A          App B          App C
         Caffeine L1    Caffeine L1    Caffeine L1
             |              |              |
             +--------------+--------------+
                            |
                     Spring Data Redis
                            |
                     Lettuce Cluster
                            |
              +-------------+-------------+
              |             |             |
              v             v             v
           Primary 1     Primary 2     Primary 3
              |             |             |
           Replica 1     Replica 2     Replica 3
                            |
                  Miss/fallback to DB
                            |
                            v
                     Authoritative DB
```

This helps when:

- L1 absorbs most hot-read traffic.
- Redis Cluster holds the large working set and distributes remaining load.
- Replicas provide HA and optionally serve lag-tolerant reads.
- The database avoids high normal-state query rates.

In return, failure modes multiply:

- Stale L1 after missed invalidations.
- Redis shard disconnection.
- Replica lag or promotion during failover.
- Redis timeouts triggering database fallback storms.
- Resharding causing redirects and latency spikes.
- Origin update failing to evict L2 or emit invalidation.
- Incompatible cache schemas across app versions.

Multi-tier caching pays off only when **measured benefits outweigh operational and consistency complexity**. For smaller apps, adding three tiers causes more bugs than latency saved.

## 21. Cache Configuration via Spring Cache Abstraction

Spring Cache integrates providers like Redis or Caffeine via `CacheManager`. By default, declaring two cache managers does not automatically create a **two-way synchronized hierarchical L1→L2 cache**.

Example:

```java
@Cacheable(cacheNames = "products", key = "#id")
public ProductView findProduct(String id) {
    return source.findById(id).orElse(null);
}
```

This annotation routes to whichever single cache manager Spring resolves. It does not automatically guarantee:

1. Reading Caffeine first, then Redis.
2. Populating L1 on L2 hits.
3. Evicting L2 and L1 in lockstep.
4. Cross-instance invalidation succeeding.
5. Separating Redis errors from local misses.

For true two-tier caching, build a **composite/tiered cache implementation** with explicit contracts or an explicit cache-aside service like the earlier example.

### 21.1. Never Assume @CacheEvict Clears L1 on All Instances

`@CacheEvict` affects only the configured cache manager/provider inside the calling instance. If that is a local Caffeine cache, it **does not evict caches on other JVMs**.

For fleet-wide invalidation:

- Broadcast post-commit events to all instances.
- Maintain TTL/reconciliation for missed events.
- Include versions to prevent stale-fill races.
- Keep cache names/prefixes uniform across deployments.
- Test with multiple instances, not a single JVM.

### 21.2. Never Use Local Cache for User-Scoped Data Without Full Key Scope

A cache key `product:42` works for a public catalog. If results depend on tenant, locale, price list, or permissions, include all dimensions in the key per contract:

```text
product:{tenant-7}:42:locale=vi-VN:priceList=retail
```

Never use an instance-wide L1 key containing only `id` without tenant/user scope; that risks leaking one user's data to another.

Beyond performance, **cache key correctness is a security boundary**.

## 22. Optimize Before Adding Nodes

Cheaper improvements often come before sharding, replicas, or L1:

### 22.1. Reduce Round Trips

If a request reads five fields from one Redis Hash using five separate `HGET`s, consider `HMGET`, or `HGETALL` when payload is small. For multiple independent commands, pipelining cuts round trips—though it **does not create a transaction**.

Never use `HGETALL` on huge Hashes when only a few fields are needed. One massive-payload command can be slower than well-batched small commands.

### 22.2. Tune Data Structures and Value Sizes

- Avoid serializing bloated object graphs.
- Use compact versioned serialization.
- Do not pack unrelated attributes into one big key.
- Set TTLs matched to data characteristics.
- Remove duplicate data and obsolete namespaces.
- Consider compression only when network savings outweigh encode/decode CPU.

### 22.3. Prevent Cache Stampedes

When concurrent requests miss a hot key, coalesce origin loading per key or bound concurrency. Otherwise, sharding Redis still leaves the database exposed.

### 22.4. Eliminate O(N) Commands

Avoid keyspace-wide scans in request paths, long Lua scripts, and full-collection dumps. Use batched `SCAN` for maintenance and measure impact per node.

### 22.5. Place Redis Close to the Application Within Latency Budgets

If app and Redis sit across regions or AZs, RTT dominates short GET latency. Colocating infrastructure or adding L1 can beat scaling Redis CPU—while still balancing AZ failure domains and cross-AZ network costs rather than optimizing latency blindly.

## 23. Benchmarking Methodology Before Deciding

A sound benchmark compares options under **the same dataset, request flow, and success criteria**.

### 23.1. Representative Workload

Prepare:

- Keys with realistic sizes and popularity skew: hot/warm/cold.
- Realistic read/write mix, e.g., 95/5 or 80/20 from telemetry.
- P50, P95, and P99 payload sizes.
- TTL distribution and simultaneous expiration cohorts.
- Traffic spike scenarios.
- Multiple concurrent app instances, not a single client.
- Production-like TLS, network latency, and topology.
- Failover, cold-start, and resharding scenarios if the design relies on them.

Never run `redis-benchmark GET` over loopback to predict real HTTP p99: Redis-level benchmarks miss Java overhead, serialization, cache misses, and database queries.

### 23.2. Configurations to Compare

| Option | Purpose |
|---|---|
| A. Baseline: current Redis primary | Establish ground truth |
| B. Optimize keys/TTLs/pipelining, same topology | Measure low-cost gains |
| C. Multi-primary Redis Cluster | Measure memory/throughput scale-out |
| D. Primary + read replicas | Measure read scaling and staleness |
| E. Baseline + Caffeine L1 | Measure Redis QPS/latency drop and heap cost |
| F. Cluster + replicas + L1 | Measure full multi-tier system only when needed |

Give every configuration a **warm-up**, sufficient steady-state duration, cold-start measurement, and enough samples for p99. Keep app/DB/traffic setup comparable across runs.

### 23.3. Results to Report

- HTTP p50/p95/p99, throughput, error rate.
- Per-node Redis command QPS, CPU/memory/network.
- Replica lag, redirects, reconnects, timeouts.
- L1 hit rate and heap/GC overhead.
- L2 hit rate **conditional on L1 misses**.
- Database QPS and latency during misses/fallbacks.
- Observed stale duration after updates.
- Failover recovery time.
- Total infrastructure cost and operational complexity.

Never pick an option just because "Redis ops/s doubled" if HTTP p99 failed to improve or stale errors breached bounds.

## 24. Correctness Testing Alongside Performance Benchmarks

Performance testing must verify correctness too:

| Scenario | What to Verify |
|---|---|
| Scale from 1 to 5 JVMs | How L1 hits/heap behave; whether instances diverge |
| Product updated | L1/L2 converge to new version within SLA |
| Instance offline during Pub/Sub invalidation | Upon return, TTL/reconcile still caps staleness |
| Read fill races with invalidation | Stale version is not served past policy |
| Redis primary failover | Command retries are idempotent; session/revocation policies hold |
| Redis replica lag | Freshness-critical reads never hit stale replicas |
| Cluster hot-slot reshard | Does not break multi-key/scripts; latency stays in budget |
| Redis outage | Database does not collapse under fallback storm |
| Caffeine reaches memory cap | Eviction/GC and p99 remain within bounds |
| Two app versions deployed together | Cache schemas/serializers stay compatible |
| Multi-tenant keys | Cache never leaks cross-tenant data |
| Simultaneous L2 TTL expiry | Coalescing/jitter prevents stampedes |
| Big key grows several-fold | Memory/network/serialization stay within capacity |

These checks are vital when adopting L1 or replica reads, because **a system can benchmark faster while returning wrong data under races or failovers**.

## 25. Evaluating Total Cost

Every choice carries costs that do not appear on a latency graph.

### Sharding

Costs:

- More primaries and replicas.
- Operating slot distribution, failover, topology refreshes.
- Migrating from standalone, testing multi-key/scripts.
- Per-shard backup/restore and monitoring.
- Resharding duration, data skew, and hot slots.

Benefits:

- Scales memory/CPU/network/write throughput across keys.
- Expands working set and total capacity.
- Combines with per-shard replicas for resilience.

### Replication

Costs:

- Every replica consumes roughly matching memory capacity.
- Replication traffic, CPU, and network bandwidth.
- Extra failure modes, lag, and failover mechanics.
- Stale-read risk when offloading reads.

Benefits:

- High availability and failover.
- Scales reads for eventually consistent workloads.
- Protects against single-node failures, though not absolute durability.

### L1 Cache

Costs:

- Heap and GC across all JVMs.
- Invalidation, TTL, versioning, cold-start warming.
- Staleness and L1/L2 stampede risks.
- Observability, debugging, and multi-instance testing complexity.

Benefits:

- Eliminates Redis network round trips for hot reads.
- Cuts Redis QPS and connection pressure.
- Dramatically lowers latency at high hit rates.
- Survives brief outages for **stale-tolerant data** (never replaces auth/consistency).

A solid plan quantifies **how each unit of infrastructure cost changes p99, throughput, error rate, and freshness SLAs**, rather than just counting nodes.

## 26. Data Checklist for Technical Decisions

Before deciding, fill in this table:

| Question | Required Data |
|---|---|
| What are peak read/write rates? | Per-node GET/SET/EVAL QPS and HTTP QPS |
| Where is HTTP p99 slow? | Traces: JVM, Redis RTT, DB, serializer |
| What is the real working set? | Used RAM, key count, payload distribution |
| Is data skewed / are there hot keys? | Top keys/slots and per-primary load |
| Does Redis currently have failover? | Replica topology, RTO, replication lag |
| How much staleness is acceptable? | TTL/staleness SLO per data type |
| Expected L1 hit rate? | Per-instance key reuse trace, benchmark |
| Available JVM memory? | Heap/GC headroom per replica |
| How reliable must invalidation be? | Pub/Sub loss tolerance, outbox, version/reconcile |
| Are multi-key/scripts used? | Operation list and slot compatibility |
| Can the DB survive Redis failure? | Fallback QPS budget, bulkheads |
| Acceptable cost and complexity? | Infrastructure budget, on-call, migration effort |

Never fill this table with "usually," "definitely faster," or numbers borrowed from another system's benchmark. Base architectural choices on your own workload metrics.

## 27. Scaling Decision Tree

```text
        Spring Data Redis having issues?
                       |
                       v
             Baseline / traces ready?
                 /           \
                No           Yes
                |             |
                v             v
           Measure first  Primary bottleneck?
                              |
            +-----------------+-----------------+
            |                 |                 |
            v                 v                 v
       One primary       High GET/RTT      Need HA/failover
       out of capacity   to Redis               |
            |                 |                 v
            v                 v            Replication +
    Optimize values/TTL  Data repeated    Sentinel/Cluster
    and commands first   per JVM?               |
            |             /       \             v
            v           Yes        No       Test durability
    Load spread across   |          |       and failover
    many keys?           v          v
       /       \     L1 Caffeine  Optimize RTT,
     Yes        No   + TTL /      commands/pipelining,
      |          |   invalidation or replicas
      v          v       |
   Sharding   Hot key?   v
   Cluster    /    \    Test stale and
             Yes   No   cold-start
             |      |
             v      v
        L1 / cut  Optimize data
        hot load  and workload
             |
             +-------------------------------+
                                             |
                                             v
                             Benchmark p95/p99, cost,
                             failures, consistency
                                             |
                                             v
                             Roll out only if SLO met
```

Branches are not mutually exclusive. A system needing both HA and extra capacity may adopt Redis Cluster with replicas, still rolling out in stages and measuring each change.

## 28. A Low-Risk Rollout Roadmap

### Phase 1: Measure and Optimize Current State

- Collect HTTP/Redis/DB metrics.
- Analyze hot keys, big keys, TTLs, and payloads.
- Fix serialization, cut round trips, bound bursts.
- Define latency budgets, staleness SLOs, and memory headroom.

### Phase 2: Pilot L1 on One Low-Sensitivity Cache

- Pick a versioned, read-heavy catalog/config cache.
- Enable Caffeine with bounded size and short TTL.
- Measure L1 hit/miss, heap/GC, Redis QPS, HTTP p99.
- Test invalidation, miss bursts, deploys, and offline instances.
- Canary roll out before broad application adoption.

### Phase 3: Add Replicas for HA or Read Offload

- Test Sentinel/Cluster failover in a matching environment.
- Measure replica lag at peak load.
- Enable replica reads only on paths with explicit stale budgets.
- Verify read-after-write, revocation, and session behavior.
- Keep invariant checks off stale replicas.

### Phase 4: Shard When One Primary Is No Longer Sufficient

- Inventory multi-key commands, Lua scripts, transactions, and scans.
- Design hash tags and balanced slot distribution.
- Provision Redis Cluster topology with headroom and per-shard replicas.
- Migrate data/traffic systematically, tracking redirects and latency.
- Test resharding, failovers, rollback plans, and partial failures.
- Monitor load skew and hot slots post-rollout.

### Phase 5: Long-Term Operations

- Alert on per-node CPU/memory/eviction/replica lag.
- Alert on falling cache hits and rising DB fallback load.
- Re-verify session/auth consistency across topology changes.
- Adjust TTLs/sizes from metrics rather than guesswork.
- Run periodic failover, cold-start, and load-backlog drills.

## 29. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Adding shards to fix one hot key | Hot key stays in one slot | L1/coalescing/shrink payload or real partitioning |
| Thinking replication splits working-set RAM | Every replica duplicates data | Shard or shrink dataset when RAM-bound |
| Adding replicas yet still reading only from primary | Read throughput never rises | Verify read routing and per-node metrics |
| Reading replicas for permissions/revocation | May return stale grants | Authoritative reads and strict consistency policy |
| Treating Cluster as a global transaction | Multi-slot writes can partially succeed | Co-locate aggregate in one slot or use DB transactions |
| Using `{all}` hash tag on all keys | Hot slot, breaks scalability | Scope hash tags per aggregate |
| Enabling L1 without controlling invalidation | JVMs serve stale data | TTL + events + versioning/reconciliation |
| Assuming Pub/Sub invalidations never drop | Offline instances miss updates | Combine with TTL/outbox/versioning |
| Sizing L1 TTL without considering L2 | End-to-end staleness exceeds L1 TTL | Design freshness across the whole chain |
| Leaving L1 size unbounded | Heap/GC climbs, OOM risk | Bounded cache/weight and metrics |
| Storing mutable entities in L1 | Data races across threads in same JVM | Immutable DTOs/versioning |
| Omitting tenant/locale from cache keys | Wrong data served, security breach | Full key scoping |
| Declaring two Spring Cache managers expecting L1/L2 | Reads/evictions behave unexpectedly | Explicit composite cache or cache-aside service |
| Letting Redis outage slam the DB | Cascading failure | Circuit breakers, bulkheads, rate limits |
| Picking architecture from loopback benchmarks | Ignores network/serializer/app costs | Production-like HTTP p99 tests |
| Skipping failover/reshard tests | Outages during peak node transitions | Controlled chaos/failover drills |
| Retrying non-idempotent writes on timeout | Double increments/decrements | Operation IDs, reconciliation, retry policies |
| Monitoring only blended hit rate | Masks separate L1 and L2 hit/miss behavior | Tier-specific hit/miss and error metrics |
| Ignoring replica and L1 fleet memory | Underestimated infrastructure cost/capacity | Sum memory across nodes and JVM instances |
| Scaling for average throughput | Insufficient headroom for bursts | Size for peaks, tail latency, and headroom |

## 30. Conclusion

Evaluating **sharding, replication, and local caching** in Spring Data Redis is about **locating bottlenecks and choosing the right trade-offs**, not maximizing node counts.

- **Sharding/Redis Cluster** fits when a single primary runs out of memory or throughput across a distributable keyset. It does not fix single hot keys and introduces hash-slot, multi-key, and reshard/failover constraints.
- **Replication** provides HA and optional read scaling, yet each replica duplicates data, adds zero primary write capacity, and introduces **stale reads** due to asynchronous replication.
- **L1 local caching** sharply reduces Redis QPS and latency for hot reads, yet requires bounded heap, hit-rate tracking, and careful multi-JVM invalidation, versioning, TTLs, and race handling.
- **Combining tiers** pays off at scale with clear SLOs, yet adds failure modes and consistency complexity.

Every good decision starts from **p95/p99 latency, Redis CPU/RAM/QPS, per-tier hits/misses, acceptable staleness, replica lag, and operational cost**—followed by representative workload benchmarks, failure/failover tests, and phased rollouts.

**Core rule:** Before adding shards, replicas, or local caches, prove **where the bottleneck sits**, **how much load/latency the change removes**, and **under what conditions data may become stale or inconsistent in return**.

