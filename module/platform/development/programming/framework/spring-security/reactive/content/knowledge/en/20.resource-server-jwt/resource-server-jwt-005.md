# Verifying Signatures and Validating iss, exp, nbf, aud in Spring Security Reactive Resource Server JWT

> **Module:** Spring Security - reactive  
> **Parent topic:** Resource Server JWT  
> **Lesson:** Verifying signatures and validating `iss`, `exp`, `nbf`, `aud`  
> **Goal:** Understand the difference between *reading* a JWT and *authenticating* a JWT; configure decoders/validators properly in Spring WebFlux; reject forged, wrong-issuer, expired, premature, and wrong-audience tokens; practice with Java 17+ and test using a real RSA-signed key pair.

## 1. From a JWT to an Access Decision

A JWT typically has the form `header.payload.signature`, where header and payload are Base64URL-encoded, **not confidentially encrypted**. Anyone can decode the first two segments. Thus seeing `"role":"admin"` or `"sub":"alice"` in the payload does not mean the sender actually holds that privilege.

Example payload:

~~~json
{
  "iss": "https://idp.example.com/realms/acme",
  "sub": "user-42",
  "aud": ["reports-api"],
  "iat": 1762500000,
  "nbf": 1762500000,
  "exp": 1762503600,
  "scope": "reports.read"
}
~~~

Timestamps in the example only illustrate **Unix seconds**, not a token still valid on the day you read this. The Resource Server must decide based on the **current clock**, configured issuer/audience, and signature verified with a trusted key.

A JWT is accepted only when all relevant conditions hold:

~~~text
Accept request only if:
  (1) Bearer token has valid syntax
  (2) JWS signature is valid against trusted public key
  (3) alg is allowlisted and not alg=none
  (4) iss matches trusted issuer
  (5) exp is still valid within policy/clock skew
  (6) nbf is not in the future beyond skew (if present)
  (7) aud contains the exact ID of the current API
  (8) scope/role suffices for the route, owner/tenant rights suffice for the object
Otherwise: fail closed
~~~

A valid signature where `aud` is another service must still be rejected. An invalid signature whose payload has every nice claim must also be rejected.

## 2. Roles of Authorization Server, Client, and Resource Server

~~~mermaid
flowchart TD
    I["Trusted Authorization Server / IdP"] -->|"Signs access token with private key"| C["Client"]
    I -->|"Publishes JWKS public keys"| R["WebFlux Resource Server"]
    C -->|"Authorization: Bearer access-token"| R
    R --> D{"Verify JWS signature + alg?"}
    D -->|"No"| X["401 invalid_token"]
    D -->|"Yes"| V{"iss + exp + nbf + aud valid?"}
    V -->|"No"| X
    V -->|"Yes"| A["JwtAuthenticationToken + GrantedAuthorities"]
    A --> P{"Scope / owner / tenant authorized?"}
    P -->|"No"| F["403 or 404 hiding object, per API policy"]
    P -->|"Yes"| H["Controller / domain service"]
~~~

- **Authorization Server** holds the private signing key; may publish public keys via JSON Web Key Set (JWKS).
- **Client** obtains an access token via an appropriate OAuth2 flow and sends it to the resource server over HTTPS.
- **Resource Server** verifies the JWT, issuer, timestamps, audience, and authorization. It **does not sign/issue tokens** just because `oauth2ResourceServer().jwt()` is enabled.
- **Authentication** answers whether the token can represent a valid subject for the API. **Authorization** answers what that subject may do and on which objects.

Do not confuse an OAuth2 Login Client (browser redirect, WebSession) with a JWT Resource Server (receives Bearer per request). Also do not use an OIDC ID Token as an access token: an ID Token's audience targets the OIDC client, not necessarily your API.

## 3. JWT, JWS, JWE, alg, and kid

| Term | Meaning | Consequence |
| --- | --- | --- |
| JWT | Claim set format | Does not by itself guarantee the token is signed |
| JWS | JSON Web Signature | Has protected header, payload, signature |
| JWE | JSON Web Encryption | Payload is encrypted; this example does not decrypt JWE |
| `alg` | JWS algorithm, e.g. RS256 | Only accept server-allowlisted algorithms |
| `kid` | Key identifier | Helps look up keys in a **trusted** JWKS |
| `typ` | Token type in header | May need access-token profile validation |
| `iss` | Issuer | Must belong to a trusted issuer and match exactly |
| `aud` | Audience | Must include this resource server API |
| `scope`/`scp` | Action permissions | Typically mapped to `SCOPE_...` authorities |

The JWT header is also **caller input prior to verification**. Never trust a key fetched from an arbitrary URL just because the token says `kid=abc`. Never use `jku`/`x5u` in a token as an HTTP address to auto-fetch public keys, as an attacker can force the server to contact private or internal hosts (SSRF).

## 4. Signature Verification: Trusted Public Key, Not the Payload

With `RS256`, the IdP signs the JWS with an RSA private key; the Resource Server verifies with the corresponding RSA public key.

~~~text
IdP: base64url(header) + "." + base64url(payload)
                       |
                 RS256 private key
                       |
                  JWS signature
                       |
             header.payload.signature

