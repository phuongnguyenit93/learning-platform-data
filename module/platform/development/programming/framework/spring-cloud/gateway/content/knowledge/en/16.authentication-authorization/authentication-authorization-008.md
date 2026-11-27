# Opaque Tokens and Introspection Integration When Appropriate

## 1. Why Does an API Gateway Need to Understand Opaque Tokens?

In a microservices architecture, **Spring Cloud Gateway** is often the common entry point for web, mobile, or partner applications. The Gateway uses **route predicates** to select routes, runs the **filter chain**, transforms paths/headers, and forwards requests to the right service. Before forwarding a request involving personal data, orders, or payments, the system must determine **who is calling** and **what the caller is allowed to do**.

A common approach is for clients to send an **OAuth 2.0 access token** via a header:

```http
GET /api/catalog/products/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer 7f8e...opaque-value...
```

If the access token is an **opaque token**, the Gateway cannot simply read the token string to learn `sub`, `scope`, expiration, or revocation status. Instead, the resource server usually must query the **Authorization Server** through an **introspection endpoint**.

This integration fits when an Identity Provider (IdP) issues **reference/opaque access tokens**, or requires resource servers to check token status against a centralized source. It also introduces important questions: at which layer checks run, how IdP errors are handled, how long caching is safe, how identity is passed to backends, and the per-request cost.

This lesson belongs to the **Authentication and Authorization** chapter of the **SPRING_CLOUD_GATEWAY** module. You will learn:

1. How to distinguish **opaque access tokens** from **JWT access tokens**.
2. OAuth 2.0 **Token Introspection (RFC 7662)** and the `active` field.
3. How to configure **Spring Security Reactive OAuth2 Resource Server** in Gateway Server WebFlux.
4. How to apply **scopes/authorities**, explain **401/403** errors, and understand security filter placement relative to Gateway filters.
5. How to evaluate trade-offs between online checks, caching, token revocation, TLS, and IdP availability.
6. How to properly test authentication flows in an API Gateway with routes, path rewriting, rate limiting, circuit breakers, and request observability.

> **Scope:** Examples use **Spring Cloud Gateway Server WebFlux**, **Spring Security Reactive**, and **OAuth2 Resource Server**. Route configs illustrate both the newer Gateway WebFlux namespace (`spring.cloud.gateway.server.webflux`) and the common 4.x style (`spring.cloud.gateway`). Security APIs and properties may change across Spring Boot/Spring Security versions; select compatible versions and verify with integration tests.

## 2. Authentication, Authorization, and the Role of Tokens

**Authentication** answers: which user or application is behind the request? **Authorization** answers: which resources or actions is that identity permitted to access?

| Concept | Question | Example |
| --- | --- | --- |
| Bearer access token | Client proves access by possessing a secret | `Authorization: Bearer <token>` |
| Authentication | Is the token still valid and which principal does it represent? | `sub=user-42`, `active=true` |
| Scope/authority | Which broad permissions were granted to the token? | `catalog.read`, `gateway.admin` |
| Route-level authorization | Does the API Gateway allow access to this endpoint? | GET catalog requires `SCOPE_catalog.read` |
| Business authorization | Does the user own order 42? | Order service verifies ownership |
| Service-to-service authorization | What functions can the calling service use on the backend? | Client credentials and matching audience |

A token with `active=true` **does not imply access to every endpoint**. The Gateway must evaluate scopes/authorities or an equivalent policy. Conversely, holding the `orders.read` scope does not prove the user can read **every order**; resource ownership should be verified inside the microservice.

**A Bearer token is a secret**: anyone holding an unexpired token can use it within its granted scope unless additional constraints like sender-constrained tokens apply. Therefore, always transmit over TLS, avoid logging tokens, and protect tokens on the client.

## 3. Opaque Tokens vs. JWT Access Tokens

### 3.1. Fundamental Differences

An **opaque token** is a value whose authoritative contents a resource server **cannot derive and verify locally** just by reading the token string. It is typically a random identifier referencing state managed by the Authorization Server.

A **JWT** has a structured, encoded format that can carry claims; a resource server can verify its signature, issuer, audience, lifetime, and other conditions **locally** when configured with appropriate keys/validation.

| Criterion | Opaque token + introspection | JWT + local verification |
| --- | --- | --- |
| Client-visible token data | Usually unreadable | Has decodable claims, though **not automatically trustworthy** |
| Typical verification | Call IdP introspection endpoint | Verify signature/JWK, issuer, audience, `exp`, `nbf` |
| Token revocation | IdP can report `active=false` when queried again | Usually needs short TTLs, denylists, or other mechanisms for early revocation |
| Latency | May add a network hop per introspection | Usually lower when verified in-process |
| IdP dependency per request | Higher without caching | Lower once valid JWKs are cached |
| Caching risk | Serving stale `active` status after revocation | JWKs/claims may remain cached until expiry or refresh |
| Data exposed to client | Typically limits claim exposure | JWTs expose claims to anyone holding the token, even if signed |
| Operations | Requires endpoint, client credentials, HTTPS, timeouts | Requires key management, rotation, issuer/audience, algorithms |

