# Handling Responses with Missing Fields, Wrong Types, or Invalid States

In a **Spring Security OAuth 2.0 / OIDC Resource Server**, when an API receives an access token under the *opaque token* mechanism, the application typically calls **OAuth 2.0 Token Introspection** at the Authorization Server (AS) to determine whether the token is still active and to receive attributes permitted for authentication/authorization. This protocol is specified in **RFC 7662**.

A JSON response that "looks right" is not safe enough. In practice, situations like these occur:

- The endpoint returns HTTP `200 OK`, yet **the `active` field is missing**.
- `active` has the value `"true"` (string), `1` (number), `null`, or `[]` instead of a JSON boolean.
- `active=true`, yet metadata required **by the API contract** is missing, such as `aud`, `sub`, or `iss`.
- `scope` is sent as an array or object even though the issuer's profile specifies a string.
- `exp`, `iat`, or `nbf` is a string instead of a NumericDate; or `exp` is already in the past while the response still claims active.
- The AS returns `active=false` along with sensitive metadata.
- The response is HTML/JSON error output, truncated JSON, contains duplicate keys, or returns HTTP `401`/`503` instead of a valid introspection result.
- After an AS upgrade, the data type of `aud` or `scp` changes without the Resource Server client being updated.

If code handles responses like "if the key exists, cast it; if missing, supply a default; if parsing fails, treat as active," the system can suffer **ClassCastException/500**, grant unintended permissions, or skip a mandatory token verification requirement.

This lesson focuses on **handling responses according to a contract, avoiding unintended privilege escalation, and failing closed**. We will distinguish *minimal RFC 7662 constraints* from *stricter `orders-api` constraints*, examine how `OpaqueTokenIntrospector` works, build metadata validation layers, and design tests for structural errors, type mismatches, token states, and upstream failures.

> **Important:** Aside from `active`, most metadata in RFC 7662 is **optional**. A Resource Server is allowed to require additional fields based on **its own** integration contract, but should not broadly label a response lacking `sub`/`aud`/`exp` as "violating RFC 7662." It may be protocol-compliant yet **insufficient** for this API to accept.

Running example throughout:

- **Trusted issuer**: `https://auth.example.test/realms/orders`.
- **Introspection endpoint**: `https://auth.example.test/oauth2/introspect`.
- **Resource Server**: `orders-api`.
- **Introspection client**: `orders-api-introspector`.
- **OAuth client requesting tokens**: `web-portal`.
- **Scopes**: `orders:read`, `orders:write`.
- **Subject**: `alice-123`, tenant `tenant-a`.

All domains, tokens, IDs, and credentials below are illustrative examples only.

---

## 1. Trust Boundary: What Is an Introspection Response Used For?

A typical request:

```http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer opaque-access-token-example
```

The Resource Server sends the token to the AS:

```http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <encoded-introspection-client-credentials>

token=opaque-access-token-example&token_type_hint=access_token
```

After authenticating the introspection client and determining the token state, the AS may return:

```json
{
  "active": true,
  "scope": "orders:read orders:write",
  "client_id": "web-portal",
  "sub": "alice-123",
  "iss": "https://auth.example.test/realms/orders",
  "aud": ["orders-api"],
  "exp": 1890003600
}
```

The Resource Server uses this response to determine:

1. **Authentication:** does the AS confirm the token is active?
2. **Token contract:** which fields have types and semantics appropriate for the current API? Does the token belong to an allowed issuer/resource?
3. **Authority mapping:** which scopes/roles may be mapped into Spring Security authorities?
4. **Business authorization:** does the principal have permission to read order `42` for the right user/tenant?

```mermaid
flowchart TD
    A["Bearer token in HTTP request"] --> B["OpaqueTokenIntrospector"]
    B --> C["HTTPS POST to trusted introspection endpoint"]
    C --> D{"Transport & response valid?"}
    D -->|No| E["Reject, record integration error"]
    D -->|Yes| F{"Is active a boolean?"}
    F -->|No| E
    F -->|false| G["Token inactive → authentication failed"]
    F -->|true| H["Validate schema + issuer/resource contract"]
    H --> I{"Metadata compliant?"}
    I -->|No| E
    I -->|Yes| J["Create controlled principal and authorities"]
    J --> K["Check route scope / role"]
    K --> L["Check owner / tenant / business rules"]
    L --> M["Allow or deny"]
```

**There is no branch where "response parsing fails so let it through anyway."** When a token cannot be established as trustworthy, the request must not execute protected business logic.

### 1.1. HTTP 200 Does Not Mean "Valid Token"

Distinguish **the introspection request being handled by the HTTP server** from **the access token actually being active**:

| Introspection HTTP Response | Meaning | API Behavior |
|---|---|---|
| `200` + `{"active":true}` | Request succeeded; AS reports token is active. | Proceed to validate metadata, scopes, and object policy. |
| `200` + `{"active":false}` | Request succeeded; token is inactive or not permitted to be introspected. | Reject authentication. |
| `200` + `{}` | Missing required field. | Treat response as invalid; grant no permissions. |
| `200` + `{"active":"true"}` | `active` has wrong type. | Treat response as invalid; do not coerce string to true. |
| `401` from AS | Introspection client failed authentication or is unauthorized, depending on AS. | Handle integration error; do not infer token is inactive. |
| `403` from AS | Introspection requester lacks permission for endpoint/resource. | Handle AS authorization error; fail closed. |
| `429`, `5xx`, timeout | AS/quota/network error. | Cannot verify token; bounded retry or incident handling. |
| Unexpected `302` redirect | Endpoint may have moved or configuration is wrong. | Do not forward credentials to an unverified host. |

When `active=false`, the AS should restrict additional metadata so it does not leak information about the token. Even if the endpoint accidentally returns extra metadata, the Resource Server **must not create a principal or authorities from an inactive response**.

### 1.2. The Token Is Not the Only Thing to Verify

Even when `active=true`, the API may need to prove:

- The introspection endpoint belongs to a **trusted Authorization Server** over a valid TLS connection.
- The token was issued by an accepted issuer, or the AS has an equivalent binding mechanism.
- The token is intended for **`orders-api`**, not `payments-api`.
- The token is an appropriate **access token**, not a refresh token.
- Metadata required by policy matches the expected schema.
- The token is not expired or blocked by policy.
- Scopes, roles, and resource ownership are sufficient for the operation.

RFC 7662 alone does not decide the entire policy of an API. That is why **protocol validation** must be separated from the **application token contract**.

---

## 2. What RFC 7662 Actually Specifies

RFC 7662 requires the response to be a **JSON object** with a **boolean** `active` field. Fields such as `scope`, `client_id`, `username`, `token_type`, `exp`, `iat`, `nbf`, `sub`, `aud`, `iss`, and `jti` are defined metadata, yet **are not required to appear in every response**.

### 2.1. `active` Is the First Branching Point

Two basic responses:

```json
{"active": true}
```

```json
{"active": false}
```

According to the RFC, `active=false` typically reflects that the token has expired, been revoked, does not exist, or the introspection requester lacks permission to access that token's metadata. The AS may mask the specific reason behind the same result.

**`active=true` does not mean the token has permission to call every API.** This state is only one part of authentication; routes still require sufficient permissions.

**Wrong-typed** examples:

```json
{"active": "true"}
```

```json
{"active": 1}
```

```json
{"active": null}
```

```json
{"active": []}
```

Do not convert these cases to `true` via `Boolean.parseBoolean(...)`, comparing to `1`, or treating any "truthy" value as active. A schema-broken serializer/issuer may occur, yet **the Resource Server must not patch the protocol with unsafe type coercion**.

### 2.2. Active Can Be Protocol-Valid Even When Other Fields Are Absent

```json
{
  "active": true
}
```

In terms of **RFC 7662 structure**, this response is not necessarily wrong: `scope`, `aud`, `sub`, and `exp` are all optional. For `orders-api`, however, if policy requires `aud` and `sub` to verify the resource and subject, that response **lacks enough data to grant access**.

There are at least two levels of evaluation:

| Level | Question | Example |
|---|---|---|
| **Baseline RFC/schema** | Is the JSON object valid with boolean `active`? | `{"active":true}` satisfies the baseline check. |
| **API integration contract** | Are there enough fields/types to confirm the right issuer/resource/subject and build authorities? | Missing `aud` in a system without another resource binding → reject. |

Do not label every policy violation as "invalid RFC." Incident logging/classification should distinguish a **malformed protocol response** from **insufficient token metadata for this resource**.

### 2.3. The `scope` and `token_type` Fields

Example:

```json
{
  "active": true,
  "scope": "orders:read orders:write",
  "token_type": "Bearer"
}
```

- `scope`, when present per RFC 7662, is a **space-delimited string of scope values**.
- `token_type` is a string that may indicate the token type such as `Bearer`.
- Never add `orders:read` automatically if `scope` is absent.
- Never infer that a refresh token can be used as an API Bearer access token just because `token_type_hint=access_token` was sent in the request. The hint aids lookup, not token-type proof.
- Some issuers use `scp`, `permissions`, or custom role structures; those belong to an **additional contract**, which does not mean `scope` is allowed to change types randomly per request.

---

## 3. Schema Policy for Each Metadata Field

The table distinguishes **RFC data types** from **safe behavior** when missing or wrong-typed. Decisions such as "requiring `aud`" are examples of the **`orders-api` profile**, not mandatory rules of RFC 7662.

| Field | Type / Meaning | If Missing | If Wrong Type |
|---|---|---|---|
| **`active`** | JSON boolean, **required**. | Invalid protocol response, fail closed. | Do not coerce; invalid response. |
| **`scope`** | Space-separated scope token string. | Do not create scope authorities from this claim; routes requiring scopes reject. | Reject response per standard profile or use an agreed vendor-specific mapper; never cast blindly. |
| **`client_id`** | String — OAuth client bound to the token. | Acceptable if API does not require it; if client allowlist is mandatory, reject. | Reject/ignore; do not build client identity from object/number. |
| **`username`** | String — human-friendly username. | Usually does not affect authentication. | Never use as owner/role; may reject per contract. |
| **`token_type`** | String, e.g. `Bearer`. | Decide per profile; do not assume every token is Bearer. | Reject if profile requires an explicit token type. |
| **`exp`** | NumericDate (JSON number, seconds since epoch). | Allowed by RFC; API may require it to bound token age/cache. | Do not arbitrarily parse `"1890003600"` as a number if contract specifies number. |
| **`iat`** | NumericDate. | Usually optional. | Do not use wrong-typed data for audit/time checks. |
| **`nbf`** | NumericDate. | Usually optional. | Do not treat arbitrary strings as timestamps. |
| **`sub`** | String — token subject. | If policy needs user/owner, must reject or look up from a trusted source per contract. | Do not call `toString()` on a map/list to invent a user ID. |
| **`aud`** | String or array of strings. | If AS does not guarantee resource binding otherwise, reject. | Reject objects/numbers/arrays containing non-strings. |
| **`iss`** | String — issuer. | If policy requires verifying issuer, reject or rely on an explicitly guaranteed provider binding. | Do not infer issuer from an unverified token. |
| **`jti`** | String — token ID. | Usually does not affect authentication. | Do not use for caching/auditing if schema is wrong. |
| **`roles` / `permissions`** | Vendor-defined. | Never grant permissions by default. | Follow custom schema; never turn arbitrary data into `ROLE_ADMIN`. |
| **`tenant_id`** | Vendor-defined. | If tenant is required, reject or deny access to tenant data. | Do not coerce objects/lists into a tenant. |

### 3.1. An API Must Choose Its Contract Up Front

Suppose `orders-api` agrees with the Identity team:

- The endpoint only emits metadata usable for **access tokens** intended for `orders-api`.
- `active` must be a boolean (RFC 7662).
- For accepted tokens, `iss`, `aud`, `sub`, and `exp` are **required by `orders-api`**.
- `iss` must equal `https://auth.example.test/realms/orders`.
- `aud` must contain `orders-api`.
- `exp` must be a NumericDate in the future.
- `scope`, if present, is an RFC 7662 string; an empty string means no scopes granted.
- `client_id`, if present, must be a string; sensitive endpoints may require a client allowlist.
- `tenant_id`, if present, must be a string; tenant-specific routes must have a valid tenant context.
- Unknown claims **must never be used automatically to grant authorities**.

This is a **stricter contract than the baseline protocol**. It helps the Resource Server distinguish "the AS says the token is active" from "the AS provided sufficient evidence for this specific API."

### 3.2. When Should `sub` Not Be Required?

With Client Credentials, `sub` may be a service identity or may be absent depending on the issuer. If an API is designed for workloads, the contract can define `client_id` as the primary principal alongside client-specific permissions and audience, instead of requiring a user `sub`.

Do not apply a single user-token schema to every grant. Separate **permitted profiles** by issuer/grant/client/token type and ensure profile selection never depends on a caller-supplied field.

### 3.3. When Can `aud` Be Absent?

RFC 7662 does not mandate `aud`. An AS can bind an introspection client to one resource and **only return active metadata for tokens allowed on that resource**. If this contract is enforced by the AS and tested, the Resource Server may rely on that binding instead of requiring an `aud` claim.

If the AS returns `active=true` for tokens belonging to multiple resources without `aud`, the API cannot reliably confirm the token is meant for itself. In that case, do not silently skip audience verification. That is a **confused deputy / token substitution** risk.

---

## 4. Processing Order Determines Safety

A clear ordering prevents reading permission fields before knowing whether the token is active.

```text
1. Verify the response comes from a trusted introspection endpoint over HTTPS.
2. Check HTTP status and JSON object structure.
3. Check that active exists and is a JSON boolean.
4. If active=false: reject the token; ignore all other metadata.
5. If active=true: check schema and token contract.
6. Verify the right issuer, audience/resource, token type, and expiration if required by contract.
7. Normalize verified metadata into principal/authorities.
8. Apply HTTP/method authorization.
9. Apply ownership, tenant, and business authorization.
```

**Never call `get("scope").asText()` before checking `active`**. A JSON number/object or an inactive response could be coerced to a string or misread. Convert data only after its schema is accepted.

### 4.1. When `active=false` Includes Other Metadata

Response:

```json
{
  "active": false,
  "sub": "alice-123",
  "scope": "orders:read",
  "exp": 1890003600
}
```

Even though the fields look complete, **the token is still inactive**. There is no such thing as "the scope matches so ignore `active: false`."

RFC 7662 advises the AS not to disclose additional information about inactive tokens. If the AS returns metadata alongside `active=false`, the Resource Server must **never use it to authenticate, authorize, or log unnecessary PII**. Record the provider anomaly by error/schema code without dumping the entire response into application logs.

### 4.2. When `active=true` Yet `exp` Is in the Past

```json
{
  "active": true,
  "sub": "alice-123",
  "aud": ["orders-api"],
  "iss": "https://auth.example.test/realms/orders",
  "exp": 1700000000
}
```

If `exp` is in the past according to the current time and API policy, there is an inconsistency between `active=true` and the expiration metadata. Under a contract requiring `exp`, the Resource Server must **reject** rather than treating `active=true` as an unconditional override.

Note that `exp` is a **NumericDate in seconds**, not milliseconds. Clock skew tolerance must be explicitly governed by policy. NumericDates may represent fractional seconds; do not arbitrarily require "must be an integer" and assume that applies across the entire RFC.

### 4.3. When JSON Has Duplicate `active` Keys

A dangerous payload for parser consistency:

```json
{
  "active": false,
  "active": true
}
```

JSON objects with duplicate keys can be handled differently across parsers (first wins / last wins / error). For authentication data, use a JSON parser with **duplicate field detection** or an explicit rejection policy so middleware and application layers never interpret the token differently.

In Jackson, `STRICT_DUPLICATE_DETECTION` can be enabled on the parser handling the response path. If using a library introspector, verify which parser/HTTP client that version actually uses; a validator running **after** JSON has already been parsed into a map cannot recover the fact that a key was duplicated.

---

