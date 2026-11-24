# Login Attempt Throttling and Password Guessing Prevention at the Application Layer

> **Topic:** Spring Security – reactive  
> **Knowledge area:** Form login  
> **Focus:** Designing login throttling for Spring Security WebFlux `POST /login`: counting failed authentication attempts, limiting by account and source, temporary time-bounded lockouts, non-enumerating responses, and testing with `WebTestClient`.

## 1. Why Does a Login Form Need Brute-Force Protection?

A valid login form can be abused to try thousands of username/password pairs. Hashing passwords with BCrypt/Argon2 is not enough to stop this behavior: hashing protects passwords **stored in the database**, whereas at login time the server still must verify every incoming password. Without rate-limiting measures, attackers can exploit request speed, weak passwords, reused passwords, and privileged accounts.

Several attack forms should be distinguished:

| Attack Type | Description | Why a Single Rule Is Insufficient |
| --- | --- | --- |
| **Brute force** | Trying many passwords on one account | **Per-account** limits block even when source IPs rotate |
| **Password spraying** | Using a few common passwords across many usernames | Locking each account after three failures may fail to catch it |
| **Credential stuffing** | Trying leaked username/password pairs from other services | Password may be right on the first try; requires MFA, risk analysis, and anomaly detection |
| **Distributed attack** | Spreading requests across many IPs/devices/instances | Limiting by one IP or storing counters in one server's memory can be bypassed |
| **Account enumeration** | Comparing messages/timing to learn if a username exists | Returning "account locked" vs. "account does not exist" creates a side channel |
| **Lockout denial of service** | Deliberately entering wrong passwords to lock real users out | Long or permanent hard locks turn the defense into a disruption tool |

The goal is **slowing down password-guessing speed and increasing detection**, not promising that a single counter eliminates every attack. A sound policy combines multiple layers: account-aware throttling, IP/device/risk throttling, MFA, password protections, observability, infrastructure limits, recovery paths, and behavioral testing.

### Learning Objectives

1. Pick the right rate-limit keys (`account`, verified IP, `account+IP`, tenant) and understand each key's weaknesses.
2. Design counters with **threshold**, **observation window**, **block duration**, and **counter reset conditions**.
3. Place the gate check **before password verification** and record outcomes after authentication, instead of blocking only inside a controller.
4. Integrate with `ReactiveAuthenticationManager` and `ServerHttpSecurity.formLogin(...)`, keeping WebFlux CSRF/session/redirects intact.
5. Write a runnable Java 17+ example with an injectable clock in tests; understand the limits of an in-memory demo.
6. Evaluate concurrency, Redis TTL/atomic operations, secret logging, NAT/proxies, UX, and how to respond when throttled.

## 2. Which Layer Is Responsible?

In Spring WebFlux, form login runs through the **Spring Security WebFilter chain**, not Servlet's `UsernamePasswordAuthenticationFilter` or `HttpSecurity`. Simplified flow:

```text
Browser sends GET /login
  └── Login form + CSRF token

Browser sends POST /login
 Content-Type: application/x-www-form-urlencoded
 username=...&password=...&_csrf=...
  |
  v
CsrfWebFilter / SecurityWebFilterChain
  |
  v
AuthenticationWebFilter (form login)
  |
  v
ServerFormLoginAuthenticationConverter
  |
  v
Rate-limited ReactiveAuthenticationManager
  |       |
  |       +-- throttle blocked --> AuthenticationException
  |       |
  |       +-- not blocked --> real authentication manager
  |                              |
  |                              +-- bad credentials --> increment counter
  |                              |
  |                              +-- success --> clear/decrement counter
  v
ServerAuthenticationSuccessHandler / ServerAuthenticationFailureHandler
  |                                             |
  +-- redirect after successful login           +-- redirect to /login?error
  |
  v
WebSession / Reactor SecurityContext for subsequent requests
```

A few important points:

- **CSRF runs before POST login processing** in the default configuration. A POST missing a CSRF token usually receives 403 **before** reaching the authentication manager. Do not record a "wrong password" event for CSRF errors.
- `ReactiveAuthenticationManager` is the right place to enforce policies **based on login identity** before checking the password; it has `Authentication.getName()` and sees authentication outcomes. If limiting by IP/ASN/device needs more request context, use a WebFilter/gateway component designed to collect source info reliably.
- `ServerAuthenticationFailureHandler` helps handle responses when authentication fails; **customizing only the failure handler without blocking before the password check** neither prevents verification CPU cost nor blocks concurrent attempts.
- **Authorization** (`hasRole`, `@PreAuthorize`) happens after/separately from authentication. A logged-in user lacking permissions typically gets 403; this is not a "wrong password attempt" event.
- With Spring Security reactive, form login uses `ServerHttpSecurity.formLogin`, `SecurityWebFilterChain`, `AuthenticationWebFilter`, `ReactiveAuthenticationManager`, and `ServerAuthenticationFailureHandler`.

## 3. Policy Design: Threshold, Window, Cooldown

A policy set must answer clearly:

| Parameter | Question | Value **for Demo Only** |
| --- | --- | --- |
| `MAX_FAILURES` | How many wrong passwords before blocking? | **3** |
| `WINDOW` | Over what duration are failures observed? | **10 minutes** |
| `COOLDOWN` | How long is the temporary block? | **2 minutes** |
| Key | Whose failures are grouped together? | Submitted username, exact match |
| Reset | When are failures cleared? | Successful auth or start of a new window |
| Response | Does it reveal blocked/unknown/wrong? | No; generic `/login?error` |
| State storage | Where are counters stored? | `ConcurrentHashMap` **single-JVM demo only** |

These values are for rapid testing, **not recommended default production thresholds**. Real policies must reflect risk, SLOs, operational data, account sensitivity, organizational traffic, MFA, and false-lockout impact.

### 3.1. State Transition Rules

Let `n` be the current failure count for the account within the active window.

1. No existing state: authentication is attempted; if wrong, `n=1`.
2. Second failure before the window expires: `n=2`.
3. Third failure: `n=3`, set `blockedUntil = now + COOLDOWN`.
4. During temporary block: any attempt for that account (even with the right password) is rejected **before checking the password**.
5. After cooldown expires: allow retrying; the next failure starts a new window. Success deletes the counter.
6. If `WINDOW` elapses before hitting the threshold: a new failure starts a new window.

