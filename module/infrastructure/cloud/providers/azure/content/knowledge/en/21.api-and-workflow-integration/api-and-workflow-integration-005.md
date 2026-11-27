# Rate Limiting, Quotas, Caching, and Request Transformation

An ordering system on Microsoft Azure may serve APIs to web apps, mobile devices, and partners. During peak hours, one client sends too many requests and overloads the backend. Another partner exceeds its monthly call allowance. Product catalog screens repeatedly read the same data, causing redundant database queries. Meanwhile, an older API version sends the field **`customer_id`**, whereas the new backend expects **`customerId`**.

These four needs have corresponding solutions: **rate limiting**, **quotas**, **caching**, and **request transformation**. On Azure, **Azure API Management (APIM)** provides a policy engine to handle these behaviors at the API gateway without rewriting every client. However, configuring the gateway properly does not make the backend automatically secure: authentication, authorization, input validation, load measurement, and consistency design are still required.

This lesson belongs to the **API and Workflow Integration** chapter of the **CLOUD_PROVIDERS_AZURE** module. This track explores Azure from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute, storage, and data, and then deploying, monitoring, securing, and controlling the cost of an application architecture.

> **Scope:** This lesson focuses on Azure API Management policies. The XML snippets below are illustrative examples that should be deployed first on a **test APIM/API**. Feature scope, capacity, caching, and behavior may vary by tier, gateway type, and service version; consult Microsoft Learn documentation before moving to production.

## Learning objectives

After this lesson, you will be able to:

1. Distinguish **rate limits** from **quotas** by protection goal, thresholds, and time windows.
2. Understand the policy pipeline **inbound → backend → outbound → on-error** and policy scopes.
3. Use **`rate-limit-by-key`** and **`quota-by-key`** with trustworthy identifier keys.
4. Design **response caching** with **`cache-lookup`** and **`cache-store`**, understanding TTL, cache keys, and cache invalidation.
5. Distinguish gateway response caching from application, CDN, or backend caching.
6. Use **`rewrite-uri`**, **`set-header`**, **`set-query-parameter`**, and **`set-body`** to transform requests.
7. Understand the impact of policy order, inheritance, authentication, sensitive data, and 429/403 errors.
8. Build a lab workflow, measure performance, diagnose errors, and estimate APIM costs.

## 1. Where does Azure API Management sit in the architecture?

**Azure API Management** is an API management platform in which a **gateway** receives requests from consumers and applies configured policies before forwarding to the backend. APIM also provides API definitions, products, subscriptions, a developer experience, and observability tools depending on the deployment model's capabilities.

~~~text
Web / mobile / partner applications
                 |
                 | HTTPS request
                 v
       Azure API Management
         +--------------------------+
         | Authentication/validation|
         | Rate limit / Quota       |
         | Request transformation   |
         | Cache lookup             |
         | Backend routing          |
         | Response transformation  |
         | Cache store              |
         +--------------------------+
                 |
                 v
        Azure App Service / AKS /
        Azure Functions / other backend
                 |
                 v
             Database / Storage
~~~

APIM can offload backends, standardize interfaces, and cap usage. It **does not replace**:

- Per-order access control checks in the backend.
- Transaction integrity and idempotency mechanisms.
- Database connection limits or downstream resource controls.
- Infrastructure-level DDoS protection, an appropriate WAF, and application observability.
- Cache-consistency design when underlying data changes.

### Gateway and management plane

| Component | Role |
|---|---|
| **APIM gateway** | Executes policies on live requests/responses |
| **Management plane/portal/API** | Creates APIs, operations, products, policies, and configurations |
| **Backend service** | Executes business logic, queries DBs, or calls other services |
| **Product/subscription** | Packages APIs and manages access/usage under the APIM model |
| **Diagnostics/monitoring** | Collects request metrics, errors, and telemetry per configuration |

Do not confuse permissions to manage an APIM instance in Azure Resource Manager with permissions to call an API through the gateway. Both permission layers can be controlled independently.

## 2. How do the four techniques differ?

| Technique | Question it answers | Target | Typical outcome |
|---|---|---|---|
| **Rate limit** | How fast at most can a client send requests? | Rate over a short window | Rejects excess traffic; typically returns **429 Too Many Requests** |
| **Quota** | How much total volume can a client consume in a period? | Total calls/bytes over a long window | Rejects once exhausted; APIM quota policies typically return **403 Forbidden** |
| **Cache** | Which requests can reuse a still-valid response without calling the backend? | Data/responses by key and TTL | Cache hits reduce latency and backend load |
| **Request transformation** | How must the gateway modify path/headers/query/body before calling the backend? | HTTP content and metadata | Backend receives a different contract or path |

**Rate limits and quotas are not synonymous.** A client allowed 10,000 calls/day can still overwhelm a backend by sending all 10,000 calls within a few seconds. Conversely, a client sending only 2 calls/second continuously all day can exhaust a monthly quota.

**Caching is not rate limiting.** Cache hits reduce backend load, but if the gateway itself still receives excessive requests, protect gateway resources or apply a dedicated rate limit.

**Transformation is not validation.** Renaming a JSON field does not prove that the field's value is valid, authorized, or safe.

## 3. APIM's policy pipeline

A typical policy document has four sections:

~~~xml
<policies>
  <inbound>
    <base />
    <!-- Authenticate, throttle, transform request, lookup cache -->
  </inbound>
  <backend>
    <base />
    <!-- Forward request to backend or backend policies -->
  </backend>
  <outbound>
    <base />
    <!-- Transform response, store in cache -->
  </outbound>
  <on-error>
    <base />
    <!-- Handle gateway/policy errors -->
  </on-error>
</policies>
~~~

### Roles of each section

- **Inbound:** processes incoming requests before the backend: token validation, throttling, URI/header/query/body edits, cache lookup.
- **Backend:** controls forwarding, backend selection, and retry/circuit-breaker policies per supported features.
- **Outbound:** processes outgoing responses: response headers/body, `cache-store`, stripping information not meant to be public.
- **On-error:** runs when policy/gateway execution hits an error per APIM semantics; not every backend HTTP error status is automatically handled here.

### Policy order matters

Policies within a section execute sequentially according to policy type. For example, to count every request toward the rate limit—including cache hits—the rate limit must appear **before `cache-lookup`**.

~~~text
Request
   |
   v
Validate identity
   |
   v
Rate limit / Quota
   |
   v
Rewrite/query/header transformation
   |
   v
Cache lookup
   | Hit                       | Miss
   v                           v
Cached response             Backend
                               |
                               v
                           Cache store
                               |
                               v
                            Response
~~~

This is a **conceptual model**. A cache hit can cause the gateway to return a response early and skip downstream backend/outbound steps per cache-policy behavior. Therefore, mandatory controls such as authentication, proper authorization, and throttling must run before the cache-return point if they apply to every request.

## 4. Policy scopes and inheritance via base

APIM policies can be applied at management scopes such as:

