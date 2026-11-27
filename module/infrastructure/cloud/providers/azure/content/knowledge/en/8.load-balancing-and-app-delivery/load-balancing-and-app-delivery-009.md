# Optimizing Caching, Static Content, and Edge Latency

When users across multiple regions access an Azure application, serving all content from a single origin server can increase page load times. A webpage typically loads HTML, JavaScript, CSS, fonts, images, and API calls; not every request needs to travel the full distance from the browser to the origin.

**Edge caching** stores copies of cacheable content at edge points of presence closer to users. When content is present and still valid, the edge system can return the response directly without contacting the origin. Combined with asset size optimization, compression, modern transport protocols, and proper cache rules, this lowers perceived latency, reduces origin load, and improves responsiveness during traffic spikes.

In the CLOUD_PROVIDERS_AZURE module, this topic connects with Azure Front Door, Azure CDN, Azure Storage, Azure Static Web Apps, App Service, DNS, Web Application Firewall (WAF) security, Azure Monitor, and cost control. The goal is not "cache as much as possible," but **delivering safe-to-cache data fast while preserving the correctness and privacy of dynamic data**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain browser caches, edge caches, origins, and cache hits/misses.
2. Choose a static content delivery architecture using Azure Front Door and an appropriate storage or web service.
3. Design policies for Cache-Control, TTL, cache keys, query strings, versioning, and purging.
4. Separate public content from personalized content to prevent data leaks via shared caches.
5. Optimize images, JavaScript, CSS, and HTTP/TLS, and measure real latency by region.
6. Configure safely, handle stale caches, and monitor cache hit ratio, error rate, latency, and costs.

Prerequisites: HTTP requests/responses, DNS, HTTPS, Azure resource groups, Azure Storage, App Service, and the concepts of origin, endpoint, and route.

## 2. Where Does Edge Latency Come From?

Page load time is more than application code execution time. The main factors can be broken down as:

- **DNS resolution:** the browser looks up the domain's address.
- **Connection setup:** TCP/TLS or QUIC/HTTP/3 depending on protocol and support.
- **Round-trip time (RTT):** time for packets to travel back and forth between client, edge, and origin.
- **Origin processing time:** database queries, authentication, HTML rendering, and downstream service calls.
- **Transfer time:** resource size, bandwidth, packet loss, and compression.
- **Client render time:** parsing JavaScript, building UI, loading fonts, and decoding images.

Example: a user in Europe visits a website whose origin sits in Southeast Asia. If every image and JS file comes from the origin, each resource pays intercontinental RTT. Moving cacheable assets to an edge near the user eliminates many origin round-trips. However, a personalized API may still need the backend, so **a CDN does not guarantee eliminating all latency**.

Response time can be modeled conceptually:

~~~text
Cache hit:
  Client → Edge → Client

Cache miss:
  Client → Edge → Origin → Edge → Client
~~~

For a cache hit, the edge still processes the request and transmits bytes over the network to the user; edge does not mean zero latency. Moreover, a system with nearby edge locations yet a slow origin still delivers a poor experience whenever cache misses occur.

## 3. Multi-Layer Caching in an Azure Application

### 3.1. Browser, Edge, and Origin

~~~mermaid
flowchart LR
    U["User browser"] --> B{"Browser cache<br/>still valid?"}
    B -->|Hit| R["Use client copy"]
    B -->|Miss or revalidate needed| F["Azure Front Door / CDN Edge"]
    F --> E{"Edge cache<br/>has valid copy?"}
    E -->|Hit| C["Return data from edge"]
    E -->|Miss| O["Origin: Storage / App Service / API"]
    O -->|Response + headers| F
    C --> U
    F --> U
~~~

* Browser cache: a copy on the user's device. It can save even the request to the edge.
* Edge cache: the delivery service's shared cache, serving multiple users when content may be shared.
* Origin: the source holding or generating content, such as Azure Storage, App Service, or a backend API.
* Application/data cache: e.g., Redis or database caching to optimize backend processing. This is a different layer from CDN edge caching.

A request reaching the edge can result in a cache hit, cache miss, or revalidation/refresh depending on expiration and rules. Exact terminology and cache status headers depend on the Azure service in use.

### 3.2. Core Metrics

| Metric | Meaning | Notes |
|---|---|---|
| Cache hit ratio | Share of requests served from cache out of cacheable requests | Distinguish request hits from byte hits |
| Byte hit ratio | Share of bytes served from cache rather than fetched from origin | Useful when file sizes vary widely |
| Origin fetches | Number of times the edge had to call the origin | Revalidated responses may still send requests to origin |
| Time to first byte (TTFB) | Time until the first byte arrives from a client or probe's viewpoint | Not equivalent to full page load time |
| p50/p95/p99 latency | Response time percentiles | p95 reveals the experience of slower users |
| Origin egress | Traffic sent from the origin to the delivery service | Can impact cost |
| Error rate | 4xx/5xx rate by error type and source | Separate edge, WAF, and origin errors |
| Core Web Vitals | User experience metrics such as LCP, INP, CLS | Measure using real-user data or suitable tools |

