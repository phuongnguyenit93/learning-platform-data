# CloudFront Distributions, Origins, and Cache Behaviors

When a web application serves users across multiple regions, sending every request directly to the origin server (*origin*) can increase latency, bandwidth usage, cost, and system load. **Amazon CloudFront** is AWS's Content Delivery Network (**CDN**) service. CloudFront accepts requests at edge locations (*edge locations*), serves cacheable content, and forwards remaining requests to origins according to the **distribution** configuration.

Three concepts must be clearly distinguished:

- **Distribution**: the CloudFront content delivery configuration, including domain names, certificates, origins, cache behaviors, security policies, and logging.
- **Origin**: the source of content or application logic, such as **Amazon S3**, an **Application Load Balancer (ALB)**, an HTTP server, or an API endpoint.
- **Cache behavior**: rules matching request path patterns, selecting the origin, and governing caching, HTTP methods, HTTPS, and attached policies.

This lesson belongs to the **DNS and Content Delivery** chapter, **CLOUD_PROVIDERS_AWS** module. Learners connect CloudFront with Regions/AZs, IAM, VPC, compute, storage, databases, integration, and serverless to design secure, observable, resilient, and cost-controlled applications.

## 1. Learning Outcomes

After this lesson, learners will be able to:

1. Describe the **viewer → CloudFront edge → origin** flow and distinguish **cache hit/miss**.
2. Model a distribution with multiple origins and multiple cache behaviors; understand **default behavior** and **path pattern** ordering.
3. Choose appropriately between **S3 bucket origins**, **custom origins**, and **origin groups** along with their respective limits.
4. Distinguish **cache policies**, **origin request policies**, **response headers policies**, and TTL settings.
5. Configure HTTPS, custom domains/Route 53, **Origin Access Control (OAC)**, WAF, and access restrictions.
6. Design caching for static files, public APIs, and personalized APIs without accidentally leaking data across users.
7. Verify behavior using the AWS CLI, HTTP headers, logs/metrics; execute invalidations and troubleshoot common issues.

## 2. How CloudFront Architecture Works

~~~mermaid
flowchart LR
    USER["Viewer<br/>Browser / application"] -->|"HTTPS + DNS"| EDGE["CloudFront edge<br/>Distribution"]
    EDGE -->|"Cache hit: return immediately"| USER
    EDGE -->|"Cache miss / TTL expired"| ORIGIN{"Cache behavior selects origin"}
    ORIGIN -->|"assets/*"| S3["S3 bucket origin<br/>Images, JS, CSS"]
    ORIGIN -->|"api/*"| ALB["ALB / API origin<br/>Dynamic application"]
    S3 --> EDGE
    ALB --> EDGE
~~~

Basic flow:

1. A user accesses a domain name, such as **www.example.com**. DNS directs the user to the corresponding CloudFront distribution.
2. CloudFront selects a **cache behavior** based on the **URL path**, such as **/assets/logo.png** or **/api/orders**.
3. CloudFront builds a **cache key** per the cache policy and looks for a valid cached response in the relevant cache layer.
4. If a matching, valid cached entry exists (**hit**), CloudFront serves the response without contacting the origin.
5. If no valid cache entry exists (**miss**), CloudFront sends an **origin request** per policy to fetch content; the response may be cached depending on request type and TTL settings.

CloudFront uses a global edge network, yet **origins still have their own location, quotas, and protection mechanisms**. CloudFront does not replace the fault tolerance of databases, applications, ALBs, or Regions. When an origin goes down, uncached content or dynamic requests will still fail without a suitable failover architecture.

### 2.1. Cache Hit, Cache Miss, and Cache Expiry

| Concept | Explanation | Impact |
|---|---|---|
| **Cache hit** | A response matching the cache key already exists and is still valid | Reduces latency and origin load |
| **Cache miss** | No valid cached entry exists or the request must query the origin | Costs origin requests and potentially origin bandwidth |
| **TTL** | Duration CloudFront considers cached content fresh per policy/headers | Longer TTL can raise hit ratio but slows content updates |
| **Cache key** | Set of attributes distinguishing variants of a response | Overly broad keys hurt hit rate; overly narrow keys risk serving wrong variants |
| **Invalidation** | Request telling CloudFront to purge cached objects by path | Fetches fresh content before TTL expiry; may incur charges |

**Do not confuse:** DNS TTL in Route 53 or your DNS provider is **different** from CloudFront cache TTL. DNS TTL governs how long domain records are cached; CloudFront TTL governs content freshness at the CDN.

## 3. CloudFront Distribution: Key Components

A distribution is the top-level resource organizing origins, behaviors, and viewer access. A typical standard distribution contains:

| Component | Example | Purpose |
|---|---|---|
| **Distribution ID** | E123EXAMPLEID | Administrative identifier for API/CLI |
| **Distribution domain name** | d111example.cloudfront.net | CloudFront-assigned domain name |
| **Alternate domain names** | www.example.com | Organization's domain names requiring certificates/DNS |
| **Viewer certificate** | ACM certificate for www.example.com | TLS between viewers and CloudFront |
| **Origins** | S3 bucket, ALB | Sources of content/applications |
| **Default cache behavior** | **\*** | Mandatory fallback rule when no other behavior matches |
| **Ordered cache behaviors** | /assets/*, /api/* | Path-based rules evaluated in explicit order |
| **Security/logging** | AWS WAF, access logs | Protection, traffic recording, and incident analysis |

When creating or updating a distribution, changes must **propagate across CloudFront**; status may remain **InProgress** before reaching **Deployed**. Thus saving a new config does not mean every edge location applies it instantaneously.

### 3.1. Custom Domains, DNS, and HTTPS

To serve **https://www.example.com**, you need:

1. Add **www.example.com** to the distribution's **Alternate domain names**.
2. Attach a valid certificate covering that domain. **ACM certificates used for CloudFront viewers must reside in Region us-east-1** (US East – N. Virginia).
3. Create the appropriate DNS record. With **Route 53**, use an **A/AAAA Alias** pointing to CloudFront; external DNS providers typically use CNAME for subdomains.
4. Verify the **viewer protocol policy** to enforce HTTPS, the TLS security policy, and allowed HTTP versions.

A **zone apex** such as **example.com** cannot use a standard CNAME per DNS rules; Route 53 supports **Alias A/AAAA** at the apex. If enabling IPv6 for viewers, verify the corresponding AAAA record. Using CloudFront does not require Route 53; you can manage DNS at another provider as long as domain requirements are met.

### 3.2. Viewer Protocol and Origin Protocol Are Two Separate Hops

~~~mermaid
flowchart LR
    U["Viewer"] -->|"Hop 1:<br/>HTTPS to CloudFront"| C["CloudFront"]
    C -->|"Hop 2:<br/>HTTPS to custom origin"| O["ALB / custom origin"]
~~~

- **Viewer protocol policy** on a cache behavior can allow HTTP/HTTPS, **Redirect HTTP to HTTPS**, or require **HTTPS Only**.
- **Origin protocol policy** on a **custom origin** controls whether CloudFront connects to the origin using HTTP Only, HTTPS Only, or Match Viewer as supported.
- With an **S3 bucket origin + OAC** configured with **Sign requests (recommended)**, CloudFront signs requests to S3 and uses HTTPS accordingly.

Enabling HTTPS between viewer and CloudFront **is not enough** if CloudFront → custom origin remains HTTP and sensitive data requires end-to-end encryption. When enabling HTTPS to a custom origin, the origin's certificate must be valid and match the domain name used to connect, or **502 Bad Gateway** errors can occur.

## 4. Origins: Where Source Content Comes From

### 4.1. Common Origin Types

| Type | Example | Best Suited For | Things to Verify |
|---|---|---|---|
| **S3 bucket origin** | Bucket with images, CSS, JS, docs served via CloudFront | Static assets and object content | **OAC**, bucket policy, KMS, object keys, cache headers |
| **Custom origin: ALB** | Java Spring Boot on EC2/ECS behind ALB | APIs, dynamic SSR/HTML | Origin HTTPS, SG/WAF, target health, timeouts |
| **Custom origin: HTTP server** | Reverse proxy or on-prem system with a reachable endpoint | App migrations or hybrid setups | DNS, Internet/private paths, TLS, origin capacity |
| **Custom origin: API endpoint** | API Gateway or compatible HTTP backend | Static/dynamic APIs | **Host** header, authorization, stage/path, caching |
| **Origin group** | Primary and secondary origins | Failover when primary fails within supported scope | Status codes, HTTP methods, data compatibility |

A distribution can have **multiple origins**, while **each cache behavior targets one origin or origin group**. CloudFront does not automatically guess that **/api/** belongs to ALB and **/images/** belongs to S3; the architect must configure behaviors and origin IDs explicitly.

### 4.2. S3 Bucket Endpoint vs. S3 Website Endpoint

This is a critical security distinction:

| Approach | Treated by CloudFront As | Access Protection |
|---|---|---|
| **Standard S3 bucket origin** | S3 origin | Can use **Origin Access Control (OAC)** with signed requests; bucket can stay private |
| **S3 static website endpoint** | **Custom origin** | **Does not support OAC/OAI** on website endpoints; requires public access design and appropriate restrictions |

For static websites serving HTML/CSS/JS, the recommended choice is usually a **private S3 bucket + CloudFront OAC**, rather than opening a public bucket just for the CDN to read. If you need website-endpoint-specific features such as S3 website hosting redirects, weigh the access-control trade-off and consider handling redirects/rewrites in CloudFront or the application instead.

### 4.3. Origin Access Control (OAC) for Private S3

**OAC** lets CloudFront sign requests to S3 using the CloudFront service principal. The bucket policy can restrict read access to **one specific distribution** via the **AWS:SourceArn** condition.

Example **read-only** bucket policy (illustrative account/distribution/bucket; replace with real ARNs):

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowCloudFrontReadWithOAC",
      "Effect": "Allow",
      "Principal": {
        "Service": "cloudfront.amazonaws.com"
      },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::web-assets-demo-example/*",
      "Condition": {
        "StringEquals": {
          "AWS:SourceArn": "arn:aws:cloudfront::111122223333:distribution/E123EXAMPLEID"
        }
      }
    }
  ]
}
~~~

The condition in the example restricts CloudFront access to that exact distribution. At the same time, you must:

- Create the OAC, attach it to the **S3 bucket origin**, select the appropriate **Sign requests** option (**always** recommended), update, and wait for distribution deployment.
- Configure S3 **Block Public Access** appropriately and verify object ownership, bucket policy, and object keys.
- If objects use **SSE-KMS** with a customer managed key, verify the **KMS key policy** allows CloudFront to use the key per AWS guidance.
- Never accidentally leave overly permissive bucket policies or public ACLs in place after switching to OAC.

**OAC does not mean only authenticated users can view the content.** OAC only locks down **CloudFront → S3 origin**; if viewers are unrestricted, anyone who knows the CloudFront URL can still fetch the delivered content. For paid/private content, enforce viewer-layer controls such as **signed URLs/signed cookies**, application auth, or equivalent mechanisms.

### 4.4. Custom Origins and Origin Path

For **ALBs**, **API endpoints**, or HTTP servers, configure:

- **Origin domain name** matching DNS and TLS certificate.
- Appropriate **Origin protocol policy** and ports/timeouts.
- **Origin path** if a fixed prefix must be prepended to paths sent to the origin.
- Forwarded headers, security groups/firewalls, networking, and origin availability.

For example, a custom origin with **Origin path = /backend** receiving viewer request **/api/products** forwards **/backend/api/products** to the origin. Do not treat **Origin path** as a rewrite that strips **/api**; if the backend only expects **/products**, use an appropriate rewrite mechanism or adjust the backend config.

