# Public Endpoints, Authenticated Endpoints, and Authority-Specific Endpoints

In a **Spring Security OAuth 2.0/OIDC Resource Server**, an API typically does not apply the same protection level to every endpoint. For example:

- `GET /api/public/catalog` can be viewed **without logging in**.
- `GET /api/me` requires a **valid access token**, without requiring a specific business scope.
- `GET /api/orders` requires a valid token **and** the `orders.read` scope.
- `POST /api/orders` requires a valid token **and** the `orders.write` scope.
- `GET /api/orders/{id}` may also need to check **permissions on the specific order**.

Spring Security uses `SecurityFilterChain`, `authorizeHttpRequests`, and `RequestMatcher`s to express these rules at the HTTP layer. Properly understanding the difference between **`permitAll()`**, **`authenticated()`**, and **`hasAuthority(...)`** helps a Resource Server enforce only the required level of protection while avoiding accidentally opening access to new endpoints.

> **Principle:** public endpoints require no authentication; authenticated endpoints require a validly authenticated principal; authority-specific endpoints require that principal to hold the exact authority defined by policy. Endpoint-layer permissions **do not replace** tenant, ownership, and per-resource permission checks.

This lesson uses Java, Spring Boot, Spring Security Servlet/Spring MVC, and JWT bearer access tokens. With opaque tokens or WebFlux, the authorization model is similar, though the authentication components and configuration APIs may differ.

## 1. Classifying Endpoints by Protection Goal

| Endpoint category | Common configuration | Condition to pass HTTP authorization | Example |
|---|---|---|---|
| **Public** | `permitAll()` | No authenticated `Authentication` required | Public health check, landing page, public catalog |
| **Authenticated** | `authenticated()` | Valid authentication present, not merely anonymous | The caller's own profile |
| **Specific authority** | `hasAuthority("SCOPE_orders.read")` | Authentication holds the exact authority | Reading order data |
| **One of several authorities** | `hasAnyAuthority(...)` | Holds at least one listed authority | Support staff or operators |
| **Application role** | `hasRole("ADMIN")` | Holds the role per prefix convention, typically `ROLE_ADMIN` | Admin dashboard |
| **Always denied** | `denyAll()` | Request not permitted | Undeclared routes or disabled features |

All six rule types belong to **authorization**. They do not decide which JWTs are trusted; bearer token verification occurs in the Resource Server components.

### 1.1. Authentication Differs from Authorization

Suppose the Resource Server receives a JWT access token:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "customer-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 2000000300
}
~~~

A properly configured `JwtDecoder` verifies signature, issuer, expiration, and audience per the contract. Spring Security can then create an `Authentication` with the authority:

~~~text
SCOPE_orders.read
~~~

The subsequent questions are **distinct**:

- Is the token valid? → authentication/validation.
- Does the request require a token? → `authenticated()` or a stricter rule.
- Does the request have the `orders.read` permission? → `hasAuthority("SCOPE_orders.read")`.
- Does the requested order belong to customer 42? → service/object-level authorization.

**A valid token does not mean every endpoint may be called.**

## 2. Request Flow in a Spring Security Resource Server

~~~text
HTTP request
     |
     v
Spring Security FilterChainProxy
     |
     v
SecurityFilterChain matching the request
     |
     +-- CORS / CSRF / security context / other filters
     |
     +-- BearerTokenAuthenticationFilter (when Resource Server is enabled on the chain)
     |       |
     |       +-- No bearer token: may continue as unauthenticated
     |       |
     |       +-- Bearer token present: verify JWT/introspection
     |               |
     |               +-- Invalid -> authentication failure
     |               +-- Valid -> create Authentication
     |
     v
AuthorizationFilter
     |
     +-- Which RequestMatcher rule matches?
     |
     +-- permitAll / authenticated / hasAuthority / denyAll
     |
     v
Controller -> service-level authorization -> data access
~~~

This high-level diagram highlights two points:

1. **`permitAll()` is a rule at the authorization layer**, not an instruction for Spring Security to skip the entire filter chain.
2. **`hasAuthority(...)` is only meaningful when authorities originate from a trusted authentication/authorization process**, not from client-supplied request parameters.

In modern Spring Security, `authorizeHttpRequests` uses the `AuthorizationManager`-based authorization infrastructure, with `AuthorizationFilter` enforcing decisions at the request boundary.

## 3. Building a Sample Resource Server

Suppose the application has these endpoints:

| HTTP method | Endpoint | Intent |
|---|---|---|
| `GET` | `/api/public/catalog` | Anyone can view |
| `GET` | `/api/me` | Any valid principal can view their own profile |
| `GET` | `/api/orders` | Requires `orders.read` |
| `GET` | `/api/orders/{id}` | Requires `orders.read` and permission on the order |
| `POST` | `/api/orders` | Requires `orders.write` |
| `PUT` | `/api/orders/{id}` | Requires `orders.write` |
| `DELETE` | `/api/orders/{id}` | Requires `orders.delete` |
| `GET` | `/actuator/health` | May be public if operations policy allows |
| Other methods/paths | `/api/**` | No implicit permission granted |

### 3.1. Gradle Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Spring Boot manages dependency versions via dependency management/BOM per project. The Resource Server starter provides bearer access token handling and JWT support when using `jwt()`.

### 3.2. application.yml