**Do not judge security by token string shape alone.** A JWT is only secure when the resource server verifies signature, allowed algorithms, claims, and issuer; an opaque token is only secure when the introspection endpoint and trust policy are properly configured.

Moreover, **introspection is not strictly limited to opaque-looking tokens**: an Authorization Server may also support introspecting certain JWT tokens. Choose the verification method based on the IdP contract and security policy, not simply by counting dots in the token string.

### 3.2. When Are Opaque Tokens Appropriate?

Consider opaque tokens and introspection when:

- The IdP **intentionally issues opaque access tokens** and exposes a standard introspection endpoint.
- Resource servers need to detect **revoked tokens** relatively quickly, within caching policy limits and IdP propagation times.
- The organization wants to keep authorization metadata at the Authorization Server rather than exposing all claims to clients.
- Resource servers have a reliable channel to the IdP and can tolerate the latency/availability cost.
- The system already has introspection operations, client credentials, and proper monitoring in place.

Introspection is not necessarily the best choice when self-verifiable JWTs already exist, ultra-low latency is required, the IdP has strict bandwidth limits, or the Gateway runs in environments with frequent IdP disconnections. In such cases, weigh SLOs against revocation risk to choose the right model.

## 4. OAuth 2.0 Token Introspection per RFC 7662

### 4.1. Who Calls the Introspection Endpoint?

A typical flow has four participants:

1. **Client**: obtains an access token from the Authorization Server via an OAuth 2.0 flow.
2. **Spring Cloud Gateway**: acts as **Resource Server**, receiving requests with a Bearer token.
3. **Authorization Server / IdP**: issues tokens and exposes the **introspection endpoint**.
4. **Upstream microservice**: executes business logic after Gateway authentication/authorization.

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant G as Gateway + Spring Security
    participant I as Authorization Server / Introspection
    participant S as catalog-service
    C->>G: GET /api/catalog/products/42 + Bearer token
    G->>I: POST /introspect (token + client authentication)
    I-->>G: active=true + scope/sub/exp (if present)
    Note over G: Authenticate token and check scope catalog.read
    G->>S: Forward permitted request via Gateway route
    S-->>G: Business response
    G-->>C: HTTP response