- **Global / all APIs** within the gateway/appropriate scope.
- **Workspace** when supported by the APIM model.
- **Product** for a bundle of APIs/consumers per product.
- **API**.
- **Operation**.

A policy at a specific scope inherits parent-scope policies via **`base`** per APIM rules. Where **`base`** is placed inside a section affects the logical execution order of policies.

### Example risk of omitting base

Suppose global scope enforces JWT validation and shared limits, while an operation adds only `rewrite-uri`. If the operation policy fails to inherit parent policies as expected, requests might bypass protections administrators assumed were active.

**Do not delete `<base />` just to make XML shorter.** Before changing anything, use the **effective policy** view or corresponding diagnostic tools to confirm which policies actually execute and in what order.

### Policy fragments

When many APIs share standard authentication and header rules, APIM supports reuse mechanisms such as **policy fragments** where available. Fragments prevent copying the same expression dozens of times, but any change to a fragment must be tested across **every place it is used**.

## 5. What is rate limiting?

A **rate limit** caps how many requests are permitted within a short interval, for example:

~~~text
Client A is allowed 60 requests / 60 seconds

Within the measurement window:
  1  ... 60: request accepted if other checks pass
  61       : may be rejected with HTTP 429

After the window elapses:
  counter resets to allow traffic again per policy
~~~

This example builds intuition; **it is not an exact description of every gateway's internal windowing algorithm**. APIM uses policy counters whose live behavior can experience synchronization lag or distribution effects, especially across multiple gateways/units/regions.

### Use cases

1. Protect backends from traffic bursts by a single client.
2. Maintain fair usage across partners.
3. Reduce impact from buggy clients looping requests infinitely.
4. Differentiate API product tiers: trial 5 req/s, commercial 50 req/s.
5. Prevent a single tenant from starving shared service capacity.

### Error code 429

When a rate limit rejects a request, the typical response is **429 Too Many Requests**. Clients should:

- Inspect retry hints such as **`Retry-After`** when provided by the gateway.
- Use exponential backoff with jitter.
- Avoid unconditional tight retries or spawning more parallel requests.
- Distinguish APIM 429s from backend 429s using diagnostics/correlation IDs.

Rate limits **do not** grant ongoing access if a token/JWT has expired or the client lacks read permissions.

## 6. The rate-limit-by-key policy

With multiple clients/tenants, bind counters to a **trustworthy identifier key** instead of counting all requests into one bucket.

Example:

~~~xml
<policies>
  <inbound>
    <base />
    <rate-limit-by-key
      calls="30"
      renewal-period="60"
      counter-key="@(context.Subscription?.Id ?? context.Request.IpAddress)" />
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
~~~

**Meaning:** illustrates a limit of 30 calls per 60-second window per key value. When the APIM request has **`Subscription.Id`**, the key uses the subscription ID; without a subscription, the example falls back to the request IP address.

### This is only a sample policy

In production, explicitly decide:

- Does the API **require a subscription**?
- Do clients use **validated JWTs** or API keys?
- Does one subscription represent one app, one partner, or many users?
- Should all anonymous requests ever share a single limit?
- Is there a reverse proxy/CDN causing multiple users to share one IP?

Using IP as a fallback **does not identify tenants accurately**: NAT can lump many users behind one IP, while a single user can rotate IPs.

### Never use self-declared headers as keys without validation

Dangerous example:

~~~xml
<!-- UNSAFE if the header is chosen by the client without verification -->
<rate-limit-by-key
  calls="30"
  renewal-period="60"
  counter-key="@(context.Request.Headers.GetValueOrDefault(&quot;X-Tenant-Id&quot;, &quot;unknown&quot;))" />
~~~

Clients can vary `X-Tenant-Id` on every request to evade the limit. Keys should come from verified subscriptions, validated token claims, or gateway-established trusted identities.

### Advanced options

APIM's `rate-limit-by-key` can support response headers and conditional counting attributes such as **`retry-after-header-name`**, **`remaining-calls-header-name`**, or **`increment-condition`/`increment-count`** depending on the policy. When exposing limit info to clients, use supported attributes rather than fabricating remaining counts.

**Note:** Counters may update post-response in certain `increment-condition` or distributed policy setups. Never use `rate-limit-by-key` as a **strict transactional lock** or guarantee that at every instant the exact final request will be blocked.

## 7. Rate limiting by subscription, product, and API

Beyond **`rate-limit-by-key`**, APIM offers **`rate-limit`** tied to subscriptions and products/APIs in supported models.

Conceptual example:

~~~xml
<rate-limit calls="10" renewal-period="60" />
~~~

In appropriate contexts, limits can be applied per API product—for example, lower limits in sandbox than production. However:

1. Policy scope alone does not establish caller identity; verify how the gateway resolves subscriptions.
2. If an API does not require a subscription, evaluate `rate-limit-by-key` with an appropriate identity.
3. Multiple products/subscriptions can yield differing counting behaviors.
4. Do not assume every policy/scope is supported identically across all tiers or self-hosted gateways.

When combining `rate-limit` and `rate-limit-by-key`, inspect the **effective policy** to avoid unintentionally double-counting.

## 8. What is a quota?

A **quota** limits **total consumption** over a period, such as:

- 50,000 API calls per day.
- 1,000,000 calls over a longer period within policy limits.
- Total bandwidth consumed over an interval where supported by the policy.

Example:

~~~text
Partner A:
  Quota = 10,000 calls / 24 hours
  Used  = 9,998

The next two valid calls exhaust the quota.
Subsequent calls are rejected until the quota renews.
~~~

Quotas fit **fair usage** and commercial tiers, but cannot replace rate limits for burst protection.

### Behavior when quota is exceeded

With APIM quota policies, the typical response when exhausted is **403 Forbidden**. Do not assume it is always 429 like rate limiting. When designing clients, check actual status codes, headers, and published API contracts.

**Quota 403** differs from **authorization 403**. Clients should not refresh tokens or immediately spam retries while the quota period remains open.

## 9. The quota-by-key policy

Example capping 10,000 calls over an 86,400-second window:

~~~xml
<policies>
  <inbound>
    <base />
    <quota-by-key
      calls="10000"
      renewal-period="86400"
      counter-key="@(context.Subscription?.Id ?? context.Request.IpAddress)" />
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
~~~

This is a **policy-driven window**, not necessarily “resetting at exactly 00:00 every day in Vietnam time” unless a matching start boundary is configured. Renewal period limits and options like **`first-period-start`** must be checked against your policy version.

### If per-tenant quotas are needed

If each tenant owns multiple subscriptions or applications, keying by **subscription ID** counts each subscription separately rather than enforcing a shared tenant budget. Extract the **verified tenant ID** or map subscriptions/apps authoritatively to a tenant and share that `counter-key`.

If the backend has entry points outside APIM, quotas on this gateway **do not automatically cover** requests arriving via other paths.

### Do not use quotas as the sole billing ledger

