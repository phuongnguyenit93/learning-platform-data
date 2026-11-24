# Converting JWTs to Authentication with Reactive Converters

## 1. Lesson Overview

In Spring Security WebFlux, a Resource Server receives requests carrying an `Authorization: Bearer <access-token>` header. When the access token is a JWT, the system must perform two distinct jobs:

1. **Verify the token**: check the JWS signature using a trusted public key, algorithm, issuer (`iss`), audience (`aud`), expiration (`exp`), not-before (`nbf`), and token profile when needed. This is the responsibility of `ReactiveJwtDecoder` and JWT validators.
2. **Convert the valid JWT into Authentication**: produce the principal name, `GrantedAuthority` instances, and `AbstractAuthenticationToken` for Spring Security. This is the responsibility of the **reactive JWT authentication converter**.

Suppose the access token was signed by a trusted issuer and carries claims:

~~~json
{
  "iss": "https://issuer.example.test/realms/lab",
  "sub": "alice-sub",
  "aud": ["report-api"],
  "scope": "report.read profile",
  "app_roles": ["AUDITOR"],
  "preferred_username": "alice"
}
~~~

Goals:
- `Authentication.getName()` is `alice-sub`, independent of mutable usernames or emails.
- Scope `report.read` becomes authority `SCOPE_report.read`.
- Role `AUDITOR` from a verified claim, when permitted by policy, becomes `ROLE_AUDITOR`.
- Role `ADMIN` does **not automatically** become `ROLE_ADMIN` if the Resource Server does not allow that mapping.
- `GET /api/reports` requires `SCOPE_report.read`; `GET /api/audit` requires `ROLE_AUDITOR`.
- A JWT with general permissions is still subject to ownership/tenant checks when accessing a specific resource.

**Key point:** The reactive converter must run after the decoder; it is not a way to bypass JWT verification and cannot turn client-asserted claims into trusted privileges.

### Learning Outcomes

After this lesson you can:
1. Explain `JwtReactiveAuthenticationManager`, `ReactiveJwtDecoder`, `JwtAuthenticationToken`, and `ReactiveSecurityContextHolder`.
2. Use `ReactiveJwtAuthenticationConverter` and configure `jwtAuthenticationConverter(...)` in `ServerHttpSecurity`.
3. Distinguish synchronous `JwtAuthenticationConverter` from `ReactiveJwtAuthenticationConverterAdapter`.
4. Understand the `Converter<Jwt, Mono<AbstractAuthenticationToken>>` and `Converter<Jwt, Flux<GrantedAuthority>>` signatures.
5. Safely combine default scopes with custom role claims without dropping existing authorities.
6. Build nonblocking converters capable of composing with R2DBC/WebClient for internal permission lookups.
7. Separate authentication, HTTP authorization, and object/tenant authorization.
8. Write a Java 17+ Spring Boot WebFlux project with complete code and Gradle setup.
9. Write `StepVerifier` unit tests for converters and `WebTestClient` integration tests with real RSA-signed JWTs.
10. Distinguish `mockJwt()` tests that only simulate Authentication from tests that genuinely run the decoder and converter.

## 2. How Does a JWT Flow Through the Reactive Security Layers?

~~~text
Client
  │ GET /api/reports
  │ Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
  ▼
Spring Security WebFilterChain
  │
  ├─ Extract Bearer access token
  ▼
JwtReactiveAuthenticationManager
  │
  ├─ ReactiveJwtDecoder.decode(rawToken)
  │    ├─ Parse JWT/JWS
  │    ├─ Verify signature via trusted public key/JWKS
  │    ├─ Validate exp/nbf/iss/aud, algorithm
  │    └─ Mono<Jwt> trusted by the API
  ▼
Converter<Jwt, Mono<AbstractAuthenticationToken>>
  │
  ├─ Use sub as principal name
  ├─ Scope → SCOPE_report.read
  ├─ Allowlisted app_roles → ROLE_AUDITOR
  └─ Optional: reactive DB entitlement lookup
  ▼
JwtAuthenticationToken
  │
  ▼
SecurityContext inside Reactor Context
  │
  ▼
authorizeExchange / ReactiveAuthorizationManager
  │
  ├─ Invalid/missing JWT          → 401
  ├─ Valid JWT lacking permission → 403
  └─ Matching JWT and permission  → controller/service
~~~

Important conditions:
- The converter receives a **`Jwt` from the decoder** in the default pipeline, not a raw token to Base64-decode itself.
- `JwtReactiveAuthenticationManager` operates on `Mono`; the converter must never call `subscribe()` or `block()`.
- `JwtAuthenticationToken` normally holds a `Jwt` principal and uses the `sub` claim as the principal name.
- `ReactiveSecurityContextHolder` stores/reads context via Reactor rather than relying on Servlet ThreadLocal.
- `GrantedAuthority` instances are mapped permission strings. They do not replace access checks for specific resource IDs or tenants.

### 2.1. Boundary Between Verification and Mapping

| Step | Responsibility | Component |
| --- | --- | --- |
| Verify JWS | Valid signature, trusted key/alg | `NimbusReactiveJwtDecoder` |
| Validate claims | Issuer, audience, time, token purpose | `OAuth2TokenValidator<Jwt>` |
| Map Authentication | Subject name, scopes, roles, authorities | `ReactiveJwtAuthenticationConverter` |
| HTTP authorization | Which authority does the route require? | `authorizeExchange` |
| Object authorization | May the user act on this specific resource? | Service/DB/ACL |
| Audit | Sanitized actor ID, decision, and trace ID | Audit logging |

Common mistake:

~~~java
// ANTI-PATTERN: readable JWT payload does not mean trustworthy.
String payloadBase64 = bearerToken.split("\\.")[1];
// Decoding and reading app_roles to grant ROLE_ADMIN
// WITHOUT verifying signature, iss, aud, and exp is wrong.
~~~

