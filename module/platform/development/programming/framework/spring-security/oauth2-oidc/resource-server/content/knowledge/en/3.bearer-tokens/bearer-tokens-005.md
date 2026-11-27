# Tokens in Header, Query, or Form: Different Support Scope and Risks

When an **OAuth 2.0 Resource Server** receives an HTTP request, the first thing it needs to do is locate the **bearer access token** sent by the client. Three locations may be encountered:

1. HTTP header: `Authorization: Bearer <access-token>`.
2. `application/x-www-form-urlencoded` request body: the `access_token` parameter.
3. URI query string: `?access_token=...`.

Although all three methods are described in **RFC 6750**, they do not share the same level of security, the same protocol constraints, or the same default support in Spring Security. **In modern systems, always send bearer access tokens in the `Authorization` header over HTTPS.** Specifically, **RFC 9700 (OAuth 2.0 Security Best Current Practice, 2025) mandates that clients MUST NOT pass access tokens in URI query parameters**. The fact that a framework can be configured to read query parameters is not a recommendation to use them.

This lesson focuses on **access tokens sent by a client to a Resource Server**, not the Authorization Server returning tokens at `/token`, not the `authorization_code` in a login callback, and not the ID token used to authenticate an OIDC client.

## 1. What is a bearer token, and where does it travel?

**Bearer** means that any party entitled to use the token (the “bearer” holding it) can present it to access resources subject to server-enforced limits. If a token is leaked, anyone who obtains it can try reusing it until it expires or is invalidated, unless the system applies additional sender-constraining mechanisms. Therefore, **how the token is transported** is part of the security model, whether the token payload is a signed JWT or an opaque string.

Example system:

- `login.example.com`: Authorization Server issuing access tokens.
- `shop.example.com`: OAuth Client sending requests.
- `api.example.com`: Resource Server using Spring Security to protect `/api/orders/**`.

Basic flow:

```mermaid
sequenceDiagram
    participant C as OAuth Client
    participant R as Spring Security Resource Server
    participant V as JWT Decoder / Token Introspector
    C->>R: HTTPS /api/orders + Bearer access token
    R->>R: BearerTokenResolver looks up credential in request
    alt Single well-formed token present
        R->>V: Validate access token
        V-->>R: Validation result / token attributes
        R->>R: Check scope, audience, and business permissions
        R-->>C: 2xx or 403
    else Missing or invalid token
        R-->>C: 401 or appropriate request error
    end
```

**Separate the two questions:** `BearerTokenResolver` decides *where to extract the token string from*; `JwtDecoder` or `OpaqueTokenIntrospector` decides *whether that token is valid*. Allowing tokens to be read from form/query **does not** change JWT signature verification, issuer, audience, expiration, scopes, or resource access permissions.

## 2. RFC 6750 defines three token transport methods

RFC 6750 section `2` describes three methods for sending bearer access tokens in requests to protected resources and specifies that **clients MUST NOT use more than one method in the same request**.

| Criterion | `Authorization` header | Form-encoded body | URI query parameter |
|---|---|---|---|
| Transport form | `Authorization: Bearer TOKEN` | Body `access_token=TOKEN` | URL `?access_token=TOKEN` |
| RFC 6750 rule | Clients **SHOULD** use; Resource Servers **MUST** support | Resource Servers **MAY** support; use only when conditions are met | Resource Servers **MAY** support; already discouraged in RFC 6750 |
| RFC 9700 (Security BCP) | Standard option for bearer requests | No blanket ban, though should be avoided when headers work | Clients **MUST NOT** send access tokens via query per RFC 6750 `2.3` |
| Spring Security Servlet default | **Yes** | **No**; requires explicit opt-in | **No**; requires explicit opt-in, should not be used in new systems |
| HTTP method | GET/POST/PUT/PATCH/DELETE… | Must have defined request body semantics; **never GET** | RFC 6750 describes query; `DefaultBearerTokenResolver` currently handles query for GET when enabled |
| Leak exposure | Headers can still be logged if misconfigured | Bodies can be captured/logged | URLs very easily appear in logs, history, analytics, links, caches, referrers |
| Implementation guidance | **Use** over HTTPS | Consider only for bounded compatibility | **Do not use for OAuth access tokens** |

