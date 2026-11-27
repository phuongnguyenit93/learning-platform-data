# Identifying Suitable Data and Objectives for Caching

A cache is often added when a system is slow or the database is under heavy load. However, caching does not automatically make every application faster. It introduces an additional copy of the data, which can become older than the primary source, requires storage capacity, and needs an expiration/refresh process. If you cache the wrong data, set an arbitrary TTL without basis, or lack a strategy for handling cache misses, the system can return incorrect results, trigger sudden traffic spikes, or become difficult to recover when the cache goes down.

Before choosing Redis, Memcached, a CDN, or an in-process cache, an architect must answer a fundamental question: **which data is worth caching, to achieve what objective, and how stale can that data be tolerated?**

This lesson belongs to the **Caching** chapter of the **CLOUD_ARCHITECTURE** module. The goal is to analyze access patterns, the value of data reuse, freshness, and consistency; define latency, throughput, and cost objectives; select suitable data; and identify cases that should not be cached. These decisions must balance reliability, security, performance, cost, and operations following a Well-Architected mindset.

## 1. What Problem Does Caching Solve?

A cache keeps a copy of data or computation results in a location that can be accessed faster than the primary source. When a request arrives:

- **Cache hit:** the required data is available in the cache and returned according to policy.
- **Cache miss:** the cache does not have a valid copy; the system fetches it from the primary source or recomputes it, and may then store it in the cache.
- **Stale entry:** data remains in the cache but no longer reflects the latest state of the source.
- **Eviction:** the cache removes an entry to free up capacity or according to a replacement policy.
- **Invalidation:** an entry is marked invalid or deleted when the source changes.

For example, the Booking API displays a room detail page. Descriptions, images, amenities, and cancellation policies are typically read many times while changing infrequently. Prices and availability, on the other hand, can change continuously. If all fields are cached with the same long TTL, the UI may display outdated prices or availability.

~~~mermaid
flowchart LR
    U["Client request"] --> APP["Application"]
    APP --> C{"Cache hit?"}
    C -->|"Yes"| R["Return cached data"]
    C -->|"No"| DB[("Source of truth")]
    DB --> APP
    APP -->|"Optional: populate/update"| C
    APP --> R
~~~

Caching is commonly used to reduce data read latency, offload databases or external APIs, absorb bursts, serve content closer to users via a CDN, reduce service call or computation costs, and maintain availability for certain functions when the source is slow if clear stale/fallback policies are in place.

A cache is not the authoritative source of data for critical transactions unless the architecture explicitly defines its role and durability mechanisms. If the cache is lost, the system should generally be able to retrieve the data from the source of truth or regenerate the copy.

## 2. Start from Access Patterns, Not Technology

The same type of data can be suitable or unsuitable for caching depending on how the application accesses it. Before choosing a cache, gather the following characteristics:

| Characteristic | Question to Answer | Implication for Caching |
|---|---|---|
| Read frequency | How often is the data read? | High reads can increase the value of reuse |
| Write/update frequency | Does the data change frequently? | High writes make the cache prone to staleness and costly invalidation |
| Read/write ratio | What is the ratio of reads to writes? | Read-heavy workloads typically benefit more easily |
| Reuse/popularity | Do many requests ask for the same key? | High reuse yields better hit rates |
| Working set | How many keys are frequently accessed? | Determines the capacity needed to keep data hot |
| Entry size | How large is each entry? | Affects memory, network, and eviction |
| Access locality | Are requests concentrated by key, tenant, or region? | May dictate tiered or partitioned caching |
| Computation cost | How much time/CPU/API calls does it take to produce the data? | Expensive computation results may be worth caching |
| Freshness requirement | How old is the data allowed to be at most? | Shapes TTL and invalidation |
| Consistency requirement | Is it necessary to immediately read a newly written value? | May rule out caching or require special design |
| Lifetime | How long can the data be reused? | Very short-lived entries may not be worth caching |

A cache key can only be reused if requests are truly equivalent. For example, room page content may depend on locale, currency, tenant, permission group, or feature flags. If the key is only roomId, the cache might return a translation, price, or data that does not belong to that user.

### 2.1. Read-heavy and write-heavy

