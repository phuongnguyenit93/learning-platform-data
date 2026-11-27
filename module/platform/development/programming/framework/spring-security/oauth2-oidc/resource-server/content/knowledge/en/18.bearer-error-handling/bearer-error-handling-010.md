# Limiting Error Details to Avoid Leaking Tokens, Keys, or Internal Configuration

## 1. Why Are Security Errors Also Part of the Attack Surface?

In **Spring Security OAuth 2.0/OIDC Resource Server**, the application receives a Bearer access token, verifies the credential, and decides API access rights. When an error occurs, the HTTP response must provide enough information for the client to react properly while **never becoming a channel that leaks tokens, keys, secrets, internal topology, or user data**.

Imagine a client sends:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6...
```

If the JWT signature is invalid, the Resource Server must reject it. However, the response must not be:

```json
{
  "error": "JWT signature verification failed",
  "rawToken": "eyJhbGciOiJSUzI1NiIsImtpZCI6...",
  "issuerJwksUri": "https://internal-idp.svc.cluster.local/keys",
  "expectedKid": "prod-signing-2026-11",
  "stackTrace": "com.example.security.JwtVerifier..."
}
```

The snippet above is an **intentionally insecure example**: a single authentication error exposed the caller's credential, deployment topology, key management info, and internal Java classes.

A better response for an invalid Bearer token:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Cache-Control: no-store
```

Public info only confirms **the token was not accepted**. Specific reasons such as bad signature, expired token, wrong issuer, or missing key can be recorded in **protected, sanitized internal security logs** instead of being exposed via `error_description` or the body.

> **Dual goal:** follow the Bearer protocol so clients know how to react, while bounding error data under the **minimum necessary disclosure** principle. Clients do not need private keys, internal JWKS URLs, issuer configurations, token payloads, or stack traces to handle an HTTP 401.

## 2. Classifying Recipients of Error Information

An error can be observed in multiple places; each place has different limits:

| Recipient | Appropriate Information | Information to Remove or Restrict |
| --- | --- | --- |
| **OAuth client** | HTTP status, Bearer challenge, standard error code, non-sensitive request/correlation ID. | Raw access token, refresh token, client secret, private key, token payload, stack trace. |
| **End user** | “Session is invalid or expired” or “You do not have permission to perform this action”. | JWKS addresses, internal `kid`, policy groups, token introspection details. |
| **API gateway / reverse proxy** | Status, public route ID, correlation ID, and permitted diagnostic metadata. | `Authorization` header, cookies, query tokens, sensitive exception bodies. |
| **Internal application logs** | Normalized error code, phase, request ID, permitted issuer identifier, latency. | Verbatim tokens, secrets, keys, or unnecessary PII claims. |
| **System security audit** | Event type, *verified* actor/issuer, relevant source/context, allow/deny decision. | Unverified input treated as true identity, secrets, full tokens. |
| **Metrics/tracing** | 401/403 counts, low-cardinality error categories, verification latency, introspection results. | Raw tokens, emails, arbitrary subjects, unverified `kid`s, or exception messages as metric labels. |
| **User support channels** | Incident reference code, timestamp, and generic endpoint. | Asking customers to paste access tokens/private keys into tickets or chats. |

**An error may need thorough investigation server-side yet require only a short response client-side.** Never turn HTTP responses into copies of debug logs.

## 3. RFC 6750: Bearer Challenges and Standard Error Codes

**RFC 6750 — OAuth 2.0 Bearer Token Usage** defines how Bearer tokens are used and how `WWW-Authenticate` is structured when the Resource Server requires or rejects credentials.

Three common errors:

| Error Code | Typical Meaning | HTTP Status Under RFC 6750 |
| --- | --- | --- |
| `invalid_request` | Token/request transmission violates protocol: malformed credential, conflicting multiple token methods, or syntax error. | Usually **400 Bad Request**. |
| `invalid_token` | Access token rejected: expired, revoked, malformed, bad signature, wrong issuer/audience, or invalid per contract. | **401 Unauthorized**. |
| `insufficient_scope` | Valid token lacking required permission for the resource/action. | **403 Forbidden**. |

An API may also return **401 when no credential is sent**, typically with a Bearer challenge **without an `error` code**.

### 3.1. No Bearer Credential Sent

```http
GET /api/orders HTTP/1.1
Host: api.example.test
```

Typical response:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
```

Per RFC 6750, when a request **contains no authentication information**, the Resource Server should not include detailed error codes that mislead the client into thinking it sent a token that failed verification.

### 3.2. Bearer Token Present but Rejected

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
```

The client understands the supplied credential was rejected; depending on the flow, it can request a new access token, prompt re-login, or stop calling the API. It **does not need** to know which key failed or the exact `exp` claim in the response.

### 3.3. Valid Token Lacking Permissions

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
```

This is not a case where the client should simply retry **the same token** repeatedly. Either an access token with valid permissions under authorization policy is needed, or the user/client lacks that permission.

### 3.4. Syntactically Invalid Bearer Request

```http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer realm="orders-api", error="invalid_request"
```

Exact examples depend on `BearerTokenResolver` and header/form/query token configuration. In a secure model, prefer `Authorization: Bearer` and never enable query-string tokens just for testing convenience.

### 3.5. Not Every 403 Must Be insufficient_scope

An API may deny record ownership, tenant membership, or business policies after authentication succeeds. Those errors are usually **403**, sometimes **404** to limit exposing resource existence, and do not necessarily have to be represented by an `insufficient_scope` Bearer challenge. Only use protocol codes when they accurately reflect the cause and active handler.

## 4. WWW-Authenticate Structure and Information Bounds

A Bearer challenge can carry these parameters:

| Parameter | Role | Safe Public Disclosure Policy |
| --- | --- | --- |
| `realm` | Protected resource space, helping clients distinguish auth zones. | Use a **stable, non-sensitive** name such as `orders-api`. |
| `error` | Machine-readable error code per RFC 6750. | Use defined enum values; never pass arbitrary exception strings as error codes. |
| `error_description` | Short, optional description. | Can be **omitted entirely** or use fixed generic text. |
| `error_uri` | Optional URL explaining the error code. | Point only to **public** docs, never internal consoles or internal paths. |
| `scope` | Optional required scope when denied due to insufficient privileges. | Disclose only if policy permits and clients truly need it; avoid leaking internal permissions. |

Safe example when guiding clients without exposing infrastructure:

```http
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token", error_description="The access token is invalid"
```

**Unsafe** example:

```http
WWW-Authenticate: Bearer error="invalid_token", error_description="The RSA key kid=prod-2026-11 was not found at https://idp-internal.svc.cluster.local/realms/a/certs; token=eyJ..."
```

**`error_description` is client-visible data.** Never pass `exception.getMessage()` directly into it, because errors from decoders/introspection/HTTP clients can hold data never meant for callers.

### 4.1. Realm Is Not a Configuration Endpoint

`realm="orders-api"` does not have to be an `issuer-uri`, JWKS URI, or Authorization Server URL. Never expose internal endpoints just to make challenges “more helpful”.

If clients need login/Authorization Server details, publish them through **API docs or permitted public discovery**; never dump runtime configuration into errors.

### 4.2. error_uri Is Not a Carrier for Dynamic Error Data

An appropriate `error_uri` might be a documentation page:

```text
https://docs.example.test/api/errors#invalid-token
```

Do not use:

```text
https://debug.internal.example.test/?token=<raw-access-token>&secret=<client-secret>
```

URLs can be recorded in history, proxies, access logs, referrers, or monitoring tools. Query strings containing tokens/secrets are an obvious leak vector.

### 4.3. Encoding Rules and Header Injection

`WWW-Authenticate` is a structured HTTP header. Never append any client-controlled message into header values without proper validation/escaping:

```java
// WRONG: error message may come from libraries or untrusted input.
response.setHeader(
        "WWW-Authenticate",
        "Bearer error_description=\"" + exception.getMessage() + "\"");
