# Protecting Tokens, Cookies, API Keys, and Downstream Credentials

**Chapter:** Security Hardening  
**Module:** `SPRING_CLOUD_GATEWAY` — Building an API Gateway with Spring Cloud Gateway using route predicates, filter chains, path/header transformations, service discovery; authentication, rate limiting, circuit breakers, retries, TLS, and request observability.

Spring Cloud Gateway sits between **untrusted clients** and **downstream services**. A single mistake in how `Authorization`, `Cookie`, `X-API-Key`, `Set-Cookie`, or OAuth2 tokens are propagated can turn an API Gateway from an access-control layer into a credential-leakage pipeline. For instance, a user sends a request to `/api/catalog/**` carrying an access token scoped for payments; if the route merely runs `StripPrefix` and forwards all headers verbatim to the catalog service, catalog receives a secret it neither needs nor should possess.

Protecting credentials at the Gateway is not simply **deleting every sensitive header**. A downstream Resource Server may **need** the original access token to authorize requests itself; another internal service needs its **own service credential**; meanwhile, a Backend-for-Frontend (BFF) app uses a session cookie at the Gateway yet **never** forwards that cookie to backends. The right policy depends on **identity, audience, trust boundaries, routes, and intended purpose**.

This lesson focuses on protecting four credential groups: **Bearer tokens/JWT/OAuth2 tokens**, **session cookies and `Set-Cookie`**, **client API keys**, and **downstream/service credentials**. We will design a forwarding matrix, implement a Gateway Server WebFlux setup, apply Spring Security, `RemoveRequestHeader`/`RemoveResponseHeader`, and a controlled backend-key filter; analyze Cookies/CSRF/CORS, `TokenRelay`, mTLS, secrets rotation, caches/retries, logs, and negative testing. Differences in Gateway Server Web MVC are also documented explicitly.

> **Version scope:** Primary YAML examples use **Gateway Server WebFlux** with `spring-cloud-starter-gateway-server-webflux` and `spring.cloud.gateway.server.webflux.routes` in the 5.x line. On Gateway 4.x, some starter/property prefixes differ (e.g., `spring.cloud.gateway.routes`). **Gateway Server Web MVC** uses Servlet/WebMvc.fn, `SecurityFilterChain`, and `spring.cloud.gateway.server.webmvc.routes` on matching lines; never paste WebFlux `GlobalFilter`/`SecurityWebFilterChain` directly into MVC. Security defaults, cookies, and filter APIs must be verified against your exact Spring Boot, Spring Cloud, and Spring Security BOM.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Classify access tokens, refresh tokens, ID tokens, session IDs, API keys, backend shared secrets, and mTLS client certificates by **owner, audience, and storage location**.
2. Describe the Client → Gateway → downstream **trust boundary** and explain why Gateway authentication does not replace backend authorization.
3. Author a **per-route/per-service** policy specifying which credentials are accepted, verified, exchanged, stripped, or forwarded.
4. Use `RemoveRequestHeader`, `SetRequestHeader`, `RemoveResponseHeader`, `SecureHeaders`, and `TokenRelay` intentionally rather than expecting default proxying to isolate secrets.
5. Configure Spring Security WebFlux Resource Server to validate JWT issuer, expiry, scopes, and audience as required.
6. Distinguish `TokenRelay` (OAuth2 authorized-client flow) from **raw `Authorization` forwarding** and **OAuth2 token exchange**.
7. Design `Secure`/`HttpOnly`/`SameSite`/`Path`/`Domain` cookies, session rotation, CSRF protection, and proper CORS policies.
8. Inject backend API keys via a **lifecycle-managed provider**, never from client headers and never hardcoded in public Java/YAML.
9. Secure outbound TLS/mTLS, trusted proxies, caches, `Retry`, `CircuitBreaker`/fallbacks, WebSocket handshakes, and dynamic route management.
10. Test that **credentials are never sent to the wrong backend**, never appear in logs/traces, and never leak through caches/redirects/errors, with measured downstream call counts.

## 2. Threat Model and Trust Boundaries

```mermaid
flowchart LR
    U["Browser / mobile / external client"] -->|"HTTPS<br/>cookie / Bearer / API key"| EDGE["Ingress / WAF / TLS termination"]
    EDGE -->|"Trusted network + forwarded headers policy"| GW["Spring Cloud Gateway<br/>Authn/Authz / routing / filters"]
    GW -->|"Audience-specific token<br/>or backend credential / mTLS"| CAT["Catalog service"]
    GW -->|"Different token audience<br/>or service identity"| PAY["Payment service"]
    GW -->|"No browser session cookie"| PUB["Public content backend"]
    GW <-->|"OAuth2/OIDC auth code<br/>token / JWKS"| IDP["Identity provider"]
    GW <-->|"Short-lived service secret"| VAULT["Vault / Secret Manager"]
```

**There are at least three independent boundaries:**

1. **Client → Gateway:** data sent by clients is **untrusted input**, including `X-User-Id`, `X-Tenant`, `Forwarded`, `Host`, `X-API-Key`, and `Cookie`. Gateway may treat a client as authenticated only after verifying the token/session/key per policy.
2. **Gateway → backend:** each backend has its own trust level, audience/scopes, and credential type. HTTPS/TLS protects transit, yet does not decide whether that backend **is authorized to receive that credential**.
3. **Gateway → identity and secret management:** OAuth2 client tokens, refresh tokens, API keys, certificates, and signing materials need dedicated storage, rotation, and auditing. Never let route YAML expose them accidentally.

### 2.1. Assets to Protect

| Asset | Example | Risk if exposed |
|---|---|---|
| User access token | `Authorization: Bearer eyJ...` | Replay against Resource Servers sharing that audience; data access |
| Refresh token | OAuth2 offline/refresh credential | Minting fresh access tokens throughout its allowed lifetime |
| ID token | OIDC identity token for the client | Leaks claims/user info; misuse if accepted as an API bearer |
| Session cookie | `__Host-GWSESSION=...` | Session hijacking/fixation |
| CSRF token | Session-bound form/header token | CSRF bypass if exposed in the same context |
| Client API key | `X-API-Key: ...` | Quota consumption, impersonating a consumer/integration |
| Backend API key | `X-Backend-Api-Key: ...` | Machine-to-machine backend access |
| OAuth2 client secret | Client credentials with IdP | Obtaining access tokens as the Gateway identity |
| mTLS private key | Service client certificate key | Impersonating Gateway when connecting to services |
| Credentials in URIs | `?token=...`, `user:pass@host` | Leaked via logs, history, proxies, and redirects |

### 2.2. Ten Scenarios to Prevent

1. Client sends `X-Internal-Admin: true` and the backend treats it as verified privilege.
2. Gateway forwards a token meant for **payment-api** to the catalog service because the request uses the same `Authorization` header.
3. Gateway forwards its **own session cookie** to every backend via proxy header passthrough.
4. Backend returns `Set-Cookie` with an overly broad `Domain`, exposing sensitive cookies across subdomains.
5. A partner's API key is recorded in access logs, route configs, metric labels, or tracing baggage.
6. A `Location` redirect containing a token/credential sends the browser to an unapproved origin.
7. Gateway accepts an Internet-sent `X-Forwarded-Proto: https` header and assumes the request is secure/internally trusted.
8. A local response cache or shared CDN serves one user's data to another due to missing credential/session partitioning.
9. A CircuitBreaker fallback or error handler returns raw upstream exceptions or request headers containing secrets.
10. A dynamic route points `uri` at a non-allowlisted host while reusing credentials from other routes — **SSRF plus credential exfiltration**.

**Design goal:** credentials exist only on the exact hops that require them; if a credential provider or check fails, **fail closed** instead of letting routes proceed unchecked, forwarding wrong tokens, or falling back to default credentials.

## 3. Distinguishing Token and Credential Types

### 3.1. Access Token, ID Token, and Refresh Token

| Type | Purpose | What Gateway should do | What NOT to do |
|---|---|---|---|
| **Access token** | Call a Resource Server per `aud`/`scope`/`exp` | Verify and route per policy; intentionally relay/exchange | Send to every backend regardless of audience |
| **ID token** | OIDC identity assertion for the client | Use properly within the OIDC flow | Substitute for an access token to call APIs |
| **Refresh token** | Obtain fresh access tokens when authorized | Keep in protected backend/authorized-client store with rotation | Send refresh tokens in ordinary downstream requests |
| **Opaque token** | Token requiring introspection or server-side verification | Resource Server introspection/authorization policy | Treat opaque strings as JWTs or trust them just for length |
| **Client API key** | Identify consumer, quota/plan | Verify via hash lookup, bind policy, rotate | Treat a key alone as high-privilege user identity |
| **Service credential** | Gateway authenticating to backend/IdP | Server-side only, bounded audience/privilege | Return to browsers or read from client headers |

**JWTs are Base64URL-encoded, not encrypted confidentially by default.** JWS JWT payloads are readable by anyone holding the token. Never place passwords, private keys, banking details, or unnecessary PII in claims. Never use ID tokens as access tokens or log full JWTs to "debug scopes."

### 3.2. `iss`, `aud`, `exp`, `scope`, and `sub` Are Not Interchangeable

- `iss`: who issued the token. Must match a trusted IdP.
- `aud`: which Resource Server the token was issued for; **each backend must check its own audience**.
- `exp`, `nbf`: validity window; requires synchronized clocks and bounded clock skew.
- `scope`/`scp`, roles: granted permissions; mapping to `SCOPE_catalog:read` depends on issuer and converter.
- `sub`: subject identifier; **not** automatically equivalent to tenant, organization, or permission to access a specific resource.
- `azp`/`client_id`: authorized client details; never replaces audience/scope checks.

Gateway verifies signature, issuer, lifetime, and at minimum contract-level scopes/audience. **Backends still need resource-level authorization**: user A holding `orders:read` must not read user B's order just because Gateway accepted the token.

### 3.3. A Token "Issued for Gateway" Is Not Automatically Valid for Every Backend

Example:

```json
{
  "iss": "https://idp.example.test/realms/demo",
  "sub": "user-123",
  "aud": ["gateway-api"],
  "scope": "catalog:read",
  "exp": 1893456000
}
```

These are **illustrative claims**, not a signed token. Its audience is `gateway-api`, **not `payment-api`**. Never pass that exact token to payment just because Gateway decoded it and saw an authenticated user. When backends need end-user authentication, choose one of these patterns:

1. The initial access token is **issued directly** for the backend's audience and checked at both layers per policy.
2. Gateway uses **OAuth2 Token Exchange**/on-behalf-of supported by the IdP to mint a downscoped token for that backend's audience/scopes.
3. BFF holds the user session at Gateway; the backend uses a **service credential** and receives user context over an authenticated, controlled channel rather than unsigned spoofable headers.

**Never treat adding `X-User-Id: user-123` as token exchange.** If a backend accepts an identity header, you must enforce network boundaries/mTLS/signatures/HMAC, block direct callers, and still check authorization.

## 4. Per-Route Credential Forwarding Matrix

Before writing filters, build a **decision table**:

| Route | Caller | Auth at Gateway | Credential sent to backend | Must strip |
|---|---|---|---|---|
| `/api/public/**` | Anonymous | No user login required; abuse throttling | No credential | `Authorization`, `Cookie`, `X-API-Key`, internal identity headers |
| `/api/catalog/**` | User/app with JWT | JWT issuer/audience/scope | Catalog-audience token **if backend requires it**; else dedicated service token | Gateway session cookie, client API key, `X-Internal-*` |
| `/api/payments/**` | Authorized user | JWT + fine-grained rules | Payment-scoped token or mTLS service identity | Catalog token, refresh token, generic cookies |
| `/api/bff/orders/**` | Browser session | Session cookie + CSRF per flow | Scoped backend token/service identity | Browser `Cookie`, BFF session ID, CSRF secret |
| `/api/partners/**` | Partner integration | Verified API key + quota | Dedicated partner-backend credential if needed | **Raw partner key**, user cookies, untrusted identity headers |
| `/internal/**` | Internal caller only | mTLS/RBAC/network policy | Appropriate least-privilege identity | Internet-controlled headers, secrets from other routes |

A route `http://backend`/`lb://service-id` does not encode access rights by itself. **Routing and authorization are distinct policies.** Verify actual execution ordering across Spring Security WebFilters, Gateway route predicates, `GlobalFilter`/`GatewayFilter`s, and HTTP client filters.

### 4.1. Name Variables Unambiguously

```text
clientAuthorization  = token sent by browser/mobile
gatewaySessionCookie = cookie for login session at Gateway
partnerApiKey        = key identifying external consumer
backendServiceKey    = Gateway's key to call backend
backendAccessToken   = token scoped to backend's audience
```

Never reuse one generic `secret` variable for all of these, which invites accidental forwarding. When managing credentials in Vault, isolate key paths/roles per backend and environment with least-privilege policies.

### 4.2. Choosing the Action

| Verification outcome | Action |
|---|---|
| Client unauthorized | Return 401/403; **never call downstream** |
| Credential audience mismatches route | Do not relay; require proper token or run proper exchange flow |
| Backend needs no user token/cookie | **Remove** before outbound HTTP routing |
| Backend needs user token | Relay verified, audience-matched token; backend verifies too |
| Backend needs machine-to-machine auth | Inject credential from server-side provider; never use client input |
| Token/key provider unavailable | Fail closed with 503/controlled error; never bypass auth |
| Response holds backend credential not meant for browsers | Remove/redact response header/body per contract |
| Logging/tracing needed | Log presence, outcome, route ID, non-sensitive credential reference only |

## 5. Spring Cloud Gateway Route/Filter Chain and HTTP Header Forwarding

Spring Cloud Gateway provides GatewayFilter factories such as `RemoveRequestHeader`, `SetRequestHeader`, `RemoveResponseHeader`, `AddRequestHeader`, `TokenRelay`, and `SecureHeaders`. Each serves a **distinct** responsibility.

| Component | Direction | Purpose | Warning |
|---|---|---|---|
| `RemoveRequestHeader` | Client → backend | Strips disallowed credentials/headers | Does not replace authentication/authorization |
| `SetRequestHeader` | Client → backend | Sets **a single value** controlled by Gateway | Never hardcode public secrets in YAML |
| `AddRequestHeader` | Client → backend | Appends a header value | Can produce multi-value headers; unsuitable for "safely overwriting" identity headers |
| `RemoveResponseHeader` | Backend → client | Strips headers carrying secrets or internal info | Do not strip `Set-Cookie` on routes that legitimately use backend cookies |
| `TokenRelay` | Gateway → backend | Fetches OAuth2 authorized-client access token and forwards bearer | Requires OAuth2 Client/registration and token audience policy |
| `SecureHeaders` | Gateway → client | Sets browser security response headers | Does not redact request tokens or replace mTLS |
| Custom `GlobalFilter` | Depends on impl | Cross-cutting routing/filter rules | Ordering, SecurityContext, and body handling must be right |

