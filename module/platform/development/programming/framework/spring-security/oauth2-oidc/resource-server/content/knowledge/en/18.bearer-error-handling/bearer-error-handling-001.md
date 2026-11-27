# Requests Missing a Token, Malformed Tokens, and Rejected Tokens

## 1. One Protected Endpoint, Three Very Different Situations

Suppose a Spring Boot application acts as an **OAuth 2.0 Resource Server** providing an orders API:

```http
GET /api/orders/42 HTTP/1.1
Host: orders.example.com
Accept: application/json
```

This endpoint requires an **OAuth 2.0 access token** presented as a Bearer credential and must have the `orders.read` permission. Learners often lump every failed API access case together as an “error token”, but there are at least three distinct situations:

1. **Request missing a token:** The client does not send any Bearer credential.
2. **Malformed token transmission:** The client sends `Authorization` with invalid Bearer syntax, or sends the credential through unsupported methods.
3. **Rejected token:** Spring Security has extracted a Bearer token string, but JWT or opaque token validation fails.

There is also another case to distinguish: **a token that validates successfully but lacks sufficient permissions** to call the endpoint. That is an *authorization* issue, not a token being rejected during *authentication*.

| Situation | Example | Typical Response |
|---|---|---|
| No token | No `Authorization` header | `401 Unauthorized`, `Bearer` challenge |
| Malformed Bearer request syntax | `Authorization: Bearer abc def` | `400 Bad Request`, `error="invalid_request"` |
| Extractable Bearer format, broken JWT | `Authorization: Bearer abc.def.ghi` | `401 Unauthorized`, `error="invalid_token"` |
| Well-structured token but expired/bad signature/issuer/audience | Bearer JWT fails validator | `401 Unauthorized`, usually `invalid_token` |
| Opaque token rejected by introspection | AS returns `{"active":false}` | `401 Unauthorized`, usually `invalid_token` |
| Authenticated token lacking scope | Has `profile.read`, needs `orders.read` | `403 Forbidden`, usually `insufficient_scope` |

The table above reflects common behaviors of the Bearer scheme according to RFC 6750 and Spring Security Resource Server. **The specific status code of a malformed request may depend on the error type, `BearerTokenResolver`, filter, and error handler in use.** You should not assume every request with a broken token returns the exact same HTTP code.

### After this lesson, you will know how to

- Distinguish **missing token**, **invalid Bearer request**, **invalid token**, and **insufficient token permissions**.
- Understand the meaning of HTTP `400`, `401`, `403`, and `WWW-Authenticate` under OAuth 2.0 Bearer Token Usage.
- Trace the processing path through `BearerTokenAuthenticationFilter`, `BearerTokenResolver`, `JwtDecoder`, or `OpaqueTokenIntrospector`.
- Configure Spring Security Resource Server to return proper challenges, protect public endpoints, and protect scope-restricted endpoints.
- Explain why `permitAll` does not guarantee an invalid Bearer token will be ignored.
- Design HTTP requests, tests, and logs to pinpoint which step produced an error.
- Avoid putting access tokens, introspection secrets, or sensitive information into error responses.

## 2. Understanding the Vocabulary: Request, Credential, and Token Validation

A common HTTP request carrying a Bearer credential:

```http
GET /api/orders/42 HTTP/1.1
Host: orders.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6ImsxIn0...
```

There are three layers to consider:

**HTTP/Bearer transport layer:** Can the `Authorization` header be interpreted as a Bearer credential? Is the Bearer credential placed where the Resource Server allows it?

**Token authentication layer:** Does the extracted string represent a token that the Resource Server is allowed to trust? For JWTs, this means verifying signature, issuer, audience, expiration, and token contract; for opaque tokens, it may require introspection.

**Authorization layer:** Does the authenticated token have sufficient scopes/authorities, Client/tenant permissions, and access rights to the record being accessed?

```mermaid
flowchart TD
    A["HTTP request"] --> B{"Has Bearer credential?"}
    B -->|No| C["No Bearer Authentication"]
    C --> D{"Public or protected endpoint?"}
    D -->|Public| OK1["Proceed to endpoint"]
    D -->|Protected| E401["401 + WWW-Authenticate: Bearer"]
    B -->|Malformed submission| E400["400 invalid_request (depends on error)"]
    B -->|Token extracted| V["JWT decoder or opaque introspector"]
    V --> G{"Token validated?"}
    G -->|No| IT["401 invalid_token"]
    G -->|Yes| P{"Sufficient permissions?"}
    P -->|No| NO["403 insufficient_scope / access denied"]
    P -->|Yes| O["Check resource/tenant then process"]
```

The diagram is a logical model. In Spring Security, many conditions are checked by different filters, and the processing order depends on configuration. Therefore, some requests are rejected in the **authentication filter before the `authorizeHttpRequests` rules run**.

### 2.1. Not Every Bearer String Is a JWT

The Bearer scheme only indicates how the credential is presented: **the bearer of the token can present the token** to access resources according to policy. The token may be:

- **JWT access token:** usually has three JWS Compact parts, verified by the Resource Server using `JwtDecoder`.
- **Opaque access token:** an unstructured string not meant for the API to read directly, verified through an introspection endpoint or equivalent trust mechanism.

Dots in a token do not by themselves prove it is a valid JWT, and a token without dots is not automatically an error if the Resource Server is designed for opaque tokens.

**Avoid using a “JWT must have three parts” regex in a Controller to replace token validation.** Let the proper `JwtDecoder` or `OpaqueTokenIntrospector` process the token according to the contract.

### 2.2. Distinguishing Authentication and Authorization

In Spring Security:

- **Authentication** answers “is this token accepted, and who is the principal?”.
- **Authorization** answers “is this authenticated principal allowed to call the endpoint and use the resource?”.

A token with a bad signature normally does not create a valid `JwtAuthenticationToken`. A token with a valid signature that lacks `SCOPE_orders.read` may create a valid Authentication and then be rejected by `AuthorizationFilter`.

## 3. The Bearer Standard: How Should `Authorization` Be Used?

RFC 6750 describes OAuth 2.0 Bearer Token Usage. The commonly recommended way to send an access token is the HTTP `Authorization` header:

```http
Authorization: Bearer <access-token>
```

Example:

```bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  'https://orders.example.com/api/orders/42'
```

`ACCESS_TOKEN` must be a real access token; this is only an illustrative command.

### 3.1. The “Bearer” Part Is the Authentication Scheme

`Bearer` is the scheme name in `Authorization`. It is not part of the access token string. The client must place the token after the scheme using proper syntax.

```text
Authorization header:
    Bearer eyJhbGciOi...

Scheme:
    Bearer

Credential:
    eyJhbGciOi...
```

A Client that prepends the `Bearer` prefix to a **stored token value that already includes the prefix**, creating the header `Authorization: Bearer Bearer ...`, will usually produce an invalid header.

Do not wrap quotes around the token as part of the credential:

```http
Authorization: Bearer "eyJhbGciOi..."
```

That is not the standard Bearer syntax expected by `DefaultBearerTokenResolver`.

### 3.2. Bearer Credentials Have Their Own Character Rules

