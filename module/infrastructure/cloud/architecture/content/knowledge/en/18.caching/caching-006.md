# Cache Penetration, Non-Existent Data, and Negative Caching

Caching reduces database load and shortens response times by temporarily storing frequently accessed results. However, a simple cache-aside system has a weak spot: when a requested key is neither in the cache nor in the data source, the application must still query the database. If the same non-existent key is called repeatedly, the cache does not offload anything. Attackers can deliberately send millions of random keys, or a buggy client can repeatedly request the same wrong ID, overloading the database even while overall cache hit ratio looks healthy.

This phenomenon is commonly called **cache penetration**: requests pass straight through the cache to the data source because the cache holds no usable result. A classic example is **querying non-existent data**. **Negative caching** stores a time-bounded negative result—such as recording "record not found"—so repeated requests do not need to hit the database during that window.

Negative caching is useful, yet must be designed carefully. Caching a false non-existence can hide newly created records for a period; an overly long TTL causes stale negatives, while an overly short TTL fails to reduce load; negative caching without permission checks can leak information or cause cross-tenant mismatches. This lesson explains how to identify, defend against, and operate these scenarios in cloud architectures.

This lesson belongs to the **Caching** chapter of the **CLOUD_ARCHITECTURE** module. It focuses on choosing caching strategies aligned with access behavior, protecting data sources, and balancing latency, reliability, security, scalability, and cost under a Well-Architected mindset.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain cache penetration and distinguish it from normal cache misses, cache breakdowns, and cache stampedes.
2. Analyze how querying random IDs or non-existent data drives up data source load.
3. Design negative caching with safe TTLs, sentinel values, and namespaces.
4. Select TTLs based on data creation likelihood, freshness requirements, and query costs.
5. Combine negative caching with validation, rate limiting, Bloom filters, and resource limits.
6. Avoid risks of cache poisoning, key collisions, tenant leakage, and stale negatives.
7. Observe negative cache hits, avoided source queries, memory usage, hit ratios, and protection effectiveness.
8. Test scenarios involving record creation/deletion, invalidation, concurrency, cache failures, and anomalous traffic.

## 2. Reviewing Cache-Aside and Cache Misses

### 2.1. Basic cache-aside flow

In the cache-aside model, the application actively checks the cache first. If the cache lacks the data, the application queries the data source and then writes the result into the cache:

~~~mermaid
flowchart TD
    R[Request] --> C{Cache has key?}
    C -->|Yes| H[Return cached value]
    C -->|No| DB[Query database]
    DB --> FOUND{Record found?}
    FOUND -->|Yes| SET[Write result to cache]
    SET --> RESP[Return result]
    FOUND -->|No| MISS[Return not found]
~~~

The basic flow typically caches only positive results. When no record is found, the application returns NOT_FOUND without storing that outcome. The next request for the same key queries the database again.

### 2.2. Cache misses are normal

Cache misses happen when a key has never been cached, an entry's TTL expired or was evicted, the cache recently restarted/is cold, a new key appears, or an entry was invalidated after data changed. Misses are not always a problem. The cache is only an optimization layer; the data source remains responsible for answering accurately. Problems arise when miss rates are high, misses hit an expensive source, or miss traffic is uncontrolled.

### 2.3. Cache penetration

Cache penetration happens when requests pass through the cache and hit the data source because the cache lacks a valid entry for the key. A common case is a key corresponding to a non-existent record:

~~~text
Request key: user:999999999
Cache lookup: MISS
Database lookup: NOT FOUND
Application: return 404

Next request for the same key:
Cache lookup: MISS
Database lookup: NOT FOUND
Application: return 404
...
~~~

If the same key is queried tens of thousands of times, the database absorbs unnecessary queries. If the key changes randomly on every request, a positive-only cache has virtually no chance to reuse results.

### 2.4. Consequences

- Database CPU, connections, IOPS, and query throughput rise.
- p95/p99 latency climbs due to connection and query queuing.
- Legitimate requests slow down or fail through cascading effects.
- Database or compute autoscaling triggers sudden cost spikes.
- Aggregate cache hit ratio may still look high if most normal traffic hits, causing overall dashboards to mask a harmful query stream.
- Under overload, client/gateway retries can amplify traffic and prolong the incident.

## 3. Distinguishing Penetration, Breakdown, and Stampede

Three phenomena can all cause heavy load on the data source, yet stem from different causes:

