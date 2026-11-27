# Synchronizing Multi-Tier Caches: Browser, CDN, Application, and Data

## 1. Why Must Multiple Cache Tiers Be Designed Together?

A cloud system typically has multiple cache tiers: browsers retain responses or static assets; CDNs store content close to users; reverse proxies/API gateways can cache responses; applications store results in local memory or distributed caches; and databases keep page buffers/caches and materialized views. Each tier reduces a different kind of cost, yet also introduces another copy of the data that can go stale.

If TTLs are configured in isolation, systems easily run into confusing behaviors: the CDN has purged while browsers still hold old responses; the application cache has updated while the CDN keeps serving the previous version; the database committed successfully while caches were never invalidated; or one tenant sees another tenant's data because a cache key omitted access scope.

**Multi-tier cache synchronization** is the practice of designing how data is created, stored, validated, refreshed, and invalidated across all tiers. The goal is not necessarily for every tier to swap data in the exact same millisecond. The goal is to define **allowed freshness, behavior when data is stale, update ordering, security boundaries, and recovery mechanisms** for each data type.

In the **CLOUD_ARCHITECTURE** module, this is a cross-cutting decision connecting networking, compute, storage, and deployment models; it must balance **performance, reliability, security, scalability, cost, and operations** under a Well-Architected mindset.

Running example: a booking platform has room search pages, property images, descriptions, pricing, room availability, account profiles, and booking history. Images rarely change, descriptions change daily, prices and room availability change continuously, and booking history is private data requiring authorization checks before returning.

## 2. The Cache Tier Landscape

~~~mermaid
flowchart TB
    B["Browser / Mobile client cache"]
    E["CDN / Edge cache"]
    P["Reverse proxy / API gateway cache"]
    A["Application cache"]
    D["Database buffer / query cache / materialized data"]
    S[("Authoritative source of truth")]
    B -->|"MISS / revalidate"| E
    E -->|"MISS / revalidate"| P
    P -->|"MISS"| A
    A -->|"MISS"| D
    D -->|"read"| S
    S -. "write event / invalidation" .-> A
    S -. "purge / version update" .-> E
    S -. "new representation / validator" .-> B
~~~

The diagram is a logical model. A request may bypass certain tiers—for instance, APIs not cached at the CDN or applications reading directly from the database; browser and CDN caches generally apply to HTTP responses, while application caches can store objects or query results. Crucially, every tier must have an explicit **cache contract** for the data it holds.

| Tier | Typically Cached Items | Primary Benefit | Primary Risks |
| --- | --- | --- | --- |
| Browser | HTML, CSS, JS, images, permitted API responses | Cuts round trips and downloads; fast UX | Clients retain stale or sensitive data too long |
| CDN/Edge | Static assets, public responses, cache-keyed content | Reduces latency and origin load at scale | Wrong cache keys, slow purges, accidentally caching private content |
| Reverse proxy/API gateway | Permitted API responses or fragments | Offloads backend, centralizes policies | Misconfigured headers/authorization/cookies |
| Application cache | Objects, public profiles, computed results, sessions depending on model | Avoids repeated queries or computations | Invalidation, stampedes, distributed state |
| Data/database cache | Buffer pages, query results, materialized views, nearby read replicas | Boosts read throughput or cuts I/O | Mistaking DB caches for durable stores; freshness/replication lag |

**Database buffer caches** are usually managed automatically by the database engine to keep data/index pages in memory. Applications should not arbitrarily treat them as API-purgeable caches. Materialized views or read models are derived data requiring their own refresh mechanisms.

## 3. Start with a Freshness Contract per Data Type

Not every piece of data requires the same consistency level. A 10-minute TTL may work well for property images, yet be completely unsuitable for room availability right before confirming a booking.