**Protecting an ALB origin:** restrict direct Internet access to the origin where possible, and apply TLS, WAF, and network policies. CloudFront does not automatically hide or close Internet-reachable origin endpoints. With private origin/VPC origin models where supported, verify specific requirements and architectural constraints.

### 4.5. Origin Groups and Failover

For origin redundancy, create an **origin group** with **primary** and **secondary** origins and attach it to a cache behavior. On a **cache miss**, when primary returns a configured error status code or hits a connection/timeout error, CloudFront can send the request to secondary.

HTTP status codes selectable for failover per CloudFront docs include **400, 403, 404, 416, 429, 500, 502, 503, 504**. **Never blindly enable 403/404 as failover triggers**: 403 can be legitimate authorization denial, and 404 can be a genuinely missing object.

**Important constraint:** origin failover normally applies only to **GET, HEAD, and OPTIONS**, **not POST, PUT, PATCH, DELETE**. CloudFront does not synchronize data between two origins or guarantee consistency. Write-heavy APIs/uploads require their own backend recovery architecture.

## 5. Cache Behaviors: Choosing Paths and Request Handling

Every standard distribution has a mandatory **default cache behavior**. You can add **ordered cache behaviors** with distinct **path patterns**. A typical behavior specifies:

| Attribute | Role | Example |
|---|---|---|
| **Path pattern** | URL paths matching this behavior | **/assets/\***, **/api/private/\*** |
| **Target origin / origin group** | Destination for origin requests on cache miss | S3 assets or ALB API |
| **Viewer protocol policy** | HTTP/HTTPS requirement | Redirect HTTP to HTTPS |
| **Allowed HTTP methods** | Methods CloudFront accepts and can forward | GET/HEAD/OPTIONS or all methods |
| **Cached HTTP methods** | Methods eligible for caching | GET/HEAD, optionally OPTIONS |
| **Cache policy** | Min/default/max TTL and cache key | Managed CachingOptimized or custom |
| **Origin request policy** | Values sent to origin without entering the cache key | Specific headers, cookies, query strings |
| **Response headers policy** | Headers added/modified on responses | CORS, HSTS, security headers |
| **Edge functions** | Custom request/response logic if needed | URL rewrites, lightweight request checks |

### 5.1. Path Pattern Order Matters Greatly

CloudFront evaluates **ordered cache behaviors in configured order** and uses the **first matching behavior**. If none matches, CloudFront falls back to the default behavior **\***.

Example sensible ordering for an application:

| Order | Path Pattern | Origin | Recommended Policy |
|---|---|---|---|
| 1 | **/api/private/\*** | ALB | Do not cache user data; forward needed auth info |
| 2 | **/api/public/\*** | ALB | Cache GET endpoints only if responses are non-personalized |
| 3 | **/assets/\*** | S3 | Long TTL, versioned/hashed filenames |
| 4 | **/api/\*** | ALB | Caching disabled by default for remaining APIs |
| Default | **\*** | S3 or web origin | HTML, other routes; TTL per content policy |

For instance, **/api/private/profile** matches behavior #1. If **/api/\*** were placed ahead of **/api/private/\***, the request would match the broad behavior first and receive the wrong policy. CloudFront **does not automatically prioritize more specific paths** if you order them backward.

Path patterns match mainly on the **URI path**, not query strings, when selecting a behavior. To vary responses by **?language=vi**, configure the **cache key/query string policy** inside the behavior.

**Security risk:** if a broad behavior allows public caching or omits viewer auth headers, a sensitive behavior placed below it may never execute. Always test overlapping path patterns.

### 5.2. Allowed Methods and Cached Methods Differ

Common CloudFront allowed methods presets:

- **GET, HEAD**.
- **GET, HEAD, OPTIONS**.
- **GET, HEAD, OPTIONS, PUT, PATCH, POST, DELETE**.

Only **GET, HEAD**, and optionally **OPTIONS** are cached per configuration. Allowing **POST/PUT/PATCH/DELETE** does not make CloudFront cache write responses. For write APIs, allow the required methods, forward needed bodies/headers, and enforce authorization at the origin.

**OPTIONS** is commonly used for CORS preflight. If caching OPTIONS, make sure the cache key and CORS response vary properly by **Origin** or required request headers; otherwise you risk returning CORS headers intended for a different caller.

## 6. Three Policy Groups: Cache, Origin Request, Response Headers

