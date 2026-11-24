# JwtDecoder, JWK Set, and Signing Key Rotation in Spring Security Resource Server

> **Context:** Spring Security **Servlet** (Spring MVC, Spring Boot 3.x, Spring Security 6.x). The API acts as an **OAuth 2.0 Resource Server**, receiving JWT access tokens via HTTP `Authorization: Bearer`. This lesson explains everything from how `JwtDecoder` trusts public keys in a JWK Set to a zero-downtime signing key **rotation** strategy, complete with Java 17+ configurations, Spring Boot examples, and security tests. Do not confuse a Resource Server with an Authorization Server—the API only **verifies** tokens; it does not issue tokens or hold the identity provider's private signing key.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the parts of a JWT, why **both signature and claims** must be verified, and the role of `JwtDecoder` in Spring Security Servlet.
2. Distinguish **JWK** (a single key, typically a public key), **JWK Set/JWKS** (a set of keys), and `kid` (merely a key-selection hint), along with `alg` (algorithm) and `use`.
3. Choose between configuring `issuer-uri`, `jwk-set-uri`, or a custom `JwtDecoder`; understand the trade-offs of discovery, issuer constraints, audience, and timestamps.
4. Plan key rotation—**publish → sign with new key → wait for old tokens to expire → remove old key**—accounting for cache lifetimes and clock skew.
5. Troubleshoot `unknown kid`, unreachable JWKS endpoints, invalid signatures, wrong `iss`/`aud`, expired tokens, and compromised keys.
6. Separately test API **authorization** decisions, decoder signature/claims, and **real rotation against a remote JWK Set**, never treating mocked `jwt()` tests as proof that cryptography works.

## 2. Problem Statement: A Resource Server Receives a Bearer JWT