Base64URL-encoded JWT payloads are **not confidentially encrypted**. Attackers can craft arbitrary claims. Every role must originate from a decoder-verified token and an issuer authorized to assert that role.

## 3. What Authentication Does Spring Security Create by Default?

Common WebFlux configuration:

~~~java
return http
    .authorizeExchange(exchanges -> exchanges
        .anyExchange().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults()))
    .build();
~~~

In a standard JWT Resource Server setup:
- `JwtAuthenticationToken` represents successful Authentication.
- `getPrincipal()` is the `Jwt` object.
- `getName()` defaults to the `sub` claim.
- `getAuthorities()` holds scopes from `scope` or `scp`, prefixed with `SCOPE_`.

Example token containing:

~~~json
{"sub":"user-42","scope":"report.read report.write"}
~~~

Typical result:

~~~text
Authentication: JwtAuthenticationToken
principal: Jwt (verified)
name: user-42
authorities:
  SCOPE_report.read
  SCOPE_report.write
~~~

A valid rule:

~~~java
.pathMatchers(HttpMethod.GET, "/api/reports")
    .hasAuthority("SCOPE_report.read")
~~~

An easily confused rule:

~~~java
.hasRole("report.read")
~~~

`hasRole("report.read")` normally looks for `ROLE_report.read`, which **differs** from `SCOPE_report.read`. When converting scopes to authorities, keep prefixes, matchers, and authority names consistent.

**Never** treat `Authentication.isAuthenticated()` as “permitted to read every document”. It only confirms authentication succeeded; route and object permissions are checked separately.

## 4. Converter APIs in WebFlux

### 4.1. ReactiveJwtAuthenticationConverter Directly

Spring Security 6.3.x provides:

~~~java
ReactiveJwtAuthenticationConverter reactive =
    new ReactiveJwtAuthenticationConverter();
~~~

It implements:

~~~java
Converter<Jwt, Mono<AbstractAuthenticationToken>>
~~~

There are two main configuration points:
- `setPrincipalClaimName(String)`: claim used as `Authentication.getName()`, defaulting to `sub`.
- `setJwtGrantedAuthoritiesConverter(Converter<Jwt, Flux<GrantedAuthority>>)`: extracts authorities as a reactive publisher.

Example custom `permissions` claim containing valid permissions:

~~~java
JwtGrantedAuthoritiesConverter permissions =
    new JwtGrantedAuthoritiesConverter();
permissions.setAuthoritiesClaimName("permissions");
permissions.setAuthorityPrefix("PERM_");

ReactiveJwtAuthenticationConverter converter =
    new ReactiveJwtAuthenticationConverter();

converter.setJwtGrantedAuthoritiesConverter(jwt ->
    Flux.fromIterable(permissions.convert(jwt)));
~~~

This snippet is **not standalone**; it needs imports and security config. Note that replacing the authorities converter like this can drop default scopes unless you merge the streams.

### 4.2. ReactiveJwtAuthenticationConverterAdapter for Synchronous Mappers

When a project already has a synchronous `JwtAuthenticationConverter`:

~~~java
JwtAuthenticationConverter sync =
    new JwtAuthenticationConverter();

JwtGrantedAuthoritiesConverter permissionMapper =
    new JwtGrantedAuthoritiesConverter();
permissionMapper.setAuthoritiesClaimName("permissions");
permissionMapper.setAuthorityPrefix("PERM_");

sync.setJwtGrantedAuthoritiesConverter(permissionMapper);
sync.setPrincipalClaimName("sub");

Converter<Jwt, Mono<AbstractAuthenticationToken>> adapted =
    new ReactiveJwtAuthenticationConverterAdapter(sync);
~~~

Used in WebFlux:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt.jwtAuthenticationConverter(adapted)))
~~~

The adapter converts a **non-blocking synchronous converter interface** to the reactive interface. It **does not turn JDBC, blocking HTTP, or `Thread.sleep` into nonblocking I/O**. If an old converter made synchronous database calls, redesign or explicitly isolate blocking I/O with care rather than assuming the adapter handles it automatically.

### 4.3. Completely Custom Converter

You can write your own:

~~~java
Converter<Jwt, Mono<AbstractAuthenticationToken>> custom =
    jwt -> Mono.just(jwt)
        .map(value -> new JwtAuthenticationToken(
            value,
            List.of(new SimpleGrantedAuthority("SCOPE_demo.read")),
            value.getSubject()));
~~~

**This only illustrates the type signature**; granting a fixed scope to every valid JWT is unsuitable for most systems. Production must properly map scopes/roles and internal privileges.

A custom converter must:
- Return `Mono<AbstractAuthenticationToken>`, not the token directly.
- Never call `subscribe()`.
- Never call `block()` on the event loop.
- Never skip issuer/audience/signature validation, which is the decoder's responsibility.
- Never default to granting `ROLE_ADMIN` on lookup errors or invalid claims.
- If changing `Authentication.getPrincipal()` to a custom local user, update controllers using `@AuthenticationPrincipal Jwt`.

## 5. Mapping Scopes and Roles Safely

Suppose a validated JWT contains:

~~~json
{
  "scope":"report.read profile",
  "app_roles":["AUDITOR","REVIEWER"]
}
~~~

The demo will produce:

~~~text
SCOPE_report.read
SCOPE_profile
ROLE_AUDITOR
ROLE_REVIEWER
~~~

We do not blindly map every string into an authority:

| Claim | Policy | Authority |
| --- | --- | --- |
| `scope="report.read"` | Standard mapping | `SCOPE_report.read` |
| `scope="profile"` | Standard mapping | `SCOPE_profile` |
| `app_roles=["AUDITOR"]` | Allowlist | `ROLE_AUDITOR` |
| `app_roles=["REVIEWER"]` | Allowlist | `ROLE_REVIEWER` |
| `app_roles=["ADMIN"]` | Absent from sample allowlist | No role granted |
| `app_roles=["ROLE_AUDITOR"]` | Not an accepted raw value | No role granted |
| `email="admin@example.org"` | Profile data | Grants no permissions |
| `tenant_id="tenant-a"` | Validated tenant context | Grants no access to tenant-b |

### 5.1. Why Preserve Scopes When Adding Roles?

A custom authorities converter that returns only roles can accidentally drop `SCOPE_report.read` from the JWT. Scope-protected endpoints would then switch from 200 to 403 even though the token carries `scope=report.read`.

If the application needs both, combine the default `JwtGrantedAuthoritiesConverter` output with mapped roles and deduplicate. The full implementation in Section 6 uses `Flux.concat(...).distinct(...)`.

### 5.2. A Role Is Not an All-Powerful Claim

A trusted issuer may sign a token containing roles, yet the Resource Server still must decide:
- Is this issuer permitted to **assert** the AUDITOR role?
- Does the role apply app-wide or to a specific tenant/organization?
- Is the claim format a list or a string?
- Could the role have been revoked after the JWT was issued?
- Is the internal role combined with token scopes as an **intersection** rather than overriding all scope checks?

For a write operation:

~~~text
ALLOW_WRITE =
    Valid JWT for the right API
AND SCOPE_report.write
AND local user ACTIVE
AND valid tenant membership
AND owner/editor permission on the target report
~~~

Having `ROLE_AUDITOR` alone does not permit editing every document, especially when data belongs to another tenant.

### 5.3. Claim Type Mismatches and Fail-Closed Policy

The `app_roles` claim may be missing or have the wrong type:
- Missing role: grant no role from this source.
- List containing non-string elements: do not coerce to authorities.
- String claim instead of list when the contract requires a list: grant no permissions; if format is mandatory, add a validator to reject the token early.
- Unknown role: never grant a role higher than default.
- User missing from local DB: depending on policy, deny rather than auto-creating an admin.
- DB unavailable: fail closed; never use `onErrorReturn(ROLE_ADMIN)`.

A valid JWT signature does not mean every claim inside it carries permission meaning in every resource server.

## 6. Java 17+ Spring Boot WebFlux Project

The sample project uses Spring Boot **3.3.13**, Gradle 8.x, and Java 17+ for consistency with Spring Security 6.3. Versions are pinned for learning purposes; production environments should use supported Spring Boot/Security lines and test upgrades.

APIs:
- `GET /health`: public.
- `GET /api/me`: valid JWT authentication; returns demo principal name and authorities.
- `GET /api/reports`: requires `SCOPE_report.read`.
- `GET /api/audit`: requires `ROLE_AUDITOR`.
- `GET /api/admin`: requires `ROLE_ADMIN`; the mapper intentionally rejects ADMIN.
- `anyExchange().denyAll()`: denies unconfigured routes.

### 6.1. Structure

~~~text
webflux-jwt-reactive-auth/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── JwtReactiveApp.java
    │   │   ├── SecurityConfig.java
    │   │   └── ReportController.java
    │   └── resources/application.yml
    └── test/java/demo/
        └── JwtConverterTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-jwt-reactive-auth'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The Resource Server starter pulls in `spring-security-oauth2-resource-server` and `spring-security-oauth2-jose` needed for JWTs. Do not add Servlet `spring-boot-starter-web` if the target is reactive WebFlux.

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/realms/lab
          jwk-set-uri: https://issuer.example.test/realms/lab/jwks
          audiences:
            - report-api
~~~

These are illustrative endpoints with no real IdP. When running against a production issuer, replace with a trusted issuer and HTTPS JWKS URL:
- `issuer-uri` validates `iss`.
- `jwk-set-uri` specifies the approved public keys source.
- `audiences` requires tokens intended for `report-api`.
- The decoder may need network access for JWKS/key rotation; offline tests use a dedicated test decoder.
- Never allow JWT headers `jku` or `x5u` to point to arbitrary URLs for fetching public keys.
- Production Resource Servers **do not need a private signing key**.

### 6.2. Main Class

