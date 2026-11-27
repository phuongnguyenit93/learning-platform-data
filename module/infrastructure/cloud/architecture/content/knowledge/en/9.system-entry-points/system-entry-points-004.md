# CDN, Edge Caching, and Static Asset Delivery

> **Chapter:** System Entry Points  
> **Scope:** Cloud application architecture design (CLOUD_ARCHITECTURE), from business requirements to selecting networking, compute, data, and deployment models. Focuses on trade-offs across latency, scalability, availability, security, cost, and operations under Well-Architected principles.

## Learning Objectives

After this lesson, you will be able to:

1. Explain the roles of a **Content Delivery Network (CDN)**, **Point of Presence (PoP)**, **edge cache**, **origin**, **origin shield**, and caching layers along an HTTP request path.
2. Design caching policies based on data characteristics, acceptable staleness, access permissions, and **Cache-Control**, **ETag**, **Last-Modified**, and **Vary** directives.
3. Safely deliver HTML, CSS, JavaScript, images, fonts, video, and downloadable files; select **content-hashed filenames**, **TTL**, **revalidation**, **invalidation**, and **deployment** strategies.
4. Mitigate cross-user/tenant data leaks, cache poisoning, unauthorized origin access, and asset delivery failures.
5. Measure effectiveness using cache hit ratio, byte hit ratio, origin offload, p95/p99 TTFB, Core Web Vitals, error rates, and total cost.
6. Evaluate CDN, edge caching, browser caching, and origin storage options against business requirements, reliability, security, cost, and operability.

## 1. Why Is a CDN Part of System Entry Points?

Suppose a cloud booking application is deployed in one region while customers access it from multiple countries. If every browser fetches images, CSS, JavaScript, and documents directly from application servers in that region, the system suffers:

- **Network latency:** distant connections incur large round-trip times, hurting Time to First Byte (TTFB) and page render speed.
- **Repeated load:** the exact same CSS file or logo image is transferred from the origin thousands of times even when unchanged.
- **Cost and bottlenecks:** the origin must serve extra requests, bandwidth, and TLS/HTTP processing, competing for resources with critical business workflows.
- **Incident blast radius:** a slow origin or network path to the origin degrades the experience for all users.

A **CDN** is a distributed network of edge locations that can place **copies of cacheable content** closer to users and route requests onward to the application/origin layer when needed. CDNs may also provide TLS termination, content delivery optimization, security policies, and traffic filtering, though exact capabilities depend on the provider and configuration.

Its core value is **shortening the distance frequently accessed data travels, offloading repetitive work from the origin, and lowering latency for eligible content**. A CDN cannot automatically speed up every API: requests requiring live computation and fresh reads still wait on the origin.

### Key Terms

| Term | Meaning | Role in Architecture |
| --- | --- | --- |
| **PoP (Point of Presence)** | Network location housing request-handling infrastructure, often with cache | Receives user traffic via CDN routing mechanisms |
| **Edge cache** | Cache residing at or near a PoP | Serves cacheable content without always calling the origin |
| **Origin** | Authoritative content source: object storage, web server, app service, or another service | Handles cache misses, revalidation, and uncacheable content |
| **Cache key** | Set of attributes identifying a cached object variant | Determines which requests share the same cached copy |
| **TTL (Time to Live)** | Duration a cached copy is considered fresh under policy | Balances content freshness against origin offload |
| **Cache hit/miss** | Hit: matching copy available to serve; miss: no matching copy found | Indicator of cache efficiency, not the sole performance metric |
| **Revalidation** | Checking with the origin whether a stale copy is still valid | Allows reusing cached content upon a 304 Not Modified response |
| **Invalidation/purge** | Removing or marking edge-cached copies invalid | Used to refresh content before TTL expires |
| **Origin shield / tiered cache** | Intermediate cache layer between multiple PoPs and the origin | Reduces concurrent origin fetches across PoPs |
| **Edge function/worker** | Logic executed at the edge when supported by the platform | Redirects, request normalization, access checks, bounded transformations |

**A CDN differs from a load balancer:** a CDN focuses on edge distribution and caching; a load balancer focuses on distributing traffic across backend targets. Both often coexist on the same path. **A CDN also differs from DNS:** DNS resolves domain names and can steer clients toward CDN endpoints; DNS does not store or serve HTTP content.

## 2. Request Path from User to Origin

### 2.1. Reference Architecture

~~~mermaid
flowchart LR
    U["Browser / mobile app"] --> DNS["DNS for domain"]
    DNS -. "Resolution / steering" .-> EDGE["Network-nearby CDN PoP"]
    U -->|"HTTPS request"| EDGE
    EDGE -->|"Cache HIT"| U
    EDGE -->|"MISS / revalidate"| SHIELD["Regional cache / origin shield (optional)"]
    SHIELD -->|"MISS / fresh data needed"| ORIGIN["Origin endpoint"]
    ORIGIN --> OBJ[("Object storage: CSS / JS / images")]
    ORIGIN --> APP["Application / API"]
    APP --> DB[("Database")]
~~~

This is a logical diagram. PoP selection may rely on DNS, Anycast, or other routing techniques depending on the provider; **the geographically closest PoP is not always the lowest-latency network path**.

An edge-cached request typically flows as follows:

1. The browser resolves the domain and opens an HTTPS connection to the CDN.
2. The CDN evaluates host, path, cache key components, security rules, and cache policies.
3. If a **fresh** and valid copy exists for the request, the CDN returns it directly.
4. If no copy exists, the copy is expired, or validation is needed, the CDN contacts the origin or intermediate cache tier.
5. The origin returns the content and headers. The CDN decides whether to store it, for how long, and under which cache key.
6. The browser receives the response and may additionally store it in the **browser cache** per its own rules.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant C as CDN Edge
    participant O as Origin
    B->>C: GET /assets/app.a71c.css
    alt Valid cached copy (HIT)
      C-->>B: 200 + cached content
    else Missing or invalid (MISS)
      C->>O: GET /assets/app.a71c.css
      O-->>C: 200 + Cache-Control + content
      C->>C: Store per policy
      C-->>B: 200 + content
    end
    Note over B,C: Subsequent loads may use browser cache directly
