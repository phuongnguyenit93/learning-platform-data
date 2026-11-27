# Cache Key Design, Partitioning, and Load Distribution

Caching can reduce latency and offload databases, but its effectiveness depends heavily on how data is identified, placed across nodes, and how requests are distributed. If key design is inconsistent, the same data may be stored under multiple keys or two tenants may accidentally share a key. If partitioning is poor, one node can become overloaded while others sit idle. If a single key is accessed far too often, the system suffers a **hot key** even when total cache capacity and node count remain sufficient.

Cache design for cloud applications must therefore solve three questions simultaneously:

- **Key design:** which requests map to the same cache entry, which tenant/scope does data belong to, and how are versioning and invalidation managed?
- **Partitioning:** which node or shard stores a key, and how are data and requests redistributed when nodes are added or removed?
- **Load distribution:** is traffic balanced across nodes and keys, and how do we detect and handle hot keys, skew, and bursts?

In the **CLOUD_ARCHITECTURE** module, these decisions must align with latency SLOs, consistency, scalability, security, cost, and operations under a Well-Architected mindset. A multi-node cache cluster will not necessarily achieve high throughput if keys are skewed; nor can a good hash function save a single key whose request volume far exceeds one shard's capacity.

## 1. Role of the Cache Key in Architecture

A cache key is the identifier of a stored or recomputed data entry. With cache-aside, the application typically constructs a key from request inputs, reads the cache, handles cache misses by querying the data source, and stores the result under that key.

~~~mermaid
flowchart LR
    CLIENT["Client request"] --> APP["Application"]
    APP --> KEY["Normalize + build cache key"]
    KEY --> CACHE["Cache cluster"]
    CACHE -->|Hit| RESULT["Return cached value"]
    CACHE -->|Miss| DB["Source database"]
    DB --> FILL["Validate + populate cache"]
    FILL --> CACHE
    FILL --> RESULT
~~~

A good key should possess these properties:

1. **Deterministic:** the same logical representation of a request produces the same key.
2. **Collision-safe at application level:** two different pieces of data never accidentally map to the same key due to missing distinguishing components.
3. **Scoped:** differentiates tenant, user, locale, permissions, or data version when those factors affect the output.
4. **Bounded:** length and cardinality are controlled; avoid turning arbitrary inputs into unbounded keys.
5. **Observable:** allows grouping metrics by key type/dataset without exposing sensitive data.
6. **Invalidatable:** has clear rules for deleting or expiring the right entries when the source changes.

### The cache key is part of the data contract

Suppose an API returns product details by product ID. If the result is identical for all users, the key can include data type, schema version, and product ID. However, if the API returns prices by region, language, or customer tier, the key must include every factor affecting the output. Omitting region or customer tier can cause users to receive the wrong price.

Do not mechanically dump every header or request field into the key. Include only factors that genuinely alter the result; irrelevant fields inflate cardinality and lower the hit ratio.

## 2. Structuring Keys with Namespaces

An operationally friendly convention splits keys into components:

\[
\text{key}=\text{namespace}:\text{schemaVersion}:\text{scope}:\text{entity}:\text{variant}
\]

Examples:

| Cache Entry | Illustrative Key | Meaning |
| --- | --- | --- |
| Product detail | product:v3:global:sku-1042 | Detail representation under schema v3 |
| Tenant-scoped list | catalog:v2:tenant-17:category-8:page-1 | Tenant-specific results |
| Locale-specific profile | profile:v1:user-482:vi-VN | Profile displayed in Vietnamese |
| Access permissions | authz:v4:tenant-17:user-482:resource-93 | Scoped authorization result |
| Daily exchange rate | fx:v1:USD-VND:2026-11-18 | Data by currency pair and date |

These keys are examples only; personal data or secrets should not be placed verbatim in keys because keys may appear in logs, metrics, or cache admin tools. Use internal identifiers or stable hashes when obfuscation is needed, while still enforcing access control on the cache.

### Avoiding key collisions from naive string concatenation

If fields are joined with a delimiter without escaping or length-prefixing, two distinct tuples can produce the same string. For example, (a, bc) and (ab, c) become ambiguous when concatenated directly. Safer practices:

- Normalize data types and encoding.
- Use a delimiter with explicit escaping rules or structured serialization.
- Optionally length-prefix each component before hashing.
- Use fixed namespace names and schema versions.
- Test values containing delimiters, Unicode, empty strings, nulls, and special characters.

Hashing keys yields fixed lengths, though it does not automatically prevent logical collisions; if a truncated hash is too short, two inputs can still collide. For critical data, store a key fingerprint and verification metadata, or choose a hash length sized to your threat and performance model.

### Distinguishing cache keys and partition keys

A cache key identifies an entry. A partition key is the component or value used to determine which shard owns the entry. Many systems hash the cache key directly to select a partition; some allow declaring a hash tag or separate partition key. If the partition key differs from the cache key, ensure co-accessed entries land together as intended and the system can route requests accurately.

For example, a cache storing shopping cart data:

- Entry key: cart:{customer-42}:metadata.
- Related keys: cart:{customer-42}:items, cart:{customer-42}:discount.
- A hash tag or customer ID can keep keys for the same cart on a single shard if supported by the platform.

This allows certain multi-key operations to execute within one partition, though it can create a hot partition if a single customer generates massive traffic or if the hash tag is too broad.

## 3. Namespacing by Tenant, Environment, and Version

In multi-tenant systems, keys must isolate data scopes to prevent cross-tenant leaks. Tenant ID is typically a key component when the cache holds tenant-specific data. However, tenant ID is not an authorization mechanism: the application must still verify permissions before returning a cache hit.

Useful namespaces:

- **Environment:** prod, staging, dev to prevent accidental cache sharing.
- **Application/domain:** catalog, booking, pricing, identity.
- **Schema version:** v1, v2 when formats or semantics change.
- **Tenant/region/locale:** when output depends on scope.
- **Data classification:** separate public and sensitive data per policy.

### Versioning keys on schema changes

If the same key is used before and after changing a data structure, old instances may fail to deserialize new payloads or vice versa. Adding a schema version to the namespace enables staged rollouts:

1. New application version writes v2 keys.
2. During transition, it can read v2 and fall back to v1 if the contract allows.
3. Once all consumers are on v2, stop reading/writing v1.
4. Let TTL/lifecycle expire old keys or delete them in verified batches.

Do not keep dual-read logic indefinitely, as it increases complexity and obscures which data is authoritative.

### Key separation does not replace security isolation

For sensitive data, consider dedicated caches, separate accounts/projects, key encryption, network boundaries, IAM, and appropriate TTLs. If one cache instance stores both authentication tokens and public catalogs, assess whether the same operators, backups, debug dumps, and admin roles can read all data.

## 4. Normalizing Inputs Before Key Construction

Two business-equivalent requests with different input representations can produce different cache keys, lowering the hit ratio. Before building a key, normalize:

- Case folding if the system treats uppercase and lowercase as equivalent.
- Unicode normalization for names or search strings where appropriate.
- Date/time normalization to a standard timezone/format.
- Sorting unordered parameter sets (such as set-like filters).
- Stripping query parameters that do not affect the output.
- Consistent representation of numbers, decimals, and booleans.
- Normalizing default values and nulls under the same contract.

Example of two URLs:

- /products?category=books&sort=price
- /products?sort=price&category=books

If parameter order does not affect results, both requests should produce the same key. However, for an ordered list such as workflow steps or ranking rules, never sort because order carries meaning.

### Avoid over-normalization

Incorrect normalization can cause two distinct requests to share a cache entry. Examples:

- Merging vi-VN and en-US locales even though responses are translated.
- Rounding monetary amounts and losing business precision/units.
- Dropping customer tier from keys for contract-based pricing.
- Dropping permission scope from keys for responses with role-hidden fields.
- Sorting an ID list when the response preserves input order.

The rule is: **only treat two inputs as equivalent when the business output is genuinely equivalent**.

## 5. TTL, Invalidation, and Data Versions in Keys

TTL governs how long a cache entry may exist from creation or update per cache semantics. TTL bounds the staleness window when exact invalidation is impossible, but it does not replace consistency rules.

Common strategies:

| Strategy | Goal | Considerations |
| --- | --- | --- |
| **Fixed TTL** | Simple, automatic expiration | Many keys can expire together if created in a batch |
| **Jittered TTL** | Spread expiration times | Must define min/max and avoid exceeding stale tolerance |
| **Explicit invalidation** | Delete key when source changes | Race condition between stale reads and cache fills |
| **Versioned keys** | New data uses a new namespace/version | Old keys remain until TTL/lifecycle cleanup |
| **Write-through/update** | Update cache in the write flow per policy | Complex with multiple cache consumers or failed updates |

### Version inside the key

For a catalog, the metadata database can maintain each product's version. Keys can include the product ID and current version. When the product changes, the version increments, so subsequent requests construct a new key; old keys go unreferenced and expire naturally. This reduces races between invalidation and cache fills, though it requires a reliable version source and version management.

Another approach uses a shared namespace generation for an entire dataset; increment the generation to invalidate a group of keys. Avoid using a single global version for all data if minor updates would cause the entire cache to miss simultaneously.

### TTL jitter and preventing expiry storms

If a batch writes millions of keys with the exact same 10-minute TTL, they can expire almost simultaneously and flood the database. Adding random jitter within allowed bounds spreads expirations out. For example, a 600-second base TTL can add or subtract a small margin based on stale tolerance. Jitter must never let sensitive data live longer than business policy permits.

## 6. Cache Partitioning: Why Sharding Is Needed

When a single cache node lacks sufficient memory, throughput, or connection capacity, the system can split data across multiple nodes (**partitioning/sharding**). Each shard owns a portion of the keyspace; clients or proxies route requests to the shard owning the key.

~~~mermaid
flowchart TB
    APP["Application / cache client"]
    ROUTER["Key routing"]
    S1["Shard A"]
    S2["Shard B"]
    S3["Shard C"]
    APP --> ROUTER
    ROUTER -->|Keys in range/hash A| S1
    ROUTER -->|Keys in range/hash B| S2
    ROUTER -->|Keys in range/hash C| S3
~~~

Sharding provides:

- Higher total capacity by combining memory across multiple nodes.
- Higher throughput when keys are well distributed and requests are independent.
- Partial fault and load isolation per shard.
- Horizontal scaling when one node is no longer enough.

Yet sharding also adds complexity:

- Clients must know where keys live or route through a proxy/router.
- Adding or removing shards can alter mappings and require data movement.
- Multi-key operations may be unsupported if keys reside on different shards.
- A hot shard can overload even while total cluster capacity remains available.
- Failover, backups, monitoring, and resharding require operational processes.

### Partitioning strategies

| Strategy | Distribution Method | Pros | Limitations |
| --- | --- | --- | --- |
| **Range-based** | Splits keys by value ranges | Easy range queries and locality | Skew if one range is heavily active |
| **Hash-based** | Hashes key then selects shard | More uniform distribution with a good hash | Range queries difficult; changing shard count can remap many keys |
| **Directory-based** | Lookup table mapping key/tenant to shard | Flexible placement control | Directory requires HA, caching, and consistency |
| **Tenant-based** | Assigns each tenant or group to shards | Isolates large tenants and simplifies quotas | Large tenants create hot shards; new tenants need placement |
| **Composite** | Combines tenant, hash, or range | Can balance isolation and distribution | Complex routing and migrations |

No partitioning strategy is universally best. Choose based on query patterns, key cardinality, tenant distribution, key count, multi-key operations, and growth rate.

## 7. Hash-Based Partitioning

A simple method hashes the cache key and takes the modulo by the shard count:

\[
\text{shard}(key)=H(key)\bmod N
\]

Where H is the hash function and N is the number of shards. If the hash distributes evenly and keys have a reasonable distribution, key counts split fairly uniformly.

### Limitations of modulo when adding nodes

Suppose you start with 4 shards. When scaling to 5 shards, the modulo over N changes for most keys; many keys must move nodes even though the data itself has not changed. This can cause:

- Mass cache misses and increased database load.
- Cost of copying or rehydrating data.
- Higher network traffic and latency during transition.
- Clients using mismatched mappings during non-atomic rollouts.

