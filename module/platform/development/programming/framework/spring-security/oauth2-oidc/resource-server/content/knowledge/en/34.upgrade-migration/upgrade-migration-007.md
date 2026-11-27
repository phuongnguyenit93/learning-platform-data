# Checking Default Changes for Algorithms, `typ`, and Validators

When upgrading a **Spring Security OAuth 2.0 / OIDC Resource Server**, you must inspect the JWT decoder across three independent layers: **JWS signature algorithm (`alg`), JOSE header type (`typ`), and the validator chain checking issuer/claims**. An application can still start and accept requests after upgrading while beginning to reject valid tokens because of how `typ` is validated. Conversely, a custom validator can inadvertently replace existing issuer or expiration checks.

For the Spring Security 6.5 branch preparing for 7.0, the key change is moving `typ` header validation from the Nimbus JOSE processor to `JwtTypeValidator`. In Spring Security 7, Nimbus no longer validates `typ` by default; `JwtValidators.createDefault...` factories add `JwtTypeValidator.jwt()` to the validator chain. That validator's default policy accepts `typ` equal to `JWT` or an absent `typ` header.

The default algorithm on `NimbusJwtDecoder` remains **RS256**. Therefore, do not assume upgrading to 7.0 automatically changes the signing algorithm. What you need to do is confirm the algorithm the issuer signs with, how the decoder is built (Boot issuer discovery vs. custom JWK Set URI), and the allowlist the Resource Server actually enforces.

This lesson belongs to the **Upgrade and Migration** chapter, using **Java 17+, Spring Boot 3.x/4.x, and Spring Security 6.5/7.x** as context. It explains the distinction between `alg`, `typ`, and JWT claims, how to prepare in 6.5, how to finalize migration in 7.x, RFC 9068 `at+jwt`, how to preserve default validators when adding audience/domain rules, and testing with real signed JWTs.

## 1. Three Validation Layers That Are Frequently Confused

A JWT Resource Server does not inspect just one string. The decoder processes multiple layers:

~~~text
Authorization: Bearer <compact-JWT>
             |
             v
       Parse JOSE header
             |
             +-- alg: which signature algorithm is required?
             +-- kid: which key in the JWK Set might match?
             +-- typ: what token type is declared?
             |
             v
       Select key and verify JWS signature
             |
             v
       Map JWT header + claims
             |
             v
       OAuth2TokenValidator chain
             |
             +-- iss: is the issuer trusted?
             +-- exp / nbf: is the token within its validity window?
             +-- typ: is the token type accepted by the decoder?
             +-- aud: is the token intended for this API?
             +-- custom claims / tenant / policy
             |
             v
       JwtAuthenticationConverter
             |
             v
       Authentication and authorities
~~~

| Field | Location | Role |
| --- | --- | --- |
| `alg` | JOSE protected header | JWS signing algorithm. The decoder must accept only trusted algorithms. |
| `kid` | JOSE header | Hint for selecting the matching key in the JWK Set; not proof of token validity. |
| `typ` | JOSE header | Declares the content/token type, such as `JWT` or `at+jwt`. |
| `iss` | JWT payload | Issuer that minted the token. |
| `aud` | JWT payload | Resource/API the token is intended for. |
| `exp`, `nbf`, `iat` | JWT payload | Token timestamps. |
| `scope`, `scp`, `roles` | JWT payload | Data that the converter can map to authorities per policy. |

`alg` and `typ` are not JWT payload claims. `JwtTypeValidator` reads `typ` from the header; `JwtClaimValidator` reads claims from the payload. Signature verification runs before claims are trusted, and additional validators decide whether the verified token conforms to the API's contract.

## 2. Changes to Compare When Upgrading

| Area | Spring Security 6.5 Migration Prep | Spring Security 7.x |
| --- | --- | --- |
| JWS algorithm | Default Nimbus decoder trusts RS256; configure explicitly if the issuer uses another algorithm. | RS256 remains the `NimbusJwtDecoder` default; continue verifying the allowlist and decoder construction. |
| Nimbus `typ` handling | Nimbus checks `typ` by default; can disable with `validateType(false)` to move to a validator. | Nimbus `typ` verification is off by default; `typ` checks live in the validator chain. |
| `JwtTypeValidator` | Add the validator explicitly to prepare for 7. | `JwtValidators.createDefault...` factories include `JwtTypeValidator.jwt()`. |
| Default `typ` policy | `JWT` or absent header matches default Nimbus behavior. | `JwtTypeValidator.jwt()` accepts `JWT` or absent `typ`. |
| RFC 9068 | `JwtValidators.createAtJwtValidator()` available since 6.5. | Can use this validator to enforce RFC 9068 JWT Access Tokens. |
| Audience | Must be configured separately; issuer validation alone does not prove the token is meant for this API. | Still must be configured separately unless using the corresponding Boot property. |
| Validator chain | Use factory/default validators and compose custom validators. | Default factory adds `typ` checking; calling `setJwtValidator` still replaces the active validator chain. |

