# High Availability, Scaling, and Monitoring for Redis

In the **CLOUD_PROVIDERS_AZURE** module, we explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID through virtual networks, compute, storage, and data. The goal is to deploy, monitor, secure, and control the cost of an application architecture on Azure. Within the **Caching and Real-time Communication** chapter, this lesson teaches how to design **high-availability (HA) Redis**, choose **scaling** options, and build reliable **monitoring/alerting** to operate Java applications.

Suppose an ordering platform runs 12 replicas of `orders-api` on AKS, queries Azure SQL Database, and uses Redis to cache product details, promotion configs, and non-transactional session data. Redis relieves database query pressure and improves p95 latency. Yet when the Redis primary fails over, some requests hit connection errors; if every API pod immediately falls back to the database without limits, the database can collapse. If the app scales out further to 40 pods and each pod opens too many Redis connections, the blast radius grows. The architecture must therefore answer three questions:

1. **HA:** When a Redis node fails, how do data and service availability behave? What is actually guaranteed?
2. **Scaling:** How do you scale node capacity, add shards, or adapt the application as traffic and memory grow?
3. **Monitoring:** Which signals detect overload, failovers, memory pressure, hot keys, and domino effects onto the database?

After this lesson, you will be able to:

- Distinguish **Azure Managed Redis** from existing **Azure Cache for Redis** deployments rather than applying one product/tier's settings to all.
- Explain **primary/replica**, replication, failover, zone redundancy, persistence, RPO/RTO, and cache data limits.
- Choose between **scale up/scale out**, and understand Redis Cluster, shards, hash slots, hot keys, and resharding risks.
- Design **cache-aside**, TTLs, eviction, fallbacks, request coalescing, and database load caps during Redis disruptions.
- Use **Java Spring Data Redis/Lettuce** with bounded timeout, retry, and circuit breaker policies.
- Monitor Redis with **Azure Monitor, Metrics Explorer, diagnostic settings**, application metrics, and logs/traces.
- Build dashboards, alerts, failover runbooks, load tests, cost controls, and network/TLS security.

## 1. What role does Redis play in the system?

**Redis** is a low-latency in-memory data store commonly used as a cache, rate limiter, session store, and for select real-time workloads. Deployed as **cache-aside**, Redis is not the sole source of truth; durable business records live in the database or designated system of record.

```text
Client
  |
  v
Orders Java API (AKS/App Service)
  |
  +---- GET product:1042 ---> Redis
  |                             |
  |                 Hit <--------+
  |                  |
  |                  v
  |             Return cached response
  |
  +---- Miss / Redis unavailable
                   |
                   v
             Azure SQL Database
                   |
                   v
       Optionally store in Redis with TTL
                   |
                   v
              Return response
```

**Cache hit:** valid data found in Redis. **Cache miss:** key absent, TTL expired, or key evicted. **Cache unavailable:** connection failure, authentication error, timeout, or cluster inability to serve the operation; this is not a miss and requires a separate metric.

### 1.1. What should never live solely in a Redis cache?

| Data | How Redis can help | Recommended source of truth |
|---|---|---|
| Product catalog, read-heavy config | Cache-aside, TTL, invalidation | Database / config service |
| Financial order status | Controlled read projection cache | Transactional database |
| Cart / temporary sessions | Depends on loss tolerance, TTL, replication, persistence | Assess session criticality and recovery strategy |
| Distributed locks | Only after analyzing failure semantics | Database constraints/transactions or suitable coordination |
| Access tokens / secrets | Never cache plaintext casually | Dedicated identity/secrets store with access control |
| Counters / leaderboards | Redis data structures can fit well | Evaluate RPO, durability, and consistency |

For critical data, a Redis outage must never turn into a lost financial write or altered payment logic. **Never treat having a Redis replica as proof that every write is durable.**

### 1.2. How does Redis differ from a relational database?

Redis prioritizes low access latency and specialized data structures (strings, hashes, sorted sets, streams, etc., depending on engine/configuration). While supporting atomic operations/transactions within defined scopes, Redis does not replace ACID transactions, relational constraints, or audit history in Azure SQL/PostgreSQL. Choose technologies by data semantics, not benchmark speed alone.

## 2. Selecting an Azure Redis service by product lifecycle

In Azure documentation, you will encounter both **Azure Managed Redis** and **Azure Cache for Redis** (including earlier deployments/tiers). These are **not** interchangeable names or identical feature sets at all times.

| Criterion | Azure Managed Redis | Existing Azure Cache for Redis |
|---|---|---|
| Direction | Azure-managed Redis service for new deployments per current capabilities | Many legacy systems running Basic/Standard/Premium/Enterprise and available variants |
| HA, clustering, persistence | Depends on configuration, SKU, and service capabilities | Significant differences across tiers |
| Zone redundancy/geo-distribution | Verify supported regions, SKUs, and topologies | Not enabled by default across all instances/tiers |
| Endpoint, port, and authentication | Obtain from the actual resource | May differ between classic Redis and Enterprise offerings |
| Metrics/diagnostics | Inspect actual resource metric names/dimensions | Metric names and categories can differ |
| Long-term planning | Verify active roadmap/support and pricing | Legacy deployments require migration planning against Microsoft's published support milestones |

**Operational rule:** before following any CLI command or guide, confirm the actual **product name, tier/SKU, Redis engine/version, region, topology, authentication, and endpoint**. Never assume `az redis ...` from classic Azure Cache for Redis applies to every Azure Managed Redis instance. When migrating legacy caches, plan methodically—**never** swap production services based on a new product name without testing compatibility, failover, and data handling.

### 2.1. Questions to ask before deploying

1. Is Redis purely a rebuildable cache, or does it hold state requiring zero loss?
2. Must it survive a single node loss, an Availability Zone outage, or an entire region outage?
3. What is the latency SLO? Is read/write traffic evenly distributed?
4. How will the keyspace and dataset size grow? Are there hot keys or big keys?
5. Do application clients support cluster-aware routing, TLS, and credential refresh?
6. Are multi-region reads or active-active writes required? What consistency/conflict semantics are acceptable?
7. What is the budget across instances, networking, logs, compute, replication, and expected downtime?

## 3. Redis high availability levels

**High availability** is the service's ability to continue or recover functionality when a component fails. It does not mean **zero downtime**, **zero data loss**, or **every request always succeeds**.

```text
AZ-1                                   AZ-2
+-------------------+                  +-------------------+
| Redis primary     |--replication---->| Redis replica     |
| Reads/Writes*     |                  | Standby / reads*  |
+-------------------+                  +-------------------+
          |                                       |
          +------ Redis service endpoint ---------+
                                 |
                     Java client with reconnect/refresh

* Replica read support, zone placement, and routing
  depend on the actual product/tier/configuration.
```

### 3.1. Primary and replica

In a typical primary/replica topology:

- **Primary** accepts writes for its dataset/shard.
- **Replica** receives copies of data for failover and/or read scaling if supported by the topology.
- **Replication is typically asynchronous** in Redis; a replica may not yet have the latest writes if the primary dies abruptly.
- A managed failover mechanism promotes an eligible replica to primary per service rules.
- Clients must detect the topology change and reconnect to the new endpoint/role.

If the app uses Redis purely to accelerate reads rebuildable from Azure SQL, losing the last few keys is an acceptable **cache miss**. For data living only in Redis, that same event becomes **business data loss**.

### 3.2. What phases occur during a failover?

```text
T0   Primary handles requests normally
T1   Primary loses connectivity or enters maintenance
T2   Service detects fault, runs election/promotion per topology
T3   Brief window where new connections or writes fail/time out
T4   Eligible replica is promoted; topology/endpoints update
T5   Java clients reconnect / refresh cluster topology
T6   Cache resumes; data may need warm-up
```

Timestamps are illustrative. Actual **failover duration** depends on service, tier, load, topology, failure mode, and client detection/retry speed. Never promise a fixed RTO without checking official SLA/documentation for your SKU and testing in your environment.

### 3.3. Availability Zones

**Zone redundancy** (where supported by service, SKU, and region) reduces the blast radius of losing a single datacenter zone. To achieve zone resilience:

1. Choose a cache configuration that distributes nodes/replicas across multiple zones.
2. Verify the Redis resource is actually deployed across zones, not merely in a multi-zone region.
3. Ensure the **Java app, ingress, VNet, DNS, and database** also survive zone loss.
4. Test failovers and measure latency from actual application zones.

**A zone-redundant Redis paired with an unprotected single-zone Azure SQL instance does not provide end-to-end HA.** Analyze the entire request path.

### 3.4. Replication, persistence, and backups are different

| Capability | What it solves | What it does not solve automatically |
|---|---|---|
| **Replication** | Provides copies for failover and/or reads per topology | May lag latest writes; does not stop accidental deletes from replicating |
| **Zone redundancy** | Mitigates loss of one Availability Zone | Does not replace multi-region disaster recovery |
| **RDB/AOF persistence** (if supported) | Saves snapshots/write logs for recovery per mechanism | Does not guarantee every write is durable or RPO=0 |
| **Backup/export** (if supported) | Restores data to a point in time | Has RPO gap, restore takes time, must test restores |
| **Geo-replication** (if supported) | Replicates data to another region | Rarely zero-loss or automatic disaster failover |
| **Cache-aside + database SoT** | Cache data can be rebuilt | When Redis drops, DB can face heavy fallback pressure |

Depending on the tier, persistence may be unavailable or carry distinct limits. Never promise data durability just because a resource is called "managed".

## 4. RPO, RTO, SLO, and failure domains

**RTO (Recovery Time Objective)** is the target maximum time to restore functionality. **RPO (Recovery Point Objective)** is the maximum acceptable time window of data loss.

Examples for cached data:

| Redis workload | Example RPO | Example RTO | Design |
|---|---|---|---|
| Product cache | Entire cache can be lost because DB is source | Minutes of degraded performance tolerable | Cache-aside, bounded fallback, warm-up |
| Session store | May tolerate losing some sessions or forcing re-login, per product | Fast recovery target | HA topology, TTL, failover UX, evaluate persistence |
| Rate limiter | Counter loss can weaken abuse protection | Needs degraded fallback | Fail-open/fail-closed per risk, edge rate limits |
| Payment ledger | Unsuitable as source of truth in cache | Strict consistency | Use transactional database/ledger; Redis only accelerates reads |

RPO/RTO targets must be confirmed with product owners and tested—never derived from generic SLA sheets. You can achieve **Redis-level HA** and still miss application SLOs due to slow retries, stale connection pools, or unbounded database fallback traffic.

### 4.1. Failure domains to examine

- **Process:** a Redis process crashes.
- **Node/host:** VM/host hardware or host software fails.
- **Zone:** an Availability Zone suffers disruption.
- **Region:** an Azure regional outage occurs.
- **Network/DNS:** Redis is healthy, yet clients cannot reach it.
- **Client/application:** bugs, expired configs/credentials, hot keys, retry storms.
- **Operator:** accidental key deletion, bad policy/scaling changes, flush, botched migration.

No single HA setting covers every failure domain. Different layers need dedicated runbooks and drills.

## 5. Data consistency during failover

A Redis write acknowledged by the primary may not yet have replicated to the replica if the primary fails suddenly. Under asynchronous replication, reads right after failover can miss the most recent write.

