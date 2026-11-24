# Building a WebFlux Authentication Flow with a Reactive User Store

## 1. Objectives of This Capstone Practice

In a Spring WebFlux application, authentication is more than writing a password comparison function. The login flow must coordinate **`ReactiveUserDetailsService`**, **`ReactiveAuthenticationManager`**, **`SecurityWebFilterChain`**, a reactive data source, and `SecurityContext` persistence. When the user store is an R2DBC database, the user lookup call must return `Mono<UserDetails>` without blocking the event loop thread.

This exercise builds a Spring Boot 3.x / Spring Security 6.x / Java 17+ application featuring:

1. A reactive user store backed by **Spring Data R2DBC** and an `app_user` table.
2. Form login handled by **Spring Security WebFlux**; no manual password checking in a controller.
3. Passwords stored as **BCrypt hashes**, with `ROLE_READER` or `ROLE_ADMIN` authorities loaded from server-controlled data.
4. A `GET /me` endpoint for authenticated users and `GET /admin/panel` requiring the ADMIN role.
5. WebFlux sessions via `WebSession`, with CSRF protection on form login and post-login requests.
6. `WebTestClient` tests: real login → capture session cookie → `GET /me` in a fresh request; wrong password; missing CSRF; insufficient role.
7. Clear separation of **authentication**, **authorization**, **reactive context**, **blocking password hashing**, and **reactive database I/O**.
8. A plan for migrating from the lab H2 database to PostgreSQL R2DBC, distributed session stores, TLS, rate limiting, monitoring, and load testing.

The sample uses **Spring Boot 3.5.x + Spring Security 6.5.x**, with a Gradle example pinned to a specific Boot 3.5 patch release. This is a **WebFlux/Reactive** exercise: do not mix Servlet `HttpSecurity`, `SecurityFilterChain`, `HttpSession`, or `UsernamePasswordAuthenticationFilter` across the two models.

**Remember:** reactive **does not mean** every operation is non-blocking. R2DBC provides a non-blocking database query API, whereas BCrypt/Argon2 remain CPU-intensive tasks requiring proper scheduler scheduling. Returning `Mono` from a method still blocks the event loop if inside it you call JDBC, `Thread.sleep`, or `block()`.

## 2. Brief Comparison: Spring MVC Security vs. WebFlux Security

| Aspect | Servlet / Spring MVC | Reactive / Spring WebFlux |
| --- | --- | --- |
| Web pipeline | `SecurityFilterChain`, servlet filters | `SecurityWebFilterChain`, WebFilters |
| Security builder | `HttpSecurity` | `ServerHttpSecurity` |
| Authentication manager | `AuthenticationManager` | `ReactiveAuthenticationManager` |
| User lookup | `UserDetailsService.loadUserByUsername` | `ReactiveUserDetailsService.findByUsername` |
| User return type | `UserDetails` | `Mono<UserDetails>` |
| Request context | Usually `SecurityContextHolder` / thread-local | `ReactiveSecurityContextHolder` / Reactor Context |
| HTTP request | `HttpServletRequest` | `ServerWebExchange` |
| Session | `HttpSession` | `WebSession` |
| Security session repository | `SecurityContextRepository` | `ServerSecurityContextRepository` |
| Form login security filter | `UsernamePasswordAuthenticationFilter` | `AuthenticationWebFilter` |
| HTTP testing | `MockMvc` | `WebTestClient` |
| Matching data source | JDBC/JPA (blocking) | R2DBC/Reactive repository |

If you mix `spring-boot-starter-web` (MVC) and `spring-boot-starter-webflux` without specifying the web application type, Spring Boot may default to the Servlet stack. This exercise uses **only** `spring-boot-starter-webflux`, explicitly configures `spring.main.web-application-type: reactive` in the lab, and does not declare Servlet `@EnableWebSecurity`.

These are **two distinct security stacks**, not identical classes with renamed packages. `SecurityContextHolder.getContext()` inside a reactive callback may not return the intended context; access identity via `ReactiveSecurityContextHolder.getContext()` or WebFlux principal/context support.

## 3. Architecture: Which Layers Does a Reactive User Pass Through?

```text
Browser                         Spring WebFlux / Reactor            R2DBC DB
   │                                       │                            │
   │ GET /login                            │                            │
   ├──────────────────────────────────────>│ Login page + CSRF          │
   │<──────────────────────────────────────┤                            │
   │ POST /login + username,password,CSRF  │                            │
   ├──────────────────────────────────────>│ AuthenticationWebFilter   │
   │                                       │   │                        │
   │                                       │   ▼                        │
   │                                       │ ReactiveAuthenticationMgr │
   │                                       │   │                        │
   │                                       │   ▼                        │
   │                                       │ ReactiveUserDetailsService│
   │                                       │   │ findByUsername -> Mono│
   │                                       │   ├───────────────────────>│
   │                                       │   │   password_hash,roles  │
   │                                       │   │<───────────────────────┤
   │                                       │   ▼                        │
   │                                       │ PasswordEncoder.matches   │
   │                                       │   │                        │
   │                                       │   ▼                        │
   │                                       │ authenticated Authentication
   │                                       │   │                        │
   │                                       │ save SecurityContext to WebSession
   │<──────────────────────────────────────┤ 302 + session cookie       │
   │ GET /me + same session cookie          │                            │
   ├──────────────────────────────────────>│ load context, authorize   │
   │<──────────────────────────────────────┤ 200 JSON username + role  │
```

There is no custom `POST /login` controller in this sample: **Spring Security's `formLogin`** owns that endpoint. Controllers only serve data after authentication filters and authorization permit access.

### 3.1. Critical Invariants of the Flow

- A `username/password` submitted by the browser is an **untrusted credential**.
- User records fetched from the DB are server-side data; password hashes must **never** be returned in API responses.
- Authentication succeeds only when the password hash matches, the account is enabled, and any additional policies pass.
- Roles come from controlled user records/mappings; clients cannot submit `role=ADMIN` to elevate privileges.
- For browser sessions, the second request uses the session cookie issued upon login rather than resending the password.
- For stateless resource servers, subsequent requests carry their own valid token; do not confuse that with saving `WebSession`.

## 4. Key Interfaces

### 4.1. ReactiveUserDetailsService

Core contract:

```java
Mono<UserDetails> findByUsername(String username);
```