**Important trap:** an HTTP proxy may forward `Authorization` under default header pass-through even when `TokenRelay` is **not** configured. `TokenRelay` is an OAuth2 mechanism to fetch/attach an access token; it is **not the sole switch** deciding whether `Authorization` reaches the backend. If a route needs no token, **actively strip** it and verify downstream via integration tests.

### 5.1. Public Route: Stripping Credentials from Outbound Requests

Minimal WebFlux 5.x YAML:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: public-catalog
              uri: http://localhost:8081
              predicates:
                - Path=/api/public/**
                - Method=GET
              filters:
                - StripPrefix=2
                - RemoveRequestHeader=Authorization
                - RemoveRequestHeader=Cookie
                - RemoveRequestHeader=X-API-Key
                - RemoveRequestHeader=X-Authenticated-User
                - RemoveRequestHeader=X-Internal-Role
                - RemoveResponseHeader=Set-Cookie
```

`GET /api/public/items/42` arrives at the backend as `GET /items/42` **without** any listed credential headers. `RemoveResponseHeader=Set-Cookie` fits **when this public route forbids backends from setting cookies**; do not copy that rule into an app requiring session cookies. Never delete security headers like `Cache-Control`, `Vary`, or HSTS just to "clean up" responses.

**Accompanying security conditions:** `Method=GET` only restricts the HTTP method, **not** authentication; `localhost:8081` is a lab backend. Gateway still needs rate limiting, TLS/egress policies, and route selection controls against abuse. If another catch-all route exists, test that it never receives unintended sensitive requests.

### 5.2. Internal Route: Never Use `AddRequestHeader` as Identity Proof

Flawed example treating an upstream header as authentication:

```yaml
filters:
  - AddRequestHeader=X-Authenticated-User, admin
```

This writes **the exact same identity** on every request to the route without checking JWTs, sessions, or permissions. Worse, if the client already sent `X-Authenticated-User`, `AddRequestHeader` creates **two values** that downstream services may parse differently—a form of **header confusion**.

When injecting a Gateway-derived header, **strip any spoofed client header first**, then use `SetRequestHeader` or a custom filter setting the **verified value** from the principal, guarded by backend allowlists and trusted transport. For strong privileges/PII, **prefer signed tokens, mTLS, or a purpose-built identity propagation mechanism** instead of relying on unsigned header strings.

### 5.3. `default-filters` Does Not Replace the Security Chain

Filters can apply globally via `default-filters` in the appropriate Gateway namespace, yet:

- A global "strip `Authorization` on all routes" rule breaks downstream Resource Servers that need bearer tokens.
- A global "add backend API key on all routes" rule is **dangerous**, leaking credentials to new or hijacked routes.
- Filter ordering interactions between `TokenRelay`, `RemoveRequestHeader`, and custom filters can cause tokens to be **stripped after relay** or **relayed after stripping**.
- `GatewayFilter` execution occurs **after** Spring Security WebFilters in standard WebFlux flows; when Gateway authenticates credentials, tests must confirm unauthenticated requests fail before outbound routing.

**Sound design:** sanitize high-risk headers **by trust zone**, reserve default filters for truly universal rules, and attach route-specific auth/credential policies to sensitive services.

## 6. Validating JWTs at Gateway with Spring Security WebFlux

Gateway can act as an **OAuth2 Resource Server**: receiving Bearer tokens, verifying signature, issuer, expiration, and authorities before allowing requests onto routes. Backends must still verify resource-level permissions and their own audience if receiving bearer tokens.

### 6.1. Dependencies and Config Source

Maven fragment for **Gateway Server WebFlux** with a compatible Spring Cloud BOM:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
```

Verify artifact/starter names against your Spring Boot/Gateway release train. **Do not add the OAuth2 Client starter solely to validate JWTs**; OAuth2 Client supports login/authorized-client/`TokenRelay` flows covered in section 7.

`application.yml` (replace issuer and audience with your **environment's** real values):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
          audiences: gateway-api
```

`issuer-uri` configures the trusted issuer; Spring Security can discover the JWK Set URI from the IdP metadata endpoint to verify JWT signatures. `audiences` is a Boot property validating the `aud` claim on supporting releases; if your target version lacks it or needs custom rules, register an `OAuth2TokenValidator<Jwt>` per your API. **Never assume setting issuer alone validates audience.** Never accept fake/unsigned JWTs just because OAuth2 test setup feels heavy.

### 6.2. Java WebFlux Security Chain

```java
package com.example.gateway.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
public class GatewaySecurityConfiguration {

    @Bean
    SecurityWebFilterChain gatewaySecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/actuator/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/catalog/**")
                    .hasAuthority("SCOPE_catalog:read")
                .pathMatchers(HttpMethod.POST, "/api/payments/**")
                    .hasAuthority("SCOPE_payments:write")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

**This is an illustrative authorization model**:

- `/api/public/**` permits anonymous **GET** only per route/security policy.
- `GET /api/catalog/**` requires scope `catalog:read`.
- `POST /api/payments/**` requires `payments:write`, which is **still not enough** to process payments safely: the backend must verify user/tenant ownership, idempotency, and transaction limits.
- `anyExchange().denyAll()` denies every undeclared path/method, including `/actuator/gateway/**` unless separately governed.
- Neither OAuth2 login nor cookie sessions are included here; for bearer-only APIs, design CSRF policy per client type. Never disable CSRF globally and then copy that snippet into a cookie-based BFF.

**If public GETs may carry Bearer tokens without forcing authentication:** `permitAll()` does not guarantee every `Authorization` header is ignored by the Resource Server filter. Test how valid and invalid bearer tokens behave on public routes. Above all, `RemoveRequestHeader=Authorization` strips tokens **before forwarding**, never replacing inbound Spring Security WebFilters.

### 6.3. Validating All Required JWT Claims

Before granting `authenticated()` or `hasAuthority(...)`:

1. Verify signing algorithms against an allowlist; never accept `alg=none`.
2. Fetch public signing keys from a **trusted** IdP/JWKS, never trusting attacker-supplied `jku`/`x5u` URLs in JWT headers.
3. Validate `iss`, `aud`, `exp`, and `nbf` with small, bounded clock skew.
4. Validate `scope`/`roles` and map per issuer policy, never trusting an arbitrary `isAdmin` claim.
5. Check `tenant`/`resource ownership` at the backend; a valid JWT never guarantees permission on a specific object.
6. Support key rotation and revoked/compromised token handling, especially for short-lived JWTs without per-request introspection.
7. Never accept refresh tokens or ID tokens as bearer API authorization.

### 6.4. `401` and `403` Have Distinct Meanings

| Request | Expected outcome | Reaches backend? |
|---|---|---|
| No token to protected route | `401 Unauthorized` | No |
| Expired token, bad signature, wrong issuer | `401 Unauthorized` | No |
| Valid token missing required scope | `403 Forbidden` | No |
| Valid token, right scope, right route | Business response | Yes |
| Token with non-gateway audience | `401` per validator | No |
| Token with right scope, wrong tenant/owner | Usually `403`/`404` per backend policy | May reach backend; must be denied |

Never echo raw Bearer tokens in `WWW-Authenticate`, error responses, or logs. `WWW-Authenticate` should tell clients only the **auth scheme, realm, or standardized error code**, never signing key material.

## 7. `TokenRelay`: When Is Relaying Access Tokens Permitted?

Spring Cloud Gateway Server WebFlux offers the **`TokenRelay` GatewayFilter Factory**, integrated with Spring Security OAuth2 Client. It retrieves the access token bound to an **OAuth2 authorized client/client registration** (or the logged-in OAuth2 user's token) and attaches it to the backend request. This **differs** from a plain HTTP proxy passing through client-sent `Authorization` headers verbatim.

### 7.1. Configuration Prerequisites

Per Gateway WebFlux docs, add the OAuth2 Client dependency (Spring Boot starter name depends on release train):

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
```

and configure `spring.security.oauth2.client.*` properties so Spring creates `ReactiveClientRegistrationRepository`/authorized-client services. Declaring `TokenRelay` **without OAuth2 Client setup** can leave the filter bean uncreated and fail route/app startup. Being a bearer-only Resource Server **does not automatically supply** an OAuth2 authorized-client token for `TokenRelay`.

### 7.2. TokenRelay with an Explicit Client Registration Name

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: partner-api
              uri: lb://partner-api
              predicates:
                - Path=/api/partners/**
              filters:
                - StripPrefix=2
                - TokenRelay=partner-backend
```

`partner-backend` in `TokenRelay=...` is the **OAuth2 client registration ID**, not a `Route ID`, `ServiceInstance ID`, or backend hostname. A matching client registration/authorized-client mechanism must exist. The forwarded token must carry the **right audience and scopes**; the filter working technically does not prove the token is appropriate for the partner API.

With the WebFlux Java DSL:

```java
@Bean
RouteLocator partnerRoutes(RouteLocatorBuilder builder) {
    return builder.routes()
        .route("partner-api", r -> r
            .path("/api/partners/**")
            .filters(f -> f
                .stripPrefix(2)
                .tokenRelay("partner-backend"))
            .uri("lb://partner-api"))
        .build();
}
```

This bean is an alternative to the YAML route above—**never register both** with the same route ID in one project. `lb://partner-api` requires Spring Cloud LoadBalancer and `DiscoveryClient`; `partner-backend` requires OAuth2 Client config.

### 7.3. `TokenRelay` Without `clientRegistrationId`

```yaml
filters:
  - TokenRelay=
```

In an app using `oauth2Login()`, Gateway can pull the access token of the **currently logged-in OAuth2 authorized client** and send it to a resource service. However:

- **Omitting the argument** does not mean "exchange tokens for any audience."
- If a user holds only a manually constructed session with no OAuth2 authorized client, no token is available to relay by default.
- If routes span multiple backends with distinct audiences, relaying one token everywhere creates unnecessary leakage.
- Protect `AuthorizedClientService`/token stores and enforce refresh-token lifetimes/rotation for long-lived sessions.

WebFlux docs note that default `ReactiveOAuth2AuthorizedClientService` implementations may use an **in-memory store**; multi-replica Gateways need secure shared server-side authorized-client/session storage so requests switching replicas do not break login or `TokenRelay`.

### 7.4. `TokenRelay`, Raw Forwarding, and Token Exchange Differ

| Mechanism | Token source | Changes audience/scopes? | When appropriate |
|---|---|---|---|
| Raw HTTP `Authorization` forward | Header sent by client | **No** | Backend is authorized to accept the exact verified token |
| `TokenRelay` | OAuth2 authorized client from Spring Security | Does not guarantee exchange/audience swap | OAuth2 Client/login flow already minted a backend-usable token |
| OAuth2 Token Exchange/OBO | IdP issues new token from subject token + policy | **Can** request new audience/scopes when IdP supports it | Gateway needs distinct tokens per backend |
| Service-to-service client credentials | Gateway uses its own client identity | Token carries service identity | Backend needs Gateway's authority, not end-user delegation |
| mTLS service identity | Client certificate issued to Gateway | Not an access token | Backend authenticates workload/service at TLS layer |

**Least-privilege principle:** every backend receives only the credential type it requires. When one user calls catalog, payments, and profile, prefer **resource-scoped tokens** instead of relaying one over-privileged token everywhere.

### 7.5. Never Implement "Token Swapping" by Forging Headers

Never do:

```yaml
filters:
  - SetRequestHeader=Authorization, Bearer fake-payment-token
```

A static "fake token" lacks IdP signatures, revocation, issuer, audience, or least privilege. When token exchange is required:

1. Gateway verifies the inbound token.
2. Calls the IdP token endpoint over **trusted TLS** with client authentication.
3. Requests a new token for `aud=payment-api` with minimal scopes and bounded lifetime.
4. Never caches multi-user tokens under wrong keys; never logs raw tokens in metrics.
5. Backend verifies the new access token, including delegation/`sub`/`actor` claims per IdP spec.
6. Handles IdP errors by failing closed—never falling back to forwarding the original mismatched-audience token.

Authorization Servers vary in supported grant types. Never claim Spring Cloud Gateway `TokenRelay` performs RFC 8693 Token Exchange automatically; that requires an explicit OAuth2 Client/IdP integration built and tested for your environment.

## 8. Gateway Session Cookies and Backend Cookies Are Not the Same

Browsers automatically send `Cookie` headers to matching origins/paths. If Gateway uses session login (BFF or OAuth2 login), the browser carries a **Gateway session cookie**; proxy routing must not forward it to every microservice.

### 8.1. Cookie Attributes You Must Understand

| Attribute | Role | Do not misinterpret |
|---|---|---|
| `Secure` | Browser sends cookie only over HTTPS (verify platform/browser edge cases) | Does not encrypt cookie contents |
| `HttpOnly` | Client-side JavaScript cannot read the cookie directly | Does not stop all XSS or CSRF; browser still auto-sends it |
| `SameSite=Strict` | Greatly reduces cross-site sending | Can break OIDC redirects/cross-site flows |
| `SameSite=Lax` | Balances safety with top-level navigations | Does not replace CSRF tokens for sensitive session-based actions |
| `SameSite=None` | Enables supported cross-site contexts | **Requires `Secure`**; raises CSRF risk without extra guards |
| `Domain` | Restricts which domains/subdomains receive the cookie | Broad domains expose cookies across sibling subdomains |
| `Path` | Limits URL paths where browser attaches cookie | Not a hard security isolation boundary across apps on one host |
| `Max-Age/Expires` | Browser cookie retention | Does not replace server-side session expiration/revocation |
| `__Host-` prefix | Browser enforces `Secure`, `Path=/`, and **no `Domain`** | Does not replace server-side session verification |

Sample cookie for a Gateway BFF:

```http
Set-Cookie: __Host-GWSESSION=<opaque-random-id>; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
```

`<opaque-random-id>` is merely a placeholder, not a real value. Cookies should hold **high-entropy random session identifiers**, never plaintext tokens or PII. Keep server-side session stores with expiry, rotation, and logout invalidation; if a cookie is stolen, `HttpOnly`/`Secure` cannot revoke it on their own.

### 8.2. Spring WebFlux `CookieWebSessionIdResolver`

For Gateway Server WebFlux using cookie-backed **`WebSession`**, example config:

```java
package com.example.gateway.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration(proxyBeanMethods = false)
class WebSessionCookieConfiguration {

    @Bean
    WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver =
            new CookieWebSessionIdResolver();

        resolver.setCookieName("__Host-GWSESSION");
        resolver.addCookieInitializer(builder -> builder
            .path("/")
            .secure(true)
            .httpOnly(true)
            .sameSite("Lax"));
        return resolver;
    }
}
```

This snippet configures only the **WebFlux `WebSession` cookie**; it does not implement OAuth2 login, share sessions across replicas, install Spring Session Redis, or replace `HttpSession` in Gateway Server Web MVC. If your app does not use `WebSession`/cookie auth, do not create sessions just "to feel safer."

**Behind a TLS-terminating ingress**, ensure `Secure` is applied properly and proxy forwarding trust is configured. Never trust client-sent `X-Forwarded-Proto`. `__Host-` forbids `Domain` and mandates `Path=/`, so skip it only if cross-subdomain cookie sharing is an intentional requirement (which needs its own threat model).

### 8.3. Session Rotation, Logout, and Storage

A secure session design requires:

1. Generating session IDs via a CSPRNG—never predictable emails, timestamps, or sequential DB IDs.
2. Rotating session IDs on login and privilege elevation to prevent session fixation.
3. Enforcing server-side idle and absolute timeouts; cap concurrent sessions per risk profile.
4. Invalidating server-side sessions and authorized-client tokens on logout.
5. Across multiple Gateway replicas, using a **secured** server-side session/authorized-client store or sticky sessions with failover analysis; sticky sessions are not a security control.
6. Locking down Redis/session stores with ACLs, TLS, network isolation, expiry, and backup/retention policies.
7. Never printing session IDs into request logs, Sentry tags, query strings, or telemetry baggage.

Spring Session offers session storage integrations (e.g., Redis) per Servlet/WebFlux stack; pick starters/repositories matching your Boot release. **Never assume a Servlet guide configures reactive WebFlux sessions identically**: consult the reactive Spring Session docs.

### 8.4. Gateway Must Never Forward Its Own Session Cookie to Backends

On a BFF route where backends use **server-to-server authentication**:

```yaml
filters:
  - RemoveRequestHeader=Cookie
  - RemoveRequestHeader=Authorization
  - RemoveRequestHeader=X-API-Key
  # Server-side credential is then injected by a dedicated filter.
```

Once Gateway receives the browser session cookie and Spring Security WebFilters authenticate the user, route filters strip browser credentials **before HTTP routing** while the backend receives a controlled credential. **Do not** interpret `RemoveRequestHeader=Cookie` as ending the Gateway session; Spring Security already read the cookie/session inbound. Still, **never hardcode assumptions about filter order**: run integration tests proving auth happens first and stripping happens before outbound.

If a backend genuinely requires its own business cookie, build a cookie-name allowlist, rewrite domains/paths, and verify backend auth instead of stripping everything blindly. Avoid sharing the **same cookie name** across multiple apps under one Gateway origin; browsers may send multiple `Cookie` values that backends parse inconsistently.

## 9. Cookie Authentication Needs CSRF; CORS Is Not Authentication

**CSRF** is the risk of a browser automatically attaching session cookies when another site triggers a state-changing request. **CORS** lets browsers decide whether JavaScript on another origin can read responses or send custom headers. The two solve different problems.

### 9.1. When Is CSRF Required?

| Client architecture | Browser auto-sends credential? | CSRF |
|---|---|---|
| BFF with HttpOnly session cookie | **Yes** | Enable CSRF protection for state-changing requests |
| OAuth2 login storing session at Gateway | **Yes** | Handle CSRF properly across login/session flows |
| API accepting only `Authorization: Bearer ...` from non-browser clients | Not auto-sent via browser cookie | May omit CSRF per threat model; still need XSS/token security |
| Browser storing Bearer token in JS-readable storage | Code attaches header manually | High XSS/token-theft risk; prefer BFF/HttpOnly cookies |
| mTLS client cert in browser | Depends on browser/client cert behavior | Evaluate CSRF and origin policies along the actual flow |

**Never disable CSRF globally** claiming "Gateway is a REST API" when cookie-based login exists. `HttpOnly` does not stop forged requests because browsers still attach cookies automatically; `SameSite=Lax/Strict` is supplementary defense, not a substitute for verified CSRF tokens or strict same-origin design.

In Spring Security WebFlux, CSRF protection can use `ServerCsrfTokenRepository` and `ServerHttpSecurity.csrf(...)` per your version. If frontend JavaScript needs to read a CSRF token, expose a **separate CSRF token** safely and accept it back in a custom header; never put session or refresh tokens into JS-readable cookies "for convenience."

### 9.2. Illustrative Secure BFF Flow

```mermaid
sequenceDiagram
    participant B as Browser
    participant G as Gateway/BFF
    participant S as Session + OAuth2 authorized-client store
    participant O as Orders backend
    B->>G: POST /api/bff/orders + secure session cookie + CSRF header
    G->>S: Validate session and CSRF binding
    S-->>G: Authenticated user context
    G->>G: Authorize scope / tenant / action
    G->>G: Remove Cookie, Authorization, X-API-Key from outbound
    G->>O: Scoped service credential / exchanged token + request
    O->>O: Resource ownership authorization
    O-->>G: Response without backend credential
    G-->>B: Status + safe body, Cache-Control: no-store
```

If the backend requires a separate cookie, replace the `Cookie` strip step with an allowlist/re-issuance per domain policy. This flow **never requires** the backend to trust an unsigned `X-User` header, and never lets the browser extract access/refresh tokens from the session store.

### 9.3. CORS Allowlist and Credentials

Key response headers:

```http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: Content-Type, X-CSRF-TOKEN
```

This illustrates **one approved origin**, not an active Gateway CORS config. With credentials enabled, never use `Access-Control-Allow-Origin: *`, which breaks browser credential rules. Never reflect arbitrary `Origin` headers verbatim; enforce an allowlist with proper URL parsing/normalization.

**OPTIONS Preflight**:

- Browser sends `Origin` + `Access-Control-Request-Method`/`-Headers`;
- Gateway must handle OPTIONS per CORS policy without letting bearer/session auth fail preflight unexpectedly;
- The actual POST must still authenticate and carry a valid CSRF token if using cookie sessions;
- Backends do not need to receive OPTIONS if Gateway handles CORS at the edge;
- CORS never blocks non-browser clients calling directly and never replaces authorization.

### 9.4. Should You Use `SameSite=None` for OIDC?

Never pick `SameSite=None` by default just because OAuth2 login is used. Across many top-level GET navigation flows, `Lax` suffices, though OIDC using `form_post` response mode, cross-site embedding, or third-party contexts may need adjustments. Test your **exact callback flow and browsers** before choosing `SameSite` and `Secure`; if cross-site cookies are required, CSRF/origin/anti-replay controls become even more critical.

### 9.5. Distinguishing Browser Errors

| Symptom | Likely cause |
|---|---|
| Browser reports "CORS error" while cURL gets 200 | Preflight/ACAO/credentials/Vary config, not backend auth |
| Browser drops cookie after login | `Secure`, Domain/Path/SameSite, HTTPS, or redirect scheme |
| GET works, POST returns 403 | Missing CSRF token or missing authorization; check responses/logs |
| Logout deletes cookie yet session stays valid | Forgot to invalidate server-side session/authorized client |
| Cookie reaches unrelated backend | Proxy forwards `Cookie`; missing strip/allowlist |
| Browser JS can read session cookie | Missing `HttpOnly`, or another cookie holds a credential |

## 10. Client API Keys and Backend API Keys: Two Separate Identities

**An API key is not a JWT, not a session cookie, and usually lacks standard audience/claims like an OAuth2 access token.** API keys identify partners, quota plans, and app usage; they should not be the sole defense for high-value financial transactions or sensitive personal data.

### 10.1. Four Steps to Process Client-Supplied Keys

1. Accept keys in a **clearly specified header** (e.g., `X-API-Key`) over HTTPS only.
2. Validate format/length and look up a server-side **verifier** by key ID or keyed hash—never log raw values.
3. Check active state, expiry/revocation, partner permissions, route allowlist, quotas, and auxiliary IP/network limits.
4. Once authenticated and mapped to a consumer identity, **strip the raw key from outbound requests** unless a specific backend explicitly contracts for and is authorized to receive it.

Never accept API keys in query strings:

```http
GET /api/partners/orders?api_key=secret-value HTTP/1.1
```

Query strings leak into proxy logs, browser history, analytics, `Referer`, and caches. For partners, `X-API-Key` or `Authorization: ApiKey ...` headers still require TLS and log redaction; **headers are not safe if logging/wiretap prints them verbatim**.

### 10.2. Storing Keys Safely

API keys need high entropy generated by a CSPRNG and shown **only once** at issuance. With high-entropy random keys:

- Store a public prefix/key ID for lookup plus a hash/HMAC verifier of the secret portion.
- Use constant-time comparison when verifying secret verifiers where timing leaks matter.
- Encrypt backups/secret stores, separating audits from key-management privileges.
- Enforce expiry/revocation/rotation, allowing a short two-key overlap window for zero-downtime transitions.
- Never use emails, customer IDs, partner names, or guessable strings as API keys.
- If a key lacks entropy, plain SHA-256 will not stop brute force—regenerate a strong random key.

**Never use raw API keys as metric labels or plaintext Redis rate-limiter keys.** Use a **verified internal consumer ID** or managed HMAC/pseudonym to avoid high-cardinality labels and leaks via Redis key scans.

### 10.3. Before/After Boundary

```text
External request:
  X-API-Key: <partner-key>
  X-Internal-Partner: admin       (untrusted)

Gateway:
  validate partner-key -> partner-id and scopes
  authorize /api/partners/** + quota
  remove X-API-Key and X-Internal-Partner
  obtain scoped backend credential

Outbound request:
  X-Backend-Api-Key: <service-secret>   (for partner backend only)
  X-Correlation-ID: <trusted/validated-id>
  [no original partner key, no browser session cookie]
```

`<...>` above are placeholders, not real secrets. Backends should verify the service credential or mTLS and continue checking partner permissions against a **trusted identity context**, never user-supplied IDs.

### 10.4. When an API Key Leaks: How to Rotate

| Event | Action |
|---|---|
| Partner key exposed in CI logs | Revoke/rotate key, scrub logs per retention policy, check copies |
| Shared backend key exposed | Rotate that backend's service key, audit usage, block old key |
| Valid key abusing quotas | Apply consumer rate limits/quotas, monitor anomalies; never treat keys as user identity |
| A backend is compromised | Revoke backend credentials, block egress/lateral movement, rotate keys known solely to it |
| Gateway replicas mix old and new keys | Short dual-key overlap + secret-free per-key-version metrics + controlled rollout/revocation |

Instead of one shared key across all microservices, issue **per-backend/per-service/per-environment credentials** with minimal scope and independent revocation. Where supported, **mTLS or short-lived workload tokens** reduce many risks of long-lived API keys.

## 11. Provisioning Backend Credentials from a Server-Side Provider, Not Clients

A Gateway sometimes authenticates to legacy backends with `X-Backend-Api-Key`. Goals:

1. Backend keys **never come from client requests**.
2. Keys attach **only on routes designated for that backend**.
3. Raw partner keys, browser cookies, and wrong-audience Bearer tokens are stripped before outbound routing.
4. Keys load from **Secret Manager/Vault/Kubernetes Secrets** or a lifecycle-managed provider supporting rotation/revocation—never hardcoded in Java/YAML.
5. If the provider has no valid credential, return **503** or a controlled policy error—never forward unauthenticated or fall back to another key.
6. Never log keys in GlobalFilters, Netty wiretaps, metrics, or exceptions.

### 11.1. Why Not Use `AddRequestHeader` Containing a Secret?

Pattern to **avoid in production**:

```yaml
filters:
  - AddRequestHeader=X-Backend-Api-Key, super-secret-value
```

Raw values leak via Git, management endpoints displaying route definitions, debug logs, change reviews, backups, and config servers. With `AddRequestHeader`, if a client sends `X-Backend-Api-Key`, the backend can receive **multiple values**. Switching to `SetRequestHeader` from a variable still leaves secrets in config/route metadata and complicates rotation. A dedicated server-side provider with policy and secret retrieval is far better.

### 11.2. Designing `BackendCredentialProvider`

An interface supplying the **current key value** for a known backend:

```java
package com.example.gateway.security;

public interface BackendCredentialProvider {
    /**
     * Returns the current in-memory loaded credential after checking
     * expiry/rotation per policy. Never perform blocking I/O directly
     * on the Spring WebFlux event loop.
     */
    String currentKey(String backend);
}
```

Production implementations should integrate with Vault/Secret Manager using a **managed cache** refreshed asynchronously on a supported schedule/workflow. Never make synchronous Vault API calls per request on the Reactor Netty event loop. When no valid secret exists, return null or an error result so the filter fails closed; avoid stale long-lived keys. If a direct reactive provider is needed, return `Mono<Credential>` with proper timeouts/cancellation/backpressure—never call `.block()` inside a `GatewayFilter`.

### 11.3. Illustrative Custom WebFlux `GatewayFilterFactory`

```java
package com.example.gateway.security;

