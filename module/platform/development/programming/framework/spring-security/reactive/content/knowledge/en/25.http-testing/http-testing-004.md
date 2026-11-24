# @WithMockUser, mockUser(), and Anonymous Users

> **Parent topic:** HTTP testing in reactive Spring Security. This lesson shows how to use **Spring Security Test 6.5.x, Spring WebFlux, WebTestClient, Java 17+, Spring Boot 3.x, and JUnit 5** to test mocked users with `@WithMockUser` or `mockUser()`, **anonymous** users, role/scope authorization, HTTP 200/401/403, CSRF, and reactive method security. Passwords in the examples are demo data only, never for real systems.

## 1. Learning Objectives

Upon completion, you will be able to:

1. Distinguish authentication and authorization when testing HTTP in WebFlux.
2. Create a mock `Authentication` with `@WithMockUser`, knowing its default username and authority.
3. Use `WebTestClient.mutateWith(mockUser(...))` to switch the principal for a single test client rather than altering every request.
4. Understand `@WithAnonymousUser`, requests without credentials, and why anonymous callers can be blocked on protected endpoints.
5. Choose `roles = "ADMIN"` versus `authorities = "SCOPE_reports.read"` appropriately.
6. Set up `WebTestClient.bindToApplicationContext(context).apply(springSecurity())`.
7. Write tests expecting 200 for authorized users, 403 for authenticated users lacking privileges, and 401 for anonymous callers when an HTTP Basic entry point is configured.
8. Test CSRF-protected POST requests with `mutateWith(csrf())`; understand why the right role can still return 403.
9. Test `@PreAuthorize` on a reactive service using `StepVerifier` and Reactor Context.
10. Write separate tests sending real HTTP Basic credentials so `@WithMockUser` is never mistaken for password verification.
11. Understand why mock users do not replace `mockJwt()` or real JWT/opaque token validation, and why they are not transmitted over a remote HTTP port.
12. Design test isolation, preventing class-level annotations or mutated clients from inadvertently granting privileges to anonymous tests.

**Principle:** A mock identity **only simulates an already-authenticated Authentication**. It helps verify authorization logic, but **does not prove real credentials, passwords, JWT signatures, or an IdP were verified**.

## 2. Authentication, authorization, and anonymous

Authentication answers: **Who is calling?**

- HTTP Basic: the server reads username/password from `Authorization: Basic ...`, using `ReactiveUserDetailsService` and `PasswordEncoder` to verify.
- OAuth2 Resource Server: the server reads `Authorization: Bearer ...`, using a JWT decoder or opaque token introspection.
- Session login: the principal comes from an established login session.
- `@WithMockUser` and `mockUser()`: Spring Security Test constructs a fake principal/authorities without verifying real credentials.

Authorization answers: **What is that principal allowed to do?**

```java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/public/ping").permitAll()
    .pathMatchers("/me").authenticated()
    .pathMatchers("/admin").hasRole("ADMIN")
    .pathMatchers("/reports").hasAuthority("SCOPE_reports.read")
    .anyExchange().denyAll()
);
```

This is a configuration snippet. A user with `ROLE_USER` cannot enter `/admin`. Having `ROLE_ADMIN` does not automatically grant `SCOPE_reports.read` because that is a different authority.

Anonymous refers to requests that Spring Security has not verified as a valid account/session. In many configurations, an `AnonymousAuthenticationToken` sits in the security context. An easy-to-miss detail: this token type can have `isAuthenticated()==true` on the object itself, yet `authenticated()` in Spring Security authorization expressions **does not treat anonymous as a logged-in user**. Never check `auth != null && auth.isAuthenticated()` on your own and use it as an authorization decision.

### 2.1 HTTP outcome model

| Request | Authentication | Rule | Common outcome |
| --- | --- | --- | --- |
| GET public | Anonymous | permitAll | 200 |
| GET protected without credentials | Anonymous | authenticated | 401 with HTTP Basic/Bearer entry point |
| GET admin with ROLE_USER | Mock/real authenticated | hasRole("ADMIN") | 403 |
| GET admin with ROLE_ADMIN | Mock/real authenticated | hasRole("ADMIN") | 200 |
| GET reports with SCOPE_reports.read | Mock/real authenticated | exact authority | 200 |
| GET reports with ROLE_ADMIN but no scope | Authenticated | exact authority | 403 |
| POST editor without CSRF | Authenticated | CSRF protection enabled | 403 |
| POST editor with CSRF + required role | Authenticated | HTTP + method security | 200 |

**Do not assume every project always returns 401 for anonymous.** With form login, requests may receive a 302 redirect to the login page. When a POST lacks a CSRF token, it may receive 403 before reaching authentication/authorization logic. The demo enables Basic and disables form login to keep 401/403 assertions clear.

## 3. @WithMockUser

Import:

```java
import org.springframework.security.test.context.support.WithMockUser;
```

The annotation can be placed on a **test method or test class**. Spring Security Test creates a `UsernamePasswordAuthenticationToken` with a Spring Security `User` principal and the declared authorities; the mock user is **not** a record queried from a database.

### 3.1 Defaults of @WithMockUser