According to the RFC 6750 Bearer token syntax, a `b64token` string may contain alphanumeric characters and certain characters such as `-`, `.`, `_`, `~`, `+`, `/`, with `=` padding according to the rules. This describes **how the credential is transmitted**, not a guarantee that the string is a valid JWT or a token issued by the AS.

A token such as:

```text
abc.def.ghi
```

may pass the Bearer header extraction step but fail in `JwtDecoder` because it is not a valid JWS.

Conversely:

```text
abc def
```

has an internal space, so it is an example of an invalid credential under standard Bearer syntax.

### 3.3. Do Not Put the Access Token in the URL to “Fix” a Broken Header

Example to avoid:

```http
GET /api/orders/42?access_token=real-secret-token HTTP/1.1
```

A token in the URL risks appearing in:

- Access logs and reverse proxy logs.
- Browser history.
- Monitoring/analytics.
- Caches or shared URLs.
- Intermediary systems that process URLs.

RFC 6750 does describe passing tokens via query or form body under specific conditions, but **`DefaultBearerTokenResolver` typically does not enable query/form token support by default**. In modern applications, use `Authorization: Bearer ...` over HTTPS.

If a system must remain compatible with a legacy Client, evaluate the risks before enabling another method; do not enable query token acceptance just to work around one malformed HTTP request.

## 4. First Case: Request Missing a Token

### 4.1. Protected Endpoint Without an Authorization Header

```http
GET /api/orders/42 HTTP/1.1
Host: orders.example.com
```

A typical response:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

The `401 Unauthorized` status in HTTP here means the request has not provided accepted authentication credentials for the protected resource; it does **not** mean a token was read and failed verification.

`WWW-Authenticate` is a **challenge** telling the Client which authentication mechanism can be used. Under OAuth Bearer, the challenge typically contains the `Bearer` scheme; when the server has a configured realm, it may be:

```http
WWW-Authenticate: Bearer realm="orders-api"
```

### 4.2. Why Does a Missing Token Usually Omit `error="invalid_token"`?

RFC 6750 recommends **not including an error code or specific error details** when the request simply lacks authentication credentials. A request without a token does not prove that any token is invalid.

Compare:

```http
# No token sent:
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
```

with:

```http
# Token sent, but token rejected:
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
```

**Do not blindly assert `error="invalid_token"` in tests for every HTTP 401.** Missing credentials and invalid credentials have different meanings.

### 4.3. Public Endpoints May Not Require a Token

If configured as:

```java
.requestMatchers("/api/public/**").permitAll()
```

then a request:

```http
GET /api/public/ping HTTP/1.1
```

is usually allowed past the authorization step, even without a Bearer token. The final status depends on the corresponding Controller or static resource.

However, **`permitAll` does not disable the Bearer authentication filter**. If a Client sends `Authorization: Bearer <invalid-token>` to a public endpoint, the filter may pick up the token and return `401` before reaching the `permitAll` rule. This is not necessarily a configuration bug.

If business requirements dictate that public routes must not process Bearer tokens at all, you can split out a separate `SecurityFilterChain` without Resource Server enabled for those routes, though you must carefully manage matchers, order, and other filters.

### 4.4. Headers Using Another Scheme May Be Treated as “No Bearer Token”

Example:

```http
Authorization: Basic dXNlcjpwYXNz
```

For a Resource Server configured only with Bearer authentication, the Bearer token resolver normally **does not treat a Basic header as a Bearer token**. If the protected endpoint requires a Bearer token, the result can still be `401` with a Bearer challenge.

Do not assume every Authorization header that does not start with Bearer is `invalid_request`. It also depends on whether the system supports other schemes or which filter processes the request.

## 5. Second Case: Malformed Bearer Token Submission

### 5.1. Invalid Header Syntax

Some illustrative requests:

```http
Authorization: Bearer abc def
```

```http
Authorization: Bearer "abc.def.ghi"
```

```http
Authorization: Bearer
```

The strings above **are not a Bearer credential according to standard header syntax**. When the resolver recognizes an attempt to present a Bearer credential that cannot be parsed properly, it may throw `OAuth2AuthenticationException` with the Bearer error `invalid_request`.

Typical response:

```http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer error="invalid_request"
```

However, how the resolver treats **a completely empty header**, whitespace, multiple headers, or unusual characters can vary by version or implementation. Write tests for your Client's actual syntax rather than relying on a single sample.

### 5.2. `invalid_request` Differs from `invalid_token`

The two errors come from different sources:

**`invalid_request`**: The Bearer credential was presented in violation of request/transport rules, such as missing a required parameter for a supported transmission method, duplicate parameters, or combining multiple token transmission methods in one request.

**`invalid_token`**: The Resource Server obtained a token string to validate, but that token is invalid for the request/API because it is expired, revoked, has a bad signature, or fails other token validation conditions.

Example:

```text
Authorization: Bearer abc def
  → credential presentation syntax error
  → may return 400 invalid_request

Authorization: Bearer abc.def.ghi
  → credential can be extracted
  → JWT decoder sees invalid token
  → usually 401 invalid_token
```

Simply having **three dots or the segment count of a JWT string** is not the sole criterion for determining which layer failed. The validator determines whether the token is valid according to the profile.

### 5.3. Sending a Token Through Multiple Mechanisms Simultaneously

RFC 6750 states the rule that a Client **must not use more than one method to transmit the Bearer token in the same request**. For example, a Client enabling tokens in both the header and query:

```http
GET /api/orders/42?access_token=some-token HTTP/1.1
Authorization: Bearer another-token
```

In an implementation that allows multiple transport methods, that situation must be rejected according to the corresponding rule, usually `invalid_request`. If query transport is not supported, the application may only look at the Bearer header and ignore `access_token` in the URL; **do not assume duplicate-token detection always happens when one transport method is disabled**.

The proper fix on the Client side: **send only one access token via the Authorization header**.

### 5.4. Characteristics of `DefaultBearerTokenResolver`

Spring Security Servlet provides `DefaultBearerTokenResolver` to extract the Bearer token from a request. Under common configuration:

- Looks for the Bearer token in the `Authorization` header.
- Does not accept tokens in query parameters or form body unless explicitly enabled.
- May raise an error if it detects a Bearer header with invalid syntax.
- Allows customizing the header name/transport options for a specific contract.

Example configuration explicitly using the default resolver:

```java
@Bean
BearerTokenResolver bearerTokenResolver() {
    return new DefaultBearerTokenResolver();
}
```

And wiring it in the appropriate DSL:

```java
.oauth2ResourceServer(oauth2 -> oauth2
    .bearerTokenResolver(bearerTokenResolver)
    .jwt(Customizer.withDefaults()))
```

These are illustrative snippets; you need to inject the bean into `SecurityFilterChain` and import the corresponding classes. For most APIs using standard Bearer headers, there is no need to declare a new resolver manually.

### 5.5. Should Query Tokens Be Enabled for Legacy Client Compatibility?

`DefaultBearerTokenResolver` provides an API to enable query parameters if the application truly requires it:

```java
DefaultBearerTokenResolver resolver =
    new DefaultBearerTokenResolver();

// Illustrates configuration capability only.
// DO NOT enable just to work around a client sending a malformed Authorization header.
resolver.setAllowUriQueryParameter(true);
```