This is the most commonly confused part of CloudFront setups:

| Policy | Controls | Affects Cache Key? |
|---|---|---|
| **Cache policy** | Min/default/max TTL, headers/cookies/query strings in cache key, compression options | **Yes** |
| **Origin request policy** | Headers/cookies/query strings sent to origin **in addition** to cache key values | **No** |
| **Response headers policy** | CORS headers, security headers, and custom response headers returned to viewers | **No** |

### 6.1. Cache Policy Determines the Cache Key

The cache key determines when two requests can share a cached object:

- **Headers**: e.g., varying responses by a specific header.
- **Cookies**: include only cookies that genuinely alter response content.
- **Query strings**: e.g., **lang=vi**, **size=small** if they change the response.
- **Compression support**: CloudFront handles/caches gzip/Brotli variants as configured and supported.

Including **all cookies**, **all headers**, or **all query strings** in the cache key explodes cache variants, lowering hit ratio and increasing origin load. Conversely, **omitting an attribute that changes the content from the cache key** can serve the wrong user's data or wrong language/format.

**Design rule:** include in the cache key **every attribute that changes the response**, and never cache personalized data without proving strict variant isolation and security.

### 6.2. Origin Request Policy Determines Info Sent Only to the Origin

A cache policy automatically forwards headers/cookies/query strings **already included in the cache key**. An origin request policy adds fields the backend needs without **creating cache variants**.

For example, suppose the backend logs a CloudFront geolocation header, while the image returned is identical for every country. You can forward that header via an origin request policy without adding it to the cache key—provided the origin truly returns the exact same response. If the backend alters content by country, you must include it in the **cache key** or disable caching for that flow.

**Important relationship:** when using an **origin request policy**, the behavior must use a **cache policy**; the two policies work together rather than blocking each other as independent filters.

### 6.3. Response Headers Policy

A response headers policy can add or modify:

- **CORS**: Access-Control-Allow-Origin, allowed methods/headers, and max-age when configured.
- **Security headers**: HSTS, X-Content-Type-Options, Content-Security-Policy, Referrer-Policy, etc.
- **Custom headers**: organization-defined headers.

These policies control headers returned to the viewer; they **do not modify object data at the origin** and **do not replace authentication/authorization**. A CORS policy allows browsers to read cross-origin responses under defined conditions, but does not grant API permissions by itself.

### 6.4. Example Avoiding Policy Confusion

Suppose **GET /catalog?lang=vi** and **GET /catalog?lang=en** return different content.

| Configuration | Outcome |
|---|---|
| Do not forward **lang** | Origin may not know which language was requested |
| Forward **lang** via origin request policy only | Origin receives `lang` on **cache miss**, yet cached response may be shared across languages |
| Include **lang** in **cache key** | Each language gets its own cache entry, and `lang` is forwarded to origin automatically |
| Disable caching | Every request goes to origin; useful when content cannot be safely cached |

## 7. TTL and Cache-Control: Balancing Performance and Freshness

### 7.1. Minimum, Default, and Maximum TTL

A cache policy has three parameters:

| Parameter | Meaning |
|---|---|
| **Minimum TTL** | Minimum duration CloudFront retains a cached object before revalidating |
| **Default TTL** | TTL used when the origin **omits** Cache-Control/Expires headers |
| **Maximum TTL** | Upper bound on cache duration even if the origin specifies a larger lifetime |

An origin may return:

~~~http
Cache-Control: public, max-age=300
~~~

In standard cases, CloudFront combines the response directive with the cache policy's min/max TTL bounds to compute cache duration. If the origin omits Cache-Control/Expires, **Default TTL** applies. Account for both **browser cache** and **CloudFront edge cache**; clearing the edge does not automatically evict browser caches.

### 7.2. Security Warning: Minimum TTL Greater Than 0

**If Minimum TTL > 0, CloudFront can cache responses for at least that duration even when the origin sends `Cache-Control: no-cache, no-store, or private`.** Therefore, for personal data, auth responses, or non-shareable content:

1. Prefer the **managed cache policy CachingDisabled** or a custom policy with **min/default/max TTL all set to 0** when disabling caching on a behavior.
2. Thoroughly review **Authorization, Cookie, session** handling and response variations; forward only what is needed.
3. Never rely solely on **Cache-Control: private** while the cache policy still has **Minimum TTL > 0**.
4. Test with two independent users receiving different content, covering both cache hit and cache miss cases.

### 7.3. TTL Strategy by Resource Type

| Resource | Recommended Strategy | Why |
|---|---|---|
| **/assets/app.ab12cd.js** | Long TTL, hashed/versioned filename | Content is effectively immutable; new releases use a new URL |
| **/index.html** | Short TTL or frequent revalidation | Ensures browsers quickly discover new asset URLs |
| **/api/public/catalog** | Short TTL if data is shareable | Reduces API load with bounded staleness |
| **/api/private/profile** | CachingDisabled | Prevents risking cross-user leakage of private responses |
| **/api/orders POST** | Forward requests; do not cache writes per standard HTTP cache semantics | Verify auth, idempotency, and backend handling |

**A long TTL does not mean "impossible to update"**: you can version asset filenames or run invalidations; however, if the URL stays the same, stale cached copies may persist until expiry or invalidation.

### 7.4. Error Response Caching

CloudFront can cache certain error responses such as **403/404/5xx** under **error caching** and **Error Caching Minimum TTL**. Consequently, even after fixing a bucket policy or uploading a missing object, users may keep seeing the old error briefly.

