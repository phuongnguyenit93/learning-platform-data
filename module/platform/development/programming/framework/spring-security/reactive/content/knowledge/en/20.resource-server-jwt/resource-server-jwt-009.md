# Reading Jwt, Claims, and Principal in Controllers or Services — Spring Security WebFlux Resource Server

## Learning Objectives

This lesson belongs to **Resource Server JWT** in the **Spring Security - reactive** module. After a client sends `Authorization: Bearer <access-token>`, Spring Security WebFlux must **verify the JWT first** before passing authentication data into the HTTP processing flow. In controllers or services, we often need the subject (`sub`), tenant, scopes/authorities, business claims, and the principal's identity to enforce data access permissions.

There are two approaches suited to two different layers:

- **WebFlux Controller:** inject `@AuthenticationPrincipal Jwt jwt` when the endpoint serves JWT-authenticated users and only needs to read a few fields.
- **Reactive Service:** use `ReactiveSecurityContextHolder.getContext()` inside a `Mono`/`Flux` publisher, verify `Authentication` is of the expected type, and extract `JwtAuthenticationToken.getToken()`, or explicitly pass a verified identity object from the controller down to the service.

**Do not** use Servlet's `ThreadLocal`-based `SecurityContextHolder.getContext()` to guess the principal in WebFlux. **Do not** Base64-decode raw JWTs and trust claims yourself. **Do not** return the entire JWT, all claims, or the raw token value to the client.

After this lesson you can:

1. Describe the flow from the Bearer header through `AuthenticationWebFilter`, `ReactiveJwtDecoder`, `JwtAuthenticationToken`, Reactor Context, and into controllers/services.
2. Distinguish `Jwt` (decoded/validated token), `JwtAuthenticationToken` (Authentication), `Authentication.getPrincipal()`, and `Authentication.getName()`.
3. Read `sub`, `iss`, `aud`, `exp`, `iat`, `nbf`, `scope`/`scp`, and custom claims like `tenant_id` using appropriately typed APIs.
4. Understand how `getClaimAsString`, `getClaimAsStringList`, `getClaimAsMap`, `getClaimAsInstant`, `getAudience`, and `getSubject` behave when claims are missing or mismatched in type.
5. Use `@AuthenticationPrincipal Jwt` in annotated controllers, and `ReactiveSecurityContextHolder`/`JwtAuthenticationToken` in services with lazy publishers.
6. Distinguish **raw claims** from **GrantedAuthority**; by default scopes become `SCOPE_<scope>`, while roles/tenants exist only when converters/policies define them.
7. Build a **Java 17+, Spring Boot 3.3.13, WebFlux + Spring Security Resource Server** app with user info and order ownership endpoints.
8. Use `WebTestClient` and `mockJwt()` to test controllers, services, scopes, and tenants; use `StepVerifier` to prove Reactor Context behavior, understanding that mocks do **not** verify JWT signatures.
9. Recognize missing/expired/invalid JWT → 401, valid identity missing scope/tenant → 403, and resource not owned by caller → 404 per demo policy.
10. Check issuer, audience, timestamps, key rotation, claim mapping, machine-token vs. user-token, token forwarding, and multi-tenant isolation before production.

## 1. Overview: Reading Jwt **After** Authentication

An API request typically arrives as:

```http
GET /api/me HTTP/1.1
Host: localhost:8080
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

The token snippet in the example is only an illustrative prefix, not a valid token. The Resource Server performs:

```text
Browser / Service client
         |
         | Authorization: Bearer <JWT access token>
         v
WebFlux WebFilter chain
         |
         v
Spring Security WebFilterChainProxy
         |
         v
AuthenticationWebFilter / Bearer-token resolver
         |
         v
ReactiveAuthenticationManager
         |
         +-> ReactiveJwtDecoder
         |     - parse JOSE/JWT
         |     - verify signature using JWK / trusted public key
         |     - validate exp, nbf, iss per configuration
         |     - validate aud when app configures matching validator
         |
         v
Jwt -> JwtAuthenticationToken (principal = Jwt)
         |
         v
SecurityContext inside Reactor Context
         |
         v
AuthorizationWebFilter (scope/authority)
         |
         v
DispatcherHandler -> @RestController
         |
         +-> @AuthenticationPrincipal Jwt jwt
         |
         +-> Service -> ReactiveSecurityContextHolder.getContext()
                          -> Authentication
                          -> JwtAuthenticationToken.getToken()
```

**Security invariant:** Without a valid `ReactiveJwtDecoder` verifying signature/issuer/time/audience per policy, “reading `sub`/`tenant_id`” does not establish a trusted identity. A JWT is data **signed by someone**, not automatically a token intended for your API.

### 1.1. Right Class, Right Role

| Component | Java type | What it represents |
| --- | --- | --- |
| Bearer header | `String` | Client-sent credential; **untrusted** |
| `Jwt` | `org.springframework.security.oauth2.jwt.Jwt` | Claims/JOSE headers of a JWT after passing the decoder in the resource server flow |
| `JwtAuthenticationToken` | `org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken` | Authentication holding `Jwt` and authorities |
| `Authentication.getPrincipal()` | `Object` | Defaults to `Jwt` upon successful bearer JWT auth; changeable via custom converter |
| `Authentication.getName()` | `String` | Defaults to `sub`, though configurable |
| `GrantedAuthority` | `String getAuthority()` | Permission produced by converter/security, e.g., `SCOPE_orders:read` |
| `SecurityContext` | Spring Security context | Holds Authentication of the current subscriber |
| `ReactiveSecurityContextHolder` | Reactive API | Reads SecurityContext via **Reactor Context**, not ThreadLocal |
| `@AuthenticationPrincipal` | Annotation | Injects principal directly into controller methods in the right scope |

**Avoid confusion:** Java's `Principal` may only expose `getName()`; it is not equivalent to the full `Jwt`. `JwtAuthenticationToken` is an `Authentication` exposing `getToken()` and `getTokenAttributes()`. If you only need `sub`, use name/principal consistently; if you need verified JWT claims, retrieve the token via the appropriate API.

### 1.2. Resource Server Is Not OAuth2 Client

- **Resource Server:** accepts Bearer tokens, verifies them, and protects endpoints.
- **OAuth2 Client / OAuth2 Login:** initiates sign-in, exchanges codes/refresh tokens with the Authorization Server, and may store `OAuth2AuthorizedClient`.
- **Authorization Server:** issues and signs tokens.

Adding `spring-boot-starter-oauth2-resource-server` does **not** add an OAuth2 login page or Token Endpoint. Conversely, `@AuthenticationPrincipal OidcUser` is for session-based OIDC Login, **not** the default for a JWT Resource Server API.

## 2. What Parts Make Up a Jwt?

A JWT (JSON Web Token) is normally a three-part Base64URL string:

```text
BASE64URL(JOSE header).BASE64URL(claims payload).BASE64URL(signature)
```

Example JOSE header:

```json
{
  "alg": "RS256",
  "kid": "key-2026-01",
  "typ": "JWT"
}
```

Illustrative claims payload:

```json
{
  "iss": "https://login.example.test/realms/learning",
  "sub": "subject-7",
  "aud": ["orders-api"],
  "exp": 1794086400,
  "iat": 1794082800,
  "nbf": 1794082800,
  "scope": "orders:read profile",
  "tenant_id": "tenant-a",
  "preferred_username": "alice"
}
```

Timestamps here are illustrative numbers, not a valid token. **JWT payloads are trivial to decode** and are not encrypted for confidentiality in standard JWS. Never put passwords, secrets, or excessive sensitive data into claims.

### 2.1. Standard Claims

| Claim | Meaning | Reading API |
| --- | --- | --- |
| `iss` | Issuer that minted the token | `jwt.getIssuer()` or `jwt.getClaimAsString("iss")` |
| `sub` | Subject within the issuer scope | `jwt.getSubject()` |
| `aud` | Intended audience of the token | `jwt.getAudience()` |
| `exp` | Expiration timestamp | `jwt.getExpiresAt()` |
| `iat` | Issued-at | `jwt.getIssuedAt()` |
| `nbf` | Not-before | `jwt.getNotBefore()` |
| `jti` | JWT ID, when provided by issuer | `jwt.getId()` |
| `scope` | Scopes, usually space-delimited string | `jwt.getClaimAsString("scope")`; converter builds authorities |
| `scp` | Scopes, potentially a list | `jwt.getClaimAsStringList("scp")` if schema is a list |
| `tenant_id` | Business claim, **not standard OAuth2** | `jwt.getClaimAsString("tenant_id")` if provider schema agrees |
| `preferred_username` | Display username, may change | `jwt.getClaimAsString("preferred_username")` |

**Do not do:** `jwt.getClaimAsString("aud").split(",")` to parse audience. `aud` can be a list; use `getAudience()`. For space-delimited `scope` strings, rely on the converter or split strictly per contract rather than assuming every provider sends the same format.

### 2.2. Missing Claims and Type Mismatches

Claim getters can return `null` when absent, and some conversions throw exceptions if the value cannot be converted. Therefore:

```java
String tenant = jwt.getClaimAsString("tenant_id");
if (tenant == null || tenant.isBlank()) {
    // fail-closed if this data is mandatory for authorization
}
```

**Never** call `Map.of("tenant", jwt.getClaimAsString("tenant_id"))` when the claim can be null: `Map.of` forbids null values and throws `NullPointerException`. In display DTOs, optional/null fields are fine for presentation; for authorization, missing required claims should be rejected.

### 2.3. Do Not Use Display-Name Claims as Identity Keys

`preferred_username`/`email` can change or collide across issuers/tenants. `sub` is generally the stable subject key within an **issuer** scope. With multiple IdPs, use the `(iss, sub)` pair or map to an internal user ID; never rely on `sub` alone globally if tokens arrive from multiple issuers.

For machine-to-machine `client_credentials`, `sub` may represent a **service account** rather than a human user. A `/me` endpoint displaying principal info can still work, but “my orders” business logic must not blindly treat a machine as a human user. Distinguish user tokens from service tokens by issuance policy, audience, scopes, and trusted source.

## 3. @AuthenticationPrincipal Jwt in Controllers

The most concise approach for annotated controllers:

```java
@RestController
class MeController {

