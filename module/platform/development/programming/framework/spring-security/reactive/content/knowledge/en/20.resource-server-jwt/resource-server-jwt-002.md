# Setting Up Resource Server and JOSE Dependencies in Spring Security Reactive

## 1. Goal: A WebFlux API That Properly Verifies JWT Bearer Tokens

An **OAuth2 Resource Server** is an API protecting resources; it receives access tokens issued by an Authorization Server (AS) and decides whether to accept the request. When an access token is represented as a **signed JWT**, the Resource Server must parse the token syntax, verify the **signature**, check critical claims such as issuer, expiration, not-before, and audience, and then convert the permissions into an `Authentication` used within Spring Security.

In Spring Security reactive/WebFlux, these responsibilities require **two distinct modules**:
- `spring-security-oauth2-resource-server`: mechanism for receiving and processing Bearer access tokens, Resource Server authentication/authorization.
- `spring-security-oauth2-jose`: JWT/JWS support and related verification operations via the JOSE/JWT library (Nimbus); contains classes such as `NimbusReactiveJwtDecoder`.

With **Spring Boot**, the simplest and recommended installation is **one starter**:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
~~~

This starter pulls in the required Resource Server/JWT components, including JOSE, according to the version set managed by Spring Boot. **There is no need to declare `spring-security-oauth2-jose` separately if you already use the starter and have a proper dependency graph.** Conversely, if you do **not** use the Boot starter and pick dependencies directly, you need both modules to process JWTs.

Diagram:

~~~text
Client / SPA / other backend
     │
     │ GET /api/catalog
     │ Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
     ▼
┌──────────────────────────────────────────────┐
│ Spring Boot WebFlux API                      │
│                                              │
│ spring-boot-starter-oauth2-resource-server   │
│  ├─ spring-security-oauth2-resource-server   │
│  │    Bearer authentication + authorization  │
│  └─ spring-security-oauth2-jose              │
│       JWT parsing / JWS signature verify    │
│       NimbusReactiveJwtDecoder              │
│                                              │
│  → JwtAuthenticationToken                    │
│  → SCOPE_catalog.read / other authorities    │
│  → Controller / service                      │
└──────────────────────────────────────────────┘
     ▲
     │ Public keys configured or fetched via JWKS
     │
Authorization Server / Identity Provider
  issuer: https://idp.example.test/issuer
  JWKS:   https://idp.example.test/jwks
~~~

**Lesson goal:** know how to install the right dependencies, configure the JWT verification source, understand WebFlux APIs instead of Servlet ones, bootstrap a Java 17+ project, and test **401, 403, 200** with real signed tokens. The lesson also distinguishes JWT, JOSE, JWS, JWE, JWK, JWKS, scopes, and common implementation pitfalls.

### Expected Outcomes

After this lesson you can:
1. Explain why adding only `spring-security-oauth2-resource-server` is insufficient when configuring JWT manually without `spring-security-oauth2-jose`.
2. Install the proper Resource Server starter using Gradle/Maven without mixing Servlet and WebFlux stacks.
3. Understand `iss`, `aud`, `exp`, `nbf`, `sub`, `scope` and how the Resource Server evaluates tokens.
4. Choose `issuer-uri`, `jwk-set-uri`, `public-key-location`, or `ReactiveJwtDecoder` based on your trust architecture.
5. Configure `SecurityWebFilterChain` and `ServerHttpSecurity.oauth2ResourceServer(...).jwt(...)`.
6. Understand `JwtAuthenticationToken`, `ReactiveJwtDecoder`, `NimbusReactiveJwtDecoder`, and `SCOPE_...` authorities.
7. Test offline using a test-only RSA signing key, genuinely exercising the signature verification path on WebFlux.
8. Distinguish `mockJwt()` (which skips signature checking) from real Bearer JWT testing.
9. Diagnose dependency, issuer, audience, JWK key rotation, HTTPS, clock skew, and invalid signature errors.
10. Keep private keys secret, reject attacker-suggested algorithms/kid/jku, and never use an ID Token in place of an access token.

## 2. How Do JWT, JOSE, JWS, JWE, JWK, and JWKS Differ?

These acronyms are related, not synonymous.

| Term | Meaning | Role in JWT Resource Server |
| --- | --- | --- |
| **JWT** (JSON Web Token) | Format representing claims as a JSON-based token | Carries `iss`, `sub`, `aud`, `exp`, `scope`... |
| **JOSE** (JSON Object Signing and Encryption) | Family of specs for signing, encrypting, and managing JSON keys | Cryptographic/verification foundation of JWT |
| **JWS** (JSON Web Signature) | Format for **signed** data | API access JWTs are typically signed compact JWS |
| **JWE** (JSON Web Encryption) | Format for **encrypted** data | Not handled the same as JWS-signed JWTs by default; requires dedicated decoder/decryption design when used |
| **JWK** (JSON Web Key) | JSON representation of a key, with `kty`, `kid`... | Public key to verify signatures |
| **JWKS** (JSON Web Key Set) | JSON object containing an array of `keys` | Authorization Server publishes a list of public keys |
| **JWA** (JSON Web Algorithms) | Algorithm names and requirements | For example `RS256`, `ES256` |
| **Bearer token** | Credential usable by whoever holds it per the token's permissions | `Authorization: Bearer ...` header; must be protected from exposure |

### 2.1. Compact JWS Structure for a JWT

A JWS-signed JWT typically has **three parts**:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Example decoded header/payload content:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "issuer-key-2026-11"
}
~~~

~~~json
{
  "iss": "https://idp.example.test/issuer",
  "sub": "user-123",
  "aud": ["catalog-api"],
  "iat": 1790000000,
  "nbf": 1790000000,
  "exp": 1790003600,
  "scope": "catalog.read"
}
~~~

**The two JSON blocks above are examples of claim shapes**, not valid tokens signed by a real issuer; the `iat/nbf/exp` timestamps only illustrate the NumericDate format and are not meant as current test fixtures.

Important points:
- JWS header and payload are **Base64URL-encoded, not secretly encrypted**. Anyone holding the token can read the claims.
- The signature detects tampering and proves the issuer holds the corresponding key; reading the payload alone is never enough for verification.
- `alg` in the header is untrusted token input before the decoder verifies it. The backend must **only accept algorithms configured for the issuer**, never switch algorithms arbitrarily based on the header.
- `kid` helps select a key in the JWKS. It does **not** grant permissions and must not be used to load arbitrary files or URLs.
- A compact JWE typically has **five parts**, unlike JWS's three parts. Do not assume the starter automatically decrypts every kind of JWE.
- Having a valid signature is not enough: you must also verify `iss`, `aud`, timestamps, token type, and permissions.

### 2.2. What Does a Public JWKS Look Like?

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "issuer-key-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "PUBLIC_RSA_MODULUS_BASE64URL",
      "e": "AQAB"
    }
  ]
}
~~~