Use 6.5 as a preparation step before upgrading to 7.0. Once tests verify the new `typ` behavior, moving to 7.x produces far fewer surprises.

## 3. Checking JWS Algorithm Defaults

### 3.1. RS256 Remains the `NimbusJwtDecoder` Default

For `NimbusJwtDecoder`, the default trusted algorithm is `RS256` (RSA signature with SHA-256). If the Authorization Server signs with `RS512`, `ES256`, or another algorithm, the Resource Server must configure the matching algorithm.

Do not confuse a `typ` change with an `alg` change: moving type validation from Nimbus to `JwtTypeValidator` does not alter the signing algorithm.

### 3.2. Configuring Algorithms via Spring Boot

Example when the issuer signs only with RS512:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test
          jwk-set-uri: https://identity.example.test/oauth2/jwks
          jws-algorithms: RS512
~~~

`jws-algorithms` is the Resource Server's allowlist. Match the exact algorithm the issuer emits and that the key/JWK supports. `issuer-uri` is still used to validate the `iss` claim; `jwk-set-uri` specifies the public key source.

If the issuer signs with multiple algorithms during a transition period, list only the algorithms explicitly approved:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test
          jwk-set-uri: https://identity.example.test/oauth2/jwks
          jws-algorithms:
            - RS256
            - ES256
~~~

Keep the allowlist short. Never add algorithms just so any token passes; each algorithm must have a supported key type, key lifecycle, and policy.

### 3.3. Configuring via `NimbusJwtDecoder` Builder

Single algorithm:

~~~java
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

JwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri("https://identity.example.test/oauth2/jwks")
    .jwsAlgorithm(SignatureAlgorithm.ES256)
    .build();
~~~

Multiple algorithms:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri("https://identity.example.test/oauth2/jwks")
    .jwsAlgorithm(SignatureAlgorithm.RS256)
    .jwsAlgorithm(SignatureAlgorithm.ES256)
    .build();
~~~

Or use `jwsAlgorithms` to declare the set of algorithms in a single callback. The examples above only configure signature verification; you must still attach validators for issuer, timestamps, audience, and type.

### 3.4. Boot Issuer Discovery and Custom Decoders Can Follow Different Config Paths

When using issuer discovery, Spring Security queries metadata to locate `jwks_uri`; some auto-configuration paths also inspect algorithms published in the JWK Set to construct the validation strategy. When manually creating `NimbusJwtDecoder` with the JWK Set URI builder, the decoder defaults to RS256 unless configured otherwise.

Therefore, during migration:

1. Determine whether the app uses Boot auto-configuration, `JwtDecoders.fromIssuerLocation`, `NimbusJwtDecoder.withIssuerLocation`, or `withJwkSetUri`.
2. Check whether the `jws-algorithms` property and a custom builder override one another.
3. Verify the JWK Set has `kty`, `use`, `key_ops`, `alg`, and `kid` matching the signing algorithm.
4. Write tests for each allowed algorithm and at least one rejected algorithm.

Never use `alg` from a token's header as the source for configuring the allowlist. Headers are untrusted input supplied by the token sender; the Resource Server must enforce an independent policy deciding which algorithms are permitted.

### 3.5. Avoiding Algorithm Confusion

- Never accept `none` for a Bearer Access Token.
- Never reuse key material in a way that lets an HMAC secret be confused with an RSA public key.
- Never widen the allowlist to an entire algorithm family just to work around a key rotation issue.
- Never let a token dictate the key URL or issuer.
- Never skip signature verification when keys fail to load.
- When migrating from RSA to EC, coordinate the issuer, JWK Set, key rotation, and Resource Server before issuing tokens signed with the new key.