**Do not confuse "3 failures triggers lock" with "the 4th submission increments the counter":** The demo enters the blocked state immediately upon recording the third failure, while responses for all three failures remain the generic redirect. The fourth request hits the gate before password verification.

```text
                         +------------------+
                         | No failures      |
                         +--------+---------+
                                  |
                            1st/2nd failure
                                  |
                         +--------v---------+
                         | Count failures   |
                         | within WINDOW    |
                         +---+----------+---+
                             |          |
               right password          3 failures reached
                             |          |
                        clear state     v
                             |   +------+-------+
                             |   | BLOCKED      |
                             |   | until deadline|
                             |   +------+-------+
                             |          |
                             |       COOLDOWN expires
                             |          |
                             +----------v
                               Allow retry
```

### 3.2. Which Key to Limit By?

**By account:** defends against brute force from multiple IPs, yet can be abused for DoS by locking out someone else's account. Keys must follow the exact same canonicalization rules as the user store. If the DB is case-sensitive while the limiter lowercases automatically, two distinct accounts can collide; if the DB is case-insensitive while the limiter is case-sensitive, attackers can vary casing to evade limits.

**By IP:** limits bursts and password spraying, yet is insufficient against botnets/rotating proxies. A single IP may represent a NAT for an entire office, campus, or mobile carrier; blocking whole IPs easily causes false positives.

**By `account + IP` pair:** helps limit within one specific source, yet relying solely on the pair lets an attacker spread attempts across countless IPs. You can combine **account-wide limit + IP-wide limit + account/IP limit**, each with its own policy.

**By device/cookie/ASN/tenant:** useful as supplementary signals; never treat client-asserted cookies or raw `X-Forwarded-For` headers as trusted identity. Behind-proxy IPs must be extracted only via trusted proxy configuration and controlled `ForwardedHeaderTransformer`/infrastructure; never blindly trust the first element of `X-Forwarded-For`.

## 4. Why Is "Checking Only After Login Fails" Insufficient?

If you only call `recordFailure(username)` in `ServerAuthenticationFailureHandler` **without checking beforehand**, the server still processes every request by checking the password (potentially hitting the DB and BCrypt) before updating the counter. Attackers can still fire hundreds of parallel requests to exhaust resources.

A stronger pattern is:

```text
1. Receive authentication attempt with username.
2. Check policy before checking the password.
3. If blocked: skip password verifier; return generic AuthenticationException.
4. If allowed: invoke delegate.authenticate(...).
5. Success: record success and reset failure state appropriately.
6. Wrong credentials: increment failure counter.
7. Infrastructure error: emit separate alert, DO NOT increment "wrong password".
```

Placing the gate in a **`ReactiveAuthenticationManager` decorator** lets you test the algorithm independently without changing how Spring Security parses form login. In distributed applications, steps 2 and 6 must account for races/in-flight attempts; section 11 discusses atomicity.

### 4.1. Classifying Errors

| Error Type | Count as Wrong Password? | Example |
| --- | --- | --- |
| `BadCredentialsException` | **Yes** | Wrong password |
| `UsernameNotFoundException` if thrown | **Yes**, without revealing to client | Account not found |
| `LockedException` thrown by the gate itself | **Do not repeatedly increment** | Cooldown active |
| `AuthenticationServiceException` / DB error | **No** | Provider unavailable, timeout |
| CSRF 403 | **No** | Invalid CSRF token |
| Authorization 403 | **No** | User logged in but lacks permission |
| Password reset/OTP failure | **Separate policy** | Do not share counters arbitrarily |

Spring Security may mask username-not-found causes behind `BadCredentialsException`. Test against the actual `ReactiveAuthenticationManager` you use. Never log credentials, passwords, tokens, or raw exceptions containing sensitive details.

## 5. Runnable Java 17+ Project with Spring Security WebFlux

This is a **single-JVM learning example** using Spring Boot **3.5.16** (Spring Security 6.x line managed by Boot), Maven, JUnit, and `WebTestClient`. Spring Boot 3.5.16 reached end of OSS support for the 3.5 line; new production systems should pick a supported line per the appropriate migration guide. The code focuses on **form login**. The example's in-memory algorithm **is not safe as-is for multiple servers or high concurrent traffic**.

**Design decisions:**

- Demo user `alice` has password `welcome123`, stored as a BCrypt hash generated by the app at startup.
- Default form login `GET /login`, `POST /login`, form fields `username`, `password`, and CSRF token.
- Wrong password: generic redirect `/login?error`; never expose "wrong password", "user does not exist", or "locked".
- Right password: redirect `/home`; Spring Security handles `SecurityContext` for the session.
- Three failures within a 10-minute window block password attempts for 2 minutes.
- `/public` is open to unauthenticated users; `/home` requires authentication.
- HTTP Basic is disabled so tests do not accidentally pass via another mechanism.
- Tests submit real credentials in forms with Spring Security Test's `csrf()`, never using `mockUser` as proof of password validation.

### 5.1. Directory Structure

```text
form-login-throttle/
├── pom.xml
└── src/
    ├── main/java/demo/login/
    │   ├── Application.java
    │   ├── LoginAttemptLimiter.java
    │   ├── ThrottledAuthenticationManager.java
    │   ├── SecurityConfiguration.java
    │   └── PageController.java
    └── test/java/demo/login/
        ├── LoginAttemptLimiterTests.java
        └── FormLoginThrottleTests.java
```

### 5.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>form-login-throttle</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The Spring Boot parent/BOM manages compatible versions of Spring Security, Reactor, and dependencies. Do not pin a separate version for `spring-security-test` to avoid API mismatches. `spring-boot-starter-test` brings JUnit/Spring Test; `spring-security-test` brings `csrf()` and `springSecurity()` helpers.

### 5.3. `src/main/java/demo/login/Application.java`