The values above are **structural placeholders**, not a JWK usable for verification. For an RSA public JWK:
- `n` is the public modulus.
- `e` is the public exponent.
- `kid` is the key identifier used to look up the key in the JWKS.
- `use=sig` indicates signing usage.
- `alg` may indicate the expected algorithm, though the application must still enforce trusted algorithms.

A JWKS used by a Resource Server should normally publish only **public key material**—never expose the private exponent or private signing key on a public endpoint. For a private RSA JWK, the `d` field holds the secret portion and must never be published.

### 2.3. The JOSE Dependency Is Not JWE Auto-Configuration

`spring-security-oauth2-jose` provides JWT/JWS infrastructure and uses the Nimbus JOSE + JWT SDK. Do not assume that merely adding the JOSE starter makes WebFlux automatically:
- Issue JWTs.
- Decrypt all JWEs regardless of algorithm and key.
- Perform OIDC login authentication.
- Create an OAuth2 Authorization Server.
- Know on its own which issuer/audience to accept.

These functions are **distinct roles**. A JWT Resource Server primarily **verifies signed access tokens** and holds no private signing key. If JWE or a specialized token profile is needed, you must determine the decryption/validation mechanism and check the capabilities of the corresponding decoder/validator.

## 3. Distinguishing Three OAuth2 Roles That Commonly Get the Wrong Starter

| Role | Responsibility | Appropriate Spring Boot starter |
| --- | --- | --- |
| **OAuth2 Client** | Redirects users to the Authorization Server, handles authorization codes, may perform OIDC login or call other APIs | `spring-boot-starter-oauth2-client` |
| **Resource Server** | Receives Bearer access tokens and protects APIs | `spring-boot-starter-oauth2-resource-server` |
| **Authorization Server** | Issues tokens, manages clients/grants/keys per auth server product | Spring Authorization Server and dedicated config, **not** enabled merely by the Resource Server starter |

An application can play multiple roles, but do not add every starter “just in case” without a use case.

For example:
- Frontend server A signs users in via OIDC, acting as an OAuth2 Client.
- API B receives `Authorization: Bearer access_token` and only verifies/authorizes, acting as a Resource Server.
- Identity Provider C issues tokens/JWKS, acting as an Authorization Server.

**Warning:** An OIDC ID Token is used by the client to confirm user authentication and **should not be used in place of an access token to call a Resource Server**. An ID Token's audience is typically the OAuth2 client ID, not `catalog-api`; if a Resource Server only checks the signature and forgets `aud`, it may mistakenly accept an ID Token.

## 4. Installing Dependencies with Gradle

### 4.1. Spring Boot 3.3.13, Gradle 8.x, Java 17+

Minimal project with WebFlux REST and OAuth2 Resource Server:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**There is no need** to add a separate JOSE dependency when using the Boot Resource Server starter with a standard dependency graph. The starter pulls in both Spring Security Resource Server and the JOSE components needed for JWT.

`spring-boot-starter-webflux` is the reactive HTTP stack; `spring-boot-starter-oauth2-resource-server` adds Spring Security Resource Server. If you accidentally add Servlet `spring-boot-starter-web` to the same app, Spring Boot may choose MVC instead of WebFlux based on the classpath, and `ServerHttpSecurity` code will not take effect as expected.

The project is pinned to Spring Boot 3.3.13 for consistency with the Java 17/Spring Security 6.3 examples in this lesson; do not treat this as advice to use an older version for production systems at the time of reading. Use a supported version and test upgrades during real deployment.

### 4.2. If Not Using the Spring Boot Starter

A project managing dependencies directly needs at least two Spring Security modules, alongside WebFlux/Security core:

~~~groovy
// SNIPPET for projects managing the Spring Security BOM manually.
implementation 'org.springframework.security:spring-security-oauth2-resource-server'
implementation 'org.springframework.security:spring-security-oauth2-jose'
~~~

Do not copy these two lines into a project that already has the starter just to duplicate dependencies. When not using Boot, you must manage **compatible versions** for Spring Security, Spring Framework, Reactor, and Nimbus. Use the appropriate BOM/platform rather than mixing incompatible releases.

### 4.3. Inspecting the Dependency Tree

From the project directory:

~~~bash
gradle dependencies --configuration runtimeClasspath
gradle dependencyInsight --dependency spring-security-oauth2-resource-server --configuration runtimeClasspath
gradle dependencyInsight --dependency spring-security-oauth2-jose --configuration runtimeClasspath
~~~

If using the Gradle Wrapper:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-oauth2-jose --configuration runtimeClasspath
~~~

Look for these modules:
- `spring-security-oauth2-resource-server`.
- `spring-security-oauth2-jose`.
- `spring-security-oauth2-core` and supporting Spring Security components.
- Nimbus JOSE + JWT pulled in by the JOSE module.
- Reactor/WebFlux pulled in by the WebFlux starter.

**Do not hard-guess the dependency tree or all transitive versions**: actual results depend on the BOM, plugins, exclusions, and Gradle resolution. Run `dependencyInsight` to see where a dependency came from and whether it was excluded or overridden.

If a project has multiple paths pulling the same module, Gradle normally resolves a single version rather than putting “two versions of JOSE” on the runtime classpath simultaneously. Still, a wrong version override can cause missing classes/methods. Do not attempt to fix it by adding an arbitrary Nimbus version without checking the BOM.

## 5. Installing Dependencies with Maven

With the Spring Boot parent managing versions:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webflux-jwt-resource</artifactId>
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
~~~

Check:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.security:spring-security-oauth2-resource-server
mvn dependency:tree -Dincludes=org.springframework.security:spring-security-oauth2-jose
~~~

**Choose one build system**: Gradle or Maven. The `build.gradle` and `pom.xml` files in these two sections are **two alternatives**, not an indication that an application should use both.

## 6. Configuring the JWT Verification Source

There are several ways to supply public keys and the issuer. The recommended option depends on your Authorization Server architecture.

### 6.1. `issuer-uri` Only — Discovery from the Authorization Server

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          audiences:
            - catalog-api
~~~

The Issuer URI must match the `iss` claim issued by the real Authorization Server. Spring Security can rely on OIDC/OAuth2 Authorization Server metadata to discover the JWKS location. Once the decoder knows the public keys, it verifies JWTs signed by the AS.

When using `issuer-uri`, note:
- The provider must expose a metadata endpoint in a structure Spring Security supports, or `jwk-set-uri` must be declared directly.
- The metadata/JWKS endpoint must be reachable over HTTPS and trusted.
- Decoder initialization behavior and discovery timing may vary across versions/configurations; in some setups, application startup may depend on Authorization Server availability. Do not rely on a blanket assumption that “issuer-uri will never make a network call at startup”.
- Never build `issuer-uri` from per-request query parameters/user input. It must be an allowlisted trust configuration.
- `audiences` ensures the token was actually issued **for this API** rather than just being any JWT from the same issuer meant for another system.

### 6.2. `issuer-uri` + `jwk-set-uri` — Avoiding Metadata Discovery to Locate JWKS

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          jwk-set-uri: https://idp.example.test/jwks
          audiences:
            - catalog-api
~~~