`RS256`, `RS512`, and `ES256` are examples of JWS signature algorithms. JWE `alg`/`enc` is a separate topic; configuring a JWS allowlist does not configure decryption for arbitrary encrypted JWTs.

## 4. `typ` Is a JOSE Header, Not a Payload Claim

Example JWT header:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026",
  "typ": "JWT"
}
~~~

The payload may contain `iss`, `sub`, `aud`, `exp`, and `scope`. `typ` resides in the protected header. Some tokens omit `typ`; RFC 7515 allows this header to be absent.

### 4.1. Default Behavior of `JwtTypeValidator.jwt()`

`JwtTypeValidator.jwt()` requires:

- `typ` equal to `JWT`; or
- No `typ` header present.

Other values such as `at+jwt`, `JOSE`, or a custom media type will fail this validator. That is intentional: a decoder needs to know what kind of JWT it accepts.

### 4.2. Why Did Spring Move Type Validation Out of Nimbus?

Previously, Nimbus verified `typ` inside the JOSE processor. Spring Security wanted to unify header and claim validation under the `OAuth2TokenValidator` mechanism so type policies can vary per token type and apply consistently alongside other validators.

Spring Security 6.5 introduced `JwtTypeValidator` and `validateType(false)` for preparation. Spring Security 7 makes this the default:

~~~text
Before migration:
  Nimbus JOSE processor
      |
      +-- verify signature
      +-- verify typ
              |
              v
        Jwt claim validators

After migration:
  Nimbus JOSE processor
      |
      +-- verify signature
      |
      v
  Jwt / OAuth2TokenValidator chain
      |
      +-- JwtTypeValidator
      +-- issuer/timestamp/audience/custom validators
~~~

### 4.3. Step-by-Step Preparation on Spring Security 6.5

For standard tokens with `typ: JWT` or no `typ`, disable Nimbus type verification and add `JwtTypeValidator.jwt()` to the validator chain:

~~~java
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTypeValidator;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation(ISSUER)
    .validateType(false)
    .build();

decoder.setJwtValidator(
    JwtValidators.createDefaultWithValidators(
        new JwtIssuerValidator(ISSUER),
        JwtTypeValidator.jwt()));
~~~

In 6.5, `validateType(false)` transfers header validation responsibility to the validator. Use `createDefaultWithValidators` to preserve the standard validators while adding issuer/type policy.

### 4.4. Completing Migration on Spring Security 7

After applying the preparation step and testing, you can remove `validateType(false)` because it is the default on the Nimbus decoder in 7. Default validator factories already include `JwtTypeValidator.jwt()`:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation(ISSUER)
    .build();

decoder.setJwtValidator(
    JwtValidators.createDefaultWithIssuer(ISSUER));
~~~

If you have a custom audience validator, compose it with the default validator:

~~~java
OAuth2TokenValidator<Jwt> audienceValidator =
    new JwtClaimValidator<List<String>>(
        JwtClaimNames.AUD,
        audience -> audience.contains(API_AUDIENCE));

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(ISSUER),
        audienceValidator));
~~~

In 7.x, `createDefaultWithIssuer` includes issuer, timestamp, and default type validation. Audience remains the Resource Server's own policy; never assume configuring an issuer alone validates `aud`.

## 5. If the Issuer Uses a Custom `typ`

Some legacy systems use types such as `JOSE`. If you previously used Nimbus `DefaultJOSEObjectTypeVerifier`, migrate that policy to `JwtTypeValidator`.

Example during 6.5 preparation:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation(ISSUER)
    .validateType(false)
    .build();

JwtTypeValidator typeValidator =
    new JwtTypeValidator("JOSE");
typeValidator.setAllowEmpty(true);

decoder.setJwtValidator(
    JwtValidators.createDefaultWithValidators(
        new JwtIssuerValidator(ISSUER),
        typeValidator));
~~~

Enable `setAllowEmpty(true)` only if the issuer contract allows the `typ` header to be absent. If the contract requires `JOSE`, omit that option so missing headers are rejected.

When upgrading to 7.x, drop `validateType(false)` since the default is already false; keep the custom `JwtTypeValidator` in the validator chain. When using a default factory, make sure the custom type validator replaces the default `JWT` policy per your running version's migration guide. Never combine two conflicting type validators—such as one accepting only `JWT` and another accepting only `JOSE`.

### 5.1. Do Not Relax Type Validation to Accept Any Value

