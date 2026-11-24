# WebTestClient and Integrating Spring Security in Reactive Applications

## 1. What should be tested in a Spring WebFlux application?

In a **Spring WebFlux** application, having a controller return the right data is not enough to claim the API is secure. You must prove that requests travel through the **reactive security filter chain**, get properly authenticated and authorized, and only then reach the handler. An endpoint might return the right output in an isolated controller test while being blocked or wrongly exposed under the real Spring Security configuration.

`WebTestClient` is Spring Test's fluent HTTP testing tool, usable with WebFlux **without starting an HTTP server** or against a live server. Combined with `spring-security-test`, it lets you supply test identities, attach authorities, provide CSRF tokens, and observe responses from Spring Security's `WebFilter`s.

A minimal test suite should answer:

1. Can **anonymous** callers access public endpoints?
2. Do login-protected endpoints return **401** or redirect to authentication as configured?
3. Do authenticated users lacking the required role/scope receive **403**?
4. Do users with sufficient permissions receive **200** with the right data?
5. Are write operations blocked by **CSRF protection** when missing a token and allowed when holding both a valid token and permissions?
6. Does the controller/service read the identity from the **reactive SecurityContext** of the request under test?
7. Do the tests actually run against the **application's `SecurityWebFilterChain`**, rather than a default security setup or a handler bypassing filters?

This lesson uses **Java 17+, Spring Boot 3.x, and Spring Security 6.x** in its examples. In Spring Boot 4.x / Spring Security 7.x, package names for some test configuration annotations changed; verify against your project's version documentation. The core concepts of `WebTestClient`, `SecurityWebFilterChain`, and test mutators remain corresponding.

## 2. Architecture: from WebTestClient to SecurityWebFilterChain

Processing flow of a secured WebFlux request:

```text
JUnit test
    |
    v
WebTestClient
    |
    v
WebFlux HttpHandler / WebHandler
    |
    v
Spring Security WebFilterChainProxy
    |
    +--> CSRF / authentication / authorization WebFilter
    |
    v
DispatcherHandler
    |
    v
@RestController or RouterFunction
    |
    v
Mono / Flux / ResponseEntity
    |
    v
HTTP status + headers + body -> expectStatus / expectHeader / expectBody
```

**Key point:** WebFlux uses `WebFilter` and `SecurityWebFilterChain`. Servlet applications typically use `Filter`, `SecurityFilterChain`, `HttpSecurity`, and `MockMvc`. The two groups have similar names, yet **their types are not directly interchangeable**.

In the reactive stack:

- `ServerHttpSecurity` declares the security policy for HTTP requests.
- `SecurityWebFilterChain` defines the `WebFilter` chain applied to requests.
- `authorizeExchange(...)` configures authorization by path and HTTP method.
- `ReactiveAuthenticationManager` and related components perform reactive authentication.
- Security state propagates via **Reactor Context**; never assume `ThreadLocal` preserves the principal across thread switches in reactive pipelines.
- `WebTestClient` can bind to an `ApplicationContext` to execute the app's real `WebFilter`s during tests, or bind to a server listening on a network port.

### Three ways to build WebTestClient

| Setup method | Opens HTTP port? | Best suited for | Notable limitations |
| --- | --- | --- | --- |
| `bindToApplicationContext(context)` | No | Testing router/controller + all configured `WebFilter`s in context | Does not test TLS, proxies, real ports, or issues outside HTTP handlers |
| `bindToController(controller)` | No | Fast testing of a single controller | Does not prove production `SecurityWebFilterChain` works; requires separate test security setup |
| `bindToServer().baseUrl(...)` | Real server | End-to-end tests over HTTP, sessions/cookies, network behavior | Must send real test credentials/tokens; `mockUser()` cannot impersonate users on a remote server |

For **integration testing Spring Security in a reactive application**, the first option is central. `spring-security-test`'s `springSecurity()` configurer adds security test support to the context-bound client.

