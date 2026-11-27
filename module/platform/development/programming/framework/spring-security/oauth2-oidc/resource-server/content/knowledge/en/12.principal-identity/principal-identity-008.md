# MappedJwtClaimSetConverter and Converting Types or Adjusting Claims

In a **Spring Security OAuth 2.0 / OIDC Resource Server** running on the Servlet stack, a JWT access token typically contains a set of claims in JSON. However, the JSON representation and the Java data types expected by the application do not always match directly. For example:

- `exp` in a JWT is a *NumericDate* (seconds since the Unix epoch), while Java code typically expects an `Instant`.
- `aud` can be a single string or a JSON array, while Spring Security exposes `Jwt.getAudience()` as a list of audiences.
- The Authorization Server may emit a custom claim such as `tenant_id`, `preferred_username`, `groups`, or `legacy_user_id` with a type or format that needs normalization before use.
- The application must distinguish the **principal's primary identifier** from display names, login names, or permissions mapped from the token.

Spring Security provides **`MappedJwtClaimSetConverter`** to customize how JWT claims map into the claims map of a `Jwt` object. It operates in the **claim-set conversion layer** of `NimbusJwtDecoder`—it is not a mechanism to bypass digital signatures, not a validator deciding token acceptance, and not the converter that creates `GrantedAuthority` instances.

This lesson explains how to understand the converter's place in the pipeline, use default conversions, customize one or more claims, avoid losing essential default conversions, and pick the right tool when the actual goal is changing the principal name or mapping scopes/roles.

> **Key point:** Claim conversion helps the application understand **data types and structure**; validators check **whether the token is accepted**; the authentication converter builds **principal and authorities**; authorization decides **access permissions**. These are four distinct responsibilities.

## 1. Placing Claim Conversion in the Servlet Chain