Quota policies are useful for usage caps, but contractual billing requires a **metering/audit pipeline** with proper consistency, deduplication, reconciliation, and business rules. Never use real-time quota counters as the sole source for customer invoicing.

## 10. Combining rate limits and quotas

Suppose an API defines:

- Rate limit: **30 calls / 60 seconds** per subscription.
- Quota: **10,000 calls / 24 hours** per subscription.

~~~text
Client calls API
      |
      v
Authenticate and resolve subscription/tenant
      |
      v
Rate limit: short-term threshold exceeded?
      | Yes -> return 429
      | No
      v
Quota: remaining budget in period?
      | No -> return 403 per quota policy
      | Yes
      v
Continue processing: cache/transform/backend
~~~

Example policy:

~~~xml
<policies>
  <inbound>
    <base />
    <rate-limit-by-key
      calls="30"
      renewal-period="60"
      counter-key="@(context.Subscription?.Id ?? context.Request.IpAddress)" />
    <quota-by-key
      calls="10000"
      renewal-period="86400"
      counter-key="@(context.Subscription?.Id ?? context.Request.IpAddress)" />
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
~~~

### Decisions to make

1. Do 4xx/5xx error responses count against limits?
2. Do cache hits count against quotas/rate limits?
3. Are limits tracked per user, application, subscription, or tenant?
4. Do premium and free customers share the same limits?
5. If one subscription calls multiple APIs, is the budget shared or separate?
6. Do multiple regions/gateways share counters as required?

In APIM, exact counter behavior depends on policy settings and placement. To count only requests meeting specific conditions, use actual policy attributes/capabilities rather than assuming counters automatically track “business success.”

## 11. Request counters do not equal concurrency limits

A requests-per-second rate limit may not stop this scenario:

~~~text
One request is admitted
     |
     v
Backend holds the connection for 10 minutes
     |
     v
Many similar slow requests pile up
~~~

An API with a low rate limit where each request takes a long time can still exhaust **connection pools, worker threads, or database sessions**. Conversely, many cached requests have far less backend impact.

Organizations should evaluate:

- **Concurrency limits** or resource caps at gateway/backend layers where available.
- Timeouts aligned with business operations.
- Queue-based load leveling for long asynchronous tasks.
- Circuit breakers, retry/backoff, and capacity-aware autoscaling.
- Load shedding on downstream databases and third-party APIs.

Rate limiting protects one dimension of load, not complete traffic orchestration.

## 12. What problem does API gateway caching solve?

Many GET APIs return identical responses across clients:

- Country lists, units of measure.
- Public product catalogs updated periodically.
- Public display configurations.
- Aggregated data not requiring second-by-second consistency.

If every request hits the backend and database, the system wastes time and resources.

~~~text
Client GET /catalog?category=books
              |
              v
       APIM cache lookup
         |          |
       HIT         MISS
         |          |
         v          v
   Fast return   Backend + database
                    |
                    v
                Cache store
                    |
                    v
                 Response
~~~

**Cache hits** reduce latency, load, and backend cost. However, cached entries can be **stale** during the TTL window, and poorly keyed caches can leak data across customers.

## 13. Cache-lookup and cache-store

APIM supports **`cache-lookup`** and **`cache-store`** policies to retrieve and store responses using gateway caching capabilities.

Sample policy for a public catalog GET:

~~~xml
<policies>
  <inbound>
    <base />
    <cache-lookup
      vary-by-developer="false"
      vary-by-developer-groups="false"
      downstream-caching-type="none">
      <vary-by-query-parameter>category</vary-by-query-parameter>
      <vary-by-header>Accept</vary-by-header>
    </cache-lookup>
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
    <cache-store duration="60" />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
~~~

**Meaning:**

- **`cache-lookup`** checks for a cached response matching the request.
- **`vary-by-query-parameter`** separates categories, such as `books` and `shoes`.
- **`vary-by-header` `Accept`** separates responses when output format varies.
- **`cache-store duration="60"`** illustrates a 60-second TTL for eligible responses.
- **`downstream-caching-type="none"`** tells downstream clients/proxies not to cache based on this policy.

### Conditions on the example

This example assumes the API **returns only public, non-personalized data with no secrets**, and applies only to cacheable GET endpoints. **Never apply it as-is to `/me`, `/accounts/{id}`, `/orders/{id}`**, or responses containing tenant-specific data without safe cache partitioning.

Cache policies depend on response types, HTTP methods, headers, and tier/cache-backend support. Never interpret `TTL=60` as a guarantee that every response stays cached and retrievable for exactly 60 seconds; entries can be evicted, not yet stored, or ineligible.

### Internal cache vs. external cache

APIM provides built-in internal caching or external caching options depending on tier and setup (e.g. supported Redis/managed caches). Evaluate:

- Which cache modes does your current tier/gateway support?
- What are the internal cache's capacity limits and sharing scope across gateways/regions?
- When scaling gateways or deploying multi-region, are cache instances consistent?
- Is a shared external cache needed per supported environment?
- How is cached data protected via networking, auth, and retention?

**Caching is a performance layer, not the system of record.** When cache misses or fails, the system must fall back cleanly to the backend without returning wrong results or cascading failures.

## 14. Designing cache keys and vary-by

A good cache key reflects **every factor that actually changes the response**.

Example:

~~~text
GET /v1/catalog?category=books&lang=vi
GET /v1/catalog?category=books&lang=en

If the response depends on lang:
  The cache key must distinguish lang=vi from lang=en.
~~~

If the policy varies only by `category` while the response changes with `lang`, a user can receive data in the wrong language.

### Dimensions to consider

| Dimension | When to vary |
|---|---|
| **URL/path** | Different endpoint or resource |
| **Query parameters** | `category`, `lang`, `currency`, `page`, `sort` that actually alter output |
| **Accept / content negotiation** | JSON/XML or differing response representations |
| **API version** | Different response contract versions |
| **Tenant / user identity** | Personalized or permission-scoped responses |
| **Authorization state** | Users have differing data visibility |
| **Feature flag/locale** | Content varies by group configuration |

### Cross-tenant data leak risk

If Tenant A's response is cached under a shared key and Tenant B receives that cached entry, the gateway leaks data even though the backend authorized the first response properly.

**Prefer not caching private responses at the gateway** without a compelling reason and verified key isolation. If authorized data is cached, ensure identity checks run before `cache-lookup`, keys partition strictly by tenant/user, and headers prevent sensitive responses from leaking through browsers/proxies.

### Authorization header is not a safe default key

Putting raw access tokens into cache keys bloats keys, risks data exposure, and lowers hit rates; tokens also rotate even for the same user. Key off verified identity attributes safely—or avoid caching sensitive responses altogether.

## 15. Cache invalidation and staleness windows

TTL caps how long a cached entry is considered valid by policy, but **does not detect when source data changes**.

~~~text
10:00  Backend returns product price = 100,000 VND
10:00  APIM caches response for 60 seconds
10:20  Price updates in backend = 90,000 VND
10:30  Client calls again
       -> may still receive the stale cached price
