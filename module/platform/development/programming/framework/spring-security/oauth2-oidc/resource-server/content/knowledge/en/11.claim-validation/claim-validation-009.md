# Preserving Default Validators When Adding New Requirements

When building a **Spring Security OAuth 2.0/OIDC Resource Server**, an API typically validates JWT access tokens issued by an Authorization Server / Identity Provider (IdP). Initially the application might configure only `issuer-uri`, and later add extra requirements such as:

- Accepting only access tokens targeted at this API (`aud`).
- Requiring `tenant_id` or allowing tokens only from specific tenants.
- Capping token lifetime (`exp - iat`) or token age.
- Enforcing the expected token profile/type—for example, JWT access tokens rather than OIDC ID tokens.
- Rejecting tokens whose claims contradict the contract.

When adding a custom `OAuth2TokenValidator<Jwt>`, a common mistake is **replacing the entire existing validator set** with the new validator. The API appears to tighten security, yet can silently lose `exp`, `nbf`, `iss`, or other default constraints that Spring Security previously applied when auto-configuring the decoder.

Principle of this lesson:

> **Add claim validation rules by composing them with the default validators matching your contract, rather than overwriting blindly.** Signatures, issuer, timestamps, audience, and business authorization are independent safeguards that must all remain intact together.

This article uses **Servlet Resource Server, Spring Security 6+ / Spring Boot 3+** as the baseline for Java examples. Exact APIs, classes, and defaults can vary across versions; for any specific version, verify which validators the framework applies and what changes a custom decoder introduces.

## 1. A Valid JWT Must Pass Multiple Verification Layers

A request to the Orders API:

```http
GET /api/orders/ord-123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

The access token might carry this payload:

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893459600,
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
```

Example values are for learning only, not a signed JWT. The Resource Server must evaluate several conditions:

| Layer | Question to Answer | Typical Handler Component |
|---|---|---|
| Credential extraction | Where is the Bearer token in the HTTP request? | `BearerTokenResolver` |
| Cryptography | Does the JWT have a valid signature under a trusted key and allowed algorithm? | `JwtDecoder` / Nimbus JOSE |
| Issuer | Was the token issued by a trusted issuer? | `JwtIssuerValidator` or equivalent |
| Timestamps | Is the token expired or not yet valid? | `JwtTimestampValidator` |
| Audience | Was the token issued for `orders-api`? | Contract audience validator |
| Additional claims | Are tenant, token type, token age, or other constraints valid? | Custom `OAuth2TokenValidator<Jwt>` |
| Endpoint permissions | Does the token carry authority `SCOPE_orders.read`? | `AuthorizationManager` / HTTP security |
| Resource permissions | May this user/tenant view order `ord-123`? | Service/domain policy |

These steps cannot substitute for one another. For instance, a token with `aud=orders-api` that has expired must be rejected. A validly signed, unexpired token with `aud=payments-api` must also be rejected at the Orders API. A valid token with `orders.read` still does not grant access to another tenant's orders.

### 1.1. Authentication and Authorization Are Different

```mermaid
flowchart TD
    A["HTTP Bearer request"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["JwtDecoder"]
    C --> D{"JWS signature, trusted key,<br/>algorithm valid?"}
    D -->|"No"| X["401: invalid token"]
    D -->|"Yes"| E{"Default validators:<br/>issuer, timestamp, ...?"}
    E -->|"No"| X
    E -->|"Yes"| F{"Custom validators:<br/>audience, tenant, token age, ...?"}
    F -->|"No"| X
    F -->|"Yes"| G["JwtAuthenticationToken / SecurityContext"]
    G --> H{"Scope + resource permissions?"}
    H -->|"No"| Y["403 or policy denial"]
    H -->|"Yes"| Z["Controller / Service"]
```

Preserving default validators belongs to **authentication and access-token contract verification**. It does not replace `authorizeHttpRequests`, `@PreAuthorize`, or business owner/tenant policies.

## 2. How Validators Work in Spring Security

Spring Security defines the interface:

```java
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public interface OAuth2TokenValidator<T> {
    OAuth2TokenValidatorResult validate(T token);
}
```

When validating JWTs, the type parameter is `Jwt`. A validator:

- Receives a JWT object already processed by the decoder in the authentication pipeline.
- Evaluates one or more conditions, e.g., `aud` contains the API name.
- Returns `OAuth2TokenValidatorResult.success()` if the condition holds.
- Returns `OAuth2TokenValidatorResult.failure(...)` if it does not.

This is a **result-returning contract**, not an HTTP filter. A validator does not read the `Authorization` header, sign JWTs, mutate token contents to make them valid, or decide row-level permissions on database entities.

### 2.1. A Simple Audience Validator

```java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class RequiredAudienceValidator
        implements OAuth2TokenValidator<Jwt> {

    private final String requiredAudience;

    public RequiredAudienceValidator(String requiredAudience) {
        this.requiredAudience = requiredAudience;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getAudience().contains(requiredAudience)) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "JWT audience is not accepted by this API",
                null
            )
        );
    }
}
```

`jwt.getAudience()` exposes the audience list; a JWT may represent `aud` as a string or an array per spec. Check membership by **exact value**—never use partial matches like `aud.contains("orders")` on raw JSON or loose domain similarity.

This validator is useful, yet **it does not check issuer or expiration itself**. If you attach it to the decoder by replacing all active validators, the Resource Server can lose other essential checks.

