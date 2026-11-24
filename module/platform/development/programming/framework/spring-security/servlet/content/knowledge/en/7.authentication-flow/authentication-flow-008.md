# AuthenticationException and Invalid Account States

> **Scope:** Spring Security 6 on the **Servlet stack** (Spring Boot 3.x, Java 17+). This lesson explains how authentication errors are reported via `AuthenticationException`, account states in `UserDetails`, verification steps in `DaoAuthenticationProvider`, and how errors are translated into HTTP responses in form login, HTTP Basic, or custom login flows. Clearly distinguish **failure to authenticate identity** from **insufficient access permissions**.

## 1. Failed Authentication Does Not Mean Only a Wrong Password

When an application receives a username/password, the system may reject login for several reasons:

- Wrong password, nonexistent username, or invalid credentials.
- Account is **locked**, e.g., locked by security policy.
- Account is **disabled**, e.g., not yet activated or turned off by an administrator.
- **Account expired**, even though the password might still be correct.
- **Credentials expired**, e.g., policy forces a password change.
- No provider supports the authentication token, or the identity lookup service failed.

Spring Security represents these situations using subclasses of `org.springframework.security.core.AuthenticationException`. Exceptions may carry detailed info for internal layers, yet **should not be automatically exposed verbatim to clients**: revealing "account exists but is locked" can help attackers enumerate accounts.

Key point: a string like "login failed" is a **business outcome**, whereas `AuthenticationException` is a **technical signal** for the authentication mechanism and HTTP security to handle failure.

## 2. Key Exceptions and Their Meanings

`AuthenticationException` is the root exception class for Spring Security authentication failures (an unchecked exception). Common branches include:

```text
AuthenticationException
├── BadCredentialsException
├── UsernameNotFoundException
├── AuthenticationCredentialsNotFoundException
├── InsufficientAuthenticationException
├── ProviderNotFoundException
├── AuthenticationServiceException
│   └── InternalAuthenticationServiceException
└── AccountStatusException
    ├── LockedException
    ├── DisabledException
    ├── AccountExpiredException
    └── CredentialsExpiredException
```

These are **representative branches**, not every subclass in the library.

| Exception Class | Primary Meaning | Example |
| --- | --- | --- |
| `BadCredentialsException` | Provided credentials were rejected | Wrong password, or nonexistent username masked behind it |
| `UsernameNotFoundException` | `UserDetailsService` could not find the user | `loadUserByUsername("missing")` finds no record |
| `LockedException` | Account is currently locked | `UserDetails.isAccountNonLocked() == false` |
| `DisabledException` | Account is not enabled / has been disabled | `UserDetails.isEnabled() == false` |
| `AccountExpiredException` | Account validity period has expired | `UserDetails.isAccountNonExpired() == false` |
| `CredentialsExpiredException` | Account credentials have expired | `UserDetails.isCredentialsNonExpired() == false` |
| `AuthenticationCredentialsNotFoundException` | No suitable authentication found in the context when required | A call requires credentials yet no matching context exists |
| `InsufficientAuthenticationException` | Current authentication level is insufficient for the operation | Mechanism requires stronger authentication, per configuration |
| `ProviderNotFoundException` | No `AuthenticationProvider` supports the submitted token | `ProviderManager` receives an `Authentication` type unsupported by any provider |
| `AuthenticationServiceException` / `InternalAuthenticationServiceException` | Processing failure in authentication infrastructure | User store error, identity query failed, provider could not complete |

**Do not lump infrastructure failures into "wrong password" in internal diagnostics.** For clients, a safe, non-disclosing message may be appropriate, while internal logs and metrics must distinguish service outages from invalid login credentials.

### The AccountStatusException Branch

The four exceptions `LockedException`, `DisabledException`, `AccountExpiredException`, and `CredentialsExpiredException` all extend `AccountStatusException`. They indicate **account status does not satisfy policy**, distinct from `BadCredentialsException` for credential verification.

If you need to catch and handle them by group inside an internal service:

