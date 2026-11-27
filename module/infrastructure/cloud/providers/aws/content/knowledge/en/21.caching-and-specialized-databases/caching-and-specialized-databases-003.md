# Cache-Aside, Write-Through, and TTL Policies

> **Chapter:** Caching and Specialized Databases  
> **Module:** `CLOUD_PROVIDERS_AWS` — explore the AWS ecosystem across Regions/AZs, IAM, VPC, compute services, storage, databases, integration, and serverless; build skills to select services and design and deploy secure, monitored, resilient, and cost-controlled applications.

An online store sees millions of product detail views per day, while price and description data change far less frequently than reads occur. If every request queries the database, the system pays I/O, connection, and compute costs for repeated results. A **cache** holds copies of frequently accessed data in memory to cut latency and offload the primary data source.

Three key cache design decisions are:

- **Cache-aside:** the application proactively reads the cache; on a cache miss, it fetches data from the database and populates the cache.
- **Write-through:** writes update both the cache and the backing data store through a clearly defined synchronous workflow.
- **TTL (Time To Live):** how long a cache entry is considered valid before expiring.

No single pattern automatically solves every consistency problem. A cache can serve stale data, lose entries to eviction, drop data on node failures, or experience concurrent updates across multiple application instances. Therefore, you must define the **source of truth**, acceptable staleness bounds, invalidation mechanisms, cache stampede handling, and failure behavior when the cache is unavailable.

On AWS, common options include **Amazon ElastiCache for Valkey/Redis OSS**, **Amazon ElastiCache for Memcached**, and **Amazon DynamoDB Accelerator (DAX)**. They serve different data models and consistency guarantees; not every cache service is an interchangeable Redis endpoint.

## 1. Learning Objectives

After this lesson, you can:

1. Explain cache hits/misses, source of truth, cache keys, cache entries, eviction, and invalidation.
2. Distinguish **cache-aside, write-through, write-around, and write-behind**, and choose patterns based on read/write demands.
3. Design **TTLs** around data freshness, traffic, and stale-data risk, distinguishing cache TTLs from database item-deletion TTLs.
4. Mitigate cache stampedes, thundering herds, cache penetration, hot keys, and cache avalanches.
5. Choose ElastiCache Valkey/Redis OSS, Memcached, or DynamoDB DAX based on use cases.
6. Implement caching in Java/Spring Boot apps with safe key design, invalidation, and serialization.
7. Monitor cache hit ratio, latency, evictions, memory, connections, and replication lag.
8. Design fallbacks, security, HA, capacity planning, and cost controls for cache outages or overload.

## 2. How Does a Cache Work?

A cache is a storage layer faster than the primary data source, typically residing in RAM. The application queries the cache using a **key**. If the key exists and the entry is still valid, the application gets a **cache hit**; otherwise, a **cache miss** occurs and the application must fetch data from the source of truth.

~~~mermaid
flowchart TD
    REQ["Application request"] --> LOOK["Lookup cache by key"]
    LOOK --> HIT{"Entry exists\nand valid?"}
    HIT -->|"Hit"| RETURN["Return cached value"]
    HIT -->|"Miss / expired"| DB["Read source of truth"]
    DB --> FILL["Populate cache with TTL"]
    FILL --> RETURNDB["Return database value"]
~~~

### 2.1. Terms to Distinguish

| Term | Meaning |
| --- | --- |
| **Source of truth** | Authoritative data store, such as RDS/Aurora or DynamoDB |
| **Cache key** | Unique identifier for a cache entry |
| **Cache entry/value** | Data stored under a key, optionally with metadata/version |
| **Cache hit** | A valid entry is found in cache |
| **Cache miss** | Entry is absent, expired, or evicted |
| **TTL** | Validity duration of a cache entry |
| **Invalidation** | Actively rendering an entry unusable, usually by deleting or changing its version |
| **Eviction** | Cache automatically dropping entries to free memory per policy |
| **Hit ratio** | Ratio of cache hits to total lookup requests |
| **Stale data** | Cached data older than the source of truth |

**TTL and invalidation are not the same:** TTL is a time boundary; invalidation reacts to a specific data change. A product whose price just changed may require immediate invalidation even with 20 minutes left on its TTL.

### 2.2. Hit Ratio Example

Suppose an application performs 10,000 cache lookups in one minute:

~~~text
Cache hits   = 9,200
Cache misses = 800

Hit ratio  = 9,200 / 10,000 = 92%
Miss ratio = 800 / 10,000   = 8%
~~~

A high hit ratio generally reduces database load, yet **does not prove the system is healthy on its own**:

- The cache may return wrong or stale data.
- A hot key can have a high hit ratio while bottlenecking a single shard.
- A single miss can trigger a very expensive database query.
- Cache compute/network costs may exceed database savings.

Measure **latency, stale data, downstream load, and business correctness** alongside hit ratio.

## 3. Cache-Aside: Application-Managed Caching

**Cache-aside** (also called lazy loading) is the standard read pattern. The application checks the cache first; on a miss, it queries the database and writes the result back to the cache.

~~~mermaid
sequenceDiagram
    participant A as Application
    participant C as Cache
    participant D as Database
    A->>C: GET product:42
    C-->>A: MISS
    A->>D: SELECT product WHERE id=42
    D-->>A: Product data
    A->>C: SET product:42 value EX TTL
    C-->>A: OK
    A-->>A: Return product
    Note over A,C: Subsequent requests usually result in a cache HIT
~~~

### 3.1. Read Flow

1. Construct the cache key from the attributes identifying the data.
2. Read the cache.
3. On a hit, deserialize, verify any needed schema/version, and return the result.
4. On a miss, query the source of truth.
5. If found, write to the cache with an appropriate TTL.
6. Return the result to the caller.

If the database finds no record, the app can **negative cache** a brief "not found" marker. Do not store a raw `null` indistinguishable from a "cache miss" unless your library explicitly supports that semantic.

### 3.2. Cache-Aside Example with Redis/Valkey (Java Pseudocode)

~~~java
public Product findProduct(String tenantId, String productId) {
    String key = "product:v3:" + tenantId + ":" + productId;

    Product cached = cache.get(key);
    if (cached != null) {
        return cached;
    }

    Product product = productRepository
        .findByTenantIdAndId(tenantId, productId)
        .orElse(null);

    if (product != null) {
        cache.set(key, product, Duration.ofMinutes(5));
    } else {
        // Short negative cache to avoid repeated lookups for nonexistent IDs.
        cache.set(key, NOT_FOUND_MARKER, Duration.ofSeconds(20));
    }
    return product;
}
~~~

This pseudocode illustrates the pattern; `cache`, `NOT_FOUND_MARKER`, and the repository must be implemented for your chosen library. If the cache stores a marker, read logic must distinguish a **not-found marker** from a **cache miss**.

### 3.3. Writes and Invalidation in Cache-Aside

~~~mermaid
sequenceDiagram
    participant A as Application
    participant D as Database
    participant C as Cache
    A->>D: UPDATE product SET price=...
    D-->>A: Commit success
    A->>C: DEL product:42
    C-->>A: Deleted
    Note over A,C: Next read will reload from DB
~~~

The order **commit database first, then invalidate cache** avoids deleting the cache entry only to let another request repopulate the old value before the DB commits. Still, a race condition remains:

1. Request A reads the old price from the database.
2. Request B commits the new price and deletes the cache key.
3. Request A writes the old price into the cache after B deleted it.

Result: the cache can become stale even though invalidation ran. Mitigate this using **versioned keys**, write serialization, conditional updates, outbox/event-driven invalidation, or short TTLs per SLA.

### 3.4. Pros and Cons

| Pros | Trade-offs |
| --- | --- |
| Caches only data actually read | First read pays database latency |
| Easy to layer onto existing databases | App must manage misses, fills, and invalidation |
| Cache loss leaves authoritative data intact | Cache outages can surge traffic onto the database |
| TTL bounds entry age | Data can be stale within the TTL window |

**Best fits:** product catalogs, user profiles, read-heavy/write-light configs, detail pages, and data reconstructible from the source of truth.

## 4. Write-Through: Writing Cache and Data Source in One Flow