Example of a client calling an API:

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleS1iIn0...
```

The value after `Bearer` in this example is a truncated illustration, **not a complete JWT**. A compact JWS-signed JWT has three Base64URL parts:

```text
BASE64URL(JOSE_header).BASE64URL(claims).BASE64URL(signature)
```

The JOSE header may contain:

```json
{
  "typ": "JWT",
  "alg": "RS256",
  "kid": "key-b"
}
```

The payload contains claims: `iss` (issuer), `sub` (subject), `aud` (audience), `exp` (expiration), `nbf` (not before), `iat` (issued at), `scope` or `scp` depending on the identity provider contract.

**Core warning:** the first two parts are only **Base64URL-encoded**, not confidentially encrypted; anyone holding the token can decode its contents. A token does not become trustworthy simply because the string has JWT structure or `sub` looks like a real account. You must verify the signature using a trusted issuer's key **and** validate claims against the API's policy.

### Three Independent Questions to Answer

| Question | Mechanism | If Skipped |
| --- | --- | --- |
| Was the token signed by a trusted issuer with an appropriate key? | JWS signature, allowlisted keys and algorithms; `JwtDecoder` | Forged or tampered tokens may be accepted. |
| Does the token belong to **the right issuer, right API, and within lifetime**? | `iss`, `aud`, `exp`, `nbf`, and validators | Tokens from another app, another environment, or expired tokens may be accepted. |
| Is the caller authorized to invoke this endpoint? | `JwtAuthenticationConverter`/authority mapping and `authorizeHttpRequests` | Technically valid tokens lacking scope/role can still read data. |

**Bearer** means anyone holding the token can use it within its granted permissions. A signed JWT does not protect itself against theft or replay; you need TLS, secure storage, appropriate lifetimes, and revocation mechanisms when risk requires them.

## 3. Components in Spring Security Servlet

A normal request passes through the components in a simplified flow:

```mermaid
flowchart TD
    A["HTTP Authorization: Bearer JWT"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["JwtAuthenticationProvider"]
    C --> D["JwtDecoder / NimbusJwtDecoder"]
    D --> E["Read JOSE alg + kid"]
    E --> F["JWK Set from issuer/JWKS endpoint"]
    F --> G{"Signature + time + issuer + audience valid?"}
    G -- No --> H["Authentication failure → 401"]
    G -- Yes --> I["JwtAuthenticationConverter → authorities"]
    I --> J{"Endpoint authorization?"}
    J -- Missing scope/role --> K["403 Forbidden"]
    J -- Allowed --> L["Controller handles request"]
```

This is a conceptual diagram, not the full class/method call stack for every configuration.

**Specific roles:**

- `BearerTokenAuthenticationFilter` extracts the Bearer token according to configured HTTP authentication rules. It does not validate the JWT itself.
- `JwtAuthenticationProvider` uses `JwtDecoder` to verify the token and build the matching Spring Security authentication.
- `JwtDecoder` is the interface with `Jwt decode(String token) throws JwtException`; Spring Security typically uses `NimbusJwtDecoder` for JWS-signed JWTs.
- `NimbusJwtDecoder` uses Nimbus JOSE/JWK capabilities to select the matching key, verify the signature, and execute `OAuth2TokenValidator<Jwt>`.
- `JwtAuthenticationConverter` converts claims into a principal and granted authorities. By default it typically converts `scope` or `scp` into authorities prefixed with `SCOPE_`; custom role policies must be designed explicitly.
- `SecurityFilterChain` enforces rules like `hasAuthority("SCOPE_orders.read")`. A valid signature does not mean having permission.

In a resource server using only Bearer tokens and not relying on login cookies, `401 Unauthorized` generally indicates missing or unauthenticated credentials; `403 Forbidden` indicates authenticated but lacking permission for the resource. Applications with custom entry points or handlers may format error JSON differently.

## 4. JWK, JWK Set, kid, and Algorithms

### 4.1. JWK Describes a Key

A **JSON Web Key (JWK)** is a JSON representation of a cryptographic key in JOSE. A **JWK Set (JWKS)** contains a `keys` array:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-a",
      "use": "sig",
      "alg": "RS256",
      "n": "BASE64URL_MODULUS_A",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "key-b",
      "use": "sig",
      "alg": "RS256",
      "n": "BASE64URL_MODULUS_B",
      "e": "AQAB"
    }
  ]
}
```

This JSON snippet is an **illustrative schema**; the two `BASE64URL_MODULUS_*` strings merely mark modulus positions and are **not valid RSA keys**; real endpoints must publish standard Base64URL public key values.

Common fields:

| Field | Meaning |
| --- | --- |
| `kty` | Key type, e.g., `RSA` or `EC`. |
| `kid` | Key ID aiding key selection within the set; should be unique within the issuer's signing context at a given time. |
| `use` | Intended use, e.g., `sig` for signing/verifying; may be omitted depending on provider contract. |
| `alg` | Algorithm the key is used with, e.g., `RS256`; metadata does not replace the Resource Server's algorithm allowlist. |
| `n`, `e` | RSA public modulus and public exponent. |
| `crv`, `x`, `y` | Public parameters of an EC JWK when using appropriate algorithms. |
| `x5c` / `x5t` | May hold certificate chain/thumbprint; does not mean the API may trust an arbitrary CA supplied by a token. |

The Resource Server should fetch **public verification keys** from the JWKS. **Never publish** private fields such as RSA's `d` or symmetric secret `k` on a public JWKS. A signed JWT is not an encrypted JWT; never put PII or secrets in claims simply because a signature is present.

### 4.2. kid Is a Hint, Not Proof of Trust

When a token reports `kid=key-b`, the decoder uses it to look up a matching candidate in **the configured issuer's JWK Set**. A token must never be allowed to select an arbitrary key-download URL. Never build logic like:

```java
// Do not do this: anti-pattern example, NOT secure.
String jwksUrl = request.getParameter("jwks");
```

A client-sent token or HTTP request must never specify the trusted endpoint where the server downloads verification keys; doing so can cause SSRF or acceptance of attacker-controlled keys. JOSE headers such as `jku`, `x5u`, and `jwk`, even if supported by some library, must never be automatically treated as trusted sources outside an allowlist policy.

**Changing `kid` does not rotate the cryptographic key.** Two different keys can accidentally share the same `kid` due to operational error, causing stale caching and unpredictable verification failures. When rotating, generate **both a new key pair and a new kid**, and do not reuse kids prematurely.

### 4.3. alg Must Be Controlled by the Server

The `alg` header is data inside the JWT supplied by the client. The API must **restrict allowed algorithms** compatible with the issuer contract and key type. Never accept `alg: none` for signed access-token JWTs, and never dynamically switch or upgrade/downgrade between HS256 and RS256 based on an unverified header.

For RSA, `RS256` is RSA PKCS#1 v1.5 + SHA-256; `PS256` is RSA-PSS + SHA-256 and **they are not interchangeable**. For EC, `ES256` uses ECDSA P-256; the algorithm must match the issuer/key. If the provider changes algorithms during rotation, configure and test the Resource Server accordingly; **never open the allowlist to all algorithms** to mask deployment errors.

## 5. Configuring JwtDecoder: issuer-uri, jwk-set-uri, or a Custom Bean?

### 5.1. Using issuer-uri Only: Convenient Discovery

With a discovery-compatible OIDC/OAuth2 provider and metadata endpoint:

```properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://identity.example.org/realms/production
```

In Boot/Spring Security's default auto-configuration, the issuer's metadata locates the JWKS endpoint and the decoder sets up `iss` validation. When supported by the docs/provider and library, this is a simple option that avoids hardcoding the JWKS path.

**Availability consideration:** with issuer-discovery-based initialization, some versions/configurations may depend on metadata reachability at startup. Do not assume every variant boots cleanly when the issuer is offline; test the actual version's behavior.

### 5.2. issuer-uri + jwk-set-uri: No Discovery Needed at Startup

```properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://identity.example.org/realms/production
spring.security.oauth2.resourceserver.jwt.jwk-set-uri=https://identity.example.org/realms/production/protocol/openid-connect/certs
```

In appropriate auto-configuration setups, specifying `jwk-set-uri` explicitly tells the Resource Server the JWKS URL directly, avoiding startup metadata discovery dependency while **retaining issuer validation** via `issuer-uri`. When actually decoding a signed JWT, the API still needs the matching public key (from cache or the JWKS endpoint); skipping discovery does not eliminate network dependence on the IdP/JWKS.

**Common pitfall:** configuring only `jwk-set-uri` without enabling a proper issuer validator can leave the API failing to verify `iss` as expected. Similarly, a valid signature with an `aud` meant for another API is still a token that should be rejected.

### 5.3. Declaring a Custom JwtDecoder

When you need an algorithm allowlist, audience check, custom claim validation, or explicit control policies, declare a `JwtDecoder` bean. That self-managed bean owns all validators, so do not expect Boot auto-config properties to combine automatically on your behalf.

Pick **one primary decoder configuration point** per security chain/issuer; avoid declaring a custom bean while expecting Boot to silently wire another decoder. If there are **multiple issuers**, use a trusted issuer/tenant resolution design and validate each issuer separately; never create a single decoder that trusts every JWKS.

## 6. Runnable Example: Spring Boot Resource Server with NimbusJwtDecoder

The demo uses **Java 17+, Maven, Spring Boot 3.3.0 / Spring Security 6.x**. The API has two endpoints:

- `GET /public/ping`: no token required, returns `ok`.
- `GET /api/orders`: requires a token with a valid signature, `iss`, `aud`, valid lifetime, and `SCOPE_orders.read`; returns a string with the subject.

Calling `/api/orders` with a real token requires a **real Authorization Server** with an HTTPS JWKS issuing compatible tokens. The Maven project compiles standalone; `mvn test` below runs offline with mocked authentication and **does not prove IdP connectivity**. Replace every example domain with a valid issuer under your control when deploying.

### 6.1. Project Structure

```text
jwt-rotation-resource-server/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/jwt/
    │   │   ├── ResourceServerApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ApiController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/demo/jwt/
            ├── ResourceServerSecurityTest.java
            └── LocalSignatureTest.java
```

### 6.2. Maven Dependencies

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>jwt-rotation-resource-server</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

**`src/main/resources/application.properties`**

```properties
server.port=8080

# Trust configuration held by the SERVER, never taken from request/JWT headers.
app.security.jwt.issuer=https://identity.example.org/realms/production
app.security.jwt.jwk-set-uri=https://identity.example.org/realms/production/protocol/openid-connect/certs
app.security.jwt.audience=orders-api
```

The domains in this example are illustrative names and not a live IdP. Before testing real tokens, replace the three values with the issuer/JWKS/audience provided by your Authorization Server. Ensure `issuer` in config matches the token's `iss` claim **exactly**—including scheme, host, port, and path.

**`src/main/java/demo/jwt/ResourceServerApplication.java`**

```java
package demo.jwt;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceServerApplication.class, args);
    }
}
```

### 6.3. JwtDecoder Verifying Signature, Issuer, Audience, and Timestamp

**`src/main/java/demo/jwt/SecurityConfig.java`**

```java
package demo.jwt;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwk-set-uri}") String jwkSetUri,
            @Value("${app.security.jwt.audience}") String audience) {

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
                        "Audience is not accepted",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime, audienceValidator));

        return decoder;
    }
}
```

**Explanation of each key point:**

1. `withJwkSetUri(jwkSetUri)` specifies the server-configured trusted public key source. Nimbus uses the matching JWK Set to verify the token signature. **Never construct a JWKS URL from an unverified `kid`/`iss` or request parameter.**
2. `jwsAlgorithm(SignatureAlgorithm.RS256)` restricts the signing algorithm accepted by the decoder per the demo contract. If the IdP uses `PS256` or `ES256`, configure accordingly **after verifying the issuer's contract**.
3. `JwtValidators.createDefaultWithIssuer(issuer)` adds standard validators (including timestamps like `exp`/`nbf` per defaults and `iss`); `DelegatingOAuth2TokenValidator` combines that with `aud` validation.
4. Audience is treated as a **list**. Tokens whose `aud` targets another app are rejected even with a valid signature and issuer.
5. `hasAuthority("SCOPE_orders.read")` checks scope. Spring Security by default can map `scope`/`scp` from JWT to `SCOPE_...`, but if the IdP uses custom claims such as `roles`/`permissions`, write a tested `JwtAuthenticationConverter` or authorities converter and never blindly trust unfamiliar formats.
6. `STATELESS` suits pure Bearer APIs: each request authenticates by token without creating an application login session. `csrf.disable()` in **this demo is only appropriate because authentication does not rely on auto-attached cookies**. If the same chain has session cookies / browser forms or endpoints using ambient credentials, evaluate and keep appropriate CSRF protection rather than copying this config into a mixed app.
7. `oauth2ResourceServer(...jwt(...))` does not turn the API into an OAuth2 Client or Authorization Server. It neither issues tokens nor knows the private signing key.
8. When you declare `@Bean JwtDecoder` yourself, validation logic is that bean's responsibility. Do not expect Spring Boot to automatically add another audience validator to a custom bean.

**`src/main/java/demo/jwt/ApiController.java`**

```java
package demo.jwt;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {
    @GetMapping("/public/ping")
    public String ping() {
        return "ok";
    }

    @GetMapping("/api/orders")
    public String orders(@AuthenticationPrincipal Jwt jwt) {
        return "orders for " + jwt.getSubject();
    }
}
```

The controller intentionally reads only `sub` and does not return the token. Production systems need authorization on specific resources (for instance, each order belonging to the right tenant/account), since a scope only verifies broad access rights. A JWT subject is not necessarily a displayable username.

### 6.4. Running the Application and Testing Requests

In directory `jwt-rotation-resource-server`:

```bash
mvn test
mvn spring-boot:run
```

Test a request without a token:

```bash
curl -i http://localhost:8080/public/ping
```

Expected HTTP `200` and body:

```text
ok
```

Test a protected request:

```bash
curl -i http://localhost:8080/api/orders
```

Expected HTTP `401` with the appropriate Bearer challenge. Once you have a **real JWT** issued by the right issuer, with the required audience and scope:

```bash
curl -i http://localhost:8080/api/orders \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

On Bash, `$ACCESS_TOKEN` is an environment variable you supply safely from your test session; never write real tokens into READMEs, source code, git, or logs. With a valid token for subject `alice` and authority `SCOPE_orders.read`, the demo's body is:

```text
orders for alice
```

If the token is expired, has an invalid signature, wrong issuer/audience, or lacks scope, the response will be 401 or 403 depending on where it failed. Never let clients pick a JWK endpoint, switch algorithms, or disable validation just to "make the demo work."

## 7. Testing with MockMvc: Routing and Authorization

**`src/test/java/demo/jwt/ResourceServerSecurityTest.java`**

```java
package demo.jwt;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ResourceServerSecurityTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicPingWorksWithoutToken() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("ok"));
    }

    @Test
    void protectedEndpointRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validPrincipalWithScopeCanReadOrders() throws Exception {
        mvc.perform(get("/api/orders")
                .with(jwt()
                    .jwt(token -> token.subject("alice"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk())
            .andExpect(content().string("orders for alice"));
    }

    @Test
    void authenticatedButMissingScopeIsForbidden() throws Exception {
        mvc.perform(get("/api/orders")
                .with(jwt()
                    .jwt(token -> token.subject("alice"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_profile"))))
            .andExpect(status().isForbidden());
    }
}
```

These tests verify **authorization given a simulated JwtAuthenticationToken**, because `jwt()` from `spring-security-test` **skips signature parsing and does not call the remote JWKS**. Thus the 200/403 tests above cannot prove that signature, `iss`, or `aud` are verified properly. This is crucial for QA: security chain tests must be separated from decoder tests.

## 8. Testing JwtDecoder with Locally Generated RSA Keys

You can verify **real signatures and claims** offline by generating an RSA key pair in JUnit, signing tokens with `NimbusJwtEncoder`, and decoding with `NimbusJwtDecoder.withPublicKey`. This test **does not call a remote JWK Set**, so it does not cover JWKS caching/rotation; it provides independent evidence of signature validation.

**`src/test/java/demo/jwt/LocalSignatureTest.java`**

```java
package demo.jwt;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.proc.SecurityContext;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class LocalSignatureTest {
    private static final String ISSUER =
        "https://identity.example.org/realms/production";

    private static KeyPair rsa() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    private static String signedToken(
            KeyPair pair, String audience) {
        RSAKey key = new RSAKey.Builder(
                (RSAPublicKey) pair.getPublic())
            .privateKey((RSAPrivateKey) pair.getPrivate())
            .keyID("test-rsa-a")
            .build();

        ImmutableJWKSet<SecurityContext> source =
            new ImmutableJWKSet<>(new JWKSet(key));
        JwtEncoder encoder = new NimbusJwtEncoder(source);

        Instant now = Instant.now();
        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(ISSUER)
            .subject("alice")
            .audience(List.of(audience))
            .issuedAt(now)
            .expiresAt(now.plusSeconds(300))
            .claim("scope", "orders.read")
            .build();

        JwsHeader header = JwsHeader
            .with(SignatureAlgorithm.RS256)
            .keyId("test-rsa-a")
            .build();

        return encoder.encode(
            JwtEncoderParameters.from(header, claims))
            .getTokenValue();
    }

    private static NimbusJwtDecoder decoder(RSAPublicKey publicKey) {
        NimbusJwtDecoder d = NimbusJwtDecoder
            .withPublicKey(publicKey)
            .build();

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token", "Audience mismatch", null));

        d.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(ISSUER), audience));

        return d;
    }

    @Test
    void validSignatureIssuerAndAudienceAccepted() throws Exception {
        KeyPair pair = rsa();
        String token = signedToken(pair, "orders-api");

        Jwt jwt = decoder((RSAPublicKey) pair.getPublic()).decode(token);
        assertEquals("alice", jwt.getSubject());
    }

    @Test
    void validSignatureWithWrongAudienceRejected() throws Exception {
        KeyPair pair = rsa();
        String token = signedToken(pair, "another-api");

        assertThrows(JwtException.class, () ->
            decoder((RSAPublicKey) pair.getPublic()).decode(token));
    }

    @Test
    void signatureFromDifferentKeyRejected() throws Exception {
        KeyPair signer = rsa();
        KeyPair unrelated = rsa();
        String token = signedToken(signer, "orders-api");

        assertThrows(JwtException.class, () ->
            decoder((RSAPublicKey) unrelated.getPublic()).decode(token));
    }
}
```

**Evidence produced by this test:** valid issuer/audience and valid signature are accepted; wrong audience is rejected despite a valid signature; mismatched public key rejects the signature. This uses real RSA cryptography in the JVM, not mocked `jwt()`. **It does not yet prove** JWKS HTTP fetching, JWK cache TTL, `kid` switching, or network availability of new keys.

Default Maven tests run on Java 17 without needing real provider keys because the test generates its own RSA key pairs. The standard JUnit outcome for success is that the test suite **passes**; do not assume a fixed Maven log line count across environments or versions.

## 9. Signing Key Rotation: Running Old and New Keys in Parallel

Signing keys are part of the security contract between the **Authorization Server** and the **Resource Server**. The authorizer holds the **private key** to sign tokens; the Resource Server retrieves the **public key** from the JWKS to verify them. Rotation is the process of changing keys without accidentally causing all still-valid tokens to fail with 401.

### 9.1. Safe Rollout Timeline

Suppose the issuer currently signs tokens with an RSA key having `kid=key-a` and JWT access tokens have a maximum lifetime of 15 minutes. The issuer prepares a new `key-b`.

| Phase | Action at Authorization Server / JWKS | Resource Server Behavior |
| --- | --- | --- |
| T0 — steady state | Signs with private `key-a`; JWKS publishes public `key-a`. | Tokens with `kid=key-a` verify with key-a. |
| T1 — pre-publish | JWKS publishes **both key-a and key-b**, while continuing to sign with key-a. | Decoders may pre-fetch key-b on refresh/cache; old tokens remain valid. |
| T2 — switch signing | Issuer begins signing new tokens with private `key-b`; JWKS still contains **both public keys**. | Old key-a tokens and new key-b tokens are both accepted when claims are valid and caches hold the keys. |
| T3 — wait out the window | Stops issuing new key-a tokens; keeps both public keys across old-token TTL, clock skew, JWKS propagation/cache, and system delays. | Key-a tokens still valid per `exp` verify; key-b tokens keep working. |
| T4 — normal retirement | Removes public key-a once certain no valid key-a tokens remain to support; continues signing with key-b. | Caches may not refresh immediately. Removing a key does not guarantee all nodes immediately reject old tokens. |

**Never reverse the order:** if you switch signing to `key-b` before the JWK Set publishes key-b, the Resource Server can return `401 invalid_token` because `kid` is unrecognized. If you remove `key-a` too early, unexpired key-a tokens can suddenly fail with 401 when caches refresh.

With the 15-minute TTL example, do not conclude “waiting exactly 15 minutes is enough”—consider **the last token signed with key-a**, validator clock skew, and cache/CDN layers plus JWKS refresh. There is no fixed minute formula for every deployment; measure the actual issuer policy and maximum token lifetime.

### 9.2. How Decoders Select Keys and Cache in Practice

When receiving a JWT with `kid=key-b`, the JOSE/JWK library looks for a key with matching `kid`/`kty`/`alg`/`use` in the trusted key set. Depending on the Nimbus/Spring Security version and cache implementation, an unseen `kid` may trigger a JWKS reload; **never rely on an untested fixed refresh interval**.

Important edge cases:

- JWKS is cached in the **Resource Server**, and possibly in CDNs/proxies or network clients. When the issuer updates JWKS, nodes may observe the new set at different times.
- If a provider reuses the **same kid** for a new key, stale caches can make new tokens fail signature validation even though `kid` looks “right.” Always use a new kid and publish-before-use.
- When removing key-a, caches may continue holding public key-a for a while. Tokens past `exp` must still be rejected by the timestamp validator, but **do not treat JWKS removal as instant revocation**.
- If the JWKS endpoint goes offline while the decoder already holds cached keys, some tokens can still verify; tokens using an unseen kid or after cache expiry will fail. Build availability tests for warm-cache, cold-start, and unknown-kid cases.
- Even when JWK Set comes over HTTPS with valid TLS, **issuer metadata/JWKS endpoints must be server-configured trusted sources**. Never turn an unverified token into an arbitrary URL to avoid SSRF/remote key injection.
- Never let all nodes hammer the JWKS continuously on errors; combine caching, timeouts, bounded retries/backoff, and monitoring per library configuration.

### 9.3. Scheduled Rotation Differs from Handling a Compromised Key

**Normal rotation:** the issuer can keep the old key long enough for live tokens to keep working. Users experience minimal disruption.

**Compromised private key incident:** priority shifts to blocking anyone holding the leaked key from minting forged tokens. You may need to **stop trusting key-a early**, even if valid old tokens get 401s, using emergency token/session revocation/invalidation and customer notifications. Because of distributed caches, removing a key from JWKS **does not automatically guarantee immediate rejection** on every Resource Server. If risk demands immediate effect, use configuration push/coordination, planned forced cache refreshes/restarts, denylists/epochs, or token introspection depending on architecture, and verify post-rollout.

Private signing keys **never** live in Resource Servers or API repos. Key storage must be tightly controlled (such as KMS/HSM or appropriate secret management); permissions for issuing, auditing, rotating, and reading public JWKS must be separated.

### 9.4. Key-a / Key-b Timeline Diagram

```mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant JWKS as JWKS endpoint
    participant RS as Resource Server
    Note over AS,RS: T1 — pre-publish public key-b
    AS->>JWKS: Public keys [key-a, key-b]
    AS-->>RS: Old token signed with key-a
    RS->>JWKS: Fetch/refresh public key-a
    JWKS-->>RS: Keys [key-a, key-b]
    RS->>RS: Verify key-a token
    Note over AS,RS: T2 — start signing with key-b
    AS-->>RS: New token signed with key-b
    RS->>JWKS: Lookup/refresh if needed
    JWKS-->>RS: Public key-b
    RS->>RS: Verify key-b token
    Note over AS,RS: T3 — wait for key-a tokens to expire and caches to sync
    AS->>JWKS: Publish public key-b only
```

The diagram does not show every client-forwarded token or actual refresh count. It illustrates **the principle that two public keys coexist during the transition window**.

## 10. Plain Java 17 Example: Valid/Invalid Signatures When Changing Public Keys

The snippet below runs **without Spring, Maven, an IdP, or a network**. It illustrates the mathematical basis of RSA rotation: a signature created by private `key-a` verifies only with public `key-a`, not with public `key-b`. This is **not** a production JWT parser/JWKS client implementation, as hand-rolling a production JWT verifier is error-prone.

Save as **`KeyRotationIntuition.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.Signature;
import java.util.LinkedHashMap;
import java.util.Map;

public class KeyRotationIntuition {
    static KeyPair generate() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    static byte[] sign(KeyPair pair, byte[] data) throws Exception {
        Signature signature = Signature.getInstance("SHA256withRSA");
        signature.initSign(pair.getPrivate());
        signature.update(data);
        return signature.sign();
    }

    static boolean verify(PublicKey publicKey, byte[] data, byte[] signature)
            throws Exception {
        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(publicKey);
        verifier.update(data);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        KeyPair oldKey = generate();
        KeyPair newKey = generate();
        byte[] payload = "signed payload".getBytes(StandardCharsets.UTF_8);
        byte[] sigOld = sign(oldKey, payload);
        byte[] sigNew = sign(newKey, payload);

        Map<String, PublicKey> published = new LinkedHashMap<>();
        published.put("key-a", oldKey.getPublic());
        System.out.println("before: old token passes = "
                + verify(published.get("key-a"), payload, sigOld));

        published.put("key-b", newKey.getPublic());
        System.out.println("overlap: old token passes = "
                + verify(published.get("key-a"), payload, sigOld));
        System.out.println("overlap: new token passes = "
                + verify(published.get("key-b"), payload, sigNew));
        System.out.println("wrong key verifies old signature = "
                + verify(published.get("key-b"), payload, sigOld));

        published.remove("key-a");
        System.out.println("after retirement: old kid present = "
                + published.containsKey("key-a"));
    }
}
```

Compile/run with Java 17+:

```bash
javac KeyRotationIntuition.java
java KeyRotationIntuition
```

**Exact stdout** (independent of random RSA key pairs since it only prints booleans):

```text
before: old token passes = true
overlap: old token passes = true
overlap: new token passes = true
wrong key verifies old signature = false
after retirement: old kid present = false
```

Note the differences between this demo and real JWTs: there is no `iss`, `aud`, `exp`, JWKS kid lookup, HTTPS, caching, or CSRF/authorization; this code only explains *why* two public keys must coexist while tokens signed by two different private keys remain in circulation.

## 11. Testing Real Rotation Against an HTTP JWKS

To prove the key rotation cycle on a Resource Server, you need integration-level tests against a controlled **HTTP JWKS test endpoint** and JWTs signed by two distinct RSA keys. You can use a local mock HTTP server/WireMock/MockWebServer; the test must invoke a **real JwtDecoder with a JWK Set URI** rather than `jwt()`.

A minimal test plan:

| Scenario | JWKS Published by Test Server | Token | Expected Outcome |
| --- | --- | --- | --- |
| Baseline | `[key-a]` | Signed with key-a, `kid=key-a`, valid claims | Decodes successfully. |
| Prepublish | `[key-a,key-b]` | Old key-a token | Still valid. |
| After switch | `[key-a,key-b]` | New key-b token | Valid once decoder loads key-b. |
| Forged signature | `[key-a,key-b]` | Header `kid=key-b` but signed with unrelated private key | Rejected. |
| Wrong issuer | `[key-a,key-b]` | Valid signature but wrong `iss` | Rejected. |
| Wrong audience | `[key-a,key-b]` | Valid signature but `aud` is another API | Rejected. |
| Expired | `[key-a,key-b]` | `exp` in the past beyond clock skew | Rejected. |
| JWKS outage | Network endpoint stopped | Cached token / unseen kid | Observe behavior per specific cache; **never assume identical outcomes**. |
| Retire | `[key-b]`, old cache refreshed/evicted | key-a token | Rejected because trusted key is gone, even if unexpired. |
| Wrong algorithm | `[key-a,key-b]` | Header `alg` outside allowlist | Rejected. |

To reliably test “retire,” control the cache/lifecycle or instantiate a fresh decoder after the mock JWKS changes. If a cache still retains key-a, the test may keep accepting key-a tokens; that is **cache behavior** to observe and design for, not a reason to weaken validation. Never use arbitrary `Thread.sleep` durations to guess unconfigured cache TTLs.

When using Spring Boot in integration tests, point `app.security.jwt.jwk-set-uri` at the local mock server URI before initializing `JwtDecoder`. Clearly document that the test verifies **remote JWKS** (unlike MockMvc `jwt()` and `withPublicKey` earlier). Each test should generate fresh key pairs, distinct kids, and separate issuer/audience policies from cache testing.

## 12. Distinguishing Key Rotation, Token Revocation, and Claim Versioning

Rotating key pairs is an operational mechanism for **trust/key material**, not a simple fix for every authorization problem:

- **Key rotation:** changes signing keys and public verification keys; old tokens can remain valid until `exp` while the old key remains trusted.
- **Revoking an access token:** requires invalidating one or a group of tokens **before `exp`**. Already-issued self-contained JWTs do not query revocation status automatically. You need short lifetimes, a `jti` denylist, session/version epochs, introspection, or a token architecture suited to the risk level.
- **Permission changes:** scopes/roles in a JWT may already have been issued; the Resource Server normally does not see permission changes immediately without live state/revocation checks. Consider token TTL and local authorization data.
- **Changing signing algorithms:** is a contract change between issuer and verifier. Moving from RSA to EC/PSS requires tested allowlist updates, public key types, and claim validation—never let tokens decide.
- **Changing issuers / multi-tenancy:** each issuer must bind to its own key set and matching issuer/audience validators; never use an uncontrolled shared JWKS to validate arbitrary tokens.

A token with a nonexistent `kid` **must never** be “temporarily” accepted while JWKS fails. Failing closed on credential verification is fundamental: return an error and monitor rather than bypassing signature checks.

## 13. Safe Operations: JWKS Endpoints, Caching, Latency, and Alerts

### 13.1. Trusted Sources and Transport

1. Use **HTTPS** for JWKS and issuer metadata in production; verify TLS certificates, DNS, and endpoint ownership.
2. Restrict Resource Server outbound HTTP to **configured/allowlisted JWKS endpoints**; never fetch URLs from `jku`/`x5u` or client requests.
3. JWKS publishes **public keys only**; private signing keys remain in the IdP/KMS/HSM, never served via public endpoints and never baked into Resource Server container images.
4. Proxies/CDNs caching JWKS need sensible TTL/ETag policies. During rotation, verify cache state at each tier; during incidents, changing the origin response alone may not suffice.
5. Enforce timeouts, connection limits, bounded retries/backoff, and monitor HTTP 404/5xx/TLS errors per actual library/client behavior. Never let bad-token requests trigger a JWKS stampede.

### 13.2. Monitoring

Record error categories with **tokens and sensitive data redacted**:

- `invalid_token` broken down by parse, signature, missing key/unknown kid, timestamp, issuer, or audience.
- JWKS fetch latency, HTTP errors, cache hit/miss/refresh, and post-rotation request counts where instrumented.
- 401/403 rates by endpoint and deployment version, separating authorization failures from authentication failures.
- Distribution of `kid` in tokens **using controlled/normalized buckets** to watch key-a drop off; since the kid header comes from untrusted tokens, never use it as an unbounded/high-cardinality metric label.
- Time of last token issued with the old key, maximum JWT TTL, clock skew, and cache expiry to pick the retirement point.

**Never log raw JWTs, Authorization headers, private keys, unnecessary internal public keys, token exchanges, or PII payloads.** You may log error category, allowlisted verified issuer/tenant, endpoint, and controlled correlation IDs.

### 13.3. Runbook for Preparing a Rotation

1. Confirm issuer/JWKS endpoints and dependent API scope; inventory Resource Servers, gateways, caches, and decoder libraries.
2. Generate a new key pair in key management with a **new kid**; verify JWKS publishes **public** key-b before enabling new signing.
3. Monitor multiple Resource Servers: confirm every node can load key-b while still verifying key-a tokens. Run staging tests with both token types.
4. Switch the Authorization Server signing key to key-b while keeping key-a in JWKS.
5. Watch 401 rates, unknown kid, signature invalid, cache fetches, and any tokens still signed with key-a from stale issuer instances (avoid split-brain rollouts).
6. Wait out max token TTL + skew + reasonable replication/cache windows; confirm all issuer instances have stopped signing with key-a.
7. Remove key-a per policy, verify all nodes after cache refresh, confirm 401 for retired tokens and 200 for valid key-b tokens.
8. Record audit logs, rollback plans, timestamps, and approvers; never re-enable an old private key if rotation was triggered by key compromise.

## 14. Common Failures and How to Diagnose Them

| Symptom | Causes to Check | Remediation |
| --- | --- | --- |
| All tokens return 401 right after deploy | Wrong issuer/JWKS, unconfigured audience, algorithm mismatch, TLS/DNS/proxy failure. | Compare `iss`/`aud` claims, decoder config, and real JWKS; never disable validation. |
| Only tokens with the new `kid` return 401 | JWKS has not published new key, CDN cache, node has not refreshed, duplicate kid. | Publish-before-sign, inspect JWKS from each node, use a unique new kid. |
| Unexpired key-a tokens return 401 after rotation | Public key-a removed too early; cache refreshed to JWKS containing only key-b. | Maintain sufficient overlap during normal rotation; distinct from emergency revocation. |
| Key-a tokens still accepted after key removal | Decoder/proxy retains stale cache or token still has a valid signature under cached key. | Verify cache refresh/eviction and token TTL; deploy active revocation if instant blocking is needed. |
| Valid signature yet wrong audience | Decoder checks only signature or issuer. | Add an `aud` validator with the right application audience. |
| Test-environment tokens accepted in prod | Shared key/issuer or missing issuer/audience validation, overly broad trust. | Isolate issuers/keys/audiences per environment and validate strictly. |
| HTTP 403 despite valid token | Missing `SCOPE_orders.read`, converter expects different claims, or overly strict authorization rule. | Check authority mapping and endpoint rules; do not suspect signature once authenticated. |
| Signature invalid after algorithm change | Decoder allowlists RS256 while issuer signs PS256/ES256. | Align algorithm contract and tests; never allow all algorithms. |
| Random 401s across pods | Different JWKS/caches, different proxies, clock skew, out-of-sync issuer nodes. | Compare kid, time, JWKS, and cache per pod; sync clocks and rollouts. |
| Startup fails when IdP is offline | Discovery at startup or specific network dependency. | Consider issuer-uri + jwk-set-uri, readiness/startup strategy, and system caching. |
| Can decode JWT payload yet cannot call API | Base64URL decoding does not mean the token is signed or authorized. | Use `JwtDecoder` for full verification; verify claims and authorities. |

### Ordered Debugging Process

1. Record request method/path, 401 vs 403 response, and server error category; **never expose raw tokens**.
2. Verify the token sent to the API is the proper access token type for the Resource Server, not an ID Token or refresh token.
3. Safely inspect `alg`/`kid` headers and `iss`/`aud`/`exp` claims to narrow down the error category; remember they are untrusted until verified.
4. Confirm the server-configured JWKS source, TLS, HTTP status, key `kid`, `kty`, and `alg` compatibility.
5. If signature passes, check issuer/audience/time validators; if the JWT authenticates yet returns 403, check scope/authority mapping and data permissions.
6. If it occurs only after rotation, cross-check the publish/sign/retire timeline, cache TTL, and active signing issuer instances.
7. Write regression tests for both key-a/key-b and negative claim cases; avoid “fixes” that disable verifiers or widen trust.

## 15. Self-Check Questions

**1. Should private keys be published in JWKS so the Resource Server can verify JWTs?**

**No.** With asymmetric signatures, the issuer uses the private key to sign and publishes the public key for Resource Servers to verify. Putting private keys in JWKS destroys the entire security boundary.

**2. Does a JWT's `kid` guarantee the token came from the right issuer?**

**No.** A client can put any `kid` it wants. The decoder only uses kid to pick a key from **the trusted configured key set**, and must still verify signature and claims.

**3. Why is configuring only `jwk-set-uri` insufficient?**

Having a key URL does not mean issuer, audience, and necessary business constraints are validated. You must ensure those checks exist in the decoder and authorization rules.

**4. When rotating keys, can the old public key be removed from JWKS immediately?**

In **normal rotation**, no, if unexpired tokens signed by the old key still exist. Overlap is required. In a **compromised key incident**, disruption may be acceptable to cut risk, but you must also handle caching and active revocation.

**5. Does a `with(jwt())` test prove JWKS rotation works?**

No. It tests authorization with a mocked principal; it does not exercise JWS signatures, remote JWKS, caching, or the decoder's issuer/audience validation.

**6. Does deleting key-a from JWKS immediately invalidate all key-a tokens?**

Not reliably. Some decoders may still cache public key-a. It is not a guaranteed real-time revocation mechanism.

## 16. Takeaways

- `JwtDecoder` authenticates **JWTs** using public keys from a JWK Set and claim validators; it never issues tokens by default.
- `kid` is a hint to **select** a key within a trusted set; `alg` must be allowlisted; **signature + issuer + audience + lifetime + authorization** are independent layers.
- Use `issuer-uri` to leverage discovery when appropriate; add `jwk-set-uri` when you want explicit control over the JWKS source and fewer startup discovery dependencies; with a custom bean, configure validators accurately yourself.
- Normal rotation always follows the order: **publish new public key first → sign new tokens → overlap old/new keys → retire old key after the validity window expires**.
- JWKS caching/timeouts/proxies introduce lag into key changes; never promise instant rollback/retirement/revocation without verified mechanisms.
- Test all three tiers: **MockMvc authorization**, **decoder signature/claims**, and **controlled real/mock remote JWKS integration**.

**Design principle:** A Resource Server does not trust self-declared JWT headers; it trusts **server-configured issuers and key sources**, verifying cryptography and claims before making authorization decisions. Signing keys have a lifecycle independent of user sessions and token revocation; operate rotation using token TTL and cache data, not just by changing a `kid` field.