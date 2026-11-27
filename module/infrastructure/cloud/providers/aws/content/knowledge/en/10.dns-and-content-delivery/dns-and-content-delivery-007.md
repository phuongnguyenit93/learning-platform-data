# Cache Keys, Cache Policies, and Invalidation

> **Chapter:** DNS and Content Delivery  
> **Module:** CLOUD_PROVIDERS_AWS — exploring Region/AZ infrastructure, IAM, VPC, compute, storage, databases, integration, and serverless; practicing service selection, secure application deployment, monitoring, recovery, and cost control.

## Learning Objectives

When users across multiple regions access images, JavaScript, video, or APIs, **Amazon CloudFront** delivers content through its network of edge locations and reduces requests sent to origins such as **Amazon S3**, an **Application Load Balancer**, or HTTP servers. These benefits only hold sustainably when the cache stores the right content variants, expires appropriately, and updates safely after deployments.

Three core concepts:

- **Cache key:** the set of attributes distinguishing cached responses; determines whether two requests can share a single cached object.
- **Cache policy:** configuration attached to a CloudFront cache behavior defining **TTLs** and which request values are included in the cache key.
- **Invalidation:** a request telling CloudFront to purge stale cached entries by **path** so subsequent requests re-fetch content; does not delete objects at the origin.

After this lesson, you will be able to:

1. Explain cache hits/misses, origins, cache behaviors, and cache keys in CloudFront.
2. Select the right query strings, HTTP headers, and cookies to include in a cache key.
3. Distinguish **cache policies**, **origin request policies**, and **response headers policies**.
4. Predict the effects of Minimum/Default/Maximum TTL, `Cache-Control`, `Expires`, and error caching.
5. Design caching for HTML, hashed static assets, image variants, and private APIs.
6. Run and verify CloudFront invalidations via the AWS CLI, and know when to use **file versioning** instead.
7. Monitor cache hit ratios, errors, latency, and costs; diagnose stale content or cross-user cache leaks.

## 1. CloudFront Caching in AWS Architecture

CloudFront is a **content delivery network (CDN)** that receives user requests at an appropriate edge location. When CloudFront holds a valid cached response, it serves it directly from the edge; if missing or needing refresh, CloudFront contacts the origin or intermediate CloudFront cache layers as configured.