When this happens, verify that the origin now returns valid data, inspect TTL and error-caching settings, and wait for expiry or run a targeted invalidation. Do not jump to blaming DNS when CloudFront is simply serving a cached error response.

## 8. Reference Design: S3 Assets and API Through ALB

Suppose an e-commerce app has a static frontend and a Java Spring Boot backend:

~~~mermaid
flowchart TB
    V["Viewer<br/>shop.example.com"] --> CF["CloudFront distribution<br/>HTTPS / WAF"]
    CF -->|"assets/* → long cache"| S3["S3 private bucket<br/>OAC"]
    CF -->|"api/public/* → short GET cache"| ALB["ALB"]
    CF -->|"api/private/* → cache disabled"| ALB
    ALB --> ASG["EC2 Auto Scaling Group<br/>Spring Boot"]
    ASG --> DB["RDS / DynamoDB"]
~~~

### 8.1. Behavior Design Matrix

| Path Pattern | Origin | Cache Policy | Origin Request Policy | Allowed Methods |
|---|---|---|---|---|
| **/api/private/\*** | ALB | **CachingDisabled** | Forward headers/cookies/queries needed for auth/backend | All methods required by API |
| **/api/public/\*** | ALB | Short cache, keyed by queries that alter content | Forward only metadata needed by origin | GET/HEAD (plus OPTIONS if using CORS) |
| **/assets/\*** | S3 | **CachingOptimized** or equivalent | Typically no need to forward cookies/auth | GET/HEAD |
| **Default \*** | S3 or web origin | TTL appropriate for HTML/SPA and routing | Application-dependent | GET/HEAD |

**This example illustrates the design pattern only.** `CachingOptimized` has a Minimum TTL greater than 0; never attach it to private data merely for "performance optimization." Even for public APIs, if they accept **Authorization** or vary per user, re-evaluate the "public" assumption before caching.

### 8.2. SPA HTML and Fallback

A Single Page Application with routes like **/products/123** may need **index.html** returned so the client-side router handles the route. With a private S3 origin, requests to nonexistent objects sometimes return **403** instead of 404 depending on permissions and request type.

**Do not blindly apply a global custom error response `403 → index.html` across an entire distribution** that mixes APIs and S3: API "forbidden" errors could be masked as HTTP 200/HTML, breaking semantics and hindering security monitoring. Prefer path-scoped viewer rewrites, separate behaviors/origins, or a tightly controlled and tested fallback strategy.

## 9. Cache Optimization, Invalidation, and Content Deployment

### 9.1. Use Versioned/Hashed Filenames

For static assets:

~~~text
/assets/app.3f2a1c.js
/assets/styles.a17bb4.css
/images/logo.v5.png
~~~

Immutable filenames can carry long TTLs. On new releases, publish new URLs and update HTML references. This is generally safer than overwriting the same filename and trying to invalidate every cache—especially since client browsers and proxies keep their own caches.

For **index.html**, use a short TTL or appropriate revalidation. When browsers fetch the updated HTML, they immediately pick up the new asset filenames.

### 9.2. When to Use Invalidation?

**Invalidation** instructs CloudFront to remove selected cached paths so the next request fetches fresh content from the origin. Use it only when needed:

- Urgent hotfixes at the same URL while a long TTL remains active.
- Purging broken or sensitive content cached unexpectedly, alongside fixing the underlying security root cause.
- Updating resources that do not use versioned filenames.

Invalidations have quotas and path-based pricing; manage them carefully in release pipelines rather than invalidating the entire distribution on every commit.

### 9.3. CloudFront Functions, Lambda@Edge, and Origin Shield

Additional capabilities:

- **CloudFront Functions**: lightweight edge logic, such as URL normalization/rewrites or simple manipulation at supported viewer events.
- **Lambda@Edge**: supports heavier logic at supported CloudFront events, including certain origin request/response customizations.
- **Origin Shield**: an optional additional caching layer chosen by Region to consolidate and reduce repeated origin requests in suitable architectures.

Each has **its own limits, pricing, and deployment behavior** and does not replace proper cache behaviors or application design. A buggy rewrite function can misalign cache keys and routing; test functions thoroughly.

## 10. Securing a CloudFront Distribution

### 10.1. Split Security into Two Hops

| Hop | Questions | Controls |
|---|---|---|
| **Viewer → CloudFront** | Who may access content? Are requests malicious? | HTTPS, WAF, signed URLs/cookies, rate-based rules, auth |
| **CloudFront → origin** | Can only CloudFront or authorized systems reach the origin? | S3 OAC + bucket policy, origin TLS, ALB/network protection |

**AWS WAF** can attach to CloudFront to enforce web protection rules. **AWS Shield Standard** provides baseline DDoS protection per service scope. These controls strengthen defense but do not guarantee stopping every attack, nor do they fix broken app authorization or bucket policies.

### 10.2. Signed URLs and Signed Cookies

For restricted files such as paid videos, reports, or subscriber content, CloudFront supports **signed URLs** and **signed cookies** via trusted key groups/signing keys:

- **Signed URL**: suited for granting access to a single specific URL or resource.
- **Signed cookie**: suited for granting access across a set of resources when a client fetches multiple URLs.

Signature expiration, URL/path policies, private key security, and cookie protection remain the issuing system's responsibility. Signed URLs/cookies **do not replace business authentication**, nor do they make an S3 origin private if the bucket policy still grants direct public access.