| Data Type | Change Characteristics | Reference Policy | Final Verification Source |
| --- | --- | --- | --- |
| Content-hashed CSS/JS | Changes only on build | Long-term cache, immutable | Build artifact/version |
| Public property images | Changes rarely, needs fast delivery | Long TTL, purge/version on update | Media metadata/origin |
| Descriptions and amenities | Changes via content management | Shorter TTL, event purge on edit | Property Service |
| Search results | Depends on data and filters | Short TTL or query-keyed cache | Search projection; verify booking at authoritative source |
| Pricing | Can change frequently | Very short cache or indicative display only | Pricing Service |
| Room availability | Changes with transactions | Do not use cache to confirm holds/bookings | Inventory/Booking Service |
| Personal profiles | User-specific data | Private cache with suitable policy or no-store | Identity/Profile Service |
| Payment/booking status | Sensitive and transactional | Typically avoid shared cache; verify permissions and state | Payment/Booking database |

### 3.1. Defining freshness by time and conditions

A freshness contract should specify the freshness target, maximum stale age, consistency requirements, invalidation triggers, fallbacks, and scope. For example: p95 time from source commit until new content is served must be under 30 seconds; maximum tolerated stale data is 2 minutes; if invalidation fails, only public descriptive content may be served stale.

TTL is merely a storage time limit or a configured refresh signal. TTL does not guarantee every tier expires at the same instant, nor does it guarantee all changes appear within the exact TTL when stale-while-revalidate, replication delays, or invalidation failures occur.

## 4. Cache Keys: Prerequisite for Correct and Safe Caching

Cache keys determine whether two requests are treated as the same shareable content. **Omitting a response-affecting dimension causes semantic cache collisions or data leaks.** Adding too many dimensions fragments the cache and lowers hit ratios.

| Dimension | When to Include in Key |
| --- | --- |
| HTTP method | Cache only supported methods and semantics; GET/HEAD differ from POST |
| Host/route/path | Responses differ by hostname or endpoint |
| Query parameters | Filters, sort, page, locale, or API version alter content |
| Content negotiation | Accept, Accept-Encoding, or output format |
| Locale/language | Content translated by language |
| Tenant | Responses genuinely vary by tenant and cache is shared across tenants |
| Identity/role | Only with a safe private-cache strategy; generally avoid shared caches for personal content |
| Cookies/headers | Only cookies/headers that genuinely alter the response; avoid overly broad Vary |
| Version | Schema, API version, or content version alters representation |

Example logical cache key for a public search page:

~~~text
search:v3:locale=vi:city=city-hcm:checkin=2026-12-18:
checkout=2026-12-21:guests=2:sort=price:page=1
~~~

Never put raw access tokens, session cookies, emails, or personal data in keys. If separation by user/tenant is required, use verified opaque identifiers while bounding TTLs and cache access permissions.

### 4.1. Query normalization

Two business-equivalent requests can generate different keys if query parameters are not normalized—for example, parameter ordering, letter casing, default values, or whitespace. Define default parameters, ordering and query encoding, multi-value handling, locale/currency/timezone defaults, and tracking parameters that can be stripped. Never strip a parameter merely assuming it is unimportant; prove that the response does not change with that parameter.

## 5. Synchronizing Browser Caches and HTTP Semantics

Browser caches generally follow HTTP caching semantics. Servers provide response headers; browsers/proxies evaluate whether stored copies can be reused, must be revalidated, or must be fetched fresh.

### 5.1. Cache-Control

| Directive | General Meaning | Use When |
| --- | --- | --- |
| max-age=3600 | Fresh for 3,600 seconds per cache policy | Content may be stored for a defined duration |
| public | Response may be stored by shared caches if other conditions permit | Public content |
| private | Intended for private caches only, not shared caches per HTTP semantics | Personal content that browsers may store |
| no-cache | May be stored, but must revalidate before reuse | Want version verification before reuse |
| no-store | Do not store the response in any cache per HTTP semantics | Sensitive content or caching prohibited |
| must-revalidate | Once stale, must revalidate before reuse per directive conditions | Disallow serving stale outside allowed conditions |
| stale-while-revalidate | May serve stale within defined window while revalidating in background | Public content tolerating brief staleness |
| stale-if-error | May serve stale when origin fails within defined window | Preserve UX for non-sensitive data with clear staleness caps |

Example:

~~~http
Cache-Control: public, max-age=300, s-maxage=900, stale-while-revalidate=30
ETag: "property-91-v1842"
Vary: Accept-Encoding
~~~

In this example, max-age targets private caches like browsers, while s-maxage applies to shared caches per HTTP caching semantics and overrides freshness duration accordingly. Real CDNs also have their own cache policy settings; understand how your provider prioritizes origin headers, min/max TTLs, query strings, and cookies.

**Never set public just to increase hit ratios.** Responses carrying user, tenant, cookie, or permission-dependent data can be stored at the wrong scope by shared caches if policies/keys are misconfigured.

### 5.2. ETag and Last-Modified

An ETag is a validator representing a specific version of a representation. Browsers send If-None-Match; if the representation has not changed, the server returns 304 Not Modified without resending the body. Last-Modified with If-Modified-Since provides time-based validation, whose precision depends on implementation.

Validators enable **revalidation** instead of re-downloading full representations. Ensure ETags accurately reflect content and variants; ETag semantics for gzip vs. uncompressed responses vary by implementation. Never use ETags as proof of authorization or tamper resistance for business data.

### 5.3. Static assets and cache busting

For built CSS/JS/images containing a content hash in their filename, cache very long and mark immutable:

~~~http
Cache-Control: public, max-age=31536000, immutable
~~~

For example, app.a83f91c2.js and app.19bc72d0.css. When content changes, builds emit new filenames; updated HTML or manifests reference the new versions. Never overwrite content at a URL already published as immutable, because browsers/CDNs may keep serving the old version for an extended period.

## 6. CDNs and Reverse Proxies: Caching Close to Users

CDNs typically cache by hostname/path/query/headers/cookies depending on configuration. They reduce round trips to the origin and distribute static assets along with eligible public API responses.

### 6.1. CDN cache policies

When configuring a CDN, specify cacheable methods, cache keys, origin request policies, TTLs, compression/content encoding, purge/invalidation, stale behavior, and origin protection. Normally cache only GET/HEAD; never cache POST/PUT/DELETE without explicit semantics.

### 6.2. Cache hit ratio is not the only goal

A CDN with a high hit ratio that caches the wrong locale, tenant, or version is still a severe bug. Certain routes have low hit ratios yet must be served from the origin to preserve correctness. Evaluate hit ratio, origin offload, latency, error rate, cache key cardinality, and false sharing together.

### 6.3. Purging/invalidation from origin to CDN

When a property updates images or content, you can:

1. Write the new content to object storage under a new key/version.
2. Update metadata in the authoritative source.
3. Emit a PropertyMediaUpdated event.
4. Invalidation workers identify affected URLs/prefixes/surrogate keys.
5. Issue purges to the CDN and track completion status.
6. UI references the new URL/version; old URLs expire or get purged per policy.

Purges may not take effect instantaneously across every edge node. Never design a business transaction that relies on every CDN edge confirming a purge simultaneously. For content that must change immediately for safety or policy reasons, add a serving denylist or new URLs and enforce access control at the origin.

## 7. Application Caches: Local Memory and Distributed Caches

Application caches typically store computed results, domain objects, sessions, or read models.

| Type | Characteristics | Best Fit | Risks |
| --- | --- | --- | --- |
| In-process memory | Lives inside each instance's memory | Small data, fast access, per-instance divergence acceptable | Different instances hold different copies; restarts wipe cache |
| Distributed cache | Multiple instances share Redis/Memcached or equivalent service | Shared cache, fewer database queries | Adds network hops, dependency, cost, and failure modes |

### 7.1. Cache-aside

A common pattern:

1. Application reads cache by key.
2. On hit, returns data per freshness policy.
3. On miss, reads the authoritative data source.
4. Writes cache with appropriate TTL.
5. On data update, commits to source then invalidates/updates cache per chosen consistency mechanism.

~~~text
value = cache.get(key)
if value is fresh:
    return value
value = database.read(key)
cache.set(key, value, ttl)
return value
~~~