If enabled, you must evaluate token leakage in URLs and logging/caching policies. Similarly, enabling form body tokens is only appropriate with method and media-type constraints per the RFC/implementation.

**Default recommendation:** use HTTPS and `Authorization: Bearer <token>`; fix misbehaving Clients instead of relaxing credential acceptance beyond requirements.

## 6. Third Case: Token String Rejected During Validation

### 6.1. When Does `invalid_token` Appear?

After the resolver extracts the token, the Resource Server verifies it using the configured mechanism.

For a JWT access token, conditions that can cause validation to fail include:

| Check Category | Failure Example | Meaning |
|---|---|---|
| JWT/JWS syntax | Missing segments, invalid Base64URL or JSON/JOSE | Token cannot be parsed validly |
| Signature | Signature does not match trusted key | Token data is not authentic |
| Algorithm | Token uses a disallowed algorithm | Does not meet signing policy |
| Signing key | `kid` not found in trusted JWKS | No valid key available to verify |
| Expiration | `exp` is in the past | Token has expired |
| Not-before time | `nbf` is in the future | Token is not yet valid for use |
| Issuer | `iss` differs from configured issuer | Token from an unauthorized issuer |
| Audience | `aud` lacks `orders-api` when required by API | Token intended for another Resource Server |
| Token type/profile | ID token or `typ` incompatible with access token contract | Wrong token purpose |
| Claim contract | Missing required claim or wrong type per policy | Fails token validation conditions |

For a rejected JWT, the response is usually:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

A JWKS connection failure due to network issues or decoder misconfiguration **does not necessarily mean the token itself is actually invalid**; depending on exception handling, the Resource Server may return a server error. Do not lump all IdP connectivity failures together as “fake tokens”.

### 6.2. A Bad Signature Cannot Be “Fixed” by Editing the Payload

If you take a signed JWT and edit `scope` from `profile.read` to `orders.read`, the original signature will no longer be valid.

```text
JWT before:
  payload: scope=profile.read
  signature: valid

JWT after manual edit:
  payload: scope=orders.read
  signature: unchanged
  → signature verification fails
```

A request with a manually edited token usually receives **`401 invalid_token`**, not `403 insufficient_scope`. To test the missing-scope branch, you must use a token **validly issued without that scope** or mock Authentication in an authorization test.

### 6.3. Tokens with Wrong Issuer or Audience Must Not Be Misused

Illustrative JWT payload example:

```json
{
  "iss": "https://id.example.com/realms/shop",
  "aud": ["billing-api"],
  "scope": "orders.read",
  "sub": "user-417"
}
```

If the API is `orders-api` and has an audience validator, the token must be rejected even though the issuer, signature, and scope may be valid. It was not issued for the current API.

A case with **valid issuer and valid signature but wrong audience** is a token-level validation failure, usually returning **401** depending on validator configuration.

Configuring `issuer-uri` alone should not be assumed to automatically check audience across all versions/configurations. Audience must be enforced according to the API contract.

### 6.4. `kid` and JWKS Do Not Expand Trust

A token might declare:

```json
{
  "alg": "RS256",
  "kid": "unknown-key",
  "jku": "https://keys.attacker.example/jwks.json"
}
```

If `kid` is not in the approved JWKS, the Resource Server may refresh the JWKS per policy or reject the token. **Do not dynamically fetch keys from a `jku` provided by the token** to try to make the token valid, as a Client could choose its own key source.

Failure to verify the signature/key still belongs to **authentication failure**, not missing `SCOPE_`.

## 7. Rejected Opaque Tokens: `active=false` and Introspection Errors

### 7.1. Introspection Response

A Resource Server using opaque tokens can send the token to a trusted introspection endpoint:

```http
POST /oauth2/introspect HTTP/1.1
Host: id.example.com
Authorization: Basic <resource-server-credentials>
Content-Type: application/x-www-form-urlencoded

token=<opaque-access-token>
```

The Authorization Server may return:

```json
{
  "active": false
}
```

This response states that under the current introspection policy, the token is not accepted. Spring Security typically treats this as an **authentication failure** and returns `401` to the Client calling the API.

An inactive token may have expired, been revoked, not exist, or not be accepted for the introspecting Resource Server. Do not expose those internal reasons in the external HTTP response.

### 7.2. `active=true` Does Not Guarantee API Permission

Another response:

```json
{
  "active": true,
  "aud": ["orders-api"],
  "scope": "profile.read",
  "sub": "user-417"
}
```

The token may pass introspection and audience validation, yet lack the `orders.read` scope. If the endpoint requires `SCOPE_orders.read`, the result is usually `403`, not `401`.

If `active=true` but the audience is `billing-api` and the contract requires `orders-api`, the API must reject it via token-level validation or an AS-enforced resource-binding mechanism. **`active` does not automatically replace audience/authorization policies.**

### 7.3. Introspection Endpoint Errors Differ from Rejected Tokens

Two outcomes must be separated:

**AS processes successfully and returns an inactive token:**

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"active":false}
```

**AS cannot process the introspection request:** TLS error, network timeout, invalid introspection credentials, AS returns 5xx, or protocol mismatch.

The second case is an **availability/configuration issue in the authentication system**, which cannot confirm that the Client's access token is actually invalid. The Resource Server must deny access safely when it cannot verify, though the final status may be a server error rather than `401 invalid_token`.

**Do not “fail open”** by letting all opaque tokens pass when the AS is unavailable.

## 8. HTTP Rules: What Do `400`, `401`, and `403` Mean?

### 8.1. `400 Bad Request` — Invalid Bearer Request

Under the Bearer error model, `invalid_request` can be used when a request carries malformed Bearer credentials or uses multiple token submission methods in violation of the rules.

Illustrative response:

```http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer realm="orders-api", error="invalid_request"
```

Not all HTTP parsing errors go through the Bearer entry point: the Servlet container, proxy, or web server may reject the request before Spring Security processes it.

### 8.2. `401 Unauthorized` — Authentication Required or Not Accepted

A request missing credentials usually receives:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
```

A rejected token usually receives:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
```

`401` here is a historical HTTP status named “Unauthorized”, but semantically it usually means **missing or unaccepted authentication credentials**. It does not necessarily mean a token was received and failed.

### 8.3. `403 Forbidden` — Authenticated, but Insufficient Permissions

A token may be valid and produce an Authentication, yet lack an authority:

```text
GrantedAuthority:
  SCOPE_profile.read

Endpoint requires:
  SCOPE_orders.read
```

The Bearer response may be:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
```

The `scope` parameter in the challenge, if used, can provide a hint of the required scope:

```http
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.read"
```

Not every default handler automatically knows or puts the exact required scope for every endpoint into the header. **Do not fabricate a specific scope in the challenge if the application has no basis to compute it.**

### 8.4. Quick Decision Table

