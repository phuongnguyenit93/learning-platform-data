# ReactiveJwtDecoder and Choosing Trusted Signature Algorithms

> **Topic:** Spring Security – reactive  
> **Knowledge group:** Resource Server JWT  
> **Focus:** Verifying JWT signatures in Spring WebFlux with `ReactiveJwtDecoder` and `NimbusReactiveJwtDecoder`; restricting trusted JWS signing algorithms, verifying issuer/audience/expiration, connecting to trusted JWKS, and testing genuinely signed tokens with Java 17+.

## 1. Why Is Reading a JWT Still Not Enough to Trust It?

A reporting API `GET /api/reports` receives:

```http
GET /api/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

A JWT in JWS Compact Serialization consists of:

```text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
```

Example header and claims:

```json
{
  "typ": "JWT",
  "alg": "RS256",
  "kid": "rsa-2026-01"
}
```

```json
{
  "iss": "https://issuer.example.test",
  "sub": "user-123",
  "aud": ["reports-api"],
  "scope": "reports.read",
  "iat": 1794000000,
  "nbf": 1794000000,
  "exp": 1794003600
}
```

The numeric timestamps only illustrate NumericDate format, **not a usable token**. Anyone can Base64URL-decode the payload or craft a fake JWT string. Therefore:

1. **Parse:** Does the string have valid JWS/JWT structure?
2. **Cryptographic verification:** Is the signature valid against a **trusted public key** and a **server-allowed algorithm**?
3. **Claims validation:** Do `iss`, `aud`, `exp`, `nbf`, and token type satisfy the API's policy?
4. **Authorization:** Does the valid principal/token have `reports.read` permission and access to the specific resource?

**Reading/decoding does not mean verification.** A JWT with a valid RSA signature from the issuer but `aud=payment-api` must still be rejected by the reports API. A JWT with valid issuer and audience but lacking scope may be authenticated and then receive **403** at the authorization layer.

### Learning Objectives

After this lesson, you can:

- Distinguish `ReactiveJwtDecoder` from Servlet `JwtDecoder` and understand how `Mono<Jwt>` handles errors.
- Understand `alg`, `kid`, JWKS, key rotation, and why trusted algorithms must be configured **server-side**, not taken from token data.
- Use Spring Boot properties `issuer-uri`, `jwk-set-uri`, `jws-algorithms`, and `audiences` when appropriate.
- Build a custom `NimbusReactiveJwtDecoder` with `jwsAlgorithm(SignatureAlgorithm.RS256)`, keeping default issuer/time validators and adding an audience validator.
- Distinguish RS256, PS256, ES256, HS256, and `alg=none`.
- Write a Java 17+ Spring Security WebFlux Resource Server and test real-signed JWTs with `NimbusJwtEncoder` + `StepVerifier`.
- Test HTTP 401/403/scopes with `WebTestClient`, clearly recognizing that `mockJwt()` **does not verify signatures**.

## 2. Role of ReactiveJwtDecoder in WebFlux Resource Server

A simplified processing path:

```text
HTTP Authorization: Bearer <token>
          |
          v
SecurityWebFilterChain / Bearer authentication
          |
          v
ReactiveJwtDecoder.decode(token)
          |
          +-- JWT parse, header alg policy, select trusted key
          +-- verify cryptographic signature
          +-- validate iss/aud/exp/nbf/type per config
          |
          +-- invalid -> JwtException / authentication failure -> typically 401
          |
          v
JwtAuthenticationToken (Jwt principal + authorities)
          |
          v
AuthorizationWebFilter
          |
          +-- missing SCOPE_reports.read -> typically 403
          +-- authorized -> WebFlux controller Mono/Flux
```

`ReactiveJwtDecoder` is an interface in `org.springframework.security.oauth2.jwt`:

```java
// API signature for reference:
Mono<Jwt> decode(String token) throws JwtException;
```

`decode` returns a `Mono<Jwt>` publisher. In WebFlux, signature/validation failures are normally emitted as a **reactive error signal**. You do not need to call `.block()` or `.subscribe()` to “trigger the decoder” in controllers: Spring Security runs it in the authentication filter before the controller handles the request.

**Stack comparison:**

| Stack | Decoder | Result |
| --- | --- | --- |
| Spring WebFlux reactive | `ReactiveJwtDecoder` | `Mono<Jwt>` |
| Spring Security Servlet | `JwtDecoder` | `Jwt` |
| Nimbus reactive implementation | `NimbusReactiveJwtDecoder` | Verified/validated JWT |
| Nimbus imperative implementation | `NimbusJwtDecoder` | Only for Servlet-compatible setups |

Do not drop an `HttpSecurity`-style `JwtDecoder` bean from a Servlet tutorial into an app using `ServerHttpSecurity` expecting the reactive resource server to use it.

### 2.1. JWT Authentication and Access Permissions Are Not the Same

Spring Security normally maps `scope` or `scp` in a JWT to `GrantedAuthority` values prefixed with `SCOPE_`:

```text
scope claim: "reports.read reports.write"
                    |
                    v
