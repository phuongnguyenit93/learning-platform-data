# Cache-Aside, Read-Through, Write-Through, and Write-Behind

A cache helps applications read data faster by keeping a copy close to where it is used. In cloud architectures, caching can reduce database queries, lower latency, and absorb bursts of traffic. However, a cache also introduces a second copy of the data, with its own lifecycle and update rules. Without clearly defining who populates the data, who writes the authoritative data, and when the cache is refreshed, the system can return stale data, lose updates, or overload the database when the cache fails.

Four common patterns for coordinating a cache with a data store are **cache-aside**, **read-through**, **write-through**, and **write-behind** (also called write-back). They differ in whether the application or the cache is responsible for loading data on reads, and when data is written to the primary store. No single pattern is always best: the choice depends on read/write frequency, consistency requirements, tolerance for data loss, latency, and operational practices.

This lesson belongs to the **Caching** section of the cloud architecture module. Its goal is to explain how to design caching as a component in the data path, understand trade-offs between performance and correctness, and make verifiable decisions aligned with reliability, security, scalability, cost, and operational goals.

After this lesson, you will be able to:

- Explain cache-aside, read-through, write-through, and write-behind through read/write flows.
- Select a pattern suited to the workload and consistency requirements.
- Design TTLs, invalidation, cache keys, negative caching, and stale data handling.
- Control cache stampedes, thundering herds, hot keys, and concurrent update contention.
- Build fallbacks when the cache fails, times out, or loses connectivity.
- Protect cached data, observe hits/misses/latency, and control costs.
- Test cache behavior under high load, failures, and concurrent updates.

## 1. Where Does the Cache Sit in the Data Path?

Applications typically use a database or source service as the store for authoritative data. A cache holds a regenerable copy of a subset of that data to serve frequent accesses faster.

~~~mermaid
flowchart LR
    CLIENT["Client"] --> APP["Application service"]
    APP --> CACHE[("Cache")]
    CACHE -->|Miss| DB[("Primary database")]
    DB -->|Load data| CACHE
    CACHE -->|Hit / loaded value| APP
    APP --> CLIENT
~~~

The diagram outlines a read path. The write path must be designed separately: writing to the cache first, writing to the database first, or writing to the database asynchronously after updating the cache creates major differences in durability and consistency.

### Why cache?

- **Lower latency:** reading from memory or a network store close to the application is usually faster than querying a remote data source.
- **Reduced database load:** repeated reads of the same data do not need to re-execute expensive queries.
- **Burst absorption:** a cache can serve heavy read traffic when the underlying data does not change frequently.
- **Higher availability during certain failures:** cached data can help serve traffic temporarily if the application is designed for stale reads.
- **Lower source cost:** fewer queries, I/O operations, or compute cycles when the hit ratio is high enough.

Caching also carries costs: infrastructure, network hops, serialization, invalidation, memory fragmentation, eviction, and operations. A distributed cache is not automatically faster than a well-indexed database query, especially when data is rarely re-read or the cache is far from the application.

### The cache is not the authoritative data source

Typically, the database or domain service that owns the data is the **source of truth**. The cache is a copy for performance optimization. When the cache is cleared or a node is lost, the application must have a way to reconstruct the data.

There are exceptions such as write-behind, where the cache or a temporary write queue participates in the write path. In that case, the system must treat the cache/buffer store as a component with its own durability responsibilities, equipped with replication, persistence, replay, and recovery procedures. You cannot treat it as a disposable cache without clarifying the risk of data loss.

## 2. How Do the Four Patterns Differ?

| Pattern | On read cache miss | On write | Primary coordinator |
| --- | --- | --- | --- |
| **Cache-aside** | Application reads the source, then loads the result into the cache | Application writes to the source, then deletes/updates the cache per policy | Application |
| **Read-through** | Cache invokes the configured loader/data source and stores the result before returning | Does not prescribe write behavior; often paired with write-through or invalidation | Cache layer/provider |
| **Write-through** | Usually reads from cache; misses are loaded via cache-aside or read-through | Writes to cache and source synchronously under one contract | Cache layer or adapter |
| **Write-behind** | Reads from cache or appropriate read layer | Writes to cache first, queues source writes asynchronously | Cache/write buffer and worker |

Key point: **read-through describes the read path; write-through and write-behind describe the write path**. Cache-aside typically leaves the application in charge of both loading on misses and invalidating on writes. Real-world architectures can combine patterns—for example, cache-aside for reads and write-through or cache invalidation for writes.