This is pseudocode. Production code must handle concurrent misses, cache failures, non-existent data, serializer/version mismatches, and post-commit errors.

### 7.2. Read-through and write-through/write-behind

- **Read-through:** cache layer automatically loads from the source on misses; applications treat the cache as the read interface.
- **Write-through:** writes go through the cache layer and update the source per supported mechanisms, typically requiring transaction considerations.
- **Write-behind/write-back:** writes to the cache first and updates the source later; throughput can be high, but data-loss risks and requirements for durable queues/flushing/error recovery are much higher.

Never choose write-behind for authoritative transactions without proven durability, replay, and reconciliation models. Standard caches are not durable databases.

## 8. Synchronizing Invalidation Across Tiers

A major challenge is that one source change must propagate to multiple cache tiers. There is no single purge primitive that runs atomically across browsers, CDNs, app caches, and databases.

### 8.1. Event-driven invalidation

~~~mermaid
sequenceDiagram
    participant U as Admin/API
    participant DB as Source DB
    participant O as Outbox
    participant W as Invalidation Worker
    participant C as App Cache
    participant CDN as CDN
    U->>DB: Update property
    DB->>O: Commit event in same transaction
    O-->>W: PropertyUpdated v1843
    W->>C: Delete/update application keys
    W->>CDN: Purge related URL/tag
    W-->>W: Record result and retry failures
~~~

For browsers, servers cannot arbitrarily wipe caches on offline clients. Use versioned URLs for static assets, short TTLs/revalidation for dynamic responses, or updated versions in pages/manifests so clients reference fresh resources.

### 8.2. Invalidation must be idempotent

Events may be redelivered; purging the same URL repeatedly is usually safe, yet workers must still be designed idempotently with bounded retries and outcome tracking. If events arrive out of order, older events must never revert the cache to previous content. Use entity versions/generations or check versions before updating the cache.

### 8.3. Invalidate after commit

If the cache is deleted first and the database transaction rolls back, subsequent requests can read old data from the database and repopulate the cache. A safer workflow commits changes to the source of truth, writes an outbox/change event in the same transaction or loss-proof log, lets invalidation workers consume events, deletes/updates cache entries by generation/version, records outcomes, retries failures, and alerts when backlogs threaten freshness SLOs.

A brief window of stale cache data still exists between commit and invalidation. If business requirements cannot tolerate this window, check the authoritative source on reads or build strong synchronization specifically for that flow.

## 9. Versioning for Predictable Cache Synchronization

URL- or key-based purging is difficult across multiple tiers and replicas. One technique embeds **version/generation** directly into cache keys or URLs:

~~~text
property:property-91:v1843
property-media/property-91/image-v1843.webp
search-result:v3:locale=vi:...
~~~

When the source bumps version from 1842 to 1843, applications read the new key. Old entries may linger briefly, yet new requests stop referencing them and TTLs clean them up gradually. For media/objects, new URLs eliminate waiting for edge purges before users see new assets.

Versioning works well for content-hashed static assets, projections/documents with sourceVersion, aggregate application caches, HTML/manifests pointing to versioned assets, and API responses with schema/content generations.

The downside is old entries consuming memory until TTL/eviction runs; enforce retention and quotas. Never put a single global generation across all keys if minor edits would invalidate the entire cache and tank hit ratios.

## 10. Cache Stampede, Thundering Herd, and Prevention

A **cache stampede** occurs when a hot key expires and many concurrent requests miss simultaneously, flooding the database or origin service.

Mitigations:

- **Single-flight/request coalescing:** only one request loads data; other requests wait for the shared result.
- **TTL jitter:** add random variance to TTLs so keys do not expire together.
- **Refresh ahead:** refresh before expiration based on popularity and predictability.
- **Stale-while-revalidate:** serve stale data within allowed bounds while a worker updates in the background.
- **Negative caching:** briefly cache non-existent results to curb repeated lookups, while handling newly created objects.
- **Rate limiting/bulkheads:** cap miss traffic hitting the origin.

TTL jitter example:

~~~text
effectiveTTL = baseTTL + random(0, jitterWindow)
~~~

