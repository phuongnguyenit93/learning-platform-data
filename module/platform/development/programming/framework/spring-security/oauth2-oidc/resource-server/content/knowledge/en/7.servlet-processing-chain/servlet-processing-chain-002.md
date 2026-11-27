# BearerTokenAuthenticationFilter and Extracting Tokens from Requests

In a **Spring Security OAuth 2.0 Resource Server application running on the Servlet stack**, clients typically call the API with an access token in an HTTP header:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

A request carrying a token **is not automatically authenticated**. The filter chain must locate the credential, pass it to the appropriate authenticator, verify its validity, and place the authenticated information into `SecurityContext` before evaluating permissions.

**`BearerTokenAuthenticationFilter`** is the component that handles Bearer requests in a Spring Security Servlet Resource Server. The filter's primary responsibility is to **extract the bearer token from the request and initiate the authentication process**. It does not decode every type of JWT itself, does not perform signature verification or introspection itself, and does not directly decide whether a client has permission to read an order. Those tasks belong to downstream components.

Running example throughout this lesson:

- Authorization Server: `https://login.example.com`.
- Resource Server: Orders API at `https://api.example.com`.
- Expected resource/audience: `orders-api`.
- Order read permission: OAuth scope `orders.read`, mapped to authority `SCOPE_orders.read`.
- Application running Spring Boot 3.x / Spring Security 6.x with Servlet/Spring MVC; specific APIs and versions should be verified during integration.

## 1. Components of the Servlet Security Filter Chain

In Servlet applications, Spring Security connects to the Servlet container through `DelegatingFilterProxy`, which delegates to `FilterChainProxy`. `FilterChainProxy` selects a matching `SecurityFilterChain` for the request and executes the security filters configured in that chain.

| Component | Responsibility |
|---|---|
| `DelegatingFilterProxy` | Bridges the Servlet filter chain with Spring Security beans. |
| `FilterChainProxy` | Selects the first security filter chain matching the request. |
| `SecurityFilterChain` | Defines the security filters applying to a group of URLs. |
| `BearerTokenAuthenticationFilter` | Extracts the Bearer token using `BearerTokenResolver`; invokes authentication and updates `SecurityContext` on success. |
| `BearerTokenResolver` | Determines which header or configured source the Bearer token is extracted from. |
| `BearerTokenAuthenticationToken` | Initial `Authentication` object carrying the **unauthenticated** token string. |
| `AuthenticationManager` / `AuthenticationProvider` | Coordinates and performs token authentication. |
| `JwtDecoder` | Verifies the signature and claims of a JWT access token according to the issuer/RS contract. |
| `OpaqueTokenIntrospector` | Validates an opaque access token via introspection or an appropriate custom mechanism. |
| `SecurityContextHolder` | Provides the authenticated `Authentication` for the request. |
| `AuthorizationFilter` | Evaluates permission to invoke the endpoint once an appropriate authentication is present. |

This lesson covers the **Servlet stack**. **WebFlux** applications use `SecurityWebFilterChain` and a different reactive mechanism; Servlet `BearerTokenAuthenticationFilter` is not used directly.

### 1.1. From Request to Controller

```mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant F as BearerTokenAuthenticationFilter
    participant R as BearerTokenResolver
    participant M as AuthenticationManager
    participant P as Jwt/opaque Provider
    participant A as AuthorizationFilter
    participant API as API Controller
    C->>F: GET /api/orders, Authorization: Bearer token
    F->>R: resolve(request)
    R-->>F: token or null / error
    alt Bearer token present
        F->>M: BearerTokenAuthenticationToken
        M->>P: authenticate(...)
        P->>P: JWT verification or introspection
        P-->>M: Authenticated Authentication
        M-->>F: Authenticated Authentication
        F->>F: Store in SecurityContext
    else No Bearer token
        F->>F: Do not create Bearer Authentication
    end
    F->>A: Continue filter chain
    A->>A: Check authenticated/scope/authority
    alt Allowed
        A->>API: Run controller
    else Denied
        A-->>C: 401 or 403 depending on scenario
    end
```

The diagram depicts **processing relationships** rather than locking down the exact absolute position of every filter. Filters such as CORS, CSRF, Anonymous, and ExceptionTranslation have presence and exact ordering depending on configuration and version. The core principle is that Bearer authentication must occur **before** the endpoint authorization step.