```java
try {
    Authentication result = authenticationManager.authenticate(requestToken);
    // Process after obtaining a successful Authentication.
} catch (AccountStatusException exception) {
    // Account is locked, disabled, or account/credentials expired.
} catch (BadCredentialsException exception) {
    // Invalid credentials or user not found under hiding policy.
} catch (AuthenticationServiceException exception) {
    // Infrastructure / authentication service failure: needs telemetry and incident handling.
}
```

This is an **illustrative snippet inside a method**, not a standalone Java program; `requestToken` is an unauthenticated `Authentication`, and `authenticationManager` is an injected dependency. In real code, each `catch` must decide the appropriate error response or routing while preserving security rules.

## 3. Four UserDetails States Checked by the DAO Provider

Spring Security models an account's login eligibility on `UserDetails` with four flags:

| `UserDetails` Flag | Value Allowing Login | When `false`, Typical Error |
| --- | --- | --- |
| `isAccountNonLocked()` | `true` | `LockedException` |
| `isEnabled()` | `true` | `DisabledException` |
| `isAccountNonExpired()` | `true` | `AccountExpiredException` |
| `isCredentialsNonExpired()` | `true` | `CredentialsExpiredException` |

Property names can occasionally confuse: `isAccountNonLocked() == true` means **not locked**, while `isCredentialsNonExpired() == false` means **credentials have expired**. These booleans reflect state supplied by the **application/`UserDetailsService`**; Spring Security does not decide on its own when an account or password expires unless you build the corresponding data and rules.

Example translating application data into `UserDetails` state:

```java
UserDetails principal = User.withUsername("han")
        .password(passwordEncoder.encode("study123"))
        .roles("USER")
        .accountLocked(true)
        .build();
```

This is an illustrative snippet in an environment with Spring Security's `PasswordEncoder` and `User`. Account `han` remains locked until administrative logic updates the status data; the encoder only processes passwords and **does not** decide unlocking.

### Verification Order in DaoAuthenticationProvider

For username/password authentication through `DaoAuthenticationProvider`, the typical flow is:

1. `AuthenticationManager` selects a provider supporting `UsernamePasswordAuthenticationToken`.
2. `DaoAuthenticationProvider` calls `UserDetailsService.loadUserByUsername(...)` to fetch `UserDetails`.
3. `AbstractUserDetailsAuthenticationProvider` runs **pre-authentication checks**: account is non-locked, enabled, and non-expired. If any check fails, it throws `LockedException`, `DisabledException`, or `AccountExpiredException`.
4. The provider checks the supplied password against the password hash via `PasswordEncoder.matches(...)`. A wrong password yields `BadCredentialsException`.
5. It runs the **post-authentication check** for non-expired credentials. If failed, it throws `CredentialsExpiredException`.
6. Only when all checks succeed does the provider create/return an authenticated `Authentication` with the appropriate principal and authorities.

```text
UsernamePasswordAuthenticationToken (unauthenticated)
            |
            v
        ProviderManager
            |
            v
   DaoAuthenticationProvider
            |
   UserDetailsService.loadUserByUsername(...)
            |
   +--> Unknown username? --> typically BadCredentialsException externally
            |
   +--> Locked?          --> LockedException
   +--> Disabled?        --> DisabledException
   +--> Account expired? --> AccountExpiredException
            |
   PasswordEncoder.matches(rawPassword, encodedPassword)
            |
   +--> Mismatch?        --> BadCredentialsException
            |
   Credentials expired?  --> CredentialsExpiredException
            |
            v
     Successful Authentication
```

**Order matters:** in the default `DaoAuthenticationProvider`, locked/disabled/account-expired checks occur **before** password verification; the expired-credentials check occurs **after** password verification. Thus an account that is both locked and given a wrong password can throw `LockedException`. Do not assume the first exception always confirms the caller knew the password.

This flow describes the standard DAO provider; custom `AuthenticationProvider`s, LDAP, OAuth2, MFA, or custom check configurations may follow different rules.

## 4. Why Is UsernameNotFoundException Often Turned into BadCredentialsException?

