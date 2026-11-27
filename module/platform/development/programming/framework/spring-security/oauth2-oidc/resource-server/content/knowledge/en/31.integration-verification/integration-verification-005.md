# Rejecting ID Tokens or Tokens Intended for Another API by Contract

## 1. Goal: A Valid Signature Alone Is Not Enough

A JWT may be properly signed by the Authorization Server, carry a trusted issuer, and remain unexpired, yet the Resource Server must still reject it if that token was not issued to call this API.

Two cases must be distinguished:

1. **An OIDC ID token** is issued to an OIDC client to confirm a login outcome. It is not an access token for calling a Resource Server.
2. **An access token meant for another API** may be a valid access token, yet its audience/resource does not match the API receiving the request.

Example system with three components:

```text
OIDC client:       web-client
Orders API:        orders-api
Inventory API:     inventory-api

ID token:
  aud = web-client
  purpose = confirm login for web-client

Access token A:
  aud = orders-api
  purpose = call Orders API

Access token B:
  aud = inventory-api
  purpose = call Inventory API
```

If Orders API receives the ID token or Access token B, it must reject the token even though its signature can be verified with the same issuer public key.

**Core rule:** signature verification answers "was the token signed by a trusted key?". Audience and token-profile validation answer "was this token issued for use at the current API?". The Resource Server must enforce both.

## 2. ID Tokens and Access Tokens Serve Different Purposes

OpenID Connect builds on OAuth 2.0 and adds the ID token to convey user authentication results to the Relying Party (OIDC client).

| Characteristic | ID Token | Access Token |
| --- | --- | --- |
| Purpose | Confirms authentication details for the OIDC client. | Grants access to protected resources. |
| Typical audience | Client ID of the signing-in application. | Identifier of the Resource Server/API. |
| Primary consumer | OIDC client/Relying Party. | Resource Server. |
| Common claims | iss, sub, aud, exp, iat; possibly nonce, auth_time, at_hash, azp. | iss, sub, aud, exp, iat, scope/scp; possibly client_id, jti, cnf. |
| Authorizes API calls? | Does not grant API access on its own. | Can be used as an API credential if it passes all validation and authorization policies. |

Example ID token:

```json
{
  "iss": "https://login.example.test",
  "sub": "user-123",
  "aud": ["web-client"],
  "exp": 1893456000,
  "iat": 1893452400,
  "nonce": "login-request-nonce",
  "auth_time": 1893452300
}
```

Example access token for Orders API:

```json
{
  "iss": "https://login.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "iat": 1893452400,
  "scope": "orders:read orders:write"
}
```

Both tokens can share the same issuer, subject, and signing key. They still differ in purpose and audience.

### 2.1. An ID Token Is Not an Access Token Just Because Both Are JWTs

JWT is a format for representing signed or encrypted claims. It does not by itself define a token's purpose. Both an ID token and an access token can be compact JWS strings:

```text
base64url(header).base64url(payload).base64url(signature)
```

Therefore, checking "is it a parseable JWT" or "is the signature valid" is not enough to decide whether the token may be used on an API.

### 2.2. Never Send an ID Token to a Resource Server

The OIDC client uses the ID token to verify the authentication response under the OIDC contract. When calling an API, the client must send the access token issued for that resource:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token-for-orders-api>
```

Never send an ID token in the Authorization header. Having `sub`, username, or email inside an ID token does not turn it into an API credential.

## 3. Audience Is the Boundary Between APIs

The `aud` claim identifies the intended recipient(s) of the JWT. The Resource Server must compare the verified audience against the API's own identifier.

Example:

```json
{
  "iss": "https://login.example.test",
  "aud": ["inventory-api"],
  "scope": "inventory:read"
}
```

Inventory API may accept this token if all other checks pass. Orders API must reject it because the audience does not include `orders-api`.

### 3.1. Audience Differs from Issuer

| Claim | Question |
| --- | --- |
| iss | Who issued the token? |
| aud | Which resource/recipient is the token intended for? |
| sub | Which subject does the token represent? |
| scope or scp | Which actions does the token permit under the authorization contract? |

A token with the right `iss` and wrong `aud` must still be rejected.

### 3.2. Never Substitute azp for aud

In an OIDC ID token, `azp` (authorized party) identifies the party to which the token was issued in certain cases, especially when an ID token has multiple audiences. It is not a Resource Server audience.

Never use `azp` in place of the API audience. `azp` may be checked by an OIDC client validating an ID token, but it never turns an ID token into an access token.

### 3.3. Audience Can Be a String or an Array

A JWT may represent `aud` as a single string or a list of strings. Spring Security normalizes this claim via:

```java
List<String> audiences = jwt.getAudience();
```

Compare by exact element membership:

```java
boolean intendedForOrders =
        jwt.getAudience().contains("orders-api");