- **Read-heavy:** the same data is read many times between updates; caching has an opportunity to reduce calls to the source.
- **Write-heavy:** data changes continuously; the cache suffers constant invalidation or returns stale copies. Benefits must be measured carefully.
- **Mixed workload:** some fields or endpoints are read-heavy while others are write-heavy. You can cache a projection or the less-frequently changing parts instead of the entire record.

Examples:
- Room type catalog: high reads, changes a few times per day — a good candidate.
- Display configuration: read frequently, changes when updated by an admin — can be cached with invalidation.
- Per-minute availability: changes continuously — short TTL or cache aggregated results with a timestamp.
- Wallet balance/transaction status: high accuracy required — consider avoiding cache as the source for transaction decisions.

## 3. Quantifying the Value of Caching

You should not cache simply because an endpoint receives many requests. Benefits should be estimated across three dimensions: latency, source load, and cost.

### 3.1. Cache hit ratio

Simple hit ratio:

\[
Hit\ Ratio = \frac{Cache\ Hits}{Cache\ Hits + Cache\ Misses}
\]

If there are 900 hits and 100 misses out of 1,000 requests, the hit ratio is 90%. However, a high hit ratio alone does not prove a cache is useful:
- Entries may be very small and the source is already fast.
- Some hits may hold data that is cheap to recompute.
- Cache hits may return stale data and cause business errors.
- A system-wide hit ratio may mask a critical endpoint with a high miss rate.

You need to track hit ratio by dataset, key namespace, endpoint, and over time; while also measuring latency, source load, and data quality.

### 3.2. Estimating latency

Suppose a source read takes 80 ms on average, a cache hit takes 4 ms, and the hit ratio is 90%, ignoring other overhead:

\[
E[T] = 0.9 \times 4 + 0.1 \times 80 = 11.6\ ms
\]

This is only a simplified estimate. In practice, you must account for the network hop to a distributed cache, serialization/deserialization, payload size, cache contention, queueing, p95/p99, and cold starts. The miss path can be slower because the application has to check the cache first before reading the source. If the source already responds in 3 ms while a remote cache takes 5 ms, adding a cache can slow down the read path.

### 3.3. Reducing source load

If an endpoint receives 10,000 requests/second and maintains a steady 90% hit ratio, source reads under a simple model drop from 10,000 to about 1,000 requests/second. This only holds if each miss triggers a single source read, there is no stampede, retry, or background refresh creating extra load, and key distribution stays stable. You must measure actual QPS at the source rather than inferring it solely from cache metrics.

### 3.4. Total cost

Caching can reduce database instance size, compute, or external API calls, but it incurs costs for memory/storage, nodes/replicas, network and cross-zone traffic, request operations, backup/replication, operational effort, and duplicated data. Compare the total per-request cost before and after: source reads, cache reads/writes, network, compute, and operations. Caching is not always cheaper when data is rarely read or the source is very inexpensive.

## 4. Which Data Is Suitable for Caching?

Good candidates typically exhibit one or more of these traits:
1. Read repeatedly across many requests.
2. Relatively high cost to query, compute, or call the source API.
3. Freshness requirements that can be expressed as a TTL or invalidation.
4. Regenerable from the authoritative source.
5. A temporary copy will not cause incorrect business decisions.
6. Bounded key space and storage capacity.

| Data Type | Reference Suitability | Why | Conditions/Risks |
|---|---|---|---|
| Catalogs, room types, amenities | High | Changes rarely, read often | Invalidate when admin updates |
| CMS content, images, static assets | High | Can be versioned/immutable | Proper CDN and cache-control |
| Public configuration | High | Many clients read the same value | Versioning and propagation |
| Dashboard aggregations | Medium–high | Queries/aggregations can be expensive | Timestamp, freshness, and permissions |
| User profiles | Use-case dependent | May be read repeatedly | Tenant/user isolation, expiry |
| Sessions/tokens | Requires custom design | Accessed frequently | Revocation, expiry, and security |
| Pricing/availability | Accuracy dependent | Read often but changes | Short TTL, verify before transaction |
| Balances/transaction status | Low for write decisions | Requires high accuracy | Do not use stale cache to confirm |
| Sensitive personal data | Caution | Reduces load but increases copies | Encryption, isolation, purge |
| Rare ad-hoc queries | Usually low | Low reuse | Cache churn and memory waste |

