# JWS and JWE: Signing, Encryption, and Decoder Support Scope

## 1. Context: JWT, JOSE, and the Resource Server

When building a **Spring Security OAuth 2.0 / OIDC Resource Server**, an API typically receives access tokens as JWTs over HTTP:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.test
Authorization: Bearer <ACCESS_TOKEN>
~~~

In designs using **JWT**, the token structure can take two different JOSE forms:

- **JWS (JSON Web Signature)**: protects **integrity** and verifies the signature/MAC of the content. The payload is not hidden merely by signing.
- **JWE (JSON Web Encryption)**: protects **confidentiality** of the content via encryption and provides integrity checks for the ciphertext through an appropriate cryptographic mechanism.

These two forms are easily confused because both can be transmitted as a compact string and both start with a Base64URL-encoded header. However, **verifying a signature** and **decrypting data** are different operations requiring different keys and are usually handled by different components.

**Lesson objective:** understand JWS/JWE within the **JOSE** standard family, identify token types by structure, know the limits of `NimbusJwtDecoder` in Spring Security Resource Server, and know how to design your system when an issuer provides JWEs instead of standard JWS access tokens.

### 1.1. Foundational Terms

| Term | Meaning | Example |
|---|---|---|
| **JWT** | JSON Web Token: represents a set of claims, commonly used for access tokens or ID Tokens | `iss`, `sub`, `aud`, `exp` |
| **JOSE** | Family of standards for signatures, encryption, and keys with JSON | JWS, JWE, JWK, JWA |
| **JWS** | Representation of a message with a digital signature or MAC | JWT signed with RS256 |
| **JWE** | Representation of an encrypted message | JWT encrypted with RSA-OAEP-256 + A256GCM |
| **JWK** | JSON Web Key: JSON representation of a key | RSA/EC public key |
| **JWKS** | JSON Web Key Set: a set of JWKs | Issuer's `jwks_uri` endpoint |
| **JWA** | JSON Web Algorithms: algorithm names and parameters | `RS256`, `PS256`, `ES256`, `A256GCM` |

JWT is defined by RFC 7519. When a JWT is protected with JWS or JWE, it inherits the rules of JWS (RFC 7515) or JWE (RFC 7516). **Not every string with three dot-separated parts is a trustworthy JWT**, and not every JWT string is a signed JWT.

## 2. JWS: Signing to Verify Integrity and Origin

### 2.1. JWS Compact Serialization Structure

A **JWS compact** string usually consists of **3 parts** separated by dots:

~~~text
BASE64URL(protected header)
.
BASE64URL(payload)
.
BASE64URL(signature)
~~~

Written inline over HTTP:

~~~text
eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjMifQ.<signature>
~~~

The string above illustrates structure only; `<signature>` is not a real signature.

The protected header may contain:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "signing-key-2026-01"
}
~~~

The payload may contain claims:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1999999700,
  "exp": 2000000000
}
~~~

The JSON examples above explain structure and do not represent a verifiable token. In JWS Compact, the header and payload are normally only **Base64URL-encoded**, not secretly encrypted; anyone receiving the token string can read the contents by decoding them.

### 2.2. What Does JWS Protect?

Conceptually, for a JWS JWT with `alg = RS256`:

~~~text
signingInput = BASE64URL(header) + "." + BASE64URL(payload)
signature    = RSA-SHA256-SIGN(privateSigningKey, signingInput)
~~~

The Resource Server uses the corresponding **public key** to verify the signature.

~~~mermaid
flowchart LR
    A["Issuer / Authorization Server"] --> B["JWT claims"]
    B --> C["Sign JWS with private key"]
    C --> D["Compact access token (3 parts)"]
    D --> E["Spring Resource Server"]
    F["JWKS public key"] --> G["JWS signature verifier"]
    E --> G
    G --> H["Validate iss, aud, exp, nbf, scope..."]
    H --> I["API access decision"]
~~~

If the signature is valid under a trusted key, the verifier has proof that **the content was protected by the corresponding signing key** and has not been modified since signing. However, the application must still verify which issuer owns the key and which audience the token was issued for; signature verification alone is not sufficient to grant access.

JWS **does not provide confidentiality** for the payload. Never put passwords, private keys, secrets, or unnecessary personal data into claims assuming JWT signing hides them.

### 2.3. Common Signature Algorithms

