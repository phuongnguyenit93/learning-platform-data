# Choosing Azure Managed Redis for Applications

An e-commerce system has **Azure App Service** serving APIs, **Azure SQL Database** storing transactional data, and **Azure Container Apps/AKS** running workers. When a promotional campaign starts, many users simultaneously open product pages. The API repeatedly reads the same product, pricing, and inventory records; response times increase and the database becomes a bottleneck. The development team wants to use Redis to keep frequently accessed data in memory, reduce SQL query volume, and handle traffic spikes.

However, choosing a Redis service is not just a decision of "how many GB should the cache be?". If the workload requires **100,000 requests/second** but the dataset is only 8 GB, the bottleneck may be **CPU and throughput**, not RAM. If the dataset is 800 GB but only 10% is read frequently, you need to consider a tier supporting RAM + flash and accept the latency of cold data. If the application uses a Redis library that does not support cluster redirects, choosing the wrong **clustering policy** can break the application. If Redis holds sessions or tokens, cache loss or authentication errors can log out large numbers of users at once.

**Azure Managed Redis (AMR)** is a Redis Enterprise service managed by Azure. This lesson guides you through choosing Azure Managed Redis based on **access patterns, tier, sizing, cluster policy, Redis modules, resiliency, security, networking, and cost**, and then designing an integration that fits the proper role of a cache. This is a lesson in the **Caching and Real-time Communication** chapter of the **CLOUD_PROVIDERS_AZURE** module: exploring Azure from subscriptions/resource groups/Microsoft Entra ID to virtual networks, compute, storage, and data, while deploying, monitoring, securing, and controlling application costs.

After this lesson, you will be able to:

- Evaluate **whether Redis is actually needed** and avoid confusing a cache with a database, queue, or durable message broker.
- Distinguish the four tiers **Memory Optimized, Balanced, Compute Optimized, and Flash Optimized** and select one based on workload characteristics.
- Choose **OSS Cluster, Enterprise Cluster, or Non-clustered** based on the client, multi-key operations, and modules.
- Estimate working set, memory overhead, connection limits, throughput, headroom, TTL, and eviction.
- Design cache-aside, invalidation, cache stampede mitigation, session/rate-limit handling, and graceful degradation.
- Choose **high availability, persistence, backup/export, and active geo-replication** according to recovery objectives and technical constraints.
- Secure Redis with **TLS, Microsoft Entra ID, managed identity, data access permissions, and Private Endpoint**.
- Build an Azure Portal lab, verify connectivity, and test cache behavior with an appropriate client.
- Design monitoring, migration from Azure Cache for Redis, cost evaluation, and incident runbooks.

## 1. Where does Redis fit in an Azure architecture?

**Redis** is a high-speed data store supporting key–value pairs and multiple data structures such as strings, hashes, lists, sets, and sorted sets; certain modules/features also support JSON, search, and other use cases. A Redis cache typically holds a **copy of data** from a source of truth to optimize speed, rather than replacing a transactional database.

~~~mermaid
flowchart LR
    USER[Web/mobile client] --> API[App Service: Catalog API]
    API -->|GET key| REDIS[(Azure Managed Redis)]
    REDIS -->|Cache hit| API
    API -->|Cache miss| DB[(Azure SQL Database)]
    DB -->|Result| API
    API -->|SET with TTL| REDIS
    API --> USER
    WORKER[Background worker] -. Update business record .-> DB
    WORKER -. Invalidate affected keys .-> REDIS
    OBS[Azure Monitor / App Insights] -. Observe .-> API
    OBS -. Observe .-> REDIS
~~~

### 1.1. Common cache functions

| Use case | Example | Key considerations |
|---|---|---|
| **Cache-aside / read-through logic in app** | `product:123` holds product description JSON | Have TTL/invalidation; authoritative data lives in SQL |
| **Session store** | Temporary session tokens/state for web app | A Redis outage can log users out; evaluate security/HA |
| **Rate limiting counter** | Number of client requests within a window | Use atomic operations/expiry and design fail-open/closed behavior |
| **Real-time leaderboard** | Sorted set by score | Protect consistency; do not assume ranks are always long-term durable data |
| **Feature flags / config cache** | Infrequently changing configuration list | TTL and versioning prevent serving stale config |
| **Real-time Pub/Sub notifications** | Worker sends internal update notifications | Redis Pub/Sub is not inherently a durable queue |
| **Distributed coordination** | Short-lived locks, state tokens | Requires fencing/timeouts; do not build correctness on a naive cache lock |
| **Search/JSON** | Searching catalog by attributes | Requires supporting module and clustering policy |

**A cache is a conditional optimization.** If a system needs replay, dead-letter handling, transactional messaging, or durable message retention, Azure Service Bus / Event Hubs / Event Grid (depending on the use case) are generally more appropriate than using Redis Pub/Sub as a queue.

### 1.2. Distinguishing source of truth from derived data

For example, the `Products` table in SQL contains:

~~~text
Id=123, Name="Headphones A", Price=1_200_000, Version=17
~~~

Redis holds data that can be easily rebuilt:

~~~text
Key: catalog:v3:product:123
Value: {"id":123,"name":"Headphones A","price":1200000,"version":17}
TTL: 300 seconds
~~~

When Redis expires or clears the key, the API can still read SQL and repopulate the data. **Do not place sole-copy transactional data** such as final balances, paid orders, or accounting records only in cache. If using Redis for data that cannot be regenerated, durability/backup/transaction requirements must be evaluated separately; Azure Managed Redis is not by default a replacement for a relational database.

### 1.3. When should you avoid adding Redis?

Do not add Redis if data is rarely accessed repeatedly, the database already meets its SLO, network latency to Redis increases total response time, or operational cost outweighs the benefit. Before purchasing a Redis instance, measure:

- P50/p95/p99 API latency and percentage of time spent waiting on SQL.
- Repeat read frequency for the same keys, **working set**, and expected hit rate.
- SQL CPU/IO/connection pool load before and after caching.
- Allowable data freshness: is 5 seconds of staleness acceptable, or strictly zero?
- Impact when the cache is cleared, fails over, or expires en masse.
- Backend cost savings compared with Redis compute/network/monitoring expenses.

Redis **is not free** just because it is a cache. An ineffective cache with a low hit ratio can add both an extra network hop and higher cost.

## 2. How does Azure Managed Redis differ from legacy Azure Cache for Redis?

Two product names are easily confused:

- **Azure Managed Redis**: the modern managed service based on Redis Enterprise, with new tiers/features and its own configuration model.
- **Azure Cache for Redis**: the previous-generation service with **Basic, Standard, Premium, Enterprise/Enterprise Flash** tiers. These tiers are **not** the four tiers of Azure Managed Redis.

According to Microsoft's lifecycle announcements as of this lesson's writing:

| Legacy service family | Planning milestone | Meaning |
|---|---|---|
| **Azure Cache for Redis Enterprise / Enterprise Flash** | Announced retirement date **March 31, 2027** | Need a migration plan to Azure Managed Redis before the deadline |
| **Azure Cache for Redis Basic / Standard / Premium** | Announced retirement date **September 30, 2028** | Need to evaluate/migrate before retirement |
| **New customers creating legacy caches** | Creation restrictions already applied in 2026 depending on tenant/region | Prefer Azure Managed Redis for new projects |

Milestones are **product lifecycle information subject to change**; always verify Microsoft announcements before signing contracts or planning migrations. Do not choose Azure Cache for Redis Basic merely because older tutorials use that SKU and assume it is still the default for new projects.

Azure Managed Redis embeds **Redis Enterprise architecture and sharding** into the platform design; the clustering policy determines **client-side** behavior. Limits, ports, DNS endpoints, modules, high availability, connection behavior, and resource provisioning can differ from legacy caches. In particular, **Azure Managed Redis typically uses endpoints in the form `<cache-name>.<region>.redis.azure.net:10000`**, which differs from the common hostname/port of previous-generation Azure Cache for Redis tiers. Do not copy port `6380` or legacy connection strings to AMR without checking.

> **Official references:** Azure Managed Redis overview: https://learn.microsoft.com/azure/redis/overview; Azure Cache for Redis retirement: https://learn.microsoft.com/azure/azure-cache-for-redis/retirement-faq.

## 3. Four Azure Managed Redis tiers: choosing by RAM, CPU, and access pattern

Azure Managed Redis provides **three in-memory tiers** differing in memory-to-vCPU ratio, and **one RAM + NVMe flash tier** for large datasets. The ratios below reflect **tier design orientation**; actual vCPU/shard counts per SKU may evolve as the service is optimized.

| Tier | Target Memory : vCPU | When it fits | When it does not fit |
|---|---:|---|---|
| **Memory Optimized** | **8 : 1** | Large datasets, moderate access rates, capacity-oriented | Very high CPU/throughput per GB of data |
| **Balanced** | **4 : 1** | General workloads: cache-aside, sessions, web APIs | Extremely large datasets or heavily CPU-bound workloads |
| **Compute Optimized** | **2 : 1** | High command rate/CPU, high throughput, compute-heavy workloads | Low request volume, high GB requirements optimizing memory cost |
| **Flash Optimized** | RAM combined with **NVMe flash** | Hundreds of GB to TB datasets, clear hot/cold split, tolerates variable tail latency | Uniform random reads across the full dataset, write-heavy loads, consistently ultra-low latency, or unsupported modules |

### 3.1. Memory Optimized

This tier prioritizes **RAM per unit of CPU**, useful when the dataset is large but command volume is not excessively high. For example, an enterprise needs to cache 100 GB of catalogs/feature flags for relatively steady, lightweight read workloads.

**Do not assume more RAM = always faster.** A 100 GB cache on Memory Optimized can hit a command-processing bottleneck while a 20 GB Compute Optimized cache handles more requests. Measure actual ops/s, Server Load/CPU, and latency.

### 3.2. Balanced

Balanced is a sensible starting point for many applications before evidence shows an extreme need for compute or memory optimization: storing sessions, product caches, and small API keys. To run Redis in production, choose **HA** and an SKU/size meeting SLA/network requirements; **selecting the Balanced tier does not automatically enable all security/HA settings**.

### 3.3. Compute Optimized

Compute Optimized fits when:

- Commands per second are high and CPU/Server Load frequently reaches thresholds.
- There are many operations or computationally costly commands.
- The dataset is not overly large relative to throughput.
- More shards/vCPUs are needed for parallelism compared with memory-oriented tiers.

However, before scaling, check for **hot keys, blocking O(N) commands, large values, improper pipelining, and excessive connections**. Buying more CPU will not fix a single key that funnels all traffic onto one shard.

### 3.4. Flash Optimized

Flash Optimized keeps hot data in RAM and cold data on NVMe flash. A reference model: roughly **20% of capacity in RAM** and the remainder on flash (verify exact ratios/behavior per SKU). Values on flash must be loaded into RAM when accessed, so p95/p99 latency depends on how hot or cold the data access is.

**Important limitations:** per current guidance, Flash Optimized **does not support active geo-replication**, **Non-clustered**, **RediSearch**, **RedisBloom**, or **RedisTimeSeries**; verify supported modules (such as RedisJSON) before choosing. If the workload requires vector search/RediSearch, **do not choose Flash simply because the dataset is large**.

Example:

~~~text
Dataset: 900 GB
Hot working set: 100 GB
Access pattern: 90% requests to hot keys
Potential fit: Flash Optimized, but measure p95/p99 after loading production-size data.

Dataset: 900 GB
Hot working set: 850 GB
Access pattern: random reads across all keys
Potential issue: flash misses/tail latency; consider other tier/architecture.
~~~

**Performance must be measured at near-production data volume.** A new Flash cache holding 5 GB completely in RAM can look extremely fast in a lab, without reflecting latency once the production dataset exceeds RAM.

### 3.5. Watch SKU sizes, preview status, and regions

Each tier has multiple **SKU sizes** with different capacities and maximum client connections; some large sizes may be in **preview**. Do not put preview sizes/features into critical production workloads without verifying support, SLA, region, and governance. Azure regions differ in availability; check **region availability** and tier capabilities at creation time rather than assuming uniform global availability.

**Reference:** https://learn.microsoft.com/azure/redis/plan-tiers-and-capacity.

## 4. Choosing a clustering policy before creating the cache

Azure Managed Redis runs Redis Enterprise internally, while the **client protocol** depends on the clustering policy. This is one of the most important decisions because **OSS/Enterprise usually cannot be changed after creation**, and the choice also affects modules, multi-key commands, and performance.

### 4.1. Three policies