| Phenomenon | Primary Cause | Traffic Pattern | Typical Mitigations |
|---|---|---|---|
| **Cache penetration** | Cache has no entry for the key; typically due to non-existent data or arbitrary keys | Many non-existent keys, or repeated missing keys | Negative caching, validation, Bloom filters, rate limits |
| **Cache breakdown** | A single hot entry expires or is lost while huge numbers of requests need it | One popular key suddenly misses | Single-flight/locks, refresh-ahead, TTL jitter |
| **Cache stampede** | Many keys expire or cache loses data together, causing concurrent source queries | A simultaneous wave of misses | Jitter, warming, request coalescing, stale-while-revalidate |

For example, someone guessing a million random non-existent customer IDs is penetration; a homepage's hottest key just expiring TTL is breakdown; a cache cluster restart wiping millions of keys is a stampede/cold-cache surge.

Solutions can overlap, but you must identify the root cause first. Negative caching does not solve an ultra-hot positive key expiring; a distributed lock does not stop an attacker generating unbounded negative keys.

## 4. Sources of Requests for Non-Existent Data

### 4.1. Random or guessable IDs

Endpoints like GET /users/{id}, /orders/{id}, or /products/{slug} can be called with sequential guessed IDs, random UUIDs, overly long strings or invalid characters, IDs belonging to another tenant, or deleted/expired identifiers. If the application does only cursory syntax checks and queries the DB for every input, the data source becomes the final filter. That wastes resources and opens a DoS surface.

### 4.2. Buggy clients or external integrations

A client may repeat invalid requests due to client-side cache bugs, retry bugs, stale bookmarks, or bad mapping data. A partner may send non-existent reference codes due to sync lag. Not all penetration is malicious; observability must distinguish valid clients, integration bugs, and hostile traffic.

### 4.3. Deleted data or lifecycle changes

A key that previously returned a positive record can become NOT_FOUND after deletion. If the positive cache is invalidated without creating a negative entry, repeated requests can hit the DB. Conversely, an old negative entry might linger after a record is recreated.

### 4.4. Tenants and authorization

An ID missing in tenant A may exist in tenant B. An unauthorized request is not necessarily equivalent to "does not exist" from a business perspective. If a negative cache keys only by ID without tenant or authorization scope, it can return wrong results across tenants.

Design must distinguish: no record in the system of record, record exists but caller lacks permission, record belongs to another tenant, and record is soft-deleted or in a hidden state. Do not store sensitive authorization outcomes in shared caches unless cache keys and policies preserve security boundaries.

## 5. What Is Negative Caching?

### 5.1. Storing negative results

Negative caching records that a lookup was performed and yielded "not found" or a defined negative outcome. When a similar request arrives within the validity window, the application returns the negative result from cache without querying the source again.

~~~mermaid
flowchart TD
    R[Request] --> C{Cache lookup}
    C -->|Positive entry| P[Return data]
    C -->|Negative entry| N[Return NOT_FOUND]
    C -->|No entry| DB[Query source]
    DB --> FOUND{Exists?}
    FOUND -->|Yes| POS[Cache positive result]
    POS --> DATA[Return data]
    FOUND -->|No| NEG[Cache negative sentinel with TTL]
    NEG --> MISS[Return NOT_FOUND]
~~~

### 5.2. Sentinel values

The cache must distinguish three states: key absent (miss), key holds positive data, and key confirms lookup found no record (negative hit). Avoid ambiguous null values if the client library or cache backend cannot tell null apart from a key miss. Use a dedicated sentinel:

~~~json
{
  "_cacheState": "NOT_FOUND",
  "version": 1
}
~~~

Or a distinct encoded marker such as __NEGATIVE__. The sentinel must live in a namespace and encoding that cannot collide with valid data. If real data could ever contain the sentinel string itself, use a strongly typed envelope.

### 5.3. Cache-aside pseudocode with negative caching

~~~text
function getUser(tenantId, userId):
    key = "user:" + tenantId + ":" + userId
    cached = cache.get(key)

    if cached == POSITIVE:
        return cached.value

    if cached == NEGATIVE_SENTINEL:
        return NOT_FOUND

    user = database.findUser(tenantId, userId)

    if user exists:
        cache.set(key, POSITIVE(user), positiveTTL)
        return user

    cache.set(key, NEGATIVE_SENTINEL, negativeTTL)
    return NOT_FOUND
