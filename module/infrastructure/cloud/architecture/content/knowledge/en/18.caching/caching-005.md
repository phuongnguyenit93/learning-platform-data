# Cache Stampede, Hot Keys, and Load-Shedding Mitigations

## 1. Caches Accelerate Reads, Yet Can Also Trigger Load Incidents

A cache keeps a copy of data close to where it is used to reduce latency and access to the origin storage or service. When cache hits are high, the database receives fewer queries, responses are faster, and the system can serve more requests with the same compute capacity. However, a cache does not automatically guarantee that load is evenly distributed.

Two scenarios are especially dangerous:

- **Cache stampede:** many requests simultaneously encounter a cache miss or an expired key, and all query the origin at once to recompute the same data.
- **Hot key:** a single key receives far more traffic than other keys, overloading the cache node, partition, shard, or backend serving that key even when the overall cluster still has spare capacity.

In the **CLOUD_ARCHITECTURE** module, cache design must balance latency, scalability, reliability, cost, and operability. An effective cache is not just about a high hit ratio; it must also control concurrency on misses, handle stale data appropriately, distribute keys, protect the origin, and recover when the cache or backend fails.

After this lesson, you will be able to:

- Distinguish cache stampede, cache penetration, cache avalanche, and hot keys.
- Explain why synchronized TTLs or a single popular key can trigger traffic spikes.
- Apply TTL jitter, request coalescing/singleflight, stale-while-revalidate, refresh-ahead, and probabilistic early refresh.
- Design distributed locks, leases, fencing tokens, and lock-hold duration limits.
- Handle hot keys using replication, local caches, deliberate sharding, admission control, and asynchronous loading.
- Protect the origin with rate limits, concurrency limits, circuit breakers, backpressure, and fallbacks.
- Measure hits/misses, refreshes, waiters, origin load, key skew, and latency to prove effectiveness.

## 2. Identifying Four Types of Cache Problems

These problems can occur individually or simultaneously:

| Problem | What Happens | Typical Consequence |
|---|---|---|
| **Cache stampede** | Many requests simultaneously refresh a missing/expired key | Origin receives hundreds of duplicate queries for one piece of data |
| **Hot key** | A few keys account for a massive share of requests | One shard/node or that key's backend becomes overloaded |
| **Cache penetration** | Requests repeatedly query non-existent or uncached keys | Misses pass straight through to the origin; exploitable via random keys |
| **Cache avalanche** | Many keys expire or the cache layer fails near-simultaneously | Widespread concurrent misses and broad origin load surge |

### 2.1. BookingCloud example

BookingCloud displays a popular device page. The cache stores key `device:dev-017` with a 10-minute TTL. A marketing campaign drives 20,000 requests/second to this key. When the key expires, huge numbers of requests simultaneously read the database to reconstruct the object.

If the database can stably handle only 2,000 queries/second, excess requests build up queues, exhaust connections, time out, and trigger retries. Slower processing keeps requests alive longer; concurrent request counts climb further, creating an overload feedback loop.

The issue is not merely "a cache miss." It is that **the cache miss removed the load-shedding layer at the exact moment the system needed it most**.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Many clients
    participant C as Cache
    participant D as Database
    Note over C: Key expires
    par Request 1
        U->>C: GET device:dev-017
        C-->>U: MISS
        U->>D: SELECT device
    and Request 2
        U->>C: GET device:dev-017
        C-->>U: MISS
        U->>D: SELECT device
    and Request N
        U->>C: GET device:dev-017
        C-->>U: MISS
        U->>D: SELECT device
    end
    D-->>U: Repeated result computation
~~~

This is a cache stampede: many requests performing the exact same recomputation work within the same time window.

## 3. Why Do Stampedes Happen?

### 3.1. Synchronized TTLs

If the system populates a batch of keys at 09:00 with an exact 3,600-second TTL, many keys expire around 10:00. A campaign, batch job, or deployment can create a "wave" of cache misses.

Fixed TTLs also make replicas caching the same dataset expire together. If all application instances refresh from the origin concurrently, load scales with the number of replicas.

### 3.2. Popular key expiration

A high-traffic key can suffer a stampede even when only that single key expires. For example, a homepage often reads the same configuration object or featured list. When the key misses, concurrent requests trigger duplicate recomputations.