**A high cache hit ratio does not prove a website is fast.** For example, a 99% hit ratio on oversized images still loads slowly on mobile networks. Optimize asset size, client rendering, and critical data paths too.

## 4. Choosing the Right Delivery Service in Azure

### 4.1. Common Options

| Service | Primary role | Use when |
|---|---|---|
| Azure Front Door Standard/Premium | Global HTTP(S) entry point, edge delivery, routing, caching for eligible content, and WAF per feature/tier | Websites or APIs serving multi-region users needing edge TLS, global routing, caching, and protection |
| Azure CDN | Edge content delivery per provided product and configuration | Primarily accelerating static content where an existing CDN tier fits |
| Azure Storage static website | Simple origin for static HTML/CSS/JS/images inside a Storage Account | Static sites requiring no backend server to generate pages |
| Azure Static Web Apps | Static web app hosting with integrated build/deploy, routing, and optional API integration | SPAs or static websites wanting streamlined deployment workflows |
| Azure App Service / API backend | Serving dynamic pages, business logic, and APIs | Content depends on request, user, permissions, or database |
| Azure Application Gateway | Regional HTTP(S) load balancer, with optional WAF by SKU | Application-layer distribution inside one region; does not replace a global edge network |
| Azure Load Balancer | Layer 4 load balancing | TCP/UDP connections; not a CDN or HTTP object cache |

These services are not mutually exclusive. For instance, Azure Front Door can use Storage as the origin for static assets and App Service as the origin for APIs. In other cases, Azure Static Web Apps meets delivery needs on its own without adding Front Door unless special requirements exist.

Product names, tiers, and features evolve; do not assume every SKU shares identical WAF, Private Link, caching rules, or origin options. Verify current support and pricing for your selected profile type.

### 4.2. Reference Architecture: One Domain, Multiple Content Types

Suppose an online store uses domain `www.example.com`, with static assets in Storage and APIs on App Service.

~~~mermaid
flowchart TD
    U["Users across regions"] --> D["DNS: www.example.com"]
    D --> F["Azure Front Door Standard/Premium<br/>TLS + routes + edge cache"]
    F -->|"/assets/*: public cache"| S["Azure Storage<br/>Hashed JS/CSS/images"]
    F -->|"/index.html: short TTL or revalidate"| H["HTML hosting origin"]
    F -->|"/api/*: bypass cache"| A["Azure App Service API"]
    A --> DB["Azure SQL / data services"]
    F --- W["WAF policy and monitoring"]
~~~

**Design point:** the same domain can enforce different policies by path. Immutable assets get long caches; the HTML entrypoint checks quickly for new releases; login and order APIs bypass the shared cache. Routing and caching features bind to the appropriate route/rule set in your Azure Front Door product.

When the origin is an Azure Storage static website endpoint, note that the static website endpoint serves public resources per service mechanics. Never store data requiring authentication hoping the CDN will hide the origin. If private origin access behind Front Door is required, verify the **exact private connectivity mechanism supported for that origin type and SKU** rather than assuming all static website endpoints support Private Link identically.

## 5. Designing HTTP Cache Policies

### 5.1. Reading Cache-Control Correctly

HTTP Cache-Control is the primary way an origin instructs browsers and shared caches. Common directives:

| Directive | General meaning | Usage |
|---|---|---|
| public | Allows shared caches to store the response if other conditions allow | Public static files |
| private | Response is for a single user's private cache, not shared caches | User-specific data where browser caching is still desired |
| no-store | Compliant caches must not store the response | Tokens, sensitive info, or data that must never be stored |
| no-cache | May be stored, but must revalidate with the origin before reuse | Frequently updated HTML |
| max-age=N | Duration content is considered fresh in applicable cache contexts | Choose per resource type |
| s-maxage=N | Controls freshness duration in shared caches per HTTP semantics | Use only when behavior and edge product support are clear |
| must-revalidate | Do not serve stale responses without revalidating after expiration | HTML needing fresh checks |
| immutable | Indicates content will not change during its freshness lifetime | Assets with content-hashed filenames |

**Distinguish no-cache from no-store:** `no-cache` does not strictly mean "do not store." It requires revalidation before reuse. For sensitive personal data, prefer `no-store` **and disable caching on the matching edge route** rather than relying solely on a header.

Some Front Door configurations can override cache behavior/TTL. When edge rules override origin directives, behavior can differ from standard Cache-Control semantics. Always inspect origin headers, route/rule-set settings, and the final headers delivered to clients.

### 5.2. Content Classification and TTL

There is no single optimal TTL. Start with this guiding table and tune using measurements:

| Content group | Example | Reference strategy |
|---|---|---|
| Static assets with content hashes | `app.a13f9c.js`, `style.9ab21.css` | Long cache, e.g., 1 year, since URL changes when content changes |
| Static images with versioned URLs | `banner.v5.webp`, `icon.ab42.svg` | Long cache if filenames change with content |
| HTML entrypoint | `/`, `/index.html` | Very short TTL, revalidate, or no edge cache depending on release needs |
| Public catalog JSON | `/api/public/catalog` | Short cache possible if data is non-private and cache keys are properly defined |
| Near-real-time status or metrics API | `/api/public/stock` | Very short TTL or bypass; weigh acceptable staleness |
| Personalized pages | `/account`, `/orders` | No shared cache; typically `no-store` |
| Login, tokens, and checkout | `/auth/*`, `/checkout/*` | Bypass edge cache, `no-store`, dedicated security controls |
| Unpublished previews | `/preview/*` | Never cache publicly if access-restricted or confidential |

The durations in this table are design guidelines, not Azure Front Door defaults. Resources with unversioned URLs should not receive long TTLs if urgent updates may be needed without reliable browser invalidation.

### 5.3. Header Example for Immutable Files

Suppose a build pipeline produces `app.a13f9c.js`. An appropriate response is:

~~~http
HTTP/1.1 200 OK
Content-Type: text/javascript; charset=utf-8
Cache-Control: public, max-age=31536000, immutable
ETag: "build-a13f9c"
~~~

When JavaScript changes, the pipeline publishes `app.b41d8e.js` rather than overwriting `app.a13f9c.js`. With a new URL, browsers and edges fetch the new version without purging all old caches.

The point of content hashing is **putting the version in the URL**. If you reuse the same URL and overwrite origin content, a long `immutable` header causes update failures.

### 5.4. Header Example for HTML and Private Data

The HTML entrypoint must pick up new deployments quickly:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Cache-Control: no-cache, max-age=0, must-revalidate
ETag: "index-build-205"
~~~

If an edge route can cache HTML, configure it to honor revalidation or bypass per deployment policy. Purging at the edge does not clear still-fresh browser caches if browsers previously received a long TTL.

For responses containing private account data:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store
~~~

For such endpoints, do not rely on `no-store` alone; also disable shared caching in the route configuration. Never put user data, sessions, or permissions into a shared cache merely because the endpoint uses GET.

### 5.5. Cache Keys and Query Strings

The **cache key** determines whether two requests can share a cached copy. It can depend on path, query string, and other product-supported factors. Misconfigured query-string caching causes two opposite failures:

- **Cache fragmentation:** two URLs returning identical content are stored as separate cache entries, lowering hit ratio.
- **Cache collision/poisoning:** two requests needing different responses share one entry, serving wrong content or leaking data.

Example:

~~~text
/assets/logo.svg?utm_source=email
/assets/logo.svg?utm_source=search

/api/public/catalog?lang=vi
/api/public/catalog?lang=en
~~~

If `utm_source` does not alter the response, configure the edge to ignore it in the cache key where supported. Conversely, `lang` changes the content and must remain part of the key—or move into separate paths like `/vi/catalog` and `/en/catalog`.

Query-string modes may include full query string, ignore all, or include/ignore specified parameters depending on SKU and setup. Never assume all parameters are harmless. Be extra careful with queries containing tokens, signed URLs, access keys, or user IDs: you cannot fix those safely with a blanket "ignore all query strings" rule.

**Headers and cookies:** do not assume the edge automatically segments caches by `Cookie`, `Authorization`, `Accept-Language`, or every `Vary` header. Header-based cache key behavior depends on product and configuration; check docs before caching responses that vary by user, language, or device. The safest rule for authenticated data is to bypass the shared cache.

### 5.6. ETag, Last-Modified, and Revalidation

ETag and Last-Modified let clients or caches verify a copy is still current without re-downloading the full payload. Example:

~~~http
GET /index.html HTTP/1.1
Host: www.example.com
If-None-Match: "index-build-205"
~~~

If unchanged and the condition matches, the origin can reply:

~~~http
HTTP/1.1 304 Not Modified
ETag: "index-build-205"
~~~

A 304 saves payload transfer, yet still incurs a round-trip for validation. For fingerprinted, immutable assets, the goal is avoiding even unnecessary revalidation requests while fresh.

## 6. Static Content: Optimizing Before Pushing to CDN

A CDN cannot fully compensate for oversized assets or heavy JavaScript execution in the browser. Build pipelines should optimize at the source.

### 6.1. JavaScript, CSS, and HTML

- Minify JS/CSS/HTML in the build pipeline where appropriate.
- Code-split bundles by route/feature; load only modules needed for the current page.
- Use tree shaking and eliminate unused dependencies.
- Defer non-critical scripts, using controlled prefetch/preload only for truly essential resources.
- Avoid slowing page loads with unnecessary third-party scripts, fonts, or widgets.
- Include content hashes in asset filenames to enable long TTLs.
- Always emit accurate `Content-Type` headers; wrong MIME types can make browsers reject files even when the edge returns HTTP 200.

Measure downloaded bytes and JS execution time in the browser. A JS file served super fast from the edge can still hurt INP if it blocks the main thread for too long.

### 6.2. Images and Fonts