~~~

### 2.2. Cache Layers That Are Often Confused

| Layer | Location | Sharing Scope | Key Design Considerations |
| --- | --- | --- | --- |
| **Browser cache** | User device | Typically per browser profile and cache partition | Freshness, reloads, app versioning, sensitive data |
| **CDN shared cache** | PoP or CDN cache tier | Across many requests/users matching cache key and policy | Never cache private content by mistake; tune TTL and invalidation |
| **Reverse-proxy cache** | Near application/origin | Across clients hitting a backend cluster | Cache key, memory sizing, TTL, behavior on backend errors |
| **Application cache** | In-process, distributed cache, or DB cache | Scoped to app/tenant and data keys | Invalidation, consistency, DB offload |
| **Origin shield** | Between edge and origin | Across multiple PoPs in a region/cache tier | Prevents synchronized cache misses and origin overload |

A single file can simultaneously reside in browser cache, edge cache, and reverse-proxy cache. Purging the CDN cache **does not** remove copies already cached long-term in users' browsers. Therefore, for assets that must update reliably, **changing URLs per content version** is far more reliable than relying on purges alone.

## 3. Classify Content Before Choosing Cache Policies

Never apply one uniform TTL across an entire website. Each content class has distinct sensitivity and freshness requirements.

| Resource Type | Sharing / Freshness Profile | Reference Strategy | Notes |
| --- | --- | --- | --- |
| CSS/JS with content-hashed filenames | Public, immutable per URL | Long TTL; cache in browser and CDN | Never overwrite the same URL with new content |
| Versioned fonts, icons, images | Public, rarely changes | Long TTL when URL changes with content | Configure proper CORS headers where fonts are used |
| Public marketing HTML | Updated frequently | Short TTL or revalidation | Ensure HTML references matching asset versions |
| Post-login HTML | Contains session/user state | Do not store in shared caches by default | Never apply a generic TTL to personalized responses |
| Public catalog read API | Tolerates seconds/minutes of staleness | Short TTL, complete cache key parameters | Cache only if unpersonalized and consistency-safe |
| Payment/booking status API | Real-time state and access control | Bypass CDN shared cache | Enforce authorization and live transaction state |
| Customer-specific downloadable docs | Sensitive, permission-checked | Expiring signed URLs/cookies or origin auth + strict cache policy | Never let two tenants share a cache key |
| Resized/reformatted image variants | Public, many variants | Cache by permitted dimensions and formats | Bound allowed variants to prevent cache bloat |

Safe baseline: **enable shared caching only for content explicitly verified as shareable**. For personal content, tenant data, financial state, or access-controlled information, design dedicated controls and bypass CDN caching by default.

**Cacheability** (allowed to store) and **correctness** (serving accurate data) are separate questions: a public API may be technically cacheable yet still unsuitable for a 10-minute TTL if inventory changes every few seconds.

## 4. Understanding HTTP Cache-Control Accurately

Cache-Control consists of directives governing storage and reuse of HTTP responses. Shared caches may obey different directives than browser caches; real behavior also depends on CDN settings, request methods, headers, and override policies.

| Directive | Practical Meaning | Common Use Cases |
| --- | --- | --- |
| **public** | Permits shared caches to store the response under HTTP rules | Publicly shareable content |
| **private** | Disallows shared caches; browser may still store per rules | User-specific content not to be shared |
| **no-store** | Compliant caches must not persist the response | Sensitive pages/responses that must never be stored |
| **no-cache** | May be stored, but must **revalidate with origin before reuse** | HTML needing prompt updates when content changes |
| **max-age=N** | Seconds the response remains fresh per HTTP caching rules | Browsers and applicable caches |
| **s-maxage=N** | Preferred freshness TTL for **shared caches**, when supported | Letting CDNs hold public content longer than browsers |
| **must-revalidate** | Once stale, must not be reused without successful validation | Content requiring strict verification after expiry |
| **immutable** | Hints that content will not change during its freshness lifetime | Content-hashed static assets |
| **stale-while-revalidate=N** | Allows serving stale content for N seconds during background revalidation | Public content tolerating brief update lag |
| **stale-if-error=N** | Permits bounded stale serving when eligible origin errors occur | Public content prioritizing availability |

**Two common misconceptions:**

- **no-cache does not mean "do not store."** It requires revalidation before reusing a stored copy. To forbid storage altogether, use **no-store** alongside matching data policies.
- **Expired TTL does not mean the cache deleted the object.** Caches may retain stale objects for revalidation or stale-serving directives. Distinguish "no longer fresh" from "purged."

### 4.1. Example 1: Content-Hashed Static Asset

~~~http
HTTP/1.1 200 OK
Content-Type: text/javascript; charset=utf-8
Cache-Control: public, max-age=31536000, immutable
ETag: "js-bundle-a71c"
~~~

Assuming the path is **/assets/app.a71c.js** and suffix **a71c** is derived from build content, a one-year TTL is safe only if **this URL is never reused for different content**. On code changes, emit a new filename such as **app.9fe2.js** instead of overwriting app.a71c.js.

### 4.2. Example 2: Public HTML Needing Prompt Updates

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Cache-Control: public, max-age=0, s-maxage=60, stale-while-revalidate=30
ETag: "home-v42"
~~~

Illustrative config: browsers revalidate immediately due to max-age=0, while shared caches stay fresh for 60 seconds and may serve stale for up to 30 seconds while revalidating asynchronously. Use only when the HTML is truly **unpersonalized** and brief update lag is acceptable. Verify provider support and edge rules.

### 4.3. Example 3: Sensitive Post-Login Content

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store
~~~

Illustrative header for an API returning private user data. For stronger safety, CDN rules should also **bypass caching** on authenticated routes rather than relying solely on origin headers if edge overrides exist.

### 4.4. Example 4: Public API Tolerating Brief Staleness

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=15, s-maxage=90, stale-while-revalidate=30
Vary: Accept-Encoding
~~~

