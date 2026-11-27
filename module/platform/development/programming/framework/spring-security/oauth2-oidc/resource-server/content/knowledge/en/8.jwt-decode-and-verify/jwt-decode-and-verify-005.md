# Allowed Algorithm Allowlists and Matching Key Types During JWT Verification

In **Spring Security OAuth 2.0/OIDC Resource Server**, verifying a JWT access token is more than just finding a public key and calling a signature-check function. The Resource Server must ensure **the JWS algorithm is allowed by policy**, **the verification key has a type and characteristics compatible with that algorithm**, and **that key comes from a trusted issuer**.

A foundational rule in [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725) is that applications must restrict the set of accepted algorithms and never allow the token's `alg` header to override security policy. For each key, the application must also bind it to the appropriate algorithm. Therefore:

> **Which `alg` a token declares is merely input data to be checked. The Resource Server decides which `alg` values are permitted, which keys are trusted, and whether verification under that exact algorithm succeeds.**

This lesson focuses on **JWS (JSON Web Signature)** algorithms when a Resource Server verifies signed JWTs. Do not confuse JWS's `alg` field with JWE's content encryption algorithm `enc`.

## 1. From JWT to selecting an algorithm and key

A JWS compact JWT access token normally has three parts:

~~~text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
~~~

Example header after Base64URL decoding:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026-01",
  "typ": "at+jwt"
}
~~~

The payload may contain:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "alice",
  "aud": ["orders-api"],
  "exp": 2000000000,
  "scope": "orders.read"
}
~~~

These values are not trustworthy just because the JSON can be read. Before using claims, the Resource Server must execute this flow:

~~~text
                       JWT from HTTP request
                                |
                                v
                    Parse JWS compact structure
                                |
                                v
              Read alg, kid (untrusted hints only)
                                |
                                v
              Is alg in configured ALLOWLIST?
                     /                         \
                   No                          Yes
                    |                           |
                    v                           v
                  Reject                 Select key from
                                         TRUSTED key source
                                                |
                                                v
                                Key type/curve/use/alg compatible?
                                         /               \
                                        No               Yes
                                        |                 |
                                        v                 v
                                      Reject         Verify signature
                                                          |
                                            +-------------+-------------+
                                            |                           |
                                          Fail                        Pass
                                            |                           |
                                            v                           v
                                          Reject             Validate iss/aud/exp/nbf
                                                                        |
                                                                        v
                                                          Map scope -> authorities
                                                                        |
                                                                        v
                                                              Authorize request
~~~

**Never invert the trust order** by reading `scope=admin` from an unverified payload and granting privileges. And **a valid signature alone does not guarantee authorization**: you must still validate issuer, audience, expiration, token type, and resource-access conditions.

## 2. What is an “allowed algorithm list”?

An **algorithm allowlist** is the set of verification algorithms approved by the Resource Server under its contract with the Authorization Server (AS) and application security policy.

For example, a system that issues JWTs exclusively with RSA RS256 may set:

~~~text
Allowed JWS algorithms = { RS256 }
~~~

If the AS is performing a controlled migration from RS256 to PS256, the application may temporarily allow:

~~~text
Allowed JWS algorithms = { RS256, PS256 }
~~~

This set must be **governed by trusted configuration**, never constructed from `alg` in the request, an unverified `iss` claim, or a client-supplied URL.

### Three conditions that must hold simultaneously

| Condition | Meaning | Rejection example |
|---|---|---|
| **Algorithm allowed** | `alg` is a member of the approved allowlist | Only RS256 is allowed, yet the token declares HS256 |
| **Compatible key** | Key type, size/curve, usage, and binding match `alg` | Using an RSA public key to verify an HMAC HS256 token |
| **Valid signature/MAC** | Cryptographic check over the JWS content actually succeeds | Payload was modified without re-signing the signature |

Only after these three conditions hold are claims and permissions evaluated.

**Note on RFC 8725:** For each key, the system must restrict which algorithms may be used with that key rather than reusing a key arbitrarily across every algorithm in the same family. Even though an RSA key can mathematically be used by multiple schemes, whether to accept `RS256`, `RS512`, or `PS256` is an explicit policy decision per key and issuer.

## 3. Common JWS algorithm families

The following algorithm identifiers come from JOSE/JWA. Runtime support depends on library version, JCA provider, key type, and Spring Security configuration; this table **does not mean all of them should be enabled**.

