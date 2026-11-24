# Separating Roles, Permissions, and Profile Data in the Principal

## 1. The Problem: Do Not Turn the Principal into an "All-in-One User Profile"

In Spring Security reactive (Spring WebFlux), logging in with a username and password produces an authenticated `Authentication`. That object holds `principal` (identity), `credentials` (authentication proof, typically erased after use), and `authorities` (the `GrantedAuthority` collection). Meanwhile, an application has plenty of business data: display name, email, address, avatar, department, UI preferences, contract status, etc.

**You should not cram everything into one principal and pass it across the entire system.** A safe design separates three groups:

1. **Identity/login:** who is logging in, is the account valid, and how is the password hash verified?
2. **Roles and permissions:** which authorities has the principal been granted for Spring Security to enforce authorization?
3. **Profile data:** business data read/updated per use case, with its own ownership and access controls.

Objectives:
- Distinguish `Authentication`, `principal`, `UserDetails`, `GrantedAuthority`, role, permission, and profile.
- Know clearly where **password hashes** live, where **authorities** are returned, and where **profiles** are loaded.
- Avoid putting emails, addresses, or unnecessary sensitive data into the principal/session/JWT.
- Understand `hasRole` vs. `hasAuthority`, the `ROLE_` convention, and the authorities-overwrite bug in `User.UserBuilder`.
- Build a Java 17+ Spring Boot WebFlux app using `ReactiveUserDetailsService`, `ReactiveAuthenticationManager`, `SecurityWebFilterChain`, Reactor Context, and a separate profile service.
- Test 200/401/403, avoid leaking passwords, and distinguish functional permissions from permission to access one's own data.

## 2. Three Data Layers That Should Stay Separate

~~~text
                        HTTP Basic username/password
                                    │
                                    ▼
                    ReactiveAuthenticationManager
                                    │
                     ReactiveUserDetailsService
                                    │
                    Account / Credential store
                   ┌──────────────────────────┐
                   │ accountId, username      │
                   │ passwordHash, enabled... │
                   │ roles + permissions      │
                   └──────────────────────────┘
                                    │
                    Verify hash, account status...
                                    ▼
                    Authentication (authenticated)
                   ┌──────────────────────────┐
                   │ principal: UserDetails   │
                   │ authorities: Granted...  │
                   │ credentials: reduced/wiped│
                   └──────────────────────────┘
                                    │
                    SecurityContext / Reactor Context
                                    │
                ┌───────────────────┴───────────────────┐
                ▼                                       ▼
        AuthorizationWebFilter                     Controller/Service
        hasRole / hasAuthority                  Get verified identity
                                                        │
                                                        ▼
                                                Profile service
                                                by accountId
                                                        │
                                                        ▼
                                           Purpose-built Profile DTO
                                           (displayName, email...)
~~~

Concepts:

| Concept | Purpose | What It Holds | What It Should Not Hold |
| --- | --- | --- | --- |
| **Account record** | Login data source | Stable ID, username, password hash, account lock flags, role/permission relations | Plaintext password |
| **`UserDetails`** | Projection for username/password authentication | Username, password hash for verification, enabled/locked flags, granted authorities | Full profile, transaction history, unnecessary secrets |
| **`Authentication.principal`** | Identity representation in an authenticated request | `UserDetails`, `Jwt`, or mechanism-specific principal | Every profile field out of habit |
| **`Authentication.authorities`** | Permissions used by the framework for authorization | `GrantedAuthority` values like `ROLE_USER`, `profile:read` | Permissions copied verbatim from unverified payloads |
| **Profile entity/service** | Mutable business data | Name, contact email, avatar, language, address... | Password hash or authentication config |
| **HTTP response DTO** | Intentional public API contract | Only fields the client is allowed to see | Raw `Authentication`/`UserDetails` objects |

**Subtle point:** standard `UserDetails` *does* have `getPassword()` and normally holds the **password hash** for the manager to compare. "Minimal principal" does not mean every implementation must never hold a hash during authentication; it means **only keep data the framework truly needs without stuffing profile fields in**, and **never expose principal/`UserDetails` directly to HTTP, logs, or events**. A post-authentication `Authentication` may have erased credentials, but do not use that as an excuse to serialize the entire principal.

## 3. `Authentication`, `principal`, and `SecurityContext` Are Not the Same Object

`SecurityContext` holds the current `Authentication`. `Authentication` exposes these APIs:

~~~java
Object principal = authentication.getPrincipal();
Object credentials = authentication.getCredentials();
Collection<? extends GrantedAuthority> authorities =
    authentication.getAuthorities();
String name = authentication.getName();
boolean authenticated = authentication.isAuthenticated();
~~~

The snippet illustrates the interface and requires an authenticated `Authentication authentication` variable. Explanation:

- `principal` answers **"who?"**; for username/password it is usually `UserDetails`, though JWT/OIDC may differ.
- `credentials` is the proof (password/token) used during authentication; afterward it may be `null`. Never read and return it in JSON.
- `authorities` is the granted permission list, *not* a profile.
- `getName()` is a generic way to obtain an identifier via `java.security.Principal`, though usernames can change so do not assume it is a permanent primary key.
- `isAuthenticated()` only describes token state; it does not replace `hasRole`/`hasAuthority`. Anonymous tokens in Spring Security can have this flag true, so never guard endpoints solely on this flag.

In reactive WebFlux, the context is propagated via the subscription's **Reactor Context**:

~~~java
Mono<Authentication> currentAuthentication =
    ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()));
~~~

This is a publisher, not a synchronous getter. Inside reactive handlers, never call `.block()`, never call `subscribe()` manually, and never rely on Servlet-style ThreadLocal `SecurityContextHolder`. Continue composing with `map`/`flatMap`.

## 4. Roles, Fine-Grained Permissions, and Profiles

### 4.1. Roles: Grouping Responsibilities

A role is a functional group of permissions. For example:
- `USER`: regular user.
- `ADMIN`: administrator.
- `AUDITOR`: audit data viewer.

By Spring Security convention, `hasRole("ADMIN")` normally matches a `GrantedAuthority` with the string `"ROLE_ADMIN"`. A role is not a profile attribute: changing a display name does not make someone ADMIN, and being ADMIN does not mean seeing all other users' personal data.

### 4.2. Permissions: Specific Operations

A permission expresses an allowed operation tied to a resource/capability:

- `profile:read`: allowed to access the profile-reading API per policy.
- `profile:write`: allowed to update a profile when additional checks pass.
- `reports:read`: allowed to call the report-viewing API.
- `users:manage`: allowed to manage accounts within granted scope.

In the demo, `profile:read` does not derive automatically from `ROLE_USER`: they are **independent** authorities. Real systems may define role→permission mappings in the backend and expand them into `GrantedAuthority`, or evaluate permissions in an authorization service. This mapping must be **backend-controlled**, never taken verbatim from clients.

### 4.3. Profile: Business Data, Not Permissions

A profile contains `displayName`, `contactEmail`, `avatarUrl`, `timezone`, `locale`, etc. It can change without requiring the user to log in again. Never turn these fields into `GrantedAuthority` or read them from `Authentication.getCredentials()`.

**Architectural recommendation:** keep the principal minimal; load profile data from a separate service **when an endpoint needs it**. For instance, `GET /api/profile` must use the **verified** identity from the context to look up the matching account/profile; never accept an arbitrary `username` query parameter as the owner.

### 4.4. Roles, Permissions, and Data Ownership Are Three Different Things

`hasAuthority("profile:read")` may grant access to the **read profile** capability, yet does not necessarily allow reading **every user's** profile. If an endpoint is `GET /api/profiles/{accountId}`, you must still verify `requestedAccountId == authenticatedAccountId` or an additional authorization rule, including tenant and policy checks.

Example:

| Actor | Role/Permission | What Can They Do? |
| --- | --- | --- |
| Reader A | `ROLE_USER`, `profile:read` | Read **A's** profile after ownership check |
| Reader B | `ROLE_USER`, `profile:read` | Cannot automatically read A's profile |
| Admin | `ROLE_ADMIN`, `profile:read`, `reports:read` | Can view reports, while reading others' profiles still depends on policy |
| Guest | Unauthenticated | Can access only `permitAll` endpoints |

Functional authorization (**RBAC**) and object/data authorization (**ownership, tenant, ABAC**) complement each other. Never treat the ADMIN role as bypassing all tenant boundaries or personal data protections by default.

## 5. Converting Roles and Permissions into `GrantedAuthority`

Spring Security represents both roles and permissions with `GrantedAuthority`. The common implementation is `SimpleGrantedAuthority`:

~~~java
new SimpleGrantedAuthority("ROLE_USER");
new SimpleGrantedAuthority("profile:read");
new SimpleGrantedAuthority("reports:read");
~~~

Rules:

~~~java
.pathMatchers("/api/admin").hasRole("ADMIN")
.pathMatchers("/api/reports").hasAuthority("reports:read")
.pathMatchers("/api/profile").hasAuthority("profile:read")
~~~

- `hasRole("ADMIN")` requires `ROLE_ADMIN` under the default convention.
- `hasAuthority("reports:read")` matches the **exact** string without prepending `ROLE_`.
- `hasRole("ROLE_ADMIN")` is non-standard usage and may be rejected due to duplicate prefixes, depending on API/version.
- In projects using custom role prefixes, matching rules must align with configuration rather than assuming `ROLE_` everywhere.
- Permissions such as `SCOPE_orders.read` in a resource server may originate from JWT/OAuth2 scopes via a converter; do not equate them with business permissions like `orders:read` unless explicitly mapped.