In this case:
- `jwk-set-uri` points directly to where public keys are fetched.
- No discovery call is needed to find the JWKS URL at initialization.
- `issuer-uri` is still provided to **validate the `iss` claim**.
- This does not guarantee JWKS is always fetched and cached successfully during an IdP outage; fetching new keys or uncached `kid`s still depends on the network.
- It does not mean the backend will never need to contact the IdP at runtime.
- The JWK URL is a **pre-configured** trusted infrastructure URL, not taken from the token's `jku`/`x5u` header.

**Setting only `jwk-set-uri` and forgetting `issuer-uri` may lose Boot's default issuer validation**, depending on the selected validator. Always specify and verify both issuer and audience; never trust that a valid signature from a key proves the token is meant for your application.

### 6.3. `public-key-location` — A Static Public Key

When the Authorization Server does not publish a JWKS but provides a stable, securely distributed public key:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          public-key-location: classpath:keys/idp-public.pem
          audiences:
            - catalog-api
~~~

This is an architectural choice, not an ideal default:
- Key rotation must be organized separately because a static public key does not auto-update like JWKS.
- Corresponding **issuer validation** must be configured/checked; do not assume a static public key automatically checks `iss`.
- Package only the **public verification key** in the Resource Server; never put the AS's private key in resource files.
- The `public-key-location` property requires the public key in a format supported by the Spring Boot decoder.
- When using a custom `ReactiveJwtDecoder`, you must configure validators for `iss`, `aud`, and timestamps to avoid losing Boot's checks.

### 6.4. When to Use an Application-Provided `ReactiveJwtDecoder`?

In WebFlux, the decoder interface is:

~~~java
org.springframework.security.oauth2.jwt.ReactiveJwtDecoder
~~~

A configuration excerpt:

~~~java
@Bean
ReactiveJwtDecoder jwtDecoder() {
    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder
            .withJwkSetUri("https://idp.example.test/jwks")
            .build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(
            "https://idp.example.test/issuer"));

    return decoder;
}
~~~

**This is not a complete production configuration:** the example shows registering a `ReactiveJwtDecoder` and checking issuer/time, but has not added audience validation yet. When you provide your own decoder bean, it **replaces Boot's auto-configured decoder path**; you must preserve all required security validators. Do not copy the code above and forget `aud`.

Using `ReactiveJwtDecoders.fromIssuerLocation(issuer)` is an API path that builds a decoder from issuer discovery with appropriate default validators. Choosing properties configuration is simplest if customization is not needed.

## 7. Path of a Bearer JWT in WebFlux Security

~~~text
GET /api/catalog
Authorization: Bearer <JWT>
       │
       ▼
Spring Security WebFilterChain
       │
       ▼
Bearer token authentication
       │
       ▼
ReactiveJwtDecoder.decode(jwt) → Mono<Jwt>
       │
       ├─ Parse token format
       ├─ Verify JWS signature using trusted RSA public JWK
       ├─ Reject unsupported / untrusted alg
       ├─ Validate exp / nbf / iss / aud
       └─ Convert claims to Jwt object
       │
       ▼
JwtReactiveAuthenticationManager + authorities converter
       │
       ▼
JwtAuthenticationToken in SecurityContext (Reactor Context)
       │
       ▼
authorizeExchange:
  hasAuthority("SCOPE_catalog.read")
       │
       ├─ Missing Bearer / invalid token → 401
       ├─ Valid JWT but lacks permission → 403
       └─ Valid JWT and right scope → Controller 200
~~~

Common classes in Spring Security reactive:
- `ReactiveJwtDecoder`: reactive contract accepting a token string and returning `Mono<Jwt>` or an error.
- `NimbusReactiveJwtDecoder`: common decoder based on the Nimbus JOSE + JWT SDK.
- `Jwt`: JWT decoded and verified against the decoder's validators.
- `JwtReactiveAuthenticationManager`: applies the decoder during authentication.
- `JwtAuthenticationToken`: Authentication created after a Bearer JWT is accepted.
- `ReactiveSecurityContextHolder`: accesses Authentication via Reactor Context rather than Servlet ThreadLocal.
- `ServerHttpSecurity` / `SecurityWebFilterChain`: WebFlux HTTP security pipeline.

Do not use synchronous Servlet `org.springframework.security.oauth2.jwt.JwtDecoder`/`NimbusJwtDecoder` instead of `ReactiveJwtDecoder` in `ServerHttpSecurity`. This code **does not manually call `block()`/`subscribe()`** to query JWTs on the event loop.

### 7.1. Default Principal and Authorities

In a typical JWT Resource Server setup:
- Principal is a `Jwt`, commonly injected via `@AuthenticationPrincipal Jwt jwt`.
- `Authentication.getName()` typically comes from the `sub` claim (customizable via converter).
- OAuth2 scopes in the `scope` or `scp` claim are mapped to authorities prefixed with `SCOPE_`.

Example:

~~~json
{
  "sub": "alice-123",
  "scope": "catalog.read catalog.write"
}
~~~

typically produces authorities:

~~~text
SCOPE_catalog.read
SCOPE_catalog.write
~~~

Rule:

~~~java
.pathMatchers(HttpMethod.GET, "/api/catalog")
    .hasAuthority("SCOPE_catalog.read")
~~~

Do **not** call `hasRole("catalog.read")` expecting it to match the scope. `hasRole("X")` normally checks the authority `ROLE_X`, which differs from `SCOPE_X`.

### 7.2. Authentication Does Not Mean Specific Resource Authorization

A valid JWT with `SCOPE_catalog.read` only permits **catalog read functionality**, not reading every other tenant's documents. For an endpoint like `GET /api/orders/{id}`, the service/repository must still check owner/tenant/membership or ACLs.

Similarly, a JWT containing a `roles` claim does not automatically turn into Spring Security authorities as desired; to use it, you must define a converter and a trusted claim source. Never assign `ROLE_ADMIN` based on email or query parameters.

## 8. Standalone WebFlux Example: Catalog API Accepting JWT

This section provides a project **buildable with Java 17+, Spring Boot 3.3.13, and Gradle 8.x**, with production-style issuer/JWKS configuration. Unit/integration tests run **offline** using a test-only public key decoder, and JWTs are genuinely RSA-signed in tests.

**Intentional limitation:** `application.yml` uses `idp.example.test` URLs as illustrative architectural addresses. There is no real Authorization Server there, so `bootRun` starts the app but cannot accept production tokens until you replace issuer and JWKS with a real provider. The test generates an RSA keypair itself and supplies a test-only `ReactiveJwtDecoder`, **making no external IdP calls**.

### 8.1. Directory Structure

~~~text
webflux-jwt-resource/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── ResourceApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── CatalogController.java
    │   └── resources/application.yml
    └── test/java/demo/
        └── JwtResourceServerTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-jwt-resource'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Do not add a manual `spring-security-oauth2-jose` version since the starter already provides it. Do not add the Spring MVC starter to avoid switching the HTTP stack.