Assume the trusted issuer and API audience are:

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

- `issuer-uri` identifies the Authorization Server trusted by the Resource Server and must match the `iss` claim in the JWT.
- `audiences` verifies that the token is intended for `orders-api`. This property is supported in modern Spring Boot versions; on other versions, configure an audience validator explicitly.
- `jwt()` does not turn an OIDC ID token into a valid API access token. Token type, issuer, and audience must match the contract.

YAML alone does not decide which endpoints are public. Authorization is defined in the `SecurityFilterChain`.

## 4. Complete Configuration of All Three Protection Levels

`SecurityConfig.java`:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            // Only suitable for stateless APIs using the bearer header,
            // not relying on automatically sent cookies to authenticate requests.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                // 1. Public
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()

                // 2. Valid token only
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()

                // 3. Specific scope required
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.PUT, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.delete")

                // Safe default: undeclared routes are not opened.
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

### Key Assumptions of the Example

The example assumes a **stateless REST API** where the client sends a bearer access token via the `Authorization` header and does **not** use session cookies/HTTP Basic/form login as the authentication channel for state-changing requests.

Therefore, `csrf(AbstractHttpConfigurer::disable)` is a choice based on that architecture, **not a universal rule for every Spring application**. If the API accepts cookies sent automatically by browsers, CSRF must be evaluated and appropriate protection kept or designed.

In an architecture with a CORS browser SPA, you need to add `cors(...)` and configure a valid CORS source as shown later; a lone `permitAll` rule does not resolve CORS by itself.

Controller paths must align with the matchers. `/actuator/health` only exists if the application includes Actuator with corresponding exposure. If Actuator runs on a separate management port, a different security context may apply.

### Meaning of the Entire Policy

~~~text
GET  /api/public/catalog --> permitAll
GET  /api/me             --> authenticated
GET  /api/orders         --> SCOPE_orders.read
POST /api/orders         --> SCOPE_orders.write
PUT  /api/orders/123     --> SCOPE_orders.write
DELETE /api/orders/123   --> SCOPE_orders.delete
GET  /api/unknown        --> denyAll
~~~

Placing `anyRequest().denyAll()` at the end creates a **fail-closed** strategy: new endpoints are not opened simply because a developer forgot to add a rule.

## 5. Public Endpoints: `permitAll()`

