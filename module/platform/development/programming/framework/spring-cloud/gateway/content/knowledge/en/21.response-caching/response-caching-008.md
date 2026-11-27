# Measuring Cache Hit Ratio and Verifying Response Correctness in Spring Cloud Gateway

Enabling response caching at an API Gateway can lower latency and cut microservice calls, yet **a fast cache reply does not guarantee a correct cache reply**. A high hit ratio can still mask severe bugs: returning another tenant's data, reusing an expired response, ignoring language variants, or serving stale content after an update.

In **SPRING_CLOUD_GATEWAY**, response caching (such as `LocalResponseCache` in supported Gateway Server WebFlux releases) lives inside the same pipeline as route predicates, `GatewayFilter`s, and downstream routing. This lesson in the **Response Caching** chapter focuses on two inseparable questions:

1. **Measuring effectiveness:** How many requests are genuinely served from cache? Which denominator defines the hit/miss ratio? How many backend calls and milliseconds of latency were actually saved?
2. **Verifying correctness:** Does every hit return the right data for the URL, query, user, tenant, variant headers, and current data state?

This lesson also connects authentication, rate limiting, circuit breakers, retries, TLS, and observability so your microservices entry point is both fast and safe.

> **Scope:** Examples primarily target **Spring Cloud Gateway Server WebFlux** with Gateway 4.x-style configuration. `LocalResponseCache` is a **local in-process Gateway cache**, not a distributed cache by default. Property names, cacheable statuses, `Cache-Control` handling, and metrics vary across release trains. Always verify documentation for your **exact version** and test runtime behavior. Never copy examples verbatim to Gateway Server MVC without checking differences.

## 1. Where Does Caching Sit in the Gateway Pipeline?

Gateway can cache **responses** after receiving results from the backend to serve future requests rather than forwarding every call. Conceptual pipeline:

~~~mermaid
flowchart TD
    C["Client: GET /api/catalog/items/42"] --> S["Spring Security / WebFlux"]
    S --> P{"Route predicates match?"}
    P -->|No| N["Other handler / 404"]
    P -->|Yes| F["Gateway filter chain"]
    F --> K["Compute representation identity / cache lookup"]
    K --> H{"Valid entry exists?"}
    H -->|Hit| RH["Return stored response per policy"]
    H -->|Miss / fetch needed| LB["Routing, LoadBalancer, downstream"]
    LB --> U["Backend catalog"]
    U --> E{"Is response cache-eligible?"}
    E -->|Yes| W["Write cache + serve response"]
    E -->|No| BY["Serve response without storing"]
    W --> OUT["Client"]
    BY --> OUT
    RH --> OUT
~~~

This diagram illustrates the **lookup → hit/miss → fetch/skip-fetch** flow; it does not prescribe exact ordering across all `GlobalFilter`s, `GatewayFilter`s, `Retry`, `CircuitBreaker`, or URL-normalization filters across all Gateway versions. Verify ordering whenever multiple filters touch the request or response.

### What Caches Typically Store

An entry may retain response body, response headers, and lifetime metadata. Storing data alone is not enough; a cache must also know **when an entry remains valid and which requests may reuse that same entry**.

| Component | Impact on Correctness |
|---|---|
| HTTP method | GET is usually a good candidate; mutating POSTs should generally not be cached naively |
| Path | `/items/42` and `/items/43` require separate data |
| Query string | `?lang=vi` vs. `?lang=en` or `?sort=price` can produce different responses |
| Request headers | `Accept-Language`, `Accept-Encoding`, and other headers can create variants |
| Identity/tenant | Personalized content must be isolated or **never cached in a shared tier** |
| Status code | Not every status code is stored by an implementation |
| Response headers | `Cache-Control`, `Vary`, `ETag`, and HTTP metadata govern policies |
| TTL / invalidation | An entry can remain alive in cache while no longer matching source truth |

**Caching is conditional data reuse**, never a shortcut to skip authentication and authorization.

## 2. `LocalResponseCache`: Enable Only When Scope Is Understood

In supported Gateway Server WebFlux versions, `LocalResponseCache` is a `GatewayFilter` factory that can store response bodies and headers in **the Gateway instance's memory**. Docs for the corresponding lines describe typical conditions such as:

- The request is a **bodiless GET**.
- The response status is supported, typically including `200 OK`, `206 Partial Content`, or `301 Moved Permanently` per version docs.
- Skip storage when the request carries `Cache-Control: no-store` or the response carries `Cache-Control: no-store` / `private` per documented behavior.
- The cache configures **time-to-live (TTL)** and a **size** limit; implementations may use **Caffeine**.
- Some versions calculate/adjust `Cache-Control: max-age` based on remaining entry lifetime.

**Do not extrapolate these rules into a full RFC-compliant HTTP cache.** For example, separately verify `Vary` differentiation, conditional GET/`304`, `Range`/`206`, and payloads carrying `Authorization`. Merely having a cacheable status code **does not mean every response with that status is safe to store**.

### Example Route for a Public Catalog