### 8.2. `application.yml`: Issuer, JWKS, and Audience

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          jwk-set-uri: https://idp.example.test/jwks
          audiences:
            - catalog-api
~~~

**These are placeholder endpoints**, not a real JWT Provider. When deploying:
- `issuer-uri` must match the exact `iss` from the trusted AS's access tokens.
- `jwk-set-uri` must be an HTTPS endpoint published by the AS per its metadata/documentation.
- `audiences` must include the audience issued by the AS for this API.
- Configure TLS/truststore DNS, egress proxy, and JWKS key rotation for the environment.
- If the AS does not issue JWT access tokens of the proper type, you may need opaque-token introspection instead of forcing an opaque token through a JWT decoder.

### 8.3. Main Class

`src/main/java/demo/ResourceApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResourceApplication.class, args);
    }
}
~~~

### 8.4. SecurityConfig: Proper WebFlux `ServerHttpSecurity`

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .pathMatchers(HttpMethod.GET, "/api/catalog")
                    .hasAuthority("SCOPE_catalog.read")
                .pathMatchers(HttpMethod.GET, "/api/manage")
                    .hasAuthority("SCOPE_catalog.write")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .build();
    }
}
~~~

Meaning:
1. `oauth2ResourceServer(...).jwt(...)` selects Bearer JWT authentication.
2. `GET /health` is public and returns no tokens or personal data.
3. `GET /api/me` requires a valid JWT but no extra scope.
4. `GET /api/catalog` requires `SCOPE_catalog.read`.
5. `GET /api/manage` requires `SCOPE_catalog.write`.
6. `anyExchange().denyAll()` blocks undeclared routes.
7. `httpBasic` and `formLogin` are disabled so this API uses only Bearer tokens.
8. **CSRF is not disabled** in the example; the demo endpoints are all safe GETs. If adding POST/PUT/DELETE, design CSRF per the threat model: a Bearer-only API accepting no ambient browser credentials may have a specific exception or dedicated chain, whereas session/cookie APIs still require CSRF protection.

**Do not put `csrf.disable()` globally without checking whether browser cookies/Basic or other endpoints exist in the chain.** Choosing a JWT resource server does not automatically eliminate CSRF risk for other credentials.

### 8.5. CatalogController: Retrieving the Verified Jwt

`src/main/java/demo/CatalogController.java`:

~~~java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
class CatalogController {

    @GetMapping("/health")
    Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping("/api/me")
    Mono<Map<String, String>> me(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of(
            "subject", jwt.getSubject(),
            "issuer", jwt.getIssuer().toString()
        ));
    }

    @GetMapping("/api/catalog")
    Mono<Map<String, List<String>>> catalog() {
        return Mono.just(Map.of(
            "items", List.of("webflux", "oauth2", "jwt")
        ));
    }

    @GetMapping("/api/manage")
    Mono<Map<String, String>> manage() {
        return Mono.just(Map.of(
            "capability", "catalog.write"
        ));
    }
}
~~~

Returns only a few fields for learning purposes; do **not** return raw tokens, authorization headers, private keys, session IDs, or full claims not approved for exposure. `jwt.getSubject()` is read from the post-decoder principal, not by manually Base64-decoding the token string.

If production uses access tokens lacking a URI-representable issuer or `sub`, define an explicit token contract and check before calling `toString()`; the demo/tests intentionally populate both `iss` and `sub`.

## 9. Offline Testing with Real RSA-Signed JWTs: No Network IdP Needed

A test using only `mockJwt()` proves the authorization converter/matcher works, but **does not** exercise JWT signature, issuer, audience, or expiration checks. To genuinely test the JOSE layer, tests need to generate tokens **signed by a test-only private RSA key** and configure `NimbusReactiveJwtDecoder` with the **corresponding public RSA key**.

Architecturally important:
- **Production Resource Servers do NOT hold private signing keys.**
- **Only test code** generates an internal private key to sign dummy access tokens.
- `@TestConfiguration` is imported in the test and does not live in `src/main`.
- The public decoder in tests must verify issuer, audience, and timestamps just like the production security contract.
- Tests use `WebTestClient` traversing actual WebFlux security filters (not `mockJwt()`), making it possible to test 401 on invalid signatures.

### 9.1. How to Structure the Test

`src/test/java/demo/JwtResourceServerTests.java`:

~~~java
package demo;

import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.proc.SecurityContext;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
@Import(JwtResourceServerTests.OfflineJwtKeys.class)
class JwtResourceServerTests {

    private static final String ISSUER =
        "https://idp.example.test/issuer";

    @Autowired
    ApplicationContext context;

    @Autowired
    JwtEncoder encoder;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class OfflineJwtKeys {

        @Bean
        KeyPair testSigningKeys() {
            try {
                KeyPairGenerator generator =
                    KeyPairGenerator.getInstance("RSA");
                generator.initialize(2048);
                return generator.generateKeyPair();
            }
            catch (GeneralSecurityException error) {
                throw new IllegalStateException(error);
            }
        }

        @Bean
        JwtEncoder testJwtEncoder(KeyPair testSigningKeys) {
            RSAKey rsa = new RSAKey.Builder(
                (RSAPublicKey) testSigningKeys.getPublic())
                .privateKey(
                    (RSAPrivateKey) testSigningKeys.getPrivate())
                .keyID("test-key")
                .build();

            return new NimbusJwtEncoder(
                new ImmutableJWKSet<SecurityContext>(
                    new JWKSet(rsa)));
        }

        @Bean
        ReactiveJwtDecoder testJwtDecoder(KeyPair testSigningKeys) {
            NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder.withPublicKey(
                    (RSAPublicKey) testSigningKeys.getPublic())
                    .build();

            OAuth2TokenValidator<Jwt> audienceValidator =
                jwt -> jwt.getAudience() != null
                    && jwt.getAudience().contains("catalog-api")
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error(
                                "invalid_token",
                                "Missing catalog-api audience",
                                null));

            // Signature + standard time/issuer + expected audience.
            decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                    JwtValidators.createDefaultWithIssuer(
                        "https://idp.example.test/issuer"),
                    audienceValidator));

            return decoder;
        }
    }

    // Sign a REAL token in test using a test-only RSA private key.
    // Use another encoder to simulate a token signed with the wrong key.
    private String signed(
            JwtEncoder tokenEncoder,
            String issuer,
            String audience,
            String scope,
            Instant expiration) {

        Instant now = Instant.now();

        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject("alice-123")
            .audience(List.of(audience))
            .issuedAt(now.minusSeconds(10))
            .notBefore(now.minusSeconds(10))
            .expiresAt(expiration)
            .claim("scope", scope)
            .build();

        JwsHeader header = JwsHeader
            .with(SignatureAlgorithm.RS256)
            .keyId("test-key")
            .build();

        return tokenEncoder.encode(
            JwtEncoderParameters.from(header, claims))
            .getTokenValue();
    }

    private String valid(String scopes) {
        return signed(encoder, ISSUER, "catalog-api", scopes,
            Instant.now().plusSeconds(600));
    }

    @Test
    void healthIsPublic() {
        client.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void missingBearerTokenIsUnauthorized() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void malformedJwtIsUnauthorized() {
        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth("not-a-jwt"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void realSignedTokenCanReadItsSubject() {
        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth(valid("catalog.read")))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.subject").isEqualTo("alice-123")
            .jsonPath("$.issuer").isEqualTo(ISSUER);
    }

    @Test
    void scopeCatalogReadBecomesAuthority() {
        client.get().uri("/api/catalog")
            .headers(h -> h.setBearerAuth(valid("catalog.read")))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.items[0]").isEqualTo("webflux");
    }

    @Test
    void signedTokenWithoutRequiredScopeIsForbidden() {
        client.get().uri("/api/catalog")
            .headers(h -> h.setBearerAuth(valid("profile")))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void differentScopeCannotReadManagementEndpoint() {
        client.get().uri("/api/manage")
            .headers(h -> h.setBearerAuth(valid("catalog.read")))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void scopeCatalogWriteCanReadManagementEndpoint() {
        client.get().uri("/api/manage")
            .headers(h -> h.setBearerAuth(valid("catalog.write")))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.capability").isEqualTo("catalog.write");
    }

    @Test
    void wrongIssuerIsUnauthorizedDespiteValidSignature() {
        String token = signed(
            encoder, "https://evil.example", "catalog-api",
            "catalog.read", Instant.now().plusSeconds(600));

        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongAudienceIsUnauthorizedDespiteValidSignature() {
        String token = signed(
            encoder, ISSUER, "unrelated-api",
            "catalog.read", Instant.now().plusSeconds(600));

        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void expiredJwtIsUnauthorized() {
        String token = signed(
            encoder, ISSUER, "catalog-api", "catalog.read",
            Instant.now().minusSeconds(600));

        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void tamperedSignatureOrUnknownSigningKeyIsRejected() {
        // Public decoder trusts only testSigningKeys; use a second keypair.
        KeyPair otherKeys;
        try {
            KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            otherKeys = generator.generateKeyPair();
        }
        catch (GeneralSecurityException error) {
            throw new IllegalStateException(error);
        }

        RSAKey wrongRsa = new RSAKey.Builder(
            (RSAPublicKey) otherKeys.getPublic())
            .privateKey((RSAPrivateKey) otherKeys.getPrivate())
            .keyID("test-key")
            .build();

        JwtEncoder otherEncoder = new NimbusJwtEncoder(
            new ImmutableJWKSet<SecurityContext>(
                new JWKSet(wrongRsa)));

        String token = signed(
            otherEncoder, ISSUER, "catalog-api",
            "catalog.read", Instant.now().plusSeconds(600));

        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void mockJwtIsUsefulForAuthorizationButDoesNotCheckSignature() {
        client.mutateWith(
                mockJwt().authorities(
                    new SimpleGrantedAuthority(
                        "SCOPE_catalog.read")))
            .get().uri("/api/catalog")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

### 9.2. What Do the Tests Prove?

| Test | Objective | Expected |
| --- | --- | --- |
| `healthIsPublic` | Public route without Bearer | 200 |
| `missingBearerTokenIsUnauthorized` | Protected route without Bearer | 401 |
| `malformedJwtIsUnauthorized` | String that is not a valid JWT | 401 |
| `realSignedTokenCanReadItsSubject` | Valid RSA signature + JWT claims | 200 |
| `scopeCatalogReadBecomesAuthority` | `scope` claim maps to `SCOPE_catalog.read` | 200 |
| `signedTokenWithoutRequiredScopeIsForbidden` | Valid token lacking permission | 403 |
| `differentScopeCannotReadManagementEndpoint` | Cannot use read scope in place of write scope | 403 |
| `scopeCatalogWriteCanReadManagementEndpoint` | Correct write scope | 200 |
| `wrongIssuerIsUnauthorizedDespiteValidSignature` | Valid signature but wrong `iss` | 401 |
| `wrongAudienceIsUnauthorizedDespiteValidSignature` | Valid signature but wrong `aud` | 401 |
| `expiredJwtIsUnauthorized` | Clearly past `exp`, beyond clock skew | 401 |
| `tamperedSignatureOrUnknownSigningKeyIsRejected` | Signing key does not match trusted public key | 401 |
| `mockJwtIsUsefulForAuthorizationButDoesNotCheckSignature` | Authorization mock; **skips real decoder** | 200 |

There are **13** test methods. The goal is to combine:
- Real path: genuinely RSA-signed Bearer string; `NimbusReactiveJwtDecoder` checks signature, issuer, audience, and timestamps, and the converter checks scopes.
- Mock path: Spring Security Test creates a simulated authentication to check authorization **without proving the signature**.

**Caution:** Testing the decoder with a test-only public RSA key does not test **network JWKS retrieval/rotation**, metadata discovery, SSL/truststore, or a real Authorization Server. Those cases require integration tests with a mock JWKS HTTP server or a test Authorization Server in a test environment; never claim they are verified just because `mockJwt()` passes.

### 9.3. Why Use a Test-Only `ReactiveJwtDecoder`?

Production `application.yml` selects issuer/JWKS URLs, whereas `OfflineJwtKeys` builds a public RSA decoder from the test keypair. Spring Boot uses the `ReactiveJwtDecoder` bean provided by the test instead of auto-configuring one from production config, so the test does not need to call `idp.example.test`.

That makes sense for testing local code/JOSE and permissions. However, precisely because the decoder was overridden, **this test has not yet verified that production `issuer-uri`/`jwk-set-uri` point to real endpoints**. Additional integration tests with JWKS/discovery and deployment checks are required.

### 9.4. Running Tests

~~~bash
gradle test
~~~

Or with the Gradle Wrapper:

~~~bash
./gradlew test
~~~

On Windows PowerShell/cmd, use `gradlew.bat test`. The Java 17+ project requires a compatible Gradle version and network access to Maven Central on the first build. **13 test cases are expected to pass when dependencies/APIs align**, but actual results must be verified by running the build/tests rather than inferred from reading snippets.

### 9.5. Commands to Run the Application

~~~bash
gradle bootRun
~~~

Public health example:

~~~bash
curl -i http://localhost:8080/health
~~~

Expected application behavior if the server starts:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

ok
~~~

Do not assert a fixed header order or exact header set since WebFlux servers and security response headers can vary. For a protected endpoint:

~~~bash
curl -i http://localhost:8080/api/catalog
~~~

The result is typically **401 Unauthorized** and `WWW-Authenticate: Bearer`. A real token must come from an Authorization Server matching the application's issuer/JWKS. For example:

~~~bash
curl -i \
  -H "Authorization: Bearer ACCESS_TOKEN_FROM_TRUSTED_AS" \
  http://localhost:8080/api/catalog
~~~

**`ACCESS_TOKEN_FROM_TRUSTED_AS` is a placeholder**, not a valid JWT. Never put real access tokens into terminal logs, screenshots, or shared documentation; in real environments use an appropriate secrets manager/tooling and HTTPS.

## 10. Why Do Some Tests Return 401 and Others Return 403?

### 10.1. 401 Unauthorized — Bearer Authentication Failure

Situations:
- No token on a protected endpoint.
- Token does not have three valid parts or has invalid Base64URL/JSON.
- `alg` header is not accepted by the decoder.
- JWS signature is wrong or `kid` key is not found in JWKS.
- JWT `exp` is expired or `nbf` is in the future beyond allowed clock skew.
- `iss` claim does not match the trusted issuer.
- `aud` claim does not include the expected API audience.
- Decoder fails to fetch the required JWKS key and the request cannot verify the token (depending on error mapping/server).

The response may include `WWW-Authenticate: Bearer error="invalid_token"` or other details depending on the error. Do not log raw tokens or over-expose verification details to public clients.

### 10.2. 403 Forbidden — Token Authenticated, Insufficient Permissions

Example valid JWT:

~~~json
{
  "sub": "alice-123",
  "aud": ["catalog-api"],
  "scope": "profile"
}
~~~

That JWT can access `/api/me` if it only requires authentication, but gets 403 on `/api/catalog` because it lacks `SCOPE_catalog.read`. **Do not fix 403 by disabling Resource Server**, and do not mistake issuer/audience validation for per-API access permissions.

Using the right status codes separates two error groups:
- **401:** credential was not accepted.
- **403:** credential was accepted, but lacks permission on the resource/rule.

Meanwhile, `404` indicates a non-existent resource or intentional non-disclosure per policy, distinct from missing dependencies/JOSE errors.

## 11. JWK Key Rotation: The Resource Server Does Not Hold Private Keys

In an asymmetric model:
- The Authorization Server holds the private RSA/EC signing key.
- Public JWKS publishes the corresponding verification keys.
- The JWT header carries `kid` identifying the signing key.
- The Resource Server selects the matching public key and verifies the signature.
- When the AS rotates keys, JWKS updates and the decoder can fetch/cache new keys per Spring Security/Nimbus mechanics.

Timeline:

~~~text
T0  AS signs tokens with private key K1
    JWKS publishes public K1 (kid=K1)

T1  AS prepares to rotate, JWKS publishes K1 + K2
    Some tokens still use K1, new tokens may use K2

T2  AS starts signing with K2
    Resource Servers fetch key K2 as needed per cache/refresh policy

T3  Once old K1 tokens have expired and caches settle,
    AS considers removing K1 from JWKS
~~~

**Do not** remove public K1 too early while valid K1 access tokens remain unexpired (unless you intentionally want to revoke them and accept the impact). Check:
- `kid` does not collide across different active keys in the same JWKS.
- The JWKS endpoint has HTTPS and appropriate timeout/cache/observability settings.
- Never allow a JWT to specify arbitrary public key URLs via `jku`/`x5u`.
- The Resource Server accepts only the set of algorithms agreed upon with the AS.
- Behavior during a JWKS outage with cached keys and new keys must be tested.
- `iss` and `aud` are still validated after signature verification succeeds.

With static `public-key-location`, key rotation typically requires updating the file/deploy/config; with JWKS, new public keys can be fetched more flexibly. **Never store private keys in the Resource Server just to verify JWTs.**

## 12. Choosing JWS Algorithms Intentionally

In standard Spring Security JWT configuration, `NimbusReactiveJwtDecoder` defaults to trusting and verifying RS256 tokens; if the Authorization Server uses RS512/ES256 or another profile, configure **according to the issuer documentation and actual version**, never accepting arbitrary `alg` from tokens.

Example config changing the algorithm (use only when the real IdP issues RS512):

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          jwk-set-uri: https://idp.example.test/jwks
          jws-algorithms:
            - RS512
          audiences:
            - catalog-api
~~~

Adding RS512 to the allowlist when the AS only signs RS256 may cause every JWT request to fail with 401. Never solve this by allowing `alg=none`, or indiscriminately allowing both HS* and RS* such that the verifier confuses symmetric and asymmetric keys. Never hand-roll JWT signature verification via string manipulation; use an up-to-date JOSE library.

### 12.1. HS256 vs. RS256

- **HS256** is symmetric HMAC: both signer and verifier must know the same secret. When a Resource Server knows the secret, it also has the ability to sign JWTs, expanding the blast radius if the server is compromised.
- **RS256** is asymmetric RSA signing: the Resource Server only needs the public key. This model is usually better suited for multiple microservices receiving tokens from one Authorization Server.
- **ES256** is asymmetric ECDSA, with its own key/algorithm requirements.

It is not that “HS256 is always wrong” algorithmically, but in microservice architectures you must consider secret scope and separation between token issuer and verifier. Configuring `withSecretKey(...)` for a Resource Server is only appropriate under a clear trust design; never store sample secrets in production repos.

## 13. Audience, Issuer, and Type Validation: Are Dependencies Enough?

Even when Gradle reports both modules are present, an API can still be insecure if validation is incomplete.

### 13.1. Issuer Identifies the Issuing Party

`iss` must match the configured issuer. For example, `https://idp.company.example/tenant-a` and `https://idp.company.example/tenant-b` are two distinct trust namespaces. Do not strip tenant paths or arbitrarily normalize issuers.