```text
Java --> SET order:1042 PENDING --> primary ACK
                                    |
                               replication lag
                                    |
                             primary fails
                                    |
                                 promote replica
                                    |
Java --> GET order:1042 --> may miss or return older value
```

If the key is a **database cache projection**, the app should query the database to rebuild it. If that key was the sole proof of "order paid", the design is dangerously flawed.

### 5.1. Should you use `WAIT` to force replica sync?

Redis offers commands like `WAIT` to wait for a number of replicas to acknowledge a write per engine semantics. However, **replication acknowledgment does not turn Redis into a strongly durable transactional store**; crashes, persistence gaps, and failovers can still lose data. Managed services may also restrict commands or topologies. Never treat `WAIT` as a substitute for database transactions and proper RPO planning.

### 5.2. Cache-aside consistency

When a record changes in Azure SQL:

1. Database transaction commits successfully.
2. Application deletes/invalidates the cache key after commit.
3. Subsequent request misses and reads the fresh record from the database.
4. Key is re-cached with a TTL.

Race conditions remain: an older read can fetch pre-commit DB data and write it back to the cache right after invalidation. Combine short TTLs, versioned keys/values, event-driven invalidation, optimistic version checks, and read-after-write strategies aligned with your consistency requirements.

**Cache invalidation has no automatic cross-SQL+Redis exactly-once guarantee** without a durable workflow. For sensitive or transactionally strict queries, bypass caching on that path.

## 6. Automatic failover does not guarantee automatic client recovery

During a failover, Java clients may encounter:

- Connection resets, EOFs, or closed TLS sockets.
- Command timeouts even as the server begins recovering.
- Cluster `MOVED`/`ASK` redirects when using Redis Cluster.
- Transient errors tied to loading, primary election, or slot migration.
- Cache misses due to unreplicated writes or eviction.

Applications must enforce **bounded timeouts**, refresh connections/topology, and retry only safe operations. A recovered Redis instance does not mean old TCP connections remain valid.

### 6.1. Retrying GET vs retrying writes

| Command / workflow | Retry after timeout? | Why |
|---|---|---|
| `GET product:42` | Usually safe to retry once within deadline, or fall back to DB | Read is idempotent when data is rebuildable |
| `SET key value EX 300` | Safer when value/version/TTL semantics align | Must guard against altering intended expiry or overwriting newer writes |
| `INCR payments:counter` | **Never retry blindly** when outcome is uncertain | Server may have incremented before the ACK was lost |
| `LPUSH queue event` | Never retry blindly if duplicate side effects break logic | Item may already be pushed despite missing ACK |
| Side-effecting Lua script | Depends on explicit idempotency | Script may have executed before client timeout |
| DB fallback on Redis error | Yes, **with concurrency bounds** | Unbounded fallback from every request can crash the DB |

Never equate a Redis command timeout with "the command did not run". For state-mutating commands, a network failure after sending leaves an **uncertain outcome**, much like an unacknowledged commit.

### 6.2. Aligning with application design

Libraries like **Lettuce** provide configurable reconnects and topology refresh. You still need to:

1. Pick a client matching the cache's cluster topology.
2. Set connect/command timeouts inside the request budget.
3. Cap retry counts rather than retrying infinitely in lockstep.
4. Degrade gracefully or fail cleanly instead of pinning threads forever.
5. Monitor latency and error rates after failover.

Never "fix" failover errors by bumping every timeout to 60 seconds: that ties up app threads, builds queues, and destroys p95/p99 latency.

## 7. Scaling: scale up, scale out, and application scaling

**Scaling Redis** has at least three dimensions:

- **Scale up / vertical:** choose higher compute/memory capacity for the existing instance/shards.
- **Scale out / horizontal:** distribute the keyspace and load across more shards, when supported by the service/tier.
- **Application scaling:** scale Java replicas, tune concurrency, caching strategies, and Redis connection usage.

These three dimensions are not interchangeable. A 200 GB cache may need more shards because a single node runs out of memory; conversely, a single hot key taking 70% of traffic will not automatically spread across new shards just by resharding.

### 7.1. When to scale up?

Signals pointing toward scaling up:

- Memory usage stays near capacity even after tuning TTLs/eviction.
- Server CPU/load is high and latency climbs under steady traffic.
- Network/command throughput hits per-node capacity ceilings.
- Workload is hard to shard or cluster-mode constraints limit scaling out.

Pros: simpler topology and client handling. Cons: upper SKU/price ceilings; changing SKUs/capacities can affect availability, rotate nodes, or force client reconnects per service behavior. **Never promise "zero-downtime" scale-up** without checking the exact product/tier mechanics and testing with your client.

### 7.2. When to scale out?

When keyspaces grow large or distributed throughput is needed and the service supports sharding, you can add shards. Keep in mind:

- Clients must understand key distribution when using Redis Cluster client-side routing.
- Resharding moves data and can temporarily elevate latency, CPU, and network traffic.
- Multi-key operations may be constrained by hash slots.
- Hotspots remain if one key or key group still attracts most traffic.
- Failovers can happen per shard, and total node/replica counts grow.

**Scaling out does not mean every command supports multi-shard transactions.** Understand your data patterns and client behavior before enabling clustering.

### 7.3. Decision comparison

| Scenario | Priority action |
|---|---|
| Growing keyspace, rising evictions from low RAM | Review TTL/sizes/eviction, then scale up/out |
| High server load across evenly distributed keys | Evaluate command cost and horizontal cluster capacity |
| One ultra-hot key | App-side local cache, read scaling where supported, key redesign, workload split |
| App scales 5→50 pods, Redis connections spike | Multiplex/reuse connections and cap client counts; don't just upsize cache |
| DB overloaded during Redis miss spikes | Request coalescing, TTL jitter, bounded fallback, cache warming |
| Redis endpoint failover causes Java timeouts | Fix timeouts, reconnects, and topology handling—not just more shards |
| Latency spikes from `KEYS *` or slow Lua | Replace commands/data model, inspect slowlog and load tests |

### 7.4. Capacity planning before scaling

Memory estimation:

\[
Memory_{needed}\approx KeyCount\times AverageEntryFootprint
 + Replication/metadata/fragmentation\ overhead
\]

`AverageEntryFootprint` includes **key/value bytes, data structure overhead, TTL metadata, and allocator effects**—not just plaintext JSON size. Illustrative example:

```text
2 million keys × 1.5 KiB effective footprint ≈ 2.86 GiB
Overhead/reserves/fragmentation increase actual requirement
```

These numbers are estimates, not final sizing. Gather **used memory, resident memory/fragmentation, evictions, key counts, working set, and peak growth** from real Redis/service metrics.

## 8. Redis Cluster and 16,384 hash slots

In the standard **Redis Cluster** model, the keyspace is partitioned into **16,384 hash slots**. Every key maps to a slot assigned to a primary shard. Cluster-aware clients track topology to route commands directly to the node owning the slot.

```text
                          Redis Cluster
   0 ---------------------------------------- 16383
   |                 |                       |
   v                 v                       v
 Shard A           Shard B                 Shard C
 primary+replica   primary+replica         primary+replica
 (slot subset)     (slot subset)           (slot subset)
       ^                 ^                       ^
       +-------- Java cluster-aware client ------+
                    (routing / topology refresh)
```

**Do not assume every Azure Redis SKU uses identical cluster routing.** Some deployments place a managed proxy/routing layer in front so clients connect to a single managed endpoint. Confirm the exact topology/endpoint provided by your resource and match the client accordingly.

### 8.1. `MOVED` and `ASK`

When talking directly to Redis Cluster nodes, clients can receive routing responses:

- **`MOVED`:** the slot belongs to another node; update topology/routing.
- **`ASK`:** temporary redirect during active slot migration.

Compatible Lettuce/Jedis cluster clients handle redirects and refresh topology. If code points a single-node client at a shard without cluster awareness, operations will fail after resharding or failover.

Never crank `MOVED` redirect limits up infinitely to "swallow errors": excessive redirects signal stale topology or ongoing resharding that needs investigation.

### 8.2. Hash tags to co-locate keys in one slot

In Redis Cluster, characters inside curly braces act as a **hash tag** so related keys map to the same slot:

```text
order:{1042}:header
order:{1042}:items
order:{1042}:status
```

This helps when a Lua script or multi-key operation must touch related keys in one slot. Yet **never put the whole system under `{all}`**: every key lands on one slot, destroying horizontal distribution.

### 8.3. Cross-slot operations

Many Redis Cluster multi-key commands, Lua scripts, and transactions require keys to share a hash slot. Running a multi-key command across `order:1042` and `product:7` in different slots fails with `CROSSSLOT` or is rejected.

The fix is rarely "add retries": **revise the data model, group keys by a sensible business partition**, or move critical multi-entity transactions to a database or workflow orchestrator.

### 8.4. Resharding and client testing

When adding or removing shards:

1. Snapshot baseline latency, hit rate, server load, and client errors.
2. Confirm the driver/client supports topology refresh and cluster failovers.
3. Evaluate big keys and hot keys before migrating slots.
4. Execute inside an approved maintenance/change window if needed.
5. Monitor `MOVED/ASK`, timeouts, p95/p99 latency, server load, and bandwidth.
6. Verify application SLOs and absence of duplicate write side effects.
7. Maintain a rollback/migration plan tailored to actual SKU capabilities.

Never alter production cluster topology just because memory spiked for a few minutes without checking TTLs, eviction, and traffic patterns first.

## 9. Hot keys and big keys: when ordinary scaling isn't enough

### 9.1. Hot keys

A key receiving an outsized share of traffic—such as `promotion:global` read by 100,000 clients within seconds—is a **hot key**. Even across many shards, a single key lives in one slot/shard, creating single-shard CPU/network pressure.

Mitigations:

- Add a tiny JVM/local L1 cache with short TTL and deliberate invalidation.
- Split or replicate workload across logical keys/partitions if semantics permit.
- Offload slowly changing public data to CDN/edge caching.
- Smooth bursts with request coalescing / near-caching.
- Inspect per-shard load and key access patterns with supported tools.

**Never duplicate one key arbitrarily across shards** when strong consistency is required: every copy demands an explicit invalidation strategy.

### 9.2. Big keys

A key holding a 50 MiB value or a massive collection can cause:

- High network transfer and serialization latency.
- Commands monopolizing CPU / the Redis event loop.
- Slow resharding and sharp memory pressure.
- Application heap/GC spikes.

Fix: paginate or split entities, enforce value size caps, store large blobs in Blob Storage or a database, and cache only small frequently read slices. Redis is **not** a large-object file store just because RAM is fast.

### 9.3. High-complexity commands

Some commands scale linearly or worse with keyspace or collection size. Never run `KEYS *` in production runtime to list all keys; use `SCAN` with tight bounds and permissions when inventory is necessary. Even `SCAN` adds load and does not yield an atomic snapshot, so run it carefully.

When investigating latency, inspect **command mix and time complexity**, not just aggregate operations/second.

## 10. Memory management: TTL, eviction, and fragmentation

In-memory Redis has finite capacity. As memory nears limits, depending on **maxmemory policy** and service behavior:

- Some keys may be **evicted** to make room for new data.
- Some writes may fail if `noeviction` or other constraints prevent freeing memory.
- Memory fragmentation can push resident memory above logical dataset size.
- Background tasks, replication, persistence, and buffers require overhead per deployment.

