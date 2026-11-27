# BearerTokenAuthenticationEntryPoint and Unauthenticated Responses

When building a **Spring Security OAuth 2.0/OIDC Resource Server**, an API must respond clearly to clients in situations such as: no access token sent, invalid token sent, expired token, or token not intended for the Resource Server. Under **HTTP Bearer Authentication**, the critical part of the reply is not just the `401 Unauthorized` HTTP status code, but also the **`WWW-Authenticate`** header. Spring Security provides the **`BearerTokenAuthenticationEntryPoint`** class for this role.

This lesson examines the following topics in depth:

- What `BearerTokenAuthenticationEntryPoint` is and when it is invoked.
- Why a missing token usually receives `401` with a `WWW-Authenticate: Bearer` challenge.
- How `realm`, `error`, `error_description`, and `error_uri` relate to RFC 6750.
- Why a malformed Bearer error can be `400 invalid_request`, while an invalid token is `401 invalid_token`.
- Distinguishing **unauthenticated** from **authenticated but lacking permissions**, where the latter is usually `403 Forbidden` and belongs to `BearerTokenAccessDeniedHandler`.
- Configuring `realm`, customizing JSON responses while preserving the Bearer challenge, monitoring errors, and testing behavior via MockMvc/curl.
- Security pitfalls when logging tokens, exposing exception details, replacing `401` with `200`, or letting clients misunderstand when to refresh tokens.

> **Principle:** When an API is protected by bearer access tokens, returning `401` and a compliant Bearer challenge on authentication failures tells the client the request lacks valid authentication. However, `401` **does not mean every error can be fixed by refreshing the token**, and `BearerTokenAuthenticationEntryPoint` **is not used to grant permissions to the caller**.

## 1. Bearer Tokens and HTTP Authentication

In OAuth 2.0, a client typically sends an access token in a header:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
Accept: application/json
```

The token string may be a JWT or an opaque token. Either way, a bearer token is a **credential**: whoever holds the token string can attempt to use it to call the API. The Resource Server must validate the token appropriately per configuration:

- **JWT Resource Server:** verifies JWS signature, public key, issuer, timestamps, audience, and configured validators.
- **Opaque Token Resource Server:** introspects the token at the Authorization Server and applies additional constraints per contract.
- **Post-authentication authorization:** checks scopes/authorities, roles, and permissions on specific resources.

If the client sends no token or an invalid token, the API must deny access before treating the caller as an authenticated principal.

### 1.1. Why Is There a `WWW-Authenticate` Header?

HTTP authentication uses a **challenge–response** model. The server can send a `WWW-Authenticate` header in the response to inform the client which authentication method is required, such as:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

`Bearer` is the authentication scheme name. It is **not** a token, secret, scope, cookie, or user login method. It signals that the Resource Server accepts a **Bearer credential** for that resource.

If the server sets `realm`:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
```

The client sees the realm as a description of the protection space. Realm can be helpful when a system has multiple APIs/security domains, but must not be used in place of issuer, audience, or tenant validation.

### 1.2. A Response May Not Need a JSON Body

For an authentication challenge, the header is the essential element. A response:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Content-Length: 0
```

can be completely sufficient under the API's Bearer contract. Some products add a JSON body for frontend display; that is a custom choice, **not an RFC 6750 requirement**.

## 2. What Is `BearerTokenAuthenticationEntryPoint`?

In Spring Security Servlet, the general `AuthenticationEntryPoint` interface has one primary method:

```java
void commence(
    HttpServletRequest request,
    HttpServletResponse response,
    AuthenticationException authenticationException
) throws IOException, ServletException;
```

The purpose of `commence(...)` is to **start the authentication-request process** when a request lacks a valid Authentication. In a traditional session-based web app, an entry point might redirect to a login page. In a Bearer-token Resource Server, an HTML login redirect is usually inappropriate; the client needs an **HTTP status and challenge**.

`BearerTokenAuthenticationEntryPoint` is the implementation for Bearer authentication. It can:

1. Write the `WWW-Authenticate` header for the Bearer scheme.
2. Optionally advertise `realm` when configured.
3. If the exception carries a `BearerTokenError`, include appropriate error parameters in the challenge.
4. Select the HTTP status based on the corresponding Bearer error; if no specific error info is present, typically use `401 Unauthorized`.

Key imports:

```java
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.AuthenticationException;
import jakarta.servlet.ServletException;
import java.io.IOException;
```

### 2.1. The Entry Point Is Not Where Tokens Are Validated

`BearerTokenAuthenticationEntryPoint` does **not**:

- Fetch JWKS or verify JWT signatures.
- Call the introspection endpoint.
- Select a trusted issuer.
- Parse tokens and construct principals.
- Grant scopes/roles to the request.
- Check order ownership permissions.

It receives an **AuthenticationException** raised in the security flow and formats the **HTTP response when authentication is required**.

### 2.2. The Entry Point Does Not Handle All 403 Errors

When a token is valid but the caller lacks an authority, the error is usually an **AccessDeniedException**, belonging to the authorization branch. Spring Security Resource Server provides `BearerTokenAccessDeniedHandler` to handle appropriate Bearer authorization failures, typically `403 Forbidden` and optionally an `insufficient_scope` challenge.

Therefore, do not misassign responsibilities:

| Error Type | Typical Component | Common HTTP |
|---|---|---|
| No valid Authentication | `BearerTokenAuthenticationEntryPoint` | `401` |
| Invalid access token | `BearerTokenAuthenticationEntryPoint` | `401 invalid_token` |
| Malformed Bearer request | `BearerTokenAuthenticationEntryPoint` with corresponding `BearerTokenError` | Possibly `400 invalid_request` |
| Authenticated caller lacking permission | `BearerTokenAccessDeniedHandler` | `403 insufficient_scope` or `403` |
| Token has scope but lacks access to order 42 | Service/method authorization | `403` or `404` per policy |
| Controller encounters business error | Business exception handler | Depends on error, does not become a Bearer challenge |

## 3. Spring Security Servlet Flow: Where Is the Entry Point Called?

For a JWT Resource Server, the logical processing chain is typically:

```mermaid
flowchart TD
    A["HTTP request"] --> B["SecurityFilterChain"]
    B --> C["BearerTokenAuthenticationFilter"]
    C --> D{"Bearer token resolved from request?"}
    D -- "Yes" --> E["AuthenticationManager / JwtAuthenticationProvider"]
    E --> F["JwtDecoder: signature + validators"]
    F --> G{"Decode and validation succeeded?"}
    G -- "No" --> H["Authentication failure"]
    H --> I["BearerTokenAuthenticationEntryPoint"]
    D -- "No" --> J["Continue with anonymous/unauthenticated context"]
    J --> K["AuthorizationFilter: route protected?"]
    K -- "Yes, requires authenticated" --> L["ExceptionTranslationFilter invokes AuthenticationEntryPoint"]
    L --> I
    G -- "Yes" --> M["JwtAuthenticationToken / SecurityContext"]
    M --> N["AuthorizationFilter"]
    N --> O{"Sufficient authority?"}
    O -- "No" --> P["BearerTokenAccessDeniedHandler"]
    O -- "Yes" --> Q["Controller / service"]
    I --> R["HTTP Bearer challenge"]
    P --> S["HTTP authorization denied"]