| JWS `alg` | Mechanism | Key at AS | Key at Resource Server | Notes |
|---|---|---|---|---|
| `HS256` | HMAC-SHA-256 | Shared secret | **Same shared secret** | Verifier can also create MACs |
| `HS384` | HMAC-SHA-384 | Shared secret | Same shared secret | Secret needs sufficient entropy and length |
| `HS512` | HMAC-SHA-512 | Shared secret | Same shared secret | Never pair with RSA/EC public keys |
| `RS256` | RSA PKCS#1 v1.5 + SHA-256 | RSA private key | RSA public key | Common default configuration |
| `RS384` | RSA PKCS#1 v1.5 + SHA-384 | RSA private key | RSA public key | Must be explicitly allowlisted |
| `RS512` | RSA PKCS#1 v1.5 + SHA-512 | RSA private key | RSA public key | Does not imply switching RSA key types |
| `PS256` | RSA-PSS + SHA-256 | RSA private key | RSA public key | Different padding scheme from RS256 |
| `PS384` | RSA-PSS + SHA-384 | RSA private key | RSA public key | PSS parameters must match |
| `PS512` | RSA-PSS + SHA-512 | RSA private key | RSA public key | Requires decoder support |
| `ES256` | ECDSA + SHA-256 | EC private key on P-256 | EC public key on P-256 | Curve is part of compatibility check |
| `ES384` | ECDSA + SHA-384 | EC private key on P-384 | EC public key on P-384 | Do not swap curves |
| `ES512` | ECDSA + SHA-512 | EC private key on P-521 | EC public key on P-521 | Name ES512 **does not mean** P-512 |
| `EdDSA` | EdDSA (per supported JOSE profile) | Ed25519/Ed448 private key | Corresponding public key | Verify Nimbus/Spring/JCA provider versions |
| `none` | No signature/MAC | None | None | **Reject** in APIs requiring signed JWTs |

`RS256` and `PS256` both use RSA keys, but differ in signing scheme. `ES256` uses an **EC public key** with the matching curve; it cannot be swapped with an RSA key or an arbitrary EC key.

Choose strong algorithms based on enterprise policy, current cryptographic guidance, AS capabilities, and specific library support. Do not try to “support more just in case” by enabling every algorithm.

## 4. How do public keys and secret keys differ?

### 4.1. RSA / RSA-PSS

For `RS256` or `PS256`:

~~~text
Authorization Server                      Resource Server
        |                                        |
   RSA private key                          RSA public key
        |                                        |
        +-- sign JWT --> client --> JWT -------->+-- verify
~~~

The Resource Server only needs the RSA public key to verify. The private signing key is protected at the AS or in a signing system like an HSM/KMS.

A public key entry in a JWKS typically has:

~~~json
{
  "kty": "RSA",
  "kid": "rsa-key-1",
  "use": "sig",
  "alg": "RS256",
  "n": "<base64url-modulus>",
  "e": "AQAB"
}
~~~

The `n`/`e` placeholders above are illustrative only. Production also requires strong RSA key size policies, key lifecycle management, and trusted distribution sources. An RSA public key from issuer A must never be arbitrarily used to verify tokens from issuer B.

### 4.2. ECDSA

For `ES256`:

~~~text
Authorization Server                      Resource Server
        |                                        |
EC private key (P-256)                  EC public key (P-256)
        |                                        |
        +-- sign JWT --> client --> JWT -------->+-- verify
~~~

An EC JWK may contain:

~~~json
{
  "kty": "EC",
  "kid": "ec-key-1",
  "use": "sig",
  "alg": "ES256",
  "crv": "P-256",
  "x": "<base64url-x-coordinate>",
  "y": "<base64url-y-coordinate>"
}
~~~

You must verify the exact **curve** for the algorithm. `ES256` corresponds to P-256, `ES384` to P-384, and `ES512` to P-521. Never accept an unexpected curve just because `kty=EC`.

Spring Security using `NimbusJwtDecoder` with a JWK Set can handle supported asymmetric signing algorithms as configured. However, `NimbusJwtDecoder.withPublicKey(...)` in the standard API accepts **`RSAPublicKey`**; do not try to force an `ECPublicKey` into an RSA-specific builder. For ECDSA, a JWK Set or an appropriate Nimbus `JWKSource` configuration is usually the right approach.

### 4.3. HMAC

For `HS256`, both the AS and RS require the same **shared secret**:

~~~text
Authorization Server                      Resource Server
        |                                        |
   Shared secret S                           Shared secret S
        |                                        |
        +-- MAC JWT --> client --> JWT ----------+-- verify MAC
~~~

Key difference from RSA: any party knowing the secret to **verify an HMAC** is technically capable of **forging a valid HMAC**. If a secret is shared across multiple Resource Servers, compromising one RS can compromise every service trusting that secret.

According to RFC 7518, the secret for `HS256` needs at least 256 bits of entropy/appropriate length; `HS384` and `HS512` require secrets of corresponding strength. Do not use predictable passwords or short strings like `"secret"` simply because the API accepts a `SecretKey`.

An HMAC JWK (when used inside an internal system with restricted access) may contain:

~~~json
{
  "kty": "oct",
  "kid": "hmac-key-1",
  "alg": "HS256",
  "k": "<base64url-secret-key-material>"
}
~~~

**Never publish a JWK with `kty=oct` and `k` containing secret material to a public JWKS.** A JWKS fetched by Resource Servers to verify asymmetric signatures should publish **public keys only**. If the secret leaks, attackers can mint tokens with valid MACs.

### 4.4. EdDSA and newer algorithms

JOSE also includes `EdDSA` using OKP keys such as Ed25519/Ed448 under appropriate profiles. However, not every version of Spring Security, Nimbus, Java Cryptography provider, or IdP supports them fully by default.

Before enabling a new algorithm, confirm the **library version**, **JCA provider**, **JWK format**, **key curve**, **issuer policy**, and **validation behavior**. A token “signed by a modern algorithm” is never a reason to disable the allowlist.

## 5. Mapping `alg`, `kty`, and `crv`

| Header `alg` | Expected JWK `kty` | `crv` / key requirement | Verifier needs |
|---|---|---|---|
| `RS256`, `RS384`, `RS512` | `RSA` | Valid RSA modulus/exponent, key length meets policy | RSA public key |
| `PS256`, `PS384`, `PS512` | `RSA` | RSA-PSS scheme and appropriate key size | RSA public key |
| `ES256` | `EC` | `crv=P-256` | EC P-256 public key |
| `ES384` | `EC` | `crv=P-384` | EC P-384 public key |
| `ES512` | `EC` | `crv=P-521` | EC P-521 public key |
| `HS256`, `HS384`, `HS512` | `oct` | Strong, protected shared secret | Secret key |
| `EdDSA` | `OKP` | Curve/primitive supported by library | EdDSA public key |
| `none` | Not applicable | Not accepted for signed JWTs | Reject |

**Mismatches that must be rejected:**

- Token declares `HS256` while the application only has an RSA public key for verification.
- Token declares `ES256` while the JWKS contains only RSA keys.
- Token declares `ES256` while the EC key uses P-384.
- Token declares `RS256` while the application allows only `PS256`.
- Token declares `none` even though the API requires signed JWTs.
- Token uses an RSA key from a different issuer, even though algorithm and key type look valid.

**Key-type** compatibility is necessary, not sufficient. The key must also come from a trusted source, be designated by the AS for signature use, and not violate `kid`/`alg` bindings or application policy.

## 6. Three control layers: algorithm policy, key source, claims policy

To implement correctly, define three questions separately:

1. **Algorithm policy:** Which `alg` values does the Resource Server permit?
2. **Key source and binding:** From which trusted source are matching keys loaded, with what key type and algorithm binding?
3. **Claims policy:** After signature verification, which `iss`, `aud`, `exp`, `nbf`, token type, and scope values are valid?

Example for `orders-api`:

~~~text
Issuer          = https://idp.example.com/realms/shop
JWK Set URI     = https://idp.example.com/realms/shop/protocol/openid-connect/certs
Allowed algs    = { RS256 }
Audience        = orders-api
Required scope  = orders.read (for GET /api/orders)
~~~

A token carrying `alg=RS256` and a valid signature, yet `aud=billing-api`, **must still be rejected**. A token carrying `aud=orders-api` and `scope=orders.read`, yet `alg=HS256` while the RS trusts only `RS256`, **must also be rejected**.

Dangerous bugs arise when a developer checks one of the three layers and treats it as sufficient:

~~~java
// WRONG: only reads token payload without verifying signature
String role = parseBase64UrlPayload(jwt).get("role");
if ("ADMIN".equals(role)) {
    allowAdminOperation();
}
~~~

An unauthorized party can craft a payload containing `role=ADMIN` and Base64URL-encode it. Standard authentication must verify the signature and policy before building an authenticated principal.

## 7. Algorithm confusion: why must the right key type be matched?

**Algorithm confusion** is a vulnerability class in which the same key material is used or interpreted under a different algorithm than intended, driven by an attacker-controlled `alg`.

### 7.1. Classic example: RSA and HMAC confused

Suppose a system is designed to accept `RS256` JWTs:

~~~text
AS uses RSA private key to sign.
RS uses RSA public key to verify.
~~~

A flawed implementation might let the client choose `alg=HS256` and then feed **the raw bytes of the RSA public key** as the HMAC secret. The public key is public knowledge. An attacker can then compute a valid HMAC using a secret they already know.

~~~text
Correct model:
  alg = RS256
  key = RSA PUBLIC KEY (verify only)
  only the AS holds the RSA private key for signing

Flawed model:
  alg = HS256 chosen by token
  key = bytes of RSA public key used as HMAC secret
  public key is not secret -> risk of forged MAC