```

Beyond internal data, strings with quotes, newlines, or control characters can break header syntax or enable log/header injection if an implementation handles them poorly.

The simplest safeguard is **fixed values from an allowlist**, delegating challenge formatting to Spring Security handlers designed for Bearer.

## 5. What Information Must Never Appear in Errors?

### 5.1. Tokens and Credentials

Never emit in responses, headers, logs, traces, or public exception messages:

- **Access tokens**, even expired JWT strings or ones with bad signatures.
- **Refresh tokens**, authorization codes, device codes, and session credentials.
- Full `Authorization` headers, HTTP Basic credentials, and cookies.
- Introspection **client secrets**, client assertion private keys, or mTLS private keys.
- Client secrets of other OAuth clients if present in configuration.
- KMS/HSM key material, JWK private fields such as RSA `d`, EC private `d`, or HMAC secret `k`.

An expired JWT is **still sensitive data**: the payload may hold claims, subject, tenant, audience, and personal data; tokens can be replayed within clock-skew windows or used to analyze system behavior.

### 5.2. Configuration and Topology That Need Not Be Disclosed

Examples:

- Internal `issuer-uri`, JWKS URI, introspection URI, and service discovery hosts.
- Kubernetes namespaces, cluster URLs, pod/host names, and internal ports.
- Keystore paths, secret mount paths, or configuration file paths.
- Environment variable names holding sensitive values, stack traces, and implementation class names.
- Detailed `kid`/`alg`/trust policy internals unless required by client contracts.
- Tenant lists, internal role/group mappings, and policy rules.

Not every issuer URL or `kid` is secret by standard: public JWKS and issuer metadata may be legitimately public. Yet **HTTP authentication errors should not volunteer extra internal topology or cryptographic decisions** beyond what the API contract permits.

### 5.3. Personal Data and Claims from Tokens

Never include in error responses:

```text
sub=user-123; email=linh@example.test; tenant_id=tenant-secret;
preferred_username=linh; roles=[finance-admin]
```

In particular, claims read from an **unverified token** are purely caller-supplied data. Never respond with “user linh@example.test does not exist” based on an unverified JWT payload. That creates a user-enumeration and account-status oracle.

## 6. Which Layer Failed? Not Every Detail Should Go External

The Resource Server authentication/authorization chain has multiple steps:

```mermaid
flowchart TD
    C["HTTP request"] --> B["BearerTokenResolver"]
    B -->|"No credential"| N["401 + minimal Bearer challenge"]
    B -->|"Invalid request structure"| BR["400 invalid_request"]
    B -->|"Bearer token string"| A["AuthenticationManager"]
    A --> D["JwtDecoder or OpaqueTokenIntrospector"]
    D -->|"Bad signature/issuer/aud/exp or inactive"| E["401 invalid_token"]
    D -->|"Authentication succeeded"| AU["GrantedAuthorities + Authorization"]
    AU -->|"Missing scope"| F["403 / insufficient_scope if appropriate"]
    AU -->|"Object/tenant denied"| G["403 or domain 404 per policy"]
    AU -->|"Sufficient permissions"| OK["Controller + domain logic"]
```

Internal errors should carry a **phase** so operations can investigate accurately:

| Internal Phase | Example Error | Sufficient Public Response |
| --- | --- | --- |
| `bearer-extraction` | Header missing scheme, malformed Bearer credential, conflicting multiple token methods. | 400 `invalid_request` or 401 challenge depending on protocol case. |
| `jwt-parse` | JWT missing segments, invalid Base64URL, invalid JSON. | 401 `invalid_token`. |
| `jws-verification` | Signature mismatch, disallowed `alg`, `kid` finds no candidate key. | 401 `invalid_token`. |
| `claim-validation` | Expired token, wrong issuer/audience, wrong token profile. | 401 `invalid_token`. |
| `opaque-introspection` | AS returns `active:false`. | 401 `invalid_token`. |
| `introspection-dependency` | Timeout, TLS error, AS HTTP 5xx, or wrong Resource Server client secret. | Fail-closed; safe operational error response, possibly 5xx/503 per handler. |
| `scope-authorization` | Valid token lacking endpoint permission. | 403; `insufficient_scope` when semantically accurate. |
| `object-authorization` | Actor does not own record or belong to tenant. | 403/404 per API policy; never reveal true owner. |
| `application-failure` | NullPointerException, database down, serialization error. | Generic 5xx; no stack trace/SQL. |

These phase names are **examples of internal taxonomy**, not new HTTP Bearer error codes. Never return `"jws-verification"` or `"introspection-dependency"` to clients as a standard OAuth 2.0 code.

### 6.1. Dependency Failures Are Not Invalid Tokens

When the Resource Server cannot reach the introspection endpoint or download JWKS due to network errors, **there is insufficient evidence to accept the token**. It must fail closed. Operationally, however, the cause is dependency unavailability—do not audit it as “user sent a fake token”.

A generic 5xx/503 response can make sense when exception handling distinguishes infrastructure failures; some framework configurations may turn authentication-phase errors into 401. What matters is **leaking no internal info**, **never creating a fake principal**, and **not mislabeling the root cause in telemetry**.

## 7. How Does Spring Security Handle Bearer Authentication Errors?

In Servlet Resource Server, common components include:

| Component | Responsibility |
| --- | --- |
| `BearerTokenAuthenticationFilter` | Extracts tokens, calls AuthenticationManager, and handles certain authentication errors directly in the filter. |
| `DefaultBearerTokenResolver` | Locates Bearer tokens in requests per policy. |
| `JwtAuthenticationProvider` / `OpaqueTokenAuthenticationProvider` | Authenticates credentials using a decoder or introspection. |
| `JwtDecoder` / `OpaqueTokenIntrospector` | Verifies tokens and metadata per trust contract. |
| `BearerTokenAuthenticationEntryPoint` | Builds Bearer challenges when authentication is needed or fails. |
| `BearerTokenAccessDeniedHandler` | Handles access denied for Bearer resources and emits matching challenges. |
| `ExceptionTranslationFilter` | Translates certain downstream `AuthenticationException`/`AccessDeniedException` instances into HTTP responses. |
| `AuthorizationFilter` / Method Security | Makes authorization decisions after authentication. |

Related exceptions:

- `OAuth2AuthenticationException`: OAuth 2.0 error carrying an `OAuth2Error`.
- `InvalidBearerTokenException`: rejected Bearer token.
- `BadJwtException`, `JwtValidationException`, and `JwtException` subtypes: JWT parsing/signature/claim errors.
- `BadOpaqueTokenException`: rejected opaque token.
- `OAuth2IntrospectionException`: introspection or protocol failures.
- `AccessDeniedException`: principal is not permitted to perform the action.

**Never forward raw exception messages.** Parser messages can contain JWT fragments, claims, `kid`s, or endpoints; HTTP client messages can contain AS statuses/bodies or request URIs. Process those strings only inside sanitized telemetry.

### 7.1. BearerTokenAuthenticationEntryPoint

Standard handler:

```java
BearerTokenAuthenticationEntryPoint entryPoint =
        new BearerTokenAuthenticationEntryPoint();
