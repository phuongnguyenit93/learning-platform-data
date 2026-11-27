# Paths When Token Is Missing, Invalid, or Insufficiently Scoped

## 1. One Endpoint, Three Different Rejection Causes

A Spring Boot API configured as an **OAuth 2.0 Resource Server** can receive three kinds of requests to the same endpoint:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
~~~

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer invalid.jwt.value
~~~

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <VALID_ACCESS_TOKEN_WITHOUT_ORDERS_READ>
~~~

If `GET /api/orders` requires scope `orders.read`, all three requests may be rejected, yet **the reasons and the paths through the Spring Security Servlet filter chain differ**:

1. **No token:** there is no authentication proof yet; the Bearer filter lets the chain continue, and authorization then blocks access to the protected endpoint.
2. **Token present but invalid:** the Bearer filter extracts the token and invokes authentication; authentication fails and typically returns an error directly from the Bearer authentication branch.
3. **Valid token but missing permissions:** authentication succeeds and builds an `Authentication`; authorization rules then deny access.

Under standard Spring Security Resource Server handling, the first two cases usually lead to **401 Unauthorized**, while the third usually leads to **403 Forbidden**. However, requests violating Bearer syntax per RFC 6750 can produce **400 Bad Request**, and public endpoints can allow unauthenticated requests to proceed.