### 5.1. A Very Common Bug with `User.UserBuilder`

`User.withUsername(...).roles(...)` is shorthand for `authorities(...)` with `ROLE_` prepended. **If you call `.roles(...)` and then call `.authorities(...)`, the builder may replace the previously set authorities rather than merging them**.

~~~java
// Do not assume both ROLE_USER and profile:read will be present:
User.withUsername("reader")
    .password(encodedPassword)
    .roles("USER")
    .authorities("profile:read")
    .build();
~~~

Reliable approach: assemble **one complete authority set**, then call `authorities(...)` exactly once:

~~~java
List<String> granted = new ArrayList<>();
granted.add("ROLE_USER");
granted.add("profile:read");

UserDetails user = User.withUsername("reader")
    .password(encodedPassword)
    .authorities(granted.toArray(String[]::new))
    .build();
~~~

In real applications, use a trusted role/permission source, manage namespaces, avoid collisions, and synchronize policy updates. Never expose an API letting clients pick their own authorities.

### 5.2. Not All Roles or Permissions Should Be Embedded Long-Term

Permission sets can change (revoked admin rights, department transfer, account closure). When roles/permissions are snapshotted into a long-lived session or JWT, authorization decisions may use **stale** data until re-login, token expiration, or refresh/invalidation occurs.

Solutions depending on your model:
- Short-lived tokens with signature/issuer/audience checks and proper refresh/revocation mechanisms.
- Session invalidation or authority refresh after permission changes.
- Per-request permission service for sensitive or freshness-critical permissions.
- Permission versioning or policy-change events for controlled cache invalidation.

**Do not** sync an entire profile into a JWT just to save the frontend an API call: payloads can leak elsewhere, go stale, and are hard to revoke. If certain claims are needed for authorization, restrict them strictly to necessary fields with a clear refresh policy.

## 6. Architecture Separating Accounts and Profiles

In a real application, you can structure tables/collections along these lines:

~~~text
accounts:
  id, username, password_hash, enabled, locked, credential_version

account_roles:
  account_id, role_code

account_permissions:
  account_id, permission_code

profiles:
  account_id, display_name, contact_email, avatar_url, locale, ...
~~~

This is an **illustrative model**, not a mandatory schema. Roles/permissions may live in separate tables or identity providers; the point is keeping responsibilities separated.

At login time:
1. The converter/filter extracts user-supplied username/password.
2. `ReactiveUserDetailsService` looks up the account and returns `UserDetails` with password hash, enabled/locked status, and system-determined authorities.
3. `ReactiveAuthenticationManager` compares passwords via `PasswordEncoder` and checks account status.
4. The authenticated `Authentication` enters the request's `SecurityContext`.
5. `SecurityWebFilterChain` uses authorities to decide whether the route is accessible.
6. Only when a handler needs profile data does the service look up the profile using the **account ID from the trusted identity**. The demo uses the verified username to resolve account ID; production should use an immutable ID plus tenant key where applicable.

This keeps email/display-name edits from affecting authentication, and authority updates from touching profile records. Conversely, changing a password never requires editing the profile table.

## 7. Complete Java 17+ Example: WebFlux Username/Password and a Separate Profile Service

The example uses **Spring Boot 3.3.13**, Spring Security WebFlux managed by Boot, Java 17+, and Gradle 8.x. This version is **to pin the learning environment and API reproducibility**, not a recommendation to run an OSS-EOL version in production. For real deployments, use a supported Spring Boot line, update dependencies, and re-run tests.

The demo defines two accounts:
- `reader` / `reader-pass`: `ROLE_USER` + `profile:read`.
- `admin` / `admin-pass`: `ROLE_ADMIN` + `profile:read` + `reports:read`.

Passwords are for local demo only. Profiles are completely separate from the principal object. All demo endpoints use GET to avoid mixing in CSRF policy details for state-changing operations.

### 7.1. Directory Structure

~~~text
reactive-principal-separation/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── PrincipalSeparationApplication.java
    │   ├── DemoAccountStore.java
    │   ├── ProfileView.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/demo/
        └── SeparationTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'reactive-principal-separation'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Boot's dependency management selects compatible Spring Security/Reactor versions. Do not mix Spring MVC's `HttpSecurity` with Spring WebFlux's `ServerHttpSecurity` in this example.

### 7.2. Entry Point Class

