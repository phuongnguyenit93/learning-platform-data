# Avoiding Unexpected Redirects of API Authentication Errors to HTML Login Pages

In a **Spring Security OAuth 2.0 / OIDC Resource Server**, clients call APIs with a **Bearer access token**. When the token is missing, expired, has a bad signature, wrong issuer/audience, or fails authentication policies, the expected **API** response is an appropriate HTTP error — typically **401 Unauthorized** with **`WWW-Authenticate: Bearer`** — rather than an HTML login page or a **302 Redirect** to `/login`.

This is especially important when a Spring application serves both an interactive web login UI and a REST API, or when `formLogin`, `oauth2Login`, API gateways, and reverse proxies all participate in authentication. If the security chain configuration is ambiguous, an API request may be routed to browser-oriented login handling: the client receives HTML, tries to parse JSON, and fails with confusing errors; worse, the client cannot tell whether its token was rejected or it was merely redirected to an IdP.

**Core principle:** API requests using Bearer credentials must have a **Bearer-specific authentication entry point**, semantically consistent HTTP 401/403 responses, and must never trigger unexpected interactive login flows. Login pages/redirects should appear only on **URLs that genuinely belong to end-user login flows**.

> **Illustrative context:** Orders API at `https://api.example.com/api/**` accepts JWT access tokens with `aud=orders-api`, issued by `https://login.example.com`. An app in the same process may also serve web pages at `/web/**` using form login or OIDC login. Examples use Spring Boot 3.x, Spring Security 6.x, and the Servlet stack; with WebFlux, use `SecurityWebFilterChain` and corresponding reactive components.

## 1. Symptom: API Request Receives HTML Instead of a Bearer Challenge

Client sends:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer EXPIRED_OR_INVALID_ACCESS_TOKEN
Accept: application/json
```

**Unwanted** response:

```http
HTTP/1.1 302 Found
Location: /login
```

or after the client automatically follows the redirect:

```http
HTTP/1.1 200 OK
Content-Type: text/html;charset=UTF-8

<!doctype html>
<html>
  <head><title>Sign in</title></head>
  <body><form action="/login" method="post">...</form></body>
</html>
```

For a REST client, this is not a suitable answer to a request carrying a Bearer credential. Common symptoms include:

- Frontend calls `response.json()` and hits a parse error because the first character is `<` instead of JSON.
- Mobile apps do not know how to handle an HTML login page.
- CLI or service-to-service clients report “HTTP 200 success” when the body is actually a login UI.
- API SDKs receive a redirect to the OpenID Provider; depending on configuration, the redirect hits CORS or origin mismatches.
- A gateway or reverse proxy displays an HTML error/login page even though the backend returned a proper 401.
- Monitoring systems count 302/200 as success, masking real authentication failures.

### 1.1. Expected Response

When a bearer token is invalid:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
```

`Cache-Control: no-store` is a configurable measure to avoid caching sensitive content; **not every Bearer 401 response is required to display this header**. What matters is status **401** and a proper Bearer challenge.

When no bearer token is sent to a protected API, the response usually looks like:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

`error="invalid_token"` is not necessarily present when **no token is supplied**. Under RFC 6750, when a request provides no authentication credentials, the server should not return an overly specific error code merely for a missing token.

When a token is valid yet lacks scope:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

Exact headers and error parameters depend on how Spring Security recognizes the Authentication and configures handlers. Nevertheless, lacking **permissions** is no reason to serve an HTML login page to an already authenticated API caller.

## 2. Two Authentication Models That Must Be Distinguished

| Characteristic | API Bearer Resource Server | Interactive Web Login |
|---|---|---|
| Caller | SPA, mobile, backend, CLI, machine-to-machine | Browser/user |
| Primary credential | `Authorization: Bearer <access-token>` | Session cookie after form login/OIDC authorization code |
| When unauthenticated | **401** + Bearer challenge | Possibly **302** to login page |
| When token is invalid | **401 invalid_token** | Not the primary case for web sessions |
| When lacking permission | **403** or corresponding authorization error | **403** or UX error page |
| Body format | May be empty, JSON, or `application/problem+json` | May be HTML |
| Spring mechanism | `oauth2ResourceServer().jwt()/opaqueToken()` | `formLogin()` or `oauth2Login()` |
| Error destination | Caller handles/refreshes access token/re-authenticates via its flow | Browser interacts with login page/IdP |

**Resource Server does not equal OAuth2 Login Client.**

- **OAuth2 Resource Server** verifies **access tokens** sent to call APIs.
- **OAuth2 Login Client** initiates login flows via an Authorization Server/OpenID Provider and manages login state for a web app.
- One backend can hold both roles, provided it clearly defines which requests belong to which role.
- Never use a redirect to the OIDC authorization endpoint as the default response to an API bearer request.

### 2.1. Why Doesn't 302 Substitute for 401?

HTTP 302 means **resource redirection**. It does not clearly communicate that a Bearer token is invalid. Clients may also:

- Automatically follow the redirect and receive 200 HTML, losing the original 401 signal.
- Change HTTP methods or handle payloads differently depending on redirect status/client.
- Block cross-origin redirects due to CORS or browser security policies.
- Accidentally send requests to a login endpoint outside the API contract.

A web app can deliberately navigate users to a login page **after the client receives 401**. Yet that UX decision belongs to the **client**, not an implicit redirect performed by the API.

## 3. Bearer Error Semantics Under RFC 6750

RFC 6750 describes how bearer access tokens are used in HTTP and the `WWW-Authenticate` header for related errors.

### 3.1. Typical Scenarios

| Request/Token | Authentication | Typical Response |
|---|---|---|
| No token supplied to auth-required endpoint | Unauthenticated | **401**, `WWW-Authenticate: Bearer` |
| Malformed token or improper submission method | Credential unusable | **400 invalid_request** or matching error depending on case |
| Expired token | Invalid | **401 invalid_token** |
| JWT with wrong signature, issuer, or audience | Invalid | **401 invalid_token** |
| Opaque token introspection `active=false` | Invalid | **401 invalid_token** |
| Valid token lacking `orders.read` | Authenticated, missing scope | **403 insufficient_scope** |
| Valid token, sufficient scope, order belongs to someone else | Authenticated, object policy denies | **403** or **404** per API policy |
| Authorization Server/JWKS/introspection endpoint outage | Unable to complete authentication | **Fail closed**, infra error mapping per design; no login redirect |

