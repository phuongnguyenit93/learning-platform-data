# Verifying Token Issuer, Audience, Expiration, and Signature

> **Module:** Spring Security – Fundamentals → **Tokens and Protocols**. This lesson focuses on how an **OAuth 2.0 Resource Server** receiving **JWT** access tokens must simultaneously verify: **issuer (`iss`)**, **audience (`aud`)**, **validity window (`exp` and `nbf`)**, and **signature/JWS + trusted keys**. Examples use **Spring Boot 3.x, Spring Security 6.x, Java 17+**, contrasting production configuration via `issuer-uri`/JWKS with local integration tests using real RSA signing.

## 1. Context: "A Decodable Token" Does Not Mean a Valid Token

An HTTP API receives:

```http
GET /api/whoami HTTP/1.1
Host: orders.example.internal
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

A JWT is typically a **JWS compact serialization** string with three Base64URL parts:

```text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
```

Illustrative structure example (not a token with a valid signature):

```json
{
  "header": {
    "alg": "RS256",
    "kid": "key-2026-11",
    "typ": "JWT"
  },
  "payload": {
    "iss": "https://identity.example.org",
    "sub": "user-42",
    "aud": ["orders-api"],
    "iat": 1793779200,
    "nbf": 1793779200,
    "exp": 1793782800,
    "scope": "orders.read"
  },
  "signature": "Base64URL-signature-here"
}
```

Merely Base64URL-decoding `header` and `payload` lets you **read** the claims. That is not authentication! An attacker can craft JSON with `"sub":"admin"` and `"scope":"orders.write"`. If the API relies on that data before verifying the signature and other conditions, the API can mistakenly trust a self-declared identity/permission forged by the attacker.

**Principle:** Do not use claims to make security decisions until the JWT decoder and validators have verified the token against **server-side trust configuration**. A signed JWT is **not encrypted by default**; payload contents can be read by anyone holding the token, so never put passwords, secrets, or unnecessary sensitive information into a JWT.

## 2. Four Non-Interchangeable Checks

| Check | Field / Component | Question | If Skipped |
|---|---|---|---|
| **Issuer** | Claim `iss` | Was the token issued by an **authorization server/issuer accepted by this API**? | Tokens from another environment or issuer can be misused |
| **Audience** | Claim `aud` | Is this token **intended for this resource server**? | A token issued for service A gets presented to service B (token substitution) |
| **Expiration** | `exp`, `nbf`, and `iat` when needed | Is the token within the validity window allowed by policy? | Expired or not-yet-active tokens are still accepted |
| **Signature and key** | JWS `alg`, `kid`, `signature`, JWKS/public key | Is the token content intact and signed with a **trusted key** using an allowed algorithm? | Tampered tokens or tokens signed with an unknown key are treated as authenticated |

**Joint requirement:** Valid signature but wrong issuer → **reject**; right issuer but wrong audience → **reject**; both right but expired → **reject**; right claims but invalid signature → **reject**.

Beyond these four core checks, real-world systems may also need to check `typ` (access token profile), `azp`/`client_id`, scopes/authorities, tenant, `jti`/revocation, token binding, DPoP, IP/device/risk policy, or token purpose. Do not turn "all 4 checks passed" into "permitted to perform any action": **authentication** differs from **authorization**.

### 2.1. Standard Authentication Flow for Bearer JWT

```text
Client sends Authorization: Bearer <JWT>
      |
      v
BearerTokenAuthenticationFilter
      |
      v
JwtAuthenticationProvider → JwtDecoder
      |
      +-- Parse JWS, check format / permitted algorithms
      |
      +-- Select public key from trust anchor / JWKS and verify signature
      |
      +-- Jwt validators
      |     ├─ iss == trusted issuer?
      |     ├─ aud contains API's audience?
      |     ├─ exp/nbf valid against clock and clock skew?
      |     └─ Other claim / business constraints?
      |
      +-- Any check fails → authentication fails (typically 401)
      |
      +-- All pass → build JwtAuthenticationToken
                         |
                         v
              Convert scope → authorities
                         |
                         v
              HTTP / method / object authorization
                         |
                         +-- Insufficient permissions → typically 403
                         |
                         +-- Authorized → controller / service
```

This is a logical processing model. Internal ordering of parsing/signature/claims may vary across library versions, yet **no trusted identity may be handed to the application before validation succeeds**.

## 3. Verifying Issuer (`iss`): Who Is Allowed to Issue Tokens for This API?

### 3.1. What Does `iss` Mean?

The issuer is the identifier of the token-issuing party, typically a stable URI managed by the identity system:

```json
{
  "iss": "https://identity.example.org/realms/shop",
  "sub": "alice"
}
```

At the resource server targeting that issuer, `iss` must be compared against the **issuer value configured from a trusted source**, not taken from the token and assumed to be legitimate.

Example **Spring Boot config**:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.org/realms/shop
```

With appropriate auto-configuration, Spring Security can discover the issuer's metadata, locate the JWKS to verify signatures, and validate `iss` along with `exp` and `nbf`. The example URI is not a live learner endpoint; replace it with the verified URI provided by your identity provider.

**Exact matching:** `https://id.example/realm` and `https://id.example/realm/` can be two distinct strings to a validator. Do not "fix" an issuer by arbitrarily stripping slashes or switching to `contains`. Use the official issuer identifier and test across both prod and staging environments.