Avoid custom validators that always return success or accept any arbitrary `typ` string. Type validation exists so a decoder does not confuse one kind of JWT with another token type having a different contract and purpose. If an API must accept multiple token profiles, define explicit decoder/validator policies per profile or per issuer.

## 6. RFC 9068 and `typ: at+jwt`

RFC 9068 defines a profile for JWT Access Tokens. A JWT Access Token following this profile uses `typ: at+jwt` and carries corresponding required claims/semantics, such as `iss`, `sub`, `aud`, `exp`, `iat`, `jti`, `client_id`, and `scope` when issued per the profile.

`JwtTypeValidator.jwt()` accepts only `JWT` or absent `typ`, making it unsuitable for validating tokens with `typ: at+jwt`. Spring Security provides `JwtValidators.createAtJwtValidator()` starting in 6.5 to enforce the RFC 9068 profile.

~~~java
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation(ISSUER)
    .validateType(false)
    .build();

decoder.setJwtValidator(
    JwtValidators.createAtJwtValidator()
        .issuer(ISSUER)
        .audience(API_AUDIENCE)
        .clientId(OAUTH_CLIENT_ID)
        .build());
~~~

In Spring Security 6.5, keep `validateType(false)` so Nimbus does not reject `at+jwt` before the RFC 9068 validator runs. In Spring Security 7, Nimbus type verification is off by default so that call can be removed.

`AtJwtBuilder` requires configuring at least `issuer`, `audience`, and `clientId`. Choose the exact client ID per the token issuance contract. Do not apply this builder to a generic non-RFC-9068 JWT expecting it to check only `typ`.

### 6.1. Distinguishing Generic JWTs from RFC 9068 Access Tokens

| Property | Generic JWT | RFC 9068 JWT Access Token |
| --- | --- | --- |
| `typ` | May be `JWT` or absent per contract. | `at+jwt`. |
| `iss` | Per profile/issuer contract. | Required by RFC 9068. |
| `aud` | Must be validated per resource policy. | Required and must contain the resource server audience. |
| `client_id` | Not mandatory for every generic JWT. | Present in the profile. |
| `jti` | Optional depending on profile. | Required by the profile. |
| Validator | Default + application policies. | `createAtJwtValidator()` with issuer/audience/client ID. |

Never alter an issuer's `typ` to `at+jwt` just to make a test pass. The issuer must genuinely issue RFC 9068 Access Tokens and satisfy the corresponding claim contract.

## 7. What Do the Default Validators Actually Check?

With a minimal Resource Server configuration using `issuer-uri`, Spring Security verifies:

- The JWT signature using a trusted key from the JWK Set.
- The `iss` claim matching the configured issuer.
- `exp` and `nbf` via the timestamp validator.
- A default 60-second clock skew for timestamp validation.

The following checks are not automatically guaranteed solely by configuring `issuer-uri`:

- The current API's audience.
- Tenant, owner, or object-level permissions.
- Required domain-specific custom claims.
- Maximum token age based on `iat`.
- Specialized token types beyond the default type policy.
- Per-endpoint scope authorization.

`JwtAuthenticationConverter` maps scopes/claims into `GrantedAuthority`; that mapping does not replace claim validation. For example, a scope maps to `SCOPE_orders.read`, yet the API must still configure authorization rules requiring that authority.

### 7.1. Validator Factories

| Factory/API | Purpose |
| --- | --- |
| `JwtValidators.createDefault()` | Standard validators not bound to a specific issuer. |
| `JwtValidators.createDefaultWithIssuer(issuer)` | Standard validators plus issuer validator. |
| `JwtValidators.createDefaultWithValidators(...)` | Standard validators plus application-supplied validators. |
| `JwtValidators.createAtJwtValidator()` | Builder for the RFC 9068 JWT Access Token profile. |
| `JwtTimestampValidator` | Validates `nbf`/`exp` window and clock skew. |
| `JwtIssuerValidator` | Validates the `iss` claim. |
| `JwtTypeValidator.jwt()` | Requires `typ` header to be `JWT` or absent. |
| `JwtClaimValidator` | Validates a single claim with a predicate. |

Starting in Spring Security 7, `createDefault...` factories include `JwtTypeValidator.jwt()`. Thus, if custom code previously called only `JwtValidators.createDefaultWithIssuer`, after migrating to 7 it also enforces default `typ` validation.

