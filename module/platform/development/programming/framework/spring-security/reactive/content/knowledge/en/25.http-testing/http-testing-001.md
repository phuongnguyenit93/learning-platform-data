# Setting Up WebTestClient with springSecurity()

## 1. Context, Goals, and Scope

This lesson belongs to the **HTTP Testing** section of the **Spring Security - reactive** course. Spring WebFlux processes HTTP using the reactive model, while Spring Security applies security rules through **`SecurityWebFilterChain`**, `AuthenticationWebFilter`, `AuthorizationWebFilter`, the CSRF filter, and Reactor Context. When testing a controller protected by authentication, authorization, or CSRF, **`WebTestClient` must be wired with the proper security test support**; otherwise, the test might exercise the controller without ever passing through the filters and produce results that diverge from the real application.

Spring Security provides the configurer **`SecurityMockServerConfigurers.springSecurity()`** to integrate with `WebTestClient` in **mock server / in-memory** mode. The most important pattern is:

```java
WebTestClient client = WebTestClient
        .bindToApplicationContext(applicationContext)
        .apply(springSecurity())
        .configureClient()
        .build();
```

This is a **setup fragment**, assuming you have imported `springSecurity()` and have an `ApplicationContext` containing WebFlux configuration and `SecurityWebFilterChain`. It is the starting point for mutators such as `mockUser()`, `csrf()`, `mockJwt()`, or `mockOidcLogin()`.

Learning goals:

1. Understand **what `springSecurity()` does** and distinguish it from merely instantiating a plain `WebTestClient`.
2. Properly configure **Gradle dependencies**, `@SpringBootTest`, `WebTestClient.bindToApplicationContext(...)`, `.apply(springSecurity())`, `.configureClient()`, and `@BeforeEach`.
3. Write a **Java 17+, Spring Boot 3.3.5, Spring Security WebFlux 6.3.x** sample application with public routes, an authenticated route, an ADMIN-only route, and a CSRF-protected POST route.
4. Test **401 (unauthenticated)**, **403 (insufficient role/missing CSRF)**, **200 OK**, **201 Created**, and **HTTP Basic with valid/invalid passwords**.
5. Understand the difference between `mockUser()` / `@WithMockUser` and sending **real HTTP Basic** credentials within the same WebTestClient.
6. Use `csrf()` for unsafe HTTP methods when Spring Security CSRF is enabled; recognize that `csrf()` is test support, not proof that an external browser token retrieval flow works.
7. Distinguish **mock in-memory WebTestClient** from **`bindToServer()` / RANDOM_PORT** and understand the limitations of mutators that depend on the test server context.
8. Recognize common mistakes: confusing Servlet `MockMvc` with WebFlux, placing `.apply` in the wrong position, missing security filters, testing every route with a fake principal, or disabling CSRF just to make tests green.
9. Have a checklist, troubleshooting table, exercises, and official documentation to verify test suites in real projects.

**Scope:** This lesson covers **setting up WebTestClient with Spring Security for WebFlux**, not building an OIDC/JWT server. Examples of `mockJwt()`, `mockOAuth2Login()`, or `mockOidcLogin()` are presented as extensions with their limitations explicitly noted.

**Version note:** Spring Boot 3.3.5 is used as the source baseline compatible with Java 17 and Spring Security 6.3.x APIs. When deploying a production project at a later time, use a framework version that is **still supported and patched for security**, and consult the release notes when APIs change.

## 2. What is `WebTestClient`?

`WebTestClient` in `org.springframework.test.web.reactive.server.WebTestClient` is the HTTP testing client for **Spring WebFlux**. It has a syntax close to `WebClient` but provides test-specific assertions:

```java
client.get().uri("/public")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("public-ok");
```

Steps:

- `get()`: builds an HTTP GET request.
- `uri("/public")`: selects the request URI.
- `exchange()`: sends the request to the mock WebFlux handler or real server, depending on the binding.
- `expectStatus()`: asserts the HTTP status.
- `expectHeader()`: checks response headers.
- `expectBody(...)`: asserts JSON/text/binary content.
- `returnResult()` or `returnResult(Class)`: retrieves the result for advanced inspection when truly needed.

### Three common binding modes

| Creation method | What is actually tested | Security note |
| --- | --- | --- |
| `bindToController(controller)` | Controller and test-built infrastructure | Easily **lacks** the production SecurityWebFilterChain; filters must be configured explicitly if you want to test security |
| `bindToApplicationContext(context)` | WebFlux stack and beans in ApplicationContext, **without opening a TCP port** | **Recommended for `springSecurity()`** in this lesson |
| `bindToServer().baseUrl(...).build()` | A real server listening on TCP/HTTPS | Tests network behavior; **do not use in-memory `mockUser()` to fake auth** |

**Key point:** `WebTestClient` is a testing tool; it does not create security rules on its own. Real rules come from the `SecurityWebFilterChain` in the Spring context. `springSecurity()` **does not replace** enabling security and loading the proper configuration.

### Why not use MockMvc for WebFlux?

`MockMvc`/`SecurityMockMvcRequestPostProcessors` are for testing the **Servlet/MVC** stack. For WebFlux, use:
- `WebTestClient`;
- `SecurityMockServerConfigurers.springSecurity()`;
- `SecurityMockServerConfigurers.mockUser()`;
- `SecurityMockServerConfigurers.csrf()`.

Do not copy `MockMvcRequestBuilders`/`SecurityMockMvcRequestPostProcessors.user(...)` and use them with `WebTestClient`. The two stacks have different class names and lifecycles.

## 3. What does `springSecurity()` actually set up?

Correct import:

```java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;
```

The line break between the package and class is only for display; in the complete Java files below, a **single-line** import is used.