This is an **API signature illustration**, not a standalone Java file. When a user is absent, return `Mono.empty()`. When the DB fails, return `Mono.error(...)`—**never** convert every network timeout into `Mono.empty()` and claim the user entered the wrong password. The manager is responsible for distinguishing rejected credentials from backend outages.

### 4.2. ReactiveAuthenticationManager

Contract:

```java
Mono<Authentication> authenticate(Authentication authentication);
```

For username/password, `UserDetailsRepositoryReactiveAuthenticationManager` uses `ReactiveUserDetailsService` to load `UserDetails` and `PasswordEncoder` to verify credentials. On failure, the pipeline emits the framework's authentication exception; on success, the `Authentication` carries the user's authorities.

### 4.3. SecurityWebFilterChain

Defines which paths are public, which require roles, enables form login and logout, and specifies the authentication manager. `.authorizeExchange(...)` is the WebFlux API; never use Servlet `.authorizeHttpRequests(...)`.

### 4.4. ReactiveSecurityContextHolder

Provides access to `SecurityContext` via **Reactor Context**, not as an application-wide user store. Never store `Authentication` in static fields or singleton state. When reactive publishers switch schedulers or cross async boundaries, preserve the Reactor chain so the framework manages context propagation.

## 5. Preparing the Spring Boot 3.5.x, Java 17 Project

The exercise uses in-memory H2/R2DBC for learning, **not a production identity store**. A new Gradle project contains:

```text
reactive-auth-lab/
  build.gradle
  settings.gradle
  src/main/java/com/example/reactiveauth/
    ReactiveAuthApplication.java
    AccountRow.java
    AccountRepository.java
    DatabaseUserDetailsService.java
    SecurityConfig.java
    IdentityController.java
    LabSeedConfig.java
  src/main/resources/
    application.yml
    schema.sql
  src/test/java/com/example/reactiveauth/
    ReactiveAuthFlowTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'reactive-auth-lab'
```

**`build.gradle`** — example using Boot 3.5.6 with matching dependency management; keep dependency versions aligned with the BOM when upgrading:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'

    runtimeOnly 'io.r2dbc:r2dbc-h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-data-r2dbc` provides Spring Data R2DBC/`ReactiveCrudRepository` and connection factories; `r2dbc-h2` is the test driver. Never put JDBC/JPA on the request path. When moving to PostgreSQL, use the PostgreSQL R2DBC driver and proper migration management.

You need JDK 17+ and a project Gradle wrapper. Run commands inside the project directory rather than assuming a wrapper exists just from copying text blocks.

## 6. Configuring the Reactive Database, Session, and Lab Seeding

**`src/main/resources/application.yml`**

```yaml
spring:
  main:
    web-application-type: reactive
  r2dbc:
    url: "r2dbc:h2:mem:///reactive_auth?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
    username: sa
  sql:
    init:
      mode: always

server:
  port: 8080

demo:
  seed-enabled: ${DEMO_SEED_ENABLED:false}
  seed-password: ${DEMO_SEED_PASSWORD:}
```

Explanation:

- `web-application-type: reactive` enforces the WebFlux stack for the lab; it is not a blanket cure for classpath conflicts in large systems.
- `r2dbc:h2:mem:///reactive_auth?...` is in-memory H2 over R2DBC. `DB_CLOSE_DELAY=-1` keeps the database alive when the last connection closes. For real data, use a persistent database server.
- `spring.sql.init.mode: always` tells Spring Boot to execute `schema.sql` here, including against the R2DBC `ConnectionFactory`. **Production** must use versioned migrations rather than running DDL on every restart.
- `DEMO_SEED_ENABLED` defaults to false. When true, supply a separate `DEMO_SEED_PASSWORD`; never commit real sample passwords.
- Passing demo credentials via environment variables is strictly for reproducing this lab; production uses a secret manager and omits this seed bean.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE IF NOT EXISTS app_user (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    username VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(120) NOT NULL,
    enabled BOOLEAN NOT NULL,
    role VARCHAR(30) NOT NULL
);
```

For the lab, each user has one role to keep code concise; production can separate `user_role` and permission tables, tenant bindings, account states, password history, and MFA factors. Never read roles directly from login request bodies.

## 7. Truly Reactive Entity and Repository

**`AccountRow.java`**

```java
package com.example.reactiveauth;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("app_user")
public record AccountRow(
        @Id Long id,
        String username,
        @Column("password_hash") String passwordHash,
        boolean enabled,
        String role
) {}
```

**`AccountRepository.java`**

```java
package com.example.reactiveauth;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface AccountRepository
        extends ReactiveCrudRepository<AccountRow, Long> {

    Mono<AccountRow> findByUsername(String username);

    Mono<Boolean> existsByUsername(String username);
}
```

**Meaning:**

- `findByUsername(...)` is a Spring Data R2DBC derived query based on the `username` property.
- `Mono<AccountRow>` represents 0 or 1 user; the repository does not return a list of users.
- `@Column("password_hash")` maps the SQL hash column onto `passwordHash`.
- `ReactiveCrudRepository` is not a blocking JPA interface; queries execute only when the publisher is subscribed to.
- Store hashes only, never raw passwords. Password hashes must never enter JSON responses, audit logs, tracing payloads, or metric labels.
- The UNIQUE index on username has security value: two distinct accounts must never share the same lookup key when login uses username alone. In multi-tenant systems, the policy key should be `(tenant_id, normalized_username)` rather than a global username.

### 7.1. Why Must You Never Call block() in the Service?

Mistake:

```java
// ANTI-PATTERN: never use on the WebFlux event loop.
AccountRow row = repository.findByUsername(username).block();
return Mono.just(toUserDetails(row));
```

Calling `block()` inside a reactive HTTP request stalls the event loop and triggers Reactor errors on non-blocking threads. Compose using Reactor operators such as `map`, `flatMap`, `switchIfEmpty`, and `onErrorResume` with proper semantics.

**Do not "solve" it by changing the return type to `Mono` while still calling JDBC/JPA inside.** A blocking query must be isolated onto a bounded scheduler like `boundedElastic` during legacy migrations, whereas this exercise's target solution is **R2DBC** for user lookup.

## 8. ReactiveUserDetailsService Loading Users from R2DBC

**`DatabaseUserDetailsService.java`**

```java
package com.example.reactiveauth;