~~~

This is pseudocode. Real implementations must handle timeouts, cache connection failures, DB errors, serialization, tenant authorization, TTLs, and concurrency. If the cache fails, fallback policies must cap source load rather than letting every request bypass the cache and flood the database.

## 6. Choosing TTL for Negative Entries

### 6.1. Short or long TTL?

| TTL | Benefits | Risks |
|---|---|---|
| Too short | New data becomes visible quickly | Repeated requests still hit the DB frequently |
| Moderate | Cuts repeated queries, limits stale negatives | Must be tuned to business lifecycle |
| Too long | Strongly reduces source load for repeated bad keys | Newly created records may stay hidden for too long |

No default TTL fits every system. An order lookup API may use a short negative TTL because new orders are created continuously. A lookup for nearly static country/config codes can use a longer TTL.

### 6.2. Choosing by likelihood of data creation

Ask: can a non-existent ID be created within the next seconds or minutes? Do clients automatically retry NOT_FOUND requests? Does any creation flow know the ID in advance and invalidate immediately? Is read-after-create required? Can data be imported or synced asynchronously?

The longer the TTL, the more you need proactive invalidation when records are created or restored. Without reliable invalidation, keep TTLs short to bound stale negative windows.

### 6.3. TTL by data category

| Lookup Type | Characteristics | Candidate Policy |
|---|---|---|
| Frequently created customer/booking IDs | May transition from absent to present soon | Short negative TTL, invalidate on creation |
| Rarely changing product slugs | Created/deleted infrequently | Medium negative TTL, purge on publish |
| Fixed config codes | Small, nearly static value set | Longer TTL if versioned/invalidated |
| External partner ID lookups | Results may change with syncs | TTL aligned with sync SLA, backoff retries |
| Malformed random IDs | Identifiable as invalid before DB | Reject in validation; skip DB negative cache |

### 6.4. Jitter to avoid synchronized expirations

If many negative entries are created simultaneously with identical TTLs, they can expire all at once. Add jitter:

~~~text
effectiveTTL = baseTTL * random(0.8, 1.2)
~~~

Jitter spreads out expiration times but does not replace TTL policy. Bound the jitter range so it never violates freshness requirements or data policies.

## 7. Invalidation When Data Is Created, Updated, or Deleted

### 7.1. Stale negatives after creation

Example: a request looks up user 10042, the database returns NOT_FOUND, and the application caches a sentinel with a 5-minute TTL; another process creates user 10042 successfully; subsequent read requests still hit the negative cache and return NOT_FOUND. This is a **stale negative**. It degrades consistency and may cause clients to resubmit creation requests or assume the account does not exist.

### 7.2. Deleting the negative key on record creation

After the creation transaction commits, the service can delete the corresponding negative entry:

~~~text
BEGIN DATABASE TRANSACTION
    INSERT user(...)
COMMIT

cache.delete("user:{tenantId}:{userId}")
~~~

Deleting after commit avoids populating positive cache entries for transactions that might roll back. However, a race remains:

- Request A reads the DB and does not see the user yet.
- Request B creates the user and deletes the cache key.
- Request A writes the negative cache entry after B deleted it.

As a result, a stale negative reappears. Mitigate this with versions/fencing tokens, post-commit positive write-through, cache generations, version checks before writing negatives, or ordered sync/invalidation pipelines. Match complexity to read-after-create requirements.

### 7.3. Version-aware caching

If the system maintains monotonically increasing versions per entity or namespace, the cache can store the version and accept writes only if they are no older than the current generation. Implementation depends on the backend and operation atomicity.

~~~text
cache key: user:{tenantId}:{userId}
cache value: {state: NOT_FOUND, generation: 12}

After create:
generation(user) = 13
negative entry generation 12 is no longer valid
~~~

Do not assume cache get-then-set is atomic. If you need compare-and-set, scripts, or cache transactions, verify the exact capabilities of your backend.

### 7.4. Deleting records and positive caches

When deleting a record, invalidate the positive entry; you may immediately write a negative entry after confirming deletion if read paths need protection from repeated queries. For soft deletes, negative semantics must be consistent: NOT_FOUND, GONE, DELETED, or hidden by permissions. Some clients distinguish 404 from 410; the cache must preserve exact business outcomes.

## 8. Defense in Depth