| Policy | How clients connect | Advantages | Limitations |
|---|---|---|---|
| **OSS Cluster** | Client supports Redis Cluster API, discovers shards, handles `MOVED`/`ASK` | Typically higher throughput, routes directly to shards | Client must be cluster-aware; multi-key ops must share the same hash slot |
| **Enterprise Cluster** | Client uses a single endpoint like standalone Redis; internal proxy routes to shards | Easy integration for non-cluster-aware clients, supports RediSearch | Proxy can cap throughput; some multi-key ops still have cross-slot restrictions |
| **Non-clustered** | Client connects to an unsharded Redis | Compatible with certain nonclustered/multikey workloads; supports RediSearch | Limited to small capacities (typically ≤25 GB), does not scale across shards; preview/availability varies |

**The name "Enterprise Cluster" does not mean it is only for an Enterprise tier.** It is a **clustering policy**, whereas Memory Optimized/Balanced/Compute Optimized/Flash Optimized are **data tiers**. These two axes are independent, though they have feature constraints.

### 4.2. OSS Cluster and hash slots

With OSS clustering, Redis distributes keys across **hash slots**. Multi-key commands, transactions, or scripts require related keys to be in the **same hash slot**, or they can fail:

~~~text
MGET product:101 product:102
    → May return CROSSSLOT if the two keys map to different slots.

MGET cart:{customer-42}:items cart:{customer-42}:total
    → The hash tag {customer-42} forces these keys into the same slot.
~~~

Do not add a `{all}` hash tag to every key just to suppress errors: that pushes the entire workload onto one shard and defeats scale-out. Design hash tags around transaction groups that truly need atomic multi-key operations.

Certain commands/scripts are restricted by the managed service. Check Redis command compatibility rather than assuming `CLUSTER SETSLOT` or topology-admin commands work in a managed service.

### 4.3. Enterprise Cluster: simple endpoint, not magic

Clients see a single endpoint, and a proxy routes internally to shards. This helps when legacy apps use `redis.Redis`/standalone clients or need RediSearch. However, **arbitrary cross-slot multi-key operations are not guaranteed to be fully supported**, and the proxy can become a bottleneck for ultra-high-throughput workloads.

**Do not claim Enterprise Cluster supports all cross-key Redis transactions.** Test the actual command set, including Lua scripts, MULTI/EXEC, cross-slot behavior, scan, pipelining, and RedisJSON/RediSearch when used.

### 4.4. Non-clustered

Non-clustered serves small workloads requiring single-shard semantics or migrating apps not yet ready for clustering. Size limits and preview status must be verified before production. Once an instance moves from Non-clustered to clustered, reverting back is not supported by default. For fast-growing workloads, choosing Non-clustered just to avoid client updates can create migration overhead later.

### 4.5. Java, .NET, Node.js, and Python clients must match the topology

| Client library | OSS Cluster | Enterprise/Non-clustered |
|---|---|---|
| **Lettuce (Java)** | `RedisClusterClient` | `RedisClient` |
| **Jedis (Java)** | `RedisClusterClient` / corresponding version API | `RedisClient` or standalone client |
| **redis-py (Python)** | `RedisCluster` | `redis.Redis` |
| **node-redis** | `createCluster` | `createClient` |
| **StackExchange.Redis (.NET)** | Cluster discovery supported by library | Single-endpoint connection model |

Azure Managed Redis typically starts on **TCP 10000**; with OSS Cluster, the client discovers and connects to **shard ports 85xx** based on current topology. Do not hardcode shard ports or hostnames in code; firewalls/private networks must allow connections as required by the service.

### 4.6. Decision tree for choosing a clustering policy

~~~mermaid
flowchart TD
    START[Redis workload] --> SEARCH{Need RediSearch / vector search?}
    SEARCH -->|Yes| SINGLE{Small dataset and need nonclustered semantics?}
    SINGLE -->|Yes, fits limits| NON[Evaluate Non-clustered]
    SINGLE -->|No| ENTER[Enterprise Cluster]
    SEARCH -->|No| LIB{Does client support Redis Cluster API?}
    LIB -->|Yes| OSS[Prefer benchmarking OSS Cluster]
    LIB -->|No| MUTLI{Need unsharded + small?}
    MUTLI -->|Yes| NON
    MUTLI -->|No| ENTER
    OSS --> BENCH[Benchmark workload and command compatibility]
    ENTER --> BENCH
    NON --> BENCH
~~~

**Choose the policy before provisioning.** Once a cache is created with OSS/Enterprise, changing policy may require creating a new instance and migrating data/clients, incurring extra cost and endpoint-cutover effort.

**Source:** https://learn.microsoft.com/azure/redis/choose-clustering-policy.

## 5. Redis modules and versions: don't decide late

Azure Managed Redis supports Redis add-on features/modules depending on **version, tier, and clustering policy**. Many module configurations are **creation-time** decisions and cannot arbitrarily be toggled on later for the same instance.

### 5.1. When modules are needed

| Feature | Purpose | Selection notes |
|---|---|---|
| **RedisJSON** | Store/access partial JSON documents | Check JSON payload, version, and memory overhead |
| **RediSearch** | Full-text, secondary indexes, and vector search depending on feature set | **Not supported with OSS Cluster** under current policy; choose Enterprise/Non-clustered appropriately |
| **RedisBloom** | Bloom/Cuckoo filters, saving memory for membership tests | False positives are by design; does not replace authoritative data |
| **RedisTimeSeries** | Time-series ingestion/aggregation | Does not replace long-term analytics systems if specific retention/audit is needed |

For **Flash Optimized**, supported modules **differ** from in-memory tiers; per current guidance, RedisJSON is the primary supported module on Flash, while RediSearch/Bloom/TimeSeries are unavailable. Always verify the compatibility matrix for the exact engine/version at creation time.

### 5.2. Redis 7.4 and Redis 8.x

Per service guidance at the time of writing, **Redis 7.4** is the stable default option. **Redis 8.2** may appear in **preview** on certain in-memory tiers with built-in modules, but comes with limitations such as no support for Flash, active geo-replication, and certain custom access policies; upgrading an existing 7.4 instance in-place to a preview release is not necessarily supported.

Do not pick a higher version number as the sole criterion. For production:

1. Choose a Redis version with acceptable support/SLA and command compatibility.
2. Verify modules/cluster policy on that version.
3. Test RESP2/RESP3 protocol differences, client libraries, and commands.
4. Check whether upgrades/downgrades are supported in-place or require a new instance.
5. For previews, review **support policy and feature exclusions** before deciding.

### 5.3. Modules can increase memory and CPU cost

A secondary index across millions of JSON documents can consume substantial RAM beyond the raw data size; searches can also cause CPU spikes. Do not size a cache solely by unindexed JSON byte totals. Estimates should include **indexes, per-key metadata, replication buffers, TTL bookkeeping, and hot working set**.

**Before creating the cache:** document the planned module set and test query patterns. If a month later you discover RediSearch is needed on an OSS Cluster cache, you may have to **provision another instance** and migrate the application.

## 6. Capacity planning: RAM, overhead, CPU, connections, and headroom

Choosing the right SKU requires **quantification** rather than "picking 10 GB because the database is 10 GB". Redis stores data in internal structures; keys, pointers, expiration metadata, indexes, replication, and system-reserved memory all incur overhead.

### 6.1. Calculating raw dataset size

Suppose a catalog API cache has:

- 2,000,000 products.
- Average JSON payload **1,200 bytes/key**.
- Average key string **40 bytes/key**.
- Per-key metadata/overhead and structural overhead estimated at **100 bytes/key** as a starting point.

Raw estimate:

\[
2{,}000{,}000 \times (1{,}200 + 40 + 100)
=2{,}680{,}000{,}000\ \text{bytes}\approx 2.68\ \text{GB}.
\]

This is a **rough estimate**, not exact Redis memory usage; serializers, Redis data types, indexes, the memory allocator, and key cardinality can change the result. Use `MEMORY USAGE` on sample data if the command is supported and measure metrics on a lab instance.

### 6.2. Reserved memory and replicas

Azure Managed Redis reserves roughly **20% of available memory** as a buffer for system tasks according to the service model; verify exact values and metric presentation per tier/SKU. **Do not treat advertised capacity as 100% free space for payloads.**

When HA is enabled, some raw memory metrics may sum both primary and replica, making numbers look nearly doubled. **Do not double the dataset estimate again** just because raw metrics include replicas; use **Used Memory Percentage** and SKU effective memory semantics for sizing. That is why understanding metric definitions matters, not just reading a "GB" table.

### 6.3. Sizing example with headroom

Suppose:

~~~text
Measured dataset after encoding/indexing:   18 GB
Expected one-year growth:                   30%
Target operational headroom:                25%
Additional workload assumptions:            validated via load test
~~~

An initial estimate of **effective usable memory**:

\[
18 \times 1.30 = 23.4\ \text{GB (projected dataset)};
\]

\[
\text{Required effective capacity}
\approx\frac{23.4}{0.75}=31.2\ \text{GB}.
\]

The figure **31.2 GB effective usable** is not the name of an Azure SKU. You must map usable capacity after reserved buffers/replicas per tier, then pick an SKU with real headroom and passing load test results. If the workload uses indexes or Flash hot/cold split, add corresponding modeling.

### 6.4. Throughput cannot be inferred from memory

Two 10 GB workloads can behave very differently:

| Workload | Requests/second | Characteristics | Potential bottleneck |
|---|---:|---|---|
| Feature flags cache | 1,000 | Small key GETs, high hit rate | Network, connection/latency |
| Product lookup | 50,000 | GET/SET, cache-aside | Server Load, CPU, shards |
| Leaderboard | 10,000 | ZADD/ZRANGE, key distribution | Hot sorted set, CPU |
| Session store | 20,000 | GET/SETEX, TTL, many connections | Connection limits, memory, serialization |
| Full-text search | 2,000 queries | RediSearch index and filtering | Index memory, CPU, cluster policy |

A smaller Compute Optimized SKU may serve a high-throughput workload better than a large Memory Optimized SKU. Conversely, a large infrequently accessed dataset may favor Memory/Flash. **Benchmark with a production-like command mix and dataset.**

### 6.5. Connection limits and client management

Each SKU has a **maximum client connections** limit. This number alone can force you to pick a larger SKU even while Used Memory and CPU remain low.

For example, suppose a system has:

~~~text
20 App Service instances × 150 Redis connections/instance = 3,000 connections
5 background workers × 200 connections/instance = 1,000 connections
Monitoring/maintenance/peak margin = 500 connections
Total plan ≈ 4,500 connections
~~~

However, 150 connections/instance may already be **far too many** for common Redis usage. Libraries like StackExchange.Redis and Lettuce are designed to **reuse connections** rather than open a new connection per request. Do not upsize the SKU to mask application code that constantly opens and closes connections.

### 6.6. Choosing headroom and scaling triggers

Per current guidance, monitor **Used Memory Percentage** and consider scaling when sustained utilization exceeds **around 75%**, while also watching Server Load/CPU, connection count, evictions, and p95/p99. This is a **reference threshold**, not a hard rule for every workload.

You should be able to answer:

- If 30% of keys expire simultaneously, can the database survive the cache misses?
- If traffic triples for 10 minutes, what happens to throughput and cache hit ratio?
- If one shard becomes a hot spot, will scaling memory solve it?
- If Redis fails over, do clients reconnect and retry safely?
- If scaling down is needed later, do usage and constraints allow it?

## 7. TTL, expiration, and eviction policy: how long does cached data live?

In Redis, **TTL (time to live)** defines when a key expires. **Eviction** is the process of removing keys under memory pressure according to a policy. These two mechanisms are distinct.

### 7.1. TTL by data type

| Data | Example TTL | Additional invalidation needed? |
|---|---|---|
| Public product description | 5–30 minutes | When product is edited |
| Promotional price | 15–60 seconds if staleness is allowed | When marketing changes price |
| Inventory availability | Very short or uncached depending on consistency | When order deducts stock; source of truth must confirm |
| User session | Per login and security policy | Logout/revoke; do not rely solely on TTL |
| Feature flags | 30–120 seconds | Urgent policy changes need fast invalidation |
| Rate-limit counter | Per algorithm window | Use atomic operations and expiry |

These TTLs are **illustrative only** and must be derived from business SLAs. **Do not cache prices/stock in ways that cause invalid transactions** if the system cannot tolerate staleness. Short TTLs do not completely eliminate race conditions; checkout must read/lock inventory from a transactional source.

### 7.2. Expiration vs eviction

~~~text
Key "catalog:product:123" TTL 300s:
    → expires after 300s, regardless of whether Redis still has free RAM.