| `alg` | Verification method | Characteristics |
|---|---|---|
| `RS256` | RSA public key, SHA-256 | Widely supported across OAuth/OIDC providers |
| `PS256` | RSA-PSS public key, SHA-256 | RSA-PSS signature |
| `ES256` | EC public key, ECDSA P-256/SHA-256 | Smaller EC signatures in many scenarios |
| `HS256` | Shared secret, HMAC-SHA256 | Signer and verifier share the same secret |

With multiple independent Resource Servers, **asymmetric** signatures allow APIs to verify using a public key without holding the private signing key. With HMAC, any party holding the shared secret can generate valid MACs, requiring a different trust boundary design.

The `alg` value inside a token is **untrusted input** until validation completes. The system must enforce an **algorithm allowlist** and configure keys of the expected type. Never allow a token to dictate which algorithm or key the application uses without explicit validation.

### 2.4. `kid` and JWKS Do Not Establish Trust by Themselves

The `kid` header helps find **the right key within an already trusted key set**. It does not mean the Resource Server may download a key from an arbitrary URL supplied by the token.

Typical flow:

1. The Resource Server is preconfigured with a trusted issuer/JWKS URI.
2. The token carries a `kid` indicating the signing key.
3. The decoder looks up the key in the configured issuer's JWKS.
4. It verifies the signature using an allowed algorithm.
5. It validates `iss`, `aud`, `exp`, and other claims/policies.

A JWKS normally serves **public keys** for JWS verification; it does not distribute the Authorization Server's private signing key.

## 3. JWE: Encryption to Protect Content

### 3.1. JWE Compact Serialization Structure

A **JWE compact** string typically has **5 parts**, also joined by dots:

~~~text
BASE64URL(protected header)
.
BASE64URL(encrypted key)
.
BASE64URL(initialization vector)
.
BASE64URL(ciphertext)
.
BASE64URL(authentication tag)
~~~

Compact notation:

~~~text
<protected-header>.<encrypted-key>.<iv>.<ciphertext>.<tag>
~~~

Note: the `encrypted-key` segment can be **empty** for some key management modes such as `alg = dir`. Thus an empty segment does not by itself make a JWE string malformed.

A typical JWE protected header:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "kid": "orders-encryption-2026-01",
  "typ": "JWT"
}
~~~

In JWE:

- **`alg`** specifies the **key management/key wrapping** algorithm used to obtain the Content Encryption Key (CEK), such as `RSA-OAEP-256`.
- **`enc`** specifies the **content encryption** algorithm using the CEK, such as `A256GCM`.
- **IV** (initialization vector/nonce) and **authentication tag** support content encryption; parameters must be generated and used according to the algorithm's requirements.
- **Ciphertext** holds the encrypted data; claims cannot be derived simply by Base64URL-decoding.

JWE requires decryption with the appropriate key. If the recipient's RSA public key was used to encrypt the CEK, the recipient needs the corresponding **private decryption key**; a public JWKS used for JWS signature verification **does not automatically enable JWE decryption**.

### 3.2. Security Properties of JWE

JWE protects **content confidentiality** and **ciphertext integrity**. With AEAD algorithms like `A256GCM`, the authentication tag detects tampering with the ciphertext or associated authenticated data.

However, **encryption does not equate to proving the issuer's identity**.

Suppose the Orders API's public key is published so parties can encrypt tokens to it. Anyone possessing that public key can construct a JWE encrypted for the Orders API; therefore, the API **successfully decrypting** it does not prove the message was issued by a legitimate Authorization Server.

To authenticate the issuer independently of whoever performed encryption, you need an explicit issuer-authentication mechanism: typically a **JWS signed first and then wrapped in JWE** (nested JWT), or another trust model with explicit key, source, and claim bindings.

### 3.3. Direct Comparison of JWS and JWE

| Criterion | JWS | JWE |
|---|---|---|
| Primary goal | Signature/MAC, integrity, signing-key authentication | Content confidentiality and ciphertext integrity/authentication tag |
| Compact serialization | Usually 3 parts | Usually 5 parts |
| Is the payload readable on Base64URL-decode? | Yes, for standard JWS JWTs | No, requires decryption |
| Key headers | `alg`, `kid`, `typ` | `alg` (key management), `enc` (content encryption), `kid` |
| Key on Resource Server | Public key for signature verification (common) or shared secret | Private decryption key or appropriate key material |
| Sufficient to authenticate the issuer? | Only when the signing key and issuer are trusted and claims are validated | Not by default; depends on origin authentication model and may need inner JWS |
| Role with default Spring JWT Resource Server | Standard supported signed JWT format | Requires dedicated decryption handling before/outside the default decoder |