### 10.1. TTL is a data contract

```text
product:1042:details        TTL = 300 seconds
promotion:public:rules      TTL = 60 seconds
session:opaque:abc          TTL = per session policy
```

**TTL is the maximum desired lifetime of a cache entry**—it neither guarantees memory is reclaimed at that exact millisecond nor prevents earlier eviction. Design for data potentially being stale within the TTL window or after a write/invalidation race.

### 10.2. Adding jitter to prevent mass simultaneous expiration

If 100,000 keys are populated with an exact 300-second TTL during a rollout, they can expire almost together and trigger a **cache stampede**.

One approach:

```text
effectiveTTL = baseTTL + random(0 .. jitterWindow)
Example: 300s + random 0..60s
```

Jitter suits data that does not require expiration at a hard timestamp. Never add positive jitter to strict security expirations (such as session/token lifetimes) if it extends validity past policy limits.

### 10.3. Eviction policies

Common Redis policy names include:

- `noeviction`: rejects memory-allocating writes once limits are reached.
- `allkeys-lru` / `allkeys-lfu`: evicts keys based on recency or frequency across all keys.
- `volatile-lru` or variants considering only keys with TTLs.
- `allkeys-random` / `volatile-random` in certain configurations.

**Available policies and configuration methods depend on the Redis service, engine/tier, and admin permissions.** Never assume Azure Managed Redis allows running `CONFIG SET maxmemory-policy ...` directly in production. If session data must never be evicted, isolate it onto its own instance or durable store.

### 10.4. Evicted Keys vs Expired Keys

- **Expired Keys:** keys removed because their TTL elapsed.
- **Evicted Keys:** keys removed due to memory pressure and the eviction policy.

Rising Expired Keys can be completely normal for short-TTL caches. Rising Evicted Keys **paired with higher misses and DB load** usually indicates a capacity or workload mismatch. Evictions alone are not enough: correlate with hit rate, working set, and application impact.

### 10.5. Memory fragmentation

The Redis process relies on an allocator and incurs overhead; resident memory can exceed logical used memory. If the **fragmentation ratio** climbs, check allocation patterns, big keys, memory churn, and active defragmentation support for your engine/service. Avoid applying one rigid ratio threshold across all SKUs, since dataset size, OS buffers, and persistence affect the metric.

## 11. Connection management as the Java app scales

Redis uses TCP/TLS connections. As Java replicas scale out, client connection counts can surge:

\[
Connections_{potential}\approx Replicas_{max}\times ConnectionsPerReplica
\]

Illustrative example:

```text
30 Java pods × 20 physical Redis connections/pod = 600 connections
Plus workers, monitoring clients, admin tools, and rollout surge
=> Peak can exceed 600
```

When a client library supports **multiplexing** commands over a shared connection (such as Lettuce in standard patterns), 20 connections per pod may be unnecessary. Conversely, **blocking operations** like `BLPOP`, Pub/Sub subscriptions, or stateful flows may require dedicated connections depending on the client.

### 11.1. Lettuce and Jedis

| Java client | Characteristics | Notes |
|---|---|---|
| **Lettuce** | Popular Java Redis client supporting async/reactive, reconnect, and clustering per config | Multiplexes most operations; do not share stateful commands/transactions improperly |
| **Jedis** | Popular Java Redis client with connection pooling and cluster APIs | Verify version, thread safety, and client lifecycle |
| **Spring Data Redis** | `RedisTemplate`/repository abstractions integrating Lettuce or Jedis | Explicitly configure serializers, TTLs, authentication, and metrics |

**Never assume every Redis connection type is thread-safe**: transactions, Pub/Sub, blocking commands, pipelines, and wrappers carry specific rules. Read your library version's contract and test during failover/resharding.

### 11.2. Connection storms during failover

When Redis recovers, 30 pods may simultaneously:

1. Hit timeouts.
2. Tear down sockets en masse.
3. Reconnect all at once.
4. Retry queued requests.
5. Flood the database with cache misses.

Mitigate by combining **reconnect backoff + jitter**, bounded connection counts, circuit breakers, timeout budgets, and bounded DB fallbacks. Simply adding Redis capacity won't stop an uncontrolled thundering reconnect storm.

### 11.3. Pooling is not a cure-all for latency

One pooled connection blocked on a huge key or slow command can stall queued requests behind it. A single multiplexed connection also has network throughput limits and head-of-line blocking risks. Measure **client command queue time, command latency, in-flight commands, server latency, and bandwidth** to locate the true bottleneck.

## 12. Connecting Java Spring Boot to Redis on Azure

In our hands-on example, we use **Java 17+, Spring Boot, Spring Data Redis, and Lettuce**. Because endpoints, ports, credentials, and cluster modes on Azure Managed Redis can differ from existing Azure Cache for Redis instances, **pull settings from the actual target resource and environment** rather than copying default ports from another product.

### 12.1. Dependencies

A Spring Boot application with managed dependencies can include:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
  </dependency>
  <dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
  </dependency>
</dependencies>
```

Versions are governed by the tested **Spring Boot BOM**. Never force an arbitrary Lettuce version into Spring Data Redis without checking compatibility, TLS, cluster routing, and credential providers.

### 12.2. Configuring TLS and timeouts

Example `application.yml` for a single endpoint or matching gateway topology:

```yaml
spring:
  data:
    redis:
      host: "${REDIS_HOST}"
      port: "${REDIS_PORT}"
      username: "${REDIS_USERNAME:}"
      password: "${REDIS_PASSWORD}"
      ssl:
        enabled: true
      connect-timeout: 1s
      timeout: 500ms

management:
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
```

`REDIS_HOST` is the Azure-issued hostname and `REDIS_PORT` is the actual resource's **TLS** port—never prepend `redis://` to the hostname field. `REDIS_USERNAME` may stay empty **only when the real auth mode permits it**; Redis ACL or Entra token modes may require a specific username. `REDIS_PASSWORD` illustrates an approved **password/access-key auth** mode and **must never be hardcoded**.

**Important:** with a **Microsoft Entra ID access token** for Redis, never treat the token as an immutable `REDIS_PASSWORD` across the JVM lifetime. Tokens expire, so clients/reconnects require **refresh and re-authentication** supported by both the service and client library. Use a tested credential provider/integration or official documentation for your SKU. Never put static tokens in Helm values or Git.

### 12.3. Ports and TLS

Many older **classic Azure Cache for Redis** deployments expose TLS on port **6380**; **never assume 6380 applies to all Azure Managed Redis or Enterprise deployments**. Some resource types use different ports and hostnames. Check resource connection details in the Azure Portal / IaC outputs and firewall rules before deploying.

Keep TLS certificate validation and hostname verification enabled. Never turn on "insecure TLS / trust all certificates" to bypass handshake errors. If private DNS resolves a hostname that mismatches the certificate, fix DNS or client hostname selection rather than disabling server verification.

### 12.4. Redis Cluster in Spring Data Redis

For client-side Redis Cluster routing, configure nodes via `spring.data.redis.cluster.nodes` per your Spring Boot version:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - "${REDIS_NODE_1}"
          - "${REDIS_NODE_2}"
      ssl:
        enabled: true
      timeout: 500ms
```

Node entries typically follow `host:port`—**use this only when the resource actually requires/permits client-aware cluster routing**. Do not apply cluster configuration to an Azure Managed Redis endpoint using a managed proxy if that deployment's docs require standalone config. Authentication and TLS must still match the real resource and topology.

### 12.5. `RedisTemplate` and serialization

Spring Data Redis provides `StringRedisTemplate` for string keys/values and `RedisTemplate<K,V>` for other types. For JSON caches:

- Use explicit key prefixes such as `catalog:v3:product:1042`.
- Use stable, versioned serializers; avoid unrestricted Java native object serialization.
- Omit Java class names or internal package metadata from cache payloads if schemas evolve.
- Separate deserialization errors from cache misses and connection timeouts.
- Bound value sizes; multi-MB JSON blobs make poor cache entries.

A schema-broken Redis JSON entry should not crash the whole API: discard/bypass the key and read the database, while emitting a metric/data-quality alert so an incompatible serializer rollout does not go unnoticed.

## 13. Java cache-aside with safe fallback

The sample below demonstrates `StringRedisTemplate`. It intentionally **never treats Redis as authoritative** and separates cache hits, misses, and cache unavailability.

### 13.1. Example service

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import java.util.Optional;
import java.util.concurrent.ThreadLocalRandom;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;

public final class ProductCacheService {
    private final StringRedisTemplate redis;
    private final ObjectMapper json;
    private final ProductRepository repository;

    public ProductCacheService(
            StringRedisTemplate redis,
            ObjectMapper json,
            ProductRepository repository) {
        this.redis = redis;
        this.json = json;
        this.repository = repository;
    }

    public Optional<ProductDto> findProduct(String productId) {
        String key = "catalog:v3:product:" + productId;

        try {
            String cached = redis.opsForValue().get(key);
            if (cached != null) {
                try {
                    return Optional.of(json.readValue(cached, ProductDto.class));
                } catch (JsonProcessingException corruptCacheValue) {
                    // Cached data is no longer compatible; do not log raw payload.
                    try {
                        redis.delete(key);
                    } catch (DataAccessException ignored) {
                        // Cache delete is best-effort; DB remains the source of truth.
                    }
                }
            }
        } catch (DataAccessException cacheFailure) {
            // Log/metrics: cache_unavailable; do not print secrets or sensitive key values.
        }

        // In production: bounded DB fallback + request coalescing.
        Optional<ProductDto> fromDb = repository.findById(productId);
        fromDb.ifPresent(product -> {
            try {
                long ttlSeconds =
                        300L + ThreadLocalRandom.current().nextLong(0L, 61L);
                redis.opsForValue().set(
                        key,
                        json.writeValueAsString(product),
                        Duration.ofSeconds(ttlSeconds));
            } catch (DataAccessException | JsonProcessingException cacheError) {
                // Do not fail a DB read just because cache population failed.
                // Record redacted metrics/logs.
            }
        });
        return fromDb;
    }
}
```

`ProductRepository` and `ProductDto` are **illustrative** domain types, not built-in Redis library classes. This snippet omits per-record authz, live telemetry, bounded fallback, and request coalescing—which we layer in architecturally next. Never copy this verbatim for strongly consistent financial flows.

### 13.2. Why simple fallback is not enough

If Redis goes down for 2 minutes and 10,000 requests/s jump straight to Azure SQL, **fallback crashes the database** even though the API "handled cache errors". Production therefore needs:

1. **Bounded concurrency:** cap how many requests can fall back to the DB simultaneously.
2. **Circuit breaker:** after consecutive Redis failures, temporarily bypass Redis calls for a cool-down window.
3. **Rate limiting / backpressure:** shed or return 503 for excess traffic beyond DB capacity.
4. **Request coalescing / single-flight:** concurrent requests for one key trigger a single DB load.
5. **Short-lived local cache:** serve slowly changing data while Redis is unavailable.
6. **Timeout budget:** ensure Redis connect/command timeouts do not consume the whole HTTP deadline.
7. **Safe stale-while-revalidate** where business rules permit and maximum staleness is defined.

### 13.3. Per-key single-flight

