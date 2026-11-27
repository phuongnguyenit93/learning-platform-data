# AuthenticationException, AccessDeniedException, and Handling Boundaries

## 1. Why Distinguish Authentication Errors from Authorization Errors?

In **Spring Security OAuth 2.0 / OIDC Resource Server**, an API receives requests like this:

```http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6ImsxIn0...
```

Before a controller executes, several Spring Security layers may participate:

1. Locate and extract the Bearer token from the HTTP request.
2. Verify the token using `JwtDecoder` or `OpaqueTokenIntrospector`.
3. Create an authenticated `Authentication` with scopes/authorities.
4. Check HTTP authorization conditions, e.g., `hasAuthority("SCOPE_orders:read")`.
5. Check service/method conditions and resource ownership.

When a step fails, Spring Security must return a meaningful response: **the token was not accepted** or **the token was accepted but lacks permissions**. These two cases flow through different exception mechanisms:

- **`AuthenticationException`** represents failures during authentication, e.g., a token rejected for bad signature, expiration, or contract mismatch.
- **`AccessDeniedException`** represents a decision denying a requested operation. It can arise when a valid token lacks an authority, or when method security denies object access.

However, there is no absolute rule that “every `AuthenticationException` is definitely handled by `ExceptionTranslationFilter`” or “every `AccessDeniedException` returns 403”. **Where the error originates, the caller's state, and which filter/handler holds responsibility** determine the actual path.

This lesson focuses on the **handling boundaries** of both exception families in the Spring Security Servlet stack, how the Resource Server builds **HTTP 401/403** responses and **`WWW-Authenticate: Bearer`** headers under **RFC 6750**, how to customize the right extension points, and test scenarios to protect the API contract.

> **Scope:** Java 17+, Spring Boot 3.x, Spring Security 6.x Servlet MVC, JWT or opaque access tokens. Some class/method names may vary by specific version; consult your project's API docs before upgrading. Issuers, endpoints, scopes, and tokens in this lesson are examples only.

## 2. Two Different Kinds of Denial

Suppose an API has two endpoints:

```text
GET  /api/orders/{id}   → requires SCOPE_orders:read
POST /api/orders        → requires SCOPE_orders:write
```

A `GET` request can fail due to:

| Scenario | Authentication | Authorization | Expected Logical Error |
|---|---|---|---|
| No Bearer token sent | No suitable principal | Route requires authentication | Initiate authentication, usually 401. |
| Expired Bearer token | Token rejected | Permissions not evaluated | Authentication failure, usually 401. |
| JWT bad signature | Token rejected | Permissions not evaluated | Authentication failure, usually 401. |
| JWT valid signature but wrong issuer/audience | Token fails API contract | Permissions not evaluated | Authentication failure, usually 401. |
| Valid token, only has `SCOPE_orders:write` | Authenticated | Lacks `SCOPE_orders:read` | Access denied, usually 403. |
| Valid token, has `SCOPE_orders:read`, order belongs to another user | Authenticated | No permission on object | Access denied or 404 per data policy. |
| Valid token, has scope, order belongs to principal | Authenticated | Permitted | Proceed with business execution. |

In OIDC, never use an **ID Token** as a Resource Server Bearer credential merely because its signature is valid. The API must verify the access token has the right issuer, audience, token type, and claims profile. Wrong audience/token type belongs to authentication/token validation—not solved by adding scopes.

### 2.1. Authentication Does Not Mean Sufficient Scope

`authenticated()` checks authentication state; it does not infer the access token has `orders:read`.

```java
// Only requires an authenticated caller; does not guarantee sufficient scope.
.requestMatchers("/api/orders/**").authenticated()
```

A route needing specific operational permissions should use:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders:read")
```

Even after passing `hasAuthority`, the app still must check owner, tenant, account, ACL, and resource state rules; scope does not automatically grant access to all orders.

### 2.2. Exceptions Are Not HTTP Status Codes

**`AuthenticationException` and `AccessDeniedException` are Java/Spring Security concepts**, not pre-built HTTP responses. Different classes turn exceptions into responses:

- **`AuthenticationEntryPoint`** initiates the response requiring/rejecting authentication, usually used for 401.
- **`AccessDeniedHandler`** handles permission denial decisions, usually used for 403.
- **`AuthenticationFailureHandler`** may be called directly by the authentication filter when an authentication attempt fails.
- **`ExceptionTranslationFilter`** intercepts certain exceptions from downstream filters/handlers and selects either the entry point or denied handler.
- **Spring MVC `HandlerExceptionResolver` / `@ControllerAdvice`** handles exceptions visible to MVC; it does not cover every exception occurring before the controller.

Saying “just throw `AccessDeniedException` and Spring automatically returns 403 everywhere” is dangerous, because exception routing depends on where it is thrown and which filter catches it.

---

## 3. Core Spring Security Servlet Classes

A JWT Resource Server filter chain typically involves these components:

| Component | Role | Key Note |
|---|---|---|
| **`FilterChainProxy`** | Selects and runs a `SecurityFilterChain` matching the HTTP request. | Endpoints matching no protected chain may miss expected rules. |
| **`BearerTokenAuthenticationFilter`** | Extracts Bearer token and requests authentication via `AuthenticationManager` or resolver. | Has its own authentication error handling; does not rely solely on `ExceptionTranslationFilter`. |
| **`JwtAuthenticationProvider`** | Uses `JwtDecoder` to verify JWT and convert into authentication. | Decoder/validator failures normally become authentication failures. |
| **`OpaqueTokenAuthenticationProvider`** | Introspects opaque token and creates authentication. | Inactive token errors differ from AS network/credential errors. |
| **`ExceptionTranslationFilter`** | Translates downstream `AuthenticationException`/`AccessDeniedException` into HTTP security behavior. | Only catches exceptions thrown inside the `filterChain.doFilter(...)` scope it wraps. |
| **`AuthorizationFilter`** | Enforces HTTP authorization via `AuthorizationManager`. | On denial, may throw `AccessDeniedException` or a subclass. |
| **`BearerTokenAuthenticationEntryPoint`** | Generates RFC 6750 Bearer challenges for authentication failures. | Usually returns 401 and `WWW-Authenticate: Bearer`, with details depending on OAuth2 error. |
| **`BearerTokenAccessDeniedHandler`** | Handles access denial in Bearer token contexts. | Usually returns 403; may attach `insufficient_scope` when caller is recognized as OAuth2-authenticated. |
| **`SecurityContextHolder`** | Holds authentication in the current request context. | Never infer from raw tokens when context lacks a trusted authentication. |

### 3.1. Request Processing Flow

```mermaid
flowchart TD
    A["HTTP request"] --> B["FilterChainProxy / SecurityFilterChain"]
    B --> C["BearerTokenAuthenticationFilter"]
    C --> D{"Bearer token present?"}
    D -->|Yes| E["AuthenticationManager"]
    E --> F{"JWT verify / introspection succeeded?"}
    F -->|No| G["AuthenticationFailureHandler"]
    G --> H["BearerTokenAuthenticationEntryPoint → 401 / challenge"]
    F -->|Yes| I["Authentication in SecurityContext"]
    D -->|No| J["Continue with unauthenticated context"]
    I --> K["ExceptionTranslationFilter"]
    J --> K
    K --> L["AuthorizationFilter / MVC / method security"]
    L --> M{"Denied?"}
    M -->|No| N["Controller / Service"]
    M -->|Yes, AccessDeniedException| O{"Caller suitably authenticated?"}
    O -->|No or anonymous| P["AuthenticationEntryPoint → 401"]
    O -->|Yes| Q["AccessDeniedHandler → 403"]
    L -->|AuthenticationException| P