`UserDetailsService.loadUserByUsername(...)` can throw `UsernameNotFoundException` when a username is missing. However, `AbstractUserDetailsAuthenticationProvider` enables `hideUserNotFoundExceptions` by default, so at the authentication boundary it typically converts this error into `BadCredentialsException`.

Two cases:

```text
Input: username=han, password=WrongPassword
    -> user exists but PasswordEncoder.matches(...) == false
    -> BadCredentialsException

Input: username=doesNotExist, password=AnyValue
    -> UserDetailsService throws UsernameNotFoundException
    -> provider hides account existence info
    -> BadCredentialsException
```

This masking makes it harder for clients to distinguish "wrong username" from "wrong password". Even if a provider preserves a distinct internal exception, the **external message should stay generic**, such as "Invalid login credentials". If you must inform users about locked accounts, design a safe recovery flow with identity verification and account-enumeration defenses.

Do not set `setHideUserNotFoundExceptions(false)` merely to display "username does not exist" to clients. When you need data for investigation, use server-side telemetry and access-controlled logging policies.

## 5. How Does AuthenticationException Differ from AccessDeniedException?

The same protected endpoint can reject a request at **two stages**:

- **Authentication:** the system has not established an eligible identity. `AuthenticationException` arises from the login attempt or missing required authentication.
- **Authorization:** the identity is authenticated yet lacks permission to perform the requested action. `AccessDeniedException` belongs to authorization and is **not** a subclass of `AuthenticationException`.

| Scenario | Primary Handling Type | Typical HTTP Status (Config-Dependent) |
| --- | --- | --- |
| No credentials on an HTTP Basic API | Authentication required via `AuthenticationEntryPoint` | **401** with `WWW-Authenticate` |
| Wrong username/password or invalid account status in HTTP Basic | Authentication failure, routed through the appropriate entry point | **401** |
| Form login with wrong password | Handled by `AuthenticationFailureHandler` | Redirect to error page or custom response |
| Logged in yet lacking role for URL | `AccessDeniedException`, `AccessDeniedHandler` | **403** |
| POST request violating CSRF | Rejected by the CSRF filter | Usually **403**, even before reaching a controller |
| Provider or user store system failure | Infrastructure authentication error | Depends on framework/handler; do not treat as wrong password |

**You cannot infer solely from an exception name that every application returns the same HTTP status.** Form login may redirect; HTTP Basic usually returns 401; custom REST controllers may catch and return custom statuses. Moreover, `ExceptionTranslationFilter` can handle an `AuthenticationException` or `AccessDeniedException` thrown downstream of it, routing to the entry point or denied handler; `BasicAuthenticationFilter` also has its own authentication failure path.

A practical rule of thumb: **401** means appropriate credentials are required to authenticate for the resource; **403** means the server refuses the request under current policy (typically insufficient permissions or CSRF). This is a common interpretation, **not a one-to-one mapping** from Java exception classes to HTTP status codes.

## 6. Runnable Spring Boot Example: Each Account State and Exception

The example uses **Java 17+, Spring Boot 3.3.5, Spring Security 6.x, Gradle 8.5**. We create five in-memory accounts sharing the same test password to isolate error causes: one normal account, one locked, one disabled, one account-expired, and one credentials-expired.

The app exposes `GET /public` and `GET /me`. With HTTP Basic, `/me` returns the username only when the user passes authentication. Tests verify both the **Java exception types from `AuthenticationManager`** and **safe HTTP 401** responses for invalid accounts.

### 6.1. Project Structure

```text
account-status-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    SecurityConfig.java
    DemoController.java
  src/test/java/demo/
    AuthenticationStatusTest.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'account-status-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 6.2. Main Application Class

File `src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 6.3. Authentication Configuration and Five Accounts