11:00  Entry expires in this illustrative timeline
       -> cache miss, backend called for fresh data
~~~

**Timestamps are hypothetical relative seconds illustrating TTL**, not a claim that caches always expire at the exact wall-clock minute under all conditions.

### Ways to keep data appropriately fresh

1. **Short TTL** for catalogs changing relatively often.
2. **No caching** for responses requiring immediate freshness, such as live payment balances.
3. **Cache versioning/key rotation** when the data source carries explicit versions.
4. **Cache invalidation** per capabilities/tooling and architecture in use.
5. **ETag/conditional requests** if supported by backend/contract, testing interaction with gateway caching.
6. Separate **public reference data** from personalized data.

APIM offers value-caching policies beyond response caching—such as **`cache-lookup-value`**, **`cache-store-value`**, and **`cache-remove-value`**—for storing/reading keyed values; never assume `remove-value` automatically purges response cache entries stored by `cache-lookup`/`cache-store`.

### Cache stampede

When a popular entry expires, many concurrent requests can miss simultaneously and slam the backend. This is a **cache stampede**. Mitigations may include:

- Controlled TTLs with jitter per architecture.
- Single-flight/coalescing or request collapsing at supported layers.
- Cache warm-up during deployments/traffic ramps.
- Rate limits and sufficient capacity at the backend.
- Excluding high-cardinality queries from caching.

APIM `cache-store` may write asynchronously; **the very next request after a cache miss is not guaranteed to hit**. Never build SLAs assuming the second call is always served from cache.

## 16. Response caching vs. value caching

Two common patterns:

| Pattern | Used for | Typical policies |
|---|---|---|
| **Response cache** | Returning an entire HTTP response for equivalent requests | `cache-lookup` / `cache-store` |
| **Value/fragment cache** | Storing an intermediate value for policy or backend reuse | `cache-lookup-value` / `cache-store-value` |

For example, a policy fetches a token/metadata or config list from an auxiliary service and wants to cache an intermediate value briefly. **Value caching** may fit better than response caching, provided keys, sensitivity, TTL, and invalidation are understood.

Never put refresh tokens, passwords, or long-lived credentials in a value cache merely for convenience. Sensitive values must follow strict secret-management and access-control policies.

## 17. Policy order: rate limits and caching interact

Suppose a catalog GET request can be cached for 60 seconds. Two orderings serve different goals.

### Approach A: rate limit before cache

~~~text
Validate -> Rate limit -> Cache lookup -> (hit/miss) -> Response
~~~

Every request counts against the limit, including cache hits. This fits when protecting the gateway or enforcing fair-use contracts so clients cannot bypass limits simply via cache hits.

### Approach B: cache before rate limit

~~~text
Validate -> Cache lookup -> on miss only, enter Rate limit
~~~

Because cache hits short-circuit early, cached requests may skip rate limiting placed afterward. That can break a contract stating “each user gets at most N requests/minute.”

### Which to choose?

If the API contract bills or limits by total client calls, **rate limits and quotas normally belong before `cache-lookup`** so clients cannot exceed allowances via cached calls. If quotas count **actual backend invocations**, design counters specifically for that goal, verify execution only on cache misses, and test the behavior. Never slap on the label “quota” and assume it counts whichever call type the business bills.

## 18. What is request transformation?

**Request transformation** modifies requests before the backend processes them, for example:

- Rewriting public path **`/v1/products`** to backend **`/internal/catalog/items`**.
- Adding or normalizing an **`X-Correlation-Id`** header.
- Adding an **`api-version`** query parameter expected by the backend.
- Renaming a JSON field from **`customer_id`** to **`customerId`**.
- Stripping or normalizing unnecessary data per approved policies.
- Selecting different backends based on version or routing conditions.

~~~text
Client:
POST /api/v1/orders
Body: {"customer_id":"C42","amount":100}
             |
             v
       API Management
       - rewrite path
       - set backend query
       - map customer_id -> customerId
       - add correlation ID
             |
             v
Backend:
POST /internal/orders?api-version=2024-06-01
Body: {"customerId":"C42","amount":100}
~~~

APIM helps **shield clients from backend changes** during transitions. However, when mapping rules grow complex, prefer a versioned API contract or a dedicated integration service over stuffing business logic into policy XML.

## 19. rewrite-uri: changing the backend path

The **`rewrite-uri`** policy transforms the URL path/query sent to the backend using a template.

~~~xml
<rewrite-uri
  template="/internal/catalog/items"
  copy-unmatched-params="true" />
~~~

If the public API receives:

~~~text
GET /v1/catalog?category=books&page=2
~~~

The backend can receive:

~~~text
GET /internal/catalog/items?category=books&page=2
~~~

Exact behavior depends on the API URL suffix, operation template, backend base URL, and query rewrites. The example assumes the backend base URL is configured properly.

### Watch out for copy-unmatched-params

- If `true`, query parameters not declared/matched in the operation template are forwarded per policy behavior.
- If `false`, unmatched query parameters may be dropped, altering the contract.
- The backend might fail to block client-injected sensitive parameters like **`isAdmin=true`**.

Do not enable copying all query parameters without an allowlist or control. **Rewriting is not input validation**; sensitive backend parameters must still be validated and protected.

## 20. set-header: standardizing and passing correlation

Example adding a tracing header:

~~~xml
<set-header name="X-Correlation-Id" exists-action="override">
  <value>@(context.RequestId.ToString())</value>
</set-header>
~~~

**`context.RequestId`** is the APIM request context identifier used for call correlation. This example generates the identifier at the gateway without trusting an arbitrary client-provided header.

### Other use cases

- Adding a header indicating the contract version passed through the gateway.
- Attaching verified tenant information for the backend, within a verified trust boundary.
- Stripping internal headers that must not leak to the Internet.
- Renaming headers when a backend updates its API contract.

**Warning:** never take client-supplied headers like **`X-Admin`**, **`X-Tenant-Id`**, or **`X-User-Role`** and pass them to the backend as trusted identity. If the backend trusts such headers, ensure the gateway deletes/overwrites untrusted values and the backend cannot be reached directly to spoof them.

### Headers are not a secret store

Never hardcode permanent access credentials into policy XML. When secrets are needed, use protected **named values**, Key Vault integration, or managed identity where supported, and keep them out of logs/traces.

## 21. set-query-parameter: controlled query edits

Suppose the backend requires **`api-version=2024-06-01`**, while legacy clients do not send it:

~~~xml
<set-query-parameter name="api-version" exists-action="override">
  <value>2024-06-01</value>
</set-query-parameter>
~~~

**`exists-action="override"`** ensures the gateway sends the policy-enforced value rather than trusting an `api-version` passed by the caller.

### Scenarios to test

1. Client sends no `api-version`.
2. Client sends a valid `api-version`.
3. Client intentionally sends an invalid `api-version`.
4. Query contains multiple parameters like `category`, `page`, `sort`.
5. Query contains repeated parameter names or URL-encoded characters.