Do not apply stale-while-revalidate to data that can cause wrong decisions, such as room availability, payment status, or access permissions. Negative caches should also avoid long TTLs if new records may appear immediately afterward.

## 11. When to Serve Stale and When to Re-Verify

Stale data is not always bad. During a transient origin failure, returning a slightly older property description beats showing a blank page; however, using stale room availability to confirm a booking causes overbooking.

| Data/Action | Safe to Serve Stale? | Conditions |
| --- | --- | --- |
| Public images/descriptions | Usually yes | Within defined stale age, no takedown/removal violation |
| Catalogs/amenities | Yes | Show last-updated timestamp or tolerate minor drift |
| Search results | Bounded yes | Transactional source must verify prior to booking |
| Estimated price | Conditionally | Clearly mark indicative only and re-verify before checkout |
| Room availability | Never use stale to commit | Always verify against inventory/booking source |
| Permissions/roles | Never keep stale long if privilege-sensitive | Fast refresh/revocation; verify per security requirements |
| Payment/booking status | Never use stale for side effects | Read authoritative source or verified state |

When permissions are revoked, stale permission caches create security holes. Enforce dedicated freshness/revocation SLOs for authorization caches rather than using long TTLs like image assets.

## 12. Cache Keys, Tenant Isolation, and Private Data

Caches shared across tenants risk data leaks if keys omit tenant scope or policies fail to separate private responses.

Safety rules:

- Authenticate identity and tenant server-side before constructing cache keys.
- Never trust client-supplied tenant headers without verifying membership.
- Shared caches should store only public content or responses safely designed for sharing.
- For personal responses, use private caches or identity-scoped keys; consider Cache-Control private or no-store.
- Never cache responses containing tokens/cookies or permission details without tested cache policies.
- When roles/permissions change, invalidate by identity/tenant and never let old responses persist past freshness SLOs.
- Never log keys containing tokens, emails, or personal data.

### 12.1. HTTP Vary and cache partitioning

The Vary header tells caches which request headers alter the response. For example, Vary: Accept-Encoding lets caches separate compressed from uncompressed payloads. If responses genuinely change by language, Vary: Accept-Language may be needed.

Never add Vary: Cookie globally without evaluation; it creates massive variants and destroys hit ratios. Yet omitting cookies/headers that do change content risks shared caches serving the wrong data. Inspect actual headers, CDN cache keys, and response semantics.

## 13. Synchronizing Caches During Deployments and Schema Changes

Caches store data serialized according to application schemas. During rolling deployments of a new version, old and new application instances may access the distributed cache concurrently.

Strategies:

- **Versioned cache keys:** include namespace/version in keys, e.g., profile:v2:<id>.
- **Backward-compatible serialization:** new code reads old formats during transition.
- **Dual-read:** try the new key, then fall back to the old key temporarily.
- **Warm-up:** pre-populate critical keys after deployments or failovers.
- **Gradual migration:** clean up old cache entries once old instances terminate and metrics confirm stability.

Never change serialized object formats under the same key if older running instances cannot deserialize them. That can cause widespread errors during rollouts.

### 13.1. Cache warm-up and cold starts

When a cache cluster restarts or changes key namespaces, hit ratios can plunge abruptly and force the database to handle mass misses. Warm up measured hot-key lists, rate-limit loading concurrency, apply single-flight and backpressure, monitor hit ratio/origin RPS/DB saturation, and let caches warm gradually with traffic.

## 14. Topology, Availability, and Cache Operations

| Failure Mode | Impact | Required Behavior |
| --- | --- | --- |
| Stale browser cache | Outdated UI or stale data | Versioned assets, validators, TTLs, and controlled hard refresh paths |
| CDN edge failure/missed purge | Higher origin load or stale responses | Multi-origin/edge policies as feasible, TTLs, and versioned URLs |
| Distributed cache disconnect | Mass cache misses or API errors | Short timeouts, bounded fallbacks, bulkheads, and backpressure |
| Cache cluster failover | Partial key loss or latency spike | Persistence/replication as needed, warm-up, and verified loss tolerance |
| Invalidation worker backlog | Prolonged staleness | Queue age alerts, retries, dead-letter handling, and reconciliation |
| Database overload from misses | Slow API transactions | Load shedding, rate limits, stale serving only for allowed data |
| Overly broad accidental purge | Hit ratio drop, origin spike | Scoped purges, canaries, auditing, and capacity headroom |