### 13.2. Audience Identifies Who Should Accept the Token

`aud` must contain the expected API identifier such as `catalog-api`. A token from the same issuer but issued for `billing-api` must not be accepted at the Catalog API.

In Spring Boot 3.3, the property:

~~~yaml
spring.security.oauth2.resourceserver.jwt.audiences:
  - catalog-api
~~~

is supported when Boot auto-configures the decoder. With a custom `ReactiveJwtDecoder`, **configure an audience validator yourself** as in the `OfflineJwtKeys` test; properties configuration does not automatically apply to a decoder you define yourself.

### 13.3. Token Type and Intended Purpose

Do not accept every JWT from the same issuer without checking that it is an **access token intended for the Resource Server**. For example:
- An OIDC ID Token has the OAuth2 client ID as its audience, not the Catalog API.
- A JWT used for password reset or email verification shares the issuer signature but serves a different purpose.
- Some Authorization Servers follow RFC 9068 and use `typ=at+jwt`, requiring profile-appropriate rules.

If the application requires RFC 9068, dedicated profile validators/checks are needed rather than just signature and `scope`. When selecting an algorithm/type, verify against the real production Authorization Server instead of guessing from examples.

## 14. When Facing Dependency or Configuration Errors

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| Cannot find `NimbusReactiveJwtDecoder` | Missing `spring-security-oauth2-jose` or excluded | Use Boot starter, inspect `runtimeClasspath` |
| Resource Server compiles, but JWT decoder is not configured | Has resource-server module without JOSE/issuer config | Add the proper starter and `issuer-uri`/JWKS |
| `JwtDecoder` cannot be used for WebFlux | Grabbed synchronous Servlet decoder | Use `ReactiveJwtDecoder` |
| Application fails to start because issuer metadata is unreachable | Discovery/runtime decoder init depends on IdP/network in that config/version | Check URL/TLS/DNS, consider configuring JWKS directly |
| App starts, but first JWT returns 401 | Keys/JWKS unreachable or token invalid | Check redacted security logs, issuer/audience/key |
| 401 with validly signed JWT | Wrong `iss`/`aud`/`exp`/`nbf` or wrong type | Check validators; do not disable all of them |
| 401 when AS rotates keys | New `kid` but JWKS/cache not updated | Check JWKS, key overlap, cache/egress |
| 403 after JWT was already accepted | Missing scope/authority | Check `scope`/`scp`, `SCOPE_` prefix, and route rules |
| Added `spring-boot-starter-oauth2-client`, but API does not accept Bearer | Client starter does not replace Resource Server starter | Use Resource Server starter |
| Added `spring-boot-starter-web`, altering security chain | Boot chose Servlet MVC or another web application type | Keep the proper WebFlux stack |
| `mockJwt()` tests pass, but real JWTs return 401 | Mock bypasses signature/decoder | Test real signed Bearer tokens + JWKS integration |
| ID Token accepted as an access token | Missing audience/type policy | Validate `aud`/`typ`/token purpose |
| App reads `sub` but still accesses wrong tenant | Missing object/tenant authorization | Check local principal mapping, owner/tenant |
| Gateway drops `Authorization` header | Proxy does not forward required header | Configure safe forwarding without logging tokens |
| `Bearer` has token, but wrong header encoding | Sent token in query/body or bad spacing | Use `Authorization: Bearer <token>` |
| Custom decoder skips issuer/audience checks | Replaced Boot decoder and forgot validators | Use `JwtValidators`/audience validator |
| JWKS cache does not refresh properly | Egress/proxy/cache TTL/key rollover | Test rotation and availability |
| JWKS SSL/TLS error | Bad certificate/truststore/hostname | Fix trust chain; do not disable certificate checks |