    @GetMapping("/api/me")
    public MeResponse me(@AuthenticationPrincipal Jwt jwt) {
        return new MeResponse(
                jwt.getSubject(),
                jwt.getClaimAsString("preferred_username"));
    }

    record MeResponse(String subject, String displayName) {}
}
```

This is an **illustrative fragment**, not a full runnable class (needs imports). Spring Security WebFlux resolves `@AuthenticationPrincipal` from the principal in the request's Authentication. When using the JWT resource server with its default converter, the principal is `Jwt`.

**Limitations to remember:**

- The route **must be protected** with appropriate authentication; on `permitAll` routes with anonymous requests, the parameter may be null.
- If a custom principal converter returns an object other than `Jwt`, `@AuthenticationPrincipal Jwt` will not receive the expected type. Test the actual security configuration.
- Controllers use the **decoder-verified** `Jwt`, never manually Base64-parsing the Bearer header.
- `@AuthenticationPrincipal` only retrieves the principal; it performs no ownership authorization. An authenticated user can still be forbidden from another user's resource.
- For methods performing trivial CPU work to build a DTO, returning a POJO is fine; when doing reactive I/O, return `Mono`/`Flux` and never `block()`.
- Never return `jwt.getTokenValue()` or the entire `jwt.getClaims()` to clients.

### 3.1. Extract Only Needed Claims

Example:

```java
@GetMapping("/api/profile")
public Mono<ProfileDto> profile(@AuthenticationPrincipal Jwt jwt) {
    String subject = jwt.getSubject();
    String username = jwt.getClaimAsString("preferred_username");

    return Mono.just(new ProfileDto(
            subject,
            username == null ? "" : username));
}
```

This is a code fragment needing `ProfileDto`. Returning an empty string if username is absent is an API **display** choice, not permission for a missing user ID. For authorization, verify subject is non-blank.

### 3.2. Retrieving Authentication or JwtAuthenticationToken

If you need authorities alongside the token, one option is service-level `ReactiveSecurityContextHolder`. In controllers, WebFlux supports injecting principal/authentication; however, never mix `Principal`, `Authentication`, `Jwt`, and `JwtAuthenticationToken` without runtime type checks.

Recall:
- `JwtAuthenticationToken.getToken()` returns `Jwt`.
- `JwtAuthenticationToken.getName()` defaults to subject or whichever claim the converter configured.
- `JwtAuthenticationToken.getAuthorities()` holds permissions mapped into Authentication.
- `Jwt.getClaims()` are raw claims, not vetted security roles.

## 4. ReactiveSecurityContextHolder in Services

In WebFlux, Reactor publishers can hop across threads/schedulers. `SecurityContext` is held in the **Reactor Context** attached to the subscription, not a global `ThreadLocal` variable.

How to read it:

```java
public Mono<String> currentSubject() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
}
```

This snippet illustrates reading the name, but is **insufficient** if the service strictly requires a JWT access token carrying a tenant claim: Authentication could be Basic/form or anonymous in another flow. In critical services, check the Authentication type, `isAuthenticated()`, and mandatory claims before proceeding.

### 4.1. A Proper Fail-Closed Pattern

```java
public Mono<Identity> requireJwtIdentity() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .switchIfEmpty(Mono.error(
                    new AccessDeniedException("Missing authentication")))
            .flatMap(authentication -> {
                if (!(authentication instanceof JwtAuthenticationToken token)
                        || !authentication.isAuthenticated()) {
                    return Mono.error(new AccessDeniedException(
                            "JWT authentication required"));
                }

                Jwt jwt = token.getToken();
                String subject = jwt.getSubject();
                String tenant = jwt.getClaimAsString("tenant_id");

                if (subject == null || subject.isBlank()
                        || tenant == null || tenant.isBlank()) {
                    return Mono.error(new AccessDeniedException(
                            "Required identity claims missing"));
                }

                return Mono.just(new Identity(subject, tenant));
            });
}
```

This fragment requires imports, an `Identity` record, and a service class. It demonstrates:

- No `block()`.
- No manual `subscribe()`.
- If `SecurityContext` is missing, emits `Mono.error` instead of continuing.
- If `Authentication` is not a JWT, rejects instead of blindly casting.
- Reads `sub` and `tenant_id` only after the token was verified in the HTTP resource-server flow.
- Missing subject/tenant triggers an authorization error rather than falling back to querying all tenants.
- Returns a minimal domain identity only once all required fields are present.

### 4.2. Why Not Use ThreadLocal SecurityContextHolder?

Wrong example in WebFlux:

```java
// WRONG or unreliable inside a reactive flow.
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
```

Servlet Spring Security propagates context via `ThreadLocal` for thread-per-request execution. WebFlux/Reactor switches threads and uses event loops and schedulers. `SecurityContextHolder` can return null, stale context, or fail to reflect the current subscriber.

Better:

```java
return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
```

In a reactive chain, context is normally populated by Spring Security's `ReactorContextWebFilter`/security integration and propagated across Reactor operators unless subscriptions are improperly detached.

### 4.3. Context Lost When Working Outside the Subscriber

Watch out for:

- Calling `subscribe()` manually inside a service and returning `Mono.empty()`; the sub-flow has its own lifecycle/context.
- Creating a `Mono` and caching/sharing it globally across users; can leak data if cached values depend on principal.
- Offloading to `CompletableFuture`/callback APIs that drop context, then trying to read `ThreadLocal`.
- Storing the “current request's” Authentication in a static field.
- Using `Context.of(...)` replacing the entire Reactor Context when merging is needed.
- Calling `block()` on the event loop and stalling WebFlux requests.

With standard Reactor operators like `flatMap`, `concatMap`, and `publishOn`, context follows the subscription per Reactor rules. When crossing into external async libraries, use explicit context propagation or pass a plain `Identity` value object as a method argument.

### 4.4. Passing Identity Explicitly Is Also a Clean Option

A pure business service can expose:

```java
Mono<Order> readOrder(String id, Identity caller);
```

The controller or application boundary constructs `Identity` from the validated JWT and passes it to the service. This simplifies unit testing and avoids coupling every service to Spring Security. Still, ensure `Identity` is **built exclusively from trusted verified sources** and never directly from client-editable request bodies/headers.

## 5. Claims Differ from GrantedAuthority

A JWT might contain:

```json
{
  "scope": "orders:read orders:write",
  "tenant_id": "tenant-a",
  "roles": ["viewer"]
}
```

In default Spring Security JWT resource server config, `scope` or `scp` typically maps to authorities:

```text
SCOPE_orders:read
SCOPE_orders:write
```

However, `roles: ["viewer"]` does **not automatically** become `ROLE_viewer` without a matching mapper. Likewise, `tenant_id` does not automatically filter SQL queries by tenant.

| Data | Where it appears | Enough to authorize? |
| --- | --- | --- |
| `jwt.getClaimAsString("scope")` | Raw claim string | Does not replace converter/security results |
| `authentication.getAuthorities()` | `GrantedAuthority` collection | Can be used for mapped scopes/roles |
| `jwt.getClaimAsString("tenant_id")` | Business claim | Must check issuer/audience, type, and record ownership |
| `jwt.getSubject()` | User/service subject | Identifies who; does not grant access to any record |
| `authentication.getName()` | Configured principal name | Not guaranteed to match sub/email with custom converters |
| `jwt.getTokenValue()` | Raw bearer credential | Never use as user ID; never log or return in responses |

### 5.1. Multi-Layer Authorization Path

```text
GET /api/orders/A-100
  |
  v
