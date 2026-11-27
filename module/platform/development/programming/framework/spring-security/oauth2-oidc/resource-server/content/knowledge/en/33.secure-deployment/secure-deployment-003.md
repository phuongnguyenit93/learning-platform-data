# Preventing Algorithm Confusion, Token-Type Confusion, and Token Substitution Across Resources

A JWT with a valid signature can still be a credential that is **not permitted for use at the current API**. A Resource Server must verify multiple independent conditions:

1. **Algorithm and key:** the token is signed using an algorithm in the allowlist and a key of the right type and issuer.
2. **Token type:** the received JWT is actually an access token conforming to a profile accepted by the API, not an OIDC ID token, client assertion, logout token, or a JWT for another purpose.
3. **Issuer:** the token was issued by a trusted Authorization Server.
4. **Audience/resource:** the token was issued for the specific API or resource server handling the request.
5. **Lifetime and status:** the token is valid according to `exp`, `nbf`, policy, and the revocation mechanism in use.
6. **Business permissions:** the token has the required scope/authorities and the caller is permitted to act on the specific tenant/object.

The three errors in the title correspond to three common security confusion classes:

- **Algorithm confusion:** the Resource Server accepts an algorithm or key interpretation different from the intended policy.
- **Token-type confusion / cross-JWT confusion:** a JWT issued for purpose A is accepted in context B.
- **Audience confusion / token substitution:** a valid access token for API A is used at API B.

RFC 8725 (JWT Best Current Practices) requires checking the algorithm, using explicit typing when needed, and designing mutually exclusive validation rules across JWT types. RFC 9068 defines the OAuth 2.0 JWT access token profile, in which `typ=at+jwt` helps the Resource Server identify access tokens, while `aud` identifies the resource to which the token is directed.

> **Principle:** a valid signature only proves the token was signed with a key trusted by the decoder under the configured algorithm. It does not by itself prove that the token is an access token, is intended for this API, or has permission to perform the requested action.

This lesson belongs to the **Secure Deployment** section and uses Spring Security Servlet Resource Server, Spring Boot, and Java. WebFlux has `ReactiveJwtDecoder` and `SecurityWebFilterChain` equivalents; the principles of algorithms, token profiles, issuers, and audiences remain the same, though the configuration API differs.

## 1. Four Questions to Answer Before Accepting a JWT

Suppose a request arrives at the Orders API:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
~~~

The Resource Server must not stop at asking "can the JWT be parsed?". It needs to answer:

| Question | Example Condition | If Wrong |
|---|---|---|
| Who issued it? | `iss=https://login.example.com/realms/shop` | Reject token |
| Signed with this algorithm/key? | `alg=RS256`, key belongs to configured issuer | Reject token |
| What kind of token is it? | OAuth JWT access token `typ=at+jwt` per RFC 9068 | Reject wrong-profile token |
| Which API is it for? | `aud` contains `orders-api` | Reject token for another resource |
| Still valid? | `exp`, `nbf`, and validity policies | Reject token |
| What permissions does caller have? | `scope=orders.read` | Authorization decides 403 if missing |

A token can pass some conditions while failing others. For example:

- Valid signature, but `alg=HS256` while the API only allows `RS256`.
- Valid signature and right issuer, but the JWT is an OIDC ID token.
- JWT is an access token with the right profile, but `aud=billing-api`.
- Right audience, but scope only has `orders.read` while the endpoint needs `orders.write`.

Each condition serves a distinct purpose. Never use one claim as a substitute for multiple other conditions.

## 2. Algorithm Confusion: Why Lock Down the Algorithm?

### 2.1. The JWT Header Has an `alg` Field

A signed JWT/JWS typically has a header:

~~~json
{
  "alg": "RS256",
  "kid": "orders-signing-key-1",
  "typ": "at+jwt"
}
~~~

`alg` indicates the signing algorithm used for the JWS. Examples:

| Algorithm | Mechanism | Verification Key |
|---|---|---|
| `RS256` | RSA + SHA-256 | RSA public key |
| `PS256` | RSA-PSS + SHA-256 | RSA public key |
| `ES256` | ECDSA P-256 + SHA-256 | EC public key |
| `HS256` | HMAC + SHA-256 | Shared secret |
| `none` | No signature | No signature verification |

The Resource Server must have an explicit policy for which algorithms are accepted. Never let the request's JWT header freely dictate the algorithm.

### 2.2. `alg` Is Untrusted Input

Before the signature is verified, the entire JWT header is sender-supplied data:

~~~json
{
  "alg": "HS256",
  "kid": "some-key",
  "typ": "JWT"
}
~~~

An attacker can craft a token with an arbitrary `alg`. The fact that a parser can read `alg=HS256` does not mean the application is allowed to use HS256.

RFC 8725 requires applications to permit only a defined set of algorithms, check the algorithm in the header against the algorithm actually used for verification, and bind each key to a single algorithm.

### 2.3. RSA/HMAC Confusion Example

Suppose the Authorization Server signs access tokens with `RS256`:

- The AS holds the RSA private key.
- The Resource Server uses the RSA public key fetched from JWKS.
- A public key is not a shared secret.

A flawed implementation might take the bytes of the RSA public key and use them as an HMAC secret when the token header declares `HS256`. If the Resource Server accepts both interpretations without binding algorithms to key types, an attacker can compute an HMAC using the public key data and forge a signature against that weak implementation.

Correct model:

~~~text
Trusted Issuer
       |
       v
RS256 + RSA signing key
       |
       v
JWKS publishes RSA public key
       |
       v
Resource Server allows RS256 only
       |
       v
Public key is only used to verify RS256 signatures
~~~