### 3.2. `invalid_request`, `invalid_token`, and `insufficient_scope`

- **`invalid_request`:** bearer token presentation breaks rules, e.g., using multiple disallowed token transport methods or invalid parameters; status may be 400 per RFC 6750.
- **`invalid_token`:** token is expired, revoked, malformed in verification payload, or invalid per Resource Server policy; typically 401.
- **`insufficient_scope`:** token is authenticated, yet granted permissions are insufficient to access the resource; typically 403.

Do not turn every exception into `invalid_token` when the root cause is a server error, misconfigured introspection client, or unauthorized access to data. Accurate classification tells clients and operations what to do.

### 3.3. `WWW-Authenticate` Is Part of the Protocol

This is not merely a decorative header. Example:

```http
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
```

or:

```http
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.read"
```

The header may include `realm`, `error_description`, or `scope` depending on the situation. Exposing full internal error details is not required. If adding `error_description`, never expose tokens, subjects, sensitive key IDs, internal policies, or secrets.

**Avoid manually overwriting `WWW-Authenticate`** with a Basic challenge or blank header when handling bearer authentication errors.

## 4. Exception and Authentication Entry Point Flow in Spring Security

Important components:

| Component | Role |
|---|---|
| `BearerTokenAuthenticationFilter` | Extracts Bearer token from request, triggers authentication |
| `AuthenticationManager` | Selects appropriate provider |
| `JwtAuthenticationProvider` / `OpaqueTokenAuthenticationProvider` | Authenticates JWT or opaque token |
| `JwtDecoder` / `OpaqueTokenIntrospector` | Verifies token or runs introspection |
| `ExceptionTranslationFilter` | Translates downstream `AuthenticationException` / `AccessDeniedException` into appropriate responses |
| `AuthenticationEntryPoint` | Handles authentication-needed cases: 401 or redirect depending on type |
| `AccessDeniedHandler` | Handles `AccessDeniedException` when request lacks permissions |
| `BearerTokenAuthenticationEntryPoint` | Produces Bearer responses/challenges |
| `BearerTokenAccessDeniedHandler` | Handles insufficient permissions in the Bearer model |
| `LoginUrlAuthenticationEntryPoint` | Redirects browser to login URL when appropriate |

An important technical point: `BearerTokenAuthenticationFilter` can **directly invoke the entry point** when bearer token authentication fails. Not every error flows through `ExceptionTranslationFilter`. Therefore, configuring the **Resource Server's entry point** properly is especially critical.

### 4.1. Branching Diagram

```mermaid
flowchart TD
    A["GET /api/orders/42"] --> B["API SecurityFilterChain"]
    B --> C{"Bearer token present?"}
    C -->|Yes| D["BearerTokenAuthenticationFilter / JwtDecoder or introspection"]
    D --> E{"Token valid?"}
    E -->|No| F["BearerTokenAuthenticationEntryPoint"]
    F --> G["401 + WWW-Authenticate: Bearer"]
    E -->|Yes| H["SecurityContext and authorities"]
    C -->|No| I["Continue chain to endpoint"]
    I --> J{"Endpoint requires auth?"}
    J -->|Yes| F
    J -->|No| K["Public endpoint"]
    H --> L{"Scope/role/ownership valid?"}
    L -->|No| M["BearerTokenAccessDeniedHandler / domain policy"]
    M --> N["403 or 404 per contract"]
    L -->|Yes| O["Business processing"]
```

On the **API** path, there is no default branch to `/login`. On the **interactive web** path, a different entry point can redirect browsers to a login page or OpenID Provider.

### 4.2. Why Does Spring Sometimes Pick a Login Page?

Spring Security can host **multiple authentication mechanisms** in the same application:

- `formLogin()` provides login flows via an HTML form.
- `oauth2Login()` supports interactive login with OAuth2/OIDC.
- `httpBasic()` provides HTTP Basic challenges.
- `oauth2ResourceServer()` provides Bearer token authentication.

When multiple authentication entry points exist, Spring may use **request matching** and **content negotiation** to pick how to respond. If configured ambiguously, an API request may be handled by the entry point meant for form login or OIDC login, causing a redirect.

**Do not rely on `Accept: application/json` always “saving” the API.** An API caller may send `Accept: */*` or even `text/html`; security boundaries must come from URL/security chains and authentication contracts, not from a client-controlled header.

## 5. Splitting SecurityFilterChains for APIs and Interactive Web

The cleanest solution in an application with both APIs and a web UI is **two security chains with non-overlapping paths**, with the API chain having higher priority.

Suppose:

```text
/api/**   → OAuth2 Resource Server, Bearer only
/web/**   → Web app, form login or OIDC login
/login    → Interactive login page
```

### 5.1. Illustrative Dependencies

For Spring Boot Servlet:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    // Only needed when the application is also an OAuth2 Login Client.
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

If the API is a service serving Bearer tokens only, **there is no need** to add the OAuth2 Client starter or `formLogin()` just to handle 401s.

### 5.2. Configuring JWT Issuer and Audience

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

`audiences` is available in compatible Spring Boot versions; if using a custom decoder or another version, configure an audience validator manually. If requiring JWT access tokens per RFC 9068, also validate token type `at+jwt` and profile claims.