Resource Server: header.payload + signature
                        |
              trusted public key (JWKS)
                        |
            Verify signature and allowed alg
                        |
            Pass or reject before trusting claims
~~~

The receiver **does not need the IdP's private key**. Never copy private signing keys into the Resource Server or Git. When `alg` specifies `none`, an unsigned token would pass without a signature; it must be rejected under mandatory signing policies. When the IdP moves from RS256 to ES256/PS256, update the allowlist based on the IdP contract and test; never let the token pick any algorithm it wants.

**Algorithm confusion:** If an application hand-rolls signature verification code and mistakes an RSA public key for an HMAC secret, a vulnerability accepting forged tokens can arise. Use maintained JOSE/JWT libraries and pin allowed algorithms appropriately.

## 5. JWKS, kid, and Key Rotation

JWKS is a JSON document containing a list of public JWKs, illustrative structure:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "illustrative-rsa-modulus",
      "e": "AQAB"
    }
  ]
}
~~~

The `n` string above is illustrative only; it is not a real public key usable for verification. In real applications, JWKS is published by a trusted IdP over **HTTPS** with algorithm-appropriate key material.

The decoder uses `kid` (when present) to choose the matching key from the trusted key set, verifies the JWS signature, and only then validates claims. During key rotation, the IdP may publish both old and new public keys for a period so unexpired JWTs continue to verify. Nimbus/Spring manages retrieval/caching per configuration and version; do not assume a fixed TTL without checking.

Cases that must **fail closed**: untrusted JWKS URI; invalid TLS certificate; `kid` with no matching key; bad signature; mismatched key type/alg; JWKS outage when the decoder lacks the required trusted key. Never fall back to unverified decoding.

## 6. Validating iss — The Right Issuer

`iss` indicates the JWT issuer, e.g. `https://idp.example.com/realms/acme`. The Resource Server must compare against the trusted configuration value, **not substring matching**. Two issuers with different paths/tenants may share a hostname yet are **not** equivalent.

| Token iss | Trusted issuer | Result |
| --- | --- | --- |
| `https://idp.example.com/realms/acme` | Same URI | May proceed |
| `https://idp.example.com/realms/other` | acme | Reject |
| `http://idp.example.com/realms/acme` | https | Reject |
| Missing iss | acme | Rejected by issuer validator |

In Spring Security, `JwtValidators.createDefaultWithIssuer(issuer)` provides issuer validation combined with default timestamp validation. If you declare a custom `ReactiveJwtDecoder` Bean from a JWKS URI without attaching an issuer validator, do not assume Boot will inject an issuer check into your custom Bean.

**Multi-issuer:** never take an unverified `iss` string and automatically download metadata/JWKS from that URL. Use an organization-approved issuer allowlist mapping exact issuer → decoder to prevent SSRF and token mix-up.

## 7. Validating exp — Expiration Time

`exp` is a NumericDate (Unix seconds) indicating when a JWT **is no longer acceptable**, optionally applying a small leeway/clock skew to tolerate minor clock drift.

~~~text
server time: 12:00 UTC
exp:         11:45 UTC   => expired, reject
exp:         12:10 UTC   => still valid, continue checking other claims
~~~

Spring Security uses `JwtTimestampValidator` with a small default clock skew (documented as typically 60 seconds). Skew is not a license to accept tokens expired by many minutes or hours. Keep nodes/IdP synchronized via NTP instead of widening skew excessively to mask errors.

**The JWT RFC treats `exp` as optional**, though an API may adopt a policy requiring tokens to have an expiration. This lab adds `ExpirationRequiredValidator` to reject tokens missing `exp` — an explicit hardening policy, not a claim that the JWT specification mandates `exp` on every token.

Do not confuse `iat` (issued at) with `exp`. A token with a recent `iat` must still be rejected if signature/issuer/aud fail.

## 8. Validating nbf — Not-Before Time

`nbf` (“not before”) specifies the time **before which the token must not be accepted**. For example, if it is now 12:00 UTC and `nbf` is 13:00 UTC, the decoder must reject even if `exp` is 14:00 UTC and the signature is valid.

| Server now | nbf | Handling |
| --- | --- | --- |
| 12:00 | 11:50 | Active |
| 12:00 | 13:00 | Not yet valid, reject |
| 12:00 | Claim absent | Allowed by RFC; if profile requires it, add custom presence validator |

The JWT RFC does not require `nbf` in every token. The lab uses the default timestamp validator which **evaluates `nbf` when present**, without requiring the claim to be present. Any system mandating `nbf` must write an explicit presence validator and test missing `nbf`.

**Do not swap `nbf` and `exp`:** `nbf` is the lower bound and `exp` is the upper bound of the validity window. Future-dated tokens or clock skew mismatches can cause 401s on some nodes; check server time and issuer time before relaxing security policies.

## 9. Validating aud — Right API Target

`aud` identifies the resource/API intended to receive the token; in JSON it can be a string or an array, and Spring's JWT API typically exposes `jwt.getAudience()` as a list.

Example:

~~~json
{
  "iss": "https://idp.example.com/realms/acme",
  "aud": ["reports-api", "analytics-api"],
  "scope": "reports.read"
}
~~~

If the current API has ID `reports-api`, the token can pass audience validation. If the audience is only `billing-api`, it must be rejected, even if both APIs share the same issuer and the signature is valid.

