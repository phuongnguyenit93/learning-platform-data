# Mapping Introspection Attributes and Scopes to GrantedAuthority in Spring Security WebFlux

## Objectives and Scope

This lesson belongs to **Spring Security – reactive**, topic **Resource Server Opaque**. Learners will understand:

1. How a Resource Server authenticates an **opaque Bearer token** via OAuth 2.0 Token Introspection (RFC 7662), then converts introspection data into an `OAuth2AuthenticatedPrincipal` and `GrantedAuthority` instances.
2. The default rule **scope -> `SCOPE_<scope>`**, and the difference between `hasAuthority("SCOPE_reports.read")` and `hasRole("ANALYST")`.
3. How to read attributes `active`, `scope`, `sub`, `client_id`, `aud`, `iss`, `exp`, `tenant`, and `app_roles`, while distinguishing standard RFC fields from IdP-specific extensions.
4. How to write a **decorator** `ReactiveOpaqueTokenIntrospector`: delegating token verification to `SpringReactiveOpaqueTokenIntrospector`, then **preserving scope authorities** and adding only business roles from a verified allowlist.
5. How to combine `SecurityWebFilterChain`, `ServerHttpSecurity.oauth2ResourceServer(...).opaqueToken(...)`, `BearerTokenAuthentication`, `@AuthenticationPrincipal`, `WebTestClient`, and `StepVerifier`.
6. Building a complete Java 17+ / Spring Boot 3.5.x example, tested against a **local mock HTTP introspection server on localhost** without needing a real IdP.
7. Analyzing risks of **privilege escalation**, scope injection, loose role mapping, cached introspection vs. revocation, introspection server downtime, wrong audience/tenant, missing timeouts, and token exposure in logs.
8. Clearly distinguishing **token validity verification** from **operation authorization**, and when resource-level permission checks are needed in the service/database.

> The hands-on code uses Spring Boot **3.5.16** / Spring Security **6.5.x**, Java 17+, and pure WebFlux. Spring Boot 3.5.16 is the final OSS release of the 3.5 line; for new systems, use a currently supported Spring Boot/Security release. Servlet APIs such as `HttpSecurity`, `SecurityFilterChain`, `OpaqueTokenIntrospector` (without Reactive), and `HttpServletRequest` are **not** used in this reactive example.

---

## 1. Model: From Bearer Token to Authorities

An OAuth2 **Authorization Server / Identity Provider (IdP)** issues access tokens. With opaque tokens, the token string carries no trustworthy claim structure for the Resource Server to read directly. The Resource Server sends the token to the Authorization Server's **introspection endpoint**, verifies token status, and receives metadata.

```text
Client / Service
   |
   | GET /api/reports
   | Authorization: Bearer <opaque-token>
   v
Spring Security WebFlux Resource Server
   |
   +-- Bearer token authentication filter
   |       |
   |       +-- ReactiveOpaqueTokenIntrospector.introspect(token)
   |              |
   |              +-- HTTPS POST /oauth2/introspect
   |              |   Resource server Basic auth
   |              |
   |              +-- Authorization Server returns JSON:
   |                  active=true, sub, scope, aud, ...
   |
   +-- OAuth2AuthenticatedPrincipal
   |      - attributes: sub, scope, tenant, app_roles...
   |      - authorities: SCOPE_reports.read, ROLE_ANALYST...
   |
   +-- BearerTokenAuthentication
   |      - principal + attributes + GrantedAuthority
   |
   +-- AuthorizationWebFilter
   |      - hasAuthority("SCOPE_reports.read")
   |      - hasRole("ANALYST")
   |
   +-- Controller / Service / Database (ownership, tenant)
   |
   +-- 200 / 401 / 403
```

**Two layers must be kept distinct:**

- **Authentication:** Is the token valid and accepted by the Authorization Server? Spring Security uses the introspector; `active=false` must be rejected. On a valid response, it creates `OAuth2AuthenticatedPrincipal` and `BearerTokenAuthentication`.
- **Authorization:** Is the valid token allowed to perform this action? Spring Security checks `GrantedAuthority` against HTTP/method policies; the service then checks owner/tenant/resource rules.

**Not every introspection attribute automatically becomes an authority.** By default, Spring Security converts scopes into `SCOPE_...`. Fields such as `app_roles`, `groups`, `tenant`, or `department` do **not automatically** turn into Spring roles.

## 2. Standard Introspection Response and Extension Attributes

An example introspection response:

```json
{
  "active": true,
  "scope": "reports.read reports.write",
  "client_id": "internal-portal",
  "sub": "alice",
  "aud": "api://reports",
  "iss": "https://idp.example.test",
  "token_type": "Bearer",
  "exp": 1893456000,
  "tenant": "acme",
  "app_roles": ["analyst"]
}
```

This illustrates a contract with a hypothetical IdP, not a mandatory structure for every provider.

| Field | Meaning | Safe Handling |
| --- | --- | --- |
| `active` | Is the token currently valid per the Authorization Server? | `false` -> reject; never create a principal when inactive |
| `scope` | OAuth2 permission list, typically a space-separated string | Framework maps each scope to `SCOPE_...` by default |
| `client_id` | OAuth2 client issued the token | Do not confuse with end user or `ROLE_*` |
| `sub` | Subject of the token | Use as identity post-authentication; verify tenant if needed |
| `aud` | Target Resource/API for the token | Match against this API's audience; may be String or collection |
| `iss` | Token issuer if published by provider | Trust only configured/allowed issuers; not every IdP returns this field |
| `exp` | Expiration time (epoch seconds) | Evaluate IdP policy and revocation capability |
| `token_type` | Token type | Never equate with roles or scopes |
| `tenant` | Extension attribute, e.g., tenant ID | Never treat client-provided query params as verified tenant |
| `app_roles` | Extension role attribute per IdP contract | Map allowlisted values only, for the right issuer/audience/tenant |

**From RFC 7662:** `active` is the core field; fields like `scope`, `client_id`, `sub`, `aud`, `iss`, and `exp` may be returned depending on the token/IdP. `tenant` and `app_roles` are **custom extension** data, not standard claims present on every introspection endpoint.

### Why Not Read Scopes Directly from an Opaque Token?

An opaque string such as `opaque-token-abc` does not contain trustworthy scopes in a standard format. If the client also sends:

```http
GET /api/reports HTTP/1.1
Authorization: Bearer opaque-token-abc
X-User-Role: ADMIN
X-Scope: reports.admin
```