**Write-through** describes a model where writes update **the cache and backing store synchronously within the same write flow** per the cache layer's contract. Some frameworks/libraries define write-through as writing to the cache first and having a cache loader synchronously write to the backing store; some app architectures commit to the database first and update the cache before returning. The core rule is **never report success as if both stores are synced when only one succeeded**.

~~~mermaid
flowchart TD
    W["Application write"] --> TW["Write-through layer"]
    TW --> DB["Persist to source of truth"]
    DB -->|"Success"| CACHE["Update cache entry"]
    CACHE -->|"Success"| ACK["Acknowledge write"]
    DB -->|"Failure"| ERR["Return failure / retry"]
    CACHE -->|"Failure"| REPAIR["Repair / invalidate / reconcile"]
~~~

This diagram shows a **database-commit-first then cache-update** variant. Exact ordering depends on implementation. A write-through layer that writes to cache first and synchronously persists to the DB must handle backing-store failures and prevent the cache from accidentally acting as the source of truth.

### 4.1. Database-First Synchronous Write Flow

1. Validate the request and write permissions.
2. Write to the database inside a transaction.
3. Commit the database transaction.
4. Update the cache with the new value or delete the entry so the next read reloads it.
5. Return the result per contract.

If step 4 fails after step 3 committed, the database holds the source of truth while the cache is stale. The app needs **invalidation/reconciliation**, events/outbox, or TTL to recover state.

### 4.2. Write-Through Does Not Create an Automatic Distributed Transaction

A database and Redis/Valkey typically do not share an ACID transaction. Never assume:

~~~text
DB COMMIT succeeds
Redis SET fails
→ both operations automatically roll back as one transaction
~~~

To ensure eventual cache updates:

- Write an **outbox event** inside the same transaction as the database business update.
- Have a worker read the outbox and update/delete the cache.
- Include an `eventId`/version, keep the worker idempotent, and use bounded retries.
- Provide a DLQ/reconciliation path when events fail processing.

This yields **eventual cache consistency** when cache updates occur asynchronously, differing from strict synchronous write-through at response time.

### 4.3. When Is Write-Through Useful?

- Data is frequently read right after creation or update.
- You want to avoid an immediate cache miss after writes.
- The cache layer provides a suitable backing-store sync mechanism.
- Extra write latency is acceptable and partial-failure recovery exists.

**Poor fit** when write volume is high and read rate is low: you populate memory with rarely used entries and pay extra latency on every write.

## 5. Cache-Aside, Write-Through, Write-Around, and Write-Behind

| Pattern | Read | Write | Pros | Risks/Trade-offs |
| --- | --- | --- | --- | --- |
| **Cache-aside** | App reads cache; on miss, reads DB and fills | App writes DB then invalidates/updates cache | Simple to adopt; cache holds only requested data | Miss latency, invalidation races, app manages cache |
| **Write-through** | Usually reads from cache | Writes backing store and cache in one sync flow | New entry is immediately available on success | Higher write latency; partial failures need handling |
| **Write-around** | App reads cache; on miss, reads DB/fills per policy | Writes directly to DB, bypassing cache | Avoids polluting cache with write-once data | Immediate post-write reads miss |
| **Write-behind / write-back** | Reads from cache | Cache accepts write first; persists to DB asynchronously | Low write latency; supports write batching | Risk of losing unflushed writes; complex ordering/retries |

### 5.1. Pattern Selection Examples

- **Product catalog:** cache-aside with a few minutes' TTL and invalidation on price/stock updates.
- **Rarely changing config always read right after updates:** write-through or DB commit + synchronous cache update.
- **High-volume, rarely read logs/events:** write-around can fit well.
- **Batchable counters/telemetry:** write-behind only if durability/consistency trade-offs are acceptable and reliable persistence exists.

**Write-behind carries clear data-loss risks.** A Redis/Valkey cache is not by default a durable database replacing RDS/DynamoDB. If a cache node restarts or unflushed entries drop, writes can be lost. Use it only with persistence, replication, queuing, and recovery semantics matching business requirements.

## 6. TTL: Cache Entry Lifetime Policies

**TTL** governs how long an entry remains valid. Once TTL expires, the cache no longer serves that entry as valid; subsequent requests must reload from the source of truth.

Example:

~~~text
SET product:42 '{"price":350000}' EX 300

EX = 300 seconds
→ Entry has a 5-minute TTL
~~~

TTL **does not mean** the database record is deleted after 5 minutes. Cache TTL is a freshness policy; DynamoDB table TTL or S3 lifecycle rules handle underlying data deletion under their own semantics.

### 6.1. Choose TTL by Data Type, Not One Number for All Keys

| Data type | Starting TTL to evaluate | Considerations |
| --- | --- | --- |
| **Product catalog/descriptions** | 5–30 minutes | Can be invalidated when products update |
| **Prices and promotions** | Tens of seconds to a few minutes | Wrong prices cause business harm; pair with event invalidation |
| **Infrequently changing profiles** | 5–60 minutes | Account for profile updates and user sessions |
| **Features/configuration** | A few minutes or longer | Can use version/config events to invalidate |
| **Session/token metadata** | Aligned with session security lifetime | Never let cache TTL exceed authorization expiry |
| **Real-time leaderboards/counters** | A few seconds | Freshness matters more than hit ratio |
| **Negative cache (not found)** | Seconds to tens of seconds | Avoid hiding newly created records |

These ranges are **starting points for load tests and SLOs**, not universal rules. Proper TTL depends on change frequency, staleness impact, and invalidation capabilities.

### 6.2. Fixed TTLs Can Trigger a Cache Avalanche

If a batch import writes 100,000 entries simultaneously with an exact 10-minute TTL, they can expire around the same time, slamming the database with misses.

A simple mitigation is **TTL jitter**:

~~~text
baseTTL = 600 seconds
jitter = random(0..120 seconds)
actualTTL = baseTTL + jitter

→ Entries expire across 10–12 minutes,
  reducing synchronized mass expirations.
~~~

Avoid adding jitter if a strict contract enforces an unextended upper lifetime; in that case, use proactive refresh or another eviction approach.

### 6.3. TTL, Absolute Expiration, and Sliding Expiration

- **Relative TTL:** entry lives for N seconds from the time it is set.
- **Absolute expiration:** entry expires at a fixed timestamp.
- **Sliding expiration:** TTL resets on every valid access.

Sliding expiration can keep "hot" entries alive indefinitely if continuously read. For sessions, this can work if paired with an explicit **maximum lifetime**. For business data, sliding expiration can keep stale values alive too long without invalidation.

### 6.4. Expiration Does Not Mean Immediate Deletion at the Exact Millisecond

Cache engines optimize expiration internally; expired entries may be removed lazily on access or via background sweeps. Applications must rely on **the guarantee that expired entries are not returned as valid after TTL**, rather than inspecting RAM to assert exact-millisecond deallocation.

In Redis/Valkey, TTLs are configured in seconds or milliseconds and inspected via `TTL`/`PTTL`. Memcached follows its own engine expiration rules. DynamoDB TTL deletes items **asynchronously**, unlike synchronous cache expiration.

## 7. Cache Invalidation: When Must Stale Data Disappear?

TTL is a safety net of last resort, while freshness-sensitive data benefits from **event-driven invalidation**.

~~~mermaid
flowchart LR
    APP["Application update"] --> DB["Commit database"]
    DB --> OUT["Outbox event"]
    OUT --> BUS["EventBridge / SNS / SQS"]
    BUS --> WORK["Invalidation worker"]
    WORK --> CACHE["DEL / version bump"]
    CACHE --> NEXT["Next read reloads current data"]
~~~

### 7.1. Invalidation Strategies

| Strategy | How it works | Characteristics |
| --- | --- | --- |
| **Delete key** | Remove entry on data change | Simple; next request reloads |
| **Update key** | Write new value to cache | Fast read-after-write; must handle cache write errors |
| **Versioned key** | Increment version in key or namespace | Prevents old writers from polluting new keys; requires version management |
| **Event-driven invalidation** | Emit event post-DB commit | Decouples app from cache, with eventual delay |
| **TTL only** | Wait for entry expiration | Easy to run, but longer stale windows |

### 7.2. Outbox Prevents Lost Invalidation Events