### 14.1. Fallback on cache failure

Bypassing the cache straight to the database is not always safe. If 100% of traffic switches to the origin when Redis fails, the database can collapse next. Fallback designs should include short timeouts, circuit breakers, concurrency/rate caps toward the origin, stale serving only where permitted, degraded mode for non-essential queries, and gradual cache recovery.

## 15. Observing Freshness and Effectiveness Across Tiers

Do not measure hit ratio alone. Observe **freshness and correctness**:

| Metric Group | Examples |
| --- | --- |
| Browser/HTTP | Cache-Control, 304 rates, asset versions, client stale reports if available |
| CDN | Hits/misses, origin offload, age headers, purge completion, errors per POP |
| Application cache | Hits/misses, evictions, key cardinality, memory, latency, timeouts |
| Invalidation | Outbox lag, queue age, purge success/failures, retries/DLQ |
| Data source | Commit timestamps/versions, replication lag, read latency |
| Freshness | Source version vs. cached/indexed version, response age |
| Correctness | Sampled mismatches, stale bookings/prices prevented, tenant isolation tests |
| Cost | Cache nodes/memory, CDN transfer/requests, origin egress, purges, and ops |

### 15.1. Cross-tier freshness lag

~~~text
freshnessLag = now - sourceCommitTime
versionLag   = sourceVersion - cachedSourceVersion
~~~

These are conceptual formulas; system clocks must be synchronized and versions must have valid comparison semantics. For browser caches, servers cannot directly observe when every client receives updates; measure via asset version telemetry or privacy-compliant client feedback.

### 15.2. Tracing a single change

When a user reports a stale price, check which version the database/Pricing Service holds; which key/version the application cache stores; whether CDN cache keys include every price-affecting parameter; what TTLs/validators response headers advertise; which URL/ETag the browser holds; and whether invalidation events were emitted, processed by workers, and purged completely.

A dashboard combining request trace/correlation IDs, cache age, and source version helps distinguish cache key bugs, slow invalidation, and un-updated source data.

## 16. Process for Designing Multi-Tier Synchronization

~~~mermaid
flowchart TD
    A["Classify data and journeys"]
    A --> B["Set freshness/stale SLOs"]
    B --> C["Choose appropriate cache tiers"]
    C --> D["Design keys, TTLs, validators, and security"]
    D --> E["Define write/invalidation/version flows"]
    E --> F["Test staleness, stampedes, failures, and tenant isolation"]
    F --> G["Canary deploy and observe"]
    G --> H["Tune TTLs, purges, fallbacks, and cost"]
~~~

For each data type, write a cache contract specifying owner and authoritative source; permitted cache tiers; cache key dimensions and normalization; TTL/freshness/max stale age; HTTP headers/validators/shared-private rules; invalidation events/versions and post-commit ordering; fallbacks; tenant/privacy constraints; and metrics/alerts/runbooks/retention/cost.

## 17. Hands-On Exercise: Synchronizing Caches for a Booking Platform

**Hypothetical context:** a platform has a website and mobile app, global CDN, API gateway, 4 Booking API instances, and a distributed cache. Property pages contain images, descriptions, and amenities; search supports date and price filters; availability and pricing change frequently; accounts and bookings are personal data.

### Tasks