Modulo hashing works for some small clusters or systems that accept cache flushes on topology changes. If you need to minimize key remapping, consider consistent hashing or other placement algorithms.

### Hash functions and distribution

A hash function must distribute well across real keys, run fast, and remain stable across clients and runtimes. Avoid language default hashes if values can vary across processes, runtime versions, or were not designed for distributed routing. All clients must share the same algorithm, seed, encoding, and mapping version.

Do not apply an unguarded hash to user-supplied inputs if attackers can craft intentional key collisions; hash choice and key constraints must account for the threat model.

## 8. Consistent Hashing and Virtual Nodes

Consistent hashing places both nodes and keys onto a hash ring. Each key is assigned to the next node clockwise along the ring. When adding or removing a node, only the slice of keyspace around that node changes owners, rather than remapping everything as in simple modulo hashing.

~~~mermaid
flowchart LR
    subgraph RING["Hash ring (linear illustration)"]
      direction LR
      P0["0"] --> A["Node A"]
      A --> P1["Token 25"]
      P1 --> B["Node B"]
      B --> P2["Token 50"]
      P2 --> C["Node C"]
      C --> P3["Token 75"]
      P3 --> D["Node D"]
      D --> P4["100 / wraparound"]
    end
~~~

The diagram illustrates ring positions; in real implementations, the hash space is typically a numeric ring and each node holds one or more tokens. A key is assigned according to the defined successor rule.

### Adding a new node

When adding Node E at a ring position, E takes over only a portion of the keyspace segment previously owned by its successor node. Remaining nodes retain ownership of most existing keys. Thus, the volume of data moved is substantially smaller than full remapping.

### Virtual nodes (vnodes)

If each physical node holds only one token, key distribution can become skewed by token placement. Virtual nodes assign multiple tokens per physical node around the ring, splitting the keyspace into smaller segments:

- Reduces the impact of an unlucky token position.
- Improves capacity and request balance when key counts are large.
- Supports weighted assignment by granting more vnodes to stronger nodes.
- Lets nodes join or leave the ring in smaller increments.

Vnodes do not automatically guarantee balanced request load. Key hashes may be uniform while a few hot keys dominate traffic; nodes with more vnodes can also absorb disproportionate workloads. Measure capacity, operations/second, CPU, network, and latency.

### Consistent hashing is not free

- Must store and synchronize ring membership and topology versions.
- Node joins/leaves create transition windows where keys may not yet be copied.
- Cache misses can spike in key ranges changing ownership.
- Old and new clients must use compatible routing maps.
- Failovers must distinguish transient disconnects from permanent node removals to avoid churn.

Some cache services manage sharding server-side; clients only talk to a cluster endpoint. Others require client libraries or proxies that understand hash slots/partitions. Know where routing happens and how topology updates propagate.

## 9. Hash Slots and Service-Managed Partition Topologies

Some cache clusters avoid direct client-side rings and instead divide the keyspace into **hash slots**. For example, a cluster defines a fixed slot count; keys hash to a slot, and slots are assigned to nodes. When scaling, the system migrates a subset of slots between nodes.

Pros of slots:

- Fixed partitioning units simplify placement management.
- Groups of slots can migrate without changing the hash function.
- Cluster clients can fetch a topology map for routing.
- Multi-key operations may be permitted when keys share a slot, depending on the service.

Cons:

- Topology changes require client and server coordination.
- Slot migrations can introduce latency, cross-node redirects, or cache misses.
- A hot slot can still create a hotspot on its owning node.
- Multi-key transactions typically require keys to reside in the same slot or partition.

Some systems support hash tags: the substring inside braces per service rules is hashed, placing keys with the same tag into the same slot. This is convenient for multi-key cart operations, though tagging everything by a massive tenant creates a hot slot.

Never assume hash tag syntax is identical across products. Verify exact algorithms, escaping rules, and how untagged keys behave.

## 10. Load Distribution and Measuring Balance

Equal key count does not mean equal load. A shard might hold 20% of keys while receiving 70% of requests because keys vary in access frequency. Observe at least three dimensions:

1. **Data distribution:** key count, byte volume, and item count per shard.
2. **Request distribution:** hits, misses, reads, writes, deletes, and operations/second per shard/key class.
3. **Resource distribution:** CPU, memory, network, connection count, evictions, and latency per node.

### Key metrics

| Metric | Detects |
| --- | --- |
| Keys/bytes per shard | Capacity imbalance |
| Ops/sec per shard | Request/throughput skew |
| p95/p99 latency per shard | One shard slower than the rest |
| CPU and network per node | Compute or bandwidth overload on a node |
| Memory fragmentation/used memory | Effective capacity and allocation health |
| Evictions per shard | Memory shortage or mismatched TTL/eviction policy |
| Hit ratio by namespace | Ineffective key design or TTLs |
| Connection count/queue depth | Client fan-in or communication bottlenecks |

### Skew

Skew occurs when a subset of keys, tenants, or partitions accounts for most data or load. Causes include:

- A large tenant far exceeding the median.
- Current day/hour keys receiving far more requests than historical keys.
- A featured product accessed repeatedly.
- A fast-growing prefix/range over time.
- A partition key lacking dispersion, funneling all writes into one shard.

Never monitor averages alone. Track p95/p99 across shards, max-to-median ratios, and load distribution by tenant/key class.

## 11. Hot Keys and Hot Partitions

A **hot key** is a key receiving read or write volume far exceeding other keys. Because a key usually routes to a single shard, every request for that key hits the same node. Adding nodes to the cluster does not automatically split a single key if routing still maps it to one partition.

For example, a featured product page receives 40,000 requests/second while all other products combined receive 20,000 requests/second. The hash function may evenly spread millions of keys, yet the node holding the featured key absorbs most of the load.

### Warning signs

- An unusually high request rate for one key, namespace, or tenant.
- One shard showing elevated CPU/network/latency while others remain normal.
- High cluster-wide hit ratio while p99 latency spikes for certain requests.
- High connections/queues on the hot node; concentrated evictions or timeouts.
- Sudden surges in repeated requests for a single resource like product detail, config, or a global counter.