An anti-pattern:

~~~text
1. UPDATE database succeeds
2. App crashes before publishing invalidation
3. Cache serves stale data until TTL expires
~~~

The **transactional outbox** pattern records the business change and an outbox row in the same database transaction. A publisher/worker reads the outbox, emits the event, and marks it processed. If the worker publishes duplicates, consumers must be idempotent.

### 7.3. Versioned Cache Keys

Example:

~~~text
product:tenant-7:42:v18
~~~

When data updates from version 18 to 19, the app queries `product:tenant-7:42:v19`. An in-flight stale request writing to version 18 cannot corrupt the new namespace. However, you still need a **reliable version source** and lookup path; caching the version pointer too long reintroduces staleness.

### 7.4. Relationship-Aware Invalidation

A product page might depend on:

- Product details.
- Prices/promotions.
- Inventory.
- Product categories.
- Recommendation results.

Deleting only `product:42` may leave `category:shoes:page:1` or `recommendations:user:42` stale. Map out the **cache dependency graph** and choose manageable namespace, tag, or version invalidation schemes.

## 8. Cache Stampede, Thundering Herd, and Cache Failure Modes

### 8.1. Cache Stampede

A very popular key hits TTL. 5,000 requests miss simultaneously and query the database:

~~~mermaid
flowchart TD
    R["5,000 requests"] --> C["Cache: key expired"]
    C --> DB["5,000 concurrent DB reads"]
    DB --> LOAD["DB CPU / connections spike"]
    LOAD --> TIMEOUT["Latency / timeout / retry"]
~~~

Mitigations:

- **Single-flight / request coalescing:** only one request refreshes the key while others wait or receive stale data if policy allows.
- **Distributed lock:** per-key lock with short TTL, unique owner token, and safe release.
- **TTL jitter:** prevents mass simultaneous expirations.
- **Refresh-ahead:** proactively refreshes hot keys before expiry.
- **Stale-while-revalidate:** serves stale data within an acceptable window while one worker refreshes.
- **Rate-limit DB fallbacks:** protects the database when cache fails.

### 8.2. Distributed Locks Need Fencing/Tokens

A basic `SET key token NX PX ...` lock prevents multiple workers from refreshing at once, provided you enforce:

1. A unique random token per owner.
2. A lock TTL shorter than processing bounds, with renewal if needed.
3. Releasing the lock only if the token still matches the current owner (Lua compare-and-delete or atomic equivalent).
4. Never assuming lock expiry means the previous worker stopped—it may still be running.
5. For critical side effects, use a **fencing token/version** on the protected resource to block stale owners from overwriting newer ones.

Cache locks only deduplicate computation; they do not replace database transactions or concurrency control.

### 8.3. Cache Penetration (Continuous Misses)

If callers send thousands of nonexistent IDs, every request misses and queries the DB. Mitigations:

- Input validation and rate limiting.
- Short-TTL negative caching.
- A Bloom filter or similar structure if use cases and false-positive semantics fit.
- Avoid caching `not found` too long if records may be created soon after.

### 8.4. Cache Breakdown and Hot Keys

A single key read tens of thousands of times per second creates a hotspot on one node/shard. When that key expires, the stampede multiplies the load.

- Replicate or route reads across replicas per supported design.
- Short-lived local in-process caches cut network hops at the cost of extra invalidation complexity.
- Use precomputed values, sharded counters, or key partitioning where semantics allow.
- Refresh before TTL and monitor key-level access patterns when possible.

### 8.5. Cache Avalanche

Many keys expiring together or an entire cache cluster failing triggers massive misses. Mitigate with jitter, controlled warm-ups, fallback concurrency caps, and capacity testing.

**Never allow unbounded fallback:** letting every request hit the DB when the cache fails can knock down the DB too. Pair caches with **bulkheads**, short timeouts, circuit breakers, and load limits.

## 9. Eviction and Memory Management

Caches have finite capacity. As memory nears limits, the engine rejects writes or drops keys per its **eviction policy**.

### 9.1. Common Policies in Redis/Valkey

| Policy (common name) | General behavior |
| --- | --- |
| `noeviction` | Does not evict keys; new writes fail when memory is exhausted |
| `allkeys-lru` | Evicts least recently used keys across the entire keyspace |
| `allkeys-lfu` | Prefers retaining frequently accessed keys |
| `volatile-lru` | Evicts least recently used keys only among keys with TTL |
| `volatile-lfu` | Evicts least frequently used keys only among keys with TTL |
| `volatile-ttl` | Prioritizes keys with the shortest remaining TTL per engine semantics |

Exact names and configurability depend on engine, version, and parameter group. **TTL expiration and eviction are separate mechanisms:** keys can be evicted prior to TTL under high memory pressure.

### 9.2. Choosing a Policy by Data Type

- **Rebuildable cache:** LRU/LFU fits well; dropped keys simply trigger misses.
- **Cache holding unpersisted critical state:** do not treat eviction as safe; persist to a durable source first.
- **Keys lacking TTLs:** `volatile-*` selects only keys with expiration; if none qualify, new writes fail.
- **`noeviction`:** fits when silent drops must be prevented, provided the app handles write errors and memory alarms.

### 9.3. Memory Estimation

Suppose:

~~~text
Keys                   = 2,000,000
Average payload/key    = 700 bytes
Key + object/metadata  = 180 bytes (estimated)

Raw estimate = 2,000,000 × 880 bytes
             = 1,760,000,000 bytes
             ≈ 1.76 GB (decimal)
~~~

This is **not the RAM size to provision**. Add overhead for data structures, allocator fragmentation, replication buffers, client output buffers, temporary memory, persistence/AOF if enabled, and OOM headroom. Benchmark with realistic production key/value distributions.

## 10. Choosing a Caching Service on AWS

Not every workload needs Redis/Valkey. Before choosing a service, clarify:

1. Is cached data **general key/value**, objects, sessions, counters, or strictly DynamoDB read results?
2. Do you need **data structures**, pub/sub, scripting, sorted sets, or atomic operations?
3. Do you need **replication, Multi-AZ failover, persistence/snapshots**, or can data be rebuilt?
4. What throughput, latency, connection counts, memory, and scaling are needed?
5. Can the application tolerate **eventual consistency**, or does it need strongly consistent reads?

### 10.1. Comparing Common Options

| Service | Model | Strengths | Considerations |
| --- | --- | --- | --- |
| **Amazon ElastiCache for Valkey** | Managed in-memory key/value/data structures | Redis-protocol compatible per engine support, rich data structures, flexible replication/topology | Requires understanding cluster mode, shards, failover, memory, and compatibility |
| **Amazon ElastiCache for Redis OSS** | Managed Redis OSS-compatible cache engine | Broad Redis ecosystem, data structures, and tooling | Verify engine/version/feature support; do not assume 100% parity with Valkey |
| **Amazon ElastiCache for Memcached** | Distributed in-memory key/value cache | Simple horizontal scaling across nodes; great for object caching | Lacks Redis-style persistence/replication and rich data structures |
| **Amazon DynamoDB Accelerator (DAX)** | Managed in-memory cache built specifically for DynamoDB | Cuts DynamoDB read latency with compatible client; write-through caching | Only for DynamoDB access patterns; understand eventual vs. strong read semantics |
| **Local in-process cache** | Cache in each app instance's RAM | Extremely fast, zero network hop | Per-instance state; invalidation, memory limits, and cold starts are harder |

**DAX is not a Redis replacement**, nor is Memcached a Redis-compatible engine. If an app relies on Redis protocols or data structures, you cannot simply point its connection string at DAX.

### 10.2. ElastiCache Valkey/Redis OSS

ElastiCache fits workloads needing flexible key/value caching, rich data structures, or atomic cache-layer operations.

Common components:

- **Node:** a cache server instance with fixed memory/compute.
- **Replication group:** nodes backing one logical cache; primary/replica topology varies by engine and config.
- **Shard:** data partition in cluster-mode enabled; keys distribute across hash slots.
- **Cluster mode disabled:** single primary with optional replicas; simpler to manage, but writes scale only on one primary.
- **Cluster mode enabled:** multiple shards/primaries distributing data and write throughput; clients must handle cluster topology/redirects.
- **Multi-AZ/automatic failover:** improves fault tolerance in supported topologies; failover still resets connections and can incur replication lag.

