# OAuth2TokenValidator and Preserving Default Checks When Customizing

## 1. Why Must Default Checks Be Preserved When Extending JWT Validation?

In a **Spring Security OAuth 2.0/OIDC Resource Server**, a **WebFlux** application receives a Bearer access token and validates it before granting an `Authentication` to the caller. For JWT access tokens, the key component is **`ReactiveJwtDecoder`**. The decoder does not merely parse the payload; it participates in JWS signature verification and enforces claim validation rules.

A common business requirement: the Resource Server only accepts access tokens intended for the `orders-api` API. A developer adds an audience validator:

```java
OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
        jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                                "invalid_token",
                                "Invalid audience",
                                null));
```

This validator checks only **`aud`**. If attached with:

```java
decoder.setJwtValidator(audienceValidator);
```

then in decoder versions/implementations using this setter, the call **replaces the current validator**, **rather than appending** the new rule onto existing checks. As a result, previously configured checks—such as **`exp`, `nbf`, or `iss`**—may no longer be in the validator chain the application expects.

This is distinct from JWS signature verification. The signature is still normally verified by the decoder at the JOSE layer, yet **a JWT with a valid signature does not mean it is unexpired or meant for the right issuer/resource**.

**The safe approach** is to construct the baseline validator set and combine it with the new validator:

```java
OAuth2TokenValidator<Jwt> defaults =
        JwtValidators.createDefaultWithIssuer(issuer);

decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
                defaults,
                audienceValidator));
```

This lesson explains the exact role of `OAuth2TokenValidator` in **WebFlux**, how to preserve baseline checks, how to add custom rules without weakening security, and how to test using JUnit, `StepVerifier`, and `WebTestClient`.

> **Core message:** When adding a security rule, **extend** the guaranteed contract—**never accidentally replace** existing security checks. In particular, `setJwtValidator(...)` does not mean "append a new validator."

## 2. Where Does JWT Validation Sit in WebFlux Architecture?

A request:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6...
```

The Servlet and WebFlux processing paths differ. In **WebFlux**, the typical model is:

```mermaid
flowchart TD
    CLIENT["HTTP client<br/>Authorization: Bearer JWT"] --> FILTER["AuthenticationWebFilter"]
    FILTER --> EXTRACT["ServerBearerTokenAuthenticationConverter"]
    EXTRACT --> MANAGER["JwtReactiveAuthenticationManager"]
    MANAGER --> DECODER["ReactiveJwtDecoder / NimbusReactiveJwtDecoder"]
    DECODER --> JOSE{"Valid JWS?<br/>alg, key, signature"}
    JOSE -->|"No"| BAD["Authentication failure<br/>usually 401 invalid_token"]
    JOSE -->|"Yes"| CLAIMS["OAuth2TokenValidator&lt;Jwt&gt;<br/>defaults + custom validators"]
    CLAIMS -->|"Failed"| BAD
    CLAIMS -->|"Passed"| AUTH["JwtAuthenticationToken + SCOPE_ authorities"]
    AUTH --> CONTEXT["Reactor SecurityContext"]
    CONTEXT --> POLICY["AuthorizationWebFilter / Method Security"]
    POLICY -->|"Missing permission"| FORBIDDEN["Usually 403 Forbidden"]
    POLICY -->|"Sufficient permission"| CONTROLLER["Handler / Service / Domain policy"]
```

The conceptual diagram highlights three distinct layers:

| Layer | Typical components | What is protected |
| --- | --- | --- |
| **JOSE / signature / trusted keys** | `NimbusReactiveJwtDecoder`, configured JWKS/public key, permitted algorithms | Was the token signed by a key the API trusts using the right algorithm and format? |
| **JWT claim validation** | `OAuth2TokenValidator<Jwt>`, `JwtValidators`, `DelegatingOAuth2TokenValidator` | Do `iss`, `exp`, `nbf`, `aud`, and business/profile claims satisfy the contract? |
| **Authorization** | `JwtAuthenticationConverter`, `SecurityWebFilterChain`, `@PreAuthorize`, domain policy | Does the authenticated principal have the required scopes/authorities and permissions on the specific resource? |

**A custom claim validator does not verify signatures**, and **a valid signature does not replace claim validation**. All three layers must succeed.

### 2.1. WebFlux Classes to Use Instead of Servlet Counterparts

| WebFlux | Servlet counterpart | Notes |
| --- | --- | --- |
| `SecurityWebFilterChain` | `SecurityFilterChain` | Reactive HTTP security chain. |
| `ServerHttpSecurity` | `HttpSecurity` | Security configuration DSL. |
| `JwtReactiveAuthenticationManager` | `JwtAuthenticationProvider` in typical flows | Turns Bearer JWT into Authentication. |
| `ReactiveJwtDecoder` | `JwtDecoder` | `decode(String)` returns `Mono<Jwt>`. |
| `NimbusReactiveJwtDecoder` | `NimbusJwtDecoder` | Nimbus-based JWT decoder with reactive API. |
| `ReactiveSecurityContextHolder` | `SecurityContextHolder` | Security context backed by Reactor Context. |

An interesting detail: **`OAuth2TokenValidator<Jwt>` is not a reactive interface**. Even though the decoder returns `Mono<Jwt>`, claim validators are usually written **synchronously**, taking a `Jwt` and returning an `OAuth2TokenValidatorResult`. `ReactiveJwtDecoder` integrates that validation step into the pipeline.

## 3. `OAuth2TokenValidator` and `OAuth2TokenValidatorResult`

A validator enforces **a policy**:

```java
public interface OAuth2TokenValidator<T extends OAuth2Token> {

    OAuth2TokenValidatorResult validate(T token);
}
```

For JWTs, use:

```java
OAuth2TokenValidator<Jwt> validator = jwt -> {
    // Inspect claims/metadata of the Jwt reaching the validator layer.
    return OAuth2TokenValidatorResult.success();
};
```

On failure:

```java
return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
                "invalid_token",
                "Access token violates API contract",
                null));
```

`OAuth2TokenValidatorResult` has two forms:

- **Success**: the token passed **this specific validator's rule**.
- **Failure**: returns one or more `OAuth2Error` instances, allowing the decoder to reject the token through the proper error mechanism.

Success **does not prove the token is completely valid** if other verification layers were omitted.

### 3.1. `OAuth2Error` Must Not Contain Sensitive Information

Avoid:

```java
// WRONG: exposing raw token or infrastructure details in error description.
new OAuth2Error(
        "invalid_token",
        "Signature failed for token=" + rawToken
                + "; jwks=https://internal-idp/keys",
        null);
```

Replace with a categorical description:

```java
new OAuth2Error(
        "invalid_token",
        "Access token does not satisfy API requirements",
        null);
