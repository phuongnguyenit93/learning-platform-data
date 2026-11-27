# KeyResolver by User, Customer, API Key, or IP Address in Spring Cloud Gateway

When a Gateway serves thousands of clients, **rate limiting** prevents a single traffic source from exhausting backend capacity. However, simply setting a threshold of "10 requests/second" is not enough: **10 requests/second for whom?** Per user, per customer organization, per API key, per IP address, or for the entire system?

In **SPRING_CLOUD_GATEWAY**, the `RequestRateLimiter` GatewayFilter Factory works with a **`KeyResolver`** to determine the **identifier used as the rate-limit key** for each request. This lesson belongs to the **Traffic Limiting** chapter and dives into choosing keys by user, tenant/customer, verified API key, or IP address, as well as the impact of that choice on fairness, security, abuse prevention, and operating multiple Gateway instances.

This connects with route predicates, filter chains, path/header transformations, service discovery, Spring Security, circuit breakers, retries, TLS, and request observability; **rate limiting does not replace any of those protection layers**.

> **Scope:** Examples apply to **Spring Cloud Gateway Server WebFlux** using configuration syntax common in Gateway 4.x. Newer releases may use different namespaces, such as `spring.cloud.gateway.server.webflux.*`; Server MVC also has a different filter structure and classes. Check your actual Spring Boot, Spring Cloud release train, and Gateway versions before copying. Sample IDs, addresses, limits, domains, and tokens are not production configurations.

## 1. What Is KeyResolver?

`KeyResolver` is a Spring Cloud Gateway interface whose core method is:

~~~java
Mono<String> resolve(ServerWebExchange exchange);
~~~

It receives a `ServerWebExchange`, reads trustworthy information available in the request/context, and returns a **`Mono<String>` containing the key**. For example:

~~~text
Request A: user u-100      -> key = user:u-100
Request B: user u-200      -> key = user:u-200
Request C: user u-100      -> key = user:u-100
~~~

Requests A and C share the same identifier and are therefore counted in the **same limit scope** if they hit the same policy/route limiter. Request B is tracked independently.

**`KeyResolver` does not count requests itself and does not decide replenish/burst values.** It only picks "whose bucket"; the `RateLimiter` handles granting or denying requests against the budget.

### Relationship Between Components

| Component | Responsibility | Example |
|---|---|---|
| **Route Predicate** | Selects the route matching URL/method/host | `Path=/api/orders/**` |
| **`RequestRateLimiter`** | Invokes KeyResolver, applies limiter, may reject request | Filter attached to orders route |
| **`KeyResolver`** | Produces a stable key from request identity/context | `user:8f2…` |
| **`RateLimiter`** | Checks/updates tokens or budget | Redis token bucket |
| **Spring Security / API-key authenticator** | Verifies caller and provides trusted identity | JWT `sub`; validated client ID |
| **Downstream** | Executes business logic when request is admitted | `lb://orders-service` |

~~~mermaid
flowchart TD
    C["Client HTTP request"] --> S["Authentication / trusted proxy context"]
    S --> M{"Gateway route matches?"}
    M -->|No| N["Does not run that route's limiter"]
    M -->|Yes| F["RequestRateLimiter GatewayFilter"]
    F --> K["KeyResolver: Mono<String>"]
    K --> KEY{"Key valid?"}
    KEY -->|No| EMPTY["Empty-key policy"]
    KEY -->|Yes| L["RateLimiter: bucket per configured scope"]
    L --> Q{"Tokens / quota available?"}
    Q -->|No| R["Reject, typically HTTP 429"]
    Q -->|Yes| G["Run filter chain and forward"]
    G --> D["Downstream microservice"]
~~~

**Design takeaway:** a good `KeyResolver` returns an ID that is **stable, leaks no secrets, distinguishes the right actor, and is hard for clients to spoof**.

## 2. Configuring RequestRateLimiter with KeyResolver

