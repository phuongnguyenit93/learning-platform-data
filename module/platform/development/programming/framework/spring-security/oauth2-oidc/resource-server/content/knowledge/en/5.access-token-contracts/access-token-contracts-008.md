# Required Claims, Optional Claims, and Handling Missing or Mistyped Data

## 1. Why Does a Resource Server Need a Claims Contract?

When a client sends an OAuth 2.0 access token to a Spring Boot API, the Resource Server must not merely check "Does the JWT have a valid signature?". A token can be properly signed by the Authorization Server yet **not be intended for the current API**, **be expired**, **lack required identity data**, or carry a business claim in an unexpected data type.

For example, an Orders API expects tokens containing:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 2000000000,
  "iat": 1999999700,
  "client_id": "shop-web",
  "jti": "token-9f2a",
  "scope": "orders.read",
  "tenant_id": "tenant-42",
  "locale": "vi-VN"
}
~~~

This is JSON **illustrating the claims section**, not an actual signed JWT. In this example:

- `iss`, `aud`, `exp`, and claims governing token usage directly impact **authentication**.
- `scope` and `tenant_id` can affect **authorization**.
- `locale` is solely for display or UX; omitting it need not reject the token.
- `client_id` and `jti` may be mandatory under the **access token profile** chosen by the Authorization Server and the API.
- Each claim also has a **data type**, **valid value set**, **issuing source**, and **handling behavior when missing or invalid**.

The **access token contract** is the document agreed upon by the Authorization Server, clients, APIs, and gateway (if any) regarding token structure, semantics, and processing policy. The contract determines which claims the Resource Server requires, which are optional, when to reject a token, and when to apply safe defaults.

This lesson focuses on **Spring Security OAuth 2.0 Resource Server handling JWT access tokens**. If an access token is an **opaque token**, the API cannot read claims directly from the token string; it needs token introspection and must handle response attributes per the Authorization Server contract.

## 2. Three Rule Layers: Standard JWT, Token Profile, API Contract

The question "Is this claim mandatory?" has no single answer until you clarify which rule layer you mean.

### 2.1. RFC 7519: Registered Claims Are Not Mandatory in Every JWT

RFC 7519 defines registered claim names such as:

| Claim | Common Meaning | Standard JSON Type |
|---|---|---|
| `iss` | Token issuer | String / StringOrURI |
| `sub` | Token subject | String / StringOrURI |
| `aud` | Intended recipient | String or array of Strings |
| `exp` | Expiration time | Number as NumericDate |
| `nbf` | Not valid before this time | Number as NumericDate |
| `iat` | Issued-at time | Number as NumericDate |
| `jti` | Unique identifier for the JWT | String |

**RFC 7519 does not require every JWT to contain all of the claims above.** It defines names, types, and semantics when used. Application profiles determine which combination of claims is mandatory.

For example, a validly signed JWT can exist without `aud`. Under generic JWT syntax, that does not invalidate the JWT's existence. However, the **Orders API** can and should reject it because the API contract requires `aud` to contain `orders-api`.

### 2.2. RFC 9068: JWT Profile for OAuth 2.0 Access Tokens

When an Authorization Server and Resource Server declare compliance with the **RFC 9068 JWT access token profile**, the token's claim set has explicitly **REQUIRED** fields:

| Claim | Requirement per RFC 9068 | Role |
|---|---|---|
| `iss` | REQUIRED | Issuing Authorization Server |
| `exp` | REQUIRED | Access token expiration |
| `aud` | REQUIRED | Target Resource Server |
| `sub` | REQUIRED | Subject represented by the token |
| `client_id` | REQUIRED | OAuth 2.0 client receiving the token |
| `iat` | REQUIRED | Time the token was issued |
| `jti` | REQUIRED | Token identifier |

`auth_time`, `acr`, and `amr` may be supplied when Resource Owner authentication occurred; they do not automatically appear in every access token. Other authorization or profile claims—such as `scope`, `groups`, or `tenant_id`—depend on the specific profile and issuance policy.

The profile also specifies the JOSE header `typ` to distinguish token types (typically `at+jwt` or `application/at+jwt` per related rules). Verifying the **token type** is a separate safeguard alongside payload claims: never accept a client's OIDC **ID Token** as an access token merely because it is also a validly signed JWT.

**Note:** Not every real-world JWT access token claims full RFC 9068 compliance. Some Identity Providers use custom profiles. The API must agree on the **actual contract profile** before requiring claims; never declare RFC 9068 claims mandatory for *every JWT in every system*.

### 2.3. Resource Server Business Contract

