# Handling Locked, Disabled, Account-Expired, and Credentials-Expired Accounts

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **locked**, **disabled**, **account expired**, and **credentials/password expired** in Spring Security reactive.
- Map the four states accurately onto `UserDetails` methods and `User.UserBuilder` flags, avoiding inverting the meaning of `Non`.
- Understand how `ReactiveUserDetailsService`, `UserDetailsRepositoryReactiveAuthenticationManager`, `PasswordEncoder`, and `AuthenticationException` errors work together during login.
- Distinguish **authentication errors (typically HTTP 401)** from **authorization errors (typically HTTP 403)**, and handle responses without leaking account state to strangers.
- Run a Java 17 + Spring WebFlux example for five users (active, locked, disabled, account-expired, password-expired), verifying outcomes via HTTP and Reactor `StepVerifier`.
- Design lock/unlock, disable/enable, expiration/password-change workflows, cache/session/token handling, time checks, auditing, and state testing.

> **Scope:** Spring Security **reactive/WebFlux**, specifically **username/password** authentication based on `UserDetails`. These flags are not automatically checked by every OAuth2 Resource Server/JWT, pre-auth, or custom `ReactiveAuthenticationManager`; for other models, inspect the actual policy and implementation. Do not confuse Servlet's `HttpSecurity` with WebFlux's `ServerHttpSecurity`.

## 1. Four States Are Four Different Rules

Suppose an application has an account `alice`. Knowing the right password is **not enough** to log in: the account must also satisfy policies for activation, locks, and expiration dates.

| State | Business meaning | `UserDetails` API when **currently invalid** | Corresponding authentication error |
|---|---|---|---|
| **Locked** | Temporarily or proactively blocked from login, e.g., after abuse signals or an admin decision. | `isAccountNonLocked() == false` | `LockedException` |
| **Disabled** | Account is not permitted to operate, e.g., not yet activated or discontinued. | `isEnabled() == false` | `DisabledException` |
| **Account expired** | The account's usage period has ended, even though the password may still be valid. | `isAccountNonExpired() == false` | `AccountExpiredException` |
| **Credentials expired** | Password/credential is no longer accepted for normal login; may require a password-change flow. | `isCredentialsNonExpired() == false` | `CredentialsExpiredException` |

The exceptions above belong to package `org.springframework.security.authentication` and are subtypes of `AuthenticationException`. They indicate an **authentication failure**, not a lack of permission to access a resource after authentication.

**Important distinction:** An account can be simultaneously locked **and** disabled. The four flags are independent in the data model; if multiple states are invalid, which exception surfaces first depends on the authentication manager's check order. Do not use the first exception type as a complete representation of every cause stored in the database.

### 1.1. Easily Confused Definitions

- **Locked** usually has an unlock mechanism (admin review or `lockedUntil`) and may relate to brute-force protection. Do not equate it with a disabled account due to business policy.
- **Disabled** usually means the account cannot be used until re-enabled; it may have been turned off by an admin or still await verification.
- **Account expired** refers to the **account's** lifecycle (for example, a contract or subscription ended), not that the account was deleted.
- **Credentials expired** refers to the **credential**. After securely changing the password and updating state, the user can continue operating if the account remains enabled, unlocked, and non-expired.
- **Wrong password** does not belong to those four states: it typically produces `BadCredentialsException`. A valid user can still mistype their password.
- **User not found** also differs from disabled/locked; the application should avoid creating public signals that allow user enumeration.

## 2. `UserDetails` Boolean Signs: Read the Direction Carefully

The `org.springframework.security.core.userdetails.UserDetails` contract includes four status-related methods:

~~~java
boolean isEnabled();                 // true = account is allowed to operate
boolean isAccountNonLocked();        // true = NOT locked
boolean isAccountNonExpired();       // true = account has NOT expired
boolean isCredentialsNonExpired();   // true = password/credential has NOT expired
~~~

The snippet above extracts method signatures for explanation, **not a standalone Java class**.

**Read the method names slowly:** the three methods prefixed with `Non` return `true` when the state is **valid**. Only `isEnabled()` directly affirms the enabled state. Do not write it backwards like:

~~~java
// WRONG if locked = true means the account is locked:
@Override
public boolean isAccountNonLocked() {
    return locked;
}

// RIGHT for a boolean locked model:
@Override
public boolean isAccountNonLocked() {
    return !locked;
}
~~~