### 3.3. Cache node restart or cache flush

Deployments, failovers, evictions, memory pressure, flushes, or lost cache connectivity can trigger mass misses. If the application falls back directly to the database without concurrency limits, a cache failure turns into an origin failure.

### 3.4. Refresh slower than request rate

Even with a long TTL, a value may take several seconds to recompute. If thousands of requests arrive during computation, a stampede still occurs unless requests are coalesced.

## 4. TTL Jitter: Spreading Expiration Times

**TTL jitter** adds a random offset to TTLs so keys do not expire simultaneously.

Instead of a fixed 3,600-second TTL, you can choose:

~~~text
ttl = base_ttl + random(0, jitter_window)
~~~

or:

~~~text
ttl = base_ttl * random(0.8, 1.2)
~~~

For example, a 10-minute base TTL with ±20% jitter produces TTLs ranging from 8 to 12 minutes. Keys written at the same time will spread out their expirations.

### 4.1. Choosing appropriate jitter

- Additive jitter works well when you want to spread expirations across a fixed time window.
- Proportional jitter works well when TTLs across data groups span multiple orders of magnitude.
- For data with hard freshness deadlines, do not let jitter push the TTL past the allowed limit.
- Different jitter ranges can be used per data class or key category.

TTL jitter **reduces the likelihood of many keys expiring simultaneously**, but it does not completely solve a hot key experiencing thousands of concurrent misses. For a popular key, you also need request coalescing, stale serving, or refresh coordination.

## 5. Request Coalescing: One Fetch, Many Waiters

**Request coalescing** (also called singleflight in some libraries) collapses multiple concurrent requests needing the same key into a single origin fetch. The first request performs the load; remaining requests wait for that result instead of querying the origin independently.

~~~mermaid
flowchart TD
    R["Concurrent requests for one key"] --> G["Cache lookup"]
    G -->|"Hit"| H["Return cached value"]
    G -->|"Miss"| S["Singleflight / in-flight registry"]
    S -->|"Leader"| L["One origin fetch"]
    S -->|"Followers"| W["Wait for shared result"]
    L --> O["Origin"]
    O --> P["Populate cache"]
    P --> RET["Return result to leader"]
    P --> W
~~~

### 5.1. In-process coalescing

If the application runs in a single process, you can maintain a map from cache key to an active promise/future:

~~~text
get(key):
    value = cache.get(key)
    if value exists:
        return value

    return singleflight.do(key, function:
        value = cache.get(key)       # double-check
        if value exists:
            return value

        value = origin.fetch(key)
        cache.set(key, value, ttl_with_jitter)
        return value
    )
~~~

This is pseudocode. Production libraries must handle exceptions, cancellation, timeouts, memory cleanup, and races when entries complete or are deleted. Double-checking after becoming the leader prevents re-fetching if another request populated the cache while waiting.

### 5.2. Limits of local singleflight

With 30 application replicas, each process has its own singleflight. When a key misses, up to roughly 30 leaders can still query the origin simultaneously. This is usually far better than thousands of requests, though not a single cluster-wide fetch.

Three options exist:

- Accept one leader per process if the origin has sufficient capacity.
- Use distributed coordination so one worker/instance acts as the cluster-wide leader.
- Combine local coalescing with a distributed cache/refresh service to limit origin fetches.

Distributed locks add latency, network dependencies, and correctness complexity; do not add them to every cache key when local singleflight already meets SLOs.

## 6. Distributed Locks, Leases, and Fencing Tokens

When multiple application replicas share a cache, they may need to coordinate so only one replica refreshes a key at a time. A distributed lock is not as simple as "SET key = locked."

### 6.1. Locks with leases and unique tokens

A lock should include an identifier for the work key, a random owner token, a finite lease/TTL, a lock-wait timeout, and a cache double-check after acquisition. Only the valid owner may release the lock.

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Replica A
    participant B as Replica B
    participant L as Lock service
    participant C as Shared cache
    participant O as Origin
    A->>C: GET key
    C-->>A: MISS
    B->>C: GET key
    C-->>B: MISS
    A->>L: Acquire lease with owner token
    L-->>A: Granted
    B->>L: Acquire lease
    L-->>B: Busy
    A->>C: Double-check key
    C-->>A: MISS
    A->>O: Fetch value
    O-->>A: Result
    A->>C: SET value + TTL
    A->>L: Release only if owner token matches
    B->>C: Retry/read
    C-->>B: HIT