Beyond standard requirements, the Orders API may impose its own rules:

- `aud` must contain `orders-api` exactly.
- `scope` must contain `orders.read` to call `GET /api/orders`.
- `tenant_id` must be a non-empty string if every API path falls under multi-tenancy.
- `region` must be an enum such as `VN`, `SG`, or `TH` if endpoints partition data by region.
- `locale` is an optional string for formatting messages; if missing, default to `vi-VN`.
- `preferred_username` or `email`, if present, is for display only; never replace `sub` with it as a security identifier.

Each claim is classified as **required or optional per endpoint/flow**, not only globally. A health-check endpoint needs no token; an order-reading endpoint needs subject, scope, and tenant; a machine-to-machine endpoint may use the client as subject per issuer convention.

## 3. Designing a Claims Contract Table

A useful contract table covers much more than claim names:

| Property | Questions to Align On |
|---|---|
| **Claim name** | Exact name; is it case-sensitive? |
| **Issuer/profile** | Which token type, which issuer, and which profile? |
| **Presence** | Mandatory in every access token or only for a specific flow/endpoint? |
| **JSON type** | String, Number, Boolean, Array, or Object? |
| **Domain constraints** | Non-empty, allowed value set, time unit, length limits? |
| **Validation point** | Decoder, token validator, authority converter, or business service? |
| **Missing behavior** | Reject or apply an appropriate default? |
| **Wrong type** | Reject, normalize in a controlled way, or ignore an optional claim? |
| **Authorization effect** | Which privileges does the claim govern? |
| **Logging/privacy** | Is the claim sensitive or personally identifiable? |

Example internal contract for **Orders API**:

| Claim | Category | Type / Condition | If Missing | If Wrong Type / Value |
|---|---|---|---|---|
| `iss` | Required | String matching configured issuer | 401 | 401 |
| `aud` | Required | String or String array containing `orders-api` | 401 | 401 |
| `exp` | Required | NumericDate; not expired | 401 | 401 |
| `sub` | Required in this contract | Non-empty String; meaning depends on grant | 401 | 401 |
| `client_id` | Required if RFC 9068 contract | Non-empty String | 401 | 401 |
| `iat` | Required if RFC 9068 contract | Valid NumericDate, not excessively in the future per policy | 401 | 401 |
| `jti` | Required if RFC 9068 contract | Non-empty String | 401 | 401 |
| `scope` | Conditional per endpoint | Space-separated String of scopes | 403 when required scope is missing | Reject token if schema violated; never escalate privileges |
| `tenant_id` | Required for example multi-tenant API | Non-empty String | 401 | 401 |
| `locale` | Optional, display-only | String from supported locale list | Use safe default | Ignore or use default per contract |
| `roles` | Optional, affects privileges | Array of Strings from allowed role set | No extra roles | Reject or grant 0 privileges under strict policy |

**401** means the token failed the authentication contract, so the Resource Server rejects it. **403** is typically for a validly authenticated token that lacks permission to access an endpoint or resource. Do not force every missing-claim error into 403: when a claim is a prerequisite for **the token to be considered valid**, failure should happen in the validator before creating `Authentication`.

Choices like requiring `tenant_id` are **decisions of the example system**, not mandatory standard claims for every OAuth 2.0 Resource Server.

## 4. Data Types: JSON Wire Format Differs from Decoded Java Types

### 4.1. JSON Values That Are Easily Confused

The following values differ in both type and semantics:

~~~json
{
  "exp": 2000000000,
  "exp_wrong": "2000000000",
  "aud": ["orders-api"],
  "aud_wrong": 42,
  "tenant_id": "tenant-42",
  "tenant_wrong": 42,
  "enabled": true,
  "enabled_wrong": "true",
  "roles": ["ORDER_VIEWER"],
  "roles_wrong": "ORDER_VIEWER"
}
~~~

- Standard `exp` is a **NumericDate**, a JSON Number; the string `"2000000000"` has the wrong JSON type if the contract requires standard NumericDate.
- `aud` per RFC 7519 allows **a single String or an array of Strings**; both `"orders-api"` and `["orders-api"]` can be valid depending on profile.
- `tenant_id` in the example contract is a **String**. `42` cannot automatically be coerced to `"42"` and accepted without an approved conversion rule.
- `enabled` is a Boolean, distinct from the string `"true"`.
- If `roles` is defined as an array of Strings, a single String must not automatically be treated as a single-element array.

Calling `String.valueOf(jwt.getClaim("tenant_id"))` can turn a Number, Boolean, or even `null` into a String and **hide schema bugs**. Avoid "make it work somehow" coercions on security-relevant claims.