The two illustrative methods above belong to **two different `UserDetails` class versions**, not placed together in one class; `locked` is a domain field. Getting one `!` wrong can let locked users log in while blocking legitimate users.

### 2.1. `User.UserBuilder` Has Flags in the Opposite Direction

With the convenient `org.springframework.security.core.userdetails.User` implementation:

~~~java
UserDetails active = User.withUsername("active")
    .password("{noop}demo-pass")
    .roles("READER")
    .build();

UserDetails locked = User.withUsername("locked")
    .password("{noop}demo-pass")
    .roles("READER")
    .accountLocked(true)
    .build();

UserDetails disabled = User.withUsername("disabled")
    .password("{noop}demo-pass")
    .roles("READER")
    .disabled(true)
    .build();

UserDetails expiredAccount = User.withUsername("account-expired")
    .password("{noop}demo-pass")
    .roles("READER")
    .accountExpired(true)
    .build();

UserDetails expiredPassword = User.withUsername("password-expired")
    .password("{noop}demo-pass")
    .roles("READER")
    .credentialsExpired(true)
    .build();
~~~

This is a **Java snippet inside a class** that imports `User` and `UserDetails`; the hands-on section below provides a full program. The default values of the builder flags `disabled/accountLocked/accountExpired/credentialsExpired` are `false`, so by default users are not blocked by those four states. These builder flags carry **negative** semantics, opposite to the **positive** semantics of the `isAccountNon...` getters.

Using `{noop}` here is **strictly for local demos**; production must store passwords hashed with an appropriate encoder and never hardcode passwords or put plaintext in source code.

### 2.2. Do Not Confuse Stored Database Timestamps with Current Booleans

If your data stores `accountExpiresAt`, `passwordExpiresAt`, `lockedUntil`, `disabledAt`, or `adminLocked`, you must evaluate them into getters at authentication time. `UserDetails` does not read database timestamps automatically, has no auto-locking cron job, and does not implement expiration-date policies for you.

Example policies might be:

- `now >= accountExpiresAt` ⇒ `isAccountNonExpired() == false`.
- `now >= passwordExpiresAt` ⇒ `isCredentialsNonExpired() == false`.
- `adminLocked == true` or `now < lockedUntil` ⇒ `isAccountNonLocked() == false`.
- `status != ACTIVE` ⇒ `isEnabled() == false`, if `status` is defined as the source of truth for activation status.

The conditions above are **sample design rules** and must be confirmed against business policies, boundary instants, and real data. When working with time, store `Instant`/UTC and inject a `Clock` for deterministic tests; avoid comparing timezone-less `LocalDateTime` values or relying on drifted node clocks.

## 3. Where Are They Checked in Reactive Authentication?

Typical flow with HTTP Basic username/password in WebFlux:

~~~text
HTTP Authorization: Basic ...
  |
  v
AuthenticationWebFilter / ServerAuthenticationConverter
  |
  v
ReactiveAuthenticationManager
  |
  +--> ReactiveUserDetailsService.findByUsername(username)
  |       |
  |       +--> Mono<UserDetails> or empty/error
  |
  +--> check account state (locked, disabled, account expired)
  +--> verify password with PasswordEncoder
  +--> check credentials/password expired
  |
  +--> SUCCESS: authenticated Authentication
  |       +--> Reactor SecurityContext / filter success handler
  |       +--> authorization / handler
  |
  +--> FAILURE: Mono.error(AuthenticationException)
          +--> Authentication failure handling
          +--> typically HTTP 401 with HTTP Basic challenge
~~~

The diagram above applies to the username/password authentication path using the default `UserDetailsRepositoryReactiveAuthenticationManager`; **other models or custom managers may check differently**. Another point: checking account status **does not verify the password**, and comparing passwords **does not replace** checking account status.

### 3.1. Components and Responsibilities

**`ReactiveUserDetailsService`** is responsible for looking up the user and constructing `UserDetails`; key method:

~~~java
Mono<UserDetails> findByUsername(String username);
~~~

This is an abridged interface signature. If no user exists, the service should emit `Mono.empty()` per the contract; the authentication manager handles the failure result. Never assume `Mono.empty()` means the account is disabled.