### 2.2. Independent Validators Must All Pass

Example Orders API contract:

```text
exact issuer      = https://idp.example.com/realms/shop
required audience = orders-api
token not expired
token not before nbf
tenant_id required
JWT profile matches access token type
```

A token is accepted only when **all mandatory conditions** hold. With validator composition, validation follows logical conjunction:

```text
VALID =
  signatureValid
  AND issuerValid
  AND timeValid
  AND audienceValid
  AND customClaimsValid
```

`OAuth2TokenValidator` runs claim checks after the decoder's cryptographic stage. Never use a custom claim validator to "compensate" for a decoder that skips signatures or permits untrusted algorithms.

## 3. What Are the Default Validators?

Spring Security provides key helpers:

```java
JwtValidators.createDefault()
JwtValidators.createDefaultWithIssuer(trustedIssuer)
```

In common JWT Resource Server setups:

- `JwtValidators.createDefault()` builds the baseline validators treated as defaults by Spring Security for the active version.
- `JwtValidators.createDefaultWithIssuer(issuer)` adds the specified issuer constraint alongside those baseline validators.
- **JWT time validation** runs through `JwtTimestampValidator`, typically checking `exp` and `nbf` when present per contract.
- Other checks such as token type / JWT profile validation may depend on version and framework setup—for instance JOSE `typ` settings and type validators. Never assume "defaults definitely contain only two validators" across all versions.

The key is using the official helper rather than guessing and hand-rolling a narrower manual subset:

```java
OAuth2TokenValidator<Jwt> defaults =
    JwtValidators.createDefaultWithIssuer(trustedIssuer);
```

For an API trusting a specific issuer, the `WithIssuer` variant captures that trust boundary. If you create a decoder from a JWK Set URI without setting an issuer validator, **a valid signature under a fetched key does not mean `iss` was checked against the expected issuer**.

### 3.1. Signature Verification Is Not Claim Validation

`NimbusJwtDecoder` verifies JWS signatures using a trusted key/key set and JOSE constraints. `OAuth2TokenValidator<Jwt>` checks token conditions like issuer, timestamps, and audience.

```text
JWT from client
    |
    v
NimbusJwtDecoder:
    parse + verify JWS with trusted key/algorithm
    |
    v
OAuth2TokenValidator<Jwt>:
    issuer, exp, nbf, audience, additional policies...
    |
    v
Verified Jwt / JwtAuthenticationToken
```

A validly signed token whose `exp` has passed must be rejected. Conversely, a token with valid `exp` yet an invalid signature must also be rejected. Never use a "parse-only" decoder or raw Base64 payload decoding in place of a real signature-verifying decoder.

### 3.2. Does Every JWT Require `exp`, `nbf`, `iat`, and `iss`?

**You cannot infer that from RFC 7519 alone.** The JWT spec defines the semantics of registered claims, while presence and mandatory rules are decided by the **token profile and API contract**. RFC 9068 JWT access tokens enforce stricter rules than arbitrary JWTs.

Therefore, distinguish:

1. **Default validators** check supported claims when present plus framework defaults.
2. **Application contract / token profile** may require specific claims to always exist, such as issuer, audience, or expiration.
3. **Custom validators** can enforce presence and cross-claim relationships for those claims.

Never assume every claim is guaranteed present just because you called `JwtValidators.createDefault()`. When following a concrete access-token profile, verify its requirements and add any needed validators.

## 4. Classic Mistake: `setJwtValidator` Replaces Rather Than Appends

Suppose code creates a JWT decoder:

```java
NimbusJwtDecoder decoder =
    NimbusJwtDecoder.withIssuerLocation(trustedIssuer).build();
```

A developer wants to add audience validation and writes:

```java
// DO NOT DO THIS: accidentally replaces the entire active validator set.
decoder.setJwtValidator(new RequiredAudienceValidator("orders-api"));
```

Problem: `NimbusJwtDecoder#setJwtValidator(...)` assigns the validator you pass for JWT checks; it is a **setter/replacement**, not an "append to existing defaults" operation.

As a result, the decoder may now check only audience at the `OAuth2TokenValidator` layer, dropping issuer and timestamp checks from the previous validator set. Signatures may still be verified, yet signature verification alone cannot protect a Resource Server.

### 4.1. Why This Bug Hides When Test Tokens Are All Valid

If tests only send a token like:

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "aud": ["orders-api"],
  "exp": 1893459600
}
```

that is still unexpired, tests keep passing after replacing the validator. The bug surfaces only when a token arrives with **the right audience yet expired**, or **the right audience yet wrong issuer** signed by a key trusted by the decoder.

Thus "adding an audience validator" must mean **preserving existing checks and adding audience**, never replacing the validator suite outright.

### 4.2. The Right Way: Compose With `DelegatingOAuth2TokenValidator`

`DelegatingOAuth2TokenValidator` combines multiple `OAuth2TokenValidator<T>` instances with logical **AND**: a token passes only when every component validator passes.

```java
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;

OAuth2TokenValidator<Jwt> defaults =
    JwtValidators.createDefaultWithIssuer(trustedIssuer);

OAuth2TokenValidator<Jwt> audience =
    new RequiredAudienceValidator("orders-api");

OAuth2TokenValidator<Jwt> composed =
    new DelegatingOAuth2TokenValidator<>(defaults, audience);