`src/main/java/demo/PrincipalSeparationApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PrincipalSeparationApplication {

    public static void main(String[] args) {
        SpringApplication.run(PrincipalSeparationApplication.class, args);
    }
}
~~~

### 7.3. Profile DTO: No Passwords or Authorities

`src/main/java/demo/ProfileView.java`:

~~~java
package demo;

public record ProfileView(
    String displayName,
    String contactEmail
) {}
~~~

This is a purpose-built DTO for the `/api/profile` API, not a principal or authentication token. Email is personal data, returned only to **its owner** per the demo's access rules. Production systems need consent management, partial masking, or role- and data-protection-based filtering.

### 7.4. Demo Store Separating Accounts from Profiles

`src/main/java/demo/DemoAccountStore.java`:

~~~java
package demo;

import java.util.Map;
import java.util.Set;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
class DemoAccountStore {

    // Data for authN/authZ, without displayName/email.
    record AccountRow(
        String id,
        String username,
        String passwordHash,
        Set<String> roles,
        Set<String> permissions
    ) {}

    private final Map<String, AccountRow> accountsByUsername;
    private final Map<String, ProfileView> profilesByAccountId;

    DemoAccountStore(PasswordEncoder encoder) {
        AccountRow reader = new AccountRow(
            "u-100",
            "reader",
            encoder.encode("reader-pass"),
            Set.of("USER"),
            Set.of("profile:read")
        );

        AccountRow admin = new AccountRow(
            "u-200",
            "admin",
            encoder.encode("admin-pass"),
            Set.of("ADMIN"),
            Set.of("profile:read", "reports:read")
        );

        this.accountsByUsername = Map.of(
            reader.username(), reader,
            admin.username(), admin
        );

        // Profiles stored separately by stable account ID.
        this.profilesByAccountId = Map.of(
            "u-100",
            new ProfileView("Reader", "reader@example.invalid"),
            "u-200",
            new ProfileView("Administrator", "admin@example.invalid")
        );
    }

    Mono<AccountRow> findAccount(String username) {
        return Mono.justOrEmpty(accountsByUsername.get(username));
    }

    Mono<ProfileView> profileForAuthenticatedUsername(String username) {
        return findAccount(username)
            .flatMap(account ->
                Mono.justOrEmpty(profilesByAccountId.get(account.id())));
    }
}
~~~

Each dataset has clear responsibilities:
- `AccountRow.id` is a stable internal identifier; the profile relationship keys off this ID.
- `AccountRow.passwordHash` is used to verify passwords during authentication, not display data.
- `roles` and `permissions` are separated in domain data and only combined into `GrantedAuthority` when building `UserDetails`.
- `ProfileView` conceptually lives in a separate store; the demo keeps both in one component for brevity, whereas real apps should have separate **AccountRepository** and **ProfileRepository/Service** structures.
- `Mono.justOrEmpty(...)` executes immediately against the in-memory `Map`. When switching to R2DBC/a reactive driver, return the publisher directly from the repository. **Never** put a blocking JDBC call inside `Mono.just(...)` and invoke it on the event loop.

The `example.invalid` email domain is a valid dummy address for illustration; no real emails are sent.

### 7.5. Configuring `ReactiveUserDetailsService` and WebFlux Security

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService userDetailsService(DemoAccountStore store) {
        return username -> store.findAccount(username)
            .map(account -> {
                List<String> authorities = new ArrayList<>();

                // ROLE_ is the default prefix for hasRole(...).
                account.roles().stream()
                    .map(role -> "ROLE_" + role)
                    .forEach(authorities::add);

                // Permissions keep their exact string, without the ROLE_ prefix.
                authorities.addAll(account.permissions());

                return User.withUsername(account.username())
                    .password(account.passwordHash())
                    // Call authorities once with the complete set.
                    .authorities(authorities.toArray(String[]::new))
                    .build();
            });
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
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager manager) {

        return http
            .authenticationManager(manager)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/reports")
                    .hasAuthority("reports:read")
                .pathMatchers("/api/profile")
                    .hasAuthority("profile:read")
                .pathMatchers("/api/me").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
~~~

**Core mechanics:**
1. `ReactiveUserDetailsService` is the interface converting a username into `Mono<UserDetails>`. It does not return a profile; it returns only the authentication/authority data needed.
2. `passwordHash` goes into `UserDetails` so the manager can use `PasswordEncoder.matches(...)` to verify client-supplied passwords. Passwords are generated with BCrypt in the demo, **not** compared as plaintext strings.
3. The authority set includes both roles (with `ROLE_` prepended) and permissions (exact strings), avoiding chained `roles(...).authorities(...)` calls.
4. `UserDetailsRepositoryReactiveAuthenticationManager` uses `ReactiveUserDetailsService` and the encoder to authenticate Basic credentials. A successful `Authentication` token is placed into the request's security context by the framework.
5. `SecurityWebFilterChain` specifies HTTP access rules. `hasRole` and `hasAuthority` evaluate the authority set without touching profile data.
6. `httpBasic(...)` accepts credentials in the Authorization header; `formLogin(...disable())` ensures unauthenticated API clients see 401 instead of a redirect in the demo.
7. `anyExchange().denyAll()` avoids implicitly allowing unknown endpoints. In production, open required endpoints (health, docs, etc.) with specific rules before this catch-all rule.
8. `@EnableWebFluxSecurity` clarifies reactive configuration. Spring Boot with the Security starter normally provides matching auto-configuration; the annotation does not grant any permissions itself.

**Known limitation:** The two sample accounts lack disabled/locked states. Real `UserDetails` also represents enabled, accountNonLocked, credentialsNonExpired, and accountNonExpired flags. Reflect these from your account record rather than checking only the password.

### 7.6. Controller Sees Only Identity and Purpose-Built DTOs

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import java.util.List;
import java.util.Objects;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
class DemoController {

    public record IdentityView(
        String username,
        List<String> authorities
    ) {}

    private final DemoAccountStore store;

    DemoController(DemoAccountStore store) {
        this.store = store;
    }

    @GetMapping("/public")
    Mono<String> publicPage() {
        return Mono.just("public");
    }

    // Identity + permissions DTO; NEVER return raw Authentication/UserDetails.
    @GetMapping("/api/me")
    Mono<IdentityView> identity() {
        return currentAuthentication().map(auth -> {
            List<String> granted = auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .filter(Objects::nonNull)
                .sorted()
                .toList();

            return new IdentityView(auth.getName(), granted);
        });
    }

    // Profile is loaded only after authorization passes
    // and by AUTHENTICATED username, never by a client-supplied ID.
    @GetMapping("/api/profile")
    Mono<ProfileView> myProfile() {
        return currentAuthentication()
            .flatMap(auth ->
                store.profileForAuthenticatedUsername(auth.getName()))
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.NOT_FOUND)));
    }

    @GetMapping("/api/admin")
    Mono<String> adminOnly() {
        return Mono.just("admin");
    }

    @GetMapping("/api/reports")
    Mono<String> reportsOnly() {
        return Mono.just("reports");
    }

    private Mono<Authentication> currentAuthentication() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(context ->
                Mono.justOrEmpty(context.getAuthentication()))
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.UNAUTHORIZED)));
    }
}
~~~

**Important separation points:**
- `/api/me` returns **IdentityView** containing the login name and authority list for demonstration. Never return raw passwords, password hashes, credentials, details, or full `UserDetails`.
- `/api/profile` is only accessible with `profile:read`. The controller gets the username from the framework-verified `Authentication`, and the store resolves the **internal account ID** before fetching the matching profile.
- `ProfileView` is never stuffed into the principal. When profile details change, the endpoint can read updated records per cache policy.
- `/api/admin` requires role ADMIN; `/api/reports` requires permission reports:read. The two conditions do not imply each other.
- `ReactiveSecurityContextHolder.getContext()` returns `Mono<SecurityContext>` on Reactor Context. Never call `block()` in a WebFlux handler; let Spring Security manage subscription.
- `switchIfEmpty` in the controller defends against missing context/profile; most unauthenticated requests are rejected earlier by HTTP security.

**Product boundary:** In the example, `/api/me` returns authorities for learning clarity. Real apps do not necessarily expose all internal permissions; a UI-facing DTO should contain only genuinely needed capability flags, and the frontend is never the final authorization authority.

## 8. Testing over HTTP

Run inside `reactive-principal-separation`:

~~~bash
gradle bootRun
~~~

If the project has a Gradle Wrapper, use `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows. JDK 17+, Gradle 8.x, and network access to download dependencies are prerequisites.

