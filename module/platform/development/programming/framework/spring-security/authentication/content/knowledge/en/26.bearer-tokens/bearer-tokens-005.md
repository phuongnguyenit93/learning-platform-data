# JWK Sets, Key Rotation, and Key Source Trust Boundaries in Bearer JWT Validation

## 1. Why Does a Resource Server Need a JWK Set?

An API receiving `Authorization: Bearer <access-token>` must decide **whether the token was truly issued by a trusted issuer and is intended for this API**. When the access token is a **JWT signed with an asymmetric algorithm**, the Authorization Server/Identity Provider holds the **private key** to sign, while the Resource Server uses the corresponding **public key** to verify the signature. A *JSON Web Key (JWK)* is a JSON representation of a key; a *JWK Set (JWKS)* is a set of JWKs, typically published over HTTPS.

A JWK Set can contain **multiple concurrently accepted public keys** so signing keys can be rotated without immediately invalidating all unexpired access tokens. However, **fetching a JWKS is not enough to trust it**: the application must strictly constrain the **key source**, which key is selected, the algorithm, issuer, audience, expiration, and granted permissions.

Learning objectives for this lesson:

1. Read `JWK`/`JWKS` structures and understand `kid`, `kty`, `alg`, `use`, `n`, `e`, and why public JWKs never contain private signing keys.
2. Describe the verification chain from JWT/JWS → selecting a key from a **trusted JWKS** → verifying the signature → validating claims → enforcing authorization.
3. Perform **key rotation with an overlap phase**: publish the new key, start signing with the new key, keep the old key for unexpired tokens, and only then retire it.
4. Distinguish **scheduled rotation** from **private-key compromise** requiring emergency revocation.
5. Configure a Spring Boot 3 / Spring Security 6 Resource Server, binding `issuer-uri`, `jwk-set-uri`, `audiences`, and algorithms.
6. Properly reject forged `kid`, client-supplied `jku`/`x5u`, wrong-issuer JWKS, mismatched keys, stale caches, and wrong-audience tokens.

**Scope:** examples use Bearer **JWTs with JWS signatures** (RS256); if the access token is an opaque string, the Resource Server typically uses introspection against the Authorization Server and cannot pull a "key from JWKS" to verify the signature of an arbitrary opaque token.

## 2. What Do JWK and JWKS Actually Contain?

Per **RFC 7517**, a JWK Set is a JSON object with a `keys` array property. Example of two public RSA keys published by **the same trusted issuer**:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "signing-2026-01",
      "n": "<base64url-public-modulus-of-key-1>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "signing-2026-02",
      "n": "<base64url-public-modulus-of-key-2>",
      "e": "AQAB"
    }
  ]
}
```

**This is sample JSON for explaining the fields**; both `n` values are placeholders and cannot construct a real RSA public key. In practice `n` is the Base64URL-encoded RSA modulus, and `e` is typically the RSA exponent 65537 (Base64URL `AQAB`).

| Field | Meaning | What to Check |
| --- | --- | --- |
| `keys` | List of JWKs that may be published concurrently | Fetch only from a preconfigured trusted JWKS source |
| `kty` | Key type, e.g., `RSA`, `EC`, `OKP`, `oct` | Must match allowed algorithms; never mix symmetric and asymmetric keys |
| `kid` | Key ID used to find a **candidate key** | Case-sensitive; not proof of trust, not a global issuer identifier |
| `use` | Intended usage, typically `sig` (signing/verification) or `enc` | Never use an encryption key for signing arbitrarily |
| `key_ops` | Permitted operations, e.g., `verify` | If present, must be consistent with purpose and policy |
| `alg` | Key algorithm hint, e.g., `RS256` | Never let this field decide the app's allowed algorithm set |
| `n`, `e` | Public RSA modulus and exponent | Used to construct the RSA public key, not the private key |
| `crv`, `x`, `y` | Elliptic curve key parameters when `kty=EC` | Accept only curves/algorithms permitted by policy |
| `x5c`, `x5t`, `x5u` | Optional X.509 certificates and references | Never automatically trust any URL/certificate just because it appears in JSON/headers |

Private RSA parameters such as `d`, `p`, `q`, `dp`, `dq`, `qi` **must not be published** in a public JWKS. The Authorization Server must keep private keys in secure secret storage, preferably KMS/HSM as required. `oct` keys represent **symmetric secrets**; never expose them on a public JWKS.

An illustrative endpoint: `https://login.example.test/tenant-a/.well-known/jwks.json`. **The exact JWKS path is not standardized across all providers.** Clients must obtain the URL from trusted configuration or metadata of a configured issuer, such as OIDC Discovery/RFC 8414. Never append `/.well-known/jwks.json` to every provider assuming it is right.