decoder.setJwtValidator(composed);
```

Here `setJwtValidator` still **replaces** the decoder's internal validator, yet the replacement explicitly includes both:

- The default validators with issuer verification.
- The new audience validator.

**Core pattern:**

```java
decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(trustedIssuer),
        extraValidator
    )
);
```

This is readable and minimizes the risk of dropping baseline checks. Never construct `DelegatingOAuth2TokenValidator<>(extraValidator)` expecting it to auto-discover existing decoder validators.

## 5. Complete Example: Preserving Defaults While Adding Audience Validation

Suppose the Orders API accepts only JWT access tokens:

```yaml
# application.yml
app:
  security:
    issuer: https://idp.example.com/realms/shop
    audience: orders-api
```

And Spring Security 6+:

```java
import org.springframework.beans.factory.annotation.Value;
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
public class JwtDecoderConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.issuer}") String trustedIssuer,
            @Value("${app.security.audience}") String requiredAudience) {

        // This issuer comes from application config, never arbitrarily
        // from an unverified incoming JWT.
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(trustedIssuer).build();

        OAuth2TokenValidator<Jwt> defaults =
            JwtValidators.createDefaultWithIssuer(trustedIssuer);

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains(requiredAudience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Unexpected access-token audience",
                        null
                    )
                );

        OAuth2TokenValidator<Jwt> allValidators =
            new DelegatingOAuth2TokenValidator<>(
                defaults,
                audience
            );

        // Replace with the COMPOSITE of defaults + audience,
        // never with audience alone.
        decoder.setJwtValidator(allValidators);
        return decoder;
    }
}
```

A `SecurityFilterChain` using the registered decoder:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ResourceServerSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Spring Security uses the application-provided `JwtDecoder` bean for the JWT Resource Server chain whenever no other decoder is explicitly set in the DSL. Because this `@Bean JwtDecoder` is custom, Spring Boot generally **does not auto-create a second default JWT decoder**. Thus the application is responsible for configuring the full validator chain on its custom bean.

Guarantees in this example:

1. The decoder fetches metadata/keys from a **trusted configured issuer**.
2. Signatures and JOSE constraints are verified by the decoder.
3. `JwtValidators.createDefaultWithIssuer` retains default checks and issuer verification.
4. Audience must contain `orders-api`.
5. After authentication, endpoints enforce `SCOPE_orders.read` or `SCOPE_orders.write`.
6. The service still enforces owner/tenant permissions on each order.

### 5.1. Why Never Read `jwt.getIssuer()` to Configure the Decoder?

Broken trust boundary:

```java
// Conceptual anti-pattern:
String issuer = decodeUnverifiedPayload(token).getIssuer();
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);
```

Any sender can put any `iss` inside an unverified JWT. If the API accepts an issuer/JWKS from a token-supplied URL, an attacker controls the key source the API trusts. Trusted issuers must be **configured or chosen from a governed allowlist**, and the actual `iss` claim must then be matched by the validator.

### 5.2. For APIs That Accept Only One Audience

In the example above, `jwt.getAudience().contains(requiredAudience)` accepts tokens with:

```json
{ "aud": ["orders-api"] }
```

or:

```json
{ "aud": ["orders-api", "another-api"] }
```

As long as the contract permits multi-audience tokens, that behavior fits. If the API **requires the audience to contain only itself**, add an explicit rule:

```java
boolean exactOnlyAudience =
    jwt.getAudience().size() == 1 &&
    jwt.getAudience().contains(requiredAudience);
```

This is a **stronger** requirement than "audience contains `orders-api`" and must be aligned with the Authorization Server. Never silently reject multi-audience tokens if the token profile permits them, and never silently accept them if your API contract requires strict resource isolation.

## 6. With Spring Boot Auto-Configuration, Do You Always Need a Custom `JwtDecoder`?

Not every new claim requirement forces you to write a `JwtDecoder` bean. In modern Spring Boot versions, audience can be configured via properties:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
```

When no custom decoder bean exists and auto-configuration applies, Spring Boot can construct a `JwtDecoder` with issuer, timestamp, and audience constraints per supported properties.

Benefit: no manual `setJwtValidator` call, reducing the risk of dropping default checks. This is usually the simplest option when **the new requirement maps directly to a supported Spring Boot property**.

### 6.1. A Custom Bean Makes Boot Step Aside

Rules to remember:

| Application State | Meaning |
|---|---|
| Only `issuer-uri`/`audiences` configured, no custom `JwtDecoder` | Boot can build a decoder with validators from properties |
| Developer defines a `@Bean JwtDecoder` | Boot typically skips creating a default decoder; custom code must preserve validators |
| Custom `SecurityFilterChain` with no `JwtDecoder` bean | Boot can still create the decoder; chain must enable `oauth2ResourceServer().jwt()` |
| Chain enables only `httpBasic()` even if a decoder exists | Decoder may exist in context yet won't run via Bearer filter |
| Chain specifies `jwt.decoder(customDecoder)` directly | Chain uses the specified decoder; changing Boot properties may not affect it |

**Creating a custom bean solely for audience can be overkill if the `audiences` property already fulfills your contract.** However, if you need tenant, token-age, or custom profile claim checks, an application-managed decoder/validator is often needed.

### 6.2. Do Not Confuse `issuer-uri`, `jwk-set-uri`, and `audiences`

| Property | Responsibility |
|---|---|
| `issuer-uri` | Declares trusted issuer and enables `iss` claim validation |
| `jwk-set-uri` | Specifies public-key source for verifying JWS signatures |
| `audiences` | Restricts tokens to audiences required by the API |