According to the Spring Security test API, `springSecurity()` prepares mock-server test support for filters and mutators. When attached to `WebTestClient.bindToApplicationContext(...)`, requests go through the **WebFlux handler with the security filter chain from ApplicationContext**, along with test support to inject `SecurityContext` for mutators/annotations.

Core setup flow:

```java
client = WebTestClient.bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();
```

Exact explanation:

1. `bindToApplicationContext(context)` builds the mock WebFlux handler based on beans/routes/filters from the context.
2. `apply(springSecurity())` attaches the Spring Security test configurer **to the mock-server spec before building**.
3. `configureClient()` transitions to configuring client options (base URL, headers, timeouts, or client-side filters when needed).
4. `build()` creates the `WebTestClient` used in test methods.
5. `mutateWith(mockUser(...))` on a request/client copy creates an **authenticated test principal**, without requiring a real password.
6. `mutateWith(csrf())` supplies a valid CSRF condition for the test request; it does not disable production CSRF.
7. `@WithMockUser` can populate a test security context via Spring TestExecutionListeners when the test runner is properly integrated.

**Do not confuse:** `springSecurity()` is a **test configurer**, whereas `mockUser()`/`csrf()` are **request/client mutators**. You typically `apply(springSecurity())` once when building the in-memory test client and `mutateWith(...)` on individual requests that need simulated identity/CSRF.

### What `springSecurity()` does NOT do

- Does not automatically provision a real user/password in the application.
- Does not replace `@EnableWebFluxSecurity` or `SecurityWebFilterChain`.
- Does not enforce authentication on every route: that is the job of `authorizeExchange`.
- Does not verify fake tokens created by `mockJwt()`: mock JWT bypasses the cryptographic decoder by design.
- Does not prove TLS, real browser cookies, reverse proxies, network timeouts, database persistence, an external IdP, or an end-to-end CSRF token lifecycle.
- Does not turn a `bindToServer()` against a TCP server into an "in-memory mock-user": test mutators require mock-server binding.
- Does not automatically add a CSRF token to every POST; tests must explicitly choose `csrf()` when needed.

## 4. Test request architecture

```text
JUnit 5 / SpringBootTest
        |
        v
Spring ApplicationContext
  ├── SecurityWebFilterChain
  ├── ReactiveUserDetailsService
  ├── Controller / Handler
  └── WebFlux WebFilters
        |
        v
WebTestClient.bindToApplicationContext(context)
        |
        +--> .apply(springSecurity())
        |
        v
WebTestClient (mock in-memory)
        |
        +-- GET /public            -> permitAll -> 200
        |
        +-- GET /me (anonymous)    -> authentication required -> 401
        |
        +-- GET /me + mockUser     -> mock authenticated -> 200
        |
        +-- GET /admin + USER     -> role mismatch -> 403
        |
        +-- GET /admin + ADMIN    -> hasRole ADMIN -> 200
        |
        +-- POST /notes + USER,
        |   no CSRF                 -> 403
        |
        +-- POST /notes + USER,
        |   csrf()                  -> 201
        |
        +-- GET /me + Basic header
            -> real ReactiveUserDetailsService/password verify
            -> 200 or 401
```

Even without opening a TCP port, in-memory tests still pass through **real Spring Security WebFilters**. However, a mock user **does not go through real password verification**. The same test class can contain:
- Authorization tests with `mockUser()`.
- Authentication integration tests with `Authorization: Basic ...`.
- CSRF rule tests with `csrf()`.

By separating these two kinds of assertions, you know which test actually verified which component.

## 5. Sample project: Java 17 / Spring Boot 3.3.5 / Spring WebFlux

The goal is to create a **small, self-contained** project without needing an external database or IdP. Two test users are configured with BCrypt in memory:
- `alice / alice-pass`: has role `USER`.
- `admin / admin-pass`: has role `ADMIN`.

Routes:
- `GET /public`: public.
- `GET /me`: requires an authenticated user.
- `GET /admin`: requires `ROLE_ADMIN`.
- `POST /notes`: requires `ROLE_USER` **and a valid CSRF token**.
- All remaining requests: `denyAll()`.

### 5.1. Project structure

```text
webflux-security-test-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/dev/example/httptests/
    │       ├── HttpTestsApplication.java
    │       ├── SecurityConfig.java
    │       └── DemoController.java
    └── test/
        └── java/dev/example/httptests/
            └── SecurityWebTestClientTests.java
```

All Java files have `package dev.example.httptests;` matching the path. No application.yml is needed: Spring Boot defaults to `localhost:8080` when using `bootRun`, whereas **`@SpringBootTest(webEnvironment = MOCK)` does not open a TCP server**.

### 5.2. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'webflux-security-test-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Important note on `spring-security-test`**:
- `spring-boot-starter-test` brings JUnit 5, Spring Test, WebTestClient tests, and assertion support.
- `spring-security-test` provides **`SecurityMockServerConfigurers.springSecurity()`, `mockUser()`, `csrf()`, `@WithMockUser`**.
- `reactor-test` is useful when testing `Mono`/`Flux` directly with `StepVerifier`, even though this lesson mainly uses WebTestClient.
- Missing `spring-security-test` usually causes a compile error where `SecurityMockServerConfigurers` cannot be found.
- Do not add `spring-boot-starter-web` (Servlet/MVC starter) into a pure WebFlux demo: Spring Boot usually prioritizes MVC when both starters are present.
- With Boot 3.3.5, manage the Spring Security version via the Boot BOM rather than manually picking an incompatible test jar version.

### 5.3. Application main

`src/main/java/dev/example/httptests/HttpTestsApplication.java`:

```java
package dev.example.httptests;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpTestsApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpTestsApplication.class, args);
    }
}
```

This is the main class to run the application; `@SpringBootTest` in tests will load the same Spring application context.