### 4.2. NumericDate Is Not a Date String

RFC 7519 defines **NumericDate** as seconds since the Unix epoch, allowing non-integer values in some cases. It is **not milliseconds by default**, and **not an ISO-8601 String**.

~~~json
{
  "iat": 1999999700,
  "exp": 2000000000
}
~~~

The following values are not equivalent:

~~~json
{
  "exp_as_millis": 2000000000000,
  "exp_as_string": "2000000000",
  "exp_as_iso": "2033-05-18T03:33:20Z"
}
~~~

If an issuer sends timestamps in milliseconds while the decoder interprets them as seconds, tokens could be treated as valid for an extraordinarily long time. Therefore, agree on units and types, and avoid accepting fallback formats for time-governing claims.

Boundaries to consider:

- `exp` must be in the future when accepting the token, with clock skew only within allowed bounds.
- `nbf` (if present) must not be farther in the future than allowed.
- `iat` should not exceed future policy tolerances, and must exist if required by profile.
- The span `exp - iat` may be capped by policy to prevent overly long-lived tokens.
- Reject contract-invalid negative numbers, overflows, extreme values, or Number formats unsupported by the parser.

### 4.3. How Spring Security Maps Claims to Java

When using **`NimbusJwtDecoder`** with Spring Security, the claim set is commonly normalized into convenient Java types via **`MappedJwtClaimSetConverter`**. Common default mappings:

| JWT claim | Java type Spring attempts to normalize to |
|---|---|
| `aud` | `Collection<String>` |
| `exp` | `Instant` |
| `iat` | `Instant` |
| `nbf` | `Instant` |
| `iss` | `String` |
| `sub` | `String` |
| `jti` | `String` |

Thus, when calling:

~~~java
Jwt jwt = /* authenticated principal */;
String subject = jwt.getSubject();
Collection<String> audiences = jwt.getAudience();
Instant expiresAt = jwt.getExpiresAt();
~~~

the program is reading **values already normalized by the decoder**, not necessarily the raw JSON types off the wire.

This makes JWT handling convenient, with an important implication: **type checks in `OAuth2TokenValidator<Jwt>` only observe claims after conversion**. If the contract demands ultra-strict wire JSON type checking, ensure the converter/parser does not silently accept wrong types via defaults; you may need an **explicitly configured claim-set converter**, additional validation, or profile enforcement at the issuer.

Never mask issuer profile bugs by coercing arbitrary String, Number, or Array inputs into a desired type. Conversion is appropriate only when every accepted input form is explicitly permitted by the **formal contract**.

## 5. Differences Among Missing, Null, Blank, and Wrong Type

Consider four payloads:

**Missing claim:**

~~~json
{"sub":"user-123"}
~~~

**Present but null:**

~~~json
{"sub":"user-123","tenant_id":null}
~~~

**Present as empty String:**

~~~json
{"sub":"user-123","tenant_id":""}
~~~

**Present with wrong type:**

~~~json
{"sub":"user-123","tenant_id":["tenant-42"]}
~~~

If the contract requires `tenant_id` to be a non-empty String, **all four cases are invalid**. Never default:

- Missing → `"public"` tenant, which easily lets tokens cross data boundaries.
- `null` → String `"null"`.
- Empty string → default tenant.
- Single-element array → String of the first element.

For an optional display-only claim like `locale`, you can design:

~~~text
missing or malformed locale -> use "vi-VN" for display
~~~

However, for claims determining **tenant, roles, scopes, assurance level, or client identity**, missing or mistyped values must be treated as **contract or privilege validation failures**, preventing a lenient parser from granting unintended access.

### 5.1. Should There Be Default Privileges?

Follow these principles:

- **Never grant new privileges via fallback.**
- For optional privilege-carrying claims, absence may mean **zero additional privileges**.
- Wrong types on privilege claims can be **rejected** during authentication or treated as **no privilege** depending on profile; rejecting usually surfaces broken issuers faster and avoids inconsistent interpretations.
- For claims completely unrelated to security (UI language, theme), policy-defined fallbacks are fine.
- For mandatory resource-identifying `sub` or `tenant_id`, never fall back to less trustworthy claims like email or preferred username.

### 5.2. Claims Containing Lists

Example contract:

~~~json
{
  "roles": ["ORDER_VIEWER", "ORDER_EDITOR"]
}
~~~

If `roles` is required to be a String array, validate every element:

- Do not accept `roles: "ORDER_EDITOR"` merely because the list has one role.
- Do not accept `roles: [true, "ORDER_EDITOR"]`.
- Do not accept `roles: [""]`.
- Maintain an allowed role set and a list-size limit to avoid unfamiliar or oversized strings.
- If an empty list is permitted by contract, explicitly document it as **no roles**.

Avoid silently merging roles from non-equivalent sources—for instance, `groups` as organizational groups while `roles` are internal permissions.

## 6. Resource Server Configuration Foundation

### 6.1. Signature, Issuer, Expiration, and Audience

With Spring Boot, add dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Example `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          audiences: orders-api
~~~

The issuer value here is only an example and must match the `iss` claim actually issued by your Authorization Server.

`issuer-uri` configures the issuer trusted by the decoder and enables metadata/JWKS discovery per provider. `audiences` is a Spring Boot property binding tokens to the API's audience in versions supporting this setting.

By default, Spring Security JWT Resource Server verifies signatures with trusted keys and runs baseline validators for `exp`, `nbf`, and `iss`. **Do not assume every RFC 9068 claim, custom claim, and type rule is automatically validated merely from `issuer-uri`.**

`audiences` handles audience verification; if the contract requires additional rules, build a custom validator.

### 6.2. SecurityFilterChain Protecting Endpoints by Scope

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
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

In the default configuration, Spring Security maps scopes from the access token into authorities prefixed with `SCOPE_`. Thus `scope: "orders.read"` can grant `SCOPE_orders.read` to the request.

**Scope does not replace data-ownership checks.** A token with `orders.read` still must not view orders belonging to another tenant. Enforce checks by `sub`/`tenant_id` and business rules.

## 7. Writing Validators for Required and Optional Claims

### 7.1. Composing Validators

For requirements beyond auto-configuration, an application can build a `JwtDecoder` and attach custom `OAuth2TokenValidator<Jwt>` instances.

Example **Orders API** contract:

- `iss` matches the configured issuer.
- `aud` must contain `orders-api`.
- `exp` and `nbf` are checked by default validators.
- `tenant_id` is required as a non-blank String.
- `client_id` is required as a non-blank String.
- `jti` is required as a non-blank String.
- `iat` is required (as `Instant` after conversion).
- `locale` is optional; if present, must be a String in one of the two supported locales. Because this is a display-only claim, the example ignores unsupported values in the controller rather than using it for authorization.

Java code example:

~~~java
package com.example.orders.security;

import java.time.Instant;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class AccessTokenContractConfig {

    private static final String ISSUER =
        "https://id.example.test/realms/shop";

    private static final String JWKS_URI =
        "https://id.example.test/realms/shop/protocol/openid-connect/certs";

    private static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS_URI)
            .build();

        OAuth2TokenValidator<Jwt> defaults =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> contract =
            AccessTokenContractConfig::validateContract;

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(defaults, contract)
        );
        return decoder;
    }

    private static OAuth2TokenValidatorResult validateContract(Jwt jwt) {
        if (!jwt.getAudience().contains(AUDIENCE)) {
            return invalid("Token has no audience for orders-api");
        }

        if (!nonBlankString(jwt.getClaim("sub"))) {
            return invalid("Missing or invalid subject");
        }

        if (!nonBlankString(jwt.getClaim("client_id"))) {
            return invalid("Missing or invalid client_id");
        }

        if (!nonBlankString(jwt.getClaim("jti"))) {
            return invalid("Missing or invalid jti");
        }

        if (!nonBlankString(jwt.getClaim("tenant_id"))) {
            return invalid("Missing or invalid tenant_id");
        }

        Instant issuedAt = jwt.getIssuedAt();
        if (issuedAt == null) {
            return invalid("Missing issued-at timestamp");
        }

        // Do not validate scope directly here: SecurityFilterChain checks
        // scope per endpoint; custom claim schemas may still need a validator.
        return OAuth2TokenValidatorResult.success();
    }

    private static boolean nonBlankString(Object claim) {
        return claim instanceof String value && !value.isBlank();
    }

    private static OAuth2TokenValidatorResult invalid(String reason) {
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", reason, null)
        );
    }
}
~~~

In this example, `JWKS_URI` uses a structure common to some Identity Providers; always obtain the real `jwks_uri` from trusted metadata. With a custom decoder bean, **calling `JwtValidators.createDefaultWithIssuer(ISSUER)` preserves baseline validators** before appending your contract checks.

The code above is a **validator operating on `Jwt` after conversion**. It illustrates rejecting missing/mistyped claims visible on the Java model; it does not by itself prove that the original *raw* JSON type of every registered claim strictly matched RFC 9068. To catch silent type coercions, also govern the claim conversion layer, as discussed later.

**Regarding `sub` and `jti`:** `jwt.getClaim(...)` returns the normalized value if the decoder uses a converter. `nonBlankString` checks the Java type and rejects empty Strings. Since `tenant_id` is a custom claim, its type generally stays as parsed from JSON unless the application configures a custom converter.

### 7.2. Checking Optional Claims Explicitly

Suppose `locale` is used solely to format display names/units:

~~~java
package com.example.orders.service;

import org.springframework.security.oauth2.jwt.Jwt;

public final class LocalePolicy {

    public static String localeForDisplay(Jwt jwt) {
        Object claim = jwt.getClaims().get("locale");

        if (!(claim instanceof String locale)) {
            return "vi-VN";
        }

        return switch (locale) {
            case "vi-VN", "en-US" -> locale;
            default -> "vi-VN";
        };
    }
}
~~~

If `locale` is absent, null, not a String, or outside the allowlist, the application uses a safe default for **display**. Never apply this kind of fallback to tenant, account ownership, audience, or roles.

If `locale` carries **security or compliance** significance (such as restricting data visibility by country), it is no longer a simple optional UI claim and must undergo stricter validation.

### 7.3. Optional Claims That Carry Privileges: `roles`

Suppose the profile defines `roles` as a String array; absence means zero privileges from roles.

A helper can parse it safely:

~~~java
package com.example.orders.security;

import java.util.Collection;
import java.util.Set;

import org.springframework.security.oauth2.jwt.Jwt;

public final class RoleClaims {

    private static final Set<String> ALLOWED =
        Set.of("ORDER_VIEWER", "ORDER_EDITOR", "ORDER_ADMIN");

    public static Set<String> readRoles(Jwt jwt) {
        Object raw = jwt.getClaims().get("roles");

        if (raw == null) {
            return Set.of(); // Missing claim -> grant no extra roles
        }

        if (!(raw instanceof Collection<?> values)) {
            throw new IllegalArgumentException(
                "Claim roles must be an array of strings");
        }

        for (Object value : values) {
            if (!(value instanceof String role)
                    || !ALLOWED.contains(role)) {
                throw new IllegalArgumentException(
                    "Invalid role claim value");
            }
        }

        return values.stream()
            .map(String.class::cast)
            .collect(java.util.stream.Collectors.toUnmodifiableSet());
    }
}
~~~

The helper above only illustrates **data validation and granting no privileges when a claim is missing**. If `roles` is a security claim under the contract, place schema validation in the **decoder/validator before creating `Authentication`**, then map to authorities per policy. Do not wait for a controller to parse roles and throw `IllegalArgumentException` into a 500 error.

Likewise, because default Spring Security reads only `scope`/`scp` to build authorities, a custom `roles` claim **does not automatically become access privileges**; configure `JwtAuthenticationConverter` or a matching authorization policy. Any accepted role must come from a trusted issuer and belong to the set recognized by the API.

## 8. Avoiding Silent Coercions in the Claim Set Converter

### 8.1. Why Validators Alone Might Not Be Enough

Suppose a buggy Authorization Server emits:

~~~json
{
  "sub": 12345,
  "exp": "2000000000",
  "aud": "orders-api"
}
~~~

In some parse/conversion paths, libraries may normalize claims into convenient Java types or reject them depending on shape and version. If `sub: 12345` is coerced into `"12345"` before `OAuth2TokenValidator<Jwt>` runs, a validator checking `sub instanceof String` **can no longer distinguish** the original JSON type.

Thus there are two distinct requirement layers:

- **Semantic validation**: after decoding, `iss` matches, `aud` contains the audience, `tenant_id` is non-empty, `exp` has not passed.
- **Strict wire-schema validation**: the incoming JSON payload actually has `sub` as a String, `exp` as a Number, and `roles` as a String Array; do not let a converter "repair" wrong types.

If the contract mandates strict wire schema, enforce these checks where the original trusted data is available after **signature verification**, or use a custom claim-set conversion that preserves contract-relevant type information; never bypass verification to read and trust the payload.

### 8.2. Using `MappedJwtClaimSetConverter` for Controlled Normalization

Spring Security lets you configure:

~~~java
import java.util.Map;

import org.springframework.security.oauth2.jwt.MappedJwtClaimSetConverter;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

NimbusJwtDecoder decoder =
    NimbusJwtDecoder.withJwkSetUri(jwksUri).build();

decoder.setClaimSetConverter(
    MappedJwtClaimSetConverter.withDefaults(
        Map.of("tenant_id", value -> {
            if (value == null) {
                return null;
            }
            if (!(value instanceof String tenant)) {
                throw new IllegalArgumentException(
                    "tenant_id must be a JSON string");
            }
            return tenant;
        })
    )
);
~~~

This snippet illustrates configuring **a single custom claim**; `jwksUri` must be a real value from the application. The converter ensures `tenant_id`, if supplied, is strictly a String, and the downstream validator rejects null or blank values. Calling `withDefaults(...)` keeps standard conversion rules for other claims.

**Be careful when customizing registered claims**: changing conversion of `exp`/`iat`/`aud` can directly affect Spring's validators. If you need to catch schema errors on raw JSON, design the check point to match your Spring/Nimbus version without disabling expiration, issuer, audience, or signature validation.

In production, if an issuer consistently sends the wrong format, prioritize **fixing the issuer side** and aligning the contract rather than building fallback chains that silently accept multiple types.

## 9. Validation Rules for Common Claims

### 9.1. `iss`: Trusted Issuer

`iss` must match **exactly** the issuer trusted by the Resource Server. Never compare with `contains` or match domains loosely.

Example:

~~~text
Configured issuer: https://id.example.test/realms/shop

Accepted:
  https://id.example.test/realms/shop

Rejected:
  https://id.example.test/realms/another
  http://id.example.test/realms/shop
~~~

The application must obtain metadata and JWKS from the trusted issuer, never letting the token choose its own verification key source.

### 9.2. `aud`: API-Matching Audience

`aud` can be a single String or a String array:

~~~json
{"aud": "orders-api"}
~~~

~~~json
{"aud": ["orders-api", "reports-api"]}
~~~

If the contract permits multiple audiences, checking membership of `orders-api` is valid. If security policy requires **a single exclusive audience**, that is an extra constraint to declare and verify explicitly. Never inspect only the first element when `aud` is an array.

A JWT with `aud: "shop-web"` is an ID Token/client audience in many OIDC flows and is usually **not intended for the Orders API**, even if its signature is valid.

### 9.3. `exp` and `nbf`: Timestamps

- `exp` is the expiration boundary.
- `nbf` constrains when the token begins to be valid.
- Bounded clock skew may be applied to absorb minor clock drift.
- An expired or not-yet-valid token must never be treated as valid by reading raw claims in a controller.
- `iat` records when the token was issued; add a dedicated validator if your profile forbids future issuance beyond tolerance or enforces a maximum token age.

Increasing clock skew excessively to "fix clock errors" widens the window in which unwanted tokens are accepted. Keep system clocks accurately synchronized.

### 9.4. `sub`: Token Subject

An access token issued under the Authorization Code Flow typically has `sub` representing a user. In the **Client Credentials Flow**, per RFC 9068, `sub` may represent the **client application**.

Therefore:

~~~java
String subject = jwt.getSubject();
~~~

does not prove a human user logged in. Never assume `sub` is always a user ID across every flow. The contract should specify:

- Which tokens represent users and which represent services/clients.
- Required grant type and actor info (if any).
- Which endpoints may be called by machine principals.
- The data scope that a subject is permitted to access.
- How `iss` + `sub` combine to scope identity properly.

### 9.5. `scope` and `roles`: Authorization

In common profiles, `scope` is represented as a space-delimited string of scopes:

~~~json
{"scope": "orders.read orders.write"}
~~~

Some providers use `scp` as a String Array; this is an **issuer-specific variant** to align on. Never equate `roles`, `groups`, or `permissions` claims with standard scopes without explicit converters and policies.

Distinguish:

1. **Is the claim schema-valid?** E.g., `scope` is a properly formatted String.
2. **Does the token hold the endpoint's required privilege?** E.g., contains `orders.read`.
3. **Does the subject have permission on the specific record?** E.g., viewing only orders in the same tenant.

Missing the `scope` claim might not invalidate the token if the profile does not require it to exist, yet an endpoint requiring `orders.read` must **deny access**.

### 9.6. Custom Claims: `tenant_id`, `region`, and `customer_id`

For custom claims:

- Define a **namespace/claim name** to avoid colliding semantically with standard claims.
- Clarify String vs. Number, especially for identifiers with leading zeros like `"00123"`.
- Never use `Integer.parseInt` on String identifiers unless the contract defines Number type.
- Define multi-tenancy and ownership; never take `tenant_id` from HTTP inputs to override the verified claim.
- When business rules require tenant identity, reject missing/invalid tokens at the appropriate validation point.

## 10. When 401, When 403?

A consistent policy helps clients fix errors without leaking sensitive details.

| Case | Typical Result | Reason |
|---|---|---|
| No Bearer token sent to a protected endpoint | **401** | Unauthenticated |
| Token with invalid signature/issuer/expiration | **401** | Invalid token |
| Token missing required `aud` or wrong audience | **401** | Token not intended for this API |
| Token missing required `tenant_id` in decoder contract | **401** | Access token contract violation |
| Token has `tenant_id` as Number when String is required | **401** | Security schema violation |
| Valid token missing `orders.read` | **403** | Authenticated but lacks endpoint privilege |
| Valid token with `orders.read` requesting another tenant's order | **403** or **404** per resource-hiding policy | Not permitted to access business object |
| Valid token, missing `locale` | **Do not reject** | Use display default |
| Valid token, `roles` absent and role privilege is optional | No extra roles granted | Fail closed in authorization |

These statuses reflect typical security configuration behavior; gateways, exception handlers, and API requirements may adjust response details. Never log raw tokens or full claims on errors; log only necessary metadata (such as error codes and correlation IDs).

### Testing Example with curl

~~~bash
curl -i \
  -H "Authorization: Bearer <VALID_ACCESS_TOKEN>" \
  https://api.example.test/api/orders
~~~

Only if the contract's required claims are present and the token passes validation does the controller handle the request. Never place real JWTs into public examples, source repositories, or third-party token-decoding websites.

On error, a client may receive a response with:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Not every error response includes a detailed JSON body. Per RFC 6750, the `WWW-Authenticate` header describes Bearer-layer errors; never put plaintext tokens or sensitive claims into client-facing messages.

## 11. Designing a Test Case Matrix for the Contract

A typical test matrix:

| Case | Input | Expected Result |
|---|---|---|
| Valid | Right `iss`, `aud`, `exp`, `sub`, `tenant_id`; has `orders.read` | May return 200 |
| Missing `aud` | Validly signed JWT without audience | 401 |
| Numeric `aud` | `"aud": 123` | Rejected per schema |
| `aud` array excluding Orders API | `["billing-api"]` | 401 |
| String `exp` | `"exp": "2000000000"` | Rejected if strict NumericDate schema |
| Expired `exp` | NumericDate in the past | 401 |
| Missing `tenant_id` | Claim absent | 401 if required |
| Null `tenant_id` | `"tenant_id": null` | 401 |
| Empty `tenant_id` | `"tenant_id": ""` | 401 |
| Numeric `tenant_id` | `"tenant_id": 42` | 401 |
| Missing `locale` | No locale present | Display fallback |
| Mistyped `locale` | `"locale": 10` | Never used for authorization decisions |
| String `roles` | `"roles": "ORDER_ADMIN"` | Rejected per defined role schema |
| `scope` missing `orders.read` | Valid token, insufficient privilege | 403 |
| ID Token sent instead of access token | `aud`/`typ` does not match API profile | Rejected |

For realistic testing, generate **test tokens signed with an issuer test key** so you can vary payloads deliberately rather than editing a production JWT payload: editing a payload invalidates the signature, making it impossible to distinguish schema errors from signature errors.

For raw JSON type test cases, ensure your tests exercise the decoder's actual parsing and claim-conversion pipeline so they verify what the application contract requires. Never test only controllers using pre-built `Jwt.withTokenValue(...)` objects and conclude that the decoder rejects all mistyped inputs.

## 12. Operational Security Constraints

### 12.1. Never Infer Privileges from Untrusted Claims

Claims are trustworthy only after the Resource Server has verified a valid token against the right issuer/keys/profile. Never Base64URL-decode the payload and trust `roles` or `tenant_id` prior to signature and claims validation.

Even after authentication, claim data remains an **issuer statement**, not the final authorization decision for every resource. The API may still need to consult internal data policies and record ownership.

### 12.2. Never Add Defaults That Can Widen Access

Defaults for UI display can be appropriate; defaults for principal, scope, or tenant usually are not. Beware of code like:

~~~java
String tenantId = jwt.hasClaim("tenant_id")
    ? jwt.getClaimAsString("tenant_id")
    : "global";  // Dangerous if "global" grants broader access
~~~

A safer pattern, when `tenant_id` is mandatory, is rejecting the token inside the validator before the request reaches business logic.

### 12.3. Bound Data and Avoid Claim Abuse

JWTs are signed, not automatically encrypted. Anyone holding a token can read JWS claims via Base64URL-decoding. Do not embed unnecessary secrets. For custom claims:

- Bound String lengths and array element counts.
- Do not trust arbitrary nested JSON objects that might exceed limits.
- Define versioning when schemas evolve.
- Ensure identifier stability; email is usually unsuitable as a principal ID.
- Define a policy for unrecognized claims; never turn unknown claims into privileges.
- Avoid bugs from comma/space splitting, empty strings, and inconsistent role formatting.

### 12.4. Evolving the Contract Between Authorization Server and API

When introducing a new mandatory claim such as `tenant_id`:

1. Confirm the issuer will emit the right type/value across all supported grant types.
2. Check whether previously issued tokens are still in circulation.
3. Roll out versioning, migration, or a compatibility window aligned with risk.
4. Once the contract takes effect, the new validator rejects tokens failing the policy.
5. Monitor 401/403 rates by error code/correlation ID; never log real tokens.

With multiple issuers or token profiles, claim policies may need to vary by **issuer and token type**. Never loosen a single shared contract just so every token passes validation.

## 13. Comprehensive Reasoning Example

Suppose an endpoint:

~~~http
GET /api/orders/42
Authorization: Bearer <JWT>
~~~

Hypothetical contract:

- Access token has issuer `https://id.example.test/realms/shop`.
- Audience must contain `orders-api`.
- Token is unexpired with a valid signature.
- Token has a non-empty String `sub`.
- Token must have a non-empty String `tenant_id`.
- The GET endpoint requires `orders.read`.
- Order 42 belongs to the token's tenant.