```

Depending on handlers and the Spring Security version, descriptions from `OAuth2Error` may appear in `WWW-Authenticate`. Keep internal data in dedicated error codes/metrics, correlation IDs, and redacted logs.

### 3.2. Do Not Use a Validator to "Fix" a Token

A validator **evaluates**; it should never:

- Turn an untrusted issuer into a valid issuer.
- Overwrite `aud` to match the current API.
- Bump `exp` or ignore `nbf` when a token is expired or not yet active.
- Add `orders:admin` scope from a client-controlled claim.
- Swap the public key or accept `alg=none` to let a token pass.

If it fails the contract, **return failure**. If valid claim formats need normalization per an issuer's profile, design a dedicated, bounded claim conversion step while preserving all trust checks; never turn validation into arbitrary privilege granting.

## 4. What Do Baseline Checks Include?

In a standard JWT Resource Server, there are several minimum requirements:

| Requirement | Valid example | If failed | Who typically enforces it? |
| --- | --- | --- | --- |
| JWT/JWS format | Compact JWS with valid header/payload/signature | Reject | Decoder / JOSE processor. |
| Cryptographic signature | Valid JWS under trusted key | Reject | Decoder. |
| Permitted algorithm | Explicitly allowed JWS algorithm | Reject | Decoder configuration. |
| Key source | JWKS/public key from issuer/trust config | Reject | Decoder/key selector. |
| `exp` | Token has not passed expiration | Reject if expired | Timestamp validator. |
| `nbf` | Token has reached its effective time | Reject if not yet active | Timestamp validator. |
| `iss` | Matches configured issuer | Reject | Issuer validator. |
| `aud` | Contains Resource Server identifier | Reject if wrong | Audience validator/Boot config if supported. |
| Token type / profile | Proper access token, not confused with ID token | Reject per profile | JOSE header validation and/or token-profile validators. |
| Specific claims | `tenant_id`, `client_id`, `scope` if mandated by contract | Reject per contract | Custom validators. |

**Not every item in the table is automatically checked by a single `createDefaultWithIssuer` call.** That call provides the baseline for **default JWT claim checks and issuer**, but does not replace:

- Public key/JWKS and algorithm selection in the decoder.
- Matching Resource Server audience if not yet configured.
- Mandatory presence of `exp`, `sub`, `client_id`, or `tenant_id` when required by a specific token profile.
- Token-type checking (e.g., OIDC ID token vs. OAuth access token) per version and policy.
- Scope, owner/tenant, and business permission policies.

### 4.1. Expiration: `exp` and `nbf` Differ

`exp` is the time when the token is **no longer accepted**; `nbf` is the time **before which it must not be used**.

Example:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893456000
}
```

Timestamps are **Unix epoch seconds**. A token may have a valid signature yet be invalid in time.

`JwtTimestampValidator` permits reasonable **clock skew** to handle clock drift. Never add an arbitrarily huge skew, as that expands the window for expired or premature tokens.

### 4.2. Issuer Requires Exact Matching

Issuer identifier:

```text
https://login.example.test/realms/shop
```

Do not treat the following issuers as equivalent by default:

```text
https://login.example.test/realms/shop/
https://login.example.test/realms/shop-admin
http://login.example.test/realms/shop
```

`iss` is a claim representing a trust domain, not a URL for the API to arbitrarily normalize, prefix-match, or use to run discovery against whatever host a token submits.

### 4.3. Audience Must Match the Resource Identifier

`aud` can be a string or an array per RFC 7519. Using Spring's `Jwt.getAudience()`, the application receives a list of audiences via the `Jwt` API.

Example:

```json
{"aud": ["orders-api", "reporting-api"]}
```

If the API expects `orders-api`, a **membership** policy may accept this token, whereas a **single-audience** policy may reject tokens targeting multiple resources. Choose the policy based on the token issuance contract, not guesswork.

**Never use `String.contains("orders-api")` on raw `aud`**, because `orders-api-admin` would falsely match and a JSON array is not equivalent to an arbitrary substring.

## 5. `JwtValidators.createDefault` and `createDefaultWithIssuer`

Spring Security provides these factory methods on `JwtValidators`:

```java
OAuth2TokenValidator<Jwt> defaults =
        JwtValidators.createDefault();

OAuth2TokenValidator<Jwt> defaultsWithIssuer =
        JwtValidators.createDefaultWithIssuer(
                "https://login.example.test/realms/shop");
```

Semantic difference:

| Factory | Purpose | When to use |
| --- | --- | --- |
| `JwtValidators.createDefault()` | Builds the default JWT validators for the Spring Security version. | When issuer is validated at a separate **explicitly designed** layer or when composing an explicit issuer validator alongside it. |
| `JwtValidators.createDefaultWithIssuer(issuer)` | Keeps default validators and adds an `iss` check against the trusted issuer. | Usually the best fit when the Resource Server accepts tokens from **a single known issuer**. |

In common Spring Security releases, default validators include `exp`/`nbf` checks via `JwtTimestampValidator`; other default components may evolve by version/token profile. Therefore, **do not hand-roll "just two validations" and call that the complete defaults**.

### 5.1. Why Version Matters

The default set in `JwtValidators` can expand as Spring Security adds token-type validation or new security rules. If a project writes manually:

```java
new DelegatingOAuth2TokenValidator<>(
        new JwtTimestampValidator(),
        new JwtIssuerValidator(issuer))
```

then although both validators are useful, this does not automatically inherit improvements added to **`JwtValidators.createDefaultWithIssuer`** when upgrading the framework.

**Prefer composing from the default factory**, then adding domain-specific checks. If an organization mandates a completely different profile, prove that every replaced check has an equivalent validator and test coverage.

### 5.2. What `createDefaultWithIssuer` Does Not Do

It does not:

- Sign access tokens.
- Obtain the Authorization Server's private key.
- Turn a JWT with an invalid signature into a valid one.
- Guarantee the token carries the API's audience without an appropriate audience validator.
- Verify order ownership, tenant membership, or business scopes.
- Prove every token is an **OAuth 2.0 access token** rather than an OIDC ID token if token-type/profile validation has not been configured.

Each of those belongs to a separate trust boundary.

## 6. Common Mistake: `setJwtValidator` Drops Baseline Checks

Suppose the application builds a decoder:

```java
NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder
                .withIssuerLocation(ISSUER)
                .build();
```

And then adds a custom audience check:

```java
// RISKY: Replaces the existing validator with only the audience validator.
decoder.setJwtValidator(jwt ->
        jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                                "invalid_token",
                                "Audience mismatch",
                                null)));
```

If the decoder no longer runs timestamp/issuer validators because the setter replaced them, a JWT like:

```json
{
  "iss": "https://evil.example.test",
  "aud": ["orders-api"],
  "exp": 1609459200,
  "scope": "orders:read"
}
```

could pass **the audience validator alone**, despite the wrong issuer or past expiration. A forged signature would still be rejected by the JOSE layer, yet a token signed by a key in a misconfigured trust setup or an old validly signed token becomes a serious security issue.

**Do not conclude from this example that any `iss=evil.example.test` token will authenticate**: actual behavior still depends on trusted JWKS, algorithms, token type, and other decoder checks. What this illustrates is **losing required claim checks when replacing the validator**, not forging valid signatures.

### 6.1. Fix with `DelegatingOAuth2TokenValidator`

```java
OAuth2TokenValidator<Jwt> defaults =
        JwtValidators.createDefaultWithIssuer(ISSUER);

OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
        jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                                "invalid_token",
                                "Access token is not for this API",
                                null));

decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
                defaults,
                audienceValidator));
```