### 5.4. Spring Security reactive configuration

`src/main/java/dev/example/httptests/SecurityConfig.java`:

```java
package dev.example.httptests;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.http.HttpMethod;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService(
            PasswordEncoder encoder) {

        return new MapReactiveUserDetailsService(
                User.withUsername("alice")
                        .password(encoder.encode("alice-pass"))
                        .roles("USER")
                        .build(),
                User.withUsername("admin")
                        .password(encoder.encode("admin-pass"))
                        .roles("ADMIN")
                        .build());
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/me")
                            .authenticated()
                        .pathMatchers(HttpMethod.GET, "/admin")
                            .hasRole("ADMIN")
                        .pathMatchers(HttpMethod.POST, "/notes")
                            .hasRole("USER")
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                // Intentionally do NOT disable CSRF.
                .build();
    }
}
```

**Analysis:**
1. `@EnableWebFluxSecurity` and `ServerHttpSecurity` belong to the **WebFlux** mechanism, not Servlet `HttpSecurity`.
2. `MapReactiveUserDetailsService` holds two test users with BCrypt-encoded passwords. Sample passwords are **for local development only**, never for production.
3. `hasRole("ADMIN")` checks for authority `ROLE_ADMIN`; `hasRole("USER")` checks for `ROLE_USER`. Do not pass the string `ROLE_ADMIN` into `hasRole(...)`: the framework handles the prefix automatically.
4. `httpBasic(...)` allows testing **real** credentials with HTTP Basic, returning a challenge/401 when unauthenticated instead of redirecting to a login page.
5. `formLogin(...disable())` turns off form login for the demo so HTTP test statuses stay clear; if form login is enabled, unauthenticated routes may redirect `302` instead of returning `401`.
6. `csrf(...)` is not disabled: Spring Security WebFlux protects unsafe methods by default. `POST /notes` can still receive **403 due to CSRF**, even when authentication has been mocked successfully.
7. `anyExchange().denyAll()` is deny-by-default: undeclared routes/methods will not accidentally become public.
8. Do not treat HTTP Basic as suitable for production over unencrypted HTTP: HTTPS/TLS must be used on real networks.

### 5.5. WebFlux REST controller

`src/main/java/dev/example/httptests/DemoController.java`:

```java
package dev.example.httptests;

import java.security.Principal;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Mono<String> publicInfo() {
        return Mono.just("public-ok");
    }

    @GetMapping("/me")
    public Mono<Map<String, String>> me(Principal principal) {
        return Mono.just(Map.of("username", principal.getName()));
    }

    @GetMapping("/admin")
    public Mono<String> adminPanel() {
        return Mono.just("admin-ok");
    }

    @PostMapping("/notes")
    public Mono<ResponseEntity<String>> createNote() {
        return Mono.just(
                ResponseEntity.status(HttpStatus.CREATED)
                        .body("created"));
    }
}
```

The `Principal` of `/me` is the authentication identity in the current request. When using `mockUser("alice")`, the controller sees the test principal alice. When sending real HTTP Basic credentials, the framework checks `ReactiveUserDetailsService` and the controller sees the corresponding identity.

Returning `Mono<T>` from `@RestController` follows the reactive model; do not call `block()` or `subscribe()` inside a controller.

## 6. Complete test class with `springSecurity()`

This is the most important part of the lesson. We use **`@SpringBootTest(webEnvironment = MOCK)`** to obtain the real Spring ApplicationContext of the application while **not starting a TCP server**. The test manually builds `WebTestClient` from the context so that `springSecurity()` wiring is transparent.

File `src/test/java/dev/example/httptests/SecurityWebTestClientTests.java`:

```java
package dev.example.httptests;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import org.springframework.security.test.context.support.WithMockUser;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class SecurityWebTestClientTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
                .bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void publicRouteAllowsAnonymous() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("public-ok");
    }

    @Test
    void privateRouteRejectsAnonymous() {
        client.get().uri("/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void mockUserCanAccessAuthenticatedRoute() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .get().uri("/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.username")
                .isEqualTo("alice");
    }

    @Test
    void mockUserWithoutAdminRoleIsForbidden() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .get().uri("/admin")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void mockAdminCanAccessAdminRoute() {
        client.mutateWith(mockUser("operator").roles("ADMIN"))
                .get().uri("/admin")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("admin-ok");
    }

    @Test
    @WithMockUser(username = "annotated-admin", roles = "ADMIN")
    void withMockUserAnnotationCanAccessAdminRoute() {
        client.get().uri("/admin")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("admin-ok");
    }

    @Test
    void postWithMockUserButNoCsrfIsForbidden() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .post().uri("/notes")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void postWithMockUserAndCsrfIsCreated() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .mutateWith(csrf())
                .post().uri("/notes")
                .exchange()
                .expectStatus().isCreated()
                .expectBody(String.class)
                .isEqualTo("created");
    }

    @Test
    void csrfWithoutAuthenticationDoesNotGrantAccess() {
        client.mutateWith(csrf())
                .post().uri("/notes")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void realBasicCredentialsAreAuthenticated() {
        client.get().uri("/me")
                .headers(h -> h.setBasicAuth(
                        "alice", "alice-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.username")
                .isEqualTo("alice");
    }

    @Test
    void wrongBasicPasswordIsRejected() {
        client.get().uri("/me")
                .headers(h -> h.setBasicAuth(
                        "alice", "wrong-pass"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void unknownRouteIsDeniedToAuthenticatedUser() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .get().uri("/internal-not-registered")
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

### 6.1. Explaining the required setup lines

`@SpringBootTest(webEnvironment = MOCK)`:
- Loads the Spring Boot application context together with WebFlux security beans.
- Does not create a Netty listener/TCP port.
- Allows `bindToApplicationContext(context)` to execute **mock-server exchanges** through WebFlux.

`@Autowired ApplicationContext context`:
- Provides the real handler/filter beans to the test client.
- Ensures tests verify **real application rules**, not just a hand-instantiated controller object.

`WebTestClient.bindToApplicationContext(context)`:
- Builds the test server handler from the context.
- Unlike `bindToController(new DemoController())`, which does not guarantee the full production security filters are present.

`.apply(springSecurity())`:
- Configures Spring Security test support to integrate with mock-server testing.
- Placed **before** `configureClient()` and `build()`.
- Do not use `.mutateWith(springSecurity())`: `springSecurity()` is a setup-stage configurer, distinct from per-request mutators.

`.configureClient()`:
- Transitions to the client builder to customize default headers, base URL, timeouts, or filters.
- In the example, no default Basic authentication is set on the client, because doing so would accidentally turn "anonymous" tests into authenticated requests.

### 6.2. Why can test methods use `mockUser()`?

After proper setup:
- `client.mutateWith(mockUser("alice").roles("USER"))` builds a client/request variant with a **test SecurityContext**, without needing a real password or user record.
- Spring Security authorization filters see this test authentication.
- The controller receives principal `alice`.
- `roles("USER")` maps to `ROLE_USER`, so the `/notes` route can pass the role check.
- However, **CSRF is still a separate layer**; a POST without `csrf()` still returns 403.

**Limitation:** `mockUser("alice")` can simulate a user that **does not exist** in `MapReactiveUserDetailsService` and still pass authorization. This test **does not prove login/password validation** or that the user store is working.

### 6.3. When to use `@WithMockUser`?

`@WithMockUser` belongs to `org.springframework.security.test.context.support.WithMockUser`, used by Spring Security test via test context listeners. Example:

```java
@Test
@WithMockUser(username = "auditor", roles = "ADMIN")
void annotationExample() {
    client.get().uri("/admin")
            .exchange()
            .expectStatus().isOk();
}
```

**Pros:** less repetition when multiple requests in the same test share one principal. It is also helpful for method security tests when Spring Test is properly integrated.

**Cons:** authentication is supplied for the **entire test method**, making it harder to read when mixing anonymous/user/admin calls in the same method. When per-request isolation is needed, `client.mutateWith(mockUser(...))` is usually preferred.

**Note:** Do not use `@WithMockUser` to claim that passwords, database login, JWT signatures, or issuer validation have been tested. It injects a test Authentication rather than invoking real login.

### 6.4. CSRF: why are two mutators required?

For POST /notes to be accepted, **two conditions** are required:
- Authentication with `ROLE_USER`.
- A valid CSRF token.

```java
client
        .mutateWith(mockUser("alice").roles("USER"))
        .mutateWith(csrf())
        .post().uri("/notes")
        .exchange()
        .expectStatus().isCreated();
```

If only mock user is provided:

```java
client.mutateWith(mockUser("alice").roles("USER"))
        .post().uri("/notes")
        .exchange()
        .expectStatus().isForbidden();
```

If only csrf is provided:

```java
client.mutateWith(csrf())
        .post().uri("/notes")
        .exchange()
        .expectStatus().isUnauthorized();
```

**Conclusion:** A CSRF token **does not prove the user is authenticated**; user login **does not substitute for a CSRF token**. Tests must reflect each layer of protection instead of disabling CSRF just to make POST succeed.

### 6.5. HTTP Basic: testing real credentials

```java
client.get().uri("/me")
        .headers(headers ->
                headers.setBasicAuth("alice", "alice-pass"))
        .exchange()
        .expectStatus().isOk();
```

The request above **does not use `mockUser`**. The Basic authentication filter performs:
1. Reads `Authorization: Basic ...`.
2. Extracts username/password.
3. Calls the reactive authentication manager and `MapReactiveUserDetailsService`.
4. Verifies the BCrypt-encoded password using `PasswordEncoder`.
5. Places the authenticated principal into the Reactor Context if valid.
6. The `/me` route retrieves the principal and returns JSON.

Therefore, this test verifies **a real authentication path** inside the in-memory Spring context, stronger than a fake-principal test regarding credential validation. It still **does not prove TLS, reverse proxy, browser cookie, or network behavior** because no socket is opened.

Use HTTP Basic over **HTTPS in production**. The `alice-pass` and `admin-pass` passwords in the demo are strictly learning credentials in a local environment.

## 7. Running and checking the test report

From the `webflux-security-test-demo` directory:

```bash
gradle test
```

If you have the Gradle Wrapper:

```bash
./gradlew test
```

Windows:

```powershell
.\gradlew.bat test
```

**Expected result based on the code:** 12 passing JUnit tests. This is an **expectation**, not a claim that Gradle was executed in this workspace.

| Test | Expected status | Verified behavior |
| --- | --- | --- |
| Public GET anonymous | 200 | `permitAll` and controller |
| Private GET anonymous | 401 | Missing Authentication |
| GET /me + mockUser USER | 200 | Test SecurityContext is used |
| GET /admin + USER | 403 | Missing ADMIN role |
| GET /admin + ADMIN | 200 | Has ADMIN role |
| GET /admin + `@WithMockUser` ADMIN | 200 | Annotation-based test context |
| POST /notes + USER, no csrf | 403 | CSRF enabled |
| POST /notes + USER + csrf() | 201 | Auth + CSRF + controller |
| POST /notes + csrf(), anonymous | 401 | CSRF does not replace auth |
| GET /me + valid Basic | 200 | Real password verification |
| GET /me + wrong Basic | 401 | Authentication failure |
| GET unknown route + authenticated USER | 403 | Deny-by-default |

**Note:** A test with `expectStatus().isUnauthorized()` may be valid due to the configured HTTP Basic entry point; if you enable form login instead, some anonymous requests may return `302` to the login page. Before changing assertions, determine the UX/security config your actual API intends.

### 7.1. Running the application over real HTTP for comparison

In addition to in-memory tests, you can run:

```bash
gradle bootRun
```

Then from a local terminal:

```bash
curl -i http://localhost:8080/public