Token A:

~~~json
{
  "iss":"https://id.example.test/realms/shop",
  "sub":"user-123",
  "aud":["orders-api"],
  "exp":2000000000,
  "scope":"orders.read",
  "tenant_id":"tenant-42"
}
~~~

If these claims belong to a validly signed, unexpired JWS and **the API contract does not mandate the full RFC 9068 profile**, Token A can pass token validation (still subject to ownership checks afterward). If the API declares **RFC 9068 compliance** and mandates `client_id`, `iat`, and `jti`, Token A lacks them and must be rejected. **The outcome depends on the contract profile.**

Token B:

~~~json
{
  "iss":"https://id.example.test/realms/shop",
  "sub":"user-123",
  "aud":["orders-api"],
  "exp":2000000000,
  "scope":"orders.read",
  "tenant_id":42
}
~~~

Token B violates the String schema for `tenant_id`. It cannot be accepted merely because the signature is valid; under a mandatory policy, it should return 401.

Token C:

~~~json
{
  "iss":"https://id.example.test/realms/shop",
  "sub":"user-123",
  "aud":["orders-api"],
  "exp":2000000000,
  "scope":"profile",
  "tenant_id":"tenant-42"
}
~~~

If the claims satisfy the authentication contract and the token is unexpired, Token C may **authenticate**, yet it lacks `orders.read`, so it cannot access the endpoint: typically 403.