```

The diagram deliberately highlights two points:

1. **Errors inside `BearerTokenAuthenticationFilter` can be handled right in that filter** by its failure handler, before an exception ever reaches `ExceptionTranslationFilter`.
2. `ExceptionTranslationFilter` wraps the downstream authorization section. It is not an application-wide `try/catch` placed outside every filter.

Exact ordering and active filters depend on Spring Security configuration. With custom filters, multiple chains, or alternative authentication, verify which side of the handling boundary they sit on.

## 4. `AuthenticationException`: Failure at Authentication

`org.springframework.security.core.AuthenticationException` is the superclass of exceptions representing authentication problems. Familiar subclasses include:

- `BadCredentialsException`: credential supplied but rejected across many authentication styles.
- `AuthenticationCredentialsNotFoundException`: no matching authentication found where authentication is required.
- `InsufficientAuthenticationException`: current authentication level is insufficient for the requested action.
- `OAuth2AuthenticationException`: error in an OAuth 2.0 context, which may carry an `OAuth2Error` object.
- `InvalidBearerTokenException`: a Bearer token error in Spring Security Resource Server, carrying corresponding OAuth2 error info.

Application code does not need to throw these exceptions at every layer. Usually **framework providers/filters** choose the right exception when processing tokens.

### 4.1. Example: Expired JWT

`JwtDecoder` reads the Bearer JWT and checks signatures/claims. If `exp` is expired, decoding/validation fails. Through the authentication provider and filter, this error is typically routed to Bearer authentication failure handling.

```text
Authorization: Bearer <expired-JWT>
        ↓
BearerTokenAuthenticationFilter
        ↓
JwtAuthenticationProvider → JwtDecoder
        ↓
JWT validation fails
        ↓
Authentication failure handling
        ↓
HTTP 401 + WWW-Authenticate Bearer challenge
```

RFC 6750-style response example:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
```

Exact headers, realm, description, and other security headers depend on handler, request, configuration, and version. Do not assert the response body will always contain JSON or always carry the exact same `error_description`.

### 4.2. Missing Bearer Token

A request without an Authorization header can pass through `BearerTokenAuthenticationFilter` **without throwing an immediate error**: finding no token, the filter lets the request continue. Upon reaching `AuthorizationFilter`, a route requiring authentication/authority denies access, and `ExceptionTranslationFilter` selects `AuthenticationEntryPoint` because the caller is unauthenticated or anonymous.

```text
GET /api/orders/42
(no Authorization header)
        ↓
BearerTokenAuthenticationFilter: no token, continue
        ↓
AnonymousAuthenticationFilter (if configured)
        ↓
AuthorizationFilter: missing permission
        ↓
ExceptionTranslationFilter: anonymous/unauthenticated
        ↓
AuthenticationEntryPoint
        ↓
HTTP 401 + WWW-Authenticate: Bearer
```

This explains why **the same HTTP 401** can come from two different boundaries: the authentication filter's failure handler or the entry point called by `ExceptionTranslationFilter`.

### 4.3. Malformed Bearer Header

A syntactically invalid request, mixing multiple token submission methods, or sending a malformed token format can be rejected by the Bearer token resolver before `JwtDecoder` is ever called.

Example that must not be treated as two equivalent tokens:

```http
GET /api/orders/42?access_token=token-B HTTP/1.1
Authorization: Bearer token-A
```

By default, Spring Security usually reads Bearer tokens from the `Authorization` header; query/form support depends on `BearerTokenResolver` and configuration. RFC 6750 sets constraints to prevent sending tokens via multiple methods in one request. Do not enable the `access_token` query parameter casually because tokens risk leaking into logs, browser history, and proxies.

For syntax errors `invalid_request`, RFC 6750 suggests HTTP **400 Bad Request** where appropriate; for `invalid_token`, usually **401**. Hence the claim “every `AuthenticationException` always returns 401” is inaccurate. `BearerTokenAuthenticationEntryPoint` can use the HTTP status inside `BearerTokenError` when the exception carries matching OAuth2 error details.

### 4.4. Cases That Are Not AuthenticationException

A `JwtException`, Jackson error, JWKS timeout, HTTP introspection error, or `IllegalArgumentException` **is not necessarily an `AuthenticationException` at its origin**. Providers or filters may wrap/convert errors per library mechanics; if a custom component throws an arbitrary exception, it may turn into a **500** instead of reaching the Bearer authentication entry point.

Therefore, custom `JwtDecoder`/`OpaqueTokenIntrospector` implementations must preserve the **exception contract** of the Spring Security API they implement. Never catch all exceptions and return an “authenticated” principal when the token was not verified.

---

## 5. `AccessDeniedException`: Caller Is Not Permitted to Perform the Action

`org.springframework.security.access.AccessDeniedException` occurs when an authorization decision denies the operation. In Spring Security 6.x, some authorization APIs may use a subclass such as `AuthorizationDeniedException`.

Example:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders:read")
    .anyRequest().denyAll())
```

Valid JWT with only:

```json
{
  "sub": "alice-123",
  "scope": "orders:write",
  "aud": ["orders-api"]
}
```

`JwtGrantedAuthoritiesConverter` may produce authority `SCOPE_orders:write`. When calling `GET /api/orders/42`, the request still lacks `SCOPE_orders:read`. `AuthorizationFilter` will deny it, and in a typical Bearer Resource Server, `ExceptionTranslationFilter` uses `AccessDeniedHandler` to return **403**.

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

This is a *typical* response, not a guarantee that every HTTP 403 attaches the exact `insufficient_scope` string; `BearerTokenAccessDeniedHandler` can only supply matching OAuth2 info when it recognizes the corresponding authentication state.

### 5.1. One Exception, Two Different Response Paths

`ExceptionTranslationFilter` typically branches based on **authentication state**:

| Exception Handled by Filter | Caller State | Typical Branch |
|---|---|---|
| `AuthenticationException` | Any | `AuthenticationEntryPoint`. |
| `AccessDeniedException` | Anonymous or insufficient authentication per `AuthenticationTrustResolver` | Initiate authentication via `AuthenticationEntryPoint`. |
| `AccessDeniedException` | Appropriately authenticated principal | `AccessDeniedHandler`. |

Why does denying an anonymous caller usually produce **401** instead of 403? Because the user has not yet presented a valid authentication credential. The API needs to send a Bearer challenge telling the client it must supply a token. Only after a valid token still lacks permissions does **403** apply.

If the application uses pre-auth, remember-me, or multiple authentication mechanisms, `AuthenticationTrustResolver` and context can affect how Spring judges “sufficiently authenticated”. Never assume every custom `Authentication` object is trusted by Spring at the same level as a verified JWT.

### 5.2. BOLA/IDOR: Valid Scope Can Still Be Denied

Alice has a valid token with `SCOPE_orders:read` yet tries to read Bob's order:

```http
GET /api/orders/order-bob-200 HTTP/1.1
Authorization: Bearer <valid-token-for-alice>
```

HTTP rules may let the request through because the scope matches. The service still must check owner/tenant. Example:

```java
if (!order.getOwnerSubject().equals(actor.subject())) {
    throw new AccessDeniedException("Order is not accessible");
}
```

Another policy may choose to return **404 Not Found** to conceal the existence of unauthorized orders; that is a business/privacy decision, not a substitute for authorization checks. Never put the owner's user ID or secret tenant in the error body.

### 5.3. Do Service Exceptions Automatically Become 403?

If the service is called by a controller inside an **HTTP Servlet flow passing through the Spring Security filter chain**, and the exception is not caught earlier by Spring MVC, `AccessDeniedException` can propagate out of `DispatcherServlet` to `ExceptionTranslationFilter` to be handled.

However, this is **not guaranteed in every architecture**:

- A `@ControllerAdvice`/`HandlerExceptionResolver` may handle the exception **inside Spring MVC** before it reaches the filter.
- A custom filter running **before** `ExceptionTranslationFilter` may throw an exception outside that filter's try/catch.
- **Async/background jobs/message listeners** do not pass through the HTTP filter chain like synchronous requests.
- A service invoked from another entry point may need its own translation policy.

Therefore, for object-level denial, **align on who owns translating errors to HTTP**: either let exceptions propagate out to the security handler, or convert them into a domain exception with a clearly designed MVC mapping. Avoid two layers writing the response.

---

## 6. What Does `ExceptionTranslationFilter` Do and Not Do?

The name `ExceptionTranslationFilter` easily misleads learners into thinking it is a “global exception handler” for the whole application. In reality it is a **security filter**:

- Wraps downstream filters via `chain.doFilter(...)`.
- Recognizes `AuthenticationException` and `AccessDeniedException` thrown within that scope, even when wrapped inside certain servlet exceptions per Spring conventions.
- Selects `AuthenticationEntryPoint` or `AccessDeniedHandler` based on authentication state.
- May use `RequestCache` on the authentication-initiation path; stateless APIs usually do not want to store requests in sessions.

### 6.1. Positional Boundaries

```mermaid
flowchart LR
    A["Filter before ExceptionTranslationFilter"] --> E["ExceptionTranslationFilter"]
    E --> Z["AuthorizationFilter / DispatcherServlet / Controller"]
    A --> B["Error directly in earlier filter"]
    B --> C["Not automatically caught by ETF"]
    Z --> D["Exception propagates back up"]
    D --> E
    E --> F["AuthenticationEntryPoint or AccessDeniedHandler"]