```java
package demo.login;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 5.4. `src/main/java/demo/login/LoginAttemptLimiter.java`

This is a **fixed observation window + cooldown** counter using an injected `Clock`. `ConcurrentHashMap.compute` updates a single key atomically within the **same JVM**. The demo intentionally omits DB/Redis or background cleanup and **does not guarantee atomic gate-check + delegate-authentication under concurrent requests**.

```java
package demo.login;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public final class LoginAttemptLimiter {
    private static final int MAX_FAILURES = 3;
    private static final Duration WINDOW = Duration.ofMinutes(10);
    private static final Duration COOLDOWN = Duration.ofMinutes(2);

    private final ConcurrentMap<String, State> states =
        new ConcurrentHashMap<>();
    private final Clock clock;

    private record State(
        Instant firstFailure,
        int failures,
        Instant blockedUntil
    ) {}

    public LoginAttemptLimiter(Clock clock) {
        this.clock = clock;
    }

    public boolean isBlocked(String username) {
        State state = states.get(username);
        return state != null
            && state.blockedUntil() != null
            && clock.instant().isBefore(state.blockedUntil());
    }

    public void recordFailure(String username) {
        Instant now = clock.instant();
        states.compute(username, (key, old) -> {
            // New account, expired observation window, or expired cooldown.
            if (old == null
                    || !now.isBefore(old.firstFailure().plus(WINDOW))
                    || (old.blockedUntil() != null
                        && !now.isBefore(old.blockedUntil()))) {
                return new State(now, 1, null);
            }

            // Do not keep incrementing during cooldown.
            if (old.blockedUntil() != null) {
                return old;
            }

            int failures = Math.min(MAX_FAILURES, old.failures() + 1);
            Instant blockedUntil = failures >= MAX_FAILURES
                ? now.plus(COOLDOWN) : null;

            return new State(old.firstFailure(), failures, blockedUntil);
        });
    }

    public void recordSuccess(String username) {
        states.remove(username);
    }

    public int failureCount(String username) {
        State state = states.get(username);
        return state == null ? 0 : state.failures();
    }

    // Only for examples/tests in package demo.login.
    void clearForTests() {
        states.clear();
    }
}
```

**Important invariants:**

- `State` is a Java `record` whose own fields are immutable. `compute` replaces a key's value with a new `State`; there is no non-atomic `get` → `put` when recording failures.
- `Clock` is injected so tests can control time without calling `Thread.sleep(120000)`.
- Once cooldown expires, `isBlocked` returns false. `recordSuccess` removes state; `recordFailure` after cooldown starts a new window.
- `failureCount()` is for illustration and testing only; never return this count to clients, as it could leak account state.
- **Username is the exact submitted string key.** The demo user store is case-sensitive; if production accounts use case-insensitive rules, canonicalize **consistently** between limiter and user store. Never arbitrarily trim/lowercase the username in only one place.
- **Memory risk:** Attackers supplying countless distinct usernames make `ConcurrentHashMap` grow without bound. Production must use TTL-backed storage, key quotas, and ingress limits.
- **Race risk:** `isBlocked` and `recordFailure` are two separate operations; multiple requests can pass the gate before the third failure is recorded. Production needs atomic budget reservation/rate limiting or a concurrency cap as in section 11.
- This is **per-account limiting**, not yet a complete credential-stuffing defense system.

### 5.5. `src/main/java/demo/login/ThrottledAuthenticationManager.java`

This decorator receives an unauthenticated `Authentication`, checks the lock **before** calling the real manager, and records state after obtaining the result.

```java
package demo.login;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import reactor.core.publisher.Mono;

public final class ThrottledAuthenticationManager
        implements ReactiveAuthenticationManager {

    private final ReactiveAuthenticationManager delegate;
    private final LoginAttemptLimiter limiter;

    public ThrottledAuthenticationManager(
            ReactiveAuthenticationManager delegate,
            LoginAttemptLimiter limiter) {
        this.delegate = delegate;
        this.limiter = limiter;
    }

    @Override
    public Mono<Authentication> authenticate(Authentication attempt) {
        // defer: check rate limit at subscription time, not assembly time.
        return Mono.defer(() -> {
            String username = attempt.getName();

            if (limiter.isBlocked(username)) {
                return Mono.error(
                    new LockedException("Authentication temporarily unavailable"));
            }

            return delegate.authenticate(attempt)
                .doOnNext(result -> limiter.recordSuccess(username))
                .doOnError(error -> {
                    if (error instanceof BadCredentialsException
                            || error instanceof UsernameNotFoundException) {
                        limiter.recordFailure(username);
                    }
                });
        });
    }
}
```

Because `ReactiveAuthenticationManager.authenticate` returns `Mono<Authentication>`, the wrapper calls neither `block()` nor `subscribe()`. When not blocked, the delegate proceeds to check the password/DB per standard mechanisms. When blocked, `LockedException` stops before the delegate.

Only the selected credential errors are counted. For infrastructure errors (`AuthenticationServiceException` or errors outside controlled `AuthenticationException`s), emit appropriate alerts/telemetry rather than incrementing `wrong-password count`.

**Limitations:** Spring Security can use multiple authentication mechanisms. Ensure **form login actually uses the wrapper** via `.authenticationManager(manager)`; if your app also supports OAuth2, passkeys, magic links, MFA, or password resets, design policies and event counting separately. Do not treat every valid `Authentication` as a password login.

### 5.6. `src/main/java/demo/login/SecurityConfiguration.java`

```java
package demo.login;

