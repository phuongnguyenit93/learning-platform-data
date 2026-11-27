# RFC 7662, introspection request, and response metadata

## 1. Why does a Resource Server need Token Introspection?

An API using OAuth 2.0 receives an **access token** via HTTP `Authorization: Bearer ...`. If the token is a signed JWT that the Resource Server is allowed to verify locally, the API can fetch public keys/JWKS and locally validate the JWS, issuer, audience, expiration, and permissions. However, many Authorization Servers issue access tokens in an **opaque** form: to the API, the token is simply a random string with no trustworthy internal structure to decode.

For example:

```http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer 5c6e86a0-opaque-token-example
```

The Resource Server must not infer identity, permission scopes, or expiration from the appearance of that string. To find out whether the token is active and what permissions were granted to it, the API can query the **Authorization Server** via **OAuth 2.0 Token Introspection**, standardized in **RFC 7662**.

In this approach, the Resource Server **sends the token to the introspection endpoint**, authenticates itself to the endpoint per the Authorization Server's policy, and receives JSON metadata reflecting the token's status. The Resource Server then checks its own API conditions (scope, audience, tenant, ownership) before executing business logic.

> **Key takeaway:** `active: true` is the result of a token status check from the perspective of the Authorization Server and the introspection caller's permissions. It **does not automatically mean** the caller is allowed to use every endpoint or view every resource.

Examples in this lesson use:

- **Authorization Server**: `https://auth.example.test`.
- **Introspection endpoint**: `https://auth.example.test/oauth2/introspect`.
- **Resource Server**: `orders-api`, protecting `/api/orders/**`.
- **Introspection client**: `orders-api-introspector`, holding its own credentials to call the endpoint.
- **OAuth client receiving the token**: `web-portal`, which requested the token on behalf of the user.
- **User subject**: `alice-123`.

Domain names, passwords, and tokens in the examples are purely symbolic; **never use illustrative values as real credentials**.

### 1.1. An exchange diagram

```mermaid
sequenceDiagram
    participant U as User / Browser
    participant C as OAuth Client web-portal
    participant AS as Authorization Server
    participant RS as Resource Server orders-api

    U->>C: Sign in and request to view order
    C->>AS: OAuth authorization / token request
    AS-->>C: Opaque access token
    C->>RS: GET /api/orders/42 + Bearer token
    RS->>AS: HTTPS POST /oauth2/introspect
    Note over RS,AS: Send token and authenticate orders-api-introspector
    AS->>AS: Check introspection permission and token state
    AS-->>RS: JSON active + permitted metadata
    RS->>RS: Validate token, audience, scope, object-level policy
    RS-->>C: 200 / 401 / 403 / 404 per policy
```

The Bearer request from the client to the API and the introspection request from the API to the Authorization Server are **two distinct transactions**, using two different sets of credentials:

| Location | Credential | Owner | What is it used for? |
|---|---|---|---|
| `Client -> orders-api` | Request's **access token** | Client issued the token; may represent a user | API needs to know if this token is valid and what scopes it has. |
| `orders-api -> Authorization Server` | **Introspection client credential** | Resource Server service | AS authenticates and decides whether the Resource Server is permitted to query token metadata. |

Never use `client_id` in the introspection response as the introspection client ID, nor use the frontend's client secret or the user's token as the introspection password.

### 1.2. "Opaque Token Resource Server" does not mandate a specific token format

RFC 7662 does not require the token passed into introspection to be a purely random string; the endpoint can introspect a JWT as well if the AS supports it. "Opaque" in Spring Security's configuration naming primarily emphasizes that **the Resource Server uses the introspection result as its authentication source**, rather than decoding and verifying a JWT via a local decoder path.

Therefore, distinguish between the two modes:

| Characteristic | Local JWT validation | Introspection via RFC 7662 |
|---|---|---|
| Verification method | JWS public key/JWKS and the API's JWT validators. | Query the Authorization Server for whether the token is active and retrieve metadata. |
| Network dependency during token check | Not per request if public keys are cached. | Usually calls introspection per token/request, unless caching is designed. |
| Early token revocation | Self-validated JWTs do not inherently know about revocations. | AS can report `active=false` if it knows the token was revoked. |
| Received payload | JWT claims issued by the issuer. | JSON metadata the AS decides to disclose to the resource requester. |
| Integration security | Managing public keys and token validation. | Adds introspection endpoint credentials, TLS, rate limiting, and response trust. |
| Business authorization | Must always check scope/role/owner/tenant. | **Still must check scope/role/owner/tenant.** |

Both approaches must validate the expected audience/token profile per contract. Never accept a token merely because it is a decodable JWT or because introspection returned `active=true`.

---

## 2. What does RFC 7662 define?

RFC 7662, **OAuth 2.0 Token Introspection**, specifies:

1. **Introspection endpoint** on the Authorization Server.
2. **Introspection request**: an HTTP `POST` using `application/x-www-form-urlencoded`, with a mandatory `token` parameter and an optional `token_type_hint`.
3. **Requester authentication and authorization**: the AS must protect the endpoint to avoid leaking token status/identity to unauthorized parties.
4. **Introspection response**: a JSON object containing the mandatory `active` (boolean) field and optional metadata.
5. **Response rules for inactive tokens or tokens the caller is not permitted to inspect**.
6. **Channel protection requirements** via TLS along with privacy, caching, and rate-limiting considerations.

There are two completely separate security decisions at the AS:

- **Is the Resource Server allowed to call the introspection endpoint?** Determined by credentials and AS policy.
- **Is the access token in the `token` parameter active and permitted to be disclosed to this requester?** Determined by token state and specific introspection permissions.

Being an authenticated introspection client does not mean being allowed to inspect the status of **every** token. The AS may restrict visibility by audience, resource, tenant, client, or authorized scope.

### 2.1. Multiple roles appearing in a single request

Suppose the AS returns:

```json
{
  "active": true,
  "client_id": "web-portal",
  "sub": "alice-123",
  "aud": ["orders-api"],
  "scope": "orders:read"
}
```

These identities are not interchangeable:

| Identity | Example | Meaning |
|---|---|---|
| **Introspection requester** | `orders-api-introspector` | Client calling `/oauth2/introspect` to query token state. |
| **OAuth token client** | `web-portal` | `client_id` of the client that requested the access token, if provided by the AS. |
| **Subject** | `alice-123` | `sub` of the subject the token represents, if present. |
| **Audience / resource** | `orders-api` | `aud` describing the target resource, if provided by the profile. |
| **Issuer** | `https://auth.example.test` | Issuing AS, if the response includes `iss`. |