~~~mermaid
flowchart TD
    A["Choose caching strategy"] --> R{"Read"}
    R --> CA["Cache-aside<br/>Application load on miss"]
    R --> RT["Read-through<br/>Cache invokes loader"]
    A --> W{"Write"}
    W --> WT["Write-through<br/>Cache + source synchronously"]
    W --> WB["Write-behind<br/>Cache first, source later"]
~~~

## 3. Cache-Aside: Application Proactively Loads and Invalidates the Cache

Cache-aside is also known as lazy loading. The application checks the cache first. If the data is present, it returns immediately. On a miss, the application reads from the source of truth, writes the result into the cache, and returns it to the caller.

### 3.1. Read flow

~~~mermaid
sequenceDiagram
    participant A as Application
    participant C as Cache
    participant D as Database
    A->>C: GET key
    alt Cache hit
        C-->>A: Cached value
    else Cache miss
        C-->>A: Miss
        A->>D: SELECT data
        D-->>A: Current data
        A->>C: SET key with TTL
        C-->>A: Stored
    end
    A-->>A: Return result
~~~

For example, a booking application reads a doctor's profile by doctor ID. When the cache does not have it, the service fetches the profile from the database, serializes it, and stores it in the cache with a 5-minute TTL. Subsequent requests can return the data from the cache.

### 3.2. Write flow: update source then invalidate

A common choice is to write to the database successfully and then delete the cache entry:

~~~mermaid
sequenceDiagram
    participant A as Application
    participant D as Database
    participant C as Cache
    A->>D: UPDATE profile
    D-->>A: Commit success
    A->>C: DEL profile key
    C-->>A: Deleted
    A-->>A: Return success
~~~

The next read request will miss and load the new version from the database. This approach reduces the risk of caching a value that was never committed by the database.

However, between the database commit and the cache delete command, a reader might read the old copy. If the application crashes after committing but before invalidation, the stale cache entry can persist until the TTL expires. Therefore:

- TTL serves as a final safety net so stale entries eventually expire.
- Invalidation events can be published via an outbox to improve reliability.
- If read-after-write requirements are strict, return the newly committed data from the writer or use versioning/fencing rather than relying solely on the cache.
- Invalidation handlers must be idempotent and support retries.

### 3.3. Pros and trade-offs

**Pros**

- Easy to implement and control within the application.
- Only caches data that is actually read.
- Cache failures can fall back to the data source if the database still has capacity to serve traffic.
- Does not force every write path to go through the cache.

**Trade-offs**

- The application must manage cache miss logic, TTLs, keys, and invalidation.
- Cache misses generate extra queries, potentially causing spikes when keys expire simultaneously.
- Post-commit invalidation has a failure window.
- Multiple services reading the same data must agree on key formats and policies.

Cache-aside is generally suited for read-heavy data that tolerates short staleness and has a reliable authoritative data source.

## 4. Read-Through: Cache Layer Loads Data Automatically

With read-through, the application sends read requests to a cache abstraction. If the key does not exist, the cache layer invokes a configured loader or data source, retrieves the data, stores it in the cache, and returns it to the application.

~~~mermaid
sequenceDiagram
    participant A as Application
    participant C as Read-through cache
    participant D as Data source
    A->>C: GET key
    alt Hit
        C-->>A: Cached value
    else Miss
        C->>D: Load(key)
        D-->>C: Value
        C->>C: Store with TTL
        C-->>A: Value
    end
~~~

### Cache loader and abstraction

The loader is the component that knows how to fetch a value on a cache miss. It can query a database, call an internal service, or assemble data from appropriate sources. The application only uses the read interface; loading details are encapsulated in the cache provider or adapter.

Pseudocode example:

~~~java
Profile profile = profileCache.get(
    doctorId,
    id -> profileRepository.findById(id)
);
~~~

This snippet illustrates the loader concept; actual APIs depend on the cache library. You must define behavior when the loader returns null, throws an exception, times out, or when multiple requests miss simultaneously.

### Pros

- Centralizes data-loading logic, reducing boilerplate across multiple callers.
- Can standardize serialization, TTLs, and error handling.
- Multiple applications share a single cache abstraction.

### Trade-offs

- The cache layer becomes a critical dependency and can hide the cost of the loader.
- Debugging misses and source queries can be harder if observability is poor.
- The loader must manage concurrency, timeouts, retries, and source errors.
- Not every cache server or managed cache includes a built-in read-through loader; some require an in-app library, sidecar, or gateway.

