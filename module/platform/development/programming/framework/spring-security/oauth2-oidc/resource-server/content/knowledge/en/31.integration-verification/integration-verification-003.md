# Valid Tokens, Wrong Signatures, Wrong Issuers, Wrong Audiences, and Wrong Types

When building a **Spring Security OAuth 2.0/OIDC Resource Server**, a valuable integration test must prove that the API only accepts access tokens satisfying the exact trust contract. A structurally valid and signed JWT does not automatically mean it was issued by an issuer the API trusts, intended for that API, or of the right token type.

A test suite needs to distinguish at least five cases:

1. **Valid token:** valid signature, trusted issuer, audience includes the Resource Server, valid timestamps, and matches the access token profile.
2. **Wrong signature:** token is signed by a private key different from the key trusted by the Resource Server, or the signature has been tampered with.
3. **Wrong issuer:** signature is valid, but the `iss` claim does not match the configured Authorization Server.
4. **Wrong audience:** token is signed by a trusted issuer, but was issued for another client/API.
5. **Wrong type:** token may be signed by the same issuer, yet is an ID token, JWT assertion, or another kind of JWT rather than an access token for the API.

Negative cases must flow through **the application's actual authentication filter and decoder/introspector**. For JWTs, generate test tokens signed with a dedicated key pair, configure the decoder to trust only the corresponding public key, and send tokens via HTTP `Authorization: Bearer`. Using `mockJwt()` or building a `JwtAuthenticationToken` directly bypasses the signature and claim verification that integration tests exist to prove.

> **A token is accepted only when every validation layer passes:** signature/trust source, issuer, audience, timestamps, token profile/type, and required authorities. A valid signature is only part of the condition.

## 1. Trust Contract of a JWT Access Token

A JWT typically consists of three parts:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

The header describes the algorithm and JOSE metadata; the payload carries claims; the signature protects the integrity of header and payload under the selected algorithm. The Resource Server must validate tokens according to the profile agreed upon with the issuer.

Example access token following the JWT Profile for OAuth 2.0 Access Tokens:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "alice",
  "aud": ["orders-api"],
  "client_id": "orders-web",
  "iat": 1893459000,
  "exp": 1893459600,
  "jti": "at-3d91c8",
  "scope": "orders.read orders.write"
}
~~~

The header might look like:

~~~json
{
  "alg": "RS256",
  "kid": "test-key-1",
  "typ": "at+jwt"
}
~~~

Key components:

| Component | Question the Resource Server Must Answer |
|---|---|
| Signature | Was the token signed by the private key matching a trusted public key and left unmodified? |
| `iss` | Who issued the token? Does it match the configured issuer? |
| `aud` | Which resource/API was the token issued for? Does it include the current API's identifier? |
| `exp`, `nbf`, `iat` | Is the token within the permitted time window? |
| `typ` / token profile | Is this JWT an access token conforming to the profile accepted by the API? |
| `scope` / authorities | Does the authenticated token hold permission to perform this operation? |

Never use a self-asserted claim from the token to decide trust before verifying the signature. For example, do not take an unverified `iss` and fetch JWKS from an arbitrary URL inside that claim. The issuer and key source must come from pre-established configuration or trusted discovery metadata.

## 2. Distinguishing Authentication Failure from Authorization Failure

The tests below must distinguish:

- **401 Unauthorized:** cannot authenticate the credential: bad signature, wrong issuer, wrong audience, expired token, wrong profile/type, or missing token when the endpoint requires authentication.
- **403 Forbidden:** the token authenticated successfully, but lacks the required authority or is denied by domain policy.
- **2xx:** both authentication and authorization pass, and the business operation succeeds.

Examples:

| Token/Request | Typical Expected Result |
|---|---:|
No Bearer token sent to a protected endpoint | 401 |
JWT signed by an untrusted key | 401 |
JWT with wrong issuer | 401 |
JWT with wrong audience | 401 |
ID token sent as an access token | 401 |
Valid JWT access token missing `orders.write` | 403 |
Valid JWT access token with required scope and domain permission | 2xx |

Do not return 403 for tokens with bad signatures or wrong issuers. Those cases never established an authenticated principal. Conversely, do not use 401 to mask authorization failures after a token has already been authenticated.

## 3. Configuring the Resource Server for Issuer, Audience, and Token Type

Spring Security's JWT Resource Server uses `JwtDecoder` to verify JWTs and `OAuth2TokenValidator<Jwt>` to enforce additional rules.

