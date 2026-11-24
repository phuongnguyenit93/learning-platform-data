# ServerHttpSecurity, SecurityWebFilterChain and authorizeExchange

> **Context:** Spring Security – authorization → **HTTP on WebFlux**. This guide explains how to configure HTTP access control in a Spring WebFlux application using `ServerHttpSecurity`, `SecurityWebFilterChain`, and the `authorizeExchange` DSL; distinguishes selecting a **filter chain** from selecting a **rule** inside a chain; and explains the reactive mechanism, default endpoint protection, multiple chains, authentication, CSRF, CORS, customizing `ReactiveAuthorizationManager`, and testing with `WebTestClient`. The main examples use Java 17+, Spring Boot 3.x, and Spring Security 6.x. Optional OAuth2/JWT extensions are noted separately so they are not confused with the standalone HTTP Basic application.

## 1. Three components solving three different tasks

Consider a WebFlux application with these URLs:

~~~text
GET  /health                   public
GET  /api/public/ping          public
GET  /api/reports/summary      requires REPORT_READ
POST /api/reports/publish      requires ROLE_ADMIN + CSRF token
GET  /api/admin/dashboard      requires ROLE_ADMIN
GET  /ui/profile               requires authenticated
GET  /internal/status          deny by default
~~~

We need to answer three questions:

1. **Which security configuration does this request belong to?** Select a `SecurityWebFilterChain` using `securityMatcher(...)` and `@Order`.
2. **Inside the selected chain, which rule matches the URL/method?** `authorizeExchange` with `pathMatchers(...)`, `matchers(...)`, or `anyExchange()`.
3. **What does that rule require?** `permitAll`, `authenticated`, `hasAuthority`, `hasRole`, `denyAll`, or `access(ReactiveAuthorizationManager)`.

| API | Package / nature | Function |
| --- | --- | --- |
| `ServerHttpSecurity` | `org.springframework.security.config.web.server`; builder | Configures WebFlux web filters, CSRF, HTTP Basic, form login, OAuth2, authorization |
| `SecurityWebFilterChain` | `org.springframework.security.web.server`; interface | Filter chain object built by `http.build()`, with a matcher and list of reactive `WebFilter`s |
| `authorizeExchange` | DSL on `ServerHttpSecurity` | Declares authorization decisions for `ServerWebExchange` inside that chain |
| `ServerWebExchangeMatcher` | Reactive matcher | Determines whether an exchange belongs to a chain/rule |
| `ReactiveAuthorizationManager<AuthorizationContext>` | Reactive authorization contract | Enables asynchronous authorization checks, returning `Mono<AuthorizationDecision>` in Spring Security 6.x |
| `WebFilterChainProxy` | WebFlux security infrastructure | Selects and applies the appropriate `SecurityWebFilterChain` |
| `AuthenticationWebFilter` and `AuthorizationWebFilter` | Reactive WebFilters | Perform authentication and enforce authorization at the appropriate positions |

**Do not mix with Servlet:** `HttpSecurity`, `SecurityFilterChain`, `authorizeHttpRequests`, and `HttpServletRequest` belong to the servlet stack. On WebFlux, use `ServerHttpSecurity`, `SecurityWebFilterChain`, `authorizeExchange`, and `ServerWebExchange`. Although the class names are similar, they are not directly interchangeable.

## 2. How does the WebFlux security flow work?

~~~text
HTTP request
     |
     v
Spring WebFlux WebFilter chain
     |
     v