~~~mermaid
flowchart TB
    APP["Application fleet"] --> EP["ElastiCache configuration endpoint"]
    EP --> S1["Shard 1\nPrimary"]
    EP --> S2["Shard 2\nPrimary"]
    EP --> S3["Shard 3\nPrimary"]
    S1 --> R1["Replica"]
    S2 --> R2["Replica"]
    S3 --> R3["Replica"]
~~~

*Conceptual diagram for cluster-mode enabled. Endpoints, replica counts, and client topology discovery depend on actual configuration.*

When designing:

- Place in **private subnets** with proper security groups and subnet groups.
- Choose node family/memory based on working set, peak traffic, and replication overhead.
- Enable encryption at rest/in transit as required and authenticate with engine-supported mechanisms.
- Configure eviction policies, max memory, and snapshots/backups if needed.
- Use clients supporting reconnects, cluster topology, and TLS; never resolve an endpoint once and hard-code node IPs.
- Test failover, resharding/scaling, and behavior during temporary cache unavailability.

### 10.3. ElastiCache Memcached

Memcached works well for **simple object caching** where the app can rebuild entries from the database on node loss.

Characteristics:

- Simple key/value model and basic cache API.
- Distributes keys across nodes via client-side hashing/auto-discovery depending on client.
- Node failures drop keys stored on that node; misses fall back to the source of truth.
- Never use node-based Memcached as durable storage or to hold unpersisted workflow state.
- Lacks the rich data structures, scripting, and replication semantics of Redis-compatible engines.

Choose Memcached when you want to cache objects to cut read load without needing sorted sets, streams, pub/sub, or complex atomic scripts.

### 10.4. DynamoDB Accelerator (DAX)

DAX is an **in-memory cache purpose-built for DynamoDB**. Applications send DynamoDB calls via a compatible DAX client; DAX caches read results and performs write-through updates to DynamoDB per service behavior.

Key points:

- **Eventually consistent reads** can be served from the DAX cache.
- **Strongly consistent reads** pass through to DynamoDB per DAX semantics; do not expect cache hits for strong reads like a local Redis `GET`.
- Write-through updates DAX when writing via the DAX client, whereas writes **bypassing the DAX path** require cache-coherence/invalidation planning.
- DAX maintains separate item caches and query caches with distinct TTLs and freshness behavior.
- DAX fits DynamoDB-centric read patterns; it is not a general cache for RDS, HTTP responses, or arbitrary sessions.

**Decision example:** a read-heavy Java app already using the DynamoDB SDK and tolerating eventual consistency should evaluate DAX. If it needs Redis sorted sets for leaderboards or distributed locks, evaluate ElastiCache Valkey/Redis OSS instead.

### 10.5. Local Cache + Distributed Cache

An architecture can combine two tiers:

~~~text
Application instance
  → L1 local cache (milliseconds, short TTL)
  → L2 ElastiCache (shared cache)
  → RDS/Aurora/DynamoDB (source of truth)
~~~

L1 eliminates network hops, yet every instance holds an isolated copy. If a product price changes, you must invalidate/refresh **both L1 and L2**, or keep L1 TTLs very short per freshness contracts. Do not add L1 just to shave microseconds in a benchmark if invalidation and staleness costs outweigh the gains.

## 11. Safe Cache Key and Value Design

### 11.1. Cache Keys Must Include Every Dimension Affecting Output

Example key:

~~~text
product:v3:tenant-17:product-42:locale-vi
~~~

If responses vary by tenant, locale, currency, role, feature flags, or version, encode all relevant dimensions in the key. Omitting tenant ID can leak one tenant's data to another—a **data isolation/security bug**.

A helpful pattern:

~~~text
cache key =
  domain + schemaVersion + tenant + entityId + relevantDimensions
~~~

Never embed sensitive data, access tokens, or full PII in keys; keys frequently appear in metrics, logs, and cache inspection tools.

### 11.2. Serialization and Schema Versioning

When caching Java objects, enforce a stable serialization format:

- JSON, MessagePack, CBOR, or another controlled format.
- Include `schemaVersion` to distinguish formats across deploys.
- Never assume native Java serialization is safe for untrusted data.
- Handle cache entries written by older app versions during rolling deployments.
- Use TTL/namespace migration to phase out old schemas.

Example envelope:

~~~json
{
  "schemaVersion": 3,
  "entityVersion": 18,
  "cachedAt": "2026-11-20T03:00:00Z",
  "value": {
    "productId": "product-42",
    "price": 350000
  }
}
~~~

`schemaVersion` tracks the cache payload format; `entityVersion` tracks the business record version. Both serve distinct purposes.

### 11.3. Avoid Caching Error Results by Mistake

Never cache:

- HTTP 500/503 errors or exceptions as valid responses.
- Authorization failures if the key omits proper identity/permission context.
- Timed-out or canceled query results.
- Partial results from incomplete queries unless explicitly allowed by contract.

Negative caches should only store **definitive business outcomes** like "record does not exist" with a short TTL—never store "database temporarily unavailable" as not found.

## 12. Java/Spring Boot: Cache-Aside with Spring Cache

The Spring Cache abstraction provides annotations at method boundaries. The backing provider can be Redis/Valkey via Spring Data Redis, Caffeine locally, or another supported store.

### 12.1. Enable Caching and Define a Service

~~~java
@Configuration
@EnableCaching
public class CacheConfiguration {
}
~~~

Example service:

~~~java
@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(
        cacheNames = "product",
        key = "#tenantId + ':' + #productId",
        unless = "#result == null"
    )
    public Product find(String tenantId, String productId) {
        return repository.findByTenantIdAndId(tenantId, productId)
            .orElse(null);
    }

    @CacheEvict(
        cacheNames = "product",
        key = "#tenantId + ':' + #productId"
    )
    public void evict(String tenantId, String productId) {
        // Used as an explicit invalidation command.
    }
}
~~~

Explanation:

- `@Cacheable`: checks the cache first; on a miss, executes the method and caches the result under `key`.
- `key`: includes both tenant and product ID to prevent cross-tenant data mixing.
- `unless`: skips caching when the result is null, avoiding unintended negative caching.
- `@CacheEvict`: deletes the entry after the method succeeds under the default `beforeInvocation=false`.

**Spring caching typically relies on AOP proxies:** calling a cacheable method from another method on the same instance (self-invocation) bypasses the proxy so annotations do not fire. Verify call boundaries and proxy modes.

SpEL keys above reference parameter names `tenantId` and `productId`. Ensure your build preserves parameter names (e.g., `-parameters` compiler flag) or use positional arguments like `#p0`/`#p1` per Spring configuration; otherwise the expression may fail to resolve.

### 12.2. Configure TTLs for Redis Cache

~~~java
@Configuration
public class CacheManagerConfig {
    @Bean
    RedisCacheManager cacheManager(
            RedisConnectionFactory connectionFactory) {

        org.springframework.data.redis.cache.RedisCacheConfiguration defaults =
            org.springframework.data.redis.cache.RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(5))
                .disableCachingNullValues();

        Map<String, org.springframework.data.redis.cache.RedisCacheConfiguration> perCache =
            Map.of(
                "product",
                defaults.entryTtl(Duration.ofMinutes(5)),
                "profile",
                defaults.entryTtl(Duration.ofMinutes(20)),
                "hot-price",
                defaults.entryTtl(Duration.ofSeconds(30))
            );

        return RedisCacheManager.builder(connectionFactory)
            .cacheDefaults(defaults)
            .withInitialCacheConfigurations(perCache)
            .build();
    }
}
~~~

This Spring Data Redis example requires imports and bean wiring matching your Spring Boot/Spring Data version. TTLs here are **defaults per cache region**, not per-entry jittered TTLs. For per-entry TTL jitter or custom freshness rules, use `RedisTemplate`/`CacheWriter` or a custom abstraction.

### 12.3. Updating Cache with `@CachePut`

~~~java
@CachePut(
    cacheNames = "product",
    key = "#tenantId + ':' + #productId"
)
public Product update(
        String tenantId,
        String productId,
        UpdateProductCommand command) {
    return repository.update(tenantId, productId, command);
}
~~~