### 1.2. Why Knowing Which Chain Matches Matters

When an application configures multiple `SecurityFilterChain`s, `FilterChainProxy` selects **the first chain with a matching matcher**, rather than running all of them in sequence.

For example, `/api/**` uses JWT while `/web/**` uses session/OIDC login: the Bearer filter is only used for requests whose matching chain enables `oauth2ResourceServer(...)`. If a broader chain is ordered earlier and matches `/api/orders`, the API may bypass the Bearer filter unexpectedly.

## 2. BearerTokenResolver: Extracting the Token from the Request

The filter does not guess where the credential is located. It calls:

```java
String token = bearerTokenResolver.resolve(request);
```

This expresses the responsibility of the `BearerTokenResolver` interface. Outcomes:

- **Token string returned:** proceed to authentication.
- **`null`:** no accepted Bearer credential was found; the filter lets the request continue.
- **`OAuth2AuthenticationException`:** the request violates Bearer rules; the filter handles the authentication failure.

Spring Security uses `DefaultBearerTokenResolver` by default. The standard enabled token source is:

```http
Authorization: Bearer ACCESS_TOKEN_VALUE
```

Bearer tokens are specified in **RFC 6750**. The filter does not expect clients to send `sub` or `scope` claims in separate headers; claims must come from verified tokens or metadata.

### 2.1. Token in the Authorization Header

Example:

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
Accept: application/json
```

Parts:

- `Authorization`: HTTP header name.
- `Bearer`: authentication scheme.
- `ACCESS_TOKEN_VALUE`: credential passed to `AuthenticationManager`.
- Do not wrap the token value in arbitrary quotes or add extra prefixes.

With sender-unconstrained Bearer tokens, **anyone possessing a valid token can use it** within its granted permissions. Therefore, always use TLS/HTTPS, mask tokens in logs, and limit scopes, audiences, and lifetimes.

### 2.2. Does Not Read Tokens from URLs or Forms by Default

| Source | Example | Enabled by default? | Notes |
|---|---|---|---|
| Authorization header | `Authorization: Bearer abc` | **Yes** | Standard source, easy to integrate, lower risk of leaking into access logs than URLs. |
| URI query parameter | `/orders?access_token=abc` | **No** | Easily leaked via logs, browser history, referrer headers, and shared links. |
| Form-encoded body | `access_token=abc` in form body | **No** | Only applicable when protocol conditions are met; should not be enabled casually. |
| Arbitrary cookie | `Cookie: access_token=abc` | **No** | Cookie-authenticated flows introduce different CSRF considerations. |
| Custom header | `X-Token: abc` | **No** | Requires a dedicated resolver/policy; no standard OAuth Bearer interoperability. |

`DefaultBearerTokenResolver` can be configured with:

```java
DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
resolver.setAllowFormEncodedBodyParameter(false);
resolver.setAllowUriQueryParameter(false);
```

These two `false` values are already the default policy, written explicitly here to emphasize that the API only accepts tokens through the standard header.

**Do not enable query tokens just to work around a client bug.** Tokens in URLs are easily recorded by proxies, CDNs, analytics, or access loggers even when the HTTP request is sent over TLS.

### 2.3. Missing Token vs. Invalid Token

A request with no Bearer token at all:

```http
GET /api/orders HTTP/1.1
Host: api.example.com
```

usually causes `resolve()` to return `null`. The filter **does not create authentication on its own**; it continues the chain. If the endpoint requires an authenticated principal, authorization steps will reject the request (typically `401`).

By contrast:

```http
Authorization: Bearer INVALID_TOKEN
```

may be syntactically extracted by the resolver yet rejected by the decoder/provider due to signature, issuer, audience, or expiration. That is an **authentication error**, typically `401 invalid_token`.

A malformed Bearer header or conflicting credentials across multiple channels can produce `invalid_request` and the corresponding syntax error response. Do not assume every Bearer error produces `401`.

## 3. Inside BearerTokenAuthenticationFilter

The flow can be broken down into these steps:

1. The filter receives `HttpServletRequest` and `HttpServletResponse`.
2. Calls `BearerTokenResolver.resolve(request)`.
3. If no token is present, calls `filterChain.doFilter(...)` without Bearer authentication.
4. If the resolver throws an error, delegates the error to the authentication failure mechanism.
5. If a token is present, creates a `BearerTokenAuthenticationToken`.
6. Selects an `AuthenticationManager` and calls `authenticate(...)`; Spring can also use `AuthenticationManagerResolver<HttpServletRequest>`.
7. If the provider succeeds, places the authenticated `Authentication` into `SecurityContext` for the request and continues the chain.
8. If the provider fails, clears the relevant authentication context and invokes the failure handler/entry point.

The following pseudocode **is not Spring's official implementation**, and only illustrates responsibilities:

```java
String bearer = bearerTokenResolver.resolve(request);