With Client Credentials, `sub` may represent a workload/client rather than an interactive user. The Resource Server must not assume every `sub` is a user to infer ownership.

---

## 3. Structure of the introspection request

### 3.1. Method, URL, and Content-Type

According to RFC 7662, an introspection request is sent to the AS's registered endpoint via **HTTP POST** with form parameters:

```http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <base64-of-introspection-client-credentials>

token=opaque-access-token-value&token_type_hint=access_token
```

In this example:

- `token` is the **mandatory parameter** holding the token whose state is queried. It is the access token from the request to `orders-api`, not the introspection client secret.
- `token_type_hint` is an **optional parameter** suggesting the token type, typically `access_token` or `refresh_token`. It only helps the AS choose an efficient lookup; the Resource Server cannot rely on this hint as proof of token type.
- `Authorization: Basic ...` is one **way to authenticate the introspection requester**. The Authorization Server may require another mechanism such as `client_secret_post`, mutual TLS, or private-key JWT depending on its capabilities and policy.
- HTTPS must verify certificates and hostnames. **Base64 in Basic Auth does not encrypt or protect the client secret**; only TLS and protecting endpoints/logs secure secrets in transit.
- Never place the access token in URL query strings or send it with `GET` just for debugging convenience; URL queries can be logged by gateways/browsers/proxies.

**Form encoding** must be handled properly by the HTTP library. Access tokens can contain special characters, so manual unescaped string concatenation can cause the AS to receive a corrupted token value. Use a standard client/library to send `application/x-www-form-urlencoded`.

### 3.2. Curl example for lab testing

If you need to observe the protocol against a **dev/test** AS you manage:

```bash
curl --request POST \
  --url 'https://auth-dev.example.test/oauth2/introspect' \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --user "$INTROSPECTION_CLIENT_ID:$INTROSPECTION_CLIENT_SECRET" \
  --data-urlencode "token=$TEST_ACCESS_TOKEN" \
  --data-urlencode 'token_type_hint=access_token'
```

For this command to be useful, the three environment variables must be populated with appropriate test credentials—**never enter production credentials into terminal history or documentation**. Avoid `curl -v`/`--trace` with real tokens, as headers/form bodies can appear in logs. In some shell/process environments, arguments and environment variables can be inspected; do not treat sample scripts as a default production secret-delivery method.

If the AS uses another client authentication method, `--user` must be replaced according to the **issuer's metadata and documentation**; never assume every introspection endpoint supports Basic Auth.

### 3.3. What does `token_type_hint` do?

An Authorization Server may store access tokens and refresh tokens in different stores. When the request includes:

```text
token_type_hint=access_token
```

the AS can check the access token store first. This is a **hint**, not authentication proof or an authorization condition. RFC 7662 allows the AS to ignore the hint; behavior for unknown or mismatched hints is implementation-dependent.

Never use `token_type_hint=access_token` to turn a refresh token into an access token, and never let an API accept a refresh token merely because this hint was sent. The API must accept only **access tokens matching the right profile/resource**, never refresh tokens as Bearer credentials.

### 3.4. Should `client_id` and `client_secret` be sent in the body?

RFC 7662 does not mandate that every introspection request use a client secret; it focuses on protecting the endpoint under AS policy. One AS using Basic may accept credentials in the HTTP Authorization header. Another AS may support body credentials, mTLS, or `private_key_jwt`.

For example, if the AS requires `client_secret_basic`, do not also add `client_id`/`client_secret` to the body "just in case," as that can violate the registered authentication method and increase exposure surface. Configure the exact **client authentication method** for the introspection client.

---

## 4. Response: `active` is the mandatory field

An introspection response under RFC 7662 is a JSON object with a required field:

```json
{
  "active": true
}
```

or:

```json
{
  "active": false
}
```

`active` must be a **JSON boolean**, not the string `"true"` or number `1`. When `active=true`, the Authorization Server has determined the token is active according to its state and policy at the time of introspection; additional metadata may accompany it.

### 4.1. Active token

A fuller example response:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "scope": "orders:read orders:write",
  "client_id": "web-portal",
  "username": "alice",
  "token_type": "Bearer",
  "exp": 1890003600,
  "iat": 1890000000,
  "nbf": 1890000000,
  "sub": "alice-123",
  "aud": ["orders-api"],
  "iss": "https://auth.example.test",
  "jti": "token-id-abc-123"
}
```

This is an **illustrative** response. Fields other than `active` appear only if the AS supports them, has the data, and permits the requester to see them. Do not force every issuer to return the entire list.

### 4.2. Inactive or non-introspectable token

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": false
}
```

A token may be inactive because it expired, was revoked, does not exist, is not yet valid, or **cannot be inspected by this introspection requester** under AS policy. RFC 7662 recommends returning only `active=false` for inactive tokens without disclosing token metadata.

Notably, the AS may return the exact same inactive response for **a non-existent token** and **a token the requester is not allowed to see**. This avoids creating an oracle that leaks valid tokens to unauthorized parties.

The Resource Server must treat `active=false` as **insufficient to authenticate the request**. Do not decode the token to fall back on claims, do not treat a "slightly expired" token as valid, and do not let the request through because the route only says `authenticated()`.

### 4.3. HTTP 200 from the AS does not mean the token is valid

At the transport layer, a successful introspection call can return **HTTP 200** while the JSON contains `active=false`. Distinguish:

| Introspection HTTP status | JSON body | Interpretation |
|---|---|---|
| `200 OK` | `{"active":true,...}` | Introspection request processed; token is active per AS, continue policy checks. |
| `200 OK` | `{"active":false}` | Token is inactive/not visible; Resource Server rejects token authentication. |
| `400 Bad Request` | AS-specific error object | Request had invalid syntax/parameters, not proof that the token is inactive. |
| `401 Unauthorized` | Error or empty body | Introspection client credential wrong/missing; integration/authorization error with AS. |
| `403 Forbidden` | Implementation-dependent | Introspection requester lacks permission for endpoint or resource; distinguish from `active=false`. |
| `429 Too Many Requests` | Implementation-dependent | AS rate-limiting; apply backoff/circuit breaker per policy, do not pass through. |
| `5xx`/timeout | No valid result received | Cannot verify token; must **fail closed**. |

