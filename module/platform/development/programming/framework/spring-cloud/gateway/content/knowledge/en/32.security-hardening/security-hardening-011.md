# Controlling Error Responses, Security Headers, and Exposed Deployment Details

## 1. Objective: A Secure Entry Point That Reveals No Internal Structure

In the **SPRING_CLOUD_GATEWAY** module, Gateway selects routes via predicates, runs filter chains, modifies paths/headers, resolves microservices via discovery/load balancing, and enforces policies such as authentication, rate limiting, circuit breakers, retries, TLS, and observability. At runtime, those layers can emit several kinds of HTTP responses: some from Gateway, some from Spring Security, and others from backends. Not every response is protected identically.

For example, suppose a client calls:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer test-token
~~~

When a service is unavailable, a response **must not** leak:

~~~http
HTTP/1.1 500 Internal Server Error
Server: ReactorNetty/1.x
X-Upstream-Host: orders-7f68d9cc58-4xg2b.internal:8081
Content-Type: text/plain

java.net.ConnectException: Connection refused:
connect to orders-7f68d9cc58-4xg2b.internal/10.42.5.31:8081
at reactor.netty.http.client.HttpClientConnect...
~~~

This is a **counterexample**: pod names, internal IPs, implementation classes, server versions, and stack traces do not belong in client-facing responses. If Gateway forwards a backend error body verbatim, SQL messages, internal hostnames, exceptions, or tokens can leak in the same way.

A better target is:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Cache-Control: no-store
X-Content-Type-Options: nosniff

{
  "type": "https://api.example.test/problems/upstream-unavailable",
  "title": "Service temporarily unavailable",
  "status": 503,
  "detail": "Please try again later.",
  "code": "UPSTREAM_UNAVAILABLE"
}
~~~

This response is an **illustrative contract**. Spring Cloud Gateway does not automatically turn every connection error into this exact body and status. Achieving this contract requires deliberate exception handling, error serialization, or response policies; status codes must accurately reflect real faults rather than being overwritten blindly.

The lesson **"Controlling Error Responses, Security Headers, and Exposed Deployment Details"**, in the **Security Hardening** chapter, focuses on three core tasks:

1. **Error control**: distinguishing routing, security, upstream HTTP response, timeout, and application exceptions; returning appropriate status codes and bodies without leaking stack traces.
2. **Response header hardening**: HSTS, CSP, `X-Content-Type-Options`, clickjacking protection, `Referrer-Policy`, caching, CORS, and cookies; preventing missing or duplicated headers.
3. **Preventing deployment leaks**: server fingerprints, internal hostnames/ports/IPs, debug headers, absolute redirects, Actuator exposure, logs/traces, and personal data.

After completing this lesson, you will be able to design a safe error contract, configure filters and security controls at the right tier, verify responses from both Gateway and backends with HTTP integration tests, and build a secure deployment checklist.

> **Scope:** Primary examples target **Spring Cloud Gateway Server WebFlux** using reactive Spring Security, Reactor Netty, and modern Spring Boot. Gateway Server Web MVC and Proxy Exchange MVC run on a different stack; the same security principles apply, though Servlet apps do not use `GlobalFilter`/`WebFilter`/`SecurityWebFilterChain` directly.

## 2. Threat Model: What Can Clients Infer from HTTP Responses?

Types of information that can accidentally leak:

| Category | Examples | Potential Impact |
| --- | --- | --- |
| Framework/server | `Server: nginx/1.xx`, `X-Powered-By`, framework/version banners | Aids fingerprinting and selecting targeted exploits |
| Internal infrastructure | `orders.default.svc.cluster.local`, private IPs, container/pod IDs, upstream ports | Reveals topology, service names, and internal management endpoints |
| Runtime exceptions | Java class names, stack traces, file/classpath paths, Netty SSL errors | Exposes implementation details and infrastructure state |
| Database | SQL statements, table names, JDBC URLs, migration errors | Leaks schema and data details |
| Authentication | JWT/session tokens, cookies, signing metadata, OAuth codes, login exceptions | Credential leakage and account enumeration |
| Authorization | Distinguishing 403 vs. 404 on unauthorized objects | Probes existence of restricted resources |
| Service discovery | Route IDs, service registry instance IDs, environment tags | Reveals internal microservice layout |
| Debug/metrics | Actuator `env`, `configprops`, `heapdump`, `gateway` routes, health details | Exposes secrets/configs and allows route mutation if permissions are too broad |
| Backend headers | `X-Backend-Server`, `X-Trace-Debug`, `Via`, internal `Location` | Reveals internal routes/paths and backend identities |
| Client-supplied headers | `Forwarded`, `X-Forwarded-Host`, `X-Debug` | Enables host poisoning or spoofing if processed unsafely |
| Backend error bodies | Raw validation DTOs, PII, echoed payloads | Discloses sensitive data outside the API contract |

**Not every `Server` banner or route ID is a critical vulnerability**, and stripping a banner never patches a CVE. Still, under defense-in-depth, clients should only receive **data belonging to the public API contract**.

### 2.1. Three Trust Zones

~~~mermaid
flowchart LR
    C["Untrusted<br/>public client"] --> I["CDN/Ingress<br/>edge policy"]
    I --> G["Spring Cloud Gateway<br/>routing + security"]
    G --> O["Backend services<br/>upstream HTTP"]
    G --> M["Management plane<br/>private access"]
~~~

- Clients can freely forge `Host`, `Origin`, `Forwarded`, query strings, bodies, and request headers.
- Edge proxies must sanitize forwarded headers and block clients from bypassing trusted paths.
- Gateway must enforce authentication/authorization, route allowlists, and error/header policies.
- Backends must never implicitly trust every caller and must also sanitize business errors and secrets.
- The management plane should be isolated from the public data plane via separate networks and access controls.

## 3. One Status Code Can Have Multiple Origins

An HTTP 404, 500, or 503 observed by a client does not automatically identify **which layer** produced it.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Spring Security
    participant G as Gateway filters/router
    participant U as Backend
    C->>S: GET /api/orders/42
    alt Unauthorized
        S-->>C: 401 or 403
    else No matching route
        S->>G: request passed security
        G-->>C: 404 or custom no-route response
    else Matched route
        S->>G: authorized request
        G->>U: forwarded HTTP request
        alt Backend returns HTTP 422/503
            U-->>G: status + body + headers
            G-->>C: HTTP response proxied/transformed per policy
        else Connect/TLS/timeout before receiving response
            G-->>C: Gateway/framework error handler
        end
    end
~~~

### 3.1. Classification by Origin

| Situation | Decision Point | What Not to Do |
| --- | --- | --- |
| 401 missing token | Spring Security entry point | Return 200 + HTML login on a pure JWT API without a contract for it |
| 403 missing scope/permission | Authorization layer | Return internal details of policy or role mappings |
| 404 unmatched route | Gateway/WebFlux handler mapping | Immediately assume the backend resource does not exist |
| 404 backend resource missing | Backend | Blindly turn it into 500 |
| 400/422 invalid body schema | Backend or request validation | Dump raw bodies, class names, or SQL errors |
| 429 quota exhausted | `RequestRateLimiter`/edge | Auto-retry and amplify load further |
| 502/503/504 network/resilience | Gateway, ingress, load balancer, custom error handling | Claim every `ConnectException` maps to one fixed default status across all releases |
| 503 returned by backend | Backend HTTP response | Label it a connection failure when upstream actually returned HTTP |
| 500 Gateway filter exception | Reactive error chain | Expose stack traces in the response body |
| 200 from circuit breaker fallback | Fallback policy | Let clients think a write succeeded without proof |

**Distinguish Gateway-generated statuses from upstream statuses** using recorded upstream requests, route IDs, redacted trace/log metadata, and error categories rather than guessing from the status code alone.

### 3.2. Unmatched Route 404 vs. Upstream 404

~~~text
GET /unknown
  -> no route matched -> Gateway/WebFlux 404
  -> upstream requests = 0

GET /api/orders/999
  -> matched orders-api, called /orders/999
  -> upstream returned 404
  -> upstream requests = 1
~~~

Both responses can carry the same status code, yet logging, problem codes, and alerting should distinguish them. A public API variant may intentionally return uniform bodies to hide resource existence, while internal observability still needs to pinpoint the source.