When a client calls the API with a JWT access token:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
Accept: application/json
```

Spring Security Resource Server typically processes it through these components:

```mermaid
flowchart TD
    A["Authorization: Bearer JWT"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["JwtAuthenticationProvider"]
    C --> D["NimbusJwtDecoder"]
    D --> E{"Valid JWS, signature, key, and algorithm?"}
    E -- "No" --> F["Authentication failed"]
    E -- "Yes" --> G["Claim-set conversion: defaults + custom"]
    G --> H["Jwt with headers and converted claims"]
    H --> I{"JwtValidators and custom validators pass?"}
    I -- "No" --> F
    I -- "Yes" --> J["JwtAuthenticationConverter"]
    J --> K["JwtAuthenticationToken and GrantedAuthority"]
    K --> L["SecurityContext"]
    L --> M{"Authorized for endpoint and data?"}
    M -- "No" --> N["Typically 403"]
    M -- "Yes" --> O["Controller / service"]
    F --> P["Typically 401 or appropriate auth failure handler"]
```

The diagram depicts the logical stages in a typical JWT Resource Server implementation. Internal details of parsing, verification, and claim normalization depend on the decoder/version, yet the invariant rule is **never use unverified claims to grant access**.

| Component | Input | Output / Purpose |
|---|---|---|
| `NimbusJwtDecoder` | JWT string from the request | Verifies signature, converts claims, and runs validators; returns `Jwt` or error |
| `MappedJwtClaimSetConverter` | `Map<String, Object>` of raw claim values | `Map<String, Object>` with normalized values/types per contract |
| `OAuth2TokenValidator<Jwt>` | `Jwt` object | Decision to accept or reject token based on issuer, timestamps, audience, and other claims |
| `JwtAuthenticationConverter` | Verified `Jwt` | `JwtAuthenticationToken` with principal name and authorities |
| `JwtGrantedAuthoritiesConverter` | Permission-related claims | List of `GrantedAuthority`, e.g., `SCOPE_orders.read` |
| `AuthorizationFilter` and method security | Verified `Authentication` and request context | Decides whether the API/action/resource is allowed |

If you want to normalize `tenant_id` from the issuer's format into a format the API understands, that is usually **claim-set conversion**. If you want to require `tenant_id` to be in an allowlist, that is **claim validation**. If you want `Authentication.getName()` to come from another claim, that is **principal mapping**, not modifying claims. If you want scopes turned into authorities, that is **authority mapping**.

## 2. How Do JSON Claims and Java Claims Differ?

A JWT has a JWS compact structure:

```text
base64url(header).base64url(payload).base64url(signature)
```

Suppose an illustrative JWT payload is:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "client_id": "web-portal",
  "preferred_username": "  phuong.nguyen  ",
  "tenant_id": 42,
  "scope": "orders.read orders.write",
  "iat": 1794715200,
  "exp": 1794718800
}
```

This is illustrative JSON, **not a signed token**. After the JWT is parsed and conversions are applied, the application can observe values such as:

| Claim | JSON Representation | How Java Applications Typically Read It |
|---|---|---|
| `iss` | Issuer URI string | `jwt.getIssuer()` or issuer string per contract |
| `sub` | String | `jwt.getSubject()` |
| `aud` | String or array of strings | `jwt.getAudience()` returning a list of audiences |
| `iat` | NumericDate | `jwt.getIssuedAt()` returning `Instant` when present |
| `exp` | NumericDate | `jwt.getExpiresAt()` returning `Instant` when present |
| `nbf` | NumericDate if present | `jwt.getNotBefore()` returning `Instant` when present |
| `tenant_id` | String or number per issuer contract | String or intentional domain type, never guessed |
| `scope` | Space-delimited string, or structure per profile | Input for the authority converter |
| `preferred_username` | String | User attribute / display username if permitted |
| `groups` | Array of group names per issuer | List, usually requiring explicit mapping to grant authorities |

Spring Security and Nimbus provide default claim converters for registered JWT claims. Classic examples are **timestamps to `Instant` and audience to a list**, giving `Jwt` convenient typed accessors.

Even so, **never assume custom claims share the exact types of standard claims**. A JSON parser may produce `Integer`, `Long`, various `Number` subtypes, or `List<?>` depending on the data and library. Know the issuer's claim contract and the types returned by your decoder.

### 2.1. Conversion Does Not Prove a Claim Is Valid

You can convert a JSON number to a Java string, such as `42` → `"42"`. However, that conversion **does not prove** tenant 42 exists, that the user has access to tenant 42, or that the token targets the receiving API.

Similarly, converting `exp` into an `Instant` only lets code **read the timestamp**; checking whether the token has expired remains the job of a timestamp validator.

### 2.2. Conversion Does Not Alter the JWS Signature

The JWS signature protects the **byte representation of the signed header and payload**. The claim-set converter operates on the parsed claim representation **after reading the JWT**, to construct a `Jwt` object structured nicely for code. It does not rewrite and re-sign the JWT.

Therefore, after conversion a claim may look different from its original JSON form without implying the Authorization Server signed the **converted Java form**. It is an internal representation accepted by the decoder. Never use a converter to legitimize a security claim that violates the issuer contract.

## 3. What Does `MappedJwtClaimSetConverter` Do?

Spring Security provides the class:

```java
org.springframework.security.oauth2.jwt.MappedJwtClaimSetConverter
```

It is a converter from one claim map to another claim map:

```java
Converter<Map<String, Object>, Map<String, Object>>
```

When building a `MappedJwtClaimSetConverter`, you can supply dedicated converters **per claim name**. Usually the safest and most convenient approach is:

```java
MappedJwtClaimSetConverter.withDefaults(customConverters)
```

This method starts from Spring Security's **default claim conversions** and adds or overrides the converters specified in `customConverters`.

For example:

```text
Claims returned by parser:
  "exp"                  -> number
  "aud"                  -> list/string
  "tenant_id"            -> 42
  "preferred_username"   -> "  phuong.nguyen  "

MappedJwtClaimSetConverter.withDefaults(...):
  "exp"                  -> Instant, per default converter
  "aud"                  -> audience list, per default converter
  "tenant_id"            -> "42", per custom converter
  "preferred_username"   -> "  phuong.nguyen  " or per custom rule

Result:
  Map<String,Object> used to build the Jwt object
```

Customization does not need to replace every field. **Preserve default claim converters**, especially for claims relied upon by standard validators such as `exp`, `nbf`, and issuer.

### 3.1. Why Is `withDefaults(...)` Important?

If a developer writes a converter that replaces the whole map carelessly, code can lose the standard types of claims used across the API such as:

```java
jwt.getExpiresAt()
jwt.getIssuedAt()
jwt.getAudience()
jwt.getIssuer()
```

This can cause failures when validators or downstream code expect normalized claim types.

Recommendation: **override only the exact claims that genuinely need changing**, starting from the defaults. Never convert all claims to Strings via `Object.toString()`; that destroys lists, timestamps, and critical types.

## 4. Converting a Custom Claim with `withDefaults(...)`

Suppose an issuer has a legacy contract emitting:

```json
"tenant_id": 42
```

while the API uses tenant codes as strings. A controlled conversion:

```java
Converter<Object, Object> tenantIdConverter = value -> {
    if (value instanceof String text) {
        return text;
    }

    if (value instanceof Number number) {
        return number.toString();
    }

    // Preserve unexpected types so the validator rejects them explicitly.
    return value;
};

Map<String, Converter<Object, ?>> overrides = new HashMap<>();
overrides.put("tenant_id", tenantIdConverter);

Converter<Map<String, Object>, Map<String, Object>> claimConverter =
    MappedJwtClaimSetConverter.withDefaults(overrides);
```

Imports:

```java
import java.util.HashMap;
import java.util.Map;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.oauth2.jwt.MappedJwtClaimSetConverter;
```

Here:

1. If `tenant_id` is a string, keep it as is.
2. If it is a Java number, convert it to a string via `number.toString()`.
3. If it is any other type, leave it for the validator to catch rather than silently fabricating a random value.
4. `withDefaults(...)` keeps standard conversion rules for registered claims.

**Important warning about numeric identifiers:** If a tenant ID is actually **an identifier** rather than a numeric quantity, the AS should emit it as a **string from the start**. JSON numbers can drop leading zeros, lose precision for large numbers, or introduce formatting differences (`42`, `42.0`). Converting `42` to `"42"` is only valid when **both forms are confirmed by the issuer contract to represent the same identifier**.

### 4.1. A Simpler Option: String Normalization

If the issuer sends an auxiliary display claim:

```json
"preferred_username": "  phuong.nguyen  "
```

you can trim leading and trailing whitespace:

```java
Converter<Object, Object> usernameConverter = value -> {
    if (value instanceof String text) {
        return text.strip();
    }
    return value;
};

Map<String, Converter<Object, ?>> overrides = new HashMap<>();
overrides.put("preferred_username", usernameConverter);

Converter<Map<String, Object>, Map<String, Object>> converter =
    MappedJwtClaimSetConverter.withDefaults(overrides);
```

This illustrates simple data normalization. However, **display names must not replace the stable `sub` identifier** for account access, ownership, or auditing merely because they look nicer.

### 4.2. Conversions Must Align with How Validators Read Claims

If the converter turns `tenant_id` into a String, the validator should check for a **String**, rather than accepting both Numbers and Strings inconsistently.

Example:

```java
OAuth2TokenValidator<Jwt> tenantValidator = jwt -> {
    Object raw = jwt.getClaim("tenant_id");

    if (raw instanceof String tenant && "42".equals(tenant)) {
        return OAuth2TokenValidatorResult.success();
    }

    return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
            "invalid_token",
            "Unexpected tenant_id claim",
            null
        )
    );
};
```

Converters **transform types**; validators **decide acceptance**. Without clear conversion rules, never accept arbitrary values after calling `String.valueOf(...)`.

## 5. Attaching a Claim Converter to `NimbusJwtDecoder`

`NimbusJwtDecoder` lets you set a claim-set converter:

```java
decoder.setClaimSetConverter(claimConverter);
```

Complete example where the Resource Server trusts issuer `shop` and requires audience `orders-api`:

```java
@Configuration
public class JwtDecoderConfiguration {

    private static final String ISSUER =
        "https://login.example.test/realms/shop";

    private static final String AUDIENCE =
        "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(ISSUER).build();

        Converter<Object, Object> tenantToString = value -> {
            if (value instanceof String text) {
                return text;
            }
            if (value instanceof Number number) {
                return number.toString();
            }
            return value;
        };

        Map<String, Converter<Object, ?>> overrides = new HashMap<>();
        overrides.put("tenant_id", tenantToString);

        decoder.setClaimSetConverter(
            MappedJwtClaimSetConverter.withDefaults(overrides)
        );

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token is not intended for orders-api",
                    null
                )
            );
        };

        OAuth2TokenValidator<Jwt> tenantValidator = jwt -> {
            Object raw = jwt.getClaim("tenant_id");
            if (raw instanceof String tenant &&
                    "42".equals(tenant)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Unexpected tenant",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audienceValidator,
                tenantValidator
            )
        );

        return decoder;
    }
}
```

Imports for the example:

```java
import java.util.HashMap;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.MappedJwtClaimSetConverter;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
```

### 5.1. How to Read the Configuration Above

- `withIssuerLocation(ISSUER)` builds a decoder using the trusted issuer and appropriate metadata/JWKS discovery.
- `tenantToString` affects only the single custom claim issued by the issuer.
- `MappedJwtClaimSetConverter.withDefaults(overrides)` preserves default conversions for standard claims.
- `setClaimSetConverter(...)` wires the converter into the decoder's claim-set processing step.
- `JwtValidators.createDefaultWithIssuer(ISSUER)` preserves issuer/timestamp validation suitable for the Spring Security version.
- `audienceValidator` verifies the token was issued for this API.
- `tenantValidator` applies the tenant policy **after the claim has been type-converted**.
- `DelegatingOAuth2TokenValidator` composes all required conditions.

If multiple tenants are served by this API, **do not hardcode tenant `"42"`** in the global decoder. Instead, the validator can verify claim structure while per-request tenant access is evaluated at the business authorization layer.

### 5.2. Connecting to the Servlet `SecurityFilterChain`

```java
@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
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

After the JWT is verified and validators accept it, Spring Security maps `scope=orders.read` to `SCOPE_orders.read`. A token with the right audience and tenant yet **missing the scope** must still be rejected when calling an endpoint requiring read access.

## 6. `withDefaults(...)` vs. Writing a Whole-Map Converter from Scratch

Suppose you want to adjust one custom claim while preserving all other claims. There are two approaches with different purposes.

**Approach A — Override conversion for a single claim:**

```java
Map<String, Converter<Object, ?>> overrides = new HashMap<>();
overrides.put("tenant_id", tenantToString);

Converter<Map<String, Object>, Map<String, Object>> converter =
    MappedJwtClaimSetConverter.withDefaults(overrides);
```

Here each converter is registered by **claim name**. This fits when you only need to transform the **value/type of an existing claim**.

**Approach B — Use a whole-map converter:** If you want to copy or synthesize a new claim from another claim, you need access to multiple entries in the claim map; a per-claim converter alone is not enough.

For example: the AS emits `preferred_username`; the application wants to derive an internal `display_name` claim **without altering `sub`**.

```java
Converter<Map<String, Object>, Map<String, Object>> defaults =
    MappedJwtClaimSetConverter.withDefaults(Map.of());

Converter<Map<String, Object>, Map<String, Object>> claimSetConverter =
    rawClaims -> {
        Map<String, Object> normalized =
            new LinkedHashMap<>(defaults.convert(rawClaims));

        Object username = normalized.get("preferred_username");

        if (username instanceof String text && !text.isBlank()) {
            normalized.put("display_name", text.strip());
        }

        return normalized;
    };

decoder.setClaimSetConverter(claimSetConverter);
```

Additional import:

```java
import java.util.LinkedHashMap;
```

Points to keep in mind:

1. The outer converter delegates to `MappedJwtClaimSetConverter.withDefaults(Map.of())` so **default conversions for registered claims are not lost**.
2. Create a new `LinkedHashMap` from the result rather than assuming the returned map is mutable.
3. Only add `display_name` when the source value has the expected type and is non-blank.
4. Never delete `iss`, `aud`, `exp`, or `sub`.
5. Token validators must still decide whether the JWT is accepted by the API.

`display_name` is application presentation data, not proof of a user's verified legal name. Never use it as a primary account key if it can change or collide across users.

### 6.1. Renaming a Claim

Suppose the AS emits a legacy claim `legacy_user_name`, while UI code expects `display_name`. You can:

- Use a whole-map converter to **add an alias** `display_name` from `legacy_user_name`, keeping the original claim.
- Update code at the application boundary to read the original claim directly.
- Update the issuer contract so the AS emits the standard claim if you control the AS.

**Never rename `legacy_user_name` to `sub`** just to make `Authentication.getName()` look prettier. `sub` is the core subject identifier scoped to the issuer, tied to ownership, auditing, and tenants. Replacing `sub` can cause the application to grant permissions to the wrong principal.

### 6.2. When Removing a Claim Is Needed

Some converters may return `null` to drop a mapped claim, depending on the `MappedJwtClaimSetConverter` implementation behavior. However, **never drop a claim as a way to “bypass validation”**. Deleting `exp`, `iss`, `aud`, or permission-bearing claims can break the system's ability to evaluate the token properly.

If the goal is simply **not returning sensitive claims in API responses**, the right solution is **filtering data in controllers/DTOs**, not altering the claim set relied upon by security layers.

## 7. Converting Numbers, Strings, Timestamps, and Lists

These are common scenarios when customizing a claim-set converter.

### 7.1. NumericDate Should Remain in Spring's Timestamp Type

A JWT contains:

```json
{
  "iat": 1794715200,
  "nbf": 1794715200,
  "exp": 1794718800
}
```

These values are JWT NumericDates, representing seconds since the Unix epoch. Spring Security converts them to proper time types in `Jwt`, such as `Instant`, for timestamp validators and application code.

When you only need to adjust `tenant_id` or `preferred_username`, **never write a whole-map converter that converts every `Number` to a `String`**. Doing so breaks `getExpiresAt()` and timestamp validation types.

If an issuer sends timestamps in a non-standard format (e.g., milliseconds in `exp`), **fix the issuer first**. Silently patching it in the Resource Server hides spec deviations and makes different systems interpret the same token differently.

### 7.2. Audience Is a List, Not Just a Single String

JSON may be written as:

```json
"aud": "orders-api"
```

or:

```json
"aud": ["orders-api", "inventory-api"]
```

Spring Security code should check `jwt.getAudience()` rather than assuming `jwt.getClaim("aud")` is always a String:

```java
OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
    boolean valid = jwt.getAudience().contains("orders-api");

    return valid
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Wrong audience",
                null
            )
        );
};
```

The identifier `orders-api` identifies the **Resource Server**; never substitute the calling client's `client_id` for audience.

If transforming a custom `aud` claim, preserve JWT semantics: audience must represent intended token recipients—never inject the current API's audience into a token just to pass validation. Doing so turns a token issued for another API into an accepted token for the wrong purpose.

### 7.3. List and Group Claims

Some ASes emit:

```json
{
  "groups": ["sales", "support"],
  "roles": ["ORDER_VIEWER"]
}
```

Other systems return strings:

```json
{
  "groups": "sales support",
  "roles": "ORDER_VIEWER"
}
```

These two representations **do not automatically carry identical semantics**. If the AS contract specifies a space-delimited list, you can split accordingly while handling escaping, whitespace, group names with spaces, and duplicates.

For example, if a custom `tags` claim has a comma-delimited string contract, a converter can do:

```java
Converter<Object, Object> tagsConverter = value -> {
    if (value instanceof String text) {
        return Arrays.stream(text.split(","))
            .map(String::strip)
            .filter(item -> !item.isEmpty())
            .distinct()
            .toList();
    }
    return value;
};
```

Import:

```java
import java.util.Arrays;
```

**Only use this splitting logic when the input format is strictly defined**: commas are true delimiters and never valid characters inside a tag. For authorization-sensitive `groups` or `roles`, never guess delimiters.

### 7.4. Numbers and Identifiers with Leading Zeros

Suppose the AS sends:

```json
{"merchant_code": 123}
```

while the database stores `"00123"`. Leading zeros cannot be recovered from the JSON number `123` once the issuer discarded them. A claim converter cannot guess whether the user is merchant `00123` or `123` without a contract.

**Identifiers should have a stable representation**, usually strings. For genuinely numeric claims, apply type/range validation rather than coercing to Strings unconditionally.

## 8. Separating Claim Conversion from Principal Name Mapping

In a Resource Server, the principal placed into `Authentication` by Spring Security has a name, typically taken from `sub`.

Given a JWT:

```json
{
  "sub": "9d7e1b48-5d53-4ecb-a321-b9fafbe1ae38",
  "preferred_username": "phuong.nguyen",
  "email": "user@example.test"
}
```

There are three distinct concepts:

| Concept | Example | What Should It Be Used For? |
|---|---|---|
| `sub` | Stable UUID/subject from the issuer | Identifying the principal and linking permissions/resources if guaranteed by contract |
| `preferred_username` | `phuong.nguyen` | Login/display name, mutable |
| `email` | `user@example.test` | Contact info, not a primary identifier by default |

If the API wants `Authentication.getName()` to use another claim, Spring Security offers **`JwtAuthenticationConverter.setPrincipalClaimName(...)`**. That is usually a much better tool than rewriting `sub` in a claim-set converter.

```java
JwtAuthenticationConverter authenticationConverter =
    new JwtAuthenticationConverter();

