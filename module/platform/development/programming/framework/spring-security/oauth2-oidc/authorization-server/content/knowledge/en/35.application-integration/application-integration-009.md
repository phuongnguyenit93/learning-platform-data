# Validating Claims Contracts, Algorithms, and Clock Skew Policies

## 1. Why Does a Resource Server Need an Explicit JWT Contract?

In the **Application Integration** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, we learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in a Spring Boot application.

The Authorization Server and Resource Server can be deployed, upgraded, and operated independently. The Authorization Server issues access tokens; the Resource Server receives tokens and decides whether to accept them for the current API. Both sides must agree on a **token contract**: which claims must be present, which claims may be absent, data types, semantics, signing algorithms, key identifiers, token types, and how timestamps are handled.

If the contract is only implicit in code, a small change on one side can break integration on the other. For example:

- The Authorization Server changes audience from a single URI to a list of URIs, while the Resource Server only reads a string.
- A Client Credentials grant sets subject to a user ID while the Resource Server interprets it as a service account.
- The Authorization Server switches from RS256 to ES256 while the Resource Server allows only RS256.
- Clock drift between two nodes causes a token to be treated as not yet valid or already expired.
- The Resource Server receives an ID Token or a JWT meant for another purpose and treats it as an access token.

A validly signed JWT is not enough to prove the token is suitable for an API. The Resource Server must validate structure, issuer, audience, timestamps, token type, algorithm, key, and business claims according to the contract.

### Learning Objectives

After this lesson, you will be able to:

- Define a JWT access token contract between an Authorization Server and a Resource Server.
- Distinguish required claims, optional claims, and application-specific private claims.
- Understand the semantics of iss, sub, aud, exp, iat, nbf, jti, client_id, scope, and tenant_id.
- Apply the JWT Access Token Profile per RFC 9068 when both sides need compliance with this profile.
- Restrict JWS algorithms and verify compatibility between algorithms and JWKs.
- Configure JwtTimestampValidator and clock skew in Spring Security 6.5.
- Add validators for required claims, token lifetime, and business claims.
- Manage contract and algorithm changes with compatible transition phases.
- Test signatures, claims, key rotation, timestamp boundaries, and clock drift.

## 2. What Does a JWT Contract Include?

A JWT contract should describe at least four groups:

| Group | What Must Be Agreed Upon | Examples |
| --- | --- | --- |
| JOSE header | Token type, algorithm, key identifier, and permitted headers. | typ, alg, kid. |
| Registered claims | Issuer, subject, audience, timestamps, and token identifier. | iss, sub, aud, exp, iat, nbf, jti. |
| Authorization claims | Permissions used by the Resource Server to make access decisions. | scope, roles, groups, entitlements. |
| Application claims | Domain-specific business attributes. | tenant_id, account_id, contract_version. |

The contract must specify whether each claim is required or optional, data types, trusted data sources, semantics by grant type, which resource servers may receive the token, accepted algorithms and key types, the validity window of tokens, and how backward-compatible changes are rolled out.

Do not treat a sample payload in documentation as a complete contract. The contract must also define missing claims, wrong claim types, multiple audiences, client credentials, user delegation, and legacy tokens during upgrade windows.

## 3. Distinguishing Generic JWTs from the JWT Access Token Profile

JWT is a general-purpose token format. The same format can be used for OIDC ID Tokens, OAuth access tokens, client assertions, logout tokens, or internal tokens. Different token types may contain identically named claims with different meanings and recipients.

| Token Type | Purpose | Consumer |
| --- | --- | --- |
| OIDC ID Token | Proves authentication result to an OIDC client. | Relying Party/OIDC client. |
| OAuth JWT Access Token | Authorizes access to a resource server. | Resource Server named in audience. |
| JWT Client Assertion | Authenticates an OAuth client at the Token Endpoint. | Authorization Server. |
| JWT Logout Token | Conveys an OIDC logout event. | OIDC client/Relying Party. |
| Internal JWT | Carries data for an internal workflow. | Component specified in the internal contract. |

### 3.1. Preventing Cross-JWT Confusion

An ID Token can have a valid signature and be signed by the same issuer as an access token. That does not make it an access token. If a Resource Server checks only signature and iss, tokens can be misused across contexts.

Differentiate JWT types using an appropriate combination:

- Token type in the typ header.
- Distinct audiences for each resource/use case.
- Separate issuers or signing keys when architecture demands.
- Distinct required claim sets and semantics.
- Validators that accept only the endpoint's expected profile.

RFC 8725 recommends explicit typing and separate validation rules to prevent one type of JWT from being accepted in another context. RFC 9068 defines a dedicated profile for JWT access tokens with typ set to at+jwt or application/at+jwt.

## 4. Core Claims and Semantics

### 4.1. Claim Table