**Right policy:** use *exact membership* comparison `jwt.getAudience().contains("reports-api")`. Do not use substring matching like `aud.contains("report")`; do not read the expected audience from request headers; do not skip `aud` because the token “was signed by our trusted IdP”.

**Audience differs from scope:** `aud` states **who it is for**; `scope` states **what is allowed**. A token with the right `aud` lacking `reports.read` typically receives 403 on a route requiring `SCOPE_reports.read`. A token with the wrong `aud` receives 401 from authentication and should not reach the authorization layer.

## 10. Request Processing Order in Spring Security Reactive

~~~mermaid
sequenceDiagram
    participant Client
    participant Security as WebFlux Security
    participant Decoder as NimbusReactiveJwtDecoder
    participant JWKS as Trusted JWKS
    participant Controller
    Client->>Security: GET /api/reports + Authorization Bearer
    Security->>Decoder: decode(token)
    Decoder->>JWKS: Fetch/cache keys when needed
    JWKS-->>Decoder: Trusted public JWK set
    Decoder->>Decoder: Verify signature & algorithm
    Decoder->>Decoder: Validate iss/exp/nbf/aud
    alt invalid
        Decoder-->>Security: JwtException
        Security-->>Client: 401 invalid_token
    else valid
        Decoder-->>Security: Jwt verified
        Security->>Security: Map scope to SCOPE_...
        alt insufficient scope
            Security-->>Client: 403 forbidden
        else allowed
            Security->>Controller: @AuthenticationPrincipal Jwt
            Controller-->>Client: 200 JSON
        end
    end
~~~

API names:
- `ServerBearerTokenAuthenticationConverter` extracts the Bearer token from the HTTP request.
- `JwtReactiveAuthenticationManager` invokes `ReactiveJwtDecoder`.
- `NimbusReactiveJwtDecoder` verifies JWS and decodes claims.
- `JwtValidators` + `OAuth2TokenValidator<Jwt>` validate conditions.
- `JwtAuthenticationToken` represents Authentication upon success.
- `ReactiveJwtAuthenticationConverter` and default authority mapping can convert scopes to `SCOPE_...`.

Do not let controllers inspect a raw Base64-decoded JWT payload to grant permissions. Only use the `Jwt` produced by the decoder/validators or the framework-verified Authentication.

## 11. Quick Configuration with Spring Boot Properties

When the IdP supports issuer discovery, minimal config:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/acme
~~~

Spring Security Reactive can discover JWKS and verify signature, issuer, and timestamps. **Do not assume the API's `aud` is automatically checked** across all versions/configs solely from `issuer-uri`. Use Boot's `audiences` property if supported by your version, or a custom audience validator.

To specify the JWKS URI via config and avoid network discovery at startup in applicable setups:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/acme
          jwk-set-uri: https://idp.example.com/realms/acme/protocol/openid-connect/certs
~~~

Real configuration must take the exact trusted issuer/JWKS from the IdP documentation, use HTTPS, and enforce an audience policy. If you write a custom decoder Bean, Boot's property-based auto-configured Bean may be overridden; preserve issuer/aud/time validators in code.

## 12. Java 17+ / Maven Project

This lab uses Spring Boot `3.3.13` as a baseline illustrating Spring Security 6.x. Boot 3.3 has reached end of OSS support, so new production systems must upgrade to a supported release and re-run tests. The example includes a WebFlux Resource Server app and two kinds of tests:

~~~text
jwt-validation-reactive/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/jwt/
    │   │   ├── JwtApplication.java
    │   │   ├── JwtSecurityConfig.java
    │   │   └── ReportsController.java
    │   └── resources/application.yml
    └── test/java/demo/jwt/
        ├── JwtCryptographicTest.java
        └── JwtRouteTest.java
~~~

### 12.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>jwt-validation-reactive</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Choose `spring-boot-starter-oauth2-resource-server` to accept Bearer/JWT, not the OAuth2 Login starter. Do not add `spring-boot-starter-web` because this is WebFlux, not Servlet MVC.

### 12.2. JwtApplication.java

~~~java
package demo.jwt;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JwtApplication {
    public static void main(String[] args) {
        SpringApplication.run(JwtApplication.class, args);
    }
}
~~~

### 12.3. application.yml

~~~yaml
server:
  port: 8080

lab:
  jwt:
    issuer: ${JWT_ISSUER:https://issuer.example.invalid/realms/demo}
    jwks-uri: ${JWT_JWKS_URI:https://issuer.example.invalid/realms/demo/protocol/openid-connect/certs}
    audience: ${JWT_AUDIENCE:reports-api}
~~~

`.invalid` is a placeholder **with no real server**. The unit tests use an internal RSA key pair and WebTestClient mock authentication, so no IdP contact is needed. To use real HTTP Bearer tokens, set `JWT_ISSUER`, `JWT_JWKS_URI`, and `JWT_AUDIENCE` for your IdP and Resource Server.

Never allow callers to pass a JWKS URL or issuer for the decoder to call over the network.

## 13. JwtSecurityConfig.java — signature, iss, exp, nbf, aud

File `src/main/java/demo/jwt/JwtSecurityConfig.java`:

~~~java
package demo.jwt;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class JwtSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public/health").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/me").authenticated()
                .pathMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .requestCache(ServerHttpSecurity.RequestCacheSpec::disable)
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
    }

    @Bean
    ReactiveJwtDecoder jwtDecoder(
            @Value("${lab.jwt.issuer}") String issuer,
            @Value("${lab.jwt.jwks-uri}") String jwksUri,
            @Value("${lab.jwt.audience}") String audience) {

        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withJwkSetUri(jwksUri)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> validator =
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                new AudienceValidator(audience),
                new ExpirationRequiredValidator()
            );
        decoder.setJwtValidator(validator);
        return decoder;
    }
}

