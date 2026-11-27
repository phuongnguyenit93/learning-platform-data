# Standardizing 401, 403, and Authentication Error Responses in Spring Cloud Gateway

An **API Gateway** typically sits in front of multiple microservices, handling route predicates, filter chains, path/header transforms, and controlling which APIs clients are allowed to call. When a request is rejected, the response must not only carry the right HTTP status code: it must also be **structurally consistent**, **compliant with authentication protocols**, **free of sensitive data leaks**, and **helpful to clients deciding what to do next**.

For instance, a mobile app calling `GET /api/orders/42` can encounter three situations:

- Missing access token: the client needs to log in or obtain an appropriate token.
- Valid token lacking permission to read orders: the client is not allowed to proceed under the current identity.
- Forged or expired token: the client must handle an invalid token rather than just showing a generic "Server error" message.

All three cases may look similar in a UI, yet they **should not return the same status or trigger the same recovery flow**.

This lesson belongs to the **Authentication and Authorization** chapter of the `SPRING_CLOUD_GATEWAY` module. The focus is on **Spring Cloud Gateway Server WebFlux**, **Spring Security Reactive OAuth2 Resource Server**, HTTP error signaling, and shared API contracts. Other policies such as rate limiting, retries, circuit breakers, TLS, and tracing are addressed where they intersect with security errors.

> **Version scope:** Primary examples follow **Spring Cloud Gateway Server WebFlux 5.0.x**, Spring Cloud 2025.1.x, Spring Boot 4.x, and Spring Security 7.x. Route YAML uses `spring.cloud.gateway.server.webflux.routes`. Do not copy configurations from older Gateway branches (using `spring.cloud.gateway.routes`) or Server Web MVC to WebFlux without consulting the docs/APIs.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish **authentication failures** from **authorization denials**, mapping `401`, `403`, and exceptional cases accurately.
2. Explain the roles of `WWW-Authenticate`, `invalid_token`, `invalid_request`, and `insufficient_scope` under OAuth 2.0 Bearer Token (RFC 6750).
3. Propose a JSON error contract based on **Problem Details** (RFC 9457) with `status`, `code`, and `requestId`.
4. Implement `ServerAuthenticationEntryPoint` and `ServerAccessDeniedHandler` in Spring Security WebFlux without confusing them with `@ControllerAdvice` or `GlobalFilter`.
5. Configure Spring Security Reactive Resource Server to verify JWTs and enforce scopes on Gateway-proxied routes.
6. Test missing tokens, invalid/expired tokens, sufficient/insufficient scopes, CORS preflight, backend 401/403, and connection errors.
7. Avoid leaking detailed authentication internals or dropping standard headers when handling errors.

## 2. Distinguishing `401 Unauthorized` and `403 Forbidden`

The standard HTTP name `401 Unauthorized` is easily misunderstood: in practice it usually means **no valid authentication yet**, not "logged in but lacking permission."

| Scenario | Valid Credentials Present? | Typical Code | Client Handling |
|---|---|---|---|
| No `Authorization` sent to Bearer-protected API | No | `401` | Obtain a token and retry if appropriate |
| Expired/invalid access token | No | `401` | Replace with a valid token; do not retry infinitely |
| JWT with bad signature, wrong issuer, or rejected | No | `401` | Re-authenticate / verify valid token |
| Malformed Bearer request, token sent multiple ways | Cannot be processed validly | Usually `400` per RFC 6750 `invalid_request` | Fix the request |
| Authenticated token missing required scope | Yes | `403` | Request appropriate permission/scope; do not refresh infinitely |
| Authenticated user lacking rights on another user's order | Yes | Usually `403`; sometimes `404` to avoid disclosing resources | Not allowed to view/modify resource |
| Route/path does not exist | Not an auth error itself | `404` if allowed by policy/handler | Check endpoint |
| Gateway rate limiter rejects request | Not an auth error itself | `429` | Honor `Retry-After` if present |
| Upstream unavailable/timeout | Not an auth error itself | Appropriate `5xx` | Bounded retries honoring idempotency |

Quick rule of thumb:

```text
401: "I cannot authenticate you yet."
403: "I authenticated you, but you are not allowed to do this."
```

Not every system uses JWTs: sessions, mTLS/X.509, or API keys have their own authentication mechanisms. **The `401`/`403` semantics remain**, while the scheme and challenge header must match the active mechanism—never emit `Bearer` for a system that does not use Bearer tokens.

### 2.1. Decision Flowchart

```mermaid
flowchart TD
    A["Request reaches protected API"] --> B{"Credentials syntactically valid?"}
    B -- "No" --> C["400 invalid_request<br/>if matching OAuth Bearer error"]
    B -- "Yes / omitted" --> D{"Authentication succeeds?"}
    D -- "No" --> E["401 + WWW-Authenticate"]
    D -- "Yes" --> F{"Authorized for route/resource?"}
    F -- "No" --> G["403 or 404 per non-disclosure policy"]
    F -- "Yes" --> H["Forward to Gateway route/backend"]
```

The diagram describes **design rules**, not the exact callback order for every request: a tokenless request can be rejected by Spring Security before Gateway route predicates are even evaluated. If an endpoint does not exist while security policy requires authentication on all paths, an unauthenticated client may still receive `401` instead of `404`.

### 2.2. `401` and `403` Are Not Interchangeable

If a client sends a valid, verified JWT lacking the `orders:write` scope, returning `401` tricks the client into thinking the token expired and repeatedly attempting to refresh it. Returning `403` lets the client display "You do not have permission" or guide the user to request access.

Conversely, returning `403` for an expired token can prevent the app from triggering its token-renewal flow. Therefore, a consistent API must distinguish **invalid token** from **permission denied**.

## 3. HTTP Bearer Standard: `WWW-Authenticate`

Per **RFC 6750**, a resource server protected by Bearer tokens must return `WWW-Authenticate` when a request lacks credentials or lacks a token granting access. The challenge header tells clients the **scheme** and, when appropriate, the **OAuth reason**.

### 3.1. Missing Token

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Cache-Control: no-store
Content-Type: application/problem+json
```

**Important:** When the client sends no authentication information, RFC 6750 recommends **not including `error`** in the challenge. In other words, `WWW-Authenticate: Bearer realm="orders-api"` is sufficient; do not attach `error="invalid_token"` when a request simply omits the token.

### 3.2. Expired or Invalid Token

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Cache-Control: no-store
Content-Type: application/problem+json
```