1. Draw a diagram of browser → CDN → gateway → application cache → database/search store, marking which requests traverse each tier.
2. Classify at least six data types by freshness SLO and maximum stale age.
3. Design HTTP Cache-Control/ETag headers for static assets, property pages, and private endpoints.
4. Design cache keys for search queries including locale, dates, guest counts, filters, and tenant if needed; prove no cross-tenant leakage.
5. Design update flows for property images/content using versioned keys and CDN purges; specify stale browser cache behavior.
6. Design price/availability update flows and prove search caches cannot confirm bookings.
7. Design outbox/event invalidation for application caches and CDNs; handle duplicate/out-of-order events.
8. Simulate cache stampedes, Redis unavailability, CDN purge backlogs, and cold starts; specify fallbacks/backpressure.
9. Define metrics for freshness, hit ratio, origin offload, invalidation lag, stale responses, and cost.
10. Write an ADR detailing chosen cache tiers, TTLs, consistency, risks, and revisit triggers.

### Sample cache contract

| Data | Authoritative Source | Cache Tiers | Freshness/Staleness | Invalidation |
| --- | --- | --- | --- | --- |
| Hashed CSS/JS | Build artifacts | Browser + CDN | Long-term, immutable | New URL on build |
| Property images | Media service/object storage | Browser + CDN | Long-term by version | New key/URL and scoped purge |
| Property descriptions | Property DB | CDN/app per public policy | Short; bounded stale | PropertyUpdated event |
| Search results | Search projection | CDN/app per keys and privacy | Short; candidates only | Index update/version |
| Prices | Pricing DB/service | Optional short cache for display | Never stale to finalize | PriceUpdated/version |
| Availability | Inventory/Booking DB | Restricted caching | Never stale to commit | Authoritative recheck |
| Personal bookings | Booking DB | Private/no-store per risk | Verify permissions and status | No shared caching |

### Completion criteria

- Every data type has a freshness contract and authoritative source.
- Cache keys prevent semantic collisions and cross-tenant/user data leaks.
- Browser/CDN/application caches have mutually consistent TTLs, validators, purges/versions, and fallbacks.
- Invalidation events support retries, duplicate handling, and backlog monitoring.
- Pricing, availability, permissions, and bookings are verified at the authoritative source when required.
- Stampede protections exist and cache failures do not crash the origin.
- Stale caches, schema-changing deployments, cold starts, purges, and tenant isolation have been tested.
- Measurements exist for latency, hit ratio, freshness, correctness, and cost.

## 18. Well-Architected Pre-Production Checklist for Multi-Layer Caches

- [ ] Data is classified by access pattern, sensitivity, and rate of change.
- [ ] Every data type has an authoritative source, freshness target, and maximum stale age.
- [ ] Permitted cache tiers are defined; shared caches hold only responses safe for shared semantics.
- [ ] Cache keys include all response-affecting dimensions and exclude tokens/PII.
- [ ] Query normalization, Vary, cookies/headers, and content negotiation are verified.
- [ ] Cache-Control, ETag/Last-Modified, TTLs, and stale directives match each route.
- [ ] Static assets use version/content hashes for long caching; immutable URLs are never overwritten.
- [ ] CDN policies explicitly define methods, keys, cookies, headers, origin requests, TTLs, and purges.
- [ ] Application caches define read/write strategies, versioning, TTLs, and invalidation.
- [ ] Invalidation follows source commits via events/CDC/outbox with retries and idempotency.
- [ ] Cache stampedes, thundering herds, cold starts, and cache outages have load-shedding protections.
- [ ] Stale serving is conditional; never use stale data for transactions, availability, final pricing, or permissions.
- [ ] Tenant isolation, authorization revocation, TLS, IAM, and log masking are verified.
- [ ] Metrics cover hits/misses, freshness lag, origin load, purge backlogs, stale responses, and correctness.
- [ ] Runbooks exist for CDN, distributed cache, invalidation worker, or origin failures.
- [ ] Costs of cache memory, CDN, requests, egress, purges, and operations are evaluated.
- [ ] An ADR documents trade-offs across reliability, security, performance, cost, and operations.

**Core takeaway:** browser, CDN, application, and data caches are copies at different locations with varying levels of control and lifetimes. To make them operate as a unified system, define **authoritative sources, cache keys, freshness, validators, invalidation/versioning, stale policies, and fallbacks** for every data type. Effective caching accelerates systems while preserving data correctness and security boundaries under rising load or single-tier failures.