When configuring only `jwk-set-uri`, the API knows **where to fetch keys** yet does not necessarily have an **issuer constraint** anchored to an explicit issuer. If your app needs both, configure `issuer-uri` or an explicit issuer validator.

Likewise, having a valid issuer does not automatically guarantee audience is checked across all versions and decoder setups. The contract must specify every constraint explicitly.

## 7. Adding Multiple Validators: Audience, Tenant, and Token Age

A Resource Server might require three additional rules:

1. Audience must include `orders-api`.
2. `tenant_id` claim must be present and in the API's configured allowlist.
3. Access token must not be too old relative to `iat`, and `iat` must be present per contract.

These validators **do not replace** issuer, expiration, or not-before checks.

### 7.1. Tenant Validator

```java
import java.util.Set;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class AllowedTenantValidator
        implements OAuth2TokenValidator<Jwt> {

    private final Set<String> allowedTenants;

    public AllowedTenantValidator(Set<String> allowedTenants) {
        this.allowedTenants = Set.copyOf(allowedTenants);
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        String tenant = jwt.getClaimAsString("tenant_id");

        if (tenant != null && allowedTenants.contains(tenant)) {
            return OAuth2TokenValidatorResult.success();
        }

        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Token tenant is not accepted",
                null
            )
        );
    }
}
```

Allowing tenants **at the token level** helps when an API serves a fixed set of tenants. Still, viewing individual records remains a business authorization problem: a token for `tenant-a` does not automatically grant access to every record in `tenant-a` if owner/role policies restrict it further.

If an API genuinely serves all tenants under an issuer, a static tenant allowlist may not fit; instead, check tenant/subject consistency and enforce access in the business layer rather than cramming every policy into JWT validators.

### 7.2. Token Age Validator

Suppose the contract requires `iat` to exist, not lie in the future beyond allowed clock skew, and have token age at most 15 minutes.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class TokenAgeValidator implements OAuth2TokenValidator<Jwt> {

    private final Clock clock;
    private final Duration maxAge;
    private final Duration allowedClockSkew;

    public TokenAgeValidator(
            Clock clock,
            Duration maxAge,
            Duration allowedClockSkew) {
        this.clock = clock;
        this.maxAge = maxAge;
        this.allowedClockSkew = allowedClockSkew;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        Instant issuedAt = jwt.getIssuedAt();
        Instant now = Instant.now(clock);

        if (issuedAt == null) {
            return invalid("Required iat claim is missing");
        }
        if (issuedAt.isAfter(now.plus(allowedClockSkew))) {
            return invalid("iat is unexpectedly in the future");
        }
        if (issuedAt.isBefore(now.minus(maxAge).minus(allowedClockSkew))) {
            return invalid("Token age exceeds policy");
        }
        return OAuth2TokenValidatorResult.success();
    }

    private static OAuth2TokenValidatorResult invalid(String description) {
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", description, null)
        );
    }
}
```

Here `Clock` is injected for deterministic time control in unit tests. `maxAge` and `allowedClockSkew` must be chosen deliberately. `JwtTimestampValidator` still checks `exp`/`nbf` per default rules; the validator above adds **constraints on `iat` and token age**, without replacing the timestamp validator.

Note two distinct concepts:

- **Current token age:** `now - iat`; an older token whose `exp` has not arrived yet can still be rejected by a max-age policy.
- **Issued lifetime:** `exp - iat`; this caps the duration the IdP assigned to the token, which is not identical to current age.

If the contract requires both, check both explicitly. Never confuse `iat` with the user's most recent interactive login; OAuth refresh or token exchange can mint a fresh token with a new `iat` without a fresh login.

### 7.3. Composing Three New Validators With Defaults

```java
import java.time.Clock;
import java.time.Duration;
import java.util.Set;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;

OAuth2TokenValidator<Jwt> defaults =
    JwtValidators.createDefaultWithIssuer(trustedIssuer);

OAuth2TokenValidator<Jwt> combined =
    new DelegatingOAuth2TokenValidator<>(
        defaults,
        new RequiredAudienceValidator("orders-api"),
        new AllowedTenantValidator(Set.of("tenant-a", "tenant-b")),
        new TokenAgeValidator(
            Clock.systemUTC(),
            Duration.ofMinutes(15),
            Duration.ofSeconds(30)
        )
    );

decoder.setJwtValidator(combined);
```

Overall effect: **each added rule narrows the accepted token set** instead of dropping older rules. If the composite returns an error, the decoder rejects the token through the JWT authentication flow.

Never try to encode database-backed authorization rules inside token validators: when an order's ownership changes, that event does not rewrite claims inside an issued JWT. Enforce resource policies at the resource layer.

## 8. When Changing Clock Skew, Keep Issuer and All Other Constraints

Spring Security provides `JwtTimestampValidator` for tuning clock skew to your environment. Example:

```java
import java.time.Duration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

JwtTimestampValidator timestamp =
    new JwtTimestampValidator(Duration.ofSeconds(30));

JwtIssuerValidator issuer =
    new JwtIssuerValidator(trustedIssuer);