- Use WebP/AVIF where appropriate with browser fallbacks; vector formats like SVG fit icons and suitable graphics.
- Generate multiple image sizes and use `srcset`/`sizes` so small devices do not download huge desktop images.
- Lazy-load below-the-fold images; avoid accidentally lazy-loading the main hero image.
- Prioritize images affecting Largest Contentful Paint (LCP) and set explicit dimensions to prevent layout shifts.
- Subset fonts, reduce weight/style variants, and pick an appropriate `font-display`.
- Version/hash image filenames if you want long cache lifetimes.

Responsive image example:

~~~html
<img
  src="/assets/product-640.webp"
  srcset="/assets/product-320.webp 320w, /assets/product-640.webp 640w, /assets/product-960.webp 960w"
  sizes="(max-width: 640px) 100vw, 640px"
  width="640"
  height="480"
  alt="Product illustration"
/>
~~~

Image URLs in the example must exist and come from your build/media pipeline. Image optimization must balance visual quality rather than shrinking file sizes at any cost.

### 6.3. Compressing Text Content

Gzip and Brotli typically shrink JS, CSS, JSON, and HTML payloads; they are poor choices for re-compressing already-compressed JPEG/WebP/AVIF images. Azure Front Door can support content compression per product mechanics and settings, but verify supported MIME types, file sizes, and request conditions.

Verify with curl:

~~~bash
curl -sS -D - -o /dev/null \
  -H "Accept-Encoding: br,gzip" \
  https://www.example.com/assets/app.a13f9c.js
~~~

Inspect `Content-Encoding`, `Vary`, `Content-Type`, and response size, and compare against requests without compression headers. `Content-Encoding: br` is valid only when the payload is actually Brotli-encoded. Never add a compression header manually if neither origin nor edge actually compresses the body.

### 6.4. Cutting Unnecessary Round-Trips

- Enable HTTPS, HTTP/2, or HTTP/3 where supported by edge and clients and configured properly.
- Leverage connection reuse and avoid multi-hop redirect chains.
- Align DNS, canonical hostnames, and HTTP→HTTPS redirects so no loops occur.
- Use a clean domain/static-asset strategy; too many hostnames add DNS/TLS handshake overhead.
- Use preconnect or preload selectively, avoiding over-preloading that competes for bandwidth with critical content.

Do not judge performance merely by pinging an IP or measuring latency from a server in the same region as the origin. Measure from locations and devices representative of real users.

## 7. Workflow for Configuring Azure Front Door with Caching

### Step 1. Classify URLs by Cacheability

Build a route table before creating the profile. Example:

| Path | Origin | Edge caching | Notes |
|---|---|---|---|
| /assets/* | Azure Storage | Enabled, long TTL for hashed URLs | Verify Content-Type and file versioning |
| /images/* | Azure Storage | Enabled for public images with versioned URLs | Optimize dimensions and formats |
| /index.html, / | Web/static origin | Short TTL or bypass | Pick up new entrypoints fast |
| /api/public/catalog | App Service | Consider short cache only after testing | Design cache key for language/options |
| /api/orders/* | App Service | Disabled | User and transaction data |
| /auth/* | App Service | Disabled | Tokens/sessions and authentication |
| /health | App Service | Usually disabled for real-time health checks | Never let caching hide an unhealthy origin |

For SPAs, paths like `/products/123` may need rewriting to `index.html` **at the origin or an appropriate route**, without accidentally rewriting `/api/` or missing `.js` files to HTML with HTTP 200. Test deep links and real 404 responses thoroughly.

### Step 2. Prepare Origins

For static assets on Azure Storage:

1. Create an appropriate Storage Account and enable static website hosting if using that feature.
2. Upload optimized build outputs to the static website container, keeping directory structure consistent.
3. Set `Content-Type` and `Cache-Control` metadata on objects per asset policy.
4. Verify origin URLs, 200/404 statuses, TLS, and SPA fallback behavior if used.
5. Control who can upload or edit objects; never place Storage Account keys in app source code.

With App Service as an origin, optimize health endpoints, TLS, API latency, and capacity to survive edge cache misses or post-purge bursts. An under-provisioned origin can still overload during a cold-cache event.

**Origin security:** Front Door Premium offers Private Link integration for supported origin types. Verify supported origins, endpoints, and SKU requirements before selecting it. For public origins, apply access restrictions, token protection, header checks, and WAF. Never treat placing Front Door in front as sufficient on its own to stop direct origin calls.

### Step 3. Create Front Door Profile, Endpoint, and Origin Group

In the Azure Portal or IaC, a typical sequence is:

1. Select Azure Front Door Standard/Premium based on WAF, origin connectivity, routing, and cost needs.
2. Create the profile in a subscription/resource group aligned with governance.
3. Create an endpoint and origin group for static origins; set protocol, host header, port, and health probe.
4. Create a separate origin group for APIs if different routing, priority, or health policies are needed.
5. Attach real origins (Storage, App Service, or appropriate service) and verify TLS/hostnames.
6. Create routes linking domain + path patterns to each origin group.
7. Configure route caching where allowed, query-string strategy, compression, and Rules Engine/rule sets if supported.
8. Configure custom domains, DNS, HTTPS certificates, and redirects per Front Door guidance.
9. Integrate WAF policies, diagnostic settings, and Azure Monitor alerts.
10. Test on a staging domain or test scope before shifting production traffic.

Conceptual route design example, **not Azure API YAML**:

~~~yaml
routes:
  - name: static-assets
    patterns: ["/assets/*"]
    originGroup: storage-static
    cache:
      enabled: true
      ttlPolicy: "long-for-fingerprinted-assets"
      queryString: "ignore-allowlisted-tracking-parameters"
      compression: true
  - name: app-html
    patterns: ["/", "/index.html"]
    originGroup: web-origin
    cache:
      enabled: false
  - name: api
    patterns: ["/api/*", "/auth/*"]
    originGroup: app-api
    cache:
      enabled: false
~~~

Fields above illustrate the mental model and cannot be fed directly into Bicep or Azure CLI. Real configs follow the service schema. In particular, check route/rule precedence so sensitive paths never accidentally fall into a shared caching route.

### Step 4. Verify Domain and HTTPS

A production domain needs valid HTTPS from client to edge; edge-to-origin connections must also be configured securely. For custom domains, verify DNS records, certificates, hostname validation, and redirects.

If an origin requires a specific Host header, set the exact origin host header to avoid 404s, certificate errors, or virtual-host mismatches. Never disable origin certificate validation just as a quick workaround for connection errors.

### Step 5. Configure Caching Per Content Group

- Fingerprinted assets: origin emits `Cache-Control: public`, long `max-age`, `immutable`; edge route cache enabled.
- HTML: configure revalidation/bypass per website capabilities and requirements.
- Public APIs: enable caching only after agreeing on what can be shared, which queries alter responses, and how invalidation works.
- Private APIs: caching disabled on the route; origin emits `no-store`/`private`.
- Errors: review how the product handles error responses and negative caching; avoid keeping stale 404/500s cached long after a fix.

With multiple origins, synchronize header policies across deployments; one origin sending `no-store` while another sends `public` for the same path creates unpredictable behavior.

## 8. Deploying New Releases: Versioning First, Purging Second

### 8.1. Why Should Purging Not Be the Default Strategy?

Purging instructs the edge service to evict cached entries for specified paths. It is useful when stale content must be invalidated, yet it has limits:

- Propagation across all edge POPs can take time.
- Edge purging **does not evict still-fresh copies in users' browsers**.
- Broad purges trigger a wave of cache misses, spiking origin load and egress costs.
- A file published under an old URL can still be fetched if that URL still exists and policies allow it.

Therefore, immutable assets should use hashed filenames. Reserve purges for HTML entrypoints, manifest files, or unversioned URLs as needed.

### 8.2. Safe SPA Deployment Workflow

Suppose a new release updates `index.html` to point to `app.b41d8e.js` instead of `app.a13f9c.js`:

1. Build bundles and generate content-hashed filenames.
2. Upload **new versioned assets first** before updating HTML. Referenced files must already exist before the new HTML is served.
3. Verify status, MIME types, hashes/sizes, and reachability of new assets via origin/edge.
4. Publish the new HTML entrypoint with short cache lifetime or revalidation.
5. If needed, purge specifically `/index.html` and unversioned paths.
6. Run smoke tests from multiple locations across fresh browsers and browsers holding old caches.
7. Retain hashed assets from the previous release at least as long as users might still hold old HTML.
8. Monitor JS/CSS 404s, cache miss ratios, p95 TTFB, and user feedback.

**Rollback:** reverting HTML to the previous version is safe only if assets referenced by the old HTML are still present. Deleting old assets immediately after every deploy breaks open tabs and pages served from browser caches.

### 8.3. When Is an Emergency Purge Needed?

Purging may be required when public content is wrong, info must be removed, or an unversioned asset was cached too long. However, if sensitive data was ever publicly exposed through a CDN, purging does not prove nobody already downloaded it. Trigger incident response, revoke access/URLs, audit logs, lock down the origin, and assess data-breach obligations.

## 9. Measuring and Validating Cache Behavior

### 9.1. Inspecting Response Headers with curl

Send two consecutive requests to a static asset on a test domain:

~~~bash
curl -sS -D - -o /dev/null \
  https://www.example.com/assets/app.a13f9c.js

curl -sS -D - -o /dev/null \
  https://www.example.com/assets/app.a13f9c.js
~~~

Observe:

- HTTP status and redirects.
- `Cache-Control`, `Expires`, `ETag`, `Last-Modified`.
- `Age`, `Via`, `X-Cache`, or other diagnostic headers **if emitted by the active service**.
- `Content-Type`, `Content-Encoding`, and `Vary`.
- Differences between the first and second request.

Do not assume the first request is always a miss and the second is always a hit: the edge cache may already be warm from other traffic, or HEAD vs. GET, different edge POPs, TTLs, or request headers may change behavior. Confirm cache status through Front Door diagnostics/metrics rather than a single header alone.

Measure TTFB with curl:

~~~bash
curl -sS -o /dev/null \
  -w "status=%{http_code} dns=%{time_namelookup}s connect=%{time_connect}s tls=%{time_appconnect}s ttfb=%{time_starttransfer}s total=%{time_total}s\n" \
  https://www.example.com/assets/app.a13f9c.js
~~~

Measured numbers reflect only **the machine running curl**, not users in all regions. Results vary with DNS, cold/warm caches, local network conditions, TLS session reuse, and device load.

### 9.2. Inspecting Front Door Config with Azure CLI

Read-only command examples for Front Door Standard/Premium:

~~~bash
az account show --output table

az afd endpoint show \
  --resource-group rg-edge-prod \
  --profile-name afd-shop-prod \
  --endpoint-name ep-shop-prod \
  --output json

az afd route list \
  --resource-group rg-edge-prod \
  --profile-name afd-shop-prod \
  --endpoint-name ep-shop-prod \
  --output table

az afd origin-group list \
  --resource-group rg-edge-prod \
  --profile-name afd-shop-prod \
  --output table
~~~

Substitute your environment's resource names. Depending on Azure CLI version, an extension/module may be required. Listing configuration does not prove data is caching properly; combine it with live request tests and log inspection.

### 9.3. Azure Monitor and Access Logs

Enable appropriate diagnostic settings, routing logs/metrics to your organization's chosen analytics sink. Monitor:

1. Request counts and bytes served from edge by domain/route.
2. Cache hits and cache misses, plus byte hit ratio if supported by metrics.
3. Origin latency, origin request counts, and origin group health.
4. HTTP 4xx/5xx, WAF blocks, and TLS/origin errors.
5. p50/p95/p99 latency from clients or synthetic/RUM tools.
6. Breakdown by geography, device, and network.
7. Edge delivery, origin egress, and log ingestion costs.

Example KQL when logs flow into `AzureDiagnostics` under the Front Door Access Log category:

~~~kusto
AzureDiagnostics
| where TimeGenerated > ago(1h)
| where Category == "FrontDoorAccessLog"
| summarize Requests = count() by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
~~~

Using resource-specific tables may store data in different tables and schemas. Check available tables and columns in your workspace before adapting queries; never treat an empty query result as proof of zero traffic if diagnostic settings are disabled or logs have not ingested yet.

### 9.4. Benchmarking Before and After Enabling Caching

Compare two states against the same content and target user base:

| Metric | Before optimization | After optimization | Interpretation |
|---|---|---|---|
| Median/p95 TTFB in Vietnam | Measured | Measured | Did edge delivery help domestic users? |
| Median/p95 TTFB in Europe | Measured | Measured | How much was origin distance reduced? |
| LCP and INP on mobile | Measured | Measured | Are JS/images still bottlenecks? |
| Cache hit ratio / byte hit | Measured | Measured | Are TTLs and cache keys sensible? |
| Origin request volume | Measured | Measured | Did origin load drop, or did we only add a hop? |
| Error rate (4xx/5xx) | Measured | Measured | Did routes/WAF/caching introduce new errors? |
| Traffic-based cost | Measured | Measured | Do origin savings offset edge costs? |

Measure over a representative window covering cold/warm caches, peak traffic, multiple locations, and asset releases. Use synthetic monitoring and Real User Monitoring (RUM) instead of drawing conclusions solely from the engineering team's office network.

## 10. Estimating Cache Impact on Origin Traffic

Suppose over a period users make 1,000,000 requests for an asset averaging 100 KB. This is an **illustrative example**, not Azure measurements or pricing:

~~~text
Total data delivered to clients (estimate):
  1,000,000 × 100 KB ≈ 100 GB

If 80% of requests hit edge cache:
  Requests needing origin fetch ≈ 20% × 1,000,000 = 200,000
  Data sent by origin (estimate) ≈ 20 GB

Data offloaded from origin (estimate) ≈ 80 GB
~~~

This rough math omits headers, revalidation, compression, range requests, varying asset sizes, and repeated cold fetches across separate edge POPs. **Request hit ratio does not necessarily equal byte hit ratio**, so verify with real telemetry.

Costs do not drop by 80% automatically, because Front Door/CDN charges for edge egress, requests, and other dimensions; origins may incur egress, Storage transactions, compute, and log ingestion. When comparing economics, model budgets by service, geographic traffic, and actual pricing tiers.

## 11. Security and Reliability at the Edge

### 11.1. Shared Cache Is a Critical Data Boundary

The worst risk of edge caching is not stale content—it is **serving User A's data to User B**. Dangerous mistakes:

- Caching a `GET /api/orders` JSON endpoint that varies by cookie or bearer token.
- Ignoring query strings even when queries carry language, tenant ID, variant, or access scope.
- Caching responses containing `Set-Cookie` or auth data without checking service caching behavior.
- Broad wildcard routes like `/*` with caching enabled accidentally covering `/auth/*` and `/checkout/*`.
- Sharing a single cache key across hosts or variants that must stay isolated.

Safe starting principle: **cache only public content with well-defined variants that can be shared across clients**. Private APIs and transactions should bypass edge caching completely. Origin `no-store`/`private` headers are an extra safeguard, not a substitute for route config.

### 11.2. TLS, WAF, and Origin Access

- Enforce HTTPS on both client→edge and edge→origin legs.
- Configure valid domains/certificates; avoid disabling origin certificate validation.
- Apply an appropriate WAF policy to filter malicious traffic; test for false positives before broad blocking.
- Restrict direct origin access where supported by service and SKU; validate origin requests reliably.
- Never put secret keys, connection strings, or access tokens inside SPA bundles or public Storage files.
- Enforce least-privilege RBAC for teams managing Front Door, Storage, and deployment pipelines.
- Enable needed access logs while avoiding logging sensitive user data unnecessarily.

WAF does not replace application security, and a CDN does not replace backups/recovery. An outage in the origin, DNS, routing, or rule config can still affect all users.

### 11.3. Availability and Origin Failover

Front Door can route across multiple origins, run health checks, and select origins per configured policies. For systems requiring HA, verify:

1. At least two suitable origins exist if redundancy is needed.
2. Health probes reflect real application health rather than returning HTTP 200 from a static page.
3. Static assets across origins are synchronized or follow identical versioning.
4. Cache rules do not retain 5xx errors for too long or mask origin failures.
5. Switching origins does not break tenants, cookies, DNS, or database paths.
6. Failover and rollback are rehearsed through change procedures.

Edge caches can soften brief origin blips, yet you should never assume all assets remain servable if the origin loses connectivity, since entries may expire or be uncached at specific edge POPs.

## 12. Real-World Scenario: Multi-Region Online Store

An Azure e-commerce team handles three kinds of requests:

- Storefront and JS/CSS/image files published from CI/CD pipelines.
- A public product catalog changing several times per day.
- User-specific shopping carts, payment details, and orders.

Initially, all requests hit App Service in one region. Distant users saw high TTFB for assets, and every page load sent many requests to App Service.

### Optimized Design

**Group 1: Static assets.** Pipeline builds `app.<hash>.js` and `style.<hash>.css`, pre-compresses where suitable, optimizes WebP/AVIF images, and uploads to Storage. Front Door route `/assets/*` enables long caching; browsers keep assets immutable.

**Group 2: HTML entrypoint.** Front Door uses a very short TTL or disables caching so users pick up new version manifests quickly. The pipeline uploads assets before swapping HTML, purging only the entrypoint if needed.

**Group 3: Public APIs.** Short catalog caching can be considered if the business accepts bounded staleness. Variants by language, currency, region, and query string must be defined; when uncertain, bypass initially.

**Group 4: Private APIs.** Orders, carts, checkout, and auth always bypass edge caching. The app emits `no-store` and continues authenticating users and enforcing backend authorization.

After rollout, the team compares p95 TTFB by country, mobile LCP, cache/byte hit ratios, 4xx/5xx rates, origin traffic, and cost. If hit ratio is high yet LCP fails to improve, investigate hero images, render-blocking JS, and third-party scripts instead of blindly raising TTLs.

### Handling a Stale Content Incident

After a release, some browsers still receive the old `index.html` while old assets were already deleted. Incident response:

1. Inspect HTML response headers and edge cache behavior.
2. Determine whether affected users have fresh browser caches or stale edge caches.
3. Restore required old assets if feasible so open tabs keep working.
4. Enforce HTML revalidation policy and purge the exact entrypoint path at the edge if needed.
5. Fix the pipeline: upload new assets first and retain old assets across a transition window.
6. Verify across multiple regions and browser types; document root causes in the runbook.

This addresses the asset lifecycle root cause rather than repeatedly running full cache purges.

## 13. Common Errors and Diagnostics

| Symptom | Possible cause | What to check |
|---|---|---|
| Low hit ratio despite high traffic | Tracking queries fragmenting cache keys, too-short TTLs, uncacheable responses | Check cache-key strategy, Cache-Control, hit/miss logs |
| Users receive stale content | Browser/edge TTL too long, unversioned files, purge still propagating | Compare URLs, Age/headers, manifests, deploy steps |
| CSS/JS returns HTTP 200 yet site breaks | Origin serves wrong MIME type, SPA rewrite returns HTML instead of JS | Check Content-Type, response body, and fallback rules |
| API returns another user's data | Overly broad cache route, cache key missing variants, private response cached | Disable route caching immediately, trigger security incident review |
| Front Door returns 502/504 | Origin unreachable, wrong health/TLS/host header, timeout | Check origin health, DNS, certificates, host header, backend logs |
| Requests return 403 | WAF, Storage policy, origin auth, or app authorization | Separate WAF logs, origin logs, and access rules |
| p95 latency stays high | Uncached dynamic APIs, slow origin, large assets, heavy JS rendering | Use synthetic + RUM data, inspect waterfalls and backend traces |
| One region fast, another slow | Different cache warmth, distant origin fetches, last-mile networks | Check measurement locations, routes, regional cache metrics |
| Still seeing old version after purge | Fresh browser cache, service worker, intermediate proxy | Inspect DevTools, service workers, Cache-Control, and URLs |
| Compression not working | Ineligible MIME/size, unsupported client, disabled in config | Compare Accept-Encoding, Content-Encoding, and payloads |
| Unexpected cost spike | Higher edge traffic/egress, frequent purges, cache misses, log ingestion | Check Cost Management, hit/byte hit, origin fetches |

For websites using service workers or PWAs, inspect the service worker cache as well. An edge purge does not directly clear caches managed by service worker JavaScript. PWA updates require dedicated versioning and activation flows.

## 14. Deployment and Testing Checklist

### Before Enabling Edge Caching

1. Classify public vs. private paths and list routes to cache or bypass.
2. Inspect `Cache-Control`, `Content-Type`, `ETag`, and user/cookie usage.
3. Apply content hashes to long-lived assets; define HTML TTL.
4. Verify origin reachability, TLS, host headers, DNS, and access controls.
5. Define query-string strategy and valid variants.
6. Configure WAF, logging, and rollback procedures.
7. Capture baseline metrics from at least one region near and one far from the origin.

### During Testing

1. Request the same asset twice; inspect headers and cache status in logs/metrics.
2. Test URLs with tracking queries and queries that alter content.
3. Verify `/auth`, `/api/orders`, and personalized responses **are never shared across users**.
4. Test browser refreshes, ETag/304, cold/warm caches, and deploying a new release.
5. Verify HTTP statuses, MIME types, compression, CSS/JS, SPA deep links, 404s, and custom domains.
6. Verify WAF false positives, origin health, and direct origin access controls.
7. Measure p95 TTFB, LCP, errors, and origin requests by region before and after changes.

### After Release

1. Monitor cache hits, origin load, 4xx/5xx rates, WAF blocks, and costs.
2. Set alerts for origin health, error spikes, and hit-ratio drops.
3. Verify correctness after every release, especially HTML and asset mappings.
4. Maintain runbooks for targeted purges, rollbacks, and data-leak incidents.
5. Revisit TTLs and cache keys whenever adding languages, tenants, or content variants.

## 15. Self-Check Questions

1. **How does a cache hit differ from a cache miss?** A hit serves a still-valid copy from the cache layer; a miss fetches data from the origin or downstream layer.
2. **Why shouldn't an unversioned `index.html` get a one-year TTL?** Browsers and edges may keep the old entrypoint for a long time, preventing users from receiving new releases.
3. **File `app.a13f9c.js` has a long TTL; what should you do when code changes?** Publish a new URL with a new content hash instead of overwriting the old file.
4. **Does `no-cache` mean the same as `no-store`?** No; `no-cache` requires revalidation before reuse, whereas `no-store` forbids storing the response.
5. **Can `/api/orders` using session cookies be cached at the edge?** It should not. Private responses need shared caching disabled and access control enforced in the application.
6. **If you ignore all query strings, what error can occur?** Requests differing by language, tenant, or data variant may share the wrong response.
7. **Does purging Front Door clear browser caches?** No. Browser caches and service workers follow their own lifecycles.
8. **Why doesn't a high hit ratio guarantee good LCP?** The page might still download oversized images or execute heavy JS; LCP reflects rendering experience.
9. **How does Azure Front Door differ from Application Gateway?** Front Door delivers HTTP(S) at the global edge; Application Gateway is primarily a regional application-layer gateway.
10. **How is ETag useful?** It enables revalidation and can avoid re-downloading unchanged payloads.
11. **Can one caching route for `/assets/*` also cover `/auth/*`?** No. Auth routes must stay separated, bypass caching, and enforce dedicated protection.
12. **If enabling caching lowers origin costs, does total cost automatically drop?** No. There are edge delivery, request, egress, WAF, logging, and other fees to account for.
13. **What should you measure to prove optimization worked?** Regional TTFB/p95, LCP/INP, hit/byte hit ratios, origin requests, error rates, and actual costs.

## 16. References

- [Azure Front Door documentation](https://learn.microsoft.com/azure/frontdoor/) — global application delivery, caching, routing, and security.
- [Caching with Azure Front Door](https://learn.microsoft.com/azure/frontdoor/front-door-caching) — cache behavior, TTLs, and configuration principles.
- [Azure Front Door Standard/Premium](https://learn.microsoft.com/azure/frontdoor/standard-premium/overview) — tier and feature overview.
- [Azure Storage static website hosting](https://learn.microsoft.com/azure/storage/blobs/storage-blob-static-website) — hosting static HTML/CSS/JS/images.
- [Azure Static Web Apps](https://learn.microsoft.com/azure/static-web-apps/overview) — hosting and deploying static web apps.
- [Azure Monitor documentation](https://learn.microsoft.com/azure/azure-monitor/) — metrics, diagnostic settings, and alerting.
- [HTTP caching (MDN)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching) — semantics of Cache-Control, ETag, and revalidation.
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/) — operational cost analysis.

In real deployments, verify exact Front Door/CDN product capabilities, SKUs, route caching, rule sets, origin access, and feature limits at implementation time. The core rule is: **cache long for public immutable assets, update entrypoints quickly, never use shared caches for private data, and decide based on real-user telemetry**.