### 10.3. Never Cache Private Data Under a Shared Cache Key

Dangerous scenario:

1. User A sends GET **/api/me** with a session cookie or Authorization header.
2. Origin returns User A's personal data.
3. CloudFront caches the response with a cache key containing only the path **/api/me**.
4. User B sends GET to the same path and receives User A's response from cache.

Therefore, for personalized endpoints use **CachingDisabled** and forward required auth credentials—unless the engineering team has a proven, security-tested per-user cache isolation design. Adding all cookies to the cache key just to "be safe" does not automatically solve auth, cost, or cache cardinality issues.

### 10.4. Geo Restriction Is Not Data Residency

CloudFront supports restricting viewer access by country where appropriate. However, **setting geo restrictions does not mean data is stored, processed, or cached exclusively inside that country/Region**. For data residency and personal data compliance, verify data handling, logs, origin Regions, CDN behavior, and legal policies end to end.

## 11. Inspecting Distributions with AWS CLI and HTTP

The commands below inspect resources or run explicit invalidations. IDs/domains are illustrative—substitute resources you manage. CloudFront distribution management APIs are global; do not confuse them with the Region of S3/ALB origins or the ACM viewer certificate.

### 11.1. List and Read Distribution Configurations

~~~bash
# List distributions the account is permitted to view.
aws cloudfront list-distributions \
  --query 'DistributionList.Items[].{Id:Id,Domain:DomainName,Status:Status,Enabled:Enabled}' \
  --output table

# Read the saved configuration of a specific distribution.
aws cloudfront get-distribution-config \
  --id E123EXAMPLEID \
  --query 'DistributionConfig.{Origins:Origins.Items,Default:DefaultCacheBehavior,Ordered:CacheBehaviors.Items}' \
  --output json
~~~

Inspect the actual **origins**, **TargetOriginId**, **PathPattern**, **CachePolicyId**, **OriginRequestPolicyId**, **ViewerProtocolPolicy**, and **AllowedMethods**. If a behavior lacks a modern cache policy ID, it may use legacy cache settings; review before migrating.

### 11.2. Create a Controlled Invalidation

~~~bash
# Replace with real distribution ID. This command mutates cache state.
aws cloudfront create-invalidation \
  --distribution-id E123EXAMPLEID \
  --paths "/index.html" "/assets/*"
~~~

The command returns an invalidation ID and status. To check a specific invalidation:

~~~bash
aws cloudfront get-invalidation \
  --distribution-id E123EXAMPLEID \
  --id I123EXAMPLEID
~~~

Invalidate only required paths; prefer versioned filenames for frequently released assets. Depending on urgency and cost, waiting for TTL expiry may be preferable to running invalidations.

### 11.3. Inspect HTTP Responses

~~~bash
# Run from an authorized test environment; replace with your real domain.
curl -I "https://www.example.com/assets/app.3f2a1c.js"

# Check a public endpoint and response headers.
curl -i "https://www.example.com/api/public/catalog?lang=vi"
~~~

Useful headers include **Cache-Control**, **Age**, **X-Cache**, **Via**, **Content-Encoding**, **Access-Control-Allow-Origin**, **Strict-Transport-Security**, and HTTP status code. **X-Cache: Hit from cloudfront** indicates a cache hit, though results depend on the edge POP, cache key, location, and timing. Two consecutive requests do not guarantee the second is a hit—especially with TTL = 0 or policies creating distinct variants.

Never test with real personal data or log full Authorization headers/cookies in public debug output.

## 12. Monitoring and Performance Investigation

### 12.1. Metrics to Watch

CloudFront publishes monitoring metrics, which can include:

| Metric | Meaning | When to Investigate |
|---|---|---|
| **Requests** | Number of viewer requests | Unexpected load spikes requiring origin scaling |
| **BytesDownloaded / BytesUploaded** | Traffic between CloudFront and viewers | Rising transfer costs or oversized payloads |
| **4xxErrorRate** | Share of client-side errors returned to viewers | S3 permissions, bad requests, missing objects, WAF/auth blocks |
| **5xxErrorRate** | Share of server/edge errors returned to viewers | Origin failures, TLS/timeouts, overloaded backends |
| **TotalErrorRate** | Combined error rate metric | Overall health overview |
| **CacheHitRate** | Share of requests served from cache per metric definition | Overly fragmented cache keys, suboptimal TTLs |
| **OriginLatency** | Latency for CloudFront to get origin responses | Slow ALB/backend/database or network issues |

Some detailed metrics such as **CacheHitRate/OriginLatency** require enabling **additional CloudWatch metrics** and may incur extra charges; check current configuration. Distribution-wide metrics can hide failures on a specific path or request type; combine with access logs and origin monitoring.

### 12.2. Standard Logs and Real-Time Logs

- **Standard access logs** help analyze request paths, statuses, user agents, cache outcomes, and traffic flows per supported log delivery.
- **Real-time logs** deliver lower-latency log records per configured sampling/fields, requiring their own pipeline design and cost budget.
- **ALB logs, application logs, S3 access logs/CloudTrail, WAF logs** provide complementary evidence at the origin or security layers.

When enabling logging, audit **PII, IP addresses, cookies, query strings, and credentials** to avoid inadvertently storing sensitive data. Restrict access to log destinations, set retention, and collect only necessary fields.

### 12.3. Procedure for Investigating a Slow URL