Here, **MUST**, **MUST NOT**, **SHOULD**, and **MAY** carry normative RFC meanings, not Spring configuration names. It is important to read RFC 6750 alongside the updated **RFC 9700**: the older document retains URL transport for historical reasons, while security guidance has grown stricter.

## 3. Method 1 — Token in the `Authorization` header

### 3.1. Syntax and HTTP examples

The bearer token is placed in a **request header**:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN_EXAMPLE
Accept: application/json
```

In practice with `curl`:

```bash
curl --request GET \
  --url https://api.example.com/api/orders/42 \
  --header 'Authorization: Bearer ACCESS_TOKEN_EXAMPLE' \
  --header 'Accept: application/json'
```

For a Java client using `RestClient`, set the header using Spring's built-in helper:

```java
String accessToken = tokenService.currentAccessToken();

String body = restClient.get()
    .uri("https://api.example.com/api/orders/42")
    .headers(headers -> headers.setBearerAuth(accessToken))
    .retrieve()
    .body(String.class);
```

Modern browser example:

```javascript
const response = await fetch("https://api.example.com/api/orders/42", {
  method: "GET",
  headers: {
    Authorization: "Bearer " + accessToken,
    Accept: "application/json"
  }
});

if (!response.ok) {
  throw new Error("Request failed: " + response.status);
}
const order = await response.json();
```

The `fetch` snippet only illustrates **how to send the header**; acquiring and safely holding `accessToken` depends on the client architecture. Never hardcode real tokens into source code.

### 3.2. Advantages and practical limits

**Advantages:**

- This is the method Resource Servers **must support** per RFC 6750 and is supported by Spring Security by default.
- The token is kept out of the URL, substantially reducing leaks via browser history, access log paths, bookmarks, shared links, and URL traffic analytics.
- The header works for both `GET` and HTTP methods with bodies; APIs can send JSON, multipart, or other payloads without mixing tokens into business data.
- Common middleware, gateways, and HTTP libraries provide dedicated support for bearer authentication.

**Limits:** Headers **do not guarantee secrecy by themselves**. Tokens can still leak if a proxy logs all request headers, a tracing system collects `Authorization`, a client prints requests to logs, or an unprotected HTTP connection is used. Gateway, APM, logging, and debugging layers must strip/mask `Authorization` values. TLS and verifying target server identity remain mandatory.

### 3.3. A Bearer header is not a token in a cookie

`Authorization: Bearer ...` is explicitly attached by the client. A cookie (`Cookie: session=...`) can be sent automatically by browsers based on domain, path, and cookie policies, carrying different CSRF/risk mechanics. If an application uses a **BFF or session cookie**, the backend can store the access token server-side and set `Authorization` itself when calling downstream APIs. Do not equate session cookies with RFC 6750 access token transport.

### 3.4. CORS is not a reason to switch to query parameters

In an SPA at `https://shop.example.com` calling an API at `https://api.example.com`, the `Authorization` header can trigger a CORS preflight. The API must configure CORS for the allowed origins, methods, and headers—such as `Authorization` and `Content-Type` as needed. **Do not move tokens into query parameters to avoid preflight.** CORS is a mechanism controlling browser response access; it does not replace Resource Server authentication/authorization.

## 4. Method 2 — Token in a form-encoded request body

### 4.1. When does RFC 6750 allow it?

This method sends the `access_token` parameter in the **body** of the HTTP request:

```http
POST /api/legacy/search HTTP/1.1
Host: api.example.com
Content-Type: application/x-www-form-urlencoded

access_token=ACCESS_TOKEN_EXAMPLE&keyword=keyboard
```

Under RFC 6750 `2.2`, a client **must not use the form-body method if any of the following conditions is missing**:

1. The `Content-Type` header is `application/x-www-form-urlencoded`.
2. The body is properly encoded according to `application/x-www-form-urlencoded` rules.
3. The body is single-part, not multipart.
4. The encoded body content consists of ASCII characters per RFC constraints.
5. The HTTP method has defined request body semantics; **GET must not be used**.

If the body also contains business parameters, `key=value` pairs must be properly encoded and separated by `&`. Example:

```bash
curl --request POST \
  --url https://api.example.com/api/legacy/search \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'access_token=ACCESS_TOKEN_EXAMPLE' \
  --data-urlencode 'keyword=keyboard'
```

