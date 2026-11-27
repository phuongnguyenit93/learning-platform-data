# Requests with Multiple Tokens, Empty Tokens, and Invalid Syntax in Bearer Tokens

## 1. The problem to solve

A **Spring Security OAuth 2.0 Resource Server** typically receives an access token from an HTTP request to protect an API. Under the **Bearer** mechanism, the client normally sends the token in a header:

```http
GET /api/orders/123 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjMifQ.signature
```

In production systems, requests are not always well-formed. A client or proxy might send **two tokens**, send `Authorization: Bearer` without a token value, pass a broken string from header concatenation, or send tokens simultaneously in both header and query/body. If the API handles these inconsistently, unpredictable authentication failures can occur, invalid tokens may be ignored, or worse, **different layers of the system may interpret different tokens**.

This lesson explains how to identify and handle three groups of situations:

1. **Multiple tokens in one request**: multiple `Authorization` headers, multiple bearer values, or combined token transport locations.
2. **Empty or absent tokens**: distinguishing providing no token from attempting to provide Bearer while leaving the value empty.
3. **Invalid syntax**: malformed HTTP Authorization header format, distinct from a syntactically valid token that fails signature/expiration/issuer checks.

The scope is **access tokens sent to a Resource Server**. OIDC ID tokens are for clients handling login; refresh tokens are used at the Authorization Server's token endpoint. Do not use those two types to replace Bearer access tokens when calling business APIs.

## 2. Bearer token rules in HTTP

### 2.1. Standard form of the Authorization header

According to **RFC 6750, Section 2.1**, the syntax of a Bearer credential is described as:

```abnf
credentials = "Bearer" 1*SP b64token
b64token    = 1*( ALPHA / DIGIT /
                  "-" / "." / "_" / "~" / "+" / "/" ) *"="
```

This has several practical consequences:

- `Bearer` is the **authentication scheme** name; scheme names in HTTP are case-insensitive.
- There must be a space `SP` between the scheme and the token. The RFC grammar permits one or more spaces, though **a framework's specific parser may be stricter**.
- The token value must not be an empty string.
- Characters belong to the `b64token` set above; `=` may only appear at the end as padding.
- Do not use commas to list multiple Bearer credentials, do not wrap tokens in quotes, and do not add a second `Bearer` prefix after a comma.
- **Valid syntax does not prove the token is valid**: `Bearer abc` may pass token extraction and still be rejected when the Resource Server validates it.

The following examples help distinguish *extractable values* from *validatable values*:

| Header | Notes |
|---|---|
| `Authorization: Bearer abc.def.ghi` | Matches Bearer syntax; a real JWT must still be verified |
| `Authorization: bearer abc` | Scheme name is case-insensitive |
| `Authorization: Bearer abc` | Syntactically acceptable even though `abc` is not a valid JWT |
| `Authorization: Bearer` | Missing token value |
| `Authorization: Bearer ` | Empty token value |
| `Authorization: Bearer "abc"` | Token wrapped in quotes, invalid `b64token` format |
| `Authorization: Bearer abc def` | Value contains a space, invalid syntax |
| `Authorization: Bearer abc,Bearer def` | Attempting to combine multiple credentials with a comma |
| `Authorization: Basic YTpi` | A different scheme; not a Bearer token |
| Missing `Authorization` | No credential provided via header |

RFC 6750 describes other mechanisms for transporting bearer access tokens, yet **recommends the `Authorization` header**. Putting tokens in query strings risks exposure in URL logs, browser history, referrer headers, and monitoring systems. Spring Security defaults to looking for bearer tokens only in the header; alternative transport paths must be explicitly enabled.

### 2.2. A request should have one unambiguous token source

In RFC 6750, a request **must not use more than one method** to transmit an access token. For instance, do not simultaneously send `Authorization: Bearer ...` and an `access_token=...` parameter in the query string or form body.