import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.filter.factory.AbstractGatewayFilterFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;

import java.util.Set;

@Component
public final class BackendApiKeyGatewayFilterFactory
        extends AbstractGatewayFilterFactory<
            BackendApiKeyGatewayFilterFactory.Config> {

    private static final Set<String> ALLOWED_BACKENDS =
        Set.of("orders", "partner");

    private final BackendCredentialProvider credentials;

    public BackendApiKeyGatewayFilterFactory(
            BackendCredentialProvider credentials) {
        super(Config.class);
        this.credentials = credentials;
    }

    @Override
    public GatewayFilter apply(Config config) {
        return (exchange, chain) -> {
            String backend = config.getBackend();
            if (backend == null ||
                !ALLOWED_BACKENDS.contains(backend)) {
                exchange.getResponse()
                    .setStatusCode(HttpStatus.FORBIDDEN);
                return exchange.getResponse().setComplete();
            }

            String secret = credentials.currentKey(backend);
            if (secret == null || secret.isBlank()) {
                exchange.getResponse()
                    .setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
                return exchange.getResponse().setComplete();
            }

            ServerHttpRequest outgoing =
                exchange.getRequest().mutate().headers(headers -> {
                    // Never let client override internal credentials.
                    headers.remove("X-Backend-Api-Key");
                    headers.remove("X-API-Key");
                    headers.remove(HttpHeaders.AUTHORIZATION);
                    headers.remove(HttpHeaders.COOKIE);
                    headers.remove("X-Internal-Role");

                    // Set one server-controlled value.
                    headers.set("X-Backend-Api-Key", secret);
                }).build();

            return chain.filter(
                exchange.mutate().request(outgoing).build());
        };
    }

    public static final class Config {
        private String backend;

        public String getBackend() {
            return backend;
        }

        public void setBackend(String backend) {
            this.backend = backend;
        }
    }
}
```

**This is sample code for a controlled filter in Gateway Server WebFlux.** Running it requires a real `BackendCredentialProvider` bean, proper Spring Security/route configs, and **never using a fake test provider in production**. If a provider is missing, failing startup is safer than silently omitting credentials. Any input path altering `Config.backend` must be policy-governed; the two-name allowlist is illustrative, not a production catalog.

### 11.4. Applying the Filter by Specific Backend Name

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-bff
              uri: lb://orders-service
              predicates:
                - Path=/api/bff/orders/**
              filters:
                - StripPrefix=2
                - name: BackendApiKey
                  args:
                    backend: orders
```