Do not interpret these two standards as "JWE is more secure than JWS in every situation." **JWS and JWE address different protection needs.** An API may need JWS plus TLS, or add JWE if confidentiality of claims across multiple intermediaries is required.

## 4. Signed-Then-Encrypted JWT: Nested JWT

When you need to **verify a token issued by the issuer** while **preventing intermediaries from reading claims**, you can use a **sign-then-encrypt** pattern.

~~~mermaid
flowchart TD
    A["JSON JWT claims"] --> B["Issuer signs to create JWS"]
    B --> C["Compact JWS - 3 parts"]
    C --> D["Encrypt into outer JWE"]
    D --> E["Compact JWE - 5 parts"]
    E --> F["Resource Server decrypts JWE"]
    F --> G["Extract inner JWS"]
    G --> H["Verify JWS with issuer signing key"]
    H --> I["Check iss / aud / exp / scope"]
    I --> J["Grant access if valid"]
~~~

On the outer JWE layer, the `cty` header can indicate that the inner content is a JWT:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "cty": "JWT"
}
~~~

Under RFC 7519 nested JWT rules, `cty: "JWT"` signals that the payload is a wrapped JWT. However, **`cty` is only metadata**; it does not replace decryption, signature verification, or policy validation.

Processing on the Resource Server must maintain the proper order:

1. Validate syntax and **accept only approved JWE algorithms**.
2. Select the decryption key from a trusted key set, decrypt, and verify the integrity tag.
3. Verify that the inner payload matches the token type/profile permitted by the contract.
4. If the inner payload is a JWS, **verify the JWS signature** with the trusted issuer's signing key.
5. Validate `iss`, `aud`, `exp`, `nbf`, token type, and API scopes/authorities.
6. Only after all checks succeed, construct the authentication principal and make authorization decisions.

Never extract JSON claims after JWE decryption and build a principal while skipping proof that a trusted issuer issued it. Similarly, never skip audience validation just because the outer JWE targeted the API's decryption key.

## 5. What Does the Default Spring Security JWT Decoder Support?

### 5.1. Resource Server Handling Bearer Tokens and JWS

With Spring Boot, after adding the OAuth2 Resource Server dependency and configuration:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

The application can build a Resource Server that accepts **JWS-signed JWT access tokens**. `issuer-uri` is an example issuer URL; use your actual Authorization Server value.

Example `SecurityFilterChain`:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Here:

- `BearerTokenAuthenticationFilter` extracts the Bearer token string.
- `JwtAuthenticationProvider` invokes `JwtDecoder` to decode/validate the JWT.
- The common default implementation is **`NimbusJwtDecoder`**, integrated with the Nimbus JOSE + JWT library.
- The decoder verifies the JWS with the appropriate key and algorithm, then runs configured JWT validators.
- After authentication succeeds, Spring builds an authentication object; endpoint policies check access permissions.

**Distinguish library capabilities from Spring configuration capabilities:** the **Nimbus JOSE + JWT** library itself has APIs for JWS, JWE, and many JOSE features; however, **Spring Security's `NimbusJwtDecoder` does not automatically decrypt compact JWEs into validated JWTs under standard JWT Resource Server configuration**. Having the Nimbus dependency on the classpath does not automatically enable encrypted access token support.

### 5.2. JWS Decoder Using JWKS

A Resource Server typically trusts an issuer and the public keys published at its JWKS endpoint. Depending on configuration, Spring can read the issuer's metadata to discover `jwks_uri` and use those public keys to verify signatures.

Header:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026-01",
  "typ": "JWT"
}
~~~

The verifier uses `kid` to select a public key from the trusted JWKS while still enforcing the configured algorithm constraints. It does not need the Authorization Server's private signing key.

**A JWKS public key for JWS verification is different from a JWE decryption key.** Pointing `jwk-set-uri` to an endpoint serving signing public keys will not enable the Resource Server to decrypt JWE ciphertext.