1. Capture the exact **URL, method, query, Host, timestamp, and user region**.
2. Identify the first matching behavior, target origin, cache policy, and TTL.
3. Inspect **X-Cache, Age, latency**, request counts, and logs to distinguish hits from misses.
4. On misses, measure **origin latency**, ALB target health, app performance, database I/O, and networking.
5. Verify the cache key does not include unnecessary cookies/headers/query parameters.
6. Fix the policy or application root cause, test across multiple edges/users, and monitor cost and performance afterward.

## 13. Common Errors and Troubleshooting

| Symptom | Possible Cause | Check First |
|---|---|---|
| **403** with private S3 | Missing OAC, wrong bucket policy/SourceArn, KMS permissions, or missing object without ListBucket | S3 origin type, OAC signing, bucket/KMS policy, exact object key |
| **403** on an API route | WAF, backend auth, misordered behavior, or origin Deny | WAF logs, access logs, path pattern order, API auth |
| **404** despite newly uploaded asset | Wrong path, origin path prefix, object key, or cached 404 | S3 key, behavior, TTL/error caching, invalidation |
| **502 Bad Gateway** | Origin TLS certificate mismatch, SSL handshake, DNS, or origin protocol error | Origin domain, certificate, listener, port, DNS |
| **503/504** | Origin overloaded, connection/response timeout, unhealthy backend | ALB/EC2 metrics, origin timeout, autoscaling, app logs |
| **Wrong origin for /api/private/\*** | Broader **/api/\*** behavior placed ahead of it | Fix ordered cache behaviors sequence |
| **X-Cache always Miss** | Caching disabled, low TTL, high-cardinality cache key, different edge POPs | Cache policy, query/cookie/header settings, origin Cache-Control |
| **User B sees User A's data** | Personalized response cached under a shared cache key | Disable caching immediately on sensitive behavior; audit auth and logs |
| **CORS fails only for some users** | Cached OPTIONS/response does not vary on Origin, or wrong response headers policy | Origin/CORS headers, OPTIONS caching, cache key, policy |
| **Stale content still appears** | Edge TTL, browser cache, stale responses, or pending invalidation | Cache-Control, Age, versioned assets, invalidation status |
| **Direct ALB works yet fails via CloudFront** | Origin path, Host header, TLS, allowed methods, origin request policy | Compare actual request reaching origin vs. CloudFront config |
| **Origin group does not fail over POST** | Origin failover supports only GET/HEAD/OPTIONS | Design backend failover, replication, and idempotent retries for writes |
| **Costs jump after adding CDN** | Too many cache variants, logs, invalidations, origin shield, or WAF charges | Billing, CacheHitRate, request counts, pricing |

## 14. Safe CloudFront Deployment Workflow

### Step 1 — Classify Content

Categorize paths into **static immutable assets**, **frequently updated HTML**, **cacheable public APIs**, **personalized APIs**, **write methods**, and **media/large files**. Document auth requirements, acceptable TTLs, cache keys, and sensitivity per category.

### Step 2 — Choose and Protect Origins

For static assets, choose a private S3 bucket and **OAC**; for APIs, choose an ALB/API endpoint with TLS and scaling. If origins span multiple Regions, define DR flows and data consistency; origin groups handle failover only for supported methods and status codes.

### Step 3 — Create Distribution and Domain

Create the distribution, define origins, certificates/alternate domains, viewer HTTPS, and WAF as needed. Configure Route 53 Alias or external DNS. Wait for distribution deployment to complete, then verify domain and TLS.

### Step 4 — Design Behaviors and Policies

Place specific and sensitive paths ahead of broad paths; attach the right origins, allowed/cached methods, and cache/origin request/response headers policies. For private responses, disable caching or prove strict per-user isolation. Always inspect **Minimum TTL** before promoting to production.

### Step 5 — Run Safe Request Tests

Test cache hits/misses, CORS OPTIONS, GET with query strings, different path patterns, 404 files, API 401/403, origin 502/503/504, HTTP-to-HTTPS viewer redirects, and HTTPS to origins. Test with two separate user accounts to catch accidental cross-user cache leaks.

### Step 6 — Integrate CI/CD and Operational Observability

Use hashed/versioned asset filenames, deploy HTML after assets, run selective invalidations, and review configs as code (CloudFormation/Terraform/CDK where appropriate). Enable required metrics/logging, monitor costs, and keep a rollback plan for misconfigured policies/behaviors.

## 15. Scenario Practice

### Scenario A — Static S3 Website with Security Requirements

A team stores HTML, CSS, and JS files in S3 and wants global delivery via CloudFront without making the bucket public.

**Question:** which origin type should they create, and how should access be configured?

**Hint:** use an **S3 bucket origin** with **OAC**, enable request signing, restrict the bucket policy to the CloudFront service principal with **AWS:SourceArn** matching the distribution, keep Block Public Access enabled, and configure SSE-KMS permissions if encrypted. Do not pick an S3 website endpoint when OAC is needed.

### Scenario B — `/api/me` Accidentally Cached

An API returns user profiles based on a session cookie. The deployment team used a static-asset-optimized cache policy and attached it to all of **/api/\***.

**Question:** what is the risk, and what needs fixing?

**Hint:** User A's response can be served to User B if the cache key does not isolate sessions. Add a **/api/private/\*** behavior ahead of **/api/\***, apply **CachingDisabled**, forward required auth/cookies, verify **Minimum TTL = 0**, and test with two accounts. Never simply add Cookie to an origin request policy while leaving a shared cache key.