### Mitigations

| Mitigation | Approach | Trade-offs |
| --- | --- | --- |
| **Local/in-process cache** | Keep a read-only copy near application instances for public, low-sensitivity keys | Multiple copies and more complex invalidation |
| **Replicate hot keys** | Create multiple read replicas/copies and spread client reads | Writes and invalidation need fan-out; reads must pick sufficiently fresh copies |
| **Key salting** | Append suffixes/buckets to spread a group of requests across multiple keys | Unsuitable when updating/reading a single atomic value; requires merging or fan-in |
| **Request coalescing** | Combine concurrent cache misses for the same key into one source call | One slow request can block multiple callers; requires timeouts |
| **Rate limiting** | Cap requests per key/tenant/user | Can degrade UX if thresholds are misconfigured |
| **TTL/stale serving** | Serve old copies within allowed windows while refreshing in background | Fits only data classes tolerating staleness |
| **Pre-warming** | Pre-populate popular keys before campaigns | Requires forecasting and maintaining hot-key lists |

### Local cache for read-heavy data

A multi-tier structure:

~~~mermaid
flowchart LR
    APP["Application instance"]
    L1["L1 local cache"]
    L2["L2 distributed cache"]
    DB["Source database"]
    APP --> L1
    L1 -->|Miss| L2
    L2 -->|Miss| DB
    DB --> L2
    L2 --> L1
~~~

A local cache cuts network hops and offloads the distributed cache for hot keys. However, it requires short TTLs, invalidation/pub-sub, or version checks; otherwise, different app instances may serve different versions. For sensitive data or authorization, evaluate stale permissions and never share L1 across tenants or unsafe request contexts.

### Replicating hot keys for reads

A read-only key can be duplicated across multiple physical keys (copies/replicas), with requests picking one of them. On updates, the system writes synchronously or asynchronously to all copies. Define:

- When is a write considered complete?
- How long may an old copy be served?
- How do we ensure new copies received the version?
- If one copy disconnects, which copy does the router pick?
- Can stale copies be bypassed to read the primary?

Do not replicate a counter requiring exact increments and sum them arbitrarily without clear semantics; updates can be lost or double-counted.

### Key salting and its limits

Salting can split a view counter across multiple buckets:

\[
\text{key}_i=\text{views}:\text{product-42}:\text{bucket-}i
\]

Each writer picks a bucket, and reads sum all buckets. This eliminates the write hotspot, though it adds read fan-out cost and requires idempotent retry handling so one event is not added multiple times. Do not arbitrarily salt state requiring a single authoritative value such as available inventory or permission state.

## 12. Request Coalescing, Stampedes, and Thundering Herds

A cache stampede occurs when a key expires or is evicted and many concurrent requests miss and call the source together. For popular keys, the database suffers a massive burst even if the normal hit ratio is very high.

### Mechanisms to reduce stampedes

- **Single-flight/request coalescing:** only one worker fetches data for the key; other requests wait for the shared result.
- **Refresh-ahead:** refresh the cache before expected expiration.
- **Stale-while-revalidate:** continue serving stale data within allowed limits while one worker refreshes in the background.
- **TTL jitter:** spread expiration timestamps across keys.
- **Negative caching:** briefly cache not-found results to block repeated source queries.
- **Rate limiting/cache miss admission:** cap concurrent fetches when the source is overloaded.

### Careful negative caching

If an ID does not exist, caching not-found results can reduce load when bots or clients repeatedly request the same ID. However, if the resource is newly created, stale not-found entries can mask new data. Keep TTLs short, invalidate explicitly on creation, and never cache 5xx errors as non-existent resources.

### Stale-while-revalidate

An entry can have two thresholds: fresh-until and stale-until. Before fresh-until, serve normally; between the two, serve stale and launch a refresh; past stale-until, fetch fresh data or return an error/fallback per policy. Enforce limits on concurrent refreshes per key and timeouts to avoid runaway refresh workers.

### Thundering herd during failover

If a cache shard fails over or nodes lose warm cache data, millions of keys can miss simultaneously. Mitigations:

- Ramp up traffic gradually rather than shifting the entire workload at once.
- Rate-limit warming of popular keys.
- Add TTL jitter and cap miss concurrency.
- Use circuit breakers and admission control to protect the database.
- Serve stale data for eligible data classes.
- Monitor database connections, CPU, IOPS, and queues during warm-up.

## 13. Load Distribution at the Client and Proxy Layers

Cache clusters must distribute requests across nodes. Routing choices affect latency, connection counts, topology churn, and failure handling.

| Routing Approach | Mechanism | Benefits | Risks |
| --- | --- | --- | --- |
| **Client-side sharding** | Client library computes key → shard | Fewer hops, direct routing | Every client must stay synced on topology and algorithm |
| **Proxy-based routing** | Clients send to proxy; proxy routes to shard | Hides topology, centralizes policy and telemetry | Proxy can become a bottleneck or failure domain |
| **Managed cluster endpoint** | Service provides endpoint and client protocol managing routing | Reduces manual topology management | Coupled to provider SDK/semantics |
| **Consistent-hash load balancer** | Selects backend by key/affinity | Preserves locality for keys or sessions | Hot keys still hit one backend unless replicated |

### Connections and pooling

With many application instances and many cache nodes, connection counts can multiply. If 100 application replicas each open 20 connections to 12 cache nodes, understand how the library actually allocates connections; never assume each app opens just 20 connections total across the cluster. Manage pooling, timeouts, keepalives, max connections, and reconnect backoff to avoid connection storms during node changes.

### Topology refresh

Client-side routing must update when clusters add/remove nodes, move slots, or fail over. Ensure:

- Topology discovery mechanisms and appropriate refresh intervals.
- Handling redirects and updated cluster maps.
- Handling in-flight requests when a shard changes ownership.
- Retrying only when operations are safe and deadline budget remains.
- Preventing all instances from refreshing simultaneously and overloading the control endpoint.
- Topology versioning to detect clients using stale maps.

## 14. Rebalancing and Adding/Removing Shards

Rebalancing changes how keys/data are distributed across shards to address capacity, performance, or topology changes.