Negative caching only stops repeats for keys already queried. An attack rotating through keys continuously still creates unbounded negative entries and forces one source query per key. Combine multiple defenses:

### 8.1. Validate before querying

- Check ID format, length, and character set.
- Reject empty, oversized, or malformed values.
- Enforce bounds on page size, filters, and query complexity.
- Canonicalize identifiers consistently before constructing cache keys.

Validation does not tell whether an ID exists, but it blocks definitely invalid inputs without touching the data source.

### 8.2. Rate limiting

Limit requests by IP, user, API key, tenant, or endpoint. Use token bucket or leaky bucket algorithms to control bursts and sustained rates. Avoid rate-limiting solely by IP since legitimate clients may share NATs; conversely, user-based limits must account for unauthenticated traffic.

Rate limiting cuts total traffic but does not replace authorization or validation. Return appropriate responses (such as 429), backoff guidance, and metrics so clients do not retry relentlessly.

### 8.3. Bloom filters

A Bloom filter is a probabilistic structure testing whether an element might belong to a dataset or is definitely not in it:

- If the Bloom filter says **definitely not present**, the application skips the database lookup.
- If it says **possibly present**, the application checks the cache or data source.

Bloom filters can produce false positives (saying a key might exist when it does not), but properly designed filters produce no false negatives if built/updated accurately and uncorrupted. Since a false positive only causes an extra lookup, it is usually safer than a false negative that hides a real record.

~~~mermaid
flowchart TD
    R[Lookup request] --> BF{Bloom filter}
    BF -->|Definitely absent| NF[Return NOT_FOUND]
    BF -->|Possibly present| CACHE[Check cache]
    CACHE -->|Hit| RET[Return cached result]
    CACHE -->|Miss| DB[Query database]
    DB --> RESULT[Return actual result]
~~~

Bloom filters suit cases where the ID set can be loaded/maintained efficiently and non-existent key traffic is huge. Manage filter updates on record creation; snapshots/rebuilds after restarts; false-positive rates and memory; deletion semantics (possibly requiring counting Bloom filters or rebuilds); and filter consistency with the database.

If a Bloom filter is stale and skips a newly created ID, it creates a system-level false negative even though the algorithm itself has no false negatives over its built input set. Therefore, use synchronous updates, safe dual-writes, generations, or read-after-create fallbacks.

### 8.4. Allowlists or valid namespaces

For small, finite key sets (such as config type codes), validate against an allowlist or cached valid catalog. This beats querying the database for arbitrary strings.

### 8.5. Query budgets and circuit breakers

Set concurrency caps, query timeouts, and request budgets toward the source. When the database slows down or overloads, a circuit breaker pauses non-essential requests and returns fallbacks or controlled errors. Never turn a cache issue into an unbounded flood of DB queries.

## 9. Negative Caching and HTTP/API Semantics

### 9.1. Do not cache every error as NOT_FOUND

| Outcome | Meaning | Safe to Negative-Cache? |
|---|---|---|
| 404 / NOT_FOUND | Resource absent in lookup scope | Yes, if semantics are stable and TTL is appropriate |
| 410 / GONE | Resource permanently or policy-removed | Possible, if clearly defined |
| 401 / UNAUTHENTICATED | Caller not authenticated | Usually do not cache as resource absence |
| 403 / FORBIDDEN | Caller not permitted | Cache only within safe identity/policy scope if deliberate |
| 429 / RATE_LIMITED | Request exceeded limits | Never treat as non-existent data |
| 500/502/503 | System or dependency error | Never negative-cache as NOT_FOUND |
| Timeout | Unknown whether source holds data | Never convert into NOT_FOUND |

If a database times out and the application writes a NOT_FOUND sentinel, existing data gets masked. Cache negative entries only on deterministic absence outcomes.

### 9.2. Cache keys must include security scope

When outcomes depend on tenant or user permissions, cache keys must capture the exact scope:

~~~text
resource:{tenantId}:{resourceId}
~~~

If results also depend on roles or authorization policies, include a permission version or separate data caching from authorization. Never use a single global negative cache key for resources whose semantics differ across tenants.

### 9.3. HTTP caching and Cache-Control

HTTP 404/410 responses can sometimes be cached per HTTP semantics and headers/config. However, negative caching at CDNs/reverse proxies requires care:

- CDNs may key caches by URL, query string, and selected headers.
- Authorization/cookies must not be ignored if responses depend on identity.
- CDN TTLs may differ from application cache TTLs.
- Purges/invalidations must run when resources are newly created.
- Never let one tenant/user's cached 404 be served to another caller.

Do not assume every CDN caches 404s identically by default; inspect actual policies and configurations.

## 10. Cache Keys, Namespaces, and Preventing Cache Poisoning

### 10.1. Key canonicalization

Keys must be constructed from validated and normalized identifiers. If one layer is case-insensitive while another is case-sensitive, the cache may hold duplicate variants or return wrong data.

Factors to include in keys: tenant or data partition, resource type, canonicalized identifier, locale/version if output depends on them, and permission scope/version if caching authorized results.

### 10.2. Never let clients write sentinels

Clients must never be able to submit payloads that write negative sentinels directly into the cache. Only authoritative server-side code may create negative entries after querying the source and confirming absence.

If cache keys are fully user-controlled, attackers can generate huge volumes of unique keys and cause memory exhaustion. Countermeasures include validation, per-tenant cardinality limits, quotas, eviction policies, and rate limits.

### 10.3. Separate namespaces for positive/negative

~~~text
cache:v1:positive:user:{tenantId}:{userId}
cache:v1:negative:user:{tenantId}:{userId}
~~~

Separate keys enable distinct TTLs and metrics, though invalidation must delete both. A single key holding a state envelope is simpler, provided parsers recognize each state accurately.

### 10.4. Avoid leaking data existence

An endpoint may deliberately return the same response for "not found" and "unauthorized" to prevent enumeration. Negative caching must preserve that semantics; internal metrics/logs can classify more finely, provided access is controlled and PII is omitted.

## 11. Stampedes on Negative Entries

Negative caching suppresses repeated queries during the TTL, yet when a negative key expires, concurrent requests can still hit the database together. This is a breakdown/stampede on negative keys.

### 11.1. Request coalescing / single-flight

Multiple concurrent lookups for the same key can collapse into one source query. One request performs the lookup; remaining requests wait for the shared result. Single-flight can be in-process or backed by distributed coordination as needed.

### 11.2. TTL jitter

Stagger expirations to prevent many negative keys from missing simultaneously after a scan or batch.

### 11.3. Bounded refresh or recheck

For data that can be newly created, some systems run background rechecks or stale-while-revalidate. However, never serve stale negatives indefinitely when clients require read-after-create. Rechecks must be rate-limited and bounded by deadlines.

### 11.4. Locks are not the only solution

Distributed locks reduce duplicate lookups, but introduce complexity around leases, fencing tokens, lock timeouts, and failures. For non-existent keys with short TTLs, in-process request coalescing plus negative caching often suffices; for large distributed workloads, weigh coordination costs carefully.

## 12. Cache Sizing and Eviction

### 12.1. Negative entries can consume significant memory

If every request targets a different non-existent key, the cache can fill up with negative entries that are rarely read again. Valuable entries get evicted, memory and cache costs rise, serialization/index overhead outweighs payloads, overall hit ratio drops, and attackers can turn the cache into a garbage dump.

### 12.2. Bounding negative caches

- Use shorter negative TTLs than positive TTLs.
- Cap capacity/namespaces or the share of negative entries.
- Evict using LRU/LFU or backend-appropriate policies.
- Cache only lookups likely to repeat.
- Do not cache invalid IDs already rejected by validation.
- Rate-limit new keys per caller/tenant.
- Track negative key counts and reuse rates before increasing TTLs.

### 12.3. Admission policies

Instead of caching every negative result immediately, cache only after a key is queried repeatedly, or use TinyLFU/admission policies depending on the cache engine. This keeps one-off keys from entering the cache and evicting valuable entries.

A simple policy: on first encounter of a missing key, return NOT_FOUND and increment a lightweight counter; if the key repeats within a short window, create the negative entry; enforce TTLs and namespace quotas. Ensure the counter/admission store does not become a new bottleneck. Use sampling or local frequency sketches if exact counts are unnecessary.

## 13. Observability and Measuring Effectiveness

### 13.1. Recommended metrics

