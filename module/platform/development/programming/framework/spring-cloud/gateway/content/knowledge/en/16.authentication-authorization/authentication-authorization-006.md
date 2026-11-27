# Separating Public, Authenticated, and Admin Routes

## 1. The Problem to Solve at the API Gateway

In a microservices system, **Spring Cloud Gateway** is typically the entry point for multiple API groups: browsing a product catalog without logging in, viewing one's own account/orders after authenticating, and managing resources restricted to administrators. The Gateway also performs route predicates, filter chains, path/header modifications, service discovery, rate limiting, circuit breakers, retries, TLS, and request observability. **Not every route should have the same access level.**

Suppose a retail system has three endpoint groups:

| Group | Sample Public URL | Who Is Permitted? | Business Example |
| --- | --- | --- | --- |
| **Public** | `GET /api/public/products/42` | Unauthenticated users may also read | Viewing catalog, public product info |
| **Authenticated** | `GET /api/account/profile` | Users with a valid session/token | Viewing their own profile |
| **Admin** | `DELETE /api/admin/products/42` | Authenticated identity **and** appropriate admin permissions | Deleting products or changing configuration |

Merely declaring routes and assuming `/api/admin/**` is "hard to guess" or has an `X-Role: admin` header is enough security can allow unauthorized access. **Routes only determine forwarding targets; authorization decides who can perform the action.**

In the **Authentication and Authorization** chapter of **Spring Cloud Gateway**, this lesson focuses on designing route boundaries and enforcing them with **Spring Security WebFlux**. After studying it, you will be able to:

1. Classify public, authenticated, and admin-only endpoints per the API contract.
2. Write Gateway routes and corresponding `SecurityWebFilterChain` policies without overlaps or exposed endpoints.
3. Understand the execution order among **security WebFilters**, **route predicates**, and **GatewayFilter/GlobalFilter**.
4. Verify JWTs by issuer, signature, and lifetime; bind admin permissions to **trusted authorities/claims**.
5. Distinguish **401 Unauthorized** from **403 Forbidden**, and keep responses from leaking data.
6. Build an anonymous/user/admin test matrix; handle CORS preflight, CSRF, token relay, and special admin routes.
7. Protect upstream services too, never treating the Gateway as the sole trust boundary.

> **Scope:** Examples use **Spring Cloud Gateway Server WebFlux** and reactive Spring Security. Spring Cloud Gateway Server Web MVC uses a different filter/config model. Route namespaces and starters depend on Spring Boot/Spring Cloud versions; pick the right version for your project.

## 2. Distinguishing Routing, Authentication, and Authorization

Three decisions often appear together at the Gateway but serve different goals:

| Decision | Question | Common Mechanism |
| --- | --- | --- |
| **Routing** | Which API/service does this request belong to? | `Path`, `Method`, `Host`, `Header` predicates and route URI |
| **Authentication** | Who is the caller? Are the identity credentials valid? | Spring Security, JWT/OAuth2 Resource Server, session, mTLS per design |
| **Authorization** | Is the authenticated caller permitted to do this? | `authenticated()`, `hasAuthority(...)`, scope/role policies, and business checks |

For instance, a route with the predicate:

~~~yaml
predicates:
  - Path=/api/admin/**
  - Header=X-Role, ^admin$
~~~

**Is not an authorization mechanism.** Any client can send `X-Role: admin` if the network edge does not control headers. The result only tells you the request **qualifies to match the route**—it does not prove the caller is an administrator.

For sensitive resources such as orders, **authorization also depends on the specific resource**: even an authenticated user must not view another user's order. The Gateway can require a valid token, while the Orders service must check whether the user has rights to the requested `orderId`.

### "Public" Does Not Mean "Unprotected"

Public endpoints still need TLS, input validation, protection against scraping/abuse, rate limits, body size limits, proper CORS, and non-leaking logging. `permitAll()` only states that **authentication is not required to proceed**; it does not remove other operational and safety measures.

### "Admin" Is Not Just "Logged In"

`authenticated()` allows any caller with valid authentication, including regular user accounts. Admin routes need **stricter** rules, such as `hasAuthority("SCOPE_admin")` when an OAuth2 access token is actually granted the `admin` scope, or a role rule mapped from a trusted identity source.

## 3. Designing the Access Matrix Before Writing Code

Write the access policy as a table before configuring routes. An example policy:

| API | Anonymous | Valid User | Valid Admin | Additional Conditions |
| --- | --- | --- | --- | --- |
| `GET /api/public/products/**` | Allow | Allow | Allow | Data must truly be public |
| `POST /auth/login` | Allow | Allow per contract | Allow per contract | Brute-force protection; do not leak password-mismatch reasons |
| `GET /api/account/profile` | Deny | Allow | Allow if contract permits | Service checks identity/ownership |
| `PATCH /api/account/profile` | Deny | Allow | Allow if contract permits | Validate fields and edit rights |
| `GET /api/admin/reports` | Deny | Deny | Allow | Requires valid admin authority |
| `DELETE /api/admin/products/{id}` | Deny | Deny | Allow | Audit, business confirmation, least privilege |
| `GET /actuator/health` | May allow | May allow | May allow | Expose minimal health info only |
| `/actuator/env`, `/actuator/beans` | Deny | Deny | Do not auto-allow | Separate management plane with restricted access |

**A sound design principle is deny-by-default:** endpoints not matching permitted groups must be denied rather than automatically treated as public.

### Separating by Path, Host, or Service?

There are multiple ways to organize:

- **Path-based:** `/api/public/**`, `/api/account/**`, `/api/admin/**`. Easy to explain and test; the primary example in this lesson.
- **Host-based:** `api.example.test` for public APIs, `admin.example.test` for admin. Can help partition admin traffic, though **DNS/Host predicates do not replace authorization**.
- **Service-based:** Catalog service for public, Account service for authenticated, Admin service for admin. Dedicated backend addresses help network isolation, yet permissions must still be checked.
- **By HTTP method:** the same path has a public `GET` while `POST` requires admin. When using this style, Spring Security policy must reflect **both method and path**, not path alone.

In the examples below, separate path groups reduce the risk of overlapping rules. In real systems, a single service may host multiple permission tiers; **do not assume every endpoint of a service shares the same protection level**.

## 4. Declaring Routes: Public, Login, Authenticated, Admin

An example configuration with **Spring Cloud Gateway Server WebFlux**:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-public
              uri: lb://catalog-service
              predicates:
                - Path=/api/public/products/**
                - Method=GET

            - id: identity-login
              uri: lb://identity-service
              predicates:
                - Path=/auth/login
                - Method=POST

            - id: account-private
              uri: lb://account-service
              predicates:
                - Path=/api/account/**

            - id: administration
              uri: lb://admin-service
              predicates:
                - Path=/api/admin/**
~~~

Explanation:

1. The **catalog-public** route accepts only GET requests on public product paths.
2. The **identity-login** route accepts only POST requests to the app's login/token-issuance endpoint.
3. The **account-private** route forwards account requests to the Account service.
4. The **administration** route forwards admin requests to the Admin service.

The `lb://` URIs require **Spring Cloud LoadBalancer** and a `ServiceInstance` source (service discovery or configured instance lists). When learning with local backends, you can use `http://localhost:9001` and corresponding backend ports.

**Critical point:** The YAML above **does not protect** account or admin yet. It only describes route-matching conditions and forwarding targets. You must configure **Spring Security** to decide who is permitted to reach them.

Backends in the example must understand the exact public path received, such as `/api/public/products/42`. If a backend expects `/products/42`, intentionally add `StripPrefix` or `RewritePath`, then test the actual received path; do not confuse path transformation with security.

**Version compatibility:** In earlier Spring Cloud Gateway WebFlux releases, the prefix is typically `spring.cloud.gateway.routes` instead of `spring.cloud.gateway.server.webflux.routes`. Do not configure both simultaneously "just in case"; check your actual docs and dependencies.

## 5. Protecting Route Groups with Spring Security WebFlux

In a Gateway Server WebFlux application, **Spring Security** operates via WebFlux **WebFilters**, typically configured with `SecurityWebFilterChain`. Rules apply to requests **before Gateway routes perform normal forwarding**.

For a **stateless Bearer JWT API** (not authenticating via browser sessions/cookies), you can configure:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class GatewaySecurityConfiguration {

    @Bean
    SecurityWebFilterChain gatewaySecurityWebFilterChain(ServerHttpSecurity http) {
        return http
                // Appropriate here only because the demo API uses Bearer JWTs
                // and does not use cookies/sessions for authentication.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .authorizeExchange(exchange -> exchange
                        .pathMatchers(HttpMethod.GET, "/actuator/health")
                            .permitAll()
                        .pathMatchers(HttpMethod.POST, "/auth/login")
                            .permitAll()
                        .pathMatchers("/api/admin", "/api/admin/**")
                            .hasAuthority("SCOPE_admin")
                        .pathMatchers("/api/account", "/api/account/**")
                            .authenticated()
                        .pathMatchers("/api/public", "/api/public/**")
                            .permitAll()
                        .anyExchange()
                            .denyAll()
                )
                .oauth2ResourceServer(resourceServer ->
                        resourceServer.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

**Points to explain clearly:**

- `permitAll()` allows proceeding without authentication; it **does not** issue tokens, route requests, or bypass measures like rate limiting.
- `authenticated()` requires valid authentication, but **does not itself restrict roles, scopes, or resource ownership**.
- `hasAuthority("SCOPE_admin")` requires **`SCOPE_admin`** to be present in `Authentication` after token verification and mapping. With typical default JWT configuration, an `admin` scope in `scope`/`scp` produces `SCOPE_admin`. A token carrying only a `role: "admin"` claim **does not guarantee** this authority.
- `anyExchange().denyAll()` ensures requests matching no explicit rule **are not automatically treated as public**. Unconfigured paths do not become public for that reason either.
- `oauth2ResourceServer(...jwt(...))` only **verifies Bearer JWTs**. It does not generate or issue tokens for `POST /auth/login`; that belongs to the Identity service/Authorization Server.
- `csrf(...disable)` **is only justified when authentication relies on Bearer tokens rather than browser-auto-sent credentials like cookies**. If cookies/sessions are used, evaluate and retain proper CSRF protection; never copy this line mechanically.

**Dependency requirements:** the application needs the appropriate WebFlux security starters, typically `spring-boot-starter-security` and `spring-boot-starter-oauth2-resource-server`; for JWTs, compatible token-decoding/verification libraries are required. Do not mix Servlet MVC's `SecurityFilterChain` with reactive `SecurityWebFilterChain` in the same setup.

### Rules Are Evaluated in Order

Inside `authorizeExchange`, matchers are evaluated in configuration order. **Specific rules must appear before broad rules.** Dangerous example:

~~~java
// WRONG for admin policy: broad rule is evaluated first!
.authorizeExchange(exchange -> exchange
        .pathMatchers("/api/**").authenticated()
        .pathMatchers("/api/admin/**").hasAuthority("SCOPE_admin")
        .anyExchange().denyAll())
~~~

Requests to `/api/admin/users` are matched first by `/api/**` and only require login, bypassing the admin requirement. A safer setup puts admin matchers before broad matchers; better yet, separate namespaces clearly and avoid unnecessarily broad rules.

### Policies Covering the Root Endpoint

When using `/api/admin/**`, do not forget the exact `/api/admin` endpoint (without trailing slash). The sample above declares both to avoid unnecessary reliance on trailing-slash matching across versions. Same for `/api/account` and `/api/public`.

## 6. JWT: Verify Identity Before Checking Authorities

Spring Security OAuth2 Resource Server can verify Bearer JWTs issued by a trusted Identity Provider. Example issuer configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/store
~~~

This is an illustrative URI and must be replaced with a **real, configured, trusted issuer** in your system. The provider must publish metadata/JWKS or use a compatible decoder mechanism. During deployment, ensure the Gateway can reach the required key source per design and has valid key-rotation/failure handling.

A JWT access token typically contains claims with meaning similar to:

~~~json
{
  "iss": "https://identity.example.test/realms/store",
  "sub": "user-742",
  "aud": ["shop-api"],
  "scope": "catalog.read account.read",
  "exp": 1999999999
}
~~~

The snippet above **is only JSON illustrating a payload**, not a real signed token; do not use it for authentication. An actual request sends a token:

~~~http
GET /api/account/profile HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...<opaque-redacted>...
~~~

The Gateway must check at least the factors suited to its trust model:

| Check | Meaning |
| --- | --- |
| **Signature and allowed algorithms** | Token was genuinely signed by the trusted issuer; avoid accepting client-dictated algorithms or keys |
| **Issuer (`iss`)** | Token came from the expected trusted issuer |
| **Expiration (`exp`)** | Token is still valid |
| **Not before (`nbf`)** | Token is not used before its effective timestamp |
| **Audience (`aud`)** | Token was issued for the API/system being protected |
| **Scope/authority** | Which operation types the caller is allowed to execute |
| **Subject/tenant** | Identity and data boundary for business checks |

**Note:** Configuring `issuer-uri` in Spring Security usually verifies issuer, signature, and certain timestamps via the default decoder, yet **you should not assume audience is always checked properly for your API**. Configure an audience validator or equivalent policy for your Security/Boot version. This is a security design requirement, not optional for multi-audience APIs.

A valid JWT **does not equal** valid admin permissions. A JWT allowing a user to browse products must not automatically grant admin rights merely because the caller knows the `/api/admin/**` URL.

### JWT Scopes vs. Identity Provider Roles

Example policy using:

~~~java
.pathMatchers("/api/admin/**")
    .hasAuthority("SCOPE_admin")
~~~

When the IdP issues an access token with `scope: "admin"` and Spring Security's converter maps it to `SCOPE_admin`, the rule allows it. However, if the IdP only uses a `roles: ["ADMIN"]` or `realm_access.roles` claim in its own format, **you must write/configure an appropriate authority converter**. Never assume `hasRole("ADMIN")` automatically picks up arbitrary role claims in the token.

**Principle of least privilege:** Overly broad tokens or roles (such as `admin` for everything) amplify the blast radius if leaked. In larger systems, split granular scopes such as `catalog.write`, `reports.read`, or `users.manage`, and pair them with method/path policies and business checks.

## 7. Where Does SecurityWebFilterChain Run Relative to Routes and GatewayFilters?

This is a frequent source of confusion when designing Gateway security:

~~~mermaid
flowchart TD
    C[HTTP request] --> W[WebFlux WebFilter chain]
    W --> S[Spring Security: authentication / authorization]
    S --> Q{Request permitted?}
    Q -->|No| D[401 or 403, no proxy]
    Q -->|Yes| M[RoutePredicateHandlerMapping]
    M --> P{Route predicate matches?}
    P -->|No| NF[No matching Gateway route]
    P -->|Yes| F[FilteringWebHandler]
    F --> GF[Gateway GlobalFilter + route GatewayFilter]
    GF --> U[Upstream service or local forward]
    U --> R[HTTP response to client]
~~~

The diagram presents a **logical view** in WebFlux: **Spring Security WebFilters** run at the WebFlux layer, whereas `GlobalFilter` and `GatewayFilter` execute in the Gateway pipeline **after a route is selected**. A `GlobalFilter` **does not automatically protect all controllers or unrouted requests**, whereas `SecurityWebFilterChain` can cover requests across the application according to its matchers.

### Why Not Use Only a GatewayFilter for Admin Checks?

Suppose you write a `GatewayFilter` on the `administration` route to inspect JWTs. Weaknesses can arise:

1. Another route or dynamic route accidentally forwards requests to the same admin backend **without attaching that filter**.
2. A local WebFlux endpoint or actuator does not go through the admin route, so **the GatewayFilter never runs**.
3. A `Path` predicate has specific conditions while an overlapping fallback route sends requests down a less-protected path.
4. Custom header-parsing logic omits signature, issuer, audience, or expiry checks.

Therefore, **Spring Security WebFlux** is the right place for foundational authentication/authorization policies. `GatewayFilter` remains valuable for rate limiting, header transforms, tracing, or well-scoped supplementary checks; it should not be the sole authorization layer for the entire app.

### Route Predicates and Security Matchers Do Not Necessarily Share Exact Semantics

`Path=/api/admin/**` belongs to **Gateway route predicates**; `pathMatchers("/api/admin/**")` belongs to **Spring Security WebFlux**. Both inspect request paths, yet may differ in parsers, trailing slashes, path parameters, or percent-encoding depending on version. Always test boundary paths, especially:

- `/api/admin` vs. `/api/admin/`.
- `/api/admin/users` vs. `/api/adminusers`.
- Duplicate slashes like `/api/admin//users`.
- Encoded slashes `%2F`, dot segments `..`, double encoding `%252F`.
- Paths already rewritten by an ingress before reaching the Gateway.

**Do not normalize paths one way for security and another way for routing** without verification. One layer seeing a path as public while another decodes it into an admin path can create an authorization bypass.

### RewritePath Runs After Security Decisions on the Input Path

For example, a `Path=/api/admin/**` route with `StripPrefix=2` delivers `/users/42` to the backend. Spring Security at the Gateway evaluates the **public path entering the Gateway**, not waiting for `StripPrefix`. The backend service must apply its own policies to `/users/42` and the identity passed via a trusted mechanism.

## 8. 401, 403, and 404 Codes: Do Not Confuse Their Causes

Error HTTP statuses must match each decision accurately.

| Scenario | Typical Security Outcome | Meaning |
| --- | --- | --- |
| Anonymous hitting `/api/account/profile` | **401 Unauthorized** | Missing valid authentication proof |
| Bearer token with invalid signature/expired | **401 Unauthorized** | Token invalid for authentication |
| User with valid token lacking `SCOPE_admin` hitting admin API | **403 Forbidden** | Authenticated but insufficient permission |
| Admin with valid authority hitting admin API | **Allowed to proceed** | Does not guarantee 200; business logic may still deny |
| No route matches, yet security permits | May be **404** or another handler result | Routing/resource issue, not authentication failure |
| `anyExchange().denyAll()` blocks unknown URL | Rejected at security layer | Final code may depend on authentication/entry point |

A common mistake is returning **403** for all missing-token cases, or **401** when an authenticated user lacks a role. This confusion leaves clients unsure whether to re-authenticate or display "access denied."

### Example 401 with Bearer Challenge

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Cache-Control: no-store
~~~

With OAuth2 Resource Server, **WWW-Authenticate** is an important part of the challenge. Protocol error details may be included; never include real tokens, stack traces, or internal data in responses. For 403, JSON payloads may simply say "insufficient permissions"; avoid publishing detailed internal permission lists.

**Never rewrite statuses with `SetStatus` to "turn" 403 into 200.** Clients might receive HTTP 200 with an error body and misinterpret business outcomes. Authentication failures and access denials should be handled by Spring Security or an error handler keeping status, headers, and body consistent.

### What If a Public Route Receives a Malformed Bearer Token?

`permitAll()` does not mean authentication filters must ignore every presented credential. Depending on configuration, if a client sends an **invalid Bearer token** to a public endpoint, the resource-server authentication filter may return 401 before reaching the `permitAll()` rule. Test both requests **without `Authorization`** and requests **with a broken `Authorization`**; do not silently assume both behave identically.

## 9. Public Login, Token Issuance, and Abuse Prevention

In the `POST /auth/login` route example, the Gateway lets anonymous callers reach the **Identity service**. That **does not mean** the Gateway checks passwords or mints JWTs itself.

~~~mermaid
sequenceDiagram
    participant Client
    participant Gateway as Spring Cloud Gateway
    participant IdP as Identity/Authorization Service
    participant API as Account service
    Client->>Gateway: POST /auth/login (credentials)
    Gateway->>Gateway: Public auth endpoint + rate limit
    Gateway->>IdP: Forward request
    IdP-->>Gateway: Access token (if valid)
    Gateway-->>Client: Token response over HTTPS
    Client->>Gateway: GET /api/account/profile + Bearer token
    Gateway->>Gateway: Validate token + authenticated
    Gateway->>API: Forward allowed request
    API-->>Client: Profile via Gateway
~~~

This **illustrative example** uses a dedicated login API for clarity. Production systems often use standard **OAuth2 Authorization Code + PKCE**, OpenID Connect, and a dedicated Authorization Server instead of building custom username/password endpoints. Flow selection depends on client type, SSO needs, and organizational policy.

Public login endpoints need protection:

- **Mandatory TLS** to avoid sending passwords or tokens in plaintext.
- **Rate limiting by sensible keys** and brute-force/credential-stuffing defenses; do not rely solely on IP behind reverse proxies or shared NATs.
- **Error responses that do not leak** account existence, password state, or secret data.
- **Request/body size limits**, abuse mitigation, safe logging, and anomaly monitoring.
- **Never arbitrarily cache token responses**; enforce cache policies per contract.
- **Never log `Authorization`, passwords, refresh tokens**, cookies, or credential-bearing body fields.
- **Do not accidentally expose** administrative Identity service endpoints via an overly broad `Path=/auth/**` route. Expose only explicitly designed public endpoints.

If supporting self-registration `POST /auth/register`, add **both a dedicated route and a dedicated `permitAll` rule**, with anti-abuse verification. Avoid making `/auth/**` public and inadvertently exposing token-minting/admin endpoints or internal functions.

## 10. Authenticated Routes: Authentication Does Not Equal Resource Permission

Consider:

~~~http
GET /api/account/orders/O-42 HTTP/1.1
Authorization: Bearer eyJ...<redacted>...
~~~

The Gateway can verify the JWT and admit it under `authenticated()`. Still, the crucial question at the Orders/Account service is: **does `O-42` belong to the logged-in user?**

A normal user with a valid token **must not view another user's resources**. The Gateway can perform partial checks based on URI, token, or available metadata; typically it lacks full visibility into data ownership relationships and service business state.

### Layers That Must Work Together

1. **Gateway:** validate the appropriate access token, block anonymous access on private routes, apply rate limiting, and filter basic inputs.
2. **Backend:** verify caller/identity from a trusted source, check specific resource permissions, tenant boundaries, and business policies.
3. **Data layer:** constrain queries by subject/tenant or ownership bindings; never look up a record solely by ID and return it.
4. **Audit:** record subject, action type, and outcome safely without exposing tokens or sensitive personal data.

Using `authenticated()` is the minimum baseline for this group. When APIs support multiple operation types, add specific authorities/permissions: `account.read`, `orders.write`, per-object rights, or equivalent system scopes.

### Avoid Trusting Self-Declared X-User-Id

Never use a client-sent header like `X-User-Id: user-742` as proof of an authenticated caller. If the architecture requires passing identity downstream, derive it from **verified authentication**, protect the backend hop, and strip any client-spoofable headers of the same name. Better yet, have the backend verify the token itself or an internal token scoped by audience/permissions.

## 11. Admin Routes: Protection Beyond a Single hasAuthority Rule

An admin API can change product prices, grant staff permissions, read reports, or operate the platform. Given the high impact, enforce stronger safeguards than standard authenticated routes.

**Appropriate defense layers:**

| Layer | Example |
| --- | --- |
| Strong authentication | Token from trusted IdP, MFA/step-up when needed |
| Authorization | Dedicated admin scopes/authorities and action-specific permissions |
| Network | Admin hostname/VPN/Zero Trust gateway or allowlist where appropriate, not replacing tokens |
| Backend | Re-verify business action permissions and resource access |
| Audit | Record who did what, when, and outcome; protect log integrity |
| Anti-abuse | Rate limiting, automation controls, and anomaly alerts |
| Session/token | Appropriate lifetime, revocation, audience, rotation, and device policies |
| High-risk changes | Separation of duties, confirmation, or approval workflows if required |

If the system uses `ROLE_ADMIN` instead of scopes, rules can use `hasRole("ADMIN")` **only when** authentication genuinely contains `ROLE_ADMIN` (per the default `ROLE_` prefix). Mapping between IdP roles and Spring Security authorities must be defined and tested. Never read roles straight from JSON bodies or request headers.

### Admin Hostname Does Not Replace Permission Checks

Consider a route with `Host=admin.example.test`. The `Host` header can be client-controlled in many scenarios; DNS or host separation does not prove the caller is an admin. When using an admin host, still require tokens/authorities, enforce TLS, and control ingress/virtual hosts. Also verify no other route exposes the same admin backend over a public host.

### Do Not Treat Business Admin Rights as Management Plane Rights

Business administration such as `/api/admin/products` differs from **Spring Boot Actuator**, infrastructure config, route refresh, metrics, environment, or heap dumps. Even a user holding business `SCOPE_admin` must not automatically read secrets or modify Gateway runtime state. The management plane requires separate protection—usually isolated ports/networks/permissions and minimal exposed endpoints.

## 12. How Are Tokens Passed Down to the Backend?

Authenticating at the Gateway and proxying requests does not automatically answer **how upstream trusts identity**.

### Model A — Forward Bearer Token and Backend Verifies Independently

Client sends:

~~~http
Authorization: Bearer <access-token>
~~~

The Gateway verifies the token; if allowed, the route may forward the `Authorization` header to the backend per system proxy/filter policy. The backend is also a resource server and **re-verifies** the token, audience, issuer, and resource permissions. This clearly defines trust boundaries, provided tokens carry audiences/scopes suited for the receiving service. Avoid minting one token with broad permissions across all services merely for forwarding convenience.

### Model B — Gateway Exchanges Tokens or Emits Internal Identity Signals

In some architectures, the Gateway performs **token exchange/on-behalf-of** or supplies an internal token with restricted audience and scopes. Backends verify internal tokens from a trusted issuer. This model requires protecting signing keys, bounding TTLs, and enforcing service-to-service delegation and identity.

If passing internal identity headers instead of tokens, prevent spoofing by stripping client headers, accepting traffic only via trusted proxies, securing the channel (e.g., mTLS), and verifying payload integrity if required. Adding a plain header without signatures or network boundaries **does not create a trusted identity**.

### TokenRelay Is Not a "Turn On Security" Switch

Spring Cloud Gateway offers the **TokenRelay GatewayFilter Factory** in certain OAuth2 Client setups to pass an authorized client's access token upstream. This differs from a **Gateway Resource Server verifying an incoming Bearer JWT**. Never assume adding `TokenRelay` to a route enables authentication/authorization or protects the backend. It requires the OAuth2 Client dependency, authorized-client context, and a proper token-forwarding policy—alongside audience checks and scope minimization.

### TLS and Discovery Boundaries

Gateway → backend is a separate connection from client → Gateway. Even when public endpoints use HTTPS, the Gateway might talk HTTP to a `ServiceInstance` if configured that way; evaluate TLS/mTLS, truststores, network policies, and token confidentiality on internal hops. **Discovery metadata or `ServiceInstance.isSecure()` does not replace certificate verification**, and clients must never arbitrarily pick internal service IDs.

## 13. CORS and CSRF: Two Concerns Distinct from Route Permissions

For a web app running on `https://shop.example.test` calling an API on `https://api.example.test`, browsers enforce **CORS**. When the frontend sends an `Authorization` header or JSON request, browsers often send a **preflight OPTIONS** before the main request.

Example:

~~~http
OPTIONS /api/account/profile HTTP/1.1
Origin: https://shop.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflight is a cross-origin policy check, **not a GET request to fetch a profile**. It usually carries no Bearer token. If Spring Security demands private-route authentication **before CORS is handled**, browsers receive 401/403 on OPTIONS and block the main request.

**How to handle:** configure CORS at the appropriate layer so valid preflights are processed before authentication/authorization steps, while ensuring actual GET/POST requests still pass through security. Never just write `.pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()` and assume CORS is done; `permitAll` does not generate `Access-Control-Allow-Origin` or validate allowed origins.

### Example CorsConfigurationSource for WebFlux

Within the same WebFlux Security setup, you can define a CORS configuration source:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration cors = new CorsConfiguration();
    cors.setAllowedOrigins(List.of("https://shop.example.test"));
    cors.setAllowedMethods(
            List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
    cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
    cors.setAllowCredentials(false);

    UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", cors);
    return source;
}
~~~

This is an **illustrative bean method**, which must be placed inside a `@Configuration` class and wired into `ServerHttpSecurity.cors(...)` or the reactive CORS mechanism matching your Spring Security version. For example, inside `SecurityWebFilterChain`, you can use `.cors(cors -> cors.configurationSource(corsConfigurationSource()))` where supported. Never copy this into a class lacking imports/wiring and assume CORS turns on automatically.

**Notes:**

- `allowCredentials(false)` is an illustrative choice for cookie-free Bearer token APIs. If using browser cookies/sessions, redesign credentials, SameSite, CSRF, and origin policies.
- Never combine `Access-Control-Allow-Origin: *` with `Access-Control-Allow-Credentials: true`.
- Avoid having both Gateway and upstream emit duplicate/conflicting CORS headers. Pick one policy owner or use controlled header deduplication.
- With origin-specific CORS, mind `Vary: Origin` and proper caching behavior.
- A passing preflight **grants no permission** to the main GET/POST; the main request still needs a valid token and scopes.
- Some Gateway setups rely on a global CORS handler when OPTIONS does not match a `Method=GET` route; test cases where route predicates do not match OPTIONS.

### CSRF Is Not CORS

**CORS** is a browser mechanism governing whether another origin can read responses and send certain cross-origin requests per server policy. **CSRF** concerns requests carrying automatically attached credentials (usually cookies/sessions) that trick browsers into unintended actions.

Therefore:

- Stateless APIs using **client-attached Bearer tokens in Authorization headers** have a different CSRF threat model than cookie-login apps; section 5 disables CSRF **only in that context**.
- If clients use session cookies, refresh-token cookies, or browser-auto-attached credentials, analyze CSRF and protect accordingly; never disable CSRF simply because "JWT is used somewhere."
- CORS never replaces authentication/authorization. Non-browser clients (curl, mobile apps, service-to-service) are not restricted by browser CORS and must still be checked by Spring Security.

## 14. Ordering Multiple SecurityWebFilterChains and Overlapping Routes

For a small Gateway application, one `SecurityWebFilterChain` ending in `anyExchange().denyAll()` is usually easy to reason about. Larger apps may split multiple security chains using `securityMatcher` and `@Order`, e.g., one chain for admin and one for public APIs.

**Key rule:** In Spring Security, **the first chain with a matching matcher** is selected for the request; multiple chains do not stack cumulatively like "public chain plus admin chain." If chain ordering or matchers are wrong, a request may fall into a less restrictive chain or remain unprotected by any chain.

Example ordering mindset:

~~~text
Priority 1: admin paths    -> authenticate + admin authority
Priority 2: account paths  -> authenticate
Priority 3: public paths   -> permitAll
Default: deny
~~~

Do not split into multiple chains without a clear need; a single chain like section 5 lets newcomers see the entire policy at a glance and avoid missed matchers.

### Route Order Differs from Security Rule Order

Spring Cloud Gateway uses `order` to select a route when multiple route predicates match. Spring Security has matcher order and `SecurityWebFilterChain` selection order. **These are separate priority layers.**

| Priority | What It Controls |
| --- | --- |
| `SecurityWebFilterChain` and security matchers | Whether the request is allowed into the application |
| `authorizeExchange` matchers | Which authorization rule applies |
| Gateway route `order` | Which route is selected when multiple predicates match |
| Gateway filter order | Which filter runs earlier/later inside the selected route |

A catch-all route like `Path=/**` can send requests to an unexpected backend. If the matching security policy only covers `/api/account/**` and leaves other URLs public, new endpoints may be exposed accidentally. **Deny-by-default** in WebFlux, combined with bounding route definitions and testing route order, mitigates this risk.

### DiscoveryClient Route Definition Locator and Auto-Exposure

If **auto-generating routes from service discovery** is enabled, the Gateway may gain routes beyond the YAML you directly read. This **does not automatically grant access permissions**, yet can create paths missing from the security matrix. On public Gateways, restrict exposed services and apply default-deny policies to unapproved URLs.

### Internal Endpoints and Fallbacks

A route with a CircuitBreaker fallback using `fallbackUri: forward:/internal/fallback` can invoke an internal handler in the same app. **Do not assume Security WebFilters re-run on every internal forward the exact same way as a fresh HTTP request entering the Gateway.** Protect the entry point, avoid exposing fallback handlers indiscriminately, and never let fallback handlers return sensitive data simply because they received an internal request.

## 15. Anonymous, User, and Admin Test Matrix

Prepare three credential sets in your **test environment**:

- **Anonymous:** send no `Authorization` header.
- **User:** valid access token with matching issuer/audience, **without** `SCOPE_admin`.
- **Admin:** valid access token with matching issuer/audience **and** `SCOPE_admin`.

Include cases for **expired tokens**, **bad signatures**, **wrong audiences**, and **tokens containing a role claim not yet mapped to an authority**.

Assuming backend, discovery, JWT issuer, and security configuration are working properly, expected results at the **Gateway security layer** are:

| Request | Anonymous | Valid User | Valid Admin |
| --- | --- | --- | --- |
| `GET /api/public/products/42` | Allowed | Allowed | Allowed |
| `POST /auth/login` | Allowed | Allowed unless another policy restricts | Allowed unless another policy restricts |
| `GET /api/account/profile` | **401** | Allowed | Allowed via `authenticated` rule |
| `PATCH /api/account/profile` | **401** | Allowed | Allowed via `authenticated` rule |
| `GET /api/admin/reports` | **401** | **403** | Allowed |
| `DELETE /api/admin/products/42` | **401** | **403** | Allowed |
| `GET /api/unknown` | Denied | Denied | Denied |

"**Allowed**" only means security did not block it; the backend may still return 400, 404, 403, 429, 500, or another status per contract. For example, an admin with a valid token may still lack permission to delete every product if the service enforces org/tenant scoping.

### Testing Paths with curl

~~~bash
# Public endpoint, no token needed:
curl -i 'http://localhost:8080/api/public/products/42'

# Private endpoint, no token: expect 401:
curl -i 'http://localhost:8080/api/account/profile'

# Valid user token on private endpoint:
curl -i -H "Authorization: Bearer ${USER_TOKEN}" \
  'http://localhost:8080/api/account/profile'

# User lacking admin authority: expect 403:
curl -i -H "Authorization: Bearer ${USER_TOKEN}" \
  'http://localhost:8080/api/admin/reports'

# Valid admin token: reaches admin service:
curl -i -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  'http://localhost:8080/api/admin/reports'
~~~

`USER_TOKEN` and `ADMIN_TOKEN` are **environment variables set by the tester**, not tokens supplied by this lesson. Never put real tokens in config files, shared shell history, screenshots, or public logs. In TLS-enabled systems, replace `http://localhost` with real **HTTPS** endpoints and never transmit tokens over unprotected networks.

### Boundary Tests to Include

1. Anonymous sends GET to the admin path without trailing slash `/api/admin`.
2. User sends `X-Role: admin` without admin scope; must still be denied.
3. User sends a JWT with `roles: ["ADMIN"]` where the authority converter does not map it to `SCOPE_admin`; verify no unintended privilege escalation.
4. JWT with wrong issuer, wrong audience, or expired; must be blocked before the backend.
5. URLs with double slashes, encoded slashes, trailing slashes, or ingress-rewritten paths.
6. OPTIONS preflight before an authenticated request; verify CORS and then verify the main request.
7. Admin backend called **directly over the network** instead of through the Gateway; must have proper network/authorization protection.
8. Verify newly added routes do not silently become public.

**Do not look only at HTTP 200:** tests must verify which backend receives requests, that blocked requests genuinely **never reach upstream**, and that security responses have consistent status/headers/body.

## 16. Testing with WebTestClient and Backend Stubs

In a WebFlux application, you can use `WebTestClient` against a running Gateway or a properly bound test environment. Illustrative integration test checking anonymous access:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.web.reactive.server.WebTestClient;

class GatewaySecurityHttpTest {

    private final WebTestClient client = WebTestClient.bindToServer()
            .baseUrl("http://localhost:8080")
            .build();

    @Test
    void anonymousCannotReadPrivateProfile() {
        client.get()
                .uri("/api/account/profile")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void anonymousCannotCallAdminApi() {
        client.delete()
                .uri("/api/admin/products/42")
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
~~~

This is an **illustrative snippet**, not immediately standalone runnable: it requires Spring test/JUnit dependencies, a Gateway listening on 8080, security config, and proper test setup. For end-to-end tests, use **backend stubs/spies** to record which requests reach Catalog/Account/Admin. Tests should assert that blocked requests **never reach** the backend, while valid tokens with right scopes actually pass through the Gateway layer.

### Mocking JWTs in Integration Tests

When testing Spring Security WebFlux at the application level, `spring-security-test` provides utilities like `mockJwt()` (with appropriate mock setup) to supply authentication/authorities for tests. That lets you test **authorization rules** without a live IdP.

However, **`mockJwt` does not prove real signature, issuer, audience, or JWKS rotation verification**. Keep another set of integration tests using JWTs signed with valid test keys and a real decoder, or a test IdP environment, to verify bad/expired token paths and trust config.

### Testing Resource Ownership

A test sending only an admin scope is insufficient for backends. Set up two users A and B and an order owned by A; verify:

- A can read A's order with sufficient permissions.
- B is denied access to A's order even with B's valid token.
- Admin can/cannot view that order **strictly per defined policy**, never assuming admin has blanket access.
- No endpoint takes the subject from a client-supplied header instead of verified authentication.

## 17. Diagnosing Common Failures

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| Anonymous reaches admin and gets 200 | Overly broad `permitAll` or `authenticated`, wrong chain order, route bypass | Inspect `SecurityWebFilterChain`, matchers, and backend/network |
| Regular user accesses admin successfully | `/api/**` matches before admin or overly broad authority mapping | Put admin rules first; inspect `Authentication.getAuthorities()` in safe tests |
| Valid admin token gets 403 | JWT has role claim not mapped to `SCOPE_admin` | Align IdP claims, converter, and policy |
| Valid token gets 401 | Wrong issuer, audience, signature, expired, clock skew, or bad JWKS | Inspect JWT validators, trust, and auth errors safely |
| Public endpoint returns 401 when sent a broken token | Bearer auth filter processes invalid credentials | Test with and without `Authorization` separately |
| Browser reports CORS error while curl works | Preflight unhandled, disallowed Origin/headers, or duplicate CORS | Inspect OPTIONS, CORS headers, and Gateway vs. upstream ownership |
| Login POST returns 403 | Wrong CSRF/session policy or mismatched route/security matcher | Clarify cookie vs. Bearer, inspect CSRF and method |
| API returns 404 despite security allowing it | Route unmatched or backend returns 404 | Check route ID and backend response |
| Client adding `X-Role: admin` accesses route | Self-claimed request header trusted as permission proof | Use verified tokens and trusted authorities |
| `/api/admin` behaves differently from `/api/admin/` | Base path uncovered or parser mismatch | Match exact path and descendants, and test |
| Fallback route leaks internal data | `forward:` handler unprotected at entry | Protect entry routes and internal handlers; do not rely on forward re-running security |
| Access token sent to wrong service | `TokenRelay`/Authorization forwarding misaligned with audience | Apply token policy, token exchange, or backend validation |
| Admin API called directly via internal IP | Backend lacks network protection/authorization | Segment network, enforce TLS/mTLS, and authorize at service |
| New endpoint accidentally public | Broad permit rule or uncontrolled auto-discovery routes | Use `anyExchange().denyAll()` and review routes |
| 403 response converted to 200 | Misuse of `SetStatus` or fallback | Preserve status semantics, body, and security |

### Step-by-Step Investigation Sequence

1. **Where did the request arrive?** Check scheme, Host, path, method, and whether ingress modified the URI.
2. **Which chain was selected?** Verify `SecurityWebFilterChain` and security matchers.
3. **Did authentication succeed?** Did the JWT decoder accept signature/issuer/audience/expiration?
4. **What are the authorities?** Did the token map to `SCOPE_admin` or the expected authority?
5. **Which authorize rule won?** Is a broad matcher placed before the admin matcher?
6. **Which Gateway route matched?** Do Path/Method/Host predicates match as expected?
7. **What did the backend receive?** How did token/claims/path/headers cross the trust boundary?
8. **Did business logic deny?** Check resource ownership and service-level policies.
9. **Did auxiliary protections intervene?** Check CORS, CSRF, rate limiter, circuit breaker, retry, or forward handlers.

You do not need to log full Authorization headers or JWT payloads on every request to investigate. Log **route ID, error category, status, normalized authority names, and safe trace IDs** at an appropriate access level; never log access tokens, cookies, or credentials.

## 18. Capstone Lab: Designing a Gateway for Three Access Levels

**Scenario:** A store management platform has Catalog, Account, and Admin services. The Gateway handles route predicates, service discovery integration, filter chains, and edge access control. Backends still enforce business permissions.

### Part A — Contract Design

1. List at least two public endpoints, two authenticated endpoints, and two admin endpoints.
2. For each endpoint, specify method, path, permitted callers, data type, target service, and caching/audit requirements.
3. Isolate `POST /auth/login` into a public route **for that exact method/path only**; do not open all of `/auth/**` without reason.
4. Pick an admin authority matching your real issuer. If using scope `admin`, verify it appears in `Authentication` as `SCOPE_admin`.

### Part B — Implementation

1. Declare four routes equivalent to section 4 using `lb://` or local backend URIs.
2. Add a `SecurityWebFilterChain` similar to section 5; place admin rules before private/public rules and end with `anyExchange().denyAll()`.
3. Configure OAuth2 Resource Server with a trusted issuer and appropriate audience validator.
4. Configure CORS for frontends on allowed Origins; test preflight before requests with Authorization.
5. Add a rate limiter protecting login/public endpoints, and safely log/audit admin actions.
6. Ensure backends cannot be called directly from unprotected network zones.

### Part C — Mandatory Tests

| Test Case | Expected Result |
| --- | --- |
| Anonymous GET public | Forwarded to Catalog if route/backend are valid |
| Anonymous GET account | 401 at security layer |
| Anonymous DELETE admin | 401 at security layer |
| User GET account | Passes Gateway; backend checks resource permissions |
| User DELETE admin | 403 and **does not reach Admin service** |
| Admin DELETE admin | Passes security; backend evaluates business policy |
| Invalid signature/issuer/audience token | Denied access to private/admin resources |
| `X-Role: admin` header from user | Does not alter actual permissions |
| Browser OPTIONS preflight | Handled per CORS policy; main GET/POST still require valid tokens |
| URL with encoded/trailing slashes | No path representation bypasses authorization |
| New route without rules | Denied by default policy |
| Direct backend access | Protected by network/backend authorization |

### Part D — Failure Review

1. **Intentional bug:** Move `.pathMatchers("/api/**").permitAll()` to the top. In a test environment, observe the impact and revert immediately. Never deploy this intentional vulnerability.
2. **Wrong authority mapping:** Issue a token with a role claim lacking the matching admin authority; verify it cannot enter admin.
3. **Wrong route order:** Add a `Path=/**` route in a test environment to see why routing must never substitute for authorization.
4. **TokenRelay and audience:** Test a backend accepting only its specific audience; verify tokens with other audiences are not blindly forwarded.
5. **CORS/session:** If cookies are used, re-evaluate CSRF, SameSite, and CORS credentials before permitting login/data mutations.

**Completion criteria:** Enforced permission matrix; anonymous blocked from private/admin; users without admin authority receive 403; authorized admins reach the right route while the backend still checks resources; default deny, CORS preflight, and path variants tested; no tokens logged and management plane not exposed.

## 19. Operational Governance and Future Changes

A security policy that is correct today can break when another team adds routes or changes APIs:

- **Review routes and policies in the same change:** adding `/api/admin/reports/export` requires an owner, auth method, authority, and matching tests.
- **Consistent URL planning:** avoid overlapping public/private prefixes or rewrites that create alternate paths to the same sensitive backend.
- **Protect secrets/JWKS/issuer:** govern key rotation, truststores, token validity, and IdP revocation/rotation workflows.
- **Monitor failures:** track abnormal 401/403 spikes, token decode errors, missing instances, rate-limit responses, latency, and upstream failures **separately**.
- **Audit admin actions:** record principal, action, resource, and outcome in access-controlled storage; avoid logging tokens, passwords, or excessive personal data.
- **Defense in depth:** if the Gateway is misconfigured or another path reaches internal services, backends still check permissions and networks still restrict connections.
- **Periodically re-verify CORS, CSRF, and paths:** changes to browser clients, ingress, redirects, or path normalization can all affect security.
- **Never trade security to fix ops issues:** never disable JWT validation, TLS hostname verification, or widen `permitAll` just to clear 401/403 errors.

## 20. Summary

- **Route predicates select targets; Spring Security handles authentication and authorization.** Never use `Header=X-Role, admin` or `Host=admin...` as proof of permission.
- Design three clear tiers: **public** uses controlled `permitAll()`; **private** requires `authenticated()`; **admin** requires a trusted authority such as `SCOPE_admin` when mapped properly.
- Use `SecurityWebFilterChain` for Gateway Server WebFlux, place **specific rules before broad rules**, and finish with `anyExchange().denyAll()` so new endpoints are not public by default.
- **JWTs must be verified thoroughly**: signature, issuer, lifetime, audience, and matching permissions. A valid access token does not mean the caller can do everything; the backend must still verify resource/tenant access.
- **401** usually means valid authentication is required; **403** means authenticated but lacking permission. Do not invert statuses via response filters or improper fallbacks.
- **CORS preflight, CSRF, token relay, URL rewriting, forwarded headers, and route order** affect access boundaries but never replace security policies.
- Admin APIs need **layered protection**: proper tokens/roles or scopes, MFA when needed, network/TLS/mTLS, backend authorization, rate limits, auditing, and an isolated management plane.
- Only consider the design successful after testing **anonymous, user, admin, invalid tokens, preflight, path variants, and direct backend access**, while observing requests per route without leaking credentials.
