# Distributing Verification Keys and Keeping Asymmetric Signing Keys Out of Resource Servers

In an OAuth 2.0 Resource Server using JWTs, the Authorization Server (AS) signs access tokens with a **private signing key**. The Resource Server only needs the **public verification key** to verify signatures and claims. Properly distributing public keys lets multiple APIs verify tokens independently without sharing a secret capable of signing tokens.

The critical principle is: **private keys belong to the issuer and the token-signing boundary; Resource Servers receive only public keys through a trusted channel such as JWKS/metadata discovery**. If a private signing key is placed inside a Resource Server, a compromised API could be abused to forge JWTs impersonating the issuer, expanding the blast radius from one service to the entire system trusting that key.

This lesson covers distributing public verification keys via JSON Web Key Sets (JWKS), configuring Spring Security Servlet/WebFlux, managing `kid` and algorithms, safe key rotation, handling key compromise, JWKS caching, multi-issuer setups, testing, and operations.

## 1. Trust Boundary Between Signing and Verification

With asymmetric signatures such as RS256 or ES256, a key pair has two roles:

- Private key signs JWTs. Only the AS or an authorized signing service may use it.
- Public key verifies signatures. It can be distributed to Resource Servers that trust the issuer.

~~~text
                  TRUST BOUNDARY: AUTHORIZATION SERVER
                  ------------------------------------
                  Private signing key (KMS / HSM)
                             |
                             | sign JWT (RS256 / ES256)
                             v
Client ---- access token JWT ----> API Gateway / Resource Server
                                           |
                                           | fetch public keys
                                           v
                                   HTTPS JWKS endpoint
                                           |
                                           v
                                  Public verification key
                                           |
                                           v
                                  Verify signature + claims
~~~

A Resource Server does not need—and must not hold—a private signing key to verify tokens. If an API holds a private key, any file-read, environment-variable, heap-dump, container-image, or secret-store vulnerability can turn that API into a rogue issuer.

### 1.1. Public Keys Are Not Secrets, Yet Their Integrity Is Critical

Public keys can be published openly. However, the Resource Server must be certain that the public key truly belongs to the configured issuer. If an attacker replaces the JWKS with a key they control, the Resource Server could verify forged JWTs using the attacker's public key.

Therefore, protect:

- Authenticity of the issuer URI and JWKS URI.
- TLS and certificates of the metadata/JWKS endpoints.
- DNS, reverse proxies, CDNs, and deployment pipelines serving JWKS.
- Resource Server configuration, preventing users from arbitrarily choosing issuer/JWKS URLs.
- Access control and auditing for key publish/rotate operations.

You do not need to keep public keys secret, but you must protect the distribution path to prevent unauthorized key substitution.

### 1.2. Why Not Share Private Keys Across All Resource Servers?

If every service holds the private signing key:

- Any compromised service can sign forged tokens.
- It is hard to determine which service issued a given token.
- Rotation must distribute a secret to many places.
- Secrets can appear in images, backups, CI logs, or crash dumps.
- An access control flaw in one Resource Server can compromise the entire trust domain.

With asymmetric signing, the AS holds the private key; Resource Servers receive public keys. When multiple issuers or signing domains are needed, use separate key pairs and issuers per trust domain.

## 2. Comparing Asymmetric Signing and Symmetric Signing

| Algorithm / Model | Signing | Verification | Distribution Consequence |
|---|---|---|---|
| RS256 (RSA + SHA-256) | Private RSA key | Public RSA key | Resource Server only needs public key |
| PS256 (RSA-PSS + SHA-256) | Private RSA key | Public RSA key | Resource Server only needs public key |
| ES256 (ECDSA P-256 + SHA-256) | Private EC key | Public EC key | Resource Server only needs public key |
| HS256 (HMAC + SHA-256) | Shared secret | Same shared secret | Every verifier can also generate signatures |

With HS256, the same secret is used for signing and verification. If multiple Resource Servers hold that secret, compromising one Resource Server lets an attacker sign tokens accepted by all other Resource Servers. This is why asymmetric signing is generally better suited when there are multiple independent services.

Do not conclude HS256 is always wrong. It can fit a small trust boundary where signer and verifier are governed as one system. Yet if you want Resource Servers to only have verification capability, asymmetric signing creates a cleaner privilege boundary.

## 3. What Is JWKS?

JSON Web Key (JWK) is a format representing a cryptographic key. A JSON Web Key Set (JWKS) is a JSON object with a `keys` property containing an array of JWKs. JWKS is commonly published at an HTTPS endpoint indicated by issuer metadata.

Example JWKS containing only a public RSA key:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "key_ops": ["verify"],
      "alg": "RS256",
      "kid": "rsa-signing-2026-01",
      "n": "sXch...public-modulus...",
      "e": "AQAB"
    }
  ]
}
~~~

Common fields:

| Field | Meaning |
|---|---|
| `kty` | Key type, e.g., `RSA` or `EC` |
| `use` | Intended use, typically `sig` for signing/verification |
| `key_ops` | Allowed operations; public verifiers usually have `verify` |
| `alg` | Intended algorithm, e.g., `RS256` |
| `kid` | Key ID to match the key against the JWT header |
| `n`, `e` | RSA public modulus and exponent |
| `crv`, `x`, `y` | EC curve and public point coordinates |

