# ReactiveUserDetailsService, UserDetails, and the User Data Model

## 1. Context and Objectives

In a **Spring Security reactive** (Spring WebFlux) application, username/password authentication needs a way to look up accounts that can be composed into a Reactor processing chain. `ReactiveUserDetailsService` handles **looking up a user by username**, while `UserDetails` is the **security data model** describing the login name, hashed password, authorities, and account status. These are two separate components, though they are commonly used together with a `ReactiveAuthenticationManager`.

For example: when a client sends HTTP Basic with `reader:reader-pass`, the server needs to look up `reader`, receive a `UserDetails` containing the password hash and authorities, verify the password via `PasswordEncoder`, check the account status, and only then create an authenticated `Authentication`. **Merely finding a user does not mean login succeeded.**

You will learn how to:
1. Read the `ReactiveUserDetailsService.findByUsername(String)` contract and the three possible signals of a `Mono<UserDetails>`.
2. Understand all attributes in `UserDetails`, including authorities and the four account status flags.
3. Distinguish between the entity/domain model, the security user model, and the principal returned to the HTTP layer.
4. Declare sample users via `MapReactiveUserDetailsService`, `User.withUsername(...)`, and `PasswordEncoder`.
5. Connect the user store with `UserDetailsRepositoryReactiveAuthenticationManager` and `SecurityWebFilterChain` in WebFlux.
6. Design an adapter from a real reactive data store, handle missing users, protect password hashes, and avoid blocking I/O.
7. Verify behavior with `StepVerifier`, `WebTestClient`, and 200/401/403 cases.

**Scope:** the user model and query contract in Spring Security **reactive**, focusing on username/password. This lesson does not implement a production database, session management, JWT/OAuth2, or federated login.

## 2. What is `ReactiveUserDetailsService`?

This is an interface in the `org.springframework.security.core.userdetails` package. Conceptual signature:

```java
public interface ReactiveUserDetailsService {
    Mono<UserDetails> findByUsername(String username);
}
```

This is an **abbreviated API signature for explanation**; you do not need to create this interface file because Spring Security already provides it.

- **Input:** `String username` passed by the authentication system to look up the user.
- **Output:** `Mono<UserDetails>`, i.e., a publisher that emits at most one `UserDetails` and completes, or completes empty, or emits an error.
- **Responsibility:** look up and provide trustworthy user data for the authentication layer to check.
- **Not its responsibility:** comparing a raw password against a password hash, granting `ROLE_ADMIN` on its own, returning HTTP 401, or saving the `SecurityContext`.

`Mono` is a reactive abstraction; it can represent an in-memory lookup, an R2DBC query, or an identity system with a non-blocking API. However, **merely returning `Mono` does not prove an implementation is non-blocking**. If it calls a synchronous JDBC/SDK inside on the event loop, the application can still be blocked.

### Signals of `Mono<UserDetails>`

| Signal | Interpretation | Handling Hint |
| --- | --- | --- |
| `onNext(userDetails)` then `onComplete()` | A security record for a user was found | The manager checks the password, status, and authorities |
| `onComplete()` with no element | No user exists in an implementation that chooses to represent missing data as empty | The authentication layer must treat a not-found situation as a login failure |
| `onError(error)` | Lookup failed or the implementation chooses to report an error for a nonexistent username | Classify technical errors and not-found errors according to policy |

The API contract states that the `UserDetails` result **must not be `null`**. How a nonexistent user is represented can vary across implementations and versions: a reactive repository typically returns `Mono.empty()` when no record exists, whereas some implementations may emit `UsernameNotFoundException`. **Do not assume every `ReactiveUserDetailsService` returns empty for an unknown username.** Test the exact implementation being used.

In particular, `Mono.empty()` here (lookup found no user) **has a different meaning** from `Mono.empty()` in `ReactiveAuthenticationManager.authenticate(...)` (the manager cannot decide / may not support the token). Do not use a fake success signal to mask a nonexistent username case.

### Comparison with Servlet

| WebFlux / reactive | Spring MVC / Servlet |
| --- | --- |
| `ReactiveUserDetailsService` | `UserDetailsService` |
| `findByUsername(String)` | `loadUserByUsername(String)` |
| `Mono<UserDetails>` | `UserDetails` directly |
| `ReactiveAuthenticationManager` | `AuthenticationManager` |
| `SecurityWebFilterChain` | `SecurityFilterChain` |
| `ServerHttpSecurity` | `HttpSecurity` |

Do not mix up the two service types and the two DSLs. With WebFlux, you need `ReactiveUserDetailsService` and `ServerHttpSecurity`; Servlet examples like `InMemoryUserDetailsManager`/`HttpSecurity` are not direct drop-in replacements for reactive configuration.

## 3. `UserDetails`: The Security Structure of a User

`UserDetails` is an interface in `org.springframework.security.core.userdetails`. Key getters:

```java
public interface UserDetails extends java.io.Serializable {
    java.util.Collection<? extends GrantedAuthority> getAuthorities();
    String getPassword();
    String getUsername();

    boolean isAccountNonExpired();
    boolean isAccountNonLocked();
    boolean isCredentialsNonExpired();
    boolean isEnabled();
}
```

This is an **abbreviated signature for learning**, not a snippet to copy into another interface. `GrantedAuthority` belongs to `org.springframework.security.core`.

### Attributes and Usage

| Attribute | Meaning | Example |
| --- | --- | --- |
| `getUsername()` | Login name the authentication system uses to identify the account | `reader` |
| `getPassword()` | **Stored password hash**, not the raw password | BCrypt string such as `$2a$...` |
| `getAuthorities()` | Permissions granted from a trusted source | `reports:read`, `ROLE_ADMIN` |
| `isEnabled()` | Whether the account is enabled | `false` when disabled |
| `isAccountNonExpired()` | Whether the account is **not expired** | `false` when the account has expired |
| `isAccountNonLocked()` | Whether the account is **not locked** | `false` when locked |
| `isCredentialsNonExpired()` | Whether the credentials are **not expired** | `false` when policy forces a password change |

Note the **double-negative** naming of the three `Non...` getters. `isAccountNonLocked() == true` means **not locked**. If you use the builder `.accountLocked(true)`, then `isAccountNonLocked()` will be `false`.

These status flags provide input data to the authentication manager. Do not automatically assume every token type and every manager applies all four flags identically; for example, a `UserDetails`-based username/password manager typically performs these checks via Spring Security components.

### Creating `UserDetails` with the Official Builder

```java
UserDetails reader = User.withUsername("reader")
        .password(passwordEncoder.encode("reader-pass"))
        .authorities("reports:read")
        .build();

UserDetails admin = User.withUsername("admin")
        .password(passwordEncoder.encode("admin-pass"))
        .authorities("reports:read", "ROLE_ADMIN")
        .build();

UserDetails disabled = User.withUsername("disabled")
        .password(passwordEncoder.encode("disabled-pass"))
        .authorities("reports:read")
        .disabled(true)
        .build();
```

This snippet **illustrates usage inside a method** that already has `PasswordEncoder passwordEncoder` and imports `User` and `UserDetails`. The full program is in Section 8.

With the builder, the status flags default to active/non-expired/non-locked unless you configure them otherwise. That is convenient for demos, but a real system must map these flags from policies and account state in the database.

## 4. Authorities and Roles: Keeping the Permission Model Clear

`GrantedAuthority` can be a fine-grained permission or a role. `SimpleGrantedAuthority` holds an authority string, such as `reports:read`. Spring Security provides the builder helpers `User.withUsername(...).authorities(...)` and `.roles(...)`.

Two concepts:

- `.authorities("reports:read")`: creates an authority with the **exact string** `reports:read`. The matching rule is `hasAuthority("reports:read")`.
- `.roles("ADMIN")`: helper that creates an authority **with the default prefix**, `ROLE_ADMIN`. The matching rule is `hasRole("ADMIN")`.

Example:

```java
UserDetails editor = User.withUsername("editor")
        .password(passwordEncoder.encode("editor-pass"))
        .authorities("reports:read", "reports:write", "ROLE_EDITOR")
        .build();
```

**Be careful when chaining `.roles(...)` and `.authorities(...)` on the same builder.** Each call sets the authorities collection; if you assume the second call appends to the previous set, you can accidentally lose roles. A readable approach is to combine all authorities in a single `.authorities("reports:read", "ROLE_EDITOR")` call, or only use `.roles(...)` when all permissions are roles.

Also never assign authorities from client-supplied strings such as `X-Role: ADMIN`. Roles must come from a trusted source managed and verified by the application/server. If a system uses a role hierarchy, custom prefix, or method security, check the corresponding authorization policy rather than assuming a role automatically implies every permission.

### Authentication vs. Authorization

- **Authentication:** verifies who the credential sender is; uses the user store, password encoder, and manager.
- **Authorization:** decides whether an authenticated identity has permission to access a URL/method or data; uses authorities/roles and rules.

A user who logs in with the right password but only has `reports:read` will still get `403 Forbidden` when accessing `/admin` which requires `ROLE_ADMIN`. `403` does not mean username lookup or password verification failed.

## 5. Password Hash Is Not the Raw Password

In `UserDetails`, `getPassword()` holds the value that the manager passes into `PasswordEncoder.matches(rawPassword, storedEncodedPassword)`. In real applications, passwords must be hashed with an appropriate algorithm such as BCrypt/Argon2/scrypt/PBKDF2 according to policy and infrastructure capacity; never store cleartext or roll your own unsalted SHA-256 as a substitute for password hashing.

Example with BCrypt:

```java
PasswordEncoder encoder = new BCryptPasswordEncoder();

String hash = encoder.encode("reader-pass");
boolean valid = encoder.matches("reader-pass", hash);
boolean invalid = encoder.matches("wrong-pass", hash);

// valid == true, invalid == false.
// Different hashes across encode calls are normal behavior because of salting.
```