**`UserDetailsRepositoryReactiveAuthenticationManager`** uses `ReactiveUserDetailsService` to verify username/password. It receives an input `Authentication` and returns an authenticated `Mono<Authentication>` or an error. With the default checks of the Spring Security 6.x line, the manager checks locked, disabled, and account-expired states in the pre-authentication password phase; credentials-expired is checked after the password step. These states emit appropriate exceptions when user data is present. Exact ordering can be customized and may vary across versions; when a user violates multiple states, test your actual manager's behavior.

**`PasswordEncoder`** checks credentials via `matches(rawPassword, encodedPassword)`; commonly using `PasswordEncoderFactories.createDelegatingPasswordEncoder()` or an encoder with a correspondingly strong hashing policy. Password hashing is CPU-intensive; configure appropriate schedulers/throughput and never call blocking database functions on the Netty event loop.

**`SecurityWebFilterChain`** controls filters, authentication mechanisms, exception handling, and URL authorization. When the authentication manager signals a status error, the failure handler returns a response according to the configured mechanism. Do not let manager exceptions turn into 500 due to missing handling at the authentication boundary.

### 3.2. Distinguishing 401 from 403

| Situation | Nature | Typical HTTP with the Basic demo config |
|---|---|---|
| Username does not exist | Authentication failed | `401 Unauthorized` |
| Wrong password | Authentication failed | `401 Unauthorized` |
| Locked/disabled/account expired/password expired | Authentication failed due to account status | `401 Unauthorized` |
| Authenticated yet lacking role/scope for URL | Authorization denied | `403 Forbidden` |
| `permitAll()` route | Authorization does not require login | May succeed; authentication/other filter errors can still block |

**`401` and `403` are HTTP handling choices, not hard-coded per exception.** In HTTP Basic, the entry point may add `WWW-Authenticate`. With form login it may redirect; with an API using a custom failure handler it may return another payload. Never claim each exception always maps to a fixed HTTP code independently.

### 3.3. Account Enumeration Warning

If a login endpoint publicly responds with `"alice is locked"`, `"bob does not exist"`, or `"charlie has an expired password"`, attackers can infer account status. Product policies can guide users to recover accounts via verified channels, yet **never expose detailed status to parties who have not proven ownership**.

A common strategy:

- External responses for failed login use a generic message and appropriate HTTP code, e.g. `401` and `"Unable to authenticate. Check your credentials or use the recovery flow."`.
- In controlled internal audit logs, distinguish `LockedException`, `DisabledException`, `AccountExpiredException`, and `CredentialsExpiredException` to aid operations.
- Apply rate limiting/failure counting against password guessing, without giving attackers a way to mass-lock accounts just by submitting others' usernames.
- Never log passwords, bearer tokens, session cookies, Basic credentials, or entire `Authentication` objects.

## 4. Runnable Java 17 Example: Five User States on WebFlux

The example below uses **Java 17**, **Spring Boot 3.5.16**, and the Boot-managed Spring Security version over WebFlux and HTTP Basic. There is one `GET /me` endpoint requiring authentication, one public endpoint, and five in-memory users sharing the same demo password but having different states.

The dependency/Gradle config below is complete for local hands-on practice. In real deployments, use a maintained release with the latest patches matching your project's Spring Boot/Spring Security version; do not treat the demo and hardcoded accounts as production configuration.

### 4.1. Project Structure

~~~text
reactive-account-status-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/ReactiveAccountStatusDemo.java
    └── test/java/example/AccountStatusAuthenticationTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'reactive-account-status-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
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

Spring Boot manages Spring Security, Reactor, JUnit, and Reactor Test versions; no need to randomly pick dependency versions. The project can run with a compatible Gradle or a generated Gradle Wrapper.

### 4.2. Complete Application

File `src/main/java/example/ReactiveAccountStatusDemo.java`:

~~~java
package example;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveAccountStatusDemo {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveAccountStatusDemo.class, args);
    }

    @Bean
    MapReactiveUserDetailsService users() {
        // {noop}: only to observe states on local machine.
        String demoPassword = "{noop}demo-pass";

        UserDetails active = User.withUsername("active")
            .password(demoPassword)
            .roles("READER")
            .build();

        UserDetails locked = User.withUsername("locked")
            .password(demoPassword)
            .roles("READER")
            .accountLocked(true)
            .build();

        UserDetails disabled = User.withUsername("disabled")
            .password(demoPassword)
            .roles("READER")
            .disabled(true)
            .build();

        UserDetails accountExpired = User.withUsername("account-expired")
            .password(demoPassword)
            .roles("READER")
            .accountExpired(true)
            .build();

        UserDetails passwordExpired = User.withUsername("password-expired")
            .password(demoPassword)
            .roles("READER")
            .credentialsExpired(true)
            .build();

        return new MapReactiveUserDetailsService(
            active, locked, disabled, accountExpired, passwordExpired);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @RestController
    static class ApiController {

        @GetMapping("/public")
        Mono<Map<String, String>> publicEndpoint() {
            return Mono.just(Map.of("access", "public"));
        }

        @GetMapping("/me")
        Mono<Map<String, String>> me(ServerWebExchange exchange) {
            return exchange.getPrincipal()
                .map(principal ->
                    Map.of("username", principal.getName()));
        }
    }
}
~~~

**Key points when reading the code:**

- `MapReactiveUserDetailsService` returns `Mono<UserDetails>` by username, enough to demonstrate Spring Security's default reactive authentication manager.
- User `active` keeps all four flags valid.
- User `locked` has `isAccountNonLocked() == false` via `accountLocked(true)`.
- User `disabled` has `isEnabled() == false` via `disabled(true)`.
- User `account-expired` has `isAccountNonExpired() == false`.
- User `password-expired` has `isCredentialsNonExpired() == false`.
- `anyExchange().authenticated()` only allows requests to `/me` to proceed after valid authentication; `/public` requires no login.
- The controller gets the principal from `ServerWebExchange.getPrincipal()` rather than trusting a client-supplied `X-User` header.
- There is no manual `LockedException` catching in the controller; the authentication filter/entry point handles it before protected controllers run.

### 4.3. Running and Testing HTTP

In the `reactive-account-status-demo` directory, with JDK 17+ and Gradle installed:

~~~bash
gradle bootRun
~~~

If a Gradle Wrapper is present, use `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows. From another terminal:

~~~bash
# A. Public route without sending credentials
curl -i http://localhost:8080/public

# B. Active account, valid password
curl -i -u active:demo-pass http://localhost:8080/me

# C. Locked account
curl -i -u locked:demo-pass http://localhost:8080/me

# D. Disabled account
curl -i -u disabled:demo-pass http://localhost:8080/me

# E. Account expired
curl -i -u account-expired:demo-pass http://localhost:8080/me

# F. Credential/password expired
curl -i -u password-expired:demo-pass http://localhost:8080/me

# G. Valid user but wrong password
curl -i -u active:wrong-password http://localhost:8080/me

# H. Nonexistent username
curl -i -u unknown:demo-pass http://localhost:8080/me
~~~

If using PowerShell where `curl` is a different alias, use `curl.exe`. Expected HTTP statuses for the **demo**:

| Request | HTTP status | Explanation |
|---|---|---|
| `GET /public`, no credentials | 200 | Route is `permitAll`. |
| `GET /me`, Basic `active:demo-pass` | 200 | Authentication succeeded; body contains `{"username":"active"}`. |
| `GET /me`, Basic `locked:demo-pass` | 401 | Account locked, authentication failed. |
| `GET /me`, Basic `disabled:demo-pass` | 401 | Account disabled, authentication failed. |
| `GET /me`, Basic `account-expired:demo-pass` | 401 | Account expired, authentication failed. |
| `GET /me`, Basic `password-expired:demo-pass` | 401 | Credentials expired, authentication failed. |
| `GET /me`, Basic `active:wrong-password` | 401 | Password mismatch. |
| `GET /me`, Basic `unknown:demo-pass` | 401 | User not found. |

The statuses above are expected with the filter, entry point, and username/password manager of the demo configuration. HTTP response headers (especially `WWW-Authenticate`) may depend on version and configuration; never rely on raw error messages to distinguish account states from the client. This is **HTTP output**, not fixed stdout from a Java program.

**Do not use the demo outside local:** `{noop}` stores plaintext, passwords are hardcoded, and HTTP Basic is safe only over HTTPS/TLS. In production, use strong encoders, secret management, TLS, appropriate session/token policies, and rate limiting.

## 5. Testing Exact Internal Exceptions with StepVerifier

Over HTTP, these errors usually all return 401 so detailed reasons are not leaked. At the **authentication manager unit-test level**, you still must verify that the flags produce the exact exceptions. Do not start by "fixing" the Basic failure handler to publicly return all four error types to clients.

File `src/test/java/example/AccountStatusAuthenticationTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AccountExpiredException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.CredentialsExpiredException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;