File `src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        String encodedPassword = encoder.encode("study123");

        UserDetails active = User.withUsername("active")
                .password(encodedPassword)
                .roles("USER")
                .build();

        UserDetails locked = User.withUsername("locked")
                .password(encodedPassword)
                .roles("USER")
                .accountLocked(true)
                .build();

        UserDetails disabled = User.withUsername("disabled")
                .password(encodedPassword)
                .roles("USER")
                .disabled(true)
                .build();

        UserDetails accountExpired = User.withUsername("accountExpired")
                .password(encodedPassword)
                .roles("USER")
                .accountExpired(true)
                .build();

        UserDetails credentialsExpired = User.withUsername("credentialsExpired")
                .password(encodedPassword)
                .roles("USER")
                .credentialsExpired(true)
                .build();

        return new InMemoryUserDetailsManager(
                active, locked, disabled, accountExpired, credentialsExpired);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager manager) throws Exception {
        http.authenticationManager(manager);

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated());

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

`DaoAuthenticationProvider` explicitly receives `UserDetailsService` and `PasswordEncoder`. Exposing `AuthenticationManager` as a bean allows the same setup to be used by the HTTP security chain and in tests. The default no-arg constructor of `DaoAuthenticationProvider` exists in the Spring Security version used here; for newer versions, check the constructor API of your chosen release.

**Meaning of each account:**

| Username | Special Flag | Authentication Result with Password `study123` |
| --- | --- | --- |
| `active` | All states valid | Success |
| `locked` | `accountLocked(true)` | `LockedException` |
| `disabled` | `disabled(true)` | `DisabledException` |
| `accountExpired` | `accountExpired(true)` | `AccountExpiredException` |
| `credentialsExpired` | `credentialsExpired(true)` | `CredentialsExpiredException` |

`User.UserBuilder` provides methods expressing **negative** states (`disabled(true)`, `accountLocked(true)`, ...), whereas getters on `UserDetails` use **positive** names (`isEnabled()`, `isAccountNonLocked()`, ...). Note this naming difference.

The password `study123` is strictly for local demos. In real systems, store secure password hashes, manage secrets properly, enforce rate limiting/lockout, avoid hardcoding accounts, and use HTTPS.

### 6.4. Controller

File `src/main/java/demo/DemoController.java`:

```java
package demo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    public String currentUser(Authentication authentication) {
        return authentication.getName();
    }
}
```

`/public` is permitted publicly. `/me` requires proper authentication to reach the controller; from there you can observe which accounts pass the checks.

### 6.5. Testing AuthenticationManager and HTTP Basic

File `src/test/java/demo/AuthenticationStatusTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AccountExpiredException;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.CredentialsExpiredException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationStatusTest {

    @Autowired
    AuthenticationManager manager;

    @Autowired
    MockMvc mvc;

    private Authentication authenticate(String username, String password) {
        return manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, password));
    }

    @Test
    void activeUserAuthenticatesSuccessfully() {
        Authentication result = authenticate("active", "study123");
        assertEquals(true, result.isAuthenticated());
        assertEquals("active", result.getName());
    }

    @Test
    void lockedAccountThrowsLockedException() {
        assertThrows(LockedException.class,
                () -> authenticate("locked", "study123"));
    }

    @Test
    void disabledAccountThrowsDisabledException() {
        assertThrows(DisabledException.class,
                () -> authenticate("disabled", "study123"));
    }

    @Test
    void expiredAccountThrowsAccountExpiredException() {
        assertThrows(AccountExpiredException.class,
                () -> authenticate("accountExpired", "study123"));
    }

    @Test
    void expiredCredentialsThrowsCredentialsExpiredException() {
        assertThrows(CredentialsExpiredException.class,
                () -> authenticate("credentialsExpired", "study123"));
    }

    @Test
    void wrongPasswordAndMissingUsernameBothThrowBadCredentials() {
        assertThrows(BadCredentialsException.class,
                () -> authenticate("active", "wrong-password"));

        assertThrows(BadCredentialsException.class,
                () -> authenticate("doesNotExist", "study123"));
    }

    @Test
    void httpBasicDoesNotExposeInvalidAccountStates() throws Exception {
        for (String username : new String[] {
                "locked", "disabled", "accountExpired", "credentialsExpired"
        }) {
            mvc.perform(get("/me").with(httpBasic(username, "study123")))
                    .andExpect(status().isUnauthorized());
        }
    }

    @Test
    void httpBasicSeparatesAnonymousAndValidUser() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));

        mvc.perform(get("/me"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/me").with(httpBasic("active", "study123")))
                .andExpect(status().isOk())
                .andExpect(content().string("active"));
    }
}
```

**Expected results with this configuration:** 8 tests **PASS**; both `authenticate("active", "wrong-password")` and `authenticate("doesNotExist", ...)` throw `BadCredentialsException`. The four account states produce their distinct Java exceptions at the Java API yet all return **401** via HTTP Basic in the example.

The HTTP tests run through the Spring Security filter chain configured on `MockMvc` by Spring Boot; no real network requests are needed. Do not use `@WithMockUser` in these tests because that annotation pre-populates an authentication in the context and skips the username/password verification under test.

### 6.6. Running the Program

Install JDK 17+ and a compatible Gradle version, such as Gradle 8.5. Run inside `account-status-demo`:

```bash
gradle test
gradle bootRun
```

If the project has a Gradle wrapper, use `./gradlew test` and `./gradlew bootRun` on macOS/Linux, or `.\gradlew.bat test` and `.\gradlew.bat bootRun` on Windows PowerShell.

In another terminal, run sequentially:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u active:study123 http://localhost:8080/me
curl -i -u locked:study123 http://localhost:8080/me
curl -i -u disabled:study123 http://localhost:8080/me
curl -i -u accountExpired:study123 http://localhost:8080/me
curl -i -u credentialsExpired:study123 http://localhost:8080/me
curl -i -u doesNotExist:study123 http://localhost:8080/me
```