This is an **illustrative code snippet** requiring imports `PasswordEncoder` and `BCryptPasswordEncoder`. Do not print hash values or raw passwords to logs in a real application.

Another option is `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, where the encoded password carries an algorithm prefix such as `{bcrypt}...`. **The two storage styles have different formats**: raw BCrypt hashes from `BCryptPasswordEncoder` typically start with `$2a$...`, whereas `DelegatingPasswordEncoder` requires a prefix like `{bcrypt}` to select the encoder by id unless specially configured. Do not swap encoders without normalizing/migrating existing data.

**Data protection:** Do not put `UserDetails.getPassword()` into response DTOs, JSON logs, exceptions, traces, or audit events. Even the hash is sensitive credential data that must be protected. Never log raw passwords, tokens, or the HTTP Authorization header.

## 6. Distinguishing Domain User and Security User

A real-world application may have three model layers:

| Layer | Typical Data | Purpose |
| --- | --- | --- |
| Domain/persistence entity | `id`, `username`, `passwordHash`, `status`, `createdAt`, business profile, roles/permissions | Store and manage accounts according to business rules |
| `UserDetails` | Username, encoded password, authorities, account flags | Supply authentication data to Spring Security |
| HTTP response DTO | `id`, display name, permitted profile fields | Return public data per policy, **without the password hash** |

Do not force a database entity to `implements UserDetails`. Mixing all ORM, security, and HTTP serialization attributes into one class means a JSON change can accidentally expose the hash, or editing an entity can unintentionally grant permissions. Separating models and **mapping intentionally** makes the system easier to audit.

Java 17 domain model example:

```java
public record AccountRecord(
        long id,
        String username,
        String passwordHash,
        boolean enabled,
        java.util.Set<String> authorities,
        String displayName) {
}
```

This is an **illustrative domain-layer model**; it does not replace `UserDetails`. `displayName` is display data and should not automatically be used as the login username; `authorities` should be constructed from server-verified permission data.

A typical mapping adapter:

```java
UserDetails toUserDetails(AccountRecord account) {
    return User.withUsername(account.username())
            .password(account.passwordHash())
            .disabled(!account.enabled())
            .authorities(account.authorities().toArray(String[]::new))
            .build();
}
```

This is an **illustrative method** inside a class that imports `User` and `UserDetails`. You should also map `accountExpired`, `accountLocked`, and `credentialsExpired` if the domain has corresponding policies. Do not grant every user `ROLE_ADMIN`; authorities must come from a trusted source.

### What Should the Data Model Contain?

At a minimum, an account for username/password authentication typically needs:
- A stable internal ID, independent of a mutable username.
- A username/email normalized according to a clear policy and unique within the required authentication scope.
- A password hash in a format supported by `PasswordEncoder`, along with a migration/version mechanism when needed.
- Enabled/locked/expired status and metadata for auditing/administration.
- Permissions or a relationship to roles/permissions granted by a trusted system.
- Public profile information in a separate DTO.

In production, you also need secure password reset flows, login attempt rate limiting, account lockout, auditing, MFA as required, PII protection, lifecycle management, and data access controls. This lesson focuses on the **bridge between the domain model and authentication**, not designing a complete identity management service.

## 7. Username/Password Authentication Flow in WebFlux

Visualize HTTP Basic:

```text
GET /me
Authorization: Basic <credentials>
          |
          v
Spring Security WebFilter / Authentication converter
          |
          v
Authentication request (username + raw password)
          |
          v
ReactiveAuthenticationManager
          |
          +--> ReactiveUserDetailsService.findByUsername(username)
          |             |
          |             +--> Mono<UserDetails> (user, hash, authorities, flags)
          |
          +--> PasswordEncoder.matches(raw, storedHash)
          +--> Account status checks
          |
          +--> Success: authenticated Authentication
          |        |
          |        v
          |  SecurityContext in Reactor Context
          |        |
          |        v
          |  authorizeExchange: check authorities
          |        |
          |        v
          |    Handler / response
          |
          +--> Failure: AuthenticationException -> challenge/handler (Basic usually 401)
```

The diagram is a **conceptual flow**, not a mandatory internal class description for every version/login type. `ReactiveUserDetailsService` does not directly create a successful `Authentication`. `UserDetailsRepositoryReactiveAuthenticationManager` combines lookup and verification, while `SecurityWebFilterChain` defines how HTTP requests are protected.

A `disabled` user can **still exist** in `ReactiveUserDetailsService`, yet the authentication manager rejects the login attempt. Therefore, testing lookup and testing login are two separate test groups.

WebFlux authentication information is propagated via the **Reactor Context**; do not rely on the Servlet application's `ThreadLocal`-based `SecurityContextHolder` as a trustworthy data source when the pipeline can switch threads.

## 8. Complete Java 17+ Example with Spring Boot 3.3.5

This example uses in-memory users so the entire demo can run without a database dependency. It clarifies how `ReactiveUserDetailsService`, `UserDetails`, and the manager wire into the security chain. The project uses Spring Boot **3.3.5**, Java **17+**, and Gradle **8.5** or a compatible wrapper, with Spring Security dependencies managed by Spring Boot.

Structure:

```text
reactive-user-details-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/dev/example/userdetails/
    │   ├── ReactiveUserDetailsApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/dev/example/userdetails/
        └── UserDetailsIntegrationTests.java