Appropriate only if every caller sharing the URL/cache key is authorized to see **identical results**, bounded staleness is acceptable, and the origin does not vary output by session, cookie, or token. If inventory shifts continuously, a 90-second TTL may break business correctness.

### 4.5. CDNs Often Enforce Their Own Override Policies

CDNs frequently offer **cache rules, origin TTL overrides, min/max TTLs, cache status headers, and error caching**. Therefore:

1. Never assume behavior from origin Cache-Control headers alone.
2. Verify actual precedence between origin headers and edge rules.
3. Build test checks for **HIT/MISS/REVALIDATED** and inspect response headers.
4. Ensure new rules never accidentally cache responses carrying Authorization, Cookie, or Set-Cookie.

## 5. ETag, Last-Modified, and Revalidation

When a cache holds a stale copy, it can send a **conditional request** to the origin instead of downloading the full payload again.

- **ETag** is a validator identifier for a specific representation version. Caches send **If-None-Match** to ask if the content still matches.
- **Last-Modified** is the modification timestamp published by the origin. Caches send **If-Modified-Since**; precision and semantics depend on the app.
- If unchanged, the origin returns **304 Not Modified**, and the cache reuses its stored body while refreshing metadata.
- If changed, the origin returns the new representation (typically **200 OK**) with updated headers.

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant E as CDN Edge
    participant O as Origin
    U->>E: GET /public/menu.json
    Note over E: Cached copy freshness expired
    E->>O: GET + If-None-Match: "menu-v7"
    alt Content unchanged
      O-->>E: 304 Not Modified + updated headers
      E-->>U: 200 served from cached body
    else Content changed
      O-->>E: 200 + ETag: "menu-v8" + new body
      E-->>U: 200 + new body
    end
~~~

**304 is not an origin-free cache hit:** revalidation still incurs a network round-trip to the origin, even though it saves body bandwidth. When analyzing cache performance, separate direct cache hits from origin revalidations.

For content-hashed assets, revalidation is rarely needed while fresh. For frequently updated HTML or public catalogs, validators avoid re-transmitting unchanged bodies.

## 6. Cache Keys: Key to Correctness and Preventing Leaks

A cache key is the set of attributes a CDN uses to identify a cached response variant. In many implementations it includes **scheme, host, path, query parameters**, and selected allowlisted headers/cookies. Default keys vary across providers.

Examples:

- **/images/item.jpg?w=200** and **/images/item.jpg?w=800** must have distinct keys if image bodies differ in size.
- **/catalog?lang=vi** and **/catalog?lang=en** must produce separate cached entries when language changes output.
- Tracking parameters that do not alter output, such as **utm_source**, can be excluded from the cache key **after verifying the origin ignores them**.
- Responses varying by Cookie, Authorization, or tenant must never share a cache key with unauthorized callers.

### 6.1. Vary and Content Negotiation

The **Vary** header declares which request headers influence response selection, for example:

~~~http
Vary: Accept-Encoding
~~~

Vary can be used with Accept-Language or a normalized image format header, yet **never add arbitrary headers indiscriminately**. Excessive variants crush hit ratio, raise cost, and risk cache fragmentation. Also verify whether your CDN actually honors Vary in its cache key construction.

### 6.2. Missing Cache Key Attributes Cause Data Leaks

Suppose `/api/profile` returns the signed-in user's profile based on a session cookie. If the CDN caches the response and serves it to another user simply because the URL matches, personal data leaks immediately.

Do not adopt "put all cookies in the cache key" as a universal fix: it is complex, error-prone, and still leaves authorization pitfalls. For profiles and private transactions, **bypassing shared caches** is normally safer and simpler.

If a product genuinely requires caching per-tenant or per-user data, design it with a full security review: verified identity, access permissions, key partitioning, lifetimes, revocation, and cross-access tests. A cache key relying on a client-asserted `tenant_id` **is not** authorization proof.

### 6.3. URL Normalization and Cache Poisoning

Checklist to audit:

- Are URLs differing only by slashes, percent-encoding, casing, query order, or duplicate parameters normalized identically?
- Does the origin use unkeyed Host headers, forwarded headers, or unkeyed query params to build redirect URLs or HTML?
- Are responses depending on Authorization, Cookie, Origin, or language properly marked and keyed?
- Can unusual request paths bypass rules meant to exclude **/api/private** or admin paths?
- Does the CDN cache **redirects, 404/500 errors, or Set-Cookie headers** under overly permissive rules?

**Cache poisoning** happens when an attacker manipulates a cacheable response so subsequent users receive malicious or wrong content. Mitigations include consistent request normalization, strict host/header allowlisting, isolating private content, and testing path/cache-key variations against the real origin.

## 7. Static Asset Deployment: Combining Immutable URLs with Fast-Updating HTML

A typical frontend build outputs:

~~~text
index.html
assets/
  app.8fe21a4.js
  style.b713e1c.css
  logo.4d92c30.svg
  font.6a8bf10.woff2
~~~

The strings in filenames are **illustrative content hashes**. Identical content deterministically produces the same filename; content changes produce new filenames.

### 7.1. Why Cache Assets Long and HTML Short?

**HTML** references the latest CSS/JS filenames. If HTML stays cached too long after a release, users keep loading stale versions. Conversely, older hashed assets should remain available temporarily because older HTML may still live in browser/CDN caches or open tabs.

| Resource | Policy Pattern | Rationale |
| --- | --- | --- |
| Public **/index.html** | no-cache, or short approved shared TTL | Surfaces new manifests/versions quickly |
| **/assets/app.hash.js** | public, long max-age, immutable | URL never reused for different body |
| **/assets/style.hash.css** | public, long max-age, immutable | Eliminates redundant downloads and origin load |
| **/api/me** | private, no-store; bypass edge cache | User-specific data |
| **/downloads/private/report.csv** | Permission-checked access; never shared casually | Private document that may require revocation |

### 7.2. Safe Release Sequence