curl -i http://localhost:8080/me

curl -i --user alice http://localhost:8080/me

curl -i --user alice http://localhost:8080/admin
```

`curl --user alice` can prompt for the password interactively, avoiding recording passwords directly in shell history. Expected:
- `/public` → 200.
- `/me` without auth → 401.
- `/me` auth alice with valid password → 200.
- `/admin` auth alice → 403.

This is HTTP over sockets, **different** from `bindToApplicationContext` tests. In production environments, HTTPS/TLS (with certificate validation) must be used, never sending Basic credentials over public HTTP.

## 8. How do in-memory WebTestClient and live-server differ?

### 8.1. In-memory: recommended when learning `springSecurity()`

```java
WebTestClient client = WebTestClient
        .bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();
```

**Has:** ApplicationContext, WebFlux WebFilters, Reactor Context, Spring Security test mutators, controllers, route authorization, CSRF rules.

**Lacks:** Real TCP/Netty server, TLS handshake, reverse proxy, network timeouts, DNS/load balancer, browser behavior.

Well suited for **Spring Security WebFlux** rules because it is fast, isolated, and requires no open ports.

### 8.2. Live server: testing real HTTP communication

```java
WebTestClient live = WebTestClient
        .bindToServer()
        .baseUrl("http://localhost:8080")
        .build();

live.get().uri("/me")
        .headers(headers ->
                headers.setBasicAuth("alice", "alice-pass"))
        .exchange()
        .expectStatus().isOk();
```

This is a fragment assuming the application is running on port 8080. `bindToServer()` opens a real HTTP connection. **Do not apply `springSecurity()` to a live client to use `mockUser()`**: Spring Security test's mock auth/CSRF mutators rely on mock-server filters and are not sent over HTTP as a real credential protocol.

### 8.3. `@SpringBootTest(RANDOM_PORT)`

An E2E/integration pattern:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class LiveHttpTests {
    @Autowired
    WebTestClient client;

    @Test
    void basicAuthenticationWorksOverRealHttp() {
        client.get().uri("/me")
                .headers(headers ->
                        headers.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isOk();
    }
}
```

This is an additional **test class fragment**; it requires JUnit/Spring Boot imports and uses the real HTTP stack. In this case, Spring Boot prepares the WebTestClient against the running server port. Tests should send **real credentials**, real cookie/CSRF tokens, or genuinely signed bearer JWTs depending on the application.

**Do not mix up modes:**

| Goal | Appropriate test style |
| --- | --- |
| Route authz by ROLE_USER/ROLE_ADMIN | In-memory + `springSecurity()` + `mockUser()` |
| CSRF enabled on POST | In-memory + `springSecurity()` + `csrf()` |
| PasswordEncoder + ReactiveUserDetailsService | In-memory + real HTTP Basic |
| Login cookie/session/redirect over real HTTP | RANDOM_PORT + HTTP client/browser |
| OAuth2/OIDC redirect to external IdP | Contract/E2E with test IdP |
| JWT cryptographic signature, issuer, and audience | Signed test JWT + real decoder |
| Reverse proxy, TLS, CORS browser preflight | Deployment E2E |

## 9. Alternative setup approaches and trade-offs

### 9.1. `@AutoConfigureWebTestClient` in Spring Boot

When using Spring Boot tests, `@AutoConfigureWebTestClient` can inject a WebTestClient already integrated with Boot's test infrastructure:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class AutoClientExample {
    @Autowired
    WebTestClient client;
}
```

However, **configuration can depend on test slices/auto-configuration**, so while learning `springSecurity()` specifically, the manual `bindToApplicationContext(context).apply(springSecurity())` pattern is more transparent. Do not call `.apply(springSecurity())` twice on a test client already configured by Boot without understanding the test setup.

If `@WebFluxTest` loads only a controller slice, ensure the security config/filter beans under test are actually present. A controller-only slice may lack the authentication dependencies you expect.

### 9.2. `bindToController(...)`

`WebTestClient.bindToController(new DemoController())` is useful for isolated controller testing. However, it **does not prove** that the production `SecurityWebFilterChain` is protecting the route. Even when applying a mock configurer, the proper security filters/context must be supplied; otherwise, the controller test may pass because security was bypassed.

**When the objective is "setting up WebTestClient with springSecurity()"**, prefer **binding an application context that includes the real security chain**.

### 9.3. Annotation-based or mutation-based tests?

`@WithMockUser`:
- Concise when the same identity is used across the entire test method.
- Easy to write method security tests.
- Requires proper Spring Security TestExecutionListeners/JUnit Spring integration.

`mockUser()`:
- Makes each request's identity explicit.
- Suitable for testing anonymous, user, and admin calls interleaved.
- Does not modify the password DB; the principal is mocked.
- `mutateWith(...)` creates a client variant, avoiding setting mock auth as a default for the whole suite.

`mockAuthentication(...)`:
- Used when a custom `Authentication` type other than UsernamePasswordAuthenticationToken is needed.
- Should only create an authenticated token when the goal is testing **authorization**, not the authentication manager.

### 9.4. Extending to OAuth2/JWT

If the application has an OAuth2 Resource Server JWT setup, add the appropriate dependency:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
```

Then you can use:

```java
client.mutateWith(mockJwt()
        .jwt(jwt -> jwt
                .subject("partner-01")
                .claim("scope", "reports:read")))
        .get().uri("/api/reports")
        .exchange();
```