Suppose 1,000 concurrent requests look up `product:1042` right after its TTL expires. Without coordination, 1,000 DB queries fire. A **single-flight coordinator** inside each JVM coalesces requests by key:

```text
1000 requests for product:1042
          |
          v
Single-flight group inside each JVM
          |
          +-- 1 owner loads from database
          +-- Followers await result with timeout
          |
          v
Redis cache set / return result
```

In-JVM single-flight **does not coalesce requests across 20 separate pods**. For large-scale stampedes, combine jitter, carefully designed distributed locks, or background warming—without making a Redis lock a hard dependency right when Redis is down.

### 13.4. Negative caching

When a product does not exist, do not cache misses with the same long TTL as real products—or skip caching blindly so bots hammer SQL. You can cache a "not found" sentinel with a short TTL to dampen repeated misses, provided:

- You check permissions/tenant scope before caching "not found" so you don't enable enumeration.
- You account for records created immediately afterward.
- Negative cache entries carry clear versions/namespaces and tight TTLs.

### 13.5. Stale data and business boundaries

A product price cached with a 5-minute TTL may show customers an old price briefly after an update. At checkout, the server must **re-validate prices and promo rules from the authoritative source** when creating orders/payments. Caching helps read UX; it is never legal proof of final pricing/settlement.

## 14. Timeouts, retries, and circuit breakers for Redis

Align timeouts with the **end-to-end deadline**. Example request budget:

```text
HTTP request deadline                    2.0s
Redis command timeout                    0.2s
DB fallback (if needed and allowed)      1.2s
Serialization + network response margin  0.6s
```

These are illustrative settings, not universal Azure Redis defaults. If Redis hangs, each request should wait only briefly before falling back or failing rather than pinning threads indefinitely.

### 14.1. Never retry every Redis command blindly

A `GET` can usually retry safely within budget because it has no side effects, whereas `INCR`, `LPUSH`, or a Lua script/transaction already sent might have executed even if the response timed out. Classify **commands and idempotency guarantees** before retrying.

| Scenario | Retry | Preferred behavior |
|---|---|---|
| Brief `GET` timeout | May retry once within deadline | If still failing: bounded DB fallback |
| `SET` same value + TTL | Allowed when semantics permit | Ensure older values cannot overwrite newer ones |
| Non-idempotent `INCR`/counter | Never retry blindly | Use event IDs/idempotency or move accounting to DB |
| Connection refused (bad firewall) | Do not hammer retries | Alert and fix network config |
| Redis failover, client reconnect | Safe retries with jitter/backoff | Monitor status, reconnects, and DB load |
| `MOVED`/`ASK` | Cluster-aware client updates topology | Never replay uncertain mutations |

### 14.2. Circuit breaker separates health from business success

A Redis circuit breaker operates across:

1. **CLOSED:** calls Redis normally while tracking timeouts/failures.
2. **OPEN:** treats Redis as temporarily unavailable; skips cache calls and shifts to bounded fallback if allowed.
3. **HALF_OPEN:** probes with a small number of requests to detect Redis recovery.

Never trip the database circuit breaker just because Redis failed if the DB is healthy—nor let all traffic slam the DB. When the breaker opens and the DB is already saturated, **fail fast** or return bounded stale data (if policy permits).

### 14.3. Retry storms during failover

```text
Redis failover
     |
     +-- 40 pods lose connections simultaneously
     |
     +-- 100 in-flight requests per pod
     |
     +-- Each request retries 5 times immediately
     |
     +-- Tens of thousands of rapid attempts
```

Tame storms with **jitter**, concurrency caps, small retry counts, deadlines, circuit breakers, and isolated critical paths. Avoid stacking uncoordinated retries across multiple layers.

### 14.4. When Redis stays down: degrade gracefully

By criticality:

- **Product cache:** bounded DB reads or time-capped stale product cache.
- **Session store:** may force re-login or show temporary unavailability; never grant fake permissions.
- **Rate limit / security counters:** choose fail-closed vs fail-open from your threat model; never drop all protection silently.
- **Payment state:** always rely on the authoritative database and transactions.

Test degraded modes in advance; never "catch every exception and return empty lists", which misleads users about order status.

## 15. Consistency during updates and cache invalidation

### 15.1. Cache-aside write path

Example updating a product name:

```text
1. BEGIN SQL transaction
2. UPDATE products ... WHERE product_id=1042
3. COMMIT SQL
4. DEL catalog:v3:product:1042
5. Subsequent reads miss -> fetch fresh DB row -> SET TTL
```

**Catch:** if Java crashes after SQL commit but before `DEL`, stale data lingers until TTL expires. If tighter consistency is required, write an outbox invalidation event inside the SQL transaction and run a relay—still handling duplicates, ordering, and races. Never delete the cache before SQL commit assuming that guarantees freshness.

### 15.2. Race between miss and invalidation

```text
Reader A: Redis miss
Reader A: reads old DB row
Writer B: COMMITs new DB row
Writer B: DELs Redis key
Reader A: SETs old value in Redis after DEL
```

This race is possible even when following "write DB first, DEL cache after". Mitigations include short TTLs, **versioned cache entries**, compare-and-set against reliable versions/timestamps, read-after-write cache bypass, or secondary invalidation. Redis supports atomicity only per command/script within slot constraints; **there is no native SQL + Redis distributed transaction**.

### 15.3. Cache versioning

Key prefix `catalog:v3:product:1042` lets a new release deploy without deserializing incompatible v2 payloads. When changing JSON shapes, bump `v3` to `v4` and let old keys age out via TTL. Note that this **temporarily increases memory** while both versions coexist—size for peak dual-version memory during rollouts.

### 15.4. Never use a Redis cache as sole leader election

Commands like `SET key value NX PX ...` support lightweight locking, yet safe distributed locking requires evaluating **ownership tokens, lease renewal, clock assumptions, failover, and fencing tokens**. If a lock expires while a worker is still running, another worker enters the critical section concurrently. Critical transactions belong in database constraints/transactions or a consensus-backed coordination service.

## 16. Azure Monitor: which Redis signals should you track?

A cache can report 99% resource availability while slowing down the API via **hot shards**, **evictions**, **network latency**, or **cache stampedes**. Monitoring should therefore combine **Azure platform metrics**, **Redis engine metrics (where supported)**, **application/client telemetry**, and **backend/database metrics**.

### 16.1. Four observability layers

```text
Azure Redis resource
   |
   +-- Platform metrics: CPU/load, memory, connections, commands...
   |
   +-- Diagnostic settings / logs if provided by service
   |
   +-- Redis engine stats/slowlog within permitted scope
   |
   v
Azure Monitor / Metrics Explorer / alerts / Workbooks
   ^
   |
Java application metrics:
   cache_hit, cache_miss, cache_error, command_latency,
   reconnects, fallback_to_db, p95 request latency
   |
   v
Azure SQL / PostgreSQL:
   CPU, active connections, slow queries, throttling, failover
```

A dashboard showing only Redis CPU/memory misses hit-rate drops that overwhelm the DB. Conversely, high application cache misses alone do not prove Redis is weak—TTLs may just be too short or a deploy may have changed key namespaces.

### 16.2. Core metric groups

| Group | Signals to watch | Interpretation |
|---|---|---|
| **Capacity/CPU** | Server load/CPU, per-shard load if available | Sustained high values + rising latency → capacity/command bottleneck |
| **Memory** | Used memory, memory percentage, resident/fragmentation if available | Working set near limit; risk of eviction/write failures |
| **Connections** | Connected clients, connection failures | Spikes on deploys/failovers, leaks, or connection storms |
| **Throughput** | Operations/sec, commands processed, read/write rates | Compare against baseline and latency |
| **Cache efficiency** | Cache hits, cache misses, hit rate | Correlate with TTL, warm-up, eviction, and DB fallback |
| **Eviction/expiration** | Evicted keys, expired keys | Memory-driven evictions vs normal TTL expirations |
| **Latency** | Server/cache latency, client command p95/p99 | Separate network, queueing, hot keys, and CPU |
| **Errors** | Timeouts, resets, rejected writes, protocol/cluster errors | Classify by layer and command |
| **Availability/replication** | Node/replica state, failover events, replication lag if exposed | Identify role flips and potential data loss |
| **Network** | Bandwidth / egress / ingress | Big keys, serialization overhead, or network saturation |

**Exact metric names, dimensions, units, and aggregations vary by product/SKU.** Legacy Redis resources often expose names like `connectedclients`, `usedmemory`, `cachehits`, or `serverLoad`; never build production alerts on guessed names. Always **list metric definitions from the target resource** and pick verified metrics.

### 16.3. Watch Max and per-shard distribution, not just Average

Suppose a four-shard cluster shows:

```text
Shard A server load: 95%
Shard B server load: 15%
Shard C server load: 20%
Shard D server load: 10%
Cluster average:     35%
```

Looking only at the 35% average hides that Shard A is saturated. When metrics include a **shard/node dimension**, inspect **Max, individual shards, p95/p99 latency**, and hot-key distribution. If shard dimensions are unavailable, use service-supported inspection tools rather than trusting cluster averages blindly.

### 16.4. Cache hit ratio

\[
HitRatio=\frac{Hits}{Hits+Misses}\times 100\%
\]

Example within an observation interval:

```text
Hits   = 900,000
Misses = 100,000
Hit ratio = 90%
```

Compute ratios from **increments within the same time window**, never dividing cumulative counters from mismatched sample intervals. Distinguish:

- **Redis hit ratio** from engine metrics.
- **Application cache hit ratio** per business endpoint.
- **Bypass rate** when circuit breakers skip Redis.

A high hit ratio can still hurt if a hot key sits on one shard; a lower hit ratio can be fine for low-reuse workloads. Anchor SLOs to **latency, DB load, and user experience**, not chasing 100% hit rates blindly.

## 17. Viewing metrics and diagnostic settings on Azure

### 17.1. Azure Portal

Standard workflow for most Azure Redis resources:

1. Open the **exact Redis resource** in the Azure Portal; confirm service/tier, region, capacity, and networking.
2. Navigate to **Monitoring → Metrics** (or equivalent).
3. Select verified **metric names**, time ranges, and aggregations.
4. Split by node/shard dimension when available.
5. Correlate memory, server load, connections, hits/misses, and evictions with application latency.
6. Pin charts to a dashboard or Workbook as supported.
7. Configure **Alerts** and **Diagnostic settings** separately—seeing metrics in the Portal does not mean raw Redis logs are stored in Log Analytics.

### 17.2. Azure CLI – discovering metric definitions

With the exact Resource ID (from Portal or IaC outputs):

```bash
az login
az account show --output table
az account set --subscription "<subscription-id>"

REDIS_RESOURCE_ID="<full-azure-resource-id-of-your-redis-instance>"

az monitor metrics list-definitions \
  --resource "$REDIS_RESOURCE_ID" \
  --output table
```

This discovers **which metrics Azure Monitor actually exposes** for the resource, avoiding mismatched namespaces/names between Azure Managed Redis and Azure Cache for Redis. If the resource uses a custom metric namespace, pass the corresponding CLI flags per current docs.

After picking an **actual returned metric name**:

```bash
METRIC_NAME="<metric-name-from-list-definitions>"

az monitor metrics list \
  --resource "$REDIS_RESOURCE_ID" \
  --metric "$METRIC_NAME" \
  --interval PT1M \
  --output json
```