### 3.3. Retries, Circuit Breakers, and Mid-Stream Disconnects

If a route uses `Retry` and the backend returns `503` on the first attempt, the client may only observe the final `200` after retry. If a `CircuitBreaker` returns a fallback, the client might receive `200` even though **the backend was never invoked**. Therefore, never rely solely on HTTP 200 to confirm a business side effect; writes like `POST`/payments require idempotency, verification, and status codes matching actual outcomes.

On timeouts or connection resets, response bytes may already have started streaming. Once a response is committed, Gateway **cannot reliably replace the entire body with Problem Details**; streaming cancellations and transport errors require separate handling.

## 4. Defining a Minimal Public Error Contract

A well-designed API contract typically specifies:

- **Semantically accurate HTTP status codes**.
- Stable, system-defined error codes.
- Safe messages clear enough for callers to act on without exposing hostnames, stack traces, or internal config.
- An appropriate `Content-Type`, such as RFC 9457 `application/problem+json`.
- Policy-governed correlation/trace IDs containing zero PII and never acting as credentials.
- `Cache-Control: no-store` on sensitive or auth-related responses.
- `Retry-After` on 429/503 when backed by a clear policy, never arbitrary values.

### 4.1. RFC 9457 Problem Details Example

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/invalid-request",
  "title": "Invalid request",
  "status": 400,
  "detail": "One or more fields are invalid.",
  "code": "INVALID_REQUEST"
}
~~~

RFC 9457 standardizes fields such as `type`, `title`, `status`, `detail`, and `instance`. `code` is an **application-defined extension member**, not a mandatory RFC field. Never pass raw validation objects containing passwords/tokens or SQL error strings into `detail`.

### 4.2. Error Codes Can Be More Specific Than Status Codes

| HTTP Status | Suggested `code` | Safe `detail` |
| --- | --- | --- |
| 400 | `INVALID_REQUEST` | Request format is invalid |
| 401 | `AUTHENTICATION_REQUIRED` | Authentication is required |
| 403 | `ACCESS_DENIED` | Access is denied |
| 404 | `RESOURCE_NOT_FOUND` | Resource not found |
| 405 | `METHOD_NOT_ALLOWED` | HTTP method not supported |
| 413 | `PAYLOAD_TOO_LARGE` | Request body exceeds allowed size |
| 429 | `RATE_LIMITED` | Too many requests |
| 502 | `BAD_GATEWAY` | Upstream response unavailable |
| 503 | `SERVICE_UNAVAILABLE` | Service temporarily unavailable |
| 504 | `GATEWAY_TIMEOUT` | Upstream request timed out |
| 500 | `INTERNAL_ERROR` | Unexpected server error |

This is a **design suggestion**, not a built-in table generated automatically by Spring Cloud Gateway. Map statuses based on **real exceptions and upstream semantics** rather than collapsing every exception into `503`.

### 4.3. When Should You Mask 403 as 404?

Some APIs do not want unauthorized callers to learn whether a resource exists. Returning **404 instead of 403** can make sense in business-layer authorization, provided:

- You enforce it consistently without leaking existence via timing, body size, or header differences.
- Internal logs still preserve the true cause (403 vs. 404).
- You never disguise 500 errors as 404s.
- Public contracts are aligned with security and product teams.
- Rate limiting and brute-force defenses still apply even when bodies look identical.

## 5. Spring Boot WebFlux Error Handling and Options for Hiding Details

Spring Boot includes a WebFlux error handler. In Boot 3.5 releases, `server.error.*` properties govern how much detail enters responses; key defaults **omit exception messages and stack traces**.

### 5.1. A Production Baseline for Spring Boot 3.5

~~~yaml
server:
  error:
    include-message: never
    include-stacktrace: never
    include-exception: false
    include-binding-errors: never
    include-path: never
~~~

**Explanation:**

- `include-message: never` avoids returning raw exception messages.
- `include-stacktrace: never` prevents stack trace exposure.
- `include-exception: false` omits the exception class name from responses.
- `include-binding-errors: never` hides detailed binding error objects that may contain sensitive values.
- `include-path: never` reduces leaking raw request paths in error payloads, especially paths carrying IDs or tokens.
- These settings **do not route an upstream 500 response through Boot's error handler**. A backend returning JSON with a stack trace can still be proxied verbatim by Gateway.
- Setting `never`/`false` does not automatically harden custom `@ExceptionHandler`s, Gateway response filters, or ingress error pages.

Spring Boot 3.5 property documentation confirms these defaults: `include-message=never`, `include-stacktrace=never`, `include-exception=false`, `include-binding-errors=never`; `include-path` may default to `always`, so environments hiding paths should explicitly set `never`.

### 5.2. Avoid `always` and `on-param`

Some dev configurations set:

~~~yaml
# COUNTEREXAMPLE: do not deploy to production.
server:
  error:
    include-stacktrace: always
    include-message: always
~~~

Likewise, `on-param` lets request query parameters toggle error detail verbosity, leaking internals to untrusted clients if no other layer blocks it. Confine verbose debug output to isolated dev environments, never query-toggled flags on public APIs.

### 5.3. Spring Boot 4.x and Property Migration

Boot 4.x alters auto-configuration structures and certain property namespaces; verify against the **versioned common application properties** for your exact release. Examples in this lesson use Boot 3.5 for concrete illustration without claiming every property name or behavior stays unchanged in Boot 4.x.

## 6. RFC 9457 and the Scope of WebFlux Support

Spring WebFlux provides `ProblemDetail` and `application/problem+json` support. Spring Boot exposes `spring.webflux.problemdetails.enabled` as documented in corresponding releases:

~~~yaml
spring:
  webflux:
    problemdetails:
      enabled: true
~~~

**Key points:**

1. Enabling this property **does not convert every upstream 4xx/5xx into Problem Details**.
2. `ProblemDetail` primarily handles errors processed by **WebFlux application/controller layers**.
3. Errors in Netty routing, load balancing, Gateway filters, or Spring Security entry points can take **different pipelines**.
4. Standardizing all response statuses and bodies requires identifying the **error source** and intervening appropriately at each tier.
5. `instance` often reflects the request path; sanitize or omit it if paths carry sensitive data.
6. If upstream already returns valid `application/problem+json`, avoid rewriting the entire body unnecessarily to preserve semantics and save overhead.

### 6.1. Error Handler for an Internal Controller

Suppose a local controller inside the **Gateway WebFlux application** needs to return a 400 without exposing internal exception messages:

~~~java
package example.gateway.security;

public class InvalidOrderInputException extends RuntimeException {
    public InvalidOrderInputException(String internalDetail) {
        super(internalDetail);
    }
}
~~~

~~~java
package example.gateway.security;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class LocalControllerProblemAdvice {

    @ExceptionHandler(InvalidOrderInputException.class)
    public ProblemDetail invalidOrderInput(InvalidOrderInputException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "The supplied order input is invalid.");

        problem.setTitle("Invalid request");
        problem.setType(java.net.URI.create(
                "https://api.example.test/problems/invalid-request"));
        problem.setProperty("code", "INVALID_ORDER_INPUT");
        return problem;
    }
}
~~~

Here, `internalDetail` stays server-side for redacted logging and triage and is **never copied to the client**. `@RestControllerAdvice` covers only annotated controller exceptions; **it does not automatically intercept upstream HTTP 503s or every error inside Gateway routing filters**.

### 6.2. `ErrorWebExceptionHandler` for Non-Controller Errors

WebFlux exposes extension points such as:

- `ErrorAttributes` to shape error payload data.
- `ErrorWebExceptionHandler` / `AbstractErrorWebExceptionHandler` to customize serialization and status mapping.
- `WebExceptionHandler` for ordered contract-based exception handling.
- Spring Security `ServerAuthenticationEntryPoint` and `ServerAccessDeniedHandler` for 401/403 responses.

When building custom handlers, pay close attention to:

- Ordering relative to Boot's default handler and Spring Security filters.
- Whether the response is already committed.
- Content negotiation (JSON/HTML).
- `Mono<Void>` semantics and avoiding blocking I/O inside reactive handlers.
- Preserving 400/404/429 vs. 500 distinctions.
- Not overwriting successful upstream payloads or already-streaming bodies.
- Not logging JWTs, cookies, or SQL queries even when the handler receives the raw exception.