Key has not reached TTL, but Redis is nearly full:
    → the eviction policy may remove the key early if it falls within the eligible set.
~~~

Applications must treat a **cache miss as normal**, even before TTL expires. Redis HA/failover, eviction, manual flush, or instance replacement can all cause keys to disappear.

### 7.3. Choosing an eviction policy

Azure Managed Redis commonly defaults to **`volatile-lru`**: when memory is tight, it prioritizes evicting **keys with a TTL** using LRU behavior. If most keys have no TTL, Redis can **run out of eviction-eligible keys** and writes begin failing once capacity is exhausted.

| Policy | Description | Use case |
|---|---|---|
| `volatile-lru` | LRU among keys **with a TTL** | Mixed cache combining non-evictable keys with expiring keys |
| `allkeys-lru` | LRU across all keys | Pure rebuildable cache where any key may be evicted |
| `volatile-ttl` | Prioritizes keys with shortest remaining TTL | When TTL remaining is the primary criterion |
| `noeviction` | Does not evict when full; writes may fail | Cases where losing keys is unacceptable, requiring early alerts/scaling |

**Do not choose `allkeys-lru` for data or coordination keys that the application assumes cannot disappear** without a recovery protocol. For pure cache-aside where all keys are rebuildable, `allkeys-lru` may make more sense.

### 7.4. Avoiding synchronized TTL expiration

If 1 million keys are created at 10:00 with a 300-second TTL, they can all expire at 10:05 and hit backend SQL with a **cache avalanche**. One way to reduce this risk is random jitter:

~~~text
baseTTL = 300 seconds
jitter  = random(0..60)
TTL     = baseTTL + jitter
~~~

In production, add jitter only when freshness SLAs permit. For authorization/session keys, do not arbitrarily extend credential validity; security-related TTLs must be anchored to actual issuance/expiration times.

### 7.5. Hot keys and big keys

- **Hot key**: a single key receiving disproportionate traffic, turning one shard/CPU into a bottleneck even when overall cache capacity is low.
- **Big key**: an oversized value/hash/list/set causing high serialization, network, and Redis command latency.
- **High cardinality**: millions of tiny keys making per-key overhead significant.

Inspect key access distribution, value sizes, and command complexity; avoid `KEYS *` in production as it can spike CPU and latency. Use scan or supported monitoring features, restrict access permissions, and avoid logging sensitive values.

### 7.6. Order of decisions for TTL/eviction

1. Define the business **staleness budget**.
2. Choose key naming and ownership.
3. Decide TTL, write-time invalidation, and cache miss handling.
4. Select an eviction policy matching how "disposable" the data is.
5. Run load tests with a nearly full working set and measure evictions/misses/DB load.
6. Set alerts/scaling before memory pressure triggers a retry storm.

If using **active geo-replication**, restrictions apply to changing the eviction policy after joining a group; finalize it early.

## 8. Cache patterns: design properly before scaling Redis

### 8.1. Cache-aside (lazy loading)

The most common pattern for read APIs:

~~~mermaid
sequenceDiagram
    participant API as Catalog API
    participant R as Managed Redis
    participant DB as Azure SQL
    API->>R: GET catalog:v3:product:123
    alt Cache hit
      R-->>API: cached product JSON
    else Cache miss
      R-->>API: null
      API->>DB: SELECT product 123
      DB-->>API: authoritative row
      API->>R: SET key value EX 300
    end
~~~

Pros: no need to preload all data. Cons: cold misses are slower, race conditions can occur when SQL updates coincide with cache population, and a **cache stampede** can hit if thousands of requests miss simultaneously.

### 8.2. Invalidate after write

~~~text
1. Backend validates request and updates SQL in a transaction.
2. SQL COMMIT succeeds.
3. Backend deletes cache key or bumps a versioned key.
4. Next GET misses cache, reads new authoritative data, repopulates Redis.
~~~

Do not delete the cache **before** SQL commit without accounting for races: another request can read the old SQL row and repopulate the cache right before commit. Handle invalidation failures (outbox/change feed/retries) if tight freshness is required.

For high-consistency payment/inventory operations, **the cache must never be the final decision source**; transaction records must be verified in the database/transaction even if an earlier GET used Redis.

### 8.3. Cache stampede

If a hot key expires and 5,000 requests arrive at once, all 5,000 could call SQL:

~~~text
Redis: key missing
   ├─ Request 1 → SQL
   ├─ Request 2 → SQL
   ├─ ...
   └─ Request 5000 → SQL overloaded
~~~

Mitigation techniques:

- TTL jitter and pre-warming hot keys.
- **Request coalescing/single-flight** within each app instance.
- Bounded distributed locks with **timeout and fencing** if needed; do not rely on Redis locks as the sole correctness mechanism.
- Stale-while-revalidate if the business tolerates slightly stale data within a controlled window.
- Rate limiting/circuit breakers toward the database during a cache miss storm.
- Background refresh, concurrency caps, and safe fallbacks.

### 8.4. Cache penetration and negative caching

If users or bots query millions of nonexistent product IDs, every cache miss can hit SQL. **Negative caching** briefly stores "not found" for valid-format but missing IDs:

~~~text
GET product:nonexistent
→ SQL: not found
→ Cache sentinel for 10–30s if appropriate
~~~

Distinguish **not found** from **database error**. Never cache a 500/timeout error as "nonexistent" for hours. Validate IDs and rate-limit before querying, and ensure negative caching does not prolong 404 responses right after a new product is created.

### 8.5. Applications must function when Redis is unavailable

If Redis fails, a catalog API can fall back to SQL with **bounded concurrency**/rate limiting. Conversely, for a Redis-backed session store, losing the cache can log users out with no "read SQL" fallback if sessions exist only in Redis. Define availability degradation **per use case**, not with a blanket catch-all that ignores every Redis exception.

**Anti-pattern:** immediately sending 100% of traffic to SQL on any Redis timeout, taking SQL down too. Use circuit breakers, sensible short timeouts, and downstream capacity budgets.

## 9. Securing Azure Managed Redis: networking, TLS, and Microsoft Entra ID

Because Redis holds short-lived keys, teams often overlook security. Yet unauthorized cache access can expose sessions, PII, access flags, or API responses, or allow an attacker to trigger heavy database load by deleting keys. **Private networking, authentication, Redis authorization, and payload protection are separate layers.**

### 9.1. Security questions to answer

| Question | Mechanism |
|---|---|
| Which runtimes may connect to Redis? | VNet/Private Endpoint, DNS, public access policy |
| Are connections encrypted and verifying the server? | TLS and certificate validation |
| What identity is the application? | Microsoft Entra ID/managed identity, or approved access key |
| Which keys/commands can that identity run? | Redis data access policies/ACLs per feature support |
| Who can create/delete/modify cache configuration? | Azure RBAC control plane and pipeline governance |
| Does the cache hold sensitive data? | Data classification, application encryption, TTL/retention |

### 9.2. Endpoints and ports

Azure Managed Redis typically uses a hostname of the form:

~~~text
<cache-name>.<azure-region>.redis.azure.net
~~~

**The standard TLS endpoint uses port `10000`.** With **OSS Cluster**, clients discover shards and subsequent connections may use **ports 85xx**, depending on cluster topology. Configure firewalls/Private Endpoint routing accordingly; do not assume opening port 10000 suffices for all Redis Cluster clients if shard connections are blocked.

**Do not copy port `6380`** from legacy Azure Cache for Redis Basic/Standard/Premium tutorials into an Azure Managed Redis client. Obtain the hostname/port from the actual Azure Managed Redis resource and corresponding client/library documentation.

### 9.3. Private Endpoint and DNS

~~~mermaid
flowchart LR
    APP[App Service/AKS/VM] --> NET[Outbound VNet route]
    NET --> DNS[Azure Private DNS / resolver]
    DNS --> IP[Private Endpoint IP]
    IP --> AMR[(Azure Managed Redis)]
    APP -. TLS + Entra token .-> AMR
    PUB[Public access] -. Disabled by policy .-> AMR
~~~

A Private Endpoint places a NIC/private IP inside your subnet for service connectivity. Clients still connect using the standard FQDN `<name>.<region>.redis.azure.net`; the associated Private DNS zone is named `privatelink.redis.azure.net` under the service model. **Do not connect directly to the private IP or `*.privatelink...`** to avoid TLS hostname/certificate mismatches and IP dependencies.

**Deployment note:** creating a Private Endpoint **does not automatically grant App Service outbound VNet Integration**. An inbound App Service private endpoint is a separate feature. AKS requires proper DNS/Pod networking, Container Apps requires VNet/network configuration, and on-premises requires VPN/ExpressRoute + DNS forwarding.

### 9.4. Public network access is a separate decision

Azure Managed Redis exposes a **`publicNetworkAccess`** setting separate from Private Endpoints in newer API versions. For private-only goals, **disable public access** alongside proper Private Endpoint/DNS configuration. Some older resources/docs had different default behaviors when adding/removing Private Endpoints; **do not assume "creating a Private Endpoint automatically disables public access"**.

Before changing public network access:

1. Inventory all consumers: APIs, workers, batch jobs, CI, monitoring, and admin tools.
2. Create the Private Endpoint, approve the connection, and configure DNS.
3. Test from the **actual runtime**: DNS → TCP → TLS → Entra AUTH → GET/SET.
4. Verify client reconnect behavior after network changes.
5. Disable public access through change approval; run positive tests from private and negative tests from public.

Do not leave public access open indefinitely just so Redis Insight on an admin laptop can connect easily; for operations, use an approved VPN/Jump Host/private runner.

### 9.5. Microsoft Entra ID by default

Azure Managed Redis prioritizes **Microsoft Entra authentication**. When creating a new instance under current guidance, Entra authentication is enabled by default and **access key authentication may be disabled by default** for security. Do not build new applications assuming a static Redis password/access key is available.

A basic Entra authentication flow:

~~~mermaid
sequenceDiagram
    participant APP as App with Managed Identity
    participant ENTRA as Microsoft Entra ID
    participant REDIS as Azure Managed Redis
    APP->>ENTRA: Acquire token for redis.azure.com scope
    ENTRA-->>APP: Access token with expiration
    APP->>REDIS: TLS connection to endpoint:10000
    APP->>REDIS: AUTH <principal-object-id> <access-token>
    REDIS-->>APP: OK if principal allowed
    Note over APP,REDIS: Refresh token and re-AUTH before expiry
~~~

Under the Entra Redis mechanism:

- **Username** is typically the **object ID** of the managed identity or service principal.
- **Password** is a **short-lived Entra access token**, not an account key.
- The token scope is typically `https://redis.azure.com/.default`.
- The principal must be **added to Redis users/data access configuration**, not merely granted Azure Contributor.
- Clients must **refresh tokens and re-authenticate before expiration**, otherwise long-lived connections can drop.
- Microsoft Entra **groups are not supported as Redis users** under current guidance; configure supported principal types directly.

**Important:** Azure RBAC Contributor on the cache resource is a **control-plane** permission. It **does not automatically grant** Redis data-plane `GET/SET` access to a managed identity. Redis authentication must be configured separately; evaluate custom data access policies and preview limitations when needed.

### 9.6. Access keys and rotation

When access keys must be used for client compatibility:

- Store secrets in Azure Key Vault or an equivalent secret store.
- Never put keys in Git, Docker images, plaintext Terraform state, query strings, or logs.
- Restrict who has permission to view or regenerate keys.
- Plan rotation with a dual-credential strategy if supported by the service.
- Transition gradually to Entra tokens and disable key auth once all clients are ready.

**Changing key-auth mode can drop active connections**, including clients already using Entra depending on service behavior; ensure reconnect/re-auth logic and a change window rather than toggling it off unverified in production.

### 9.7. Data access policies and data classification

When multiple applications share a cache, isolate access:

~~~text
Principal orders-api:
    read/write keys orders-cache:*

Principal catalog-api:
    read/write keys catalog:*

Principal monitoring:
    read-only metrics/approved commands
~~~

This illustrates **policy intent**, not guaranteed valid ACL syntax. Custom data access permissions may be in preview or unsupported on certain Redis versions; verify capabilities before basing security designs on them.

**A single Redis instance is not an absolute tenant isolation boundary** when multiple tenants share memory, CPU, eviction, and broad privileges. Key prefixes do not replace ACLs/identity. For sensitive data, consider separate cache instances or application-level encryption, because encryption-at-rest for persistence disks **does not mean payloads in RAM are encrypted with an application-owned key**.

### 9.8. TLS and certificate validation