With default HTTP Basic in the demo, expected outcomes are:

| Call | HTTP status | Body on success |
| --- | --- | --- |
| `GET /public` (anonymous) | **200** | `public` |
| `GET /me` (anonymous) | **401** | — |
| `GET /me` (active, valid password) | **200** | `active` |
| `GET /me` (locked) | **401** | — |
| `GET /me` (disabled) | **401** | — |
| `GET /me` (accountExpired) | **401** | — |
| `GET /me` (credentialsExpired) | **401** | — |
| `GET /me` (nonexistent username) | **401** | — |

Exact error headers/bodies are produced by the entry point and server; do not try to guess byte-for-byte payloads. **Key takeaway:** the Java API can distinguish exact causes for auditing/remediation, while public endpoints should not emit detailed messages that leak account states.

## 7. When Writing Custom Login, How Should AuthenticationException Be Handled?

A controller/service calling `AuthenticationManager` directly must separate the **success flow** from the **error flow**:

```text
Login request
    |
    v
AuthenticationManager.authenticate(...)
    |
    +-- success -> valid Authentication
    |              -> apply session strategy / context persistence if needed
    |              -> return success response
    |
    +-- AuthenticationException -> do not establish a logged-in session
                                    -> record safe server-side event/metric
                                    -> return generic error per public contract
```

Never write:

```java
// SECURITY FLAW: accidentally treats every exception as a successful login.
try {
    Authentication authentication = manager.authenticate(token);
    SecurityContextHolder.getContext().setAuthentication(authentication);
} catch (AuthenticationException ignored) {
    return "ok";
}
```

This snippet illustrates an anti-pattern only and **is not standalone Java code**. Swallowing errors misleads the client into thinking it is logged in; if a prior request left an old context, state can become corrupted. On failed login, follow the system's policy for preserving/clearing prior sessions and contexts, and never persist an authentication from a failed request.

A JSON controller can follow this strategy:

- **Client side:** a generic error such as "Invalid login credentials or account cannot be used", status 401 per API contract; never return `exception.getMessage()` or subclass names in the public body.
- **Server side:** structured logs with an internal error code, correlation ID, and username normalized/masked per policy; never log passwords or raw tokens. Emit metrics to detect mass account lockouts or identity store outages.
- **Infrastructure errors:** distinguish `AuthenticationServiceException` in observability/alerting; depending on design, return a server error or service unavailable instead of treating it as a wrong password. Even if returning the same external body to prevent enumeration, operations must still distinguish outages.
- **Recovery flows:** "forgot password", unlock, and account activation must verify identity and enforce rate limits; never grant access merely because the client submitted a valid username.