final class AudienceValidator implements OAuth2TokenValidator<Jwt> {
    private final String expected;

    AudienceValidator(String expected) {
        this.expected = expected;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getAudience() != null
                && jwt.getAudience().contains(expected)) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token", "Wrong JWT audience", null));
    }
}

final class ExpirationRequiredValidator
        implements OAuth2TokenValidator<Jwt> {

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getExpiresAt() != null) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token", "exp is required", null));
    }
}
~~~

**Why is it configured this way?**

1. `withJwkSetUri(jwksUri)` fetches public keys from an **admin-approved** JWKS, not from arbitrary JWTs. IdP signing still uses the private key at the IdP.
2. `jwsAlgorithm(SignatureAlgorithm.RS256)` pins the signing algorithm per the test contract. If a real IdP uses ES256/PS256, update the allowlist accordingly and test.
3. `JwtValidators.createDefaultWithIssuer(issuer)` validates the exact issuer and `exp`/`nbf` timestamps.
4. `AudienceValidator` adds `aud` checking because the API must only accept tokens **intended for reports-api**.
5. `ExpirationRequiredValidator` is an API-specific requirement: reject tokens lacking `exp`. In the JWT RFC, `exp` is optional; this lab intentionally enforces a stricter policy.
6. `nbf` is not required to be present, but if present, the timestamp validator must check not-before and clock skew.
7. `NoOpServerSecurityContextRepository` and disabling form login/HTTP Basic make this a **header-only JWT API**, not relying on `WebSession` cookies for authentication.
8. Disabling CSRF is **only appropriate for a header-only Bearer API that accepts no browser auto-sent credentials**. If an API uses cookie JWTs/sessions/Basic in the same chain, revisit the CSRF policy.
9. `hasAuthority("SCOPE_reports.read")` only checks route permissions, not owner/tenant checks.
10. `anyExchange().denyAll()` blocks undeclared routes.

**Common pitfall:** If you define your own `ReactiveJwtDecoder` Bean, do not assume Boot defaults still apply automatically afterward. Explicitly compose issuer/timestamp/audience policies in code and write negative tests.

## 14. ReportsController.java — Reading Only the Verified Subject

File `src/main/java/demo/jwt/ReportsController.java`:

~~~java
package demo.jwt;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReportsController {

    @GetMapping("/public/health")
    public Mono<Map<String, String>> health() {
        return Mono.just(Map.of("status", "up"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            @AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of("subject", jwt.getSubject()));
    }

    @GetMapping("/api/reports")
    public Mono<Map<String, String>> reports() {
        return Mono.just(Map.of(
            "report", "Visible to reports.read scope"));
    }
}
~~~

When the access token has valid issuer/times/audience/signature and sufficient scope, `GET /api/reports` returns JSON with a `report` key. The controller does **not** accept a raw JWT for manual parsing. Never log or return `jwt.getTokenValue()` in JSON. With real data, add owner, tenant, domain policy, and database authorization checks to prevent BOLA/IDOR.

## 15. Two Required Test Types That Cannot Replace Each Other

**Group A — cryptographic/claims tests:** generate an ephemeral RSA key pair, sign real JWTs with `NimbusJwtEncoder`, decode/verify with `NimbusReactiveJwtDecoder.withPublicKey(...)`. Test both valid tokens and forged signatures; test **wrong issuer, expired, future nbf, wrong/missing aud, missing exp**. Requires no IdP or HTTP network.

**Group B — WebTestClient security tests:** use `mockJwt()` to confirm routes return 401/403/200 with or without Authentication and scopes. These are authorization tests that **do not invoke the JWT decoder**; never use `mockJwt` to claim signature, `exp`, `nbf`, `iss`, or `aud` have been verified.

Group A uses a pinned test public key; production uses JWKS. A third integration test type is needed to prove JWKS retrieval/rotation over HTTPS. This lesson states these boundaries clearly without blurring test evidence.

## 16. JwtCryptographicTest.java — Signing JWTs with Test RSA Keys

File `src/test/java/demo/jwt/JwtCryptographicTest.java`:

~~~java
package demo.jwt;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import reactor.test.StepVerifier;

class JwtCryptographicTest {
    static final String ISSUER =
        "https://idp.example.invalid/realms/demo";
    static final String AUDIENCE = "reports-api";

    private JwtEncoder encoder;
    private NimbusReactiveJwtDecoder decoder;

    private KeyPair keyPair() throws Exception {
        KeyPairGenerator g = KeyPairGenerator.getInstance("RSA");
        g.initialize(2048);
        return g.generateKeyPair();
    }

    private JwtEncoder encoderFor(KeyPair pair) {
        RSAKey signingKey =
            new RSAKey.Builder((RSAPublicKey) pair.getPublic())
                .privateKey((RSAPrivateKey) pair.getPrivate())
                .keyID("test-key")
                .build();

        JWKSource<SecurityContext> source =
            new ImmutableJWKSet<>(new JWKSet(signingKey));

        return new NimbusJwtEncoder(source);
    }

    @BeforeEach
    void setUp() throws Exception {
        KeyPair trustedKeys = keyPair();
        encoder = encoderFor(trustedKeys);
        decoder = NimbusReactiveJwtDecoder
            .withPublicKey((RSAPublicKey) trustedKeys.getPublic())
            .build();

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                new AudienceValidator(AUDIENCE),
                new ExpirationRequiredValidator()));
    }

    private String signed(
            JwtEncoder signingEncoder,
            String issuer,
            List<String> audience,
            Instant notBefore,
            Instant expiresAt) {

        Instant now = Instant.now();
        Instant issuedAt =
            expiresAt != null && expiresAt.isBefore(now)
                ? now.minusSeconds(7200)
                : now;

        JwtClaimsSet.Builder claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject("alice")
            .audience(audience)
            .issuedAt(issuedAt)
            .claim("scope", "reports.read");

        if (notBefore != null) {
            claims.notBefore(notBefore);
        }
        if (expiresAt != null) {
            claims.expiresAt(expiresAt);
        }

        JwsHeader header = JwsHeader
            .with(SignatureAlgorithm.RS256)
            .keyId("test-key")
            .build();

        return signingEncoder.encode(
            JwtEncoderParameters.from(header, claims.build()))
            .getTokenValue();
    }

    private String validToken() {
        Instant now = Instant.now();
        return signed(encoder, ISSUER, List.of(AUDIENCE),
            now.minusSeconds(10), now.plusSeconds(600));
    }

    @Test
    void validSignatureAndAllClaimsPass() {
        StepVerifier.create(decoder.decode(validToken()))
            .assertNext(jwt -> {
                assertEquals("alice", jwt.getSubject());
                assertEquals(ISSUER, jwt.getIssuer().toString());
                assertTrue(jwt.getAudience().contains(AUDIENCE));
            })
            .verifyComplete();
    }

    @Test
    void signatureFromDifferentPrivateKeyFails() throws Exception {
        JwtEncoder attacker = encoderFor(keyPair());
        Instant now = Instant.now();
        String forged = signed(attacker, ISSUER, List.of(AUDIENCE),
            now.minusSeconds(10), now.plusSeconds(600));

        StepVerifier.create(decoder.decode(forged))
            .expectError(JwtException.class)
            .verify();
    }

    @Test
    void wrongIssuerFailsWithValidSignature() {
        Instant now = Instant.now();
        String bad = signed(encoder,
            "https://idp.example.invalid/realms/another",
            List.of(AUDIENCE),
            now.minusSeconds(10), now.plusSeconds(600));

        StepVerifier.create(decoder.decode(bad))
            .expectError(JwtException.class)
            .verify();
    }

    @Test
    void expiredTokenFailsWithValidSignature() {
        Instant now = Instant.now();
        String expired = signed(encoder, ISSUER, List.of(AUDIENCE),
            now.minusSeconds(7100), now.minusSeconds(600));

        StepVerifier.create(decoder.decode(expired))
            .expectError(JwtException.class)
            .verify();
    }

    @Test
    void futureNbfFailsWithValidSignature() {
        Instant now = Instant.now();
        String premature = signed(encoder, ISSUER, List.of(AUDIENCE),
            now.plusSeconds(3600), now.plusSeconds(7200));

        StepVerifier.create(decoder.decode(premature))
            .expectError(JwtException.class)
            .verify();
    }

    @Test
    void wrongAudienceFailsWithValidSignature() {
        Instant now = Instant.now();
        String bad = signed(encoder, ISSUER, List.of("billing-api"),
            now.minusSeconds(10), now.plusSeconds(600));

        StepVerifier.create(decoder.decode(bad))
            .expectError(JwtException.class)
            .verify();
    }

    @Test
    void absentAudienceFails() {
        Instant now = Instant.now();
        String bad = signed(encoder, ISSUER, List.of(),
            now.minusSeconds(10), now.plusSeconds(600));

        StepVerifier.create(decoder.decode(bad))
            .expectError(JwtException.class)
            .verify();
    }

    @Test
    void missingExpirationFailsUnderLabPolicy() {
        Instant now = Instant.now();
        String bad = signed(encoder, ISSUER, List.of(AUDIENCE),
            now.minusSeconds(10), null);

        StepVerifier.create(decoder.decode(bad))
            .expectError(JwtException.class)
            .verify();
    }
}
~~~

**Key takeaways from the 8 tests:**
- Another private key cannot forge a token with valid claims; the signature must match the **trusted public key**.
- A token signed with the right private key is still rejected if `iss`/`aud`/`exp`/`nbf` violate policy.
- Tokens missing `exp` are blocked by the additional policy.
- Test key pairs are randomly generated, load no JWKS, and use no real IdP private keys.