~~~

### 6.2. Why lock TTL alone is insufficient

Suppose Replica A holds a 5-second lease, but the origin query takes 8 seconds. The lock expires while A is still running. Replica B acquires a new lease and starts refreshing. A later finishes and overwrites the newer result with an older value.

A leased lock reduces deadlock risk if an owner crashes, but it does not automatically stop a stale owner from writing after its lease expires.

### 6.3. Fencing tokens

A **fencing token** is a monotonically increasing sequence number issued by the lock/coordination service on each acquire. The storage/write path checks the token; tokens older than an already accepted token are rejected. This prevents a stale owner from writing after a new owner has been granted access.

~~~text
Replica A acquires lease -> token 41
Lease A expires
Replica B acquires lease -> token 42
Storage accepts write with token 42
Replica A later sends write with token 41 -> reject
~~~

Fencing only works if the write destination actually enforces tokens. A simple Redis lock cannot stop an old process from writing directly to a database unless the database checks the fencing token or version. If the cache only stores regenerable copies, stale overwrites can be handled via version checks or compare-and-set; for business-critical data, stronger consistency mechanisms are required.

## 7. Stale-While-Revalidate and Stale-If-Error

One of the most effective ways to prevent stampedes is avoiding forcing every request to wait for fresh data the instant a TTL expires.

**Stale-while-revalidate (SWR):** after the fresh TTL passes, the cache continues returning the old copy within a stale window while one worker refreshes in the background.

**Stale-if-error:** if a refresh fails, the cache continues serving the old copy for an allowed window to preserve availability.

~~~mermaid
flowchart LR
    F["Fresh period"] --> S["Stale-while-revalidate window"]
    S -->|"Refresh succeeds"| N["New fresh value"]
    S -->|"Refresh fails, within policy"| E["Serve stale-if-error"]
    E --> R["Retry with backoff"]
    R -->|"Success"| N
    S -->|"Stale limit exceeded"| H["Fail / fallback by business policy"]
~~~

Example policy:

| Threshold | Behavior |
|---|---|
| 0–300 seconds | Return fresh value |
| 300–360 seconds | Return stale immediately; one request triggers background refresh |
| Refresh succeeds | Replace with new value and start a new TTL |
| Refresh fails within 10-minute stale-if-error | Continue serving old value and retry with limits |
| Stale window expires | Fail/fallback per business requirements |

These thresholds are illustrative only, not defaults for all data.

### 7.1. Which data can be served stale?

More suitable: device catalogs, images, marketing descriptions; rarely changing configs with last-known-good values; aggregated reports tolerating delay; recommendations if policy permits.

Use caution or never serve stale: monetary balances, access permissions, payment statuses; booking slots or inventory where stale values cause double-booking; revocations, credentials, security policies, and account lock states; data with mandatory freshness deadlines.

Never use SWR for data requiring strong consistency if a stale response can break invariants or trigger irreversible actions.

## 8. Refresh-Ahead and Probabilistic Early Refresh

Beyond waiting for TTL expiration, the system can proactively refresh entries before they expire.

### 8.1. Refresh-ahead

When a certain window remains before expiration, a background worker reloads the value. If it succeeds, replace the cache entry; if it fails, retain the existing copy within stale policy bounds.

The benefit is fewer cache misses during peak hours and the ability to refresh when the origin is less busy. The trade-off is wasting load refreshing rarely used keys; needing schedulers/workers and concurrency control; and accounting for freshness, versions, and failures.

Refresh-ahead can be paired with an admission policy: only refresh keys whose recent accesses or popularity exceed a threshold.

### 8.2. Probabilistic early expiration

For large keysets with fluctuating traffic, a request can be probabilistically selected to refresh before TTL expires. The probability increases as the key nears expiration or when origin computation takes longer.

~~~text
refresh_probability = f(time_to_expiry, observed_load_time, traffic_rate)
~~~

No single formula fits every application. Some probabilistic early expiration algorithms use the most recent load duration and an exponential random variable to spread refreshes without a global lock. Load-test, measure wasted refreshes, and verify freshness.