**Lesson objective:** accurately trace requests in the **Servlet stack**, distinguish `BearerTokenAuthenticationFilter` from `AuthorizationFilter`, understand the roles of `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, and `AccessDeniedHandler`, and apply this to diagnose 400/401/403 responses.

## 2. The Servlet Security Filter Chain Model

Spring Security does not wait for the controller to look for tokens. Enforcement happens before the Spring MVC controller.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Servlet container"]
    B --> C["DelegatingFilterProxy"]
    C --> D["FilterChainProxy"]
    D --> E["Select first matching SecurityFilterChain"]
    E --> F["SecurityContextHolderFilter and supporting filters"]
    F --> G["BearerTokenAuthenticationFilter"]
    G --> H["Downstream security filters"]
    H --> I["ExceptionTranslationFilter"]
    I --> J["AuthorizationFilter"]
    J --> K["DispatcherServlet / Controller if permitted"]
~~~

The diagram highlights **relevant processing milestones**, not a fixed or exhaustive list of filters for every configuration. For instance, an app may also include CORS, CSRF, logout, request cache, custom filters, and filters for other login mechanisms.

Main components:

| Component | Role in the flow |
|---|---|
| `DelegatingFilterProxy` | Forwards calls from the Servlet container to the Spring Security bean |
| `FilterChainProxy` | Selects the first `SecurityFilterChain` matching the request |
| `SecurityFilterChain` | Defines the security filters that run for the request |
| `SecurityContextHolderFilter` | Prepares/manages `SecurityContext` for the request lifecycle |
| `BearerTokenAuthenticationFilter` | Extracts Bearer token and requests token authentication if a token is provided |
| `BearerTokenResolver` | Extracts the token from the request (default `Authorization: Bearer ...`) |
| `AuthenticationManager` | Dispatches the authentication request to a matching provider |
| `JwtAuthenticationProvider` | Validates JWTs via `JwtDecoder` and builds authentication |
| `OpaqueTokenAuthenticationProvider` | Validates opaque tokens via introspection |
| `AnonymousAuthenticationFilter` | Provides anonymous authentication when no principal exists, if enabled |
| `ExceptionTranslationFilter` | Converts authentication/authorization errors from downstream filters into appropriate responses |
| `AuthorizationFilter` | Decides whether to allow/deny the request via `AuthorizationManager` |

**Key point:** `BearerTokenAuthenticationFilter` handles Bearer token **authentication**; `AuthorizationFilter` performs **authorization**. `ExceptionTranslationFilter` helps translate exceptions from downstream filters, but is not the sole catch point for every Bearer authentication error.

### 2.1. Prerequisite: The Right SecurityFilterChain

If an application defines multiple `SecurityFilterChain`s, `FilterChainProxy` selects **the first chain matching the request**. If a request falls into a chain without Resource Server enabled, Bearer tokens may not be processed as expected.

For example:

~~~java
http.securityMatcher("/api/**");
~~~

means this chain applies only to requests matching `/api/**`. Meanwhile:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .anyRequest().authenticated()
);
~~~

defines **permission rules** once the chain has been selected.

Therefore, when analyzing a 401/403 response, first determine **which chain the request entered** before concluding there is an issue with the JWT.

## 3. Unified Example Configuration for All Scenarios

Assume an Orders API with these rules:

- `GET /api/orders` requires `orders.read`.
- `POST /api/orders` requires `orders.write`.
- `GET /api/public/ping` is accessible without authentication.
- The Resource Server validates **JWT access tokens** issued by a trusted issuer.
- The API accepts Bearer tokens in the `Authorization` header.

### 3.1. Dependencies

With Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

### 3.2. Issuer Configuration

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

This is an **illustrative** issuer. In real deployments, use your Authorization Server's real issuer, configure appropriate JWT verification keys, and verify the access token's `aud` per the Orders API contract.

When using `issuer-uri`, Spring Security uses the issuer's metadata to locate the public key / JWKS set. Do not assume this setting automatically guarantees every access token is meant for Orders API: **apply per-API audience validation** if not already configured.

### 3.3. SecurityFilterChain

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
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            // Appropriate only for APIs genuinely authenticating via Bearer tokens
            // outside cookies, without cookie/session login.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/orders", "/api/orders/**"
                ).hasAuthority("SCOPE_orders.read")
                .requestMatchers(
                    HttpMethod.POST, "/api/orders", "/api/orders/**"
                ).hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

The `oauth2ResourceServer(...jwt(...))` line enables JWT Bearer token authentication for this chain. You do not need to register `BearerTokenAuthenticationFilter` manually.

**Example scope limitation:** The `SecurityFilterChain` above only matches `/api/**`. A real application must ensure other paths also have appropriate protection policies, via another chain or a fallback chain. If a request matches no chain, Spring Security's security filters do not apply to that request.

### 3.4. HTTP Convention and Principal

Client sends:

~~~bash
curl -i \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  https://api.example.test/api/orders
~~~

Spring Security extracts the token string from the header, authenticates it, and maps scopes to authorities. Under the default configuration, scope `orders.read` produces authority `SCOPE_orders.read`, so `hasAuthority("SCOPE_orders.read")` checks the permission.

Assume a valid token has these illustrative claims:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 2000000000,
  "scope": "orders.read"
}
~~~

This is only an **illustrative JSON payload**, not a real signed JWT.

## 4. First Branch: Request Without a Bearer Token

### 4.1. What Does the Bearer Filter Do When There Is No Token?

Request:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
~~~

Typical flow:

~~~mermaid
sequenceDiagram
    participant Client
    participant Bearer as BearerTokenAuthenticationFilter
    participant Resolver as BearerTokenResolver
    participant Anonymous as AnonymousAuthenticationFilter
    participant Authorization as AuthorizationFilter
    participant Exception as ExceptionTranslationFilter
    participant Entry as AuthenticationEntryPoint

    Client->>Bearer: GET /api/orders (no token)
    Bearer->>Resolver: resolve(request)
    Resolver-->>Bearer: null
    Bearer->>Anonymous: continue filter chain
    Anonymous->>Authorization: anonymous principal (if enabled)
    Authorization-->>Exception: AccessDeniedException
    Exception->>Entry: commence(request, response, exception)
    Entry-->>Client: 401 + WWW-Authenticate: Bearer
~~~

Some filters in the diagram are simplified to highlight the business branch. In actual execution order, `ExceptionTranslationFilter` sits before `AuthorizationFilter` and catches exceptions thrown further down the filter chain. `AnonymousAuthenticationFilter` typically runs before those two components.

**Detail to remember:** `BearerTokenAuthenticationFilter` **does not throw an error** merely because no token was found. It calls `FilterChain.doFilter(...)` to continue. It is the `hasAuthority(...)` or `authenticated()` rule at the authorization stage that prevents an anonymous request from entering a protected endpoint.

### 4.2. Does `AnonymousAuthenticationFilter` Mean Logged In?

No. This filter can place an `AnonymousAuthenticationToken` so the system has a uniform representation for unauthenticated requests. This anonymous token **is not treated as a logged-in user** when checking `authenticated()`.

For example:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .requestMatchers("/api/orders/**").authenticated()
);
~~~

An unauthenticated request to `/api/orders/42` does not satisfy `authenticated()` even though an anonymous principal may exist in `SecurityContext`.

Checking `authentication != null` yourself and treating that as a valid login fails when anonymous authentication is enabled. Use Spring Security's authorization rules or an appropriate `AuthenticationTrustResolver`.

### 4.3. Why Does Missing a Token Usually Return 401?

When authorization denies an insufficiently authenticated request, `ExceptionTranslationFilter` identifies the caller as anonymous and invokes **`AuthenticationEntryPoint`** to request authentication.

For a Bearer Resource Server, the typical entry point is `BearerTokenAuthenticationEntryPoint`. The response may be:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

When the client simply **did not send a token**, RFC 6750 recommends omitting error codes such as `invalid_token` from the challenge. Therefore, do not assume every 401 carries `error="invalid_token"`.

### 4.4. No Token on a `permitAll` Endpoint

Request:

~~~http
GET /api/public/ping HTTP/1.1
Host: api.example.test
~~~

With `permitAll()`, a request without a Bearer token passes straight to the controller and receives `200 OK`. Having `BearerTokenAuthenticationFilter` in the chain does not mean **every endpoint in the chain must supply a token**.

That is why an API can share one filter chain for both public endpoints and scope-protected endpoints: **the authentication filter runs, while authorization policies differ per endpoint**.

## 5. Second Branch: Token Present but Invalid

### 5.1. Invalid Token vs. Missing Token Take Two Different Branches

Request:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer invalid.jwt.value
~~~

`BearerTokenResolver` can extract the string `invalid.jwt.value` because the header uses the Bearer format. The filter then executes:

~~~text
BearerTokenAuthenticationFilter
    |
    v
BearerTokenResolver -> "invalid.jwt.value"
    |
    v
BearerTokenAuthenticationToken
    |
    v
AuthenticationManager
    |
    v
JwtAuthenticationProvider
    |
    v
JwtDecoder
    |
    v
Authentication failed
    |
    v
AuthenticationFailureHandler / Bearer entry point
    |
    v
401 Unauthorized (usually with invalid_token)
~~~

In this branch, failure occurs **inside Bearer authentication** before the request ever reaches `AuthorizationFilter`. Thus, claiming "every 401 comes from `AuthorizationFilter` denying access" is incorrect.

During failure handling, the filter clears/manages `SecurityContext` via Spring Security's mechanism so a failed authentication is never used as a principal for the request.

### 5.2. Common Reasons a JWT Is Invalid

| Issue | Stage typically detecting | Behavior |
|---|---|---|
| String is not a valid JWS JWT per contract | JWT parser/decoder | Authentication failure |
| Signature does not match a trusted key | `JwtDecoder` | Authentication failure |
| Token expired (`exp`) | `JwtDecoder`/validator | Authentication failure |
| Token not yet valid (`nbf`) | `JwtDecoder`/validator | Authentication failure |
| Wrong issuer (`iss`) | Issuer validator | Authentication failure |
| Wrong audience (`aud`), when validator configured | Audience validator | Authentication failure |
| Disallowed JWS algorithm | Decoder/signature verifier | Authentication failure |
| Token missing mandatory claim per contract | Custom validator | Authentication failure |
| ID Token sent instead of access token | Audience/`typ`/token-profile checks | Must be rejected |
| Opaque token revoked or inactive | Opaque token introspector | Authentication failure |

For JWT access tokens, Spring Security typically includes basic checks such as signature, issuer, and timestamps per configuration. Audience, token type, and custom claims must be verified against your profile/version and application configuration. Never assume a valid signature alone suffices to accept any JWT.

### 5.3. Errors When Extracting the Bearer Token

If the header has invalid syntax or the request supplies Bearer credentials from multiple disallowed sources, **`DefaultBearerTokenResolver`** can throw `OAuth2AuthenticationException` before creating `BearerTokenAuthenticationToken`.

Example of a malformed request:

~~~http
Authorization: Bearer token1, Bearer token2
~~~

This is **not** a valid way to pass multiple tokens to one API. Per `BearerTokenResolver` and the Bearer specification, the error may be classified as `invalid_request` rather than `invalid_token`.

Do not casually lump every resolver-stage error into "invalid JWT signature," since the resolver **has not inspected any JWT yet**.

### 5.4. 400 and 401 Are Not Synonymous

RFC 6750 defines key Bearer error codes:

| Error code | Meaning | Typical HTTP status |
|---|---|---|
| `invalid_request` | Malformed Bearer request, unsupported/duplicate parameters or sources | **400 Bad Request** |
| `invalid_token` | Token expired, revoked, malformed, or otherwise invalid | **401 Unauthorized** |
| `insufficient_scope` | Access token is valid, but lacks the required scope | **403 Forbidden** |

In Spring Security, `BearerTokenAuthenticationEntryPoint` can inspect `BearerTokenError` to choose the appropriate status and header. Thus **a syntactically invalid Bearer header may return 400**, whereas a syntactically valid token that fails validation usually returns 401.

Not every non-Bearer header automatically produces 400. For instance, `Authorization: Basic abc` may simply be treated by the resolver as **no Bearer token present**, causing a protected endpoint to return 401 because it is unauthenticated. Exact behavior depends on syntax, token source, resolver, and active configuration.

### 5.5. Example Authentication Error Headers

When a token is provided but invalid, the Bearer response may be:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

When a Bearer formatting error is classified as `invalid_request`:

~~~http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer error="invalid_request"
~~~

These examples only illustrate response shapes; headers may include `realm`, `error_description`, or other fields per configuration, and some reverse proxies may alter responses. Never return full tokens or sensitive claims in error responses.

## 6. Third Branch: Valid Token, Missing Permissions

### 6.1. Successful Authentication Does Not Guarantee Endpoint Access

Suppose a token is signed by a trusted issuer and valid, yet carries only the `profile` scope:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 2000000000,
  "scope": "profile"
}
~~~

If this is a real, properly signed token passing all validators, Bearer authentication **succeeds**. Spring Security constructs an authenticated `Authentication` and stores it in `SecurityContext`.

However, `GET /api/orders` requires:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

Because the authority is missing, `AuthorizationFilter` denies the request.

~~~mermaid
sequenceDiagram
    participant Client
    participant Bearer as BearerTokenAuthenticationFilter
    participant Decoder as JwtDecoder
    participant Context as SecurityContext
    participant Authorization as AuthorizationFilter
    participant Exception as ExceptionTranslationFilter
    participant Handler as AccessDeniedHandler

    Client->>Bearer: GET /api/orders + Bearer token
    Bearer->>Decoder: validate JWT
    Decoder-->>Bearer: valid token
    Bearer->>Context: store JwtAuthenticationToken
    Bearer->>Authorization: continue filter chain
    Authorization->>Context: read authorities
    Context-->>Authorization: SCOPE_profile
    Authorization-->>Exception: AccessDeniedException
    Exception->>Handler: handle(request, response, exception)
    Handler-->>Client: 403 Forbidden
~~~

This is an **authorization failure**. The Resource Server identified the caller, yet the caller lacks permission to invoke the endpoint.

### 6.2. `BearerTokenAccessDeniedHandler` and `insufficient_scope`

Spring Security Resource Server provides **`BearerTokenAccessDeniedHandler`** to handle access denials in a Bearer token context. When a request holds a valid OAuth 2.0 authentication and is denied permission, the handler can return:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Depending on the situation and current authentication, the handler may return a challenge without `insufficient_scope`. Do not assume every `403`, especially from a controller or gateway, carries that header.

### 6.3. Scope Differs from Data Ownership

A token with scope `orders.read` may pass the endpoint rule, yet the user may still only view orders belonging to their tenant.

For example:

~~~http
GET /api/orders/123 HTTP/1.1
Authorization: Bearer <VALID_TOKEN_WITH_ORDERS_READ>
~~~

Steps:

1. Token is valid → Bearer authentication succeeds.
2. Has `SCOPE_orders.read` → endpoint authorization allows it.
3. Service checks which tenant/subject owns order 123.
4. If the caller lacks permission for order 123, the business layer can return **403**, or **404** if the API follows a policy not to disclose resource existence.

**A 403 at the business layer** does not mean `BearerTokenAuthenticationFilter` or `AuthorizationFilter` failed; the request passed both.

### 6.4. Scopes and Roles Are Two Different Kinds of Permissions

By default, Spring Security maps token scopes like `orders.read` to authority `SCOPE_orders.read`. If an organization uses custom roles like `roles: ["ADMIN"]`, that claim **does not automatically become** `ROLE_ADMIN` or `SCOPE_orders.read` in all configurations.

To use custom roles or permissions, configure a `JwtAuthenticationConverter` or explicit mapping policy. A valid token with mismatched authority names can cause 403; never fix this by disabling authorization.

## 7. `ExceptionTranslationFilter`: When EntryPoint vs. AccessDeniedHandler Is Invoked

`ExceptionTranslationFilter` converts **`AuthenticationException`** or **`AccessDeniedException`** from downstream processing into an HTTP response via the appropriate security handler.

Main handling paths:

| Scenario | Terminating component | Meaning |
|---|---|---|
| No valid authentication on a protected endpoint | `AuthenticationEntryPoint` | Prompts client for credentials; usually 401 for Bearer |
| Properly authenticated request denied permission | `AccessDeniedHandler` | Signals insufficient rights; usually 403 |
| Token fails directly inside `BearerTokenAuthenticationFilter` | Bearer filter's failure handler/entry point | Usually 401, or 400 for malformed Bearer requests |

Pay attention to **filter ordering**: `BearerTokenAuthenticationFilter` normally runs **before `ExceptionTranslationFilter`**. Therefore, errors occurring inside the Bearer filter are handled by the Bearer filter's own failure handling, rather than waiting for `ExceptionTranslationFilter` to catch them downstream.

### 7.1. Logic When Catching AccessDeniedException

When `AuthorizationFilter` or downstream protection logic throws `AccessDeniedException`:

- If the caller is not fully authenticated (e.g., anonymous), `ExceptionTranslationFilter` uses **`AuthenticationEntryPoint`** to return a 401 challenge.
- If the caller is authenticated yet lacks permission, it uses **`AccessDeniedHandler`** to return 403.

That is why the exact same `AccessDeniedException` class can lead to **401** or **403** depending on authentication status. This aligns with HTTP semantics: **not validly authenticated** versus **authenticated but forbidden**.

### 7.2. Default Entry Point and Denied Handler for Bearer

In a Resource Server, the standard components are:

~~~java
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
~~~

When configuring `oauth2ResourceServer(...)`, Spring Security applies the appropriate Bearer error handling automatically. In the default configuration, **you do not need to recreate these two handlers just to get 401/403**.

You can specify them explicitly when you need customization:

~~~java
http.exceptionHandling(exceptions -> exceptions
    .authenticationEntryPoint(
        new BearerTokenAuthenticationEntryPoint()
    )
    .accessDeniedHandler(
        new BearerTokenAccessDeniedHandler()
    )
);
~~~

The snippet illustrates Resource Server handlers. In applications with multiple login mechanisms or multiple security chains, attach handlers carefully to the **API request chain** to avoid unintentionally replacing browser/OIDC login entry points.

### 7.3. Do Not Force Every Error into the Same Status Code

A custom configuration like "return 401 whenever any security exception occurs" erases an important distinction:

- Clients cannot tell whether the token needs to be re-issued or the caller needs more scopes.
- Logs and monitoring cannot separate authentication from authorization.
- Behavior diverges from RFC 6750 semantics for `invalid_request`, `invalid_token`, and `insufficient_scope`.

If the API uses a custom JSON error format, customize the response body while keeping the appropriate HTTP status and `WWW-Authenticate` header.

## 8. 400, 401, and 403 Decision Table

Assume a JWT Resource Server where `GET /api/orders` requires `SCOPE_orders.read`:

| Input | Token processing | Permission check | Typical HTTP status |
|---|---|---|---|
| No `Authorization` header | No Bearer token | Anonymous denied | **401** |
| `Authorization: Basic ...` | Not treated as a Bearer token | No Bearer authentication | **401** if no other auth applies |
| `Authorization: Bearer invalid.jwt.value` | JWT validation fails | Does not reach authorization | **401** |
| Expired Bearer token | Timestamp validator rejects | Does not reach authorization | **401** |
| Bearer token with wrong signature | Decoder rejects | Does not reach authorization | **401** |
| Bearer token with wrong issuer | Issuer validator rejects | Does not reach authorization | **401** |
| Bearer token with wrong audience and audience validator enabled | Audience validator rejects | Does not reach authorization | **401** |
| Malformed Bearer request classified as `invalid_request` | Resolver rejects | Does not reach authorization | **400** |
| Valid JWT, `scope: "profile"` | Authentication succeeds | Missing `SCOPE_orders.read` | **403** |
| Valid JWT with `orders.read` | Authentication succeeds | Endpoint rule allows | Possibly **200** |
| Valid JWT with scope, wrong tenant | Authentication succeeds | Data permission denied | **403** or **404** |
| No token, `GET /api/public/ping` | No Bearer authentication | `permitAll` | Possibly **200** |
| Invalid token, `GET /api/public/ping` in same chain | Bearer authentication may fail before authorization | Does not reach `permitAll` | Usually **401** |

These are **typical** outcomes, not absolute guarantees for every application. Gateways, custom filters, exception handlers, Spring versions, and business rules can alter specific response details.

**Most easily confused case:** `permitAll` only skips **endpoint authorization rules**; it does not disable `BearerTokenAuthenticationFilter` for that request.

## 9. Why Can a `permitAll` Endpoint Still Return 401?

Suppose a chain contains:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .anyRequest().authenticated()
)
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
);
~~~

Request without a token:

~~~http
GET /api/public/ping HTTP/1.1
~~~

The Bearer filter finds no token and lets the request pass. `AuthorizationFilter` hits `permitAll`, so the request is allowed.

However, for this request:

~~~http
GET /api/public/ping HTTP/1.1
Authorization: Bearer broken.token
~~~

The Bearer filter **sees a Bearer token** and attempts to authenticate it. When authentication fails, the filter returns an error before the request ever reaches `AuthorizationFilter`. Thus a public endpoint can still return **401**.

This is a consequence of the authentication pipeline, not a bug in `permitAll`.

If a public area must **completely bypass Bearer authentication**, design a separate `SecurityFilterChain` with an explicit matcher and ordering. Evaluate this alongside all routes so protected endpoints are never accidentally left outside appropriate chains.

## 10. Multiple SecurityFilterChains: An Overlooked Source of Errors

In an application with both web login and token APIs, an API request sometimes hits the **wrong chain**.

Architectural illustration:

~~~mermaid
flowchart TD
    A["Request"] --> B["FilterChainProxy"]
    B --> C{"Matches first chain?"}
    C -->|"/api/**"| D["API chain: Bearer Resource Server"]
    C -->|"No"| E["Fallback chain: Web / other policy"]
    D --> F["Bearer auth + API authorization"]
    E --> G["Web login / denyAll / other policy"]
~~~

Suppose a broad `/**` chain has higher priority than the `/api/**` chain. Because `FilterChainProxy` picks the **first matching chain**, the `/**` chain catches every request and the API chain never runs.

Consequences can include:

- The API returns a **302 redirect** to a login page because it uses the browser login entry point.
- The API never reads Bearer tokens.
- A valid Bearer header still returns 401/403 from another mechanism.
- Scope rules intended for `/api/**` never apply.

Two-chain example:

~~~java
@Configuration
public class SplitSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            );
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll()
            );
        return http.build();
    }
}
~~~

This code is an **alternative example** to the single-chain configuration earlier; do not place both in the same application simultaneously without adjustment. Imports can be taken from the earlier configuration, adding `org.springframework.core.annotation.Order`.

**A request executes only the first matching security chain.** Therefore, diagnosing 401/403 accurately starts with matchers and chain order before tracing the Bearer filter.

## 11. JWT and Opaque Tokens: Similar HTTP Failure Branches, Different Internals

### 11.1. JWT Access Token

~~~text
BearerTokenAuthenticationFilter
    |
    v
JwtAuthenticationProvider
    |
    v
JwtDecoder
    |
    +-- invalid signature -> authentication failure
    +-- wrong issuer -> authentication failure
    +-- expired token -> authentication failure
    +-- wrong audience (if validator configured) -> authentication failure
    |
    v
JwtAuthenticationToken
    |
    v
AuthorizationFilter
~~~

The JWT decoder verifies signatures against the issuer's public keys/JWKS and runs claim validators. Base64URL-decoding claims alone never proves a token is valid.

### 11.2. Opaque Access Token

~~~text
BearerTokenAuthenticationFilter
    |
    v
OpaqueTokenAuthenticationProvider
    |
    v
OpaqueTokenIntrospector
    |
    +-- active=false / invalid -> authentication failure
    +-- active=true + attributes -> Authentication
    |
    v
AuthorizationFilter
~~~

With opaque tokens, the Resource Server can use `oauth2ResourceServer(...opaqueToken(...))` to call the introspection endpoint per contract. Expired, revoked, or inactive tokens normally result in authentication failures.

If the introspection endpoint is **unreachable**, times out, or hits an infrastructure error, the outcome may be a service error distinct from `invalid_token`; do not automatically assume every network failure means an invalid token. Handle availability and incident observability appropriately per configuration.

### 11.3. An OIDC ID Token Is Not a Bearer Access Token for APIs

An OIDC **ID Token** is issued to an OIDC client to prove user authentication, typically with the client ID as its audience. A Resource Server must accept **access tokens intended for the API**.

If a client sends an ID Token:

~~~http
Authorization: Bearer <OIDC_ID_TOKEN>
~~~

the API must reject it based on audience, token type, or token profile requirements, even if that JWT carries a valid signature from the same issuer. Never "fix" 401 by removing audience validation.

## 12. Differences with CORS Preflight and CSRF

### 12.1. CORS Preflight Requests Usually Carry No Bearer Token

A browser may send:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://shop.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflight checks CORS policy and typically **carries no access token**. If the application requires Bearer authentication before handling preflight, the frontend reports a CORS error even when the real request's access token is valid.

Spring Security integrates CORS via:

~~~java
http.cors(Customizer.withDefaults());
~~~

The application must also supply a CORS configuration matching real origins/methods/headers, such as a `CorsConfigurationSource`. CORS must run in the proper order before authentication for preflight requests.

**Do not confuse CORS errors with an invalid JWT.** When preflight is rejected, the browser never sends the actual GET/POST request, so the Bearer filter never even sees the intended access token.

### 12.2. CSRF and Non-Cookie Tokens

Disabling CSRF on the API chain is only appropriate when authentication truly relies on **Bearer tokens actively sent by the client without cookies automatically attaching credentials**. If the frontend/web app still uses login cookies, assess CSRF risk and configure proper protection.

A 403 response can also originate from **`CsrfFilter`** before endpoint authorization ever runs. Never conclude "403 definitely means missing scope" without knowing which filter/handler produced the response.

## 13. Does Altering Status Codes Make the System Safer?

Do not "turn 401 into 403" or "turn 403 into 401" by catching all exceptions generically just to appease one client. HTTP status codes reflect the stage of failure and aid diagnostics.

### 13.1. `AuthenticationEntryPoint`

Used when authentication is required/challenged or when Bearer authentication fails per its mechanism.

Under RFC 6750, responses usually include `WWW-Authenticate: Bearer` so clients know the scheme. When an access token was sent but is invalid, `error="invalid_token"` may be included.

### 13.2. `AccessDeniedHandler`

Used when an authenticated request is denied permission. `BearerTokenAccessDeniedHandler` supports Bearer responses with `insufficient_scope` under matching conditions.

### 13.3. Custom JSON Bodies

An API may want a body like:

~~~json
{
  "code": "ACCESS_DENIED",
  "message": "Permission required",
  "traceId": "trace-123"
}
~~~

That is a **response format** decision. When customizing a handler to write JSON, preserve the exact status and headers and avoid leaking tokens or secrets into the body or logs.

Never disclose details such as "which key failed signature," "which account has permission," or "which password/certificate was invalid" in public responses.

## 14. Accurately Observing Request Flow

### 14.1. Reading Logs During Development

Enable debug logging in local/dev environments:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Logs can reveal which filter chain was selected, the protected request, and why authentication or authorization failed. `TRACE` adds even more detail if truly needed, at the cost of noise and higher risk of logging sensitive data.

Avoid logging raw Bearer tokens, `Authorization` headers, full introspection responses, or secrets/JWKS private keys. In production, log error codes, endpoints, correlation IDs, and non-sensitive metadata.

### 14.2. Order for Diagnosing 401

1. Did the request enter the right `SecurityFilterChain`?
2. Did `BearerTokenResolver` inspect the right header source?
3. Was the token sent as `Authorization: Bearer <token>`?
4. Is it a request syntax error (`invalid_request`) or a token content error (`invalid_token`)?
5. Does the JWT match the contracted issuer, signature, algorithm, expiration, and audience/profile?
6. If opaque, did the introspection endpoint return active, or was there a connection failure?
7. If multiple authentication entry points exist, which handler generated the response?

This sequence identifies **which layer failed**. Never downgrade endpoints to `permitAll` or disable JWT validation just to make 401s disappear.

### 14.3. Order for Diagnosing 403

1. Did the token authenticate successfully?
2. Which `requestMatchers` rule applies?
3. Which authority was the `scope` claim mapped to? Is the name `SCOPE_orders.read` exact?
4. Are custom roles/authorities using a different prefix?
5. Was the request denied by `AuthorizationFilter`, `CsrfFilter`, method security, or a business service?
6. Are there owner/tenant or record-level ACL checks?

A 403 can originate from multiple layers; pinpoint where the decision occurred instead of looking only at the HTTP status.

### 14.4. Testing Rules vs. Testing the Bearer Pipeline Are Two Different Scopes

In Spring Security Test, MockMvc's `jwt()` usually creates a synthetic authentication to test authorization, for example:

~~~java
mockMvc.perform(
    get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        ))
);
~~~

This is useful for testing rules, yet **does not prove on its own** that real Bearer tokens are extracted from HTTP headers, JWT signatures are verified, and claim validators execute properly.

For the full flow, integration tests should send test tokens in real headers against a controlled test issuer/JWK set and verify missing tokens, expired tokens, bad signatures, wrong audiences, missing scopes, and malformed headers. Never use production tokens in tests.

## 15. Practice Matrix with curl

Use placeholders; real tokens must come from a test Authorization Server with the Orders API audience.

### Case A — No Token

~~~bash
curl -i https://api.example.test/api/orders
~~~

**Expected:** 401 when the endpoint requires Bearer authentication. The header may be `WWW-Authenticate: Bearer` with no error code.

### Case B — Invalid JWT

~~~bash
curl -i \
  -H "Authorization: Bearer invalid.jwt.value" \
  https://api.example.test/api/orders
~~~

**Expected:** 401 with a token validation error (usually `invalid_token`).

### Case C — Valid Token Missing Scope

~~~bash
curl -i \
  -H "Authorization: Bearer <TOKEN_SCOPE_PROFILE_ONLY>" \
  https://api.example.test/api/orders
~~~

**Expected:** 403 because it is authenticated but lacks `orders.read`. With appropriate Bearer access denied handling, `insufficient_scope` may appear.

### Case D — Sufficient Scope

~~~bash
curl -i \
  -H "Authorization: Bearer <TOKEN_SCOPE_ORDERS_READ>" \
  https://api.example.test/api/orders
~~~

**Expected:** endpoint authorization allows it and the controller runs; final status depends on application logic.

### Case E — Public Endpoint, No Token

~~~bash
curl -i https://api.example.test/api/public/ping
~~~

**Expected:** `permitAll` endpoint is accessible unless blocked by another filter or policy.

### Case F — Public Endpoint, Invalid Token

~~~bash
curl -i \
  -H "Authorization: Bearer invalid.jwt.value" \
  https://api.example.test/api/public/ping
~~~

**Expected:** may return 401 despite `permitAll`, because the Bearer filter processes the invalid token before authorization.

### Case G — Malformed Bearer Request

~~~bash
curl -i \
  -H "Authorization: Bearer token1, Bearer token2" \
  https://api.example.test/api/orders
~~~

**Expected:** malformed Bearer request; the resolver may classify it as `invalid_request` and return 400. Exact behavior depends on the resolver and syntax; send a single valid access token per request per contract.

## 16. Real-World Scenario: Same Caller, Different Statuses

Suppose the frontend calls:

~~~text
GET /api/orders/42
~~~

Contract:

- Access tokens must have a trusted issuer and audience `orders-api`.
- The GET endpoint requires `SCOPE_orders.read`.
- Order 42 belongs to `tenant-A`.
- A caller belonging to `tenant-B` must not view order 42.

Corresponding requests:

| Token / state | Detection point | Expected response |
|---|---|---|
| No token | Authorization requires an authenticated caller | 401 |
| Expired token | Bearer authentication / `JwtDecoder` | 401 |
| Wrong `aud` token | `JwtDecoder` with audience validator | 401 |
| Right audience, only `orders.write` | Authorization rule lacks `orders.read` | 403 |
| Has `orders.read`, belongs to `tenant-B` | Service / ownership policy | 403 or 404 |
| Valid token, `orders.read`, belongs to `tenant-A` | Passes security and business checks | Returns appropriate data, usually 200 |

**Do not use email or display name in place of ownership checks against verified `sub`/tenant.** When a service has multi-tenancy logic, determine ownership from trusted data and business policies.

## 17. Common Misconceptions

### 17.1. "Missing Token and Invalid Token Both Return 401, So They Are Identical"

Their execution paths differ. A missing token lets the Bearer filter pass the request along so authorization issues a challenge. An invalid token is extracted and rejected directly during authentication. Knowing the difference helps pinpoint what to fix.

### 17.2. "403 Means the JWT Failed Verification"

Usually false on Bearer endpoints with scope rules. A bad signature or expired JWT normally returns 401 at authentication. A 403 typically means the token was valid yet failed authorization, or another filter/policy such as CSRF denied it.

### 17.3. "Setting `permitAll` Skips the Bearer Filter"

Incorrect. `permitAll` is purely an authorization rule. If the chain still enables Resource Server and the request carries an invalid Bearer token, an authentication failure can occur before authorization reaches that rule.

### 17.4. "Every 401 Is Caught by `ExceptionTranslationFilter`"

Incorrect. Bearer token failures inside `BearerTokenAuthenticationFilter` are handled by the filter's own failure handler/entry point. `ExceptionTranslationFilter` handles exceptions thrown in the downstream chain it wraps.

### 17.5. "Any `Authentication` in SecurityContext Means an Authenticated User"

Not necessarily. It could be an anonymous authentication. Rely on `authenticated()`/authorities policies and the right principal type.

### 17.6. "Adding a Scope to the JWT Payload Grants Permission"

Editing the JWT payload invalidates the signature. Scopes must be issued by the Authorization Server and verified by the Resource Server. Beyond scopes, audience and per-resource permissions still apply.

### 17.7. "Disabling CSRF Fixes 403 Errors"

Only disable CSRF when the API design genuinely does not rely on browser cookies/sessions; a 403 can also come from authorities, ownership, or another filter. Applying the wrong fix weakens application protection.

### 17.8. "A Validly Signed ID Token Works to Call APIs"

No. ID Tokens are meant for OIDC clients; APIs must accept **access tokens intended for that API**, checking audience, token type, and profile per contract.

## 18. Key Takeaways to Apply

Whenever a request is rejected, tie the outcome to its **stage in the Servlet chain**:

~~~text
FilterChainProxy selects SecurityFilterChain
               |
               v
BearerTokenAuthenticationFilter
  |           |
  |           +-- Token present but invalid -> authentication failure -> 401
  |                 (malformed Bearer request may -> 400)
  |
  +-- No token -> continue, no authenticated principal yet
  |
  +-- Valid token -> SecurityContext holds Authentication
               |
               v
AuthorizationFilter / business permissions
  |           |
  |           +-- Unauthenticated + protected endpoint -> 401
  |           +-- Authenticated but missing permissions -> 403
  |           +-- Authorized -> controller, then business access checks
~~~

- **401**: request requires authentication or the supplied token is invalid.
- **400**: certain **`invalid_request`** errors from malformed Bearer requests.
- **403**: caller is authenticated but not permitted; can also stem from another policy/filter such as CSRF.
- `AuthenticationEntryPoint` and `AccessDeniedHandler` produce the appropriate response for each branch.
- `SecurityFilterChain` configuration, matchers, and chain ordering determine whether Bearer processing runs at all.
- Scopes inside a token only assist policy-level authorization; object-level permissions must still be verified during business processing.

### References

- [Spring Security Reference — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security API — BearerTokenAuthenticationFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/authentication/BearerTokenAuthenticationFilter.html)
- [Spring Security API — BearerTokenAuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html)
- [Spring Security API — BearerTokenAccessDeniedHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/access/BearerTokenAccessDeniedHandler.html)
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
