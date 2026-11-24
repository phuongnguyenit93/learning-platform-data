# Keeping HTTP Authorization Rules Consistent for Controller and RouterFunction in Spring Security Reactive

## 1. The Problem and Target Outcome

Spring WebFlux simultaneously supports two ways of writing HTTP endpoints: **annotation-based Controllers** like `@RestController`/`@GetMapping`, and **WebFlux.fn** with `RouterFunction`/`HandlerFunction`. In a real product, teams might use Controllers for legacy APIs, `RouterFunction` for new APIs, or keep both side by side during a gradual architectural migration.

Risk arises when a capability is implemented in both handler styles yet **ends up with different access policies**. For example, `GET /api/profile/annotated` requires login, whereas `GET /v2/profile` served by a `RouterFunction` accidentally sits outside the protected `/api/**` pattern. If an overly broad `permitAll` rule exists, one copy of the endpoint can leak data.

The goal of this lesson is: **the same security intent must produce the same outcome, regardless of whether the endpoint is handled by a Controller or a RouterFunction**.

After this lesson, you can:

1. Explain the boundaries between **`SecurityWebFilterChain`**, **`DispatcherHandler`**, **`HandlerMapping`**, Controllers, and `RouterFunction`.
2. Configure one central rule set using **`ServerHttpSecurity.authorizeExchange`** protecting both handler models.
3. Design URLs, HTTP methods, and rule precedence to avoid vulnerabilities caused by path changes or ordering mistakes.
4. Distinguish **route predicates** from **authorization matchers**, never confusing them as the same thing.
5. Separate URL-level permissions from owner/tenant business permissions, sharing services across both endpoint styles.
6. Run a Java 17+ Spring Boot WebFlux example with equivalent endpoints in both Controller and `RouterFunction`.
7. Write **`WebTestClient`** tests verifying pairs of public, authenticated, admin, `denyAll`, invalid-credential, and unlisted-URL endpoints.
8. Build a review checklist for refactoring or adding a new `RouterFunction`.

**Core principle:** an endpoint is protected by the **actual HTTP request** (path, method, and designed matchers), not because a method has `@GetMapping` or is registered via `RouterFunctions.route()`.

## 2. Two Endpoint Styles Running Together in WebFlux

### 2.1. Annotated Controller

A Controller maps requests using annotations:

~~~java
@RestController
public class AnnotatedApi {
    @GetMapping("/api/profile/annotated")
    public Mono<Map<String, String>> profile(Mono<Principal> principal) {
        return principal.map(p ->
                Map.of("username", p.getName()));
    }
}
~~~

This is an illustrative excerpt of a class and requires the corresponding imports; the complete demo is in Section 6. The handler returns `Mono` for the reactive model. Mappings are discovered by WebFlux through its annotation handler mapping mechanism.

### 2.2. RouterFunction and HandlerFunction

The functional style provides a `RouterFunction` defining which predicates route to a `HandlerFunction`:

~~~java
@Bean
RouterFunction<ServerResponse> routes() {
    return RouterFunctions.route()
            .GET("/public/functional",
                    request -> ServerResponse.ok()
                            .bodyValue(Map.of("mode", "public")))
            .build();
}
~~~

`RouterFunction` is not a Servlet Filter. When a request matches a predicate, the handler returns **`Mono<ServerResponse>`**; the Spring Boot WebFlux starter registers the components needed for `WebFlux.fn` and annotated endpoints to run in the same application.

### 2.3. Where Spring Security Sits

~~~text
                 HTTP request
                      |
                      v
          WebFlux WebFilter chain
                      |
                      v
            SecurityWebFilterChain
             Authentication + Authorization
                      |
            Match HTTP method/path
                      |
             +--------+---------+
             | permitted?       |
             +---+----------+---+
                 | Yes      | No
                 v          v
          DispatcherHandler  401/403/entry point
                 |
        Select matching HandlerMapping
                 |
          +------+------+
          |             |
   Annotated Controller RouterFunction
          |             |
          +------+------+
                 |
           Shared service
                 |
            Response body
~~~

**Key point:** `SecurityWebFilterChain` is a security chain at the `WebFilter` layer, not exclusively for `@RestController`. In a standard WebFlux setup bootstrapped by Spring Boot, requests through both Controllers and `RouterFunction` pass through the appropriate `WebFilter`s. Security rules are evaluated on `ServerWebExchange` before handler logic executes.

This also has boundaries: if you build another **separate `HttpHandler`** and mount it directly on the server without going through the application's `SecurityWebFilterChain`, or if an endpoint lives in another gateway/service, you cannot assume this app's policy covers it. Protection must be verified on the **actual execution path**.

## 3. Two Different Matcher Layers

| Aspect | Authorization Matcher | Router/Controller Matcher |
| --- | --- | --- |
| Where is it configured? | `ServerHttpSecurity.authorizeExchange` | `@GetMapping`/`@RequestMapping` or `RouterFunctions.route` |
| What is it based on? | `ServerWebExchange`: path, method, custom matcher | Path, HTTP method, headers, Accept, Content-Type, route predicates |
| Goal | Decide whether permissions suffice to proceed | Locate the handler that processes the request |
| On mismatch | Move to next rule or default deny | Move to another route/mapping or 404/405 |
| Order | Rules evaluated in declaration order | `RouterFunction` evaluated in order; annotation mapping uses specificity rules |
| Security mechanism | `ReactiveAuthorizationManager` | Does not replace `SecurityWebFilterChain` authorization |

These are two independent responsibilities. If a `RouterFunction` declares `GET /api/profile/functional`, yet the security policy only protects `/api/profile/annotated`, returning the same user data does not automatically extend the security policy to the second URL.