Never assume every metric supports 1-minute granularity; if the CLI rejects the interval, inspect **supported time grains** in the metric definition and choose a valid one. Values, units, and aggregations are meaningful only when matched to the metric definition.

### 17.3. Azure CLI – checking diagnostic settings

```bash
az monitor diagnostic-settings list \
  --resource "$REDIS_RESOURCE_ID" \
  --output json
```

Supported diagnostic categories depend on the resource. Logs/metrics can route to Log Analytics workspaces, Storage accounts, or Event Hubs per Azure Monitor support. **Never assume Redis command logs or slowlogs land in Log Analytics merely because platform metrics appear.**

When compliance requires audit/connection logs:

- Check whether the resource exposes a matching diagnostic category.
- Define destination, data residency, retention, and query RBAC.
- Avoid overly verbose logging that leaks key names or inflates bills unnecessarily.
- Test with safe synthetic events to verify ingestion end-to-end.

### 17.4. Classic Azure Cache for Redis – inspecting the resource

Only for **classic Azure Cache for Redis** using compatible resource/CLI tooling:

```bash
az redis show \
  --resource-group "<legacy-cache-resource-group>" \
  --name "<legacy-cache-name>" \
  --output json
```

This is **not** a universal command for Azure Managed Redis or Enterprise variants. For Managed Redis, use the Azure Portal or the resource provider/CLI supported by the **current product version**—never assume classic commands can inspect or modify newer resources.

## 18. Logs and KQL: understand the pipeline before querying

**Azure Monitor Metrics** and **Log Analytics logs** are distinct telemetry pipelines. For Redis:

- **Platform metrics** appear in Metrics Explorer and metrics APIs when exposed by the resource.
- **Diagnostic logs** require supported categories and diagnostic settings.
- **Java application logs** flow to Application Insights/Log Analytics via OpenTelemetry, Azure Monitor Agent, or custom pipelines.
- **Redis `INFO`/`SLOWLOG`** are Redis engine commands, not automatically KQL tables.

### 18.1. Explore tables rather than guessing schemas

In a configured Log Analytics workspace:

```kusto
AzureMetrics
| where TimeGenerated > ago(2h)
| take 10
```

This KQL query **only works if Redis metrics are exported to that workspace and the table exists**. Table names vary by routing mode and resource type. If results are empty, verify **diagnostic settings, destination workspace, enabled categories, and ingestion** rather than concluding Redis emits no metrics.

To discover metric names when that schema is populated:

```kusto
AzureMetrics
| where TimeGenerated > ago(24h)
| summarize Samples=count() by MetricName
| top 30 by Samples desc
```

When multiple Azure resources share a workspace, always filter by resource identity/column after checking the real schema—never blend dev Redis, prod Redis, and other services into one chart or alert.

### 18.2. Java Redis client logs

An **illustrative** structured log entry:

```json
{
  "timestamp": "2026-11-20T10:05:31Z",
  "service": "orders-api",
  "cacheOperation": "GET",
  "cacheKeyPrefix": "catalog:v3",
  "result": "TIMEOUT",
  "durationMs": 205,
  "cluster": "orders-prod",
  "fallback": "DATABASE",
  "traceId": "trace-93a5"
}
```

Never log access keys, Entra tokens, raw cached values, personal user IDs, or full keys carrying sensitive identifiers. Under high traffic, use **aggregated metrics** for every request and selectively sample errors instead of writing DEBUG logs on every GET.

### 18.3. Distributed tracing separates Redis from the database

```text
GET /products/1042       610ms
  |
  +-- Redis GET           200ms timeout
  +-- DB SELECT           350ms
  +-- Serialization        20ms
  +-- HTTP response        40ms
```

Looking solely at the 350 ms DB query hides 200 ms wasted waiting on Redis. Instrument **Redis command spans, DB dependency spans, fallback reasons, and request deadlines** using OpenTelemetry/Application Insights—never attaching payloads or credentials to spans.

### 18.4. Redis `SLOWLOG` and `INFO`

Commands like `INFO` and `SLOWLOG GET` help when permitted by the service and privileges:

```text
INFO memory
INFO stats
SLOWLOG GET 20
```

Managed offerings may restrict them or substitute Azure-native telemetry. `SLOWLOG` captures commands exceeding threshold **inside the Redis engine**, excluding network RTT, serialization, and client-side queuing. Command logs can expose key names, so restrict access and scrub sensitive data. **Never run `MONITOR` continuously on production Redis** just to "watch commands"—it adds heavy overhead and leaks payloads.

## 19. Designing a Redis + application + database dashboard

A useful dashboard answers "Is Redis making the app faster and more resilient?", not merely "Is Redis up?".

| Panel | Charts | Decision supported |
|---|---|---|
| **Redis capacity** | Used memory %, fragmentation/reserves, server load | Scale/optimize before memory pressure hits |
| **Redis performance** | Commands/s, p95/p99 latency, per-shard load | Spot hot shards, big keys, client bottlenecks |
| **Cache effectiveness** | Hit/miss ratio, expired/evicted keys | Tune TTLs, working set, invalidation |
| **Redis reliability** | Connected clients, reconnect/timeout rates, failover events | Track networking, HA, client recovery |
| **Application** | HTTP p95, error rate, fallback counts, circuit state | Measure user impact and degraded modes |
| **Database** | CPU, query p95, active connections, throttling | Verify whether Redis outages spill onto SoT |
| **Deployment** | Redis scaling/migrations, AKS rollouts, config changes | Correlate changes with incidents |
| **Cost** | Cache tier/capacity, network, monitoring ingestion | Trim spend without breaking SLOs |

### 19.1. Example incident interpretation

```text
10:00 Redis hit rate      97%
10:03 Redis evicted keys  spiking sharply
10:05 Redis hit rate      62%
10:06 DB CPU              91%
10:07 API HTTP p95        jumps from 120ms to 1900ms
```

A plausible hypothesis is **memory pressure → eviction → cache misses → SQL surge → API latency**. Still verify working set, app logs, traffic spikes, SQL plans, and recent rollouts. **Temporal correlation alone does not prove causation.**

### 19.2. Naming metrics by business outcome

When Redis is an optional cache, define:

- `cache_lookup_total{result=hit|miss|error|bypassed}`.
- `cache_command_duration_seconds` by safe operation name, never raw keys.
- `cache_db_fallback_total{reason=miss|timeout|circuit_open}`.
- `cache_degraded_requests_total`.
- `redis_reconnect_total` per client/instance with bounded cardinality.

**Never use `userId`, `orderId`, full Redis keys, or request IDs as metric labels**: cardinality explodes, inflating bills and crashing telemetry pipelines. Stick to low-cardinality dimensions like app, environment, result, and command type.

## 20. Redis alerting: thresholds, windows, and runbooks

A strong alert specifies **signal → scope → evaluation window → threshold → owner → action**. Never copy one static threshold everywhere—a 1 GB dev cache differs vastly from a multi-shard production cluster.

### 20.1. Priority alerts

| Alert | Suggested tuning condition | Action |
|---|---|---|
| **Memory pressure** | Sustained high used memory with or near evictions | Inspect TTLs, big keys, growth, scaling plan |
| **Abnormal evictions** | Eviction rate exceeds baseline alongside rising misses/DB load | Audit working set and eviction policy |
| **Server load / capacity** | Sustained high server load + rising p95 command latency | Hunt hot keys/slow commands; evaluate scaling |
| **Hot shard** | One shard load/latency far exceeds peers | Analyze slot/key distribution and hotspots |
| **Connection spike** | Connected clients surge after rollout/failover | Check Java client lifecycle and reconnect logic |
| **Cache unavailable** | Java cache error/timeout rate breaches SLO | Open incident; check Redis, network, identity |
| **DB fallback overload** | Cache fallbacks rise alongside DB CPU/connections | Enforce bounded fallback, shed load, protect DB |
| **Hit rate drop** | Hit ratio drops sharply from workload baseline | Check deploys, key versions, TTLs, evictions |
| **Replication/failover** | Redis node/role/health changes or maintenance event | Check RTO, client recovery, data consistency |
| **Cost/capacity** | Projected memory growth nears ceiling or tier spend rises | Forecast scaling and trim cache waste |

Never alert on cache hit ratio when total hits+misses is near zero, as small sample counts swing wildly. Add a **minimum traffic condition**, evaluation window, and cooldown/suppression to reduce noise.

### 20.2. Example alert policy

For a catalog Redis cache:

```text
Signal: cache_error_rate measured by Java
Scope: orders-api production
Condition: > 2% of cache lookup requests over 5 minutes
AND: cache lookups > 1000 over 5 minutes
Severity: P2 if DB fallback is healthy, P1 if API errors/p95 breach SLO
Action group: SRE on-call + incident system
Runbook: "Redis unavailable / fallback overload"
```

These thresholds **illustrate policy structure**, not Azure standards. Derive real thresholds from actual traffic and SLOs.

### 20.3. Alerts should cross-correlate multiple sources

If Redis `server load=90%` yet API p95, hit ratio, and error rates remain normal, it may simply be expected peak load—plan capacity rather than paging an outage. Conversely, if Redis resource metrics look calm while Java client timeouts climb, suspect DNS, TLS, networking, or blocked client event loops. **Cross-correlate** to avoid misdiagnosis.

### 20.4. Alert pipeline and permissions

In Azure Monitor, a metric or log search alert typically requires:

1. Exact target resource/workspace scope.
2. Verified signal (metric name, dimensions, units).
3. Appropriate aggregation and granularity.
4. Threshold and evaluation window.
5. Action group, recipients, severity, and on-call schedule.
6. Environment/owner tags and ticket/runbook links.
7. Validation via simulated test in dev/staging.

Permissions to **read metrics** should not automatically grant permission to **modify alerts or Redis resources**. Separate RBAC and manage critical alerts through IaC and change review.

## 21. Multi-region disaster recovery and geo-replication

**Single-region HA** cannot survive a regional outage. High-criticality systems need a **disaster recovery (DR)** plan covering secondary regions, app routing, data sources, RPO/RTO, and failover/failback procedures.

### 21.1. Common DR patterns

| Pattern | Mechanism | Notes |
|---|---|---|
| **Recreate cache in secondary region** | Provision fresh Redis and populate from DB/source | Fits rebuildable caches; heavy cold-start DB load |
| **Passive geo-replication** (if supported) | Data replicates asynchronously to a secondary cache | Replication lag exists; failover may require manual steps |
| **Active-active geo-distribution** (if supported) | Multiple regions serve reads/writes per compatible data model | Conflict resolution/consistency differs from single-primary Redis; test thoroughly |
| **Dual-region apps + independent caches** | Each region uses its local cache; DB source handles DR separately | No automatic cross-region cache coherence |

Geo-replication and active-active options **are not available across every Azure Redis product/tier**. Verify exact SKUs, region pairings, networking, licensing/features, and data-structure limits before designing around them.

### 21.2. Async replication and RPO

With asynchronous geo-replication, region B can lag behind region A. If region A fails abruptly, writes not yet shipped to B are lost. **Never promise RPO=0** solely because a secondary Redis exists.

Product caches can rebuild; sessions may require re-login; critical business state must rely on a durable database with dedicated DR.

### 21.3. What a DR runbook must include