```

Never use substring matching:

```java
// WRONG: orders-api-admin also contains the substring orders-api.
boolean wrong =
        jwt.getAudience().toString().contains("orders-api");
```

### 3.4. Membership vs. Exact-Single Audience?

Two policies are commonly used:

**Membership:** the token is accepted if the `aud` list contains the API's identifier:

```java
boolean allowed =
        jwt.getAudience().contains("orders-api");
```

**Exact-single audience:** the token must contain exactly one audience and that audience must be this API:

```java
boolean allowed =
        jwt.getAudience().size() == 1
        && jwt.getAudience().contains("orders-api");
```

Membership fits when the AS contract allows a single access token to target multiple recipients. Exact-single is stricter and useful when an organization requires separate tokens per API. Choose a policy deliberately, align with the AS, and apply it consistently across instances.

## 4. Resource Server Token Contract

Before writing validators, define which access tokens the API accepts. A practical contract typically specifies:

| Element | Example Contract for Orders API |
| --- | --- |
| Trusted issuer | https://login.example.test |
| Audience/resource | orders-api |
| Token format | RS256-signed JWT, or opaque token via introspection |
| Token purpose/profile | Access token; if using RFC 9068, require the corresponding JWT access token profile |
| Required scope | orders:read for GET, orders:write for POST |
| Lifetime | Must have exp, bounded by policy maximum lifetime |
| Time claims | Validate exp, nbf, and clock skew |
| Subject | sub matching the agreed user/service identifier |
| Optional constraints | client_id, cnf, tenant, actor/delegation claims |

A Resource Server should not accept a token merely because it was signed by a familiar issuer. An issuer can mint multiple token types for many different clients and resources.

### 4.1. Do Not Guess Token Type from Arbitrary Claims

Some Authorization Servers add proprietary claims such as `token_use`, `typ`, `client_id`, or `resource`. Such claims are meaningful only if the AS and Resource Server agreed on that contract.

There is no universal vendor claim across all OAuth servers. If your AS emits `token_use=access`, you can validate that claim as part of your specific profile. Do not assume every issuer emits it.

### 4.2. RFC 9068 and typ=at+jwt

RFC 9068 defines a JWT access token profile. Under this profile, the JOSE header uses media type `at+jwt` or `application/at+jwt` to identify JWT access tokens:

```json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "access-key-1"
}
```

If the AS commits to RFC 9068, the Resource Server can require `typ` per this profile. Never apply that check blindly to issuers using a different JWT access token profile or legacy tokens that do not implement RFC 9068.

Even when `typ=at+jwt` is present, you must still verify issuer, audience, timestamps, signature, and scope. The type header grants no permissions on its own.

## 5. Checks That Are Insufficient on Their Own

| Single Check | Why It Is Insufficient |
| --- | --- |
| JWT parses cleanly | Token may be malformed for the profile, have a bad signature, or target the wrong recipient. |
| Valid signature | Token may be an ID token or an access token meant for another API. |
| Valid iss | Same issuer can mint tokens for many clients/APIs. |
| sub present | Subject does not prove the token is an access token or meant for this API. |
| scope contains orders:read | Token could be issued for another resource; scope does not replace audience. |
| Valid azp | Authorized party in an OIDC context does not replace API audience. |
| Unexpired exp | Unexpired tokens can still have the wrong type or wrong audience. |
| active=true from introspection | Active tokens can still belong to another resource or lack required permissions. |

The Resource Server must verify the entire contract before constructing an authenticated principal.

## 6. Configuring a JWT Resource Server with Issuer and Audience Validators

Spring Security can verify signatures via JWKS and execute `OAuth2TokenValidator` instances before constructing `JwtAuthenticationToken`.

Servlet configuration example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersResourceServerConfiguration {

    private static final String ISSUER =
            "https://login.example.test";
    private static final String JWKS_URI =
            "https://login.example.test/oauth2/jwks";
    private static final String API_AUDIENCE =
            "orders-api";

    @Bean
    NimbusJwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(JWKS_URI).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains(API_AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }

            OAuth2Error error = new OAuth2Error(
                    "invalid_token",
                    "Token is not intended for Orders API",
                    null);

            return OAuth2TokenValidatorResult.failure(error);
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        issuerAndTime,
                        audience));

        return decoder;
    }

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/public/**").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .requestMatchers(HttpMethod.POST, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:write")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
```