```java
@Test
@WithMockUser
void example() {
    client.get().uri("/me")
        .exchange()
        .expectStatus().isOk();
}
```

Default values:
- Username: `user`.
- Mock password: `password`; **no password verification occurs**.
- Granted authority: `ROLE_USER` from role `USER`.

If the endpoint returns `Principal.getName()`, the test will see `user`. Never claim that the account `user` exists in `MapReactiveUserDetailsService` or a production DB just because the test passes.

### 3.2 Changing username and role

```java
@Test
@WithMockUser(username = "alice", roles = "USER")
void aliceCanReadOwnProfile() {
    client.get().uri("/me")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class).isEqualTo("alice");
}
```

`roles = "USER"` is converted into authority `ROLE_USER`. For admin:

```java
@Test
@WithMockUser(roles = "ADMIN")
void adminCanReadRestrictedPage() {
    client.get().uri("/admin")
        .exchange()
        .expectStatus().isOk();
}
```

**Do not use `roles = "ROLE_ADMIN"`**: Spring Security automatically prepends the `ROLE_` prefix to roles. If you already have the full string, use `authorities = "ROLE_ADMIN"` or pass just `roles = "ADMIN"`.

### 3.3 Roles and scope authorities are different

Rule:

```java
.pathMatchers("/reports")
    .hasAuthority("SCOPE_reports.read")
```

Correct test:

```java
@Test
@WithMockUser(authorities = "SCOPE_reports.read")
void reportScopeCanReadReports() {
    client.get().uri("/reports")
        .exchange()
        .expectStatus().isOk();
}
```

Semantically wrong: `roles = "SCOPE_reports.read"` creates `ROLE_SCOPE_reports.read`, which does not match `SCOPE_reports.read`.

When multiple authorities are needed, provide the complete list:

```java
@WithMockUser(authorities = {
    "ROLE_ADMIN",
    "SCOPE_reports.read"
})
```

Use `roles` or `authorities` deliberately; avoid specifying both and implicitly hoping they merge without checking the annotation's contract.

## 4. mockUser(): WebTestClient mutator

Static import:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
```

Example:

```java
client.mutateWith(mockUser())
    .get().uri("/me")
    .exchange()
    .expectStatus().isOk();
```

`mockUser()` also creates the default mock principal `user` with `ROLE_USER`. Unlike the annotation, this is a **WebTestClient mutator**, ideal when a test needs to vary identities per request.

### 4.1 Mutating a client does not make the original client an admin

```java
WebTestClient adminClient = client.mutateWith(
    mockUser("bob").roles("ADMIN")
);

adminClient.get().uri("/admin")
    .exchange()
    .expectStatus().isOk();

client.get().uri("/admin")
    .exchange()
    .expectStatus().isUnauthorized();
```

The snippet assumes the original `client` has no class-level `@WithMockUser` or credentials/session. The mutated client gets identity `bob`, while the original client still does not have admin attached.

### 4.2 Mutating authorities instead of roles

```java
client.mutateWith(
    mockUser("analyst").authorities(
        new SimpleGrantedAuthority("SCOPE_reports.read")
    )
).get().uri("/reports")
 .exchange()
 .expectStatus().isOk();
```

Requires importing `org.springframework.security.core.authority.SimpleGrantedAuthority`. Do not mix `roles("ADMIN")` with `authorities(...)` expecting both sets to merge automatically as you wish.

### 4.3 Comparing @WithMockUser and mockUser()

| Criterion | @WithMockUser | mockUser() |
| --- | --- | --- |
| Placement | Method/class annotation | `mutateWith` on WebTestClient |
| Primary scope | Test lifecycle | Specific client/request |
| Username | `username = "alice"` | `mockUser("alice")` |
| Role | `roles = "ADMIN"` | `mockUser().roles("ADMIN")` |
| Exact authority | `authorities = "SCOPE_x"` | `authorities(new SimpleGrantedAuthority("SCOPE_x"))` |
| Runs Basic password verification? | No | No |
| Verifies JWT? | No | No |
| Ease when testing multiple users | Requires multiple tests/annotations | Create multiple mutated clients |
| Needs Spring Security Test integration | Yes | Yes |

**Tip:** Annotations keep single-identity tests concise. Mutators are handier when testing alice, bob, admin, and anonymous within the same method.

## 5. @WithAnonymousUser and requests without credentials

Import:

```java
import org.springframework.security.test.context.support.WithAnonymousUser;
```

If the test class has **no** default mock user, simply omit annotations and Basic/Bearer headers:

```java
@Test
void publicEndpointAllowsAnonymous() {
    client.get().uri("/public/ping")
        .exchange()
        .expectStatus().isOk();
}

@Test
void protectedEndpointRejectsAnonymous() {
    client.get().uri("/me")
        .exchange()
        .expectStatus().isUnauthorized();
}
```

When a test class has a class-level `@WithMockUser`, a method-level `@WithAnonymousUser` can override it:

```java
@SpringBootTest
@WithMockUser(roles = "USER")
class ClassLevelExample {

    @Test
    void testHasMockUser() {
        // Test calls in this method have mock user ROLE_USER.
    }