Thus, audience is purely an **additional condition**. A token must pass **both default/issuer validators and the audience validator**.

### 6.2. Why Not Call `oldValidator.validate(...)` Manually?

Custom example:

```java
OAuth2TokenValidator<Jwt> composite = jwt -> {
    OAuth2TokenValidatorResult base = defaults.validate(jwt);
    if (base.hasErrors()) {
        return base;
    }
    return audienceValidator.validate(jwt);
};
```

Conceptually this can work if carefully written, but `DelegatingOAuth2TokenValidator` is already Spring Security's built-in component for combining validators and aggregating error results. There is no need to write custom control flow, exception semantics, or error aggregation unless you have a special requirement.

## 7. Complete WebFlux Example: `ReactiveJwtDecoder` Keeping Defaults, Adding Audience and Tenant

Suppose `orders-api`'s contract states:

1. Accept only tokens issued by `https://login.example.test/realms/shop`.
2. The JWT must carry a trusted signature with an algorithm allowed by decoder policy.
3. The token must not be expired and must satisfy `nbf`.
4. `aud` must **explicitly contain** `orders-api`.
5. The multi-tenant API requires `tenant_id` to be a non-blank string matching expected syntax.
6. Specific endpoints require scopes such as `orders:read` and `orders:write`.

### 7.1. Properties Configuration

```yaml
security:
  orders:
    issuer: https://login.example.test/realms/shop
    jwk-set-uri: https://login.example.test/realms/shop/protocol/openid-connect/certs
    audience: orders-api
```

These are **illustrative application-specific properties**, not default `spring.security.*` keys. The JWKS URL is an example only; obtain the real URL from issuer metadata/AS documentation and enforce TLS/trust.

### 7.2. Decoder and Validators

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
public class OrdersJwtDecoderConfiguration {

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder(
            @Value("${security.orders.issuer}") String issuer,
            @Value("${security.orders.jwk-set-uri}") String jwksUri,
            @Value("${security.orders.audience}") String audience) {

        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder
                        .withJwkSetUri(jwksUri)
                        .build();

        OAuth2TokenValidator<Jwt> defaults =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> expectedAudience = jwt ->
                jwt.getAudience().contains(audience)
                        ? OAuth2TokenValidatorResult.success()
                        : failure("Unexpected audience");

        OAuth2TokenValidator<Jwt> tenantClaim = jwt -> {
            Object raw = jwt.getClaims().get("tenant_id");

            if (raw instanceof String value
                    && !value.isBlank()
                    && value.matches("[a-zA-Z0-9_-]{1,64}")) {
                return OAuth2TokenValidatorResult.success();
            }

            return failure("Invalid tenant claim");
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        defaults,
                        expectedAudience,
                        tenantClaim));

        return decoder;
    }

    private static OAuth2TokenValidatorResult failure(String reason) {
        return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                        "invalid_token",
                        reason,
                        null));
    }
}
```

In this example:

- `withJwkSetUri(jwksUri)` specifies the trusted JWKS endpoint for signature verification; this URI alone **does not turn on an issuer claim validator**.
- `JwtValidators.createDefaultWithIssuer(issuer)` preserves default checks and requires `iss` to match the issuer.
- `expectedAudience` adds an exact `aud` check via `List.contains`.
- `tenantClaim` is an **application-specific** rule, not a JWT standard. If workload tokens lack `tenant_id` per contract, build a distinct policy rather than forcing all tokens to carry this claim.
- `DelegatingOAuth2TokenValidator` composes all conditions.
- `setJwtValidator(...)` is called **once**, with the **entire** intended validator chain.

**The example does not implement** per-order ownership checks; that belongs to domain authorization.

### 7.3. Wiring the Decoder into `SecurityWebFilterChain`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class OrdersSecurityConfiguration {

    @Bean
    SecurityWebFilterChain api(
            ServerHttpSecurity http,
            ReactiveJwtDecoder reactiveJwtDecoder) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .pathMatchers(HttpMethod.POST, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:write")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
                        jwt.jwtDecoder(reactiveJwtDecoder)))
                .build();
    }
}
```

These two configurations work **together**: the decoder bean and the WebFlux security chain. When the API already exposes a `ReactiveJwtDecoder` bean, the DSL can use the auto-detected bean instead of passing it explicitly; here it is explicit so readers can clearly see which validator chain is used.

### 7.4. What About Automatic Boot `issuer-uri` Configuration?

A concise option when no custom decoder is needed:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
```

Boot/Spring Security can auto-configure a `ReactiveJwtDecoder` with validation matching `issuer-uri`. However, once you **define your own decoder bean**, auto-configuration may **back off**; from that point on, the application itself must ensure all validators are configured completely.

Some Spring Boot lines support an audience property for JWTs. When using that property, verify your Boot version and its effect when a custom decoder bean is present. **Do not assume Boot will "secretly append" issuer/audience properties onto a custom decoder.**

## 8. Organizing Validators into a Reusable Factory

In larger projects, validation logic does not have to live inside a `@Bean` method. You can define a factory with a clear contract:

```java
public final class OrdersJwtValidationPolicy {

    private OrdersJwtValidationPolicy() {
    }

    public static OAuth2TokenValidator<Jwt> build(
            String issuer,
            String audience) {

        OAuth2TokenValidator<Jwt> defaults =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> apiAudience = jwt ->
                jwt.getAudience().contains(audience)
                        ? OAuth2TokenValidatorResult.success()
                        : invalid();

        OAuth2TokenValidator<Jwt> subjectRequired = jwt ->
                jwt.getSubject() != null
                        && !jwt.getSubject().isBlank()
                        ? OAuth2TokenValidatorResult.success()
                        : invalid();

        return new DelegatingOAuth2TokenValidator<>(
                defaults,
                apiAudience,
                subjectRequired);
    }

    private static OAuth2TokenValidatorResult invalid() {
        return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                        "invalid_token",
                        "JWT does not match the resource contract",
                        null));
    }
}
```

Usage:

```java
decoder.setJwtValidator(
        OrdersJwtValidationPolicy.build(ISSUER, "orders-api"));
```

Advantages:

- Every decoder is constructed with **one centrally defined validator chain**.
- Nobody accidentally calls `setJwtValidator(audienceOnly)` in another config branch.
- Unit testing the validation policy is decoupled from networking/JWKS.
- Multi-issuer/multi-resource setups can instantiate distinct policies per trust domain.

**Never use a global static mutable validator/allowlist** that a tenant or HTTP client can alter. The policy must take trusted configuration and never trust issuer/audience hints from unverified tokens.

## 9. How to Require `exp`, `sub`, or Another Claim?

**"Default timestamp checking" and "requiring a claim to exist" are not always the same requirement.** Depending on token profile, a validator may verify `exp` when present, while a strict profile such as JWT access tokens requires `exp` to be mandatory.

Example validator requiring `exp`:

```java
OAuth2TokenValidator<Jwt> expirationRequired = jwt ->
        jwt.getExpiresAt() != null
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                                "invalid_token",
                                "Expiration is required",
                                null));