Never use RSA public key bytes as an HMAC secret. If a system genuinely needs HMAC, manage a separate shared secret, never reuse public key material, and never share keys across algorithm families.

### 2.4. Rejecting `alg=none`

An unsecured JWT may have a header:

~~~json
{
  "alg": "none",
  "typ": "JWT"
}
~~~

The token has no cryptographic signature. Under RFC 9068, OAuth JWT access tokens **MUST NOT** use `none`. A Resource Server for access tokens must reject this token.

Do not configure a decoder to "verify if a signature is present, otherwise still read the claims." Never extract `sub`, `scope`, or `role` from an unverified token.

### 2.5. Key Type and Algorithm Must Be Compatible

Example expected mapping:

| JWK Key Type | Expected Algorithm | What to Verify |
|---|---|---|
| RSA | `RS256`, if permitted by policy | Compatible RSA key and signature algorithm |
| EC P-256 | `ES256`, if permitted by policy | Matching curve and algorithm |
| Octet/shared secret | `HS256`, if intentionally designed | Dedicated secret, securely protected and distributed |
| Any key | `none` | Never accepted |

A JWK may contain `alg`, `use`, or `key_ops`; if published, they must match the key's intended usage. Do not infer that every key in a JWKS is allowed for every algorithm.

### 2.6. `kid` Does Not Determine the Algorithm

`kid` only helps select a key within a trusted key source. It is not proof that:

- The key is permitted for the `alg` declared by the JWT.
- The token belongs to the expected issuer.
- The token is an access token.
- The token is intended for the current API.

Do not load keys from arbitrary `jku` or `x5u` values in the JWT header. Only fetch public keys from configured JWKS URIs or discovery from an approved issuer. If a key ID is used in database/cache lookups, prevent injection and bound size/format.

## 3. Configuring an Algorithm Allowlist in Spring Security

### 3.1. Default Behavior of `NimbusJwtDecoder`

Spring Security Resource Server uses `NimbusJwtDecoder` for JWTs in the Servlet stack. Per current Spring Security documentation, the default decoder only trusts the `RS256` algorithm.

This means `HS256`, `none`, or other algorithms are not automatically accepted just because the JWT parser can read them.

However, when an application builds its own decoder, configure an explicit allowlist matching the issuer's contract. Do not widen algorithms based on token headers or caller-supplied data.

### 3.2. Spring Boot Properties

Example configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          jwk-set-uri: https://login.example.com/realms/shop/protocol/openid-connect/certs
          jws-algorithms:
            - RS256
          audiences:
            - orders-api
~~~

This is an illustrative configuration for Spring Boot versions supporting these properties. Confirm property names against your application's Spring Boot BOM/version.

Meaning:

- `issuer-uri`: canonical issuer trusted by the Resource Server.
- `jwk-set-uri`: governed source of public keys.
- `jws-algorithms`: signature algorithm allowlist.
- `audiences`: resource identifiers that the token must contain.

If the AS only signs with RS256, do not add HS256/ES256 "just in case for later." When changing algorithms, perform a controlled policy change and rollout.

### 3.3. Configuring `NimbusJwtDecoder` in Java

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtDecoderConfiguration {

    @Bean
    JwtDecoder jwtDecoder() {
        String issuer =
            "https://login.example.com/realms/shop";

        String jwkSetUri =
            "https://login.example.com/realms/shop/protocol/openid-connect/certs";

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(issuer)
        );

        return decoder;
    }
}
~~~

This code:

1. Fetches keys from a fixed JWKS URI.
2. Accepts only RS256.
3. Keeps default validation for issuer and timestamps.
4. Returns a `JwtDecoder` for the Resource Server.

It does not yet add audience or token-type validation. Those checks are added in the following sections.

If an issuer genuinely signs with multiple approved algorithms, you can call `.jwsAlgorithm(...)` multiple times or `.jwsAlgorithms(...)` to declare the allowed set. Every algorithm must have a justification, compatible key type, and negative tests. Never permit all algorithms just because JWKS contains multiple key types.

### 3.4. Do Not Write a Header-Driven Verifier

Avoid code like:

~~~java
// Unsafe: the attacker controls alg in the JWT header.
String algorithm = unverifiedJwt.getHeaders().get("alg").toString();

if ("HS256".equals(algorithm)) {
    verifyWithHmac(jwt);
} else if ("RS256".equals(algorithm)) {
    verifyWithRsa(jwt);
}
~~~

If multiple algorithms must be supported, configure the decoder/key selector with a fixed allowlist. The JOSE library must verify both the algorithm and the corresponding key in one unified verification flow.

## 4. Token-Type Confusion: A JWT Can Be Issued for Many Purposes

### 4.1. JWT Is Only a Format, Not a Single Credential Type

A system may use JWTs for many purposes:

| JWT / Credential Type | Intended Consumer | Purpose |
|---|---|---|
| OAuth access token | Resource Server/API | Access protected resources |
| OIDC ID token | OIDC client/Relying Party | User authentication details |
| Client assertion | Authorization Server token endpoint | OAuth client authentication |
| Logout token | OIDC relying party | Logout / back-channel logout notification |
| Security Event Token | Event receiver | Delivering security events |
| Internal service JWT | A specific service | Internal identity/delegation per contract |

These types can all use JWT, be signed by the same issuer, and even be signed with the same key. If an API only checks "valid signature" and "has `sub`", a JWT issued for another purpose can be misused.

This is **cross-JWT confusion** as described in RFC 8725.

### 4.2. An OIDC ID Token Is Not an Access Token

An OIDC ID token is issued to an OIDC client so the client knows the end-user's authentication result.

Example ID token:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-42",
  "aud": "storefront-web",
  "azp": "storefront-web",
  "nonce": "client-generated-nonce",
  "auth_time": 2000000000,
  "exp": 2000000300,
  "iat": 2000000000
}
~~~