Read-through fits well when an organization wants to standardize data loading or has a cache provider layer with clear loader support. It does not automatically solve invalidation when data is modified by another system.

## 5. Write-Through: Synchronous Cache and Source Writes

Write-through requires write operations to pass through the cache layer. The cache writes the new value to the data store first or according to a defined synchronous mechanism, then updates the cache and returns success.

~~~mermaid
sequenceDiagram
    participant A as Application
    participant C as Write-through cache
    participant D as Database
    A->>C: PUT key, new value
    C->>D: Persist value
    D-->>C: Commit success
    C->>C: Update cache entry
    C-->>A: Success
~~~

The advantage of write-through is that once the operation succeeds under the contract, the cache typically holds the newly written value. Readers do not have to wait for a cache miss to see the updated value.

### Questions that must be defined

- Does the source commit before the cache update, or vice versa?
- If the source commits successfully but the cache update fails, what is the response?
- If the cache updates successfully but the source fails, can the cache be rolled back?
- Is write ordering protected when two writers update the same key?
- Is there an atomic transaction between the cache and database, or simply two sequential operations?

Typically, there is no shared ACID transaction between an independent cache and database. Therefore, write-through must still define partial failure states. A safer option is **commit to the source first, then update the cache; if the cache update fails, invalidate the cache and let the next read reload it**. The response contract must clearly reflect whether the source has committed.

### Pros and trade-offs

**Pros**

- Cached data is refreshed immediately after a successful write along the standard flow.
- Reduces the staleness window compared to waiting for TTL expiration alone.
- Can simplify the read path.

**Trade-offs**

- Write latency increases because writes must touch both the cache and the source.
- All writers must follow the same policy; writing directly to the database breaks the assumption.
- Partial failures can still occur between the two systems.
- Rarely read data still consumes cache memory.

Write-through is suitable when many reads need to see new values promptly and write traffic is not overly sensitive to synchronous overhead. Evaluate carefully if the database has multiple independent writers or the cache is shared across multiple applications.

## 6. Write-Behind: Cache Accepts Writes First, Source Updates Later

Write-behind (write-back) responds to the caller as soon as changes are written to the cache or a write buffer, while writing to the database happens asynchronously. The system can coalesce multiple changes, batch writes, or reduce source access frequency.

~~~mermaid
sequenceDiagram
    participant A as Application
    participant C as Cache / write buffer
    participant Q as Durable queue or log
    participant W as Writer worker
    participant D as Database
    A->>C: Write value
    C->>Q: Persist pending write
    Q-->>C: Durable acknowledgement
    C-->>A: Accepted
    Q->>W: Deliver pending write
    W->>D: Apply write
    D-->>W: Commit
    W->>Q: Mark processed
~~~

A critical point in the diagram is the need for a **durable queue/log or equivalent persistence mechanism** if the system wants to claim a write is safely accepted before the database commits. If data is only placed in a cache node's RAM before returning success, a node power loss can lose unflushed writes.

### When is write-behind useful?

- Very high write load where multiple updates can be batched.
- Delay before data appears in the primary store is acceptable.
- Writing to the cache/buffer is faster than synchronous database writes.
- Eventual consistency can be handled and replay/reconciliation processes exist.

For example, view counters can be incremented in a buffer and aggregated in batches by a worker. Conversely, money transfers or booking slot reservations should not arbitrarily use write-behind if callers need confirmation that the authoritative store has committed.

### Key risks

- **Data loss:** non-durable buffers or unreplicated queues.
- **Backlog:** writers cannot keep up with write velocity, increasing sync lag.
- **Out-of-order updates:** multiple workers processing updates for the same key out of sequence.
- **Duplicate writes:** a worker commits to the database and crashes before acknowledging, leading to redelivery.
- **Desynchronization:** the cache reflects the new value while the database remains stale or fails to write.
- **Conflicts:** another writer updates the database directly while a write-behind update is still pending.

### Prerequisites before production

- Write buffers are persisted durably with appropriate replication.
- Each mutation has an operation/event ID and is processed idempotently.
- Per-key/aggregate ordering is enforced if required by business logic.
- Backlog limits, oldest-age alerts, and backpressure are in place.
- Dead-letter/quarantine handling and controlled replay capabilities exist.
- Reconciliation compares the cache/buffer against the database.
- Policies exist for when writers fail to recover within the allowed time window.

## 7. Comparison by Read and Write Scenarios