| Request | Condition | Typical Response |
|---|---|---|
| Protected, no Authorization header | Unauthenticated | `401` + `WWW-Authenticate: Bearer` |
| Protected, `Authorization: Basic ...`, Bearer-only enabled | No matching Bearer credential | `401` + Bearer challenge |
| Malformed Bearer header syntax | `invalid_request` | `400` + Bearer error |
| Extractable Bearer token but invalid JWT | `invalid_token` | `401` + Bearer error |
| Expired/bad signature/wrong issuer JWT | `invalid_token` | `401` |
| JWT with wrong audience per policy | Fails token validation | `401` |
| Opaque introspection `active=false` | Inactive token | `401` |
| Valid JWT/opaque token but missing scope | Insufficient endpoint permissions | `403` |
| Valid token with scope but wrong owner/tenant | Insufficient resource permissions | `403` or `404` per policy |
| Introspection endpoint timeout | Unable to verify | Deny safely; status depends on error/handler |
| Public endpoint without token | `permitAll` | Proceeds to Controller; may return `200` |
| Public endpoint with broken Bearer token | Authentication filter may run before `permitAll` | May return `401` |

The outcomes in the table are an **expected model for design and testing**, not a guarantee for every Spring Security version or custom filter chain.

## 9. `WWW-Authenticate`: Reading Bearer Challenges Properly

### 9.1. Not Every Error Response Has a JSON Body

Under HTTP authentication and RFC 6750, `WWW-Authenticate` is the key header indicating the authentication scheme and Bearer error information. Clients should not only parse a JSON body and ignore headers.

A request missing a token might receive:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Content-Length: 0
```

A rejected token might receive:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token", error_description="Token validation failed"
```

The body may be empty or customized by the application/gateway. If building a custom JSON error API, you still need to preserve `WWW-Authenticate` semantics when returning Bearer challenges.

### 9.2. Common Challenge Parameters

| Parameter | Meaning | Note |
|---|---|---|
| `realm` | Name of the protection space/resource | Declared by the server, not the access token |
| `error` | Bearer error code | Usually `invalid_request`, `invalid_token`, `insufficient_scope` |
| `error_description` | Short description for the Client | Do not expose stack traces, tokens, or security internals |
| `error_uri` | URI to documentation explaining the error | Only use trusted documentation addresses, never embed tokens |
| `scope` | Required scope for the protected resource in an appropriate context | Do not assume every `403` response includes this parameter |

### 9.3. Do Not Confuse `realm` with `issuer`

Example:

```http
WWW-Authenticate: Bearer realm="orders-api"
```

`orders-api` is only a **realm/challenge parameter** set by the Resource Server. It is **not** `iss` in the access token, not an OAuth Client ID, and not proof that the token was issued for the right audience.

### 9.4. Be Careful with Error Descriptions

Do not send:

```http
WWW-Authenticate: Bearer error="invalid_token", error_description="Private key kid=prod-signing-2026 missing; token=eyJ..."
```

This description leaks unnecessary data. A safe response should provide just enough for the Client to know it needs a valid token or appropriate permissions, while diagnostic details belong in controlled internal logs.

Do not place refresh tokens, session secrets, raw JWTs, or introspection Client secrets in error headers or bodies.

## 10. Which Components Handle Bearer Requests in Spring Security?

### 10.1. General Servlet Flow

A Servlet Resource Server application typically passes through these components:

```mermaid
flowchart TD
    HTTP["HTTP request"] --> FCP["FilterChainProxy selects SecurityFilterChain"]
    FCP --> BTF["BearerTokenAuthenticationFilter"]
    BTF --> RES{"BearerTokenResolver"}
    RES -->|No Bearer token| NEXT["Continue filter chain"]
    RES -->|Bad request syntax| EP["AuthenticationEntryPoint"]
    RES -->|Token extracted| AM["AuthenticationManager"]
    AM --> JP["JwtAuthenticationProvider + JwtDecoder<br/>or OpaqueTokenAuthenticationProvider"]
    JP -->|AuthenticationException| FAIL["FailureHandler → AuthenticationEntryPoint"]
    JP -->|Success| CTX["SecurityContext holds Authentication"]
    NEXT --> AUTHZ["AuthorizationFilter and policy"]
    CTX --> AUTHZ
    AUTHZ -->|Insufficient permissions| AD["AccessDeniedHandler / ExceptionTranslationFilter"]
    AUTHZ -->|Allowed| CTRL["Controller → Service"]
```

Exact filter ordering and error handling may vary by version/configuration, but the primary boundaries remain the same:

- **Resolver** handles how the credential is sent.
- **Authentication provider/decoder/introspector** decides whether the token is accepted.
- **Authorization** decides whether the authenticated token has permission to call the resource.

### 10.2. `BearerTokenAuthenticationFilter`

This filter typically:

1. Asks `BearerTokenResolver` to find a Bearer token in the request.
2. If no token is present, lets the request continue; a downstream protected rule may require Authentication and return `401`.
3. If the resolver throws an error, triggers appropriate authentication failure handling.
4. If a token is present, sends an authentication request to `AuthenticationManager`.
5. If authentication fails, invokes the failure handler/entry point.
6. If authentication succeeds, stores the Authentication in the SecurityContext per the configured strategy and continues.

One crucial point: **an invalid token can be rejected right inside `BearerTokenAuthenticationFilter`**, meaning before the request ever reaches `AuthorizationFilter`.

### 10.3. `ExceptionTranslationFilter` and Bearer Failures

`ExceptionTranslationFilter` bridges `AuthenticationException` or `AccessDeniedException` thrown downstream from it to an HTTP response. For an unauthenticated request hitting a protected authorization rule, it typically calls `AuthenticationEntryPoint`.

However, for a token rejected directly inside the Bearer authentication filter, the error may be handled directly by the filter's failure handling mechanism — **not necessarily caught and handled by `ExceptionTranslationFilter`**.

This explains why a custom `@ControllerAdvice` for Controllers does not always catch JWT/opaque token errors: the request is usually rejected in Servlet security filters **before reaching the Controller**.

### 10.4. `BearerTokenAuthenticationEntryPoint`

Spring Security provides `BearerTokenAuthenticationEntryPoint` to generate Bearer challenge responses when authentication fails or no suitable Authentication is present.

It can be configured with a realm and handle the corresponding Bearer error information.

### 10.5. `BearerTokenAccessDeniedHandler`

`BearerTokenAccessDeniedHandler` is used in a Bearer Resource Server context when Authentication is present but the request is denied permission. For a token authenticated via Bearer, it can produce `403` and the `insufficient_scope` Bearer challenge.

Do not write a custom AccessDeniedHandler that returns `invalid_token` for every missing-scope case. Doing so misleads the Client into thinking it must swap tokens because the token failed validation, when the actual problem is **insufficient granted permissions**.

### 10.6. Do Not Conflate All `AccessDeniedException` Cases into One Error Type

`AccessDeniedException` can arise because of:

- Missing endpoint scope/authority.
- Missing role.
- No permission for the tenant or record.
- Method security denial.
- Denial by a custom authorization manager.

`insufficient_scope` is appropriate when OAuth scope permissions are lacking, but it is not necessarily a good description for every business error, especially object-level authorization. Choose error details per API policy; do not leak the owner/tenant of unauthorized resources.

## 11. Configuring a Spring Boot Resource Server Application with JWT

### 11.1. Gradle Dependencies

Example:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

The Spring Boot plugin and Java/Spring Security versions must be configured appropriately for your real project.

### 11.2. `issuer-uri` for JWT Access Tokens

```yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com/realms/shop
```