### Why is rebalancing risky?

- Moving data consumes network and CPU, competing with user requests.
- During migration, clients might read from old or new nodes.
- Keys receiving writes may require dual-writes, forwarding, or brief locks depending on the service.
- Outdated clients may still route to old owners.
- Increased cache misses put extra load on the source database.
- Rolling back topology is non-trivial once data movement is partially complete.

### Controlled scaling process

1. **Measure baseline:** bytes/key count, ops/sec, p99, CPU, memory, network, and evictions per shard.
2. **Forecast:** identify which nodes lack capacity/throughput; do not look solely at cluster totals.
3. **Choose algorithm:** consistent hashing, slot migration, range split, tenant move, or managed resharding.
4. **Provision capacity:** new nodes, connection quotas, replication, and network paths.
5. **Canary:** migrate a small slice of keyspace or a subset of tenants.
6. **Monitor:** data integrity, hit ratio, latency, errors/redirects, and source database load.
7. **Expand gradually:** increase migration rate once metrics stabilize.
8. **Finalize and clean up:** remove old ownership, update topology, and decommission unused resources.

~~~mermaid
flowchart TD
    BASE["Baseline + capacity forecast"] --> PREP["Provision new shard"]
    PREP --> CANARY["Move a slice of keyspace"]
    CANARY --> OBS["Measure hit/miss, latency, integrity"]
    OBS --> OK{"Stable?"}
    OK -->|No| PAUSE["Pause / rollback per plan"]
    OK -->|Yes| EXPAND["Expand migration"]
    EXPAND --> VERIFY["Verify ownership + data"]
    VERIFY --> CLEAN["Update topology and cleanup"]
~~~

For pure caches with regenerable data, flushing or lazy rewarming may be preferable to copying everything. However, if the cache holds sessions, coordination state, or data that cannot be quickly reconstructed, never treat it as disposable cache; evaluate a more suitable storage/database tier.

## 15. Replication, Failover, and Load Distribution on Node Failure

Sharding partitions the keyspace; replication creates multiple copies of a shard or key. The two mechanisms serve different goals:

- Sharding primarily increases capacity and aggregate throughput by distributing data.
- Replication primarily increases read capacity, redundancy, and resilience according to system semantics.

A cluster with 6 shards and 1 replica per shard has 12 nodes, but that does not mean write capacity doubles. Writes typically still go through the shard's primary/owner; replicas receive copies synchronously or asynchronously.

### Primary-replica

In a primary-replica model, writes go to the primary while reads may go to the primary or replicas. On failover, a replica can be promoted. Define:

- Replication lag and read consistency.
- Promotion criteria and fencing mechanisms for the old primary.
- Potential loss of unreplicated writes.
- Client topology refresh and redirects.
- How stale replica reads are allowed to be.

For caches of regenerable data, stale reads are sometimes acceptable. For caches holding critical state or driving permission decisions, consider stronger sources and explicit contracts.

### Failover creating new hot shards

When a node fails, another node may absorb traffic from the failed shard. If backup nodes are already near capacity, failover can trigger a secondary overload. Capacity planning must assume at least one failure domain loss and distribute the remaining load safely.

### Split brain and stale topology

During certain network partitions, clients may believe the old primary is still active while the cluster has promoted a new primary. Without fencing/epochs/terms or proper anti-dual-primary controls, writes can diverge. Never improvise failover simply by switching DNS to another node when the cache service uses its own cluster protocol.

## 16. Multi-Key Operations and Locality

Many cache operations read or write multiple keys:

- Fetching metadata and items for a shopping cart.
- Updating a session alongside secondary indexes.
- Checking multi-dimensional rate limits.
- Storing user data and recent activity lists.

If keys span multiple shards, atomic operations or transactions may be unsupported, or require fan-out across nodes. This increases latency and introduces partial failures.

### Co-location by aggregate

One strategy places co-accessed keys in the same partition via an aggregate ID or hash tag. For instance, customer 42's cart keys reside on one shard keyed by cart ID. This eliminates cross-shard operations, though you must check tenant skew and hot aggregate risks.

### Avoid overly broad co-location

Using tenant ID as the partition key for all of a tenant's data can turn a large tenant into a hot shard. You can combine tenant with a subpartition (such as tenant + category or tenant + hash bucket), though operations querying multiple subpartitions must fan out and aggregate.

### Design from query patterns

Before selecting a partition key, list all operations:

| Operation | Keys Read/Written | Atomic Required? | Placement Impact |
| --- | --- | --- | --- |
| Fetch cart | metadata + items | May need consistent snapshot | Can co-locate by cart ID |
| Read product detail | Single key | Rarely written | Can replicate hot keys |
| Check inventory | Single inventory aggregate | Needs atomic/strong source | Do not salt arbitrarily |
| Count page views | Multiple counter buckets | Can be eventual | Shard counters then aggregate |
| Delete tenant data | Multiple keys/prefixes | Must complete in batches | Tenant directory/namespace helps management |

Do not design partition keys purely from data structure. Start from access patterns and consistency requirements.

## 17. Security and Tenant Protection in Caching

Because caches are often seen as a performance layer, they are easily overlooked during security reviews. Yet caches can store PII, session tokens, access permissions, contract pricing, or tenant-private data.

### Key scoping and authorization

- Include tenant/scope in keys whenever output depends on tenant.
- Verify authorization before returning cache hits; never treat a key namespace as access control.
- Never use raw access tokens or sensitive data as keys.
- Use namespaces to separate prod/staging and customer environments.
- Consider dedicated instances/cache databases for tenants with strict isolation requirements.
- Set short TTLs or explicit invalidation for permissions and sensitive data.

### Cache poisoning

If unvalidated input is used to build cache keys or contents, attackers can inject invalid data affecting other users. Validate inputs, bind cache entries to scope/version, protect write paths, and never let clients choose arbitrary cache keys.

### Resource exhaustion

Attackers can generate random keys to inflate cardinality, memory usage, and evictions. Mitigations:

- Cap key length and key counts per tenant.
- Rate-limit misses and writes.
- Cap value sizes.
- Enforce namespace/tenant quotas.
- Monitor key creation rates and evictions.
- Avoid caching arbitrary query parameters indiscriminately.