| Criterion | Cache-aside | Read-through | Write-through | Write-behind |
| --- | --- | --- | --- | --- |
| Cache miss | Application loads | Cache layer invokes loader | Must pair with a read pattern | Typically reads from cache/buffer or source |
| Authoritative write target | Usually source first | Does not dictate write path | Source updated synchronously via cache layer | Source updated asynchronously |
| Write latency | Usually lower since app writes source then invalidates; adds invalidation overhead | Depends on paired write pattern | Higher due to synchronous source write | Low on front path if buffer acks quickly |
| Staleness lag | Possible until invalidation/TTL | Depends on refresh/invalidation | Usually low after successful contracted write | Intentional until flushed |
| Complexity | Moderate, in application | Loader/provider | Coordinating partial failure across two stores | High: queues, replay, ordering, recovery |
| Prominent risks | Stale cache, stampede | Loader bottleneck | Partial write failure | Data loss/backlog/duplicates |
| Typical use cases | Profiles, catalogs, rarely changing config | Shared cache abstraction | Data re-read immediately after write | Counters, telemetry, or batchable eventual updates |

Do not treat the four patterns as four separate caching technologies. They are **patterns for coordinating read and write paths**. A single system may use cache-aside for profiles, read-through for catalogs, write-through for configuration, and write-behind for non-critical counters.

## 8. TTL, Invalidation, and Stale Data

A cache needs lifecycle policies. **TTL (time to live)** determines how long an entry can remain before expiring. Long TTLs increase hit ratios but heighten staleness risk; short TTLs lower theoretical maximum staleness but increase misses and source load.

### Choosing TTL by data semantics

| Data | Suggested starting TTL for testing | Considerations |
| --- | --- | --- |
| Rarely changing public catalogs | A few minutes to hours | Can invalidate on publish |
| User profiles | Tens of seconds to a few minutes | Permission/info updates require strict policies |
| Features/configs | Per release lifecycle or a few minutes | Needs versioning and refresh capability |
| Expensive query results | Depends on access pattern and freshness sensitivity | Keys must include all relevant filters |
| Inventory/slot data | Short TTL or do not cache final decisions | Revalidate on source during actual booking |
| Negative cache (not found) | Very short | The resource may have just been created |

These intervals are starting points for benchmarking, not universal standards. TTLs should derive from business freshness requirements.

### Event-driven invalidation

When data changes, the owning service can emit an event to delete or update the cache. Use a transactional outbox when you need to guarantee events are not lost between database commits and publishing.

For example, a ProfileUpdated event contains a profile ID and version. Cache consumers only update or invalidate if the version is newer than the current one; delayed old events must not overwrite newer data.

### Versioned keys

One way to reduce race conditions is to embed the version in the cache key:

~~~text
profile:{profileId}:v{version}
~~~

The application looks up the current version from a reliable coordinator or appropriate metadata, then reads the corresponding key. This reduces overwrites on old keys, though it still requires a mechanism to determine the current version and clean up old keys.

### Intentional stale caching

Some use cases accept **stale-while-revalidate**: returning usable stale data while fetching a fresh copy in the background. This can improve latency and availability, provided you:

- Define the maximum acceptable data age.
- Do not apply it to state that must be checked immediately before side effects.
- Indicate data timestamp/version to clients if needed.
- Limit concurrent background refreshes.
- Have a fallback if refresh fails and stale data exceeds its age limit.

## 9. Cache Keys, Serialization, and Data Scope

A cache key is the logical address of an entry. Poor key design can return data belonging to the wrong tenant or the wrong query variant.

A cache key must include every factor that changes the output:

- Resource identifier.
- Tenant/organization if data is tenant-isolated.
- Locale, currency, or role/permission scope when it affects the result.
- Query filters, sort order, page/cursor when caching list responses.
- Schema/data version when formats change.
- Feature flags or required business parameters.

Examples:

~~~text
booking:tenant-21:doctor-42:date-2026-11-18
catalog:tenant-21:locale-vi-VN:category-8:page-1
profile:user-991:v17
~~~

Do not put raw access tokens, emails, or unnecessary personal data into keys. Keys should have length limits, naming conventions, and namespaces to prevent collisions.

### Serialization

Caches typically store bytes or strings, so the application must choose a serialization format. JSON is easy to debug and compatible, though it carries overhead; binary formats can be smaller and faster, but require schema/version management. Cache entries should include:

- Schema version.
- Data version or updated timestamp if needed.
- Appropriate TTL.
- Controlled payload size.
- Rules for handling unparseable payloads.