then `X-User-Role` and `X-Scope` are **client-controlled headers**. Never grant `ROLE_ADMIN`/`SCOPE_reports.admin` based on them. Permissions must originate from a trusted introspection server or verified authorization service and be enforced by policy.

## 3. How Scopes Map to GrantedAuthority by Default

Spring Security reactive opaque token support:

1. Passes the token through `ReactiveOpaqueTokenIntrospector`.
2. For active tokens, takes the scopes returned by the introspection endpoint.
3. Converts each scope into a `SimpleGrantedAuthority` prefixed with **`SCOPE_`**.
4. Places them on `OAuth2AuthenticatedPrincipal.getAuthorities()` and `BearerTokenAuthentication.getAuthorities()`.

Introspection example:

```json
{
  "active": true,
  "sub": "alice",
  "scope": "reports.read reports.write"
}
```

Resulting default authorities semantically:

```text
SCOPE_reports.read
SCOPE_reports.write
```

**There is no `ROLE_ANALYST` authority in this example**, even though the resource server verified the token.

| Introspection Scope | GrantedAuthority | Corresponding Rule |
| --- | --- | --- |
| `reports.read` | `SCOPE_reports.read` | `hasAuthority("SCOPE_reports.read")` |
| `reports.write` | `SCOPE_reports.write` | `hasAuthority("SCOPE_reports.write")` |
| `message:read` | `SCOPE_message:read` | `hasAuthority("SCOPE_message:read")` |
| Missing scope | No corresponding SCOPE authority | Rules requiring the scope must deny |

**Distinguishing matchers:** `hasRole("ANALYST")` in standard configurations checks `ROLE_ANALYST`, **not** `SCOPE_ANALYST`. Meanwhile, `hasAuthority("ROLE_ANALYST")` checks that exact authority string. Spring Security applies `ROLE_` for role matchers and does not automatically treat scopes as roles.

Instead of `hasAuthority`, you can use `OAuth2ReactiveAuthorizationManagers.hasScope("reports.read")` inside `.access(...)`. From the application's perspective, this still relies on the mapped scopes.

### HTTP Policy Example

```java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers(HttpMethod.GET, "/api/reports")
            .hasAuthority("SCOPE_reports.read")
        .pathMatchers(HttpMethod.GET, "/api/analyst")
            .hasRole("ANALYST")
        .anyExchange().denyAll()
)
```

This is a **fragment** inside `ServerHttpSecurity`, not a standalone Java program. These rules differ: a token with scope `reports.read` may still lack the analyst role; conversely, the analyst role does not automatically create scope `reports.read` unless the mapping grants it.

## 4. ReactiveOpaqueTokenIntrospector and DefaultOAuth2AuthenticatedPrincipal

In Spring Security 6.5, the reactive interface has the signature:

```java
Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
```

Located in package:

```java
org.springframework.security.oauth2.server.resource.introspection
```

With `SpringReactiveOpaqueTokenIntrospector`, Spring calls the introspection endpoint and returns a principal that has **already passed token verification**. If inactive/invalid, it must never return a principal treated as authenticated.

**Do not do this yourself:**

```java
// Anti-pattern: does not verify the token with the Authorization Server at all.
return Mono.just(new DefaultOAuth2AuthenticatedPrincipal(
        "alice",
        Map.of("scope", "reports.admin"),
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))));
```

That pattern turns any garbage token into a high-privilege principal if used as a production introspector. A mock introspector is permitted only in unit tests and must never be deployed in place of real verification.

**Proper extension approach:** wrap a real introspector:

```java
return trustedDelegate.introspect(token)
        .map(principal -> new DefaultOAuth2AuthenticatedPrincipal(
                principal.getName(),
                principal.getAttributes(),
                remapAuthorities(principal)));
```

In this pipeline:

- `trustedDelegate` verifies active status via the IdP first.
- `principal.getAttributes()` preserves claims returned by the IdP.
- `principal.getAuthorities()` contains the default scope authorities.
- `remapAuthorities(...)` only **adds or restricts** authorities per an explicit contract; never construct arbitrary roles from user input.

A common critical bug is creating a new collection containing only `ROLE_ANALYST` and **dropping all `SCOPE_...`**, or conversely copying raw `app_roles` without restricting prefixes/values.

## 5. Safe Mapping Rules for Extension Attributes

Suppose the IdP additionally guarantees:

```json
{
  "active": true,
  "sub": "alice",
  "aud": "api://reports",
  "scope": "reports.read",
  "tenant": "acme",
  "app_roles": ["analyst", "viewer"]
}
```

API policy:

- **Audience must be** `api://reports`. Tokens meant for other resources receive 401 even if active.
- **Scope `reports.read`** produces `SCOPE_reports.read` as provided by Spring Security's default.
- Only when `tenant=acme` and `app_roles` is genuinely a **collection** containing the exact string `analyst`, add `ROLE_ANALYST`.
- Never accept `admin`, `ROLE_ADMIN`, `root`, `superuser`, or arbitrary role strings.
- Never turn a role string sent by the client via HTTP parameters into an authority.
- In a real multi-tenant policy, the tenant must be matched against the resource in the service/DB; the hardcoded `acme` role mapping in this example is for the lab only.

### Why Must Scope Authorities Be Preserved?

Suppose the delegate produced:

```text
SCOPE_reports.read
SCOPE_profile
```

Correct mapper after adding analyst:

```text
SCOPE_reports.read
SCOPE_profile
ROLE_ANALYST
```

Incorrect mapper replacing everything:

```text
ROLE_ANALYST
```

In the latter case, an endpoint guarded by `hasAuthority("SCOPE_reports.read")` can return 403 despite the token having the right scope. The safe pattern is to initialize a `LinkedHashSet<GrantedAuthority>` from `principal.getAuthorities()` and then add only allowlisted roles, avoiding duplicates.

### Attribute Schemas Must Be Checked

Different introspection endpoints may return `scope` as a string or a framework-normalized collection; the extension field `app_roles` may be a JSON array, string, map, or absent. **Never cast blindly**:

```java
// Unsafe and prone to ClassCastException if the provider changes the format:
List<String> roles = (List<String>) principal.getAttribute("app_roles");
```

Better: check `instanceof Collection<?>`, inspect supported values, and treat missing fields with a deny policy. If the IdP uses another role format, define an adapter for the exact agreed schema rather than loosening checks arbitrarily.

## 6. Runnable Java 17+ Project: Spring WebFlux Resource Server Opaque