Even when both locations hold the same value, the request remains ambiguous about the credential source, especially when API gateways, proxies, and backends run different parsers. Do not invent rules like “prefer header” or “take the last token” if the security contract requires a single source.

## 3. Requests containing multiple tokens

### 3.1. Two separate Authorization headers

Example request that might arrive from a client:

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer token-A
Authorization: Bearer token-B
```

This case should be rejected under a unified input policy: the client is supplying **more than one credential in the same header type**. However, you must understand how HTTP layers behave:

- HTTP clients, reverse proxies, or servlet containers may **preserve both values**, **merge them into one value**, or handle duplicate headers in their own way.
- In the Servlet API, `request.getHeader("Authorization")` typically returns the **first value**. Reading a single value with `getHeader` does not guarantee duplicate headers were caught.
- `request.getHeaders("Authorization")` lets you inspect the values still retained by the container; gateway filters may need to detect and reject duplicate headers **before reaching the application**.
- Do not assume default Spring Security always detects every duplicate `Authorization` variant passing through a proxy. Checks must be placed at the layer that can still observe the original request.

If a system consists of an API gateway and a Resource Server, apply a consistent policy: **one Authorization header containing one Bearer credential**. If multiple values exist, reject at the trusted entry point.

### 3.2. Two tokens inside the same header

```http
Authorization: Bearer token-A, Bearer token-B
```

This is not valid Bearer credential syntax. Do not call `split(",")` and pick one token: commas are not valid syntax for passing a list of Bearer tokens in that header. The parser should reject the malformed value.

Another variant:

```http
Authorization: Bearer token-A token-B
```

An internal space within the token string makes the credential syntactically invalid. Do not concatenate the two parts, and do not ignore the second token part.

### 3.3. Both a Bearer header and a query parameter

```http
GET /api/orders?access_token=token-B HTTP/1.1
Host: api.example.com
Authorization: Bearer token-A
```

Under RFC 6750, the client is using **two methods to transmit an access token**. With Spring Security:

- **By default**, `DefaultBearerTokenResolver` does not read bearer tokens from query strings, so that parameter does not automatically trigger a “multiple tokens” error in the resolver. The header remains the default token source.
- If `setAllowUriQueryParameter(true)` is enabled, the resolver can detect both the header token and query token and reject with an `invalid_request` error.
- An API that wants to **completely forbid** `access_token` in queries (even when the resolver does not use it) needs an input validation policy at the application/gateway layer. Do not mistake “not reading query” for “actively rejecting every request containing a query token.”

For most APIs, keeping the default configuration and requiring clients to send tokens in the header is the easiest option to manage.

### 3.4. Both a Bearer header and a form body parameter

When body parameters are allowed, a request may contain two sources:

```http
POST /api/orders/search HTTP/1.1
Host: api.example.com
Authorization: Bearer token-A
Content-Type: application/x-www-form-urlencoded