This is not an absolute classification. Financial reports may be cached for dashboard display with a label like "updated at 10:05", but that cached copy must not be used to decide payments or accounting entries.

### 4.1. Caching data or caching results?

- **Entity/data caching:** stores a record/object by ID, such as room type details. Easy to reuse across multiple queries, though it may require assembling data.
- **Query/result caching:** stores the result of a query or calculation, such as the top 20 most-viewed rooms of the week. Reduces computation, but keys are complex, cardinality is high, and invalidation is difficult when many records affect the result.

Choose based on access patterns and change scope. Do not cache arbitrary query sets if each key is only used once.

## 5. Data That Should Not Be Cached or Needs Strict Limits

In several cases, caching usually offers no benefit or carries high risk:
- Data changes after almost every request and must always reflect the latest state.
- Results have nearly unique keys, leading to low hit rates.
- Payloads are too large relative to capacity and reuse value.
- Queries are already very fast, and adding a cache network hop increases latency.
- Confidential data lacking isolation, encryption, and purge design.
- Results depend on identity, permissions, tenant, or locale, yet the key fails to capture full context.
- The cache is treated as the sole data store without durability or recovery.
- Stale results could cause side effects or erroneous transactional decisions.

"Do not cache" is also a valid architectural decision. You can optimize queries/indexes, connection pools, pagination, read replicas, or algorithms before adding a cache.

## 6. Freshness, TTL, and Consistency

Caching always poses the question: **how old can a copy be while remaining acceptable to the business?**

### 6.1. TTL

Time to live (TTL) is the duration an entry is considered valid from the time it is stored or refreshed according to system semantics.

A long TTL can increase hit ratio and reduce source load, but data stays stale longer. A short TTL typically provides fresher data, yet increases misses, source load, and the chance of many entries expiring simultaneously. TTL must derive from freshness requirements. A catalog that changes every few hours can tolerate a TTL of several minutes; transaction status may require reading the source or immediate update/invalidation. Never pick a TTL just because "5 minutes is common".

### 6.2. Freshness budget

| Data | Illustrative Freshness Budget | Handling Approach |
|---|---|---|
| Versioned images/content | Daily or until next version | Long cache with versioned keys |
| Amenities catalog | A few minutes | TTL + invalidate on publish |
| Landing page content | 1–5 minutes | CDN cache, purge on publish |
| Search results | A few seconds to one minute | Short TTL or refresh |
| Availability | 0–a few seconds depending on business rules | Very short cache; verify before booking |
| Payment status | Per transaction requirements | Read authoritative source |

These durations are illustrative only. Product owners and business systems must define actual acceptable thresholds.

### 6.3. Cache consistency models

- **Eventual consistency:** the cache converges to the new value after some time or once refresh/invalidation succeeds.
- **Read-after-write:** after a user performs an update, subsequent read requests must see the newly written value.
- **Authoritative read:** requires reading the authoritative value at the point of decision.
- **Stale-while-revalidate:** serves an old copy within an allowed window while refreshing in the background.
- **Stale-if-error:** when the source fails, serves an old copy within a defined fallback window.

No single consistency model fits every field. A detail page may show content that is a few seconds stale, but when a user confirms a booking, availability must be verified against the authoritative source.

## 7. Cache Update Strategies

### 7.1. Cache-aside (lazy loading)

The application checks the cache first; on a miss, it reads from the source, writes the result into the cache, and returns it.

~~~mermaid
sequenceDiagram
    participant A as Application
    participant C as Cache
    participant DB as Database
    A->>C: GET key
    alt Cache hit
        C-->>A: Value
    else Cache miss
        C-->>A: Miss
        A->>DB: Read source
        DB-->>A: Value
        A->>C: SET key with TTL
        A-->>A: Return value
    end
~~~

Pros: only caches data that is actually requested; simple and easy to implement. Trade-offs: the first miss request is slow; requires handling stampedes, stale entries, and cache write failures.

### 7.2. Read-through

The application asks the cache to read a key; the cache layer fetches data from the source on a miss via a configured loader. This centralizes loading logic, though it introduces coupling to the cache client/library and still requires handling errors, TTL, and invalidation.

### 7.3. Write-through