The `invalid_token` code covers expired, revoked, bad-signature, wrong-issuer, and many other token errors. **Do not disclose** the exact reason a token failed in public responses. Returning overly detailed `error_description` values can expose authentication internals; prefer safe messages externally and log details internally.

### 3.3. Valid Token Missing Scope

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders:write"
Cache-Control: no-store
Content-Type: application/problem+json
```

`insufficient_scope` applies **when you specifically know a scope is missing**, not for every `403` denial. For instance, a user holding the order-read scope who accesses another user's order may be denied due to **resource ownership**. That is not necessarily a missing-scope error, and you should not advertise a misleading scope or leak another user's resource info.

### 3.4. Malformed Bearer Request

RFC 6750 defines `invalid_request`, e.g., sending a token via multiple invalid methods or malformed authentication parameters. In that case, `400 Bad Request` is recommended by the spec; do not force every Authorization-related error into `401`.

| OAuth Code in `WWW-Authenticate` | Typical HTTP Status | Meaning |
|---|---|---|
| No `error` | `401` | Credentials not sent |
| `invalid_request` | `400` | Malformed authentication request |
| `invalid_token` | `401` | Token cannot be accepted |
| `insufficient_scope` | `403` | Valid token lacking required scope |

For non-OAuth Bearer APIs, `WWW-Authenticate` must use the corresponding authentication scheme. Never emit fake challenges or pass through unverified challenges from another backend outside the same security domain.

## 4. JSON Contract: RFC 9457 Problem Details

Returning only:

```json
{"message":"Unauthorized"}
```

is too vague when applications need to distinguish invalid tokens, missing scopes, or business errors. One solution is **Problem Details for HTTP APIs**, standardized in **RFC 9457** (obsoleting RFC 7807).

Example `401`:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json
WWW-Authenticate: Bearer realm="orders-api"
Cache-Control: no-store
X-Request-Id: 9e84c68e-3b32-44aa-a0dd-439d4c4c3a8e

{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "code": "AUTHENTICATION_REQUIRED",
  "requestId": "9e84c68e-3b32-44aa-a0dd-439d4c4c3a8e"
}
```

Where:

| Field | Purpose | Notes |
|---|---|---|
| `type` | Problem type identifier | `about:blank` is valid; APIs can supply a docs URI if available |
| `title` | General, stable summary | Do not stuff exception details here |
| `status` | HTTP status in body | **Must match** the actual response status code |
| `detail` | Short user-facing description | May be omitted to avoid leaking details |
| `instance` | Identifies the specific occurrence | If using a URI, avoid sensitive queries/tokens |
| `code` | Machine-readable API **extension field** | Stable per team contract, not a mandatory RFC field |
| `requestId` | Log correlation **extension field** | Must not contain tokens, emails, or user IPs |

`type: about:blank` does not make `code` a standard HTTP error code. **The `AUTHENTICATION_REQUIRED`, `TOKEN_INVALID`, and `ACCESS_DENIED` codes below are application conventions** published and kept stable by the team.

### 4.1. Recommended Error Code Table

| HTTP | Application `code` | When to Use |
|---|---|---|
| `401` | `AUTHENTICATION_REQUIRED` | Request lacks credentials |
| `401` | `TOKEN_INVALID` | JWT/token was sent but is invalid |
| `403` | `ACCESS_DENIED` | Valid identity denied due to policy or ownership |
| `403` | `INSUFFICIENT_SCOPE` | Verified missing specific scope |
| `400` | `AUTH_REQUEST_INVALID` | Malformed Bearer authentication request |

A stable error contract needs a **documentation link**, code catalog, and client handling guidance. HTTP status remains the primary signal; frontends should not rely solely on `title` strings, which may be localized.

### 4.2. Never Return Detailed Exceptions to Clients

Avoid responses like:

```json
{
  "status": 401,
  "detail": "SignatureVerificationException at com.example.jwt.AuthFilter:172"
}
```

or embedding raw JWTs, public key IDs, internal issuers, role lists, user IDs, or stack traces. Clients only need enough signal to choose the right action. Internal logs may record the **normalized error category**, route ID, request ID, and timestamp; never log access tokens, cookies, or raw Authorization headers.

## 5. Error-Handling Boundary: Spring Security or GatewayFilter?

In **Gateway Server WebFlux**, **Spring Security `WebFilter`s** typically process authentication/authorization **before** requests reach route selection and the Gateway's `GlobalFilter + GatewayFilter` chain.

```mermaid
sequenceDiagram
    participant C as Client
    participant S as Spring Security WebFilter
    participant G as Gateway route + filter chain
    participant B as Backend
    C->>S: GET /api/orders/42
    alt Missing or invalid token
      S-->>C: 401 + Bearer challenge
    else Valid token lacking permission
      S-->>C: 403
    else Valid authentication + authorization
      S->>G: Forward HTTP request
      G->>B: Proxy to matched service
      B-->>G: HTTP response
      G-->>C: HTTP response
    end
```

Consequently, **placing `onErrorResume` inside a `GlobalFilter` does not guarantee catching authentication errors thrown in Spring Security WebFilters**. Nor should you expect `@RestControllerAdvice` to catch errors rejected by security before any controller runs.

| Location | Appropriate Tool | What It Does Not Automatically Handle |
|---|---|---|
| **Spring Security**: unauthenticated | `ServerAuthenticationEntryPoint` | Does not handle errors returned by backends |
| **Spring Security**: access denied | `ServerAccessDeniedHandler` | Does not automatically parse upstream 403s |
| **WebFlux controller** | `@ExceptionHandler`, `@RestControllerAdvice` / `ProblemDetail` | Does not replace security filter entry points |
| **Gateway route filter** | `GatewayFilter`, `GlobalFilter` | Does not run before Spring Security by default |
| **Backend service** | Backend security/exception handling | Gateway does not auto-convert backend 401/403 to a shared contract |
| **Ingress/WAF** | Proxy/ingress policies | Not generated by Gateway application code |