### 3.2. Issuer Differs from the API's Host

`iss` is the token issuer, not the domain receiving the request. The API `orders.example.org` can legitimately accept tokens issued by `identity.example.org`. `iss` does not have to equal the service's hostname.

An application can support multiple issuers (multi-tenant, multiple identity providers). In that case, there must be an **explicit policy** selecting trust configuration per issuer—such as maintaining an allowlist of permitted issuers and using an appropriate resolver—rather than downloading keys from whatever `iss` URL an attacker supplies. In particular, prevent SSRF or blindly trusting JWKS endpoints specified by a token.

### 3.3. Checking `iss` Alone Is Still Not Enough

An attacker can craft a payload with `"iss":"https://identity.example.org"`. Without verifying the signature with a **trusted key bound to that issuer**, this claim is just an attacker-supplied string. Validation claims and keys must belong to one consistent trust setup: official issuer ↔ official metadata/JWKS ↔ allowed algorithms.

## 4. Verifying Audience (`aud`): Who Is This Token Intended For?

### 4.1. Audience Is the Resource/Recipient, Not the User

`aud` answers "**where or by which service** is this token intended to be used?" It is not a username; the `sub` field typically identifies the subject.

For example, a shared issuer mints tokens for two APIs:

```json
{
  "iss": "https://identity.example.org",
  "sub": "alice",
  "aud": ["catalog-api"],
  "scope": "catalog.read"
}
```

The token above may be valid at `catalog-api`, yet **`orders-api` must reject it**, even though both signature and issuer are valid. If both services trust the same issuer and ignore `aud`, a token for service A can be "passed along" to service B.

A JWT `aud` can be a single string or an array of strings per the standard; in Spring Security the JWT claim is typically converted into a `List<String>` for validation:

```json
{
  "aud": ["orders-api", "billing-api"]
}
```

A resource server expecting `orders-api` checks that **the audience list contains the exact element `orders-api`** (while still enforcing other policies), rather than matching substring `"orders"`. If a product requires the audience to contain only a single value, that is a **stricter policy** requiring dedicated design and testing.

### 4.2. Boot Configuring Audience Directly

On Spring Boot 3.x versions supporting this property:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.org/realms/shop
          audiences:
            - orders-api
```

Spring Boot wires audience validation into the resource server when configured appropriately. If you declare only `issuer-uri` without declaring audiences, **do not assume `aud` is already validated against your API name**. Check your exact Boot version and any custom `JwtDecoder` bean (a custom bean can override auto-configuration).

### 4.3. When Is a Custom Validator Needed?

For dynamic issuers, multi-audience policies, mandatory claim rules, or environments needing clear error reporting, a custom `OAuth2TokenValidator<Jwt>` can be used:

```java
OAuth2TokenValidator<Jwt> audienceValidator =
    new JwtClaimValidator<List<String>>(
        JwtClaimNames.AUD,
        audiences -> audiences != null
            && audiences.contains("orders-api"));
```

This is a **configuration snippet**; complete imports and class structure appear in the example in Section 8. Note: never replace all default validators with **only** an audience validator, as that would drop issuer/timestamp checks. Always **compose** validators.

## 5. Expiration (`exp`, `nbf`, `iat`) and Clock Skew

### 5.1. Meaning of Time Claims

- `exp` (*expiration time*): the token is no longer valid at or after this expiration timestamp. It is the upper bound of usability.
- `nbf` (*not before*): the token must not be accepted **before** this timestamp.
- `iat` (*issued at*): when the token was created. Useful for auditing and certain "token age" policies, though **it does not replace `exp`/`nbf`**.

Time values in JWT are typically **NumericDate**, meaning seconds since the Unix epoch in UTC (which may be decimal per the spec), not JavaScript milliseconds. Do not confuse `1793782800` seconds with `1793782800000` milliseconds.

### 5.2. Illustrative Timeline

```text
UTC time:
    nbf                    now                    exp
     |----------------------|----------------------|
  not yet valid       token usable            expired
```

A token with `nbf` one hour in the future must not be accepted right now. A token with `exp` one hour ago must be rejected. A few seconds of clock drift may exist between the Authorization Server and API; Spring Security provides `JwtTimestampValidator` to evaluate `exp`/`nbf` with an appropriate **clock skew**.

**Clock skew is not an arbitrary token extension.** If an API allows a few dozen seconds of leeway, a token that expired just a couple of seconds ago may still pass under policy. Do not test a token expired by 1–2 seconds and declare validation broken; test well past the boundary or configure skew explicitly.

### 5.3. Default Time Validators and Additional Policies

`JwtValidators.createDefaultWithIssuer(issuer)` combines default conditions (including timestamps and issuer per Spring Security's API). However, applications must verify their own contract:

- Some validators only check `exp`/`nbf` **when the claim is present**; if tokens **must contain `exp`**, add an explicit required-claim policy.
- `iat` does not inherently prove the token came from a trusted party. Trust it only after signature validation, and add a "maximum token age" check if the threat model requires it.
- JWTs have no built-in revocation. An unexpired token may already have been revoked. Use short TTLs, introspection, revocation stores, key rollover, or other mechanisms as needed.
- Never "add 1 day to `exp` when the server reads the token" to work around clock errors; fix NTP/time sync and agreed skew.

Example setting tolerance (illustrative snippet):

```java
JwtTimestampValidator timestamp =
    new JwtTimestampValidator(Duration.ofSeconds(30));