```

The diagram shows the conceptual flow. Specific filter names, providers, and exception-handling branches may vary in detail by version/configuration, but **two main scenarios** are critical:

- A token was sent, yet **authentication failed**: the failure path triggers the entry point.
- **No token was sent**: the bearer filter may create no Authentication; when the route requires authentication, authorization/exception translation triggers the entry point.

### 3.1. When No Token Is Present, the Bearer Filter Does Not Necessarily Error Directly

Suppose a request:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Accept: application/json
```

If `BearerTokenResolver` finds no token, `BearerTokenAuthenticationFilter` typically lets the request pass instead of throwing an error immediately. Then:

1. Route `/api/orders/**` requires a suitable Authentication.
2. `AuthorizationFilter` detects the caller does not meet the requirement.
3. The exception translation mechanism initiates authentication via the entry point.
4. The server sends the challenge to the client.

This explains why a `permitAll()` endpoint is accessible **without an Authorization header**, whereas a protected endpoint returns `401`.

### 3.2. Sending a Bad Token Is a Different Scenario

If the client sends a token that the decoder cannot authenticate:

```http
Authorization: Bearer invalid-token-value
```

then the AuthenticationProvider/decoder/introspector rejects it. The entry point can receive an exception containing `BearerTokenError` and craft a more specific challenge.

There is no need to wait for the controller, because authentication is the security filter chain's responsibility.

### 3.3. Avoid Letting Controllers Return `401` Ad Hoc

A controller returning:

```java
return ResponseEntity.status(401).body("Please log in");
```

is just a developer-crafted response; it is **not guaranteed** to contain `WWW-Authenticate` or match Bearer error semantics. For protected endpoints, let Spring Security handle authentication at the filter layer; the controller handles business logic once the request is authenticated.

## 4. Missing Token: Challenge Need Not Say “invalid_token”

Per RFC 6750, if a request **sends no authentication information**, the server should send a Bearer challenge, but **should not attach an error code** for this case.

Appropriate example:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
```

Whereas this can mislead a request that has not sent a token:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Because **there is no token to judge invalid**. The client simply needs to know the endpoint requires Bearer authentication.

A browser or API client can use this information to switch to the appropriate access-token acquisition flow, or prompt the user to log in. The Resource Server **does not provide a password login flow merely because it emits a Bearer challenge**.

### 4.1. Request Missing a Token on a Public Endpoint

Suppose:

```java
.requestMatchers(HttpMethod.GET, "/public/catalog").permitAll()
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

Typical results:

| Request | Authorization Header | Decision |
|---|---|---|
| `GET /public/catalog` | None | Permitted past HTTP authorization |
| `GET /api/orders/42` | None | Authentication required, usually `401` + Bearer challenge |
| `GET /api/orders/42` | Valid token with read scope | Proceeds to business authorization |
| `GET /api/orders/42` | Valid token missing read scope | Usually `403` |
| `GET /api/orders/42` | Invalid/expired token | Usually `401 invalid_token` |

Note: `permitAll()` **does not mean skipping all security filters**. If a client intentionally sends a malformed Bearer header even to a public route, the filter may process the bad token before the authorization step and generate an error response depending on configuration.

## 5. HTTP Bearer Error Semantics Under RFC 6750

RFC 6750 describes common errors when accessing protected resources.

| Bearer error code | When It Appears | Typical HTTP Status |
|---|---|---|
| `invalid_request` | Malformed request, duplicate/invalid Bearer token transport, or invalid parameters | `400 Bad Request` |
| `invalid_token` | Token expired, revoked, malformed, unverifiable, or unaccepted under contract | `401 Unauthorized` |
| `insufficient_scope` | Token authenticated but lacking sufficient scope required for resource | `403 Forbidden` |

The statuses are standard/typical Bearer token usage behaviors; exception handlers, gateways, or custom policies can affect actual responses. When designing an API, keep meaningful distinctions instead of forcing every error to `401`.

### 5.1. Example: `invalid_request`

A Bearer request deemed malformed may receive:

```http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer realm="orders-api", error="invalid_request"
```

Examples of issues that can trigger `invalid_request`: sending multiple token methods disallowed by the resolver, malformed Authorization header, or violating token transport rules accepted by the Resource Server.

**Do not conclude every bad Authorization header must yield the exact same code:** `DefaultBearerTokenResolver` and version-specific configuration determine the raised error. Semantically, however, `invalid_request` differs from `invalid_token`: one says the request presented the credential improperly, while the other says the token is not accepted.

### 5.2. Example: `invalid_token`

Token sent, but signature invalid or expired:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
```

Some cases include a description:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api",
  error="invalid_token",
  error_description="The access token is invalid"
```

This is wrapped onto multiple lines for readability; **over real HTTP, the header must follow valid header value syntax**, without inserting arbitrary newlines into the value.