### 5.3. Priority 1 Chain: Bearer-Only API

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiChainSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api", "/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            // Illustrative API accepts only Bearer headers, no cookie sessions.
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .requestCache(AbstractHttpConfigurer::disable)
            .csrf(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .oauth2Login(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(
                    new BearerTokenAuthenticationEntryPoint()
                )
                .accessDeniedHandler(
                    new BearerTokenAccessDeniedHandler()
                )
            )
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/web/**", "/login", "/logout")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/web/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain remainingPaths(HttpSecurity http) throws Exception {
        // Defensive example: other paths not assigned to a chain
        // do not become public simply by lacking a matcher.
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll()
            )
            .build();
    }
}
```

**Policy analysis:**

- `@Order(1)` places the chain for `/api` and `/api/**` first.
- `securityMatcher` decides **whether a chain applies to a request**. This is the primary boundary preventing API requests from hitting the login chain.
- The API chain configures `oauth2ResourceServer(...jwt(...))` and explicitly sets `BearerTokenAuthenticationEntryPoint`.
- `formLogin`, `oauth2Login`, and `httpBasic` are disabled on the **API chain**, preventing other login/challenge mechanisms from sneaking in via accidental configuration.
- `requestCache` is disabled on the API so requests are never saved for post-login redirects.
- The web chain applies only to `/web/**`, `/login`, `/logout`, so it can safely use interactive form login.
- The final chain **denies all** so new endpoints outside existing matchers never become unintentionally public.

**Limitation to understand:** this example assumes the API **authenticates solely via Bearer headers** and uses no cookies/browser sessions for state-changing actions. That is why it disables CSRF in the API chain. If the same API also accepts cookies or browser-attached credentials, never copy `csrf(...disable)`; design appropriate CSRF protection instead. The web chain keeps Spring Security's default CSRF protection.

### 5.4. Why Is the Final Chain Needed?

`securityMatcher("/api/**")` does not mean every URL in the app is protected by this chain. For instance, `/admin/export` or `/internal/jobs` does not match `/api/**`.

If no chain matches a request, **Spring Security may not protect that request with the expected filters**. In a multi-chain system, explicitly decide which chain protects remaining URLs. A `denyAll()` fallback is a defensive choice for unclassified URLs, while real applications may need dedicated configurations for health checks, static assets, management endpoints, or OIDC callbacks.

### 5.5. If the Application Is Purely a Resource Server API

When there is no web login, a single chain makes complete sense:

```java
@Bean
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/actuator/health").permitAll()
            .anyRequest().authenticated()
        )
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults())
        )
        .exceptionHandling(ex -> ex
            .authenticationEntryPoint(
                new BearerTokenAuthenticationEntryPoint()
            )
            .accessDeniedHandler(
                new BearerTokenAccessDeniedHandler()
            )
        )
        .build();
}
```

This template installs no form login/OIDC login. If the API is bearer-only with specific CSRF/session needs, add corresponding configuration. Never disable other security protections merely to get 401 instead of HTML.

## 6. If the Web Layer Uses oauth2Login() Instead of formLogin()

A web UI application may use **OAuth2 Login** to redirect users to an OpenID Provider:

```java
@Bean
@Order(2)
SecurityFilterChain oidcWebSecurity(HttpSecurity http) throws Exception {
    return http
        .securityMatcher(
            "/web/**",
            "/oauth2/**",
            "/login/oauth2/**",
            "/logout"
        )
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/web/public/**", "/oauth2/**").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2Login(Customizer.withDefaults())
        .build();
}
```

This snippet **replaces the formLogin web chain** from the previous example; do not register both beans side by side with `@Order(2)` and overlapping matchers. Real usage requires a proper `ClientRegistrationRepository`/OIDC client configuration and verifying callback routes, CSRF, logout, and public assets.

**Never let `/api/**` routes fall into this chain.** An API missing a Bearer credential must never emit a redirect:

```http
Location: /oauth2/authorization/<registration-id>
```

If a SPA frontend needs the user to re-authenticate, the frontend should run **OIDC Authorization Code + PKCE** via its own client mechanism after handling the API error, rather than letting the Resource Server convert a 401 into a login flow.

## 7. When Is BearerTokenAuthenticationEntryPoint Needed?

Spring Security's `BearerTokenAuthenticationEntryPoint` specializes in building Bearer-model authentication responses based on the `AuthenticationException` it receives.

Cases:

- Endpoint requires authentication, yet the request has no Bearer token.
- Invalid/expired token rejected by the provider/decoder.
- A Bearer error carrying an `OAuth2Error` to populate `WWW-Authenticate` when appropriate.

Instead of:

```java
.exceptionHandling(ex -> ex
    .authenticationEntryPoint(
        new LoginUrlAuthenticationEntryPoint("/login")
    )
)
```

on the API chain, use:

```java
.exceptionHandling(ex -> ex
    .authenticationEntryPoint(
        new BearerTokenAuthenticationEntryPoint()
    )
)
```

**Never return redirects inside an API's `AuthenticationEntryPoint`** to “help the client log in”. That breaks the Bearer error contract and causes trouble for mobile/CLI/backend clients.

### 7.1. What Does BearerTokenAccessDeniedHandler Handle?

When a token is valid but lacks an authority:

```java
.exceptionHandling(ex -> ex
    .accessDeniedHandler(
        new BearerTokenAccessDeniedHandler()
    )
)
```

The handler produces a **403** response and, when the authentication carries sufficient OAuth2 token context, can populate `insufficient_scope` in the Bearer challenge.

Do not confuse:

- **AuthenticationEntryPoint:** unauthenticated or invalid credential → points to 401.
- **AccessDeniedHandler:** request has an authentication context but lacks required permission → points to 403 or domain response.

In cases of anonymous/insufficient authentication, `ExceptionTranslationFilter` may trigger the entry point rather than the access-denied handler. Therefore, statuses must reflect actual authentication state and error type.

## 8. Separating Authentication Errors from Authorization Errors

Example GET API requiring `SCOPE_orders.read`:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().authenticated()
)
```

Three situations exist:

| Bearer Token | Permission | Response |
|---|---|---|
| No token sent | No valid Authentication | **401**, Bearer challenge |
| JWT with bad signature | No valid Authentication | **401 invalid_token** |
| Valid JWT, only `orders.write` | Lacks `orders.read` | **403** (usually `insufficient_scope`) |

If the service also checks ownership, a valid JWT with `orders.read` can still be denied because the order belongs to another tenant. That is **object-level authorization**, not a reason to return a login page.

### 8.1. Missing Scope Should Not Turn into “Please Log In”

Logging in again may or may not help the client obtain a new scope; granting permissions depends on the Authorization Server, consent, roles, client registration, and policy. An API should not assume every `403` can be cured by logging in again.

SPAs should handle the two error groups differently:

- **401:** missing/invalid token; may attempt obtaining a new token if allowed for the client, or prompt the user to log in via a separate OIDC flow.
- **403:** valid token lacking permissions; display an insufficient-permissions message or business guidance instead of looping logins infinitely.

## 9. Should 401/403 Return a JSON Body?

**Not mandatory.** For Bearer, HTTP status and `WWW-Authenticate` form the core contract. An API may choose an empty body.

However, many frontend/mobile apps want consistent JSON messages, e.g.:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401
}
```

Or:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403
}
```

`application/problem+json` is a standardized HTTP error representation (RFC 9457). Keep messages short, reveal no tokens/raw claims, and disclose no internal details about keys, tenants, or whether users exist.

### 9.1. Custom JSON Entry Point Preserving the Bearer Challenge

If a JSON body is desired, **do not replace the entire Bearer response with a controller `ResponseEntity`**. Authentication errors in the filter chain usually happen **before any controller runs**.

You can wrap `AuthenticationEntryPoint`: let Spring write the Bearer challenge first, then append a body.

```java
package com.example.orders.security;

import java.io.IOException;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.MediaType;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;

public final class JsonBearerAuthenticationEntryPoint
        implements AuthenticationEntryPoint {

    private final BearerTokenAuthenticationEntryPoint bearer =
        new BearerTokenAuthenticationEntryPoint();

    private final ObjectMapper objectMapper;

    public JsonBearerAuthenticationEntryPoint(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException {

        // Preserve Bearer status and WWW-Authenticate header.
        bearer.commence(request, response, exception);

        if (response.isCommitted()) {
            return;
        }

        response.setContentType(
            MediaType.APPLICATION_PROBLEM_JSON_VALUE
        );
        response.setCharacterEncoding("UTF-8");

        objectMapper.writeValue(
            response.getOutputStream(),
            Map.of(
                "type", "about:blank",
                "title", "Unauthorized",
                "status", 401
            )
        );
    }
}
```

A similar wrapper for `AccessDeniedHandler`:

```java
package com.example.orders.security;

import java.io.IOException;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;

public final class JsonBearerAccessDeniedHandler
        implements AccessDeniedHandler {

    private final BearerTokenAccessDeniedHandler bearer =
        new BearerTokenAccessDeniedHandler();

    private final ObjectMapper objectMapper;

    public JsonBearerAccessDeniedHandler(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            AccessDeniedException exception)
            throws IOException {

        // Keep status and Bearer challenge from standard handler.
        bearer.handle(request, response, exception);

        if (response.isCommitted()) {
            return;
        }

        response.setContentType(
            MediaType.APPLICATION_PROBLEM_JSON_VALUE
        );
        response.setCharacterEncoding("UTF-8");

        objectMapper.writeValue(
            response.getOutputStream(),
            Map.of(
                "type", "about:blank",
                "title", "Forbidden",
                "status", 403
            )
        );
    }
}
```

Attach both handlers to the **API chain**:

```java
@Bean
SecurityFilterChain apiChain(
        HttpSecurity http,
        ObjectMapper objectMapper) throws Exception {

    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults())
        )
        .exceptionHandling(ex -> ex
            .authenticationEntryPoint(
                new JsonBearerAuthenticationEntryPoint(objectMapper)
            )
            .accessDeniedHandler(
                new JsonBearerAccessDeniedHandler(objectMapper)
            )
        )
        .build();
}
```

This is an **alternative variant** of the API chain in section 5, not a bean to register concurrently on the same `/api/**` path without controlling `@Order`. When using multiple filter chains, keep a single configuration covering the API path.

**Notes on custom error bodies:**

- Never call `sendRedirect(...)` or render an HTML view template.
- Never write a body once the response is already committed.
- Keep `WWW-Authenticate` produced by the standard handler.
- Ensure actual status matches the body (401/403).
- Never pass `exception.getMessage()` directly to clients if it could contain sensitive info.
- Never serialize the full `Authentication`, `Jwt`, or `OAuth2AuthenticatedPrincipal` into error responses.
- Test with `curl -i` to inspect real headers/statuses, not just the JSON body.

### 9.2. Why Not Use Only @RestControllerAdvice?

`@RestControllerAdvice` is great for errors originating in **controllers/services**, such as invalid inputs, domain exceptions, or business errors. However, many authentication errors occur inside the **Spring Security filter chain before DispatcherServlet**, so they do not pass through controller advice like ordinary MVC errors.

To change responses for missing/invalid Bearer tokens, use **`AuthenticationEntryPoint` / `AccessDeniedHandler`** or the corresponding security components rather than merely adding:

```java
@ExceptionHandler(AuthenticationException.class)
```

and expecting it to catch all errors inside `BearerTokenAuthenticationFilter`.

Another pitfall: API gateway middleware or a global error handler can **overwrite statuses/headers** after Spring Security already built the right response. Check the entire path.

## 10. Do Not Use Request Cache and Saved-Request Redirects for APIs

Web logins usually follow this flow:

```text
Browser calls /web/account
       |
       v
Not logged in
       |
       v
Save /web/account request into RequestCache
       |
       v
302 /login
       |
       v
User logs in
       |
       v
Redirect browser back to /web/account
```

That flow makes sense for a session-based web app. For a bearer-only API, however:

```text
Client calls /api/orders/42 with bad token
       |
       v
401 WWW-Authenticate: Bearer
       |
       v
Client decides to fetch a new access token/re-authenticate
       |
       v
Client retries the request itself with a valid credential
```

An API does not need to save requests in an HTTP session to redirect after login. In the API chain you can configure:

```java
.requestCache(AbstractHttpConfigurer::disable)
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
)
```

**`STATELESS` does not automatically express every other security choice.** It describes not using an HTTP session to store/retrieve the security context per the configured policy. If the app still uses cookie credentials, you still must evaluate CSRF and corresponding stateful mechanisms.

### 10.1. What If the API Still Redirects Despite STATELESS?

Possible causes:

- A `formLogin`/`oauth2Login` chain still matches before the API chain.
- A custom authentication entry point is still `LoginUrlAuthenticationEntryPoint`.
- An API gateway or reverse proxy injects a redirect.
- MVC/controller returns `redirect:/login` itself.
- Request URL does not match the `securityMatcher` you expect.
- The SPA/client redirected itself after receiving 401; the observed result is not the API's raw response.

`STATELESS` is **not** a “disable login redirect” switch substituting for proper security chain and entry point design.

## 11. Filter Chain Ordering: Where Bugs Commonly Hide

Spring Security picks the **first matching SecurityFilterChain** in `FilterChainProxy`. An API URL that accidentally matches an earlier web chain gets treated like a browser.

Improper example:

```java
@Bean
@Order(1)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()))
        .build();
}
```

The first web chain **has no dedicated `securityMatcher`**, so it matches every URL; the second API chain is never selected for `/api/orders`. Consequently, responses look like web logins instead of Bearer.

Fix by:

1. Putting `@Order(1)` on the API chain with `/api/**` matcher.
2. Putting specific matchers on the web chain or an intentional fallback.
3. Never placing catch-all chains with `anyRequest()` matchers ahead of the API chain.
4. Checking both `/api` and `/api/**` URL variants.
5. Checking context-path and reverse proxy path rewrites.
6. Testing requests with missing token, bad token, and `Accept: text/html`.

### 11.1. Distinguishing securityMatcher from requestMatchers

```java
.securityMatcher("/api/**")
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .anyRequest().authenticated()
)
```

- `securityMatcher` selects which **SecurityFilterChain** applies to the request.
- `requestMatchers` inside `authorizeHttpRequests` selects the **authorization rule** once the chain is chosen.

If the wrong chain is chosen, adding `requestMatchers("/api/**").authenticated()` inside the web chain **does not change the entry point** to Bearer. Fix the chain selection and authentication mechanism layer instead.

## 12. Content Negotiation: Accept Is Not a Security Boundary

Some clients send:

```http
Accept: application/json
```

while others send:

```http
Accept: */*
```

or a browser hitting an API directly sends:

```http
Accept: text/html,application/xhtml+xml
```

If the API contract is Bearer, all three missing-token cases must still respond with Bearer semantics. Never rely on the Accept header to decide **whether to redirect to login**.

### 12.1. Why Does an API Turn into HTML When Called from a Browser?

Spring Security supports content negotiation for entry points depending on configuration. A chain combining `formLogin` and `oauth2ResourceServer` may pick different handlers based on request type/matchers. Browsers also follow redirects automatically, making it look like the API returned 200 HTML.

The reliable fix is a **dedicated API chain with an explicit Bearer entry point**. Content negotiation should select **error format** (JSON vs. problem+json) within the same API contract, never switch into a completely different interactive login flow.

## 13. Client-Side: Receiving 401 and Handling Login in the Right Place

A SPA might call:

```javascript
async function loadOrders(accessToken) {
  const response = await fetch("/api/orders", {
    method: "GET",
    headers: {
      Authorization: "Bearer " + accessToken,
      Accept: "application/json"
    }
  });

  if (response.status === 401) {
    // Caller handles credentials: refresh or start a dedicated login flow.
    throw new Error("ACCESS_TOKEN_INVALID_OR_MISSING");
  }

  if (response.status === 403) {
    throw new Error("ACCESS_DENIED");
  }

  if (!response.ok) {
    throw new Error("API_REQUEST_FAILED");
  }

  return response.json();
}
```

This is an example of reacting to status codes, **not guidance to store access tokens in localStorage**. How tokens are stored and refreshed depends on your browser security architecture: SPA OAuth client, Backend-for-Frontend (BFF), cookies/sessions, and PKCE.

**Pitfall to avoid:** an API returning 302 HTML makes `response.ok` true after the redirect, causing the client to try parsing HTML. When the API returns a proper 401, the frontend can tell auth errors apart from domain/permission errors.

### 13.1. Refresh Tokens Do Not Belong on Resource Server Endpoints

If the client holds a refresh token, renewing the access token belongs to the **OAuth client and Authorization Server token endpoint** under a valid flow—not the Orders API accepting a refresh token and arbitrarily “swapping it for another Bearer token”.

The API should only accept access tokens issued for this resource. Reject ID tokens or refresh tokens masquerading as access tokens.

### 13.2. Avoiding Infinite Login Loops

Sensible frontend rules:

- On **401**: if a valid refresh mechanism exists, retry up to policy limits and deduplicate concurrent refreshes; if that fails, navigate the user to login via the client.
- On **403**: show insufficient permissions or permission workflow; do not repeatedly re-trigger login.
- On **503** or network errors: report service unavailability; do not wipe sessions/log everyone out when the AS is temporarily down.
- Do not turn every non-200 response into `window.location='/login'`.
- Do not treat followed HTML redirects as successful JSON API responses.

## 14. CORS Preflight Does Not Require Bearer Authentication

For cross-origin SPAs, browsers may send an **OPTIONS preflight** before requests carrying `Authorization`:

```http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Preflights normally **carry no bearer access token** from the real request. If Spring Security requires a Bearer token on OPTIONS preflights and redirects to login, the browser will report confusing CORS errors.

Configure CORS properly so preflights pass through the right mechanism. Example for an app whose frontend is at `https://app.example.com`:

```java
package com.example.orders.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiCorsConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(
            List.of("https://app.example.com")
        );
        cors.setAllowedMethods(
            List.of("GET", "POST", "PUT", "DELETE", "OPTIONS")
        );
        cors.setAllowedHeaders(
            List.of("Authorization", "Content-Type")
        );

        // Illustrative API uses Authorization Bearer only, no cookies.
        cors.setAllowCredentials(false);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
```

In the API chain:

```java
.cors(Customizer.withDefaults())
```

With a matching `CorsConfigurationSource`, Spring Security can handle CORS preflights before requiring authentication on the real request. Tailor CORS policies to actual origins/methods/headers. If using cross-origin cookies, add appropriate credentials, SameSite, and CSRF protections rather than copying bearer-only samples.

**Do not assume every 401 on OPTIONS is a bad token**. It may be a broken CORS setup. Never add `permitAll()` across the entire API just to get preflights through.

## 15. Gateways, Reverse Proxies, and Ingresses Can Inject HTML Redirects

Sometimes the Spring Security backend returns a compliant response:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

yet the client actually receives:

```http
HTTP/1.1 302 Found
Location: /auth/login
```

or:

```http
HTTP/1.1 200 OK
Content-Type: text/html

<html>Gateway sign-in</html>
```

This can be caused by:

- API gateway applying a blanket domain-wide login policy.
- Reverse proxy `auth_request` or forward-auth module.
- Service mesh/ingress access policy.
- CDN/WAF custom error pages.
- Load balancer/web SSO proxy.
- Frontend dev server proxy or service worker.
- Another `ErrorPageFilter`/application error-forwarding layer in the system.

**Backend Spring Security cannot fix a response already rewritten by a gateway**. Inspect every hop and enforce that **API routes preserve 401/403, Bearer challenges, and error formats**, while web routes can use interactive login.

### 15.1. How to Pinpoint Where the Redirect Originated

Compare:

1. Direct request to the **backend instance/service endpoint** inside an allowed internal network.
2. The same request passing through ingress/gateway.
3. Inspect status, `Location`, `WWW-Authenticate`, `Content-Type`, and request IDs.
4. Check whether a gateway authentication policy applies to `/api/**`.
5. Check whether the proxy rewrites paths before Spring picks a chain.
6. Check whether 401/403 response bodies are replaced with branded HTML error pages.

Do not remove gateway or backend authentication just to stop redirects; configure **Bearer/API handling mode** on API routes instead.

### 15.2. Note on Forwarded Prefix / Context Path

For example, external traffic calls:

```text
https://example.com/orders-api/api/orders/42
```

while the proxy forwards to the backend as:

```text
/api/orders/42
```

If Spring sees a different path than `securityMatcher` expects, the request can fall into a web/fallback chain. When debugging, inspect the **exact path `FilterChainProxy` receives**, not just the external URL.

## 16. CSRF and Browser Cookies: Never Disable One Protection to Fix a Redirect Bug

A bearer-only, stateless API typically does not rely on browser-auto-sent cookies, so it can design its CSRF policy accordingly. However, an app combining login sessions and APIs must be careful:

- If endpoints support **cookie-based authentication**, browsers may send cookies automatically on cross-site requests → evaluate CSRF.
- If endpoints **only** accept Bearer tokens in `Authorization` headers explicitly attached by JavaScript/clients, classic CSRF risk differs.
- If accepting both Bearer tokens and session cookies, never disable CSRF globally for the entire application.
- CORS does not replace CSRF; they solve different problems.
- `SessionCreationPolicy.STATELESS` does not prove no browser-auto-sent credentials exist.

When splitting chains, base CSRF configuration on each chain's **actual credentials and browser interactions**. Returning proper Bearer 401s does not require disabling all CSRF protection.

## 17. Configurations That Cause Confusion

### 17.1. Putting formLogin in a Catch-All Chain

```java
http.authorizeHttpRequests(auth -> auth
    .anyRequest().authenticated()
).formLogin(Customizer.withDefaults());
```

If this is the first chain matching `/api/**`, Spring may use the login entry point for the API. Put the API chain first and the web chain after.

### 17.2. Mixing oauth2Login and Resource Server Without Specifying Entry Points

```java
http
    .oauth2Login(Customizer.withDefaults())
    .oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults())
    );
```

Such a configuration does **not automatically** ensure API requests always get Bearer challenges. Entry point selection depends on request matchers and remaining settings. When one app acts as both browser client and API RS, configure explicit matchers/chains and entry points.

### 17.3. Using a Global `.exceptionHandling().authenticationEntryPoint(loginEntryPoint)`

An overly broad custom login entry point can end up applied to Bearer APIs too. Keep it on the **web chain**; on the API chain use `BearerTokenAuthenticationEntryPoint`.

### 17.4. Editing Only @ControllerAdvice

Bearer token errors usually happen before controllers. Fix Spring Security entry points/handlers rather than just adding `@RestControllerAdvice`.

### 17.5. Always Redirecting When the User Is Unauthenticated

A generic “anonymous → /login” helper works for HTML pages, not APIs. Branch on **route/authentication model**, not merely `Authentication.isAuthenticated()`.

### 17.6. Sending 200 HTML Error Pages for “User-Friendly Error Pages”

An API returning status 200 misleads clients and monitoring. Keep appropriate 401/403/5xx statuses and matching media types where needed; HTML pages are a UI choice, not an API error contract.

### 17.7. Using HTTP Basic Challenges Instead of Bearer

If the Resource Server accepts Bearer tokens, a response:

```http
WWW-Authenticate: Basic realm="App"
```

can trigger a browser Basic Authentication popup, unsuitable for an OAuth Bearer API. Never enable `httpBasic` on a bearer-only chain without an explicit requirement.

## 18. OAuth2 Opaque Tokens Must Also Return Bearer, Not HTML Login

The JWT vs. opaque difference lies in **how the Resource Server validates access tokens**, not in Bearer error response semantics.

JWT:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.jwt(Customizer.withDefaults())
)
```

Opaque:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults())
)
```