## 3. Project dependencies

Create a Spring Boot 3.x project with Spring Initializr, selecting **Spring Reactive Web** and **Spring Security**. Using Gradle Groovy DSL, the core dependencies are:

```groovy
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

This is the **dependencies/test task** block to place inside `build.gradle` of a Spring Boot project that already has plugins and versions from Initializr, not the entire build script. Purpose of each dependency:

- `spring-boot-starter-webflux` provides Spring WebFlux, Reactor, codecs, and `WebTestClient` when paired with Spring Test.
- `spring-boot-starter-security` provides reactive security and the `ServerHttpSecurity` DSL.
- `spring-boot-starter-test` provides JUnit Jupiter, Spring Boot Test, Spring Test, and assertion utilities.
- `spring-security-test` provides `springSecurity()`, `mockUser()`, `csrf()`, and dedicated mock authentication annotations/mutators.
- `reactor-test` is needed for tests asserting directly on `Mono`/`Flux` via `StepVerifier`; in the HTTP examples below, it can be used for extended streaming exercises.

**Do not add `spring-boot-starter-web` just to run the example.** When both Web MVC and WebFlux are on the classpath, Spring Boot 3.x defaults to Servlet/MVC mode. In hybrid projects needing reactive tests, explicitly set `spring.main.web-application-type=reactive` and verify which `SecurityWebFilterChain` bean is active.

## 4. Sample reactive application with authorization and CSRF

Place the example Java source at:

```text
src/main/java/demo/reactivetest/ReactiveSecurityLabApplication.java
```

Create **exactly one file** containing the complete program below:

```java
package demo.reactivetest;