entryPoint.setRealmName("orders-api");
```

`setRealmName` configures a stable realm containing no secrets. The handler interprets `OAuth2AuthenticationException` carrying a `BearerTokenError` to set HTTP status and Bearer challenge.

If the application itself throws:

```java
throw new OAuth2AuthenticationException(
        BearerTokenErrors.invalidToken(
                "JWT failed to validate: issuer=https://internal..."));
```

then sensitive details are already placed inside `OAuth2Error.description` and may surface in `error_description`. **Therefore, avoid using sensitive info as public descriptions right at the point where errors are created**.

## 8. Minimal Default Configuration and Distinguishing 401/403

Example Servlet JWT Resource Server configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.web
        .BearerTokenAccessDeniedHandler;
import org.springframework.security.oauth2.server.resource.web
        .BearerTokenAuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        BearerTokenAuthenticationEntryPoint entryPoint =
                new BearerTokenAuthenticationEntryPoint();
        entryPoint.setRealmName("orders-api");

        BearerTokenAccessDeniedHandler denied =
                new BearerTokenAccessDeniedHandler();
        denied.setRealmName("orders-api");

        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .authenticationEntryPoint(entryPoint)
                        .accessDeniedHandler(denied)
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
```

This example uses familiar modern Spring Security Servlet APIs. To run in a real project, you still must configure a **`JwtDecoder` trusting the issuer/JWKS, verifying audience and token profile**, appropriate dependencies, and a matching CSRF policy.

If the API uses opaque tokens, replace `.jwt(...)` with `.opaqueToken(...)` and configure introspection per contract. The **non-disclosure** principle remains identical.

Note: configuring the entry point/denied handler **does not automatically guarantee every error description is harmless** if upstream exceptions carry sensitive content. When strict bounds are needed, **sanitize `OAuth2Error` values before passing them to the handler** or return only allowlisted fields.

## 9. Creating an AuthenticationEntryPoint That Emits Safe Bearer Challenges

A practical policy may decide:

- Request with no credential: return only `Bearer realm="orders-api"`.
- Malformed Bearer request: return `invalid_request` with a fixed description.
- Token present, authentication failed: return `invalid_token` with a fixed description.
- Never return raw `exception.getMessage()`, stack traces, tokens, `kid`, JWKS, or introspection URIs.

Wrapper example using Spring Security's Bearer handler to format challenges:

```java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.BearerTokenErrorCodes;
import org.springframework.security.oauth2.server.resource.BearerTokenErrors;
import org.springframework.security.oauth2.server.resource.web
        .BearerTokenAuthenticationEntryPoint;
import org.springframework.security.web.AuthenticationEntryPoint;

@Bean
AuthenticationEntryPoint safeBearerEntryPoint() {
    BearerTokenAuthenticationEntryPoint delegate =
            new BearerTokenAuthenticationEntryPoint();
    delegate.setRealmName("orders-api");

    return (request, response, exception) -> {
        if (exception instanceof OAuth2AuthenticationException oauth) {
            // Use only allowlisted error codes; discard original message/description.
            String code = oauth.getError().getErrorCode();

            OAuth2AuthenticationException safe =
                    BearerTokenErrorCodes.INVALID_REQUEST.equals(code)
                            ? new OAuth2AuthenticationException(
                                    BearerTokenErrors.invalidRequest(
                                            "Invalid Bearer request"))
                            : new OAuth2AuthenticationException(
                                    BearerTokenErrors.invalidToken(
                                            "Invalid access token"));

            delegate.commence(request, response, safe);
            return;
        }

        // E.g., request with no credential: keep generic Bearer challenge.
        delegate.commence(request, response, exception);
    };
}
```

This pattern deliberately **replaces every description originating from `OAuth2AuthenticationException`** with fixed strings. It focuses on 400 `invalid_request` and 401 `invalid_token`; if the system exposes additional OAuth2 error types per contract, design an explicit allowlist and test thoroughly.

**Key points when customizing:**

1. Do not turn every exception into `invalid_token` and lose `invalid_request` semantics from the Bearer resolver.
2. Do not modify the handler so requests **with no token** are described as “invalid token”.
3. Never let `exception.getMessage()` leak into descriptions or bodies.
4. Never call `sendError(status, exception.getMessage())` because servlet containers may render that message in an HTML error page.
5. If using a separate handler for 503 dependency unavailable, route that error type explicitly and still fail closed.
6. Keep challenges RFC-compliant and test against your active clients/frameworks.

### 9.1. Wiring the Handler into Resource Server

```java
@Bean
SecurityFilterChain api(
        HttpSecurity http,
        AuthenticationEntryPoint safeBearerEntryPoint)
        throws Exception {

    BearerTokenAccessDeniedHandler denied =
            new BearerTokenAccessDeniedHandler();
    denied.setRealmName("orders-api");

    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/api/orders/**")
                        .hasAuthority("SCOPE_orders:read")
                    .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                    .authenticationEntryPoint(safeBearerEntryPoint)
                    .accessDeniedHandler(denied)
                    .jwt(Customizer.withDefaults()))
            .build();
}
```

This example is an **alternative** to the `SecurityFilterChain` bean in the previous section, not two beans sharing `/api/**` concurrently in one app. With multiple security chains, verify requests actually enter the expected chain and handler.

### 9.2. Why Prefer Spring Handlers Over Manual Header String Concatenation?

Bearer challenges have specific syntax and status conventions. Spring handlers reduce the risk of writing malformed `WWW-Authenticate` headers, though **the application remains responsible for controlling data passed into the handler**. The best approach is usually **sanitizing `OAuth2Error`** and letting Spring build the challenge rather than concatenating exceptions manually.