access_token=token-B&state=open
```

If configuration allows reading `access_token` from a form body, simultaneously providing a bearer header must be treated as **multiple tokens** and rejected. Under RFC 6750, the form-body method is only used under the conditions described in Section 2.2 (such as an `application/x-www-form-urlencoded` body); do not treat a JSON field named `access_token` as standard bearer token transport.

Spring Security by default **disables** form-body token transport. Enable it only when strict compatibility requires it and the impact of reading request parameters is understood.

### 3.5. Repeated access_token parameter

```http
GET /api/orders?access_token=token-A&access_token=token-B HTTP/1.1
Host: api.example.com
```

When a system enables query parameters, repeating the same parameter name makes it unclear which value the parser should select. Do not handle this by arbitrarily taking the first or last token. The same applies to repeated form-body parameters. In HTTP parameter parsing, repeated values can be retrieved via `getParameterValues("access_token")`; if this channel is accepted, establish a policy to reject ambiguous cases.

**Important case:** enabling another token transport channel can alter how the application interprets requests that previously worked. Treat such a change as an input protocol change requiring consistency across components.

## 4. Empty tokens, missing tokens, and absent Bearer credentials

A common mistake is treating every failure to extract a token identically. In reality, there are at least three distinct categories:

| Situation | Request | Meaning |
|---|---|---|
| No Authorization sent | Header absent | Client did not supply a Bearer credential |
| Non-Bearer header | `Authorization: Basic ...` | Another credential scheme is present; standard Bearer resolver does not extract a token |
| Attempting Bearer with missing value | `Authorization: Bearer` or `Bearer ` | Request attempts to use Bearer, but the credential is **invalid** |
| Token built from empty value | `Authorization: Bearer ${token}` when variable is empty | Client request-construction bug |
| Literal `null`/`undefined` value | `Authorization: Bearer null` | Non-empty string; Bearer syntax may pass, yet the value is not a validatable access token |

Distinguishing these helps when returning responses and investigating root causes.

### 4.1. No token sent

```http
GET /api/orders HTTP/1.1
Host: api.example.com
```

Standard resolvers return `null` when no Bearer credential is found. The request continues down the filter chain. If the endpoint requires authentication, Spring Security typically returns **401** with a Bearer challenge. If the endpoint permits anonymous access, the request can proceed normally. **A resolver returning null does not by itself mean the request is immediately rejected.**

### 4.2. Sending Bearer with no value

```http
Authorization: Bearer
```

or:

```http
Authorization: Bearer 
```

This is a syntactically invalid Bearer credential. With Spring Security's `DefaultBearerTokenResolver`, a value starting with `Bearer` that fails to match the valid pattern typically raises an `OAuth2AuthenticationException` with error `invalid_token`, after which the Resource Server error handler normally returns **401 Unauthorized**.

Do not silently fall back to anonymous access or look up another token from query/cookies. If a client sends an empty Bearer header, fix the client's request construction logic.

### 4.3. Token values with whitespace

```http
Authorization: Bearer    
```

Spaces do not constitute a token value. Variants with newlines, misplaced tabs, trailing spaces, or spaces embedded within the token string must be handled by the configured HTTP/bearer parser; do not call `trim()` and arbitrarily repair a credential. One layer may normalize whitespace while another does not, making consistency critical.

## 5. Header syntax errors vs. invalid tokens

A Resource Server processes requests in two conceptual steps:

```text
HTTP request
    |
    v
[Step 1] Extract Bearer credential
    |  - Is the header present?
    |  - Are the scheme and structure recognizable?
    |  - Are there multiple sources or multiple values?
    |
    +-- Fails Step 1 --> Token format/transport error
    |
    v
[Step 2] Validate the extracted access token
       - JWT: signature, issuer, expiration, audience, validators
       - Opaque: introspection and token status/contract
       - Next: scope/authority and business permissions
    |
    +-- Invalid token --> Authentication/authorization error
    |
    v
Endpoint permitted to process
```

**Example 1: invalid HTTP structure**

```http
Authorization: Bearer abc def
```

Extraction fails because the string contains an internal space.

**Example 2: valid structure, fake access token**

```http
Authorization: Bearer abc.def.ghi
```

This value uses allowed characters and has dots, yet having three segments **does not prove it is a valid JWT**. The JWT decoder may reject it due to invalid Base64URL, JSON, signature, algorithm, or claims.

**Example 3: validly signed token not meant for this API**

A JWT access token for `catalog-api` with `aud=catalog-api` must not be used to call `orders-api` if the API requires its own audience. Audience, issuer, and permission scope must be checked **after** extracting the token. Likewise, an OIDC ID token with `aud=web-client` is not an API access token, even if it is a validly signed JWT.

**Example 4: active access token lacking scope**

A token valid for authentication may still not be permitted for `POST /api/orders`; in that case the system enforces authorization policy and typically returns **403 Forbidden**, not a token syntax error.

## 6. HTTP statuses and WWW-Authenticate

RFC 6750 Section 3 defines how a Resource Server communicates errors via **`WWW-Authenticate`** with the Bearer scheme. Key error codes:

| Error | Typical context | Common HTTP status |
|---|---|---|
| No credential when API requires one | Client sent no Bearer token | **401 Unauthorized**, usually with a Bearer challenge, possibly without `error` |
| `invalid_request` | Malformed request, more than one token transport mechanism, repeated or unsupported parameters | **400 Bad Request** per RFC 6750 |
| `invalid_token` | Access token expired, revoked, malformed, or unverifiable | **401 Unauthorized** |
| `insufficient_scope` | Access token is valid but lacks required permissions | **403 Forbidden** |

Challenge examples; displayed attributes depend on configuration:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token", error_description="Bearer token is malformed"
```