~~~mermaid
flowchart TD
    A["Build hashed assets"] --> B["Upload new assets to object storage"]
    B --> C["Verify existence / MIME / integrity"]
    C --> D["Publish new HTML/manifest"]
    D --> E["Revalidate / purge HTML if policy requires"]
    E --> F["Monitor 404s, JS errors, hit ratio, and LCP"]
    F --> G["Retain old assets for agreed transition window"]
~~~

**Why upload assets before HTML?** If new HTML goes live first and references a JS bundle not yet uploaded to the origin, cache misses return 404 and break the page. Likewise, deleting old assets immediately after deploy breaks users with open tabs running older HTML who request lazy-loaded chunks.

Additionally:

- Use diff-aware uploads/syncs so URLs marked immutable are never overwritten.
- Set **accurate Content-Type headers** for JS, CSS, images, fonts, etc.; check compression behavior if objects are pre-compressed.
- Use declarative pipelines recording active release versions with fast rollback capability for HTML/manifests.
- Define retention policies, storage budgets, and version tracking for old assets aligned with TTLs and user behavior.
- If the app uses a **Service Worker**, design its update lifecycle carefully, as it introduces another independent cache layer.
- For code-split frontends using dynamic chunks, test navigating from an old tab right after a deploy to catch missing-chunk errors.

### 7.3. Single Page Applications (SPAs) and Fallback Routing

SPAs typically serve **index.html** for client-side routes that do not map to physical files, such as **/dashboard/orders**. However, fallback rules must never turn **/assets/missing.js** into an HTTP 200 returning HTML, which causes cryptic JavaScript parse errors in browsers.

Restrict SPA fallbacks to genuine navigation requests, while missing static assets must return proper **404/410** codes. Watch error caching policies too: a long-cached 404 captured right before an asset upload finishes can keep failing even after the file exists.

## 8. Content and Connection Optimization at the Edge

A CDN does not replace asset optimization. A page shipping 10 MB of JavaScript and unoptimized images remains slow even at a 100% cache hit ratio.

### 8.1. Images and Media

- Serve images sized to display dimensions, resolution, and device capabilities; avoid shipping huge images scaled down via CSS.
- Consider modern formats suited to content and clients (WebP/AVIF where supported) with appropriate fallbacks.
- Bound variant explosion: allowing arbitrary dimension query parameters lets abusers generate endless variants, inflating compute and storage costs.
- Use lazy loading for off-screen images; apply appropriate preload/priority hints for images affecting **Largest Contentful Paint (LCP)**.
- Large videos typically rely on segmented streaming protocols; configure the CDN for Byte-Range/segment caching, playback authorization, and media-appropriate caching.

### 8.2. Compression and Transport

- Text payloads like HTML/CSS/JS/JSON benefit from Brotli or gzip when supported by clients.
- Avoid re-compressing already compressed formats like most images/videos; gains are negligible or negative.
- Verify gzip/Brotli variants sharing a URL are keyed and served properly per **Accept-Encoding**.
- HTTP/2 and HTTP/3, TLS resumption, keep-alive, and edge connection reuse can improve transport depending on infrastructure, browsers, and network paths.
- Minimize critical resource count and size, eliminate unnecessary render-blocking CSS/JS, and validate improvements using Real User Monitoring (RUM).

### 8.3. When Is Edge Compute Useful?

Edge functions/workers handle URL rewrites, regional redirects, signature verification, security header injection, or **lightweight** personalization well. However, moving business logic and sensitive data onto the edge expands data processing locations, configuration complexity, and attack surface; assess data residency, secrets, backend callback latency, and per-invocation costs.

Start with **simple cache rules and a static origin**. Introduce edge code only for measured problems matched by operational readiness.

## 9. Securing the CDN, Origin, and User Data

Because a CDN sits on the system entry path, security controls must stay consistent across client, edge, and origin.

### 9.1. Essential Controls

1. **TLS client-to-edge and edge-to-origin:** configure certificates, protocol versions, and cipher policies per requirements; never leave edge-to-origin as unencrypted HTTP for sensitive traffic.
2. **Prevent unintended public origin exposure:** lock object storage origins so only the CDN can read them; protect application origins via firewalls/network policies or origin-authentication mechanisms. Verify how your provider actually enforces "edge-only origin access."
3. **WAF, bot protection, DDoS, and rate limiting:** filter abuse early at the edge according to risk policies; never substitute these for application authorization.
4. **Restrict caching of sensitive data:** bypass login pages, tokens, payment transactions, user profiles, and permissioned records unless explicitly engineered otherwise.
5. **Signed URLs / signed cookies:** time-bound access to authorized assets. Manage signing key storage, rotation, path scoping, expirations, and revocation behavior.
6. **Never trust client-supplied headers:** especially Host, forwarded host, tenant ID, origin IP, and any header used for redirects or cache keys.
7. **Application security headers:** evaluate Content-Security-Policy (CSP), HSTS, X-Content-Type-Options, and CORS policies; CDNs can inject them, but compatibility must be tested.
8. **Logs and personal data:** redact tokens, cookies, secret query params, and PII before storing edge logs/analytics; govern retention, access control, and storage regions.

### 9.2. Signed URLs Do Not Automatically Mean Uncached

A signed URL can let the edge verify access authorization before serving a cached body; execution depends on design and CDN features. Crucially, **cached bodies must never be served prior to required authentication/authorization checks**.

If multiple tenants with differing permissions reference a shared object URL, ensure unauthorized callers cannot retrieve it simply because another tenant warmed the cache. Account also for link sharing within the validity window and early revocation needs.

### 9.3. Illustrative Threat Matrix

