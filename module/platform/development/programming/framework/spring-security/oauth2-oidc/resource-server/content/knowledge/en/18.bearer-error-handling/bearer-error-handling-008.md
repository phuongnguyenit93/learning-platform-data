# Coordinating JSON Error Payloads with Semantically Accurate Headers and Status Codes

## 1. Goal: A Bearer Response Must Be Consistent from HTTP to JSON

In **Spring Security OAuth 2.0 / OIDC Resource Server**, clients usually send an OAuth 2.0 access token as a Bearer credential:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
~~~

When a request is rejected, the API has at least **three layers of information** to coordinate:

1. **HTTP status code:** the HTTP outcome, such as `400`, `401`, `403`, `429`, or `503`.
2. **`WWW-Authenticate` response header:** the Bearer challenge and OAuth error parameters under **RFC 6750** when the situation involves Bearer token authentication/authorization.
3. **JSON response body:** helps frontends, SDKs, and operators understand the error, typically as custom JSON or **RFC 9457 Problem Details**.

Example of a JWT with a bad signature or expired lifetime:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required or the access token is invalid.",
  "code": "invalid_token"
}
~~~

The example shows all three elements indicating an authentication failure. If an API instead returns:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status": 401, "error": "invalid_token"}
~~~

then the JSON claims an error while the HTTP status is still **success**; browsers, SDKs, monitoring, and proxies can misbehave. Never use `200 OK` for an authentication error just to standardize a body schema.

**Scope:** Spring MVC/Servlet Resource Server accepting JWT or opaque access tokens, using `AuthenticationEntryPoint` and `AccessDeniedHandler` to produce security responses. OIDC login/sessions have their own response contract and should not be conflated automatically.

## 2. RFC 6750: Right Error Requires the Right HTTP Status

### 2.1. Three Core Bearer Error Codes

Under **RFC 6750, Section 3.1**, the three core Bearer error codes are:

| Bearer `error` | When? | Typical HTTP Status | Client Action |
|---|---|---|---|
| `invalid_request` | Malformed Bearer token/request submission, duplicate parameters, or using multiple token transport methods simultaneously | **400 Bad Request** | Fix the request |
| `invalid_token` | Token expired, revoked, malformed, or failed authentication | **401 Unauthorized** | Obtain a valid new token or re-authenticate |
| `insufficient_scope` | Token valid but lacking required permission scope | **403 Forbidden** | Request privileges/scopes properly; do not retry infinitely with the same token |

These statuses are `SHOULD` recommendations in RFC 6750 and must be read in context. Never turn every `AccessDeniedException` or every system error into `invalid_token`.

### 2.2. Request Missing a Token

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
~~~

Representative response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required.",
  "code": "authentication_required"
}
~~~

**Important note:** `authentication_required` in the body is an **application-defined error code**, not a Bearer `error` registered in RFC 6750.

When a request contains no authentication information at all, RFC 6750 recommends the Resource Server **not add `error` or extra error details to the challenge**. Therefore, do not blindly return:

~~~http
WWW-Authenticate: Bearer error="invalid_token"
~~~

merely because the token is missing.

### 2.3. Invalid or Expired Token

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <INVALID_OR_EXPIRED_ACCESS_TOKEN>
~~~

Response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "The access token could not be accepted.",
  "code": "invalid_token"
}
~~~

Causes that can lead to a JWT Resource Server authentication failure:

- Invalid JWS signature or disallowed `alg` algorithm.
- Token past `exp` or before `nbf`.
- `iss` does not match a trusted issuer.
- `aud` is not intended for this API.
- Token fails profile/claim validators.
- JWKS has no trusted key to verify the token.

With opaque-token introspection, a token where the AS returns `active:false` is also normally rejected. **Not every network outage while fetching JWKS/introspection means the token is invalid**; distinguish infrastructure failures when mapping responses.

Public descriptions should stay generic, avoiding raw exception messages, tokens, issuer allowlists, key info, or internal data.

### 2.4. Malformed Bearer Request Structure

For example, a client sends tokens in both header and query when the resolver/contract forbids it:

~~~http
GET /api/orders?access_token=abc HTTP/1.1
Authorization: Bearer def
~~~

Reasonable response:

~~~http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer realm="orders-api", error="invalid_request"
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "The Bearer authentication request is malformed.",
  "code": "invalid_request"
}
~~~

Distinguish **malformed Bearer token/request presentation** (`invalid_request`, 400) from **a submitted token that is invalid** (`invalid_token`, 401). Spring Security classifies these based on `BearerTokenResolver` and authentication exceptions.

### 2.5. Valid Token Lacking Scope

Suppose the Orders API requires:

~~~java
.hasAuthority("SCOPE_orders.write")
~~~

but the token was only issued `scope=orders.read`.

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.write"
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "The access token has insufficient privileges.",
  "code": "insufficient_scope"
}
~~~

The `scope="orders.write"` parameter is **optional** per RFC 6750. Only emit the required scope if the server genuinely knows it and policy allows disclosing it.