| Metric | Meaning | Operational Question |
|---|---|---|
| Positive cache hits | Requests served positive data from cache | How effectively is the cache accelerating normal reads? |
| Negative cache hits | Requests served NOT_FOUND from cache | How many source queries are being avoided? |
| Cache misses | No entry present | Are misses rising due to new keys, evictions, or TTLs? |
| Negative write rate | Creation rate of negative entries | Is there scanning or anomalous traffic? |
| Negative entry count/memory | Count and memory footprint of negative keys | Is there a risk of cache pollution? |
| Negative reuse ratio | Share of negative entries hit again | Is negative caching worth keeping? |
| DB not-found query rate | Source queries returning non-existent | How much penetration still reaches the DB? |
| Invalid key reject rate | Inputs rejected prior to lookup | Are buggy clients or enumeration attempts rising? |
| TTL expiry/recreation | Negative entries expiring and recreated | Is the TTL too short or repeat traffic abnormal? |
| Freshness/read-after-create errors | New records masked by negatives | Are there invalidation races or overly long TTLs? |

### 13.2. Slice metrics by scope

Break down by endpoint, tenant, caller type, region, and result class. Never put userId/resourceId into metric labels if it causes high cardinality; use access-controlled structured logs or traces for investigation.

### 13.3. Measuring real impact

~~~text
Before:
Not-found requests = 10,000 requests/min
DB not-found queries = 10,000 queries/min

After:
Not-found requests = 10,000 requests/min
Negative cache hits = 8,500 requests/min
DB not-found queries = 1,500 queries/min

Estimated DB queries avoided = 8,500/min
~~~

These numbers are illustrative. Compare over equivalent load windows and separate valid requests, random keys, validation failures, and callers. If DB queries drop while cache memory/evictions spike too sharply, the policy is not yet optimal.

### 13.4. Alerts

Alert when DB not-found queries spike; negative write rates exceed baseline; negative entries consume excessive memory share; one tenant/caller generates excessive new keys; cache errors drive heavy DB fallbacks; read-after-create misses/false-not-founds breach thresholds; or negative hit ratio is too low relative to consumed memory.

Base thresholds on baselines and SLOs; never apply one fixed number across all workloads.

## 14. Implementation Example for a Booking Lookup API

Suppose an application exposes an endpoint to look up bookings by tenant and booking ID. IDs must match a defined format; bookings may be created right after a client submits a request.

### 14.1. Proposed flow

~~~mermaid
flowchart TD
    REQ[GET booking] --> AUTH[Authenticate caller]
    AUTH --> VALID{Validate ID and tenant}
    VALID -->|Invalid| REJECT[Reject without DB lookup]
    VALID -->|Valid| CACHE{Check scoped cache}
    CACHE -->|Positive| RETURN[Return booking]
    CACHE -->|Negative| NF[Return not found]
    CACHE -->|Miss| DB[Query Booking DB]
    DB --> FOUND{Found and authorized?}
    FOUND -->|Yes| POS[Write positive entry]
    POS --> RETURN
    FOUND -->|No record| NEG[Write negative sentinel with short TTL]
    NEG --> NF
    FOUND -->|DB error/timeout| ERR[Return controlled error; do not cache NOT_FOUND]
~~~

### 14.2. Sample policy

| Component | Illustrative Policy | Rationale |
|---|---|---|
| ID validation | Defined UUID/format | Rejects clearly invalid inputs |
| Cache key | Version + tenantId + bookingId | Isolates tenant scope and supports schema evolution |
| Positive TTL | 60–180 seconds depending on fields | Optimizes frequent reads |
| Negative TTL | 5–15 seconds | Curbs repeated DB queries while bounding stale negatives |
| Cache miss | Query DB with timeout | Authoritative source decides existence |
| DB NOT_FOUND | Write negative sentinel | Reuses negative outcomes |
| DB timeout/5xx | Do not write negative | Avoids turning source errors into absence |
| Create booking | Commit then write-through/invalidate cache | Shrinks stale negative window |
| Caller rate limit | By identity/tenant/endpoint | Limits enumeration and bursts |
| Observability | Negative hits, DB not-found, key cardinality | Measures efficiency and detects abuse |

Durations are examples for discussion only; validate against business requirements. If clients must see a booking immediately upon creation, the creation endpoint can return the result from the transaction or read directly from the system of record instead of relying on the cache.

### 14.3. Race condition during create and lookup

~~~mermaid
sequenceDiagram
    participant R as Reader
    participant DB as Booking DB
    participant C as Cache
    participant W as Writer
    R->>C: GET key
    C-->>R: MISS
    R->>DB: SELECT booking
    DB-->>R: NOT FOUND
    W->>DB: INSERT booking
    DB-->>W: COMMIT
    W->>C: DELETE negative key
    R->>C: SET negative key
    Note over R,C: Stale negative created after invalidation