### 5.3. Configuring Allowed JWS Algorithms

Example explicitly selecting `RS256` when the issuer's contract specifies RS256 signing:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder() {
        return NimbusJwtDecoder
            .withJwkSetUri("https://id.example.test/realms/shop/protocol/openid-connect/certs")
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();
    }
}
~~~

The `jwks_uri` path in the example follows a common IdP layout; inspect your actual provider's metadata. This snippet illustrates **restricting the JWS verification algorithm**, not a complete application validation setup.

**Note when defining a custom decoder bean:** add or preserve all required validators such as issuer, expiration, and audience. Do not accidentally drop the issuer validator just because you replaced Spring Boot's auto-configured decoder with your own bean.

A more complete validator example for signed JWT access tokens is shown below.

### 5.4. Validator for JWS Access Tokens

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class OrdersJwtConfig {

    private static final String ISSUER =
        "https://id.example.test/realms/shop";

    private static final String JWKS_URI =
        "https://id.example.test/realms/shop/protocol/openid-connect/certs";

    private static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS_URI)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> standard =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> expectedAudience = jwt -> {
            if (jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Access token audience is not orders-api",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                standard,
                expectedAudience
            )
        );

        return decoder;
    }
}
~~~

The code above illustrates verifying **valid JWS signature + issuer/lifetime + audience**. Endpoints still require `hasAuthority("SCOPE_orders.read")` or equivalent authorization checks. For JWT access token standards and requirements like `typ = at+jwt`, additional validators matching the token profile and your Spring Security version may be needed.

None of the libraries, beans, or validators shown here **turn `NimbusJwtDecoder` into a JWE decoder**.

## 6. What Happens When You Send a JWE to a Default-Configured JWT Resource Server?

Suppose the client sends a **5-part compact JWE** as a Bearer token:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <jwe-header>.<encrypted-key>.<iv>.<ciphertext>.<tag>
~~~

The resolver can still extract the string from the `Authorization` header because it is a Bearer token at the HTTP layer. However, standard `NimbusJwtDecoder` expects a **signed JWT/JWS** under Resource Server JWT configuration.

Consequently, the API **does not automatically decrypt** a JWE token solely from `issuer-uri` or `jwk-set-uri`; the typical result is **401 Unauthorized** due to JWT authentication failure, rather than a decrypted JWT evaluated for scopes.

Actions that do not solve JWE support:

- Changing the header name from `Authorization` to `X-Access-Token`: only changes where the Bearer token is read.
- Adding `jwk-set-uri` pointing to signing keys: only supplies public keys for JWS signature verification.
- Setting `jwsAlgorithm(ES256)` or `jwsAlgorithm(RS256)`: only configures **JWS** verification, not JWE.
- Base64URL-decoding the ciphertext segment: that is not decryption.
- Parsing JSON claims out of ciphertext or skipping validation after decryption: does not create a trustworthy authentication.
- Using an OIDC ID Token instead of an access token: an ID Token has its own audience and purpose and must not be used as an API access credential.

### 6.1. Behavior Matrix by Token Type

| Incoming token | Default JWT Resource Server | Explanation |
|---|---|---|
| Signed JWS access token (3 parts), valid algorithm/issuer/claims | **Can authenticate** | Both JWS signature and validators must succeed |
| Signed JWS with invalid signature | **Rejected** | Signature verification fails |
| Signed JWS with wrong `aud` when audience validator is enabled | **Rejected** | Token is not intended for the API |
| Compact JWE (5 parts) | **Does not auto-decrypt** | Requires an explicitly configured JWE decryption component |
| Nested JWT: JWS inside JWE | **Does not auto-decrypt outer layer** | Must decrypt JWE and then verify inner JWS |
| Opaque access token | **Cannot be verified as a JWT** | Requires opaque-token introspection if supported by the provider |
| Plain/unsigned JWT | **Not treated as a trusted signed JWS** | Cannot skip signing requirements just because payload is JSON |

This table describes Spring Security Servlet `oauth2ResourceServer(...jwt(...))` with standard JWT configuration. Systems using a custom `JwtDecoder` or translating tokens at an API gateway have different architectures and must be evaluated separately.

## 7. If the System Must Accept JWEs, How Should It Be Designed?

### 7.1. Prefer Aligning the Token Issuance Contract First

