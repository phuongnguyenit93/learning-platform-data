# ReactiveOpaqueTokenIntrospector and OAuth2AuthenticatedPrincipal — Spring Security Reactive

> **Context:** Spring WebFlux, OAuth2 Resource Server verifying opaque access tokens, Spring Security 6.x, and Java 17+. The code baseline is Spring Boot 3.3.13/Spring Security 6.3.x for learning the APIs. Do not keep old versions in production; always use a supported release with security patches.

## 1. Why Is Introspection Needed?

A client calls an API:

```http
GET /api/reports HTTP/1.1
Authorization: Bearer Sx7V-p9a8-kZ0...
Accept: application/json
```

The string `Sx7V-p9a8-kZ0...` is just a **bearer token**. If it is an **opaque access token**, the resource server cannot read a signature or claims directly to know:

- Is the token still **active**, or has it expired or been revoked?
- Which subject/client was the token issued to?
- Does the token hold the scope to read reports?
- Is the token being used for the **right resource/audience**?
- Which tenant does the user belong to, and which records may they read?

Instead of guessing, Spring Security queries a trusted source, typically the **OAuth2 Authorization Server introspection endpoint** per RFC 7662.

```text
HTTP client                  Spring WebFlux Resource Server           Authorization Server
    |                                       |                              |
    | Authorization: Bearer opaque-value    |                              |
    |-------------------------------------->|                              |
    |                               Bearer authentication                  |
    |                                       |                              |
    |                           ReactiveOpaqueTokenIntrospector          |
    |                               introspect(token)                      |
    |                                       |---- POST /introspect ------->|
    |                                       |  client id + secret/other    |
    |                                       |<--- active, scope, sub, ... -|
    |                                       |                              |
    |                           OAuth2AuthenticatedPrincipal             |
    |                                       |                              |
    |                           BearerTokenAuthentication                  |
    |                                       |                              |
    |                        authorizeExchange / method security           |
    |                                       |                              |
    |<----------------- 200 / 401 / 403 ----|                              |
```

**Principle:** a `ReactiveOpaqueTokenIntrospector` returning a principal successfully means the implementation has **verified the token**. Never write an implementation that returns `Mono.just(adminPrincipal)` for every token or when the AS times out.

## 2. Comparing Opaque Introspection with JWT Decoding

| Criterion | Opaque Resource Server | JWT Resource Server |
|---|---|---|
| Token sent by client | Usually a non-self-describing string | Signed JWT |
| Verification component | `ReactiveOpaqueTokenIntrospector` | `ReactiveJwtDecoder` |
| Task | Queries introspection endpoint or trusted token store | Verifies signature, timestamps, issuer, validators |
| Network call per request? | Typically yes, unless cached | Typically no, once JWKS is cached |
| Revocation detection | Can be fast when AS returns updated state | Requires extra measures for unexpired JWTs |
| Principal | `OAuth2AuthenticatedPrincipal` | `Jwt` |
| Authentication | `BearerTokenAuthentication` | `JwtAuthenticationToken` |
| Default authorities | Introspection scope -> `SCOPE_...` | JWT scope/scp -> `SCOPE_...` with appropriate converter |
| Cost | Latency, AS availability, introspection credentials | Signature verification, key rotation, validation |

The name "opaque-token" describes the **Resource Server's verification mechanism**, not a requirement that the bearer token be an unstructured string. If you choose to verify JWTs via introspection because revocation is needed, Spring Security can still send that JWT string to the AS and trust the **introspection response** rather than treating raw JWT claims as verified locally.

**Never send an OIDC ID Token instead of an API access token.** The ID Token is for the client to authenticate the user, whereas the resource server needs an access token with the right purpose, scopes, and audience.

## 3. RFC 7662: Sample Request and Response

The Authorization Server's introspection endpoint is typically called via POST with a form-URL-encoded body; the resource server also authenticates itself using a method allowed by the IdP, such as HTTP Basic:

```http
POST /oauth2/introspect HTTP/1.1
Host: idp.example.com
Authorization: Basic <introspection-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=Sx7V-p9a8-kZ0...
```

When a token is valid, an IdP may return:

```json
{
  "active": true,
  "scope": "messages.read reports.read",
  "sub": "user-alice-42",
  "client_id": "portal-web",
  "token_type": "Bearer",
  "exp": 1980000000,
  "iat": 1979996400,
  "aud": ["reports-api"],
  "iss": "https://idp.example.com",
  "tenant_id": "north"
}
```

When the token is inactive:

```json
{"active": false}
```

The values above are **illustrative assumptions**; not every provider returns all claims. Distinguish:

- `active` confirms the status known to the AS at introspection time. If false, **reject the token**.
- `scope` is typically space-separated scopes. The introspector may convert it into an internal list.
- `sub` identifies the subject and is not necessarily an email/username or human user (client credentials can represent a service).
- `client_id` in the response is the client issued the token; **not the same** as the client ID the Resource Server uses to authenticate to introspection.
- `aud` indicates the target of the access token. The AS returning `active=true` does not necessarily prove the token matches the current API's audience.
- `iss` is the issuer; it must match a trusted source if used for authorization decisions.
- `exp`, `nbf`, `iat` are timestamps when returned; their converted Java types may differ from raw JSON strings/numbers.
- `tenant_id`, `roles` are custom claims; trust them only when issued by the AS or a trusted entitlement backend.
- Introspection credentials must **never** be emitted in responses or forwarded to downstream APIs.

In multi-tenant products, enforce audience/issuer/tenant/record-level policies in addition to checking whether the token is active.

## 4. ReactiveOpaqueTokenIntrospector: The Core Contract

Package:

```java
org.springframework.security.oauth2.server.resource.introspection
```

Abbreviated signature:

```java
@FunctionalInterface
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
```

This is a library API; **do not recreate this interface** in your project source.

### Input and Output

`introspect(String token)` accepts a raw bearer access token and emits `Mono<OAuth2AuthenticatedPrincipal>` only after successful verification. It does not simply decode a string.

- Confirmed active token -> `Mono` emits a principal.
- Invalid/revoked/expired token -> emits an appropriate error, such as `BadOpaqueTokenException`.
- AS down / network timeout -> **fail closed**, never synthesize a principal automatically.
- Never return an "anonymous principal" from the introspector and let the chain treat it as a successful login.
- Never call `block()` inside the WebFlux security pipeline.
- If a backend token store uses synchronous JDBC/JPA, isolate blocking I/O behind a bounded scheduler/adapter; prefer a reactive backend.

### An Intentionally Unsafe Implementation

```java
// ANTI-PATTERN — NEVER USE IN PRODUCTION.
@Bean
ReactiveOpaqueTokenIntrospector acceptEverything() {
    return token -> Mono.just(
        new DefaultOAuth2AuthenticatedPrincipal(
            "admin",
            Map.of("sub", "admin"),
            List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))));
}
```

Any token—even a fabricated string sent by an attacker—becomes admin. A stub introspector **used only in a test context** can maintain an allowlist of token fixtures, but must never be packaged into a production JAR.

## 5. Choosing an Implementation by Version

Spring Security has had several implementations:

- `NimbusReactiveOpaqueTokenIntrospector` appeared in 6.x releases with constructor `(introspectionUri, clientId, clientSecret)`; in 6.5 it was marked deprecated.
- `SpringReactiveOpaqueTokenIntrospector` is used by Spring Security as the reactive implementation. It existed prior to 6.5 with corresponding constructors.
- `SpringReactiveOpaqueTokenIntrospector.withIntrospectionUri(...).clientId(...).clientSecret(...).build()` is the **builder introduced in 6.5**. **Do not copy this builder into Boot 3.3 / Spring Security 6.3** without upgrading versions.

Example for **Spring Security 6.5+**, not a runnable file for the 3.3 demo:

```java
ReactiveOpaqueTokenIntrospector introspector =
    SpringReactiveOpaqueTokenIntrospector
        .withIntrospectionUri(introspectionUri)
        .clientId(clientId)
        .clientSecret(clientSecret)
        .build();
```

In the Boot 3.3 project in Section 9, configure via **Spring Boot properties** so Boot instantiates the appropriate implementation bean rather than calling version-specific constructors/builders. When upgrading, check the exact Javadoc of your dependency rather than inferring from the "current" docs page.

## 6. What Is OAuth2AuthenticatedPrincipal?

Package:

```java
org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal
```

The principal holds the **identity and attributes accepted by the introspector**. Key methods to know:

```java
String name = principal.getName();
Map<String, Object> attributes = principal.getAttributes();
String subject = principal.getAttribute("sub");
String tenant = principal.getAttribute("tenant_id");
Collection<? extends GrantedAuthority> granted =
    principal.getAuthorities();
```

These lines are a Java snippet requiring a `principal` variable and imports.

| API | Meaning | Key Point to Remember |
|---|---|---|
| `getName()` | Principal name seen by the application | Usually defaults to `sub`; custom mappings may differ |
| `getAttributes()` | Accepted metadata/token claims | Never dump the raw Map to public JSON |
| `getAttribute("sub")` | Subject if provided by AS | May be absent or typed differently in custom providers |
| `getAttribute("scope")` | Scopes after conversion | May be `List<String>`; do not assume String |
| `getAttribute("tenant_id")` | Tenant if provided by AS | Does not mean the client may pick another tenant |
| `getAttribute("exp")` | Expiry info if present | Check `Instant`/numeric type per implementation |
| `getAuthorities()` | Spring GrantedAuthority collection | Used by `hasAuthority(...)` and method security |

`getAttribute(name)` is a generic accessor and may return `null`. Never cast blindly across different providers; validate required claims before processing.

### DefaultOAuth2AuthenticatedPrincipal

`DefaultOAuth2AuthenticatedPrincipal` is the common implementation:

```java
OAuth2AuthenticatedPrincipal alice =
    new DefaultOAuth2AuthenticatedPrincipal(
        "alice-id-42",
        Map.of(
            "sub", "alice-id-42",
            "tenant_id", "north"),
        List.of(new SimpleGrantedAuthority("SCOPE_reports.read")));
```

This snippet compiles inside a class with proper imports and Spring Security dependencies. The constructor taking `name` preserves the principal name explicitly; a constructor taking `(Map, Collection)` also exists.

**A Principal is not an Authentication.** It represents the subject/attributes/authorities; Security uses it to construct the `Authentication` for a verified request.

## 7. BearerTokenAuthentication and Reactive SecurityContext

After successful introspection, Spring Security creates a `BearerTokenAuthentication`, containing:

```text
BearerTokenAuthentication
  principal      -> OAuth2AuthenticatedPrincipal
  authorities    -> GrantedAuthority collection
  tokenAttributes-> principal's attributes
  credentials    -> token-associated data (sensitive)
```

`Authentication.getName()` typically delegates to the principal name; `BearerTokenAuthentication.getTokenAttributes()` returns the accepted attributes. In WebFlux, `SecurityContext` flows through the **Reactor Context**.

Two ways to use it in controllers:

```java
@GetMapping("/api/me")
public Mono<String> me(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
    String sub = principal.getAttribute("sub");
    return Mono.just("subject=" + sub);
}
```

```java
@GetMapping("/api/meta")
public Mono<String> meta(BearerTokenAuthentication authentication) {
    Object subject = authentication.getTokenAttributes().get("sub");
    return Mono.just("subject=" + subject);
}
```

These are two **illustrative methods**, not standalone Java files. Expose them only on protected endpoints. When logging, log only request IDs or policy-approved subject identifiers; **never log `getCredentials()`, token values, or the full authentication**.

### Avoiding Principal Type Confusion

| Scenario | Typical Principal/Authentication |
|---|---|
| Opaque Resource Server | `OAuth2AuthenticatedPrincipal` / `BearerTokenAuthentication` |
| JWT Resource Server | `Jwt` / `JwtAuthenticationToken` |
| OAuth2 Login | `OAuth2User` / `OAuth2AuthenticationToken` |
| OIDC Login | `OidcUser` / `OAuth2AuthenticationToken` |
| Basic username/password | `UserDetails` or provider-created principal |

Never use `@AuthenticationPrincipal Jwt` on a route configured solely for opaque introspection and assume it is non-null. And never treat an opaque token principal as having admin rights merely because `authenticated()` evaluates to true.

## 8. Mapping Scopes to Authorities: 401 or 403?

Example introspection response:

```json
{"active":true,"sub":"alice","scope":"messages.read reports.read"}
```

Spring Security maps scopes by default to:

```text
SCOPE_messages.read
SCOPE_reports.read
```

And policy:

```java
.pathMatchers(HttpMethod.GET, "/api/messages")
    .hasAuthority("SCOPE_messages.read")
.pathMatchers(HttpMethod.GET, "/api/reports")
    .hasAuthority("SCOPE_reports.read")
```

**`hasRole("ADMIN")` normally checks `ROLE_ADMIN`, not `SCOPE_admin`.** If role data comes from an AS or trusted entitlement service, map authorities explicitly using an allowlist; never read roles from caller-supplied headers.

| Case | Typical HTTP Status | Reason |
|---|---|---|
| Missing bearer on protected route | 401 | Unauthenticated |
| Inactive/unknown/expired token | 401 | Authentication failed |
| Active token missing scope | 403 | Authenticated but lacks authority |
| Active token with scope but wrong tenant | 403 or 404 per policy | Business authorization |
| Active token with sufficient permissions | 200 when business succeeds | Permitted |
| AS timeout / malformed reply | Fail closed; response per failure handler | Never emit an authenticated principal |

**Critical security point:** returning `active:true` does not automatically guarantee the token matches each API's audience. When an AS serves multiple resources, the API must enforce `aud`/`resource`, issuer/client, tenant, and data permissions as required by policy.

## 9. Complete Java 17+ Spring Boot WebFlux Project

The demo includes public, profile, messages, admin, and tenant-scoped report endpoints. Spring Boot builds the real introspector from properties; tests use a fake introspector **only inside tests** to verify the bearer -> principal -> authorization flow without needing a real IdP.

### 9.1 Project Structure

```text
webflux-opaque-principal/
  settings.gradle
  build.gradle
  src/main/resources/application.yml
  src/main/java/example/opaque/OpaqueApplication.java
  src/main/java/example/opaque/SecurityConfiguration.java
  src/main/java/example/opaque/OpaqueController.java
  src/test/java/example/opaque/OpaqueSecurityTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'webflux-opaque-principal'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example.opaque'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**src/main/resources/application.yml**

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.invalid/oauth2/introspect
          client-id: training-introspection
          client-secret: training-not-a-real-secret
```