### 7.2. Audience Is Not Automatically Added by the Issuer Validator

`iss` answers who issued the token; `aud` answers which resource the token is meant for. A token with a valid issuer whose audience is `inventory-api` must not be automatically accepted by `orders-api`.

Example validator:

~~~java
OAuth2TokenValidator<Jwt> audienceValidator =
    new JwtClaimValidator<List<String>>(
        JwtClaimNames.AUD,
        audience -> audience.contains("orders-api"));

OAuth2TokenValidator<Jwt> validators =
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(ISSUER),
        audienceValidator);

decoder.setJwtValidator(validators);
~~~

On Spring Boot versions supporting `spring.security.oauth2.resourceserver.jwt.audiences`, audiences can be declared in configuration. When using a custom decoder or custom validator chain, verify that property still takes effect; a custom `JwtDecoder` can replace Boot auto-configuration.

### 7.3. `setJwtValidator` Replaces the Existing Chain

This is a frequent migration mistake:

~~~java
// RISK: only the audience validator remains if default validators are not composed.
decoder.setJwtValidator(audienceValidator);
~~~

How to preserve the defaults:

~~~java
decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(ISSUER),
        audienceValidator));
~~~

If you build a `DelegatingOAuth2TokenValidator` containing only `JwtTimestampValidator` and `JwtIssuerValidator`, other validators do not appear automatically. Explicitly list all required validators and test each condition.

## 8. Do Not Confuse Validators with Authority Converters

~~~text
JwtDecoder
  |
  +-- signature verification
  +-- issuer / timestamp / typ / audience / custom validation
  |
  v
Validated Jwt
  |
  v
JwtAuthenticationConverter
  |
  +-- scope -> SCOPE_...
  +-- custom roles -> ROLE_...
  |
  v
Authentication
  |
  v
Authorization rules
~~~

A token with `scope: "orders.read"` can map to `SCOPE_orders.read`. However, if the token carries the wrong audience, the decoder must reject it before the authority converter ever runs. Never try to patch audience checks inside a converter or map roles to compensate for a missing validator.

## 9. Validator Configuration Differs Between Servlet and WebFlux

The semantics of algorithm allowlists, `typ`, and claim validators are identical; the decoder interfaces differ:

| Stack | Decoder Interface | Nimbus Implementation |
| --- | --- | --- |
| Servlet | `JwtDecoder` | `NimbusJwtDecoder` |
| WebFlux | `ReactiveJwtDecoder` | `NimbusReactiveJwtDecoder` |

The reactive decoder offers a builder and similar APIs to configure trusted JWS algorithms, type validation, and the validator chain. Never use the blocking Servlet `JwtDecoder` in a reactive request pipeline just to reuse configuration.

Reactive JWT decoder example:

~~~java
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

ReactiveJwtDecoder reactiveDecoder() {
    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder
            .withJwkSetUri(JWKS_URI)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(ISSUER));
    return decoder;
}
~~~

When audience validation is needed, compose `JwtClaimValidator` with the default validator just as in Servlet. For RFC 9068 tokens, use `createAtJwtValidator()` and ensure Nimbus type verification does not block `at+jwt` before the profile validator runs.

## 10. Step-by-Step Migration Process

### Step 1: Capture the Current Token Contract

Collect sample tokens from each issuer/client/resource in a test or staging environment. Record the verified fields:

- JOSE `alg`, `kid`, `typ`.
- `iss`, `aud`, `exp`, `nbf`, `iat`.
- `client_id`, `jti`, `scope`/`scp` if used by the profile.
- JWK `kty`, `use`, `key_ops`, `alg`, and key rotation overlap.

Never log or place raw production tokens into migration docs. Use test tokens signed with test keys.

### Step 2: Identify How the Decoder Is Built

Locate all occurrences of:

- `spring.security.oauth2.resourceserver.jwt.issuer-uri`.
- `jwk-set-uri` and `jws-algorithms`.
- `JwtDecoders.fromIssuerLocation`.
- `NimbusJwtDecoder.withIssuerLocation` and `withJwkSetUri`.
- `jwtProcessorCustomizer`, `setJWSTypeVerifier`, `validateType`.
- `setJwtValidator`, `JwtValidators`, and custom `OAuth2TokenValidator`.

A custom decoder can override auto-configuration, so do not read YAML alone to infer the active policy.