With Spring Security `formLogin`, `AuthenticationFailureHandler` is the standard extension point after authentication failure, normally redirecting to an error page or returning a custom response. With HTTP Basic, `AuthenticationEntryPoint` usually sends 401 and a challenge. With custom REST login, your controller or filter must explicitly translate `AuthenticationException` into a contract-compliant response; do not assume every exception is caught at the right spot by `@ControllerAdvice` or `ExceptionTranslationFilter`.

## 8. Account States in a Real Database

`UserDetails` flags must have a **source of truth** in the application. A users table might include:

```text
username
password_hash
enabled
locked_until
account_expires_at
password_changed_at
password_expires_at
```

These are only illustrative fields, not a mandatory Spring Security schema. `UserDetailsService` logic can compute:

- `isEnabled()` from account activation, deactivation, or administrative decisions.
- `isAccountNonLocked()` from manual lock status or time-based lockout policy; define automatic unlock timing if using `locked_until`.
- `isAccountNonExpired()` from account lifetime limits, e.g., temporary/seasonal accounts.
- `isCredentialsNonExpired()` from password lifecycle policy, **not** naively from JWT/access-token expiration.

**Lockout on failed login attempts does not happen automatically just by using Spring Security.** You must build failed-attempt counters, rate limiting, lock triggers, race-condition handling, and recovery mechanisms. When a username does not exist, enforce anti-enumeration policies and avoid leaking status via response timing when high security is required.

**Expired passwords differ from expired tokens:** `CredentialsExpiredException` in DAO authentication typically reflects `UserDetails.isCredentialsNonExpired()`, not the default exception for an expired JWT. OAuth2/JWT mechanisms have their own token error types and processing paths.

### Should You Use AccountStatusUserDetailsChecker?

`AccountStatusUserDetailsChecker` is a utility class that checks a `UserDetails`'s status and throws the appropriate account-status exceptions. It is useful when a custom provider or flow genuinely needs account-status checking. However, `DaoAuthenticationProvider` already runs its pre/post checks; there is no need to invoke the checker again inside every controller as a login "patch".

If you write a custom `AuthenticationProvider`, you must implement the **complete** lookup, account-status checks, credential verification, error reporting, and safe `Authentication` creation. Never just return an `authenticated=true` token while skipping account-status checks.

## 9. Common Pitfalls and How to Fix Them

### 9.1. Account Is Locked Yet HTTP Response Is Still 401: Is That a Bug?

Not necessarily. HTTP Basic uses an `AuthenticationEntryPoint` that typically returns 401 for unauthenticated states, including locked/disabled accounts. Clients do not need to know the exact subclass; inspect server logs or direct `AuthenticationManager` tests to determine the internal cause.

### 9.2. Config Has `hasRole("ADMIN")` Yet a `USER` Gets 403

This is an **authorization** error: the user logged in successfully yet lacks the required authority. Do not misclassify it as `DisabledException` or `BadCredentialsException`. Check `GrantedAuthority` values and `authorizeHttpRequests`/method security rules.

### 9.3. Configured 401 for Invalid Credentials Yet POST Login Receives 403

A likely cause is CSRF: the CSRF filter blocks the POST before login logic checks credentials. Send a valid CSRF token in session/cookie apps, or design a CSRF policy fitting the architecture. **Never disable CSRF app-wide** just to make wrong-password messages show up.

### 9.4. Username Not Found Yet Exception Is BadCredentialsException

This may be the default behavior of `hideUserNotFoundExceptions` to avoid leaking account existence. Check internal logs for the distinction when permitted; never expose that detail in public responses.

### 9.5. Wrong Password AND Account Locked: Which Exception Takes Precedence?