When an endpoint has the rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/public/**")
    .permitAll()
~~~

it means **no permission/authentication is required to pass the HTTP authorization rule**. Unauthenticated users can access it. This is appropriate for:

- Catalogs or information intended for broad publication.
- Landing endpoints, public documentation.
- Health endpoints revealing only minimal status, if operations permit.
- Dedicated callbacks/public endpoints with independent protocol-level verification (if needed).

### 5.1. `permitAll` Is Not "Skip Spring Security"

As a request passes through the `SecurityFilterChain`, security filters may still perform processing such as security headers, CORS, JWT authentication, CSRF, or exception handling depending on configuration.

For example:

~~~http
GET /api/public/catalog HTTP/1.1
Host: api.example.com
~~~

with no token, the `permitAll` rule can let it through.

However, with:

~~~http
GET /api/public/catalog HTTP/1.1
Host: api.example.com
Authorization: Bearer invalid-or-expired-token
~~~

a Resource Server chain with `BearerTokenAuthenticationFilter` may **return 401 before the request reaches `permitAll`**, because the client actively sent an invalid bearer token. `permitAll` does not force the authentication filter to ignore a submitted token.

Therefore, to test a public endpoint, test a request **without an Authorization header**; an HTTP client that automatically attaches an expired token to every request can make it look like the endpoint is not public.

### 5.2. Prefer `permitAll` Over `web.ignoring()`

Spring Security recommends using `permitAll` for public resources instead of bypassing the entire filter chain with `web.ignoring()`, because ignored requests do not receive security headers or protective behavior provided by the filter chain.

~~~java
// Usually appropriate: still passes through the security filter chain
.requestMatchers("/assets/**").permitAll()
~~~

This does not mean public resources require a JWT; it simply lets them continue being served **within a unified security structure**.

### 5.3. Public Endpoints Still Need Data and Infrastructure Protection

`permitAll` only states **no authentication is needed**. It does not automatically protect against:

- Personal data leakage if a controller returns data unsuitable for public access.
- Rate limiting, scraping, or bot abuse.
- Input validation/SQL injection.
- Sensitive details in health/info/metrics.
- Public endpoints causing unintended state changes.

Never use `permitAll` on an endpoint containing private data just because the front-end has not implemented login yet. Public exposure must be an approved product and security decision.

## 6. Authenticated Endpoints: `authenticated()`

Rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/me")
    .authenticated()
~~~

requires the caller to present a **valid `Authentication`** per the filter chain's mechanism. In a JWT Resource Server, that is normally a bearer access token with valid signature/issuer/audience/lifetime.

Example:

~~~http
GET /api/me HTTP/1.1
Host: api.example.com
Authorization: Bearer <valid-access-token>
~~~

`authenticated()` **does not require** the token to carry `orders.read`, `orders.write`, or an `ADMIN` role. It only sets the authentication threshold.

### 6.1. When Is Requiring Authentication Alone Enough?

It can be suitable for:

- Viewing basic information about **the calling principal itself**.
- Checking authenticated session/token state on an API designed for that purpose.
- Endpoints that do not modify other people's data and do not require separate entitlements.
- Functions where business policy states every valid principal of the API is permitted access.

Be aware, though: **"every valid principal"** in a Resource Server may include **machine clients** or other subject types, depending on the token profile. If `/api/me` only makes sense for human users, enforce an appropriate token/client type policy or principal model; do not assume `authenticated()` distinguishes a human user from a service account.

### 6.2. Authentication Does Not Guarantee Resource Ownership

If the endpoint is:

~~~http
GET /api/profiles/user-42 HTTP/1.1
Authorization: Bearer <token-of-user-99>
~~~

`authenticated()` alone is insufficient to stop user 99 from reading user 42's profile. The API must check the subject or the corresponding data access rights.

A `GET /api/me` endpoint is usually safer by design when it reads the subject from `SecurityContext` rather than accepting an arbitrary client-supplied user ID.

### 6.3. `authenticated()` and the Anonymous Principal

Spring Security can create an `AnonymousAuthenticationToken` to represent an unauthenticated request in certain flows. Despite having "Authentication" in its class name, the `authenticated()` rule recognizes anonymous tokens and **does not treat anonymous as a validly authenticated user**.

Do not write code that merely checks `SecurityContextHolder.getContext().getAuthentication() != null` and assumes the user is logged in.

## 7. Endpoints Requiring a Specific Authority: `hasAuthority(...)`

A JWT access token might contain:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "customer-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 2000000300
}
~~~

Once verified, Spring Security typically converts `scope=orders.read` into the authority:

~~~text
SCOPE_orders.read
~~~

To protect reading orders:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

To protect creating or updating orders:

~~~java
.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
.requestMatchers(HttpMethod.PUT, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

A token with only `orders.read` **cannot** write orders, even when authenticated with a valid signature.

### 7.1. `hasAuthority` Compares the Actual Authority String

`hasAuthority("SCOPE_orders.read")` checks for an authority named **`SCOPE_orders.read`**; it does not automatically translate another string into an equivalent permission.

| Mapped JWT scope/authority | Rule | Result |
|---|---|---|
| `SCOPE_orders.read` | `hasAuthority("SCOPE_orders.read")` | Passes rule |
| `SCOPE_orders.write` | `hasAuthority("SCOPE_orders.read")` | Denied |
| `ROLE_ORDERS_READER` | `hasAuthority("SCOPE_orders.read")` | Denied if missing read scope |
| `SCOPE_orders.read` and `SCOPE_orders.write` | `hasAuthority("SCOPE_orders.write")` | Passes rule |
| Empty authority set | `authenticated()` | Can pass if token is authenticated |
| Empty authority set | `hasAuthority("SCOPE_orders.read")` | Denied |

**Do not "fix" a 403 error by injecting scopes on the Resource Server** if the Authorization Server did not issue that scope. Check the OAuth authorization flow and actual permissions instead.

### 7.2. One of Several Authorities: `hasAnyAuthority`

For example, an endpoint permitting both operators and admins per **trusted granted roles**:

~~~java
.requestMatchers("/api/support/**")
    .hasAnyAuthority(
        "ROLE_SUPPORT_AGENT",
        "ROLE_SUPPORT_ADMIN"
    )
~~~

`hasAnyAuthority` is an **OR** condition. A single matching authority suffices. Ensure roles/authorities come from a trusted source rather than being inferred from email or username.

If an endpoint requires multiple permissions simultaneously, use an appropriate authorization manager or custom policy; do not mistake `hasAnyAuthority` for an AND condition.

### 7.3. `hasRole` Is a Role Convention, Not a Scope

In standard Spring Security configuration:

~~~java
.hasRole("ADMIN")
~~~

is equivalent to requiring the authority `ROLE_ADMIN` under the default role prefix. It is **different from**:

~~~java
.hasAuthority("SCOPE_admin")
~~~

A JWT scope containing `admin` does not automatically become `ROLE_ADMIN` without an approved mapping.

If the AS uses a custom role claim, configure `JwtAuthenticationConverter` or an appropriate authority source. This is an authority-mapping policy, not merely renaming strings for convenience.

## 8. `requestMatchers` Ordering Determines Which Rule Applies

One of the most dangerous mistakes when writing `authorizeHttpRequests` is placing a broad rule before a specific rule.

Spring Security evaluates rules in **declaration order** within a chain; once a request matches a rule, the system uses that rule's decision and does not keep looking for a "stricter" rule later.

### 8.1. Incorrect Example: Public Rule Shadows a Private Route

~~~java
// WRONG: overly broad public rule comes first.
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
)
~~~

A request to `/api/admin/users` matches `/api/**` and is allowed by `permitAll`; `/api/admin/**` **never gets a chance to protect it**.

### 8.2. Fixing with Specific Rules First

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/public/**").permitAll()
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
)
~~~

New order:

1. Admin routes require the role.
2. Public routes are explicitly opened.
3. Remaining APIs require authentication.
4. Anything outside the described scope is denied.

This is a valid organization if business requirements truly allow **all other APIs after authentication**. If many APIs need dedicated scopes, declare scope-requiring rules first and end with `denyAll()` instead of an overly broad `authenticated()` fallback.

### 8.3. Incorrect Example: `authenticated` Placed Before `hasAuthority`

~~~java
// WRONG if /api/orders must be restricted to tokens with orders.read
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().denyAll()
)
~~~

The `/api/**` rule blocks reaching the scope rule below it. Any valid token can cross the HTTP boundary for `/api/orders/**`, even without `orders.read`.

**Conclusion:** ordering is part of the authorization policy, not merely code formatting.

## 9. `securityMatcher` and `requestMatchers` Are Not the Same

In an application with **multiple `SecurityFilterChain`s**, the two matchers have different responsibilities:

- **`securityMatcher(...)`:** decides **which chain** applies to the request.
- **`requestMatchers(...)` inside `authorizeHttpRequests`:** decides **which authorization rule** applies **inside the selected chain**.

Example:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers("/api/me").authenticated()
            .anyRequest().hasAuthority("SCOPE_api.read"))
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

With `securityMatcher("/api/**")`, this chain **does not handle `/actuator/health`** or `/admin`. Unmatched requests are evaluated by subsequent chains, if any.

### 9.1. Always Plan for Requests Matching No Chain

A multi-chain configuration can include a fallback:

~~~java
@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/actuator/health").permitAll()
            .anyRequest().denyAll())
        .build();
}
~~~

The two snippets above are **two beans in the same class/configuration** and require importing `org.springframework.core.annotation.Order` and the corresponding Spring Security imports.

When multiple chains exist, `FilterChainProxy` picks **the first matching chain in order**. Authorization rules across chains **do not merge automatically**.

Major risk: if you create only one chain with `securityMatcher("/api/**")` and no chain catches paths outside `/api/**`, those requests may **fall outside Spring Security filter chain protection**. This is a separate issue from `anyRequest().denyAll()` inside a chain.

### 9.2. When Should Multiple Chains Be Used?

They can be used when the system has distinct security zones:

- `/api/**` using OAuth2 JWT bearer and stateless sessions.
- `/admin-ui/**` using browser login/session/CSRF.
- `/actuator/**` with separate operational and network rules.

However, each chain must have:

1. A properly scoped `securityMatcher`.
2. Explicit `@Order` ordering.
3. Authorization rules not shadowed by broad matchers.
4. A fallback plan for paths outside the intended chains.
5. Tests for paths along the boundary between chains.

## 10. Combining HTTP Methods with URLs

Matching only paths while omitting HTTP methods can make rules overly broad.

Example:

~~~java
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

Written this way, **POST, PUT, PATCH, DELETE** on `/api/orders/**` may also require only the read scope unless a stricter rule precedes it. This can be an authorization bug.

When permission semantics depend on the HTTP action, use `requestMatchers(HttpMethod, path)`:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")

.requestMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")

.requestMatchers(HttpMethod.PUT, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")

.requestMatchers(HttpMethod.PATCH, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")

.requestMatchers(HttpMethod.DELETE, "/api/orders/**")
    .hasAuthority("SCOPE_orders.delete")

.anyRequest().denyAll()
~~~

Using `anyRequest().denyAll()` ensures a new HTTP method or unapproved endpoint **does not receive permissions by default**.

### 10.1. Notes on `HEAD`, `OPTIONS`, and Preflight

HTTP includes methods beyond GET/POST/PUT/DELETE. In Spring MVC, `HEAD` handling can relate to GET mappings, whereas a security rule matching only `HttpMethod.GET` will not automatically imply the same coverage for every other method.

For `OPTIONS`, browsers may send a **CORS preflight** before a request carrying an `Authorization` header. Configure CORS properly per section 14 instead of opening `OPTIONS /**` unconditionally just to "make frontend errors go away."

When designing policies, align on how every HTTP method that the application or proxy might forward to the backend is handled, including TRACE/HEAD/OPTIONS if applicable.

### 10.2. Matchers Depend on Actual Paths and the Framework

In Spring MVC, matcher syntax and selection can vary with context path, servlet path, library versions, and presence/absence of MVC on the classpath. Check:

- Which URL the controller is actually registered at.
- Whether there is a context path or servlet prefix.
- Whether a reverse proxy rewrites paths.
- Whether `/api/public/**` accidentally encompasses `/api/public/admin/**`.
- Whether routes can have trailing slashes or different path variables.
- Whether security matchers and controller matchers are in sync.

Do not rely on gut feeling that "`**` probably covers all cases" when an endpoint has high security impact. Write tests for concrete paths.

## 11. Choosing a Fallback: `authenticated()` or `denyAll()`?

Two endings for a chain:

~~~java
.anyRequest().authenticated()
~~~

and:

~~~java
.anyRequest().denyAll()
~~~

have different meanings.

| Fallback | When a new endpoint appears without a dedicated rule | Appropriate when |
|---|---|---|
| `authenticated()` | Any valid principal can pass the HTTP layer | Intentionally allowing all remaining endpoints with minimal authentication |
| `denyAll()` | New endpoint is denied until an explicit rule is added | APIs with multiple scopes or requiring policy approval before opening |
| `permitAll()` | New endpoint is public by default | Generally **unsuitable** for systems holding private data |

**Practical recommendation for Resource Servers with business data:** explicitly declare public, authenticated, and authority-specific endpoints, then use `denyAll()` for the rest unless there is a clear reason for an authenticated fallback.

Remember that `denyAll` at the end can also block useful routes like health, error, or static content if undeclared; decide explicitly on those routes.

## 12. Differences Between 401 and 403 Statuses

When a request is rejected:

- **401 Unauthorized:** no valid authentication, or the bearer token was rejected. The HTTP status name says "Unauthorized," though in practice it usually means **authentication did not succeed**.
- **403 Forbidden:** validly authenticated, but lacking the required authority, or rejected by a resource policy.

Examples:

| Request | Typical outcome | Explanation |
|---|---|---|
| No token calling `GET /api/public/catalog` | `200` if handler succeeds | Public |
| No token calling `GET /api/me` | `401` | Authentication required |
| Expired token calling `GET /api/me` | `401` | Invalid token |
| Valid token without scopes calling `GET /api/me` | `200` if contract allows | Authenticated only |
| Token with only `orders.read` calling `GET /api/orders` | `200` if data policy allows | Valid read permission |
| Token with only `orders.read` calling `POST /api/orders` | `403` | Missing `orders.write` |
| Token with `orders.write` but missing `orders.read` calling GET | `403` | Write permission does not imply read permission |
| Valid token calling an undeclared route | `403` per `denyAll` | Fallback denial |
| Valid token with scope reading someone else's order | `403` or `404` per policy | Object ownership check |

Exact outcomes also depend on exception handlers, the selected chain, dispatcher types, and whether a handler exists. `200` in the table assumes the controller and business service succeed.

### 12.1. `WWW-Authenticate` with Bearer Tokens

RFC 6750 defines headers for bearer authentication. Example:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
~~~

When the token is valid but lacks sufficient scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.write"
~~~

This illustrates the standard; Spring Security and custom error handlers may emit different concrete details. Never include raw access tokens, private keys, or sensitive data in error responses.

## 13. A Valid JWT May Still Lack Resource-Level Permissions

A `GET /api/orders/1001` may pass the rule:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

yet still must check whether the user has permission to view **order 1001**.

Endpoint layer:

~~~text
Has SCOPE_orders.read? -> allowed into handler
~~~

Business layer:

~~~text
Which tenant does order 1001 belong to?
Does the subject hold membership in that tenant?
Which user owns the order?
Does the user have entitlement to read this order?
~~~

Pseudocode example:

~~~java
Order order = repository.findById(orderId)
    .orElseThrow(NotFoundException::new);

InternalUser user = identityDirectory.resolve(
    jwt.getIssuer().toString(),
    jwt.getSubject()
);

if (!authorizationService.canReadOrder(user, order)) {
    throw new AccessDeniedException("Forbidden");
}

return order;
~~~

`Order`, `InternalUser`, `NotFoundException`, `identityDirectory`, and `authorizationService` above are illustrative domain classes/concepts, not built-in Spring APIs.

Checking only `SCOPE_orders.read` while skipping object authorization exposes the Resource Server to **Broken Object Level Authorization (BOLA)/IDOR**, allowing users to read others' data by changing `orderId`.

## 14. CORS Preflight Is Not a Public Business Endpoint

A browser client at `https://app.example.com` calling `https://api.example.com` with a bearer token usually requires CORS. The browser may send a preflight first:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflight requests usually **do not carry the API access bearer token**. If authentication treats it like a normal business request, the browser may report a CORS error even when the actual access token is valid.

Spring Security recommends processing CORS **before security authentication** using proper configuration, such as supplying a `CorsConfigurationSource`.

### 14.1. Illustrative CORS Source Example

~~~java
package com.example.orders.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class CorsConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://app.example.com"));
        config.setAllowedMethods(
            List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
        config.setAllowedHeaders(
            List.of("Authorization", "Content-Type"));
        config.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", config);
        return source;
    }
}
~~~

Combined in the filter chain:

~~~java
.cors(Customizer.withDefaults())
~~~

This is merely an example of one allowed public SPA origin. If cookies/credentials are used cross-origin, the CORS policy differs and requires proper `allowCredentials`/`SameSite`/CSRF configuration; never use `allowedOrigins("*")` with credentials.

**CORS does not replace authentication/authorization.** It is a browser cross-origin policy and does not stop a non-browser HTTP client from calling the API. Never treat CORS as proof that an endpoint is protected.

### 14.2. Do Not Unconditionally Open All `OPTIONS`

You may see a workaround like:

~~~java
.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
~~~

This rule is not always wrong, but it is very broad and can mask CORS configuration issues. Nor does it automatically produce the `Access-Control-Allow-*` headers browsers expect. Prioritize configuring CORS and preflight handling properly, and only add specific matchers afterward if the architecture requires it.

## 15. CSRF and the Decision to Disable CSRF in Bearer APIs

A REST API that uses only `Authorization: Bearer <token>` explicitly set by the client and does not use automatically sent cookies for authentication typically has a different CSRF model from browser apps relying on session cookies.

Hence you may see:

~~~java
.csrf(AbstractHttpConfigurer::disable)
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
~~~

This is a **conditional choice** for stateless bearer-only APIs, not a statement that every OAuth API can disable CSRF.

If the same endpoint also accepts:

- Session cookies used for form login.
- Automatically sent cookies representing authentication.
- A cookie-based BFF mechanism.
- Browser-attached HTTP authentication where applicable.

then CSRF must be evaluated based on how the browser transmits credentials. An API with JWTs that also accepts cookies may still need CSRF protection.

**`permitAll` does not mean bypassing the CSRF filter.** For example, a public `POST` without a CSRF token in an application with CSRF enabled can result in `403`. So do not conclude `permitAll` is "broken" from a 403 response without checking which filter raised the error.

## 16. Dispatcher Types and Error Handling

In the Servlet stack, besides direct requests, there are dispatch types such as `FORWARD` and `ERROR`. A controller can forward, or the framework can dispatch to an error endpoint.

If rules are very strict and omit these dispatches, error responses may be masked by another `403`. Spring Security supports:

~~~java
import static jakarta.servlet.DispatcherType.ERROR;
import static jakarta.servlet.DispatcherType.FORWARD;

// Inside authorizeHttpRequests:
.dispatcherTypeMatchers(ERROR, FORWARD).permitAll()
~~~

Add this only when consistent with architecture and policy; it allows **these dispatcher types** through the authorization rule without turning main endpoints public. Understand how the container and application use dispatchers, and do not open other dispatch types indiscriminately.

In an application with only simple REST controllers, this rule may be unnecessary. With complex error handling or MVC view rendering, it is worth checking if unexpected 403s occur.

## 17. Method Security and Multi-Layer Authorization

HTTP request rules are usually the first line of defense:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

However, service permissions may be finer-grained and need enforcement regardless of which controller calls the service. Spring Security supports method authorization via `@EnableMethodSecurity`, `@PreAuthorize`, and related mechanisms.

Example:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderSummary findOrder(String orderId) {
        // Must also check ownership/tenant via service policy.
        return loadAndCheckOwnership(orderId);
    }
}
~~~

`OrderSummary` and `loadAndCheckOwnership(...)` are illustrative domain components.

Do not assume enabling `@EnableMethodSecurity` automatically protects every method. Only methods/rules with explicit policies are governed per configuration. And `@PreAuthorize` checking a scope still does not replace object-level authorization if the scope does not encode per-order permissions.

### Do Two Protection Layers Conflict?

If HTTP requires `orders.read` and the service also requires `orders.read`, the two layers can follow **defense in depth**. Keep the goals clear:

- HTTP rules protect routes from the outside.
- Service rules protect business logic when called from multiple entry points.
- Object policies control specific data.

Do not use method security to mask an overly broad HTTP matcher without tests; every boundary should be understood and controlled.

## 18. Authorization by Role, Scope, and Multiple Authority Sources

At the HTTP layer, Spring Security does not know whether an authority came from a JWT `scope`, a `roles` claim, or a database once adapters represent them all as `GrantedAuthority`. Authority mapping must therefore be well-grounded.

Example:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

should correspond to a real scope issued by the AS. If using roles:

~~~java
.hasRole("ORDERS_ADMIN")
~~~

requires `ROLE_ORDERS_ADMIN` issued from an approved authorization source.

Never inject `ROLE_ORDERS_ADMIN` when a token only carries `scope=orders.read`. That is **privilege escalation**. Likewise, never rely on `email`, `preferred_username`, or an email domain to mint admin permissions inside a converter.

### JWTs and Opaque Tokens

HTTP authorization conditions like `permitAll`, `authenticated`, or `hasAuthority` do not directly depend on whether the token is a JWT or opaque. The main difference lies in **how `Authentication` is constructed**:

- JWT: `JwtDecoder` verifies signature/claims; a converter maps scopes/roles.
- Opaque: `OpaqueTokenIntrospector` checks status/attributes with the Authorization Server or a trusted introspection component.

Both must only produce well-founded authorities. `authenticated()` must never be escalated into `hasAuthority("SCOPE_orders.write")`.

## 19. An Illustrative Controller for All Three Endpoint Types

To make the outcomes concrete, consider this controller:

~~~java
package com.example.orders.api;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {

    @GetMapping("/public/catalog")
    public Map<String, String> catalog() {
        return Map.of("status", "public");
    }

    @GetMapping("/me")
    public Map<String, String> me(@AuthenticationPrincipal Jwt jwt) {
        return Map.of("subject", jwt.getSubject());
    }

    @GetMapping("/orders")
    public Map<String, String> orders() {
        return Map.of("action", "read orders");
    }

    @PostMapping("/orders")
    public Map<String, String> createOrder() {
        return Map.of("action", "create order");
    }
}
~~~

This snippet is solely for illustrating HTTP rules; `/orders` in a real product must work with a database and enforce ownership/tenant checks. `/me` assumes valid tokens have a non-null `sub`. For machine tokens, redefine what "me" means for the actual principal.

### Sample Requests

No token:

~~~bash
curl -i https://api.example.com/api/public/catalog
~~~

Valid token:

~~~bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.example.com/api/me
~~~

Token with read scope:

~~~bash
curl -i \
  -H "Authorization: Bearer $READ_ACCESS_TOKEN" \
  https://api.example.com/api/orders
~~~

Attempting POST with a read-only token:

~~~bash
curl -i -X POST \
  -H "Authorization: Bearer $READ_ACCESS_TOKEN" \
  https://api.example.com/api/orders
~~~

Per the example policy, the final POST request must be rejected because it lacks `SCOPE_orders.write`. Never put real tokens in logs, tickets, screenshots, or shared shell history.

## 20. Testing HTTP Authorization with MockMvc

`spring-security-test` provides utilities to help test authorization. Example test using `MockMvc` with `jwt()` to simulate a JWT authentication:

~~~java
package com.example.orders.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HttpAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointWorksWithoutToken() throws Exception {
        mvc.perform(get("/api/public/catalog"))
            .andExpect(status().isOk());
    }

    @Test
    void meRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void meAllowsValidatedPrincipalInAuthorizationTest()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(jwt().jwt(token -> token.subject("user-42"))))
            .andExpect(status().isOk());
    }

    @Test
    void readScopeAllowsGetOrders() throws Exception {
        mvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    () -> "SCOPE_orders.read")))
            .andExpect(status().isOk());
    }

    @Test
    void readScopeDoesNotAllowPostOrders() throws Exception {
        mvc.perform(post("/api/orders")
                .with(jwt().authorities(
                    () -> "SCOPE_orders.read")))
            .andExpect(status().isForbidden());
    }

    @Test
    void writeScopeAllowsPostOrders() throws Exception {
        mvc.perform(post("/api/orders")
                .with(jwt().authorities(
                    () -> "SCOPE_orders.write")))
            .andExpect(status().isOk());
    }

    @Test
    void unknownEndpointIsDeniedByDefault() throws Exception {
        mvc.perform(get("/api/unknown")
                .with(jwt()))
            .andExpect(status().isForbidden());
    }
}
~~~

**Conditions of the test example:** the application has the earlier `DemoController` and corresponding filter chain; actual handlers throw no business errors; CSRF is configured per the bearer-only model as in the example. In an application with CSRF enabled, a POST request in a test may need `csrf()` or a different policy.

### Limitations of `jwt()` in Tests

`jwt()` is a tool for mocking **authentication/principal/authorities**. When a test uses:

~~~java
.with(jwt().authorities(() -> "SCOPE_orders.read"))
~~~

it is directly assigning authorities to a test authentication, **without checking real JWT signatures, JWKS, issuer, audience, or production converters**.

Therefore, separate:

- **Authorization tests:** verify HTTP rules allow/deny based on expected `Authentication`.
- **Authentication/integration tests:** send real JWSs signed with test keys through `JwtDecoder` and test invalid signature, issuer, audience, and expiration.
- **Converter tests:** verify `scope`/`scp` claims map accurately without fabricating permissions.
- **Business policy tests:** verify tenant/ownership and object-level authorization.

Each test type guards a different boundary; never use a single mocked-JWT test to claim the entire OAuth system is secure.

## 21. Key Test Matrix for the Three Endpoint Types

| Case | Public GET | Authenticated GET | Scoped GET | Scoped POST |
|---|---|---|---|---|
| No token | Allowed | 401 | 401 | 401 |
| Expired JWT | May be 401 if invalid bearer sent to same chain | 401 | 401 | 401 |
| Valid JWT, no scopes | Allowed | Allowed | 403 | 403 |
| JWT with `orders.read` only | Allowed | Allowed | Allowed | 403 |
| JWT with `orders.write` only | Allowed | Allowed | 403 | Allowed |
| JWT with both read and write | Allowed | Allowed | Allowed | Allowed |
| JWT with wrong audience | May be 401 if invalid token sent | 401 | 401 | 401 |
| Valid JWT without permission on specific order | Allowed for public resource | Depends on policy | 403/404 in object policy | Depends on policy |

The table states **expected security decisions**. Actual status codes assume the endpoint exists, business logic succeeds, no other filter rejects, and invalid tokens are sent via a bearer header to a chain with Resource Server authentication.

Specifically test **no token** and **invalid token** on public endpoints as two separate scenarios. `permitAll` does not force the bearer authentication filter to ignore a bad credential that was presented.

## 22. Common Mistakes When Designing the Three Endpoint Groups

### 22.1. Setting `permitAll` Too Broadly

~~~java
// WRONG: opens the entire API, including private endpoints.
.requestMatchers("/api/**").permitAll()
~~~

Fix with narrow public paths and per-group endpoint rules.

### 22.2. Using `authenticated` for APIs Needing Entitlements

~~~java
// INSUFFICIENT if orders require a dedicated read scope.
.requestMatchers("/api/orders/**").authenticated()
~~~

Fix with HTTP method matchers and appropriate `hasAuthority`.

### 22.3. Using `hasRole` When Only an OAuth Scope Exists

~~~java
// May never match if the token only has SCOPE_orders.read.
.requestMatchers("/api/orders/**").hasRole("orders.read")
~~~

Fix to `hasAuthority("SCOPE_orders.read")` if the issuer grants that scope. Do not inject `ROLE_orders.read` in the converter just to keep legacy code running.

### 22.4. Placing a General Rule Before a Specific Rule

~~~java
// WRONG: /api/admin/** will be shadowed by /api/**.
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
~~~

Place strict specific rules first.

### 22.5. Forgetting a Default Rule

If there are only a few `requestMatchers` in a chain, remaining paths may be handled by other rules/chains you did not intend. Declare an explicit `anyRequest()` for the chain and include a fallback chain when using a narrow `securityMatcher`.

### 22.6. Protecting Only GET While Forgetting POST/PUT/DELETE

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.anyRequest().authenticated()
~~~

In this example, POST without its own scope rule falls into `authenticated()`, potentially exposing write access unintentionally if a controller handles it. Use `denyAll` or declare all methods explicitly.

### 22.7. Using CORS to Make Permission Decisions

~~~text
AllowedOrigin: https://app.example.com
~~~

is not an authorization policy. Direct HTTP clients are not constrained by browser CORS. Verify bearer tokens and authorities on the server.

### 22.8. Treating Scopes as Permission on All Records

`orders.read` permits calling the read endpoint class; whether a user may view a specific order still requires a data-level policy.

### 22.9. Making Public Health Endpoints Reveal Too Much by Default

A minimal health check may be public if operations require it. However, metrics, environment, config, heapdump, loggers, or other actuator endpoints should not be opened with `/actuator/**.permitAll()` just because health needs to be public.

### 22.10. Disabling CSRF Unconditionally

A bearer-only stateless API may have valid reasons to disable CSRF. Browser session/cookie authentication has a different threat model. Verify the architecture before disabling it.

## 23. Policy Design Workflow for a New API

When adding an endpoint, instead of starting with "`authenticated()` is good enough," answer in order:

1. **Is this genuinely public data?** If yes, use a narrow matcher with `permitAll` and control returned data.
2. **Do we only need a valid principal, or a specific entitlement?** If it is strictly the principal's own info, `authenticated` may suffice.
3. **Which scope/role does the HTTP action belong to?** Use `hasAuthority`, `hasAnyAuthority`, or an explicit policy.
4. **Which HTTP methods are allowed?** Do not let write actions fall into an `authenticated`-only fallback.
5. **Are there tenant, owner, or record conditions?** Add policies in the service or method security.
6. **Do other endpoints/chains/fallbacks affect it?** Review matcher ordering and `securityMatcher`.
7. **Do clients send browser cookies or make cross-origin calls?** Evaluate CSRF and CORS.
8. **Are there proper denial tests?** Test no token, bad token, missing scope, undeclared routes, and unauthorized objects.

### Example Design Checklist for `POST /api/refunds`

This is a sensitive endpoint. `authenticated()` is usually insufficient. It may require:

~~~text
POST /api/refunds
    -> valid access token
    -> aud = refunds-api
    -> SCOPE_refunds.create
    -> caller has permission to refund at this merchant
    -> transaction is still in a refundable state
    -> additional limit/approval policies
~~~

HTTP `hasAuthority("SCOPE_refunds.create")` protects only one layer. Do not equate a scope with approval of the entire transaction.

## 24. Self-Check Questions

**Question 1.** Does `permitAll()` mean Spring Security skips the JWT filter completely?

> No. It is an authorization rule; other filters in the chain, including bearer token authentication, may still process the request. An invalid token sent to a public endpoint can trigger a 401.

**Question 2.** Does `authenticated()` require the token to contain `orders.read`?

> No. It requires valid authentication. Permission to read orders requires a `hasAuthority("SCOPE_orders.read")` rule or equivalent policy.

**Question 3.** A JWT has `scope=orders.read` and calls `POST /api/orders`, which requires `orders.write`. What is the result?

> The token may be authenticated, yet fail the write-permission rule; typically 403.

**Question 4.** Why is placing `requestMatchers("/api/**").permitAll()` before an admin rule dangerous?

> Because the broad matcher can match the request first; the admin rule afterward is never evaluated.

**Question 5.** Does `anyRequest().denyAll()` protect URLs outside `securityMatcher("/api/**")`?

> No. `anyRequest` applies only inside the selected chain. If no other chain matches, out-of-scope URLs may bypass Spring Security protection.

**Question 6.** If a browser reports a CORS preflight error, should JWT verification be removed?

> No. Configure CORS and preflight handling properly, independent of business-request authentication/authorization.

**Question 7.** Why might a token with `SCOPE_orders.read` still be rejected when reading an order?

> Because the API must also check tenant, owner, or permission on the specific record.

**Question 8.** Is `hasRole("ADMIN")` the same as `hasAuthority("SCOPE_admin")`?

> No. With the default prefix, `hasRole("ADMIN")` checks `ROLE_ADMIN`.

**Question 9.** Does MockMvc `with(jwt())` prove production JWT signatures are verified?

> No. It simulates authentication to test authorization; integration tests with JWTs signed by test keys and a real decoder are needed.

**Question 10.** A new endpoint should be open only to authenticated users, but has no matcher yet and the fallback is `denyAll()`. What happens?

> The request is denied until a developer adds an explicit rule, consistent with a fail-closed policy.

## 25. References

- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `authorizeHttpRequests`, `permitAll`, `denyAll`, `hasAuthority`, and matcher ordering.
- [Spring Security — Java Configuration / Multiple SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `securityMatcher`, chain ordering, and applicability scope.
- [Spring Security — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT verification and scope → `SCOPE_*` authorities.
- [Spring Security — Bearer Tokens (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html): how bearer tokens are received and authentication behavior.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity` and `@PreAuthorize`.
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): preflight and `CorsConfigurationSource`.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF policy, especially with browsers/cookies.
- [Spring Security — Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): testing JWT authentication in MockMvc.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer authentication and `WWW-Authenticate`.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): claims and scope/audience semantics of JWT access tokens.

When designing HTTP authorization for a Resource Server, **explicitly declare which endpoints are public, which require authentication only, and which require specific authorities**, control matcher ordering, handle undeclared routes clearly, and always enforce resource-level permissions at the business layer. This is the foundation for an API that is both easy to use and free from accidental privilege expansion.
