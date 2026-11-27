# Data Types, Empty Values, Missing Claims, and Rejected Tokens

In a **Spring Security OAuth 2.0 / OIDC Resource Server**, verifying a JWT's signature only proves that the payload was not tampered with relative to a trusted signing key. Before allowing an API request through, the system must also decide **which claims are required**, **which data types and values are acceptable**, and **how a token must be rejected when a claim is missing, null, empty, mistyped, or semantically invalid**.

This is a critical security boundary: a JWT with a **valid signature** can still cause failures or open privilege-escalation paths if the Resource Server misreads a data type, falls back to an unsafe default, or ignores a claim the API genuinely needs.

This lesson covers schema-design principles for JWT claims, distinguishing **missing / JSON null / empty / malformed**, using **`JwtDecoder`**, **`OAuth2TokenValidator`**, and authorization in Spring Security, along with test scenarios for rejected tokens. Examples use **Spring Boot 3.x, Spring Security 6.x, Java 17+**, a Servlet Resource Server, and an **`orders-api`** service that trusts only JWT Access Tokens from a configured issuer.

## 1. A Valid Signature Does Not Mean Valid Claims

Suppose an Authorization Server issues a JWT Access Token with the following payload:

~~~json
{
  "iss": "https://login.example.test/realms/demo",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iat": 1893452400,
  "exp": 1893456000,
  "scope": "orders.read",
  "tenant_id": "tenant-42",
  "roles": ["ORDER_READER"]
}
~~~

The Resource Server must answer more than "is the signature valid?":

1. Does **issuer** match the trusted issuer?
2. Does **audience** target **orders-api**?
3. Was the token issued under the profile expected by the API, and is it still valid?
4. Is **tenant_id** a non-empty string, and does it match the target resource's tenant?
5. Is **roles** a string array containing allowed roles?
6. Is **scope** formatted per the token contract, and does it grant read access to orders?

A signed JWT only protects claims **placed into the token by the signer**. If the issuer and Resource Server disagree on schema, even a validly signed value can be wrong for business logic. Even after the decoder accepts the JWT, **authorization** must ensure the token cannot access out-of-scope data.

~~~text
Authorization: Bearer <jwt>
             |
             v
    Verify signature / algorithm / key
             |
             v
    Validate registered claims
    iss, aud, exp, nbf, ...
             |
             v
    Validate custom claims contract
    tenant_id, roles, scope, ...
             |
             v
    Authentication accepted
             |
             v
    Authorization by scope, tenant, and resource
             |
          Allow or deny
~~~

**Token validation** and **authorization** are related yet distinct:

- A token missing a claim **required for token acceptance** should be rejected at **authentication**, typically **401 Unauthorized**.
- A valid token lacking **permission** for an operation is typically rejected at **authorization**, usually **403 Forbidden**.

To distinguish them accurately, first define the **schema and policy** for every claim.

## 2. What Value Types Exist in JSON?

A JWT Claims Set is fundamentally a **JSON object** of name–value pairs. JSON supports:

| JSON Type | Example | Meaning in JWT |
| --- | --- | --- |
| **string** | `"tenant-42"` | Issuer, subject, tenant, scope text, etc., depending on claim. |
| **number** | `1893456000` | NumericDate timestamp, counter, or numeric field defined by profile. |
| **boolean** | `true` | Status flag, such as `email_verified` in OIDC. |
| **array** | `["orders-api", "reports-api"]` | Multiple audiences, roles, permissions, etc. |
| **object** | `{"region":"apac"}` | Nested structure governed by an explicit contract. |
| **null** | `null` | Null value; never equivalent to an automatically valid value. |

Beyond **type**, individual claims carry specific rules:

- `iss` is a **string** per RFC 7519.
- `sub` is a **string**, interpreted within the issuer's context.
- `aud` may be a **string** or an **array of strings** per RFC 7519.
- `exp`, `nbf`, `iat` are **NumericDate**, represented as **JSON numbers** (seconds since Unix epoch), not date strings.
- `scope` is typically a **space-delimited string** in compliant JWT Access Token profiles; some providers use `scp` with a different representation requiring its own contract.
- `roles`, `tenant_id`, `permissions` are common custom names, yet **there is no single JSON type enforced across all issuers**.

**Never assume a familiar-looking claim name automatically has the expected type.** One issuer might emit `roles: ["ORDER_READER"]`, while another emits `roles: "ORDER_READER"`. If an API accepts both loosely without a clear contract, permission enforcement becomes inconsistent.

## 3. Distinguishing Missing Claims, JSON Null, Empty, and Wrong Type

The following cases are fundamentally different:

| Situation | Example `tenant_id` Claim | Interpretation |
| --- | --- | --- |
| **Missing** | No `tenant_id` key in JSON. | The issuer omitted the claim from the token. |
| **JSON null** | `"tenant_id": null` | The key is present with no value. |
| **Empty string** | `"tenant_id": ""` | Zero-length string. |
| **Whitespace only** | `"tenant_id": "   "` | String with no meaningful content once whitespace is considered. |
| **Wrong type** | `"tenant_id": 42` | Number instead of string. |
| **Wrong structure** | `"tenant_id": ["tenant-42"]` | Array instead of a single tenant identifier. |
| **Unexpected value** | `"tenant_id": "tenant-99"` | Valid type, though potentially unauthorized for the target resource. |

For **roles**, many variants can occur:

~~~json
{"roles": ["ORDER_READER"]}
~~~

~~~json
{"roles": []}
~~~

~~~json
{"roles": [""]}
~~~

~~~json
{"roles": null}
~~~

~~~json
{"roles": "ORDER_READER"}
~~~