`401` differs from `403`: with 401, authentication is missing or failed; with 403, the principal is authenticated but not permitted to perform the operation. Frontends should not repeatedly refresh tokens on a 403.

### 2.6. No Permission for a Specific Resource

Caller has `SCOPE_orders.read` yet order 42 belongs to another tenant:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "Access to this order is not permitted.",
  "code": "resource_access_denied"
}
~~~

An API may also choose `404 Not Found` to conceal the existence of the resource when required by policy. **Do not turn every ACL/owner/tenant failure into `insufficient_scope`**, because requesting another OAuth scope will not necessarily solve the problem.

## 3. Response Selection Table by Semantics

| Situation | Status | Bearer Header | Example JSON Code |
|---|---|---|---|
| Missing Bearer on protected endpoint | 401 | Bearer challenge, usually no `error` | `authentication_required` |
| Expired/bad-signature/wrong-issuer JWT | 401 | `invalid_token` on matching branch | `invalid_token` |
| Inactive opaque token | 401 | `invalid_token` on matching branch | `invalid_token` |
| Malformed Bearer header/request | 400 | `invalid_request` | `invalid_request` |
| Valid token missing OAuth scope | 403 | `insufficient_scope` when appropriate | `insufficient_scope` |
| Valid token missing local role/ACL | 403 | Per policy; do not fake missing scope | `resource_access_denied` |
| Resource not found or not disclosed | 404 | Not a Bearer error | `resource_not_found` |
| Business request body fails schema | 400/422 per policy | Not a Bearer error | `invalid_body` |
| Unsupported HTTP method | 405 | Not a Bearer error; includes `Allow` | `method_not_allowed` |
| Quota/rate limited | 429 | Not `invalid_token`; may include `Retry-After` | `rate_limited` |
| JWKS/introspection service outage | 5xx or appropriate infra handling | Do not fake a Bearer error | `dependency_unavailable` |
| Unexpected server error | 500 | Not a Bearer error | `internal_error` |

**Not every 400 is a Bearer `invalid_request`**. JSON body validation failures can also return 400 without involving `WWW-Authenticate`.

In particular, an AS returning HTTP 401 **during an introspection call** may mean the Resource Server's client credentials are wrong; it does not mean the caller's bearer token was revoked.

## 4. 400/401/403 Decision Diagram

~~~mermaid
flowchart TD
    A["Request to protected API"] --> B{"Valid Bearer request structure?"}
    B -->|No| C["400 invalid_request"]
    B -->|Yes| D{"Bearer token present?"}
    D -->|No| E["401 Bearer challenge, no error"]
    D -->|Yes| F{"Token authentication succeeded?"}
    F -->|No| G["401 invalid_token when appropriate"]
    F -->|Yes| H{"Sufficient action scope?"}
    H -->|No| I["403 insufficient_scope"]
    H -->|Yes| J{"Tenant/owner/ACL allows?"}
    J -->|No| K["403 or 404 per resource policy"]
    J -->|Yes| L["Controller executes business logic"]
    L --> M{"Business error?"}
    M -->|Yes| N["Semantically accurate 4xx/5xx, do not fake Bearer"]
    M -->|No| O["Success response"]
~~~

The diagram depicts the main paths and does not cover all exceptions, CORS, rate limits, or multiple authentication schemes. Key point: **the status line must be right** before designing JSON.

## 5. `WWW-Authenticate`: Staying Compliant with RFC 6750

### 5.1. Request `Authorization` Differs from Response `WWW-Authenticate`

Client sends:

~~~http
Authorization: Bearer <token>
~~~

Server challenges:

~~~http
WWW-Authenticate: Bearer realm="orders-api"
~~~

A Bearer challenge may contain:

| Parameter | Role |
|---|---|
| `realm` | Resource protection space name |
| `error` | `invalid_request`, `invalid_token`, or `insufficient_scope` |
| `error_description` | Syntactically valid and safe error description |
| `error_uri` | URI explaining the error |
| `scope` | Additional scope needed when privileges are insufficient, if appropriate |

Not every response needs every parameter. Never put raw tokens, refresh tokens, client secrets, or stack traces into headers.

### 5.2. Do Not Concatenate Uncontrolled Values

An error-prone approach:

~~~java
response.setHeader(
    "WWW-Authenticate",
    "Bearer error_description=\"" + exception.getMessage() + "\""
);
~~~

Exception messages can contain control characters, key/issuer details, or sensitive data. Manual string concatenation can also violate challenge quoting/escaping rules.

Prefer **`BearerTokenAuthenticationEntryPoint`** and **`BearerTokenAccessDeniedHandler`** provided by Spring Security. They are responsible for building Bearer headers and statuses from OAuth2 errors/framework rules.

### 5.3. Distinguish `error_description` from JSON `detail`

The two fields do not have to be identical. `error_description` is a parameter on an HTTP authentication challenge, with character and length constraints to respect. JSON `detail` is human-oriented and can use a generic sentence.

A security policy:

~~~text
Header:
  error="invalid_token"