OAuth2TokenValidator<Jwt> audience =
    new RequiredAudienceValidator("orders-api");

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        timestamp,
        issuer,
        audience
    )
);
```

**This is an explicit timestamp/issuer/audience pattern when you have a clear reason to override the timestamp validator.** Inspect all remaining default validators in your current Spring Security version (especially JWT type/profile constraints) before using this as a production replacement.

Because `setJwtValidator` replaces the entire chain, writing only `timestamp + issuer + audience` can drop other validators if your framework version includes more defaults. **When you only need to add audience or tenant, prefer `createDefaultWithIssuer` + extra validators.** When you must change timestamp validation itself, reconstruct the **complete** policy set for your version and contract rather than copying an outdated snippet.

### 8.1. Clock Skew Has Security Bounds

A Resource Server whose clock drifts by a few seconds from the IdP may reject newly minted tokens or tokens right at `nbf`. Allowing a small offset is practical. However:

- Large skew widens the acceptance window around both `exp` and `nbf`.
- Never use large skew to mask broken system clock synchronization.
- Policies should be consistent across APIs sharing the same contract.
- Server clock sync (NTP) and monitoring actual drift matter far more than loosely relaxing validators.

## 9. Beyond Adding Claims: Keep the Right Token Type and Profile

An Authorization Server may issue:

- **Access tokens** for Resource Servers.
- **OIDC ID tokens** for OIDC clients.
- Other JWTs for logout, authorization responses, or internal protocols.

Multiple token types can share the same `iss` and verify under the same key set while having **different purposes and audiences**. APIs must distinguish token profile/type per contract rather than accepting any JWT with a valid signature.

Example:

```text
OIDC ID token:
  aud = shop-web
  purpose = client verifies login result

OAuth access token:
  aud = orders-api
  purpose = Orders API protects resources
```

Even when using `JwtValidators.createDefaultWithIssuer`, still verify token type, `aud`, and accepted access-token profile rules. Default `typ` checks can vary across versions and decoder setups; never replace them with an overly permissive custom check.

### 9.1. Header `typ` Alone Does Not Prove a Token Is an Access Token

Example JWS header:

```json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "issuer-key-1"
}
```

`typ` signals the JWT type, yet this header comes from the token sender and becomes trustworthy only alongside **proper JWS signature and token-profile verification**. Never use a lone string check like `typ == "at+jwt"` in place of issuer, audience, timestamps, and signature verification.

If adopting the RFC 9068 JWT access token profile, the Resource Server must verify all profile-required claims and token types using version-appropriate APIs/validators. A stricter contract never means discarding baseline safeguards.

### 9.2. JWE or Opaque Tokens Do Not Automatically Flow Through the Same JWT Validators

`OAuth2TokenValidator<Jwt>` applies when the Resource Server works with a `Jwt` produced by a contract-compliant decoder. When validating access tokens via **opaque-token introspection**, Spring Security uses `OpaqueTokenIntrospector` and different principals/authorities; `JwtDecoder#setJwtValidator` does not automatically apply to the opaque chain.

For **JWE / nested JWTs**, the application needs a processor capable of decrypting and verifying the format into a trustworthy `Jwt`, or appropriate introspection. Never use `JwtValidators` to cover up an unverified inner JWS signature or missing decryption/issuer-authentication contract.

## 10. With Multiple Issuers, Keep Validators Per Issuer

Some APIs accept access tokens from multiple trusted IdPs or realms. A common mistake is sharing one global decoder across all issuers and merely adding audience:

```text
Token A: iss = https://idp-a.example.com
Token B: iss = https://idp-b.example.com
```

Even if the API genuinely trusts both A and B, each issuer may have its own:

- JWKS URI or key set.
- Allowed signing algorithms.
- Claim mapping, scope format, and tenant policies.
- Issuer and profile validators.

Never take an arbitrary unverified `iss` and automatically download keys from that URL. Maintain a **trusted issuer allowlist**, a multi-issuer resolver/decoder, and per-issuer validators.

Conceptual model:

```mermaid
flowchart TD
    A["Bearer JWT"] --> B{"Is iss in<br/>trusted-issuer allowlist?"}
    B -->|"No"| X["Reject"]
    B -->|"Yes"| C["Select configured trusted<br/>decoder/keys for issuer"]
    C --> D["Verify signature"]
    D --> E["Default validators<br/>for that issuer"]
    E --> F["API audience, tenant, profile"]
    F --> G["Authorization"]
```

In this architecture, "preserving default validators" means **each issuer branch still validates issuer and timestamps**—never drop issuer validation just to support multiple IdPs.

### 10.1. Sharing an Audience Does Not Make Two Issuers Equivalent

A token from an untrusted issuer can assert `aud=orders-api`. Audience is therefore an **additional check inside the issuer boundary**, never a substitute for issuer verification.

Similarly, `sub=user-42` from two different issuers does not guarantee the same user. When mapping to internal accounts, pair `(iss, sub)` or use explicit identity linking.

## 11. With a Custom Authentication Converter, Are Validators Still Needed?

`JwtAuthenticationConverter` or a custom authority converter transforms a verified JWT into an `Authentication` and `GrantedAuthority` collection. For example:

```text
JWT scope = orders.read
      |
      v
JwtGrantedAuthoritiesConverter
      |
      v
GrantedAuthority = SCOPE_orders.read
```

Converters and validators perform two distinct jobs:

| Component | Responsibility |
|---|---|
| `JwtDecoder` | Verifies signature / JOSE spec and builds `Jwt` |
| `OAuth2TokenValidator<Jwt>` | Evaluates claim contract to decide token acceptance |
| `JwtAuthenticationConverter` | Converts accepted `Jwt` into `Authentication`/principal/authorities |
| HTTP/method authorization | Enforces authorities and endpoint rules |
| Business service | Decides access to specific resources |