The example above configures the JWKS URI directly and attaches both the issuer/time validator and the audience validator. When using `issuer-uri` discovery, you can build the decoder from the issuer and attach the audience validator similarly. Either way, preserve issuer validation.

This example uses Servlet `HttpSecurity`. WebFlux applications must configure `ServerHttpSecurity` and `SecurityWebFilterChain`; never use `HttpSecurity` in the reactive stack.

### 6.1. Why JwtValidators.createDefaultWithIssuer Is Needed

The issuer-aware default validator keeps the default timestamp checks and verifies `iss` matches the trusted issuer. The audience validator adds verification that the token is intended for Orders API.

Never replace the default validator with one that checks only `aud`, as doing so would drop issuer and timestamp checks.

### 6.2. Extracting the Audience Validator into a Reusable Function

```java
static OAuth2TokenValidator<Jwt> audienceValidator(
        String expectedAudience) {

    return jwt -> jwt.getAudience().contains(expectedAudience)
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token",
                            "Unexpected token audience",
                            null));
}
```

Extracting the validator lets you reuse the same contract across configurations and unit-test it directly. Each Resource Server must pass its own audience; do not share a single global constant across APIs that define separate resource boundaries.

## 7. Validating the RFC 9068 Token Profile When Supported by the AS

If the Authorization Server issues JWT access tokens per RFC 9068, you can require `typ=at+jwt` or `application/at+jwt`:

```java
static OAuth2TokenValidator<Jwt> accessTokenTypeValidator() {
    return jwt -> {
        Object typ = jwt.getHeaders().get("typ");

        boolean validType =
                "at+jwt".equalsIgnoreCase(String.valueOf(typ))
                || "application/at+jwt".equalsIgnoreCase(
                        String.valueOf(typ));

        if (validType) {
            return OAuth2TokenValidatorResult.success();
        }

        return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                        "invalid_token",
                        "Expected an RFC 9068 access token",
                        null));
    };
}
```

Compose this validator with issuer/time and audience:

```java
decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audienceValidator("orders-api"),
                accessTokenTypeValidator()));
```

**Enable the typ validator only when the issuer commits to RFC 9068.** If your system's current access tokens follow a different contract, requiring `at+jwt` will reject valid access tokens. Even without checking `typ`, the API must still validate audience and all agreed claims/profile rules.

## 8. How Is an ID Token Rejected?

Suppose the OIDC client holds an ID token:

```json
{
  "iss": "https://login.example.test",
  "sub": "user-123",
  "aud": ["web-client"],
  "exp": 1893456000,
  "iat": 1893452400,
  "nonce": "browser-login-nonce",
  "auth_time": 1893452300
}
```

Orders API requires audience `orders-api`. Outcome:

```text
Signature verification: pass
Issuer validation:      pass
Timestamp validation:   pass
Audience validation:    fail (web-client != orders-api)
Authentication:         reject
HTTP result:            401 Unauthorized
```

This is a critical point: tests must use an ID token with a **valid signature** to prove the API rejects it because it is not intended for the API. If you use a malformed JWT string, the test may fail during parsing and never exercise the audience policy.

### 8.1. Do Not Rely on nonce to Distinguish Tokens

`nonce` in an ID token binds the authentication response to the OIDC login request. It is not an audience validation mechanism for a Resource Server.

Never conclude:

- If `nonce` is present, it must be an ID token.
- If `nonce` is absent, it must be an access token.

Rely on the token profile and audience contract. An access token might carry a custom claim named `nonce`, and an ID token may omit `nonce` in certain flows.

### 8.2. Do Not Rely on at_hash to Turn an ID Token into an Access Token

`at_hash` in an ID token binds the ID token to an access token in certain OIDC flows. It does not substitute for a Resource Server audience and does not authorize sending the ID token as a Bearer credential to an API.

## 9. Tokens Intended for Another API Are Rejected

Suppose Orders API and Inventory API share the same issuer. A token is issued for Inventory:

```json
{
  "iss": "https://login.example.test",
  "sub": "user-123",
  "aud": ["inventory-api"],
  "scope": "inventory:read",
  "exp": 1893456000
}
```