Body:
  detail="The access token could not be accepted."

Internal logs:
  jwt_expired / issuer_mismatch / aud_missing
  correlationId=req-729e
~~~

The client receives the information it needs, while the server keeps diagnostic details inside access-restricted logs. Never drive security logic from the wording of `detail`.

### 5.4. Do Not Lose Other Authentication Challenges

HTTP can support multiple authentication schemes across the same system. A web app may have OIDC login/sessions, an API has a Bearer Resource Server, or Basic authentication exists elsewhere. Never use a single handler that overwrites every response with `Bearer` without knowing which security chain the client hit.

When separating UI and API:

~~~text
/api/**   -> Bearer + 401/403 + JSON
/web/**   -> Browser OIDC login + redirect/page
~~~

Use `securityMatcher` and intentional `SecurityFilterChain` ordering so a browser chain never intercepts API calls and returns a 302 HTML login redirect.

## 6. RFC 9457 Problem Details as the JSON Response Body

### 6.1. Standard Fields

**RFC 9457** defines **Problem Details** with media type:

~~~http
Content-Type: application/problem+json
~~~

A body:

~~~json
{
  "type": "https://api.example.test/problems/access-denied",
  "title": "Forbidden",
  "status": 403,
  "detail": "You do not have permission to perform this action.",
  "instance": "/api/orders/42",
  "code": "resource_access_denied",
  "traceId": "req-729e"
}
~~~

Where:

- `type` identifies the problem type, e.g., a public documented URI; if omitted, defaults to `about:blank`.
- `title` is a short, stable summary of the error type.
- `status` is the HTTP status of the response when generated.
- `detail` describes this occurrence without sensitive details.
- `instance` identifies the occurrence if helpful, avoiding paths containing PII.
- `code` and `traceId` are **API-defined extensions**, not mandatory RFC 9457 fields.

### 6.2. The Actual HTTP Status Is the Source of Truth

Per RFC 9457, if the body contains `status`, the server must set the exact same status on the HTTP response:

~~~text
HTTP status = body.status
~~~

Wrong:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json

{"status":403,"title":"Forbidden"}
~~~

Even worse:

~~~http
HTTP/1.1 200 OK
Content-Type: application/problem+json

{"status":401,"code":"invalid_token"}
~~~

Set the status once according to the security outcome, then build the body from that status. If an API gateway alters the status while keeping the JSON untouched, fix proxy handling rather than forcing clients to pick arbitrarily.

### 6.3. Must JSON `code` Equal Bearer `error`?

No. They belong to two contract layers:

- `WWW-Authenticate` carries the standard **OAuth Bearer error** per RFC 6750.
- JSON `code` can be an **application code**, such as `authentication_required`, `invalid_token`, `forbidden`, `resource_access_denied`.

A body `code="forbidden"` is a general category while the header `error="insufficient_scope"` gives Bearer-specific detail. That is acceptable if the client contract documents it clearly. If you want `insufficient_scope` in both places, classify from the **actual missing-scope policy source** rather than guessing by parsing exception messages.

### 6.4. Problem Details Is Not Mandatory

An API with an existing error envelope:

~~~json
{
  "error": {
    "code": "invalid_token",
    "message": "Authentication failed",
    "requestId": "req-729e"
  }
}
~~~

can still use `application/json`. It still needs the right HTTP status and Bearer header. Never use `application/problem+json` for JSON that does not conform to the Problem Details schema.

## 7. Security Filter Path Differs from Spring MVC Controllers

Spring Security handles Bearer authentication in the **Servlet filter chain**, before the controller:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Spring SecurityFilterChain"]
    B --> C["BearerTokenAuthenticationFilter"]
    C --> D["AuthenticationEntryPoint when token invalid"]
    B --> E["ExceptionTranslationFilter / AuthorizationFilter"]
    E --> F["AccessDeniedHandler when missing permissions"]
    B --> G["DispatcherServlet"]
    G --> H["Controller / Service"]
    H --> I["@RestControllerAdvice for MVC exceptions"]
~~~

Therefore, writing only:

~~~java
@RestControllerAdvice
public class GlobalErrors {
    @ExceptionHandler(Exception.class)
    public ProblemDetail error(Exception ex) {
        // ...
    }
}
~~~

is **not enough** to catch all authentication failures inside the Bearer filter. `@RestControllerAdvice` normally handles exceptions routed by MVC to exception resolvers; the filter may have already sent 401/403 before entering MVC.

Worse, if generic advice catches all security exceptions and returns 200/500, it breaks the semantics the Resource Server intends to enforce.

### 7.1. `AuthenticationEntryPoint`

Interface `org.springframework.security.web.AuthenticationEntryPoint` handles responses when authentication needs to be initiated/challenged. Resource Server provides:

~~~java
org.springframework.security.oauth2.server.resource.web
    .BearerTokenAuthenticationEntryPoint
~~~

This implementation relies on `BearerTokenError` to set HTTP status and `WWW-Authenticate`.

### 7.2. `AccessDeniedHandler`

Interface `org.springframework.security.web.access.AccessDeniedHandler` is used when access is denied.

Resource Server provides:

~~~java
org.springframework.security.oauth2.server.resource.web.access
    .BearerTokenAccessDeniedHandler
~~~

This handler crafts an RFC 6750 response based on authentication/security context state. However, not every `AccessDeniedException` in the domain layer is necessarily a missing OAuth scope.

### 7.3. Why Configure in Two Places?

`BearerTokenAuthenticationFilter` may invoke the entry point directly on authentication failures. Some authorization failures are handled by `ExceptionTranslationFilter`. When standardizing JSON, pay attention to both **Resource Server configuration** and **`exceptionHandling(...)`** so one path does not return JSON while another returns headers only.

In Spring Security, exact call paths can vary by version, filter chain, and authentication mechanism. Test on your actual version to verify which handler runs.

## 8. Basic Spring Boot Resource Server Configuration

Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Illustrative `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          audiences:
            - orders-api
~~~

Issuer/audience are examples and must match the Authorization Server contract. To authenticate, JWTs must pass signature, issuer, audience, time, and profile validation.

A simple chain:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Spring Security already provides Bearer error/challenge defaults. **Do not hand-craft challenge strings before verifying whether the defaults satisfy your contract.** Adding JSON is a representation requirement, not a reason to alter authentication logic.

## 9. Java Example: Wrapping Bearer Handlers to Add Problem JSON

Example targets **Spring Boot 3.x / Spring Security 6.x** with Servlet `jakarta.servlet.*` and Jackson `com.fasterxml.jackson.databind.ObjectMapper`. If using Spring Boot 4.x or Jackson 3, verify the actual JSON mapper package.

Design:

1. Let `BearerTokenAuthenticationEntryPoint` set status/challenge for authentication errors.
2. Let `BearerTokenAccessDeniedHandler` set status/challenge for access denied.
3. Append JSON only if the response is not yet committed.
4. Never overwrite `WWW-Authenticate`, call `sendError`, or reflect sensitive exception messages.

### 9.1. Handler Implementing Both Interfaces

~~~java
package com.example.orders.security;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.access.AccessDeniedHandler;

public final class BearerProblemHandlers
        implements AuthenticationEntryPoint, AccessDeniedHandler {

    private final ObjectMapper mapper;

    private final BearerTokenAuthenticationEntryPoint entryPoint =
        new BearerTokenAuthenticationEntryPoint();

    private final BearerTokenAccessDeniedHandler deniedHandler =
        new BearerTokenAccessDeniedHandler();

    public BearerProblemHandlers(ObjectMapper mapper) {
        this.mapper = mapper;

        entryPoint.setRealmName("orders-api");
        deniedHandler.setRealmName("orders-api");
    }

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException, ServletException {

        // Let Spring Security determine the status and Bearer challenge.
        entryPoint.commence(request, response, exception);

        String code = "authentication_required";
        String detail = "Authentication is required.";

        if (exception instanceof OAuth2AuthenticationException oauth) {
            code = oauth.getError().getErrorCode();
            detail = "Authentication failed or the Bearer request is invalid.";
        }

        writeProblem(response, code, detail);
    }

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            AccessDeniedException exception)
            throws IOException, ServletException {

        deniedHandler.handle(request, response, exception);

        // Generic app code: do not assume every denial is a missing scope.
        writeProblem(
            response,
            "forbidden",
            "You do not have permission to perform this action."
        );
    }

    private void writeProblem(
            HttpServletResponse response,
            String code,
            String detail) throws IOException {

        if (response.isCommitted()) {
            return;
        }

        int status = response.getStatus();

        // Preserve status/challenge just set by the delegate.
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType("application/problem+json");
        response.setHeader("Cache-Control", "no-store");
        response.setHeader("Pragma", "no-cache");

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("type", "about:blank");
        body.put(
            "title",
            HttpStatus.valueOf(status).getReasonPhrase()
        );
        body.put("status", status);
        body.put("detail", detail);
        body.put("code", code);

        mapper.writeValue(response.getOutputStream(), body);
    }
}
~~~

**Key design decisions:**

- **Missing token:** `AuthenticationException` is not necessarily an `OAuth2AuthenticationException`; the body can carry app code `authentication_required`, while the Bearer challenge omits `error` if the framework sees missing credentials.
- **Invalid token/request:** if Spring Security supplies an `OAuth2AuthenticationException` and standard error code, the body uses that code. Status is still set by the delegate, which may be 401 or 400 depending on `BearerTokenError`.
- **Access denied:** body uses app code `forbidden`; the header is managed by `BearerTokenAccessDeniedHandler`. In a chain primarily protecting OAuth scopes, the handler may emit `insufficient_scope`. If domain-level 403 classification is needed, design explicit policies and handlers rather than guessing from exception messages.
- **`response.isCommitted()`:** prevents writing a second time; if the response committed too early, investigate which filter/handler wrote earlier.
- **`setStatus` instead of `sendError`:** the delegate already sets the status, and the JSON writer avoids calling `sendError` so the servlet container does not replace the body with an error page.
- **No raw internal errors exposed:** never add stack traces, decoder causes, token strings, issuer lists, or client secrets to the body.

This snippet does not implement full Content Negotiation on `Accept`; the API fixes its error representation to `application/problem+json`. If some clients only accept another format, design deliberate content negotiation without losing status/challenges.

### 9.2. Registering the Handler in the API Chain

~~~java
package com.example.orders.security;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    BearerProblemHandlers bearerProblems(ObjectMapper mapper) {
        return new BearerProblemHandlers(mapper);
    }

    @Bean
    SecurityFilterChain apiChain(
            HttpSecurity http,
            BearerProblemHandlers problems)
            throws Exception {

        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationEntryPoint(problems)
                .accessDeniedHandler(problems)
                .jwt(Customizer.withDefaults())
            )
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(problems)
                .accessDeniedHandler(problems)
            );

        return http.build();
    }
}
~~~

Configuring the same handler in both **`oauth2ResourceServer(...)`** and **`exceptionHandling(...)`** ensures both security processing paths get to write Problem JSON. In an app with multiple auth schemes, never apply this single Bearer handler across every security chain.

If `oauth2Login`/form login is mixed into the API chain, challenges/redirects can collide. Separate `/api/**` and `/web/**` with clear chains and test matching order.

### 9.3. Why Not Write `WWW-Authenticate` from Scratch?

Hand-crafting:

~~~java
response.setHeader(
    "WWW-Authenticate",
    "Bearer realm=\"orders-api\", error=\"invalid_token\""
);
~~~

easily misses:

- Missing-token challenges should omit `invalid_token`.
- `invalid_request` may use status 400 rather than 401.
- `insufficient_scope` is usually 403 and `scope` may be optional.
- Encoding/escaping of `error_description`.
- Other authentication schemes/challenges.
- Version-specific changes/framework extensions.

Using the built-in delegate reduces the risk of breaking the protocol when your goal is simply adding a JSON body.

## 10. Domain Authorization: 403 Is Not Always a Missing OAuth Scope

### 10.1. Scope-Based Denial

A method:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public OrderDto load(long id) {
    return repository.findOrderDto(id);
}
~~~

If a valid principal lacks the scope, returning 403 is appropriate. `insufficient_scope` accurately describes the cause per RFC 6750.

### 10.2. Owner/Tenant Denial

A service might check:

~~~java
if (!order.getTenantId().equals(caller.tenantId())) {
    throw new AccessDeniedException("Tenant access denied");
}
~~~

This error is not necessarily fixed by requesting a new OAuth scope. If all `AccessDeniedException` instances share one Bearer `insufficient_scope` handler, clients may be misled.

Options include:

- Creating a **policy-specific exception/result** mapped to `resource_access_denied`.
- Using a clearly structured service/controller authorization manager.
- Returning 403 or 404 per data contract without fabricating a wrong required scope.
- Keeping the default Bearer handler for URL/method scopes while giving object policies their own documented path.

Do not parse exception messages like `"Access denied"` to guess the error source. Application error codes should come from **structured policy/exception types**.

### 10.3. `@PreAuthorize` and Spring MVC Exception Handling

`AccessDeniedException` from method security can pass through different components depending on proxy/MVC/`ExceptionTranslationFilter`. If `@RestControllerAdvice(Exception.class)` catches everything and returns `500` or `200`, it can mask security denials.

Design exception handling so security exceptions are never swallowed or mis-mapped. Also remember `@PreAuthorize` in proxy mode only runs when invoked through the AOP proxy; self-invocation must not be the sole guard for sensitive actions.

## 11. `@RestControllerAdvice` Is Still Needed for MVC Errors

Request body validation errors do not belong to Bearer authentication:

~~~java
@PostMapping("/api/orders")
public OrderDto create(
        @Valid @RequestBody CreateOrderRequest request) {
    return service.create(request);
}
~~~

Can be handled using Spring Framework's `ProblemDetail`:

~~~java
package com.example.orders.api;

import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiValidationAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ProblemDetail invalidBody(
            MethodArgumentNotValidException exception) {

        ProblemDetail problem =
            ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);

        problem.setType(
            URI.create("https://api.example.test/problems/invalid-body")
        );
        problem.setTitle("Bad Request");
        problem.setDetail("The request body is invalid.");
        problem.setProperty("code", "invalid_body");

        return problem;
    }
}
~~~

Although both Bearer `invalid_request` and JSON body `invalid_body` may use HTTP 400, they operate at **different error layers**:

- Malformed Bearer request: RFC 6750 `invalid_request` header.
- Invalid MVC request body schema: Problem Details `invalid_body`, no Bearer error added.

`ProblemDetail` supports RFC 9457 in Spring MVC, yet **does not by itself solve security filter failures**. Maintain a unified response contract across the right extension points.

## 12. Do Not Turn Business/Infrastructure Errors into Bearer Errors

An API must preserve semantics:

### 12.1. Validation Errors

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/invalid-body",
  "title": "Bad Request",
  "status": 400,
  "code": "invalid_body"
}
~~~

Never attach `WWW-Authenticate: Bearer error="invalid_token"` when the token is valid.

### 12.2. Unsupported Method

~~~http
HTTP/1.1 405 Method Not Allowed
Allow: GET, PUT
Content-Type: application/problem+json
~~~

`Allow` is the proper header for 405. Never change the status to 401 just because the endpoint sits under `/api/**`.

### 12.3. Rate Limiting

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: application/problem+json
~~~

This is not `invalid_token`. Clients should back off per policy, not continuously refresh tokens.

### 12.4. JWKS or Opaque Introspection Outage

If the Resource Server cannot verify a token because the JWKS endpoint/introspection is unavailable, **do not fail open**. Yet do not pretend the token is invalid either. Depending on exception mapping, the API can return an appropriate infrastructure error; metrics must distinguish:

~~~text
invalid_token
jwks_unavailable
introspection_timeout
introspection_client_auth_failed
authorization_denied
business_validation_failed
~~~

These values are examples of internal monitoring codes, **not all RFC 6750 Bearer error codes**.

## 13. CORS: Can the Frontend Read the Bearer Challenge?

If a frontend at `https://app.example.test` calls an API at `https://api.example.test`, a request containing an `Authorization` header can trigger a **CORS preflight**.

Even if the response includes:

~~~http
WWW-Authenticate: Bearer error="invalid_token"
~~~

browser JavaScript may be unable to read that header unless the API exposes:

~~~http
Access-Control-Expose-Headers: WWW-Authenticate
~~~

Configure CORS so security does not block valid preflights.

### 13.1. Example CORS Configuration

~~~java
package com.example.orders.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiCorsConfig {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        cors.setAllowedOrigins(
            List.of("https://app.example.test")
        );
        cors.setAllowedMethods(
            List.of("GET", "POST", "PUT", "DELETE", "OPTIONS")
        );
        cors.setAllowedHeaders(
            List.of("Authorization", "Content-Type")
        );
        cors.setExposedHeaders(
            List.of("WWW-Authenticate", "X-Request-Id")
        );

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

In the API `SecurityFilterChain`, enable:

~~~java
http.cors(Customizer.withDefaults());
~~~

If using cookies/credentials, evaluate `allowCredentials` and allowed origins carefully. Never combine wildcard origins with credentials unconditionally. CORS is a browser protection; it **does not replace OAuth access token validation**.

### 13.2. `permitAll` Does Not Mean the Bearer Filter Is Off

A public endpoint `/api/public/info` may allow requests **with no token**. However, if a client sends an **invalid token**, the Bearer filter may still attempt to verify it and return 401 before the controller runs.

Do not “fix” this by stripping authentication validation from every public endpoint if the security architecture requires uniform credential handling.

## 14. Cache-Control, Vary, and Correlation IDs

### 14.1. Avoid Caching Error Responses Carrying Sensitive Info

You can set:

~~~http
Cache-Control: no-store
Pragma: no-cache
~~~

for authentication/authorization errors. `Pragma` is mainly for historical compatibility; `Cache-Control` is the primary mechanism.

Do not confuse error-body caching with:

- JWKS public key caching.
- Introspection result caching.
- Per-principal data response caching.
- Browser OAuth token storage.

### 14.2. CORS and Vary

When CORS varies responses by `Origin`, the framework may add `Vary: Origin` and related fields. Do not strip `Vary` when customizing security responses, so proxies/caches never mix responses across origins.

### 14.3. Correlation ID Instead of Raw Token

A response:

~~~json
{
  "status": 401,
  "code": "invalid_token",
  "traceId": "req-a19e"
}
~~~

is useful when internal logs/traces carry the same ID. However, `traceId` must be a controlled identifier; never blindly echo an overly long/malicious client-supplied header as a security identifier.

Never return raw Bearer tokens, private JWKS keys, refresh tokens, stack traces, or validator configuration details in the body.

## 15. Gateways and Proxies Can Break the HTTP Contract

A Spring Boot service returns a compliant 401, yet an upstream proxy may:

- Turn 401 into a 302 login redirect.
- Replace 403 with an HTML error page.
- Strip `WWW-Authenticate`.
- Change `Content-Type` to `text/html`.
- Omit CORS headers on errors.
- Turn a backend 503 into 200 with custom JSON.
- Incorrectly cache responses across authorization headers.

Therefore, test through the **actual public entrypoint**, not only directly against localhost.

Examples:

~~~bash
curl -i https://api.example.test/api/orders
~~~

~~~bash
curl -i \
  -H "Authorization: Bearer <INVALID_TEST_TOKEN>" \
  https://api.example.test/api/orders
~~~

Inspect status, headers, content type, and body together. Use test tokens—never paste production tokens into logs or bug reports.

## 16. Clients Should Process Status Before JSON

JavaScript frontend example:

~~~js
async function loadOrders(token) {
  const response = await fetch(
    "https://api.example.test/api/orders",
    {
      headers: { Authorization: "Bearer " + token }
    }
  );

  const challenge =
    response.headers.get("WWW-Authenticate");

  const contentType =
    response.headers.get("Content-Type") || "";

  const problem = contentType.includes("application/problem+json")
    ? await response.json()
    : null;

  if (response.status === 401) {
    // Expired/invalid token or unauthenticated caller.
    // May refresh per OAuth client policy; do not retry infinitely.
    throw new Error(problem?.code || "authentication_required");
  }

  if (response.status === 403) {
    // Valid permission required; do not endlessly refresh the same scope.
    throw new Error(problem?.code || "forbidden");
  }

  if (!response.ok) {
    throw new Error(problem?.detail || "API request failed");
  }

  return response.json();
}
~~~

The `challenge` variable is read for illustration; when parsing Bearer parameters, use an RFC-compliant HTTP challenge parser rather than ad-hoc string splitting.

When JavaScript needs to read `WWW-Authenticate` cross-origin, the API must configure CORS exposed headers as shown earlier. The frontend must also handle non-JSON responses or 204 statuses per the actual contract.

## 17. Tests Must Verify Status, Headers, and Body Together

### 17.1. Three Testing Scopes

- **Handler unit test:** verifies the delegate keeps headers/status intact and the writer produces valid JSON.
- **MockMvc/Spring Security integration test:** verifies requests pass through the right filter chain, entry point, and access-denied handler.
- **End-to-end test via proxy/gateway:** verifies status/challenge/body/CORS are not altered by intermediaries.

Spring Security Test's `jwt()` creates a convenient mock JWT authentication for authorization tests, **not proof that JwtDecoder verified signature/issuer/audience/JWKS**.

### 17.2. Missing Bearer Token

Example test with a configured `MockMvc mvc` and protected URL:

~~~java
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@Test
void missingTokenReturnsBearerChallengeAndJson() throws Exception {
    mvc.perform(get("/api/orders/42"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            "WWW-Authenticate",
            startsWith("Bearer")
        ))
        .andExpect(content().contentTypeCompatibleWith(
            "application/problem+json"
        ))
        .andExpect(jsonPath("$.status").value(401))
        .andExpect(jsonPath("$.code")
            .value("authentication_required"));
}
~~~

For a missing token, verify the Bearer challenge does **not** contain `error="invalid_token"` when the request genuinely has no authentication info.

### 17.3. Valid JWT Principal Missing Scope

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Test
void authenticatedWithoutReadScopeGetsForbidden() throws Exception {
    mvc.perform(
        get("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_profile")
            ))
    )
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.status").value(403))
        .andExpect(jsonPath("$.code").value("forbidden"));
}
~~~

The test above verifies the **authorization rule and handler body**, not JWT signatures. If the default Bearer handler emits `insufficient_scope` in the header, verify it per your implementation/version.

### 17.4. Testing Invalid JWTs with a Real or Stubbed Decoder

To properly test `invalid_token`, you can:

- Send real test JWTs signed with a test key, intentionally failing `exp`/`aud`/signature, with a configured test decoder/JWKS.
- Use a stub `JwtDecoder` throwing the corresponding authentication exception in the Spring test context, verifying the Bearer filter handles it and invokes the entry point.

Expectations:

~~~text
HTTP status = 401
WWW-Authenticate: Bearer ... error="invalid_token"
Content-Type: application/problem+json
JSON status = 401
JSON code = invalid_token
~~~

Never use mocked `jwt()` and assume you tested the JWT validator; that helper normally bypasses real token verification.

### 17.5. Testing Malformed Bearer Requests

With a resolver configured to detect duplicate/malformed token submissions, test:

~~~text
HTTP status = 400
WWW-Authenticate includes error="invalid_request"
JSON status = 400
JSON code = invalid_request
~~~

The default `BearerTokenResolver` restricts query/form parameters. Do not assume it reads `access_token` from URLs unless that transport method is explicitly enabled.

### 17.6. Response Contract Test Matrix

| Test | HTTP | Header | Body |
|---|---|---|---|
| No token, protected endpoint | 401 | Bearer challenge, no error for missing credentials | `status=401` |
| Bad-signature/expired JWT | 401 | `invalid_token` | `status=401`, right code |
| Malformed Bearer header | 400 | `invalid_request` | `status=400` |
| Valid principal missing `orders.read` | 403 | `insufficient_scope` on scope denial | `status=403` |
| Tenant/owner policy denial | 403/404 | Do not fake scope error | Body matches status |
| Invalid request body validation | 400 | No fake Bearer error | `invalid_body` |
| Wrong HTTP method | 405 | Valid `Allow` | `status=405` |
| Rate limit | 429 | `Retry-After` if applicable | `status=429` |
| JWKS/introspection outage | Infra error per config | Do not fail open | No secrets leaked |
| `permitAll` without token | Per endpoint | No challenge needed | Data response |
| `permitAll` with invalid Bearer | Possibly 401 | Bearer challenge | Authentication error |
| CORS OPTIONS preflight | Per CORS config | Do not require Bearer token | Valid CORS headers |
| Browser reading challenge | Preserve original status | Expose `WWW-Authenticate` | Parseable body |
| API gateway | Preserve original status | Do not drop challenge | Matching media type/status |

### 17.7. Assert Actual HTTP Status Equals JSON Status

Never check only one of the two. A test could pass with body `status` equal to 401 even when actual HTTP status is 200—a severe HTTP semantics bug.

If a reverse proxy alters the body or status, end-to-end tests must catch it rather than relying solely on MockMvc directly against the app.

## 18. Common Mistakes and How to Avoid Them

### “401 with a JSON body is enough; `WWW-Authenticate` is unnecessary”

Wrong. Bearer clients require HTTP authentication challenges per RFC 6750. Use standard handlers or preserve the challenge when adding JSON.

### “Sending no token equals `invalid_token`”

Not quite. RFC 6750 recommends **not** adding an error code to the challenge when the request lacks authentication information.

### “Token with insufficient scope returns 401”

Usually wrong. A valid token lacking privileges is `403`, optionally `insufficient_scope` per RFC 6750.

### “Every 403 must carry `insufficient_scope`”

Wrong when the reason is ACL/tenant/owner or business policy; classify the source of denial.

### “Every 400 is OAuth `invalid_request`”

Wrong. A JSON request body failing schema validation can return 400 without involving Bearer.

### “Return 200 with JSON error so the frontend handles it easily”

Wrong. Breaks semantics across HTTP clients, caches, gateways, and monitoring.

### “`@RestControllerAdvice` alone handles Bearer errors too”

Wrong. The Bearer filter can return errors before MVC. Use `AuthenticationEntryPoint` and `AccessDeniedHandler`.

### “Putting exception messages into `error_description` is safe”

No. Risks exposing internal info, invalid header characters, and untrusted data.

### “Calling `sendError` and then writing a JSON body works fine”

Do not rely on it. Containers/error handling may alter or commit the response. Set status/headers/body in one clean path.

### “CORS only needs allowed origins”

Frontends also need proper preflights and `Access-Control-Expose-Headers` to read `WWW-Authenticate` in JavaScript.

### “API gateways cannot modify auth responses”

Gateways can strip headers, alter statuses, or substitute HTML pages. Test through the exact path real clients use.

### “AS introspection returning 401 means the caller's Bearer token is invalid”

Not necessarily. The Resource Server's own introspection client credentials may be wrong.

## 19. Implementation Principles

1. **Get HTTP status right first:** 400 malformed Bearer request, 401 authentication failure, 403 insufficient privilege, other errors keep their own semantics.
2. **Keep `WWW-Authenticate` compliant with RFC 6750:** missing credentials usually omit Bearer `error`; invalid tokens carry `invalid_token`; missing scope carries `insufficient_scope` when appropriate.
3. **JSON supplements rather than replaces headers:** use RFC 9457 Problem Details or a uniform app schema; body `status` must match actual HTTP status.
4. **Use the right Spring extension points:** `AuthenticationEntryPoint` for authentication, `AccessDeniedHandler` for security denials, `@RestControllerAdvice` for MVC/business errors.
5. **Prefer built-in Bearer handlers:** preserve standard statuses/headers and only append safe JSON, avoiding manual challenge string concatenation.
6. **Never expose tokens/secrets/internal errors:** keep public descriptions concise; use correlation IDs and dedicated logs for operations.
7. **Separate HTTP API and browser login flows:** never apply one Bearer JSON handler to all URLs if OIDC login/sessions exist.
8. **Test the full response contract:** status + headers + body + CORS + gateway, including negative cases.

## 20. Summary

An error from an OAuth 2.0 Resource Server must maintain **consistent semantics across three layers**:

~~~text
HTTP status
  + WWW-Authenticate Bearer challenge / error
  + JSON body per API contract
~~~

Four situations to remember:

- **No token:** `401`, Bearer challenge usually without `error`.
- **Invalid token:** `401`, `invalid_token` when properly classified.
- **Malformed Bearer request:** `400`, `invalid_request` when RFC 6750 applies.
- **Valid token missing scope:** `403`, `insufficient_scope` on scope denial.

In Spring Security Servlet, **`BearerTokenAuthenticationEntryPoint`** and **`BearerTokenAccessDeniedHandler`** already handle most statuses and challenges. When JSON is required, wrap or customize these handlers **without losing RFC 6750 headers**, use RFC 9457 Problem Details if suitable, and keep body status identical to HTTP status.

### References

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [Spring Security Reference — OAuth 2.0 Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security API — BearerTokenAuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html)
- [Spring Security API — BearerTokenAccessDeniedHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/access/BearerTokenAccessDeniedHandler.html)
- [Spring Security API — OAuth2ResourceServerConfigurer](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/oauth2/server/resource/OAuth2ResourceServerConfigurer.html)
- [Spring Framework Reference — Error Responses and Problem Details](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