### The JWT Header Only Selects a Candidate Key

A signed JWT header may contain:

```json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "signing-2026-02"
}
```

`typ=at+jwt` illustrates the JWT access token profile (RFC 9068), though **not every provider's JWT access tokens are guaranteed to carry that value**. Crucially: before signature verification, **the header is unverified**. An attacker can set any `kid` they like. It only helps the library look up a key **within the set of keys the resource server already decided to trust**; it does not let a JWT "register" a new key.

A JWT has the structure `base64url(header).base64url(payload).base64url(signature)`. With RS256, the signed/verified bytes are **the first two segments with the dot between them**. Decoding the JSON payload to inspect `sub`, `roles`, or `iss` **does not prove the token is valid**; verify first before trusting claims.

## 3. Proper Bearer JWT Verification Flow and Trust Boundaries

Suppose the API trusts only issuer `https://login.example.test/tenant-a`, audience `api://orders`, and algorithm `RS256`.

```text
HTTP request: Authorization: Bearer <JWT>
           |
           v
BearerTokenAuthenticationFilter (Spring Security)
           |
           v
JwtAuthenticationProvider / JwtDecoder
           |
           | 1. Use only trusted, configured issuer + jwkSetUri
           | 2. JWT header alg must be in allowlist (RS256 here)
           | 3. kid selects candidate key from that issuer's JWKS
           | 4. Verify signature over JWS signing input
           | 5. Validate iss, aud, exp, nbf, and required claims
           v
JwtAuthenticationToken + authorities
           |
           | 6. Check scope, route, tenant, business permissions
           v
Controller only if all conditions pass
```

All conditions **are required** and do not substitute for one another:

- **Signature:** proves the payload was signed by a private key matching a public key **already trusted for this issuer**. Does not prove all claims fit your API.
- **Issuer `iss`:** must match the issuer the application **preconfigured**. Never accept an arbitrary `iss` and fetch a JWKS from the Internet based on it.
- **Audience `aud`:** must contain this API's identifier, e.g., `api://orders`. A validly signed token issued for another API **must not be accepted**.
- **Expiration/time:** verify `exp` and `nbf` with only reasonable clock skew; if relying on `iat`, `jti`, `typ`, token type, lifetime, or revocation, define explicit policies.
- **Algorithm:** the app maintains an allowlist, e.g., RS256; reject `alg=none` or HS256/RS256 "algorithm confusion." Libraries must bind key types to permitted algorithms.
- **Authorization:** `scope`/`scp`, `roles`, tenant, and owner/resource permissions are checked **after authentication**; a valid signature does not grant admin rights automatically.

In Spring Security Resource Server, `JwtDecoder` handles verification/validation; `JwtAuthenticationConverter` maps scopes to authorities (default `SCOPE_...`), and `SecurityFilterChain` handles authorization.

### A Case That Must Be Rejected

Token A has a valid signature from **Issuer A**, yet `aud=api://billing` while the request targets the Orders API. If the app checks only signature and `exp`, the token can be misused via cross-audience token substitution. You must check `aud=api://orders` to reject A. Similarly, a token issued by Issuer B must not be accepted merely because Issuer B also has a JWKS endpoint and happens to use the same `kid` as Issuer A.

## 4. How Is a Trusted Key Source Established?

**Trusting a key ≠ trusting a JSON string.** Per RFC 7517 and RFC 8725, trust comes from how the application **establishes the relationship between issuer, URL/metadata, and keys**, and then restricts which tokens are accepted.

### 4.1. Configuring the Issuer as a Trust Anchor

In OAuth2/OIDC, a resource server typically has static/managed configuration:

```text
trusted issuer: https://login.example.test/tenant-a
expected aud:   api://orders
allowed alg:    RS256
JWKS endpoint:  https://login.example.test/tenant-a/keys
```

The domain above is a sample. When using discovery, the library fetches the metadata document **for the configured issuer** and reads `jwks_uri` from it. TLS/certificates, hostnames, and issuer metadata must be verified; redirect handling, DNS, and network egress must prevent pointing to untrusted sources.