Host `idp.example.invalid` **has no real IdP**; the project can boot and return public/401 for unauthenticated requests, while real bearer tokens cannot be introspected until a real AS is configured. The tests import a stub introspector and do not call this endpoint. In production, use:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: ${INTROSPECTION_URI}
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

These three configuration variables must be supplied via secret/config management; enforce HTTPS/trust and least privilege for the introspection client.

### 9.2 Main Application

**src/main/java/example/opaque/OpaqueApplication.java**

```java
package example.opaque;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OpaqueApplication {
    public static void main(String[] args) {
        SpringApplication.run(OpaqueApplication.class, args);
    }
}
```

### 9.3 SecurityConfiguration.java

**src/main/java/example/opaque/SecurityConfiguration.java**

```java
package example.opaque;

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
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/messages")
                    .hasAuthority("SCOPE_messages.read")
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasAuthority("SCOPE_admin.read")
                .pathMatchers(HttpMethod.GET,
                    "/api/tenant/{tenantId}/reports")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
```

Key points to read:

1. `@EnableWebFluxSecurity` + `SecurityWebFilterChain` is the reactive mechanism, not Servlet `HttpSecurity`.
2. `.oauth2ResourceServer(...opaqueToken(...))` enables opaque token introspection.
3. `.hasAuthority("SCOPE_messages.read")` enforces permissions by trusted scope, **not** by client query parameters.
4. The tenant route requires a scope while still checking `tenant_id` in the controller/service.
5. With an **invalid** Bearer token, the authentication filter may still return 401 even on a `permitAll` route; public means no token is required, **not** that fake tokens are accepted.
6. The demo only has GET routes so no CSRF token is used; apps with unsafe methods and browser-managed credentials must evaluate CSRF per threat model.

### 9.4 OpaqueController.java

**src/main/java/example/opaque/OpaqueController.java**

```java
package example.opaque;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
public class OpaqueController {

    public record Message(String message) {}
    public record Profile(
        String subject, String tenant, List<String> authorities) {}

    @GetMapping("/api/public")
    public Mono<Message> publicEndpoint() {
        return Mono.just(new Message("public"));
    }

    @GetMapping("/api/me")
    public Mono<Profile> me(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal,
            BearerTokenAuthentication authentication) {
        String subject = principal.getAttribute("sub");
        String tenant = principal.getAttribute("tenant_id");
        List<String> authorities = authentication.getAuthorities()
            .stream().map(a -> a.getAuthority()).sorted().toList();

        // Do not serialize the entire Authentication/opaque token.
        return Mono.just(new Profile(subject, tenant, authorities));
    }

    @GetMapping("/api/messages")
    public Mono<Message> messages(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return Mono.just(new Message(
            "messages for " + principal.getName()));
    }

    @GetMapping("/api/admin")
    public Mono<Message> admin() {
        return Mono.just(new Message("admin-area"));
    }

    @GetMapping("/api/tenant/{tenantId}/reports")
    public Mono<Message> tenantReports(
            @PathVariable String tenantId,
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {

        String allowedTenant = principal.getAttribute("tenant_id");
        if (allowedTenant == null || !allowedTenant.equals(tenantId)) {
            return Mono.error(
                new ResponseStatusException(HttpStatus.FORBIDDEN));
        }
        return Mono.just(new Message("reports for " + allowedTenant));
    }
}
```

**Demo limitation:** the controller checks tenant equality merely to illustrate the boundary. Production should enforce tenant/owner checks at the repository query layer and verify issuer+subject/internal account mapping. Never call `findAll()` and filter results after the DB has already returned every tenant.

### 9.5 OpaqueSecurityTest.java — WebTestClient Through Security WebFilters

**src/test/java/example/opaque/OpaqueSecurityTest.java**