### Encryption and networking

Use TLS over untrusted networks, private networks/security groups, authentication/ACLs for the cache service, and secret rotation. If the cache holds sensitive data, evaluate encryption at rest, admin permissions, snapshots/backups, and debug tooling. Never leave cache endpoints publicly exposed just because entries have short TTLs.

## 18. Cost and Cache Cluster Sizing

Cache sizing must account for both payload data and overhead:

- Value payloads and key bytes.
- Object/header/allocator overhead.
- Replication copies.
- Fragmentation and reserved memory.
- Eviction headroom.
- Connection buffers and replication backlogs.
- Hot-key replication/local caches if used.

### Rough capacity estimation

Suppose there are 4 million entries, average value size 1.5 KiB, 100-byte keys, and 30% overhead:

\[
\text{Raw estimate}
=4,000,000\times(1,536+100)\times 1.30
\]

\[
\approx 8.51\times 10^9\text{ bytes}\approx 7.93\text{ GiB}.
\]

This is a rough estimate excluding actual fragmentation, replication, connection buffers, engine-specific metadata, and headroom. With one full replica per shard, total physical memory roughly doubles accordingly. Measure actual memory consumption using representative keys/values instead of relying on raw payload size alone.

### Hit ratio and source cost

A high hit ratio can reduce database queries, but it is not the sole objective:

- A hit ratio inflated by overly long TTLs can violate freshness requirements.
- A low hit ratio on high-cardinality keys may not be a bug.
- Hot keys needing local caching can cut network and node costs while raising app memory.
- An oversized cache can cost more than well-optimized database queries.

Track costs across **cache hits/misses, bytes stored, ops, network, node-hours, replication, and how much source database load is offloaded**.

### Eviction policies

When memory fills up, caches evict entries using policies such as LRU, LFU, TTL-based, or no-eviction depending on the engine. Policies directly impact hit ratios and workloads:

- LRU fits when recent accesses strongly predict near-future accesses.
- LFU helps when a set of keys is accessed consistently over long periods.
- TTL expiration fits data with explicit business lifetimes.
- No-eviction can fail writes when full; suitable when strict control is required and the application handles failures.

Never choose an eviction policy by name alone. Measure access patterns, memory pressure, churn, and tail latency.

## 19. Operations: Metrics, Logs, and Runbooks

### Minimum dashboard

| Category | Metrics |
| --- | --- |
| Hit/miss | Hit ratio, miss rate by namespace, negative cache hits |
| Capacity | Memory used/free, fragmentation, keys, bytes, evictions |
| Throughput | Ops/sec, reads/writes, bandwidth, command latency |
| Distribution | Per-shard CPU/memory/ops/p99, max-to-median ratio |
| Hot keys | Top key classes/hashed key fingerprints, request rates |
| Connections | Active clients, connection errors, reconnect storms |
| Topology | Slot ownership, ring version, shard health, migration progress |
| Replication | Lag, link status, failover/promotion events |
| Source pressure | Database QPS, connection pools, queues, fallback rate |
| Cost | Node-hours, storage bytes, network transfer, backup/replication |

Never place full cache keys containing PII or tokens into metric labels. Use controlled key fingerprints or namespace/tenant tiers; query detailed context through access-controlled logs/traces.

### Situational runbooks

**One hot shard:** identify the namespace/key class, measure ops and resources, inspect tenant/hot keys, and apply rate limits or local/replicated read caches if data allows; do not blindly rebalance when a single key is the cause.

**Rising evictions:** inspect memory, value sizes, TTLs, cardinality, and leaks. Distinguish between traffic growth filling the cache versus non-expiring keys; adjust capacity or lifecycles per policy.

**Cache miss storm:** cap concurrency to the database, enable coalescing/stale serving for eligible datasets, warm keys in batches, and monitor downstream connections/IOPS.

**Node failover:** verify new topology, client refresh, primary/replica roles, and replication lag; throttle traffic ramp-up if the source database is absorbing rehydration load.

**Prolonged resharding:** pause if p99 or error rates breach thresholds, inspect network/CPU and transfer rates, and avoid changing topology concurrently with client upgrades.

**One tenant causing skew:** inspect quotas, hot keys, and access patterns; consider moving the large tenant to a dedicated shard or subpartitioning if operations support it.

## 20. Process for Designing Cache Keys and Partitions

A practical process can follow eight steps:

### Step 1 — Classify data

Document public, tenant-scoped, user-scoped, and sensitive data, plus regenerable caches versus non-losable state. Identify authoritative sources, owners, and acceptable staleness windows.

### Step 2 — Map access patterns

For each data type, measure or estimate read/write ratios, key cardinality, value sizes, request rates, multi-key operations, range queries, and fan-out. Separate normal traffic from campaigns/bursts.

### Step 3 — Define the key contract

Choose namespaces, scopes, schema versions, identifiers, response-affecting variants, and canonicalization. Define max key length, encoding, hashing, and collision-prevention rules.

### Step 4 — Choose partition keys

Evaluate hash distribution, tenant skew, hot keys, locality for multi-key operations, and queryability. Simulate distributions on real or synthetic representative data; avoid using concentrated values like region or large tenants as the sole partition key.

### Step 5 — Select routing algorithm

Modulo, consistent hashing, hash slots, range, or directory-based. Define who holds the topology map, how clients refresh, how nodes join/leave, and acceptable remapping rates.

### Step 6 — Define load strategies

Design local L1 caches, hot-key replication, request coalescing, TTL jitter, stale-while-revalidate, rate limiting, and admission control per data group. Enable stale serving only where business rules allow.

### Step 7 — Plan capacity and failure handling

Size memory, CPU, network, connections, replication, and headroom for node/AZ loss. Estimate cache warm-up, database fallbacks, and resharding costs. Set quotas and autoscaling/alert thresholds.

### Step 8 — Test and operate

Test skew, hot keys, miss storms, failovers, topology refreshes, resharding, multi-tenant isolation, and invalidation races. Maintain per-shard/key-class dashboards, runbooks, and owners.