If the backend requires parameters signed with HMAC or signatures computed over the URL, modifying query parameters after signing invalidates the signature. Design auth/signing at the right point and verify it.

## 22. set-body: transforming JSON requests

When a backend upgrades from **`customer_id`** to **`customerId`**, APIM can transform the body using policy expressions in appropriate scenarios.

### Illustrative example

~~~xml
<set-body>@{
    var payload = context.Request.Body.As<JObject>(preserveContent: true);
    if (payload["customer_id"] != null)
    {
        payload["customerId"] = payload["customer_id"];
        payload.Remove("customer_id");
    }
    return payload.ToString();
}</set-body>
~~~

Example input:

~~~json
{
  "customer_id": "C42",
  "amount": 100
}
~~~

Becomes:

~~~json
{
  "customerId": "C42",
  "amount": 100
}
~~~

### Limits and warnings

- This is a **structural transformation**, not proof that the customer ID is valid or the amount is authorized.
- **`JObject`** belongs to the .NET types supported in APIM policy expressions; this snippet assumes the body is a valid JSON object.
- Empty bodies, JSON arrays, non-JSON data, or malformed payloads must be handled with proper validation and error responses.
- **`preserveContent: true`** helps when reading the body stream while still needing its contents later; weigh memory usage and payload sizes.
- Body transformation consumes CPU/memory and adds latency, especially for large payloads.
- Never alter data **signed by the client** and expect the signature to remain valid.
- If the backend uses request compression/streaming, verify whether policies support the payload format.

For files of hundreds of MB, it is usually better to have clients upload directly to Blob Storage via controlled authorization and then emit an event or job, rather than making APIM parse and transform every byte.

## 23. Transforming responses while preserving API contracts

Besides requests, APIM can modify responses in **`outbound`**.

Example adding a contract version header:

~~~xml
<set-header name="X-Api-Contract-Version" exists-action="override">
  <value>v1</value>
</set-header>
~~~

You can apply policies for schema/contract conformance, JSON/XML conversion, or stripping headers as needed. However, explicitly verify:

- Does `Content-Type` match the transformed response body?
- Did the status code change, and do clients rely on it?
- Are `ETag`/`Last-Modified` or `Content-Length` still valid?
- Is the response cached by the gateway, proxies, or browsers?
- Was any sensitive data added to logs or responses?

A transform that “just adds a JSON field” can break response signatures or invalidate `ETag`/cache keys. Test contracts from the client's perspective rather than checking only that the backend returned HTTP 200.

## 24. Combining policies in a public API

Suppose a public catalog API **`GET /v1/catalog`** maps to backend **`/internal/catalog/items`** and requires `api-version`. Clients present subscription keys for usage limits.

### Illustrative combined policy

~~~xml
<policies>
  <inbound>
    <base />

    <!-- Key by subscription; IP fallback is for lab use only. -->
    <rate-limit-by-key
      calls="30"
      renewal-period="60"
      counter-key="@(context.Subscription?.Id ?? context.Request.IpAddress)" />

    <quota-by-key
      calls="10000"
      renewal-period="86400"
      counter-key="@(context.Subscription?.Id ?? context.Request.IpAddress)" />

    <set-header name="X-Correlation-Id" exists-action="override">
      <value>@(context.RequestId.ToString())</value>
    </set-header>

    <rewrite-uri
      template="/internal/catalog/items"
      copy-unmatched-params="true" />

    <set-query-parameter name="api-version" exists-action="override">
      <value>2024-06-01</value>
    </set-query-parameter>

    <cache-lookup
      vary-by-developer="false"
      vary-by-developer-groups="false"
      downstream-caching-type="none">
      <vary-by-query-parameter>category</vary-by-query-parameter>
      <vary-by-query-parameter>page</vary-by-query-parameter>
      <vary-by-header>Accept</vary-by-header>
    </cache-lookup>
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
    <cache-store duration="60" />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
~~~

**Mandatory conditions for this example to be valid:**

1. The API returns **identical public data for all subscriptions**, with no user-specific data.
2. The operation uses GET; never bundle mutating POST/PUT operations under it.
3. `category`, `page`, `Accept`, and `api-version` queries are handled properly; if responses also vary by `lang`/`currency`/feature flags, add those vary keys.
4. The backend URL is configured accurately.
5. Caching is supported and enabled on the target tier/gateway.
6. Subscription/identity is verified before being used to partition counters.
7. Cache-hit behavior, policy order, and policy inheritance are verified.

### Why must cache keys reflect backend query parameters?

If public requests **`category=books`** and **`category=shoes`** rewrite to the same path while caching ignores `category`, responses get mixed up. `vary-by` on `category` prevents that bug.

### When should you NOT use this combined policy?

Never apply the same policy to **`POST /payments`** or **`GET /users/me`**. Payments must not use generic response caching; user data must never share cache keys. Design policies per **API operation and sensitivity level** instead of pasting one XML block across every API.

## 25. Authentication and authorization must sit in the right place

In APIM, a **subscription key** supports API access/usage management under the product model, **but it does not replace** end-user authentication or per-resource access control.

An Orders API may require:

1. Validating JWTs from Microsoft Entra ID or an appropriate identity provider.
2. Checking issuer, audience, signature, expiration, and required claims.
3. Resolving the verified tenant/user.
4. Rate-limiting by verified tenant or subscription.
5. Caching only where an airtight data-partitioning model prevents leaks.
6. Backend verifying read/write permission for the **exact `orderId`**.

~~~text
Request -> JWT validation -> tenant/user context
                         |
                         v
                  Rate limit / Quota
                         |
                         v
                  Cache/Transformation
                         |
                         v
                  Backend authorization
~~~

### Never extract sensitive identifiers from unauthenticated requests

A client can send **`X-User-Id=admin`** or **`tenantId=other`**. If the gateway uses those untrusted values as a `counter-key`, cache key, or trusted backend header, attackers can bypass limits and access unauthorized data.

Use verified claims, validated subscriptions, or mappings from trusted sources. Audit all paths to the backend outside APIM; if the backend allows direct traffic bypassing the gateway, APIM policies can be circumvented.

## 26. Policy XML and policy expressions: safety limits

APIM policy XML can embed **C# policy expressions** in supported attributes/values, for example:

~~~xml
<set-header name="X-Gateway-Request-Id" exists-action="override">
  <value>@(context.RequestId.ToString())</value>
</set-header>
~~~

Expressions must stick to the subset of APIs/.NET types supported by APIM. Never assume you can import arbitrary C# libraries or make network calls as in a general .NET application.

### Risks when writing expressions

- **Null references:** `Subscription` or `User` can be null on certain requests.
- **Unexpected body format:** parsing `JObject` on XML or empty bodies throws errors.
- **CPU/memory overhead:** processing huge bodies at the gateway.
- **Exceptions:** failing requests before reaching the backend.
- **Secrets in traces:** logging variables holding tokens leaks credentials.
- **Inconsistent scope:** global policies applied to APIs with differing contracts.