Both normally receive access tokens via `Authorization: Bearer ...`. When a token is invalid, the API must respond under Bearer authentication semantics, never redirecting to `/login`.

With opaque token introspection:

- `active=false` usually leads to an invalid token, returning 401.
- `active=true` with missing scope leads to 403.
- AS introspection timeouts, wrong client secrets, or TLS failures are dependency/configuration incidents; **fail closed**, never accept tokens by guessing, and never redirect users to mask errors.
- If mapping AS outages to 503 instead of 401 in some cases, classify exceptions and test; **Spring does not automatically map every network error to 503**.

## 19. Testing: Proving the API Never Returns HTML Login

Tests checking only `status().isUnauthorized()` miss bugs when a 401 response carries an out-of-contract HTML body. Assert **status, headers, redirects, and Content-Type** together when needed.

### 19.1. MockMvc: Missing Token with Accept text/html Must Still Receive 401

Spring Boot test example with `MockMvc`:

```java
package com.example.orders.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiBearerErrorTest {

    @Autowired
    MockMvc mvc;

    @Test
    void apiNeverRedirectsToHtmlLoginWhenTokenIsMissing()
            throws Exception {
        mvc.perform(get("/api/orders/42")
                .accept(MediaType.TEXT_HTML))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                startsWith("Bearer")
            ))
            .andExpect(header().doesNotExist(HttpHeaders.LOCATION));
    }
}
```