## 5. When Data Has the Wrong Type: Never Coerce Just to "Get Permissions"

### 5.1. Wrong-Typed `active`

| Input | Why Invalid? | Handling |
|---|---|---|
| `{"active":true}` | Valid type. | Continue validating metadata. |
| `{"active":false}` | Valid type, token inactive. | Reject. |
| `{"active":"true"}` | String, not boolean. | Schema error, fail closed. |
| `{"active":"false"}` | String, not boolean. | Schema error, fail closed. |
| `{"active":1}` | Number, not boolean. | Schema error, fail closed. |
| `{"active":null}` | Null, not boolean. | Schema error, fail closed. |
| `{"active":[]}` | Array, not boolean. | Schema error, fail closed. |
| `{}` | Missing required field. | Schema error, fail closed. |
| `[]` | Root is not a JSON object. | Schema error, fail closed. |

Do not write:

```java
// DO NOT USE: turns arbitrary data into a boolean.
boolean active = Boolean.parseBoolean(
    String.valueOf(response.get("active"))
);
```

The snippet above turns the string `"true"` into true even though the protocol specifies a boolean. Worse, other code might use truthiness conventions that even treat `"false"` as true. Use **strict type checking**.

### 5.2. Wrong-Typed `scope`

Standard contract:

```json
{"active":true,"scope":"orders:read orders:write"}
```

A vendor-specific response might use:

```json
{"active":true,"scope":["orders:read","orders:write"]}
```

However, an array is not the string `scope` representation in RFC 7662. If an issuer genuinely has an array contract, the application must **select a dedicated parser for that profile**, not accept any type via `String.valueOf(...)`.

In particular:

```json
{
  "active": true,
  "scope": {
    "admin": true
  }
}
```

must not produce an `SCOPE_ADMIN` authority merely because the object has an `admin` field. Without a verified contract, **grant no additional authorities**. For APIs enforcing a strict schema, reject the response/token to surface AS drift.

### 5.3. Wrong-Typed `aud` and Resource Confusion

Common valid forms:

```json
{"active":true,"aud":"orders-api"}
```

```json
{"active":true,"aud":["orders-api","reports-api"]}
```

Either a string or a string array can be valid. Conversely:

```json
{"active":true,"aud":[42,"orders-api"]}
```

```json
{"active":true,"aud":{"resource":"orders-api"}}
```

should not be accepted under a string/string-array audience contract. Never call `String.valueOf(aud).contains("orders-api")`, as it can match substrings inside an untrusted object. Compare **intact audience values**:

```text
aud == "orders-api"
OR
aud is an array of strings containing the exact element "orders-api"
```

`"orders-api-dev"` or `"not-orders-api"` must not match `"orders-api"`.

### 5.4. NumericDate with Wrong Units or Types

`exp`, `iat`, and `nbf` in RFC 7662 are JSON numbers in **seconds since the Unix epoch**.

```json
{"active":true,"exp":1890003600}
```

Do not automatically treat these as equivalent:

```json
{"active":true,"exp":"1890003600"}
```

```json
{"active":true,"exp":1890003600000}
```

The first is a wrong-typed string if the contract requires a number. The second is a number that looks like Unix **milliseconds**, which could make a token appear valid for tens of thousands of years if interpreted as seconds. Beyond type checking, you can enforce a **maximum token lifetime policy** or verify the AS sends the right units. Never divide by 1000 based on "number magnitude" without a contract, as that masks provider bugs.

### 5.5. Custom Fields Need Dedicated Validators

Some issuers return:

```json
{
  "active": true,
  "tenant_id": "tenant-a",
  "roles": ["orders-viewer"],
  "permissions": ["orders:approve"]
}
```

If policy requires `tenant_id` to be a string, `roles` a string array, and `permissions` a string array, validate every element properly. Never take an object/map or a list containing numbers, call `toString()`, and prepend `ROLE_` or `PERM_`.

If `roles` is absent, the token may still be active without role permissions. If the API requires that role to reach an endpoint, route/method security will reject it. If the role is **mandatory for a token to belong to a valid profile**, a profile validator should reject early.

---

## 6. Two Customization Layers in Spring Security

In a Spring Security Servlet Resource Server using opaque tokens, the main extension point is **`OpaqueTokenIntrospector`**:

```java
public interface OpaqueTokenIntrospector {
    OAuth2AuthenticatedPrincipal introspect(String token);
}
```

A standard introspector calls the endpoint and returns an `OAuth2AuthenticatedPrincipal`, or throws an exception if the token/response is not accepted. There are **two distinct levels of checking**:

1. **Post-library checking:** wrap a standard introspector, receive the principal already validated by the library, and enforce the **application contract** such as audience, issuer, tenant, or client restrictions.
2. **Raw JSON checking before type conversion:** when you need to strictly enforce boolean `active`, reject duplicate keys, check `scope` in wire format, and classify malformed responses. This level requires owning your own HTTP client/parser or an equivalent extension **before** the response is parsed into a map/principal.

**Do not assume a wrapper after `delegate.introspect(...)` can re-check original JSON types.** The library may have already normalized `exp` to `Instant`, `scope` to a collection, or omitted `active` from the principal; afterward, you can no longer tell whether the AS sent a boolean or a string if the earlier parser coerced it.

### 6.1. Basic Opaque Token Configuration

`pom.xml` under the Spring Boot BOM:

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

security:
  token-contract:
    issuer: https://auth.example.test/realms/orders
    audience: orders-api
```

`INTROSPECTION_CLIENT_SECRET` must be supplied from a Secret Manager or secure runtime injection. **Never hardcode secrets** in Git-tracked config files or Java code.

`SecurityFilterChain`:

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
public class OpaqueApiSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            // Stateless API using Bearer header, not cookie authentication.
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

Disabling CSRF is appropriate only when the API does not use cookies/sessions for authentication; never copy this blindly into session-based web applications.

---

## 7. Approach 1: Wrapping the Standard Introspector to Enforce Contract Metadata

If the introspector already handles HTTP, `active`, and data mapping, the Resource Server only needs to enforce selected metadata. This is usually simpler than reimplementing the entire protocol.

For example, a wrapper accepting only tokens with:

- Exact issuer match.
- Audience containing `orders-api`.
- Non-blank subject.
- Normalized scope metadata, if present, as a string or collection of strings.
- No default scopes, roles, or tenants fabricated.

### 7.1. Illustrative `ContractCheckingOpaqueTokenIntrospector` Code

```java
package com.example.orders.security;