Redis connections must verify the certificate chain and hostname, not merely flip a TLS flag nominally. Never connect via private IP, disable certificate validation, or downgrade to non-TLS to work around DNS issues. Keep runtime trust stores and Redis clients updated when certificate/TLS requirements change.

**Sources:** https://learn.microsoft.com/azure/redis/secure-azure-managed-redis; https://learn.microsoft.com/azure/redis/entra-for-authentication; https://learn.microsoft.com/azure/redis/private-link.

## 10. High availability, persistence, backup, and geo-replication

"Redis has a replica" does not mean "all data is permanently safe". Azure Managed Redis offers multiple reliability features, each protecting against different failure modes. Choose based on **business RPO/RTO and acceptable cache loss**, instead of toggling everything on just because switches exist.

### 10.1. High Availability (HA)

HA distributes **primary and replica shards** across multiple nodes to enable failover during node/shard faults or maintenance. For production, **enable HA**; current guidance states HA is required for SLA coverage under Managed Redis. Non-HA instances carry higher downtime/data-loss risk and should only be used for **disposable dev/test**.

Once HA is enabled on a cache, disabling it later is not supported by default; this choice has directional constraints. HA also does not create independent backup/restore points.

### 10.2. Availability zones

In regions supporting Availability Zones, HA caches are typically distributed across zones per the service model, providing zone-fault resilience. However:

- Zone redundancy does not protect against a **region-wide outage**.
- Replicated data may experience **lag** prior to failover.
- Clients must reconnect and retry safely after topology changes.
- Verify availability per region/SKU and automatic zone selection behavior.

### 10.3. Data persistence: RDB and AOF

Based on supported features:

- **RDB persistence:** periodic snapshots of Redis state to service-managed disk, useful for recovering from certain failures; changes since the last snapshot can be lost.
- **AOF persistence:** logs write operations and syncs per service policy, narrowing the data-loss window compared with periodic RDB without providing database transaction semantics.

**Persistence is not backup.** Bad writes or accidental key deletions can also be persisted. Internal persistence files are generally used by the service to **recover that same cache**, not as portable artifacts you extract to restore into a different cache. For importable copies, use **Export/Import** or data/application-tier backups.

Data persistence requires HA per service guidance and **cannot be combined with active geo-replication** on the same cache. Flash Optimized has its own conditions, potentially in preview. Do not design AOF + geo-replication together assuming the Portal will allow enabling both.

### 10.4. Active geo-replication

Active geo-replication synchronizes caches across Azure regions using an eventual consistency model. It solves certain multi-region/DR scenarios, with key caveats:

- Not **synchronous strong consistency** and carries no instant-sync SLA; conflicts and lag must be tolerated by the application.
- Instances in a group must have compatible configurations (SKU/capacity, modules, cluster policy, eviction/TLS as required).
- **Flash Optimized does not support** this feature per current documentation.
- Certain small SKUs like **Balanced B0/B1** are not supported.
- Cannot be combined with persistence.
- Adding/removing members from a geo-replication group can affect existing data; require a migration runbook and testing.

If a cache only stores rebuildable product descriptions, **independent regional caches** pre-warmed from an authoritative DB are often simpler to operate than geo-replication. If Redis holds session state shared across regions, carefully evaluate privacy, TTL, conflicts, and latency beforehand.

### 10.5. Export/Import and operational backups

Azure Managed Redis provides supported **Export/Import** mechanisms, typically interacting with Azure Blob Storage. Use them when snapshots are needed for migration, testing, or recovery, while verifying:

1. Format/version compatibility and modules.
2. Data size, export/import duration, and network/storage permissions.
3. Encryption/retention, artifact storage location, and data classification.
4. Whether a custom automation schedule exists; do not assume Azure automatically creates nightly export backups.
5. Importing into a populated instance can overwrite keys or produce side effects per semantics.
6. Recovery objective: RDB-style backups can still lose changes between snapshots.

**A Redis cache should still have an independent source of truth** for data that cannot be lost. If the entire cache is lost, the system must have a rebuild strategy or accept the impact documented in its SLO.

### 10.6. Choosing features by failure mode

| Failure mode | HA | Persistence | Geo-replication | Rebuild/source of truth |
|---|---|---|---|---|
| Single node failure | Better protection, failover | Supplemental per config | Not required | Fallback on cache miss |
| Region outage | Insufficient | Insufficient | Can support multi-region architecture | DB/regional DR remains critical |
| Accidental flush of all keys | No | May persist the deletion | May propagate the deletion | **Independent backup + source of truth** |
| Cache instance replaced/deleted | Insufficient | Not a portable backup | Requires group runbook | Export/import or rebuild |
| App writes bad data | No | Persists bad data | Replicates bad data | Business validation and source fix |

**Sources:** https://learn.microsoft.com/azure/redis/plan-reliability-and-durability; https://learn.microsoft.com/azure/redis/how-to-persistence.

## 11. Choosing connectivity and topology in Azure

### 11.1. App Service → Redis Private Endpoint

~~~text
Client Browser
  → App Service (HTTP ingress)
      → App Service VNet Integration (outbound)
          → Private DNS resolution
              → Azure Managed Redis Private Endpoint
                  → TLS port 10000 + Entra authentication
~~~

**An inbound Private Endpoint on App Service** does not automatically grant App Service outbound access to a Redis Private Endpoint. Check the App Service plan, VNet Integration, DNS, and routing.

### 11.2. AKS → Redis OSS Cluster

In AKS, a Redis client inside a Pod needs:

- The right **Kubernetes service account / Workload Identity** if using Entra tokens.
- Cluster DNS/CoreDNS resolving the Redis FQDN to its private IP.
- NSG/UDR/NetworkPolicy permitting Redis port 10000 and client-discovered shard ports when using OSS cluster.
- A client supporting the Redis Cluster API and dynamic topology/`MOVED` redirects.
- Timeouts/reconnect/circuit breakers and key hash-slot compatibility.

A debug Pod might reach Redis while the production Pod is blocked by a NetworkPolicy. Test from the **exact Pod namespace and service account**, not merely from an admin VM.

### 11.3. Azure Container Apps / Functions / VMs and on-premises

Each runtime has distinct networking considerations:

| Runtime | What to verify |
|---|---|
| Container Apps | VNet environment/egress, private DNS, identity/token, scale concurrency |
| Azure Functions | Hosting plan supporting outbound VNet, cold starts, connection reuse, token refresh |
| VM | VNet/NSG/UDR, DNS, managed identity, and trust store |
| On-premises | VPN/ExpressRoute routing + conditional DNS forwarding + firewall |
| Hosted CI runner | Not inside your private VNet by default; use a self-hosted/private runner when testing private data plane |

### 11.4. Multiple private endpoints and hub-spoke DNS

If multiple applications across different VNets access the same Redis:

- Identify the owner of the **Private DNS zone**/links and resolvers.
- Verify routes to the private IP from each spoke/VPN network.
- Avoid conflicting A records that cause clients in spoke A to resolve an IP unroutable from spoke B.
- With custom DNS, configure conditional forwarding to a resolver capable of querying the Private DNS zone.
- Place Redis close to workloads to reduce network latency/egress and evaluate multi-region requirements.

**Never skip TLS hostname verification** or point Redis clients straight at the Private Endpoint IP just to avoid fixing DNS.

## 12. Controlled lab: creating and verifying Azure Managed Redis

The lab below **was not executed during the writing of this article**. If you practice it, you need an **authorized** Azure subscription/resource group, permissions to create Azure Managed Redis, budget alerts, and an isolated test environment. Azure Managed Redis is a billable resource and can incur noticeable charges even for learning. Never share a production cache with real data for testing.

### 12.1. Lab scenario

~~~text
Goal: Cache-aside for product catalog
Azure resource: Azure Managed Redis
Region: near test App Service/SQL
Tier: Balanced, initial supported size
Clustering policy: Enterprise (for simple standalone Python client lab)
Redis version: generally available supported version, e.g. Redis 7.4
High Availability: enabled if testing a production-like setup
Auth: Microsoft Entra ID
Network: private endpoint if runtime VNet is available
Data: synthetic product data only
~~~

**Why does the lab choose Enterprise policy?** So the example can use a simple Redis client (`redis.Redis`) without configuring cluster discovery. **This is not a recommendation for every production app to choose Enterprise**; if production needs maximum throughput and clients support Redis Cluster, benchmark OSS policy.

### 12.2. Creating the instance via Azure Portal

1. Sign in to the Azure Portal under your **lab subscription**.
2. Select **Create a resource → Azure Managed Redis**.
3. Choose the **Resource group**, valid cache name, available region, tier, and a size suitable for testing.
4. Under **Networking**, choose the public/private model matching your lab client connectivity. Prefer **Private Endpoint** if a VM/AKS/App Service runtime in a VNet is available.
5. Under **Advanced**, select a stable Redis version, **appropriate clustering policy**, required modules (if any), and HA/persistence if testing them specifically.
6. Confirm **Entra authentication**; do not enable access key auth merely to bypass identity setup.
7. Review **Review + Create**: check price, SKU preview status, region, networking, policy, and settings hard to change after creation.
8. Create the cache and monitor provisioning; record the cache **hostname, port, tier, policy, and resource ID**.
9. In the cache's **Authentication/Data access configuration**, grant Redis user permissions to the managed identity or developer principal authorized for test data access.

Portal labels may evolve; the constant rule is to document **tier, capacity, clustering, modules, network, auth, and HA** before provisioning.

### 12.3. Azure CLI for inventory only—do not mutate resources blindly

The CLI provides the `az redisenterprise` command group via its extension; the resource type may still appear as `Microsoft.Cache/redisEnterprise` even though the product is branded **Azure Managed Redis**.

~~~bash
az login

SUBSCRIPTION_ID="<lab-subscription-id>"
RG="rg-redis-lab"
CACHE_NAME="<lab-managed-redis-name>"

az account set --subscription "$SUBSCRIPTION_ID"
az account show --query "{id:id,name:name}" -o table

az redisenterprise list \
  --resource-group "$RG" \
  --output table

az redisenterprise show \
  --resource-group "$RG" \
  --name "$CACHE_NAME" \
  --output json
~~~

Replace `<...>` placeholders with your actual lab resources. With a recent Azure CLI version, check:

~~~bash
az version
az redisenterprise --help
az redisenterprise show --help
az redisenterprise database --help
~~~

**Do not run `az redisenterprise create` with unverified syntax or against an existing cache name.** Some CLI/API calls can **overwrite/recreate** a resource in ways that cause downtime. If your platform team uses Bicep/Terraform, provision resources through an approved pipeline rather than creating unrecorded Portal resources manually.

### 12.4. Verifying DNS and TCP from the client runtime

The cache hostname typically looks like:

~~~text
<cache-name>.<region>.redis.azure.net
~~~

From an authorized **VM/Pod/App Service runtime**:

~~~bash
nslookup "<cache-name>.<region>.redis.azure.net"

nc -vz "<cache-name>.<region>.redis.azure.net" 10000
~~~

If using OSS Cluster, also verify the shard ports after cluster discovery. `nc -vz` only confirms TCP reachability; **it does not prove TLS or Redis AUTH works**.

With Private Endpoint, verify DNS resolves to the private IP. If DNS returns a public IP while public network access is disabled, fix Private DNS/VNet integration/forwarding before modifying authentication.

### 12.5. Installing the Python SDK/client for the lab

In a Python 3 environment permitted to connect to Redis:

~~~bash
python -m pip install redis azure-identity
~~~

Set environment variables—**never** hardcode access tokens in source code:

~~~bash
export REDIS_HOST="<cache-name>.<region>.redis.azure.net"
export REDIS_PORT="10000"
export REDIS_PRINCIPAL_OBJECT_ID="<entra-principal-object-id>"
~~~

`REDIS_PRINCIPAL_OBJECT_ID` is the **object ID** of the identity added to the Redis authentication configuration, not necessarily the application (client) ID. A user or service principal can have multiple IDs; use the exact object ID accepted by Redis.

### 12.6. Python example: Entra auth and Redis commands

This is a **short smoke test** for the **Enterprise Cluster/Non-clustered** client model. It fetches an Entra token once at runtime, so it is **not suitable for holding connections open for hours** without adding token-refresh/re-auth logic.

~~~python
import json
import os

from azure.identity import DefaultAzureCredential
import redis

redis_host = os.environ["REDIS_HOST"]
redis_port = int(os.environ.get("REDIS_PORT", "10000"))
principal_oid = os.environ["REDIS_PRINCIPAL_OBJECT_ID"]