Orders API receives this token:

```text
Signature verification: pass
Issuer validation:      pass
Timestamp validation:   pass
Audience validation:    fail (inventory-api != orders-api)
Authentication:         reject
HTTP result:            401 Unauthorized
```

Never accept this token merely because it carries a similar-looking scope or comes from the same issuer. The Resource Server must check its own audience.

### 9.1. Scope Does Not Replace Audience

Example token:

```json
{
  "aud": ["inventory-api"],
  "scope": "orders:read"
}
```

Even though `scope` includes `orders:read`, the token is still addressed to Inventory API by audience. Orders API must reject it. Scope expresses permissions; audience identifies the recipient.

### 9.2. Never Rewrite Audience at the Resource Server

A Resource Server must never accept a token meant for Inventory and treat it as an Orders token just because the subject or scope looks suitable. To call another API, the client must obtain a new token through an AS-supported flow, such as token exchange targeting the right audience.

## 10. Audience Validation with Opaque Access Tokens

Not every access token is a JWT. For opaque tokens, the Resource Server calls an introspection endpoint and receives token status metadata.

Example response:

```json
{
  "active": true,
  "iss": "https://login.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "exp": 1893456000
}
```

`active=true` only states that the token is active according to the Authorization Server. The Resource Server must still verify audience, scope, and contract metadata.

### 10.1. Wrapping OpaqueTokenIntrospector to Validate Audience

Decorator example:

```java
import java.util.Collection;

import org.springframework.security.oauth2.core.OAuth2IntrospectionException;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

OpaqueTokenIntrospector ordersIntrospector(
        String introspectionUri,
        String clientId,
        String clientSecret) {

    OpaqueTokenIntrospector delegate =
            new NimbusOpaqueTokenIntrospector(
                    introspectionUri, clientId, clientSecret);

    return token -> {
        OAuth2AuthenticatedPrincipal principal =
                delegate.introspect(token);

        Object aud = principal.getAttribute("aud");
        boolean intendedForOrders =
                aud instanceof String value
                        ? "orders-api".equals(value)
                        : aud instanceof Collection<?> values
                                && values.contains("orders-api");

        if (!intendedForOrders) {
            throw new OAuth2IntrospectionException(
                    "Token is not intended for Orders API");
        }

        return principal;
    };
}
```

This illustrates handling an introspection response where `aud` may be a string or a collection. Real bean configuration must load the URI and client credentials from configuration or a secret manager, never from caller input.

If the AS uses a different attribute to express audience/resource binding, implement the AS's exact introspection contract. Never infer audience from scope.

### 10.2. Introspection Must Not Ignore Token Purpose

The Resource Server must know the introspection endpoint is verifying an access token. If the AS can return `active=true` for multiple security token types, the contract needs a trustworthy token purpose/type attribute or an endpoint/policy scoped strictly to access tokens.

Never accept an ID token solely because `active=true`.

## 11. HTTP Status: 401 or 403?

Distinguish authentication errors from authorization errors:

| Scenario | Typical Status | Meaning |
| --- | --- | --- |
| ID token sent instead of access token | **401 Unauthorized** | Credential is invalid for the Resource Server. |
| Access token meant for another API | **401 Unauthorized** | Token was not issued for the current API. |
| Wrong signature/issuer/expired | **401 Unauthorized** | Authentication failed. |
| Valid issuer/audience token missing scope | **403 Forbidden** | Token is valid, but lacks permission for the operation. |
| Valid token, user lacks permission on object/tenant | **403** or **404** per API contract | Domain authorization denied. |
| No Bearer token sent to protected endpoint | **401 Unauthorized** | No credential supplied to authenticate. |

Do not return 403 for a wrong-audience token just to hide configuration issues. The Resource Server has not authenticated a credential meant for itself, so 401 is the right semantic response.

### 11.1. Prevent Business Controllers from Running with Invalid Tokens

When signature, issuer, audience, or token-profile validation fails, the request must stop at the authentication layer. Controllers must never execute with an unverified principal.

In tests, you can mock the service and verify no business method is invoked when the audience is wrong:

```java
verify(orderService, never()).findOrders(any());
```

This proves the request is blocked before any business logic executes.

## 12. Integration Testing: Must Send Real Signed Bearer Tokens

To verify the token contract, use:

- A test-only RSA/EC key pair.
- A mock JWKS endpoint publishing only the test public key.
- A compact JWS signed with the test private key.
- MockMvc running through the full Spring Security filter chain.
- HTTP header `Authorization: Bearer <token>`.