### Scenario C — Same API, Two Languages

**GET /api/public/catalog?lang=vi** and **?lang=en** return different payloads. The origin request policy forwards all query strings, but the cache policy omits **lang** from the cache key.

**Question:** why might users receive the wrong language?

**Hint:** both requests share the same cache key. Add **lang** to the cache policy so each language caches separately, and verify whether any other query parameters alter the response.

### Scenario D — Reversed Behavior Order

A distribution puts **/api/\*** before **/api/private/\***; the broad behavior forwards to the origin with a positive TTL. Private APIs have strict security requirements.

**Question:** which behavior applies, and how do you fix it?

**Hint:** CloudFront picks the **first matching behavior**, which is **/api/\***. Move **/api/private/\*** above it, attach the appropriate cache and auth policies, and test URLs with query strings too.

### Scenario E — New Deploy Yet Users Still See Old JS

CI/CD overwrites **/assets/app.js**, while CloudFront caches that file with a long TTL. Even after invalidation, some users still see the old version in their browsers.

**Question:** what should change in the long-term deployment strategy?

**Hint:** use hashed/versioned filenames (e.g., **app.f2c9a1.js**), keep long TTLs on immutable assets, use short caching/revalidation on HTML, and run invalidations only when truly necessary. Edge invalidations do not force browsers or client proxies to purge their local caches.

### Scenario F — Primary Origin Fails During a User POST

An app submits orders via POST and sets up a CloudFront origin group with primary/secondary ALBs configured to fail over on 503.

**Question:** does CloudFront automatically forward the POST to secondary?

**Hint:** no—CloudFront origin failover normally supports only **GET, HEAD, and OPTIONS**. For write operations, design backend traffic failover, data sync, idempotent retries, and application recovery separately. Never blindly retry POST requests without idempotency, or duplicate orders can occur.

## 16. Pre-Production Checklist for CloudFront

- [ ] Classified static files, HTML, public APIs, private APIs, and write methods.
- [ ] Created distribution with valid origins, certificates/TLS, and Route 53/DNS records.
- [ ] Enabled **S3 OAC** where private origins are needed, with accurate bucket and KMS policies.
- [ ] Configured **ordered cache behaviors in the right sequence** and a sensible default behavior.
- [ ] Verified allowed methods, cached methods, and CORS OPTIONS handling.
- [ ] Confirmed which headers/cookies/query strings belong in the cache key vs. origin-only forwarding.
- [ ] Distinguished cache policy, origin request policy, and response headers policy.
- [ ] Verified min/default/max TTLs, checking **Minimum TTL > 0** against sensitive data.
- [ ] Verified viewer/origin HTTPS, certificates, WAF, OAC, and signed access if needed.
- [ ] Established versioned assets, invalidation, and deployment rollback strategies.
- [ ] Tested origin failover within supported HTTP methods and built DR for write APIs.
- [ ] Enabled monitoring for 4xx/5xx errors, latency, cache hit rate, and required logging.
- [ ] Confirmed geo restriction is not mistaken for data residency compliance.
- [ ] Budgeted for requests/data transfer, WAF, invalidations, origin shield, and logging.

## 17. Key Takeaways

A **CloudFront distribution** organizes domains, origins, behaviors, and policies; an **origin** supplies source content; a **cache behavior** routes paths and governs request handling. A **cache policy** defines TTL and cache keys; an **origin request policy** forwards extra data to the backend without altering cache keys; a **response headers policy** adds headers for viewers. For **private S3**, use **OAC** with a distribution-scoped bucket policy. For personal data, **never use a shared cache key** or positive Minimum TTL without proven isolation. Performance tuning must go hand in hand with **security, resilience, monitoring, and cost control**.

### Official AWS Documentation for Deployment Reference

- [CloudFront Developer Guide](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Introduction.html) — service overview.
- [CloudFront cache behavior settings](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/DownloadDistValuesCacheBehavior.html) — path patterns, methods, viewer protocol, policies.
- [CloudFront CacheBehavior API](https://docs.aws.amazon.com/cloudfront/latest/APIReference/API_CacheBehavior.html) — behavior ordering and TargetOriginId.
- [Understand cache policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/cache-key-understand-cache-policy.html) — TTL and cache keys.
- [Understand origin request policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/origin-request-understand-origin-request-policy.html) — headers, cookies, query strings sent to origin.
- [Understand cache and origin request policy combination](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/understanding-how-origin-request-policies-and-cache-policies-work-together.html) — interaction between both policies.
- [Response headers policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/understanding-response-headers-policies.html) — CORS/security headers.
- [Control how long content is cached](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Expiration.html) — Cache-Control and TTL.
- [Restrict access to an S3 origin with OAC](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html) — OAC, bucket policy, website endpoint limitations.
- [Origin failover](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/high_availability_origin_failover.html) — primary/secondary and HTTP methods.
- [Alternate domain names and certificates](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/CNAMEs.html) — DNS, certificates, and domain ownership.
- [Route 53 alias to CloudFront](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-to-cloudfront-distribution.html) — DNS routing to distributions.
- [Invalidate content](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Invalidation.html) — content versioning and invalidation.
- [CloudFront pricing](https://aws.amazon.com/cloudfront/pricing/) — request, data transfer, and optional feature pricing per applicable pricing model.