### 14.1. Inspecting Logs Without Exposing Tokens

During troubleshooting, you can log:
- Request ID, route, HTTP status, error category `invalid_token`/`insufficient_scope`.
- Configured issuer and JWKS endpoint name (without credentials).
- Token `kid`/`alg` once sanitized and without exposing sensitive data; logging policy depends on the organization.
- Key cache/network state and decode latency.

**Never** log full `Authorization: Bearer ...`, private keys, secrets, refresh tokens, session cookies, or raw JWT payloads containing PII. Getting 401/403 is not a reason to print tokens to production logs.

## 15. Anti-Patterns to Avoid

### 15.1. Manually Base64-Decoding JWTs and Trusting the Payload

~~~java
// ANTI-PATTERN: no signature verification or validators!
String payloadBase64 = token.split("\\.")[1];
// Decoding and reading roles/sub directly to grant access is wrong.
~~~

A readable JWT payload **does not mean its contents are trustworthy**. An attacker can alter claims and attach any arbitrary signature. You must let `ReactiveJwtDecoder` verify signature/issuer/audience/expiration before using it as an identity.

### 15.2. Accepting `alg=none` or Letting the Token Dictate the Algorithm

Do not skip signature verification because “it's only internal calls”, and do not use the JWT's `alg` header to dynamically decide signing logic without an allowlist. The Resource Server must trust keys and algorithms based on configured policy, not unverified metadata.