~~~

This is why you **never let the token decide the algorithm** and **never use an RSA public key as an HMAC secret**. Modern libraries like Nimbus enforce key-type separation, yet application policy must still restrict algorithms to prevent misconfiguration, unsafe fallbacks, or risky custom processors.

### 7.2. `alg=none`

JOSE includes the `none` value to represent a JWS without signature/MAC protection. It is unsuitable for APIs requiring signed access tokens.

If a processor parses a token, sees `alg=none`, and still trusts `sub`/`scope` claims, an attacker can forge unsigned tokens. The Resource Server must reject them rather than automatically “accepting because no verification is needed”.

### 7.3. Dynamically choosing an algorithm from the token header

Flawed pseudocode pattern:

~~~java
// WRONG: the token header must not dictate policy
String algorithm = parseHeaderWithoutVerification(token).get("alg");
Verifier verifier = createVerifierFromAnyAlgorithm(algorithm, someKey);
return verifier.verify(token);
~~~

Conceptually correct approach:

~~~java
// THIS IS PSEUDOCODE: a real JOSE library performs these steps
Set<String> allowed = Set.of("RS256");
String advertisedAlg = readUntrustedHeader(token).alg();

if (!allowed.contains(advertisedAlg)) {
    rejectToken();
}

TrustedKey key = resolveFromTrustedIssuerJwks(token);
if (!key.matchesPolicy(advertisedAlg)) {
    rejectToken();
}

verifyJwsSignatureOrReject(token, key);
validateIssuerAudienceTimeOrReject(token);
~~~

Never hand-roll cryptographic verification logic. Use Spring Security's `JwtDecoder`, Nimbus, and reviewed policy configuration.

## 8. Which algorithms does Spring Security allow by default?

According to Spring Security Resource Server JWT documentation, `NimbusJwtDecoder` in its default configuration path **trusts `RS256`** to verify signed JWTs. When the Authorization Server uses `RS512`, `PS256`, `ES256`, or another supported algorithm, configure the appropriate allowlist. Never enable all algorithms by default just because Nimbus knows how to process them.

For a Spring Boot application using Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

A minimal filter chain:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

The filter chain protects the API, while `JwtDecoder` is responsible for verifying tokens. The YAML snippets in the next section supply the key source and algorithm policy. CSRF/cookie, CORS, session, and method security concerns must still be configured per application architecture and are not solved solely by an algorithm allowlist.

## 9. Allowing an algorithm via Spring Boot properties

Suppose the AS issues JWTs with `RS512` and publishes public keys via JWKS:

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          jwk-set-uri: https://idp.example.com/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
          jws-algorithms:
            - RS512
~~~

This configuration explicitly declares:

- The **issuer** trusted by the Resource Server.
- The **JWKS source** from which to select the matching RSA public key.
- The **audience** the JWT must contain.
- The allowed **JWS algorithm**, which is `RS512`.

If the AS still issues `RS256` while configuration allows only `RS512`, `RS256` tokens must be rejected even though their signatures might be valid under `RS256`.

When the issuer has standard discovery metadata, you can omit `jwk-set-uri` and use `issuer-uri` alone so Spring Security discovers the JWKS in the supported way. When using `jwk-set-uri` alone without `issuer-uri`, proactively add issuer validation if the API requires a fixed issuer.

**Version note:** `jws-algorithms` and `audiences` are properties supported in modern Spring Boot releases. If your project uses another version or defines a custom `JwtDecoder` bean, verify that the properties actually apply to the running decoder.

### Allowing multiple algorithms during a planned migration

For example, the AS is migrating from `RS256` to `PS256`, only during an approved transition window:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          jwk-set-uri: https://idp.example.com/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
          jws-algorithms:
            - RS256
            - PS256
~~~

This works only if the decoder and JWK Set actually support both algorithms, the corresponding keys are published, and each key has a valid binding. **Do not leave the allowlist broadened indefinitely** once migration completes. Treat adding/removing algorithms as controlled configuration changes, just like changing trusted issuers.

## 10. Using the `NimbusJwtDecoder` builder to restrict algorithms

When the application needs a custom decoder or complex validators, you can use `NimbusJwtDecoder`.

### 10.1. `withJwkSetUri(...)` and `jwsAlgorithm(...)`

Example accepting only `RS256` from a trusted JWKS:

~~~java
package com.example.orders.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class StrictRsaDecoderConfig {

    private static final String ISSUER =
        "https://idp.example.com/realms/shop";
    private static final String JWKS =
        "https://idp.example.com/realms/shop/protocol/openid-connect/certs";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audience =
            new JwtClaimValidator<List<String>>(
                "aud",
                values -> values != null && values.contains("orders-api"));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audience));

        return decoder;
    }
}
~~~