if (bearer == null) {
    chain.doFilter(request, response);
    return;
}

try {
    Authentication candidate =
        new BearerTokenAuthenticationToken(bearer);

    Authentication authenticated =
        authenticationManager.authenticate(candidate);

    SecurityContext context = createEmptyContext();
    context.setAuthentication(authenticated);
    setCurrentSecurityContext(context);
    saveContextIfConfigured(context, request, response);

    chain.doFilter(request, response);
} catch (AuthenticationException ex) {
    clearContext();
    authenticationFailureHandler.onAuthenticationFailure(
        request, response, ex
    );
}
```

Actual code also involves `AuthenticationDetailsSource`, `SecurityContextHolderStrategy`, and `SecurityContextRepository`. Only trust the `Authentication` returned by the provider after verifying the token, never the candidate object.

### 3.1. BearerTokenAuthenticationToken as Input

`new BearerTokenAuthenticationToken(token)` creates an **unauthenticated** `Authentication`. It holds the token so the provider can determine its validity. This state does not carry authorities such as `SCOPE_orders.read`.

With JWT:

```text
BearerTokenAuthenticationToken
  → AuthenticationManager
  → JwtAuthenticationProvider
  → JwtDecoder / JWT validators
  → JwtAuthenticationToken
  → SecurityContext
```

With opaque tokens:

```text
BearerTokenAuthenticationToken
  → AuthenticationManager
  → OpaqueTokenAuthenticationProvider
  → OpaqueTokenIntrospector
  → BearerTokenAuthentication
  → SecurityContext
```

Both share **Bearer extraction**, but validate the token using different providers.

### 3.2. JWT Validation and Authority Mapping

For JWTs, `JwtDecoder` must verify the signature using trusted issuer keys, lifetimes (`exp`, `nbf`), `iss`, `aud`, and any claims/token profile required by the AS–RS contract. A valid signature is not enough: a token issued for a different API must be rejected for an invalid `aud`.

`JwtAuthenticationConverter` converts scopes into authorities. With the common default mapping:

```text
JWT claim:    "scope": "orders.read orders.write"
Authorities:  SCOPE_orders.read
              SCOPE_orders.write