```

### 8.1. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'reactive-user-details-demo'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-webflux` selects the reactive web stack. Avoid adding `spring-boot-starter-web` when you want pure WebFlux: if both are present, Spring Boot normally selects MVC/Servlet. `reactor-test` provides `StepVerifier` to verify `Mono` signals. HTTP tests use `WebTestClient` from Spring Test.

### 8.2. Startup Class

`src/main/java/dev/example/userdetails/ReactiveUserDetailsApplication.java`:

```java
package dev.example.userdetails;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveUserDetailsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveUserDetailsApplication.class, args);
    }
}
```

### 8.3. User Store, Encoder, Manager, and Security Chain Beans

`src/main/java/dev/example/userdetails/SecurityConfig.java`:

```java
package dev.example.userdetails;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
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
                .authorities("reports:read")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .authorities("reports:read", "ROLE_ADMIN")
                .build();

        UserDetails disabled = User.withUsername("disabled")
                .password(encoder.encode("disabled-pass"))
                .authorities("reports:read")
                .disabled(true)
                .build();

        return new MapReactiveUserDetailsService(reader, admin, disabled);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users,
            PasswordEncoder encoder) {
        UserDetailsRepositoryReactiveAuthenticationManager manager =
                new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager manager) {
        return http
                .authenticationManager(manager)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/reports").hasAuthority("reports:read")
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .anyExchange().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

Explanation:

1. `PasswordEncoder` is a BCrypt bean used to generate hashes in the sample data and compare passwords in the authentication manager.
2. `MapReactiveUserDetailsService` is an in-memory `ReactiveUserDetailsService` implementation. Its constructor accepts `UserDetails...`; for large lists or a real database, swap in an appropriate implementation.
3. `reader` has authority `reports:read`; `admin` has `reports:read` and `ROLE_ADMIN`; `disabled` has a user record but `isEnabled() == false`.
4. `UserDetailsRepositoryReactiveAuthenticationManager` takes `ReactiveUserDetailsService` and `PasswordEncoder` and handles username/password authentication. You do not call `findByUsername` manually from controllers.
5. `SecurityWebFilterChain` defines three access levels: `/public` is public; `/reports` requires authority `reports:read`; `/admin` requires role ADMIN. All other URLs require authentication.
6. `.httpBasic(...)` enables HTTP Basic for the demo, while `.formLogin(form -> form.disable())` disables form login so HTTP status codes can be observed clearly.
7. No permissions are ever granted from query parameters/headers; the authorities in the user store bean are server-created data.

The demo contains **cleartext passwords in source** solely for running on localhost; those passwords are hashed when building `UserDetails`. Never use sample accounts/passwords on a public service.

### 8.4. WebFlux Controller

`src/main/java/dev/example/userdetails/DemoController.java`:

```java
package dev.example.userdetails;

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

    @GetMapping("/me")
    public Mono<String> me(Principal principal) {
        return Mono.just("user=" + principal.getName());
    }

    @GetMapping("/reports")
    public Mono<String> reports() {
        return Mono.just("reports-ok");
    }

    @GetMapping("/admin")
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }
}
```

The handlers return `Mono<String>`. `/me` uses the authenticated `Principal` provided by the framework. There is no need to call `users.findByUsername(...)` in every request handler; doing so is redundant and risks accidentally exposing the password hash if `UserDetails` is returned directly over HTTP.

## 9. Running the Demo with Gradle and Testing HTTP

From the `reactive-user-details-demo` directory:

```bash
gradle bootRun
```

If the project already has a Gradle Wrapper, use `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows. The following commands assume the server has started on port 8080. Open another terminal:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u reader:reader-pass http://localhost:8080/me
curl -i -u reader:reader-pass http://localhost:8080/reports
curl -i -u reader:reader-pass http://localhost:8080/admin
curl -i -u admin:admin-pass http://localhost:8080/admin
curl -i -u disabled:disabled-pass http://localhost:8080/me
curl -i -u reader:wrong-pass http://localhost:8080/me
curl -i -u unknown:guess http://localhost:8080/me
```

**Expected** results:

| Request | Main Status / Response | Interpretation |
| --- | --- | --- |
| `GET /public`, anonymous | 200, `public` | Public endpoint |
| `GET /me`, anonymous | 401 | Unauthenticated |
| `GET /me`, reader with correct password | 200, `user=reader` | Valid username/password |
| `GET /reports`, reader with correct password | 200, `reports-ok` | Has `reports:read` |
| `GET /admin`, reader with correct password | 403 | Authenticated but lacks `ROLE_ADMIN` |
| `GET /admin`, admin with correct password | 200, `admin-ok` | Has `ROLE_ADMIN` |
| `GET /me`, disabled with correct password | 401 | User exists but is disabled |
| `GET /me`, reader with wrong password | 401 | Invalid credentials |
| `GET /me`, nonexistent username | 401 | No valid account to log into |

HTTP Basic usually responds with `WWW-Authenticate` when credentials are required. The main statuses/bodies in the table are expected for the example configuration; exact headers or error responses may vary by version. All commands here use GET so they do not trigger CSRF for state-changing requests. When testing POST/PUT/DELETE, check the CSRF policy separately.

**Important:** `401` can come from a nonexistent user, wrong password, disabled user, or locked account, so **do not** let the HTTP response distinguish the exact sensitive case, to prevent user enumeration. Keep error details returned to clients separate from internal audit information.

## 10. Testing `UserDetails`, Manager, and Security Chain

`src/test/java/dev/example/userdetails/UserDetailsIntegrationTests.java`:

```java
package dev.example.userdetails;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class UserDetailsIntegrationTests {

    @Autowired
    ReactiveUserDetailsService users;

    @Autowired
    ReactiveAuthenticationManager manager;

    @Autowired
    PasswordEncoder encoder;

    @Autowired
    WebTestClient client;

    @Test
    void readerLookupReturnsEncodedPasswordAndAuthority() {
        StepVerifier.create(users.findByUsername("reader"))
                .assertNext(user -> {
                    assertEquals("reader", user.getUsername());
                    assertTrue(encoder.matches(
                            "reader-pass", user.getPassword()));
                    assertTrue(user.getAuthorities().stream()
                            .anyMatch(a ->
                                    a.getAuthority().equals("reports:read")));
                    assertTrue(user.isEnabled());
                    assertTrue(user.isAccountNonExpired());
                    assertTrue(user.isAccountNonLocked());
                    assertTrue(user.isCredentialsNonExpired());
                })
                .verifyComplete();
    }

    @Test
    void disabledUserIsStillPresentButNotEnabled() {
        StepVerifier.create(users.findByUsername("disabled"))
                .assertNext(user -> {
                    assertEquals("disabled", user.getUsername());
                    assertFalse(user.isEnabled());
                })
                .verifyComplete();
    }

    @Test
    void managerAuthenticatesCorrectPassword() {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "reader", "reader-pass");

        assertFalse(request.isAuthenticated());

        StepVerifier.create(manager.authenticate(request))
                .assertNext(result -> {
                    assertTrue(result.isAuthenticated());
                    assertEquals("reader", result.getName());
                    assertTrue(result.getAuthorities().stream()
                            .anyMatch(a ->
                                    a.getAuthority().equals("reports:read")));
                })
                .verifyComplete();
    }

    @Test
    void wrongPasswordIsAuthenticationFailure() {
        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "reader", "wrong-pass");

        StepVerifier.create(manager.authenticate(request))
                .expectError(BadCredentialsException.class)
                .verify();
    }

    @Test
    void publicEndpointIsOpen() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void anonymousCannotReadMe() {
        client.get().uri("/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerCanReadMe() {
        client.get().uri("/me")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("user=reader");
    }

    @Test
    void readerCanReadReports() {
        client.get().uri("/reports")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("reports-ok");
    }

    @Test
    void readerCannotAccessAdmin() {
        client.get().uri("/admin")
                .headers(h -> h.setBasicAuth("reader", "reader-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanAccessAdmin() {
        client.get().uri("/admin")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-ok");
    }

    @Test
    void disabledCannotAuthenticate() {
        client.get().uri("/me")
                .headers(h -> h.setBasicAuth("disabled", "disabled-pass"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void incorrectPasswordIsRejected() {
        client.get().uri("/me")
                .headers(h -> h.setBasicAuth("reader", "wrong-pass"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void nonexistentUserIsRejected() {
        client.get().uri("/me")
                .headers(h -> h.setBasicAuth("unknown", "guess"))
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

Run:

```bash
gradle test
```

**Expected:** 13 tests pass when using the consistent files and dependencies above. This is the **expected result from the learning code**, not a claim that Gradle was run in your environment. Exact Gradle output may vary by version.

The two test groups answer two different questions:
- `StepVerifier` with `users.findByUsername(...)`: does the returned user data have the right username, password hash, authorities, and status? A disabled user can still have their record retrieved.
- HTTP `WebTestClient` and `manager.authenticate(...)`: does the system verify raw credentials, reject disabled users, and apply authorization properly?

Testing only `findByUsername` and concluding login is secure is not enough. The user store may contain valid data while the password encoder/manager/security chain is misconfigured.

## 11. From `MapReactiveUserDetailsService` to a Real Reactive Repository

`MapReactiveUserDetailsService` is useful because it stores fixed data in RAM and implements `ReactiveUserDetailsService`. For production requiring persistence, you can create an adapter that keeps the same contract while fetching data from R2DBC or another appropriate reactive API.

Design diagram:

```text
HTTP Basic / authentication request
        |
        v
UserDetailsRepositoryReactiveAuthenticationManager
        |
        v
ReactiveUserDetailsService (application adapter)
        |
        v
AccountRepository.findByUsername(username)
        |
        v
Mono<AccountRecord> (domain/persistence)
        |
        v
map(AccountRecord -> UserDetails)
        |
        v
Mono<UserDetails>
```

**The adapter code example here is a standalone illustrative structure** and must not be added alongside the Section 8 demo without replacing the `MapReactiveUserDetailsService` bean. Having two `ReactiveUserDetailsService` beans at the same time can cause injection ambiguity, and a production application must clearly choose which user source is used.

### 11.1. Model and Repository Contract

```java
package dev.example.accounts;

import java.util.Set;
import reactor.core.publisher.Mono;

record AccountRecord(
        Long id,
        String username,
        String passwordHash,
        boolean enabled,
        boolean locked,
        Set<String> authorities) {
}

interface AccountRepository {
    Mono<AccountRecord> findByUsername(String username);
}
```

This is a **model and contract declaration**, without a database implementation yet. With Spring Data R2DBC, entities and repositories will have their own annotations, queries, schema, driver, and migrations according to system design. `Mono<AccountRecord>` usually completes empty when no row is found, though you must verify the specific repository implementation.

### 11.2. Security Adapter

```java
package dev.example.accounts;

import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import reactor.core.publisher.Mono;

final class AccountReactiveUserDetailsService
        implements ReactiveUserDetailsService {

    private final AccountRepository repository;

    AccountReactiveUserDetailsService(AccountRepository repository) {
        this.repository = repository;
    }

    @Override
    public Mono<UserDetails> findByUsername(String username) {
        return repository.findByUsername(username)
                .map(this::toUserDetails);
    }

    private UserDetails toUserDetails(AccountRecord account) {
        return User.withUsername(account.username())
                .password(account.passwordHash())
                .disabled(!account.enabled())
                .accountLocked(account.locked())
                .authorities(
                        account.authorities().toArray(String[]::new))
                .build();
    }
}
```

The classes in Sections 11.1 and 11.2 compile with Reactor + Spring Security Core, but do not run as a standalone application yet because **there is no repository implementation, persistence, or bean configuration**. Key points to note:
- `findByUsername` only retrieves data and maps it to `UserDetails`. It does not compare passwords itself.
- `Mono.map(...)` only runs mapping when the repository emits an `AccountRecord`. If the repository is empty, the chain continues empty; exceptions from the repository are forwarded as `onError`.
- `passwordHash` must be stored in the format expected by the active encoder; do not call `encoder.encode(account.passwordHash())` again on read, as that causes **double hashing**.
- `locked` in the domain maps to `.accountLocked(true)`, making `isAccountNonLocked() == false`.
- `Set<String> authorities` must come from a permission table or trusted logic; never take a client-submitted list directly.
- Do not use blocking JDBC inside `repository.findByUsername(...)` if you want to keep the pipeline non-blocking.

### 11.3. Should You Call `switchIfEmpty` Yourself?

If the service returns `Mono.empty()` for a nonexistent user, the authentication manager must treat the corresponding username/password request as a failed authentication. Depending on internal contracts, the adapter may also convert it to:

```java
return repository.findByUsername(username)
        .map(this::toUserDetails)
        .switchIfEmpty(Mono.error(
                new UsernameNotFoundException("User not found")));
```

This is a **replacement snippet inside the adapter method**, requiring `UsernameNotFoundException` to be imported and ensuring the Spring Security manager's error policy aligns. Do not let public messages distinguish specifically between "wrong username" and "wrong password". Do not convert all database errors into `Mono.empty()`: outages, timeouts, and query errors must be monitored rather than disguised as missing accounts.

## 12. `ReactiveUserDetailsPasswordService` and Password Hash Upgrades

There is a separate interface `ReactiveUserDetailsPasswordService` with the method `Mono<UserDetails> updatePassword(UserDetails user, String newPassword)`. It supports **updating the encoded password in the user store**, for example when the authentication mechanism detects that a hash needs to be upgraded to a newer algorithm or cost factor.

This is **not** a method built into every `ReactiveUserDetailsService`. A class may implement both interfaces; `MapReactiveUserDetailsService` is an example of this, though in-memory changes do not automatically persist safely across restarts.

In a production repository, updating a hash requires:
- Ensuring the new password is properly **encoded** before saving, based on the encoder design and calling API.
- Updating the corresponding record and handling race conditions/concurrency if two login requests upgrade the hash simultaneously.
- Not storing raw passwords, not logging hashes, and restricting update permissions.
- Using transactions/optimistic locking if persistence and policy require consistency.
- Returning the updated `UserDetails` version via `Mono`.

Therefore, username/password management also includes **data lifecycle and migration**, not just initial user creation.

## 13. Username Normalization, Permissions, and Sensitive Data

### 13.1. Username Rules Must Be Consistent

A system may choose case-sensitive or case-insensitive usernames; no single rule fits every product. If policy dictates case-insensitive emails, normalize consistently across **registration, unique index creation, lookup, and migration**. Do not silently lowercase all existing accounts if legacy data previously allowed names differing only by case, as this can cause collisions.

In a multi-tenant system, `username` may only be unique **within a tenant**, not globally. In that case, the default service receives a `String username` without an embedded tenant id; you must design a trustworthy key or context and never rely on a client-supplied tenant query parameter to choose an identity.

### 13.2. Account Status Differs from Session Status

`enabled=false` can block new username/password logins, but revoking previously issued sessions/tokens is a **separate** problem. An already-issued JWT can remain valid until expiration if there is no revocation mechanism; changing an account flag does not guarantee automatic blocking of all bearer tokens. Design an account disable/revocation policy suited to the actual authentication mechanism.

### 13.3. Caching User Details

Caching can reduce repository load, but it can also make authorities or locked/disabled state stale. If caching `UserDetails`, define TTLs, invalidation on password/role/status changes, and permission revocation requirements. Do not carelessly use `Mono.cache()` on a single publisher shared across multiple usernames.

In multi-instance deployments, `MapReactiveUserDetailsService` only holds each process's own RAM data. Even with a password update method, changes do not automatically sync across instances or survive restarts. Use a centralized repository or dedicated identity system for real administration.

### 13.4. Do Not Return Raw `UserDetails` via REST

Wrong in intent:

```java
// RISK illustration: may serialize sensitive data.
@GetMapping("/user")
public Mono<UserDetails> user(@RequestParam String username) {
    return users.findByUsername(username);
}
```

The method above is **only a controller illustration**; the `users` field must be injected and `@RequestParam` imported. Exposing username lookup like this also creates a **user enumeration** risk and leaks password hashes/authorities/account status. Avoid this design.

Better: at the `/me` endpoint after authentication, map an authenticated principal to a publicly safe DTO containing only ID/display name or fields permitted by access policy. Never include `getPassword()`, `getCredentials()`, refresh tokens, or secrets in responses.

## 14. Common Mistakes

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| WebFlux app uses synchronous `UserDetailsService` | Confusing Servlet and reactive interfaces | Use `ReactiveUserDetailsService`, `Mono<UserDetails>` |
| User exists but login still returns 401 | Raw password does not match hash; wrong encoder; user disabled/locked/expired | Check manager, encoder, and account flags |
| `getPassword()` contains raw password | User data created directly from raw secret | Encode before storing, use a proper `PasswordEncoder` |
| Switched to `DelegatingPasswordEncoder` and got null id error | Stored hash lacks `{id}` prefix | Migrate/normalize hashes or configure a compatible encoder |
| `.roles(...)` followed by `.authorities(...)` drops roles | Builder overwrites authorities | Combine all permissions in a single call |
| `hasRole("ADMIN")` does not match | Only authority `ADMIN` exists instead of `ROLE_ADMIN` | Use `.roles("ADMIN")` or `.authorities("ROLE_ADMIN")` consistently |
| Missing user treated as success | Misusing `defaultIfEmpty(fakeAdmin)` or assigning a default principal | Treat missing user as failed authentication |
| Database timeout turned into missing user | Overly broad `onErrorResume(ex -> Mono.empty())` | Classify system errors, do not mask outages |
| `ReactiveUserDetailsService` returns `Mono` yet requests still block | Repository calls a blocking driver on the event loop | Use R2DBC/reactive API, or isolate truly blocking calls |
| 403 on admin despite valid login | Missing authority or security rule rejects access | Distinguish authentication from authorization |
| Returning `UserDetails` as JSON | Leaks hash/authorities and enables enumeration | Use a safe DTO; only allow access to appropriate data |
| Newly locked user can still make requests | Stale cache or unrevoked token/session | Check TTL, revocation, and cache invalidation |
| Two users share the same username across tenants | Missing tenant-aware identity key | Design lookup keys/unique constraints per tenant boundary |
| Calling `block()` in a WebFlux filter/handler | Blocks threads, can cause errors and reduce throughput | Compose with Reactor operators and let the framework subscribe |

### Three Distinctions to Remember

1. **Having `UserDetails`** only proves the user was found; **having a successful `Authentication`** requires checking credentials and status.
2. **Having authorities in an account record** does not grant access by itself: they must pass through a trusted model, produce an authentication result, and be checked by authorization rules.
3. **Having `Mono`** does not prove everything underneath is non-blocking: the repository implementation determines whether blocking I/O occurs.

## 15. Self-Check Questions

**Question 1.** What method does `ReactiveUserDetailsService` have and what type does it return?  
**Answer:** `findByUsername(String username)` returning `Mono<UserDetails>`.

**Question 2.** Does `findByUsername` verify the password itself?  
**Answer:** No. It looks up the user; the authentication manager verifies credentials using `PasswordEncoder` and checks account status.

**Question 3.** What does `UserDetails.getPassword()` usually contain?  
**Answer:** The stored password hash compatible with `PasswordEncoder`; not the raw password, and it must not be exposed over HTTP.

**Question 4.** What does `isAccountNonLocked() == false` mean?  
**Answer:** The account is currently locked. The getter name is a double negative.

**Question 5.** Which authority does `.roles("ADMIN")` correspond to with the default prefix?  
**Answer:** `ROLE_ADMIN`.

**Question 6.** Which rule does `.authorities("reports:read")` pair with?  
**Answer:** `hasAuthority("reports:read")`.

**Question 7.** Can the `disabled` user in the example be found by the service? Can they log in?  
**Answer:** The service can return that user's `UserDetails`, but the manager rejects authentication because `isEnabled() == false`.

**Question 8.** When a repository returns `Mono.empty()` for a nonexistent username, can login immediately be considered successful?  
**Answer:** No. The authentication layer must turn a missing user into an authentication failure per the contract.

**Question 9.** Should domain entities directly implement `UserDetails` in every application?  
**Answer:** Not necessarily; it is usually better to separate the entity/domain, security model, and response DTO with explicit mapping.

**Question 10.** Why does setting `enabled=false` not guarantee all previously issued JWTs are revoked immediately?  
**Answer:** Because token/session revocation is a separate mechanism depending on the authentication strategy and infrastructure.

**Question 11.** Why does calling JDBC from `findByUsername` and wrapping it in `Mono.just(...)` still risk blocking?  
**Answer:** The JDBC call executes blocking I/O while evaluating the argument; `Mono.just` does not make it non-blocking.

**Question 12.** Is it a bug when a BCrypt hash changes on every `encode` call for the same password?  
**Answer:** No. Salting produces a different hash, while `matches` still verifies it properly.

### Practice Exercises

1. Add `editor` to `MapReactiveUserDetailsService` with authorities `reports:read` and `reports:write`. Add an endpoint `GET /reports/write` allowing only `reports:write`; test 200 with editor and 403 with reader.
2. Add a `locked` user using the builder `.accountLocked(true)`. Verify with `StepVerifier` that lookup still returns the user with `isAccountNonLocked() == false`, then test that login returns 401.
3. Rewrite the mapper in Section 11 so the domain record also contains `accountExpired` and `credentialsExpired`, mapping them accurately to `.accountExpired(...)`/`.credentialsExpired(...)`.
4. Write a test proving `user.getPassword()` does not equal `"reader-pass"` while `encoder.matches("reader-pass", hash)` returns true.
5. Design a DTO `AccountProfileResponse(id, displayName)` and an endpoint returning only the authenticated principal's profile; exclude hashes and authorities from the JSON.
6. Review the nonexistent username and backend timeout cases. Write separate tests for both branches so infrastructure errors are never accidentally turned into missing accounts.

**Replacement template for Exercise 2** (place inside the `users(...)` bean where `encoder` is already available):

```java
UserDetails locked = User.withUsername("locked")
        .password(encoder.encode("locked-pass"))
        .authorities("reports:read")
        .accountLocked(true)
        .build();

// Add locked to the MapReactiveUserDetailsService constructor.
```

This snippet is a **fragment**, not a standalone Java program. Expected result: `locked.isAccountNonLocked() == false`; when using the username/password manager in the demo, Basic requests from `locked` must be rejected.

## 16. Official Documentation

- [Spring Security API — ReactiveUserDetailsService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/ReactiveUserDetailsService.html): `findByUsername` and the `Mono<UserDetails>` return type.
- [Spring Security API — UserDetails](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetails.html): username, password, authorities, and account status flags.
- [Spring Security API — MapReactiveUserDetailsService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/MapReactiveUserDetailsService.html): in-memory map-backed implementation.
- [Spring Security API — UserDetailsRepositoryReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html): username/password authentication backed by a reactive user store.
- [Spring Security API — ReactiveUserDetailsPasswordService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/ReactiveUserDetailsPasswordService.html): contract for updating encoded passwords.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): password encoders, hashing algorithms, and migration.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): configuring the security chain in WebFlux.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): testing `Mono` using `StepVerifier`.

**Key takeaway:** `ReactiveUserDetailsService` **looks up user data** as a `Mono<UserDetails>`; `UserDetails` provides the **password hash, authorities, and account flags**; `ReactiveAuthenticationManager` performs **credential verification** and creates the authentication result. Keep the domain model separate from the security model/response DTO and ensure data, permissions, hashes, errors, and reactive flows are handled properly at each layer.