Private RSA JWKs can contain fields like `d`, `p`, `q`, `dp`, `dq`, `qi`; private EC JWKs can contain `d`; symmetric JWKs can contain `k`. **Never publish private members on a public JWKS endpoint.**

### 3.1. JWT Header Uses `kid` to Select a Public Key

A JWT may have a protected header:

~~~json
{
  "alg": "RS256",
  "kid": "rsa-signing-2026-01",
  "typ": "at+jwt"
}
~~~

The Resource Server reads `kid` to find the corresponding JWK in the configured key set. `kid` is an identifier for selecting a key, not proof that the key is trustworthy. Trust still comes from the configured issuer/JWKS endpoint verified via TLS/metadata.

`kid` should be unique within a JWKS at any point in time and stable throughout the key's lifecycle. Never reuse the same `kid` for different key material, as caches and verifiers may retain the old version.

### 3.2. JWKS Can Contain Multiple Public Keys

During rotation, JWKS typically contains both the old key and the new key:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "key_ops": ["verify"],
      "alg": "RS256",
      "kid": "signing-old",
      "n": "old-public-modulus",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "use": "sig",
      "key_ops": ["verify"],
      "alg": "RS256",
      "kid": "signing-new",
      "n": "new-public-modulus",
      "e": "AQAB"
    }
  ]
}
~~~

The issuer can begin signing new tokens with `signing-new`, while Resource Servers continue verifying older tokens signed with `signing-old`.

### 3.3. Never Put Private Keys in Public JWKS

The following is wrong for a public JWKS:

~~~json
{
  "kty": "RSA",
  "kid": "do-not-publish",
  "n": "public-modulus",
  "e": "AQAB",
  "d": "PRIVATE-EXPONENT",
  "p": "PRIVATE-PRIME-P",
  "q": "PRIVATE-PRIME-Q"
}
~~~

If private members are published, treat the signing key as compromised: stop using the key, generate a new key pair, rotate, assess tokens signed during exposure, and execute incident response. Simply removing private fields from the response is insufficient if the private key could have been accessed without authorization.

## 4. Key Distribution via Issuer Metadata and JWKS

A Resource Server typically needs to know the issuer URI. From issuer metadata, it locates `jwks_uri` and fetches the key set.

With OpenID Connect Discovery, metadata is typically published at:

~~~text
https://id.example.com/.well-known/openid-configuration
~~~

Metadata may contain:

~~~json
{
  "issuer": "https://id.example.com",
  "jwks_uri": "https://id.example.com/oauth2/jwks",
  "authorization_endpoint": "https://id.example.com/oauth2/authorize",
  "token_endpoint": "https://id.example.com/oauth2/token"
}
~~~

With OAuth 2.0 Authorization Server Metadata, RFC 8414 also defines metadata endpoints and the `jwks_uri` property. For OpenID Connect, discovery metadata is defined in the OIDC Discovery specification.

The Resource Server does not fetch private keys or client secrets from issuer metadata. `jwks_uri` is solely the location to download public verification keys.

### 4.1. Discovery and Token Verification Flow

~~~text
Resource Server startup / first request
        |
        | configured issuer URI
        v
Issuer metadata endpoint
        |
        | issuer + jwks_uri
        v
JWKS endpoint
        |
        | public JWK set
        v
JWK cache / key selector
        |
        | JWT header kid + alg
        v
Signature verification
        |
        v
Validate iss / exp / nbf / audience / token profile
        |
        v
Authentication
~~~

### 4.2. HTTPS and Trusted Issuer Configuration

In production:

- Use HTTPS for metadata and JWKS endpoints.
- Configure issuer URIs from trusted deployment configuration.
- Validate the issuer claim (`iss`) in the JWT.
- Verify the API's audience.
- Never allow arbitrary request bodies/queries/headers to specify `jwk-set-uri`.
- Restrict outbound network traffic from the Resource Server to approved issuer/JWKS hosts.

Public keys are not secret, yet an attacker can tamper with key distribution to forge tokens. TLS certificate validation, issuer pinning/configuration, and network egress policies are part of the trust model.

### 4.3. Do Not Trust Self-Declared `jku`/`x5u` in Tokens

A JWT header can contain `jku` or `x5u` referencing where to fetch keys/certificates. A Resource Server should not automatically fetch arbitrary URLs from a token header. Doing so can cause SSRF or let an attacker point to a key set they control.

Spring Resource Server should use configured `issuer-uri`/`jwk-set-uri` and a JWK source bound to a trusted issuer. Never build a custom decoder that reads URLs from JWT headers and downloads keys from them unless there is a specialized protocol, allowlist, and explicit threat model.

## 5. Configuring Spring Security Resource Server

Spring Security supports JWT verification using public keys from JWKS. The application only needs to configure an issuer or JWK Set URI; it never supplies a private signing key.

### 5.1. Spring Boot Configuration Using `issuer-uri`

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com
~~~

With `issuer-uri`, Spring Security discovers issuer metadata and retrieves the JWKS URI. The decoder verifies signatures using the public key and checks the configured issuer.

Advantages:

- Configured by issuer rather than hard-coding the JWKS URL.
- Automatically retrieves `jwks_uri` from metadata.
- Uses issuer validation alongside default JWT validation.
- Key rotation is handled via JWKS refresh according to decoder/library behavior.