**Do not apply this to JSON, multipart, or GET:**

```http
POST /api/orders HTTP/1.1
Content-Type: application/json

{"access_token":"ACCESS_TOKEN_EXAMPLE","productId":123}
```

The JSON snippet above **is not** RFC 6750 form-encoded bearer transport and **is not** recognized by `DefaultBearerTokenResolver` as an access token by default. Putting `access_token` inside a business JSON field does not make Spring Security authenticate the request automatically.

### 4.2. Risks and compatibility scenarios

Form-body transport reduces URL exposure but **does not hide the token from systems that read or log request bodies**. Data can appear in APMs, middleware, reverse proxies, error reports, debug dumps, web application firewalls, or request replays. It also creates coupling to content type, body parsing behavior, and how the application accesses form parameters.

RFC 6750 states this method **SHOULD NOT** be used unless the participating browser environment cannot access the `Authorization` header. With modern environments supporting `fetch`, `XMLHttpRequest`, or full HTTP clients, that situation is rare.

A plausible use case is a **legacy client** constrained to submitting HTML forms. If compatibility must be maintained, restrict which endpoints accept form transport, require HTTPS, mask tokens from logs, use short token lifetimes, tighten audience/scope, and plan a migration to headers.

> **Easy confusion:** The OAuth 2.0 **token endpoint** commonly uses `application/x-www-form-urlencoded` for grants such as `authorization_code` and `refresh_token`. That does not mean a **Resource Server** should accept bearer access tokens via forms; those are two completely different exchanges.

## 5. Method 3 — Token in a URI query parameter

### 5.1. Historically documented syntax

RFC 6750 `2.3` documented sending a token via `access_token` in the query string:

```http
GET /api/orders/42?access_token=ACCESS_TOKEN_EXAMPLE HTTP/1.1
Host: api.example.com
```

**This is only an example for recognizing an outdated pattern, not a template to copy into applications.** RFC 6750 already discouraged this approach; **RFC 9700 `4.3.2` subsequently mandates that clients MUST NOT pass access tokens in URI query parameters as described in RFC 6750 `2.3`**. Consequently, any new client must use headers.

### 5.2. Why are URLs dangerous?

When a token sits in a URL, it easily passes through systems designed specifically to record or share addresses:

| Where the token can leak | Typical scenario |
|---|---|
| **Proxy / web server / API gateway access logs** | Log entries store the request target `/api/orders?access_token=...`. |
| **Browser history, bookmarks, and autocomplete** | Users open the URL from the address bar or save the page. |
| **Referrer** | URLs containing tokens can be sent in `Referer` under certain conditions/policies; never rely on referrer policies to keep tokens secret. |
| **Analytics, APM, error tracking, tracing** | Tools collect `url`, `path`, or query strings. |
| **Caches, CDNs, proxies** | Intermediaries may retain URLs, cache keys, or metadata; `Cache-Control` helps but does not stop all URL recording. |
| **Copying/sharing links** | Tokens stick to links pasted into chat, tickets, emails, screenshots, or docs. |
| **Monitoring / security tools** | WAFs, monitors, and testing tools may record full URIs. |

**HTTPS does not eliminate these risks.** TLS protects data in transit between appropriate endpoints, but systems at endpoints/TLS termination still see the URL and may store it. Redacting tokens from header logs is insufficient if the token is already in the query string.

**Do not treat configuring** `Cache-Control: no-store`, `private`, or `Referrer-Policy` as a justification for query bearer tokens. Those controls only partially reduce risk and do not satisfy RFC 9700.

### 5.3. Presigned URLs are not OAuth `access_token`s

Some systems issue **presigned URLs**, containing a time-limited signature in the query string for downloading a file or accessing a specific resource. That is a **different** authorization mechanism with its own signature structure, audience, lifetime, and threat model. Do not infer from the existence of presigned URLs that OAuth bearer access tokens should be embedded in `?access_token=...`.

### 5.4. If a legacy system currently uses query tokens

For systems already deployed improperly or bound by legacy integration contracts, prioritize migration:

1. Identify clients/endpoints sending `access_token` in query strings; avoid printing token values in inventory reports.
2. Update clients to send `Authorization: Bearer ...`; adjust CORS or gateway configuration where needed.
3. Narrow scopes/audience and lifetime of access tokens, and rotate tokens that may have appeared in logs.
4. Scrub or restrict access to logs, analytics, histories, and caches containing old URLs per data policy.
5. Disable query acceptance at the Resource Server and monitor failing requests to catch remaining legacy clients.

The fact that an API “works with query tokens” does not prove the practice complies with the Security BCP.

## 6. How does Spring Security Resource Server read tokens?

### 6.1. By default, it only looks in `Authorization`

For **Spring MVC / Servlet** applications, Spring Security uses a `BearerTokenResolver` to extract the bearer credential. The default implementation is `DefaultBearerTokenResolver`, which checks the `Authorization` header and **disables** form and query parameters.

Typically involved components:

```text
HTTP request
    |
    v
BearerTokenAuthenticationFilter
    |
    v
BearerTokenResolver (DefaultBearerTokenResolver)
    |-- Authorization: Bearer ...     -> read by default
    |-- form body: access_token=...   -> not read by default
    |-- URI query: access_token=...   -> not read by default
    |
    v
AuthenticationManager / JWT Decoder or OpaqueTokenIntrospector
    |
    v
SecurityContext + authorization rules
```

Minimal Gradle (Groovy DSL) dependencies for a Spring Boot application with the Boot plugin configured:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Example JWT Resource Server configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
```

`issuer-uri` must match the trusted issuer of the token provider. Beyond verifying signature, expiration, and issuer, production APIs must verify the **audience** issued for this API alongside scopes/access policies. If the deployment uses opaque tokens, substitute the appropriate introspection configuration; **where the bearer token is carried remains an independent concern**.

Configuration protecting endpoints using default header access tokens:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

`SCOPE_orders.read` illustrates the authority mapped from the `orders.read` scope by the JWT Resource Server's default converter. The code above assumes the application has appropriate issuer/JWK metadata configured and only accepts access tokens for the API. If the API also maintains session/cookie state or multiple security filter chains, configure security to match the real architecture.

### 6.2. Only when mandatory: allowing `access_token` in forms

Spring provides `DefaultBearerTokenResolver#setAllowFormEncodedBodyParameter(true)`. Illustrative configuration:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class LegacyApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
        DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();

        // Enable only if legacy form clients truly must be supported.
        resolver.setAllowFormEncodedBodyParameter(true);

        // Keep query bearer tokens disabled.
        resolver.setAllowUriQueryParameter(false);

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/api/legacy/search")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .bearerTokenResolver(resolver)
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

This is an **alternative configuration** to `ApiSecurityConfig` above, not two `SecurityFilterChain` beans to copy verbatim into the same application without clear `securityMatcher`/ordering design.

**Exact Servlet resolver scope:**

- `setAllowFormEncodedBodyParameter` defaults to `false`; when enabled, the resolver inspects only `application/x-www-form-urlencoded` bodies and does not apply to `GET`.
- `setAllowUriQueryParameter` defaults to `false`; in the current `DefaultBearerTokenResolver` implementation, query extraction is restricted to `GET` requests when enabled.
- Both flags configure **where tokens are extracted from**—they do not convert JSON payloads into forms, verify signatures, or issue new tokens.
- The standard header remains accepted. If a request carries bearer credentials in multiple sources, the resolver can detect the conflict and reject it as an invalid request.

**Why leave query disabled?** `setAllowUriQueryParameter(true)` exists for special compatibility scenarios, yet having clients send OAuth access tokens in query parameters violates RFC 9700. Keep it at the default `false` or use it only while studying a legacy migration path; never use this option in a new API.

### 6.3. What about WebFlux and custom headers?

The configuration above uses **Servlet** `DefaultBearerTokenResolver`. In **Reactive WebFlux** applications, the pipeline relies on `ServerBearerTokenAuthenticationConverter`, which has its own API and configuration; do not copy a Servlet `SecurityFilterChain` directly into a `SecurityWebFilterChain`.

Spring also supports configuring a **different header name** for specialized proxy architectures via `setBearerTokenHeaderName`. That is an ingress customization, not a replacement for standard `Authorization` for public clients. Carefully verify which proxy sets the header, whether client-supplied copies are stripped, and how tokens are redacted from logs. Avoid creating unnecessary additional token-intake channels.