Do not use `with(jwt())` for these tests because that helper pre-builds a `JwtAuthenticationToken`, bypassing `JwtDecoder`, signature verification, and audience validation.

### 12.1. Test Factory for Signing Tokens

Example with Nimbus JOSE:

```java
import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import java.time.Instant;
import java.util.Date;
import java.util.List;

final class TestAccessTokenFactory {

    static RSAKey newKey(String kid) throws JOSEException {
        return new RSAKeyGenerator(2048)
                .keyID(kid)
                .generate();
    }

    static String sign(
            RSAKey key,
            String issuer,
            List<String> audiences,
            String scope,
            String typ) throws JOSEException {

        Instant now = Instant.now();

        JWTClaimsSet claims = new JWTClaimsSet.Builder()
                .issuer(issuer)
                .subject("user-123")
                .audience(audiences)
                .issueTime(Date.from(now))
                .expirationTime(Date.from(now.plusSeconds(300)))
                .claim("scope", scope)
                .build();

        JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.RS256)
                .keyID(key.getKeyID())
                .type(new JOSEObjectType(typ))
                .build();

        SignedJWT jwt = new SignedJWT(header, claims);
        jwt.sign(new RSASSASigner(key.toPrivateKey()));
        return jwt.serialize();
    }
}
```

For RFC 9068 access tokens, pass `typ` as `at+jwt` or `application/at+jwt`. To build an ID token fixture, use the header type matching the simulated OIDC provider and set the audience to the client ID. If a test aims purely to prove audience rejection, do not enable a separate type validator in that fixture or assert each cause independently.

### 12.2. Serving Test JWKS from the Public Key

```java
String jwksJson =
        new JWKSet(testSigningKey.toPublicJWK()).toString();
```

The JWKS must never contain private keys. The private key remains inside the test process to sign JWTs.

### 12.3. Sending Tokens Through MockMvc

```java
mockMvc.perform(get("/api/orders")
        .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer " + compactJwt))
        .andExpect(status().isOk());
```

The test application context must use a real decoder pointing to the mock JWKS endpoint; never replace `JwtDecoder` with a mock. Requests then pass through the Bearer filter, authentication provider, decoder, signature verification, and validators.

## 13. Mandatory Tests for ID Tokens and Other-API Tokens

Assume the test issuer is `https://issuer.test`, the test signing key is published in the JWKS, and the API checks for `orders-api`.

### 13.1. Positive: Access Token with Matching Audience

```java
String ordersToken = TestAccessTokenFactory.sign(
        trustedKey,
        TEST_ISSUER,
        List.of("orders-api"),
        "orders:read",
        "at+jwt");

mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + ordersToken))
        .andExpect(status().isOk());
```

The token has a trusted signature, valid issuer, Orders audience, and sufficient scope, so it is accepted.

### 13.2. Negative: Web Client ID Token

The ID token fixture must be signed by the same test issuer key so the test does not fail solely on signature:

```java
String idToken = TestAccessTokenFactory.sign(
        trustedKey,
        TEST_ISSUER,
        List.of("web-client"),
        "openid profile",
        "JWT");

mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + idToken))
        .andExpect(status().isUnauthorized());
```

This test proves an ID token with a valid issuer/signature is still rejected because its audience is the OIDC client rather than Orders API. Real fixtures can include `nonce`, `auth_time`, and relevant OIDC claims; those claims do not change the audience decision.

### 13.3. Negative: Access Token for Inventory API

```java
String inventoryToken = TestAccessTokenFactory.sign(
        trustedKey,
        TEST_ISSUER,
        List.of("inventory-api"),
        "inventory:read",
        "at+jwt");

mockMvc.perform(get("/api/orders")
        .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer " + inventoryToken))
        .andExpect(status().isUnauthorized());
```

The token is a valid access token per profile, yet its recipient is wrong. This is a critical test proving the Resource Server does not accept tokens merely because they share the same issuer and signature.

### 13.4. Negative: Matching Audience but Missing Scope

```java
String noReadScope = TestAccessTokenFactory.sign(
        trustedKey,
        TEST_ISSUER,
        List.of("orders-api"),
        "orders:write",
        "at+jwt");

mockMvc.perform(get("/api/orders")
        .header(
                HttpHeaders.AUTHORIZATION,
                "Bearer " + noReadScope))
        .andExpect(status().isForbidden());
```