If the Resource Server only needs to verify access tokens and has no requirement for token-layer payload encryption, the simplest and most maintainable approach is for the Authorization Server to issue **signed JWS access tokens** with the proper audience for the API.

TLS protects data in transit; safe logging and token storage remain mandatory. JWS does not hide claims from token holders, so minimize sensitive claims and keep lifetimes short.

Not every IdP issues JWEs to Resource Servers. Confirm explicitly:

- Is the access token issued by the issuer **JWS, JWE, or opaque**?
- If it is a JWT, does it have **3 or 5 compact parts**?
- What scopes, audience, and token type are used?
- Does the issuer publish a **JWKS for signing keys**, and who owns the JWE decryption key?
- Is there a genuine requirement to keep claims confidential across proxies/gateways that TLS alone cannot address?

Never guess the access token format solely from whether the system supports OIDC or whether clients receive ID Tokens.

### 7.2. Architecture Option A: Decrypt JWE Before the Resource Server

A dedicated component can **decrypt and verify** the JWE, then forward a tightly bound internal token/credential to the backend. If the inner result is an unmodified issuer-signed JWS with the right audience, the Resource Server can verify that JWS with a standard decoder.

Conceptual diagram:

~~~mermaid
flowchart LR
    A["Client: Bearer JWE"] --> B["Gateway / JWE service"]
    B --> C["Decrypt + enforce alg/enc/key/typ"]
    C --> D["Validate nested JWS + issuer/audience"]
    D --> E["Internal token exchange / trusted handoff"]
    E --> F["Spring Resource Server"]
    F --> G["Endpoint policy"]
~~~

This option requires clearly defined **trust boundaries**: can the backend be called directly bypassing the gateway; does the gateway strip client-supplied headers; does internal traffic use TLS/mTLS or service-to-service authentication; does the forwarded token target the backend's audience? Never blindly trust a plaintext header like `X-Authenticated-User` that any client could spoof.

### 7.3. Architecture Option B: Writing a Custom \`JwtDecoder\`

Spring Security provides the **`JwtDecoder`** interface contract. If an API must accept JWEs directly, a custom implementation can:

1. Receive the Bearer token string from the filter.
2. Identify and parse **compact JWE** from untrusted input.
3. Allow only the `alg` and `enc` combinations approved by the contract.
4. Select the proper decryption key, verify integrity, and decrypt the JWE.
5. If the contract specifies a nested JWS, verify the inner JWS using the **trusted issuer's key**.
6. Fully validate `iss`, `aud`, `exp`, `nbf`, token type, scopes, and related constraints.
7. Only upon full success return a valid Spring `Jwt` to the Resource Server pipeline.

The integration shape with Spring can be illustrated by the following **pseudocode**; this outlines the processing steps, not a ready-made class to copy into production:

~~~java
// PSEUDOCODE: requires full decryption, signature verification,
// and claim validation per the real JWE/JWS contract.
class ContractAwareJweJwtDecoder implements JwtDecoder {

    @Override
    public Jwt decode(String compactJwe) throws JwtException {
        var decrypted = decryptJweWithApprovedAlgorithmsAndKeys(compactJwe);
        var signedJws = requireNestedSignedJwt(decrypted);
        var validatedJwt = verifyJwsAndValidateClaims(signedJws);

        return validatedJwt;
    }
}
~~~

The methods `decryptJweWithApprovedAlgorithmsAndKeys`, `requireNestedSignedJwt`, and `verifyJwsAndValidateClaims` are only descriptive placeholders. Never implement them with manual Base64URL or JSON parsing; use a proper JOSE library, explicit key and algorithm policies, rotation/error handling, and full validation.

In Spring Security, the custom decoder is wired into the Resource Server:

~~~java
JwtDecoder customDecoder = /* complete JWE decoder provided by the application */;

http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt.decoder(customDecoder))
);
~~~

This snippet shows the **extension point**, not a `customDecoder` implementation. When multiple `SecurityFilterChain` beans exist, wire the decoder to the right chain handling those tokens. If the decoder is meant only for JWEs, the API should not silently accept unsigned JWTs or tokens from another profile.

### 7.4. A JWE Is Not Necessarily a Nested JWS

Decrypting a JWE may yield a JSON claims set directly or an inner JWT/JWS, depending on the contract. Never assume every decrypted payload is a signed JWT, or assume a decrypted JWE automatically proves the issuer.

