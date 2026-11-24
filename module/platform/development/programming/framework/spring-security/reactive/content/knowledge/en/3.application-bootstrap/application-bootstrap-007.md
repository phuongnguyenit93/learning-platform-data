# Configuring Sample Users with `MapReactiveUserDetailsService`

## 1. Goal and context

During the **bootstrapping phase of a reactive Spring Security application**, you often need a few sample accounts to test login, verify authorization, and confirm that the Spring WebFlux security pipeline works before integrating a real database or identity system.

`MapReactiveUserDetailsService` is a simple setup for this scenario. It stores `UserDetails` records in an in-memory `Map` and provides a user-lookup API by username returning Reactor `Mono<UserDetails>`. You do not need JDBC, R2DBC, or an external identity server to start testing basic security rules.

After this lesson, you will be able to:

1. Distinguish `ReactiveUserDetailsService` from Servlet/MVC's `UserDetailsService`.
2. Declare multiple sample accounts using `User.withUsername(...)` and `MapReactiveUserDetailsService`.
3. Encode passwords with `PasswordEncoder` and grant permissions with roles.
4. Connect the sample user store to `SecurityWebFilterChain`, HTTP Basic, and WebFlux endpoints.
5. Run, test 200/401/403 outcomes, and diagnose common configuration errors.
6. Explain why an in-memory solution is only suitable for learning, demos, and controlled tests.

**Scope:** configuring sample users in a Spring Boot + Spring WebFlux + Spring Security application. Implementing production user stores, OAuth2/OIDC, JWT, or federated login are subsequent topics.

## 2. What is `MapReactiveUserDetailsService`?

Key components:

| Component | Role |
| --- | --- |
| `UserDetails` | Represents username, encoded password, authorities/roles, and account status flags needed for authentication |
| `User.withUsername(...)` | Builder for creating sample `UserDetails` |
| `ReactiveUserDetailsService` | Reactive interface providing `Mono<UserDetails> findByUsername(String username)` |
| `MapReactiveUserDetailsService` | `ReactiveUserDetailsService` implementation backed by an in-memory `Map` |
| `PasswordEncoder` | Verifies the password supplied by the user against the encoded value in `UserDetails` |
| `SecurityWebFilterChain` | Defines HTTP request protection rules in WebFlux |
| `ServerHttpSecurity` | DSL for creating `SecurityWebFilterChain` in reactive applications |

Conceptual flow with HTTP Basic:

```text
HTTP request with Authorization: Basic ...
                 |
                 v
       Spring Security WebFilter
                 |
                 v
     Decode username/password
                 |
                 v
  Reactive authentication infrastructure
                 |
                 v
ReactiveUserDetailsService.findByUsername(...)
                 |
                 v
    MapReactiveUserDetailsService
      (lookup in application memory)
                 |
                 v
    Verify password + user status
                 |
                 v
    Create Authentication if valid
                 |
                 v
    Check authorization in SecurityWebFilterChain
                 |
             200 / 401 / 403
```

This is a **conceptual flow**, not a fixed internal class list across every Spring Security version. `MapReactiveUserDetailsService` only handles user data lookup; it does not create login endpoints or define URL access rules on its own. Spring Security combines it with authentication/authorization components when configured appropriately.

### How does reactive differ from the Servlet approach?

- **WebFlux/reactive:** uses `org.springframework.security.core.userdetails.ReactiveUserDetailsService` and `MapReactiveUserDetailsService`; the lookup method returns `Mono<UserDetails>`. Web security uses `SecurityWebFilterChain` and `ServerHttpSecurity`.
- **Servlet/Spring MVC:** typically uses `UserDetailsService`, `InMemoryUserDetailsManager`, `SecurityFilterChain`, and `HttpSecurity`. The `loadUserByUsername(...)` method returns `UserDetails` directly.

Do not mix `InMemoryUserDetailsManager` and `HttpSecurity` configuration into a pure WebFlux example. If a project adds both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot normally selects Servlet/MVC mode; to learn WebFlux reactive properly, use only the WebFlux starter.

## 3. Prerequisites and example versions