## 10. AccessDeniedHandler: Insufficient Permission Is Not a Token Error

Once authentication succeeds, Spring Security may deny access due to missing scope or business permissions. `BearerTokenAccessDeniedHandler` is the standard choice for a Bearer Resource Server:

```java
BearerTokenAccessDeniedHandler handler =
        new BearerTokenAccessDeniedHandler();
handler.setRealmName("orders-api");
```

A typical response:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
```

Do not build a response like:

```json
{
  "error": "insufficient_scope",
  "requiredScopes": ["orders:admin", "tenant:root", "finance:write"],
  "currentScopes": ["orders:read", "profile:read"],
  "ownerUserId": "user-456",
  "actualTenant": "tenant-secret"
}
```

That response leaks internal permissions, the principal's privilege set, and the resource owner's identity. To tell the client permissions are lacking, `403` and `insufficient_scope`—or a general scope already published in the API contract—are usually enough.

### 10.1. Should the scope Parameter Be Returned in Challenges?

RFC 6750 allows `scope` alongside `insufficient_scope` to indicate the required scope. Yet it is **optional**, not an obligation to expose your entire policy.

Only disclose scopes belonging to the **public API contract**, e.g.:

```http
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders:read"
```

Never disclose internal rules like `ROLE_SUPER_ADMIN_INTERNAL` or tenant conditions of a specific record. If the API does not wish to disclose scopes, omit this parameter.

### 10.2. Do Not Reflect User/Tenant Info in 403s

Instead of:

```text
User alice@example.test is not a member of tenant "company-acquisition-2026"
```

return:

```text
Access denied.
```

You can record a **predefined policy ID**, verified internal actor ID, and decision in protected audit logs if permitted by policy. Never include unnecessary emails, full tokens, or sensitive tenant names in client responses.

## 11. When Using @ControllerAdvice, Do Not Let Internal Errors Override Bearer Handlers

Some apps implement a global exception handler:

```java
@RestControllerAdvice
class GlobalErrorHandler {

    @ExceptionHandler(Exception.class)
    ResponseEntity<?> handle(Exception ex) {
        return ResponseEntity.status(500)
                .body(Map.of("message", ex.getMessage())); // WRONG
    }
}
```

The bug here is putting the raw exception message directly into the JSON response. That content could include:

- An exposed `Authorization` header from an HTTP client.
- JWK/JWKS URIs, key IDs, or key material.
- Database SQL, table/column names, class names, file paths.
- Introspection URIs and AS error responses.
- Tenant/user data inside policy exceptions.

Most authentication failures happen in the **security filter chain before the controller**, so `@ControllerAdvice` is neither the sole nor proper place to handle them. Still, controller/service exceptions or custom handlers can reach MVC exception resolvers; hence the entire app needs a safe disclosure policy.

A generic template for application errors:

```java
@RestControllerAdvice
class PublicApiErrorHandler {

    @ExceptionHandler(Exception.class)
    ResponseEntity<Map<String, String>> unexpected(Exception ex) {
        // Log server-side per redaction policy, with correlation ID.
        // Never send ex.getMessage() or stack trace to the client.
        return ResponseEntity.status(500)
                .body(Map.of(
                        "code", "INTERNAL_ERROR",
                        "message", "Unable to process the request"));
    }
}
```

This is an **error-content limitation example**, not a complete exception hierarchy design. Real apps need dedicated handlers for validation, not-found, domain access denied, and security exceptions—avoiding catching everything into 500 or losing Bearer challenges.

## 12. RFC 7807 / RFC 9457 Problem Details: Usable, but Keep Minimal

Some APIs standardize response bodies on **Problem Details for HTTP APIs** (RFC 9457, succeeding RFC 7807). This format works for business errors and 5xx:

```json
{
  "type": "https://docs.example.test/problems/access-denied",
  "title": "Forbidden",
  "status": 403,
  "detail": "You are not allowed to perform this action",
  "instance": "/api/orders/42",
  "requestId": "req-7a3c"
}
```

Even with a Problem Details body, **Bearer authentication challenges** still require `WWW-Authenticate` per RFC 6750 when applicable. Problem Details **does not replace the Bearer protocol**.

Things to avoid:

- `detail` must not be taken verbatim from `Exception.getMessage()`.
- `instance` must not include query strings containing `access_token`, `code`, or sensitive data.
- `type` must not point to internal dashboards/stack traces.
- Extensions must not contain `rawToken`, `jwksUri`, `privateKey`, `claims`, or internal config.
- `requestId` is a random/PII-free identifier usable for authorized internal log lookup.

If policy requires **not revealing resource existence**, apply a uniform generic 404 body for “not found or not permitted” and avoid leaking owners on other endpoints.

## 13. Which Channels Can Still Leak Tokens Even When Responses Are Safe?

Suppose the Resource Server returns a clean response:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Access tokens can still leak if surrounding components are configured carelessly.

### 13.1. Reverse Proxy Access Logs

Never log raw headers:

```text
request_headers={"Authorization":"Bearer eyJ..."}
```

Inspect NGINX/Envoy/API gateway/WAF/ingress and APM agents: **do not capture full `Authorization` or `Cookie` headers**. To indicate credential presence, log:

```text
authorization_present=true
authorization_scheme=Bearer
```

Never log token values.

### 13.2. Tokens in URLs / Query Strings

```text
GET /api/orders?access_token=eyJ...
```

Tokens in URLs easily end up in browser history, proxy logs, referrers, caches, or analytics. RFC 6750 warns of the many risks of query-parameter transport; Resource Servers should prefer **Authorization headers** and **leave URI query tokens disabled** unless an explicitly reviewed compatibility requirement exists.

In Spring Security, `DefaultBearerTokenResolver` controls acceptance of URI query parameters and form-encoded bodies. Never relax it just because a client got 401 before fixing how it sends tokens.

### 13.3. Exception Messages from HTTP Clients

A `RestClientResponseException` or introspection HTTP client exception can include response bodies/URLs leaking metadata. Do not throw:

```java
throw new RuntimeException(
        "introspection failed at " + introspectionUri
        + ": " + exception.getMessage());