1. **Trigger:** when to declare regional failover and who approves it.
2. **Data classification:** can the cache be skipped/rebuilt, or does it need restore/replication?
3. **Dependencies:** Azure SQL/Storage/Service Bus, identity, DNS, secrets, networking.
4. **Traffic routing:** Front Door, Traffic Manager, DNS, or equivalent.
5. **Cache connection:** region B's endpoint, port, TLS, and ACL/Entra auth.
6. **Warm-up:** prevent all apps from slamming the DB for every key at once.
7. **Validation:** API p95/error rate, hit rate, DB load, stale data checks.
8. **Failback:** how to restore region A, switch back, and reconcile diverged/lost cache state.

A runbook saying "flip DNS to region B" fails if databases, identities, or backends aren't ready in B or if JVMs keep caching region A's Redis hostname.

### 21.4. Cache consistency in active-active setups

If a product/tier offers active-active Redis via conflict-free replicated data types or similar mechanisms, never assume every command, data type, or Lua/transaction behaves identically to a single-primary Redis. Concurrent writes across regions introduce **conflict resolution and eventual consistency**. Evaluate workload fit carefully; financial invariants still require a purpose-built transactional store.

## 22. Security: TLS, private connectivity, and authentication

Redis is fast, which is no excuse for exposing it over open networks with weak credentials. On Azure, design **networking, identity, secret lifecycles, and data-plane permissions**.

### 22.1. Private networking

Conceptual layout:

```text
AKS / App Service / Container Apps
              |
              | VNet integration / node egress
              v
        VNet / private DNS
              |
        NSG / Firewall / route
              |
              v
       Azure Redis endpoint
       (private access if SKU supports)
```

Private endpoint / VNet injection options and support **differ across Managed Redis and Cache for Redis tiers**. Never toggle production public access blindly from a guide written for another SKU; verify all clients, diagnostics, and migration tools still connect after changes.

### 22.2. Mandatory TLS by policy

- Always use TLS when sending credentials and cache payloads across networks.
- Validate server certificate chains and hostnames.
- Never allow plaintext or disable SSL to bypass DNS bugs.
- Plan certificate/CA rotation inside JVM containers.
- Test from the **actual runtime**, not just a developer laptop.

### 22.3. Microsoft Entra ID and ACLs/access keys

Some Azure Redis offerings support **Microsoft Entra authentication** with data access policies/Redis ACLs; others still use **access keys/passwords**. Support depends on service, tier, region, and version:

1. Prefer identity-based authentication when supported by workload and Redis resource.
2. Identify the actual **runtime principal** (managed identity, workload identity, service principal).
3. Grant exact **Redis data-plane permissions**—never assume Azure RBAC Contributor grants Redis command access.
4. Because Entra tokens expire, implement **refresh/re-auth** before expiry and on reconnect.
5. If access keys remain in use, store in a secrets manager, rotate, audit, and never commit to repos.
6. Restrict Redis commands via ACLs where supported, keeping flush/config/admin commands away from web apps.

### 22.4. Key naming and PII

Avoid embedding raw emails, phone numbers, tokens, or sensitive user IDs in Redis keys unnecessarily. Key names surface in logs, diagnostics, sampled metrics, and debuggers. Use opaque IDs with versioned prefixes and align retention/TTLs with data classification.

### 22.5. Avoiding dangerous commands in production

`FLUSHALL`, `FLUSHDB`, sensitive `CONFIG SET` calls, `KEYS *`, and `MONITOR` can wipe data, stall traffic, or leak secrets. Managed services often block/restrict several of these; even where permitted, require change review and staging tests first. **Never run `FLUSHALL` to "fix" cache performance.**

## 23. Cost and capacity planning

Azure Redis costs extend well beyond raw cache size:

| Item | Cost drivers | Control levers |
|---|---|---|
| **Redis tier/instance** | Capacity, SKU, region, node/shard count, uptime | Size to working set and SLO, not user count guesses |
| **HA replication** | Replica/zone counts per topology | Match actual RTO/RPO requirements |
| **Geo-replication / DR** | Secondary region, cross-region traffic, sync overhead | Enable only when business RTO/RPO requires it |
| **Networking** | Private endpoints, Firewall/NAT, cross-region egress | Co-locate with compute, trim payload traffic |
| **Monitoring** | Diagnostic log volume, retention, alerts, App Insights | Collect purposeful telemetry; sample verbose logs |
| **Application / DB** | Cache misses driving SQL compute/IOPS | Optimize hit ratio, TTLs, fallback, warm-up |
| **Migration / scaling** | Resharding/dual-runs, load tests, temporary peak capacity | Plan maintenance and rollback windows |

**Never rely on fixed price tables**, as products, tiers, regions, and rates change. Use the Azure Pricing Calculator, Cost Management, and real usage telemetry.

### 23.1. Expand RAM or trim cached data?

If used memory hits 90% and evictions rise:

1. Identify which keys truly need caching.
2. Inspect payload sizes, overly long TTLs, and stale keys from older schema versions.
3. Measure active working set; stop caching rarely read objects.
4. Check for big keys, bloated serialization, and memory fragmentation.
5. After optimizing, forecast growth and evaluate scaling.

Never slash TTLs near zero just to save RAM: extra misses can push far higher costs onto Azure SQL and hurt user latency.

### 23.2. Estimating scaling and rollout impacts

Suppose Redis hit rate drops from 96% to 80% on 10 million reads/day:

```text
Before: misses ≈   400,000/day
After:  misses ≈ 2,000,000/day
Delta:  +1,600,000 DB fallback reads/day
```

This simple model assumes one DB read per miss; request coalescing and local caches can lower it, while multi-query fetches raise it. When sizing Redis capacity, factor in **the cost of post-miss database traffic**.

### 23.3. Cost-aware monitoring

Keep aggregated metrics (hits/errors/memory/latency) to catch issues early without logging every key-value per request. Match retention and diagnostic categories to real audit/debugging needs. On dimensional metrics, avoid high-cardinality labels like raw keys or transaction IDs that inflate telemetry bills and overload collectors.

## 24. Runbook: when the Redis primary fails over

### 24.1. Warning signs

- Redis platform health/failover events or node role changes reported by the service.
- Client errors: rising connection resets, timeouts, or cluster redirects.
- Java circuit breakers tripping OPEN and cache fallback traffic climbing.
- Rising DB read traffic and latency.
- Temporary Redis hit-rate dip as cold keys or unsynced writes miss.

**Never conclude primary failover from a single timeout alone**: network blips, credentials, client threads, or GC pauses can look identical.

### 24.2. Response steps

1. **Confirm incident scope:** one app replica, one shard, or the entire Redis resource?
2. **Check Azure Redis resource health:** is maintenance, failover, or scaling underway?
3. **Check Java metrics:** Redis timeouts/reconnects, p95, circuit state, fallback rate.
4. **Check DB:** are SQL CPU, active connections, and query latency surging from misses?
5. **Throttle load:** enforce bounded fallback, request coalescing, and rate limits as needed.
6. **Do not flush or restart all pods at once:** avoid simultaneous reconnects and cold-cache storms.
7. **Wait/reconnect cleanly:** let clients refresh topology and retry safe operations only.
8. **Verify data:** cache may miss or be stale, yet critical transactions must read the authoritative DB.
9. **Monitor recovery:** cache errors drop, hit ratio rebounds, DB returns to baseline, API SLO recovers.
10. **Postmortem:** document timeline, actual RTO, potential RPO/lost keys, alert fidelity, and runbook updates.

### 24.3. What not to do

- Never bump connection timeouts to minutes across the whole API.
- Never blindly retry `INCR` or list pushes when ACKs may have been lost.
- Never run `FLUSHALL` to "resync the cache".
- Never force all requests onto an already saturated DB.
- Never flip DNS/primary to another region without DR approval and data reconciliation.
- Never disable TLS or Redis authentication to mask connectivity errors.

### 24.4. Criteria for full recovery

Recovery means more than the Redis resource showing healthy. Confirm:

```text
Redis command error/timeout rates back to baseline
Redis read/write latency within SLO
Java connections/reconnects stable
Cache hit ratio recovering with working set
DB CPU/connections subsiding after fallback burst
API p95/p99 and error rates back within SLO
No duplicate side effects on critical Redis counters/flows
```

If Redis shows healthy yet Java p95 stays elevated, investigate cache warm-up, thread pools, DNS, client topology, and database backpressure.

## 25. Runbook: Redis memory pressure and eviction storms

### 25.1. Scenario

A catalog cache sees rising evictions, climbing DB read load, and worsening API p95. Redis server load/CPU may still look low, so CPU alone hides the problem.

### 25.2. Steps

1. Verify **used memory**, eviction rate, expired keys, and hit ratio over the same window.
2. Correlate key counts/working set with recent deployments, serializer/version bumps, or batch jobs.
3. Inspect memory fragmentation and largest values/collections with approved tools.
4. Audit TTL distribution: are there TTL-less keys that do not need permanent retention?
5. Check whether a new key prefix doubled cached memory across schema versions.
6. Throttle producers creating low-value keys; fix data models, TTLs, or serialization.
7. Evaluate scaling up/out based on the optimized working set—never scale blindly.
8. Watch DB fallback and API latency after changes.
9. Set predictive capacity alerts rather than waiting until 100% exhaustion.

### 25.3. Distinguishing eviction from expiration

If **Expired Keys** rise naturally with TTLs while hit ratio stays steady, that is normal operation. If **Evicted Keys** surge alongside high used memory, rising misses, and DB saturation, capacity or policy is mismatched. Read the **combined signal set**, never a single counter in isolation.

### 25.4. Never change `maxmemory-policy` casually

Switching from `noeviction` to `allkeys-lru` can silently drop keys an app expects to remain present. Switching the other way immediately turns full memory into write failures. Confirm data classification, backup/persistence, and app behavior before changing eviction policies.

## 26. Runbook: Redis healthy but Java clients time out

### 26.1. Asking the right questions

Redis metrics look healthy, yet Java `RedisCommandTimeoutException` rates climb. Likely causes:

- AKS node egress, NSGs/firewalls, NAT/SNAT exhaustion, or DNS resolution.
- TLS handshakes, certificates, truststores, or expired credentials.
- Blocked client event loops, CPU/GC pauses, or excessive in-flight commands.
- Connection pool exhaustion / client-side queueing.
- Big-key responses, slow serializers, or blocking commands.
- Stale topology after resharding or a non-cluster-aware client.
- High cross-region network RTT between app and Redis.

### 26.2. Diagnostic sequence

1. **Scope:** one pod, one node, all pods, or an entire region?
2. **Client:** Lettuce/Spring Data Redis versions, thread/GC metrics, command timeout, reconnect counts.
3. **Connectivity:** DNS, endpoint/port, TLS, and ACL/Entra token refresh from the actual runtime.
4. **Network:** routes, firewalls/private endpoints, packet loss, and cross-region paths.
5. **Redis:** server load/per-shard latency, connections, command mix, slowlog if permitted.
6. **App:** serialization/deserialization duration, payload sizes, and in-flight command counts.
7. **Topology:** Redis Cluster slot mappings, redirects, recent resharding or failovers?
8. **Controlled probe:** one lab-key GET/SET along the valid path; avoid destructive commands.
9. **Fix the exact root cause:** code/client, credentials, routing, hot keys, or capacity.
10. **Verify SLO:** Java p95 timeouts drop and DB fallback stays healthy.