~~~

Mitigation options by requirement: write positive cache on create and use generations/versions to block older negative writes; route cache updates/invalidations through an ordered pipeline; skip negative caching for newly created resources or transitional state windows; read directly from the authoritative source on paths requiring read-your-writes; keep negative TTLs short to limit residual error windows.

No single cache delete operation solves every reader/writer race. Define explicit consistency contracts per endpoint.

## 15. Testing

### 15.1. Functional tests

- Existing key: returns positive data and writes positive cache.
- Non-existent key: returns NOT_FOUND and writes negative sentinel.
- Repeated request for same key: negative hit, no repeat DB query.
- DB timeout: no negative entry written.
- Malformed ID: rejected before DB.
- Two tenants using the same ID: cache scopes never cross.
- Creating record after negative: invalidation/write-through exposes the record within SLO.
- Deleting record: positive entry invalidated and negative semantics accurate.

### 15.2. Concurrency/race tests

- Multiple readers concurrently querying one missing key.
- Creation occurring between DB lookup and negative cache write.
- Negative TTL expiring during a request burst.
- Cache restart/flush wiping all negative entries.
- Two writers creating the same ID or retrying after timeout.

### 15.3. Load and security tests

- High volume of random non-existent keys.
- One hot negative key hammered at high rate.
- One tenant generating new keys at an anomalous rate.
- Very long or malformed keys.
- Cross-tenant and cross-permission-scope probes.
- Cache errors or slowness under rising traffic.

Evaluate DB QPS, connections, p95/p99, negative memory, evictions, cache CPU, and false-not-founds after creation. Do not merely verify that the app returns 404 properly.

## 16. Common Mistakes

| Mistake | Consequence | Improvement |
|---|---|---|
| Never caching NOT_FOUND | Same negative key repeatedly queries the DB | Negative cache with TTL |
| Caching every error as NOT_FOUND | DB timeouts or 500s get treated as non-existent data | Cache only deterministic absence |
| Negative TTL too long | New records are hidden | Lifecycle-aligned TTL and invalidation |
| Negative TTL too short | Repeated queries still flood the DB | Measure reuse and pick suitable TTL |
| Using ambiguous null | Cannot distinguish misses from negative hits | Explicitly typed sentinels/envelopes |
| Cache keys missing tenant | Cross-tenant leaks or wrong results | Include tenant/scope in keys |
| Trusting cache delete to fix all races | Old readers can write negatives after invalidation | Versioning/fencing/read-your-writes |
| Caching every random key | Cache pollution and memory exhaustion | Validation, admission policies, quotas |
| Relying solely on negative caching against DoS | Continuous new keys still hit DB once each | Rate limiting, Bloom filters, query budgets |
| Unupdated Bloom filter | System-level false negatives after creation | Sync/generations/rebuilds/fallbacks |
| Not observing negative entries | Blind to cache efficiency or scanning | Metrics for hits/reuse/cardinality/DB not-found |
| Not testing cache failures | Cache down causes requests to flood the DB | Circuit breakers, concurrency caps, fallback controls |

## 17. Well-Architected Review

| Pillar | Question | Measures and Trade-offs |
|---|---|---|
| **Operational Excellence** | How do we know negative caching reduces load and which keys are anomalous? | Metrics, dashboards, alerts, runbooks, and TTL reviews; more policies to manage |
| **Security** | Who can create keys, read negative outcomes, and access other tenants? | Validation, scoped keys, IAM, rate limits, and anti-enumeration |
| **Reliability** | How are DB timeouts, cache outages, create races, and failed invalidations handled? | Never cache ambiguous errors, bounded TTLs, versioning, controlled fallbacks |
| **Performance Efficiency** | How many DB queries does negative caching save and how much memory does it cost? | TTL/admission tuning, Bloom filters for suitable sets, measuring p95/p99 |
| **Cost Optimization** | Are countless one-off negative keys being stored? | Admission policies, quotas, short TTLs, and eviction |
| **Sustainability** | Are there repeated queries, oversized payloads, or un-reused cache entries? | Early validation, compact keys, cutting wasteful requests, and sensible retention |