Backend routes **must have allowlisted URIs/service IDs owned by a trusted control plane**. If an admin could change `uri: lb://orders-service` to an attacker-controlled host, the filter would still inject the key into that request; **the `backend=orders` allowlist does not verify the network destination by itself**. You still need route-definition authorization, egress policies, DNS/SSRF protections, and integration tests.

**Auth flow note:** BFF routes must be gated/authorized by Spring Security WebFlux **before this filter runs**; this filter **does not authenticate users**. If the backend needs end-user identity, never infer a user solely from a service API key's presence; backend authorization must rely on a verified token/exchanged context or dedicated delegation mechanism.

### 11.5. How Should Missing Beans/Providers Behave?

| Case | Behavior |
|---|---|
| Provider bean unregistered | Startup fails; fix configuration/dependencies |
| Provider returns null/empty key | Gateway returns 503 ahead of outbound call |
| Secret expired/revoked | Fail closed; refresh/rotate per policy |
| Client sends spoofed `X-Backend-Api-Key` | Stripped before attaching server key |
| Route targets unlisted backend | 403 / route load-time rejection |
| Backend returns 401 on stale key | Alert on rotation drift; never log key; avoid infinite retries |
| User unauthorized for `/api/bff/orders/**` | Spring Security returns 401/403 before filter runs |

**Avoid keeping secrets in `String` longer than needed**, even though HTTP headers ultimately take strings; avoid unexpiring static global caches and heap dumps/logs during incident triage. Where OAuth2 client credentials or mTLS are available, prefer short-lived, audience-bound credentials.

## 12. TLS/mTLS and Gateway Identity When Calling Downstream

An edge-deployed Gateway typically manages **two separate connections**:

```text
Client --TLS--> Ingress/Gateway --TLS/mTLS--> Orders service
              ^ public HTTPS     ^ internal service identity
```

HTTPS from browser to ingress **does not guarantee** the Gateway → backend leg is encrypted. Never treat a "private" network as an excuse to send bearer tokens, cookies, or backend API keys over plaintext HTTP without a threat model.

### 12.1. What Does TLS Protect?

| Mechanism | Protects | Does NOT replace |
|---|---|---|
| Client → Gateway TLS | Confidentiality/integrity on public leg | Authorization, anti-CSRF, backend TLS |
| Gateway → backend TLS | Credentials and payloads in internal transit, hostname validation | Backend audience/scope/resource authorization |
| Gateway → backend mTLS | Backend verifies Gateway cert; Gateway verifies backend cert | User identity, business authorization, token expiry |
| Service mesh mTLS | Workload-to-workload identity/transport | Route policies, app-layer identity, quotas |
| HSTS | Directs browsers to use HTTPS on subsequent requests | API key rotation, TLS between microservices |

**mTLS is service/workload authentication**; it never verifies which user is accessing whose order. If backends need end-user delegation, pair mTLS with an appropriate access token or approved signed user context.

### 12.2. Outbound TLS in WebFlux

Gateway Server WebFlux typically uses the Reactor Netty HTTP client. Truststore/SSL/handshake-timeout settings live in `spring.cloud.gateway.server.webflux.httpclient.*` and release-train TLS properties; do not transfer them blindly to Servlet/Web MVC `RestClient`. For Spring Cloud Gateway Server Web MVC, current docs describe **Spring Boot SSL bundles/`spring.http.client.ssl.bundle`** for outbound clients.

**Never use settings that disable certificate verification**, such as:

```yaml
# NEVER put into production:
# spring.cloud.gateway.server.webflux.httpclient.ssl.use-insecure-trust-manager: true
```

To test, create a test CA and certificates with SANs matching backend hostnames, configure valid trust, and test negative cases:

1. Backend cert signed by trusted CA → succeeds.
2. Certificate hostname/SNI mismatch → connection fails.
3. Untrusted CA → handshake fails.
4. Backend requires mTLS and Gateway lacks client cert → fails.
5. Expired or rotated cert not yet reloaded by Gateway → fail closed and alert.

**Never "fix" TLS errors by relaying another token, adding `X-Forwarded-Proto`, or enabling trust-all.** TLS failures, OAuth2 failures, and Gateway route failures live in different layers.

### 12.3. Choosing Internal Identity

If backends support both mTLS and OAuth2:

- Use mTLS to verify the **Gateway workload** and curb lateral movement.
- Use scoped access tokens to verify **user/client context** or machine-to-machine permissions.
- Allowlist approved targets via service DNS/`lb://service-id`.
- Audit `service principal`, `route ID`, `decision`, and non-sensitive `tenant ID`.
- Never record raw access tokens or private keys in traces.

If a legacy backend accepts only an API key, temporarily use a service credential per section 11 with bounded scope/rotation and network policy; **an API key alone is not equivalent to mTLS**.

### 12.4. Trusted Proxy Headers

`Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto`, and `X-Forwarded-Host` affect client IP resolution, redirects, and HTTPS detection. Per Gateway WebFlux 5.x docs, emitting/applying Forwarded/X-Forwarded headers can be governed by:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          trusted-proxies: "10\\.0\\.0\\.\\d+"
```

This regex is strictly an **illustration** for a small network; it is **not** an exact CIDR allowlist for arbitrary proxies. Match exact IP/IPv6 formats, load-balancer/ingress source addresses, and release-specific semantics. With IPv6, NAT, and multiple hops in real life, define explicit policies and verify with request integration tests. Never set `trusted-proxies: ".*"` to trust the whole Internet. Ingress must **strip/overwrite client-supplied forwarded headers before adding its own**.

**If spoofed headers trick Gateway into thinking HTTP is HTTPS**, apps can emit broken redirects/cookies/HSTS or log wrong client IPs; never trust a self-declared IP to skip authentication or rate limiting.

## 13. Never Let Responses Become a Token/Cookie Leak Channel

Credentials can leak **in reverse** via `Set-Cookie`, `Location`, response bodies, `WWW-Authenticate`, `X-Debug-*`, or exception messages. Route filters must guard responses too, not just requests.

### 13.1. `RemoveResponseHeader` Per Contract

Suppose the public catalog backend accidentally emits:

```http
HTTP/1.1 200 OK
Set-Cookie: BACKENDSESSION=internal; Path=/; HttpOnly
X-Backend-Debug-Token: abc123
X-Internal-Host: catalog-pod-10-0-2-4
Content-Type: application/json
```

For a **route that needs no backend cookies**, filter:

```yaml
filters:
  - RemoveResponseHeader=Set-Cookie
  - RemoveResponseHeader=X-Backend-Debug-Token
  - RemoveResponseHeader=X-Internal-Host
```

Sensitive headers vanish from client responses per route policy. However, if a backend legitimately sets session cookies, **stripping `Set-Cookie` breaks login**; instead of blanket removal, use a cookie allowlist and verify `Secure`/`HttpOnly`/`SameSite`/`Domain`/`Path`.

### 13.2. Never Leak Credentials via `Location`

Suppose a backend returns:

```http
HTTP/1.1 302 Found
Location: https://external.example.test/callback?access_token=<secret>
```

Browsers can store URLs in history, leak them to other origins, or log queries. Gateway needs redirect-destination policies and must forbid backends from generating URLs containing bearer tokens. **Never treat `RewriteLocationResponseHeader` as an automatic secret scrubber across all URLs**; that filter transforms hosts/paths/Locations per rewrite rules and does not replace validating every credential class. Fix the upstream app and test redirects.

### 13.3. `SecureHeaders` Is Response Hardening, Not a Credential Sanitizer

WebFlux `SecureHeaders` adds headers such as:

- `Strict-Transport-Security` — enforces HTTPS in browsers per policy.
- `X-Content-Type-Options: nosniff` — curbs MIME sniffing.
- `X-Frame-Options: DENY` or CSP `frame-ancestors` — curbs clickjacking.
- `Referrer-Policy: no-referrer` — reduces URL leakage via referrers.
- `Content-Security-Policy` and `Permissions-Policy` — browser capability policies.

Yet **it never removes `Authorization`, `Cookie`, or API keys**, does not replace outbound TLS, and does not authorize routes. For HSTS, enable only once the entire domain/subdomains support HTTPS and understand `includeSubDomains`/`preload`; never apply it blindly to HTTP staging environments.

### 13.4. `Cache-Control` and Shared Caches

For responses holding personal data, sessions, or tokens:

```http
Cache-Control: private, no-store
Pragma: no-cache
```

`no-store` directs compliant HTTP caches not to persist sensitive content; `Pragma` only addresses legacy clients and never replaces `Cache-Control`. In production, inspect **CDNs, browser caches, Gateway `LocalResponseCache`, and backend caches** together.

Never rely on `Vary: Authorization` as "guaranteed private caching" in every setup. Shared caches can be misconfigured or fail to partition keys by tenant; the safer option is **disabling caching** on responses containing session/user-specific data. If caching is mandatory, verify cache keys include user/tenant/authorization context, expiry/revocation, encryption, and cache-poisoning protection.

### 13.5. Error Handlers and Fallbacks

A handler might accidentally emit:

```json
{
  "error": "backend timeout",
  "Authorization": "Bearer ...",
  "backendApiKey": "secret",
  "debugUri": "https://user:password@backend.internal"
}
```

Never return raw exceptions or `toString()` dumps of requests or configs. Gateway error responses should carry **stable error codes**, sanitized messages, and non-sensitive request/correlation IDs, while server logs hold filtered stack traces. CircuitBreaker fallbacks may return only approved data; never serialize `ServerWebExchange` attributes, tokens, or request headers into response JSON.

## 14. Logs, Tracing, Metrics, and Audits: Avoid Passive Credential Exfiltration

Many token leaks happen in **observability systems**: access logs, debug traces, APM tags, distributed tracing baggage, HAR files, and exception dumps. When instrumenting Gateway, enforce **data minimization**.

### 14.1. What to Log vs What Never to Log

| Should record | Never record |
|---|---|
| Route ID, service ID, HTTP method, status class | `Authorization` and Bearer token values |
| Pseudonymized internal authenticated principal ID | Session ID, `Cookie`, `Set-Cookie` |
| Authn/authz outcome, standardized reason codes | API keys, client secrets, refresh tokens |
| Backend latency, LB no-instance/retry counts | Full URLs if queries contain secrets or PII |
| Controlled Correlation ID | Raw login forms, passwords, payment payloads |
| Key version/reference like `orders-key-v3` (not raw key) | HMAC signing keys / private certificate keys |
| Trace ID / span ID | Full JWT payloads, user PII, full HTTP headers |

**Never use a token as a correlation ID**: tokens repeat across thousands of requests and grant access. Generate a random/trace ID, validate length/charset on client-sent `X-Request-ID`, and replace with a trusted value if needed.

### 14.2. Protecting Reactor Netty Wiretap and Actuator

Gateway Server WebFlux includes Reactor Netty HTTP client/server logging/wiretap features. Enabling DEBUG/wiretap at header/body level dumps credentials and cookies into logs or memory buffers. In production:

- Keep wiretap/debug logging off except under time-bounded incident procedures.
- When diagnosing, prefer status/route ID/trace ID and header **names/presence**, never raw values.
- Redact **at log emission time**, never trusting downstream log collectors to scrub every copy.
- Lock down `/actuator/gateway/routes`, `/actuator/env`, `/actuator/configprops`, `/actuator/heapdump` (if present), and any endpoint exposing route configs/properties.
- Never attach raw headers or request bodies to Sentry/OTel attributes or baggage.
- Enforce RBAC, retention/PII classification, and audits when accessing traces.

### 14.3. Log a Decision Instead of a Secret

```json
{
  "routeId": "orders-bff",
  "requestId": "req-0f8a...",
  "subjectRef": "usr-42",
  "credentialSource": "backend-provider",
  "credentialVersion": "orders-v3",
  "authDecision": "ALLOW",
  "backendStatus": 200,
  "durationMs": 38
}
```

This is a **secret-free record example**. `subjectRef` may still be personal data depending on your system; use pseudonyms and valid retention. Omit `credentialVersion` if key names/versions themselves reveal sensitive topology in multi-tenant/public contexts.

### 14.4. Audit Before Release

After hitting routes with **synthetic** JWTs/cookies/API keys in testing, inspect:

1. Gateway stdout/stderr.
2. Ingress access logs.
3. Downstream service logs.
4. Trace spans + attributes + baggage.
5. Prometheus metric label values.
6. CircuitBreaker/retry error details.
7. Test artifacts, screenshots, HAR files, and CI upload logs.

**PASS is not just the client receiving 200**: none of the synthetic credentials used in testing **may appear verbatim** in any unauthorized log, trace, or metric output.

## 15. `Retry`, `CircuitBreaker`, `RateLimiter`, and Caching Can Multiply Credential Risks

A normal request carrying sensitive tokens/cookies/headers traverses the filter chain. Enabling `Retry`, `CircuitBreaker`, `RequestRateLimiter`, or `LocalResponseCache` alters **downstream call counts, data retention windows, where credentials appear, and execution order**.

### 15.1. `Retry` Can Send Credentials Multiple Times

Consider a payment POST:

```text
POST /api/payments/charge
Authorization: Bearer <payment-scoped-token>
Idempotency-Key: <random-key>
```

If Gateway retries after a timeout, the backend might have **committed the transaction** on the first attempt. Retrying the request with the same credentials without an idempotency contract risks double charging. Ensure:

- Retry only **approved methods/failure classes**; avoid blindly retrying side-effecting POSTs.
- Use backend-verified idempotency keys scoped per key/tenant; the key is not an auth token.
- Set max retries/backoff/jitter and retry budgets to avoid retry storms.
- Confirm the access token lifetime covers retries; if refreshing mid-retry, keep token audience/subject within policy.
- If using `CacheRequestBody`/`ModifyRequestBody`, bound memory and never log bodies/credentials.
- Test **backend call counts** and header hygiene on every attempt.

Never let `Retry` or HTTP client retries automatically send credentials to a **different host** if routes/redirects/discovery are manipulated outside policy. When target URI/host changes, backend allowlists and TLS hostname validation must hold on every attempt.

### 15.2. `CircuitBreaker` Fallbacks Are Also Destinations

Example route with fallback:

```yaml
filters:
  - name: CircuitBreaker
    args:
      name: ordersBreaker
      fallbackUri: forward:/fallback/orders
      statusCodes:
        - 500
        - 503