`src/main/java/demo/JwtReactiveApp.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JwtReactiveApp {
    public static void main(String[] args) {
        SpringApplication.run(JwtReactiveApp.class, args);
    }
}
~~~

### 6.3. SecurityConfig: Scope + Custom Role Converter

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import java.util.List;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverter;
import org.springframework.security.web.server.SecurityWebFilterChain;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    private static final Set<String> ALLOWED_ROLES =
        Set.of("AUDITOR", "REVIEWER");

    @Bean
    Converter<Jwt, Mono<AbstractAuthenticationToken>>
    jwtAuthenticationConverter() {

        JwtGrantedAuthoritiesConverter scopeMapper =
            new JwtGrantedAuthoritiesConverter();

        ReactiveJwtAuthenticationConverter reactive =
            new ReactiveJwtAuthenticationConverter();

        reactive.setJwtGrantedAuthoritiesConverter(jwt -> {
            Flux<GrantedAuthority> scopes =
                Flux.fromIterable(scopeMapper.convert(jwt));

            Object rawRoles = jwt.getClaims().get("app_roles");

            Flux<GrantedAuthority> roles =
                rawRoles instanceof List<?> values
                    ? Flux.fromIterable(values)
                        .ofType(String.class)
                        .filter(ALLOWED_ROLES::contains)
                        .map(role -> (GrantedAuthority)
                            new SimpleGrantedAuthority("ROLE_" + role))
                    : Flux.empty();

            return Flux.concat(scopes, roles)
                .distinct(GrantedAuthority::getAuthority);
        });

        reactive.setPrincipalClaimName("sub");
        return reactive;
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            Converter<Jwt, Mono<AbstractAuthenticationToken>>
                jwtAuthenticationConverter) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .pathMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_report.read")
                .pathMatchers(HttpMethod.GET, "/api/audit")
                    .hasAuthority("ROLE_AUDITOR")
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasAuthority("ROLE_ADMIN")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtAuthenticationConverter(
                    jwtAuthenticationConverter)))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .build();
    }
}
~~~

**Configuration breakdown:**
1. `ReactiveJwtAuthenticationConverter` returns a publisher of the right type `Mono<AbstractAuthenticationToken>`.
2. `JwtGrantedAuthoritiesConverter` preserves default `SCOPE_*` scopes.
3. `app_roles` is read only when it is a `List<?>`. Non-string items are filtered out; production contracts should add a validator if wrong types must reject the token.
4. `ALLOWED_ROLES` blocks `ADMIN` and pre-prefixed strings like `ROLE_AUDITOR`; only raw values AUDITOR/REVIEWER become authorities.
5. `Flux.concat(...).distinct(...)` merges scopes and roles without duplicates.
6. `setPrincipalClaimName("sub")` keeps a relatively stable identifier within the issuer namespace.
7. `jwtAuthenticationConverter(...)` must be registered on the WebFlux chain's JWT DSL.
8. `httpBasic` and `formLogin` are disabled since the demo is Bearer-only. Never use username/password/cookies to spoof JWTs.
9. The demo only has GET routes so CSRF need not be disabled; when adding unsafe methods, evaluate CSRF against ambient browser credentials.
10. No token is mapped to the `ROLE_ADMIN` route through the custom role allowlist in this lesson. In production, admin privileges require a governed role model.
11. Never call `block()` or manual `subscribe()` inside security config.
12. Multi-tenant/object authorization is not solved by roles alone.

### 6.4. Controller Reading SecurityContext Properly

`src/main/java/demo/ReportController.java`:

~~~java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
class ReportController {

    public record IdentityView(
        String name, String subject, List<String> authorities) {}

    @GetMapping("/health")
    Mono<String> health() {
        return Mono.just("ok");
    }

    @GetMapping("/api/me")
    Mono<IdentityView> me(@AuthenticationPrincipal Jwt jwt) {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> new IdentityView(
                context.getAuthentication().getName(),
                jwt.getSubject(),
                context.getAuthentication().getAuthorities()
                    .stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList()
            ));
    }

    @GetMapping("/api/reports")
    Mono<Map<String, String>> reports() {
        return Mono.just(Map.of("result", "report.read allowed"));
    }

    @GetMapping("/api/audit")
    Mono<Map<String, String>> audit() {
        return Mono.just(Map.of("result", "ROLE_AUDITOR allowed"));
    }

    @GetMapping("/api/admin")
    Mono<Map<String, String>> admin() {
        return Mono.just(Map.of("result", "ROLE_ADMIN allowed"));
    }
}
~~~

Because Authentication remains `JwtAuthenticationToken`, `@AuthenticationPrincipal Jwt` can be injected by Spring Security WebFlux. `ReactiveSecurityContextHolder` reads Authentication via the Reactor Context rather than Servlet ThreadLocal.

**`/api/me` is strictly for learning**; never publicly dump tokens, raw `Authorization`, private keys, or sensitive full claims. In real products, permissions may be sensitive and should not be returned verbatim when unnecessary.

## 7. Test Suite: StepVerifier + Real RSA-Signed JWTs + WebTestClient

There are three testing levels:

1. **Direct converter unit test**: build a `Jwt` fixture and use `StepVerifier` to check `Mono<AbstractAuthenticationToken>`, principal name, and authorities. This tests conversion, **not** signatures.
2. **Signed JWT integration tests**: generate RSA-signed JWS JWTs with a test-only private key; the `NimbusReactiveJwtDecoder` trusts only the matching public RSA key and validates issuer, audience, and timestamps; `WebTestClient` exercises real filters and converter.
3. **`mockJwt()` security test**: supplies fake Authentication/authorities for authorization tests. It can bypass decoder/converter; this test explicitly documents that limitation.

### 7.1. Full Test File

`src/test/java/demo/JwtConverterTests.java`:

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
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
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
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
@Import(JwtConverterTests.OfflineKeys.class)
class JwtConverterTests {

    private static final String ISSUER =
        "https://issuer.example.test/realms/lab";

    @Autowired
    ApplicationContext context;

    @Autowired
    JwtEncoder jwtEncoder;

    @Autowired
    Converter<Jwt, Mono<AbstractAuthenticationToken>> mapping;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class OfflineKeys {

        @Bean
        KeyPair keyPair() {
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
        JwtEncoder jwtEncoder(KeyPair keys) {
            RSAKey jwk = new RSAKey.Builder(
                (RSAPublicKey) keys.getPublic())
                .privateKey((RSAPrivateKey) keys.getPrivate())
                .keyID("test-key")
                .build();

            return new NimbusJwtEncoder(
                new ImmutableJWKSet<SecurityContext>(
                    new JWKSet(jwk)));
        }

        @Bean
        ReactiveJwtDecoder jwtDecoder(KeyPair keys) {
            NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder.withPublicKey(
                    (RSAPublicKey) keys.getPublic())
                    .build();

            OAuth2TokenValidator<Jwt> audience =
                jwt -> jwt.getAudience() != null
                    && jwt.getAudience().contains("report-api")
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error(
                                "invalid_token",
                                "Missing report-api audience",
                                null));

            decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                    JwtValidators.createDefaultWithIssuer(
                        "https://issuer.example.test/realms/lab"),
                    audience));

            return decoder;
        }
    }

    private String signed(
            JwtEncoder signer,
            String issuer,
            String audience,
            String scope,
            List<String> roles,
            String username,
            Instant expiry) {

        Instant now = Instant.now();

        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject("alice-sub")
            .audience(List.of(audience))
            .issuedAt(now.minusSeconds(10))
            .notBefore(now.minusSeconds(10))
            .expiresAt(expiry)
            .claim("scope", scope)
            .claim("app_roles", roles)
            .claim("preferred_username", username)
            .build();

        JwsHeader header = JwsHeader
            .with(SignatureAlgorithm.RS256)
            .keyId("test-key")
            .build();

        return signer.encode(
            JwtEncoderParameters.from(header, claims))
            .getTokenValue();
    }

    private String valid(String scope, List<String> roles) {
        return signed(
            jwtEncoder, ISSUER, "report-api",
            scope, roles, "display-alice",
            Instant.now().plusSeconds(600));
    }

    @Test
    void directReactiveConverterMapsScopeAndRole() {
        // Unit test: Jwt fixture without signature verification.
        Jwt jwt = Jwt.withTokenValue("test-only")
            .header("alg", "RS256")
            .claim("sub", "alice-sub")
            .claim("scope", "report.read")
            .claim("app_roles", List.of("AUDITOR"))
            .build();

        StepVerifier.create(mapping.convert(jwt))
            .assertNext(authentication -> {
                assertThat(authentication)
                    .isInstanceOf(JwtAuthenticationToken.class);
                assertThat(authentication.getName())
                    .isEqualTo("alice-sub");
                assertThat(authentication.getAuthorities())
                    .extracting(GrantedAuthority::getAuthority)
                    .contains("SCOPE_report.read", "ROLE_AUDITOR");
            })
            .verifyComplete();
    }

    @Test
    void healthIsPublic() {
        client.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void protectedEndpointWithoutJwtIs401() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void malformedJwtIs401() {
        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth("not-a-jwt"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void signedJwtCreatesAuthenticationWithSubName() {
        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth(
                valid("report.read", List.of("AUDITOR"))))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.name").isEqualTo("alice-sub")
            .jsonPath("$.subject").isEqualTo("alice-sub")
            .jsonPath("$.authorities").isArray();
    }

    @Test
    void preferredUsernameDoesNotOverridePrincipalName() {
        String token = signed(
            jwtEncoder, ISSUER, "report-api", "profile",
            List.of(), "pretend-admin",
            Instant.now().plusSeconds(600));

        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth(token))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.name").isEqualTo("alice-sub");
    }

    @Test
    void reportReadScopeAllowsReading() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth(
                valid("report.read profile", List.of())))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.result")
                .isEqualTo("report.read allowed");
    }

    @Test
    void missingReportReadScopeIs403() {
        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth(
                valid("profile", List.of("AUDITOR"))))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void auditorRoleAllowsAudit() {
        client.get().uri("/api/audit")
            .headers(h -> h.setBearerAuth(
                valid("profile", List.of("AUDITOR"))))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.result")
                .isEqualTo("ROLE_AUDITOR allowed");
    }

    @Test
    void reviewerDoesNotHaveAuditorRole() {
        client.get().uri("/api/audit")
            .headers(h -> h.setBearerAuth(
                valid("report.read", List.of("REVIEWER"))))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void unapprovedAdminDoesNotGetRoleAdmin() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBearerAuth(
                valid("report.read", List.of("ADMIN"))))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void rolePrefixStringCannotBypassAllowlist() {
        client.get().uri("/api/audit")
            .headers(h -> h.setBearerAuth(
                valid("profile", List.of("ROLE_AUDITOR"))))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void wrongIssuerIs401() {
        String token = signed(
            jwtEncoder, "https://evil.example", "report-api",
            "report.read", List.of("AUDITOR"), "alice",
            Instant.now().plusSeconds(600));

        client.get().uri("/api/audit")
            .headers(h -> h.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongAudienceIs401() {
        String token = signed(
            jwtEncoder, ISSUER, "other-api",
            "report.read", List.of("AUDITOR"), "alice",
            Instant.now().plusSeconds(600));

        client.get().uri("/api/audit")
            .headers(h -> h.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void expiredTokenIs401() {
        String token = signed(
            jwtEncoder, ISSUER, "report-api",
            "report.read", List.of("AUDITOR"), "alice",
            Instant.now().minusSeconds(600));

        client.get().uri("/api/reports")
            .headers(h -> h.setBearerAuth(token))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongRsaSigningKeyIs401() {
        KeyPair other;
        try {
            KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            other = generator.generateKeyPair();
        }
        catch (GeneralSecurityException error) {
            throw new IllegalStateException(error);
        }

        RSAKey jwk = new RSAKey.Builder(
            (RSAPublicKey) other.getPublic())
            .privateKey((RSAPrivateKey) other.getPrivate())
            .keyID("test-key")
            .build();

        JwtEncoder wrongEncoder = new NimbusJwtEncoder(
            new ImmutableJWKSet<SecurityContext>(
                new JWKSet(jwk)));

        String forged = signed(
            wrongEncoder, ISSUER, "report-api",
            "report.read", List.of("AUDITOR"), "alice",
            Instant.now().plusSeconds(600));

        client.get().uri("/api/audit")
            .headers(h -> h.setBearerAuth(forged))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void mockJwtSkipsRealDecoderAndCustomRoleMapping() {
        // mockJwt contains app_roles claim but does not run the
        // resource server's real JWT authentication converter.
        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.claim(
                    "app_roles", List.of("AUDITOR"))))
            .get().uri("/api/audit")
            .exchange()
            .expectStatus().isForbidden();

        // Mock is given the authority directly to test the route rule.
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("ROLE_AUDITOR")))
            .get().uri("/api/audit")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

### 7.2. Test Suite and Expected Outcomes

| Test | Expected |
| --- | --- |
| `directReactiveConverterMapsScopeAndRole` | `StepVerifier` confirms token, `sub`, and 2 authorities |
| `healthIsPublic` | 200 |
| `protectedEndpointWithoutJwtIs401` | 401 |
| `malformedJwtIs401` | 401 |
| `signedJwtCreatesAuthenticationWithSubName` | 200, name = `sub` |
| `preferredUsernameDoesNotOverridePrincipalName` | 200, does not use username |
| `reportReadScopeAllowsReading` | 200 |
| `missingReportReadScopeIs403` | 403 |
| `auditorRoleAllowsAudit` | 200 |
| `reviewerDoesNotHaveAuditorRole` | 403 |
| `unapprovedAdminDoesNotGetRoleAdmin` | 403 |
| `rolePrefixStringCannotBypassAllowlist` | 403 |
| `wrongIssuerIs401` | 401 |
| `wrongAudienceIs401` | 401 |
| `expiredTokenIs401` | 401 |
| `wrongRsaSigningKeyIs401` | 401 |
| `mockJwtSkipsRealDecoderAndCustomRoleMapping` | 403, then 200 with mock authority |

There are **17 test methods**. Tests with real signed Bearer strings traverse the real decoder and converter; the `mockJwt()` test intentionally bypasses that path. The direct `StepVerifier` test exercises only the converter, not signatures.

### 7.3. Running

~~~bash
gradle test
~~~

If using the Gradle Wrapper: `./gradlew test` on Linux/macOS, or `gradlew.bat test` on Windows. No actual build output is claimed in this lesson; run in a compatible Java/Gradle environment to confirm the tests pass. Tests use a test-only keypair in the JVM, needing no external IdP/JWKS once dependencies are downloaded.

To run the API against a real IdP:
1. Replace `issuer-uri`/`jwk-set-uri`/`audiences` with approved values.
2. Verify HTTPS/JWKS/issuer metadata and trusted certificates.
3. Run `gradle bootRun`.
4. Call the public endpoint:

~~~bash
curl -i http://localhost:8080/health
~~~

5. Calling a protected endpoint without a token normally returns 401:

~~~bash
curl -i http://localhost:8080/api/reports
~~~

6. Call with a real access token issued by the issuer for `report-api` with scope `report.read`:

~~~bash
curl -i \
  -H "Authorization: Bearer ACCESS_TOKEN_FROM_TRUSTED_AS" \
  http://localhost:8080/api/reports
~~~

`ACCESS_TOKEN_FROM_TRUSTED_AS` is only a placeholder. Test tokens signed with the internal keypair are not production tokens. Never write raw access tokens into logs or screenshots, and use HTTPS outside local environments.

## 8. When Database Lookups Are Needed in the Converter

If permissions do not live entirely inside the JWT or require rapid revocation, you can look up local user/tenant membership by verified `(iss,sub)` using R2DBC, or call a reactive entitlement service.

**The following is an architectural snippet**, not part of the runnable project because service implementation depends on your specific DB and business logic.

~~~java
interface ReactiveMembershipService {
    Mono<List<GrantedAuthority>> authoritiesFor(
        String verifiedIssuer, String verifiedSubject);
}

Converter<Jwt, Mono<AbstractAuthenticationToken>>
    lookupConverter(ReactiveMembershipService service) {

    return jwt -> service.authoritiesFor(
            jwt.getIssuer().toString(),
            jwt.getSubject())
        .switchIfEmpty(Mono.error(
            new BadCredentialsException(
                "Local identity not available")))
        .map(authorities -> new JwtAuthenticationToken(
            jwt, authorities, jwt.getSubject()));
}
~~~

Guidelines:
1. Invoke only with a decoder-validated `Jwt`; never trust `iss/sub` from a manually parsed token.
2. Use the `(issuer, subject)` pair, not email lookups.
3. Disabled accounts must not receive privileges just because the JWT has not expired.
4. DB errors must **fail closed**, never automatically granting privileges.
5. Do not `block()` or `subscribe()`; return the publisher to the security pipeline.
6. Per-request lookups increase latency and DB dependency; consider short-lived caching and revocation invalidation.
7. If the JWT scope only grants read access, do not let a DB editor role grant write permissions beyond the scope. Combine scopes **and** local permissions.
8. Check object/tenant permissions in the service/repository when `resourceId` is needed, rather than cramming every object ID into Authentication.
9. Custom converter exceptions need explicit error handling; never assume every error always returns 401 or 403.

### 8.1. Blocking I/O Anti-Pattern

Wrong:

~~~java
// ANTI-PATTERN: blocking DB call right when creating Mono.
return jwt -> Mono.just(
    jdbcRepository.findRoles(jwt.getSubject())
).map(roles -> new JwtAuthenticationToken(jwt, roles));
~~~

`findRoles` executes before `Mono` creation and can block the event loop. For legacy JDBC that cannot yet be replaced with R2DBC, isolate explicitly on `boundedElastic` with controlled capacity/timeouts; do not mistake it for real nonblocking I/O. The long-term solution is a reactive service/repository.

Wrong:

~~~java
// ANTI-PATTERN: subscribe detaches work from the request lifecycle.
service.authoritiesFor(issuer, subject)
    .subscribe(roles -> cache.put(subject, roles));

return Mono.just(new JwtAuthenticationToken(jwt));
~~~

The framework must own subscription; the converter's returned publisher should complete only once the required authentication steps have finished.

### 8.2. Disabled Accounts and DB Errors

If a local user is locked after a token is issued, the JWT may remain cryptographically valid. A claims-only converter cannot know that. You need:
- Short token TTLs / revocation strategy.
- Backend user status/entitlement checks for sensitive operations.
- Controlled caching and invalidation.
- Fail-closed behavior on DB outages, distinguishing infrastructure errors from permission denials in logs/metrics.
- Tests for races when roles are revoked, accounts disabled, or tenants split.

## 9. Principal Name and Stable Identity

`Authentication.getName()` defaults to `sub` and can be changed:

~~~java
ReactiveJwtAuthenticationConverter converter =
    new ReactiveJwtAuthenticationConverter();
converter.setPrincipalClaimName("preferred_username");
~~~

However, `preferred_username`, email, or name can change; never use them as long-term ownership IDs. `sub` is also only unique within an issuer namespace. For example:

~~~text
(iss=https://issuer-a.example, sub=123) → User A
(iss=https://issuer-b.example, sub=123) → User B
~~~

Never merge those two users just because `sub` matches. Systems with local users should store a `(verified iss, sub) → local UUID` mapping. Business tables should use local UUIDs for ownership/foreign keys; scopes and roles do not replace data authorization.

In multi-issuer setups, never create arbitrary decoders from an attacker-supplied issuer in the JWT. Use a trusted issuer allowlist with matching public keys/algorithms/audience config before converting authorities.

## 10. Controlling Roles, Scopes, and Tenants

A token having:
- `scope=report.read`, without write.
- `app_roles=["AUDITOR"]`.
- `tenant_id=tenant-a`.

does not mean the user:
- Can write reports just because of the AUDITOR role.
- Can read tenant-b data.
- Can self-grant admin privileges.
- Can access a report owned by another user.

A safe update policy might be:

~~~text
ALLOW_UPDATE =
    Valid JWT + right audience
AND SCOPE_report.write
AND local user ACTIVE
AND tenant membership ACTIVE
AND service verifies editor/owner on the specific report
~~~

Role claims can become stale. If privileges must be revoked immediately, trusting JWT roles with an appropriate TTL alone is insufficient; re-check a permission server/DB or use a revocation design.

## 11. Distinguishing Errors in the Security Pipeline

| Result | Typical cause | Where to check |
| --- | --- | --- |
| **401** | Missing Bearer on protected route | Authentication entry point |
| **401** | Malformed JWT, wrong signature | `ReactiveJwtDecoder` |
| **401** | Issuer/audience/time failed | JWT validators |
| **403** | Valid JWT missing `SCOPE_report.read` | `authorizeExchange` |
| **403** | Valid JWT missing `ROLE_AUDITOR` | Role mapping/authorization |
| **403/404** | Different tenant/owner, per policy | Resource authorization |
| **5xx or handler-defined status** | Custom converter/entitlement service error | Exception handling, DB/network |
| **200** | Valid JWT, converter produced required authority | Controller executes |

Do not equate every 403 with CSRF: it could be authorities, tenant, CORS, or another policy.

### 11.1. Debugging Missing Roles

1. Confirm a real access token was signed by the issuer, has the right audience, and is unexpired.
2. Confirm the JWT entered the right `SecurityWebFilterChain` and the converter is registered via `jwtAuthenticationConverter(...)`.
3. Check the claim name: `app_roles` vs `roles`, `realm_access.roles`?
4. Check the claim type: String, List, nested object?
5. Check whether the role is in the allowlist.
6. Check prefixes `ROLE_`/`SCOPE_`/`PERM_`.
7. Check whether the route uses `hasRole` or `hasAuthority`.
8. Check object-level/tenant rules.
9. Avoid testing only with `mockJwt()`; run real signed Bearer JWT tests.
10. Never log raw tokens, unnecessary access token scopes/PII, or private keys.

## 12. Comparing Converters

| Approach | Best suited for | Limitations |
| --- | --- | --- |
| `JwtAuthenticationConverter` + `ReactiveJwtAuthenticationConverterAdapter` | Existing synchronous in-memory claim mapper | Adapter does not fix blocking JDBC |
| `ReactiveJwtAuthenticationConverter` | Mapping scopes/roles with Flux and setting principal claim | Still needs independent decoder/authorization |
| Custom `Converter<Jwt, Mono<AbstractAuthenticationToken>>` | Local principal / DB entitlements / reactive WebClient | More complex, easier to fail-open or add latency |

Pick the **simplest approach that still satisfies policy**. Do not write a new converter if default scope mapping already suffices.

## 13. Common Pitfalls and How to Fix Them

| Pitfall | Why it is wrong | Fix |
| --- | --- | --- |
| Manually Base64URL-decoding JWT to grant roles | Does not verify signature | Use `ReactiveJwtDecoder` |
| Forgetting `aud` in custom decoder | Accepts tokens meant for other APIs | Add audience validator |
| Dropping scopes when adding custom roles | `SCOPE_*` disappears | Merge default scopes and roles |
| Confusing `ROLE_` with `SCOPE_` | Unexpected 403 on routes | Align authority prefixes |
| Unknown role automatically becomes ADMIN | Privilege escalation | Role allowlist / issuer trust |
| Mapper accepts `ROLE_ADMIN` from claim string | Prefix injection | Stick to exact contract; reject pre-prefixed input |
| Using email as principal/owner | Mutable / reusable | Verified `(iss,sub)` → local UUID |
| Blocking JDBC inside adapter | Blocks event loop | R2DBC/WebClient or explicit isolation |
| Calling `subscribe()` manually | Race / broken lifecycle | Compose `Mono/Flux` |
| `onErrorReturn(ROLE_ADMIN)` | Fails open on DB errors | Fail closed |
| Using only `mockJwt()` | Bypasses real decoder/converter | Signed JWT integration tests |
| Tenant access based solely on role | IDOR/BOLA | Resource-level owner/tenant checks |
| Stale JWT roles still accepted after revocation | Stale authorities | TTL / revocation / re-checks |
| Using Servlet `HttpSecurity` | Wrong stack for WebFlux | `ServerHttpSecurity` |
| Logging full JWTs to debug | Exposes credentials/claims | Filtered structured logs |

## 14. Exercises and Answers

**Q1.** A JWT has `scope=report.read report.export`. What does the default converter produce?

**Answer:** `SCOPE_report.read` and `SCOPE_report.export`, provided the JWT passed validation and default mapping is preserved.

**Q2.** Why doesn't `hasRole("report.read")` match `SCOPE_report.read`?

**Answer:** `hasRole` normally expects `ROLE_report.read`, whereas scopes carry the `SCOPE_` prefix.

**Q3.** A JWT has `app_roles=["AUDITOR"]`, and a route requires `ROLE_AUDITOR`. What is needed besides the signature?

**Answer:** Valid issuer/audience/timestamps and a converter policy permitting the AUDITOR role mapping.

**Q4.** Does a JWT with `app_roles=["ADMIN"]` automatically become `ROLE_ADMIN`?

**Answer:** No; the demo allowlists only AUDITOR/REVIEWER.

**Q5.** Why does a mapper returning only roles cause scope-protected endpoints to return 403?

**Answer:** Default scope authorities are lost. Merge scopes and roles properly.

**Q6.** If a JWT has a valid signature but wrong audience, should the converter run?

**Answer:** No; the decoder must reject the token before the mapping step.

**Q7.** Does the adapter make blocking JDBC nonblocking?

**Answer:** No; use a reactive DB or reviewed isolation.

**Q8.** Does `mockJwt().authorities(ROLE_AUDITOR)` prove the role claim is mapped properly?

**Answer:** No. Mocks supply the authority directly and can bypass the converter.

**Q9.** When you need to unit-test the converter independently, what should you use?

**Answer:** Build a `Jwt` fixture, invoke the converter, and use `StepVerifier` to assert Authentication/authorities. This does not test signatures.

**Q10.** If JWTs have the same `sub` from two different issuers, can they be treated as the same person?

**Answer:** No; the identity key is verified `(issuer, subject)`.

**Q11.** Is returning `Mono.empty()` from a converter doing DB lookups for a missing user clear?

**Answer:** No; define and test explicit failure/denial behavior.

**Q12.** Should a DB timeout grant a default role to increase availability?

**Answer:** No if that role grants privileges beyond policy. Fail closed and handle infrastructure errors properly.

**Q13.** Does a JWT with `ROLE_AUDITOR` in tenant A automatically allow reading tenant B?

**Answer:** No; check resource membership/ownership.

**Q14.** If a JWT is valid while the account is locked in the local DB, does a claims-reading converter know automatically?

**Answer:** No; revocation/TTL or permission/account-status re-checks are required.

**Q15.** Does changing the principal claim to email change authorities?

**Answer:** No. Principal name and granted authorities are two separate configurations.

## 15. Implementation Checklist

- [ ] Resource Server uses JWTs only after signature, issuer, audience, and time validation.
- [ ] Uses OAuth2 access tokens intended for the API, never ID Tokens in their place.
- [ ] JWT converter wired properly into WebFlux `SecurityWebFilterChain`.
- [ ] Default `SCOPE_*` scopes preserved when adding roles.
- [ ] Only allowlisted role values from trusted issuers are mapped.
- [ ] No auto-granting roles from email, username, headers, or request bodies.
- [ ] Principal/owner IDs rely on verified identity and stable local mappings.
- [ ] Tenant/resource-owner constraints checked independently.
- [ ] No blocking I/O, no manual `subscribe()`, no fail-open paths.
- [ ] Cache/revocation/disabled-user policy defined when dynamic roles are needed.
- [ ] `StepVerifier` unit tests exist for the converter.
- [ ] RSA-signed Bearer JWT integration tests cover decoder+mapping.
- [ ] 401 tests cover missing/bad signature/wrong issuer/audience/expired tokens.
- [ ] 403 tests cover valid JWTs lacking scope/role/tenant permission.
- [ ] Unknown role and prefix injection tests exist.
- [ ] `mockJwt()` test limitations clearly documented.
- [ ] Never log raw tokens, secrets, or private keys.
- [ ] Re-test after Spring Security version upgrades.

## 16. References

- Spring Security — Reactive OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- Spring Security 6.3 — ReactiveJwtAuthenticationConverter: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/oauth2/server/resource/authentication/ReactiveJwtAuthenticationConverter.html
- Spring Security 6.3 — ReactiveJwtAuthenticationConverterAdapter: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/oauth2/server/resource/authentication/ReactiveJwtAuthenticationConverterAdapter.html
- Spring Security 6.3 — JwtReactiveAuthenticationManager: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/oauth2/server/resource/authentication/JwtReactiveAuthenticationManager.html
- Spring Security — JWT testing with WebTestClient: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Boot 3.3 — Resource Server Auto Configuration: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- RFC 7519 — JSON Web Token: https://www.rfc-editor.org/rfc/rfc7519
- RFC 9068 — OAuth2 JWT Access Token Profile: https://www.rfc-editor.org/rfc/rfc9068
- OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html

**Remember:** `ReactiveJwtDecoder` verifies the JWT; the **reactive JWT authentication converter** determines the principal and authorities of a valid JWT. In WebFlux, use `ReactiveJwtAuthenticationConverter` for scopes/roles, the adapter for non-blocking synchronous converters, or a custom `Converter<Jwt, Mono<AbstractAuthenticationToken>>` when reactive entitlement lookups are required. Always keep signature/issuer/audience validation and resource/tenant authorization layers distinct.