Here `aud` is the OIDC client ID (`storefront-web`) per OIDC Core. The token is directed at that client so the client can verify authentication.

Example access token intended for the Orders API:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "client_id": "storefront-web",
  "scope": "orders.read",
  "exp": 2000000300,
  "iat": 2000000000
}
~~~

The access token is directed at the `orders-api` resource server. It represents API access permissions per the AS's authorization policy.

**Do not use an ID token as a Bearer access token for an API.** An ID token has a valid signature and may contain `sub`, `email`, `name`, and `aud`; none of those properties make it an access token.

### 4.3. Why Checking `sub` Is Not Enough

Both an ID token and an access token can have:

~~~text
iss = https://login.example.com/realms/shop
sub = user-42
exp = ...
```

If an API only checks:

~~~java
if (jwt.getSubject() != null) {
    allow();
}
~~~

then a token issued to another client can slip through. `sub` only identifies the subject within the issuer; it does not say which API or purpose the token was issued for.

### 4.4. OIDC ID Token Audience and Access Token Audience Differ

| Token | What `aud` Represents | Who Must Validate |
|---|---|---|
| OIDC ID token | OIDC client/Relying Party `client_id` | OIDC client |
| OAuth JWT access token | Resource Server/resource indicator | API/Resource Server |

An API with `aud=orders-api` should not accept an ID token with `aud=storefront-web`. Likewise, an OIDC client should not accept an ID token just because `aud` contains an API identifier.

Do not use `azp` as a substitute for audience validation. `azp` represents the authorized party in an OIDC ID token; it does not turn a client ID into an access token's resource audience.

## 5. Explicit Typing and the RFC 9068 Access-Token Profile

### 5.1. JWT `typ` and OAuth `token_type` Are Two Different Concepts

Two fields are easily confused:

**JOSE header `typ`:**

~~~json
{
  "typ": "at+jwt",
  "alg": "RS256"
}
~~~

It indicates the JWT type by media-type/profile.

**OAuth token response `token_type`:**

~~~json
{
  "access_token": "eyJ...",
  "token_type": "Bearer",
  "expires_in": 600
}
~~~

It tells the OAuth client how to present the token when calling a resource. `token_type=Bearer` is not a claim inside the JWT and does not replace checking JWT `typ`.

A token can be an RFC 9068 JWT access token (`typ=at+jwt`) and be returned in the OAuth response with `token_type=Bearer`.

### 5.2. RFC 9068 Requires `typ=at+jwt`

RFC 9068 defines the JWT Profile for OAuth 2.0 Access Tokens. Under this profile:

- JWT access tokens must be signed.
- `alg=none` is not allowed.
- `typ` must be `at+jwt` or `application/at+jwt`.
- Required access-token profile claims must be present, including issuer, subject, audience, expiry, issued-at, JWT ID, and client ID.
- The Resource Server must check the exact issuer.
- The Resource Server must confirm `aud` contains the resource server's own identifier.
- The Resource Server must verify the signature using a supported algorithm and the Authorization Server's key.

The `at+jwt` value indicates this is a profiled JWT access token, not an ID token or arbitrary JWT.

### 5.3. `typ=JWT` Is Not Enough to Distinguish Access Tokens

Many JWTs may use:

~~~json
{
  "typ": "JWT"
}
~~~

This value only says the token is a generic JWT. It does not assert that it is an OAuth access token.

If the AS does not implement RFC 9068, tokens may use a custom type or profile. The Resource Server needs to clearly define the contract with the issuer and validation rules that exclude wrong-purpose tokens. Do not force `at+jwt` if the AS does not issue that profile; nor assume `typ=JWT` is sufficient for every API.

### 5.4. Validation Rules Must Be Mutually Exclusive

RFC 8725 requires that if the same issuer issues multiple types of JWTs, validation rules for each type must be mutually exclusive and reject wrong-type JWTs.

Approaches that can be combined:

- Distinct explicit `typ` per profile.
- Distinct `aud` per purpose.
- Distinct required claims and claim values.
- Separate signing keys per token type.
- Separate issuers per token type.
- Separate validators per token type.

Do not rely on a single field if profiles can be confused. For example, if both ID tokens and access tokens have `typ=JWT`, use audience and other required claims to distinguish them.

## 6. Using Audience to Prevent Misusing Tokens Across Resources

### 6.1. `aud` Indicates the Intended Recipient

The JWT `aud` claim identifies the recipient the token is intended for. It can be a string or an array of strings.

Example:

~~~json
{
  "aud": ["orders-api"]
}
~~~

The Orders API only accepts it if `orders-api` is an allowed audience.

An access token with:

~~~json
{
  "aud": ["billing-api"]
}
~~~

must be rejected by the Orders API, even when:

- The signature is valid.
- The issuer is right.
- The token is not expired.
- The scope contains `orders.read`.
- The subject is a valid user.

### 6.2. Scope Does Not Replace Audience

Scope answers the question: **what permissions were granted to the token?**

Audience answers the question: **which resource was the token issued for?**

Example:

~~~json
{
  "aud": ["billing-api"],
  "scope": "orders.read"
}
~~~

The Orders API must not accept a token merely because a scope named `orders.read` appears. Scopes can have different meanings across APIs; resource binding must be verified independently.

### 6.3. `client_id` Is Not Audience

Example:

~~~json
{
  "client_id": "storefront-web",
  "aud": ["orders-api"]
}
~~~

- `client_id`: the OAuth client that received/was issued the token per contract.
- `aud`: the resource server intended to consume the token.

Do not write a policy like:

~~~java
if ("storefront-web".equals(jwt.getClaimAsString("client_id"))) {
    allowOrdersApi();
}
~~~

without checking `aud`. One client can request tokens for multiple APIs; client ID does not bind the resource by itself.

### 6.4. Audience Can Be Multi-Valued

JWT `aud` can be a string or an array. Spring's `Jwt#getAudience()` provides a normalized list of audiences.