```

and return it to the client. In internal logs, prefer **error category, upstream status code, duration**, and correlation ID; avoid echoing `token=...` request bodies.

### 13.4. Tracing and OpenTelemetry Baggage

Avoid placing access tokens, Basic headers, refresh tokens, or emails into:

- Trace/span attributes.
- `baggage` or HTTP propagation headers.
- Auto-captured full request/response logs.
- Distributed tracing dashboards.
- HTTP client metric tags.

To record failed authentication, use low-cardinality labels like `auth.outcome=denied` and `auth.reason=jwt_expired` (internal), rather than `auth.token=<raw-token>`.

### 13.5. Test Snapshots, CI Artifacts, and Bug Reports

Integration tests easily print full response bodies, HTTP requests, or tokens on failure. Use **dedicated test credentials**, scrub logs/snapshots, and keep secrets out of assertion failure messages.

Never ask developers to “paste the production token to reproduce” in issue trackers. Use hypothetical tokens, test tokens signed with test keys, or a correlation ID for lookup.

## 14. Logging: Enough to Diagnose, Never a Leak Channel

An example **not to follow**:

```java
try {
    return jwtDecoder.decode(token);
} catch (JwtException ex) {
    log.error("Could not decode token {}: {}", token, ex.getMessage(), ex);
    throw ex;
}
```

This snippet logs both the raw token and exception/stack trace. In production, it creates a repository of JWTs accessible to many ops tools, backups, or centralized log stores.

A minimal logging approach:

```java
try {
    return jwtDecoder.decode(token);
} catch (JwtException ex) {
    log.warn(
            "Authentication denied: phase={}, category={}, requestId={}",
            "jwt-validation",
            "invalid-token",
            requestId);
    throw ex;
}
```

This pattern assumes `requestId` comes from a server-generated/controlled correlation ID system and has been validated. If a request ID arrives from a client-sent header, never use the unvalidated string directly as a log identifier.

### 14.1. Should Internal Stack Traces Be Logged?

It is not “never log stack traces” for every error. For certain **programming bugs** or sanitized infrastructure failures, stack traces may be needed operationally. However:

1. **Do not log stack traces for every invalid token**: attackers can send thousands of bad tokens to cause log flooding.
2. **Do not assume exception messages contain no secrets**: evaluate libraries and configs before logging.
3. Enforce log access control, retention, and auditing.
4. Attach correlation IDs and low-cardinality categories instead of raw inputs.
5. Never put stack traces in response bodies or `WWW-Authenticate`.

### 14.2. Distinguishing Internal Errors Without Returning Reasons to Clients

You can use a taxonomy:

```text
auth.failure.type = JWT_SIGNATURE_INVALID
auth.failure.type = JWT_EXPIRED
auth.failure.type = JWT_AUDIENCE_INVALID
auth.failure.type = JWKS_UNAVAILABLE
auth.failure.type = INTROSPECTION_INACTIVE
auth.failure.type = INTROSPECTION_DEPENDENCY_ERROR
auth.failure.type = INSUFFICIENT_SCOPE
auth.failure.type = OBJECT_ACCESS_DENIED
```

These codes are **internal observability codes**, not `error` names for Bearer challenges. Client-side, many situations still only need `invalid_token`.

### 14.3. Why Not Use kid as an Unbounded Metric Label?

`kid` in a JOSE header may be read before signature verification to select a public key, so it is **unverified at that moment**. Attackers can send thousands of random `kid` values and blow up metric series cardinality. For observability, use only key identifiers belonging to your **controlled trusted key set**, or emit a category value like `key-not-found`.

## 15. JWT Signatures and JWKS: Which Details Should Be Hidden?

Common JWT errors:

- JWS does not have three properly formatted segments.
- `alg` is disallowed by the Resource Server.
- Signature does not match the public key.
- `kid` finds no candidate key in the trusted JWKS.
- JWKS endpoint is unreachable or fails TLS verification.
- Token declares an issuer/audience violating the contract.
- Invalid `exp` or `nbf`.
- Token is an OIDC ID token sent to the API as an access token.

To **untrusted callers**, reveal nothing beyond **the token was not accepted**. Examples:

| Internal Cause | Do Not Return | Return Publicly |
| --- | --- | --- |
| Invalid signature | Public key parameters and expected signature. | `401 invalid_token`. |
| Unknown `kid` | List of all active key IDs. | `401 invalid_token`. |
| Bad JWKS URI | Internal URL and HTTP client stack trace. | Generic auth/service error per policy. |
| Wrong issuer | Full trusted issuer allowlist if not part of API contract. | `401 invalid_token`. |
| Wrong audience | Internal tenant/API names or verbatim token claims. | `401 invalid_token`. |
| Expired token | Full payload and unnecessary exact token timestamps. | `401 invalid_token`, generic description if desired. |
| Disallowed algorithm | Internal algorithm/key policy configuration details. | `401 invalid_token`. |
| ID token confused for access token | Subject/email and full profile claims. | `401 invalid_token`. |

**Never remove validators to cut down 401 errors**. Limiting error details means **adjusting response content**, never weakening token validation rules.

### 15.1. Valid Signature with Wrong Audience Must Still Be Rejected

A JWT signed by a trusted issuer might be meant for `payments-api`, not `orders-api`. The Resource Server still returns `invalid_token` when the token does not target its resource. Never tell the caller “this token belongs to payments tenant X”.

## 16. Opaque Introspection: Never Expose Endpoints, Credentials, or Metadata

With opaque access tokens, the Resource Server calls the AS per RFC 7662:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <introspection-client-credential>
Content-Type: application/x-www-form-urlencoded

token=<caller-access-token>
```

Two sensitive pieces of data appear **in the same request**:

1. Basic credentials authenticating the **Resource Server to the AS**.
2. The **caller's** access token in the form body.

Additionally, the response may contain `sub`, `client_id`, `aud`, `scope`, `email`, and private data. Never write full requests/responses to logs or caller responses.

### 16.1. HTTP 401 from AS Differs from HTTP 401 of the API

**AS returning 401 to an introspection request** can mean:

- Resource Server's client secret is wrong/expired.
- Client ID does not exist or was revoked.
- Misconfigured Basic/client assertion/mTLS.
- Wrong introspection URI or permissions.

This does **not mean** “the user's Bearer token has a bad signature”. The Resource Server must deny access when it cannot introspect, yet internal telemetry must distinguish **client-auth failure** from `active=false`.

Never forward the AS error body:

```json
{
  "error": "invalid_client",
  "client_id": "orders-introspector-prod",
  "endpoint": "https://idp-admin.internal/introspect",
  "detail": "client_secret does not match registration secret_version_12"
}
```

to the API caller. It contains internal Resource Server configuration.

### 16.2. Token active=false

```json
{"active": false}
```

Standard AS responses do not necessarily reveal whether the token was revoked, expired, or never existed. Neither should the Resource Server invent extra details for callers without a contract basis; usually `401 invalid_token` is enough.

### 16.3. Timeout Errors and Fail-Closed Behavior

When the AS times out:

```java
// WRONG: dependency failed, so fabricate a principal to keep the system running.
try {
    return introspector.introspect(token);
} catch (Exception ex) {
    return makeAuthenticatedAdminPrincipal();
}
```

It must **fail closed**. If implementing 503 for dependency unavailability, keep bodies/challenges safe:

```http
HTTP/1.1 503 Service Unavailable
Cache-Control: no-store
Content-Type: application/json

{"code":"AUTH_SERVICE_UNAVAILABLE","message":"Authentication is temporarily unavailable"}
```