Test expressions against valid requests, missing fields, wrong types, auth failures, and large payloads.

### Avoid overly complex business logic in the gateway

APIM excels at **cross-cutting concerns**: auth, routing, throttling, caching, and header/path transformations. Stateful business logic, transactions, long retries, or multi-system orchestrations usually fit better in backends, Azure Functions, Logic Apps, or dedicated services.

## 27. Safe deployment workflow on the Azure Portal

The lab below uses only an **authorized test APIM instance and test API**, never modifying production. APIM and backends can incur charges even during lab usage.

### Step 1: prepare the test API

1. Select the lab subscription/resource group.
2. Verify the APIM instance, tier, and gateway in use.
3. Create or select API **`catalog-lab`** with operation **`GET /v1/catalog`**.
4. The test backend returns a simple response with `category` and processing duration.
5. If using subscriptions, create an authorized lab account/subscription.
6. Enable appropriate diagnostics/logs while excluding secrets.

### Step 2: measure baseline

Send several GET requests with different categories:

- `category=books`.
- `category=shoes`.
- `category=books&page=2`.

Record status, latency, correlation ID, and actual backend invocation counts. **Keep caching off** to establish a baseline.

### Step 3: add rate limit first

In the policy editor at the appropriate API/operation scope, add a low **`rate-limit-by-key`** (e.g., 5 calls/60 seconds) for the lab client. Confirm requests within the limit succeed and excess requests receive **429**.

Use low thresholds only at lab scope—never apply them globally across APIs in a production subscription.

### Step 4: add quota

Add **`quota-by-key`** at lab scope with a testable threshold. Remember quota counters span renewal windows; never exhaust a production quota just to observe the error.

Record the actual status code, headers, and when calls resume, rather than assuming quotas reset immediately when you edit policy XML.

### Step 5: add caching

For the public-data GET operation only, add **`cache-lookup`** and **`cache-store`**. Send repeated identical GETs and measure backend call counts and latency. Verify:

- Different categories never return each other's data.
- Responses contain no private data.
- Cache hits do not skip mandatory controls.
- Once TTL expires, fresh backend data is fetched again.

### Step 6: add transformations

Test `rewrite-uri` to a different backend path; add `api-version` via `set-query-parameter`; add a correlation header via `set-header`. For POST JSON, use a **separate test API** to try `set-body`; never share GET caching with POST.

### Step 7: evaluate and clean up

Save before/after policies, compare effective policies, test cases, and metrics. Clean up scoped lab resources afterward without deleting shared APIM instances or resource groups hosting other workloads.

## 28. Testing the API with curl

The HTTP commands below **call live APIs** and can generate request volume/charges. Run them only against authorized lab APIs.

~~~bash
# Assign APIM_SUBSCRIPTION_KEY via a secure secret mechanism
# in the lab environment; never save keys in scripts/repositories.

curl --request GET --include \
  --header "Ocp-Apim-Subscription-Key: $APIM_SUBSCRIPTION_KEY" \
  "https://<APIM_GATEWAY_HOST>/catalog/v1/catalog?category=books"
~~~

Verify:

- HTTP status.
- Response headers such as `Retry-After` if emitted by the gateway.
- `X-Correlation-Id` / `X-Api-Contract-Version` per policy.
- JSON body matching the requested category.
- Latency across repeated calls.

### Testing rate limits

~~~text
Lab API scenario: 5 calls / 60 seconds

Requests 1..5: accepted if no other errors
Request 6: inspect HTTP 429 and retry info
Wait until policy window allows:
  call again, verify normal operation resumes
~~~

Do not run stress loops of thousands of requests against APIM casually. Load testing requires approved tools, budget, rate caps, stop conditions, and active monitoring.

### Testing caching

~~~text
GET /catalog?category=books (1st call):
  expect cache miss or unpopulated cache

Identical GET afterward:
  may cache hit if entry was stored and within TTL

GET /catalog?category=shoes:
  must never receive books response
~~~

Never claim a cache hit purely from fast response times; cross-check backend request logs or configured telemetry.

## 29. Azure CLI: inspecting APIM configuration before editing

The following commands are **read-only** on Azure resources. Service and resource group names are placeholders.

### Check subscription

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"
az account show --query "{id:id,name:name,tenantId:tenantId}" --output json
~~~

### Inspect APIM instance

~~~bash
az apim show \
  --resource-group "rg-api-lab" \
  --name "apim-catalog-lab" \
  --query "{name:name,location:location,sku:sku.name,gatewayUrl:gatewayUrl,provisioningState:provisioningState}" \
  --output json
~~~

### List APIs

~~~bash
az apim api list \
  --resource-group "rg-api-lab" \
  --service-name "apim-catalog-lab" \
  --output table
~~~

### List products

~~~bash
az apim product list \
  --resource-group "rg-api-lab" \
  --service-name "apim-catalog-lab" \
  --output table
~~~

To inspect policy XML at each scope, use the Azure Portal or APIM REST/CLI operations targeting the **exact policy resource** for your CLI version. Never invent guessed flags for a show-policy command and assume it works across all Azure CLI versions.

**Read-only configuration commands do not test 429s, cache hits, or body transforms.** Send test requests through the gateway in an authorized environment and inspect backend/gateway logs.

## 30. Monitoring APIM, rate limits, quotas, and caching

An API gateway must be observed across both **requests** and **business outcomes**.

| Category | Metrics / questions |
|---|---|
| **Requests** | Total requests by API, operation, client, and response code |
| **Throttling** | 429s by key/tier/operation; are there abnormal bursts? |
| **Quota** | Quota-driven 403s, quota period, impacted clients |
| **Latency** | Total gateway duration, backend latency p50/p95/p99 |
| **Backend failures** | 429/503/504, timeouts, circuit breakers, or connection failures |
| **Cache** | Hit/miss, TTL, backend call reduction, stale responses |
| **Transform** | Body parse failures, backend receiving wrong schema/route |
| **Identity** | 401/403 auth failures, subscription/tenant scope |
| **Cost** | Gateway capacity/units, external cache, logs, backend savings |
| **Security** | Token/claim validation failures, client abuse, mis-cached data |

Not every row corresponds to a built-in Azure Monitor metric with that exact name. For example, cache hit rate, per-field transform errors, or quota-specific 403s may require **custom logs, diagnostics, or backend telemetry**. Never enable verbose body logging in production when payloads may contain sensitive data.

### Correlation ID

On each request, attach an identifier sufficient for linking telemetry:

~~~json
{
  "requestId": "example-req-42",
  "api": "catalog-lab",
  "operation": "GET /v1/catalog",
  "outcome": "200",
  "gatewayDurationMs": 28,
  "backendDurationMs": 0,
  "throttled": false
}
~~~

**`backendDurationMs=0`** in the sample log merely illustrates a request that did not call the backend; it is not a mandatory APIM metric field. When measuring cache hits, cross-check against actual logging mechanics to avoid misreporting.