Exact error codes depend on the AS and Spring Security version. When the Resource Server cannot verify due to a network failure, the HTTP response to the client may differ from 401 depending on exception handling; the invariant is that the request **must never execute protected business logic** without trusted authentication.

---

## 5. Standard metadata in the introspection response

RFC 7662 defines `active` as mandatory and several **optional** field names. The table below focuses on their meaning, data types, and usage policy.

| Field | Typical type per RFC 7662 | Meaning | Notes for Resource Server |
|---|---|---|---|
| **`active`** | Boolean, **required** | Whether the token is active per AS. | `false` → do not build authenticated principal. `true` → still requires scope/resource policy. |
| **`scope`** | Space-delimited string | OAuth scopes associated with the token. | Convert to authorities per profile; never invent permissions when absent. |
| **`client_id`** | String | OAuth client that requested the token. | Distinct from introspection requester; does not automatically grant this client access to all resources. |
| **`username`** | String | Human-friendly username when token represents a resource owner. | Do not use as a stable primary authorization key. |
| **`token_type`** | String | Token type, typically `Bearer`. | Do not assume every AS returns it; verify expected token type if contract requires. |
| **`exp`** | Number, NumericDate | Expiration time (Unix seconds). | Useful to block expired tokens and bound cache TTL. |
| **`iat`** | Number, NumericDate | Issuance timestamp. | Useful for audit or token-age policy; not a permission by itself. |
| **`nbf`** | Number, NumericDate | Not-before timestamp. | If used by contract, tokens before this time must not be accepted. |
| **`sub`** | String | Subject represented by the token. | Interpret with issuer namespace and grant; do not assume it is always a user. |
| **`aud`** | String or array of strings | Token audience/resource. | Verify `orders-api` is in the audience set per policy. |
| **`iss`** | String | Token issuer. | Verify against trusted issuer if provided by contract. |
| **`jti`** | String | Token identifier, if present. | Useful in audit/revocation policies; not standalone token proof. |

This table does not mean these fields are **mandatory** in every introspection response. Aside from `active`, their presence and interpretation depend on **the contract between the Authorization Server and Resource Server**.

### 5.1. `scope` and authority mapping

Under OAuth 2.0, scopes are represented as space-separated scope tokens:

```json
{
  "active": true,
  "scope": "orders:read orders:write"
}
```

In Spring Security Resource Server using opaque tokens, default mapping typically converts scopes into:

```text
SCOPE_orders:read
SCOPE_orders:write
```

Thus:

```java
.hasAuthority("SCOPE_orders:read")
```

checks Spring's authority, rather than comparing raw form strings or a `scope` query parameter directly.

Some IdPs put permissions into `scp`, `roles`, `permissions`, or custom claims. **Never assume they are automatically equivalent to `scope`** unless the AS explicitly defines that profile. If a custom mapper is required, validate the schema, resource names, and permission boundaries.

### 5.2. `client_id` is not the introspection client ID

The response:

```json
{
  "active": true,
  "client_id": "web-portal",
  "sub": "alice-123"
}
```

does not say the Resource Server called introspection using `web-portal`. It describes the OAuth client bound to the access token. The client calling introspection is typically `orders-api-introspector` with its own credentials.

This distinction matters when enforcing:

- Rate limits by the OAuth client that requested the token.
- Policies permitting only specific clients to call the API.
- Audits of access token issuance sources.
- Service-to-service integrations.

If the API needs a `client_id` allowlist, base it on the **verified token profile** and **never treat `client_id` alone as proof that a user owns an object**.

### 5.3. `sub`, `username`, and subjects that are not always users

An Authorization Code token may contain:

```json
{
  "sub": "alice-123",
  "username": "alice"
}
```

Meanwhile, a Client Credentials token may carry a subject corresponding to a service account:

```json
{
  "client_id": "orders-importer",
  "sub": "orders-importer-service"
}
```

Do not use `username` (which can change or be recycled) as an owner key in the database. When using `sub` for ownership relationships, pair it with the issuer or a trusted internal identity mapping. For client credentials, keep workload policies separate from user policies.

### 5.4. `iss` and `aud` are trust boundaries

One AS may issue tokens for many APIs. Therefore, seeing `active=true` is not enough to confirm the token is meant for `orders-api`.

Example response:

```json
{
  "active": true,
  "aud": ["payments-api"],
  "scope": "orders:read",
  "iss": "https://auth.example.test"
}
```

If policy requires the audience to include `orders-api`, the Resource Server must reject this token even though its scope is named `orders:read`.

Not every AS returns `aud` or `iss` in the introspection response. To guarantee resource binding, the API and AS need one of these contracted models:

1. The AS **only returns active/usable metadata for tokens meant for this resource requester**, based on introspection credentials and resource policy.
2. The AS explicitly returns `aud`/`iss`, and the Resource Server **validates** those fields.
3. An equivalent contracted endpoint/provider-specific extension identifies the proper issuer/resource.

**If there is no audience in the response and the AS does not guarantee resource scoping, the Resource Server lacks sufficient proof to confirm the token belongs to the API.** Never ignore this gap by checking only `active=true`.

### 5.5. `exp`, `iat`, and `nbf` are not HTTP cache lifetimes

These are **NumericDate** (Unix seconds) values, for example:

```json
{
  "active": true,
  "iat": 1890000000,
  "nbf": 1890000000,
  "exp": 1890003600
}
```

Meaning:

- `iat`: when the token was issued.
- `nbf`: time before which the token is not valid.
- `exp`: time at or after which the token is no longer valid.

Do not compare these values against epoch milliseconds without unit conversion. Spring may convert timestamps appropriately in the authentication principal, but custom code must understand the schema returned by the provider.

Do not confuse `exp` with:

- The **Cache-Control** header of the HTTP introspection response.
- **Cache TTL** of an application cache.
- **Token refresh interval** on the OAuth client.
- **JWT `exp`** in a locally parsed token.

If caching introspection results, the maximum retention must account for `exp`, revocation goals, cache policy, and clock skew; **never cache an "active" response past the token's expiration**.

### 5.6. `jti` and tracing

`jti` can serve as a token identifier, though the AS does not always provide it. It can be useful for audits/denylists if the product designs for it.

Never store raw access tokens in logs just for tracing; an access token is a Bearer credential. Likewise, do not turn `jti` or `sub` into unbounded-cardinality metric labels. When correlation is needed, use a request ID and fields permitted by privacy policy.

### 5.7. Claims beyond RFC 7662

An issuer might return:

```json
{
  "active": true,
  "scope": "orders:read",
  "tenant_id": "tenant-a",
  "roles": ["orders-viewer"],
  "department": "sales",
  "authorization_details": [
    {
      "type": "order_access",
      "actions": ["read"],
      "locations": ["orders-api"]
    }
  ]
}
```

This is a **hypothetical extension profile**. There is no universal rule that `tenant_id`, `roles`, or `authorization_details` will always be supplied or follow this exact schema. If the API uses them for authorization, document the contract:

- Allowed claim names and data types.
- Which issuer emits them, for which audience/resource.
- How missing/null/mistyped values must be handled.
- Permission names and resource scope.
- How they combine with scopes.
- How user vs. workload context is distinguished.
- Policy for permission updates while a token remains active.

**Never take any arbitrary `"admin"` string in JSON to grant system-wide administrative roles.**

---

## 6. Spring Security Resource Server with opaque tokens

Spring Security supports OAuth 2.0 Resource Server Bearer token authentication via **`OpaqueTokenIntrospector`**. On this path, the application does not need to decode the access token as a JWT; it sends the token to the AS and processes the verified metadata.

### 6.1. Required dependencies

Maven example with Spring Boot parent/BOM managing versions:

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

### 6.2. Configuring the introspection endpoint and credentials

`application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Placeholders are resolved by Spring Boot from runtime property sources/environment. **Secret values must never be hardcoded in source code, Git config files, Dockerfiles, or logs**. A secret manager or platform runtime injection should provide `INTROSPECTION_CLIENT_SECRET` to the process.

Example variable names:

```text
INTROSPECTION_CLIENT_ID=orders-api-introspector
INTROSPECTION_CLIENT_SECRET=<injected-at-runtime>
```

The secret line is a placeholder, not a real password.

If the AS only supports an introspection client authentication method other than Basic, or requires custom HTTP timeouts/mTLS/`private_key_jwt`, customize `OpaqueTokenIntrospector` or the underlying HTTP client accordingly. Do not assume the properties above suffice for every provider.

### 6.3. `SecurityFilterChain` requiring scopes

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
public class OpaqueTokenSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            // Suitable for stateless APIs using Bearer tokens in the Authorization header.
            // Apps with session cookies must evaluate CSRF separately.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders:write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
```

By default, the Resource Server creates authentication for an active token and maps scopes into `SCOPE_...` authorities. `authorizeHttpRequests` then uses those authorities to authorize routes. Do not change `.anyRequest().denyAll()` to `.anyRequest().authenticated()` just to avoid 403 errors, as that could leave newly added routes without required scope enforcement.

The snippet above only designs **one authentication mode for the API**. If the application must accept both local JWTs and introspection, use a resolver/policy that cleanly classifies token, issuer, and audience; never allow a token that "fails in one mode to try another until accepted" without trust boundaries.

### 6.4. What does Spring do with the introspection result?

Conceptual flow:

```mermaid
flowchart TD
    A["Request Authorization: Bearer opaque token"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["OpaqueTokenIntrospector"]
    C --> D["HTTPS POST /oauth2/introspect"]
    D --> E{"AS returns active?"}
    E -->|false / error| F["Authentication fails or upstream error; do not allow"]
    E -->|true| G["Create OAuth2AuthenticatedPrincipal from metadata"]
    G --> H["Map scope to SCOPE_..."]
    H --> I["Create BearerTokenAuthentication"]
    I --> J{"Has endpoint's required authority?"}
    J -->|No| K["403"]
    J -->|Yes| L["Check owner, tenant, business logic"]
    L --> M["Return data or deny per policy"]
```

Class names and implementation details may vary across Spring Security versions. The core structure is `OpaqueTokenIntrospector` returning an `OAuth2AuthenticatedPrincipal` with attributes and authorities, after which the Resource Server creates the appropriate authentication.

### 6.5. Reading metadata in a controller or service

An example outputting only **permitted information** without returning the raw token:

```java
package com.example.orders.api;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class WhoAmIController {

    @GetMapping("/api/whoami")
    Map<String, Object> whoami(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return Map.of(
            "name", principal.getName(),
            "authorities", principal.getAuthorities().stream()
                .map(authority -> authority.getAuthority())
                .sorted()
                .toList()
        );
    }
}
```

In a real system, do not expose `sub`/`roles`/PII on a public API just for debugging. The illustrative endpoint also runs after the security filter; ensure `/api/whoami` has a route policy requiring authentication and only exposes details the caller is authorized to see.

To read attributes:

```java
Object rawScope = principal.getAttribute("scope");
Object rawSubject = principal.getAttribute("sub");
Object rawClientId = principal.getAttribute("client_id");
```

**Do not blindly cast** every field to `String` because Java types depend on JSON/claim conversion in your Spring version, introspector, and issuer; `aud` may be a string or a collection. Write mappers/validators per contract rather than treating `String.valueOf(null)` as valid data.

### 6.6. Do not use `JwtAuthenticationToken` in opaque mode

When the Resource Server runs in opaque-token introspection mode, application authentication may be `BearerTokenAuthentication` with an `OAuth2AuthenticatedPrincipal`, not `JwtAuthenticationToken`. Avoid hardcoding in services:

```java
// DO NOT USE FOR ALL TOKEN TYPES:
JwtAuthenticationToken auth =
    (JwtAuthenticationToken) SecurityContextHolder
        .getContext().getAuthentication();
```

If the system supports multiple token mechanisms, build a normalized **AuthenticatedActor/AccessContext** from the active authentication mechanism and keep business policy decoupled from the framework's token class.

---

## 7. `active=true` is still not enough to access resources

Consider the metadata:

```json
{
  "active": true,
  "sub": "alice-123",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "tenant_id": "tenant-a"
}
```

An active token may allow reading certain orders. Yet the API must still enforce authorization across:

1. **Audience/resource**: `orders-api` is the right target resource for the token.
2. **Scope**: `orders:read` authorizes the read action type.
3. **Actor context**: subject/user vs. service; stable issuer/tenant/identifier.
4. **Object-level access**: whether the order record is within the permitted scope.
5. **Business rules**: order status, data type, partner rights, separation of duties, quotas.

Examples:

| Caller | Token active? | Read scope? | Order | Object permission | Outcome |
|---|---:|---:|---|---:|---|
| Alice | Yes | Yes | Alice's order | Yes | May be allowed. |
| Alice | Yes | Yes | Bob's order in same tenant | No | 403/404 per policy. |
| Alice | Yes | No | Alice's order | Yes | 403 due to missing scope. |
| Service `orders-importer` | Yes | Only `orders:import` | User order | Wrong actor/path | Rejected. |
| Carol | Yes | Yes | Another tenant's order | No | Rejected. |
| Inactive token | No | N/A | Any | N/A | Authentication fails, usually 401. |