```

The diagram depicts a request **requiring introspection**. In a system with caching configured, the Gateway may return a cached verification result instead of calling the IdP every time; freshness depends on TTL and invalidation mechanisms.

> **Key point:** introspection is executed by **Spring Security Resource Server**. A route predicate like `Path=/api/catalog/**` or a Gateway filter like `AddRequestHeader` **does not authenticate** Bearer tokens.

### 4.2. Illustrative Introspection Request

Per RFC 7662, the endpoint typically accepts an **HTTP POST** with an `application/x-www-form-urlencoded` body containing the `token` parameter. `token_type_hint` is an **optional hint**. The endpoint must authenticate the introspecting caller via an IdP-supported mechanism, such as client credentials over HTTP Basic.

```http
POST /oauth2/introspect HTTP/1.1
Host: identity.example.test
Authorization: Basic <client-credentials-encoded>
Content-Type: application/x-www-form-urlencoded

token=<url-encoded-access-token>&token_type_hint=access_token
```

Above is an **illustrative HTTP message**, not a request using real credentials. The client's Bearer token and the **introspection client** password are two separate secrets.

Example **active token** response:

```json
{
  "active": true,
  "client_id": "web-client",
  "sub": "user-42",
  "scope": "catalog.read orders.read",
  "token_type": "Bearer",
  "iss": "https://identity.example.test",
  "aud": ["gateway-api"],
  "exp": 1900000000
}
```

Example response when a token does not exist, has expired, or was revoked:

```json
{
  "active": false
}
```

Per RFC 7662 convention, an inactive token is typically returned with **HTTP 200 + `active:false`**. That is **not the Gateway's HTTP 401**. The Gateway evaluates the introspection result and rejects the client's request per its authentication policy.

**Not every field is guaranteed to be present.** Beyond `active`, an IdP may include or omit `sub`, `scope`, `client_id`, `aud`, `iss`, `exp`, `iat`, and other metadata. Agree on the actual introspection schema with your identity provider rather than assuming every response matches the example.

### 4.3. Introspection Endpoint and the Gateway's Authentication Account

Typically the Gateway needs:

| Item | Meaning | Example |
| --- | --- | --- |
| Introspection URI | HTTPS endpoint to query token state | `https://identity.example.test/oauth2/introspect` |
| Client ID | Identifier of the resource server calling introspection | `gateway-resource-server` |
| Client secret | Secret authenticating the Gateway to the IdP | Retrieved from a secret store |
| Client's access token | Token to inspect | From `Authorization: Bearer ...` header |
| Returned metadata | `active`, `scope`, `sub`, and other claims | Result returned by IdP to Gateway |

Never use a **public frontend client's ID/secret** as introspection credentials. The Gateway should be a confidential client/resource server with dedicated credentials, minimal introspection permissions, and rotation support.

The path to the introspection endpoint requires HTTPS with certificate verification. If the IdP uses mTLS, a private CA, or another client authentication method, configure the HTTP client accordingly. Never use plaintext HTTP or disable certificate validation just to get a connection working.

## 5. Configuring OAuth2 Resource Server for Spring Cloud Gateway Server WebFlux

### 5.1. Required Dependencies

The Gateway application needs **Spring Security** and **OAuth2 Resource Server** dependencies supporting the reactive stack. With Spring Boot and appropriate dependency management, a typical Maven entry is:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
```

Gateway WebFlux needs starters/dependencies compatible with the Spring Boot and Spring Cloud release train. Do not add `spring-boot-starter-web` just to write Security config: it belongs to the Servlet stack and can cause unintended web application type auto-configuration when using the reactive Gateway.

A Resource Server **does not require** OAuth2 Login functionality. It validates Bearer tokens on incoming requests; issuing access tokens or displaying login forms is handled by the identity system/client.

### 5.2. application.yml: Declaring Opaque Token Introspection

Core Spring Boot Security configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: ${IDP_INTROSPECTION_URI}
          client-id: ${IDP_INTROSPECTION_CLIENT_ID}
          client-secret: ${IDP_INTROSPECTION_CLIENT_SECRET}
```

Notes:

- The key is **`opaquetoken`**, not `jwt.jwk-set-uri`.
- `introspection-uri` is the IdP endpoint, **not the route URI to catalog-service**.
- `client-id` and `client-secret` are credentials the Gateway uses when **calling introspection**, not the user's JWT/cookie.
- Use placeholders without fallback defaults so an environment missing secrets/URIs does not silently fall back to a test account or test IdP.
- This is **Spring Security/Spring Boot configuration**, independent of the `spring.cloud.gateway.routes` or `spring.cloud.gateway.server.webflux.routes` prefix.

In deployment, supply variables from a secret manager or protected secret-injection mechanism:

```bash
export IDP_INTROSPECTION_URI=https://identity.example.test/oauth2/introspect
# IDP_INTROSPECTION_CLIENT_ID and IDP_INTROSPECTION_CLIENT_SECRET
# must be supplied via platform secret channels, never hardcoded into scripts.
export SPRING_PROFILES_ACTIVE=staging
java -jar target/api-gateway.jar
```

All domain names and JAR names are illustrative. In production, restrict access to client ID/secret configs, and never log the entire `Environment` or expose it via public Actuator endpoints.

### 5.3. Configuring Gateway Routes Without Confusing Routes and Security Policy

Catalog route example with the **newer Server WebFlux namespace**:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-api
              uri: http://localhost:8081
              predicates:
                - Path=/api/catalog/**
              filters:
                - StripPrefix=1
```

On the Gateway **Server WebFlux 4.x** branch, the route key is typically:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-api
          uri: http://localhost:8081
          predicates:
            - Path=/api/catalog/**
          filters:
            - StripPrefix=1
```

The two YAML snippets above are **version-specific alternatives** and should not be declared together. The route matches all requests to `/api/catalog/**`; **the route itself does not require a token**. The `SecurityWebFilterChain` policy in the next section decides which methods/paths are permitted.

For example, `GET /api/catalog/products/42` passes through the Gateway and becomes `GET /catalog/products/42` after `StripPrefix=1`. Gateway authorization checks must be designed for the **original client-sent path**, rather than assuming the rewritten path is checked.

## 6. Reactive SecurityWebFilterChain: Authentication and Scope Checks

### 6.1. Java Configuration for a Bearer-Token-Only API

Illustrative configuration:

```java
package example.gateway;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class GatewaySecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            // Only appropriate when the API is stateless using Bearer tokens,
            // without cookies/sessions as browser credentials.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)

            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/actuator/health", "/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/catalog/**")
                    .hasAuthority("SCOPE_catalog.read")
                .pathMatchers(HttpMethod.POST, "/api/catalog/**")
                    .hasAuthority("SCOPE_catalog.write")
                .pathMatchers("/api/admin/**")
                    .hasAuthority("SCOPE_gateway.admin")
                .anyExchange().denyAll()
            )

            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults()))

            .build();
    }
}
```

Explanation:

1. `@EnableWebFluxSecurity` enables reactive Security configuration for WebFlux.
2. `authorizeExchange` enforces permissions by HTTP method and the **URL the Gateway receives from the client**.
3. `GET /api/catalog/**` requires `SCOPE_catalog.read`; `POST` requires `SCOPE_catalog.write`.
4. `/api/admin/**` requires `SCOPE_gateway.admin`.
5. `anyExchange().denyAll()` closes undeclared endpoints. A product with additional routes must add matching matchers/policies; do not keep this snippet unchanged and expect other routes to become accessible automatically.
6. `oauth2ResourceServer(...opaqueToken(...))` enables introspection for Bearer tokens.
7. `csrf(...disable)` is only safe as a **conditional** choice for stateless APIs not relying on browser cookies/sessions as credentials. If a product combines cookie login or form/session auth, design CSRF properly rather than copying `disable` mechanically.

**CORS preflight:** for browser clients, configure valid CORS and allow `OPTIONS` preflight processing at the right WebFlux/Spring Security layer. The `denyAll` matcher above **is not a complete CORS configuration**; integrate CORS or a properly protected preflight matcher per your architecture.

### 6.2. How Are Scopes Mapped to Authorities?

With Spring Security's default OAuth2 opaque token Resource Server configuration, scopes returned from introspection are typically converted into authorities prefixed with `SCOPE_`.

For example, if introspection returns:

```json
{
  "active": true,
  "sub": "user-42",
  "scope": "catalog.read catalog.write"
}
```

After authentication, the principal typically has:

```text
SCOPE_catalog.read
SCOPE_catalog.write
```

Thus `.hasAuthority("SCOPE_catalog.read")` matches catalog GET requests, while a token carrying only `catalog.read` will **not** pass the `SCOPE_gateway.admin` check.

Each IdP may represent permissions differently: `scope`, `scp`, `roles`, `groups`, or custom metadata. **Do not assume Spring maps all of them into default authorities.** If permissions live in custom claims, implement an appropriate converter/introspector and test it separately to avoid accidentally granting admin rights from unnormalized data.

### 6.3. Successful Authentication Does Not Replace API-Specific Claim Checks

An introspection response with `active=true` and broad scopes may still be insufficient:

- **Audience:** was the access token issued for this API/Gateway?
- **Issuer:** did the metadata come from an allowed IdP?
- **Client ID:** does the token belong to an approved application/client group?
- **Expiration:** does the IdP still recognize the token, and does caching exceed `exp`?
- **Tenant/organization:** does the token belong to an authorized tenant?
- **Token binding/sender constraint:** if using mTLS/DPoP, are the constraints verified?

Validating these fields depends on the IdP contract. `active=true` **must not be treated as a substitute for all application audience/issuer constraints**. When additional checks are needed, you can decorate a `ReactiveOpaqueTokenIntrospector` bean to validate claims and convert authorities per policy. When declaring that bean yourself, note that it may **replace auto-configuration** from properties, so supply a version-appropriate delegate introspector.

Never synthesize permissions from client-sent `X-Role` or `X-Scopes` headers.

## 7. Gateway Security Filters and the Gateway Filter Chain Are Two Separate Layers

Reactive Spring Security operates through **`SecurityWebFilterChain`**, part of Spring WebFlux's **WebFilter** chain. Meanwhile, `GatewayFilter` and `GlobalFilter` are assembled and ordered by the Gateway **after a route is selected**.

```mermaid
flowchart TD
    C["Client + Bearer token"] --> W["Spring WebFlux SecurityWebFilterChain"]
    W --> A{"Token active and scope matches?"}
    A -->|"Missing/invalid"| U["401 Unauthorized"]
    A -->|"Authenticated, lacking permission"| F["403 Forbidden"]
    A -->|"Valid, sufficient permission"| R["Gateway route predicates"]
    R --> G["GlobalFilter + GatewayFilter"]
    G --> P["StripPrefix / headers / load balancing"]
    P --> S["Upstream microservice"]
    S --> C
    U --> C
    F --> C
```

This model clarifies responsibilities; the exact ordering of every filter and error handler depends on configuration. For requests matching no route after passing security, the Gateway can return 404.

**Important consequences:**

- Route `Path=/api/catalog/**` may match for routing, yet a request will not reach the route if Spring Security blocks it first.
- `RewritePath` or `StripPrefix` changes paths **inside the Gateway chain**; security policies should target the original public URL rather than relying on the rewritten path being re-checked automatically.
- `RequestRateLimiter` in the Gateway filter chain may run after authentication; when rate-limiting by user, use the **authenticated principal** as the key, never a client-sent `X-User-Id` header.
- Upstream route `CircuitBreaker`/`Retry` filters do not by default wrap introspection calls, which live in the security layer and use their own HTTP client.
- `GlobalFilter` applies to route chains, but is not guaranteed to observe 401/403 responses returned by `SecurityWebFilterChain` **before Gateway routing**.

## 8. HTTP 401, 403, 200, and Introspection Failures

| Scenario | Typical Gateway Result | Interpretation |
| --- | --- | --- |
| No Bearer token sent to protected endpoint | **401 Unauthorized** | Unauthenticated |
| Forged, expired, or `active=false` token | **401 Unauthorized** | Authentication failed |
| Token `active=true`, missing `catalog.read` scope | **403 Forbidden** | Identity established, insufficient permission |
| Token has right scope, Gateway route has healthy upstream | Status returned by upstream, e.g. 200/404/5xx | Passed Gateway security; business outcome not guaranteed |
| IdP returns 200 with `active=false` at introspection | Gateway typically returns 401 to client | 200 was the **Gateway → IdP call status** |
| Introspection endpoint rejects Gateway's own credentials | Internal 401/403 on call to IdP | Do not confuse with client 401/403 |
| IdP times out / unavailable | Protected requests must **not be allowed through by default** | Final HTTP status depends on error handling; do not assume always 401 |
| No Gateway route matches after passing security | Usually 404 | Distinct from missing authority |

**`401` differs from `403`:** 401 usually calls for re-authentication or a valid token; 403 usually requires higher privileges and is not fixed by resending the same token. In OAuth2, `WWW-Authenticate: Bearer` may carry error codes like `invalid_token` or `insufficient_scope`; how much detail is exposed must follow security policy.

### 8.1. Fail Closed When the IdP Does Not Respond

An essential operational decision:

> When the Gateway cannot prove a token is valid, **never forward the request to a protected endpoint simply because the introspection endpoint is failing**.

Never write a fallback like "IdP timeout → allow temporarily." If high availability is required, deploy an HA IdP, use sensible timeouts, explicitly managed caching, or choose a different token validation architecture per product requirements.

A network error talking to the IdP may surface as a 5xx response depending on the handling chain rather than 401; what matters for safety is **never treating an unverified token as an authenticated user**. Test failure branches to confirm there is no authentication bypass.

### 8.2. Separating Authentication Errors from Upstream Errors

When seeing 503 or timeouts, ask:

1. Did the Gateway call introspection?
2. Did the IdP return `active=false`, reject client authentication, or fail to respond?
3. Did `SecurityWebFilterChain` allow the request through?
4. Does the `lb://` route have available instances?
5. Did upstream return 5xx, or did the Gateway's HTTP client hit a network/TLS error?

Do not lump everything into a single "Gateway 5xx" log to conclude a microservice is broken. Tracing and metrics should separate introspection calls, route selection, upstream connections, and response handling.

## 9. Latency, Caching, and Token Status Freshness

### 9.1. Cost of Online Verification

If a Gateway handles 500 requests/second, and **every protected request performs a fresh introspection call**, the IdP may have to serve nearly **500 introspections/second** from that Gateway alone. Multiple Gateway replicas multiply the load significantly.

Uncached per-request latency can include:

```text
Total request time
  ≈ client -> Gateway network
  + Gateway -> IdP introspection time
  + Security policy evaluation
  + route/filter/LoadBalancer
  + Gateway -> upstream time
  + backend processing and response
```

This is a conceptual breakdown, not a strict additive formula in all cases, since reactive stages are asynchronous and may overlap. The key point is that **introspection impacts latency and availability across the entire request**.

You should not assume Spring Security Resource Server automatically caches introspection results with a TTL suited to your business needs. If caching is desired, verify your version's behavior or build an explicit caching layer.

### 9.2. Trade-Offs Between Caching and Token Revocation

| Approach | Advantage | Risk |
| --- | --- | --- |
| No cache | `active` state stays fresh with IdP | Higher latency, IdP load, network dependency |
| Short cache with bounded TTL | Cuts introspection call volume | Revoked tokens remain usable during cache window |
| Long cache | Saves even more calls | Increases revocation propagation delay and security exposure |
| Locally verified JWT | Reduces per-request IdP dependency | Needs dedicated expiration/revocation/rotation strategy |

**No setup guarantees "absolute instant revocation."** An IdP may have replication lag, or a token may be verified right before revocation occurs. Caching makes that delay more pronounced.

If caching introspection results:

- Never cache `active` beyond the token's `exp` if present; bound TTL by token lifetime and policy-acceptable staleness.
- Cap cache size to prevent exhaustion attacks using high volumes of random tokens.
- Avoid caching network errors as if they were `active=false`; distinguish **inactive token** from **unresponsive IdP**.
- Never log raw token strings used as cache keys. Tokens remain secrets even in memory.
- Provide invalidation/eviction hooks if the IdP or admin system emits revocation events.
- Test revocation, logout, user lockouts, permission changes, and actual cache expiration.

### 9.3. Introspection Timeouts, Concurrency, and Circuit Breakers

To keep a slow IdP from stalling the Gateway:

1. Configure connect/read timeouts aligned with SLOs.
2. Bound concurrent calls to the IdP and control queueing.
3. Use sensible connection pooling and monitor DNS/TLS.
4. If adding a circuit breaker, enforce **fail closed**; never return synthetic successful authentication.
5. Never retry infinitely on IdP errors; use bounded retries aware of error types to avoid amplifying outages.
6. Design HA IdPs and alert early when introspection error rates or latency rise.

Configuring `spring.cloud.gateway...httpclient.response-timeout` usually controls the **upstream routing** HTTP client, **not necessarily** the HTTP client used by Spring Security's introspector to call the IdP. When configuring an outbound proxy, custom truststore, or timeouts for introspection, configure the **introspector's own client** rather than assuming Netty routing properties control it.

## 10. Transport Security, Secrets, and Outbound Proxies

### 10.1. Protecting Both Directions

A request using an opaque Bearer token traverses sensitive hops:

```mermaid
flowchart LR
    C["Client"] -->|"HTTPS + Bearer"| G["Gateway / Resource Server"]
    G -->|"HTTPS + client auth + token"| I["IdP introspection"]
    G -->|"Backend HTTP(S) per policy"| B["Microservice"]
```

**Client → Gateway** requires proper TLS; **Gateway → IdP** requires TLS with certificate/hostname verification; **Gateway → upstream** also requires trusted encryption per system policy.

If reaching the IdP requires a **corporate egress proxy**, do not assume the Gateway routing `httpclient.proxy` property configures the introspection HTTP client. These two outbound flows can use different HTTP clients. Troubleshoot DNS/CONNECT/TLS on the exact HTTP client failing.

### 10.2. Never Expose Access Tokens or Client Secrets

- Never commit real access tokens or introspection client secrets in `application.yml` in Git.
- Use a secret manager/Kubernetes Secret/volume mount with least-privilege access.
- Never log `Authorization`, `Proxy-Authorization`, `Cookie` headers, or introspection request bodies.
- Avoid enabling full HTTP wiretap in production without redaction.
- Never place tokens in URLs/query strings; URLs routinely appear in access logs, history, and traces.
- Never return raw introspection payloads containing internal identity details to browser clients.
- Rotate client secrets and certificates; verify whether processes need restarts/reloads to pick up new values.

Access tokens should only be shared with resource servers matching the intended **audience**. If the Gateway forwards Bearer tokens upstream, backends must still verify the token or rely on a properly secured trust mechanism. **Successful authentication at the Gateway does not automatically secure downstream services** if network paths can bypass the Gateway.

## 11. Principal, Metadata, and Passing Information to Microservices

### 11.1. Should the Bearer Token Be Forwarded to the Backend?

There are two common models:

| Model | Benefit | Responsibility |
| --- | --- | --- |
| Gateway authenticates, backend also verifies Bearer token | Defense in depth; backend enforces business permissions | Backend must understand tokens and IdP, validating audience/scope properly |
| Gateway authenticates and passes controlled identity metadata | Backend avoids duplicate introspection, lower coupling | Protect network, strip spoofed client headers, verify metadata provenance |

The second model **must never** simply copy a client-sent `X-User-Id`. When passing identity headers between the Gateway and services, the Gateway must **strip/overwrite untrusted inputs**, derive identity from the **authenticated principal**, and secure internal connections via network isolation, mTLS, or verifiable message signatures.

For sensitive operations, services must still enforce resource permissions, tenant isolation, ownership, and business rules.

### 11.2. TokenRelay Is Not Synonymous with Introspection

Spring Cloud Gateway can support **`TokenRelay`** when the Gateway acts as an OAuth2 client relaying an authorized client's access token. That **is not required** to perform opaque token introspection at the Gateway.

An inbound request already carrying `Authorization: Bearer ...` may be forwarded depending on filter/header policies; the real question is **whether the backend is allowed to accept that exact token**, along with audience and trust boundaries. Do not add `TokenRelay` just because you see the word "token" and inadvertently swap tokens or leak credentials to the wrong target API.

### 11.3. Route Scopes Differ from Data Ownership

Suppose user A's token has `catalog.read` and `orders.read`. The Gateway may allow A to call `GET /api/orders/42` by scope, yet the service must verify that order 42 belongs to A or that A holds matching administrative rights. **The Gateway should not query every business table just to decide ownership.**

Layering lets the Gateway focus on authentication, shared policies, routing, rate limiting, circuit breakers, retries, TLS, and observability, while microservices own specific business decisions.

## 12. Testing with a Mock IdP and curl

### 12.1. Preparing the Test Environment

A test environment may include:

- Gateway: `http://localhost:8080` (for development on trusted networks only).
- Mock introspection endpoint: `http://localhost:9000/oauth2/introspect` (local only; use HTTPS in production).
- Catalog service: `http://localhost:8081` returning content for `GET /catalog/products/42`.
- `SecurityWebFilterChain` policy as in section 6.

The mock introspection server should simulate **Gateway authentication** via client ID/secret, HTTP POST, and both `active:true` and `active:false` responses—rather than returning `active:true` for every token. Keep mocks off public networks, and never bring production credentials into test environments.

When connecting across containers, `localhost` refers to the current container; use proper hostnames/networks if the mock IdP runs in another container.

### 12.2. Test Requests

```bash
# 1) Missing token: GET catalog requires authentication.
curl -i http://localhost:8080/api/catalog/products/42

# 2) Valid test token with catalog.read scope.
curl -i \
  -H "Authorization: Bearer demo-token-catalog-read" \
  http://localhost:8080/api/catalog/products/42

# 3) Revoked or nonexistent test token.
curl -i \
  -H "Authorization: Bearer demo-revoked-token" \
  http://localhost:8080/api/catalog/products/42

# 4) Active test token lacking catalog.read scope.
curl -i \
  -H "Authorization: Bearer demo-token-orders-read" \
  http://localhost:8080/api/catalog/products/42
```

These `demo-...` strings are **dummy tokens for the mock IdP**, not real access tokens. For real credentials, be mindful of shell history, process listings, and logs; never paste raw Bearer headers into bug reports.

### 12.3. Behavioral Test Matrix

| Case | Introspection Response | Policy to Check | Expectation |
| --- | --- | --- | --- |
| T1 | No token | GET catalog requires scope | 401, upstream not called |
| T2 | `active=false` | Unauthenticated | 401, upstream not called |
| T3 | `active=true`, scope `orders.read` | Missing `catalog.read` | 403, upstream not called |
| T4 | `active=true`, scope `catalog.read` | Sufficient for GET catalog | Gateway calls catalog-service |
| T5 | `active=true`, scope `catalog.write` | POST catalog | Permitted to proceed per route/policy |
| T6 | Valid token with wrong `aud` | Extra audience validation enabled | Rejected per policy |
| T7 | IdP unresponsive | Fail closed | Upstream access denied; status per error handling |
| T8 | IdP returns 401 due to wrong introspection secret | Failure between Gateway and IdP | Request denied; investigate secret/config |
| T9 | Valid token on nonexistent route `/unknown` | `denyAll` at end of chain | Rejected by security policy; 404 if permitted |
| T10 | Token has `orders.read` accessing another user's order | Backend checks ownership | 403/404 per service policy |

**Crucial evidence** is not just status codes: record **how many times the mock IdP was called**, **how many times upstream received a request**, the route ID, and sanitized `sub`. Requests denied 401/403 at the Security layer must never reach upstream.

### 12.4. Testing Performance and Revocation

Add these checks:

1. Send multiple requests with the same token; count introspection calls to verify whether caching actually occurs.
2. Revoke the token at the mock/IdP and retry; measure maximum delay before the Gateway rejects it.
3. Make the introspection endpoint respond slowly, drop connections, or return 5xx; verify timeouts and **no fail-open behavior**.
4. Send many random tokens to check for abnormal load on the IdP or cache.
5. Verify how the Gateway handles expired Bearer tokens while upstream remains healthy.
6. Test browser CORS preflight and `OPTIONS` handling if the frontend uses a different origin.
7. If using load balancing/circuit breakers for upstream, verify IdP failures are measured **separately** from backend failures.
8. If using an egress proxy or private CA, test the introspection HTTP client itself rather than only testing Netty routing connections.

## 13. Common Issues and How to Resolve Them

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Every request returns 401 | Token inactive, `Authorization` header never reached Gateway, wrong introspection credentials | Distinguish IdP vs. Gateway responses; check config and redacted logs |
| Introspection returns `active:true` yet Gateway returns 403 | Scope does not match `SCOPE_...` or policy denies | Check claims and granted authorities |
| Only `GET` works, `POST` fails | Policy requires `catalog.write` scope; or CSRF enabled per client type | Check method matchers, CSRF, and auth policy |
| `jwt` configured when token is opaque | Resource Server uses JWT decoder instead of introspection | Configure `opaquetoken` and matching DSL |
| Browser tokens exposed in Network/logs | Overly verbose logging/wiretap or token in URL | Remove logs, rotate tokens, and fix client |
| Gateway works locally but times out in prod during auth | IdP DNS, egress proxy, TLS/trust, or firewall | Inspect Gateway → IdP path, not just Gateway → upstream |
| HTTP 503 when IdP disconnects | Auth server outage or internal error-mapping handler | Fail closed; ensure timeouts/HA/monitoring |
| IdP returns HTTP 401/403 for introspection | Wrong client auth or unauthorized to introspect | Check client ID/secret and IdP policy |
| Scope present in IdP yet authority missing | Different claim format unsupported by default converter | Inspect principal and custom introspector/converter |
| Revoked token still accepted by some Gateways | Cache TTL, propagation delay, sessions, or mixed verification sources | Inspect caches across all Gateway replicas |
| Gateway permits API yet service returns 403 | Service checks ownership/audience/roles itself | Check business policies and token forwarding |
| Route returns 404 despite valid token | Wrong route predicate, wrong route namespace, or upstream 404 | Separate route matching from upstream response |
| IdP HTTPS connection fails cert check | CA, hostname/SNI, proxy TLS inspection, mTLS | Fix trust/identity; never enable insecure trust |
| `AddRequestHeader=X-User-Id` copies client input | Client can spoof identity | Populate from authenticated principal or verify at backend |
| Gateway latency spikes sharply | High introspection volume, slow IdP, or pool exhaustion | Measure each hop; design bounded caching/HA/limits |

## 14. Case Study Exercise: Catalog and Orders Behind One Gateway

**Context:** One Gateway serves two APIs:

| Public API | Upstream | Minimum Permission |
| --- | --- | --- |
| GET `/api/catalog/**` | `catalog-service` | `catalog.read` |
| POST `/api/catalog/**` | `catalog-service` | `catalog.write` |
| GET `/api/orders/**` | `order-service` | `orders.read` |

The IdP issues **opaque access tokens**, returning `active`, `sub`, `scope`, `aud`, and `exp` via introspection. Some tokens may be revoked immediately when users lock their accounts.

Design requirements:

1. Configure `SecurityWebFilterChain` to authorize by **method + path**, denying undeclared endpoints by default.
2. Enable opaque token introspection with URI/credentials injected from deployment secrets.
3. Ensure `aud` is valid for the target API when required by the IdP contract.
4. When `active:false` or scope is missing, the Gateway must not forward requests upstream.
5. Add Gateway routes to services with `StripPrefix=1`.
6. Rate limit by authenticated subject, avoiding client-declared headers.
7. Trigger an IdP timeout to observe fail-closed behavior; never fall back to an authorized anonymous user.
8. Test token revocation after successful introspection, especially if caching is used.
9. Decide whether backends validate Bearer tokens independently or consume protected identity assertions.
10. Emit separate metrics for 401, 403, IdP errors, upstream errors, introspection duration, and rate-limited requests.

Example adding a matcher to `SecurityWebFilterChain` from section 6:

```java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

In real code, place this matcher **before `anyExchange().denyAll()`**, alongside the catalog matchers. Never place matchers outside the DSL or after a catch-all rule covering every exchange.

### Pre-Production Checklist

- [ ] Gateway runs **Server WebFlux** with the matching Security Resource Server version.
- [ ] `opaquetoken.introspection-uri` points to HTTPS IdP with trusted hostname/CA.
- [ ] Gateway uses dedicated client credentials with minimal introspection rights, stored securely.
- [ ] `SecurityWebFilterChain` specifies scopes per method/path, denying by default where appropriate.
- [ ] `active:false`, wrong audience/issuer, expired, and revoked tokens are handled per policy.
- [ ] Resource Server does not confuse introspection HTTP 200 with client HTTP 200.
- [ ] Tested 401 vs. 403 distinction, including browser CORS preflight.
- [ ] Fails closed on IdP timeouts or 5xx; no accidental bypasses.
- [ ] Cache TTL, max size, and revocation behavior reviewed against security SLOs.
- [ ] No tokens or client secrets in logs, traces, URLs, or Git.
- [ ] Egress proxy/TLS/timeouts of the **introspection HTTP client** verified separately.
- [ ] Rate limits and audits rely on verified identities.
- [ ] Upstreams enforce ownership/tenant checks and cannot be bypassed arbitrarily around the Gateway.
- [ ] Retries/circuit breakers applied selectively; never retry infinitely on IdP failures.
- [ ] Metrics/alerts configured for spikes in introspection errors, 401/403s, and p95/p99 latency.

## 15. Summary and References

**Opaque access tokens** generally do not carry self-verifiable information for local Gateway validation. **Introspection per RFC 7662** allows Spring Security Reactive Resource Server to ask the IdP whether a token is `active` and obtain metadata such as `scope`, `sub`, `aud`, or `exp` when provided.

In **Spring Cloud Gateway Server WebFlux**, `spring.security.oauth2.resourceserver.opaquetoken` and `SecurityWebFilterChain` handle authentication and authorization. **Route predicates and Gateway filters** continue serving routing, path/header rewriting, discovery, rate limiting, and resilience; they never replace a proper OAuth2 policy.

Opaque tokens shine when centralized token state and revocation matter, at the cost of **network overhead, latency, and IdP dependency**. Combine HTTPS, secure credentials, audience/scope validation, deliberate cache TTLs, fail-closed handling, service-side business authorization, and observability to operate the Gateway safely.

Version-aligned references:

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662).
- [Spring Security Reactive — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html).
- [Spring Security Reactive — Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html).
- [Spring Cloud Gateway Server WebFlux — Gateway Filters](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories.html).