```

When requiring `exp`, still keep `JwtValidators.createDefaultWithIssuer(...)` to **validate the timestamp value**. Merely seeing `exp` present does not mean the token is unexpired.

Similarly, you can require `sub`:

```java
OAuth2TokenValidator<Jwt> subjectRequired = jwt ->
        jwt.getSubject() != null
                && !jwt.getSubject().isBlank()
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                                "invalid_token",
                                "Missing subject",
                                null));
```

### 9.1. Do Not Mechanically Require `sub` for Every Client Credentials Token

In OAuth 2.0, **machine-to-machine (M2M)** tokens may carry a subject/actor under a different contract than end-user tokens. Some JWT access token profiles still include `sub`, yet the meaning of the principal depends on the grant/client.

Before requiring `sub`, `tenant_id`, or `email_verified`, determine:

- Is this token **representing an end user** or a **service/workload**?
- Does `sub` identify a user, a client, or an intermediary entity?
- What are the token's issuer and token profile?
- Does the API allow multiple actor types on the same endpoint?
- Which claims are needed to authorize access on this resource?

**A validator misaligned with the contract can reject valid tokens**, while an overly permissive validator can cause privilege escalation. Both risks must be managed through tests.

### 9.2. Do Not Require `email` as a Substitute for Subject

Claims like `email`, `name`, and `preferred_username` can change over time. Never use email as a stable user key without an explicit contract. With multiple issuers, external identity generally needs to be bound to the **verified issuer and subject**, then mapped to an internal user ID.

## 10. `JwtClaimValidator`: Convenient When Used Correctly

Spring Security provides `JwtClaimValidator<T>` to validate a single claim with a predicate.

Example:

```java
JwtClaimValidator<String> tenantValidator =
        new JwtClaimValidator<>(
                "tenant_id",
                tenant -> tenant != null
                        && !tenant.isBlank()
                        && tenant.matches("[a-zA-Z0-9_-]{1,64}"));
```

This pattern is convenient when you **know the data type** the claim has been converted to by the decoder/claim converter and have a clear contract. In systems that must reject JSON numbers/objects/lists in `tenant_id`, a custom validator checking `raw instanceof String` can be easier to inspect.

### 10.1. Do Not Arbitrarily Loosen Types

Suppose the issuer commits to:

```json
{
  "tenant_id": "tenant-a"
}
```

Do not silently accept:

```json
{"tenant_id": 123}
```

or:

```json
{"tenant_id": {"value": "tenant-a"}}
```

and call `toString()` to produce a valid tenant ID. For claims used in authorization, **the JSON type is part of the contract**.

### 10.2. Claim Conversion Is a Separate Step

A `JwtDecoder` can use a claim set converter to normalize standard claim types such as timestamps or audience. When customizing claim conversion, maintain safe rules:

- Never overwrite `iss`/`aud` with values the API expects.
- Never turn an untrusted user-supplied claim into a high-privilege role.
- Never strip `exp`/`nbf` before validators run.
- Never merge claims from multiple sources without clear precedence.

**Contract-compliant type conversion** differs from **rewriting a token to bypass validation**.

## 11. Be Careful with Clock Skew

The clocks of the Resource Server and Authorization Server may drift slightly. `JwtTimestampValidator` supports **clock skew**, commonly defaulting to around **60 seconds** in several Spring Security lines. Any clock skew setting must reflect **version and policy**.

Example when custom skew is required:

```java
JwtTimestampValidator timestamps =
        new JwtTimestampValidator(Duration.ofSeconds(30));
```

Do not do this:

```java
// WRONG: excessively wide skew accepts long-expired tokens.
new JwtTimestampValidator(Duration.ofDays(365));
```

### 11.1. Does Changing Clock Skew While Keeping Defaults Cause a Conflict?

If you write:

```java
new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        new JwtTimestampValidator(Duration.ofSeconds(30)))
```

you may be running **two timestamp validators**: one inside defaults and one with 30-second skew. If the two validators have different thresholds, a token must pass **both**. That **does not mean you reconfigured the default validator's skew**.

When you genuinely need to change clock skew, construct an **equivalent, consistent baseline** for your framework version, or use a configuration/extension point supported by that version. Never drop defaults just to tweak one parameter; if replacement is unavoidable, identify every baseline validator that must be retained and test thoroughly.

### 11.2. Never Rely on Client-Supplied Time

`exp`, `iat`, and `nbf` are issuer-issued claims. Never let an HTTP client send `X-Current-Time` for the Resource Server to treat as real time during validation. In tests, a fixed `Clock` or relatively computed timestamps can be used, but production must rely on a trusted system clock.

## 12. JWT Access Token Differs from OIDC ID Token

In an OpenID Connect system:

- An **ID token** proves a user authentication event to the **OIDC client**, typically with `aud` set to the **client ID**.
- An **OAuth 2.0 access token** is a credential checked by the **Resource Server** to permit API access, with a different issuer/resource/scope contract.

Verifying only signature and `iss` is **not enough** to make an ID token valid as an API access token. Example:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "aud": "web-client-id",
  "sub": "user-123",
  "exp": 1893456000
}
```

The token above may be a genuine ID token intended for the OIDC client. `orders-api` must check `aud` or a contract-defined resource-binding mechanism to reject it.

### 12.1. `typ` and RFC 9068

If the issuer implements **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens**, tokens typically include a JOSE `typ` header identifying the access-token profile, such as `at+jwt` per standard rules. Type validation involves **the header and decoder**, not only payload claims.

Points to remember:

- How Spring Security/Nimbus checks `typ` by default **depends on version and decoder builder**.
- Newer versions provide APIs/validators for type validation; check the Javadoc for your exact version.
- If a version lets you disable JOSE-layer type verification in favor of a custom profile validator, **do so only when the replacement validator is explicitly configured** and tested with valid/invalid token types; never simply disable the check and ignore it.
- `JwtValidators.createDefaultWithIssuer` does not replace a **complete token-profile policy** in all systems.

**Do not treat `typ=JWT`, `typ=at+jwt`, or missing `typ` as equivalent** if the issuer contract requires distinguishing access tokens from ID tokens.

### 12.2. Which Claims Does the Profile Require?

RFC 9068 specifies conditions for issuer, subject, audience, expiry, client ID, and scopes in appropriate contexts. Yet not every JWT access token claims RFC 9068 compliance. Before enforcing validators:

1. Confirm which profile the AS issues tokens under.
2. Confirm which token profile the Resource Server accepts.
3. Identify which claims are mandatory.
4. Choose matching decoder/header validators.
5. Add negative tests with an ID token, wrong `typ`, wrong `aud`, and missing mandatory claims.

## 13. Failure Modes When Replacing the Decoder Bean or DSL Config

### 13.1. A Custom Bean Causes Boot to Back Off

When a project has only:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
```

Boot can build a decoder from issuer metadata. Yet once you add:

```java
@Bean
ReactiveJwtDecoder jwtDecoder() {
    return NimbusReactiveJwtDecoder
            .withJwkSetUri("https://login.example.test/keys")
            .build();
}
```

the application has taken ownership of decoder configuration. Without `JwtValidators.createDefaultWithIssuer(...)`, the issuer validator you expected from properties may **no longer be applied** to this bean.

### 13.2. DSL Overriding the Bean Decoder

A chain might explicitly specify:

```java
.oauth2ResourceServer(oauth2 ->
        oauth2.jwt(jwt -> jwt.jwtDecoder(customDecoder)))