    @Test
    @WithAnonymousUser
    void testOverridesClassUserWithAnonymous() {
        // Does not implicitly inherit the class-level authenticated user.
    }
}
```

This is an **annotation illustration**, not a complete test class since it has no client/assertions. The purpose is to prevent anonymous tests from unexpectedly succeeding by inheriting class-level auth.

### 5.1 Anonymous does not inherently have data access

Anonymous can have a principal represented as `anonymousUser` and authority `ROLE_ANONYMOUS`. This is not equivalent to a real account. Never grant access to personal data simply because `Authentication.getName()` returns a non-empty string or `isAuthenticated()` returns true. Rely on Spring Security authorization rules and proper domain ACLs.

### 5.2 Test public policies before protected ones

A public `permitAll()` endpoint does not require a mock user; it must work for anonymous callers. If you only test a public endpoint with `@WithMockUser`, that test **does not prove** you configured the route as public properly.

Similarly, an `authenticated()` route needs a true negative test without credentials; a mock-authenticated test returning 200 is not enough to prove the endpoint is protected.

## 6. WebTestClient + springSecurity() setup

In Spring Security 6.5 reactive tests, the typical configuration is:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@BeforeEach
void setUp() {
    client = WebTestClient.bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();
}
```

- `bindToApplicationContext` dispatches requests internally through the WebFlux application context.
- `apply(springSecurity())` attaches Spring Security Test integration to WebTestClient.
- `configureClient().build()` finalizes the client.
- With `@SpringBootTest`, Spring TestContext and security test listeners manage the lifecycle of `@WithMockUser`/`@WithAnonymousUser`.
- WebFlux SecurityContext uses **Reactor Context**, not just Servlet's `ThreadLocal SecurityContextHolder`.

**Do not confuse with MVC:** Servlet tests use `MockMvc`, `HttpSecurity`, `SecurityFilterChain`, and `SecurityMockMvcRequestPostProcessors.user()`. WebFlux uses `WebTestClient`, `ServerHttpSecurity`, `SecurityWebFilterChain`, and `SecurityMockServerConfigurers.mockUser()`.

Using only `WebTestClient.bindToController(new Controller())` without wiring the WebFlux SecurityFilterChain may run the handler while bypassing authorization. To test real filters/security, use bind-to-application-context with `springSecurity` support or an equivalently configured integration test.

## 7. Mini project: Java 17+, Spring Boot 3.x, WebFlux

The example provides:

| Endpoint | Policy | To test |
| --- | --- | --- |
| GET `/public/ping` | `permitAll()` | Anonymous 200 |
| GET `/me` | `authenticated()` | Anonymous 401; mock/basic user 200 |
| GET `/admin` | `hasRole("ADMIN")` | User 403, admin 200 |
| GET `/reports` | `hasAuthority("SCOPE_reports.read")` | Scope 200, plain role 403 |
| POST `/notes/approve` | HTTP authenticated + `@PreAuthorize("hasRole('EDITOR')")` on service | CSRF + role |
| Other routes | `denyAll()` | No new routes left open by accident |

### 7.1 Dependencies

Create a Java 17+ Spring Boot 3.x Gradle Groovy project with Reactive Web and Security. The dependencies section in `build.gradle` (assuming Spring Boot plugins are present):

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

`spring-security-test` contains mock annotations/mutators; `reactor-test` contains `StepVerifier`. Do not add `spring-boot-starter-web` to a WebFlux-only project, because Boot usually prioritizes Spring MVC when both starters are present.

### 7.2 File layout

```text
src/main/java/com/example/reactivetest/
  ReactiveTestApplication.java
  WebSecurityConfiguration.java
  NoteService.java
  DemoController.java
src/test/java/com/example/reactivetest/
  ReactiveHttpSecurityTest.java
  NoteServiceSecurityTest.java
```

Each public class is saved in a file of the same name under package `com.example.reactivetest`. These examples require the Spring Boot dependency classpath and are not meant to be compiled standalone with `javac`.

### 7.3 ReactiveTestApplication.java

`src/main/java/com/example/reactivetest/ReactiveTestApplication.java`:

```java
package com.example.reactivetest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveTestApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveTestApplication.class, args);
    }
}
```

### 7.4 WebSecurityConfiguration.java

`src/main/java/com/example/reactivetest/WebSecurityConfiguration.java`:

```java
package com.example.reactivetest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class WebSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        var reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-password"))
            .roles("USER")
            .build();

        var editor = User.withUsername("editor")
            .password(encoder.encode("editor-demo-password"))
            .roles("USER", "EDITOR")
            .build();

        var admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo-password"))
            .roles("USER", "ADMIN")
            .build();

        return new MapReactiveUserDetailsService(
            reader, editor, admin
        );
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/me")
                    .authenticated()
                .pathMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/reports")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers(HttpMethod.POST, "/notes/approve")
                    .authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            // CSRF remains ENABLED for unsafe HTTP methods.
            .build();
    }
}
```