When the application writes data, the cache layer updates both the source and the cache in the same flow. This ensures the cache has fresh data after a write if the operation completes properly, but it can increase write latency and requires handling partial failures between the two stores.

### 7.4. Write-behind / write-back

The application writes to the cache first, and the cache writes asynchronously to the source later. This can speed up writes, though at higher risk: losing the cache before flushing can cause data loss; durability, retries, and ordering must be guaranteed; and reconciliation is difficult when source writes fail. Not suitable by default for critical transactions without robust durability mechanisms.

| Pattern | When Suitable | Risks to Manage |
|---|---|---|
| Cache-aside | Read-heavy, want control inside the app | Misses, invalidation, stampede |
| Read-through | Want to centralize loading in the cache layer | Coupling with library/provider |
| Write-through | Need immediate cache update after writes | Latency and partial failure |
| Write-behind | Accept asynchronous writes with durability | Data loss, ordering, reconciliation |

## 8. Choosing Cache Placement by Data and Objective

~~~mermaid
flowchart TB
    U["Browser / Mobile"] --> EDGE["Browser cache / CDN / Edge"]
    EDGE --> GW["API gateway / reverse proxy"]
    GW --> APP["Application / in-process cache"]
    APP --> DIST["Distributed cache"]
    DIST --> DB[("Database / source of truth")]
~~~

| Tier | Examples | Suitable Data | Considerations |
|---|---|---|---|
| Browser/client | HTTP cache, local cache | Images, JS/CSS, public content | Requires cache headers and privacy |
| CDN/edge | Static assets, public API responses | Widely distributed, rarely changing content | Invalidation, cache key, geo, and authorization |
| Gateway/reverse proxy | GET responses, metadata | High-reuse endpoints | Vary, auth, cookies, status/error caching |
| In-process | Map/LRU in JVM | Small, immutable configs, frequent lookups | Each instance holds its own copy |
| Distributed cache | Managed Redis/Memcached | Sessions, hot data, query results | Network hop, HA, scaling, eviction |
| Database cache/buffer | Buffer pool, query/page cache | Data pages/indexes | Managed by DB engine; does not replace app cache |

### Local cache and distributed cache

**Local/in-process cache** is fast because it avoids network calls, making it suitable for small, heavily read values where instances can tolerate updating at slightly different times. However, 10 instances mean 10 separate copies; invalidation requires broadcasting/versioning or short TTLs.

**Distributed cache** shares cached entries across multiple instances, reducing duplicate data per process. In return, every read goes over the network; the cache cluster becomes a dependency requiring HA, scaling, failover, and monitoring.

A system can combine both: a very short-TTL local cache in front of a distributed cache, provided versioning/invalidation rules prevent compounding layers of staleness.

## 9. HTTP Caching, CDN, and Cache-Control

For HTTP, response headers instruct browsers and intermediary caches on how to store and reuse responses.