### 3.1. The URL on the Wire Is the Security Contract

Example:

~~~java
// Annotation path:
@GetMapping("/api/admin/annotated")

// Functional route:
.GET("/api/admin/functional", handler)
~~~

Both live under `/api/admin/**`, so they can share **one common rule**:

~~~java
.pathMatchers("/api/admin/**").hasRole("ADMIN")
~~~

Conversely, if the functional route is accidentally placed at `/functions/admin`, the rule above does not protect the new URL. A default **`anyExchange().denyAll()`** prevents the new URL from opening automatically, though the policy still needs updating if that route is an intended feature.

### 3.2. First-Match Rule and Wrong Ordering

~~~java
// RIGHT: specific admin rule comes before broad /api/** rule.
.authorizeExchange(ex -> ex
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .pathMatchers("/api/**").authenticated()
        .anyExchange().denyAll())
~~~

Dangerous configuration:

~~~java
// WRONG if you want /api/admin/** to require ROLE_ADMIN.
.authorizeExchange(ex -> ex
        .pathMatchers("/api/**").authenticated()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .anyExchange().denyAll())
~~~

In the wrong configuration, `/api/admin/functional` matches `/api/**` first, so the role check on the next line is never selected. **There is no special exception for `RouterFunction`**: both handler styles suffer from the exact same bug.

### 3.3. HTTP Methods Also Belong to the Policy

If an API only wants to make **GET** public for two URLs:

~~~java
.pathMatchers(
        HttpMethod.GET,
        "/public/annotated",
        "/public/functional").permitAll()
~~~

That way, the policy does not accidentally expose POST/PATCH/DELETE on the same paths if another team adds handlers later. In Spring Security WebFlux, `pathMatchers(HttpMethod, String...)` is the authorization DSL API.

**Important note:** CSRF is enabled by default for state-changing methods in typical browser configurations. When testing POST without a token, requests can be rejected with **403 by CSRF before reaching the intended rule**. You cannot use a tokenless POST test to prove that an authorization rule executed properly. The demo uses GET to focus on authorization and covers HTTP method/CSRF risks in Section 11.

### 3.4. Route Predicates Do Not Replace Security Matchers

A functional route might say:

~~~java
.GET("/api/items", accept(MediaType.APPLICATION_JSON),
        handler::listItems)
~~~

It has an **`Accept: application/json`** condition. If URL security is configured as:

~~~java
.pathMatchers("/api/items").authenticated()
~~~

the security rule still applies to the URL even if a request lacks the matching `Accept` header; once permitted, `RouterFunction` may not select the handler and WebFlux returns a different routing result. Never rely on `Accept` or `Content-Type` as an access control boundary unless you intentionally use a specifically designed and tested `ServerWebExchangeMatcher`.

Likewise, two requests to the same URL with different GET/POST methods can match different handlers. When write endpoints exist, define authorization by method, role, and owner together—never assume path names alone suffice.

## 4. One Common Permission Matrix for Both Handler Types

Before writing controllers/routers, list the **desired behaviors** and make both adhere to them:

| Purpose | Annotated Endpoint | Functional Endpoint | Shared Rule |
| --- | --- | --- | --- |
| Public | GET `/public/annotated` | GET `/public/functional` | GET public URLs → `permitAll` |
| Caller profile | GET `/api/profile/annotated` | GET `/api/profile/functional` | `/api/**` → `authenticated` |
| Admin operation | GET `/api/admin/annotated` | GET `/api/admin/functional` | `/api/admin/**` → `hasRole ADMIN` |
| Locked | GET `/internal/annotated` | GET `/internal/functional` | `/internal/**` → `denyAll` |
| Unpublished URL | `/unlisted` | `/unlisted-functional` | `anyExchange` → `denyAll` |

Grouping URLs under **the same permission-aligned namespaces** reduces repeating policies per handler. When permissions differ by method (e.g., GET publicly readable, POST staff-only write), add explicit method rules.

A typical rule set:

~~~java
.authorizeExchange(ex -> ex
        .pathMatchers(
                HttpMethod.GET,
                "/public/annotated",
                "/public/functional").permitAll()
        .pathMatchers("/internal/**").denyAll()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .pathMatchers("/api/**").authenticated()
        .anyExchange().denyAll())
~~~

**Why is public an exact list?** Using `/public/**.permitAll()` means a developer accidentally adding `/public/debug-secrets` exposes the endpoint. An explicit URL allowlist ensures adding a route requires **deliberately updating the policy**. Broad namespaces can be used for trusted static assets, provided you know everything served there.

**Why `anyExchange().denyAll()`?** A `RouterFunction` can be added without touching any Controller; fail-closed reduces the chance of new URLs opening automatically. However, `denyAll` **is not an owner/tenant checker** and cannot automatically know which endpoints should be allowed.

## 5. Share Business Logic, Never Scatter Permission Checks

There are two protection levels:

1. **HTTP authorization:** checks URL, HTTP method, and role/scope on `SecurityWebFilterChain`.
2. **Business authorization:** checks whether the caller has permission on a specific record (owner, tenant, group relationship, resource state) inside the service/repository.

Both handler styles should invoke **the same business service**, rather than duplicating permission checks:

~~~text
Controller GET /api/orders/42 -----+
                                   |
                                   v
                           OrderService.read(...)
                                   ^
                                   |
RouterFunction GET /api/orders/42 -+
                                   |
                                   v
                    owner/tenant check + query
~~~

In real applications, avoid registering two handlers for the exact same method+path expecting WebFlux to pick by intent. The diagram only illustrates sharing a service when endpoints are at different paths or during refactoring.

Business service example:

~~~java
// Integration illustration: OrderDto and repository are application components.
public Mono<OrderDto> readOrder(String orderId, String actorId) {
    return repository.findByIdAndOwnerId(orderId, actorId);
}
~~~

**`actorId`** must come from a verified `Authentication` (or verified subject/claim), never from a client-declared query parameter. In multi-tenant systems, queries also need a `tenantId` from a trusted source.

### 5.1. Method Security as an Additional Layer

If a shared service requires `ADMIN` regardless of which handler calls it, you can enable **`@EnableReactiveMethodSecurity`** and use **`@PreAuthorize("hasRole('ADMIN')")`** on a **Spring bean** method returning the appropriate reactive `Publisher`. Then both Controller and `RouterFunction` call that bean and get consistent method-layer checks.

However:
- `@PreAuthorize` does not replace URL rules for unauthenticated access.
- Self-invocation within the same class can bypass the proxy.
- Record-level authorization still requires checking permissions against actual data/resources.
- If a custom `RouterFunction` filter checks permissions, it only applies to functional routes inside that router; Controllers do not automatically share that filter. Never use **`RouterFunction.filter()`** as the sole shared policy across both handler styles.

The demo below focuses on **one `SecurityWebFilterChain`** and a shared `ProfileService` to demonstrate the exact problem.

## 6. Runnable Java 17+ Example with Spring Boot WebFlux

Fixed example versions: **Java 17+**, **Spring Boot 3.5.16**, and compatible **Gradle 8.x** (Spring Boot 3.5.16 supports Gradle 8.4+). All endpoints run inside **one Spring WebFlux application**, without adding `spring-boot-starter-web`.

Two learning users:

| User | Demo Password | Authorities |
| --- | --- | --- |
| `reader` | `reader-pass` | `ROLE_USER` |
| `admin` | `admin-pass` | `ROLE_USER`, `ROLE_ADMIN` |

Public URLs are explicitly allowlisted by GET. One Controller and one `RouterFunction` produce matching profile response shapes by calling the shared **`ProfileService`**.

Structure:

~~~text
hybrid-webflux-security/
├── settings.gradle
├── build.gradle
├── src/main/java/example/hybrid/HybridApplication.java
├── src/main/java/example/hybrid/SecurityConfig.java
├── src/main/java/example/hybrid/ProfileService.java
├── src/main/java/example/hybrid/AnnotatedApi.java
├── src/main/java/example/hybrid/FunctionalRoutes.java
└── src/test/java/example/hybrid/HybridAuthorizationTest.java
~~~

### 6.1. settings.gradle

~~~groovy
rootProject.name = 'hybrid-webflux-security'
~~~

### 6.2. build.gradle

~~~groovy
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot manages compatible versions of Spring Framework, Spring Security, and Reactor via its BOM, avoiding mismatched library branches. Use a controlled **Gradle Wrapper** in real projects. This illustration calls `gradle` directly because no wrapper was generated.

### 6.3. HybridApplication.java

~~~java
package example.hybrid;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HybridApplication {

    public static void main(String[] args) {
        SpringApplication.run(HybridApplication.class, args);
    }
}
~~~

### 6.4. SecurityConfig.java — One Policy for All WebFlux Handlers

~~~java
package example.hybrid;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        // Only these two GET endpoints are public.
                        .pathMatchers(
                                HttpMethod.GET,
                                "/public/annotated",
                                "/public/functional").permitAll()
                        // Deny all internal routes, regardless of handler.
                        .pathMatchers("/internal/**").denyAll()
                        // Must appear before /api/**.
                        .pathMatchers("/api/admin/**").hasRole("ADMIN")
                        .pathMatchers("/api/**").authenticated()
                        // Unlisted new routes are closed by default.
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }
}
~~~

**Points to observe:**

- No Controller or `RouterFunction` class names appear in the authorization rules.
- The security policy relies on the HTTP exchange's **method+path**.
- `/api/admin/**` is placed **before** `/api/**` because the first matching matcher decides the rule.
- `/internal/**` is denied even when the logged-in user is `admin`.
- Unlisted paths are denied by default; they do not become public merely because a developer adds a `RouterFunction`.
- HTTP Basic only collects/verifies credentials. If a user has the right password yet lacks the required role, authorization still denies the request.
- **CSRF is not disabled**; the demo uses only GET so it focuses on GET authorization. When adding write methods, design CSRF properly for the app's browser/session/credential model.

**Passwords:** the demo uses fixed passwords for localhost testing and `BCryptPasswordEncoder` to store hashes. Never copy hardcoded credentials into production. Use HTTPS for real HTTP Basic because Base64 does not protect secrets in transit.

### 6.5. ProfileService.java — Shared Logic for Both Handler Styles

~~~java
package example.hybrid;

import java.util.Map;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ProfileService {

    public Mono<Map<String, String>> profile(
            String username, String source) {

        return Mono.just(Map.of(
                "username", username,
                "source", source));
    }
}
~~~

The service only illustrates sharing presentation logic. The `username` argument is supplied by the **framework-authenticated principal** in both handler styles; clients cannot choose a username via a query parameter on this endpoint. With real resources, use a stable subject/user ID and verify owner/tenant before accessing repositories.

### 6.6. AnnotatedApi.java — Annotation-Based Endpoints