Suppose `catalog-service` exposes a **genuinely public, non-personalized** API. An illustrative configuration for versions supporting the `LocalResponseCache` shortcut:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: public-catalog
          uri: http://localhost:9090
          predicates:
            - Path=/api/public/catalog/**
            - Method=GET
          filters:
            - StripPrefix=2
            - LocalResponseCache=30s,50MB
~~~

In this example, the intent is caching responses on route `public-catalog` with a ~**30-second** TTL and a **50 MB** size limit. **Shortcut syntax, TTL/size argument order, units, and activation flags must be verified against docs for your exact Gateway version**; real environments also require compatible cache dependencies/implementations.

`StripPrefix=2` drops the two segments `api` and `public`; the backend receives `/catalog/...`. Whether a filter sees the original or rewritten URI depends on filter ordering and implementation. Whenever modifying paths/queries, verify **how two URLs share or split cache entries** rather than guessing cache keys.

### Never Enable Globally Before Classifying Routes

Enabling caching across all routes can store responses from cookie/JWT APIs or tenant-scoped endpoints inside Gateway memory. Safe workflow:

1. Classify **public and stable** endpoints first.
2. Enable caching only for routes with explicit response contracts and TTLs.
3. Test ineligible cases, authorized payloads, and content variants.
4. Expand gradually based on metrics and correctness tests.

For user data such as `/api/me`, orders, invoices, sessions, tokens, or account profiles, **avoid shared Gateway response caching by default** unless a fully proven identity-keyed, invalidation-backed, isolated model exists. Upstream `Cache-Control: private, no-store` is an essential safeguard on sensitive responses.

## 3. Define Hit, Miss, Bypass, and Error Before Computing Ratios

A request entering a cached route does not automatically mean a **lookup actually occurred**. Lumping every non-hit into "miss" produces misleading charts.

| Classification | Interpretation | Counted as Lookup Hit/Miss? |
|---|---|---|
| **HIT** | Found a matching, valid entry; served from cache | Yes |
| **MISS** | Request eligible for lookup, yet no usable entry existed; fetched backend | Yes |
| **BYPASS** | Skipped lookup/cache by policy (e.g., method exclusion, sensitive route, `no-store`) | No, if metrics separate policy bypass |
| **INELIGIBLE** | Request/response outside cacheable rules | Either a bypass reason or tracked separately |
| **EXPIRED / STALE** | Entry expired or failed freshness checks | Explicitly define whether recorded as a miss or separate bucket |
| **ERROR** | Cache lookup/store failed or produced an indeterminate outcome | Track separately; never count as a hit |
| **REVALIDATED** | Revalidated with origin and existing entry remained valid | Use only if implementation supports and actually measures it |

**Recommended convention:** each lookup records **exactly one primary outcome** (`hit` or `miss`). `bypass` and `error` belong in separate buckets. Reasons such as `expired` or `no-store` can serve as secondary tags/labels without double-counting any request in the denominator.

### 5-Minute Metrics Table Example

Suppose traffic to cache-enabled routes over 5 minutes looks like:

| Outcome | Requests |
|---|---:|
| HIT | 800 |
| MISS | 400 |
| Policy BYPASS | 250 |
| INELIGIBLE (no lookup) | 50 |
| **Total requests entering route set** | **1,500** |

Here there were **1,200 eligible lookups**. The cache hit ratio among lookups is:

\[
\text{Hit ratio}_{eligible} =
\frac{H}{H+M} = \frac{800}{800+400}
= 66.67\%
\]

Meanwhile, the share of **total traffic on that route set** served by hits is:

\[
\text{Hit coverage}_{traffic} =
\frac{H}{N_{requests}} = \frac{800}{1500}
= 53.33\%
\]

Both numbers are accurate, **yet answer different questions**. A dashboard showing only "hit ratio 66.67%" without specifying the denominator can mislead teams into thinking Gateway eliminated 66.67% of **all** downstream traffic.

### Ratios to Report Separately

- **Eligible hit ratio:** entry reuse efficiency among requests eligible for lookup.
- **Traffic hit coverage:** percentage of total requests served from cache.
- **Bypass ratio:** share of traffic skipping the cache and why.
- **Cache error ratio:** lookup/store failures over eligible operations.
- **Origin offload:** backend calls genuinely **avoided** thanks to caching, verified via downstream request counters.

**Origin offload does not automatically equal hit coverage** when systems also involve retries, conditional requests, external CDNs, circuit breakers, fallbacks, or fan-out outbound calls per client request.

## 4. Do Not Mistake Gateway Request Metrics for Cache Hit Metrics

Spring Cloud Gateway can emit **Gateway request metrics** via Micrometer/Actuator (such as meters tied to `spring.cloud.gateway.requests` in certain versions). Those metrics help track **routes, HTTP statuses, latency, and total requests**.

However, they **do not prove** a response was a cache hit.

~~~text
GET /api/public/catalog/42 -> HTTP 200, latency 5ms
~~~

A 5ms request could be:
- A Gateway cache hit.
- A very fast backend.
- A CDN/ingress serving from cache before Gateway.
- A fast fallback response.
- A handler that never called a backend.

Likewise, HTTP `200` is not a hit signal; `Cache-Control: max-age=30` does not prove an entry already existed in cache.

### Three Evidence Sources to Correlate

| Source | What It Proves | What It Cannot Prove Alone |
|---|---|---|
| **Cache implementation hit/miss metrics** | Whether lookup used a stored entry | How many attempts hit backend if other tiers intervene |
| **Gateway request metrics** | Traffic, latency, route/status | Whether requests hit or missed cache |
| **Backend request counters / access logs** | How many requests actually hit the service | Why a request never reached the backend |
| **Client HTTP headers/response body** | What the client observed | Where the entry came from without instrumentation |
| **Distributed tracing** | Gateway/downstream path when spans exist | Every hit if instrumentation omits cache decisions |

**Never conclude caching works merely because response time dropped.** Pair a metric capturing the **actual lookup decision** with downstream call counts and a correctness check.

## 5. How to Measure Hits/Misses Without Built-In Standard Metrics

Do not assume every `LocalResponseCache` release automatically emits `cache.hit` or `gateway.cache.hits`. Metric names and availability depend on Gateway version, cache implementation, Spring Boot Actuator, Micrometer binders, and stats flags.

Three approaches:

1. **Use real cache statistics exposed** by Caffeine/implementation where supported (e.g., `hitCount`, `missCount`, `evictionCount`). Check **whether `recordStats` is enabled**, which caches binders recognize, and exact runtime metric names/tags.
2. **Controlled instrumentation at the lookup site** in an application-managed cache filter/service: each decision emits `hit`, `miss`, `bypass`, or `error`. This is the most deterministic approach when built-in metrics are absent.
3. **Empirical correlation**: backend counters + client request counts + controlled test cases proving caching cuts outbound calls when library internals cannot be modified.

Never add a custom `GlobalFilter` that guesses hits from latency or `Cache-Control` headers. That filter **cannot read internal hit/miss decisions** of another filter factory. Accurate metrics require hooking into **the exact component performing the cache lookup**, or a cache component you control.

### Custom Metric Naming Convention (Not Built-In Names)

Example of a counter **explicitly instrumented by your application**:

~~~text
gateway_response_cache_lookups_total{
  route_id="public-catalog",
  outcome="hit"
} 800

gateway_response_cache_lookups_total{
  route_id="public-catalog",
  outcome="miss"
} 400

gateway_response_cache_bypass_total{
  route_id="public-catalog",
  reason="policy"
} 250
~~~

These are **proposed meter names**, not claims that Gateway ships them automatically. Document units and increment conditions for every meter. Define clearly whether errors are excluded from the hit/miss total or categorized inside the same metric.

### Never Use Cache Keys or User IDs as Metric Tags

Use only bounded-cardinality tags, such as:

~~~text
route_id = public-catalog
outcome  = hit | miss | bypass | error
reason   = expired | no-store | unauthorized | method | other
~~~

**Never put** full `url`s with personal queries, session IDs, access tokens, API keys, tenant IDs, emails, or raw cache keys into tags. High cardinality overwhelms Prometheus/metrics backends and risks leaking data.

If per-tenant analytics are required, use dedicated authorized analytics pipelines, finite-group aggregation, and data governance policies instead of emitting millions of time series.

## 6. Computing Hit Ratios in Prometheus/Grafana

**Apply the queries below only if you instrumented and exposed the custom metric** `gateway_response_cache_lookups_total` with the exact `outcome` tag from Section 5. Never paste them expecting output on a Gateway lacking this counter.

### Hit Ratio Across All Routes Over a 5-Minute Window

~~~promql
sum(rate(gateway_response_cache_lookups_total{outcome="hit"}[5m]))
/
sum(rate(gateway_response_cache_lookups_total{outcome=~"hit|miss"}[5m]))
~~~

Multiply by 100 to express as a **percentage** rather than 0 to 1.

### Hit Ratio by Route ID

~~~promql
sum by (route_id) (
  rate(gateway_response_cache_lookups_total{outcome="hit"}[5m])
)
/
sum by (route_id) (
  rate(gateway_response_cache_lookups_total{outcome=~"hit|miss"}[5m])
)
~~~

**When zero lookups occur in the window, the denominator is 0.** Dashboards should display "N/A / no traffic" rather than 0% or 100% hits. Likewise, counter resets/restarts must be handled via `rate`/`increase` semantics rather than subtracting raw counter snapshots.

### Measuring Over Longer Windows

~~~promql
sum(increase(gateway_response_cache_lookups_total{outcome="hit"}[1h]))
/
sum(increase(gateway_response_cache_lookups_total{outcome=~"hit|miss"}[1h]))
~~~

A **5-minute** window spots rapid shifts quickly yet looks noisy at low traffic; **1-hour/24-hour** windows show steady trends. Always display **absolute hit/miss counts alongside percentages**, because 90% of 10 requests is vastly different from 90% of 1 million requests.

### Additional Metrics to Track

| Metric | Benefit |
|---|---|
| Hit/miss/bypass counts & rates | Verifies caching handles expected traffic shares |
| Backend requests per second | Confirms actual backend offload |
| Gateway P50/P95/P99 latency per route | Measures user experience gains beyond averages |
| Cache entry count/weight/evictions | Detects undersized caches or key churn |
| Miss load time | Measures cost of backend fetches after misses |
| Memory/GC/heap and direct memory | Checks whether caching creates resource pressure |
| 4xx/5xx error rates and stale correctness alerts | Prevents trading correctness/safety for high hits |
| Retry attempts / circuit breaker fallbacks | Separates cache offload from resilience paths |

Never assume all metrics are pre-exported; availability depends on project libraries and instrumentation.

## 7. Reading Cache Keys and Defining "Identical" Responses

Two HTTP requests may share a cached representation only when **every factor affecting the response is captured**.

Example:

~~~http
GET /api/public/catalog/items?sort=price&lang=vi HTTP/1.1
Host: api.example.test
Accept: application/json
Accept-Language: vi
~~~

Compared with:

~~~http
GET /api/public/catalog/items?sort=price&lang=en HTTP/1.1
Host: api.example.test
Accept: application/json
Accept-Language: en
~~~

If content is translated by `lang`, the two requests need **distinct cache variants**. Never merge them simply because the path matches.

### Variables to Verify in Cache Keys

| Variable | Example Difference | Risk If Cache Ignores It |
|---|---|---|
| Path | `/items/42` vs. `/items/43` | Serves wrong resource |
| Query | `?page=1` vs. `?page=2` | Serves wrong page |
| Sort/filter | `?sort=price` vs. `?sort=name` | Serves wrong ordering |
| Locale | `Accept-Language: vi` vs. `en` | Serves wrong language |
| Media type | `Accept: application/json` vs. other | Serves wrong representation |
| Encoding | `Accept-Encoding: gzip` vs. `identity` | Sends mismatched body/`Content-Encoding` |
| Tenant | Tenant A vs. B | **Cross-tenant data leak** |
| User/role | User X vs. Y | **Personal data or privilege leak** |
| Feature flag | App version/experiment | Serves wrong content variant |
| Route rewrite | URI before/after `RewritePath` | Key collision or entry fragmentation |

**Never assume `LocalResponseCache` automatically puts all of the above into its cache key** or honors every `Vary` combination as desired. Verify your version's implementation and write **negative tests** for every variable that alters responses.

### Improper Key Normalization Also Causes Bugs

Two query strings:

~~~text
?tag=red&tag=blue
?tag=blue&tag=red
~~~

can have **different semantics** if the backend cares about repeated parameter ordering. Conversely:

~~~text
?sort=price&page=1
?page=1&sort=price
~~~

may mean the exact same thing to an API yet create two separate keys without normalization. Never reorder or drop duplicate query parameters without understanding the backend contract.

**Correctness outweighs saving a few cache entries.** When unsure whether two requests are equivalent, keep them separate or skip caching.

## 8. `Cache-Control`, TTL, and Revalidation: True HTTP Semantics

Relevant response headers:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=30
ETag: "catalog-42-v8"
Vary: Accept-Language

{"id":42,"title":"Product"}
~~~

General meanings:

- `Cache-Control: public`: representation may be stored in shared caches if no other constraints forbid it.
- `max-age=30`: freshness directive of **30 seconds** per HTTP semantics; does not guarantee an actual cache holds it for exactly 30 seconds.
- `ETag`: validator to check whether the representation changed on conditional requests.
- `Vary: Accept-Language`: response selection depends on that header, so HTTP-compliant caches must separate matching variants.
- `Age` (when emitted by a cache/proxy) reports estimated representation age under HTTP; **never assume every `LocalResponseCache` hit emits `Age`**.

### `no-store` Differs From `no-cache` and `private`

| Directive | Key Meaning |
|---|---|
| `no-store` | Do not store the representation under normal caching rules |
| `private` | Forbids **shared caches** from storing; private browser caches follow separate rules |
| `no-cache` | Must not be reused without successful revalidation; **not an absolute ban on storage** |
| `max-age=N` | Freshness duration directive |
| `s-maxage=N` | Shared-cache-specific freshness directive for compliant shared caches |
| `must-revalidate` | Once stale, must revalidate before reuse per HTTP rules |
| `Vary` | Request headers influencing representation selection |

A specific implementation may **not support every HTTP cache directive**. Tests must verify **live runtime behavior** rather than assuming sending `ETag` or `s-maxage` automatically triggers filter revalidation.

### Conditional GET and 304

A client may send:

~~~http
GET /api/public/catalog/42 HTTP/1.1
If-None-Match: "catalog-42-v8"
~~~

If the validator still matches, an HTTP origin can return a bodyless `304 Not Modified` so clients or caches refresh metadata. Yet **never treat 304 automatically as a `LocalResponseCache` hit**. `304` has distinct semantics and requires proper handling of accompanying headers. Filters often cache only specific statuses; if `304` is excluded, how it is returned is a separate integration question.

**Mandatory test**: send requests with and without `If-None-Match`, inspect status/body/ETag/`Cache-Control` through Gateway, and compare against calling origin directly. Never serve a body from the wrong representation or return `304` to a client lacking a matching prior copy.

## 9. Balancing TTL and Data Freshness

Longer TTLs generally boost hit ratios, yet lengthen the window during which users may receive **stale data**.

An API serving public category names can tolerate tens of seconds of lag. An API returning **account balances, reserved inventory, or real-time transaction pricing** is likely unfit for shared caching, even over GET.

### Business Framework for Picking TTLs

| Data Category | Freshness Requirement | Initial Strategy |
|---|---|---|
| Slowly changing public catalog | Short lag acceptable | Bounded TTL, well-tested keys |
| Articles / public info | Minute-level lag if product accepts | TTL + purge/invalidation on publish |
| Campaign display pricing | Business-dependent | Very short TTL or versioned keys; re-verify price at checkout |
| Inventory / reservations | Usually requires fresh reads | Limit or avoid shared response caching |
| `/api/me`, invoices, user profiles | Personalized, sensitive | No shared caching unless isolation is proven |
| Authn/Authz responses | Must reflect immediate revocations | Avoid shared caching; dedicated policy needed |
| Error / fallback responses | Strictly status/contract dependent | Never auto-cache degraded responses just to inflate hits |

With a fixed `30s` TTL, the question is not only "how much does hit ratio rise?" but also **"can the business tolerate showing stale info for that window?"**

### Testing Expiration and Updates

1. Send the first request; confirm accurate response and (if eligible) storage.
2. Call again **within TTL**: expect a hit returning the stored copy.
3. Mutate backend data via a controlled lab step.
4. Call again **before TTL expires**: verify whether the contract permits stale data.
5. Call again **after TTL expires**: expect a miss/fetch returning fresh data, assuming backends and outer caches do not hold old copies.
6. Repeat across multiple Gateway instances to see whether one node returns fresh data while another still serves its old entry.

Never treat a "30-second TTL" as a precision wall-clock stopwatch; scheduling, expiration policies, clocks, `Cache-Control` freshness, and external proxies all affect timing.

## 10. Security Verification: Auth, Cookies, Tenants, and Route Filters

**The gravest risk of a shared response cache is serving one user's or tenant's content to someone else.**

Suppose `GET /api/me` returns:

~~~json
{"userId":"alice","email":"alice@example.test","balance":120}
~~~

If Gateway caches by URI alone and serves that entry to Bob's cookie or token, that is **cross-user data exposure**. A sky-high hit ratio here is a **critical alarm**, not an achievement.

### Default Safety Rules

- Never cache responses varying by JWT, cookie, session, or tenant in a shared Gateway cache without a fully verified partitioning model.
- Backends should mark sensitive responses `Cache-Control: private, no-store` per contract.
- Never place **raw** `Authorization` or cookie values into cache keys, metric labels, or logs.
- Never treat HTTP `200` after authentication as "public"; authenticated users still see different data.
- Verify **Spring Security and `GatewayFilter` ordering**: a cache hit must never become a way to bypass authorization.
- When auto-generating routes via service discovery, ensure global caching is never applied to internal or tenant-sensitive APIs.

### Identity Isolation Test Matrix

| Request | Guarantee Required |
|---|---|
| User A, `GET /api/me` | Sees only A's data |
| User B, same URL | Sees only B's data; never reuses A's entry |
| User A changes role/permissions | Responses stop exposing revoked fields/data |
| Tenant A and Tenant B, same path/query | Zero cross-tenant leakage |
| Missing or expired token/cookie | Security returns 401/403 per policy; cache never bypasses it |
| Client-supplied `X-Tenant-Id` header | Untrusted for keying/authz unless verified |
| Fallback route returning generic payload | Never turns sensitive or error payloads into shared entries |

**If isolation cannot be proven**, the right decision is **disabling Gateway response caching on that route** rather than adding a custom key without testing the full trust boundary.

## 11. `Vary`, Compression, and Range: Test Both Bodies and Headers

Even public APIs produce distinct representations based on request headers. Example:

~~~http
GET /api/public/articles/42 HTTP/1.1
Accept-Language: vi
Accept-Encoding: gzip
~~~

The backend may reply:

~~~http
HTTP/1.1 200 OK
Vary: Accept-Language, Accept-Encoding
Content-Encoding: gzip
Content-Type: text/html; charset=utf-8
~~~

An English request with `Accept-Encoding: identity` **must never receive the gzipped Vietnamese body**.

### Fields to Compare Alongside the Body

| Field | Bug If Inconsistent |
|---|---|
| `Content-Type` / charset | Client misparses representation |
| `Content-Encoding` | Browser fails to decompress, corrupting body |
| `Content-Length` / transfer framing | Truncated body or framing mismatch |
| `ETag` / `Last-Modified` | Validator no longer matches body |
| `Vary` | Returns wrong header variant |
| `Cache-Control` / freshness | Client caches too long or misreads remaining lifetime |
| `Content-Range` and status `206` | Serves wrong byte slice, corrupting files/streams |
| `Set-Cookie` | Replays another user's cookie/session if cached |
| Security / CORS headers | Inconsistent trust boundaries and browser policies |

**Especially for `206 Partial Content`:** if the implementation caches `206`, test requests with distinct `Range` headers. Never let two byte ranges share an entry. `Content-Range` and byte payloads must match the request precisely. For large downloads or streaming, disable Gateway local caching unless cache keys and range handling are proven accurate.

### CORS and Origin

Responses emitting `Access-Control-Allow-Origin` per `Origin` or carrying `Vary: Origin` must preserve variants properly. Caching a public body while attaching Origin A's CORS header to Origin B's response causes browser rejections or broken security policies.

Never assume `DedupeResponseHeader` or `RemoveResponseHeader` fixes cache partitioning bugs. Response header filters can clean up final headers, yet **cannot fix a mismatched cached body**.

## 12. Factors That Artificially Inflate or Deflate Hit Ratios

Hit ratios can shift due to environmental factors without reflecting policy quality.

| Phenomenon | Why It Happens | How to Read the Metric |
|---|---|---|
| Traffic spikes on one "hot" URL | Repeated lookups hit one key | High hit ratio even if most other URLs skip cache |
| Cache just restarted | Empty memory (cold start) | Temporary spike in misses |
| System scales from 2 to 10 Gateway instances | Each instance keeps its own cache | Same keys must warm up across multiple pods |
| Sticky routing pins clients to one node | Warm entries get reused more | Hit ratio depends on load-balancer behavior |
| CDN serves requests in front of Gateway | Gateway never sees hot requests | Gateway hit ratio may drop while total offload rises |
| TTL raised | Entries live longer | Higher hit ratio yet greater stale-data risk |
| Key too broad (omits query/header/tenant) | Distinct requests collide on one key | Hit ratio rises **alongside correctness bugs** |
| Key too granular (includes timestamp/random ID) | Entries rarely get reused | Low hit ratio from fragmentation |
| Backend errors, fast fallbacks | Response times appear shorter | Does not prove cache hits |
| Retries increase | One miss triggers multiple backend calls | Real offload is lower than hit ratio implies |
| Cache evictions from low memory | Entries evicted early | Misses climb; check eviction counts |

**Never optimize hit ratio in isolation.** Enforce guardrails: **zero data leaks**, accurate statuses/headers, valid stale-data budgets, memory caps, P95/P99 latency, and downstream load.

### Local Caching and Multiple Instances

A local cache on Gateway A **does not sync entries** to Gateway B. The same URL can:

- Hit on A because A is warm.
- Miss on B because B has never seen the request.
- Return an old copy from A and a new copy from B right after an origin update.

Therefore, **overall hit ratio must aggregate across all instances**, paired with per-instance charts to spot uneven load. When strict consistency is required, use managed invalidation/versioning or another cache architecture instead of treating local caches as shared distributed state.

## 13. Verification With a Backend Counter and `curl`

### Lab Environment

Assume:

- Gateway: `http://localhost:8080`.
- Public catalog backend: `http://localhost:9090`.
- The `public-catalog` route from Section 2 with `LocalResponseCache` where supported.
- Backend serves `GET /catalog/items/42`, incrementing a counter and returning content version every time it is **genuinely invoked**.
- No CDN, reverse proxy cache, or client SDK retries in the lab to avoid noise.

A demo WebFlux backend:

~~~java
package example.catalog.lab;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class CatalogEchoController {

    private final AtomicInteger originCalls = new AtomicInteger();

    @GetMapping("/catalog/items/{id}")
    public Mono<ResponseEntity<Map<String, Object>>> item(
            @PathVariable String id) {

        int call = originCalls.incrementAndGet();
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("itemId", id);
        body.put("originCall", call);
        body.put("name", "Demo product");

        return Mono.just(ResponseEntity.ok()
            .cacheControl(CacheControl.maxAge(
                java.time.Duration.ofSeconds(30)).cachePublic())
            .body(body));
    }
}
~~~

This code belongs in the **lab backend**, never inside the Gateway process; it lacks auth and is unsuitable for public release. Its counter is **per-process across all requests**, meant only for manual testing against a single backend instance. In production, use proper metrics and omit invocation counts from customer-facing payloads.

### Step 1 — Call the Backend Directly

~~~bash
curl -i "http://localhost:9090/catalog/items/42"
~~~

Verify the response carries the intended `Cache-Control`, `originCall` appears in the body, and the backend works. This is your **control baseline**: the backend endpoint must work cleanly before testing caching.

### Step 2 — First Call Through Gateway

~~~bash
curl -i "http://localhost:8080/api/public/catalog/items/42"
~~~

With a fresh/cold cache and matching route, this is normally a **miss**. With no other lab traffic, `originCall` increments because the backend was called.

### Step 3 — Repeat Immediately Within TTL

~~~bash
curl -i "http://localhost:8080/api/public/catalog/items/42"
curl -i "http://localhost:8080/api/public/catalog/items/42"
~~~

If route caching works and the response is eligible, the backend counter **should not increment further** because the next two requests are served from cache. The body keeps the miss's `originCall`; while convenient in the lab, **lookup/cache instrumentation metrics remain the stronger source of truth**.

Verify simultaneously:

| Observation | Expected on a Genuine Cache HIT |
|---|---|
| Backend counter | Does not increment on hit calls |
| Cache hit metric (if present) | Increments by the exact lookup hit count |
| Client body | Matches representation for the requested URL |
| HTTP status | Matches stored response contract |
| `Cache-Control` | Never advertises freshness beyond configured policy |
| Latency | May drop, yet is not proof on its own |
| Security / headers | Zero sensitive data improperly reused |

### Step 4 — Test Different Queries and Paths

~~~bash
curl -i "http://localhost:8080/api/public/catalog/items/43"
curl -i "http://localhost:8080/api/public/catalog/items/42?lang=vi"
curl -i "http://localhost:8080/api/public/catalog/items/42?lang=en"
~~~

The demo backend above does not vary output by `lang` yet; thus **you cannot prove query-distinct cache keys** from its current body alone. To test rigorously, modify your **lab backend** to return genuinely query-dependent payloads, or use a mock backend with clearly distinct responses. Confirm zero cross-key collisions afterward.

### Step 5 — Wait for TTL and Observe Refresh

Wait past the configured TTL, then call:

~~~bash
curl -i "http://localhost:8080/api/public/catalog/items/42"
~~~

Once the entry expires with no other cache layer active, the backend counter increments and the body reflects a new `originCall`. If it does not increment, inspect effective TTL, warm-up timing, external proxies, and route/cache config on the serving instance.

### Step 6 — Request Carrying `no-store`

~~~bash
curl -i "http://localhost:8080/api/public/catalog/items/42" \
  -H "Cache-Control: no-store"
~~~

In `LocalResponseCache` versions documenting request `no-store` handling, this case must **bypass or avoid storing entries** per the filter's contract. Verify whether the backend is invoked and whether responses are stored. Never assume `Cache-Control: no-cache` shares the same semantics as `no-store`.

### Step 7 — Test Sensitive Responses and Variants

Use a **dedicated mock backend** returning `Cache-Control: private, no-store` on a simulated `/api/me` endpoint; even if a test route has caching configured, verify **zero shared entries are stored**. Next, test responses varying by `Accept-Language`, `Origin`, `Range`, and API-contract headers. Never use real customer data or access tokens in the lab.

## 14. Correctness Test Matrix by Data Type

A meaningful test suite needs both **positive tests** (genuine hits) and **negative tests** (never hitting improperly).

| Case | Condition | Expected Result |
|---|---|---|
| Same public GET, same representation, within TTL | Cacheable endpoint | First misses, subsequent hits |
| Same public URL after TTL | Expired entry | Refetches or enforces freshness per policy |
| Two distinct resource IDs | `/42` and `/43` | Never crosses data across IDs |
| Query alters output | `lang=vi` and `lang=en` | Never serves wrong representation |
| Request carries `no-store` | Excluded by cache policy | Never used/stored against policy |
| Response carries `private, no-store` | Personal data | Never shared-cached |
| Users A/B on same private URL | Different auth | Never leaks A to B |
| Tenants A/B | Different tenants | Proper isolation |
| `Vary: Accept-Language` | Vi/En | Accurate language body |
| `Vary: Accept-Encoding` | gzip/identity | Body and `Content-Encoding` stay aligned |
| `Range` request | Different byte ranges | Accurate `206`/`Content-Range` or not cached |
| `If-None-Match` | Valid vs. invalid validator | Accurate `200`/`304` and body/headers |
| POST update followed by GET | Mutated data | Freshness/invalidation per contract |
| Retry on a miss | Transient backend error | Never caches unintended error/fallback entries |
| CircuitBreaker fallback | Backend outage | Never caches degraded fallback against policy |
| Multiple Gateway nodes | Differing warm entries | Correctness holds even as per-node hit ratios differ |
| Security 401/403 | Bad token / unauthorized | Never bypassed by cache |
| Streaming / committed response | Large body / SSE | Never assumed safe to store or replay |

If a test reveals the cache key ignores a factor the response actually depends on, **disable caching on that route** until fixed properly. Never massage dashboards to make hit counts look better.

## 15. Interactions With Retry, CircuitBreaker, RateLimiter, and Service Discovery

### Rate Limiter

If `RequestRateLimiter` runs before cached responses are returned, both hits and misses consume the client's request budget. If policy requires **hits to cost less than misses**, design around actual filter/metric capabilities rather than assuming one filter knows another filter's cache decision before lookup.

A `KeyResolver` keyed by user/tenant/IP is not a cache key. Users may be rate-limited individually while sharing a **public cached representation**; conversely, a private route does not become safe to cache merely because the rate limiter distinguishes tenants.

### Retry and CircuitBreaker

A cache miss can enter `Retry` and generate **multiple outbound attempts**; a hit can skip this chain if filter ordering allows. Thus:

~~~text
1 cache lookup MISS
  -> Backend attempt #1 (503)
  -> Retry backoff
  -> Backend attempt #2 (200)
  -> May store final response if genuinely eligible
~~~

Elsewhere, `CircuitBreaker` may switch to a fallback. If the fallback returns `200` with degraded data, an overly broad cache can **mistakenly store fallback content as a normal representation**. Check response status, headers, filter ordering, and fallback non-caching rules; never rely on status 200 to assume safety.

### Service Discovery and Multiple Backend Instances

A `lb://catalog-service` URI picks an instance on a cache miss. A local cache hit may **skip LoadBalancer and backend calls** in the pipeline. Yet if backend instances return inconsistent data, misses landing on Instance A vs. Instance B will cache conflicting entries. Ensure origin data consistency before evaluating hit ratios.

### TLS and Proxies/CDNs

Caching never replaces TLS. HTTPS from client → Gateway and Gateway → backend still protects traffic in transit. When a CDN/ingress cache sits in front, distinguish **CDN hits**, **Gateway hits**, and **backend fetches**, each with its own metrics and invalidation. An `X-Cache` header emitted by an external proxy **does not automatically reflect Gateway's `LocalResponseCache`**.

## 16. Dashboards and Operational Procedures

A useful dashboard for each cacheable route should display **effectiveness, correctness, and infrastructure health**:

| Category | Charts / Metrics |
|---|---|
| Traffic | Requests/s, cache-eligible lookups/s, bypasses/s |
| Effectiveness | 5m/1h hit ratio, hit coverage, backend requests/s |
| Latency | Gateway and downstream P50/P95/P99; split hit vs. miss if genuinely instrumented |
| Memory | Cache weight/entry count/evictions; heap/GC |
| Freshness | Effective TTL, expired misses, age when reliable metrics exist |
| Safety | Cross-user/tenant invariant failures, Vary/Range test outcomes |
| Resilience | Retry attempts, breaker opens, fallback rate, 5xx |
| Environment | Per-instance cache stats, deployments/restarts, cache warm-up |

### High-Priority Alerts

- **P95 latency climbs** alongside rising miss rates and backend saturation.
- **Evictions spike** under steady traffic: cache may be undersized or suffering key fragmentation.
- **Hit ratio drops after deploys**: likely cold caches; correlate with restarts and autoscaling events.
- **Gateway serves stale data past allowed TTL**: prioritize correctness alerts over performance.
- **Cross-user/tenant isolation tests fail**: treat as a security incident; disable route caching and investigate.
- **Backend call rate fails to drop** despite high hit metrics: metrics may miscount, retries may amplify, or other traffic hits origin.

Never impose "hit ratio must always exceed 90%" as a universal SLO across every API. For a long-tail URL set with high variant cardinality, low hit ratios are natural; **serving accurate responses** matters far more than chasing high hit percentages.

### Safe Rollout Process

1. Pick **one public GET route** with stable payloads and a business-approved TTL.
2. Run **correctness tests** covering hits/misses, TTL, queries, `Vary`, statuses, and security.
3. Enable caching in staging; compare Gateway metrics against backend request counters.
4. Test restarting/scaling multiple Gateway nodes and measure memory/evictions.
5. Roll out gradually, monitoring hit ratios **alongside** data errors, latency, and offload.
6. Keep a **fast cache-disable plan** ready if leaks, excessive staleness, or HTTP header mismatches appear.
7. Only after stability is proven, evaluate additional routes; each route needs its own data-freshness and authorization contract.

## 17. Troubleshooting: Hit Ratios Not Matching Expectations

| Symptom | Causes to Check | Verification Steps |
|---|---|---|
| Hit ratio stays 0 despite repeating same URL | Filter not loaded, ineligible entries, `no-store`, tiny TTL | Check runtime routes and backend call count |
| High hit ratio yet backend calls remain high | Mis-scoped metric, nested retries, CDN/other traffic | Count outbound attempts per route and instance |
| Only one Gateway node gets hits | Local caches unevenly warmed, skewed load balancing | Inspect per-instance stats and rollout state |
| Hit ratio plunges after deploy | Restarts wiped local caches | Correlate timestamps with startup and warming |
| Data stays stale too long | TTL or external HTTP `Cache-Control`/proxy mismatch | Inspect freshness across layers and backend version |
| User B sees User A's data | Broken cache partitioning or cached private API | **Disable route cache and investigate security immediately** |
| Different queries yield strangely identical bodies | Key ignores queries or backend ignores queries | Use a mock backend returning two distinct versions |
| Language/encoding gets mixed up | Broken `Vary`/cache key | Test `Accept-Language`, `Accept-Encoding`, headers/body |
| `206` Range returns wrong slice | Cache ignores `Range` or wrong metadata | Compare bytes and `Content-Range` |
| `Cache-Control` header changes between hit and miss | Filter adjusts `max-age` to remaining TTL | Check docs and HTTP semantics rather than brittle string equality |
| Unexpected `304` returned | Unsupported conditional GET/revalidation behavior | Check `If-None-Match` and origin behavior |
| Cache metadata missing in Actuator | Binder/stats disabled or library does not expose it | Check actual metric names; never assume built-in availability |
| Memory climbs as cache fills | Oversized entries, weight limits, evictions, body buffering | Inspect heap/GC/Caffeine stats; tune size limits |
| Fallback data gets cached | Fallback response carries cacheable status/headers | Separate routes or set `no-store` and test filter order |
| GET stays stale after POST | Active TTL, missing invalidation, or CDN caching | Define stale budget and purge/version strategy |
| Bug occurs only through ingress | CDN/proxy caching/headers differ from Gateway | Inspect every hop and effective `Vary`/`Cache-Control` |

### Six Investigation Questions

1. **Did the request match the intended route**, and is `LocalResponseCache` actually active on that instance?
2. **Was the request lookup-eligible**? What were the method, body, headers, and policy?
3. **What exact hit/miss event fired at lookup**? Or are we merely guessing from latency/HTTP 200?
4. **Which cache key/variants were used**? Does it separate queries, auth/tenants, locales, and `Range` per contract?
5. **How many attempts did origin actually receive**, and did CDN, Retry, CircuitBreaker, or fallbacks intervene?
6. **Did the final response** match expected body, status, ETag, `Vary`, `Cache-Control`, `Content-Encoding`, and stale budget?

A cache bug is usually a combination of **entry identity + TTL + filter order + security policy**, not just one missing property.

## 18. Self-Assessment and Acceptance Checklist

- [ ] I distinguish **HIT, MISS, BYPASS, INELIGIBLE, ERROR** and define the hit-ratio denominator explicitly.
- [ ] I know how to compute `H/(H+M)` vs. `H/total requests` without conflating them.
- [ ] I never rely solely on HTTP 200, low latency, or `spring.cloud.gateway.requests` as proof of a cache hit.
- [ ] I know hit/miss metrics must originate from **actual cache lookups** or verified instrumentation.
- [ ] I do not assume every version ships identical built-in cache metric names.
- [ ] I keep user IDs, cache keys, raw URL queries, tokens, cookies, and API keys out of metric tags.
- [ ] I selected appropriate public GET routes and set bounded TTL/size limits.
- [ ] I verified `Cache-Control: no-store`/`private` enforcement on my actual implementation.
- [ ] I tested cache keys across paths, queries, headers, and `Vary`.
- [ ] I tested `ETag`/`304`, gzip/identity, and `Range`/`206` wherever APIs use them.
- [ ] I never enable shared caching for personal or tenant-sensitive data without proven isolation.
- [ ] I tested User A/B, Tenant A/B, expired tokens, and 401/403 security rejections.
- [ ] I understand TTL, cold starts, evictions, and stale-data risks after mutations.
- [ ] I count backend calls to verify offload, accounting for retries, fallbacks, and multi-layer caches.
- [ ] I tested multi-instance Gateways where local caches do not share entries.
- [ ] I monitor per-route hit ratios, hit coverage, P95/P99, memory/GC, and backend saturation.
- [ ] I maintain a fast disable/rollback procedure for cache correctness failures or data leaks.
- [ ] I keep TLS, authorization, RateLimiter, Retry, and CircuitBreaker intact as independent policies.

## Official References

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — look up **LocalResponseCache GatewayFilter Factory**, **Local Response Cache Global Filter**, HTTP timeouts, and metrics for **Server WebFlux** by version.
- [Spring Cloud Gateway Project](https://spring.io/projects/spring-cloud-gateway) — project documentation and release trains.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111) — freshness, validation, `private`/`no-store`, `Age`, `Vary`, and shared-cache rules.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) — HTTP methods, statuses 200/206/304, validators, and representation metadata.
- [Caffeine Cache Documentation](https://github.com/ben-manes/caffeine/wiki) — statistics recording and in-process memory bounding when implementations use Caffeine.
- [Micrometer Reference](https://docs.micrometer.io/micrometer/reference/) — counters, tags, and measurement via Micrometer.
- [Prometheus Querying Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/) — `rate`, `increase`, counter math, and observation windows.
- [Spring Boot Actuator](https://docs.spring.io/spring-boot/reference/actuator/) — metrics endpoints, exposure, and securing management APIs.

**Key takeaway:** **A cache hit ratio measures only reuse, never response correctness.** When evaluating Gateway response caching, measure **actual hits/misses at lookup time**, state denominators clearly, and cross-check backend call counts; simultaneously verify **data accuracy across users, tenants, URLs, queries, `Vary`, lifetimes, and statuses/headers**. Whenever a conflict arises, always prioritize **correctness and security** over boosting hit percentages.