import reactor.test.StepVerifier;

class AccountStatusAuthenticationTest {

    @Test
    void lockedAccountFails() {
        assertFailure(
            user("locked").accountLocked(true).build(),
            LockedException.class);
    }

    @Test
    void disabledAccountFails() {
        assertFailure(
            user("disabled").disabled(true).build(),
            DisabledException.class);
    }

    @Test
    void accountExpirationFails() {
        assertFailure(
            user("account-expired").accountExpired(true).build(),
            AccountExpiredException.class);
    }

    @Test
    void passwordExpirationFails() {
        assertFailure(
            user("password-expired").credentialsExpired(true).build(),
            CredentialsExpiredException.class);
    }

    @Test
    void badPasswordFails() {
        var details = user("active").build();
        var manager = new UserDetailsRepositoryReactiveAuthenticationManager(
            new MapReactiveUserDetailsService(details));

        var attempt = UsernamePasswordAuthenticationToken.unauthenticated(
            "active", "wrong-password");

        StepVerifier.create(manager.authenticate(attempt))
            .expectError(BadCredentialsException.class)
            .verify();
    }

    @Test
    void validAccountSucceeds() {
        var details = user("active").build();
        var manager = new UserDetailsRepositoryReactiveAuthenticationManager(
            new MapReactiveUserDetailsService(details));

        var attempt = UsernamePasswordAuthenticationToken.unauthenticated(
            "active", "demo-pass");

        StepVerifier.create(manager.authenticate(attempt))
            .expectNextMatches(authentication ->
                authentication.isAuthenticated()
                    && authentication.getName().equals("active"))
            .verifyComplete();
    }

    private static User.UserBuilder user(String username) {
        return User.withUsername(username)
            .password("{noop}demo-pass")
            .roles("READER");
    }

    private static void assertFailure(
        UserDetails details, Class<? extends Throwable> errorType) {

        var manager = new UserDetailsRepositoryReactiveAuthenticationManager(
            new MapReactiveUserDetailsService(details));

        var attempt = UsernamePasswordAuthenticationToken.unauthenticated(
            details.getUsername(), "demo-pass");

        StepVerifier.create(manager.authenticate(attempt))
            .expectError(errorType)
            .verify();
    }
}
~~~

Run:

~~~bash
gradle test
~~~

Or `./gradlew test` / `gradlew.bat test` with a wrapper. All six tests are expected to pass with no uncaught exceptions. The test suite deliberately verifies **exceptions at the manager layer**, while HTTP clients only see safe responses. If building a custom `ReactiveAuthenticationManager`, add dedicated tests because default checks might not be implemented by a custom manager.

### 5.1. Why Test Both HTTP and Manager?

- **Manager tests** prove `UserDetails` states are evaluated properly, exception types are exact, and wrong-password cases are distinguished internally.
- **HTTP tests** prove security filters block requests before handlers, external statuses match expectations, and sensitive states are not leaked.
- **Integration tests with a real database** prove mapping timestamps/flags to `UserDetails` and cache/invalidation work properly.
- You cannot conclude WebFlux filter behavior merely by testing the `isAccountNonLocked()` getter without running the authentication pipeline.

## 6. Mapping Database State to `UserDetails` in Reactive Apps

A real-world example might store records:

| Sample column | Conceptual type | Meaning |
|---|---|---|
| `username` | Unique/canonical String | Authenticating username. |
| `password_hash` | String | Encoded hash with appropriate encoder ID. |
| `status` | `ACTIVE / DISABLED / PENDING_ACTIVATION` | Activation status. |
| `admin_locked` | boolean | Manual/investigative lock. |
| `locked_until` | nullable `Instant` | Instant when temporary lock ends. |
| `account_expires_at` | nullable `Instant` | Instant when account expires. |
| `password_expires_at` | nullable `Instant` | Instant when credential expires. |
| `failed_attempts` | integer | Counter for password-guessing protection policy. |
| `version` | integer | Supports optimistic locking on concurrent updates. |

Mapping to `UserDetails` can be written with logic like the following; this is an **illustrative snippet inside a service**, where `record` is the entity returned by a repository, `clock` is `java.time.Clock`, and `Instant` is `java.time.Instant`:

~~~java
Instant now = clock.instant();

boolean enabled = record.status() == Status.ACTIVE;

boolean accountNonLocked =
    !record.adminLocked()
    && (record.lockedUntil() == null
        || !now.isBefore(record.lockedUntil()));

boolean accountNonExpired =
    record.accountExpiresAt() == null
    || now.isBefore(record.accountExpiresAt());

boolean credentialsNonExpired =
    record.passwordExpiresAt() == null
    || now.isBefore(record.passwordExpiresAt());

UserDetails details = User.withUsername(record.username())
    .password(record.passwordHash()) // Hash from trusted data store.
    .authorities(record.authorities())
    .disabled(!enabled)
    .accountLocked(!accountNonLocked)
    .accountExpired(!accountNonExpired)
    .credentialsExpired(!credentialsNonExpired)
    .build();
~~~

Do not treat this snippet as a standalone class: `Status`, `record`, `clock`, and storage backend depend on the application. The sample logic uses half-open intervals **[start, expiresAt)**: at the exact instant `expiresAt`, the account/credential is already expired. `lockedUntil` locks only while `now < lockedUntil`; if `adminLocked` is set, the account stays locked even after the time lock ends. You must confirm your actual policy before applying it.

### 6.1. `ReactiveUserDetailsService` with a Non-Blocking Data Store

With Spring Data R2DBC, the service should return `Mono<UserDetails>` by mapping the publisher from the reactive repository:

~~~java
@Override
public Mono<UserDetails> findByUsername(String username) {
    return accountRepository.findByUsername(username)
        .map(this::toUserDetails);
}
~~~

This is an illustrative snippet **inside a class implementing `ReactiveUserDetailsService`** with `accountRepository` and `toUserDetails` already defined. Never wrap blocking JDBC inside `Mono.just(jdbcCall())` because the blocking call still executes immediately when creating the publisher.

For mandatory blocking data stores, offload the task to the right scheduler per WebFlux rules, e.g., `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`, and configure timeouts/resource limits. Switching schedulers does not magically turn blocking I/O into genuine non-blocking I/O.

### 6.2. State Transitions Must Be Consistent

When a password change succeeds, update both the hash and `passwordExpiresAt`/flag so `isCredentialsNonExpired()` subsequently returns `true`. If you only change the hash and forget to reset expiry, login will still fail.

When an admin activates an account, update `status=ACTIVE` without **accidentally unlocking** an account still under investigation. When a temporary lock expires, the getter can return `true`, yet update failure counters and logs per policy to avoid locking immediately again.

When two failed login requests arrive concurrently, incrementing `failed_attempts`, setting `lockedUntil`, and checking `version` should be executed **atomically** in the database/Redis using appropriate transactions/optimistic locking. Never let concurrent requests overwrite counters and prevent locking or unintentionally weaken it.

## 7. Account Lock/Unlock Policy

### 7.1. Reasons for Locking

- Temporary lock when sufficient evidence of repeated password guessing exists after considering access limits.
- Manual lock upon credential-leak alerts, fraud, or administrator decision.
- Business-policy lock such as anomalous login risk, potentially paired with stronger verification steps.

Account locking should not be your sole defense against brute-force attacks: attackers can **intentionally mass-lock users** using only usernames if the system auto-locks too easily. Combine IP/device/account rate limiting, appropriate delays, MFA, anomaly detection, and reliable recovery paths.

### 7.2. Unlocking

A solid policy specifies:

1. Who is allowed to unlock (admin, user via proof-of-possession, or system upon timeout)?
2. What criteria prove it is safe enough?
3. Is a password reset or revocation of old sessions/tokens required?
4. What must auditing record (actor, timestamp, reason, correlation ID) without logging secrets?
5. How do `lockedUntil` and `adminLocked` interact?

Never force `isAccountNonLocked() == true` for all users just to bypass a login error. Update the proper record and ensure risk policies are satisfied.

## 8. Disabling and Expiring Accounts

**Disabled** and **expired** both block authentication in the default manager yet carry different business impacts:

- `disabled`: turns off account usability even before any expiration date; useful when the user has not verified email or is banned.
- `account expired`: usage window ended, e.g., contract access period lapsed; can be extended via administrative action.
- A user with `isEnabled()==true` yet `isAccountNonExpired()==false` still cannot log in.
- A user with `isEnabled()==false` yet far from account expiration is still rejected.