```

In a standard pipeline, `BearerTokenAuthenticationFilter` handles its own errors via its failure handler. It does not rely on `ExceptionTranslationFilter` sitting elsewhere to catch those errors.

If you add a custom filter processing Bearer tokens before Spring Security or a custom authentication filter, determine:

1. Does the filter sit before or after `ExceptionTranslationFilter`?
2. Does it actually run inside `FilterChainProxy`, or is it registered directly in the Servlet container outside the chain?
3. Which exception types does it throw?
4. Who is responsible for clearing SecurityContext and writing responses when authentication fails?
5. Could it call `chain.doFilter(...)` after a response was already sent or committed?

There is no automatic “global catch” across every filter.

### 6.2. Committed Response Boundary

If a filter/controller has already written data and committed the response, the handler cannot safely change the status to 401/403 and append a Bearer challenge. `ExceptionTranslationFilter` may error when it detects an exception cannot be handled because the response is already committed.

Design rules:

- Verify Bearer tokens and authorization **before** sending sensitive data.
- Never stream part of a response and only afterward check file/order permissions.
- Never call `sendError(...)` after the output stream has been committed.
- Never handle errors by both writing JSON and calling a delegate entry point/denied handler that also writes.
- For streaming, SSE, or async, enforce policy at the boundary before starting the stream and define behavior if permissions change mid-stream.

### 6.3. Request Cache and Stateless APIs

In form-login apps, when unauthenticated, the original request may be saved to replay after login. For Bearer-token Resource Servers, browser redirects/session request caches are usually not desired. A stateless config may use:

```java
.sessionManagement(session ->
    session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
.requestCache(cache -> cache.disable())
```

Disabling the request cache is appropriate for pure Bearer APIs. However, if the app also uses browser sessions, SSO login redirects, or MVC views, design explicit multiple `SecurityFilterChain`/authentication policies instead of blindly disabling all session features.

---

## 7. `AuthenticationEntryPoint`: Boundary for Returning Responses When Authentication Is Required

Interface:

```java
package org.springframework.security.web;

public interface AuthenticationEntryPoint {
    void commence(
        HttpServletRequest request,
        HttpServletResponse response,
        AuthenticationException authException
    ) throws IOException, ServletException;
}
```

This is the conceptual interface signature, with corresponding Servlet imports depending on Spring Security/Jakarta Servlet version.

In a Resource Server, **`BearerTokenAuthenticationEntryPoint`** is the implementation aligned with RFC 6750. It builds `WWW-Authenticate` challenges and statuses for Bearer authentication cases.

### 7.1. What Is a Challenge?

A response:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

tells the client the resource expects a Bearer credential. Some cases carry an OAuth2 error:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

`realm` or `error_description` may appear if the handler has the data and policy permits. Avoid depending on English wording of error descriptions in client logic; applications should branch on HTTP status and standard error codes.

### 7.2. RFC 6750 Bearer Errors

| Error Code | Meaning | Typical HTTP Status |
|---|---|---|
| **`invalid_request`** | Malformed Bearer request / missing required parameter / token sent via multiple invalid methods. | **400 Bad Request** in cases described by RFC. |
| **`invalid_token`** | Token expired, revoked, invalid, or non-compliant with contract. | **401 Unauthorized**. |
| **`insufficient_scope`** | Request has a token, but permissions are insufficient for the resource. | **403 Forbidden**. |

RFC 6750 does not require attaching `error` to every challenge when **the request provides no credentials at all**. Thus you should not expect every 401 to contain `error="invalid_token"`. For no-token cases, `WWW-Authenticate: Bearer` alone can be standard behavior.

### 7.3. Do Not Arbitrarily Return 200/302 in APIs

If using a custom JSON body for authentication errors, still preserve:

- Meaningful 401 status (or 400 for applicable Bearer `invalid_request`).
- `WWW-Authenticate` per Bearer challenge.
- No leakage of raw Bearer tokens, secrets, or PII claims.
- No redirect to HTML login when the API contract is a JSON Bearer Resource Server.
- No creation of an authenticated “guest principal” to fill the gap when a token is invalid.

A frontend can open a login page on its own when it receives 401, without the API turning every authentication failure into a `302` redirect.

---

## 8. `AccessDeniedHandler`: Boundary for Returning Responses When Permissions Are Insufficient

Interface:

```java
package org.springframework.security.web.access;

public interface AccessDeniedHandler {
    void handle(
        HttpServletRequest request,
        HttpServletResponse response,
        AccessDeniedException accessDeniedException
    ) throws IOException, ServletException;
}
```

In a Bearer Resource Server, **`BearerTokenAccessDeniedHandler`** is typically used to emit `insufficient_scope` when the caller is authenticated via a compatible OAuth2 type. For principals lacking sufficient OAuth2 authentication indicators, the handler may return only a challenge without detailed error codes. This prevents falsely claiming “the server verified the token, only scope is missing” when the authentication state is not firmly established.

### 8.1. 403 Does Not Mean a Broken Token

Valid token, missing scope:

```text
JWT signature validation  → PASS
issuer/audience/exp        → PASS
SCOPE_orders:read          → MISSING
                           ↓
AccessDeniedHandler        → 403
```

The client may need to request additional scopes through proper OAuth flows (if permitted), rather than simply refreshing the same token expecting permissions to expand automatically.

### 8.2. 403 Can Also Come from Constraints Other Than Scope

For example, the request is authenticated and has sufficient scope, yet:

- User does not belong to the required tenant.
- User does not own the order.
- Role is restricted by department.
- An action requires dual approval.
- An endpoint requires a feature entitlement condition.
- CSRF protection denies a cookie/session request, because `CsrfException` belongs to the access-denied family in the Security stack.

Never assume every 403 equals **`insufficient_scope`**. If a custom handler always writes `error="insufficient_scope"` for every `AccessDeniedException`, it can mislead clients into thinking they just need more scopes, even when denied due to owner/tenant or CSRF.

An API may return `404` when a resource is outside visible permissions to prevent object enumeration; that is a separate **domain authorization/error policy** decision. When changing status codes, check RFC 6750 conditions and which handler is executing so responses never contradict Bearer challenge semantics.

---

## 9. Basic Spring Boot / Spring Security Configuration

Example `orders-api` accepting JWT access tokens. If using Maven with Spring Boot parent/BOM:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Configuring issuer and audience:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test/realms/orders
          audiences:
            - orders-api
```

This is an example configuration for JWT. If using opaque tokens, select `opaquetoken` with appropriate introspection URI and credentials; never assume one mechanism automatically falls back to the other on failure.

### 9.1. `SecurityFilterChain` Requiring Explicit Scopes

```java
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
        return http
            // Appropriate only for stateless APIs using Bearer headers,
            // not using cookies/sessions as primary auth.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(cache -> cache.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/ping")
                    .permitAll()

                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")

                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders:write")

                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
```

This configuration defines **HTTP-level authorization** only. Controllers/services still need object-level authorization with owner/tenant checks. If the API uses session cookies, do not copy `csrf(...disable)` unconditionally.

### 9.2. One Route, Different Outcomes

`GET /api/orders/42`:

| Header and Token | Authority | Typical Outcome |
|---|---|---|
| No `Authorization` | None | 401, Bearer challenge. |
| Expired `Authorization: Bearer ...` | No valid authentication created | 401, possibly `invalid_token`. |
| Valid JWT for API without read scope | `SCOPE_profile` | 403, possibly `insufficient_scope`. |
| Valid JWT with read scope | `SCOPE_orders:read` | Passes HTTP rule; subject to object/business policy. |
| Valid JWT, right scope, ID belongs to someone else | `SCOPE_orders:read` | Denied at service or 404 per policy. |

If the same request returns a 302 login page or 200 HTML login form, the API may have hit another form-login/session entry point instead of the Bearer entry point. Check multiple filter chains and matcher ordering.

---

## 10. Customizing `AuthenticationEntryPoint` and `AccessDeniedHandler` Properly

A team wants consistent JSON responses, such as:

```json
{
  "code": "AUTHENTICATION_REQUIRED",
  "message": "A valid access token is required",
  "requestId": "req-123"
}
```

and:

```json
{
  "code": "ACCESS_DENIED",
  "message": "Access is not permitted",
  "requestId": "req-456"
}
```

What you can do is **delegate the Bearer challenge/status to the standard handler**, then write a safe body if the response is not yet committed and status is appropriate. Never rewrite all RFC 6750 parsing by hand just to change error JSON.

### 10.1. Using Standard Bearer Handlers

Explicit configuration:

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;

@Configuration
public class BearerErrorHandlers {

    @Bean
    AuthenticationEntryPoint bearerEntryPoint() {
        return new BearerTokenAuthenticationEntryPoint();
    }

    @Bean
    AccessDeniedHandler bearerDeniedHandler() {
        return new BearerTokenAccessDeniedHandler();
    }
}
```

Then in `SecurityFilterChain` you can configure:

```java
.oauth2ResourceServer(oauth -> oauth
    .authenticationEntryPoint(bearerEntryPoint)
    .accessDeniedHandler(bearerDeniedHandler)
    .jwt(Customizer.withDefaults()))
```

When using bean parameter injection, `bearerEntryPoint` and `bearerDeniedHandler` must be correctly typed beans/injected variables. The snippet above is a **configuration fragment to integrate** into an existing chain, not a standalone chain. Declaring entry point/denied handler via the Resource Server DSL aligns with Bearer mechanics; if other authentication schemes exist, you may also need `exceptionHandling(...)` and exact matchers.

### 10.2. Pragmatic Option: Logging/Decorating and Delegating

Not every API needs a JSON body. Many systems keep the default `WWW-Authenticate` response, emit separate events/metrics, and let clients read HTTP status/error codes from headers. This lowers the risk of customizations breaking RFC 6750 semantics.

Decorator example for the entry point:

```java
package com.example.orders.security;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.web.AuthenticationEntryPoint;

public final class ObservedBearerEntryPoint
        implements AuthenticationEntryPoint {

    private final BearerTokenAuthenticationEntryPoint delegate =
        new BearerTokenAuthenticationEntryPoint();

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException, ServletException {

        // Log only bounded reason codes, normalized path, and request ID.
        // Never log raw Authorization headers or library exception
        // messages if they could contain tokens/PII.
        recordAuthFailure(request, exception);

        delegate.commence(request, response, exception);
    }

    private void recordAuthFailure(
            HttpServletRequest request,
            AuthenticationException exception) {
        // Integrate safe metrics/logs per application.
    }
}
```

Similarly for the denied handler:

```java
package com.example.orders.security;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
import org.springframework.security.web.access.AccessDeniedHandler;

public final class ObservedBearerDeniedHandler
        implements AccessDeniedHandler {

    private final BearerTokenAccessDeniedHandler delegate =
        new BearerTokenAccessDeniedHandler();

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            AccessDeniedException exception)
            throws IOException, ServletException {

        recordAccessDenied(request, exception);
        delegate.handle(request, response, exception);
    }

    private void recordAccessDenied(
            HttpServletRequest request,
            AccessDeniedException exception) {
        // Integrate safe metrics/logs per application.
    }
}
```

The advantage is that challenge details, `invalid_token`, `insufficient_scope`, and statuses determined by Spring Security **remain in the standard implementation**. This option does not write a JSON body itself.

### 10.3. When a JSON Body Is Truly Needed

One possible pattern:

1. Invoke the standard handler to prepare status and `WWW-Authenticate`.
2. If the response is not committed, status is appropriate, content-type has not been sent, and the error contract allows, set `application/problem+json` or `application/json`.
3. Write a body **containing no tokens, sensitive claims, or other owners' info**.
4. Never call `sendError` after writing a response body has begun.
5. Never write two bodies from two different handlers.
6. Test realistically through the filter chain and gateway for missing token, bad token, and missing scope.

This approach requires care: a standard handler may use `setStatus` or `sendError` depending on implementation; `sendError` may commit or cause the container to render an error page. **Do not assume you can write a body after `delegate.commence(...)` across all versions/Servlet containers.** If a strict JSON contract is mandatory, write a thoroughly integration-tested handler that constructs the Bearer challenge directly from `BearerTokenError` and standard statuses rather than layering bodies uncontrollably.

### 10.4. Do Not Let ErrorController Mask Bearer Responses

Spring Boot has error dispatch/mapping (`/error`) and may produce default JSON or HTML error pages for certain failures. Security handlers have their own responsibility; not every 401/403 should route through Boot's `ErrorController`.

If `WWW-Authenticate` disappears after adding a custom error handler or error page, check:

- `sendError`/forwarding to `/error`.
- Whether `ERROR` dispatcher type hits a different filter chain.
- Whether the response was already committed.
- Whether a `@ControllerAdvice` caught the security exception in MVC and wrote its own response.
- Whether a reverse proxy/gateway altered headers.

Test actual responses over HTTP, not only direct method calls.

---

## 11. Configuring `exceptionHandling` and Multiple Filter Chains

Spring Security provides the DSL:

```java
.exceptionHandling(ex -> ex
    .authenticationEntryPoint(bearerEntryPoint)
    .accessDeniedHandler(bearerDeniedHandler))