import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    LoginAttemptLimiter loginAttemptLimiter(Clock clock) {
        return new LoginAttemptLimiter(clock);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        // Demo accounts only; never hardcode passwords in production.
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("welcome123"))
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("hello456"))
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(alice, bob);
    }

    @Bean
    ReactiveAuthenticationManager formAuthenticationManager(
            MapReactiveUserDetailsService users,
            PasswordEncoder encoder,
            LoginAttemptLimiter limiter) {

        UserDetailsRepositoryReactiveAuthenticationManager delegate =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        delegate.setPasswordEncoder(encoder);

        return new ThrottledAuthenticationManager(delegate, limiter);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager formAuthenticationManager) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/login", "/public").permitAll()
                .pathMatchers("/home").authenticated()
                .anyExchange().denyAll()
            )
            .formLogin(form -> form
                .authenticationManager(formAuthenticationManager)
                .authenticationSuccessHandler(
                    new RedirectServerAuthenticationSuccessHandler("/home"))
                .authenticationFailureHandler(
                    new RedirectServerAuthenticationFailureHandler("/login?error"))
            )
            .httpBasic(basic -> basic.disable())
            .build();
    }
}
```

Choices made:

1. `formLogin(...)` enables Spring Security WebFlux's default form login. Because `.loginPage(...)` **is not called**, Spring Security supplies the default login page at `GET /login` and handles `POST /login`.
2. `authenticationManager(formAuthenticationManager)` ensures the login filter uses the throttling decorator instead of bypassing the counter.
3. Success/failure redirects use the proper reactive handlers (`RedirectServerAuthenticationSuccessHandler`, `RedirectServerAuthenticationFailureHandler`) with the **same generic error target**, revealing no lock state.
4. `httpBasic(...disable())` keeps the exercise focused on form login, preventing tests from accidentally succeeding via Basic.
5. `CSRF` remains enabled by default. Browsers must submit the form with a CSRF token; `WebTestClient` uses `mutateWith(csrf())`.
6. `MapReactiveUserDetailsService` is only a mock user source for the demo. Passwords are stored **as BCrypt hashes**, even though sample inputs appear in plaintext in source for learning purposes.
7. Only **one** `ReactiveAuthenticationManager` bean (the wrapper) is registered; the delegate is instantiated locally inside the factory bean, avoiding ambiguous manager injection.
8. Form login uses sessions/cookies per Spring Security's mechanism. Never casually switch to `NoOpServerSecurityContextRepository` if you expect users to stay logged in after redirecting.

### 5.7. `src/main/java/demo/login/PageController.java`

```java
package demo.login;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class PageController {

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public OK");
    }

    @GetMapping("/home")
    public Mono<String> home() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .map(username -> "Hello " + username);
    }
}
```

`/home` is a plain text REST endpoint instead of a real HTML page to keep the demo concise. Output appears only after Spring Security has authenticated the user from the session. Never read a username from an arbitrary query/header to decide whether someone is logged in.

## 6. Testing the Policy with a Fake Clock: No Waiting Two Real Minutes

### 6.1. `src/test/java/demo/login/LoginAttemptLimiterTests.java`

Tests the fixed-window and cooldown algorithm directly. Uses a custom `AdjustableClock`, making results completely deterministic within the same JVM.

```java
package demo.login;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LoginAttemptLimiterTests {

    private static final class AdjustableClock extends Clock {
        private Instant now = Instant.parse("2026-01-01T00:00:00Z");

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            return Clock.fixed(now, zone);
        }

        @Override
        public Instant instant() {
            return now;
        }

        void advance(Duration elapsed) {
            now = now.plus(elapsed);
        }
    }

    @Test
    void threeFailuresCauseTwoMinuteCooldown() {
        AdjustableClock clock = new AdjustableClock();
        LoginAttemptLimiter limiter = new LoginAttemptLimiter(clock);

        limiter.recordFailure("alice");
        limiter.recordFailure("alice");
        assertEquals(2, limiter.failureCount("alice"));
        assertFalse(limiter.isBlocked("alice"));

        limiter.recordFailure("alice");
        assertEquals(3, limiter.failureCount("alice"));
        assertTrue(limiter.isBlocked("alice"));

        clock.advance(Duration.ofMinutes(2));
        assertFalse(limiter.isBlocked("alice"));

        limiter.recordFailure("alice");
        assertEquals(1, limiter.failureCount("alice"));
    }

    @Test
    void successResetsOnlyItsOwnAccount() {
        LoginAttemptLimiter limiter =
            new LoginAttemptLimiter(Clock.systemUTC());

        limiter.recordFailure("alice");
        limiter.recordFailure("bob");
        limiter.recordSuccess("alice");

        assertEquals(0, limiter.failureCount("alice"));
        assertEquals(1, limiter.failureCount("bob"));
    }

    @Test
    void failureAfterObservationWindowStartsNewWindow() {
        AdjustableClock clock = new AdjustableClock();
        LoginAttemptLimiter limiter = new LoginAttemptLimiter(clock);

        limiter.recordFailure("alice");
        limiter.recordFailure("alice");

        clock.advance(Duration.ofMinutes(10));
        limiter.recordFailure("alice");

        assertEquals(1, limiter.failureCount("alice"));
        assertFalse(limiter.isBlocked("alice"));
    }
}
```

The test class has **3 JUnit methods**. The tests show:

- Immediately after the third failure, `isBlocked("alice")` is true.
- After exactly 2 minutes, the cooldown ends; the next failure starts a new window.
- Success clears only that account's state.
- After 10 minutes, a subsequent failure restarts the count rather than retaining old failures forever.

No `Thread.sleep` is used in these tests, so they do not depend on machine/CI speed.

## 7. Real Integration Tests for `POST /login` and CSRF

A test that only calls `mockUser()` does not prove `ReactiveAuthenticationManager` checked any password, so it is **insufficient** for testing brute-force protection. With form login, submit `application/x-www-form-urlencoded` and a valid CSRF token.

### 7.1. `src/test/java/demo/login/FormLoginThrottleTests.java`

```java
package demo.login;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class FormLoginThrottleTests {

    @Autowired
    ApplicationContext applicationContext;

    @Autowired
    LoginAttemptLimiter limiter;

    private WebTestClient client;

    @BeforeEach
    void prepare() {
        limiter.clearForTests(); // Reset in tests only.
        client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient.ResponseSpec login(
            String username, String password) {

        return client.mutateWith(csrf())
            .post().uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("username", username)
                .with("password", password))
            .exchange();
    }

    @Test
    void loginPageIsAvailable() {
        client.get().uri("/login")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void guestIsRedirectedToLogin() {
        client.get().uri("/home")
            .exchange()
            .expectStatus().is3xxRedirection();
    }

    @Test
    void incorrectPasswordUsesGenericFailureRedirect() {
        login("alice", "wrong")
            .expectStatus().is3xxRedirection()
            .expectHeader().valueEquals(
                HttpHeaders.LOCATION, "/login?error");

        assertEquals(1, limiter.failureCount("alice"));
    }

    @Test
    void unknownUserSeesSameErrorUrl() {
        login("nobody", "wrong")
            .expectStatus().is3xxRedirection()
            .expectHeader().valueEquals(
                HttpHeaders.LOCATION, "/login?error");

        assertEquals(1, limiter.failureCount("nobody"));
    }

    @Test
    void threeBadPasswordsBlockLaterCorrectPassword() {
        for (int attempt = 0; attempt < 3; attempt++) {
            login("alice", "wrong")
                .expectStatus().is3xxRedirection()
                .expectHeader().valueEquals(
                    HttpHeaders.LOCATION, "/login?error");
        }

        assertEquals(3, limiter.failureCount("alice"));
        assertTrue(limiter.isBlocked("alice"));

        // Even though password is now right, gate is still in cooldown.
        login("alice", "welcome123")
            .expectStatus().is3xxRedirection()
            .expectHeader().valueEquals(
                HttpHeaders.LOCATION, "/login?error");
    }

    @Test
    void successfulLoginResetsEarlierFailures() {
        login("alice", "wrong").expectStatus().is3xxRedirection();
        login("alice", "wrong").expectStatus().is3xxRedirection();
        assertEquals(2, limiter.failureCount("alice"));

        login("alice", "welcome123")
            .expectStatus().is3xxRedirection()
            .expectHeader().valueEquals(
                HttpHeaders.LOCATION, "/home");

        assertEquals(0, limiter.failureCount("alice"));
        assertFalse(limiter.isBlocked("alice"));
    }

    @Test
    void oneLockedAccountDoesNotBlockAnother() {
        for (int attempt = 0; attempt < 3; attempt++) {
            login("alice", "wrong").expectStatus().is3xxRedirection();
        }
        assertTrue(limiter.isBlocked("alice"));

        login("bob", "hello456")
            .expectStatus().is3xxRedirection()
            .expectHeader().valueEquals(
                HttpHeaders.LOCATION, "/home");

        assertFalse(limiter.isBlocked("bob"));
    }

    @Test
    void formPostWithoutCsrfIsRejectedBeforePasswordCheck() {
        client.post().uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("username", "alice")
                .with("password", "wrong"))
            .exchange()
            .expectStatus().isForbidden();

        assertEquals(0, limiter.failureCount("alice"));
    }
}
```

There are **8 `@Test` methods** in the integration test. Combined with the 3 limiter tests in section 6, that makes **11 tests**. `WebTestClient` is bound to `ApplicationContext` with `springSecurity()` to exercise the real chain; `csrf()` is mock support supplying a valid CSRF token for test requests, not a production configuration disabling CSRF checks.

**Important note on sessions:** The tests intentionally assert redirects on successful login, without assuming a single `WebTestClient` automatically retains cookies from one response to the next. To test `GET /home` after login, **capture the session cookie from the login response and resend that cookie**, or configure a cookie-retaining test client. Do not equate "POST login returns a redirect" with "verified the next request carries a session". The current topic prioritizes the limiter; a session-focused test should separately verify cookie/session persistence.

### 7.2. Test Matrix and Interpretation

| Test | What Is Verified | Result |
| --- | --- | --- |
| GET `/login` | Default form is served | **200** |
| GET `/home` unauthenticated | Browser authentication entry point | **3xx** to login |
| `alice` wrong password once | Counter after authentication failure | `302 /login?error`, count = 1 |
| `nobody` wrong password | Does not leak account existence | Same generic redirect as real user |
| `alice` wrong 3 times | Lock threshold | Count = 3, blocked |
| `alice` right password while blocked | Gate sits before password verifier | Still generic error redirect |
| `alice` wrong twice then right | Reset after success | Redirect `/home`, count = 0 |
| `alice` blocked, `bob` logs in | Per-account state isolation | Bob succeeds |
| POST `/login` missing CSRF | CSRF is not converted into password failure | **403**, count = 0 |

Browser form-login responses **are typically 302 redirects**, not necessarily 401/429. If a JSON API wants to return 429 for throttling, it needs an appropriate endpoint/authentication mechanism and failure/entry point; never convert every `BadCredentialsException` into 429 to avoid revealing account state.

## 8. Running and Observing from a Browser

### 8.1. Environment Requirements

- Java 17+ (Spring Boot 3.5.x), compatible Maven.
- Files in the right `demo.login` package and Maven layout.
- Port `8080` free, or reconfigured `server.port`.

Commands:

```bash
java -version
mvn -version
mvn clean test
mvn spring-boot:run
```

Expect **11 tests, 0 failures, 0 errors** from the demo code, and a successful build when JDK/dependencies are compatible. This is the **expected outcome**, not a claim that tests were run in every environment.

Open a browser at `http://localhost:8080/login` and try:

1. Log in as `alice` with password `wrong`: displays the generic error state.
2. Fail a total of three times: `alice`'s account is temporarily blocked.
3. Enter the right password `welcome123` immediately afterwards: still receives the generic error during cooldown.
4. Use `bob`/`hello456`: the other account can log in.
5. After cooldown expires, `alice` can log in with `welcome123`; success resets state.

**Note when testing manually in a browser:** After successful login, the current session retains the logged-in state. To test unauthenticated flows from scratch, log out via Spring Security's flow (with valid CSRF) or open a separate/incognito browser window with clean cookies. Never use demo accounts in public environments.

### 8.2. Why Is Simple `curl -X POST /login -d ...` Discouraged?

Spring Security WebFlux form login normally enables CSRF. A POST missing a CSRF token gets **403** before reaching the authentication manager, so it is not a valid test of the password-limiting algorithm. In browsers, the default login page handles generating the CSRF token for the form. In integration tests, `WebTestClient.mutateWith(csrf())` handles this.

If manual testing with `curl` is needed, manage **cookies + CSRF token + form fields** realistically rather than disabling CSRF just to dodge 403. For APIs using credentials not auto-sent by browsers, CSRF policies may differ, though risks must be evaluated before changing them.

## 9. When to Return 429, When to Keep a Generic Redirect?