```

With `forward:/fallback/orders`, the fallback usually runs inside Gateway and can access the `ServerWebExchange` containing `Authorization`/`Cookie`. Never:

- Echo raw request headers or exceptions;
- Send credentials to a fallback service with a different audience;
- Return a fake 200 carrying unauthorized private order data;
- Treat a fallback as an authentication mechanism;
- Expose `/fallback/orders` as an unauthenticated public API.

During backend outages, **fail closed**: if authentication or the secret provider is also unavailable, never reuse another user's stale token or bypass authorization to preserve "availability." Fallbacks should return contract-approved degraded error statuses.

### 15.3. Rate Limiting Needs Verified Keys

`RequestRateLimiter` or Redis token buckets rely on a `KeyResolver`. Avoid:

```java
// Never trust this header if client-declared and unverified.
String key = request.getHeaders().getFirst("X-User-Id");
```

Prefer deriving keys from:

- Authenticated consumer IDs from the API key verifier;
- Verified principals/tenant IDs;
- Client certificate identities verified at TLS;
- A separate fallback rate-limit key for anonymous traffic per policy.

Never use raw Bearer tokens or API keys as Redis keys or metric labels when opaque consumer IDs or keyed hashes work instead. Apply quotas **ahead of downstream API key injection** so internal secrets are never sent for Gateway-rejected requests. Verify filter ordering across security/routes in practice rather than assuming rate limiters always run ahead of every filter.

### 15.4. Response Caching Is Especially Dangerous for Session/User Data

`GET /api/orders/me` can return identical HTTP statuses with different bodies for two users. If `LocalResponseCache`/CDN keys strictly by `path`, user A can receive user B's response. Therefore:

1. For routes carrying sensitive data: **disable shared caching**, setting `Cache-Control: private, no-store`.
2. If caching is genuinely needed: partition keys by authenticated principal/tenant/authorization scope with reviewed invalidation.
3. Never store `Set-Cookie`, OAuth2 callbacks, or refresh-token responses in shared caches.
4. Test with **two users** and **two tenants**, asserting bodies never leak across them.
5. Backends still enforce ownership; cache hits bypass backend authorization, making cache policy a security layer of its own.

Never assume `LocalResponseCache` automatically skips `no-store` responses without checking version eligibility and testing that sensitive responses **are never cached**.

### 15.5. Failure Modes When Combining Filters

| Symptom | Likely cause |
|---|---|
| Public route sends user Bearer token to backend | Missing `RemoveRequestHeader` or wrong filter order |
| Backend receives two `X-Backend-Api-Key` headers | Used `AddRequestHeader` while client also sent the header |
| Retry attempt 2 lacks credential | Custom filter mishandled body/header caching or order |
| Retry attempt 2 carries another user's token | Token cache shared across users/tenants |
| Fallback returns key in JSON | Over-verbose exception/error serializer |
| RateLimiter bucket holds raw key | `KeyResolver` took unhashed/unvalidated `X-API-Key` |
| User B receives user A's response | Faulty cache key or privacy policy |
| Downstream 401 after rotation | Gateway replicas hold mismatched secret versions |

## 16. WebSocket, SSE, and Credentials on Long-Lived Connections

### 16.1. WebSocket Handshakes Are HTTP Requests Carrying Credentials

Browsers send cookies and `Origin` during the WebSocket handshake. Some non-browser clients support `Authorization` headers, yet **browser WebSocket APIs do not let JavaScript set arbitrary HTTP headers**, so apps often authenticate handshakes with session cookies/OIDC BFFs. Either way:

- Authenticate/authorize **before accepting `101 Switching Protocols`**.
- Validate `Origin` against an allowlist; WebSockets **do not use CORS preflight like `fetch`**.
- Never accept identity from `Sec-WebSocket-Protocol` or arbitrary URL query tokens without verification and leak-risk review.
- If query/subprotocol tokens are unavoidable, use short-lived single-use tokens and scrub all logs, though safer flows are preferred.
- Bind each session to the verified principal/tenant; backends must authorize messages against session context.
- Close/revoke sessions per policy on credential expiry or logout; an upgraded 101 socket does not automatically re-authenticate every frame.

`TokenRelay` or `RemoveRequestHeader` on a WebSocket route can affect the **handshake**, yet cannot filter individual WebSocket frames post-upgrade. HTTP `Retry` cannot safely reconnect/resume WebSocket messages either.

### 16.2. Cookies and Origin on WebSockets

Cookie `SameSite`/Domain/Path settings control whether browsers attach session cookies on handshakes based on origin/site relationships. If broad configs send cookies cross-site, never assume the request is valid just because a cookie arrived; validate `Origin`, defend against cross-site WebSocket hijacking, and check auth context. In Gateway Server Web MVC, WebSocket docs cover `spring.cloud.gateway.server.webmvc.websocket.allowed-origins` depending on version; Server WebFlux exposes its own handshake/filter route APIs.

### 16.3. SSE and HTTP Streaming

SSE uses a long-lived HTTP response. Tokens/cookies are usually checked **at request setup**, so tokens expiring mid-stream need explicit policy (close/re-auth/reconnect). Keep raw secrets out of streamed events, logs, and errors. `Retry` cannot safely replay a stream after initial events without duplicating data; rely on `Last-Event-ID` and backend-supported resume semantics.

### 16.4. Payload Limits and Backpressure

Access tokens and cookies can grow large; Gateway needs sensible **header-size limits**, without setting them so low that legitimate JWKS/JWTs/cookies break. Across request body sizes, streaming/multipart, and response buffering, avoid logging or retaining credentials longer than needed. Huge client cookies can trigger header-parse/413/431 errors ahead of routing; test that error bodies never echo raw headers.

## 17. Credential Lifecycle: Issuance, Storage, Rotation, and Revocation

### 17.1. Standard Lifecycle

```mermaid
flowchart LR
    ISSUE["Issue: minimum scope & TTL"] --> STORE["Store in protected system"]
    STORE --> USE["Use only on allowlisted route"]
    USE --> OBS["Observe metadata, never secret value"]
    OBS --> ROT["Rotate with bounded overlap"]
    ROT --> REVOKE["Revoke old credential"]
    REVOKE --> AUDIT["Audit + verify no stale replicas"]
```

| Stage | What to check |
|---|---|
| Issuance | Entropy, least privilege, audience, and owner |
| Storage | Vault/KMS/Secret Manager/Redis/authorized-client store ACLs/TLS |
| Retrieval | No blocking remote secret fetches on Reactor event loop; bounded cache/timeouts |
| Usage | Inject solely on approved targets; never log |
| Rotation | Do all replicas receive new keys? Is overlap bounded? |
| Revocation | Do backends/IdPs genuinely block old keys/tokens? |
| Incident | Auditing, isolation, remediation, and retention policies |

### 17.2. Lifetimes and Rotation Procedure

**Access tokens** should be short-lived with issuer/audience/scopes; refresh tokens need stronger protection because they mint new access tokens. **API keys** need expiry/revocation/overlap during rotation. **Client certificates** need renewal ahead of expiry plus backend trust updates. Across multiple Gateway replicas:

1. Issue credential v2.
2. Backend temporarily accepts v1/v2 within a bounded window.
3. Update Gateway providers/secret volumes to v2.
4. Confirm every replica uses v2 via **key version/ref, never raw keys**.
5. Revoke v1 and confirm v1 is rejected.
6. Purge logs/artifacts holding the old key per incident policy.

If a secret is actively compromised, never delay revocation just for zero-downtime migration; respond proportionally to severity and abuse risk.

### 17.3. Kubernetes Secrets and Vault Do Not Hide Leaks Automatically

A Kubernetes Secret is a Base64-encoded API object in YAML/manifests—**Base64 is not encryption**. You need encryption at rest, RBAC, pod security, auditing, CSI/external-secrets integration, restricted read access, and rotation. Secrets passed via environment variables can surface in process environments/dumps; properly permissioned mounted files still require avoiding logs and handling reloads. Never put API keys in annotations or unencrypted ConfigMaps.

### 17.4. Encryption at Rest and Trust Boundaries

For OAuth2 authorized-client stores or session stores:

- Encryption at rest reduces risk if storage/backups are read.
- TLS from client → Redis/DB/Vault secures transit.
- Access controls separate token-store read/write from route management.
- Retention/expiry and revocation do not rely solely on Redis TTLs.
- Never allow a Gateway instance acting for tenant A to retrieve tenant B's refresh tokens.
- Test backup/DR restores to ensure revoked tokens never "resurrect" unexpectedly.

### 17.5. When the Secret Provider Is Out

An in-memory cache layer can serve valid loaded credentials until expiry. Once no valid credential remains:

- Return 503/controlled failure for routes requiring backend credentials.
- Emit metrics for provider unavailability/credential expiry **without** raw secrets.
- Never fall back to hardcoded emergency keys or forward unauthenticated requests.
- Never fail over to a different backend with weaker policies.
- Maintain alerts and rotation/restore runbooks without triggering retry storms against Vault/IdP.

## 18. Security Lab: Real Gateway → Mock Backend

To ensure policies work beyond paper, test a **real HTTP port Gateway** against a **mock HTTP backend** (WireMock/MockWebServer)—never production backends. Tests verify:

1. Gateway receives requests carrying synthetic client credentials.
2. Spring Security allows/denies per route.
3. Gateway routes/filters execute.
4. Mock backend records **exact received HTTP requests**, methods, paths, headers, and call counts.
5. Clients receive responses free of leaked backend headers/credentials.

### 18.1. Test Project and Dependencies

Maven fragment matching compatible Boot/Cloud BOMs:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.wiremock</groupId>
    <artifactId>wiremock</artifactId>
    <version>3.13.2</version>
    <scope>test</scope>
  </dependency>
</dependencies>
```

`3.13.2` is an **illustrative WireMock 3 version**; check patches/compatibility for your project. Never ship test-scope WireMock into production images. Spring Boot 4 tests have updated starter artifacts; consult Spring Initializr/your BOM. Spring Security Resource Server/OAuth2 tests require security test dependencies when testing 401/403.

### 18.2. Internet-Free Route Test

