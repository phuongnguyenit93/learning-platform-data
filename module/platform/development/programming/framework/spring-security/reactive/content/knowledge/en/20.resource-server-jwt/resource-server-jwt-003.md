# Configuring issuer-uri, jwk-set-uri, and Relationship with the Identity Provider — Spring Security WebFlux

## Learning Objectives

This lesson belongs to **Resource Server JWT** in the **Spring Security – reactive** module. Upon completion, you can:

1. Distinguish **Identity Provider / OAuth2 Authorization Server**, **OAuth2 Client**, and **Resource Server**; understand that a Resource Server validates tokens rather than issuing them.
2. Explain the exact meanings of `issuer-uri`, `jwk-set-uri`, OpenID Connect Discovery, OAuth 2.0 Authorization Server Metadata, and `jwks_uri`.
3. Choose among three configurations: `issuer-uri` only, `jwk-set-uri` only, and **both**; know what is discovered and what is automatically validated.
4. Verify JWTs by **signature, issuer, audience, timestamps, and scope**; avoid confusing a JWT access token with an ID token.
5. Configure Java 17+ / Spring Boot 3.5.x / Spring Security 6.5.x using WebFlux `SecurityWebFilterChain`, `ServerHttpSecurity`, `ReactiveJwtDecoder`, and scope authorization.
6. Run integration tests generating RSA-signed JWTs and serving public JWKS from a local MockWebServer; test 200, 401, 403, wrong issuer, wrong audience, invalid signature, and expired tokens.
7. Handle key rotation, metadata discovery, IdP downtime, clock skew, TLS, multiple issuers, wrong `kid`, multi-tenant permissions, and the risk of custom decoders missing an issuer validator.

> Illustrative versions: Java 17+, Spring Boot **3.5.16**, Spring Security **6.5** (at least patch **6.5.10** should be used on this branch). Spring Boot 3.5 has reached end of OSS support; when designing new systems, prefer a still-supported branch. This lesson uses **reactive** APIs; Servlet code like `HttpSecurity` or `JwtDecoder` is not the WebFlux equivalent.

---

## 1. JWT Resource Server and Identity Provider Architecture

```text
User / background service
           |
           v
   OAuth2 Client requests token
           |
           v
+-------------------------------------+
| Identity Provider / Authorization   |
| Server                              |
| - Authenticates user, grant/consent |
| - Issues JWT access token           |
| - Signs with private signing key    |
| - Publishes public keys via JWKS    |
+-------------------------------------+
           |                    ^
           | access token       | GET issuer metadata / JWKS
           v                    |
   OAuth2 Client                |
           |                    |
           | Authorization: Bearer <JWT>
           v                    |
+-------------------------------------+
| Spring Security WebFlux             |
| OAuth2 Resource Server              |
| - verify signature via trusted JWK  |
| - validate iss / aud / nbf / exp    |
| - map scopes to SCOPE_*             |
| - authorize URL/service/resource    |
+-------------------------------------+
           |
           v
        HTTP 200 / 401 / 403
```

An **Identity Provider (IdP)** typically provides sign-in/OIDC flows; an **Authorization Server** issues OAuth2 access tokens. One product can be both an IdP and an Authorization Server, though not necessarily. An **OAuth2 Client** obtains and uses tokens. A **Resource Server** receives Bearer tokens and decides whether to accept them; it does not issue tokens when enabling `oauth2ResourceServer().jwt()`.

Do not conflate concepts:

| Concept | Illustrative example | Responsibility |
| --- | --- | --- |
| Issuer identifier | `https://idp.example.test/realms/acme` | Value that must match the `iss` claim |
| Discovery metadata | JSON document at `.well-known` URL | Publishes issuer, `jwks_uri`, and provider endpoints |
| JWK Set URL | `https://idp.example.test/realms/acme/certs` | Returns public signing keys |
| Token endpoint | `https://idp.example.test/realms/acme/token` | Client exchanges grant for tokens, **not** the JWKS address |
| Audience | `api://inventory` | Which API is permitted to receive the access token |
| Resource Server | `inventory-api` | Verifies signature, claims, scopes, and data permissions |

Each URL is an example, not an endpoint of any real IdP.

## 2. What Does a JWT Access Token Contain?

A compact JWT typically has the structure:

```text
base64url(header).base64url(payload).base64url(signature)
```

Header example **for illustration only**:

```json
{"typ":"JWT","alg":"RS256","kid":"signing-key-1"}
```

Payload example:

```json
{
  "iss": "https://idp.example.test/realms/acme",
  "sub": "user-123",
  "aud": ["api://inventory"],
  "scope": "inventory.read inventory.write",
  "iat": 1794000000,
  "nbf": 1794000000,
  "exp": 1794003600
}
```

The timestamps above are sample numbers only and do not imply the token is currently valid. Base64URL payload is **not encrypted**; decoding merely inspects the data without authenticating its contents. Only after the signature is verified with a trusted public key and validators pass does Spring create an Authentication.

| JWT field | Role | Safety rule |
| --- | --- | --- |
| `iss` | Who issued the token | Exact match against trusted issuer |
| `aud` | Which resource it is for | Must contain this API's own audience |
| `sub` | Subject | Use as identity after verification; consider namespace/tenant |
| `exp` | Expiration | Reject once expired |
| `nbf` | Not before | Reject if presented too early |
| `iat` | Issued at | Does not replace `exp`/`nbf` checks |
| `scope` / `scp` | OAuth2 permissions | Mapped to e.g. `SCOPE_inventory.read` |
| `kid` | Key hint for verification | Select only from trusted JWKS, never trust blindly |
| `alg` | Signing algorithm | Must be in allowlist; never accept `none` |
| `typ` | Token profile/type | Important for distinguishing access token vs ID token |

**A token with a valid signature might still not be intended for your API.** The same IdP can issue tokens for many applications with different audiences. Hence checking `aud` is critical rather than relying solely on `iss` and signature.

## 3. issuer-uri: Exact Issuer Identifier

In `application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/acme
```

This value must match the exact `iss` claim the IdP actually issues, including **scheme, hostname, path, and trailing slash**. Do not use the token endpoint URL as the issuer if the token's issuer is a different URL. For example:

```text
expected iss: https://idp.example.test/realms/acme
actual iss:   https://idp.example.test/realms/other
=> REJECT, even if the signature verifies
```

Spring Security 6.5 can use the issuer to look up OpenID Provider Configuration or OAuth2 Authorization Server Metadata at supported `.well-known` endpoints, then extract the `jwks_uri` property. Metadata might look like:

```json
{
  "issuer": "https://idp.example.test/realms/acme",
  "authorization_endpoint": "https://idp.example.test/realms/acme/authorize",
  "token_endpoint": "https://idp.example.test/realms/acme/token",
  "jwks_uri": "https://idp.example.test/realms/acme/certs"
}
```

This is only abbreviated JSON, not complete provider metadata. **Do not guess the JWKS URL by appending a fixed path to the issuer**; the JWKS path is not standardized as a mandatory suffix. Use official discovery or IdP documentation.

### Discovery at Startup or on First Request?

In default Spring Boot 3.5 / Spring Security 6.5 reactive configurations, discovery from the issuer may be **deferred until the first JWT request** via `SupplierReactiveJwtDecoder`. This allows the application to start **without requiring** IdP connectivity. However, a custom decoder may discover metadata immediately upon construction, so do not generalize that every issuer configuration is lazy.

Distinguish:

- **App started**: WebFlux server is listening and basic configuration beans are ready.
- **Can verify a JWT**: required metadata/JWKS has been fetched or reliably cached.
- IdP/JWKS unreachable when a key is needed: Bearer requests cannot be authorized, even if the app healthcheck reports UP.
- A custom `ReactiveJwtDecoder` can change when metadata calls occur.

## 4. jwk-set-uri: Address of Public Signing Keys

When configured directly:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri: https://idp.example.test/realms/acme/certs
```

A JWK Set (RFC 7517) is typically JSON containing a `keys` array, shaped like:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "signing-key-1",
      "use": "sig",
      "alg": "RS256",
      "n": "BASE64URL_PUBLIC_MODULUS",
      "e": "AQAB"
    }
  ]
}
```

The `n` field above is a placeholder string to illustrate structure, **not a valid RSA key**. A JWKS should only publish **public keys**; never include RSA private exponent `d`, private PEM keys, or client secrets in the response.

### Rotation

When the IdP rotates keys:

1. Publish the **new public key** to JWKS (with a new `kid`).
2. Start signing new JWTs with the corresponding private key.
3. Keep the old public key long enough for unexpired old tokens to be verified.
4. Account for cache/re-fetch behavior at the Resource Server and the access token TTL.
5. Once old tokens have expired, remove the old public key per policy.

Do not assume every JWT request hits JWKS. Spring Security/Nimbus performs caching. When a new `kid` is not yet in cache, the decoder may need to refresh JWKS; when the endpoint is down or the cache lacks a matching key, **never skip signature checks**.