| Claim | Data Type | Meaning | Validation Rule |
| --- | --- | --- | --- |
| iss | String/URI | Authorization Server that issued the token. | Must match the trusted issuer exactly. |
| sub | String | Subject represented by the token. | Must have clear semantics per grant; never assume always a user. |
| aud | String or array of strings | Resource server/recipient allowed to use the token. | Must contain the current API's identifier. |
| exp | NumericDate | Time when the token expires. | Must be present per contract and unexpired, allowing small clock skew. |
| iat | NumericDate | Time when the token was issued. | Check presence, not excessively in the future, and token age if policy requires. |
| nbf | NumericDate | Time when the token becomes valid. | If present, must not fall outside the allowed window. |
| jti | String | Unique ID of the token. | Must be present if contract requires; used for audit/denylist/replay detection when needed. |
| client_id | String | OAuth client that requested the token. | Distinguish client identity from subject. |
| scope | String | Granted scopes, typically space-delimited. | Contains only scopes approved for the audience. |
| tenant_id | String | Tenant to which the token belongs, if multi-tenant. | Must match a trusted issuer/tenant mapping. |

RFC 9068 specifies required claims for the JWT access token profile: iss, exp, aud, sub, client_id, iat, and jti. nbf is not in the general mandatory list of that profile, but if emitted, the Resource Server must enforce its semantics properly.

### 4.2. iss Must Match Exactly

iss identifies the Authorization Server. Compare the full issuer value, including scheme, host, port, and path if present. Do not strip paths or trailing slashes to create approximate matches.

In a multi-tenant model, the issuer often also defines the identity domain. Two tokens with the same sub from different iss values do not automatically represent the same principal.

### 4.3. sub Is Not Always a User ID

With Authorization Code Grant or grants representing a resource owner, sub is typically the user's subject identifier. With Client Credentials Grant, there is no resource owner; sub may be the client application's identifier or a service principal per contract.

The Resource Server should not force every sub into a users table. If a globally unique principal identifier across multiple issuers is needed, use the (iss, sub) pair or a trusted mapping.

### 4.4. aud Must Identify a Specific Resource

Audience answers the question: which API was this token issued for? A token can be validly signed and unexpired yet still must be rejected if aud does not contain the current API.

If a token serves multiple resources, the contract must define which scopes apply to each audience. Avoid issuing a token with multiple audiences and an ambiguous set of scopes that cannot be bound to specific resources.

### 4.5. client_id and sub Answer Two Different Questions

client_id identifies the OAuth application that requested the token. sub identifies the subject the token represents. In grants with user delegation, the two values usually differ. In Client Credentials, they may both point to a service identity per policy, yet you should never assume the two claims are always equal.

### 4.6. scope Must Have Clear Semantics

OAuth scopes are typically represented as a single string of space-separated values:

```json
{
  "scope": "orders.read orders.write"
}
```

Some systems use an array-typed scp claim. That is a custom contract choice; do not assume scope and scp are always equivalent. If a Resource Server supports both, define precedence and how conflicts are handled when both appear with different values.

## 5. Required, Optional, and Private Claims

### 5.1. Required Claims

A required claim is one without which a token cannot satisfy the API contract. For example, an API may require:

- iss: identifies the issuing source.
- aud: identifies the receiving API.
- sub: identifies the subject.
- exp: bounds usage lifetime.
- client_id: identifies the client.
- iat: issuance timestamp.
- jti: token identifier.
- scope: if the API contract requires the scope claim to always be present.
- tenant_id: if every API request must operate within a tenant.

Do not mark every claim as required merely because a current sample token happens to include it. For instance, auth_time, acr, and amr may appear only when the grant involves resource owner authentication and policy requires assurance details.

### 5.2. Optional Claims

Optional claims may be absent. The Resource Server must define explicit behavior when a claim is missing: ignore it in policy, apply a defined default value, or reject a specific feature that needs that claim.

Never fall back to a higher privilege level when an optional claim is missing.

### 5.3. Private Claims

Application-specific private claims should use collision-resistant names, especially when tokens are consumed across organizations or products. URI namespaces can be used:

```json
{
  "https://example.com/claims/contract_version": "1",
  "https://example.com/claims/tenant_id": "tenant-a"
}
```

Do not name custom claims identically to registered claims or reuse a standard claim name with different semantics. Keep data types stable: tenant_id as a string, roles as a string array, permissions as a well-defined permission set.

### 5.4. Do Not Put Sensitive Data in JWTs

JWS JWTs are signed, not encrypted by default. Clients and token holders can decode the payload. Include only claims necessary for the Resource Server; avoid passwords, secrets, sensitive identifiers, large profile payloads, or data unnecessary for authorization.

## 6. Designing Contracts by Grant Type

Not every grant shares the same subject semantics. Define token profiles by grant and resource.

| Grant | Subject (sub) | Client (client_id) | Claims Often Needed |
| --- | --- | --- | --- |
| Authorization Code | Authenticated user/resource owner. | Client application. | auth_time, acr, amr when policy requires. |
| Client Credentials | Service principal/client identity. | Service client. | tenant_id, workload identity, resource audience. |
| Device Authorization | User who completed confirmation on another device. | Device client. | User subject and consented scopes. |
| Token Exchange | Approved delegated subject/actor. | Client performing exchange. | act, may_act, audience, and scopes per supported profile. |
| Custom Grant | Subject determined by verified grant. | Authenticated client. | Grant identifier or tenant claim if policy permits. |