`src/test/resources/application-credentialtest.yml`:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: public-test-route
              uri: ${test.backend.base-url}
              predicates:
                - Path=/api/public/**
                - Method=GET
              filters:
                - StripPrefix=2
                - RemoveRequestHeader=Authorization
                - RemoveRequestHeader=Cookie
                - RemoveRequestHeader=X-API-Key
                - RemoveRequestHeader=X-Authenticated-User
                - RemoveResponseHeader=Set-Cookie
                - RemoveResponseHeader=X-Backend-Debug-Token
```

This is a **dedicated test profile**; `${test.backend.base-url}` is injected by JUnit from the mock's random port. Isolate profiles so default production routes do not merge unintentionally. Never put mock URIs into production `application.yml`.

### 18.3. JUnit + WireMock Outbound Header-Stripping Test

```java
package com.example.gateway;

import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration
    .wireMockConfig;
import static org.springframework.boot.test.context.SpringBootTest
    .WebEnvironment.RANDOM_PORT;

@SpringBootTest(classes = GatewayApplication.class,
                webEnvironment = RANDOM_PORT)
@ActiveProfiles("credentialtest")
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class CredentialBoundaryIntegrationTest {

    private static final WireMockServer BACKEND =
        new WireMockServer(wireMockConfig()
            .dynamicPort().bindAddress("127.0.0.1"));

    static {
        BACKEND.start();
    }

    @DynamicPropertySource
    static void backendUri(DynamicPropertyRegistry properties) {
        properties.add("test.backend.base-url", BACKEND::baseUrl);
    }

    @LocalServerPort
    int gatewayPort;

    private WebTestClient client() {
        return WebTestClient.bindToServer()
            .baseUrl("http://127.0.0.1:" + gatewayPort)
            .build();
    }

    @BeforeEach
    void reset() {
        BACKEND.resetAll();
    }

    @AfterAll
    static void stop() {
        BACKEND.stop();
    }

    @Test
    void publicRouteDoesNotForwardClientSecrets() {
        BACKEND.stubFor(get(urlEqualTo("/items/42"))
            .willReturn(okJson("{\"sku\":\"42\"}")
                .withHeader("Set-Cookie", "backend=test")
                .withHeader("X-Backend-Debug-Token",
                            "synthetic-backend-secret")));

        client().get()
            .uri("/api/public/items/42")
            .header("Authorization", "Bearer synthetic-client-token")
            .header("Cookie", "__Host-GWSESSION=fake-session")
            .header("X-API-Key", "fake-partner-key")
            .header("X-Authenticated-User", "admin")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().doesNotExist("Set-Cookie")
            .expectHeader().doesNotExist("X-Backend-Debug-Token")
            .expectBody().jsonPath("$.sku").isEqualTo("42");

        BACKEND.verify(1, getRequestedFor(urlEqualTo("/items/42"))
            .withHeader("Authorization", absent())
            .withHeader("Cookie", absent())
            .withHeader("X-API-Key", absent())
            .withHeader("X-Authenticated-User", absent()));
    }
}
```

**Execution prerequisites:** `GatewayApplication` and the test profile must exist in the Gateway project; to isolate header-stripping filters, this fixture **does not** attach Resource Server authentication to `/api/public/**`. If the real application runs an OAuth2 Resource Server `SecurityWebFilterChain` validating every Bearer header even on `permitAll` routes, the synthetic `synthetic-client-token` may be rejected **before the Gateway route runs**, returning 401. Use an **isolated test-only security config** or a valid test-signed token for separate targets; **never disable production authentication just to pass fixtures**.

This tests **outbound header hygiene**, **not** authn/authz. Token verification tests in section 18.4 must run with the real Spring Security chain rejecting fake unsigned tokens. `@DirtiesContext` prevents Spring TestContext from reusing the stopped mock's URI; never run parallel tests sharing `BACKEND.resetAll()`.

### 18.4. Testing Negative Authentication Cases at Gateway

Configure a separate test profile with:

- A real JWT Resource Server `SecurityWebFilterChain`;
- **Test-only** JWKS/issuer or tokens signed with a lab key;
- Route `/api/private/**` requiring `SCOPE_orders:read`;
- WireMock backend holding zero production data.

For each request, verify:

| Request | Expected client | Mock backend |
|---|---|---|
| No Bearer token | 401 | **0 calls** |
| Invalid signature token | 401 | **0 calls** |
| Expired / future `nbf` token | 401 | **0 calls** |
| Wrong-issuer token | 401 | **0 calls** |
| Non-gateway `aud` token | 401 per validator | **0 calls** |
| Valid token lacking scope | 403 | **0 calls** |
| Valid token with scope | Per backend contract | Exact permitted calls |
| `X-Internal-Role: admin` without token | 401 | **0 calls** |

To assert zero backend calls with WireMock:

```java
BACKEND.verify(0, anyRequestedFor(anyUrl()));
```

This is a test assertion fragment run after resetting the request journal. **Never use Mockito `@WithMockUser` or `mockJwt()` expecting the principal to cross a live TCP `WebTestClient.bindToServer()` call.** Spring Security Test helpers apply when binding a mock application context, not minting JWTs over live HTTP wires. For live-port integration tests, sign real test tokens with a **test signing key** or stand up a test auth server/JWKS fixture.

### 18.5. Testing Backend Key Injection and Rotation

With the `BackendApiKey` filter and a test provider returning `key-v1-test-only`:

1. Client sends `X-Backend-Api-Key: attacker-value` and `X-API-Key: partner-fake-key`.
2. Gateway authenticates/authorizes the client per policy ahead of routing.
3. WireMock at the **orders backend** receives **one** `X-Backend-Api-Key: key-v1-test-only` and **zero** `attacker-value`/raw partner key/cookies.
4. Client response contains no `X-Backend-Api-Key`/`Set-Cookie` from backend if forbidden by route contract.
5. Provider switches to `key-v2-test-only`; new requests get v2, and v1 is revoked per test model.
6. Provider returns null/expired → 503, backend **0 calls**, never falling back to the old key.
7. Change route URI to an **unlisted** mock backend in a control-plane config test; policy layer blocks it before any key is sent.

**Never put raw production keys/tokens into test fixtures.** When testing rotation, `key-v1`/`v2` are synthetic strings, and assert that logs/metrics never contain them.

### 18.6. Testing Response Leaks and Cache Isolation

Stub WireMock returning:

```http
HTTP/1.1 302 Found
Location: /orders
Set-Cookie: BACKENDSESSION=synthetic
X-Backend-Debug-Token: synthetic-secret
Cache-Control: no-store
```

Test routes with response policies:

- `Set-Cookie`/`X-Backend-Debug-Token` **never** reach the browser if disallowed.
- `Location` contains no tokens and never points to non-allowlisted origins.
- `Cache-Control: no-store` is preserved.
- Across two synthetic users A/B, private responses are never cached or shared across users.
- On backend HTTP 500, fallbacks never echo raw headers/keys in JSON.

### 18.7. Observing Both Directions and Every Attempt

In tests with `Retry` enabled:

```text
Client request 1:
  Authorization: Bearer fake-user-token
  X-API-Key: fake-partner-key

Gateway outbound attempt 1:
  [neither raw client credential]
  X-Backend-Api-Key: fake-backend-key

Gateway outbound attempt 2 (if permitted by policy):
  [same credential policy, no cross-user mix]

Response:
  [no backend credential/cookie]
```

If backend recordings show **retry attempt 2 missing the token** or **carrying another user's token**, fix filter ordering/body caching/authorized-client state before release. Never assert status 200 alone; verify **downstream call counts and header safety on every call**.

## 19. Gateway Server Web MVC: Same Principles, Different APIs and Security Chains

Spring Cloud Gateway Server Web MVC runs on **Servlet/WebMvc.fn**, not Reactor/WebFlux. It provides corresponding filters like `RemoveRequestHeader`, `RemoveResponseHeader`, and `TokenRelay` per flavor docs, yet its Java DSL does not use `GatewayFilterFactory`/`GlobalFilter`.

### 19.1. Implementation Comparison Table

| Category | Server WebFlux | Server Web MVC |
|---|---|---|
| Starter | `spring-cloud-starter-gateway-server-webflux` | `spring-cloud-starter-gateway-server-webmvc` |
| Routing 5.x | `server.webflux.routes` | `server.webmvc.routes` |
| Security chain | `SecurityWebFilterChain` + `ServerHttpSecurity` | `SecurityFilterChain` + `HttpSecurity` |
| Request context | `ServerWebExchange`/reactive `Mono` | `ServerRequest`/Servlet request |
| Custom filters | `GatewayFilter`/`GlobalFilter` | WebMvc.fn `Before/AfterFilterFunctions`/`HandlerFilterFunction` |
| TokenRelay | WebFlux `TokenRelayGatewayFilterFactory` | MVC `TokenRelay` filter/`tokenRelay(...)` |
| Cookie session | WebFlux `WebSession` + `CookieWebSessionIdResolver` | Servlet `HttpSession` + container/Spring Session |
| OAuth2 Client | Reactive authorized-client APIs | Servlet authorized-client APIs |
| Outbound TLS | Reactor Netty HTTP client | Spring Boot `RestClient`/SSL bundles per release |
| Rate limiting | Reactive `RequestRateLimiter`/RedisRateLimiter | MVC `RateLimiter`/Bucket4j per 5.x docs |

### 19.2. Equivalent Credential-Stripping MVC Route

```yaml
spring:
  cloud:
    gateway:
      server:
        webmvc:
          routes:
            - id: mvc-public
              uri: http://localhost:8081
              predicates:
                - Path=/api/public/**
              filters:
                - StripPrefix=2
                - RemoveRequestHeader=Authorization
                - RemoveRequestHeader=Cookie
                - RemoveRequestHeader=X-API-Key
                - RemoveResponseHeader=Set-Cookie
```

In the WebMvc.fn Java DSL, use `BeforeFilterFunctions.removeRequestHeader` and `AfterFilterFunctions.removeResponseHeader` per version docs. **Never copy** the WebFlux `BackendApiKeyGatewayFilterFactory` bean from section 11 into MVC expecting it to run. Write an equivalent MVC filter pulling credentials from the provider while governing routing/headers and Servlet/`RestClient` lifecycles separately.

### 19.3. MVC Security Is Servlet-Based

```java
@Bean
SecurityFilterChain mvcSecurity(HttpSecurity http)
        throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/actuator/health").permitAll()
            .requestMatchers("/api/private/**").authenticated()
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()));
    return http.build();
}
```

This **method fragment** illustrates Servlet security APIs only; supply proper imports, Maven dependencies, and version-matched JWT issuer/audience decoders. Never use `SecurityWebFilterChain` or Reactor `WebSession` in MVC. For browser cookies, align CSRF/session configs with Spring Security Servlet rather than disabling CSRF globally to make test POSTs succeed.

### 19.4. MVC `TokenRelay` Does Not Mean All JWTs Auto-Forward Safely

Gateway Server MVC docs include a `TokenRelay` filter with an optional `clientRegistrationId`. Yet the authorized-client store, security filter chain, and token acquisition use **Servlet OAuth2 Client integration**, not WebFlux's `ReactiveOAuth2AuthorizedClientService`. Test:

- Does the registration ID exist and hold a token?
- Do token audience/scopes match the backend?
- Are duplicate `Authorization` headers or accidental client-token overrides prevented?
- How do logout/token refresh behave across multiple replicas?
- Do backends receive tokens strictly on approved routes?

### 19.5. Parity Testing Must Not Rely on Filter Names Alone

Two Gateways sharing `RemoveRequestHeader=Authorization` still differ in **filter ordering, exception mapping, security chains, connection pools, and cookie handling**. Test both against the **same downstream HTTP mock**:

1. Anonymous/invalid/valid tokens hitting each Gateway.
2. Public routes never forwarding tokens/cookies.
3. Protected routes forwarding only audience-matched credentials.
4. Retries and fallbacks leaking no keys.
5. TLS/mTLS never failing open.
6. Caches/response headers leaking no sessions.

**Never assume Gateway MVC is "less secure" just because it isn't Reactor**, nor assume WebFlux YAML copies 1:1 into MVC.

## 20. Troubleshooting Credential Leakage or Auth Mismatches

| Symptom | First suspect | Check and fix |
|---|---|---|
| Public route sends Bearer token to backend | Missing `RemoveRequestHeader` or filter order | WireMock verifies header absent |
| Backend receives two `X-Backend-Api-Key` values | `AddRequestHeader` alongside client-sent header | Strip spoofed input + `SetRequestHeader` from provider |
| Gateway 200 yet backend gets raw cookie | Default cookie passthrough unstripped | Per-route cookie allowlist/strip |
| OAuth2 `TokenRelay` bean missing | Missing OAuth2 Client/registration | Check Gateway flavor docs, authorized-client config |
| `TokenRelay` runs yet backend returns 401 | Wrong `aud`/`scope`/token type | Inspect IdP claims and backend validator |
| 401 ahead of `RemoveRequestHeader` | Spring Security rejected inbound bearer | Separate security tests from header-hygiene tests |
| `TokenRelay` grabs wrong user's token | Auth context / authorized-client cache scoping | Per-user/per-tenant store; concurrency tests |
| Backend 403 despite Gateway allowing | Stricter backend resource authorization | Check ownership/tenant; never bypass backend |
| Browser fails to store session cookie | `Secure`/SameSite/Domain/Path/HTTPS | Inspect `Set-Cookie` and reverse proxy TLS scheme |
| Browser sends cookie yet POST gets 403 | Missing CSRF token or wrong role/scope | Test CSRF separately from authorization |
| Logout fails to kill session | Cleared cookie only; server session still alive | Invalidate store and authorized-client lifecycle |
| Cookie sent to all subdomains | Overly broad `Domain` | Host-only cookie / `__Host-` prefix |
| Public response leaks internal `Set-Cookie` | Backend emitted cookie, missing response filter | `RemoveResponseHeader` per route |
| Redirect contains `?access_token=` | Upstream built URL containing secret | Fix upstream flow; validate `Location` |
| Key visible in Gateway routes Actuator | Secret hardcoded in route filter args | Move to provider and lock down Actuator |
| Traces contain JWTs/headers | Wiretap/APM baggage capture | Redact at source; enforce retention/audits |
| `429` fails to isolate tenants | `KeyResolver` used anonymous/spoofable header | Use authenticated consumer ID/tenant key |
| Retried POST causes duplicate side effects | Missing idempotency and retry policy | Per-method policy + backend deduplication |
| Cache returns wrong user's data | Unpartitioned shared cache | `no-store` or safe cache keys/invalidation |
| Internal key filter returns 503 | Secret provider unavailable/expired | Fail closed, alert/rotate |
| Backend mTLS handshake fails | Missing CA/client cert/SNI | Fix outbound TLS; never trust-all |
| Some replicas still use old key | Rotation propagation drift | Audit credential version per replica |
| Spoofed header bypasses auth | Backend trusted client-sent `X-User` | Strip + signed identity or mTLS trust |
| Ingress trusts wrong client IP | Overly broad `trusted-proxies` | Allowlist trusted hops + sanitize `Forwarded` |
| Route admin creates arbitrary targets | Dynamic routing lacks RBAC/URI allowlist | Route policy, egress limits, audits |
| 404/403 differs between WebFlux/MVC | Different property namespaces/filters/security stacks | Version/flavor-specific config + integration tests |

### 20.1. Layer-by-Layer Investigation Procedure

1. **Client:** status, route/path, credential types sent (log type only, never raw value).
2. **Ingress:** TLS termination, forwarded headers, client IP trust.
3. **Spring Security:** authn success/failure, scope/audience, session/CSRF.
4. **Gateway Route:** predicates, route ID, matched URI, default vs route-specific filters.
5. **Outbound HTTP:** exact path/method/headers/body received by backend? Any raw client credentials?
6. **Backend auth:** does backend verify issuer/audience/ownership/service credentials or blindly trust an internal header?
7. **Response:** do `Set-Cookie`/`Location`/`Cache-Control`/`WWW-Authenticate`/error bodies contain secrets?
8. **Operations:** logs, traces, retries, caches, multi-replica secret versions, and Actuator exposure.

Once credentials leak, **never merely delete logs and consider it safe**: revoke/rotate, investigate access scope, find copies in backups/telemetry, and follow organizational incident policy. Distinguish **false positives** (synthetic test tokens in fixtures) from real production secrets, yet stay vigilant when logs ship to third-party systems.

### 20.2. "Quick Fixes" to Avoid

- Disabling JWT signature/audience validation to stop 401s.
- Disabling CSRF globally because browser POSTs get 403 while using cookie sessions.
- Enabling `Access-Control-Allow-Origin: *` with credentials or reflecting arbitrary `Origin`s.
- Enabling trust-all TLS to hide certificate errors.
- Baking a hardcoded fallback key into the JAR.
- Removing `RemoveRequestHeader=Authorization` from a public route just because another backend wants tokens.
- Enabling global `TokenRelay` across all routes without audience checks.
- Dumping full headers/JWTs into logs for debugging.
- Exposing Actuator route writes on the Internet for quick config updates.
- Returning 200 fallbacks with unauthorized user data.

## 21. Operations, Reviews, and Suspected Credential Leak Response

### 21.1. Pre-Release Checks

Route/filter/secret policy edits must be reviewed by the **route owner, backend owner, and security/identity team** whenever trust boundaries shift:

| Change | Required approvers | Mandatory tests |
|---|---|---|
| Adding `TokenRelay` to a route | OAuth2/IdP + backend owner | Audience/scope, token store, negative tests |
| Adding a backend API key | Secret owner + backend owner | No client spoofing, no cross-route leaks, rotation |
| Changing cookie `Domain/SameSite` | BFF/frontend/security owners | Browser flows, CSRF, logout |
| Enabling response caching | Privacy/security + API owner | Cross-user/tenant isolation |
| Opening new `lb://service` route | Gateway platform + backend owner | URI allowlist, mTLS, authz |
| Changing `trusted-proxies` | Ingress/network security | Spoofed headers, redirects, client IP |
| Changing retry/fallback | Backend/domain owner | Call counts, idempotency, zero credential leaks |

Never treat "unit tests are green" as sufficient for routing/credential changes; run HTTP integration tests and inspect downstream requests.

### 21.2. Canary and Rollback

A safe rollout:

1. Deploy Gateway candidate with updated filter/security policies to canary replicas.
2. Send synthetic requests with fake tokens/keys; verify outbound headers and logs.
3. Test clients A/B across two tenants, asserting 401/403/no-leak per contract.
4. Shift a small fraction of traffic on low-risk routes first.
5. Compare 401/403/429/5xx, p95/p99, backend auth failures, KeyProvider health, mTLS errors, and token renewal rates.
6. **Roll back immediately** on unauthorized forwarding, cross-tenant cache leaks, wrong-audience `TokenRelay`, or secrets in logs.
7. After rollback, evaluate whether leaked credentials need revocation/rotation; rolling back a binary **never revokes tokens** already sent to wrong destinations.

When WebSocket sessions are open, rolling back the router does not move already-established TCP connections; force client reconnects and revoke backend sessions if exposure is suspected.

### 21.3. Incident Response When a Key/Token Leaks

Recommended workflow:

```mermaid
flowchart TD
    DET["Detect leak: logs / backend / monitoring"] --> CON["Contain: stop route or egress"]
    CON --> REV["Revoke affected keys/tokens / sessions"]
    REV --> ROT["Issue rotated credentials"]
    ROT --> AUD["Audit use, routes, logs, copies"]
    AUD --> FIX["Fix filters / cache / trust boundary"]
    FIX --> TEST["Run positive + negative integration tests"]
    TEST --> ROLL["Canary + monitor + close incident"]
```

**Never destroy evidence needed for investigation** outside retention/privacy rules; handle log artifacts containing credentials under strict security and access controls. If a signing private key or mTLS private key leaks, rotation/revocation scope exceeds a single API key—audit certificate chains, clients, and affected downstream systems.

## 22. Practice Exercises with Pass Criteria

All exercises target your **Gateway lab project with synthetic credentials**; never hit production endpoints or attempt unauthorized access to real accounts, tenants, or secret stores. An exercise passes only when **both client assertions and backend request verification** succeed.

### Exercise 1 — Classifying Credentials

Given:

```text
Authorization: Bearer <user-access-token>
Cookie: __Host-GWSESSION=<random-id>
X-API-Key: <partner-key>
X-Backend-Api-Key: <orders-service-key>
X-Internal-Role: admin
```

Classify each by issuer, consumer, storage, lifetime, verification mechanism, and permitted routes. **Pass** when you clearly distinguish raw client API keys from backend service keys and identify client-sent `X-Internal-Role` as untrusted.

### Exercise 2 — Public Route Never Forwards Credentials

Set up a WireMock backend and Gateway route `/api/public/**` with `StripPrefix=2`, `RemoveRequestHeader=Authorization`/`Cookie`/`X-API-Key`. Send requests carrying synthetic headers. **Pass** when the client receives 200 per stub, the backend receives `/items/42`, and zero denylisted credential headers remain.

### Exercise 3 — Header Spoofing

Client sends `X-Authenticated-User: admin` and `X-Backend-Api-Key: attacker-value`. Add a custom filter fetching backend keys from a provider. **Pass** when the backend receives none of the spoofed client values and sees **only one** server-controlled key header. Explain why `AddRequestHeader` risks header confusion.

### Exercise 4 — JWT Issuer/Audience

Create signed test JWTs for: valid `iss/aud/exp`, wrong issuer, wrong audience, expired, and future `nbf`. Run a real Spring Security Resource Server in tests. **Pass** when invalid cases return 401 with **zero calls** to the mock backend, while valid tokens proceed per scope/route.

### Exercise 5 — Scope and Ownership

Users A and B both hold `SCOPE_orders:read`, yet request each other's `/orders/{id}`. Gateway may allow through on scope; the backend must check ownership. **Pass** when user A cannot read user B's data and tests prove authorization runs on the backend.

### Exercise 6 — `TokenRelay` with Authorized Client

Configure a test OAuth2 Client registration holding a catalog-scoped token and a `TokenRelay=...` route. Verify the token reaches the right backend and never appears on public or payment routes. **Pass** when audience/scopes match and browsers/callers never get the access token echoed in responses. Contrast `TokenRelay` with token exchange.

### Exercise 7 — BFF Session Cookie

Use `CookieWebSessionIdResolver` with `__Host-GWSESSION`, `Secure`, `HttpOnly`, `SameSite=Lax`, and `Path=/`. Test:

1. Browser receives `Set-Cookie` with exact attributes over lab HTTPS.
2. Cookie holds no raw access/refresh tokens.
3. Backend never receives the Gateway session cookie over the BFF route.
4. Logout/timeout invalidates the session server-side.

**Pass** when simulated JS cannot read the cookie and state-changing requests enforce matching CSRF/session policies.

### Exercise 8 — Independent CSRF and CORS

Simulate a POST from a valid origin missing a CSRF token in a session-cookie app: it must be denied per security contract. Send allowed and unlisted `Origin` OPTIONS preflights. **Pass** when CORS is never treated as login/authorization and CSRF is never disabled globally to silence POST 403s.

### Exercise 9 — Partner API Key Verification

Design a verifier using key ID + secret hash/HMAC, active status, scopes, and consumer-ID quotas. Generate a test API key with high entropy. **Pass** when revoked/expired keys are blocked, keys never appear in queries/logs/metrics, and backends receive only Gateway's credential.

### Exercise 10 — Backend Key Rotation

Test provider returns `orders-key-v1`, then `orders-key-v2`. Mock backend accepts a short overlap, then rejects v1. **Pass** when all replicas switch to v2 on schedule, provider failure returns 503 ahead of downstream calls, and zero hardcoded fallback keys exist.

### Exercise 11 — Response Leakage

WireMock returns `Set-Cookie: BACKENDSESSION=...` and `X-Backend-Debug-Token: ...`. Public route strips both, while a valid login route keeps `Set-Cookie` with proper attributes. **Pass** when blanket stripping does not break login and public responses leak zero internals.

### Exercise 12 — Redirects and Query Secrets

Mock backend returns `302 Location` carrying a synthetic token in the query. Audit Gateway/client policy and fix upstream to avoid URL-borne tokens. **Pass** when zero tokens appear in URLs/history/logs and external redirect hosts are allowlisted.

### Exercise 13 — Cache Isolation Across Two Users

Create two principals/tenants A and B whose `GET /api/orders/me` responses differ. Enable controlled test cache policy. **Pass** when A never receives B's body even on cache hits; verify `Cache-Control: no-store` and cache bypass on private data.

### Exercise 14 — Retries and Credentials Per Attempt

WireMock returns 503 first, then 200; enable `Retry` only on idempotent GETs. Record each request. **Pass** when both attempts carry proper backend credentials, zero raw client keys/cookies, and zero out-of-policy attempts.

### Exercise 15 — CircuitBreaker Fallback Leaks No Requests

Make the backend return 503 to trip the fallback. **Pass** when the fallback echoes zero `Authorization`, `Cookie`, API keys, exception messages, or internal upstream hosts, and never turns auth failures into 200s holding sensitive data.

### Exercise 16 — Outbound TLS/mTLS

Run a test HTTPS backend with a lab CA/private key and route Gateway to `https://`. Test valid trust, hostname mismatch, missing CA, and missing client cert. **Pass** when Gateway never fails open and never enables an insecure trust manager.

### Exercise 17 — Trusted Proxy Header Spoofing

Client injects `Forwarded`/`X-Forwarded-Proto`/`X-Forwarded-For` in the lab while a trusted test ingress hop emits standard headers. **Pass** when Gateway obeys the proxy allowlist and never trusts spoofed client IPs to bypass rate limits/auth.

### Exercise 18 — WebSocket Handshake

Use a compliant WebSocket test server. Authenticate handshakes via allowed session/token; test valid/invalid `Origin`, unauthorized sessions, and logout. **Pass** when unauthorized clients fail to open sessions, `Origin` policy holds, and zero tokens travel in query strings.

### Exercise 19 — Log/Trace Redaction

Send synthetic credentials with easily searchable markers `fake-user-token`/`fake-partner-key`/`fake-backend-key` through the lab. Scan sanitized outputs from Gateway, backend, test ingress, and trace exporters. **Pass** when zero raw values appear outside the protected mock request journal, leaving only route IDs/statuses/decision codes.

### Exercise 20 — Testing SSRF via Dynamic Routes

Build a test control plane enforcing URI host and service ID allowlists. Propose a route targeting an unlisted destination **without sending real requests to unauthorized internal hosts**. **Pass** when route creation is rejected before traffic/secret injection, recording the proposer's audit identity.

### Exercise 21 — Comparing Server WebFlux and Server Web MVC

Against the same downstream mock, build two separate Gateway apps: `SecurityWebFilterChain`/WebFlux `RemoveRequestHeader` vs `SecurityFilterChain`/MVC `BeforeFilterFunctions`. **Pass** when both enforce identical credential-isolation contracts despite differing Java APIs/route configs, with 401/403/response-header test cases on both.

### Exercise 22 — Key-Compromise Drill

Simulate a synthetic backend API key leaking into a log fixture. Write a runbook covering containment → revoke/rotate → audit → fix → integration tests → canary. **Pass** when it includes purging keys from log/backup copies per policy, scoping prior key usage, and verifying every replica adopts the new key.

### Self-Assessment Table

| Competency | Pass criterion |
|---|---|
| Trust boundaries | Distinguishes client/Gateway/backend credentials |
| JWT | Verifies iss/aud/exp/nbf/scopes plus backend resource ownership |
| TokenRelay | Never confuses raw forwarding with OAuth2 authorized-client/token exchange |
| Cookies | Secure/HttpOnly/SameSite/Domain/Path + session lifecycle |
| CSRF/CORS | Never treats CORS as auth; never disables CSRF on cookie sessions |
| API keys | Verifies, quotas, rotates; never uses raw keys in logs/rate keys |
| Backend credentials | Server-side provider, route allowlist, fail-closed |
| TLS | Proper HTTPS/mTLS and proxy trust |
| Filters | Tested Remove/SetRequestHeader and response sanitization |
| Resilience/caching | Retries/fallbacks/caches leak zero credentials or cross-user data |
| Observability | Logs/traces/metrics free of raw tokens/keys/cookies |
| CI | Asserts both client responses and backend headers/call counts |
| Incident response | Clear revoke/rotate/audit/rollback steps and ownership |

## 23. Review Questions and Model Answers

**1. Why shouldn't all client request headers be forwarded to every backend?**  
Because headers can carry tokens, session cookies, API keys, or client-spoofed identities. Each backend should receive only credentials matching its audience and policy.

**2. Why doesn't `RemoveRequestHeader=Authorization` authenticate clients by itself?**  
It only removes the header on outbound requests; Spring Security must authenticate/authorize inbound ahead of routing.

**3. Is `TokenRelay` the same as raw `Authorization` forwarding?**  
No. `TokenRelay` integrates OAuth2 Client/authorized-client token acquisition, whereas plain proxying may pass through raw `Authorization` unless filtered. Both require audience policies.

**4. What happens if you add `TokenRelay` to YAML without an OAuth2 Client registration?**  
The filter bean may not be created or routes may fail startup due to missing client config; Resource Server JWT validation does not automatically create an authorized-client token.

**5. What name does `TokenRelay=partner-backend` take?**  
The OAuth2 **client registration ID**, not automatically a Route ID or ServiceInstance ID.

**6. Does `TokenRelay` automatically convert a Gateway access token into a token with `aud=payment-api`?**  
Never assume so. Changing audience requires Token Exchange/OBO or an appropriate IdP flow plus backend validation.

**7. Should ID tokens be used to call Resource Servers?**  
No. ID tokens are identity assertions for the OAuth2/OIDC client; APIs require access tokens issued for the right audience and scopes.

**8. Are JWT payloads encrypted confidentially?**  
Not by default. JWS JWT payloads are Base64URL-encoded and readable; never store secrets or unnecessary PII inside them.

**9. Why is verifying `iss` alone insufficient?**  
A token from the right issuer could be minted for another audience or lack required scopes. Verify `aud`, expiry, signature, scopes, and resource ownership.

**10. If Gateway already checked scopes, must the backend still authorize?**  
Yes. Backends understand resource ownership/tenants and must enforce their own policies, especially on sensitive data.

**11. How does 401 differ from 403?**  
401 generally indicates missing/invalid authentication; 403 indicates an authenticated principal lacking permission. Always test your exact contract.

**12. Why shouldn't an API key be the sole protection for high-value resources?**  
Keys typically identify apps/consumers, leak/replay easily if exposed, and lack user/transaction context. Pair with authorization, quotas, and mTLS/OAuth2.

**13. Why never send API keys in query strings?**  
URLs leak through access logs, browser history, `Referer`, analytics, and caches. Use headers over TLS with log redaction.

**14. Can random API keys be stored hashed?**  
Yes—store a secret verifier/hash/HMAC if the key has strong entropy and lookup/rotation are secure. Hashing cannot save a short, guessable key.

**15. Should raw partner API keys be forwarded to the Orders backend?**  
Not by default. Gateway verifies the key and enforces quotas/identity; the backend receives a service credential or appropriate token if needed.

**16. Why can `AddRequestHeader=X-Backend-Api-Key` be dangerous?**  
Clients sending that header cause the backend to receive multiple values; hardcoding secrets in YAML also risks leaks via configs/Actuator.

**17. What is the purpose of `BackendCredentialProvider`?**  
Retrieving server-managed keys with rotation/expiry rather than client inputs. Missing keys must fail closed ahead of downstream routing.

**18. Can placing a secret in route YAML as `${SECRET}` be considered completely safe?**  
No. Property resolution avoids hardcoded literals, yet route metadata/config dumps, access controls, rotation, and exposure still need scrutiny. Server-side providers suit sensitive/long-lived secrets better.

**19. Does `HttpOnly` prevent CSRF?**  
No. Browsers still attach session cookies automatically on requests. `HttpOnly` mainly blocks JS access to the cookie.

**20. Does a `Secure` cookie encrypt the cookie's value?**  
No. It instructs browsers to transmit the cookie only over secure transport; you still need HTTPS, strong session IDs, and backend validation.

**21. Does `SameSite=Lax/Strict` replace CSRF tokens?**  
Not by default. It adds defense in depth and carries trade-offs with OAuth2 login/cross-site flows.

**22. What does a `__Host-` cookie require?**  
`Secure`, `Path=/`, and no `Domain`; this curbs subdomain cookie forgery without replacing session authorization.

**23. Why not forward BFF session cookies to all microservices?**  
The cookie belongs to Gateway's session trust boundary; backends needing no session cookie could leak session IDs via logs or compromise. Use service identity or scoped backend tokens.

**24. With multiple Gateway replicas, what fails with an in-memory authorized-client/session store?**  
Switching replicas loses session/token state or causes flaky logins/logouts. Use a distributed server-side store and consistent rotation/policies if required.

**25. Does CORS authenticate users?**  
No. CORS is a browser cross-origin policy; non-browser clients call directly and can spoof `Origin`.

**26. When must Gateway handle OPTIONS preflight?**  
When browsers send cross-origin requests whose methods/headers require preflight. Gateway must return allowlisted CORS headers without relaxing auth on the actual request.

**27. Does Gateway → backend mTLS replace JWT user authorization?**  
No. mTLS authenticates the workload/service; user permissions still require trusted tokens/context and backend policies.

**28. Why never use `use-insecure-trust-manager` to resolve TLS errors?**  
It disables certificate validation, opening MITM and credential theft. Fix CAs/hostnames/SNI/client certs properly.

**29. If a client sends `X-Forwarded-For`, can Gateway trust it as the client IP?**  
Not outside a controlled proxy chain. Ingress must sanitize headers and Gateway must use a trusted-proxy allowlist.

**30. Does the `SecureHeaders` filter strip access tokens?**  
No. It adds browser security response headers, not request credential sanitization.

**31. Should `Set-Cookie` be stripped on every response?**  
No. Good for routes needing no backend cookies, yet breaks login/sessions on legitimate routes. Set response policies per route.

**32. Why is `Location: https://...?...token=...` dangerous?**  
Tokens leak via browser history, logs, `Referer`, and destination sites. Never pass credentials through URLs or redirects.

**33. Why should `Cache-Control: no-store` appear on private data?**  
It directs HTTP caches not to persist sensitive responses; verify Gateway/CDNs honor it and never mix users/tenants.

**34. Does `Vary: Authorization` guarantee completely safe caching?**  
No. Misconfigured caches, key design, and storage quirks can still leak data. Prefer disabling shared caches on private data.

**35. How else can `Retry` leak credentials?**  
Every attempt resends headers/bodies; govern target hosts, attempt caps, expiry, user/tenant isolation, and idempotency.

**36. How can a `CircuitBreaker` fallback leak secrets?**  
By echoing raw exceptions, request headers, exchange attributes, or calling a fallback backend with the wrong audience.

**37. Why never use a raw API key as a rate-limit key?**  
Keys leak into Redis/metrics/logs, and clients can invent unverified keys. Use internal consumer IDs or trusted keyed hashes.

**38. How does a WebSocket handshake differ from CORS preflight?**  
WebSocket handshakes carry `Origin` without fetch-style CORS preflight; authenticate/authorize the handshake and check an `Origin` allowlist.

**39. What happens when a Bearer token expires mid-SSE/WebSocket session?**  
Frames/events are not automatically re-authenticated. Apps must explicitly close, trigger re-auth/reconnect, and control resumption.

**40. Can WebFlux's `SecurityWebFilterChain` be used in Gateway Server Web MVC?**  
No. MVC uses Servlet `SecurityFilterChain`/`HttpSecurity`, and route filter APIs differ too.

**41. Why do credential-leak tests need WireMock/MockWebServer?**  
They capture actual requests **after Gateway routes/filters run**, verifying exact backend headers and call counts rather than client status alone.

**42. Why does a public route with a fake Bearer sometimes return 401 before `RemoveRequestHeader`?**  
Spring Security Resource Server may evaluate and reject the bearer token inbound even on `permitAll` routes; separate header-hygiene tests from authentication tests.

**43. During a secret provider outage, what should Gateway do?**  
Fail closed with 503/controlled errors on routes needing keys and fire metrics/alerts; never forward unauthenticated or use hardcoded fallbacks.

**44. When a key leaks, is rolling back the Gateway image enough?**  
No. Keys/tokens may already have been copied or used. Revoke/rotate, audit, scrub logs/backups/other replicas, and complete incident remediation.

**45. What else does dynamic route security need besides a known service ID?**  
Route-management RBAC, URI/host allowlists, egress policies, mTLS, filter validation, and audits; a valid service name never proves a caller may create a route.

## 24. Gateway Credential Protection Checklist

### 24.1. Architecture and Trust Boundaries

- [ ] Every route has a defined owner, backend service ID/URI, security policy, and allowed client types.
- [ ] Clear **client credential → Gateway validation → downstream credential** matrix per route.
- [ ] Never forward client `Authorization`/`Cookie`/`X-API-Key` by default.
- [ ] Allowlists cover backend destinations, TLS requirements, URI schemes, and dynamic route permissions.
- [ ] Client-declared headers (`X-User`, `X-Tenant`, `X-Internal-Role`) never treated as verified identity.
- [ ] Trusted-proxy policy trusts only verified ingress/mesh hops; ingress sanitizes forwarded headers.
- [ ] Backends still enforce resource/tenant authorization rather than relying solely on Gateway.
- [ ] Public/catch-all routes cannot shadow protected routes via predicate/order mistakes.

### 24.2. OAuth2/JWT/TokenRelay

- [ ] Spring Security JWT/opaque introspection matches Gateway flavor and Boot release.
- [ ] Validators check signature algorithms, issuer, audience, expiration, and not-before.
- [ ] Every route enforces scopes/roles/permissions per HTTP method and business data.
- [ ] ID tokens and refresh tokens are never accepted as bearer API access tokens.
- [ ] `TokenRelay` applies solely to approved routes and OAuth2 client registrations.
- [ ] Relayed access tokens match target audience/scopes; token exchange uses IdP-supported flows where needed.
- [ ] OAuth2 authorized-client/session stores have ACLs, encryption/TTL, rotation, and multi-replica strategy.
- [ ] 401/403 failures never reach backends when Gateway must block.
- [ ] Tokens never appear in query strings, `Location` redirects, or URL userinfo.

### 24.3. Cookies/Sessions/CSRF/CORS

- [ ] Session cookies set `Secure`, `HttpOnly`, `SameSite`, `Path`, and `Domain` per threat model.
- [ ] `__Host-` cookies omit `Domain` and require `Path=/` and `Secure`.
- [ ] Session IDs are random with idle/absolute expiry, rotation, and server-side invalidation.
- [ ] Backends never receive Gateway session cookies unless explicitly contracted.
- [ ] Cookie-backed POST/PUT/PATCH/DELETE endpoints enforce proper CSRF protection.
- [ ] CORS permits only approved origins/methods/headers; wildcards never paired against credential rules.
- [ ] OPTIONS preflight follows browser policy while actual requests still enforce authz/CSRF.
- [ ] Logout invalidates server sessions/authorized clients, not merely browser cookies.
- [ ] Evaluated risks of overlapping cookie names/`Domain`/`Path` across apps.

### 24.4. API Keys and Service Credentials

- [ ] Client API keys have high entropy, expiry/revocation, and verified consumer quotas.
- [ ] Keys rejected in URL queries and logs; raw keys never used as Redis/metric labels.
- [ ] Each backend has its own service credential/permission scope where needed.
- [ ] Backend credentials fetched from Vault/Secret Manager/provider, never hardcoded in route YAML/Java.
- [ ] Inbound client `X-Backend-Api-Key` stripped; outbound key holds **one** server-controlled value.
- [ ] Service credentials never injected on routes outside the backend allowlist.
- [ ] Provider unavailable / expired secret **fails closed** with alerting.
- [ ] Secret rotation tested across all replicas; old keys revoked on schedule.
- [ ] No blocking remote secrets API calls on the WebFlux event loop.

### 24.5. TLS, Headers, Responses, and Observability

- [ ] Client → Gateway and Gateway → backend secured with TLS per policy.
- [ ] Certificate hostnames, trust CAs, mTLS identities, and expiry/rotation tested.
- [ ] Never use insecure trust managers; never trust arbitrary `Forwarded` headers.
- [ ] Header sanitization runs ahead of outbound HTTP routing on every relevant route.
- [ ] `RemoveResponseHeader` strips only forbidden headers without breaking login/cookie flows.
- [ ] `Location` never embeds tokens/keys/secrets or redirects to non-allowlisted hosts.
- [ ] Sensitive responses set `Cache-Control: no-store` and never leak via shared caches across users/tenants.
- [ ] `SecureHeaders`/HSTS/CSP/Referrer-Policy aligned with browser/domain policy.
- [ ] Logs, traces, APM, Netty wiretap, Actuator, and metrics leak zero tokens/cookies/keys.
- [ ] Never use raw `Authorization`/API keys/session IDs as correlation IDs or metric labels.
- [ ] WebSocket/SSE handshakes, `Origin`, token expiration, and reconnects tested.

### 24.6. Resilience, Testing, and Operations

- [ ] `Retry` restricted to approved methods/failures with idempotency where needed.
- [ ] Retry attempts never switch credential audience/user/tenant or hit unlisted hosts.
- [ ] `CircuitBreaker` fallbacks/error handlers never reflect secrets/exceptions.
- [ ] `RateLimiter` keys on authenticated principals/consumer IDs instead of spoofable headers.
- [ ] Cache/Retry/TokenRelay/filter ordering covered by flavor-specific integration tests.
- [ ] Downstream mocks verify **headers and call counts**, not client status alone.
- [ ] Tests cover negative cases: missing/invalid tokens, wrong scope/audience, client header spoofing, CSRF/CORS denials.
- [ ] Tests cover response leaks, redirects, `Set-Cookie`, and key provider outage/rotation.
- [ ] TLS negative cases and forwarded-header spoofing tested.
- [ ] Two-user/two-tenant scenarios prove zero response or cache cross-contamination.
- [ ] Sensitive admin/Actuator routes enforce authentication, authorization, network isolation, and audits.
- [ ] CI uses synthetic credentials only, keeping raw values out of logs/artifacts.
- [ ] Canary/rollback, revoke/rotate, and credential-compromise incident runbooks exist.

## 25. Summary

Protecting tokens, cookies, API keys, and credentials behind Spring Cloud Gateway begins with **designing trust boundaries per route and per backend**. The Gateway must not act as a "transparent pipe" forwarding everything clients send into internal networks. It must **verify inbound identity**, enforce authorization, **strip unneeded credentials**, attach only **audience/service-matched credentials**, and scrub responses so secrets never leak back to browsers.

Principles to remember:

1. **Right token for the purpose:** access tokens differ from ID tokens/refresh tokens; JWTs must be verified for signature, issuer, audience, expiry, and scopes. Backends still enforce resource ownership.
2. **`TokenRelay` does not magically make every token valid for every backend.** To swap audiences, implement IdP-backed OAuth2 Token Exchange/client credentials rather than forging `Authorization` via route headers.
3. **Gateway cookies are Gateway credentials.** Configure `Secure`/`HttpOnly`/`SameSite`, session lifecycles, and CSRF/CORS for browsers; never forward session cookies to every backend.
4. **Client API keys and backend API keys are distinct.** Verify client keys first, strip raw keys, fetch rotating service keys from a provider, attach one controlled value on trusted routes, and fail closed if keys are missing.
5. **TLS/mTLS and egress allowlists protect internal legs**, while `RemoveRequestHeader`/`RemoveResponseHeader`, `SecureHeaders`, and security filters guard distinct parts of the HTTP flow. No single filter replaces the whole security architecture.
6. **`Retry`, `CircuitBreaker`, `RateLimiter`, caches, and WebSocket/SSE** change how credentials persist and traverse connections; never test only "HTTP 200."
7. **Measure both sides.** Verify what clients receive and **which exact headers and call counts** downstream receives—while proving zero raw tokens/cookies/keys land in logs, traces, or responses.

A secure Gateway does more than **reject bad requests**: it **never sends credentials where they are unneeded**, **never caches or logs them wrongly**, and can **revoke, rotate, and audit** when a trust boundary is breached. STEP 4 completes authoring this knowledge document; domain Content QA/refactoring, integration testing, and real security reviews remain separate steps.

## Official References

1. [Spring Cloud Gateway Server WebFlux — TokenRelay GatewayFilter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/tokenrelay-factory.html) — OAuth2 Client integration, `clientRegistrationId`, and authorized-client store.
2. [Spring Cloud Gateway Server Web MVC — TokenRelay Filter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/filters/tokenrelay.html) — token relay in Servlet/WebMvc.fn.
3. [Spring Cloud Gateway Server WebFlux — SecureHeaders](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/secureheaders-factory.html) — browser security response headers.
4. [Spring Cloud Gateway Server WebFlux — RemoveRequestHeader](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/removerequestheader-factory.html) — stripping headers before proxy routing.
5. [Spring Cloud Gateway Server WebFlux — RemoveResponseHeader](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/removeresponseheader-factory.html) — stripping response headers.
6. [Spring Cloud Gateway Server WebFlux — HTTP Headers Filters](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/httpheadersfilters.html) — Forwarded/X-Forwarded, trusted proxies, hop-by-hop headers.
7. [Spring Cloud Gateway Server WebFlux — CORS Configuration](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/cors-configuration.html) — global/route CORS and preflight.
8. [Spring Cloud Gateway — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html) — route/filter namespaces per Gateway flavor/version.
9. [Spring Cloud Gateway Server Web MVC — Spring Security Integration](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webmvc/spring-security.html) — Servlet SecurityFilterChain/Resource Server/OAuth2 Client.
10. [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html) — JWT issuer, audience, validators, and scopes.
11. [Spring Security — Servlet OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html) — Resource Server configuration on the Servlet stack.
12. [Spring Security — WebFlux CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html) — CSRF protection and reactive setup.
13. [Spring Framework — CookieWebSessionIdResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/session/CookieWebSessionIdResolver.html) — WebFlux session cookie options.
14. [Spring Session — Reference](https://docs.spring.io/spring-session/reference/) — session lifecycle, Redis, and WebFlux/Servlet integrations.
15. [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) — `Secure`/`HttpOnly`/`SameSite` cookies, session rotation, and storage.
16. [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html) — token validation, API keys, HTTP methods, CORS, and URL leakage.
17. [OWASP — JSON Web Token Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html) — JWT risks and token claims/storage.
18. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — sensitive data in logs and auditing.
19. [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) — rotation, vaults, and least privilege.
20. [OWASP — Server Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) — URI/host allowlists and network controls.
21. [OAuth 2.0 Token Exchange — RFC 8693](https://www.rfc-editor.org/rfc/rfc8693) — standards-based delegation/token exchange.
22. [OAuth 2.0 Security Best Current Practice — RFC 9700](https://www.rfc-editor.org/rfc/rfc9700) — OAuth2 token/redirect/client security.
23. [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie) — cookie attributes and `__Host-` prefix.
24. [OWASP — Application Security Verification Standard](https://owasp.org/www-project-application-security-verification-standard/) — authentication, session, secrets, and API security baseline.

> **Version and testing note:** Java/YAML examples in this lesson require compatible Spring Boot/Gateway/Security BOMs and must be run in a lab project with test backends and synthetic credentials before real-world use. `TokenRelay`/`SecureHeaders`/`RemoveRequestHeader`, configuration namespaces, cookie/session APIs, and Web MVC equivalents can change across release trains; consult the documentation for your active version. This content **does not replace** the STEP 6 academic QA cycle, integration tests on real systems, or authorized security penetration testing.