Spring Security WebFilterChainProxy
     |
     +-- select chain by @Order + securityMatcher
     |       |-- /api/** -> API SecurityWebFilterChain
     |       +-- remaining -> fallback SecurityWebFilterChain
     |
     v
WebFilters of the selected chain
     |
     +-- SecurityContext / Authentication
     +-- CSRF, headers, and other protections
     +-- AuthorizationWebFilter per authorizeExchange
     |
     +-- DENY -> AuthenticationEntryPoint/AccessDeniedHandler
     |
     +-- ALLOW -> DispatcherHandler -> Controller/RouterFunction
                                         |
                                         v
                                    Mono / Flux
~~~

WebFlux security uses `WebFilter` and reactive streams; it does not run through the servlet `FilterChainProxy`. Authentication/authorization and related security information are typically propagated via **Reactor Context**. Do not read ThreadLocal-based `SecurityContextHolder` as a default mechanism in WebFlux services and assume the same principal will be present across scheduler hops.

### 2.1. The builder is not the final result

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchange -> exchange
                    .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

`ServerHttpSecurity` is a **configuration builder**; `build()` creates the `SecurityWebFilterChain` that the framework uses when requests arrive. Mutating the builder after building is not how you update policies at runtime; if dynamic policies are needed, `access(...)` should call a consistent policy source/PDP.

### 2.2. What does `@EnableWebFluxSecurity` do?

~~~java
@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {
    // @Bean SecurityWebFilterChain definitions
}
~~~

This annotation imports the Spring Security components required for WebFlux. A minimal setup may let Spring Security provide default authentication/headers/CSRF mechanisms, but in real applications you should declare chains and rules explicitly to control behavior. With the Spring Boot starter, auto-configurations may supply defaults if you have not defined beans yourself; **do not rely on guessing defaults** when endpoints have specific requirements.

Do not use `@EnableWebSecurity` for this WebFlux configuration; that annotation belongs to the servlet stack. If you need Method Security for `Mono`/`Flux`, see `@EnableReactiveMethodSecurity` in a later section.

## 3. `authorizeExchange`: common rules

A simple chain:

~~~java
@Bean
SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/health", "/public/**").permitAll()
                    .pathMatchers("/admin/**").hasRole("ADMIN")
                    .pathMatchers("/reports/**").hasAuthority("REPORT_READ")
                    .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

| Rule | Meaning | Note |
| --- | --- | --- |
| `permitAll()` | No authorization required | Declare only for genuinely public endpoints |
| `authenticated()` | Requires a valid Authentication | Does not automatically know which objects the user may access |
| `hasRole("ADMIN")` | Requires authority `ROLE_ADMIN` by default | Do not add `ROLE_` to the argument of `hasRole` |
| `hasAuthority("REPORT_READ")` | Matches the exact authority string | Does not automatically add a prefix |
| `hasAnyRole("USER","ADMIN")` | One of multiple roles | Still a coarse role, not an object-level scope |
| `denyAll()` | Denies every caller | Useful as a sensitive catch-all |
| `access(manager)` | Applies a custom reactive policy | Must handle missing/timeout and fail closed |

### 3.1. Rules are evaluated in declaration order

**Wrong** example:

~~~java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/**").authenticated()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .anyExchange().denyAll())
~~~

`/api/admin/dashboard` matches `/api/**` first. Because that only requires authentication, the subsequent admin rule is never selected. **Specific rules must come before broad rules.**

Correct:

~~~java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .pathMatchers("/api/**").authenticated()
        .anyExchange().denyAll())
~~~

Also pay attention to method-specific rules: if `GET /api/reports/**` is for readers only, do not put a `/api/reports/**` `permitAll` rule above it and then try to protect POST below. Test GET/POST/PUT/DELETE and path variants.

### 3.2. `pathMatchers` can check the HTTP method

~~~java
.pathMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAuthority("REPORT_READ")
.pathMatchers(HttpMethod.POST, "/api/reports/**")
    .hasRole("ADMIN")
.anyExchange().denyAll()
~~~

This split lets the same URL path have different requirements depending on the HTTP method. `HEAD` and `OPTIONS` should also be considered when public APIs support them; do not carelessly allow all methods because you only thought of GET.

### 3.3. Deny unknown endpoints

~~~java
.anyExchange().denyAll()
~~~

This final rule ensures a controller added later **does not accidentally open access** by falling into an overly broad `authenticated` catch-all. If an application intentionally requires only authentication for all other endpoints, `anyExchange().authenticated()` is also a valid choice, though a different policy. In learning environments with admin or data-sensitive paths, choosing deny-by-default helps reviewers clearly see that new endpoints must be explicitly declared.

### 3.4. HTTP status codes and different mechanisms

| Scenario | Common expectation |
| --- | --- |
| Unauthenticated, endpoint requires authenticated/authority, HTTP Basic | 401 with appropriate challenge |
| Authenticated, missing `ROLE_ADMIN` or authority | 403 |
| Authorized POST without CSRF token when CSRF is enabled | 403 |
| Public endpoint | 200 if controller succeeds; may be 404 if route does not exist |
| Catch-all `denyAll` for an authenticated user | 403 |
| Data/service error in controller | Application-specific error code, not automatically an authentication error |

401/403 responses are affected by the configured `ServerAuthenticationEntryPoint`, `ServerAccessDeniedHandler`, authentication mechanism, and error handling. Do not write tests assuming all failures return the same status code.

## 4. Two levels of rule selection: `securityMatcher` and `pathMatchers`

This is the most common source of confusion.

**Level 1 – selecting the SecurityWebFilterChain:**

~~~java
http.securityMatcher(
        new PathPatternParserServerWebExchangeMatcher("/api/**"));
~~~

The matcher decides **whether this chain applies to the request**.

**Level 2 – `authorizeExchange` inside the selected chain:**

~~~java
http.authorizeExchange(ex -> ex
        .pathMatchers("/api/public/**").permitAll()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .anyExchange().denyAll());
~~~

Rules at level 2 are **evaluated only after the request has entered that chain**.

~~~text
Request GET /api/admin/dashboard
       |
       v
Chain #1 matcher /api/** -> MATCH
       |
       v
Rule /api/public/**     -> no
Rule /api/admin/**      -> yes, require ROLE_ADMIN
Rule anyExchange        -> not reached
       |
       v
Authentication + authorization decision
~~~

If chain #1 does not match, Spring Security tries the next chain in order. If **no chain matches**, that request may remain unprotected by Spring Security. Therefore, always have a catch-all fallback chain and test URLs outside `/api/**`. Do not assume `anyExchange().denyAll()` in a chain matching only `/api/**` will automatically protect `/internal/**`.

### 4.1. `@Order` ordering

~~~java
@Bean
@Order(1)
SecurityWebFilterChain api(ServerHttpSecurity http) {
    // /api/** only
}

@Bean
@Order(2)
SecurityWebFilterChain fallback(ServerHttpSecurity http) {
    // applies to the rest
}
~~~

Spring Security chooses the first matching chain; once chosen, it does not merge or combine permissions from later chains. A fallback chain without a `securityMatcher` usually matches every exchange. Place the fallback last so it does not swallow every request before the API chain is evaluated.

### 4.2. Policies across chains can differ

| Scope | Authentication | CSRF | Authorization |
| --- | --- | --- | --- |
| `/api/**` serving browser + HTTP Basic demo | HTTP Basic | Keep enabled to demonstrate safe POST | GET public, REPORT_READ, ADMIN, deny unknown |
| `/ui/**` | HTTP Basic in demo; real apps may use form login/session | Keep enabled when browsers use cookies/sessions | Authenticated |
| `/internal/**` | No access path created | N/A | `denyAll` in fallback |
| `/health` | Public | No unsafe methods | `permitAll` |
| Truly stateless bearer-token API | OAuth2 resource server | May consider disabling when **only** Authorization header is used and not auto-sent by browser | Scope/roles + object policy |

HTTP Basic **does not automatically mean** a stateless API is immune to CSRF: browsers can automatically attach Basic credentials, so CSRF must be considered for state-changing endpoints. This sample **does not disable CSRF** and will test the missing-token case.

## 5. Runnable example: Spring Boot 3.x + WebFlux + HTTP Basic

The sample has complete files and tests. Setup choices:
- Java 17;
- Gradle;
- Spring Boot `3.3.5` (a specific Boot 3.x release for the example, with Spring Security 6.x dependency management);
- Spring WebFlux, without `spring-boot-starter-web`;
- `MapReactiveUserDetailsService` with bcrypt passwords for demo purposes;
- Two `SecurityWebFilterChain` beans and reactive controllers returning `Mono<String>`.

**Do not use this user list in production**; these credentials are only for learning and integration tests. Production requires appropriate identity sources, passwords, MFA, rate limiting, and token/session management.

### 5.1. `settings.gradle`

~~~groovy
rootProject.name = 'webflux-security-demo'
~~~

### 5.2. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.webflux'
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
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

If your project uses another Spring Boot 3.3.x/3.4.x/3.5.x release, let the Boot BOM manage compatible versions; do not force Spring Security 7.x onto Boot 3.x. For production apps on other versions, verify the exact DSL/API before copying.

### 5.3. `src/main/java/demo/webflux/WebFluxSecurityApplication.java`

~~~java
package demo.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxSecurityApplication.class, args);
    }
}
~~~

### 5.4. `src/main/java/demo/webflux/SecurityConfiguration.java`

~~~java
package demo.webflux;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher(
                                "/api/**"))
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(
                                HttpMethod.GET, "/api/public/**")
                        .permitAll()
                        .pathMatchers(
                                HttpMethod.GET, "/api/reports/**")
                        .hasAuthority("REPORT_READ")
                        .pathMatchers(
                                HttpMethod.POST, "/api/reports/**")
                        .hasRole("ADMIN")
                        .pathMatchers("/api/admin/**")
                        .hasRole("ADMIN")
                        .anyExchange().denyAll())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                // Keep CSRF at its default: enabled.
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(
                                HttpMethod.GET, "/health")
                        .permitAll()
                        .pathMatchers("/ui/**")
                        .authenticated()
                        .anyExchange().denyAll())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails viewer = User.withUsername("viewer")
                .password(encoder.encode("viewer-pass"))
                .authorities("REPORT_READ")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .authorities("REPORT_READ", "ROLE_ADMIN")
                .build();

        return new MapReactiveUserDetailsService(viewer, admin);
    }
}
~~~

**Line-by-line breakdown:**

1. `@EnableWebFluxSecurity` initializes the WebFlux security infrastructure.
2. `apiSecurity` at `@Order(1)` accepts only paths matching `/api/**`.
3. The API `authorizeExchange` distinguishes GET public, GET reports, POST reports, and admin routes; finally it denies all other API URLs/methods.
4. `httpBasic(withDefaults())` enables HTTP Basic; `formLogin(form -> form.disable())` prevents returning an HTML login page when an API client is unauthenticated.
5. `csrf(...disable())` is not declared, so WebFlux CSRF remains **enabled by default** for unsafe methods.
6. `fallbackSecurity` at `@Order(2)` has no matcher restriction and covers requests that do not enter the API chain.
7. `/health` is public, `/ui/**` requires authentication, and everything else in the fallback chain is denied.
8. `MapReactiveUserDetailsService` is an in-memory user store (reactive contract). Passwords use an encoder with the appropriate prefix; do not use `{noop}` in real products.
9. `hasRole("ADMIN")` looks for `ROLE_ADMIN`, so `admin` has that exact authority; `viewer` only has `REPORT_READ`.

**Note on `/api` (without trailing slash):** `/api/**` should not be assumed to protect every variant such as `/api`, `/api/`, different casing, or URL-encoded paths. Test the exact paths that your gateway/framework actually routes. A fallback with `denyAll` helps stop an unexpected URL from slipping past protection.

### 5.5. `src/main/java/demo/webflux/ExampleController.java`

~~~java
package demo.webflux;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ExampleController {

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("OK");
    }

    @GetMapping("/api/public/ping")
    public Mono<String> publicPing() {
        return Mono.just("PONG");
    }

    @GetMapping("/api/reports/summary")
    public Mono<String> reportSummary() {
        return Mono.just("summary");
    }

    @PostMapping("/api/reports/publish")
    public Mono<String> publishReport() {
        // Demo only returns a string; production must authorize both
        // the target resource and the business operation.
        return Mono.just("published");
    }

    @GetMapping("/api/admin/dashboard")
    public Mono<String> adminDashboard() {
        return Mono.just("dashboard");
    }

    @GetMapping("/ui/profile")
    public Mono<String> profile() {
        return Mono.just("profile");
    }

    @GetMapping("/api/unknown")
    public Mono<String> unknownApi() {
        return Mono.just("should-not-be-accessible");
    }

    @GetMapping("/internal/status")
    public Mono<String> internalStatus() {
        return Mono.just("internal-secret");
    }
}
~~~

**Creating a route does not grant access to it.** The last two routes intentionally exist to test deny-by-default even when a request actually has a handler.

The controller returns simple `Mono` values without side effects so the exercise stays focused on HTTP authorization. In real systems, business services must still enforce object-level checks on tenant, owner, status, and permission; `ROLE_ADMIN` at the HTTP layer **does not automatically** grant access to every document.

## 6. Integration tests: `WebTestClient` with real Spring Security

Spring Security provides reactive HTTP test support. One strong option is:

~~~java
WebTestClient.bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();
~~~

This creates a client that passes through the WebFlux application context and security filters without opening a TCP port. `WebTestClient.bindToController(new Controller())` **alone** does not prove that the application's security chains are wired properly.

### 6.1. `src/test/java/demo/webflux/WebFluxSecurityTests.java`

~~~java
package demo.webflux;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

@SpringBootTest(
        classes = WebFluxSecurityApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class WebFluxSecurityTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void healthIsPublicThroughFallbackChain() {
        client.get().uri("/health")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("OK");
    }

    @Test
    void publicApiIsPublicWithoutCredentials() {
        client.get().uri("/api/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("PONG");
    }

    @Test
    void protectedReportWithoutAuthenticationReturns401() {
        client.get().uri("/api/reports/summary")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void viewerMayReadReports() {
        client.get().uri("/api/reports/summary")
                .headers(h -> h.setBasicAuth(
                        "viewer", "viewer-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("summary");
    }

    @Test
    void wrongPasswordDoesNotAuthenticate() {
        client.get().uri("/api/reports/summary")
                .headers(h -> h.setBasicAuth(
                        "viewer", "wrong"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void viewerCannotAccessAdminDashboard() {
        client.get().uri("/api/admin/dashboard")
                .headers(h -> h.setBasicAuth(
                        "viewer", "viewer-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminMayAccessAdminDashboard() {
        client.get().uri("/api/admin/dashboard")
                .headers(h -> h.setBasicAuth(
                        "admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("dashboard");
    }

    @Test
    void viewerCannotPublishEvenWithCsrfToken() {
        client.mutateWith(csrf())
                .post().uri("/api/reports/publish")
                .headers(h -> h.setBasicAuth(
                        "viewer", "viewer-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminWithoutCsrfCannotPublish() {
        client.post().uri("/api/reports/publish")
                .headers(h -> h.setBasicAuth(
                        "admin", "admin-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminWithCsrfMayPublish() {
        client.mutateWith(csrf())
                .post().uri("/api/reports/publish")
                .headers(h -> h.setBasicAuth(
                        "admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("published");
    }

    @Test
    void viewerCanAccessAuthenticatedUi() {
        client.get().uri("/ui/profile")
                .headers(h -> h.setBasicAuth(
                        "viewer", "viewer-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("profile");
    }

    @Test
    void uiRequiresAuthentication() {
        client.get().uri("/ui/profile")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedUserCannotAccessUnknownApi() {
        client.get().uri("/api/unknown")
                .headers(h -> h.setBasicAuth(
                        "admin", "admin-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void authenticatedAdminCannotBypassFallbackDenyAll() {
        client.get().uri("/internal/status")
                .headers(h -> h.setBasicAuth(
                        "admin", "admin-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

**Two static imports wrapped at a Java-valid line break:** this is an important note when copying the source. In Java, `import static org.springframework.security.test.web.reactive.server` wraps onto a line starting with `.SecurityMockServerConfigurers.springSecurity;`; to avoid confusion and copy cleanly, write them on a single line in your IDE as follows:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
~~~

These are the **two actual imports needed** in the test file above. `springSecurity()` attaches Spring Security test support to the client; `csrf()` generates an appropriate test CSRF token to distinguish CSRF denials from role denials.

### 6.2. Test matrix

| Request | Caller | CSRF | Expected |
| --- | --- | --- | --- |
| GET /health | Anonymous | N/A | 200 |
| GET /api/public/ping | Anonymous | N/A | 200 |
| GET /api/reports/summary | Anonymous | N/A | 401 |
| GET /api/reports/summary | viewer (REPORT_READ) | N/A | 200 |
| GET /api/reports/summary | viewer wrong password | N/A | 401 |
| GET /api/admin/dashboard | viewer | N/A | 403 |
| GET /api/admin/dashboard | admin | N/A | 200 |
| POST /api/reports/publish | viewer | Valid | 403 because missing ROLE_ADMIN |
| POST /api/reports/publish | admin | Missing | 403 because CSRF |
| POST /api/reports/publish | admin | Valid | 200 |
| GET /ui/profile | viewer | N/A | 200 |
| GET /ui/profile | Anonymous | N/A | 401 |
| GET /api/unknown | admin | N/A | 403 |
| GET /internal/status | admin | N/A | 403 |

Testing both **a caller lacking permission** and **an authorized caller missing CSRF** prevents false conclusions: a 403 error does not necessarily originate from `authorizeExchange`. Debugging security logs and tests requires separating authentication, authorization, CSRF, and controller routing.

### 6.3. Running the example

With the project's Gradle wrapper:

~~~bash
./gradlew test --tests demo.webflux.WebFluxSecurityTests
./gradlew bootRun
~~~

Windows:

~~~text
gradlew.bat test --tests demo.webflux.WebFluxSecurityTests
gradlew.bat bootRun
~~~

Test requests while the server is running:

~~~bash
curl -i http://localhost:8080/health
curl -i http://localhost:8080/api/public/ping
curl -i -u viewer:viewer-pass http://localhost:8080/api/reports/summary
curl -i -u viewer:viewer-pass http://localhost:8080/api/admin/dashboard
curl -i -u admin:admin-pass http://localhost:8080/api/admin/dashboard
~~~

Those GET commands are expected to return bodies `OK`, `PONG`, `summary`, 403, and `dashboard` respectively. With `curl`, credentials after `-u` are only for local demos; never put real passwords into shell history or public logs. POST requests using CSRF require the corresponding token/session; the `mutateWith(csrf())` test demonstrates that exact condition.

This example has no `System.out.println`, so JVM/server stdout depends on Gradle, logging configuration, and version. The fixed contract is only the **HTTP status/body verified by the tests**, not the startup log lines.

## 7. Deeper look at the two selection tiers

### 7.1. Why is fallback `denyAll` important?

If you only declare:

~~~java
@Bean
SecurityWebFilterChain api(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(ex -> ex.anyExchange().authenticated())
            .build();
}
~~~

then `/health`, `/internal/status`, and `/ui/profile` do not enter the `/api/**` chain. If no other chain matches, they **may sit outside Spring Security's protection**. Therefore, `anyExchange().authenticated()` inside this chain cannot be treated as "every application request must authenticate." It means **every exchange selected into this chain** must authenticate.

### 7.2. What if the fallback is at `@Order(1)`?

~~~text
Chain fallback: match all, @Order(1)
Chain API:      match /api/**, @Order(2)
GET /api/admin/dashboard
   |
   +-- fallback matches all first -> fallback selected
   +-- API chain is no longer evaluated
~~~

Even if the API chain has a strict `hasRole("ADMIN")` rule, it will not execute for this request. Always test boundary paths and verify chain ordering.

### 7.3. Why must `anyExchange` come last?

In `authorizeExchange`, declaration order determines which rule is tried first. If you put `anyExchange().authenticated()` before `pathMatchers("/api/admin/**").hasRole("ADMIN")`, every request already satisfies the broad rule, shadowing the admin rule. Some DSL versions may raise an error when rules are added after a terminal matcher; even as handling evolves across versions, **the design must still place the catch-all last**.

### 7.4. Multi-application setups and gateway routing

If a gateway rewrites URLs before WebFlux receives them, patterns must match the **actual path inside the Spring Security server**, not just the external public URL. Security path matching generally does not know that `/gateway/api/admin` was rewritten to `/api/admin` unless the Spring exchange reflects the true path. Test with gateway integration/casing and encoded paths, rather than casually using `startsWith("/api")` string prefixes in place of framework matchers.

## 8. `hasRole`, `hasAuthority`, and business scope

In the example:

~~~text
viewer authorities = [REPORT_READ]
admin  authorities = [REPORT_READ, ROLE_ADMIN]
~~~

- `hasAuthority("REPORT_READ")` requires the exact string `REPORT_READ`.
- `hasRole("ADMIN")` checks `ROLE_ADMIN` by default.
- `hasRole("ROLE_ADMIN")` can result in a duplicate/wrong prefix; use `hasAuthority("ROLE_ADMIN")` if you want to match the full string.
- `authenticated()` only requires the caller to be authenticated; it does not check object owner or tenant.

If a report belongs to tenant `acme` while the caller belongs to `beta`, a coarse `REPORT_READ` authority may **not be enough**. You need per-resource and per-tenant policies **in the service layer** or a custom manager. Do not treat HTTP rules as a replacement for object-level authorization.

For example, a document-access service should verify:

~~~text
authenticated user
AND has REPORT_READ
AND resource.tenantId == actor.activeTenant
AND user has allowed permission for resource
AND document not archived/locked as business rule
~~~

Resources can also be accessed from background jobs, message consumers, or GraphQL, so enforcing checks in the service avoids depending solely on URIs.

## 9. Custom `ReactiveAuthorizationManager` with `access(...)`

When simple rules are insufficient, `authorizeExchange` supports a custom reactive authorization manager. In Spring Security 6.x, the contract receives `Mono<Authentication>` and `AuthorizationContext` and returns `Mono<AuthorizationDecision>` (it can complete without a decision depending on framework semantics, so design it to return an explicit DENY when data is missing).

### 9.1. Example that can be registered in configuration as a `@Bean`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.web.server.authorization.AuthorizationContext;
import reactor.core.publisher.Mono;

@Bean
ReactiveAuthorizationManager<AuthorizationContext> exportPolicy() {
    return (authentication, context) -> authentication
            .map(auth -> new AuthorizationDecision(
                    auth.isAuthenticated()
                    && auth.getAuthorities().stream()
                        .anyMatch(a ->
                            "EXPORT_REPORTS".equals(a.getAuthority()))))
            .defaultIfEmpty(new AuthorizationDecision(false));
}
~~~

Usage in configuration:

~~~java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/api/exports/**")
        .access(exportPolicy)
        .anyExchange().denyAll())
~~~

**These are illustrative integration snippets, not standalone Java files.** The `exportPolicy` bean can be injected as a parameter of the chain configuration method or via a constructor field. If placed in the same `SecurityConfiguration` class from the example, add the `/api/exports/**` route, the appropriate bean/parameter, and place the rule before the catch-all. An `exportPolicy()` method on a `@Configuration` class can be managed as a bean, but do not arbitrarily invoke a helper outside the Spring context and expect interceptors to still apply.

### 9.2. Async decisions fetching data from WebFlux and repositories

A real-world policy may need R2DBC, Redis, or an HTTP PDP:

~~~java
// LOGIC ILLUSTRATION, not a standalone class.
return authentication
        .flatMap(auth ->
                reactivePolicyRepository.canExport(
                        auth.getName(),
                        tenantFromTrustedContext,
                        resourceId))
        .map(AuthorizationDecision::new)
        .defaultIfEmpty(new AuthorizationDecision(false))
        .onErrorReturn(new AuthorizationDecision(false));
~~~

`reactivePolicyRepository`, `tenantFromTrustedContext`, and `resourceId` must be obtained from trusted sources. `onErrorReturn(deny)` is a fail-closed choice; in production you may distinguish "unauthorized" (403) from "policy service unavailable" (503), but **never** turn a timeout into allow.

**Do not call `.block()` directly on the event loop** to fetch policy results. If a policy requires blocking JDBC, offload the blocking work onto an appropriate scheduler in a controlled manner or prefer genuinely reactive drivers/repositories; never block Netty threads. For a remote PDP, configure timeouts, circuit breakers, versioned caching, auditing, and non-amplifying retries.

### 9.3. Why should you not infer the tenant from the path alone?

`AuthorizationContext` provides the `ServerWebExchange` and request details; however, a `tenantId` appearing in the URL **does not prove** the user is allowed to access that tenant. You must verify membership from the trusted principal and determine which tenant the resource belongs to from the database. In particular, never treat arbitrary request headers as proof of `ROLE_ADMIN` or tenant membership.

## 10. HTTP Basic, form login, JWT resource server: choosing the right mechanism

### HTTP Basic in the sample

`httpBasic(withDefaults())` makes observing 401/403 straightforward. However, Basic carries credentials on every request, so it must use HTTPS and appropriate rate-limiting; secrets must never be hardcoded in production source. Browsers can automatically send Basic credentials, so do not mechanically disable CSRF when state-changing endpoints exist.

### Form login/session

`formLogin(withDefaults())` can fit browser applications. When logging in with form/session cookies, CSRF is a critical component. For SPAs using cookies, understand cookie `SameSite`, CSRF token repositories, CORS, and session fixation; do not conflate CORS with CSRF.

### OAuth2 resource server JWT for bearer APIs

In production, stateless APIs using Bearer tokens commonly use:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
~~~

And add a configured API chain:

~~~java
// ADDITIONAL ILLUSTRATION: replace HTTP Basic in the API chain
// with OAuth2 resource server using a suitable JWT verifier.
http
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(
            org.springframework.security.config.Customizer.withDefaults()));
~~~

The Issuer URL is verified against your project's identity provider, for example in `application.properties`:

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://idp.example.invalid/issuer
~~~

`example.invalid` is an illustrative address, not a real JWT endpoint; use a real issuer in deployment environments. When using bearer tokens via the `Authorization` header without cookies or automatic browser credentials, you may consider disabling CSRF **for that specific stateless chain**; if the same chain also accepts cookies/sessions, re-evaluate. Do not disable CSRF merely because the request body is JSON.

Do not mix an incomplete JWT configuration lacking an issuer/JWK verifier with the HTTP Basic example and assume the standalone test project still runs. The two models are separate deployment approaches.

## 11. CSRF on WebFlux: authorization can be right while POST is still blocked

By default, Spring Security WebFlux enables CSRF. CSRF aims to stop malicious websites from tricking a browser with existing credentials into automatically performing state changes.

~~~text
POST /api/reports/publish
Authorization: Basic (admin)
CSRF header/token: missing
  |
  +-- Authentication valid
  +-- ROLE_ADMIN true
  +-- CsrfWebFilter denies
  |
  v
403 Forbidden
~~~

Adding the appropriate token:

~~~java
client.mutateWith(csrf())
        .post().uri("/api/reports/publish")
        .headers(h -> h.setBasicAuth("admin", "admin-pass"))
        .exchange()
        .expectStatus().isOk();
~~~

In a real browser/session application, the token must be issued and sent according to the configured repository/handler; `mutateWith(csrf())` is a **test helper**, not how production clients send tokens.

### Questions to ask before disabling CSRF

1. Does authentication come from cookies or another mechanism automatically sent by browsers?
2. Are unsafe methods POST/PUT/PATCH/DELETE processed from a browser?
3. Does the API accept Basic Authorization that a browser might send automatically?
4. Do clients exclusively use Bearer Authorization headers explicitly attached by JavaScript/mobile clients, or is there a mix of mechanisms?
5. Are there cross-origin requests/SSO or proxies/gateways affecting headers?
6. Are there integration tests proving CSRF neither creates a bypass nor falsely blocks valid endpoints?

Only when the threat model allows should you disable CSRF **on the exact chain that needs it**:

~~~java
// ILLUSTRATION for a stateless API not using browser-auto credentials:
http.csrf(csrf -> csrf.disable());
~~~

Disabling it on the browser fallback chain can strip session-based UIs of essential protection. This sample **keeps CSRF enabled**.

## 12. CORS and preflight are not authorization

A browser may send:

~~~text
OPTIONS /api/reports/summary
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: Authorization
~~~

CORS decides which origins a **browser** is allowed to share responses with. It is not a policy granting permission to read reports. A request that does not involve CORS (curl/service-to-service) must still pass Authentication and Authorization.

An illustrative reactive CORS configuration:

~~~java
// ILLUSTRATION inside @Configuration:
@Bean
org.springframework.web.cors.reactive.CorsConfigurationSource corsSource() {
    var cors = new org.springframework.web.cors.CorsConfiguration();
    cors.setAllowedOrigins(
            java.util.List.of("https://app.example.com"));
    cors.setAllowedMethods(
            java.util.List.of("GET", "POST", "OPTIONS"));
    cors.setAllowedHeaders(
            java.util.List.of("Authorization", "Content-Type",
                    "X-CSRF-TOKEN"));

    var source = new org.springframework.web.cors.reactive
            .UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", cors);
    return source;
}
~~~

**Note when copying:** for the snippet above to compile, put `UrlBasedCorsConfigurationSource` on a proper import line or use a fully qualified name without breaking the package name across lines in invalid Java syntax. Use the exact snippet:

~~~java
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;
~~~

Then add `http.cors(withDefaults())` to the relevant chain and configure the CORS source as required by your Spring Security version. If preflight is blocked by authorization before CORS is properly handled, browsers will report an error; do not solve this by opening `permitAll("/**")`. Allow only the necessary origins/methods/headers, and when cookies are involved verify `allowCredentials` plus explicit allowed origins (never an uncontrolled wildcard).

## 13. Reactive Method Security and object-level permissions

The HTTP layer usually sees only the URI, method, and authorities; permissions on a specific Document require inspecting the resource.

Spring Security WebFlux provides:

~~~java
@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfiguration {
}
~~~

A simple service:

~~~java
@Service
public class DocumentReader {
    @PreAuthorize("hasAuthority('DOC_READ')")
    public Mono<String> readDocument(String id) {
        return repository.findById(id)
                .map(Document::getContent);
    }
}
~~~

**This is a conceptual snippet**, where `repository` and `Document` must be defined. The annotation only checks `DOC_READ` authority; **it does not yet check the tenant/owner of the ID**. To enforce object-level protection, add a policy bean with a trusted reactive lookup or constrain queries by tenant/owner and deny when not found. Do not use servlet `@EnableMethodSecurity` when intentionally implementing reactive method authorization; use the reactive configuration for this stack.

### Reactor Context instead of assumed ThreadLocal

In a reactive flow, the user context can be accessed via `ReactiveSecurityContextHolder`:

~~~java
// ILLUSTRATION SNIPPET inside a reactive service:
return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
~~~

Creating new threads or manually calling `subscribe()` inside a service can lose context or break transaction/error lifecycles. Compose `Mono`/`Flux` and let the framework subscribe. Do not use `Thread.sleep()`, `block()`, or blocking JDBC repositories directly on the Netty event loop.

## 14. Functional endpoints also need security

WebFlux can use annotated controllers or RouterFunctions:

~~~java
// ROUTER FUNCTION ILLUSTRATION:
@Bean
RouterFunction<ServerResponse> routes() {
    return RouterFunctions.route(
            RequestPredicates.GET("/api/public/fn"),
            request -> ServerResponse.ok()
                    .bodyValue("fn"));
}
~~~

WebFlux Security is based on `WebFilter`, so it applies to handler functions as well when requests pass through the same WebFlux application. However, router functions do not have `@PreAuthorize` on a corresponding controller method; object-level authorization must live in the service/handler or a custom manager. Test new routes under the same `SecurityWebFilterChain`.

## 15. Common configuration mistakes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| IDE cannot find `ServerHttpSecurity` | Using servlet starter / missing Spring Security WebFlux | Use `spring-boot-starter-webflux` + security |
| `HttpSecurity` in WebFlux config | Mixing Servlet and Reactive stacks | Switch to `ServerHttpSecurity` and `SecurityWebFilterChain` |
| 401 for unauthenticated request | No authentication present | Authenticate properly with HTTP Basic/JWT; check entry point |
| 403 even when logged in | Missing role/authority or CSRF | Distinguish via GET/POST and security logs |
| Every request enters fallback instead of API chain | Wrong `@Order`; match-all fallback comes first | Give the API chain higher priority |
| `/internal/**` is unprotected | Only a chain matching `/api/**` exists | Add a fallback chain with `denyAll` |
| `/api/admin/**` only requires login | `/api/** authenticated` rule placed first | Order specific rules before general ones |
| Role ADMIN does not match | Using `hasRole("ROLE_ADMIN")` or authority missing prefix | Use `hasRole("ADMIN")` or `hasAuthority("ROLE_ADMIN")` |
| Path `/api` behaves differently from `/api/**` | Pattern/route differs from expectation | Test slashes, encoded paths, and path variables |
| Admin POST returns 403 while admin GET returns 200 | Missing CSRF token or different POST rule | Keep CSRF and send a valid token |
| Viewer POST with token still returns 403 | Missing `ROLE_ADMIN` | This is an expected authorization denial |
| `WebTestClient` tests pass but security is not running | `bindToController` does not wire security | Bind to application context and apply `springSecurity()` |
| Opening `permitAll("/**")` to fix CORS | Confusing CORS and authorization | Configure `CorsConfigurationSource`/preflight properly |
| Disabling CSRF unconditionally on Basic API | Browsers can send Basic credentials automatically | Check threat model; keep CSRF for browser-auto credentials |
| Controller calls `.block()` | Blocking the Netty event loop | Compose `Mono`/`Flux`, reactive driver, or controlled `boundedElastic` |
| Reading principal with Servlet ThreadLocal | Reactor Context differs from ThreadLocal | Use `ReactiveSecurityContextHolder` and reactive composition |
| `@PreAuthorize` on Mono does not work | Reactive Method Security not enabled / wrong proxy | Add `@EnableReactiveMethodSecurity`, test Spring context |
| New endpoint is unexpectedly open | Overly broad `authenticated`/`permitAll` catch-all | Use deny-by-default and negative tests |
| Unclear switch between JWT and Basic | Mixing filter mechanisms and configs across chains | Separate chains by path with clear auth mechanisms |
| HTTP authorization passes but user edits another user's object | Checking only coarse roles | Enforce service-level resource/tenant authorization |
| Logs expose Authorization header | Debug logging prints raw credentials | Redact tokens and never log secrets |

## 16. Pre-production review checklist

1. Is the app genuinely running on WebFlux without accidentally pulling in the servlet stack or misusing `HttpSecurity`?
2. Do `SecurityWebFilterChain` beans have clear matchers and `@Order`?
3. Is there a fallback chain protecting requests that do not match specialized chains?
4. Does `authorizeExchange` place specific rules before general rules?
5. Is there `anyExchange().denyAll()` or an intentional catch-all?
6. Are `hasRole`/`hasAuthority` consistent regarding the `ROLE_` prefix and token mapping?
7. Are HTTP methods GET/HEAD/OPTIONS/POST/PUT/PATCH/DELETE tested against the contract?
8. Do state-changing APIs using browser-auto credentials enforce CSRF tokens?
9. Is CORS restricted to trusted origins rather than using `permitAll("/**")` as a workaround?
10. Are authentication mechanisms across HTTP Basic/form/JWT clearly separated, with TLS enabled in production?
11. Do all endpoints enforce object-level policies in the service layer where needed?
12. Is the security context propagated through Reactor Context without manual `.block()` or `.subscribe()`?
13. Do remote/repository-based reactive authorization managers enforce timeouts and fail closed?
14. Does `WebTestClient` test against real Spring Security filters with sufficient positive and negative cases?
15. Are chain selection, fallback, admin routes, and newly added denied routes covered by tests?
16. Have you verified that CSRF 403s are distinct from role 403s?
17. Are gateway rewrites and forwarded headers tested against the exact path Spring actually receives?
18. Do actuator/health/metrics endpoints have explicit policies rather than vague whitelists?
19. Does error handling avoid leaking resource metadata or principals/tokens in logs?
20. Are authorization rules reviewed when upgrading from Spring Security 6.x to 7.x?

## 17. Self-practice exercises

**Exercise 1 – Rule order.** Intentionally move `.pathMatchers("/api/**").authenticated()` above `/api/admin/**`. Write a test where `viewer` accesses the dashboard and observe the discrepancy; then fix it and keep the regression test.

**Exercise 2 – Chain level.** Move `@Order(1)` to the fallback chain and keep the API chain at Order 2. Check which rule `/api/admin/dashboard` hits; fix the order and explain how chain selection differs from rule selection.

**Exercise 3 – Blocking new endpoints.** Create GET `/api/debug/secrets` without declaring a rule. Even `admin` must receive 403 due to `anyExchange().denyAll()`. Only add a narrow rule when officially required.

**Exercise 4 – Method-based authorization.** Add DELETE `/api/reports/{id}`, restricted to `REPORT_DELETE`. Test that `viewer` with only `REPORT_READ` is denied, and `admin` does not automatically get DELETE unless granted.

**Exercise 5 – CSRF.** Keep Basic and default CSRF. Write two admin POST tests with and without `mutateWith(csrf())`; the outcomes must differ. Explain why CSRF should not be disabled just because a controller accepts JSON.

**Exercise 6 – JWT.** Create a dedicated `/api/**` chain for an OAuth2 resource server, adding the resource-server starter and a valid issuer verifier. Test expired tokens, invalid signatures, missing scopes, missing tokens, and tenant object-level denials.

**Exercise 7 – Custom reactive manager.** Write a `ReactiveAuthorizationManager<AuthorizationContext>` that reads a policy repository via R2DBC. Return DENY when no rule exists and never return allow on timeout. Use `.access(manager)` before `anyExchange()`.

**Exercise 8 – Resource scope.** Write a service that reads a `Document` by `id + tenantId` and the principal's active membership. Prove that role `REPORT_READ` does not allow a user in tenant A to read tenant B's data.

**Exercise 9 – CORS.** Allow only `https://app.example.com` to use the `Authorization` header. Test valid and invalid preflight requests and confirm GET still requires authentication when the actual request reaches the server.

**Exercise 10 – Reactive Context.** Create a service using `ReactiveSecurityContextHolder` to obtain the principal and combine it with a repository via `flatMap`. Compare this with manually calling `subscribe()` or `block()` and explain the risks.

**Completion criteria:** You can create and explain `SecurityWebFilterChain` from `ServerHttpSecurity`, distinguish `securityMatcher` from `authorizeExchange.pathMatchers`, master chain/rule ordering, enforce deny-by-default, configure Basic/CSRF correctly, test with `WebTestClient` using Spring Security test support, and never confuse WebFlux with Servlet or HTTP authorization with object-level policy.

## 18. Official references

- Spring Security 6.5 – **WebFlux Security**, explicit config and multiple chains: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security – **Authorize ServerHttpRequest** and `authorizeExchange`: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security 6.5 – **ServerHttpSecurity API**: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security – **Testing Authentication on WebFlux**, `WebTestClient`, `mockUser`: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security – **WebTestClient Security Setup**: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html
- Spring Security 6.5 – **CSRF for WebFlux**: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security – **Reactive Method Security**: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Framework – **WebTestClient**, binding to ApplicationContext: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Security 6.5 – **Migration to Spring Security 7 Configuration**, lambda DSL: https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html
