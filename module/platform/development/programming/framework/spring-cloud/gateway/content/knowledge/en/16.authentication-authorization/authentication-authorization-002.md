# Integrating Spring Security with SecurityWebFilterChain in Spring Cloud Gateway

An API Gateway is often the common entry point for multiple microservices. If the Gateway routes requests properly but fails to authenticate callers or control access permissions, a public URL can become a direct path to internal data. With **SPRING_CLOUD_GATEWAY** running on **Spring WebFlux**, the key foundation for protecting HTTP requests is **reactive Spring Security**, configured via **`SecurityWebFilterChain`** and **`ServerHttpSecurity`**.

This lesson belongs to the **Authentication and Authorization** chapter, focusing on how to integrate Spring Security into Gateway Server WebFlux: structuring the security chain before route matching, validating JWTs using the OAuth2 Resource Server model, authorizing by public path and HTTP method, handling `401`/`403` status codes, coordinating CORS/CSRF, and forwarding identity information safely to downstream services. The examples connect with route predicates, filter chains, path/header transformations, service discovery, rate limiting, circuit breakers, retries, TLS, and request observability, though **each group of capabilities requires its own policy**.

> **Scope:** examples target **Spring Cloud Gateway Server WebFlux** and reactive Spring Security using common Spring Security 6.x / Spring Boot 3.x configuration patterns. Starter names, Gateway namespaces, and DSLs may vary across other release trains. **Gateway Server MVC uses Servlet security (`SecurityFilterChain` / `HttpSecurity`) and does not directly use the `SecurityWebFilterChain` code below.** Consult the documentation for your specific release train before applying.

## 1. Three Different Questions: Routing, Authentication, and Authorization

Suppose a client sends:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

The Gateway must resolve three distinct questions:

| Question | Typical Component | Meaning |
|---|---|---|
| Which service should the request go to? | `RoutePredicateHandlerMapping`, `Route`, `Path`/`Method` predicates | **Routing**: select downstream target and gateway filters |
| Who is calling the API? | Spring Security `AuthenticationWebFilter` / OAuth2 Resource Server | **Authentication**: verify token/credentials and build `Authentication` |
| What is this caller allowed to do? | `SecurityWebFilterChain`, `authorizeExchange`, and backend policy | **Authorization**: decide whether the operation is permitted |

**A matching route does not mean the request is permitted.** Conversely, a valid access token does not guarantee the request matches a route or that the backend can serve it.

For example:
- A valid JWT with the `orders.read` permission can read `GET /api/orders/42`.
- The same JWT is not necessarily allowed to `POST /api/orders`, because that is a write action.
- A valid JWT for a nonexistent `/api/unknown` route does not invent a new route.
- A request without a JWT can be rejected at the security layer **before the Gateway looks up a route**.

### High-Level Architecture Diagram

~~~mermaid
flowchart TD
    C["Client: HTTP request"] --> W["Spring WebFlux WebFilter chain"]
    W --> SEC{"Spring Security: authentication and authorization"}
    SEC -->|Missing / invalid token| U["401 Unauthorized"]
    SEC -->|Authenticated but insufficient permissions| F["403 Forbidden"]
    SEC -->|Allowed| HM["Gateway: RoutePredicateHandlerMapping"]
    HM -->|No matching route| N["No matching route / handler"]
    HM -->|Matched| GF["FilteringWebHandler: GlobalFilter + GatewayFilter"]
    GF --> RW["RewritePath / Headers / Rate limit / Circuit breaker"]
    RW --> LB["Routing: static URI or lb://service-id"]
    LB --> DS["Downstream checks business permissions"]
    DS --> R["Response back to Gateway and client"]
~~~

The diagram illustrates the conceptual architecture. Spring Security's `WebFilter` operates at the WebFlux HTTP layer, whereas `GatewayFilter` only participates once a Gateway route has been selected. Mechanisms such as CORS or error handling may intervene earlier at their respective layers.

## 2. Why Does Gateway WebFlux Need SecurityWebFilterChain?

In Spring Security, there are two easily confused API families:

| Web stack | Security configuration | Core APIs |
|---|---|---|
| **Reactive WebFlux** | `SecurityWebFilterChain` | `ServerHttpSecurity`, `WebFilter`, Reactor `Mono`/`Flux` |
| **Servlet / Spring MVC** | `SecurityFilterChain` | `HttpSecurity`, Servlet `Filter` |