### 5.2. Configuring `jwk-set-uri` Directly

If the deployment already knows the JWKS endpoint:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri: https://id.example.com/oauth2/jwks
~~~

When configuring `jwk-set-uri` alone, ensure the application still validates the issuer claim per your trust policy. Both `issuer-uri` and `jwk-set-uri` can be configured to retain issuer validation without needing metadata discovery at startup:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com
          jwk-set-uri: https://id.example.com/oauth2/jwks
~~~

When combined, `issuer-uri` identifies the trusted issuer and `jwk-set-uri` explicitly specifies where to fetch public keys. This is useful when the metadata discovery endpoint should not be called on the startup path yet the Resource Server still needs issuer validation.

### 5.3. `SecurityFilterChain` for Servlet

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Boot creates/configures the decoder from properties. The security chain only enables JWT Resource Server support. Never inject a private key into `HttpSecurity` or `JwtDecoder`.

### 5.4. `SecurityWebFilterChain` for WebFlux

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/health").permitAll()
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Reactive Resource Server also uses public keys from issuer/JWKS. The difference is the reactive decoder and filter chain; the key distribution trust model remains identical to Servlet.

## 6. Restricting Algorithms and Validating Claims

A valid signature only proves the JWT was signed by a private key matching a trusted public key. It does not prove the token is intended for the current API or authorized for the operation.

The Resource Server must verify at least:

- Signature under an allowed algorithm.
- Issuer (`iss`) matching trust configuration.
- Timestamps (`exp`, `nbf`, and clock skew) valid.
- Audience (`aud`) containing the current API.
- Token type/profile matching the access token accepted by the API.
- Scopes/authorities sufficient for the endpoint.

### 6.1. Do Not Let the Token Choose Allowed Algorithms

JWT headers are sender-supplied data. The Resource Server must restrict accepted algorithms in configuration. Never write a verifier that reads `alg` from the header and accepts whatever algorithm the library supports.

For example, if the issuer only signs with RS256, configure the verifier to accept only RS256. Never accept `none`, never arbitrarily switch from asymmetric to HMAC, and never reuse the same key material across algorithms with different semantics.

`alg` in a JWK helps describe the key, yet the Resource Server's allowlist policy is the deciding boundary.

### 6.2. Configuring a Servlet Decoder with Explicit Algorithm and Audience

If building a decoder manually instead of relying on Boot auto-configuration:

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
class JwtDecoderConfiguration {

    @Bean
    JwtDecoder jwtDecoder() {
        String issuer = "https://id.example.com";
        String jwkSetUri = "https://id.example.com/oauth2/jwks";
        String audience = "orders-api";

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Required audience is missing",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime,
                audienceValidator));

        return decoder;
    }
}
~~~

`JwtValidators.createDefaultWithIssuer` provides default issuer and timestamp validation. The audience validator is composed via `DelegatingOAuth2TokenValidator`; never accidentally replace the default validators when adding a custom validator.

The example uses fixed URLs and audience for readability. In production, place them in trusted configuration, appropriate secret/config management, and deployment environment settings. While a JWKS URL is not a secret, it is still a trust-sensitive configuration.

### 6.3. Configuring a WebFlux Decoder

The reactive decoder enforces the same validation policy:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
class ReactiveJwtDecoderConfiguration {

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder() {
        String issuer = "https://id.example.com";
        String jwkSetUri = "https://id.example.com/oauth2/jwks";
        String audience = "orders-api";

        NimbusReactiveJwtDecoder decoder = NimbusReactiveJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Required audience is missing",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator));

        return decoder;
    }
}
~~~

The reactive decoder fetches JWKS through its configured reactive infrastructure. Never invoke blocking JWK fetches manually on the event loop.

### 6.4. `kid` Does Not Replace Signature Verification

`kid` is only a hint for selecting a JWK. An attacker can craft a JWT with an arbitrary `kid`. The Resource Server must look up the key in the trusted issuer's JWKS and verify the signature. If no matching key is found or the signature is invalid, the token must be rejected.

Never treat `kid` as proof that a token was issued for a specific user, tenant, or client.

## 7. Managing Private Signing Keys at the Issuer

Resource Servers do not need private keys, yet the issuer must protect signing keys carefully because private key compromise allows forging valid signatures.

### 7.1. KMS or HSM

Consider storing/generating private keys in:

- A Hardware Security Module (HSM).
- A Cloud Key Management Service (KMS) with an asymmetric signing API.
- An isolated signing service with dedicated policies and auditing.

The issuer application can send a payload/digest to a controlled signing operation instead of exporting private keys to files or environment variables. Signing capability must be restricted by workload identity, key alias, algorithm, and authorization policy.

### 7.2. Least Privilege

A signing workload should only have permission to sign with the specific key it needs. A Resource Server workload needs no Sign, Decrypt, or private-key export permissions. It only needs access to the public JWKS endpoint.

Role/identity separation:

| Workload | Required Permissions |
|---|---|
| Authorization Server / signing service | Sign with designated key |
| JWKS publisher | Publish corresponding public JWK |
| Resource Server | Fetch/read public JWKS |
| Operator | Rotate/disable keys with approval and audit |
| CI/CD | Deploy config, never read private signing keys |

### 7.3. Backup and Recovery