This is a **fragment for applications with resource-server JWT configuration**, not code runnable in the HTTP Basic project from section 5. Import static `SecurityMockServerConfigurers.mockJwt` when using it.

**Warning:** `mockJwt()` creates an authenticated test principal with test-defined authorities. It **does not verify JWT signature, issuer, audience, `exp`, `nbf`, JWK rotation, or token revocation**. Do not use mockJwt as proof that the Resource Server decoder is secure.

Similarly:
- `mockOAuth2Login()`: mocks OAuth2 Login Authentication.
- `mockOidcLogin()`: mocks OIDC user/session context.
- `mockOpaqueToken()`: mocks BearerTokenAuthentication and claims.
- `mockAuthentication(...)`: supplies a custom test authentication.

All of these are used to **test authorization/controller behavior**; real authentication/login/token verification requires separate integration tests.

### 9.5. Reactive method security

If the application enables `@EnableReactiveMethodSecurity` and services return `Mono`/`Flux`, Spring Security uses Reactor Context to propagate Authentication to method authorization. With an in-memory WebTestClient + `springSecurity()` + `mockUser()`, you can test permissions at both the HTTP route level and `@PreAuthorize` when beans/services are properly proxied by Spring.

Example method security fragment (not in the sample app):

```java
@PreAuthorize("hasAuthority('ROLE_ADMIN')")
public Mono<String> auditReport() {
    return Mono.just("secret-report");
}
```

This is a **fragment inside a Spring bean** and only works with reactive method security enabled. Tests must use the Spring-managed service bean; calling new Service() directly bypasses the AOP security proxy.

## 10. Testing CSRF at the right level

Spring Security protects state-changing HTTP methods with CSRF by default when using session/browser authentication. Tests should cover at least:

| Request | Auth | CSRF | Expected result |
| --- | --- | --- | --- |
| GET /public | None | Not needed | 200 |
| GET /me | None | Not needed | 401 |
| POST /notes | USER | Missing | 403 |
| POST /notes | USER | `csrf()` | 201 |
| POST /notes | None | `csrf()` | 401 |
| POST /notes | ADMIN | `csrf()` | 403 because ADMIN lacks ROLE_USER in demo |

**Why use `csrf()` in in-memory tests?** It constructs a request with a valid token for CSRF verification. When you want to test **the flow of obtaining a token from a real page/form/cookie**, you must execute the sequence of requests with proper session state against the server and verify the real CSRF token repository; `csrf()` **does not replace** browser E2E tests.

**Do not fix a 403 error with `csrf.disable()`** in production code just to make a POST test pass. Check whether the token is missing or the role is missing, then choose the exact test scenario.

### CSRF and stateless Bearer token APIs

If a resource server only accepts an `Authorization: Bearer` header from machine clients and has no automatic browser cookie authentication, the application may be designed to disable CSRF after a threat-model review. In that case, a POST test with `csrf()` is no longer meaningful evidence because the filter has been disabled.

If the application uses form login/WebSession cookies, CSRF should normally be kept enabled and tested with proper session state. When multiple security chains exist, CSRF rules may differ by path; tests should cover the exact chain rather than applying one assumption to every endpoint.

## 11. Detecting "false-green tests"

### 11.1. Testing only the controller, skipping security filters

Anti-pattern:

```java
WebTestClient client = WebTestClient
        .bindToController(new DemoController())
        .build();

client.get().uri("/public")
        .exchange()
        .expectStatus().isOk();
```

The test above may be correct for `/public`, but **it does not prove `/me` is protected**. Add an anonymous `/me` case expecting 401 through a context containing the SecurityWebFilterChain.

### 11.2. Mocking a user in every test

Anti-pattern:

```java
// If the default client always has ADMIN, anonymous tests become meaningless.
WebTestClient adminClient = client
        .mutateWith(mockUser("root").roles("ADMIN"));
```

This configuration is **not invalid in terms of API**, but it is wrong when used as the sole client for the entire suite. A missing-auth test must truly have **no authentication mutator/credentials**, rather than inheriting ADMIN from default test setup.

### 11.3. What do mock tests fail to prove?

| Test | What is verified | What is NOT verified |
| --- | --- | --- |
| `mockUser("alice")` → 200 | Authorization/context/controller | Password encoder, DB |
| `@WithMockUser(roles="ADMIN")` | Test context and role policy | Login, user disabled status |
| Real HTTP Basic → 200 | Converter/manager/users/password in mock app | TLS/ingress/proxy |
| `mockJwt()` → 200 | Scope/claims mapping in test mutator and authz | Signed JWT verification |
| `csrf()` → POST 201 | CSRF protection test path | Browser token issuance/lifecycle |
| RANDOM_PORT with Basic | HTTP server + credential handling | Production gateway/cert configuration |
| Browser E2E with session cookies | Redirects, cookies, CSRF flow | Backend security on endpoints not yet tested |

**Note:** If the application has custom authentication logic, `mockUser()` may bypass that logic. To test a custom `ReactiveAuthenticationManager`/API key/token decoder, send **real** credentials to the filter in tests or use signed-token fixtures with the real decoder.

### 11.4. Asserting status only without asserting body content

Avoid only doing:

```java
client.get().uri("/me").exchange()
        .expectStatus().isOk();
```

Also verify the correct principal:

```java
client.mutateWith(mockUser("alice"))
        .get().uri("/me")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.username").isEqualTo("alice");
```

When roles/tenants differ, assert the authorized data, not just status 200. A 200 response returning another tenant's data is still a critical bug.

### 11.5. Using sleep/block to wait for reactive results

`WebTestClient.exchange()` and Reactor testing utilities already handle subscription and test lifecycle. Do not add `Thread.sleep` to "wait for the server", or call `block()` arbitrarily in controller/security code. For custom `Mono`/`Flux` services, use `StepVerifier` or appropriate WebTestClient streaming assertions.