Spring Security:
  Bearer token valid?
  -> scope/authorities contain SCOPE_orders:read?
  |
  v
OrderService:
  subject, tenant_id valid?
  -> query only records matching tenant and owner?
  |
  v
200 (right owner)
404 or 403 (unauthorized, per response policy)
```

**Having `SCOPE_orders:read` alone is not enough** to read every user's orders. Scopes permit **types of operations**; ownership + tenant protect **specific data objects**. A token with `tenant_id=tenant-a` must still be rejected if requesting a record belonging to `tenant-b`.

### 5.2. Warning About Custom Roles

If a provider uses `realm_access.roles` or `resource_access.{client}.roles` (common in some IdPs), never cast raw `Map<String,Object>` without type checks and treat them as `ROLE_*`. Use a tested converter, issuer/audience validation, and a controlled role mapping policy. **Access token** role claims differ from ID tokens and may be absent depending on provider/client scopes.

In WebFlux, the DSL supports:

```java
.oauth2ResourceServer(oauth2 -> oauth2
        .jwt(jwt -> jwt
                .jwtAuthenticationConverter(
                        reactiveConverter)))
```

Here `reactiveConverter` must be an appropriate `Converter<Jwt, Mono<AbstractAuthenticationToken>>`. A synchronous `JwtAuthenticationConverter` with an authorities mapper can be wrapped with `ReactiveJwtAuthenticationConverterAdapter`. **This is an illustrative snippet**, not a variable present in the runnable project below.

## 6. Runnable Project: Java 17+, Spring Boot 3.3.13, WebFlux JWT

The goal is a **real** Resource Server application configured with `issuer-uri` and these endpoints:

| Endpoint | Rule | Behavior |
| --- | --- | --- |
| `GET /public/ping` | permitAll | Health check, requires no JWT |
| `GET /api/me` | authenticated JWT | Reads `Jwt` in controller via `@AuthenticationPrincipal` and returns only three fields |
| `GET /api/context` | authenticated JWT | Reads `SecurityContext` in service; requires `sub` + `tenant_id` |
| `GET /api/orders/{id}` | `SCOPE_orders:read` | Reads subject/tenant in service; returns only owner's order |
| Other URLs/methods | denyAll | Closed by default |

**Structure:**

```text
webflux-jwt-principal/
  settings.gradle
  build.gradle
  src/
    main/
      resources/application.yml
      java/example/
        JwtPrincipalApplication.java
        SecurityConfig.java
        IdentityController.java
        CurrentJwtService.java
        OrderService.java
        OrdersController.java
    test/
      java/example/
        JwtPrincipalApplicationTests.java
        CurrentJwtServiceTests.java
```

The example uses an in-memory `Map` solely to illustrate ownership, not as a production repository. With R2DBC/DB, **put `tenant` + `owner` into the query's WHERE clause** rather than loading another tenant's record and filtering afterward, and enforce policy on every update operation.

### 6.1. settings.gradle

```groovy
rootProject.name = 'webflux-jwt-principal'
```

### 6.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Note:** The Boot OAuth2 Resource Server starter supplies required dependencies, including JWT/JOSE support. Do not mix in `spring-boot-starter-web` (Servlet MVC) when targeting Netty/WebFlux. The Spring Boot BOM manages compatible Spring Security, Reactor, and Nimbus versions.

### 6.3. application.yml

Create `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: http://localhost:9090/realms/learning
```

This is a **localhost HTTP demo issuer**, not for production. When deploying, use an HTTPS issuer from a real IdP:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/learning
```

If local Keycloak is not running, `mockJwt()` tests need no real JWT yet still initialize the Spring test context. In standard Boot/Spring Security setups, resource server discovery can be deferred until the first JWT request; however, eager custom decoder beans or version changes may require the IdP during context initialization. Do not treat mock tests as proof that the IdP is up.