```

In that case, verify that **`customDecoder`** has the right validator chain; inspecting a different `ReactiveJwtDecoder` bean in the context does not prove the chain is using it.

### 13.3. Wrong JWKS URI

Using `withJwkSetUri(uri)` only defines the key source; it does not prove the issuer claim is valid. Multiple tenants/issuers may share an endpoint or public key material. Always bind the trust domain by issuer **and** audience when the contract requires it.

### 13.4. Creating a Decoder from an Unverified Token's `iss`

Do not do this:

```java
// WRONG: attacker supplies an issuer URL in an unverified payload.
String iss = parseUnverifiedPayload(token).get("iss").toString();
ReactiveJwtDecoder decoder =
        ReactiveJwtDecoders.fromIssuerLocation(iss);
```

This risks SSRF and fetching keys from untrusted parties. For multi-issuer setups, use an explicit issuer allowlist and a properly designed resolver; once a decoder is chosen, **still verify signature, issuer, and audience**.

## 14. Multi-Issuer in WebFlux: Each Issuer Needs Its Own Defaults and Policy

Suppose the API accepts:

```text
Issuer A = https://idp-a.example.test/issuer
Issuer B = https://idp-b.example.test/issuer
```

Spring Security provides `JwtIssuerReactiveAuthenticationManagerResolver` to select a reactive authentication manager from a set of trusted issuers:

```java
JwtIssuerReactiveAuthenticationManagerResolver resolver =
        JwtIssuerReactiveAuthenticationManagerResolver
                .fromTrustedIssuers(
                        "https://idp-a.example.test/issuer",
                        "https://idp-b.example.test/issuer");
```

The resolver may read `iss` before the token is verified to **pick a candidate**, yet unverified data **is not proof of issuer**. After selection, the decoder must verify the signature and corresponding issuer.

### 14.1. Different Audiences per Issuer

If:

```text
Issuer A -> aud = orders-api
Issuer B -> aud = https://api.example.test/orders
```

you cannot blindly use one audience literal across all issuers. Define policy per issuer/resource:

```text
Trusted issuer A
    -> trusted JWKS A
    -> JwtValidators.createDefaultWithIssuer(A)
    -> audience validator "orders-api"

Trusted issuer B
    -> trusted JWKS B
    -> JwtValidators.createDefaultWithIssuer(B)
    -> audience validator "https://api.example.test/orders"
```

A default resolver that only selects trusted issuers **does not automatically add custom audience validators**. If multiple audiences are required, inspect how the resolver constructs its managers/decoders and add custom policies via the appropriate extension point.

### 14.2. Do Not "Union" Permissions Across Different Sources

Issuer A has `scope="orders:read"`, Issuer B has `scp=["orders.read"]`. Never assume `orders.read` equals `orders:read` or grant `ROLE_ADMIN` without a mapping contract. Validators enforce the token profile, converters map authorities per issuer/client contract, and domain authorization enforces owner/tenant.

## 15. Negative Tests: Tokens That Must Be Rejected

A **test matrix** helps catch cases where a setter drops baseline validators:

| Test token | JWS signature | Important claims | Expected authentication |
| --- | --- | --- | --- |
| Valid token | Valid, trusted key | Valid `iss`, valid `aud`, future `exp`, valid `nbf` | Succeeds. |
| Expired token | Valid, trusted key | `exp` sufficiently past clock skew | **Rejected**. |
| Not-yet-valid token | Valid, trusted key | `nbf` sufficiently in future beyond skew | **Rejected**. |
| Wrong issuer token | Valid per test trust setup | `iss` does not match API's issuer | **Rejected**. |
| Wrong audience token | Valid | `aud=["payments-api"]` | **Rejected**. |
| Missing audience when contract requires it | Valid | No `aud` | **Rejected**. |
| Lookalike audience token | Valid | `aud=["orders-api-admin"]` | **Rejected**. |
| Invalid signature token | Invalid or untrusted key | Other claims look valid | **Rejected at decoder**. |
| `alg=none` token | No valid JWS signature | Claims look valid | **Rejected**. |
| Token missing mandatory `exp` per profile | Valid | No `exp` | **Rejected if contract requires it**. |
| Wrong tenant token | Valid | `tenant_id` wrong type/format | **Rejected per custom policy**. |
| OIDC ID token sent as access token | Possibly valid | `aud=client-id`, wrong type/profile | **Rejected**. |
| Valid auth token missing scope | Valid | Missing `orders:read` | Authentication may succeed; endpoint **403**. |

A negative test is only meaningful when you know **which path is being exercised**:

- Validator unit tests prove the claim predicate functions.
- Decoder unit tests prove validator wiring/JOSE signatures with a real decoder or controlled test double.
- WebFlux integration tests prove the HTTP Bearer filter, decoder, authorization, and response.

Never use `mockJwt()` and claim signature, `exp`, or `iss` were tested.

## 16. Unit Testing Validators with JUnit: Combining Defaults with Audience

You can test the policy factory **without** an HTTP server or Spring context.

JUnit Jupiter example (assuming `OrdersJwtValidationPolicy` from Section 8):

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;

class OrdersJwtValidationPolicyTest {

    private static final String ISSUER =
            "https://login.example.test/realms/shop";

    private final OAuth2TokenValidator<Jwt> policy =
            OrdersJwtValidationPolicy.build(
                    ISSUER, "orders-api");

    private Jwt jwt(
            String issuer,
            String audience,
            Instant expiration,
            Instant notBefore) {

        Instant now = Instant.now();
        return Jwt.withTokenValue("unit-test-only")
                .header("alg", "RS256")
                .issuer(issuer)
                .subject("user-123")
                .audience(List.of(audience))
                .issuedAt(now.minusSeconds(10))
                .notBefore(notBefore)
                .expiresAt(expiration)
                .build();
    }

    @Test
    void acceptsValidClaims() {
        Instant now = Instant.now();
        assertTrue(policy.validate(jwt(
                ISSUER, "orders-api",
                now.plusSeconds(300),
                now.minusSeconds(10))).getErrors().isEmpty());
    }

    @Test
    void rejectsExpiredTokenEvenWhenAudienceMatches() {
        Instant now = Instant.now();
        assertFalse(policy.validate(jwt(
                ISSUER, "orders-api",
                now.minusSeconds(3600),
                now.minusSeconds(7200))).getErrors().isEmpty());
    }

    @Test
    void rejectsNotYetValidToken() {
        Instant now = Instant.now();
        assertFalse(policy.validate(jwt(
                ISSUER, "orders-api",
                now.plusSeconds(7200),
                now.plusSeconds(3600))).getErrors().isEmpty());
    }

    @Test
    void rejectsWrongIssuerEvenWhenAudienceMatches() {
        Instant now = Instant.now();
        assertFalse(policy.validate(jwt(
                "https://another.example.test/issuer", "orders-api",
                now.plusSeconds(3600),
                now.minusSeconds(10))).getErrors().isEmpty());
    }

    @Test
    void rejectsWrongAudienceEvenWithValidTimeAndIssuer() {
        Instant now = Instant.now();
        assertFalse(policy.validate(jwt(
                ISSUER, "payments-api",
                now.plusSeconds(3600),
                now.minusSeconds(10))).getErrors().isEmpty());
    }
}
```