Private key backups must follow KMS/HSM policies. Never copy private keys into repositories or build artifacts for easy recovery. Disaster recovery procedures must prove the issuer can sign with restored keys and Resource Servers can pick up new public keys.

### 7.4. Never Store Private Keys in Resource Server Configuration

Examples to avoid:

~~~yaml
resource-server:
  signing:
    private-key: classpath:private-key.pem
~~~

~~~java
// The Resource Server does not need a private signing key to verify JWTs.
RSAPrivateKey privateKey = loadPrivateSigningKey();
~~~

If an application acts as both Authorization Server and Resource Server in the same process, the private key should only be injected into the signing component with explicit responsibility. Never put private keys into shared beans or configuration just because both roles live in the same deployment.

## 8. Safe Signing Key Rotation

Rotation must allow Resource Servers to obtain the new public key before the issuer begins signing tokens with the corresponding private key. Meanwhile, the old public key must remain published long enough to verify already-issued access tokens.

### 8.1. Standard Rotation Process

Suppose the issuer currently signs with key A and plans to switch to key B:

~~~text
Phase 1 — Generate
    Generate private/public key pair B in KMS/HSM
    Keep private B accessible only to signing workload

Phase 2 — Publish
    Add public B to JWKS alongside public A
    Keep signing with private A

Phase 3 — Propagate
    Wait for JWKS caches / CDN / Resource Servers to refresh
    Confirm key B is visible to verifiers

Phase 4 — Switch signer
    Sign newly issued JWTs with private B
    JWT header kid = B

Phase 5 — Overlap
    Continue publishing public A and public B
    Resource Servers verify old and new tokens

Phase 6 — Retire
    Wait until every token signed by A has expired
    Remove public A from JWKS
    Retire private A according to key-retention policy
~~~

### 8.2. Why Publish the New Key Before Signing?

Resource Servers may be caching the old JWKS. If the issuer begins signing tokens with B before Resource Servers know public B, verifiers will not find `kid=B` and valid requests may be rejected.

Some libraries refresh JWKS on encountering an unknown `kid`, yet you should not rely on that behavior as the sole rollout mechanism. It can be disrupted by caching, network outages, rate limiting, or library versions. Pre-publishing and waiting for propagation makes rollouts predictable.

### 8.3. How Long to Retain the Old Key?

Let:

- `T_last_old`: timestamp when the issuer signed the last token with key A.
- `L_max`: maximum access token lifetime signed with A.
- `S`: allowed clock skew/leeway.
- `P`: safety margin for propagation and operations.

Earliest time to remove public A from JWKS:

\[
T_{\text{remove A}} \ge T_{\text{last old}} + L_{\text{max}} + S + P
\]

If tokens have varying expiries, you can base this on the last token actually signed with A. Without exact tracking, use the issuer's maximum lifetime policy.

Never delete key A immediately after switching the signer to B. Still-valid tokens signed with A still require public A for verification.

### 8.4. Sample Timeline

| Time | JWKS | Signing Key | Outcome |
|---|---|---|---|
| Day 0 | A | A | Normal operation |
| Day 1 | A + B | A | Public B is pre-distributed |
| Day 1 after propagation | A + B | B | New tokens use B, old tokens use A |
| After max token lifetime + leeway | A + B | B | No valid A tokens remain per lifetime policy |
| After overlap window | B | B | A can be retired |

Exact timing depends on JWKS TTL, CDN caching, token lifetime, clock skew, and Resource Server refresh behavior.

### 8.5. Never Swap Key Material While Keeping the Same `kid`

If public key A is replaced with public key B while keeping the same `kid`, Resource Servers may hold key A in cache and not realize the key material changed. Assign a new `kid` for every key pair. Never reuse a `kid` while verifiers may still cache the old version.

## 9. Handling a Compromised Signing Key

Key compromise differs from routine rotation. If an attacker holds the private key, they can craft forged JWTs with any subject/scope/audience/expiry that Resource Servers will accept under their validators.

### 9.1. Emergency Response

When private signing key exposure is suspected:

1. Stop issuer/signing workloads using the compromised key.
2. Generate a new key pair in KMS/HSM or a clean signing boundary.
3. Publish the new public key and switch the signer to the new key.
4. Remove the compromised public key from JWKS per incident policy.
5. Invalidate/refresh JWKS caches at CDNs, gateways, and all Resource Servers.
6. Actively reject the compromised `kid` if immediate enforcement is needed while stale caches remain.
7. Revoke affected tokens/sessions/families per AS capabilities.
8. Investigate forged tokens created, logs, API usage, and accessed data.
9. Notify Resource Server owners and monitor propagation.

### 9.2. Removing a Public Key from JWKS Is Not Instantaneous

Resource Servers may have cached public key A. Even after the JWKS endpoint removes A, verifiers may keep using key A until their cache refreshes or is invalidated. CDNs/proxies may also serve stale JWKS responses.

Therefore emergency response must address:

- JWKS origin cache.
- CDN/reverse proxy cache.
- In-application Nimbus/JWK cache.
- Local caches on Resource Server instances.
- Offline nodes or nodes missing invalidation events.

### 9.3. Blocking a Compromised `kid`

During an incident, you can add a policy rejecting JWTs with the compromised `kid`. This is an extra defense layer while old keys remain cached. Example validator:

~~~java
import java.util.Set;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

final class DenyCompromisedKeyIds implements OAuth2TokenValidator<Jwt> {

    private final Set<String> deniedKids;

    DenyCompromisedKeyIds(Set<String> deniedKids) {
        this.deniedKids = Set.copyOf(deniedKids);
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        Object rawKid = jwt.getHeaders().get("kid");
        if (rawKid instanceof String kid && deniedKids.contains(kid)) {
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Signing key is no longer trusted",
                    null));
        }
        return OAuth2TokenValidatorResult.success();
    }
}
~~~

Combine this validator with existing issuer/time/audience validators. The denied `kid` list must be distributed through a trusted, audited control plane capable of fast updates. Do not use this validator as a substitute for removing the compromised key from JWKS and handling the incident.

### 9.4. When Attackers Have Already Signed Forged Tokens

Forged tokens signed with an exposed private key can carry an `exp` far in the future. As long as the compromised public key remains trusted, the forged token's signature remains valid. Waiting for normal access token expiry may be insufficient.

Consider:

- Denying the compromised `kid` across all Resource Servers.
- Revoking affected sessions/token families or accounts.
- Using a denylist or introspection for flows requiring immediate revocation.
- Auditing token issuance logs to detect tokens not actually issued by the AS.
- Assessing whether the attacker could have exfiltrated additional keys or credentials.

### 9.5. Do Not Retire a Private Key and Forget Old Public Keys and Tokens

Retiring a private key prevents signing new tokens with it; it does not make already-signed tokens disappear. The public key is still needed for older tokens until expiry, except in emergency compromise cases requiring rejection of all tokens signed by that key.

## 10. JWKS Caching and Behavior When the Endpoint Is Unavailable

Resource Servers typically cache JWKS to avoid downloading the key set on every request. JWKS caching differs from introspection caching:

- JWKS cache stores public key material for signature verification.
- Introspection cache stores status/claims for a specific token.

### 10.1. How JWKS Caching Affects Rotation

If a Resource Server holds a stale JWKS, it may:

- Not yet know the new key and reject tokens newly signed with it.
- Keep trusting the old key after the issuer has removed it from JWKS.

Therefore, TTL/cache headers and rotation procedures must be coordinated.

### 10.2. `Cache-Control`, `ETag`, and CDN

The JWKS endpoint can use HTTP caching headers such as `Cache-Control`, `ETag`, and `Last-Modified` to guide caches/proxies. Determine:

- Whether `max-age` aligns with the rotation SLA.
- Whether the CDN caches per exact endpoint/issuer.
- Whether emergency invalidation can be triggered during a compromise.
- Whether the Resource Server library honors HTTP caching headers as expected.
- Whether an unknown `kid` triggers a refresh in the running version.

Never assume all decoders/libraries share identical cache TTLs or refresh behavior. Check your specific version's documentation and verify behavior in integration tests.

### 10.3. Temporary JWKS Endpoint Outage

If a Resource Server has already cached the needed public key, some verifiers can continue verifying tokens with known keys while the cache remains valid. Tokens using an uncached new key may fail while the JWKS endpoint is down.

Never turn a JWKS fetch error into accepting all signatures or skipping signature verification. When a key is unknown and trusted keys cannot be fetched, failing closed is the safe behavior.

### 10.4. Stale Keys and Emergency Invalidation

During normal rotation, retain the old key during the JWKS overlap window. During key compromise, stale caches are a risk. Have a plan to:

- Purge CDN/reverse proxy caches.
- Force-refresh or invalidate JWK caches as supported by the library.
- Distribute a `kid` denylist.
- Restart/replace instances if that is a verified, controlled mechanism.
- Confirm all nodes have received the new policy.

Restarting is not a universal fix if a CDN still serves stale JWKS or restarted nodes immediately reload the same stale cached response.

## 11. Multiple Issuers and Multi-Tenancy

A Resource Server may trust multiple issuers. Each issuer has its own JWKS and its own validation policy.

### 11.1. Do Not Share One JWKS Cache Namespace Across All Issuers

A public key from issuer A must not verify a token from issuer B merely because the algorithm and `kid` match. `kid` is not guaranteed globally unique; it usually only has meaning within an issuer's key set.

Caches and decoders must be bound to their issuer:

~~~text
issuer A
    -> metadata A
    -> JWKS A
    -> decoder A
    -> issuer/audience policy A

issuer B
    -> metadata B
    -> JWKS B
    -> decoder B
    -> issuer/audience policy B
~~~

### 11.2. Issuer Allowlist

If an application selects an issuer based on the `iss` claim in the JWT, never automatically trust any URL the token provides. An attacker can send an issuer pointing to their own server, causing the Resource Server to fetch arbitrary metadata/JWKS (SSRF or trust injection).

Accept issuers only from a provisioned, controlled allowlist or tenant registry. Validate the issuer before creating a decoder or performing outbound fetches.

### 11.3. Spring Security Issuer Resolvers

Spring Security provides multi-issuer resolvers, such as `JwtIssuerAuthenticationManagerResolver` in the Servlet stack and `JwtIssuerReactiveAuthenticationManagerResolver` in the reactive stack. When using them, configure explicit trusted issuers or provide a resolver backed by a controlled registry.

