# Caching with Redis and Offloading Database Access

In the **High Availability Architecture** chapter of the **Oracle Cloud Infrastructure** module, caching reduces database query volume and shortens response times for repeatedly read data. However, a caching tier only improves availability when the application handles stale data, cache misses, connection errors, and cache repopulation.

If the database can only survive traffic while the cache is warm, a Redis incident can immediately overload the database next. Therefore, the design must include **how reads work**, **how updates work**, **load bounds during degradation**, and **how the cache recovers**.

This lesson uses **OCI Cache** as the managed caching service on OCI and **Oracle Database** as the business source of truth. Examples focus on Redis and fundamental operations; verify the actual cluster's engine, version, and supported capabilities.

## 1. Cache Is a Read Copy, Not a Replacement for the Database

In this lesson's design:

- Oracle Database holds the authoritative data and executes business transactions.
- Redis holds a subset of reconstructible data to serve suitable reads.
- The application defines keys, TTLs, access rules, loading logic, and invalidation.
- OCI provisions and operates the infrastructure components within the managed service scope.

“Reconstructible data” means losing the cache does not lose committed business records. Data such as unique payment status, final ownership, or reserved inventory quantities must be protected by appropriate business mechanisms at the authoritative source.

| Data or Workload | Cache Suitability | What Must Be Decided |
| --- | --- | --- |
| Product descriptions, infrequently changing catalog | Usually suitable | Acceptable staleness window |
| Read-heavy summary pages, expensive computations | Potentially suitable | Data dependencies and invalidation strategy |
| User profiles | Potentially suitable | Permission scope, sensitive fields, profile changes |
| Displaying indicative price or stock | Needs an explicit freshness contract | Re-verify at business decision time |
| Confirming payment or reserving inventory | Do not rely solely on a read cache | Transactions, constraints, and checks at the database |
| Rare queries whose results are almost never reused | May not be worth caching | Memory cost and added complexity |

Caching does not fix bad queries or a database missing essential indexes. Before adding Redis, identify which queries drive load and whether repeat reads are high enough for a cache to deliver value.

## 2. OCI Cache in OCI Architecture

### 2.1. Service Name and Cluster Types

OCI Cache is a managed in-memory caching service supporting Redis and Valkey engines per the service's version list. It has two main modes:

- **Non-sharded:** one primary and optional replicas; data is replicated across nodes.
- **Sharded:** data is partitioned across shards; each shard has a primary and configured replicas.