Common directives:
- public: the response may be stored by shared caches according to policy.
- private: only private caches (such as the user's browser) may store it.
- no-store: do not store the response under this directive.
- no-cache: may be stored, but must be revalidated before reuse.
- max-age: maximum age in seconds for eligible caches.
- s-maxage: max age specifically for shared caches.
- must-revalidate: caches must revalidate once stale per HTTP semantics.
- stale-while-revalidate: allows serving stale responses within a specified window if the cache supports it.

For example, immutable assets can use:

~~~http
Cache-Control: public, max-age=31536000, immutable
~~~

This fits when the URL contains a content hash/version and the content at the same URL never changes. When releasing new content, generate a new URL.

User-specific responses require care:

~~~http
Cache-Control: private, max-age=60
Vary: Accept-Language
~~~

If a response depends on cookies, Authorization, tenant, or role, verify whether a shared cache is allowed to store it and whether the cache key distinguishes all variants adequately. Never use public for sensitive data just to boost hit ratios.

### Cache keys and Vary

Caches must distinguish requests that can produce different responses. Common dimensions include: path/query, Accept/Accept-Language, cookies/session, tenant, authorization role/scope, feature flags, locale, and currency.

Missing a dimension can cause the cache to serve one user/tenant's response to another. Including too many dimensions increases cardinality and lowers the hit ratio. Key design impacts both correctness and security.

## 10. Caching Data in the Booking System

Not every field on a screen should share the same policy.

| Room Page Component | Access Pattern | Objective | Illustrative Cache Decision |
|---|---|---|---|
| Room images | High reads, rare changes | Reduce latency/origin traffic | Long CDN/browser cache, versioned URLs |
| Description/amenities | High reads, rare admin updates | Reduce queries | Cache-aside for a few minutes, invalidate on publish |
| Cancellation policy | High reads, versioned changes | Consistency of published content | Cache by policy version |
| Listed price | High reads, changes by schedule/promo | Reduce queries | Short cache, keyed by currency/tenant/segment |
| Availability | Changes on booking/cancel | Prevent overbooking | Very short cache; atomic verify before booking |
| Payment status | Transaction dependent | Authoritative state | Read primary source or consistent mechanism |
| Search reports | Expensive aggregation queries | Reduce compute/database load | Cache by query key, TTL, and timestamp |
| User profile | User-specific, changes on profile edit | Reduce repeated queries | Keyed by user/tenant; invalidate after update |

You can cache room descriptions for 5 minutes, but when a user clicks confirm booking, the backend must verify availability and price against the authoritative source within a transaction or reservation mechanism. A single screen may combine multiple sources with different freshness levels; the UI should indicate when data is indicative only.

## 11. Cache Stampede, Hot Keys, and Eviction

### 11.1. Cache stampede

When a popular key expires, many requests miss simultaneously and call the database at once. This can cause a sudden load spike.

Mitigations:
- **Single-flight/request coalescing:** one request refreshes the key; other requests wait for the result.
- **TTL jitter:** spread out expiration times.
- **Refresh-ahead:** refresh entries before they expire.
- **Stale-while-revalidate:** return stale data within the allowed budget while refreshing in the background.
- **Bounded locks:** one worker refreshes; lock timeouts and crashed workers must be handled.

Do not serve stale data for cases where staleness can cause severe business impact.

### 11.2. Hot keys

A very popular key can overload a single cache node or partition. Monitor request rates per key/shard, and consider local caching, replication/read scaling, key sharding, or precomputation. Mechanically splitting keys can complicate invalidation.

### 11.3. Eviction policies

When memory runs out, the cache selects entries to remove:
- **LRU:** evicts the least recently accessed entries.
- **LFU:** prefers keeping entries accessed most frequently.
- **TTL-based expiration:** deletes expired entries.
- **Random/segmented policies:** depending on implementation and product goals.

There is no universally optimal policy. LRU works well with strong temporal locality; LFU retains long-term popular data but can react slowly to shifting trends. Monitor eviction rates, memory fragmentation, and hit ratios.

## 12. Security and Privacy in Caching

Caching creates additional copies of data. You must answer: what data classification is permitted in the cache? Do cache keys contain tokens or emails? Is data isolated by user/tenant? Do the cache cluster and network have encryption and authentication? Who can inspect the keyspace or export snapshots? Do TTL and purge mechanisms meet retention/deletion policies? Do backups or replicas retain data after source deletion?

Principles:
- Do not arbitrarily cache long-lived credentials or secrets; use a secret manager for secret lifecycles.
- Avoid caching sensitive responses in shared caches without proper authorization and key isolation design.
- Encrypt in transit and at rest as required; enforce access controls and network boundaries.
- Minimize storing full payloads; cache minimal projections where possible.
- Provide purge mechanisms by user/tenant when data deletion is required.
- Do not log cache values; log only normalized key namespaces, TTL, hit/miss, and latency.
- Manage memory dumps, snapshots, backups, and replication as data copies.

Even a private cache requires authorization. Simply residing in an internal subnet does not mean every workload in that subnet should read every key.

## 13. Cache Failure and Resilience

A cache should be designed as a component that can fail. You need to decide how each request type is handled:

- **Fail open:** bypass the cache and read from the source.
- **Fail closed:** reject or degrade functionality when policies or data cannot be guaranteed.
- **Serve stale:** return the last cached copy within limits.
- **Fallback:** use an alternative source or a safe default value.

If the room type catalog cache goes down, the application can fall back to the database with higher latency. If a session/authentication cache holds permission revocation state, bypassing the cache could lead to wrong security decisions; dedicated consistency and failure modes are required.

Failing open is not always the right choice. If every miss floods the database simultaneously, a cache outage can trigger a cascading database outage. Implement concurrency/connection limits to the source, circuit breakers, load shedding, bounded stale serving, gradual warm-up, and tested failovers.

## 14. Key Metrics to Monitor

| Metric | Meaning | Interpretation |
|---|---|---|
| Hit ratio | Percentage of requests served from cache | Track per dataset/endpoint, not just aggregate |
| Miss rate | Requests falling back to source | Miss spikes may indicate flushes, TTLs, or new traffic |
| Hit/miss latency | Service time for each path | Compare p50/p95/p99, including network overhead |
| Eviction rate | Entries removed due to memory/policy | High rates may indicate the working set is too large |
| Memory utilization | Memory consumption | Monitor headroom and fragmentation |
| Key cardinality | Number of distinct keys | Sudden growth lowers hits and raises memory usage |
| Hot key distribution | Load concentration per key | Identify hotspots and shard overloads |
| Backend fallback QPS | Source read requests after miss/failure | Assess actual source offload |
| Stale response rate | Responses serving stale data per policy | Compare against freshness budget |
| Refresh/invalidation failure | Failed cache refreshes or deletions | Risk of prolonged staleness |
| Cache availability | Health/errors/timeouts | Evaluate dependency impact |
| Cost per hit/saved read | Cache cost vs. avoided source reads | Supports keeping or removing the cache |

A high hit ratio is not an isolated goal. If the cache hits 99% but the 1% misses overload the database, or if the cache returns stale data causing overbooking, the design still fails. Business goals are latency, availability, throughput, correctness, and cost at required levels.

## 15. Process for Deciding Whether Data Should Be Cached

A decision process for design reviews:

1. **Identify the source of truth:** Which database, service, or object storage holds the authoritative data?
2. **Measure access patterns:** Read/write ratio, QPS, popularity, working set, key cardinality, and payload size.
3. **Measure the baseline:** Latency p50/p95/p99, source QPS, CPU, IO, API cost, and errors.
4. **Define freshness/consistency:** How stale can data be? Is read-after-write required? Can stale data be served on error?
5. **Estimate benefits:** Potential hit ratio, source offload, latency savings, and avoided cost.
6. **Choose tier and pattern:** Browser/CDN, gateway, in-process, distributed cache; cache-aside, read-through, or write-through.
7. **Design keys and isolation:** Include every dimension that changes the response; prevent cross-user/tenant leaks.
8. **Design TTL/invalidation:** Which source emits update events? If invalidation fails, how is staleness bounded?
9. **Design cache miss/failure handling:** Load control, fallback, stampede protection, warm-up, and recovery.
10. **Experiment with measurement:** Compare with/without cache via controlled A/B or load testing.
11. **Decide to keep or remove:** The cache stays only if measured benefits outweigh costs and risks.

### Quick decision checklist

| Question | If the answer is "no" |
|---|---|
| Is there enough reuse of the same data/key? | Do not cache or find a hotter dataset |
| Is the source slow/expensive enough to justify caching? | Optimize the source first |
| Is there a concrete freshness budget? | Do not cache flows requiring authoritative reads |
| Are keys and authorization safe? | Redesign identity/key isolation |
| Is there a way to update, expire, or invalidate? | Do not deploy cache to production yet |
| Can the source/fallback survive if the cache is lost? | Add load shedding, stale policies, or capacity |
| Do measured benefits exceed operational costs? | Do not cache |

## 16. Well-Architected Review

| Pillar | Review Question | Evidence |
|---|---|---|
| **Operational Excellence** | Who owns TTL, key schemas, invalidation, and cleanup? | Runbooks, config versions, cache dashboards |
| **Security** | Can users/tenants read the wrong data? Does the cache store secrets/PII? | Threat model, IAM review, negative tests |
| **Reliability** | Can a cache outage/stampede take down the source? How long is staleness allowed? | Failure injection, circuit breakers, fallback tests |
| **Performance Efficiency** | Is hit latency better than the miss path? Are there hot keys or evictions? | p95/p99, hit ratio per dataset, load tests |
| **Cost Optimization** | Does the cache save more on the source than cluster/network/ops costs? | Cost model, saved source QPS, memory |
| **Sustainability** | Are oversized copies kept or rarely used data cached? | Working-set analysis, TTL/eviction review |

### Illustrative ADR — Room Catalog Caching

> **Context:** The room catalog endpoint receives high read volume. Database queries take an average of 70 ms; content only changes when admins publish updates.
>
> **Option A:** Keep reading from the database. Fewer components and direct source state, but repeated queries cause load and latency.
>
> **Option B:** Cache-aside in a distributed cache with a short TTL and invalidation on publish.
>
> **Illustrative Decision:** Choose B if load testing proves lower latency/source QPS and an owner is assigned for invalidation.
>
> **Key:** tenant + locale + catalogVersion.
>
> **Freshness:** Accept a staleness window approved by the product owner; publish events invalidate relevant keys.
>
> **Failure behavior:** On cache failure, fall back to the database with concurrency limits; if DB load is high, serve stale catalog within bounds.
>
> **Verification:** Compare p95, hit ratio, database QPS, stale age, invalidation delay, tenant isolation, and cache outages.
>
> **Revisit conditions:** Catalog reads drop, queries are significantly optimized, or cache costs exceed benefits.

## 17. Hands-on Exercise: Selecting Data to Cache for the Booking API

The Booking API exposes these endpoints:
- GET /rooms: room catalog and amenities.
- GET /rooms/{id}: description, images, indicative price, and availability.
- POST /bookings: creates a booking after checking availability and price.
- GET /bookings/{id}/status: booking/payment status.
- GET /reports/popular-rooms: 30-day aggregation query.

The team is considering adding a shared distributed cache and plans to set a 30-minute TTL on all keys to achieve a high hit ratio.

**Requirements:**
1. Classify the data by read/write ratio, reuse, cost, and freshness.
2. Determine which fields should have long caching, short caching, or no caching.
3. Propose cache keys for tenant/locale catalogs and personal data.
4. Explain how to handle admin updates to the catalog.
5. Explain why availability must be re-verified when creating a booking.
6. Design cache failure behavior to avoid overloading the database.
7. Select metrics and measurement targets before/after deployment.
8. Define criteria for removing the cache if benefits are insufficient.

### Solution approach

- Catalogs and descriptions/images have high read reuse and infrequent changes, making them suitable for caching; images/static assets can use a CDN with versioned URLs.
- Indicative prices can have a short cache and must distinguish currency, tenant, and time/segment if those factors affect pricing.
- Availability changes continuously; do not use cached values to confirm reservations. POST booking must perform an authoritative check and execute an atomic reservation/transaction.
- Booking/payment status requires appropriate freshness; if cached solely for UI display, return updatedAt and use a short refresh. Sensitive flows must read the authoritative source.
- Popular room reports have expensive aggregations and batch updates, so they can be cached by query parameters, time window, and tenant.
- Catalog invalidation can emit events after publishing; TTL serves as a safety net if an event is lost. Versioned keys avoid relying on synchronous deletion of every entry.
- On cache failure, apply fallback QPS/concurrency limits, circuit breakers, bounded stale catalogs, and gradual warm-up.
- Compare p95/p99 latency, database QPS/CPU, cache hits per endpoint, stale age, invalidation delay, memory/cost, and error rates.
- Retain the cache only if it meets performance/cost goals without violating freshness/security budgets; if the source is already fast enough, remove the cache to reduce complexity.

### Self-check questions

1. Why is being read-heavy a good sign, yet insufficient on its own to decide on caching?
2. What issues can a high hit ratio conceal?
3. How does TTL differ from invalidation?
4. When should you use an in-process cache, a distributed cache, or a CDN?
5. Why might roomId alone be insufficient as a cache key?
6. How does cache-aside handle cache misses, and what risks arise when many requests miss simultaneously?
7. Why is stale-while-revalidate unsuitable for all data?
8. How can a cache outage trigger a secondary database outage?
9. How do ETag, Cache-Control, and Vary enable HTTP caching?
10. Which measurements prove that caching saves costs and improves user experience?

A sound caching decision begins with **reused data, a source incurring significant cost or latency, and a business-acceptable freshness budget**. Choosing the right keys, cache tiers, TTLs, invalidation, and failure behavior matters more than maximizing hit ratio. A cache should only be kept when measurements demonstrate clear benefits while the system remains accurate, secure, and resilient when copies disappear or go stale.