What to observe:

- Even when the client sends `Accept: text/html`, the API chain still responds as a **Bearer API**.
- No `Location: /login` or `Location: /oauth2/authorization/...`.
- `WWW-Authenticate` starts with `Bearer`.

This test checks **filter chain configuration on missing-token requests**; it does not prove JwtDecoder verifies signatures properly. For real tokens, write dedicated integration tests.

### 19.2. MockMvc: Valid Token Lacking Scope Must Return 403

With `spring-security-test`:

```groovy
dependencies {
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.http.MediaType;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@Test
void validJwtWithWrongScopeDoesNotOpenLoginPage() throws Exception {
    mvc.perform(get("/api/orders/42")
            .accept(MediaType.APPLICATION_JSON)
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_unrelated")
            )))
        .andExpect(status().isForbidden())
        .andExpect(header().doesNotExist(HttpHeaders.LOCATION));
}
```

This is a test fragment inside a full `MockMvc` test class. `jwt()` builds a mocked authentication and **does not verify real JWT signatures**. It suits testing authorization and response handling, not replacing decoder tests.

### 19.3. MockMvc: Web Pages May Redirect to Login

In the separate web chain, a browser request to a protected page may expect a redirect:

```java
@Test
void webPageMayRedirectToLogin() throws Exception {
    mvc.perform(get("/web/account")
            .accept(MediaType.TEXT_HTML))
        .andExpect(status().is3xxRedirection())
        .andExpect(header().string(
            HttpHeaders.LOCATION,
            startsWith("http")
        ));
}
```