import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public final class DatabaseUserDetailsService
        implements ReactiveUserDetailsService {

    private final AccountRepository accounts;

    public DatabaseUserDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    public Mono<UserDetails> findByUsername(String username) {
        return accounts.findByUsername(username)
                .map(row -> {
                    String authority = switch (row.role()) {
                        case "READER" -> "ROLE_READER";
                        case "ADMIN" -> "ROLE_ADMIN";
                        default -> throw new IllegalStateException(
                                "Unsupported stored account role");
                    };

                    return User.withUsername(row.username())
                            .password(row.passwordHash())
                            .authorities(authority)
                            .disabled(!row.enabled())
                            .build();
                });
    }
}
```

**Why is this code reactive-friendly?**

1. Using the username supplied by the login filter, it queries the repository returning `Mono<AccountRow>`.
2. `map(...)` transforms the DB record into `UserDetails` **synchronously, concisely, and with zero I/O** inside the callback.
3. Missing user → empty `Mono`, letting the authentication manager handle rejection.
4. Disabled account → `UserDetails.isEnabled()==false`; the manager rejects login before issuing an authenticated token.
5. Roles map from a server-side allowlist; invalid roles throw an exception and fail closed rather than defaulting to `ROLE_ADMIN` or `ROLE_USER`.
6. The password hash stays inside `UserDetails` for `PasswordEncoder.matches(...)`; controllers never see it.

**Understanding error signals:** `Mono.empty()` means "account not found". `Mono.error(R2dbc...Exception)` means a query/transport failure. Never write `.onErrorResume(ex -> Mono.empty())` across all exceptions: that turns DB outages into "wrong password", complicating diagnostics and causing bad retry/lockout behavior.

### 8.1. Canonical Usernames and Anti-Enumeration

- Normalize usernames using the **exact same rules** at account creation and lookup (case sensitivity, Unicode, email aliases, tenant).
- Bound input length and attempt rates before querying to prevent attackers from triggering excessive lookups.
- Never return different public messages for "username does not exist" vs. "wrong password".
- Never log raw usernames/passwords or put them into metric labels.
- For privileged/tenant accounts, add account status, password expiry, breached-password checks, and MFA/risk policies at the right security layers.
- If mapping privileges requires a second query, compose with `flatMap(row -> roleRepository...collectList().map(...))`, never a blocking DAO call inside `map`.

## 9. PasswordEncoder and ReactiveAuthenticationManager

**`SecurityConfig.java`** below wires the authentication manager and WebFlux policy:

```java
package com.example.reactiveauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
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
    ReactiveAuthenticationManager reactiveAuthenticationManager(
            ReactiveUserDetailsService userService,
            PasswordEncoder passwordEncoder) {

        var manager =
                new UserDetailsRepositoryReactiveAuthenticationManager(
                        userService);
        manager.setPasswordEncoder(passwordEncoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain webFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager authenticationManager) {

        return http
                .authenticationManager(authenticationManager)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/", "/error", "/login").permitAll()
                        .pathMatchers("/admin/**").hasRole("ADMIN")
                        .pathMatchers("/me").authenticated()
                        .anyExchange().denyAll())
                .formLogin(Customizer.withDefaults())
                .logout(Customizer.withDefaults())
                .build();
    }
}
```

**How the components relate:**

- `UserDetailsRepositoryReactiveAuthenticationManager` is the `ReactiveAuthenticationManager` implementation using `ReactiveUserDetailsService` to fetch user/password hashes.
- `setPasswordEncoder(...)` must match the stored algorithm/hash format. Never use `NoOpPasswordEncoder` or plaintext comparisons in real apps.
- `ServerHttpSecurity.authenticationManager(...)` configures the manager on the chain; form login uses it to process username/password.
- `.authorizeExchange(...)` enforces rules: root public, `/me` requires authentication, `/admin/**` requires `ROLE_ADMIN`; all other paths are denied by default.
- `.formLogin(...)` enables the default login UI and form authentication filter, rather than a custom controller.
- `.logout(...)` enables framework logout; for browser sessions with CSRF, state-changing logout requests typically require POST plus CSRF.
- Do not call `.csrf(disable)`, because this is a **web browser using session cookies**. Default WebFlux CSRF protection remains active.
- By default in Spring Security, successful form login saves `Authentication` into `WebSession` so subsequent requests reuse the same session cookie.
- `@EnableWebFluxSecurity` and `SecurityWebFilterChain` are reactive APIs; never add Servlet `@EnableWebSecurity` to the same project.

### 9.1. BCrypt Still Consumes CPU

`PasswordEncoder.matches` is CPU-intensive. Spring Security's `AbstractUserDetailsReactiveAuthenticationManager` provides scheduler support for password encoding/checking; **R2DBC makes queries non-blocking, not BCrypt**.

If checking passwords in custom code (outside the standard manager), avoid running `matches(...)` directly on Netty event-loop threads under load. Use bounded CPU scheduling, rate limiting, and load testing. Never wrap every publisher in `subscribeOn(boundedElastic())` without understanding demand—that hides blocking rather than fixing architecture.

## 10. Starting the Application and Seeding a Lab Account

**`ReactiveAuthApplication.java`**

```java
package com.example.reactiveauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuthApplication.class, args);
    }
}
```

To provide a test user, add a seed bean **active only when lab config enables it**.

**`LabSeedConfig.java`**

```java
package com.example.reactiveauth;

import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class LabSeedConfig {

    @Bean
    ApplicationRunner seedLabUser(
            AccountRepository repository,
            PasswordEncoder encoder,
            @Value("${demo.seed-enabled:false}") boolean enabled,
            @Value("${demo.seed-password:}") String password) {

        return args -> {
            if (!enabled) {
                return;
            }
            if (password == null || password.length() < 12) {
                throw new IllegalStateException(
                        "Set a separate lab password of at least 12 characters");
            }

            // Startup runner ONLY; DO NOT run inside a reactive request callback.
            boolean exists = Boolean.TRUE.equals(
                    repository.existsByUsername("alice")
                            .block(Duration.ofSeconds(5)));

            if (!exists) {
                AccountRow account = new AccountRow(
                        null,
                        "alice",
                        encoder.encode(password),
                        true,
                        "READER");

                repository.save(account)
                        .block(Duration.ofSeconds(10));
            }
        };
    }
}
```

**Distinguish carefully:** `block(Duration)` appears **only inside the lab initialization `ApplicationRunner`**, executing at startup on an operational thread—never inside `ReactiveUserDetailsService` or the HTTP event loop. It includes timeouts to avoid hanging indefinitely. Never copy this blocking seed into a login handler. In production, account provisioning belongs to a dedicated workflow with migrations/transactions/approvals rather than seeding from a global environment variable.

Concurrency note: if two instances run the same seed on first boot, both see Alice missing and both attempt to insert; the UNIQUE constraint causes one to fail. This is a **single-instance H2 demo**, not a multi-node provisioning mechanism. In real systems, use idempotent migrations/provisioning with proper transactions/constraints and race handling.

### 10.1. Running the Demo

Bash:

```bash
export DEMO_SEED_ENABLED=true
export DEMO_SEED_PASSWORD='local-lab-strong-passphrase-2026'
./gradlew bootRun
```

Windows PowerShell:

```powershell
$env:DEMO_SEED_ENABLED = "true"
$env:DEMO_SEED_PASSWORD = "local-lab-strong-passphrase-2026"
.\gradlew.bat bootRun
```

These strings are **strictly for local learning environments**. Running a public app with seeded accounts/passwords from this guide is unsafe. Generate separate passwords via a secret manager for staging/prod, and never place real values in source code, shell history, or CI logs.

With lab config active, `schema.sql` runs and `alice` is stored with a BCrypt hash. Because H2 is in-memory, restarts recreate the data per configuration; do not expect persistence across restarts. Visit `http://localhost:8080/login` to see the default login form.

## 11. Reactive Controller: Reading Authentication from Reactor Context

**`IdentityController.java`**

```java
package com.example.reactiveauth;

import java.util.List;
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class IdentityController {

    @GetMapping("/")
    public Mono<String> home() {
        return Mono.just("Home: public");
    }

    @GetMapping("/me")
    public Mono<Map<String, Object>> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(authentication -> {
                    List<String> roles =
                            authentication.getAuthorities().stream()
                                    .map(GrantedAuthority::getAuthority)
                                    .sorted()
                                    .toList();

                    return Map.<String, Object>of(
                            "username", authentication.getName(),
                            "authenticated", authentication.isAuthenticated(),
                            "authorities", roles);
                });
    }

    @GetMapping("/admin/panel")
    public Mono<String> admin() {
        return Mono.just("Admin: permitted");
    }
}
```

`GET /me` reaches the controller only after `.authenticated()` permits it. The code never reads usernames from query params or headers, never calls `block()`, and never uses MVC thread-local `SecurityContextHolder.getContext()`.

Expected response after Alice logs in:

```json
{
  "username": "alice",
  "authenticated": true,
  "authorities": ["ROLE_READER"]
}
```

This is **expected demo output**, not captured from a specific repository run. The learning endpoint returns authorities for easy inspection; production APIs should consider omitting internal privilege details and must never serialize full principals, password hashes, or tokens.

### 11.1. Reactor Context and Schedulers

`ReactiveSecurityContextHolder.getContext()` reads `SecurityContext` from the subscriber context managed by Spring Security. If code spawns detached publishers by calling `subscribe()` manually in a controller/service, or hands data off to external callbacks outside the pipeline, `SecurityContext` and error handling can detach from the request.

**Right approach:** return the publisher and let WebFlux subscribe; when invoking services, compose via `flatMap`/`map` on the same chain.

```java
// Valid snippet inside a reactive service:
return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMap(authentication ->
                accountService.findSummary(authentication.getName()));
```

This requires `accountService.findSummary(...)` to return `Mono<...>` and still enforce ownership/tenant checks inside the service. Never use principal info to skip object-level authorization.

## 12. From Browser to WebSession: What Does the Second Request Verify?

Typical WebFlux form login spans two requests:

```text
GET /login
  → HTML login form with CSRF token and session cookie when needed

POST /login
  Content-Type: application/x-www-form-urlencoded
  username=alice
  password=...
  _csrf=...
  → AuthenticationWebFilter
  → DB lookup + BCrypt check
  → success handler + SecurityContext save
  → 302 redirect + session cookie

GET /me
  Cookie: SESSION=<value received after login>
  → SecurityContext loaded from WebSession
  → 200, username=alice, ROLE_READER
```

**Never conclude "login saved state" from a POST 302 alone.** A custom authentication handler could build a valid `Authentication` during the login request yet fail to save it to `ServerSecurityContextRepository`, leaving the next GET anonymous.

In WebFlux, the session cookie is typically named `SESSION`, unlike Servlet's `JSESSIONID`. This name can change via session ID resolver or proxy configuration; verify in practice rather than hardcoding cookie names for production.

### 12.1. Logout and Session Lifecycle

After logout, invalidated sessions must never continue accessing `/me`. In multi-node deployments, use a shared reactive `WebSession` store (e.g., Spring Session reactive Redis) if sessions must survive across arbitrary pods. Sticky routing alone does not guarantee correctness when nodes drain or restart.

Session cookies need TLS, `Secure`, `HttpOnly`, `SameSite`, and proper path/domain settings; apply session ID rotation and idle timeouts per policy. Session cookie IDs are bearer secrets—never place them in URLs or logs.

## 13. Form Login and CSRF in WebFlux

Cookie-backed form login faces Cross-Site Request Forgery risk. Spring Security WebFlux **enables CSRF by default**, typically storing the expected token in `WebSessionServerCsrfTokenRepository`.

Rules to follow:

- Browser GETs the login page and receives the CSRF token in the form.
- Browser POSTs login or logout with a server-accepted token.
- Never disable `csrf()` system-wide just because a test POST returned 403.
- AJAX/SPA requests using session cookies must send the CSRF token via header or configured repository pattern.
- With `CookieServerCsrfTokenRepository`, exposing a JS-readable cookie must be deliberate and paired with XSS defenses.
- APIs using solely Bearer headers without auto-sent cookies can have a separate CSRF policy; never cite that to disable CSRF on form login.
- CSRF 403 happens **before** password checking; never diagnose HTTP 403 as a wrong password.

Negative example:

```http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=alice&password=correct
```

Without a valid CSRF token, expect a CSRF rejection even with the right password. Never put real passwords into test logs/reports; the protocol snippet is illustrative only.

## 14. WebTestClient: Testing Authorization with Mocks vs. Real Login

Spring Security Test supports WebFlux via:

- `SecurityMockServerConfigurers.springSecurity()`: attaches security filter support when binding `WebTestClient` to context.
- `SecurityMockServerConfigurers.csrf()`: injects CSRF test support for unsafe requests.
- `SecurityMockServerConfigurers.mockUser()`: injects a mock principal for **a single request** to test authorization.
- `@WithMockUser`: convenient for policy tests, though it bypasses database/BCrypt.
- `StepVerifier`: tests publishers like `Mono<AccountRow>`, `Mono<UserDetails>`, error signals, and completion.
- HTTP integration tests with cookies/sessions: prove subsequent requests restore the right principal.

**Never equate them:** a test using `mockUser("alice")` where `GET /me` returns 200 **does not prove** `ReactiveUserDetailsService` queried the DB or checked passwords. It is solely an authorization test with a mock context.

## 15. Integration Tests: Real Login Followed by a New GET with the Same Session

The file below boots the Spring Test context and binds `WebTestClient` to the WebFlux application context with Spring Security. It exercises real security web filters, form login, the reactive manager, and the demo H2/R2DBC store.

**`src/test/java/com/example/reactiveauth/ReactiveAuthFlowTest.java`**

```java
package com.example.reactiveauth;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(properties = {
        "demo.seed-enabled=true",
        "demo.seed-password=local-test-password-2026"
})
class ReactiveAuthFlowTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    private ResponseCookie loginAlice() {
        EntityExchangeResult<byte[]> result = client
                .mutateWith(csrf())
                .post()
                .uri("/login")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData(
                        "username", "alice")
                        .with("password", "local-test-password-2026"))
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectBody()
                .returnResult();

        ResponseCookie session = result.getResponseCookies()
                .getFirst("SESSION");
        assertNotNull(session, "Expected WebFlux session cookie");
        return session;
    }

    @Test
    void loginThenNewRequestMustRestoreDatabaseUser() {
        ResponseCookie session = loginAlice();

        client.get()
                .uri("/me")
                .cookie(session.getName(), session.getValue())
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.username").isEqualTo("alice")
                .jsonPath("$.authenticated").isEqualTo(true)
                .jsonPath("$.authorities[0]").isEqualTo("ROLE_READER");
    }

    @Test
    void anonymousRequestCannotBorrowPreviousLogin() {
        loginAlice();

        client.get()
                .uri("/me")
                .accept(MediaType.TEXT_HTML)
                .exchange()
                .expectStatus().is3xxRedirection();
    }

    @Test
    void authenticatedReaderCannotAccessAdminArea() {
        ResponseCookie session = loginAlice();

        client.get()
                .uri("/admin/panel")
                .cookie(session.getName(), session.getValue())
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void wrongPasswordDoesNotProvideAccess() {
        client.mutateWith(csrf())
                .post()
                .uri("/login")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData(
                        "username", "alice")
                        .with("password", "incorrect"))
                .exchange()
                .expectStatus().is3xxRedirection();

        client.get()
                .uri("/me")
                .accept(MediaType.TEXT_HTML)
                .exchange()
                .expectStatus().is3xxRedirection();
    }

    @Test
    void loginWithoutCsrfIsDenied() {
        client.post()
                .uri("/login")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData(
                        "username", "alice")
                        .with("password", "local-test-password-2026"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

**Reading the tests purposefully:**

- `.mutateWith(csrf())` is a test helper, not the production app injecting CSRF for clients automatically.
- `POST /login` performs login through Spring Security filters; the manager verifies the password hash.
- `getResponseCookies().getFirst("SESSION")` grabs the session cookie per default WebFlux lab naming. If your system configures another cookie name, update the helper to match your contract.
- The fresh `GET /me` sends **only the cookie, not username/password**. It proves context was loaded and returns the right identity/authorities.
- Requests without a cookie cannot borrow Alice's session. Two independent requests are the core assertion, not merely a 302.
- READER accessing admin gets 403; wrong password creates no authenticated session.
- Missing CSRF token → rejected despite valid password. Never disable protections just to turn tests green.

**Limits of mock `WebTestClient`:** binding to context verifies WebFlux filters/manager/repository, yet does not prove real cookie flags, TLS termination, or shared sessions across two pods. Add end-to-end HTTP tests with `RANDOM_PORT` and a real cookie jar for deployment validation.

### 15.1. If Your Project's WebTestClient Does Not Return a Cookie as Expected

Check first:

1. Is the app actually running WebFlux, or did Servlet accidentally take over?
2. Did the client call `apply(springSecurity())` when binding to context?
3. Is `POST /login` handled by `AuthenticationWebFilter` or a custom route?
4. Did login persist `SecurityContext` into `WebSession`?
5. Is the cookie named `SESSION` or customized?
6. Did a test double use `mockUser()` and accidentally bypass real login?
7. Did a redirect/saved-request or session fixation policy change the cookie after login?

Never "fix" this by slapping `mockUser` onto `GET /me`; doing so hides the exact persistence bug the test was meant to catch.

## 16. Testing ReactiveUserDetailsService in Isolation

Alongside HTTP integration tests, write unit/integration tests for lookup semantics:

- Alice in DB → `Mono<UserDetails>` emits a user with right username, enabled=true, **hashed** password, and authorities.
- Unknown username → `Mono.empty()` (no user), never a placeholder account.
- Account `enabled=false` → disabled user details, manager refuses login.
- DB timeout/connection error → reactive error signal; never converted to user-not-found.
- Non-allowlisted role → fail closed; never assign strong default authorities.
- Username with SQL-injection characters → repository parameter binding, never string-concatenated SQL.
- Concurrent lookups → zero event-loop blocking, bounded pool.

Example **snippet in a test class** with `@Autowired AccountRepository repository`:

```java
StepVerifier.create(repository.findByUsername("alice"))
        .assertNext(row -> {
            assertEquals("alice", row.username());
            assertTrue(row.passwordHash().startsWith("$2"));
            assertTrue(row.enabled());
        })
        .verifyComplete();

StepVerifier.create(repository.findByUsername("missing-user"))
        .verifyComplete();
```

Requires `reactor.test.StepVerifier` and JUnit assertion imports. This snippet **is not a standalone class**; it only illustrates verifying reactive signals. With a shared test DB, ensure seeding ran and tests do not mutate shared rows into flakiness.

### 16.1. Why Doesn't StepVerifier Replace Security Integration Tests?

`StepVerifier` verifies the repository/`Mono`. It does not execute `AuthenticationWebFilter`, `PasswordEncoder`, `SecurityContext` persistence, or authorization rules. Combine **data-store tests** with **HTTP chain tests**.

## 17. Common Pitfall: A Mono Does Not Make Inside Code Reactive

### 17.1. Wrong Example: Blocking JDBC Wrapped in Mono

```java
// ANTI-PATTERN:
public Mono<UserDetails> findByUsername(String username) {
    UserEntity entity = jpaUserRepository.findByUsername(username);
    return Mono.just(toUserDetails(entity));
}
```

Here the JDBC/JPA query executes **before `Mono` is even created**. Running on Netty's event loop, it still blocks. Transitional projects may temporarily use `Mono.fromCallable(() -> blockingLookup(username)).subscribeOn(Schedulers.boundedElastic())`, which is a **blocking-source adapter**, not true R2DBC; enforce concurrency bounds, timeouts, and a plan to eliminate blocking.

### 17.2. Wrong Example: Calling block() on Repository Results

```java
// ANTI-PATTERN:
AccountRow account = accounts.findByUsername(username).block();
return Mono.just(toDetails(account));
```

Can stall requests, exhaust threads, or make Reactor throw `block()/blockFirst()/blockLast() are blocking` on non-blocking threads.

### 17.3. Wrong Example: Calling subscribe() Manually in a Controller

```java
// ANTI-PATTERN:
accounts.findByUsername(username)
        .subscribe(account -> auditService.record(account));
return Mono.just("OK");
```

The request returns OK before the subscription finishes; errors detach and context/cancellation no longer track the request. Instead, compose and return the pipeline, e.g., `flatMap(account -> auditService.recordSafeEvent(account).thenReturn(...))` when audit logging is mandatory; for best-effort telemetry use managed queues rather than ad-hoc `subscribe()`.

### 17.4. Wrong Example: Taking Roles from the Request

```java
// ANTI-PATTERN:
return User.withUsername(username)
        .password(password)
        .roles(request.getQueryParams().getFirst("role"))
        .build();
```

Privileges must come from a trusted source, never the client. Likewise, never keep raw passwords inside `UserDetails` in storage.

## 18. How Do WebFlux Sessions Differ from Stateless JWT?

In the **browser form login** pattern:

```text
POST /login → Authentication
          → WebSessionServerSecurityContextRepository
          → SESSION cookie
GET /me + SESSION → load Authentication
```

In the **OAuth2 Resource Server JWT** pattern:

```text
GET /api/me + Authorization: Bearer <access_token>
          → AuthenticationWebFilter / Bearer support
          → ReactiveJwtDecoder verifies token
          → Authentication for this request
GET /api/me without token → 401
```

Never assume "reactive means no sessions". WebFlux supports web sessions. Never assume "logging into the web app automatically gives stateless APIs a token". Both flows manage credentials and state differently.

When serving both browser forms and bearer APIs, consider **multiple `SecurityWebFilterChain` beans** using `securityMatcher(ServerWebExchangeMatcher)` and `@Order` to separate:

- `/api/**`: bearer tokens, 401 + `WWW-Authenticate`, no HTML login redirects.
- Web pages: form/OIDC login, session cookies, and CSRF.
- Catch-all: deny or require auth per policy.

Never apply Servlet's `SessionCreationPolicy.STATELESS` to WebFlux; manage sessions and contexts with reactive APIs.

## 19. Roles, Ownership, and Business Data

`.pathMatchers("/admin/**").hasRole("ADMIN")` only checks **authority**; it does not mean the user can access every record. For an API like `GET /orders/{id}`, you may require:

```text
authenticated
AND requiredAuthority
AND order.tenantId == principal.tenantId
AND order.ownerId == principal.id
```

Enforce tenant/ownership checks with reactive queries and server-side rules. Never read `ownerId` from the URL and allow access solely based on a role when object ownership is required. In multi-tenant systems, usernames can collide across tenants; the demo's `findByUsername` repository method is insufficient for real systems. Define consistent identity keys such as verified `(tenantId, normalizedUsername)` and map principals by a stable internal ID.

Reactive method security uses `@EnableReactiveMethodSecurity` for service-layer policies; SpEL expressions/managers must remain non-blocking. WebFlux path rules never replace object-level authorization.

## 20. Production User Store: PostgreSQL R2DBC and Migrations

Moving from the H2 lab to PostgreSQL:

1. Use the BOM-managed PostgreSQL R2DBC driver and `r2dbc:postgresql://...` connection URL.
2. Configure TLS, least-privilege DB accounts, pools/timeouts, and credentials from a secret manager.
3. Run Flyway/Liquibase migrations via a dedicated step if using a JDBC migration tool; do not assume the app includes a JDBC driver merely because it uses R2DBC.
4. Create unique indexes on canonical account/tenant keys and constraints on account columns.
5. Protect hashes with adaptive algorithms/parameters, hash upgrades, and account lifecycle policies.
6. Use `ReactiveUserDetailsService` returning `Mono`; do not mix JPA into the same request path.
7. Ensure DB outages surface clear errors and fail closed rather than turning every failure into an empty account.
8. Load-test queries under concurrency; tune R2DBC pools, indexes, and password-hashing schedulers.
9. Use a shared session store across multiple pods; per-pod in-memory H2 is obviously not a shared user store.
10. Design MFA/step-up, brute-force throttling, lockouts, auditing, and recovery before production.

Example PostgreSQL config (replaces H2; **never enable both simultaneously**):

```yaml
spring:
  r2dbc:
    url: "r2dbc:postgresql://db.internal.example:5432/authdb"
    username: ${R2DBC_USERNAME}
    password: ${R2DBC_PASSWORD}
```

For auth DBs, enable TLS and driver-appropriate truststores. Never log passwords or URLs containing embedded credentials. Manage migrations so deployed schemas stay compatible with the app; rollbacks must never lose user sessions or corrupt role mappings.

## 21. Performance: Password Hashing, Event Loop, Pools, and Backpressure

Reactive keeps threads efficient during I/O waits, yet does not eliminate security computation costs:

| Bottleneck | Symptom | Remediation |
| --- | --- | --- |
| High BCrypt cost | Rising login p99 / high CPU | Tune encoder parameters, bound concurrent hashes, rate-limit |
| R2DBC pool exhaustion | Connection acquire timeouts | Tune pool, limit ingress, optimize queries/indexes |
| Blocking call in `map`/`flatMap` | Stalled Netty event loop, BlockHound alerts | Remove JDBC/`.block`; temporary `boundedElastic` adapter if forced |
| Excessive password attempts | CPU saturated even on wrong passwords | Per-account/per-IP/tenant rate limits before hashing |
| Broken DB credential rotation | Widespread login failures | Health checks/alerts, tested secret rotation |
| Slow `findByUsername` query | Requests hold connections long | Indexes, max query timeouts, fast failure/backoff |
| Session store failure | Logged-in user appears anonymous next call | Monitor `WebSession` persistence, fail closed |
| Unbounded resources | Unbounded queues/tasks | Bounded schedulers, connection pools, and budgets |
| GC/memory pressure | p95/p99 jitter | Bound payloads, concurrency, and rate/lifecycle |
| Hashing passwords on event loop | Other endpoints' throughput drops | Use standard manager and evaluate scheduler |

**Never call `passwordEncoder.encode(rawPassword)` on the WebFlux event loop in signup or password-reset endpoints when using CPU-intensive algorithms.** In custom code, schedule CPU work properly, bound concurrency, and test timeouts; the sample hashes only inside `ApplicationRunner` at lab startup.

Emit controlled metrics: login successes/failures, duration, password-verify latency, reactive DB pool acquisition, rate limits/429s, `WebSession` load/save failures, blocked event-loop counts, and app errors. Never use usernames, passwords, or tokens as tags.

## 22. Safe Error-Handling Flow

Systems should distinguish:

| Case | Client-Facing Surface | Internal Classification |
| --- | --- | --- |
| Wrong username/password | Generic login failure, e.g., redirect `/login?error` | CREDENTIAL_REJECTED |
| Nonexistent user | Same public message | UNKNOWN_SUBJECT or generic auth failure |
| Disabled/locked account | Policy-safe message avoiding enumeration | ACCOUNT_DISABLED / LOCKED |
| DB/R2DBC timeout | Temporarily unable to authenticate; never bypass | IDENTITY_STORE_UNAVAILABLE |
| Missing/invalid CSRF | 403, before password check | CSRF_REJECTED |
| Logged in, missing role | 403 | AUTHORIZATION_DENIED |
| No session on protected web route | Redirect to login | ANONYMOUS_ACCESS |
| Expired session | Must log in again | SESSION_EXPIRED |
| Invalid API JWT | 401 Bearer if Resource Server API exists | TOKEN_REJECTED |

**Notable point:** never fabricate `UserDetails` on DB errors to "let users log in offline"; that creates a backdoor. Never log `Authentication.toString()`, raw passwords, full principals, headers, or cookies. Use correlation IDs and allowlisted mechanism/error codes.

On login failures, generic responses defend against user enumeration. Internally, keep accurate observability so a DB outage is never mistaken for mass bad-password attempts.

## 23. Full Security Before Deploying WebFlux Login to Production

- **HTTPS/TLS** from client to ingress/app; protect session cookies and authentication payloads.
- **CSRF:** enabled for browser sessions and unsafe methods; test login/logout and mutating endpoints.
- **XSS:** if an attacker runs JS on the same origin, `HttpOnly` cookies limit direct cookie theft yet do not eliminate XSS damage. Enforce CSP, output encoding, and sanitization.
- **Session fixation:** use appropriate session security; verify ID/cookie rotation across login and invalidation on logout.
- **Passwords:** BCrypt/Argon2 adaptive hashes, upgrade policies, no plaintext, no credentials in logs.
- **Brute force / credential stuffing:** per-account/per-source/risk throttling before password verification, without permanently locking accounts on a few attacker probes.
- **MFA:** dedicated step-up factor verification for high-assurance resources; `formLogin()` alone is not MFA.
- **Account status:** disabled, locked, expired; policies must reflect authoritative server state.
- **Role mapping:** allowlists, object-level authorization, tenant binding. Bad DB roles must never become ADMIN.
- **Reactive safety:** zero JDBC/JPA/`.block` on the event loop. Bound concurrency and thread pools for CPU-heavy hashing.
- **Multi-node session store:** for HA, use a supported reactive Spring Session backend, testing pod failover and logout.
- **Secret management:** demo seed is lab-only; keep secrets/DB credentials in a secret manager; never expose DB repositories or hashes via endpoints.
- **Error handling:** never leak stack traces, SQL exceptions, user existence, or LDAP/DB causes publicly.
- **Auditing:** record event types and pseudonymized actors without blocking the login path on slow SIEM/HTTP calls; mandatory audits need durable handoff.
- **Testing:** `WebTestClient` integration + signed-token tests if using JWT + E2E browser/cookie/proxy + load/chaos tests.
- **Dependency upgrades:** keep Boot/WebFlux/Security/Reactor/R2DBC/H2 aligned via BOM and track security advisories/CVEs.

## 24. Common Implementation Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Copying MVC `HttpSecurity`/`SecurityFilterChain` | Fails to protect WebFlux filter chain properly | Use `ServerHttpSecurity` / `SecurityWebFilterChain` |
| `ReactiveUserDetailsService` calls JPA/JDBC directly | Blocks event loop | Use R2DBC or controlled scheduler adapter |
| Returning `Mono.just(blockingResult)` | Still blocks before publisher creation | Compose non-blocking sources / `flatMap` |
| Calling `block()` in HTTP handler | Deadlock/thread starvation or Reactor exception | Return `Mono`/`Flux`, let WebFlux subscribe |
| Calling `subscribe()` manually then returning OK | Errors/context detach from request | Return composed reactive pipeline |
| Missing matching `PasswordEncoder` | Password hashes fail verification | Configure BCrypt/Delegating properly and test |
| Storing raw passwords in DB | Credential exposure on breach | Adaptive hash + salt/migration |
| Granting roles from request body | Privilege escalation | Map server-side from verified DB/IdP |
| `onErrorResume(Mono::empty)` on DB errors | Infra outages disguised as wrong passwords | Preserve error signal, classify internally |
| Disabling CSRF because form POST returned 403 | CSRF vulnerability | Send valid token from browser/test |
| Testing only with `@WithMockUser` | Skips R2DBC/password/form login | Real `POST /login` then fresh GET with cookie |
| Asserting only POST 302 | Unverified whether context persisted across requests | `GET /me` with the same `SESSION` cookie |
| Mixing browser and Bearer API rules | APIs get HTML redirects instead of 401 | Separate policies/chains per endpoint |
| Storing `SecurityContext` in static fields | Cross-user/thread identity leaks | Reactor Context + security repositories |
| Building principals without checking account status | Disabled users still log in | Use `UserDetails` checks / standard manager |
| Using local H2 across multiple pods | Each pod has a separate user DB | Shared production DB |
| Rate-limiting only after BCrypt | CPU DoS already occurred | Distributed pre-auth throttling |
| Running H2 `schema.sql` every startup in prod | Data/schema corruption risk | Controlled migrations / CI deployment |
| Returning raw `UserDetails` in API DTOs | Leaks hashes/roles/details | Allowlisted response contracts |
| Untested store outages | May fall back to `permitAll` or mask errors | Fail closed, proper 503/UX, alerts |
| Untested cookies after logout | Old sessions retain access | E2E revocation/invalidation tests |
| Wrong matcher/order across multiple chains | Endpoints left unauthenticated or misrouted | Ordered matcher tests and catch-all |
| Leaving sample seed accounts in public deployments | Guessable credentials, uncontrolled accounts | Disable seed outside lab, formal provisioning |

## 25. Exercise Acceptance Checklist

- [ ] App uses `spring-boot-starter-webflux` without accidentally running Servlet MVC.
- [ ] `SecurityWebFilterChain` and `.authorizeExchange(...)` enforce rules properly.
- [ ] `ReactiveUserDetailsService.findByUsername` returns `Mono<UserDetails>` without blocking.
- [ ] `AccountRepository` uses R2DBC and maps username/password hash/role/enabled accurately.
- [ ] Passwords store BCrypt hashes; the manager uses a matching `PasswordEncoder`.
- [ ] Unknown usernames never fabricate accounts; DB errors are never swallowed as `Mono.empty()`.
- [ ] Form login is handled by Spring Security, with no manual password checks in controllers.
- [ ] Successful POST login populates `WebSession` with an authenticated `SecurityContext` per design.
- [ ] A **new `GET /me` request** with the session cookie returns Alice / `ROLE_READER`.
- [ ] `GET /me` **without a cookie** cannot borrow identity from the earlier request.
- [ ] Wrong passwords fail to log in; disabled accounts are rejected.
- [ ] Users lacking `ROLE_ADMIN` receive 403 at `/admin/panel`.
- [ ] Login/logout POSTs without CSRF are rejected; CSRF is never disabled for tests.
- [ ] No ad-hoc `block()`/`subscribe()` calls on the reactive request path.
- [ ] Tested with `WebTestClient` and `StepVerifier`, including negative cases.
- [ ] Cookies/TLS, rate limiting, session stores, secret management, and load tests are evaluated for production.
- [ ] R2DBC errors, hash latency, and failure categories are monitored without leaking secrets.
- [ ] Across multiple nodes, session stores and account data are shared rather than local H2.

## 26. Extension Exercises

1. Replace the single-column role with a reactive `account_role` table. Query by user ID using `flatMap(...collectList()...)` to assemble authorities, avoiding N+1 for multi-role users.
2. Add user Bob with `ROLE_ADMIN` via safe seed/migration, and verify with `WebTestClient` that `/admin/panel` returns 200 for Bob and 403 for Alice.
3. Add `locked`/`credentials_expired_at` DB columns and map them to `UserDetails` flags. Test that logins fail when locked/expired.
4. Make a custom `ReactiveUserDetailsService` return `Mono.error(...)` when the DB is unavailable; verify failures do not masquerade as account-not-found.
5. Migrate to PostgreSQL R2DBC and verify indexes, canonicalization, and multi-tenant subject uniqueness.
6. Add `ReactiveUserDetailsPasswordService` for password hash upgrades, ensuring upgrades never target the wrong user.
7. Add a rate-limiter `WebFilter` keyed by account and trusted IP; verify brute-force bursts stop invoking BCrypt once quota is exhausted.
8. Enable `@EnableReactiveMethodSecurity` on a `Mono`-returning service, enforcing both roles and object ownership/tenant checks.
9. Run two instances sharing a reactive session store, log in on A, then request B. Confirm the principal survives node switching.
10. Add a separate API JWT chain returning 401 Bearer without a token and 403 when a valid token lacks scope, without redirecting APIs to HTML login.
11. Use BlockHound in tests (with appropriate JVM config) or event-loop profiling to catch a stray JDBC/blocking call inside a request.
12. Test session timeout, logout, re-authentication, and saved-request redirects after form login completes.

## 27. Summary and Official References

- Spring WebFlux uses **`SecurityWebFilterChain`**, **`ServerHttpSecurity`**, **`ReactiveAuthenticationManager`**, **`ReactiveUserDetailsService`**, and **Reactor Context**; never guess Servlet class renames.
- Reactive user stores over R2DBC return `Mono<AccountRow>`, mapped to `Mono<UserDetails>`; invalid credentials and database outages are **two distinct outcomes**.
- The form login filter calls the manager to verify BCrypt and account status, then stores the authenticated `SecurityContext` in `WebSession`; subsequent GETs must supply the session cookie to restore identity.
- Authorization distinguishes `authenticated`, `hasRole`, and per-object business permissions. Roles come from the server, never user input.
- **Reactive does not make password hashing non-blocking**; use proper schedulers and concurrency policies, and never call `block()`/`subscribe()` inside requests.
- `WebTestClient` submitting real form logins differs from `mockUser()`. Two-request tests prove persistence and prevent state leakage across users.
- H2/seeding are strictly for learning; production requires shared DBs, migrations, rate limiting, CSRF, TLS, session stores, and properly operated auditing.

**Official Documentation:**

- [Spring Security 6.5 — WebFlux Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/index.html)
- [Spring Security 6.5 — WebFlux Form Login](https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/passwords/form-login.html)
- [Spring Security 6.5 — WebFlux Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Reactive Authentication Testing](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html)
- [Spring Security 6.5 — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security 6.5 — WebFlux CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security 6.5 Javadoc — UserDetailsRepositoryReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html)
- [Spring Boot 3.5 — R2DBC and Database Initialization](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html)
- [Spring Data R2DBC — Reactive Repositories](https://docs.spring.io/spring-data/relational/reference/r2dbc/repositories.html)
- [Spring Framework — R2DBC ConnectionFactory](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)