Never take sub from an unverified request parameter. The Authorization Server must derive the subject from authentication or a trusted grant record.

### 6.1. Scopes Must Match the Audience

If a token has audience orders-api, the scope orders.read must be meaningful on the Orders API. Do not include billing.write in the same token without an explicit policy tying it to another resource.

The Resource Server grants access only based on signed scopes accepted by the contract. It must still verify record-level permissions, tenant, and business relationships.

## 7. Example JWT Access Token Contract

The example below describes a token following an internal Orders API profile. This does not automatically claim RFC 9068 compliance; claiming compliance requires meeting all corresponding header and validation rules.

```json
{
  "iss": "https://auth.example.com",
  "sub": "user-8f31",
  "aud": ["https://orders-api.example.com"],
  "exp": 1794852300,
  "iat": 1794851700,
  "nbf": 1794851680,
  "jti": "9d5d1a5e-6f5a-4b6d-9e77-14d1ef4f52b1",
  "client_id": "storefront-web",
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-a",
  "https://example.com/claims/contract_version": "1"
}
```

Illustrative contract:

- Issuer is https://auth.example.com.
- Orders API is a required audience.
- sub is the verified subject.
- Token is valid between nbf and exp, with small clock skew applied.
- jti is unique within the token issuer's scope.
- Client ID is the application that requested the token.
- Scope uses OAuth space-delimited format.
- Tenant ID must match the tenant context determined by a trusted system.
- Contract version is string "1", not a number.

The Resource Server must reject tokens missing required claims, having wrong data types, wrong issuer/audience, or falling outside the validity window.

## 8. Standardizing with RFC 9068

RFC 9068 defines the JWT Profile for OAuth 2.0 Access Tokens so different Authorization Server and Resource Server implementations can agree on structure and validation rules.

Key aspects of the profile:

- JWT access tokens must be signed; the none algorithm is forbidden.
- Header typ must be at+jwt or application/at+jwt.
- Required claims include iss, exp, aud, sub, client_id, iat, and jti.
- Resource Server must validate exact issuer, audience containing its own resource identifier, and signature using the Authorization Server's key.
- Scopes in the token must be meaningful for the resource named in the audience.
- A small leeway may be allowed to handle clock skew.

RFC 9068 is a concrete profile. If an existing system uses typ JWT and a custom claim set, do not switch only the Resource Server validator to RFC 9068 without updating the Authorization Server and testing compatibility.

### 8.1. Distinguishing JWT and at+jwt

typ JWT indicates only that the token is a JWT in general. typ at+jwt explicitly identifies the token as an OAuth JWT access token per RFC 9068.

Spring Security 6.5 provides JwtTypeValidator.jwt() to accept typ JWT or absent typ under default validator configurations. When adopting RFC 9068, the decoder must switch type validation to JwtValidators.createAtJwtValidator() instead of letting the generic validator reject at+jwt.

### 8.2. Configuring RFC 9068 on the Resource Server

The following example uses Spring Security 6.5 APIs:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration(proxyBeanMethods = false)
public class Rfc9068JwtDecoderConfig {

    private static final String ISSUER =
            "https://auth.example.com";
    private static final String AUDIENCE =
            "https://orders-api.example.com";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(ISSUER)
                        .jwsAlgorithm(SignatureAlgorithm.RS256)
                        .validateTypes(false)
                        .build();

        decoder.setJwtValidator(
                JwtValidators.createAtJwtValidator()
                        .issuer(ISSUER)
                        .audience(AUDIENCE)
                        .build());

        return decoder;
    }
}
```

createAtJwtValidator() validates the RFC 9068 profile, including typ and required claims. If the API accepts tokens only from one specific client, you can add clientId("orders-service-client"). If the API serves multiple clients, do not pin a single client ID; keep a validator checking the presence and type of client_id per contract.

This example uses the profile validator's default clock skew. If a different clock skew policy is needed, explicitly define how to replace the timestamp validator and re-test all required claim validations; never drop the profile validator just to keep a time check.

## 9. Contract Versioning and Compatible Changes

JWT access tokens are typically short-lived, yet during rollout windows a Resource Server may receive tokens issued by multiple Authorization Server versions. Therefore, contract changes require a compatibility phase.

### 9.1. Normally Backward-Compatible Changes

- Adding a new optional claim that older Resource Servers ignore.
- Adding a new scope without granting it to legacy clients.
- Adding metadata that does not alter semantics of existing claims.
- Bumping contract documentation version while keeping schema and behavior unchanged.

### 9.2. Breaking Integration Changes

- Changing a claim's type from string to array.
- Renaming scope to scp without dual support.
- Changing the semantics of sub.
- Changing iss or audience identifiers.
- Removing a required claim.
- Changing typ from JWT to at+jwt before Resource Servers are updated.
- Changing signing algorithm before decoders allowlist the new algorithm.
- Reducing clock skew or TTL such that currently issued tokens are rejected.

### 9.3. Contract Upgrade Workflow

1. Document the current contract and active consumers.
2. Add support for reading the new claim/algorithm in Resource Servers first.
3. Roll out the Authorization Server issuing tokens under the new contract or transition state.
4. Monitor old/new token ratios and validation errors.
5. Wait until old tokens expire plus clock skew and an operational buffer.
6. Remove legacy validators/algorithms once no valid legacy tokens remain to support.

Do not keep weak algorithms or obsolete claims indefinitely just to avoid change. Compatibility windows must have a defined end date and clear observability criteria.

## 10. Choosing Signing Algorithms

### 10.1. Algorithm Is an Application Policy

The alg header carried by a token is not a decision the Resource Server may blindly trust. The Resource Server must pre-configure an allowlist of accepted algorithms; the library verifies signatures using only algorithms in that allowlist.

Spring Security 6.5 NimbusJwtDecoder trusts only RS256 by default. It can be configured explicitly via Spring Boot:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com
          jws-algorithms: RS256
```