`kid` is input supplied by the JWT sender; it only helps select a key **from the configured trusted JWKS**. Never take `jku` or `x5u` from a JWT header as a URL to fetch keys from arbitrary hosts, as that enables SSRF and key trust injection.

## 5. Three Proper Configuration Modes and Differences

### Mode A — issuer-uri Only

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/acme
          audiences:
            - api://inventory
```

- Suitable for IdPs supporting standard metadata discovery.
- Spring determines the expected issuer and discovers the JWKS URI from metadata.
- Metadata lookup can be lazy in Boot/Security 6.5 defaults.
- The API still needs JWKS public keys when verifying signatures.
- `audiences` adds the `aud` check; do not omit it.

### Mode B — jwk-set-uri Only

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri: https://idp.example.test/realms/acme/certs
          audiences:
            - api://inventory
```

- No metadata discovery needed to locate JWKS.
- Used when the provider lacks discovery or the JWKS URL is explicitly managed.
- **Does not automatically provide an expected issuer** when only JWKS is declared, so an issuer validator must be added via trusted configuration/policy.
- A valid signature against a key is not enough to prove issuer and audience. In production, configure both properties whenever the issuer is known.

### Mode C — issuer-uri + jwk-set-uri (Recommended When Pinning JWKS)

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/acme
          jwk-set-uri: https://idp.example.test/realms/acme/certs
          audiences:
            - api://inventory
```

- The JWKS URL is supplied directly, avoiding a metadata call just to discover the public key address.
- Expected issuer remains `issuer-uri`; Spring Boot defaults validate `iss`.
- Audience property validates that `aud` targets this API.
- Startup does not depend on metadata discovery, **but** JWKS contact is still required when the cache lacks the matching key.
- If the provider changes its JWKS URL, you must update the pinned configuration.

| Comparison point | Issuer only | JWKS only | Both |
| --- | --- | --- | --- |
| Metadata discovery for JWKS URL | Yes | No | Not needed |
| Expected `iss` from property | Yes | No | Yes |
| Signature verification | Yes | Yes | Yes |
| `aud` automatically enforced without `audiences`? | No | No | No |
| Always needs IdP at startup? | Not necessarily in 6.5 defaults | Not for discovery | Not for discovery |
| May require network key fetch at runtime | Yes | Yes | Yes |
| Safe on JWKS failure | Denies access if unverifiable | Same | Same |

**Practical choice:** if IdP discovery is reliable, issuer+audience alone is usually sufficient. If you want startup independent of metadata or the IdP lacks discovery, use issuer+JWK URL+audience. Never trade issuer checks for availability.

## 6. JWT Authentication Steps in WebFlux

```text
GET /api/inventory
Authorization: Bearer <token>
          |
          v
Bearer token authentication filter
          |
          +-- parse JWT/JWS
          +-- select public JWK by trusted jwk-set-uri and kid
          +-- verify signature using allowed JWS algorithm
          +-- check exp, nbf, iss and aud
          |
          v
Jwt Authentication (principal = Jwt, name ~= sub)
          |
          +-- scope inventory.read => SCOPE_inventory.read
          |
          v
AuthorizationWebFilter
          |
          +-- hasAuthority("SCOPE_inventory.read") ?
               +-- yes -> Controller/Service
               +-- no  -> 403
```

A JWT Resource Server is not where user passwords are managed or OAuth2 tokens are self-issued. It verifies tokens issued by the Authority Server, maps authorities, and enforces authorization. If controllers manage row-level permissions/tenants, business data must still be checked; a scope check alone does not grant a user access to every record.

For missing or invalid Bearer tokens, Bearer APIs typically return **401**; for an authenticated JWT lacking the required scope, typically **403**. On a JWKS network failure, the exact status may depend on error handling, but data must never be returned without verifying the token.

## 7. Runnable Java 17+ Project and Offline Tests

This project uses **Spring Boot 3.5.16**, Spring Security 6.5, WebFlux. Production-style configuration demonstrates issuer/JWKS; the integration test runs a loopback mock JWKS and signs tokens with **real RSA signatures** to exercise validation. No production secrets or IdP are included.

### 7.1. Structure

```text
jwt-resource-lab/
  settings.gradle
  build.gradle
  src/main/java/example/jwtlab/
    JwtResourceApplication.java
    SecurityConfiguration.java
    InventoryController.java
  src/main/resources/
    application.yml
  src/test/java/example/jwtlab/
    JwtResourceIntegrationTest.java
```

### 7.2. Full Gradle Setup

**`settings.gradle`:**

```groovy
rootProject.name = 'jwt-resource-lab'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The OAuth2 Resource Server starter pulls in the required JOSE/JWT libraries, including Nimbus used by Spring Security to verify signatures. Test code uses Nimbus from this dependency graph.