import java.net.URI;
import java.net.URL;
import java.util.Collection;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class ContractCheckingOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final String expectedIssuer;
    private final String expectedAudience;

    public ContractCheckingOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate,
            String expectedIssuer,
            String expectedAudience) {
        this.delegate = delegate;
        this.expectedIssuer = expectedIssuer;
        this.expectedAudience = expectedAudience;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // Delegate handles HTTP request, active check, and parsing.
        // If delegate rejects token/response, exception propagates.
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        Object issuer = principal.getAttribute("iss");
        Object audience = principal.getAttribute("aud");
        Object subject = principal.getAttribute("sub");
        Object scope = principal.getAttribute("scope");

        if (!sameIssuer(issuer)
                || !containsExpectedAudience(audience)
                || !(subject instanceof String s) || s.isBlank()
                || !validNormalizedScopeType(scope)) {
            // Do not log raw tokens or responses containing sensitive data.
            throw new BadOpaqueTokenException(
                "Token does not satisfy orders-api contract");
        }

        return principal;
    }

    private boolean sameIssuer(Object value) {
        if (value instanceof String s) {
            return expectedIssuer.equals(s);
        }
        // Some parsers/versions may represent URLs as URI/URL.
        if (value instanceof URI uri) {
            return expectedIssuer.equals(uri.toString());
        }
        if (value instanceof URL url) {
            return expectedIssuer.equals(url.toString());
        }
        return false;
    }

    private boolean containsExpectedAudience(Object value) {
        if (value instanceof String audience) {
            return expectedAudience.equals(audience);
        }
        if (value instanceof Collection<?> audiences) {
            if (audiences.isEmpty()) {
                return false;
            }
            for (Object item : audiences) {
                if (!(item instanceof String s) || s.isBlank()) {
                    return false;
                }
            }
            return audiences.contains(expectedAudience);
        }
        return false;
    }

    private static boolean validNormalizedScopeType(Object value) {
        // Scope is not mandatory on every token. Routes needing scopes
        // require their own authority; never invent default permissions.
        if (value == null) {
            return true;
        }
        if (value instanceof String) {
            return true;
        }
        if (value instanceof Collection<?> scopes) {
            return scopes.stream()
                .allMatch(s -> s instanceof String);
        }
        return false;
    }
}
```

**Important points when using this wrapper:**

- The class only sees **the principal after the delegate has processed it**, not the raw JSON response directly.
- `scope` may already have been converted by the introspector from a string into a collection. Accepting a collection in the wrapper accepts **the normalized internal form**, not a claim that the AS is allowed to send `scope` as an array on the wire.
- Missing `iss` or `aud` causes the wrapper to reject due to **the `orders-api` contract**, even though RFC 7662 allows them to be absent.
- If a token has no scope, the wrapper may accept authentication, yet routes requiring `SCOPE_orders:read` still reject authorization. If the contract requires every token to carry a non-empty scope, add that check **explicitly**.
- Audience checking is safe only when the `aud` attribute comes from a **trusted introspector** and cannot be overwritten on the principal by the client.

### 7.2. Creating the Delegate and Registering the Bean

Example for Spring Security 6.x supporting `NimbusOpaqueTokenIntrospector`:

```java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
public class OpaqueIntrospectionConfig {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
            String introspectionUri,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
            String clientId,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
            String clientSecret,
        @Value("${security.token-contract.issuer}")
            String issuer,
        @Value("${security.token-contract.audience}")
            String audience
    ) {
        OpaqueTokenIntrospector delegate =
            new NimbusOpaqueTokenIntrospector(
                introspectionUri, clientId, clientSecret);

        return new ContractCheckingOpaqueTokenIntrospector(
            delegate, issuer, audience);
    }
}
```

Implementation/builder names may change or be deprecated across Spring Security 6.x/7.x versions; `NimbusOpaqueTokenIntrospector` is widely used in 6.x. When upgrading, check `SpringOpaqueTokenIntrospector` or the corresponding implementation in your actual library version's docs rather than copying the wrong constructor.

**Do not unconditionally register another `OpaqueTokenIntrospector` bean**, as the application context may be ambiguous about which bean gets used. Ensure the actual filter chain points to the wrapped introspector (via bean auto-wiring or explicit DSL configuration).

### 7.3. When Is a Wrapper Not Enough?

A wrapper cannot verify the following if the delegate has already normalized the data:

- Was `active` originally `"true"` or `true` in the JSON?
- Was `scope` originally a string or an array?
- Did the JSON have duplicate `active` keys?
- Was `exp` an integer, decimal, or string that the delegate coerced?
- Was the response content type `application/json`, or did an HTTP converter read another type?

If **policy mandates inspecting the raw bytes/JSON from the endpoint before the library parser interprets it**, validation must sit **at the HTTP response reception boundary**, not merely inspect `OAuth2AuthenticatedPrincipal` afterward.

---

## 8. Approach 2: Inspecting Raw JSON Responses Before Creating a Principal

When a project must strictly reject wrong-typed responses, the clearest approach is owning the pipeline:

```text
RestOperations POST introspection
    ↓
HTTP status / TLS / content-type / response size
    ↓
Strict JSON parser (checks duplicate fields)
    ↓
active: mandatory boolean
    ↓
If false → reject
    ↓
Required fields per API contract
    ↓
Create OAuth2AuthenticatedPrincipal with explicit attributes/authorities
```

This is an **educational example of custom introspection**, not a recommendation that every application reimplement an RFC 7662 client. If a standard introspector satisfies your policy, prefer the **wrapper** in the previous section. When writing your own HTTP/parser layer, you take full responsibility for client authentication, timeouts, TLS, error handling, secret masking, parser limits, logging, and library updates.

### 8.1. `StrictRfc7662Introspector` Example

This example assumes the **introspection client ID/secret contain only safe ASCII characters** for Basic Auth; for credentials with special characters, check the AS/RFC 6749 OAuth client authentication encoding rules and prefer a vetted library HTTP client/authenticator. The code focuses on **response JSON schema**, not replacing transport security policy.

```java
package com.example.orders.security;

import java.math.BigDecimal;
import java.net.URI;
import java.time.Clock;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OAuth2IntrospectionException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestOperations;