### Alerts to consider

- Sudden surge in HTTP 429 rates.
- Multiple clients simultaneously receiving quota 403s after a policy update.
- Backend latency or 5xx rising even while APIM response times look normal.
- Sharp drop in cache hit rate after deployment.
- Unexpected cache hits on endpoints containing user-specific data.
- JSON parsing/transformation errors and unusual 400/500 spikes.
- Changes to global/product/API policies outside the approval workflow.
- Gateway/Redis/log costs exceeding budget.

## 31. Rate limits do not defend against every attack

`rate-limit-by-key` helps curb some forms of overuse, yet:

- Attackers can rotate across multiple accounts/IPs.
- Malicious requests can stay below thresholds.
- Backends can still suffer from huge payloads or CPU-heavy queries.
- Bots can distribute traffic across many sources.
- Caches can be abused to generate numerous unique keys, causing cache pollution.

Combine:

1. Microsoft Entra ID/JWT and API subscriptions where appropriate.
2. Azure Front Door/WAF or edge controls per architecture.
3. Schema validation, size caps, content-type enforcement, and request controls.
4. Backend authorization, idempotency, and resource limits.
5. Network isolation, private endpoints, TLS, and secrets management.
6. Monitoring, alerting, and incident response.

**WAF and APIM policies operate at different layers** and should not replace one another with a single rate-limit rule.

## 32. Multi-region, multi-gateway, and self-hosted gateway operations

When APIM runs across multiple regions or uses self-hosted gateways, counters and caches may differ in scope and synchronization compared to a single gateway.

### Rate limits and quotas

Some `rate-limit-by-key` counters are **distributed per gateway/region or eventually consistent** depending on features. Never promise customers a **globally exact 100-call cutoff down to the microsecond** without proving consistency under your deployment topology.

### Caching

Internal caches may not act as a globally shared store across all gateways. When designing an external cache, account for:

- Networking, Private Endpoints, and DNS.
- Authentication and encryption.
- Availability, cross-region latency, and cache failover.
- External cache costs and sensitive data exposure.
- Cache miss/fallback behavior when the cache is unavailable.

### Self-hosted gateway

Self-hosted gateways are a distinct deployment model whose policy/caching capabilities and limits can differ from managed gateways. Confirm **your exact policies and caching mode** are supported before migrating from a managed test gateway to self-hosted.

## 33. Impact on SLA and cost

### Cost benefits

- Cache hits reduce backend requests, database reads, and response times.
- Rate limits curb abusive clients and reduce burst pressure.
- Quotas enforce fair use and prevent over-consumption beyond contracts.
- Transformations reduce the need to maintain many trivial backend adapters.

### Costs to account for

- APIM tier/gateway capacity and instances/units per billing model.
- External cache if provisioned.
- Azure Monitor, Application Insights/Log Analytics, and log retention.
- Network egress and Private Endpoints/Firewalls/NAT where present.
- Backend compute/database costs, which can drop when caching works well.
- Engineering effort for policies, debugging, CI/CD, and contract tests.

**Do not assume caching is always cheaper.** An API whose responses vary across millions of keys can suffer low hit rates; external caches and serialization add costs while the backend still processes nearly all requests.

### Rough calculation of cache impact

Hypothetical example:

~~~text
100,000 requests/day to catalog API
Measured cache hit rate = 70%

Approximate backend requests:
  100,000 x (1 - 0.70) = 30,000/day

Backend calls avoided:
  70,000/day
~~~

This simplified math excludes retries, cache warm-up, eviction, fan-out, uncacheable requests, and data churn. Measure actual traffic before using it for budgeting or capacity commitments.

## 34. Common errors and how to diagnose them

| Symptom | Possible cause | Investigation direction |
|---|---|---|
| Client gets 429 despite few calls | Shared `counter-key`, shared NAT IP, or parent policy also throttling | Inspect effective policy, key, and actual request rate |
| Client exceeds limit without immediate block | Distributed/delayed counter sync, wrong scope, or policy not running | Check effective policy, tier, logs, and controlled tests |
| Quota returns 403 long after expected reset | Renewal period not elapsed or shared key | Check `renewal-period`, scope, `counter-key` |
| Customer changes `X-Tenant-Id` to evade rate limit | Key read from untrusted header | Switch to verified identity/tenant |
| Low cache hit rate | Too many vary dimensions, short TTL, cache backend unavailable | Inspect cache mode, query/headers, evictions, backend calls |
| Cache returns wrong language | Missing `lang` in key | Add `vary-by-query-parameter` `lang` |
| Cache serves Tenant A's data to B | Cache key lacks identity or endpoint shouldn't be cached | Disable caching on endpoint, investigate data leak, fix scope |
| Price updates but clients see old price | TTL not expired or downstream cache active | Inspect invalidation, TTL, browser/CDN/backend |
| Rewrite causes backend 404 | Wrong backend base URL, path, or `copy-unmatched-params` | Inspect exact request received by backend |
| POST returns 500 after `set-body` | Payload not a `JObject`, null/oversized body, or expression error | Test valid/malformed JSON, add validation |
| Backend never sees correlation ID | Header overwritten later or policy at wrong scope | Check effective order and backend logs |
| Cache hit omits required response header | Header was added in a step skipped by cache short-circuit | Place mandatory policies before cache or shape responses safely |
| Production 5xx rises after policy change | Backend throttling, retry amplification, timeout/circuit breaker | Check gateway and backend logs by correlation ID |
| New API lacks global rule | Broken `base` inheritance or unreferenced fragment | Inspect effective policy |
| Internal cache misses in another region | Non-shared cache / separate gateway | Evaluate external cache and multi-region design |

### Six-step diagnostic workflow

1. **Request:** confirm method, URL, query, headers, subscription/identity, and correlation ID.
2. **Policy:** inspect effective policy, scope, and section ordering.
3. **Counters/cache:** verify `counter-key`, renewal, `vary-by`, TTL, and backend cache mode.
4. **Backend:** verify actual received URL/path/query/body, latency, and errors.
5. **Infrastructure:** check tier/gateway, DNS, Private Endpoint, outbound network, and scaling.
6. **Business outcome:** verify responses match the right tenant/operation and staleness stays acceptable.

Never fix a 429 by disabling rate limits globally before checking which key/scope is active; and never skip cache validation merely because the second request feels faster than the first.

## 35. Case study exercise: partner commerce API

An enterprise runs an API serving three client groups:

- **Mobile app:** high-volume reads of the public catalog.
- **Partner Free:** at most **30 calls/minute** and **10,000 calls/day**.
- **Partner Premium:** at most **120 calls/minute** and **100,000 calls/day**.

A new backend moves `GET` **`/v1/catalog`** to **`/internal/catalog/items`** and requires **`api-version`**. `POST` **`/v1/orders`** accepts **`customer_id`**, while the backend expects **`customerId`**. The catalog changes roughly every 5 minutes; orders are private data.

### Tasks

