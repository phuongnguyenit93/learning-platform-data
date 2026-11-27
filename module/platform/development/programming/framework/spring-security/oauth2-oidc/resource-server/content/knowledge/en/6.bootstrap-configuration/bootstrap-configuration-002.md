# Resource Server Dependencies, JOSE, and Security Testing

A Spring Boot application protecting APIs with **OAuth 2.0 Bearer Access Tokens** needs three parts working in harmony: **Resource Server dependencies**, **JOSE/JWT** tooling matching how tokens are issued, and **security tests** proving the application only accepts valid tokens with the right audience and sufficient permissions.

This lesson goes from initialization to testing, using **Spring Boot 3.x, Spring Security 6.x, Java 17+, and Spring MVC (Servlet)** as examples. If using a newer version or another branch, cross-check the configuration properties and starters supported by that version. The examples illustrate an orders API receiving Bearer tokens issued by an external Authorization Server.

## 1. Identify the Right Role Before Adding Dependencies

In an OAuth 2.0/OIDC system:

| Component | Role | Common Spring Security configuration |
| --- | --- | --- |
| **Authorization Server / OpenID Provider** | Authenticates, authorizes, and issues tokens. | Separate service such as Keycloak or Spring Authorization Server. |
| **OAuth 2.0 Client / OIDC Client** | Redirects users to log in, receives authorization codes and tokens. | `spring-boot-starter-oauth2-client`, `oauth2Login()`. |
| **Resource Server** | Receives Bearer Access Tokens in HTTP requests, validates tokens and API access permissions. | `spring-boot-starter-oauth2-resource-server`, `oauth2ResourceServer()`. |

Example client call:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN
Accept: application/json
~~~

The Resource Server must determine: whether the token is valid, **which issuer** issued it, whether it is still valid in time, whether **audience** includes this API, and whether it has **scope orders.read**. Then the API can also check permissions for individual orders or tenants.

An API that only accepts Bearer tokens **does not require** an OIDC login screen or `oauth2Login()`. Conversely, OIDC login on a website **does not automatically turn every API request into a valid Bearer request**. If one backend handles both, you must configure the appropriate security chain for each area.

## 2. Dependencies for the Resource Server

### 2.1. Gradle

In a Spring Boot project whose dependency versions are already managed via plugin/BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Meaning:

- **spring-boot-starter-web**: Spring MVC, HTTP controllers, and servlet runtime.
- **spring-boot-starter-security**: Spring Security, filter chain, and authorization mechanism.
- **spring-boot-starter-oauth2-resource-server**: Bearer token authentication; in common Spring Boot 3.x releases, the starter also pulls in the **JOSE** module for JWT support.
- **spring-boot-starter-test**: JUnit 5, Spring Test, and assertion utilities.
- **spring-security-test**: integrates security with MockMvc and request post processors like `jwt()`, `opaqueToken()`.

You do not need to manually specify versions for individual Spring Security artifacts when using Spring Boot dependency management. Mixing incompatible module versions easily causes startup or test failures.

### 2.2. Maven

Equivalently, in a project using the Spring Boot parent or BOM:

~~~xml
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
~~~

Choose only **Gradle or Maven** according to your project's build tool.

### 2.3. Resource Server and JOSE Are Two Different Modules

When configuring Spring Security with manual modules instead of a Boot starter, JWT scenarios usually require both:

~~~groovy
dependencies {
    implementation 'org.springframework.security:spring-security-oauth2-resource-server'
    implementation 'org.springframework.security:spring-security-oauth2-jose'
}
~~~

| Module | Responsibility |
| --- | --- |
| **spring-security-oauth2-resource-server** | Handles Bearer token filtering, request authentication, Resource Server configuration, and SecurityContext integration. |
| **spring-security-oauth2-jose** | Supports JWT/JWS, decoders, signature and claims processing; uses appropriate JOSE/JWT libraries. |

If you already added the Boot starter and the dependency tree contains JOSE, **do not declare it twice**. If you only add `spring-security-oauth2-resource-server` manually and forget JOSE, JWT verification may lack required classes.