A consistent architecture **defines the error contract system-wide**, while implementing it at **each layer where errors originate**. Never write a filter trying to "turn all 4xx into 401", as that destroys `404`, `429`, `WWW-Authenticate`, and other critical signals.

## 6. Configuring JWT Resource Server on Gateway WebFlux

### 6.1. Dependencies and Issuer

With Spring Boot 4, the recommended starter for OAuth 2.0 Resource Server is:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security-oauth2-resource-server</artifactId>
</dependency>
```

You also need the **Spring Cloud Gateway Server WebFlux** starter, a Spring Cloud BOM compatible with Boot 4, and a Spring Boot app. This dependency does not create an Authorization Server.

Example configuration:

```yaml
server:
  port: 8080

spring:
  application:
    name: secure-gateway
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/issuer

  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-route
              uri: http://localhost:9001
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
```

`identity.example.test` is an **illustrative address** with no real IdP behind it, so this snippet alone cannot verify tokens. In a lab, replace it with an issuer from a configured test OIDC/OAuth2 system. The Gateway verifies signature, `iss`, `exp`, and `nbf` per decoder config; if your API requires a specific **audience**, add an appropriate `aud` validator. Never simply decode the JWT payload and trust `sub`/`scope` as valid data.

**Note:** In Spring Security, OAuth2 scopes are typically mapped to authorities prefixed with `SCOPE_`. For example, scope `orders:read` yields authority `SCOPE_orders:read`. If the IdP emits custom claims like `roles`/`permissions`, configure a verified converter and policy; never assign `ROLE_ADMIN` from a request header.

### 6.2. First Step: Keeping Spring Security's Standard Bearer Handlers

Before writing custom JSON formatting, run an app using the **built-in Bearer handlers**. The reactive classes are:

- `BearerTokenServerAuthenticationEntryPoint`: standardizes challenges and status on authentication failure.
- `BearerTokenServerAccessDeniedHandler`: standardizes access denials. The default handler may emit `insufficient_scope` when it sees a valid OAuth2 Authentication; if the app also checks **ownership/tenant** beyond scopes, consider a custom handler so not every denial is mislabeled as a missing scope.

Example `GatewaySecurityConfiguration.java`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.server.BearerTokenServerAccessDeniedHandler;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class GatewaySecurityConfiguration {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        var authEntryPoint = new BearerTokenServerAuthenticationEntryPoint();
        authEntryPoint.setRealmName("orders-api");

        var deniedHandler = new BearerTokenServerAccessDeniedHandler();
        deniedHandler.setRealmName("orders-api");

        return http
            // Only suitable for stateless Bearer-token APIs NOT using browser sessions.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .authorizeExchange(ex -> ex
                .pathMatchers("/actuator/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:write")
                .anyExchange().authenticated())
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(authEntryPoint)
                .accessDeniedHandler(deniedHandler))
            .oauth2ResourceServer(oauth -> {
                oauth.authenticationEntryPoint(authEntryPoint);
                oauth.accessDeniedHandler(deniedHandler);
                oauth.jwt(Customizer.withDefaults());
            })
            .build();
    }
}
```

**This configuration is for a stateless Bearer-only API.** If the Gateway also uses cookies/sessions or browser logins, do not blindly disable CSRF/`formLogin`; design security chains by endpoint type and credential model.

Behavior when calling `GET /api/orders/42`:

- No Bearer token → typically `401` with challenge `Bearer realm="orders-api"`.
- Invalid JWT → typically `401` and `invalid_token`.
- Valid JWT lacking `orders:read` → `403`; the built-in denial handler formats the Bearer challenge per authentication context.
- JWT with `orders:read` → enters the Gateway route, after which the HTTP status depends on the backend.

The default Bearer handlers **do not automatically add Problem Details JSON like the contract in section 4**; their advantage is built-in RFC 6750 semantics. If adding a JSON body, do so carefully without breaking challenges or statuses.

### 6.3. Why Configure Both Extension Points?

`exceptionHandling(...)` on `ServerHttpSecurity` configures the entry point and access-denied handler for errors handled by framework authorization. `oauth2ResourceServer(...)` also lets you set handlers for errors originating directly during Bearer token authentication.

When standardizing errors, ensure **both the authorization path and the Bearer token path** share a consistent policy, since invalid tokens and missing tokens may pass through different handling points. Spring Security provides defaults, which do not guarantee your team's custom JSON contract.

## 7. Customizing `401` and `403` to Problem Details JSON

The pattern below produces an `application/problem+json` body using **server-generated constants/UUIDs**, avoiding raw exception messages. It is an **alternative** to the built-in handlers in section 6.2 — choose one approach rather than registering two conflicting policies in the same security chain.

### 7.1. Writing Responses with WebFlux `ServerHttpResponse`

Create `SecurityProblemHandlers.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.UUID;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public final class SecurityProblemHandlers {
    private static final MediaType PROBLEM_JSON =
            MediaType.parseMediaType("application/problem+json");

    private SecurityProblemHandlers() { }

    public static ServerAuthenticationEntryPoint entryPoint() {
        return (exchange, error) -> {
            HttpStatus status = HttpStatus.UNAUTHORIZED;
            String code = "AUTHENTICATION_REQUIRED";
            String challenge = "Bearer realm=\"orders-api\"";

            if (error instanceof OAuth2AuthenticationException oauth) {
                String oauthCode = oauth.getError().getErrorCode();

                if ("invalid_token".equals(oauthCode)) {
                    code = "TOKEN_INVALID";
                    challenge += ", error=\"invalid_token\"";
                } else if ("invalid_request".equals(oauthCode)) {
                    status = HttpStatus.BAD_REQUEST;
                    code = "AUTH_REQUEST_INVALID";
                    challenge += ", error=\"invalid_request\"";
                }
            }

            return write(exchange, status, code, challenge);
        };
    }

    public static ServerAccessDeniedHandler deniedHandler() {
        return (exchange, denied) ->
            // Do not assume insufficient_scope for EVERY 403:
            // it could also be missing permission on a specific resource.
            write(exchange, HttpStatus.FORBIDDEN, "ACCESS_DENIED", null);
    }

    private static Mono<Void> write(
            ServerWebExchange exchange,
            HttpStatus status,
            String code,
            String wwwAuthenticate) {

        ServerHttpResponse response = exchange.getResponse();

        if (response.isCommitted()) {
            // Do not attempt to mutate status/headers/body once committed.
            return Mono.error(new IllegalStateException(
                    "Security response was already committed"));
        }

        String id = UUID.randomUUID().toString();
        String title = status == HttpStatus.UNAUTHORIZED
                ? "Unauthorized"
                : status == HttpStatus.FORBIDDEN
                    ? "Forbidden"
                    : "Bad Request";

        response.setStatusCode(status);
        response.getHeaders().setContentType(PROBLEM_JSON);
        response.getHeaders().set(HttpHeaders.CACHE_CONTROL, "no-store");
        response.getHeaders().set("X-Request-Id", id);

        if (wwwAuthenticate != null) {
            response.getHeaders().set(
                    HttpHeaders.WWW_AUTHENTICATE, wwwAuthenticate);
        }

        // Every field inserted into JSON is server-controlled:
        // constant status/title/code and a fresh UUID. Never insert raw error text.
        String json = """
            {"type":"about:blank",
             "title":"%s",
             "status":%d,
             "code":"%s",
             "requestId":"%s"}
            """.formatted(title, status.value(), code, id);

        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        return response.writeWith(Mono.just(
                response.bufferFactory().wrap(bytes)));
    }
}
```