When deploying a new version incompatible with old formats, use a namespace/versioned key strategy or controlled invalidation. Never let serialization failures cause every request to continuously hit the source and trigger a stampede.

## 10. Cache Stampede, Thundering Herd, and Hot Keys

When a popular key expires, many requests can miss simultaneously and query the database at once. This is a **cache stampede** or thundering herd. An extremely popular key can also become a hot key, saturating a single shard or node.

### Mitigations

1. **Request coalescing/single-flight:** only one request loads the key while other requests wait for the result.
2. **TTL jitter:** add random variance to TTLs so multiple entries do not expire at the exact same moment.
3. **Refresh ahead:** refresh entries before they expire according to policy.
4. **Stale-while-revalidate:** serve the old copy within allowed limits while refreshing.
5. **Negative caching:** cache not-found results briefly to prevent repeated queries.
6. **Rate limiting/load shedding:** cap load sent to the source when the cache loses effectiveness.
7. **Sharding/replication:** distribute hot key load if architecture and semantics allow.

### Single-flight example on one instance

A service can maintain a future/promise per key currently being loaded. Requests within the same process await the shared future. However, local coalescing only works within one instance; multiple instances can still miss simultaneously. If cluster-wide coordination is needed, use a distributed mechanism with timeouts and safe fencing, or accept a bounded number of parallel loaders.

Do not use a distributed lock without a lease/fencing token and assume absolute safety. A lock expiring while an old loader is still running can let two loaders write concurrently. Version checks or compare-and-set prevent stale data from overwriting newer data.

### Cache hit ratio is not the sole goal

A high hit ratio that serves stale data can break business logic. A low hit ratio may be acceptable if source queries are cheap and latency meets targets. Track these together:

- Hits/misses by key class or endpoint.
- Loader calls and database load.
- p50/p95/p99 latency for hits and misses.
- Stale age and invalidation lag.
- Evictions, memory pressure, hot keys, and payload sizes.

## 11. Concurrency and Competing Updates

Two writers can update the same key nearly simultaneously. Without versioning or ordering, an older writer arriving later can overwrite a newer value.

Example:

1. Request A reads version 10.
2. Request B reads version 10.
3. B updates the source to version 12 and updates the cache.
4. A finishes slowly, writing version 11 to the cache.

The cache reverts to stale data even though the source is at version 12. Apply one of these approaches:

- Compare-and-set: only write to the cache if the version is newer than the current cached version.
- Optimistic concurrency: update the source conditionally on the version matching what was read.
- Versioned invalidation and discarding late-arriving events.
- Serialize updates per aggregate/key if strict ordering is required.
- Read the version from the source of truth when processing critical operations.

Because the cache is a copy, do not use cache locks to replace business transactions or constraints in the database. For example, reserving a booking slot must be protected by a database transaction/unique constraint, not merely a cache lock.

## 12. Failure Modes and Fallbacks

A cache can time out, lose nodes, fail over, run out of memory, evict entries, suffer network partitions, or return undeserializable data. Applications must define whether the cache is a hard dependency or an optional optimization.

### When the cache is unavailable

With cache-aside, the application can fall back to the database. However, if every request falls back simultaneously, the database can become overloaded. Fallbacks require:

- Short timeouts and circuit breakers.
- Concurrency limits toward the database.
- Rate limiting or load shedding as the database approaches saturation.
- Bulkheads so cache failures do not exhaust the entire thread pool.
- Bounded retries to avoid retry storms.
- Alerts for cache unavailability and database saturation.

If the cache serves as a durable write buffer in write-behind, do not bypass the cache on failure. Halt or buffer in another durable system, and return error or accepted statuses matching how safely the data was persisted.

### Cache failover

A managed cache service may provide replication and failover, yet clients can still experience connection resets, DNS changes, or data loss depending on configuration. Check:

- Replication mode and potential loss of recent writes.
- Client reconnection and backoff behavior.
- Read endpoints after failover.
- Eviction and persistence behavior.
- Impact on hit ratios while the entire cache warms up again.

### Cache poisoning and invalid data

If an attacker can write arbitrary cache keys or contents, malicious data can be served to many users. Authorize write paths, validate payloads, namespace by tenant, verify serialization, and never trust raw user input directly as a cache key.

## 13. Security and Privacy

A cache typically holds copies of application data; therefore, security requirements are no lower than the data source just because the data is temporary.