With **opaque tokens**, the Resource Server typically uses introspection instead of a JWT decoder. Even though the starter may transitively include JOSE, the presence of that JAR does not force the application to decode JWTs.

Reference commands to inspect the dependency tree:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./mvnw dependency:tree
~~~

On Windows you can use `.\gradlew.bat` or `.\mvnw.cmd` depending on the project. These two commands are a **dependency inspection method**, not a mandatory coding step.

## 3. JOSE, JWT, JWS, JWE, JWK, and JWA

**JOSE** (JSON Object Signing and Encryption) is a family of specifications for representing, signing, and encrypting JSON data. Common terms:

| Term | Description | Role in Resource Server |
| --- | --- | --- |
| **JWT** (JSON Web Token) | A token carrying claims such as issuer, subject, audience, expiration, and scope. | Payload describing authentication/authorization details carried by the token. |
| **JWS** (JSON Web Signature) | Represents data and a signature/MAC to verify integrity and signer authenticity. | Digitally signed JWT Access Tokens commonly use JWS compact serialization. |
| **JWE** (JSON Web Encryption) | Represents encrypted data to keep content confidential. | Not decrypted by default merely by enabling `oauth2ResourceServer().jwt()`. |
| **JWK** (JSON Web Key) | Represents a key in JSON format. | A JWK Set endpoint can publish public keys to verify signatures. |
| **JWA** (JSON Web Algorithms) | Set of algorithms used for JWS/JWE. | For example RS256; the verifier must restrict trusted algorithms. |

A JWT signed in JWS compact format typically has three parts:

~~~text
BASE64URL(JOSE_HEADER).BASE64URL(JWT_CLAIMS).BASE64URL(SIGNATURE)
~~~

Example JOSE Header:

~~~json
{
  "alg": "RS256",
  "kid": "rsa-key-2026",
  "typ": "at+jwt"
}
~~~

Example Access Token payload claims:

~~~json
{
  "iss": "https://identity.example.test/realms/demo",
  "sub": "employee-123",
  "aud": ["orders-api"],
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893456000,
  "scope": "orders.read"
}
~~~

**alg**, **kid**, and **typ** are header parameters, not JWT claims. **iss**, **sub**, **aud**, **exp** are claims; **scope** is a field commonly used in the OAuth Access Token profile. These two JSON blocks are illustrative examples and do not constitute a validly signed JWT.

**A signed JWT is not encrypted.** The JWS payload content can be read after Base64url decoding. Do not place private keys, passwords, or unnecessary personal data in claims.

### 3.1. Asymmetric Keys and JWK Set

When an issuer signs Access Tokens with RS256:

1. The Authorization Server holds the **private key** for signing.
2. The Resource Server uses the corresponding **public key** to verify.
3. Public keys may be published as a JWK Set at an HTTPS address configured by a trusted system.
4. The **kid** header helps select the key in the JWK Set, especially during key rotation.

Illustrative Keycloak URI example:

~~~text
https://identity.example.test/realms/demo/protocol/openid-connect/certs
~~~

The Resource Server **does not need** to hold the private key to verify asymmetric signatures. Never blindly trust a JWK address suggested by a client inside an unverified token; always obtain it from trusted issuer/discovery or configuration.

The algorithm declared in the `alg` header **is not automatically permitted**: the decoder configuration must restrict allowed algorithms and trusted keys. Never accept `alg: none` or switch algorithms based on untrusted data.

### 3.2. Bearer JWT Processing Pipeline

~~~text
HTTP Authorization: Bearer <token>
             |
             v
BearerTokenAuthenticationFilter
             |
             v
JwtAuthenticationProvider / JwtDecoder
             |
             +-- verify signature with trusted key
             +-- verify iss, exp, nbf per configuration
             +-- verify aud for this API
             +-- verify additional profile/type/claims if needed
             |
             v
JwtAuthenticationToken
             |
             v
AuthorizationFilter / Method Security
             |
             +-- sufficient scope and resource permissions -> controller
             +-- token unauthenticated -> typically 401
             +-- valid token but insufficient permissions -> typically 403
~~~