```java
package example.opaque;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
@Import(OpaqueSecurityTest.TestIntrospector.class)
class OpaqueSecurityTest {

    @Autowired
    WebTestClient client;

    @TestConfiguration(proxyBeanMethods = false)
    static class TestIntrospector {

        private static OAuth2AuthenticatedPrincipal principal(
                String user, String tenant, String... granted) {
            List<GrantedAuthority> authorities = new ArrayList<>();
            for (String name : granted) {
                authorities.add(new SimpleGrantedAuthority(name));
            }
            return new DefaultOAuth2AuthenticatedPrincipal(
                user,
                Map.of("sub", user, "tenant_id", tenant),
                authorities);
        }

        @Bean
        ReactiveOpaqueTokenIntrospector testOpaqueTokenIntrospector() {
            // Present in test context only. Does not verify real tokens!
            return token -> Mono.defer(() -> switch (token) {
                case "alice-token" -> Mono.just(principal(
                    "alice", "north",
                    "SCOPE_messages.read", "SCOPE_reports.read"));
                case "bob-token" -> Mono.just(principal(
                    "bob", "south",
                    "SCOPE_messages.read", "SCOPE_reports.read"));
                case "admin-token" -> Mono.just(principal(
                    "admin", "north", "SCOPE_admin.read"));
                case "viewer-token" -> Mono.just(principal(
                    "viewer", "north"));
                case "revoked-token", "expired-token" -> Mono.error(
                    new BadOpaqueTokenException("Inactive token"));
                default -> Mono.error(
                    new BadOpaqueTokenException("Unrecognized token"));
            });
        }
    }

    @Test
    void publicRouteAllowsAnonymous() {
        client.get().uri("/api/public").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("public");
    }

    @Test
    void protectedRouteWithoutTokenIs401() {
        client.get().uri("/api/me").exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void principalExposesVerifiedSubjectAndAuthorities() {
        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth("alice-token"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.subject").isEqualTo("alice")
            .jsonPath("$.tenant").isEqualTo("north")
            .jsonPath("$.authorities[0]")
                .isEqualTo("SCOPE_messages.read");
    }

    @Test
    void scopeAllowsMessages() {
        client.get().uri("/api/messages")
            .headers(h -> h.setBearerAuth("bob-token"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("messages for bob");
    }

    @Test
    void tokenWithoutScopeGets403() {
        client.get().uri("/api/messages")
            .headers(h -> h.setBearerAuth("viewer-token"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void revokedTokenGets401() {
        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth("revoked-token"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void expiredTokenGets401() {
        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth("expired-token"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void adminScopeAllowsAdminRoute() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBearerAuth("admin-token"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("admin-area");
    }

    @Test
    void aliceCannotUseAdminRoute() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBearerAuth("alice-token"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void tenantConstraintStillAppliesWithValidScope() {
        client.get().uri("/api/tenant/north/reports")
            .headers(h -> h.setBearerAuth("alice-token"))
            .exchange()
            .expectStatus().isOk();

        client.get().uri("/api/tenant/south/reports")
            .headers(h -> h.setBearerAuth("alice-token"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void unknownTokenCannotBecomeAuthenticated() {
        client.get().uri("/api/me")
            .headers(h -> h.setBearerAuth("random-token"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

**11 test methods** verify public access, 401 on missing credentials, principal/authority extraction, 403 on missing scope, revoked/expired/unknown tokens, admin role, and tenant isolation. The test stub accepts only fixed token fixtures and errors on any other token.

Because `@TestConfiguration` is only `@Import`ed in tests, it **does not replace the production introspector during `bootRun`**. This tests **WebFilter bearer parsing + authentication + authorization**, not real RFC 7662 HTTP introspection.

**Run:**

```bash
gradle test
```

You can use `./gradlew test` with the matching Wrapper version, or `gradlew.bat test` on Windows.

**Do not claim Gradle was executed:** the tests represent expected results from reviewing APIs and syntax. When actually running, verify the dependency tree, compilation errors, and specific assertions. These tests do not prove a real AS issues/revokes tokens, nor TLS configuration, Basic introspection credentials, latency, or retries.

### 9.6 Running the App and Calling Endpoints with a Real IdP

```bash
gradle bootRun

curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/me

# After replacing YAML with real introspection URI and credentials:
curl -i -H "Authorization: Bearer <ACCESS_TOKEN>" \
  http://localhost:8080/api/me
```

`<ACCESS_TOKEN>` is only a placeholder; never place real raw tokens in documentation or shared logs. `curl -i` prints the response status; if a token is missing or inactive, expect 401; if active but lacking route permissions, expect 403.

## 10. Customizing the Introspector to Map Authorities

Many enterprises want to inspect a tenant claim or translate scopes into roles. A reliable approach is a **decorator** that invokes the delegate introspector **first**, then maps.

**src/main/java/example/policy/TenantPolicyIntrospector.java** (an alternative example; **do not add directly to the Section 9 project**):

```java
package example.policy;

import java.util.ArrayList;
import java.util.Collection;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

import reactor.core.publisher.Mono;

public final class TenantPolicyIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;

    public TenantPolicyIntrospector(
            ReactiveOpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token).map(principal -> {
            Object value = principal.getAttributes().get("tenant_id");
            if (!(value instanceof String tenant)
                    || tenant.isBlank()) {
                throw new BadOpaqueTokenException(
                    "Required verified tenant is missing");
            }

            Collection<GrantedAuthority> authorities =
                new ArrayList<>(principal.getAuthorities());

            boolean canRead = authorities.stream().anyMatch(a ->
                "SCOPE_reports.read".equals(a.getAuthority()));

            if (canRead) {
                authorities.add(
                    new SimpleGrantedAuthority("ROLE_REPORT_VIEWER"));
            }

            return new DefaultOAuth2AuthenticatedPrincipal(
                principal.getName(),
                principal.getAttributes(),
                authorities);
        });
    }
}
```

The class only maps a verifiable role derived from AS scopes. It **does not grant admin privileges on its own** and does not construct a principal if the tenant is absent. A `roles` claim from the AS can be used, provided its format, issuer, and official role allowlist are validated.

### Avoiding Bean Circular Dependencies

Do not write:

```java
// RISK OF CIRCULAR DEPENDENCY:
@Bean
ReactiveOpaqueTokenIntrospector wrapper(
        ReactiveOpaqueTokenIntrospector sameBean) {
    return new TenantPolicyIntrospector(sameBean);
}
```

Instead, **construct the delegate explicitly** from the introspection URL and credentials and expose only the final bean, or declare two beans with distinct qualifiers. Boot auto-configuration backs off whenever the app provides a custom introspector bean; never assume it still creates a delegate for your custom wrapper.

In Boot 3.3, construct the delegate with the 6.3-compatible implementation/constructor; in Spring Security 6.5+, use the new builder. Check the exact version before writing the factory.

## 11. Unit Testing ReactiveOpaqueTokenIntrospector Directly with StepVerifier

Example test snippet for the decorator using a fake delegate, without needing a Spring `ApplicationContext`:

```java
ReactiveOpaqueTokenIntrospector delegate = token ->
    Mono.just(new DefaultOAuth2AuthenticatedPrincipal(
        "alice",
        Map.of("sub", "alice", "tenant_id", "north"),
        List.of(
            new SimpleGrantedAuthority("SCOPE_reports.read"))));