**Explanation:**

- `ServerAuthenticationEntryPoint` receives `AuthenticationException` before returning an authentication failure response.
- If the exception is `OAuth2AuthenticationException` with code `invalid_token`, it sets status `401`, code `TOKEN_INVALID`, and the matching challenge.
- If `invalid_request`, the example maps it to `400` per RFC 6750. Not every application `400` is an `invalid_request`.
- `ServerAccessDeniedHandler` returns `403` and `ACCESS_DENIED`. It **does not guess** missing scope for every denial.
- `Cache-Control: no-store` reduces the risk of caching auth-related responses.
- `requestId` is generated with a fresh UUID in the handler. This is a **standalone demo**: if your system already has a trusted correlation ID, unify ID generation at the ingress/early `WebFilter` so both success and failure responses share one ID; do not generate a second arbitrary ID in production.
- `Content-Type: application/problem+json` indicates RFC 9457 format; `code` and `requestId` are extension fields.
- JSON is formatted manually **only because every interpolated value is a safe constant or UUID**. If adding `detail`, URIs, or dynamic fields, use a JSON serializer with proper escaping; never concatenate arbitrary inputs.

### 7.2. Wiring the New Handlers into `SecurityWebFilterChain`

Keep the issuer and route config from section 6.1. Define **one** security chain; the snippet below **replaces** the handler configuration from section 6.2:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class GatewayProblemSecurityConfiguration {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        var entry = SecurityProblemHandlers.entryPoint();
        var denied = SecurityProblemHandlers.deniedHandler();

        return http
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .authorizeExchange(ex -> ex
                .pathMatchers("/actuator/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:write")
                .anyExchange().authenticated())
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(entry)
                .accessDeniedHandler(denied))
            .oauth2ResourceServer(oauth -> {
                oauth.authenticationEntryPoint(entry);
                oauth.accessDeniedHandler(denied);
                oauth.jwt(Customizer.withDefaults());
            })
            .build();
    }
}
```

**Do not register both `GatewaySecurityConfiguration` and `GatewayProblemSecurityConfiguration` at the same time**, as they create competing `SecurityWebFilterChain` beans under the same conditions. Keep only one configuration class.

### 7.3. Important Limitation of the Simple JSON Sample

In this example, the `403` handler uses the generic `ACCESS_DENIED` code and **omits `WWW-Authenticate`** because it does not know whether the denial was truly caused by a missing scope. For pure OAuth2 APIs requiring an accurate `insufficient_scope` challenge, there are two options:

1. **Prefer Spring Security's built-in `BearerTokenServerAccessDeniedHandler`**, which handles RFC 6750 based on the OAuth2 authentication type; accept the default body and normalize on the client if Problem Details is not mandatory.
2. When Problem Details is mandatory, extend the handler with a **trusted authorization result** to distinguish missing-scope errors from policy/ownership denials; only when a scope is genuinely missing should you emit `WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"` and, where appropriate, `scope="orders:write"`. Never infer missing scopes from exception text alone.

The demo also intentionally **omits** `error_description`; when using the native Bearer handler, additional challenge attributes like `error_uri` can be handled per RFC 6750. When customizing, thoroughly test `invalid_request`, `invalid_token`, and insufficient-permission requests; **never treat the example as a full drop-in replacement for every framework feature**.

### 7.4. Consistent Error Codes Must Match the HTTP Status