If a custom converter changes the principal name from `sub` to `preferred_username`, it does not automatically ensure that claim is present, from the right issuer, or contract-compliant. Likewise, if a custom validator checks tenant, the converter does not turn tenant into object-level authorization.

### 11.1. Never Use a Converter to Reject Non-Conforming Tokens

A converter maps authorities, whereas rules governing **whether the token should be accepted at all** belong in the decoder/validators whenever possible. If an invalid claim requires rejecting the token outright, signal `OAuth2TokenValidatorResult.failure` instead of silently producing an authority-less `Authentication` and hoping every endpoint blocks it.

## 12. Error Handling: `invalid_token` and HTTP Responses

When a custom claim validator returns an error, e.g.:

```java
return OAuth2TokenValidatorResult.failure(
    new OAuth2Error(
        "invalid_token",
        "Required audience is missing",
        null
    )
);
```

`JwtDecoder` rejects the JWT in the authentication flow. In a standard bearer API, an invalid token results in **HTTP 401 Unauthorized** with a Bearer challenge handled by Spring Security components.

Conversely, a token that authenticates cleanly yet lacks the required endpoint scope receives **HTTP 403 Forbidden**:

```text
Valid JWT:
  iss = trustedIssuer
  aud = orders-api
  exp unexpired
  scope = orders.read

Request:
  POST /api/orders

Policy:
  POST requires SCOPE_orders.write

=> Authentication succeeds, authorization denies.
```

Never push business permissions indiscriminately into issuer/audience validators so that every missing permission turns into `invalid_token`. Separating **non-conforming token** from **valid token lacking operation permission** keeps `401` and `403` clear for both API and clients.

JWT validator error messages should be informative enough for operations without including raw tokens, secret keys, full personal claims, or overly granular verification internals in client responses.

## 13. Testing Validators Condition by Condition

To prove a composition matches requirements, separate **validator unit tests** from **full JWT decoder / filter-chain integration tests**.

### 13.1. Unit Test: Validating a Constructed `Jwt`

Example building a synthetic `Jwt` directly for the validator chain:

```java
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;

import static org.assertj.core.api.Assertions.assertThat;

class JwtClaimsValidatorTest {

    private final String issuer =
        "https://idp.example.com/realms/shop";

    private final OAuth2TokenValidator<Jwt> validators =
        new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(issuer),
            new RequiredAudienceValidator("orders-api")
        );

    private Jwt token(
            String actualIssuer,
            List<String> audiences,
            Instant expiresAt) {
        Instant now = Instant.now();
        return Jwt.withTokenValue("test-token")
            .header("alg", "RS256")
            .claim("iss", actualIssuer)
            .claim("sub", "user-842")
            .audience(audiences)
            .issuedAt(now.minusSeconds(60))
            .notBefore(now.minusSeconds(60))
            .expiresAt(expiresAt)
            .build();
    }

    @Test
    void acceptsCorrectIssuerAudienceAndTime() {
        Jwt jwt = token(
            issuer,
            List.of("orders-api"),
            Instant.now().plusSeconds(300));

        assertThat(validators.validate(jwt).hasErrors()).isFalse();
    }

    @Test
    void rejectsWrongAudience() {
        Jwt jwt = token(
            issuer,
            List.of("payments-api"),
            Instant.now().plusSeconds(300));

        assertThat(validators.validate(jwt).hasErrors()).isTrue();
    }

    @Test
    void rejectsExpiredToken() {
        Jwt jwt = token(
            issuer,
            List.of("orders-api"),
            Instant.now().minusSeconds(600));

        assertThat(validators.validate(jwt).hasErrors()).isTrue();
    }

    @Test
    void rejectsWrongIssuer() {
        Jwt jwt = token(
            "https://other-idp.example.com",
            List.of("orders-api"),
            Instant.now().plusSeconds(300));

        assertThat(validators.validate(jwt).hasErrors()).isTrue();
    }
}
```

These tests prove only that **the validator over a `Jwt` object** enforces those conditions. The token string `"test-token"` has no real signature. This is **not** a test of cryptography, JWKS discovery, HTTP Bearer parsing, or the full Resource Server.

Time-testing note: `JwtTimestampValidator` may allow a default clock skew; to test expiration reliably, use a timestamp sufficiently far in the past rather than a few milliseconds past `now`. For validators with an injected `Clock`, use `Clock.fixed(...)` for deterministic boundary tests.

### 13.2. Integration Test: Real JWTs Flowing Through the Decoder

At the integration level, verify:

- Tokens signed by the test private key matching the trusted public key are accepted.
- Invalid signatures or disallowed algorithms are rejected.
- Wrong `iss` is rejected.
- Wrong `aud` is rejected even when the signature is valid.
- Expired `exp` or future `nbf` is rejected.
- Valid tokens lacking `SCOPE_orders.read` receive the expected authorization denial.
- Public and protected routes match the intended `SecurityFilterChain`.

Use a test-only signing key, a decoder pointing at test JWKS, or well-bounded test doubles. Never commit test private keys or real production tokens into docs or logs.