`@CachePut` **always runs the method** and updates the cache with its return value, unlike `@Cacheable`, which skips execution on hits. This illustrates application-level write-through: the repository commits and returns `Product`, then Spring Cache updates the cache. If the cache write fails after DB commit, the caller can receive an error despite the DB having changed; ensure invalidation/reconciliation and idempotent update APIs.

### 12.4. Clearing Multiple Keys

~~~java
@CacheEvict(cacheNames = "product", allEntries = true)
public void rebuildProductCatalog() {
    // Rebuild operation
}
~~~

`allEntries=true` can cause a surge of misses immediately after invalidation. For large caches, prefer versioned namespaces, batch warm-up, or targeted deletions rather than flushing everything under high traffic.

## 13. Basic Redis/Valkey TTL and Inspection Commands

The commands below illustrate Redis-compatible protocol behavior. Exact syntax/support must match your engine and version.

### 13.1. Writing a Key with TTL

~~~text
SET product:42 '{"price":350000}' EX 300

EX = 300 seconds
→ Entry has a 5-minute TTL
~~~

~~~text
TTL product:42
PTTL product:42
~~~

- `SET ... EX 300`: stores value and sets a 300-second TTL atomically in one command.
- `TTL`: inspects remaining lifetime in seconds.
- `PTTL`: inspects remaining lifetime in milliseconds.
- Negative return values indicate either a missing key or a key with no expiration per Redis semantics; distinguish the return codes carefully.

### 13.2. Deleting and Updating TTL

~~~text
DEL product:42
EXPIRE product:42 120
PERSIST product:42
~~~

- `DEL`: deletes the key.
- `EXPIRE`: sets or resets TTL on an existing key.
- `PERSIST`: removes expiration so the key never expires by TTL.

**Caution with PERSIST:** cache keys without TTLs can linger in memory indefinitely and increase memory pressure. Never run mutating commands on production keys just to experiment in a console.

### 13.3. Never Use `KEYS *` to Inspect Production

`KEYS *` scans the entire keyspace and can cause blocking/latency spikes depending on engine and dataset size. When iterating keys is necessary, prefer cursor-based `SCAN` with bounded `COUNT` and rate control. Even `SCAN` can return duplicates or miss keys modified mid-scan; never treat it as a transactional snapshot.

### 13.4. Atomic Updates and Preserving TTL

A plain `SET` **overwrites the value and clears the existing TTL** unless you pass the appropriate expiration or keep-TTL option for your engine/version. When updating values:

- Pass TTL within the same command whenever possible.
- Or use a script/transaction designed to update value and TTL atomically.
- Never assume `GET` → `SET` → `EXPIRE` is atomic; a crash mid-sequence leaves a key with no TTL.

## 14. AWS Architecture: Caching in Multi-Tier Applications

### 14.1. Cache-Aside with ElastiCache and RDS/Aurora

~~~mermaid
flowchart LR
    CLIENT["Web / Mobile"] --> ALB["ALB / API"]
    ALB --> APP["Spring Boot services\nECS / EKS / Lambda"]
    APP -->|"GET / SET / DEL"| CACHE["ElastiCache\nValkey / Redis OSS"]
    APP -->|"Miss / write"| DB["RDS / Aurora\nsource of truth"]
    DB -->|"Commit + outbox"| OUT["Outbox publisher"]
    OUT --> BUS["SQS / EventBridge"]
    BUS --> INV["Invalidation worker"]
    INV -->|"DEL / version bump"| CACHE
    CACHE -.-> MON["CloudWatch metrics"]
    DB -.-> MON
~~~

**The cache is not the source of truth** in this diagram. If the cache cluster loses data, the app can read from the database and repopulate entries, provided fallback traffic is throttled to protect the database.

### 14.2. Multi-AZ and Replication

With ElastiCache Valkey/Redis OSS, topologies can include a primary and replicas; when supported HA options are enabled, the service can fail over to a replica if a node fails.

Notes:

- Replication may be **asynchronous**; the latest writes may not yet have replicated before a node fails.
- Failover changes the primary and drops active connections.
- Clients must reconnect, refresh topology/endpoints, and retry safely.
- Read replicas can lag behind the primary; never use replicas for read-after-write flows requiring strong consistency.
- Snapshots/persistence are engine/config-dependent recovery tools, not a guarantee that every cache write survives like a database transaction.

With cache-aside, losing partial entries is recoverable from the source of truth. If unpersisted sessions, counters, or workflow state reside in cache, re-evaluate whether the cache is inadvertently acting as a primary database.

### 14.3. Cluster Mode and Key Distribution

Cluster mode enabled partitions the keyspace into shards. Clients must understand **cluster redirection/topology** and handle `MOVED`/`ASK` or protocol equivalents.

- Keys sharing a hash tag co-locate in the same slot, e.g., `cart:{user-42}:items` and `cart:{user-42}:total`.
- Overly broad hash tags create hot shards.
- Multi-key commands and Lua scripts may require all keys to reside in the same hash slot.
- Resharding can increase network traffic/latency; test client behavior and operations before scaling.

Never force all keys into one shared hash tag just to run multi-key commands—that negates shard distribution benefits.

### 14.4. ElastiCache and VPC Connectivity

ElastiCache typically runs inside a VPC and accepts traffic from authorized workloads via security groups:

1. Select a subnet group spanning subnets appropriate for your topology.
2. Restrict the security group inbound rule to the application security group and required engine ports.
3. Verify route tables, DNS, NACLs, and VPC peering/Transit Gateway if apps sit in another VPC.
4. Enable TLS and configure client trust stores and hostname validation.
5. Never expose cache endpoints directly to the public Internet.

A classic misconfiguration is opening the database Security Group for ECS tasks while forgetting the cache Security Group; the app reports connection timeouts even while the cache cluster status shows Available.

## 15. Cache Consistency and Race Conditions

### 15.1. Define a Freshness Contract

Before setting TTLs, answer:

- How stale is the data allowed to be?
- Is read-after-write required for the user who just performed an update?
- Can other users tolerate seeing stale data for a few seconds?
- Do prices, balances, permissions, and inventory carry different staleness risks?
- When the cache is unreachable, should the app read the DB, serve stale data, or reject the request?

Illustrative contract table:

| Data | Freshness requirement | Suggested pattern |
| --- | --- | --- |
| Product description | Can be stale up to 5 minutes | Cache-aside + TTL + event invalidation |
| Price/discount | Needs rapid updates | Short-TTL cache-aside + invalidation/version; verify price in DB at checkout |
| Account balance | Never use cache as authoritative transaction value | Read source of truth / strong consistency by design |
| Feature flags | Can lag by a few seconds | Short cache + push invalidation |
| Public reference data | Can tolerate longer staleness | Long-TTL cache-aside, refresh-ahead |

**Never rely on a cache to make final decisions for sensitive financial transactions or authorization checks** when consistency requires querying the source of truth.

### 15.2. Read-After-Write

A user updates their profile name and immediately issues a `GET` profile request. If the write committed to the DB while the invalidation event lags, `GET` may return stale cached data.

Options:

- Synchronously update/invalidate the cache after DB commit before returning the response.
- Return the newly committed data directly to the caller while updating cache for future requests.
- Pass a version token in responses/requests so clients require at least that version.
- Read directly from the database during a read-after-write window or on critical paths.

### 15.3. Race Between Cache Fill and Invalidation

~~~mermaid
sequenceDiagram
    participant A as Reader A
    participant B as Writer B
    participant D as Database
    participant C as Cache
    A->>C: GET key
    C-->>A: MISS
    A->>D: Read old value v10
    B->>D: Commit new value v11
    B->>C: DEL key
    A->>C: SET old value v10
    Note over A,C: Cache holds stale data again
~~~

Versioned keys isolate the stale request to writing version 10 while newer readers fetch version 11, provided the version pointer updates reliably. Another option is a fill lock or version check during population. No single TTL eliminates race conditions on its own.

### 15.4. Eventual Consistency from an Outbox

When an outbox worker updates the cache asynchronously:

- The database commits first.
- Events can arrive late or duplicated.
- Consumers must be idempotent and enforce version ordering.
- Reordering can deliver version 12 after version 13; never let older events overwrite newer cached state.
- Periodic reconciliation catches key/version drift.

Conditional update rule: only write to cache if incoming `entityVersion` is **not lower** than the current version using atomic cache/datastore logic. Without atomic comparison, redesign the flow.

## 16. TTL Across AWS Services: Do Not Confuse Semantics

| Mechanism | Meaning | When does deletion happen? |
| --- | --- | --- |
| **ElastiCache Redis/Valkey TTL** | Key lifetime in cache | Engine expires per its rules; key is no longer returned as valid |
| **Memcached expiration** | Cache item lifetime | Per Memcached expiration rules |
| **DAX item/query cache TTL** | Lifetime of DAX cached results | Per DAX configuration and service behavior |
| **DynamoDB TTL** | Expiration attribute to delete table items | Deleted **asynchronously**, not at the exact timestamp |
| **S3 Lifecycle expiration** | Object/version lifecycle rule | Background lifecycle processing, not cache expiration |

### 16.1. DynamoDB TTL Is Not Redis TTL

DynamoDB TTL uses a Number attribute representing **Unix epoch time in seconds**. Once the timestamp passes, the item becomes eligible for background deletion; actual removal can lag significantly.

This implies:

- Expired items can still appear in `GetItem`/`Query` before background deletion runs.
- Applications must filter on `expiresAt` if expired items must not be used.
- DynamoDB TTL is not an exact-second mechanism to revoke sessions instantly.
- DynamoDB TTL does not automatically invalidate a separate Redis key caching the same item.

Example item:

~~~json
{
  "sessionId": "session-123",
  "userId": "user-42",
  "expiresAt": 1795143600
}
~~~

`expiresAt` is in Unix seconds; do not store an ISO timestamp string if DynamoDB TTL targets this Number attribute.

### 16.2. DAX TTL Differs from DynamoDB TTL

DAX applies TTLs to cached items and query results per service configuration. When a DAX entry expires, DAX re-fetches from DynamoDB per its cache mechanism. DynamoDB TTL deletes items from the underlying table. Both can coexist, yet **neither replaces the other**.

### 16.3. Session and Access Control TTLs

For session/token metadata, cache TTLs belong inside the **security contract**:

- Never let cached permissions outlive token/session revocation when immediate revocation is required.
- Use denylists, version checks, or invalidation on logout/role-change events.
- A cache outage must never flip authorization to allow-by-default.
- Avoid long-lived authorization caches when permissions change frequently.

## 17. Cache Security on AWS

### 17.1. Network Isolation

- Place ElastiCache in appropriate private subnets; never open cache endpoints to the public Internet.
- Restrict security groups strictly to source application SGs and required ports.
- Separate production, staging, and dev using distinct VPCs, subnets, security groups, or boundaries.
- With VPC peering or Transit Gateway, verify routing, DNS, and security boundaries on both sides.

### 17.2. Encryption and Authentication

- Enable **encryption in transit (TLS)** where supported by engine/config, with client certificate/hostname verification.
- Enable **encryption at rest** as required; manage KMS key policies, rotation, and decrypt permissions.
- Use AUTH tokens, user groups/ACLs, or engine-supported IAM authentication.
- Never hard-code credentials in source code, container images, logs, or shell history.
- Coordinate secret rotation so client connection pools do not suffer simultaneous outages.

Support for TLS, AUTH, ACLs, IAM authentication, and encryption depends on **engine, engine version, node type, and deployment mode**. Check the exact feature matrix before writing IaC.

### 17.3. Least Privilege

Separate roles:

- **Application role:** only allowed to connect to the cache via network and required credentials.
- **Provisioning role:** creates/modifies clusters, parameter groups, and subnet groups.
- **Operations role:** inspects metrics/logs and performs failover/scaling per runbook.
- **Security role:** manages secrets, KMS keys, auditing, and policies.

Never grant full AWS admin permissions to an application just because it reads/writes a cache. IAM does not replace network security or cache ACLs; enforce all layers.

### 17.4. Multi-Tenant Isolation

Cache keys should carry tenant namespaces, and code must enforce tenant authorization at the application layer. Unpredictable keys are **not** access control. For sensitive workloads, consider dedicated cache namespaces, encryption, and workload separation matching isolation requirements.

## 18. Resilience: When the Cache Slows Down or Fails

### 18.1. Cache Failure Policy

| Condition | Designed behavior |
| --- | --- |
| Cache GET timeout | Bounded fail-open read to DB, or serve stale value if permitted |
| Cache SET error after DB commit | Keep DB as source of truth; trigger invalidation/reconciliation |
| Cache cluster unavailable | Circuit breaker, bulkhead, capped DB fallback |
| Corrupt entry / deserialization error | Discard entry, emit metric, reload from source of truth |
| Failover/reconnect | Client reconnects with backoff/jitter, bounded retries |
| Memory full / eviction | Monitor evictions/write errors; scale or tune TTL/policies |

### 18.2. Short Timeouts and Bulkheads

Caches exist to cut latency; a 5-second cache `GET` timeout can make requests slower than querying the DB directly. Set timeouts within your latency budget, isolate connection pools, and never let cache calls block worker threads indefinitely.

When the cache becomes unavailable:

1. Trip the circuit breaker once error thresholds are crossed.
2. Stop queuing new requests to wait on cache timeouts.
3. Gate DB fallbacks behind a semaphore/concurrency cap.
4. Close the circuit gradually via half-open probes once the cache recovers.
5. Warm the cache in a controlled manner to prevent a post-outage stampede.

### 18.3. Stale-If-Error

Where freshness contracts allow, store `cachedAt`/`staleUntil` metadata and serve stale entries briefly when the source of truth or refresh fails. However:

- Never use stale-if-error for account balances, authorization checks, or checkout prices requiring fresh state.
- Bound the stale window strictly.
- Emit metrics tracking how many responses served stale data.
- Keep background refreshes idempotent with concurrency limits.

### 18.4. Post-Deploy / Post-Failover Warm-Up

Never preload an entire database into cache all at once. Identify the **working set** from access logs/metrics, batch-warm hot keys under QPS caps, and watch DB health. For cache-aside, live traffic can often warm the cache naturally if the database handles cold-start misses.

## 19. Monitoring and Metrics for AWS Caches

A cache can keep answering requests while memory fills, evictions climb, or latency degrades. Combine **CloudWatch metrics, application metrics, and database metrics**.

### 19.1. ElastiCache Metrics to Monitor

| Metric (common name) | Meaning | Signals to investigate |
| --- | --- | --- |
| **CacheHits** | Cache read hits | Sudden drop after deploy/flush |
| **CacheMisses** | Cache read misses | Spike driving up database load |
| **Evictions** | Keys dropped by memory policy | Continuous rise indicates memory pressure or mismatched TTL policy |
| **CurrConnections** | Active client connections | Unusual growth, connection leaks |
| **EngineCPUUtilization** | Cache engine CPU usage | High engine CPU even when overall host CPU looks moderate |
| **CPUUtilization** | Node CPU usage | Saturation or uneven shard load |
| **FreeableMemory / BytesUsedForCache** | Available memory / cache memory used | Low headroom, risk of evictions/write errors |
| **ReplicationLag** | Replication delay where supported | Read replicas may serve stale data |
| **NetworkBytesIn/Out** | Network throughput | Bandwidth limits, large payloads, client bursts |

Exact metric names/dimensions vary by engine and node type. Check the **`AWS/ElastiCache`** namespace, dimensions for replication groups/cache clusters/nodes, and current metric docs.

### 19.2. Complementary Application Metrics

CloudWatch cannot tell whether a cache hit returned stale data or a valid business result. Applications should emit:

- **cache_lookup_total** labeled by cache name and outcome (hit/miss/error).
- **cache_lookup_latency**.
- **cache_fill_total** and **cache_fill_error_total**.
- **cache_invalidation_lag_seconds**.
- **cache_stale_response_total**.
- **cache_fallback_db_total**.
- **cache_deserialization_error_total**.
- **cache_stampede_lock_wait_seconds**.