## 9. Hot Keys: When One Key Dominates Total Load

Hot keys differ from stampedes: the cache may have a great hit ratio, yet one key receives overwhelming traffic. If a cache cluster shards by key hash, every request for that key hits the same shard. That shard overloads while other shards remain idle.

For example, the key `homepage:featured-devices` receives 40% of total requests. Adding shards does not automatically help because the hash of that single key still maps to one shard.

### 9.1. Replicating popular values

For read-only data or distributable updates, create multiple cache replicas and spread reads:

~~~mermaid
flowchart TB
    U["High-volume clients"] --> LB["Read routing"]
    LB --> R1["Cache replica A"]
    LB --> R2["Cache replica B"]
    LB --> R3["Cache replica C"]
    R1 --> ORIGIN["Origin / refresh result"]
    R2 --> ORIGIN
    R3 --> ORIGIN
    REF["Refresh publisher"] --> R1
    REF --> R2
    REF --> R3
~~~

Variants:

- Replicas across multiple cache nodes/zones to boost read capacity.
- Local in-process caches on application replicas for public keys, with short TTLs/invalidation.
- CDN edge caches for cacheable content close to users.
- Database read replicas if query and consistency semantics allow.

Replication increases read capacity but requires synchronized invalidation/updates. Multiple copies may keep serving stale values until updates arrive; define freshness and propagation bounds.

### 9.2. Key salting and sharding

A hot key can be split into multiple sub-keys, for example:

~~~text
homepage:featured-devices:bucket-00
homepage:featured-devices:bucket-01
homepage:featured-devices:bucket-02
...
~~~

This only helps if requests can genuinely be distributed across buckets and content can be replicated or partitioned. If every request must still read a single counter or object before picking a bucket, the bottleneck remains.

Do not append random suffixes to shard when each suffix leads to independent data or inconsistent population. For a single shared value, fan-out writes/updates can be costly; use a canonical source and distribute snapshots to replicas.

### 9.3. Local cache and CDN

Local caches provide low latency and reduce traffic to shared caches, though each process holds its own copy. Enforce short TTLs or versioned invalidation; cap memory and configure eviction policies; never cache user/tenant-scoped data without identity scope in keys; and accept eventual updates only where business rules allow.

CDNs suit public/cacheable content; configure Cache-Control, surrogate keys/purges, Vary dimensions, and authorization carefully. Never let a CDN cache private responses just because URLs match.

## 10. Cache Penetration and Negative Caching

Attackers or buggy clients can send many random non-existent keys. Because caches normally do not store misses, every request falls through to the database.

Mitigations:

- **Negative caching:** cache "not found" results with a short TTL.
- **Bloom filter:** a probabilistic structure checking whether a key might exist; false positives can happen, while false negatives must be controlled by how it is initialized and updated.
- Validate IDs/formats before calling the origin.
- Rate-limit by identity/IP/API key and cap concurrency.
- Monitor miss rates for nonexistent keys and anomalous request sources.

Negative caching requires care when new resources are created: if NOT_FOUND is cached too long, users cannot see newly created resources. Invalidate negative entries on create commits or keep TTLs short.

## 11. Protecting the Origin: Preventing Cache Failures from Causing Database Outages

A cache is only an optimization layer. The origin needs load limits independent of the cache.

### 11.1. Concurrency limits and semaphores

Cap concurrent origin queries per resource group or service. Once the threshold is reached, queue requests within bounded limits; serve stale data if policy allows; return controlled overload errors; or deprioritize background refreshes.

Unbounded queues merely convert overload into latency and memory exhaustion. Cap queue length, queue wait time, and deadlines.

### 11.2. Rate limits and token buckets

Rate limits cap origin call rates by tenant, client, route, or key group. Token buckets allow brief bursts while bounding average rate. Partition budgets between foreground requests and background refreshes so refreshes do not starve user traffic.

### 11.3. Circuit breakers

When the origin repeatedly fails or times out, a circuit breaker opens to temporarily stop sending new requests, preventing incident amplification. After a cooldown, let a few requests probe (half-open). While the breaker is open:

- Serve stale data if permitted for that data class.
- Return a business-meaningful fallback.
- Return structured errors if safe serving is impossible.
- Never retry immediately across every application replica.