import java.security.Principal;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveSecurityLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityLabApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain webFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers(HttpMethod.POST, "/api/notes")
                    .hasRole("EDITOR")
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            // HTTP Basic API: do not use HTML form login redirects.
            .formLogin(form -> form.disable())
            // Do not disable CSRF: POST must carry a valid CSRF token.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService(
            PasswordEncoder encoder) {

        return new MapReactiveUserDetailsService(
            User.withUsername("alice")
                .password(encoder.encode("alice123"))
                .roles("USER")
                .build(),
            User.withUsername("editor")
                .password(encoder.encode("editor123"))
                .roles("EDITOR")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    public record NoteRequest(String text) {}

    @RestController
    public static class ApiController {

        @GetMapping("/api/public")
        public Mono<String> publicEndpoint() {
            return Mono.just("public-ok");
        }

        @GetMapping("/api/admin")
        public Mono<String> adminEndpoint() {
            return Mono.just("admin-ok");
        }

        // WebFlux retrieves the Principal of the authenticated request.
        @GetMapping("/api/me")
        public Mono<String> currentUser(Mono<Principal> principal) {
            return principal.map(Principal::getName);
        }

        @PostMapping("/api/notes")
        public Mono<Map<String, String>> createNote(
                @RequestBody Mono<NoteRequest> body) {

            return body.map(note ->
                Map.of("saved", note.text())
            );
        }
    }
}
```

### Why these specific components?

**`@EnableWebFluxSecurity`** enables WebFlux security; `SecurityWebFilterChain` declares rules for reactive requests. `ServerHttpSecurity` differs from Servlet `HttpSecurity`. This code **does not** use Spring MVC's `SecurityFilterChain` or `@EnableWebSecurity`.

**`authorizeExchange(...)`** evaluates paths in order:

1. `/api/public` is open to anonymous callers.
2. `POST /api/notes` allows only role `EDITOR`.
3. `/api/admin` allows only role `ADMIN`.
4. All other requests require authentication.

`hasRole("ADMIN")` checks for the `ROLE_ADMIN` authority under default prefix conventions. Users with `ROLE_USER` are authenticated yet still receive 403 on `/api/admin`.

**`httpBasic(...)`** lets tests check both missing/invalid credentials and valid credentials. `formLogin(form -> form.disable())` avoids HTML login-page redirects in the sample API. Therefore anonymous GET `/api/admin` returns **401** instead of 302 under the example setup.

**Do not disable CSRF.** Spring Security WebFlux's default CSRF mechanism protects state-changing HTTP methods. Thus a POST request with role `EDITOR` lacking a CSRF token can return **403 before the controller runs**. In tests, `csrf()` generates a **valid simulated test token**, not a way to turn off protection in production.

**`MapReactiveUserDetailsService`** is a reactive account service suited to test examples. Passwords are encoded via `DelegatingPasswordEncoder`; account data here is strictly a local fixture. Real systems need an appropriate provider/user store, HTTPS, and secrets management.

**`Mono<Principal>`** on `/api/me` retrieves the identity from the active request reactively—not from a query parameter. Using this parameter lets tests verify directly that the test's authentication actually flowed through the reactive pipeline into the handler.

**`Mono` in controllers contains no `block()`.** In WebFlux, avoid blocking I/O threads inside request handlers; when using real data stores, choose reactive drivers or isolate blocking operations intentionally.

## 5. Integration test using WebTestClient and spring-security-test

Place the test file at:

```text
src/test/java/demo/reactivetest/ReactiveSecurityLabApplicationTests.java
```

Here is the **complete Java test file** for the project just created:

```java
package demo.reactivetest;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;

@SpringBootTest
class ReactiveSecurityLabApplicationTests {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicEndpointAllowsAnonymous() {
        client.get()
            .uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public-ok");
    }

    @Test
    void adminEndpointRequiresAuthentication() {
        client.get()
            .uri("/api/admin")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists("WWW-Authenticate");
    }

    @Test
    void userWithoutAdminRoleIsForbidden() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .get()
            .uri("/api/admin")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminRoleCanAccessAdminEndpoint() {
        client.mutateWith(mockUser("admin").roles("ADMIN"))
            .get()
            .uri("/api/admin")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-ok");
    }

    @Test
    void principalReachesReactiveController() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .get()
            .uri("/api/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("alice");
    }

    @Test
    void editorWithoutCsrfTokenIsForbidden() {
        client.mutateWith(mockUser("editor").roles("EDITOR"))
            .post()
            .uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"text\":\"hello\"}")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void editorWithCsrfTokenCanCreateNote() {
        client.mutateWith(mockUser("editor").roles("EDITOR"))
            .mutateWith(csrf())
            .post()
            .uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"text\":\"hello\"}")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.saved").isEqualTo("hello");
    }

    @Test
    void userWithCsrfButWithoutEditorRoleIsForbidden() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .mutateWith(csrf())
            .post()
            .uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"text\":\"hello\"}")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void realBasicCredentialsAreCheckedByReactiveAuthentication() {
        client.get()
            .uri("/api/me")
            .headers(headers ->
                headers.setBasicAuth("alice", "alice123")
            )
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("alice");
    }

    @Test
    void wrongBasicPasswordIsUnauthorized() {
        client.get()
            .uri("/api/me")
            .headers(headers ->
                headers.setBasicAuth("alice", "wrong-password")
            )
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

**Wrapped static import syntax:** Java allows line breaks between the package name and the class dot, yet to avoid IDE confusion or copy-paste errors, the three imports above can be written **one line per static import**:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
```

When creating the actual file, **use these three single-line imports instead of the wrapped imports above**, without duplicating them. The static members belong to `SecurityMockServerConfigurers` in the `spring-security-test` dependency.

### What happens in @BeforeEach

The statement:

```java
client = WebTestClient.bindToApplicationContext(context)
    .apply(springSecurity())
    .configureClient()
    .build();
```

creates a client calling HTTP handlers **inside the Spring Boot `ApplicationContext`**, without opening port 8080. `.apply(springSecurity())` integrates Spring Security test support, enabling mock mutators like `mockUser()` and `csrf()` to flow through the pipeline. The application's `SecurityWebFilterChain` is loaded, so tests verify more than isolated controller methods.

With `@SpringBootTest`, the context holds application beans and real security config at test scope. `@SpringBootTest` uses a mock web environment by default—unlike `@SpringBootTest(webEnvironment = RANDOM_PORT)`, which starts an HTTP server on a real port. For these tests, `@AutoConfigureWebTestClient` is unnecessary because `WebTestClient` is constructed manually in `setUp()`.

### Meaning of the tests

| Test | Request | Expected outcome |
| --- | --- | --- |
| `publicEndpointAllowsAnonymous` | GET `/api/public`, unauthenticated | 200 + `public-ok` |
| `adminEndpointRequiresAuthentication` | GET `/api/admin`, anonymous | 401 + Basic challenge |
| `userWithoutAdminRoleIsForbidden` | GET `/api/admin`, mock USER | 403 |
| `adminRoleCanAccessAdminEndpoint` | GET `/api/admin`, mock ADMIN | 200 + `admin-ok` |
| `principalReachesReactiveController` | GET `/api/me`, mock Alice | 200 + `alice` |
| `editorWithoutCsrfTokenIsForbidden` | POST `/api/notes`, mock EDITOR, no CSRF | 403 |
| `editorWithCsrfTokenCanCreateNote` | POST, mock EDITOR, valid CSRF | 200 + `{"saved":"hello"}` |
| `userWithCsrfButWithoutEditorRoleIsForbidden` | POST, mock USER, valid CSRF | 403 |
| `realBasicCredentialsAreCheckedByReactiveAuthentication` | GET `/api/me`, valid Basic Alice | 200 + `alice` |
| `wrongBasicPasswordIsUnauthorized` | GET `/api/me`, wrong Basic Alice | 401 |

The suite clearly separates **two verified layers**: `mockUser()` skips password authentication to focus on authorization; real Basic credential tests pass through the app's authentication mechanism. With only `mockUser` tests, you **have not proved** the password encoder, `ReactiveUserDetailsService`, or Basic credentials work properly.

### Running the tests

In the Gradle project directory with Wrapper:

```bash
./gradlew test
# Windows PowerShell:
# .\gradlew.bat test
```

To run only the test class (using the exact class name above):

```bash
./gradlew test --tests "demo.reactivetest.ReactiveSecurityLabApplicationTests"
```

**Expected result:** all 10 test methods PASS and Gradle task `test` succeeds. This is an **expectation derived from config and assertions**, not stdout measured from a run inside this document. When a test fails, inspect the actual status, assertion message, and active `SecurityWebFilterChain`, and cross-check your exact Spring Boot/Security version.

## 6. What do the test mutators actually do?

### 6.1. mockUser(): creates an identity in the test request

Example:

```java
client.mutateWith(mockUser("alice").roles("USER"))
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class).isEqualTo("alice");
```

`mockUser("alice").roles("USER")` supplies a simulated `Authentication` named Alice with `ROLE_USER` for **the test client request**. It works well for verifying `authorizeExchange(...)`, `@PreAuthorize` when method security is enabled, and principal access in handlers.

Do not assume `mockUser()`:

- Checked Alice's password in the user store.
- Verified a JWT's signature or expiration.
- Executed a form login flow, OIDC callback, or refresh token issuance.
- Enforced tenant boundaries, resource ownership, or business checks outside the rules actually invoked by the test.
- Can alter the identity on a remote server over a real HTTP connection.

This tool **focuses on authorization behavior**. To test authentication providers, submit real credentials in tests or unit-test the provider directly.

**Note on roles vs authorities:** `roles("ADMIN")` generates `ROLE_ADMIN`. If a rule uses `hasAuthority("SCOPE_notes.read")`, supply that exact authority rather than assuming `ADMIN` grants the scope.

### 6.2. csrf(): supplies a valid CSRF token for testing

Example:

```java
client.mutateWith(mockUser("editor").roles("EDITOR"))
    .mutateWith(csrf())
    .post()
    .uri("/api/notes")
    .bodyValue("{\"text\":\"hello\"}")
    .header("Content-Type", "application/json")
    .exchange()
    .expectStatus().isOk();