## 12. Common errors list

| Symptom | Possible cause | How to check/fix |
| --- | --- | --- |
| `springSecurity()` does not resolve | Missing `spring-security-test` or wrong import | Add testImplementation matching BOM, import reactive package |
| Missing `WebTestClient` | Missing WebFlux/test dependencies | Add `starter-webflux` and `starter-test` |
| Anonymous `/me` test returns 200 | Missing SecurityWebFilterChain, overly broad permitAll, or leftover mock principal | Bind proper ApplicationContext + apply springSecurity; test without mutator |
| Unauthenticated GET /me returns 302 instead of 401 | Form login entry point is active | If API expects 401, configure HTTP Basic/entry point explicitly |
| POST with mockUser returns 403 | Missing CSRF | Add `mutateWith(csrf())` for the success case |
| POST with CSRF still returns 403 | Missing ROLE_USER or wrong method matcher | Check authority prefix and route |
| POST with CSRF while anonymous returns 401 | Expected behavior | CSRF does not create Authentication |
| Basic with valid password returns 401 | UserDetailsService/encoder mismatch | Check BCrypt, username, header |
| Basic with wrong password still passes test | `mockUser` is still used on the request | Use real HTTP Basic, no mock |
| `@WithMockUser` does not work | Missing Security TestExecutionListeners or mock-server setup | Spring Test + security-test + apply springSecurity |
| `mockJwt()` is missing | Missing spring-security-test or wrong import | Add test jar and OAuth2 Resource Server config when used |
| Spring Boot test starts Servlet | `starter-web` added alongside WebFlux | Use only the WebFlux starter |
| `bindToServer()` rejects `mockUser()` | Mutator requires mock-server filter context | Use real HTTP credentials or bindToApplicationContext |
| WebFlux test does not enforce `@PreAuthorize` | Reactive method security/proxy not enabled | `@EnableReactiveMethodSecurity` and a real Spring bean |
| Mock test passes but production JWT fails | Test bypasses decoder | Signed JWT integration test |
| JSON body assertion fails due to key order | JSON object key order is not fixed | Assert JSONPath/semantic JSON |
| `/unknown` returns 403 instead of 404 | `denyAll` blocks before router | That is the security policy; assert accordingly |
| Session cookie leaks principal across tests | Client shares cookies/mutated state | Create a fresh client per test, isolate flows |
| Multi-chain rule does not trigger | Wrong chain matcher/order | Test path/method against the exact filter chain |
| Security filter accidentally disabled in slice | `@WebFluxTest` loads only partial beans | Import exact security config, or use SpringBootTest |
| CORS OPTIONS returns 401 | CORS preflight not handled before security | Test/preconfigure CORS appropriately for browser cases |
| Redirect test missing Location | Using Basic 401 or different entry point | Choose the right security config, assert header when needed |
| Tests depend on external database/IdP | Setup lacks mocks/fixtures | Separate unit authz and integration credential tests |

## 13. Quality checklist for setting up WebTestClient

- [ ] The application is truly **WebFlux** and has a proper `SecurityWebFilterChain`.
- [ ] `spring-security-test` is added under `testImplementation`.
- [ ] The `SecurityMockServerConfigurers.springSecurity` import is from **reactive.server**, not MockMvc.
- [ ] Use `WebTestClient.bindToApplicationContext(context)` for mock-server setup.
- [ ] Call `.apply(springSecurity())` before `.configureClient().build()`.
- [ ] The default client **does not** carry ADMIN user/Basic credentials if tests need anonymous requests.
- [ ] Tests cover public route 200 and protected route anonymous 401/redirect per contract.
- [ ] Tests cover authenticated USER 200 and missing ADMIN role 403.
- [ ] Tests cover ADMIN 200 and denied-by-default routes.
- [ ] For unsafe methods with CSRF enabled: test missing token 403 and valid `csrf()` success.
- [ ] Use `@WithMockUser` or `mockUser()` within proper scope; do not treat them as password tests.
- [ ] Include at least one **real credential flow** test if the objective covers authentication.
- [ ] Do not use `mockJwt()` to claim JWT signature/issuer/audience verification is tested.
- [ ] If using OAuth2/OIDC, separate mocked authz tests from external IdP integration tests.
- [ ] If using method security, test through a Spring-managed bean and Reactor Context.
- [ ] Do not disable CSRF/filters because a test failed.
- [ ] Do not expose passwords, session cookies, bearer tokens, or client secrets in logs/test reports.
- [ ] Tests needing browser/network behavior are separated into RANDOM_PORT/proxy E2E tests.
- [ ] Assert both HTTP status and important body/headers (principal, tenant, Location, challenge).
- [ ] Test 401 and 403 according to the real security entry point/config, without assuming all apps share the same status.
- [ ] Re-run the full test suite after changing `SecurityWebFilterChain` or Boot/Spring Security versions.
- [ ] On CI, test reports are archived/audited without containing real credentials.

## 14. Self-check questions

**1. Where is `springSecurity()` imported from?**  
`org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity`.

**2. Why must `.apply(springSecurity())` be called?**  
To attach Spring Security mock-server test support to `WebTestClient` and enable security mutators/test context alongside the security filter chain.

**3. How does `bindToApplicationContext` differ from `bindToServer`?**  
One tests in-memory using the WebFlux context without opening TCP; the other sends HTTP over the network to a real server.

**4. Does `mockUser()` verify database passwords?**  
No, it creates a test Authentication.

**5. When is `@WithMockUser` suitable?**  
When a test method needs a single mocked principal via Spring Test context integration.