Do not delete users from the database to simulate disabled if the system needs auditing, data ownership, or recovery flows. Conversely, do not use disabled to retain accounts indefinitely when privacy policies require deletion. Align with data retention rules and real deletion handling.

When using external OAuth2/SSO, local `UserDetails.isEnabled` might not be evaluated by the IdP's authentication provider. If disabled users must be blocked in the application, enforce the policy at the identity/authority check or appropriate authorization layer and test every login mechanism, not just Basic.

## 9. Password Expiration: Required Recovery Flow

`CredentialsExpiredException` does not automatically render a password-change screen or grant temporary permissions. If normal authentication rejects a user due to an expired password, you must design a **separate, verified password-change flow**.

A typical safe workflow:

1. When a password change is required, display a general prompt or route the user to an appropriate identity-verification flow (dedicated session, email verification link, MFA, or policy-compliant verification step).
2. Validate single-use, time-limited reset/change tokens bound to the right account and stored securely; avoid password-change endpoints that merely trust a self-declared username.
3. Validate the new password against policy, compare against password history if needed, and hash with an appropriate `PasswordEncoder`; never store/log raw passwords.
4. In one consistent unit of work: store the new hash, update `passwordChangedAt/passwordExpiresAt`, clear the credentials-expired state, and optionally revoke old sessions/refresh tokens per threat model.
5. Notify the user via a verified channel; log audit events and rate-limit the reset endpoint.
6. Require re-login or issue a new session via the full verification flow per policy; never grant `ROLE_ADMIN` or full API access merely because the user is inside a "change password" flow.

Distinguish **expired password** from **wrong password**. For an account with an expired password, the manager can block login even when the correct password is entered; returning the specific reason to someone whose identity has not been verified creates an account-enumeration risk. Use an identity-protecting recovery flow and limit returned details.

If using passkeys/OIDC/passwordless, `isCredentialsNonExpired` on a local `UserDetails` may not govern the actual authentication mechanism; manage credential state in the corresponding system.

## 10. Status Changes While the User Is Already Logged In

**The four flags are normally checked during a username/password authentication attempt.** Do not assume that when an admin flips `enabled=false` or `locked=true`, every already-issued session/JWT immediately stops working.

Examples:

- A website already saved `SecurityContext` in WebSession: later requests may restore the old Authentication unless the user is revalidated. Setting disabled in the database **does not necessarily** delete active sessions immediately.
- A resource server verifying JWT signature/expiry/scopes: if it only checks the token without querying local account status, valid tokens may continue being accepted until expiry/revocation by design.
- A custom `ReactiveAuthenticationManager` using LDAP/OIDC may have different account-status semantics from `UserDetailsRepositoryReactiveAuthenticationManager`.

If locking/disabling must **take effect immediately**, design:

- Revocation of the corresponding WebFlux/Spring Session, invalidating refresh tokens or session tokens.
- Short-lived tokens or token introspection/revocation/version checks.
- User status checks in sensitive authorization when needed, with reasonable cache TTL/invalidation.
- Multi-instance updates and concurrent request testing; do not assume caches synchronize instantly unless configured.

The cost of per-request status checks must be balanced against resource sensitivity and acceptable validity windows. Never just flip a boolean in the database and claim "all access is blocked".

## 11. Notes on PasswordEncoder and Specific Errors

An example password hash may carry a `{bcrypt}...` prefix when using `DelegatingPasswordEncoder`. `{noop}demo-pass` is for demos only; if plaintext is stored in production, having account status flags does not compensate for password exposure risk.

Situations to distinguish:

| Symptom | Likely cause | How to investigate |
|---|---|---|
| Active user always gets 401 | Wrong password, encoder mismatch with hash, or failed username lookup. | Check encoder ID, hash migration, canonical username, and internal audits. |
| User stays locked past `lockedUntil` | Wrong `isAccountNonLocked` mapping; `adminLocked` still true; stale cache. | Test with injected Clock, inspect record and cache. |
| User changed password yet still "expired" | Status or expiry timestamp not updated, stale cached user details. | Review password-change transaction and invalidation. |
| Disabled user still accesses with old token | SecurityContext/session/JWT not revalidated/revoked. | Check token/session revocation and authorization. |
| Credential expired error surfaces as 500 | `AuthenticationException` mishandled in custom filter/handler. | Test WebFlux failure handler and entry point. |
| Multiple invalid states trigger an "unexpected" exception | Checks have a priority order; custom manager behavior. | Test the manager directly with each flag independently first. |