```

Spring Security WebFlux enables CSRF protection by default for many state-changing operations. Test `editorWithoutCsrfTokenIsForbidden` shows that **having the right role alone is not enough**. Tests with `csrf()` verify authorization policy **after** the CSRF condition is satisfied.

Never disable CSRF globally with `.csrf(csrf -> csrf.disable())` just because a POST test returned 403. Apps using cookies/sessions, form login, or browser-cached HTTP Basic credentials are exposed to CSRF risk. For stateless APIs sending Bearer tokens explicitly in headers, base CSRF decisions on the actual authentication model and threat profile.

### 6.3. @WithMockUser: using an annotation instead of mutateWith

`spring-security-test` also supports `@WithMockUser`. Example **illustrating a method inside a test class already configured with `springSecurity()`**, not a standalone class:

```java
@Test
@WithMockUser(username = "admin", roles = "ADMIN")
void annotationProvidesMockAdmin() {
    client.get()
        .uri("/api/admin")
        .exchange()
        .expectStatus().isOk();
}
```

Also import `org.springframework.security.test.context.support.WithMockUser` when using this snippet. When a test needs multiple principals or you want security state visible right at the request call, `mutateWith(mockUser(...))` is often clearer. Always verify the annotation/mutator actually flows through the client's security test support rather than putting annotations on a test without wiring Spring Security into the HTTP handler.

### 6.4. Preventing mock state from leaking across tests

In the example class, `@BeforeEach` rebuilds the base client, and each `mutateWith(mockUser(...))` returns a client configured for that specific call. That prevents one test from inheriting another test's principal. Avoid setting a default `mockUser("admin")` for every test and then claiming endpoints protect against anonymous callers, because you never actually tested unauthenticated requests.

## 7. Testing JWT/Bearer in WebFlux: using the right layer

If the application is an **OAuth2 Resource Server** rather than HTTP Basic, you can use `mockJwt()` from Spring Security Test. However, you must include the Spring Security OAuth2 Resource Server dependency and configure `oauth2ResourceServer(...jwt...)` in `SecurityWebFilterChain`; **do not copy this JWT test into the HTTP Basic program in section 4 expecting it to enforce scopes automatically**.

Illustrative example for a configured resource server:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

// In a test of a reactive resource server application:
client.mutateWith(
        mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read")
        )
    )
    .get()
    .uri("/api/reports")
    .exchange()
    .expectStatus().isOk();
```