~~~java
package example.hybrid;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class AnnotatedApi {

    private final ProfileService profiles;

    public AnnotatedApi(ProfileService profiles) {
        this.profiles = profiles;
    }

    @GetMapping("/public/annotated")
    public Mono<Map<String, String>> publicInfo() {
        return Mono.just(Map.of(
                "source", "annotated",
                "visibility", "public"));
    }

    @GetMapping("/api/profile/annotated")
    public Mono<Map<String, String>> profile(Mono<Principal> principal) {
        return principal.flatMap(p ->
                profiles.profile(p.getName(), "annotated"));
    }

    @GetMapping("/api/admin/annotated")
    public Mono<Map<String, String>> admin() {
        return Mono.just(Map.of("admin", "annotated"));
    }

    @GetMapping("/internal/annotated")
    public Mono<Map<String, String>> internal() {
        return Mono.just(Map.of("internal", "not-exposed"));
    }
}
~~~

You can replace `profile(Mono<Principal>)` with `ReactiveSecurityContextHolder.getContext()` when a service needs to read the identity itself. In this example, accepting `Mono<Principal>` from WebFlux's argument resolver clearly illustrates the source of the authenticated username.

### 6.7. FunctionalRoutes.java — RouterFunction Endpoints

~~~java
package example.hybrid;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class FunctionalRoutes {

    @Bean
    RouterFunction<ServerResponse> functionalApi(ProfileService profiles) {
        return RouterFunctions.route()
                .GET("/public/functional", request ->
                        ServerResponse.ok().bodyValue(Map.of(
                                "source", "functional",
                                "visibility", "public")))
                .GET("/api/profile/functional", request ->
                        request.principal()
                                .flatMap(p -> profiles.profile(
                                        p.getName(), "functional"))
                                .flatMap(data ->
                                        ServerResponse.ok().bodyValue(data)))
                .GET("/api/admin/functional", request ->
                        ServerResponse.ok().bodyValue(
                                Map.of("admin", "functional")))
                .GET("/internal/functional", request ->
                        ServerResponse.ok().bodyValue(
                                Map.of("internal", "not-exposed")))
                .build();
    }
}
~~~

**Technical difference:** `RouterFunction` uses **`ServerRequest.principal()`** returning `Mono<Principal>`, whereas a Controller can accept **`Mono<Principal>`** as a method parameter. Despite the different Java APIs, both rely on the identity established by Spring Security for the request.

**Why not call `profiles.profile("admin", ...)`?** Because that is a hardcoded name, which can lead to business spoofing if used as a permission. Only take the username from the principal after the `authenticated` URL rule has passed.

**Why not add a `RouterFunction.filter()` to check roles itself?** Because a local filter only protects functional routes attached to that router, **never `AnnotatedApi`**. Shared HTTP protection must live in `SecurityWebFilterChain`; route filters are only for functional-endpoint-specific logic like input format checks or response enrichment, never replacing centralized authorization.

### 6.8. Running the Application

In the `hybrid-webflux-security` directory, with JDK 17+, Gradle 8.4+, and Maven Central access:

~~~bash
gradle bootRun
~~~

The application listens on `http://localhost:8080` by default unless another `server.port` is configured. GET endpoints return nearly identical shapes in both styles for convenient testing. Only use HTTP localhost for learning; with real credentials, HTTPS is mandatory.

## 7. Testing HTTP with curl: Two Handlers, One Policy

In another Bash terminal:

~~~bash
# Public: both return 200.
curl -s http://localhost:8080/public/annotated
# {"source":"annotated","visibility":"public"}

curl -s http://localhost:8080/public/functional
# {"source":"functional","visibility":"public"}

# Not logged in: both profiles require authentication.
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/profile/annotated
# 401

curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/profile/functional
# 401

# Wrong username/password: neither handler may return data.
curl -s -o /dev/null -w '%{http_code}\n' \
  -u reader:wrong-pass \
  http://localhost:8080/api/profile/functional
# 401

# Valid login: both handlers return the same authenticated username.
curl -s -u reader:reader-pass \
  http://localhost:8080/api/profile/annotated
# {"username":"reader","source":"annotated"}

curl -s -u reader:reader-pass \
  http://localhost:8080/api/profile/functional
# {"username":"reader","source":"functional"}

# Regular user lacking ROLE_ADMIN: both return 403.
curl -s -o /dev/null -w '%{http_code}\n' \
  -u reader:reader-pass http://localhost:8080/api/admin/annotated
# 403

curl -s -o /dev/null -w '%{http_code}\n' \
  -u reader:reader-pass http://localhost:8080/api/admin/functional
# 403

# Valid admin: both return 200.
curl -s -u admin:admin-pass http://localhost:8080/api/admin/annotated
# {"admin":"annotated"}

curl -s -u admin:admin-pass http://localhost:8080/api/admin/functional
# {"admin":"functional"}

# DenyAll: even admin is denied.
curl -s -o /dev/null -w '%{http_code}\n' \
  -u admin:admin-pass http://localhost:8080/internal/annotated
# 403

curl -s -o /dev/null -w '%{http_code}\n' \
  -u admin:admin-pass http://localhost:8080/internal/functional
# 403

# URL not listed in policy: blocked by default.
curl -s -o /dev/null -w '%{http_code}\n' \
  -u reader:reader-pass http://localhost:8080/unlisted
# 403
~~~

Lines starting with `#` are **expected results**, not output captured from a running server. For JSON Maps, field order is not a contract; `WebTestClient` below compares values by JSON path. On Windows PowerShell, use **`curl.exe`** and put commands on a single line instead of Bash line continuation.

**Important observation:** for HTTP Basic 401 responses, the response usually includes a `WWW-Authenticate: Basic ...` header; 403 denies permission for an authenticated caller. Controllers and `RouterFunction` must never manually change the status to 200 and stuff `{"error": "..."}` into the body to mask authorization failures.

### 7.1. Expected Matrix