SCOPE_reports.read
SCOPE_reports.write
```

When the rule is `hasAuthority("SCOPE_reports.read")`, a JWT with a valid signature that only holds `SCOPE_profile.read` is denied by authorization. In many configurations, authentication failure returns HTTP **401** with a Bearer challenge; insufficient privileges on a valid principal return **403**. CORS, CSRF, or gateways can also return 403, so not every 403 comes from scopes.

## 3. Trusted Signature Algorithms: RS256 by Default

Spring Security 6.5 documentation explicitly states that `NimbusReactiveJwtDecoder` **trusts only RS256 by default** in JWT Resource Server setups. Do not widen it merely because the decoder supports other algorithms; change it only when the Authorization Server actually issues access tokens with another algorithm and you have verified key types, issuer, and profile.

| JWS algorithm | Crypto family | Verification key | Notes |
| --- | --- | --- | --- |
| `RS256` | RSA PKCS#1 v1.5 / SHA-256 | RSA public key | Spring Security 6.5 default |
| `RS384`, `RS512` | RSA SHA-384/512 | RSA public key | Do not enable if IdP does not use them |
| `PS256`, `PS384`, `PS512` | RSA-PSS | RSA public key | Distinct from RS*, even with same key family |
| `ES256` | ECDSA P-256 / SHA-256 | EC public key | Must match curve/key |
| `ES384`, `ES512` | Curve-matched ECDSA | EC public key | Enable only per provider |
| `HS256`, `HS384`, `HS512` | HMAC | Shared secret | Verifier holding secret can also sign |
| `none` | Unsigned | None | Never accept for protected Bearer JWTs |

`SignatureAlgorithm.RS256` and `SignatureAlgorithm.PS256` are both in `org.springframework.security.oauth2.jose.jws`. With the RSA public-key builder, the API uses `.signatureAlgorithm(...)`; with the trusted JWKS builder, it uses `.jwsAlgorithm(...)`.

### 3.1. The alg Header Is Always Untrusted Input

Wrong in principle:

```java
// Wrong pseudocode: do not implement this pattern.
String algorithm = parseUnverifiedHeader(token).get("alg");
ReactiveJwtDecoder decoder = trustAlgorithmFromCaller(algorithm);
```

Attackers control the header. If the server blindly accepts “whatever alg the token requests”, **algorithm confusion/substitution** can occur (for example, mixing RSA public keys and HMAC secrets in a misdesigned verifier). Trusted keys, allowed algorithms, and issuer must be decided **from backend configuration**, never from an unverified JWT.

Correct:

```java
// Snippet inside configuration with a trusted JWKS URI.
NimbusReactiveJwtDecoder decoder =
    NimbusReactiveJwtDecoder.withJwkSetUri(trustedJwksUri)
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .build();
```

This **pins the algorithm**. Afterward, issuer/audience validators must still be configured.

### 3.2. When Two Algorithms Are Needed During Migration

```java
// Enable only when the real issuer publishes both and a cutover plan exists.
NimbusReactiveJwtDecoder decoder =
    NimbusReactiveJwtDecoder.withJwkSetUri(trustedJwksUri)
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .jwsAlgorithm(SignatureAlgorithm.ES256)
        .build();
```

Each `jwsAlgorithm` call on the JWKS builder **adds** an accepted algorithm rather than merely replacing the previous one. A safe migration requires a bounded time window, testing RS256/ES256 tokens, key rotation, and eventually removing the old algorithm. Never add every algorithm to an allowlist just to silence HTTP 401 errors.

### 3.3. RS256 and PS256 Are Not Interchangeable

Both use RSA public/private keys, but RS256 is RSA PKCS#1 v1.5 while PS256 uses RSA-PSS. If the decoder allows only RS256, a JWT signed with PS256 **must be rejected**, **even when** the PS256 signature was created with the exact same trusted RSA private key. The real test in Section 9 intentionally verifies this.

### 3.4. HMAC Is a Different Trust Model

```java
// Separate HMAC snippet: use only when design trusts a shared secret.
NimbusReactiveJwtDecoder decoder =
    NimbusReactiveJwtDecoder.withSecretKey(secretKey)
        .macAlgorithm(MacAlgorithm.HS256)
        .build();
```

`MacAlgorithm` is imported from `org.springframework.security.oauth2.jose.jws.MacAlgorithm`; `secretKey` must be a `javax.crypto.SecretKey` with sufficient entropy retrieved from a secrets manager. **Do not** use an RSA public key as an HMAC secret. Across multiple Resource Servers, asymmetric signatures are usually preferable because APIs only receive public keys and cannot forge JWTs.

## 4. JWKS, kid, and Trust Boundaries

An Authorization Server can publish **JWKS** (JSON Web Key Set) over HTTPS:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "rsa-2026-01",
      "alg": "RS256",
      "n": "BASE64URL_RSA_MODULUS",
      "e": "AQAB"
    }
  ]
}
```

This is a **structural example**, not a usable key. Public JWKS must never expose private exponent `d`, key primes, or signing secrets. The Resource Server picks keys from a **trusted configured JWKS URL**:

```text
JWS header alg=RS256, kid=rsa-2026-01
             |
             v
Server algorithm allowlist (RS256?)
             |
             v
Trusted JWKS source for the expected issuer
             |
             v
Filter key matching kid/kty/use/alg/key material
             |
             v
Verify signature
             |
             v
Validate JWT claims and API policy
```

`kid` is only a **key identifier hint**, not proof that the issuer or key is trusted. JOSE headers like `jku`/`x5u` can contain URLs; **never automatically download public keys from a caller-supplied URL in the token**. Doing so opens SSRF and key-injection risks: an attacker could redirect the verifier to keys they control.

When the AS rotates keys, publish the new public key **before** or concurrently with issuing tokens signed by the new key, keeping the old key long enough for unexpired tokens. Spring Security/Nimbus handles selecting and refreshing keys from JWKS, yet you must still test cache TTL, rotation, outages, unknown `kid`, concurrency, and multiple replicas. Never fall back to “skipping signature checks” on temporary JWKS failures.