If `/api/reports` enforces `hasAuthority("SCOPE_reports.read")`, the test verifies the authorization branch for a simulated authority. `mockJwt()` **does not prove** that an IdP-issued JWT has a valid signature, valid issuer/audience, or passes through `ReactiveJwtDecoder`. Add separate token-validation tests or integration tests using the resource server config and verifiable test tokens.

Similarly, `mockOpaqueToken()` supports testing opaque-token principals in a simulated setup; it does not prove the introspection endpoint works. For cookie/session OAuth login, test the login flow, session storage, and cookie transmission when required.

## 8. Distinguishing a mock HTTP handler from a real server

`WebTestClient.bindToApplicationContext(...)` is ideal for reactive security tests because it is fast and loads security filters in-context. Still, in-memory tests cannot verify all production behaviors:

- Does the reverse proxy forward or strip identity headers properly?
- Do `Secure`/`SameSite`/domain/path cookie attributes work properly in browsers?
- Are TLS, CORS with real origins, and external redirects configured properly?
- Do the real HTTP server's header/body limits, compression, and timeouts match requirements?
- Do sessions, load balancers, multiple instances, and inter-service networking work as configured?

To test real networking, use `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` with `@AutoConfigureWebTestClient` appropriate for Boot 3.x, or build `WebTestClient.bindToServer().baseUrl("http://localhost:<port>")`. Tests must send Basic credentials or Bearer tokens **actually accepted by the test environment**. Do not use `mockUser()` to impersonate identities on an independent server.