### Step 3: Prepare `typ` on Spring Security 6.5

Set `validateType(false)` and add the matching type validator to the validator chain. For generic JWTs, use `JwtTypeValidator.jwt()`. For custom types, use `new JwtTypeValidator("...")`. For RFC 9068, use `createAtJwtValidator()`.

### Step 4: Lock Down the Algorithm Allowlist

Cross-check the issuer's signing configuration and JWK Set. Configure `RS256`/`RS512`/`ES256` or the minimal approved algorithm set. Do not widen the allowlist merely to silence test failures.

### Step 5: Add Any Missing Validators

Ensure issuer, timestamp, type, audience, and required domain policies are present. Inspect every `setJwtValidator` call carefully because it replaces the active chain.

### Step 6: Run Tests Before Bumping the Major Version

On 6.5, run the full signed-JWT test suite with the new type validator. Adjust either the issuer token profile or decoder policy if actual tokens differ from the contract.

### Step 7: Upgrade to Spring Security 7

After preparation:

- Remove `validateType(false)` unless needed for a special reason, since 7.x disables Nimbus type verification by default.
- Remove explicit `JwtTypeValidator.jwt()` additions if using a default validator factory.
- Retain custom type validators when the issuer uses a custom type.
- Confirm the new validator factory still preserves audience/domain checks.
- Check whether any custom Nimbus `jwtProcessorCustomizer` alters the legacy type verifier; move that logic to `JwtTypeValidator` or a custom `OAuth2TokenValidator`.

### Step 8: Compare Before and After Behavior

Run the identical set of signed tokens against the 6.5 decoder and the 7.x decoder. For each token, record pass/fail and the reason. Any differences must be explained by intentional policy migration—never accept tests turning green because a validator was dropped.

## 11. Testing Algorithms, `typ`, and Validators

### 11.1. Testing the Algorithm Allowlist

Generate tokens signed with each accepted algorithm and at least one token signed with an algorithm outside the allowlist.

| Token | Expectation |
| --- | --- |
| RS256 when allowlist is RS256 | Signature verifies if matching key is present. |
| ES256 when allowlist is only RS256 | Rejected. |
| RS512 when allowlist is RS256 and RS512 | Signature verifies if matching key is present. |
| `alg: none` | Rejected. |
| Allowed algorithm with incompatible key type | Rejected. |
| `kid` missing from trusted JWK Set | Cannot verify; rejected. |

Never merely edit the `alg` header on an already-signed token. Modifying the header invalidates the signature; algorithm tests must mint new tokens genuinely signed with matching keys.

### 11.2. Testing the Type Header

With default `JwtTypeValidator.jwt()`:

| JOSE `typ` | Expectation |
| --- | --- |
| `JWT` | Passes type validator if other checks pass. |
| No `typ` | Passes type validator per default policy. |
| `at+jwt` | Rejected by default JWT type validator; use RFC 9068 validator if that profile is supported. |
| `JOSE` | Rejected unless decoder is configured for custom type. |
| Arbitrary string | Rejected. |

### 11.3. Testing Claim Validators

| Claim | Test Token | Expectation |
| --- | --- | --- |
| `iss` | Matching issuer | Pass. |
| `iss` | Different issuer | Fail. |
| `aud` | Contains API audience | Pass. |
| `aud` | Contains only another API's audience | Fail. |
| `exp` | Expired beyond clock skew | Fail. |
| `nbf` | Not yet valid beyond clock skew | Fail. |
| `iat` | In the future / too old | Per custom policy if configured. |
| `scope` | Has required scope | Converter grants authority; authorization policy decides. |

### 11.4. Using Signed JWT Integration Tests

`mockJwt()` in MockMvc/WebTestClient injects a pre-authenticated mock `Authentication`. It is helpful for authorization tests, but it does not exercise signatures, algorithms, `typ`, or real decoder validators.

To verify migration:

1. Generate an RSA/EC test key pair.
2. Sign a test JWT with controlled protected headers and claims.
3. Configure the real decoder against the test public key or JWK Set.
4. Call `JwtDecoder.decode(token)` or send the Bearer token through the full Resource Server filter chain.
5. Assert valid tokens are accepted and each invalid variant is rejected.

Never use unsigned tokens or hand-edited compact JWT strings to test a production decoder.

### 11.5. Verifying Custom Validators Were Not Dropped