With the server running on the default `localhost:8080`, using bash/Git Bash:

~~~bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/public
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/me
curl -s -u reader:reader-pass http://localhost:8080/api/me
curl -s -u reader:reader-pass http://localhost:8080/api/profile
curl -s -u reader:reader-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/admin
curl -s -u reader:reader-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/reports
curl -s -u admin:admin-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/admin
curl -s -u admin:admin-pass -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/reports
curl -s -u reader:wrong -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/me
~~~

HTTP status codes for commands **1, 2, 5, 6, 7, 8, 9** in exact order:

~~~text
200
401
403
403
200
200
401
~~~

Command 3 returns `IdentityView` data like this (JSON key order may vary):

~~~json
{
  "username": "reader",
  "authorities": [
    "ROLE_USER",
    "profile:read"
  ]
}
~~~

Command 4 returns **separate profile** data like:

~~~json
{
  "displayName": "Reader",
  "contactEmail": "reader@example.invalid"
}
~~~

Verification points:
- Profile data does not appear in `IdentityView`.
- Passwords, password hashes, and raw HTTP Basic credentials appear in neither response.
- `reader` is logged in yet lacks role ADMIN and permission reports:read, so they get **403** on both sensitive endpoints.
- Wrong password leads to **401**.
- Admin has `ROLE_ADMIN` and `reports:read`, so both corresponding URLs return 200.