Live-server test skeleton (illustrated in a Boot 3.x app with a running test server):

```java
@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class LiveHttpSecurityTest {

    @Autowired
    WebTestClient client;

    @Test
    void anonymousAdminIsUnauthorized() {
        client.get()
            .uri("/api/admin")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

In Boot 3.x, import `@AutoConfigureWebTestClient` from `org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient`. In Boot 4.x, package names/test starters differ, so follow your exact version. The snippet above is only an **illustrative skeleton** for a separate test class in a project with the app class and security config from section 4; it is not a standalone file with all imports.

In live-server tests, failures also involve database state and transaction commit timing. If tests use a database, create isolated fixtures and clean up appropriately; do not assume a test-side transaction rollback reverts transactions committed on server threads/connections.

## 9. `@WebFluxTest` slice tests and why security config is easy to miss

`@WebFluxTest(SomeController.class)` loads a small web slice to test controllers faster than `@SpringBootTest`. However, **application service beans, repositories, and custom `SecurityWebFilterChain` configurations may not be loaded automatically**. Therefore:

1. To test **controller behavior** in isolation, `@WebFluxTest` can fit; mock collaborators and import needed config.
2. To verify the **application's authorization chain**, use `@SpringBootTest` (as in the example) or `@Import(SecurityConfig.class)` into the slice test.
3. Do not see a `@WebFluxTest` return 401/403 and assume production's custom matchers were tested; it may be a different default security setup.
4. If the project uses `RouterFunction` instead of `@RestController`, the slice test must import the right routes/beans or use a full context.

Keep the difference between **mocking the app** and **mocking the identity** clear:

- `bindToApplicationContext` keeps the real app in the test context without opening a network server.
- `mockUser` replaces identity provisioning, not the whole application.
- `@WebFluxTest` narrows the beans loaded into the application context.
- `bindToController` attaches only specified controller(s), easily omitting production `WebFilter`s.

Whenever a test keeps returning 200 on an endpoint that should require a role, check whether the security chain was loaded, `springSecurity()` was applied, and the rule matches the URL.

## 10. Method security and propagating SecurityContext across reactive chains

In larger systems, authorization does not live only in `authorizeExchange`. Services can use `@EnableReactiveMethodSecurity` and `@PreAuthorize` to enforce permissions at business methods—such as roles/scopes or resource checks. You then must test **calls through the Spring proxy** and Reactor Context rather than invoking methods directly on `new Service()`.

**Illustrative example on a reactive service with reactive method security enabled**:

```java
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> privilegedAction() {
    return Mono.just("approved");
}
```

This is an illustrative method that must reside in a Spring-managed service with the matching annotation/imports. When invoked through a controller calling the service, `WebTestClient` can verify regular users receive 403 while admins receive 200. Calling the method on a non-proxied instance skips the annotation.

In Reactor, operators such as `publishOn(...)`, `flatMap(...)`, and async scheduling can switch threads; never rely on Servlet `SecurityContextHolder.getContext()` assuming the principal rides on `ThreadLocal`. Reactive security uses `ReactiveSecurityContextHolder` and Reactor Context. To read the identity inside a reactive service, use the reactive context API, for example:

```java
Mono<String> currentAuthenticatedName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
}
```

This is an **illustrative method**; import `org.springframework.security.core.context.ReactiveSecurityContextHolder` and `reactor.core.publisher.Mono`. When no reactive security context exists, the publisher can complete empty; never treat an empty stream as an authenticated identity. Testing with `mockUser()` should prove the identity reaches the tested method via the right context.

## 11. Testing Flux, SSE, and continuous streaming endpoints

`WebTestClient` can assert both single-value (`Mono`) and multi-item (`Flux`) reactive responses. For `Mono` in the example, `expectBody(String.class)` or `expectBody().jsonPath(...)` suffices. For streaming or Server-Sent Events endpoints, responses may not complete quickly, so calling `expectBody()` to buffer the entire stream can hang until timeout.

For finite streams, use `returnResult(...)` to obtain the body as a `Flux` and verify item counts and completion with `StepVerifier`. For infinite streams, check the first few events and then **cancel the subscription** rather than waiting for completion. Conceptual example against an existing stream endpoint:

```java
FluxExchangeResult<String> result = client
    .mutateWith(mockUser("alice").roles("USER"))
    .get()
    .uri("/api/events")
    .exchange()
    .expectStatus().isOk()
    .returnResult(String.class);