Or configured directly via the builder:

```java
NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withIssuerLocation("https://auth.example.com")
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();
```

Never accept none. Never automatically allow every algorithm simply because a JWK Set response or token header advertises it.

### 10.2. Comparing Algorithm Families

| Family | Examples | Characteristics | Notes |
| --- | --- | --- | --- |
| RSA PKCS#1 v1.5 | RS256, RS384, RS512 | Common, broad compatibility, uses private/public keys. | RS256 is trusted by default in Spring Security 6.5. |
| RSA-PSS | PS256, PS384, PS512 | Uses RSA with PSS padding. | Both sides must support the same algorithm and compatible keys. |
| ECDSA | ES256, ES384, ES512 | Compact signatures using elliptic curves. | Curve and algorithm must match. |
| HMAC | HS256, HS384, HS512 | Shared secret for signing and verification. | Resource Server must hold a signing-capable secret; never publish secrets in JWKS. |

With an Authorization Server and multiple independent Resource Servers, asymmetric signatures are usually a better fit: the Authorization Server holds the private key, and Resource Servers need only the public key. If Resource Servers hold a shared HMAC secret, one compromised Resource Server could forge tokens accepted by other components.

### 10.3. Never Use Weak Algorithms or Infer from Tokens

RFC 8725 requires applications to verify algorithms, constrain supported algorithms, and bind each key to its corresponding algorithm. Never:

- Accept alg none.
- Use the same key with incompatible algorithms.
- Let a token dictate the key URL or key material.
- Downgrade algorithms when signature verification fails.
- Treat an HMAC secret as if it were a public key.

## 11. Compatibility Between JWS Algorithms and JWKs

The signing algorithm must match the key type:

| JWS Algorithm | JWK kty | Key Parameters That Must Match |
| --- | --- | --- |
| RS256 | RSA | RSA public modulus/exponent and corresponding private key at the Authorization Server. |
| PS256 | RSA | RSA key used with RSA-PSS. |
| ES256 | EC | Curve P-256. |
| ES384 | EC | Curve P-384. |
| ES512 | EC | Curve P-521. |

A JWK can include kid, kty, use, key_ops, alg, and key parameters. kid must uniquely identify a key within the published key set. If a JWK declares alg, its value must match the token signing algorithm.

The Resource Server must select public keys from a configured JWKS or one discovered via a trusted issuer. Never use jku, x5u, or any URL specified in a JWT header to fetch keys.

### 11.1. Configuring Multiple Algorithms During Migration

Spring Security allows configuring multiple algorithms by calling jwsAlgorithm multiple times:

```java
NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withIssuerLocation("https://auth.example.com")
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .jwsAlgorithm(SignatureAlgorithm.PS256)
                .build();
```

Allow multiple algorithms concurrently only when executing a defined migration plan. Monitor active tokens being issued; once no valid tokens remain under the old algorithm, remove it from the allowlist.

### 11.2. kid Does Not Replace Algorithm Validation

kid only helps locate a key. It does not prove a token is trustworthy. The decoder must still validate signature, algorithm, issuer, and audience. If kid does not exist or the key is incompatible with the algorithm, reject the token.

## 12. Synchronizing Algorithms on the Authorization Server

The Authorization Server must issue JWTs using an algorithm accepted by Resource Servers. When using Spring Authorization Server, JwtGenerator uses JwtEncoder and an appropriate JWK to sign tokens.

The operational contract must specify the active algorithm, key type and curve/size, kid of the current signing key, JWK Set URI publishing public keys, start/end timestamps for algorithm migration, and retention window for old keys to verify unexpired tokens.

Never rotate signing algorithms merely by changing configuration on the Authorization Server. Resource Servers must update their allowlist before new tokens are issued.

### 12.1. Setting Token Type and Custom Claims at the Authorization Server

Spring Authorization Server lets you customize JWT headers and claims via OAuth2TokenCustomizer<JwtEncodingContext>. If your system adopts RFC 9068, you can set type at+jwt for access tokens and add namespaced contract claims:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Configuration(proxyBeanMethods = false)
public class JwtContractCustomizerConfig {