### 11.4. Backpressure and graceful degradation

Under overload, shed work rather than accepting unbounded load: temporarily drop recommendations or view counts; cache aggregated responses; throttle non-urgent batches/refreshes; reserve capacity for critical operations like creating or canceling bookings; and return 429/503 with Retry-After where appropriate so clients back off.

~~~mermaid
flowchart TD
    REQ["Request"] --> CACHE["Cache lookup"]
    CACHE -->|"Hit"| OK["Return cached"]
    CACHE -->|"Miss"| GUARD["Origin load guard"]
    GUARD --> CB{"Circuit breaker"}
    CB -->|"Closed + capacity"| SEM["Concurrency / rate limit"]
    CB -->|"Open"| STALE["Serve stale if allowed"]
    STALE -->|"Not allowed"| ERR["Controlled fallback/error"]
    SEM -->|"Admitted"| ORIGIN["Origin service"]
    SEM -->|"Rejected / queue full"| STALE
    ORIGIN -->|"Success"| SET["Populate cache"]
    ORIGIN -->|"Timeout / error"| STALE
    SET --> OK
~~~

### 11.5. Never let fallbacks break business correctness

Default values of 0, empty lists, or old states may keep the UI running while producing wrong business outcomes. Product pages can display slightly stale descriptions; recommendations can be skipped temporarily; booking slot availability requires an authoritative source or a clear "cannot verify yet" message; authorization must never fall back to allow; unknown payment outcomes must never be assumed failed to trigger a re-charge or assumed succeeded to confirm an order.

## 12. Choosing Strategies by Workload

| Workload | Primary Risks | Recommended Mitigations |
|---|---|---|
| Public product/catalog | Hot keys, cache avalanche | CDN/local cache, TTL jitter, refresh-ahead, replicas |
| Personal booking details | Wrong key scope, stampede, stale privacy | Tenant/user-scoped keys, singleflight, short TTL |
| Slot availability | Staleness causing double-booking | Use DB/strong source for write decisions; cache as hint only |
| Dashboards/reports | Heavy-query stampedes | SWR, background refresh, coalescing, materialized views |
| Sessions/tokens | Invalidation and security | Exact TTL/expiry, revocation semantics, no arbitrary stale serving |
| Configs/feature flags | Simultaneous key expiration | Jitter, local cache, versioning/invalidation |
| Recommendations | Hot aggregate keys, expensive origin queries | Precomputation, replication, stale serving |
| Negative lookups | Penetration from random keys | Short-TTL negative cache, validation, Bloom filters, rate limits |

## 13. Observing Caches and Detecting Anomalies

A high hit ratio alone does not prove a cache is healthy. A cache can achieve 99% hits while the 1% misses concentrate on one hot key and overload the origin; or hits may serve overly stale data.

### 13.1. Metrics to monitor

| Metric | Meaning | Anomaly Indicator |
|---|---|---|
| Hit/miss ratio | Share of requests served from cache | Sudden miss spike after deploy/expiry |
| Origin QPS | Queries hitting the source | Rapid surge during misses or flushes |
| Refresh count/duration | Count and time to recompute keys | One key refreshing multiple times in parallel |
| Coalesced waiter count | Requests waiting on one refresh | High counts indicate slow refreshes |
| Lock contention/lease expiry | Refresh contention | Leases expiring before owners finish |
| Stale response rate/age | Frequency and age of served stale data | Prolonged rise or freshness budget breach |
| Hot-key skew | Traffic share of top keys/shards | One shard far exceeding others |
| Evictions/memory usage | Memory pressure and key churn | Cache thrashing |
| Origin latency/errors | Dependency health | Timeouts, connection pool exhaustion |
| Negative-cache hits | Misses blocked at the cache | Spike in bots or random keys |

### 13.2. Avoiding cardinality explosion

Never attach raw cache keys as metric labels; one million keys can create one million time series. Instead, capture top-N hot keys via logs/sampling or bounded diagnostic views; group metrics by key namespace, tenant tier, shard, endpoint, and data class; use histograms for latency; hash/mask keys containing sensitive IDs; and use trace exemplars or sampled events.

### 13.3. Request-flow dashboards

