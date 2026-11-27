# NimbusJwtDecoder and Key Provider Sources

When a Spring Security API receives an **OAuth 2.0 Bearer Access Token** in JWT format, it must know **which key to use to verify the signature** and **which claims to check** before allowing the request to access resources. The component handling most of this work in Spring Security Servlet is **NimbusJwtDecoder**.

There are several ways to provide keys to the decoder: letting it discover the **JWK Set** from the issuer's metadata, configuring the **JWK Set URI** directly, loading a static **RSA public key**, or using a **shared secret** for HMAC-signed JWTs. Each approach has its own trust model, operational behavior, and limitations.

This lesson focuses on **JWT Access Tokens at a Resource Server** in the context of **Spring Boot 3.x, Spring Security 6.x, Java 17+, and Spring MVC/Servlet**. The URIs, key IDs, and tokens in the examples are illustrative data and must be replaced with your actual issuer configuration.

## 1. What does NimbusJwtDecoder do?

Spring Security defines the `JwtDecoder` interface with the responsibility of accepting a JWT string and returning a processed `Jwt` object, or throwing a `JwtException` if the token cannot be accepted. **NimbusJwtDecoder** is the implementation built on the **Nimbus JOSE + JWT** library.

In a Resource Server using JWTs, the typical path is:

~~~text
Client
  |
  | GET /api/orders
  | Authorization: Bearer <access-token>
  v
Spring SecurityFilterChain
  |
  v
BearerTokenAuthenticationFilter
  |
  v
JwtAuthenticationProvider
  |
  v
NimbusJwtDecoder
  |-- read JWT header/payload
  |-- verify signature/MAC with trusted key
  |-- execute OAuth2TokenValidator<Jwt> instances
  |   (issuer, expiration, audience, token profile...)
  v
JwtAuthenticationToken in SecurityContext
  |
  v
AuthorizationFilter / Method Security
  |-- scope / authority
  |-- tenant permissions, business data permissions
  v
Controller or reject request
~~~

**Decoding is not the same as authentication.** Anyone can split a JWS JWT into three segments and Base64url-decode the payload to **read** claims. The API can only **trust** those claims after the decoder verifies the token with a trusted key/algorithm and the validators check the API context.

A signed JWT typically has three segments:

~~~text
BASE64URL(JOSE_HEADER).BASE64URL(CLAIMS).BASE64URL(SIGNATURE)
~~~

Examples of JSON structures inside a token:

~~~json
{
  "alg": "RS256",
  "kid": "key-2026-01",
  "typ": "at+jwt"
}
~~~

~~~json
{
  "iss": "https://login.example.test/realms/demo",
  "sub": "employee-123",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "scope": "orders.read"
}
~~~

**alg**, **kid**, and **typ** belong to the JOSE header; **iss**, **sub**, **aud**, **exp**, and **scope** belong to claims. The two JSON blocks above do not form a valid JWT because there is no real signature. A JWS-format JWT **does not encrypt its contents**; the payload remains readable. JWE is a different encryption mechanism and is not supported by default in a standard JWT Resource Server configuration.

## 2. Choosing a key source: decision diagram

~~~text
Which format does the Authorization Server issue tokens in?
  |
  +-- Opaque Access Token
  |      -> OAuth2 Resource Server opaqueToken()
  |      -> introspection; do not use NimbusJwtDecoder to verify JWS
  |
  +-- Signed JWT Access Token
         |
         +-- Does IdP publish OIDC / Authorization Server metadata?
         |      -> issuer-uri / JwtDecoders.fromIssuerLocation()
         |
         +-- Is a trusted JWK Set URI already known?
         |      -> jwk-set-uri / NimbusJwtDecoder.withJwkSetUri()
         |
         +-- Only a single static RSA public key available?
         |      -> public-key-location / NimbusJwtDecoder.withPublicKey()
         |
         +-- Does JWT use a pre-agreed HMAC symmetric key?
                -> NimbusJwtDecoder.withSecretKey()
~~~

| Key source | How to configure | Strengths | Aspects to control |
| --- | --- | --- | --- |
| **Issuer metadata** | `issuer-uri`, `JwtDecoders.fromIssuerLocation`, `withIssuerLocation` | Discovers JWK Set via metadata; suits standard IdPs, supports multiple public keys and rotation. | Issuer must be trusted, discovery/network depends on config, check `iss`. |
| **Direct JWK Set URI** | `jwk-set-uri`, `withJwkSetUri` | Knows the exact key endpoint; can decouple discovery at startup. | JWK URI must be configured securely; proactively maintain issuer/audience validators. |
| **Static RSA public key** | `public-key-location`, `withPublicKey` | No need to fetch JWKs over the network during verification. | Rotating keys requires updating deployment/config; choose matching algorithm and claim checks. |
| **Shared secret HMAC** | `withSecretKey` | Suits systems with tight control over both signing and verification sides. | Every party holding the secret can forge a valid MAC; requires strict secret protection/distribution. |