An invalid token status can result from JWT signature, issuer, audience, time validators, or opaque introspection failure. Never expose raw JWTs, key data, sensitive claims, or internal system structure via `error_description`.

### 5.3. Example: `insufficient_scope`

Valid token has `orders.read` while the endpoint requires `orders.export`:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api",
  error="insufficient_scope",
  scope="orders.export"
```

The snippet above depicts **one possible response**; Spring Security does not automatically infer and emit the required scope name of every matcher rule in all configurations. The `scope` parameter must have a solid basis and only be emitted when known accurately—do not assume the framework fills it in automatically.

Typically `BearerTokenAccessDeniedHandler` is the component involved in the authorization-denied branch. `BearerTokenAuthenticationEntryPoint` is not the place to design the “insufficient permissions on a valid token” API response.

## 6. Parameters of `WWW-Authenticate: Bearer`

A Bearer challenge may contain these parameters:

| Parameter | Meaning | Note |
|---|---|---|
| `realm` | Protection space advertised by server | Does not replace issuer/audience; avoid names with sensitive data |
| `error` | Error code such as `invalid_token` | Missing credentials usually omit error |
| `error_description` | Description helping explain the error | Avoid leaking sensitive details or exploitable info |
| `error_uri` | URI pointing to error documentation | Never use client-supplied URLs; omit if unnecessary |
| `scope` | Required scope, usually paired with `insufficient_scope` | Not necessarily derived automatically from Spring authorization matchers |

Values must be encoded/escaped per header syntax, never concatenated from untrusted input.

### 6.1. Realm Differs from Issuer

A configuration may have:

```text
Issuer:
  https://login.example.test/realms/shop

Audience:
  orders-api

Bearer realm:
  orders-api
```

All three have different meanings:

- `iss` in the token: the issuer trusted by the Resource Server.
- `aud`: whether the token was issued for this API.
- `realm`: how the protection space is labeled in the HTTP challenge.

**Do not use Bearer realm to validate issuer or audience**. An attacker can send a token from the wrong issuer even when the server's challenge sets a clean, accurate realm.

### 6.2. Header Values Should Not Contain User Input

Unsafe example:

```java
String realm = request.getParameter("realm");
entryPoint.setRealmName(realm);
```

If realm comes from an unauthenticated request, a client can manipulate response headers. In practice, realm should be a **trusted server configuration value**, typically set at bean creation and invariant across requests.

## 7. Spring Security Builds Challenges from `BearerTokenError`

In Spring Security Resource Server, an authentication exception may be an `OAuth2AuthenticationException` carrying an `OAuth2Error`. For errors specific to Bearer transport, Spring Security also provides `BearerTokenError`.

Conceptual code example:

```java
BearerTokenError error =
    BearerTokenErrors.invalidToken("The access token is invalid");

OAuth2AuthenticationException exception =
    new OAuth2AuthenticationException(error);
```

Corresponding imports:

```java
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.BearerTokenError;
import org.springframework.security.oauth2.server.resource.BearerTokenErrors;
```

`BearerTokenAuthenticationEntryPoint` can read the error details from the exception and build the corresponding Bearer challenge.

**There is no need to throw this exception manually in ordinary controllers.** It illustrates how Spring Security represents errors at the authentication layer.

### 7.1. Distinguish Error Objects from HTTP Responses

`BearerTokenError` describes the error: code, HTTP status, description/URI, and optionally related scope. `BearerTokenAuthenticationEntryPoint` uses that information to return a response.

For authentication exceptions without specialized Bearer error info, the entry point usually generates only a generic challenge. That is far more sensible than inventing an “expired token” reason when the framework has no evidence.

### 7.2. Do Not Force Every Exception into `invalid_token`

A request without a token, a malformed bearer header, and a badly signed token **are not the same event**. A custom entry point should preserve the framework's standard classification or map intentionally under control.

Do not catch `Exception` and always return `invalid_token`; infrastructure failures like JWKS endpoint unavailable, DNS/TLS/introspection timeouts may require different operational classification, though authentication must still fail closed.

## 8. Default JWT Resource Server Configuration

Spring Boot can configure issuer and audience:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
          audiences:
            - orders-api
```

The audience property is supported in compatible Spring Boot versions; if the project uses a custom decoder or another version, attach an appropriate audience validator.

SecurityFilterChain:

```java
@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/catalog")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
```

With this configuration, Spring Security sets up Bearer authentication and handles authentication failures via the Resource Server branch, typically with the appropriate Bearer entry point.

**Boundary point:** `audiences: orders-api` verifies which API the token is intended for; `hasAuthority("SCOPE_orders.read")` checks endpoint operation permissions. A token with the right issuer but wrong audience must be rejected at authentication, not let through just because it carries a plausible-looking scope.

## 9. Explicitly Configuring `BearerTokenAuthenticationEntryPoint` and Realm

If the API wants challenges with a consistent realm, you can instantiate the entry point directly:

```java
@Configuration
public class BearerChallengeConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        BearerTokenAuthenticationEntryPoint entryPoint =
            new BearerTokenAuthenticationEntryPoint();

        entryPoint.setRealmName("orders-api");

        BearerTokenAccessDeniedHandler accessDeniedHandler =
            new BearerTokenAccessDeniedHandler();

        accessDeniedHandler.setRealmName("orders-api");

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/catalog")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> {
                oauth2.jwt(Customizer.withDefaults());
                oauth2.authenticationEntryPoint(entryPoint);
                oauth2.accessDeniedHandler(accessDeniedHandler);
            })
            .build();
    }
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
import org.springframework.security.web.SecurityFilterChain;
```

How to read this:

- `BearerTokenAuthenticationEntryPoint` is responsible for the challenge when authentication has not succeeded.
- `setRealmName("orders-api")` describes the protection space.
- `BearerTokenAccessDeniedHandler` handles AccessDeniedException in the Resource Server, rather than conflating it with a missing token.
- `oauth2.jwt(...)` enables JWT Resource Server.
- `authorizeHttpRequests(...)` protects endpoints by method/path/authority.