`SecurityMockMvcRequestPostProcessors.jwt()` is great for testing HTTP authorization with a mocked `JwtAuthenticationToken`, yet it can **bypass real signature and claim verification in `JwtDecoder`**. Calling `mockMvc.perform(...).with(jwt())` alone therefore does not prove your validator chain is wired into the Resource Server.

### 13.3. The "New Test Passes, Old Policy Breaks" Regression

A common regression when editing security code:

```text
Before change:
  expired token      -> 401
  wrong issuer token -> 401

After setting only audienceValidator:
  right audience, expired      -> unexpectedly accepted
  right audience, wrong issuer -> issuer check may be lost
```

This is a **replaced-validator regression**. Prevent it by keeping baseline requirements explicit and verifying that adding new claim checks leaves all legacy negative cases rejected.

## 14. Configuration Variants and Limits to Remember

### 14.1. Decoder Built Directly From Issuer

```java
NimbusJwtDecoder decoder =
    NimbusJwtDecoder.withIssuerLocation(trustedIssuer).build();

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(trustedIssuer),
        new RequiredAudienceValidator("orders-api")
    )
);
```

This is the classic pattern when the API manages its decoder and trusts one issuer.

### 14.2. Decoder Built From a Fixed JWKS URI

```java
NimbusJwtDecoder decoder =
    NimbusJwtDecoder.withJwkSetUri(trustedJwkSetUri).build();

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(trustedIssuer),
        new RequiredAudienceValidator("orders-api")
    )
);
```

Here both `trustedJwkSetUri` and `trustedIssuer` are application-managed. Never treat a JWKS URL extracted from a token as trusted. When pointing directly at a JWKS URI, adding an explicit issuer validator is essential.

### 14.3. Using `createDefault` Without an Issuer?

```java
OAuth2TokenValidator<Jwt> defaults =
    JwtValidators.createDefault();
```

This helper can fit a JWT contract that does not validate issuer the same way, or where another properly configured component already validates issuer. However, **for an OAuth 2.0 Resource Server trusting a specific Authorization Server**, dropping `iss` validation just for shorter code weakens the trust boundary.

Never swap `createDefaultWithIssuer(...)` for `createDefault()` in an API with a fixed issuer assuming both enforce the same policy.

### 14.4. Overriding the Decoder in the DSL Chain

```java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt.decoder(customDecoder)))
```

When specifying a decoder directly on the DSL, context/property defaults may no longer govern that chain's validators. In multi-chain apps, inspect each chain independently:

```text
/api/orders/**   -> JwtDecoder A -> issuer A + audience orders-api
/api/payments/** -> JwtDecoder B -> issuer B + audience payments-api
```

Never assume all chains share the same decoder or validator simply because YAML defines one `issuer-uri`.

### 14.5. Never Use a Custom Validator to Weaken Default Checks

A new validator meant to "accept when audience matches" must never bypass a bad issuer. Never write:

```text
if (aud == "orders-api") ACCEPT
else RUN_DEFAULT_VALIDATORS
```

That is dangerous **OR** logic: matching audience alone bypasses every other constraint. Composition must use **AND**, unless a security contract explicitly defines distinct token-type branches where each branch still runs complete verification.

## 15. Practical Scenarios and Right Decisions

### Scenario A — Adding Audience to an API