# DefaultAzureCredential uses developer auth locally or workload identity
# in an approved Azure runtime. Do not log the token.
credential = DefaultAzureCredential()
token = credential.get_token("https://redis.azure.com/.default").token

client = redis.Redis(
    host=redis_host,
    port=redis_port,
    username=principal_oid,
    password=token,
    ssl=True,
    ssl_cert_reqs="required",
    socket_connect_timeout=3,
    socket_timeout=3,
    decode_responses=True,
)

key = "lab:catalog:v1:product:123"
payload = json.dumps({
    "id": 123,
    "name": "Demo Headphones",
    "price": 1200000,
})

try:
    print("PING:", client.ping())
    client.set(name=key, value=payload, ex=60)
    print("GET:", client.get(key))
    print("TTL:", client.ttl(key))
    client.delete(key)  # Only remove the synthetic lab key.
finally:
    client.close()
~~~

**Before running:** practice only when the cache name is verified, the network path works, and the principal has Redis data-plane permissions. If the Entra token is valid but the principal was not added to Redis users, Redis may return **NOAUTH/WRONGPASS**. That is not necessarily a firewall failure.

### 12.7. Production: token refresh must be automatic

In production, a Java/.NET/Python/Node.js app may hold Redis clients open for days. Entra access tokens expire, so:

- Use the authentication helper/client library recommended for Azure Managed Redis.
- Refresh tokens **before expiry** (Microsoft guidance suggests a buffer of a few minutes) and issue a new **AUTH** on appropriate connections.
- With RESP2/RESP3 and Pub/Sub, verify whether dedicated connections are re-authenticated.
- Do not instantiate a new client per HTTP request; reuse connections/pools properly.
- Handle reconnects after Redis failover, DNS/network changes, and token refresh failures.
- Never log access tokens or passwords in Redis URLs, exceptions, or diagnostics.

The Python snippet in section 12.6 is **only for a short lab**. Do not copy it verbatim into a long-running worker expecting tokens to auto-refresh after 60 minutes.

### 12.8. OSS Cluster requires a cluster-aware client

Illustrative initialization for a **different topology** (do not run interchangeably against the same cache as the standalone example):

~~~python
from redis.cluster import RedisCluster

# credential and token reused from earlier lab initialization
cluster_client = RedisCluster(
    host=redis_host,
    port=redis_port,
    username=principal_oid,
    password=token,
    ssl=True,
    ssl_cert_reqs="required",
    decode_responses=True,
)

try:
    print(cluster_client.get("lab:catalog:v1:product:123"))
finally:
    cluster_client.close()
~~~

With RedisCluster, firewalls/DNS/networking must allow cluster discovery and shard connections. Multi-key commands require hash-slot compatibility; do not use a standalone client and call Redis "broken" when the service is operating as designed under OSS Cluster.

### 12.9. Lab pass criteria

| Criterion | Evidence |
|---|---|
| Correct Azure resource | Subscription/RG/name/tier/policy/region |
| Networking | Redis FQDN resolves to expected private IP or approved public path |
| TLS | Client validates certificate successfully |
| Entra ID | PING/SET/GET via registered principal object ID |
| TTL | `TTL` returns a value and key disappears upon expiry |
| Security | An unauthorized principal is rejected |
| Cost | Tags/owner/budget and cleanup plan are in place |
| Operational | Metrics/alerts are configured and read back |

**Never run `FLUSHALL`, `FLUSHDB`, or broad delete commands** on a shared cache to test TTL. Use a `lab:` prefix and delete only the test key.

## 13. Benchmarking to prove tier/policy selection

Specs like **"GB RAM", "vCPU ratio", or "price/hour"** are not enough to finalize a tier. Before production, benchmark with a realistic workload.

### 13.1. Minimum measurements required

- Dataset size, key count, value sizes, TTL distribution, and hot/cold access skew.
- Command mix: GET/SET/EXPIRE/HGET/HSET/ZADD/RedisJSON/Search.
- Target, peak, and burst commands/second.
- Concurrency, connections, pipelining, and batch/payload sizes.
- Cache hit ratio and p50/p95/p99 application latency.
- Redis Server Load/CPU, Used Memory Percentage, eviction rate, and connected clients.
- Network latency between app and cache region, Private Link/DNS overhead.
- Failover/reconnect, token refresh, cache miss surge, and backend degradation.

### 13.2. Illustrative test matrix

| Test | Dataset | Load | Example pass criteria |
|---|---|---|---|
| Baseline | 10% expected working set | 1× traffic | API p95 meets target; no errors |
| Production-size | 100% expected working set | 1× traffic | Redis memory/CPU retain headroom |
| Burst | Production-size | 3× for 10 minutes | No sustained timeouts/DB overload |
| Hot-key | One key serves 30% of reads | 2× | Hot shard/CPU remain within thresholds |
| Cold miss | Evict/invalidate selected test keys | 1× | DB fallback stays bounded, no stampede |
| Failover | HA enabled | 1× | Clients reconnect, business SLO within runbook |
| Token expiry | >60 minutes with Entra helper | 1× | Auto-refresh/re-auth without long disruption |
| Flash hot/cold | Dataset exceeds RAM share | 1×/2× | p99 tolerates cold read latency |

These figures are a **test design**, not an Azure-guaranteed SLA. If production traffic fluctuates, pick realistic peaks from actual measurements.

### 13.3. Redis benchmarking tools

`redis-benchmark` or custom load generators can measure synthetic command throughput. However, simple command benchmarks on a single VM do not represent **a real application with JSON serialization, database fallback, Entra tokens, network latency, request composition, and Redis Cluster sharding**.

Do not run heavy load benchmarks against an unapproved production cache; this can spike CPU, cause evictions, and impact real customers. Benchmark on an **isolated lab instance** with matching tier, size, and data patterns.

### 13.4. When benchmark results fall short

| Symptom | First areas to investigate |
|---|---|
| High CPU/Server Load, low memory | Compute tier, hot keys, O(N) commands, cluster topology |
| High Used Memory, low CPU | Memory size/tier, TTL/eviction, big keys/overhead |
| Many connection errors | Client reuse/pooling, token re-auth, connection cap, DNS/TLS |
| Low cache hit ratio | Key design, invalidation/TTL, working set mismatch |
| Poor p99 on Flash | Hot/cold skew and flash reads, not just average latency |
| Good Redis latency, slow API | App serialization, SQL misses, network, other dependencies |
| CROSSSLOT errors | OSS/Enterprise cluster policy and multi-key hash tags |

**Do not rush to change tiers** before isolating client or configuration issues. If moving from Memory → Compute/Flash tier families is necessary, check upgrade/change support: some choices are **fixed** after creation and require provisioning a new cache.

## 14. Observability: how do you know if Redis is helping or slowing things down?

A 95% cache hit ratio sounds great, yet if the 5% misses are the heaviest SQL queries, the backend may still crawl. Conversely, a 70% hit ratio can be effective if it eliminates most expensive queries.

### 14.1. Metric layers to correlate

| Layer | Metrics/logs | Decision to make |
|---|---|---|
| **Application** | Cache hit/miss, cache latency p95/p99, fallback rate | Is the cache reducing business latency? |
| **Redis service** | Used Memory Percentage, Server Load, CPU, connected clients | Are we constrained on RAM, compute, or connections? |
| **Commands** | GET/SET rate, operations/second, cache reads/writes | Has the traffic mix shifted? |
| **Memory** | Evicted keys, expired keys, memory trend | Are TTL/eviction/capacity reasonable? |
| **Networking** | Private DNS, TCP connection errors, egress, TLS errors | Do clients have proper routing and auth? |
| **Entra** | Authentication failures, token refresh/re-AUTH errors | Are tokens expiring or Redis principals missing? |
| **Backend** | SQL query count/CPU/p95/deadlocks | Is Redis actually offloading the authoritative store? |
| **Reliability** | Failover events, geo-replication health, data recovery tests | Do HA/DR meet RTO/RPO? |
| **FinOps** | Cache tier/units, Private Link, logs, DB compute savings | Does overall benefit justify the cost? |

Azure Managed Redis exposes Azure Monitor metrics and diagnostic settings; metric names/dimensions can vary by version/tier. **Do not assume every platform metric is p99.** For instance, platform cache latency may report **averages**, requiring application-side instrumentation for p95/p99.

### 14.2. Calculating hit ratio

For a workload with:

~~~text
Cache Hits   = 900,000
Cache Misses = 100,000
~~~

\[
\text{Hit ratio} = \frac{\text{Hits}}{\text{Hits}+\text{Misses}} \times 100
=90\%.
\]

Do not calculate `Cache Hits / All Redis commands`, because SET, EXPIRE, and other commands are not lookup hits/misses. Also distinguish hits in an **application-local L1 cache** from the Redis L2 cache if using two tiers.

### 14.3. Priority alerts

| Alert | Meaning | Response runbook |
|---|---|---|
| Sustained high **Used Memory Percentage** | Near capacity; risk of eviction/write failures | Inspect keys, TTLs, resize per sizing plan |
| High **Server Load/CPU** | Throughput/compute bottleneck | Hot keys/slow commands, Compute tier/shards |
| **Client Connections** near cap | Pool/reconnect storm | Reuse clients, reduce per-instance connections |
| Spike in **Evicted keys** | Memory pressure or mismatched policy | Check TTL/eviction and DB load from misses |
| Sudden spike in **Cache Misses** | Flush, TTL avalanche, or version key change | Check invalidation and SQL fallback |
| Spike in **Connection errors/NOAUTH** | DNS, TLS, Entra refresh, Redis user permissions | Troubleshoot layer by layer; do not blindly enable static keys |
| High **Application p99** | Tail latency hurting users | Separate Redis vs SQL vs network/serialization |
| **Geo replication unhealthy** | Multi-region state not syncing as expected | Check links/regions/network and DR runbook |

**Every alert must have an owner** and separate Redis issues from external causes. An operator could double Redis size while the real culprit is a database miss stampede or code opening a connection per request.

### 14.4. Azure diagnostics and sensitive data

Azure Portal allows configuring metrics/diagnostics export depending on feature support. Do not assume Azure Monitor/Log Analytics automatically captures full **per-command payload logs**. When enabling connection auditing or diagnostic streams:

- Choose storage/Log Analytics/Event Hub matching retention and cost goals.
- Restrict log access according to data classification.
- Never log `password`, Entra tokens, access keys, or JSON containing PII.
- Correlate application correlation IDs with Redis request/operation metrics.
- Evaluate sampling, high-cardinality labels, and ingestion billing.

### 14.5. Synthetic tests

A synthetic probe **uses dedicated test keys only**:

~~~text
SET health:catalog-test random-value EX 30
GET health:catalog-test
DEL health:catalog-test
~~~

This proves Redis can process commands from an authorized client. However, **successful PING/GET does not prove cache hit ratios are healthy or SQL is healthy**. Supplement with synthetic business flows, token-refresh tests, and app failover checks.

## 15. Migration from Azure Cache for Redis or self-hosted Redis

Projects already running Redis should not merely swap a DNS endpoint and declare migration complete. Azure Managed Redis differs in **tiers, cluster policies, auth, ports, command/module compatibility, and network topology**.

### 15.1. Surveying the source

Before migrating, record:

1. Is the source Azure Cache for Redis Basic/Standard/Premium/Enterprise or self-managed Redis?
2. Redis version, modules, blocked/used commands, Lua scripts, clustering, and key hash tags.
3. Data size, connected clients, hot keys, TTL distribution, and eviction policy.
4. Current authentication: access key/password/ACL or Entra?
5. Hostnames/ports/network paths; which VMs, AKS, Functions, or App Services connect?
6. Are there **Pub/Sub**, queues/streams, or session data that cannot easily be rebuilt?
7. RPO/RTO, expected downtime, and acceptable cold-cache warming time.
8. Rollback plan and how key consistency will be verified.

### 15.2. Do not assume "100% Redis drop-in compatibility"

- **OSS Cluster** requires cluster-aware clients and multi-key hash-slot design.
- **Enterprise Cluster** uses a proxy and still enforces multi-key constraints.
- **Non-clustered** has size limits.
- Certain management commands are blocked; module feature sets differ.
- Port `10000`, TLS, and client auth differ from legacy caches.
- Entra principal authorization and token refresh must be added to clients.
- Public/Private Endpoint DNS differs from legacy configurations.

If code uses `KEYS *`, multi-key scripts, or self-managed Redis CLUSTER commands, verify allowed commands before picking a clustering policy. For workloads using RedisJSON/RediSearch, module compatibility may dictate tier and policy up front.

### 15.3. Choosing a cutover approach