Here authentication succeeds: the token is intended for Orders API. The GET request requires `orders:read`, while the token only carries `orders:write`, so authorization returns 403.

### 13.5. Negative: Different Issuer

Sign the token with the trusted test key, but set a different `iss`. Although the signature is valid, the issuer validator must reject it:

```java
String wrongIssuer = TestAccessTokenFactory.sign(
        trustedKey,
        "https://other-issuer.test",
        List.of("orders-api"),
        "orders:read",
        "at+jwt");

mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + wrongIssuer))
        .andExpect(status().isUnauthorized());
```

This test separates issuer validation from signature verification.

## 14. Testing the Type Validator Separately When Using RFC 9068

If the API contract mandates RFC 9068:

| Token | typ | aud | Outcome |
| --- | --- | --- | --- |
| RFC 9068 access token | at+jwt or application/at+jwt | orders-api | May be accepted. |
| ID token | JWT or OIDC provider's type | web-client | Rejected. |
| Non-access-token profile JWT | JWT | orders-api | Rejected per type policy. |
| Inventory RFC 9068 access token | at+jwt | inventory-api | Rejected due to audience. |

Do not rely on `typ` alone. An ID token with the wrong audience must still be rejected even if an issuer deviates from the header type convention. Conversely, a JWT with `typ=at+jwt` and the wrong audience must also be rejected.

## 15. Integration Test Matrix

| Case | Token | Signature | Issuer | Audience | Scope | Result |
| --- | --- | --- | --- | --- | --- | --- |
| INT-01 | Orders access token | Valid | Valid | orders-api | orders:read | 2xx |
| INT-02 | Web Client ID token | Valid | Valid | web-client | Not an API scope | 401 |
| INT-03 | Inventory access token | Valid | Valid | inventory-api | inventory:read | 401 |
| INT-04 | Orders access token | Valid | Wrong | orders-api | orders:read | 401 |
| INT-05 | Orders access token | Wrong | Valid | orders-api | orders:read | 401 |
| INT-06 | Orders access token | Valid | Valid | orders-api | Missing orders:read | 403 |
| INT-07 | Orders access token | Valid | Valid | Other audience | orders:read | 401 |
| INT-08 | Orders access token | Valid | Valid | orders-api | Valid, expired | 401 |
| INT-09 | Multi-audience access token | Valid | Valid | Includes orders-api and another API | Sufficient | Per membership/exact-single policy |
| INT-10 | Token missing aud | Valid | Valid | None | Has scope | 401 |
| INT-11 | RFC 9068 access token | Valid | Valid | orders-api | Sufficient | 2xx if profile enabled |
| INT-12 | Different JWT type | Valid | Valid | orders-api | Sufficient | 401 if RFC 9068 type validator enabled |
| INT-13 | Active opaque token, matching audience | Introspection succeeds | Valid | orders-api | Sufficient | 2xx |
| INT-14 | Active opaque token, another audience | Introspection succeeds | Valid | inventory-api | Sufficient | 401 |
| INT-15 | Inactive opaque token | Not active | — | — | — | 401 |

### 15.1. Verifying the Controller Does Not Execute

For wrong-audience tokens or ID tokens, in addition to asserting 401, verify the business service was never called:

```java
verify(orderService, never()).findOrders(any());
```

This guarantees invalid tokens are stopped at the authentication layer before controllers or services process data.

### 15.2. Asserting the Exact Status Code

Do not assert only `is4xxClientError()`. Check specifically:

- Unauthenticated token: 401.
- Authenticated token lacking scope: 403.

These two outcomes represent distinct failures and govern how clients respond.

## 16. Testing Opaque Tokens via Introspection

If the API uses opaque access tokens, tests should not attempt to decode tokens as JWTs. Mock the introspection endpoint to return different metadata payloads.

### 16.1. Active Token with Matching Audience

```json
{
  "active": true,
  "iss": "https://login.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "exp": 1893456000
}
```

Expected: the introspector returns a principal, the authority converter maps scopes, and the API allows GET.

### 16.2. Active Token Intended for Another API

```json
{
  "active": true,
  "iss": "https://login.example.test",
  "sub": "user-123",
  "aud": ["inventory-api"],
  "scope": "inventory:read",
  "exp": 1893456000
}
```

Expected: the delegate introspector reports active, but the audience decorator rejects it. No Authentication is created for Orders API.

### 16.3. Inactive Token

```json
{
  "active": false
}
```