### 15.3. Trusting a JWKS URL Taken from the JWT

A JWT's `jku`/`x5u` header can supply an external URL. If the backend fetches keys from that URL unchecked, an attacker can host their own JWKS containing their public key and sign forged tokens with the corresponding private key. Only use `jwk-set-uri` configured from a trusted AS, or reviewed allowlist logic.

### 15.4. Checking Only `exp` Without `iss`/`aud`

An unexpired token for another API still has no right to access Catalog. Add issuer/audience validation. For permission claims, check scopes and object authorization separately.

### 15.5. Placing Private Signing Keys in the Resource Server

A Resource Server needs no private key to verify RS256. Pushing private keys into every service widens the blast radius and violates separation of duties. The test-only private key in `src/test` is generated at runtime solely for illustration; it is not a production pattern.

### 15.6. Copying Servlet Configuration into Reactive

~~~java
// DO NOT USE in WebFlux:
HttpSecurity http; // Servlet security DSL
JwtDecoder decoder; // synchronous decoder
~~~

The right stack is `ServerHttpSecurity` and `ReactiveJwtDecoder`. If custom reactive logic is needed, compose `Mono`/`Flux` instead of calling `block()` on the Netty event loop.

### 15.7. Assuming JOSE Automatically Provides JWT Login or JWT Minting

A Resource Server receives and verifies tokens; login/OIDC redirects belong to OAuth2 Client, and issuing JWTs belongs to the Authorization Server. The JOSE library provides the necessary primitives, but does not by itself supply the full protocol or key issuance.

## 16. Practice Questions and Exercises

**Q1.** If a project does not use the Boot starter, which modules are needed for a JWT Resource Server?

**Answer:** At least `spring-security-oauth2-resource-server` and `spring-security-oauth2-jose`, along with compatible WebFlux/Spring Security dependencies.

**Q2.** With Boot, which dependency should you start with?

**Answer:** `spring-boot-starter-oauth2-resource-server`; check the dependency graph to ensure JOSE is pulled in.

**Q3.** What are the three parts of a JWT?

**Answer:** Header, payload, and signature of a compact JWS. Base64URL does not secretly encrypt the payload.

**Q4.** What is JOSE used for?

**Answer:** A family of JSON signing/encryption/key specifications such as JWS, JWE, and JWK/JWKS; the Spring Security JOSE module provides JWT decoding/signature support.

**Q5.** How do JWK and JWKS differ?

**Answer:** A JWK is a single key described in JSON; a JWKS is a set of keys, usually public, used for key rotation.

**Q6.** Does a Resource Server need the IdP's private RSA key?

**Answer:** No. With RS256, only the public verification key is needed; the private key stays on the AS.

**Q7.** What does `issuer-uri` provide?

**Answer:** Specifies the trusted issuer, can support discovery, and validates `iss` per configuration.

**Q8.** What do you gain by adding `jwk-set-uri` alongside the issuer?

**Answer:** Specifies the JWKS directly without needing discovery to find the JWKS URL, while still validating `iss` when issuer is configured.

**Q9.** Is having JWKS without audience validation secure enough?

**Answer:** No. A token from the same issuer meant for a different API could still be misused; check the resource's `aud`.

**Q10.** What authority does `scope=catalog.read` become by default?

**Answer:** `SCOPE_catalog.read`.

**Q11.** Why doesn't `hasRole("catalog.read")` match the scope?

**Answer:** `hasRole` uses the `ROLE_` prefix; scopes default to `SCOPE_`. Use `hasAuthority("SCOPE_catalog.read")`.

**Q12.** How does 401 differ from 403?

**Answer:** 401 when the Bearer token is missing/invalid; 403 when the token is accepted but lacks route permissions.

**Q13.** Can `mockJwt()` verify RSA signatures?