    @Bean
    OAuth2TokenCustomizer<JwtEncodingContext> jwtContractCustomizer() {
        return context -> {
            if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
                context.getJwsHeader().type("at+jwt");
                context.getClaims().claim(
                        "https://example.com/claims/contract_version", "1");
            }
        };
    }
}
```

Enable this snippet only once Resource Servers are configured to accept RFC 9068. If the application already defines an OAuth2TokenCustomizer<JwtEncodingContext>, merge the logic into the existing customizer; avoid accidentally creating multiple beans of the same generic type. Tenant, role, or permission claims must come from trusted server sources, never copied directly from request parameters.

## 13. What Is Clock Skew?

Machines in a distributed system may not share the exact same clock time. The Authorization Server might issue a token at 12:00:00 while a Resource Server's clock runs 20 seconds fast. If the token sets nbf to issuance time, the Resource Server might think the token is not yet valid.

Conversely, if the Resource Server runs slow, it might continue accepting a token past its true exp timestamp.

Clock skew is a small tolerance window permitted by the Resource Server to absorb clock drift between systems.

Spring Security uses JwtTimestampValidator to check a token's validity window:

- nbf: token must not be used before its not-before time.
- exp: token must not be used at or after its expiration time.

In Spring Security 6.5, the default clock skew is 60 seconds.

### 13.1. Validity Window with Skew

With clock skew S, the accepted current time window can be visualized as:

```text
nbf - S <= now < exp + S
```

This illustrates policy leeway interpretation. It means a token may be accepted slightly before nbf and slightly after exp.

Clock skew does not alter timestamps inside the token, does not extend the exp issued by the Authorization Server, and does not replace clock synchronization. It only adjusts how the Resource Server evaluates time boundaries.

### 13.2. Choosing a Small Skew

A value like 30 or 60 seconds is usually sufficient in environments with healthy NTP/chrony. RFC 9068 permits a small leeway, typically no more than a few minutes, to handle clock skew.

Do not set an excessively large skew to mask a misconfigured system clock. The larger the skew, the wider the window where tokens work beyond their nominal lifetime, especially around expiration boundaries.

## 14. Configuring Clock Skew with JwtTimestampValidator

Spring Security 6.5 provides a constructor taking a Duration:

```java
import java.time.Duration;

import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

JwtTimestampValidator timestampValidator =
        new JwtTimestampValidator(Duration.ofSeconds(45));
```

Example Resource Server using custom issuer, audience, type, and timestamp validators:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.JwtTypeValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration(proxyBeanMethods = false)
public class ResourceServerJwtContractConfig {

    private static final String ISSUER = "https://auth.example.com";
    private static final String AUDIENCE = "https://orders-api.example.com";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(ISSUER)
                        .jwsAlgorithm(SignatureAlgorithm.RS256)
                        .build();

        OAuth2TokenValidator<Jwt> validators =
                new DelegatingOAuth2TokenValidator<>(
                        new JwtTimestampValidator(Duration.ofSeconds(45)),
                        new JwtIssuerValidator(ISSUER),
                        JwtTypeValidator.jwt(),
                        audienceValidator(),
                        requiredClaimsValidator());

        decoder.setJwtValidator(validators);
        return decoder;
    }

    private OAuth2TokenValidator<Jwt> audienceValidator() {
        return jwt -> jwt.getAudience() != null &&
                jwt.getAudience().contains(AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error("invalid_token", "Invalid audience", null));
    }

    private OAuth2TokenValidator<Jwt> requiredClaimsValidator() {
        return jwt -> {
            boolean valid = jwt.getIssuer() != null
                    && jwt.getSubject() != null
                    && !jwt.getSubject().isBlank()
                    && jwt.getAudience() != null
                    && !jwt.getAudience().isEmpty()
                    && jwt.getExpiresAt() != null
                    && jwt.getIssuedAt() != null
                    && jwt.getId() != null
                    && !jwt.getId().isBlank()
                    && jwt.getClaimAsString("client_id") != null
                    && !jwt.getClaimAsString("client_id").isBlank();

            return valid
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error(
                                    "invalid_token", "Required claim is missing", null));
        };
    }
}
```

This example intentionally lists validators explicitly in order to set a 45-second clock skew. When constructing a validator chain manually, keep all checks required for your active profile. JwtTypeValidator.jwt() suits token type JWT or absent typ; if your contract uses RFC 9068 at+jwt, use JwtValidators.createAtJwtValidator() as in section 8.

If an internal contract requires the typ header to be present with the exact value JWT, replace JwtTypeValidator.jwt() with new JwtTypeValidator("JWT"). The jwt() validator allows typ to be absent; strict choices must match how the Authorization Server actually emits tokens.

If using JwtValidators.createDefaultWithIssuer(ISSUER), Spring Security already provides a standard validator covering issuer, timestamps with default 60-second skew, and token type. When changing skew, do not merely add another validator thinking the default validator was replaced; build the chain explicitly as shown and verify no validator is omitted.

## 15. Using a Fixed Clock to Test Time Boundaries

JwtTimestampValidator supports setClock(Clock) for deterministic testing without depending on the host machine's wall clock:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-16T12:00:00Z"),
        ZoneOffset.UTC);

JwtTimestampValidator validator =
        new JwtTimestampValidator(Duration.ofSeconds(30));