### 4.1. Key Rotation vs. Algorithm Migration

- **Rotate key, keep RS256:** add a new `kid` in JWKS while keeping RS256.
- **Move RS256 to ES256:** add the new algorithm/key type per plan, test both profiles together, then retire the old algorithm.
- **Change issuer:** requires new trust policy/decoder routing, not just changing `kid`.

If the system accepts tokens from multiple issuers, configure a **trusted issuer allowlist** and bind each issuer to its matching JWKS/audience. Use an unverified `iss` only as a lookup key *within trusted issuers*, never to fetch JWKS from arbitrary issuer strings in the token.

## 5. Spring Boot Properties: Fast, Clear, and Bounded Configuration

For a WebFlux Resource Server using **Boot auto-configuration** without declaring a custom decoder bean:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test
          jwk-set-uri: https://issuer.example.test/oauth2/jwks
          jws-algorithms: RS256
          audiences:
            - reports-api
```

- `issuer-uri` validates `iss` and can be used for metadata discovery.
- `jwk-set-uri` is the **trusted URL** for fetching public signing keys. When both are declared, the Resource Server avoids discovery to locate the JWKS URL at startup; verifying new tokens may still require contacting JWKS.
- `jws-algorithms` picks trusted JWS signing algorithms. For example, RS256 only.
- `audiences` enforces `aud` validation via supported Boot configuration, blocking tokens meant for other APIs.

Having only `jwk-set-uri` without appropriate issuer validation is **not enough** to confirm every token came from the right issuer. One issuer can issue tokens for multiple Resource Servers, so audience is typically a separate requirement.

If the application provides a **`@Bean ReactiveJwtDecoder`**, that custom bean replaces Spring Boot's auto-configured decoder; **do not assume** the properties above still apply to your bean. A custom bean must configure allowed algorithms, key source, and validators itself. Section 8 uses a custom bean to make every step explicit.

### 5.1. Spring Security WebFlux DSL

```java
// Snippet inside @Configuration (import withDefaults).
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/health").permitAll()
            .pathMatchers("/api/reports")
                .hasAuthority("SCOPE_reports.read")
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
        .build();
}
```

When using Boot properties, Resource Server JWT automatically uses the Boot-created decoder bean. `ServerHttpSecurity` is WebFlux; do not substitute Servlet `HttpSecurity`.

## 6. Custom NimbusReactiveJwtDecoder and Validators

Sometimes you need custom audience, token profile, or multi-issuer/algorithm checks. Java configuration:

```java
// Snippet inside @Configuration; full version is in Section 8.
@Bean
ReactiveJwtDecoder jwtDecoder() {
    String issuer = "https://issuer.example.test";
    String jwks = issuer + "/oauth2/jwks";

    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withJwkSetUri(jwks)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

    OAuth2TokenValidator<Jwt> defaults =
        JwtValidators.createDefaultWithIssuer(issuer);
    OAuth2TokenValidator<Jwt> audience =
        new AudienceValidator("reports-api");

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(defaults, audience));
    return decoder;
}
```

`AudienceValidator` is written in full in Section 8. In this configuration:

1. The JWKS URL is trusted and never derived from tokens.
2. Only RS256 is trusted even if JWKS contains other keys.
3. `JwtValidators.createDefaultWithIssuer` preserves default validators (including timestamps) and issuer validation.
4. Audience is checked explicitly: JWT must include `aud=reports-api`.
5. Only if the token passes the decoder does Spring map claims to authorities for endpoint permissions.

**Warning about `setJwtValidator`:** it **replaces** the current validator. If you pass only `new AudienceValidator(...)` and drop the default validators, you risk losing `iss` and `exp`/`nbf` checks. Combine them using `DelegatingOAuth2TokenValidator` as shown above.

### 6.1. Clock Skew

Many systems drift by a few seconds. Spring Security uses `JwtTimestampValidator` to check `exp` and `nbf`, with a documented default skew typically **60 seconds**. Never enlarge skew excessively to legitimize expired tokens. Synchronize clocks via NTP and test expired tokens as well as `nbf` far in the future. Example tests use offsets of several minutes to avoid flakiness.

### 6.2. Audience, Issuer, and Scope Are Three Distinct Concepts

| Claim | Question |
| --- | --- |
| `iss` | Who issued the JWT? |
| `aud` | Which Resource Server was the JWT issued for? |
| `sub` | Who is the subject referenced by the token? |
| `exp` | When does the token expire? |
| `nbf` | When does it become valid? |
| `scope`/`scp` | Which permissions did the AS grant for accessing resources? |

A JWT with the right scope but wrong audience must be **rejected by the decoder** without reaching authorization rules. A JWT with the right audience but missing scope may **authenticate and then receive 403**. A validly signed **OIDC ID token** with `aud=web-client` must never be used as an access token to call a Resource Server.

### 6.3. JWT Type: Access Token vs. ID Token

An OIDC ID token is meant for an OIDC Client to verify user identity. An OAuth2 access token is meant for a Resource Server. In practice, both may be JWTs signed by the same issuer. Checking only signature/issuer risks **token substitution / cross-JWT confusion**. Depending on the issuer, check audience, token type `typ`, `client_id`, scopes, or RFC 9068 profile.

Spring Security 6.5 provides `JwtValidators.createAtJwtValidator()` to build an RFC 9068 validator when the Authorization Server issues JWT access tokens following that profile; configure compatible type/header validation rather than applying it blindly to arbitrary providers without reading their token profile docs.

## 7. Safety Rules When Calling decode() from Reactive Code

```java
// Reactive task outside the filter (snippet; requires injected decoder):
return decoder.decode(rawToken)
    .map(Jwt::getSubject)
    .switchIfEmpty(Mono.error(
        new IllegalStateException("No JWT was produced")));