**Never embed exception class names in public responses merely for debugging convenience.** Return standardized error codes and policy-governed correlation IDs instead, keeping technical details in internal logs.

## 7. Gateway Route Filters vs. `WebFilter` vs. Spring Security Scopes

### 7.1. Three Distinct Hook Scopes

| Hook | Where It Executes | Things to Watch |
| --- | --- | --- |
| `GatewayFilter` / `GlobalFilter` | Gateway filter chain **after route matching** | Does not run for unmatched 404s or requests rejected earlier by Security |
| `WebFilter` | WebFlux HTTP request pipeline | Can cover non-Gateway routes depending on ordering and filter chain |
| Spring Security `SecurityWebFilterChain` | AuthN/AuthZ, CSRF, and HTTP headers | 401/403 responses may be emitted before any Gateway route executes |

Consequently, placing filters only under Gateway `default-filters` **does not guarantee** headers appear on responses generated earlier by Spring Security or WebFlux.

For example:

~~~text
GET /api/orders/42 + valid token
  -> route matched -> SecureHeaders / RemoveResponseHeader can run

GET /api/orders/42 + invalid token
  -> Security returns 401 before routing -> Gateway route filters may never run

GET /no-such-route
  -> WebFlux 404 -> no Gateway route filters run
~~~

If you require HSTS, `X-Content-Type-Options`, and caching policies across **all public responses**, enforce them at the **edge proxy, Spring Security, or a well-placed `WebFilter`** and verify every error path instead of assuming one route filter covers everything.

### 7.2. Spring Security Headers Do Not Replace Upstream Policies

Spring Security header writers protect responses produced or handled through the security chain, yet they do not scrub sensitive error bodies returned by upstreams, nor do they replace backend authorization or fix internal redirect `Location` URLs.

## 8. Security Headers: Each Serves a Specific Purpose

| Header | Purpose | Deployment Notes |
| --- | --- | --- |
| `Strict-Transport-Security` | Instructs browsers to prefer HTTPS for the origin | Meaningful only on public HTTPS; handle `includeSubDomains`/`preload` carefully |
| `X-Content-Type-Options: nosniff` | Prevents MIME type sniffing | Always pair with accurate `Content-Type` headers |
| `Content-Security-Policy` | Restricts script/style/frame sources and capabilities | Depends on HTML/UI design; no single CSP fits every app |
| `X-Frame-Options: DENY` | Blocks framing/clickjacking in supporting UAs | CSP `frame-ancestors` offers finer control |
| `Referrer-Policy` | Controls URL data sent in `Referer` | `no-referrer` is strict; `strict-origin-when-cross-origin` is a common alternative |
| `Cache-Control: no-store` | Prevents storing sensitive responses in caches | Avoid applying blindly to public cacheable assets |
| `Pragma`, `Expires` | Legacy cache compatibility | Does not replace primary `Cache-Control` directives |
| `Permissions-Policy` | Restricts browser APIs (camera, geolocation, etc.) | Browser support and directive syntax evolve over time |
| `Cross-Origin-Opener-Policy` | Isolates browsing contexts where needed | Can break OAuth popups/flows if misconfigured |
| `Cross-Origin-Resource-Policy` | Controls cross-origin resource embedding | Can block asset delivery unexpectedly |
| `X-Download-Options` | Legacy behavior in certain older browsers | Does not replace MIME or `Content-Disposition` controls |
| `X-Permitted-Cross-Domain-Policies` | Legacy Adobe cross-domain policy | Only relevant for legacy Flash/Acrobat clients |
| `X-XSS-Protection` | Legacy browser XSS auditor header | Does not replace CSP; `1; mode=block` is no longer universally recommended |
| `Access-Control-Allow-Origin` | Browser CORS control | **Not authentication**; never combine wildcard with credentials |

### 8.1. HSTS Must Be Governed at the HTTPS Edge

~~~http
Strict-Transport-Security: max-age=31536000
~~~

Browsers honor HSTS only when delivered over **trusted HTTPS**. If TLS terminates at a CDN or ingress and Gateway receives plain HTTP internally, Spring Security may omit HSTS unless trusted forwarded-scheme handling is properly configured; inspect where public TLS terminates and how forwarded headers are processed.

**Do not enable right away:**

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
~~~

on a domain until every subdomain supports HTTPS reliably long-term. `includeSubDomains` and `preload` have broad, hard-to-reverse blast radii and require domain-owner approval, staged rollout, and compliance with preload list criteria.

### 8.2. CSP Must Match the Frontend

A JSON-only API can still set a restrictive CSP if it might ever render HTML/docs, yet **browsers enforce CSP primarily on loaded documents**, not as a firewall for pure JSON endpoints.

Example strict policy for internal pages needing no external scripts:

~~~http
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'
~~~

For SPAs or CDNs, policies must allow required script hashes, nonces, or hosts. Never copy a blanket CSP onto routes serving Swagger UI or OAuth callbacks and assume you hardened the app—it can easily break functionality.

Use `Content-Security-Policy-Report-Only` during evaluation where appropriate before switching to enforcement once violations are resolved. CSP violation reports can also leak sensitive URLs, so sanitize report data and rate-limit the reporting endpoint.

### 8.3. `X-XSS-Protection` Is Not a Modern Defense

Older Gateway `SecureHeaders` defaults include this legacy value:

~~~http
X-XSS-Protection: 1; mode=block
~~~

Modern browsers have retired legacy XSS auditors, and modern Spring Security defaults to `X-XSS-Protection: 0`. Avoid having two tiers emit conflicting values. Rely on proper output encoding, input validation, strict CSPs, and data protection rather than legacy headers.

### 8.4. Never Let Sensitive Responses Be Cached

An API serving account profiles or login errors should consider:

~~~http
Cache-Control: no-store
Pragma: no-cache
~~~

Meanwhile, routes serving public static assets may intentionally leverage caching. Separate cache policies by route, resource type, auth state, and data sensitivity. Remember that `no-cache` enforces revalidation and **does not mean `no-store`**. With `Vary: Authorization`/`Cookie` and shared caches, understand HTTP caching semantics rather than relying on one blanket policy.

## 9. Gateway `SecureHeaders` Filter and Its Limitations

Spring Cloud Gateway Server WebFlux includes the `SecureHeaders` `GatewayFilter` factory. It emits a group of security response headers and lets you customize or disable specific headers depending on release version.

### 9.1. WebFlux 5.x Route Example

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-api
              uri: http://localhost:8081
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
                - SecureHeaders
~~~

This is a **route-specific filter**. In legacy Gateway 4.x namespaces, routes generally sit under `spring.cloud.gateway.routes`. While `SecureHeaders` exists across branches, exact default headers and customization properties must be checked per version.

### 9.2. Defaults Do Not Automatically Fit Every Environment

According to Gateway 5.x documentation, default headers can include:

- `X-XSS-Protection`
- `Strict-Transport-Security`
- `X-Frame-Options`
- `X-Content-Type-Options`
- `Referrer-Policy`
- `Content-Security-Policy`
- `X-Download-Options`
- `X-Permitted-Cross-Domain-Policies`

**Do not treat that list as an endorsement to turn every default on unchanged in production.** For example, a default CSP like `script-src https:` may be far too permissive for an SPA requiring strict policies, and `X-XSS-Protection` can conflict with another header writer. Gateway 5.x also optionally supports `Permissions-Policy`.

### 9.3. Per-Route Customization and Property Namespaces