Negative caching eliminates duplicate work, yet does not remove the need to protect the data source. A healthy cache layer must behave properly across hits, misses, timeouts, and disconnects.

## 18. Practice Exercises

### Exercise A — Calculating query reduction

An endpoint receives 12,000 requests/minute for non-existent IDs. Of these, 75% repeat keys already queried within the negative TTL.

**Question:** Estimate remaining database queries if negative caching is active and hits 75% of repeated requests?

**Hint:** If 75% represents the share of requests served from negative hits, the DB receives roughly 25% = 3,000 queries/minute. Measure actual key distributions and reuse; key repetition rate does not automatically equal hit ratio.

### Exercise B — Choosing a TTL

A booking lookup system may create a new booking immediately after the first request. The team plans to cache NOT_FOUND for 30 minutes.

**Question:** What risks arise and what alternatives should be considered?

**Hint:** Stale negatives can hide new bookings for up to 30 minutes. Reduce the TTL, invalidate/write-through on create, use versioning/generations, and read from the authoritative source for read-your-writes.

### Exercise C — Error classification

The database returns a timeout. Current code caches NOT_FOUND for 10 minutes to reduce retries.

**Question:** Why is this a design flaw?

**Hint:** A timeout does not prove a record does not exist. Only negative-cache deterministic absence results; timeouts should trigger retry/backoff or controlled errors.

### Exercise D — Random key attack

An attacker sends a different UUID on every request. Negative TTL is 10 minutes, yet virtually no key is ever queried twice.

**Question:** Why is negative caching insufficient? What other layers are needed?

**Hint:** Each key still causes one DB lookup and one cache entry; add format validation, rate limits, Bloom filters if a bounded ID set exists, admission policies, per-tenant quotas, and query budgets.

### Exercise E — Tenant leakage

Tenant A requests non-existent resource ID 42, caching NOT_FOUND at key resource:42. Tenant B owns resource ID 42, yet its request receives NOT_FOUND.

**Question:** What is the cause and how do you fix it?

**Hint:** The cache key lacked tenant scope. Use resource:{tenantId}:{resourceId}, validate tenant from server-side identity, and test authorization separately.

### Exercise F — Invalidation race

A reader queries the DB and gets NOT_FOUND, a writer inserts the record and deletes the cache key, and then the reader writes the negative sentinel.

**Question:** Why is deleting the cache after creation not enough?

**Hint:** The reader held stale results and wrote after invalidation. Use versioning/fencing, positive write-through, atomic primitives, read-your-writes, or short negative TTLs to bound risk.

## 19. Pre-Production Checklist for Negative Caching

- [ ] Endpoints and workloads with repeated non-existent data queries are identified.
- [ ] Validation rejects malformed inputs before hitting the database.
- [ ] Only deterministic NOT_FOUND/absence is cached; timeouts and system errors never become negatives.
- [ ] Sentinels clearly distinguish cache misses, positive hits, and negative hits.
- [ ] Cache keys include required tenant/resource/permission scopes.
- [ ] Positive and negative TTLs are chosen based on freshness, creation likelihood, and reuse.
- [ ] Create/delete flows include appropriate invalidation or write-through.
- [ ] Races between lookups and creates are analyzed; versioning/fencing/read-your-writes are added where needed.
- [ ] Negative entries have memory limits, TTLs, quotas, and admission/eviction policies.
- [ ] Rate limits, query budgets, and circuit breakers protect the database under anomalous traffic.
- [ ] Bloom filters are used only with clear sync, rebuild, and deletion procedures.
- [ ] Cache failures do not cause all requests to bypass the cache and flood the database.
- [ ] Metrics track negative hits/reuse, DB not-found QPS, key cardinality, evictions, and stale negatives.
- [ ] Alerts by tenant/caller and runbooks exist for penetration spikes.
- [ ] Functional, concurrency, race, load, and security tests have been executed.
- [ ] Freshness SLOs, tenant isolation, retention, and cache costs have been reviewed.

**Core takeaway:** cache penetration happens when requests continuously pass through the cache to the data source, typically due to non-existent or uncached keys. Negative caching remembers negative results temporarily to prevent repeated queries, provided TTLs are bounded, NOT_FOUND is separated from errors, tenant scopes are preserved, and creation races are handled. Combining validation, rate limiting, Bloom filters/admission policies, and observability protects the database effectively without turning the cache into a garbage dump or a source of stale data.