**Use only one matching SecurityFilterChain configuration per request**, or configure multiple chains with clear scope and ordering. The snippets in this lesson illustrate configuration patterns; do not paste duplicate `apiSecurity` beans into the same application.

### 9.1. Realm Is Descriptive Configuration, Not Permission Granting

Example response when missing a token:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
```

This does not cause the Resource Server to accept a token with `aud=payments-api` or `iss` from another issuer. The decoder/validator continues enforcing its own trust boundaries.

### 9.2. The Stateless Nature of a Bearer Resource Server

For an API based on bearer access tokens, do not redirect users to an HTML login page merely for a missing token. Obtaining tokens is normally the OAuth client's responsibility. The Resource Server protects data and returns meaningful HTTP challenges.

Stateless authorization does not necessarily eliminate all sessions/cookies in a hybrid app combining web UI and API. If multiple filter chains exist, assign Bearer authentication to the API branch rather than accidentally letting a form-login entry point handle API requests.

## 10. Customizing the JSON Body While Preserving `WWW-Authenticate`

Some frontends want a uniform JSON response:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Content-Type: application/problem+json

{"type":"about:blank","title":"Unauthorized","status":401}
```

Returning only JSON and omitting `WWW-Authenticate` can lose the Bearer challenge details API clients depend on.

A safer implementation is to **delegate first to BearerTokenAuthenticationEntryPoint** to set the standard status/headers, then write a neutral JSON body if the response is not yet committed.

### 10.1. Example of a Custom `AuthenticationEntryPoint`

```java
public final class JsonBearerAuthenticationEntryPoint
        implements AuthenticationEntryPoint {

    private final BearerTokenAuthenticationEntryPoint delegate;
    private final ObjectMapper objectMapper;

    public JsonBearerAuthenticationEntryPoint(
            ObjectMapper objectMapper,
            String realm) {

        this.objectMapper = Objects.requireNonNull(objectMapper);
        this.delegate = new BearerTokenAuthenticationEntryPoint();
        this.delegate.setRealmName(realm);
    }

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException, ServletException {

        // Write Bearer challenge and HTTP status per Spring Security.
        delegate.commence(request, response, exception);

        if (response.isCommitted()) {
            return;
        }

        int status = response.getStatus();
        String title = (status == 400)
            ? "Bad Request"
            : (status == 401)
                ? "Unauthorized"
                : "Authentication Error";

        Map<String, Object> problem = Map.of(
            "type", "about:blank",
            "title", title,
            "status", status
        );

        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType("application/problem+json");

        objectMapper.writeValue(response.getWriter(), problem);
    }
}
```