Example:

~~~json
{
  "aud": ["orders-api", "inventory-api"]
}
~~~

If the AS issues tokens with multiple audiences, each API must verify whether policy permits multi-resource tokens. Never automatically accept any token with any audience just because it has a "similar" audience.

For architectures requiring per-resource tokens, RFC 8707 Resource Indicators lets clients specify the intended resource in the token request. The AS can use that information to issue an access token with the matching audience.

### 6.5. Wrong Audience Must Fail Authentication

If a token is validly signed but `aud` does not contain the API's resource identifier, the Resource Server should reject it as an invalid token (typically 401). Do not turn an audience mismatch into a 403 because the token was never issued for this API.

Once the audience is valid and the token is authenticated, missing scopes/roles become an authorization denial (typically 403).

## 7. Configuring Spring Security for RFC 9068

Spring Security supports a validator for RFC 9068 JWT access tokens. The `JwtValidators.createAtJwtValidator()` API has been available since Spring Security 6.5.

Servlet Resource Server example:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class AccessTokenDecoderConfiguration {

    @Bean
    JwtDecoder jwtDecoder() {
        String issuer =
            "https://login.example.com/realms/shop";

        String jwkSetUri =
            "https://login.example.com/realms/shop/protocol/openid-connect/certs";

        String audience = "orders-api";

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .validateTypes(false)
            .build();

        decoder.setJwtValidator(
            JwtValidators.createAtJwtValidator()
                .issuer(issuer)
                .audience(audience)
                .build()
        );

        return decoder;
    }
}
~~~

### 7.1. What Each Line Does

- `withJwkSetUri(...)`: fetches public keys from a governed endpoint.
- `jwsAlgorithm(RS256)`: permits only RS256.
- `validateTypes(false)`: disables Nimbus's default type validation so Spring's profile validator can validate `typ` according to RFC 9068.
- `createAtJwtValidator()`: creates a validator for the OAuth JWT access-token profile.
- `issuer(...)`: requires the specific issuer.
- `audience(...)`: requires the Orders API's resource identifier.

This configuration is for issuers committed to issuing RFC 9068 JWT access tokens. If the AS uses a custom token profile, replace the type/profile validator to match the contract.

### 7.2. When to Add `clientId(...)`

The builder allows specifying a client ID:

~~~java
JwtValidators.createAtJwtValidator()
    .issuer(issuer)
    .audience(audience)
    .clientId("storefront-web")
    .build();
~~~

Only add `.clientId(...)` if the API truly only accepts tokens from a single OAuth client. If multiple web/mobile/service clients are allowed to call the API, do not lock it to one client ID; use a separate allowlist policy if required by business rules.

Even with a client ID allowlist, you must still validate audience. `client_id` does not replace resource binding.

### 7.3. Spring Security Version Alignment

- `JwtValidators.createAtJwtValidator()` is available from Spring Security 6.5.
- Current Spring Security documentation instructs using `.validateTypes(false)` together with `createAtJwtValidator()` to verify RFC 9068.
- Default behavior changes around JWT `typ` have appeared in newer version lines; follow the documentation for the exact BOM your application uses.

Do not copy validators from another version without verifying `typ` handling, as this can conflict between Nimbus's type verifier and the access-token profile validator.

## 8. When the Issuer Does Not Use RFC 9068

Not every Authorization Server issues access tokens per RFC 9068. An AS might issue JWTs with:

~~~json
{
  "typ": "JWT",
  "iss": "https://legacy-idp.example.com",
  "aud": "orders-api",
  "sub": "user-42",
  "scope": "orders.read"
}
~~~

In that case, the Resource Server needs an explicitly agreed custom profile:

- Allowed algorithms.
- Exact issuer.
- Required audience.
- Claim/type used to identify an access token.
- Required claims.
- Time validation.
- How scopes/roles are mapped.
- How to distinguish this token from ID tokens or other JWTs from the same issuer.

You can write a custom `OAuth2TokenValidator<Jwt>` to check the `typ` header or custom claims. However, it must be combined with standard issuer/time/audience validators and never omit signature verification.

Example validator checking a custom header type:

~~~java
private OAuth2TokenValidator<Jwt> customAccessTokenTypeValidator() {
    return jwt -> {
        Object type = jwt.getHeaders().get("typ");

        if ("orders-access+jwt".equals(type)) {
            return OAuth2TokenValidatorResult.success();
        }

        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Unexpected JWT type",
                null
            )
        );
    };
}
~~~

This is only one component validator. When using a custom profile, configure the decoder so type handling does not conflict with the validator, and combine this validator with:

- `JwtIssuerValidator`.
- `JwtTimestampValidator`.
- Audience validator.
- Signature algorithm allowlist.

Do not copy the custom `typ` from this example into production unless the AS actually issues that exact value.

## 9. Custom Audience Validator Example

If not using the RFC 9068 builder, or if a complex audience policy is needed, you can use `OAuth2TokenValidator`.

~~~java
package com.example.orders.security;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class OrdersAudienceValidator
        implements OAuth2TokenValidator<Jwt> {

    private static final String REQUIRED_AUDIENCE = "orders-api";

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getAudience().contains(REQUIRED_AUDIENCE)) {
            return OAuth2TokenValidatorResult.success();
        }

        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Token is not intended for Orders API",
                null
            )
        );
    }
}
~~~

Combining validators:

~~~java
decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        new OrdersAudienceValidator()
    )
);
~~~

This snippet illustrates an additional audience validator. If explicit type validation is needed per a custom profile, add the corresponding validator for your Spring Security version and ensure default type validation does not accidentally reject valid tokens or accept wrong-type tokens.

**Note:** `createDefaultWithIssuer(...)` retains the default validators Spring provides for generic JWTs in the corresponding version. If you intentionally change type validation, confirm the final validator set still checks timestamps, issuer, audience, and type according to the chosen profile.

## 10. Distinguishing ID Tokens and Access Tokens in Depth

A secure strategy should not rely on `typ` alone. Combine:

| Property | ID Token | RFC 9068 JWT Access Token |
|---|---|---|
| JOSE `typ` | May be `JWT` or per provider profile | `at+jwt` or `application/at+jwt` |
| `aud` | OIDC client ID | Resource server identifier |
| `iss` | OIDC Provider issuer | Authorization Server issuer |
| `sub` | End-user subject | Subject per access-token profile |
| `client_id` | Not a core ID token claim | Access-token profile claim |
| `scope` | Not the way to determine API permissions | May carry OAuth scopes |
| Consumer | OIDC client | Resource Server |
| Validation profile | OIDC Core ID Token validation | RFC 9068 access-token validation |

Values in this table represent standard profiles. Not every provider emits every custom claim identically. Obtain the contract from your actual issuer.

### 10.1. ID Tokens Can Be Signed with the Same Signing Key

Do not assume:

~~~text
ID token -> key A
Access token -> key B
~~~

An issuer can use the same signing key for both. In that case, signature verification alone will not distinguish tokens.

Use explicit token types, distinct audiences, and mutually exclusive validation rules. If the AS supports key separation for different token purposes, that is a useful additional layer.

### 10.2. Do Not Use `nonce` as an API Audience

`nonce` in an OIDC flow helps the client bind an ID token to an authentication request. It is not the Orders API's resource indicator.

Never replace `aud` checks with `nonce`, `azp`, `client_id`, `email`, or `preferred_username`.

### 10.3. An ID Token Is Not a Credential for Downstream APIs

A web client may receive:

- An ID token to know the user authenticated.
- An access token to call the Orders API.
- A refresh token to request new access tokens at the token endpoint per policy.

Each token has its own purpose. Do not forward an ID token to the Orders API or Billing API. When calling APIs, use an access token with the right audience/resource.

## 11. Token Substitution Across Multiple APIs

### 11.1. Example: Token for API A Sent to API B

The system has:

~~~text
Authorization Server
    |
    +-- Billing API
    |
    +-- Orders API
    |
    +-- Inventory API
~~~

The AS issues:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-42",
  "aud": ["billing-api"],
  "scope": "read"
}
~~~

The Billing API is allowed to accept this token. The Orders API must reject it because the audience does not contain `orders-api`.

If all three APIs only check issuer and signature, tokens can be used across resources. This is the substitution attack highlighted by RFC 8725.

### 11.2. Identical Scope Names Do Not Make Tokens Interchangeable

Suppose both Billing and Orders have a `read` scope:

~~~text
billing-api: read
orders-api: read
~~~

These two scopes do not automatically share semantics. An access token must be bound to its intended resource, and the API must enforce permissions per the exact contract.

Clearer naming conventions can be used:

~~~text
billing.read
orders.read
inventory.read
~~~

Yet naming conventions still do not replace audience validation.

### 11.3. Resource Indicators

RFC 8707 defines Resource Indicators for OAuth 2.0. Clients can specify the resource for which the access token is intended.

Example token request:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
resource=https%3A%2F%2Fapi.example.com%2Forders
~~~

The AS can use `resource` to bind the token to the corresponding audience. How a resource URI maps to `aud` must be agreed upon between the AS and the Resource Server.

Not every AS supports RFC 8707. If unsupported, another verified audience mapping mechanism is needed.

### 11.4. Token Exchange When Calling Downstream APIs

If API A needs to call API B on behalf of a user, do not forward an `aud=api-a` access token to API B and expect B to accept it.

Options depending on architecture:

- Request a new access token intended for `api-b`.
- Use OAuth Token Exchange per RFC 8693 if supported by the AS.
- Use an on-behalf-of flow per vendor/AS contract.
- Keep actor/subject delegation semantics explicit.

API B must still verify the audience of the new token. Never rewrite the `aud` claim in an old JWT or forge an internal token by copying payloads.

## 12. Multi-Issuer: Issuer, Algorithm, and Audience Must Go Together

An API may trust multiple issuers:

~~~text
Issuer A -> JWKS A -> RS256 -> aud orders-api
Issuer B -> JWKS B -> ES256 -> aud orders-api
~~~

Do not use a vague policy such as:

~~~text
accept any issuer
accept any algorithm
accept any audience
```

Each issuer should have its own trust profile:

| Attribute | Issuer A | Issuer B |
|---|---|---|
| Canonical `iss` | URL A | URL B |
| JWKS URI | JWKS A | JWKS B |
| Allowed algorithm | RS256 | ES256 |
| Audience | orders-api | orders-api |
| Token type | at+jwt | at+jwt |
| Required claims | RFC 9068 + policy | RFC 9068 + policy |
| Client allowlist | clients A | clients B |

### 12.1. Selecting Managers Only from a Trusted Issuer Registry

You can use `JwtIssuerAuthenticationManagerResolver` with an allowlist:

~~~java
@Bean
AuthenticationManagerResolver<HttpServletRequest> issuerResolver() {
    return JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://issuer-a.example.com",
        "https://issuer-b.example.com"
    );
}
~~~

The resolver selects a manager by issuer, yet the token must still pass that issuer's decoder and validators. An unverified `iss` in the payload must never be used to grant access.

Each manager/decoder needs the proper algorithm allowlist, JWKS URI, audience, and token-type policy.

### 12.2. Do Not Use Issuer A's Key for Issuer B

Two issuers may both use:

~~~text
kid = signing-key-1
~~~

Yet their public keys differ. Never cache keys by `kid` alone; namespace them by issuer/JWKS source.

### 12.3. Do Not Fetch JWKS URLs from JWT Headers

Do not let `jku`, `x5u`, or an unverified claim control outbound key lookups. Doing so can enable SSRF and allow attackers to inject their keys into the trust path.

## 13. Opaque Tokens Also Need Resource Binding

Not every access token is a JWT. Opaque tokens have no JOSE `alg`, `typ`, or `kid` for the Resource Server to inspect locally.

For opaque tokens, the Resource Server calls an introspection endpoint:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <resource-server-credentials>

token=opaque-access-token
~~~

Illustrative response:

~~~json
{
  "active": true,
  "iss": "https://login.example.com",
  "sub": "user-42",
  "client_id": "storefront-web",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 2000000300
}
~~~

The Resource Server must verify:

- `active=true`.
- The token belongs to the appropriate issuer/introspection trust context.
- Audience/resource matches the API, if returned by the AS.
- Scopes/authorities match.
- Expiry and attributes per contract.

RFC 7662 allows the AS to return different responses depending on which protected resource calls introspection. If the response lacks `aud`, there must be an explicit contract that the endpoint/client authentication only returns active tokens valid for that resource server. Never assume every active opaque token is valid for every API.

Opaque tokens do not suffer from JOSE algorithm confusion, yet can still suffer from cross-API token substitution if resource binding is omitted.

## 14. Configuring HTTP Authorization After Token Authentication

After authentication and validation, Spring Security maps scopes to authorities, typically with the `SCOPE_` prefix.

Example:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/api/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

This snippet illustrates authorization only. It assumes `JwtDecoder` is already configured to check:

- Algorithm allowlist.
- Signature.
- Issuer.
- Access-token profile/type.
- Audience/resource.
- Time claims.

If a token intended for the Billing API carries `orders.read`, the decoder must reject it before authority mapping and HTTP authorization take place.

### 14.1. Authentication Failure vs. Authorization Failure

| Case | Typical Result | Reason |
|---|---:|---|
| `alg=none` | 401 | No valid signature |
| `HS256` when only RS256 is allowed | 401 | Disallowed algorithm |
| Invalid signature | 401 | Token cannot be authenticated |
| ID token sent to RFC 9068 API | 401 | Wrong token profile/type and audience |
| Access token with `aud=billing-api` sent to Orders API | 401 | Token not intended for this resource |
| Untrusted issuer | 401 | Wrong trust context |
| Valid token with right audience but missing scope | 403 | Authorization failure |
| Valid scope but order belongs to another tenant | 403/404 per policy | Business authorization |

Audience mismatch and wrong token type are authentication/profile validation failures, not merely missing endpoint permissions.

## 15. Testing Algorithm Confusion

A test suite must prove the decoder only accepts configured algorithms.

### 15.1. Test Matrix

| JWT | Decoder Configuration | Expected Result |
|---|---|---|
| RS256, right RSA key | RS256 allowlist | Pass if claims are valid |
| RS256, different key | RS256 allowlist | Reject signature |
| HS256, even using public key bytes as secret | RS256 allowlist | Reject algorithm |
| `alg=none` | RS256 allowlist | Reject |
| ES256 | RS256 allowlist | Reject |
| RS512 | RS256 allowlist | Reject |
| Header with `jku` pointing to attacker URL | Fixed JWKS URI | Do not fetch URL from header |
| Non-existent `kid` | Issuer's JWKS | Reject after key lookup/refresh per policy |

### 15.2. Use Dedicated Test Keys

- Generate an RSA key pair exclusively for tests.
- Use the private key to sign valid JWTs.
- Configure the decoder with the RSA public key or a test JWKS.
- Create another token signed with a different key pair.
- Create tokens with algorithms outside the allowlist.
- Verify the decoder rejects invalid tokens.

Never use production signing keys in unit/integration tests.

### 15.3. Do Not Test Only with `jwt()` Mocks

`MockMvc` with `.with(jwt())` or WebTestClient `.mockJwt()` generally creates a mock authentication and bypasses the decoder. They are useful for testing authorization, but do not prove the algorithm allowlist or signature verification.

To test algorithms, send `Authorization: Bearer <signed-token>` through the real filter chain with a real `JwtDecoder`.

## 16. Testing Token-Type Confusion

Create separate JWTs:

| Token Fixture | Header/Payload | Result at Orders API |
|---|---|---|
| Right-profile access token | `typ=at+jwt`, `aud=orders-api` | Pass if claims/permissions are valid |
| ID token | `typ` per OIDC provider, `aud=storefront-web` | Reject |
| Generic JWT | `typ=JWT`, no access-token profile | Reject if API requires RFC 9068 |
| Client assertion | Audience is token endpoint, not Orders API | Reject |
| Logout/security event token | Different token profile | Reject |
| Right access-token profile but wrong audience | `typ=at+jwt`, `aud=billing-api` | Reject |

### 16.1. Validly Signed ID Tokens Must Still Be Rejected

An essential test:

1. Sign an ID token with the exact same test key trusted by the decoder.
2. Use the exact same issuer.
3. Set `aud=storefront-web`.
4. Send that token to the Orders API.
5. Verify the API rejects it because token type/profile and audience do not match.

This test proves the system does not rely on signatures alone.

### 16.2. Testing `typ`

With RFC 9068:

- Accept `at+jwt` or `application/at+jwt`.
- Reject `JWT` if the profile validator requires the access-token type.
- Reject types from other tokens.
- Reject missing `typ` if required by the profile.
- Never alter behavior by disabling type validation while forgetting to attach the profile validator.

### 16.3. Do Not Assume Every AS Emits the Same Type

If the AS does not yet support RFC 9068, test against the actual profile. Never manually rewrite a JWT in tests to add `typ=at+jwt` and conclude the production issuer is already compatible.

## 17. Testing Audience/Resource Substitution

Create two APIs:

~~~text
orders-api
billing-api
~~~

And two tokens:

~~~json
{
  "iss": "https://login.example.com",
  "aud": ["orders-api"],
  "scope": "read"
}
~~~

~~~json
{
  "iss": "https://login.example.com",
  "aud": ["billing-api"],
  "scope": "read"
}
~~~

Tests:

| Request | Token | Result |
|---|---|---|
| Orders API | Audience orders-api | Pass if scope is sufficient |
| Orders API | Audience billing-api | 401 |
| Billing API | Audience billing-api | Pass if scope is sufficient |
| Billing API | Audience orders-api | 401 |
| Orders API | Audience contains both resources | Per defined multi-audience policy |
| Orders API | Missing `aud` | Reject |
| Orders API | Empty `aud` | Reject |

A test can assert that controllers/services are never invoked when the audience is wrong:

~~~java
mvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + billingToken))
    .andExpect(status().isUnauthorized());

verifyNoInteractions(ordersService);
~~~

This test requires `billingToken` to be signed with the test key and the request to go through the real decoder.

## 18. Testing Cross-Issuer and Key Confusion

If an API trusts multiple issuers:

- Issuer A and B have different keys.
- Both may use the same `kid`.
- Both may use the same algorithm.
- Each issuer has its own audience/token profile.

Tests:

1. Token A signed with key A and `iss=A`.
2. Token B signed with key B and `iss=B`.
3. Token A modified to `iss=B` while keeping signature A.
4. Token B sent to decoder A.
5. Both issuers using `kid=key-1`, confirming proper decoder/key namespacing.
6. Non-allowlisted issuer.
7. `jku` pointing to another host.
8. Issuer A's audience mismatched with resource B.

Never use a single global decoder that can accept keys from any issuer. Use trusted, configured issuer-specific managers/decoders.

## 19. Anti-Patterns to Avoid

### 19.1. Accepting Any `alg`

~~~java
// Flawed design: no explicit allowlist.
acceptAlgorithm(jwt.getHeaders().get("alg"));
~~~

Algorithms must be configured per issuer and key policy, not taken from the token header.

### 19.2. Allowing HS256 Just Because the API Uses RS256

Never use RSA public key bytes as an HMAC secret. If HMAC is needed, design separate shared-secret key management and never share keys with asymmetric signatures.

### 19.3. Checking Only the Signature

A JWT with a valid signature could still be an ID token, client assertion, or access token for another API. Type/profile, issuer, and audience validators are required.

### 19.4. Checking Only `sub`

`sub` does not prove a token is an access token or intended for the current resource.

### 19.5. Using `client_id` Instead of `aud`

Client ID identifies the OAuth client; audience identifies the recipient/resource. Never use one field in place of the other.

### 19.6. Using Scope Instead of Audience

A `read` scope can appear across many APIs. It does not prove the token was issued for the API handling the request.

### 19.7. Accepting ID Tokens at an API

ID tokens are issued to OIDC clients. Resource Servers must accept access tokens matching the supported profile.

### 19.8. Disabling Type Validation Without Adding a Replacement Validator

If using `.validateTypes(false)` for RFC 9068 integration, attach `JwtValidators.createAtJwtValidator()` per the corresponding version's documentation. Simply disabling type validation removes a layer distinguishing JWT profiles.

### 19.9. Trusting Arbitrary `jku`/`x5u`

Never let the JWT header dictate where the Resource Server fetches signing keys. Only use trusted issuer/JWKS URIs.

### 19.10. One Shared Validator for Every Issuer and Token Purpose

If the same issuer emits both ID tokens and access tokens, validation rules must be mutually exclusive. Use profile-specific decoders/validators when needed.

### 19.11. Accepting Any Audience

Never replace "audience contains this API's resource identifier" with "audience exists."

### 19.12. Testing Only with Mock Authentication

`jwt()`/`mockJwt()` can bypass signature, algorithm, issuer, type, and audience validation. Always test bearer requests with signed tokens.

### 19.13. Returning 403 for Wrong-Audience Tokens

A token not intended for an API is not authenticated at that API. Reject at authentication validation, typically with 401.

## 20. Safe Deployment Process

**Step 1 — Choose token profile.** Confirm whether the AS issues JWT access tokens per RFC 9068 or a custom profile.

**Step 2 — Confirm issuer and JWKS.** Select canonical issuer, JWKS URI, and key rotation contract.

**Step 3 — Lock down algorithms.** Configure an explicit allowlist, e.g. RS256. Verify key type and key usage.

**Step 4 — Define token type.** Require `typ=at+jwt` if using RFC 9068; if custom, define explicit type/claim rules.

**Step 5 — Define audience.** Choose a stable resource identifier for each API. Never use client ID instead of resource audience.

**Step 6 — Configure validators.** Signature, issuer, timestamps, audience, type/profile, and required claims.

**Step 7 — Configure authorization.** Map scopes/roles after successful authentication; verify tenant and ownership in the business layer.

**Step 8 — Write negative tests.** `alg=none`, HS/RS confusion, wrong `typ`, ID token, wrong issuer, wrong audience, and expired tokens.

**Step 9 — Test across multiple APIs.** Send API A's token to API B and confirm it is rejected.

**Step 10 — Roll out per issuer.** When changing algorithms or token profiles, coordinate the AS and Resource Servers with managed overlap and rollback phases.

## 21. Authentication Decision Matrix

| Signature / `alg` | Token Type | Issuer | Audience | Outcome |
|---|---|---|---|---|
| Valid | Access token | Valid | Orders API | Continue to expiry/scope checks |
| Invalid | Access token | Valid | Orders API | Reject |
| `alg` outside allowlist | Access token | Valid | Orders API | Reject |
| Valid | ID token | Valid | Web client | Reject at Orders API |
| Valid | Access token | Wrong | Orders API | Reject |
| Valid | Access token | Valid | Billing API | Reject at Orders API |
| Valid | Access token | Valid | Orders API | Missing scope -> 403 |
| Valid | Access token | Valid | Orders API | Wrong tenant/owner -> 403/404 per policy |
| Valid | Unknown token type | Valid | Orders API | Reject |
| Unsigned | Any | Any | Any | Reject |

Exact execution order may vary by decoder, but none of these conditions may be skipped.

## 22. Self-Check Questions

**1.** Why must the JWT header not choose the algorithm on its own?

> The header is unverified and sender-controlled. The Resource Server must use a preconfigured algorithm allowlist.

**2.** When does algorithm confusion between RS256 and HS256 happen?

> When an implementation mistakes an asymmetric public key for an HMAC secret or fails to bind keys to allowed algorithms.

**3.** Is `alg=none` allowed for OAuth JWT access tokens under RFC 9068?

> No. Access tokens must be signed and `none` is prohibited.

**4.** Does a valid JWT signature prove the token is an access token?

> No. It only proves the signature under the trust/key policy; token-type/profile validation is required.

**5.** Who is an OIDC ID token issued to?

> The OIDC client/Relying Party; `aud` must contain that client's client ID.

**6.** What does the access token audience represent?

> The Resource Server or resource identifier that the token was issued to access.

**7.** What does `typ=at+jwt` mean?

> The JWT is an OAuth 2.0 access token conforming to the RFC 9068 profile.

**8.** Are `token_type=Bearer` and JOSE `typ=at+jwt` the same?

> No. One specifies how the client presents the access token; the other identifies the JWT profile/type.

**9.** Can `client_id` replace `aud`?

> No. Client ID identifies the OAuth client; audience identifies the resource recipient.

**10.** Is the `orders.read` scope enough for the Orders API to accept a token?

> No. Right issuer, signature, token type, and audience are required before considering scopes.

**11.** Why can the same issuer and the same signing key still cause token-type confusion?

> Because an issuer can issue multiple JWT types; a shared signature does not distinguish purpose. Explicit typing and mutually exclusive validation rules are required.

**12.** Since which Spring Security version is the RFC 9068 validator available?

> `JwtValidators.createAtJwtValidator()` has been available since Spring Security 6.5.

**13.** Why does RFC 9068 code use `.validateTypes(false)`?

> To delegate JWT access-token type checking to the profile validator instead of Nimbus's default type verifier; `createAtJwtValidator()` must be attached immediately afterward per the version docs.

**14.** What should be returned when a token with `aud=billing-api` is sent to the Orders API?

> Reject authentication, typically 401, because the token is not intended for the Orders API.

**15.** What if a token has the right audience but lacks the required scope?

> The token is authenticated but lacks sufficient permissions, typically 403.

**16.** Can `jwt()` in MockMvc be used to prove an algorithm allowlist?

> No. `jwt()` creates a mock authentication; signed bearer tokens through a real decoder are required.

**17.** Can `jku` or `x5u` in a JWT header be trusted?

> Not if the URL is uncontrolled; only use JWKS/key sources belonging to a trusted issuer.

**18.** If an API must call another API on behalf of a user, should it forward the old access token?

> Only if the token's audience authorizes the target resource. Typically, a new token with the right audience, token exchange, or an on-behalf-of flow is required.

## 23. References

- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html): algorithm verification, key/algorithm binding, explicit typing, mutually exclusive validation rules, substitution, and cross-JWT confusion.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): `typ=at+jwt`, required claims, issuer/audience/signature validation, and access-token profile.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, `aud`, `azp`, `nonce`, and OIDC client-side validation.
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515.html): JOSE header and JWS signatures.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517.html): JWK, `kty`, `kid`, `use`, `key_ops`, and public key material.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519.html): JWT claims `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707.html): specifying resources in OAuth token requests.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html): token exchange and delegation across resources/services.
- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): algorithm allowlist, `NimbusJwtDecoder`, issuer/audience validation, and RFC 9068.
- [Spring Security 6.5 — Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): `JwtValidators.createAtJwtValidator()` and RFC 9068 configuration.
- [Spring Security — JwtValidators API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtValidators.html): `createAtJwtValidator()` and builder for the JWT access-token profile.
- [Spring Security — JWT Type Validation Migration](https://docs.spring.io/spring-security/reference/7.0/migration/servlet/oauth2.html): type validation changes in newer Spring Security lines.
- [Spring Security — Multi-tenancy Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): issuer-aware authentication manager and multi-issuer setup.

**Conclusion:** A Resource Server should only accept a JWT when the algorithm/key matches the trust policy, the token belongs to the right profile, the issuer is trusted, and the audience contains the API's own resource identifier. An algorithm allowlist prevents signature verification confusion; explicit typing and mutually exclusive validators prevent ID tokens or other-purpose JWTs from being used as access tokens; audience validation prevents an access token for one API from being sent to another API. Only after those steps does Spring Security map scopes/authorities and the application continue verifying tenant, ownership, and business permissions.