Example JSON when an access token is valid but lacks permission:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-Id: 90f9fe22-44f4-49bb-9cae-1824f821d591

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "code": "ACCESS_DENIED",
  "requestId": "90f9fe22-44f4-49bb-9cae-1824f821d591"
}
```

A `401` error must never carry `status: 403` in its body from sharing a template. Clients may inspect both HTTP status and application `code`. Treat the actual HTTP status as authoritative; whenever the two mismatch, it is an API implementation bug.

## 8. `401/403` at the Gateway and at the Backend Are Two Different Sources

### 8.1. Gateway Rejects Directly

If Spring Security denies **before Gateway routing**, the backend **is not called**. This is the proper place for uniform responses via `ServerAuthenticationEntryPoint`/`ServerAccessDeniedHandler`.

### 8.2. Backend Returns 401 or 403

If the Gateway authenticated the client and proxied to order-service, and order-service returns `403` (e.g., the user does not own the order), that is an **HTTP response from the backend**. Do not assume the Gateway's Security WebFilter will intercept and reformat that response.

Design implications:

- Backends should adopt the **same error contract** if system-wide consistency is needed.
- If normalization at the Gateway is mandatory, use a dedicated response filter handling content-type, body, streaming, and committed responses, while **preserving valid `WWW-Authenticate` headers**.
- Never unconditionally rewrite backend `403` to `401`. That breaks HTTP semantics and can trigger token-refresh loops on clients.
- If the backend returns 401 due to an **internal service-to-service token** used by the Gateway to call the backend, that is an internal config/credential failure and **must not be blamed directly on the end user**. Identify the error origin before choosing the public response.

### 8.3. Gateway Authentication Alone Cannot Protect Every Resource

A route with `hasAuthority("SCOPE_orders:read")` verifies scope before forwarding to the backend. Yet the backend still needs to verify whether the user has rights to **specific order 42**. A token with order-read scope does not grant access to every order.

When there is a risk of disclosing sensitive resource existence, a backend may opt to return `404` instead of `403` per product policy. Agree on and test this rule consistently rather than applying it haphazardly across services.

## 9. Hands-On Practice: Testing `401` and `403` with `curl`

Assume the Gateway is configured with:

- Route `/api/orders/**` to backend `http://localhost:9001`, filter `StripPrefix=1`.
- Spring Security Resource Server JWT with a **real test issuer**, not the dummy `identity.example.test`.
- `GET /api/orders/**` requiring `SCOPE_orders:read`.
- `POST /api/orders/**` requiring `SCOPE_orders:write`.
- One of the two handler approaches from section 6 or section 7.

### 9.1. Echo Backend Only to Verify Routing

If you do not have an order-service yet, create `OrderBackend.java` in a lab folder:

```java
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

public class OrderBackend {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 9001), 0);

        server.createContext("/", exchange -> {
            String payload = "method=" + exchange.getRequestMethod()
                    + "\npath=" + exchange.getRequestURI().getRawPath()
                    + "\n";

            byte[] bytes = payload.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, bytes.length);
            try (var out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        });

        server.start();
        System.out.println("Order backend listening on :9001");
    }
}
```

Run with JDK 17+:

```bash
java --add-modules jdk.httpserver OrderBackend.java
```

Open another terminal in the Gateway project:

```bash
# Linux/macOS
./mvnw spring-boot:run

# Windows PowerShell
.\mvnw.cmd spring-boot:run
```

This echo backend **has no authentication** and exists solely to observe whether the Gateway proxies requests. Production must block direct backend access via network policies/mTLS or service-to-service authentication rather than relying solely on the Gateway.

### 9.2. Test A — Missing Bearer Token

```bash
curl -i http://localhost:8080/api/orders/42
```

With the custom Problem Details setup from section 7, you will see output similar to:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Content-Type: application/problem+json
Cache-Control: no-store

{"type":"about:blank","title":"Unauthorized","status":401,
 "code":"AUTHENTICATION_REQUIRED","requestId":"<Gateway-generated UUID>"}
```

This is an **illustrative response**: the UUID value, header order, and formatting may differ. What matters is HTTP `401`, the `Bearer` challenge, and a consistent application code. The order backend **should not receive** this request.

With the **built-in handlers from section 6.2**, the status and challenge are similar, though **there may be no JSON body**.

### 9.3. Test B — Invalid Access Token

```bash
curl -i http://localhost:8080/api/orders/42 \
  -H "Authorization: Bearer this-is-not-a-valid-jwt"
```

This dummy token cannot pass JWT verification. When Spring Security classifies it as `invalid_token`, the expected result is:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Content-Type: application/problem+json

{"type":"about:blank","title":"Unauthorized","status":401,
 "code":"TOKEN_INVALID","requestId":"<Gateway-generated UUID>"}
```

In the demo code, if the framework throws another `AuthenticationException` type, the application may fall back to the generic `AUTHENTICATION_REQUIRED` code. When a contract demands finer classification, clarify the **actual exception types** and assert them in automated tests rather than matching exception message strings.

### 9.4. Test C — Valid Token Lacking Permission

Prepare a **valid JWT issued by the test IdP** with scope `profile:read` and **without** `orders:read`. Do not manually edit a token's payload and expect its signature to stay valid.

In Bash:

```bash
# Obtain token from test IdP; never paste real tokens into docs/code.
export TOKEN_PROFILE='<valid-test-access-token>'

curl -i http://localhost:8080/api/orders/42 \
  -H "Authorization: Bearer $TOKEN_PROFILE"
```

Result with custom Problem Details from section 7:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
Cache-Control: no-store

{"type":"about:blank","title":"Forbidden","status":403,
 "code":"ACCESS_DENIED","requestId":"<Gateway-generated UUID>"}
```

If using **`BearerTokenServerAccessDeniedHandler`** from section 6.2, challenge info for missing scopes is handled by Spring Security per OAuth2 rules; do not compare the JSON bodies of the two approaches as though they were identical.

### 9.5. Test D — Valid Token with Matching Scope

Prepare a test token containing scope `orders:read` and an audience/issuer accepted by the Gateway:

```bash
export TOKEN_READ='<valid-test-access-token-with-orders-read>'

curl -i http://localhost:8080/api/orders/42 \
  -H "Authorization: Bearer $TOKEN_READ"
```

If the backend is healthy and routing is correct, sample response:

```http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=utf-8

method=GET
path=/orders/42
```

This proves the request passed the security policy, the Gateway matched the route, and `StripPrefix=1` worked. **It does not prove a production backend will let the user read order 42**, because resource-level authorization is not modeled in the echo backend.

### 9.6. Test E — Difference Between `GET` and `POST`

Using the same token that only has `orders:read`:

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Authorization: Bearer $TOKEN_READ"
```

Since the `POST` policy requires `SCOPE_orders:write`, the result is `403` **before proxying**. Never grant write permission just because a JWT has read permission. Retry with a separate token containing `orders:write` from the test IdP to confirm the Gateway allows POST.

> On PowerShell 5.1, `curl` may be an alias for `Invoke-WebRequest`. For standard curl syntax, invoke `curl.exe` and collapse `\` line continuations onto a single line. Never place real access tokens in command history, CI logs, or bug reports; use test-environment secrets and revoke them afterward.

### 9.7. Minimum Test Table

| Test Case | Expected HTTP | `WWW-Authenticate` | Backend Called? |
|---|---:|---|---|
| No Bearer token | `401` | `Bearer`, usually no `error` | No |
| Bad signature / expired JWT | `401` | `Bearer` with `invalid_token` when identified | No |
| Malformed Bearer request | Usually `400` | `invalid_request` per RFC | No |
| Valid JWT missing `orders:read` | `403` | Native handler may include `insufficient_scope` | No |
| Valid JWT with `orders:read`, GET, healthy backend | `200` from backend | Not required | Yes |
| Valid JWT with read-only, POST needing write | `403` | Depends on handler/scope policy | No |
| Valid JWT, backend returns 404 | `404` from backend | Not an auth challenge | Yes |
| Valid JWT, backend down | `5xx` or configured fallback | Do not replace with `401` | Proxy attempted |

Run tests against both handler approaches and note the distinction between **HTTP semantics** and the **JSON contract**.

## 10. CORS: Browsers Can Be Blocked Before Ever Seeing 401/403

For an SPA running on `https://app.example.test` calling a Gateway on another origin, browsers may send an `OPTIONS` **preflight** before requests carrying an `Authorization` header. Preflight requests usually lack a Bearer token; if Security immediately rejects with `401`, JavaScript may only see a CORS error instead of the actual JSON body.

**CORS must be processed before security steps that depend on the actual request's credentials.** In Gateway Server WebFlux, configure CORS at the Gateway or use `CorsWebFilter`/Spring Security reactive integration. Never simply add `OPTIONS` to a route's `Method` predicate and consider CORS handled.

### 10.1. CORS Example for WebFlux Security

One clear approach is providing a `UrlBasedCorsConfigurationSource` in the application:

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiCorsConfiguration {
    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://app.example.test"));
        config.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        config.setAllowedHeaders(
                List.of("Authorization", "Content-Type", "X-Request-Id"));
        config.setExposedHeaders(
                List.of("WWW-Authenticate", "X-Request-Id"));
        config.setAllowCredentials(false);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", config);
        return source;
    }
}
```

In `SecurityWebFilterChain`, add:

```java
.cors(Customizer.withDefaults())
```

at the appropriate place in the fluent DSL before `.build()`. Do not create multiple conflicting CORS configurations across Security, Gateway, and ingress.

- `allowedOrigins` should list trusted origins; never use arbitrary wildcards when credentials are allowed.
- `allowedHeaders` must permit necessary request headers, such as `Authorization`.
- `exposedHeaders` allows JavaScript to read `WWW-Authenticate` and `X-Request-Id` when permitted by CORS policy.
- `allowCredentials(false)` suits the Bearer-only API example; if using cookies/sessions, explicitly design `allowCredentials`, CSRF, SameSite, and origin allowlists.

### 10.2. Testing Preflight

```bash
curl -i -X OPTIONS http://localhost:8080/api/orders/42 \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: Authorization"
```

Inspect the status, `Access-Control-Allow-Origin`, allowed methods/headers, and verify whether the **actual GET request** reaches the Gateway. Without proper headers for a valid origin, browsers block reading the response even if the API returned a Problem Details body over the wire.

With Gateway 5.0, an alternative at the Gateway layer uses `spring.cloud.gateway.server.webflux.globalcors.cors-configurations`. If a `Method=GET` route prevents `OPTIONS` from matching, check `globalcors.add-to-simple-url-handler-mapping`. Pick one CORS strategy intentionally and test both paths **matching** and **not matching** Gateway routes.

## 11. Standardizing Security Errors Must Not Mix Up Other Error Types

The Gateway also runs rate limiters, circuit breakers, retries, TLS, and proxy mechanics. They produce HTTP outcomes **distinct** from auth/authorization:

| Scenario | Originating Layer | Typical Status | Handling |
|---|---|---|---|
| Missing access token | Spring Security | `401` | Valid Bearer challenge |
| Valid token lacking permission | Spring Security/backend | `403` | Do not continuously refresh token |
| Resource does not exist | Backend/router | `404` | Check business logic/path |
| Invalid body/request | Gateway/backend | `400`/`413` | Fix payload or reduce size |
| `RequestRateLimiter` rejects | Gateway filter | `429` | Honor limits and `Retry-After` if present |
| Backend connection failure | Gateway HTTP client | `502`/`503`/`504` depending on case | Monitor upstream, timeouts, and fallback |
| Circuit breaker open | Gateway filter | `5xx` or configured fallback response | Monitor circuit state; do not masquerade as 401 |
| Client → Gateway TLS handshake fails | TLS terminator | Usually **no HTTP status** | Check cert/CA/SAN/protocol |
| Gateway → backend mTLS fails | Gateway HTTP client/TLS | `5xx` proxy error | Check outbound certificates/trust |

**Never write an error filter turning all `4xx`/`5xx` into `200` with JSON `{"success":false}`.** Doing so misleads clients, load balancers, metrics, and retry policies while breaking `WWW-Authenticate` and `Retry-After` semantics.

### 11.1. Constraining Retries on Authentication Errors

- `401` for an expired token: the client may obtain a valid token **once per policy** and retry; never loop retries indefinitely on the same token.
- `403` for missing permissions: refreshing the same credentials usually grants no new permissions. Avoid futile retries.
- `429`: respect rate-limiting/backoff policies.
- `5xx`/timeouts: retries must weigh idempotency, attempt limits, total timeouts, and circuit breakers; for `POST /payments`, retries risk duplicate transactions.

### 11.2. Blocking Spoofed Internal Identity Headers

A client-sent `X-Internal-User-Id` header is **not** proof of identity. When the Gateway verifies a JWT and passes user ID downstream, strip incoming internal headers before regenerating them from the verified principal, and block direct backend access.

If the system uses correlation IDs, generate or validate the request ID at a trusted ingress/early `WebFilter` **before authentication** so both `401`/`403` errors and successful requests stay linked. A Gateway `GlobalFilter` may not execute for requests rejected by Security before routing, so do not rely on it to cover all auth failures.

## 12. Logging, Tracing, and Observability for 401/403

Observability should not merely count `401` and `403` responses—it should distinguish **missing tokens**, **invalid tokens**, **authorization denials**, and **backend errors**.

A safe log event might include:

```json
{
  "event": "gateway.security.denied",
  "requestId": "8fa0c97f-a5c2-4bca-9f93-b26ab23563f3",
  "routePattern": "/api/orders/**",
  "method": "GET",
  "status": 403,
  "code": "ACCESS_DENIED",
  "authMethod": "bearer",
  "source": "gateway-security",
  "durationMs": 7
}
```

This is illustrative data. In particular, `routePattern` should be a route template (without real order numbers) to bound metric cardinality. Prior to route matching, a **route ID may not exist yet**, so auth-rejection logging should not assume that field is always populated.

### 12.1. What to Log and What Never to Log

| Safe to Log | Avoid in Standard Logs |
|---|---|
| `requestId`, normalized `traceId` | Raw Bearer tokens or refresh tokens |
| HTTP status and stable error code | Full `Authorization`, `Cookie`, `Set-Cookie` headers |
| Safe `missing`/`invalid`/`denied` error category | Raw JWT claims containing personal data |
| Approved policy/route pattern name | Client-facing response bodies or debug stack traces |
| Processing duration, grouped error rates | Passwords, private keys, session IDs |
| Decision origin: gateway security vs. backend | Unverified client-sent internal headers |

When `401`s spike steadily, check for mass token expiration, IdP key/issuer changes, clock drift, or misconfigured client credentials. When `403`s spike, inspect permissions/roles/scopes, policy rollouts, and resource-level authorization.

### 12.2. Alerts and Origin Breakdown

Useful metric groups:

- `http.server.requests` or equivalent, tagged by status code, route pattern, and origin when available.
- `401`/`403` rates by **authenticated** client application/tenant, avoiding high-cardinality user IDs directly in metric labels.
- Token validation failures caused by JWKS/IdP unreachability vs. genuinely invalid tokens.
- `403` counts following role/scope policy changes.
- `429` from rate limiters and `5xx` from backends—never lump everything into "authentication failures."
- CORS preflight failure rate for allowed frontend origins.

Never assume every JWKS connection failure means an **invalid token**; sometimes the **verification infrastructure is unavailable**. Enforcement must still fail closed for protected access, while internal alerts and reasons must differentiate the two so operators fix the right issue.

## 13. Common Configuration Mistakes

| Symptom | Cause to Check | Fix |
|---|---|---|
| Missing token returns `403` | Handler/CSRF policy runs before auth or misconfigured exception handling | Check `SecurityWebFilterChain` and whether the API uses sessions/CSRF |
| Expired token returns only `403` | Authentication failure mapped to access denied | Configure entry point for `AuthenticationException`; inspect JWT validation |
| Backend 403 turns into 401 at Gateway | Error-rewrite filter overwrites status or groups all security errors | Separate error layers; never overwrite statuses arbitrarily |
| Missing `WWW-Authenticate` on Bearer 401 | Custom JSON handler forgot challenge | Use built-in Bearer entry point or construct RFC 6750 challenge |
| Every 403 emits `insufficient_scope` | Handler assumes all denials are missing scope | Emit only when policy confirms missing scope; use `ACCESS_DENIED` otherwise |
| Client refreshes tokens infinitely | Frontend treats every 403 as expired token or retries every 401 | Bound retries; distinguish 401/403 and OAuth error codes |
| SPA reports CORS error instead of 401 JSON | Preflight blocked or error response lacks CORS headers | Configure CORS before Security, test `OPTIONS`, and expose headers |
| Valid JWT still gets 401 | Issuer/audience/clock/key/algorithm mismatch or wrong-API token | Check validators, JWKS, and IdP environment |
| JWT has `scope=orders:read` yet gets 403 | Authority mapping mismatches `SCOPE_orders:read` or custom converter bug | Inspect verified authorities; never rely on unverified tokens |
| `@RestControllerAdvice` misses 401 | Error occurs in Spring Security WebFilter before controller | Configure `ServerAuthenticationEntryPoint` and `ServerAccessDeniedHandler` |
| `GlobalFilter` logs no 401s | Request rejected before Gateway route/filter chain | Generate correlation/observability early at ingress or WebFilter |
| JWT with read scope accesses another user's order | Only checked scope at Gateway; backend lacks ownership check | Enforce resource-level authorization at backend |
| Client sends `X-Internal-Role: admin` and gains access | Gateway/backend trusts internal headers from Internet | Strip/sanitize headers, generate only from verified principal; lock down backend |
| Route returns 401 despite Gateway authenticating | Backend verifies tokens itself and Gateway→backend credential is invalid | Identify 401 source and fix service-to-service trust/credentials |
| Bad token returns HTTP `200` + error JSON | Normalization handler breaks HTTP semantics | Return proper `401`/`403` per RFC and API contract |
| `401` gets cached and served wrongly | Improper caching configuration | Set `Cache-Control: no-store` on sensitive auth error responses |
| Services return inconsistent bodies | No shared error contract | Publish schema/version and enforce in Gateway **and** backends |

**Never "fix" 401/403 by broadly adding `permitAll()` just to make tests pass.** For public Gateways, policy must be **default deny or explicit allow** by design; opening permissions to mask config mistakes creates vulnerabilities.

## 14. Implementation Checklist for API Gateway Teams

- [ ] Clear contract for `401` (unauthenticated), `403` (authenticated but denied), `400` (malformed Bearer request), and `404` per resource policy.
- [ ] Uses Spring Security WebFlux Reactive Resource Server; never reads unverified JWT claims from headers/bodies.
- [ ] Validates signature, issuer, lifetime, audience, and scope/authority policies per API contract.
- [ ] `WWW-Authenticate` uses the right scheme; never includes `invalid_token` on requests simply missing a token.
- [ ] `insufficient_scope` used only for actual missing scopes; never leaks sensitive roles/tenants.
- [ ] HTTP status and Problem Details JSON `status` always match.
- [ ] Application codes like `AUTHENTICATION_REQUIRED` and `ACCESS_DENIED` are clearly defined and versioned.
- [ ] Never exposes stack traces, tokens, keys, passwords, signature info, user IDs, or internal policies in `detail`.
- [ ] Sets `Cache-Control` on sensitive auth responses; applies rate limiting on login/token endpoints.
- [ ] Configures CORS preflight for valid frontend origins; never skips CSRF when cookie/session auth is present.
- [ ] Distinguishes Gateway Security, ingress, Backend Security, and proxy/timeout errors.
- [ ] Prevents clients from injecting `X-Internal-User-Id`/`X-Internal-Role` headers trusted by backends.
- [ ] Backends enforce ownership/tenant/resource checks rather than trusting Gateway scopes alone.
- [ ] Normalizes request/trace IDs before security for both allowed and denied responses.
- [ ] Tests cover 401/403 for missing token, expired token, wrong issuer, missing scope, sufficient scope, CORS, and backend 401/403.
- [ ] Dashboards/alerts track error groups without logging raw `Authorization`/`Cookie` headers.
- [ ] Retries/fallbacks never convert auth errors into success codes or loop infinitely.

## 15. Design Scenario: Three Backends Sharing One Error Contract

Suppose a Gateway fronts three API groups:

| API | Gateway Policy | Policy Still Required at Backend |
|---|---|---|
| `GET /api/catalog/**` | May be public or require `SCOPE_catalog:read` | Restrict non-public items by product/tenant |
| `GET /api/orders/**` | Requires token with `SCOPE_orders:read` | Verify user owns the order |
| `POST /api/payments/**` | Token with `SCOPE_payments:write` | Enforce payment limits, anti-replay/idempotency |

The team adopts JSON Problem Details with `status`, `code`, and `requestId`. Still, enforcement follows each **error source**:

- **Gateway** emits 401 when tokens are missing/expired and 403 when pre-routing policies deny access.
- **Order-service** emits 403 or 404 per ownership policy, even when the token passed the Gateway.
- **Payment-service** may emit 409 on duplicate idempotency keys or 422 on business validation; never normalize those to 401 simply because payments involve "authorization."
- **Rate limiter** emits 429 and **circuit breaker** may return fallback/5xx; they can share the JSON envelope if desired, while keeping **distinct HTTP statuses and `code`s**.
- **TLS/mTLS** certificate failures abort before an HTTP response exists; JSON Problem Details cannot handle TLS terminator handshake failures.

## 16. Self-Check Questions

**Question 1.** A client calls a JWT-protected API without sending `Authorization`. Should you return `401` or `403`?

**Answer:** `401`, along with `WWW-Authenticate: Bearer ...` if it is a Bearer-protected resource.

**Question 2.** A verified JWT has only `orders:read`, and the client calls `POST /api/orders` requiring `orders:write`. What should be returned?

**Answer:** `403 Forbidden`. When missing scope is confirmed, Bearer `insufficient_scope` and the required scope may be included per RFC 6750.

**Question 3.** Does a request completely missing a token need `error="invalid_token"` in `WWW-Authenticate`?

**Answer:** No. RFC 6750 recommends omitting the error code when the request lacks authentication information.

**Question 4.** Why does `@RestControllerAdvice` not always catch `401`s from Resource Server?

**Answer:** Errors may originate inside Spring Security WebFilters before any controller executes. Configure `ServerAuthenticationEntryPoint` / `ServerAccessDeniedHandler`.

**Question 5.** Is `code: ACCESS_DENIED` in Problem Details a mandatory standard field of RFC 9457?

**Answer:** No. It is an application-defined extension field. `type`, `title`, `status`, `detail`, and `instance` have RFC-defined semantics, though not all are required to appear.

**Question 6.** The backend returns HTTP 403 after the Gateway proxies successfully. Will the Gateway's `401` entry point reformat that body?

**Answer:** No. That response came from the backend; achieving a unified schema requires the backend to follow the contract or a dedicated response transformation.

**Question 7.** Why might a browser report a CORS error even though `curl` sees a 401 JSON body?

**Answer:** Browsers require preflight and valid CORS response headers. If Security rejects `OPTIONS` or the response lacks `Access-Control-Allow-Origin`, JavaScript cannot read the body the way curl does.

**Question 8.** A `GlobalFilter` logging request IDs never sees requests rejected with 401. Why?

**Answer:** Requests may be handled by Spring Security before the Gateway route/filter chain. To cover all requests, generate correlation IDs early at the ingress or an appropriate WebFilter.

**Question 9.** Should you return a raw exception like `JWT signature mismatch at key-2026-prod` in `detail`?

**Answer:** No. Clients do not need implementation/key metadata; use public error codes and secure internal logs.

**Question 10.** A client receives 403 because it does not own order 42 even though its token has `orders:read`. Should it automatically refresh its token?

**Answer:** No. This is a resource-level denial; refreshing the token generally will not change ownership.

**Extended exercise:** Starting from the Security configuration in section 6, build a test table with at least 8 cases: missing token, bad signature, wrong issuer, expired, missing scope, sufficient scope, browser preflight, and backend 403. For each case, specify **originating layer**, **HTTP status**, **`WWW-Authenticate`**, **`code`**, **whether the backend is called**, and **frontend behavior**. Then pick one of the two handler options from sections 6/7 and write matching automated integration tests before deploying to production.

## 17. References

- [RFC 9110 — HTTP Semantics, 401 and 403](https://www.rfc-editor.org/rfc/rfc9110).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage, `WWW-Authenticate` and error codes](https://www.rfc-editor.org/rfc/rfc6750).
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457).
- [Spring Security 7.0 — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/7.0/reactive/oauth2/resource-server/jwt.html).
- [Spring Security 7.0 — Reactive Bearer Tokens](https://docs.spring.io/spring-security/reference/7.0/reactive/oauth2/resource-server/bearer-tokens.html).
- [Spring Security — `ServerHttpSecurity.ExceptionHandlingSpec` Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html).
- [Spring Security — `BearerTokenServerAuthenticationEntryPoint` Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/server/BearerTokenServerAuthenticationEntryPoint.html).
- [Spring Security — `BearerTokenServerAccessDeniedHandler` Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/access/server/BearerTokenServerAccessDeniedHandler.html).
- [Spring Security — Reactive CORS](https://docs.spring.io/spring-security/reference/7.0/reactive/integrations/cors.html).
- [Spring Framework 7.0 — WebFlux Error Responses / ProblemDetail](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html).
- [Spring Cloud Gateway 5.0 — CORS Configuration](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/cors-configuration.html).
- [Spring Cloud Gateway 5.0 — How It Works](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/how-it-works.html).
- [Spring Boot 4.0 — Starter dependencies](https://docs.spring.io/spring-boot/4.0/reference/using/build-systems.html).

**Key takeaway:** `401` tells the client it has not authenticated validly, while `403` means the request was authenticated but denied; `WWW-Authenticate` must follow the Bearer protocol when using OAuth2. **Problem Details standardizes JSON without replacing HTTP semantics.** In Gateway WebFlux, place logic in the right Spring Security layer, keep responses free of sensitive leaks, distinguish backend errors, and test every branch thoroughly before operating your microservices entry point.