| Attack / Misconfiguration | Impact | Defense and Verification Test |
| --- | --- | --- |
| Shared caching of profile responses | User/tenant data exposure | Bypass authenticated routes, audit cache keys, test with two accounts |
| Header/path cache poisoning | Multiple users served malicious/wrong payload | Normalize requests, trust only verified headers, fuzz URL variants |
| Direct access to origin object storage | Edge controls bypassed | Private origin, origin access policy, test direct non-CDN fetch |
| Overly long signed URL TTL | Unauthorized link redistribution | Short TTLs, narrow URL scope, revocation mechanism when needed |
| CDN rule stripping/ignoring Authorization | Data leak or wrong session served | Check auth bypass rules, run security integration tests |
| Malicious file upload served via CDN | CDN amplifies malware distribution | Validate uploads, scan files appropriately, enforce MIME and Content-Disposition |
| Edge logs capturing tokens/sessions | Leaks through observability tools | Redact sensitive fields, enforce RBAC, retention, and audits |
| Wrong wildcard/host mapping | Wrong domain content served | Verify domain/cert/origin mapping, test Host header variations |

**Zero trust mindset:** the CDN and internal network are defensive layers, yet applications must still independently authorize access to sensitive data and business actions.

## 10. Reliability, Failover, and Stale Data

A CDN helps keep static resources online when an origin slows down, yet **survivability depends on what is already cached, stale policies, failure modes, and origin design**.

### 10.1. Failure Scenarios

- **Single PoP failure:** the CDN shifts traffic to another location depending on routing and network conditions; latency and hit ratio may shift.
- **Slow or overloaded origin:** cache HITs keep serving eligible content; MISSes may fail and trigger a cache stampede.
- **Origin returning 5xx:** for public content, stale-if-error or conditional stale serving can keep older versions available. Never apply indiscriminately to payment states, live pricing requiring consistency, or private data.
- **Deployment asset mismatch:** new HTML references un-uploaded files, or negative 404 caching lingers. Enforce ordered publishing and rollback processes.
- **Global CDN config error:** a bad rule can affect every PoP simultaneously; require staged/canary rollouts and change controls.
- **Full origin region loss:** the CDN lacks uncached objects or unsynced data on standby origins; multi-region design, failover, and RTO/RPO must be validated independently.

### 10.2. Cache Stampede, Origin Shield, and Request Collapsing

Suppose a popular asset's TTL expires simultaneously across many PoPs. If all query the origin concurrently, traffic spikes abruptly (**cache stampede / thundering herd**).

Platform-dependent mitigations:

- **Origin shield / tiered caching:** consolidates misses from multiple PoPs to curb origin load.
- **Request collapsing/coalescing:** merges concurrent in-flight misses for the same cache key if supported by the CDN.
- **TTL jitter or proactive refresh:** avoids synchronized expiration across objects where feasible.
- **stale-while-revalidate:** serves stale copies while refreshing asynchronously for eligible public content.
- **Origin autoscaling / rate limiting:** helps survive MISS bursts, though never replaces good cache design.

### 10.3. Error Caching Must Be Bounded

Many CDNs cache status codes like 301, 302, 404, 500, or 503. While useful in some cases, it can prolong outages after backend recovery. Inspect **negative caching TTLs** to ensure transient 404s on newly uploaded assets do not stick and private error details are never cached.

### 10.4. Failover Must Preserve Correctness

A standby origin may sit in another AZ/region using replicated object storage or a standby app environment. Before failing over:

- Confirm static assets are synced and compatible with live HTML versions.
- Verify data residency rules allow serving from the standby region.
- Check DNS, TLS, origin failover, and cache keys for potential redirect loops.
- Test primary outage scenarios including cold CDN MISSes at PoPs lacking cached copies.
- Measure RTO (recovery time) and RPO (acceptable data loss) for **components holding stateful data that actually requires protection**.

For versioned static assets reproducible from build artifacts, RPO is evaluated differently than for transactional databases. Never equate logo/image availability with booking workflow availability.

## 11. Measuring CDN Effectiveness with Targeted Metrics

### 11.1. Distinguish Request Hit Ratio from Byte Hit Ratio

**Request hit ratio** (simplified model):

\[
H_{\text{request}}=\frac{\text{requests served by CDN from cache}}{\text{total relevant requests}} \times 100\%
\]

**Byte hit ratio**:

\[
H_{\text{byte}}=\frac{\text{bytes served by CDN from cached content}}{\text{total bytes served by CDN in scope}} \times 100\%
\]

A site with a 90% request hit ratio whose large video files are all MISSes can still saturate origin egress. Conversely, dynamic API calls intentionally bypassing the CDN lower overall hit ratio and are **not errors**.

Define the denominator clearly: all requests, cacheable requests only, whether revalidations, byte-range/partial requests, errors, or edge functions are included? Providers define metrics differently.

### 11.2. Operational Metrics

| Category | Metrics | Question Answered |
| --- | --- | --- |
| **Cache** | Hit/miss ratio, byte hit ratio, revalidation count, bypass count | Is eligible content actually cached and served correctly? |
| **Origin** | Origin requests/s, origin bandwidth, p95 origin latency, 5xx | Is the CDN genuinely offloading the origin? |
| **Experience** | Regional p50/p95/p99 TTFB, LCP, INP, resource load times | Are users receiving content faster? |
| **Quality** | 4xx/5xx, JS/CSS load failures, stale hits, MIME errors, asset 404s | Are the right versions and paths served reliably? |
| **Security** | WAF/rate-limit blocks, signature errors, denied origin requests | Are controls blocking threats without false positives? |
| **Cost** | CDN egress, requests, origin fetches, invalidations, edge compute, logging | Is total spend within budget? |
| **Operations** | Purge/publish time, rollback time, rule change frequency, incident count | Can issues be resolved quickly and safely? |

**TTFB** reflects DNS, TLS handshake, network path, edge processing, origin processing, and client measurement methodology. A low TTFB will not rescue LCP if hero images are oversized or JavaScript blocks rendering.

### 11.3. Verification with HTTP Requests

Inspect headers using:

~~~bash
curl -I https://static.example.com/assets/app.a71c.js
~~~

When testing live endpoints, inspect:

- Cache-Control, ETag, Last-Modified, Content-Type, and Vary.
- CDN cache-status headers if provided, such as HIT/MISS/BYPASS/REVALIDATED per provider conventions.
- Response Age header, when present, to estimate shared cache residency time (not all responses include it).
- Repeated calls to the same URL across cold/warm states, multiple network locations, before/after TTL expiry, and after deploys.
- Private API calls across two distinct accounts **must never return shared content**.

Do not treat a single local `curl` run as proof: PoPs, cookies, accept headers, cache warmth, origin state, and rules can vary by region and environment.

## 12. Cost Analysis: Where CDNs Save and Where They Add Spend

A CDN reduces origin traffic and compute, yet introduces its own billing dimensions:

- Egress data transfer from CDN to end users, varying by geography and provider tiers.
- Per-request charges and content transformation/processing fees.
- Origin fetch / cross-region egress fees if applicable.
- WAF, bot mitigation, edge functions, logging/analytics, and purges if billed separately.
- Object storage, replication, standby infrastructure, operations, and incident overhead.
- Differences in contracts, volume tiers, serving regions, and traffic growth models.

### Back-of-the-Envelope Example with Explicit Assumptions

Suppose in one billing period:

- **10 million downloads** of cacheable public assets occur.
- Average size is **100 KB/download**; using decimal units 1 KB = 1,000 bytes.
- The CDN achieves a **90% byte hit ratio** for this traffic scope.
- Excluding revalidation requests, range requests, protocol overhead, dynamic content, purges, and other cache layers for simplicity.

Then:

\[
B_{\text{client}} = 10{,}000{,}000 \times 100{,}000
 = 1{,}000{,}000{,}000{,}000\text{ bytes} \approx 1 \text{ TB}
\]

\[
B_{\text{origin}} \approx (1-0.90)\times1\text{ TB}=0.1\text{ TB}=100\text{ GB}
\]

**Conditional conclusion:** instead of the origin serving nearly 1 TB directly, origin body fetch drops to roughly 100 GB in this example. However, the CDN **still delivers roughly 1 TB to clients**, so CDN egress costs remain. Never equate a 90% hit ratio with "saving 90% of the cloud bill."

**Impact of geography and cache fragmentation:** if numerous PoPs, query variants, and versions warm caches independently, origin fetches can exceed simple estimates. Conversely, an origin shield/tiered cache can cut origin fetches substantially.

### TCO Comparison Table to Build

| Line Item | Without CDN | With CDN | Data Source |
| --- | --- | --- | --- |
| Origin compute | Higher from serving static directly | Lower when static traffic is offloaded | Measured CPU/network/requests |
| Origin egress | Direct to all clients | Edge fetches and other flows | Origin bytes and pricing rules |
| CDN egress | None | Present; often largest line item | Regional traffic and rate forecast |
| CDN requests/processing | None | Present | Request count and enabled features |
| Storage, backups, replicas | Present | Still present | Capacity and retention policies |
| Security and observability | App bears more directly | Shifts edge controls outward; adds fees | WAF, logs, metrics, audits |
| Operations | Origin/server changes | Adds cache keys, TTLs, purges, certs, rules | Engineering, incidents, pipelines |

Model at least three scenarios: **normal traffic, peak campaign load, and cache MISS/origin failover incidents**. The worst-case spike often occurs when purging the entire cache right before peak traffic.

## 13. Designing a CDN Architecture for a Scheduling Application

### 13.1. Business Scenario

A booking platform has:

- Marketing site, service listings, and thousands of public images.
- An SPA frontend whose CSS/JS bundles update several times a week.
- A public catalog API that can tolerate roughly one minute of staleness if Product approves.
- Availability search, booking creation, user account, payment, and transaction confirmation APIs requiring strict authorization and live state.
- Users distributed across multiple cities with traffic spikes during promotional campaigns.

Assumed goals: reduce static asset p95 load time in markets far from the origin, cut origin load, prevent cross-tenant data leaks, and ensure safe updates/rollbacks. Specific quantitative thresholds must be approved by Product/SRE before serving as acceptance criteria.

### 13.2. Proposed Architecture

~~~mermaid
flowchart TB
    U["Web / Mobile clients"] --> CDN["CDN: TLS, WAF, cache rules"]
    CDN -->|"Static HIT/MISS"| STO[("Private object storage\nHTML, hashed CSS/JS, images")]
    CDN -->|"Public catalog with TTL"| API["API Gateway / Load Balancer"]
    CDN -->|"Private API: BYPASS"| API
    API --> APP["Multi-AZ Booking App"]
    APP --> DB[("Transactional Database")]
    APP --> CACHE[("Business-scoped App Cache")]
    CDN -. "Cache metrics / logs" .-> OBS["Monitoring, tracing, cost"]
    APP -. "SLI / traces" .-> OBS
~~~

Labeled edges distinguish caching policies; one CDN endpoint can route by host/path to multiple origins, provided every rule is explicitly implemented and tested.

### 13.3. Proposed Policy Table