### 26.3. Testing with `redis-cli`

In a lab environment or authorized jump host:

```bash
REDIS_HOST="<redis-host-from-azure-resource>"
REDIS_PORT="<tls-port-from-azure-resource>"

# Use product-appropriate secure auth: Entra token / Redis ACL / secret store.
# Avoid passing passwords directly on the command line or in shell history.
redis-cli --tls -h "$REDIS_HOST" -p "$REDIS_PORT" PING
```

This is a **basic connectivity check** that may return an auth error if credentials are required (expected). Follow your security team's credential workflow; Entra tokens/ACLs may require a username/secret and a compatible `redis-cli` version.

A passing `PING` proves only **one** connection and command succeeded at that moment—not that all shards, commands, permissions, failovers, or application SLOs are healthy.

## 27. Testing HA and scaling before production

Never enable HA and declare a system safe without testing **client recovery and DB fallback**. Run fault-injection and failover drills only in authorized environments—never disrupt shared production resources.

### 27.1. Test matrix

| Test | Controlled procedure | Expected outcome |
|---|---|---|
| **Cache hit/miss** | Query present and absent keys in lab Redis | App accurately separates hits and misses |
| **TTL expiry** | Let key expire | Reads DB cleanly without data corruption |
| **Redis network outage** | Block connectivity from one test Java pod | Bounded timeouts, bounded fallback |
| **Primary failover** | Use service-supported, approved failover test | Clients reconnect; SLO degradation stays within target |
| **Zone failure scenario** | Simulate per environment capabilities | Topology survives zone loss as designed |
| **Cold cache** | Provision an empty cache | DB survives without collapsing from stampedes |
| **Eviction pressure** | Load dataset exceeding working set controllably | Policy behaves predictably; alerts fire |
| **Cluster resharding** | Scale shards in dev/staging | Cluster client refreshes topology without business loss |
| **Hot key** | Concentrate requests on one key | Detect shard/latency hotspot |
| **Connection storm** | Start many app replicas simultaneously | Stays inside client/Redis/network limits |
| **Credential rotation** | Execute policy rotation test | New/reconnecting clients pick up valid credentials |
| **Entra token expiration** | Run app past token expiry cycles | Token refresh prevents extended Redis disconnects |
| **Region DR** | Shift traffic to test region | App, DB, Redis endpoint, and auth all work |
| **Chaos duplicate outcome** | Drop ACK on a stateful Redis command in test | App prevents unintended duplicate side effects |

### 27.2. What should load tests measure?

Test across varying dimensions:

```text
App replicas:     2 -> 8 -> 20
Cache hit ratio:  98% -> 80% -> 40%
Key size:         small -> medium -> large
Traffic pattern:  uniform -> hotspot
Redis topology:   baseline -> scaled
```

Track **throughput, client p50/p95/p99, Redis server load, per-shard distribution, used memory, evictions, connections, DB CPU, SQL query p95, cache fallback, and error rate**.

Never optimize solely for commands/second. If Redis throughput rises while HTTP p99 degrades and SQL bills climb, the design misses the system goal.

### 27.3. Measuring RTO from the user's perspective

Redis resource RTO and **application SLO recovery time** can diverge. A primary may promote quickly while apps still need time to reconnect, refresh DNS, warm the cache, and drain DB pressure. In drills, record:

- Timestamp Redis started failing.
- Timestamp the Redis endpoint passed health commands.
- Timestamp Java cache errors returned to baseline.
- Timestamp API error rate and p95 returned to SLO.
- Duration of stale/missing cache and whether any business side effects occurred.

### 27.4. Testing without exposing production secrets

Use dedicated lab Redis resources, synthetic keys, and test secrets—never copy raw session tokens or customer records into labs. If realistic data is needed where privacy applies, enforce masking/anonymization and strict access controls.

## 28. Real-world scenario: ordering platform Redis cache

### 28.1. Business requirements

System architecture:

```text
Azure Front Door / API gateway
          |
          v
AKS orders-api (12 pods, max 30)
          |
          +-- L1 cache: slowly changing read data, short in-JVM TTL
          |
          +-- Azure Redis: catalog and promotion cache
          |       |
          |       +-- HA primary/replica per SKU
          |       +-- TLS, private connectivity
          |       +-- Metrics/alerts
          |
          +-- Azure SQL: product/order source of truth
          |
          +-- Application Insights / Azure Monitor
```

Goals:

- Low-latency product reads under normal load.
- Zero lost orders or double charges during Redis failover.
- Bounded fallback protecting Azure SQL while the cache is unavailable.
- Triple traffic spikes do not overload a single hot key/shard.
- SREs have dashboards, alerts, runbooks, and verified failover tests.
- Cache sized within budget and appropriate tier.

### 28.2. Data classification

| Data | Source of truth | Cache design | During failover |
|---|---|---|---|
| Product details | Azure SQL | Redis TTL 5 min + jitter | Bounded DB fallback; brief local stale allowed |
| Promotion rules | Config/SQL | Short Redis TTL, versioned | Verify final eligibility against authoritative source |
| Order payment status | Azure SQL | Display-only cache projection | Never confirm payment from cache |
| Idempotency records | Transactional DB | Never use Redis as SoT | Never issue duplicate charges |
| Sessions | Depends on auth requirements | Dedicated TTL/security policy | Can force re-login if session loss is acceptable |

### 28.3. Capacity calculation

Assumptions:

```text
1,500,000 product entries
Average effective footprint ~2 KiB/key
Raw estimate ~2.86 GiB before other overhead
Peak traffic ~50,000 cache lookups/s
Hot promotion key may draw 35% of requests
```

Evaluate on two axes:

1. **Memory:** working set, TTL, replication/persistence overhead, fragmentation, plus headroom for deploys and resharding.
2. **Throughput:** heavy requests hitting one hot key can saturate a shard even while total memory looks low.

Hot promotion key mitigation: 2–5s JVM L1 cache if business permits, request coalescing, event-driven invalidation on rule changes, and monitoring load on the owning shard.

### 28.4. When a failover happens

Hypothetical timeline:

```text
14:00:00 Redis normal, hit ratio 96%
14:05:00 Redis primary failover begins
14:05:02 Java cache timeouts increase
14:05:04 Circuit breaker OPEN; bounded DB fallback
14:05:10 SQL CPU rises yet stays below saturation threshold
14:05:20 Redis clients reconnect, cache requests recover
14:06:00 Redis hit ratio climbs via warm-up
14:07:00 HTTP p95 returns to baseline
```

This is an **illustrative** timeline, not an Azure Redis SLA or measurement. If SQL CPU hits 100% during fallback, the runbook must tighten concurrency/rate limits and consider permitted stale serving rather than just waiting for Redis.

### 28.5. Acceptance criteria

- App verifies TLS and Redis permissions from the real runtime.
- Zero secrets in keys, values, logs, or metric labels.
- HA/failover is never reported as zero data loss under async replication.
- Redis command errors drop post-recovery; API p95 meets SLO.
- SQL survives cache cold starts and fallbacks.
- Product cache enforces TTLs, jitter, serialization versions, and invalidation.
- Hot keys and per-shard imbalance have alerts or monitoring visibility.
- DR has a runbook separate from intra-region HA.
- Baseline established for Redis, SQL fallback, networking, and monitoring costs.

## 29. Controlled Redis migrations and upgrades

Upgrading engine versions, changing tiers, or migrating from an existing Azure Cache for Redis to Azure Managed Redis is never just swapping a hostname.

### 29.1. Compatibility checklist

| Component | What to verify |
|---|---|
| **Redis engine/modules** | Commands, data structures, Lua scripts, features/limits |
| **Cluster mode** | Proxy vs direct cluster, hash slots, redirect behavior, multi-key ops |
| **Authentication** | Access keys/ACLs vs Entra, client usernames, token refresh |
| **TLS/networking** | Endpoint, port, cert chains, private DNS/endpoint support |
| **HA/DR** | Replica counts, zones, persistence, geo-replication, RPO/RTO |
| **Memory policy** | Maxmemory, eviction semantics, cache warming |
| **Java client** | Lettuce/Jedis/Spring Data Redis versions, topology refresh |
| **Monitoring** | Metric names/categories/tables, dashboard/alert mappings |
| **Pricing** | New tier instance cost, temporary dual-run/network spend |

### 29.2. Step-by-step migration

1. **Inventory:** document Redis product/tier/version, keys, TTLs, value schemas, command usage, and constraints.
2. **Classification:** which data can be lost/rebuilt? Are there sessions, counters, or workflow states?
3. **Compatibility tests:** Java clients, SSL, ACLs, clustering, scripts/multi-key semantics.
4. **Target deployment:** provision Redis in the right region/network/HA with monitoring.
5. **Data transfer strategy:** pick export/import, replication, or cache warming supported by **both source and target**—never assume every pair supports online migration.
6. **Canary:** shift low-risk traffic and compare hit ratios, latency, stale data, and failovers.
7. **Gradual cutover:** use config/feature flags while watching errors and DB load.
8. **Rollback:** preserve conditions to revert cleanly and handle keys written post-cutover.
9. **Decommission:** delete the old cache only after confirming no clients or required keys remain.

**Never run `FLUSHALL` on the source before cutover.** If data is more than rebuildable cache entries, protect and migrate it according to durability needs.

### 29.3. Risks of dual-write

An app issuing `SET` to two Redis deployments can succeed on A and fail on B; there is no native atomic transaction across two deployments. At cutover, state diverges. For **cache-aside**, it is usually safer to warm/populate the target from the authoritative DB; sessions and counters need tailored migration strategies and testing.

### 29.4. Check support lifecycles and roadmaps

Azure Redis plans and tier capabilities evolve. Before choosing a new service or renewing a legacy architecture, verify **product lifecycle notices, support/migration deadlines, feature parity, and regional availability** from the provider. Never invent retirement dates or feature claims from an old code sample.

## 30. Hands-on exercises

### Exercise A – HA and consistency

A product cache uses primary + replica with asynchronous replication. Java runs `SET product:1042`, then the primary fails before the replica receives the write.

**Task:** explain why a post-failover `GET` can miss; define suitable RPOs for a product cache, session store, and payment ledger; explain why "having a replica" does not equal zero data loss.

**Solution guide:** product cache reloads from SQL, sessions need UX fallback or suitable persistence/DR, and a payment ledger must never treat Redis as source of truth.

### Exercise B – Scale out and Redis Cluster

A three-shard cluster distributes keys evenly. An app needs an atomic operation across `order:1042:header` and `order:1042:items` but hits `CROSSSLOT`.

**Task:** redesign the keys with hash tags, explain why `{all}` must not be used globally, and describe testing when scaling to six shards.

**Solution guide:** group `order:{1042}:header` and `order:{1042}:items` into the same slot while partitioning each order separately to prevent hotspots. Test client topology refresh and redirects.

### Exercise C – Cache stampede

Key `promotion:global` receives 40,000 reads/s with a 300s TTL. After a rollout, it expires and misses en masse; Azure SQL absorbs 40,000 extra queries/s.

**Task:** propose TTL jitter, single-flight, L1 cache, bounded DB fallback, and telemetry. Explain what a single ultra-hot key needs beyond cross-key jitter.