This is a **designable operational response pattern**, not the default produced by every Spring Security version. It requires explicitly written exception handlers, tests proving no fallback authentication triggers, and no exposure of endpoint/credential info.

## 17. Do Not Let Spring Boot Error Pages and Actuator Leak Details

If an application has overly permissive error handling in production, 500 or 401/403 responses passing through MVC can expose:

- Exception class and message.
- Binding errors containing sensitive input values.
- Stack traces.
- Debug messages or internal paths.

Common Spring Boot properties to curb response body disclosure:

```yaml
server:
  error:
    include-message: never
    include-stacktrace: never
    include-binding-errors: never
    include-exception: false
```

Depending on Boot version, property names/settings may be managed differently; check your version. These settings protect the **Boot error response layer**, not replacing `BearerTokenAuthenticationEntryPoint`, `BearerTokenAccessDeniedHandler`, or logging policies.

If using Actuator:

- Expose only necessary endpoints via auth/network policies.
- Never expose `/actuator/env`, `/actuator/configprops`, or heap dumps to the public Internet.
- Verify sanitization of property values and secret references in Actuator.
- Protect tracing/heapdump/logfile endpoints because they can hold credentials or request data.

An app is insecure if 401s are scrubbed clean yet anyone can download a heap dump full of access tokens.

## 18. Reverse Proxies, API Gateways, and CORS

In gateway architectures, error responses can be **rewritten** or logged by multiple layers:

```mermaid
flowchart LR
    CLIENT["Browser / OAuth client"] --> G["API Gateway"]
    G --> APP["Spring Resource Server"]
    APP --> LOG["App logs / tracing"]
    G --> EDGE["Gateway logs / WAF"]
    APP --> AS["Authorization Server / JWKS / Introspection"]
    APP --> G
    G --> CLIENT
```

### 18.1. Gateways Should Not Echo Request Headers on Error

Some gateway debug modes return:

```json
{
  "message": "Upstream rejected request",
  "requestHeaders": {"Authorization": "Bearer ..."}
}
```

This is a leak even when Spring Security returns a minimal 401. Apply redaction/response policies at **both the gateway and application**.

### 18.2. CORS Does Not Mean Exposing Tokens

`WWW-Authenticate` is a response header in the auth flow. If a cross-origin frontend needs to observe the challenge, configure CORS purposefully—never enable `Access-Control-Expose-Headers: *` or unrestricted wildcard origins/credentials. Exposing a header does not grant permissions itself, though it makes challenge info visible to browser code on allowed origins.

**Never** return access tokens in response headers/bodies to “help debug CORS”. OAuth clients should manage tokens via their flows and never send credentials to untrusted origins.

### 18.3. Caching and 401/403 Responses

For authentication errors carrying request/user-related info, you can apply:

```http
Cache-Control: no-store
```

to reduce the risk of caches/proxies storing sensitive responses or reusing them across requests. This is part of an API-wide caching strategy, not a rule breaking valid caches. Avoid letting shared CDNs cache user/token-specific responses without proper separation.

## 19. Security Diagnostics Without Echoing Credentials

When a client reports “Token doesn't work”, a good workflow separates **system root causes** from secret data.

### 19.1. Information to Request from Clients

- Approximate timestamp and timezone.
- Request/correlation ID returned by the API.
- Endpoint/HTTP method (excluding query credentials).
- HTTP status and standard error code.
- OAuth client application name or environment if shareable.
- When the token was requested/refreshed, **without asking for the raw access token**.

### 19.2. Information to Investigate Server-Side

- Phase logs: `bearer-extraction`, `jwt-validation`, `introspection`, or `authorization`.
- Normalized error category.
- Resource audience/issuer configured in internal catalogs, not from self-asserted token values.
- AS/JWKS availability, latency, TLS/certificate state.
- Verified `kid` belonging to trusted JWKS if truly diagnosing key rotation.
- Scope/authority mapping and policy evaluation under access control and data protection limits.

### 19.3. Do Not Create Token Fingerprints Casually

Sometimes teams want a token fingerprint in logs to correlate errors. **Do not** slice:

```text
token_prefix = first 30 characters
token_suffix = last 30 characters
```

because those slices can reveal payloads/headers/signatures or enough data to link sensitive activity.

If token-level correlation is genuinely needed, consider **HMAC-SHA-256 of the token with a dedicated observability key**, protected with retention/rotation policies. Never use that hash as an authentication credential or send it to clients, and evaluate privacy/linkability. For many APIs, a request ID is simpler and far less sensitive.

## 20. Testing to Guarantee No Leaks via HTTP Responses

A robust test suite verifies both **protocol compliance** and **absence of secrets**, not just status codes.

### 20.1. Test Matrix for Bearer Failures

| Situation | Typical Expected Status | WWW-Authenticate | Must Not Appear |
| --- | --- | --- | --- |
| Missing Bearer token | 401 | `Bearer` (usually no `error`) | Hypothetical tokens, issuer/key settings, stack trace. |
| Malformed Bearer | 400 or 401 per resolver error and config | Matching challenge | Verbatim header input and exception message. |
| Expired token | 401 | `invalid_token` | `exp`/full payload, raw JWT. |
| Bad-signature token | 401 | `invalid_token` | Public key, signature, JOSE debug details. |
| JWT wrong issuer | 401 | `invalid_token` | Unpublished trusted issuer allowlist. |
| JWT wrong audience | 401 | `invalid_token` | Internal API/tenant names in description. |
| `kid` not found | 401 | `invalid_token` | Key lists/JWKS endpoints. |
| Opaque token `active=false` | 401 | `invalid_token` | Detailed AS response body. |
| Wrong opaque introspection client secret | Reject token; status per fail-closed handler | Do not expose AS client auth response | Client ID/secret, internal introspection URI. |
| Valid token lacking scope | 403 | Possibly `insufficient_scope` | Role/tenant policy and real owner. |
| User accesses another's order | 403/404 per policy | Scope challenge not required | Real owner ID, order data. |

### 20.2. Testing with MockMvc

Example using `spring-security-test` and a real Resource Server config or intentional test decoder. To test **an authentication failure**, assert:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class BearerFailureDisclosureTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void failedAuthenticationDoesNotEchoTokenOrInternalData()
            throws Exception {
        String token = "opaque-test-invalid-credential";
        String privateMarker = "internal-jwks-secret-marker";

        // Test decoder/introspector must reject this token.
        MockHttpServletResponse response = mockMvc.perform(
                get("/api/orders")
                        .header(HttpHeaders.AUTHORIZATION,
                                "Bearer " + token))
                .andExpect(status().isUnauthorized())
                .andReturn()
                .getResponse();

        String exposed = response.getContentAsString()
                + String.valueOf(response.getHeader(
                        HttpHeaders.WWW_AUTHENTICATE));

        assertFalse(exposed.contains(token));
        assertFalse(exposed.contains(privateMarker));
        assertTrue(exposed.contains("invalid_token"));
    }
}
```

The example assumes the Spring Security chain is active, the test decoder/introspector **genuinely rejects the token**, and the entry point emits a Bearer challenge. `privateMarker` is a dummy value showing how to write assertions; a stronger leak test should **deliberately throw an exception from the dependency containing that marker**, then assert the response scrubbed it.

### 20.3. Testing Exceptions Containing a Secret Marker

A test bean can simulate a dependency throwing:

```java
// Test-only value, not a real private key.
String sensitive = "TEST-PRIVATE-KEY-MARKER";