```

And the Resource Server DSL:

```java
.oauth2ResourceServer(oauth -> oauth
    .authenticationEntryPoint(bearerEntryPoint)
    .accessDeniedHandler(bearerDeniedHandler)
    .jwt(Customizer.withDefaults()))
```

These configuration points can complement or override one another depending on chain structure and version. For pure Bearer APIs, it is usually simplest to keep Resource Server configuration consistent, declare the right entry point/denied handler, and integration-test responses. If the app also uses form login, Basic, sessions, or public web endpoints, split chains with `securityMatcher` and `@Order` where appropriate.

### 11.1. An App with Both Browser UI and API

Conceptual example:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/ping").permitAll()
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth ->
            oauth.jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/web/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
```

Necessary imports must be included (`@Order`, `@Bean`, `HttpSecurity`, `SecurityFilterChain`, and `Customizer`). This is an **illustrative chain-splitting sample**, not a complete security configuration: the API chain needs scope rules/stateless/CSRF policies; the web chain needs matching CSRF/session policies. `@Order` controls chain priority; Spring Security selects the **first matching chain**. If `securityMatcher` accidentally overlaps too broadly, `/api/**` requests could receive form-login redirects or web requests could hit Bearer handlers.

### 11.2. Matcher Order and Security Holes

Within a single chain, authorization rules are typically evaluated in order; placing a broad matcher before a specific one can nullify the specific rule.