- Use private networking and firewalls/security groups to restrict clients.
- Enable TLS in transit if required by the service and environment.
- Use appropriate authentication/ACLs/identities; never expose cache endpoints publicly.
- Isolate namespaces and permissions by service/tenant.
- Encrypt data at rest if supported by the platform and required by the data.
- Do not cache tokens, secrets, or sensitive data without a clear need.
- For personal data, enforce TTL, deletion, and invalidation policies upon user deletion requests.
- Avoid logging cache values or sensitive keys; mask details in traces.
- Control snapshot/export access and console permissions.

### Authorization before or after the cache?

If caching a user-filtered response, the key must accurately reflect permissions/tenant, or data must be re-authorized on every request. Never share a cache key for responses containing personal data if another caller could receive that result.

A safe approach is caching properly scoped domain data at the service tier and enforcing authorization on each request. Never treat hard-to-guess keys as an authorization control.

## 14. Observability, Operations, and Cost

A cache needs dedicated dashboards and alerts, with metrics tied to user experience and the underlying data source.

| Metric | Question it answers |
| --- | --- |
| Hit/miss ratio | Is the cache serving most of the expected access patterns? |
| Hit/miss latency | Does the cache actually reduce latency compared to the loader? |
| Evictions/expired entries | Is memory insufficient or are TTLs too short? |
| Memory used/fragmentation | Is there a risk of OOM or growing payload sizes? |
| Connections/commands per second | Are clients creating excessive connections or commands? |
| Hot keys / top key cardinality | Is load skewed toward a single key or shard? |
| Loader/database QPS | Are cache misses overloading the data source? |
| Invalidation lag | How long does it take for new data to appear in the cache? |
| Stale age | How old can data served to callers be? |
| Write-behind backlog/oldest age | How far is the source falling behind the write intake rate? |
| DLQ/retry count | Are there mutations/events that cannot be applied? |
| Cache spend / cost per request | Do cache savings outweigh cache costs? |

### Estimating cost-effectiveness

Suppose an endpoint receives 1,000 requests/second with a 90% hit ratio, where each database query costs one unit of resources. With the cache active, theoretical source queries drop to around 100/second, excluding refreshes, invalidations, retries, and other queries.

This is a simple baseline calculation. Total Cost of Ownership (TCO) must add cache nodes, replication, networking, serialization CPU, observability, and operations. If a cache adds latency while achieving only a low hit ratio, the solution may not be worthwhile.

### Capacity planning

Estimate memory based on active entry count, actual payload sizes, metadata, keys, engine overhead, replication, and headroom. Do not sum raw JSON sizes and treat that as provisioned capacity. Measure on the target engine/instance type under representative load.

## 15. Choosing a Pattern by Requirements

A sound decision starts with the question: **if the cache is stale, lost, or slow, what happens to the business?**

| Question | Potentially suitable choice |
| --- | --- |
| Read-heavy, write-light data tolerating brief staleness? | Cache-aside or read-through |
| Want to centralize data-loading logic in a cache abstraction? | Read-through |
| After writes, most callers need immediate reads and higher write latency is acceptable? | Write-through |
| Can tolerate delayed source updates and need to batch massive write volumes? | Write-behind, only with a durable buffer and recovery |
| Data governs immediate transactional decisions, such as slots or balances? | Source of truth/transaction; cache assists reads only, never final decisions |
| Multiple independent writers? | Prefer invalidation/versioning strategies and source transactions; use caution with write-through |
| Must the system still write durably if the cache is unavailable? | Do not rely on the cache as the sole buffer unless durability is proven |

### Reference decision tree

~~~mermaid
flowchart TD
    A["Identify access pattern"] --> B{"Primarily optimize reads?"}
    B -- "Yes" --> C{"Can application manage the loader?"}
    C -- "Yes" --> D["Cache-aside"]
    C -- "Want centralized loader" --> E["Read-through"]
    B -- "Need to choose write strategy" --> F{"Must source commit before response?"}
    F -- "Yes" --> G["Write-through or source write + invalidate"]
    F -- "No, accept eventual" --> H{"Durable buffer, replay, and idempotency?"}
    H -- "Yes" --> I["Evaluate write-behind"]
    H -- "No" --> J["Do not ack before data is durable"]
~~~

The tree is only a starting guide. An architecture may need to combine multiple patterns across different data types.

## 16. Cache Design Example for a Booking Application

**Assumed context:** An application has three types of data:

- Doctor profiles and service descriptions: read-heavy, updated infrequently.
- Bookable slot lists: read-heavy, changing continuously as users book or cancel.
- Doctor page view counts: updated continuously, tolerating aggregation delayed by a few seconds.

### Doctor profiles

Use cache-aside or read-through with a TTL of a few minutes. When an admin updates a profile, the database commits and emits an invalidation event. If the event is delayed, the TTL bounds staleness. Include tenant/locale in the cache key if content varies.

### Bookable slots

The cache can serve slot lists for fast display, but **does not decide booking success**. When a customer selects a slot, the Booking Service revalidates and writes through a database transaction/constraint or a booking store with appropriate consistency. After committing, invalidate or version the slot cache. Display a data timestamp so customers know when the list was last refreshed.

### View counts

Use write-behind or counter aggregation if delayed counts are acceptable and a durable event buffer exists. Each event needs an ID for idempotent consumption; workers batch-update the source. Maintain dashboards for backlog, oldest event age, and reconciliation.

### Overall architecture diagram

~~~mermaid
flowchart TD
    USER["Browser / Mobile"] --> API["Application API"]
    API --> PROFILE["Profile cache-aside<br/>TTL + invalidation"]
    PROFILE --> PDB[("Profile database")]
    API --> SLOT["Slot cache<br/>Read optimization only"]
    SLOT --> SDB[("Booking database<br/>Source of truth")]
    API --> BOOK["Reserve/confirm transaction"]
    BOOK --> SDB
    BOOK --> INV["Invalidate slot cache"]
    API --> COUNTER["View counter buffer"]
    COUNTER --> Q[("Durable event log / queue")]
    Q --> WORKER["Batch consumer"]
    WORKER --> ANALYTICS[("Analytics store")]
~~~

### Verification checklist

- Profile update commits but the invalidation event is lost: do TTL/replay recover it?
- Two users simultaneously book a slot cached as available: does the database constraint prevent double booking?
- All cache nodes are lost: can the database withstand cold-cache load?
- View counter events are delivered twice: are counts incremented twice?
- Tenant A never receives Tenant B's cache entry: are keys and authorization correct?

## 17. Hands-On Exercise: Designing and Testing the Four Cache Patterns

**Scenario:** An e-commerce platform has catalogs, inventory, customer profiles, and product views. The catalog is read-heavy and updated in batches; inventory changes continuously; profiles contain tenant-scoped data; view counts can be aggregated with delay. At peak load, the catalog receives 5,000 read requests/second; the database must not exceed 1,000 queries/second. These figures are hypothetical for this exercise.

### Task 1 — Choose patterns per data type

Propose cache-aside/read-through for catalog and profiles, a strategy for inventory, and write-behind for view counters if appropriate. Explain which data can be stale, for how long at most, and which operations must go through the source of truth.

### Task 2 — Design keys and TTLs

Write cache keys for the catalog by locale/category/page, profiles by tenant/user, inventory by SKU/warehouse, and counters by product ID. Choose initial TTLs and invalidation/versioning mechanisms.

### Task 3 — Handle concurrency

Simulate many concurrent requests missing the same catalog key. Design single-flight, jitter, or stale-while-revalidate. For inventory, demonstrate that the cache never decides the final transaction.

### Task 4 — Design write failures

Analyze: source commit succeeds but cache update fails; cache update succeeds but source fails; write-behind buffer accepts writes while the worker is down; worker commits and crashes before ack. Define states and recovery.

### Task 5 — Capacity and observability

Calculate source QPS from the target hit ratio, estimate memory from payloads, and propose replication/headroom. Build dashboards for hits/misses, latency, evictions, loader QPS, stale age, invalidation lag, and backlog.

### Task 6 — Failure and security testing

Test cache unavailability, node failover, key collisions, cross-tenant access, malformed entries, hot keys, and duplicate events. Collect evidence on latency, database saturation, stale data, and duplicate side effects.

### Test matrix

| Test | Action | Expected outcome to verify |
| --- | --- | --- |
| Cold cache | Clear/switch cache namespace in test environment | Database does not suffer stampede exceeding quota |
| Stampede | Expire popular keys' TTLs simultaneously | Loaders are bounded; latency and source QPS stay within thresholds |
| Invalidation gap | Commit DB then intentionally fail invalidation publish | Outbox/retry or TTL recovers within freshness bounds |
| Concurrent inventory update | Multiple users book the same SKU/slot | Source constraints protect inventory without relying on cache |
| Write-through partial failure | Fail either cache or database | State is clearly reflected, with invalidation/reconciliation |
| Write-behind crash | Worker crashes after DB commit before ack | Redelivery produces no duplicate side effects |
| Cache outage | Block connectivity to the cache | Fallback is bounded and does not overload the source |
| Tenant isolation | Use the same resource ID across two tenants | No cross-tenant cache entries returned |
| Stale event | Older version event arrives after newer event | Newer value is not overwritten |
| Capacity peak | Increase QPS and hot keys | Memory/connections/quotas not exceeded; SLOs met |