**Note:** test timestamps are separated by hundreds or thousands of seconds to avoid flakiness around the 60-second clock skew. Do not write `exp` within milliseconds of `Instant.now()` and assert deterministic outcomes.

## 17. JwtRouteTest.java — WebFlux Authentication and Scopes

File `src/test/java/demo/jwt/JwtRouteTest.java`:

~~~java
package demo.jwt;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class JwtRouteTest {

    @Autowired
    WebTestClient client;

    @Test
    void healthIsPublic() {
        client.get().uri("/public/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("up");
    }

    @Test
    void missingBearerGets401() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void mockedJwtPrincipalMayReadProfile() {
        client.mutateWith(mockJwt().jwt(jwt ->
                jwt.subject("alice")))
            .get().uri("/api/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.subject").isEqualTo("alice")
            .jsonPath("$.access_token").doesNotExist();
    }

    @Test
    void wrongScopeGets403() {
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_profile")))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void reportsReadScopeGets200() {
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read")))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.report").exists();
    }

    @Test
    void unknownRouteIsDenied() {
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read")))
            .get().uri("/api/admin/debug")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

**These six tests check only HTTP security:** public route, 401 when token is missing, mock principal, 403 when scope is missing, 200 with right scope, and deny unknown routes.

`mockJwt()` creates an Authentication for `WebTestClient` **without calling ReactiveJwtDecoder**. A `mockJwt` in a test could have `alg=none` and still be granted Authentication due to the mocking mechanism; this does **not** prove the production decoder accepts unsigned JWTs. To test signatures/claims, use real signed JWTs and the decoder as in Section 16.

## 18. Running Maven and Observing HTTP

In the directory containing `pom.xml`:

~~~bash
mvn clean test
~~~

The example suite has **8 cryptographic tests + 6 HTTP security tests = 14 JUnit tests**. They are expected to run under Java 17+ with Spring Boot 3.3.13 when dependencies work properly. There is no fixed business stdout; Maven/JUnit reports vary by environment. This lesson does not claim to have run Maven on the reader's machine.

Start the application:

~~~bash
mvn spring-boot:run
~~~

Public request:

~~~bash
curl -i "http://localhost:8080/public/health"
~~~

Expected JSON body:

~~~json
{"status":"up"}
~~~

Private request missing token:

~~~bash
curl -i "http://localhost:8080/api/reports"
~~~

Expect **401**, since it is unauthenticated. With `.invalid` configured in YAML, real JWTs **cannot** be verified via online JWKS; only unit/mock tests work offline. For end-to-end testing, substitute the real issuer/JWKS/audience and obtain an access token issued by a trusted IdP.

Example API call once you have a valid token (never put real tokens in URLs or logs):

~~~bash
curl -i "http://localhost:8080/api/reports" \
  -H "Authorization: Bearer <valid-access-token>"
~~~

When signature, issuer, timestamps, audience, and `reports.read` scope are all valid, expect **200**. Valid tokens missing the scope typically get **403**. Tokens with invalid signatures/claims typically get **401**. The `WWW-Authenticate` response header helps distinguish `invalid_token` from `insufficient_scope`, without leaking raw tokens in logs.

## 19. Why Is 401 Different from 403?

| Situation | Typical result | Layer |
| --- | --- | --- |
| Missing Bearer token | 401 | Authentication |
| Malformed or tampered JWT | 401 | Decoder/JWS verification |
| Wrong signature, non-allowlisted alg, unknown kid | 401 | Decoder/JWKS |
| `iss` differs from trusted issuer | 401 | Issuer validation |
| `exp` expired beyond clock skew | 401 | Timestamp validation |
| `nbf` still in the future | 401 | Timestamp validation |
| `aud` missing or wrong API | 401 | Audience validation |
| `exp` missing under lab profile | 401 | Required expiration validator |
| Valid signature/claims but missing scope | 403 | Authorization |
| Valid token and sufficient scope | 200 | Controller |
| Valid token, undeclared route | 403 | denyAll |
| Token has scope, but user has wrong tenant/owner | 403 or 404 per API contract | Domain authorization |

Browser CORS errors do not substitute for JWT debugging. If an API lacks CORS response headers, the browser may hide 401/403 status codes in the console. Read Network and sanitized server logs; never turn off signature/issuer/audience checks to “let requests through”.

## 20. Extended JWKS/Network and Key Rotation Testing

Unit tests in Section 16 use a pinned RSA public key and do not test JWKS fetching/caching. For deeper integration testing:

1. Spin up an internal test-controlled mock JWKS server returning valid JWK public keys and key IDs.
2. Configure `lab.jwt.jwks-uri` pointing to the test server, never a user-supplied host.
3. Generate an RSA private key and sign JWTs with valid `iss`/`aud`/`exp`/`nbf`.
4. Send real Bearer HTTP requests via `WebTestClient` to the Resource Server and verify 200.
5. Alter the signature or `aud`/`iss`/`exp`/`nbf` and verify 401.
6. Test a JWT carrying the new key's `kid` once mock JWKS publishes old + new keys; verify cache/rotation behavior for your Spring/Nimbus version.
7. Induce JWKS timeout/5xx/TLS failures and ensure there is no “accept anything” or signature-skipping fallback.

This is an **advanced exercise** rather than a pre-written Java file in the example. Key rotation cache TTL/refresh behavior can change across versions, so never assert a fixed number of seconds without measuring and checking the docs for your exact version.

## 21. Decoder Configurations: Which Option to Choose?

| Approach | Best when | Limitations / points to check |
| --- | --- | --- |
| Boot `issuer-uri` | IdP supports standard metadata discovery | Additional aud policy, discovery availability |
| Boot `issuer-uri` + `jwk-set-uri` | Want to use trusted JWKS URI directly | Still verify iss and aud |
| `ReactiveJwtDecoders.fromIssuerLocation` | Custom Java Bean using issuer discovery | Startup/runtime network depends on version; retain validators |
| `NimbusReactiveJwtDecoder.withJwkSetUri` | Need to pin JWKS URI, algorithm, custom validators | Easy to forget iss/aud/timestamp when replacing defaults |
| `NimbusReactiveJwtDecoder.withPublicKey` | Tests or pinning a single public key | Rotation requires manual rollout, no automatic remote JWKS |

Spring Security docs describe these decoder builders and validators. In production, choose the approach with minimal custom code **yet complete security policy**, never building decoders from raw token input or letting clients pick trusted keys.

## 22. Multi-Issuer, Tenants, and Cross-JWT Confusion

A multi-tenant system may trust multiple issuers, but must enforce an admin-managed **issuer allowlist**. The following approach is wrong:

~~~java
// UNSAFE PSEUDOCODE:
String userProvidedIssuer = unverifiedJwt.getClaimAsString("iss");
ReactiveJwtDecoder chosen =
    ReactiveJwtDecoders.fromIssuerLocation(userProvidedIssuer);
~~~

Using an unverified token to drive network discovery creates SSRF/trust injection. Proper design uses an allowlisted `issuer → decoder` registry with per-resource/API trusted JWKS/alg/audience.

When two issuers emit the same `sub`, never assume they are the same user. If the app needs a stable user ID, map based on `(issuer, subject)`. When tenant membership changes, permissions inside tokens can remain stale until expiry; domain authorization or revocation/refresh mechanisms must handle this per SLA.

**Cross-JWT confusion:** OIDC ID Tokens and JWT access tokens may be signed by the same IdP yet target different recipients/purposes. Audience validation is a critical barrier; systems following the RFC 9068 JWT access token profile must also check `typ`/`client_id` and contract claims rather than only the four claims in this lesson.

## 23. Production Failures and Diagnostics

| Symptom | Likely cause | Action |
| --- | --- | --- |
| 401 despite valid-looking JWT payload | Bad signature / untrusted JWKS | Do not trust payload; check key/alg |
| Token for A accepted by API B | Missing `aud` check | Require B's expected audience |
| API returns 200 with `mockJwt alg=none` | Mock bypasses decoder | Use signed-token tests |
| Prod 401 while mock tests pass | Issuer/aud/time/signature differ from tests | Test real decoder and mock JWKS |
| Valid JWT, missing `SCOPE_reports.read` | Authorization policy | Check scope mapping and routes |
| Future `nbf` | Clock/issuer time drift | NTP, small skew, inspect `nbf` |
| Expired `exp` still passes | Custom decoder forgot timestamp validator | Compose `JwtValidators` + negative tests |
| All tokens 401 after key rotation | JWKS cache/kid/alg mismatch | Check key overlap and cache |
| JWKS endpoint unreachable | DNS/TLS/timeouts, key not cached | Fail closed, monitor IdP |
| Valid token accesses wrong tenant data | Missing domain-level auth | Enforce owner/tenant/DB policies |
| Revoked token still passes before `exp` | Stateless verification does not introspect | Short TTL / introspection / revocation |
| Fixing 401 by removing issuer validator | Security anti-pattern | Fix misconfiguration; never fail open |
| Boot API with `issuer-uri` fails to start | Metadata discovery or wrong issuer | Trusted issuer config, check deferred decoder behavior |

Debugging order: valid Bearer header → JWS syntax/alg/kid → trusted JWKS → signature → issuer → timestamps → audience → Authentication authorities → object/tenant authorization. Never log raw tokens or sensitive claims verbatim while investigating.

## 24. Operational Security

- Only accept Bearer over **HTTPS**; never pass tokens in URL/query strings, logs, screenshots, analytics, or exception messages.
- Pin algorithms, trusted issuers, and JWKS URLs; never trust `jku`/`x5u`/issuer URLs from unverified tokens.
- Never store private signing keys in the Resource Server. Keys published in JWKS are public keys.
- Sync clocks with NTP, keep skew small, and test expired/not-before across nodes.
- Monitor IdP/JWKS availability, enforce bounded retries/caching, and overlap key rotations.
- Limit token/header sizes and apply rate limits to prevent token/JWKS endpoint DoS.
- If immediate revocation is required, design appropriate revocation/introspection/token TTLs; signature validation cannot tell a token was revoked before `exp`.
- Scope/role mapping does not replace object/tenant/ownership checks.
- If JWTs are auto-sent by browsers via cookies, evaluate CSRF; disabling CSRF in the lab assumes header-only Bearer.
- For APIs following RFC 9068, validate the full token profile/`typ` rather than only `iss`/`exp`/`nbf`/`aud`.

## 25. Hands-On Exercises

**A. Tampering with claims:** modify the raw JWT `scope` payload without re-signing. Why does the signature break? Try with dummy test tokens, never real tokens.

**B. Wrong signature:** sign a JWT with a different RSA key pair while keeping valid `iss`/`aud`/`exp`/`nbf`. Expect `JwtException` from the trusted public-key decoder.

**C. Different realm issuer:** same private key, but `iss` from another realm → rejected. Explain why matching hostname alone is insufficient.

**D. Expired vs. future nbf:** a token expired by 10 minutes and a token with `nbf` 1 hour ahead must both be rejected despite valid signatures.

**E. Different audience:** a token with `aud` `billing-api` sent to `reports-api` must be rejected; only tokens whose `aud` contains `reports-api` proceed.

**F. Missing exp:** omit `exp` from a signed token and compare results with `ExpirationRequiredValidator`.

**G. Route authorization:** `mockJwt` with `SCOPE_profile` accessing reports must return 403; `SCOPE_reports.read` → 200. Recall that mocks do not verify signatures.

**H. Mock JWKS:** write an integration test for JWKS key rotation and outage ensuring fail-closed behavior.

**I. Multi-tenant:** use an allowlist of two issuers and two audiences; prevent tenant A tokens from accessing B.

**J. Version upgrade:** upgrade Spring Security/Boot in a sandbox, re-run crypto negative tests, and check defaults for `alg`/`typ`/validators.

### Checklist

- [ ] Distinguish reading payload from verifying JWS signature.
- [ ] Know trusted JWKS/public keys, alg allowlist, and kid/key rotation.
- [ ] `iss` exact-matches trusted issuer.
- [ ] `exp` checked against current time/clock skew with a policy for missing `exp`.
- [ ] Future `nbf` rejected, understanding it is an optional claim per RFC.
- [ ] `aud` contains the exact Resource Server ID without substring matching.
- [ ] Distinguish 401 authentication from 403 authorization.
- [ ] Compose `JwtValidators.createDefaultWithIssuer` + `AudienceValidator`.
- [ ] Have independent RSA signed-token tests and `WebTestClient` `mockJwt` tests.
- [ ] Never arbitrarily use an ID Token as an API access token.
- [ ] Never trust caller-supplied issuer/JWKS URLs.
- [ ] Never skip tenant/owner checks after a token passes validation.

## 26. Self-Check Questions

1. Why does Base64URL-decoding a JWT not prove identity?
2. What are `alg`/`kid` headers and why is an allowlist needed?
3. How can a public key verify a signature without knowing the private key?
4. Why must a token with valid `iss` but wrong `aud` still be rejected?
5. How do `exp` and `nbf` differ regarding the start and end of validity?
6. Are `exp`/`nbf` mandatory in RFC 7519? What policy did the lab choose?
7. Why shouldn't you select a JWKS URL based on an unverified `iss`?
8. Why does a valid JWT lacking `reports.read` receive 403?
9. Why does `mockJwt` not prove token signature, issuer, `exp`, `nbf`, or `aud`?
10. During key rotation, why is an overlapping two-key window required?
11. If a token is revoked before `exp`, does signature verification know?
12. Why must an OIDC ID Token not be treated as an access token for `reports-api`?
13. When supporting multiple issuers, how should decoders be selected to prevent SSRF?
14. Why must the Resource Server still check owner/tenant after authentication?

## 27. References

- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): issuer/JWKS, signed JWT, timestamp validator, and custom audience validator.
- [Spring Security — Reactive JWT Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt`, authorities, and mock limitations.
- [Spring Security API — NimbusReactiveJwtDecoder](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html): decoder/JWK builder.
- [Spring Security API — JwtValidators](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/oauth2/jwt/JwtValidators.html): default validators.
- [Spring Security — WebFlux HTTP Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): rule-based routing.
- [RFC 7519 — JWT](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `aud`, `exp`, `nbf`, and NumericDate.
- [RFC 7515 — JWS](https://www.rfc-editor.org/rfc/rfc7515): JSON Web Signature.
- [RFC 7517 — JWK](https://www.rfc-editor.org/rfc/rfc7517): JWKS representation and key identifiers.
- [RFC 8725 — JWT BCP](https://www.rfc-editor.org/rfc/rfc8725): algorithm confusion, key validation, and cross-JWT confusion.
- [RFC 9068 — JWT Access Token Profile](https://www.rfc-editor.org/rfc/rfc9068): additional access-token-specific claims and `typ`.
- [OWASP — JSON Web Token for Java Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): JWT security.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, object authorization.

**Conclusion:** In Spring Security Reactive, `NimbusReactiveJwtDecoder` verifies the JWS with a **trusted public key**, and validators then evaluate issuer, timestamps, and audience. `iss` blocks tokens from the wrong issuer; `exp` blocks expired tokens; `nbf` blocks premature tokens; `aud` blocks tokens meant for other APIs. Validating the signature and all four claims is still not enough for business permissions: you must enforce scope, owner, and tenant. **Use genuinely signed JWTs to test crypto/claims; use `mockJwt` to test authorization — never swap these two kinds of evidence.**