Example Gateway with an orders route using Redis Rate Limiter and a bean named `userKeyResolver`:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-api
          uri: lb://orders-service
          predicates:
            - Path=/api/orders/**
          filters:
            - name: RequestRateLimiter
              args:
                key-resolver: "#{@userKeyResolver}"
                redis-rate-limiter.replenishRate: 10
                redis-rate-limiter.burstCapacity: 20
                redis-rate-limiter.requestedTokens: 1
~~~

Meaning of these parameters under the Redis token bucket model:

- `key-resolver: "#{@userKeyResolver}"` references a **Spring Bean** via a SpEL expression. This is **not a header name** read directly by the Gateway.
- `replenishRate: 10`: refills up to roughly **10 tokens/second** into a bucket, subject to the algorithm and runtime conditions.
- `burstCapacity: 20`: maximum bucket capacity is **20 tokens**; allows a short burst when full.
- `requestedTokens: 1`: each allowed request consumes **1 token**.
- When budget is insufficient, the filter typically returns **HTTP 429 Too Many Requests** without forwarding the request.

**This does not mean "strictly at most 10 requests in every 1-second window."** Token bucket allows bursts when tokens are available and refills gradually over time; its semantics differ from a fixed-window counter.

The Redis limiter requires **a running Redis instance and matching dependencies** (typically via Spring Data Redis Reactive) plus Gateway Redis connectivity. YAML declarations alone do not make Redis available. Redis allows sharing limiter state across multiple Gateway nodes; how Redis keys are structured and the algorithm belong to `RedisRateLimiter`'s implementation.

### Key States and Error Codes

| Scenario | What Happens? | How to Interpret |
|---|---|---|
| Route matches, key resolved, bucket has tokens | Request continues through filter chain | Backend may be called |
| Route matches, key resolved, bucket lacks tokens | Typically **429** | Rate limit reached |
| No key / `Mono.empty()` | **Empty key** policy decides, usually deny by default | Do not confuse with an empty token bucket |
| Authentication blocks before route | May be **401/403** | Route's limiter may not have run |
| No route match | Route's limiter does not run | May be 404 or another route |
| Redis encounters an error | Depends on error handling/implementation | Do not assume fail-open or fail-closed |

In supported branches, empty-key policy properties include `spring.cloud.gateway.filter.request-rate-limiter.deny-empty-key` and `spring.cloud.gateway.filter.request-rate-limiter.empty-key-status-code`. Check exact property names and defaults for your version. **Never set `deny-empty-key` to `false` merely to silence errors when a principal is missing.**

## 3. Choosing Keys by Authenticated User

A common use case is **per-user** limiting—for example, allowing one user only a set number of requests/second to the orders API. With reactive Spring Security, you can read the `Principal` from `ServerWebExchange`:

~~~java
package example.gateway.ratelimit;

import org.springframework.cloud.gateway.filter.ratelimit.KeyResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import reactor.core.publisher.Mono;

@Configuration
public class RateLimitKeysConfiguration {

    @Bean("userKeyResolver")
    KeyResolver userKeyResolver() {
        return exchange -> exchange.getPrincipal()
            .ofType(Authentication.class)
            .filter(Authentication::isAuthenticated)
            .filter(auth -> !(auth instanceof AnonymousAuthenticationToken))
            .map(Authentication::getName)
            .filter(name -> !name.isBlank())
            .map(name -> "user:" + name);
    }
}
~~~

The snippet above illustrates reading identity reactively via `exchange.getPrincipal()` without using `ThreadLocal`. In practice:

- `Authentication.getName()` must be a **trusted, stable ID** produced by the configured authentication mechanism.
- Do not assume `getName()` is always an email or always a JWT subject across every OAuth2 provider; inspect the application's principal converter.
- In a multi-tenant system, a username like `alex` alone could collide across two organizations. Include tenant/issuer scoping per policy.
- For unauthenticated public APIs, `exchange.getPrincipal()` may be empty. Keep **deny on empty** behavior or place a separate IP-based limit layer for anonymous traffic rather than accidentally dumping everyone into an `anonymous` bucket.
- If authentication runs **after** the rate-limit filter due to unusual wiring, `KeyResolver` will not yet see the identity. Verify actual security/route filter ordering.

**Never use a display name instead of an ID:** a nickname can change, collide, or be user-chosen. For consistent per-account quotas, choose an immutable subject/account ID per business policy.

### JWT: Choose `sub` Instead of Client-Supplied Data

When the Gateway uses Spring Security OAuth2 Resource Server, a JWT-specific bean can read `sub` from the verified `JwtAuthenticationToken`:

~~~java
import org.springframework.cloud.gateway.filter.ratelimit.KeyResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import reactor.core.publisher.Mono;

@Bean("jwtSubjectKeyResolver")
KeyResolver jwtSubjectKeyResolver() {
    return exchange -> exchange.getPrincipal()
        .ofType(JwtAuthenticationToken.class)
        .flatMap(auth -> Mono.justOrEmpty(auth.getToken().getSubject()))
        .filter(sub -> !sub.isBlank())
        .map(sub -> "user:" + sub);
}
~~~

**Only trust JWT claims after signature, issuer, expiration, and required audience checks pass.** `sub` may only be unique **within an issuer**, not necessarily across the entire platform. With multiple identity providers, include a verified **issuer/client namespace** in the key to prevent ID collisions. Never use the raw JWT string as the key.

## 4. Choosing Keys by Customer, Organization, or Tenant

In B2B APIs, one customer may have **multiple users** sharing a single budget. In that case, limiting by `tenantId` or `clientId` can be more appropriate than limiting by `sub`.

Example:

~~~text
Tenant acme:
  user u1 ─┐
  user u2 ─┼──> key = tenant:acme (shared quota)
  user u3 ─┘

Tenant beta:
  user v1 ────> key = tenant:beta (independent quota)
~~~

### KeyResolver from Verified Tenant Claim

Assuming the Identity Provider issues JWTs containing a `tenant_id` claim and the Gateway validates tokens properly:

~~~java
import org.springframework.cloud.gateway.filter.ratelimit.KeyResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import reactor.core.publisher.Mono;

@Bean("tenantKeyResolver")
KeyResolver tenantKeyResolver() {
    return exchange -> exchange.getPrincipal()
        .ofType(JwtAuthenticationToken.class)
        .flatMap(auth -> {
            String tenant = auth.getToken().getClaimAsString("tenant_id");
            if (tenant == null || tenant.isBlank()) {
                return Mono.empty();
            }
            return Mono.just("tenant:" + tenant);
        });
}
~~~

If `tenant_id` is missing, `Mono.empty()` triggers the filter's empty-key policy. Never fall back to a client-sent `X-Tenant-Id` header without verifying that the user actually belongs to that tenant.

**Multi-tenancy risk:** having a `tenant_id` in the JWT does not replace validating that the user is authorized to act on that tenant. Backends must still enforce resource ownership and tenant isolation. If a user can switch active tenants, `KeyResolver` must read the **system-verified** active tenant, not an unvalidated client parameter.

### Two Budget Layers: Tenant + User

A system might want:

1. Each organization gets at most **1,000 requests/second**.
2. Each user within an organization gets at most **20 requests/second**.

**One `KeyResolver` returning one key does not automatically create two independent counters.** Combining keys into `tenant:acme:user:u1` creates one bucket for **that tenant/user pair**, rather than enforcing both a tenant cap and a user cap simultaneously.

To enforce **two independent policies**, design an extra rate-limiter/filter layer or a centralized quota service that checks both. When using multiple `RequestRateLimiter` filters, understand which routes they apply to, how they are configured, their order, and Redis cost; never assume a one-line config creates hierarchical limits.

| Key Structure | Quota Actually Shared By |
|---|---|
| `tenant:acme` | All users belonging to tenant acme |
| `user:u1` | User u1 within that limiter's scope |
| `tenant:acme:user:u1` | Only u1 inside tenant acme |
| `consumer:mobile-app` | One authenticated application/client |
| `ip:198.51.100.10` | Requests from that resolved IP address |

## 5. Keying by API Key: Only After Verification

API keys often arrive in a header like:

~~~http
GET /api/reports HTTP/1.1
Host: api.example.test
X-API-Key: <secret-api-key>
~~~

An easy-to-write but **insecure** mistake is:

~~~java
// DO NOT USE IN PRODUCTION:
return Mono.justOrEmpty(
    exchange.getRequest().getHeaders().getFirst("X-API-Key")
);
~~~

Why? A client can **generate unlimited random API key strings**, each creating a brand-new bucket if the limiter hasn't verified the key. Moreover, raw keys may end up in Redis keys, logs, or traces, leaking credentials.

### Safer Pattern

1. An **authentication component** validates the API key (or signature, status, scopes, expiration) against a trusted store.
2. That component resolves a **stable consumer ID**, such as `partner-42` or an internal account ID.
3. `KeyResolver` uses only the **verified consumer ID**, never the raw API key.
4. Execution order guarantees the consumer ID is populated **before `RequestRateLimiter`**; if missing or invalid, the request is handled by security/empty-key policy.

Suppose a security `WebFilter` has validated the API key and stored a trusted `verifiedConsumerId` attribute on the exchange. `KeyResolver`:

~~~java
import org.springframework.cloud.gateway.filter.ratelimit.KeyResolver;
import org.springframework.context.annotation.Bean;
import reactor.core.publisher.Mono;

@Bean("consumerKeyResolver")
KeyResolver consumerKeyResolver() {
    return exchange -> Mono
        .justOrEmpty(exchange.<String>getAttribute("verifiedConsumerId"))
        .filter(consumerId -> !consumerId.isBlank())
        .map(consumerId -> "consumer:" + consumerId);
}
~~~

**This is only the `KeyResolver` piece.** This lesson does not imply Spring Security includes a `verifiedConsumerId` attribute out of the box. You must implement and test the authentication component that populates it from API-key verification, with clear rules on lifecycle and trust boundaries.

If one customer holds multiple API keys, use a shared **consumer ID** to apply a per-customer limit. If you want separate quotas per valid key, use a system-issued **non-secret key ID**, never the raw secret key.

### Where Do API Keys Fit in Security Policy?

| Value | Suitable as a Quota Key? | Reason |
|---|---|---|
| Raw `X-API-Key` from request | **No** | Unverified, contains a secret, value can be rotated/spoofed |
| Internal key ID post-auth | Possibly | Stable and contains no secret |
| Consumer/account ID post-auth | Possibly | Multiple keys of one consumer share a quota |
| Tenant ID from self-declared header | No, unless verified | Easy to spoof tenants |
| Verified OAuth2 `client_id` | Possibly | Fits per-application quotas when identity is verified |

## 6. Keying by IP Address: For Bounded Anonymous Traffic

When a public endpoint has neither a principal nor an API key, **IP address** is one option for basic abuse throttling. From a WebFlux request:

~~~java
import java.net.InetSocketAddress;
import org.springframework.cloud.gateway.filter.ratelimit.KeyResolver;
import org.springframework.context.annotation.Bean;
import reactor.core.publisher.Mono;

@Bean("peerIpKeyResolver")
KeyResolver peerIpKeyResolver() {
    return exchange -> {
        InetSocketAddress remote = exchange.getRequest().getRemoteAddress();
        if (remote == null || remote.getAddress() == null) {
            return Mono.empty();
        }
        return Mono.just("ip:" + remote.getAddress().getHostAddress());
    };
}
~~~

This is the **peer IP recognized by the runtime** for the incoming WebFlux connection. If the Gateway sits behind an ingress, load balancer, or reverse proxy, `getRemoteAddress()` may be **the proxy's IP**, forcing all clients into a single bucket.

### Never Trust Raw `X-Forwarded-For`

A request can freely send:

~~~http
X-Forwarded-For: 203.0.113.1
~~~

If you use this header directly as the key, an attacker can swap IPs at will to create unlimited buckets and bypass limits.

**Design a trusted proxy chain**:

- Only trusted ingress/proxies may set or append forwarded headers.
- Edge proxies must strip or overwrite untrusted forwarded headers sent by clients.
- The Gateway/framework must be configured to process forwarded headers under a **trusted proxies** policy matching its version.
- When using proxy-derived IPs, `KeyResolver` must read only the **canonicalized result inside the trust boundary**, never the raw client-supplied header string.
- In specific deployments, rely on verified connection metadata or PROXY protocol rather than guessing from `X-Real-IP`, `Forwarded`, or `X-Forwarded-For`.

~~~mermaid
flowchart LR
    C["Client IP 198.51.100.10"] --> P["Trusted ingress"]
    P -->|Normalized request| G["Gateway"]
    U["Untrusted client-sent X-Forwarded-For"] -.-> P
    P -->|Do not trust spoofed chain| X["Strip or replace forged header"]
    G --> R["KeyResolver reads trusted IP"]
    R --> B["Bucket ip:198.51.100.10"]
~~~

This diagram illustrates the target architecture; **it does not mean every ingress automatically strips forged headers.** You must configure and test it.

### Inevitable Limitations of IP-Based Limiting

| Limitation | Consequence |
|---|---|
| NAT / corporate networks / mobile carriers | Many legitimate users share one IP and may be blocked unfairly |
| IPv6 privacy addresses | Clients rotate addresses, making stable tracking difficult |
| Misconfigured proxy/CDN forwarding | All requests collapse onto the ingress IP |
| Multi-IP botnets | Easily distribute load to stay under per-IP limits |
| IP addresses change over time | Quotas no longer follow accounts |
| IP addresses can be sensitive data | Require storage/logging policies and access control |

Consequently, IP-based limiting works best as a **preliminary defense layer**, not a substitute for user identity or edge/network DDoS mitigation.

## 7. Choosing Strategies by Endpoint Type

No single `KeyResolver` is optimal for every route. Ask: **who consumes resources, who pays, and who can overload downstream?**

| API / Flow | Preferred Key | Reason |
|---|---|---|
| Authenticated user APIs | Verified User ID | Fairness per account |
| B2B SaaS APIs with contract quotas | Verified Tenant/Consumer ID | Entire organization shares a budget |
| Partner integration APIs | Validated API key ID or consumer ID | Manages quotas per licensed client |
| Login pages, public health, landing endpoints | Trusted-proxy-verified IP, or dedicated key | No user identity exists initially |
| Resource-heavy upload APIs | User/tenant + tuned cost weight | Large requests cost more than tiny GETs |
| Sensitive admin APIs | Operator ID and tight quota alongside authorization | Never let anyone bypass permissions just because tokens remain |
| GraphQL / variable-cost operations | Cost-aware limiter if supported, possibly custom logic | One request can vary dramatically in cost |
| Internal service-to-service endpoints | Verified service identity (mTLS/SPIFFE/OAuth2 client) | Isolates traffic per workload |

**Do not use IP as the primary key for authenticated users** when the true goal is per-account quotas; it penalizes NAT users and is easily bypassed by switching networks. Conversely, **do not use user ID as the key for an unauthenticated login page**, because no verified identity exists yet.

### Which Endpoints Should Not Share the Same Policy?

A cached read GET and a transaction-creating POST have different costs and risks. Using the same key across **different route/filter policies** creates separate quotas; you can also deliberately share a budget using a custom limiter. Document the intended behavior explicitly rather than letting it emerge accidentally from route ID naming.

## 8. Bucket Scope: Route ID and the Key Returned by KeyResolver

An advanced yet critical detail: with default wiring, `RequestRateLimiter` operates in **route context**. `RedisRateLimiter` is normally passed both the **route ID** and the **resolved key** when constructing Redis storage keys. Therefore:

- Two requests with `user:u1` on the **same route** share a bucket.
- The same `user:u1` across **two different routes** can hit **two independent buckets**, even though `KeyResolver` returns the exact same string.
- Merely prepending `routeId` inside `KeyResolver` **does not create a global quota**, and is redundant if the Redis limiter already partitions by route.
- To enforce **a single shared limit across multiple routes**, choose a limiter supporting cross-route pooling/costing or build a custom centralized rate limiter/policy; never assume returning the same user ID is enough.

Example:

~~~text
Route orders-read:
  Redis limiter scope = orders-read + user:u1

Route reports-read:
  Redis limiter scope = reports-read + user:u1

=> Two independent buckets in standard RedisRateLimiter config.
~~~

A system may intentionally set two separate limits: "10 GET orders/s" and "2 GET reports/s." When adding a third route, design its quota explicitly rather than assuming it inherits a global user limit.

### Structured Composite Keys

For custom limiters or policies requiring tenant/user separation, you can build keys like:

~~~text
tenant:<trustedTenantId>:user:<trustedSubjectId>
~~~

Ensure both IDs are **normalized/encoded unambiguously**. If IDs can contain the delimiter `:` or unusual characters, use normalized internal UUIDs/IDs or safe encoding. Never let client-supplied strings directly generate arbitrary Redis keys, causing key-space explosion.

## 9. Handling Empty Keys and Errors: Policies Must Be Explicit

`KeyResolver` returns `Mono.empty()` when no trustworthy key is found. This is not the same scenario as "key resolved, but bucket out of tokens."

On Gateway versions supporting configuration:

~~~yaml
spring:
  cloud:
    gateway:
      filter:
        request-rate-limiter:
          deny-empty-key: true
          # empty-key-status-code can be configured
          # per the docs and namespace of your running version.
~~~

`deny-empty-key: true` expresses the intent to **reject requests lacking a key**. The HTTP status for empty keys is governed separately by implementation/version (often different from the `429` returned for an exhausted bucket). Never hardcode tests expecting every missing-key case to return `429`.

### Four Strategies for Missing Keys

| Strategy | Pros | Risks |
|---|---|---|
| **Deny empty key** | Prevents quota bypass | Public endpoints may be rejected if unauthenticated |
| Fallback to verified IP | Works for anonymous traffic | Must handle proxy trust, NAT, and privacy |
| Shared `anonymous` bucket | Easy cap on total anonymous requests | One bad actor can starve everyone's quota |
| Allow through when key is missing | Avoids blocking valid edge cases | Easily creates rate-limit bypasses if key resolver breaks |

If falling back from user → IP, **design request types** and authentication order explicitly rather than grabbing arbitrary data. Example logic:

~~~text
If principal is authenticated and has a stable user ID:
    key = user:<id>
Else if endpoint is public and IP was verified by a trusted proxy:
    key = ip:<client-ip>
Else:
    return no key -> apply explicit deny / error policy
~~~

**Fail-open vs. fail-closed on Redis errors is a separate decision from `deny-empty-key`.** `deny-empty-key` only covers **unresolved keys**; it does not govern behavior when the Redis backend suffers network errors. Verify exception propagation/fallback behavior in your version and set safety boundaries for critical APIs.

## 10. Ordering with Spring Security, GatewayFilters, and Service Discovery

In Gateway Server WebFlux, Spring Security normally runs at the **WebFilter** layer before requests enter a route's `GatewayFilter` chain. As a result, `exchange.getPrincipal()` already holds the authenticated identity when `RequestRateLimiter` runs.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Spring Security WebFilters
    participant G as Gateway Route Filter Chain
    participant K as KeyResolver
    participant R as RedisRateLimiter
    participant B as Backend
    C->>S: HTTP request + Bearer token
    S->>S: Validate token + authorize
    alt Invalid token / missing permission
        S-->>C: 401 / 403
    else Permitted
        S->>G: Request passed security
        G->>K: resolve(exchange)
        K-->>G: user:sub-123
        G->>R: isAllowed(routeId, key)
        alt Insufficient tokens
            R-->>G: not allowed
            G-->>C: 429
        else Permitted
            R-->>G: allowed
            G->>B: Route/LoadBalancer/forward
            B-->>C: Response via Gateway
        end
    end
~~~

This has several consequences:

1. **401/403 can fire before 429**. An attacker without a valid JWT does not spend tokens from the user's bucket because the `GatewayFilter` never ran.
2. To throttle login/invalid-token floods as well, add a **pre-authentication limiting layer** (e.g., ingress/WAF, WebFilter-level rate limiting, or proxy) with an appropriate identifier.
3. `GlobalFilter` and `GatewayFilter` have `Ordered` priorities; if a custom filter populates a trusted consumer ID *after* `RequestRateLimiter`, `KeyResolver` will not see it.
4. `lb://service-id` picks an instance after route matching; a per-user/per-tenant limiter does not automatically become a per-backend-instance limiter.
5. `Retry` can turn one admitted Gateway request into **multiple outbound attempts**. A rate limiter placed before `Retry` typically counts per client request, not per backend attempt. Design retry budgets and timeouts separately.

### Warning About Internal Headers

A `GlobalFilter` might attach `X-Authenticated-User` after authentication, yet `KeyResolver` must never blindly trust **whatever header happens to sit on the exchange**. If clients can send that same header and it isn't stripped, spoofing becomes possible. Prefer principals, verified claims, or exchange attributes written exclusively by security components.

## 11. Redis Token Bucket: Understanding Parameters and Live Behavior

In the Redis token bucket model:

~~~text
burstCapacity: 20 max tokens
replenishRate: 10 tokens/second
requestedTokens: 1 token/request

When bucket is full:
  Up to roughly 20 closely spaced requests can pass,
  then requests must wait for token replenishment.
~~~

**Do not treat 20/10 as exact guarantees in every stress test.** Outcomes depend on request timing, concurrency, Redis latency, bucket initialization, refill granularity, and client/load-balancer jitter.

### Average Limit Lower Than One Request per Second

To target roughly **1 request per 20 seconds**, some `RedisRateLimiter` guides use:

~~~yaml
filters:
  - name: RequestRateLimiter
    args:
      key-resolver: "#{@userKeyResolver}"
      redis-rate-limiter.replenishRate: 1
      redis-rate-limiter.burstCapacity: 20
      redis-rate-limiter.requestedTokens: 20
~~~

Under this model, 1 token is added per second, each request costs 20 tokens, and the bucket holds at most 20: after one successful request, roughly 20 seconds are needed to refill enough for the next, all else equal. **Test this limit in practice** rather than copying it to production without matching business needs.

### Redis Operational Factors

| Concern | What to Monitor |
|---|---|
| Multiple Gateway instances | Are they sharing the same Redis/namespace and limiter configuration? |
| Redis cluster/latency | Network errors, script execution times, and timeouts |
| Route ID changes | Buckets may shift scope because Redis keys include the route |
| Many dynamic keys | Memory/key churn and key-space DoS risk |
| Clock/time windows | Algorithm behavior across clock drift or restarts |
| Rate-limit response headers | Quota headers (if enabled) and consistency with policy |
| Observability | Allowed/denied counts, 429s, Redis latency, resolver errors |

Do not use this limiter to replace volumetric DDoS mitigation at the ingress/CDN; floods can exhaust network resources before the Gateway even calls Redis.

## 12. Hands-On Exercise: Comparing User, Consumer, and IP Keys

### Setup

Assumptions:

- Gateway Server WebFlux runs on port `8080`, orders backend serves `/orders/42`.
- Redis is available for `RedisRateLimiter`.
- Spring Security JWT Resource Server validates test users' JWTs.
- `KeyResolver` bean `userKeyResolver` or `tenantKeyResolver` is registered and selected in config.
- `lb://orders-service` resolves via DiscoveryClient/LoadBalancer, or temporarily points to `http://localhost:9090` in a discovery-free lab.

Example route with a small limit for easy observation:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-lab
          uri: http://localhost:9090
          predicates:
            - Path=/api/orders/**
          filters:
            - StripPrefix=1
            - name: RequestRateLimiter
              args:
                key-resolver: "#{@userKeyResolver}"
                redis-rate-limiter.replenishRate: 2
                redis-rate-limiter.burstCapacity: 3
                redis-rate-limiter.requestedTokens: 1
~~~

`StripPrefix=1` only rewrites the path; the key comes from the Spring Security principal. The backend receives `/orders/42` if no other path filters run.

### Step 1 — Send Requests as User A

Assuming a valid test token has been issued for user A:

~~~bash
# Replace <JWT_USER_A> with a valid TEST access token for user A.
curl -i -H "Authorization: Bearer <JWT_USER_A>" \
  http://localhost:8080/api/orders/42
~~~

Send multiple requests **within a short window**; some will return `429` once the bucket empties. Exact counts depend on timing and prior bucket state. Never log real tokens or commit tokens into a repository.

### Step 2 — Compare with User B

~~~bash
curl -i -H "Authorization: Bearer <JWT_USER_B>" \
  http://localhost:8080/api/orders/42
~~~

If both tokens are valid, principal IDs differ, and the policy uses `userKeyResolver`, B is tracked in B's own bucket. If B immediately gets 429 with a fresh bucket, check whether principal IDs actually differ, route IDs, leftover Redis state from prior tests, or limiters at other layers.

### Step 3 — Switch to `tenantKeyResolver`

Update:

~~~yaml
key-resolver: "#{@tenantKeyResolver}"
~~~

Use two test tokens belonging to **the same tenant** with different `sub` values. Both resolve `tenant:<id>` and share one budget. A token from another tenant hits a different bucket. For fair comparison, reset test buckets through approved procedures or use a new test route ID; never delete production Redis keys.

### Step 4 — API Key Consumer

Only once API key verification and trusted `verifiedConsumerId` population are in place, update the route to:

~~~yaml
key-resolver: "#{@consumerKeyResolver}"
~~~

Send two valid API keys belonging to the same consumer and verify they share the consumer-ID quota. Send a bogus API key: the request must be rejected by the authentication component or lack a trusted consumer ID; **never spawn a new bucket from an unverified fake API key string**.

### Step 5 — Anonymous IP Policy

On a separate public route, use `peerIpKeyResolver` with verified proxy trust. Send multiple requests from the same peer IP, then test behind a reverse proxy and inspect `getRemoteAddress()` at the Gateway:

- If every client collapses onto the ingress IP, IP-based limiting no longer distinguishes clients.
- If raw client-edited `X-Forwarded-For` alters quotas, there is a security flaw.
- If IP is unresolved, verify expected empty-key policy behavior.

### Testing Matrix

| Test | Resolver | What to Observe |
|---|---|---|
| Multiple requests, same user | User ID | Shared bucket; exceeding threshold returns 429 |
| Two independent users | User ID | Isolated buckets when IDs differ |
| Two users, same tenant | Tenant ID | Shared limit when tenant matches |
| Two API keys, same consumer | Trusted consumer ID | Shared limit per consumer |
| Invalid API key | Consumer ID | Never mints a key from a bogus secret |
| Client behind proxy | Peer/trusted client IP | Real client IP per trust boundary, not just ingress IP |
| Unauthenticated request | User ID | Clear security/empty-key policy behavior |
| Request on different route | User ID | Verify quota isolates by route ID as designed |
| Redis failure | Any resolver | Verify fail policy and actual HTTP status |

## 13. Troubleshooting by Symptom

| Symptom | Possible Cause | Resolution |
|---|---|---|
| All requests rejected before 429 | Authentication returns 401/403; no principal | Check security chain and tokens before debugging Redis |
| Empty key for logged-in user | `KeyResolver` extracts wrong `Authentication` or converter emits blank ID | Check principal type and bean name |
| All users share one quota | Key is always `anonymous` or ingress IP | Use verified user/consumer ID |
| One user gets unusually many buckets | Key derived from raw token, mutable email, or arbitrary path/query | Use stable internal ID and canonicalize keys |
| 429 only on certain nodes | Mismatched Redis/cache/config or inconsistent route IDs | Audit all Gateway instances |
| 429 triggers too early | Burst too small, `requestedTokens` too high, or test reused an old bucket | Check config, Redis state, and timing |
| Never see 429 under load | Limiter not bound to route, empty key bypassed, Redis policy, route mismatch | Inspect runtime routes/filter chain and HTTP responses |
| Random API keys keep getting fresh quotas | Key read from raw header | Enforce API-key validation before rate limiting |
| IP key changes with spoofed `X-Forwarded-For` | Trusting client-supplied forwarded headers | Configure trusted proxy chain |
| NAT users unfairly blocked | IP-based quota groups many users | Switch to user/tenant when authenticated; tune anonymous policy |
| Redis outage yields 5xx | Implementation error handling fails SLO | Check circuit/timeouts and approved fail-open/fail-closed policy |
| Same user across routes doesn't share quota | Buckets partitioned by route ID | Build custom shared quota if a global limit is truly desired |
| Backend overloaded despite few 429s | Retries multiply outbound attempts or heavy requests cost too little | Design retry budgets, cost-aware limits, and capacity management |
| Sensitive info leaked in logs | Logging raw JWT/API key/session ID inside keys | Use internal IDs only; mask/sanitize logs |

**Quick triage checklist:** (1) did the request pass authentication; (2) did a route match; (3) what key does `KeyResolver` return and is it trusted; (4) which limiter/route owns that key; (5) is Redis healthy; (6) did the rejection come from the Gateway or backend. Never read or log raw credentials during troubleshooting.

## 14. Production Design and Operating Principles

1. **Authenticate before trusting identity:** prefer principals, validated JWT claims, mTLS identities, or verified consumer IDs; never trust self-declared headers.
2. **Choose a clear quota owner:** user, tenant, consumer, service identity, or trusted client IP. Document why those actors share a budget.
3. **Do not confuse composite keys with hierarchical quotas:** a `tenant:user` key is a single bucket, not simultaneous tenant and user limits.
4. **Design route scope:** remember `RedisRateLimiter` partitions by route ID; build a custom policy if quotas must span routes.
5. **Layer defenses:** throttle anonymous/invalid-auth traffic at the edge, authenticated calls at the Gateway, and resource/cost risks in backends.
6. **Constrain empty/error behavior:** prevent bypass when principals are absent; define explicit behavior when Redis is unavailable.
7. **Align budgets with true cost:** `requestedTokens` handles static per-route cost, while dynamic cost requires dedicated custom logic and testing.
8. **Govern discovered routes:** routes generated dynamically from a registry might miss default policies; verify public routes are protected.
9. **Never treat rate limits as authorization:** remaining tokens do not grant access; invalid JWTs must still be rejected.
10. **Watch retries and circuit breakers:** one edge-admitted request can trigger multiple backend calls; bound retries, timeouts, and enforce idempotency.
11. **Protect Redis and data:** use network isolation, access controls, TLS where appropriate, and keep secrets/unneeded PII out of quota keys.
12. **Observe without leaking:** track 429s, deny rates, Redis latency, route IDs, and key classes (never log sensitive keys).
13. **Test multi-instance and proxies:** verify shared Redis backends, true client IPs, and downstream failure policies.
14. **Change limits cautiously:** assess customer impact, roll out gradually, and keep rollback and alerts ready.

## 15. Self-Assessment Checklist

- [ ] I can explain how `KeyResolver.resolve(exchange)` returns `Mono<String>` and what `RequestRateLimiter` does.
- [ ] I understand the Redis token bucket with `replenishRate`, `burstCapacity`, and `requestedTokens`.
- [ ] I know when to choose user ID (per-account), tenant ID (per-customer), and consumer ID (per-API-key).
- [ ] I **never** use raw API keys or raw JWTs as rate-limit keys.
- [ ] I ensure `JwtAuthenticationToken`/`Authentication` is verified before reading `sub`/client ID.
- [ ] I do not take tenant IDs from unverified headers or unvalidated client claims.
- [ ] I distinguish peer IP from proxied client IP and do not trust raw `X-Forwarded-For`.
- [ ] I account for NAT, IPv6 privacy addresses, and botnets when using IP quotas.
- [ ] I understand `Mono.empty()` triggers `deny-empty-key` behavior and differs from an empty token bucket.
- [ ] I do not accidentally allow empty-key bypasses or unintended Redis fail-open behavior.
- [ ] I understand `RedisRateLimiter` typically scopes quotas by **route ID + key**, not automatically globally across routes.
- [ ] I have verified ordering across security, `GatewayFilter`s, and custom authentication attributes.
- [ ] I know 401/403 differs from 429 and requests blocked pre-route do not spend user bucket tokens.
- [ ] I understand retries/fallbacks and rate limiting may count different request units.
- [ ] I have tested user A/B, tenant, validated API key, proxy IP, multi-instance, and Redis failure cases.
- [ ] I monitor denied/allowed counts, Redis latency, 429s, and backend capacity without exposing secrets.
- [ ] I still maintain authorization, TLS, discovery route governance, circuit breakers, and observability as independent controls.

## Official References

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — **RequestRateLimiter GatewayFilter Factory**, **Redis RateLimiter**, `KeyResolver`, and route configuration for your **Server WebFlux** version.
- [Spring Cloud Gateway project](https://spring.io/projects/spring-cloud-gateway) — project documentation, releases, and release trains.
- [Spring Security Reactive Reference](https://docs.spring.io/spring-security/reference/reactive/index.html) — principal/JWT authentication and `SecurityWebFilterChain`.
- [Spring Security Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html) — validating JWTs and trustworthy claims.
- [Spring Framework — ServerWebExchange](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html) — `getPrincipal()`, request, and exchange attributes.
- [Redis documentation](https://redis.io/docs/latest/) — Redis state infrastructure, performance monitoring, and access security.

**Key takeaway:** `KeyResolver` answers **"whose budget does this request consume?"** Choose an **authenticated user** for per-account quotas, a **verified tenant/consumer** for customer or API-key quotas, and a **trusted-proxy-verified IP** for anonymous traffic. When keys are missing, Redis fails, or multiple routes/instances exist, policies must be explicitly defined; otherwise rate limiting is easily bypassed or blocks legitimate users.