This complete project includes:

- A Spring Boot WebFlux application using real opaque token introspection over a reactive HTTP client.
- A `ScopeAndRoleIntrospector` decorator adding `ROLE_ANALYST` from allowlisted introspection attributes while **preserving default SCOPE authorities**.
- Audience validation for `api://reports` on every token before issuing an Authentication.
- API `/api/reports` requiring scope `reports.read`, `/api/analyst` requiring role `ANALYST`, and `/api/me` exposing non-sensitive metadata.
- `MockWebServer` in tests simulating an IdP returning `active=true/false` and attributes, verifying 401/403/200/role spoofing.

**In tests only**, the introspection endpoint is HTTP on `127.0.0.1`. **Production strictly requires HTTPS** and securely managed credentials; the project does not issue real tokens and does not implement an Authorization Server.

### 6.1. Directory Structure

```text
opaque-authorities-lab/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/opaquelab/
        OpaqueAuthoritiesApplication.java
        SecurityConfiguration.java
        ScopeAndRoleIntrospector.java
        ReportsController.java
      resources/
        application.yml
    test/
      java/example/opaquelab/
        OpaqueAuthoritiesIntegrationTest.java
```

Do not include `spring-boot-starter-web`. Adding both MVC and WebFlux to the classpath causes Spring Boot to prefer Servlet, breaking the expected stack and filter types.

### 6.2. Gradle Groovy DSL

**`settings.gradle`:**

```groovy
rootProject.name = 'opaque-authorities-lab'
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
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Boot 3.5.16 was chosen for an exact baseline targeting Spring Security 6.5.x, not as advice to deploy an EOL OSS line in new products. The project requires JDK 17+ and a compatible Gradle/Gradle Wrapper.

### 6.3. application.yml

**`src/main/resources/application.yml`:**

```yaml
server:
  port: 8080

spring:
  application:
    name: opaque-authorities-lab
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: ${INTROSPECTION_URI:https://idp.example.invalid/oauth2/introspect}
          client-id: ${INTROSPECTION_CLIENT_ID:resource-api}
          client-secret: ${INTROSPECTION_CLIENT_SECRET:demo-only-not-production}
```

Spring's `${...}` placeholder syntax resolves from the environment; the default values are solely for running the **local lab**, not real secrets. If you run `bootRun` outside tests and call `/api/reports` with a token, the app will attempt to call `idp.example.invalid` and **no protected data will be returned** because that domain is not an IdP. A real Authorization Server must be configured outside tests.

In integration tests, `@DynamicPropertySource` overrides the introspection URI, client-id, and client-secret to point to MockWebServer. **No real IdP is needed to run `./gradlew test`.**

### 6.4. Main Class

**`src/main/java/example/opaquelab/OpaqueAuthoritiesApplication.java`:**

```java
package example.opaquelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OpaqueAuthoritiesApplication {

    public static void main(String[] args) {
        SpringApplication.run(OpaqueAuthoritiesApplication.class, args);
    }
}
```

### 6.5. ScopeAndRoleIntrospector: Decorator Preserving Scopes, Adding Conditional Roles

**`src/main/java/example/opaquelab/ScopeAndRoleIntrospector.java`:**

```java
package example.opaquelab;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.user.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

import reactor.core.publisher.Mono;

public final class ScopeAndRoleIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private static final String EXPECTED_AUDIENCE = "api://reports";

    private final ReactiveOpaqueTokenIntrospector delegate;

    public ScopeAndRoleIntrospector(
            ReactiveOpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token).flatMap(principal -> {
            Object audience = principal.getAttribute("aud");

            if (!audienceMatches(audience, EXPECTED_AUDIENCE)) {
                return Mono.error(new OAuth2AuthenticationException(
                        new OAuth2Error("invalid_token",
                                "Token audience is not this API", null)));
            }

            // Preserve SCOPE_... created by the standard Spring introspector.
            Set<GrantedAuthority> authorities =
                    new LinkedHashSet<>(principal.getAuthorities());

            Object rawRoles = principal.getAttribute("app_roles");
            Object tenant = principal.getAttribute("tenant");

            // Only grant explicitly declared roles for the lab's tenant.
            if ("acme".equals(tenant)
                    && rawRoles instanceof Collection<?> roles
                    && roles.contains("analyst")) {
                authorities.add(
                        new SimpleGrantedAuthority("ROLE_ANALYST"));
            }

            return Mono.just(new DefaultOAuth2AuthenticatedPrincipal(
                    principal.getName(),
                    principal.getAttributes(),
                    authorities));
        });
    }

    private static boolean audienceMatches(
            Object audience, String expected) {
        if (audience instanceof String value) {
            return expected.equals(value);
        }
        if (audience instanceof Collection<?> values) {
            return values.contains(expected);
        }
        return false; // missing/unknown format -> deny
    }
}
```

**Careful explanation:**

1. `delegate.introspect(token)` must succeed before the mapping code runs. If the token is inactive/invalid, **there is no principal** to enrich with roles.
2. `audienceMatches` handles `aud` as either a string or collection; if missing, malformed, or mismatched, it emits `OAuth2AuthenticationException` with `invalid_token`. This is an **application-level policy addition**, not a default audience check on every opaque introspector.
3. Using `new LinkedHashSet<>(principal.getAuthorities())` keeps all `SCOPE_...` mapped by the delegate and never creates scopes from client-supplied headers or queries.
4. Only the value `"analyst"` inside collection `app_roles` **and** `tenant="acme"` produces `ROLE_ANALYST`. Values like `"admin"` or `"ROLE_ANALYST"` never grant permissions automatically.
5. `new DefaultOAuth2AuthenticatedPrincipal(principal.getName(), principal.getAttributes(), authorities)` preserves both the principal name and attributes published by the introspection server, changing only the authorities collection.
6. `flatMap` keeps the pipeline reactive; no `block()`, no manual `subscribe()`, and no ThreadLocal as a security context.
7. `EXPECTED_AUDIENCE` and the tenant condition are hardcoded because this is a **single-API, single-tenant lab**. Real applications must read from trusted policy/config and enforce tenant checks at the resource/service layer rather than relying on one global role check.

**Note:** Libraries and introspection endpoints can vary in how they normalize claims. If `app_roles` is a CSV string or different nested JSON, **do not** loosen `instanceof` with unsafe casts. The IdP API contract must specify the exact format and which values may grant roles.

### 6.6. SecurityConfiguration: Real Introspection + Mapping

**`src/main/java/example/opaquelab/SecurityConfiguration.java`:**

```java
package example.opaquelab;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    ReactiveOpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
                    String uri,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
                    String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
                    String clientSecret) {

        ReactiveOpaqueTokenIntrospector delegate =
                SpringReactiveOpaqueTokenIntrospector
                        .withIntrospectionUri(uri)
                        .clientId(clientId)
                        .clientSecret(clientSecret)
                        .build();

        return new ScopeAndRoleIntrospector(delegate);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/reports")
                            .hasAuthority("SCOPE_reports.read")
                        .pathMatchers(HttpMethod.GET, "/api/analyst")
                            .hasRole("ANALYST")
                        .pathMatchers(HttpMethod.GET, "/api/me")
                            .authenticated()
                        .anyExchange().denyAll()
                )
                .oauth2ResourceServer(oauth2 -> oauth2
                        .opaqueToken(Customizer.withDefaults()))
                .build();
    }
}
```

**Mandatory points:**

- Configure `spring.security.oauth2.resourceserver.opaquetoken.*` in the proper Spring Boot namespace. `@Value` reads properties/environment; real IdP client secrets must be managed via a secret manager.
- The application's `ReactiveOpaqueTokenIntrospector` bean **replaces the default introspector** Boot would otherwise create. Never register two ambiguous introspectors or directly instantiate Servlet's `SpringOpaqueTokenIntrospector`.
- `SpringReactiveOpaqueTokenIntrospector.withIntrospectionUri(...).clientId(...).clientSecret(...).build()` is the reactive client calling the real endpoint; Spring Security performs client authentication with the IdP per configuration.
- `SecurityWebFilterChain` uses `.opaqueToken(Customizer.withDefaults())` to pick up the matching `ReactiveOpaqueTokenIntrospector` bean.
- `/api/reports` requires **SCOPE_reports.read**, `/api/analyst` requires **ROLE_ANALYST**, and `/api/me` requires a valid token passing the audience check.
- Neither form login nor sessions are enabled for the demo, nor is a JWT decoder; tokens are verified via introspection.
- The demo only defines GET endpoints, so default CSRF does not block requests. If browser ambient cookies or unsafe methods are present, analyze CSRF separately instead of disabling it blindly.

**Difference between bean and DSL:** You could call `.opaqueToken(opaque -> opaque.introspector(customBean))` directly; however, defining a single `ReactiveOpaqueTokenIntrospector` bean and using `Customizer.withDefaults()` as in this project is sufficient. Avoid configuring the same policy in multiple places.

### 6.7. ReportsController: Reading Principal and Authorities

**`src/main/java/example/opaquelab/ReportsController.java`:**

```java
package example.opaquelab;