A JWT with a valid signature can still have the **wrong audience**, be expired, or lack the required scope. A valid signature does not replace authorization.

## 4. Configuring a JWT Resource Server

### 4.1. Minimal Configuration with Issuer and Audience

Example `src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/demo
          audiences:
            - orders-api
~~~

- **issuer-uri** specifies the issuer trusted by the Resource Server; the decoder can use appropriate discovery mechanisms to locate metadata/JWK Set.
- **audiences** requires the token to be issued for **orders-api**. Some Spring Boot versions support this property directly; on versions that do not, use a custom audience validator.
- The Spring Security JWT decoder verifies the signature, time constraints, and issuer as configured. **Do not assume the API automatically checks audience without confirming the actual configuration or validator.**

An Authorization Server can issue tokens intended for multiple APIs. If an API does not validate audience, it risks accepting tokens meant for a different system.

### 4.2. Explicit JWK Set URI Configuration

When the JWK Set URI is known and you want to avoid relying on metadata discovery every time the decoder is initialized:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/demo
          jwk-set-uri: https://identity.example.test/realms/demo/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

Keep **issuer-uri** to validate the **iss** claim. Configuring `jwk-set-uri` tells the Resource Server where to fetch public keys; it **does not replace issuer validation**. When metadata/JWKs are fetched, cached, and refreshed depends on the decoder and the version in use.

### 4.3. Defining a Custom Audience Validator When Needed

This is an **alternative** when the Boot version does not provide `audiences` or the application has custom policies:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtValidationConfig {

    private static final String ISSUER =
        "https://identity.example.test/realms/demo";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(ISSUER).build();

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Unexpected token audience",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audience));

        return decoder;
    }
}
~~~

`JwtValidators.createDefaultWithIssuer` preserves standard issuer and timestamp checks; the custom validator adds audience checking. If you define your own `JwtDecoder`, Spring Boot may no longer use the auto-configured decoder. **Required validators must live inside the decoder actually in use.** When deploying, externalize issuer/audience as environment-based configuration rather than hardcoding them like in this learning example.

## 5. SecurityFilterChain and Sample API

Example pure Bearer API that does not use session cookies for authentication:

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
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

- `oauth2ResourceServer(...jwt(...))` configures Spring Security to authenticate Bearer JWTs.
- `SessionCreationPolicy.STATELESS` indicates the API does not rely on HTTP sessions.
- `csrf(...disable)` is only appropriate in this **pure Bearer-header API** example. For web apps authenticating via cookies, evaluate CSRF separately.
- `GET /api/orders` requires **SCOPE_orders.read**; `POST /api/orders` requires **SCOPE_orders.write**.
- `anyRequest().denyAll()` locks down endpoints not explicitly declared in the example.

Spring Security normally maps scopes in a JWT, such as `"scope": "orders.read orders.write"`, into authorities **SCOPE_orders.read** and **SCOPE_orders.write**. For custom claims like `roles` or `permissions`, a custom conversion rule is required, and it must not grant all permissions by default.

Sample controller:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrdersController {

    @GetMapping
    Map<String, Object> list(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
            "subject", jwt.getSubject(),
            "orders", List.of());
    }

    @PostMapping
    ResponseEntity<Map<String, String>> create() {
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(Map.of("status", "created"));
    }
}
~~~

This is a learning controller and does not yet handle data persistence or order ownership. A real system must also verify tenant, owner, and business rules after the token is authenticated.

## 6. Opaque Token: Does Not Use a JOSE Decoder Like JWT

Not every Access Token is a JWT. If the Authorization Server issues **opaque tokens**, the API typically calls an **introspection endpoint** to learn whether the token is `active` and what attributes/permissions it carries.

Example configuration, with introspection credentials supplied via environment variables:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example.test/oauth2/introspect
          client-id: REPLACE_WITH_ENV_CONFIGURATION
          client-secret: REPLACE_WITH_ENV_CONFIGURATION
~~~

Both placeholders must be replaced with a secure secret configuration mechanism; never commit real client secrets to source control. In `SecurityFilterChain`, the Resource Server branch uses:

~~~java
.oauth2ResourceServer(oauth ->
    oauth.opaqueToken(Customizer.withDefaults()))
~~~

This is a replacement snippet inside the HttpSecurity DSL, not a standalone Java file.

| JWT | Opaque token |
| --- | --- |
| Uses JwtDecoder and JOSE/JWS to verify signatures. | Uses introspection to validate tokens with the issuer. |
| Can be verified locally using an available public key. | Typically depends on a configured introspection endpoint. |
| Principal is usually `Jwt`. | Principal is usually `OAuth2AuthenticatedPrincipal`. |
| MockMvc provides `jwt()`. | MockMvc provides `opaqueToken()`. |

Do not enable `jwt()` and expect an opaque token to be decoded. Likewise, an API receiving JWTs should not randomly switch to introspection if the issuer does not support it.

## 7. Two Security Testing Layers Must Be Kept Separate

**Authorization testing** asks: does the API block unauthorized requests properly, and allow the right HTTP methods/scopes?

**Token validation testing** asks: does JwtDecoder reject forged signatures, wrong issuers, wrong audiences, expired tokens, or disallowed algorithms?

These are two different types of evidence:

| Layer | Tool | What it verifies | What it does NOT verify |
| --- | --- | --- | --- |
| HTTP/authorization | MockMvc + `jwt()`, `opaqueToken()` | Authorization by route, method, authority; status codes 401/403/200/201. | JWT signatures and whether JwtDecoder actually rejects forged tokens. |
| Claims mapping | `JwtAuthenticationConverter` unit test | Scope/custom claims converted into authorities according to rules. | Whether the token was signed by a trusted issuer. |
| JWT decoder | Test-key-signed JWT + NimbusJwtDecoder | Signature, issuer, audience, expiration, custom validators. | HTTP filter, key loading via JWK Set, endpoint policies if testing decoder alone. |
| Opaque introspection | Stub `OpaqueTokenIntrospector` or local introspection endpoint | Active status, attribute mapping, network/timeout errors. | Real Authorization Server behavior outside fixtures. |
| HTTP integration | MockMvc or HTTP server + real signed JWT + JWK Set fixture | Bearer filter pipeline, decoder, validators, authorization, and HTTP response. | Production issuer operations if not tested separately. |

Minimum test matrix for the sample API:

| Request | Token / permission | Expected outcome |
| --- | --- | --- |
| GET /api/orders | No token | **401 Unauthorized** |
| GET /api/orders | Invalid Bearer token | **401 Unauthorized** |
| GET /api/orders | Valid token, only **orders.write** | **403 Forbidden** |
| GET /api/orders | Valid token, has **orders.read** | **200 OK** |
| POST /api/orders | Valid token, only **orders.read** | **403 Forbidden** |
| POST /api/orders | Valid token, has **orders.write** | **201 Created** |
| GET /api/orders | Valid signature JWT, wrong audience | **401 Unauthorized** |
| GET /api/orders | Expired JWT or invalid signature | **401 Unauthorized** |

Typically **401** means the request is unauthenticated; **403** means the request is authenticated but lacks sufficient permissions. Responses should include appropriate challenges such as `WWW-Authenticate: Bearer` where applicable, without leaking tokens or internal details.

## 8. HTTP Testing with MockMvc and spring-security-test

`SecurityMockMvcRequestPostProcessors.jwt()` creates a JWT-style Authentication for test requests, convenient for testing **SCOPE_orders.read** or **SCOPE_orders.write** without calling an IdP.

Example:

~~~java
mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

**Important boundary:** `jwt()` does not pass a real signed JWT through `JwtDecoder`. It simulates an already-authenticated principal, so it **cannot** prove the decoder checks signatures, issuers, or audiences properly. When forcing authorities via `jwt().authorities(...)`, the test also **does not prove** that the application's converter maps claims properly.

### 8.1. Sample Authorization Test Class

With the configuration and controller from section 5, you can create `OrdersSecurityTest.java`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Import(OrdersSecurityTest.TestDecoderConfig.class)
class OrdersSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @TestConfiguration
    static class TestDecoderConfig {
        @Bean
        JwtDecoder jwtDecoder() {
            // For authorization tests only, do not use in production.
            return value -> {
                throw new BadJwtException("Synthetic test decoder");
            };
        }
    }

    @Test
    void missingTokenGets401() throws Exception {
        mockMvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void rejectedTokenGets401() throws Exception {
        mockMvc.perform(get("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer invalid-token"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readScopeCanRead() throws Exception {
        mockMvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.orders").isArray());
    }

    @Test
    void writeScopeAloneCannotRead() throws Exception {
        mockMvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void readScopeAloneCannotCreate() throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void writeScopeCanCreate() throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.write"))))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.status").value("created"));
    }
}
~~~

**TestDecoderConfig** gives the context a JwtDecoder for testing without needing a real Authorization Server. The synthetic decoder always rejects real Bearer strings sent via headers; `with(jwt())` requests already have a pre-built Authentication and bypass token verification. If the application already defines another `JwtDecoder` bean, adjust the test configuration to avoid duplicate beans; this sample assumes the production decoder is auto-configured by Boot.

Do not move this synthetic decoder into production code. The test suite above mainly proves **HTTP authorization rules**, while signature/claims verification requires dedicated decoder tests.

### 8.2. Why @WithMockUser Is Not Enough

`@WithMockUser` creates a mock user in Spring Security Test. It is useful for testing general user/role-based method security, but **does not faithfully represent a Jwt principal, Bearer token, claims, or JwtDecoder**.

For controllers receiving `@AuthenticationPrincipal Jwt`, using `jwt()` aligns much closer to the Resource Server structure. If using a custom `JwtAuthenticationConverter` for roles/permissions, you must write a **separate test for the converter** instead of manually injecting authorities and assuming the mapping works.

## 9. Testing JwtDecoder with Real Signed JWTs

To test **RS256 signatures, issuer, audience, and expiration** independently of the network, generate an RSA key pair for testing only. The test signs JWTs with the **private key**, lets NimbusJwtDecoder verify them with the corresponding **public key**, and varies claims or keys to verify rejection behavior.

JUnit 5 example using Nimbus JOSE/JWT classes already present in the JOSE dependency branch:

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

class JwtDecoderValidationTest {

    private static final String ISSUER =
        "https://identity.example.test/realms/demo";

    private KeyPair trustedKeys;
    private NimbusJwtDecoder decoder;

    @BeforeEach
    void setUp() throws Exception {
        trustedKeys = newRsaKeys();
        decoder = NimbusJwtDecoder
            .withPublicKey((RSAPublicKey) trustedKeys.getPublic())
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token", "Invalid audience", null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audienceValidator));
    }

    private static KeyPair newRsaKeys() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    private static String signedToken(
            KeyPair signingKeys,
            String issuer,
            String audience,
            Instant expiration) throws Exception {

        JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer(issuer)
            .subject("employee-123")
            .audience(audience)
            .issueTime(Date.from(Instant.now().minusSeconds(60)))
            .notBeforeTime(Date.from(Instant.now().minusSeconds(60)))
            .expirationTime(Date.from(expiration))
            .claim("scope", "orders.read")
            .build();

        SignedJWT token = new SignedJWT(
            new JWSHeader(JWSAlgorithm.RS256), claims);
        token.sign(new RSASSASigner(
            (RSAPrivateKey) signingKeys.getPrivate()));
        return token.serialize();
    }

    @Test
    void validJwtPasses() throws Exception {
        String token = signedToken(
            trustedKeys, ISSUER, "orders-api",
            Instant.now().plusSeconds(600));

        Jwt jwt = decoder.decode(token);
        assertEquals("employee-123", jwt.getSubject());
    }

    @Test
    void wrongAudienceIsRejected() throws Exception {
        String token = signedToken(
            trustedKeys, ISSUER, "other-api",
            Instant.now().plusSeconds(600));

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void wrongIssuerIsRejected() throws Exception {
        String token = signedToken(
            trustedKeys, "https://untrusted.example.test", "orders-api",
            Instant.now().plusSeconds(600));

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void expiredJwtIsRejected() throws Exception {
        String token = signedToken(
            trustedKeys, ISSUER, "orders-api",
            Instant.now().minusSeconds(3600));

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void unknownSigningKeyIsRejected() throws Exception {
        KeyPair otherKeys = newRsaKeys();
        String token = signedToken(
            otherKeys, ISSUER, "orders-api",
            Instant.now().plusSeconds(600));

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }
}
~~~

This test verifies the **signature path and JwtDecoder with a test public key**, while also checking issuer, audience, and exp. The expiration in the expired test is set one hour in the past to avoid skew tolerances. Never use production private keys or Access Tokens as fixtures.

**Limitation:** Because the decoder is constructed directly with a public key, the test does not cover metadata discovery, HTTP JWK Set fetching, caching, key rotation, or the Bearer filter. Those require integration tests.

### 9.1. Experiment Demonstrating the Limit of jwt() in MockMvc

~~~java
mockMvc.perform(get("/api/orders")
        .with(jwt()
            .jwt(token -> token.audience("other-api"))
            .authorities(new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

The request can still return **200** because the `jwt()` helper puts an already-valid Authentication in the SecurityContext. No real JWS string is verified by JwtDecoder. To prove a wrong-audience token is rejected, **invoke the real JwtDecoder** as in section 9 or send a signed JWT via the header in an HTTP test using a real decoder.

## 10. Integration Testing with a Local JWK Set

To test the entire HTTP flow with a real JWT, you can spin up a **local test JWK Set endpoint** hosting the test public key, sign the JWT with the test private key, and configure the Resource Server to point to the fixture's issuer/JWK URI.

~~~text
JUnit/Test fixture
  |-- Test RSA private key: sign JWT
  |-- JWK Set HTTP test endpoint: publish RSA public key
  |
  v
MockMvc or HTTP test
  Authorization: Bearer <real signed JWT>
  |
  v
BearerTokenAuthenticationFilter
  |
  v
NimbusJwtDecoder -> JWK Set -> signature/iss/aud/exp
  |
  v
Scope/authorization -> Controller or 401/403
~~~

Scenarios worth testing:

1. Missing header or malformed Bearer header.
2. Invalid signature, unknown key, or `kid` missing from the JWK Set.
3. Expired `exp`, future `nbf`, or wrong issuer or audience.
4. Disallowed algorithm/header outside the allowed profile; never accept unsigned JWTs.
5. Valid signature token lacking scope/role or lacking permission on the resource.
6. JWK endpoint error or unavailability: the application must never grant access when a token cannot be verified.
7. JWK Set key rotation if the system must support rotation.
8. An ID Token with an OIDC Client audience mistakenly sent to the API: the Resource Server must reject it based on audience/profile.

These integration tests complement standalone decoder tests while avoiding dependence on a production Authorization Server, real tokens, and external networks.

## 11. Testing Opaque Tokens with spring-security-test

For a Resource Server configured with opaque tokens, use `opaqueToken()` to simulate Authentication when testing authorization:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.opaqueToken;

mockMvc.perform(get("/api/orders")
        .with(opaqueToken().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

Like `jwt()`, this helper **does not prove** a real token went through the introspection endpoint. To test opaque token verification, test `OpaqueTokenIntrospector` with mocked responses or a local introspection HTTP test server, covering:

- Token with **active=true** and matching permissions.
- Token with **active=false**, nonexistent, or revoked.
- Wrong introspection client credentials.
- Timeouts/network errors and proper rejection behavior.
- Whether returned claims/scopes match the API contract.

Do not test RS256 signatures on an opaque token that the Resource Server does not decode with a JWT decoder.

## 12. Testing Resource-Level Permissions and Method Security

Passing JWT authentication **does not prove** the caller is allowed to read a specific record. For instance, a token with `orders.read` for tenant A must be blocked when calling tenant B's API.

If the API uses `@PreAuthorize`, enable method security configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Business rules should compare `tenant_id` from the JWT with the order's tenant and resource ownership, rather than just reading claims for display. When using a custom converter for `roles`/`permissions`, write dedicated tests proving claim names, JSON types, and authority mapping rules are correct. A `jwt().authorities(...)` test does not cover that custom converter.

Useful cases: cross-tenant access, accessing another user's order, POST calls with only GET scope, tampering with identifiers in the URL, and resources whose permissions were revoked.

## 13. Common Implementation Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Adding only the OAuth 2.0 Client starter | API lacks Bearer token authentication. | Add the Resource Server starter and proper configuration. |
| Manually adding Resource Server module without JOSE | Missing classes to process JWT/JWS. | Add `spring-security-oauth2-jose` with compatible dependency management. |
| Verifying only signature, skipping audience | Tokens for other APIs may be accepted by mistake. | Validate `aud` via properties or custom validator, and write real tests. |
| Declaring a custom JwtDecoder that drops default validators | May skip issuer/expiration checks if misconfigured. | Combine default and custom validators, and write negative tests. |
| Testing only with `jwt()` and claiming "JWT signatures are secure" | Tests never pass through the decoder. | Add real signed JWT tests against the decoder or HTTP integration tests. |
| Testing only success cases | Misses 401/403, expired tokens, wrong-audience tokens. | Include both positive and negative tests at every required layer. |
| Using `@WithMockUser` for all JWT tests | Does not verify Bearer JWT principal/claims. | Use `jwt()`, plus dedicated converter and decoder tests. |
| Disabling CSRF globally when still using session cookies | Web endpoints may lose necessary CSRF protection. | Apply CSRF policy per authentication flow. |
| Tests depending on a live IdP | Slow, flaky, may involve real secrets. | Use local RSA/JWK/introspection fixtures. |
| Logging tokens or putting them in URLs or errors | Bearer credentials leaked. | Use Authorization headers over TLS, sanitize logs, and avoid echoing tokens. |

### 13.1. Distinguishing 401 and 403 Errors

For a typical Resource Server:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Typically returned when there is no Bearer token or the token cannot be authenticated.

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Typically returned when the token is authenticated but lacks sufficient permissions. Header details may vary by configuration and scenario; when customizing `AuthenticationEntryPoint` or `AccessDeniedHandler`, keep proper HTTP status codes and challenges without returning tokens, raw exceptions, or stack traces to clients.

### 13.2. Do Not Identify a JWT Just by Three Dot-Separated Segments

A string with dots does not prove it is a trustworthy JWT. The Resource Server must use an official decoder and validator, restrict allowed algorithms/keys, and trust only configured issuers/audiences. Writing your own Base64url decoder to read claims **is not authentication**.

## 14. Implementation Workflow from Bootstrap to Testing

1. **Align on the contract with the Authorization Server:** JWT or opaque, issuer, JWK Set/introspection URI, audience, scope, algorithms, lifetimes, and token profile.
2. **Choose the right dependencies:** Resource Server starter; JOSE for JWT; Spring Security Test for testing. Do not mix versions arbitrarily.
3. **Configure token validation:** issuer, signature, lifetime, audience, and profile requirements; never grant access when verification fails.
4. **Configure HTTP authorization:** methods, routes, scopes, and data-level permissions; identify where sessions/CSRF apply.
5. **Write MockMvc tests:** anonymous 401, invalid token 401, missing scope 403, valid scope 200/201; test read and write permissions separately.
6. **Write JwtDecoder tests:** real tokens signed with test keys; test valid/invalid issuer, audience, expiration, and signing key.
7. **Write integration tests when needed:** local JWK Set or introspection endpoint, testing the Bearer filter and full HTTP behavior.
8. **Harden operations:** HTTPS, no token logging, no leaking keys/sensitive claims in error responses, prepare for key rotation and IdP outages.

**Key takeaway:** `spring-boot-starter-oauth2-resource-server` enables Bearer token processing; **JOSE** verifies signed JWTs; **security tests** must prove both that endpoints enforce permissions accurately and that the decoder rejects untrusted tokens. Tests using `jwt()` are great for authorization, but must be paired with signature and claims verification to conclude a JWT Resource Server is secure.

## References

- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html).
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html).
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html).
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515).
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517).
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519).
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