A cache incident dashboard should display side by side: incoming QPS, hits/misses, origin QPS/latency, refresh concurrency, top hot namespaces, cache memory/evictions, DB connections, error rates, and stale age. With only cache hit ratio, it is hard to see where misses are putting pressure.

## 14. Testing and Drills for Stampedes and Hot Keys

Before production, simulate these scenarios:

1. Thousands of concurrent requests for a cold key.
2. An ultra-popular key expiring during peak traffic.
3. Many keys populated simultaneously and expiring simultaneously.
4. Cache cluster restarts or network partitions.
5. Origin responding slower than the lease/refresh timeout.
6. Lock holder killed before writing to the cache.
7. Lock lease expiring while the old leader is still running.
8. Refreshes failing repeatedly or returning invalid payloads.
9. A tenant/client sending random keys to trigger penetration.
10. Cache replicas remaining stale after purges/invalidations.

### 14.1. Acceptance criteria

Pre-define max origin QPS and concurrent queries; max origin loads per key within one refresh window; p95/p99 latency and error rates; recovery time after cache flush/node loss; maximum freshness/stale age per data class; percentage of shed/rate-limited requests; and verification that zero bookings, payments, or authorizations fail correctness due to stale fallbacks.

Good tests intentionally inject faults while verifying that the system preserves origin limits and returns responses compliant with policy.

## 15. Reference Design for BookingCloud

Suppose the public product catalog has high traffic, while slot availability and booking details are business-critical.

| Flow | Cache Strategy | Origin Protection | Consistency Policy |
|---|---|---|---|
| Public product pages | CDN + shared cache + short local cache | TTL jitter, SWR, refresh-ahead | Tolerates a few minutes of staleness |
| Popular device details | Replicated hot entries + singleflight | Per-key refresh limit, origin semaphore | Versioned refresh, stale window |
| Booking details | Tenant/user-scoped keys, coalescing | Rate/concurrency limits | Short TTL; invalidate after mutation |
| Slot availability | Cache for display hints only | Write path always checks authoritative source | Never decide bookings from stale cache |
| Recommendations | Precompute + CDN/local cache | Background refresh, stale-if-error | Tolerates bounded stale data |
| User-not-found lookups | Short negative cache + input validation | Rate limits and origin budget | Invalidate when user is created |

~~~mermaid
flowchart TB
    CLIENT["Web / mobile clients"] --> CDN["CDN / edge cache"]
    CDN --> API["API gateway / application"]
    API --> LOCAL["Local cache + request coalescing"]
    LOCAL --> SHARED["Shared cache / hot-key replicas"]
    SHARED --> GUARD["Refresh coordinator + origin guard"]
    GUARD --> ORIGIN["Catalog / reporting origin"]
    ORIGIN --> DB[("Database / materialized view")]
    ORIGIN --> SHARED
    API --> BOOK["Booking write service"]
    BOOK --> DB
~~~

The diagram shows the cache serving reads and offloading the origin; booking writes still verify invariants at the authoritative data source. Never turn the cache into the final decision-maker for booking transactions.

## 16. Well-Architected Review

| Pillar | Review Question | Required Evidence |
|---|---|---|
| **Operational Excellence** | Who monitors hot keys, refresh queues, and cache recovery? | Dashboards, alerts, runbooks, load/chaos drills, and owners |
| **Security** | Do cache keys isolate tenants/users? Could stale data or CDNs leak private data? | Key scoping, authorization tests, TLS, private access, and log redaction |
| **Reliability** | Can a cache flush, node loss, or origin outage take down the database too? | Coalescing, stale policies, origin concurrency budgets, circuit breakers, and failover tests |
| **Performance Efficiency** | Are hot-key reads distributed? Do refreshes compete with foreground traffic? | Key skew, p95/p99, origin QPS, waiter counts, and refresh latency |
| **Cost Optimization** | Are replication, local caches, CDNs, and refresh-ahead worth their cost? | Cost per request, avoided origin queries, memory/egress, and refresh overhead |
| **Sustainability** | Are rarely used keys refreshed, redundant data cached, or caches kept overly large? | Admission metrics, evictions, TTL/retention policies, and resource utilization |

A load-shedding solution must prove both sides: the cache can serve the target read volume, and the origin remains protected when the cache misses or fails. Adding replicas or extending stale windows without measuring freshness, memory, egress, and correctness may simply shift costs or risks elsewhere.