Expected: the introspector rejects before the audience check runs. Never treat an inactive token as valid merely because other attributes are present in the response.

### 16.4. Testing Token Type per AS Contract

If the introspection response carries a dedicated claim or token-type metadata, validate it per contract. Do not assume all AS implementations return `token_type` or `token_use` with identical semantics. If the AS can introspect ID tokens as well, the Resource Server needs an explicit rule accepting access tokens only.

## 17. Token Exchange When Calling Another API

If Orders API needs to call Inventory API, never forward the Orders token to Inventory, and never loosen the audience validator so both APIs accept all tokens.

Use OAuth 2.0 Token Exchange (RFC 8693) if supported by the AS:

```text
subject_token = access token intended for orders-api
audience = inventory-api
scope = inventory:read
```

The AS validates the client, subject, actor, and target, then issues a new token with the appropriate audience. Inventory API still validates its own audience.

If token exchange is not supported, the client must use another flow/credential designed for Inventory API, such as client credentials for a workload if user delegation is not required.

**Never solve a wrong-audience error by removing audience validation.**

## 18. Common Implementation Mistakes

1. **Verifying only the signature:** a token can be validly signed by the issuer yet be an ID token or an access token for another API.
2. **Calling APIs with an ID token:** ID tokens are for OIDC clients; use access tokens for Resource Servers.
3. **Accepting tokens solely for sharing an issuer:** a single issuer mints many token types across many audiences.
4. **Substituting scope for audience:** scope describes permissions; audience describes the recipient.
5. **Substituting azp for aud:** `azp` is not a Resource Server audience.
6. **Substring-matching audiences:** can mistakenly match `orders-api-admin`; use exact membership or exact-single policy.
7. **Unintentionally permitting multiple audiences:** multi-audience tokens can be replayed across multiple resources.
8. **Dropping the issuer validator when adding an audience validator:** the two validators complement each other.
9. **Relying on typ across all issuers:** `at+jwt` works when the AS implements RFC 9068; legacy profiles may omit it.
10. **Using with(jwt()) to prove bad tokens are rejected:** that helper builds an Authentication directly and skips the decoder.
11. **Mocking JwtDecoder in integration tests:** a mocked decoder does not check signatures, issuers, or audiences.
12. **Testing only malformed tokens:** you need validly signed tokens with the wrong recipient to prove the audience policy works.
13. **Accepting opaque tokens solely because active=true:** active does not mean intended for this API.
14. **Letting invalid tokens reach controllers:** authentication must fail before business handlers execute.

## 19. Observability and Operations

When a token is rejected, logs should record the reason safely:

```text
event=oauth2_authentication_failed
reason=invalid_audience
resource=orders-api
issuer=https://login.example.test
request_id=...
```

Never log raw access tokens, ID tokens, Authorization headers, or full JWT claims containing PII.

Metrics can categorize `invalid_signature`, `invalid_issuer`, `invalid_audience`, `expired_token`, `invalid_token_profile`, `insufficient_scope`, and `introspection_inactive`. Never use token values or `sub` as metric labels, as that creates high cardinality and leaks data. Use stable API/resource identifiers and error categories.

### 19.1. Do Not Return Internal Details to Callers

HTTP responses should generally use a generic Bearer challenge:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Never return raw tokens, internal issuer signing key IDs, stack traces, or full claims in `error_description`. Deeper diagnostic details belong in redacted internal telemetry.

## 20. Implementation Checklist

- [ ] Identify the exact trusted issuer.
- [ ] Identify the API's audience/resource identifier.
- [ ] Confirm the token profile issued by the AS.
- [ ] Separate ID tokens from access tokens in the client/API contract.
- [ ] Verify JWS signatures via trusted JWKS or introspection for opaque tokens.
- [ ] Validate issuer and timestamps.
- [ ] Validate audience using exact membership or exact-single policy.
- [ ] Never substitute `azp`, `sub`, `scope`, or `active=true` for audience.
- [ ] Enforce scopes/authorities after authentication.
- [ ] Require `typ=at+jwt` only when the AS commits to RFC 9068.
- [ ] Test validly signed ID token with client ID audience → 401.
- [ ] Test validly signed access token with another API's audience → 401.
- [ ] Test matching-audience token missing scope → 403.
- [ ] Test wrong issuer/signature/expired → 401.
- [ ] Test active opaque token with wrong audience → 401.
- [ ] Assert controllers/business services do not execute when authentication fails.
- [ ] Never log tokens or sensitive claims.