Example disabling legacy `X-XSS-Protection` on a specific route:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: json-api
              uri: http://localhost:8081
              predicates:
                - Path=/api/json/**
              filters:
                - name: SecureHeaders
                  args:
                    disable: x-xss-protection
~~~

Verify parameter names such as `disable` and lowercase header keys against your running Gateway version's API; some releases also expose `enabled-headers`/`disabled-headers` and `default-headers` via `configprops`. **Never verify header removal solely by reading YAML**—confirm it directly on live HTTP responses.

### 9.4. Why `SecureHeaders` Alone Is Insufficient

Because it runs as a **`GatewayFilter` on matched routes**, it does not apply to 401s emitted earlier by Security or 404s matching no route. Nor does it scrub stack traces from upstream error bodies or coordinate with ingress/CDN layers that might re-inject duplicate headers.

**Solution:** assign a clear owner per security header (edge, Spring Security, or Gateway filter), prevent overlap, and test successes, upstream errors, unmatched routes, and auth denials.

## 10. Spring Security WebFlux and Response Headers Across Error Types

Spring Security WebFlux attaches default HTTP response header writers configured via `SecurityWebFilterChain`. Per modern Spring Security documentation, defaults typically include cache-control headers, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and `X-XSS-Protection: 0`, plus HSTS when running in an HTTPS context. **CSP is not enabled with a single universal default** because HTML/script needs vary widely across apps.

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 0
~~~

Exact emitted headers depend on Spring Security version, pre-existing response headers, filter ordering, and TLS termination. Never assume every single header above automatically appears on every 401/403 if custom filters or ingress proxies override them.

### 10.1. Example `SecurityWebFilterChain` for a Gateway JWT Resource Server

This example assumes the project includes the Spring Security OAuth2 Resource Server dependency and valid issuer/JWK configuration:

~~~java
package example.gateway.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class GatewaySecurityConfiguration {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/actuator/health").permitAll()
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth -> oauth
                        .jwt(Customizer.withDefaults()))
                .headers(headers -> headers
                        .contentSecurityPolicy(policy -> policy
                                .policyDirectives(
                                    "default-src 'none'; " +
                                    "frame-ancestors 'none'")))
                .build();
    }
}
~~~

Notes:

1. Permitting `/actuator/health` does not mean exposing other Actuator endpoints; keep admin endpoints protected by network and auth policies.
2. `oauth2ResourceServer(jwt)` validates bearer JWTs, while fine-grained scope and resource-ownership authorization must still be defined explicitly.
3. A `default-src 'none'` CSP may work for a pure JSON API, yet **will break** a Gateway hosting Swagger UI or an SPA that needs scripts and styles. Tailor CSP to the public UI contract.
4. Never call `headers.disable()` blindly to fix "duplicate headers"—it strips valuable built-in protections too.
5. If browser cookies or sessions are involved, evaluate CSRF protection via threat modeling rather than disabling CSRF everywhere simply because Gateway supports JWTs.
6. Test response headers across **401/403, no-route 404, upstream 503, and 200 OK**, since they traverse different execution pipelines.

### 10.2. Assign One Owner per Header

~~~http
Strict-Transport-Security: max-age=31536000
Strict-Transport-Security: max-age=631138519
~~~

When CDN, ingress, Spring Security, and Gateway `SecureHeaders` all emit HSTS, CSP, or CORS headers, clients receive conflicting values. Multiple CSP headers intersect restrictively and can break frontend loading; overly broad HSTS directives like `includeSubDomains`/`preload` affect the entire organization's domain tree.

| Header | Suitable Owner by Topology | Rationale |
| --- | --- | --- |
| HSTS | Public TLS edge or HTTPS-aware app | Meaningful only on public HTTPS origins |
| CSP for HTML | Application/UI owner with security review | Requires full knowledge of scripts, assets, and framing |
| `X-Content-Type-Options` | Spring Security or agreed edge layer | Uniform baseline policy |
| Frame protection | UI owner or Spring Security | Depends on embedding rules |
| `Cache-Control` for private APIs | Backend or per-route Gateway filter | Depends on payload sensitivity |
| CORS | One primary owner; backend aligns to contract | Prevents duplicate `ACAO` values |
| Server/version banners | Ingress/CDN and server-level config | May be injected after Gateway filters run |
| Backend debug headers | Backend + Gateway route/default filters | Keep from crossing the public boundary |

**Final public responses** passing through CDN and ingress are what clients see; testing only an internal Gateway pod inside a cluster is insufficient.

## 11. `RemoveResponseHeader`, `SetResponseHeader`, and `WebFilter`

Gateway Server WebFlux supports:

- `RemoveResponseHeader`: deletes a named response header.
- `SetResponseHeader`: overwrites values of a named header.
- `AddResponseHeader`: appends a header value (potentially creating multiples).
- `DedupeResponseHeader`: removes duplicate header values using a chosen strategy.
- `RewriteLocationResponseHeader`: rewrites parts of `Location` headers, though it does not resolve every public scheme/prefix case automatically.

### 11.1. Gateway Server WebFlux 5.x: `default-filters` Only Apply to Matched Routes

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          default-filters:
            - RemoveResponseHeader=X-Powered-By
            - RemoveResponseHeader=X-Backend-Host
            - RemoveResponseHeader=X-Internal-Error
          routes:
            - id: private-orders-api
              uri: http://localhost:8081
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
                - SetResponseHeader=Cache-Control, no-store
~~~

Key takeaways:

1. Gateway 5.x uses `spring.cloud.gateway.server.webflux.default-filters`, whereas legacy 4.x namespaces use `spring.cloud.gateway.default-filters`.
2. `default-filters` execute only on **matched routes**, not on unmatched 404s or 401s stopped by Spring Security before routing.
3. `RemoveResponseHeader=X-Powered-By` does not inspect or sanitize JSON/HTML bodies returned by backends.
4. `SetResponseHeader=Cache-Control, no-store` suits private routes, while public assets require distinct cache directives.
5. `Server` headers can be added by Netty, Nginx, or CDN **after** `GatewayFilter` completes; a route filter cannot guarantee removing them at the edge.
6. Avoid stripping `WWW-Authenticate` on 401s or `Retry-After` on 429/503s when part of the API contract.
7. Never strip `Set-Cookie` indiscriminately: login sessions, OAuth state, and refresh-token flows rely on properly configured cookies.

### 11.2. When Header Scrubbing Needs Wider Scope Than Routes

Example `WebFilter` registering a `beforeCommit` hook:

~~~java
package example.gateway.security;

import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(-200)
public class ResponseMetadataBoundaryFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        exchange.getResponse().beforeCommit(() -> {
            HttpHeaders headers = exchange.getResponse().getHeaders();
            headers.remove("X-Powered-By");
            headers.remove("X-Backend-Host");
            headers.remove("X-Internal-Error");
            return Mono.empty();
        });

        return chain.filter(exchange);
    }
}
~~~

This is a **`WebFilter`** example, not a Gateway `GlobalFilter`. Using `beforeCommit` modifies headers while the response remains mutable, though it cannot alter already-committed responses or headers added downstream/externally by an upstream proxy or CDN.

A `WebFilter` covers non-route requests as well, yet still requires integration tests covering error handlers and security filter ordering. `@Order(-200)` is merely illustrative, not mandatory across every codebase. **If Spring Security and the public edge already enforce the policy cleanly, prefer built-in configuration over adding redundant custom filters.**

### 11.3. Removing a Header Does Not Scrub the Response Body

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/json
X-Backend-Host: orders.svc.cluster.local

{
  "message": "jdbc:postgresql://db-internal:5432/orders",
  "exception": "org.postgresql.util.PSQLException"
}
~~~

Removing `X-Backend-Host` leaves the JSON payload intact. When backend bodies expose SQL/JDBC URLs, server paths, or stack traces, fix backend error serialization or implement **schema-aware** response rewriting—never global regex word stripping. Any body rewrite must safely handle JSON/HTML/gzip compression, `Content-Length`, streaming, `HEAD`/204/304 responses, and memory bounds.

## 12. Upstream HTTP Errors Need Dedicated Policy

### 12.1. An Upstream 500 Is an HTTP Response, Not Automatically a Gateway Exception

A backend might return:

~~~json
{
  "exception": "org.postgresql.util.PSQLException",
  "message": "Authentication failed for database admin",
  "node": "orders-7cd9.internal"
}
~~~

Gateway received a valid HTTP response—merely with status 500. **Setting `server.error.include-stacktrace=never` on Gateway does not sanitize this body**, because Gateway's Boot error handler is not necessarily invoked.

Three approaches:

| Approach | Strength | What to Verify |
| --- | --- | --- |
| Backend normalizes errors | Closest to domain exceptions; preserves accurate statuses | Every service honors the error contract |
| Selective Gateway body rewrite | Protects legacy APIs that cannot be changed immediately | Memory bounds, encoding, retries, 204/HEAD, performance |
| Ingress / service mesh generic error | Intercepts certain infrastructure failures | Lacks awareness of application/JSON business errors |

**Prefer fixing error contracts in the backend services**, using Gateway sanitization as a boundary guardrail for legacy workloads.

### 12.2. Do Not Flatten Every Exception into 503

~~~text
Upstream 400/422:
  Preserve validation error statuses per contract
  Never expose raw DTOs containing passwords or secrets

Upstream 401/403:
  Never leak internal role/scope mappings
  Preserve authentication semantics

Upstream 500/503:
  Sanitize details while keeping accurate failure status

Gateway DNS/connect/timeout:
  Map to 502/503/504 intentionally by failure source
  Never assume every exception defaults to one fixed status
~~~

Once a response partially commits mid-stream, converting it cleanly to Problem Details may no longer be feasible; connection resets and streaming faults need dedicated handling.

## 13. CORS, Caching, and Protocol Headers

### 13.1. `DedupeResponseHeader` Does Not Substitute for a CORS Policy

Suppose two tiers both append CORS headers:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Gateway offers `DedupeResponseHeader`:

~~~yaml
filters:
  - DedupeResponseHeader=Access-Control-Allow-Credentials Access-Control-Allow-Origin
~~~

Available strategies include `RETAIN_FIRST`, `RETAIN_LAST`, and `RETAIN_UNIQUE`. **Deduplicating headers does not guarantee the retained value is safe**: keeping `*` alongside credentials makes browsers reject requests or accidentally widens trust boundaries.

Process:

1. Assign one primary CORS owner.
2. Explicitly allowlist required origins, methods, and headers.
3. Never emit `Access-Control-Allow-Origin: *` for credentialed requests.
4. Emit `Vary: Origin` when shared caches might serve different origins.
5. Test preflight `OPTIONS` alongside both success and error responses.
6. Never treat CORS as authentication; `curl` and non-browser clients ignore CORS entirely.

### 13.2. `Cache-Control` for Sensitive Resources

An authenticated user response:

~~~http
Cache-Control: private, no-store
Vary: Authorization
~~~

differs sharply from a public static asset:

~~~http
Cache-Control: public, max-age=300
~~~

Never return `Cache-Control: public` for user-specific data or auth failures unless safe cache keys and auth partitioning are guaranteed. Recall that `no-cache` merely forces revalidation; **`no-store`** forbids persistence. When CDNs sit in front, inspect CDN caching rules directly rather than trusting Gateway headers alone.

### 13.3. Headers You Should Not Strip Blindly

- `WWW-Authenticate`: 401 challenge metadata required by many OAuth2/Bearer clients.
- `Authorization`: request credential header governed by token relay/auth policies; never reflect it into responses or logs.
- `Set-Cookie`: session/credential cookies requiring proper `Secure`, `HttpOnly`, `SameSite`, `Path`, and `Domain` attributes.
- `Retry-After`: used on 429/503 responses under documented backoff rules.
- `Location`: HTTP redirect target; must use safe public hostnames and prefixes.
- `Vary` and `ETag`: essential to caching and content-negotiation contracts.
- `traceparent`: trace context propagation, never a credential or rate-limit key.

## 14. Response URLs Are Another Source of Leaks Beyond Bodies and Debug Headers

### 14.1. Internal `Location` Headers

Backend emits:

~~~http
HTTP/1.1 302 Found
Location: http://orders.internal:8081/orders/42
~~~

Clients should only see:

~~~http
Location: https://api.example.test/platform/api/orders/42
~~~

A route that strips `X-Powered-By` yet returns an absolute `Location` pointing to `orders.internal` **is not fully hardened**.

`RewriteLocationResponseHeader` can rewrite portions of URLs, but it does not automatically reconstruct every `https` scheme, host, port, and public path prefix across arbitrary topologies.

### 14.2. Three Path Layers Need Explicit Contracts

~~~text
Client:     /platform/api/orders/42
Ingress:    /api/orders/42       (strip /platform)
Gateway:    /orders/42           (StripPrefix=1)
Client redirect Location:
            https://api.example.test/platform/api/orders/42
~~~

If both Gateway and ingress append prefixes carelessly, callers can see `/platform/platform/api/...`. Conversely, if a backend returns a relative `/orders/42`, browsers will not automatically prepend `/platform/api`.

### 14.3. Untrusted Forwarded Headers Enable Host Poisoning

~~~http
Forwarded: for=10.0.0.1;proto=http;host=evil.example
X-Forwarded-Host: evil.example
X-Forwarded-Prefix: /admin
~~~

Clients can inject these headers arbitrarily. Trust forwarded metadata only from authenticated proxies after ingress sanitization at the trust boundary, and block direct Gateway bypass via network ACLs. Never build OAuth2 `redirect_uri` or password-reset links from untrusted client `X-Forwarded-Host` values.

### 14.4. Other Leaked URL Locations

- `Link`, `Content-Location`, and `Refresh` headers.
- OAuth2/OIDC `redirect_uri` and logout callbacks.
- OpenAPI/Swagger `servers` arrays.
- Password-reset or invitation email links.
- JSON `downloadUrl` and pagination links.
- Cookie `Domain` and `Path` attributes.
- CORS `Access-Control-Allow-Origin` when echoing unvalidated `Origin` headers.

Inspect **both headers and payloads** from the public entrypoint, not status codes alone.

## 15. Keeping Actuator Governance Off the Public Data Plane

### 15.1. Endpoints Requiring Tight Control

Spring Boot Actuator can expose:

| Endpoint | Risk if Publicly Exposed |
| --- | --- |
| `health`, `info` | Metadata, service status, and discovery details |
| `metrics`, `prometheus` | Traffic patterns, route names, and runtime cardinalities |
| `env`, `configprops` | Runtime properties that may include sensitive settings |
| `beans`, `conditions`, `mappings` | Internal application wiring |
| `loggers` | Adjusting log levels or probing runtime state depending on permissions |
| `heapdump`, `threaddump` | Memory snapshots potentially holding tokens, strings, and stack topology |
| `gateway` | Reading routes, refreshing routes, or creating/deleting routes depending on access level |
| `logfile` | Access/app logs that may contain PII or secrets |

### 15.2. Management Exposure Baseline for Boot 3.5

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
    gateway:
      access: none
~~~

This limits HTTP management exposure to `health,info`. **It does not by itself isolate network ports, configure `SecurityWebFilterChain`, or replace firewalls.**

If route inspection is required on a **private management network**:

~~~yaml
management:
  endpoint:
    gateway:
      access: read-only
  endpoints:
    web:
      exposure:
        include: health,info,gateway
~~~

Gateway 5.x documentation recommends `management.endpoint.gateway.access=read-only` if enabling the Actuator gateway endpoint. `unrestricted` access permits refreshing, creating, and deleting routes—highly sensitive operations requiring strict network and auth controls. In certain releases, `management.endpoint.gateway.enabled=true` may also affect write capabilities depending on version; verify exact behavior rather than copying config blindly.

### 15.3. Health Checks Should Not Expose Infrastructure

Setting `show-details: never` suppresses granular details on public health endpoints. Orchestration liveness/readiness checks can use dedicated internal endpoints without publishing JDBC/Redis/Eureka hostnames or raw exceptions to the Internet.

### 15.4. Security Testing Actuator Paths

Probe typical paths:

~~~text
/actuator
/actuator/env
/actuator/configprops
/actuator/gateway
/actuator/heapdump
/actuator/loggers
/swagger-ui
/v3/api-docs
/error
~~~

This is a **checklist of endpoints to test per deployment**, not an assumption that all exist. A public 404 returned by ingress does not guarantee the direct management port is closed; test for network bypass separately.

## 16. Server Fingerprints, TLS Errors, and the True Reach of HTTP Filters

~~~text
Backend -> Gateway/Reactor Netty -> Nginx/Ingress -> CDN -> Browser
~~~

`Server`, `Via`, `X-Powered-By`, `X-Envoy-Upstream-Service-Time`, and vendor headers can originate at any hop. Stripping `Server` inside a Gateway route filter does not stop Nginx or a CDN from re-adding it downstream. Verify public responses across **all sources**:

- 200/3xx responses from backends.
- 404/5xx generated by Gateway.
- 401/403 generated by Spring Security.
- 413/502/503/504 generated by ingress/CDN.
- TLS/HTTP2 handshake errors occurring before HTTP routing begins.

If a TLS handshake fails before HTTP framing, **there is no HTTP response** for a `WebFilter` to serialize Problem Details or attach headers. Test TLS and certificates directly.

Hiding server banners reduces fingerprinting noise, **never substituting for CVE patching, Spring/Netty updates, and minimizing public attack surfaces**. If rewriting JSON error payloads, handle gzip encoding, `Content-Length`, 204/HEAD/304 status rules, streaming, committed responses, and backpressure cleanly—never string-replace over raw byte chunks with naive regexes.

## 17. Logging, Tracing, and Error Diagnostics Without Creating New Leaks

### 17.1. Client Responses and Internal Diagnostics Must Differ

| Information | Return to Client? | Log Internally? |
| --- | --- | --- |
| HTTP status, public error code | Yes | Yes |
| Safe detail message | Yes | Yes |
| Validated correlation ID | Optional | Yes |
| Route ID, retry count, upstream failure category | Generally no | Yes, when useful |
| Internal hostname/IP/Pod ID | No | With access restrictions |
| Java exception class/stack trace | No | Restricted secure logs only |
| SQL statements / JDBC URLs | No | Restricted, credentials stripped |
| JWTs, refresh tokens, cookies | No | **Never log raw**, even at DEBUG |
| User payloads containing PII | Never echo | Never dump raw |
| `traceparent`, baggage | Not credentials | Per trust and privacy policy |

Trace IDs correlate requests across Gateway and microservices, yet **never prove caller authentication**. Validate format and bounds on client-supplied `traceparent` or `X-Request-Id` headers at trust boundaries before writing them into logs or response headers.

### 17.2. A Very Dangerous Logging Counterexample

~~~java
// COUNTEREXAMPLE: risks logging Authorization, cookies, and PII payloads.
log.error("Gateway failed, headers={}, body={}",
        request.getHeaders(), rawRequestBody, exception);
~~~

A cleaner structured log design:

~~~text
timestamp=2026-11-24T05:00:00Z
service=edge-gateway
routeId=orders-api
httpMethod=POST
outcome=ERROR
status=503
errorCategory=UPSTREAM_CONNECT
durationMs=155
correlationId=req-demo-42
~~~

This is an **illustrative log schema**, not automatic Gateway output. When stack traces are needed for troubleshooting, route them exclusively to access-controlled operator logs with token/PII redaction and bounded retention. Never copy raw exception messages into public `detail` fields.

### 17.3. Wiretap and Distributed Tracing

Enabling Reactor Netty wiretap can log raw HTTP headers and bodies depending on log levels, leaking secrets. Restrict it to sandboxes or synthetic traffic for short troubleshooting windows under strict data-handling rules.

Micrometer Tracing/OpenTelemetry identifies failing hops and latency spikes, yet never hides `Server` headers, fixes `Location` redirects, or sanitizes error bodies on its own. Traces can also capture raw URLs, query parameters, hostnames, and baggage; enforce attribute schemas and redaction.

### 17.4. Never Put Arbitrary Inputs in Metric Labels

Avoid attaching raw `traceId`, JWT `sub`, email addresses, request bodies, or `/api/orders/{actual-id}` paths as Prometheus/metric labels. Use bounded, low-cardinality dimensions such as static route IDs, statuses, outcomes, and error categories to prevent cardinality explosions.

## 18. HTTP Testing Across Both Boundaries: Client and Mock Upstream

### 18.1. Integration Test Topology

~~~mermaid
flowchart LR
    T["WebTestClient/curl"] --> G["Gateway WebFlux<br/>RANDOM_PORT"]
    G --> U["MockWebServer/WireMock"]
    U --> R["RecordedRequest: method/path/headers"]
    G --> C["Public response: status/headers/body"]
~~~

Do not test a `GlobalFilter` only against a mocked `ServerWebExchange` and conclude the public Gateway is safe. Test **real outbound HTTP calls** to a mock backend alongside **real responses received by the client**.

### 18.2. Example Status + Header + Body Assertions

Assume the test boots Gateway with route `/api/orders/**`, a mock backend returning `503` with a **safe** Problem Details payload, and filters removing `X-Powered-By`/`X-Backend-Host`:

~~~java
// Illustrative assertion snippet, not a standalone test class.
client.get()
        .uri("/api/orders/42")
        .header("Authorization", "Bearer demo-test-token")
        .exchange()
        .expectStatus().isEqualTo(503)
        .expectHeader().doesNotExist("X-Powered-By")
        .expectHeader().doesNotExist("X-Backend-Host")
        .expectHeader().valueEquals(
                "X-Content-Type-Options", "nosniff")
        .expectBody()
        .jsonPath("$.code").isEqualTo("UPSTREAM_UNAVAILABLE")
        .jsonPath("$.trace").doesNotExist()
        .jsonPath("$.exception").doesNotExist();
~~~

Prerequisites:

- `client` is a `WebTestClient` bound to Gateway's real HTTP server port, not `bindToController`.
- The bearer token comes from a test identity provider or valid test JWT fixture; `"demo-test-token"` is not inherently a valid JWT.
- Mock upstream returns `code=UPSTREAM_UNAVAILABLE` JSON, or Gateway performs intentional response rewriting (`RemoveResponseHeader` strips headers only—it never fabricates bodies).
- Verifying that two JSON fields are absent does **not** guarantee `detail` lacks embedded SQL strings or internal hostnames.
- If Spring Security rejects with 401 **before route matching**, Gateway `default-filters` may not run; never treat a passing post-auth 503 test as proof that 401 responses carry the right headers.

### 18.3. Make Mock Upstreams Produce Diverse Responses

A thorough mock upstream should simulate:

~~~text
1) Valid HTTP 200 JSON
2) Safe business error HTTP 404
3) Validation error HTTP 422
4) Safe HTTP 503 problem+json
5) Legacy HTTP 500 body containing stack trace and internal hostname
6) HTTP 302 Location=http://orders.internal:8081/...
7) HTTP 204 No Content
8) HTTP 200 with X-Backend-Host, X-Powered-By, Set-Cookie
9) Slow responses, connection resets, and truncated bodies
~~~

For case (5), a test **should fail** if Gateway only configures `RemoveResponseHeader` with no body protection—catching real gaps rather than representing a broken fixture.

### 18.4. Compare Upstream Request Counts to Pinpoint Status Origin

~~~text
No JWT:
  -> Security returns 401
  -> upstream request count increments by 0

Insufficient scope:
  -> Security returns 403
  -> upstream request count increments by 0

No matching Gateway route:
  -> WebFlux/Gateway returns 404
  -> upstream request count increments by 0

Route matched, upstream returns HTTP 404:
  -> upstream request count increments by 1
  -> client receives contract 404

Rate limiter denies:
  -> Gateway returns 429
  -> upstream request count increments by 0

Backend HTTP 503:
  -> upstream request count increments by 1
  -> client receives 503 unless Retry/fallback alters it

Circuit breaker short-circuit:
  -> upstream request count may increment by 0
  -> client status/body comes from fallback policy
~~~

Asserting only HTTP 404 or 503 proves nothing about whether a route executed. Inspect recorded upstream requests alongside redacted route/trace metadata to verify the true source.

## 19. Response Security Test Matrix

| ID | Scenario | Assertion |
| --- | --- | --- |
| E01 | Unmatched route | No-route status; zero backend calls; route table not exposed |
| E02 | Backend returns 404 | Upstream invoked; contract status and body preserved |
| E03 | Missing token | 401, zero backend calls, policy-compliant `WWW-Authenticate` |
| E04 | Insufficient token scope | 403 without exposing principal or role map |
| E05 | Malformed JSON | 400/422 without echoing raw payloads or validation secrets |
| E06 | Backend 500 raw stack trace | Client sees zero leaked details |
| E07 | Gateway connection refused | No internal IP, hostname, or exception class leaked |
| E08 | Backend timeout | Policy-defined status; never falsifies success |
| E09 | Backend 503 + Retry | Bounded attempts; safe final status |
| E10 | CircuitBreaker fallback | Never claims write operations succeeded falsely |
| E11 | Rate limiter 429 | Zero upstream calls; `Retry-After` emitted if required by contract |
| H01 | Upstream `X-Powered-By` | Absent from public response |
| H02 | Upstream `X-Backend-Host` | Absent from public response |
| H03 | Security 401/403 | Security headers emitted by the designated owner |
| H04 | No-route 404 | Protected by Security/edge/`WebFilter` headers |
| H05 | CDN-generated 502/504 | No version banners or internal upstreams leaked |
| H06 | Multi-tier CSP/HSTS | Zero conflicting values |
| H07 | CORS trusted origin | `ACAO`, credentials, and `Vary` align with policy |
| H08 | CORS untrusted origin | No cross-origin access allowed outside allowlist |
| H09 | Session cookie | `Secure`/`HttpOnly`/`SameSite`/`Domain`/`Path` valid |
| H10 | Redirect `Location` | Uses public HTTPS origin and external path prefix |
| H11 | Spoofed `Forwarded`/`Host` headers | Never produces redirects toward attacker hosts |
| H12 | 204/HEAD responses | No illegal JSON bodies appended |
| M01 | Public `/actuator/env` | Blocked |
| M02 | Public `/actuator/gateway` | Route read/write blocked per policy |
| M03 | Public `/actuator/heapdump` | Blocked |
| M04 | `/actuator/health` | Exposes zero internal dependency details |
| M05 | Public OpenAPI docs | Contains no internal service hostnames |
| P01 | Gzipped/streamed errors | Neither body nor compression corrupts |
| P02 | Multi-replica consistency | Headers and error schemas match across pods |
| P03 | Boot/Cloud/Security upgrades | Regression tests continue passing contract |

**Do not force every exception into a single fixed error code without a formal error-mapping policy.** When failures occur below HTTP (such as TLS handshakes), do not expect a Gateway JSON body.

## 20. Inspecting the Public Boundary with `curl`

### 20.1. Testing a Normal Endpoint

~~~bash
curl -isS 'https://api.example.test/api/orders/42'
~~~

Check `X-Content-Type-Options`, HSTS on public HTTPS if enabled, caching headers, CORS/`Content-Type`, and absence of backend debug banners. If the endpoint requires a JWT and receives none, 401 is expected—**do not misdiagnose it as a routing failure**.

### 20.2. Checking the Initial 3xx Response

~~~bash
curl -isS 'https://api.example.test/api/orders/42/redirect'
~~~

Omit `-L` when inspecting raw status codes and `Location` headers prior to redirects. A redirect pointing to `http://orders.internal` remains a vulnerability even if external browsers cannot resolve the internal hostname.

### 20.3. Checking Missing Tokens, Invalid Tokens, and Unmatched Routes

~~~bash
curl -isS 'https://api.example.test/api/orders/42'

curl -isS \
  -H 'Authorization: Bearer demo-invalid-token' \
  'https://api.example.test/api/orders/42'

curl -isS 'https://api.example.test/no-such-path'
~~~

Verify that response headers and bodies leak no exceptions, secrets, or implementation internals; exact statuses depend on security and routing policies. Never place **real production tokens** into shell command histories.

### 20.4. Testing Header Spoofing in Authorized Environments

~~~bash
curl -isS \
  -H 'Forwarded: proto=http;host=evil.example' \
  -H 'X-Forwarded-Host: evil.example' \
  -H 'X-Forwarded-Prefix: /internal' \
  'https://api.example.test/api/orders/42'
~~~

Confirm that no `Location` or cookie domains reflect the attacker host or prefix. Edge proxies must sanitize forwarded headers, and Gateway must not allow public bypass of the edge.

### 20.5. Checking Management Exposure

~~~bash
curl -isS 'https://api.example.test/actuator/env'

curl -isS 'https://api.example.test/actuator/gateway'
~~~

Non-public management endpoints must be unreachable externally. Keep in mind a 404 at the CDN edge does not prove the direct management port is firewalled; test network reachability separately.

### 20.6. Verifying Real Headers Through the CDN

Security scanners observe the public edge response; compare end-to-end across:

~~~text
Backend -> Gateway -> Ingress -> CDN -> Client
~~~

- Successful responses traversing all hops.
- Security denials and unmatched-route errors.
- Proxy-generated 413/502/504 timeouts or errors at ingress/CDN.
- Duplicate HSTS, `Server`, CSP, or CORS headers.
- `Location`, `Set-Cookie`, and caching behavior.

Never treat responses measured directly from a Gateway pod as final proof if downstream ingress or CDN layers add or mutate headers later.

## 21. Troubleshooting Common Mistakes

| Symptom | Likely Cause | Fix |
| --- | --- | --- |
| Client sees `java.net.ConnectException` | Error handler exposes message/stack trace | Enforce `server.error.*` and safe error serialization |
| Client sees JDBC URL inside 500 | Upstream JSON proxied verbatim | Fix backend error output or add schema-aware Gateway rewrite |
| `X-Powered-By` still appears | Injected at ingress/CDN or route filter skipped | Inspect public edge and 401/unmatched-route paths |
| 401 lacks `SecureHeaders` | Security rejected request pre-route | Move header ownership to Spring Security / edge |
| Browser blocks Swagger UI | Strict CSP (`default-src 'none'`) breaks UI | Tailor CSP directives to required UI assets |
| HSTS header missing | TLS terminates upstream; Gateway sees HTTP | Enforce HSTS at public HTTPS owner or trusted forwarded scheme |
| HSTS breaks subdomains | Premature `includeSubDomains`/`preload` | Scope carefully and follow staged rollout |
| CORS fails from duplicate `ACAO` headers | Both Gateway and backend emit headers | Pick one owner; dedupe only after policy validation |
| Browser ignores stored cookies | Invalid `Secure`/`Domain`/`Path`/`SameSite` | Verify browser-facing URLs and cookie attributes |
| 302 redirects point to internal hosts | Backend builds internal `Location` | Configure canonical public base URL or safe rewrite |
| 429 lacks `Retry-After` | Limiter omits header or global filter stripped it | Configure per API contract |
| 401 lacks `WWW-Authenticate` | Overly aggressive global header removal | Preserve standard auth challenge headers |
| 503 turned into 200 | Overbroad fallback or `SetStatus` | Fix error mapping and fallback contract |
| `/actuator/gateway` publicly accessible | Endpoint exposed without strict auth/network isolation | Restrict to private management plane / read-only |
| Prometheus cardinality spikes | Raw paths or `traceId` used as labels | Switch to bounded low-cardinality tags |
| Stack traces queried via URL param | Left `include-stacktrace: on-param` enabled | Enforce `never` in production |
| Errors appear on a single pod | Config drift or version mismatch | Use consistent canary rollouts and diff configs |
| TLS failure returns no JSON body | Connection aborted before HTTP | Test TLS certificates and protocols separately |

## 22. Safe Policy Rollout Procedure

1. **Survey:** map all public/private routes, auth flows, backend error formats, proxy hops, and Actuator exposure.
2. **Classify:** inventory unmatched routes, security rejections, upstream 4xx/5xx, connect/timeouts, and fallbacks.
3. **Design contracts:** define statuses, stable error codes, safe messages, security headers, caching/CORS/cookies, and `Location` handling.
4. **Assign owners:** clarify exact responsibilities across CDN/ingress, Spring Security, Gateway filters, and backends.
5. **Configure:** suppress messages/stack traces, strip debug headers, tune CSP/HSTS safely, and lock down management paths.
6. **Test:** combine mock upstreams with client assertions for success, errors, spoofed `Host`/`Forwarded`, 401s, and unmatched routes.
7. **Evaluate performance:** verify error body rewrites remain memory-bounded and keep full-body logging off.
8. **Canary:** roll out to one replica/subset, tracking 401/403/404/429/5xx rates alongside frontend, SSO, and cookie flows.
9. **Monitor:** track error metrics by route and origin with redacted logs and trace IDs.
10. **Rollback:** revert safely to known-good configs—never disable Spring Security headers wholesale or expose Actuator to patch over breakage.

Hardening changes that stop leaks can still break OAuth callbacks or CORS if untested, so verify real user workflows rather than relying solely on scanner checklists.

## 23. Capstone Exercise

**Scenario:** A WebFlux Gateway serves `https://api.example.test`, routing `/api/orders/**` to `order-service` with JWT auth, ingress TLS termination, and private Actuator management. A legacy backend occasionally returns HTTP 500 containing internal hostnames.

Tasks:

1. Select supported Boot, Gateway, and Security versions and document explicit dependencies.
2. Configure the `/api/orders/**` route with `StripPrefix=1`.
3. Build a mock backend emitting 200, 404, 422, 503, and a sensitive-info 500.
4. Verify unmatched 404 vs. backend 404 via mock upstream request counts.
5. Configure `server.error.include-stacktrace/message/exception/binding-errors` safely on Boot 3.5.
6. Design JSON errors conforming to Problem Details or your API error code contract.
7. Strip `X-Backend-Host` and `X-Powered-By` on matched routes using `RemoveResponseHeader`.
8. Configure appropriate Spring Security headers and verify 401/403 responses before route execution.
9. Assign clear owners for HSTS, CSP, caching, CORS, framing, and `Referrer-Policy`.
10. Normalize backend 500 responses in the backend or via schema-aware rewriting instead of naive string filtering.
11. Confirm HTTP 422 remains 422 without turning into 200 or 503.
12. Verify Gateway connection refused and timeout errors expose zero DNS names, IPs, or stack traces.
13. Verify 302 `Location` headers never leak internal hostnames while preserving HTTPS and public path prefixes.
14. Test session cookies, OAuth redirect URIs, and browser CORS flows.
15. Isolate management endpoints onto a private network and lock down the `gateway` Actuator endpoint.
16. Confirm client-forged `Host`/`Forwarded`/`X-Forwarded-Host` headers cannot alter public URLs.
17. Inspect responses generated by ingress/CDN directly, including 413, 502, and 504.
18. Execute regression tests across all Gateway replicas.
19. Verify logs, traces, and CI artifacts contain no tokens, cookies, or PII.
20. Document safe deployment and rollback runbooks.

### Completion Criteria

~~~text
[PASS] Statuses and error codes accurately reflect fault origin and business outcomes
[PASS] Responses never leak stack traces, class names, SQL, or internal hosts/IPs
[PASS] Matched route error headers are scrubbed per policy
[PASS] Security and no-route responses receive protective headers from their designated owners
[PASS] HSTS, CSP, CORS, and caching behave consistently on the public origin
[PASS] Cookies, Location redirects, and OAuth flows reveal no internal hosts/paths
[PASS] Actuator env/configprops/gateway endpoints are inaccessible publicly
[PASS] Client-spoofed Forwarded/Host headers cannot hijack redirects
[PASS] WWW-Authenticate and Retry-After are preserved per API contract
[PASS] Logs, traces, and test fixtures leak zero secrets or PII
[PASS] Behavior verified across the full HTTP chain rather than isolated unit tests alone
~~~

These are **target acceptance criteria**, not tests executed in the current workspace.

## 24. Pre-Production Checklist

- [ ] Error origins classified across Spring Security, unmatched routes, upstream HTTP, network/timeouts, and fallbacks.
- [ ] Error responses carry accurate statuses, stable error codes, and safe messages without hiding failures behind 200.
- [ ] Boot `server.error.*` configured so messages, exception classes, and stack traces never reach public APIs.
- [ ] Debug flags `always` and `on-param` disabled in production.
- [ ] Backends emit normalized errors free of raw SQL, JDBC URLs, hostnames, class names, and PII.
- [ ] Any Gateway error body rewriting tested across gzip, streaming, `Content-Length`, `HEAD`/204/304, and memory limits.
- [ ] HSTS governed by the public HTTPS owner without blindly forcing `preload` or `includeSubDomains`.
- [ ] CSP tailored to frontend/HTML requirements using `Report-Only` rollouts when needed.
- [ ] Spring Security default headers kept enabled instead of disabled wholesale due to `SecureHeaders` overlap.
- [ ] Gateway `SecureHeaders` not assumed to protect pre-route 401s or unmatched 404s.
- [ ] `X-Content-Type-Options`, framing rules, `Referrer-Policy`, and caching tested end-to-end.
- [ ] CORS has a single owner, forbids credentialed wildcards, and sets `Vary` appropriately.
- [ ] Essential protocol headers (`WWW-Authenticate`, `Retry-After`, `Vary`, `Set-Cookie`) preserved properly.
- [ ] Debug/node/version headers stripped at the right hops and verified from the public edge.
- [ ] `Location`, `Link`, and OpenAPI metadata contain zero internal hostnames or ports.
- [ ] Cookies enforce `Secure`, `HttpOnly`, `SameSite`, `Domain`, and `Path` aligned with public URLs.
- [ ] Ingress sanitizes untrusted `Forwarded`/`Host` headers and prevents direct public bypass of Gateway.
- [ ] Actuator/`gateway` management isolated on a private network (minimum read-only if enabled) or disabled.
- [ ] Logs, traces, and CI outputs never dump raw headers, payloads, tokens, cookies, or PII.
- [ ] Trace IDs validated and metric labels kept low-cardinality.
- [ ] Test matrix covers 200/201/204/3xx/400/401/403/404/413/429/500/503/504 thoroughly.
- [ ] Integration tests validate both recorded mock-upstream requests and final public client responses.
- [ ] Edge errors emitted by CDN/ingress before requests reach Gateway tested explicitly.
- [ ] Spring Boot, Spring Cloud Gateway, and Spring Security trains patched and within support.
- [ ] Canary rollout, multi-replica config drift checks, rollback, and observability plans documented.

## 25. Summary and References

**Hardening Spring Cloud Gateway responses cannot be finished with a single filter.** A secure API controls all three dimensions together:

1. **Error responses:** preserve accurate HTTP statuses, stable public error codes, and zero leaked Java stack traces, SQL, internal hostnames, or PII—including errors originating from backends.
2. **Security headers:** enforce them from the rightful owner—public TLS edge, Spring Security, `WebFilter`, or Gateway route filter—eliminating missing or duplicate headers on 401, 404, and 5xx responses.
3. **Deployment metadata:** suppress server banners, debug headers, internal `Location` redirects, misconfigured cookie attributes, exposed Actuator endpoints, and secret leaks in logs/traces.

Always test across **public clients** and **mock upstreams** within the same HTTP flow. Neither HTTP 200 smoke checks nor header-scanner green lights alone prove routing, authorization, and error contracts are safe. Maintain clear error contracts, timely security patches, network isolation, and redacted internal diagnostics to protect users while keeping incident response effective.

### Official References

- [Spring Boot — Reactive Web Applications: Error Handling and Problem Details](https://docs.spring.io/spring-boot/reference/web/reactive.html).
- [Spring Boot 3.5 — Common Application Properties, `server.error.*`](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/).
- [Spring Security — Reactive HTTP Response Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html).
- [Spring Cloud Gateway Server WebFlux — `SecureHeaders` GatewayFilter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/secureheaders-factory.html).
- [Spring Cloud Gateway Server WebFlux — `RemoveResponseHeader`](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/removeresponseheader-factory.html).
- [Spring Cloud Gateway Server WebFlux — `SetResponseHeader`](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/setresponseheader-factory.html).
- [Spring Cloud Gateway Server WebFlux — `DedupeResponseHeader`](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/deduperesponseheader-factory.html).
- [Spring Cloud Gateway Server WebFlux — `RewriteLocationResponseHeader`](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/rewritelocationresponseheader-factory.html).
- [Spring Cloud Gateway — Configuration Properties 5.x](https://docs.spring.io/spring-cloud-gateway/reference/5.0/configprops.html).
- [Spring Cloud Gateway Server WebFlux — Actuator API](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/actuator-api.html).
- [Spring Boot — Actuator Endpoints and Access Control](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).
- [Spring Framework WebFlux — Error Responses / RFC 9457](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html).
- [IETF RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html).