Spring Cloud Gateway **Server WebFlux** uses an asynchronous, non-blocking architecture. Therefore:

- Define a `SecurityWebFilterChain` bean, not a Servlet `SecurityFilterChain` bean.
- Use `ServerHttpSecurity` to define matchers, authentication, and authorization.
- When handling security information in custom code, use reactive APIs and Reactor Context; do not assume the principal lives in a servlet thread's `ThreadLocal`.
- Avoid calling `block()` inside reactive security/filter chains; blocking operations can stall the event loop or increase latency.

A typical WebFlux application may have multiple `WebFilter` instances, with Spring Security organizing its filters inside `SecurityWebFilterChain`. These filters protect requests **before** they reach Gateway handlers/routing according to the security configuration.

### SecurityWebFilterChain vs. GatewayFilterChain

| Characteristic | `SecurityWebFilterChain` | `GatewayFilterChain` |
|---|---|---|
| Belongs to library | Reactive Spring Security | Spring Cloud Gateway |
| Configuration entry point | `ServerHttpSecurity` and security matchers | Route `GlobalFilter` / `GatewayFilter` |
| Scope | HTTP requests matching the security chain, even if no Gateway route matches | Requests with a selected Gateway route |
| Role | Authentication, authorization, security handling | Request/response transformation, routing, resilience |
| Included automatically when only declaring YAML routes? | Requires appropriate Spring Security dependency/configuration | Included in Gateway Server WebFlux |

**Dangerous mistake:** adding only a `GatewayFilter` that checks a client-sent `X-User-Role` header and assuming authorization is handled. Incoming headers can be spoofed. Use a security framework to verify trusted identity and policy.

## 3. Required Dependencies

Assume a Maven or Gradle project managed by a compatible **Spring Boot BOM** and **Spring Cloud BOM**.

The typical functional components needed are:

- The **Spring Cloud Gateway Server WebFlux** starter for your release train.
- `spring-boot-starter-security` to enable Spring Security.
- `spring-boot-starter-oauth2-resource-server` to verify Bearer JWTs or tokens under the resource server model.
- If URIs use `lb://`, add the appropriate Spring Cloud LoadBalancer and DiscoveryClient, which are **not dependencies of SecurityWebFilterChain**.

Example Gradle dependencies section (illustrating artifact names for a supported release line):

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway-server-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    // Only needed when routes use lb:// and runtime lacks a load balancer:
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

**Do not arbitrarily pin individual dependency versions** when the project already uses compatible BOMs. Gateway starter names have evolved across releases (`spring-cloud-starter-gateway` also appears in older docs), so check the artifact and release train for your project. Do not add `spring-boot-starter-web` (Servlet) just to "enable Spring Security" in a Gateway WebFlux application.

## 4. Configuring a SecurityWebFilterChain for a Bearer JWT API

Suppose the Gateway exposes three endpoint groups:

- `GET /api/orders/**` requires the `SCOPE_orders.read` authority.
- `POST /api/orders/**` requires the `SCOPE_orders.write` authority.
- `/api/admin/**` requires the `SCOPE_admin` authority.
- `/actuator/health` is publicly readable under the example policy; other management endpoints are not open by default.

This is an **illustrative policy**, not a built-in default scope set in Spring or OAuth2.

~~~java
package example.gateway.security;

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
            // Only appropriate if this API is stateless Bearer-token
            // and does not rely on session cookies for authentication.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)

            .authorizeExchange(exchanges -> exchanges
                // Only lets OPTIONS requests pass the authorization step;
                // proper CORS configuration is still required at the appropriate layer.
                .pathMatchers(HttpMethod.OPTIONS, "/api/**").permitAll()

                .pathMatchers("/actuator/health").permitAll()

                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")

                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")

                .pathMatchers("/api/admin/**")
                    .hasAuthority("SCOPE_admin")

                // Fail closed: new routes do not automatically receive access.
                .anyExchange().denyAll()
            )

            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

### Reading Each Section

1. `@EnableWebFluxSecurity` enables Spring Security for WebFlux in this Java config setup.
2. `@Bean SecurityWebFilterChain` provides rules for the reactive security pipeline.
3. `authorizeExchange` declares rules **against the request path and method received by the Gateway**, not the path after `StripPrefix`.
4. `hasAuthority("SCOPE_orders.read")` requires an authority established during authentication. With a Bearer JWT resource server and Spring Security's default scope mapping, the `orders.read` scope is typically represented as `SCOPE_orders.read`.
5. `anyExchange().denyAll()` **denies by default** for undeclared paths/methods. If the project requires another policy, decide explicitly and test it.
6. `oauth2ResourceServer(...jwt(...))` enables Bearer JWT validation via the auto-configured or application-defined `ReactiveJwtDecoder`.

