# authorizeExchange and Authorization Rules for HTTP Exchanges

In a **Spring Security OAuth 2.0/OIDC Resource Server running on Spring WebFlux**, the HTTP protection layer is typically declared using **`ServerHttpSecurity.authorizeExchange(...)`**. This is how you specify which requests are public, which require authentication, which require an OAuth scope or role, and which must be rejected right at the web layer.

Example:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/public/**").permitAll()
    .pathMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .pathMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .anyExchange().denyAll()
)
~~~

Each rule consists of **an HTTP exchange matching condition** and **an authorization decision**. Spring Security evaluates rules in declaration order; the first matching rule wins. This makes matcher order and scope a critical part of the security model.

> **Principle:** `authorizeExchange` defines access policies **at the HTTP exchange boundary**. JWT/opaque access tokens must be authenticated beforehand by Reactive Resource Server components; and even when a scope is valid, permissions on a specific tenant or order still need to be checked at the business layer.

This lesson focuses on **`SecurityWebFilterChain`, `ServerHttpSecurity`, `authorizeExchange`, `pathMatchers`, `matchers`, `anyExchange`, `ReactiveAuthorizationManager<AuthorizationContext>`, and `WebTestClient`**. Examples use **Java 17+, Spring Boot, and Spring Security Reactive/WebFlux**. API names may vary across versions; custom manager examples prefer the Spring Security 6.4+/7.x API with the `authorize(...)` method.

## 1. How Does WebFlux Authorization Differ from Servlet?

Spring Security supports both the Servlet stack and the Reactive WebFlux stack. Both apply the same authentication and authorization concepts, but use different objects and contracts.

| Aspect | Servlet/Spring MVC | Reactive/WebFlux |
|---|---|---|
| HTTP security configuration type | `HttpSecurity` | **`ServerHttpSecurity`** |
| Security chain | `SecurityFilterChain` | **`SecurityWebFilterChain`** |
| Web filter | Servlet `Filter` | Reactive **`WebFilter`** |
| HTTP representation | `HttpServletRequest` / `HttpServletResponse` | **`ServerWebExchange`** |
| Authorization DSL | `authorizeHttpRequests` | **`authorizeExchange`** |
| Path matcher | `requestMatchers` | **`pathMatchers` or `matchers`** |
| Catch-all rule | `anyRequest` | **`anyExchange`** |
| Custom HTTP authorization | `AuthorizationManager<RequestAuthorizationContext>` | **`ReactiveAuthorizationManager<AuthorizationContext>`** |
| JWT decoder | `JwtDecoder` | **`ReactiveJwtDecoder`** |
| Opaque token introspector | `OpaqueTokenIntrospector` | **`ReactiveOpaqueTokenIntrospector`** |
| Security context | `SecurityContextHolder` via Servlet execution model | **Reactor Context / `ReactiveSecurityContextHolder`** |
| HTTP testing | `MockMvc` | **`WebTestClient`** |

**Do not copy** MVC's `SecurityFilterChain`, `requestMatchers()`, and `JwtDecoder` into `ServerHttpSecurity` expecting it to run as WebFlux. Similarly, never call `HttpServletRequest#getSession()` in reactive business code because WebFlux's HTTP request model is `ServerWebExchange`/`ServerHttpRequest`.

### 1.1. What Is an HTTP Exchange?

`ServerWebExchange` represents a single HTTP request-response exchange in WebFlux:

~~~text
ServerWebExchange
    |
    +-- exchange.getRequest()
    |      +-- method, path, headers, cookies, query params
    |
    +-- exchange.getResponse()
    |      +-- status, headers, body
    |
    +-- exchange.getAttributes()
    |
    +-- exchange.getPrincipal()
    |
    +-- exchange.getSession() -> reactive WebSession when needed
~~~

At the authorization layer, Spring Security does not look solely at the URL; it can inspect **HTTP method, path, headers, query parameters, principal, and contextual attributes**, though client-supplied inputs are never proof of authority.

Paths, headers, and query parameters describe **what the client is requesting**. Authority must come from trusted authentication or an authoritative authorization source.

### 1.2. Where Does `authorizeExchange` Sit in the Request Flow?

~~~text
Client:
Authorization: Bearer <access-token>
                |
                v
WebFlux WebFilter chain
                |
                +-- CORS / CSRF / headers / context filters
                |
                +-- AuthenticationWebFilter (Resource Server)
                |      |
                |      +-- ReactiveJwtDecoder or
                |      |   ReactiveOpaqueTokenIntrospector
                |      |
                |      +-- Success: Authentication in Reactor Context
                |      +-- Failure: authentication failure
                |
                +-- AuthorizationWebFilter
                |      |
                |      +-- ServerWebExchangeMatcher?
                |      +-- permitAll/authenticated/hasAuthority/access
                |      |
                |      +-- Grant or Deny
                |
                v
WebFlux handler / Controller / HandlerFunction
                |
                v
Reactive service + object/tenant authorization
                |
                v
Response
~~~

This is a conceptual diagram, not an exhaustive list of every WebFilter or exact ordering across all versions. The key point is that **authentication produces identity/authorities**, while **`authorizeExchange` uses that data to make HTTP authorization decisions**.

## 2. Three Basic Endpoint Types and a Default Rule

In business APIs, endpoints can be categorized as:

| Endpoint Type | WebFlux Rule | HTTP-Layer Condition |
|---|---|---|
| Public | `permitAll()` | No authentication required |
| Authenticated | `authenticated()` | Valid authentication required |
| Specific permission | `hasAuthority("SCOPE_orders.read")` | Exact authority required |
| Specific role | `hasRole("ADMIN")` | Corresponding role required, typically `ROLE_ADMIN` |
| One of several permissions | `hasAnyAuthority(...)` | At least one required authority present |
| Always deny | `denyAll()` | Not permitted |
| Custom logic | `access(customReactiveManager)` | Decision from supplied policy |

Example:

~~~java
.authorizeExchange(exchanges -> exchanges
    // Public
    .pathMatchers(HttpMethod.GET, "/api/public/**").permitAll()

    // Valid token, no specific business scope required yet
    .pathMatchers(HttpMethod.GET, "/api/me").authenticated()

    // Valid token with exact granted scope
    .pathMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .pathMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")

    // Do not expose undeclared exchanges
    .anyExchange().denyAll()
)
~~~

**Common point of confusion:** `authenticated()` is not equivalent to `hasAuthority("SCOPE_orders.read")`; and `permitAll()` does not mean all security WebFilters are bypassed.

### 2.1. `permitAll()` Is Public Authorization, Not Bypassing the Filter Chain

With:

~~~java
.pathMatchers(HttpMethod.GET, "/api/public/catalog")
    .permitAll()
~~~

a request without a bearer token is allowed through. However, if a client sends an **invalid or expired bearer token** to that same public endpoint, the Resource Server authentication filter may reject the token before the exchange reaches `permitAll`.

Example:

~~~http
GET /api/public/catalog HTTP/1.1
Host: api.example.com
~~~

May be allowed through.

~~~http
GET /api/public/catalog HTTP/1.1
Host: api.example.com
Authorization: Bearer invalid-token
~~~

May receive **401** because the client presented an invalid credential. `permitAll` does not instruct the authentication filter to ignore a submitted token.

To test public endpoints properly, include one test **without an Authorization header** and a separate test with an **invalid bearer header**.

### 2.2. `authenticated()` Does Not Check Object Ownership

~~~java
.pathMatchers("/api/me").authenticated()
~~~

is appropriate if the endpoint only reads data for the **current principal**. However:

~~~text
GET /api/users/{userId}/profile
~~~

typically cannot rely on `authenticated()` as its sole protection, because user A could substitute user B's `{userId}`. Object-level authorization is also required.

### 2.3. `hasAuthority()` Checks Exact Authorities

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

requires the exact authority string `SCOPE_orders.read`. If a token only has `SCOPE_orders.write`, it will not pass the read rule. Similarly named scopes, roles, or authorities are not interchangeable.

### 2.4. `hasRole()` Uses Its Own Prefix

~~~java
.hasRole("ORDERS_ADMIN")
~~~

typically requires `ROLE_ORDERS_ADMIN` under the default role prefix. It differs from:

~~~java
.hasAuthority("SCOPE_orders.admin")
~~~

An OAuth scope `orders.admin` **does not automatically become** an application role `ORDERS_ADMIN`, unless the application has an approved and explicitly tested mapping.

## 3. Complete WebFlux JWT Resource Server Configuration

Suppose `orders-api` is protected by bearer JWTs issued by a trusted AS.

### 3.1. Gradle Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Use the **WebFlux starter**, not Servlet MVC security as the basis. If both MVC and WebFlux starters exist in the project, understand how Spring Boot selects the web application type; never assume an app runs reactively simply because a WebFlux dependency is present.

### 3.2. `application.yml`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
~~~

- `issuer-uri` identifies the issuer the Resource Server trusts, matching the `iss` claim.
- `audiences` binds tokens to `orders-api` in Spring Boot versions supporting this property.
- Signature, expiration, key rotation, and token profile must be verified by the decoder and validators.
- An OIDC Client ID token is not an access token for a Resource Server; never substitute an ID token simply because it is also a JWT.

When declaring a custom `ReactiveJwtDecoder`, remember Spring Boot may **back off** from decoder auto-configuration. Issuer, audience, and profile validators must be preserved explicitly per contract; never just decode payloads and trust arbitrary claims.

### 3.3. `SecurityWebFilterChain`

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()

                .pathMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()

                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")

                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")

                .pathMatchers(HttpMethod.PUT, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")

                .pathMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.delete")

                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

`@EnableWebFluxSecurity` is the annotation for Spring Security WebFlux. Spring Boot has auto-configuration mechanisms, but declaring it explicitly distinguishes it from Servlet `@EnableWebSecurity`.

This example intentionally **omits** `.csrf(...disable)` or `.httpBasic(...disable)` to separate orthogonal concerns from the mechanics of `authorizeExchange`. For bearer-only APIs, CSRF, session, CORS, HTTP Basic, and form login policies must be evaluated against the concrete architecture.

### 3.4. Which Rule Applies?

| Method | URL | First Matching Rule | Required Permission |
|---|---|---|---|
| GET | `/api/public/catalog` | Public GET | No token required |
| GET | `/api/me` | Authenticated GET | Valid token |
| GET | `/api/orders` | Orders GET | `SCOPE_orders.read` |
| GET | `/api/orders/1001` | Orders GET | `SCOPE_orders.read` |
| POST | `/api/orders` | Orders POST | `SCOPE_orders.write` |
| PUT | `/api/orders/1001` | Orders PUT | `SCOPE_orders.write` |
| DELETE | `/api/orders/1001` | Orders DELETE | `SCOPE_orders.delete` |
| PATCH | `/api/orders/1001` | `anyExchange` | Denied because no rule matches |
| GET | `/api/unknown` | `anyExchange` | Denied |
| GET | `/management/secrets` | `anyExchange` | Denied |

These are **HTTP authorization** outcomes from the example matchers before controller/service checks. A non-existent endpoint might return 404 in other setups; with a `denyAll` fallback, Spring Security rejects it before checking whether a handler exists.

## 4. `pathMatchers(...)` and Scope of Application

`pathMatchers` is a convenient API for matching paths or HTTP method + path combinations.

~~~java
.pathMatchers("/api/public/**").permitAll()
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.pathMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

These three expressions differ:

1. `/api/public/**` applies to **all HTTP methods** matching the path.
2. `HttpMethod.GET` applies only to **GET** requests on matching paths.
3. `HttpMethod.POST` applies only to **POST** requests.

If a public endpoint is read-only, restrict it with `HttpMethod.GET`. Granting `permitAll` across all methods can accidentally expose a POST or DELETE added later under the same path prefix.

### 4.1. Path Patterns and Path Variables

Example:

~~~java
.pathMatchers(
    HttpMethod.GET,
    "/api/tenants/{tenantId}/orders/{orderId}"
).hasAuthority("SCOPE_orders.read")
~~~

Here `{tenantId}` and `{orderId}` **match the route**. Having `SCOPE_orders.read` alone still does not prove the principal may view a specific order.

When using a custom `ReactiveAuthorizationManager<AuthorizationContext>`, you can read URI template variables via `AuthorizationContext#getVariables()` for matchers that extract variables. If a variable is missing due to matcher or WebFlux routing differences, **fail closed**—never infer permissions from client headers.

### 4.2. Path Normalization, Encoding, and Reverse Proxies

When using matchers in production, verify:

- Does the API configure `spring.webflux.base-path` or gateway path rewrites?
- Which path do matchers see when the request reaches the application?
- Are there trailing slashes or differently encoded path segments?
- Do routing handlers and security matchers handle path variables identically?
- Does a proxy apply a `/gateway` prefix or rewrite `/api`?
- Are there static resources, actuator endpoints, or error routes outside the prefix?

Never assume `"/api/**"` covers every active route if a reverse proxy or handler has different routing configuration. A vulnerability arises whenever a business route falls outside the pattern security developers thought covered it.

### 4.3. `HEAD`, `OPTIONS`, `PATCH`, and Other Methods

Do not test only GET and POST. HTTP allows many methods:

| Method | Scenario | Note |
|---|---|---|
| GET | Read data | Does not imply access to every object |
| HEAD | Fetch headers | May map similarly to GET in handlers, but verify security method matchers |
| POST | Create/action | Needs dedicated scope and CSRF checks when applicable |
| PUT/PATCH | Update | Must not require only read scope |
| DELETE | Delete | Needs delete entitlement and object policy |
| OPTIONS | CORS preflight | Needs CORS configuration; do not mistake for a public business endpoint |
| TRACE | Diagnostic method | Should typically be restricted/denied per server policy |

If you write:

~~~java
.pathMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

every HTTP method matching that path is allowed through with only read scope. If a controller later adds `DELETE /api/orders/{id}`, the broad rule creates an over-privileged access risk.

A safer configuration declares **each method explicitly** with its required scope and ends with `.anyExchange().denyAll()`.

## 5. Rule Ordering Is Part of Security

Spring Security Reactive evaluates rules in `authorizeExchange` **in declaration order**; the first matching rule dictates the policy.

### 5.1. Bad Example: Broad Public Matcher Placed First

~~~java
// WRONG: the first rule shadows the admin rule.
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").permitAll()
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .anyExchange().denyAll()
)
~~~

`/api/admin/users` matches `/api/**` first, so `hasRole("ADMIN")` **is never selected**. Adding a strict rule afterward cannot undo an earlier match.

### 5.2. Fix by Placing Specific Rules First

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/admin/**").hasRole("ADMIN")
    .pathMatchers("/api/public/**").permitAll()
    .pathMatchers("/api/**").authenticated()
    .anyExchange().denyAll()
)
~~~

This is safe **if it is genuinely intended** that all remaining `/api/**` routes require only authentication. If endpoints hold protected data requiring scopes, declare scoped rules before general rules or use `denyAll` as the fallback.

### 5.3. Bad Example: Authenticated Matcher Shadowing Scoped Matchers

~~~java
// WRONG: any valid token can access orders.
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").authenticated()
    .pathMatchers("/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyExchange().denyAll()
)
~~~

`/api/orders/**` is not protected by the scope as intended because `/api/**` matched first.

### 5.4. Maintainable Organization Pattern

~~~text
1. Sensitive / admin exact routes
2. Routes with specific HTTP methods and scopes
3. Authenticated routes requiring no business scope
4. Truly public routes (placed before any broader parent matcher)
5. anyExchange().denyAll()
~~~

Exact ordering depends on your path structure. There is no single rigid order for all systems, but **narrower matchers must precede broader matchers that could cover them**.

## 6. `anyExchange()` and Default Policies

Two common choices:

~~~java
.anyExchange().authenticated()
~~~

and:

~~~java
.anyExchange().denyAll()
~~~

have different consequences.

| Fallback | Unmatched Exchange | Risk |
|---|---|---|
| `authenticated()` | Any valid principal passes the HTTP layer | Newly added sensitive endpoints may be exposed to every authenticated user |
| `denyAll()` | Denied until an explicit rule is added | Config must be updated whenever new endpoints are introduced |
| `permitAll()` | Public by default | Dangerous for APIs handling private data |

**For a Resource Server with multiple scopes**, `anyExchange().denyAll()` is usually a strong fail-closed starting point. New endpoints must be reviewed and given explicit rules.

Still, if an application's policy intentionally states “all remaining endpoints are available to any valid principal”, `authenticated()` is valid once confirmed. Never turn every design decision into a single rigid formula.

### 6.1. Deny-All Does Not Replace Checking Returned Data

A GET endpoint guarded by `SCOPE_orders.read` can still return another user's order if the service skips ownership checks. A `denyAll` fallback only guards **unmatched paths**, not the data scope of allowed paths.

## 7. Combining JWT Access Tokens and Scope-Based Rules

Example JWT access token:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 2000000300
}
~~~

Spring Security Resource Server Reactive typically maps `scope` or `scp` into authorities prefixed with `SCOPE_`.

~~~text
JWT scope:    orders.read
Authority:    SCOPE_orders.read
~~~

Therefore:

~~~java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

lets this token pass the HTTP layer. However:

~~~java
.pathMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

will reject it if the token only contains `orders.read`.

### 7.1. Using `OAuth2ReactiveAuthorizationManagers.hasScope`

Spring Security offers another way to express scope conditions:

~~~java
import static org.springframework.security.oauth2.core.authorization
    .OAuth2ReactiveAuthorizationManagers.hasScope;

// Inside authorizeExchange:
.pathMatchers("/api/orders/**")
    .access(hasScope("orders.read"))
~~~

The snippet wraps the static import across lines for readability; in real Java source, `import static` must be **on a single line**:

~~~java
import static org.springframework.security.oauth2.core.authorization.OAuth2ReactiveAuthorizationManagers.hasScope;
~~~

`hasScope("orders.read")` expresses the unprefixed scope, whereas `hasAuthority("SCOPE_orders.read")` checks the converter-generated authority. Both typically achieve the same goal when the default mapping is intact.

**Never promote a scope to a higher privilege** just to “make the API work”. If a token lacks `orders.write`, obtain proper authorization from the Authorization Server or deny the request.

### 7.2. An Authenticated Token Does Not Automatically Match the Target API

At a Resource Server, JWTs must satisfy the contract for issuer, audience, expiry, key/algorithm, and token type. An ID token issued for OIDC Client login may carry a valid signature yet have the client ID as its audience instead of `orders-api`. Never use ID tokens to satisfy an API's `authenticated()` check.

If using a custom `ReactiveJwtDecoder`, preserve these validators explicitly.

### 7.3. `scope` and Custom Claims Are Not the Same Policy

A token may also contain:

~~~json
{
  "scope": "orders.read",
  "roles": ["orders_manager"],
  "tenant_id": "tenant-a"
}
~~~

Spring Security does not automatically turn `roles` and `tenant_id` into tenant-admin rights. Mapping custom roles requires a trusted authorization source and explicit contract; tenant IDs still require membership/ownership verification.

## 8. Opaque Token Resource Servers Still Use `authorizeExchange`

HTTP authorization rules do not depend on whether tokens are JWT or opaque. The difference lies in **how the token is verified**.

JWT:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults()))
~~~

Opaque:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults()))
~~~

With opaque tokens, Spring Security Reactive uses `ReactiveOpaqueTokenIntrospector` to query a trusted introspection endpoint. When the token is active and scopes match the contract, authorities follow the same `SCOPE_orders.read` format as JWTs.

Example opaque configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: "${INTROSPECTION_CLIENT_SECRET}"
~~~

Never put client secrets in source code or logs. When writing a custom `ReactiveOpaqueTokenIntrospector`, ensure you **never return an authenticated principal for inactive tokens** and never map arbitrary profile attributes into admin authorities.

**In summary:** `authorizeExchange` consumes the `Authentication`/`GrantedAuthority` produced by the reactive authentication pipeline. It does not verify JWT signatures or invoke introspection itself.

## 9. `SecurityWebFilterChain` Is the Scope of `authorizeExchange`

A request must first match a configured **security chain**. With multiple `SecurityWebFilterChain` beans, `securityMatcher` selects the chain, and then `authorizeExchange` selects the rule **inside that chain**.

~~~text
Incoming ServerWebExchange
          |
          v
WebFilterChainProxy
          |
          +-- Select first matching SecurityWebFilterChain
                    |
                    +-- securityMatcher("/api/**")?
                    |
                    v
              authorizeExchange rules
                    |
                    v
              authenticated/authorized?
~~~

### 9.1. Multi-Chain Example

An application has:

- `/api/**`: JWT bearer Resource Server, stateless API.
- `/web/**` and other routes: web login or a separate policy.
- Specific operational/health endpoints intentionally opened.

~~~java
package com.example.shop.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class MultiChainSecurityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/actuator/health").permitAll()
                .anyExchange().denyAll())
            .build();
    }
}
~~~

This is an **example of policy separation** without declaring web login. If an application supports OAuth2/OIDC browser login, the fallback chain must configure login flows, state, CSRF, and callback routes appropriately rather than calling `denyAll()` on everything.

### 9.2. Vital Difference Between the Two Matchers

- `securityMatcher(...)`: does the exchange belong to this **chain**?
- `pathMatchers(...)` inside `authorizeExchange`: which **authorization rule** applies to the exchange within the chain?

If `apiChain` only matches `/api/**`, then `.anyExchange().denyAll()` inside it **does not** protect `/management/**`. Another appropriate chain or fallback must cover it.

### 9.3. When No Chain Matches

In Spring Security, a request matching no `SecurityWebFilterChain` may **skip security WebFilters entirely**. That is a serious configuration hazard.

With multiple chains, verify that all sensitive routes are covered—including error routes, actuators, static assets, WebSocket handshakes if present, and proxied URLs.

### 9.4. `@Order` Priority

`@Order(1)` is evaluated before `@Order(2)`. If a catch-all chain matching every request is ordered ahead of the API chain, the API chain will **never be selected**. Therefore, test chain order as well as rule order.

## 10. `matchers(ServerWebExchangeMatcher)` for Advanced Cases

`pathMatchers` handles most simple cases. When exchanges must be matched on other criteria, Spring Security provides:

~~~java
ServerWebExchangeMatcher
~~~

and the factory:

~~~java
ServerWebExchangeMatchers.pathMatchers(...)
ServerWebExchangeMatchers.anyExchange()
ServerWebExchangeMatchers.matchers(...)
~~~

Example custom matcher for path and HTTP method using the factory:

~~~java
import org.springframework.http.HttpMethod;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatcher;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

ServerWebExchangeMatcher reportsGet =
    ServerWebExchangeMatchers.pathMatchers(
        HttpMethod.GET,
        "/api/reports/**"
    );
~~~

Wiring into the DSL:

~~~java
.authorizeExchange(exchanges -> exchanges
    .matchers(reportsGet)
        .hasAuthority("SCOPE_reports.read")
    .anyExchange().denyAll()
)
~~~

**Custom matchers decide *which requests* a policy applies to**; they do not guarantee the caller is authorized. Client-supplied attributes must still be treated as untrusted targets or inputs.

### 10.1. Matching Headers, Queries, and Protocol Requirements

An organization might apply a distinct policy when a request carries a header identifying the client type, such as:

~~~text
X-Client-Type: mobile
~~~

However, a client-supplied header **is never sufficient to grant roles**. It may select a routing rule, but entitlements must still come from a verified token or an authoritative policy server.

If using headers to adjust privilege checks, evaluate whether callers can spoof those headers. Avoid patterns like:

~~~text
header X-Role=ADMIN -> permitAll
~~~

which constitute privilege escalation.

### 10.2. Path Variables Must Be Checked in Authorization Logic

You can write custom authorization requiring `tenantId`:

~~~java
.pathMatchers(
    HttpMethod.GET,
    "/api/tenants/{tenantId}/orders/**"
).access(tenantPolicyManager)
~~~

`tenantPolicyManager` can read `AuthorizationContext#getVariables()`. However, the tenant name in the URL only identifies **the target resource**, not proof that the user belongs to that tenant.

## 11. Custom ReactiveAuthorizationManager for WebFlux

When policies depend on data beyond authentication—such as tenant membership—the API can use:

~~~java
ReactiveAuthorizationManager<AuthorizationContext>
~~~

which differs from Servlet `AuthorizationManager<RequestAuthorizationContext>`.

### 11.1. Contract

In Spring Security 6.4+/7.x, the abstraction provides:

~~~java
Mono<AuthorizationResult> authorize(
    Mono<Authentication> authentication,
    AuthorizationContext context
);
~~~

This is a simplified signature for explanation. `authentication` is **`Mono<Authentication>`**, not `Supplier<Authentication>` as in modern Servlet examples. `AuthorizationContext` provides access to:

~~~java
context.getExchange();
context.getVariables();
~~~

`AuthorizationDecision` is an implementation of `AuthorizationResult`:

~~~java
new AuthorizationDecision(true)  // allow
new AuthorizationDecision(false) // deny
~~~

In older Spring Security versions, you may see `check(Mono<Authentication>, T)` returning `Mono<AuthorizationDecision>`. According to Javadoc, `check` is deprecated in 6.4+/7.x. Cross-check versions when reading older blog posts.

**Do not return `Mono.empty()` assuming it universally means DENY in every composition.** Empty can mean abstain (no decision), and enforcement/composition has specific semantics. For sensitive permissions, return explicit grant or deny decisions.

### 11.2. Example: Tenant-Scoped Order Read Permission

Requirement:

> Allow `GET /api/tenants/{tenantId}/orders/**` only when the user has scope `orders.read` **and** holds membership permitting reading orders in the requested tenant.

Define the reactive membership source:

~~~java
package com.example.orders.security;

import reactor.core.publisher.Mono;

public interface ReactiveTenantMembershipPolicy {

    Mono<Boolean> canReadOrders(
        String issuer,
        String subject,
        String tenantId
    );
}
~~~

Implementations must query an authoritative source: a reactive repository, non-blocking API, or a properly concurrency-isolated adapter. Returning `true` unconditionally is not a safe implementation.

### 11.3. Custom Manager Without Blocking the Event Loop

~~~java
package com.example.orders.security;

import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public final class TenantOrdersReadAuthorizationManager
        implements ReactiveAuthorizationManager<AuthorizationContext> {

    private final ReactiveTenantMembershipPolicy memberships;

    public TenantOrdersReadAuthorizationManager(
            ReactiveTenantMembershipPolicy memberships) {
        this.memberships = memberships;
    }

    @Override
    public Mono<AuthorizationResult> authorize(
            Mono<Authentication> authentication,
            AuthorizationContext context) {

        Object rawTenant = context.getVariables().get("tenantId");

        if (!(rawTenant instanceof String tenantId)
                || tenantId.isBlank()) {
            return Mono.just(new AuthorizationDecision(false));
        }

        return authentication
            .filter(Authentication::isAuthenticated)
            .ofType(JwtAuthenticationToken.class)
            .flatMap(jwtAuthentication -> {
                boolean hasScope = jwtAuthentication
                    .getAuthorities().stream()
                    .anyMatch(authority -> "SCOPE_orders.read"
                        .equals(authority.getAuthority()));

                if (!hasScope) {
                    return Mono.just(
                        (AuthorizationResult) new AuthorizationDecision(false));
                }

                Jwt jwt = jwtAuthentication.getToken();
                String issuer = jwt.getIssuer() == null
                    ? null : jwt.getIssuer().toString();
                String subject = jwt.getSubject();

                if (issuer == null || subject == null
                        || subject.isBlank()) {
                    return Mono.just(
                        (AuthorizationResult) new AuthorizationDecision(false));
                }

                return memberships
                    .canReadOrders(issuer, subject, tenantId)
                    .defaultIfEmpty(false)
                    .map(allowed ->
                        (AuthorizationResult) new AuthorizationDecision(allowed));
            })
            // No valid authentication -> DENY.
            .defaultIfEmpty(new AuthorizationDecision(false));
    }
}
~~~

This snippet intentionally **never calls `.block()`** and never runs blocking JDBC directly inside `flatMap`. It operates purely on the `Mono` from the reactive policy source.

**What the manager does:**

1. Extracts the tenant ID captured by the path matcher.
2. Denies if tenant ID is missing.
3. Accepts `JwtAuthenticationToken` authenticated by the Resource Server.
4. Checks `SCOPE_orders.read`.
5. Reads `(iss, sub)` from the verified JWT to distinguish identity.
6. Queries the authoritative membership source via `Mono<Boolean>`.
7. Returns an explicit `AuthorizationDecision`.
8. Never derives authorities from headers, queries, email, or display names.

### 11.4. Database / Policy Service Errors

The snippet above lets errors from the membership source **propagate**. If a reactive repository fails, the manager **never returns a grant**; the request is halted. The HTTP response may be 5xx/503 depending on error handling, not necessarily 403.

Some systems convert policy-service failures into denials per fail-closed rules; if doing so, emit clear telemetry so DB outages are not mistaken for unauthorized users.

**Never write:**

~~~java
.onErrorReturn(new AuthorizationDecision(true))
~~~

to “reduce 403 errors” when the database is unavailable. That is fail-open and permits unauthorized actions.

### 11.5. Registering the Manager in `authorizeExchange`

~~~java
@Bean
SecurityWebFilterChain apiChain(
        ServerHttpSecurity http,
        TenantOrdersReadAuthorizationManager tenantRead) {

    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers(
                HttpMethod.GET,
                "/api/tenants/{tenantId}/orders/**")
                .access(tenantRead)

            .pathMatchers(HttpMethod.POST, "/api/orders/**")
                .hasAuthority("SCOPE_orders.write")

            .anyExchange().denyAll()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

This `@Bean` method is an excerpt; imports include `ServerHttpSecurity`, `SecurityWebFilterChain`, `HttpMethod`, `Customizer`, and `Bean`.

Watch the **ordering:** if `.pathMatchers("/api/**").authenticated()` precedes `tenantRead`, the manager will never be invoked for tenant paths matched by the general rule.

### 11.6. Do Not Use the HTTP Manager to Replace Object-Level Authorization

If `tenantId=tenant-a` and `orderId=order-from-tenant-b`, the manager may confirm the subject belongs to tenant A. However, it **does not prove that order ID belongs to tenant A**.

The service layer must query with tenant constraints:

~~~java
// Domain pseudocode: repository implemented by the application.
return orderRepository
    .findByIdAndTenantId(orderId, tenantId)
    .switchIfEmpty(Mono.error(new NotFoundException()))
    .flatMap(order -> orderPolicy.canReadOrder(actor, order)
        .flatMap(allowed -> allowed
            ? Mono.just(order)
            : Mono.error(new AccessDeniedException("Forbidden"))));
~~~

`orderRepository`, `orderPolicy`, `actor`, and `NotFoundException` are illustrative business abstractions, not built-in Spring Security APIs.

If you only validate the request's `tenantId` and query the order by ID without a tenant predicate, the API becomes vulnerable to **Broken Object Level Authorization (BOLA/IDOR)**.

## 12. Never Call Blocking APIs Inside Reactive Authorization

WebFlux uses a reactive execution model. A custom manager containing:

~~~java
// WRONG on the reactive event loop if this is a blocking JDBC call.
boolean allowed = jdbcTemplate.queryForObject(
    "...", Boolean.class);
return Mono.just(new AuthorizationDecision(allowed));
~~~

can **block the event-loop thread**, degrading throughput or causing high tail latency under load.

Options:

- Use R2DBC or a reactive repository where appropriate.
- Use `WebClient` when calling external authorization services over non-blocking HTTP.
- If a blocking SDK is unavoidable, isolate it on an appropriate scheduler via `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` and monitor resource bounds.
- Never call `.block()` to unwrap a `Mono` inside a manager or handler.

Example transitional adapter for a blocking policy:

~~~java
public Mono<Boolean> canReadOrders(
        String issuer, String subject, String tenantId) {
    return Mono.fromCallable(() ->
            blockingMembershipService.canReadOrders(
                issuer, subject, tenantId))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

`blockingMembershipService` is a hypothetical business dependency; import `reactor.core.scheduler.Schedulers`. `boundedElastic` does not turn a blocking library into true non-blocking I/O; it only isolates blocking work from critical reactive threads. Enforce timeouts, connection pools, and load limits.

### 12.1. Reactor Context and Authentication

In WebFlux, authentication is propagated via **Reactor Context**; never assume a `ThreadLocal` remains bound to the request across thread switches.

Example retrieving authentication in a reactive service:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<String> currentPrincipalName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
}
~~~

This demonstrates reading the name, not replacing business authorization checks. Never store principals in static variables across requests.

## 13. Custom WebFilters Do Not Replace `authorizeExchange` in Every Case

Spring Security WebFlux supports custom `WebFilter`s. However, a custom filter that reads headers and returns 403 manually can:

- Run before authentication, lacking a trusted identity.
- Clash with the reactive error-handling flow.
- Bypass configured matchers and authorization managers.
- Duplicate policies and complicate testing.
- Accidentally log bearer tokens or mishandle streaming request bodies.

If the goal is **HTTP authorization rules**, prefer `authorizeExchange` and `.access(ReactiveAuthorizationManager)`.

If the goal is **business transactions/ownership**, enforce policies in services/method security. Reserve custom filters for responsibilities genuinely belonging at the filter layer rather than rewriting rules as filters.

## 14. Combining HTTP Authorization with Reactive Method Security

`authorizeExchange` checks exchanges when requests enter the API. However, a service method might be called from:

- An HTTP handler.
- A background job.
- A message consumer.
- Another reactive pipeline.

When business policies must apply consistently, you can add **Reactive Method Security**.

### 14.1. Enabling Reactive Method Security

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfig {
}
~~~

### 14.2. Guarding a Service with Scopes

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderQueryService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Mono<OrderDto> getOrder(String orderId) {
        return loadAuthorizedOrder(orderId);
    }
}
~~~

`OrderDto` and `loadAuthorizedOrder(...)` are illustrative domain components. Scope rules do not replace owner/tenant checks inside the service.

### 14.3. Reactive Business Policies

A complex policy can return `Mono<Boolean>` or a decision object depending on method security integration:

~~~text
@PreAuthorize -> policy bean
              -> Mono<Boolean> current permission
              -> continue or AccessDenied
~~~

When using SpEL, check the supported signatures in your Spring Security version and ensure reactive return types match. Avoid blocking calls to return an immediate `boolean` from an async database.

### 14.4. Proxy/Self-Invocation and Side Effects

Method security typically relies on AOP proxies. If one method in the same class calls another protected method directly, the call may **bypass the proxy**.

For operations with side effects—such as issuing refunds or approving payments—never place all protection in `@PostAuthorize` or a pre-check before state can mutate. Enforce invariants inside transactional/reactive transactional boundaries and guard against TOCTOU.

## 15. CORS Preflight and `authorizeExchange`

When a browser SPA calls a cross-origin API with a bearer header, it typically triggers a preflight request:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflight requests usually **carry no access token**. If the authentication filter treats it like a business request requiring a token, the browser reports a CORS error even when the API allows GET with a valid token.

Spring Security and Spring WebFlux need CORS configuration applied in the proper order. `authorizeExchange` does not emit headers like `Access-Control-Allow-Origin` by itself.

### 15.1. CorsWebFilter Example

~~~java
package com.example.orders.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiCorsConfig {

    @Bean
    CorsWebFilter corsWebFilter() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(
            List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
        cors.setAllowedHeaders(
            List.of("Authorization", "Content-Type"));
        cors.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", cors);
        return new CorsWebFilter(source);
    }
}
~~~

This example assumes one allowed SPA origin. If the app already configures CORS via WebFlux or Spring Security, **do not inadvertently register multiple CORS filter sets**, and verify ordering relative to security.

### 15.2. CORS Is Not Authorization

CORS restricts browser behavior when reading cross-origin responses. It **does not stop** direct HTTP clients or non-browser clients from calling the API.

Never treat `Origin` or `Access-Control-Allow-Origin` as proof that a user holds the `orders.write` scope.

### 15.3. Do Not Blindly Permit `OPTIONS /**`

A rule like:

~~~java
.pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()
~~~

may fit certain architectures, but is overly broad without review. It also **does not guarantee** valid CORS headers. Prefer proper CORS configuration that handles preflights for approved origins/headers/methods before adding authorization exceptions.

## 16. CSRF in a WebFlux Resource Server

In Spring Security WebFlux, CSRF protection is enabled by default in many baseline setups and may use `WebSessionServerCsrfTokenRepository`.

If an API accepts only bearer tokens explicitly attached by clients in the `Authorization` header and uses no browser-sent ambient credentials, its CSRF model differs from browser session login. In that case you may consider:

~~~java
.csrf(ServerHttpSecurity.CsrfSpec::disable)
~~~

or:

~~~java
.csrf(csrf -> csrf.disable())
~~~

**This is not a default to copy blindly into every WebFlux/OIDC app.** If the backend uses login cookies, a BFF, sessions, or other browser-sent credentials, CSRF must still be addressed despite using JWTs or a reactive architecture.

### 16.1. A 403 Error Might Be Unrelated to `authorizeExchange`

A POST request without a CSRF token in an app with CSRF enabled can receive **403** before scope rules are even evaluated.

When testing POST scopes, check:

- Is CSRF enabled?
- Does the endpoint use bearer-only auth or session cookies?
- Did the request include a valid CSRF token?
- Did the 403 come from the CSRF WebFilter, HTTP authorization, or a service policy?

Never disable CSRF just to make a test pass when the real application accepts cookies.

## 17. Distinguishing 401 and 403

| Scenario | Typical Result | Explanation |
|---|---|---|
| Public GET without token | 200 if handler succeeds | `permitAll()` |
| `/api/me` without token | 401 | Unauthenticated |
| JWT with wrong signature/issuer/audience/expiry | 401 | Authentication failure |
| Valid JWT without scope calling `/api/me` | 200 if contract permits | Requires only `authenticated` |
| JWT with only `orders.read` calling GET orders | 200 if business policy permits | Has HTTP read permission |
| JWT with only `orders.read` calling POST orders | 403 | Missing `orders.write` |
| JWT with only `orders.write` calling GET orders | 403 if lacking read | Write does not imply read |
| JWT with read scope querying another tenant's order | 403/404 per API policy | Object-level denial |
| Unknown path hitting `denyAll` | Typically 403 if authenticated | Route not permitted |
| POST in CSRF-enabled app missing token | Typically 403 | CSRF filter |
| Public GET with invalid bearer header | May return 401 | Authentication filter processed invalid credential |

These statuses reflect **typical** behavior; custom exception handlers, WebFilter order, gateways, route availability, and login mechanisms can change exact responses.

### 17.1. Bearer Challenge

RFC 6750 defines the `WWW-Authenticate` header to describe bearer authentication failures:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Insufficient scope can be reported with:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Exact formatting, realm, scope, and error descriptions depend on Spring Security and custom handlers. Never echo raw bearer tokens or secrets in error responses.

### 17.2. A 403 Does Not Prove the Token Is Invalid

If a token is authenticated but lacks `SCOPE_orders.write`, returning 403 is the right behavior. Never “fix” it by injecting the write scope inside `ReactiveJwtAuthenticationConverter` when the AS did not grant it.

## 18. Reactive Controller Matching the Policy

An illustrative controller:

~~~java
package com.example.orders.api;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/api/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            @AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of("subject", jwt.getSubject()));
    }

    @GetMapping("/api/orders")
    public Mono<Map<String, String>> listOrders() {
        return Mono.just(Map.of("action", "read"));
    }

    @PostMapping("/api/orders")
    public Mono<Map<String, String>> createOrder() {
        return Mono.just(Map.of("action", "write"));
    }
}
~~~

This is a **JWT Resource Server** example where the principal is injected as `Jwt`. With opaque tokens, the principal type usually differs. The `read`/`write` handlers only illustrate outcomes without touching a database or showing ownership/tenant policies.

`Map.of(...)` rejects nulls; the example assumes the JWT carries `sub` per contract. In production APIs, design dedicated DTOs and avoid returning unnecessary claims.

### 18.1. Illustrative HTTP Requests

No token:

~~~bash
curl -i https://api.example.com/api/public/ping
~~~

Token with read scope:

~~~bash
curl -i \
  -H "Authorization: Bearer $READ_TOKEN" \
  https://api.example.com/api/orders
~~~

Attempting POST with a read-only token:

~~~bash
curl -i -X POST \
  -H "Authorization: Bearer $READ_TOKEN" \
  https://api.example.com/api/orders
~~~

Token with write scope:

~~~bash
curl -i -X POST \
  -H "Authorization: Bearer $WRITE_TOKEN" \
  https://api.example.com/api/orders
~~~

URLs and tokens are illustrative. Never leave real bearer tokens in shell history, logs, or shared tickets.

## 19. WebTestClient Is the Primary Testing Tool for WebFlux

Servlet MVC uses `MockMvc`, whereas Reactive WebFlux uses **`WebTestClient`** and Spring Security reactive test support.

Testing approaches include:

- `@SpringBootTest` + `@AutoConfigureWebTestClient`.
- `WebTestClient.bindToApplicationContext(context).apply(springSecurity())` for customized test contexts.
- `mockJwt()` to construct an authenticated JWT principal.
- `mockOpaqueToken()` for opaque authentication.
- `mockUser()` when testing general authorization independent of token format.
- Integration tests with a real or controlled stub `ReactiveJwtDecoder` to verify signature and claim validation.

### 19.1. Testing HTTP Policy with `mockJwt()`

~~~java
package com.example.orders.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveHttpAuthorizationTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicGetNeedsNoToken() {
        client.get().uri("/api/public/ping")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void meNeedsAuthentication() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void meAcceptsMockAuthenticatedJwt() {
        client.mutateWith(
                mockJwt().jwt(jwt -> jwt.subject("user-42")))
            .get().uri("/api/me")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void readScopeCanGetOrders() {
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")))
            .get().uri("/api/orders")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void readScopeCannotPostOrders() {
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")))
            .post().uri("/api/orders")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void writeScopeCanPostOrders() {
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.write")))
            .post().uri("/api/orders")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void unknownRouteIsDenied() {
        client.mutateWith(mockJwt())
            .get().uri("/api/not-configured")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

**Preconditions for this example:** the earlier `DemoController` exists, the JWT chain from Section 3 is configured, business logic raises no other errors, and CSRF is configured appropriately for bearer-only POST tests. If CSRF remains active and requires a token on POST, a test may get 403 due to CSRF rather than missing scope; write tests that distinguish both causes.

### 19.2. `mockJwt()` Does Not Verify Signatures

`mockJwt()` creates a mock authentication to focus on testing **authorization rules**. When specifying:

~~~java
mockJwt().authorities(
    new SimpleGrantedAuthority("SCOPE_orders.read")
)
~~~

the test **attaches the authority directly**, potentially bypassing the production converter and the real `ReactiveJwtDecoder`.

Therefore, this test **does not prove**:

- The JWT has a valid JWS signature.
- JWKS is fetched from the right issuer.
- Claims `iss`, `aud`, `exp`, and `nbf` are checked.
- Production's scope converter maps authorities properly from claims.
- Token type and key/algorithm policies are enforced safely.

Add integration tests for the decoder, issuer/audience validation, claim mapping, and full authentication flow.

### 19.3. Testing Opaque Tokens

When the Resource Server uses introspection:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOpaqueToken;

client.mutateWith(mockOpaqueToken()
        .authorities(new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get().uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

Like `mockJwt`, this test can **bypass real network introspection**. It tests HTTP rules against a mock authentication, not whether the AS returned `active=true`.

## 20. Testing a Custom `ReactiveAuthorizationManager` with StepVerifier

A manager returning `Mono<AuthorizationResult>` can be unit tested in isolation with Reactor Test.

Example creating a mock context with `MockServerWebExchange`:

~~~java
package com.example.orders.security;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.web.server.authorization.AuthorizationContext;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class TenantOrdersReadAuthorizationManagerTest {

    @Test
    void missingTenantIdIsDenied() {
        ReactiveTenantMembershipPolicy memberships =
            mock(ReactiveTenantMembershipPolicy.class);

        var manager =
            new TenantOrdersReadAuthorizationManager(memberships);

        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/api/tenants/tenant-a/orders"));

        // Intentionally leave URI template variables empty.
        var context = new AuthorizationContext(
            exchange, Map.of());

        Mono<AuthorizationResult> result =
            manager.authorize(Mono.empty(), context);

        StepVerifier.create(result)
            .expectNextMatches(decision -> !decision.isGranted())
            .verifyComplete();
    }
}
~~~

This test verifies that missing `tenantId` is denied. To test allow cases, construct a `JwtAuthenticationToken` with the scope and issuer/subject and stub reactive membership to return `Mono.just(true)`.

### 20.1. A Test Allowing Access by Membership

~~~java
@Test
void tenantMemberWithReadScopeIsAllowed() {
    ReactiveTenantMembershipPolicy memberships =
        mock(ReactiveTenantMembershipPolicy.class);

    when(memberships.canReadOrders(
        "https://idp.example.com/realms/shop",
        "user-42",
        "tenant-a"
    )).thenReturn(Mono.just(true));

    Jwt jwt = Jwt.withTokenValue("unit-test-only")
        .header("alg", "RS256")
        .claim("iss", "https://idp.example.com/realms/shop")
        .claim("sub", "user-42")
        .build();

    var authentication = new JwtAuthenticationToken(
        jwt, List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
    );

    var exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/api/tenants/tenant-a/orders"));

    var context = new AuthorizationContext(
        exchange, Map.of("tenantId", "tenant-a"));

    var manager =
        new TenantOrdersReadAuthorizationManager(memberships);

    StepVerifier.create(
        manager.authorize(Mono.just(authentication), context))
        .expectNextMatches(AuthorizationResult::isGranted)
        .verifyComplete();
}
~~~

The second snippet is **an additional test method in the test class** and requires the corresponding imports: `java.util.List`, `Jwt`, `JwtAuthenticationToken`, `SimpleGrantedAuthority`, plus Mockito static imports. `Jwt.withTokenValue` builds a mock object and does not verify signatures.

### 20.2. Essential Negative Tests

| Scenario | Outcome to Guarantee |
|---|---|
| Empty Authentication Mono | Deny |
| Anonymous / non-JWT Authentication | Deny in JWT-only manager |
| Valid token missing `orders.read` | Deny |
| Blank tenant ID | Deny |
| Matcher failed to extract tenant ID | Deny |
| Missing subject/issuer | Deny |
| Subject belongs to tenant A, calls tenant B | Deny |
| Membership repository returns false | Deny |
| Membership repository returns `Mono.empty()` | Deny if required by policy |
| Membership repository errors | Never grant; clear error telemetry |
| Two issuers sharing the same `sub` | Never mix identities |
| User belongs to tenant A, order belongs to B | Deny in service |
| POST with only read scope | Deny |
| Broad rule placed before manager | Test must catch misconfiguration |
| Request outside API security chain | Never bypass policy |

These tests help verify **fail-closed** behavior across the full execution path, not just the happy path.

## 21. Limitations of Mock Security Context Tests

A test using `mockJwt()` can pass requests with manually attached authorities even when the real production converter fails to parse `scope` or `scp`.

Therefore, maintain four test layers:

1. **Decoder/authentication tests:** JWTs signed with test keys, testing valid and invalid issuer/audience/time.
2. **Converter tests:** verifying `scope`/`scp` or role claims map to the expected authorities.
3. **WebTestClient authorization tests:** verifying `authorizeExchange` selects the right rules and statuses.
4. **Service business tests:** verifying tenant, ownership, ACL, and state protection on objects.

A valid token **does not** prove access to a resource; a passing `WebTestClient` test **does not** prove production JWTs are verified properly.

## 22. Public Endpoints, Exception Handling, and Security Headers

A rule:

~~~java
.pathMatchers("/api/public/**").permitAll()
~~~

does not mean exchanges bypass `WebFilterChainProxy`. Other filters may still apply security headers, exception handling, CORS, CSRF, or attempt authentication if a client sends credentials.

Do not skip all security filters for public resources if headers or baseline protections are still needed. In WebFlux, inspect `securityMatcher` and the active filter chain rather than confusing it with a `permitAll` authorization rule.

If a Resource Server uses a custom `ServerAuthenticationEntryPoint` or `ServerAccessDeniedHandler`, you can customize the 401/403 JSON response without altering authorization decisions. Never turn a 403 handler into a place that grants extra authorities.

## 23. Object-Level Authorization Remains in the Service

Example:

~~~http
GET /api/orders/order-123 HTTP/1.1
Authorization: Bearer <token-with-orders.read>
~~~

`authorizeExchange` verifies the token carries `SCOPE_orders.read`, but has no idea who owns `order-123`.

Proper protection involves:

~~~text
HTTP:
  valid token for orders-api
  AND SCOPE_orders.read
          |
          v
Service:
  order exists?
  AND correct tenant?
  AND actor is owner or authorized staff?
  AND order data accessible under current policy?
          |
          v
Return only allowed fields
~~~

A reactive service should avoid loading an entire order and filtering outside the database if that risks leaking data. Use repository queries constrained by `ownerId`, `tenantId`, or required policies.

Example:

~~~java
return orderRepository
    .findByIdAndTenantId(orderId, tenantId)
    .switchIfEmpty(Mono.error(new NotFoundException()))
    .flatMap(order -> accessPolicy.canReadOrder(actor, order)
        .flatMap(allowed -> allowed
            ? Mono.just(toDto(order))
            : Mono.error(new AccessDeniedException("Forbidden"))));
~~~

`actor`, `NotFoundException`, `toDto`, and the repository are domain abstractions. No Spring Security API automatically infers every tenant or owner rule from scopes alone.

### 23.1. TOCTOU in Operations with Side Effects

If a policy checks “order has not been refunded yet”, checking once in an HTTP authorization filter is vulnerable to **time-of-check/time-of-use** races if state changes before writing.

Mitigations require transactions, conditional updates, versioning/locking, or proper idempotency policies. Custom reactive authorization can fail fast early, but cannot replace database-level invariants.

## 24. Debugging 401/403 When Moving from MVC to WebFlux

| Symptom | Possible Cause | Investigation |
|---|---|---|
| Cannot find `.authorizeHttpRequests(...)` | Running on WebFlux | Use `authorizeExchange` |
| `SecurityFilterChain` bean not applied | Wrong stack/bean type | Use `SecurityWebFilterChain` |
| `JwtDecoder` fails to inject | WebFlux expects `ReactiveJwtDecoder` | Check dependencies and beans |
| Public GET without token returns 401 | Matcher mismatch, wrong chain, or another filter | Inspect path, chain, and method |
| Public GET with invalid token returns 401 | Authentication filter processed invalid Bearer | Retry without Authorization header |
| Valid JWT gets 403 on GET orders | Missing `SCOPE_orders.read` or bad mapping | Inspect authorities safely |
| GET orders succeeds, POST gets 403 | Missing `SCOPE_orders.write`, or CSRF | Distinguish denial source |
| Admin endpoint publicly accessible | Broad `permitAll` matcher ordered first | Fix matcher ordering |
| API scope manager never runs | Broad `authenticated` matcher ordered first | Fix rule ordering |
| `/api/**` URL misses API chain | Wrong `securityMatcher` or `@Order` | Inspect all chains |
| Valid token accesses another tenant's resource (200) | Missing object policy | Inspect service queries |
| Reactive manager stalls | Blocking DB/SDK or `.block()` | Use reactive source / isolated scheduler |
| Empty authorization context | URI variable not extracted by matcher | Test matcher and fail closed |
| `mockJwt()` test passes, production returns 401 | Different decoder/issuer/audience/signature | Add real JWT integration test |
| WebFlux app switches to Servlet | Both starters present and auto-detection picks MVC | Verify app type/config |
| `SecurityContextHolder.getContext()` empty in another thread's callback | ThreadLocal unsuitable for Reactor pipelines | Use `ReactiveSecurityContextHolder` |

**Never fix a 403 error by arbitrarily injecting scopes/roles** that the AS did not issue. If the converter uses the wrong format, fix the mapping per contract; if the user truly lacks permissions, request valid grants or deny.

## 25. Applying the Principle of Least Privilege to Policy Design

Endpoint design workflow:

1. **Classify the endpoint:** public, authenticated, scope/role, or object-level policy.
2. **Specify HTTP methods:** apply rules per GET/HEAD/OPTIONS/POST/PUT/PATCH/DELETE.
3. **Place specific matchers first:** never let broad public or authenticated rules shadow scoped routes.
4. **Choose an explicit fallback:** typically `anyExchange().denyAll()` for tightly controlled APIs.
5. **Separate chains when needed:** bearer APIs and browser logins differ in state and CSRF handling.
6. **Verify the right token:** access token with valid issuer and audience; never accept ID tokens as API credentials.
7. **Never fabricate authorities:** OAuth scopes and roles must come from trusted sources.
8. **Separate business authorization:** enforce tenant, owner, and state rules in services/domain logic.
9. **Stay reactive and non-blocking:** never call blocking DB/HTTP inside managers on the event loop.
10. **Write negative tests:** missing/expired tokens, missing scopes, wrong tenants, matcher order, unknown routes.
11. **Never log credentials:** tokens, client secrets, and PII must not be exposed.
12. **Review every new route:** never rely on “the frontend doesn't call this endpoint” as a security control.

### Example Policy for a Refund API

~~~text
POST /api/refunds/{refundId}/approve

HTTP authorization:
  valid access token
  AND SCOPE_refunds.approve

Business authorization:
  actor belongs to the refund's merchant
  AND actor is assigned approval rights
  AND actor is not the requester (if required by policy)
  AND amount is within limits
  AND refund is pending
  AND write operation is atomic/idempotent
~~~

`authorizeExchange` should guard coarse-grained access, while stateful and object-specific rules live in business services and transactions.

## 26. Common Mistakes to Avoid

**“`authorizeExchange` is just an alias for `authorizeHttpRequests`.”** No. They serve two different stacks with different HTTP models and authorization manager types.

**“`SecurityWebFilterChain` is directly interchangeable with Servlet `SecurityFilterChain` in code.”** Conceptually similar, but the APIs are not drop-in replacements.

**“`pathMatchers("/api/**").permitAll()` only opens GET requests.”** False. Without specifying an HTTP method, the pattern matches all HTTP methods.

**“A stricter matcher placed later will override an earlier matcher.”** False. Spring Security evaluates rules in order, and the first match wins.

**“`authenticated()` is enough for an API requiring scopes.”** No, not if the API enforces specific entitlements.

**“`hasRole("ADMIN")` checks `SCOPE_admin`.”** No; by default it checks `ROLE_ADMIN`.

**“Read scope automatically grants write access.”** No. `orders.read` and `orders.write` are distinct.

**“`anyExchange().denyAll()` inside an `/api/**` chain protects every URL in the app.”** No. It applies only to exchanges routed into that chain.

**“A validly signed JWT grants access to all user data.”** False. Scopes do not replace object ownership.

**“A custom manager can call `.block()` since it's just checking permissions.”** Never do this on the reactive event loop; blocking hurts throughput and risks deadlocks or thread starvation.

**“Reactor Context and ThreadLocal behave identically.”** False. Reactive pipelines switch threads, so use reactive context APIs.

**“CORS restrictions replace authentication.”** No. CORS is solely a browser cross-origin policy.

**“`permitAll` ignores invalid bearer tokens.”** Not guaranteed. The authentication filter can still validate a submitted token and return 401.

**“WebTestClient `mockJwt()` proves production JWT signatures are valid.”** No. It uses mock authentication.

**“Disabling CSRF is always safe for a WebFlux Resource Server.”** No, not if browsers automatically send cookies or ambient credentials.

## 27. Self-Check Questions

**1.** Which DSL does WebFlux use to declare HTTP authorization?

> `ServerHttpSecurity.authorizeExchange(...)` inside a `SecurityWebFilterChain`.

**2.** How do `permitAll`, `authenticated`, and `hasAuthority` differ?

> Public requires no authentication; `authenticated` requires a valid principal; `hasAuthority` requires a specific granted authority.

**3.** Why is `.pathMatchers("/api/**").permitAll()` dangerous when placed first?

> Because it matches private/admin routes before stricter rules can run.

**4.** Which authority is a JWT containing `scope=orders.read` typically mapped to?

> `SCOPE_orders.read`.

**5.** Which authority does `hasRole("ORDERS_ADMIN")` typically check?

> `ROLE_ORDERS_ADMIN`, not the OAuth scope `orders.admin`.

**6.** How do `securityMatcher` and `pathMatchers` inside `authorizeExchange` differ?

> `securityMatcher` selects the security chain; `pathMatchers` selects the authorization rule inside the chosen chain.

**7.** What is the risk of a request matching no `SecurityWebFilterChain`?

> It may bypass security WebFilters entirely; explicit chain/fallback coverage is required.

**8.** What input type does a custom reactive HTTP manager receive for authentication?

> `Mono<Authentication>`, along with `AuthorizationContext`, returning `Mono<AuthorizationResult>` in newer Spring Security APIs.

**9.** Why must blocking `JdbcTemplate` not be called directly in a reactive manager?

> It can block the event loop. Use a reactive repository/HTTP client or isolate blocking work on an appropriate scheduler.

**10.** Does a `tenantId` in the URL prove membership?

> No. It is a client-chosen target; query an authoritative permission source.

**11.** Why might a token with `SCOPE_orders.read` still be denied when reading an order?

> Business policies may require matching tenant, owner, or ACL permissions for that order.

**12.** When is `mockJwt()` appropriate?

> Testing WebFlux HTTP authorization with mock principals/authorities. It does not replace decoder/signature integration tests.

**13.** Does a 403 on POST definitely mean a missing scope?

> No. It could be CSRF, an HTTP rule, a service ACL, or another policy; diagnose at the right layer.

**14.** Why is `anyExchange().denyAll()` needed?

> It prevents unconfigured exchanges from being implicitly allowed in the chain, aligning with fail-closed design.

**15.** Can opaque tokens use `authorizeExchange`?

> Yes. Swap the authentication path to `ReactiveOpaqueTokenIntrospector`, while rules still evaluate the authentication's authorities.

## 28. References

- [Spring Security — Authorize ServerHttpRequest (WebFlux)](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `authorizeExchange`, `pathMatchers`, `hasRole`, custom access, rule ordering, and `denyAll`.
- [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `ServerHttpSecurity`, `SecurityWebFilterChain`, multiple chains, and `securityMatcher`.
- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `ReactiveJwtDecoder`, `scope`/`scp` and `SCOPE_*`, `hasScope`.
- [Spring Security — OAuth2 WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/): overview of reactive Resource Server, JWT, opaque tokens, and OIDC Client.
- [Spring Security — Reactive Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): reactive introspection.
- [Spring Security — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html): DSLs and `securityMatcher`.
- [Spring Security — AuthorizeExchangeSpec.Access API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.AuthorizeExchangeSpec.Access.html): `permitAll`, `authenticated`, `hasAuthority`, `hasRole`, `access`.
- [Spring Security — ServerWebExchangeMatchers API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/util/matcher/ServerWebExchangeMatchers.html): method/path matching and custom exchange matchers.
- [Spring Security — AuthorizationContext API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/AuthorizationContext.html): HTTP exchange and extracted path variables.
- [Spring Security — ReactiveAuthorizationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html): reactive authorization decisions and versioned APIs.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity`, `@PreAuthorize`, and custom policies.
- [Spring Security — Reactive Testing OAuth2](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt`, `mockOpaqueToken`, custom authorities.
- [Spring Security — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): `WebTestClient` integration and security testing.
- [Spring Security — CSRF Protection for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): CSRF, WebSession, and cookie repositories.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer HTTP headers, authentication errors, and insufficient scope.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token structure, audience/scope.

**Summary:** `authorizeExchange` is the primary layer for authorizing **HTTP exchanges in WebFlux**. Use `pathMatchers` with explicit methods and paths, place narrow rules before broad ones, distinguish `securityMatcher` from authorization matchers, enforce genuinely granted scopes/authorities, and conclude with a clear default policy. When tenant or business rules are needed, use `ReactiveAuthorizationManager<AuthorizationContext>` with trusted data and non-blocking execution; then enforce ownership and state checks in the service layer. A secure reactive API combines **sound authentication, sound authorization, and negative tests for denied paths**, not merely a plausible-looking DSL chain.