Never build a resolver that extracts a URL from `iss` and fetches arbitrary endpoints without allowlist checks. Multi-tenant discovery must constrain hosts, schemes, issuer identity, tenant status, and cache capacity.

### 11.4. Tenant Onboarding and Offboarding

When adding a tenant:

- Provision the issuer URI and JWKS endpoint via an admin/control plane.
- Verify issuer metadata matches the registered tenant.
- Configure audience and scope policies.
- Bound the number of issuers/decoders/cache entries.

When offboarding a tenant:

- Stop accepting that issuer.
- Remove/disable the decoder mapping and cache namespace.
- Revoke tenant credentials/sessions per policy.
- Confirm no remaining routes or background processes trust that issuer.

## 12. Protecting the JWKS Endpoint and Signing Pipeline

A public JWKS endpoint normally requires no authentication because Resource Servers need to download public keys. That does not mean every key-related operation is public.

### 12.1. Separate Public Key Reads from Key Writes/Publishing

- Public JWKS endpoint: read-only access to the public JWK set.
- Signing API/KMS: callable only by signing workloads.
- Key management API: only operators/control planes may create, rotate, or disable keys.
- Deployment pipeline: publishes only approved public material.

Never use the same endpoint or credential to both read JWKS and upload private keys.

### 12.2. Publish JWKS Atomically

When updating JWKS, publish a complete and consistent document. Avoid letting the endpoint temporarily serve JSON missing keys, duplicate `kid`s, or partial key sets during deployment.

If using object storage/CDN, upload the new version first and switch the pointer/route atomically. Verify the live response after publishing before switching the signer.

### 12.3. Validate JWKS Contents Before Publishing

Pipelines can verify:

- JSON parses cleanly and has a `keys` array.
- Every key has `kty`, `kid`, and valid public parameters.
- No private parameters exist such as `d`, `p`, `q`, `dp`, `dq`, `qi`, or symmetric secret `k`.
- No duplicate `kid`s exist in the set.
- `use`/`key_ops` match verification.
- `alg` is in the allowlist.
- Key size/curve meets cryptographic policy.
- The public key matches the key pair used by the signing service.

Verify key pairs by signing a test payload in the pipeline and verifying it against the corresponding public JWK before publishing/switching.

### 12.4. Network Egress and SSRF

Resource Servers should only connect to configured metadata/JWKS endpoints. With multi-tenant dynamic discovery, the registry must control issuers and hosts; never feed user-controlled URLs into HTTP clients.

Enforce outbound network policies, DNS resolution policies, timeouts, and response size limits. A JWKS endpoint should only return small structured payloads; bounding response size reduces resource exhaustion risk.

## 13. Testing Key Distribution and Rotation

A test that only uses `mockJwt()` does not prove the JWKS endpoint, key selection, or signature verification works. Test at least one request with a real signed JWT and a decoder fetching public keys from a JWKS endpoint.

### 13.1. Testing with a Local JWKS Server

In integration tests:

1. Generate an RSA key pair A exclusively for tests.
2. Build JWKS JSON containing only public JWK A.
3. Start a local mock HTTP server at a fixed URI.
4. Configure `jwk-set-uri` pointing to the mock server.
5. Sign a JWT with private A and `kid=A`.
6. Send the Bearer token via `WebTestClient`/`MockMvc` and assert the endpoint accepts it.

A mock server keeps tests independent of the Internet or a real Authorization Server. Use dedicated test private keys, never production keys.

### 13.2. Testing Key Rotation

An integration scenario:

~~~text
JWKS version 1 = public A
Signer = private A
Token A -> Resource Server accepts

JWKS version 2 = public A + public B
Wait/force JWKS refresh as test setup requires
Signer switches to private B
Token B -> Resource Server accepts
Token A -> Resource Server still accepts

JWKS version 3 = public B only
After token A expires and cache refreshes:
Token B -> Resource Server accepts
Token A -> Resource Server rejects (or is expired)
~~~

Do not use arbitrary sleep durations to simulate caching. Where possible, configure controllable caches/test clocks or explicitly trigger JWKS refreshes via library-supported APIs. Otherwise, use short TTLs in tests and bounded waits.

### 13.3. Testing Tokens with a Non-Existent `kid`

Sign a token with key C while JWKS contains only A/B. The Resource Server must reject it because no matching trusted verification key exists. Never fall back to an arbitrary key or accept the token merely because `iss` is valid.

### 13.4. Testing Wrong Signature with Matching `kid`

Create a JWT with header `kid=A` yet signed with a different private key. JWKS contains public A. The decoder must reject the signature. This proves the system does not merely check for the existence of `kid`.

### 13.5. Testing Algorithm Policy

If the API accepts only RS256:

- RS256 token with valid key: verified.
- Token using a disallowed algorithm: rejected.
- `alg=none` token: rejected.
- Token attempting HMAC with public RSA material: rejected.

### 13.6. Testing Issuer and Audience Separately

Create JWTs with valid signatures yet:

- Issuer differs from the trusted issuer.
- Audience does not include the current API.
- Token is expired.
- `nbf` is in the future beyond allowed clock skew.

These tokens must be rejected even though the signature is cryptographically valid.

### 13.7. Testing That Private Material Never Appears in JWKS

Pipeline tests can parse the JWKS response and assert no private JWK members exist. For RSA, check no `d`, `p`, `q`, `dp`, `dq`, `qi`; for EC, no `d`; for octet/symmetric keys, no `k`.