**None of these choices makes the decoder understand business permissions on its own.** Even with a valid signature, the API must still check **issuer, audience, lifetime, token profile, and permissions**; an Access Token for another API should not be accepted just because it comes from the same IdP.

## 3. Dependencies: Resource Server and JOSE

In a Spring Boot Gradle project (Groovy DSL) with dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

The Resource Server starter in mainstream Spring Boot 3.x releases already brings the required JWT/JOSE dependencies into the dependency tree. If configuring Spring Security modules manually, a JWT Resource Server typically needs **both**:

~~~groovy
implementation 'org.springframework.security:spring-security-oauth2-resource-server'
implementation 'org.springframework.security:spring-security-oauth2-jose'
~~~

**spring-security-oauth2-resource-server** provides the Bearer token mechanism and security integration; **spring-security-oauth2-jose** contains the JWT decoder/JOSE classes. Do not mix arbitrary versions when the Spring Boot BOM manages dependencies. An API using only opaque tokens may not need JWS decoding, even though the starter may still bring JOSE as a transitive dependency.

## 4. Key source #1: discovering the JWK Set via issuer

This is usually the simplest option when the Authorization Server/OpenID Provider supports standard metadata discovery.

### 4.1. Configuring with Spring Boot

Example `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/demo
          audiences:
            - orders-api
~~~

Meaning:

1. **issuer-uri:** identifies the issuer trusted by the Resource Server. Spring Security can discover the appropriate metadata to obtain **jwks_uri**.
2. **jwks_uri:** the JWK Set address described by the issuer's metadata, where public keys are published.
3. **audiences:** requires the **aud** claim to contain **orders-api** in Spring Boot versions that support this property. If your version lacks a matching property, add an audience validator.

In the metadata discovery flow, the decoder uses information published by the **configured issuer**, for example:

~~~text
Trusted issuer
  https://login.example.test/realms/demo
       |
       v
OIDC / Authorization Server metadata
  "issuer": "https://login.example.test/realms/demo"
  "jwks_uri": "https://login.example.test/realms/demo/protocol/openid-connect/certs"
       |
       v
JWK Set (public keys)
       |
       v
Verify JWS, then validate JWT claims
~~~

This is the **configuration and key usage flow**, not a claim that every Bearer request fetches metadata from scratch. The decoder and caching layer usually reuse key information. Exact initialization, fetching/caching, and connection timing depend on the version and configuration; account for scenarios where the issuer or key endpoint is unavailable.

**Do not** accept an arbitrary token, read `iss` from the unverified payload, and then treat that URL as a trusted issuer. If a Resource Server must accept multiple issuers, every issuer must be allowlisted by an explicit rule.

### 4.2. Initializing with JwtDecoders.fromIssuerLocation

If you need to explicitly define a decoder bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoders;

@Configuration
public class JwtDecoderConfig {

    private static final String ISSUER =
        "https://login.example.test/realms/demo";

    @Bean
    JwtDecoder jwtDecoder() {
        return JwtDecoders.fromIssuerLocation(ISSUER);
    }
}
~~~

`JwtDecoders.fromIssuerLocation` performs discovery on the appropriate endpoint and configures a decoder with the necessary validators to check the issuer per framework defaults. **The API's audience still needs to be checked separately**, unless enforced by an active configuration.

With this approach, if you want to attach an audience validator to a specific decoder, it is usually more convenient to use **NimbusJwtDecoder** directly with `setJwtValidator` (see section 8).

### 4.3. Using NimbusJwtDecoder.withIssuerLocation directly

In Spring Security 6.1+, the builder supports:

~~~java
NimbusJwtDecoder decoder =
    NimbusJwtDecoder.withIssuerLocation(
        "https://login.example.test/realms/demo").build();
~~~

**Important reminder:** when building a decoder manually with the builder, **configure validators explicitly**; do not assume that giving the builder an issuer URI always means the exact issuer and audience policies for your API are already enforced:

~~~java
decoder.setJwtValidator(
    JwtValidators.createDefaultWithIssuer(
        "https://login.example.test/realms/demo"));
~~~

The snippet above adds the default validators, including the issuer check; if the API requires an audience check, combine it with an additional validator (section 8).

## 5. Key source #2: directly configured JWK Set URI

When you know the exact location of the public keys, the Resource Server can use the **JWK Set URI** without relying on issuer metadata discovery to locate that URI.

### 5.1. Spring Boot: issuer-uri combined with jwk-set-uri

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/demo
          jwk-set-uri: https://login.example.test/realms/demo/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

**jwk-set-uri** points to the endpoint hosting public keys; **issuer-uri** remains responsible for binding tokens to a valid issuer. Explicitly declaring the JWK URI can avoid requiring a connection to the metadata discovery endpoint when the Resource Server starts up, depending on configuration and version.

**Do not configure only the key source and forget the issuing authority.** The same key might be used across multiple contexts, or an attacker might attempt to send a token with syntactically valid claims but an inappropriate issuer/audience.

### 5.2. JWK Set structure

Example representation of a **public** RSA JWK Set (the `n` value is shortened for readability):

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "PUBLIC_RSA_MODULUS_BASE64URL",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "key-2026-02",
      "use": "sig",
      "alg": "RS256",
      "n": "ANOTHER_PUBLIC_RSA_MODULUS_BASE64URL",
      "e": "AQAB"
    }
  ]
}
~~~

This is **illustrative data, not real RSA keys usable for verifying tokens**.

- **kty:** key type, e.g., RSA.
- **kid:** key identifier used to distinguish and select the matching key.
- **n**, **e:** RSA public key parameters.
- **use**, **alg:** metadata describing intended usage/algorithm; the Resource Server must still **restrict algorithms according to its trust policy**, rather than expanding to any algorithm suggested by an external source.
- **keys:** array allowing multiple public keys to be published simultaneously for key rotation.

A public JWK Set for RSA verification **must never contain private key material** such as the private parameter `d`. The Authorization Server keeps the private key secret for signing.

### 5.3. NimbusJwtDecoder.withJwkSetUri

When configuring in Java:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwksDecoderConfig {

    private static final String ISSUER =
        "https://login.example.test/realms/demo";
    private static final String JWKS_URI =
        "https://login.example.test/realms/demo/protocol/openid-connect/certs";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS_URI)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(ISSUER));

        return decoder;
    }
}
~~~

This bean illustrates **signature and issuer** checks. To protect a real API, add an **audience validator** as shown in section 8; do not treat this as a complete policy just because the token is signed.

In particular, **withJwkSetUri(JWKS_URI)** specifies where to fetch keys, but by itself **should not be treated as guaranteeing a valid issuer**. Set the validator explicitly in a custom decoder, or use Boot configuration that enforces the corresponding constraints.

### 5.4. Why must the JWK Set URI be trusted?

The JWK Set is the source of **verification keys**. If an attacker controls the key source, they can generate a new key pair, sign forged tokens, and have the system verify the signature using their own public key. Therefore:

- Configure the URI from a trusted, managed source; use HTTPS and verify TLS.
- Do not arbitrarily use the token's `jku` or `x5u` headers, or an unverified `iss` claim, to automatically fetch keys from a client-specified URL.
- Do not select the JWK Set URI based on a request parameter, free-form tenant ID, or untrusted header.
- When supporting multiple issuers, use an allowlist of approved issuers/JWKs and bind them together.
- Account for network errors, timeouts, caching, and key rotation so permissions are never granted when keys cannot be verified.

## 6. Key source #3: static RSA public key

Not every system provides discovery or a JWK Set endpoint. If the API is provisioned with a trusted **RSA public key**, it can be used directly to verify JWS tokens.

### 6.1. Spring Boot public-key-location configuration

For example, place the PEM-formatted public key at **src/main/resources/keys/access-token-pub.pem**, then:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          public-key-location: classpath:keys/access-token-pub.pem
          audiences:
            - orders-api
~~~

This is an example of a **key source**. Depending on the Boot version and configuration, ensure the issuer and required validators are actually applied. If the API needs to check a specific `iss`, you can declare a custom decoder as shown below to consolidate all conditions in one place.

The public key can live on the classpath or in another managed configuration; it is **not the issuer's private key**. Never store the private signing key in a Resource Server just to verify RSA signatures.

### 6.2. NimbusJwtDecoder.withPublicKey

Suppose the application has loaded the trusted public key into an **RSAPublicKey** object:

~~~java
import java.security.interfaces.RSAPublicKey;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class StaticRsaDecoderConfig {

    private static final String ISSUER =
        "https://login.example.test/realms/demo";

    @Bean
    JwtDecoder jwtDecoder(RSAPublicKey trustedPublicKey) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withPublicKey(trustedPublicKey)
            .build();

        decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(ISSUER));

        return decoder;
    }
}
~~~

The **trustedPublicKey** bean is a dependency that must be configured to load from PEM or a controlled key management source. The snippet shows how to use the decoder when an **RSAPublicKey is already available**, rather than a standalone runnable app. Add an audience validator as in section 8 if the API only accepts tokens meant for it.

**When is it suitable?** Small internal services where keys are tightly provisioned and managed, change infrequently, or systems with a secure key-update distribution mechanism.

**Main limitation:** a static public key **does not inherently support multiple simultaneous keys for rotation** like a JWK Set does. When the Authorization Server rotates its signing key, the Resource Server must be updated via a rollout process, or new tokens may fail with 401. For frequent rotation requirements, a JWK Set is a better fit.

### 6.3. Algorithm must match the key source

`withPublicKey` accepts an **RSAPublicKey**. It is not a generic builder for passing arbitrary EC, EdDSA, or symmetric secret keys. If the issuer uses another algorithm, configure a decoder/JWK matching the algorithm and application policy rather than attempting arbitrary key conversions.

## 7. Key source #4: shared secret for HMAC

For JWS using an HMAC algorithm such as **HS256**, both the issuer and the verifier share a **secret key**. Spring Security can verify tokens using `NimbusJwtDecoder.withSecretKey`.

Important security differences compared to RSA:

| Asymmetric RSA / ECDSA | Symmetric HMAC |
| --- | --- |
| Authorization Server signs with a private key. | Authorization Server computes a MAC with a shared secret. |
| Resource Server verifies with a public key and cannot create signatures from it. | Resource Server holds the shared secret; anyone holding the secret can create a valid MAC. |
| A public JWK Set can be shared publicly when it contains only public parameters. | The secret must be kept strictly confidential; **never** publish it in a public JWK Set. |
| Well suited when many Resource Servers only need to verify. | Requires extra caution when sharing the secret across multiple services. |

### 7.1. withSecretKey example

Java example using a Base64-encoded secret loaded from an environment variable, intended for trusted environments controlled by the organization:

~~~java
import java.util.Base64;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class HmacDecoderConfig {

    private static final String ISSUER =
        "https://login.example.test/realms/demo";

    @Bean
    SecretKey jwtSharedSecret() {
        String base64Secret = System.getenv("JWT_HMAC_SECRET_BASE64");
        if (base64Secret == null || base64Secret.isBlank()) {
            throw new IllegalStateException("Missing JWT HMAC secret");
        }

        byte[] keyBytes = Base64.getDecoder().decode(base64Secret);
        if (keyBytes.length < 32) {
            throw new IllegalStateException("HS256 key must be at least 256 bits");
        }

        return new SecretKeySpec(keyBytes, "HmacSHA256");
    }

    @Bean
    JwtDecoder jwtDecoder(SecretKey jwtSharedSecret) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withSecretKey(jwtSharedSecret)
            .macAlgorithm(MacAlgorithm.HS256)
            .build();

        decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(ISSUER));

        return decoder;
    }
}
~~~

This is an **alternative for HMAC-signed JWTs**; do not declare it alongside an RSA/JWKS JWT decoder bean in the same filter chain without an explicit routing design. The snippet also needs an audience validator (section 8) to bind tokens to the API.

The secret length for HS256 must satisfy standards and security policy; for example, checking for at least 32 bytes. In real systems, prefer a secret manager/KMS, least-privilege read access to secrets, a key rotation mechanism, and never put secrets in repositories, logs, error reports, or public test fixtures. Base64 **is only an encoding**, not a secret protection mechanism.

**Do not** pick HS256 on your own if the Authorization Server signs with RS256. The Resource Server must have an exact agreement on the token profile and algorithm; never switch to HMAC just because a token failed RSA verification.

## 8. Verifying the signature alone is not enough: issuer, audience, and lifetime

A reliable decoder requires two layers:

1. **Cryptographic check:** the signature/MAC matches an accepted key and an allowed algorithm.
2. **Semantic JWT checks:** issuer, audience, timestamps, token profile, and API-specific constraints.

### 8.1. Key claims to watch

| Claim/header | What to check? | Notes |
| --- | --- | --- |
| **iss** | Matches a trusted issuer. | Never treat an unverified issuer as an automatic allowlist entry. |
| **aud** | Contains the current Resource Server, e.g., **orders-api**. | **aud** can be a single string or an array of strings per RFC 7519. |
| **exp** | Token has not expired. | NumericDate in seconds since Unix epoch; a small clock skew may apply. |
| **nbf** | Token has reached its not-before time. | Pay attention to system clock synchronization. |
| **iat** | Issued-at timestamp, used when required by profile/policy. | Do not treat iat as the expiration time. |
| **typ** (JOSE header) | JWT type matching the profile if required. | **at+jwt** may be required under RFC 9068; it is not a payload claim. |
| **scope/scp** | Contains the required permissions after valid authentication. | API permissions are an authorization step; they do not replace audience checks. |

Spring Security JWT Resource Server usually includes default validators for timestamps and issuer when configured with an issuer. **Audience must be configured explicitly** according to API requirements. Building a decoder manually with a builder can bypass Boot's auto-configuration logic, so declare the full validator set explicitly.

### 8.2. Complete decoder example with issuer + audience

Bean example using a direct JWK Set URI while restricting to RS256 and checking issuer/audience:

~~~java
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
public class OrdersJwtDecoderConfig {

    private static final String ISSUER =
        "https://login.example.test/realms/demo";
    private static final String JWKS =
        "https://login.example.test/realms/demo/protocol/openid-connect/certs";
    private static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token audience is not accepted",
                    null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audienceValidator));

        return decoder;
    }
}
~~~

In this example:

- **withJwkSetUri(JWKS):** fetches public keys from the trusted endpoint.
- **jwsAlgorithm(RS256):** accepts only the agreed signature algorithm.
- **createDefaultWithIssuer(ISSUER):** applies the default issuer and timestamp checks.
- **audienceValidator:** requires the token to be intended for this API.

If the application also requires a specific token type or tenant, add clearly defined validators/policies. The **aud** field does not replace authorization based on scopes, roles, and record-level permissions.

**Important:** calling `decoder.setJwtValidator(...)` can replace previously registered validators with the new one. Do not set only an audience validator and accidentally drop issuer/time checks; combine them using `DelegatingOAuth2TokenValidator`.

### 8.3. A JwtDecoder bean can override auto-configuration

If you define your own `JwtDecoder` bean, Spring Boot generally yields decoder creation to that bean. Therefore:

- Do not assume that having `audiences` in `application.yml` guarantees the audience validator is applied to a custom decoder.
- If using a custom builder, ensure issuer/audience/clock and algorithm settings are all configured on the actual bean.
- Avoid having multiple competing `JwtDecoder` beans without an explicit bean-selection configuration.
- If there is no need for customization, Boot configuration via `issuer-uri`, `jwk-set-uri`, and `audiences` can be simpler and less error-prone.

## 9. Controlling trusted algorithms

According to Spring Security documentation for standard JWT configurations, NimbusJwtDecoder trusts **RS256** by default when no other algorithm is configured. This can be changed to match the issuer, for example RS512:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri: https://login.example.test/oauth2/jwks
          jws-algorithms:
            - RS512
~~~

If using the Java builder:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri("https://login.example.test/oauth2/jwks")
    .jwsAlgorithm(SignatureAlgorithm.RS512)
    .build();
~~~

Each snippet illustrates only the **algorithm policy**; issuer/audience checks via validators are still required. When issuer tokens use ES256/EC keys or other algorithms, the key and algorithm configuration must match. Never rely solely on the **alg** field sent in the token to automatically accept arbitrary algorithms.

**Algorithm confusion** is a class of vulnerabilities where a verifier trusts the wrong key type/algorithm, causing signature checks to cross security boundaries incorrectly. Mitigate this by **pinning the trusted key source, the allowed algorithm list, and the token profile**, never falling back automatically from asymmetric verification to HMAC or accepting `alg: none`.

## 10. Caching, key rotation, and issuer availability

### 10.1. Why does a JWK Set often contain multiple public keys?

An Authorization Server cannot keep the same signing key forever. During rotation:

~~~text
Phase A: JWKS has key-1; issuer signs JWTs with key-1
Phase B: JWKS publishes key-1 and key-2
Phase C: issuer starts signing new JWTs with key-2
Phase D: JWTs signed with key-1 expire
Phase E: JWKS removes key-1 as scheduled
~~~

Thanks to **kid** and multiple public keys in the JWKS, the Resource Server can verify both still-valid older JWTs and newly issued JWTs without redeploying keys to every API.

However, rotation also depends on **token lifetime, caching, key publication timing, and JWK Set refetch behavior**. Do not remove an old key too early while valid tokens signed with it are still active, unless an incident requires immediate revocation with an appropriate strategy.

### 10.2. Decoder caching

Nimbus/Spring Security caches the JWK Set to avoid a network request for every Bearer token. Spring Security documentation for some versions describes an in-memory JWK Set cache of roughly **5 minutes** by default; actual duration and behavior depend on the version, cache provider, and configuration.

If you need Spring-level cache control:

~~~java
import org.springframework.cache.CacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Bean
JwtDecoder jwtDecoder(CacheManager cacheManager) {
    return NimbusJwtDecoder
        .withJwkSetUri("https://login.example.test/oauth2/jwks")
        .cache(cacheManager.getCache("jwks"))
        .build();
}
~~~

The example above only shows **how to supply a cache**; it does not yet include issuer/audience validators. When configuring a custom cache, ensure the cache exists, has an appropriate TTL/eviction strategy, and is not shared indiscriminately across different JWK Set URIs. When using a cache provider, add the corresponding dependency and configuration.

**Do not** arbitrarily set cache duration to 0: that can make every request depend on the network/IdP and overload the JWKS endpoint. Nor should you cache for so long that key rotation is not picked up in time. Choose based on rotation cadence, SLA, and Access Token lifetime.

### 10.3. What if the JWKS endpoint is unavailable?

Distinguish these cases:

- When the decoder **already has the cached public key** for the token being checked, it can continue verifying per cache policy.
- When encountering a **new kid not yet cached**, the decoder may need to refetch the JWK Set. If no trusted key can be retrieved, the token must not be accepted.
- If discovery is unreachable at startup, the application may fail depending on how the decoder is built; configuring the JWK URI directly can reduce startup discovery dependence, **but does not eliminate network dependence when keys must be fetched**.
- When an issuer performs an emergency key revocation/rotation, nodes with different caches may refresh at different times; have an operational plan and monitoring in place.

Safe rule: **never switch to skipping signature verification when the JWKS experiences an outage**. Nor should you allow fetching keys from arbitrary hosts just to “quickly fix 401 errors”.

## 11. Routing multiple issuers and multiple tenants

A Resource Server sometimes serves multiple tenants, each with its own Authorization Server or issuer URI. In that case, a single decoder with one issuer is insufficient.

You can use an appropriate resolver mechanism, such as **JwtIssuerAuthenticationManagerResolver** in Spring Security Servlet, to select an AuthenticationManager based on an **allowlisted** issuer.

Concept:

~~~text
Request carrying Bearer JWT
         |
         v
Read initial iss claim only to SELECT branch
         |
         v
Is issuer in allowlist?
    |               |
   No              Yes
    |               |
   401        Select decoder/keys
                     |
                     v
            Verify JWT signature
            Re-check iss
            Check API audience
            Check expiration/scope
                     |
                     v
                Allow / reject
~~~

**Reading the issuer from an unverified token is strictly a routing step, not an authorization step.** The resolver must restrict trusted issuers from configuration/managed storage; never dynamically create decoders or fetch metadata/JWKs from arbitrary issuer URLs supplied by callers. If a shared issuer serves multiple tenants, separate validators may be needed for tenant, resource, and token profile.

When an API accepts multiple issuers, custom claims such as `roles`, `tenant_id`, or `permissions` can carry different meanings. Never merge permissions across issuers without an explicit mapping contract and security policy.

## 12. Wiring the decoder into SecurityFilterChain

A basic Resource Server configuration in **Spring Security 6.x**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Here, the decoder created by Boot from JWT properties or a custom `JwtDecoder` bean is plugged into the Resource Server flow. When a request has no token or the token is rejected during authentication, the API typically returns **401 Unauthorized**. A valid token lacking `SCOPE_orders.read` typically receives **403 Forbidden** when calling the corresponding GET endpoint.

Notes:

- **scope → authority:** Spring Security usually maps the `scope` or `scp` claim to authorities prefixed with **SCOPE_**. If the issuer emits custom roles, configure an explicit converter or authorization rule.
- **STATELESS:** requests are authenticated via Bearer tokens rather than HTTP sessions.
- **CSRF disabled:** in this example, this is suitable only for pure Bearer-header APIs. If the same application also serves OIDC Login with browser session cookies, apply appropriate CSRF protection per security filter chain.
- **Resource authorization:** a valid scope does not mean the user can read every order; the API may still need to check tenant, owner, and record-level permissions.

Never send an OIDC Login **ID Token** as a Bearer Access Token to an API. An ID Token typically has the **OIDC client ID as its audience**, whereas an Access Token must target the Resource Server.

## 13. Testing NimbusJwtDecoder across key sources

### 13.1. Distinguishing mock tests from real verification tests

**spring-security-test** supports `jwt()` in MockMvc:

~~~java
mockMvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

This is a good way to test **authorization rules**, but it places a simulated Authentication into the SecurityContext and **does not invoke NimbusJwtDecoder to verify a signature**. Even if you put the wrong `aud` into the simulated principal, the test can still pass because it bypasses the decoder.

To confirm **signature, issuer, audience, and expiration**, test `JwtDecoder.decode(token)` using JWTs **actually signed with test keys**, or run integration tests through the Bearer filter with a JWK Set fixture.

### 13.2. Unit test example with a test-only RSA key pair

The following JUnit 5 example generates an RSA key pair inside the test, signs JWTs with the test private key, and verifies them via `NimbusJwtDecoder.withPublicKey`. This is a standalone decoder test without hitting an external Authorization Server:

~~~java
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Date;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class NimbusDecoderTest {

    private static final String ISSUER =
        "https://login.example.test/realms/demo";

    private KeyPair trustedPair;
    private NimbusJwtDecoder decoder;

    @BeforeEach
    void setUp() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        trustedPair = generator.generateKeyPair();

        decoder = NimbusJwtDecoder
            .withPublicKey((RSAPublicKey) trustedPair.getPublic())
            .build();

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token", "Invalid audience", null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER), audience));
    }

    private static String signed(
            KeyPair signer, String issuer, String audience,
            Instant expiration) throws Exception {
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer(issuer)
            .subject("user-123")
            .audience(audience)
            .issueTime(Date.from(Instant.now().minusSeconds(60)))
            .expirationTime(Date.from(expiration))
            .claim("scope", "orders.read")
            .build();

        SignedJWT jwt = new SignedJWT(
            new JWSHeader(JWSAlgorithm.RS256), claims);
        jwt.sign(new RSASSASigner(
            (RSAPrivateKey) signer.getPrivate()));
        return jwt.serialize();
    }

    @Test
    void validTokenIsAccepted() throws Exception {
        String token = signed(
            trustedPair, ISSUER, "orders-api",
            Instant.now().plusSeconds(600));
        assertEquals("user-123", decoder.decode(token).getSubject());
    }

    @Test
    void wrongAudienceIsRejected() throws Exception {
        String token = signed(
            trustedPair, ISSUER, "billing-api",
            Instant.now().plusSeconds(600));
        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void wrongIssuerIsRejected() throws Exception {
        String token = signed(
            trustedPair, "https://untrusted.example.test", "orders-api",
            Instant.now().plusSeconds(600));
        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void expiredTokenIsRejected() throws Exception {
        String token = signed(
            trustedPair, ISSUER, "orders-api",
            Instant.now().minusSeconds(3600));
        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void unknownKeyIsRejected() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair untrustedPair = generator.generateKeyPair();
        String token = signed(
            untrustedPair, ISSUER, "orders-api",
            Instant.now().plusSeconds(600));
        assertThrows(JwtException.class, () -> decoder.decode(token));
    }
}
~~~

In this test:

- **validTokenIsAccepted** shows that the trusted public key verifies the signature of a token signed with the corresponding private key and that claims pass the validators.
- **wrongAudienceIsRejected** proves the audience validator is active.
- **wrongIssuerIsRejected** proves the decoder does not accept a different issuer.
- **expiredTokenIsRejected** uses a token expired well beyond typical small clock skew.
- **unknownKeyIsRejected** proves a mismatched public key causes signature rejection.

This test **does not** prove that network discovery/JWKS loading or key rotation works. To test a JWK Set, spin up a local test HTTP endpoint returning a JWK Set containing the fixture public keys, then run a **withJwkSetUri** decoder or test the server through the Bearer filter.

### 13.3. Dedicated tests when using a JWK Set URI

A useful integration test suite should cover:

| Scenario | Expected outcome |
| --- | --- |
| JWT signed by key-1 present in JWKS | Accepted by decoder if claims are valid. |
| JWT with `kid` absent from JWKS | Rejected when no matching key is found. |
| JWT signed by a private key not matching JWKS | Rejected due to signature verification failure. |
| JWKS contains key-1 and key-2 during rotation | Tokens from both keys are handled per policy. |
| JWT algorithm not in the allowed list | Rejected rather than loosening algorithm checks. |
| JWK endpoint unreachable when an uncached key is needed | Permissions are never granted without verification. |
| JWT has audience for another API | 401 after audience validator rejects it. |
| Valid JWT but missing scope | 403 at endpoints requiring that scope. |

Use **test-only** key pairs/issuers/JWK servers—never production private keys or real user Access Tokens. Testing with a JWKS fixture verifies key fetching and selection; a `withPublicKey` unit test only verifies decoder logic against a single key.

## 14. Observability and error handling

### 14.1. What error does an invalid JWT return?

A request without a Bearer token or carrying an unauthenticatable token typically receives **401 Unauthorized** from the Resource Server:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

A token with a valid signature/claims that lacks permission for the endpoint typically receives **403 Forbidden**. The `WWW-Authenticate` header may include standard error codes depending on context. Never return raw JWTs, key material, internal exception messages, or stack traces in response bodies or headers sent to clients.

### 14.2. Symptoms and troubleshooting paths

| Symptom | Possible cause | What to inspect |
| --- | --- | --- |
| Startup failure when using issuer | Metadata endpoint unreachable, wrong issuer URI, TLS or discovery mismatch. | Configured issuer, metadata/JWKS URL, connectivity/TLS. |
| 401 for new tokens after rotation | JWK Set/cache lacks the new signing key, mismatched `kid`. | Does JWKS publish the new public key? cache/TTL/refresh? |
| 401 despite valid signature | Wrong `iss`, `aud`, `exp`, `nbf`, token profile, or algorithm. | Which API was the token issued for, are validators configured properly? |
| HS256 token rejected by RSA decoder | Algorithm and key type mismatch. | Token issuance contract, `withSecretKey` vs. `withPublicKey`/JWKS. |
| Token for another API accepted | Missing or bypassed audience validator. | Which decoder is actually active; does a custom bean override auto-config? |
| 403 after JWT passes decoder | Missing authority/scope or record-level permission. | `scope/scp` claim, JwtAuthenticationConverter, endpoint policy. |
| Intermittent failures across nodes | Different JWKS caches/rotation/config, clock drift, inconsistent issuers. | Per-node config, key cache, clock skew, deployment timing. |

When debugging, **do not paste real tokens into public decoding tools** and do not put raw Authorization headers into logs, URLs, tickets, or error messages. Use a correlation/request ID, normalized error type, `kid`, or controlled metadata to identify the root cause without leaking credentials.

### 14.3. Pitfalls to avoid

1. **“withJwkSetUri already checks the issuer.”** It only selects the key source; ensure an issuer validator is actually active.
2. **“A validly signed token can call any API under the same issuer.”** You must verify the Resource Server's own **audience** and specific permissions.
3. **“JwtDecoders.fromIssuerLocation and NimbusJwtDecoder.withIssuerLocation have identical defaults.”** When using the builder directly, explicitly verify the validator set; factories and Boot auto-config may apply additional defaults.
4. **“A JWK Set must include the private key.”** A public JWK Set for asymmetric signature verification should contain **public keys** only.
5. **“kid is a secret or proof of trust.”** kid is merely a key-selection label; trust comes from the **configured key source** and signature verification.
6. **“Keeping a single static public key supports rotation automatically.”** With a static key, changing the signing key usually requires updating the API.
7. **“Having an HMAC secret lets the API only verify.”** Any party with the shared secret can compute a valid MAC; protect the secret like a signing credential.
8. **“Skip verification during a JWKS outage to avoid downtime.”** Never grant permissions when a token cannot be verified.
9. **“Base64url decoding is JWT verification.”** Reading the payload is insufficient; verify the key, signature, issuer, audience, lifetime, and policy.
10. **“A valid JWT means permission to read any data.”** Authorization by scope, tenant, owner, and policy is a separate step.

## 15. Recommendations for choosing a key source in projects

| Situation | Usually appropriate option |
| --- | --- |
| Standard IdP/OIDC Provider with issuer metadata and JWKS | **issuer-uri**; if customization is needed, use **JwtDecoders.fromIssuerLocation** or **NimbusJwtDecoder.withIssuerLocation** with validators. |
| API has a stable JWK Set URI and wants to reduce startup discovery dependence | **issuer-uri + jwk-set-uri** or **withJwkSetUri** with issuer/audience validators. |
| Issuer provides only a static RSA public key | **public-key-location** or **withPublicKey**, with a key-update rollout plan for rotation. |
| Issuer uses HS256 and both sides share a trust boundary | **withSecretKey**, sufficiently strong secret stored via a secret manager, never distributed indiscriminately. |
| Opaque token where issuer requires introspection | **oauth2ResourceServer().opaqueToken()**, do not use NimbusJwtDecoder for that flow. |
| Multiple issuers/tenants | Resolver with an **issuer allowlist**, dedicated decoder/validators per trusted source. |

Practical implementation workflow:

1. **Define the token profile**: JWT/JWS or opaque, issuer, audience, algorithm, lifetime, scopes, and token type.
2. **Define the trusted key source**: issuer metadata, JWK Set URI, RSA public key, or shared secret; use the matching mechanism.
3. **Configure decoder + validators**: signature, issuer, audience, exp/nbf, and additional constraints.
4. **Configure authorization**: endpoints, HTTP methods, scopes/authorities, and business permissions.
5. **Write negative tests**: invalid signature, key, issuer, audience, expiration, algorithm, missing scope, and key-source failures.
6. **Prepare operations**: key rotation, caching, timeouts, TLS, secret management, and token-safe logging.

**Takeaway:** **NimbusJwtDecoder** is only trustworthy when it retrieves keys from an **approved source** and applies the right **validators for the API**. Choosing the key source answers “does this signature belong to an issuer we trust?”; checking claims and authorization then answers “was this token issued for this API and the current operation?”.

## References

- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — NimbusJwtDecoder Java API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html).
- [Spring Security — OAuth 2.0 Resource Server Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html).
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515).
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517).
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519).
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