```

If building a custom validator with timestamp checking, **preserve** issuer/audience and other policies via `DelegatingOAuth2TokenValidator`. Do not call `setJwtValidator(timestamp)` and accidentally drop issuer validation.

### 5.4. When Must `iat` and TTL Be Controlled?

Suppose a system accepts access tokens living at most 10 minutes. Even if `exp` is in the future, a token claiming `exp = now + 10 years` violates policy. Because tokens must be validly signed first, that would indicate an issuer or issuance-config flaw, yet the resource server can enforce defense-in-depth: check `exp - iat <= 10 minutes`, cap clock skew, and require a valid `iat`.

**Do not allow callers to supply `iat`/`exp`** and sign tokens with the API's key; the issuer must manage this. If writing a custom TTL validator, test missing/null claims, tokens issued in the future, negative/abnormally large spans, and `Duration` subtraction overflow or unit mismatches.

## 6. Signatures: Trusted Keys, `alg`, `kid`, and JWKS

### 6.1. What Does a Signature Prove?

With JWS `RS256`, the Authorization Server signs `Base64URL(header) + "." + Base64URL(payload)` using its **RSA private key**. The Resource Server uses a **trusted public key** to verify the signature. If an attacker modifies `sub`, `aud`, or `exp` without being able to produce a matching signature using a trusted private key, the token must be rejected.

```text
Authorization Server                        Resource Server
  RSA private key (secret)                    RSA public key (trusted)
           |                                         ^
           v                                         |
     JWS signature --- JWT over HTTPS -------------> verify
                                                      |
                        ┌─────────────────────────────┤
                        |                             |
                        v                             v
                    signature OK                 signature FAIL
                        |                             |
                        v                             v
                 Validate claims                  Reject token
```

**Important:** A valid signature only asserts that the token was signed by the private key corresponding to a public key the verifier already trusts; it **does not** by itself prove issuer/audience/timestamps are right. A public key read from an arbitrary URL is **not enough** to make a token trustworthy: that URL must reside in server-controlled trust configuration.

### 6.2. The `alg` Header Must Not Decide Everything on Its Own

A JWT header may carry:

```json
{
  "alg": "RS256",
  "kid": "prod-2026-rotate-a",
  "typ": "at+jwt"
}
```

- `alg` indicates which algorithm the token requests, yet the API must enforce an **algorithm allowlist** chosen by application/issuer configuration.
- `kid` is only a **key selection hint** within the trusted key set. `kid` is neither proof of key ownership nor a URL to download. Never let a token pick a file path, SQL query, or JWKS host based on an arbitrary `kid`.
- `typ` indicates the JWT type; many access token systems use `at+jwt` per RFC 9068, whereas ID tokens have a different contract. If the system relies on a token profile, add compatible validators and tests.

**Mistakes to avoid:** accepting `alg=none`, confusing asymmetric RS256 with symmetric HS256, trusting any algorithm requested by the token, fetching public keys from a URL inside an untrusted token, rolling your own signature verification via naive string concat/compare, or treating "JSON decoded successfully" as permission to authorize.

### 6.3. What Is JWKS?

A **JSON Web Key Set (JWKS)** is the set of public keys published by an issuer for resource servers to verify JWTs. Simplified structural example:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "prod-key-1",
      "use": "sig",
      "alg": "RS256",
      "n": "BASE64URL_RSA_MODULUS",
      "e": "AQAB"
    }
  ]
}
```

The snippet above only describes structure, not a usable JWK: a real RSA modulus must be a valid value. **Public keys** may be published; **private keys must never appear in a JWKS**. Use TLS when fetching metadata/JWKS, restrict outbound network access, and trust JWKS only from the configured issuer/URL, never from data inside the token.

When an issuer rotates keys:

1. The issuer may publish the new key before beginning to sign tokens with it.
2. New tokens carry the matching `kid`.
3. The resource server refreshes its JWKS cache and verifies new tokens with the corresponding public key.
4. The old key may remain published while previously signed tokens have not yet expired, depending on the rotation process.
5. After an appropriate period, remove the old key from the trust set.

Never disable signature verification to avoid `kid not found` errors. Investigate JWKS cache, proxies, metadata, key rotation schedules, algorithm mismatches, and timeouts. When a private key is compromised, an emergency response distinct from routine rollover is required.

### 6.4. Distinguishing JWS and JWE

A JWT can be **signed** (JWS) or **encrypted** (JWE), or nested depending on design. A JWT Resource Server under this learning example's configuration verifies **signed JWS**, and does not decrypt JWE by default. A JWS payload can be read without a key. If your product needs to hide token contents from the token holder, consider limiting claims or adopting an encryption standard fit for the requirement—never call JWS an "encrypted JWT".

## 7. Concise Production Configuration with Spring Boot

### 7.1. Dependencies

Create a Spring Boot 3.x / Java 17+ application from Spring Initializr, selecting **Spring Web** and **OAuth2 Resource Server**. In a project `build.gradle` already configured with the Boot plugin/BOM, the core setup is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

The Resource Server starter pulls in the Spring Security components needed for bearer JWTs, including the appropriate JOSE library in the dependency graph. Do not override individual security library versions without checking compatibility with the Boot BOM.

### 7.2. Configuring Only Issuer and Audience

In `src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.org/realms/shop
          audiences:
            - orders-api
```