Never put high-cardinality tenant IDs, user IDs, or full cache keys into metric labels. Keep label dimensions bounded and log correlation IDs per policy.

### 19.3. DAX Metrics

For DAX, track hits/misses separately across item, query, and scan caches by workload type, alongside request counts, throttling, CPU/memory, and latency. An aggregate hit ratio can hide **high `ItemCache` hits alongside high `QueryCache` misses**; inspect the specific operations your app calls.

Also monitor DynamoDB:

- Consumed read/write capacity or request units per billing mode.
- Throttled requests.
- Latency and system errors.
- Hot partitions/key skew.

If DAX lowers read latency without reducing DynamoDB load as expected, verify consistency modes, query patterns, and uncached calls.

### 19.4. Symptom-Based Alarms

~~~text
Warning:
  Evictions rising continuously over 10 minutes
  CacheMisses spiking above baseline
  EngineCPUUtilization exceeding benchmarked threshold

Critical:
  Cache connection errors climbing
  App DB fallback exceeding concurrency budget
  Database CPU and connection pool rising simultaneously

Recovery:
  Cache hits recovering
  Evictions/latency returning to baseline
  Database load subsiding
~~~

Never hard-code one CPU threshold for every node family or workload. Base alarms on **baselines, latency SLOs, and downstream capacity**.

## 20. Capacity Planning and Cost

### 20.1. Caching Can Cut Database Costs While Raising Total Cost

Cache costs can include:

- ElastiCache node hours or Serverless capacity per active pricing model.
- Replicas, shards, Multi-AZ, and node family selection.
- Data transfer, cross-AZ traffic, and networking.
- Backups/snapshots, storage, and monitoring/logging.
- DAX node hours plus remaining DynamoDB charges.
- Application compute and operational overhead.

Evaluate costs across the **entire system**:

~~~text
Net benefit =
  Database cost avoided
  + latency/SLO value
  - Cache service cost
  - Added network/monitoring cost
  - Engineering/operations cost
~~~

A high cache hit ratio does not automatically save money if cache nodes are overprovisioned or data transfer is expensive.

### 20.2. Estimating Hit Rate and Database Offload

Suppose:

~~~text
Read requests/day        = 50,000,000
Expected hit ratio       = 90%
Database reads avoided   = 45,000,000/day
Database reads remaining =  5,000,000/day
~~~

This idealized calculation assumes each hit replaces one equivalent DB read. In practice:

- One miss can trigger multiple DB queries.
- One cache entry can serve multiple request types.
- TTLs/invalidations shift hit ratios over time.
- Query costs and request units vary widely.
- Stale reads can cause business errors if unacceptable.

### 20.3. Sizing by Working Set

You do not need to cache every row in the database. Determine:

1. **Working set:** keys actively accessed within a representative window.
2. Actual serialized payload sizes.
3. Key/object overhead, fragmentation, and metadata.
4. Replication memory, buffers, and client connections.
5. Headroom for bursts, failovers, and resharding.
6. Acceptable eviction rate.

Benchmark using a **Zipf/hot-key** distribution close to production. Uniform-key benchmarks miss hot shards and stampedes.

### 20.4. Before/After Cost Comparison

| Metric | Before cache | After cache (target) |
| --- | --- | --- |
| Database reads | 100% baseline | Reduced per actual hit ratio |
| DB CPU/connections | High at peak | Lower, maintaining headroom |
| API p95/p99 | Baseline | Measurable improvement |
| Cache service cost | 0 | Increases by nodes/throughput |
| Data freshness | Direct DB reads | Defined stale window/invalidation |
| Operational complexity | Fewer components | Higher due to cache, failover, keys, TTL |

Compare identical workloads, time windows, and traffic levels; avoid comparing a quiet day to a peak day.

## 21. Read-Only AWS CLI: Inspecting Cache Configurations

The following commands only read metadata and never create, modify, reboot, or delete clusters. Substitute Regions/identifiers with resources you are authorized to inspect.

### 21.1. List ElastiCache Clusters

~~~bash
aws elasticache describe-cache-clusters \
  --region ap-southeast-1 \
  --show-cache-node-info \
  --query "CacheClusters[].{Id:CacheClusterId,Engine:Engine,Version:EngineVersion,Status:CacheClusterStatus,NodeType:CacheNodeType,Nodes:NumCacheNodes}" \
  --output table
~~~

Verify engine, version, node type, and node count. Do not assume `describe-cache-clusters` alone shows full replication-group or cluster-mode topology.

### 21.2. Inspect Replication Groups

~~~bash
aws elasticache describe-replication-groups \
  --region ap-southeast-1 \
  --query "ReplicationGroups[].{Id:ReplicationGroupId,Status:Status,ClusterMode:ClusterEnabled,MultiAZ:MultiAZ,AutomaticFailover:AutomaticFailover,NodeGroups:NodeGroups}" \
  --output json
~~~

Check cluster mode, Multi-AZ, automatic failover, and node group membership. Endpoints/configuration details vary by topology; never hard-code IPs from output into applications.

### 21.3. Inspect Parameter Groups

~~~bash
aws elasticache describe-cache-parameters \
  --region ap-southeast-1 \
  --cache-parameter-group-name cache-lab-params \
  --output json
~~~

Parameter groups and supported settings depend on engine and version. This command makes no edits; changing parameters requires a dedicated change workflow.

### 21.4. Inspect DAX Clusters

~~~bash
aws dax describe-clusters \
  --region ap-southeast-1 \
  --query "Clusters[].{Name:ClusterName,Status:Status,NodeType:NodeType,Nodes:TotalNodes,Endpoint:ClusterDiscoveryEndpoint}" \
  --output json
~~~

Use DAX endpoints only with compatible DAX clients. Never feed this endpoint to a Redis client or Spring Data Redis connection factory.

### 21.5. Inspect CloudWatch Metrics Metadata

~~~bash
aws cloudwatch list-metrics \
  --region ap-southeast-1 \
  --namespace AWS/ElastiCache \
  --metric-name CacheHits

aws cloudwatch list-metrics \
  --region ap-southeast-1 \
  --namespace AWS/ElastiCache \
  --metric-name Evictions
~~~

`list-metrics` lists available series metadata rather than returning datapoint arrays for analysis. Use the CloudWatch Console or `get-metric-data` with proper dimensions and time ranges to examine trends.

## 22. Case Study: Cache-Aside for a Product Catalog

### 22.1. Context

A storefront has:

~~~text
Application:       Spring Boot on ECS Fargate
Source of truth:   Amazon Aurora PostgreSQL
Cache:             Amazon ElastiCache Valkey
Traffic:           8,000 product reads/s at peak (assumed)
Writes:            20 product updates/s
Freshness target:  Description < 5 minutes; price < 30 seconds
Availability:      Cache may fail, but the DB must stay protected
~~~

### 22.2. Design

- Cache-aside for product details.
- Keys include schema version, tenant ID, product ID, and locale.
- 5-minute TTL for descriptions; 30-second TTL plus event invalidation for prices.
- DB update and outbox event in a single transaction.
- Worker reads the outbox and deletes or version-bumps related keys.
- TTL jitter reduces avalanches during cache warm-up.
- Single-flight refresh for hot products.
- App DB fallback gated by a semaphore/concurrency cap on cache errors.
- ElastiCache placed in private subnets with TLS/auth and Multi-AZ topology.

### 22.3. Price Update Flow

~~~mermaid
sequenceDiagram
    participant API as Product API
    participant DB as Aurora
    participant O as Outbox
    participant Q as SQS
    participant W as Invalidation worker
    participant C as ElastiCache
    API->>DB: UPDATE price + INSERT outbox
    DB-->>API: Commit
    API-->>API: Return committed product
    O->>Q: Publish ProductPriceChanged
    Q->>W: Deliver event
    W->>C: DEL / version bump
    Note over C: Next request loads latest value
~~~

Events can arrive delayed or duplicated, so the worker must be idempotent. Between DB commit and invalidation, the cache may serve the prior price within contract bounds; checkout must still verify authoritative prices in the source of truth before confirming orders.

### 22.4. During Cache Cluster Failover