If the API profile requires **a non-empty role list where every element is a valid string**, only the first payload satisfies the rule. `[]` can be valid under a **different contract** meaning "no roles", yet it must never be treated as granting access. Whether missing or empty is allowed must be defined explicitly per field.

### 3.1. Fail-Closed Principle

**Fail-closed** means whenever the system cannot be certain a credential satisfies a required rule, it **does not grant access** by default.

For a required claim:

~~~text
Is the required claim present?
  | No -> Reject token
  |
  Yes
  v
Is it non-null and of the expected type?
  | No -> Reject token
  |
  Yes
  v
Does it satisfy non-empty and domain constraints?
  | No -> Reject token
  |
  Yes
  v
Evaluate against policy / target resource
  | No -> Deny access
  |
  Yes -> May proceed subject to remaining checks
~~~

An **optional** claim does not necessarily cause token rejection when absent. However, **absence must never escalate into higher privilege**. For instance, missing `roles` may map to **no roles** if the contract permits, but must never default to `ADMIN` or skip tenant checks.

### 3.2. "Missing" vs. "Null" Once Inside Java

When a JWT is decoded into `Map<String, Object>`, you can check key presence:

~~~java
Map<String, Object> claims = jwt.getClaims();
boolean present = claims.containsKey("tenant_id");
Object value = claims.get("tenant_id");
~~~

- If `present == false`, the claim key does not exist in the map.
- If `present == true` and `value == null`, the map holds a null entry.
- However, some JSON parsing, claim conversion, or library steps may **strip or normalize nulls**, making the two states harder to tell apart after decoding.

If a contract genuinely requires distinguishing **absent JSON key** from **key with null** at the raw data level, inspect at the appropriate parsing/claim-conversion boundary and test using **real signed JWTs**. From a security standpoint, both cases are usually rejected identically when the claim is required.

## 4. Registered Claims: Not All Are Mandatory in RFC 7519