~~~mermaid
flowchart TD
    DATA["Data classification + authoritative source"] --> ACCESS["Access pattern + load"]
    ACCESS --> KEY["Key contract + namespace"]
    KEY --> PART["Partition key + routing"]
    PART --> LOAD["Hot key / coalescing / TTL"]
    LOAD --> CAP["Sizing + failure capacity"]
    CAP --> TEST["Test skew / failover / rebalance"]
    TEST --> OPS["Dashboard + runbook"]
    OPS --> ACCESS
~~~

## 21. Case Study: Catalog Cache for a Booking Platform

A booking platform has a catalog API with these hypothetical requirements:

- 8 million products/services.
- 70% of requests read product details; 20% read category lists; 10% read prices by region/customer tier.
- Certain featured products can receive 15,000 requests/second.
- Contract prices vary by tenant and customer tier.
- Product details may be stale for up to 30 seconds; prices need a tighter stale window and must be re-verified at booking time.
- Cache cluster starts with 6 shards and must scale out.

### Step 1 — Key design

Sample design:

| Dataset | Key Format | Key Components |
| --- | --- | --- |
| Product detail | product:v3:{productId} | Product ID, schema version |
| Category page | category:v2:{region}:{categoryId}:{page}:{filterHash} | Region, category, page, canonicalized filter |
| Contract price | price:v5:{tenantId}:{customerTier}:{productId}:{currency} | Tenant, tier, product, currency |
| Availability display | availability:v2:{slotId}:{date} | Slot/date; display only |

Display availability may be stale per policy, but booking must re-check capacity at the authoritative write source. Contract pricing must include tenant/tier/currency in the key to prevent cross-tenant pricing errors.

### Step 2 — Partitioning

Product details can be hashed by key for even distribution. Category pages can also hash by full key; however, a large category's first page can become very hot. If category pages need separate caching, monitor hot keys and replicate read-only copies if needed. Contract pricing has higher cardinality and requires per-tenant quotas so large tenants do not evict everyone else.

Choose consistent hashing or hash slots depending on the cache service; all clients must share the same topology/routing contract. Avoid modulo node count if resharding happens frequently and warm-up cannot absorb large remaps.

### Step 3 — Hot keys

For featured products:

1. Short-TTL local L1 cache for public data, if the 30-second stale window permits.
2. Per-instance request coalescing to collapse misses.
3. Read replicas/copies if one shard stays hot; refresh copies by product version.
4. Rate-limit anomalous traffic by product/tenant.
5. Pre-warm the hot product list before campaigns.

Never replicate contract pricing if tenants have distinct access rules without verified key scoping and cache isolation. Never use stale local caches for booking commits.

### Step 4 — Invalidation and versioning

When a product updates, the source increments its version. Cache keys can embed the product version or use event invalidation. Event publishers use an outbox to avoid dropping invalidation events after commits; consumers are idempotent with replay support. During propagation, L1 caches may serve stale entries up to the allowed window. For prices, use shorter TTLs and re-verify at the source during booking.

### Step 5 — Capacity and load distribution

Measure bytes and ops per shard; do not simply divide 8 million keys by 6 shards. Check hot product lists, category pages, large tenants, and price payloads. Provision headroom so if one shard fails, remaining nodes absorb the load or selected endpoints degrade gracefully. Post-failover warm-up must cap database fallback load.

### Step 6 — Acceptance criteria

| Objective | Evidence |
| --- | --- |
| Product details stale no more than 30s per policy | Version/TTL/lag telemetry and invalidation tests |
| No cross-tenant/tier price mixing | Cross-tenant tests, key canonicalization, and authorization checks |
| Hot products do not overload shards | Per-key-class ops, local cache hit effectiveness, p99 |
| Resharding does not trigger excessive miss storms | Canary migrations, database fallback load tests |
| Cache failover does not corrupt bookings | Bookings revalidate authoritative availability/price |

## 22. Case Study: Partition-Keyed Counters and Rate Limits

An API tracks product page views and enforces request rate limits per user/tenant. The two use cases have different properties:

- Page views tolerate eventual aggregation and small discrepancies over short windows.
- Rate limits control request counts within a window; splitting counters must preserve limit semantics.

### Page views

A single key product:42:views can become a hot key when a product goes viral. It can be split into multiple buckets hashed by application instance or request ID, then aggregated:

\[
\text{views}_{42}=\sum_{i=1}^{k}\text{views}_{42,i}.
\]

Consumers/aggregators must deduplicate events if counter updates arrive via redeliverable events. Totals are eventual and may lag by a few seconds.

### Rate limits

Per-user rate limits can key by user ID and time window. If a user sends massive traffic, that key heats up; yet splitting into multiple counters and summing on every request adds complexity and races. Choose algorithms like token bucket or leaky bucket, define accuracy requirements, and use a single partition owner or atomic script if supported by the cache service.

If hard limits must not be exceeded, never salt counters and let every bucket grant the full quota independently. You can allocate bounded quota leases across buckets or use a serialization point. If approximate rate limiting is acceptable to protect services, local counters periodically summed can work, provided error bounds are documented.

### Lesson from both use cases

Partitioning cannot be separated from consistency. For the same hot-key challenge:

- For view counters, bucketing and eventual aggregation can fit well.
- For spending caps or final booking limits, independent bucketing can break invariants.

Always define **what must remain exact** before deciding how to distribute load.

## 23. Hands-On Exercise and Guided Solutions

A 4-shard cache cluster serves three key groups:

| Group | Key Count | Request Rate | Characteristics |
| --- | ---: | ---: | --- |
| Product detail | 2 million | 30,000 ops/s | 5 featured keys account for 40% of traffic |
| Tenant configuration | 50,000 | 8,000 ops/s | One large tenant accounts for 35% of traffic |
| Session | 1 million | 12,000 ops/s | Keys scoped per user/session, 30-minute TTL |

During a campaign, shard 2 experiences rising p99 latency and evictions while the other three shards still have spare capacity. The backend database starts receiving more queries from cache misses.

### Question 1 — Should we add shards immediately?