1. Clients hit timeouts/connection resets and reconnect with backoff.
2. Circuit breakers limit requests piling up on cache timeouts.
3. Application DB fallback enforces a concurrency cap rather than sending all 8,000 requests/s straight to Aurora.
4. Once the cache recovers, batch-warm hot keys.
5. Monitor hit ratio, evictions, DB CPU, and API p99 to confirm recovery.

### 22.5. Metrics to Measure

Do not set an arbitrary "99% hit ratio" goal. Measure:

- Database QPS and CPU before/after.
- Cache hit/miss ratio by cache region.
- Product endpoint p50/p95/p99 latency.
- Invalidation lag and stale response counts.
- Cache memory/evictions and hot-shard load.
- ElastiCache cost, data transfer, and realized database savings.

## 23. Reinforcement Exercises

### Exercise 1 — Cache-Aside

A `GET` product request arrives for the first time with no cache entry. Describe the sequence of steps.

**Guidance:** lookup cache → miss → read source of truth → populate cache with TTL → return data. Subsequent reads can hit.

### Exercise 2 — Write-Through and Partial Failure

The database commit succeeds, but `Redis SET` fails. Should the API return success?

**Guidance:** depends on the API contract. Since the DB already committed, do not pretend it rolled back; trigger invalidation/outbox/reconciliation. The caller needs accurate business status and must not blindly retry the write into duplicates.

### Exercise 3 — Choosing TTL

Product descriptions change a few times a day; flash-sale prices change every minute. Should both use a 30-minute TTL?

**Guidance:** no. Pick TTLs by freshness risk; prices need short TTLs/event invalidation plus authoritative DB verification at checkout.

### Exercise 4 — Cache Stampede

A key expires and 2,000 requests miss simultaneously. Propose at least three mitigations.

**Guidance:** single-flight, safe distributed locks, stale-while-revalidate, refresh-ahead, TTL jitter, and DB fallback limits.

### Exercise 5 — TTL and DynamoDB

A DynamoDB item's `expiresAt` has passed, yet it still shows up in `Query`. Is TTL broken?

**Guidance:** not necessarily. DynamoDB TTL deletes asynchronously; the application must filter by timestamp if expired items cannot be used.

### Exercise 6 — Choosing an AWS Service

An app needs a Redis sorted set for player rankings. Should you choose DAX or ElastiCache?

**Guidance:** ElastiCache Valkey/Redis OSS fits the sorted set data structure. DAX is strictly for DynamoDB.

### Exercise 7 — Lost Memcached Node

A Memcached node is replaced and many keys vanish. Did the system lose authoritative data?

**Guidance:** if the cache only held reconstructible copies, the database remains the source of truth; the app experiences misses and must protect the DB from a cold-start surge.

### Exercise 8 — Tenant Leakage

A cache key uses only product ID, even though the same product ID can exist across two tenants with different prices. What can go wrong?

**Guidance:** one tenant can receive another tenant's price. Add a tenant namespace and enforce authorization; obscure keys never replace access control.

### Exercise 9 — Rising Evictions

Hit ratio drops while `Evictions` climbs steadily. What investigations should you run?

**Guidance:** working set/memory sizing, value sizes, TTLs, eviction policy, hot keys, replication overhead, and memory fragmentation.

### Exercise 10 — DAX Consistency

A screen requires a strongly consistent read right after updating DynamoDB, while the app reads through DAX. What must you verify?

**Guidance:** DAX routes strongly consistent reads to DynamoDB per supported semantics; confirm the client/API call actually requests strong consistency rather than assuming all cache reads are strong.

### Exercise 11 — Cache Outage

ElastiCache loses connectivity during peak traffic. Why can unbounded fail-open bring down Aurora?

**Guidance:** all misses/fallbacks hit the DB simultaneously. Use circuit breakers, bulkheads, semaphores, rate limits, and appropriate stale policies.

### Exercise 12 — Invalidation Race

Reader A reads version 10, writer B commits version 11 and deletes the key, then A writes version 10 back into cache. How do you reduce this risk?

**Guidance:** versioned keys, conditional version checks/atomic scripts, locking/coalescing, and outbox ordering; TTL only caps the stale window without eliminating the race.

## 24. Production Deployment Checklist

- [ ] Defined source of truth and freshness contracts for each data type.
- [ ] Selected cache-aside/write-through/write-around/write-behind matching read/write ratios.
- [ ] Cache keys include tenant, locale, version, and all output-affecting dimensions.
- [ ] TTLs are grounded in SLAs, with jitter/refresh strategies where needed.
- [ ] Post-commit DB invalidation uses outbox/retries/idempotency or reconciliation.
- [ ] Tested cache stampedes, hot keys, negative caching, and cache avalanches.
- [ ] Benchmarked eviction policies, working set, memory headroom, and node sizing.
- [ ] Chose ElastiCache Valkey/Redis OSS, Memcached, DAX, or local cache matching access patterns.
- [ ] Tested cluster mode/client topology, Multi-AZ, failover, and reconnects.
- [ ] Configured short application cache timeouts, circuit breakers/bulkheads, and DB fallback concurrency caps.
- [ ] Verified no sensitive data leaks into keys/values/logs and validated tenant isolation.
- [ ] Configured TLS, encryption at rest, secrets, ACL/IAM, and security groups with least privilege.
- [ ] CloudWatch/app metrics cover hits/misses, latency, evictions, memory, replication lag, and stale responses.
- [ ] Prepared runbooks for cache failover, warm-up, cache flush/invalidation, and downstream overload.
- [ ] Compared cache, data transfer, replica, backup costs against realized database savings.
- [ ] Verified the cache is not used as a durable source of truth without dedicated durability/recovery design.

## 25. Key Takeaways

**Cache-aside, write-through, and TTL** are three complementary decisions:

1. **Cache-aside** loads only data actually read; misses fetch from the source of truth and populate the cache.
2. **Write-through** updates cache and backing store in the same write path per a clear contract; it does not create an automatic distributed ACID transaction.
3. **TTL** bounds freshness windows; event-driven invalidation reacts quickly when data changes.
4. Caches can go stale, evict entries, or lose data on node failures. Design idempotency, outboxes, stampede protection, bounded fallbacks, and reconciliation.
5. **ElastiCache Valkey/Redis OSS**, **Memcached**, and **DAX** fit distinct workloads. DAX is dedicated to DynamoDB and does not replace Redis.
6. Redis/Memcached/DAX cache TTLs differ from **DynamoDB TTL**, which deletes items asynchronously.
7. A cache only delivers value when you measure latency, correctness, downstream load, and cost—not hit ratio alone.

Good cache design is not about caching as much as possible. It is about picking the right reconstructible data, defining clear freshness contracts, shielding the source of truth during misses/outages, and proving net benefit with production metrics.

### Official AWS Documentation

- [Amazon ElastiCache User Guide](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/WhatIs.html) — ElastiCache architecture and operations.
- [ElastiCache for Valkey](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/WhatIs.core.html) — Valkey engine and core concepts.
- [ElastiCache for Redis OSS](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/WhatIs.core.html) — Redis OSS-compatible deployments.
- [ElastiCache for Memcached](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/WhatIs.core.html) — cache nodes and Memcached.
- [ElastiCache best practices](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/BestPractices.html) — sizing, connections, and operations.
- [ElastiCache metrics](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/CacheMetrics.html) — CloudWatch metrics.
- [ElastiCache security](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/WhatIs.Overview.html) — networking and service security.
- [DynamoDB Accelerator (DAX)](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DAX.html) — DAX architecture and clients.
- [DAX consistency](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DAX.consistency.html) — strongly/eventually consistent reads.
- [DynamoDB TTL](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TTL.html) — expiration and asynchronous item deletion.
- [Redis commands](https://redis.io/docs/latest/commands/) — TTL, EXPIRE, eviction, and key operations.
- [Spring Cache abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html) — cache annotations.
- [Spring Data Redis](https://docs.spring.io/spring-data/redis/reference/redis.html) — Redis connections, templates, and cache managers.
- [Amazon ElastiCache pricing](https://aws.amazon.com/elasticache/pricing/) — nodes/capacity and costs.
- [Amazon DynamoDB pricing](https://aws.amazon.com/dynamodb/pricing/) — evaluating costs when pairing DAX and DynamoDB.