public final class StrictRfc7662Introspector
        implements OpaqueTokenIntrospector {

    // RFC 6749 scope-token: visible ASCII excluding double quote and backslash.
    private static final Pattern SCOPE_TOKEN =
        Pattern.compile("[\\x21\\x23-\\x5B\\x5D-\\x7E]+");

    private final RestOperations http;
    private final ObjectMapper json;
    private final Clock clock;
    private final URI endpoint;
    private final String introspectionClientId;
    private final String introspectionClientSecret;
    private final String expectedIssuer;
    private final String expectedAudience;

    public StrictRfc7662Introspector(
            RestOperations http,
            ObjectMapper json,
            Clock clock,
            URI endpoint,
            String clientId,
            String clientSecret,
            String expectedIssuer,
            String expectedAudience) {
        this.http = http;
        this.json = json;
        this.clock = clock;
        this.endpoint = endpoint;
        this.introspectionClientId = clientId;
        this.introspectionClientSecret = clientSecret;
        this.expectedIssuer = expectedIssuer;
        this.expectedAudience = expectedAudience;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        if (token == null || token.isBlank()) {
            throw new BadOpaqueTokenException("Invalid bearer token");
        }

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_FORM_URLENCODED);
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));

        // Demo: Basic Auth for ASCII-safe test credentials.
        // Production: match the auth method registered with the AS.
        headers.setBasicAuth(
            introspectionClientId, introspectionClientSecret);

        MultiValueMap<String, String> form =
            new LinkedMultiValueMap<>();
        form.add("token", token);
        form.add("token_type_hint", "access_token");

        ResponseEntity<String> response;
        try {
            response = http.exchange(
                endpoint,
                HttpMethod.POST,
                new HttpEntity<>(form, headers),
                String.class
            );
        } catch (RestClientException ex) {
            // HTTP 401/403/429/5xx, DNS, timeout, TLS...
            // Do not attach token or response body to public exceptions.
            throw new OAuth2IntrospectionException(
                "Introspection endpoint unavailable or request rejected");
        }

        if (response.getStatusCode().value() != 200
                || response.getBody() == null) {
            throw invalidResponse();
        }

        JsonNode root;
        try {
            root = json.readTree(response.getBody());
        } catch (JsonProcessingException ex) {
            throw invalidResponse();
        }

        if (root == null || !root.isObject()) {
            throw invalidResponse();
        }

        JsonNode active = root.get("active");
        if (active == null || !active.isBoolean()) {
            throw invalidResponse();
        }

        if (!active.booleanValue()) {
            // Important: do not read scope/sub even if sent in response.
            throw new BadOpaqueTokenException("Inactive token");
        }

        // The fields below are required by the orders-api contract,
        // NOT because every RFC 7662 response must contain them.
        String issuer = requiredString(root, "iss");
        String subject = requiredString(root, "sub");
        List<String> audiences = requiredAudience(root.get("aud"));

        if (!expectedIssuer.equals(issuer)
                || !audiences.contains(expectedAudience)) {
            throw new BadOpaqueTokenException(
                "Token not intended for this resource");
        }

        BigDecimal expiry = requiredNumericDate(root, "exp");
        BigDecimal now = BigDecimal.valueOf(
            clock.instant().getEpochSecond());
        if (expiry.compareTo(now) <= 0) {
            throw new BadOpaqueTokenException("Expired token");
        }

        // RFC 7662 allows nbf and iat to be absent.
        if (root.has("nbf")) {
            BigDecimal notBefore = requiredNumericDate(root, "nbf");
            if (notBefore.compareTo(now) > 0) {
                throw new BadOpaqueTokenException(
                    "Token not yet valid");
            }
        }
        if (root.has("iat")) {
            requiredNumericDate(root, "iat");
        }

        String scopesValue = optionalString(root, "scope");
        List<String> scopes = parseStandardScopes(scopesValue);

        // Additional fields must match schema if used.
        optionalString(root, "client_id");
        optionalString(root, "token_type");
        optionalString(root, "jti");

        Set<GrantedAuthority> authorities = new LinkedHashSet<>();
        for (String scope : scopes) {
            authorities.add(
                new SimpleGrantedAuthority("SCOPE_" + scope));
        }

        Map<String, Object> attributes = new LinkedHashMap<>();
        attributes.put("active", true);
        attributes.put("iss", issuer);
        attributes.put("sub", subject);
        attributes.put("aud", audiences);
        attributes.put("exp", expiry);
        attributes.put("scope", scopes);
        if (root.hasNonNull("client_id")) {
            attributes.put("client_id",
                root.get("client_id").textValue());
        }

        // Principal name is the contract-validated subject.
        return new DefaultOAuth2AuthenticatedPrincipal(
            subject, attributes, authorities);
    }

    private static String requiredString(
            JsonNode root, String field) {
        JsonNode value = root.get(field);
        if (value == null || !value.isTextual()
                || value.textValue().isBlank()) {
            throw invalidResponse();
        }
        return value.textValue();
    }

    private static String optionalString(
            JsonNode root, String field) {
        JsonNode value = root.get(field);
        if (value == null) {
            return null;
        }
        if (!value.isTextual()) {
            throw invalidResponse();
        }
        return value.textValue();
    }

    private static BigDecimal requiredNumericDate(
            JsonNode root, String field) {
        JsonNode value = root.get(field);
        if (value == null || !value.isNumber()) {
            throw invalidResponse();
        }
        return value.decimalValue();
    }

    private static List<String> requiredAudience(JsonNode value) {
        if (value == null) {
            throw invalidResponse();
        }
        if (value.isTextual() && !value.textValue().isBlank()) {
            return List.of(value.textValue());
        }
        if (value.isArray()) {
            List<String> audiences = new ArrayList<>();
            for (JsonNode entry : value) {
                if (!entry.isTextual()
                        || entry.textValue().isBlank()) {
                    throw invalidResponse();
                }
                audiences.add(entry.textValue());
            }
            if (!audiences.isEmpty()) {
                return audiences;
            }
        }
        throw invalidResponse();
    }

    private static List<String> parseStandardScopes(String scope) {
        if (scope == null || scope.isEmpty()) {
            return List.of();
        }

        List<String> result = new ArrayList<>();
        // Standard delimiter is ASCII space, not comma.
        for (String item : scope.split(" ", -1)) {
            if (!SCOPE_TOKEN.matcher(item).matches()) {
                throw invalidResponse();
            }
            result.add(item);
        }
        return List.copyOf(result);
    }

    private static OAuth2IntrospectionException invalidResponse() {
        return new OAuth2IntrospectionException(
            "Invalid introspection response schema");
    }
}
```

**Scope and limitations of this example:**

1. The code genuinely inspects **raw JSON** and verifies `active` is a true boolean before creating a principal.
2. Any `active=false` response is rejected **before reading permission metadata**.
3. `iss`, `sub`, `aud`, and `exp` are treated as **mandatory per the `orders-api` contract**. If your AS does not guarantee these fields, do not copy the code without first agreeing on how resource binding/subject are guaranteed.
4. `scope` is required to be a standard RFC 7662 string; arrays/vendor extensions are not accepted automatically. If `scope` is absent, the principal gets no `SCOPE_...` authority, so scope-protected routes reject.
5. The `nbf` and `exp` checks here have no clock skew allowance. Production systems should pick an explicit clock-skew policy aligned with the AS, never silently adding several hours.
6. `exp` is stored in the principal as a `BigDecimal` defined by this custom class; framework introspectors may use another internal type such as `Instant`. Downstream code **must match the type produced by its own implementation** rather than casting blindly.
7. The HTTP client lacks **connection pooling, total deadline, retry/backoff, response body size limits**, rate limiting, and full observability. These must be added for production use.
8. The `ObjectMapper` in the example must be configured with **strict duplicate detection**, depth/size input limits, and disallowed unsafe coercion per security requirements. Simply reading a `JsonNode` does not by itself enable duplicate-key detection.
9. The example catches `RestClientException` and throws a generic error. In production, classify 401/403 credential errors, 429/5xx, timeouts, and JSON errors **in safe logs**, without exposing raw tokens/secrets/bodies in client error responses.
10. Basic Auth here assumes suitable credentials. For OAuth 2.0 client IDs/secrets containing special characters, apply the issuer's proper encoding/auth method; prefer the library's vetted authentication implementation over hand-rolled headers.
11. The example demonstrates strict parsing principles; it does not replace integration testing and security review of custom code during QA.

### 8.2. Initializing the HTTP Client with Finite Timeouts

Example registering the custom implementation in a Spring Boot environment:

```java
package com.example.orders.security;

import java.net.URI;
import java.time.Clock;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.web.client.RestTemplate;

@Configuration
class StrictIntrospectionConfig {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
            String endpoint,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
            String clientId,
        @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
            String clientSecret,
        @Value("${security.token-contract.issuer}")
            String issuer,
        @Value("${security.token-contract.audience}")
            String audience,
        ObjectMapper objectMapper
    ) {
        SimpleClientHttpRequestFactory factory =
            new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(1_500);
        factory.setReadTimeout(2_000);

        RestTemplate http = new RestTemplate(factory);

        return new StrictRfc7662Introspector(
            http,
            objectMapper,
            Clock.systemUTC(),
            URI.create(endpoint),
            clientId,
            clientSecret,
            issuer,
            audience
        );
    }
}
```

The timeout values here are **illustrative only**, not a universal recommendation. If the API has an SLO of a few hundred milliseconds or calls an AS across regions, measure latency, concurrency, and gateway timeouts.

**Choose one customization approach:** Section 7 and Section 8 are **two alternatives**. Do not place both `OpaqueIntrospectionConfig` and `StrictIntrospectionConfig` in the same context if both declare an `OpaqueTokenIntrospector` bean.

### 8.3. Detecting Responses Parsed Incorrectly Before Custom Logic Runs

If an application uses `RestTemplate` with a converter that automatically maps JSON to `Map<String, Object>`, the conversion step may already have altered types or duplicate-key handling. If preserving the wire schema is required, fetch the **raw response** and parse it with a strict configuration.

Example test path using Jackson to reject duplicate keys:

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper strictMapper = new ObjectMapper();
strictMapper.enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);

// When reading JSON with two duplicate "active" keys, the mapper must throw an error.
```

Configuring the global `ObjectMapper` may affect business JSON endpoints, so consider **a dedicated mapper for introspection** for precise control. Never assume that a JSON object "looking valid" after parsing proves its original keys were unique.

---

## 9. Protecting Against Null, Missing Metadata, and Unexpected Types in the Principal

Whether using a standard or custom introspector, downstream code must avoid cast errors.

### 9.1. Do Not Write Direct Getters Assuming Every Attribute Is Present

Error-prone example:

```java
// DO NOT USE:
String tenantId =
    principal.<String>getAttribute("tenant_id").toUpperCase();

List<String> aud =
    (List<String>) principal.getAttribute("aud");
```

Problems:

- `tenant_id` might be missing → `NullPointerException`.
- `tenant_id` might have the wrong type → `ClassCastException`.
- `aud` might be a single string or a collection, not a `List<String>`.
- If an element in the collection is not a string, an unchecked generic cast may not catch it early.
- The exception could produce an unclear `500` instead of rejecting the token per policy.

### 9.2. Creating a Normalized Application Context

One approach is converting data only after validation:

```java
package com.example.orders.security;

public record AuthenticatedActor(
    String issuer,
    String subject,
    String tenantId
) { }
```

Mapper:

```java
package com.example.orders.security;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

public final class ActorMapper {
    private ActorMapper() { }

    public static AuthenticatedActor requireUserActor(
            OAuth2AuthenticatedPrincipal principal) {
        Object rawIssuer = principal.getAttribute("iss");
        Object rawSubject = principal.getAttribute("sub");
        Object rawTenant = principal.getAttribute("tenant_id");

        if (!(rawIssuer instanceof String issuer)
                || issuer.isBlank()
                || !(rawSubject instanceof String subject)
                || subject.isBlank()
                || !(rawTenant instanceof String tenant)
                || tenant.isBlank()) {
            throw new AccessDeniedException(
                "Authenticated principal lacks required user context");
        }

        return new AuthenticatedActor(issuer, subject, tenant);
    }
}
```

**Note:** if the introspector normalized `iss` to a `URI`/`URL`, the mapper must use the agreed contract type or a controlled conversion utility. **Never use `String.valueOf(rawIssuer)` to produce a trusted issuer from an arbitrary object.**

`AuthenticatedActor` must be built only from an **authenticated principal** or a trusted internal identity mapping path, never from request JSON or client HTTP headers.

### 9.3. Does Missing Metadata Belong to Authentication or Authorization?

This depends on the metadata's role:

- If `iss`/`aud`/**token type** is a prerequisite for the Resource Server to accept the token in the first place, missing/wrong values should normally be handled at **authentication/token contract**.
- If the token is active and its profile is valid, yet it lacks the scope to call a read endpoint, that is **authorization**: the token lacks `SCOPE_orders:read`, so the route returns 403.
- If the token is active and has sufficient scope, yet lacks tenant information needed to decide order access, you can deny at application authorization; if tenant is mandatory for *every* token in the profile, reject early at authentication.
- If the AS returns malformed JSON or wrong-typed `active`, that is a **response/protocol integration error**, not a typical "user lacks permission" case.

**There is no single HTTP status for every schema discrepancy.** Real Spring Security exception handlers may return 401 or report an upstream error depending on implementation; what matters is **not executing the protected operation**. If you want to distinguish 401/403/503 for clients, define an explicit error contract without leaking token state or internal data.

---

## 10. Never Create Authorities from Arbitrary Data

A response may contain several claims:

```json
{
  "active": true,
  "scope": "orders:read",
  "roles": ["ADMIN"],
  "permissions": ["orders:delete"],
  "tenant_id": "tenant-a"
}
```

Never turn every value into a Spring authority unconditionally:

```java
// DO NOT USE:
for (Object value : response.values()) {
    authorities.add(
        new SimpleGrantedAuthority("ROLE_" + value));
}
```

Distinguish carefully:

- Standard `scope` → authorities like `SCOPE_orders:read` once the parser confirms a string and valid token profile.
- `roles` → issuer/resource-specific roles with a schema and allowlist.
- `permissions` → business permissions if the API accepts this contract.
- `tenant_id` → data-scoping context, **not a role**.

If both `scope` and `scp`/`roles` appear, do not blindly **union** every permission. Some claims may apply only to another resource or actor. Read only sources defined in the contract for the corresponding issuer/tenant/audience.

### 10.1. Checking Permission Values Against an Allowlist

Suppose the system defines two custom permissions:

```text
orders:approve
orders:export
```

A mapper can map them to:

```text
PERM_orders:approve
PERM_orders:export
```

only after verifying the `permissions` claim is a string array and allowed by issuer/profile. If an unfamiliar string `"superadmin"` appears, never automatically grant `ROLE_SUPERADMIN`. You may ignore unknown permissions if the contract specifies forward compatibility, or reject the entire response if strict consistency is required. This decision must be **consistent and tested**.

### 10.2. Never Solve Response Errors by Weakening Route Security

For example, when responses omit `scope`, the API might see increased `403`s on `GET /api/orders/**`. Wrong fix:

```java
// DO NOT USE: lets every active token enter the route.
.requestMatchers("/api/orders/**").authenticated()
```

The right fix is to **confirm which scopes the AS is issuing**, whether the response matches the contract, whether the converter maps `SCOPE_...`, and which permissions the route actually requires. Never weaken security requirements to mask an integration bug.

---

## 11. Distinguishing AS Errors, Token Errors, and Business Errors

An operable system must classify failures so operators know whether to fix credentials, fix schema, or ask the user to obtain a new token.

| Error Category | Example | Security Behavior | Investigation Path |
|---|---|---|---|
| **Inactive token** | `active=false` | Do not create principal. | Token expired, revoked, or AS refuses introspection. |
| **Protocol schema** | Missing `active`, `active="true"`, malformed JSON. | Fail closed; never coerce types. | New AS version, serializer, proxy, parsing. |
| **Token contract** | `active=true` but missing `aud`/`iss`/`sub` required by API. | Reject token per profile. | AS–API contract, issuer/resource binding. |
| **Metadata type** | `exp` is a string, `aud` is an object. | Do not use wrong-typed data. | JSON mapping/token profile. |
| **Credential integration** | AS returns HTTP 401/403. | Do not let request through. | Introspection client secret, client auth method, permissions. |
| **Upstream transient** | Timeout, `429`, `503`. | Fail closed; bounded retry if appropriate. | Network, TLS, quota, AS availability. |
| **Insufficient scope** | Token active, missing `orders:read`. | Route denies authorization. | Scope grant and converter. |
| **Object-level denial** | Token has scope, yet order belongs to another user. | Reject per owner/tenant policy. | BOLA/IDOR, database/ACL, delegation. |

Never log the entire response when schema validation fails. Introspection responses may contain PII, OAuth client IDs, scopes, and token IDs; raw tokens and introspection client secrets must never appear in logs/traces.

---

## 12. Block Network Errors, Yet Do Not Equate Them with `active=false`

During AS outages, some programs turn every exception into "token inactive" or a fallback:

```java
// DO NOT USE:
try {
    return delegate.introspect(token);
} catch (Exception e) {
    return anonymousPrincipalWithNoAuthorities();
}
```

This can create an unintended principal, hide dependency outages, and prevent administrators from detecting expired credentials. Even if the principal has no authorities, `authenticated()` routes could still pass depending on implementation.

A safe handling approach:

- **Inactive token**: the library throws an appropriate exception; no authentication is created.
- **AS HTTP 401/403**: different root cause; operators check client credentials and policy.
- **`429`/`503`/timeout**: very bounded retries with backoff/jitter and total deadline; if still no result, reject.
- **Invalid schema**: do not retry indefinitely, because structurally broken responses rarely fix themselves in milliseconds.
- **Wrong audience/issuer**: do not probe introspection at other issuers based on token input to see which one reports active.
- **Missing scope**: do not "retry until scope appears" without an explicit grant-update workflow.

### 12.1. Bounded Timeouts and Retries

An introspection request crosses the network. Configure:

- Finite connect and read timeouts.
- Total time across all attempts within the request budget.
- Low max retries for genuinely transient errors.
- Exponential backoff + jitter, honoring `Retry-After` when reasonable.
- Connection pool/concurrency limits to avoid multiplying requests to the AS.
- A circuit breaker if AS outages persist, with **no branch granting access when the circuit is open**.

Simple policy example:

```text
if AS returned valid active=false:
    reject token, do not retry
else if AS returned invalid JSON/schema:
    fail closed, report integration error
else if AS timeout/503:
    retry at most N times within total deadline
    if no valid answer: fail closed
else if AS returned valid active=true:
    validate contract and route/object authorization
```

Under high load, enabling retries simultaneously in the HTTP client, service mesh, and gateway can cause a **retry storm**. Measure request amplification and establish a single owner for the retry budget.

### 12.2. Cached Introspection Results Also Have Schema and Lifecycle

If the application caches `active=true` results:

- Cache only after the response **is verified and schema-valid**.
- Never cache a parse-failed response as a valid principal.
- Keep TTL no longer than `exp` if present, and aligned with revocation requirements.
- Never use an indefinite active cache to bypass the AS after a token is revoked.
- Never share metadata across issuers/resources without namespacing and a trust model.
- Never serve token A's cached principal for token B due to a poorly designed cache key.
- Never treat a network error as `active=false` or `active=true` and cache that unverified state.

In practice, the system's **revocation delay** depends on whether the API caches introspection, cache TTLs, and invalidation capability; you cannot claim "opaque tokens are always revoked instantaneously" if the API itself holds stale entries.

---

## 13. Testing Missing-Field, Wrong-Type, and Abnormal-State Responses

A genuinely useful test suite must send **real JSON/HTTP responses through the introspection pipeline**, rather than only mocking a principal and testing `hasAuthority`.

### 13.1. Matrix of Positive and Negative Tests

| Test Case | Sample JSON/HTTP | Expected Outcome |
|---|---|---|
| Valid active, meets contract | `{"active":true,"iss":"...","aud":["orders-api"],"sub":"alice","exp":...}` | May create principal; permissions per `scope`. |
| Minimal inactive | `{"active":false}` | Reject token. |
| Inactive still carries scope | `{"active":false,"scope":"orders:read"}` | Still reject; ignore scope. |
| Missing `active` | `{"scope":"orders:read"}` | Schema error, fail closed. |
| String `active` | `{"active":"true"}` | Schema error, no coercion. |
| Numeric `active` | `{"active":1}` | Schema error. |
| `active=null` | `{"active":null}` | Schema error. |
| Root array | `[{"active":true}]` | Schema error. |
| HTML body | `<html>error</html>` | Content/parse error, grant nothing. |
| Truncated JSON | `{"active":tru` | Parse failure, grant nothing. |
| Duplicate `active` key | `{"active":false,"active":true}` | Strict parser must reject. |
| Active valid, missing `aud` | `{"active":true,"sub":"alice"}` | Rejected by `orders-api` contract if `aud` required. |
| Wrong audience | `{"active":true,"aud":["payments-api"]}` | Reject tokens belonging to other resources. |
| Wrong-typed audience | `{"active":true,"aud":{"name":"orders-api"}}` | Schema error, no `toString().contains(...)`. |
| Scope absent | `{"active":true,...}` | No scope authority granted; scope-requiring routes reject. |
| Scope as array | `{"active":true,"scope":["orders:read"]}` | Reject per the example's string `scope` profile. |
| Scope as object | `{"active":true,"scope":{"admin":true}}` | Create no authority. |
| String `exp` | `{"active":true,"exp":"1890003600"}` | Reject if contract requires NumericDate number. |
| Expired `exp` | `{"active":true,"exp":1700000000}` | Reject even when `active=true`. |
| Future `nbf` | `{"active":true,"nbf":<future-seconds>}` | Reject per time policy. |
| Missing `sub` | `{"active":true,"aud":["orders-api"]}` | If user profile requires subject: reject. |
| AS HTTP 401 | Unauthorized | Introspection client error, reject token. |
| HTTP 429/503 | Rate limit / Service Unavailable | Bounded retry if configured, then fail closed. |
| HTTP 204 | No body | Cannot treat token as active. |
| HTTP 200 body `null` | JSON null | Schema error. |
| Active token, insufficient scope | Has `scope="orders:write"` | `GET` requiring read must deny authorization. |
| Active token, sufficient scope, wrong owner | Alice uses token to read Bob's order | Deny at object authorization. |

The `...` and `<future-seconds>` placeholders in the table are shorthand, **not valid JSON test fixtures**. In real tests, populate full `iss`, `aud`, `sub`, and `exp` values and pin time with `Clock.fixed(...)` so tests are deterministic.

### 13.2. Direct JUnit Tests for Parser and Schema

Extract raw JSON validation into an independently testable function/object. Pseudocode example:

```text
given HTTP 200, body {"active":"true"}:
    expect protocol/schema failure

given HTTP 200, body {"active":false,"scope":"orders:read"}:
    expect inactive-token rejection
    expect zero authorities

given HTTP 200, body active=true, aud=["payments-api"]:
    expect token-contract failure

given HTTP 200, body active=true, iss/orders-api/sub valid,
                      scope="orders:read", exp in future:
    expect principal with SCOPE_orders:read
```

With Jackson, a unit test can verify duplicate-key rejection:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class IntrospectionJsonStrictTest {

    @Test
    void duplicateActiveIsRejected() {
        ObjectMapper mapper = new ObjectMapper();
        mapper.enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION);

        assertThrows(JsonProcessingException.class,
            () -> mapper.readTree(
                "{\"active\":false,\"active\":true}"));
    }
}
```

This is a **parser test**; it does not by itself prove that the HTTP client or Spring filter chain uses that exact mapper. Integration tests must feed JSON through an endpoint stub to the real implementation.

### 13.3. Integration Testing with a Mock HTTP Endpoint

Use `MockRestServiceServer` when the custom introspector uses `RestTemplate`, or WireMock/MockWebServer when a local HTTP server is needed.

Example with `MockRestServiceServer`:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import java.net.URI;
import java.time.Clock;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.server.resource.introspection.OAuth2IntrospectionException;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

class StrictIntrospectionHttpTest {

    @Test
    void stringActiveFailsClosed() {
        RestTemplate http = new RestTemplate();
        MockRestServiceServer server =
            MockRestServiceServer.bindTo(http).build();

        String endpoint = "https://auth.example.test/oauth2/introspect";
        server.expect(requestTo(endpoint))
            .andExpect(method(HttpMethod.POST))
            .andRespond(withSuccess(
                "{\"active\":\"true\"}", MediaType.APPLICATION_JSON));

        var introspector = new StrictRfc7662Introspector(
            http,
            new ObjectMapper(),
            Clock.systemUTC(),
            URI.create(endpoint),
            "test-client",
            "test-secret",
            "https://auth.example.test/realms/orders",
            "orders-api"
        );

        assertThrows(OAuth2IntrospectionException.class,
            () -> introspector.introspect("test-token"));

        server.verify();
    }
}
```

This test uses **fake secrets and makes no real network calls**. Add assertions for:

- HTTP method `POST`, content-type `application/x-www-form-urlencoded`.
- Form-encoded `token=...` body.
- `Authorization` header using proper client authentication and not printed to public output.
- `active` false → exception/denial per policy.
- Complete `iss`/`aud`/`sub`/`exp`/`scope` → right principal/authorities.
- HTTP 401/429/503, timeouts, and malformed JSON bodies never allow requests into business endpoints.
- Negative tests with object `scope`, numeric `aud`, string `exp`, duplicated `active`.
- Integration tests against a real staging AS to catch serialization differences.

If tests use a default `ObjectMapper` while production uses a mapper with duplicate detection, inject the production mapper into tests. Never just assert stub HTTP 200 and ignore whether `active` and the contract are actually enforced.

### 13.4. What Does MockMvc `opaqueToken()` Test?

`spring-security-test` supports:

```java
mvc.perform(get("/api/orders/42")
    .with(opaqueToken().authorities(
        new SimpleGrantedAuthority("SCOPE_orders:read"))))
   .andExpect(status().isOk());
```

Prerequisite: the controller/fixture and owner policy permit access to order `42`.

However, `opaqueToken()` **mocks an already authenticated principal** without actually sending an introspection request to the AS. Therefore, this test **does not prove** `active` is type-checked, duplicate keys are rejected, or HTTP endpoints handle errors properly. To test schemas, use **an HTTP stub + real introspector** or direct parser tests.

### 13.5. Testing Contract Changes Between the AS and API

When upgrading the Authorization Server version, compare test tokens across grants:

| Token Profile | Metadata That May Differ | Must Test |
|---|---|---|
| Authorization Code / user token | `sub`/`username`, `scope`, tenant. | User identity, owner, audience, expiry. |
| Client Credentials / service token | `client_id`, possibly no user `sub`. | Separate workload profile; do not force user schema. |
| Token exchange/delegation | Subject, additional actor/claims, different audience. | Do not automatically inherit all scopes from original token. |
| Token intended for another API | `aud` lacks `orders-api`. | Reject token substitution. |
| Revoked token | `active=false` or AS policy handling. | Do not cache active too long. |
| Near-expiry token | `exp` and clock skew. | Do not let tokens live past policy. |

Any contract change must have explicit **versioning/migration**. Never disable validators in production merely because the AS renamed a field.

---

## 14. Observing and Auditing Schema Errors Without Leaking Tokens

An introspection response may contain usernames, OAuth client IDs, scopes, tenants, roles, token identifiers, and other sensitive fields. **Never log the entire response** on parse failure just to "have debug data."

### 14.1. Useful Metric Groups

Example application-defined metric names:

| Metric / Event | Meaning |
|---|---|
| `introspection_request_total{result=...}` | Distinguishes success, inactive, HTTP error, timeout, schema error. |
| `introspection_response_schema_error_total{field=...}` | Missing `active`, wrong-typed `scope`, wrong `aud`... using **fixed labels**. |
| `introspection_dependency_failure_total{status=...}` | 401/403/429/5xx or TLS/network failures. |
| `opaque_authentication_failure_total{reason=...}` | Token rejected; standardized reason code. |
| `opaque_authorization_failure_total{reason=...}` | Insufficient scope, tenant/owner denial. |
| `introspection_duration_seconds` | p95/p99 round-trip latency to AS. |
| `introspection_cache_hit_total` | If cached; semantics and TTL must be understood. |

**Never use** tokens, `jti`, `sub`, or response bodies as metric labels; both cardinality and privacy become issues. In logs, use request correlation IDs and fixed error names:

```text
event=introspection_response_rejected
reason=active_wrong_type
issuer_config_id=orders-auth
http_status=200
correlation_id=<request-id>
```

Never include the raw token or client secret in that log entry.

### 14.2. Fail Closed While Still Classifying Incidents

A clean design records safe internal reason codes:

```text
TOKEN_INACTIVE
INTROSPECTION_SCHEMA_INVALID
INTROSPECTION_REQUIRED_CLAIM_MISSING
INTROSPECTION_CLAIM_TYPE_INVALID
INTROSPECTION_AUDIENCE_MISMATCH
INTROSPECTION_ISSUER_MISMATCH
INTROSPECTION_EXPIRED_METADATA
INTROSPECTION_CLIENT_UNAUTHORIZED
INTROSPECTION_UPSTREAM_UNAVAILABLE
SCOPE_INSUFFICIENT
OBJECT_ACCESS_DENIED
```

These reasons are for controlled logging/monitoring. Client responses should not reveal details like "token belongs to Bob in tenant B," sensitive scope lists, client secrets, or AS JSON bodies.

---

## 15. Runbook When the AS Starts Returning Malformed-Schema Responses

Suppose right after an Identity Provider upgrade, the API sees increased 401/5xx errors and internal logs show `INTROSPECTION_CLAIM_TYPE_INVALID`.

**Step 1 — Classify before changing code.** Determine whether tokens are inactive, responses are malformed, introspection client credentials failed, or scopes are simply insufficient. Check the HTTP status from the AS and metric reasons without printing raw tokens.

**Step 2 — Check the active contract.** Is `active` a proper boolean? Which field changed type? For instance, `aud` changing from string to string array may still fall within RFC-supported forms; `scope` changing from string to object is a major breaking change. Distinguish protocol rules from API contract rules.

**Step 3 — Verify the response source.** Confirm requests are not hitting the wrong realm/tenant, a proxy mutating bodies, an unexpected redirect, or broken TLS. Never switch endpoints based on data inside the token.

**Step 4 — Stay fail-closed.** Never silently coerce `active="true"` to true, remove audience/issuer checks, or enable `permitAll()`. If an AS bug causes disruption, prefer rolling back/fixing the AS or rolling out a reviewed migration.

**Step 5 — Reproduce with tests.** Save a **redacted fixture free of PII/secrets** representing the schema and reproduce the failure in unit/integration tests. Never commit a raw response containing production user/token data.

**Step 6 — Agree on a new contract if the change is intentional.** If the AS officially changed `scp` to an array or added a tenant field, update versioned parsers/profiles and test user/service grants and other audiences.

**Step 7 — Verify actual permissions.** An active token with route permissions must not access another user's or tenant's data. Test list, export, and bulk endpoints as well.

**Step 8 — Check caching.** If caching introspection results, track which instances still hold old response schemas. Avoid flushing all caches simultaneously during an AS outage, as that increases load. For revoked tokens, cache invalidation must meet policy.

**Step 9 — Monitor after recovery.** Watch error reasons, introspection p95, 401/403 rates, AS request rate, and distribution by pod/region. Confirm no unexpected authorities appeared outside the approved list.

**Step 10 — Update documentation.** Record the AS version, API-required fields, data types, missing/invalid handling, HTTP error mappings, and rollback steps.

---

## 16. Checklist for Designing a Clear Contract

| Question | Decision Needed |
|---|---|
| Which endpoint verifies tokens? | Fixed URL, HTTPS, client auth, introspection requester permissions. |
| What data is required by the RFC? | JSON object with boolean `active`. |
| What data is required by the **API**? | Issuer, audience, subject, expiry, tenant, or client depending on profile. |
| How is `active=false` handled? | Reject immediately; ignore extra metadata. |
| When `active` is missing or wrong-typed? | Schema failure, no coercion, fail closed. |
| When `scope` is missing? | Grant no scope authority; scope-requiring routes deny; may reject token if required by contract. |
| Can `aud` be a string or an array? | Yes per RFC, but the parser must validate every element properly. |
| Which units do `exp`/`nbf` use? | NumericDate seconds; skew and max-age policies. |
| Can custom claims map to permissions? | Only with an agreed issuer/profile and allowlist. |
| Are schema errors and network errors retried? | Classify separately; bounded retries only for transient upstream failures. |
| Which HTTP statuses do clients receive? | Designed and tested mapping for authentication/authorization/dependency errors. |
| Does introspection caching delay revocation? | Explicit TTL/invalidation, never exceeding expiry. |
| Are tokens for other APIs/tenants tested for rejection? | Mandatory in multi-resource/multi-tenant environments. |
| Are duplicate `active` and wrong types tested? | At the raw parser if required by policy. |
| Do logs leak tokens/secrets/PII? | Masked and using fixed reason codes/metric labels. |

## 17. Distinguishing Three Final Outcomes

From an `orders-api` client's perspective, three scenarios may look similar yet have completely different root causes:

```text
(1) Introspection:
    HTTP 200 + {"active": false}
    → token is not accepted
    → authentication failure (usually 401)

(2) Introspection:
    HTTP 200 + {"active": true, "scope": "orders:read", ...}
    → token is contract-valid
    → POST /api/orders requires SCOPE_orders:write
    → authorization failure (usually 403)

(3) Introspection:
    HTTP 200 + {"active": "true"}
    → malformed RFC 7662 structure
    → integration/protocol error; no principal created
    → HTTP status returned to client depends on error handler;
      protected API must not execute
```

And a fourth scenario:

```text
(4) Introspection:
    HTTP 200 + {"active": true, "scope": "orders:read", ...}
    → valid token, valid scope
    → Alice requests Bob's order
    → object-level authorization denies with 403/404
```

All four scenarios can occur within a single Resource Server. **A safe parser does not replace scope policy; a proper scope policy does not replace resource ownership checks.**

---

## 18. Technical References

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): request/response, `active`, optional metadata, client authentication, and endpoint security.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): OAuth client authentication, `scope`, and access token semantics.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): Bearer tokens and resource access errors.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519.html): `iss`, `aud`, `sub`, and NumericDate.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): JWT access token contract for comparison with introspection.
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259.html): JSON values, object member names, and duplicate-member risks.
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): `OpaqueTokenIntrospector`, authorities, and custom introspection.
- [Spring Security API — OpaqueTokenIntrospector](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html): interface and `introspect(...)` method.
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): applying scopes/authorities after authentication.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): per-resource authorization after token verification.

**Conclusion:** When customizing introspection in Spring Security, follow the principle of **checking the protocol first, validating the issuer/resource contract next, and only then creating the principal and authorities**. `active` must be a genuine boolean; optional metadata becomes mandatory only when API policy specifies it; responses with missing or wrong-typed fields must be rejected or grant no permissions, and you must never coerce types to turn ambiguous data into valid authentication.