## 14. Testing Key Distribution Failures

### 14.1. JWKS Endpoint Returns 5xx

Tests verify:

- Tokens using cached keys behave per decoder/cache policy.
- Tokens using a new unknown `kid` are not accepted if trusted public keys cannot be retrieved.
- Errors are logged/metered without leaking tokens.
- Requests do not hang indefinitely; HTTP timeouts are bounded.

### 14.2. Malformed JWKS Response

If JSON is invalid, keys miss public parameters, or duplicate `kid`s exist, the decoder must refuse to load the key set or fail verification for corresponding tokens. Publishing pipelines should catch this before documents reach production.

### 14.3. Key Compromise and Denylist

Test `DenyCompromisedKeyIds` with tokens carrying a blocked `kid` and tokens carrying a new `kid`. Ensure the denylist updates across all nodes and does not inadvertently block another issuer sharing the same `kid` in a different namespace.

### 14.4. Multi-Issuer Isolation

Create two test issuers A/B with the same `kid` but different key pairs. Token A must verify under decoder A; token B under decoder B. Never allow issuer A's token to verify using B's public key.

## 15. Observing and Operating Key Distribution

Key distribution is a runtime dependency of JWT verification. If the JWKS endpoint or cache fails, Resource Servers may reject valid new tokens or keep trusting old keys longer than intended.

### 15.1. Useful Metrics

You can track:

| Metric | Meaning |
|---|---|
| JWKS fetch count | Number of times Resource Servers fetch JWKS |
| JWKS fetch latency | Time to retrieve the key set |
| JWKS fetch errors | Timeouts, TLS failures, HTTP 4xx/5xx, malformed JSON |
| JWK cache hit/miss | Cache behavior per decoder/library |
| Unknown `kid` count | Tokens with key IDs absent from current JWKS |
| Signature validation failures | Invalid signatures or missing keys |
| Issuer/audience validation failures | Tokens in wrong trust context |
| Key rotation propagation time | Time from publishing public key until nodes confirm visibility |
| Compromised `kid` denials | Tokens rejected by emergency deny policy |

Metric names are suggestions. Labels must be bounded, such as issuer alias, environment, outcome, and resource-server name. Never put full JWTs, subjects, or token IDs into metrics.

### 15.2. Structured Logs

Helpful log events:

~~~text
event=jwks_fetch issuer=main outcome=success key_count=2
event=jwks_fetch issuer=main outcome=error reason=timeout
event=jwt_validation issuer=main outcome=invalid_signature
event=jwt_validation issuer=main outcome=unknown_kid
event=key_rotation issuer=main phase=public_key_published kid_alias=signing-next
event=key_rotation issuer=main phase=signer_switched kid_alias=signing-next
event=key_compromise issuer=main action=deny_kid kid_alias=signing-old
~~~

Never log raw tokens or private keys. `kid` may be logged if it is a non-secret identifier handled per log policy; if `kid` is considered sensitive internal data, use an alias.

### 15.3. Alerts Should Align with Impact

Useful alerts:

- JWKS endpoint unreachable beyond a threshold duration.
- JWKS response malformed or contains no usable keys.
- Spike in unknown `kid` outside a rotation schedule.
- Unusual spike in signature failures.
- Some nodes fail to see a new public key past the propagation deadline.
- Key approaching end of overlap while old tokens are still being issued.
- Compromise denylist not confirmed across all nodes.

Occasional signature failures can result from bad tokens or buggy clients; alerts should rely on rates, issuer/resource context, and patterns rather than single requests.

### 15.4. Runbook When Valid Tokens Suddenly Return 401

Check:

1. Which `kid` is in the JWT header?
2. Does the right issuer's JWKS endpoint contain that key?
3. Is the Resource Server using the right issuer/JWKS URI?
4. Is a CDN/proxy serving stale JWKS?
5. Is the decoder/JWK cache refreshing per current version and policy?
6. Is the token's algorithm in the allowlist?
7. Does the signature verify with the fetched public key?
8. Are issuer, audience, `exp`, and `nbf` valid?
9. Are multiple security chains/decoders routing requests to the wrong config?

Never resolve errors by disabling signature/issuer/audience validation or accepting arbitrary keys.

### 15.5. Runbook When Forged Tokens Are Still Accepted

Check:

1. Is the token's `kid` compromised or already retired?
2. Is the corresponding public key still in JWKS/cache?
3. Is the Resource Server trusting an unauthorizedly altered issuer/JWKS URI?
4. Is there a multi-issuer resolver allowing arbitrary issuers?
5. Is there a custom decoder trusting `jku`/`x5u` from JWT headers?
6. Is there a validator skipping `iss`, `aud`, `exp`, or the algorithm allowlist?
7. Has the compromised `kid` denylist been applied across all nodes?

## 16. Common Implementation Mistakes

### 16.1. Placing Private Keys in Resource Servers

Resource Servers only need public keys to verify. Private keys inside an API increase blast radius and enable forging tokens if the API is compromised.

### 16.2. Publishing Private Members in JWKS

Public JWKS must contain only public key parameters. Private RSA/EC/symmetric members must stay within the key management boundary.

### 16.3. Checking Signature Without Checking Issuer/Audience