```

If the issuer represents scopes/roles differently, configure an appropriate converter. `BearerTokenAuthenticationFilter` does not directly understand business permissions like `orders.read`.

### 3.3. Opaque Token Introspection

If the access token is an opaque string, `OpaqueTokenAuthenticationProvider` uses `OpaqueTokenIntrospector` to verify it with the Authorization Server (or an appropriate custom mechanism). Returned metadata may include `active`, scope, subject, expiration, and other server-supported attributes.

The Resource Server must still check **target/audience and permissions** according to the contract, rather than assuming an `active=true` token is accepted by every API. Network-based introspection also requires planning for availability, timeouts, caching, and protecting introspection credentials.

### 3.4. When One API Serves Multiple Issuers

In some cases, the filter selects a manager using `AuthenticationManagerResolver<HttpServletRequest>` based on an allowed tenant or issuer. This is useful when each Authorization Server has its own issuer, JWKS, and policies.

**Do not trust unverified data just because it appears in a JWT header/payload.** A resolver may use such hints for preliminary routing, but must only select from a trusted set of issuers/tenants; the chosen manager must still genuinely verify the issuer, signature, audience, and permissions.

## 4. SecurityContext and Request State

After successful authentication, Spring Security creates or populates a `SecurityContext` holding the authenticated `Authentication` for the current request. Downstream steps in the chain, especially `AuthorizationFilter`, use that information.

| Access token type | Authenticated Authentication | Typical principal |
|---|---|---|
| JWT | `JwtAuthenticationToken` | `Jwt` verified by the decoder |
| Opaque | `BearerTokenAuthentication` | `OAuth2AuthenticatedPrincipal` |

JWT-only controller example:

```java
package com.example.orders.api;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CurrentSubjectController {

    @GetMapping("/api/me")
    Map<String, String> me(@AuthenticationPrincipal Jwt jwt) {
        return Map.of("subject", jwt.getSubject());
    }
}
```

This example assumes the endpoint is protected and the issuer issues `sub`. If the Resource Server switches to opaque tokens, the principal type can differ, so assuming `@AuthenticationPrincipal Jwt` will no longer hold.

### 4.1. Bearer Authentication and HttpSession

In Bearer-based APIs, clients normally send the access token on **every request**. This differs from browsers carrying a session cookie while the server tracks traditional login state.

Spring Security integrates `SecurityContextRepository`; however, the filter having a context-saving mechanism does not mean every Bearer request automatically creates an `HttpSession`. To keep the API stateless, configure an appropriate session policy and filter chain; if the same app uses both sessions/cookies and Bearer tokens, design clear boundaries.

## 5. Configuring a Resource Server with JWT

Assume the project uses **Spring Boot 3.x, Spring Security 6.x, Spring MVC**.

### 5.1. Gradle Dependencies

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

### 5.2. application.yml

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
          audiences:
            - orders-api
```

`issuer-uri` provides a trusted issuer/JWKS source via appropriate discovery. `audiences` is used for audience validation by Spring Boot 3.x versions supporting this property; if your project does not support it, configure a custom `OAuth2TokenValidator<Jwt>`. For access tokens following specific profiles (such as RFC 9068), you must still verify the token type and required claims per the contract.