On PowerShell, use `curl.exe` if `curl` is an alias. Some Windows shells require replacing `/dev/null` with `NUL`. For HTTP Basic, use TLS/HTTPS outside local environments; username/password travel in the Authorization header, **not** secretly encrypted by Basic.

## 9. Automated Tests: Roles, Permissions, and Profiles Must Stay Separate

`src/test/java/demo/SeparationTests.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class SeparationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicIsOpenButIdentityNeedsAuthentication() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk();

        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void readerIdentityContainsAuthoritiesButNoProfileOrPassword() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("reader", "reader-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("reader")
            .jsonPath("$.authorities[0]").isEqualTo("ROLE_USER")
            .jsonPath("$.authorities[1]").isEqualTo("profile:read")
            .jsonPath("$.contactEmail").doesNotExist()
            .jsonPath("$.password").doesNotExist()
            .jsonPath("$.passwordHash").doesNotExist();
    }

    @Test
    void readerGetsOnlyTheirOwnProfile() {
        client.get().uri("/api/profile")
            .headers(h -> h.setBasicAuth("reader", "reader-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.displayName").isEqualTo("Reader")
            .jsonPath("$.contactEmail")
                .isEqualTo("reader@example.invalid")
            .jsonPath("$.password").doesNotExist()
            .jsonPath("$.passwordHash").doesNotExist();
    }

    @Test
    void ordinaryUserHasNeitherAdminRoleNorReportPermission() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("reader", "reader-pass"))
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/api/reports")
            .headers(h -> h.setBasicAuth("reader", "reader-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminHasRoleAndExplicitReportPermission() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("admin", "admin-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin");

        client.get().uri("/api/reports")
            .headers(h -> h.setBasicAuth("admin", "admin-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reports");
    }

    @Test
    void incorrectPasswordDoesNotProduceTrustedPrincipal() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("reader", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Run:

~~~bash
gradle test
~~~

Or use the appropriate wrapper. Expect six tests to pass; `gradle test` exits with code 0. Gradle logs, timings, and summary lines depend on the environment, so exact verbatim stdout is not predetermined.

The tests catch real-world vulnerabilities:
1. **Unauthenticated requests** cannot reach `/api/me` (401).
2. **Principal/Identity DTO** does not leak hashes, passwords, or email.
3. **Profile** is loaded separately using reader's verified identity.
4. **Roles** and **permissions** are not conflated.
5. **Regular users** cannot access admin or reports endpoints (403).
6. **Wrong passwords** never create a trusted identity (401).

These tests do not cover full ownership checks on URLs taking arbitrary account IDs, because the demo intentionally has no such URL. If you add `/api/profiles/{id}`, you must write a test where user A tries to read profile B and assert policy rejects it.

## 10. When You Need a Custom Principal Carrying an Immutable accountId

Section 7's example uses `org.springframework.security.core.userdetails.User`; `getName()` returns the username. That works for a demo, yet usernames can change, making them an unstable key for profile lookups.

In production applications, you can create a **custom minimal principal** containing only the stable ID, username, required tenant ID, and minimal account metadata. **Illustrative model example, not a direct replacement for the runnable files above**:

~~~java
public record ActorIdentity(
    String accountId,
    String username,
    String tenantId
) {}
~~~

After the authentication manager verifies the password/token, it can build a trusted `Authentication` with an `ActorIdentity` principal and backend-determined authorities. Services then query profiles by `accountId` and check `tenantId` at the data access boundary:

~~~java
Authentication trusted =
    UsernamePasswordAuthenticationToken.authenticated(
        new ActorIdentity("u-100", "reader", "tenant-1"),
        null, // Do not keep raw password in the authenticated token.
        grantedAuthoritiesFromServer
    );
~~~

**Boundary explanation:** The snippet illustrates how the **manager builds authentication after verifying proof**, and must never call `authenticated(...)` directly on unverified request data. `grantedAuthoritiesFromServer` is a backend-determined `Collection<? extends GrantedAuthority>`, not an existing variable in the demo project.

In a custom `UserDetails` used for username/password, you still need `UserDetails` interface methods like `getUsername()`, `getPassword()`, `getAuthorities()`, and account status flags. `ActorIdentity` is simply a minimal principal object for the **authentication result**, not a full replacement for `UserDetails`. Do not confuse this illustrative model with Spring's `User` class in the runnable project.

### 10.1. Multi-Tenancy Cannot Simply Stick tenantId on the Principal and Trust It Blindly

If a request hits `/tenants/{tenantId}/data`, you must verify the authenticated identity belongs to that tenant and policy permits the operation. Tenant IDs in JWTs must also come from **verified** issuers/claims, never trusted by default from a client-supplied `X-Tenant` header.

An `ADMIN` role in tenant A does not imply admin permissions in tenant B. A concrete design may bind grants per tenant or use a scoped authorization service rather than one global role crossing all boundaries.

### 10.2. Distinguishing "Display Identity" from "Authorization Identity"

`displayName`, email, and avatar are display data. `accountId` is the stable key for business relationships. `getName()` on an authentication may be a username or subject depending on the mechanism. Use keys solely from a **verified identity provider/account store**, never a display name as a security key.

## 11. Updating Roles/Permissions and Profiles While Logged In

The two update types have different lifecycles:

**Profile changes** (`displayName`, contact email):
- The service updates the profile record after checking ownership/permission.
- The app reads the updated profile on the next request (subject to caching).
- No need to replace the whole `Authentication` just because display name changed; the principal did not hold the profile anyway.

**Role/permission changes** (revoking ADMIN, granting reports:read):
- Update the backend's trusted authority source.
- Check whether previously issued authentications/sessions/JWTs hold an **authorities snapshot**.
- Design refresh, token TTL, revocation, or live permission checks suited to sensitivity.
- Test that once a permission is revoked, the user loses resource access within the policy's allowed window.

**Password changes or account locking**:
- Rehash the password with the configured algorithm; never store plaintext.
- Consider invalidating active sessions/tokens when policy requires.
- Never write the new password into the profile or return password hashes to clients.

Keep these three lifecycles separate so a harmless profile edit never accidentally injects stale permissions into active tokens, and permission revocations do not wait on profile updates to take effect.

## 12. Why Should You Never Serialize `UserDetails`/`Authentication` to JSON?

Developers sometimes write:

~~~java
@GetMapping("/me")
Mono<Authentication> me() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication);
}
~~~

**Do not use this as a real endpoint.** The authentication object can contain mechanism-specific principals, authorities, details, and in some phases or implementations even credentials or password-related fields. The JSON shape changes across library versions, easily leaks unintended fields, couples the API to Spring Security internals, and exposes personal data.

Instead, use an **allowlisted DTO** you control: only permitted display/identity names, client-needed capabilities, or purpose-built profile views. Do not rely on scattered `@JsonIgnore` annotations on framework objects as your sole defense; better yet, never cross the HTTP boundary with security objects.

The same applies to logging and telemetry:
- Never log `getCredentials()`, raw tokens, or Authorization headers.
- Never log raw `principal.toString()` without knowing every field in the implementation.
- Log trace IDs, error codes, internal IDs pseudonymized per policy, and controlled permission names when needed for observability.
- Define clear log retention, log read access, and permitted data policies.

## 13. Common Mistakes, Detection, and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Putting `displayName`, email, address into `UserDetails` so every service can read them easily | PII leaks, stale principals/sessions, coupling between auth and business logic | Keep principal minimal; load profiles via a dedicated service |
| Using one DTO containing both `passwordHash` and profile and returning it to clients | Leaks authentication credentials | Use separate response DTOs; never expose entities |
| Calling `.roles("USER").authorities("profile:read")` assuming they merge | Role may be overwritten → unexpected 403 | Combine roles + permissions and call `authorities(...)` once |
| Setting `ADMIN` instead of `ROLE_ADMIN` while using `hasRole("ADMIN")` | Fails to match authority under default prefix | Normalize mappings / verify prefix configuration |
| Assuming `hasRole("ADMIN")` allows all operations across all tenants | Data scope breach | Check owner, tenant, resource, and fine-grained permissions |
| Taking profile `accountId` from a query param without ownership checks | IDOR/BOLA | Use the authenticated ID or enforce explicit permissions on requested ID |
| Accepting roles from a JSON request and creating an authenticated `Authentication` | Privilege escalation | Manager assigns authorities only from trusted sources after verification |
| Using ThreadLocal `SecurityContextHolder` like Servlet in WebFlux | Wrong/empty when threads switch | Use `ReactiveSecurityContextHolder` inside Reactor pipelines |
| Calling `block()` in reactive handlers/repositories | Blocks event loop, deadlock/performance risk | Use `Mono`/`Flux` and async repositories |
| Keeping stale authorities forever in sessions/JWTs | Role revocations take too long to apply | Token TTL, refresh, revocation, or access-time permission checks |
| Creating global permissions without namespaces | Name collisions/confusion across modules | Define namespaces/naming conventions and policy reviews |
| Treating `isAuthenticated()` as the entire access condition | Can misclassify anonymous/roles | Use Spring Security authorization and method security |
| Using `getName()` as an immutable key by default | Username changes break lookups | Use a stable `accountId` when business logic requires |
| Treating "profile readable" as "allowed to view every profile" | Personal data breach | Enforce ownership/tenant/object policies |
| Using HTTP Basic over plain HTTP on the Internet | Credentials exposed on the wire | HTTPS, secure transport, appropriate auth mechanisms |

### 13.1. Why Are 401 and 403 Different?

With the demo HTTP Basic configuration:
- Missing credentials or wrong password → **401 Unauthorized**: not validly authenticated.
- Reader with right password but lacking `ROLE_ADMIN` → **403 Forbidden**: authenticated, lacks permission.
- Reader accessing `/api/profile` → **200 OK**: has `profile:read` and the service loads reader's own profile.
- No API may accept passwords/hashes just to display a profile.

Status codes can be affected by exception handling, login mechanisms, and other filters; that is why testing against the real HTTP contract matters.

### 13.2. Does `@EnableReactiveMethodSecurity` Replace HTTP Rules?

No. Reactive method security such as `@PreAuthorize("hasAuthority('reports:read')")` protects method-level logic when enabled with `@EnableReactiveMethodSecurity` and invoked through appropriate Spring proxies. It **complements** `SecurityWebFilterChain` rather than replacing domain ownership/tenant logic. If a business service handles highly sensitive data, place checks close to the resource and test at both HTTP and service layers.

## 14. Practice Exercises

1. **How do `principal` and `GrantedAuthority` differ?** Principal describes identity; GrantedAuthority describes permissions granted to the authentication.
2. **Does `ProfileView.contactEmail` need to be inside `UserDetails` to log in?** No. Only username/password hash and account status flags relate directly; contact email should be loaded when needed.
3. **Which string does `hasRole("ADMIN")` check under the default convention?** `ROLE_ADMIN`.
4. **Does `hasAuthority("reports:read")` automatically prepend `ROLE_`?** No, it checks the exact authority name.
5. **If you write `.roles("USER").authorities("profile:read")`, is `ROLE_USER` guaranteed to remain?** No. A builder call may replace the authority set; combine them first and call once.
6. **Can the ADMIN role automatically view other users' profiles?** Not necessarily; that depends on tenant/ownership/resource policies.
7. **Should `/api/me` return the raw `Authentication`?** No. Use an allowlisted response DTO to prevent unintended exposure of credentials, details, or profile data.
8. **When usernames can change, should username be used as the immutable profile key?** No. In real systems, prefer a stable `accountId`.
9. **When a permission is revoked, does an already-issued JWT update automatically?** No. A JWT is an issued snapshot; use TTL/revocation/refresh or dynamic policy checks.
10. **Where do you read the user in WebFlux?** From `ReactiveSecurityContextHolder.getContext()` or an appropriate argument resolver, never assuming Servlet ThreadLocal.
11. **Why can user `reader` read their profile yet not read reports?** Because they hold `profile:read` but lack `reports:read`.
12. **When the password is wrong yet the client sends role ADMIN in the body, should the backend trust that role?** No. Roles are determined exclusively by the system after verifying credentials.
13. **Must a successful authentication always carry email and avatar?** No; it only needs identity and authorities required for authorization.
14. **With a custom principal, can you create an authenticated token straight from an unverified request?** No. Verify first, then build the trusted principal and authorities.

## 15. Production Deployment Checklist

- [ ] Account/credentials, roles/permissions, and profiles have clear storage and API boundaries.
- [ ] Passwords are stored as strong hashes with a proper encoder; no plaintext passwords in logs/DTOs.
- [ ] Principal is minimal; PII is not automatically copied into sessions/JWTs.
- [ ] Authorities come from trusted sources, never client-controlled role fields.
- [ ] Role prefixes are standardized; `hasRole` and `hasAuthority` are properly distinguished.
- [ ] Unit/integration tests cover regular users, admins, fine-grained permissions, and denied paths.
- [ ] Object ownership, tenant boundaries, and resource conditions are enforced alongside functional permissions.
- [ ] Lifetime of permissions in sessions/tokens and revocation mechanisms are evaluated.
- [ ] API/profile DTOs use field allowlists and never serialize security objects.
- [ ] Reactive pipelines never call `block()` or manual `subscribe()` for identity.
- [ ] Resource/profile reads and writes obey least privilege and privacy policies.
- [ ] HTTPS, supported dependencies, and proper rate limiting/logging/monitoring are in place.

## 16. Official Reference Documentation

- Spring Security — Authentication architecture and principal/credentials/authorities properties: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — `User.UserBuilder` / `roles` / `authorities`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/User.UserBuilder.html
- Spring Security — `ReactiveUserDetailsService`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/ReactiveUserDetailsService.html
- Spring Security — `UserDetailsRepositoryReactiveAuthenticationManager`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html
- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — HTTP authorization in reactive: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security — Reactive method security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Boot 3.3 — Build/Gradle reference (pinned version for the demo): https://docs.spring.io/spring-boot/3.3/gradle-plugin/getting-started.html

**Key takeaway:** **Principal** represents verified identity; **GrantedAuthority** represents roles/permissions for authorization; **profile** is business data read only when needed and per ownership rules; **password hashes/credentials** must never be returned in responses. Keeping these three boundaries clear makes Spring Security reactive easy to test, reduces data exposure, and allows roles and profiles to evolve independently.