A token with a valid signature from another issuer or audience may still not be intended for the current API. Verifying signature, issuer, audience, time, and scopes are distinct steps.

### 16.4. Trusting `kid` Without Verifying Signature

`kid` only selects a key. Never accept a token merely because a key ID exists in JWKS.

### 16.5. Accepting Algorithms Chosen by the Token Header

Pin algorithms per issuer policy. Never accept `none` or unexpected algorithm fallbacks.

### 16.6. Switching the Signer Before Publishing the New Public Key

Resource Servers may not have cached the new key yet. Pre-publish, wait for propagation, and only then switch the signer.

### 16.7. Deleting the Old Public Key Immediately After Rotation

Unexpired old tokens will fail verification. Maintain key overlap until all old tokens expire, accounting for caching and clock skew.

### 16.8. Keeping the Same `kid` for a New Key Pair

Caches can confuse old and new key material. Every key pair needs a new, stable `kid` that is not reused while cached.

### 16.9. Relying on JWKS Cache TTL for Emergency Revocation

Removing a key from JWKS does not immediately evict cached keys. Cache invalidation, CDN purges, and emergency deny policies are needed on compromise.

### 16.10. Dynamic Issuers Without an Allowlist

Never fetch metadata/JWKS from arbitrary issuer URLs supplied by tokens or users. This enables SSRF and trust injection.

### 16.11. Using Symmetric Secrets in All Resource Servers

With HMAC, every verifier can also sign. When signing and verification privileges must be separated across services, prefer asymmetric key pairs.

### 16.12. Thinking the JWKS Endpoint Must Be Protected Like a Private Key

A public JWKS endpoint can allow public GET requests. What must be protected is permission to publish/modify the key set and the integrity of the distribution channel.

## 17. Deployment Checklist

### 17.1. Key Ownership

- [ ] Private signing keys reside only in AS/signing service/KMS/HSM.
- [ ] Resource Servers hold only public verification keys.
- [ ] Signing and key-export permissions are restricted.
- [ ] Private key backup/recovery follows KMS/HSM policy.
- [ ] CI/CD and Resource Server identities cannot read private signing keys.

### 17.2. JWKS and Trust Configuration

- [ ] Public JWKS endpoint contains only public JWK members.
- [ ] `kid` is unique and never reused for different key material.
- [ ] `kty`, `use`, `key_ops`, `alg`, and public parameters are appropriate.
- [ ] Metadata/JWKS are fetched over HTTPS.
- [ ] Issuer URI/JWKS URI are trusted configuration.
- [ ] Issuer, audience, expiry, and not-before are validated.
- [ ] Algorithms are pinned by an allowlist.
- [ ] Arbitrary `jku`/`x5u` from token headers are never fetched.
- [ ] Multi-issuer setups have an allowlist/tenant registry and cache isolation.

### 17.3. Rotation and Incidents

- [ ] New public keys are published before the signer uses the new key.
- [ ] Propagation wait/verification occurs before switching the signer.
- [ ] Old keys are retained long enough for old tokens to expire.
- [ ] A new `kid` is assigned for each key pair.
- [ ] Emergency key compromise procedure exists.
- [ ] Capability exists to invalidate CDN/JWK caches or deny compromised `kid`s.
- [ ] Mechanism exists to confirm new policies reach all Resource Server nodes.

### 17.4. Testing and Operations

- [ ] Integration tests use real signed JWTs through a JWKS endpoint.
- [ ] Tests cover unknown `kid`, invalid signatures, and unsupported algorithms.
- [ ] Tests cover issuer, audience, `exp`, and `nbf`.
- [ ] Tests cover key overlap/rotation and old-key retirement.
- [ ] Tests cover JWKS endpoint outages/malformed responses.
- [ ] Tests cover multi-issuer isolation.
- [ ] Metrics track fetch errors, unknown `kid`, and rotation propagation.
- [ ] Logs contain no tokens/private keys.
- [ ] Runbooks exist for key compromise and stale JWKS caches.

## 18. Conclusion

With asymmetric JWT signing, the Authorization Server keeps the private signing key and Resource Servers receive only public verification keys. JWKS is the standard way to publish public keys; issuer metadata advertises the JWKS endpoint; Spring Security can be configured via `issuer-uri` or `jwk-set-uri` for both Servlet and WebFlux.

Key distribution is only secure when the Resource Server trusts the right issuer, fetches keys from configured endpoints, pins algorithms, verifies signatures, and validates issuer/audience/time claims. `kid` assists key selection but never replaces signature verification.

Routine rotation requires pre-publishing the new key, waiting for cache propagation, switching the signer, and retaining the old key until older tokens expire before retiring it. When a private key is compromised, stop signing, rotate keys, invalidate JWKS caches, and optionally block the old `kid` to prevent forged tokens from passing verification via stale caches.

**A Resource Server does not need token-signing privileges to perform its verification role.** Keeping private keys in KMS/HSM or a dedicated signing boundary, distributing public keys over authenticated JWKS, and testing rotation/compromise across all instances form the foundation of a secure trust model.

## References

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — JwtDecoder Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/JwtDecoder.html)
- [Spring Security — ReactiveJwtDecoder Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/ReactiveJwtDecoder.html)
- [Nimbus JOSE + JWT](https://connect2id.com/products/nimbus-jose-jwt)