**Solution guide:** jitter across multiple keys does not solve **one hot key**. Pair coalescing, near-caching/background refresh, and capped fallbacks.

### Exercise D – Azure Monitor dashboard

You have an Azure Redis resource but do not know its exact metric names or dimensions. Write a procedure to:

1. List metric definitions via Azure CLI/Portal.
2. Select used memory, server load, connections, evictions, hits/misses, and latency **if supported**.
3. Use per-shard dimensions so averages don't mask a hot shard.
4. Correlate with Java cache errors/p95 and Azure SQL CPU.
5. Configure an alert with evaluation window, owner, and runbook.

**Solution guide:** run `az monitor metrics list-definitions` against the exact Resource ID, checking aggregations, time grains, and names before creating alerts.

### Exercise E – Redis timeouts on AKS

Redis reports healthy, yet pods on node A repeatedly time out after a network policy change.

**Task:** distinguish Redis server load from network/DNS/TLS/client GC issues, test connectivity from the **actual pod**, and explain why upsizing Redis will not help.

**Solution guide:** inspect pod/node scope, DNS, egress, private endpoints, firewalls/NSGs, TLS, and client metrics. Never disable TLS or open public access just to "test".

### Exercise F – Migrating from an existing cache

A legacy app uses access keys, a specific TLS port, a single-node client, and multi-key Lua scripts. The organization plans to adopt Azure Managed Redis.

**Task:** build a compatibility plan covering endpoints, auth, versions, clustering, Lua/multi-key limits, replication/persistence, metrics, and migration/rollback.

**Solution guide:** pick a target SKU matching real features, test Java clients, evaluate password→Entra migration if supported, size for cold-cache load, and never assume dual-write is atomic.

### Exercise G – Failover game day

In staging, run an approved failover supported by the service. Measure:

- Duration of Redis endpoint interruption/recovery.
- Java command timeouts/reconnects and circuit breaker state.
- DB fallback rate and CPU.
- API p95/p99 and error rates.
- Cache hit ratio after warm-up.
- Gap between HA resource recovery and end-to-end application RTO.

**Solution guide:** build a UTC incident timeline, check whether alerts fired early without duplicate side effects, and propose tuning for timeouts, backoff, and DB bulkheads.

### Exercise H – Analyzing memory pressure

A Redis instance hits 92% used memory, evictions climb, and hit ratio falls from 94% to 75%.

**Task:** determine whether big keys, overly long TTLs, dual-schema payloads, fragmentation, or traffic shifts caused it; choose between data model optimization and scaling up/out with acceptance criteria.

**Solution guide:** measure working set and entry sizes first, separate evictions from expirations, and decide on scaling from load tests and total Redis + Azure SQL fallback cost.

## 31. Self-check questions

**1. Does Redis HA guarantee zero lost writes when the primary fails?** No. Replication can be asynchronous; RPO depends on topology, persistence, and failover conditions.

**2. How does a Redis replica differ from a backup?** A replica is a live copy for replication/failover; a backup is a stored point-in-time snapshot for restoration. Accidental deletes also replicate to replicas.

**3. Does zone redundancy protect against losing an entire Azure region?** No. Multi-region disaster recovery is required separately.

**4. When Redis serves solely as a product cache, where should the source of truth live?** In a designated database or authoritative system such as Azure SQL.

**5. What errors can Java see during a Redis primary failover?** Connection resets, command timeouts, reconnects, or cluster redirects depending on topology and client.

**6. Why never blindly retry `INCR` after a timeout?** The server may have incremented the counter before the ACK was lost; retrying can double-increment.

**7. How do scale up and scale out differ?** Scale up increases node/instance capacity; scale out partitions data and load across multiple shards where supported.

**8. How many hash slots does Redis Cluster have?** 16,384.

**9. What do `MOVED`/`ASK` typically indicate?** Cluster routing or slot migration; cluster-aware clients must refresh topology.

**10. When is a `{orderId}` hash tag useful?** When multi-key operations require keys for one order to reside in the same slot.

**11. Why doesn't adding shards cool down a single hot key?** One key still maps to one slot/shard; its traffic does not split automatically.

**12. What harm do big keys cause?** Elevated latency, network saturation, CPU/serialization spikes, slow resharding, and memory pressure.

**13. How do Evicted Keys differ from Expired Keys?** Eviction is driven by memory pressure/policy; expiration is driven by TTL.

**14. Does a high cache hit ratio always mean good performance?** No. Hot shards, large values, network RTT, or Java client contention can still cause high latency.

**15. Why check per-shard Max instead of only Average server load?** Averages mask a 95%-loaded hot shard when peer shards sit idle.

**16. Does viewing Azure Monitor metrics mean Redis diagnostic logs are in Log Analytics?** No. Logs require supported diagnostic categories, settings, and destinations.

**17. When Redis is unavailable, is DB fallback always better than failing requests?** No. Unbounded fallback from all traffic can crash the database; use bulkheads, backpressure, and tailored degradation.

**18. What problem does single-flight solve?** It coalesces concurrent requests for the same key to cut duplicate DB loads on misses, though in-JVM single-flight does not coalesce across separate pods.

**19. What is TTL jitter used for?** Preventing huge numbers of keys from expiring simultaneously and triggering a cache stampede.

**20. Is Redis `SET` always safe to retry?** No. Consider value/version ordering, TTL resets, concurrent writers, and side effects.

**21. Why never use Redis as the sole payment ledger?** Replicas, failovers, eviction, and persistence do not natively enforce financial invariants and durability.

**22. What causes rising Java timeouts when the Redis resource looks healthy?** DNS, TLS, credentials/tokens, networking, GC/event loops, command queues, or stale topology.

**23. Does a Redis Private Endpoint automatically grant authorization?** No. Private networking restricts connectivity; data-plane authentication and permissions are still required.

**24. Can you paste an Entra access token into a static password field forever?** No. Tokens expire and require refresh and re-authentication on new connections and reconnects.

**25. Do Managed Redis and legacy Azure Cache for Redis always share CLI commands, ports, and metrics?** No. Verify the exact product, tier, and version of your resource.

**26. Does geo-replication guarantee RPO=0?** Not by default; many modes are asynchronous with distinct consistency and conflict semantics.

**27. Does cache-aside invalidation have race conditions?** Yes. Stale reads can repopulate the cache after a writer commits and deletes the key.

**28. Should you measure Redis RTO or application RTO?** Both; users care when the API recovers its SLO, including reconnects, DB fallback, and cache warm-up.

**29. Why avoid running `KEYS *` or `MONITOR` continuously in production?** Both add heavy overhead, expose key names, and degrade performance.

**30. What are the top three signals to check when Redis evictions climb?** Used memory/working set, cache hit/miss rates, and application/DB fallback latency and load.

## 32. Production Redis deployment checklist

### 32.1. Product and HA architecture

- [ ] Confirmed whether the resource is **Azure Managed Redis** or an existing **Azure Cache for Redis** tier.
- [ ] Verified region, engine/version, networking, endpoint/port/TLS, and feature availability.
- [ ] Classified rebuildable cache data separately from state needing persistence/durability.
- [ ] Defined RPO/RTO/SLO and business owners without promising zero loss from replicas.
- [ ] Configured primary/replica and zone redundancy per SKU and region where needed.
- [ ] Planned multi-region DR if required by business, including traffic routing and DB dependencies.
- [ ] Tested failovers and measured **application RTO** beyond resource recovery.
- [ ] Documented runbooks for failover, DR/failback, data reconciliation, and cache warm-up.

### 32.2. Scaling and data

- [ ] Measured working set, memory overhead/fragmentation, and peak growth.
- [ ] Scaled up/out based on actual memory, server load, throughput, and latency.
- [ ] Java client supports the exact cluster or proxy topology of the Redis deployment.
- [ ] Tested slot migration and `MOVED/ASK` if using Redis Cluster.
- [ ] Analyzed big keys, hot keys, and multi-key/cross-slot constraints.
- [ ] Aligned TTL, invalidation, and schema versioning with consistency needs.
- [ ] Chose eviction policy from data classification rather than arbitrary toggles.
- [ ] Budgeted cost, reshard/upgrade headroom, and dual-version memory spikes during rollouts.

### 32.3. Java application

- [ ] Java uses compatible, tested Lettuce/Jedis/Spring Data Redis versions.
- [ ] Redis clients/connections are reused properly—never created per HTTP request.
- [ ] Configured connect/command timeouts, bounded retries, and jitter/backoff.
- [ ] No blind retries on `INCR`, list pushes, or scripts with uncertain side effects.
- [ ] Implemented circuit breakers, bounded DB fallback, and request coalescing for Redis disconnects.
- [ ] Separate metrics track cache misses vs cache unavailability.
- [ ] Redis unavailability cannot unleash unbounded SQL queries.
- [ ] Session/security counters enforce clear fail-open/fail-closed rules per threat model.
- [ ] Cache projections are never used as authoritative payment sources.
- [ ] Verified graceful shutdown, reconnects, and topology refresh during scaling/rollouts.

### 32.4. Security and operations

- [ ] TLS certificate chain and hostname validation work from actual pods/VMs.
- [ ] Private connectivity, DNS, firewalls, and routing verified for the resource SKU.
- [ ] Authentication uses Entra/ACLs or keys per support, with least-privilege data-plane rights.
- [ ] Entra token setups refresh/re-authenticate cleanly across token expiry.
- [ ] Access keys/secrets follow rotation lifecycles and stay out of Git, logs, and images.
- [ ] No raw PII, bearer tokens, or sensitive Redis keys appear in logs or metric labels.
- [ ] Web app runtimes lack unnecessary admin commands like flush or config.
- [ ] Azure Monitor metric definitions, aggregations/time grains, and shard dimensions verified.
- [ ] Unified Redis + Java + DB dashboards exist; alerts carry owners and runbooks.
- [ ] Diagnostic settings/retention match needs and access controls without logging whole keyspaces.
- [ ] Tested network outages, eviction pressure, hot keys, failovers, resharding, token expiry, and cold starts.
- [ ] Established baselines for tier spend, traffic, hit ratio, Redis capacity, DB fallback, and user p95.
- [ ] Migrations/upgrades follow staging validation, compatibility tests, canarying, rollback, and change review.

## 33. Conclusion

**High availability, scaling, and monitoring for Redis** is a system-wide architectural discipline, not merely toggling replicas in Azure. A **primary/replica** topology helps recover from node faults, yet asynchronous replication does not guarantee zero data loss; **zone redundancy** does not replace multi-region DR; persistence and backups serve distinct roles. Under growing load, distinguish **scale up, scale out, hot keys, big keys, cluster slots, and connection storms**, while matching the exact capabilities of Azure Managed Redis or your existing Redis tier.

Java applications need **TLS, authentication, timeouts, reconnects, bounded retries, cache-aside, TTL/invalidation, circuit breakers, and database fallback protection** to survive Redis faults. Operationally, combine **Azure Monitor metrics/diagnostics** with **Java command latency, cache hit/error/bypass rates, API SLOs, and Azure SQL telemetry**; attach owners to alerts and rehearse failover and cold-cache scenarios before production. Only when the cache stops being a single point of failure while preserving low latency, appropriate consistency, and budget discipline does Redis deliver its full value on Azure.