- `UserDetailsService` is a demo store, not a production user DB.
- Basic is enabled so tests can verify **real passwords** through the Spring Security authentication filter.
- Form login is disabled so unauthenticated requests are not redirected to a login page; protected anonymous GETs are expected to return 401.
- `@EnableReactiveMethodSecurity` enables `@PreAuthorize` on reactive services.
- CSRF is **not disabled** by default; POSTs without `csrf()` can return 403 before reaching the service.
- The fallback `denyAll` route prevents new endpoints from becoming public accidentally.

### 7.5 NoteService.java

`src/main/java/com/example/reactivetest/NoteService.java`:

```java
package com.example.reactivetest;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class NoteService {

    @PreAuthorize("hasRole('EDITOR')")
    public Mono<String> approve() {
        return Mono.just("approved");
    }
}
```

The method returns `Mono<String>`, matching reactive method security; `@PreAuthorize` requires `ROLE_EDITOR`. The service must be Spring-managed; calling `new NoteService()` bypasses the method-security proxy.

### 7.6 DemoController.java

`src/main/java/com/example/reactivetest/DemoController.java`:

```java
package com.example.reactivetest;

import java.security.Principal;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    private final NoteService noteService;

    public DemoController(NoteService noteService) {
        this.noteService = noteService;
    }

    @GetMapping(
        value = "/public/ping",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping(
        value = "/me",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> me(Principal principal) {
        return Mono.just(principal.getName());
    }

    @GetMapping(
        value = "/admin",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }

    @GetMapping(
        value = "/reports",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> reports() {
        return Mono.just("reports-ok");
    }

    @PostMapping(
        value = "/notes/approve",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> approve() {
        return noteService.approve();
    }
}
```

`Principal` on `/me` is only injected after the `authenticated` rule. Public endpoints do not attempt to extract a username so anonymous callers do not enter user-specific logic. This is a simplified example without tenant/resource ACLs.

## 8. ReactiveHttpSecurityTest.java: 18 HTTP tests

Create `src/test/java/com/example/reactivetest/ReactiveHttpSecurityTest.java`. The suite uses `WebTestClient` bound to the real application context without opening an HTTP port. Tests with `@WithMockUser` test authorization; Basic-header tests omit annotations so they pass through the authentication filter.

```java
package com.example.reactivetest;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
class ReactiveHttpSecurityTest {

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
    void anonymousCanReadPublic() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void unauthenticatedCannotReadMe() {
        client.get().uri("/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    @WithAnonymousUser
    void explicitlyAnonymousCannotCallAdmin() {
        client.get().uri("/admin")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    @WithMockUser
    void defaultMockUsernameIsUser() {
        client.get().uri("/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("user");
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void aliceNameComesFromMockPrincipal() {
        client.get().uri("/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("alice");
    }

    @Test
    @WithMockUser(roles = "USER")
    void userCannotCallAdmin() {
        client.get().uri("/admin")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void annotatedAdminCanCallAdmin() {
        client.get().uri("/admin")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-ok");
    }

    @Test
    void perRequestAdminDoesNotChangeOriginalClient() {
        WebTestClient asAdmin =
            client.mutateWith(mockUser("bob").roles("ADMIN"));

        asAdmin.get().uri("/admin")
            .exchange()
            .expectStatus().isOk();

        client.get().uri("/admin")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void mockUserWithExactScopeCanReadReports() {
        client.mutateWith(
            mockUser("analyst").authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read")
            )
        ).get().uri("/reports")
         .exchange()
         .expectStatus().isOk()
         .expectBody(String.class).isEqualTo("reports-ok");
    }

    @Test
    @WithMockUser(authorities = "SCOPE_reports.read")
    void annotatedScopeCanReadReports() {
        client.get().uri("/reports")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminRoleDoesNotImplyReportScope() {
        client.get().uri("/reports")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    @WithMockUser(roles = "EDITOR")
    void editorPostWithoutCsrfIsRejected() {
        client.post().uri("/notes/approve")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    @WithMockUser(roles = "EDITOR")
    void editorWithCsrfCanApprove() {
        client.mutateWith(csrf())
            .post().uri("/notes/approve")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("approved");
    }

    @Test
    @WithMockUser(roles = "USER")
    void csrfDoesNotGrantEditorRole() {
        client.mutateWith(csrf())
            .post().uri("/notes/approve")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void correctBasicPasswordAuthenticatesRealFilter() {
        client.get().uri("/me")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reader");
    }

    @Test
    void incorrectBasicPasswordIsRejected() {
        client.get().uri("/me")
            .headers(h -> h.setBasicAuth(
                "reader", "incorrect-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void basicReaderLacksAdminRole() {
        client.get().uri("/admin")
            .headers(h -> h.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void basicAdminCanCallAdmin() {
        client.get().uri("/admin")
            .headers(h -> h.setBasicAuth(
                "admin", "admin-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-ok");
    }
}
```

**Why are these tests valuable?**
- Anonymous tests check both public and protected endpoints without being masked by class-level `@WithMockUser`.
- Mock annotation tests verify username/roles and HTTP rules.
- Mock mutator tests verify isolation and exact scope authorities.
- POST tests prove CSRF and roles are two separate layers.
- Basic tests use **real credentials** from the demo `MapReactiveUserDetailsService`, without bypassing the password manager.