| Illustrative Path | Origin | Edge Cache | Browser Cache | Rationale |
| --- | --- | --- | --- | --- |
| **/assets/*.hash.js, *.hash.css** | Object storage | Long cache with immutable URLs | Long cache, immutable | Optimizes repeat loads and versioned deploys |
| **/images/catalog/*.hash.webp** | Object storage | Long cache per URL/variant | Long cache | Public, rarely changing media |
| **/**, **/landing** | Object storage/static site renderer | Short TTL or revalidate | Revalidate | HTML points to latest hashed assets |
| **/api/public/catalog** | App/API | Short TTL matching freshness target | Shorter or revalidate | Public catalog with bounded staleness |
| **/api/search/availability** | App/API | Bypass if live inventory needed | Per business rules; avoid arbitrary caching | Prevents misleading stale availability |
| **/api/bookings** | App/API | Bypass | no-store if carrying sensitive data | Correctness and authorization |
| **/api/payment/status** | App/API | Bypass | no-store | Sensitive transaction state |
| **/api/account/profile** | App/API | Bypass | no-store | Personal user data |
| **/download/private/** | Object storage or auth service | Enforce signature/auth check if cached; never share indiscriminately | Per data policy | Private customer documents |

This is an **illustrative proposal**, not a production-ready config. Classify public/private scope using real data governance and test all edge cases including errors, redirects, query params, cookies, and non-GET/HEAD HTTP methods.

### 13.4. Frontend Deployment Runbook

1. Build frontend, generating hashed assets and manifest.
2. Upload all new assets; verify origin object permissions, MIME types, checksums, and URLs.
3. Publish new HTML only after assets are confirmed ready.
4. Revalidate/purge updated HTML; avoid purging long-lived hashed assets.
5. Run synthetic checks from multiple network locations across SPA routes, assets, and private APIs.
6. Monitor asset 404s, JavaScript errors, p95 TTFB, LCP, cache HITs, and origin request rates.
7. To roll back, revert HTML/manifest to the retained prior version after confirming older chunks/assets are still intact.

### 13.5. Pre-Go-Live Verification Tests

| Test | Pass Criteria |
| --- | --- |
| Hashed JS/CSS files | Two versions keep distinct URLs, valid cache headers, zero 404s on rollout/rollback |
| Public HTML | Updates appear within committed freshness window without holding stale HTML past limits |
| Private API across two users | Cross-account/cross-tenant leakage via shared cache is impossible |
| Public catalog caching | Freshness stays within approved bounds; query variants return accurate results |
| Origin slowdown/brief outage | HITs keep serving per policy; MISSes and error responses follow runbook |
| DDoS / rate limit / WAF | Throttles abuse effectively with verified acceptable false-positive rate |
| Campaign cost check | Projected CDN egress, origin traffic, and cold-cache start stay within budget |
| Data/log residency | Cache locations, logs, origins/replicas, and access controls verified by Security/Legal where constrained |

## 14. Architecture Decision Process and Trade-Offs

### 14.1. Questions to Answer Before Buying or Configuring a CDN

1. **What content is shareable?** Is there any login state, tenant context, or personal data?
2. **Where are users?** Measure p95 TTFB/LCP by network, geography, and device rather than guessing from a map.
3. **How fresh must content be?** 1 second, 1 minute, or 1 day; how does staleness impact business correctness?
4. **Where are the data sources?** Object storage, app servers, multiple origins, or standby regions; is private origin access required?
5. **What is the traffic and object profile?** File sizes, geographic spread, update frequency, cache key variations.
6. **Which failures must the system survive?** PoP, origin, CDN control plane, region outages, and bad CDN rule deployments?
7. **What is the budget?** CDN egress, requests, origin traffic, logs, WAF, edge compute, operations, and DR.
8. **Who operates it?** Permissions for rule edits, certs, emergency purges, rollbacks, cache-poisoning response, and metric monitoring.

### 14.2. Comparing Three Options

| Option | Pros | Cons | Typically Fits When |
| --- | --- | --- | --- |
| **A. Direct origin** | Fewer components, simpler cache rules | Static load hits origin, high remote latency, higher origin resource use | Internal systems, few users near origin, small files |
| **B. CDN in front of static origin** | Offloads public files, clean asset rollouts, lowers global latency | Requires cache policies, invalidations, logging, and origin access controls | Public websites/SPAs/images serving distributed audiences |
| **C. CDN in front of static and eligible public APIs** | Also reduces load on public read APIs | Trickier cache keys and freshness; risk of wrong/leaked data | Public APIs with clearly approved data and TTLs |

Never enable shared caching across all APIs simply because a CDN fronts the system. Private APIs can still sit behind a CDN acting as a **reverse proxy/security ingress** with caching bypassed.

### 14.3. Sample ADR

~~~markdown
# ADR-024: Static Asset Delivery via CDN

Status: Proposed / Conditionally Approved
Owner: Architect, SRE, and Product
Date: YYYY-MM-DD

Context:
- Users span multiple network regions; site includes CSS/JS and public images.
- Origin currently serves static assets alongside transactional APIs.
- Account and payment APIs contain permission-scoped user data.

Options:
A. Direct origin.
B. CDN + private object storage for public content.
C. CDN + static + selected short-TTL public APIs.

Decision:
- Adopt B first; evaluate C later once freshness and security evidence exists.
- Content-hashed assets cached long-term; HTML revalidated.
- Private APIs BYPASS shared cache; restrict direct origin access.

Trade-offs / Risks:
- Cold cache misses still depend on origin availability.
- Misconfigured cache keys could leak data.
- CDN egress and logging introduce recurring costs.

Acceptance Criteria:
- Measured regional p95 TTFB/LCP and expected cache/origin offload.
- Two-account test confirms zero cross-user data leaks.
- Asset rollout/rollback produces zero 404s.
- TCO modeled for baseline and peak loads.

Revisit Triggers:
- Major traffic/cost shifts, demand for public API caching,
  or changes to SLOs, data policies, or staleness tolerances.
~~~

## 15. Well-Architected Review

| Pillar | CDN / Edge Review Questions |
| --- | --- |
| **Operational Excellence** | Are cache rules versioned, peer-reviewed, canary-deployed/reversible, with purge runbooks and dashboards? |
| **Security** | Are TLS, WAF, origin access, signed URLs, private data isolation, cache keys, and logs verified? |
| **Reliability** | How do origin misses behave during region loss? Are 404s, stale serving, cold caches, failover, and CDN misconfigs tested? |
| **Performance Efficiency** | Does the CDN measurably improve p95 TTFB/LCP and reduce origin saturation across real user locations? |
| **Cost Optimization** | Are CDN egress, origin fetches, logs, invalidations, and edge compute modeled across load profiles? |
| **Sustainability** | Are redundant transfers, oversized assets, unneeded storage, and idle origin capacity minimized? |

The six pillars form a **framework for questioning and gathering evidence**. They do not guarantee a CDN is always superior; an internal tool with co-located users and dynamic content may not justify the added complexity.

## 16. Common Errors and Remediations

| Error | Consequence | Remediation |
| --- | --- | --- |
| Caching all responses purely by URL | Data leaks when identical URLs serve different sessions/tenants | Classify public/private, bypass by path/auth, run two-account tests |
| Caching HTML as immutable assets | Users stay stuck on old UI referencing deleted bundles | Short HTML TTL/revalidate; content-hashed bundle URLs |
| Overwriting a bundle URL with a 1-year TTL | Users receive inconsistent mixed old/new code | Emit immutable content-hashed URLs; retain prior versions |
| Deploying HTML before assets | 404s on JS/CSS during initial page loads | Upload and verify assets before publishing HTML |
| Deleting old assets immediately after deploy | Open tabs fail to load dynamic chunks | Retention window covering transition period |
| Ignoring query params that alter content | Wrong images, languages, or results served | Include impactful parameters in cache key |
| Putting all cookies/headers into cache key | Cache fragmentation, wasted memory, hard audits | Allowlist only needed variants; bypass private routes |
| Trusting origin TTL when edge overrides exist | Freshness targets missed | Audit CDN config and inspect live response headers |
| Caching 404s for too long | Asset errors persist after files are uploaded | Short negative caching TTLs and ordered deployment tests |
| Tracking only request hit ratio | Masks heavy origin egress or poor UX | Measure byte hit ratio, TTFB/LCP, miss cost, errors, and UX |
| Treating CDN as complete origin protection | Attackers reach origin directly, bypassing WAF | Private origin/allowlists and proper origin authentication |
| Treating CDN as complete DR | Cache misses still fail if origin is lost | Backups, replicas, failover, and RTO/RPO drills |
| Looking only at lower origin bills | Overlooks CDN egress, WAF, logs, edge functions | Forecast end-to-end TCO |
| Purging entire cache before peak event | Massive MISS storm causes cache stampede | Scoped invalidations, pre-warming/origin shield as needed |

## 17. Practice Exercise

An e-commerce platform runs in a single cloud region serving customers in three countries. The site loads 15 MB of static assets on first visit (including images), JS/CSS bundles deploy twice a week, the public catalog updates every minute, and cart/checkout require authenticated sessions. The company expects a promotional campaign at five times normal traffic. SREs observe rising origin load and high p95 TTFB for distant users.

Complete the following tasks:

1. **Draw as-is and to-be architectures:** client, DNS, CDN PoP, optional shield, object storage, API gateway, application, database, and monitoring.
2. **Classify resources:** HTML, JS/CSS, images, public catalog API, cart, checkout, and private downloads; choose cache/bypass, TTL, and freshness validation.
3. **Design cache keys:** for a catalog API accepting `language` and `category` params, and an image service accepting `width` and `format`. State which parameters may be ignored and why.
4. **Write headers:** Cache-Control headers for hashed bundles, public HTML, public API, and profile API; explain the difference between `no-cache` and `no-store`.
5. **Design deployment:** specify upload order for assets, HTML publishing, testing, and rollback; handle open tabs loading old chunks.
6. **Short threat model:** identify at least three paths risking cache poisoning or data leaks; propose tests proving authorization boundaries.
7. **Resilience:** describe behavior when the origin returns 503, cache MISSes surge, or a CDN rule is misconfigured; specify what can safely be served stale.
8. **Preliminary cost estimate:** calculate client egress and origin fetches under at least two byte-hit-ratio scenarios, add CDN request/WAF/log fees, and outline live tracking.
9. **Define acceptance criteria:** regional p95 TTFB, LCP, asset 404 rate, hit ratio, origin load, two-account security verification, and campaign spend.
10. **Write an ADR:** chosen CDN option, benefits, mandatory preconditions, residual risks, and revisit triggers.

**Self-review hints:** strong solutions go beyond high hit ratios; they prove content reaches the **right user, right version, and right freshness**, survives cold caches, includes rollback plans, and demonstrates measurable gains in UX and total cost.

## 18. Pre-Production CDN Checklist

- [ ] Clearly separated cacheable content from content requiring bypass for access control, privacy, or correctness.
- [ ] Mapped client → edge → shield (if used) → origin → app/data paths, including trust boundaries and dependencies.
- [ ] Verified Cache-Control, s-maxage/max-age, ETag, Last-Modified, Vary, and CDN override rules.
- [ ] Designed cache keys covering allowed host/path/query/header variants with safe URL normalization.
- [ ] Enforced rules preventing caching of Authorization, Cookie, Set-Cookie, private HTML/APIs, or tenant data.
- [ ] Configured hashed assets as immutable; HTML/manifests have fast update and clear rollback workflows.
- [ ] Enforced uploading assets before HTML and retaining older assets long enough for open tabs/browser caches.
- [ ] Tested SPA fallbacks, MIME types, compression, fonts/CORS, image variants, and negative caching.
- [ ] Locked down direct origin access; verified TLS, WAF, rate limits, signed resources, and logging.
- [ ] Tested cross-user/cross-tenant cache leaks, cache poisoning, and invalid signed URLs.
- [ ] Tested cold caches, cache stampedes, origin 5xx, bad purges, region loss, and failover procedures.
- [ ] Instrumented request/byte hit ratios, origin offload, p95 TTFB, LCP, error rates, and cost per request.
- [ ] Established dashboards, alerts, owners, rule-change permissions, canary rollouts, and incident runbooks.
- [ ] Reconciled CDN, origin, egress, logging, WAF, and DR costs against baseline and peak budgets.
- [ ] Documented trade-offs, test evidence, residual risks, and revisit triggers in an ADR.

## Key Takeaways

A **CDN** places content distribution points along the system entry path, serving cacheable copies near users and reducing repetitive origin load. **Edge caching** is effective and safe only when you know exactly which content may be shared, build cache keys with complete variants, and align TTLs with freshness needs. For **static assets**, the most dependable strategy combines **content-hashed URLs + long-lived caching** with **revalidated or short-cached HTML/manifests** and reversible release pipelines.

A reliable cloud design must simultaneously prove **performance, correctness, security, recoverability, scalability, cost, and operability** through real metrics and deliberate testing. A CDN is one component in system entry-point architecture—it never replaces sound data, application, and DR decisions behind it.