### 6.4. JwtPrincipalApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JwtPrincipalApplication {

    public static void main(String[] args) {
        SpringApplication.run(JwtPrincipalApplication.class, args);
    }
}
```

### 6.5. SecurityConfig.java

```java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(
                                HttpMethod.GET, "/public/ping")
                        .permitAll()
                        .pathMatchers(
                                HttpMethod.GET, "/api/me", "/api/context")
                        .authenticated()
                        .pathMatchers(
                                HttpMethod.GET, "/api/orders/**")
                        .hasAuthority("SCOPE_orders:read")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(withDefaults()))
                .build();
    }
}
```

**Explanation:**

- `@EnableWebFluxSecurity` enables WebFlux Security (not Servlet's `@EnableWebSecurity`).
- `oauth2ResourceServer(o -> o.jwt(...))` requires Bearer JWTs for protected routes.
- `GET /public/ping` is `permitAll`.
- `GET /api/me` and `GET /api/context` require Authentication; the service further checks JWT type and claims.
- `GET /api/orders/**` requires `SCOPE_orders:read`.
- `anyExchange().denyAll()` blocks unintended routes/methods.
- 401/403 are handled by Spring Security following the HTTP security flow; never write an `@ExceptionHandler(Exception.class)` turning all errors into 200.
- HTTP Basic and form login are **not** enabled; default authentication here is Bearer resource-server.
- The example has no POST/PUT/DELETE; when building state-changing APIs, evaluate CSRF according to credential delivery (Bearer header vs. cookies/sessions) instead of disabling it unconditionally.
- Route patterns must be tested when reverse proxies, path prefixes, or multiple `SecurityWebFilterChain`s are involved.

### 6.6. IdentityController.java: Reading Jwt in Controller

```java
package example;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    private final CurrentJwtService currentJwtService;

    public IdentityController(CurrentJwtService currentJwtService) {
        this.currentJwtService = currentJwtService;
    }

    @GetMapping("/public/ping")
    public Map<String, String> ping() {
        return Map.of("message", "PONG");
    }

    @GetMapping("/api/me")
    public JwtView me(@AuthenticationPrincipal Jwt jwt) {
        // jwt is provided by Spring Security AFTER decoder validation.
        String username = jwt.getClaimAsString("preferred_username");
        String tenant = jwt.getClaimAsString("tenant_id");

        return new JwtView(
                jwt.getSubject(),
                username == null ? "" : username,
                tenant == null ? "" : tenant);
    }

    @GetMapping("/api/context")
    public reactor.core.publisher.Mono<CurrentJwtService.Identity> context() {
        // Does not pass raw token; service reads Reactor Context.
        return currentJwtService.requireIdentity();
    }

    public record JwtView(
            String subject,
            String preferredUsername,
            String tenantId) {
    }
}
```

**Core points:**

1. `@AuthenticationPrincipal Jwt jwt` extracts the principal from the validated JWT request's `SecurityContext`.
2. `getSubject()` reads `sub`. `preferred_username` is display-only; do not use it as an immutable user key.
3. Missing `tenant_id` is represented as an empty string on the **display endpoint** `/api/me`, whereas `/api/context` rejects when that claim is required.
4. Response bodies **never** contain `jwt.getTokenValue()`, JOSE signatures, raw claims, email/phone, or credentials.
5. `/api/context` returns `Mono` and reads authentication in the service, never using thread-locals.
6. Never wrap `currentJwtService.requireIdentity().block()` in the controller.
7. Java 17 record DTOs are a clean choice for stable API responses.
8. If the app customizes the principal to an object other than `Jwt`, adjust the annotation to match the converter; never cast blindly.
9. On `permitAll` endpoints, an annotated principal parameter can be null if the request has no JWT; protected endpoints in this example avoid that.

### 6.7. CurrentJwtService.java: Reading JWT in a Reactive Service

```java
package example;

import java.util.List;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationToken;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class CurrentJwtService {

    public Mono<Identity> requireIdentity() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .switchIfEmpty(Mono.error(new AccessDeniedException(
                        "Missing authentication context")))
                .flatMap(authentication -> {
                    if (!(authentication instanceof JwtAuthenticationToken token)
                            || !authentication.isAuthenticated()) {
                        return Mono.error(new AccessDeniedException(
                                "JWT authentication required"));
                    }

                    Jwt jwt = token.getToken();

                    String subject = jwt.getSubject();
                    String tenant = jwt.getClaimAsString("tenant_id");

                    if (subject == null || subject.isBlank()
                            || tenant == null || tenant.isBlank()) {
                        return Mono.error(new AccessDeniedException(
                                "Missing subject or tenant claim"));
                    }

                    List<String> authorities = authentication
                            .getAuthorities().stream()
                            .map(GrantedAuthority::getAuthority)
                            .sorted()
                            .toList();

                    return Mono.just(new Identity(
                            subject, tenant, authorities));
                });
    }

    public record Identity(
            String subject,
            String tenantId,
            List<String> authorities) {
    }
}
```

**Step-by-step explanation:**

- `ReactiveSecurityContextHolder.getContext()` returns `Mono<SecurityContext>`, reading from no static/global variable.
- `map(SecurityContext::getAuthentication)` retrieves the Authentication of the **current subscription**.
- `switchIfEmpty(Mono.error(...))` fails closed if context is absent.
- `instanceof JwtAuthenticationToken token` uses Java 17 pattern matching, preventing `ClassCastException` when callers use another authentication type.
- `token.getToken()` returns the `Jwt` verified by the decoder through the HTTP resource server.
- `sub`/`tenant_id` are mandatory claims for this example's business behavior; missing them yields 403 when an authenticated caller triggers `AccessDeniedException` handled by security.
- Authorities come from `authentication.getAuthorities()` via the converter, not from splitting raw `scope` arbitrarily.
- `Identity` is minimized: no raw access token, full claims, or email.
- No `block()`, no `subscribe()`, never treating `Mono.empty()` as “permission granted”.
- If a pure business service should not depend on Security APIs, pass `Identity` as a parameter from the verified application boundary.

**Why does the service still check JWT even when the URL is already authenticated?** Because one day a Basic/form/opaque-token chain might be added, or the service might be called from a background job or test. Failing closed prevents silently accepting another principal type.

### 6.8. OrderService.java: Protecting Tenant + Owner

```java
package example;

import java.util.Map;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderService {

    private final CurrentJwtService currentJwtService;

    private final Map<String, StoredOrder> data = Map.of(
            "A-100", new StoredOrder(
                    "A-100", "tenant-a", "subject-7", "READY"),
            "A-101", new StoredOrder(
                    "A-101", "tenant-a", "subject-8", "PAID"),
            "B-200", new StoredOrder(
                    "B-200", "tenant-b", "subject-7", "PENDING")
    );

    public OrderService(CurrentJwtService currentJwtService) {
        this.currentJwtService = currentJwtService;
    }

    public Mono<OrderView> readOwned(String orderId) {
        return currentJwtService.requireIdentity()
                .flatMap(identity ->
                        Mono.justOrEmpty(data.get(orderId))
                                .filter(order ->
                                        order.tenantId()
                                                .equals(identity.tenantId())
                                        && order.ownerSubject()
                                                .equals(identity.subject()))
                                .map(order -> new OrderView(
                                        order.id(), order.status())));
    }

    private record StoredOrder(
            String id,
            String tenantId,
            String ownerSubject,
            String status) {
    }

    public record OrderView(String id, String status) {
    }
}
```

This is an **in-memory demo** without a database connection, kept brief so learners can focus on JWT/claims/principal. In production you need:

```sql
SELECT id, status
FROM orders
WHERE id = :orderId
  AND tenant_id = :verifiedTenantId
  AND owner_subject = :verifiedSubject;
```

These SQL placeholders are **bind parameters**—never concatenate strings from requests/JWTs into SQL. With R2DBC, run reactive queries keeping tenant/owner inside the `WHERE` clause; never load another tenant's record and filter afterward to avoid data leaks or TOCTOU issues.

In the demo, a token for `subject-7` in `tenant-a` can read `A-100`, cannot read `A-101` (different owner), and cannot read `B-200` (different tenant). The same subject string in `tenant-b` does not imply shared privileges. The endpoint returns 404 for non-existent or unauthorized records to reduce existence probing.

### 6.9. OrdersController.java

```java
package example;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
public class OrdersController {

    private final OrderService orders;

    public OrdersController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/api/orders/{id}")
    public Mono<OrderService.OrderView> get(@PathVariable String id) {
        return orders.readOwned(id)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND,
                                "Order not found")));
    }
}
```

**Distinguishing 401/403/404:**

- Missing/malformed/expired JWT → Spring Security 401, **never enters controller**.
- Valid JWT lacking `SCOPE_orders:read` → 403, **never enters `OrdersController`**.
- Valid JWT with scope, missing required `sub`/`tenant_id` → 403 from service.
- Valid scope and claims, record owned by another user/tenant → 404 per example policy.
- Valid scope, owner, and tenant → 200 DTO with only id/status.

**Never write logic like “if different tenant, skip filter and return all data”**. `Mono.empty()` in a repository read can mean “not found”, yet `Mono.empty()` must never substitute for authentication/claim validation failures when a policy is mandatory.

## 7. Running and Observing HTTP

### 7.1. Startup

Install JDK 17+ and a Gradle version compatible with Boot 3.3.13. From the project directory:

```bash
gradle bootRun
```

If using the Gradle Wrapper:

```bash
./gradlew bootRun
```

On Windows use `gradlew.bat bootRun`. The app listens on `http://localhost:8080`.

**Note:** With `issuer-uri` and decoder auto-configuration, key discovery may occur when the first token is decoded (depending on decoder setup/version). To test real Bearer tokens, a matching IdP/issuer must be available. The `mockJwt()` tests below do not need signed access tokens to verify business logic.

### 7.2. Testing the Public Route

```bash
curl -i http://localhost:8080/public/ping
```

Expected status 200 and:

```json
{"message":"PONG"}
```

### 7.3. Testing Protected Routes Without a Token

```bash
curl -i http://localhost:8080/api/me
curl -i http://localhost:8080/api/context
curl -i http://localhost:8080/api/orders/A-100
```

With Bearer Resource Server configuration, requests missing credentials typically receive **401** with a `WWW-Authenticate: Bearer` challenge header. Sending a dummy token causes the decoder to reject it without creating a trusted principal.

### 7.4. Testing with a Real IdP (Optional)

You can run local Keycloak to issue real access tokens:

```bash
docker run --rm --name keycloak-jwt-lab \
  -p 127.0.0.1:9090:8080 \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=admin \
  -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin \
  quay.io/keycloak/keycloak:26.8.2 \
  start-dev --hostname=http://localhost:9090
```

This is Keycloak **dev mode**, HTTP with a demo admin; localhost only. In the admin console `http://localhost:9090/admin/`:

1. Create realm `learning`.
2. Create a confidential OIDC client with **Client ID** `jwt-demo-machine`, enable client authentication and **Service Accounts Roles / client_credentials**.
3. Copy the client secret into your test environment; never commit it to Git or put it in a frontend.
4. You can create a client scope/mapper so access tokens contain `tenant_id=tenant-a` and scope `orders:read` when testing `/api/context` and `/api/orders/...`. **Keycloak does not add arbitrary business claims by default**; a real mapper must be configured.
5. If Resource Server tokens require audience `orders-api`, configure an audience mapper on the IdP and an `aud` validator on the API (see Section 10).
6. Ensure the discovery issuer is `http://localhost:9090/realms/learning`.

Token endpoint:

```text
http://localhost:9090/realms/learning/protocol/openid-connect/token
```

The demo machine-token will have a Keycloak-issued **service account** `sub`, which will not default to `subject-7` from fixtures. Thus `/api/me` can return the service account identity, whereas `/api/orders/A-100` **should not be expected to return 200** unless policies/fixtures actually match owner and tenant. That is proper security behavior, not an `@AuthenticationPrincipal` bug.

In the lab environment, after obtaining a token via an appropriate HTTP client, call the API:

```bash
curl -i -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/me

curl -i -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/context
```

`TOKEN` is an environment variable holding an access token obtained via OAuth2, **not** a hand-crafted string or ID token. Passing tokens on the command line can expose them in process lists/shell history/traces; suitable only in protected test environments, and never copy tokens into logs/chat. Production uses secure secret/token management and HTTPS.

If the access token lacks `tenant_id`, `/api/me` shows an empty tenant while `/api/context` returns 403 per the example policy. If the app lacks audience validation, add it before production; issuer validation alone does not guarantee the token was issued **for this API**.

## 8. Automated Testing with WebTestClient and mockJwt

To test controllers/services reading principals, **you do not need to mint signed JWTs** for every test. Spring Security Test provides `SecurityMockServerConfigurers.mockJwt()` to inject a mock JWT Authentication into `WebTestClient`.

Crucial point: **`mockJwt()` does not run `ReactiveJwtDecoder`, verify signatures, check issuer/aud/exp, or fetch JWKs.** It only helps test authorization logic, controllers, and `SecurityContext`/roles/claims. Keep these tests separate from integration tests verifying real tokens.

### 8.1. JwtPrincipalApplicationTests.java

Create `src/test/java/example/JwtPrincipalApplicationTests.java`:

```java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
        .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class JwtPrincipalApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicPingIsVisibleWithoutJwt() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("PONG");
    }

    @Test
    void anonymousMeMustAuthenticate() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void meReadsJwtClaimsInController() {
        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt
                                .subject("subject-7")
                                .claim("tenant_id", "tenant-a")
                                .claim("preferred_username", "alice")))
                .get().uri("/api/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.subject").isEqualTo("subject-7")
                .jsonPath("$.preferredUsername").isEqualTo("alice")
                .jsonPath("$.tenantId").isEqualTo("tenant-a");
    }

    @Test
    void meDisplaysMissingOptionalClaimWithoutCrash() {
        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt
                                .subject("subject-7")
                                .claims(claims ->
                                        claims.remove("tenant_id"))))
                .get().uri("/api/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.tenantId").isEqualTo("");
    }

    @Test
    void serviceReadsReactorContext() {
        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt
                                .subject("subject-7")
                                .claim("tenant_id", "tenant-a"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_orders:read")))
                .get().uri("/api/context")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.subject").isEqualTo("subject-7")
                .jsonPath("$.tenantId").isEqualTo("tenant-a")
                .jsonPath("$.authorities[0]")
                .isEqualTo("SCOPE_orders:read");
    }

    @Test
    void serviceDeniesMissingRequiredTenant() {
        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt
                                .subject("subject-7")
                                .claims(claims ->
                                        claims.remove("tenant_id"))))
                .get().uri("/api/context")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void ownerCanReadOwnOrder() {
        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt
                                .subject("subject-7")
                                .claim("tenant_id", "tenant-a")
                                .claim("scope", "orders:read"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_orders:read")))
                .get().uri("/api/orders/A-100")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo("A-100")
                .jsonPath("$.status").isEqualTo("READY");
    }

    @Test
    void sameTenantDifferentOwnerIsNotVisible() {
        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt
                                .subject("subject-7")
                                .claim("tenant_id", "tenant-a"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_orders:read")))
                .get().uri("/api/orders/A-101")
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void sameSubjectDifferentTenantIsNotVisible() {
        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt
                                .subject("subject-7")
                                .claim("tenant_id", "tenant-a"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_orders:read")))
                .get().uri("/api/orders/B-200")
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void missingScopeIsForbiddenBeforeController() {
        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt
                                .subject("subject-7")
                                .claim("tenant_id", "tenant-a"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_profile")))
                .get().uri("/api/orders/A-100")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void rawScopeStringIsNotSameAsGrantedAuthority() {
        // Mock deliberately overrides authorities. Demonstrates that
        // authorization checks Authentication authorities, not a raw
        // string returned by getClaimAsString("scope").
        client.mutateWith(mockJwt()
                        .jwt(jwt -> jwt
                                .subject("subject-7")
                                .claim("tenant_id", "tenant-a")
                                .claim("scope", "orders:read"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_other")))
                .get().uri("/api/orders/A-100")
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

Command:

```bash
gradle test
```

**Note:** In the test code above, `import java.util.List;` is unused; Java compiles fine with unused imports, though strict linters may ask to remove it. These tests cover **controllers, Spring Security HTTP rules, service claims, and Reactor Context**, not the cryptographic trustworthiness of fake tokens.

### 8.2. Testing a Pure Reactive Service with StepVerifier

Create `src/test/java/example/CurrentJwtServiceTests.java`:

```java
package example;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationToken;

import reactor.test.StepVerifier;

class CurrentJwtServiceTests {

    private final CurrentJwtService service = new CurrentJwtService();

    @Test
    void extractsJwtFromSubscriberContext() {
        Jwt jwt = Jwt.withTokenValue("unit-test-only-token")
                .header("alg", "none")
                .claim("sub", "subject-7")
                .claim("tenant_id", "tenant-a")
                .build();

        Authentication authentication = new JwtAuthenticationToken(
                jwt,
                List.of(new SimpleGrantedAuthority(
                        "SCOPE_orders:read")));

        StepVerifier.create(
                service.requireIdentity()
                        .contextWrite(
                                ReactiveSecurityContextHolder
                                        .withAuthentication(authentication)))
                .assertNext(identity -> {
                    org.junit.jupiter.api.Assertions.assertEquals(
                            "subject-7", identity.subject());
                    org.junit.jupiter.api.Assertions.assertEquals(
                            "tenant-a", identity.tenantId());
                    org.junit.jupiter.api.Assertions.assertTrue(
                            identity.authorities().contains(
                                    "SCOPE_orders:read"));
                })
                .verifyComplete();
    }

    @Test
    void missingContextFailsClosed() {
        StepVerifier.create(service.requireIdentity())
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void missingTenantFailsClosed() {
        Jwt jwt = Jwt.withTokenValue("unit-test-only-token")
                .header("alg", "none")
                .claim("sub", "subject-7")
                .build();

        Authentication authentication =
                new JwtAuthenticationToken(jwt);

        StepVerifier.create(service.requireIdentity()
                .contextWrite(
                        ReactiveSecurityContextHolder
                                .withAuthentication(authentication)))
                .expectError(AccessDeniedException.class)
                .verify();
    }
}
```

**Why does the test use `alg=none` while production must not?** This `Jwt` is constructed directly in a unit test and **never passes through `ReactiveJwtDecoder`**. It only demonstrates propagating Authentication through Reactor Context. In production, never configure a decoder to accept unsigned JWTs or `alg=none`. Signature/issuer/exp testing belongs to a separate integration test suite.

### 8.3. Test Matrix

| Request / scenario | Expected | Handled by |
| --- | --- | --- |
| GET `/public/ping` without token | 200 | Controller |
| GET `/api/me` without token | 401 | Resource Server entry point |
| Mock JWT with sub/username/tenant | 200 + DTO | `@AuthenticationPrincipal Jwt` |
| Mock JWT missing tenant on `/api/me` | 200 + empty tenant | Display controller, no tenant authz |
| Mock JWT with tenant on `/api/context` | 200 + Identity | `ReactiveSecurityContextHolder` |
| Mock JWT missing tenant on `/api/context` | 403 | Service fail-closed |
| Mock JWT with scope + owner + tenant for A-100 | 200 | Security + OrderService |
| Mock JWT same tenant, different owner A-101 | 404 | OrderService |
| Mock JWT same subject, different tenant B-200 | 404 | OrderService |
| Mock JWT missing `SCOPE_orders:read` | 403 | AuthorizationWebFilter |
| Mock JWT with raw scope claim, overridden authorities | 403 | AuthorizationWebFilter |
| Wrong signature, wrong issuer/audience, expired token | Must be 401 in E2E | `ReactiveJwtDecoder` + validations; **not** tested by `mockJwt` |

**Note:** Some default Spring Boot/Spring Security error responses depend on version and `Accept` header. The tests above assert only status codes rather than assuming every 401/403 has a fixed JSON body. If the API needs unified `ProblemDetail`, build custom `ServerAuthenticationEntryPoint`/`ServerAccessDeniedHandler` without breaking Bearer `WWW-Authenticate`.

## 9. Differences Between Jwt, Principal, and Name

### 9.1. Why Is `Authentication.getPrincipal()` a Jwt?

In default Spring Security JWT Resource Server setups, once a token is verified, Authentication is normally a `JwtAuthenticationToken`; its principal is `Jwt` and `getName()` defaults to the `sub` claim.

```java
JwtAuthenticationToken token = ...;
Jwt jwt = token.getToken();

String subject = jwt.getSubject();
String principalName = token.getName();
```

This is an **illustrative fragment**, not a standalone runnable block. By default both values represent `sub`. However, if you configure `JwtAuthenticationConverter.setPrincipalClaimName("preferred_username")`, `token.getName()` can differ while `jwt.getSubject()` remains the real subject.

**Recommendation:** Derive the **identity key** from a stable, issuer-verified claim per system contract; never rely on mutable display usernames or custom principal names when identifying data owners.

### 9.2. Customizing Principal Name in WebFlux

When genuinely required, you can register a converter on the reactive DSL:

```java
JwtAuthenticationConverter sync = new JwtAuthenticationConverter();
sync.setPrincipalClaimName("preferred_username");

var adapter = new ReactiveJwtAuthenticationConverterAdapter(sync);

// Inside ServerHttpSecurity.oauth2ResourceServer(...):
.jwt(jwt -> jwt.jwtAuthenticationConverter(adapter))
```

This snippet requires importing `JwtAuthenticationConverter`, `ReactiveJwtAuthenticationConverterAdapter`, and wiring it into the security chain. It does **not** replace issuer/audience validators or create tenant permissions; it merely changes which claim populates `Authentication.getName()`. For tenant isolation, still read trusted `sub`/`tenant_id` and enforce access checks.

### 9.3. Reading Nested Claims

Some IdPs emit claims like:

```json
{
  "realm_access": {
    "roles": ["employee", "manager"]
  }
}
```

You can read them as:

```java
Map<String, Object> realm =
        jwt.getClaimAsMap("realm_access");

if (realm != null) {
    Object rawRoles = realm.get("roles");
    if (rawRoles instanceof List<?> roles) {
        // Validate each element type, allowlist role names,
        // and map according to server policy.
    }
}
```

Never cast `(List<String>) realm.get("roles")` without type checks; that risks `ClassCastException` on unexpected data. Never turn arbitrary unbounded role strings into `ROLE_ADMIN` just because the IdP put them in the payload; enforce issuer, audience, client scope, and controlled role mappers.

### 9.4. Reading Jwt in a Service Method with @PreAuthorize

When `@EnableReactiveMethodSecurity` is enabled, you can protect service methods:

```java
@PreAuthorize("hasAuthority('SCOPE_orders:read')")
public Mono<OrderView> findOwned(String id) {
    return currentJwtService.requireIdentity()
            .flatMap(identity -> repository.findOwned(
                    id, identity.tenantId(), identity.subject()));
}
```

This is an **illustrative fragment**, assuming `repository` and `OrderView` exist. With reactive method security, methods returning `Mono`/`Flux` must be invoked through the Spring proxy rather than self-invocation that bypasses the interceptor. Method security checks scopes; the service still enforces tenant/owner boundaries. Never call `block()` inside SpEL or business pipelines.

## 10. Trust Model: Signature, Issuer, Audience, exp, and Tenant

### 10.1. Being Decodable Does Not Mean Trustworthy

An attacker can craft JSON:

```json
{
  "sub": "admin",
  "tenant_id": "tenant-a",
  "scope": "orders:read orders:write"
}
```

and Base64URL-encode it into a string resembling a JWT. If an application merely splits the payload and trusts claims, the attacker grants themselves privileges. **Always use a verifying `ReactiveJwtDecoder`** before invoking services. Never settle for “checking that the JWT has three parts” or inspecting `alg` alone.

### 10.2. What Does Spring Resource Server Check by Default?

With `issuer-uri` and trusted JWK, Spring Security resource server typically:

- Verifies the JWS/JWK signature against permitted algorithms;
- Checks `exp`/`nbf` timestamps (with version-dependent default clock skew);
- Validates `iss` matches configuration;
- Maps `scope`/`scp` into `SCOPE_*` authorities;
- Creates `Authentication` based on the validated `Jwt`.

**Key point:** Do not assume **audience (`aud`) is automatically validated** for your API just because you configured `issuer-uri`. With many Authorization Servers, audience checks are mandatory to stop tokens issued for App A from being used at API B. Add an `aud` validator or a verified provider-equivalent policy.

### 10.3. Adding an Audience Validator per API Contract

You can replace the Boot decoder bean with the following configuration (complete configuration class snippet):

```java
package example;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
public class AudienceDecoderConfig {

    @Bean
    ReactiveJwtDecoder audienceAwareDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer) {

        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder
                        .withIssuerLocation(issuer)
                        .build();

        OAuth2TokenValidator<Jwt> base =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains("orders-api")
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Required API audience missing",
                                        null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        base, audience));

        return decoder;
    }
}
```

**This is an OPTIONAL configuration to add when deploying a real API**, not required for `mockJwt` tests with a local issuer. When defining a custom `ReactiveJwtDecoder` bean, you **replace/override Boot auto-config**, so preserve `JwtValidators.createDefaultWithIssuer(issuer)` to avoid accidentally dropping `exp`/`nbf`/`iss` checks. `withIssuerLocation(...)` may require OIDC metadata/discovery from the IdP when constructing the bean, so tests/startup need an IdP or a stub setup.

If the IdP does not yet include `aud=orders-api`, real tokens will get 401 — which is the **correct** behavior for an audience-enforcing resource server. Configure the Authorization Server to issue the right audience; **never** delete the validator just to let another service's tokens work.

### 10.4. Issuer + Subject with Multiple IdPs

If an app trusts multiple issuers, do not build user keys from `sub` alone; use `(issuer, subject)`, validate issuer routing, and enforce per-source audience checks. Multi-tenant authentication may require `JwtIssuerReactiveAuthenticationManagerResolver` or multiple `SecurityWebFilterChain`/manager configurations per pattern. An issuer URI from a token/host/request is **untrusted input until matched by policy**—avoid SSRF from blindly fetching token-specified JWK URLs.

### 10.5. Claims Do Not Replace Current Data State

Tokens are signed at issuance time, whereas permissions can change afterward:

- A user is deleted/locked or leaves a tenant;
- An order changes owner;
- An admin role is revoked;
- A subscription expires;
- An access token remains valid until `exp` even though policy changed.

If near-real-time revocation is required, consider short token TTLs, revocation/introspection, DB/cache policy checks, token versioning, or event-driven invalidation. Never assume JWTs automatically reflect database changes after issuance.

## 11. Common Pitfalls and How to Fix Them

### 11.1. `@AuthenticationPrincipal Jwt` Returns Null

Causes:
- Route is `permitAll`/anonymous while code assumes a JWT is always present;
- A custom converter replaced the authentication principal with another type;
- Request traversed a Basic/form/opaque-token chain;
- `SecurityWebFilterChain` did not match the path;
- No Bearer token was sent;
- Controller method was invoked directly outside a security request context in a unit test.

Fix: protect the route, check filter chains and Authentication types, and use `mockJwt` properly in `WebTestClient`. If supporting multiple auth types, branch cleanly per contract rather than casting blindly.

### 11.2. `jwt.getClaimAsString("tenant_id")` Is Null

The provider may not emit the claim yet, may name it differently, nest it, or lack a client scope mapper. Inspect a **real access token**, not an ID Token by mistake. For tenant-scoped queries, **fail closed**; never fall back to an unverified `X-Tenant` request header.

### 11.3. Calling `getClaimAsStringList("scope")` Fails

`scope` is usually a **single space-delimited string**, whereas `scp` is sent as a list by some providers. Use the API matching the schema; authorization should inspect Spring-mapped `GrantedAuthority` instances rather than re-splitting strings in every service.

### 11.4. 401 Even Though the JWT Has “Correct” Claims

The JWT may be expired, before `nbf`, have the wrong issuer/audience, use an untrusted JWK key, fail signature verification, use a disallowed `alg`, be truncated, or have a malformed `Authorization` header. Inspect the error category/`WWW-Authenticate`; **never** decode the JWT yourself and bypass verification to make it work.

### 11.5. 403 Even Though Signature Verification Succeeded

A valid signature only verifies the issuer. The token may lack `SCOPE_orders:read`, required tenant claims, role mappings, or business permissions. Distinguish 403 from Security authorization vs. 403 from service-layer claim validation.

### 11.6. 404 Even Though the Order Exists in the DB

The order may belong to another user/tenant — which is precisely the resource-hiding policy. Never switch production debugging queries to look up solely by `id` without tenant/owner filters. Use redacted audit logs recording request IDs and policy outcomes.

### 11.7. `SecurityContextHolder.getContext()` Is Empty in WebFlux

You are using the Servlet ThreadLocal API. Fix by calling `ReactiveSecurityContextHolder.getContext()` inside a publisher or passing identity explicitly. Do not block, manually subscribe, or globally cache Authentication.

### 11.8. Principal Name Differs from Subject

`JwtAuthenticationConverter.setPrincipalClaimName(...)` may have changed it; `getName()` is not guaranteed to be `sub` across all apps. When storing owner IDs, follow a contract based on issuer+subject or internal user ID, not mutable usernames/emails.

### 11.9. `@PreAuthorize` Only on Scope Still Leaves IDOR

Scopes permit an action category, not ownership of specific records. Add tenant/owner constraints in database queries and enforce resource-specific policies. Avoid returning entities solely by client-supplied IDs.

### 11.10. `mockJwt` Tests PASS, Real Bearer Tokens FAIL

`mockJwt` bypasses the decoder. E2E tests with IdP/JWK/signature/iss/aud/exp and real HTTP requests are needed. This is not a test bug; the two test suites measure different layers.

### 11.11. Leaking Full Claims in Responses

`return jwt.getClaims()` can leak emails, phone numbers, internal roles, tenant mappings, session metadata, or unnecessary fields. Return a DTO allowlisting UI-needed fields; redact logs/traces too. Never return `jwt.getTokenValue()`.

### 11.12. Resource Server Confuses ID Token with Access Token

OIDC ID Tokens let clients verify login and should not be sent as Bearer tokens to Resource Servers by default. APIs should accept **access tokens** with appropriate audience/scopes. If a decoder checks only the issuer without audience, an ID Token could be accepted erroneously under weak config. Add audience/token-purpose validation.

### 11.13. Multiple Services Forward the Request's Authorization Header

Do not blindly forward the user's raw Bearer JWT to every downstream API. Each Resource Server needs valid audience/scopes; token relay requires clear trust boundaries and may require OAuth2 Token Exchange or a separate access token. HTTP client logs must never print the `Authorization` header.

### 11.14. Wrong JSON Claim Type Causes 500

If `tenant_id` is a string from one issuer but an object/list from another, `getClaimAsString` may error or convert unexpectedly. Agree on claim schemas and validate during decode/validation or at the service boundary; return controlled errors without exposing stack traces.

### 11.15. `@EnableReactiveMethodSecurity` Has No Effect

Verify the bean method is called through a Spring proxy, the annotation is on a public method, the return type is reactive, there is no self-invocation, and Servlet method security is not accidentally configured. Add integration tests with real security context / `mockJwt`.

### 11.16. Token Scopes Containing Colons or Hyphens

`SCOPE_orders:read` is a normal authority name. Inside SpEL strings, quote the literal properly:

```java
@PreAuthorize("hasAuthority('SCOPE_orders:read')")
```

The `:` does not create a special role. `hasRole("ADMIN")` checks `ROLE_ADMIN` and is **not equivalent** to `SCOPE_orders:read`.

## 12. Real JWT Testing and Distinguishing Confidence Levels

### 12.1. mockJwt Tests: Checking Business Logic, Not Cryptography

Unit/integration tests in Section 8 simulate successful Authentication. They are suited for:
- URL rules and 403 when authorities are missing;
- Controller `@AuthenticationPrincipal`;
- Service Reactor Context;
- Tenant/owner enforcement;
- DTO contracts.

However, they **do not run**:
- Signature verification;
- JWK retrieval/rotation;
- Issuer/audience validation;
- Timestamp/clock skew;
- Token type confusion;
- Certificate/HTTPS verification;
- Token replay/revocation.

### 12.2. Testing Real Signatures and Token Endpoints

Use a test IdP realm or a test signer paired with matching public JWKs. Cases to cover:

| Token | Expected |
| --- | --- |
| Valid signature, right issuer, right audience, unexpired | 200 on endpoint with matching scope and record |
| Tampered signature | 401 |
| `exp` in the past | 401 |
| `nbf` in the future beyond clock skew | 401 |
| Untrusted issuer | 401 |
| Audience missing API when aud validator enabled | 401 |
| Missing scope | 403 on `/api/orders/**` |
| Missing tenant | 403 in service requiring tenant |
| Different owner/tenant | 404 per policy |
| Unsigned/`alg=none` JWT outside unit tests | 401 |
| OIDC ID token with wrong audience/type for API | 401 with proper validators |

Never forge a “fake token with the right claims” and treat HTTP 200 as proof of production safety. Verify the API uses a proper `ReactiveJwtDecoder`, JWK trust, and validators.

### 12.3. Testing Reactive Context with StepVerifier

If a service requires user identity, test the publisher directly with:

```java
.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(authentication))
```

This is the modern Reactor API; do not use `subscriberContext` from very old Reactor examples. Remember to also test **missing context** and **missing tenant** to confirm fail-closed behavior.

### 12.4. Never Log Raw Tokens in Tests

Synthetic tokens in `mockJwt()` are dummy data safe in test memory, but never write raw production JWTs into fixtures or CI artifacts. When testing with real tokens, use a CI secret store and short-lived tokens, logging only redacted status/codes.

## 13. Advanced: Multiple Identity Types and Mapping Principles

### 13.1. Opaque Tokens Differ from JWTs

With OAuth2 opaque token introspection, Authentication is normally `BearerTokenAuthentication` holding an `OAuth2AuthenticatedPrincipal` and attributes, **not `JwtAuthenticationToken`**. If an API supports both, build a `CurrentCaller` abstraction populated by each verified auth mechanism rather than casting every principal to `Jwt`.

Safe approach:

```text
JWT access token -> ReactiveJwtDecoder -> JwtAuthenticationToken -> CurrentCaller
Opaque token -> ReactiveOpaqueTokenIntrospector -> BearerTokenAuthentication
             -> CurrentCaller
OIDC Login session -> OidcUser/Auth -> CurrentCaller (separate policy)
```

Each branch has its own validation and trust semantics. A pure service can accept `CurrentCaller(subject, tenant, permissions)` constructed after authentication rather than coupling to framework types.

### 13.2. Separating JWT Claims, Authorities, and Permissions

Keep three concepts distinct:

1. **Signed claims:** issuer/sub/audience/tenant/scope.
2. **Authentication authorities:** mapper converts appropriate claims to `SCOPE_*`/`ROLE_*`.
3. **Effective permissions:** resource policy + DB state + user/tenant status at request time.

Never read raw role or scope claims from query parameters. Never let services treat `preferred_username` as a tenant ID. In multi-tenant systems, a tenant chosen via URL/header is at most a **requested tenant** and must be cross-checked against the authorized tenant/affiliation; never trust an `X-Tenant` header on its own.

### 13.3. @AuthenticationPrincipal(expression = ...)

Spring Security annotations support SpEL expressions on principals, e.g., extracting a nested field. Still, when learning JWT Resource Server, `@AuthenticationPrincipal Jwt` followed by `jwt.getClaimAsString(...)` is clearer, avoids coupling controllers to nested Map shapes, and makes missing-claim tests easier. If using a meta-annotation for a normalized identity, build an explicit resolver/converter and test it in WebFlux rather than copying Servlet code.

### 13.4. Avoid Caching Tokens in Global Caches

Never store raw `Jwt`/Authentication in static fields, singleton state, or Reactor `cache()` on publishers shared across requests. `Jwt` holds user data; mis-scoped caching can expose user A's identity to user B. When caching authorization decisions, keys must include issuer+subject+tenant+resource+policy version with an appropriate TTL.

### 13.5. When Services Call Downstream via WebClient

`ReactiveSecurityContextHolder` identifies the caller but **does not automatically attach bearer tokens** to outbound `WebClient` requests. Forwarding a user's token to another Resource Server requires security design:
- Does the downstream API trust that token's issuer/audience?
- Is token exchange / on-behalf-of needed?
- Are scopes sufficient for downstream?
- Could the token be logged by proxies?
- Are separate service-to-service client credentials needed?

Never automatically attach `Authorization: Bearer jwt.getTokenValue()` to arbitrary client-controlled URLs; that creates SSRF and token-leakage risks. For legitimate token relay use cases, use security integrations with strict endpoint/destination controls.

## 14. Production Checklist

1. JWTs are decoded and **signature-verified** with an appropriate `ReactiveJwtDecoder`; never parse Base64 manually for auth.
2. Trust only configured issuers/algorithms/JWKs; never fetch arbitrary token-specified JKU/JWKS URLs.
3. Enable issuer validation and `exp`/`nbf`; manage clock skew and key rotation.
4. Enforce API-specific **audience validation**; reject ID Tokens or tokens meant for other services.
5. Standardize claim schemas: `sub`, `tenant_id`, `scope`/`scp`, and data types.
6. Read `@AuthenticationPrincipal Jwt` when the controller expects JWT Authentication; check null/types on multi-auth routes.
7. In services, use `ReactiveSecurityContextHolder` or pass normalized `Identity`, never Servlet `SecurityContextHolder`.
8. Never call `block()` or manual `subscribe()` inside reactive requests.
9. Check mapped `GrantedAuthority` instances for scopes/roles rather than trusting raw client strings.
10. Enforce resource ownership/tenant in service/DB queries, not only on HTTP routes.
11. Fail closed when mandatory claims are missing; never fall back to a default tenant.
12. Never put `Jwt.getTokenValue()`, full claims, emails, or token headers into JSON/logs/metrics.
13. Distinguish human user subjects from service accounts, and user tokens from client-credentials tokens.
14. Account for JWT latency until expiry when roles/user status change, or implement a revocation strategy.
15. Preserve 401/403 Bearer semantics; never catch-all to return 200/500 or strip `WWW-Authenticate`.
16. Include negative tests for different tenant, different owner, missing scope, and wrong issuer/audience/exp/signature.
17. Pair `mockJwt()` authorization tests with **E2E decoder tests** using real signed tokens.
18. With multiple issuers, key users by `(issuer, sub)` and isolate trust policies.
19. Behind proxies/gateways, never trust externally supplied auth headers/claims unless they crossed a trusted auth boundary.
20. When dispatching to Kafka or background jobs, HTTP Reactor Context does not propagate automatically; pass immutable verified identities or use dedicated service principals.
21. On Spring Boot/Spring Security upgrades, re-verify converters, claim coercion, WebFlux argument resolvers, and security chain matching.
22. Run load/regression tests to catch token/identity leaks caused by reactive caching or context propagation bugs.

## 15. Self-Check Questions

**1. How do `Jwt` and `JwtAuthenticationToken` differ?**  
`Jwt` holds the token/claims/headers produced by the decoder. `JwtAuthenticationToken` is the `Authentication` wrapping `Jwt`, authorities, and principal name.

**2. Which annotation do controllers use to inject the default `Jwt`?**  
`@AuthenticationPrincipal Jwt jwt` on a WebFlux controller method parameter.

**3. Which API must reactive services use to read `SecurityContext`?**  
`ReactiveSecurityContextHolder.getContext()` inside a `Mono`/`Flux` publisher, never Servlet's ThreadLocal `SecurityContextHolder`.

**4. Is a Base64URL-decoded JWT payload trustworthy on its own?**  
No. Signature, issuer, timestamps, audience, and token policy must be verified by the decoder first.

**5. What should a tenant-aware service do when `tenant_id` is missing?**  
Fail closed; e.g., emit `AccessDeniedException` instead of granting access across all tenants.

**6. Which claim does `getSubject()` correspond to?**  
`sub`.

**7. Does `Authentication.getName()` always equal email or username?**  
No. For JWTs it defaults to `sub`, though a principal claim converter can change it; emails/usernames are not guaranteed stable.

**8. Does the `scope` claim automatically become `ROLE_*`?**  
No. By default scopes map to `SCOPE_*`, while roles require a dedicated mapper.

**9. Why does having `SCOPE_orders:read` still forbid reading order A-101?**  
Because scope only authorizes the action type, while order A-101 belongs to another owner; the service must verify ownership.

**10. Do matching subjects across two different tenants share permissions?**  
No. Identity and permissions must evaluate tenant, issuer, and resource ownership.

**11. What does an unauthenticated or Bearer-missing request to a protected endpoint typically return?**  
401 from the resource server entry point.

**12. Valid JWT lacking `SCOPE_orders:read` on `/api/orders/A-100`?**  
403.

**13. Valid JWT with right scope, but record belongs to another user/tenant?**  
The demo returns 404 to avoid disclosing the existence of unauthorized records.

**14. Why does `mockJwt()` not prove certificates, JWKs, or signatures are valid?**  
Because it injects a mock `Authentication` in tests, bypassing `ReactiveJwtDecoder`.

**15. Should `Jwt.getTokenValue()` be returned in `/api/me`?**  
No. It is a bearer credential that could be replayed to call APIs.

**16. When an IdP sends `scp` as a list, should you call `getClaimAsString("scope")` and split it?**  
No. Read the claim name/type matching the schema and/or rely on Spring authority mapping.

**17. What is the role of audience validation?**  
It ensures the access token was issued **for this API**, not merely signed by the same issuer.

**18. Does a JWT with `preferred_username=admin` prove the user is an admin?**  
No. It is a display claim and grants neither `ROLE_ADMIN` nor business privileges.

**19. Should `Authentication` be stored in a static field so services can read it quickly?**  
No. That mixes contexts/identities and leaks privileges across requests.

**20. When outbound `WebClient` calls another API, does Reactor Context automatically attach the bearer token?**  
No. Token relay or client credentials must be configured intentionally with proper audience/scopes.

**21. Why does `Identity` in the service exclude the raw `Jwt`?**  
To minimize privileges and sensitive data, making domain logic and tests cleaner.

**22. If an app accepts multiple issuers, is using `sub` alone as a global key safe?**  
No guarantee. Use `(issuer, subject)` or an internal mapping, and isolate validators.

**23. What is wrong when handling unexpected types in `getClaimAsStringList`?**  
Never cast blindly or swallow exceptions into permissions; validate schema/mappers and fail closed.

**24. Is a JWT access token the same as an OIDC Login ID Token?**  
No. ID Tokens verify user login at the client; Resource Servers need access tokens with the right audience/scopes.

**25. Why test against real tokens even after controller tests pass?**  
To verify cryptographic signatures, issuer, audience, expiry/JWK, and real HTTP Bearer integration behavior.

**Remember:** In **Spring Security WebFlux Resource Server JWT**, controllers can read the principal via `@AuthenticationPrincipal Jwt`, while reactive services read `Authentication` via `ReactiveSecurityContextHolder`. Always read a **validated Jwt**, maintain the boundary between raw claims and authorities, check **`sub` + tenant + resource ownership**, fail closed on missing mandatory claims, never block the event loop, and **never expose raw bearer tokens**. Combine `mockJwt`/`StepVerifier` with real decoder/JWK tests to verify both business logic and security.

## References

- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): issuer setup, Jwt authentication, scope authorities, audience validation, claim conversion.
- [Spring Security — OAuth2 WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/): resource server, OAuth2 client, and JWT support.
- [Spring Security — Reactive JWT testing](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt()`, authorities, `JwtAuthenticationToken`, and test limitations.
- [Spring Security — EnableReactiveMethodSecurity](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): Reactor Context, `@PreAuthorize`, and reactive method security.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain` and `ServerHttpSecurity`.
- [Spring Security 6.3 — Jwt API](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/oauth2/jwt/Jwt.html): token value, subject, claim methods, JOSE headers.
- [Spring Security 6.3 — ClaimAccessor API](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/oauth2/core/ClaimAccessor.html): typed claim extraction and missing claims.
- [Spring Security 6.3 — NimbusReactiveJwtDecoder API](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html): decoder, validator, JWK.
- [Spring Framework — Reactor Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): subscription context and propagation.
- [OAuth 2.0 Bearer Token Usage — RFC 6750](https://www.rfc-editor.org/rfc/rfc6750): Authorization Bearer, `WWW-Authenticate`, and 401/403 errors.
- [JSON Web Token — RFC 7519](https://www.rfc-editor.org/rfc/rfc7519): registered claims, sub/iss/aud/exp/iat/nbf.
- [JWT Best Current Practices — RFC 8725](https://www.rfc-editor.org/rfc/rfc8725): algorithm confusion, audience/issuer, trust boundaries.
- [Keycloak — Getting Started on Docker](https://www.keycloak.org/getting-started/getting-started-docker): demo local IdP/realm/client configuration.