## 21. Self-Check Questions

**1. What is an ID token used for?** Confirming authentication results for an OIDC client/Relying Party.

**2. What is an access token used for?** Granting access to protected resources according to scopes/policies.

**3. Why should an ID token never be sent to a Resource Server?** Its audience and purpose are for the OIDC client, not the API.

**4. Is a valid JWT signature enough to accept a token?** No. You must also verify issuer, audience, timestamps, profile, and authorization.

**5. Which claim identifies which API a token is intended for?** `aud`, per the Resource Server's audience contract.

**6. How do iss and aud differ?** `iss` identifies the issuer; `aud` identifies the recipient.

**7. Can azp replace aud?** No. `azp` is the authorized party in an OIDC context.

**8. Can scope replace audience?** No. Scope describes permissions; audience identifies the resource.

**9. Which HTTP status should be returned for a wrong audience?** Typically 401, because the credential is invalid for the Resource Server.

**10. What about a matching-audience token missing a scope?** 403.

**11. Can multiple audiences be accepted?** Yes, if the contract allows it; choose membership or exact-single policy explicitly.

**12. Is typ=at+jwt always mandatory?** Only when the AS token profile commits to RFC 9068.

**13. Does nonce prove a token is an ID token?** No; `nonce` binds an OIDC authentication response.

**14. Is active=true sufficient for opaque tokens?** No. You still validate audience/resource and scope.

**15. Does MockMvc's jwt() check audience from a signed token?** No. It constructs a simulated `JwtAuthenticationToken`.

**16. Which test proves an API rejects an ID token?** Send an ID token signed with the trusted test key, valid issuer, and client ID audience through the full Bearer filter chain and assert 401.

**17. Which test proves an API rejects another API's token?** Send a validly signed access token from the same issuer whose `aud` is another API's identifier.

**18. Why test 403 separately?** To prove authentication succeeded and authorization denied the request due to missing scope.

**19. What should Orders do if it needs to call Inventory?** Obtain an Inventory-targeted token via token exchange or a designed service credential flow; never remove audience validation.

**20. Why assert the business service is not called?** To ensure invalid tokens are blocked before any side effects occur.

## 22. References

- **OpenID Connect Core 1.0 — ID Token:** defines ID tokens, `iss`, `sub`, `aud`, `azp`, `nonce`, and how clients validate ID tokens. https://openid.net/specs/openid-connect-core-1_0.html
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** access-token profile, `typ=at+jwt`, audience, and claims. https://www.rfc-editor.org/rfc/rfc9068
- **RFC 8725 — JSON Web Token Best Current Practices:** algorithm verification, issuer/audience validation, and preventing cross-JWT confusion. https://www.rfc-editor.org/rfc/rfc8725
- **RFC 7519 — JSON Web Token (JWT):** semantics of `iss`, `sub`, `aud`, `exp`, `nbf`, and `iat`. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 7662 — OAuth 2.0 Token Introspection:** opaque token status and metadata. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** Bearer authentication and `invalid_token`/`insufficient_scope` errors. https://www.rfc-editor.org/rfc/rfc6750
- **Spring Security Reference — Servlet OAuth 2.0 Resource Server JWT:** decoder, issuer, JWKS, and JWT validation. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- **Spring Security Reference — Servlet OAuth 2.0 Resource Server Opaque Token:** introspection and opaque token validation. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Spring Security Reference — Testing OAuth 2.0:** MockMvc and the `jwt()` request post-processor. https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html

## 23. Conclusion

A Resource Server must reject ID tokens and access tokens intended for other APIs according to its token contract. A valid signature proves only that the token was signed by a trusted key; it does not prove the token is an access token or was issued for the receiving API.

For JWTs, verify signature, issuer, timestamps, audience, and token profile; for opaque tokens, verify introspection state alongside audience/resource and scope. ID tokens typically carry the OIDC client as audience, whereas access tokens must carry the Resource Server's audience. When audience is wrong, authentication fails and the API typically returns 401; when the audience matches but scope is missing, authorization returns 403.

The most important test uses **validly signed tokens with the wrong recipient**: both an ID token with `aud=web-client` and an access token with `aud=inventory-api` must be rejected by Orders API through the full Bearer filter chain. Follow that with a token carrying `aud=orders-api` but lacking scope to prove 403. Together these tests confirm the API upholds the token contract at both authentication and authorization boundaries.