import java.util.Map;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ReportsController {

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/reports")
    public Mono<String> reports(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return Mono.just("reports-for-" + principal.getName());
    }

    @GetMapping("/api/analyst")
    public Mono<String> analyst() {
        return Mono.just("analyst-only");
    }

    @GetMapping("/api/me")
    public Mono<Map<String, Object>> me(
            BearerTokenAuthentication authentication) {

        var authorities = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();

        return Mono.just(Map.of(
                "name", authentication.getName(),
                "authorities", authorities,
                "tenant", String.valueOf(
                        authentication.getTokenAttributes().get("tenant"))));
    }
}
```

**This is a test API using dummy data.** `/api/me` returns only the principal name, authorities, and tenant for learners to observe. In production, do not expose introspection attributes and role data indiscriminately; enforce schema/authorization/logging policies. Specifically, never return the opaque Bearer token or `client_secret`.

Spring Security stores `BearerTokenAuthentication` in the Reactor Context after successful introspection. In WebFlux, `@AuthenticationPrincipal OAuth2AuthenticatedPrincipal` is the way to access attributes; never use Servlet request/session APIs.

### 6.8. Flow of a Successful Request

For example, a client calls:

```http
GET /api/reports HTTP/1.1
Authorization: Bearer reader-token
```

In tests, MockWebServer returns:

```json
{
  "active": true,
  "sub": "alice",
  "scope": "reports.read",
  "aud": "api://reports",
  "tenant": "acme",
  "app_roles": ["viewer"]
}
```

The delegate produces `SCOPE_reports.read`. The decorator's audience check passes and does not add `ROLE_ANALYST` because the analyst role is absent. Outcomes:

- `GET /api/reports` -> **200**, body `reports-for-alice`.
- `GET /api/analyst` -> **403**, because the token is valid but lacks `ROLE_ANALYST`.
- `GET /api/me` -> **200**, authorities list includes `SCOPE_reports.read`.

With `analyst-token`, introspection returns scope `reports.read`, `app_roles:["analyst"]`, and `tenant=acme`, so the decorator adds `ROLE_ANALYST` and both protected endpoints are permitted.

## 7. Integration Tests: MockWebServer for Real Introspection

This section **does not mock Authentication to bypass introspection**. It uses OkHttp's MockWebServer to serve a local test-controlled HTTP endpoint. The Resource Server calls that endpoint using Spring's real reactive client; HTTP rules are verified with `WebTestClient` against Netty on a random port.

**`src/test/java/example/opaquelab/OpaqueAuthoritiesIntegrationTest.java`:**

```java
package example.opaquelab;

import java.io.IOException;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Base64;