**Note:** `Location` in MockMvc/Spring may be a relative path `/login` instead of an absolute URL. Therefore, asserting `startsWith("http")` is not always accurate if redirects are relative. In practice, check the redirect target matching your app, e.g., matching `/login` or `redirectedUrlPattern("**/login")` per your test framework.

The test's goal is proving **web and API have distinct error behaviors by design**, not requiring every web redirect to use the same Location format.

### 19.4. Integration Tests for Bad Tokens / Bad Signatures

For end-to-end authentication tests:

1. Send HTTP requests with `Authorization: Bearer <TEST_JWT>`.
2. Use a trusted test issuer/JWKS in the test environment.
3. Verify expired/wrong-issuer/wrong-audience/bad-signature tokens are all rejected.
4. Ensure **401 Bearer** responses with no login `Location`.
5. Verify wrong scope returns **403**, no redirect.
6. Test across `Accept: application/json`, `Accept: text/html`, and `Accept: */*`.
7. Test through the **real gateway or staging ingress** to catch 401s rewritten into HTML.
8. Verify no raw tokens/sensitive claims leak via body, headers, or logs.

If using opaque tokens, swap the mock JWKS for an introspection test server returning `active=true/false` and controlled client-credential/network errors.

## 20. Real-World Verification with curl

`curl` does not follow redirects by default without `-L`, making it convenient to inspect the **original** response.