```http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer error="invalid_request", error_description="Found multiple bearer tokens in the request"
```

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

**Distinguish RFC rules from actual framework mapping.** Under the RFC, malformed requests typically map to `invalid_request` with 400. However, Spring Security's `DefaultBearerTokenResolver` handles non-matching Bearer headers using `invalid_token`, resulting in 401 in standard setups. Individual exceptions and final responses also depend on the security filter chain, entry point, and custom configuration. Do not write clients assuming every extra space always returns 400.

`error_description` exists to help clients fix errors, not to echo back the original token. **Never include raw access tokens, Authorization headers, or sensitive data in error responses**.

## 7. Where does Spring Security handle Bearer tokens?

With Spring Security Servlet Resource Server, the typical flow is:

1. **`BearerTokenAuthenticationFilter`** calls `BearerTokenResolver` to locate the token.
2. **`DefaultBearerTokenResolver`** defaults to reading the `Authorization` header and checking Bearer structure.
3. If there is no Bearer token, the filter continues the chain; whether anonymous access is allowed or authentication is required depends on endpoint configuration.
4. If the resolver throws `OAuth2AuthenticationException`, the filter delegates to the authentication failure mechanism (e.g., `BearerTokenAuthenticationEntryPoint`).
5. Once a token is extracted, `AuthenticationManager` uses a JWT decoder or opaque introspection to authenticate it.
6. When valid, Spring Security creates an `Authentication` and enforces endpoint authorization policies.

For JWTs and opaque tokens, **the HTTP token extraction step is essentially identical**. The difference lies in validating the token's contents (JWT decoding/verification versus introspection).

### 7.1. Default configuration: accepting only Bearer headers

Example Spring Boot application protecting endpoints with JWTs:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com/realms/demo
```

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

In this configuration, `DefaultBearerTokenResolver` defaults to:

- Looking for the token in the `Authorization` header.
- Disallowing `access_token` from URI query parameters.
- Disallowing `access_token` from form-encoded body parameters.
- Matching a specific Bearer header pattern that may reject some inputs even where RFC syntax is more permissive; for instance, the RFC allows multiple `SP` characters whereas the default parser typically expects a single space after `Bearer`.
- Failing on malformed Bearer values rather than treating them as valid credentials.

These settings **only describe bearer token selection**. The API still needs validators for audience, issuer, expiration, and access permissions matching the system's contract.

### 7.2. When enabling query or form bodies

Spring Security exposes setters on `DefaultBearerTokenResolver`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

@Bean
BearerTokenResolver bearerTokenResolver() {
    DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();

    // Keep safe defaults: read Bearer only from the header.
    resolver.setAllowUriQueryParameter(false);
    resolver.setAllowFormEncodedBodyParameter(false);

    return resolver;
}
```

If an alternative mechanism must be enabled for legacy protocol reasons, `setAllowUriQueryParameter(true)` or `setAllowFormEncodedBodyParameter(true)` changes extraction behavior. You must then explicitly specify how to handle requests with **multiple token locations**, duplicate parameter names, and logging impacts. Never enable both merely to “let clients send however they like.”