Token D:

~~~json
{
  "iss":"https://id.example.test/realms/shop",
  "sub":"user-123",
  "aud":["orders-api"],
  "exp":2000000000,
  "scope":"orders.read",
  "tenant_id":"tenant-42",
  "locale":null
}
~~~

If `locale` is purely an optional UI claim, the application can default to `vi-VN`; this does not escalate the token's privileges.

All payloads above serve only to illustrate differences; **they are not signed JWTs** and must never be used directly as real credentials.

## 14. Key Takeaways

- **There is no universal mandatory claim list for every JWT** in RFC 7519. Choose your **JWT access token profile** and **API contract** explicitly before enforcing required fields.
- **RFC 9068** defines `iss`, `exp`, `aud`, `sub`, `client_id`, `iat`, and `jti` as mandatory claims for JWT access tokens under that profile.
- **JWT claims have both data types and semantics**. `aud` can be a String or String array; `exp`/`iat` are NumericDate; custom `tenant_id` and `roles` must follow an agreed schema.
- **Missing, null, empty string, and wrong type are not equivalent to valid values**. Never perform loose type coercions on security claims.
- Spring Security normalizes claim types; when strict **wire JSON types** are required, govern claim conversion/parsing in addition to validating the converted `Jwt`.
- Optional display claims can use safe defaults; claims determining principal, scope, tenant, and privileges must **fail closed**.
- Token authentication (`iss`, `aud`, signature, timestamps, contract) and endpoint/object authorization (`scope`, ownership) are two complementary layers.
- The contract document should specify exact behavior for missing/mistyped tokens so the Authorization Server, Resource Server, and clients behave consistently.

### References

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [Spring Security — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security API — MappedJwtClaimSetConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/MappedJwtClaimSetConverter.html)
- [Spring Security API — Jwt](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/Jwt.html)