A JWKS endpoint can return 200 OK and valid JSON and still be **untrusted** if it does not belong to an allowed issuer. If an attacker can swap the JWKS URL or tamper with responses over an insecure TLS proxy, the attacker can swap in their own public key and forge tokens the app will accept.

### 4.2. Never Let a JWT Tell You Where to Fetch Keys

A JWT/JWS header may contain:

- `kid`: candidate key identifier, which must be matched in the **application's trusted JWKS**.
- `jku`: JWKS URL suggested by the header.
- `x5u`: certificate URL.
- `jwk`: public key embedded directly in the header.
- `x5c`: embedded certificate chain.

**Never automatically trust or fetch `jku`/`x5u` from an unverified token.** Doing so can introduce **SSRF** vulnerabilities hitting internal networks or metadata services, or allow an attacker to host a JWKS with attacker-generated keys and sign forged tokens. If a special use case truly requires these headers, enforce a strict source allowlist, verify key/certificate ownership under a trust policy, and never forward cookies or Authorization headers to arbitrary URLs. The safe API default is to **ignore key URLs inside the JWT** and use only configured sources.

Likewise, an embedded `jwk` inside the token **does not make itself trusted**; "the token says trust my key" is meaningless circular verification. A certificate chain in `x5c` is not safe by default without PKIX chain validation and verifying the issuer relationship.

### 4.3. Kid Collisions and Algorithm Confusion

- `kid` is case-sensitive and not guaranteed to be globally unique across providers. An ID like `key-1` can exist in both Issuer A and B. Key lookup must be **scoped to the selected issuer's key set**.
- Never interpolate an unsanitized `kid` into file paths or SQL/LDAP queries; RFC 8725 warns about `kid` injection. Standard practice is letting the JWT library select from the already-fetched key set.
- The set of allowed algorithms is a decision **from application configuration**. Never read `alg=HS256` and treat an RSA public key as an HMAC secret; never accept `alg=none`; never treat `alg` inside an attacker-controlled JWK as policy.
- Use public and private keys for their proper roles: public keys verify asymmetric signatures and cannot sign tokens; private keys stay with the issuer.
- A JWKS may contain `enc` keys for encryption; do not apply them as `sig` signature-verification keys.

## 5. Spring Boot 3.x / Spring Security 6.x: Resource Server Configuration

### 5.1. Dependencies

Create a Spring Boot 3.x application (Java 17+, Servlet/Spring MVC). In a Gradle project with the Spring Boot plugin/dependency management, add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

The Spring Boot Resource Server starter provides Bearer JWT authentication and JOSE/JWT libraries. The code below **does not need a handwritten parser, JWKS fetcher, `PublicKey` builder, or manual signature check**.

### 5.2. Option A: Issuer Discovery

In `src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/tenant-a
          audiences: api://orders
          jws-algorithms: RS256
```

When the provider supports OIDC Discovery or OAuth Authorization Server Metadata, Spring can discover metadata from `issuer-uri`, obtain `jwks_uri`, use the public keys to verify signatures, and validate `iss`. `audiences` requires the current API's audience; `jws-algorithms` restricts accepted algorithms. The `example.test` URL is a placeholder, so this runs only after substituting a real issuer.

Never assume a decoder returning a payload with `sub` is enough: the validators decide whether the `Jwt` is trustworthy and intended for the resource.

### 5.3. Option B: Pin JWKS URI While Keeping Issuer and Audience

If you want a fixed JWKS URL for the API or want to avoid startup discovery:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/tenant-a
          jwk-set-uri: https://login.example.test/tenant-a/keys
          audiences: api://orders
          jws-algorithms: RS256
```

When providing both `issuer-uri` and `jwk-set-uri`, Spring Boot uses the URI directly instead of discovering the endpoint via metadata, and **still validates the `iss` claim**. Exact JWKS connection timing, caching, and refresh behavior depend on the library version and decoder configuration. **Never configure only JWKS and forget issuer and audience**: being able to verify a signature with a public key is not enough to prove the token belongs to your system.

These two snippets are **two deployment options**, not two duplicate Resource Servers to configure at once. The JWKS URI must be operator-managed per issuer; never derive it from request-supplied `iss`, `kid`, or `jku` without a trust policy.

### 5.4. SecurityFilterChain Applying Bearer Authentication + Scope

Create `src/main/java/com/example/api/ApiSecurityConfig.java`:

```java
package com.example.api;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyRequest().authenticated())
                // Only for APIs authenticating via Bearer header, without cookies.
                .csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