Check current engines and capabilities in [About OCI Cache](https://docs.oracle.com/en-us/iaas/Content/ocicache/overview.htm). Do not assume every feature of the latest Redis or Redis Enterprise exists in the OCI Cache engine.

Replicas add redundancy and can serve suitable read loads. Shards partition data and load across multiple slices. The two mechanisms solve different needs.

### 2.2. Illustrative Deployment Diagram

~~~mermaid
flowchart TD
    U["Client"] --> LB["OCI Load Balancer"]
    LB --> A["Application A"]
    LB --> B["Application B"]
    A --> C["OCI Cache: private endpoint"]
    B --> C
    C --> P["Primary"]
    P --> R1["Replica 1"]
    P --> R2["Replica 2"]
    A --> D["Oracle Database: authoritative data source"]
    B --> D
    D --> E["Outbox or implemented change stream"]
    E --> I["Cache invalidation worker"]
    I --> C
~~~

This is an illustrative architecture, not integrations created automatically when provisioning a cluster. The application, database, and cache each require their own high-availability plan.

For a production non-sharded cluster, Oracle recommends one primary and two replicas. The service attempts to spread nodes across fault domains and availability domains suited to the region. Do not infer that every region has three availability domains or identical placement. [Creating an OCI Cache Cluster](https://docs.oracle.com/en-us/iaas/Content/ocicache/createcluster.htm), [About OCI Cache](https://docs.oracle.com/en-us/iaas/Content/ocicache/overview.htm).

### 2.3. Connectivity Is Part of the Architecture

OCI Cache provides a private endpoint. Over a standard TLS path, clients connect over TCP 6379, verify certificates, and use the service hostname. [Connecting to an OCI Cache Cluster](https://docs.oracle.com/en-us/iaas/Content/ocicache/connecttocluster.htm).

A common layout:

- The application runs in a subnet authorized to reach the cache.
- The cache sits on a private network, with an NSG or security list restricting sources.
- Oracle Database has its own dedicated connection path and access permissions.
- Operational workloads have access paths to Monitoring, authentication services, and secret management as needed.

Compartments organize resources and IAM scopes; they do not create network boundaries. Creating a cluster in the same compartment as the application does not mean the application can connect.

## 3. Choosing Cache-Aside for Repeated Reads

### 3.1. Read Flow

With **cache-aside**, the application actively checks the cache; on a miss, it reads the database and may populate the cache.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Application
    participant R as Redis
    participant D as Oracle Database
    C->>A: Read product description
    A->>A: Check permissions and build cache key
    A->>R: GET key
    alt Valid cache hit
        R-->>A: Cached data
        A-->>C: Result
    else Cache miss
        R-->>A: Key missing
        A->>D: Bounded query
        D-->>A: Source data
        A->>R: SET key value EX ttl
        A-->>C: Result
    end
~~~

Cache-aside only loads data that is actually requested. TTL and invalidation are necessary parts of managing freshness. [Redis cache-aside](https://redis.io/docs/latest/develop/use-cases/cache-aside/).

The flow above is the happy path. Before production, add timeouts, duplicate-load prevention, and database load controls.

### 3.2. Basic Update Flow

One starting approach is:

1. Check permissions and business preconditions.
2. Update Oracle Database.
3. Commit the transaction.
4. Delete affected cache keys.
5. Subsequent reads repopulate the data.

Never delete the cache first and assume the database update is guaranteed to succeed. Nor should invalidation callbacks run before commit if a concurrent reader might immediately reload stale pre-commit data.

If the database commits yet cache deletion fails, the database transaction does not automatically roll back. You need a mechanism to record and retry invalidations; avoid returning ambiguous errors that cause clients to retry non-idempotent business transactions.

### 3.3. Distinguishing Other Patterns

| Pattern | How It Works | Trade-Offs |
| --- | --- | --- |
| **Cache-aside** | App reads cache and loads from source on miss | Simple write path, but requires managing freshness |
| **Read-through** | Cache layer or adapter handles loading from source | Requires a component implementing the loader |
| **Write-through** | Write path coordinates updating source and cache before completing per contract | Higher latency and dual-system error handling |
| **Write-behind** | Writes are accepted in an intermediate layer; source updates later | Risk window for data loss or lag; needs separate durability |

Redis does not automatically know how to query Oracle Database just because an app calls `GET`. Read-through requires a library, adapter, or service to implement it.

For offloading reads from an existing transactional database, cache-aside is typically the easiest starting point to control. The final choice depends on the data contract and error handling.

## 4. Estimating Load Reduction and Load When Cache Fails

Suppose all 10,000 reads per second are cacheable, each miss triggers one database query, and the hit ratio is 95%:

~~~text
DB reads while cache is active =
    read requests × (1 - hit ratio)
  = 10,000 × 0.05
  = 500 reads/second

DB reads when cache is unavailable =
    10,000 reads/second
~~~

Database read load can jump **20x** compared to a warm cache. This is a simplified example excluding writes, secondary queries, and background tasks.

If only part of traffic is cacheable:

~~~text
DB reads ≈
    uncacheable reads
  + cacheable reads × miss ratio
  + reads from refreshes or background work
~~~

Calculations only make sense when units align. One miss request may run multiple queries; another miss may be a single primary-key lookup. Measure query counts, database time, and connection consumption together.

A high hit ratio may barely reduce load if the cache mostly stores cheap queries while expensive queries still always miss.

A critical design requirement is defining the **degraded database load budget**. If the database cannot absorb full uncached traffic, the app must enforce admission control, degraded service levels, or controlled rejection.

## 5. Designing Keys, Payloads, and TTL

### 5.1. Keys Must Reflect Exact Data Scope

Example application-defined key:

~~~text
cache:prod:catalog:tenant-demo:v2:product:p-100:locale:vi
~~~

The key encodes environment, data type, tenant, schema version, entity, and locale. If results also depend on region, filters, or permission groups, include those factors in the key design or authorization check.

Never put emails, tokens, or full personal information inside key names. Those values can surface in operational tools and logs.

For private data, authorization checks must still run before returning cached values. A cache hit is not proof the caller is allowed to read that payload.

### 5.2. Payloads Need Schema and Traceability Metadata

~~~json
{
  "schemaVersion": 2,
  "entityVersion": 42,
  "loadedAt": "2026-11-21T03:00:00Z",
  "data": {
    "productId": "p-100",
    "name": "Sample product",
    "category": "demo"
  }
}
~~~

This is an illustrative schema, not a mandatory OCI Cache format.

`schemaVersion` supports application code rollouts. `entityVersion` can help reconcile with the source if the source supports versioning. `loadedAt` only indicates load time; it does not prove the database snapshot reflects all prior updates.

Do not cache entire ORM entities if they contain sensitive fields, lazy proxies, or unneeded relations. Choose small DTOs with explicit schemas and bounded sizes.

### 5.3. Writing Value and TTL in a Single Operation

Example commands in an authenticated Redis CLI session:

~~~text
SET cache:lab:catalog:v1:product:p-100 '{"productId":"p-100","name":"Demo"}' EX 60
GET cache:lab:catalog:v1:product:p-100
TTL cache:lab:catalog:v1:product:p-100
DEL cache:lab:catalog:v1:product:p-100
~~~

`SET` with `EX` sets the value and expiration in one atomic operation. Splitting `SET` and `EXPIRE` risks crashing between the two commands and leaving a key without a TTL. A plain `SET` can also overwrite an old TTL, so specify the TTL explicitly on every write. [Redis SET](https://redis.io/docs/latest/commands/set/).

Example keys belong to the lab namespace. A 60-second TTL is illustrative only, not a universal recommendation for business data.

### 5.4. Choosing TTL from Staleness Tolerance

TTLs must balance:

- How often data changes.
- Severity of reading stale data.
- Invalidation capability.
- Reload traffic and cost.
- Working set size and memory budget.

You can add **jitter** so keys do not expire simultaneously. For instance, randomize TTL between 48–60 seconds instead of setting every key to 60 seconds. Do not add jitter beyond the business's staleness tolerance.

TTL counts from when a key is written to the cache. It does not guarantee “data is always fresh within X seconds of every database commit,” especially under slow loads, replica lag, or read/write races.

Nor does TTL guarantee a key survives until expiration: eviction, explicit deletion, or crashes can remove keys sooner.

## 6. Invalidation and Stale-Data Races

### 6.1. Commit-Then-Delete Still Has a Race Window

Consider this timeline:

~~~text
T1: Request A misses cache and reads version 41 from database
T2: Request B updates database to version 42 and commits
T3: B deletes the cache key
T4: A finishes slow processing and writes version 41 into cache
T5: Request C reads version 41 from cache
~~~

The `DEL` at T3 succeeded, yet stale data was repopulated at T4. This is why cache-aside with delete-on-write should not be described as strongly consistent.

If bounded staleness is acceptable, short TTLs, bounded load durations, and invalidation may suffice for some data. State those conditions explicitly rather than treating TTL as an absolute guarantee.

### 6.2. Improving Invalidation Reliability with Outbox or CDC

An outbox design can:

1. Update the business record and write a change event in the same database transaction.
2. Commit both together.
3. Have a worker read events and delete affected keys.
4. Track progress and retry on errors.

Events should carry an ID, entity identifier, and version where appropriate. Consumers must be idempotent; issuing `DEL` for an already-missing key still achieves invalidation.

CDC is another option when changes come from multiple applications or direct database tasks. It is an integration requiring configuration, monitoring, and cost accounting.

An outbox prevents losing invalidation intent after commit, yet by itself does not eliminate races from stale loads that began earlier. If a versioned protocol is needed, design the read path, write path, and missing-marker handling together.

### 6.3. Identifying Dependent Keys

Updating a product may affect:

- The product detail key.
- Category pages and filter results.
- Homepage summary blocks.
- Related locale or tenant variants.

Design dependency lists, version groups, or namespace generations accordingly. Never assume deleting one detail key refreshes all aggregate query results.

Never scan the entire keyspace on the update hot path. If a large invalidation wave is needed, rate-limit it and monitor the resulting miss spike.

### 6.4. When Stronger Consistency Is Needed

Options include:

- Returning freshly committed data directly to the updater.
- Bypassing the cache for reads requiring read-your-writes.
- Comparing versions or using a fully designed controlled-loading protocol.
- Reading the authoritative source at business decision points.

A deduplication lock around the loader alone does not synchronize with writers updating the database.

For account balances, newly revoked permissions, or inventory holds, use appropriate source-level consistency rather than relying solely on cache TTLs.

## 7. Preventing Stampede, Avalanche, Penetration, and Hot Keys

| Phenomenon | Mechanism | Mitigations to Consider |
| --- | --- | --- |
| **Cache stampede** | Many requests miss one hot key simultaneously | Single-flight, bounded loading, early refresh |
| **Cache avalanche** | Many keys expire or the cache fails together | TTL jitter, rate-limited warm-up, database protection |
| **Cache penetration** | Repeated lookups for nonexistent entities | Input validation, rate limiting, negative caching |
| **Hot key** | One key receives more load than a node can serve | Shrink payload, L1 if appropriate, distribute reads per contract |
| **Hot shard** | Data or traffic skews onto one shard | Inspect key distribution and partitioning design |

Terminology varies across references; what matters is recognizing the load pattern accurately.

### 7.1. Per-Key Single-Flight

Single-flight lets concurrent requests for the same key share one in-progress load.

Within one instance, an in-flight map and future can coalesce calls. Across multiple instances, local coalescing only merges per instance and does not guarantee a single global database read.

If using a short Redis lock to coordinate loading:

~~~text
SET lock:lab:catalog:product:p-100 UNIQUE_TOKEN NX PX 3000
~~~

The token must be unique per lock acquisition. When releasing, verify the token and delete atomically; never issue a blind `DEL` because the lock may have expired and been acquired by another client. On older versions, an appropriate Lua script can be used if supported by the service and permissions. [Distributed Locks with Redis](https://redis.io/docs/latest/manual/patterns/distributed-locks/).

This is a technique to reduce duplicate loads, not an exclusivity guarantee for financial or inventory transactions. Leases can expire while a loader is still running, or locks can be lost during failover.

Requests that fail to acquire the lock should wait with a strict timeout, use allowed stale data, or go through admission control. If all waiters time out and hit the database together, the stampede is merely delayed.

### 7.2. Soft TTL and Stale-While-Revalidate

Applications can distinguish:

- **Soft expiry:** refresh should begin.
- **Hard expiry or staleness cap:** must no longer be served per contract.

Between those two boundaries, permitted stale data can be returned while only one task refreshes in the background. Do not let every read extend stale data lifetime indefinitely.

If Redis has already expired or evicted the key, no payload remains for stale serving. Supporting this behavior requires storing payload and metadata deliberately, not just setting a TTL and assuming data stays around.

### 7.3. Negative Caching

You can store a short-TTL “does not exist” sentinel for IDs confirmed absent by the source. Delete or invalidate the sentinel when the entity is created.

Never cache timeouts, permission errors, or database errors as “not found.” Nor should you share a “missing” result across permission scopes if visibility depends on the caller.

Negative caching does not replace rate limiting: continuous requests for varying random IDs can still exhaust memory and database capacity.

## 8. Keeping the Database Stable When the Cache Fails

### 8.1. Fallbacks Must Be Bounded

“If Redis fails, read the database” is a fallback path, not a complete high-availability strategy.

Combine:

- **Cache timeout:** fits inside the request time budget.
- **Circuit breaker:** temporarily skips the cache during prolonged failures instead of waiting on every request.
- **Bulkhead:** limits concurrent fallback tasks hitting the database.
- **Rate limiting or admission control:** bounds accepted work.
- **Load shedding:** rejects excess traffic cleanly when capacity is exhausted.
- **Stale fallback:** only for data still within its allowed staleness contract.

A Redis circuit breaker only cuts Redis wait time. It does not reduce database load once all traffic shifts to fallback.

If fallback limits are set per app instance, multiply by max autoscale count. Ten instances each allowing small concurrency can still exceed the global database budget.

### 8.2. Pseudocode for a Protected Read Flow

~~~text
read product description:
    authenticate and authorize caller
    build key with environment, tenant, and schema

    if cache circuit allows:
        attempt Redis read within cache budget
        if valid payload exists and is within allowed contract:
            return result
        if cache errors:
            record error; do not count as a normal cache miss

    coalesce requests for the same key if possible

    if database read permit cannot be acquired within deadline:
        if permitted stale data is available:
            return stale data per contract
        else:
            reject cleanly or route to appropriate wait queue

    with database read permit:
        read source with dedicated timeout
        if database errors:
            return controlled error or permitted stale data
        if source confirms not found:
            consider short-TTL negative cache
        if data exists:
            attempt cache write with chosen TTL and loading protocol
            if cache write fails:
                record error; do not discard successful read result
            return source data
~~~

This pseudocode is not a specific OCI SDK or Redis client API. It illustrates order of responsibilities and where bounds belong.

### 8.3. Classifying Error Behavior

| Incident | Expected Behavior |
| --- | --- |
| Redis timeout or transient disconnect | Bounded fallback, no infinite retries |
| Cache miss or evicted key | Reload with deduplication and database limits |
| Cache `SET` fails after successful DB read | Return source result, emit cache write error metric |
| DB commit succeeds, `DEL` fails | Preserve committed transaction and handle invalidation durably |
| DB errors, permitted stale data exists | Serve degraded data per contract with age limits |
| DB errors, strict correctness required | Report inability to complete; never fabricate state |
| Both cache and DB overloaded | Admission control, prioritize core functions, avoid unbounded queues |

Never configure liveness checks on all app instances to fail merely because an acceleration cache tier is temporarily degraded. Mass restarts wipe L1 caches, spike new connections, and complicate recovery. Health checks must reflect each dependency's true role.

## 9. Replicas, Failover, and Clients on OCI

### 9.1. Replicas Do Not Guarantee Immediate Freshness

Standard Redis replication is asynchronous. Replicas can lag, and writes right before an incident may not reach a node promoted to primary. [Redis replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/).

For reconstructible caches, losing some cached entries may be acceptable if the database stays authoritative. However, dropping an invalidation command or reading a lagging replica can resurface stale data; TTLs and sync behavior still matter.

Reading from replicas only suits consistency levels the application tolerates. If data was just updated and must immediately read fresh, do not assume a replica endpoint will satisfy that.

### 9.2. Using the Right Endpoint

For a non-sharded cluster:

- **Primary endpoint** routes to whichever node currently holds the primary role.
- **Replicas endpoint** routes to replicas and does not necessarily hit the same node.
- **Node endpoint** is bound to a specific node, so do not use it in place of the primary endpoint when you always need the primary.

For a sharded cluster, clients must support cluster mode, hostnames, and appropriate topology discovery. [Connecting to an OCI Cache Cluster](https://docs.oracle.com/en-us/iaas/Content/ocicache/connecttocluster.htm), [OCI Cache Sharded Clusters](https://docs.oracle.com/en-us/iaas/Content/ocicache/shardedclusters.htm).

Never hardcode the current primary's IP address. Clients must handle broken connections, DNS updates, and topology shifts as supported by their library.

### 9.3. Reusing Connections and Bounded Retries

For Java applications, pick clients compatible with TLS and your cluster mode; OCI documentation notes options such as Lettuce and Redisson. Verify library versions before deployment. [OCI Cache Client Best Practices](https://docs.oracle.com/en-us/iaas/Content/ocicache/ocicachebestpractices.htm).

Reuse clients or connections per library guidance, bounding pool size, command timeouts, and queue waits. Never create a new client per HTTP request.

Retries must stay within the total deadline and match command semantics. Repeating `SET` can alter expiration times; retrying increment/decrement commands has different semantics than retrying `GET`. Never assume all Redis commands are equally safe to retry.

Failover can drop active connections; “managed failover” does not mean every in-flight app request finishes uninterrupted.

## 10. Memory, Eviction, and Data Partitioning

### 10.1. Size for Working Set Rather Than Entire Database

Initial estimate:

~~~text
Cache memory to consider ≈
    active keys × (key + payload size)
  + metadata and data structures
  + buffers, connections, and overhead
  + headroom for spikes and operations
~~~

One million ~1 KiB payloads already consume nearly 1 GiB of value data before adding keys and overhead. Compressed source data or JSON size on disk does not equal Redis memory consumption.

Measure using representative data: size distributions, field counts, lifetimes, and access frequencies. Avoid oversized values that saturate bandwidth and tie up single commands.

### 10.2. Distinguishing Expiration from Eviction

- **Expiration:** key exceeds its TTL.
- **Eviction:** key is removed to satisfy memory policy limits.
- **Invalidation:** app actively removes outdated data.

Redis offers policy families such as LRU, LFU, volatile-only TTL policies, and `noeviction`. With `noeviction`, commands needing more memory can be rejected when full. [Redis Key Eviction](https://redis.io/docs/latest/reference/eviction/).

OCI Cache only allows tuning the subset of configurations supported by the service. Do not take `CONFIG SET` guides from self-managed Redis and assume they apply identically to OCI Cache. [Supported Configurations for OCI Cache](https://docs.oracle.com/en-us/iaas/Content/ocicache/supported-configurations.htm).

Separate evictable cache workloads from data with different lifecycles such as sessions or critical coordination state when needed. Both using Redis does not mean they belong under the same memory policy and failure domain.

### 10.3. Replicas Do Not Multiply Unique Data Capacity

A three-node non-sharded cluster replicating the same dataset cannot hold three times a single node's working set.

Sharding partitions data across shards. However, adding shards does not split a single hot key or fix skewed access patterns. Multi-key commands and scripts must also satisfy cluster-mode slot rules.

When using hash tags to co-locate related keys in the same slot, scope tags to an entity or small group. Using one global hash tag for an entire application can force all data onto a single shard.

## 11. IAM, Authentication, and Protecting Cached Data

### 11.1. Separating Management Permissions from Data Access

| Layer | What Must Be Protected |
| --- | --- |
| **OCI IAM resource management** | Who can create, modify, resize, or delete clusters |
| **Network** | Which workloads can reach the private endpoint |
| **Cache auth and permissions** | Which identities can run data commands |
| **Application** | Which tenants, objects, and fields callers may view |
| **Secrets and logs** | Who can view tokens, connection info, and logged data |

An IAM policy allowing cluster creation does not grant permission to read all Redis data. A successful TLS handshake likewise does not replace authentication or business authorization checks.

OCI Cache supports cache users and short-lived token IAM authentication depending on configuration. If using IAM auth, clients must integrate proper token issuance and refresh workflows. [OCI Cache Users](https://docs.oracle.com/en-us/iaas/Content/ocicache/cache-users.htm), [IAM Authentication for OCI Cache](https://docs.oracle.com/en-us/iaas/Content/ocicache/iam-authentication.htm).

### 11.2. Restricting Network Paths and Commands

- Allow connections only from required app sources via NSGs or security lists.
- Enable TLS certificate validation and use the exact hostname.
- Never place endpoints or credentials in public URLs, logs, or repositories.
- Restrict bulk-delete and config-change commands as supported by the service.
- Grant only needed read/write commands; do not assume apps need every admin command.

If an L1 in-process cache exists, manage L1 invalidation and TTL separately. Deleting a key in Redis does not clear copies held inside app instances.

Cached data, backups, and operational logs remain within data governance scope. Key TTLs do not automatically expire all copies or logs simultaneously.

## 12. Monitoring Offloading Efficiency and Resilience

OCI Cache emits metrics under the **oci_redis** namespace. Metrics are primarily per-node, so inspect the right resources and topology. [OCI Cache Metrics](https://docs.oracle.com/en-us/iaas/Content/ocicache/metrics.htm).

| Key Service Metric | Question It Helps Answer |
| --- | --- |
| **KeyspaceHits / KeyspaceMisses** | Key lookups succeeding vs. missing |
| **UsedMemory / MemoryUtilization** | Is memory approaching capacity limits? |
| **EvictedKeys / ExpiredKeys** | Are keys removed for memory pressure or TTL expiry? |
| **ConnectedClients** | Are client connections growing abnormally? |
| **CPUUtilization** | Are nodes under heavy processing load? |
| **NetworkBytesIn / NetworkBytesOut** | Is there data transfer pressure? |
| **ReplicationLag** | Are replicas falling behind the primary? |

Do not average per-node hit ratios and treat the result as the system-wide ratio if traffic differs across nodes. Aggregate hit/miss counts over the same window matching how metrics are emitted. When using cumulative counters from external tools, handle deltas and counter resets properly.

Application metrics to add:

- Valid lookups, hits, misses, cache errors, and intentional bypasses.
- Cache latency and end-to-end p95/p99 latency.
- Database reads broken down by cause: miss, refresh, fallback.
- Requests coalesced by single-flight, queued, or rejected.
- Cache write errors and invalidation processing lag.
- Stale serves and data age relative to contract.
- Database load, query duration, and connection pool utilization.

Cache timeouts must be tracked separately from cache misses. During a timeout, the application does not know whether the key exists.

A useful dashboard places hit ratio, cache errors, DB QPS, DB latency, and application latency on the same timeline. When evictions spike followed by misses and DB latency rising together, you have clear evidence to investigate working set sizing or memory policy.

Alerts should drive concrete actions: throttle warm-up, inspect hot nodes/shards, verify client reconnection, or shed fallback load. Never alert only on cache memory while ignoring a database nearing connection exhaustion.

## 13. Recovery, Warm-Up, and Cost

### 13.1. Warm-Up Must Not Cause Overload

After a new namespace rollout, cache outage, or regional switch, the cache may be cold. Warm-up should:

1. Prioritize a high-value subset of hot keys.
2. Bound concurrency and database read rates.
3. Back off or halt when database protection thresholds are crossed.
4. Avoid having every app instance load the entire dataset concurrently.
5. Measure how long hit ratio and latency take to return to target.

Do not load the entire database into Redis just because the cache is empty. Rarely accessed entries can evict hot keys and raise costs without meaningfully reducing load.

### 13.2. Cache Backups Do Not Replace Database Backups

OCI Cache provides backup/restore capabilities per supported configuration. For reconstructible caches, backups can speed up recovery, yet they never replace Oracle Database durability and recovery plans. [OCI Cache Backup and Restore](https://docs.oracle.com/en-us/iaas/Content/ocicache/backup-restore.htm).

When restoring an older cache snapshot, account for updates and invalidations that occurred after the backup timestamp. You may need to switch namespaces, reconcile versions, or rebuild entries before serving.

If using cross-region cache replication, you still need plans to fail over the app, data source, permissions, and network routing. A replicated cache alone does not complete full-system disaster recovery.

### 13.3. Comparing Total Solution Cost

Costs to account for include node memory/capacity, replicas, shards, networking, monitoring, backup storage, and operational procedures. Check current SKUs and billing units in the [Oracle Cloud Price List](https://www.oracle.com/cloud/price-list/).

Evaluate:

~~~text
Offloading value =
    saved database resources or latency
  - cache cost and added operational overhead
~~~

This is an evaluation framework, not a billing settlement formula. The database may still need standby capacity to survive cache degradation, so lowering DB QPS does not automatically translate into proportional dollar savings.

Measure cost per target-compliant served request and evaluate recovery periods as well. Never drop replicas just to cut costs while ignoring stated high-availability goals.

## 14. Hands-On: Designing and Verifying the Cache Flow

The steps below are for learners in an isolated test environment using synthetic or authorized data. You do not need to alter business database schemas to start this exercise.

### 14.1. Defining the Contract

Pick a product-description read API and document:

- Source data and tenant scope.
- Acceptable staleness window.
- Conditions requiring a direct database read.
- Keys affected by updates.
- Permitted database load when cache is cold or degraded.
- Target latency, success rate, and recovery time.

### 14.2. Preparing Resources and Connectivity

1. Choose compartment, region, and cluster configuration matching targets.
2. For non-sharded HA, evaluate the primary-plus-two-replicas recommendation.
3. Configure private connectivity, NSGs/security lists, TLS, and authentication.
4. Retrieve endpoints from cluster details rather than guessing hostnames.
5. Pick a compatible client; verify connection reuse and timeouts.
6. Confirm both cache metrics and database metrics are observable.

### 14.3. Implementing Bounded Cache-Aside

1. Use a dedicated prefix for the lab.
2. Build keys containing tenant, schema version, and result-affecting parameters.
3. Read cache, handling misses through a bounded loader.
4. Write value and TTL in one atomic operation.
5. Deduplicate concurrent loads per key.
6. Update database, then invalidate after commit.
7. Record cache hits, misses, errors, and bypasses separately.

### 14.4. Comparing Test Scenarios

| Test Scenario | Evidence to Collect |
| --- | --- |
| Without cache | DB QPS, query duration, app p95/p99 |
| Cold cache | Load rate, database load, throttled requests |
| Warm cache | Hit ratio, DB read reduction, latency |
| Burst of requests on expired hot key | Actual concurrent loaders run and DB load |
| Many keys expiring close together | Effectiveness of jitter and refresh bounds |
| Concurrent reads and writes | Data versions and observed stale window |
| Cache unreachable in test env | Circuit breaker, fallback budget, load shedding |
| Supported failover or topology change | Reconnects, transient errors, and recovery duration |
| Data exceeding projected working set | Evictions, cache write errors, and DB impact |

Do not use hit ratio alone as the pass criterion. What matters is that the database does not collapse when the cache fails and the app does not serve out-of-contract data.

### 14.5. Design Completion Checklist

| Question | Expected Evidence |
| --- | --- |
| Does losing cache lose business transactions? | Authoritative data remains in the database |
| Is it clear when stale data is acceptable? | TTL, stale, and bypass contract |
| Does invalidation handle post-commit errors? | Outbox, CDC, or controlled retry mechanism |
| Are stale-reload races addressed? | Timeline analysis and accepted consistency level |
| Can a cold cache overload the database? | Loader limits, fallback caps, and warm-up bounds |
| Do clients follow failovers? | Endpoints, reconnects, and topology configuration |
| Are memory and cost aligned? | Measured working set, overhead, and replica/shard sizing |
| Can incidents be investigated? | Cache, application, database metrics, and runbooks |

A well-designed Redis layer offloads repetitive work from Oracle Database while preserving a controlled serving path when the cache is empty, stale, or temporarily unavailable. That is the role of caching in high-availability architecture on OCI.