```

Most APIs **do not need to call the decoder manually in controllers**: the Spring Security Resource Server filter already authenticates the Bearer token before the request arrives. For other use cases, return the publisher and handle `onError`; do not call:

```java
// Do NOT use on the Netty event loop:
Jwt jwt = decoder.decode(rawToken).block();

// Do NOT create a detached subscription and assume the request is authenticated:
decoder.decode(rawToken).subscribe(jwt -> allowRequest());
```

`.block()` blocks the thread and manual `.subscribe()` detaches lifecycle/errors/cancellation from the request. In WebFlux, request `Authentication` travels in the **Reactor Context**, read via `ReactiveSecurityContextHolder`, not from Servlet `SecurityContextHolder` ThreadLocal assumptions.

## 8. Java 17+ WebFlux Project: RS256 Signature and Audience

The following project uses **Spring Boot 3.5.16** (final OSS release of the 3.5 branch, used solely as a baseline for learning Spring Security 6.5; production in 2026 should use a supported branch). **Maven tests run offline** with genuinely signed JWTs using a keypair generated at test runtime and mock JWTs for HTTP authorization. The running app demonstrates public/401 endpoints, while end-to-end HTTP Bearer validation requires replacing the example issuer/JWKS with a real sandbox IdP.

### 8.1. Structure

```text
reactive-jwt-algorithms/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/jwt/
    │   │   ├── Application.java
    │   │   ├── AudienceValidator.java
    │   │   ├── JwtSecurityConfiguration.java
    │   │   └── ReportController.java
    │   └── resources/application.yml
    └── test/java/demo/jwt/
        ├── JwtDecoderSignatureTests.java
        └── HttpJwtAuthorizationTests.java
```

### 8.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-jwt-algorithms</artifactId>
    <version>1.0.0</version>
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
```

`spring-boot-starter-oauth2-resource-server` provides the required Resource Server/JWT JOSE dependencies in a Boot project. Do not use the OAuth2 Client starter if the app only **receives and verifies** Bearer JWTs rather than requesting tokens for outbound API calls.

### 8.3. src/main/resources/application.yml

```yaml
app:
  security:
    jwt:
      issuer: https://issuer.example.test
      jwk-set-uri: https://issuer.example.test/oauth2/jwks
      audience: reports-api
server:
  port: 8080
```

These are **custom** `app.security.jwt.*` properties read by Java config. They are not the Spring Boot decoder auto-configuration keys from Section 5. `issuer.example.test` is only an example host: **there is no real Authorization Server at this URL**. Never put private signing keys or client secrets into the resource server.

### 8.4. src/main/java/demo/jwt/Application.java