In standard `DaoAuthenticationProvider`, pre-auth checks for locked/disabled/account-expired run before password comparison, so `LockedException` can be thrown first. With other providers or custom configurations, ordering can differ. Never treat `LockedException` as proof that the password was right.

### 9.6. Account Credentials Expired Yet an Earlier Request Still Uses the Session

`CredentialsExpiredException` belongs to the **provider re-authentication stage**. An already-authenticated session with a saved context may not call `DaoAuthenticationProvider` again on every HTTP request. If policy requires revoking sessions immediately when a password expires, add session invalidation, revalidation, or a revocation mechanism; flipping a database flag alone does not automatically invalidate existing sessions.

### 9.7. Database Connection Error Reported as Wrong Password

Do not swallow `InternalAuthenticationServiceException`/`AuthenticationServiceException` internally and emit a "wrong password" metric. Categorize identity/store failures separately to avoid false brute-force alerts and fix the root cause; public responses must still avoid leaking internal details.

### 9.8. Catching Every AuthenticationException and Returning 200

A login endpoint returning 200 on failure breaks the client-server contract and misleads UI/session logic. Use proper HTTP statuses/redirects and failure handling; ensure tests cover valid accounts, wrong passwords, nonexistent users, locked, disabled, and expired accounts.

## 10. QA Checklist for the Authentication Flow

1. **Valid password and valid account:** authenticates successfully, `Authentication.isAuthenticated()` is `true`, and expected authorities are present.
2. **Wrong password and nonexistent username:** identical generic public outcome without leaking status; internal path records the right failure type.
3. **Locked, disabled, account expired, credentials expired:** verified accurately with `AuthenticationManager`/provider tests and policy-compliant public responses.
4. **Insufficient role/permission:** test authorization separately so `AccessDeniedException` is never confused with authentication failure.
5. **CSRF and HTTP methods:** for POST login, test valid CSRF tokens, form login, and requests missing tokens; do not test only GET via HTTP Basic.
6. **Sessions/cookies/remember-me:** if an account is disabled after login, are active sessions revoked or allowed until re-authentication? Define the policy clearly.
7. **Messages and logs:** never return exception classes, passwords, hashes, stack traces, or sensitive states in responses; internal metrics distinguish bad credentials, account state, and infrastructure errors.
8. **Multi-provider testing:** if multiple `AuthenticationProvider`s exist, verify which provider handles each token and ensure no fallback path accidentally bypasses account-status checks.

## 11. Self-Check

1. **Which flag triggers `DisabledException`?** `UserDetails.isEnabled() == false` in standard DAO verification.
2. **Does `LockedException` prove the password was right?** No; the locked-account check can run before password comparison.
3. **Why does a nonexistent username receive `BadCredentialsException`?** The provider masks `UsernameNotFoundException` by default to mitigate username enumeration.
4. **Is `CredentialsExpiredException` the same as an expired JWT?** No; it normally stems from `UserDetails.isCredentialsNonExpired()`, whereas JWTs have their own lifecycle and token validation mechanisms.
5. **Is `AccessDeniedException` an `AuthenticationException`?** No; it is an authorization exception, typically resulting in 403 when an authenticated user lacks permission.
6. **Why should public APIs use generic messages for login failures?** To minimize account-existence disclosure; detailed causes can still be recorded in access-controlled server-side logs/telemetry.
7. **When using HTTP Basic, must a locked account return 403?** There is no such rule; in the demo configuration, authentication failures return 401, whereas 403 typically relates to permissions or CSRF.
8. **Does changing the `disabled` flag in the database automatically log out existing sessions?** Never assume so; you must manage session lifecycle or re-verify status when policy requires.

**Remember:** `AuthenticationException` indicates identity establishment failed. For `DaoAuthenticationProvider`, `LockedException`, `DisabledException`, `AccountExpiredException`, and `CredentialsExpiredException` reflect distinct `UserDetails` states; `BadCredentialsException` commonly covers both wrong passwords and masked nonexistent usernames. Separate internal causes for remediation while keeping public login responses safe; clearly distinguish authentication failures from authorization's `AccessDeniedException`.