### 5.3. SecurityFilterChain

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ResourceServerSecurity {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {

        DefaultBearerTokenResolver bearerResolver =
                new DefaultBearerTokenResolver();
        bearerResolver.setAllowFormEncodedBodyParameter(false);
        bearerResolver.setAllowUriQueryParameter(false);

        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .bearerTokenResolver(bearerResolver)
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Configuration summary:

- Applies the chain to `/api/**`.
- Reads tokens via `Authorization: Bearer ...`; query and form body parameters are disabled.
- Uses the JWT decoder/provider to validate access tokens.
- Uses authorities to authorize endpoint calls.
- Treats the API as not relying on sessions to identify users.

**URLs outside `/api/**`** need another chain or a fallback policy. The `anyRequest().authenticated()` rule in this chain only applies within the scope of its `securityMatcher`.

### 5.4. Why Not Register the Bearer Filter with FilterRegistrationBean?

Configuring `oauth2ResourceServer(...)` **already adds `BearerTokenAuthenticationFilter` to the Spring Security chain**. If you also register the same filter with the Servlet container or add it again in `HttpSecurity`, it can run in the wrong order, execute outside `FilterChainProxy`, or process the same request twice.

The standard extension approach is to configure `BearerTokenResolver`, `JwtDecoder`, `OpaqueTokenIntrospector`, converters, or `AuthenticationManagerResolver` as needed.

## 6. Changing Token Extraction Location Behind a Gateway

### 6.1. Switching to the Proxy-Authorization Header

`DefaultBearerTokenResolver` provides `setBearerTokenHeaderName(String)`. For example:

```java
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
resolver.setBearerTokenHeaderName(HttpHeaders.PROXY_AUTHORIZATION);
```

Then pass the resolver to the DSL:

```java
.oauth2ResourceServer(oauth2 -> oauth2
    .bearerTokenResolver(resolver)
    .jwt(Customizer.withDefaults())
)
```

This design is only suitable when the gateway/proxy system has a clear contract. If the backend is exposed directly, clients could forge headers intended to be controlled by the gateway. The gateway must strip or overwrite spoofed client headers, control the path to the backend, and ensure the API still validates the token properly.

### 6.2. Custom BearerTokenResolver

When specialized logic is needed, you can implement the interface:

```java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

public final class RestrictedBearerResolver implements BearerTokenResolver {
    private final BearerTokenResolver delegate =
            new DefaultBearerTokenResolver();

    @Override
    public String resolve(HttpServletRequest request) {
        // Illustrates a controllable extension point.
        // Preserves standard behavior here.
        return delegate.resolve(request);
    }
}
```

When extending to read another header, define how to handle requests carrying **two credentials** in two sources instead of arbitrarily picking one token. Do not extract tokens from URLs, cookies, or "internal" headers without a clear threat model and trust boundary.

A custom resolver **is only allowed to decide where the token is extracted from**; it should not make authorization decisions by reading unverified claims or return a faked authenticated object.

## 7. Requests with Missing, Invalid, and Sufficient Permissions

Assume `GET /api/orders/42` requires `SCOPE_orders.read`.

| Scenario | What happens | Typical outcome |
|---|---|---|
| No Authorization header | Filter finds no Bearer token; endpoint requires authentication | `401 Unauthorized` |
| Bearer header with fake/invalid-signature token | Resolver extracts string; provider rejects | `401` / `invalid_token` |
| Bearer header with JWT having wrong issuer/audience/expired | Decoder/validator rejects | `401` / `invalid_token` |
| Valid Bearer header missing `orders.read` | Authentication succeeds; authorization denies | `403 Forbidden`, possibly `insufficient_scope` |
| Valid Bearer token, sufficient scope | Passes route check; service still checks permissions on the specific order | May return `200` if permitted |
| Token only in query `?access_token=...` | Default resolver does not read it | Usually `401` on protected endpoints |
| `permitAll` endpoint but request carries **invalid** Bearer token | Filter may still attempt authentication before `permitAll` | May return `401` |

Example valid API call:

```bash
curl -i \
  -H "Authorization: Bearer ACCESS_TOKEN_VALUE" \
  https://api.example.com/api/orders/42
```

Do not send a refresh token or ID token to the Orders API just because they are also tokens generated by the Authorization Server. An **access token** is the credential meant for the resource server.

### 7.1. permitAll Does Not Force the Filter to Skip Tokens

This is a frequent source of confusion: `permitAll()` specifies that the **authorization rule** does not require an authenticated principal to reach the endpoint. It **does not prevent authentication filters from running** beforehand.

If `/api/public/info` is called without a bearer token, the filter skips it and the request is allowed. If an invalid token is intentionally attached, the Bearer filter may return an error during authentication even though the downstream authorization rule is `permitAll`.

If a public endpoint must ignore Bearer processing even when the header is malformed, design a dedicated filter chain or matcher deliberately. Do not solve this by "swallowing all token errors" across the entire API.

## 8. BearerTokenAuthenticationEntryPoint and HTTP Errors

A Resource Server can use `BearerTokenAuthenticationEntryPoint` to send an RFC 6750 challenge:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

For an invalid access token:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

A request that violates Bearer syntax per the specification may receive `invalid_request` and the corresponding error status code. The exact code depends on the `OAuth2Error` and entry point/failure handler configuration; do not assume every error is `401`.

When a token is authenticated but lacks sufficient scope, `BearerTokenAccessDeniedHandler` supports returning an insufficient-permission response, for example:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

**Practical rule:**

- **401:** unauthenticated or invalid credential.
- **403:** validly authenticated, but lacking permission for the action.
- **400 / invalid_request:** certain Bearer requests with invalid syntax or multiple sources per the RFC.

Never return raw tokens, sensitive claims, secrets, stack traces, or key configuration details in HTTP errors.

## 9. JWT and Opaque Tokens: Same Bearer Filter

### 9.1. JWT

Example JWT configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
```

`BearerTokenAuthenticationFilter` extracts the token, and `JwtAuthenticationProvider` calls `JwtDecoder` to verify it. JWTs are usually validated locally by signature and claims using trusted keys from JWKS. While a JWT remains unexpired, token revocation or permission changes at the AS are not necessarily known immediately by the RS unless additional mechanisms exist.

### 9.2. Opaque Token

Example configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: orders-api-introspection
          client-secret: CHANGE_ME_USING_SECRET_MANAGER
```

Java DSL:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults())
)
```

Introspection credentials must come from environment variables or a secret manager; `CHANGE_ME_USING_SECRET_MANAGER` is only a placeholder—**never commit real secrets to the repository**.

The filter still uses the same Bearer resolver. The difference is that the provider uses `OpaqueTokenIntrospector` to validate and return metadata, and the resource server maps the appropriate authorities. When switching between JWT and opaque tokens, you change the validation mechanism, **not necessarily the Bearer header sent by clients**.

## 10. Multi-Chain and Matchers

An application can separate Bearer APIs from other endpoints:

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class MultipleSecurityChains {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth ->
                auth.anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth ->
                auth.anyRequest().denyAll()
            )
            .build();
    }
}
```