## 18. Well-Architected Review

| Pillar | Questions for cache patterns |
| --- | --- |
| **Operational Excellence** | Are there runbooks for warm-up, invalidation, failover, cache flush, and backlog handling? Are keys/TTLs/policies managed as code and reviewed? |
| **Security** | Does the cache have proper private access, identity, TLS, encryption, tenant isolation, and data retention? |
| **Reliability** | How does the application fall back if the cache is lost? Have stampedes, hot keys, write-behind recovery, and stale bounds been tested? |
| **Performance Efficiency** | Are hit ratios, latency, memory, serialization, loader QPS, and query costs measured? |
| **Cost Optimization** | Do cache capacity, replication, networking, eviction, and operations cost less than the data source savings? |
| **Sustainability** | Are rarely used caches, redundant refreshes/polling, and unnecessarily large payloads avoided? |

## 19. Common Mistakes

**Using the cache as the source of truth without designing durability.** Caches can evict, fail over, or lose data depending on configuration; critical data must have durable storage.

**Choosing the same TTL for every key.** Catalogs, profiles, inventory, and counters have different freshness requirements.

**Only invalidating after writes without handling failures between commit and delete.** Outbox/retry or versioning is needed to prevent unbounded staleness windows.

**Allowing two writers to update the cache without versioning.** A slower older writer finishing later can overwrite newer data.

**Using cache locks instead of business transactions.** Cache locks do not replace uniqueness or transactions in the database.

**Writing to RAM and acking write-behind immediately.** Losing a node can lose unflushed mutations; durable buffers and replay are required.

**Leaving fallbacks unbounded.** A cache outage can push all traffic to the database and cause a cascading failure.

**Monitoring only hit ratio.** A high hit ratio does not prove data is fresh or latency is good.

**Omitting tenant/locale/filters from cache keys.** Data can leak across tenants or return wrong variants.

**Assuming read-through solves invalidation automatically.** Loaders only handle misses; data modified outside the cache still needs refreshing or invalidating.

**Ignoring cache stampedes and hot keys.** One expiring key can overload the data source.

**Lacking a process to purge personal data from the cache.** Data lifecycles must cover cache copies and snapshots.

## 20. Pre-Production Checklist

- [ ] Source of truth and cacheable data types are defined.
- [ ] Read/write patterns are selected based on freshness, durability, and latency requirements.
- [ ] Cache keys include tenant, locale, filters, version, and all factors affecting the result.
- [ ] TTL, invalidation, negative caching, and stale-while-revalidate have policies per data class.
- [ ] Competing writers are protected by versioning/transactions at the data owner.
- [ ] Cache-aside/read-through loaders have timeouts, retries, and request coalescing.
- [ ] Write-through handles partial failures between cache and source.
- [ ] Write-behind has durable buffers, idempotency, ordering, DLQ, replay, and reconciliation.
- [ ] Cache stampedes, hot keys, memory pressure, and cold-cache loads have been tested.
- [ ] Fallbacks on cache failure have concurrency/rate limits to prevent taking down the database.
- [ ] Clients, networking, secrets, TLS, tenant isolation, and data retention are controlled.
- [ ] Dashboards track hit/miss, latency, evictions, loader QPS, stale age, and invalidation lag.
- [ ] Costs of cache, replication, networking, logging, and data sources are compared.
- [ ] Runbooks exist for failover, flush, warm-up, invalidation, replay, and corrupted data handling.
- [ ] Concurrency, failure, security, and load tests show evidence of meeting targets.

Cache-aside, read-through, write-through, and write-behind are ways of organizing responsibilities between the application, cache, and data store. Cache-aside lets the application actively load and invalidate; read-through places the loader in the cache layer; write-through synchronizes writes with the source; write-behind accepts writes first and updates the source asynchronously. The right choice depends on which data may be stale, which store is authoritative, and how the system recovers when one step succeeds and another fails. Caching delivers lasting value only when TTL, invalidation, concurrency, fallbacks, security, and observability are designed alongside the pattern.