This example clearly separates the three layers:

1. `withJwkSetUri(JWKS)`: trusted key source.
2. `jwsAlgorithm(RS256)`: allowed algorithm.
3. `setJwtValidator(...)`: issuer, timestamp, and audience validation.

**Do not call `NimbusJwtDecoder.withJwkSetUri(...).build()` and assume the decoder automatically knows the expected issuer and audience.** With a custom bean, you must configure validators yourself. Spring Boot normally backs off decoder auto-configuration when the application supplies a `JwtDecoder` bean; YAML properties may not automatically apply validators or algorithm policy to a custom bean.

### 10.2. Builder with multiple algorithms

Spring Security documentation permits calling `jwsAlgorithm(...)` multiple times:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri(jwksUri)
    .jwsAlgorithm(SignatureAlgorithm.RS256)
    .jwsAlgorithm(SignatureAlgorithm.PS256)
    .build();
~~~

You can also use `jwsAlgorithms(...)` with a managed set of algorithms. Remember, however, that **expanding the allowlist is a security decision**, not a default compatibility tweak. If only RS256 is used for signing, keep only RS256.

In practice, each key must have an appropriate algorithm binding; do not enable both algorithms for every key just because both use RSA.

### 10.3. Is deriving algorithms from JWKS always safe?

Nimbus/Spring Security has capabilities to derive the algorithm list from a JWK Set in certain versions and configurations. This is useful when the AS fully controls the JWKS and the contract has been approved.

However, **a trusted JWKS source and an algorithm policy are not necessarily synonymous**. Having multiple RSA/EC keys in a JWKS does not mean the API accepts every algorithm those keys could mathematically support. If security policy requires `RS256` exclusively, configure an explicit allowlist. When relying on JWKS-derived algorithms, ensure the JWKS source, key metadata, and trusted algorithm scope align with policy.

Never let the token decide where to fetch keys via `jku`/`x5u` or dynamically add algorithms to the allowlist.

## 11. Using a static RSA public key

For systems with a single managed RSA public key, Spring Security supports the builder:

~~~java
import java.security.interfaces.RSAPublicKey;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

// rsaPublicKey is the public key loaded from a trusted source
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withPublicKey(rsaPublicKey)
    .signatureAlgorithm(SignatureAlgorithm.RS256)
    .build();
~~~

Signatures in this example are verified strictly under RSA/RS256 with the supplied key. You still need to attach appropriate issuer, audience, and timestamp validators, similar to `StrictRsaDecoderConfig` above.

Take special note: **Spring Security's `PublicKeyJwtDecoderBuilder.signatureAlgorithm(...)` uses an RSA key and supports the RS256/RS384/RS512 options described in the API docs**. If you need RSA-PSS/EC or multiple keys, the right design choice is typically a JWK Set, a trusted `JWKSource`, or matching Nimbus configuration, rather than forcing an RSA-public-key-only builder to cover every algorithm family.

With Spring Boot, you can supply a public key via property:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          public-key-location: classpath:keys/as-public.pem
~~~

Illustrative PEM file:

~~~text
-----BEGIN PUBLIC KEY-----
<base64-encoded-rsa-public-key>
-----END PUBLIC KEY-----
~~~

The Resource Server should load only the public key, never hold the AS's private signing key. With a static public key, you need an update process when the AS rotates keys; replacing a file on disk does not automatically cause `JwtDecoder` to reload it.

## 12. The HMAC case: `withSecretKey(...)` vs. `withPublicKey(...)`

If the AS and Resource Server have a contract requiring `HS256`, the decoder needs a **shared SecretKey**, not an RSA public key.

Illustrative Spring Security API example:

~~~java
import javax.crypto.SecretKey;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

// hmacSecretKey loaded from secret manager / trusted source.
// Never hardcode secrets in source code.
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withSecretKey(hmacSecretKey)
    .macAlgorithm(MacAlgorithm.HS256)
    .build();
~~~

Once again, apply appropriate issuer/audience/timestamp validators. This snippet shows only the HMAC builder, not a complete Resource Server configuration.

Do not use unsafe examples:

~~~java
// WRONG: short, predictable secret
SecretKey secretKey =
    new SecretKeySpec("secret".getBytes(UTF_8), "HmacSHA256");
~~~

For HS256, use a randomly generated secret with sufficient strength and minimum standard length, provisioned via a secret store and kept out of logs. Across multiple Resource Servers, consider asymmetric signing because giving each RS an HMAC secret means each RS can mint valid MACs under that same key.

**Never use the bytes of an RSA public key as a `SecretKey` to verify HS256.** A widely published public key can never serve as a confidential HMAC shared secret.

## 13. JWK metadata: `kty`, `use`, `key_ops`, `alg`, and `kid`