To wire a custom `BearerTokenResolver` bean into a security chain:

```java
@Bean
SecurityFilterChain api(HttpSecurity http,
        BearerTokenResolver bearerTokenResolver) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                    .bearerTokenResolver(bearerTokenResolver)
                    .jwt(Customizer.withDefaults()))
            .build();
}
```

The snippets in this section are **illustrative configuration options**; when applying them, consolidate into a consistent project configuration with a `SecurityFilterChain` matching your API paths.

## 8. Actively rejecting two Authorization headers

Spring Security's `DefaultBearerTokenResolver` focuses on the token returned by the servlet request when reading the header. In environments at risk of duplicate `Authorization` headers, you can add a check layer before delegating value parsing to the default resolver.

Example decorator for an application supporting only **one Authorization header**:

```java
import java.util.Enumeration;

import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.BearerTokenErrors;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

@Bean
BearerTokenResolver strictBearerTokenResolver() {
    DefaultBearerTokenResolver delegate = new DefaultBearerTokenResolver();

    return request -> {
        Enumeration<String> headers =
                request.getHeaders(HttpHeaders.AUTHORIZATION);
        int count = 0;
        while (headers != null && headers.hasMoreElements()) {
            headers.nextElement();
            count++;

            if (count > 1) {
                throw new OAuth2AuthenticationException(
                        BearerTokenErrors.invalidRequest(
                                "More than one Authorization header"));
            }
        }

        return delegate.resolve(request);
    };
}
```

Wire the resolver into the `oauth2ResourceServer(...)` DSL as shown in section 7.2. Then:

- When the servlet container **still retains** two separate `Authorization` values, the resolver rejects with `invalid_request`.
- When a request has a single header `Authorization: Bearer token-A, Bearer token-B`, the default delegate detects a malformed Bearer credential.
- When a request has exactly one Bearer header, the delegate proceeds with standard syntax checks.
- The example enforces rejecting **every duplicate Authorization header**; if the API also supports other schemes or multiple security chains, scope the check to the appropriate endpoints.

**Limitation to understand:** if a reverse proxy already dropped the second header before the request reached the application, the servlet filter cannot tell that the original request had duplicates. Therefore, **gateway/edge** and **application** policies must align. Do not treat the snippet above as a complete substitute for gateway configuration.

## 9. Matrix of requests and expected behaviors

The table below assumes an **API protected by Spring Security Resource Server with the default resolver** (query/body tokens disabled). For the status column, values describe typical behavior when the endpoint requires authentication; custom security chains may alter results.

| Input | At the Bearer extraction step | Typical outcome |
|---|---|---|
| No `Authorization` | No token found | Proceeds; protected endpoints typically return 401/challenge |
| `Authorization: Basic ...` | Not Bearer scheme | Does not extract Bearer; protected endpoints typically return 401/challenge |
| `Authorization: Bearer` | Malformed Bearer header | `invalid_token`, typically 401 |
| `Authorization: Bearer ` | Empty value, malformed | `invalid_token`, typically 401 |
| `Authorization: Bearer abc def` | Contains internal space | `invalid_token`, typically 401 |
| `Authorization: Bearer "abc"` | Token wrapped in quotes | `invalid_token`, typically 401 |
| `Authorization: Bearer abc, Bearer def` | Multiple tokens in one header, invalid pattern | `invalid_token`, typically 401 |
| `Authorization: Bearer abc` | Extracts string `abc` | Passes extraction; JWT/opaque validator may return 401 |
| Bearer header + query `access_token` | Default resolver **ignores query** | Only attempts to validate the header token |
| Only query `access_token` | Default resolver **does not read query** | Protected endpoint typically returns 401/challenge |
| Bearer header + form `access_token` | Default resolver **does not read form** | Only attempts to validate the header token |
| Two separate Authorization headers | Depends on servlet/proxy and resolver | Should be blocked at gateway or via extra resolver check |
| Valid token lacking scope | Token extracted and authenticated | Authorization check typically returns 403 |