authenticationConverter.setPrincipalClaimName("preferred_username");
```

Then wire the converter into the JWT Resource Server:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    JwtAuthenticationConverter authenticationConverter =
        new JwtAuthenticationConverter();

    authenticationConverter.setPrincipalClaimName(
        "preferred_username"
    );

    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(jwt ->
                jwt.jwtAuthenticationConverter(authenticationConverter)
            )
        )
        .build();
}
```

Related imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.web.SecurityFilterChain;
```

**Security note:** Choose `preferred_username` as the principal name only when the issuer guarantees the claim is always present, carries the required stability, and causes no identity confusion. For systems needing accurate ownership mapping or auditing, keeping `sub` is usually safer; display names can be read separately via `@AuthenticationPrincipal Jwt`.

### 8.1. Reading `Jwt` in a Controller Without Changing the Principal Name

```java
@GetMapping("/api/me")
public Map<String, Object> me(@AuthenticationPrincipal Jwt jwt) {
    return Map.of(
        "subject", jwt.getSubject(),
        "username", jwt.getClaimAsString("preferred_username")
    );
}
```

This snippet is illustrative and assumes `preferred_username` is present; `Map.of(...)` rejects null values. In production code, handle missing claims and return only fields cleared for disclosure.

Reading claims in a controller after Spring Security verifies the token **is completely different** from Base64URL-decoding the payload yourself and trusting it.

## 9. Separating Claim Conversion from Authority Mapping

Many systems want to turn `scope`, `scp`, `permissions`, or `roles` claims into `GrantedAuthority` instances.

That is the job of **`JwtGrantedAuthoritiesConverter`** paired with `JwtAuthenticationConverter`, not the default job of `MappedJwtClaimSetConverter`.

### 9.1. Standard Scopes

Token:

```json
{"scope": "orders.read orders.write"}
```

In a standard setup, Spring Security converts this to:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Then authorization can use:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

### 9.2. Custom Permission Claims

Suppose the issuer contract defines:

```json
{
  "permissions": ["orders:read", "orders:export"]
}
```

You can configure the authorities converter:

```java
JwtGrantedAuthoritiesConverter authoritiesConverter =
    new JwtGrantedAuthoritiesConverter();