Wrong:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll())
```

`/api/admin/**` already matches the first rule, so the later `ADMIN` requirement is never enforced. Better order:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll())
```

Specific scopes are still needed for real APIs. Replacing every `hasAuthority` with `authenticated()` just to avoid 403 is **privilege broadening**, not a fix.

---

## 12. Boundary Between Spring Security Filters and Spring MVC Exception Handling

In a Spring MVC app, `DispatcherServlet` has its own exception-resolution system:

- `@ExceptionHandler` inside controllers.
- `@ControllerAdvice`.
- `HandlerExceptionResolver` / framework resolvers.
- Boot error handling for unhandled exceptions.

These mechanisms are not full replacements for `AuthenticationEntryPoint` and `AccessDeniedHandler`.

### 12.1. Why Doesn't `@RestControllerAdvice` Catch Every Token Error?

Errors like an invalid JWT signature happen in **`BearerTokenAuthenticationFilter`**, **before** the request enters a controller:

```text
HTTP request
  → Servlet filters / Spring Security
    → BearerTokenAuthenticationFilter: JWT invalid
      → AuthenticationFailureHandler / EntryPoint
  (DispatcherServlet has not run yet)
```

Therefore:

```java
@RestControllerAdvice
class ApiErrorAdvice {

    @ExceptionHandler(AuthenticationException.class)
    ResponseEntity<?> handle(AuthenticationException ex) {
        // Not guaranteed to be called for errors from BearerTokenAuthenticationFilter.
        return ResponseEntity.status(401).build();
    }
}
```

The snippet above is not a reliable way to “catch all 401s”. Security filters can handle errors directly outside MVC. Use `AuthenticationEntryPoint` for authentication filter/`ExceptionTranslationFilter` errors; use advice only for exceptions genuinely inside the MVC boundary and explicitly designed.

### 12.2. What If a Service Throws `AccessDeniedException`?

Suppose:

```java
@Service
class OrderService {
    Order getOrder(String id, Actor actor) {
        Order order = repository.findById(id)
            .orElseThrow(NotFoundException::new);

        if (!authorization.canRead(actor, order)) {
            throw new AccessDeniedException("Order forbidden");
        }
        return order;
    }
}
```

If `AccessDeniedException` propagates out of the controller/`DispatcherServlet`, `ExceptionTranslationFilter` can catch it when the request sits in a matching chain. However, an overly broad `@ControllerAdvice` may intercept it first:

```java
// RISK: catches all exceptions and arbitrarily returns 200/400/500.
@ExceptionHandler(Exception.class)
ResponseEntity<?> handleAll(Exception ex) {
    return ResponseEntity.ok(Map.of("error", "failed"));
}
```

That turns an authorization denial into HTTP 200—wrong for both security and observability. If advice must cover domain exceptions:

- Never convert security exceptions into success responses.
- Clearly distinguish `AccessDeniedException` from business errors.
- Never log raw tokens or sensitive contents.
- Preserve status/headers aligned with the HTTP/Bearer contract.
- Write integration tests proving unauthorized requests never reach business logic.

### 12.3. Problem with Custom Servlet Filters Outside Spring Security

If a filter is registered via `FilterRegistrationBean` or `@Component` as a servlet filter **outside `FilterChainProxy`**, how it participates differs from a filter added via `http.addFilterBefore/After(...)`. Exceptions it throws may never reach `ExceptionTranslationFilter`.

So never put sensitive authorization logic into an arbitrary filter expecting Spring Security to handle its errors like a framework filter. If a custom filter is unavoidable:

1. Pinpoint its exact position and lifecycle.
2. Define who catches failures.
3. Maintain proper SecurityContext cleanup.
4. Use an entry point/denied handler with a clear contract if crafting responses directly.
5. Verify behavior across `REQUEST`, `ASYNC`, and `ERROR` dispatches when needed.
6. Avoid double-registering the same filter in both the Servlet container and Spring Security.

### 12.4. Methods Invoked Outside HTTP

Method security can also be triggered from scheduled jobs, messaging consumers, or application event listeners. If a method throws `AccessDeniedException` without an HTTP request passing through `ExceptionTranslationFilter`, **no Bearer HTTP 403 is produced automatically**. Callers at those entry points need their own domain error policy, such as nacking a message, routing to a DLQ, or recording an audit entry per requirements. Never use HTTP responses as the universal model for every call site.

---

## 13. Choosing Exceptions in Custom Layers According to Context

An API may have custom components:

- Custom `JwtDecoder` or JWT validator.
- Custom `OpaqueTokenIntrospector`.
- `Converter<Jwt, ? extends AbstractAuthenticationToken>`.
- Custom `AuthorizationManager`.
- `@PreAuthorize` with an authorization bean.
- Domain service checking owner/tenant.

Each place carries different responsibilities.

### 13.1. Rejecting Tokens at the Authentication Boundary

If a token lacks a required audience, has the wrong issuer, or opaque introspection reports inactive, reject it **before creating a successful authentication**.

```text
Token has valid signature, but aud does not contain orders-api
      ↓
JWT validator / token contract validator fails
      ↓
JwtDecoder / authentication provider
      ↓
Authentication failure (Bearer challenge)
```

Never create an authenticated `JwtAuthenticationToken` and then throw `AccessDeniedException` later just for a wrong audience. Audience is a **prerequisite for accepting the token as an API credential**.

### 13.2. Denying Permissions at the Authorization Boundary

If a token is valid yet lacks `SCOPE_orders:read`, HTTP authorization or method authorization rules deny it. Do not pretend the token has a bad signature to emit 401, as that confuses clients into infinitely refreshing tokens without gaining scopes.

Similarly, if a token is authenticated and has the scope yet is not allowed to view Bob's order, domain policy denies object access.

### 13.3. Infrastructure Failures Should Not Masquerade as Bad Tokens

When a JWKS endpoint, introspection endpoint, or entitlement database times out, the program **lacks a reliable result** to authenticate or authorize. Security requires **failing closed**, though you must classify errors carefully:

- Bad JWT signature or inactive token: credential/token error.
- Expired introspection client secret: Resource Server–AS integration error.
- AS returns `503`: dependency error.
- Database ownership lookup timeout: indeterminate business/authorization error.

Never write:

```java
try {
    return introspector.introspect(token);
} catch (Exception ex) {
    return anonymousOrPrivilegedPrincipal();
}
```

Never return `200` thinking “maybe the AS is just having a blip”. If the API needs 503 for dependency outages, design an appropriate handler/exception translation layer—never an arbitrary `@ControllerAdvice` that breaks Bearer validation paths.

### 13.4. Avoid Overly Broad `try/catch Exception`

Bad example:

```java
try {
    updateOrder();
} catch (Exception ex) {
    return ResponseEntity.status(401).build();
}
```

This code conflates:

- Invalid token.
- Missing scope.
- Order not belonging to owner.
- SQL connection timeout.
- `NullPointerException` bug.
- Non-existent order.

The result is misleading responses and masked programming bugs. Classify exceptions by **boundary and ownership** instead of turning every failure into an authentication failure.

---

## 14. Calling `AuthenticationEntryPoint` Directly in a Custom Component: Should You?

Some code attempts:

```java
if (tokenInvalid) {
    response.setStatus(401);
    response.getWriter().write("unauthorized");
    filterChain.doFilter(request, response);
}
```

This contains multiple bugs:

- Continues running the filter chain after writing a 401 response.
- Omits `WWW-Authenticate: Bearer`.
- Controller may still execute and overwrite/commit the response.
- SecurityContext may retain stale authentication if custom filter management is faulty.
- Response body may leak internal error details.

If a custom filter **genuinely owns authentication and does not use the standard filter**, one pattern is:

```java
try {
    Authentication authentication = authenticateToken(request);
    SecurityContextHolder.getContext()
        .setAuthentication(authentication);
    filterChain.doFilter(request, response);
} catch (AuthenticationException ex) {
    SecurityContextHolder.clearContext();
    bearerEntryPoint.commence(request, response, ex);
    return;
}
```

This is only **pseudocode** illustrating exception-management steps; production code also needs SecurityContext repository handling, authentication results, async dispatch, duplicate filter registration protection, bearer resolvers, token errors, and Spring version-specific lifecycles. **Prefer the standard `BearerTokenAuthenticationFilter`** over hand-rolling Bearer authentication to minimize boundary mistakes.

### 14.1. Do Not Throw AccessDeniedException Before Authentication Exists

If a pre-authentication custom filter throws `AccessDeniedException` for a missing token, the outcome depends on handlers, trust resolvers, and filter position. If outside `ExceptionTranslationFilter`'s catch scope, it may yield `500`. Better to let the Bearer resolver/filter and HTTP authorization handle standard semantics.

### 14.2. Clear Context When Authentication Fails

Standard Spring Security filters/providers manage SecurityContext per the framework's lifecycle. When customizing, never leave a stale authentication in thread-local storage for the next request. In thread-pooled servlet applications, context leakage bugs are especially dangerous.

Never construct `UsernamePasswordAuthenticationToken.authenticated(...)` or `JwtAuthenticationToken` from claims parsed out of an unverified JWT payload. Having `isAuthenticated=true` in a Java object **does not prove** JWT signature/issuer/audience passed trust policies.

---

## 15. Testing 401/403 and Bearer Challenges

A test suite asserting only `status().isUnauthorized()` or `status().isForbidden()` is not enough. Verify simultaneously:

1. The Spring filter chain actually runs.
2. HTTP status is appropriate.
3. The `WWW-Authenticate` header preserves Bearer semantics when needed.
4. Controllers/services **do not execute** for invalid tokens.
5. Valid tokens lacking permissions are not confused with invalid tokens.
6. No raw tokens/claims/secrets leak in responses.
7. Error handlers do not turn 401/403 into 200/302/500.

### 15.1. Testing Missing Token

Suppose `GET /api/orders/42` exists and the route requires `SCOPE_orders:read`:

```java
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;
import static org.hamcrest.Matchers.startsWith;

@Test
void missingBearerTokenGetsChallenge() throws Exception {
    mvc.perform(get("/api/orders/42"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            "WWW-Authenticate", startsWith("Bearer")));
}
```

Do not assert the header must contain `invalid_token` when **there is no token at all**, because RFC 6750 permits a challenge without an error code in that case.

### 15.2. Testing Valid Token Missing Scope

Using `spring-security-test`:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Test
void validAuthenticatedJwtWithoutReadScopeIsForbidden()
        throws Exception {
    mvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders:write"))))
        .andExpect(status().isForbidden());
}
```

`jwt()` is a request post-processor creating a mock authentication for testing **authorization**; it does not prove the JWT decoder verified signatures, `exp`, audience, or JWKS. To test real token failures, send Bearer JWTs signed with a test keypair through the filter chain with a matching decoder configured.

### 15.3. Testing `invalid_token` with Genuinely Signed Tokens

An integration test can generate a test RSA keypair and sign hypothetical JWTs with:

- Issuer `https://auth.example.test/realms/orders`.
- Audience `orders-api`.
- Valid or expired `exp`.
- Scope `orders:read`.
- Valid or tampered signature.

Configure the Resource Server to trust only the test public key/JWKS. Example test plan:

```text
given valid signed access token:
    GET /api/orders/42 → passes authentication, proceeds to authorization

given same JWT with modified payload and old signature:
    GET /api/orders/42 → 401; Bearer invalid_token

given expired but correctly signed JWT:
    GET /api/orders/42 → 401

given signed JWT for payments-api:
    GET /api/orders/42 → 401

given signed JWT for orders-api but without orders:read:
    GET /api/orders/42 → 403

given signed JWT with scope but order belongs to Bob:
    GET /api/orders/order-bob → 403/404 per policy
```

Never use production private signing keys in tests. Never put `.with(jwt())` in tests meant to verify the real decoder, because the mock bypasses the authentication step.

### 15.4. Testing Custom Entry Point and Denied Handler Responses

If implementing a decorator or JSON handler, tests must verify:

- Missing token → 401 and Bearer challenge.
- Invalid token → 401 and `invalid_token` when supplied by framework/exception.
- Malformed Bearer request → status per `invalid_request`, possibly 400.
- Valid token lacking scope → 403, appropriate challenge/error.
- Under-privileged OAuth2 principal → handler leaks no sensitive scopes/claims.
- Handler writes the response **only once**.
- Response does not turn into a 302 login redirect through the API chain.
- `GET /api/public/ping` is allowed if genuinely public, without unnecessary Bearer challenges.
- `/api/admin/**` is not shadowed by a broad `authenticated()` matcher overriding role/scope rules.
- Other security headers (if any) are not accidentally wiped when writing the JSON body.

### 15.5. Testing Boundaries: Filter vs. MVC

Create two separate tests:

**Test A — failure right at the authentication filter**

```text
Authorization: Bearer <invalid token>
    ↓
JwtDecoder fails
    ↓
BearerTokenAuthenticationFilter invokes entry point
    ↓
Assert: controller does not run, 401 + challenge
```

**Test B — downstream access denied**

```text
Authentication valid, authorities missing SCOPE_orders:read
    ↓
AuthorizationFilter denies
    ↓
ExceptionTranslationFilter invokes denied handler
    ↓
Assert: controller does not run, 403
```

You can add **Test C — denial in the service**:

```text
JWT valid, right scope
    ↓
Controller calls service
    ↓
Service/Method Security denies access to Bob's order
    ↓
Assert: 403/404 as designed by the application
        and Bob's data is not returned
```

If Test C returns 500, check controller advice/exception resolvers, filter chain, exception type, and whether the response was already committed. Never fix it by removing object authorization.

### 15.6. Testing with Opaque Tokens

If the API uses introspection, add scenarios:

| Introspection Outcome | Expectation |
|---|---|
| `{"active":false}` | No authentication; never enters controller. |
| `{"active":true,"scope":"orders:read"}` | Sufficient scope for read route if other API contracts pass. |
| `{"active":true,"scope":"orders:write"}` | Token active but lacks read → 403. |
| HTTP 401 from AS due to wrong introspection client credentials | Deny access; alert on integration error. |
| HTTP 503/timeout from AS | Deny access; clearly classify dependency error. |
| Response JSON missing `active` or wrong type | Do not treat token as active. |

Spring Security Test `opaqueToken()` can also mock authentication for route tests, yet it **does not perform real HTTP introspection**, so it cannot replace tests with a mock AS endpoint.

---

## 16. Diagnosing Common Failures

### 16.1. Bad JWT, Yet API Returns 500

Possibilities:

- Custom `JwtDecoder` throws an exception not handled as an authentication failure by the provider/filter.
- Custom filter throws before `ExceptionTranslationFilter`.
- `@ControllerAdvice` or ErrorController writes an incompatible response.
- Response was already committed and handler tried calling `sendError`.
- An actual coding bug occurred while parsing/converting claims.

Do not fix by writing `catch (Exception ex) { return 401; }`. Find the exact boundary and preserve the framework's exception contract.

### 16.2. Missing Scope, Yet API Returns 401

Possibilities:

- Token actually **did not authenticate**: wrong issuer/audience, expired, decoder error.
- Principal created by a custom converter has `isAuthenticated=false` or incompatible type.
- `ExceptionTranslationFilter` evaluates authentication as anonymous/insufficient.
- Custom handler converts every `AccessDeniedException` to 401.
- The active API chain is not the chain you think is running.

Check whether an authentication was created, which authorities are present, and which route rule matched. Never log raw tokens; log normalized reason codes/issuer IDs only if policy permits.

### 16.3. Bad Token, Yet API Returns 403

A custom authentication filter may have created an authenticated principal from unverified data, causing the authorization layer to run and then deny for missing scope. This signals a trust-boundary bug. A JWT without a verified signature must never become an authenticated user.

Another cause is a custom denied handler returning 403 for all missing-authentication errors. Run no-token and invalid-token tests against the standard entry point.

### 16.4. API Returns a 302 Redirect Instead of a Bearer Challenge

The app may be using a form-login entry point because:

- `formLogin()` is enabled on the same chain.
- Multiple chains/`securityMatcher` misconfigured.
- `exceptionHandling` was overridden.
- Request fell outside the `/api/**` chain.
- Browser Accept headers caused the framework to pick another entry point when multiple mechanisms exist.

For pure Bearer APIs, define an explicit chain for `/api/**` and test `WWW-Authenticate: Bearer`.

### 16.5. API Returns 403 Without `insufficient_scope`

This is not always a bug. `BearerTokenAccessDeniedHandler` may only add `insufficient_scope` when it confirms the caller holds a matching OAuth2 authentication. A 403 from CSRF, ACL, or a custom handler may produce a different response. Do not force every 403 to carry the same error code when the cause is not scope.

### 16.6. `@RestControllerAdvice` Does Not Run for Expired Tokens

This is normal if the token was rejected inside `BearerTokenAuthenticationFilter`, before MVC. Inspect the Resource Server's `AuthenticationEntryPoint`/`AuthenticationFailureHandler` rather than trying to catch it in controller advice.

### 16.7. Security Exceptions Escape the Chain When Adding Custom Filters

If a custom filter outside or before `ExceptionTranslationFilter` throws `AccessDeniedException`, ETF may not catch it. Do not simply swap exception types; examine filter position, ownership, and how HTTP responses are written. Delegate to the appropriate standard handler where the custom filter owns failures, or move the authorization decision into `AuthorizationManager`/method security.

### 16.8. Valid Token with Scope, Yet API Leaks Another Tenant's Data

This is an **object-level authorization** failure, not merely a 401/403 configuration bug. Scope alone does not determine record-level permissions. Services/repositories must filter by owner, tenant, delegated access, or ACL, and tests must cover cross-tenant/cross-user access.

---

## 17. Safety Principles When Crafting Error Responses

A useful error response never needs to expose credentials or token internals.

Should include:

- Appropriate HTTP status.
- `WWW-Authenticate: Bearer` per RFC 6750 when needed.
- Stable error code, e.g., `invalid_token` or `insufficient_scope`, in the header when contextually accurate.
- Correlation/request ID for operations.
- Short message revealing no other user's data.
- `Cache-Control: no-store` if the app has error responses containing sensitive info or per contract.
- Internal logs/metrics classifying errors.

Should exclude:

- Raw `Authorization: Bearer ...` or access tokens in the body.
- Full JWT payloads, refresh tokens, introspection client secrets.
- Exception stack traces sent to clients.
- Unfiltered upstream `error_description` containing PII or internal URLs.
- Details like “order belongs to Bob in tenant B” when Alice is not allowed to know.
- Internal admin scope names that do not need public exposure.

### 17.1. Should You Use RFC 7807 / RFC 9457 Problem Details?

APIs can use `application/problem+json` for consistent business errors. Example:

```json
{
  "type": "https://api.example.test/problems/access-denied",
  "title": "Forbidden",
  "status": 403,
  "detail": "You do not have permission to perform this action",
  "instance": "/api/orders/42"
}
```

This is a **response body format**, not a replacement for `WWW-Authenticate` when a Bearer challenge is required. A neat JSON body with the wrong status or missing standard headers can still break OAuth clients.

Also take care not to echo raw URLs/paths containing private information in `instance`. Never produce differing content that reveals the existence of hidden objects.

### 17.2. Do Not Turn Every Denial into `insufficient_scope`

Classify:

```text
AUTHN_NO_TOKEN
AUTHN_INVALID_TOKEN
AUTHN_MALFORMED_BEARER_REQUEST
AUTHZ_INSUFFICIENT_SCOPE
AUTHZ_OBJECT_NOT_ALLOWED
AUTHZ_TENANT_DENIED
AUTHZ_CSRF_DENIED
DEPENDENCY_JWKS_UNAVAILABLE
DEPENDENCY_INTROSPECTION_UNAVAILABLE
```

These are **reason codes for internal logs/metrics**, not all meant to be sent to clients. Multiple authn or dependency errors may equally result in a denied request yet follow different operational runbooks.

---

## 18. Monitoring and Auditing Error Boundaries

A common operational incident is a spike in 401s after a JWKS rotation, or 403s after the Authorization Server changes scope claims. Watching a single “HTTP errors” graph is not enough to find the root cause.

Useful metrics:

| Metric | Goal |
|---|---|
| `http_server_requests_seconds{status=401}` | Rate/latency of unauthenticated requests. |
| `http_server_requests_seconds{status=403}` | Rate/latency of permission-denied requests. |
| `bearer_authentication_failure_total{reason=...}` | Classifies no-token, invalid token, malformed bearer, audience, expiry. |
| `bearer_access_denied_total{reason=...}` | Scope/role, object ACL, tenant, CSRF. |
| `jwks_fetch_error_total` | JWKS dependency failures that can cause authn failures. |
| `introspection_error_total{class=...}` | Separates inactive tokens from introspection client timeouts/401s. |
| `authorization_decision_total{result=...}` | Tracks permit/deny decisions on measurable policies. |

Keep label cardinality bounded: never put raw `sub`, tokens, `jti`, attacker-controlled scope values, or individual order resource IDs into metric labels. For sensitive audit trails, follow PII retention and log-access control policies.

A minimal runbook when `401`/`403` spikes:

1. Identify API route, region/pod/version, and onset timestamp.
2. Inspect response status alongside `WWW-Authenticate`.
3. Distinguish no-token, expired/invalid token, wrong issuer/audience, and insufficient authority.
4. Check JWKS/introspection endpoints, rotation caches, and HTTP timeouts if 401/5xx involves dependencies.
5. Check `scope`/`scp` mappers and matcher ordering if 403 spikes after a deploy.
6. Check owner/tenant business policies if only certain objects are denied.
7. Check custom entry points, denied handlers, and ControllerAdvice if statuses/headers are wrong.
8. Reproduce via tests without printing raw production tokens.
9. Recover via verified configuration/rollout; never disable authentication/authorization as a shortcut.
10. Add negative tests to prevent regressions.

---

## 19. A Decision Matrix for Bearer APIs

| Origin Point | Exception / Scenario | Who Typically Handles It? | Typical HTTP Outcome |
|---|---|---|---|
| `BearerTokenResolver` | Malformed Bearer header, invalid token method | `BearerTokenAuthenticationFilter` + failure handler/entry point | RFC 6750 `invalid_request`, possibly 400. |
| `JwtAuthenticationProvider` | Invalid JWT signature/exp/issuer/audience | Authentication filter + entry point | 401, `invalid_token`. |
| `OpaqueTokenAuthenticationProvider` | `active=false` | Authentication filter + entry point | 401, `invalid_token` or appropriate challenge. |
| No token sent | Filter finds no credential; protection rule denies | `ExceptionTranslationFilter` + entry point | 401, Bearer challenge. |
| `AuthorizationFilter` | Authenticated JWT missing `SCOPE_orders:read` | `ExceptionTranslationFilter` + denied handler | 403, possibly `insufficient_scope`. |
| Method security | `@PreAuthorize` denies | If exception crosses HTTP filter chain: ETF/handler; if MVC catches first: MVC handler | Usually 403, depends on boundary. |
| Service owner check | Not permitted to read order | Designed domain policy + error mapping | 403 or 404. |
| CSRF filter | Missing/bad CSRF token (cookie/session apps) | Security access denied handling at that point | Usually 403, not necessarily insufficient_scope. |
| AS/JWKS timeout | Dependency unresponsive | Decoder/introspector/provider or custom error boundary | Fail closed; status depends on design/exception mapping. |
| Controller/service bug | `NullPointerException`, DB error | Appropriate MVC/Boot error handling | Usually 5xx, never turned into 401/403. |
| Response already committed | Exception occurs after writing data | Handler may be unable to alter response | Design/ops bug; check permissions before writing. |

**Note:** this table illustrates common paths, not an immutable contract for every version/configuration. Especially with custom filters or exception resolvers, verify actual responses via integration tests.

---

## 20. An End-to-End Example of Three Requests

### Request A — No Token

```http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
```

Decision chain:

```text
BearerTokenAuthenticationFilter: no Bearer token
  → request continues
AuthorizationFilter: requires SCOPE_orders:read but unauthenticated
  → AccessDeniedException
ExceptionTranslationFilter: anonymous/unauthenticated
  → BearerTokenAuthenticationEntryPoint
Response: usually 401 + WWW-Authenticate: Bearer
```

### Request B — Valid Token, Missing Scope

```http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <valid-jwt-with-orders-write-only>
```

Decision chain:

```text
BearerTokenAuthenticationFilter
  → JwtDecoder verifies token successfully
  → Authentication has SCOPE_orders:write
AuthorizationFilter requires SCOPE_orders:read
  → AccessDeniedException
ExceptionTranslationFilter sees caller is authenticated
  → BearerTokenAccessDeniedHandler
Response: usually 403; possibly error="insufficient_scope"
```

### Request C — Valid Token, Sufficient Scope, Wrong Owner

```http
GET /api/orders/order-bob-200 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <valid-jwt-for-alice-with-orders-read>
```

Decision chain:

```text
JwtDecoder: signature, issuer, audience, exp valid
AuthorizationFilter: SCOPE_orders:read present
Controller/Service: loads order-bob-200
Domain policy: order.owner != alice
  → deny
Response: 403 or 404 per API policy
Bob's data is not returned.
```

The three requests illustrate:

```mermaid
flowchart TD
    A["Bearer request"] --> B{"Token validated?"}
    B -->|No| C["AuthenticationEntryPoint → 401"]
    B -->|Yes| D{"Sufficient scope/authority?"}
    D -->|No| E["AccessDeniedHandler → 403"]
    D -->|Yes| F{"Permitted to access object?"}
    F -->|No| G["Domain denial → 403/404"]
    F -->|Yes| H["Execute business logic"]
```

This is a **logical policy diagram**; in the actual filter chain, a no-token denial may start as an `AccessDeniedException` and be routed by `ExceptionTranslationFilter` to the entry point, as Request A explained.

---

## 21. Pitfalls to Avoid

| Pitfall | Why It Is Wrong | Right Approach |
|---|---|---|
| “`AuthenticationException` is always caught by `ExceptionTranslationFilter`.” | Bearer authentication filter has its own failure handler outside ETF's downstream catch. | Understand where each exception arises and who owns its handler. |
| “`AccessDeniedException` always produces 403.” | Anonymous callers can be routed to the authentication entry point and receive 401. | Check `AuthenticationTrustResolver` and context. |
| “Every 401 must contain `invalid_token`.” | Requests without credentials may receive `WWW-Authenticate: Bearer` with no error. | Follow RFC 6750. |
| “Every 403 is a missing scope.” | Could be ACL, tenant, object policy, or CSRF. | Do not attach `insufficient_scope` unconditionally to every denial. |
| “`@ControllerAdvice` is a global handler for all Spring Security filters.” | Filters before DispatcherServlet are not automatically caught by MVC advice. | Use entry points/denied handlers at the right boundary. |
| “One valid token grants access to every order.” | Scope does not prove ownership. | Enforce object-level authorization. |
| “Let bad-signature tokens create a principal and let the route deny later.” | Creates untrusted contexts and breaks HTTP semantics. | Reject invalid tokens at authentication. |
| “You can write a JSON body after any `sendError`.” | Response may already be committed or owned by the container. | Test handler/commit lifecycle; keep standard challenges. |
| “Handling errors with a 302 login redirect works fine for APIs.” | Bearer clients expect status/challenges, not HTML login pages. | Separate API chains from browser form-login chains. |
| “Using `try/catch Exception` and returning 401 is safe.” | Masks bugs, network failures, scope errors, and object denials. | Classify exceptions by responsibility. |
| “`jwt()` tests prove expired tokens are rejected.” | `jwt()` mocks authentication and skips the decoder. | Use separate signed-JWT integration tests. |
| “Changing `hasAuthority` to `authenticated()` fixes 403.” | Unintentionally widens route privileges. | Fix grants, mappings, or policies without lowering security. |
| “`CsrfException` is caused by missing Bearer scope.” | CSRF is a semantically distinct access-denied category. | Set CSRF policy matching your cookie/token model. |
| “Custom filters anywhere are protected by ETF.” | ETF only wraps the chain downstream of it. | Order filters properly or handle failures explicitly in place. |

---

## 22. References

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): `WWW-Authenticate`, `invalid_request`, `invalid_token`, `insufficient_scope`, and HTTP statuses.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): authentication/authorization contexts and OAuth scopes.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): token type, issuer/audience constraints when using JWT access tokens.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): inactive tokens and opaque token metadata.
- [Spring Security — ExceptionTranslationFilter API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/access/ExceptionTranslationFilter.html): coordinating entry point/denied handler dispatch.
- [Spring Security — BearerTokenAuthenticationFilter API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/authentication/BearerTokenAuthenticationFilter.html): authentication filter and failure handling.
- [Spring Security — BearerTokenAuthenticationEntryPoint API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html): Bearer challenges.
- [Spring Security — BearerTokenAccessDeniedHandler API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/access/BearerTokenAccessDeniedHandler.html): handling access denial for Bearer tokens.
- [Spring Security — Handling Security Exceptions](https://docs.spring.io/spring-security/reference/servlet/architecture.html): filter chain, exception translation, and architecture.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): authorization rules and filter behavior.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, authorities, and request authorization.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, least privilege, object-level checks.

**Conclusion:** `AuthenticationException` and `AccessDeniedException` represent **two distinct decision layers**, yet the final HTTP response also depends on **where the exception is thrown, who catches it, and whether the caller is already authenticated**. In Spring Security Resource Server, let the Bearer authentication filter and `ExceptionTranslationFilter` work with the right `AuthenticationEntryPoint`/`AccessDeniedHandler`, preserve RFC 6750 challenges, and continue enforcing scope/ownership checks even after a token validates successfully.