~~~mermaid
flowchart TD
    U[User / Browser] --> D[DNS: www.example.com]
    D --> C[Amazon CloudFront distribution]
    C --> B{Cache behavior by URL path}
    B -->|/assets/*| P1[Cache policy: static assets]
    B -->|/api/*| P2[Cache policy: API]
    B -->|default *| P3[Cache policy: HTML]
    P1 --> K1[Cache key + TTL]
    P2 --> K2[Cache key + TTL]
    P3 --> K3[Cache key + TTL]
    K1 --> H{Cache hit?}
    K2 --> H
    K3 --> H
    H -->|Yes, valid| R[Return content from cache]
    H -->|No or expired| O[Origin: S3 / ALB / HTTP]
    O --> R
~~~

### 1.1. Components to Know

| Component | Responsibility | Example |
|---|---|---|
| **Distribution** | CloudFront configuration serving domains, origins, and behaviors | `d123example.cloudfront.net` or `www.example.com` |
| **Origin** | Actual content source | Private S3 bucket or ALB |
| **Cache behavior** | Selects origin and policies based on path pattern | `/assets/*`, `/api/*`, default `*` |
| **Cache key** | Identifies reusable content variants | Path + query `lang=vi` + header if needed |
| **Cache policy** | How the cache key is built and TTL bounds | Managed policy or custom policy |
| **Origin request policy** | Forwards extra info to the origin | Specific headers, cookies, queries excluded from cache key |
| **Response headers policy** | Adds/modifies headers returned to viewers | Security headers, CORS, and custom headers |
| **Invalidation** | Requests purging cached entries by path | `/index.html`, `/assets/*` |

**DNS does not determine the cache key.** Route 53 (or another DNS provider) points the domain to CloudFront, whereas the logic deciding which requests share a cache lives in cache behaviors and policies. Custom domains with HTTPS also require DNS records and matching TLS certificates per CloudFront requirements.

### 1.2. Cache Hit, Miss, and Origin Load

- **Hit:** a matching, valid cached object is available and served from cache.
- **Miss:** no matching cached object exists or rules require querying the origin.
- **Refresh/validation:** a cached object may need revalidation with the origin, e.g., via `ETag` and conditional requests, depending on origin type and headers.
- **Error caching:** CloudFront can cache certain error responses for a separate duration; inspect this when the origin is fixed yet clients still see errors.

A higher **cache hit ratio** reduces origin load and latency, but **it is not the highest goal**: serving wrong data or caching responses containing personal information is far worse than a cache miss.

## 2. Cache Keys: Same Content or Two Distinct Variants?

### 2.1. Mental Model

A cache key can be understood conceptually as:

~~~text
Cache key ≈ URL path
          + selected query parameters
          + selected request headers
          + selected cookies
          + CloudFront-managed normalization/variant factors
~~~

CloudFront manages caches per distribution and access behavior; the formula above is **illustrative only**, not the internal key format. Never assume every header, query parameter, or cookie is included in the cache key by default.

Example:

~~~http
GET /catalog?page=2&sort=price HTTP/1.1
Host: shop.example.com
Accept-Language: vi-VN
Cookie: theme=dark; session_id=abc123
~~~

Suppose the catalog HTML genuinely depends on:

- `page` and `sort`;
- language normalized by the system to `vi` or `en`;
- `theme` if HTML renders differently per theme.

A **good cache key** only needs to capture values that can **alter the cacheable response**. `session_id` only tracks login state and should not enter a public page's cache key if content does not depend on the session. Conversely, **never omit session/user identity** if the origin actually returns per-user private data; the safer choice is **not caching personalized responses** in a shared CDN.

### 2.2. Missing Components: Risk of Serving Wrong Content

Suppose the origin returns:

~~~text
GET /products/123?lang=vi -> "Giá bán"
GET /products/123?lang=en -> "Price"
~~~

If the cache key includes only `/products/123` and **omits `lang`**, CloudFront may cache the Vietnamese version and serve it to an English request. This is a **variant cache collision**.

With personal data, the consequence is far worse: a URL-only cache key while the origin varies responses by cookie/`Authorization` can leak one user's data to another. Therefore, **cache only public responses or responses with carefully designed and tested variant isolation**.

### 2.3. Extra Components: Lowering the Cache Hit Ratio

Suppose public content has only two language variants, yet the cache key includes:

- The `User-Agent` header with countless values;
- A per-user `session_id` cookie;
- Marketing query parameters like `utm_source`, `utm_campaign`;
- Raw `Accept-Language` headers with many complex combinations.

Nearly every request generates a separate key, multiplying cached objects, slashing hit ratio, and driving load back to the origin.

An intuitive calculation:

~~~text
4 pages × 3 languages × 2 image sizes × 2 themes
= 48 variants before counting cookies or other headers
~~~

Adding a cookie with thousands of random values explodes variant count even though the content is unchanged. **Rule:** include in the key only attributes that actually change the cacheable response.

### 2.4. Query Strings in the Cache Key

CloudFront cache policies support query string modes such as:

| Configuration Mode | Meaning | When Appropriate |
|---|---|---|
| **None** | Exclude all query strings from key | Static assets unaffected by queries |
| **All** | Include all query strings in key | Only when every parameter changes the response |
| **Include specified** | Include only named parameters | E.g., `lang`, `page`, `size` |
| **All except specified** | Include all parameters except an exclusion list | When most parameters matter except tracking parameters |

For example, keep only `lang` and `page`, excluding `utm_*` parameters that do not alter content. **Whitelist** modes match by *parameter name*; they do not automatically normalize arbitrary values into safe sets.

Points to note:

1. CloudFront can treat **query parameter order** as distinct in cache entries. For instance, `?a=1&b=2` vs. `?b=2&a=1` can lower hit ratios even if the origin treats them identically; normalize URLs at the app/edge layer if needed.
2. Query parameter names and values can be case-sensitive; `lang=vi` and `Lang=vi` are not automatically identical.
3. Query strings **are not part of the path pattern** selecting a behavior; `/api/*` routing and cache-key query selection are two separate steps.
4. Never put access tokens, passwords, or sensitive data in URLs to solve caching; URLs appear in logs and monitoring systems.

### 2.5. HTTP Headers in the Cache Key

Specific headers can be included in the key, such as when content depends on `Accept-Language` or a format negotiation header. However:

- High-cardinality header values fragment the cache.
- Client-supplied headers can be spoofed; **never use a cache-key header value as an authorization mechanism**.
- Certain headers receive special CloudFront handling, notably `Accept-Encoding` when gzip/Brotli compression caching is enabled.
- Use only headers supported by the cache policy/API with a verification plan.

**Option worth considering:** instead of putting raw `Accept-Language` strings with many variations into the key, the app can use paths like `/vi/...`, `/en/...` or a normalized language value. That usually makes caching far more predictable.

An origin's `Vary` header **does not make CloudFront automatically vary by every header listed in `Vary`**. To cache the right variants in CloudFront, include the relevant headers in the cache key per service capabilities, or use distinct URLs.

### 2.6. Cookies in the Cache Key

Cookies commonly hold session state, experiment buckets, themes, or login state. Cache policies offer options similar to query strings:

- None;
- All cookies;
- An inclusion list;
- All except an exclusion list.

**Include a cookie in the cache key** when a cacheable response truly varies by that cookie (e.g., a controlled public UI variant). **Never cache personalized cookie-driven responses without an access-isolation design.** For user-specific endpoints, apply **CachingDisabled** or an equivalent tested setup, even if the origin also sends cache-control headers.

## 3. Cache Policy: Configuring TTL and Cache Key

### 3.1. Policies Attach to Cache Behaviors

A CloudFront distribution has a **default cache behavior** and optionally multiple ordered cache behaviors. Each behavior selects an origin, HTTP methods, and its policies.

~~~text
Distribution: www.example.com
├── /assets/*  -> S3 origin -> Cache policy: static-long
├── /images/*  -> S3 origin -> Cache policy: image-variants
├── /api/*     -> ALB origin -> Cache policy: caching-disabled
└── default *  -> S3 origin -> Cache policy: html-short
~~~

CloudFront evaluates path patterns of **ordered cache behaviors** in configured order; the first matching behavior applies, otherwise default applies. Specific path patterns and ordering are therefore critical when an app has multiple routes.

**Example:** if `/api/*` has caching disabled while default behavior caches HTML, verify `/api/user` actually matches the API behavior; otherwise a private API could fall through to an inappropriate cache policy.

### 3.2. Minimum TTL, Default TTL, and Maximum TTL

| Property | Meaning | How to Use |
|---|---|---|
| **Minimum TTL** | Minimum duration CloudFront may hold an object in cache | Set to **0** if `no-cache`/`no-store`/`private` from the origin must be honored |
| **Default TTL** | TTL applied when the origin omits cache directives | Fallback value for content lacking headers |
| **Maximum TTL** | Upper bound when the origin requests a very long cache lifetime | Caps acceptable staleness |

CloudFront combines the cache policy and origin cache headers to determine cache lifetime. A standard mental model:

~~~text
CloudFront TTL ≈
  If origin sends Cache-Control / Expires:
      origin-requested lifetime, clamped by Min TTL and Max TTL
  If origin sends no cache directives:
      cache policy Default TTL (within policy bounds)
~~~

**Critical safety rule:** if **Minimum TTL > 0**, CloudFront can cache responses for at least that duration **even when the origin returns `Cache-Control: no-cache`, `no-store`, or `private`**. Never attach a policy with positive Min TTL to personal-data endpoints assuming `no-store` from the origin prevents caching.

### 3.3. Cache Lifetime Examples

Suppose a policy has:

~~~text
Minimum TTL = 0 seconds
Default TTL = 300 seconds
Maximum TTL = 3600 seconds
~~~

| Origin Header | Typical CloudFront TTL | Explanation |
|---|---:|---|
| No cache directives | 300 seconds | Uses Default TTL |
| `Cache-Control: max-age=120` | 120 seconds | Origin specifies lifetime |
| `Cache-Control: s-maxage=600` | 600 seconds | Directive for shared caches |
| `Cache-Control: max-age=86400` | Max 3600 seconds | Clamped by Maximum TTL |
| `Cache-Control: no-store` | Should not cache per directive with Min TTL = 0 | Holds when no other config/path overrides it |

These examples illustrate common rules; combinations of directives like `s-maxage`, `Expires`, `no-cache`, and error caching should be verified against CloudFront documentation.

### 3.4. Browser `Cache-Control` Differs from CloudFront TTL

CloudFront is a **shared cache** sitting between browsers and origins. Browsers maintain their own caches. Distinguish:

- `max-age`: governs cache reuse per HTTP semantics, including browser caches where applicable.
- `s-maxage`: lifetime specifically for shared caches like CDNs; can take precedence over `max-age` there.
- `no-store`: forbids storing the response in any cache along the path; requires CloudFront Min TTL = 0.
- `no-cache`: allows storing, but requires revalidation before reuse per HTTP rules—it does not mean "never store a copy."
- `private`: response belongs to one user and must not be cached in shared caches when honored by proper config.
- `immutable`: hints clients to skip revalidation while content at that URL never changes; ideal for hashed assets.

**CloudFront invalidation does not clear browser caches.** If browsers hold a file with a long `max-age`, users may continue seeing the old version even after CDN invalidation finishes. That is why **hashed filenames** are used for static assets and short TTLs for HTML.

### 3.5. Managed Cache Policies vs. Custom Cache Policies

AWS provides managed cache policies for common patterns, including **CachingOptimized** and **CachingDisabled**. They are convenient starting points, but **they do not understand your application's semantics automatically**.

When creating a custom policy, decide:

1. Is this content safe to cache in a shared CDN?
2. What are Min/Default/Max TTLs?
3. Which queries, cookies, and headers alter the response?
4. Should gzip/Brotli compression be enabled as supported?
5. Are there language/device variants needing normalization?
6. What error caching and invalidation procedures are required?

Name policies clearly by purpose, e.g., `aws-lab-static-v1`, `aws-lab-html-short`, or `aws-lab-api-no-cache`. Managing policies via IaC makes diffs easy to review before production changes.

## 4. Cache Policy, Origin Request Policy, and Response Headers Policy

### 4.1. Why Separate into Three Policies?

A request may carry information the origin needs for authentication, logging, or processing. However, **not everything sent to the origin should become part of the cache key**.

| Policy | Purpose | Changes Cache Key? |
|---|---|---|
| **Cache policy** | TTL and which queries/headers/cookies enter the cache key | **Yes** |
| **Origin request policy** | Forwards additional queries/headers/cookies to the origin | **Not directly** |
| **Response headers policy** | Controls headers CloudFront returns to viewers | **Not directly** |

CloudFront automatically forwards to the origin any values included in the cache key by the cache policy. An origin request policy **supplements** values needed by the origin without putting them in the key.

~~~mermaid
flowchart LR
    V[Viewer request] --> C[Cache policy]
    C --> K[Cache key + TTL]
    K --> H{Hit?}
    H -->|Yes| R[Cached response]
    H -->|Miss| O[Origin request policy: forward extra values]
    O --> B[Origin: S3 / ALB / API]
    B --> R
    R --> RH[Response headers policy]
    RH --> V2[Viewer receives response]
~~~

The diagram shows only the logical role of each policy; real requests are also affected by CloudFront Functions, Lambda@Edge, origin custom headers, Origin Shield, and other settings.

### 4.2. Risk When the Origin Receives Data Excluded from the Key

Suppose an origin reads an `X-Account-Tier` header injected by a proxy and returns different content for `free` vs. `premium`. If that header is forwarded by an **origin request policy** yet **omitted from the cache key**, CloudFront can cache one response and serve it to requests with other tiers sharing the same key.

This is a severe bug if the variants differ in access privileges. How to handle it:

- For valid public variants, put the **normalized signal** into the cache key per service capabilities.
- For personal info or authorization-gated data, **disable shared caching** on that behavior and verify origin headers.
- Never trust client-supplied headers to make privacy decisions.
- Test with two principals requesting the same URL with different permissions/content before deploying.

### 4.3. Can a Response Headers Policy Override Origin TTL?

A response headers policy can add/modify headers on responses sent to viewers, including CORS/security headers or custom headers per CloudFront capabilities. However, **CloudFront's cache TTL is controlled by the cache policy and origin cache directives during caching**; changing a header sent to viewers does not alter the internal TTL of the cached object at the edge.

For example, to cache a JavaScript file at the edge for a long time, configure the cache policy and origin `Cache-Control` properly; injecting a header solely on the viewer response does not make CloudFront cache it for a year.

### 4.4. Authorization, CORS, and Cache Keys

- **Authorization:** carefully verify how CloudFront forwards the header and how the cache policy handles it for your origin. Never enable caching on a private API assuming `Authorization` is automatically in the key.
- **CORS:** if the origin generates different `Access-Control-Allow-Origin` values per request `Origin`, failing to separate variants can return the wrong CORS header; consider appropriate policies/response headers policies or standard CORS design.
- **Session cookies:** usually have high cardinality, and personalized content does not belong in a default shared cache.
- **Tracking cookies:** if they do not change content, exclude them from the key.
- **Host header:** CloudFront has specific handling depending on origin/policy; do not assume it behaves identically to a self-managed reverse proxy.

## 5. Designing Caching by Content Type

### 5.1. Starting Matrix

| Content | Recommended Caching | Cache Key | Updates |
|---|---|---|---|
| `/assets/app.a1b2c3.js`, hashed CSS/images | Long TTL; immutable files | Usually URL/path plus truly meaningful variants | Upload new hashed file; HTML references new name |
| `/index.html` or HTML entry | Short TTL, revalidatable | Usually URL/path | Invalidation or short TTL after deploy |
| Dynamic images by `width`/`format` | Cache normalized variants | URL/path + controlled `width`/`format` queries | Versioning or path invalidation |
| Public API catalog | Short cache if non-personalized | Path + selected queries; maybe language | Short TTL or invalidation |
| `/api/me`, cart, profile | **CachingDisabled** or equivalent protection | Do not use shared CDN cache for private data | Origin serves fresh data, `no-store` |
| Session-rendered pages | Design-dependent; usually do not cache shared responses | Avoid keys lacking identity | Authorization design and testing |
| Restricted downloads | Consider CloudFront signed URLs/cookies or origin auth | Never share unauthorized data | Access policies and file versioning |

Choose TTLs based on product requirements. No single TTL set fits every service.

### 5.2. Content-Hashed Static Assets

For example, builds output:

~~~text
/app.js                 (fixed name, prone to staleness)
/assets/app.4e9c12.js   (content-hashed name)
/assets/app.8af2d1.js   (new release)
~~~

For hashed files, you can use:

~~~http
Cache-Control: public, max-age=31536000, immutable
~~~

This is the standard pattern for assets that are **truly immutable** for the lifetime of that filename. Never attach `immutable` to `/index.html` or `/app.js` if the content at that URL can be overwritten.

Sample deploy order:

1. Build and upload assets under **new** hashed filenames.
2. Verify S3 origin and CloudFront delivery of the new assets.
3. Upload the new HTML entry referencing the new hashes.
4. Rely on short HTML TTL or invalidate `/index.html` and actual entry routes (if needed).
5. Retain old assets for an appropriate window so open browser tabs from before the deploy do not break; clean up later via lifecycle rules.

Advantage: new URLs generate new cache keys without relying on purging every old asset at the edge. Invalidation remains useful for HTML or files that cannot be versioned by name.

### 5.3. Image Variants

Example URLs:

~~~text
/images/course-cover.jpg?width=400&format=webp
/images/course-cover.jpg?width=800&format=webp
/images/course-cover.jpg?width=400&format=jpeg
~~~

If the origin/edge genuinely produces three distinct payloads, the cache key must include `width` and `format` or encode variants into the path. If `utm_campaign` is only for analytics, exclude it from the cache key.

**Prevent variant explosion:** allow only normalized values, such as width ∈ {320, 640, 960} and format ∈ {webp, jpeg}. Never let arbitrary width values from 1 to thousands generate unbounded cached objects.

### 5.4. APIs and User Data

An endpoint:

~~~http
GET /api/me HTTP/1.1
Authorization: Bearer <token>
~~~

returns user profile data and strictly requires authorization checks at origin/edge per approved design. For typical private APIs:

- `/api/*` cache behavior uses managed **CachingDisabled** or a policy with caching disabled properly.
- Origin returns `Cache-Control: private, no-store` or system-approved directives.
- Forward required headers/cookies through compatible CloudFront configuration and test live.
- Ensure User A's response is never served to User B using a two-session test.
- Verify special routes like `/api/public/catalog` have their own cache behavior with higher path precedence if needed.

**CloudFront signed URLs/cookies** protect access to a resource via edge authentication, and caching can help when the exact same resource is granted to multiple authorized users. That differs from blindly caching **origin-personalized** responses by session. Authorization design is mandatory before sharing cache.

## 6. Invalidation: Purging Cached Entries by Path

### 6.1. When Is Invalidation Needed?

When an origin updates content at an unchanged URL, CloudFront may keep serving the old cached version until TTL expires or revalidation runs. **Invalidation** tells CloudFront to purge cached versions by path within the distribution.

~~~mermaid
sequenceDiagram
    participant Dev as Deployment pipeline
    participant S3 as S3 Origin
    participant CF as CloudFront
    participant V as Viewer
    Dev->>S3: Upload new index.html
    Dev->>CF: CreateInvalidation /index.html
    CF-->>Dev: Invalidation ID - InProgress
    Dev->>CF: GetInvalidation / poll Completed
    CF-->>Dev: Completed
    V->>CF: GET /index.html
    CF->>S3: Fetch new version on cache fill
    S3-->>CF: New index.html
    CF-->>V: Serve new content
~~~

**Invalidation does NOT:**

- Delete or modify objects at S3/ALB origins;
- Clear browser caches, external proxy caches, or app service worker caches;
- Permanently alter `Cache-Control` or TTLs for future requests;
- Replace deployment pipelines, backups, or application rollbacks.

If the origin still serves stale data (e.g., deployment incomplete or unsynced origins), CloudFront will simply re-cache the **stale version** after invalidation.

### 6.2. Invalidation Path Syntax

CloudFront invalidation paths begin with `/`, for example:

~~~text
/index.html
/
/assets/app.js
/images/*
/*
~~~

The `*` wildcard may only appear **at the end of an invalidation path**. `/*` invalidates broadly and should not be the default on every deploy. Paths are **case-sensitive**, and URL rewrites, default root objects, or cached query strings may require invalidating multiple corresponding paths.

SPA example:

~~~text
GET /            -> CloudFront default root object index.html
GET /index.html
GET /courses/123 -> may be rewritten to /index.html (depending on config)
~~~

Depending on default root object and URL rewrite rules, verify which paths actually hold cache entries, then invalidate `/index.html`, `/`, and/or matching patterns. **Never assume invalidating `/index.html` alone refreshes every SPA route.**

### 6.3. Invalidation with Query Strings

If CloudFront caches **distinct variants by query string**, one path can correspond to multiple cache entries:

~~~text
/catalog?lang=vi
/catalog?lang=en
/catalog?page=2
~~~

Either specify exact query paths or use a trailing wildcard pattern like `/catalog*` to cover variants. `*` must be the final character in the path. Avoid `/catalog*` on distributions with similarly named routes you do not intend to purge.

**Better strategy:** design low-cardinality keys and versioned URLs for frequently changing assets to minimize invalidations.

### 6.4. Status and Billing

CloudFront returns an **invalidation ID** and a status such as `InProgress` or `Completed`. Only when AWS reports `Completed` has the invalidation propagated across the delivery network. Testing from one network vantage while still `InProgress` does not reflect global state.

Invalidations have **concurrency quotas, path limits, and free-tier/per-path pricing** per account; never assume `/*` is always free or harmless to origin performance. Check current AWS pricing and quotas.

## 7. Invalidation vs. Versioned Filenames

| Criterion | Invalidation | Versioned filenames / content hash |
|---|---|---|
| Mechanism | Purges existing cached URLs | Creates a **new URL** with a new cache key |
| Must update referencing URLs? | No | Yes; app/HTML must reference new filenames |
| Best suited for | HTML entry points, metadata, fixed URLs, emergency fixes | JS, CSS, images, and immutable assets |
| Update delay | Depends on invalidation propagation and origin | Clients fetch new URL as soon as the reference updates |
| Browser cache | Does not clear old browser caches | New URL bypasses old browser caches cleanly |
| Operational cost | May incur invalidation fees | Extra storage/requests for retaining versions |
| Rollback | May require re-invalidating after restoring origin | HTML reverts to referencing old asset name if still stored |
| Risk | Over-broad invalidation triggers origin traffic spikes | Deleting old assets too soon breaks open older pages |

**Common architectural recommendation:** versioning + long TTLs for static assets, and short TTLs or selective invalidation for HTML/manifests. Never apply long-term caching to personal content or regulated data without explicit access controls.

### 7.1. Safe Ordered Deployment

A typical flow for S3 + CloudFront websites:

~~~text
1. Build -> generate content-hashed asset filenames
2. Upload new assets with long Cache-Control
3. Verify new assets are reachable via CloudFront/origin
4. Upload HTML/manifest referencing the new assets
5. Invalidate only HTML/manifest (if needed)
6. Monitor error rates, cache hit ratio, latency, and origin traffic
7. Roll back HTML/manifest if issues occur and invalidate accordingly
8. Clean up very old assets per retention rules—do not delete immediately
~~~

When using a **service worker**, client-side caching has its own lifecycle and update logic that must be tested independently; CloudFront invalidation does not force service worker caches to clear.

## 8. Cache Behavior Selection and Path Pitfalls

### 8.1. Behavior Order Affects Security Too

Suppose a distribution has:

~~~text
Ordered behaviors:
  /api/private/* -> CachingDisabled + API origin
  /api/*         -> Short cache + API origin

Default behavior:
  *              -> Cache HTML + S3
~~~

`/api/private/profile` must hit the first behavior. If `/api/*` were placed first, the broader rule would intercept it. **Having the right cache policy on the wrong behavior does not protect the endpoint.**

Also test path variations with trailing slashes, URL encoding, case differences, and rewrites from CloudFront Functions/Lambda@Edge—never test only one clean URL from docs.

### 8.2. Cache Keys and Compression

CloudFront supports gzip/Brotli compression. When enabled on the cache policy, CloudFront **normalizes `Accept-Encoding` and separates required compressed variants** in the cache key per service capabilities.

Do not manually add raw `Accept-Encoding` variants or entire `User-Agent` headers to the key when CloudFront's built-in compression handles it. Verify:

- The origin sets accurate `Content-Type`/`Content-Encoding`.
- Content is not double-compressed.
- Viewers supporting gzip/Brotli receive valid responses.
- Cache hit ratio before and after changes.

### 8.3. Caching HTTP Errors

CloudFront can cache error responses like 404/5xx per **Error Caching Minimum TTL** and related rules. Thus:

~~~text
t0: /assets/new.js does not exist yet -> origin returns 404
t1: Upload /assets/new.js to S3
t2: CloudFront may still return cached 404 while error TTL remains valid
~~~

When a freshly deployed asset still returns 404:

1. Verify the object exists at the origin with the exact key, Region, and permissions.
2. Check HTTP status/`X-Cache` from CloudFront.
3. Inspect error caching TTL/config.
4. Consider invalidating that specific path, avoiding `/*` unless needed.

Never raise error caching TTL on time-sensitive API routes unless you accept prolonged errors after origin recovery.

## 9. Lab 1 — Inspecting Cache Policies on a Distribution via AWS CLI

> This section is read-only and creates no resources. You need AWS CLI v2 and an IAM role/user with permissions such as `cloudfront:ListDistributions`, `cloudfront:GetDistribution`, and `cloudfront:GetCachePolicy`. AWS CloudFront is a global service; confirm the exact **account and distribution ID** before reading or modifying.

### 9.1. Verify AWS Identity

Example in Bash or CloudShell:

~~~bash
export AWS_PROFILE=aws-lab-dev
aws sts get-caller-identity --profile "$AWS_PROFILE"
~~~

If using CloudShell with an already signed-in identity and no profile, omit `export AWS_PROFILE=...` and `--profile`. `Account` and `Arn` must match your assigned sandbox.

### 9.2. List Distributions

~~~bash
aws cloudfront list-distributions \
  --query 'DistributionList.Items[].{Id:Id,Domain:DomainName,Status:Status,Enabled:Enabled}' \
  --output table
~~~

If the account has no distributions, the list may be empty. Do not create a production distribution just to complete a read-only exercise; you can still study the sample JSON/policies below.

### 9.3. Inspect Behaviors and Policy IDs

~~~bash
DIST_ID=E123EXAMPLEABC

aws cloudfront get-distribution \
  --id "$DIST_ID" \
  --query 'Distribution.DistributionConfig.{Origins:Origins,Default:DefaultCacheBehavior,Ordered:CacheBehaviors.Items}' \
  --output json
~~~

Replace `E123EXAMPLEABC` with an ID you are **authorized to read**. Locate:

- `PathPattern` on ordered cache behaviors and the default behavior.
- `TargetOriginId` identifying S3/ALB/HTTP origins.
- `CachePolicyId`, `OriginRequestPolicyId`, and `ResponseHeadersPolicyId` (if attached).
- Settings such as `ViewerProtocolPolicy`, `Compress`, and allowed/cached HTTP methods.

If a behavior still uses legacy `ForwardedValues`, do not interpret it as if a modern cache policy exists; review legacy rules and plan a tested migration.

### 9.4. Read a Specific Cache Policy

~~~bash
CACHE_POLICY_ID=11111111-2222-3333-4444-555555555555

aws cloudfront get-cache-policy \
  --id "$CACHE_POLICY_ID" \
  --query 'CachePolicy.CachePolicyConfig' \
  --output json
~~~

The ID is a placeholder. Inspect:

~~~text
MinTTL / DefaultTTL / MaxTTL
ParametersInCacheKeyAndForwardedToOrigin:
  EnableAcceptEncodingGzip
  EnableAcceptEncodingBrotli
  HeadersConfig
  CookiesConfig
  QueryStringsConfig
~~~

**Analysis question:** if the cache key includes all cookies even though the app does not vary content by cookie, what happens to the cache hit ratio? If `MinTTL=60` yet the API origin returns `no-store`, what is the risk?

### 9.5. Inspect Origin Request Policy If Present

~~~bash
ORIGIN_REQUEST_POLICY_ID=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee

aws cloudfront get-origin-request-policy \
  --id "$ORIGIN_REQUEST_POLICY_ID" \
  --query 'OriginRequestPolicy.OriginRequestPolicyConfig' \
  --output json
~~~

Distinguish values **forwarded to the origin** from values **included in the cache key**. You can list available policies with `list-cache-policies` and `list-origin-request-policies` as permitted.

### 9.6. Observe HTTP Cache Behavior with `curl`

If you have a sandbox CloudFront domain:

~~~bash
CF_URL=https://d123example.cloudfront.net

curl -sSI "$CF_URL/assets/app.js"
curl -sSI "$CF_URL/assets/app.js"
~~~

Inspect headers that may appear:

~~~text
HTTP/2 200
cache-control: public, max-age=...
age: ...
x-cache: Hit from cloudfront
x-amz-cf-pop: ...
x-amz-cf-id: ...
~~~

Values above are **illustrative**, not guaranteed identical output. `X-Cache` can be `Miss from cloudfront`, `Hit from cloudfront`, `RefreshHit`, or other states; `Age` may be absent on some responses. Because caching is distributed, two requests from different locations/edges are not guaranteed to share a cache entry at the same instant.

**Never use `X-Cache: Hit` as security proof.** It only helps observe caching, not whether authorization was enforced properly.

## 10. Lab 2 — Selective Invalidation in a Sandbox

> This section **mutates the CloudFront distribution** and may incur invalidation charges. Run only on a sandbox distribution you are authorized to update, targeting paths you own. Never invalidate a production distribution just for practice.

### 10.1. Check the Origin Version First

Suppose the S3 origin holds `index.html` and asset `assets/app.a1b2c3.js`. If you have bucket read access:

~~~bash
BUCKET=aws-lab-cloudfront-demo

aws s3api head-object \
  --bucket "$BUCKET" \
  --key index.html \
  --query '{ETag:ETag,LastModified:LastModified,CacheControl:CacheControl,ContentType:ContentType}' \
  --output json
~~~

Confirm the origin was actually updated and has an appropriate `Cache-Control` header. With S3 versioning, inspect the right version if rollback relies on a specific version. **Invalidating while the origin is still stale simply re-caches stale data.**

### 10.2. Create an Invalidation for the HTML Entry

~~~bash
DIST_ID=E123EXAMPLEABC

aws cloudfront create-invalidation \
  --distribution-id "$DIST_ID" \
  --paths "/index.html" "/"
~~~

The command returns `Invalidation.Id`, `Status`, paths, and metadata. For apps with URL rewrites or query variants, target the exact paths needing refresh per the delivery configuration.

### 10.3. Check Invalidation Status

~~~bash
aws cloudfront list-invalidations \
  --distribution-id "$DIST_ID" \
  --query 'InvalidationList.Items[].{Id:Id,Status:Status,Created:CreateTime}' \
  --output table
~~~

Inspect a specific invalidation:

~~~bash
INVALIDATION_ID=I123EXAMPLEABC

aws cloudfront get-invalidation \
  --distribution-id "$DIST_ID" \
  --id "$INVALIDATION_ID" \
  --query 'Invalidation.{Id:Id,Status:Status,Paths:InvalidationBatch.Paths.Items}' \
  --output json
~~~

Replace the ID with the value from `create-invalidation`. When an approved pipeline needs to wait for completion, the AWS CLI provides a waiter:

~~~bash
aws cloudfront wait invalidation-completed \
  --distribution-id "$DIST_ID" \
  --id "$INVALIDATION_ID"
~~~

**Do not assume completion merely because creation succeeded**; wait until `Completed` when rollouts depend on invalidation. Timing varies, and pipelines need appropriate timeouts/retries.

### 10.4. Test After Invalidation

~~~bash
CF_URL=https://d123example.cloudfront.net

curl -sSI "$CF_URL/"
curl -sSI "$CF_URL/index.html"
~~~

Check `Date`, `Last-Modified`, `ETag`, `Cache-Control`, `Age`, and `X-Cache` where present; compare actual response content and build version. Two URLs may behave differently due to behavior/default root/rewrite/caching differences; test **every access path real users take**.

### 10.5. Wildcard Invalidation When Needed

To refresh a specific subtree:

~~~bash
aws cloudfront create-invalidation \
  --distribution-id "$DIST_ID" \
  --paths '/images/*'
~~~

Single quotes prevent the shell from expanding `*` into local filenames. Verify scope before submitting, as broad invalidations can spike origin traffic. Avoid `'/*'` as a routine step after every deploy.

**Lab cleanup:** Invalidation is a cache-management request; there is no "delete invalidation" action to undo it. Caches refill as requests arrive. If the lab created S3 test objects, delete only your lab objects per procedure—never delete shared buckets/distributions. Review S3 request, CloudFront transfer, invalidation, and log charges in your billing dashboard once updated.

## 11. Design Exercise: Cache Keys and TTLs

### 11.1. Problem Statement

An online learning platform serves:

- `learn.example.com/index.html`: SPA entry deployed frequently.
- `learn.example.com/assets/app.<hash>.js`: JavaScript and CSS built with content hashes.
- `learn.example.com/images/course.jpg?size=small|large`: images in two sizes.
- `learn.example.com/catalog?lang=vi|en&page=N`: public catalog.
- `learn.example.com/api/me`: per-student profile with Authorization/cookie.
- `learn.example.com/api/progress`: private learning progress.

Requirements: minimize latency nationwide, prevent data leaks, recover quickly from bad deploys, and control CloudFront/S3/ALB costs.

### 11.2. Reference Design

| Behavior | Origin | Suggested Cache Key | Target TTL | Updates |
|---|---|---|---|---|
| `/assets/*` | Private S3 + OAC | URL/path; exclude session cookies | Long for hashed immutable assets | Upload new hash; HTML references new name |
| `/images/*` | S3/image service | URL/path + normalized `size` | Medium/long depending on churn | Versioning or path invalidation |
| `/catalog` | Public API | Path + `lang` + `page` | Short, per data freshness needs | TTL or invalidation |
| `/api/me` | ALB/API | **Do not cache personal responses** | Disabled / Min TTL 0 | Fetched from backend |
| `/api/progress` | ALB/API | **Do not cache personal responses** | Disabled / Min TTL 0 | Backend enforces per-user auth |
| Default/HTML | Private S3 + OAC | Path and truly needed variants | Short, with revalidation | Invalidate `/index.html` or root if needed |

**Protect the S3 origin with Origin Access Control (OAC)** so CloudFront is the authorized delivery path; never enable public bucket ACLs just to serve a website. For APIs, ALB and application authorization still control user access.

### 11.3. Calculating Variant Count Yourself

Catalog has 2 languages, 10 pages, and 3 sort orders:

~~~text
2 languages × 10 pages × 3 sorts = 60 cache variants
~~~

If the cache key also adds a unique `session_id` for 10,000 users, theoretical variants jump into the hundreds of thousands without changing the actual content. Ask: which attributes truly change the response? If `sort` reorders items, it belongs in the key or path. If session does not change the public catalog, exclude session from the cache key.

### 11.4. Rollback Scenario

Newly deployed HTML references `app.bad123.js`, breaking the frontend. Remediation:

1. Previously tested HTML still points to `app.good456.js`, which remains stored.
2. Restore the old HTML to the origin per controlled rollback procedure.
3. Invalidate HTML/root or wait out a very short TTL per SLO.
4. Watch CloudFront error rates, asset 404s, frontend error tracking, and origin request volume.
5. Never delete old hashed assets still referenced by open browser tabs.
6. Check browser/service worker caches if users still hit the broken version after invalidation completes.

## 12. Monitoring Cache, Origin, and Costs

### 12.1. Important Signals

| Signal | Reference Source | Question Answered |
|---|---|---|
| **CacheHitRate** | CloudFront monitoring / applicable CloudWatch metrics | What share of requests are served from cache? |
| **Requests** | CloudFront monitoring/logs | Is traffic surging in a given period? |
| **4xxErrorRate / 5xxErrorRate** | CloudFront metrics | Are there notable viewer or origin errors? |
| **OriginLatency** | CloudFront metrics when supported/enabled | Is the origin responding slowly? |
| **X-Cache, Age** | HTTP response headers | Did a sample request hit, miss, or revalidate? |
| **S3 request metrics / ALB metrics** | Origin metrics | Are cache misses overloading the origin? |
| **CloudFront access logs / real-time logs** | Logging if enabled | Analyze request paths, hits/misses, and error trends |
| **Cost Explorer / Budgets** | Billing | What are transfer, request, invalidation, and logging costs? |

Metric availability, dimensions, sampling, and pricing vary by CloudFront feature. **Real-time logs** and additional metrics can incur extra fees; enable them based on concrete observability needs.

### 12.2. Interpreting Cache Hit Ratio

~~~text
Cache hit ratio ≈ requests served from cache
                  / total requests in measured scope
~~~

This is an explanatory formula; CloudFront's metric has its own definitions and exclusions. Never use a distribution-wide average to conclude `/api/*` behaves properly, since high-volume static assets can mask API issues.

If cache hit ratio drops:

- Check whether deployments alter URLs/hashes too frequently.
- Were all cookies/headers/queries accidentally added to the key?
- Is TTL too short relative to request cadence?
- Are there many error responses or uncacheable directives?
- Is traffic spread across many edge locations or keys with few repeated hits?
- Does the origin emit `Cache-Control` or cookies preventing caching?

### 12.3. Costs and Trade-Offs

CloudFront charges can include data transfer out to viewers, HTTP/HTTPS requests, invalidations beyond free tiers, logging, edge/security features, plus S3/ALB origin costs depending on architecture.

**Good optimization:** fewer origin requests and lower backend load by caching public content. **Bad optimization:** adding every header to the cache key, causing high miss rates, hammering the origin, and raising costs.

**Never chase hit ratio by caching private data.** Pick TTLs based on data risk, SLAs, and user experience first, then evaluate costs.

## 13. Diagnosing Common Failures

| Symptom | Common Cause | How to Check |
|---|---|---|
| New deploy yet users still see old HTML | Long HTML TTL, incomplete invalidation, browser/service worker cache | Check `Cache-Control`, invalidation status, `Age`, browser |
| One user receives another user's data | Shared cache on personalized response; missing key variant or caching not disabled | Disable caching on sensitive routes immediately; audit logs/auth; test two accounts |
| English catalog shows Vietnamese content | `lang` omitted from cache key or bad normalization | Inspect cache policy query strings and origin response |
| Very low cache hit ratio | Session cookie, User-Agent, or tracking queries fragmenting keys | Inspect `HeadersConfig`/`CookiesConfig`/`QueryStringsConfig` |
| CloudFront hits yet origin file changed | TTL unexpired or invalidation missed the path | Check `Age`, `ETag`, origin version, invalidation |
| Invalidated `/index.html` yet `/` stays stale | Default root object/rewrite uses a different cache path | Inspect URLs and invalidation paths |
| Origin returns `no-store` yet CloudFront caches | Cache policy has Minimum TTL > 0 | Set Min TTL 0 or `CachingDisabled` on private routes |
| 404 persists after uploading object | Error caching, wrong object key, S3 origin permissions | Check origin, error caching TTL, and invalidate exact path |
| Reordered URL queries cause misses | Cache key distinguishes query parameter order | Normalize query/path before caching where appropriate |
| CORS breaks for some websites | Origin varies response by `Origin` header while cache key lacks variant | Check `Origin` and CORS policies; fix cache key/headers |
| Requests to `/api/*` cached like HTML | Misordered behavior or wrong path match | Check ordered cache behaviors and test all paths |
| `create-invalidation` fails with access denied | IAM lacks `cloudfront:CreateInvalidation` or wrong account distribution | Verify STS identity, distribution ARN, and IAM policy |
| Invalidation Completed yet old asset appears | Independent browser/proxy/service-worker cache | Check client cache, versioned URLs, and response headers |
| Origin load spikes after invalidation | Overly broad invalidation or high traffic | Narrow invalidation scope, use versioning, ensure origin capacity |
| Long TTL yet continuous API cache misses | API returns `private`/`no-store` or high key cardinality | Determine whether the API should even be cached before tuning |

### 13.1. Ordered Verification Procedure

~~~text
1. Verify account, distribution ID, domain, and DNS.
2. Identify exact URL/path and which cache behavior actually matches.
3. Check CachePolicyId, Min/Default/Max TTL, and query/header/cookie key settings.
4. Check OriginRequestPolicyId and what the origin receives.
5. Check Cache-Control/Expires/ETag returned by the origin.
6. Request via CloudFront and inspect X-Cache/Age/response body.
7. Check invalidation paths and Completed status if issued.
8. If still stale, inspect browser, service worker, proxy, and origin version.
9. For sensitive content, prioritize verifying auth and preventing cross-user leaks.
10. Measure cache ratio, error rate, latency, origin load, and cost.
~~~

## 14. Misconceptions to Avoid

**"CloudFront caches by every header, cookie, and query by default."** False. Cache keys depend on cache policy settings, forwarding/normalization options, and CloudFront behavior.

**"Putting all cookies in the cache key is safest."** False. This usually ruins hit ratios; for personal data you must still analyze authorization and CDN data-sharing risks.

**"If an origin request policy forwards a header to the origin, it automatically enters the cache key."** False. Values forwarded via an origin request policy **do not automatically** join the cache key.

**"`Cache-Control: no-store` always disables caching."** Not necessarily. A cache policy with **Minimum TTL > 0** can still make CloudFront cache for at least that duration even when the origin sends `no-store` or `private`.

**"Invalidation updates browser caches too."** False. Invalidation clears CloudFront's cache; browsers, service workers, and external proxies have independent cache lifecycles.

**"Updating a JavaScript file while keeping the same filename and a one-year TTL is safe."** Unsuitable. Clients may keep the stale file; use hashed filenames or an explicit update strategy.

**"Invalidating `/*` after every deploy is best practice."** Unnecessary in most cases. It can spike origin load and cost; invalidate only the URLs that truly need refreshing.

**"A higher `CacheHitRate` proves the architecture is secure."** False. Cache hit ratio is a performance signal; data security must be verified separately via permissions, cache keys, and multi-principal testing.

## 15. Self-Check and Exercises

1. What logical components make up a cache key? When should query parameter `lang` be included in the cache key?
2. Can `/catalog?a=1&b=2` and `/catalog?b=2&a=1` produce separate cache entries? How would you handle that?
3. Why can adding `User-Agent` or a session cookie to the key increase origin traffic?
4. How does an origin request policy differ from a cache policy in its effect on the cache key?
5. If `Minimum TTL = 60` while the origin returns `Cache-Control: no-store`, what is the risk for a personal profile endpoint?
6. Why should `/api/me` use `CachingDisabled` even if the app sends an `Authorization` header?
7. When does CloudFront use Default TTL?
8. How do `max-age` and `s-maxage` differ for browsers vs. shared caches?
9. Does invalidating `/index.html` clear all browser caches and service worker caches?
10. When should you use `/assets/app.<hash>.js` with a long TTL instead of overwriting `/assets/app.js`?
11. Why should new assets be uploaded before updating HTML?
12. How does invalidating `/images/*` affect origin load and cost?
13. What evidence confirms a 404 response is being error-cached by CloudFront?
14. If updated HTML is already in S3 yet CloudFront still serves old HTML, in what order do you investigate?
15. How do you ensure a request to `/api/private/profile` is not handled by a public `/api/*` caching behavior?
16. Should two applications sharing a URL but returning different data based on a client header share the same cache?
17. Propose a cache key for a public catalog with `lang`, `page`, `sort`, and `utm_source`.
18. For an SPA using a service worker, why isn't CDN invalidation enough to ensure every user sees the new release?
19. Beyond cache hit ratio, what other metrics should be monitored to evaluate a cache policy's impact?
20. How does protecting an S3 origin with CloudFront OAC benefit static asset delivery?

### 15.1. Decision Exercise

Given a system with four response types:

| URL | Response | Recommended Cache |
|---|---|---|
| `/assets/app.f84a2.js` | User-independent JS | Long TTL, hashed URL |
| `/index.html` | HTML changing on every deploy | Short TTL + selective invalidation if needed |
| `/api/products?lang=vi` | Public catalog by language | Short cache, key includes `lang` |
| `/api/me` | Personal info per Authorization | Do not cache in shared CDN |

**Explain** your choices, origin behavior, and deploy/rollback steps for each URL. Factor in browser caching, cost, and acceptable post-deploy delay.

## 16. Pre-Production Checklist for CloudFront Caching

- [ ] Listed all origins, domains, TLS certificates, and DNS routes.
- [ ] Identified which behavior serves HTML, assets, public APIs, and private APIs.
- [ ] Ordered path patterns accurately and verified with test requests.
- [ ] Confirmed cache keys include the exact queries/headers/cookies that alter cacheable responses.
- [ ] Ensured no cross-user/tenant or authorization-gated data is ever cached together.
- [ ] Understood cache policy vs. origin request policy; ensured origin does not depend on values omitted from the key.
- [ ] Set Minimum TTL = 0 or equivalent policy on endpoints that must honor `no-store`.
- [ ] Aligned HTML/manifest and hashed asset TTLs with deployment cadence.
- [ ] Designed scoped invalidation paths and versioning strategies.
- [ ] Tested rollbacks, client/browser caches, and service worker caches if used.
- [ ] Protected S3 origins with OAC and appropriate bucket policies where S3 is used.
- [ ] Configured CloudFront/ALB/S3 metrics, logs, error alerts, latency, and origin load monitoring.
- [ ] Reviewed request, data transfer, invalidation, logging, and add-on feature costs.
- [ ] Prepared runbooks for stale content, 404 error caching, cache key fragmentation, and misordered behaviors.
- [ ] Managed TTLs, policies, and rollouts via IaC/code review where possible.

**Expected Outcome:** You can explain **which requests share a cache entry**, how long CloudFront retains cached objects, when invalidation is needed, and how to pair it with file versioning for reliable deployments. You can also identify access risks, measure performance, and run content updates without unexpected costs or outages.

## Official AWS Documentation

- [Understand cache keys](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/understanding-the-cache-key.html)
- [Control the cache key with a policy](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/controlling-the-cache-key.html)
- [Use managed cache policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-cache-policies.html)
- [Control origin requests with a policy](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/controlling-origin-requests.html)
- [Response headers policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/modifying-response-headers.html)
- [Manage how long content stays in the cache](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Expiration.html)
- [Cache content based on query string parameters](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/QueryStringParameters.html)
- [Cache content based on cookies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Cookies.html)
- [Invalidate files to remove content](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Invalidation.html)
- [Specify invalidation files](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/invalidation-specifying-objects.html)
- [Choose between invalidating files and using versioned file names](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Invalidation.html#invalidation-choosing-between)
- [CloudFront cached HTTP error responses](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/HTTPStatusCodes.html)
- [CloudFront pricing](https://aws.amazon.com/cloudfront/pricing/)
- [Protect S3 origins with Origin Access Control](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html)

> **Application Note:** Domains, distribution IDs, policy IDs, buckets, and outputs in this lesson are training examples. CloudFront features, pricing, quotas, and caching behavior can change over time. Before deploying cache policies or invalidations to production, check current AWS documentation, test with representative requests, and follow your organization's change approval process.