This is **an example protecting the API and denying all other URLs**, not a complete login UI configuration. If you have `/web/**` with sessions or OIDC login, create an appropriate chain and callbacks. `@Order` affects matcher evaluation order; an overly broad chain placed before `/api/**` can prevent the Bearer filter from ever running on the intended endpoints.

## 11. CORS, CSRF, and Requests Before Reaching the API

### 11.1. CORS Preflight Does Not Carry a Bearer Token Like the Main Request

A cross-origin frontend calling an API with an `Authorization` header can trigger the browser to send a preflight request:

```http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

The `OPTIONS` preflight normally has no Bearer token. CORS must be handled properly before security authorization blocks the request. Spring can integrate it via:

```java
http.cors(Customizer.withDefaults());
```

with an appropriate `CorsConfigurationSource` restricting origins, methods, headers, and credentials as needed. Do not enable wildcard origins casually when cookies/credentials are involved.

### 11.2. CSRF with Bearer APIs

An API that authenticates solely via bearer tokens actively attached by the client in the `Authorization` header has a different CSRF model than cookie-based sessions, because browsers do not automatically send access tokens from JavaScript storage the way they automatically send cookies. However, if the application also uses cookies to authenticate state-changing requests, full CSRF evaluation is still required.

Do not disable CSRF mechanically just because `oauth2ResourceServer()` is present; base the decision on the actual authentication mechanisms of each `SecurityFilterChain`.

### 11.3. Proxy Stripping the Authorization Header

If the client sends a bearer token but the backend sees an unauthenticated request:

- A proxy/gateway may have stripped the `Authorization` header.
- A proxy may have moved it to a different header not read by the resolver.
- The request may have routed to a chain without Resource Server enabled.
- A custom resolver may be returning `null` due to an incorrect condition.

Verify header propagation in a test environment, but **never log raw bearer tokens**. You can log "header present/missing" or a request ID without recording the credential.

## 12. Using Authentication in Controllers and Services

After authentication, a controller can receive `Authentication`:

```java
package com.example.orders.api;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import java.util.Map;

@RestController
class IdentityController {

    @GetMapping("/api/whoami")
    Map<String, String> whoami(Authentication authentication) {
        return Map.of("principal", authentication.getName());
    }
}
```

`Authentication.getName()` is not guaranteed by default to be an email address or database user account. With JWTs it typically derives from `sub`; in `client_credentials`, the subject usually represents the client/application rather than an end user. Do not use this name blindly to grant access to data.

Route permission rules:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

only prove that the client/subject is allowed to **invoke the order-reading endpoint**. The service layer must still check ownership, tenant, order status, and all other business rules before returning a specific record.

## 13. Testing Token Extraction and Authentication

Basic cases:

| Request | Processing flow result |
|---|---|
| No header on public endpoint | Bearer filter skips; `permitAll` may allow. |
| No header on protected endpoint | Bearer filter skips; authorization usually returns `401`. |
| Bearer header with valid JWT | Resolver reads token, provider verifies, context holds `JwtAuthenticationToken`. |
| Bearer header with JWT having bad signature/issuer/audience/expired | Provider rejects; usually `401`. |
| Valid Bearer token missing scope | Authentication succeeds; authorization returns `403`. |
| Token placed in `?access_token=...` | Default resolver does not read from query parameters. |
| `permitAll` endpoint with invalid Bearer token | May still receive `401` because Bearer filter runs before the rule. |
| Browser `OPTIONS` preflight | CORS must handle it properly so the main request can proceed. |

### 13.1. Distinguishing Authorization Tests from Extraction Tests

In Spring Security Test, MockMvc `jwt()` can set an authenticated principal to test authorization:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@Test
void userWithoutReadScopeIsForbidden() throws Exception {
    mvc.perform(get("/api/orders/42").with(jwt()))
        .andExpect(status().isForbidden());
}
```