**6. What should an unauthenticated GET /me test return in this sample?**  
401 because the route requires authentication, the HTTP Basic entry point is enabled, and form login is disabled.

**7. Why does GET /admin + USER return 403?**  
USER is authenticated but does not have `ROLE_ADMIN`.

**8. Why does POST /notes + mockUser still return 403 when `csrf()` is missing?**  
CSRF is a separate barrier for state-changing requests.

**9. Does a CSRF token automatically authenticate a user?**  
No. Having CSRF without authentication still yields 401 in this sample.

**10. Does `mutateWith(csrf())` prove real browser cookie/CSRF repository behavior?**  
No; it is test support in mock-server mode.

**11. How does real HTTP Basic in a test differ from mockUser?**  
Basic invokes the authentication manager, reactive user details service, and password encoder; mockUser skips those steps.

**12. Does `mockJwt()` verify the signature?**  
No. It mocks an authenticated JWT principal.

**13. Why should `bindToController` not be used as proof that security is applied?**  
Because controller-only binding may not include the production SecurityWebFilterChain.

**14. Which authority does `hasRole("ADMIN")` check?**  
`ROLE_ADMIN`.

**15. Should CSRF be disabled to make POST tests pass?**  
No, if the real application requires CSRF; use `csrf()` for success tests and verify 403 when the token is missing.

**16. How can form login change an unauthenticated response?**  
It can redirect 302 to the login page instead of returning HTTP Basic 401.

**17. Does `springSecurity()` apply to a live `bindToServer()` the same way as a mock client?**  
Not for injecting fake users; live HTTP requires real credentials/tokens.

**18. When reactive method security is enabled, how is Authentication propagated?**  
Through Reactor Context, not relying on ThreadLocal as in Servlet.

**19. Does a passing mock ADMIN test mean the admin password is still valid?**  
No. To verify passwords, you must test a real authentication flow.

**20. Why should anonymous tests use a fresh client without mutators?**  
To avoid accidentally carrying over fake Authentication and creating false positives.

**21. When HTTP status is 200 but the JSON returns the wrong tenant, should the test pass?**  
It should not. Assert tenant/resource identity and important fields.

**22. Which test suites should run before deploying to production?**  
In-memory security policy tests, real credential/token tests, HTTP/TLS/proxy/browser E2E per threat model, and Boot/Spring Security regression tests.

### Practice exercises

1. Run `SecurityWebTestClientTests` and explain why each 200/201/401/403 case occurs.
2. Remove `.apply(springSecurity())` on a learning branch; observe the mock principal/CSRF tests and explain where test support is missing.
3. Replace `/admin` with `hasAuthority("ROLE_ADMIN")` and compare with `hasRole("ADMIN")`.
4. Add a test using `@WithMockUser(roles="USER")` to verify `/admin` returns 403.
5. Add a JSON payload to POST /notes and assert the response body; keep CSRF required.
6. Use `mockUser("bob")` who is not in MapReactiveUserDetailsService, confirm the `/me` test can still pass, and explain why that is **not** a password validation test.
7. Test Basic password `wrong-pass` → 401, then change the password encoder in code and verify the real auth flow fails if hashes do not match.
8. Enable form login, update the expected unauthenticated status per UX, and verify the Location redirect.
9. Add a service annotated with `@PreAuthorize` + `@EnableReactiveMethodSecurity` and test through the Spring proxy.
10. Write a `@WebFluxTest` controller slice with `@Import(SecurityConfig.class)` and required beans; verify the SecurityWebFilterChain is actually present.
11. Write a RANDOM_PORT test sending real Basic credentials over sockets without `mockUser()`.
12. Add OAuth2 Resource Server to a separate project, use `mockJwt()` to test scopes and a signed JWT fixture to test decoder signature verification.
13. Write a CORS preflight test if the app has a cross-origin browser client, without requiring token/CSRF on preflight.
14. Add a tenant-scoped protected route, asserting user A cannot see tenant B's data even if status/role appear valid.
15. Test timeout or error propagation of a custom reactive authentication manager; ensure it does not pass when the store is unavailable.
16. Configure the test suite not to store raw credentials in logs/CI reports.
17. Compare SpringBootTest MOCK, RANDOM_PORT, and WebFlux slice in terms of speed, wiring level, and coverage.
18. Conduct a code review ensuring new routes do not fall into `permitAll` or bypass the filter chain.

## 15. Official documentation

- [Spring Security — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): `bindToApplicationContext(...).apply(springSecurity()).configureClient().build()`.
- [Spring Security — Testing Authentication (WebFlux)](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html): `mockUser()` and `@WithMockUser`.
- [Spring Security — Testing CSRF (WebFlux)](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html): `csrf()` mutator.
- [Spring Security — Testing OAuth2 (WebFlux)](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt()`, `mockOAuth2Login()`, `mockOidcLogin()`, and authz test scope.
- [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `ServerHttpSecurity`, `SecurityWebFilterChain`.
- [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): CSRF semantics with browser sessions.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity` and Reactor Context.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): mock server and live server bindings, assertions.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@AutoConfigureWebTestClient`, test slices.
- [Spring Security 6.3 — SecurityMockServerConfigurers](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html): test configurer API.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): `@BeforeEach`, `@Test`, and test lifecycle.

**Remember:** To test HTTP security in **Spring WebFlux**, build `WebTestClient.bindToApplicationContext(context).apply(springSecurity()).configureClient().build()`. Use `mockUser()` or `@WithMockUser` for **authorization scenarios**, `csrf()` when testing **CSRF-protected POST/PUT/DELETE**, and send **real HTTP credentials** when authentication needs verification. **Mock passes do not mean passwords, JWT signatures, cookies, TLS, or IdP integration have been truly tested.** Always test 200/201/401/403 according to the real configuration and never lose SecurityWebFilterChain in test setup.