In this setup, the key source is discovered via issuer metadata (requiring the provider to expose a compatible discovery endpoint), and baseline policies are integrated by Resource Server. On Boot versions supporting the `audiences` property, tokens with a different issuer, not intended for `orders-api`, expired/not yet valid, or with invalid signatures must be rejected.

If the issuer supports JWKS yet you do not want startup metadata discovery or want to configure the exact URI, you can specify **both issuer and JWKS**:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.org/realms/shop
          jwk-set-uri: https://identity.example.org/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
```

**Do not infer that the JWKS URL above applies to every provider**; it is only an illustrative shape. Obtain the exact value from your issuer's verified documentation/metadata. **Using `jwk-set-uri` while omitting `issuer-uri` may not automatically enable issuer validation**, so keep both when explicit issuer trust management is required.

### 7.3. Configuring HTTP Security and Scopes

Java snippet for `SecurityFilterChain` (just a method inside a configuration class, **not a standalone class**):

```java
@Bean
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/ping").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll())
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .oauth2ResourceServer(oauth -> oauth.jwt(
            Customizer.withDefaults()))
        .build();
}
```

Spring Security imports: `HttpSecurity`, `SecurityFilterChain`, `Customizer`, `SessionCreationPolicy`, `HttpMethod`. Under default configuration, scope `orders.read` is typically converted into authority `SCOPE_orders.read`. This is **authorization**, layered on top of the four token checks; never use roles/scopes as a substitute for issuer/signature validation.

To build a fully stateless API, evaluate the CSRF/browser-cookie threat model, session policy, error handlers, and client architecture. Do not assume "Bearer token" means every browser flow is immune to CSRF; evaluate whether browsers automatically attach credentials. Safe GET endpoints in the example can keep the default CSRF configuration without issues.

### 7.4. Auto-Configuration vs. Custom `JwtDecoder`

When Spring Boot detects a developer-defined `JwtDecoder` bean, decoder auto-configuration may be backed off. That means properties/validators you **assumed** Boot applied automatically might no longer be active. With a custom decoder, explicitly configure issuer, audience, timestamps, and signature trust/algorithms.

Do not do this:

```java
// Illustrates a mistake only: this custom decoder does NOT
// automatically enforce policy-compliant issuer and audience checks.
@Bean
JwtDecoder decoderOnlyKey() {
    return NimbusJwtDecoder.withPublicKey(publicKey).build();
}
```

`publicKey` is undeclared here, and the snippet is not a runnable class. Checking a standalone public key can verify signatures, yet to conform to your API's policy, **claim validators must still be configured**.

## 8. Runnable Example: Verifying RSA Signatures and Four Claims Locally

This example uses **an ephemeral RSA key pair generated on each startup**, solely for quick testing **in a local environment**. The Resource Server receives the public key; tests hold the private key to sign test tokens. **Do not deploy a "service generates a fresh key pair on every startup" model in production**, because there is no independent issuer, JWKS rotation/discovery, key management, or authentication continuity across restarts.

In a Spring Boot 3.x / Java 17+ project with the dependencies from Section 7.1, create two files.

### 8.1. Spring Security Application

Place at `src/main/java/example/jwtcheck/JwtValidationDemoApplication.java`:

```java
package example.jwtcheck;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPublicKey;
import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimNames;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class JwtValidationDemoApplication {

    static final String ISSUER = "https://issuer.example.test";
    static final String AUDIENCE = "orders-api";

    public static void main(String[] args) {
        SpringApplication.run(JwtValidationDemoApplication.class, args);
    }

    @Bean
    KeyPair demoKeyPair() throws Exception {
        // Ephemeral key for local testing only; production fetches JWKS
        // from a configured and protected issuer.
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    @Bean
    JwtDecoder jwtDecoder(KeyPair demoKeyPair) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withPublicKey((RSAPublicKey) demoKeyPair.getPublic())
            .signatureAlgorithm(
                org.springframework.security.oauth2.jose.jws.SignatureAlgorithm.RS256)
            .build();

        // Includes issuer + timestamp validation by default.
        OAuth2TokenValidator<Jwt> issuerAndTimes =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        // Audience must contain exact "orders-api".
        OAuth2TokenValidator<Jwt> audience =
            new JwtClaimValidator<List<String>>(
                JwtClaimNames.AUD,
                values -> values != null && values.contains(AUDIENCE));

        // Additional policy: require exp to always be present.
        OAuth2TokenValidator<Jwt> requireExpiry =
            new JwtClaimValidator<java.time.Instant>(
                JwtClaimNames.EXP,
                value -> value != null);

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTimes, audience, requireExpiry));

        return decoder;
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/whoami")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .build();
    }
}

@RestController
class DemoController {

    @GetMapping("/public/ping")
    String ping() {
        return "ok";
    }