### 20.1. Without a Token

```bash
curl --include \
  --header "Accept: application/json" \
  "https://api.example.com/api/orders/42"
```

Expected on a protected endpoint:

```text
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

Unwanted:

```text
HTTP/1.1 302 Found
Location: /login
```

### 20.2. Bad Token When Client Accepts HTML

```bash
curl --include \
  --header "Accept: text/html" \
  --header "Authorization: Bearer INVALID_TEST_TOKEN" \
  "https://api.example.com/api/orders/42"
```

Expected to remain a Bearer 401, with no HTML login.

### 20.3. Checking Whether a Gateway Rewrites Responses

Compare headers between direct backend calls and the public URL:

```bash
# Public URL through ingress/gateway:
curl --include \
  "https://api.example.com/api/orders/42"

# Internal URL inside an authorized network, used for debugging:
curl --include \
  "http://orders-api.internal:8080/api/orders/42"
```

The internal `http://...` example illustrates debugging inside a protected network; environments requiring internal mTLS/TLS must use HTTPS accordingly. Never expose internal endpoints to the Internet or bypass authentication for testing.

Observe:

- `HTTP status`.
- `WWW-Authenticate`.
- `Location`.
- `Content-Type`.
- `Server`, request ID, or proxy headers if safe.
- If 302 appears, is the target `/login`, `/oauth2/authorization/...`, or the gateway's login host?

**Never put real access tokens on command lines where logs/shell history could expose credentials.** Use harmless test tokens or organization-approved credential mechanisms.

## 21. Distinguishing API 401s from Other Systems' 401s

An application traverses multiple hops:

```text
OAuth Client
    |
    v
CDN / WAF
    |
    v
API Gateway / Ingress
    |
    v
Spring Security Resource Server
    |
    +--> JWT JWKS endpoint or opaque introspection endpoint
    |
    v
Domain service
```

Each hop can generate 401/403 or HTML error responses. Ask:

- Who emitted the **first status**?
- Did a gateway rewrite any response into a redirect?
- Is the Bearer challenge intact?
- Is the failure the **caller's access token** or the **Resource Server's client secret** during introspection?
- Is there a request trace/correlation ID to correlate both layers?
- Which policy applies to the path actually seen by the backend?

An HTTP 401 from the introspection endpoint may mean the **Resource Server is using the wrong client secret**, not that the caller needs to open a browser login. The API must fail closed and report an operational error properly, never redirecting all callers to an unexpected login page.

## 22. Special Cases

### 22.1. Public APIs

Genuinely public `permitAll()` endpoints may return 200 with no token. Do not force every `/api/**` request to 401 when authorization policy permits anonymous access.

However, with a bearer token **that is supplied yet invalid**, `BearerTokenAuthenticationFilter` may still attempt validation and return an error before evaluating `permitAll()`, depending on the security filter chain. If a public endpoint must accept tokenless callers, test both no-token and bad-token cases for clear behavior.

### 22.2. “Health” APIs Not Requiring Bearer

`/actuator/health` or a dedicated health route may belong to a separate chain. Decide which endpoints allow unauthenticated access and which expose sensitive info requiring protection. Never put all of Actuator under `permitAll()` just to let load balancer health checks pass.