**Answer:** No. It simulates authentication to test authorization, bypassing the decoder. Use signed tokens + decoder in integration tests.

**Q14.** Can JWKS publish public RSA exponent/modulus values?

**Answer:** Yes; the public key is used for verification. Never publish the private exponent `d`.

**Q15.** What happens if the IdP uses RS512 while the decoder only trusts RS256?

**Answer:** Tokens are rejected; you must configure an algorithm allowlist matching the verified AS rather than opening up all algorithms.

**Q16.** Is it valid to use an OIDC ID Token to call the Catalog Resource Server?

**Answer:** No. The Resource Server should accept an access token intended for the API, validating `aud`/purpose and profile, rather than using an ID Token as a bearer access credential.

**Q17.** Does a valid JWT with `SCOPE_catalog.read` let user A view user B's orders?

**Answer:** No if business policy forbids it. Owner/tenant checks are needed in the service/repository layer.

**Q18.** Why should key rotation publish K1 and K2 overlapping?

**Answer:** So unexpired K1-signed tokens and new K2 tokens can both be verified during the transition period.

**Q19.** If a JWT has `jku=https://evil.example/jwks`, should the Resource Server fetch it?

**Answer:** No. Key sources must come from approved issuer trust configuration, never from URLs suggested by the token.

**Q20.** Does a GET-only API using Bearer tokens already need CSRF disabled?

**Answer:** Not necessarily. GET is a safe method so default CSRF does not require a token. If adding POST/PUT and the app is strictly Bearer-only, evaluate the credential model before deciding the policy.

**Q21.** When customizing `ReactiveJwtDecoder`, is the `audiences` property guaranteed to remain effective?

**Answer:** Do not assume so. A custom bean replaces Boot's auto decoder; you must configure and test validators yourself.

**Q22.** Does Spring Security Resource Server automatically create a `/.well-known/jwks.json` endpoint?

**Answer:** No. JWKS is the key source of an Authorization Server or separate infrastructure. A Resource Server normally **consumes** JWKS and does not issue signing keys itself.

**Q23.** Is JWE automatically supported by typical JWS JWT decoders?

**Answer:** Do not assume this by default; JWE is an encrypted format with separate keys/algorithms/decryption, requiring an appropriate decoder design.

**Q24.** When the dependency tree includes JOSE yet requests still return 401, should you add the dependency again?

**Answer:** No. Check for invalid signature, issuer/audience, exp, JWKS, algorithm, and the HTTP header.

## 17. Checklist for Secure JWT Resource Server Implementation

### Dependencies and Configuration

- [ ] Project genuinely runs WebFlux, not accidentally Servlet `spring-boot-starter-web`.
- [ ] Has `spring-boot-starter-oauth2-resource-server`; if not using the starter, includes both Resource Server + JOSE modules.
- [ ] Spring Boot BOM/versions aligned with Spring Security/Framework/Reactor/Nimbus.
- [ ] `gradle dependencyInsight` or `mvn dependency:tree` confirms the actual dependency graph.
- [ ] `issuer-uri` points to a verified issuer and matches `iss`.
- [ ] HTTPS JWKS endpoint is configured from a trusted IdP, not taken from tokens.
- [ ] API requires the proper audience; wrong `aud` gets 401.
- [ ] JWS algorithm allowlist matches the IdP; rejects `none`/algorithm confusion.
- [ ] Handling in place for key rotation, cache, network outage, and clock skew.
- [ ] No private signing keys placed inside the Resource Server.

### Spring Security and Permissions

- [ ] `ServerHttpSecurity.oauth2ResourceServer(...).jwt(...)` runs inside the right `SecurityWebFilterChain`.
- [ ] Undeclared routes are `denyAll` or covered by an explicit allowlist policy.
- [ ] Scopes are mapped properly to `SCOPE_`; not confused with `ROLE_`.
- [ ] `JwtAuthenticationToken`/principal is never taken from unverified sources.
- [ ] `sub` is not assumed to be a local UUID/role/tenant; identity must be mapped and resource permissions checked.
- [ ] ID Tokens/refresh tokens are not accepted in place of access tokens.
- [ ] No custom Base64 JWT decoding used to grant permissions.
- [ ] CORS/CSRF designed around browser credential delivery and topology.
- [ ] No logging of raw tokens, secrets, or private data.

### Testing and Operations

- [ ] Public GET → 200; protected without token → 401.
- [ ] Malformed, expired, wrong signature, wrong issuer, wrong audience → 401.
- [ ] Valid signed JWT with right scope → 200.
- [ ] Valid signed JWT with wrong scope → 403.
- [ ] Non-mock tests exist for signatures, and `mockJwt()` tests clearly document their limitations.
- [ ] Separate integration tests exist for discovery/JWKS URL/key rotation beyond local RSA tests.
- [ ] HTTPS, proxy `Authorization` header forwarding, and timeout/key caching are observed.
- [ ] Alerts configured for unusual 401 spikes or JWKS fetch failures.
- [ ] Never auto-disable certificate validation or trust hosts outside the allowlist.
- [ ] Use supported Boot/Security versions for production and test upgrades.

## 18. References

- Spring Security — Reactive OAuth2 Resource Server JWT (minimal dependencies, issuer, JWKS, validators): https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- Spring Security — OAuth2 WebFlux overview (Resource Server, ReactiveJwtDecoder): https://docs.spring.io/spring-security/reference/reactive/oauth2/index.html
- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Reactive Testing OAuth2/JWT with WebTestClient: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Boot 3.3 — Resource Server and issuer/JWKS/audiences properties: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Spring Security 6.3 API — NimbusReactiveJwtDecoder: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html
- IETF RFC 7515 — JSON Web Signature (JWS): https://www.rfc-editor.org/rfc/rfc7515
- IETF RFC 7516 — JSON Web Encryption (JWE): https://www.rfc-editor.org/rfc/rfc7516
- IETF RFC 7517 — JSON Web Key (JWK): https://www.rfc-editor.org/rfc/rfc7517
- IETF RFC 7518 — JSON Web Algorithms (JWA): https://www.rfc-editor.org/rfc/rfc7518
- IETF RFC 7519 — JSON Web Token (JWT): https://www.rfc-editor.org/rfc/rfc7519
- IETF RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens: https://www.rfc-editor.org/rfc/rfc9068
- IETF RFC 9700 — OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700

**Remember:** A WebFlux Resource Server processing JWTs needs more than “reading a JWT string”: it needs both the Resource Server **and JOSE** modules, trusted public keys, signature/issuer/audience/time validators, and scope/tenant authorization. The Spring Boot starter `spring-boot-starter-oauth2-resource-server` is the cleanest way to get the right dependency graph; then configure `issuer-uri`/`jwk-set-uri`/`audiences` and `ServerHttpSecurity.oauth2ResourceServer(...).jwt(...)`. In tests, clearly distinguish **real RSA-signed JWTs** from `mockJwt()` which only checks permissions. Never place private keys in a production Resource Server and never accept ID Tokens in place of access tokens.