RFC 7519 defines **Registered Claim Names**: `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `jti`. However, **RFC 7519 does not require every JWT to carry all seven claims**. Mandatory rules depend on the **token profile** and the receiving system's policy.

For example, an **OIDC ID Token** has OIDC-specific rules; a **JWT Access Token profile (RFC 9068)** has different requirements for Resource Servers. Never copy ID Token validation logic into an Access Token validator without accounting for audience, `typ`, and profile.

| Claim | JSON Type and Basic Rule | What to Consider When Missing or Invalid |
| --- | --- | --- |
| **iss** | String identifying issuer. | A Resource Server with a trusted issuer must reject missing/mismatched issuers. |
| **sub** | String identifying subject. | May be required by profile; never fall back to email if `sub` is missing. |
| **aud** | Single string or array of strings. | An API requiring audience must reject tokens missing its audience. |
| **exp** | NumericDate. | If the API profile requires `exp`, tokens missing `exp` must be rejected. |
| **nbf** | NumericDate if present. | Tokens before `nbf` must be rejected, allowing only configured small clock skew. |
| **iat** | NumericDate if present. | If the profile requires `iat`, reject missing/invalid values; `iat` never replaces `exp`. |
| **jti** | String token ID if present. | Does not prevent replay on its own without state tracking/denylisting. |

### 4.1. `aud`: Both String and Array Can Be Valid

Both JWT Claims Sets below express an audience targeting `orders-api` per RFC 7519:

~~~json
{"aud": "orders-api"}
~~~

~~~json
{"aud": ["orders-api", "reports-api"]}
~~~

Other examples fail a policy requiring "audience must include `orders-api`":

~~~json
{"aud": []}
~~~

~~~json
{"aud": ["billing-api"]}
~~~

~~~json
{"aud": 123}
~~~

~~~json
{"aud": null}
~~~

**Never write a validator assuming `aud` is always a single string** and comparing with `equals("orders-api")`; that can wrongly reject valid arrays or mishandle other structures. Spring Security's `Jwt.getAudience()` provides the normalized list of audiences after decoding:

~~~java
if (!jwt.getAudience().contains("orders-api")) {
    // Reject tokens issued for other resources.
}
~~~

If your policy strictly validates **raw JSON types**, remember that the decoder may **normalize registered claims** while converting JSON into `Jwt`. Verify behavior through the real decoder rather than only building mock `Jwt` objects with pre-normalized claims.

### 4.2. `exp`: Missing `exp` Can Be a Risk Even When "Not Expired"

Two distinct cases:

~~~json
{"exp": 1893456000}
~~~

~~~json
{"exp": null}
~~~

And a token **completely missing `exp`**. If the API policy requires Access Tokens **to be bounded by expiration**, tokens with missing or null `exp` must be rejected.

Some timestamp validators are designed to check **`exp` when present**, without necessarily requiring every JWT to include it. Therefore:

> **Never equate checking "has `exp` expired?" with checking "does `exp` exist and have a valid value?"**

If your contract requires `exp`, add an explicit **presence** check alongside expiration validation. Do the same for `iat` if your token profile requires an issuance timestamp.

### 4.3. NumericDate: Seconds, Not Date Strings or Milliseconds

`exp`, `iat`, and `nbf` use **NumericDate**: seconds since `1970-01-01T00:00:00Z` (per RFC 7519 semantics). Example:

~~~json
{
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893456000
}
~~~

Do not equate that with:

~~~json
{"exp": "2030-01-01T00:00:00Z"}
~~~

~~~json
{"exp": 1893456000000}
~~~

The first is an **ISO-8601 string**, not a NumericDate JSON number; the second looks like **milliseconds**, which would make the token live thousands of years if interpreted as seconds. An API should never "guess" units or coerce arbitrary strings into expirations to accept a token.

When Spring Security's `NimbusJwtDecoder` constructs a `Jwt` object, standard time claims are typically converted into **`Instant`**. Inspecting `Jwt.getClaims().get("exp")` may therefore show a normalized Java type, **no longer the raw JSON number**. Do not confuse the JSON wire schema with post-conversion Java types.

If security policy requires rejecting **invalid raw JSON types**, test with real signed JWTs, review the claim-set converter/decoder and profile rules, and do not rely solely on manually constructed `Jwt` objects.

### 4.4. `iss`: Present With the Wrong Value Must Still Be Rejected

Suppose the API trusts only:

~~~text
https://login.example.test/realms/demo
~~~

All of the following fail that issuer policy:

~~~json
{"iss": ""}
~~~

~~~json
{"iss": "https://login.example.test/realms/other"}
~~~

~~~json
{"iss": "https://login.example.test/realms/demo/"}
~~~

The third string differs from the trusted issuer by a trailing **/**. Never strip paths or do fuzzy matching to trust every issuer sharing a hostname. Use the **exact issuer identifier published by the Authorization Server** and an explicitly configured validator.

## 5. Custom Claims: Schema Must Be Defined by the System

Suppose **`orders-api`** defines this Access Token contract:

| Claim | Required Type | Required? | Rule |
| --- | --- | --- | --- |
| **iss** | String/URI | Yes | Exact trusted issuer. |
| **aud** | String or array of strings | Yes | Must include `orders-api`. |
| **exp** | NumericDate | Yes | Not expired at request time. |
| **iat** | NumericDate | Yes | Must be present under this token profile. |
| **scope** | String | Yes | Non-empty; scopes checked per endpoint. |
| **tenant_id** | String | Yes | Non-empty; identifies tenant owning the grant. |
| **roles** | Array of strings | Yes in this example | Non-empty array; every element is a valid role. |

This is an **example contract** for a specific system, not a universal JWT rule. Another API might treat `roles` as optional or use `scp` instead of `scope`; in that case, redefine the contract and validators accordingly.

### 5.1. Wrong Types Are More Dangerous Than "Simply Not Getting Data"

Tokens with valid signatures yet non-conforming custom claims may look like:

~~~json
{"tenant_id": 42}
~~~

~~~json
{"tenant_id": ""}
~~~

~~~json
{"roles": "ORDER_READER"}
~~~

~~~json
{"roles": ["ORDER_READER", 99]}
~~~

~~~json
{"roles": ["ORDER_READER", null]}
~~~

Never blindly coerce with `String.valueOf(claim)` and treat `42` as a valid tenant ID, or turn arbitrary objects into role strings. Identification rules must adhere to the agreed schema. For role arrays, validate **every element**, not only the first item.

### 5.2. An Empty Array Never Implies Full Access

Suppose an issuer emits:

~~~json
{
  "scope": "",
  "roles": []
}
~~~

If `roles` is optional and an empty array means **no roles**, the Resource Server may treat the token as authenticated while rejecting privileged endpoints with **403**. If the profile requires at least one role, the validator can reject the token upfront with **401**.

**Both policies can be valid in different systems**, provided they are fixed by contract. Never write logic like "if `roles` is empty, skip role checks".

### 5.3. Avoid Confusing `false`, `0`, `""`, and `null`

In JSON, these values are completely distinct:

~~~json
{
  "email_verified": false,
  "login_count": 0,
  "display_name": "",
  "approval": null
}
~~~

Do not apply JavaScript-style "truthy/falsy" logic uniformly to claims: **`false`** or **`0`** can be meaningful valid values, whereas **`null`** or a missing claim is a different condition. Spring Security exposes claims as typed Java objects, so use **explicit type and value checks**.

For instance, a business flag `can_export` grants permission only when it is actually boolean `true`—never treat `"true"` or `1` as equivalent if the contract defines a boolean.

## 6. Reading Claims in Spring Security Without Masking Type Errors

After `JwtDecoder` succeeds, Spring Security supplies a `Jwt` object. Common accessors include:

~~~java
String subject = jwt.getSubject();
String tenantId = jwt.getClaimAsString("tenant_id");
List<String> roles = jwt.getClaimAsStringList("roles");
Map<String, Object> claims = jwt.getClaims();
~~~

Convenience methods like `getClaimAsString` and `getClaimAsStringList` are handy, yet **should not be mistaken for a complete schema validator**. Depending on input types and claim conversion, values may be converted or throw when incompatible.

When **`tenant_id` must be a JSON string**, inspect the underlying value in the post-decoder map for custom claims:

~~~java
Object rawTenant = jwt.getClaims().get("tenant_id");
if (!(rawTenant instanceof String tenantId)
        || tenantId.isBlank()) {
    // Claim violates contract; request must be rejected.
}
~~~

For a role array:

~~~java
Object rawRoles = jwt.getClaims().get("roles");

if (!(rawRoles instanceof List<?> roleList)
        || roleList.isEmpty()) {
    // Contract violation.
}
~~~

Once the list is present, still check the type and value of **every element**. Never cast `(List<String>) rawRoles` assuming every element is a string: generics are erased at runtime, so a list containing a number passes the list cast and only fails later when elements are consumed.

**Important limitation:** `Jwt.getClaims()` reflects data **after the decoder's conversion step**. Standard claims like `exp` and `aud` may have been normalized by the library; custom claims generally mirror JSON structures unless a claim-set converter altered them. If you need strict enforcement of raw JSON types prior to conversion, enforce rules at the parse/decode boundary and test with real signed tokens.

## 7. Writing a Fail-Closed Validator for Required Claims

In Spring Security, **`OAuth2TokenValidator<Jwt>`** lets you enforce acceptance/rejection rules during authentication. Returning **`OAuth2TokenValidatorResult.failure(...)`** causes `JwtDecoder` to reject the token, typically resulting in **401** for the Bearer request.

Suppose our example contract requires:

1. `exp` and `iat` must exist after the decoder builds `Jwt`.
2. `aud` must include `orders-api`.
3. `tenant_id` must be a non-blank string.
4. `roles` must be a **non-empty** array whose elements are all non-blank strings.
5. `scope` must be a non-blank string in the agreed issuer format.

### 7.1. Custom Validator

Example class **`RequiredApiClaimsValidator.java`**:

~~~java
import java.util.List;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class RequiredApiClaimsValidator
        implements OAuth2TokenValidator<Jwt> {

    private final String requiredAudience;

    public RequiredApiClaimsValidator(String requiredAudience) {
        this.requiredAudience = requiredAudience;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {

        // Presence is distinct from expiration validation.
        if (jwt.getExpiresAt() == null) {
            return invalid("Required expiration time is missing");
        }
        if (jwt.getIssuedAt() == null) {
            return invalid("Required issued-at time is missing");
        }

        if (!jwt.getAudience().contains(requiredAudience)) {
            return invalid("Required audience is missing");
        }

        Object tenant = jwt.getClaims().get("tenant_id");
        if (!(tenant instanceof String tenantId)
                || tenantId.isBlank()) {
            return invalid("Invalid tenant claim");
        }

        Object roles = jwt.getClaims().get("roles");
        if (!(roles instanceof List<?> roleList)
                || roleList.isEmpty()) {
            return invalid("Invalid roles claim");
        }

        for (Object role : roleList) {
            if (!(role instanceof String roleName)
                    || roleName.isBlank()) {
                return invalid("Invalid roles claim");
            }
        }

        Object scope = jwt.getClaims().get("scope");
        if (!(scope instanceof String scopeValue)
                || scopeValue.isBlank()) {
            return invalid("Invalid scope claim");
        }

        return OAuth2TokenValidatorResult.success();
    }

    private static OAuth2TokenValidatorResult invalid(String message) {
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", message, null));
    }
}
~~~

This code intentionally inspects **objects** instead of relying on coerced strings. Because **roles** is a custom claim, it checks `List<?>` and each element; because **exp/iat** are normalized by the decoder into `Instant`, it checks `jwt.getExpiresAt()` and `jwt.getIssuedAt()`.

These are **rules for the example token profile**, not universal rules for every JWT. If an API does not require roles on every request, design that claim as optional and evaluate roles at authorization time—while **never inventing default privileges when absent**.

A production system might add:

- Pattern/domain validation on `tenant_id`.
- Checking role names against an allowlist of roles meaningful to the API.
- Checking token scopes against scopes supported by the application, if required by profile.
- Checking that `iat` is not too far in the future or that token age stays within policy limits.
- Checking token type/profile when multiple JWT kinds exist.

**Never echo raw offending claim values** in `OAuth2Error`, logs, or HTTP bodies. Report only which validation category failed to avoid leaking personal data or tokens. Handle internal error messages carefully in error handlers as well.

### 7.2. Combining Spring Security Validators with the Custom Validator

Example configuring **`NimbusJwtDecoder`** to fetch public keys from a JWK Set:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtValidationConfig {

    private static final String ISSUER =
        "https://login.example.test/realms/demo";
    private static final String JWKS =
        "https://login.example.test/realms/demo/protocol/openid-connect/certs";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS)
            .build();

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<Jwt>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                new RequiredApiClaimsValidator("orders-api")));

        return decoder;
    }
}
~~~

**`JwtValidators.createDefaultWithIssuer(ISSUER)`** applies the default validators—including issuer and timestamp checks per framework configuration; **`RequiredApiClaimsValidator`** adds the API's contract rules, notably **presence** for `exp` and `iat`, audience, and custom claims.

Calling `decoder.setJwtValidator(...)` replaces any previous validator chain. Therefore, **never set only a custom validator and omit the default checks**. Also restrict signing algorithms and JWKS sources per your Authorization Server contract.

When you declare a custom `JwtDecoder` bean, Spring Boot generally skips creating its auto-configured YAML decoder. Do not assume `audiences` or `issuer-uri` properties in `application.yml` automatically attach validators to your custom bean; verify explicitly which decoder the Resource Server uses.

### 7.3. What If You Use Boot Properties Instead of a Custom Bean?

Common JWT Resource Server configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/demo
          jwk-set-uri: https://login.example.test/realms/demo/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

On Spring Boot versions supporting `audiences`, these properties configure JWT verification for issuer and API audience. However, **custom requirements** like non-blank string `tenant_id` or non-empty list `roles` **do not materialize automatically from issuer configuration**. Enforce them via validators and authorization per contract.

If you need extra validators while reusing Boot's decoder, pick the integration approach supported by your project's version and keep the validator chain clear; avoid declaring two conflicting decoder beans.

## 8. Separating Validation from Authorization for Accurate 401/403 Responses

A JWT can be **valid for authentication** yet lack the scope needed for an endpoint:

~~~json
{
  "iss": "https://login.example.test/realms/demo",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "iat": 1893452400,
  "scope": "orders.read",
  "tenant_id": "tenant-42",
  "roles": ["ORDER_READER"]
}
~~~

If `POST /api/orders` requires **`SCOPE_orders.write`**, a JWT with only `orders.read` must receive **403** after authentication succeeds.

### 8.1. Sample `SecurityFilterChain`

~~~java
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
    SecurityFilterChain apiFilterChain(HttpSecurity http)
            throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

In this example:

- **Missing/invalid Bearer JWT** or a missing required claim in the decoder → typically **401**.
- Valid JWT lacking the required method scope → **403**.
- Valid JWT with the required scope → proceeds to the controller, where tenant, owner, and resource checks can also run.

Spring Security normally maps `scope` or `scp` to authorities prefixed with **`SCOPE_`**. If the issuer profile structures scopes differently, configure **`JwtAuthenticationConverter`** or an appropriate converter. Never assume a `roles` claim automatically becomes `ROLE_...` authorities without a configured mapping.

Disabling CSRF in this snippet applies strictly to **Bearer-header-only** APIs that do not use session cookies as credentials. If the same backend also handles cookie/session-based OIDC login, apply appropriate CSRF protection per security chain.

### 8.2. Error Decision Table

| Condition | Failing Stage | Typical HTTP Status |
| --- | --- | --- |
| Missing `Authorization: Bearer` on protected endpoint | Authentication | **401** |
| Invalid signature or untrusted signing key | Authentication | **401** |
| Wrong issuer/audience or expired token | Token validation | **401** |
| `tenant_id` is a number in a string-required profile | Token validation | **401** |
| Missing `exp` when profile requires it | Token validation | **401** |
| Missing `roles` when schema requires it, prior to authorization | Token validation | **401** |
| Valid JWT lacking required read/write scope | Authorization | **403** |
| Valid JWT and scope, wrong resource tenant | Resource authorization | **403** (or 404 when resource-hiding policy applies) |
| Token satisfies authentication and authorization | Request processed | **200/201/...** per operation |

Do not blur "missing a required structural claim" into "valid token lacking permissions" unless the system **deliberately** defines that claim as optional and evaluates permissions at authorization time.

### 8.3. Error Messages Must Not Leak Tokens

Example concise responses:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Content-Type: application/json

{"code":"invalid_token","message":"Unable to authenticate the request."}
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
Content-Type: application/json

{"code":"forbidden","message":"Insufficient permissions."}
~~~

Exact `WWW-Authenticate` values depend on the situation and Spring Security handlers; not every `403` error will match this example identically. **Never echo JWTs, sensitive claims, raw exceptions, or stack traces** in headers or response bodies. In a Servlet Resource Server, filter-chain errors occur **before the controller**, so relying solely on `@RestControllerAdvice` is not enough to customize all Bearer authentication errors.

## 9. Safely Reading Claims in Controllers and Business Services

Once the JWT is authenticated, a controller can inspect the principal:

~~~java
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/tenants")
public class TenantOrdersController {

    @GetMapping("/{tenantId}/orders")
    Map<String, Object> listOrders(
            @PathVariable String tenantId,
            @AuthenticationPrincipal Jwt jwt) {

        String tokenTenant =
            jwt.getClaimAsString("tenant_id");

        if (tokenTenant == null || !tokenTenant.equals(tenantId)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN);
        }

        // Illustration: business layer must still check that
        // resources belong to this tenant and verify scope/role.
        return Map.of("tenantId", tenantId, "orders", "[]");
    }
}
~~~

In this lesson's architecture, `RequiredApiClaimsValidator` already checked that `tenant_id` is **properly typed and non-blank**. The controller checks whether **the claim matches the requested resource**. Those are two distinct responsibilities.

This illustrative controller only demonstrates tenant comparison; it is not a complete order-management API and does not verify record ownership. A real application should enforce data-access checks in the service/repository layer per business policy to prevent **BOLA/IDOR** vulnerabilities.

### 9.1. Avoid Defaulting to Broad Access When a Claim Is Missing

The following pattern is **unsafe** if a missing `tenant_id` lets the caller read all tenants:

~~~java
// DO NOT DO THIS:
String tenant = jwt.getClaimAsString("tenant_id");
if (tenant == null) {
    return orderService.findAllOrders(); // Unintended privilege escalation!
}
~~~

Instead, if the schema requires a tenant, reject missing-tenant tokens in the validator; if the service ever encounters a missing value, **deny the operation** rather than widening the query.

### 9.2. Never Treat Client-Supplied Headers as Verified Claims

The following request cannot grant itself permissions:

~~~http
GET /api/tenants/tenant-99/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN
X-Tenant-Id: tenant-99
X-User-Role: ADMIN
~~~

Client-sent `X-Tenant-Id` and `X-User-Role` headers are **untrusted input**. When the API needs tenant or role information, read it from the verified JWT or a managed authorization source, then compare against the resource. A valid JWT signature never allows a client to override its tenant via arbitrary headers.

## 10. Claim Type Failures Can Occur at Multiple Layers

When a JWT carries malformed claims, behavior depends on **which layer catches the error**:

~~~text
Raw Bearer JWT
    |
    v
1. JOSE/JWT parsing
    |-- Malformed JSON, broken token structure
    |-- Cannot read header/claims
    |     -> Authentication fails
    v
2. NimbusJwtDecoder / claim conversion
    |-- Cannot convert standard claims
    |-- Incompatible data type
    |     -> Decode fails
    v
3. OAuth2TokenValidator<Jwt>
    |-- Missing exp, tenant_id, roles, ...
    |-- Issuer/audience/time mismatch
    |     -> Token validation fails
    v
4. JwtAuthenticationConverter
    |-- Map scope/roles to GrantedAuthority
    v
5. AuthorizationFilter / Method Security
    |-- Missing scope, wrong tenant, missing resource permission
    |     -> 403 / policy response
    v
Controller
~~~

**Never rely on "a bad type will surely throw an exception" as your schema policy.** One decoder or converter might coerce certain values while another version rejects them. Critical fields therefore require **validators with explicit rules** tested against real JWTs.

### 10.1. Claim Normalization and the Risk of Checking the Wrong Layer

Spring Security converts claims from Nimbus into familiar Java types; for example:

- `exp` and `iat` are typically exposed as **`Instant`** in `Jwt`.
- `aud` is typically exposed as **`List<String>`**.
- Custom claims such as `tenant_id` or `roles` usually retain their JSON-mapped structure unless custom claim conversion alters them.

If an application must reject **string-typed JSON `exp`** while a converter happens to parse strings into timestamps, simply checking `jwt.getExpiresAt() != null` **does not prove the raw JSON type was a number**. Enforce strict type rules where raw values remain visible, or configure a strict converter/decoder and test with mistyped payloads. Never build schema guarantees on unverified assumptions about library type conversions.

### 10.2. Do Not Mix Claims Across Token Profiles

An **OIDC ID Token** may include `email`, `email_verified`, `nonce`, and `auth_time`, yet it targets an **OIDC Client**, not a Resource Server's Access Token endpoint by default.

An **OAuth 2.0 JWT Access Token** may include `client_id`, `scope`, `aud` targeting the API, and issuer-specific claims. **Presence** and **type** requirements must come from the **actual profile**, not a generic claim list borrowed from ID Tokens.

In particular, an ID Token with a valid issuer and signature still fails audience and intended-use checks. The Resource Server must reject tokens not issued for it.

## 11. Unit-Testing the Custom Validator with Synthetic `Jwt` Objects

To test **presence/type/value rules** independently of network and signatures, you can build a `Jwt` directly and call the validator. This is a **validator unit test** and does not verify RSA/JWKS or the Bearer filter chain.

JUnit 5 example using `RequiredApiClaimsValidator` from Section 7:

~~~java
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RequiredApiClaimsValidatorTest {

    private static final Instant NOW =
        Instant.parse("2030-01-01T00:00:00Z");

    private final RequiredApiClaimsValidator validator =
        new RequiredApiClaimsValidator("orders-api");

    private Jwt jwt(
            Object tenant, boolean includeTenant,
            Object roles, boolean includeRoles,
            Object scope, boolean includeScope) {

        Map<String, Object> claims = new LinkedHashMap<>();
        claims.put("iss", "https://login.example.test/realms/demo");
        claims.put("sub", "user-123");
        claims.put("aud", List.of("orders-api"));
        claims.put("iat", NOW);
        claims.put("exp", NOW.plusSeconds(600));

        if (includeTenant) {
            claims.put("tenant_id", tenant);
        }
        if (includeRoles) {
            claims.put("roles", roles);
        }
        if (includeScope) {
            claims.put("scope", scope);
        }

        return new Jwt(
            "synthetic-token",
            NOW,
            NOW.plusSeconds(600),
            Map.of("alg", "RS256"),
            claims);
    }

    @Test
    void validCustomClaimsPass() {
        Jwt token = jwt(
            "tenant-42", true,
            List.of("ORDER_READER"), true,
            "orders.read", true);
        assertFalse(validator.validate(token).hasErrors());
    }

    @Test
    void missingTenantIsRejected() {
        Jwt token = jwt(
            null, false,
            List.of("ORDER_READER"), true,
            "orders.read", true);
        assertTrue(validator.validate(token).hasErrors());
    }

    @Test
    void nullTenantIsRejected() {
        Jwt token = jwt(
            null, true,
            List.of("ORDER_READER"), true,
            "orders.read", true);
        assertTrue(validator.validate(token).hasErrors());
    }

    @Test
    void blankTenantAndWrongTypeAreRejected() {
        Jwt blank = jwt(
            "   ", true,
            List.of("ORDER_READER"), true,
            "orders.read", true);
        Jwt number = jwt(
            42, true,
            List.of("ORDER_READER"), true,
            "orders.read", true);

        assertTrue(validator.validate(blank).hasErrors());
        assertTrue(validator.validate(number).hasErrors());
    }

    @Test
    void invalidRolesAreRejected() {
        Jwt missing = jwt(
            "tenant-42", true,
            null, false,
            "orders.read", true);
        Jwt empty = jwt(
            "tenant-42", true,
            List.of(), true,
            "orders.read", true);
        Jwt wrongType = jwt(
            "tenant-42", true,
            "ORDER_READER", true,
            "orders.read", true);
        Jwt wrongElement = jwt(
            "tenant-42", true,
            List.of("ORDER_READER", 12), true,
            "orders.read", true);

        assertTrue(validator.validate(missing).hasErrors());
        assertTrue(validator.validate(empty).hasErrors());
        assertTrue(validator.validate(wrongType).hasErrors());
        assertTrue(validator.validate(wrongElement).hasErrors());
    }

    @Test
    void missingOrEmptyScopeIsRejected() {
        Jwt missing = jwt(
            "tenant-42", true,
            List.of("ORDER_READER"), true,
            null, false);
        Jwt empty = jwt(
            "tenant-42", true,
            List.of("ORDER_READER"), true,
            "", true);

        assertTrue(validator.validate(missing).hasErrors());
        assertTrue(validator.validate(empty).hasErrors());
    }
}
~~~

These tests use **synthetic `Jwt` instances** with `iat`/`exp` already typed as **`Instant`** like post-decode objects. They prove **validator logic on normalized data**, not how Nimbus handles raw JSON, key sources, or signatures.

To test **missing `exp` and `iat`**, build a test `Jwt` omitting them—or, more reliably across the decoding boundary, sign a real test JWT missing those claims to verify end-to-end behavior. When constructing synthetic `Jwt` instances, ensure you respect any constructor invariants of your Spring Security version.

## 12. Testing with Real Signed JWTs to Catch Raw Claim Errors

Cases like `exp: "2030-01-01T00:00:00Z"`, `aud: 7`, or arrays with mistyped elements should be tested **through the same JWT decoder used in production**, because converters can normalize inputs before custom validators execute.

A reliable test flow:

~~~text
JUnit test
   |
   +-- generate test-only RSA key pair
   +-- build JWT claims per test case
   +-- sign JWT with test private key
   |
   v
NimbusJwtDecoder using test public key
   |
   +-- verify JWS signature
   +-- convert raw JSON claims -> Jwt
   +-- run default validators + custom validator
   |
   v
decode succeeds / JwtException
~~~

Illustrative helper signing a JWT with Nimbus JOSE + JWT:

~~~java
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import java.security.KeyPair;
import java.security.interfaces.RSAPrivateKey;
import java.util.Date;
import java.time.Instant;
import java.util.List;

public final class JwtTestTokens {

    private JwtTestTokens() {}

    public static String signWithMissingTenant(
            KeyPair testKeyPair) throws Exception {

        JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer("https://login.example.test/realms/demo")
            .subject("user-123")
            .audience("orders-api")
            .issueTime(Date.from(Instant.now()))
            .expirationTime(Date.from(
                Instant.now().plusSeconds(600)))
            .claim("scope", "orders.read")
            .claim("roles", List.of("ORDER_READER"))
            // Omit tenant_id to verify required-claim rejection.
            .build();

        SignedJWT jwt = new SignedJWT(
            new JWSHeader(JWSAlgorithm.RS256),
            claims);

        jwt.sign(new RSASSASigner(
            (RSAPrivateKey) testKeyPair.getPrivate()));

        return jwt.serialize();
    }
}
~~~

In the corresponding test, build a decoder via `NimbusJwtDecoder.withPublicKey((RSAPublicKey) testKeyPair.getPublic()).build()`, **attach the exact same validators** as production, and assert `JwtException` when calling `decode` on the tenant-less JWT. To cover the full HTTP path, send the signed JWT string in `Authorization: Bearer` through MockMvc or a test server using the real decoder.

**Never** use production private keys or Access Tokens in tests. Test JWT fixtures with ephemeral RSA keys and synthetic claims are enough to cover nearly all missing/null/wrong-type scenarios deterministically.

### 12.1. Token Test Matrix

| Token / Claim | Expectation Under Example Contract |
| --- | --- |
| Valid signature, issuer/audience, and all required claims | Decodes successfully. |
| Invalid signature | Rejected before trusting any claims. |
| Missing `iss` or different issuer | Token rejected. |
| Missing `aud`, wrong resource, or wrong JSON type | Token rejected. |
| Missing `exp` when profile requires it | Rejected by required-claim policy. |
| Expired `exp` | Rejected by timestamp validation. |
| Future `nbf` | Rejected, accounting for allowed clock skew. |
| `exp` as date string or milliseconds violating schema | Must be rejected per profile/raw-type rules. |
| Missing `iat` when profile requires it | Token rejected. |
| Missing `tenant_id` | Token rejected. |
| `tenant_id: null` | Token rejected. |
| `tenant_id: ""` or whitespace only | Token rejected. |
| `tenant_id: 42` | Rejected due to wrong type. |
| `roles: []` | Rejected per example's non-empty requirement. |
| `roles: ["ORDER_READER", 1]` | Rejected due to mistyped array element. |
| `scope: ""` or missing `scope` | Rejected per example contract. |
| Valid token missing **orders.write** on POST | Authentication succeeds; authorization typically returns **403**. |
| Valid token and scope, wrong resource tenant | Resource authorization denies access. |

### 12.2. MockMvc `jwt()` Is Not a Decoder Test

Spring Security Test supports:

~~~java
mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

This is well suited for testing **authorization** given an authenticated principal. However, `jwt()` **bypasses `JwtDecoder` signature verification and validators**. Consequently, a test using `jwt()` with malformed claims that returns `200` **does not prove the decoder accepts bad JWTs**. To test rejection for missing/invalid claims, invoke a real decoder or send a real signed JWT through the filter chain.

## 13. Edge Cases Requiring Dedicated Design

### 13.1. Claim Normalization Can Hide Raw JSON Type Errors

If a converter turns a standard claim into a valid Java type, downstream validators may no longer see whether the raw JSON held a string, number, or array. If your token profile requires **strict JSON types**, enforce checks during parsing/conversion and add integration tests with mistyped raw payloads.

This is why **manually constructed `Jwt` objects** alone cannot verify that your decoder rejects every mistyped input. Always distinguish **validator tests** from **raw JWT decoding tests**.

### 13.2. Duplicate Claims in JSON

A JSON object can be crafted with duplicate keys:

~~~json
{
  "scope": "orders.read",
  "scope": "orders.admin"
}
~~~

RFC 7519 requires claim names in a JWT Claims Set to be unique; parsers must handle duplicates per specification—either rejecting them or following specified rules. Some parsers simply keep the last value, so after decoding into a map, the application **might never detect** that the original payload had duplicate keys.

For sensitive authorization claims, never merge or union duplicate values. Rely on compliant parsing behavior, test how your library actually handles duplicates, and reject non-conforming JWTs.

### 13.3. Whitespace or Unicode Characters in Strings

A tenant identifier `"tenant-42"` differs from `" tenant-42 "`. If the contract expects a strict identifier format, **validate an explicit pattern** instead of calling `trim()` on everything and treating them as equal. For names or identifiers coming from multiple systems, Unicode normalization can carry security implications and should never happen silently inside authorization checks.

### 13.4. Nested Objects and Large Arrays

If an issuer emits claims like:

~~~json
{
  "permissions": {
    "orders": ["read", "write"],
    "billing": ["read"]
  }
}
~~~

the Resource Server must verify that `permissions` is an object, which keys are allowed, whether each value is a string array, and whether sizes and permission names are bounded. Never cast blindly to `Map<String, List<String>>` and trust the contents.

Malformed tokens may also carry oversized arrays or deeply nested objects, inflating CPU, memory, and HTTP header size. Alongside schema validation, enforce request/header size limits and avoid stuffing unnecessary data into Access Tokens.

### 13.5. Multiple Issuers With Different Contracts

If a Resource Server accepts multiple issuers, `roles` might differ in shape. One issuer emits:

~~~json
{"roles": ["ORDER_READER"]}
~~~

Another emits:

~~~json
{"role": "ORDER_READER"}
~~~

Never build a loose fallback across all issuers ("read `roles`, else `role`, else allow default"). If you genuinely support multiple profiles, **select the contract based on the verified issuer/token profile** and map authorities accordingly. Never let a token from an unauthorized issuer pass merely because it contains a familiar claim name.

## 14. When to Reject the Token vs. Reject Only an Action

A helpful design question is: **does this claim belong to token acceptance or to action authorization?**

| Claim / Condition | When Missing or Invalid | Suggested Handling Layer |
| --- | --- | --- |
| Signature, issuer, audience, timestamps per profile | Credential cannot be trusted. | **Decoder / validation → 401** |
| `tenant_id` required for every API token | Token violates contract. | **Custom token validator → 401** |
| `roles` required and mistyped | Token violates contract. | **Custom token validator → 401** |
| `roles` optional per profile; missing means no roles | Token may be valid, yet lacks role permission. | **Authorization → 403** when endpoint requires it |
| Empty `scope` treated by profile as having no scopes | Token may authenticate, yet lacks permission. | **Authorization → 403** when endpoint needs scope |
| Non-empty `scope` required by example profile | Token violates mandatory schema. | **Custom token validator → 401** |
| Valid `tenant_id` not matching order's tenant | Credential valid, resource access unauthorized. | **Resource authorization → 403/404 per policy** |

There is no single answer for every custom claim, because policy follows the token contract. Once the contract is chosen, however, **every Resource Server instance must enforce it consistently** so no gaps appear across endpoints or environments.

## 15. Common Mistakes When Writing Claim Validation

| Mistake | Consequence | Proper Practice |
| --- | --- | --- |
| Checking signature only, skipping audience. | Tokens for other APIs can be misused. | Enforce an API-specific audience validator. |
| Checking `exp` only if present when profile requires `exp`. | Non-expiring tokens slip past policy. | Enforce both presence and timestamp checks. |
| Treating `null`, missing, or empty string as default privilege. | Unintended privilege escalation. | Fail-closed or map explicitly to zero permissions per contract. |
| Using `String.valueOf` to convert any type to string. | Mistyped claims are accepted unexpectedly. | Enforce explicit schema types. |
| Casting `List<String>` without checking each element. | Runtime error or wrong grants when elements are numbers/objects. | Check `List<?>` and every item. |
| Creating a custom `JwtDecoder` and forgetting default validators. | Drops issuer/timestamp validation. | Combine `JwtValidators.createDefaultWithIssuer` with custom validators. |
| Relying on `@RestControllerAdvice` for all JWT errors. | Security filter errors happen before the controller. | Configure error handling inside the security filter chain. |
| Testing only `jwt()` and claiming the decoder rejects bad tokens. | Test bypasses real JWT verification. | Test the decoder with real signed JWTs. |
| Using an ID Token instead of an Access Token. | Token type and audience confusion. | Validate profile, issuer, and API audience. |
| Logging raw JWTs/claims on validation failure. | Leaks Bearer credentials and sensitive data. | Log error codes/request IDs without echoing tokens. |

## 16. Workflow for Adding Schema Validation to a Resource Server

1. **Align on the token contract** with the Authorization Server: JWT Access Token profile, issuer, audience, scopes, and required claims.
2. **Define the schema per claim**: name, JSON type, required/optional, handling of null, empty, whitespace, value domain, versioning, and authoritative source.
3. **Configure a trusted `JwtDecoder`**: signature/JWK Set, algorithms, issuer, timestamps, audience.
4. **Add contract validators**: presence, type, and required value constraints without accidentally dropping default validators.
5. **Map authorities intentionally**: derive scopes, roles, and permissions from schema-valid claims; never trust client-asserted inputs.
6. **Enforce resource-level authorization**: verify tenant ID, record ownership, and specific action after token authentication.
7. **Test missing/null/empty/wrong-type cases** with validator unit tests and real signed JWTs through the decoder, covering both positive and negative paths.
8. **Harden error handling and operations**: return meaningful `401`/`403` responses, never log Bearer Tokens or leak sensitive claims, and monitor anomalous schema failures.

**Remember:** In a Spring Security Resource Server, "the JWT has a valid signature" only starts authentication. A secure API requires a **clear claims contract**, distinguishes **missing / null / empty / mistyped**, validates **issuer, audience, timestamps, and required claims**, and then enforces **authorization by permissions and resources**. Whenever trustworthy information is insufficient to grant access, the system must reject per policy rather than interpreting ambiguities permissively.

## References

- [RFC 7519 — JSON Web Token (JWT), Section 4: JWT Claims](https://www.rfc-editor.org/rfc/rfc7519#section-4).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725).
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — JwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtDecoder.html).
- [Spring Security — OAuth2TokenValidator API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2TokenValidator.html).
- [Spring Security — Jwt API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/Jwt.html).
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html).