TenantPolicyIntrospector policy =
    new TenantPolicyIntrospector(delegate);

StepVerifier.create(policy.introspect("fixture"))
    .assertNext(p -> {
        boolean mapped = p.getAuthorities().stream()
            .anyMatch(a ->
                "ROLE_REPORT_VIEWER".equals(a.getAuthority()));
        org.junit.jupiter.api.Assertions.assertTrue(mapped);
    })
    .verifyComplete();
```

This is a **test snippet** requiring imports (`Map`, `List`, `Mono`, `StepVerifier`) and a containing test class. Follow-up exercises: a delegate missing `tenant_id` must emit `BadOpaqueTokenException`; a delegate failing with 5xx/timeout must propagate the error rather than producing a principal.

**Never use an always-accept stub in production.** Unit tests verify decorator code and do not replace HTTP integration tests against an AS.

## 12. Fast Tests with Spring Security mockOpaqueToken()

When the goal is solely to test a controller or method authorization, Spring Security Test provides:

```groovy
testImplementation 'org.springframework.security:spring-security-test'
```

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOpaqueToken;

// Mock-based WebTestClient snippet:
client.mutateWith(mockOpaqueToken())
    .get().uri("/api/me")
    .exchange()
    .expectStatus().isOk();
```

`mockOpaqueToken()` builds a mock `BearerTokenAuthentication` with principal/authorities for the test request. It **bypasses real introspection**, making unit tests fast but not proving that `active:false`, client secrets, HTTP bodies, or AS errors are handled properly.

Comparing the tiers:

- `mockOpaqueToken()`: tests controllers with a mocked security context; fast.
- Fake `ReactiveOpaqueTokenIntrospector` + Bearer header as in Section 9: tests requests passing through the filter pipeline and calling the stub introspector without an AS.
- Mock HTTP AS / WireMock / MockWebServer: tests RFC 7662 networking, credentials, active true/false, timeouts, and scope mapping; suited for integration tests.
- Staging/real AS: tests real key/secret rotation, TTL, revocation, and environment behavior.

## 13. Performance, Revocation, and AS Outages

Opaque token introspection typically adds a network call on the critical path:

```text
Client HTTP request -> Resource Server -> Authorization Server
                                         introspection
                       <- active / claims
                     authorization + domain DB
Client <- 200 / 401 / 403
```

If every API request introspects and QPS is high, cost increases on both the AS and Resource Server:

- Higher latency: DNS/TLS/network/JSON parsing.
- An AS outage can impact all protected APIs.
- Introspection credentials can be misconfigured/rotated, causing spikes in 401/5xx errors.
- Caching results reduces load but **allows revoked tokens to keep being accepted** until the TTL expires.

### Fail Closed, Timeouts, Retries

1. Bound connect/read/total timeouts, connection pools, and concurrency.
2. When the AS returns invalid/inactive: do not keep retrying to force `active=true`.
3. When the AS returns 5xx or times out: handle with bounded backoff/circuit breaker, **never letting unauthenticated requests pass**.
4. Distinguish introspection transport failures from invalid-token failures in internal logs/metrics.
5. Never log tokens, client secrets, Authorization headers, or raw introspection bodies.
6. Use HTTPS with certificate validation only; never disable TLS checks for convenience.
7. If retrying, never retry unboundedly on every bad bearer token, which can trigger amplification DoS.

### What Are the Risks of Caching Introspection?

```text
10:00 Token X active=true, cache TTL 5 minutes
10:01 User logs out / revokes Token X
10:02 Cache still returns active=true
10:05 TTL expires -> queries AS -> active=false
```

If near-instant revocation is required, long caches are inappropriate.

- TTL must not exceed token `exp` and must align with the revocation SLA.
- Tokens lacking `exp` must not be cached indefinitely.
- Never use raw access tokens as metric labels, log text, or plain Redis keys.
- Partition cache keys by issuer/introspection endpoint/tenant and use a secure HMAC/digest when needed.
- Consider cache invalidation when permissions/roles/tenants change.
- Verify multi-node caching, clock skew, idempotency, and negative caching.
- Spring Security documentation does not promise a universal default cache TTL; measure and design per your threat model.