Write at least one test token with the wrong audience yet valid signature/issuer/timestamps/type. That token must be rejected. This catches `setJwtValidator(audienceValidator)` overwriting default validators or migrations accidentally dropping audience rules.

## 12. Common Migration Mistakes

| Mistake | Consequence | Resolution |
| --- | --- | --- |
| Assuming Spring Security 7 changes default algorithm away from RS256 | Misconfiguration or overly broad allowlist | Verify RS256 and the issuer's actual signing algorithm |
| Trusting `alg` from the header to choose policy dynamically | Algorithm confusion | Configure an independent allowlist |
| Keeping `DefaultJOSEObjectTypeVerifier` in `jwtProcessorCustomizer` | Type policy remains buried in legacy Nimbus, disconnected from validator chain | Migrate to `JwtTypeValidator` |
| Disabling Nimbus type checking without adding a validator | Intended type validation disappears | Add `JwtTypeValidator` or RFC 9068 validator |
| Using `JwtTypeValidator.jwt()` for `at+jwt` | RFC 9068 JWT Access Tokens get rejected | Use `createAtJwtValidator()` |
| Accepting any `typ` to silence errors | Tokens from other profiles can be confused | Explicitly allowlist types |
| Calling `setJwtValidator` with a single standalone validator | Loses issuer/timestamp/type defaults | Compose with `createDefaultWithIssuer` or appropriate factory |
| Assuming `issuer-uri` validates audience automatically | Tokens issued for another API pass issuer checks | Add audience validator/property |
| Confusing scope converter with scope validation | Authentication receives authorities while routes remain unprotected | Add authorization rules |
| Testing solely with `mockJwt()` | Never exercises the real decoder | Add signed JWT integration tests |
| Testing only valid tokens | Misses regressions with malformed/invalid tokens | Test invalid `alg`, `typ`, `iss`, `aud`, `exp`, `nbf` |
| Using a custom decoder and forgetting validators | Boot defaults no longer apply | Attach an explicit validator chain |

## 13. Pre-Completion Migration Checklist

- [ ] Active and target Spring Security/Spring Boot versions are identified.
- [ ] How `JwtDecoder` or `ReactiveJwtDecoder` is constructed is verified.
- [ ] Issuer signing algorithm and JWK Set are confirmed.
- [ ] JWS algorithm allowlist contains only approved algorithms.
- [ ] Trust policy never relies on token-supplied `alg`.
- [ ] JOSE `typ` header on real tokens has been checked.
- [ ] `JwtTypeValidator` preparation was completed on Spring Security 6.5.
- [ ] `at+jwt` uses the RFC 9068 validator if the issuer uses that profile.
- [ ] Legacy custom Nimbus type verifiers are removed or moved to validators.
- [ ] Validator chain still enforces issuer and timestamps.
- [ ] Resource Server audience is explicitly validated.
- [ ] Custom validators are not lost in `setJwtValidator` calls.
- [ ] Scope converter and authorization rules remain intact.
- [ ] Signed JWT tests cover both pass and fail cases.
- [ ] Test suite does not rely solely on mock Authentication.
- [ ] Decoder behavior was compared before and after migration.

**Remember:** `alg` governs signature verification and `RS256` remains the `NimbusJwtDecoder` default; `typ` is a JOSE header whose verification moves to `JwtTypeValidator` in Spring Security 7; and 7.x default validator factories include `JwtTypeValidator.jwt()` accepting `JWT` or an absent header. For RFC 9068, use `createAtJwtValidator()` for `at+jwt`. Whenever adding audience or custom policies, retain issuer/timestamp/type validators and test the decoder with genuinely signed JWTs.

## References

- [Spring Security 6.5 — OAuth 2.0 Migration to 7.0](https://docs.spring.io/spring-security/reference/6.5/migration-7/oauth2.html).
- [Spring Security 7.0 — OAuth 2.0 Migrations](https://docs.spring.io/spring-security/reference/7.0/migration/servlet/oauth2.html).
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html).
- [Spring Security API — JwtTypeValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtTypeValidator.html).
- [Spring Security API — JwtValidators.AtJwtBuilder](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/oauth2/jwt/JwtValidators.AtJwtBuilder.html).
- [Spring Security API — NimbusJwtDecoder.JwkSetUriJwtDecoderBuilder](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.JwkSetUriJwtDecoderBuilder.html).
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515).
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517).
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519).
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