## 17. Hands-On Exercise: Handling Cache Stampedes and Hot Keys

BookingCloud has an endpoint GET /devices/dev-017. During peak hours:

- The endpoint receives 15,000 requests/second.
- Cache TTL is 5 minutes.
- Origin queries take p95 250 ms and handle only about 2,500 queries/second for this workload.
- There are 20 application replicas.
- The shared cache is currently sharded by key hash.
- When the key expires, origin QPS spikes and the database connection pool saturates.

The team proposes doubling the number of cache shards.

Complete the following:

**Exercise 1 — Diagnosis:** explain why adding shards will likely not fix a hot key; distinguish stampede issues from key skew.

**Exercise 2 — Coalescing:** choose local singleflight, a distributed refresh lock, or a combination. Estimate the maximum concurrent origin fetches if only local singleflight is used across 20 replicas.

**Exercise 3 — Freshness:** propose TTL jitter, stale-while-revalidate, and stale-if-error windows for product details. Define conditions for stopping stale serving.

**Exercise 4 — Lock safety:** describe leases, owner tokens, timeouts, and fencing tokens; analyze what happens when an old leader finishes after its lease expires.

**Exercise 5 — Hot keys:** propose replicas/local cache/CDN or precomputation; explain how updates and invalidation prevent copies from going too stale.

**Exercise 6 — Origin protection:** design rate limits, concurrency limits, circuit breakers, and backpressure; specify when to return 429/503.

**Exercise 7 — Verification:** design load tests for cold keys, cache flushes, slow origins, leader crashes, and a tenant sending random keys. Select metrics and go/no-go thresholds.

### Self-check analysis framework

| Decision | Line of Reasoning |
|---|---|
| Adding shards | Helps only if many keys/partitions are skewed; a single key still hashes to one shard |
| Local singleflight | At most roughly one leader per key per process; 20 replicas can still trigger 20 origin fetches |
| Distributed coordination | Reduces cluster-wide leaders, though adds latency and failure modes; needs leases/fencing or versioning |
| SWR | Returns stale immediately within window and refreshes in background; never use for booking/payment decisions |
| Replicas | Increases read capacity; must have refresh/invalidation and freshness policies |
| Origin guards | Caps concurrency/rate; never allow unbounded queues |
| Fallbacks | Preserves availability, yet must maintain business semantics and never bypass access control |

These figures are for exercise purposes only. Production designs require benchmarking and verifying traffic shapes and data freshness.

## 18. Pre-Production Checklist

- [ ] Cache stampede, hot keys, penetration, and avalanche risks are classified for the workload.
- [ ] TTLs have appropriate jitter; freshness deadlines are defined per data class.
- [ ] Cache misses use request coalescing or refresh coordination where needed.
- [ ] Refresh leaders double-check the cache before calling the origin.
- [ ] Distributed locks have owner tokens, leases, timeouts, and safe release.
- [ ] Where correctness requires it, write paths enforce fencing/version checks to block stale owners.
- [ ] SWR/stale-if-error is enabled only for data classes permitted to serve stale data.
- [ ] Refresh-ahead/probabilistic refreshes are bounded to avoid wasted refreshes.
- [ ] Hot keys are identified; replication/local caches/CDN/sharding are chosen from access patterns.
- [ ] Cache keys include proper tenant/user scope to prevent data leaks.
- [ ] Negative caching has appropriate TTLs and invalidates when new resources are created.
- [ ] The origin has rate limits, concurrency budgets, bounded queues, circuit breakers, and backpressure.
- [ ] Fallbacks never allow incorrect decisions for bookings, payments, or authorization.
- [ ] Metrics include origin QPS, refresh concurrency, waiter counts, hot-key skew, and stale age.
- [ ] Cache flushes, node failures, slow origins, duplicate refreshes, and lock expirations have been rehearsed.

A cache stampede occurs when many requests recompute the same value simultaneously; a hot key occurs when a few keys concentrate most of the traffic. TTL jitter staggers expirations, request coalescing collapses duplicate loads, stale-while-revalidate avoids blocking callers, and replication plus local/edge caches expand read capacity for popular keys. These measures must be paired with origin guards, freshness policies, and comprehensive observability so cache failures never cascade into database outages or corrupt business state.