### 22.3. Cookie-Based APIs Through a BFF

If a frontend calls a BFF using a session cookie, the BFF may be a web app using 302 login for **HTML pages**, yet the BFF's JSON endpoints should usually still have a **dedicated JSON/401 error contract** so the SPA never receives unexpected HTML. Here, Bearer challenges are not strictly needed on the browser-to-BFF layer since the actual credential is a session cookie. Distinguish **credentials per hop**.

Example:

```text
Browser --cookie--> BFF --Bearer access token--> Orders API
```

Orders API still returns Bearer 401 when the BFF's access token is invalid. The BFF can map errors appropriately for the browser per its own contract, while never accidentally returning an HTML page to a JSON request.

### 22.4. WebSocket, SSE, GraphQL

Special protocols or endpoints may use distinct security contexts and error framing:

- GraphQL may return `200` with `errors` per the GraphQL contract even when an authorization resolver fails, yet HTTP handshake authentication must be designed cleanly.
- WebSocket handshakes and message-level auth need dedicated mechanisms rather than a single REST controller rule.
- SSE is an HTTP stream; authentication failures before streaming starts need proper statuses rather than opening an HTML login stream.

Regardless, **never turn token failures into an HTML login page** on endpoints defined as machine-consumed APIs.

### 22.5. OIDC Login Callbacks Are Not Business APIs

Routes `/login/oauth2/code/{registrationId}` and `/oauth2/authorization/{registrationId}` serve the **OAuth2 Login Client**. Redirects are valid there; simply ensure those routes never become the default entry point for `/api/orders/**`.

## 23. Quick Diagnostic Matrix

| Symptom | Likely Cause | Resolution |
|---|---|---|
| `/api/**` returns 302 `/login` when missing token | Form-login entry point matches API | Separate API chain + Bearer entry point |
| API returns 302 `/oauth2/authorization/...` | OAuth2 login chain matches API | Separate web client and RS matchers |
| `/api/**` returns `200 text/html` | HTTP client followed redirect or error page rewrite | Inspect initial response, gateway, and Location |
| API with Accept JSON works, Accept HTML redirects | Content negotiation picking login entry point | Configure Bearer API chain independent of Accept |
| API 401 yet browser reports CORS | Broken preflight/CORS config or gateway block | Configure CorsConfigurationSource and chain |
| Bad JWT gets 401, yet wrong scope redirects | Misconfigured AccessDeniedHandler/exception translation | BearerTokenAccessDeniedHandler and authorization mapping |
| Controller advice misses JWT errors | Error happens in security filter before MVC | AuthenticationEntryPoint/AccessDeniedHandler |
| Backend 401, gateway returns HTML | Gateway custom auth/error page | Adjust API-route handling at gateway |
| Missing token on `/api/**` serves login page | Wrong chain order/matcher | `@Order`, `securityMatcher`, fallback deny-all |
| 401 from wrong introspection client treated as bad user | Outbound RS→AS failure | Classify dependency/client-auth failure |
| SPA infinitely refreshes/logs in on 403 | Client treats 403 same as 401 | Distinguish unauthorized vs. forbidden |
| 302 appears only in production | Proxy/ingress differs from staging or path rewrite | Compare route/hop configs and response headers |

## 24. Long-Term Design Principles

**1. Every API endpoint must have a clear error contract.** Define 401/403/5xx statuses, `WWW-Authenticate`, and JSON/problem+json bodies if any.

**2. HTTP Bearer and web login are two distinct mechanisms.** They can coexist in the same application, but trust boundaries and request matchers must be separated.

**3. Place API security chains before web chains.** Verify `@Order`, `securityMatcher`, and fallback chains; never fix only `requestMatchers` inside the wrong chain.

**4. Use BearerTokenAuthenticationEntryPoint and BearerTokenAccessDeniedHandler.** Never redirect APIs to form login or OIDC authorization endpoints.

**5. Do not rely on the Accept header to choose authentication types.** APIs must behave consistently even for clients sending `text/html` or `*/*`.

**6. Never use @ControllerAdvice to replace security exception handling.** Errors occurring before MVC must be handled at security filters/handlers.

**7. APIs do not refresh bearer tokens themselves.** Clients or BFFs execute valid OAuth flows at the proper boundary.

**8. Never conflate 401 and 403.** Invalid/missing authentication differs from a valid token lacking action or object permissions.

**9. Design CORS, CSRF, and sessions around the credential model.** Fixing redirects does not mean turning off all protections.

**10. Observe responses across every hop.** Gateways/CDNs/ingresses can rewrite status/headers into HTML even when Spring Security is right.

**11. Never expose sensitive info in errors.** Bearer tokens, signing keys, personal claims, secrets, and internal policies must never appear in JSON errors, HTML pages, or logs.

**12. Test missing tokens, invalid tokens, and valid tokens lacking scope.** Verify status/headers/Location/Content-Type across different `Accept` headers and through real proxies.

## 25. References

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `Authorization: Bearer`, `WWW-Authenticate`, `invalid_request`, `invalid_token`, and `insufficient_scope`.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): meanings of HTTP 401, 403, 302, `Location`, and challenges.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): `application/problem+json` format for API errors.
- [Spring Security Reference — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): Bearer authentication, filters/providers, and error handling.
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `jwt()` configuration and validation.
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): `opaqueToken()` configuration and introspection.
- [Spring Security Reference — Java Configuration / Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): multiple `SecurityFilterChain` beans, matcher ordering, and chain selection.
- [Spring Security Reference — Exception Handling](https://docs.spring.io/spring-security/reference/servlet/architecture.html): filter chains, `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, and `AccessDeniedHandler`.
- [Spring Security Reference — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): handling CORS before security when appropriate.

**Key takeaway:** a **Resource Server API receiving Bearer access tokens** should return a **401 Bearer challenge** on missing/invalid tokens and **403** when authenticated but lacking permissions. **302/HTML login belongs to browser login flows**, not as a fallback for Bearer errors. Splitting `SecurityFilterChain` by route, using the right entry point and access-denied handler, and verifying statuses/headers across both backend and gateway keeps the API's authentication contract intact even when the application simultaneously serves web logins.