| Caller | Annotated Path | Functional Path | Policy | Outcome Pair |
| --- | --- | --- | --- | --- |
| Guest | `/public/annotated` | `/public/functional` | GET `permitAll` | 200 / 200 |
| Guest | `/api/profile/annotated` | `/api/profile/functional` | `authenticated` | 401 / 401 |
| Wrong credentials | `/api/profile/annotated` | `/api/profile/functional` | Authentication failed | 401 / 401 |
| `reader` | `/api/profile/annotated` | `/api/profile/functional` | `authenticated` | 200 / 200 |
| `reader` | `/api/admin/annotated` | `/api/admin/functional` | `hasRole ADMIN` | 403 / 403 |
| `admin` | `/api/admin/annotated` | `/api/admin/functional` | `hasRole ADMIN` | 200 / 200 |
| `admin` | `/internal/annotated` | `/internal/functional` | `denyAll` | 403 / 403 |

This is how you verify **policy parity across both handler models**, rather than testing only the Controller and skipping `RouterFunction`.

## 8. Testing with WebTestClient: One Test Suite for Both Endpoint Styles

Use **`WebTestClient`** to test the real Spring Security `WebFilter` + `RouterFunctionMapping` + annotated handlers inside the same Spring context. Never substitute unit tests that call handler methods directly, as those bypass `SecurityWebFilterChain`.

File `src/test/java/example/hybrid/HybridAuthorizationTest.java`:

~~~java
package example.hybrid;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class HybridAuthorizationTest {

    @Autowired
    WebTestClient client;

    @Autowired
    ProfileService profiles;

    private static final List<String> PUBLIC = List.of(
            "/public/annotated",
            "/public/functional");

    private static final List<String> PROFILE = List.of(
            "/api/profile/annotated",
            "/api/profile/functional");

    private static final List<String> ADMIN = List.of(
            "/api/admin/annotated",
            "/api/admin/functional");

    private static final List<String> INTERNAL = List.of(
            "/internal/annotated",
            "/internal/functional");

    @Test
    void bothPublicEndpointsAcceptAnonymousClient() {
        for (String path : PUBLIC) {
            client.get().uri(path)
                    .exchange()
                    .expectStatus().isOk()
                    .expectBody()
                    .jsonPath("$.visibility").isEqualTo("public");
        }
    }

    @Test
    void bothProfileEndpointsRejectMissingCredentials() {
        for (String path : PROFILE) {
            client.get().uri(path)
                    .exchange()
                    .expectStatus().isUnauthorized()
                    .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
        }
    }

    @Test
    void bothProfileEndpointsRejectWrongCredentials() {
        for (String path : PROFILE) {
            client.get().uri(path)
                    .headers(h -> h.setBasicAuth("reader", "wrong-pass"))
                    .exchange()
                    .expectStatus().isUnauthorized();
        }
    }

    @Test
    void bothProfileEndpointsReturnTheSameVerifiedUser() {
        for (String path : PROFILE) {
            client.get().uri(path)
                    .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                    .exchange()
                    .expectStatus().isOk()
                    .expectBody()
                    .jsonPath("$.username").isEqualTo("reader");
        }
    }

    @Test
    void bothAdminEndpointsRequireRoleAdmin() {
        for (String path : ADMIN) {
            client.get().uri(path)
                    .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                    .exchange()
                    .expectStatus().isForbidden();

            client.get().uri(path)
                    .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                    .exchange()
                    .expectStatus().isOk();
        }
    }

    @Test
    void bothInternalEndpointsAreDeniedEvenForAdmin() {
        for (String path : INTERNAL) {
            client.get().uri(path)
                    .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                    .exchange()
                    .expectStatus().isForbidden();
        }
    }

    @Test
    void newUnlistedUrlCannotBeAccessedEvenWithLogin() {
        client.get().uri("/unlisted")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void sharedServiceEmitsTheSameShapeForBothAdapters() {
        StepVerifier.create(profiles.profile("alice", "annotated"))
                .expectNext(Map.of(
                        "username", "alice",
                        "source", "annotated"))
                .verifyComplete();

        StepVerifier.create(profiles.profile("alice", "functional"))
                .expectNext(Map.of(
                        "username", "alice",
                        "source", "functional"))
                .verifyComplete();
    }
}
~~~

Run:

~~~bash
gradle test
~~~

**Expected result:** 8 tests PASS and Gradle prints BUILD SUCCESSFUL when code/dependencies are entered properly, JDK/Gradle meet requirements, and the app boots cleanly.

### 8.1. What Is Tested?

- **Public parity:** both Controller and `RouterFunction` let guests access the same public data type.
- **Authentication parity:** both return 401 when credentials are missing or the password is wrong.
- **Identity parity:** valid requests both use the name from the verified principal, never hardcoding usernames.
- **Role parity:** both reject `ROLE_USER` and accept `ROLE_ADMIN` in the admin area.
- **Deny parity:** neither internal route can be viewed even by `admin`.
- **Fail-closed:** unlisted URLs are denied when a user is logged in, never randomly returning 404/200 depending on route order.
- **Shared service:** data logic is reused; `StepVerifier` tests verify `Mono` signals and mapped output.

**Limitation of service unit tests:** `StepVerifier` calling `profiles.profile` directly bypasses HTTP security. It only confirms the same method returns the expected data. To know the policy is actually enforced, you must use `WebTestClient` as in the tests above.

### 8.2. Why Not Assert JSON Bodies as Fixed Strings?

A `Map` can serialize with arbitrary key order, which is not a security guarantee. Asserting fields with `jsonPath`, or decoding into a DTO and comparing properties, is far more reliable than comparing raw JSON strings. Note that testing statuses, headers, unauthenticated behavior, and authorized/over-privileged cases still matters more than pure formatting.

### 8.3. When Adding a New RouterFunction, Update Tests First

For example, suppose the team adds:

~~~java
.GET("/api/admin/export", request ->
        ServerResponse.ok().bodyValue(Map.of("export", "ok")))
~~~

Because the route sits under `/api/admin/**`, the central rule still requires `ROLE_ADMIN`. Add guest/reader/admin tests for the new URL to catch regressions. Conversely, if accidentally added under `/reports/export`, `anyExchange().denyAll()` denies it; that signals the developer must **explicitly decide the policy before opening the route**.

Never run tests calling `RouterFunction.route()` in isolation and conclude the app is secure: that style skips `SecurityWebFilterChain`, the authentication manager, and other `WebFilter`s.

## 9. Avoiding Vulnerabilities During Controller ↔ RouterFunction Refactoring

Consider a refactoring plan from:

~~~java
@GetMapping("/api/orders/{id}")
public Mono<OrderDto> byId(@PathVariable String id) {
    return orderService.loadForCurrentUser(id);
}
~~~

to:

~~~java
// Integration illustration; handler must be implemented in the application.
return RouterFunctions.route()
        .GET("/api/orders/{id}", orderHandler::byId)
        .build();
~~~

To migrate safely:

1. **Preserve the HTTP contract**: URL, method, required Content-Type/Accept, path variables, response schema, status, and media types.
2. **Preserve the security path**: do not change `/api/orders/{id}` to `/func/orders/{id}` if authorization rules still match `/api/**`.
3. **Preserve caller identity**: Controllers can accept `Principal`/`Authentication`, while `RouterFunction` must read from `ServerRequest.principal()` or Reactor `SecurityContext`; never default principals from query strings.
4. **Preserve service policy**: invoke the same service checking owner/tenant, rather than moving data queries directly into the handler and skipping permissions.
5. **Preserve exception behavior**: `@RestControllerAdvice` and `RouterFunction` filters have different scopes; ensure no branch leaks stack traces or blocked data.
6. **Preserve observability**: actor IDs, correlation IDs, auditing, and metrics must not be dropped when switching handlers.
7. **Preserve test coverage**: run matrix tests for both old and new versions during transition; test 401/403/2xx, ownership, and CSRF on write methods.
8. **Protect unpublished routes**: `anyExchange().denyAll()` still blocks new paths until rules are approved.

### 9.1. Do Not Register Two Handlers on the Same Path/Method and Guess

If both a Controller and a `RouterFunction` declare `GET /api/orders/42`, know which `HandlerMapping` is chosen and its exact configuration order. WebFlux supports both styles inside the same `DispatcherHandler`, yet **security does not run twice for both and pick the safer branch**.

Use separate URLs during migration or keep only one active mapping per method+path at a time. If two routes must coexist temporarily, determine routing order explicitly and test with real HTTP requests.

### 9.2. Router Order Is Not Authorization Order

In `RouterFunctions.route()`, functional routes are normally tried **in declaration order**. When there is a broad dynamic route:

~~~java
return RouterFunctions.route()
        .GET("/api/items/special", handler::special)
        .GET("/api/items/{id}", handler::byId)
        .build();
~~~

Put `/special` before `/{id}` so the specific route is not treated as an `id` path variable. In Controllers, annotation routing selects mappings by specificity; do not assume the two route-priority mechanisms are identical.

Yet **both are independent of `authorizeExchange` order**. Security rules are evaluated in their own declaration order; a right route with a wrong security rule still leaks permissions, and a right security rule with a wrong route can invoke the wrong handler.

### 9.3. Nested RouterFunction and Effective Prefixes

If using:

~~~java
return RouterFunctions.route()
        .path("/api", api -> api
                .GET("/orders", handler::list)
                .GET("/admin/report", handler::report))
        .build();
~~~

The final HTTP paths are `/api/orders` and `/api/admin/report`. Verify the **full path after nesting**, rather than comparing literal strings `"/orders"` or `"/admin/report"` in source against `pathMatchers`.

Policies in `SecurityWebFilterChain` must match **the URI the client actually calls**, not where files/classes/router builders live. Behind a reverse proxy rewriting prefixes, test the path **the application actually sees**, not just the gateway URL.

### 9.4. Every Handler Should Use One Standard for Caller Identity

In Controllers, you can use the **`Mono<Principal>`** method parameter or Spring Security WebFlux's **`ReactiveSecurityContextHolder.getContext()`**. In `RouterFunction`, use **`ServerRequest.principal()`** or `ReactiveSecurityContextHolder`. Both must originate from the same security pipeline.

Never do this:

~~~java
// Wrong: client-sent header is not a verified identity.
String actor = request.headers().firstHeader("X-User");
~~~

A custom header is trustworthy only if verified by a trusted gateway with an appropriate trust/proxy boundary design. In the demo we use HTTP Basic, so names must come from the principal provided by Spring Security.

### 9.5. Method Security Is Defense in Depth

In large codebases, services may be invoked by HTTP endpoints, queue consumers, schedulers, or internal RPCs. Protecting HTTP paths does not automatically protect every other entry point. Enforce policies at the service/data layer, combining reactive method security, message-consumer authorization, and owner checks as needed. Maintain **a single source of business authorization truth** so Controllers and `RouterFunction` never reach conflicting conclusions.

## 10. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Protecting Controller URLs while forgetting `RouterFunction` URLs | Functional endpoint exposed or inverted policy | Align namespaces + test both |
| Checking roles only in `RouterFunction.filter()` | Controllers lack matching protection | `SecurityWebFilterChain` and shared service policy |
| Relying solely on `@PreAuthorize` on Controller methods | Functional handlers lack equivalent annotations | Centralized HTTP authorization + method security on shared service |
| Placing `/api/**.authenticated` before `/api/admin/**.hasRole` | Admin rule shadowed, both handlers exposed | Specific rules before broad rules |
| Using `/public/**.permitAll` and adding a debug route underneath | Debug data accidentally public | Exact public allowlist or prefix governance |
| Using `anyExchange().permitAll` during dev and forgetting to change it | New URLs automatically public | `anyExchange().denyAll()` |
| Assuming `RouterFunction` uses Servlet's `SecurityFilterChain` | Wrong stack in WebFlux | `ServerHttpSecurity`, `SecurityWebFilterChain`, `WebFilter` |
| Writing matchers based on class names | Matcher fails to match actual paths | Use HTTP exchange method/path |
| Putting GET on `RouterFunction` and POST in security rule thinking GET is protected | Wrong method controlled | Align method matrix |
| Changing route prefix during refactor without updating policy | Policy miss/bypass | Test URLs after refactoring |
| Testing only handler unit methods | Skips `WebFilter`/authentication/authorization | Integration tests with `WebTestClient` |
| Reading user ID from query parameters in handler | Caller can spoof subject | Read verified `Principal`/`Authentication` |
| Treating `authenticated()` as enough for all user data | Any user can probe others' records | Owner/tenant authorization |
| Registering same method+path in two mappings | Unclear which handler wins | Keep one mapping or test explicit order |
| Thinking `permitAll` skips authentication | Bad Basic credentials can still yield 401 | Understand authn/authz separation |
| Disabling CSRF for all POSTs because tests got 403 | Opens forged-request risks | Configure CSRF per browser/client model |
| Assuming 404 on a missed route means security was tested | Route may never have matched; new handler permissions untested | Test real existing endpoints with multiple roles |
| Forgetting `securityMatcher` when using multiple chains | Requests enter unintended chain | Test chain order and actual URLs |
| Protecting WebFlux in service while gateway exposes resources separately | External URLs bypass Spring Security | Analyze topology and enforce at proper boundaries |

## 11. Write Methods, CSRF, and 404/405 Scenarios

The demo uses only GET to isolate URL authorization parity. In production, Controllers with `@PostMapping` or `RouterFunction.POST` introduce additional concerns:

- **POST** under `/public` is not automatically public just because GET on the same path is public.
- **CSRF** protects unsafe methods by default in Spring Security WebFlux. A POST missing a token can return 403 before authorization code runs.
- **CORS preflight `OPTIONS`** usually carries no credentials. For cross-origin browsers, configure CORS with allowed origins/headers/methods and proper `WebFilter` order; never widen `permitAll` across all URLs because preflight returned 401.
- **`DELETE /api/items/{id}`** requires appropriate roles/authorities and ownership checks, not just `authenticated`.
- A URL matching no handler can return **404**, or if the path has a handler for another method can return **405**, yet security filters can return 401/403 **before** routing. Never rely on missed-route statuses to judge permissions of an unexecuted endpoint.

Illustrative method-sensitive policy:

~~~java
.authorizeExchange(ex -> ex
        .pathMatchers(HttpMethod.GET, "/catalog/**").permitAll()
        .pathMatchers(HttpMethod.POST, "/catalog/**")
                .hasAuthority("CATALOG_WRITE")
        .pathMatchers(HttpMethod.DELETE, "/catalog/**")
                .hasRole("ADMIN")
        .anyExchange().denyAll())
~~~

This is a configuration snippet **inside** `SecurityWebFilterChain`, not a standalone Java file. Whether you define a functional route `.POST("/catalog/items")` or a Controller `@PostMapping("/catalog/items")`, both are governed by `CATALOG_WRITE`. When testing POST via `WebTestClient`, supply a CSRF token if CSRF is active and applicable to the request; otherwise tests can fail on CSRF before proving the role rule.

Never disable CSRF just to make all state-changing tests return 200. For APIs using only bearer tokens in `Authorization` headers without browser-attached cookies/credentials, CSRF policy can differ, though it must be evaluated for your authentication model rather than copied blindly.

## 12. Multiple SecurityWebFilterChains and Protection Boundaries

In large applications with multiple chains, one chain can match `/api/**` and another match web pages. Each request traverses **the single matching chain selected**, without merging authorization rules across chains.

Mental model:

~~~text
Chain A, high priority: securityMatcher("/api/**")
  +--> HTTP Basic or Bearer
  +--> /api/admin/** hasRole ADMIN
  +--> /api/** authenticated

Chain B, low priority:
  +--> form login or public web
  +--> anyExchange denyAll / intentional allow
~~~

If a `RouterFunction` moves from `/api/legacy` to `/fn/legacy`, it can shift into Chain B even though business code still calls the same service. Consistency requires checking not only `pathMatchers`, but also **`securityMatcher`**, **`@Order`**, authentication mechanisms, CORS, CSRF, session repositories, and entry points of each chain.

### 12.1. Bind Policies to Capabilities, Not Handler Technologies

During code reviews, instead of asking "is this endpoint a Controller?", ask:

- Is this capability public, authenticated, admin-only, or owner/tenant-scoped?
- What is the actual HTTP path+method after `@RequestMapping` or `RouterFunction` nesting?
- Which `SecurityWebFilterChain` catches the request?
- Which rule matches **first**?
- What will unauthenticated users, regular users, and admins receive?
- Are there new paths from route versioning, proxy prefixes, or rewrites?
- Are there write methods needing CSRF or CORS preflight?
- Does the same business flow have other entry points (queues/GraphQL/gRPC) needing equivalent policies?

**One primary policy** should answer all of these; Controller vs. `RouterFunction` is an HTTP handler implementation detail.

## 13. Review and Testing Workflow to Prevent Regressions

When adding or migrating an endpoint:

1. **Inventory** all Controller and `RouterFunction` mappings with their methods/paths at the application level. Never guess from class or file names.
2. **Classify data sensitivity**: public, private, admin, tenant-bound, owner-bound.
3. **Map central policy** by URL/method before opening the handler. For specific URLs, prefer exact allowlists unless expansion is intentional.
4. **Order rules** from specific to general. Avoid `/api/**` shadowing `/api/admin/**`.
5. **Choose default** `anyExchange().denyAll()` when fail-closed is required.
6. **Share one service** for common business logic and enforce owner/tenant checks in the service/repository.
7. **Build a `WebTestClient` matrix** for guests, invalid credentials, regular users, admins, and unknown paths—covering both Controllers and `RouterFunction`.
8. **Check methods**, not only paths, especially POST/PUT/PATCH/DELETE/OPTIONS.
9. **Verify multiple chains** if `securityMatcher` and `@Order` are used.
10. **Audit production details**: reverse proxy rewrites, context paths, multi-tenant headers, session/JWT behavior, observability, and staging tests.

### 13.1. Parallel Contract Testing

You can expand the test suite using an endpoint/role matrix table:

~~~text
endpoint group    annotated                 functional
public            /public/annotated         /public/functional
profile           /api/profile/annotated    /api/profile/functional
admin             /api/admin/annotated      /api/admin/functional
disabled          /internal/annotated       /internal/functional
~~~

For each group, test the exact same set of roles, HTTP methods, and statuses. This catches bugs when a developer **changes only the `RouterFunction`** and forgets to update authorization rules, or vice versa.

### 13.2. Do Not Rely Solely on Static Analysis

Source reviews and grepping path strings can miss:

- Nested routes with prefixes.
- Class-level `@RequestMapping` combined with method-level mappings.
- Dynamic properties/context paths.
- Multi-chain matchers.
- Reverse proxy rewrites.
- Custom `RequestPredicate` / custom `ServerWebExchangeMatcher`.

Therefore, HTTP integration tests are mandatory to verify that policies apply on the **real execution path**. In production, you can add gateway contract tests or staging e2e tests, without skipping unit tests for services.

## 14. Practice Exercises

1. Convert the annotated profile endpoint to a functional profile endpoint while keeping the same path and service; how do you ensure only one mapping is active at a time?
2. Move functional admin from `/api/admin/functional` to `/functions/admin`. Under the demo policy, how does the response change and why?
3. Swap `/api/**` before `/api/admin/**`. Which tests detect the vulnerability? Explain.
4. Replace the exact public rules with `/public/**.permitAll()`. What happens if someone adds `/public/debug-tokens`?
5. Add `GET /api/catalog/annotated` and `GET /api/catalog/functional`. Which rule do they need if only logged-in users may view them?
6. Add `POST /api/catalog` in both handler styles requiring authority `CATALOG_WRITE`. Beyond authorization, how must CSRF be handled?
7. Write `WebTestClient` tests for both profile endpoints with `reader`/`admin` and missing credentials; compare statuses and usernames.
8. Why does testing a `HandlerFunction` directly fail to verify `SecurityWebFilterChain`?
9. Why does having `@PreAuthorize` on a Controller method not guarantee the corresponding functional endpoint is protected?
10. A `RouterFunction` has nested prefix `/api` and child route `/admin/report`. Which path must the security matcher use?
11. A request is denied with 403, yet the route does not exist. Can you conclude the service's ownership check ran?
12. If an app uses both bearer tokens and form sessions across two chains, what must you review when changing an endpoint's URL?

**Suggested Answers:**

- (1) Register only one mapping per method+path, or toggle explicitly via configuration and HTTP tests.
- (2) It no longer matches `/api/**` and falls into `anyExchange().denyAll()`, usually returning 403 when logged in; URL/policy must be updated intentionally.
- (3) Tests where `reader` calls `/api/admin/annotated` and `/api/admin/functional` must receive 403; receiving 200 indicates a bug.
- (4) Debug routes in the public namespace can become exposed unintentionally, leaking secrets if no other guard exists.
- (5) `/api/**.authenticated()` or an equivalent exact rule.
- (6) Configure authority by HTTP method while keeping and testing appropriate CSRF protection.
- (7) Guest receives 401, valid callers receive 200 with their own identity, regardless of handler style.
- (8) Direct handler unit calls bypass `WebFilter`/authorization.
- (9) Method/controller annotations do not automatically apply to functional `HandlerFunction`s; use centralized `WebFilter` policies or shared service enforcement.
- (10) `/api/admin/report`, not just `/admin/report`.
- (11) No; security can deny before the handler/service ever runs.
- (12) `securityMatcher`/`@Order`, authentication mechanisms, entry points, session/CSRF/CORS, and actual matched URLs.

## 15. References

- Spring Security — Authorize ServerHttpRequest (Reactive): https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — ServerHttpSecurity Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Framework — WebFlux Functional Endpoints: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
- Spring Framework — WebFlux DispatcherHandler: https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html
- Spring Framework — Annotated Controllers in WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
- Spring Boot 3.5 System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html

**Conclusion:** Keeping rules consistent for Controllers and `RouterFunction` means defining **one intentional HTTP authorization rule set** on `SecurityWebFilterChain`, matching the exact URLs/methods of both endpoint styles, ordering rules by specificity, denying by default, and calling the same business service. Test endpoint pairs with `WebTestClient` for guests, invalid credentials, regular users, admins, and unpublished paths; never rely on class names, local route filters, or unit handler tests to assume uniform security.