**Guided answer:** Not yet. Determine whether shard 2 is hot due to many keys/bytes or one/a few hot keys. If hot keys drive 40% of traffic, adding nodes will not split a single key automatically. If a large tenant concentrates onto one partition key, revisit the tenant/subpartition strategy. Adding shards only helps if total capacity is the bottleneck or data partitioning is unbalanced.

### Question 2 — Propose handling for the 5 hot product keys.

**Answer:** Consider short-TTL local L1 caches, request coalescing, pre-warming, rate limiting, and read-only replicas/copies if data is public and tolerates staleness. Updates/invalidations use versioning/events with lag monitoring; bookings still verify prices/inventory at the authoritative source.

### Question 3 — How do you handle the large tenant?

**Answer:** Measure the tenant's keys, bytes, and ops. Move the large tenant to a dedicated shard via directory mapping, or subpartition by domain/category if queries allow. Apply quotas and a migration plan. Do not split purely on aggregate traffic if multi-key operations require co-location.

### Question 4 — Should sessions be replicated arbitrarily across shards?

**Answer:** Sessions require strict scoping and lifecycles; if using read replicas, understand consistency for updates, logouts, and permission changes. On logout or permission revocation, stale sessions create security risks. Use TTLs, version/revocation state, and authoritative checks for sensitive operations.

### Question 5 — Why are evictions rising on shard 2 while cluster-wide memory still has free space?

**Answer:** Because evictions occur per node/shard or capacity domain; free memory on other shards does not automatically transfer to shard 2. Inspect byte distribution, TTLs, skew, placement, and rebalancing options.

### Question 6 — Which resharding strategy fits?

**Guided answer:** If using hash slots or consistent hashing, migrate a slice of keyspace as a canary while tracking p99, hit ratio, integrity, and database fallbacks. If hot keys are the root cause, fix hot keys first. Coordinate topology/client refreshes so stale maps do not linger.

### Question 7 — What must be tested before failing over a shard?

**Answer:** Ownership maps, primary/replica roles, replication lag, fencing, client redirects/topology refreshes, request retries/idempotency, hit/miss storms, database fallbacks, and recovery times. Also test scenarios where a node is not cleanly dead but network-partitioned.

## 24. Common Mistakes

1. **Keys missing tenant or permission scope:** returns wrong data across tenants or privilege levels.
2. **Keys containing every query parameter:** inflates cardinality and drops hit ratios even for equivalent requests.
3. **Joining keys without escaping rules:** two distinct inputs produce the same key.
4. **Not versioning keys on schema changes:** old and new instances read incompatible payloads.
5. **Using modulo hashing when frequently adding nodes:** remaps nearly all keys and triggers miss storms.
6. **Hashing evenly without measuring traffic:** a single hot key still overwhelms one shard.
7. **Choosing tenant as the sole partition key:** large tenants turn into hot shards.
8. **Using key salting for atomic single-value state:** updates/reads require fan-in and can break invariants.
9. **Adding shards to solve a hot key:** the key still maps to one shard unless intentionally replicated or split.
10. **Replicating hot keys without versioning/invalidation:** copies serve divergent values for too long.
11. **No request coalescing:** a popular key's miss sends a flood of queries to the database.
12. **Identical TTLs for an entire batch:** keys expire simultaneously and cause thundering herds.
13. **Local caches lacking invalidation:** app instances see inconsistent versions.
14. **Resharding the entire cluster at once:** client topology, database fallbacks, and network spike simultaneously.
15. **No headroom for shard loss:** surviving nodes lack capacity to absorb traffic.
16. **Using raw cache keys in metrics:** leaks data and explodes metric cardinality.
17. **Measuring only cluster-wide hit ratio:** misses shards/key classes with severe p99 and evictions.
18. **Treating cache as durable irreplaceable state:** eviction/failover loses business data.

## 25. Cache Design Review Checklist

- Are keys deterministic, canonical, bounded, and collision-safe?
- Do namespaces separate environment, domain, schema version, and tenant scope?
- Does the key capture every factor affecting the response without exploding cardinality?
- Are inputs normalized according to business semantics?
- Are cache keys and partition keys clearly distinguished?
- Does the partition strategy match access patterns, multi-key operations, and tenant distribution?
- Are hash functions/mappings consistent across all clients?
- When adding/removing nodes, how many keys remap and how do clients refresh topology?
- Are hot keys, hot tenants, and skew measured per shard/key class?
- Are local caches, replication, request coalescing, or salting applied only where appropriate?
- Do TTL, jitter, stale-while-revalidate, and invalidation match stale tolerance?
- Can cache misses/failovers overload the database?
- Do replication/failover designs handle lag, fencing, and stale topologies?
- Do IAM, TLS, key scoping, and quotas protect tenants and sensitive data?
- Do dashboards include per-shard latency, memory, evictions, ops, replication, and migration metrics?
- Are canaries, rollbacks, runbooks, and restore/warm-up drills in place?
- Does TCO include nodes, replication, networking, memory overhead, and operations?

## 26. Well-Architected Review

| Pillar | Key Question | Required Evidence |
| --- | --- | --- |
| **Reliability** | If a shard/node fails or topology changes, can the cache and data source recover? | Replication/failover tests, miss storm tests, database headroom |
| **Security** | Do keys isolate tenants and permissions; are endpoints, credentials, and logs secure? | IAM, TLS, namespaces, negative permission tests |
| **Performance** | Do keys/partitions distribute traffic and data well? Are hot keys handled? | Per-shard p95/p99, ops, bytes, hot-key metrics |
| **Cost Optimization** | Are unnecessary keys retained, copies over-replicated, or shards over-provisioned? | Hit ratio, cost per operation, memory/egress, evictions |
| **Operational Excellence** | Are there procedures for adding/removing shards, refreshing topology, invalidating, and handling miss storms? | IaC/configs, canaries, dashboards, runbooks, owners |
| **Sustainability** | Does the cache reduce source resources and avoid unnecessary data duplication? | Database offload, TTL/lifecycle, right-sizing |

Good cache design does more than distribute key counts evenly. It must distribute **capacity and real load**, preserve data boundaries, handle hot keys and topology changes, and protect the database during cache misses or failovers. Design keys and partitions around access patterns and business invariants; then use metrics and testing to prove the cache meets SLOs, cost targets, and operational readiness.