## 7. What if a client sends two tokens at once?

RFC 6750 `2` states that **a request must not use more than one method to transmit the bearer token**. Do not design “prefer the header, and if invalid fall back to the query token,” as that creates discrepancies across gateways, proxies, and applications, as well as *credential confusion* risks.

Example that is **invalid** in principle:

```http
POST /api/legacy/search HTTP/1.1
Host: api.example.com
Authorization: Bearer TOKEN_IN_HEADER
Content-Type: application/x-www-form-urlencoded

access_token=TOKEN_IN_BODY&keyword=keyboard
```

When form input is enabled, `DefaultBearerTokenResolver` detects multiple bearer tokens and reports `invalid_request` instead of picking one arbitrarily. Other middleware must also agree on which source represents the trusted credential.

Distinguish these situations:

- **Token only in header:** extracted by the default parser and forwarded to validation.
- **Token only in form, form flag disabled:** not recognized as a bearer credential by the resolver; protected endpoints typically respond as unauthenticated.
- **Token only in query, query flag disabled:** similarly, query is not an accepted credential.
- **Token with invalid signature/expired:** token validation failure, regardless of whether it came from header or form.
- **Multiple tokens from enabled sources:** may fail with `invalid_request`; do not pick the “stronger” or “newer” token.
- **Valid token lacking scope:** authorization error, typically `403 Forbidden`.

Separating **rejected due to token location** from **rejected due to token contents** helps diagnose issues at the right layer.

## 8. Comparing HTTP responses and error meanings

| Scenario | Typical HTTP status | Meaning |
|---|---|---|
| `GET` without a bearer token to a protected endpoint | `401 Unauthorized` | Client did not provide a credential accepted by the API. |
| `GET` with only `?access_token=...` under default resolver | `401 Unauthorized` | Query is ignored; not treated as a bearer header token. |
| `POST` with only form `access_token=...` when support is disabled | `401 Unauthorized` | Form parameter is not read as a bearer credential. |
| Header has an expired, badly signed, or wrong-audience bearer token | `401 Unauthorized`, possibly with `invalid_token` | Credential was extracted but is invalid for this API. |
| Valid bearer header lacking required scope | `403 Forbidden`, possibly with `insufficient_scope` | Authenticated, but lacks sufficient permissions. |
| Request sends bearer token in both header and form when both are enabled | `400 Bad Request`, possibly with `invalid_request` | Violates the single-transport-method rule. |

Exact responses depend on `SecurityFilterChain` configuration, exception handling, gateways, and Spring Security version. With a default Resource Server, responses from bearer authentication typically use the `WWW-Authenticate` header, for example:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

This header is part of the **response** communicating bearer authentication errors; it is not where a client sends an access token. Clients must handle `401`/`403` semantically rather than “retrying via query” to bypass header configuration.

## 9. Protecting tokens across the entire transport path

Putting the token in the header is the best of the three methods, yet you still must protect the **entire lifecycle**:

### 9.1. Protecting the channel and destination

- Use **HTTPS** from client to API; protect proxy/gateway-to-backend hops according to the architecture.
- Verify TLS certificates and the API's exact hostname; avoid sending tokens to untrusted endpoints.
- Restrict `audience` so tokens meant for API A are rejected by API B. Constrain `scope`, lifetime, and data permissions to what is needed.
- Consider sender-constrained tokens such as mTLS-bound access tokens or DPoP in environments requiring replay reduction; these are additional controls, not a reason to use query strings.

### 9.2. Controlling logs and monitoring

Systems where real tokens should be redacted or omitted:

- Client console logs, HTTP client debug interceptors, crash reports.
- API gateways, reverse proxies, WAFs, load balancers.
- Application access logs, tracing spans, request/response logging middleware.
- APMs, monitoring tools, support tickets, analytics, and request replay recordings.

Log **correlation IDs**, HTTP methods, route templates, statuses, latency, error codes, and normalized subject identifiers when genuinely needed; never log `Authorization`, `access_token`, raw request bodies containing credentials, or full query strings.

### 9.3. Separating token protection from storage method

- **Transport:** the token travels from client to API via `Authorization`.
- **Storage:** the token is kept in memory, server-side, a secret store, or a mechanism suited to the client type and threat model.
- **Validation:** the server verifies the token and permissions.
- **Revocation/rotation:** the Authorization Server or another mechanism manages lifecycle.