Do not add `spring-boot-starter-web` alongside it if you want pure WebFlux. Boot 3.5.16 is a baseline for reproducible examples, not a recommendation to deploy an OSS-EOL branch for new products.

### 7.3. application.yml

**`src/main/resources/application.yml`:**

```yaml
server:
  port: 8080

spring:
  application:
    name: jwt-resource-lab
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.invalid/realms/lab
          jwk-set-uri: https://idp.example.invalid/realms/lab/certs
          audiences:
            - api://inventory
```

These `.invalid` URLs are **not a real IdP**; outside tests, replace them with your provider's official issuer and JWKS URLs. In tests, `@DynamicPropertySource` overrides them with a local JWKS fixture, so `./gradlew test` requires no Internet IdP connection.

### 7.4. Main Class

**`src/main/java/example/jwtlab/JwtResourceApplication.java`:**

```java
package example.jwtlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JwtResourceApplication {

    public static void main(String[] args) {
        SpringApplication.run(JwtResourceApplication.class, args);
    }
}
```

### 7.5. WebFlux Security Configuration

**`src/main/java/example/jwtlab/SecurityConfiguration.java`:**

```java
package example.jwtlab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/inventory")
                            .hasAuthority("SCOPE_inventory.read")
                        .anyExchange().denyAll()
                )
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Here `ServerHttpSecurity` creates a reactive `SecurityWebFilterChain`. Because the project declares no custom `ReactiveJwtDecoder` bean, Spring Boot uses the issuer/JWK/audience properties to configure the decoder. `hasAuthority("SCOPE_inventory.read")` requires the scope from the JWT rather than permitting any Bearer token.

Do not enable `httpBasic`, `formLogin`, or OAuth2 Client when acting solely as a **Resource Server**. Default WebFlux CSRF remains enabled, though the demo API only exposes GET; evaluate CSRF separately if adding unsafe methods where browsers auto-send cookies/Basic/mTLS.

### 7.6. Controller

**`src/main/java/example/jwtlab/InventoryController.java`:**

```java
package example.jwtlab;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class InventoryController {

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/inventory")
    public Mono<String> inventory(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just("inventory-for-" + jwt.getSubject());
    }
}
```

After JWT authentication, Spring Security sets `Jwt` as the principal. When the token has `sub=alice` and the required scope, the expected response is `inventory-for-alice`. This is demo data; real APIs must also bind user/tenant and check per-resource access permissions.

## 8. Real JWT/JWKS Integration Test Using MockWebServer

The test creates a private RSA key in **test memory**, exposes the public JWK via a local MockWebServer, then signs RS256 JWTs and sends HTTP requests to real Netty via `WebTestClient`. Even without a real IdP, **JWT signature/issuer/audience/timestamps are all checked by the real ReactiveJwtDecoder**.

**`src/test/java/example/jwtlab/JwtResourceIntegrationTest.java`:**

```java
package example.jwtlab;