## 14. Active Does Not Replace Audience and Object-Level Authorization

A token can be `active:true` because it is still valid at the AS, yet have been issued for **another resource**:

```text
token: active=true, aud=["inventory-api"]
request: Payroll API /payroll/users

Checking only active+authenticated -> risk of accepting wrong token
Must check aud/resource/scope/issuer per Payroll policy.
```

If the introspection response lacks `aud` and the resource API requires audience isolation, ask the AS to return the needed claims or enforce another mechanism verifying the token is meant for this API. Never assume "missing claim = all resources permitted."

**Multi-tenancy:** scope `reports.read` is only a broad capability. Data queries must bind tenant/owner, e.g., pseudo R2DBC:

```java
Flux<Report> findVisibleReports(
        String trustedTenantId, String trustedUserId) {
    return repository.findAllByTenantIdAndOwnerId(
        trustedTenantId, trustedUserId);
}
```

This snippet does not compile standalone; the repository must be declared for your real entity. `trustedTenantId` and `trustedUserId` must come from the verified principal and policy mapping, never directly from query parameters.

## 15. Differences Between Reactive and Servlet

| Factor | Spring WebFlux | Spring MVC / Servlet |
|---|---|---|
| Security builder | `ServerHttpSecurity` | `HttpSecurity` |
| Chain | `SecurityWebFilterChain` | `SecurityFilterChain` |
| Introspector | `ReactiveOpaqueTokenIntrospector` | `OpaqueTokenIntrospector` |
| Return type | `Mono<OAuth2AuthenticatedPrincipal>` | `OAuth2AuthenticatedPrincipal` |
| Request | `ServerWebExchange` | Servlet request |
| Principal | `OAuth2AuthenticatedPrincipal` | `OAuth2AuthenticatedPrincipal` (same interface) |
| Authenticated token | `BearerTokenAuthentication` | `BearerTokenAuthentication` (same type) |
| Authentication context | Reactor Context | ThreadLocal in Servlet flow |
| Test | WebTestClient | MockMvc |

Never import a Servlet implementation and wrap its blocking call in `Mono.just(...)` on the event loop; this risks thread starvation and timeouts. If the introspection backend is inherently synchronous, evaluate a reactive `WebClient` solution or a bounded, monitored scheduler boundary.

## 16. Common Pitfalls

| Symptom | Diagnosis |
|---|---|
| Bearer always returns 401 | AS returns inactive, wrong URI, wrong introspection credentials, expired TTL, wrong issuer token |
| Token active yet 403 | Missing `SCOPE_...` or rejected by tenant/role policy |
| `hasRole("ADMIN")` fails | Scope claims map to `SCOPE_admin`, not `ROLE_ADMIN` |
| Reading `scope` throws ClassCastException | Introspector already converted it to a List; do not cast unconditionally to String |
| `getName()` has wrong user | AS uses a claim other than `sub`; configure trusted name mapping |
| External caller uses another API's token | Missing audience/resource validation |
| Public endpoint returns 401 when junk bearer sent | Filter still attempts to authenticate invalid bearer headers |
| AS downtime breaks all protected APIs | Resource Server depends on introspection; plan availability/timeouts |
| Revoked token still returns 200 | Positive cache TTL too long or AS not yet updated |
| Valid token for wrong tenant still reads data | Scope-only authorization; query lacks tenant filtering |
| `@AuthenticationPrincipal Jwt` is null | Configured for opaque tokens; principal is not a `Jwt` |
| Every token becomes admin in tests, fails in prod | Always-accept stub placed in wrong context |
| Using 6.5 builder on Security 6.3 | No `withIntrospectionUri` method; use version-appropriate Boot properties/constructor |
| Confusing 401 and 403 | Distinguish authentication failure vs. authorization denied |
| `mockOpaqueToken()` passes while integration fails | Test skips HTTP introspection/credentials |
| Token leaked in logs | Redact raw HTTP headers, principal/credentials, and sensitive token attributes |
| Wrong `SecurityWebFilterChain` selected | Check `securityMatcher`, `@Order`, and fallback chains |
| Issuer/tenant claims have wrong types | Validate required claims before constructing principal |

Never "fix" these errors by setting `.anyExchange().permitAll()`, disabling token checks, or writing `onErrorResume(e -> Mono.just(adminPrincipal))`.

## 17. Recommended Production Test Matrix