Switching from query to header is an important improvement, but it does not automatically fix insecure browser storage, over-privileged tokens, missing audience validation, or token leaks through APMs.

## 10. Deployment scenarios and engineering decisions

### Scenario A — SPA calling a JSON REST API

The SPA uses `fetch` to send a JSON body and bearer header:

```http
POST /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN_EXAMPLE
Content-Type: application/json

{"productId":123,"quantity":2}
```

**Choose the header.** The token stays independent of the order creation payload. If cross-origin, configure CORS properly; if the architecture uses a BFF, the backend can make API requests with the bearer header on the browser's behalf.

### Scenario B — Legacy client capable only of HTML forms

An older system may only submit `POST application/x-www-form-urlencoded` requests. If the client cannot be updated immediately, the API can temporarily enable form support on the required endpoints, monitor closely, mask body logs, and schedule migration to headers. Never make temporary compatibility the default across all APIs.

### Scenario C — Sending a report download link via email

A request to “put the access token in the URL so the recipient just clicks it” is **unsuitable** for modern OAuth bearer transport. Better product solutions include directing recipients to a login-protected page, issuing a dedicated single-purpose/short-lived download code, or using a presigned URL mechanism designed for the specific resource. Never embed OAuth access tokens in links.

### Scenario D — WebSocket or SSE

Some browser APIs have restrictions on setting custom headers during connection setup (for example, the native `WebSocket` API). This does not automatically permit putting OAuth `access_token` values in query parameters under RFC 9700. Design an appropriate authentication mechanism: backend sessions, secure cookies where appropriate, an in-protocol credential exchange step, or a dedicated token with tightly scoped audience and lifetime by design. Evaluate CORS/origin, CSRF, replay, and protocol-specific logging. Never mix OAuth bearer access tokens into URLs merely because an HTTP client has limitations.

## 11. Quick decision table

| If you are building… | Appropriate approach |
|---|---|
| A new Spring Security REST API | Accept only `Authorization: Bearer ACCESS_TOKEN` over HTTPS. |
| A JSON API handling GET/POST/PATCH/DELETE | Put the access token in the header; keep the JSON body for business data. |
| A legacy form client unable to send headers | Consider `access_token` in form bodies only if RFC 6750-compliant and explicitly enabled with controls; prioritize a migration plan. |
| An API with `?access_token=...` from an old client | Migrate the client to headers; do not expand or design new APIs around query tokens. |
| A system needing shareable file download URLs | Use a dedicated signed URL design or login/authorization flow; do not put OAuth bearer access tokens in queries. |
| A server with JWT access tokens | Verify signature, issuer, audience, expiration, and permissions **after** receiving the bearer header. |
| A server with opaque access tokens | Use introspection and check permissions **after** receiving the bearer header. |

## 12. Standards and Spring Security documentation

- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html), especially `2.1` (Authorization header), `2.2` (form body), `2.3` (URI query), `3` (WWW-Authenticate), and `5` (Security Considerations).
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html), especially `4.3.2` (Access Token in Browser History) requiring clients **MUST NOT** send access tokens in URI query parameters.
- [Spring Security — OAuth 2.0 Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html), describing header defaults and form/custom-header configuration.
- [Spring Security — DefaultBearerTokenResolver API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/DefaultBearerTokenResolver.html), documenting `setAllowFormEncodedBodyParameter`, `setAllowUriQueryParameter`, and their defaults.

## 13. Takeaways

The three locations found in historical documentation are **header**, **form body**, and **query string**, and they are not equivalent:

- **`Authorization` header:** standard interaction between OAuth clients and Resource Servers; supported by default in Spring Security; recommended.
- **Form body `access_token`:** conditional compatibility mechanism for valid form requests only; requires explicit opt-in in Spring Security; evaluate body logging risks and restrict use cases.
- **Query `access_token`:** documented in RFC 6750 to describe legacy practice, but prohibited for OAuth clients by RFC 9700; disabled by default in Spring Security and must not be accepted in new APIs.

**A bearer token is a sensitive credential.** Placing it properly in the header is only the first layer; the system still needs HTTPS, log redaction, token verification for issuer/audience/scope, resource-level authorization checks, and an appropriate token lifecycle.