Imports:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.Objects;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
```

Usage configuration:

```java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        ObjectMapper objectMapper) throws Exception {

    AuthenticationEntryPoint jsonEntryPoint =
        new JsonBearerAuthenticationEntryPoint(
            objectMapper, "orders-api");

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/**").authenticated()
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> {
            oauth2.jwt(Customizer.withDefaults());
            oauth2.authenticationEntryPoint(jsonEntryPoint);
        })
        .build();
}
```

The JSON body snippet shows how to **preserve status/headers produced by the delegate**, avoid forcing every failure into `401`, and avoid leaking internal errors. In a real API, routes need `hasAuthority(...)` instead of only `authenticated()` when endpoints require specific permissions.

### 10.2. Caveats When Adding a Body

- **Do not overwrite** the `WWW-Authenticate` header created by the delegate.
- Do not lose the `400` status on `invalid_request` when adding a custom body.
- Do not include raw tokens, JWT claims, introspection secrets, stack traces, or key info in JSON.
- Do not blindly copy `exception.getMessage()` into `detail` for callers without sanitization rules.
- Do not write anything further if the response is already committed.
- Ensure consistent encoding, content type, and error handling.
- If a custom body is needed for `403`, customize the corresponding **AccessDeniedHandler** rather than trying to make AuthenticationEntryPoint handle both.

### 10.3. Why Doesn't Every API Need a JSON Body?

HTTP clients can handle errors based on status and `WWW-Authenticate`. Adding a JSON body means the API maintains an extra contract for error format, versioning, localization, and display text. Without an actual requirement, the standard challenge is already a clear answer.

## 11. Differences Between `ExceptionTranslationFilter` and `BearerTokenAuthenticationFilter`

Two intersection points often appear:

### 11.1. ExceptionTranslationFilter Handles Initiating Authentication

When authorization encounters an unauthenticated request requiring login/token, `ExceptionTranslationFilter` can forward that situation to `AuthenticationEntryPoint` to return a challenge.

Example:

```text
GET /api/orders
Authorization: (none)

authorizeHttpRequests:
  /api/orders requires SCOPE_orders.read

→ no valid Authentication yet
→ invoke AuthenticationEntryPoint
→ 401 + WWW-Authenticate: Bearer
```

### 11.2. BearerTokenAuthenticationFilter Handles Tokens That Were Sent but Failed

Example:

```text
GET /api/orders
Authorization: Bearer expired-token

BearerTokenAuthenticationFilter:
  resolve token
  authenticate via JwtDecoder / introspector
  AuthenticationException
  failure handler invokes corresponding entry point
→ Bearer challenge with appropriate error
```

This matters when customizing error handling: a `@ControllerAdvice` is usually **not enough** to catch all Spring Security exceptions occurring in the filter chain before the controller.

### 11.3. Do Not Assume All Errors Are AuthenticationException

Once a token is valid, `AccessDeniedException` belongs to the insufficient-permissions branch. If a business service throws a domain exception itself, that may fall under MVC/controller exception handling. Understand the error layer to return the right status.

## 12. Comparing `BearerTokenAuthenticationEntryPoint` and `BearerTokenAccessDeniedHandler`

These two classes are often mentioned together, yet their functions differ.

| Property | BearerTokenAuthenticationEntryPoint | BearerTokenAccessDeniedHandler |
|---|---|---|
| Exception family | `AuthenticationException` | `AccessDeniedException` |
| Detected state | Caller is not validly authenticated | Caller is authenticated but lacks permissions |
| Typical HTTP | `401`, sometimes `400` per BearerTokenError | `403` |
| Header | `WWW-Authenticate: Bearer...` | Possibly Bearer challenge and `insufficient_scope` |
| Has `setRealmName`? | Yes | Yes |
| Verifies JWT signature? | No | No |
| Grants authorities to Authentication? | No | No |
| Should object-level policy live here? | No | No |

### 12.1. Missing Scope Scenario

Valid token:

```json
{
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

Route:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/admin/export")
    .hasAuthority("SCOPE_orders.export")
```

The result is usually `403 Forbidden`, not `401 invalid_token`. The token can still be used on normal read endpoints, so clients should not be told to refresh the token infinitely trying to get export scope.

### 12.2. Missing Record-Level Permission Scenario

The token has `orders.read`, the GET endpoint allows it through, yet the request targets an order belonging to another user. Business authorization may return `403` or intentionally `404` to avoid revealing record existence.

This is **object-level authorization**, not an authentication error. Never throw `BadJwtException` or attach `invalid_token` just for lacking permission on one order.

## 13. When to Use `401`, `403`, and `400`?

Summary by API behavior:

| Request | Token Status | Authorization | Expected HTTP |
|---|---|---|---|
| No Bearer header to protected API | Unauthenticated | Cannot authorize | `401` + Bearer challenge |
| Malformed Bearer header structure | No valid token to authenticate | Permissions not evaluated | Possibly `400 invalid_request` |
| JWT with bad signature | Invalid | Permissions not evaluated | Usually `401 invalid_token` |
| Expired JWT | Invalid | Permissions not evaluated | Usually `401 invalid_token` |
| JWT with wrong issuer/audience | Unsuitable for API | Permissions not evaluated | Usually `401 invalid_token` |
| Opaque introspection returns inactive | Invalid | Permissions not evaluated | Usually `401 invalid_token` |
| Valid token lacking `SCOPE_orders.read` | Authenticated | HTTP authorization denies | Usually `403` |
| Valid token, has scope, not owner | Authenticated | Object policy denies | `403`/`404` |
| Valid token, has permission, domain state forbids operation | Authenticated | State constraint | Possibly `409` |
| Valid token, sufficient permissions | Authenticated | Permitted | Business HTTP success |

Not every infrastructure error in decoder/introspection maps identically to token errors. If JWKS or introspection is unreachable, the server may return a 5xx error depending on exception flow; **never accept a token just because infrastructure failed**.

## 14. Which Errors Does `BearerTokenResolver` Influence?

Before calling the decoder/introspector, the Resource Server must extract the token from the request. Spring Security normally uses `DefaultBearerTokenResolver` to resolve bearer tokens from the `Authorization` header.

Standard example:

```http
Authorization: Bearer <ACCESS_TOKEN>
```

Some configurations allow tokens from form-encoded bodies or query parameters; however, transmitting tokens in URLs **risks** recording them in browser history, server logs, referrers, proxies, and analytics. For modern REST APIs, **prefer the Authorization header**.

### 14.1. A Bad Header Does Not Mean an Expired Token

Example:

```http
Authorization: Bearer
```

A header with no token value can cause a request error or prevent the resolver from extracting a token, depending on how the parser/filter behaves. When investigating, distinguish:

- Actually invalid/expired token.
- Syntactically invalid Authorization header.
- Client failing to send the header due to proxy/CORS/HTTP client bugs.
- Sending credentials in a location unsupported by the resolver.
- Sending multiple tokens/multiple transport methods against the contract.

If the request is judged malformed, the `invalid_request` branch may make more sense than `invalid_token`.

### 14.2. Do Not Log the Authorization Header

`Authorization: Bearer ...` contains a reusable credential. Logging the raw header risks exposing access rights.

Instead, log:

```text
request_id=req-123
http_path=/api/orders/{id}
authn_result=FAILED
reason=INVALID_BEARER_REQUEST
bearer_present=true
```

Never log raw tokens, query tokens, or sensitive payloads.

## 15. Check Issuer/Audience Before Treating a Token as Valid

A JWT:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "aud": ["payments-api"],
  "scope": "orders.read"
}
```

may be signed by a trusted AS, yet **is not intended for the Orders API**. If the Orders API requires audience `orders-api`, the decoder/validator must reject the token before HTTP authorization, resulting in a Bearer authentication failure.

Never configure the entry point to return 403 to mask a decoder that failed to validate audience. HTTP error formatting cannot fix trust boundaries.

With opaque tokens, introspection may return `active=true`; the Resource Server may still need to verify audience/client/tenant per contract via an `OpaqueTokenIntrospector` wrapper. If that fails, it is still an authentication/token-contract failure.

### 15.1. An OIDC ID Token Is Not an API Access Token

A validly signed OIDC ID token is usually meant for an **OIDC client** and has the client ID as its audience, not the Resource Server. An API should not accept an ID token as a bearer access token merely because they share an issuer. Check token type/profile and expected audience in the decoder or introspection contract.

When an ID token is sent by mistake and fails the Resource Server contract, the response is typically an authentication failure—not granting access just because `sub` matches a valid user.

## 16. Request with an Old Token: Should the Client Refresh Immediately?

A client may receive:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

This case **might** be caused by token expiration, and an OAuth client may need to run an appropriate token refresh flow if it holds a refresh token and the AS supports it. However, `invalid_token` can also be caused by:

- Bad signature.
- Mismatched issuer/audience.
- Revoked token.
- Token not intended for the Resource Server.
- Malformed token.
- Clock skew or key rotation issues.
- AS/Resource Server validation contract changes.

Therefore:

- Do not automatically refresh tokens **infinitely** on every 401.
- Do not replay the exact same token infinitely.
- Do not assume `403 insufficient_scope` will be fixed by refreshing if there is no flow to grant extra scopes.
- OAuth clients should enforce safe retry/refresh policies; Resource Servers simply return accurate statuses.
- Never pass refresh tokens to a Resource Server unless a specific protocol and architecture intentionally allow it; normally refresh tokens belong to the client/AS token endpoint.

### 16.1. Avoid Turning Challenges into Login Redirects

For machine-to-machine and SPA/mobile API clients, a `302 /login` returning HTML is rarely useful when the resource is protected by Bearer tokens. If an app combines form login and Resource Server, configure a dedicated SecurityFilterChain for the API so the entry point returns HTTP Bearer challenges.

## 17. CORS, Frontends, and Reading `WWW-Authenticate`

A cross-origin web frontend may call the Orders API using Fetch:

```javascript
const response = await fetch("https://api.example.test/api/orders/42", {
  headers: {
    Authorization: "Bearer " + accessToken
  }
});

if (response.status === 401) {
  // Per OAuth client contract: handle login/token refresh appropriately.
}
```

On cross-origin requests, CORS policy affects whether the frontend can read the response:

- The Resource Server must allow appropriate origins/methods/headers.
- The browser may send an **OPTIONS preflight** due to the Authorization header.
- If the frontend needs to read `WWW-Authenticate` in JavaScript, the CORS response may need `Access-Control-Expose-Headers: WWW-Authenticate`.
- Even when the browser is allowed to read the challenge, that **does not replace API authentication/authorization**.

### 17.1. CORS Preflight Is Not Bearer Authentication

Preflights typically do not carry a bearer token:

```http
OPTIONS /api/orders/42
Origin: https://app.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

If preflights are protected like business requests requiring tokens, the browser may never send the real request. Spring Security CORS configuration usually needs to handle preflights before requiring Bearer auth.

A CORS policy must restrict origins, methods, and headers per contract; do not blindly set `OPTIONS /** permitAll` for everything without understanding the API.

### 17.2. Expose Headers Justifiably

Partial CORS config illustration:

```java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of("https://app.example.test"));
cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
cors.setExposedHeaders(List.of("WWW-Authenticate"));
```

Imports:

```java
import java.util.List;
import org.springframework.web.cors.CorsConfiguration;
```

Configuring `CorsConfigurationSource` and integrating `http.cors(...)` depends on application structure. Expose headers only to permitted origins; never treat CORS as a user authorization mechanism.

## 18. When Multiple SecurityFilterChains Exist

An application may have a Bearer API and a form-login web UI:

```text
/api/**        -> JWT Resource Server, Bearer challenge
/web/**        -> Session/Form login
/public/**     -> Public routes
```

If a catch-all chain with form login precedes the API chain, `/api/orders` requests may be routed to HTML login instead of returning a Bearer challenge.

### 18.1. Distinguishing `securityMatcher` from `requestMatchers`

- `http.securityMatcher("/api/**")`: selects which requests enter the **entire filter chain**.
- `authorizeHttpRequests(...).requestMatchers(...)`: selects authorization rules **within that chain**.

Example:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
```

Additional import:

```java
import org.springframework.core.annotation.Order;
```

Another chain is needed to protect the rest where appropriate. If a request matches no chain, Spring Security may leave that request unprotected. `anyRequest().denyAll()` in a chain that only matches `/api/**` **does not protect the entire application**.

### 18.2. Avoid Using Web Entry Points for APIs

If an API request missing a bearer token receives a 302/HTML, check:

1. Which chain did the request enter?
2. Is `@Order` between chains correct?
3. Does `securityMatcher` match the exact servlet path?
4. Is form login, HTTP Basic, or a global exception handler overriding the Bearer entry point?
5. Is a reverse proxy stripping/transforming the Authorization header?

Do not fix this by adding a custom controller returning 401 when the wrong filter chain is being selected.

## 19. Gateways, Proxies, and Header Propagation

A Resource Server may sit behind an API gateway:

```text
OAuth client
    |
    v
API Gateway / reverse proxy
    |
    v
Spring Security Resource Server
```

Common issues:

- Gateway **strips the Authorization header** before forwarding to the API.
- Gateway authenticates and injects identity headers while the backend still expects a Bearer token.
- Gateway returns its own `401` without `WWW-Authenticate`.
- Gateway rewrites body/status and drops the Bearer challenge.
- Gateway mistakenly caches 401/403 responses.
- WAF blocks tokens or flags the header as an anomalous payload.

When investigating, identify **which response came from the gateway and which came from Spring Security**. Never blame `BearerTokenAuthenticationEntryPoint` solely based on an external client response.

### 19.1. Do Not Trust Identity Headers Without a Trust Boundary

If the gateway validates tokens and forwards `X-User-Id` to the backend, enforce a trust mechanism between gateway and backend (network isolation, mTLS, header sanitization, and proper policy). Never accept an `X-User-Id` sent by an Internet client to bypass Bearer authentication.

### 19.2. Do Not Expose Bearer Tokens in Access Logs

Avoid logging `Authorization` at the gateway or backend, and avoid passing tokens in query strings. Error headers and JSON bodies must never echo tokens.

## 20. `WWW-Authenticate` and the API Error Body Are Two Distinct Contracts

Suppose an organization defines a JSON response:

```json
{
  "code": "AUTH_REQUIRED",
  "message": "Authentication is required",
  "requestId": "req-123"
}
```

The response may be:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Content-Type: application/json
```

An HTTP Bearer-compliant client can inspect the header; a frontend can inspect the JSON body. Both must be designed **consistently in status**.

### 20.1. Why Not Return 200 with an Error Field?

Wrong:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"error":"invalid_token"}
```

HTTP status 200 indicates request success at the HTTP layer, misleading clients, caches, monitoring, and retry logic. Authentication failures need proper HTTP statuses, not just a field in JSON.

### 20.2. Why Not Return 403 for Every Request Missing a Token?

`403 Forbidden` normally expresses that the server refuses to fulfill a request even though the caller is authenticated but lacks permission. When **no Authentication is present** on a protected API, a `401` challenge is the proper message telling the client to present credentials.

### 20.3. When Is RFC 9457 Problem Details Needed?

If an organization standardizes API errors on Problem Details, you can use media type `application/problem+json` with `type`, `title`, and `status` fields. Even then, this body **still does not replace `WWW-Authenticate`** in Bearer authentication.

Any custom entry point should preserve status/headers first, then add safe JSON information if needed.

## 21. Logging, Monitoring, and Avoiding Information Leaks

A Resource Server should observe:

| Signal | Meaning |
|---|---|
| HTTP 401 rate by route | Detects callers with missing/bad credentials |
| `invalid_request` rate | Indicates malformed Bearer headers or transport bugs |
| `invalid_token` rate | May indicate expired tokens, wrong issuer/audience, or bad signatures |
| 403 rate | Tokens validate but lack permissions |
| JWKS/introspection HTTP errors | Possible AS infrastructure or network outage |
| JWT/introspection validation time | Latency/availability metric |
| Request ID and API version | Correlates traces without exposing bearer tokens |

Safe log example:

```text
request_id=req-74aa
route=GET /api/orders/{id}
authentication_result=FAILED
error_category=INVALID_TOKEN
bearer_present=true
http_status=401
```

Do not log:

```text
Authorization: Bearer <RAW_ACCESS_TOKEN>
client_secret=<INTROSPECTION_SECRET>
jwt_payload=<SENSITIVE_CLAIMS>
```

Those fields may contain credentials or personal data. If debugging issuer/audience, gather info from controlled internal decoder/logs—never print raw tokens in error responses.

### 21.1. Avoid Overly Detailed error_description

Do not give clients details such as:

- Private key filenames or key material.
- Lists of internal infrastructure paths.
- Client secrets or introspection credentials.
- Full expected sensitive tenant claims.
- Raw exceptions/stack traces.
- Information confirming an unauthorized user/object exists.

Clients usually only need to know the token was not accepted or permissions are insufficient. Diagnostic details can be recorded in secured logs keyed by request ID.

## 22. MockMvc: Testing Bearer Challenges When Missing a Token

HTTP behavior can be tested using Spring Boot Test and Spring Security Test.

Example app configuration protecting `GET /api/orders/**`. When no token is sent:

```java
@SpringBootTest
@AutoConfigureMockMvc
class BearerChallengeTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void missingTokenReturnsBearerChallenge() throws Exception {
        mockMvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                startsWith("Bearer")
            ));
    }
}
```

Imports:

```java
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
```

This test confirms that missing Authentication on a protected route leads to `401` and an appropriate challenge **provided the Resource Server/SecurityFilterChain config is loaded properly**.

If the application has multiple filter chains, test the exact request/servlet path and verify the Bearer chain is selected.

### 22.1. Which Test Cases Are Needed?

| Test case | Expected HTTP | Header |
|---|---|---|
| No token, protected endpoint | `401` | Bearer challenge |
| No token, public endpoint | Per public API, usually `200` | No Bearer challenge needed |
| Expired token | Usually `401` | Possibly `error="invalid_token"` |
| JWT wrong issuer/audience | Usually `401` | Appropriate Bearer challenge |
| Malformed Bearer request | Possibly `400` | Possibly `error="invalid_request"` |
| Valid token, missing scope | `403` | AccessDeniedHandler/Bearer semantics |
| Valid token, has scope, wrong owner | `403` or `404` | Per business policy |
| Valid access token, sufficient permissions | Business status | No authentication challenge needed |

Testing missing tokens alone is not enough to prove JWT signature/issuer/audience validation. Those scenarios require configuring an appropriate decoder/introspector and real test tokens or targeted mocks.

### 22.2. Why Is `jwt()` in Spring Security Test Not Enough?

Spring Security Test can mock an Authentication:

```java
mockMvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
```

This snippet illustrates an authorization test, yet `jwt()` **usually bypasses real JWT signature verification**. To test `BearerTokenAuthenticationEntryPoint` on bad signatures/expired tokens, send requests through an appropriate decoder or stub the decoder to throw exceptions as designed.

Also, §status().isOk()§ is only valid if the controller/service/test fixtures actually return HTTP 200 after authorization.

## 23. Testing the Entry Point Directly: Header and Status

You can unit test the entry point without running the entire Servlet filter chain.

Example with Spring mock servlet request/response:

```java
@Test
void entryPointSetsBearerRealmForMissingAuthentication()
        throws Exception {

    BearerTokenAuthenticationEntryPoint entryPoint =
        new BearerTokenAuthenticationEntryPoint();

    entryPoint.setRealmName("orders-api");

    MockHttpServletRequest request = new MockHttpServletRequest();
    MockHttpServletResponse response = new MockHttpServletResponse();

    AuthenticationException exception =
        new InsufficientAuthenticationException(
            "Authentication is required"
        );

    entryPoint.commence(request, response, exception);

    assertEquals(401, response.getStatus());
    assertEquals(
        "Bearer realm=\"orders-api\"",
        response.getHeader(HttpHeaders.WWW_AUTHENTICATE)
    );
}
```

Imports:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.InsufficientAuthenticationException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
```

This tests the entry point's response formatting. It **does not prove** the API route matched the right filter chain, the decoder validates tokens properly, or RBAC/ABAC is fully implemented.

### 23.1. A Test for invalid_token

You can create an exception containing a `BearerTokenError`:

```java
@Test
void invalidTokenProducesBearerError() throws Exception {
    BearerTokenAuthenticationEntryPoint entryPoint =
        new BearerTokenAuthenticationEntryPoint();

    MockHttpServletResponse response = new MockHttpServletResponse();

    OAuth2AuthenticationException exception =
        new OAuth2AuthenticationException(
            BearerTokenErrors.invalidToken("Invalid access token")
        );

    entryPoint.commence(
        new MockHttpServletRequest(),
        response,
        exception
    );

    assertEquals(401, response.getStatus());
    assertTrue(
        response.getHeader(HttpHeaders.WWW_AUTHENTICATE)
            .contains("error=\"invalid_token\"")
    );
}
```

Additional imports:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.BearerTokenErrors;
```

Avoid asserting exact character-by-character header equality if the framework might reorder non-essential parameters across versions; prefer checking status and presence of the required scheme/error code.

## 24. Quick Checks with curl

### 24.1. Sending No Token

```bash
curl -i "https://api.example.test/api/orders/42"
```

Expected for a protected API:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

May include `realm` if configured.

### 24.2. Sending an Invalid Token

```bash
curl -i \
  -H "Authorization: Bearer invalid-token" \
  "https://api.example.test/api/orders/42"
```

Typically:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Depending on decoder, resolver, and exception flow, error description/headers may differ. Never use production bearer tokens in terminal history or logs.

### 24.3. Valid Token Missing Permissions

```bash
curl -i \
  -H "Authorization: Bearer <VALID_TOKEN_WITHOUT_orders.read>" \
  "https://api.example.test/api/orders/42"
```

Usually `403 Forbidden`. Even when receiving `403`, verify the token was genuinely validated by the decoder and route policy applied the right rule.

### 24.4. Distinguishing Gateway Errors from Spring Security Errors

If curl to the gateway receives 401 while internal curl in the test environment to the Resource Server does not, check whether the gateway rewrites/deletes `WWW-Authenticate`, drops the Authorization header, or returns its own challenge. Never blame `BearerTokenAuthenticationEntryPoint` based solely on an external response.

## 25. Common Design Mistakes

### Mistake 1 — Returning 200 with JSON for Every Failure

```http
HTTP/1.1 200 OK
{"error":"invalid_token"}
```

Misleads clients/caches/monitoring. Use proper HTTP status codes.

### Mistake 2 — Returning 401 Without `WWW-Authenticate`

Bearer clients receive no challenge. Use `BearerTokenAuthenticationEntryPoint` or delegate to it when adding a JSON body.

### Mistake 3 — Returning `invalid_token` When No Token Exists

If the caller sent no credentials, `WWW-Authenticate: Bearer` is usually the proper challenge; do not claim a token is invalid.

### Mistake 4 — Turning Missing Scope into an Invalid Token

A token with `orders.read` but missing `orders.export` can still be used on other read endpoints. Return `403` per authorization instead of emitting `401 invalid_token`.

### Mistake 5 — Dropping Audience Validation to Reduce 401s

A token for the Payments API must never become valid for the Orders API. A 401 caused by wrong audience must be solved in the token request/AS config/Resource Server contract, not in the error handler.

### Mistake 6 — Using `@ControllerAdvice` to Catch All Security Errors

Many security failures happen in the filter chain before MVC, so controller advice will not necessarily receive them. Configure `AuthenticationEntryPoint` and `AccessDeniedHandler` properly.

### Mistake 7 — Custom Entry Point Loses `invalid_request` Status

If the delegate determines `400` while custom code always runs `response.setStatus(401)`, the API loses the distinction between malformed requests and invalid tokens. Preserve the delegate's status or map intentionally per contract.

### Mistake 8 — Logging Bearer Headers for “Quick Debugging”

Access tokens are credentials. Keep them out of stdout, APM, exception messages, HTTP access logs, or tickets.

### Mistake 9 — Letting Form Login HTML Redirects Replace Bearer Challenges

Often caused by a web chain preceding the API chain. Separate security matchers and priorities.

### Mistake 10 — Confusing Realm with Issuer

`realm="orders-api"` cannot replace checking `iss`, `aud`, signatures, or introspection.

### Mistake 11 — Forcing Bearer Authentication on CORS Preflights

The browser may fail to send the actual request. Configure CORS to handle preflights properly.

### Mistake 12 — Client Refreshes Infinitely After 401

Not every `invalid_token` is expiration. Bound retries/refreshes and classify errors.

### Mistake 13 — Echoing Exception Details to the Client

Never expose expected private claims, sensitive key IDs, internal network endpoints, object subject/tenant, or stack traces.

### Mistake 14 — Allowing Tokens Just Because JWKS/Introspection Is Unavailable

An infrastructure outage does not prove a token is valid. Must fail closed; operational responses can be handled separately without fabricating a fake Authentication.

## 26. Practical Decision Model for the Orders API

Suppose the Orders API serves both a frontend and service integrations.

Policy:

```text
Authentication contract:
  - Bearer access token required for /api/**
  - JWT signature or opaque introspection must pass
  - issuer must be trusted
  - audience must contain orders-api
  - token must be active/not expired

HTTP authorization:
  GET /api/orders/**  -> SCOPE_orders.read
  POST /api/orders    -> SCOPE_orders.write
  POST /api/orders/*/cancel -> SCOPE_orders.cancel

Object authorization:
  - Only orders visible by subject/tenant/ACL
  - Bulk list and export filtered to allowed resources

Error contract:
  - No token: 401 + WWW-Authenticate: Bearer realm="orders-api"
  - Invalid token: 401 + Bearer error="invalid_token"
  - Malformed Bearer request: use RFC 6750 error semantics
  - Valid token, missing authority: 403
  - Object not visible: 403 or 404 consistently
```

This structure separates **authentication challenges**, **action permissions**, and **business object permissions**. Changing the response format does not alter the policy.

## 27. References

- [Spring Security — BearerTokenAuthenticationEntryPoint API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html): `commence(...)` method, Bearer challenges, and realm.
- [Spring Security — BearerTokenAccessDeniedHandler API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/access/BearerTokenAccessDeniedHandler.html): handling AccessDeniedException in Bearer Resource Servers.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT configuration, Bearer authentication, and mapping scopes to authorities.
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection and authentication for opaque tokens.
- [Spring Security — Exception Handling](https://docs.spring.io/spring-security/reference/servlet/architecture.html): Spring Security filter ordering and exception handling.
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer scheme, `WWW-Authenticate`, and error codes.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): 401/403 status codes and HTTP authentication challenges.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): machine-readable error responses when an API needs a JSON error contract.

**Conclusion:** `BearerTokenAuthenticationEntryPoint` is the key component enabling a Resource Server to send a **Bearer challenge when a request lacks a valid Authentication**, typically via `401 Unauthorized` and `WWW-Authenticate: Bearer`. When the exception carries a `BearerTokenError`, it can emit appropriate Bearer error parameters such as `invalid_token` or `invalid_request`. **Insufficient permissions on a valid token** belong to the authorization branch, typically handled by `BearerTokenAccessDeniedHandler` with `403`. A well-built API preserves accurate HTTP statuses and challenge headers, avoids leaking credentials, and cleanly separates authentication, scope authorization, and business object permissions.