If query/form parameters **are enabled** in the resolver, the table changes: a request carrying tokens in both the header and the enabled method may be classified as `invalid_request` (typically 400). When transmitting tokens via an alternative method, RFC 6750 and servlet request constraints still apply.

## 10. Illustrating scenarios from client to Resource Server

### 10.1. Client accidentally concatenating two tokens

Suppose a frontend sets the header twice because one interceptor adds the token and another HTTP layer wraps it again:

```text
Interceptor A: Authorization = "Bearer token-A"
Interceptor B: Authorization = "Bearer " + previousValue
Result:        Authorization = "Bearer Bearer token-A"
```

The resulting request contains two `Bearer` prefixes in one string, so the parser cannot extract a valid bearer credential. **The fix** is ensuring only one place is responsible for attaching `Authorization`, and never prepending `Bearer ` onto an already formatted header.

### 10.2. Client producing an empty token due to a race condition

```javascript
// Buggy example: accessToken may be an empty string at request time.
const headers = { Authorization: `Bearer ${accessToken ?? ""}` };
```

If `accessToken` is not ready yet, the request becomes `Authorization: Bearer `, which is typically rejected as a malformed Bearer credential.

Fix request construction: only attach the header when a non-empty access token is actually present:

```javascript
const headers = {};

if (typeof accessToken === "string" && accessToken.length > 0) {
  headers.Authorization = `Bearer ${accessToken}`;
}
```

This only prevents sending empty values; it does not replace Resource Server authentication. If the endpoint requires authentication and the client lacks a token, the application must complete the proper login/authorization flow before calling.

### 10.3. Gateway and backend seeing different tokens

```text
Client
  |-- Authorization: Bearer token-A
  |-- Authorization: Bearer token-B
  v
Gateway  [may keep, merge, or pick a value depending on product/config]
  |
  v
Resource Server [reads whatever headers remain after the gateway]
```

If the gateway validates `token-A` while the backend uses `token-B`, the identity/permissions enforced by the two layers can diverge. This is a key reason to **reject ambiguous credentials as early as possible** and configure all layers with the same rules.

### 10.4. Syntactically valid Bearer token that is an ID token

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer ID_TOKEN_CREATED_FOR_WEB_CLIENT
```

If the value consists solely of allowed characters, the parser can extract the token; that does not mean the API should accept it. The API must validate issuer, audience, Authorization Server access token requirements, and access permissions. Never work around token-type errors by loosening the parser or skipping audience checks.

## 11. Manually testing an API

When inspecting an endpoint configured with Resource Server, you can construct illustrative cURL requests. Each command below is a **request scenario**; actual HTTP statuses depend on the server and security chain, not observed runtime output:

**Missing token:**

```bash
curl -i https://api.example.com/api/orders
```

**Empty Bearer:**

```bash
curl -i -H 'Authorization: Bearer ' \
  https://api.example.com/api/orders
```

**Two Bearer credentials combined in one header:**

```bash
curl -i -H 'Authorization: Bearer token-A, Bearer token-B' \
  https://api.example.com/api/orders
```

**Sending Authorization twice:**

```bash
curl -i \
  -H 'Authorization: Bearer token-A' \
  -H 'Authorization: Bearer token-B' \
  https://api.example.com/api/orders
```

Note: HTTP clients, reverse proxies, and servlet containers can normalize duplicate headers, so verifying gateway policy requires observing the request at that exact layer. Never leave real access tokens in command history or logs when testing against environments with real data.

**Header with query token:**

```bash
curl -i \
  -H 'Authorization: Bearer token-A' \
  'https://api.example.com/api/orders?access_token=token-B'