Initially:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
```

New requirement: `aud` must contain `orders-api`.

**Simple path:** use `spring.security.oauth2.resourceserver.jwt.audiences` if your Boot version supports it and no custom decoder replaces auto-config. **Custom path:** compose `createDefaultWithIssuer` + audience validator via `DelegatingOAuth2TokenValidator`. Never call `setJwtValidator(audienceOnly)`.

### Scenario B — Adding `tenant_id`

New requirement: access tokens must carry a `tenant_id` in the API's managed tenant set. Build a tenant validator and **compose** it with issuer/time/audience. Also check tenant in the database at the business layer; a token validator alone cannot solve every cross-tenant access rule.

### Scenario C — Token Has Unexpired `exp` Yet Stale `iat`

Add an `iat` max-age validator backed by `Clock`. Keep `JwtTimestampValidator` so `exp`/`nbf` continue to run. If `iat` is missing when required by profile, reject. Never use `iat` as a replacement for `exp`.

### Scenario D — Specifying `jwk-set-uri` to Avoid Startup Discovery

The API uses a pre-configured JWKS URI. Still keep issuer validation via `JwtValidators.createDefaultWithIssuer`. Key retrieval and issuer verification serve different purposes; never drop issuer validation merely because the key URI is explicit.

### Scenario E — Resource Server Accepting Multiple IdPs

Never rely on one `audience == orders-api` validator as a global trust anchor. Select decoders from a **trusted issuer allowlist**, retain per-issuer issuer/time/profile validators, and then enforce the API audience.

### Scenario F — Replacing `JwtDecoder` for JWE or Custom Formats

If you replace the decoder completely, every check—signature/decryption, issuer, audience, timestamps, and token type—must be enforced per contract. `JwtValidators.createDefaultWithIssuer` is a helpful claim validator, **not a substitute** for a trustworthy cryptographic JWE/JWS processor.

## 16. Common Mistakes

| Mistake | Consequence | Right Practice |
|---|---|---|
| `setJwtValidator(new AudienceValidator(...))` assuming defaults still run | Drops issuer/timestamp validators | Compose defaults + audience |
| Having `@Bean JwtDecoder` while assuming Boot auto-wires `audiences` into every decoder | Claim checks may be skipped | Wire validators explicitly in custom decoders |
| Setting only `jwk-set-uri` and thinking issuer is verified | Loses issuer boundary if `iss` is unchecked | Add an issuer validator per contract |
| Accepting ID tokens because signature and issuer match | Token substitution between OIDC client and API | Validate audience, token type, and profile |
| Matching audience by substring | Wrongly accepts lookalike resources | Match exact audience values |
| Using `scope` instead of audience | Tokens from other APIs can be misused | Validate `aud` independently of scopes |
| Treating `sub` as universal record ownership | Cross-user or cross-tenant data leak | Enforce owner/tenant checks in business services |
| Dropping `exp` because an `iat` age validator exists | Expired tokens may be accepted | Keep the timestamp validator |
| Dropping `nbf` when tuning clock skew | Premature tokens accepted | Keep not-before validation |
| Checking only `isAuthenticated` in services | Misinterprets anonymous or weak auth | Use explicit authorization and trust resolvers |
| Replacing type/profile validators with naive `typ` string checks | Cross-token confusion | Keep version/contract profile validators |
| Auto-configuring issuers from unverified `iss` | Trusts attacker's JWKS | Use a configured trusted-issuer allowlist |
| Using `@WithMockUser` and thinking `JwtDecoder` was tested | Bypasses signature/claim validation | Separate validator unit tests from decoder integration tests |
| Logging raw JWTs on validator failure | Leaks bearer credentials | Log metadata/generic reasons without tokens |

## 17. Design Checklist When Adding a Claim Check

A change like "also validate audience" should follow this order of reasoning:

1. **Read the current contract:** issuer, token profile, algorithms, JWKS, timestamps, audience, and existing defaults.
2. **Define the new requirement:** which claim, pass/fail criteria, and whether presence is mandatory.
3. **Check whether framework config supports it directly:** e.g., `spring.security.oauth2.resourceserver.jwt.audiences` in Boot.
4. **If customizing the decoder:** keep baseline validators using `JwtValidators.createDefaultWithIssuer(trustedIssuer)` where appropriate.
5. **Compose rather than replace:** use `DelegatingOAuth2TokenValidator<>(defaults, custom1, custom2, ...)`.
6. **Keep signature verification intact:** configure decoder/JWKS/algorithms from trusted sources, never unverified payloads.
7. **Separate business permissions:** claim validation rejects non-conforming tokens; HTTP/method/domain authorization handles missing permissions.
8. **Cover negative scenarios:** expired, not yet valid, wrong issuer, wrong audience, missing new claim, wrong token profile, missing scope.
9. **Observe without leaking credentials:** log safely without raw JWTs or secrets in errors.
10. **Verify against your version:** check default validators, builders, and auto-configuration behavior on your exact Spring Security/Boot version.

### 17.1. Decision Flowchart

```mermaid
flowchart TD
    A["Need a new claim check"] --> B{"Does Boot support a property directly<br/>and is decoder auto-configured?"}
    B -->|"Yes"| C["Configure the property"]
    B -->|"No"| D["Provide or customize JwtDecoder"]
    D --> E["Obtain default validators<br/>with trusted issuer"]
    E --> F["Write custom validator per contract"]
    F --> G["DelegatingOAuth2TokenValidator<br/>(defaults AND customs)"]
    G --> H["setJwtValidator(combined)"]
    C --> I["JWT authentication + HTTP authorization"]
    H --> I
    I --> J["Business authorization<br/>owner / tenant / object"]
```

When you truly must **modify a default validator itself** (such as timestamp validation with custom skew), inspect **every remaining default validator** in your exact version so none of the other safeguards get dropped in the new chain. That is an intentional exception—never the default way to add extra checks.

## 18. Summary

```text
JWT from HTTP request
    |
    v
Verify signature + trusted keys + allowed algorithms
    |
    v
Default claim validators (issuer, timestamps, profile per version)
    |
    AND
    |
    v
Custom claim validators (audience, tenant, max age...)
    |
    v
JwtAuthenticationToken
    |
    v
Scope/authority checks
    |
    v
Business permissions for the requested resource
```

**Most important takeaway: `NimbusJwtDecoder#setJwtValidator(...)` sets the active validator chain; it does not mean "append one validator to the end of the default list".** When extending an access token contract, preserve baseline validators with an appropriate helper like `JwtValidators.createDefaultWithIssuer(...)` and compose via `DelegatingOAuth2TokenValidator`.

New constraints strengthen security only when **all prior safeguards remain active**. Audience validation must never trade away issuer validation; tenant validation must never trade away expiration validation; token-type checks must never trade away signature verification; and even verified claims never replace resource-level authorization.

## References

- [Spring Security Reference — JWT Resource Server (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): configuring decoders and validators.
- [Spring Security Reference — OAuth 2.0 Resource Server (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): bearer token authentication flow.
- [Spring Security API — JwtValidators](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/JwtValidators.html): `createDefault`, `createDefaultWithIssuer`.
- [Spring Security API — NimbusJwtDecoder](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html): `setJwtValidator` and decoder builder.
- [Spring Security API — DelegatingOAuth2TokenValidator](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/DelegatingOAuth2TokenValidator.html): composing token validators.
- [Spring Security API — JwtTimestampValidator](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/JwtTimestampValidator.html): expiration and clock skew checks.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): standard claim definitions.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): issuer, audience, algorithms, and distinguishing JWT types.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): OAuth JWT access token profile and requirements.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): receiving bearer credentials and returning errors.