```java
package demo.jwt;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 8.5. src/main/java/demo/jwt/AudienceValidator.java

```java
package demo.jwt;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class AudienceValidator
        implements OAuth2TokenValidator<Jwt> {

    private final String expectedAudience;

    public AudienceValidator(String expectedAudience) {
        this.expectedAudience = expectedAudience;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getAudience().contains(expectedAudience)) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token",
                "JWT audience is not this resource server", null));
    }
}
```

`AudienceValidator` checks **only** `aud`. It does not verify signature/issuer/expiration on its own; the configuration must combine it with the default validators.

### 8.6. src/main/java/demo/jwt/JwtSecurityConfiguration.java

```java
package demo.jwt;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class JwtSecurityConfiguration {

    @Bean
    ReactiveJwtDecoder jwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwk-set-uri}") String jwksUri,
            @Value("${app.security.jwt.audience}") String audience) {

        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withJwkSetUri(jwksUri)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> defaultWithIssuer =
            JwtValidators.createDefaultWithIssuer(issuer);
        OAuth2TokenValidator<Jwt> audienceValidator =
            new AudienceValidator(audience);

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                defaultWithIssuer, audienceValidator));

        return decoder;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/health").permitAll()
                .pathMatchers("/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers("/api/me").authenticated()
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(withDefaults()))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            // Bearer-header-only API in demo, no browser session.
            .csrf(csrf -> csrf.disable())
            .build();
    }
}
```

**Explanation:** The custom `ReactiveJwtDecoder` trusts only RS256, fetches public keys from the trusted JWKS URL, preserves issuer/time validators, and adds an audience check. The security filter requires JWT Bearer and enforces `SCOPE_reports.read`. `httpBasic`/`formLogin` are disabled to avoid mixing login mechanisms. `csrf.disable()` is only justified under the assumption of a **pure Bearer API** with no session cookies or browser-sent ambient credentials; do not copy into cookie-based websites without CSRF analysis.

### 8.7. src/main/java/demo/jwt/ReportController.java

```java
package demo.jwt;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReportController {

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("OK");
    }

    @GetMapping("/api/reports")
    public Mono<String> reports() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> "report:" + auth.getName());
    }

    @GetMapping("/api/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> "subject:" + auth.getName());
    }
}
```

`getName()` typically maps from the JWT's `sub` in default Resource Server config, though it can be customized via a converter. This is an **identity authenticated by Spring Security**, never taken from `?user=` or a client-supplied `X-User`. With real data, ownership and tenant must still be checked against a trusted repository.

## 9. Real Cryptographic Tests: RS256 Accepted, PS256 Rejected

This test suite generates a random RSA keypair in **test memory**, signs JWTs with the private key via `NimbusJwtEncoder`, then decodes JWTs with the **public key** using `NimbusReactiveJwtDecoder`. Wrong algorithm, wrong key, wrong issuer, wrong audience, expired, future `nbf`, and unsigned cases are all verified with `StepVerifier`.

### 9.1. src/test/java/demo/jwt/JwtDecoderSignatureTests.java

```java
package demo.jwt;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.PlainJWT;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class JwtDecoderSignatureTests {

    private static final String ISSUER =
        "https://issuer.example.test";
    private static final String AUDIENCE = "reports-api";

    private static KeyPair trustedKeyPair;
    private static NimbusReactiveJwtDecoder decoder;

    @BeforeAll
    static void setup() throws Exception {
        trustedKeyPair = makePair();
        decoder = NimbusReactiveJwtDecoder
            .withPublicKey((RSAPublicKey) trustedKeyPair.getPublic())
            .signatureAlgorithm(SignatureAlgorithm.RS256)
            .build();
        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(ISSUER),
            new AudienceValidator(AUDIENCE)));
    }

    private static KeyPair makePair() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    private static String sign(
            KeyPair keyPair, SignatureAlgorithm algorithm,
            String issuer, String audience,
            Instant notBefore, Instant expiresAt) {

        RSAKey jwk = new RSAKey.Builder(
                (RSAPublicKey) keyPair.getPublic())
            .privateKey((RSAPrivateKey) keyPair.getPrivate())
            .keyID("test-kid")
            .build();

        NimbusJwtEncoder encoder = new NimbusJwtEncoder(
            new ImmutableJWKSet<>(new JWKSet(jwk)));

        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject("alice")
            .audience(List.of(audience))
            .issuedAt(Instant.now().minusSeconds(900))
            .notBefore(notBefore)
            .expiresAt(expiresAt)
            .claim("scope", "reports.read")
            .build();

        JwsHeader header = JwsHeader.with(algorithm)
            .keyId("test-kid")
            .build();

        return encoder.encode(
            JwtEncoderParameters.from(header, claims))
            .getTokenValue();
    }

    private static String validToken() {
        Instant now = Instant.now();
        return sign(trustedKeyPair, SignatureAlgorithm.RS256,
            ISSUER, AUDIENCE,
            now.minusSeconds(120), now.plusSeconds(300));
    }

    @Test
    void trustedRs256AndClaimsAreAccepted() {
        StepVerifier.create(decoder.decode(validToken()))
            .assertNext(jwt -> {
                assertEquals("alice", jwt.getSubject());
                assertEquals(ISSUER, jwt.getIssuer().toString());
                assertEquals(List.of(AUDIENCE), jwt.getAudience());
            })
            .verifyComplete();
    }

    @Test
    void signedPs256IsRejectedWhenOnlyRs256IsAllowed() {
        Instant now = Instant.now();
        String token = sign(trustedKeyPair,
            SignatureAlgorithm.PS256, ISSUER, AUDIENCE,
            now.minusSeconds(120), now.plusSeconds(300));

        StepVerifier.create(decoder.decode(token))
            .expectError(JwtException.class).verify();
    }

    @Test
    void rs256WithDifferentSigningKeyIsRejected() throws Exception {
        Instant now = Instant.now();
        String token = sign(makePair(), SignatureAlgorithm.RS256,
            ISSUER, AUDIENCE,
            now.minusSeconds(120), now.plusSeconds(300));

        StepVerifier.create(decoder.decode(token))
            .expectError(JwtException.class).verify();
    }

    @Test
    void validSignatureWithWrongIssuerIsRejected() {
        Instant now = Instant.now();
        String token = sign(trustedKeyPair, SignatureAlgorithm.RS256,
            "https://other.example.test", AUDIENCE,
            now.minusSeconds(120), now.plusSeconds(300));

        StepVerifier.create(decoder.decode(token))
            .expectError(JwtException.class).verify();
    }

    @Test
    void validSignatureWithWrongAudienceIsRejected() {
        Instant now = Instant.now();
        String token = sign(trustedKeyPair, SignatureAlgorithm.RS256,
            ISSUER, "payments-api",
            now.minusSeconds(120), now.plusSeconds(300));

        StepVerifier.create(decoder.decode(token))
            .expectError(JwtException.class).verify();
    }

    @Test
    void expiredJwtIsRejected() {
        Instant now = Instant.now();
        String token = sign(trustedKeyPair, SignatureAlgorithm.RS256,
            ISSUER, AUDIENCE,
            now.minusSeconds(900), now.minusSeconds(300));

        StepVerifier.create(decoder.decode(token))
            .expectError(JwtException.class).verify();
    }

    @Test
    void futureNbfJwtIsRejected() {
        Instant now = Instant.now();
        String token = sign(trustedKeyPair, SignatureAlgorithm.RS256,
            ISSUER, AUDIENCE,
            now.plusSeconds(600), now.plusSeconds(1200));

        StepVerifier.create(decoder.decode(token))
            .expectError(JwtException.class).verify();
    }

    @Test
    void unsignedPlainJwtIsRejected() {
        String plain = new PlainJWT(
            new JWTClaimsSet.Builder().subject("alice").build())
            .serialize();

        StepVerifier.create(decoder.decode(plain))
            .expectError(JwtException.class).verify();
    }
}
```

These are **8 cryptographic tests**. The PS256 test is the most critical for algorithm selection: a PS256 signature can be generated by the very same RSA private key, yet the RS256-only decoder **must still reject it** because `alg` is not in the allowlist. The issuer/audience tests prove that **signing properly is not enough** to be accepted by the Resource Server.

**Do not test by comparing against a hardcoded signature string:** the RSA keypair is randomly generated and `Instant.now()` produces dynamic timestamps, so tests only assert the decoded result or exception. `JwtException` is the right superclass so tests are not coupled to internal messages or exact library-version subclasses.

**Limitation:** this decoder uses a direct public key to verify. It does not prove remote JWKS retrieval, HTTP filters, or key rotation; those parts require separate integration tests.

## 10. HTTP Tests: 401/403 and SCOPE_ Mapping

`mockJwt()` helps test Spring WebFlux URL authorization **without requiring a real JWT**. This is a different goal from the cryptographic unit tests above.

### 10.1. src/test/java/demo/jwt/HttpJwtAuthorizationTests.java

```java
package demo.jwt;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class HttpJwtAuthorizationTests {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void healthIsPublic() {
        client.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("OK");
    }

    @Test
    void missingBearerIs401() {
        client.get().uri("/api/reports")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void correctScopeIs200() {
        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.subject("alice"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_reports.read")))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report:alice");
    }

    @Test
    void wrongScopeIs403() {
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.write")))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void unprefixedScopeIs403() {
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("reports.read")))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void jwtSubjectAvailableInReactiveContext() {
        client.mutateWith(mockJwt().jwt(jwt -> jwt.subject("bob")))
            .get().uri("/api/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("subject:bob");
    }

    @Test
    void basicAuthenticationDoesNotReplaceBearer() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBasicAuth("alice", "demo123"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void unknownPathDeniedEvenWithJwt() {
        client.mutateWith(mockJwt())
            .get().uri("/api/internal")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

There are **8 WebTestClient tests**. Since `mockJwt` **bypasses the decoder**, `correctScopeIs200` does not prove a valid RSA signature; it only proves the `SCOPE_reports.read` URL rule and Reactor Context work. Conversely, `JwtDecoderSignatureTests` genuinely processes private-key-signed JWTs, but does not test full HTTP filters/JWKS. The two test suites **complement** rather than replace each other.

### 10.2. Result Matrix

| Case | Test suite | Expected result |
| --- | --- | --- |
| RS256 valid signature/claims | StepVerifier | Emits Jwt |
| PS256 when only RS256 allowed | StepVerifier | JwtException |
| RS256 signed with different key | StepVerifier | JwtException |
| Wrong issuer | StepVerifier | JwtException |
| Wrong audience | StepVerifier | JwtException |
| Expired or future nbf | StepVerifier | JwtException |
| Unsigned/plain | StepVerifier | JwtException |
| Health without JWT | WebTestClient | HTTP 200 |
| API without Bearer | WebTestClient | HTTP 401 |
| Mock JWT + read scope | WebTestClient | HTTP 200 |
| Mock JWT + wrong scope | WebTestClient | HTTP 403 |
| Mock JWT + unprefixed scope | WebTestClient | HTTP 403 |
| Mock JWT accessing subject | WebTestClient | HTTP 200 |
| HTTP Basic instead of Bearer | WebTestClient | HTTP 401 |
| Mock JWT on unknown route | WebTestClient | HTTP 403 |

Total **16 tests**: 8 signature/claims tests and 8 HTTP authorization tests. Do not use these expected outcomes to claim real remote issuer/JWKS verification has been tested.

## 11. Running Maven and Testing with curl

In the directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn clean test
```

**Expected** (in a compatible environment): `Tests run: 16, Failures: 0, Errors: 0` and `BUILD SUCCESS`. This is an expectation from the example, **not a claim that Maven was executed on the reader's machine or during authoring**. If the build fails, check `target/surefire-reports`, JDK, Maven, dependency versions, and API signatures per version.

Start the application:

```bash
mvn spring-boot:run
```

Public health endpoint:

```bash
curl -i http://localhost:8080/health
```

Expected response body: `OK`, HTTP 200.

Without providing a token:

```bash
curl -i http://localhost:8080/api/reports
```

Expected HTTP **401 Unauthorized**, with `WWW-Authenticate: Bearer` or an appropriate variant.

### 11.1. Real HTTP Bearer Tokens Require a Valid Authorization Server

The app configures `issuer.example.test`, which is a **learning placeholder** with no real issuer/JWKS. To successfully call protected endpoints over HTTP:

1. Choose a sandbox IdP and configure its trusted issuer/JWKS URLs.
2. Ensure the IdP issues **RS256** JWT access tokens with the right `iss`, `aud=reports-api`, lifetime, and `reports.read` scope.
3. Reach JWKS over TLS, verify certs/keys/kid, and sync clocks.
4. Send the access token intact in `Authorization: Bearer`.
5. Verify HTTP 200, while also testing wrong key/algorithm/issuer/audience (401) and missing scope (403).

Example using an environment variable once you have a **real sandbox token**:

```bash
curl -i -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/reports
```

Never put private signing keys or raw Bearer tokens in logs, tickets, source code, or screenshots. In production, use HTTPS; tokens are credentials whose payloads are readable and which can be replayed if leaked.

## 12. Debugging When the Resource Server Returns 401 or 403

| Symptom | Cause | Check |
| --- | --- | --- |
| 401, missing Bearer | Unauthenticated | Did the client send a real access token? |
| 401, token has `alg=PS256` | Allowlist only has RS256 | Enable PS256 only if confirmed by AS/issuer policy |
| 401, unknown `kid` | JWKS lacks key / rotation / cache | Check trusted JWKS, key ID, cache |
| 401, token signed with another key | Signature verification failed | Compare against trusted AS public key |
| 401, valid signature but wrong `iss` | Untrusted issuer | Reject token; check registration/issuer config |
| 401, wrong `aud` | Token not meant for this API | Add audience validation; client must request right API token |
| 401, `exp` expired | Token past lifetime | Client refreshes/re-authorizes; do not drop timestamp checks |
| 401, `nbf` in future | Not yet valid | Clock sync / AS timestamps, reasonable skew |
| 401, AS JWKS offline | Key retrieval failed | Timeouts/cache, fail closed, never skip signature |
| 401, token rejected during alg change | AS/RS migration out of sync | Align key types and allowed algorithms |
| 403, valid token but missing scope | Authorization policy | `SCOPE_` mapping / tenant / resource checks |
| 403, another user's JWT has admin role | Resource-level permissions differ | Check object ownership, tenant, policy |
| `mockJwt()` tests pass, real token 401 | Mock bypasses crypto | Write signed-token decoder/JWKS tests |
| YAML `spring.security...` has no effect | Custom decoder bean replaces auto-config | Fix the bean/config source directly |
| Used Servlet `JwtDecoder` in WebFlux | Wrong interface | Use `ReactiveJwtDecoder` |
| Header has arbitrary `jku` URL | Key injection / SSRF risk | Use only trusted configured JWKS |
| JWT uses `alg=none` | Unsigned | Reject; never “fall back” |
| Copied `HS256` secret to many APIs | Secret holders can also sign | Re-evaluate trust model; prefer asymmetric |
| Browser CORS error, API logs 401 | Error response missing CORS headers | Debug preflight/CORS separately from authentication |
| API accepts JWT meant for a different frontend client | Token substitution | Check audience/token type and issuer |

### 12.1. Step-by-Step Debugging Order

1. Separate 401 authentication from 403 authorization.
2. Confirm the client sent an **access token**, not an OIDC ID token or refresh token.
3. Inspect the active decoder bean, allowed JWS algorithms, and trusted JWKS URL.
4. Inspect `kid/alg` headers only for diagnosis—**never** treat them as trustworthy signals.
5. Verify signature against trusted keys, then issuer/audience/time/token type.
6. After the decoder passes, check `SCOPE_...` authorities and URL/method/object-level policies.
7. Test wrong-alg/key/issuer/audience/expired cases rather than only testing happy paths.
8. Evaluate cache/key rotation, JWKS outages, and error handling through gateways.
9. Redact tokens, secrets, PII, and raw `Authorization` headers in all logs.

## 13. Advanced Cases to Distinguish

### 13.1. Signing (JWS) Is Not Encryption (JWE)

JWS protects integrity/origin with a signature, while header/payload remain readable. JWE is a separate encryption standard. This example's `ReactiveJwtDecoder` handles signed access tokens; it does **not** automatically decrypt arbitrary encrypted JWTs. If an issuer uses nested JWT/JWE, a dedicated solution with clear keys/decryption policies is needed without skipping signature verification just because the payload is “encrypted”.

### 13.2. Same Issuer and Valid Signature Are Still Not Enough

An IdP sometimes uses the same signing keys to issue multiple token types across many applications. The Resource Server must inspect **`aud`** and token-purpose profiles. A token with `aud=web-client` (ID token) must not access `reports-api` just because its signature is valid. This is why audience validators and RFC 8725 cross-JWT confusion guidance matter.

### 13.3. JWKS Connection Loss

If the public key is not cached and the JWKS endpoint is experiencing an outage, verification cannot complete. Behavior must **fail closed** or return an availability error per policy, never allowing unsigned tokens through. Design timeouts, bounded retries, caching, and tested key-rotation transitions to preserve availability without breaking trust boundaries.

### 13.4. Multiple Tenants/Issuers

In multi-tenant SaaS, each issuer may have its own JWKS and audience policy. Never create a single shared “public key bucket” and accept any JWT signed by any key. If using `JwtIssuerReactiveAuthenticationManagerResolver` to route, route only within a configured list of trusted issuers; never use an unverified `iss` as an arbitrary network URL.

### 13.5. JWT Signature vs. Business Authorization

Even a valid JWT with `reports.read` scope does not guarantee user `alice` may read `bob`'s report. Service/database layers must still verify owner/tenant from trusted sources; method security `@PreAuthorize`, `ReactiveAuthorizationManager`, and resource checks can reinforce this. Never treat a client-supplied `owner` as proof of data ownership.

## 14. Self-Check Questions

**Q1.** What return type does `ReactiveJwtDecoder.decode` have?  
**Answer:** `Mono<Jwt>` when valid; an error signal if JWT parsing/verification/validation fails.

**Q2.** Which JWS algorithm does Spring Security 6.5 reactive JWT Resource Server trust by default?  
**Answer:** **RS256**.

**Q3.** Why shouldn't the client pick the allowed alg via the JWT header?  
**Answer:** The header is unverified attacker-controlled data, which can cause algorithm confusion.

**Q4.** Does `kid` prove the key belongs to the issuer?  
**Answer:** No. It only helps pick a key **within the trusted JWKS**, and never permits fetching URLs from client headers.

**Q5.** Are RS256 and PS256 using the same RSA keypair equivalent?  
**Answer:** No. They are different signing schemes; an RS256-only decoder must reject PS256.

**Q6.** Should a JWT with a valid signature but `aud=payments-api` be accepted by `reports-api`?  
**Answer:** No; audience does not match.

**Q7.** Why is `JwtValidators.createDefaultWithIssuer` important?  
**Answer:** It preserves default validators, including timestamps, and validates the issuer; do not drop it when adding an audience check.

**Q8.** Does a Resource Server need the private key to verify RS256?  
**Answer:** No. It only needs the public key; the issuer keeps the private key for signing.

**Q9.** How does HMAC HS256 differ from RS256 regarding trust boundaries?  
**Answer:** HS256 uses a shared secret that allows the verifier to also sign; RS256 verifies with a public key separated from the private signing key.

**Q10.** If a JWT is valid but lacks `SCOPE_reports.read`, what is the typical HTTP status?  
**Answer:** **403**, because authentication passed but authorization is lacking.

**Q11.** If a token has no signature and sets `alg=none`, what must the API do?  
**Answer:** Reject it; never skip verification.

**Q12.** Does passing `mockJwt()` tests prove remote JWKS/signature checking works?  
**Answer:** No; mocks bypass the decoder. You must test with signed JWTs and the network/JWKS path separately.

**Q13.** Does a custom `@Bean ReactiveJwtDecoder` automatically inherit all Boot YAML `audiences`?  
**Answer:** Do not assume so; you must attach policy-appropriate validators to the custom bean yourself.

**Q14.** What about a JWT with the exact right issuer, but the web frontend's audience?  
**Answer:** The API must reject it, even if signed with a trusted IdP key.

**Q15.** Why not fetch JWKS from an arbitrary `jku` provided by the JWT?  
**Answer:** SSRF / key injection: the verifier could end up using keys owned by the attacker.

**Q16.** When rotating RSA keys while staying on RS256, must ES256 be enabled?  
**Answer:** No. Key rotation changes key IDs/material; algorithm migration is a separate policy change.

## 15. Production Checklist and References

- [ ] Spring WebFlux uses `ReactiveJwtDecoder` / `ServerHttpSecurity`, without mixing in Servlet decoders.
- [ ] Trusted JWS algorithm allowlist is grounded in the AS and **independent of request headers**.
- [ ] Trusted JWKS URL is centrally managed; never accept arbitrary `jku/x5u`.
- [ ] RSA/EC/HMAC key types are bound strictly to matching algorithms; `none` disallowed.
- [ ] Only public verification keys reside at the Resource Server; private signing keys stay protected at the AS.
- [ ] Signature, issuer, audience, `exp`, and `nbf` are validated.
- [ ] Custom validators do not discard default timestamp/issuer checks.
- [ ] Token type/profile checks are clear enough to prevent OIDC ID tokens from being used as OAuth access tokens.
- [ ] Valid JWTs still pass URL, method, scope, and object/tenant authorization.
- [ ] Negative tests exist for wrong alg/key/issuer/aud/exp/nbf/unsigned.
- [ ] `mockJwt` is used only for authz tests, alongside independent signed-token tests.
- [ ] Integration tests cover a trusted JWKS network/server and key rotation before production.
- [ ] Key rotation, JWKS outage/caching, clock skew, and timeouts/retries operate fail-closed.
- [ ] Never call `block()` or arbitrary `subscribe()` inside WebFlux requests.
- [ ] Never log Bearer tokens, private keys, shared secrets, or sensitive JWT claims.
- [ ] Production Java/Spring Boot/Spring Security versions are still supported.

**Conclusion:** `ReactiveJwtDecoder` does more than read JWTs — it is part of the **trust boundary** between caller-supplied tokens and the `JwtAuthenticationToken` accepted by Spring Security. Restrict JWS algorithms **server-side**, select keys from **trusted issuer JWKS**, validate issuer/audience/time/token-type claims, and **then** enforce scopes/permissions. Test the decoder with **genuinely signed JWTs**, and test HTTP authorization with `WebTestClient`; never confuse these two forms of evidence.

**Official Documentation:**

- Spring Security 6.5 – Reactive JWT Resource Server, trusted algorithms, JWKS, and validators: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security 6.5 – `ReactiveJwtDecoder` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/ReactiveJwtDecoder.html
- Spring Security 6.5 – `NimbusReactiveJwtDecoder` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html
- Spring Security 6.5 – `JwtValidators`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/JwtValidators.html
- Spring Security 6.5 – `NimbusJwtEncoder`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/NimbusJwtEncoder.html
- Spring Security 6.5 – Reactive JWT tests: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- Spring Boot 3.5.16 release/end of OSS support: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
- RFC 7515 – JSON Web Signature: https://www.rfc-editor.org/rfc/rfc7515
- RFC 7517 – JSON Web Key: https://www.rfc-editor.org/rfc/rfc7517
- RFC 7518 – JSON Web Algorithms: https://www.rfc-editor.org/rfc/rfc7518
- RFC 7519 – JSON Web Token: https://www.rfc-editor.org/rfc/rfc7519
- RFC 8725 – JWT Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725
- RFC 9068 – JWT Profile for OAuth2 Access Tokens: https://www.rfc-editor.org/rfc/rfc9068
- OWASP JSON Web Token Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html