**Note on `denyAll()`:** a request not permitted by policy can receive `401` or `403` at the security layer **before the Gateway even determines whether a route exists**. If you want public URLs to return `404` according to routing, design public/security matchers clearly. Do not use global `permitAll()` just to "get clean 404 codes."

### CSRF Is a Decision Based on the Authentication Model

The `.csrf(ServerHttpSecurity.CsrfSpec::disable)` line in the example **is only valid when the Gateway truly operates a stateless API using Bearer tokens in headers, without relying on browser-attached credentials such as session cookies**. If the application uses `oauth2Login`, form login, session cookies, or capabilities needing CSRF protection, **do not copy disabling CSRF**; configure appropriate protection and test every flow.

## 5. Configuring Where JWTs Are Verified

An OAuth2 Resource Server needs to know how to verify token signatures and claims. Spring Boot example:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
~~~

`issuer-uri` must match the **real issuer** of the Identity Provider, and the provider must expose suitable metadata/JWKs so Spring Security can verify JWTs. The domain here is purely illustrative: this configuration **cannot run without a real Identity Provider**.

When using an OAuth2 resource server with JWT, the typical steps are:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Spring Security at Gateway
    participant IDP as Identity Provider / JWKS
    participant G as Gateway route filters
    participant B as Backend
    C->>S: Authorization: Bearer access-token
    S->>IDP: Fetch metadata/JWKs when needed (cached per implementation)
    IDP-->>S: Public keys / metadata
    S->>S: Verify signature, lifetime, issuer, and validators
    S->>S: Convert claims/scopes to Authentication and authorities
    alt Authentication fails
        S-->>C: 401
    else Insufficient authority
        S-->>C: 403
    else Permitted
        S->>G: Pass to Gateway handler/filters
        G->>B: Forward request per policy
        B-->>C: Response via Gateway
    end
~~~

The diagram **does not mean every request calls the Identity Provider**: fetching/caching public keys and metadata depends on the decoder and configuration. JWTs can be verified locally using known public keys. Never issue a remote HTTP call per JWT just from reading the diagram.

### Which Claims Are Checked?

| Field | Role | Notes |
|---|---|---|
| **Signature** | Prevents token tampering | Must be verified with a trusted algorithm/key |
| `exp` | Expiration time | Expired JWTs must be rejected by the appropriate validator |
| `nbf` | Not valid before timestamp | Depends on validator/presence of claim |
| `iss` | Issuer | Must match trusted issuer |
| `aud` | Intended token audience | **Do not assume it is already checked for your API**; add audience validation when required |
| `scope` or `scp` | Permission scopes | Can map to `SCOPE_...` authorities per default converter |
| `sub` | Principal identifier | Does not prove permission to read all data of another user |

**A properly signed token does not equate to sufficient permissions.** A JWT with a valid `iss` whose `aud` targets another API may still be unsuitable for this Gateway. If the contract requires a specific audience, configure `ReactiveJwtDecoder` with validators for `aud` and test tokens with wrong audiences.

**Do not hardcode secret keys/real JWTs in YAML or logs.** With asymmetric JWTs, the backend/Gateway typically uses public keys from a trusted JWK Set; the system needs policies for key rotation, caching, clock skew, and TLS to the Identity Provider.

### How Does Scope-Based vs. Role-Based Authorization Differ?

By default, a JWT resource server can convert a scope like `orders.read` into `SCOPE_orders.read`. However, if the Identity Provider puts roles into a custom claim like `realm_access.roles` or `roles`, you usually need an **appropriate converter** to map them into authorities used by `hasAuthority`. Do not assume Spring Security reads every role claim automatically.

Comparison:

~~~text
JWT scope: "orders.read orders.write"
 -> authorities (per default scope mapping):
    SCOPE_orders.read
    SCOPE_orders.write

JWT roles: ["ADMIN"]
 -> does not necessarily auto-generate ROLE_ADMIN
    without a matching converter
~~~

In addition, `hasRole("ADMIN")` typically works with the `ROLE_ADMIN` authority convention, whereas `hasAuthority("SCOPE_admin")` checks for the **exact** authority named `SCOPE_admin`. The two forms are **not equivalent**.