### 8.1 Expected results

| Group | Scenario | HTTP |
| --- | --- | --- |
| Anonymous | GET /public/ping | 200 |
| Anonymous | GET /me without credentials | 401 |
| Explicit anonymous | GET /admin | 401 |
| @WithMockUser default | GET /me, username=user | 200 |
| @WithMockUser alice | GET /me, username=alice | 200 |
| @WithMockUser ROLE_USER | GET /admin | 403 |
| @WithMockUser ROLE_ADMIN | GET /admin | 200 |
| mockUser bob/ADMIN | GET /admin | 200 |
| Original client without mock | GET /admin | 401 |
| mockUser SCOPE_reports.read | GET /reports | 200 |
| @WithMockUser SCOPE_reports.read | GET /reports | 200 |
| Role ADMIN without scope | GET /reports | 403 |
| EDITOR without csrf() | POST /notes/approve | 403 |
| EDITOR with csrf() | POST /notes/approve | 200 |
| USER with csrf() | POST /notes/approve | 403 |
| Basic reader valid password | GET /me | 200 |
| Basic reader wrong password | GET /me | 401 |
| Basic reader to admin | GET /admin | 403 |
| Basic admin to admin | GET /admin | 200 |

The table has 19 HTTP assertion rows because `perRequestAdminDoesNotChangeOriginalClient` tests **two requests**. The file has **18 test methods**. These are **expected results from the code**; Gradle was not executed in the authoring environment.

### 8.2 Running the tests

Linux/macOS:

```bash
./gradlew test --tests '*ReactiveHttpSecurityTest'
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*ReactiveHttpSecurityTest'
```

Because `WebTestClient` binds to the application context, there is no need to run `bootRun` before running tests.

## 9. Testing @PreAuthorize on reactive services with StepVerifier

`@EnableReactiveMethodSecurity` combined with `@PreAuthorize` protects services. With reactive return types `Mono`/`Flux`, evaluation relies on `Reactor Context` during subscription.

`src/test/java/com/example/reactivetest/NoteServiceSecurityTest.java`:

```java
package com.example.reactivetest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

import reactor.test.StepVerifier;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
class NoteServiceSecurityTest {

    @Autowired
    NoteService notes;

    @Test
    @WithMockUser(roles = "EDITOR")
    void editorCanApprove() {
        StepVerifier.create(notes.approve())
            .expectNext("approved")
            .verifyComplete();
    }

    @Test
    @WithMockUser(roles = "USER")
    void userIsDenied() {
        StepVerifier.create(notes.approve())
            .expectError()
            .verify();
    }

    @Test
    @WithAnonymousUser
    void anonymousIsDenied() {
        StepVerifier.create(notes.approve())
            .expectError()
            .verify();
    }
}
```

This test verifies the security proxy of the Spring-managed `NoteService`. Using `expectError()` in the two denial cases avoids tying every version/caller to the same exception subclass; when stricter checks are needed, assert `AccessDeniedException` per the real contract.

### 9.1 Why not instantiate the service with `new`?

Wrong:

```java
NoteService service = new NoteService();
StepVerifier.create(service.approve())
    .expectNext("approved")
    .verifyComplete();
```

This code calls an object **without going through the Spring AOP proxy**, so `@PreAuthorize` may not run. Right: autowire `NoteService` from a Spring context with `@EnableReactiveMethodSecurity`.

### 9.2 Why does Reactor Context matter?

Do not call `SecurityContextHolder.setContext(...)` in Servlet style and expect it to propagate across every reactive subscription. In WebFlux, the security context travels via the Reactor subscriber context; Spring Security Test provides `ReactorContextTestExecutionListener` for compatibility.

If you need manual testing without annotations, you can do:

```java
Authentication authentication =
    new TestingAuthenticationToken(
        "alice", "unused", "ROLE_EDITOR");

Mono<String> result = notes.approve()
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(
            authentication)
    );

StepVerifier.create(result)
    .expectNext("approved")
    .verifyComplete();
```

**This is a snippet**, requiring imports for `Authentication`, `TestingAuthenticationToken`, `ReactiveSecurityContextHolder`, `Mono`, and `StepVerifier`; `notes` must be a Spring-managed proxied service. Test annotations are more convenient for standard cases.

## 10. Why does a POST with mock editor still return 403?

`@WithMockUser(roles="EDITOR")` supplies **Authentication**, not a **CSRF token**. Spring Security WebFlux enables CSRF protection by default for state-changing methods (POST/PUT/PATCH/DELETE).

Write two separate tests:

```java
@Test
@WithMockUser(roles = "EDITOR")
void withoutCsrfShouldFail() {
    client.post().uri("/notes/approve")
        .exchange()
        .expectStatus().isForbidden();
}

@Test
@WithMockUser(roles = "EDITOR")
void withCsrfShouldPass() {
    client.mutateWith(csrf())
        .post().uri("/notes/approve")
        .exchange()
        .expectStatus().isOk();
}
```

Static import `csrf` from `SecurityMockServerConfigurers`. For a `ROLE_USER` user, even with a CSRF token, `@PreAuthorize("hasRole('EDITOR')")` on the service still denies access.