### 3.1. Configuring Issuer and Audience

Example `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/realms/shop
          audiences:
            - orders-api
~~~

`issuer-uri` lets Spring Security configure the decoder from the issuer's metadata/JWKS. Audience validation must be supported by the active version/configuration; otherwise, attach an explicit validator. Never assume configuring `issuer-uri` alone automatically rejects wrong-audience tokens.

With a manually configured decoder:

~~~java
NimbusJwtDecoder decoder =
    NimbusJwtDecoder.withJwkSetUri(trustedJwkSetUri).build();

OAuth2TokenValidator<Jwt> issuerAndTime =
    JwtValidators.createDefaultWithIssuer(expectedIssuer);

OAuth2TokenValidator<Jwt> audience = jwt ->
    jwt.getAudience().contains("orders-api")
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Required audience is missing",
                null));

OAuth2TokenValidator<Jwt> tokenType = jwt -> {
    Object typ = jwt.getHeaders().get("typ");
    boolean isAccessToken =
        "at+jwt".equals(typ) || "application/at+jwt".equals(typ);

    return isAccessToken
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "JWT is not an access token",
                null));
};

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        issuerAndTime,
        audience,
        tokenType));
~~~

This pattern applies to systems using RFC 9068 that agree on the `typ` header under that profile. If the issuer uses a different profile, validate the token type per the specific contract; never accept arbitrary `typ` values. Under RFC 9068, `at+jwt` is a key signal distinguishing JWT access tokens from other JWTs. Some profiles/implementations use the media type `application/at+jwt`; allow that form only if your deployment contract calls for it.

`JwtValidators.createDefaultWithIssuer(...)` provides Spring Security's standard checks, including the default issuer and timestamp validators. Audience and access-token type are composed alongside them as explicit policy.

### 3.2. Configuring Trusted Algorithms

The Resource Server must not let tokens pick algorithms arbitrarily. With an RSA test key, the decoder can be configured directly:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withPublicKey(trustedRsaPublicKey)
    .signatureAlgorithm(SignatureAlgorithm.RS256)
    .build();
~~~

When using JWKS, the key source/issuer configuration must be trusted and the decoder must accept only policy-allowed algorithms. Reject `alg=none`, never switch to HMAC just because a token header requests it, and never alter trust policy using unverified token metadata.

### 3.3. `typ` Is Not `token_type`

Two values are frequently confused:

| Value | Where It Lives | Meaning |
|---|---|---|
| JOSE header `typ: at+jwt` | JWT header | JWT type per the access-token profile |
| OAuth token response `token_type: Bearer` | JSON response from the token endpoint | How the client presents the access token in HTTP requests |

`token_type=Bearer` does not prove a JWT is an RFC 9068 access token. Nor does it replace validating `typ` or issuer/audience.

### 3.4. An ID Token Is Not an Access Token

An OIDC ID token describes an authentication outcome for an OIDC client. Its audience is typically the client ID, and it may include `nonce`, `auth_time`, and authentication claims. An access token is issued for calling a Resource Server and must carry the matching resource/audience.

Even if an ID token is signed by the same OP with a valid signature, the API must not accept it as an access token. Use token profile/type validation and audience validation to prevent token substitution/cross-JWT confusion.

## 4. Setting Up Integration Tests with Dedicated Key Pairs

A trustworthy test controls both the private key signing tokens and the public key trusted by the decoder:

~~~text
Test token issuer
  private key A
      |
      +-- sign valid token
      +-- sign wrong-issuer token
      +-- sign wrong-audience token
      +-- sign wrong-type token

Resource Server under test
  trusts public key A
      |
      +-- accepts only token satisfying validators

Rogue test issuer
  private key B
      |
      +-- sign wrong-signature token
           (decoder does not trust public key B)
~~~

Never use production private keys in tests. Test key pairs can be generated at test suite startup or stored as fixed test fixtures in source control. If using fixed fixtures, the private key is strictly for tests and must never be used in real environments.

### 4.1. Generating an RSA Key Pair

~~~java
static KeyPair generateRsaKeyPair() throws GeneralSecurityException {
    KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
    generator.initialize(2048);
    return generator.generateKeyPair();
}
~~~

The test creates two key pairs:

- `trustedKeyPair`: valid tokens are signed with this private key; the decoder trusts its public key.
- `untrustedKeyPair`: wrong-signature tokens are signed with this private key; the decoder does not trust its public key.

### 4.2. Creating Genuinely Signed Test JWTs

Helper example using `NimbusJwtEncoder`:

~~~java
import java.security.KeyPair;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.proc.SecurityContext;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.jwk.source.JWKSource;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.jwt.JwsHeader;

final class TestAccessTokens {

    static String issue(
            KeyPair signingKey,
            String issuer,
            List<String> audience,
            String jwtType,
            String scope) {

        RSAKey rsaJwk = new RSAKey.Builder(
                (RSAPublicKey) signingKey.getPublic())
            .privateKey((RSAPrivateKey) signingKey.getPrivate())
            .keyID("test-key")
            .build();

        JWKSource<SecurityContext> jwkSource =
            new ImmutableJWKSet<>(new JWKSet(rsaJwk));
        JwtEncoder encoder = new NimbusJwtEncoder(jwkSource);

        Instant now = Instant.now();
        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject("alice")
            .audience(audience)
            .issuedAt(now.minusSeconds(30))
            .expiresAt(now.plusSeconds(300))
            .id(UUID.randomUUID().toString())
            .claim("client_id", "orders-web")
            .claim("scope", scope)
            .build();

        JwsHeader headers = JwsHeader
            .with(SignatureAlgorithm.RS256)
            .type(jwtType)
            .keyId("test-key")
            .build();

        return encoder.encode(
            JwtEncoderParameters.from(headers, claims)
        ).getTokenValue();
    }
}
~~~

The helper produces a compact JWT with a real RSA signature. The `issuer`, `audience`, `jwtType`, and `scope` parameters let you construct negative tokens that are still signed by the trusted key. This is essential for testing issuer, audience, and type independently from signature failures.

If your project uses a Spring Security/Nimbus version with different builder APIs, adjust the imports/APIs to match your project BOM; the test principle stays the same: sign tokens with a test private key, verify with the configured test public key.

### 4.3. Configuring the Decoder with the Trusted Public Key

~~~java
static JwtDecoder testDecoder(
        RSAPublicKey trustedPublicKey,
        String expectedIssuer) {

    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withPublicKey(trustedPublicKey)
        .signatureAlgorithm(SignatureAlgorithm.RS256)
        .build();

    OAuth2TokenValidator<Jwt> issuerAndTime =
        JwtValidators.createDefaultWithIssuer(expectedIssuer);

    OAuth2TokenValidator<Jwt> audience = jwt ->
        jwt.getAudience().contains("orders-api")
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Wrong audience", null));

    OAuth2TokenValidator<Jwt> type = jwt ->
        "at+jwt".equals(jwt.getHeaders().get("typ"))
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Wrong token type", null));

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            issuerAndTime, audience, type));
    return decoder;
}
~~~

The sample above accepts strictly `typ=at+jwt`. If your chosen profile also allows `application/at+jwt`, update the validator per the contract. Never relax a validator just to let a wrong-type test token pass.

### 4.4. Wiring the Decoder into a Servlet Resource Server

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        JwtDecoder jwtDecoder) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt.decoder(jwtDecoder)))
        .build();
}
~~~

This is a Servlet `SecurityFilterChain`. If the application uses WebFlux, use `SecurityWebFilterChain` and `ReactiveJwtDecoder`; never mix Servlet and reactive configurations.

## 5. Token Matrix to Generate

Use an expected issuer and API audience:

~~~text
EXPECTED_ISSUER = https://identity.example.test
EXPECTED_AUDIENCE = orders-api
EXPECTED_TYPE = at+jwt
EXPECTED_ALGORITHM = RS256
~~~

Generate the following tokens:

| Case | Signing Key | `iss` | `aud` | `typ` | Expected |
|---|---|---|---|---|---|
| Valid token | Trusted private key A | Valid | `orders-api` | `at+jwt` | Accepted |
| Wrong signature | Untrusted private key B | Valid | `orders-api` | `at+jwt` | Rejected |
| Wrong issuer | Trusted private key A | Different issuer | `orders-api` | `at+jwt` | Rejected |
| Wrong audience | Trusted private key A | Valid | `billing-api` | `at+jwt` | Rejected |
| Wrong type | Trusted private key A | Valid | `orders-api` | `JWT` or disallowed type | Rejected |
| Expired | Trusted private key A | Valid | `orders-api` | `at+jwt` | Rejected |
| Not yet valid | Trusted private key A | Valid | `orders-api` | `at+jwt` | Rejected |
| Valid token, missing scope | Trusted private key A | Valid | `orders-api` | `at+jwt` | Authentication succeeds, authorization denied |

For the wrong issuer/audience/type tests, the token is still signed with **trusted private key A**. That way, the test proves the corresponding validator rejects the token rather than failing early on signature verification.

For the wrong signature case, keep issuer, audience, type, and timestamps valid; swap only the signing key to private key B. Since the decoder trusts public key A, signature verification must fail.

## 6. Integration Testing with MockMvc

### 6.1. Testing a Valid Token

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AccessTokenIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    TestTokenFactory tokens;

    @Test
    void acceptsCorrectAccessToken() throws Exception {
        String token = tokens.validAccessToken();

        mockMvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isOk());
    }
}
~~~

The token flows through the Bearer authentication filter, `JwtAuthenticationProvider`, decoder, and configured validators. This test proves the request is authenticated and authorized per the fixture.

### 6.2. Testing Wrong Signature

~~~java
@Test
void rejectsTokenSignedByUntrustedKey() throws Exception {
    String token = tokens.accessTokenSignedByUntrustedKey();

    mockMvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isUnauthorized());
}
~~~

The token still has valid claims. Only the signing private key differs from the public key trusted by the decoder. Expect 401 due to authentication failure.

### 6.3. Testing Wrong Issuer

~~~java
@Test
void rejectsTokenFromUnexpectedIssuer() throws Exception {
    String token = tokens.accessToken(
        "https://attacker.example.test",
        List.of("orders-api"),
        "at+jwt",
        "orders.read",
        tokens.trustedSigningKey());

    mockMvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isUnauthorized());
}
~~~

The token is signed by the trusted key, but the `iss` claim differs from the configured issuer. This test verifies the issuer validator, not signature verification.

### 6.4. Testing Wrong Audience

~~~java
@Test
void rejectsTokenIssuedForAnotherApi() throws Exception {
    String token = tokens.accessToken(
        "https://identity.example.test",
        List.of("billing-api"),
        "at+jwt",
        "orders.read",
        tokens.trustedSigningKey());

    mockMvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isUnauthorized());
}
~~~

The token has a valid signature and issuer, but is intended only for `billing-api`. `orders-api` must reject it, even if the token carries a scope named `orders.read`. Scopes do not substitute for audience.

### 6.5. Testing Wrong Token Type

~~~java
@Test
void rejectsJwtWithWrongTypeHeader() throws Exception {
    String token = tokens.accessToken(
        "https://identity.example.test",
        List.of("orders-api"),
        "JWT",
        "orders.read",
        tokens.trustedSigningKey());

    mockMvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isUnauthorized());
}
~~~

The token has the right signature, issuer, and audience; only the JOSE `typ` is not an access-token type accepted by the Resource Server. This is an isolated test for the token-type validator.

### 6.6. Testing a Valid Token Missing Required Scope

~~~java
@Test
void rejectsValidTokenWithoutRequiredScope() throws Exception {
    String token = tokens.accessToken(
        "https://identity.example.test",
        List.of("orders-api"),
        "at+jwt",
        "profile.read",
        tokens.trustedSigningKey());

    mockMvc.perform(get("/api/orders")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
        .andExpect(status().isForbidden());
}
~~~

This case differs from the previous ones: the token authenticated successfully, but lacks `SCOPE_orders.read`, so the result is 403.

### 6.7. TestTokenFactory Example

A factory can wrap the helper shown earlier:

~~~java
final class TestTokenFactory {

    private final KeyPair trusted;
    private final KeyPair untrusted;

    TestTokenFactory(KeyPair trusted, KeyPair untrusted) {
        this.trusted = trusted;
        this.untrusted = untrusted;
    }

    String validAccessToken() {
        return issue(trusted, EXPECTED_ISSUER,
            List.of("orders-api"), "at+jwt", "orders.read");
    }

    String accessTokenSignedByUntrustedKey() {
        return issue(untrusted, EXPECTED_ISSUER,
            List.of("orders-api"), "at+jwt", "orders.read");
    }

    String accessToken(
            String issuer,
            List<String> audience,
            String type,
            String scope,
            KeyPair signingKey) {
        return issue(signingKey, issuer, audience, type, scope);
    }
}
~~~

`issue(...)` delegates to the `TestAccessTokens.issue(...)` helper shown earlier. You can place `KeyPair` and the factory in a test configuration or JUnit extension for reuse. Only test code should access the private key.

## 7. Testing WebFlux with WebTestClient

If the Resource Server uses WebFlux, the same token matrix applies; replace MockMvc with WebTestClient and use a reactive decoder.

### 7.1. Configuring the Reactive Decoder

~~~java
@Bean
ReactiveJwtDecoder reactiveJwtDecoder(RSAPublicKey trustedPublicKey) {
    NimbusReactiveJwtDecoder decoder = NimbusReactiveJwtDecoder
        .withPublicKey(trustedPublicKey)
        .signatureAlgorithm(SignatureAlgorithm.RS256)
        .build();

    OAuth2TokenValidator<Jwt> defaults =
        JwtValidators.createDefaultWithIssuer(EXPECTED_ISSUER);

    OAuth2TokenValidator<Jwt> audience = jwt ->
        jwt.getAudience().contains("orders-api")
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Wrong audience", null));

    OAuth2TokenValidator<Jwt> type = jwt ->
        "at+jwt".equals(jwt.getHeaders().get("typ"))
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Wrong token type", null));

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(defaults, audience, type));
    return decoder;
}
~~~

Specific builder/setter APIs may vary by Spring Security version; preserve the policy: the decoder trusts public key A and checks issuer/time, audience, and access-token type.

### 7.2. Reactive SecurityWebFilterChain

~~~java
@Bean
SecurityWebFilterChain apiSecurity(
        ServerHttpSecurity http,
        ReactiveJwtDecoder reactiveJwtDecoder) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt.jwtDecoder(reactiveJwtDecoder)))
        .build();
}
~~~

### 7.3. Bearer-Header Test

~~~java
@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveAccessTokenIntegrationTest {

    @Autowired
    WebTestClient webTestClient;

    @Autowired
    TestTokenFactory tokens;

    @Test
    void acceptsCorrectSignedAccessToken() {
        webTestClient
            .get()
            .uri("/api/orders")
            .headers(headers ->
                headers.setBearerAuth(tokens.validAccessToken()))
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void rejectsWrongAudience() {
        String token = tokens.wrongAudienceToken();

        webTestClient
            .get()
            .uri("/api/orders")
            .headers(headers -> headers.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

The wrong signature, issuer, and type cases follow the same structure: generate the corresponding token with the factory, send via `setBearerAuth(...)`, and assert 401. Never use `mutateWith(mockJwt())` in these tests because that helper creates an already-authenticated principal, bypassing `ReactiveJwtDecoder`.

## 8. Testing Wrong Token Types: ID Tokens, Access Tokens, and JWT Assertions

"Wrong type" is an easy bug to miss because multiple token types are JWTs and may be signed by the same OP.

### 8.1. ID Token

An OIDC ID token typically contains:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "alice",
  "aud": ["orders-web"],
  "iat": 1893459000,
  "exp": 1893459600,
  "nonce": "oidc-login-transaction"
}
~~~

This token was issued for the OIDC client `orders-web`, not the `orders-api` Resource Server. If the API validates audience properly, it is rejected because `aud` does not contain `orders-api`. If the access-token profile also requires `typ=at+jwt`, an ID token typed `JWT` is rejected as well.

### 8.2. Testing That an ID Token Is Rejected

Generate a JWT signed by the trusted key, but with:

- `aud` set to the client ID (`orders-web`).
- `typ` not equal to the access-token type.
- Optionally `nonce` per the OIDC fixture.

Send that token in `Authorization: Bearer`. The API must return 401. This test proves an ID token cannot stand in for an access token.

To isolate type validation, add another synthetic test: keep `iss`, `aud=orders-api`, `exp`, `nbf` (if present), and signature all valid, but set `typ=JWT`. That way the audience validator does not reject first, and the type validator must reject it.

### 8.3. `token_type=Bearer` Does Not Rescue a Wrong-Profile Token

A token endpoint may return:

~~~json
{
  "access_token": "<jwt>",
  "token_type": "Bearer",
  "expires_in": 300
}
~~~

`Bearer` only instructs the client to present the access token using the Bearer Authorization scheme. It does not mean every JWT from the same OP (including ID tokens) is permitted on the API. The Resource Server must still verify signature, issuer, audience, timestamps, and token profile.

### 8.4. JWT Client Assertions

A client assertion may be signed by the same client or a key trusted by the AS, but `aud` is usually the token endpoint and `sub`/`iss` follow the client-authentication profile. It is not an access token for the Orders API. If sent to the API, audience and token-type/profile validation must reject it.

## 9. Validating Audience Properly

### 9.1. Audience Is a Resource Identifier

Audience must identify the target Resource Server/resource API per contract. Examples:

~~~text
orders-api
billing-api
https://api.example.com/orders
~~~

Pick one canonical format and use it consistently across AS, client, and RS. Never use the client ID as the resource audience if your protocol/provider defines audience as a resource identifier.

### 9.2. One Token with Multiple Audiences

A JWT may contain multiple audiences:

~~~json
{
  "aud": ["orders-api", "reporting-api"]
}
~~~

If policy permits multiple resources, the validator must check membership per contract. If policy requires a single exact audience, check both exact count and value. Do not arbitrarily enforce `aud.size()==1` when the system legitimately permits multi-audience tokens; likewise, never accept any audience merely because one familiar value is present.

### 9.3. `azp` Does Not Replace `aud`

OIDC can use `azp` (authorized party) to identify the client permitted to use an ID token in relevant flows. `azp` does not replace access-token audience validation at a Resource Server. Do not substitute `client_id` or `azp` for `aud` just because both mention a client.

### 9.4. Wrong Audience Must Fail Authentication

If `aud` does not contain the API's identifier, do not create an authenticated principal. Do not defer audience checks to a controller after accepting the JWT into `SecurityContext`; doing so risks other endpoints or services accidentally trusting a token issued for the wrong resource.

## 10. Validating Issuer and Public Key Sources

### 10.1. Issuer Is an Exact Trust Boundary

`iss` must match the configured issuer per contract, including scheme/host/path and the profile's comparison rules. Do not arbitrarily lowercase, strip paths, or normalize URLs. Two distinct issuers can share the same subject or `kid`.

### 10.2. Never Trust a JWKS URI From the Token

A JWT may declare `iss` or `jku`/`x5u` in its header. The Resource Server must never use data from an unverified token to fetch arbitrary public keys. The key source must come from configured issuers or trusted discovery metadata.

### 10.3. `kid` Is Not Proof of a Valid Signature

`kid` only selects a key within a JWK Set. An attacker can set `kid` to any valid-looking value. The decoder must still verify the signature with the selected public key. Wrong-signature tests should keep the same `kid` when possible, while signing with a different key pair to prove matching `kid` alone is insufficient.

### 10.4. JWKS Rotation

In a JWKS-backed setup:

- New tokens may carry a new `kid` when the issuer rotates signing keys.
- The decoder must fetch keys from the trusted JWKS endpoint and refresh according to its implementation behavior.
- Old keys may need to remain published while older tokens are still valid.
- Unknown `kid`, JWKS timeouts, and key rotation need dedicated tests.

Tests using `NimbusJwtDecoder.withPublicKey(...)` verify signatures against a fixed public key; they do not test JWKS HTTP fetching or rotation. To test JWKS integration, use a test HTTP server serving a JWK Set and configure the decoder with that server's URI.

## 11. Other Time and Structural Cases

Beyond the five core cases, include boundary tests:

| Case | Condition | Result |
|---|---|---|
Expired | `exp` in the past beyond clock skew | 401 |
Not yet valid | `nbf` in the future beyond clock skew | 401 |
Missing `exp` | Profile requires expiry | 401 |
Future `iat` | `iat` far in the future | 401 per validator |
Malformed JWT | Invalid compact serialization/base64/JSON | 401 |
Unsupported algorithm | `alg` outside allowlist | 401 |
Unknown key ID | No trusted key found | 401 |
Valid JWT, no scope | Valid signature/claims/type, missing authority | 403 |
Valid JWT, enough scope | All validations and authorization pass | 2xx |

Avoid test clocks tied to wall-clock run time when you can inject `Clock` and use a fixed timestamp in custom validators. With the default decoder, issue tokens with sufficient time margin to avoid flakiness from a few seconds of clock skew.

## 12. Verifying Tests Actually Run Through the Decoder

An integration test can accidentally skip the decoder if it uses mock authentication helpers or manually populates `SecurityContext`.

### 12.1. The Path Tests Should Exercise

~~~text
WebTestClient / MockMvc
  Authorization: Bearer <signed test JWT>
          |
          v
Bearer token filter
          |
          v
AuthenticationManager
          |
          v
JwtDecoder / ReactiveJwtDecoder
          |
          +-- signature
          +-- issuer
          +-- audience
          +-- time
          +-- token type
          |
          v
JwtAuthenticationToken
          |
          v
HTTP authorization / controller
~~~

### 12.2. Approaches That Do Not Prove the Decoder

The following approaches are useful for controller/authorization tests, but do not prove signature/issuer/audience/type validation:

- `mockJwt()` in WebTestClient.
- `jwt()`/`mockJwt()` in MockMvc.
- `@WithMockUser`.
- Manually setting `SecurityContext` with a `JwtAuthenticationToken`.
- Invoking controller methods directly.

These helpers are not wrong; they simply answer a different question. Use them for fast authorization tests, and use Bearer-header tests for trust validation.

### 12.3. Verifying Failure Occurs at the Right Layer

To ensure a test is not rejected for an unintended reason:

- Wrong signature: valid claims, wrong signing key.
- Wrong issuer: valid signature, valid audience/type/time, wrong issuer.
- Wrong audience: valid signature and issuer, valid type/time, wrong audience.
- Wrong type: valid signature, issuer, audience, and time, wrong type only.

This is the principle of **varying one condition per test**. If a token has both the wrong issuer and the wrong audience, a 401 response does not prove which validator fired.

## 13. Recommended Integration Test Matrix

| Test name | Token construction | Expected result | What it proves |
|---|---|---:|---|
`acceptsCorrectAccessToken` | Trusted key + expected iss/aud/typ/time | 200 | Happy path end-to-end |
`rejectsUntrustedSignature` | Untrusted key, all other claims valid | 401 | Signature verification |
`rejectsUnexpectedIssuer` | Trusted key, wrong issuer | 401 | Issuer validator |
`rejectsWrongAudience` | Trusted key, another API's audience | 401 | Audience validator |
`rejectsWrongJwtType` | Trusted key, expected iss/aud, wrong typ | 401 | Token-type validator |
`rejectsIdTokenAsAccessToken` | Trusted key, ID-token audience/type | 401 | Token separation |
`rejectsExpiredToken` | Trusted key, past exp | 401 | Expiry validator |
`rejectsNotYetValidToken` | Trusted key, future nbf | 401 | Not-before validator |
`forbidsMissingScope` | Valid token, insufficient scope | 403 | Authorization |
`allowsRequiredScope` | Valid token, required scope | 200 | Authentication + authorization |

Tests should have clear names and the token factory should take explicit parameters so reviewers can immediately see which condition varies.

## 14. Example Unit Testing Audience/Type Validators Directly

If you want to unit-test validators ahead of integration tests:

~~~java
@Test
void rejectsJwtWithoutOrdersAudience() {
    Jwt jwt = Jwt.withTokenValue("test")
        .header("alg", "RS256")
        .header("typ", "at+jwt")
        .claim("iss", EXPECTED_ISSUER)
        .claim("aud", List.of("billing-api"))
        .build();

    OAuth2TokenValidatorResult result = audienceValidator.validate(jwt);

    assertThat(result.hasErrors()).isTrue();
}
~~~

And token type:

~~~java
@Test
void rejectsJwtThatIsNotAnAccessTokenType() {
    Jwt jwt = Jwt.withTokenValue("test")
        .header("alg", "RS256")
        .header("typ", "JWT")
        .claim("iss", EXPECTED_ISSUER)
        .claim("aud", List.of("orders-api"))
        .build();

    OAuth2TokenValidatorResult result = accessTokenTypeValidator.validate(jwt);

    assertThat(result.hasErrors()).isTrue();
}
~~~

These are validator unit tests with no signatures and no filter chain execution. They give fast feedback on policy logic; integration tests with genuinely signed tokens are still required to verify decoder/validator wiring.

## 15. Common Mistakes

| Anti-pattern | Consequence | Correct Approach |
|---|---|---|
Validating only signature | Cryptographically valid tokens meant for other APIs/clients may be accepted | Validate `iss`, `aud`, time, and type |
Validating only issuer | Tokens from the right issuer with the wrong audience can still enter the API | Audience validator |
Validating only audience | Another issuer could mint a token with the same audience | Issuer validator and trusted key source |
Using `kid` to decide token trust | `kid` is a selector, not signature verification | Verify signature with a trusted public key |
Trusting `jku` from the token | Lets an attacker specify the key endpoint | Use configured/trusted discovery JWKS URI |
Accepting ID tokens as access tokens | Token substitution/cross-JWT confusion | Audience + token-type/profile validation |
Confusing `token_type=Bearer` with JOSE `typ` | Fails to verify JWT purpose | Validate `typ`/profile per contract |
Checking `scope` only in controllers | Wrong-issuer/audience tokens already passed authentication | Validate before creating Authentication |
Wrong signature and wrong issuer in the same test | Unclear which check rejected the token | Vary one condition per negative test |
Using `mockJwt()` to test signatures | Decoder is bypassed | Send signed JWT through Bearer filter |
Assigning authorities directly to test converters | Production converter never runs | Test converter directly and via integration pipeline |
Asserting only HTTP 401 | Endpoint might have been rejected by CSRF/other matchers | Verify the right filter chain and each test condition |
Accepting `alg=none` | Unsigned JWTs are trusted | Algorithm allowlist and decoder configuration |
Assuming `aud` is a single string | Mishandles valid JWTs with multiple audiences | Apply explicit audience policy |
Allowing any `typ` for compatibility | Other token types can be mistaken for access tokens | Choose profile and allowlist types |

## 16. Implementation Checklist

### Valid Tokens

- [ ] JWT is signed with a key belonging to a trusted issuer.
- [ ] Signing algorithm is in the allowlist.
- [ ] `iss` matches the configured issuer.
- [ ] `aud` contains the Resource Server identifier.
- [ ] `exp`/`nbf`/`iat` are valid under the clock-skew policy.
- [ ] `typ`/token profile matches the access token accepted by the API.
- [ ] Scope/authorities are sufficient for the endpoint.

### Negative Integration Tests

- [ ] Token signed by another key gets 401.
- [ ] Token with valid signature but wrong issuer gets 401.
- [ ] Token with valid signature/issuer but wrong audience gets 401.
- [ ] Token with valid signature/issuer/audience but wrong type gets 401.
- [ ] ID token is rejected when used as a Bearer access token.
- [ ] Expired/not-yet-valid tokens are rejected.
- [ ] Valid token missing scope gets 403.
- [ ] Tests send Bearer headers through the filter chain and real/signed-token test decoder.
- [ ] Each negative test varies only one primary condition.

### Trust and Key Operations

- [ ] Never fetch key URLs from unverified tokens.
- [ ] JWKS URI/discovery metadata come from trusted configuration.
- [ ] `kid` is used only for key selection; signature is always verified.
- [ ] Unknown `kid`, key rotation, and JWKS outages are tested when using JWKS.
- [ ] Test key pairs never use production private keys.
- [ ] Logs never contain raw access tokens.

## 17. Conclusion

~~~text
VALID ACCESS TOKEN
  signature verified with trusted key
  + expected issuer
  + audience contains this API
  + valid time window
  + correct access-token profile/type
  + required authority
        |
        v
      ACCEPT

BAD SIGNATURE / ISS / AUD / TYPE / TIME
        |
        v
       401

VALID TOKEN, INSUFFICIENT SCOPE
        |
        v
       403
~~~

A strong integration test does more than prove valid tokens are accepted. It proves the Resource Server rejects tokens signed by untrusted keys, tokens from other issuers, tokens meant for different audiences, and wrong-type JWTs. To make those results meaningful, sign test tokens with a dedicated private key, configure the decoder to trust the expected public key, and send Bearer tokens through the real filter chain.

For wrong issuer, audience, or type, keep the signature valid so each validator is tested independently. For wrong signature, keep claims valid and swap only the signing key. Distinguish 401 authentication failures from 403 insufficient authority. Above all, never accept an ID token in place of an access token: sharing the same issuer and verifiable signature does not give two tokens the same purpose.

## References

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT structure, JOSE headers, and `iss`, `aud`, `exp`, `nbf`, `iat` claims.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access-token profile, required claims, and `typ`.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm verification, issuer/audience validation, and cross-JWT confusion.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): OAuth security practices and token confusion/replay mitigations.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token semantics and validation.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): Authorization Server metadata discovery.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS and key identifiers.
- [Spring Security Reference — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JwtDecoder, issuer validation, audience, and JWT authentication.
- [Spring Security Reference — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): ReactiveJwtDecoder and WebFlux Resource Server.
- [Spring Security API — NimbusJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html): Nimbus JWT decoder builders and validators.
- [Spring Security API — NimbusReactiveJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html): reactive Nimbus decoder.
- [Spring Security API — NimbusJwtEncoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtEncoder.html): creating signed JWTs in tests.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer token Authorization header and error responses.