On a browser form-login endpoint, returning `/login?error` for all authentication errors avoids leaking "valid username, currently locked." Throttling does not need to expose exact counter values to the client.

At an **IP/edge rate-limiting** layer, `429 Too Many Requests` with `Retry-After` can fit: a client is sending too many requests regardless of account. Still, do not rely solely on gateway 429s to stop distributed brute force, and do not return 429 only when an account threshold is hit if doing so tells attackers the account exists.

| Response Type | When to Consider | Risk |
| --- | --- | --- |
| Generic redirect `/login?error` | Wrong form authentication or in cooldown | Leaks less state, though users need generic recovery guidance |
| `401 Unauthorized` with generic body | Password login API not using browser redirects | Avoid overly detailed account descriptions |
| `429 Too Many Requests` | Broad burst limit by IP/client with `Retry-After` | If emitted only for existing accounts, creates enumeration |
| CAPTCHA / progressive delay | High-risk bursts while supporting legitimate users | CAPTCHA does not replace throttling; impacts accessibility |
| Step-up MFA / passkeys | High risk, exposed passwords, or anomalous logins | Must prevent bypassing across different login paths |
| Recovery/self-service | Legitimate user hits cooldown | Must protect the recovery mechanism itself from abuse |

Displayed text can be: "Unable to sign in. Please check your details or try again later; if needed, use account recovery." Avoid phrases distinguishing "This username does not exist" from "Real account locked due to 3 wrong attempts."

## 10. Designing Combined IP and Account Protection Layers

**Username-only limiting in the demo is insufficient** against credential stuffing and password spraying. Add a **coarse request-rate gate** before authentication:

```text
Internet
  |
  v
CDN / WAF / ingress        --> IP/source burst rate, abuse reputation
  |
  v
Spring WebFlux WebFilter   --> trusted remote address / device risk
  |
  v
Form AuthenticationFilter  --> account-wide failure window
  |
  v
Password verification      --> BCrypt/Argon2id, account state
  |
  v
Login result               --> MFA/step-up, metrics and redacted audit
```

Logic example (**architectural illustration, not standalone runnable Java**):

```text
if IP budget exhausted:
    respond 429/Retry-After (generic; do not parse username)
else if account-wide failed-login budget exhausted:
    fail authentication with generic login response
else:
    verify credentials
    if credentials wrong:
        atomically record account failure
        record coarse source risk signal
    if credentials right:
        clear/reduce account failures
        continue normal session/MFA flow
```

**Never read `X-Forwarded-For` directly from the Internet** as a rate-limit key. Clients can forge headers if the app is not shielded by trusted proxies. In trusted infrastructure, configure forwarded headers at the proper proxy layer, declare an allowlist of trusted proxies, and use the normalized remote address.

Points to consider for IP keys:

- IPv4/IPv6: normalize formats, consider IPv6 prefixes and policies avoiding blocking overly huge network blocks.
- NAT: many users share one IP, especially corporate and mobile networks.
- Proxy chains: never trust values clients can supply themselves.
- VPN/botnets: IPs change, so IP cannot be the sole defense.
- Privacy: retain IPs only as needed with explicit TTLs, never log passwords; comply with data protection policies.
- Rate limits on `POST /login` should be separate from site-wide limits so an attacker's login attempts do not degrade content reading for other users.

## 11. Production: Atomicity, TTL, Multi-Instance, and Anti-DoS

### 11.1. Why Is `ConcurrentHashMap` Not Enough?

The demo stores state in **one JVM**. With three app replicas:

```text
Login requests
   |
   +--> Instance A: alice failures = 2
   +--> Instance B: alice failures = 2
   +--> Instance C: alice failures = 2

If each instance caps locally at 3, attacker already made 6 attempts
without any single instance necessarily hitting 3.
```

Rolling restarts also wipe counters, and each JVM consumes memory per username. Never deploy raw `ConcurrentHashMap` to multi-instance systems. In real products, use **Redis** (or dedicated storage with TTLs/atomic updates) to share state across replicas and prevent unbounded memory growth.

### 11.2. TTL and Key Design in Redis

A conceptual structure:

```text
login:acct:<keyed-hash-of-canonical-username>
  failures: 2
  window_started_ms: ...
  blocked_until_ms: ...
  EXPIRE: long enough to cover window/cooldown
```

Avoid storing raw passwords, `Authorization`, JWTs, or unnecessary data. If usernames are identifying data, an HMAC with a server-held secret can produce stable keys and reduce direct username exposure in Redis keys; you must still manage secret lifecycles, cardinality bounds, and Redis access control. A plain unsalted hash is not automatic protection for low-entropy usernames.

**Every counter and TTL update must be atomic**, such as via a Redis Lua script or appropriate transactions/primitives. Separate read `GET` then write `SET` across replicas risks lost updates under concurrent requests.

### 11.3. Concurrency: Gate and Password Check Are Two Steps

Suppose `MAX_FAILURES=3` and currently `failures=2`. Suppose 100 parallel requests simultaneously see not-blocked and all start BCrypt before the first records the third failure. The counter may still update afterwards, yet **compute cost and slipped attempts** already exceeded the threshold. In production, you need an atomic **reserve/check budget** mechanism before the password verifier:

```text
Lua/transaction (concept):
  read current window, blocked-until, in-flight
  atomically reject if blocked or risk budget exhausted
  reserve one attempt slot and set short TTL
return allow/deny

if allow:
  verify credentials
  atomically mark failed/successful and release reservation
  release reservation also on cancellation/timeout
```

The snippet above is **pseudocode**, not a complete Redis Lua program. Carefully design idempotency, TTLs for in-flight reservations, races between success and failure, clock sources, outage fallbacks, and cancellation. Without reservations or a concurrency cap, incrementing counters only after failure does not stop floods that already entered the password verifier.

Never lock an account **permanently** solely due to wrong passwords; that easily turns into a denial of service against account owners. Combine progressive backoff, MFA/step-up, risk checks, and safe recovery instead.