The issuer address is an example, not a live Authorization Server. Spring Security can use the trusted issuer's metadata/JWKS to verify JWTs and apply issuer/timestamp validators.

**Ensure audience binding:** A token for `billing-api` must not be accepted by default at `orders-api` just because both share the same issuer. If `aud=orders-api` is required, configure an audience validator or equivalent mechanism for your project version.

### 11.3. SecurityFilterChain: Public API and Scope-Protected API

```java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(s -> s
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Here:

- `/api/public/**` does not require Authentication at the authorization step.
- `GET /api/orders/**` requires `SCOPE_orders.read`.
- `POST /api/orders` requires `SCOPE_orders.write`.
- `anyRequest().denyAll()` restricts endpoints without an explicit policy.
- `oauth2ResourceServer(...jwt(...))` enables Bearer JWT acceptance.
- `STATELESS` suits APIs that do not use sessions to authenticate Bearer requests.

The `csrf.disable()` example is only appropriate when the API accepts Bearer tokens via headers and **does not use cookies as credentials automatically sent by browsers**. If the application uses sessions/cookies, CSRF must be evaluated separately.

### 11.4. Minimal Controller

```java
package com.example.orders;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/orders/{orderId}")
    public Map<String, String> order(
            @PathVariable String orderId,
            @AuthenticationPrincipal Jwt jwt) {

        return Map.of(
            "orderId", orderId,
            "subject", jwt.getSubject());
    }
}
```

This Controller only illustrates the difference between public and protected routes. **Do not use it as-is for a production orders API**: you still must verify the principal's permissions for `orderId`, tenant, and which attributes may be returned.

This snippet does not declare a `POST /api/orders` handler. The authorization rule for POST can exist even without a matching Controller yet; when authenticated/authorized but unmapped, the route may return `404` or `405` depending on the request.

## 12. Configuring the Realm and Keeping Bearer Error Handlers Purpose-Aligned

### 12.1. Using Built-in Entry Points and Handlers

When a fixed realm is needed so Clients recognize the protection space, you can configure:

```java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;

@Configuration
public class BearerErrorConfig {

    @Bean
    BearerTokenAuthenticationEntryPoint bearerEntryPoint() {
        BearerTokenAuthenticationEntryPoint entryPoint =
            new BearerTokenAuthenticationEntryPoint();
        entryPoint.setRealmName("orders-api");
        return entryPoint;
    }

    @Bean
    BearerTokenAccessDeniedHandler bearerAccessDeniedHandler() {
        BearerTokenAccessDeniedHandler handler =
            new BearerTokenAccessDeniedHandler();
        handler.setRealmName("orders-api");
        return handler;
    }
}
```

Configure the Resource Server DSL with the injected beans:

```java
.oauth2ResourceServer(oauth2 -> oauth2
    .authenticationEntryPoint(bearerEntryPoint)
    .accessDeniedHandler(bearerAccessDeniedHandler)
    .jwt(Customizer.withDefaults()))
```

This replaces the `oauth2ResourceServer` portion of `ApiSecurityConfig` in the previous section. In a project, use constructor injection or bean method parameters for `bearerEntryPoint` and `bearerAccessDeniedHandler`.

If the application has multiple `SecurityFilterChain` beans, apply the entry point/handler to the API chain rather than causing a form-login web chain to unintentionally emit Bearer challenges.

### 12.2. Do Not Turn `401` into `200` So the “Client Doesn't Throw an Error”

Some systems want to return uniform JSON, such as:

```json
{
  "code": "TOKEN_INVALID",
  "message": "Access token is not accepted"
}
```

You can add a JSON body for authentication errors according to your API contract, but **the HTTP status should still reflect the actual error** and `WWW-Authenticate` should be preserved when the Bearer scheme applies.

Do not use:

```http
HTTP/1.1 200 OK

{"success":false,"error":"TOKEN_INVALID"}
```

for a protected request with an invalid token. HTTP 200 can mislead Clients, gateways, monitoring, and caches into treating the request as successful.

### 12.3. Be Careful When Customizing `AuthenticationEntryPoint`

If writing a custom `AuthenticationEntryPoint` to return JSON:

1. Keep HTTP `401` or `400` matching the actual Bearer error.
2. Keep the standard `WWW-Authenticate` challenge.
3. Do not expose raw tokens or cryptographic/AS details.
4. Do not return exception stack traces to the Client.
5. Write the response only once; avoid sending additional body content after the response is committed.
6. Ensure both resolver errors and decoder errors flow through the expected handling path.

In many systems, using the built-in entry point is less risky than writing a completely custom one just to change a JSON message.

## 13. Audience Validator: Syntactically Valid Tokens Can Still Be Rejected

A JWT may pass signature, expiration, and issuer verification while its `aud` is not intended for `orders-api`.

Example adding an audience validator in Spring Security:

```java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoders;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtValidationConfig {

    @Bean
    JwtDecoder jwtDecoder() {
        String expectedIssuer =
            "https://id.example.com/realms/shop";
        String expectedAudience = "orders-api";

        NimbusJwtDecoder decoder =
            (NimbusJwtDecoder)
                JwtDecoders.fromIssuerLocation(expectedIssuer);

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains(expectedAudience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Invalid audience",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(expectedIssuer),
                audience));

        return decoder;
    }
}
```

This decoder bean validates the audience alongside the declared issuer/timestamp validators. It must match your Spring Security version. When creating a custom decoder, ensure you **do not omit the required default validators** when adding audience checks.

For a token with the wrong audience, the API typically returns `401 invalid_token`. For a token with the right audience but missing scope, the API typically returns `403 insufficient_scope`. These two cases should be tested separately.

## 14. Configuring Opaque Tokens and Differences in Errors

If the Authorization Server issues opaque tokens, use introspection configuration instead of a JWT decoder.

Spring Boot example:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.com/oauth2/introspect
          client-id: INTROSPECTION_CLIENT_ID_FROM_SECRET_STORE
          client-secret: INTROSPECTION_CLIENT_SECRET_FROM_SECRET_STORE
```

The credential names are placeholders, not real secrets. When deploying, use environment variables or an appropriate secret manager instead of hardcoding Client secrets in source code.

In `SecurityFilterChain`:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
```

Key branches:

- No token → protected endpoint usually returns `401`.
- Malformed Bearer request → resolver may return `400 invalid_request`.
- Opaque token introspected and returns `active=false` → usually `401 invalid_token`.
- `active=true` but audience does not match the contract → API must reject via appropriate policy.
- `active=true` with right audience but missing scope → usually `403`.
- AS introspection times out/fails TLS → **upstream authentication failure**, must not fail open.

**Do not use `JwtDecoder` for opaque tokens just because an arbitrary string happens to contain dots.** The Resource Server must know the token mechanism according to the AS contract.

## 15. Endpoint Authorization and Resource Permissions

### 15.1. Scopes Are Mapped to Authorities

With a JWT:

```json
{
  "scope": "orders.read profile.read"
}
```

or an introspection response:

```json
{
  "active": true,
  "scope": "orders.read profile.read"
}
```

under Spring Security's standard mapping mechanism, you may receive:

```text
SCOPE_orders.read
SCOPE_profile.read
```

The rule:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

only checks whether the `SCOPE_orders.read` authority is present. `orders.read` is not automatically translated into permission to view **every order of every tenant**.

### 15.2. Missing Scope Is Usually 403, Not 401

Token:

```json
{
  "iss": "https://id.example.com/realms/shop",
  "aud": ["orders-api"],
  "sub": "user-417",
  "scope": "profile.read"
}
```

If valid under all token-level validators, it can become an Authentication and then be rejected by `hasAuthority("SCOPE_orders.read")`. This is an **authorization failure** and typically returns `403`.

A test for missing scope must use a **real token issued without that scope**, or a mocked authenticated Authentication—not by editing a signed JWT string.

### 15.3. Having the Scope Still Requires Tenant and Owner Checks

For the request:

```http
GET /api/tenants/tenant-beta/orders/order-42 HTTP/1.1
Authorization: Bearer <token-of-tenant-alpha>
```

even if the token is unexpired and has `orders.read`, the API must not return Beta's order if the caller is only allowed to access Alpha.

The repository should scope the query:

```sql
SELECT id, tenant_id, owner_subject, amount
FROM orders
WHERE id = :order_id
  AND tenant_id = :verified_tenant_id
  AND owner_subject = :verified_subject;
```

The `verified_tenant_id` and `verified_subject` values must come from Authentication/trusted authority sources. Do not take `tenant_id` solely from a Client-supplied URL/header and treat it as authorization.

If no record is found within the authorized scope, the API may return `404` to avoid revealing the existence of out-of-scope resources. This is an **object-level authorization** policy, distinct from Bearer token errors.

## 16. Errors on Public Endpoints: Why Does `permitAll` Sometimes Still Return 401?

Consider the configuration:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .anyRequest().authenticated())
.oauth2ResourceServer(oauth2 ->
    oauth2.jwt(Customizer.withDefaults()))
```

Four requests can behave differently:

| Request to `/api/public/ping` | Bearer authentication filter | Typical Outcome |
|---|---|---|
| No Authorization header | No token to authenticate | Endpoint permitted |
| Valid Bearer token | Authenticates token | Endpoint permitted |
| Bearer token rejected by decoder | Authentication fails before authorization | May return `401` |
| Malformed Bearer header syntax | Resolver may throw an error | May return `400` |

This explains why a public API with `permitAll` still returns an authentication error if a Client sends a broken credential.

### 16.1. When Should You Split a SecurityFilterChain?

If the requirement is that a public endpoint **must not attempt to authenticate Bearer tokens**, you can design a separate chain:

```java
@Bean
@Order(1)
SecurityFilterChain publicApi(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/public/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().permitAll())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain protectedApi(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
```

You need to import `@Order` and related classes. This is an alternative example illustrating chain selection, not a complete configuration with all scopes, CSRF, CORS, or catch-all rules for a production app. If there are endpoints outside `/api/**`, you must add a chain/policy covering them appropriately.

**Spring Security picks the first matching chain**; it does not merge filters from two chains. A separate public chain can let requests through even with an invalid Bearer header, because it does not enable the Resource Server Bearer filter. In return, you must understand clearly which security filters are present or absent on the public chain.

### 16.2. Do Not Use `web.ignoring()` to Fix Every Error

Completely bypassing Spring Security is not the same as `permitAll`. When ignoring paths, protections such as security headers or corresponding filter policies may not be applied. For public HTTP endpoints, `permitAll` in the appropriate chain is usually the less surprising choice.

## 17. CORS, Reverse Proxies, and Errors That Look Like Token Errors

### 17.1. Browser Preflights Usually Have No Bearer Token

A cross-origin frontend calling an API may send:

```http
OPTIONS /api/orders/42 HTTP/1.1
Origin: https://shop.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

A preflight is not the actual order-reading request and usually does not send a Bearer token. If the application requires Authentication before handling CORS, the browser may display a **CORS error**, even though the token in the actual request is valid.

Configure CORS properly on the API chain and only allow appropriate origins/methods/headers. Do not solve it by calling `permitAll()` on the entire API.

### 17.2. Gateways Stripping the Authorization Header

An initial request contains:

```http
Authorization: Bearer <valid-token>
```

but the reverse proxy does not forward the header to the backend. The Resource Server sees a **request missing a token** and returns `401`.

Therefore, when a Client insists “I sent the token”, trace the request path through gateways/proxies. Never ask the Client to log the real token as proof; check header presence, request IDs, and secret-masked information instead.

### 17.3. Web Form Login Chains Can Return 302 Instead of 401

If an application has multiple `SecurityFilterChain` beans and an API request accidentally matches the web form-login chain, a missing token may result in:

```http
HTTP/1.1 302 Found
Location: /login
```

This is more likely a symptom of wrong **chain selection** than an invalid Bearer token. Check `securityMatcher` and `@Order` before customizing the entry point.

### 17.4. HTTPS Must Be Protected End-to-End

A Bearer token is a credential: anyone holding the token can attempt to use it. Transmit it over HTTPS from Client to gateway and over internal connections according to policy. Do not print tokens in URLs, logs, error bodies, or monitoring.

Returning an HTTP 401 properly does not protect the system if the token has already leaked over an insecure channel.

## 18. Hands-on with curl: Identifying 401, 400, and 403

Assume the app runs at `http://localhost:8080` in a development environment, with the Controllers `/api/public/ping`, `/api/orders/42`, and `SecurityFilterChain` from section 11. Real environments require HTTPS.

### 18.1. No Token on a Public Endpoint

```bash
curl -i 'http://localhost:8080/api/public/ping'
```

If the endpoint exists and handles the request successfully, it usually returns `200 OK`.

### 18.2. No Token on a Protected Endpoint

```bash
curl -i 'http://localhost:8080/api/orders/42'
```

Typical result:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

If a realm is configured, the header may be `Bearer realm="orders-api"`.

### 18.3. Malformed Bearer Header Syntax

```bash
curl -i \
  -H 'Authorization: Bearer abc def' \
  'http://localhost:8080/api/orders/42'
```

With standard Bearer resolvers, the request is expected to be treated as malformed syntax and may return `400 Bad Request` with `error="invalid_request"`.

An HTTP intermediary may process headers before the backend; observe actual behavior if the outcome differs.

### 18.4. JWT-like String That Is Invalid

```bash
curl -i \
  -H 'Authorization: Bearer abc.def.ghi' \
  'http://localhost:8080/api/orders/42'
```

This string can be extracted from the header, but it is not a JWT with a valid signature. With a JWT decoder, it typically returns `401` and `invalid_token`.

### 18.5. Expired Access Token

If `EXPIRED_ACCESS_TOKEN` is genuinely a token signed by the AS that has expired:

```bash
curl -i \
  -H "Authorization: Bearer $EXPIRED_ACCESS_TOKEN" \
  'http://localhost:8080/api/orders/42'
```

Typical result is `401 invalid_token`. Do not manually edit `exp` in an existing token payload to simulate an expired token, as doing so breaks the signature and prevents isolating the cause.

### 18.6. Valid Token Missing Scope

If `VALID_TOKEN_WITHOUT_ORDERS_READ` is a real token with the right audience/issuer and unexpired, but lacks `orders.read`:

```bash
curl -i \
  -H "Authorization: Bearer $VALID_TOKEN_WITHOUT_ORDERS_READ" \
  'http://localhost:8080/api/orders/42'
```

Typical result is `403 Forbidden`. This is an authorization check, not token validation.

### 18.7. Valid Token with Sufficient Scope

```bash
curl -i \
  -H "Authorization: Bearer $VALID_TOKEN_WITH_ORDERS_READ" \
  'http://localhost:8080/api/orders/42'
```

If the token has the right issuer/audience, is unexpired, has `orders.read`, and the demo Controller is active, you may receive:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"orderId":"42","subject":"user-417"}
```

This response is only an example; the subject depends on the token. Real APIs also need tenant and ownership checks.

### 18.8. Notes When Using curl

- The `-i` flag displays **response headers**, which is important for inspecting `WWW-Authenticate`.
- Do not use `-L` when trying to observe a 302 returned by a form login chain, as it will follow the redirect.
- Avoid using `-v` with real tokens in logs/tickets because it may print the Authorization header.
- Do not paste production tokens or introspection secrets into bug reports.
- HTTP `localhost` is for labs only; real environments require HTTPS.
- All token variables in examples assume tokens validly prepared from the AS/lab, not arbitrary typed strings.

## 19. Authorization Tests and Decoder Tests Are Two Separate Goals

### 19.1. MockMvc with `spring-security-test`

A test can verify that an endpoint requires Authentication:

```java
package com.example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BearerAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void missingTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedWithoutScopeIsForbidden() throws Exception {
        mvc.perform(get("/api/orders/42")
                .with(jwt()
                    .jwt(token -> token.subject("user-417"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_profile.read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedWithScopePassesEndpointRule() throws Exception {
        mvc.perform(get("/api/orders/42")
                .with(jwt()
                    .jwt(token -> token.subject("user-417"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk());
    }
}
```

Tests using `with(jwt())` simulate a valid JWT `Authentication` for **authorization tests**; they **do not actually invoke `JwtDecoder` or verify JWK/signature/issuer/audience**.

To prevent the test application from looking up metadata for the example issuer on startup, the project can supply a suitable decoder/JWKS fixture or mock `JwtDecoder` in the test context depending on the Spring Boot version. Do not conclude JWT validation is correct merely because tests with mocked principals pass.

### 19.2. Testing Malformed Bearer Headers

Another test exercises the HTTP filter:

```java
@Test
void malformedBearerHeaderIsRejected() throws Exception {
    mvc.perform(get("/api/orders/42")
            .header("Authorization", "Bearer abc def"))
        .andExpect(status().isBadRequest());
}
```

Under standard `DefaultBearerTokenResolver` configuration, this string is treated as an invalid Bearer request. If the app uses a custom resolver, verify the outcome against its specific contract.

### 19.3. Testing JWTs with Bad Signatures or Expiration

To verify the real `JwtDecoder` rejects them:

- Prepare test JWKS/public keys.
- Create a JWT signed with a valid key and a JWT signed with an untrusted key.
- Create an expired JWT **properly signed** with the test key.
- Create a JWT with a valid signature but wrong issuer or audience.
- Send requests through the security filters and real decoder.
- Assert `401` and no Controller/business side effects.

If you only send the string `not-a-jwt`, you have only proven the parser/decoder rejects malformed tokens—not that the audience or expiration validators work properly.

### 19.4. Testing Opaque Introspection

For opaque tokens, use a mock introspection endpoint to return:

```json
{"active":false}
```

and:

```json
{
  "active":true,
  "aud":["orders-api"],
  "scope":"profile.read",
  "sub":"user-417"
}
```

Then verify `401` for an inactive token and `403` for an active token with the right audience but missing scope, **provided the Resource Server has configured audience and authority mapping appropriately**.

Spring Security Test's `with(opaqueToken())` typically mocks Authentication and does not by itself prove HTTP introspection was called or `active=false` is handled properly. Integration tests or dedicated introspector tests are needed for those conditions.

## 20. Investigating Errors Stage by Stage

When encountering an unexpected response, first pinpoint which stage stopped the request.

### 20.1. Missing `WWW-Authenticate` Even Though Protected Endpoint Returned 401

Possible causes:

- A custom error handler replaced the Bearer entry point.
- A gateway/proxy modified the response.
- The request went through a different `SecurityFilterChain`.
- The application manually returned `401` from a Controller.
- Another HTTP error occurred before Spring Security.

Do not simply add the header in a Controller before identifying the actual filter chain and entry point.

### 20.2. Request Missing Token Returns 403

This may be due to a custom authorization/error handler configuration or another authentication mechanism running. Inspect the selected `SecurityFilterChain`, current Authentication, and how `ExceptionTranslationFilter` chooses the entry point/AccessDeniedHandler.

### 20.3. Request with Modified Token Returns 403

If an actually invalid token still produces an Authentication, check whether the decoder/introspection ran and whether tests are using `with(jwt())` or a pre-installed mock Authentication.

Do not rely on `403` to conclude a JWT was verified; the status must be interpreted within the actual pipeline context.

### 20.4. API Missing Token Redirects to `/login`

This usually involves a form-login entry point or a web chain being selected. If the Resource Server should return Bearer challenges, check `securityMatcher`, `@Order`, and `oauth2ResourceServer` in the API chain.

### 20.5. Client Says Token Was Sent, Backend Says Missing

Check:

- Did the `Authorization` header actually reach the backend through proxies/gateways?
- Did the Client accidentally send the token in query/body instead of the header?
- Is there an invalid space or control character?
- Did the frontend send an unauthenticated `OPTIONS` preflight before the actual request?
- Did an interceptor overwrite the header with `Basic` or a stale token?
- Did two HTTP client interceptors both add conflicting Authorization headers?

When diagnosing, **only confirm header presence and scheme**; do not expose the full token in logs.

## 21. Appropriate Logging Without Leaking Tokens

In development environments, you can enable Spring Security logging:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web: TRACE
```

Actual log levels and messages vary by version. Do not leave TRACE enabled long-term in production if logs could contain sensitive data or consume excessive resources.

Useful details to track:

| Information | Purpose |
|---|---|
| Request/correlation ID | Correlate logs across gateway, API, and AS |
| HTTP method and route pattern | Identify the endpoint needing protection |
| Selected SecurityFilterChain | Verify whether the API or web chain handled it |
| “Bearer credential present?” | Know if a header/token exists without leaking its value |
| Error category `invalid_request`/`invalid_token` | Distinguish transport vs token validation |
| Failing validator (bounded detail) | Diagnose issuer/audience/exp |
| Scope/authority rule outcome | Diagnose missing permissions |
| Introspection latency and AS status | Distinguish inactive token vs AS outage |
| Response status and sanitized `WWW-Authenticate` | Confirm API contract |

**Do not log:** raw Bearer tokens, refresh tokens, Client secrets, private keys, HTTP Basic introspection credentials, or unnecessary sensitive claim contents.

### 21.1. Do Not Return Detailed Decoding Errors to the Client

A message like “JWT JSON invalid” is sometimes helpful during development, but not necessarily suitable to expose in production. For authentication errors, return just enough information and record internal diagnostics under the principle of data minimization.

Never echo the verbatim token in errors, even when the token is expired.

## 22. How Should the Client React?

### 22.1. When Receiving 401 Without a Token

The Client should check its authentication flow and supply an appropriate **access token** for the API if authorized. Do not send an OIDC ID token in place of an access token.

### 22.2. When Receiving 400 invalid_request

The Client needs to fix how it transmits the Bearer credential:

- Use only one `Authorization: Bearer ...` header.
- Do not add the `Bearer` scheme twice.
- Do not include spaces/quotes/invalid characters inside the token.
- Do not simultaneously place the access token in both query and header.
- Do not send the token in the URL just to bypass a header error.

This is a request formatting error; **simply requesting a new access token will not solve it**.

### 22.3. When Receiving 401 invalid_token

The Client may need to re-run the flow to obtain an access token, use a valid new token, or handle expiry per the OAuth mechanism granted to the Client.

Not every `invalid_token` is an expired token. If the token has the wrong audience/issuer, **refreshing and obtaining a token with the same wrong audience** can still be rejected. The Client/AS must issue tokens for the proper resource and profile.

Only Clients with the proper authority and mechanism should execute a refresh-token flow. Resource Servers should not accept refresh tokens to exchange for access tokens at business APIs.

### 22.4. When Receiving 403 insufficient_scope

An authenticated Client lacking permissions should handle it according to policy:

- Do not automatically try a stronger scope that the user/Client was not granted.
- Do not retry infinitely with the same token.
- May prompt the user/administrator to grant permissions or perform an additional authorization flow where allowed by contract.
- Understand that an API may return `403` due to tenant/owner/role even if the token has every expected scope.

Display an appropriate business message rather than always logging the user out upon seeing any `403`.

## 23. Common Real-World Misconceptions

| Symptom | Hasty Assumption | Cause to Investigate |
|---|---|---|
| `401` with no error code | “Token has a bad signature” | **No token may have been sent** |
| `400 invalid_request` | “Token has expired” | Bearer header may be malformed |
| `401 invalid_token` | “Just change the scope” | Signature, issuer, audience, or `exp` may be wrong |
| `403` with a valid token | “Spring doesn't understand JWT” | Missing `SCOPE_` or resource permissions |
| `401` on a public route | “`permitAll` is broken” | Client may have sent a bad Bearer token to a chain with an authentication filter |
| `302` to login | “Bearer token was rejected” | Request may have hit a web form-login chain |
| `401` only from browser | “JWT is invalid” | Could be CORS preflight or gateway/header issue |
| AS introspection HTTP 200 | “Token is definitely active” | Response might be `{"active":false}` |
| Opaque token `active=true` | “Allowed to call any API” | Still requires audience, scope, tenant/owner |
| `with(jwt())` test returns 200 | “Real signature is valid” | Test may be bypassing the decoder |
| Editing JWT payload returns 401 | “Missing scope” | Editing payload invalidated the signature |
| `WWW-Authenticate` missing | “Not using Spring Security” | Custom handler/gateway may have altered headers |
| `401` when JWKS endpoint is down | “Token is definitely fake” | Verification system may be unable to fetch keys |
| Valid token but API returns 404 | “JWT is wrong” | Controller route may be wrong or record is outside authorized scope |

Understanding **where an error originates** helps Clients fix requests and backend teams protect APIs without relaxing validation rules.

## 24. Self-Check Questions

**Question 1.** What does a request without an `Authorization` header to a protected endpoint usually receive?

**Answer:** Usually `401 Unauthorized` with `WWW-Authenticate: Bearer`. Because there is no token, the challenge may not carry `error="invalid_token"`.

**Question 2.** Why does `Authorization: Bearer abc def` usually differ from `Authorization: Bearer abc.def.ghi`?

**Answer:** The first violates Bearer transport syntax because of the internal space. The second can be extracted, but will be rejected by the token decoder if the JWT is invalid. Thus they can lead to `400 invalid_request` and `401 invalid_token`, respectively.

**Question 3.** What code should a properly signed token with `exp` in the past return?

**Answer:** When the `exp` validator rejects the token, usually `401 invalid_token`.

**Question 4.** What if a token is unexpired with the right issuer/audience, but lacks `orders.read`?

**Answer:** The token can be authenticated, but the endpoint requiring `SCOPE_orders.read` will deny permission, usually returning `403 Forbidden`.

**Question 5.** Opaque token introspection returns HTTP 200 and body `{"active":false}`. Does the API allow the request?

**Answer:** No. HTTP 200 is the status of the request to the introspection endpoint; `active=false` means the token is not accepted.

**Question 6.** Does `permitAll` for `/api/public/ping` guarantee a bad Bearer token cannot cause the request to receive `401`?

**Answer:** No. The Bearer authentication filter can process the token before authorization, so an invalid credential may still be rejected.

**Question 7.** When should you inspect `WWW-Authenticate`?

**Answer:** When analyzing Bearer `401`/`403`/`400` responses, because the header can provide the scheme, error code, and relevant scope/realm info. Do not only look at the JSON body.

**Question 8.** Does `@ControllerAdvice` always catch JWT bad-signature errors?

**Answer:** No. Errors typically occur in the Servlet security filter before entering the Controller; inspect Spring Security's entry point/failure handler.

**Question 9.** If a Bearer token has the wrong audience but the right scope, should the API let it through?

**Answer:** No. Audience ensures the token was issued for a specific Resource Server, independent of scope permissions.

**Question 10.** Why shouldn't you edit a JWT payload to create a missing-scope test?

**Answer:** Because altering the payload invalidates the signature; the request will fall into the invalid-token branch rather than the valid-token-missing-scope branch.

**Question 11.** Does an introspection timeout prove the Client's opaque token was revoked?

**Answer:** No. A timeout is a verification failure; the Resource Server must not fail open, but you must distinguish an upstream outage from an AS `active=false` result.

**Question 12.** Should receiving `403` always trigger refreshing the token and retrying?

**Answer:** No. `403` is usually due to missing scope or business permissions. Refreshing with the same permissions will not solve it; the Client must handle it per the appropriate authorization policy.

## 25. Key Takeaways

With Spring Security OAuth 2.0/OIDC Resource Server, always distinguish four steps:

1. **No Bearer credential:** protected endpoints usually return **`401` with a `Bearer` challenge**, not necessarily accompanied by a specific error code.
2. **Malformed Bearer request:** the resolver may return **`400 invalid_request`**.
3. **Token present but validation failed:** the decoder or introspector may return **`401 invalid_token`** when the token is rejected.
4. **Token authenticated but insufficient permissions:** authorization usually returns **`403 insufficient_scope`** or an access-denial code matching policy.

Do not confuse an unverifiable JWT with a token lacking scope, nor confuse an AS-rejected token with an AS timeout. `BearerTokenAuthenticationFilter`, `AuthenticationEntryPoint`, `AccessDeniedHandler`, and the Resource Server's validators each play a distinct role in the processing chain.

Finally, **a proper error response is more than just an HTTP status**: it needs an appropriate Bearer challenge, must not leak tokens or secrets, must not open permissions to “fix” errors, and must still protect audience, scope, tenant, and resource ownership before allowing the API to return data.