validator.setClock(fixedClock);
```

With a fixed clock, tests can construct tokens right on the boundaries:

| Token Timestamp | Current Time | Result with 30s Skew |
| --- | --- | --- |
| nbf = now - 1 minute | now | Valid if other checks pass. |
| nbf = now + 20 seconds | now | Still within leeway. |
| nbf = now + 45 seconds | now | Rejected. |
| exp = now - 20 seconds | now | Still within expiration leeway. |
| exp = now - 45 seconds | now | Rejected. |
| exp = now + 5 minutes | now | Not yet expired. |

These tests help catch confusion around UTC timestamps, timezones, and comparison logic. NumericDate is seconds since the Unix epoch; never emit exp as an ISO-8601 date string.

## 16. iat Is Not the Same as exp and nbf

JwtTimestampValidator focuses on the validity window via exp and nbf. The iat claim indicates issuance time; having iat alone does not cap a token's maximum age.

If policy requires rejecting tokens with iat too far in the future, rejecting tokens older than 10 minutes, ensuring exp is after iat, or enforcing a maximum TTL of 15 minutes, add a dedicated validator.

Example:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class IssuedAtPolicyValidator
        implements OAuth2TokenValidator<Jwt> {

    private final Clock clock;
    private final Duration allowedFutureSkew;
    private final Duration maxTokenAge;
    private final Duration maxTokenLifetime;

    public IssuedAtPolicyValidator(
            Clock clock,
            Duration allowedFutureSkew,
            Duration maxTokenAge,
            Duration maxTokenLifetime) {
        this.clock = clock;
        this.allowedFutureSkew = allowedFutureSkew;
        this.maxTokenAge = maxTokenAge;
        this.maxTokenLifetime = maxTokenLifetime;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        Instant issuedAt = jwt.getIssuedAt();
        Instant expiresAt = jwt.getExpiresAt();
        Instant now = this.clock.instant();

        if (issuedAt == null || expiresAt == null) {
            return failure();
        }
        if (issuedAt.isAfter(now.plus(this.allowedFutureSkew))) {
            return failure();
        }
        if (issuedAt.isBefore(now.minus(this.maxTokenAge)
                .minus(this.allowedFutureSkew))) {
            return failure();
        }
        if (!expiresAt.isAfter(issuedAt)) {
            return failure();
        }
        if (Duration.between(issuedAt, expiresAt)
                .compareTo(this.maxTokenLifetime) > 0) {
            return failure();
        }
        return OAuth2TokenValidatorResult.success();
    }

    private OAuth2TokenValidatorResult failure() {
        return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                        "invalid_token",
                        "The token violates the issued-at policy",
                        null));
    }
}
```

This validator is an application-level policy add-on, not default Spring Security behavior. Choose maxTokenAge and maxTokenLifetime consistent with the TTL issued by the Authorization Server. If legitimate tokens can live longer than these limits, the Resource Server will reject them even while exp remains in the future.

Never use clock skew to allow an arbitrary future iat. Leeway handles minor clock drift only; tokens with anomalous issuance times must still be rejected.

## 17. Synchronizing Clocks in Distributed Environments

Clock skew is a last-resort tolerance buffer, not a substitute for clock synchronization.

Operational practices:

- Run NTP or chrony on servers and container hosts.
- Synchronize UTC across the Authorization Server, Resource Servers, databases, and audit systems.
- Monitor clock offset and alert when thresholds are exceeded.
- Avoid changing JVM timezones to work around time drift.
- Never use client-supplied timestamps as the basis for token validation.
- Keep clock skew consistent across contracts and configurations for Resource Servers sharing a policy.

If a node has a 3-minute clock offset while clock skew is 45 seconds, rejecting tokens is the intended behavior. Fix the time infrastructure instead of increasing skew to 5 minutes.

### 17.1. How Does Clock Skew Affect Revocation and TTL?

Because JWTs are self-contained, Resource Servers usually do not query the Authorization Server per request. If a token is revoked at the Authorization Server while Resource Servers lack introspection or denylists, the token can still be accepted until expiration as evaluated by validators and leeway.

Thus, short TTLs shrink the exposure window of compromised tokens; large clock skew widens the acceptance window around expiration; and key rotation does not revoke tokens while the old key stays in JWKS. If immediate revocation is needed, consider opaque tokens/introspection, jti denylists, or an appropriate stateful mechanism.

## 18. Key Rotation and Algorithm Migration Policies

Algorithms and keys are part of the contract. When changing keys or algorithms, the Resource Server must be able to verify both old and new tokens during the transition period.

Same-algorithm key rotation workflow:

1. Generate a new key with a new kid.
2. Publish the new public key in JWKS.
3. Update Resource Servers if the new algorithm is not yet allowlisted.
4. Switch the Authorization Server to sign with the new private key.
5. Retain the old public key long enough for existing tokens to remain valid plus clock skew and a buffer.
6. Remove the old public key once no valid tokens still rely on it.

Algorithm migration workflow, e.g., RS256 to PS256, requires coordinating allowlists:

- Resource Servers allow both RS256 and PS256 for a short window.
- Authorization Server starts signing new tokens with PS256.
- Monitor remaining RS256 tokens and their expiration times.
- After the overlap period ends, remove RS256 from the allowlist.