    @GetMapping("/api/whoami")
    Map<String, String> whoami(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
            "subject", jwt.getSubject(),
            "issuer", jwt.getIssuer().toString());
    }

    @GetMapping("/api/orders")
    String orders() {
        return "orders:allowed";
    }
}
```

**Component breakdown:**

1. `demoKeyPair()` generates a 2048-bit RSA key pair **for local demo only**. The public key goes to the decoder, while tests access the private key solely to mint test tokens. There is no token-issuing endpoint.
2. `NimbusJwtDecoder.withPublicKey(...)` verifies token signatures with the trusted public key. The builder restricts the algorithm to `RS256`.
3. `JwtValidators.createDefaultWithIssuer(ISSUER)` retains issuer and default time validators.
4. `JwtClaimValidator` for audience requires `aud` to contain exact `orders-api`.
5. `requireExpiry` is an extra rule requiring `exp` to be present, rather than relying only on the validator checking the claim when present.
6. `DelegatingOAuth2TokenValidator` aggregates the checks; **all** must pass.
7. HTTP bearer JWTs are validated by Spring Security before the controller receives `@AuthenticationPrincipal Jwt`.
8. `/api/whoami` requires only a valid token; `/api/orders` additionally requires scope `orders.read`, mapped to `SCOPE_orders.read`.

**Why not use `@WithMockUser` or `jwt()` to test signatures?** They are helpful for authorization tests, yet they typically **inject an `Authentication` directly into the security context**, bypassing real JWS/claim validators in the decoder. To prove all four checks work, you must send a **genuinely signed compact Bearer token** through the filter chain.

### 8.2. Integration Test Issuing Real JWTs with a Private Key

Place at `src/test/java/example/jwtcheck/JwtValidationDemoTest.java`:

```java
package example.jwtcheck;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class JwtValidationDemoTest {

    @Autowired MockMvc mvc;
    @Autowired KeyPair trustedKey;

    private String sign(KeyPair key, String issuer,
                        List<String> audiences,
                        Instant notBefore, Instant expiresAt,
                        String scope) {
        RSAKey jwk = new RSAKey.Builder(
                (RSAPublicKey) key.getPublic())
            .privateKey((RSAPrivateKey) key.getPrivate())
            .keyID("test-key")
            .build();

        NimbusJwtEncoder encoder = new NimbusJwtEncoder(
            new ImmutableJWKSet<>(new JWKSet(jwk)));

        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject("alice")
            .audience(audiences)
            .issuedAt(Instant.now().minusSeconds(7200))
            .notBefore(notBefore)
            .expiresAt(expiresAt)
            .claim("scope", scope)
            .build();

        JwsHeader header = JwsHeader.with(SignatureAlgorithm.RS256)
            .keyId("test-key")
            .build();

        return encoder.encode(
            JwtEncoderParameters.from(header, claims))
            .getTokenValue();
    }

    private String validToken() {
        Instant now = Instant.now();
        return sign(
            trustedKey,
            JwtValidationDemoApplication.ISSUER,
            List.of(JwtValidationDemoApplication.AUDIENCE),
            now.minusSeconds(30),
            now.plusSeconds(600),
            "orders.read");
    }

    @Test
    void validTokenPassesAllChecks() throws Exception {
        mvc.perform(get("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + validToken()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("alice"));
    }

    @Test
    void missingBearerIsRejected() throws Exception {
        mvc.perform(get("/api/whoami"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongIssuerIsRejected() throws Exception {
        Instant now = Instant.now();
        String token = sign(trustedKey,
            "https://another-issuer.example.test",
            List.of("orders-api"),
            now.minusSeconds(30), now.plusSeconds(600),
            "orders.read");

        mvc.perform(get("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongAudienceIsRejected() throws Exception {
        Instant now = Instant.now();
        String token = sign(trustedKey,
            JwtValidationDemoApplication.ISSUER,
            List.of("catalog-api"),
            now.minusSeconds(30), now.plusSeconds(600),
            "orders.read");

        mvc.perform(get("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void expiredTokenIsRejected() throws Exception {
        Instant now = Instant.now();
        String token = sign(trustedKey,
            JwtValidationDemoApplication.ISSUER,
            List.of("orders-api"),
            now.minusSeconds(7200), now.minusSeconds(3600),
            "orders.read");

        mvc.perform(get("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void notYetValidTokenIsRejected() throws Exception {
        Instant now = Instant.now();
        String token = sign(trustedKey,
            JwtValidationDemoApplication.ISSUER,
            List.of("orders-api"),
            now.plusSeconds(3600), now.plusSeconds(7200),
            "orders.read");

        mvc.perform(get("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void signatureFromUntrustedKeyIsRejected() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair attackerKey = generator.generateKeyPair();

        Instant now = Instant.now();
        // Full and VALID claims, only the signature is untrusted.
        String token = sign(attackerKey,
            JwtValidationDemoApplication.ISSUER,
            List.of("orders-api"),
            now.minusSeconds(30), now.plusSeconds(600),
            "orders.read");

        mvc.perform(get("/api/whoami")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void scopeStillControlsAuthorizationAfterValidJwt() throws Exception {
        Instant now = Instant.now();
        String noOrderScope = sign(trustedKey,
            JwtValidationDemoApplication.ISSUER,
            List.of("orders-api"),
            now.minusSeconds(30), now.plusSeconds(600),
            "profile.read");

        mvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + noOrderScope))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + validToken()))
            .andExpect(status().isOk())
            .andExpect(content().string("orders:allowed"));
    }
}
```

**Expected result when running `./gradlew test`:**

| Test | Expect | Proves |
|---|---:|---|
| Valid issuer/audience/time/signature | 200 | All four checks pass together |
| Missing Bearer | 401 | No valid authentication |
| Different issuer | 401 | `iss` check |
| Different audience | 401 | `aud` check |
| Long-expired token | 401 | `exp` beyond clock skew |
| Future `nbf` | 401 | `nbf` beyond clock skew |
| Signed by another private key | 401 | JWS and key trust check |
| Valid JWT with wrong scope | 403 | Distinguishes token authentication from authorization |

**Test invariant:** Each negative case **alters only one primary condition** relative to the valid token (aside from time fields that must remain mutually consistent), pinpointing policy failures. Tests send HTTP requests through the security filter chain without mocking the decoder. Java code does not guarantee identical behavior across all minor/patch versions; use Spring Initializr with a suitable Boot 3.x version and test inside a real project. If packages/APIs shift across versions, update per BOM/official docs; never remove validators just to make tests pass.

In the demo, `issuer.example.test` is only a signed claim string, **with no connection to an external issuer**. This is a local decoder test using a static RSA public key and does not test JWKS rotation/discovery. Those mechanisms require dedicated integration tests in a staging environment.

### 8.3. Running the Application

Inside a project with Gradle Wrapper:

```bash
./gradlew test
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat bootRun
```

When calling:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/whoami
```

Expected: the public route returns 200 with `ok`, whereas the private route without Bearer returns 401. To obtain a validly signed token for the running demo instance, you must sign with the **private key matching that exact process's `demoKeyPair` bean**; the key changes on every restart. In this learning setup, tests generate tokens from the test context's bean. A token signed by the test context cannot be used against a separately running process because their key pairs differ.

**Never commit demo private keys, real access tokens, or Bearer headers into source control, logs, screenshots, or public issues.**

## 9. Which Policy Should the Validation Suite Enforce?

A typical token validation checklist:

```text
[ ] Bearer token follows valid HTTP structure/contract
[ ] Only allowlisted JWS algorithms accepted
[ ] Key selected from server-configured JWKS/trust anchor
[ ] Signature verified with matching key
[ ] iss matches API-approved issuer
[ ] aud includes at least one valid audience for this API
[ ] exp present and not expired (within allowed clock skew)
[ ] nbf, if present, not in the future beyond tolerance
[ ] iat / maximum age if required by policy
[ ] typ / token profile matches access token type
[ ] Token not revoked / compromised per policy
[ ] scope / roles / permissions sufficient for endpoint
[ ] tenant / owner / ACL checked on the specific resource
```

Do not substitute `aud` for `scope`: audience answers **which API is the recipient**, scope answers **which capabilities were delegated**, and owner/tenant answers **which record may be accessed**.

### 9.1. Example: Three Tokens from the Same Issuer

| Token | Issuer | Audience | Scope | Accepted by `orders-api`? |
|---|---|---|---|---|
| A | Valid issuer | `orders-api` | `orders.read` | If signature/time valid: passes token validation and has read permission |
| B | Valid issuer | `catalog-api` | `orders.read` | **No**: wrong audience |
| C | Valid issuer | `orders-api` | `profile.read` | Token validation may pass; endpoint requiring `orders.read` returns **403** |

### 9.2. Multi-Environment Issuers and Tenants

A staging issuer may sign with its own key using the same token format as production. A production API must not trust a staging issuer merely because the payload contains `role=admin`. When multiple issuers are permitted, manage issuer → JWKS/trust config and audience mappings per environment; test cross-tenant/cross-environment tokens.

### 9.3. Subject and Authorized Party

The `sub` claim identifies the subject, yet does not by itself tell you "which user in this database this is" when multiple issuers exist. A durable identity key may require the `(iss, sub)` pair, not `sub` alone, to prevent two different issuers both issuing `sub=42` from colliding. Depending on the profile, `azp` or `client_id` can identify the calling application; with multiple audiences or delegation, evaluate the authorized party per the specific protocol/IdP.

### 9.4. Access Token Differs from ID Token

An **OIDC ID token** is designed to prove login results to an **OAuth/OIDC client**, typically carrying `aud` set to the **client ID**. A Resource Server API must accept **access tokens intended for the API**, never accepting an ID token merely because it is a validly signed JWT from the same issuer. If the issuer supports `typ=at+jwt`/RFC 9068, consider access-token-profile validators and explicitly design audience, `client_id`, and scope.

**Important:** An ID token's signature may be valid, `iss` valid, and timestamps valid; **audience/token type** still makes the ID token unsuitable for the API. This is a key reason never to skip `aud`.

## 10. 401 and 403: Invalid Token vs. Insufficient Permissions

| Case | Typically Returns | Cause |
|---|---|---|
| No `Authorization: Bearer ...` sent to private API | 401 | Unauthenticated |
| JWT invalid signature | 401 | Token cannot be authenticated |
| JWT wrong issuer | 401 | Untrusted issuer |
| JWT wrong audience | 401 | Not intended for this API |
| JWT expired / `nbf` not reached | 401 | Outside validity window |
| Valid JWT lacking authority for endpoint | 403 | Authenticated but unauthorized |
| Valid JWT and scope, yet object belongs to another user | 403 or 404 per policy | Object-level authorization |
| App/DB error unrelated to JWT | 5xx/4xx per error type | Do not conflate with authentication |

In OAuth2 Bearer responses, a `WWW-Authenticate` header per RFC 6750 may appear, such as `error="invalid_token"` for rejected tokens. **Never expose internal details** such as private keys, raw tokens, keystore filenames, or stack traces in responses/logs. Distinguish 401/403 by testing against your exact authentication configuration (form login may redirect instead of returning 401).

JWT is a bearer credential: anyone holding an active token can use it without additional binding/mitigation. Always use HTTPS, restrict token storage, and never pass tokens in query strings.

## 11. Do Not Just Check Four Claims and Ignore Revocation and Rotation

### 11.1. Expiration Does Not Revoke Tokens Early

A token with 30 minutes left on `exp` is not automatically invalidated immediately when the user logs out, changes password, is locked, or loses permissions. If "immediate revocation" is required, consider introspection, `jti` denylists, emergency key rotation, short token lifetimes, session coordination, and appropriate policies. Balance real-time immediacy, availability, cost, and security.

### 11.2. Key Rotation and JWKS Caching

A token with `kid=new-key` will not be recognized by the API if the JWKS cache does not yet have the new public key. Never accept unverified tokens just to avoid 401s; solve this through advance key publication, signing-key cutover, old-token lifetimes, and cache refresh. Normal key rollover differs from a compromised private key requiring immediate revocation.

### 11.3. Handling Temporary IdP/JWKS Unavailability

If an API has only `issuer-uri` and relies on discovery/JWKS fetching, when connections occur depends on Spring Security version, configuration, and caching. Do not claim every version always pings the issuer at startup or always waits until the first request. With `issuer-uri + jwk-set-uri`, some discovery steps can be bypassed, though key fetching/refreshing is still needed later. Configure bounded timeouts, limited retry policies, error monitoring, and **fail-closed** fallback: never disable signature validation or trust unknown keys.

### 11.4. JWT Validators Do Not Replace Business Logic Controls

For example, a buyer has `SCOPE_orders.read` and audience `orders-api`, yet attempts `GET /api/orders/999` belonging to another tenant. A valid token still does not grant permission to read order 999. Services/repositories must enforce tenant, owner, ACL, and field-level authorization against trusted data, not just look at role claims.

## 12. Common Misconceptions and Implementation Pitfalls

| Mistake | Consequence | Fix |
|---|---|---|
| "Base64URL decoding is JWT validation." | Trusting attacker-forged claims | Use `JwtDecoder` with signature + validators |
| "Valid signature means valid for every API." | Token substitution across services | Validate `aud` for the current API |
| "Presence of `iss` means right issuer." | Tokens from foreign issuers accepted | Exact match against trusted issuer allowlist |
| "Having `issuer-uri` means audience is checked automatically." | Tokens from same issuer for another API slip through | Configure `audiences` or custom validator |
| "Any key matching `kid` works." | Trusting attacker-chosen keys | Select keys only from configured JWKS/trust anchor |
| "Verify with whatever `alg` the token specifies." | Algorithm confusion / `none` attack | Restrict to server-approved algorithms |
| "JWT cannot be read because it has a signature." | Payload data exposure | Do not put secrets in JWT; JWS is not JWE |
| "`exp` passed 1 second ago and still works, so it's broken." | Ignoring clock skew | Understand leeway; test well outside boundary |
| "Token has `iat` so `exp` isn't needed." | Unbounded token lifetime | Require `exp` and validate expiration |
| "Custom decoder still uses all Boot properties automatically." | Drops issuer/audience checks | Register full validators on the bean |
| "MockMvc `jwt()` proves signature checking." | Test bypasses real decoder | Send genuinely signed tokens in Bearer header |
| "401 for every missing permission is right." | Blurs authentication vs. authorization | Use 401 for invalid token, 403 for insufficient scope |
| "Validly signed ID token can call APIs." | Confusing OIDC client token with access token | Check audience/token type/profile |
| "Log full JWTs for debugging." | Leaking bearer credentials | Redact headers/tokens, log trace IDs |
| "Valid JWT means any record can be read." | IDOR/BOLA, cross-tenant breach | Enforce resource-level permissions |

## 13. High-Value CI Test Matrix

In addition to the tests in Section 8, include cases aligned with production policy:

1. **Positive:** issuer, audience, signature, timestamps, and scope all match; API returns valid response.
2. **Signature mismatch:** same claims, signed with a private key not accepted by the issuer → 401.
3. **Modified payload:** alter one character in payload after signing so signature no longer matches → 401.
4. **`alg=none` and unexpected algorithms:** must be rejected when API only trusts RS256.
5. **Unknown `kid`:** trust only keys in configured JWKS, never fetch keys from attacker-requested locations.
6. **Wrong issuer:** staging issuer or token from another IdP → 401.
7. **Wrong audience:** token for another API → 401 even when all other claims match.
8. **Missing audience:** if contract requires `aud`, must reject.
9. **Expiration:** long expired → 401; boundary timestamps tested per policy clock skew.
10. **Not before:** token active only one hour in the future → 401.
11. **Missing expiration:** if contract requires `exp`, custom policy must block.
12. **Issued-at:** depending on threat model, test future `iat` or overly old tokens.
13. **Valid JWT missing scope:** 403 on endpoints guarded by `hasAuthority`.
14. **Valid scope but wrong object:** 403/404 in service/repository.
15. **Multi-issuer:** key/issuer/audience must match corresponding trust config without mixing stage/prod.
16. **JWKS rotation:** tokens signed with old/new keys accepted or rejected appropriately during transition.
17. **Auth provider outage:** unvalidatable requests fail closed and return safe errors; never skip validation.
18. **Unauthorized logs:** contain no raw Bearer tokens, JWT signatures, or secrets; metrics emit appropriate signals.
19. **ID token as access token:** OIDC token with wrong audience/type rejected.
20. **Timeout/retry/clock drift:** bounded configurations; never widen lifetimes indefinitely to mask infrastructure issues.

Separate **unit tests** for policy (audience, claim shape, TTL), **integration tests** traversing `BearerTokenAuthenticationFilter` with genuinely signed tokens, and **staging tests** against real issuer/JWKS/token rotation. A single test layer does not prove the entire system.

## 14. Code Review Checklist

- [ ] Defined which issuers, audiences, and algorithms this API accepts for access tokens.
- [ ] Issuer URI comes from a trusted source and matches exactly; never blindly trust hosts from `iss` claims.
- [ ] JWKS URL/public keys are managed under trust configuration; only allowed `kid` and `alg` values are accepted.
- [ ] JWT signature is verified; claims are never decoded and used without verification.
- [ ] `aud` is explicitly checked, never confusing audience with scope or subject.
- [ ] `exp`/`nbf` are validated with appropriate clock skew; `exp` is mandatory if policy requires it.
- [ ] If `iat`/TTL/`typ`/`azp` policies exist, validators are enforced and tested.
- [ ] Custom `JwtDecoder` preserves full validators when overriding auto-configuration.
- [ ] Scopes map accurately to authorities, e.g., `SCOPE_orders.read`.
- [ ] Endpoints still enforce HTTP/method/object/tenant permissions; a valid JWT does not permit all operations.
- [ ] Login/ID tokens and access tokens are never mixed, especially from the same issuer.
- [ ] Client-supplied forwarded Host/issuer/JWKS URLs are not trusted.
- [ ] Auth fails closed; signature/issuer validation is never disabled to "fix a 401 error".
- [ ] Operational procedures exist for rotation, revocation, caching, retries, timeouts, NTP, and key compromise.
- [ ] Negative tests use **genuinely signed** tokens, not only mocked `Authentication`.
- [ ] Tokens, private keys, or sensitive claims are never logged; communication uses HTTPS.

## 15. Self-Check Exercises

**Question 1.** A token has a valid RSA signature, `iss=https://identity.example.org`, future `exp`, but `aud=["catalog-api"]`. Should `orders-api` accept it?

**Answer:** No. The token is not intended for `orders-api`; valid signature/issuer/expiration do not substitute for audience validation.

**Question 2.** You Base64URL-decode a JWT and see `"role":"ADMIN"`. Can you trust it yet?

**Answer:** Not yet. The payload is readable without a secret, so anyone can craft it. You must verify the signature with a trusted key, issuer/audience/time, and role/authority mapping.

**Question 3.** A token has the right `iss` and `aud`, yet was signed with an attacker-generated private key. What happens?

**Answer:** Rejected because the signature does not verify against a public key trusted by the resource server. Self-declared `kid` or `iss` does not make an unknown key valid.

**Question 4.** A JWT's `exp` passed 5 seconds ago yet the API still accepts it. Is the validator definitely disabled?

**Answer:** Not necessarily. `JwtTimestampValidator` may allow a clock skew window. Check your policy and test a long-expired token to tell them apart.

**Question 5.** Why might `issuer-uri` alone be insufficient to protect two APIs sharing the same issuer?

**Answer:** It identifies the issuer and sets up signature/time validation, but APIs A and B need distinct audiences. Without `aud`, a token for API A can be used on API B.

**Question 6.** A valid token has `scope=orders.read` and is used to read Bob's order. Is it definitely permitted?

**Answer:** No. `scope` indicates general capability; the API must still check owner, tenant, and membership/ACL for the specific order.

**Question 7.** In MockMvc, a test uses `jwt()` and expects 200. Does that prove the RSA signature is valid?

**Answer:** No. `jwt()` mainly builds an `Authentication` to test authorization; it does not run real signing/verification in the decoder. Send a signed compact JWT via `Authorization: Bearer ...` to test cryptography and validators.

**Question 8.** Should you call `jwtDecoder.setJwtValidator(audienceValidator)` to enable audience checking if the decoder previously checked issuer/timestamps?

**Answer:** Do not replace it alone. `setJwtValidator` sets a new validator; use `DelegatingOAuth2TokenValidator` to combine issuer/timestamp checks with audience and other constraints.

## 16. Official References

- [Spring Security 6.5 — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): `issuer-uri`, JWKS, trusted algorithms, audience, `exp`/`nbf`, custom JWT validators, and scope mapping.
- [Spring Security — OAuth2 Resource Server JWT (current reference)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): current API and behavior documentation.
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `jwt()` testing, mocking `Authentication`, and distinguishing from sending real Bearer tokens.
- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): reference when using WebFlux/`ReactiveJwtDecoder`.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): defines registered claims `iss`, `aud`, `exp`, `nbf`, and `iat`.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JWS signatures, protected headers, and compact serialization.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): public key representation, `kid`, and JWK Sets.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): constraints when using JWTs as OAuth access tokens.
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `Authorization: Bearer` and authentication error semantics.

**Conclusion:** A JWT is accepted by a resource server only when it **is signed by a trusted key using an allowed algorithm**, **comes from an approved issuer**, **targets the API's audience**, and **is within its validity window**. Even then, scopes, business permissions, and data-level permissions must be checked. With Spring Security, prefer Resource Server + `issuer-uri` + `audiences`; if customizing `JwtDecoder`, actively retain all validators and test with genuinely signed JWTs, including negative cases.