This is a **unit test of `OAuth2TokenValidator`**. The token `unit-test-only` has no JWS signature; `Jwt.withTokenValue(...)` simply builds an in-memory object. Unit tests do not prove `NimbusReactiveJwtDecoder` verified signatures or had `setJwtValidator(policy)` configured.

### 16.1. A Test That "Catches Dropped Defaults"

If someone changes the factory to:

```java
return audienceValidator; // WRONG: drops defaults and issuer.
```

then `rejectsExpiredTokenEvenWhenAudienceMatches`, `rejectsNotYetValidToken`, and `rejectsWrongIssuerEvenWhenAudienceMatches` will fail. That is the value of **negative tests protecting invariants**, rather than testing only valid tokens.

### 16.2. Use a Fixed Clock If Tests Assert Exact Second Boundaries

The example tests use `Instant.now()` with offsets of several minutes/hours to stay well clear of clock skew. When testing exact `exp`/`nbf` boundaries, use `Clock.fixed(...)` with a timestamp validator supporting a clock extension point in your version, or design a clock-injected test fixture. Do not assert that a token expired by **1 millisecond** is always rejected when the validator allows clock skew.

## 17. Testing the Reactive Decoder with `StepVerifier`

`ReactiveJwtDecoder.decode(String)` returns `Mono<Jwt>`. `StepVerifier` lets you verify the emitted item or error:

```java
Mono<Jwt> decoded = reactiveJwtDecoder.decode(signedTestJwt);

StepVerifier.create(decoded)
        .expectNextMatches(jwt ->
                "user-123".equals(jwt.getSubject())
                && jwt.getAudience().contains("orders-api"))
        .verifyComplete();
```

For an invalid token:

```java
StepVerifier.create(
        reactiveJwtDecoder.decode(signedExpiredTestJwt))
        .expectError(JwtException.class)
        .verify();
```

For security-meaningful tests, `signedTestJwt` and `signedExpiredTestJwt` must be JWS strings signed by the **test private key** matching the test decoder's trusted public key/JWKS. Never use production tokens/production private keys.

### 17.1. Building a Test Decoder with a Trusted Public Key

Skeleton example:

```java
RSAPublicKey publicKey = /* public key of test key pair */;

NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder
                .withPublicKey(publicKey)
                .build();

decoder.setJwtValidator(
        OrdersJwtValidationPolicy.build(
                "https://issuer.test", "orders-api"));
```

Here the keypair is strictly for testing; test JWTs must be signed with the corresponding private key. When the `JwtDecoder` uses a public key directly, the test removes HTTP/JWKS variables and focuses on **signature + claims + validator wiring**.

### 17.2. Separating Signature Failures from Claim Failures

Two cases must remain distinct:

1. Invalid JWS signature while `iss`/`aud`/`exp` in the payload look valid → rejected at JOSE verification.
2. Valid JWS signature while `exp` is expired or `aud` is wrong → rejected at claim validation.

If you test only the first group, the application can still suffer from **`setJwtValidator(audienceOnly)`** undetected.

### 17.3. Do Not Test with a Lambda Decoder That Always Succeeds

```java
ReactiveJwtDecoder fake = token ->
        Mono.just(jwtFixture);
```

A fake can help test how `JwtReactiveAuthenticationManager` turns a `Jwt` into an `Authentication`, but it **bypasses every real decoder mechanism**, including signatures and validators. You cannot use that fake to conclude JWT security is properly configured.

## 18. `WebTestClient`: Verifying HTTP 401 and 403

A WebFlux application has an endpoint:

```java
@RestController
class OrderController {

    @GetMapping("/api/orders")
    public Flux<OrderDto> listOrders() {
        return orderService.listVisibleOrders();
    }
}
```

Suppose `SecurityWebFilterChain` requires `SCOPE_orders:read`. Testing must distinguish:

| Condition | Authentication | Authorization | Typical HTTP |
| --- | --- | --- | --- |
| No token | No authenticated principal | Endpoint requires auth | **401**. |
| JWT with bad signature | Fails | Does not reach domain | **401 invalid_token**. |
| Expired JWT | Fails if defaults are still active | Does not reach domain | **401 invalid_token**. |
| JWT with wrong issuer | Fails | Does not reach domain | **401 invalid_token**. |
| JWT with wrong audience | Fails | Does not reach domain | **401 invalid_token**. |
| JWT with valid issuer/aud/time, missing `orders:read` | Succeeds | Missing authority | **403 Forbidden**. |
| Valid JWT with `orders:read` scope | Succeeds | Passes URL rule | 2xx if domain succeeds. |
| Valid token with scope, wrong owner/tenant | Succeeds | Domain policy denies | **403/404** per API contract. |

### 18.1. HTTP Authorization Unit Tests with `mockJwt()`

Spring Security Test supports:

```java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;

webTestClient.mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders:read")))
        .get().uri("/api/orders")
        .exchange()
        .expectStatus().isOk();

webTestClient.mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders:write")))
        .get().uri("/api/orders")
        .exchange()
        .expectStatus().isForbidden();
```

These are **authorization tests**: `mockJwt()` creates a simulated Authentication. It **does not prove** `ReactiveJwtDecoder` or `OAuth2TokenValidator` ran.

### 18.2. Full Integration Through Real Bearer JWS

To verify that defaults remain intact:

1. Generate RSA/EC test keys and a test JWT encoder.
2. Configure a real `NimbusReactiveJwtDecoder` using the test public key/JWKS.
3. Attach the composite `JwtValidators.createDefaultWithIssuer + audience + custom` just like production.
4. Send HTTP `Authorization: Bearer <signed-test-JWS>` through `WebTestClient` with WebFlux security filters.
5. Test **valid JWS but expired** → 401.
6. Test **valid JWS but future `nbf`** → 401.
7. Test **valid JWS but wrong `iss`** → 401.
8. Test **valid JWS but wrong `aud`** → 401.
9. Test **valid JWS but missing `SCOPE_orders:read`** → 403.
10. Test **valid JWS, all claims valid, sufficient scope** → endpoint succeeds.

If using `@SpringBootTest(webEnvironment = RANDOM_PORT)`, use `WebTestClient`/live HTTP matching the test mode. With `bindToApplicationContext`, apply `springSecurity()` per the Spring Security Test guide. Never confuse mocked user/JWT HTTP tests with tests exercising the real decoder.

## 19. 401, 403 Errors and What Information Should Be Exposed

For a Bearer Resource Server:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

or:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

These headers are typical examples; the Spring Security handler, realm, and specific error conditions may produce slightly different output.

**Never return all validator errors** to the client. An issuer mismatch error need not disclose an internal issuer list. An audience mismatch error need not expose other tenants/resources. A `JwtValidationException` can contain multiple errors; internal telemetry should classify causes with redaction.

### 19.1. JWKS Unavailable Errors Differ from Expired Tokens

When the JWKS endpoint suffers network/TLS errors or the key cache lacks a new `kid`, the Resource Server cannot verify the token. **Do not fail open**. Still, distinguish them operationally:

- `JWT_EXPIRED`: valid signature, expired token.
- `JWT_ISSUER_INVALID`: claims do not match issuer.
- `JWT_AUDIENCE_INVALID`: resource mismatch.
- `JWKS_DEPENDENCY_UNAVAILABLE`: unable to obtain trusted metadata/keys.
- `JWT_SIGNATURE_INVALID`: invalid signature.

Do not treat every network outage as a user submitting forged tokens. The exact HTTP status on dependency unavailability depends on handlers; you may want safe 5xx/503 responses that remain fail-closed.

### 19.2. Do Not Echo Raw Token, `kid`, or JWKS URI

Avoid:

```java
new OAuth2Error(
        "invalid_token",
        "Invalid " + jwt.getTokenValue()
                + " at jwks=" + internalJwksUrl,
        null);
```

When errors require tracking, use correlation IDs and standardized categories. `kid` from an unverified JOSE header is caller-controlled data; never use it freely as a metric label due to cardinality risk.

## 20. WebFlux-Specific Performance Concerns

`OAuth2TokenValidator<Jwt>` is a synchronous contract. When applied inside `ReactiveJwtDecoder`, validator logic must be **fast, deterministic, and non-blocking**.

### 20.1. Do Not Query the Database Inside `validate()`

```java
// WRONG: synchronous DB call in a WebFlux validator.
OAuth2TokenValidator<Jwt> validator = jwt -> {
    boolean allowed =
            jdbcTemplate.queryForObject(
                    "select ...", Boolean.class);
    return allowed
            ? OAuth2TokenValidatorResult.success()
            : failure();
};
```

This can block threads executing the reactive pipeline. Never run DB queries, HTTP calls, large secret file reads, or `Thread.sleep` inside `validate`.

### 20.2. When Dynamic Tenant or User Permissions Are Needed

Split the two responsibilities:

1. **JWT validation**: stable rules such as signature, issuer, audience, `exp`/`nbf`, token type/profile, and claim syntax.
2. **Reactive authorization**: query actor/tenant permissions via a reactive repository or a custom reactive authorization manager/service policy.

Example:

```java
@PreAuthorize("hasAuthority('SCOPE_orders:read')")
public Mono<OrderDto> getOrder(UUID orderId) {
    return currentActorReactiveService.getActor()
            .flatMap(actor -> orders
                    .findByIdAndOwnerIdAndTenantId(
                            orderId,
                            actor.userId(),
                            actor.tenantId()))
            .map(OrderDto::from);
}
```

The domain types in the example must be defined by the application; `@PreAuthorize` in WebFlux requires **`@EnableReactiveMethodSecurity`** and calls passing through the Spring proxy. Object access should be scoped directly in the query rather than trusting `tenant_id` from an HTTP request.

**Never put blocking I/O inside `JwtClaimValidator` thinking an outer `Mono` automatically makes it non-blocking.**

## 21. When Should You Truly Replace a Baseline Check?

Occasionally, an organization has specific policies:

- Clock skew must be tighter than the default.
- Only accept tokens with a mandatory `exp`.
- Prohibit tokens issued with excessively long lifetimes.
- Require `iat` not to lie too far in the future.
- Access token profile must carry appropriate `typ` and `client_id`.
- Allow only specific issuer/resource audiences during a migration.

Still, **customizing is different from disabling security**.

### 21.1. Example: Limiting Lifetime

A token with `exp` far in the future may pass the timestamp validator, yet an API contract permits access tokens to live at most one hour.

```java
OAuth2TokenValidator<Jwt> maxLifetime = jwt -> {
    Instant issuedAt = jwt.getIssuedAt();
    Instant expiresAt = jwt.getExpiresAt();

    if (issuedAt == null || expiresAt == null) {
        return failure("Missing token lifetime");
    }

    Duration lifetime = Duration.between(issuedAt, expiresAt);

    if (lifetime.isNegative()
            || lifetime.compareTo(Duration.ofHours(1)) > 0) {
        return failure("Token lifetime violates API policy");
    }

    return OAuth2TokenValidatorResult.success();
};
```

This is an **optional custom policy**. If the AS has a different lifetime policy, do not mechanically impose one hour. What matters is using it **together with** defaults:

```java
decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audience,
                maxLifetime));
```

Even a valid lifetime is insufficient if the JWS signature or audience is wrong.

### 21.2. Custom `nbf`/`exp` Must Not Remove Other Checks

If timestamp validation must be redesigned for a different policy, list **all existing guarantees** and how to reproduce them in your framework version. Never do this:

```java
// WRONG: keeps only custom iat and drops default temporal/issuer checks.
decoder.setJwtValidator(customIssuedAtValidator);
```

Redesigning a baseline validator is a security architecture decision, not a quick tweak to "fix an expired token test."

## 22. Troubleshooting JWT Validation Errors in WebFlux

| Symptom | Possible cause | How to diagnose |
| --- | --- | --- |
| JWT with valid `aud` yet expired is still accepted | `setJwtValidator(audienceOnly)` dropped timestamp defaults. | Inspect attached composite validator; add expired negative test. |
| JWT with valid signature and wrong `iss` passes | Used `withJwkSetUri` without issuer validator, or custom validator replaced defaults. | Verify `createDefaultWithIssuer` and which decoder the chain actually uses. |
| Unexpired token returns 401 | Wrong audience, issuer, `typ`/profile, `nbf`, or key/algorithm. | Check each phase in internal logs; do not assume `exp` is at fault. |
| JWT has `aud=["orders-api"]` yet API still returns 401 | Configured audience literal differs, role/scope unrelated to authn, or decoder does not trust signature. | Compare exact contract; verify JWS and audience validation. |
| Token with 30 seconds remaining fails test | Clock skew/clock timing behaves unexpectedly or another claim fails. | Use a test clock and isolate claim tests. |
| `mockJwt()` test passes yet production returns 401 | Mock bypasses decoder and validators. | Send real signed JWTs through `WebTestClient`. |
| Custom `ReactiveJwtDecoder` bean makes `issuer-uri` property "stop working" | Boot backed off; app must configure issuer validator itself. | Inspect bean/DSL, not just YAML. |
| Two decoders in context, which one runs? | DSL picks a different decoder than the tested bean. | Verify `jwtDecoder(...)` and actual security chain matcher. |
| JWT with wrong `kid` triggers many JWKS calls | Cache miss, key rotation, or malicious input. | Check trusted JWKS, refresh policy, rate limiting, metrics. |
| Authenticated yet request returns 403 | Insufficient scope/authority or domain policy denies. | Check `SCOPE_...` mapping and ownership; never edit `JwtValidator` to grant permissions. |
| Validator with JDBC call slows the API | Blocking I/O on reactive request path. | Move dynamic permission checks to reactive authorization/service. |
| ID token accepted by API as access token | Missing audience/type/profile validation. | Separate OIDC client audience from Resource Server audience; test `typ`/token profile. |

### 22.1. Verify the Actual Execution Path, Not Just Code Structure

When troubleshooting, verify:

1. Which **`SecurityWebFilterChain`** handles the request?
2. Which **`ReactiveJwtDecoder`** bean does that chain use?
3. Which issuer/JWKS does that decoder fetch keys from?
4. How many times is `setJwtValidator` called, and with which composite validator?
5. Are default/issuer checks included in the composite?
6. Are audience/token type/profile validated?
7. After authentication, what authorities are mapped?
8. Which permissions do endpoint/method/domain policies require?

Never patch security based purely on an HTTP 401 symptom without knowing whether it failed at signature, claims, or dependency level.

## 23. Design Scenarios

### A. Adding Audience Only for a New API

The API previously validated tokens via `issuer-uri`. When adding `aud=orders-api`, the validator configuration must **retain defaults + issuer**, then add audience. Expired/`nbf`/`iss` tests must still pass in the sense of **being rejected**.

### B. One Issuer Serving Multiple APIs

The issuer mints tokens for `orders-api` or `payments-api`. Both APIs may share the same JWKS yet must check **their own audience**. Never accept another API's token merely because the signature came from the same issuer.

### C. M2M Token Without `tenant_id`

A custom tenant validator requiring `tenant_id` on every JWT can reject a valid workload token. The fix is not deleting issuer/exp validators; instead, design a **dedicated token profile or authentication/authorization policy for service actors** while ensuring no privilege escalation path exists.

### D. OIDC ID Token Mistaken for an Access Token

An ID token may have valid signature, issuer, and timestamps, yet `aud` is `web-client-id`. The Resource Server must check audience/`typ`/profile so ID tokens are never used to authorize API access.

### E. Expired JWTs Slipping Through After a Refactor

A developer replaces `setJwtValidator(composite)` with `setJwtValidator(custom)` to reduce boilerplate. Validly signed expired tokens are no longer blocked by the timestamp validator. Negative unit and decoder integration tests must catch this regression.

### F. Wrong Issuer in a Multi-Tenant Identity Provider

A JWT from Tenant A cannot be used in Tenant B merely because they share public keys or audience names. Each tenant's decoder must check the issuer matching its trust domain and tenant/account linking policy.

### G. JWKS Server Temporarily Unreachable

A new token needs an uncached key, and the decoder cannot verify the JWS. Do not skip signature verification or fabricate a temporary principal. Monitor dependency failures, cache key metadata, and maintain a safe key rotation runbook.

### H. Valid Token, User Lacks Permission to Read the Order

`JwtValidators` all succeed and the token carries `SCOPE_orders:read`, yet `orderId` belongs to someone else. Domain authorization must still deny access; validators check only the access-token contract, not per-object permissions.

## 24. Self-Check Questions

**1. Does `OAuth2TokenValidator<Jwt>` verify JWS signatures?** No. Signatures/algorithms/trusted keys belong to the decoder/JOSE layer.

**2. What does `ReactiveJwtDecoder.decode(...)` return?** `Mono<Jwt>` for a decoder-accepted token, or an error signal when invalid.

**3. Why can `setJwtValidator(customAudience)` be dangerous?** The setter replaces the active validator, dropping default claim checks unless you compose them back in.

**4. Which factory is typically suitable for keeping baseline and issuer checks?** `JwtValidators.createDefaultWithIssuer(trustedIssuer)`.

**5. What do you use to combine multiple validators?** `DelegatingOAuth2TokenValidator<Jwt>`.

**6. Does `JwtValidators.createDefaultWithIssuer` automatically check the `orders-api` audience?** Do not assume so. Configure an audience validator per the API's contract.

**7. Does `withJwkSetUri(...)` automatically prove `iss` is valid?** No. Ensure issuer validation is added to the decoder.

**8. Is the mere presence of `exp` enough to prove a token is unexpired?** No. Timestamp validity and clock skew must be evaluated; claim presence differs from value validation.

**9. Why not check `aud` via substring matching?** Because `orders-api-admin` is not `orders-api`; exact membership in the audience list is required.

**10. Why don't `Jwt.withTokenValue` tests verify signatures?** They only construct an in-memory `Jwt` object without creating or verifying a JWS.

**11. Can `StepVerifier` test default issuer/expiry validators?** Yes, when running against a **properly configured real decoder**, not a lambda returning a fixed `Jwt`.

**12. Does `WebTestClient` `mockJwt()` prove full JWT validation?** No. It injects a simulated authentication for testing authorization.

**13. What HTTP status should a valid token lacking `SCOPE_orders:read` return?** Typically 403 from authorization, unlike 401 when a JWT is rejected at authentication.

**14. Can multi-issuer dynamically fetch metadata/JWKS from an unverified `iss`?** No. Only select issuers from an allowlist, then still verify signature and issuer.

**15. If database membership checking is needed, should a blocking query run inside the validator?** Not on a WebFlux request path. Move it to reactive authorization/service policy.

**16. Why not hand-build defaults from just a single `JwtTimestampValidator`?** You can miss issuer/type/other baseline checks introduced by the framework version.

**17. If you want to change default clock skew, is adding another `JwtTimestampValidator` enough?** Not quite; that can create two timestamp validators with different thresholds. Replace the baseline policy deliberately and carefully.

**18. When a validator error occurs, should raw JWTs and JWKS URLs be returned to the client?** No. Return only an appropriate Bearer error and keep details in secure telemetry.

## 25. References

- **Spring Security Reference — Reactive OAuth 2.0 Resource Server JWT:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- **Spring Security Reference — Reactive OAuth 2.0 Resource Server Multi-tenancy:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html
- **Spring Security API — JwtValidators:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtValidators.html
- **Spring Security API — NimbusReactiveJwtDecoder:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html
- **Spring Security API — JwtTimestampValidator:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtTimestampValidator.html
- **Spring Security API — JwtClaimValidator:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtClaimValidator.html
- **Spring Security API — DelegatingOAuth2TokenValidator:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/DelegatingOAuth2TokenValidator.html
- **Spring Security Reference — WebFlux Security Testing:** https://docs.spring.io/spring-security/reference/reactive/test/index.html
- **RFC 7519 — JSON Web Token (JWT):** https://www.rfc-editor.org/rfc/rfc7519
- **RFC 8725 — JSON Web Token Best Current Practices:** https://www.rfc-editor.org/rfc/rfc8725
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** https://www.rfc-editor.org/rfc/rfc9068
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** https://www.rfc-editor.org/rfc/rfc6750

## 26. Conclusion

In a **Spring Security WebFlux Resource Server**, `OAuth2TokenValidator<Jwt>` is the layer evaluating **JWT claims/token contracts** after JOSE verification. When adding audience, tenant, subject, lifetime, or token-profile rules, never accidentally overwrite baseline checks such as `exp`, `nbf`, and `iss`.

The standard, maintainable pattern is:

```java
decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator,
                customContractValidator));
```

Alongside this, ensure the decoder still verifies **signatures, algorithms, and trusted key sources**, URLs/issuers come from trusted configuration, audiences match the resource identifier, ID tokens are not confused with access tokens, and data access permissions are enforced at the authorization layer. **Validator unit tests**, **`StepVerifier` against a real decoder**, and **`WebTestClient` through the Bearer filter chain** are complementary testing layers. A new validator is only helpful when it makes constraints **stricter per contract**, without dropping conditions that already keep the API secure.