1. Missing Bearer -> 401.
2. Malformed/invalid Bearer -> 401, controller not called.
3. Active token with valid scope -> 200.
4. Active token missing scope -> 403.
5. AS returns `active:false` -> 401.
6. Token revoked between two requests -> subsequent request blocked per revocation SLA.
7. Expired token -> 401.
8. AS returns 401 due to wrong introspection client secret -> no principal created.
9. AS returns 429/500/timeout/malformed JSON -> fail closed, categorized metrics.
10. Missing or mistyped `sub`/`tenant_id` claims -> deny when policy requires them.
11. Wrong audience/issuer -> deny, even if `active=true`.
12. Cross-tenant/owner route -> deny at service/repository layer.
13. Scopes containing `.` or `:` mapped with exact prefix.
14. No response leaks tokens or secrets.
15. Load test the AS introspection endpoint: QPS, p95/p99, connection pool, backoff.
16. Cache TTL and multi-pod consistency after revocation.
17. Runbooks for credential rotation, issuer migration, and AS outages.
18. Dependency upgrades Spring Security 6.3->6.5/7.x with tests on introspector implementations/builders.

## 18. Adoption Checklist

- Choose the right model: opaque introspection vs. JWT signature decoding.
- Enable `oauth2ResourceServer().opaqueToken()` on the right WebFlux chain.
- Use `ReactiveOpaqueTokenIntrospector` and `OAuth2AuthenticatedPrincipal` from the right packages.
- Configure introspection URI, client-id, and client-secret from trusted sources over TLS.
- Define required attributes, principal name, and scopes/roles clearly.
- Reject inactive tokens and introspection errors; never fail open.
- Enforce audience, issuer, tenant, client, and record ownership per policy.
- Use allowlisted DTOs in JSON; never serialize raw principals/tokens.
- Protect the event loop, timeouts, backpressure, circuit breakers, and AS availability.
- If caching, define the revocation window and cap TTL within `exp`.
- Test real `WebTestClient` bearer headers + fake introspector, test `mockOpaqueToken` separately, and run HTTP introspection integration tests with mock/real AS.
- When upgrading, check `NimbusReactiveOpaqueTokenIntrospector`/`SpringReactiveOpaqueTokenIntrospector` variants and builder APIs.
- Keep production on a security-supported Spring Security release.

## 19. Practice Exercises

1. Write an explanation of why an opaque token cannot provide subject/scopes on its own without introspection.
2. Compare `ReactiveOpaqueTokenIntrospector` with `ReactiveJwtDecoder` regarding revocation and network cost.
3. Construct a `DefaultOAuth2AuthenticatedPrincipal` with `sub`/`tenant_id` and two scopes.
4. In `WebTestClient`, switch `alice-token` to `viewer-token` on `/api/messages`. Why does it return 403?
5. Verify an active token for another tenant gets 403 despite holding `SCOPE_reports.read`.
6. Add a case where the introspector returns `Mono.error(new BadOpaqueTokenException(...))` and verify HTTP 401.
7. Use `mockOpaqueToken()` and explain why it does not prove introspection networking works.
8. Write a `StepVerifier` unit test for `TenantPolicyIntrospector` when the tenant is missing.
9. Stand up a mock AS returning `active:true` and `active:false`, verifying client authentication and the form-encoded request.
10. Write an audience policy for the Reports API accepting only `aud=reports-api`.
11. Measure the cost of 1,000 requests when every request introspects; discuss cache TTL and revocation.
12. Design a safe fallback when the AS times out without returning 200 or default roles.
13. Compare 401, 403, and 5xx/AS outage errors in an operations report.
14. Audit potential token exposure in HTTP logs, traces, test reports, and exception handling.
15. Upgrade Spring Security 6.3 to a newer version and update introspector construction per Javadoc.

## Conclusion

**`ReactiveOpaqueTokenIntrospector`** verifies a bearer access token in **Spring Security WebFlux**, returning `Mono<OAuth2AuthenticatedPrincipal>` on success. The principal carries **attributes and authorities** so Spring can build `BearerTokenAuthentication` and enforce authorization; inactive or unverified tokens must be rejected. Under standard policies, **401** is for unauthenticated or invalid bearer requests, while **403** is for an authenticated principal lacking scope/tenant permissions. Introspection supports revocation detection at the cost of extra latency and Authorization Server dependency. Production systems need TLS, secret management, audience validation, tenant checks, fail-closed handling, TTL-bounded caching, and thorough negative tests.

## Official Documentation

1. Spring Security 6.5 — Reactive Resource Server Opaque Token: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html
2. Spring Security — ReactiveOpaqueTokenIntrospector Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html
3. Spring Security — SpringReactiveOpaqueTokenIntrospector.Builder (Since 6.5): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.Builder.html
4. Spring Security — DefaultOAuth2AuthenticatedPrincipal Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/core/DefaultOAuth2AuthenticatedPrincipal.html
5. Spring Security — Reactive OAuth2 testing, mockOpaqueToken: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
6. Spring Security 6.3 — Introspection package Javadoc: https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/oauth2/server/resource/introspection/package-summary.html
7. Spring Boot 3.3 — WebFlux Security/OAuth2 Resource Server: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
8. RFC 7662 — OAuth2 Token Introspection: https://www.rfc-editor.org/rfc/rfc7662
9. RFC 6750 — OAuth2 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