### 10.1 CSRF is not a role

| User | CSRF token | Service permission | Expected |
| --- | --- | --- | --- |
| EDITOR | Missing | Has ROLE_EDITOR | 403 due to CSRF |
| EDITOR | Valid | Has ROLE_EDITOR | 200 |
| USER | Valid | Lacks ROLE_EDITOR | 403 due to method security |
| Anonymous | Missing | None | May be 403 (CSRF) or 401 depending on entrypoint/filter order |
| Admin | Valid | HTTP route is denyAll | 403 due to HTTP authorization |

Do not disable CSRF application-wide just to make tests pass. For Bearer-only APIs with no ambient browser credentials, a different CSRF policy may be designed, but only with a clear threat model. CORS does not replace CSRF or authentication either.

## 11. Anonymous, 401/403, and form-login redirects

**401 Unauthorized**: a protected API requires Authentication, yet the caller lacks valid credentials. With HTTP Basic enabled, responses typically include `WWW-Authenticate: Basic ...`.

**403 Forbidden**: the caller is authenticated but lacks authority, or the request was rejected by the CSRF filter. Therefore, two tests sharing `expectStatus().isForbidden()` may be testing **two completely different causes**.

**302 redirect**: if form login is enabled, an anonymous caller hitting a protected route may be redirected to the login page. This does not mean the policy is more or less correct; it is simply a different authentication entrypoint.

**404 Not Found**: if a route does not exist or no handler matches, the status depends on security filter ordering. Never use a lone 404 as proof that authorization blocked a resource.

**Fail closed**: missing/invalid authentication must never become `permitAll` just to avoid failing tests.

## 12. Mock authentication does not verify passwords, JWTs, or an IdP

### 12.1 Real HTTP Basic vs @WithMockUser

`@WithMockUser(username="reader")` passes when the rule only requires `authenticated`, even if `reader` does not exist in the DB. That is a feature of mocking, not a bug.

Testing real credentials requires:

```java
client.get().uri("/me")
    .headers(h -> h.setBasicAuth(
        "reader", "reader-demo-password"))
    .exchange()
    .expectStatus().isOk();

client.get().uri("/me")
    .headers(h -> h.setBasicAuth(
        "reader", "incorrect-password"))
    .exchange()
    .expectStatus().isUnauthorized();
```

**Do not place `@WithMockUser` on a test trying to prove a wrong Basic password fails**, because the mock identity can interfere with the outcome.

### 12.2 JWT and opaque Bearer tokens

A fake mock user with `SCOPE_reports.read` does not prove:
- That the JWT has a valid signature;
- That `iss`, `aud`, `exp`, `nbf`, and allowed algorithms were checked;
- That an opaque token underwent introspection and returned `active:true`;
- That `WWW-Authenticate` or malformed Bearer headers are handled properly;
- That token revocation, role mapping, or tenant scoping works.

If the real app is an OAuth2 Resource Server, Spring Security Test provides `mockJwt()` / `mockOpaqueToken()` to simulate the matching authentication type. Example snippet **only for apps configured as a JWT Resource Server**, not the Basic-only project in section 7:

```java
client.mutateWith(
    mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_reports.read")
    )
).get().uri("/reports")
 .exchange()
 .expectStatus().isOk();
```

Import `mockJwt` from the Spring Security WebFlux Test package. `mockJwt()` still **does not verify the JWS signature**. Add integration tests using a real `ReactiveJwtDecoder` or IdP/JWKS sandbox with invalid issuer/audience/key/exp cases.

### 12.3 Different principal types

`@WithMockUser` normally creates a `UsernamePasswordAuthenticationToken` with a Spring Security `User` principal, **not** a `JwtAuthenticationToken` or an application-specific custom principal.

If production code casts the principal to `JwtAuthenticationToken`, use `mockJwt()` or real token integration tests; `@WithMockUser` can cause a `ClassCastException` even when the real policy works fine. Minimize coupling to auth implementation classes and rely on verified claims/service layers where appropriate.

## 13. In-memory WebTestClient and real servers are not the same

`WebTestClient.bindToApplicationContext(context)` runs through the WebFlux application context in the same test process. `mockUser()` and `@WithMockUser` can participate in Spring Security Test integration.

When the application starts with:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
```

and requests travel over a **real HTTP socket**, the test security context in the test thread **cannot automatically cross the network** to become the server's identity. In E2E/remote HTTP tests, send real Basic/Bearer/session credentials rather than expecting `mockUser()` to spoof identity across the wire.

This does **not** mean `@WithMockUser` is useless for integration tests: it is very useful for **in-memory WebFlux integration**. Simply respect the boundary between local mock security state and credentials crossing a network boundary.

## 14. Test isolation and avoiding security context pollution

A common mistake is putting `@WithMockUser` on the whole class and then writing:

```java
@Test
void noAuthorizationHeaderShouldGet401() {
    client.get().uri("/me")
        .exchange()
        .expectStatus().isUnauthorized();
}
```

Because the class already has a mock user, this test can receive 200 even without an Authorization header. Fix: annotate that method with `@WithAnonymousUser`, or leave the class anonymous by default and add `@WithMockUser` only to the tests that need it.

Do not mutate a shared `client` field and reuse it across multiple tests sequentially; create a fresh `WebTestClient` in `@BeforeEach` and use local variables:

```java
var asUser = client.mutateWith(
    mockUser("alice").roles("USER")
);