// Fake decoder/introspector throws an error containing the marker.
// Send a real request through the Resource Server filter chain.
// Assert the response body and all response headers do not contain the marker.
```

This checks **upstream errors containing sensitive content**, not just client-sent tokens. Tests should also check HTML/JSON bodies produced by the servlet container or `/error` endpoint.

### 20.4. Testing 401 vs. 403

Two requests should be separated:

```java
// Invalid token → authentication failure → 401.
mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer invalid-test-token"))
        .andExpect(status().isUnauthorized());

// Mocked valid authentication lacking authority → 403.
mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(new GrantedAuthority[0])))
        .andExpect(status().isForbidden());
```

**Spring Security Test's `jwt()` does not run JWT signature verification.** Use it to test authorization/responses after mocking a principal; never treat it as proof that your authentication error sanitizer works. For real tokens and JWT decoders, test separately via the `Authorization` header.

### 20.5. Testing Logs and Tracing with Dummy Data

To verify no credentials leak into logs:

1. Issue a dummy token with an easily searchable marker, e.g., `TEST-TOKEN-LEAK-MARKER`.
2. Trigger a test error carrying a marker inside a nested exception message.
3. Route requests through the gateway/Resource Server/HTTP introspection mock if needed.
4. Capture logs/traces in an isolated **test environment** using a test appender/collector.
5. Verify the marker never appears in logs, response bodies, headers, or tracing attributes.
6. Also test `Authorization: Basic ...` and `token=...` in introspection.

These are **testing guidelines**, not executed test results from this repository. Use only test-environment fake tokens/keys/credentials.

## 21. Monitoring Tools and Incident Response

Not every 401 signals an attack; clients regularly expire tokens. However, abnormal bursts of failures can indicate abuse or misconfiguration.

### 21.1. Useful Metrics

| Metric/Label | Recommended Values | Avoid |
| --- | --- | --- |
| `auth_result` | `success`, `denied`, `error`. | Raw access tokens. |
| `auth_phase` | `bearer`, `jwt`, `introspection`, `authorization`. | Exception messages. |
| `failure_category` | `expired`, `invalid_signature`, `audience_mismatch`, `upstream_timeout` per allowlist. | Arbitrary unverified `iss`/`kid` as labels. |
| `http_status` | 400, 401, 403, 5xx. | Email/username in tags. |
| `upstream_status` | AS 2xx, 401, 429, 5xx. | Full introspection response bodies. |
| `request_id` | In controlled logs/traces, safe values. | Putting every request ID into high-cardinality metric series. |

### 21.2. Rate Limiting and Log Flooding

Attackers can send thousands of badly signed JWTs to trigger floods of stack traces, JWKS fetches, or introspection calls. Besides response minimization:

- Apply rate limiting at the gateway/resource where appropriate.
- Enforce timeouts and bounded retries for JWKS/introspection.
- Use sampling/aggregation for repeated errors.
- Avoid fetching arbitrary JWKS URLs suggested by JOSE `jku`/`x5u` in tokens.
- Limit error details to avoid turning the decoder into an “oracle” helping attackers guess valid keys/claims.

### 21.3. Should “Token Expired” Be Disclosed to Clients?

Some legitimate clients want to distinguish expiration from bad signatures to refresh tokens automatically. Protocol-wise, `invalid_token` is usually sufficient for refresh/re-authentication branches; the “expired” detail is a **design option** requiring consideration of oracle risks and extra disclosure.

If the system intentionally emits `error_description="The access token expired"`, it must be a **fixed string**, never concatenating raw tokens, unverified timestamps/claims, or verifier internals. A more minimal option is returning only `invalid_token`, letting clients request new tokens per their OAuth flow.

## 22. Specific Anti-Patterns

### Anti-pattern 1 — Returning `exception.getMessage()` to Clients

Messages can contain tokens, `kid`s, URLs, or stack traces. Use defined public error codes and fixed messages.

### Anti-pattern 2 — Logging Raw JWTs to Debug 401s

JWTs can carry personal data, scopes, and signatures; long-term logs create uncontrolled credential stores. Use correlation IDs and categories.

### Anti-pattern 3 — Echoing the `Authorization` Header in Responses

Never include full request headers in debug bodies, especially in API gateways or `@ControllerAdvice`.

### Anti-pattern 4 — Returning Public Keys/`kid` Lists When Signatures Fail

`kid` mismatches are internal key-selection details. Never dump internal JWKS info into `error_description`.

### Anti-pattern 5 — Returning Introspection Client Secrets or Upstream Responses

An HTTP 401 from the AS can relate to the Resource Server's client secret, not the caller's token. Never forward upstream bodies/headers holding sensitive metadata.

### Anti-pattern 6 — Returning Overly Detailed Scope/Role/Tenant Policies on 403

Tell the client permissions are missing using standard codes, without exposing group maps, owner IDs, or internal admin roles.

### Anti-pattern 7 — Pointing error_uri to an Internal Console

Use public documentation only. Never attach tokens or secrets to query strings.

### Anti-pattern 8 — Leaving Production Debug/Profiling Enabled Indefinitely

Debug logs, full tracing, heap dumps, and Actuator can retain credentials. Enforce operational modes, retention, and access controls.

### Anti-pattern 9 — Disabling Authentication Validation to Suppress Errors

Never choose “return 200 for bad tokens” to reduce error leakage. Stay fail-closed; only reduce what is disclosed externally.

### Anti-pattern 10 — Returning 401 invalid_token for Every Error

Missing scopes on a valid token are usually 403; syntax errors may be 400; AS unavailability is a dependency failure. Never break protocols/monitoring just to have one uniform response.

### Anti-pattern 11 — A 500 Body Naming SQL or Keystores

Not just Bearer: every app error response must avoid stack traces, SQL, and secret paths, even when errors occur after authentication.

### Anti-pattern 12 — Treating Unverified Data as Audit Truth

`sub`, `email`, and `tenant_id` from an unverified JWT can be forged by attackers. If recorded for investigation, mark them clearly as “unverified input” and bound content; never treat them as verified actor identities.

## 23. Illustrative Operational Scenarios

### A. Expired Token

Client calls the API with an expired access token. The Resource Server returns **401 invalid_token** without revealing the payload or exact expiration timestamp. Client runs a valid OAuth flow for a new token. Server logs can record `JWT_EXPIRED` per defined policy.

### B. JWKS Cache Has Not Received a New Key

Issuer rotates keys, token carries a new `kid`, and the Resource Server's stale cache does not yet see the matching public key. The client still receives only token-rejected or dependency-error per policy. Server telemetry logs a controlled `JWKS_KEY_NOT_FOUND`/`JWKS_REFRESH_FAILED`, never returning internal JWKS URIs or key lists.

### C. Token from an Untrusted Issuer

Attacker crafts a JWT with a URL-like `iss` and `aud=orders-api`. The Resource Server does not dynamically fetch JWKs from unapproved issuers. Generic `invalid_token` response, disclosing no issuer allowlist in the body.

### D. User Lacks Permission to View an Order

Valid JWT has `orders:read`, yet the actor does not own `orderId`. The API enforces object-level authorization, returning **403** or 404 per resource-hiding policy. Never includes the real owner in the response.

### E. Introspection Client Secret Was Rotated

All opaque tokens fail simultaneously because the Resource Server is calling the AS with an old secret. The AS returns HTTP 401 **to the API**. The server must fail closed, alert, and update the credential version. Never forward the upstream `invalid_client` body containing client registration/secret details to callers, and never misdiagnose it as users losing permissions.

### F. An Error in `@ControllerAdvice` Returns a Stack Trace

After authentication succeeds, the controller throws a database exception. If the handler puts `ex.toString()` or a stack trace into JSON, it can expose DB structure. Use a handler returning a fixed `INTERNAL_ERROR` message and scrubbed internal logs.

### G. Gateway Saves the Authorization Header on 401 Requests

Spring Security returns a clean, safe Bearer challenge, yet API gateway debug logs still record the full token. This proves **error minimization must be enforced end-to-end**, not only in Spring controllers.

### H. Application Wants to Show a “Log In Again” Button

The frontend usually only needs **401 invalid_token** to request a new token or redirect to a login flow. It does not need raw JWT claims, private keys, JWKS URLs, or internal IdP tenant names.

## 24. Self-Check Questions

**1. When a Bearer token is missing, should the Resource Server return `error="invalid_token"`?** Not by default. Under RFC 6750, when no authentication information is supplied, Bearer challenges usually omit an error code.

**2. What should a JWT with a bad signature return?** Usually `401 Unauthorized` with `WWW-Authenticate: Bearer error="invalid_token"`, without tokens or key details.

**3. What should a valid access token lacking an endpoint scope return?** Usually `403 Forbidden`; `insufficient_scope` when matching Bearer semantics and handlers.

**4. Is error_description required?** No. It can be omitted or set to a safe fixed string.

**5. Is it safe to return `exception.getMessage()` inside `error_description`?** No. It can expose tokens, issuer URIs, JWKS, internal HTTP responses, and stack traces.

**6. Are public keys/JWKS always secret?** Public keys may be public by design, yet error responses should not volunteer internal topology/key inventories; private keys and shared secrets must be strictly protected.

**7. Why does HTTP 401 from the AS not mean the caller's token is invalid?** Because the AS may be rejecting the **Resource Server's introspection credentials**, distinct from the status of the access token being queried.

**8. Is logging raw tokens in temporary debug logs acceptable?** It is high risk; use markers/test tokens, correlation IDs, and log categories instead. If real tokens are found in logs, follow your credential-exposure incident procedure.

**9. Does `@ControllerAdvice` catch every error from BearerTokenAuthenticationFilter?** No. Many authentication errors occur in the security filter chain before MVC; configure `AuthenticationEntryPoint`/`AccessDeniedHandler` and layer-appropriate error handlers.

**10. Why must `WWW-Authenticate` be tested?** Because it is the Bearer contract for clients, covering error codes, HTTP statuses, and potential leaks via descriptions/scopes.

**11. Should owner/tenant names be returned in 403s to help clients debug?** No; that can expose unauthorized access details. Use generic error codes and correlation IDs.

**12. Can JWKS unavailability be turned into allow-all to avoid 401s?** No. When tokens cannot be verified, fail closed and handle dependency errors per policy.

**13. Is it safe to log expired tokens verbatim?** No. Old tokens can still contain PII or system details and pose risks if harvested.

**14. To test for leaks, is asserting HTTP status alone enough?** No. Assert that bodies, response headers, and logs/traces (with test data) contain no raw tokens, secret markers, internal URLs, or exception details.

**15. Do gateways/Actuator still need protection once Spring Security sanitizes 401s?** Yes. Reverse proxy logs, tracing, heap dumps, and Actuator can become independent leak channels.

## 25. Standards and API References

- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** `WWW-Authenticate`, `invalid_request`, `invalid_token`, `insufficient_scope`, and guidance to avoid tokens in URIs. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 7662 — OAuth 2.0 Token Introspection:** `active`, introspection access control, and Resource Server authentication when calling the endpoint. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 7519 — JSON Web Token (JWT):** claim structure; JWTs do not encrypt payloads by default. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 8725 — JSON Web Token Best Current Practices:** token validation, issuer/audience binding, and preventing context confusion. https://www.rfc-editor.org/rfc/rfc8725
- **RFC 9110 — HTTP Semantics:** 401, 403, 404, and authentication challenge mechanics. https://www.rfc-editor.org/rfc/rfc9110
- **RFC 9457 — Problem Details for HTTP APIs:** structured API error bodies and minimizing unnecessary info. https://www.rfc-editor.org/rfc/rfc9457
- **Spring Security Reference — Servlet OAuth 2.0 Resource Server JWT:** `JwtDecoder`, Bearer token handling, entry points, and scope authorities. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- **Spring Security Reference — Servlet OAuth 2.0 Resource Server Opaque Token:** `OpaqueTokenIntrospector` and introspection. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Spring Security API — BearerTokenAuthenticationEntryPoint / BearerTokenAccessDeniedHandler / BearerTokenErrors:** standard handlers and errors for Bearer Resource Server; consult your version's Javadoc.
- **OWASP Cheat Sheet Series — Logging Cheat Sheet:** controlling security events, PII, and secrets written to logs. https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- **Spring Boot Reference — Error Handling and Actuator Security:** securing error responses and operational endpoints, depending on your Spring Boot release line.

**Conclusion:** A Resource Server must return **the right HTTP status and Bearer error code**, yet only with the **minimum necessary information**. Use `BearerTokenAuthenticationEntryPoint` and `BearerTokenAccessDeniedHandler` per RFC 6750; strip raw tokens, keys, secrets, issuer/JWKS/introspection configs, and exception messages from `error_description`, bodies, and headers. Keep technical diagnostics inside **scrubbed, access-controlled internal logs/tracing/audits** keyed by correlation IDs. When authentication cannot be verified, **fail closed**; when a valid principal lacks scope or ownership, enforce authorization independently. **Hiding internal error details never means hiding protocol status or relaxing validation.**