```

With the default resolver, the query token is not an authentication source; if an environment must **forbid** the presence of `?access_token`, enforce that rule separately.

## 12. Designing error handling and operational observability

### 12.1. Errors should be meaningful without leaking credentials

Appropriate diagnostic details:

- Extraction errors: missing header, empty Bearer, malformed Bearer, multiple sources.
- Validation errors: token not accepted by issuer, expired, or not intended for this API.
- Authorization errors: token authenticated, but lacks permission to access the resource.

Information that **must not appear in logs/responses**: full bearer tokens, refresh tokens, intact Authorization headers, `access_token` values from query or body, or unnecessary sensitive identity data.

If metrics are needed, use event labels such as `missing_credentials`, `malformed_bearer`, `multiple_authorization_headers`, `multiple_token_sources`, `jwt_validation_failed`. Distinguish resolver errors from decoder/introspector errors because the client/gateway fixes are completely different.

### 12.2. Do not auto-repair malformed requests

The following patterns are discouraged:

```java
// Wrong approach: picking the last part of an ambiguous header.
String token = authorization.substring(
        authorization.lastIndexOf("Bearer ") + "Bearer ".length());

// Wrong approach: if Bearer is empty, try searching query or cookies.
// Wrong approach: try each token in turn until one validates.
```

Such “workarounds” widen the accepted input surface, hide client bugs, and can create divergence between gateways and backends. Define a clear request format and return appropriate errors when clients violate it.

### 12.3. Assigning responsibilities per layer

| Layer | Appropriate responsibility |
|---|---|
| **Client** | Attach only a single `Authorization: Bearer <access_token>` header once a token is obtained; never concatenate repeatedly |
| **API Gateway / Reverse Proxy** | Standardize duplicate-header policy and reject ambiguous credentials before proxying onward |
| **BearerTokenResolver** | Identify token source and Bearer syntax; reject inputs that cannot be interpreted consistently |
| **JWT Decoder / Opaque Introspector** | Verify the token was issued and remains valid under the issuer contract |
| **Authorization layer** | Enforce scope/authority, tenant, resource ownership, and specific operations |
| **Error handling / Logging** | Return proper status/challenge, log minimal reason codes, and never log tokens |

## 13. Rules to remember

For Spring Security OAuth 2.0 Resource Server:

1. **One request, one Bearer access token, one unambiguous source.** The `Authorization` header is the recommended default location.
2. **No token** differs from **attempting to send an empty Bearer**: the first may proceed as anonymous, whereas the second is an invalid credential.
3. **Syntax error** differs from **an extracted token failing validation**: the resolver and the JWT decoder/introspector own those two separate steps.
4. **Multiple Authorization headers** require considering gateways/proxies as well as the servlet container; do not rely on a single `getHeader` call to conclude there are no duplicates.
5. **RFC 6750 and Spring Security behavior do not align identically on every malformed error code**: inspect `WWW-Authenticate`, `invalid_request`, `invalid_token`, and actual responses under your application config.
6. **Do not try to repair bad tokens in the backend** by picking first/last tokens, slicing strings arbitrarily, or trying multiple tokens sequentially.

A secure Resource Server needs to **select exactly one bearer credential**, **validate the right access token for the API**, and then **enforce authorization on the requested resource**. Those three steps are independent and all must be implemented properly.

## 14. References

- **RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage**, especially Sections 2.1–2.3 (token transport), Section 3 (Bearer challenge and errors), Section 5 (security considerations): https://www.rfc-editor.org/rfc/rfc6750
- **RFC 9110 — HTTP Semantics**, HTTP authentication, `Authorization`, and `WWW-Authenticate`: https://www.rfc-editor.org/rfc/rfc9110
- **Spring Security Reference — OAuth 2.0 Resource Server**: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html
- **Spring Security API — `DefaultBearerTokenResolver`**: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/DefaultBearerTokenResolver.html
- **Spring Security API — `BearerTokenAuthenticationFilter`**: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/authentication/BearerTokenAuthenticationFilter.html