The complete example below targets **Java 17+**, Spring Boot **3.3.5**, Spring Security 6.x managed by Spring Boot, and a Gradle version compatible with Spring Boot 3.3 (such as Gradle 8.5). The core APIs also exist in newer Spring Security lines, but if you want to copy the entire project and run it as-is, use the version set listed here.

Requirements:
- JDK 17 or higher.
- Gradle or a compatible Gradle Wrapper (if a wrapper exists, prefer `./gradlew` on Linux/macOS or `gradlew.bat` on Windows).
- Port 8080 free, or adjust `server.port` and the test commands.

File structure:

```text
reactive-users-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/dev/example/reactiveusers/
    │       ├── ReactiveUsersApplication.java
    │       ├── SecurityConfig.java
    │       └── DemoController.java
    └── test/
        └── java/dev/example/reactiveusers/
            └── SecurityIntegrationTest.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'reactive-users-demo'
```

File `build.gradle`:

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
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-webflux` provides WebFlux and Reactor; `spring-boot-starter-security` provides Spring Security. To test HTTP Basic authentication in this lesson, **there is no need to add a database**. Spring Boot manages dependency versions consistently via its BOM; do not manually pair incompatible Spring Security versions with the Boot version.

## 4. Creating the application bootstrap class

File `src/main/java/dev/example/reactiveusers/ReactiveUsersApplication.java`:

```java
package dev.example.reactiveusers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveUsersApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveUsersApplication.class, args);
    }
}
```

`@SpringBootApplication` enables auto-configuration and component scanning for package `dev.example.reactiveusers`. Place configuration classes, controllers, and tests in this package or underneath it so Spring discovers them.

## 5. Declaring two sample users and protecting URLs

File `src/main/java/dev/example/reactiveusers/SecurityConfig.java`:

```java
package dev.example.reactiveusers;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    public MapReactiveUserDetailsService userDetailsService(
            PasswordEncoder passwordEncoder) {

        UserDetails reader = User.withUsername("reader")
                .password(passwordEncoder.encode("reader-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(passwordEncoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

**Step-by-step explanation:**

1. `@Configuration` declares a Spring configuration class; `@EnableWebFluxSecurity` enables Spring Security support for WebFlux.
2. The `PasswordEncoder` bean uses BCrypt to hash passwords. The strings `reader-pass` and `admin-pass` are plaintext passwords **only in the demo program**; the two `UserDetails` objects store *hashes*, not plaintext strings. BCrypt uses a salt, so hashes can differ on each restart even though the demo passwords stay the same.
3. `User.withUsername(...).password(...).roles(...)` builds a `UserDetails` record containing login credentials and permissions. `roles("USER")` creates authority `ROLE_USER`, while `roles("USER", "ADMIN")` creates `ROLE_USER` and `ROLE_ADMIN`.
4. `new MapReactiveUserDetailsService(reader, admin)` initializes the in-memory store from the two `UserDetails` instances. This constructor takes `UserDetails...` (varargs); there are also constructors accepting `Collection<UserDetails>` or `Map<String, UserDetails>` for other cases. With the map constructor, the map must support non-blocking access.
5. The `MapReactiveUserDetailsService` bean is also a bean of type `ReactiveUserDetailsService`; Spring Security reactive infrastructure can use it to look up usernames. Spring Boot will also stop creating the auto-generated default account once you provide a suitable authentication service.
6. `authorizeExchange` assigns permissions: `/public` allows everyone, `/admin` requires role ADMIN; all remaining URLs require login. Putting specific matchers before `anyExchange()` is critical.
7. `httpBasic(Customizer.withDefaults())` enables HTTP Basic for testing with `curl -u`. `formLogin(form -> form.disable())` disables form login for the API example, avoiding a redirect to a login page when observing Basic 401 responses.
8. `build()` returns `SecurityWebFilterChain` attached to the WebFlux pipeline. This configuration does not use Servlet's `HttpSecurity`.

**Key takeaway:** `MapReactiveUserDetailsService` defines "who the users are and what permissions they have"; `SecurityWebFilterChain` defines "which URLs require login or which roles". The two parts work together, yet solve two different problems.

### Why is `PasswordEncoder` needed?

HTTP Basic input contains the username and password sent by the client. Spring Security verifies the password using `PasswordEncoder.matches(rawPassword, encodedPassword)` according to the appropriate authentication method. Therefore, `UserDetails.password` data must match the format expected by the active encoder.

In this example:

```text
raw password from client: reader-pass
PasswordEncoder bean:     BCryptPasswordEncoder
stored password of user:  BCrypt hash, format $2a$... / $2b$...
comparison:               passwordEncoder.matches(raw, storedHash)
```

There is no need to call `matches` manually inside a controller or `SecurityWebFilterChain`. The authentication mechanism handles password verification.

A common alternative when supporting multiple hash formats is `PasswordEncoderFactories.createDelegatingPasswordEncoder()`. This encoder stores hashes in `{id}encodedPassword` format (e.g., `{bcrypt}$2a$...`). **Do not mix** unprefixed BCrypt hashes from the current example with `DelegatingPasswordEncoder` without adjusting the format; if no mapping exists for the id, you can get an error like "There is no PasswordEncoder mapped for the id null". Both models are valid when configured consistently.

## 6. Creating three WebFlux endpoints to test security

File `src/main/java/dev/example/reactiveusers/DemoController.java`:

```java
package dev.example.reactiveusers;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/profile")
    public Mono<String> profile(Principal principal) {
        return Mono.just("profile:" + principal.getName());
    }

    @GetMapping("/admin")
    public Mono<String> admin(Principal principal) {
        return Mono.just("admin:" + principal.getName());
    }
}
```

Spring WebFlux supports a `Principal` parameter in request handler methods. For `/profile` and `/admin`, the security chain requires authentication, so when the handler executes, `principal` reflects the logged-in identity.

The handler return type is `Mono<String>`, matching the reactive processing model; the example does not call `block()` or `subscribe()` inside the controller.

## 7. Running the application and self-testing via HTTP

Run from the `reactive-users-demo` directory:

```bash
gradle bootRun
```

If the project has a Gradle Wrapper, use `./gradlew bootRun` (Linux/macOS) or `gradlew.bat bootRun` (Windows). Dependencies must resolve from an appropriate repository, and the application should start successfully on port 8080.

Open another terminal and use `curl -i` to observe status lines, headers, and bodies:

```bash
# No account needed
curl -i http://localhost:8080/public

# Not logged in
curl -i http://localhost:8080/profile

# Valid sample user/password
curl -i -u reader:reader-pass http://localhost:8080/profile

# Wrong password
curl -i -u reader:wrong-pass http://localhost:8080/profile

# USER is not ADMIN
curl -i -u reader:reader-pass http://localhost:8080/admin

# ADMIN has access permission
curl -i -u admin:admin-pass http://localhost:8080/admin
```

Expected results for **HTTP status and body**:

| Request | Expected result | Why? |
| --- | --- | --- |
| `GET /public`, no credentials | `200 OK`, body `public` | `permitAll()` |
| `GET /profile`, no credentials | `401 Unauthorized` | `authenticated()` and HTTP Basic |
| `GET /profile`, `reader:reader-pass` | `200 OK`, body `profile:reader` | Valid credentials, authenticated |
| `GET /profile`, `reader:wrong-pass` | `401 Unauthorized` | Authentication failed |
| `GET /admin`, `reader:reader-pass` | `403 Forbidden` | Valid login, but missing `ROLE_ADMIN` |
| `GET /admin`, `admin:admin-pass` | `200 OK`, body `admin:admin` | Has `ROLE_ADMIN` |

Exact HTTP headers are not guaranteed verbatim because versions and configurations may change, but the statuses/bodies above should remain consistent with this demo configuration.

### Distinguishing `401` and `403`

- `401 Unauthorized` usually indicates the client has not supplied valid credentials or authentication failed. With HTTP Basic, the server can send a `WWW-Authenticate` header so the client knows how to authenticate.
- `403 Forbidden` in this example appears when the user **is already authenticated** but does not satisfy the `hasRole("ADMIN")` condition.

Do not equate "logged in successfully" with "has every permission".

### Why does the example only test GET?

The configuration still has Spring Security's default CSRF protection for applicable methods. A `POST`/`PUT`/`DELETE` with HTTP Basic may return `403` if a CSRF token is missing even when username/password are right. This is a **different concern** from looking up users with `MapReactiveUserDetailsService`. Do not arbitrarily disable CSRF for applications using cookies/sessions or browsers; decide based on the client model, authentication mechanism, and actual CSRF risk.

## 8. Automated integration testing with `WebTestClient`

File `src/test/java/dev/example/reactiveusers/SecurityIntegrationTest.java`:

```java
package dev.example.reactiveusers;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class SecurityIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointIsOpen() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void missingCredentialsAreUnauthorized() {
        client.get().uri("/profile")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerCanReadProfile() {
        client.get().uri("/profile")
                .headers(headers ->
                        headers.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("profile:reader");
    }

    @Test
    void readerCannotOpenAdminEndpoint() {
        client.get().uri("/admin")
                .headers(headers ->
                        headers.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanOpenAdminEndpoint() {
        client.get().uri("/admin")
                .headers(headers ->
                        headers.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin:admin");
    }

    @Test
    void invalidPasswordIsUnauthorized() {
        client.get().uri("/profile")
                .headers(headers ->
                        headers.setBasicAuth("reader", "wrong-pass"))
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

Run:

```bash
gradle test
```

Expected: **6 tests pass**, when the application and dependencies match the sample configuration. This is an **expected outcome based on configuration logic**, not a report of having executed Gradle in your environment. `RANDOM_PORT` lets the test start a real HTTP server on a random port; `WebTestClient` sends requests and checks responses instead of only unit-testing `PasswordEncoder` in isolation.

For internal authentication tests, you can directly test `ReactiveUserDetailsService.findByUsername("reader")` with `StepVerifier` if `reactor-test` is added. However, the integration tests above are more valuable for this lesson's objective because they jointly verify the user store, password encoding, and authorization chain.

## 9. Understanding detailed elements in the configuration

### 9.1. What does `UserDetails` contain?

A `UserDetails` object typically holds `username`, encoded `password`, `authorities`, and status flags such as enabled/account non-expired/account non-locked/credentials non-expired. The `User.withUsername` builder fits small demos because it creates a complete object with minimal code.

`.roles("USER")` is a convenience for building roles; it adds the `ROLE_` prefix. If you explicitly configure `.authorities("report:read")`, that is a literal authority and does **not** generate a `ROLE_report:read` role. The `hasRole("ADMIN")` rule looks for authority `ROLE_ADMIN` (per the default role prefix), whereas `hasAuthority("report:read")` looks for that exact authority string.

Standalone conceptual example:

```java
UserDetails sample = User.withUsername("analyst")
        .password(passwordEncoder.encode("example-pass"))
        .authorities("report:read")
        .build();
```

The snippet above is **illustrative** and requires a `passwordEncoder` variable in scope; it does not automatically add the user to `MapReactiveUserDetailsService`. To use this user, pass it into the service's constructor.

### 9.2. Is `findByUsername` a database query?

No. With this class, it looks up in memory and returns `Mono<UserDetails>` to fit the reactive API. The method can be used where Spring Security needs to look up user data, or called directly in a test/service with a clear reason.

```java
// Demo snippet in a class that already has the service:
Mono<UserDetails> userMono = userDetailsService.findByUsername("reader");
```

The statement creates a `Mono` to be consumed in Reactor style. Do not call `userMono.block()` inside a WebFlux request handler. Looking up a nonexistent user does not produce a valid identity to authenticate; let the authentication layer handle failure per the framework contract rather than treating `null` as a user.

`MapReactiveUserDetailsService` implements `ReactiveUserDetailsService` and `ReactiveUserDetailsPasswordService`; the API documentation describes constructors taking `Map`, `Collection`, or a varargs list of `UserDetails`, along with `findByUsername` and `updatePassword` methods. It is **not** an account management system with CRUD, transactions, auditing, or durable storage.

### 9.3. Should you create a custom `ReactiveAuthenticationManager`?

Not needed in this lesson. With a valid sample user store, a matching `PasswordEncoder`, and standard WebFlux Security configuration, Spring Security can set up username/password authentication. Writing a custom authentication manager is only useful when authentication logic is genuinely special, and it easily complicates an introductory lesson.

### 9.4. Do you need to call `subscribeOn(Schedulers.boundedElastic())`?

Not needed for this simple in-memory lookup. A `Mono` API does not guarantee everything is non-blocking; however, a `Map` lookup is an in-memory operation, not blocking I/O. When moving to a truly synchronous DAO, you must have a strategy to isolate blocking or prefer reactive drivers. Do not mechanically attach a scheduler to every method returning `Mono`.

## 10. Common mistakes when getting started

| Symptom | Common cause | How to check |
| --- | --- | --- |
| App starts but only the auto-generated user appears in logs | Sample user bean not component-scanned, missing `@Bean`, or wrong config active | Check package, `@Configuration`, `@EnableWebFluxSecurity`, and `ReactiveUserDetailsService` bean |
| `401` even when sending the right demo password | Hash and `PasswordEncoder` mismatch; username/password differs from bean data; app running another config | Check `encode(...)`, encoder bean, and username; do not log real passwords |
| `403` on `/admin` despite logging in | User lacks `ROLE_ADMIN` or an overly broad matcher intercepted earlier | Check `roles("ADMIN")` and `pathMatchers` order |
| Sending Basic redirects to form login | Form login still enabled or app not applying expected security chain | Check `formLogin(form -> form.disable())`, `httpBasic(...)`, and chain |
| Controller is reactive but security code uses `HttpSecurity` | Mixing MVC/Servlet config with WebFlux | Use `ServerHttpSecurity`/`SecurityWebFilterChain`; check dependencies |
| `There is no PasswordEncoder mapped for the id "null"` | Using `DelegatingPasswordEncoder` but hash lacks `{id}` prefix | Align hash format with active encoder |
| Using unencoded `password("reader-pass")` | Password in `UserDetails` is not in the format expected by provider | `password(passwordEncoder.encode("reader-pass"))` |
| Restarting the app loses user/password changes | Store lives in RAM | Move to a database or identity provider when persistence is required |
| POST with right credentials still gets `403` | CSRF protection may be active | Check CSRF mechanism instead of immediately blaming the user store |
| Using `User.withDefaultPasswordEncoder()` from demo snippets without heeding the warning | Convenient API for learning, unsuitable for production password storage design | Define an explicit `PasswordEncoder` as in the example |

### Three situations to avoid

**1. Do not store plaintext passwords in `UserDetails`.**

```java
// Incompatible with BCryptPasswordEncoder:
UserDetails wrong = User.withUsername("reader")
        .password("reader-pass")
        .roles("USER")
        .build();

// Compatible:
UserDetails right = User.withUsername("reader")
        .password(passwordEncoder.encode("reader-pass"))
        .roles("USER")
        .build();
```

Both are illustrative snippets with `passwordEncoder` in scope. Even though this is a demo with plaintext passwords in source so learners can run curl, the actual value stored inside `UserDetails` should be **the encoded value**.

**2. Do not use Servlet-style signatures in WebFlux lessons.**

```java
// Servlet stack, DO NOT use for reactive WebFlux configuration:
SecurityFilterChain filterChain(HttpSecurity http) { /* ... */ }

// WebFlux stack:
SecurityWebFilterChain filterChain(ServerHttpSecurity http) { /* ... */ }
```

The two lines above are **signature illustrations**, not complete compilable methods; the full program is in Section 5.

**3. Do not treat sample users as a real identity management system.** Demo passwords in source, fixed roles, and RAM storage all serve pedagogical purposes. Do not enable them outside controlled learning/demo environments, especially on public servers. For production environments, use credential stores and account lifecycle mechanisms that are properly protected, monitored, and governed.

## 11. When to replace `MapReactiveUserDetailsService`?

The current solution has the advantages of being **fast, low-config, zero external I/O, and easy to test**. It fits:
- Introductory Spring Security reactive tutorials.
- Local demos and integration tests with fixed accounts.
- Temporary prototypes checking matchers and URL authorization.

Switch to another mechanism when you need:
- Accounts added/edited/locked/deleted at runtime and persisted across restarts.
- Identity synchronization across multiple instances/containers.
- Secure password changes, password resets, rotation, auditing, rate limiting, or MFA.
- Integration with databases, LDAP, enterprise systems, OIDC/OAuth2, or external identity providers.

When the identity source moves to another reactive backend, you can still keep the `ReactiveUserDetailsService` contract (if username/password authentication is appropriate) while swapping its implementation. Do not turn a manually shared `Map` into a database; that approach does not magically provide persistence, transactions, or cross-node consistency.

**On operational security:** enable HTTPS when sending Basic credentials over a network; use demo passwords only in test environments. Basic sends Base64-encoded credentials, which is **not** a form of encryption protecting against eavesdropping without TLS. Log redaction, password attempt throttling, secret management, and password policies are needed when moving to real systems.

## 12. Self-check questions and exercises

**Question 1.** Where does `MapReactiveUserDetailsService` store data?  
**Answer:** in application memory, via a `Map` structure; it does not write to a database or persist across restarts.

**Question 2.** Why use `ReactiveUserDetailsService` in WebFlux?  
**Answer:** the lookup API returns `Mono<UserDetails>` to compose with the reactive pipeline, instead of returning `UserDetails` directly like the Servlet interface.

**Question 3.** What authority does `roles("ADMIN")` provide in the default configuration?  
**Answer:** `ROLE_ADMIN`. That is why `hasRole("ADMIN")` works with this user.

**Question 4.** What will `reader` receive when accessing `/admin` with the right password?  
**Answer:** `403 Forbidden`: authentication succeeded, but authorization denied access.

**Question 5.** What will an unauthenticated user receive when accessing `/profile` over HTTP Basic?  
**Answer:** `401 Unauthorized` with the example's form-login-disabled configuration.

**Question 6.** Can `MapReactiveUserDetailsService` be used to store users long-term?  
**Answer:** you should not: it has no persistence, production user administration, or ability to share data across multiple instances.

**Question 7.** Why call `passwordEncoder.encode(...)`?  
**Answer:** because Spring Security needs to verify raw passwords against encoded passwords; storing raw strings causes misconfiguration and is less secure.

### Hands-on exercises

1. Add user `auditor` with demo password `auditor-pass` and role `AUDITOR` to the `userDetailsService` bean. Add endpoint `GET /audit` and matcher `hasRole("AUDITOR")`.
2. Confirm `auditor` can access `/audit`; `reader` gets `403`; requests without credentials get `401`.
3. Write `WebTestClient` integration tests for all three cases.
4. Try replacing `hasRole("AUDITOR")` with `hasAuthority("AUDITOR")` and explain why a user with `roles("AUDITOR")` does not satisfy the new condition.
5. Change user `reader` from `.roles("USER")` to `.authorities("report:read")`, create a new endpoint requiring `hasAuthority("report:read")`, and test it.

Template for Exercise 1:

```java
UserDetails auditor = User.withUsername("auditor")
        .password(passwordEncoder.encode("auditor-pass"))
        .roles("AUDITOR")
        .build();

// Pass into constructor alongside reader/admin:
return new MapReactiveUserDetailsService(reader, admin, auditor);
```

This is a **replacement snippet inside the `userDetailsService` method**, not a standalone Java class; you must also add the endpoint and matcher to complete the exercise.

## 13. Official references

- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): how to enable and configure `@EnableWebFluxSecurity`, `MapReactiveUserDetailsService`, and `SecurityWebFilterChain`.
- [Spring Security API — MapReactiveUserDetailsService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/MapReactiveUserDetailsService.html): constructors and methods of the class.
- [Spring Security API — ReactiveUserDetailsService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/ReactiveUserDetailsService.html): reactive user lookup contract.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): `PasswordEncoder`, BCrypt, and `DelegatingPasswordEncoder`.
- [Spring Boot — Gradle Plugin](https://docs.spring.io/spring-boot/docs/3.3.5/gradle-plugin/reference/htmlsingle/): how to use the Boot plugin with Gradle.

**Takeaway:** `MapReactiveUserDetailsService` provides **sample users in RAM via a reactive API**; `PasswordEncoder` verifies passwords in the right format; `SecurityWebFilterChain` controls URLs and roles. Combining all three gives you a small, runnable, and testable Spring Security WebFlux application.