import java.io.IOException;
import java.time.Instant;
import java.util.Date;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class JwtResourceIntegrationTest {

    private static final String ISSUER =
            "https://issuer.example.invalid/realms/test";
    private static final String AUDIENCE = "api://inventory";
    private static final RSAKey SIGNING_KEY =
            generateKey("training-key-1");
    private static final MockWebServer JWKS =
            startJwksServer();

    @DynamicPropertySource
    static void overrideIdpProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.security.oauth2.resourceserver.jwt.issuer-uri",
                () -> ISSUER);
        registry.add(
                "spring.security.oauth2.resourceserver.jwt.jwk-set-uri",
                () -> JWKS.url("/jwks").toString());
        registry.add(
                "spring.security.oauth2.resourceserver.jwt.audiences",
                () -> AUDIENCE);
    }

    @LocalServerPort int port;
    private WebTestClient client;

    @BeforeEach
    void makeClient() {
        client = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();
    }

    @AfterAll
    static void closeJwks() throws IOException {
        JWKS.shutdown();
    }

    private static RSAKey generateKey(String kid) {
        try {
            return new RSAKeyGenerator(2048)
                    .keyID(kid).generate();
        } catch (JOSEException ex) {
            throw new IllegalStateException(ex);
        }
    }

    private static MockWebServer startJwksServer() {
        MockWebServer server = new MockWebServer();
        server.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                if ("/jwks".equals(request.getPath())) {
                    // JWKS contains only the public key, excluding the private exponent.
                    String json = new JWKSet(SIGNING_KEY.toPublicJWK())
                            .toString();
                    return new MockResponse()
                            .setResponseCode(200)
                            .setHeader("Content-Type", "application/json")
                            .setBody(json);
                }
                return new MockResponse().setResponseCode(404);
            }
        });
        try {
            server.start();
        } catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
        return server;
    }

    private static String signedJwt(
            RSAKey signer, String issuer, String audience,
            String scope, Instant notBefore, Instant expiresAt) {
        try {
            JWTClaimsSet claims = new JWTClaimsSet.Builder()
                    .issuer(issuer)
                    .subject("alice")
                    .audience(audience)
                    .issueTime(Date.from(notBefore.minusSeconds(10)))
                    .notBeforeTime(Date.from(notBefore))
                    .expirationTime(Date.from(expiresAt))
                    .claim("scope", scope)
                    .build();

            SignedJWT jwt = new SignedJWT(
                    new JWSHeader.Builder(JWSAlgorithm.RS256)
                            .type(JOSEObjectType.JWT)
                            .keyID(signer.getKeyID())
                            .build(),
                    claims);
            jwt.sign(new RSASSASigner(signer));
            return jwt.serialize();
        } catch (JOSEException ex) {
            throw new IllegalStateException(ex);
        }
    }

    private static String token(
            String issuer, String audience, String scope) {
        Instant now = Instant.now();
        return signedJwt(
                SIGNING_KEY, issuer, audience, scope,
                now.minusSeconds(30),
                now.plusSeconds(600));
    }

    @Test
    void publicEndpointDoesNotNeedJwt() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void missingJwtReturns401() {
        client.get().uri("/api/inventory")
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void malformedJwtReturns401() {
        client.get().uri("/api/inventory")
                .headers(h -> h.setBearerAuth("not-a-jwt"))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void validSignatureIssuerAudienceScopeReturns200() {
        client.get().uri("/api/inventory")
                .headers(h -> h.setBearerAuth(
                        token(ISSUER, AUDIENCE, "inventory.read")))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("inventory-for-alice");
    }

    @Test
    void wrongIssuerIsUnauthorized() {
        client.get().uri("/api/inventory")
                .headers(h -> h.setBearerAuth(token(
                        "https://other.example.invalid",
                        AUDIENCE, "inventory.read")))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void wrongAudienceIsUnauthorized() {
        client.get().uri("/api/inventory")
                .headers(h -> h.setBearerAuth(
                        token(ISSUER, "api://billing", "inventory.read")))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void missingScopeIsForbidden() {
        client.get().uri("/api/inventory")
                .headers(h -> h.setBearerAuth(
                        token(ISSUER, AUDIENCE, "inventory.write")))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void wrongSignatureIsUnauthorized() {
        // Same kid, but different private signing key!
        RSAKey outsider = generateKey("training-key-1");
        Instant now = Instant.now();
        String jwt = signedJwt(
                outsider, ISSUER, AUDIENCE, "inventory.read",
                now.minusSeconds(30), now.plusSeconds(600));
        client.get().uri("/api/inventory")
                .headers(h -> h.setBearerAuth(jwt))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void expiredJwtIsUnauthorized() {
        Instant now = Instant.now();
        String jwt = signedJwt(
                SIGNING_KEY, ISSUER, AUDIENCE, "inventory.read",
                now.minusSeconds(3600), now.minusSeconds(600));
        client.get().uri("/api/inventory")
                .headers(h -> h.setBearerAuth(jwt))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void futureNbfIsUnauthorized() {
        Instant now = Instant.now();
        String jwt = signedJwt(
                SIGNING_KEY, ISSUER, AUDIENCE, "inventory.read",
                now.plusSeconds(600), now.plusSeconds(1800));
        client.get().uri("/api/inventory")
                .headers(h -> h.setBearerAuth(jwt))
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void unknownKidIsUnauthorized() {
        RSAKey outsider = generateKey("not-published-key");
        Instant now = Instant.now();
        String jwt = signedJwt(
                outsider, ISSUER, AUDIENCE, "inventory.read",
                now.minusSeconds(30), now.plusSeconds(600));
        client.get().uri("/api/inventory")
                .headers(h -> h.setBearerAuth(jwt))
                .exchange().expectStatus().isUnauthorized();
    }
}
```

### 8.1. How This Test Genuinely Verifies Issuer/JWKS

- `@DynamicPropertySource` overrides config right before Boot initializes the context.
- Expected issuer is `https://issuer.example.invalid/realms/test`; because **both issuer and JWK URI** are provided, Spring does not need to fetch metadata from that dummy domain.
- The JWK URI is `http://127.0.0.1:<port>/jwks`, loopback-only in tests; MockWebServer returns the public RSA key of `SIGNING_KEY`.
- The test signs JWTs with that private RSA key, and Spring Security fetches the public JWKS and verifies them.
- Wrong issuer, wrong audience, wrong signature, expired, or future `nbf` must return 401; missing only scope is authenticated but returns 403.
- For a real IdP, **HTTPS is mandatory** with hostname/certificate verification; never copy a mock HTTP JWK URL into production.
- The test does not call an OAuth2 token endpoint, nor test OIDC login or token rotation; those are separate workflows.

### 8.2. Running the Test

The project includes Gradle Wrapper:

```bash
./gradlew test --tests example.jwtlab.JwtResourceIntegrationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.jwtlab.JwtResourceIntegrationTest
```

Or use a pre-installed compatible Gradle:

```bash
gradle test --tests example.jwtlab.JwtResourceIntegrationTest
```

**Expected:** 11 tests PASS. This is an expectation from reading the code and checked APIs, **not a log of an actual compile/test run**. In CI environments, loopback port binding and Maven Central dependency downloads must be allowed. The test can be extended to cover JWKS rotation/retry/timeout behavior.

## 9. Custom ReactiveJwtDecoder and Validators: An Error-Prone Area

**Recommendation:** when you only need issuer, JWK URL, and audience, use Boot properties as in the demo. Create a custom decoder only when you need specific algorithms, caching, HTTP clients, timeouts, or custom claim validators.

Fragment **replaces** Boot auto-config, not code to add to the main project:

```java
// Place inside @Configuration along with the imports in the next snippet.
@Bean
ReactiveJwtDecoder jwtDecoder() {
    String issuer = "https://idp.example.test/realms/acme";
    String jwks = "https://idp.example.test/realms/acme/certs";
    String audience = "api://inventory";

    NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withJwkSetUri(jwks).build();

    OAuth2TokenValidator<Jwt> withIssuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> withAudience =
            new JwtClaimValidator<java.util.List<String>>(
                    "aud", aud -> aud != null && aud.contains(audience));

    decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            withIssuerAndTime, withAudience));
    return decoder;
}
```

Required imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
```

**Mandatory security point:** when using `NimbusReactiveJwtDecoder.withJwkSetUri(...).build()`, do not think knowing the JWKS URL alone validates the issuer. `JwtValidators.createDefaultWithIssuer(issuer)` preserves issuer and timestamp checks; the audience validator checks `aud`. If you call `setJwtValidator` with only an audience validator and forget the default validators, you can lose issuer/time validation.

### CVE-2026-22748 Warning

Spring Security announced on 2026-04-20 that versions **6.5.0–6.5.9** could lead developers to mistakenly assume `NimbusReactiveJwtDecoder.withIssuerLocation(...)` automatically adds issuer validation. The published patch is **6.5.10**. Even on patched versions, write tests with **a validly signed JWT having the wrong iss** and explicit validators in custom decoders.

Never configure a default policy that accepts `alg=none`, never use a JWKS URL specified by a JWT's `jku` header, never accept keys from arbitrary issuers, and never disable TLS verification in production.

## 10. ID Tokens, Access Tokens, and Audience Checking

An OIDC **ID token** is used by an OIDC Client to confirm authentication, normally carrying the client ID as `aud`. An OAuth2 **access token** is used to call a Resource Server and needs the right audience/resource, scopes, and profile. The same IdP may sign both with one signing key, so **a valid signature is not enough**.

If the IdP follows the RFC 9068 JWT access token profile, you may need to require `typ=at+jwt` and matching validators. Do not accept just any JWT from the issuer by default. Tokens with the same `sub`/`iss` but a different `aud` must be rejected when calling the API.

| Token | Typical audience | Used for |
| --- | --- | --- |
| ID token | OIDC client_id | Client app verifying sign-in session |
| API access token | API/resource identifier | Resource Server authorization |
| Refresh token | Token endpoint/IdP semantics | Requesting a new access token, not sent directly to APIs |
| Opaque access token | Provider-managed token identifier | Introspection or opaque-token mechanisms |

A JWT Resource Server normally verifies signatures **offline once trusted keys are obtained**, without calling the IdP on every request to check if the token is still permitted. Immediate revocation before `exp` requires other strategies such as short TTLs, revocation lists, introspection, or business-level session/token management.

## 11. Operations: Connecting an IdP, Key Rotation, and Multi-Tenancy

**When switching to a real IdP**, align with the identity team on:

- Exact `iss` in both the JWT and metadata, including trailing slash and realm path.
- Official `jwks_uri`, TLS certificate hostname, supported JWS algorithms, and key-rotation policy.
- `aud` the Resource Server must accept, scope/role mapping, and token type.
- Whether access tokens are JWT or opaque, plus expiry/revocation policy.
- Whether the backend has outbound HTTPS to metadata/JWKS, and timeout/cache/retry behavior.
- Which tenant an account/service client belongs to and whether subject identity is stable.
- An IdP proxy's public issuer may differ from internal HTTP hosts; external HTTPS issuer config must be exact.
- On every deploy/key rotation, test JWTs issued with both old and new keys.

**Never use a JWKS URL supplied by request query/body/header or unverified claims.** When an API must support multiple issuers, pin an **issuer allowlist** and a corresponding decoder/validator per trust domain; use mechanisms like `JwtIssuerReactiveAuthenticationManagerResolver` per version docs. Arbitrary issuer discovery risks SSRF and trust boundary confusion.

### Startup Independence from the IdP Does Not Mean Authentication Is Always Available

With issuer-only in Boot/Security 6.5, discovery can be lazy. With both issuer and JWKS, metadata discovery is unnecessary. Yet if a new signing key is not in cache and the JWK endpoint is down, the Resource Server cannot verify JWTs. In that case it must **fail closed**, return an appropriate error, and emit metrics; never fall back to `permitAll()` or decode without signature checks.

### Verification Workflow Using curl

Only run against IdP domains you are authorized to query:

```bash
curl --fail --show-error --silent \
  "https://idp.example.test/realms/acme/.well-known/openid-configuration"
```

Check the `issuer`/`jwks_uri` fields in the actual metadata; discovery endpoints may use different paths depending on standard/IdP.

```bash
curl --fail --show-error --silent \
  "https://idp.example.test/realms/acme/certs"
```

Verify that JWKS has valid `keys`, `kid`, and the expected kty/algorithm. Never paste real access tokens/refresh tokens into online decode websites and never use `curl -k` in production.

## 12. Common Error Reference

| Symptom | Cause | Fix |
| --- | --- | --- |
| Startup OK, but first JWT request gets 401 | Discovery/JWKS unreachable or bad token | Separate metadata/network/token causes; test issuer |
| Discovery 404 | Wrong issuer URL or IdP lacks standard endpoint | Check IdP metadata/docs; consider pinning JWK URI |
| JWKS returns HTML/login page | Wrong JWK URL, proxy redirect, or access denied | Use the exact public signing keys endpoint |
| Wrong `iss` | Token issued from another realm/tenant, trailing slash mismatch | Exact canonical issuer |
| Wrong `aud` | Token meant for another client/resource | Configure Boot audiences and request the right token |
| `kid` not found | JWK rotation or wrong provider JWKS | Check JWK Set and cache/rotation |
| Signature fails despite matching `kid` | Public key does not match private signer | Use only the issuer's trusted JWKS |
| `exp` expired | Old token or clock drift | Obtain a fresh token, sync NTP |
| `nbf` in the future | Clock skew or token not yet active | Evaluate moderate clock skew |
| Valid token, but GET returns 403 | Insufficient scope/authority | Map `SCOPE_` properly; check rules |
| JWT from another IdP still accepted | Missing issuer validation | Add issuer validator; write negative tests |
| ID token accepted by API | Missing aud/token type policy | Accept only access tokens meant for the API |
| Base64-decoded JWT treated as valid | Signature not verified | Use `ReactiveJwtDecoder` with validators |
| Custom decoder lost defaults | Forgot time/issuer checks | Compose `JwtValidators.createDefaultWithIssuer` |
| Used `HttpSecurity` in WebFlux | Wrong stack | Use `ServerHttpSecurity` |
| Used synchronous `JwtDecoder` in Netty | Mixes Servlet stack | Use `ReactiveJwtDecoder` |
| JWKS network timeout | DNS, TLS, firewall, IdP outage | HTTPS egress, timeout, monitoring |
| Configured public HTTP JWKS URL | MITM can swap keys | HTTPS with cert/hostname verification |
| Trusted `jku` from user JWT | SSRF / key substitution | Pin trusted JWKS URL |
| Old key deleted too early | Unexpired JWTs return 401 | Overlap rotation beyond token TTL |
| API accepts scope without owner check | IDOR | Enforce authorization in service/repository |
| Multi-tenant picks arbitrary issuer from URL | Trust confusion | Issuer allowlist, tenant-aware policy |
| Logging Authorization header | Exposes Bearer token | Mask/redact tokens |
| Fixing 401 with `permitAll()` | Bypasses authentication | Stay fail-closed and fix the root cause |

### Distinguishing 401 and 403

| Status | Typically occurs when |
| --- | --- |
| 401 Unauthorized | Missing Bearer, malformed JWT, wrong signature/iss/aud, expired or future `nbf` |
| 403 Forbidden | Authenticated JWT lacking required scope or business permission |
| 200 OK | Valid token + matching issuer/audience/scope + allowed by business policy |
| JWKS network error | Never grants data; exact HTTP status depends on exception handling and needs telemetry |

Do not conclude that every JWKS error always returns the same HTTP status; the mandatory rule is **never release protected data if the JWT cannot be verified**.

## 13. Checklist and Exercises

### Pre-Production Checklist

1. Canonical issuer confirmed with the IdP team; public metadata uses the exact external HTTPS URL.
2. JWKS URL taken from provider documentation/metadata, not guessed via suffix.
3. Spring WebFlux has Resource Server JWT config and does not mix in MVC classes.
4. `issuer-uri` + `audiences` configured; if pinning JWK, issuer validator is still retained.
5. JWT access tokens use RS256 or a policy-trusted algorithm; `alg=none` rejected.
6. Tests cover signature, wrong key/kid, wrong issuer, wrong audience, `exp`/`nbf`, and scope.
7. If using a custom `ReactiveJwtDecoder`, default issuer/time validators are kept and audience checks are configured.
8. Security dependency is on a patched and supported version; review CVE-2026-22748 when upgrading.
9. API rejects ID tokens used as access tokens; verify type/aud per IdP.
10. Runbook exists for JWKS TLS, egress allowlist, caching, and rotation.
11. Never log raw JWTs, private keys, client secrets, or session IDs.
12. Service/repository layer still checks owner/tenant/resource-specific access.
13. Never fall back to permit when JWKS/IdP fails.
14. Multi-issuer uses an allowlist; never fetch keys from token-supplied URLs.
15. Test staging through real reverse proxies and certificates.

### Exercises

1. Run the 11 tests; explain why `@DynamicPropertySource` can use a loopback JWKS while keeping an HTTPS issuer.
2. Remove the audience property in a test branch and run the wrong-audience test; analyze the risk.
3. Change `issuer-uri` to another realm while keeping JWKS, and verify a validly signed JWT is still rejected.
4. Try an `issuer-uri`-only setup: build a mock metadata endpoint publishing `jwks_uri` to test real discovery.
5. Try a `jwk-set-uri`-only setup: add an issuer validator before treating the configuration as secure.
6. Create a JWKS with 2 public keys, alternate signing, and test key rotation; never publish private keys.
7. Add `SCOPE_inventory.write` to a protected POST endpoint, ensuring role/scope and CSRF policies align.
8. Add a multi-tenant ownership predicate for a resource endpoint with an ID; do not check only scopes.
9. Test a JWT whose `aud` is an OAuth2 Client ID (ID token) and ensure the API rejects it.
10. Configure a custom `NimbusReactiveJwtDecoder` and run the wrong-issuer test; then add `JwtValidators.createDefaultWithIssuer`.
11. Simulate a JWKS outage and observe fail-closed/cached-key behavior without disabling signatures.
12. Use the real IdP's public HTTPS issuer and official JWKS URI on staging; verify TLS and callback URLs.

## Summary

- **`issuer-uri`** is the trusted issuer identifier, used for metadata discovery when needed and matching `iss`.
- **`jwk-set-uri`** is where public signing keys are fetched for signature verification, not a replacement for issuer/audience validators.
- **Declaring both** pins JWKS directly while still validating the issuer; `audiences` enforces the target API.
- Spring Security 6.5 with Boot defaults can defer discovery lazily, yet runtime verification still needs trusted keys.
- In WebFlux, use `ReactiveJwtDecoder`, `ServerHttpSecurity`, and `SecurityWebFilterChain`; avoid custom decoders that drop default validators.
- Never grant access when a token is unverified, JWKS fails, or the JWT comes from the wrong issuer/audience.

## References

- [Spring Security 6.5 — OAuth 2.0 Resource Server JWT (Reactive)](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive Resource Server](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/index.html)
- [Spring Boot 3.5 — Resource Server configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [Spring Security — NimbusReactiveJwtDecoder Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html)
- [Spring Security — JwtValidators Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/JwtValidators.html)
- [Spring Security Advisory — CVE-2026-22748](https://spring.io/security/cve-2026-22748/)
- [Spring Boot 3.5.16 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8414 — OAuth2 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [OpenID Connect Discovery](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [RFC 9068 — JWT Profile for OAuth2 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