Never retain legacy algorithms forever. Never reuse a kid for different key material within the same issuer/key set.

## 19. Securing the Claim Contract

### 19.1. Do Not Trust Claims Before Verifying the Signature

A JWT payload can be parsed before signature verification, yet it must never be used to grant permissions, select tenants, query databases, or call URLs. Only consume claims after JwtDecoder succeeds.

### 19.2. Never Use Arbitrary Claim URLs as Endpoints

Claims such as iss, jku, x5u, tenant_url, or resource_uri can be abused if an application uses them to call network endpoints without an allowlist. Metadata/JWKS URIs must come from configuration or a trusted issuer registry.

### 19.3. Do Not Escalate Privileges from Unrecognized Claims

Do not map every string in roles, groups, or permissions into an authority. Resource Servers must enforce explicit allowlists or mappings. A claim named admin does not automatically make a principal an administrator.

### 19.4. Claims Must Have Authoritative Data Sources

| Claim | Recommended Source |
| --- | --- |
| iss | AuthorizationServerSettings/issuer configuration. |
| sub | Authenticated principal or verified grant. |
| aud | Policy-approved resource parameter or scope-to-resource mapping. |
| client_id | Authenticated RegisteredClient. |
| scope | Approved scopes after applying client/grant/consent policies. |
| tenant_id | Verified tenant context, never taken directly from arbitrary headers. |
| roles/permissions | Trusted authorization service or entitlement store. |

## 20. Testing Claims Contracts, Algorithms, and Clock Skew

Testing should include unit tests for validators, integration tests with genuinely signed JWTs, and operational tests for key rotation/clocks.

| Category | Scenario | Expected |
| --- | --- | --- |
| Required claim | Missing iss, sub, aud, exp, iat, jti, or client_id per contract. | invalid_token. |
| Claim type | aud is an object or client_id is a number. | Rejected. |
| Issuer | iss differs by one character or has wrong path. | Rejected. |
| Audience | aud lacks API identifier. | Rejected. |
| Subject | Client Credentials token interpreted as non-existent user. | Policy rejects or handles service principal per contract. |
| Scope | Scope absent from contract or unbound to audience. | Access denied. |
| Tenant | tenant_id mismatches issuer/tenant mapping. | Rejected. |
| Token type | ID Token or internal JWT sent as an API access token. | Rejected due to profile/type/audience. |
| Algorithm | alg is none or outside allowlist. | Rejected. |
| Key compatibility | RSA token verified against EC key or unknown kid. | Rejected. |
| Signature | Payload/header modified after signing. | Rejected. |
| nbf boundary | Inside vs. outside clock skew. | Matches policy outcome. |
| exp boundary | Newly expired token still within leeway. | Accepted within leeway; rejected beyond leeway. |
| iat future | Issued-at exceeds allowed future skew. | Rejected. |
| Maximum age | Token older than maxTokenAge. | Rejected if policy is enabled. |
| Maximum TTL | Interval exp - iat exceeds limit. | Rejected if policy is enabled. |
| Key rotation | Token uses new key after JWKS update. | Verified. |
| Key overlap | Old token still valid and old public key still in JWKS. | Continues to verify. |
| Algorithm migration | RS256 and PS256 during overlap window. | Only the two allowlisted algorithms are accepted. |
| Contract migration | Old and new token versions during compatibility window. | Follows migration policy. |
| Clock drift | Resource Server clock skewed inside/outside threshold. | Matches clock skew rules. |
| Missing typ | Token lacks typ when contract requires explicit typing. | Rejected. |

### 20.1. Unit Testing Custom Validators

Construct test Jwt instances with Jwt.withTokenValue(...), setting headers and claims per contract. Use Clock.fixed(...) to test exact timestamps. Verify valid cases as well as each missing or mistyped claim.

Validator unit tests do not prove signature verification works. They only test policy logic on an already-constructed Jwt object.

### 20.2. Integration Testing with Real Signatures

Generate test RSA/EC key pairs and sign real JWTs. Configure NimbusJwtDecoder with the test public key/JWKS, then send requests to protected endpoints.

Test altering the payload, alg header, kid, issuer, audience, timestamps, and token type. Invalid modifications must be rejected by the decoder before authorization policies run.

### 20.3. Testing Clock Skew with Fixed Time

With a 30-second skew, test these points:

- nbf 1 second before now.
- nbf 29 seconds after now.
- nbf 31 seconds after now.
- exp 29 seconds ago.
- exp 31 seconds ago.

This verifies boundary behavior without tests depending on machine execution speed.