## 6. Route Predicates and Security Rules: Which Order Is Checked?

Suppose a route is configured:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-api
          uri: http://localhost:9090
          predicates:
            - Path=/api/orders/**
            - Method=GET
          filters:
            - StripPrefix=1
            - SetRequestHeader=X-Edge-Service,orders
~~~

Under the policy in section 4, a `GET /api/orders/42` request follows this logical sequence:

1. Spring Security verifies the Bearer token and `SCOPE_orders.read` authority against the **public path `/api/orders/42`**.
2. If security fails, the request is rejected; the backend is not called.
3. If security passes, the Gateway selects `orders-api` via `Path` and `Method`.
4. The `StripPrefix=1` filter rewrites `/api/orders/42` to `/orders/42`.
5. The `X-Edge-Service: orders` header is set on the forwarded request.
6. The backend receives the request and still needs to check business permissions (e.g., whether order 42 belongs to the user).

**Do not write security rules for `/orders/42` just because `StripPrefix` produces that URL downstream.** Security matchers at the Gateway inspect the path **before** rewrite filters run.

### Rule Ordering Inside authorizeExchange

Specific rules should come **before** catch-all rules:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/public/**").permitAll()
    .pathMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyExchange().denyAll()
)
~~~

If you place `anyExchange().permitAll()` or an overly broad matcher before specific protective rules, the specific rules may never be evaluated. Do not treat a `Gateway RoutePredicate` with the same path as a substitute for defining this security rule.

## 7. HTTP 401, 403, and Commonly Misdiagnosed Responses

**401 Unauthorized** typically occurs when a request requires authentication but **lacks valid credentials**: missing Bearer token, expired token, invalid signature, wrong issuer, or unparseable token.

**403 Forbidden** typically occurs when the principal is authenticated but **lacks sufficient authority** for the operation, or when a policy explicitly denies access.

| Request to Gateway | Expected security outcome in demo policy | Backend called? |
|---|---|---|
| GET `/api/orders/42` without token | `401` | No |
| GET `/api/orders/42` with malformed JWT | `401` | No |
| GET `/api/orders/42` valid JWT with only `SCOPE_orders.write` | `403` | No |
| GET `/api/orders/42` JWT with `SCOPE_orders.read` | Passes security; further result depends on route/backend | Yes if route matches and routing succeeds |
| POST `/api/orders/42` JWT with only `SCOPE_orders.read` | `403` | No |
| POST `/api/orders/42` JWT with `SCOPE_orders.write` | Passes security; but demo route only allows `Method=GET` | Not via demo route; may return 404 |
| GET `/api/unknown` with valid JWT | `403` due to demo policy's `denyAll` | No |

**This table describes the example's specific policy**, not a universal rule that every Gateway must return those exact codes in all cases. In particular, CSRF, CORS, custom exception handlers, route fallbacks, and error handlers can alter actual behavior.

When a token is invalid, Spring Security may add `WWW-Authenticate` per Bearer token error handling. Do not strip this header mechanically with `RemoveResponseHeader`, as it helps HTTP clients understand authentication requirements.

### Why Not Convert Every Error to 200?

A Gateway filter rewriting status codes to `200` to bypass CORS/error handling makes the frontend think an operation succeeded, breaks tracing, and hides security errors. Keep meaningful HTTP status codes, use consistent error payloads, and manage CORS headers on error responses as well.

## 8. CORS Preflight in a Gateway with Spring Security

A browser from `https://app.example.test` sending a POST with `Authorization` may begin with:

~~~http
OPTIONS /api/orders/42 HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

**Preflight requests typically do not carry a Bearer token like the actual request.** If Spring Security requires a token for OPTIONS before CORS processing handles the preflight, the frontend can receive `401/403` and report a CORS error.

In the Java example, the rule:

~~~java
.pathMatchers(HttpMethod.OPTIONS, "/api/**").permitAll()
~~~

lets API OPTIONS requests pass the **authorization** step, but **does not itself generate `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, or `Access-Control-Allow-Headers`**. You must still configure CORS in WebFlux/Gateway and coordinate how Spring Security handles preflight.

Example global CORS in Gateway Server WebFlux (using the namespace for your version):

~~~yaml
spring:
  cloud:
    gateway:
      globalcors:
        add-to-simple-url-handler-mapping: true
        cors-configurations:
          '[/**]':
            allowedOrigins:
              - https://app.example.test
            allowedMethods:
              - GET
              - POST
              - OPTIONS
            allowedHeaders:
              - Authorization
              - Content-Type
            exposedHeaders:
              - X-Request-Id
~~~

`add-to-simple-url-handler-mapping` helps when an OPTIONS preflight does not match a route's `Method=POST`. However, if a Security `WebFilter` blocks the request before the CORS handler resolves it, you still need version-appropriate Spring Security CORS integration (such as `CorsWebFilter`/reactive CORS configuration). **Do not create two conflicting CORS policies** and rely on a deduplication filter to mask duplicate headers.

CORS only governs interactions between **browser origins** and responses. It **does not verify JWTs** and does not prevent non-browser HTTP clients from calling the API. For cookie-based apps, address `allowCredentials`, `SameSite`, `Secure`, and CSRF per your threat model.

## 9. Token Propagation: Checking the JWT at the Gateway Does Not End the Security Problem

There are two common models when the Gateway forwards requests downstream.

### Model A: Gateway Authenticates, Downstream Still Verifies Independently

The Gateway uses Spring Security JWT Resource Server. Downstream is also a resource server or has a trusted verification mechanism and checks tokens/claims per its own policy.

Advantages:
- Downstream does not have to blindly trust a header that a client could spoof.
- If a request arrives via a network path bypassing the Gateway, the backend still has a protection layer.
- The backend enforces business permissions such as `order.ownerId == authenticatedUser`.

Note: you must know **whether the Authorization header is forwarded or stripped by filters/proxies**. Some Gateway configurations forward remaining headers, but that does not replace designing token propagation and downstream security.

### Model B: Gateway Authenticates, Downstream Receives Internal Identity

In some architectures, the Gateway/edge handles authentication and forwards a verified identity representation to trusted services. That requires a **strong trust boundary**:

- Prevent external clients from calling the backend directly.
- Strip client-supplied identity headers such as `X-Authenticated-User` and `X-User-Role` **before** attaching values from the verified security context.
- Protect the Gateway → backend hop with a private network and TLS/mTLS or required service-to-service authentication.
- Define exactly which fields downstream trusts and which permissions it must still check itself.

**Do not do this:**

~~~yaml
filters:
  - SetRequestHeader=X-Authenticated-User,admin
~~~

A static `admin` header does not come from authentication results; it can trick downstream into treating every caller as an administrator.

### TokenRelay Does Not Mean JWT Resource Server

In Spring Cloud Gateway, the **TokenRelay GatewayFilter Factory** relates to forwarding access tokens in appropriate OAuth2 client/authorized client flows; it requires matching integration and configuration. Simply enabling a JWT resource server **does not mean** TokenRelay is automatically added to every route, nor does it mean incoming request tokens should always be forwarded verbatim to all downstream services.

Token-forwarding decisions must account for audience, least-privilege scopes, token exchange/on-behalf-of where appropriate, confidentiality, TTL, and backend purpose. Never forward a JWT intended for one API to a service with a different audience without verifying the authentication contract.

## 10. Reactive Security Context and Custom Filters

When writing WebFlux code, authentication information travels in the **reactive subscriber context**; you should not rely on the same Java thread handling a request from start to finish.

In an appropriate filter/handler, you can access the principal through `ServerWebExchange`:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

Mono<String> authenticatedName(ServerWebExchange exchange) {
    return exchange.getPrincipal()
        .cast(Authentication.class)
        .filter(Authentication::isAuthenticated)
        .map(Authentication::getName);
}
~~~

**This is an example of reading identity in a reactive application**, not a complete policy snippet. The `Mono` may be empty if the request has no principal; `isAuthenticated` does not by itself represent the permission level required by an API. In real custom filters, explicitly handle missing principals, anonymous authentication, and different principal types if the environment supports multiple login mechanisms.

If you need specific JWT details, use an appropriate `Authentication` type such as `JwtAuthenticationToken` after verification; never split the `Authorization` string on dots manually and trust unverified claims.

Avoid:
- Calling `SecurityContextHolder.getContext()` in a reactive callback assuming the context is always bound to the current thread.
- Calling remote services with blocking APIs on the Netty event loop.
- Copying client-supplied role/tenant headers and skipping verification.
- Logging full access tokens, refresh tokens, session cookies, or secrets.

**Prefer declarative policies in `authorizeExchange`** for clear rules. Only use a custom `ReactiveAuthorizationManager` when complex checks require a trusted data source, along with proper timeouts, cancellation, and error handling.

## 11. Multiple SecurityWebFilterChains and Matcher Ordering

A Gateway may need separate policies for public APIs, management endpoints, and OAuth2 login. Reactive Spring Security supports **multiple `SecurityWebFilterChain` beans**, selecting one chain based on `securityMatcher` and `@Order`.

Example **illustrating the principle**:

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Bean
@Order(1)
SecurityWebFilterChain managementChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(new PathPatternParserServerWebExchangeMatcher("/actuator/**"))
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/actuator/health").permitAll()
            .anyExchange().hasAuthority("SCOPE_ops")
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults())
        )
        .csrf(ServerHttpSecurity.CsrfSpec::disable)
        .build();
}
~~~

Another chain at `@Order(2)` can cover `/api/**` with its own rules. **Do not simultaneously register the chain from section 4 and an additional chain without designing their ordering properly**: verify whether `securityMatcher` patterns overlap, which chain gets selected, and where remaining requests go.

Practical notes:

- `@Order` here controls the order of **selecting a SecurityWebFilterChain**, not Gateway `Route.order`.
- `securityMatcher` limits the scope of the chain. `pathMatchers` inside `authorizeExchange` are **rules within the already-selected chain**; they do not replace chain scoping.
- A chain at `@Order(1)` matching early can prevent an `@Order(2)` chain from ever receiving certain URLs.
- If the management server runs on a **separate port or application context**, Actuator security must also consider port/context boundaries rather than assuming the Gateway's chain covers everything.

In many projects, **a single chain with clear rules** is easier to read. Split into multiple chains only when there are real differences in authentication mechanisms, session policies, or administrative scope.

## 12. Common Pitfalls When Combining Spring Security with Gateway

| Symptom | Cause to Check | Remediation |
|---|---|---|
| Every request returns 401 | Missing/invalid JWT, wrong issuer, missing decoder | Check `issuer-uri`, JWKS, clock, token signature/claims |
| Valid token returns 403 | Missing authority or wrong scope/roles mapping | Check `scope`/`scp`, converter, and `hasAuthority` |
| GET works but POST returns 403 | Method-based rules separate read/write permissions | Issue proper scope; do not reuse read permission for POST |
| Valid token returns 404 | Passed security, route unmatched or backend 404 | Check Route Predicate/`StripPrefix` and downstream |
| New route created but all requests return 403 | `anyExchange().denyAll()` fails closed | Update approved security policy rather than opening all routes |
| Preflight OPTIONS returns 401/403 | Security blocks before CORS processing | Check reactive CORS integration and OPTIONS rules |
| Browser reports CORS error while cURL sees 401 | Error response lacks CORS headers, not solely a JWT issue | Inspect browser Network tab and actual 401 response |
| Security class fails to compile | Confused `HttpSecurity`/Servlet with `ServerHttpSecurity`/WebFlux | Choose the right dependencies and APIs |
| Backend receives different path than security matcher | Gateway filter rewrote the public path | Write security matchers against incoming Gateway paths |
| Backend does not receive token | Header stripped or unclear token-propagation design | Inspect Authorization/header filters and backend trust model |
| Backend trusts wrong role | Uses client/static header instead of auth result | Remove untrusted headers; protect identity in security context |
| Properly signed JWT not meant for this API | Audience not validated as required | Add audience validation and test wrong-audience tokens |
| Actuator exposed to the Internet | Overly permissive security rule or ingress/proxy | Restrict endpoint exposure and admin access at network/security layers |
| Cookie login fails or faces CSRF risk | Copied CSRF disable from stateless example | Design dedicated session, CSRF, SameSite, and CORS policies |
| Some Gateway nodes accept while others reject | Differences in version, issuer config, keys/cache, clock, or policy | Check rollout, clocks, configs, and logs per node |

### Did 401/403 Come from the Gateway or Downstream?

Distinguish by observable signals:

- If Spring Security blocks early, there is usually **no route ID or downstream call**.
- If the Gateway already forwarded the request and the backend returned 401/403, it may be the **backend's security policy**.
- If a rate limiter returns 429 or a circuit breaker returns 503, do not immediately conclude the JWT is invalid.
- If a request matches no route, the error handler may produce a different response than expected by security policy, depending on `anyExchange` rules.

Use structured logs/metrics to correlate route ID, status, security events, backend target, and correlation ID. **Do not log raw Bearer tokens.**

## 13. End-to-End Practice Exercise with JWT and Routes

### Prerequisites

- Gateway Server WebFlux running at `http://localhost:8080`.
- A real Identity Provider at the configured issuer issuing **JWT access tokens** signed with keys trusted by the Gateway.
- An echo/order backend at `http://localhost:9090` accepting `GET /orders/42`; the endpoint is illustrative for the lab.
- The `GatewaySecurityConfiguration` class from section 4 and the route from section 6.
- Use one token with the `orders.read` scope and one authenticated token without that scope; obtain values from an authorized test environment, **never committing real tokens into source code**.

### Step 1 — No JWT

~~~bash
curl -i http://localhost:8080/api/orders/42
~~~

Expect security to require authentication and return **401** per the demo policy, without forwarding to the backend. If you get 404, verify that the security chain actually covers the URL and check handler ordering.

### Step 2 — Invalid JWT

~~~bash
curl -i -H "Authorization: Bearer invalid-token" \
  http://localhost:8080/api/orders/42
~~~

Expect **401** due to an invalid Bearer token; check the status and `WWW-Authenticate` if returned. Never use production tokens in the lab.

### Step 3 — Valid JWT Missing Permission

Use an environment variable holding a token issued specifically for testing:

~~~bash
curl -i -H "Authorization: Bearer <VALID_JWT_WITHOUT_orders.read>" \
  http://localhost:8080/api/orders/42
~~~

The string in angle brackets is only an **illustrative placeholder** that must be replaced with a real test token issued by the Identity Provider. Expect **403** per the example when the token authenticates but lacks the `SCOPE_orders.read` authority.

### Step 4 — Valid JWT with Sufficient Permission

~~~bash
curl -i -H "Authorization: Bearer <VALID_JWT_WITH_orders.read>" \
  http://localhost:8080/api/orders/42
~~~

Security passes; the `orders-api` route matches GET/path, the filter strips `/api`, and the backend receives `GET /orders/42`. The client result may be 2xx or whatever status the backend decides. **A 5xx response does not imply the JWT lacked permission.**

### Step 5 — Different HTTP Method

Use the token that only has `orders.read` to send a POST:

~~~bash
curl -i -X POST \
  -H "Authorization: Bearer <VALID_JWT_WITH_orders.read>" \
  http://localhost:8080/api/orders/42
~~~

Expect **403** due to missing `SCOPE_orders.write`, even before Gateway route matching. Next, try a token with `orders.write`: it passes security, but the demo route only allows `Method=GET`, so it **does not forward via that route**. You may see 404 if no other route/handler matches, illustrating the separation between security and routing.

### Step 6 — Preflight from a Browser

~~~bash
curl -i -X OPTIONS \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization" \
  http://localhost:8080/api/orders/42
~~~

Verify the Gateway returns a proper preflight response when CORS is configured correctly, even though OPTIONS carries no Bearer token. **CORS is not verified by `200` alone**: also check `Access-Control-Allow-Origin`, Allow-Methods, and Allow-Headers.

### Consolidated Test Matrix

| Case | Security Result | Routing Result | What to Confirm |
|---|---|---|---|
| Missing JWT | 401 | Not routed | Backend receives no request |
| Invalid JWT | 401 | Not routed | Token is rejected |
| Valid JWT missing read | 403 | Not routed | Authority mapping is correct |
| Valid JWT with read + GET | Allowed | Matches `orders-api` | Backend path after StripPrefix |
| Valid JWT with read + POST | 403 | Not routed | Rule enforced by HTTP method |
| Valid JWT with write + POST | Allowed | GET-only demo route does not match | Separation of routing and security |
| Valid OPTIONS preflight | Does not require Bearer token on matching branch | May not match route | Valid CORS response |
| Backend unavailable | Allowed if JWT is valid | Routing error | Not confused with auth error |

### Recommended Automated Tests

In a Spring WebFlux project, write integration tests using **`WebTestClient`** and reactive **`spring-security-test`** utilities. When testing security in isolation, mock JWTs with the desired authorities to verify `401`/`403` and path/method authorization; when testing end-to-end, use a test Identity Provider or JWTs signed with test keys to verify the decoder and actual forwarding path.

Do not unit-test only `hasAuthority` rules while ignoring `StripPrefix` routes, stripped auth headers, CORS preflight, or backend object-level denial.

## 14. Operating a Secured Gateway in Production

| Area | What Must Be Designed Beyond SecurityWebFilterChain |
|---|---|
| **Authentication** | Trusted issuer/JWKS, signature, `exp`/`nbf`/`iss`, audience validation when needed, clock sync, and key rotation |
| **Authorization** | Proper source of scopes/roles, least privilege, backend object/tenant permissions, policy when new routes appear |
| **Rate limiting** | Key resolver never trusts client-set headers, quotas per user/client/route, clear HTTP 429 handling |
| **Circuit breaker & retry** | No uncontrolled retries, retry limits, timeouts, idempotency for write operations |
| **Service discovery** | Control routes generated from registry; avoid auto-exposing internal APIs; `lb://` URIs have valid instances |
| **TLS** | HTTPS client → Gateway and Gateway → backend per threat model, certificate trust, mTLS if needed |
| **Request/response headers** | Avoid forwarding unnecessary credentials; manage `Authorization`/`Forwarded`/`X-User-*` per trust boundary |
| **CORS and CSRF** | Clear origin policies; preflight before auth where appropriate; never blindly disable CSRF for cookie apps |
| **Observability** | Metrics for 401/403/429/5xx, traces and audits without exposing tokens/PII; distinguish edge vs. backend errors |
| **Management** | Actuator/gateway management endpoints restricted by network and authentication/authorization |
| **Multiple Gateway instances** | Consistent configs, keys, clocks, security rules, and caches; verified rollout/rollback |

**Defense in depth:** the Gateway is the first checkpoint, but should not be the **sole** place deciding access to sensitive data. The backend must verify resource ownership, tenant isolation, and business constraints that the Gateway lacks sufficient context to know.

## 15. Completion Checklist

- [ ] I selected Gateway **Server WebFlux** and used `SecurityWebFilterChain` with `ServerHttpSecurity`.
- [ ] Gateway/Spring Security/OAuth2 Resource Server dependencies come from compatible release trains.
- [ ] I distinguish routing (`RoutePredicate`) from authentication (`Authentication`) and authorization (`Authorization`).
- [ ] Spring Security protects public URLs **before** Gateway path/header rewrite filters.
- [ ] I use `authorizeExchange` by path/method and an intentional `anyExchange` rule.
- [ ] I verify issuer/JWKS, JWT lifetime, and **audience when required by the API contract**.
- [ ] Scope/role converters match authorities like `SCOPE_orders.read`; I do not confuse `hasRole` and `hasAuthority`.
- [ ] I tested missing token → 401, valid token lacking permission → 403, sufficient permission → routing proceeds.
- [ ] I know unmatched routes and backend failures can yield status codes other than 401/403.
- [ ] I integrated CORS/preflight with Spring Security without opening business API permissions.
- [ ] I only disable CSRF for truly stateless models; cookie/session apps have dedicated policies.
- [ ] I distinguish TokenRelay/OAuth2 client from Resource Server JWT validation.
- [ ] I do not trust self-claimed identity headers or hardcode user/role in a GatewayFilter.
- [ ] The backend still verifies business permissions and cannot easily be bypassed around the Gateway.
- [ ] I treat TLS, rate limiting, retry/circuit breakers, discovery, and Actuator as separate security concerns.
- [ ] I inspect logs/metrics/tracing without exposing access tokens or user data.
- [ ] I tested across multiple Gateway instances and real error paths.

## Official References

- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — `SecurityWebFilterChain`, `ServerHttpSecurity`, and reactive security setup.
- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html) — Bearer JWT verification, issuer, JWKs, and authority mapping.
- [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html) — `authorizeExchange` and endpoint protection.
- [Spring Security — Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html) — coordinating CORS with Spring Security on WebFlux.
- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — route predicate architecture, GatewayFilter chain, TokenRelay, and WebFlux/MVC by version.
- [Spring Framework WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html) — WebFilter, ServerWebExchange, and Reactive Streams.

**Key takeaway:** `SecurityWebFilterChain` is the **reactive HTTP security layer** in front of Gateway routing: the JWT Resource Server authenticates the caller, `authorizeExchange` checks permissions on the **public path/method**, and only then does the Gateway select a route and execute its filter chain. Maintain object-level checks downstream, configure CORS/CSRF to match your model, and never use self-claimed headers or route predicates as substitutes for authorization.