**URL-level authorization is only one layer**. A `GET /api/orders/{id}` route requiring `SCOPE_orders:read` is still vulnerable to **BOLA/IDOR** if the controller calls `findById(id)` and returns data without checking subject/tenant.

### 7.1. Filtering data using the authenticated subject

Suppose the `orders` table stores `id`, `tenant_id`, `owner_issuer`, and `owner_subject`. A query suited to a **read-own** policy:

```sql
SELECT *
FROM orders
WHERE id = :requested_id
  AND tenant_id = :trusted_tenant_id
  AND owner_issuer = :trusted_issuer
  AND owner_subject = :trusted_subject;
```

The `trusted_*` parameters must come from verified introspection metadata and the API's identity/entitlement contract, **never from client-supplied query parameters or JSON bodies**. If the AS does not return issuer or tenant, establish another trusted way to resolve identity; never auto-fill defaults just to let requests succeed.

A user with `orders:read` scope is not automatically entitled to read every order in the tenant. If support/admin access is needed, implement a separate policy with explicit scope/role/tenant bounds.

### 7.2. Metadata may be restricted per requester

RFC 7662 allows the AS to decide **which information is disclosed** to the caller. Two different Resource Servers can receive different metadata for the exact same token if the AS applies such a policy.

Therefore:

- Never inspect a token response for API A and assume API B will receive the same metadata.
- Never forward introspection metadata across services as a shared resource-agnostic entitlement source.
- Never cache/share metadata across audiences/tenants without clear namespacing and policy.
- Never treat missing `aud` or `client_id` as a default RFC violation; rely on each issuer/resource contract.

---

## 8. Securing the introspection endpoint and client credentials

Introspection can disclose highly sensitive token details: subject, user, client, scopes, audience, timestamps, tenant, or roles. Consequently, the endpoint must never be open to any caller holding a token.

### 8.1. Authenticating and authorizing the caller

A typical design:

- Each Resource Server has a **dedicated introspection client**, e.g. `orders-api-introspector`.
- The AS restricts token lookup to the `orders-api` resource, as supported by the AS.
- Staging and production have separate clients/secrets.
- Client authentication uses `client_secret_basic`, private-key JWT, or mTLS per the issuer's contract.
- Never grant AS admin rights or permission to inspect all tokens if the API does not need them.
- Audits at the AS record client ID/request status appropriately, **without logging raw tokens or secrets**.

**The introspection client ID and the token response's `client_id` mean different things.** Confusing them can cause authorization bugs or inaccurate audit logs.

### 8.2. Managing the client secret

Never put:

```yaml
# DO NOT USE IN GIT/IMAGES:
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          client-secret: "orders-prod-real-secret"
```

Replace with placeholders and runtime secret injection. Secret Manager, Kubernetes Secrets referenced via `secretKeyRef`, mounted files, or platform-appropriate mechanisms can be used with least privilege.

**Base64 in a Kubernetes Secret manifest is not encryption.** Never commit manifests containing raw Base64 credentials and treat them as secure. With env var injection, updating a secret on the cluster does not make a running JVM reload the new value; you need a rollout/restart or a designed reload mechanism.

Never log:

- `Authorization: Basic ...` sent to the introspection endpoint.
- The `token=...` form body of the introspection request.
- `Authorization: Bearer ...` from incoming requests to the Resource Server.
- Credentials in CI/CD, Docker layers, unintentionally exposed Java system properties, or HTTP traces.
- Full introspection responses containing PII during debugging.

### 8.3. TLS, fixed endpoints, and SSRF

`introspection-uri` must come from trusted configuration, never from user input or unverified token contents. If an attacker can alter the introspection URL, the Resource Server could send **both the access token and the introspection client credential** to the attacker's server.

Requirements:

1. Use **HTTPS** and verify TLS certificates/hostnames properly.
2. Control redirects; never automatically forward credentials to untrusted hosts.
3. Restrict outbound network access to appropriate AS endpoints.
4. Never disable TLS verification when an issuer/proxy fails.
5. Configure HTTP timeouts, concurrency limits, and response size bounds.
6. Separate observability metadata from sensitive token and user data.

### 8.4. Distinguishing client credential errors from inactive tokens

If the AS returns `401 Unauthorized` because the introspection client secret is wrong, **never** interpret that as `active=false` per token and lose the incident signal. Both situations must fail closed, yet operational handling differs:

- **Inactive token**: the client must obtain a valid token; the API rejects the credential.
- **Wrong/expired introspection client credential**: operators must fix the secret/permissions/rotation; valid tokens will also fail verification.
- **AS timeout/5xx**: handle infrastructure issue, bounded retries, alerting; never allow requests through.

---

## 9. Caching: performance versus revocation freshness

One key value of introspection is that the Authorization Server can return `active=false` even before a token reaches `exp` if it was revoked. If the Resource Server caches `active=true` results for too long, the benefit of near-real-time revocation diminishes.

### 9.1. The latency problem

Suppose an API handles 2,000 requests/second, each calling introspection:

```text
Client request → orders-api → auth/introspect → orders-api → business response
```

If the AS or network is slow, authentication latency becomes a large share of total response time. Introspection request volume can match API request volume (depending on cache/framework/config), placing heavy load on the AS.

Some systems cache introspection responses keyed by access token for a short, controlled duration. However, caching is a **security decision**, not merely a latency optimization.

### 9.2. Conditions when caching introspection

| Principle | Why |
|---|---|
| **Finite, short TTL matching revocation policy** | Avoid trusting invalidated tokens for too long. |
| **Never exceed `exp`** | Never use caching to extend a token's lifetime. |
| **Distinguish `active=false` from upstream errors** | A timeout does not mean the token is inactive; never cache network errors as token status. |
| **Namespace cache by issuer/resource/policy** | Never apply metadata from a token scoped to another resource to this API. |
| **Bound entry count and size** | Prevent cache exhaustion from random tokens. |
| **Never write raw tokens in logs/metrics** | Tokens are Bearer credentials; cache keys must be protected and kept out of observability. |
| **Design emergency revocation** | When a token or client is compromised, you need invalidation or short TTLs. |
| **Verify policy on every request** | A cached principal never replaces object authorization, tenant/owner/business state. |