authoritiesConverter.setAuthoritiesClaimName("permissions");
authoritiesConverter.setAuthorityPrefix("PERM_");

JwtAuthenticationConverter authenticationConverter =
    new JwtAuthenticationConverter();

authenticationConverter.setJwtGrantedAuthoritiesConverter(
    authoritiesConverter
);
```

Imports:

```java
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
```

Then `orders:read` maps to `PERM_orders:read`. If multiple permission claims must be merged, use a controlled composite authorities converter; never blindly trust any role-like claim.

**Keep the distinction clear:**

- **Claim-set converter:** What Java shape/type does `permissions` have?
- **Authorities converter:** Which Spring Security authorities does `permissions` translate into?
- **Authorization:** Which authority does this endpoint require?

If a claim simply has a non-standard name, you do not need to **rename the original claim** with `MappedJwtClaimSetConverter`: changing `authoritiesClaimName` on `JwtGrantedAuthoritiesConverter` is simpler and safer.

### 9.3. Never Escalate Privileges in the Conversion Layer

Insecure pattern:

```text
JWT has groups=["users"]
  -> inject "roles": ["ADMIN"] in claim-set converter
  -> JwtAuthenticationConverter grants ROLE_ADMIN
```

A converter running inside the Resource Server has no authority to **grant itself elevated privileges** just for internal convenience. Claim-to-authority mapping must reflect **policies and permission contracts attested by the issuer**, properly reviewed and tightly bounded.

## 10. Should You Convert or Validate a Claim?

Consider four distinct needs:

| Need | Right Tool | Example |
|---|---|---|
| Transform claim format per contract | `MappedJwtClaimSetConverter` or claim-set converter | `tenant_id` Number → String, `tags` CSV → List |
| Enforce a condition on the token | `OAuth2TokenValidator<Jwt>` / `JwtClaimValidator<T>` | `aud` contains `orders-api`; tenant is in allowlist |
| Choose principal name / authorities | `JwtAuthenticationConverter` / `JwtGrantedAuthoritiesConverter` | Principal from `sub` or another claim; `permissions` → `PERM_...` |
| Enforce endpoint/resource permissions | `authorizeHttpRequests`, method security, services | Read scope, order tenant/ownership |

### 10.1. Example: `tenant_id` Is a String, Yet Blank

A signed token contains:

```json
"tenant_id": ""
```

The claim-set converter keeps the empty string because it is already a String. If the contract forbids blank values, **a validator must reject it**:

```java
OAuth2TokenValidator<Jwt> tenantPresence = jwt -> {
    Object value = jwt.getClaim("tenant_id");

    if (value instanceof String text && !text.isBlank()) {
        return OAuth2TokenValidatorResult.success();
    }

    return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
            "invalid_token",
            "Missing or blank tenant_id",
            null
        )
    );
};
```

The converter must never replace a blank tenant with a default Resource Server tenant; that could turn an invalid token into a valid one against the AS's intent.

### 10.2. Example: Permission to Read Order #42

Token contains:

```json
{
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

No general converter or validator confirms that `user-123` is allowed to read **order 42**, unless the system has a very specific object-scoped token contract. This is a business permission: the controller/service or method security must verify ownership, tenant, and sharing policies.

## 11. Claim Modifications That Can Break Security

Not every normalization is harmless. In particular, these claims play direct roles in JWT validation:

| Claim | Risk If Modified Arbitrarily |
|---|---|
| `iss` | Can legitimize tokens from unauthorized issuers/realms by rewriting a wrong issuer to an accepted one |
| `aud` | Can let tokens meant for another API pass the audience validator |
| `exp`, `nbf` | Can extend lifetimes, drop not-before constraints, or subvert time validation |
| `sub` | Can attribute requests to the wrong user or service principal |
| `client_id` | Can spoof calling application identity when used in policies |
| `scope`, `permissions`, `roles` | Can over-grant privileges if values are added or altered |
| `cnf` | Can break sender-constrained access tokens (DPoP/mTLS binding) when used |
| `jti` | Can interfere with replay protection, denylists, or audits relying on JWT ID |

Especially dangerous examples:

```java
// UNSAFE ILLUSTRATION:
// Never rewrite audience so a token meant for another API passes validation.
normalized.put("aud", List.of("orders-api"));

// Never remove exp because a token expired.
normalized.remove("exp");

// Never hardcode sub to a default user.
normalized.put("sub", "admin-user");
```

**Never use a claim-set converter to “fix” a token that violates the authentication contract.** If the AS emits the wrong audience, fix the AS configuration, token request, or validator expectation. If timestamps fail, fix clock sync and issuer configuration—never delete claims.

### 11.1. Normalization Needs Both Justification and Trusted Source Data

A converter only receives information already inside a JWT signed by the issuer. Transforming `legacy_user_name` into `display_name` merely changes the representation of data the issuer sent.

However, mapping `legacy_role=admin` to `ROLE_ADMIN` is an **access control decision**. You need a contract confirming that `legacy_role` truly carries that meaning, that the role is valid for this API, and that all accepted issuers share that semantics.

### 11.2. Handling Wrong Types: Never Turn Errors into Valid Values

Suppose `tenant_id` must be a String per contract, yet an issuer unexpectedly sends an object:

```json
{"tenant_id": {"value": "shop"}}
```

A converter using `String.valueOf(value)` produces `"{value=shop}"`, causing downstream failures or weird matches. It is far better to **preserve the unexpected type so a validator catches it**, or fail validation explicitly; never invent ad-hoc parsing for out-of-contract data.

## 12. Claim Converters and Default Validators Must Go Together

A JWT decoder enforces multiple conditions:

1. The JWT is signed with a key from a trusted issuer.
2. Token timestamps are valid.
3. Issuer `iss` matches.
4. Audience `aud` targets this API.
5. Contract-required claims such as `tenant_id` are present.
6. Token type fits the access token profile, not an OIDC ID token.

`MappedJwtClaimSetConverter` **does not replace** these steps. It only adjusts claim structures and types.

When configuring a custom decoder, preserve standard validators:

```java
decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(ISSUER),
        audienceValidator,
        tenantValidator
    )
);
```

If you only call:

```java
decoder.setJwtValidator(tenantValidator);
```

without combining the remaining validators, issuer and timestamp checks may be lost because `setJwtValidator(...)` replaces the entire validator on the decoder. This is a **validation** configuration issue, distinct from using `MappedJwtClaimSetConverter.withDefaults(...)` to preserve default **conversions**.

Remember that “defaults” appears in **two different places**:

- **`MappedJwtClaimSetConverter.withDefaults(...)`:** preserves default claim type conversions.
- **`JwtValidators.createDefaultWithIssuer(...)`:** preserves default JWT validators along with the issuer check.

They serve two distinct responsibilities, so one **does not replace the other**.

## 13. Can You Supply a Default Claim Value When Missing?

You can write a converter that adds a fallback claim when missing, provided you distinguish **display helpers** from **security-critical values**.

For example, if `display_name` is purely for UI display and is absent, you might fall back to `preferred_username` or an application-chosen placeholder:

```java
Converter<Map<String, Object>, Map<String, Object>> defaults =
    MappedJwtClaimSetConverter.withDefaults(Map.of());

Converter<Map<String, Object>, Map<String, Object>> converter = raw -> {
    Map<String, Object> claims =
        new LinkedHashMap<>(defaults.convert(raw));

    if (!claims.containsKey("display_name")) {
        Object source = claims.get("preferred_username");
        if (source instanceof String name && !name.isBlank()) {
            claims.put("display_name", name);
        }
    }

    return claims;
};
```

However, **never auto-fill mandatory security claims** such as:

- `sub` when subject is missing.
- `tenant_id` when tenant drives authorization.
- `aud` when the token is not meant for this API.
- `exp` when expiration is missing despite being required by contract.
- `roles=ADMIN` when the issuer granted no such privilege.

Values synthesized for UI purposes should be clearly labeled **derived/internal**, never treated as claims attested by the AS.

## 14. Analyzing Multi-Issuer Scenarios

A Resource Server might receive JWTs from two issuers:

```text
Issuer A:
  https://login.example.test/realms/customers
  claim "tenant_id": "shop"

Issuer B:
  https://login.example.test/realms/partners
  claim "organization": "partner-shop"
```

You might want to normalize both into one internal `tenant_code` field. Before doing so, ensure:

- Both A and B are **configured trusted issuers**.
- The right decoder/JWKS for each issuer is used.
- `tenant_id` and `organization` carry equivalent contractual meaning.
- Neither issuer uses the same claim name with a completely different meaning.
- Audience and access-token types for each issuer are validated separately.
- Post-conversion tenant access is still enforced by policy.

**Never use a loose global converter to merge identities** across different issuers merely because two strings look alike. A user with the same username in two realms is not necessarily the same subject.

### 14.1. Principal Context Must Be Bound to Issuer

When using `sub` to identify users, a safe model pairs identity with:

```text
(iss, sub)
```

rather than `sub` alone when multiple issuers are accepted.

Replacing `sub` with a short username or dropping the issuer from the identity key can merge two distinct accounts by mistake. If you need an internal identity, build it through a verified mapping policy rather than writing ad-hoc converter code that assumes uniqueness.

## 15. Reading Claims in Controllers and Services

After the decoder accepts the JWT and Spring Security builds `Authentication`, a controller can inspect the principal:

```java
@RestController
@RequestMapping("/api")
public class CurrentUserController {

    @GetMapping("/me")
    public Map<String, Object> me(@AuthenticationPrincipal Jwt jwt) {
        Map<String, Object> result = new LinkedHashMap<>();

        result.put("subject", jwt.getSubject());
        result.put("tenantId", jwt.getClaimAsString("tenant_id"));
        result.put("displayName", jwt.getClaimAsString("display_name"));

        return result;
    }
}
```

Imports:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
```

This is an educational API example only. In production, never dump all claims/credentials into responses. For optional claims, `LinkedHashMap` permits null values; your response contract should decide whether to omit null fields or provide defaults.

Using `@AuthenticationPrincipal Jwt` gives the controller a **`Jwt` already verified by the Resource Server** per the filter chain configuration—completely different from manually splitting headers and Base64URL-decoding.

### 15.1. Do Not Treat a DTO as Proof of Authorization

A DTO returning `tenantId=shop` does not prove the caller is allowed to touch every resource in that tenant. Services must still enforce per-record permissions, scopes, data sharing rules, and business policies.

## 16. Distinguishing Claim Conversion Errors from Validation Errors

Consider a validly signed token with claims:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "aud": ["orders-api"],
  "tenant_id": {"unexpected": "object"},
  "exp": 1900000000
}
```

There are at least three ways the system can react:

**Case A — Converter handles Number/String and leaves Object untouched:** After conversion, `tenantValidator` checks that `tenant_id` is a String and returns `failure(...)`. This is a clean **claim validation** failure.

**Case B — Converter unsafely casts and throws a runtime exception:** Depending on how the decoder handles exceptions, the request may fail with a decoding error or infrastructure error. Never rely on an unhandled `ClassCastException` to produce your desired security HTTP response.

**Case C — Converter blindly turns Object into a string:** Execution continues with an out-of-contract string, risking subtle business bugs. Avoid this for identity or permission claims.

For required claims, choose **controlled conversion + explicit validators** so valid inputs are clearly bounded.

### 16.1. Wrong Issuer/Audience Is Not a Converter Problem

If a token contains:

```json
"aud": ["payments-api"]
```

while Orders API requires `orders-api`, **never** write a converter that adds `orders-api` to audience. The token must be rejected by the audience validator.

If a token is expired, **never** use a converter to bump `exp`. Expired tokens must be rejected by the timestamp validator.

If a JWT has an invalid signature, **no claim converter may ever make that token valid**.

## 17. Study Scenarios and Conclusions

### Scenario 1 — Issuer Sends `tenant_id=42`, API Expects `"42"`

The contract confirms numeric tenant 42 and string `"42"` have identical meaning, with no leading zeros or values exceeding parser precision.

**Approach:** `MappedJwtClaimSetConverter.withDefaults(...)` converts Number → String for `tenant_id`; add a validator checking the tenant is in an allowed list. Never alter `iss`, `aud`, `sub`, or `exp`.

### Scenario 2 — Wanting `Authentication.getName()` to Be `preferred_username`

**Approach:** Consider `JwtAuthenticationConverter.setPrincipalClaimName(...)` if the contract allows it and stability requirements are met. Never overwrite `sub` just to change a display name.

### Scenario 3 — `permissions` Claim Holds a List of Permissions

**Approach:** If the data already has the right structure, configure `JwtGrantedAuthoritiesConverter.setAuthoritiesClaimName("permissions")` and a suitable prefix. No need to rename the claim via claim-set conversion just to map authorities.

### Scenario 4 — JWT Contains `exp` as a NumericDate

**Approach:** Keep default conversion so `Jwt.getExpiresAt()` works with `Instant` and the timestamp validator enforces expiration. Never write a whole-map converter turning every value into a String.

### Scenario 5 — Missing `tenant_id` When Required by the API

**Approach:** Reject the token in a validator. Never silently populate a default tenant when tenant drives authorization.

### Scenario 6 — Token Has `aud=payments-api` While Client Calls Orders API

**Approach:** Reject in the audience validator. Never use a converter to “patch audience” to match the API.

### Scenario 7 — Issuers A and B Both Emit `sub=user-1`

**Approach:** In multi-issuer setups, identify principals by issuer + subject or an appropriate trusted mapping. Never merge two accounts from two issuers solely on matching `sub`.

### Scenario 8 — `groups` Claim Is a String While Backend Needs a Set

**Approach:** Convert only if the issuer has a clear delimiter contract and semantics, or ask the issuer to emit a proper array. When `groups` grants permissions, keep authority mapping and authorization tightly bounded to avoid privilege escalation.

## 18. Unit Testing Claim Converters vs. Integration Testing

When developing custom conversions, separate testing **type conversion logic** from testing **real JWT authentication**.

A unit test can invoke the claim-set converter directly:

```java
@Test
void tenantIdIsConvertedAndStandardClaimsRemainAvailable() {
    Converter<Object, Object> tenantToString = value -> {
        if (value instanceof Number number) {
            return number.toString();
        }
        return value;
    };

    Map<String, Converter<Object, ?>> overrides = new HashMap<>();
    overrides.put("tenant_id", tenantToString);

    Converter<Map<String, Object>, Map<String, Object>> converter =
        MappedJwtClaimSetConverter.withDefaults(overrides);

    Map<String, Object> raw = new HashMap<>();
    raw.put("tenant_id", 42);
    raw.put("aud", List.of("orders-api"));
    raw.put("exp", 1900000000L);

    Map<String, Object> result = converter.convert(raw);

    assertEquals("42", result.get("tenant_id"));
    assertTrue(result.containsKey("aud"));
    assertInstanceOf(Instant.class, result.get("exp"));
}
```

Additional imports for the test:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.oauth2.jwt.MappedJwtClaimSetConverter;
```

**This unit test does not verify JWT signatures**: it only checks that the map converter handles values as expected. Integration tests must use properly signed test JWTs passing through a real `JwtDecoder`, verifying issuer, audience, timestamps, and converter/validator wiring in Spring Security configuration.

A technical integration matrix to consider:

| Scenario | Expectation |
|---|---|
| Valid signature, right issuer/audience/time, convertible tenant | Decodes successfully and exposes normalized claim |
| Invalid signature, plausible-looking claims | Decoder rejects before trusting claims |
| Valid signature, different audience | Audience validator rejects |
| Expired JWT | Timestamp validator rejects |
| Wrongly typed tenant with no valid conversion rule | Tenant validator rejects |
| Empty/missing tenant when required | Validator rejects |
| Valid claims, missing endpoint scope | Authentication may succeed; authorization denies |
| Display name changes while `sub` stays unchanged | Stable identity remains intact when anchored on subject |

These scenarios illustrate how to design data boundaries; they do not claim automated tests were executed inside this knowledge article.

## 19. Mistakes to Avoid When Adjusting Claims

| Mistake | Harm | Right Direction |
|---|---|---|
| Manually parsing Base64URL JWTs and trusting username for access | Trusts unverified data | Let Spring Security's decoder verify first |
| Writing a whole-map converter turning every claim into String | Breaks timestamps, arrays, identifiers | Override only required claims; keep defaults |
| Rewriting `aud` to match the API | Accepts tokens meant for other resources | Reject with an audience validator |
| Altering `exp` or removing `nbf` | Weakens token expiration enforcement | Keep standard claims and run timestamp validators |
| Replacing `sub` with display name | Mixes identities; breaks ownership/auditing | Use `JwtAuthenticationConverter` or display DTOs |
| Using `client_id` in place of audience | Confuses the calling client with the Resource Server | Check issuer + expected audience |
| Inferring `ADMIN` from `groups` without a contract | Escalates privileges beyond issuer intent | Map authorities strictly per security contract |
| Dropping the issuer validator in a custom decoder | Trusts tokens from unwanted issuers | Keep `JwtValidators.createDefaultWithIssuer(...)` |
| Swallowing exceptions and accepting tokens | Fails open | Reject whenever validation fails |
| Merging claims from multiple issuers by matching names | Identity/permission collisions | Use issuer-specific mappings with explicit policies |

### 19.1. Do Not Confuse “Display Name” with Identity

A claim like `preferred_username` can change when a user renames themselves. `sub` is typically designed to identify the subject stably within the issuer. Never let display-name normalization change the principal used by business services for data ownership checks.

### 19.2. Never Use Conversion to Work Around Security Errors

If a JWT violates the contract, fix it at the **issuing source** or in **validators/policies**. Conversion is a format-compatibility tool, never a shortcut to bypass validation.

### 19.3. What About Opaque Tokens?

In the **opaque token** branch of Spring Security Resource Server, `OpaqueTokenIntrospector` returns an `OAuth2AuthenticatedPrincipal` based on introspection results. `MappedJwtClaimSetConverter` is a tool of the **JWT decoder** and is not automatically applied to opaque token attributes.

When introspection data needs normalization, design an appropriate converter/introspector wrapper aligned with the AS contract and opaque authentication policy rather than trying to reuse `NimbusJwtDecoder`.

## 20. Deciding Which Tool Fits a Real Requirement

When faced with “the JWT has a claim different from what the application expects”, ask:

1. **Do we need to convert a type or add a data alias?** Use `MappedJwtClaimSetConverter.withDefaults(...)` or a whole-map converter delegating to defaults.
2. **Do we need to reject tokens with missing/invalid claims?** Use `OAuth2TokenValidator<Jwt>` or `JwtClaimValidator<T>`.
3. **Do we need to change `Authentication.getName()`?** Use `JwtAuthenticationConverter.setPrincipalClaimName(...)` when appropriate, while protecting stable identity.
4. **Do we need to turn claims into permissions?** Use `JwtGrantedAuthoritiesConverter` or a controlled custom authorities converter.
5. **Do we need to control which endpoints or records a user sees?** Use `authorizeHttpRequests`, method security, and data policies.
6. **Do we need to fix a JWT with wrong issuer, audience, expiry, or signature?** **Never use a claim-set converter**; fix token issuance/validation config or reject the token.
7. **Are there multiple issuers or tenants?** Bind converters and validators to trusted issuers and avoid identity/authority ambiguity.
8. **Is this Servlet or WebFlux?** Examples here target a Servlet JWT Resource Server using `NimbusJwtDecoder`; the Reactive stack has its own decoder/configuration mechanisms—do not copy-paste the Servlet filter chain verbatim.

## 21. References

- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `NimbusJwtDecoder`, claim-set conversion, JWT validation, and authority mapping.
- [Spring Security API — MappedJwtClaimSetConverter](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/MappedJwtClaimSetConverter.html): JWT claim-set conversion and `withDefaults(...)`.
- [Spring Security API — NimbusJwtDecoder](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html): decoder and `setClaimSetConverter(...)`.
- [Spring Security API — JwtAuthenticationConverter](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html): principal name and authorities converter.
- [Spring Security API — JwtGrantedAuthoritiesConverter](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html): converting permission claims into `GrantedAuthority`.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): registered claims such as `iss`, `sub`, `aud`, `exp`, `iat`.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token claim conventions and usage at Resource Servers.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): avoiding token-type confusion and unsafe JWT handling.

**Summary:** `MappedJwtClaimSetConverter` helps **convert types and adjust claim representations** during JWT decoding, especially for issuer-specific custom claims. Use `withDefaults(...)` to preserve standard conversions; never rewrite issuer, audience, expiry, subject, or permissions to “legitimize” an invalid token. `JwtValidators` verifies the token, `JwtAuthenticationConverter` builds identity/authorities, and authorization decides resource access.