import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OpaqueAuthoritiesIntegrationTest {

    private static final String BASIC =
            "Basic " + Base64.getEncoder().encodeToString(
                    "resource-api:test-secret".getBytes(StandardCharsets.UTF_8));

    private static final MockWebServer IDP = startIdp();

    @DynamicPropertySource
    static void overrideIdp(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.security.oauth2.resourceserver.opaquetoken.introspection-uri",
                () -> IDP.url("/introspect").toString());
        registry.add(
                "spring.security.oauth2.resourceserver.opaquetoken.client-id",
                () -> "resource-api");
        registry.add(
                "spring.security.oauth2.resourceserver.opaquetoken.client-secret",
                () -> "test-secret");
    }

    @LocalServerPort int port;

    @Autowired
    ReactiveOpaqueTokenIntrospector introspector;

    private WebTestClient client;

    @BeforeEach
    void prepare() {
        client = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();
    }

    @AfterAll
    static void stopIdp() throws IOException {
        IDP.shutdown();
    }

    private static MockWebServer startIdp() {
        MockWebServer server = new MockWebServer();
        server.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                if (!"POST".equals(request.getMethod())
                        || !"/introspect".equals(request.getPath())) {
                    return new MockResponse().setResponseCode(404);
                }
                if (!BASIC.equals(request.getHeader("Authorization"))) {
                    return new MockResponse().setResponseCode(401);
                }

                String body = request.getBody().readUtf8();
                String token = Arrays.stream(body.split("&"))
                        .filter(part -> part.startsWith("token="))
                        .map(part -> URLDecoder.decode(
                                part.substring(6), StandardCharsets.UTF_8))
                        .findFirst().orElse("");

                return new MockResponse()
                        .setResponseCode(200)
                        .setHeader("Content-Type", "application/json")
                        .setBody(responseFor(token));
            }
        });

        try {
            server.start();
            return server;
        } catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private static String responseFor(String token) {
        return switch (token) {
            case "reader-token" -> """
                {
                  "active": true,
                  "sub": "alice",
                  "scope": "reports.read",
                  "aud": "api://reports",
                  "tenant": "acme",
                  "app_roles": ["viewer"]
                }
                """;
            case "analyst-token" -> """
                {
                  "active": true,
                  "sub": "ann",
                  "scope": "reports.read",
                  "aud": ["api://reports"],
                  "tenant": "acme",
                  "app_roles": ["analyst"]
                }
                """;
            case "spoof-role-token" -> """
                {
                  "active": true,
                  "sub": "bob",
                  "scope": "reports.read",
                  "aud": "api://reports",
                  "tenant": "acme",
                  "app_roles": ["ROLE_ANALYST", "admin"]
                }
                """;
            case "other-tenant-token" -> """
                {
                  "active": true,
                  "sub": "carol",
                  "scope": "reports.read",
                  "aud": "api://reports",
                  "tenant": "other",
                  "app_roles": ["analyst"]
                }
                """;
            case "write-only-token" -> """
                {
                  "active": true,
                  "sub": "dave",
                  "scope": "reports.write",
                  "aud": "api://reports",
                  "tenant": "acme",
                  "app_roles": ["viewer"]
                }
                """;
            case "wrong-audience-token" -> """
                {
                  "active": true,
                  "sub": "erin",
                  "scope": "reports.read",
                  "aud": "api://billing",
                  "tenant": "acme",
                  "app_roles": ["analyst"]
                }
                """;
            default -> """
                { "active": false }
                """;
        };
    }

    @Test
    void publicPingDoesNotNeedBearer() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void absentBearerTokenIs401() {
        client.get().uri("/api/reports")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void inactiveOpaqueTokenIs401() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBearerAuth("inactive-token"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerScopeAllowsReports() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBearerAuth("reader-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("reports-for-alice");
    }

    @Test
    void readerCannotAccessAnalystRoute() {
        client.get().uri("/api/analyst")
                .headers(h -> h.setBearerAuth("reader-token"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void analystRoleAllowsAnalystRoute() {
        client.get().uri("/api/analyst")
                .headers(h -> h.setBearerAuth("analyst-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("analyst-only");
    }

    @Test
    void analystStillHasOriginalScope() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBearerAuth("analyst-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("reports-for-ann");
    }

    @Test
    void attackerStyleRoleStringDoesNotUpgradeRole() {
        client.get().uri("/api/analyst")
                .headers(h -> h.setBearerAuth("spoof-role-token"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void otherTenantDoesNotReceiveAnalystRole() {
        client.get().uri("/api/analyst")
                .headers(h -> h.setBearerAuth("other-tenant-token"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void validTokenWithoutReadScopeReturns403() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBearerAuth("write-only-token"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void wrongAudienceIs401() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBearerAuth("wrong-audience-token"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void inspectorOutputContainsScopeAndMappedRole() {
        client.get().uri("/api/me")
                .headers(h -> h.setBearerAuth("analyst-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("ann")
                .jsonPath("$.authorities[0]").isEqualTo("ROLE_ANALYST")
                .jsonPath("$.authorities[1]").isEqualTo("SCOPE_reports.read")
                .jsonPath("$.tenant").isEqualTo("acme");
    }

    @Test
    void stepVerifierSeesMappedAuthoritiesAndAttributes() {
        StepVerifier.create(introspector.introspect("analyst-token"))
                .assertNext(principal -> {
                    assertEquals("ann", principal.getName());
                    assertEquals("acme",
                            principal.getAttribute("tenant"));
                    var names = principal.getAuthorities().stream()
                            .map(a -> a.getAuthority()).toList();
                    assertTrue(names.contains("SCOPE_reports.read"));
                    assertTrue(names.contains("ROLE_ANALYST"));
                })
                .verifyComplete();
    }

    @Test
    void stepVerifierRejectsWrongAudience() {
        StepVerifier.create(introspector.introspect(
                        "wrong-audience-token"))
                .expectError(OAuth2AuthenticationException.class)
                .verify();
    }
}
```

### 7.1. Why Is This Test Suite Trustworthy for Mapping?

MockWebServer starts on a dynamic port via `server.start()`. `@DynamicPropertySource` injects its URL into the introspector bean as soon as Spring Boot builds the `ApplicationContext`. Even though the test tokens are test-defined, **`SpringReactiveOpaqueTokenIntrospector` genuinely sends POST `/introspect`** via Spring's HTTP client and receives JSON just like an IdP.

- The test requires HTTP Basic `resource-api:test-secret` on the mock IdP; if the Resource Server lacks client credentials, the mock returns 401.
- `reader-token` is active with scope `reports.read` but without the analyst role.
- `analyst-token` is active with scope and analyst role, and its audience is a **list**, verifying the mapper handles multiple `aud` shapes.
- `spoof-role-token` tries injecting `ROLE_ANALYST` / `admin` strings in attributes; the allowlist grants no role.
- `other-tenant-token` has `app_roles:["analyst"]` but a tenant other than `acme`, so it receives no `ROLE_ANALYST`.
- `write-only-token` is active but only holds scope `reports.write`; the endpoint requires `reports.read` and returns 403.
- `wrong-audience-token` is active with the analyst role, yet targets the wrong Resource Server audience and gets **401 before authorization**.
- `inactive-token` returns `active:false` and is never treated by Spring as an authenticated principal.

**Do not mistake these tests for a production IdP:** the mock IdP does not issue tokens, perform real revocations, or exercise production network/TLS/certificates. The goal is to verify the **introspection response -> principal -> GrantedAuthority -> HTTP authorization** chain accurately.

### 7.2. Running the Tests

From the project directory containing the Gradle Wrapper:

```bash
./gradlew test --tests example.opaquelab.OpaqueAuthoritiesIntegrationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.opaquelab.OpaqueAuthoritiesIntegrationTest
```

If a compatible Gradle installation is available:

```bash
gradle test --tests example.opaquelab.OpaqueAuthoritiesIntegrationTest
```

**Expected outcome:** 14 passing tests given matching project setup, dependencies, Java runtime, and permission to bind a loopback port. This is an *expected result from code inspection*, **not an actual compile/test log** in the learner's workspace.

Test lifecycle note: `IDP` is a static `MockWebServer` shut down in `@AfterAll`; only this test class uses it, and it is not shared with longer-lived contexts. Tests are order-independent because the dispatcher returns immutable JSON per token name.

### 7.3. Limitations to Understand

- Uses loopback HTTP for introspection tests; production must use HTTPS and verify server certificates.
- Does not test timeouts, rate limits, caching, multiple instances, or token revocation against a real IdP.
- `SpringReactiveOpaqueTokenIntrospector` governs field and scope parsing per the 6.5 implementation; run actual tests against your exact dependency versions.
- All roles in the example are dummy names with a single `acme` tenant. Production requires domain policies, tenant-aware storage, auditing, and per-resource permissions.
- Do not use `mockOpaqueToken()` in this end-to-end introspection test because it bypasses the introspector; however, `mockOpaqueToken()` remains very useful when you **only want to unit-test authorization mappings** without networking.

## 8. Do Not Equate Introspection, Scopes, and Business Permissions

### Wrong Example of Record-Level Permissions

A token has:

```text
SCOPE_reports.read
ROLE_ANALYST
tenant = acme
sub = alice
```

This token **does not automatically permit** reading every tenant's or every user's reports. If the service runs:

```java
// Illustrative anti-pattern: missing tenant/owner check.
return reportRepository.findById(reportId);
```

IDOR can occur even when the token is active and both scope and role match.

A better design pulls the verified tenant/user from `Authentication` and pushes ownership filtering into the query:

```java
// Illustrative fragment; reportRepository must be defined in a real app.
return reportRepository.findByIdAndTenantId(reportId, authenticatedTenant)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.NOT_FOUND)));
```

This enforces data-level authorization inside the query, avoiding fetching the record first and comparing tenants afterward or leaking the existence of unauthorized resources.

**Do not confuse `tenant` with a role.** A tenant is a namespace isolating data/customers; a role is a capability within that namespace. `SCOPE_reports.read` may be granted between OAuth2 Client and Resource Server, while ownership must still be enforced at runtime.

### Service Method Security

In WebFlux, you can enable reactive method security and apply `@PreAuthorize("hasAuthority('SCOPE_reports.read')")` on services when appropriate. However, annotations do not filter tenant data in queries and require methods to return `Mono`/`Flux` under the Reactor Context contract without losing `SecurityContext` across threads.

Configuring WebFlux reactive method security differs from Servlet (use `@EnableReactiveMethodSecurity`). Test authorization at both the HTTP layer and service layer if both are configured.

## 9. How Can Incorrect Role Mapping Escalate Privileges?

### 9.1. Copying Arbitrary Role Strings

Wrong:

```java
// Anti-pattern: every roles value from the IdP is promoted to a Spring role.
for (String role : roles) {
    authorities.add(new SimpleGrantedAuthority("ROLE_" + role));
}
```

If clients control the role source or the IdP defines roles with different semantics, unintended privileges can be granted. Map **allowlisted values** into **explicit authorities**:

```java
if (roles.contains("analyst")
        && "acme".equals(tenant)) {
    authorities.add(new SimpleGrantedAuthority("ROLE_ANALYST"));
}
```

In production, also verify issuer/`client_id`/audience, tenant/resource policies, and trust boundaries. Never grant `ROLE_ADMIN` automatically from a plausible-looking string.

### 9.2. Dropping Scopes During Customization

Wrong:

```java
return new DefaultOAuth2AuthenticatedPrincipal(
        principal.getName(),
        principal.getAttributes(),
        List.of(new SimpleGrantedAuthority("ROLE_ANALYST")));
```

This **overwrites** existing scope authorities. As a result, `hasAuthority("SCOPE_reports.read")` fails even when the token holds the read scope. In the lab, the mapper initializes a `Set` from `principal.getAuthorities()` to preserve scopes before adding `ROLE_ANALYST` per policy.

### 9.3. Ignoring `active` or Assuming Scopes Alone Suffice

An inactive introspection response:

```json
{"active":false}
```

must never produce a principal with authorities. **Only code running after the delegate verifies the token may map scopes/roles.** Writing a custom introspector that returns a principal without checking `active` turns any Bearer token into an authenticated user.

### 9.4. Mixing User Roles and Client Identities

`client_credentials` can be a service-to-service token without a human Resource Owner `sub` like a user token. If code sees `client_id=reports-worker` and grants `ROLE_ANALYST` just like a human analyst, you risk a confused deputy or overly privileged service. Maintain distinct policies for service identities, scopes/audiences, and caller types.

### 9.5. Accepting an Unmatched `aud`

An active introspection response with scope `reports.read` yet `aud=api://billing` must not be used to call the reports API. The audience check in the decorator is intentional. Some Authorization Servers omit `aud`; in that case, establish an explicit contract for resource indicators, client binding, issuer/trust, and scope policy rather than **dropping audience validation by default when switching providers**.

## 10. 401, 403, and HTTP Flow in an Opaque Resource Server

| Request / Token | Introspection | Authorities | Outcome |
| --- | --- | --- | --- |
| No Bearer | No introspection needed | None | 401 on protected endpoint |
| Inactive Bearer token | `active=false` | No principal created | 401 |
| Active token, wrong audience | Verified active, rejected by decorator | No authorities granted | 401 |
| Active token, scope `reports.write` | Pass | `SCOPE_reports.write` | 403 when endpoint requires `reports.read` |
| Active token, `reports.read` | Pass | `SCOPE_reports.read` | 200 on `/api/reports` |
| Active token, analyst role per policy | Pass | `SCOPE_reports.read`, `ROLE_ANALYST` | 200 on `/api/analyst` |
| Active token, unallowlisted role string `"admin"` | Pass | Keeps scope, no `ROLE_ANALYST` | 403 on `/api/analyst` |
| Introspection timeout / down | Cannot verify token | No permissions granted | Reject; HTTP code per error handling |

Do not assume every introspection timeout **always** returns 401: if the exception surfaces through service error handling, the status may be 5xx depending on pipeline translation. The security invariant is **never returning protected data when the token cannot be verified**.

### Do Not Treat CORS as Token Protection

CORS applies to cross-origin browser JavaScript; cURL and server callers may omit `Origin`. The Resource Server must **always** validate Bearer tokens and authorities independently of CORS. If an API also uses session cookies/browser auth, evaluate CSRF for unsafe methods as well; sending opaque Bearer tokens via headers does not automatically eliminate all browser attack vectors.

## 11. Operations: Every Request May Trigger Introspection

### 11.1. Latency and Request Volume

With introspection, the Resource Server regularly **asks the Authorization Server about token state** instead of verifying JWT signatures locally offline. This helps when revocation tracking is needed, but creates a network dependency:

- Authorization Server latency increases API response times.
- Introspection endpoint downtime can cause valid requests to be rejected.
- High API request volume can overload the introspection service without caching or optimization layers.
- The IdP may enforce rate limits, timeouts, backpressure, and quotas.

Never write `block()` on the Reactor event loop when performing HTTP introspection. `SpringReactiveOpaqueTokenIntrospector` uses a reactive client; if you add custom enrichment to other APIs/DBs, compose with `Mono.flatMap` and bound concurrency.

### 11.2. Caching Introspection vs. Revocation

Caching can improve latency at the cost of staleness for `active`, audience/roles/scopes—especially when a token is revoked or a user loses permissions.

| Cache Configuration | Advantage | Risk |
| --- | --- | --- |
| No response caching | Checks current active state every introspection | Higher network dependency and latency |
| Short TTL cache | Reduces load and latency | Revoked tokens/permissions remain valid until TTL expires |
| Long TTL cache | High throughput | Large stale revocation window; role changes propagate slowly |
| Cache key missing context | Oversimplified wrongly | Mixes tokens/tenants/issuers, risking wrong privileges |

Set TTL according to the IdP's token revocation policy, token `exp`, auditing, and service-level risk. Never cache `active=true` indefinitely. If the cache key derives from the token, **never log or emit the raw token**; use a proper hash/HMAC for observability, and enforce isolation by issuer/client/tenant in the cache design.

### 11.3. Protecting Introspection Credentials

The Resource Server typically needs `client-id` and `client-secret` to authenticate to the introspection endpoint. These are **the API's credentials when calling the IdP**, distinct from the end user's inbound Bearer token.

- Never commit secrets to Git, sample configs, or READMEs.
- Store secrets in a secret manager/env with a rotation policy.
- Call only `https://...` endpoints with TLS certificate and hostname validation in production.
- Never write secrets into logs/traces and never return backend HTTP Basic headers to clients.
- When the provider supports stronger client authentication (mTLS/`private_key_jwt`), pick the mechanism matching IdP policy and the corresponding Spring APIs.
- Review outbound egress allowlists, DNS, and proxy security to prevent redirecting secrets to another host.

### 11.4. How to Further Validate `exp` / `aud` / `iss`?

In opaque introspection, the **Authorization Server is the source of truth for `active`**, yet the Resource Server's own policy requirements (API audience, tenant, issuer) must still be checked if the response supplies those fields. Never equate `"active=true"` with `"this token belongs to this API and has full permissions."`

Some IdPs return `aud` as a list, others as a string; agree on the format. If `iss` checks are mandatory, do not assume every provider returns `iss`. If `exp` is present and already past, align on a clear policy with the IdP; never grant permissions from claims unconfirmed by introspection. In production code, handle reasonable clock skew and `token_type`/client restrictions if required by contract.

### 11.5. Multi-Tenant, Multi-Issuer

If the Resource Server serves multiple tenants/issuers, do not use a single global `ROLE_ANALYST` while ignoring tenant context. Design the mapping:

- Establish the trust domain of the introspection endpoint and principal.
- Validate the exact audience/resource ID.
- Establish the verified tenant identity and bind the tenant to the resource.
- Restrict role mapping to the allowed namespace/tenant.
- With multiple IdPs, select resolvers/managers using an allowlisted configuration, **never using an arbitrary URL from the request** to call introspection (SSRF/credential leakage).
- Never allow callers to supply a `client_id` or introspection URL to inherit privileges from another provider.

## 12. Another Case: Introspecting JWTs as Well

How the Resource Server handles tokens depends on the **verification strategy**, not purely on token shape. A JWT access token can be sent to the **introspection endpoint** to check revocation rather than relying solely on local signature verification. Spring Security's opaque token support works with that strategy even when tokens look like JWTs.

However:

- Never use an **unverified** decoded JWT payload as the source for granting `GrantedAuthority`.
- An introspector can receive `active=true` and return attributes; treat those attributes as data from the trusted Authorization Server.
- If additional JWT claims are needed, either design explicit signature/claim validation or ensure introspection is authoritative and extra unverified data never elevates privileges beyond policy.
- Never copy a "parse-only JWT" snippet and accidentally turn unverified claims into `ROLE_ADMIN`.
- For offline JWT Resource Servers, `ReactiveJwtDecoder` and JWT validators are a separate mechanism from `ReactiveOpaqueTokenIntrospector`.

## 13. Common Pitfalls

| Mistake | Symptom | Fix |
| --- | --- | --- |
| Using Servlet `OpaqueTokenIntrospector` | Wrong reactive stack | Use `ReactiveOpaqueTokenIntrospector` |
| Wrong `opaquetoken` property | Boot fails to configure properly | Use `spring.security.oauth2.resourceserver.opaquetoken.*` |
| Introspection URI points to token endpoint | 401/404/parse error | Use the real RFC 7662 endpoint |
| Missing client-id/client-secret | IdP denies introspection | Configure client credentials from secret manager |
| `active=false` still builds a principal | Authentication bypass | Use trusted delegate, fail closed |
| Creating `SCOPE_` from query/header | Privilege escalation | Use verified introspection scopes only |
| Using `hasRole("reports.read")` | Wrong `ROLE_` comparison | Use `hasAuthority("SCOPE_reports.read")` |
| Using `hasAuthority("analyst")` when mapper yields `ROLE_ANALYST` | String mismatch | Use `hasRole("ANALYST")` or exact `ROLE_ANALYST` |
| Custom mapper drops default authorities | Scope routes return 403 | Start from `principal.getAuthorities()` |
| Blindly casting `app_roles` to `List<String>` | ClassCastException | Check `instanceof Collection<?>`, validate schema |
| Copying raw role names as `ROLE_*` | Overprivilege | Allowlist role values + context |
| Skipping audience validation | Token meant for another API works | Validate `aud` per resource policy |
| Skipping tenant check at database | IDOR, cross-tenant data | Enforce tenant/owner predicate in repository/service |
| Treating `client_id` as user name | Confused deputy | Distinguish service client vs. resource owner |
| Returning 200 fallback on introspection timeout | Fail-open vulnerability | Fail-closed error handling |
| Caching `active=true` too long | Revoked token retains access | Short policy-aligned TTL, invalidation |
| Keying cache by registrationId instead of token/principal | Identity mix-up | Complete cache key, isolation |
| Logging `Authorization: Bearer` | Access token exposure | Redact tokens and credentials |
| Public plain-HTTP introspection endpoint | MITM / credential theft | HTTPS + cert/hostname verification |
| Testing only with `mockOpaqueToken` | Real introspection calls untested | Add `MockWebServer` integration tests |
| Analyst role in another tenant gets `acme` access | Cross-tenant privilege | Tenant-aware mapping and data auth |
| Calling `block()` on Netty | Event loop blocked | Compose reactive `Mono`/`Flux` |
| Passing tokens in URLs | Token leaked via logs/history | Use `Authorization: Bearer` header |
| Returning all attributes to clients | IdP info leak | Minimize responses/PII |
| Confusing 401 and 403 | Hard to debug | Separate authentication vs. authorization |
| Disabling all security due to introspection 5xx | Bypasses token validation | Fix endpoint/TLS/client auth/timeouts |

## 14. Review Checklist and Exercises

### Production Checklist

1. Resource Server uses WebFlux, `SecurityWebFilterChain`, and `ReactiveOpaqueTokenIntrospector` without mixing Servlet APIs.
2. Trusted HTTPS introspection endpoint, with client credentials in a secret manager.
3. `active=false`, token errors, and network errors **never grant access**.
4. Default scope mapping is preserved or intentionally modified; `SCOPE_...` is tested.
5. Role mapping reads only verified attributes, strictly allowlisting roles and tenants.
6. Audience/resource/client restrictions are checked per the IdP contract.
7. `Authentication.getName()`/`sub` behavior is clearly defined for both user tokens and service tokens.
8. Scopes at HTTP and owner/tenant/resource checks at service/DB are thoroughly enforced.
9. Tokens and secrets never appear in logs, URLs, or public JSON.
10. Introspection timeouts, rate limits, caching, revocation, and key isolation are monitored.
11. Negative tests: missing bearer, inactive, wrong aud, missing scope, spoofed role, wrong tenant, 401/403.
12. Test actual HTTP introspection and client authentication, not only `mockUser`/`mockOpaqueToken`.
13. Never send tokens/secrets to arbitrary user-specified IdP endpoints.
14. Audit elevated privileges (admin/analyst), enforcing deny-by-default and least privilege.
15. Expand test coverage when method security, multiple chains, or multi-tenancy are present.

### Exercises

1. Given `scope="reports.read reports.write"`, list the two default authorities and write the matching `hasAuthority` expressions.
2. Explain why `hasRole("ANALYST")` is not satisfied by scope `reports.read` alone.
3. Add role `reviewer` to the allowlist per the IdP contract, mapping it to `ROLE_REVIEWER` only for tenant `acme`.
4. Try removing `new LinkedHashSet<>(principal.getAuthorities())` and run the tests: why does `SCOPE_reports.read` disappear?
5. Add a token with `active=false` that still includes `scope:reports.admin`: ensure 401 is returned.
6. Change `aud` to `api://billing`: why is the active token still rejected?
7. Test `app_roles:["ROLE_ANALYST"]` and explain why the mapper does not grant `ROLE_ANALYST`.
8. Convert the app to multi-tenant by updating the mapping to verify tenant per resource instead of hardcoding one tenant.
9. Add a `WebTestClient` test for `/api/me` without a token and assert 401.
10. Use `StepVerifier` directly on the introspector to assert that metadata still preserves `sub` and `tenant`.
11. Simulate IdP timeout/500 with `MockWebServer`, verifying fail-closed behavior and that the controller is not invoked.
12. Evaluate cache TTL options against token revocation requirements (30 seconds, 5 minutes, no cache) and their availability impact.
13. Compare `ReactiveOpaqueTokenIntrospector` with `ReactiveJwtDecoder`: when are network calls, signatures, and revocation checks needed?
14. Add a resource-ID endpoint querying `findByIdAndTenantId` to prevent IDOR.
15. Compare testing with `mockOpaqueToken()` alone vs. the `MockWebServer` integration test in this lesson: which test verifies calling the introspection endpoint?

## Summary

**Spring Security WebFlux Resource Server Opaque** authenticates Bearer tokens via `ReactiveOpaqueTokenIntrospector`. When the Authorization Server returns an active token with scopes, Spring converts each scope into `SCOPE_<scope>` and places those authorities on `OAuth2AuthenticatedPrincipal` / `BearerTokenAuthentication`. Fields such as `tenant` or `app_roles` **do not automatically become roles**.

To add roles, use a **decorator** wrapping the real introspector, **preserve default authorities**, validate audience/tenant/schema on trusted attributes, and map only allowlisted roles. `hasAuthority("SCOPE_reports.read")` and `hasRole("ANALYST")` enforce distinct policies; neither replaces resource owner/tenant checks.

When introspection fails or a token is inactive, **grant no access**. In production, add HTTPS, credential management, caching/revocation/timeout controls, monitoring, and negative tests.

## Official References

- [Spring Security 6.5 — Reactive OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security 6.5 — OAuth2 WebFlux Overview](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html)
- [Spring Security — ReactiveOpaqueTokenIntrospector Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html)
- [Spring Security — SpringReactiveOpaqueTokenIntrospector Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html)
- [Spring Security — OAuth2AuthenticatedPrincipal Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/core/OAuth2AuthenticatedPrincipal.html)
- [Spring Security — DefaultOAuth2AuthenticatedPrincipal Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/core/user/DefaultOAuth2AuthenticatedPrincipal.html)
- [Spring Security — BearerTokenAuthentication Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/BearerTokenAuthentication.html)
- [Spring Security — Reactive Web Test Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Boot 3.5 — Spring Security for Reactive Web](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