A cache key may need an internal keyed HMAC/digest to avoid storing raw tokens in observable locations; the design must resist collisions, protect the key, and guard the original token in memory. Never treat a publicly visible SHA-256 of a bearer token as a replacement credential or complete privacy protection.

### 9.3. Cache TTL and permission freshness

Even when a token has not been revoked, user permissions can change:

- The user is removed from a tenant.
- The client loses a scope.
- A support role is revoked.
- Order ownership changes.
- The user account is locked.

Introspection may reflect some of these changes **if the AS updates token metadata/status**. However, the AS does not necessarily know every business change inside `orders-api`. In particular, order ownership should be checked against a trusted business data source rather than relying solely on cached token metadata.

Different revocation delays may be acceptable for reading public-like catalog data versus payment or administrative actions. This must be aligned with security requirements and SLOs, not guessed from library defaults.

---

## 10. Timeouts, retries, and handling network errors

Because the Resource Server must call the AS, DNS failures, TCP/TLS errors, connect timeouts, read timeouts, invalid responses, or HTTP `429`/`5xx` can occur.

### 10.1. The non-negotiable rule: fail closed

When there is no trusted introspection response or the token is inactive, the Resource Server **cannot establish a valid authenticated principal for the request**. Never:

- Let the request pass because the AS is "probably just having a temporary glitch."
- Extract claims from an opaque token via arbitrary string parsing.
- Drop `scope` checks to avoid 403s.
- Use an introspection response from a different issuer/tenant.
- Turn an unverified token into a default user.
- Retry indefinitely until the API/gateway times out.

### 10.2. Categorizing error handling

| Incident | Retry? | Security handling |
|---|---|---|
| `active=false` | **No**. | Reject authentication. |
| Token lacks required `scope` | Do not retry introspection to "wait for permissions." | Reject authorization. |
| `401` due to wrong Basic credentials | Do not retry indefinitely. | Alert operator, rotate/fix credentials. |
| `403` due to introspection client lacking permissions | Do not retry indefinitely. | Fix AS grant/policy. |
| `400` due to malformed form request | No, until code/config is fixed. | Reject token, investigate request. |
| `429` | May retry very conservatively, honoring `Retry-After` if appropriate. | Do not overload the AS further. |
| `503`/`502`/`504` | May retry briefly if within deadline. | Fail closed when no result arrives. |
| Network connect/read timeout | May do bounded retries with backoff/jitter. | Do not exceed the request budget. |
| Invalid TLS certificate | Never "fix" by disabling TLS verification. | Never send secrets over untrusted channels. |
| Non-boolean `active` in response | Do not treat as active. | Treat response as invalid; raise integration error if needed. |
| `active=true` response violates audience/issuer contract | Do not retry to bypass policy. | Reject authentication/authorization at the designed layer. |

### 10.3. Bounded retries and load limiting

A system can configure:

- Finite connect timeout.
- Finite read/response timeout.
- Low max attempts for transient failures.
- Exponential backoff with jitter.
- Total request deadline protecting the SLO.
- Concurrency limits on concurrent introspection connections/requests.
- Circuit breaker during prolonged AS outages.
- Rate limits at the API gateway against unusual bursts of invalid tokens/requests.

Thresholds should be derived from p95/p99 measurements, traffic volume, and AS capacity. **Never stack retries across the HTTP client, service mesh, and gateway with an uncontrolled multiplier.**

Illustrative pseudocode:

```text
introspect(token):
    if token missing or obviously malformed:
        reject

    for attempt in 1..MAX_ATTEMPTS:
        if request deadline exceeded:
            fail closed

        try:
            response = POST trusted_introspection_endpoint
                       with authorized client authentication
                       and short connect/read timeouts
            validate response schema
            return response
        catch transientNetworkFailure:
            if no attempts remain:
                fail closed
            bounded exponential backoff with jitter

    fail closed
```

Here `return response` **is not yet "authorize the API"**: you still must read `active`, check the resource/scope/claims contract, and enforce object-level policy. Retries apply only to transient network/upstream errors, never to invalid tokens or missing permissions.

### 10.4. HTTP status returned to the client

A Resource Server receiving `active=false` for a protected request's Bearer token typically returns **401**; an active token lacking `orders:read` typically returns **403**. For an introspection dependency failure, the status depends on exception handling: it might be an authentication failure or a server/upstream error; if returning `503`, design and test it carefully without leaking secrets.

Do not conflate:

```text
HTTP 401 from AS to introspection client -> Resource Server credential error
HTTP 401 from orders-api to Bearer request -> client token not accepted
HTTP 403 from orders-api -> token authenticated but lacks permission
```

These are three distinct HTTP responses with different roles, even when status codes look identical.

---

## 11. Testing introspection with Spring Security

To test properly, separate:

1. **Route authorization**: which roles/authorities are allowed to access what?
2. **Introspection client integration**: does the API send the right POST, credential headers, and form body?
3. **Response parsing and contract**: `active`, claims, audience, scope, timestamps.
4. **Failure behavior**: network/HTTP errors and fail-closed handling.
5. **Business object authorization**: owner/tenant/ACL checks once the token is active.

### 11.1. MockMvc route tests using `opaqueToken()`

`spring-security-test` provides the `opaqueToken()` request post-processor to create a mocked authentication, suited for testing HTTP authorization without calling the AS.

```java
package com.example.orders.security;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OpaqueAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void missingTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void activePrincipalWithReadAuthorityCanReachRoute() throws Exception {
        mvc.perform(get("/api/orders/42")
            .with(opaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read"))))
            // Assumes the test controller/service fixture allows the test principal
            // to read order 42 and returns 200.
            .andExpect(status().isOk());
    }

    @Test
    void principalWithoutReadScopeIsForbidden() throws Exception {
        mvc.perform(get("/api/orders/42")
            .with(opaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:write"))))
            .andExpect(status().isForbidden());
    }
}
```

This is a **route test pattern**, assuming a `GET /api/orders/42` controller exists and business policy lets the fixture principal access it. If the service also requires `sub`/tenant/owner, supply the matching attributes/fixture; never remove object-level policy just to make a test pass.

**`opaqueToken()` does not send HTTP introspection calls, does not check the client secret, does not parse `active` from the AS, and does not test timeouts/TLS.** It injects an already-authenticated principal in tests, so it cannot prove RFC 7662 integration.

### 11.2. HTTP stub simulating the Authorization Server