## 21. Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Token has valid signature but is rejected | Issuer/audience/required claim mismatch. | Inspect verified claims and compare against contract. |
| Invalid signature | Wrong key, wrong kid, wrong algorithm, or tampered token. | Check JWK, signing algorithm, and token source. |
| Unsupported algorithm | Resource Server has not allowlisted the signing algorithm. | Update allowlist carefully before switching signing keys. |
| Invalid typ | Disagreement between JWT and at+jwt. | Define profile and use matching type validator. |
| Missing required claim | Authorization Server does not emit claim per contract. | Check grant, token customizer, and contract schema. |
| Newly issued token fails not-before | Resource Server clock runs fast or wrong nbf. | Check NTP and issuance timestamp. |
| Token expires early | Resource Server clock runs fast or skew is too small. | Check clock offset and leeway policy. |
| Token remains usable past exp | Clock skew wider than expected. | Reduce skew appropriately and evaluate TTL. |
| Future iat still accepted | Default validator does not enforce custom issued-at policy. | Add IssuedAtPolicyValidator if contract requires. |
| New tokens fail after rotation | New public key not published yet or algorithm not allowlisted. | Publish JWKS first, then switch signing key. |
| Old tokens fail immediately after rotation | Old public key removed too early. | Keep key overlap through token lifetime plus skew. |
| Resource Server and Authorization Server interpret claims differently | Unversioned contract or undocumented semantics. | Standardize contract, test consumers, and roll out overlapping migration. |

## 22. Hands-on Exercises and Checklist

### Exercise 1 — Write a JWT Contract

Define required and optional claims for the Orders API. Specify data types, semantics, issuer, audience, subject, scopes, tenant, and token lifetime.

### Exercise 2 — Add a Required Claims Validator

Create a validator checking iss, sub, aud, exp, iat, jti, and client_id. Send tokens missing each claim and confirm all are rejected.

### Exercise 3 — Restrict Algorithms

Configure the Resource Server to accept RS256 only. Sign tokens with RS256, PS256, and none; confirm only the allowlisted algorithm is accepted.

### Exercise 4 — Adjust Clock Skew

Configure a 45-second skew and use a fixed Clock. Test nbf/exp just inside and outside the boundaries.

### Exercise 5 — Enforce iat and Token Lifetime

Add IssuedAtPolicyValidator limiting token age to 10 minutes and TTL to 15 minutes. Test future-issued tokens and tokens exceeding the TTL cap.

### Exercise 6 — Adopt RFC 9068

Configure the Authorization Server to emit typ at+jwt for access tokens. Configure the Resource Server with JwtValidators.createAtJwtValidator(), then verify an ID Token cannot be used in place of an access token.

### Exercise 7 — Algorithm/Key Migration

Configure the Resource Server to accept RS256 and PS256 during a transition window. Switch the Authorization Server to PS256, retain the old key in JWKS, and then remove RS256 once legacy tokens expire.

### Completion Checklist

- [ ] Documented JWT contract exists between Authorization Server and Resource Server.
- [ ] Required/optional claims and data types are defined.
- [ ] Subject (sub) semantics per grant type are clear.
- [ ] iss and aud are validated accurately.
- [ ] client_id, scope, jti, and tenant claims come from trusted sources.
- [ ] Generic JWTs are distinguished from the RFC 9068 access token profile.
- [ ] Token type is validated according to the contract.
- [ ] Signing algorithms are allowlisted.
- [ ] JWKs match algorithms and use stable kids.
- [ ] none and token-supplied key URLs are rejected.
- [ ] Clock skew is small and consistent across Resource Servers.
- [ ] iat/max token age checks exist if required by policy.
- [ ] Infrastructure clocks are synchronized to UTC.
- [ ] Key rotation/algorithm migrations include overlap windows.
- [ ] Missing/mistyped claims, signatures, algorithms, and timestamp boundaries are tested.
- [ ] Raw JWTs and sensitive claim data are never logged.

## 23. References

- [Spring Security 6.5 — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html) — trusted algorithms, custom validators, RFC 9068 validation, and timestamp/clock skew.
- [Spring Security 6.5 API — JwtTimestampValidator](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/JwtTimestampValidator.html) — configuring Duration clock skew and Clock.
- [Spring Security 6.5 API — JwtValidators](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/JwtValidators.html) — default validators and RFC 9068 builder.
- [Spring Security 6.5 API — JwtTypeValidator](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/JwtTypeValidator.html) — verifying the typ header.
- [Spring Authorization Server 1.5.8 — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html) — OAuth2TokenCustomizer, JwtEncodingContext, JwtGenerator, and token claims.
- [Spring Authorization Server 1.5.8 — How-to: Add authorities as custom claims in JWT access tokens](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-custom-claims-authorities.html) — customizing claims for JWT access tokens.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html) — required claims, typ at+jwt, audience, and validation.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html) — algorithm verification, issuer/subject, audience, and cross-JWT confusion.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519.html) — registered claims and NumericDate.
- [RFC 7518 — JSON Web Algorithms](https://www.rfc-editor.org/rfc/rfc7518.html) — JWS/JWE algorithms and key compatibility.

**Conclusion:** A JWT contract must be jointly defined between the Authorization Server and Resource Server, covering claim semantics, data types, token type, audience, signing algorithms, and validity windows. Spring Security 6.5 provides validators for issuer, type, timestamps, claims, and RFC 9068; Resource Servers must configure an algorithm allowlist and a small clock skew matched to infrastructure. When changing claims, keys, or algorithms, roll out changes across compatible transition phases, test tokens at time boundaries, and retire legacy contracts only after older tokens are no longer valid.