| Approach | When to use | Risks |
|---|---|---|
| **Rebuild from SQL/source** | Pure cache-aside where cached data is regenerable | Cold-start/DB spike and warm-up time |
| **Export/Import** | Need to move a dataset snapshot with a planned downtime window | Stale snapshot, format/version/module compatibility |
| **Azure-supported migration tooling** | Supported migration path exists for source tier and features | Prerequisites, preview status, and endpoint updates vary by tier |
| **Controlled dual-write / shadow-read** | Need minimal downtime or compatibility verification | Data drift, duplicate side effects, complexity |

**Never run dual-write if the application lacks an idempotency/consistency plan.** When Redis is purely a cache, **creating a new cache and warming/rebuilding** is often safer than attempting to migrate every key.

### 15.4. Sample migration plan

~~~mermaid
flowchart TD
    INVENTORY[Inventory clients/keys/modules/commands] --> PLAN[Choose tier size cluster policy auth network]
    PLAN --> BUILD[Provision Azure Managed Redis target]
    BUILD --> TEST[Validate TLS/Entra/network/client cluster commands]
    TEST --> WARM[Warm target or import approved snapshot]
    WARM --> SHADOW[Compare values/latency and verify TTL]
    SHADOW --> CUT[Cut over one app/traffic cohort]
    CUT --> OBS[Observe SLO, misses, DB load, errors]
    OBS --> DEC{Acceptable?}
    DEC -->|No| ROLL[Rollback endpoint with reviewed plan]
    DEC -->|Yes| ALL[Promote remaining clients]
    ALL --> RETIRE[Retire old cache after retention/approval]
~~~

### 15.5. Cutover must account for TTL/invalidation

Old and new caches can hold diverging values if invalidations go to only one side or source SQL changes during import. You need:

- An **event/version key** or new cache namespace if schema separation is needed.
- Designed invalidation/write handling during any dual-read/write phase.
- Not judging data correctness solely by key count.
- For session storage, verifying user experience during endpoint switch (logouts, token TTL, cookie behavior).
- If using Redis Streams/PubSub for business messaging, verifying replay/consumer-group semantics; avoid turning critical events into easily lost keys.

### 15.6. Migration under the Azure Cache for Redis lifecycle

Per current Azure guidance, organizations should plan migration to **Azure Managed Redis** ahead of legacy Azure Cache for Redis retirement dates. Migration tools may be in **GA or preview** depending on the source tier; check support details, data handling, downtime, and SKU availability before committing.

**Sources:** https://learn.microsoft.com/azure/azure-cache-for-redis/retirement-faq; https://learn.microsoft.com/azure/redis/overview.

## 16. Decision matrix: choosing tier, clustering, reliability, and security

A Redis purchase decision should be captured as an **Architecture Decision Record** (ADR), not just a Portal screenshot.

### 16.1. Workload matrix

| Workload | Preferred tier to benchmark | Cluster policy | Modules needed? | Reliability |
|---|---|---|---|---|
| Medium Catalog API, 5–20 GB cache | **Balanced** | OSS if client is cluster-aware; Enterprise if single endpoint needed | No | HA, TTL + invalidation, SQL fallback |
| 100 GB feature flag dataset, light reads | **Memory Optimized** | OSS/Enterprise per client | No | HA, cache rebuild |
| High-throughput rate-limit counter | **Compute Optimized** | OSS if key distribution is balanced | No | HA, atomic semantics, defined fail-open/closed |
| 1 TB dataset, 10% hot, mostly GET | **Flash Optimized** | Flash-supported policy | RedisJSON if needed, not RediSearch | HA + cold-read benchmark, non-geo DR |
| Search/vector catalog | **Balanced/Compute/Memory** per index/CPU | **Enterprise** or Non-clustered within limits | **RediSearch** | HA, index memory, reindex/rebuild |
| Small sessions, legacy nonclustered client | **Balanced** | Enterprise/Non-clustered per compatibility | No | HA; evaluate token/session loss |
| Multi-region active cache | Compatible in-memory tier | Uniform policy across regions | Supported modules only | HA + active geo, app routing, no persistence |

This table is a **starting point**, not a substitute for benchmarking. Redis sizes/SKUs and feature support evolve; verify specific SKUs, regions, and pricing at deployment time.

### 16.2. Condensed decision tree

~~~mermaid
flowchart TD
    START[App is slow or needs caching] --> NEED{Working set and repeat reads exist?}
    NEED -->|No| SKIP[Optimize DB/query first, Redis may not help]
    NEED -->|Yes| SIZE{Very large dataset, clear hot/cold?}
    SIZE -->|Yes| FLASH{Accept cold latency and feature limits?}
    FLASH -->|Yes| FLASH_T[Benchmark Flash Optimized]
    FLASH -->|No| MEM_T[Benchmark in-memory tier]
    SIZE -->|No| THROUGHPUT{CPU/ops bound or memory bound?}
    THROUGHPUT -->|CPU/ops bound| COMPUTE[Compute Optimized]
    THROUGHPUT -->|Memory bound| MEMORY[Memory Optimized]
    THROUGHPUT -->|Unclear| BAL[Start Balanced and benchmark]
    FLASH_T --> POLICY[Select cluster policy/modules]
    MEM_T --> POLICY
    COMPUTE --> POLICY
    MEMORY --> POLICY
    BAL --> POLICY
    POLICY --> SEC[Entra + TLS + network]
    SEC --> HA[HA + persistence/geo/rebuild choice]
    HA --> BENCH[Load test + cost + approval]
~~~

### 16.3. Sample ADR

~~~yaml
# Example ADR data in documentation, not an Azure Resource Manager schema.
decision: "Redis for Product Catalog API"
authoritativeStore: "Azure SQL Database"
dataClassification: "Internal"
datasetMeasuredGb: 12
peakOpsPerSecond: 35000
workingSetHotRatio: 0.80
dataTierCandidate: "Balanced"
clusterPolicyCandidate: "OSS Cluster"
redisVersionCandidate: "Supported GA version"
modules: []
highAvailability: true
network: "Private Endpoint, public disabled"
authentication: "Microsoft Entra managed identity"
ttlSeconds: 300
evictionPolicy: "allkeys-lru if all keys rebuildable"
fallback: "SQL with bounded concurrency + circuit breaker"
monitoring:
  - cacheHitRatio
  - redisUsedMemoryPercentage
  - serverLoad
  - connectionErrors
rollback: "Switch back to prior cache or SQL fallback with SLO guardrails"
decisionGate: "Load test and security review"
~~~

**Note:** `dataTierCandidate` or `clusterPolicyCandidate` in an ADR does not provision Azure resources. When using RedisJSON/RediSearch, adjust modules/policy for compatibility before provisioning.

### 16.4. What is fixed vs changeable

| Decision | Flexibility |
|---|---|
| In-memory tier family vs Flash | Usually **hard/impossible to change in-place**, may require a new cache |
| OSS/Enterprise clustering policy | Usually **cannot change after creation** |
| Non-clustered → clustered | May support one-way upgrade under certain conditions |
| Redis modules on 7.4 | Typically must be selected at creation |
| HA | Can be enabled later, but should not be assumed reversible |
| Capacity size | Scale up and scale down have constraints |
| Public access/Private Endpoint | Adjustable per networking/change policy |
| Entra principals/diagnostics | Manageable throughout lifecycle |
| Persistence/active geo | Subject to restrictions, **mutually exclusive on the same cache** |

This is why **tier family, clustering, and modules** must be reviewed before creating a production instance.

## 17. Troubleshooting: slow Redis, dropped connections, or Redis Cluster errors

When an API slows down after adding Redis, separate **DNS/network**, **TLS/authentication**, **client topology**, **memory/CPU**, **cache logic**, and **database fallback**. Never disable TLS or enable access key authentication just to make errors go away.

### 17.1. Common errors table

| Symptom | Possible cause | Action to take |
|---|---|---|
| `Name or service not known` | Wrong Redis FQDN or Private DNS fails to resolve | Check hostname/region, private zone/VNet links/resolver |
| DNS returns public IP when private intended | App lacks VNet Integration or Private DNS link | Probe from actual runtime; fix network/DNS |
| TCP timeout on `:10000` | NSG/firewall/route, pending PE, public disabled while client uses public path | Check approved PE, routes, and TCP |
| TLS certificate hostname mismatch | Connecting by IP/privatelink alias or outdated CA trust | Use standard FQDN, update trust store |
| `NOAUTH`/`WRONGPASS` | Wrong Entra token audience/expired, object ID not added to Redis users | Check token scope/identity/data-plane grants |
| Connection works for 1 hour then drops | Entra token not refreshed/re-AUTHed | Use helper supporting long-lived auth |
| `CROSSSLOT Keys in request don't hash to same slot` | Multi-key command on OSS/Enterprise cluster | Design hash tags or revise command/data model |
| `MOVED`/`ASK` unhandled by client | Using standalone client against OSS Cluster | Use RedisCluster/cluster-aware library |
| `ERR unknown command`/blocked command | Managed service blocks certain commands or module not enabled | Check supported commands/modules |
| `OOM command not allowed` | Cache full and eviction policy/keys prevent eviction | Check Used Memory, TTL, eviction, resize |
| Evictions rise after release | Big keys, memory pressure, TTL/working set shifted | Measure key count/size and capacity |
| Hit ratio drops | New key prefix/schema, TTL too short, broken invalidation | Inspect key design and lookup patterns |
| High Server Load | Hot key/CPU-heavy command/too many ops | Optimize commands, shard keys, Compute tier |
| Sharp p99 spike on Flash | Cold values read from flash, uniform access | Benchmark hot/cold, re-evaluate tier |
| Redis healthy but SQL overloaded | Cache miss avalanche or unbounded fallback | Single-flight, TTL jitter, bounded SQL |
| 429/403 on Azure management API | Azure RBAC/Policy/resource provider | Separate control plane from Redis data plane |
| Failover hangs app | Client fails to reconnect, stale DNS/shard topology | Backoff, reconnect, token refresh, circuit breaker |

### 17.2. Step-by-step diagnostic runbook

**Step 1 — Verify resource:** exact Azure subscription, resource group, cache name, tier, cluster policy, Redis version, and private/public network settings.

**Step 2 — DNS:** from the failing runtime, resolve **`<name>.<region>.redis.azure.net`**. If private-only, it must resolve to the appropriate private endpoint IP.

**Step 3 — TCP:** check port 10000; with OSS Cluster, allow clients to reach shard ports after discovery.

**Step 4 — TLS:** certificate chain, hostname verification, supported TLS version; never use IP instead of FQDN.

**Step 5 — Identity:** verify Entra token scope `https://redis.azure.com/.default`, principal **object ID**, and Redis user/data access policy; for long-lived connections, check re-AUTH.

**Step 6 — Client topology:** does RedisCluster vs single-endpoint client match OSS/Enterprise/Non-clustered? Are there CROSSSLOT or blocked commands?

**Step 7 — Runtime load:** memory%, Server Load, CPU, connections, evictions, hits/misses, hot keys, and p99.

**Step 8 — Business fallback:** are SQL/database CPU, cache stampede, latency, and data errors the actual root cause?

**Step 9 — Recovery:** fix the exact layer, validate with synthetic tests, monitor SLOs, and record incident/source-of-truth findings.

### 17.3. Token refresh scenario

~~~text
09:00  App obtains Entra token and connects to Redis.
09:05  GET/SET requests succeed.
10:05  Token is expired; client keeps old token.
10:07  Authentication begins to fail on re-auth/new connections.
10:10  Team incorrectly regenerates Redis access key.
~~~

The fix is controlled **token refresh/re-AUTH**, not creating a static password as a shortcut. If the client uses Redis Pub/Sub/RESP2 with dedicated connections, verify the helper supports re-auth across all relevant connections.

### 17.4. Hot key scenario

An API has 10,000 products, yet 60% of requests target `catalog:product:hot-item`. Cluster-wide Redis memory is only 30% used, yet one shard hits high CPU and poor p99 latency. Doubling Memory Optimized size may **not** improve key distribution.

Remediation:

- Identify the hot key, request distribution, and command complexity.
- Use a short-lived near-cache/L1 cache if staleness permits.
- Optimize serialization/value size and connection pooling.
- Consider shard-friendly key design and client batching.
- Benchmark Compute Optimized/cluster topology rather than simply adding memory.

### 17.5. Overfull cache scenario

The cache defaults to `volatile-lru`, and many keys lack a TTL so they are ineligible for eviction. Used Memory stays high, and SET starts failing even though API GETs sometimes still succeed. Proper fix:

- Identify keys without TTLs and why they exist.
- Add business-appropriate expiration to rebuildable keys.
- If **all** data is evictable cache data, consider `allkeys-lru` after review.
- Increase capacity with headroom if the real working set is larger.
- Set alerts; never run `FLUSHALL` in production to free RAM.

## 18. FinOps: does Redis actually save money?

A financially sound decision compares **total cost without caching** against **Redis + app + database + network + operations**, not just the hourly Redis SKU rate.

### 18.1. Cost components

| Component | Examples |
|---|---|
| **Managed Redis tier/size/HA** | Provisioned cache cost, CPU/RAM capacity |
| **Active geo-replication** | Multiple Redis instances across regions, network/DR |
| **Persistence/backup/export** | Disk/storage, Export Blob, automation and operations |
| **Private Endpoint/Private DNS/Resolver** | Endpoints, DNS, peering, VPN/Firewall/egress |
| **Application client compute** | Serialization CPU, networking, retries, fallback |
| **Backend database** | SQL CPU/IO/throughput reduced on hits or spiked on misses |
| **Observability** | Azure Monitor, Log Analytics, App Insights ingestion/retention |
| **CI/DR/test** | Staging instances, load tests, regional backups, runbooks |

### 18.2. Benefit analysis example

Suppose before caching:

~~~text
API requests:       5,000,000/day
Read-heavy share:   80%
SQL reads from API: 4,000,000/day
Expected cache hit ratio: 85%
~~~

If requests are uniform and cache coverage is accurate:

\[
\text{SQL reads avoided} \approx 4{,}000{,}000 \times 0.85
=3{,}400{,}000 \text{ reads/day}.
\]

Remaining SQL reads from that portion are roughly 600,000/day, but this is a **request-count metric**, not direct **dollar savings**. If the SQL database still needs the same vCore/SKU for write peaks, the SQL bill may not drop proportionally. On the other hand, Redis improves latency/SLO even when DB costs do not fall immediately.

A business case should:

1. Measure SQL CPU/IO p95 before and after.
2. Run load tests to confirm hit ratio and command rate.
3. Determine whether **SQL can be safely right-sized**.
4. Account for Redis HA, networking, logs, and staging resources.
5. Assess the cost of outages, session loss, and production incidents.
6. Project 6–12 month growth and scaling paths.

### 18.3. Which tier is "cheapest"?

No single tier is cheapest for all workloads:

- Memory Optimized can save money when needing **high RAM / moderate CPU**.
- Compute Optimized can be cost-effective for high throughput on a small dataset.
- Balanced fits well when extreme resource ratios are unnecessary.
- Flash Optimized can lower costs on large hot/cold datasets, provided latency/feature trade-offs are acceptable.

**Pricing and SKU availability vary** by region, currency, date, reservations, and contract. Use the Azure pricing calculator and Cost Management instead of hardcoding USD figures in docs.

### 18.4. Reservations and commitments

Azure may offer reservation/commitment options for Azure Managed Redis under current terms. Consider them only after confirming **tier, region, baseline capacity, and steady usage horizon**. Do not sign long-term commitments before finalizing cluster policy/modules or while tier-family changes remain likely.

### 18.5. Hidden quality costs

- Too-short TTL → DB spikes → requiring a larger SQL SKU.
- Excessive logging with key/value contents → ingestion fees and PII risk.
- Non-HA Redis configuration → downtime and lost sessions.
- Shared Redis across teams → one team's hot key slows down another workload.
- Flash mismatched to access pattern → higher p99, forcing migration to in-memory.
- Scaling Redis without shrinking database footprint → paying twice for two systems.

**Budget alerts do not automatically stop billing.** Labs need an explicit resource owner/TTL and cleanup plan.

## 19. Case study: e-commerce promotional campaign

**Hypothetical scenario:** The Commerce team runs Azure App Service for the Catalog API, Azure SQL Database for merchandise data, and Azure Container Apps for a price-update worker. During peak hours:

- 40,000 GET/second reading product data.
- Dataset is 12 GB payload/metadata serialized, expected to grow 50% over the year.
- Hot set accounts for roughly 70% of total data.
- Product descriptions tolerate staleness of up to a few minutes.
- Promotional prices require near-real-time updates (10-second staleness budget).
- Inventory and checkout must check SQL transactions, never trusting the cache to commit.
- Java clients use Lettuce and support Redis Cluster.
- Private VNet, Entra managed identity, and HA are production requirements.

### 19.1. Reference architecture

~~~mermaid
flowchart TB
    BUYER[Buyer web/mobile] --> API[Azure App Service - Catalog API]
    API -->|GET catalog keys| CACHE[(Azure Managed Redis)]
    API -->|Cache miss/fresh consistency| SQL[(Azure SQL)]
    API -->|Checkout transaction| SQL
    WORKER[Price update worker] -->|Commit price change| SQL
    WORKER -->|Invalidate related keys| CACHE
    CACHE -. Private Link/TLS/Entra .-> API
    MON[Azure Monitor/App Insights] -. Observe .-> CACHE
    MON -. Observe .-> API
    MON -. Observe .-> SQL
~~~

### 19.2. Initial selections

| Decision | Choice to benchmark | Rationale |
|---|---|---|
| Tier | **Balanced** or **Compute Optimized** | 40k GET/s; need to measure Server Load/throughput |
| Initial size | Measured dataset + 50% growth + headroom | Do not extrapolate blindly from 12 GB raw payload |
| Cluster policy | **OSS Cluster** | Lettuce RedisClusterClient supports it and GETs target individual keys |
| Modules | None needed | Catalog lookup by product ID does not need full-text search |
| Auth | Managed identity + Entra token auto-refresh | Avoids static access keys |
| Network | Private Endpoint + public disabled | API accesses strictly via VNet |
| Availability | HA/zone redundancy if supported by region | Production SLO and failover |
| TTL descriptions | 180–300 seconds + jitter | Tolerates short staleness and prevents avalanche |
| TTL prices | 5–10 seconds or post-commit invalidation | Needs high freshness; checkout confirms via SQL |
| Eviction | Evaluate `allkeys-lru` if all keys are rebuildable | Reduces OOM risk; requires review |
| Degradation | Bounded SQL fallback + circuit breaker | Prevents cache outage from crashing SQL |
| DR | Rebuild cache from SQL with prewarming plan | Cache is derived state; geo may be unnecessary |

**Do not pick Flash** when the working set fits comfortably in memory and stable latency is required at tens of thousands of requests/s; Flash mainly benefits huge datasets with a pronounced hot/cold split.

### 19.3. Capacity estimate

Suppose after measurement, the actual cached dataset (including metadata) is 18 GB; 50% growth brings it to 27 GB. To retain 25% operational headroom:

\[
\text{Effective memory target}
= \frac{27}{0.75}=36\ \text{GB}.
\]

Choose an Azure SKU with **effective usable capacity ≥36 GB** after accounting for reserved memory and metric semantics, then load-test at 40k–80k ops/s with production networking and auth. Do not assume a "36 GB" SKU exists just from the formula; pick from actual Azure-offered sizes.

### 19.4. On price update

~~~mermaid
sequenceDiagram
    participant W as Price Worker
    participant SQL as Azure SQL
    participant R as Managed Redis
    participant API as Catalog API
    W->>SQL: UPDATE price + COMMIT
    SQL-->>W: Success
    W->>R: DEL price:product:123 / update cache version
    Note over W: Retry invalidation via outbox if Redis fails
    API->>R: GET price:product:123
    alt Miss
       R-->>API: null
       API->>SQL: SELECT current price
       SQL-->>API: Committed price
       API->>R: SET value EX short TTL
    else Hit
       R-->>API: Cached price
    end
~~~

For pricing and inventory, define an **acceptable stale window**. If a promo code takes effect at an exact timestamp, checkout/services are responsible for checking authoritative data; the cache can power fast display but must not serve as the final authority for payment.

### 19.5. Incident: Redis outage causes SQL stampede

During a Redis failover, the app experienced timeouts; every request immediately fell back to SQL and drove 100% CPU/IO. Remediation:

1. Configure bounded timeouts/reconnects and a circuit breaker on the Redis client.
2. Cap concurrent SQL fallback queries; return 503 with retry-after rather than overloading the whole system.
3. Re-warm hot keys via a background worker.
4. Apply TTL jitter/single-flight to flatten herd behavior on recovery.
5. Monitor application hit ratio, SQL dependency rate, Redis load, and 5xx errors.
6. Re-test failover with a production-sized dataset and record actual recovery time.

### 19.6. When to change tiers?

If Balanced has memory headroom yet Server Load/CPU runs high and p99 degrades, benchmark **Compute Optimized** with the same workload. However, changing tier families should not be assumed in-place: verify features, pricing, new instance provisioning, and migration steps. If the bottleneck is a hot key, changing tiers may only mask symptoms temporarily without fixing the root cause.

**Case conclusion:** Redis reduces queries and improves latency; **TTL/invalidation design, cluster awareness, fallback limits, and database transactions** determine business correctness—not cache size.

## 20. Exercise: choosing Azure Managed Redis for three systems

**Prompt:** You are a cloud architect tasked with selecting a Redis solution for three applications running on Azure. Do not create production resources; complete this exercise on paper/ADR or in an authorized **lab subscription**.

### 20.1. Hypothetical workloads

| Attribute | System A — Product Catalog | System B — Analytics Hot/Cold | System C — Realtime Counter |
|---|---|---|---|
| Dataset | 15 GB current; 50% growth | 900 GB data, 12% very hot | 5 GB |
| Load | 20,000 GET/s | 2,000 queries/s, mostly reads | 100,000 INCR/s |
| Client | Java Lettuce cluster-aware | Python redis-py, cluster-aware client required or replaceable | .NET StackExchange.Redis |
| Latency | Low, consistent p95 | Tolerates slower cold reads | Very low p99 |
| Features | GET/SET/EXPIRE | JSON documents + potential field search | Atomic increments, TTL |
| Recoverability | Rebuildable from SQL | Export/rebuild possible but slow | Quota accuracy must not be lost |
| Network | Private VNet | Private VNet | Multi-region APIs |

### 20.2. Analysis tasks

1. **System A:** choose Balanced or Compute Optimized as baseline? When would you consider Memory Optimized?
2. Compute the effective capacity target if A has a 15 GB measured dataset, 50% growth, and requires 25% headroom.
3. **System B:** is Flash Optimized suitable if RediSearch is required? Explain the feature incompatibility and propose an alternative.
4. If B only uses GET/SET with a 12% hot set, design a benchmark to decide on Flash.
5. **System C:** choose Compute Optimized or Memory Optimized? Why does throughput matter more than raw GB?
6. If C serves as a rate limiter, how do you avoid lost/evicted counter keys letting clients exceed quotas?
7. **Cluster policy:** if Java uses Lettuce `RedisClusterClient`, why can OSS Cluster work well? What should you choose if using a non-cluster-aware client?
8. Write two Redis keys using a **hash tag** so an atomic multi-key command can map to the same slot.
9. Contrast **RedisJSON** and **RediSearch**, and identify which module is needed when only doing GET object by ID.
10. Draw the **App Service → outbound VNet → Private DNS → Redis Private Endpoint** flow. Why is an inbound app private endpoint insufficient?
11. Design Microsoft Entra authentication for a managed identity; specify token scope, username, and refresh behavior.
12. Why does Azure Contributor not automatically grant GET/SET on the cache?
13. Choose HA/persistence/geo-replication for A/B/C per business RPO/RTO; identify which features cannot be combined.
14. Design TTL/invalidation for product descriptions (few minutes stale) and stock (needs transactional accuracy).
15. Calculate cache hit ratio given 1,800,000 hits and 200,000 misses.
16. Write a load test plan covering near-full data, 1×/3× traffic, failover, token expiry, and Redis unavailable.
17. List metrics that distinguish insufficient RAM from insufficient compute.
18. If Redis Cluster returns `CROSSSLOT`, explain how to fix it and the risk of putting every key under one hash tag.
19. Outline a migration path from legacy Azure Cache for Redis Basic to Azure Managed Redis when clients still use port 6380.
20. Draft an ADR covering tier, size, clustering, modules, auth, network, HA, fallback, monitoring, and cost owner.

### 20.3. Guided solutions

**Question 2 — capacity:**

\[
\text{Dataset after growth}=15 \times 1.5=22.5\ \text{GB}.
\]

\[
\text{Effective memory target}=\frac{22.5}{0.75}=30\ \text{GB}.
\]

Compare the **30 GB effective memory** target against actual SKUs, reserved memory, HA memory metrics, key overhead, and benchmarks; do not blindly select a cache labeled 30 GB.