For systems authenticating an external Authorization Server, a **nested JWS inside JWE** is the clean way to separate **signing-source proof** from **content confidentiality**. If another JWE profile is chosen, clearly document issuer authentication proof, key ownership, and the threat model. Specifically, encrypting with the API's public key only ensures only the private-key holder can read it—it **does not prove who encrypted it**.

### 7.5. Do Not Downgrade to Client Secrets or Arbitrary Substitutes

Never "solve" JWE by exporting private decryption keys to untrusted Resource Servers, placing private keys into a public JWKS, skipping signature verification in a nested JWT, or replacing the token with an unauthenticated gateway header.

If the provider supports **OAuth 2.0 Token Introspection** for opaque access tokens, that is a separate mechanism from JWE decryption. Introspection may fit opaque tokens, but there is no general rule that every JWE can be introspected; it depends on the Authorization Server and API contract.

## 8. Examples: Distinguishing Protection Layers and Readable Data

### 8.1. JWS Access Token

Header:

~~~json
{"alg":"RS256","typ":"JWT","kid":"sig-2026-a"}
~~~

Payload:

~~~json
{
  "iss":"https://id.example.test/realms/shop",
  "sub":"user-123",
  "aud":"orders-api",
  "scope":"orders.read",
  "exp":2000000000
}
~~~

Anyone holding the token can read claims via Base64URL-decoding, but cannot change `aud` from `orders-api` to `billing-api` while preserving a valid RSA signature without the private signing key.

The Resource Server must verify the signature and claims; `scope` is only one part of authorization. When reading orders, the application may still need to verify user/tenant ownership of each record.

### 8.2. JWE Access Token

Outer protected header:

~~~json
{
  "alg":"RSA-OAEP-256",
  "enc":"A256GCM",
  "cty":"JWT",
  "kid":"enc-2026-a"
}
~~~

The payload is ciphertext, so `sub`, `aud`, or `scope` cannot be viewed via Base64URL-decoding alone. The recipient must hold the matching private decryption key to decrypt it. If decryption yields a nested JWS, both the JWS signature and inner claims must be verified.

The header above **only illustrates metadata**, not a complete JWE. All cryptographic values such as IV, CEK, tag, and signature must be generated by a compliant library.

### 8.3. JWT with `alg: none`

A token may carry the header:

~~~json
{"alg":"none","typ":"JWT"}
~~~

That is not a signed JWS that a Resource Server should accept in an issuer-signed access token flow. Even though the JWT representation spec describes unsecured JWTs, never enable accepting unsigned JWTs simply because a payload has plausible-looking `sub`, `iss`, and `scope` fields.

## 9. Security Boundaries That Must Be Explicitly Designed

### 9.1. Do Not Trust Keys from Token-Specified URLs

JOSE headers can contain metadata such as `kid`, and some profiles include key references. These are untrusted external inputs. The Resource Server must use its **configured issuer, key source, and algorithm allowlist**, never arbitrarily downloading keys from `jku`/`x5u` or unapproved URLs to verify a token.

Otherwise, an attacker could attempt to inject their own key into verification.

### 9.2. Validate Issuer and Audience After Cryptographic Verification

- **`iss`**: token was issued by the expected Authorization Server.
- **`aud`**: token is intended for the current Resource Server.
- **`exp`**, **`nbf`**: time window during which the token is allowed.
- **`scope`** or mapped authorities: API permissions.
- **`typ`** and token profile: ensure the API does not mistakenly accept ID Tokens or JWTs meant for another purpose.
- **`sub`**, tenant, resource ownership: enforce business policies as needed.

Never use email/name claims as a substitute for authorization. A JWT with a valid signature whose `aud` does not include Orders API must still be rejected when the API enforces its audience.

### 9.3. Separate Signing Keys and Decryption Keys

In an asymmetric deployment:

- The Authorization Server holds the **private signing key** to create JWS tokens.
- The Resource Server uses the **public verification key** to verify JWS tokens.
- For JWE encrypted to the Resource Server, the sender can use the Resource Server's **public encryption key**.
- The Resource Server holds the matching **private decryption key** to unwrap the JWE.

An organization may maintain multiple keys and algorithms per profile; the principle is that each key serves a distinct cryptographic purpose with separate lifecycle and access controls. Never reuse the same key for every cryptographic task by default.