Use a local HTTP server such as WireMock/MockWebServer to verify:

- The request is a `POST` to `/oauth2/introspect`.
- `Content-Type` is form URL encoded.
- The form actually contains the incoming token, plus `token_type_hint` if configured.
- Requester authentication matches `client_secret_basic` or the mechanism agreed with the dev AS.
- Credentials are never sent to another host/redirect.
- `active=true` with matching `scope` maps to authorities.
- `active=false` fails authentication.
- HTTP `401`/`403` from the AS due to bad credentials is handled as an integration error, never letting the user through.
- Timeouts, `503`, and invalid JSON never create an authenticated principal.
- Responses missing `aud`/`iss` are handled per contract, never granting access if policy requires those fields.

Use only **dummy** client secrets in fixtures. Avoid printing Basic headers, form tokens, or introspection bodies containing user data into test reports.

### 11.3. Sample response matrix

| Response from stub | Expectation |
|---|---|
| `{"active":false}` | Token rejected, never reaches controller. |
| `{"active":true,"scope":"orders:read"}` | Read permission only, if resource contract permits. |
| `{"active":true,"scope":"orders:write"}` | Lacks `SCOPE_orders:read`; GET route requiring read returns 403. |
| `{"active":true}` | Must not synthesize scopes. Routes requiring scope are denied. |
| `{"active":"true"}` | Wrong field type; reject token per schema. |
| `{"scope":"orders:read"}` | Missing mandatory `active`; reject. |
| `{"active":true,"aud":"payments-api","scope":"orders:read"}` | Rejected if API policy requires audience to include `orders-api`. |
| `{"active":true,"exp":<expired-time>}` | Must honor expiration contract/AS policy; never let cache extend token. |
| `{"active":true,"roles":["ADMIN"]}` | Never automatically grant admin authority without an explicit converter/contract. |
| HTTP 401 from AS | Grant no access, alert on introspection credentials. |
| HTTP 429 or 503 from AS | Bounded retry if policy permits, then fail closed. |
| Network timeout | Grant no access; observe latency, timeouts, and handler behavior. |

`<expired-time>` is only a presentation placeholder, not valid JSON; in real fixtures use a numeric NumericDate (e.g., `1700000000`) or compute dynamically relative to the test clock.

### 11.4. Object-level authorization tests

Suppose Alice has `SCOPE_orders:read` and an active token. Tests must still prove:

- Alice reading Alice's order is allowed.
- Alice reading Bob's order **in the same tenant** is denied.
- Alice reading an order from another tenant is denied.
- A Client Credentials token cannot masquerade as a user token.
- List/export/bulk endpoints filter **every record**, not just route-level scope.
- Behavior when `sub` or `tenant_id` is missing per contract: reject/deny access rather than picking a default user.

An `active=true` response in a test never substitutes for real data-level permission checks.

### 11.5. Contract tests against a real staging AS

Stub tests can still miss provider-specific nuances. In staging, using a **dedicated introspection client** and staging tokens:

1. Create a valid access token and verify introspection succeeds.
2. Revoke the token and verify `active=false` per provider semantics.
3. Wait for the token to expire and check the response and API behavior.
4. Try a token belonging to another audience/resource and verify what metadata/`active` the AS returns.
5. Compare a Client Credentials access token and a user token (`sub`, `client_id`, `scope`).
6. Verify which metadata fields are actually present (`iss`, `aud`, `exp`, `jti`, custom claims).
7. Test wrong/unauthorized introspection credentials; verify they are not confused with inactive tokens.
8. Test quotas, timeouts, and controlled network failures.
9. Verify logs/traces/APM do not leak raw tokens or secrets.
10. Document the observed schema/contract for the Resource Server team, including optional fields **not** provided by the AS.

Never use production credentials in staging or local developer environments.

---

## 12. Integration errors and troubleshooting

### 12.1. Valid token yet API returns 401

Possible causes:

- AS returns `active=false` because the token expired, was revoked, or falls outside the introspection requester's scope.
- Resource Server mistakenly received a **refresh token** or ID token.
- API points to an introspection endpoint for the wrong tenant/realm/issuer.
- Resource Server's introspection credential expired.
- AS returned an `active` type incompatible with the parser or a malformed response.
- Token was issued only for a different audience.
- API policy requires a claim absent from the response.

How to investigate: inspect the request correlation ID, AS status, introspection client name, token profile, and claim validation outcome **without logging raw tokens or secrets**.

### 12.2. Active token yet API returns 403

Common causes:

- Missing `scope`, or a different scope than required by the endpoint.
- Authority name does not match the `SCOPE_` prefix.
- Issuer returns `scp`/`permissions`/`roles` while the API still uses default mapping reading only `scope`.
- Token is a client-credentials token with different privileges from a user token.
- Token has the right scope but lacks permission on the specific resource/tenant/owner.

Never "fix" this by replacing `hasAuthority("SCOPE_orders:read")` with `authenticated()` to let everything pass; check the contract and define the right policy.

### 12.3. System slows down or outages occur when the AS slows down

Causes can include every API request needing an introspection round-trip, unbounded retries, missing timeouts, exhausted connection pools, or AS rate limits. Mitigations include:

- Setting connect/read/overall timeouts.
- Bounded retries for transient errors, with backoff/jitter.
- Concurrency limits, connection pool tuning, and circuit breakers.
- Optimizing AS availability and network routing.
- Caching introspection with TTLs **aligned to revocation policy**, never unbounded caching by default.
- Separating alerts for dependency failures from invalid tokens and missing scopes.

Never skip token verification or enable `permitAll()` to mask an outage.

### 12.4. Just migrated from JWT to opaque tokens

Check that:

- The Spring filter chain switched from `jwt()` to `opaqueToken()`, or uses a controlled multi-token-type solution.
- Principal types changed; services do not hard-cast `JwtAuthenticationToken`.
- Claims/authorities may differ from the old JWT payload.
- Expiration/issuer/audience metadata from introspection may not be as complete as in a JWT.
- Logout/revocation/caching behavior has been re-evaluated.
- Introspection credentials and timeout/network settings are provisioned.
- Authentication tests and route/business policy tests are separated cleanly.

**Migrating token format does not automatically make business authorization correct.** The Resource Server must still enforce scopes, owners, and tenants.

---

## 13. Designing a handoff-ready introspection contract

Before production, the Identity and API teams should agree in writing on:

| Contract item | Questions to answer |
|---|---|
| **Issuer / realm** | Which AS is authorized to validate tokens? How does the Resource Server avoid issuer mix-ups? |
| **Endpoint** | What is the fixed HTTPS introspection URL? Is there a proxy/mTLS? |
| **Client authentication** | Basic/client secret, private-key JWT, mTLS, or another mechanism? How are requester privileges scoped? |
| **Token profile** | Access tokens only? Opaque or introspected JWTs? Differences by grant? |
| **`active` semantics** | How does the AS determine active/accessible? What does it return after revocation? |
| **Application-required metadata** | Are `scope`, `client_id`, `sub`, `aud`, `iss`, `exp`, tenant/roles guaranteed to appear? |
| **Data types** | Space-separated scope string or custom collection? Audience string or array? NumericDate in seconds? |
| **Resource binding** | Is targeting `orders-api` proven via `aud` or by the AS restricting `active` per requester? |
| **Authority mapping** | `scope` maps to `SCOPE_...`; which custom roles/permissions are permitted? |
| **Object authorization** | Where are owner/tenant/ACL checks enforced? |
| **Error contract** | 200 inactive, 400 invalid request, 401/403 credentials, 429/5xx; fail-closed behavior. |
| **Timeouts and retries** | SLO, total deadline, max attempts, backoff, concurrency limits. |
| **Caching and revocation** | Max cache TTL, invalidation mechanism, and acceptable permission staleness window. |
| **Logging/audit** | Which fields may be recorded; blocking raw tokens, client secrets, and PII from logs. |
| **Rotation/incident** | When the introspection client secret leaks or rotates, how does the API roll out? |
| **Testing** | Stub protocol tests, schema tests, staging integration, and BOLA/tenant negative tests. |

### 13.1. A sequential rollout checklist

1. **Register an introspection client** with the AS, scoped with least privilege for `orders-api`.
2. **Provision secret/private credentials** from a Secret Manager at runtime, never in source code.
3. **Configure Spring Boot** with `introspection-uri`, `client-id`, `client-secret`, or the appropriate custom authentication method.
4. **Configure the opaque-token filter chain** and define route-level scope authorities.
5. **Define the metadata contract**: `active`, `scope`, `sub`, `aud`, `iss`, `exp`, and custom claims.
6. **Enforce audience/issuer/resource binding**, not just `active=true`.
7. **Enforce object-level authorization** in the service/repository for order data.
8. **Configure TLS, timeouts, rate limits, and log masking**.
9. **Choose a cache policy** grounded in token lifetime and revocation requirements.
10. **Test** with active/inactive tokens, bad credentials, missing scopes, wrong audience/tenant, timeouts, and AS outages.
11. **Rehearse rotation** of introspection credentials and incident response for leaks.
12. **Monitor production** for introspection success/failure rates, latency, 401/403 counts, and dependency errors, without logging raw tokens.

---

## 14. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| "Just Base64-decode an opaque token to read its scopes." | Opaque tokens have no trustworthy structure from which to infer permissions locally. Introspection or an AS-provided mechanism is required. |
| "Introspection is a handy GET call for debugging." | RFC 7662 defines a form-urlencoded POST with required `token` and secure authentication/transport. |
| "`token_type_hint=access_token` proves the token is an access token." | It is only a hint; the AS determines token status/type per its policy. |
| "HTTP 200 means the token is valid." | You must inspect JSON `active`; `200 + active=false` means the token is inactive or hidden. |
| "HTTP 401 from the AS is the same as an inactive token." | Usually means the introspection client is unauthenticated; that is a credential/integration error. |
| "`active=true` grants all permissions." | Resource binding, scope, role, tenant, and object-level authorization are still required. |
| "`client_id` in the response is the client ID that called introspection." | Usually it is the OAuth client that requested the token, not the introspection requester. |
| "The response always has `sub`, `aud`, and `exp`." | Under RFC 7662, metadata beyond `active` is optional. |
| "`username` is a stable owner ID." | Usernames can change; use an identity contract such as issuer + subject/internal ID. |
| "`scope` and `roles` are always equivalent." | They are distinct claims/semantics; a mapper per issuer/profile is needed. |
| "Once an access token is revoked, the Resource Server always knows instantly." | If introspection responses are cached, the API can keep seeing `active=true` until expiration/invalidation. |
| "If the AS does not respond, let requests pass to preserve uptime." | Without trusted authentication proof → **fail closed**. |
| "Spring's `opaqueToken()` test calls the AS." | Mock principals bypass HTTP introspection; a separate integration test is required. |
| "Switching to opaque tokens removes the need for owner/tenant checks." | BOLA and data authorization issues do not disappear when changing token formats. |
| "Because JWKS is public, the introspection endpoint should also be public." | Introspection can disclose sensitive state/metadata and must protect callers with authentication/authorization. |

## 15. Mental flow summary

A secure RFC 7662 Resource Server implementation should follow this flow:

```text
Client sends Bearer access token to orders-api
                │
                ▼
Resource Server receives token without trusting its contents yet
                │
                ▼
HTTPS POST introspection request
  ├─ token=<request's access token>
  ├─ token_type_hint=access_token (optional)
  └─ client authentication for orders-api-introspector
                │
                ▼
Authorization Server processes
  ├─ requester allowed to call endpoint?
  ├─ requester allowed to see token status?
  ├─ token exists, unexpired, unrevoked?
  └─ which metadata may be returned?
                │
                ▼
JSON response
  ├─ active=false -> reject authentication
  └─ active=true  -> continue contract checks
                       ├─ audience/issuer/resource match?
                       ├─ token type/profile match?
                       ├─ sufficient scopes/roles?
                       └─ owner/tenant/business constraints met?
                                 │
                                 ▼
                           Allow operation
                    or deny 401 / 403 / 404
```

**Remember:** **RFC 7662 supplies token status and metadata to an authorized requester; it does not replace the Resource Server's own authorization rules.** `active` is only the first condition. Scope, audience, subject, and supplementary fields are meaningful only when interpreted per the issuer contract; object-level authorization remains the API's responsibility.

### References

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): request, response, `active`, client authorization, and security considerations.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): client authentication, access tokens, and scopes.
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): Bearer token usage and protected resource errors.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html): NumericDate, `sub`, `iss`, `aud` when response metadata uses similar claim names.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): JWT access token contract and differences from introspection.
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): `opaquetoken` configuration, authorities, and `OpaqueTokenIntrospector`.
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): comparison with local JWT verification.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): why object-level authorization must still be checked after token authentication.