**Question 3 — Flash + RediSearch:** per current compatibility, Flash Optimized does not support RediSearch. If search is a primary requirement, choose an **in-memory tier + Enterprise/Non-clustered policy** or offload the search index to a dedicated service (such as Azure AI Search), keeping Flash for key–value caching if beneficial.

**Question 5 — counter:** little RAM combined with very high INCR/s is typically **compute/throughput-bound**. Benchmark Compute Optimized/OSS Cluster with realistic key distribution; if all updates hit one key, fix the data model/algorithm or accept single-shard limits rather than simply buying more CPU.

**Question 8 — hash tag:**

~~~text
cart:{customer-42}:items
cart:{customer-42}:total
~~~

The shared substring inside curly braces keeps both keys in the same hash slot under OSS Cluster. Never use one global hash tag across all customers, as that unbalances shards.

**Question 11 — Entra:** create a managed identity and add its principal object ID to Redis users, request scope `https://redis.azure.com/.default`, connect over TLS with username=object ID and password=access token, and implement re-auth/token refresh before expiry.

**Question 15 — hit ratio:**

\[
\frac{1{,}800{,}000}{1{,}800{,}000+200{,}000}
=90\%.
\]

**Question 19 — migration:** provision the target AMR with chosen tier/policy/modules, update/test client library/cluster topology, port 10000, Entra auth, Private DNS, and data; warm/rebuild or use supported migration tooling, cut over clients with a rollback plan, and retire the legacy cache only once metrics and business SLOs stabilize.

### 20.4. Passing criteria

A strong answer does not just state "Balanced" or "Compute Optimized". It includes:

- Assumptions on **dataset/working set, command mix, ops/s, latency, and connection count**.
- Justification for compatible **tier, initial size, cluster policy, and modules**.
- **Private networking/TLS/Entra principal** decisions.
- HA/DR, persistence, or geo choices tied to failure modes, recognizing incompatible combinations.
- Sound cache logic: TTL, invalidation, eviction, fallback, and source of truth.
- Benchmark/metrics set proving performance.
- Cost, migration risks, cleanup plan, and named owner.

## 21. Production selection and deployment checklist

### 21.1. Before creating the Redis instance

- [ ] Confirm the use case is cache/session/coordination rather than needing a database or message broker.
- [ ] Establish an authoritative data store and design fallback/recovery when the cache is empty.
- [ ] Measure dataset size, key counts/value sizes, hot working set, and growth.
- [ ] Measure peak ops/s, p95/p99 latency, connection limits, and client concurrency.
- [ ] Select **Memory/Balanced/Compute/Flash** by RAM/CPU/hot–cold profile, not intuition.
- [ ] Select **OSS/Enterprise/Non-clustered** by client library, multi-key ops, and modules.
- [ ] Confirm Redis version and **module set at creation time**, especially RediSearch/Flash restrictions.
- [ ] Verify region/SKU/size/preview/support status and current pricing.
- [ ] Enable **HA** for production; review zone distribution and reliability targets.
- [ ] Decide between persistence, geo-replication, or rebuild/Export; do not assume all can be enabled together.
- [ ] Design Private Endpoint/DNS/VNet networking and public access policy.
- [ ] Choose Entra managed identity, Redis user permissions, TLS, and a token-refresh library.
- [ ] Define key naming, TTL, eviction, invalidation, and sensitive-data policies.
- [ ] Assign an owner, IaC/CI/CD change controls, alerts, and Cost Management budget.

### 21.2. After creation / before production traffic

- [ ] Read back tier/size/policy/modules of the **actual resource**, not just the planned manifest.
- [ ] Private Endpoint connection Approved; DNS from runtime resolves to the private IP.
- [ ] TLS hostname/CA verification succeeds; TCP 10000 and shard ports (if OSS) are allowed.
- [ ] Managed identity has Redis data-plane permissions, not just Azure RBAC.
- [ ] Token re-auth succeeds across multiple expiry cycles on long-lived connections.
- [ ] Test GET/SET/TTL/DEL on synthetic keys and verify command compatibility.
- [ ] Benchmark near-production working set and 1×/peak/burst throughput.
- [ ] Test multi-key/CROSSSLOT if using OSS, or RediSearch if required as a module.
- [ ] Verify HA failover/reconnect and SQL fallback/circuit breaker behavior.
- [ ] Confirm alerts on Used Memory/Server Load/evictions/connections/hit ratio/p99 work.
- [ ] Prepare a cache warm-up plan to prevent stampedes/DB overload during rollouts.
- [ ] Obtain sign-off from security, app owner, SRE, and FinOps.

### 21.3. During operations

- [ ] Track hit/miss, memory%, Server Load/CPU, connections, and p95/p99 latency per app.
- [ ] Inspect hot keys/big keys and command patterns before scaling.
- [ ] Monitor actual database CPU/IO and throughput savings.
- [ ] Keep Redis clients, CA trust stores, and Entra SDKs updated and verify token refresh.
- [ ] Audit changes to data access policies and public access settings.
- [ ] Review Redis metrics/diagnostics retention and prevent PII logging.
- [ ] Rehearse failover, outage, cache rebuild, and import/export as needed.
- [ ] Maintain a scale/migration plan if the dataset outgrows memory or the tier family.
- [ ] Periodically review reservations/pricing and orphaned resources.

### 21.4. During an incident

- [ ] Identify exact subscription/RG/cache, tenant/region, policy, and affected runtimes.
- [ ] Check DNS/TCP/TLS before altering Redis passwords or tiers.
- [ ] Check Entra token expiry/object ID/Redis users on auth failures.
- [ ] Check CROSSSLOT/MOVED, client mode, and shard reachability.
- [ ] Correlate Used Memory/evictions and Server Load/CPU before scaling.
- [ ] During a Redis outage, throttle SQL fallback to avoid cascading failure.
- [ ] Never run FLUSHALL/FLUSHDB in production to "clean up" data.
- [ ] Preserve evidence, test recovery/rollback, and verify business SLOs after changes.

## 22. Lab cleanup and resource lifecycle management

Azure Managed Redis and Private Endpoints continue incurring charges after you stop running code. Conversely, deleting the wrong production cache immediately wipes sessions and temporary data across applications; a shared Redis instance may serve multiple teams.

### 22.1. Inventory (read-only)

~~~bash
az account show --query "{id:id,name:name}" -o table

az redisenterprise list \
  --resource-group "$RG" \
  --output table

az redisenterprise show \
  --resource-group "$RG" \
  --name "$CACHE_NAME" \
  --output json

az resource list \
  --resource-group "$RG" \
  --output table
~~~

Confirm `RG` and `CACHE_NAME` explicitly—never rely on names resembling production. If the cache uses active geo-replication, verify group membership/ownership and follow the corresponding unlink/delete runbook before any teardown action.

### 22.2. Cleanup procedure

1. Verify **this is an isolated lab instance**, not shared with any product or application.
2. Check whether any sessions, jobs, streams, or keys must be retained.
3. If data must be saved, run Export/backup per policy and verify the artifact and storage permissions.
4. Confirm apps/workers/CI are no longer connecting or have migrated to another cache.
5. Inventory Private Endpoints, DNS links, subnets, logs, Key Vault references, and network dependencies.
6. Delete the resource or resource group only when 100% confirmed as lab-owned and approved.
7. Check for lingering charges (Redis, Private Link, DNS, VPN/Firewall, logs, storage artifacts).

**Never clean up a lab using `FLUSHALL`** on a cache without verified ownership. A Redis data-plane flush and Azure resource deletion are two distinct actions, both capable of destroying data.

Commands **for reference only, commented out**:

~~~bash
# DO NOT execute directly:
# az redisenterprise delete \
#   --resource-group "$RG" \
#   --name "$CACHE_NAME" \
#   --yes

# Do not delete the resource group if shared DB/VNet/Private DNS/Key Vault remain:
# az group delete --name "$RG" --yes
~~~

If current preview/CLI versions introduce different options, check `az redisenterprise delete --help` first. **Do not blindly retry delete calls if the API returns an unknown state**, especially with geo-replication groups or caches holding non-rebuildable data.

## 23. References and currency notes

Tier configurations, versions, pricing, preview SKUs, and supportability can change. When finalizing production designs, consult official documentation for the exact region, SKU, and service version:

1. [Azure Managed Redis overview](https://learn.microsoft.com/azure/redis/overview) — product, tiers, features, versions.
2. [Plan Azure Managed Redis configuration](https://learn.microsoft.com/azure/redis/plan-configuration) — creation-time fixed decisions.
3. [Choose a tier and plan capacity](https://learn.microsoft.com/azure/redis/plan-tiers-and-capacity) — RAM/CPU/Flash, connection limits, memory headroom.
4. [Choose a clustering policy](https://learn.microsoft.com/azure/redis/choose-clustering-policy) — OSS/Enterprise/Non-clustered, client compatibility, hash slots.
5. [Quickstart: create Azure Managed Redis](https://learn.microsoft.com/azure/redis/quickstart-create-managed-redis) — Portal, networking, policy/modules.
6. [Use Microsoft Entra authentication](https://learn.microsoft.com/azure/redis/entra-for-authentication) — tokens, Redis users, re-AUTH.
7. [Secure Azure Managed Redis](https://learn.microsoft.com/azure/redis/secure-azure-managed-redis) — Private Link/TLS/data access.
8. [Azure Managed Redis Private Link](https://learn.microsoft.com/azure/redis/private-link) — Private Endpoint, DNS, public access.
9. [Plan reliability and durability](https://learn.microsoft.com/azure/redis/plan-reliability-and-durability) — HA/zone/persistence/geo/backup restrictions.
10. [Data persistence](https://learn.microsoft.com/azure/redis/how-to-persistence) — RDB/AOF vs Export backup.
11. [Monitoring data reference](https://learn.microsoft.com/azure/redis/monitor-cache-reference) — metrics and semantics.
12. [Azure Cache for Redis retirement FAQ](https://learn.microsoft.com/azure/azure-cache-for-redis/retirement-faq) — lifecycle/migration.

**Important note:** any references to retirement milestones, Redis preview versions, default auth, ports, sizes/ratios, or product features in this lesson illustrate how to **make decisions grounded in verified documentation**; before finalizing production, re-verify against current announcements and feature tables. Never choose a Redis module or cluster policy based solely on an outdated blog post written for Azure Cache for Redis.

## 24. Key takeaways

**Choosing Azure Managed Redis for applications** combines **data patterns, memory, compute, client compatibility, reliability, security, and FinOps**; the cheapest or highest-GB SKU is rarely enough on its own.

Key points:

1. **Redis is not by default a source-of-truth database:** keep authoritative data in Azure SQL/Cosmos DB or a store with suitable durability/transactions; define cache misses and fallbacks.
2. **Choose the tier by bottleneck:** Memory Optimized favors capacity, Balanced balances general use, Compute Optimized favors throughput, and Flash Optimized serves large hot/cold datasets with latency/feature trade-offs.
3. **Clustering policy affects clients:** OSS requires Redis Cluster awareness and valid hash slots; Enterprise uses a proxy/single endpoint; Non-clustered has size caps.
4. **Select modules early:** RedisJSON/RediSearch/Bloom/TimeSeries carry Redis version, tier, and policy constraints; Redis 8 preview does not replace production suitability checks.
5. **Capacity must be quantified:** data size + key overhead + reserved memory + growth + headroom + connection cap + benchmarks, not raw GB alone.
6. **TTL/eviction govern correctness and cost:** stale/evicted cache entries are normal; invalidation and authoritative transactions preserve business correctness.
7. **Defense-in-depth security:** Private Endpoint/DNS/public access, TLS certificate verification, Microsoft Entra managed identity, and Redis data access permissions; never confuse Azure RBAC with Redis AUTH.
8. **HA is not backup:** replicas/zones protect against node failures, persistence recovers the same cache, active geo enables multi-region eventual consistency, Export/Import provides portable backups; some features are mutually exclusive.
9. **Observe end-to-end SLOs:** cache hit ratio, p95/p99, memory%, Server Load, connections, evictions, Redis auth/network health, and database impact.
10. **Plan migration/FinOps:** legacy Azure Cache for Redis has retirement dates, while AMR introduces new endpoints/policies; benchmark, maintain rollback plans, track costs, and clean up labs safely.

An Azure Managed Redis decision is ready when you can answer: **What data should the app cache, what are its volume/latency profiles, which tier and cluster policy are truly compatible, how can keys be lost, how will clients authenticate and connect, how does a Redis outage affect the business, and what benchmark and cost evidence justifies the deployment?**