The example requires `spring-security-test` and an appropriate test setup; the endpoint is assumed to require `SCOPE_orders.read`. `jwt()` in Spring Security Test creates a synthetic authentication, which is useful for testing **authorization**, but **does not prove that the header was actually extracted by `BearerTokenAuthenticationFilter` or that the JWT signature was verified**.

To test the filter/extraction/decoder, write an integration test sending requests with an `Authorization: Bearer ...` header through the real filter chain, using a test-controlled issuer/JWKS or `JwtDecoder`, and test missing headers, malformed headers, invalid signatures, wrong audiences, and sufficient scopes.

## 14. Diagnosing 401 and 403 Layer by Layer

When troubleshooting errors, check in this order:

**(1) Did the request enter the right `SecurityFilterChain`?** Check `securityMatcher`, `@Order` precedence, and the actual path. Another chain might have matched first.

**(2) Can `BearerTokenResolver` read the token?** Check the standard header, proxy forwarding, sources disabled by default, and syntax errors. Do not expose real credentials in logs.

**(3) Did the provider verify the token?** For JWTs, check `iss`, `aud`, signature, algorithm, expiration, and token profile. For opaque tokens, check introspection, RS credentials, and metadata.

**(4) Authenticated, but which permission is missing?** Check `scope`/`scp` to `SCOPE_*` mapping, role converters, endpoint policies, and business permissions.

| Symptom | Layer to focus on |
|---|---|
| Client sends token, yet API says unauthenticated | Chain matcher, proxy, resolver |
| `401 invalid_token` even though JWT payload is readable | Decoder/issuer/audience/signature/expiration |
| `403` even though token is accepted | Authorities, scopes, object-level authorization |
| `permitAll` yet request with invalid token is rejected | Authentication filter runs before authorization |
| Query token does not work | `DefaultBearerTokenResolver` disables query tokens by default |
| `@AuthenticationPrincipal Jwt` is null/invalid with opaque token | Different Authentication/principal types |

## 15. Core Security Rules

1. **Use HTTPS** and keep `Authorization: Bearer` as the default token source.
2. **Never put tokens in URLs** or write raw credentials into logs, traces, or crash reports.
3. **Never decode and trust claims manually**; authorize only using the authentication verified by the provider.
4. **Verify issuer, audience, signature, expiration, and permissions**; a token valid for API A must not automatically work on API B.
5. **Do not use an ID token, refresh token, or authorization code** in place of an access token to call a Resource Server.
6. **Pay attention to chain matchers**: tokens are only processed by the Bearer filter in chains with Resource Server enabled.
7. **Do not register duplicate filters** outside `FilterChainProxy` when the DSL already installs them.
8. **Do not enable query/form tokens casually**; if special compatibility is required, enforce an explicit policy.
9. **Authorize at both routes and data objects**: having enough scope does not mean the caller may read every order.
10. **Distinguish 401 from 403**: missing/invalid token is authentication; valid token with insufficient rights is authorization.

## 16. Remembering the Servlet Bearer Flow

```text
HTTP request: Authorization: Bearer <access_token>
       |
       v
Servlet SecurityFilterChain
       |
       v
BearerTokenAuthenticationFilter
       |
       +--> BearerTokenResolver.resolve(request)
               |
               +--> null: continue chain (not yet authenticated)
               |
               +--> syntax error: failure handler / entry point
               |
               +--> token: BearerTokenAuthenticationToken
                              |
                              v
                       AuthenticationManager
                              |
                 +------------+-------------+
                 |                          |
         JwtAuthenticationProvider   OpaqueTokenAuthenticationProvider
                 |                          |
             JwtDecoder             OpaqueTokenIntrospector
                 |                          |
                 +-----------+--------------+
                             |
                    Valid Authentication
                             |
                        SecurityContext
                             |
                       AuthorizationFilter
                             |
                  authorized --> Controller
                  unauthorized --> 403
```

When analyzing a request in a Spring Security Servlet Resource Server, inspect in order: **matching chain → token extraction → token authentication → endpoint authorization**. `BearerTokenAuthenticationFilter` is the link that turns a bearer credential in an HTTP request into an authentication input; downstream layers determine whether the token is valid and whether the request has sufficient permissions.