A JWK can include metadata to assist key selection. Example of an RSA key in a JWK Set:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "rsa-sig-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

| Field | Meaning | How the application should handle it |
|---|---|---|
| `kty` | Key type, such as `RSA`, `EC`, `oct`, `OKP` | Must match the algorithm family |
| `kid` | Key identifier hint | Look up only within a trusted key source |
| `use` | Intended key use, such as `sig` or `enc` | Do not use an encryption key for signatures if policy forbids it |
| `key_ops` | Allowed operations such as `verify`, `sign` | Must not conflict with intended key usage |
| `alg` | Algorithm the JWK declares it is intended for | Cross-check against allowlist and key binding |
| `crv` | Curve in EC/OKP | Must match the required algorithm |
| `n`, `e` | RSA public parameters | Use only valid material from a trusted source |
| `x`, `y` | EC public point coordinates | Must lie on the proper curve and be validated by the library |

**Metadata is meaningful only when the JWK Set comes from a trusted source.** Even a trusted JWKS must be managed as security configuration: if a JWKS URI points to the wrong environment or allows unapproved parties to alter its contents, the API could trust the wrong key.

### `kid` is a hint, not a certificate

A JWT header may contain:

~~~json
{
  "alg": "RS256",
  "kid": "rsa-sig-2026-01"
}
~~~

The Resource Server uses `kid` solely to select a key **within the configured trusted key set**. Never automatically fetch any URL from token headers `jku` or `x5u`, as that can be abused for SSRF or injecting attacker-controlled keys into the verification path.

If `kid` collides or does not match any key in the trusted JWKS, handle it according to selector policy and reject when unverifiable—never fall back to “any key that verifies” outside trust policy.

### `key_ops` and `use` may be absent

A JWK is not required to carry every metadata field. The absence of `use` or `alg` does not automatically make a key safe or unsafe in all contexts. Applications and libraries must combine the fields actually present with **external policy**: issuer, algorithm allowlist, key type, and token purpose.

If a JWK states `alg=RS256` while the JWT header requests `HS256`, the system must never interpret the RSA key as an HMAC secret. Similarly, `use=enc` should not be used for `sig`.

## 14. Distinguishing JWS `alg` from JWE `alg`/`enc`

Another misconception is treating every JOSE `alg` value as a signing algorithm. For **JWS**, `alg` typically indicates the signature/MAC algorithm:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt"
}
~~~

For **JWE**, the header may contain:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "cty": "JWT"
}
~~~

In JWE:

- `alg` is the key management/wrapping algorithm used for encryption.
- `enc` is the content encryption algorithm.
- A JWT may be nested (JWE wrapping JWS) and require multi-step processing if the contract specifies it.

**Never add `RSA-OAEP-256` or `A256GCM` to a JWS signature allowlist.** And do not confuse “successfully decrypting JWE content” with “token accepted”: issuer, audience, timestamps, token type, and authorization must still be checked.

An access token that is not a three-part JWS—such as an opaque token or a JWE—should not be forced through `oauth2ResourceServer().jwt()` unless the system properly supports its structure and verification mechanism.

## 15. When should you change the allowlist?

Reasonable scenarios:

### 15.1. Authorization Server migrates from RS256 to PS256

This is an intentional change to the RSA signature padding scheme. Minimum plan:

1. Confirm the AS actually issues `PS256` and your Resource Server/Nimbus version supports it.
2. Publish the corresponding public keys through the trusted JWKS.
3. Add `PS256` to the allowlist with clear key/issuer boundaries.
4. Monitor requests rejected due to algorithm/key mismatches.
5. Once older RS256 JWTs expire and the AS stops issuing them, narrow the allowlist per policy.

Never convert `RS256` to `PS256` by editing the token header. The signature must be produced by the AS using the right scheme.

### 15.2. AS switches from RSA to ECDSA

If the AS plans to use `ES256`:

- The JWKS must publish EC public keys with `kty=EC` and `crv=P-256`.
- The allowlist must permit `ES256` per contract.
- The decoder/JCA provider must support ECDSA verification in JOSE format.
- Do not try to verify ES256 using an old RSA public key.

During transition, the JWKS may publish both RSA and EC keys with distinct `kid` values. You must know which key binds to which algorithm while preserving issuer/audience policies.

### 15.3. Changing digest size within the same RSA family

`RS256`, `RS384`, and `RS512` all use PKCS#1 v1.5 RSA signatures with different hashes. That does not mean every variant should be enabled automatically. Add an algorithm only when required and backed by an operational plan; evaluate RSA key size, cryptographic recommendations, and library compatibility.

## 16. Diagnosing algorithm and key errors

When a request receives `401 Unauthorized` even though the JWT can be Base64URL-decoded, consider these possibilities:

| Symptom | Possible cause | How to verify |
|---|---|---|
| JWT header `alg=HS256`, RS configured for RS256 only | Algorithm rejected by allowlist | Check which algorithm the AS actually uses |
| JWT header `alg=ES256`, JWKS has only `kty=RSA` | No key of matching type/curve | Inspect JWKS and key types |
| JWT header `alg=RS256`, decoder trusts only PS256 | Mismatched algorithm policy | Align AS and RS allowlists |
| JWT header `alg=none` | Unsigned token under signed-token contract | Reject token |
| New `kid` missing from JWKS cache | AS key rotation, key fetch not refreshed | Check updated JWKS and cache |
| `kid` exists but verification fails | Wrong issuer's key, wrong public key, tampered signature | Verify trust source and actual signing |
| `HS256` token uses too-short or mismatched secret | HMAC key mismatch or policy rejection | Secret manager, key rotation, key length |
| `ES256` token uses P-384 EC key | Curve mismatch | `crv`, signer and decoder configuration |
| JWKS URI points to staging in production | Wrong key source selected | Deployment config, issuer, environment |
| Valid signature, different `aud` | Rejected by JWT claim validation | Audience validator |
| Valid signature, `exp` in the past | Rejected by JWT time validation | Clock synchronization, claim validator |
| Valid token lacking `SCOPE_orders.write` | Authorization failure | Authority mapping, endpoint rules |

Reading `alg` and `kid` only helps **form a hypothesis**. Conclusions must rest on the decoder running real verification with a trusted key and properly configured validators.

### Distinguishing status codes

- **401** typically occurs when the token is missing, invalid, or fails JWT authentication.
- **403** typically occurs when the token is authenticated yet lacks an authority or resource permission.
- JWKS/metadata or key management failures may throw other exceptions depending on version and error handler. Do not assume every network failure maps to 401.

Never **fail open** by accepting tokens when no matching key is available or signature verification cannot run.

## 17. Reading logs and investigating safely

A Bearer token is a credential. Anyone possessing a valid access token can use it within the privileges it grants. Therefore:

- Never log raw tokens or the `Authorization` header.
- Never paste real access tokens into public web JWT decoders, issues, chats, or tickets.
- When diagnostics are needed, log error codes such as `algorithm_not_allowed`, `key_not_found`, `invalid_signature`, or `invalid_audience` if policy permits.
- You may log the identifier of the trusted issuer/JWKS configuration, request ID/trace ID, and endpoint, while avoiding PII or secrets.
- Do not expose internal key/algorithm details to clients if doing so leaks unnecessary information.
- Investigate using short-lived, narrowly scoped test tokens in controlled environments.

Illustrative log:

~~~text
event=jwt_authentication_failed
path=/api/orders
reason=algorithm_not_allowed
configuredAlgorithms=[RS256]
traceId=4cf7...
bearerToken=[REDACTED]
~~~

Never leave “debug only” paths that skip signature verification in production, even when an endpoint has an IP allowlist; fix verification issues at the root cause.

## 18. A complete architectural example

Suppose the shop system has:

- Issuer: `https://idp.example.com/realms/shop`.
- Resource Server: `orders-api`.
- JWT access tokens signed with RSA `RS256`.
- JWKS publishing the issuer's public keys.
- `GET /api/orders` requiring `SCOPE_orders.read`.

`application.yml` configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          jwk-set-uri: https://idp.example.com/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
          jws-algorithms:
            - RS256
~~~

With `SecurityConfig`:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Test request:

~~~bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.example.com/api/orders
~~~

Expected cases:

| JWT | Expected result | Explanation |
|---|---|---|
| `RS256`, RSA key from right issuer, valid signature, `aud=orders-api`, read scope | Allows GET | All core checks pass |
| `HS256` even with payload `aud=orders-api` | Rejected | Not in allowlist |
| `ES256` even if `kid` exists for an RSA key | Rejected | Algorithm/key type mismatch |
| `RS256`, right RSA key, tampered payload | Rejected | Invalid signature |
| `RS256`, valid signature, `aud=billing-api` | Rejected | Wrong audience |
| `RS256`, valid signature and audience, missing read scope | Typically 403 | Authentication succeeded, authorization failed |
| `RS256`, valid signature, expired token | Rejected | Time validator failed |

When changing algorithms, update the **AS signing configuration**, **JWKS/key source**, **RS allowlist**, and **validator policy** in a coordinated plan. Never just alter `alg` in the token header.

## 19. Common misconceptions

**“The JWT header says `alg=RS256`, so the token was definitely signed with RS256.”** Incorrect. That is an untrusted assertion; the Resource Server must verify using the permitted algorithm and matching key.