var asAdmin = client.mutateWith(
    mockUser("bob").roles("ADMIN")
);
```

Then verify each client individually. Do not use `@TestMethodOrder` to mask state leakage. The goal is for every test to have explicit preconditions, run independently, and run in parallel without randomly losing context.

## 15. Common pitfalls table

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| @WithMockUser has no effect on WebTestClient | Missing springSecurity() or TestContext listeners | Bind application context and apply springSecurity |
| mockUser() fails to compile | Accidentally imported MockMvc user() | Import SecurityMockServerConfigurers.mockUser |
| Mock username passes despite missing from DB | Mock bypasses credential verification | Expected; add a real password test |
| @WithMockUser(roles="ROLE_ADMIN") fails | roles automatically adds prefix | Use roles="ADMIN" |
| Has scope but reports test returns 403 | Used roles instead of exact SCOPE authority | Use authorities="SCOPE_reports.read" |
| Anonymous test returns 200 | Class-level mock user or mutated client | Use @WithAnonymousUser or a separate test class |
| Anonymous test returns 302 | Form login is enabled | Check entrypoint; do not always assume 401 |
| POST with right role still returns 403 | Missing CSRF token | Use mutateWith(csrf()), keep CSRF policy |
| Has csrf yet still returns 403 | Missing HTTP/service authority | Check @PreAuthorize/hasRole |
| @PreAuthorize does not run | Service instantiated with new, missing EnableReactiveMethodSecurity | Autowire proxied service |
| StepVerifier misses Authentication | Missing Reactor Context/TestExecutionListener | Check ReactorContextTestExecutionListener |
| Protected GET returns 200 without headers | Mock identity/session active | Check annotation/client scope |
| Wrong Basic password still gets 200 | Test has a mock user active | Separate real Basic integration test |
| Mock JWT test passes, real server returns 401 | Mock skips signature/issuer verification | Test real ReactiveJwtDecoder and signed tokens |
| ClassCastException with JwtAuthenticationToken | WithMockUser creates username/password token | Use mockJwt or real JWT |
| RANDOM_PORT test ignores mock identity | Test context does not cross HTTP | Send real credentials |
| BindToController test passes when security is broken | Bypasses security filters | Use BindToApplicationContext + springSecurity |
| AnonymousAuthenticationToken has isAuthenticated true | Misunderstood auth object semantics | Use official authorization expressions |
| CSRF test mixed up with auth test | Missing CSRF token on unsafe method | Use GET to isolate authentication or add csrf |
| Every test runs as ADMIN | Testing happy path only | Add anonymous, USER, missing scope/CSRF |
| ROLE_USER accesses another tenant | HTTP role does not replace object authorization | Add domain ACL tests |
| Mock user leaks into another test | Reused mutated client field | Create per-test local clients |
| Security test missing dependency | spring-security-test absent | Add to testImplementation |
| WebFlux test uses MockMvc | Confused Servlet/Reactive stacks | Use WebTestClient, ServerHttpSecurity |

## 16. Multi-layer testing strategy

**Layer A — HTTP authorization with mock identities**

Use `@WithMockUser`, `mockUser()`, and `@WithAnonymousUser` to test:
- Public vs protected;
- 200/401/403 by role/scope;
- Scopes are not equivalent to roles;
- CSRF positive/negative;
- No state leaks between tests.

**Layer B — Real authentication filter**

Use real Basic credentials or Bearer tokens in WebTestClient:
- Valid/wrong passwords;
- Malformed Authorization headers;
- Invalid JWT issuer/audience/expiry/signature;
- Opaque token active true/false;
- Session login/logout/cookies if used by the app.

**Layer C — Reactive method security**

Use `StepVerifier` with the Spring-managed service:
- EDITOR can approve;
- USER/anonymous are denied;
- Domain ACLs and tenant ownership;
- Reactor Context propagation across flatMap/parallel/deferred operations.

**Layer D — E2E**

Use a real server/socket to test:
- TLS/headers/gateway;
- Reverse proxy, CORS, CSRF;
- Cookie/session boundaries;
- Token revocation, key rotation, auth provider outages;
- Real status/challenge bodies per API contract.

Mock identities keep tests fast, deterministic, and clear about authorization intent, but they never replace authentication integration.

## 17. Pre-merge checklist

- [ ] Spring Boot app truly uses WebFlux and SecurityWebFilterChain.
- [ ] Test dependencies include spring-security-test and reactor-test.
- [ ] WebTestClient uses bindToApplicationContext(context).apply(springSecurity()).
- [ ] Anonymous access to public endpoint → 200 is tested.
- [ ] Anonymous access to protected endpoint → 401 (per demo Basic entrypoint) is tested.
- [ ] If class-level @WithMockUser is used, @WithAnonymousUser overrides negative cases.
- [ ] Understand default @WithMockUser creates user/ROLE_USER.
- [ ] Use roles="ADMIN" with hasRole("ADMIN"), not roles="ROLE_ADMIN".
- [ ] Use authorities="SCOPE_reports.read" with hasAuthority(...).
- [ ] Tests cover sufficient role/scope → 200 and insufficient role/scope → 403.
- [ ] Tests cover multiple mock users via client.mutateWith(mockUser(...)).
- [ ] Original client is never permanently mutated or leaking state.
- [ ] For POSTs, missing/valid CSRF and method permissions are tested separately.
- [ ] Never disable CSRF just because a mock-user test returned 403.
- [ ] @EnableReactiveMethodSecurity is enabled and services are Spring-managed.
- [ ] StepVerifier tests for @PreAuthorize cover both success and error cases.
- [ ] Real Basic password tests exist if the app supports Basic auth.
- [ ] If Bearer JWT/opaque tokens are used, real verification integration tests exist.
- [ ] Do not treat mockJwt/mockOpaqueToken as cryptographic verification tests.
- [ ] Do not attempt to pass @WithMockUser over a RANDOM_PORT network boundary.
- [ ] Do not treat AnonymousAuthenticationToken.isAuthenticated() as an authenticated user.
- [ ] Do not use MockMvc post-processors in WebFlux.
- [ ] Negative test cases run independently with no ordering dependencies.
- [ ] Never commit real passwords/tokens in test sources or logs.

## 18. Self-check

**1. Does @WithMockUser verify username/password?** No, it creates a fake Authentication.

**2. Default username and authority of @WithMockUser?** `user` and `ROLE_USER`.

**3. Difference between roles and authorities?** `roles` adds the `ROLE_` prefix; `authorities` uses exact strings.

**4. What configuration does `hasAuthority("SCOPE_reports.read")` require?** `@WithMockUser(authorities="SCOPE_reports.read")` or `mockUser().authorities(new SimpleGrantedAuthority(...))`.

**5. How does mockUser differ from @WithMockUser?** One is a WebTestClient mutator, the other is a test-lifecycle annotation.

**6. When is @WithAnonymousUser especially useful?** When overriding a class-level mock user.

**7. Why might a request without an Authorization header still return 200?** Because `@WithMockUser` or a mutated WebTestClient already supplied Authentication.

**8. When does a protected anonymous request typically return 401?** With an HTTP Basic/Bearer entrypoint on an API without valid user credentials.

**9. Why does USER accessing /admin get 403?** Authenticated, but lacking `ROLE_ADMIN`.

**10. Why does an editor POST without csrf() get 403?** Missing CSRF token, not missing role.

**11. Does having csrf() automatically make a USER an EDITOR?** No; CSRF does not replace permissions checked by `@PreAuthorize`.

**12. How should a service be obtained to test @PreAuthorize?** Autowire the Spring-managed bean rather than instantiating with `new`.

**13. Where does reactive method security get the identity from?** Subscriber Reactor Context, supported by Spring Security Test listeners.

**14. Can AnonymousAuthenticationToken.isAuthenticated() be true?** Yes; authorization expressions explicitly distinguish anonymous.

**15. Can a mock user replace a signed JWT token integration test?** No. It does not verify signature/issuer/audience/exp.

**16. Why doesn't WebTestClient RANDOM_PORT use mockUser like in-memory?** Mock test SecurityContext does not cross the network.

**17. What harm comes from confusing WebTestClient with MockMvc?** Wrong stack DSL and test processors, and security filters may not run.

**18. Why test both 401 and 403?** To distinguish unauthenticated from authenticated-but-unauthorized, and catch authorization bypasses.

## 19. Summary

- **`@WithMockUser`** creates a mock user for a test method/class; defaults to `user` + `ROLE_USER`.
- **`mockUser()`** attaches a mock Authentication via a WebTestClient mutator per client/request; well suited for testing multiple identities.
- **`@WithAnonymousUser`** tests anonymous access and overrides class-level mock users.
- **`springSecurity()`** must be applied in standard WebFlux WebTestClient setups.
- **`csrf()`** is a separate requirement when testing CSRF-protected POST/unsafe HTTP methods.
- **`@PreAuthorize` + `StepVerifier`** verifies Reactor Context-based method security.
- **Mock authorization tests != real authentication tests**: supplement with Basic/Bearer integration and negative cases.

**Two key takeaways:** Anonymous callers must be rejected on protected endpoints, and a passing mock user with roles does not mean the server verified real credentials. Structure tests to cover anonymous access, sufficient/insufficient privileges, CSRF, and real authentication filters.

### Official references

- [Spring Security 6.5 — Testing Authentication (Reactive)](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html)
- [Spring Security 6.5 — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security 6.5 — Testing Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/test/method.html)
- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security 6.5 — CSRF Protection in WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security 6.5 — Reactive OAuth2 Test](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html)
- [Spring Security 6.5.x API — @WithMockUser](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/test/context/support/WithMockUser.html)
- [Spring Security 6.5.x API — @WithAnonymousUser](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/test/context/support/WithAnonymousUser.html)