Do not collapse `CredentialsExpiredException` into `BadCredentialsException` in internal audits, yet keep public responses minimal. Likewise, never disable account status checks to "fix" user login: those are security policies, not annoying validations.

## 12. Security Review and Concurrency Testing

### Configuration Checklist

1. **Right stack:** `ReactiveUserDetailsService` + `ReactiveAuthenticationManager` + `ServerHttpSecurity`, never transplanting Servlet examples into reactive.
2. **Data source:** status, lock time, and password expiry share a consistent source of truth; database lookups are non-blocking or placed on the right scheduler.
3. **Boolean mapping:** test `true/false` cases for every getter, especially `is...Non...` names.
4. **Authentication:** test valid/wrong passwords, nonexistent users, and each account state; never skip password comparison.
5. **HTTP behavior:** login API returns appropriate responses without leaking usernames/statuses; distinguish 401 from 403.
6. **Rate limiting:** guard against brute-force and lockout-as-DoS; have a verified unlock policy.
7. **Time boundaries:** test `now < expiresAt`, `now == expiresAt`, `now > expiresAt`, and timezone/clock skew.
8. **Concurrency:** update `failedAttempts` and `lockedUntil` atomically; prevent races from dropping failed attempts.
9. **Sessions/tokens:** test disabling/locking a user with an active session/JWT; if immediate blocking is required, revoke/revalidate.
10. **Logging:** log events and actor/correlation IDs, never plaintext passwords or tokens; restrict audit read access.
11. **Recovery:** password reset/enable/unlock via verified flows, single-use reset tokens with explicit expiry.
12. **Test every mechanism:** HTTP Basic, form login, JWT/OIDC, and custom managers can follow different paths; never generalize from one passing test.

### Self-Assessment Scenarios

**1.** A user has `isEnabled()=true` and `isAccountNonLocked()=false`. Correct password entered. Can they log in?

**Answer:** No, a status-checking username/password authentication manager will reject due to the account lock. The exception is typically `LockedException`.

**2.** With builder `.credentialsExpired(true)`, what does `isCredentialsNonExpired()` return?

**Answer:** `false`. The builder flag expresses "is expired", whereas the getter expresses "is not expired".

**3.** Password expired, yet the user is already authenticated in a still-live prior WebSession. Does setting the expired flag automatically destroy the open session?

**Answer:** Not necessarily. You need a session-revocation/revalidation policy per security requirements.

**4.** Why not return `LockedException` or `DisabledException` details to all unauthenticated clients?

**Answer:** That data can aid account-status and existence enumeration. Record specific reasons in protected audits, while public responses use an appropriately generic message and verified recovery flows.

**5.** Does a `ReactiveAuthenticationManager` handling JWTs automatically call `UserDetails.isCredentialsNonExpired()`?

**Answer:** You cannot assume so. A JWT resource server can verify signature/expiry/scopes without consulting local `UserDetails`; if local status is required, design it explicitly.

**6.** An account is simultaneously expired, locked, and disabled. Why might the first exception be locked?

**Answer:** The default username/password manager checks conditions in sequence; multiple invalid states can coexist. Check order only determines which exception is emitted first, without changing underlying data.

**7.** Should a locked account be unlocked simply by entering the correct password repeatedly?

**Answer:** No. Unlocking must follow a verified policy, potentially requiring MFA, admin review, or a lock timeout. Entering the right password does not override administrative decisions or anti-abuse policies.

## Official Documentation

- Spring Security — `UserDetails`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetails.html
- Spring Security — `User.UserBuilder`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/User.UserBuilder.html
- Spring Security — `ReactiveUserDetailsService`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/ReactiveUserDetailsService.html
- Spring Security — `UserDetailsRepositoryReactiveAuthenticationManager`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html
- Spring Security — `AbstractUserDetailsReactiveAuthenticationManager`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AbstractUserDetailsReactiveAuthenticationManager.html
- Spring Security — `LockedException` / `DisabledException` / `AccountExpiredException` / `CredentialsExpiredException`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/package-summary.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — HTTP Basic: https://docs.spring.io/spring-security/reference/reactive/authentication/passwords/basic.html
- Spring Security — Password Storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