1. Choose which policies enforce rate limits and quotas across the two partner tiers.
2. Identify a trustworthy `counter-key` and explain why client-sent `X-Partner-Id` headers must not be used.
3. State where to place policies—product, API, or operation—and how inheritance must be checked.
4. Design caching for `GET catalog`, choosing a pilot TTL and query parameters to vary on.
5. Explain why the same cache must not apply to `GET /orders/{id}` or `POST /orders`.
6. Write sample `rewrite-uri` and `set-query-parameter` policies for catalog.
7. Write a sample `set-body` policy mapping `customer_id` to `customerId` for POST, including validation.
8. Design 429/403 handling and backoff strategies for mobile/partner clients.
9. Describe how to verify cache hits reduce backend load without serving wrong data.
10. Design logs, alerts, and metrics for throttling/transform incidents.
11. Estimate backend impact if the catalog cache hit rate is 70%.
12. Propose a canary/testing rollout and rollback plan if the API contract breaks.

### Solution hints

**`rate-limit-by-key`** and **`quota-by-key`** keyed by verified subscription/tenant are the starting point. You can separate Free/Premium products and attach corresponding policies, while verifying how subscriptions map to products and checking effective policies at the operation level.

**`GET catalog`** can use caching keyed by category, page, language, and version if responses depend on them. **`POST orders`** must never share response caching and needs backend validation and idempotency; `set-body` only bridges the legacy contract.

Test calls within limits, calls exceeding rate limits, exhausted quotas, cache hits/misses, differing query results, and malformed JSON. Use logs with correlation IDs to distinguish gateway errors from backend errors.

## 36. Pre-production deployment checklist

| Area | Verification item |
|---|---|
| Policy scope | Global/product/API/operation scopes intentionally assigned |
| Inheritance | `<base />`, fragments, and effective policies reviewed |
| Authentication | JWT/subscription/tenant identity validated before sensitive keys |
| Rate limit | Thresholds match bursts/SLOs; 429 handling clear |
| Quota | Window, key, 403/remaining budget, and usage contract aligned |
| Counter semantics | Scope, distribution, multi-region, and consistency limits understood |
| Cache scope | Only eligible endpoints/responses cached; zero data leaks |
| Cache key | `vary-by` covers query, version, locale, tenant where truly needed |
| TTL | Acceptable staleness; invalidation strategy ready where needed |
| Cache backend | Tier, internal/external support, networking, and failure modes verified |
| Transformation | Path/query/header/body accurate without breaking auth/signatures |
| Validation | Malformed JSON, empty bodies, large payloads, and schema versions tested |
| Backend | No unintended access path bypasses gateway policies |
| Security | Entra ID, RBAC, Key Vault, TLS, firewalls, WAF applied where appropriate |
| Monitoring | 429/403, 5xx, cache hits, backend latency, transform errors tracked |
| Cost | Budgeted APIM/cache/logs/backend with before/after baselines |
| Rollout | API tests, canary/versioning, and rollback plan prepared |

## 37. Self-check questions

1. How do rate limits and quotas differ in purpose and time window?
2. Why might a 10,000 calls/day quota fail to protect a backend from bursts?
3. What sections make up an APIM policy pipeline?
4. How does the placement of `base` affect policy inheritance?
5. Distinguish `rate-limit` from `rate-limit-by-key`.
6. Why should `counter-key` never come directly from a client-sent `X-Tenant-Id` header?
7. Why can IP-based keys cause false throttling when multiple clients share NAT?
8. When rate-limited, which status code do clients usually receive and how should they react?
9. When exceeding a quota in APIM, how does the response typically differ from rate limiting?
10. Does a per-subscription quota automatically equal a per-tenant quota?
11. Why doesn't a rate limit automatically cap concurrent backend connections?
12. What do `cache-lookup` and `cache-store` do?
13. Why does `vary-by-query-parameter` matter for `category` and `lang`?
14. Why can't public response caching be applied directly to `/me`?
15. Does a cache hit always run every downstream outbound policy?
16. Why should rate limits usually run before `cache-lookup`?
17. Does `TTL=60` guarantee data cannot become stale within 60 seconds?
18. Distinguish response caching from value caching.
19. When backend prices change, what cache invalidation options exist?
20. Why doesn't `rewrite-uri` replace authorization/validation?
21. How can `set-header` introduce identity-spoofing risks?
22. What problem does `set-query-parameter` `exists-action="override"` solve?
23. When `set-body` parses a `JObject`, which edge-case inputs must be checked?
24. Why shouldn't the gateway JSON-transform large file uploads?
25. What must be verified when migrating an API from `customer_id` to `customerId`?
26. How do you prove cache hits actually reduce backend requests?
27. With multi-region APIM, what must be checked regarding counters and caches?
28. Does an APIM subscription key replace a user JWT?
29. How do gateway 429s differ from backend 429s during diagnostics?
30. What are the main cost components of an APIM solution with an external cache?

## References

- Microsoft Learn — *Azure API Management overview*: https://learn.microsoft.com/azure/api-management/api-management-key-concepts
- Microsoft Learn — *API Management policies overview*: https://learn.microsoft.com/azure/api-management/api-management-howto-policies
- Microsoft Learn — *Policy reference*: https://learn.microsoft.com/azure/api-management/api-management-policies
- Microsoft Learn — *Policy scopes and inheritance*: https://learn.microsoft.com/azure/api-management/api-management-howto-policies#scopes
- Microsoft Learn — *Rate limit by key*: https://learn.microsoft.com/azure/api-management/rate-limit-by-key-policy
- Microsoft Learn — *Rate limit*: https://learn.microsoft.com/azure/api-management/rate-limit-policy
- Microsoft Learn — *Quota by key*: https://learn.microsoft.com/azure/api-management/quota-by-key-policy
- Microsoft Learn — *Quota*: https://learn.microsoft.com/azure/api-management/quota-policy
- Microsoft Learn — *Cache lookup*: https://learn.microsoft.com/azure/api-management/cache-lookup-policy
- Microsoft Learn — *Cache store*: https://learn.microsoft.com/azure/api-management/cache-store-policy
- Microsoft Learn — *Cache lookup value*: https://learn.microsoft.com/azure/api-management/cache-lookup-value-policy
- Microsoft Learn — *Rewrite URL*: https://learn.microsoft.com/azure/api-management/rewrite-uri-policy
- Microsoft Learn — *Set header*: https://learn.microsoft.com/azure/api-management/set-header-policy
- Microsoft Learn — *Set query parameter*: https://learn.microsoft.com/azure/api-management/set-query-parameter-policy
- Microsoft Learn — *Set body*: https://learn.microsoft.com/azure/api-management/set-body-policy
- Microsoft Learn — *API Management monitoring*: https://learn.microsoft.com/azure/api-management/api-management-howto-use-azure-monitor
- Microsoft Learn — *API Management security baseline*: https://learn.microsoft.com/security/benchmark/azure/baselines/api-management-security-baseline