**“The library understands HS256 and RS256, so just enable both.”** Wrong. Broadening the allowlist increases misconfiguration exposure, especially in systems historically vulnerable to algorithm confusion.

**“An RSA public key can be used as an HMAC secret.”** No. Public keys are public data; an HMAC secret must remain confidential.

**“RS256 and PS256 are identical because both use RSA.”** No. They differ in signature scheme/padding and must be explicitly selected.

**“ES256 only needs any EC key.”** No. It requires ECDSA signing/verification matching P-256.

**“A matching `kid` means the signature is valid.”** No. `kid` only assists key selection; the signature must still be verified.

**“`jwk-set-uri` ensures the issuer and audience are valid.”** No. JWKS is a key source; issuer and audience are separate claim policies.

**“`withPublicKey(...)` works identically for ECDSA and HMAC.”** No. The standard `NimbusJwtDecoder` builder takes an RSA public key. HMAC uses `withSecretKey(...)`, and ECDSA normally uses an appropriate JWKS/JWKSource.

**“Once the signature is valid, `iss`, `aud`, and `exp` are unnecessary.”** Wrong. Both signature verification and claims validation are required.

**“Key rotation only requires changing `kid`.”** No. The AS must publish trusted new key material, sign with the matching key, and ensure the RS refreshes its key source on time.

## 20. Reasoning exercises

### Question 1: JWT has `alg=HS256` while the API only uses RSA

The API trusts only `RS256` and fetches RSA public keys from JWKS. An incoming JWT declares `HS256` while its `sub`/`aud` claims look accurate. Should it be accepted?

> No. `HS256` is not in the allowlist and cannot be verified with an RSA public key. Merely reading the payload establishes no trust.

### Question 2: JWKS contains EC P-384, JWT declares ES256

Can ES256 be verified using a P-384 EC key?

> No. ES256 corresponds to P-256. For EC keys, the curve must match the algorithm, in addition to valid issuer and signature checks.

### Question 3: AS switches from RS256 to PS256

What else is needed besides changing `jws-algorithms`?

> Ensure the AS actually signs with PS256, key/selector and Nimbus/Spring support that scheme, JWKS publishes the right keys, a rollout/rotation plan is in place, and the allowlist is not kept wider than needed.

### Question 4: Custom `JwtDecoder` bean already defined

The application has `jws-algorithms: [RS256]` in YAML, yet the custom decoder accepts another algorithm. Why?

> A custom bean usually causes Boot auto-configuration to back off; YAML properties may not be applied to the custom decoder. Configure the allowlist directly on the builder/processor and preserve issuer/audience/timestamp validators.

### Question 5: Valid JWT signature and issuer, yet 403 returned

Is this an algorithm mismatch?

> Usually no. Once authentication succeeds, 403 typically points to authorization: missing scope/authority or denied by resource policy. Keep verification errors and permission errors distinct.

### Question 6: Why should a shared HMAC secret never be published via JWKS?

> If a shared secret is published, anyone holding it can forge valid MACs. A public JWKS for asymmetric algorithms should publish public-key material only; HMAC secrets must remain protected.

## 21. References

- [Spring Security — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): configuring trusted algorithms, issuer/JWK Set, and JWT decoder.
- [Spring Security — NimbusJwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html): factories/builders for JWKS, RSA public keys, SecretKey, and validators.
- [Spring Security — NimbusJwtDecoder PublicKeyJwtDecoderBuilder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.PublicKeyJwtDecoderBuilder.html): configuring RSA public keys and signature algorithms.
- [Spring Security — NimbusJwtDecoder SecretKeyJwtDecoderBuilder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.SecretKeyJwtDecoderBuilder.html): `macAlgorithm` and HMAC keys.
- [Spring Security — NimbusJwtDecoder JwkSetUriJwtDecoderBuilder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.JwkSetUriJwtDecoderBuilder.html): `jwsAlgorithm`, `jwsAlgorithms`, key sources, and caching.
- [Spring Boot — OAuth2 Resource Server](https://docs.spring.io/spring-boot/reference/security/oauth2.html): JWT Resource Server properties.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JWS format and signature rules.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): `kty`, `kid`, `use`, `key_ops`, and public key representation.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): HS, RS, PS, ES and algorithm/key characteristics.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT structure and claims.
- [RFC 8037 — CFRG Elliptic Curve Algorithms for JOSE](https://www.rfc-editor.org/rfc/rfc8037): OKP keys and EdDSA.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm verification, key/algorithm binding, trusted keys, and preventing JWT confusion.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token profile and verification policy.

When designing a JWT Resource Server, **`alg` in the token is not a security decision**. The decision resides in the **system-managed allowlist**, **matching key types from a trusted issuer**, and **validators checking that the token is meant for this API**. Only after those steps may scopes and claims be used for authorization.