```

In this configuration, `/api/orders/**` requires scope `orders.read`. Spring Resource Server maps `scope`/`scp` to authorities prefixed with `SCOPE_` by default. **CSRF is disabled only because this is a pure Bearer-header API and does not use session cookies to authenticate requests.** If the same application has browser form login/cookies, design separate security chains and appropriate CSRF protection; do not disable CSRF globally by reflex.

Create `src/main/java/com/example/api/OrdersController.java`:

```java
package com.example.api;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersController {

    @GetMapping("/api/orders")
    public Map<String, String> orders(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
                "subject", jwt.getSubject(),
                "issuer", jwt.getIssuer().toString());
    }
}
```

The project needs a `@SpringBootApplication` class in `com.example.api` or a parent package so Spring scans these two classes. With an unexpired JWT signed by a key in the right issuer's JWKS, containing `api://orders` in `aud` and `orders.read` in `scope`, the request:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <signed-access-token>
```

can return `200 OK`. If the token is missing, invalidly signed, expired, or has the wrong issuer/audience, the Resource Server typically returns `401 Unauthorized` with a Bearer challenge. If **the token is valid** but lacks `SCOPE_orders.read`, Spring Security returns `403 Forbidden`. Never print raw access tokens to logs.

### 5.5. When Defining a Custom JwtDecoder, Keep All Validators

Spring Boot can auto-configure `JwtDecoder` from the properties above. If you declare your own `@Bean JwtDecoder` or just call `NimbusJwtDecoder.withJwkSetUri(...).build()`, you replace auto-configuration; **never assume Boot's issuer/audience validators automatically apply to the new bean**.

The class below is an **alternative** to Boot auto-config in section 5.2/5.3, explicitly illustrating algorithm pinning and claim validation. Use the same `SecurityFilterChain`, with **only one** source creating `JwtDecoder`:

```java
package com.example.api;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class ExplicitJwtDecoderConfig {

    private static final String ISSUER =
            "https://login.example.test/tenant-a";
    private static final String JWKS =
            "https://login.example.test/tenant-a/keys";
    private static final String AUDIENCE = "api://orders";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder.withJwkSetUri(JWKS)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(AUDIENCE)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error("invalid_token",
                                        "Unexpected audience", null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        issuerAndTime, audience));

        return decoder;
    }
}
```

Meaning: JWKS is the **operator-chosen key source**, RS256 is the **permitted algorithm**, and the validators check issuer/time and audience. `JwtValidators.createDefaultWithIssuer` includes standard validators for issuer and timestamps. If the system requires rules for `typ`, `azp`, tenant, `jti`, token lifetime, or custom scopes, add appropriate policies **without dropping standard validators**.

## 6. Scheduled Key Rotation: Publish First, Sign Next, Retire Last

Let us call the two RSA signing keypairs **K1** (old) and **K2** (new). The JWK Set publishes only **public** K1/K2; private keys remain at the issuer. Tokens already issued with K1 may remain valid until `exp`.

| Stage | Issuer Signs New Tokens With | JWKS Public Keys | API Behavior |
| --- | --- | --- | --- |
| T0 — steady state | Private K1 | Public K1 | Valid K1 tokens accepted |
| T1 — prepare transition | Private K1 | **Public K1 + K2** | APIs have time to refresh cache and learn K2 |
| T2 — start new signing | **Private K2** | **Public K1 + K2** | Unexpired K1 tokens and K2 tokens both verify |
| T3 — K1 token window drains | Private K2 | **Public K1 + K2** until no valid K1 tokens remain | Never remove K1 abruptly while K1 tokens are unexpired |
| T4 — retire old key | Private K2 | Public K2 only | K1 tokens rejected; K2 continues working |

**Why pre-publish?** Resource Servers typically cache the JWKS. If the issuer starts signing with K2 immediately while APIs only know K1, many requests will fail with 401 because the new `kid` is missing from cache. Publish K2 first, monitor cache refresh/fetch success, and only then start signing tokens with private K2.

**Why keep the old key for a while?** A JWT access token signed with K1 **is not re-signed because of rotation**. While the token remains unexpired, APIs need public K1 to verify it. The overlap window depends on **maximum old-token lifetime**, clock skew, JWKS cache/refresh behavior, retries, and propagation latency. There is no single fixed number of minutes that fits every system.

**Assign a distinct `kid` to each public key** and avoid reusing the same `kid` for a new key within an issuer. If K2 reuses the `kid` "K1", caches may hold the old public key while the issuer signs with the new private key, causing hard-to-diagnose verification failures.

Practical scheduling calculation: if a K1 access token is issued just before T2 with a max lifetime of 15 minutes and 60 seconds of allowed clock skew, keep public K1 **at least until the last token issued with K1 has expired**, plus any necessary operational margin. You must know **when the last K1 token was issued**, not merely when K2 was published.

## 7. Emergency Revocation When a Private Key Is Compromised

Scheduled rotation aims for **zero disruption**; when private K1 is compromised, the goal shifts to **stopping attacker-signed forged tokens**. Keeping public K1 so old tokens still pass poses a real risk.

Incident response procedure for suspected compromise:

1. Stop signing with private K1, isolate key material, assess blast radius, and securely provision K2.
2. Remove or disable **public K1 from trusted key sources** as quickly as practical; critically note that **Resource Server JWKS caches may still retain K1**.
3. Execute a cache invalidation/refresh plan and fail-closed policies for APIs. Do not merely delete K1 from the endpoint and claim all APIs have stopped trusting K1.
4. Accept that unexpired tokens signed with K1 **may be rejected**; require users/clients to obtain fresh tokens through secure flows.
5. If immediate pre-TTL revocation is required, consider a `jti` denylist, centralized introspection/revocation, shorter token lifetimes, trust-configuration updates, or additional controls. These must be designed beforehand; self-contained JWTs with only `exp` do not provide instant revocation.
6. Monitor 401/403 rates, API instances still trusting K1, and key/access logs to detect forged tokens or operational impact.

**There is no "remove key from JWKS = instant revocation of all tokens."** From the Resource Server's perspective, already-signed tokens may continue verifying against a cached public K1 until the cache expires/is invalidated or additional blocking policies take effect.

## 8. JWKS Caching and Availability: When to Refresh, When to Reject?

Spring Security Resource Server uses JWT/JWK libraries with caching and key-refresh mechanisms; per Spring Security docs, it can update keys automatically when the Authorization Server publishes new keys. **Exact refresh timing, TTL, and behavior on an unknown `kid` depend on library version, decoder, and cache config**, so verify empirically rather than assuming "an unknown `kid` always triggers an immediate fetch."

| Scenario | Correct Resource Server Behavior | What to Monitor |
| --- | --- | --- |
| JWT has kid K1 and K1 is in trusted cache | Verify signature with K1, then validate claims | Only valid tokens accepted |
| JWT has new kid K2, cache only has K1 | May need to fetch updated JWKS; if trusted K2 is unavailable, **fail closed** | Refresh attempts, cache age, HTTP errors, transient 401s |
| JWKS server returns 5xx/timeout | Never skip signature verification; policy for using valid cached trusted keys must be explicit | 401 rate, JWKS fetch failures, TTL |
| JWKS returns malformed JSON or empty keys | Reject tokens lacking a trusted key; alert operations | Parse errors, empty sets, schema mismatches |
| JWKS completely replaced unscheduled | Alert on unexpected change/kid; verify source/incident | Publication audit trail and key-set diffs |
| Disallowed token alg | Reject; never try algorithms/keys indiscriminately | JWT decode failures |
| Key K1 retired, yet server caches K1 | May still verify K1 tokens until cache invalidates | Forced refresh / deny policy needed |

Operational considerations:

- Use HTTPS with certificate verification, reasonable timeouts, JWKS response size/key count limits, and rate limiting/backoff on refresh calls. Do not let every JWT carrying a random `kid` trigger continuous outbound requests.
- HTTP caching semantics like `Cache-Control`/`ETag` can be used **if supported by the client/decoder**, though exact behavior must be verified. Cache tuning must never keep a revoked key trusted indefinitely.
- Separate JWKS network failures from bad-signature JWT failures for investigation; **never log full JWTs** when enabling debug logging.
- Manage multi-instance/multi-region deployments: instances hold caches of different ages; canary-test K2 across regions before switching signing.
- Test retry/recovery and availability alerts for the provider; a prolonged JWKS outage can prevent verifying tokens signed with newly rotated keys.

## 9. Standalone Java 17 Example: Public JWK and K1 → K2 Lifecycle

The example below generates RSA keypairs in memory, exports **only public modulus/exponent** into a JWK-like structure, and uses RS256 signatures to simulate three rotation stages. It uses **pure JDK 17+** with no Spring dependencies and issues no real usable access tokens.

**Lab limitation:** `DemoJws` only holds signed content, `kid`, and signature—no production JSON/JWT parser, no `iss`/`aud`/`exp` validation, and no network trust. After learning from it, use a maintained library's `JwtDecoder`; **never copy this example into a production JWT verifier**.

Save as `JwkRotationDemo.java`:

```java
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.RSAPublicKeySpec;
import java.util.Arrays;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;

public class JwkRotationDemo {

    record PublicJwk(String kid, String n, String e) {}
    record DemoJws(String kid, String signingInput, byte[] signature) {}

    static String b64url(byte[] value) {
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(value);
    }

    static String unsigned(BigInteger value) {
        byte[] bytes = value.toByteArray();
        if (bytes[0] == 0) {
            bytes = Arrays.copyOfRange(bytes, 1, bytes.length);
        }
        return b64url(bytes);
    }

    static PublicJwk publicJwk(String kid, PublicKey key) {
        RSAPublicKey rsa = (RSAPublicKey) key;
        return new PublicJwk(
                kid, unsigned(rsa.getModulus()),
                unsigned(rsa.getPublicExponent()));
    }

    static PublicKey toPublicKey(PublicJwk jwk) throws Exception {
        BigInteger n = new BigInteger(
                1, Base64.getUrlDecoder().decode(jwk.n()));
        BigInteger e = new BigInteger(
                1, Base64.getUrlDecoder().decode(jwk.e()));
        return KeyFactory.getInstance("RSA")
                .generatePublic(new RSAPublicKeySpec(n, e));
    }

    static DemoJws sign(String kid, PrivateKey privateKey)
            throws Exception {
        String header = "{\"alg\":\"RS256\",\"kid\":\"" + kid + "\"}";
        String payload = "{\"sub\":\"alice\"}";

        String input = b64url(header.getBytes(StandardCharsets.UTF_8))
                + "."
                + b64url(payload.getBytes(StandardCharsets.UTF_8));

        Signature rs256 = Signature.getInstance("SHA256withRSA");
        rs256.initSign(privateKey);
        rs256.update(input.getBytes(StandardCharsets.US_ASCII));

        return new DemoJws(kid, input, rs256.sign());
    }

    // Illustrates only looking up kid in a fixed trust store.
    // Production must safely parse JWTs and validate all claims.
    static boolean verify(DemoJws token, Map<String, PublicJwk> trusted)
            throws Exception {
        PublicJwk jwk = trusted.get(token.kid());
        if (jwk == null) {
            return false;
        }

        Signature rs256 = Signature.getInstance("SHA256withRSA");
        rs256.initVerify(toPublicKey(jwk));
        rs256.update(
                token.signingInput().getBytes(StandardCharsets.US_ASCII));
        return rs256.verify(token.signature());
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);

        KeyPair old = generator.generateKeyPair();
        KeyPair next = generator.generateKeyPair();
        KeyPair attacker = generator.generateKeyPair();

        PublicJwk k1 = publicJwk("k-2026-01", old.getPublic());
        PublicJwk k2 = publicJwk("k-2026-02", next.getPublic());

        DemoJws oldToken = sign(k1.kid(), old.getPrivate());
        DemoJws newToken = sign(k2.kid(), next.getPrivate());
        DemoJws forged = sign(k2.kid(), attacker.getPrivate());

        Map<String, PublicJwk> trusted = new HashMap<>();

        // T0: only K1 is in trusted JWKS.
        trusted.put(k1.kid(), k1);
        System.out.println("oldBefore=" + verify(oldToken, trusted));

        // T1/T2: K1 + K2 are published during the overlap phase.
        trusted.put(k2.kid(), k2);
        System.out.println("oldOverlap=" + verify(oldToken, trusted));
        System.out.println("newOverlap=" + verify(newToken, trusted));

        // Attacker sets the same kid=K2 but uses a different private key.
        System.out.println("forgedSameKid=" + verify(forged, trusted));

        // T4: remove K1 from the trusted set after old tokens expire.
        trusted.remove(k1.kid());
        System.out.println("oldAfter=" + verify(oldToken, trusted));
        System.out.println("newAfter=" + verify(newToken, trusted));
    }
}
```

Run in the directory containing the file:

```bash
javac JwkRotationDemo.java
java JwkRotationDemo
```

Deterministic stdout (keys are randomly generated so bytes differ on each run, while boolean results remain identical):

```text
oldBefore=true
oldOverlap=true
newOverlap=true
forgedSameKid=false
oldAfter=false
newAfter=true
```

Explanation of each output:

- `oldBefore=true`: a JWS signed with private K1 verifies with public K1.
- `oldOverlap=true` and `newOverlap=true`: while both keys are published, tokens signed by either private key have a matching verification key.
- `forgedSameKid=false`: the attacker sets the `kid` header to K2's name but **lacks private K2**, so the signature fails. `kid` is not a granted permission.
- `oldAfter=false`: once K1 is removed from the **trusted key set**, the verifier no longer accepts K1 token signatures in this mini-lab.
- `newAfter=true`: K2 continues working.

The lab uses `DemoJws.kid` as trusted input, **not building a parser for Internet-sourced tokens**. Real verification must check JWS structure, protected headers, algorithms, public key trust, issuer, audience, lifetime, and scopes; raw Java `Signature` alone is insufficient.

## 10. End-to-End Verification When Issuing or Rotating Keys

In a test environment with an Authorization Server minting real RSA JWTs and a controlled JWKS, include at least the independent tests below. Do not merely mock `JwtDecoder` to return a prebuilt `Jwt`, as that skips the signature/JWKS mechanics this lesson tests.

| Case | Input Data/Keys | Expectation |
| --- | --- | --- |
| Initial K1 | JWKS=[K1], JWT signed by private K1, valid iss/aud/scope | 200 on permitted endpoint |
| Prepublish K2 | JWKS=[K1,K2], still signing with K1 | K1 token continues returning 200 |
| Switch to signing K2 | JWKS=[K1,K2], K2 JWT, updated cache | K2 token 200, unexpired K1 still 200 |
| After K1 expiry | JWKS=[K2], K1 no longer in trusted cache | K1 token 401; K2 200 |
| Forged kid | JWT carries kid K2 but signed by attacker's private key | 401 |
| Nonexistent kid | JWT carries a kid absent from trusted JWKS | 401; never pick a public key from the token |
| Wrong issuer | Valid signature, disallowed `iss` | 401 |
| Wrong audience | Valid signature, `aud=api://billing` | 401 |
| Expired / future nbf | Valid signature, past `exp` / future `nbf` | 401 (beyond allowed clock skew) |
| Wrong alg | `alg=none`, HS256, or disallowed algorithm | 401 |
| Missing scope | Valid signature/claims, missing `orders.read` | 403 |
| Malicious jku | JWT includes `jku=https://attacker.example.test/keys` | Never fetch outside allowlist; attacker cannot make JWT trusted |
| JWKS 5xx | Old cache has K1, request uses new K2 | Never bypass signature; log refresh error, fail closed if key missing |
| Emergency retire | Key K1 suspected compromised, deny policy/cache refresh updated | Instances gradually/immediately reject K1 per designed incident mechanism |
| Multi-issuer | Issuer B token validly signed, yet API trusts only Issuer A | 401 even when kid names collide |

For "401" tests, verify the cause **is actual validation**, not an unstarted controller, generic TLS error, or MockMvc injecting a principal. To test real signed JWTs, use dedicated test keypairs, a mock HTTPS JWKS endpoint or test Authorization Server, and point the Spring Resource Server to the test-controlled mock issuer. Tests using only Spring Security Test's `jwt()` mock principal test authorization, yet **do not prove JWKS rotation works**.

### Observing Without Leaking Secrets

- Track error categories: `invalid_token` due to signature/issuer/audience/expiry, unknown kid, JWKS fetch failed, 401, and 403.
- Emit metrics on **JWKS refresh counts, cache age, endpoint availability, and currently published kid set**; avoid logging full tokens or full Authorization headers.
- During K2 rollout, track key distribution per instance/region; when retiring K1, confirm instances still holding cached K1 have been updated.
- Use request correlation IDs and key-set version events, without letting untrusted `kid` values create unbounded metric cardinality.

## 11. Common Pitfalls and Diagnostics

| Symptom | Cause | Resolution |
| --- | --- | --- |
| 401 after issuer starts signing with K2 | JWKS didn't prepublish K2, cache hasn't refreshed, old kid reused | Prepublish K2, verify cache/discovery, check kid uniqueness |
| 401 on only some instances | Instances hold caches of different ages, differing network/egress | Inspect per-instance cache/refresh and JWKS reachability |
| "JWT signature valid" yet API rejects | Wrong `iss`/`aud`/`exp`/scope or policy | Distinguish 401 authentication from 403 authorization |
| Token from another issuer gets in | Overly broad JWKS trust or missing issuer/audience binding | Bind each issuer to its JWKS, algorithm, and audience policy |
| Outsider signs token and passes | API trusts JWT-supplied `jku`/`jwk` | Use only configured trusted key sources and verify policy |
| `alg=none` token passes | JWT allowed to pick algorithm or buggy custom decoder | Enforce algorithm allowlist, use maintained library |
| JWKS leaks private key | Public JWKS mixed with private JWK containing `d` | Isolate secret store, emergency key rotation, investigate |
| K1 removed too early | K1 tokens still unexpired and Resource Server needs K1 | Maintain overlap until expiry during normal rotation |
| K1 removed yet K1 tokens still pass | Old key cache unexpired or decoder uses another key store | Invalidate cache, update trust policy, audit config |
| JWKS down → all tokens fail | Missing valid key cache, TTL expired, network timeout | Design availability/cache/fail-closed behavior and SLOs |
| ID Token used as Bearer API token | JWT type confusion, wrong audience/typ/token purpose | Separate ID Token and access token; verify audience/token profile |
| Custom `JwtDecoder` drops issuer check | Custom bean replaced Boot auto-config | Wire `JwtValidators.createDefaultWithIssuer` and aud validator |

**Distinguish a revoked token from a retired signing key.** Removing a public key causes **every token signed by that key** to fail verification once verifiers refresh. Revoking **one** specific access token generally requires another mechanism such as a `jti` denylist, introspection, or short token lifetimes; you cannot delete an entire key just to revoke one token without impacting all other tokens.

## 12. Key-Source Trust Assessment Checklist

1. **JWKS source:** URL/issuer is predefined by configuration or metadata of a trusted issuer; TLS/certificates and DNS/redirects/egress are controlled; never accept key URLs from JWT headers.
2. **Keys:** publish public keys only, protect private keys separately; verify matching `kty`, `use/key_ops`, `alg`; `kid` only selects candidates within the right issuer's set.
3. **JWT:** verify JWS signature, algorithm allowlist, `iss`, `aud`, `exp`, `nbf`, and required token type/claims; prevent HS/RS confusion and `none`.
4. **Authorization:** scopes/roles/tenants/resource permissions are decided separately, after authentication passes.
5. **Scheduled rotation:** K2 is published **before** signing; K1+K2 coexist during overlap; K1 is removed only after the last token's expiry plus appropriate clock/cache margin.
6. **Key compromise:** have a plan to stop trusting K1, refresh/invalidate caches, balance downtime, and revoke potentially forged access tokens.
7. **Caching/availability:** refresh timing, unknown kid handling, timeouts, rate limits, JWKS outages, multi-instance behavior, and fail-closed behavior are tested.
8. **Multi-issuer:** each issuer has its own trust policy; never pool public keys to accept arbitrary tokens; `kid` is not globally unique.
9. **Negative tests:** wrong kid/signature/alg/issuer/audience/exp, attacker `jku`, key rotation under stale cache, and revoked keys all have verified test outcomes.

If you remember only one sequence: **Select the trusted issuer first → fetch that issuer's JWKS → use `kid` to select a candidate and verify signature per algorithm allowlist → validate claims and permissions → manage rotation with caching and incident response.** A JWT offering its own "key to trust me" must never replace step one.

### Standards and Documentation

- [RFC 7517 — JSON Web Key (JWK), JWK Set, Key Provenance and Trust](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JWT Best Current Practices; algorithm verification, key provenance, jku/x5u risks](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [Spring Security 6.5 — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security 6.5 — Bearer Token Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/bearer-tokens.html)