StepVerifier.create(result.getResponseBody())
    .expectNextCount(2)
    .thenCancel()
    .verify();
```

This snippet is an **additional illustration** requiring a real `/api/events` endpoint emitting at least two String-decodable items. Import `org.springframework.test.web.reactive.server.FluxExchangeResult` and `reactor.test.StepVerifier`. For SSE, verify the actual media type and event/decoder types. Do not paste this snippet into the complete test in section 5 because the sample app defines no `/api/events` endpoint.

Note that security can check permissions when establishing the subscription/request, yet if stream items contain data belonging to multiple users, **per-resource filtering must still run inside the business pipeline**. A "stream connected successfully" test does not prove every emitted event is authorized.

## 12. Diagnosing 401, 403, or wrong redirect failures in tests

### Case 1: expected 401 but received 302

The usual cause is form login being enabled or an `AuthenticationEntryPoint` choosing a redirect. For JSON APIs, configure HTTP Basic/Bearer with the matching entry point. In the sample app, `formLogin(form -> form.disable())` ensures anonymous GET `/api/admin` expects 401. Never change the assertion to 302 without understanding the API contract.

### Case 2: mock admin still receives 403

Check step by step:

- Is `springSecurity()` really applied to the context-bound `WebTestClient`?
- Does the `/api/admin` matcher match the test path?
- Does the test use `roles("ADMIN")` or another authority? `hasRole("ADMIN")` requires `ROLE_ADMIN`.
- For POST/PUT/DELETE, is a CSRF token missing, or did CORS or another rule block before roles?
- Does the controller/service have `@PreAuthorize` or extra business authorization checks?

Never assume every 403 means a missing role; CSRF, policy engines, or other control layers can return 403.

### Case 3: test with no principal still returns 200 for a private endpoint

Check whether the test uses a default `mockUser`, class-level `@WithMockUser`, or never loaded the security filter. A controller-only client does not carry production config automatically. Retry from a clean client with no mutators and verify `.anyExchange().authenticated()`.

### Case 4: valid Basic credentials return 401

Verify `MapReactiveUserDetailsService` is loaded, the test username/password match, the password encoder/format is valid, and the server enables HTTP Basic. Passing `mockUser` tests does not prove Basic login works; keep at least one real-credentials test to distinguish the two layers.

### Case 5: POST with right role gets 403

Split into two tests:

1. Editor **without** CSRF token → 403.
2. Editor **with** `csrf()` → 200.

Then test USER **with** `csrf()` → 403. These three scenarios separate CSRF failures from role failures. Changing both auth and CSRF in a single edit makes it hard to tell which condition failed.

### Case 6: 404 instead of 401/403

The endpoint may not be component-scanned, the URL may be misspelled, the controller may lack annotations, or the test context may omit a `RouterFunction`. When a request passes security with valid permissions yet no handler exists, HTTP 404 is expected; it does not prove security is broken. Verify the test hits the real path and the controller bean is present.

### Case 7: test behaves differently from production

In-memory tests skip networking, reverse proxies, OAuth identity providers, TLS, CORS preflight, and certain session/cookie nuances. Add live-server or end-to-end tests for network/infrastructure-dependent behaviors. Do not try to cram every kind of test into a portless `@SpringBootTest`.

## 13. Designing a strong security test matrix

Instead of writing a single `200 OK` test, lay out a condition table:

| Target | Action | Anonymous | USER | EDITOR | ADMIN |
| --- | --- | --- | --- | --- | --- |
| `GET /api/public` | Public read | 200 | 200 | 200 | 200 |
| `GET /api/admin` | Admin view | 401 | 403 | 403 | 200 |
| `GET /api/me` | View current identity | 401 | 200 | 200 | 200 |
| `POST /api/notes` with CSRF | Create note | Depends on filter order; never 200 | 403 | 200 | 403 in sample policy |
| `POST /api/notes` without CSRF | Create note | Never 200 | 403 | 403 | 403 |

The bottom row reflects **the sample app's default CSRF behavior**. For stateless Bearer APIs designed without automatic cookies, CSRF strategy differs and needs its own tests.

Additional test categories to include as products grow:

- **Unauthenticated tests:** missing tokens/passwords, wrong credentials, expired sessions.
- **Negative authorization tests:** valid identity lacking role/scope, wrong tenant, non-owner, revoked resource permissions.
- **CSRF/CORS tests:** state-changing methods missing tokens, CORS preflight from foreign origins, valid headers/credentials.
- **Controller/business tests:** validation errors, missing records, accurate JSON status/fields.
- **Reactive tests:** `SecurityContext` propagation across operators, service policies executing inside publishers without blocking I/O.
- **Real HTTP tests:** connectivity, redirects, cookies, TLS/proxies when needed.
- **Streaming tests:** no leakage of unauthorized users' events, subscription cancellation/timeout handling.

A good matrix distinguishes the **HTTP result** from the **reason it must happen**. For instance, a POST without CSRF returning 403 does not prove roles are checked; a USER with CSRF returning 403 exercises the role-rejection branch of that policy.

## 14. Project adoption checklist

1. Ensure the app really runs reactive WebFlux; use `ServerHttpSecurity` and `SecurityWebFilterChain`.
2. Add `spring-security-test`; verify `spring-boot-starter-test` and JUnit Platform dependencies.
3. Build `WebTestClient.bindToApplicationContext(context).apply(springSecurity())` to test `WebFilter` integration without opening a port.
4. Use `mockUser()` / `@WithMockUser` for authorization tests; add real HTTP Basic/Bearer tests for authentication and token validation.
5. For write requests, test both **with and without CSRF**, as well as sufficient and insufficient roles.
6. Assert response status, headers, and bodies—not merely that a controller was invoked.
7. Never let slice tests bypass security config: with `@WebFluxTest`, import the exact security configuration under test.
8. Never use `mockUser()` to draw conclusions about a server over the network; add `RANDOM_PORT` or equivalent environment tests.
9. For sensitive business operations, test object-specific authorization inside services, not only URL roles.
10. Track Spring Boot/Security versions; check test annotation package changes during major upgrades.

**Most important rule:** `WebTestClient` truly tests reactive Spring Security only when you clearly specify **which context, which security filters, and which test identity** are active. A sound suite includes anonymous callers, under-privileged users, authorized users, missing-CSRF requests, and valid-CSRF requests, while keeping a real authentication path tested so "mock principal passes" is never confused with "production login is secure."

### References

- [Spring Security 6.5 — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security 6.5 — Testing Authentication with WebTestClient](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html)
- [Spring Security — Testing with CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html)
- [Spring Security — Testing OAuth2 and mockJwt](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html)
- [Spring Security — WebFlux Security Configuration](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