### 11.4. Redis Failure Policy: Fail-Open or Fail-Closed?

When Redis is slow/down, the system must decide the trade-off:

- **Fail-open** lets logins continue: increases availability while weakening brute-force protection.
- **Fail-closed** rejects logins: stronger protection, though a Redis outage locks everyone out.
- **Degraded mode**: tighter gateway limits, short-TTL local cache, alerts, circuit breakers, or risk-based fallbacks.

There is no single right choice for every product. Document the decision in runbooks, run load/chaos tests, and align with SLOs and account sensitivity.

### 11.5. Memory/Cardinality Limits

Even Redis with TTLs can be flooded with millions of random usernames; IP-only and account-only limits are complementary dimensions. Bound the **number of keys created**, key TTLs, key-creation rate per source, Redis capacity, and retention. An attacker can intentionally fill the cache if the system creates keys for arbitrary usernames without bounds.

## 12. User Enumeration, Latency, and UX

Identical wording **is not always enough** to prevent account enumeration. If real usernames execute BCrypt while nonexistent usernames reject immediately, response latency can differ. Spring Security user-details authentication includes mechanisms to mask username-not-found and narrow timing differences depending on the provider, yet any custom authentication manager/DB integration must be re-verified.

Rules:

1. Never return `"Unknown username"` or `"Account locked for 120 seconds"` only for existing accounts.
2. Keep timing behavior reasonably consistent between unknown accounts and wrong passwords within practical limits; avoid blocking sleeps on the Netty event loop to fake delays.
3. Never log raw usernames/passwords into high-cardinality metrics. Use aggregated buckets/labels, request correlation IDs, and protected audit stores.
4. When users are temporarily blocked, provide a **safe recovery path** without opening new easily abused endpoints.
5. The login error page must be accessible without authentication; for `GET /login?error`, Spring Security matches path `/login` (query strings are not separate path matchers).
6. Apply rate limiting even for nonexistent usernames so attackers cannot probe `nobody` indefinitely, while bounding distinct keys.

### Deliberate Lockout Caused by Others

An attacker can submit wrong passwords for an employee's public email to prevent the employee from logging in. Defenses can include per-IP limits, progressive delays instead of hard locks, MFA, controlled recovery mechanisms, false-positive detection, and notifying the user via a trusted out-of-band channel without leaking state on the login UI.

Do not treat CAPTCHA as a silver bullet: bots can solve CAPTCHAs via paid farms, and CAPTCHAs hurt accessibility and UX. CAPTCHA is **defense in depth**, triggered after appropriate risk signals.

## 13. Testing and QA for Real Environments

Demo tests are educational, whereas production needs multiple testing levels:

| Test Group | What to Verify | Hints |
| --- | --- | --- |
| Unit | `MAX_FAILURES`, `WINDOW`, `COOLDOWN`, reset boundaries | Fake `Clock`, no sleep |
| Integration | Valid form POST+CSRF, authentication manager invoked, generic redirect | `WebTestClient` sending real credentials |
| Negative | Unknown user, wrong password, blocked account, expired cooldown | Do not leak username in responses |
| CSRF | POST missing/wrong token skips password verification | 403, does not increment wrong-password count |
| Concurrency | N parallel requests on same key | Does not exceed reservation/budget |
| Distributed | N replicas sharing counters | Atomic Redis/Lua scripts, no lost updates |
| Proxy/IP | Spoofed headers, multiple proxy hops, NAT/IPv6 | Do not trust client `X-Forwarded-For` |
| Availability | Redis timeout, DB unavailable | Tested fail-open/closed policy |
| Security | Password hashing, TLS, CSRF, session fixation, cookies | No secret logging; proper session behavior |
| Load | Login flood exhausting CPU on BCrypt | Gate before verifier, backpressure, in-flight caps |
| Usability | Accidental lockouts, recovery, accessibility | Support flows and neutral notices |

In Spring Security, `@WithMockUser` is helpful for testing **authorization**, yet it **does not simulate a wrong password through form login**, so it should not be the primary test for a limiter inside `ReactiveAuthenticationManager`.

Other useful tests:

- Ensure **success after 1–2 failures** resets the counter without clearing other users' keys.
- Test exact WINDOW/COOLDOWN boundaries, e.g., `now == blockedUntil`.
- Test across restarts/deploys if policy requires counters to survive across instances.
- Test the same account from two different IPs and password spraying across many accounts from one IP.
- Test rate-limit behavior when a client cancels a request after reserving a slot.
- Test real sessions/cookies: after form login succeeds and redirects, the next request with the session cookie accesses `/home`; unauthenticated requests redirect.
- Test that password reset/account recovery does not bypass the policy or enable enumeration.
- Verify logs, traces, and metrics contain no raw passwords, form payloads, or raw authentication objects.

## 14. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Counting by IP only | Botnets rotate IPs to hit the same account | Add account-wide budgets |
| Counting by username only | Password spraying across many accounts goes undetected | Add source-wide burst limits |
| Counting in per-replica maps | Load balancers distribute requests and bypass limits | Use shared state with TTLs and atomic operations |
| Incrementing in failure handler without gating before manager | BCrypt CPU is still flooded | Add pre-auth decision before password verification |
| Using `get` then `put` for counters | Lost updates under races | Use `compute` or Redis scripts/atomic primitives |
| Counting only "real users" | User enumeration and unlimited unknown guesses | Count bad credentials/unknowns under a unified policy |
| Counting every `AuthenticationException` as bad password | Redis/DB outages lock users out | Distinguish bad credentials from system errors |
| Returning "locked" only when username exists | Leaks account existence | Keep messages and timing reasonably uniform |
| Permanent hard lock on third failure | Attackers easily DoS real accounts | Bounded cooldowns, progressive controls, recovery |
| Not resetting on success | Legitimate users get locked repeatedly | Define reset/decay per policy |
| Resetting all keys when one user succeeds | Can wipe IP/system-wide attack signals | Reset only that account's scope |
| Calling `subscribe()` or `block()` inside a WebFilter | Context leaks, event-loop blocking, poor cancellation | Compose `Mono`/reactive operators |
| Disabling CSRF just to make POST login tests run | Browser forms become vulnerable to CSRF | Use `csrf()` in tests; keep proper policies |
| Relying on `@WithMockUser` to test password checks | Bypasses real authentication path | POST forms and verify manager/counters |
| Reading IP from arbitrary client headers | Attackers spoof IPs to evade limits | Trust only configured proxies |
| Unbounded key cardinality | Memory/Redis exhaustion | TTLs, per-source limits, HMAC/normalization |
| 429 for real accounts, 401 for nonexistent accounts | User enumeration | Generic responses for account state; 429 for global/IP budgets when appropriate |
| Hardcoded passwords in production source | Secret exposure | Secret management/DB hashes, rotation |
| Logging form payloads or `Authentication.getCredentials()` | Password leakage | Redact logs, audit appropriately |
| No plan for Redis failure | Uncontrolled fail-open or total login outage | Runbooks, alerts, tested fallbacks |