### 9.4. Key Rotation and Operations

Issuers rotate signing keys periodically. For JWS, a JWKS can hold multiple public keys during a transition window; `kid` helps pick the right key. For JWE, rotating decryption keys must ensure non-expired tokens can still be decrypted per policy.

Systems should manage:

- Active keys, legacy keys in a transition window, and revoked keys.
- JWKS caching/refresh behavior in the library and infrastructure.
- Network failures reaching the issuer/JWKS and authentication failure responses when keys cannot verify tokens.
- Avoiding logging raw access token strings or sensitive decrypted plaintext.
- Bounding token size, nesting depth, and algorithms to mitigate resource exhaustion risks.
- Protecting cryptographic configurations and secrets/private keys in an appropriate key management store.

## 10. Troubleshooting Scenarios

### 10.1. Token Has Five Parts and the API Returns 401

If the Resource Server only configures:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

and the incoming token is actually a **compact JWE**, the root cause is likely that the default decoder does not support JWE decryption. Confirm the **format/token contract** with the issuer. Do not try changing `jwsAlgorithm` or headers to "enable JWE."

### 10.2. Token Has Three Parts but Still Returns 401

Three parts suggest a compact JWS, so verify:

1. Is the header `alg` in the permitted algorithms?
2. Does the signature match a trusted key from the issuer?
3. Does `iss` match the configured issuer?
4. Are `exp`/`nbf` valid for the current time?
5. Is `aud` intended for this API?
6. Was an OIDC client **ID Token** mistakenly sent instead of a Resource Server **access token**?

Never diagnose a token by printing the raw value to logs or pasting it into third-party websites. Use non-sensitive metadata or a test environment with synthetic tokens to verify structure and configuration.

### 10.3. JWE Decrypts Successfully, Yet Authorization Still Cannot Be Granted

Decryption only produces plaintext. If the payload is a JWS, you must verify the JWS signature, issuer, audience, and permissions. If the payload is only JSON claims, check what contract mechanism proves the issuer and binds the token to the issuer/API. Without sufficient trust proof, do not build an `Authentication` for the request.

### 10.4. Key Exists in JWKS, Yet JWE Cannot Be Decrypted

The JWKS fetched by the Resource Server may contain only **public signing keys**. Decrypting a JWE normally requires a **private decryption key** or an appropriate symmetric key, plus support for the token's actual `alg` and `enc`. Matching a `kid` alone does not mean a key is valid for decryption.

### 10.5. Should Every Access Token Be Encrypted for Extra Security?

Not always. JWS is often sufficient for APIs authenticating access over HTTPS; minimize unnecessary claims and protect tokens from logs and leaks. JWE adds claim confidentiality when specifically needed, at the cost of extra complexity in decryption key management, nested token flows, rotation, and error handling. Choose based on your threat model, not the number of cryptographic layers.

## 11. Implementation Decision Summary

| Need | Typically appropriate design |
|---|---|
| API validates tokens signed by an issuer | **JWS** JWT and Spring Security's `NimbusJwtDecoder` |
| API accepts only tokens from its issuer and audience | JWS signature validation + `iss`/`aud`/lifetime + authorization |
| Must hide claims from untrusted intermediaries | Consider **JWE** per an explicit contract |
| Need both encryption and proof of issuer signature | **Nested JWS inside JWE**, decrypt then verify signature/claims |
| Issuer issues opaque access tokens | Use Resource Server **opaque token introspection** if supported by issuer |
| 5-part token while Resource Server only configures JWT issuer URI | Confirm and handle **JWE** explicitly; default JWT decoder is insufficient |
| Public keys from `jwks_uri` | Typically for **JWS verification**, not private-key JWE decryption |

**The most critical distinction:** **JWS signs to verify integrity and signing source under a trusted key; JWE encrypts to hide contents and verify ciphertext integrity.** For Spring Security OAuth 2.0 Resource Server, `oauth2ResourceServer().jwt()` with `NimbusJwtDecoder` is the standard path for **signed JWS access tokens**. **Encrypted JWEs and nested JWTs require dedicated decryption, origin verification, and validation design**, and are not handled automatically simply by having the Nimbus dependency or configuring an issuer/JWKS.

### Reference Specifications

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security API — NimbusJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