## 15. Self-Check Questions

**Q1.** If a policy locks after three wrong attempts on a username, can a 20-IP botnet be stopped by an IP-only limiter?  
**Answer:** Not reliably. Botnets can distribute attempts. You need account-wide state plus supplementary source/risk signals.

**Q2.** Why shouldn't `recordFailure` live solely inside `ServerAuthenticationFailureHandler`?  
**Answer:** Because requests can still go through password/BCrypt checks before the handler is called; without an early gate, verification cost and in-flight requests are not reduced.

**Q3.** If a form login POST lacks a CSRF token and returns 403, should you increment a bad-password attempt?  
**Answer:** No. Password authentication was not even performed; CSRF errors belong to another layer. Record a separate risk signal if desired.

**Q4.** A user logs in right after two failures. Which step resets the state?  
**Answer:** `doOnNext(result -> limiter.recordSuccess(username))` in the decorator after the manager returns a successful authentication. Never reset before verifying the password.

**Q5.** Why is the demo's `ConcurrentHashMap.compute` still insufficient for many concurrent requests?  
**Answer:** Per-key updates themselves are atomic, yet **`isBlocked` and `delegate.authenticate` run before failures are recorded**. Multiple requests can pass the gate simultaneously; production needs atomic reservations/in-flight caps.

**Q6.** Why is a single Redis `INCR` with TTL not always enough?  
**Answer:** You must handle windows, cooldowns, in-flight limits, reset conditions, and races together, typically via scripts/transactions. Also ensure TTL/cardinality bounds and failover.

**Q7.** What is the risk of returning `"username alice is locked for 2 minutes"` explicitly?  
**Answer:** It reveals account existence and login state, aiding account enumeration and denial of service. Use generic messages and safe support/recovery channels.

**Q8.** Why must you combine `@SpringBootTest`, `WebTestClient`, and `csrf()` in this exercise?  
**Answer:** Because you need to execute the real form authentication/filter chain with a valid POST. `csrf()` avoids 403s at the CSRF layer so the test actually exercises the password limiter.

**Q9.** If the authentication provider times out, is that a wrong password that should increment the counter?  
**Answer:** No. Categorize infrastructure incidents separately with alerts and appropriate errors; never cause account lockouts from outages.

**Q10.** Is locking an account longer always better?  
**Answer:** No. Long locks can be exploited by attackers to cause DoS. Balance protection and availability: windows, cooldowns, progressive controls, MFA, recovery, and risk policies.

**Q11.** Why can't Basic authentication and form login automatically share the same failure handler/flow?  
**Answer:** Form login typically uses sessions, CSRF, and browser redirects; HTTP Basic typically uses 401 challenges. Rate limits can be shared at the identity service, while HTTP responses and authentication flows differ.

**Q12.** What must be tested when running three application instances?  
**Answer:** Shared counters, atomic updates, behavior across node restarts, no budget overruns from concurrent requests, and behavior when central storage times out.

## 16. Implementation Checklist

- [ ] Account-wide/IP-wide/account-IP policies are aligned with the risk team and SLOs.
- [ ] Thresholds, observation windows, cooldowns, resets, and concurrent-attempt limits are explicit.
- [ ] The gate runs **before** password verification; failed/success outcomes are recorded afterwards.
- [ ] Bad credentials, locked state, service failures, CSRF, and authorization are cleanly separated.
- [ ] Responses and timing do not reveal account existence/nonexistence in an exploitable way.
- [ ] Browser forms have CSRF and appropriate cookie/session policies.
- [ ] Passwords are stored as strong hashes, with no real credentials in code/logs/traces.
- [ ] Trusted proxy/IP handling and IPv6/NAT cases have been tested.
- [ ] Multi-instance deployments use a shared store with TTLs, atomic updates, and bounded cardinality.
- [ ] Redis/gateway failure handling and alerts are in place.
- [ ] Abuse metrics are collected without logging raw secrets.
- [ ] MFA/step-up, false-lockout handling, and safe recovery are available.
- [ ] Tests cover unit boundaries, integration POST login, concurrency, distributed behavior, security, and usability.
- [ ] The single-JVM in-memory demo is never deployed verbatim to production.

## 17. Summary and Reference Documentation

**Remember:** Effective login throttling must stop **actual password verification attempts**, not merely count errors. For Spring Security WebFlux form login, you can use a `ReactiveAuthenticationManager` decorator to check an account limiter before the delegate, update state on authentication success/bad credentials, and keep responses generic with `ServerAuthenticationFailureHandler`. Production additionally requires source-level limits, distributed state, atomic reservations, CSRF/session security, MFA, anti-enumeration, and operational recovery.

**Official sources:**

- OWASP Authentication Cheat Sheet – Login Throttling, Account Lockout, Authentication Responses: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP Credential Stuffing Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html
- OWASP Forgot Password Cheat Sheet – anti-user-enumeration and rate limiting: https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html
- Spring Security 6.5 – WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 – `ServerHttpSecurity.FormLoginSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html
- Spring Security 6.5 – `AuthenticationWebFilter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Security – WebFlux CSRF protection: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security – Testing CSRF with WebTestClient: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html
- Spring Security – Password Storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Boot 3.5.16 release announcement (end of OSS support): https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
