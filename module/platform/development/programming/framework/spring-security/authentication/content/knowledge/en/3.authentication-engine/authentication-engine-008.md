# AuthenticationException and Account Status Errors

> **Topic:** Authentication Engine in Spring Security Servlet. This lesson explains the `AuthenticationException` hierarchy, account status errors, where errors originate in `AuthenticationManager`/`AuthenticationProvider`, how they are translated into HTTP responses, and how to verify them with a Java 17+ Spring Boot app. The focus is username/password; for bearer tokens, OIDC, or other mechanisms, error types and protocol responses have their own specifics.

## 1. A Failed Login Can Have Many Causes

A client sends a username and password to the application. When login fails, we must distinguish at least the following cases:

1. The username does not exist in the identity source.
2. The user exists, yet the password or authentication proof is wrong.
3. The user is **disabled** by an administrator or policy.
4. The user is **locked**, potentially due to security or an administrative decision.
5. The account has **expired**.
6. Credentials have **expired**, e.g., a password change is required.
7. The identity service/database is down, so verification is impossible.
8. Login **succeeded**, yet the account lacks permission to access a specific feature.

Groups 1–7 relate to **authentication**. Group 8 is **authorization**. These groups may produce similar external responses, yet their internal causes, monitoring, and remediation actions differ.

Spring Security uses `AuthenticationException` to represent failures occurring during authentication. For user status, `AccountStatusException` subclasses pinpoint the internal reason. However, **never return raw exception names to an unauthenticated client**: returning distinct responses for non-existent username, locked username, and wrong password enables account enumeration.

### An Illustrative Scenario

Suppose account `an` is locked by policy; account `binh` is normal yet entered the wrong password. Neither request obtains a successful login `Authentication`. With an HTTP Basic API, callers typically receive **401**. Internally, the provider may throw `LockedException` for An and `BadCredentialsException` for Binh. This distinction is valuable for auditing, operations, and unlock workflows, yet is not exposed verbatim in public responses by default.

## 2. `AuthenticationException` and Key Branches to Know

`org.springframework.security.core.AuthenticationException` is an unchecked exception (extending `RuntimeException`) serving as the base for authentication failures. Implementations of `AuthenticationManager` or `AuthenticationProvider` typically throw an appropriate subclass when checks fail.

**Abbreviated** hierarchy tree:

```text
AuthenticationException
├── BadCredentialsException
├── UsernameNotFoundException
├── AccountStatusException
│   ├── DisabledException
│   ├── LockedException
│   ├── AccountExpiredException
│   └── CredentialsExpiredException
├── AuthenticationServiceException
│   └── InternalAuthenticationServiceException
├── ProviderNotFoundException
└── InsufficientAuthenticationException
```

This tree only depicts the prominent types in this lesson, not the full API. Other exceptions exist for other authentication mechanisms.

| Exception | Characteristic | What not to infer |
| --- | --- | --- |
| `BadCredentialsException` | Supplied credentials are invalid | Does not confirm the username actually exists in the system |
| `UsernameNotFoundException` | `UserDetailsService` could not find the user | Should not be forwarded verbatim to the client by default |
| `DisabledException` | User is disabled | Does not prove the password was correct |
| `LockedException` | User is locked | Does not prove the password was correct |
| `AccountExpiredException` | Validity of the account itself has ended | Does not mean the password expired |
| `CredentialsExpiredException` | Credential validity has ended | Does not mean the account is disabled |
| `AuthenticationServiceException` | Error from the authentication system | Should not be treated as user input error |
| `ProviderNotFoundException` | No provider supports the received `Authentication` type | May be a configuration/authentication-contract issue |
| `InsufficientAuthenticationException` | Trust level of authentication is insufficient | Not simply “wrong password” |

**Key separation:** `AccessDeniedException` belongs to **authorization**, not as a subclass of `AuthenticationException`. If An authenticated successfully yet lacks admin permission, that is an access-permission decision, with no reason to claim An's password was wrong.

### Java Exceptions and HTTP Statuses Are Different

Calling `authenticationManager.authenticate(request)` directly is a Java operation. On success it returns `Authentication`; on failure it throws `AuthenticationException`. HTTP statuses such as 401/403 are decided afterward by web/filter/handler components. There is no rule that “every `AuthenticationException` in every application produces the same body or status”.

## 3. Four Account Status Errors

`AccountStatusException` is the parent class for four user states commonly checked on the username/password authentication path.

### 3.1. `DisabledException` — Disabled Account

Can occur when an administrator disables an account, an account is awaiting activation by policy, or the system decides the user is not yet permitted to log in. The corresponding flag in `UserDetails` is `isEnabled()`.

Important point: a provider may check **status before** comparing the password. Therefore, observing `DisabledException` **does not prove the password was right**. A public interface should not use this to disclose “the account exists and is disabled” without information-protection controls.

### 3.2. `LockedException` — Locked Account

A lock may stem from an administrator or an anti-attack policy. The corresponding flag is `isAccountNonLocked()`. A lock may be permanent, time-bound, or require a verification workflow to unlock.

**Account locking differs from rate limiting**: Spring Security provides recognition of the locked flag and exception, yet does not automatically supply a full failed-attempt counter, 15-minute lockout strategy, distributed storage, alerts, and unlock flows. If an app needs to lock after N failures, you must design a reliable counting/state-recording mechanism with rate limits and concurrency handling.

### 3.3. `AccountExpiredException` — Expired Account

Reflects that the account's validity has ended, corresponding to `isAccountNonExpired() == false`. For example, guest accounts or seasonal accounts with an expiration date.

You do not necessarily want an authentication error for every expired subscription/contract case. If the user still needs to log in to view billing history or renew, it may need to be handled via **authorization/business rules** rather than blocking authentication for the entire account.

### 3.4. `CredentialsExpiredException` — Expired Credentials

For example, a policy requiring a password change after a set period. The corresponding flag is `isCredentialsNonExpired()`. The user still exists, yet cannot use the old credentials to establish full authentication.

This error **does not automatically generate** a change-password screen or reset flow. You must design a credential change/recovery flow with identity verification, scoped permissions, and appropriate anti-abuse measures.

### Table of Four `UserDetails` Flags

| Method | `true` means | When `false`, the checker may throw |
| --- | --- | --- |
| `isEnabled()` | Account is permitted for use | `DisabledException` |
| `isAccountNonLocked()` | Account is **not** locked | `LockedException` |
| `isAccountNonExpired()` | Account has **not** expired | `AccountExpiredException` |
| `isCredentialsNonExpired()` | Credentials have **not** expired | `CredentialsExpiredException` |

The three methods containing `Non` often cause confusion when implementing database mappings. For example, `isAccountNonLocked() == false` means **currently locked**, not “not locked”.

If multiple invalid flags apply simultaneously, the observed exception depends on checker/provider ordering. Never use that order as a business authorization rule; explicitly define effective status and policy handling strategies.

## 4. Where Do Exceptions Originate in the Authentication Engine?

A typical processing chain for username/password with `DaoAuthenticationProvider`:

```text
Request with username/password (untrusted)
             |
             v
Authentication Filter
             |
             v
AuthenticationManager (e.g., ProviderManager)
             |
             v
DaoAuthenticationProvider
             |
             +-- UserDetailsService.loadUserByUsername(...)
             |       +-- No user -> UsernameNotFoundException
             |                      (may be hidden as BadCredentialsException)
             |
             +-- Pre-credential status checks
             |       +-- locked / disabled / account expired
             |
             +-- PasswordEncoder.matches(raw, encoded)
             |       +-- Wrong -> BadCredentialsException
             |
             +-- Post-credential status checks
             |       +-- credentials expired
             |
             +-- Success -> Authenticated Authentication
                                        |
                                        v
                                 SecurityContext
                                        |
                                        v
                                Authorization
```

The flow above is the **common model** of `DaoAuthenticationProvider` and user-details checkers in Spring Security. With custom providers, caches, MFA, or token mechanisms, the steps can differ.

### Why Does Loading the Profile Still Not Mean Login Succeeded?

`UserDetailsService` loads the account, password hash, flags, and authorities from the application source. It does not verify credentials itself. When `loadUserByUsername("an")` returns a user, `an` is still only the identity the caller **claimed**; the provider must run its checks before producing a successful authentication result.

### Non-Existent Username Can Become `BadCredentialsException`

`AbstractUserDetailsAuthenticationProvider` has a `hideUserNotFoundExceptions` policy, typically **enabled by default**. When `UserDetailsService` reports no user found, the provider can convert it into `BadCredentialsException`. The goal is reducing an attacker's ability to tell “user does not exist” from “user exists with wrong password” via a single exception type.

Consequently, **catching `BadCredentialsException` does not guarantee there is a real account whose lockout counter should be incremented**. Counters and anti-attack policies require validated data and designs preventing user enumeration.

### Checkers Before/After Password Verification

In the standard DAO flow, locked/disabled/account-expired flags are checked before password verification; credential expiration can be checked after that step. This does not change the rule: a login succeeds only when all required conditions pass. Nor may you conclude credentials are valid solely from a status exception, since processing order, custom providers, and configuration variants can differ.

## 5. Distinguishing Authentication Failure from Missing Permissions

Consider an API with endpoint `GET /me` requiring login and `GET /admin` requiring `ROLE_ADMIN`:

| Request | Meaning | Typical response |
| --- | --- | --- |
| Calling `/me` with no credentials | Unauthenticated | HTTP 401/challenge in Basic |
| Sending wrong password | Authentication failed | HTTP 401 |
| Sending right password for disabled account | Authentication failed | Usually HTTP 401 in Basic |
| Authenticated yet lacking `ROLE_ADMIN` | Missing permissions | HTTP 403 |
| User store suffers network failure | Unable to process authentication | Depends on error policy; needs infra alerting |

**HTTP 401** usually requests authentication/credentials. **HTTP 403** usually indicates access denied due to permissions. Still, filters, entry points, form login, reverse proxies, and token protocols can alter representations. Never deduce the exact cause solely from a status code.

In particular, `AccessDeniedException` arises during authorization evaluation; if the request is unauthenticated or anonymous, Spring Security may **initiate the authentication process** instead of always returning 403.

## 6. How Does Spring Security Surface Exceptions to HTTP?

There are three key extension points:

### `AuthenticationEntryPoint`

Initiates an authentication scheme when a request requires authentication. With HTTP Basic, `BasicAuthenticationEntryPoint` usually returns HTTP 401 with a `WWW-Authenticate` challenge; with form login, it may redirect to the login page.

### `AuthenticationFailureHandler`

Authentication filters such as the form-login filter can directly catch authentication failures and invoke a handler. The handler decides routing, response, message, or redirect depending on the app. Therefore, **not every login error flows through `ExceptionTranslationFilter`**.

### `ExceptionTranslationFilter` and `AccessDeniedHandler`

`ExceptionTranslationFilter` translates `AuthenticationException`/`AccessDeniedException` thrown **downstream** in the filter chain to the appropriate HTTP handling path:

```text
ExceptionTranslationFilter
       |
       +-- AuthenticationException --> AuthenticationEntryPoint
       |
       +-- AccessDeniedException
                    |
                    +-- Unauthenticated/anonymous --> AuthenticationEntryPoint
                    |
                    +-- Authenticated --------------> AccessDeniedHandler
```

This filter **does not verify passwords itself**; a filter such as `BasicAuthenticationFilter` has its own authentication-failure path and can invoke `AuthenticationEntryPoint` directly.

### Why Might `@RestControllerAdvice` Fail to Catch the Error?

Security filters process requests before MVC controllers. Many authentication errors occur in the filter chain and are handled before reaching a controller, so `@ExceptionHandler(AuthenticationException.class)` inside `@RestControllerAdvice` is not a substitute for full web security handling. Choose `AuthenticationEntryPoint`, `AuthenticationFailureHandler`, or `AccessDeniedHandler` matching the error source. Controller advice still has a role for exceptions inside MVC when they genuinely fall within MVC scope.

## 7. Runnable Java 17+ Example: Directly Observing Four Statuses

The example uses Spring Boot Servlet with **Spring Web** and **Spring Security** dependencies. To observe the real exception classes, `CommandLineRunner` invokes `AuthenticationManager.authenticate(...)` directly and prints only the error type. An HTTP Basic `SecurityFilterChain` lets you observe external web response codes.

Create a Java 17+ Spring Initializr project compatible with your Spring Boot version, then create `src/main/java/com/example/autherrors/AuthErrorsApplication.java`:

```java
package com.example.autherrors;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthErrorsApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthErrorsApplication.class, args);
    }

    @Bean
    CommandLineRunner showFailures(AuthenticationManager manager) {
        return args -> {
            check(manager, "active", "demo-pass", "valid");
            check(manager, "active", "wrong", "wrong-password");
            check(manager, "unknown", "demo-pass", "unknown-user");
            check(manager, "disabled", "demo-pass", "disabled-user");
            check(manager, "locked", "demo-pass", "locked-user");
            check(manager, "expired", "demo-pass", "expired-account");
            check(manager, "stale", "demo-pass", "expired-credential");
        };
    }

    private static void check(AuthenticationManager manager,
                              String username,
                              String password,
                              String label) {
        try {
            Authentication result = manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            username, password));
            System.out.println(label + " -> AUTHENTICATED:"
                    + result.getName());
        } catch (AuthenticationException ex) {
            System.out.println(label + " -> "
                    + ex.getClass().getSimpleName());
        }
    }
}

@Configuration(proxyBeanMethods = false)
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        String hash = encoder.encode("demo-pass");

        UserDetails active = User.withUsername("active")
                .password(hash).roles("USER").build();

        UserDetails disabled = User.withUsername("disabled")
                .password(hash).roles("USER")
                .disabled(true).build();

        UserDetails locked = User.withUsername("locked")
                .password(hash).roles("USER")
                .accountLocked(true).build();

        UserDetails expired = User.withUsername("expired")
                .password(hash).roles("USER")
                .accountExpired(true).build();

        UserDetails stale = User.withUsername("stale")
                .password(hash).roles("USER")
                .credentialsExpired(true).build();

        return new InMemoryUserDetailsManager(
                active, disabled, locked, expired, stale);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users,
            PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain chain(HttpSecurity http,
                              AuthenticationManager manager)
            throws Exception {
        return http
                .authenticationManager(manager)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/ping").permitAll()
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class DemoController {

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/me")
    String me(Authentication authentication) {
        return "principal=" + authentication.getName();
    }

    @GetMapping("/admin")
    String admin() {
        return "admin";
    }
}
```

### Role of Each Part

- `UserDetailsService` holds five demo accounts. One is active and four have distinct status failures.
- `PasswordEncoder` uses BCrypt; accounts share a learning password, though in reality never use a shared default password.
- `DaoAuthenticationProvider` loads users, checks flags, and matches credentials via standard mechanisms.
- `ProviderManager` invokes that provider; an exception thrown during authentication fails that authentication attempt.
- `CommandLineRunner` calls the manager **directly**, allowing observation of subclasses before translation to HTTP. The demo does not log passwords/hashes/tokens.
- `SecurityFilterChain` uses the configured manager and protects endpoints with Basic; `/admin` requires `ROLE_ADMIN`, whereas all demo users only have `ROLE_USER`.

The demo conditions are constructed so each user has only **one** status failure, avoiding dependence on precedence order when multiple flags are invalid simultaneously.

### Running via Build Tool

For a Gradle project using the wrapper:

```bash
./gradlew bootRun
```

For Maven:

```bash
./mvnw spring-boot:run
```

On PowerShell, use `.\gradlew.bat bootRun` or `.\mvnw.cmd spring-boot:run`. Since the file depends on Spring Boot/Spring Security, it cannot be compiled with plain `javac` without the classpath/dependencies.

After startup, in addition to Spring Boot logs, `CommandLineRunner` is expected to print:

```text
valid -> AUTHENTICATED:active
wrong-password -> BadCredentialsException
unknown-user -> BadCredentialsException
disabled-user -> DisabledException
locked-user -> LockedException
expired-account -> AccountExpiredException
expired-credential -> CredentialsExpiredException
```

This output is based on `DaoAuthenticationProvider` with default settings hiding `UsernameNotFoundException`. If changing the provider, custom checkers, or user-hiding policy, the exception types may differ.

### Testing Over HTTP

In another terminal:

```bash
curl -s http://localhost:8080/public/ping
curl -s -u active:demo-pass http://localhost:8080/me
curl -i http://localhost:8080/me
curl -i -u active:wrong http://localhost:8080/me
curl -i -u disabled:demo-pass http://localhost:8080/me
curl -i -u locked:demo-pass http://localhost:8080/me
curl -i -u active:demo-pass http://localhost:8080/admin
```

If PowerShell aliases `curl` to another command, use `curl.exe`. In this application:

| Command | Observed outcome |
| --- | --- |
| `/public/ping` anonymous | Body `pong` |
| `/me` with valid credentials | Body `principal=active` |
| `/me` missing credentials | HTTP 401 |
| `/me` with wrong password | HTTP 401 |
| `/me` with disabled/locked | HTTP 401 |
| `/admin` with `active` having `ROLE_USER` | HTTP 403 |

Error headers and bodies depend on Spring Boot/Spring Security/versions/configuration, so do not rely on a specific string other than the statuses and bodies of the two success endpoints. With HTTP Basic, `WWW-Authenticate` normally accompanies 401. Basic only uses Base64, **not secret encryption**; real environments must use HTTPS.

**Comparing the two observation levels:** on the backend, `disabled-user` is `DisabledException`; on the Basic client, it is usually 401. The two facts do not contradict: the backend classifies the cause, while the HTTP endpoint enforces the disclosure policy.

## 8. Translating Database State into Proper `UserDetails`

The example used fixed flags. Real applications may store fields such as:

```text
users:
  user_id
  username
  password_hash
  enabled
  locked_until
  account_expires_at
  credentials_expires_at
```

A converter must determine `UserDetails` from a **server-managed** source. For an illustrative time-based policy, the logic:

```java
boolean enabled = user.isEnabled();
boolean accountNonLocked =
        user.getLockedUntil() == null
                || !now.isBefore(user.getLockedUntil());
boolean accountNonExpired =
        user.getAccountExpiresAt() == null
                || now.isBefore(user.getAccountExpiresAt());
boolean credentialsNonExpired =
        user.getCredentialsExpiresAt() == null
                || now.isBefore(user.getCredentialsExpiresAt());
```

This is a **design snippet**, not a self-compiling program: an entity `user`, `now`, and a time contract are needed. For a **permanent** lock flag, `locked_until` alone is insufficient; an explicit lock-state flag is also needed. `now` should come from a `Clock` or consistent time source. Clearly define boundary inclusivity of `expires_at` and time zones.

Never have `isAccountNonLocked()` return a raw `locked` flag from the DB; the method name negates the error state.

### When Does Account State Take Effect?

Normally, statuses in `UserDetails` are checked **at authentication time**. An already-created session can retain an older `Authentication`. If an admin locks an account after login, the old session **does not automatically disappear merely because the `enabled` flag changed in the DB**.

For lock/disable statuses to take effect on time, the system may need:

- Invalidate active sessions or require re-authentication.
- Appropriate token TTLs, revocation/rotation/introspection.
- Policies checking current status on high-risk operations.
- User cache controls and propagation across instances.
- Testing both new requests and sessions/tokens existing prior to the lock event.

Getting `LockedException` on a new login attempt does not guarantee all requests from old sessions are blocked.

### Failed-Login Counting Must Be Designed as Its Own Workflow

If locking after multiple failures is required, you must define the counting key (user/IP/device), time window, atomic/transactional updates, rate limits, unlocking, and avoid letting invalid info enumerate usernames. Distributed systems cannot rely on single-instance in-memory counters when consistent state is required.

Be careful: `BadCredentialsException` can also come from a **non-existent username** after exception hiding. Never automatically assume there is a real user whose counter should be incremented solely from the exception name.

## 9. Response Policy and Preventing User Information Leakage

An API might return a generic authentication error, for example:

```json
{
  "error": "authentication_failed",
  "message": "Unable to authenticate the request."
}
```

This is an application **policy template**, not default framework output. With Basic, appropriate status/challenges are needed; with form login, redirects/failure handlers apply; with OAuth2 Resource Server, token protocol rules must be followed.

### What Is User Enumeration?

If `POST /login` returns “no such username” for An yet “account is locked” for Binh, an unauthenticated actor can build a list of valid accounts. Risks also stem from differing response times, inconsistent payloads, or leaked SQL/backend errors.

A strategy:

1. **Externally:** neutral messages, revealing neither password validity nor account status without appropriate verification.
2. **Internally:** record error type, request ID/correlation ID, provider source, and status to support investigation; never log passwords or tokens.
3. **Account recovery:** use an ownership-verified workflow; more detail may be given inside a trusted channel.
4. **Anti-abuse:** rate limiting, anomaly monitoring, handling brute force and credential stuffing.
5. **Credential security:** HTTPS, standard password hashing, never log raw Authorization headers/session cookies.

It is not necessary to hide every status in every context. For instance, after verifying via an independent factor, you can guide the user to change credentials. Yet public login endpoints should not expose verbatim `LockedException` or `UsernameNotFoundException` by default.

### Customizing the Basic Entry Point to Return JSON

In `HttpSecurity` configuration, you can replace `.httpBasic(Customizer.withDefaults())` with:

```java
.httpBasic(basic -> basic.authenticationEntryPoint((request, response, ex) -> {
    response.setStatus(401);
    response.setHeader("WWW-Authenticate", "Basic realm=\"api\"");
    response.setContentType("application/json;charset=UTF-8");
    response.getWriter().write("{\"error\":\"authentication_failed\"}");
}))
```

This is an **illustrative DSL snippet**, not a standalone program. The `WWW-Authenticate` header preserves HTTP Basic's challenge requirement. Avoid putting `ex.getMessage()` directly into public JSON because internal messages may contain account or infrastructure details.

### Service Errors Must Not Be Mistaken for Wrong Passwords

`AuthenticationServiceException` or `InternalAuthenticationServiceException` reflect processing failures in the authentication service. If the database fails, log operationally and apply an appropriate response policy rather than assuming every client “typed wrong input”. A custom API might choose status 503 when the service is temporarily unavailable, yet **there is no fixed default HTTP 503 mapping** for all these exceptions.

## 10. Tracing Events and Handling Locations

To find the root cause, ask in order:

- Did the request carry credentials, and did the right filter receive them?
- Does `AuthenticationManager` have a provider supporting this token type?
- Did `UserDetailsService` or the IDP source find the user and operate properly?
- Did a checker reject due to disabled/locked/expired?
- Was the password/token verified with the right mechanism?
- Was `Authentication` returned successfully and placed into `SecurityContext`?
- If already authenticated, did authorization deny due to permissions/resource?
- Who translated the exception into a response: Basic filter, entry point, failure handler, or exception translation filter?

### Authentication Events

Spring Security provides `AuthenticationEventPublisher` and `DefaultAuthenticationEventPublisher`. When configured and wired to the right manager, events can be emitted such as:

| Exception | Typical event |
| --- | --- |
| `BadCredentialsException` | `AuthenticationFailureBadCredentialsEvent` |
| `DisabledException` | `AuthenticationFailureDisabledEvent` |
| `LockedException` | `AuthenticationFailureLockedEvent` |
| `AccountExpiredException` | `AuthenticationFailureExpiredEvent` |
| `CredentialsExpiredException` | `AuthenticationFailureCredentialsExpiredEvent` |
| `AuthenticationServiceException` | `AuthenticationFailureServiceExceptionEvent` |

Do not assume a manually created `ProviderManager` always has a publisher automatically; verify wiring. Default event mapping normally distinguishes concrete exception classes, so custom subclasses may need additional mapping configuration.

Telemetry should include standardized error type, timestamp, request/correlation ID, provider, flow type, denial decision, and HTTP status. Never record plaintext passwords, bearer tokens, session cookies, password hashes, or whole `Authentication` objects in public logs.

## 11. Focused Test Matrix

| Scenario | Verify at AuthenticationManager layer | Verify at HTTP layer |
| --- | --- | --- |
| Active user, right password | Returns authenticated `Authentication` | Protected endpoint allowed |
| Active user, wrong password | `BadCredentialsException` | Not logged in; Basic usually 401 |
| Non-existent username | Default may hide as `BadCredentialsException` | Does not disclose user existence |
| Disabled user | `DisabledException` | No new session issued |
| Locked user | `LockedException` | No new session issued |
| Expired account | `AccountExpiredException` | No new session issued |
| Expired credentials | `CredentialsExpiredException` | Guides recovery via trusted flow |
| Missing provider | `ProviderNotFoundException` or corresponding error | Does not report login success |
| DB/IDP failure | Identifies service failure | Operational alert, safe response |
| Valid login yet missing role | Authentication succeeds | Authorization denies, usually 403 |
| Locked after session existed | Old session may still hold info | Test actual revocation policy |
| Username enumeration | Compare valid/invalid usernames | Neutral public response |

When writing tests, verify **both sides**: internal exceptions/events used for investigation, and public responses sent to clients. A system returning 401 can still be broken if it issued a session before checking status, or accidentally wrote passwords to logs.

### Common Misconceptions

1. **“Every authentication failure is `BadCredentialsException`.”** False; account status, service errors, or missing providers have distinct types.
2. **“`DisabledException` proves the password was right.”** False; status may be checked before the password.
3. **“Account expired is the same as credentials expired.”** The two have different lifecycles and policies.
4. **“Setting `accountLocked(true)` makes the framework auto-count wrong attempts.”** False; counting and locking are additional policies.
5. **“`UsernameNotFoundException` is always returned intact.”** DAO provider typically hides it as `BadCredentialsException`.
6. **“`@RestControllerAdvice` catches all security filter errors.”** False; filter errors have their own handlers.
7. **“Disabling a user in the database immediately kills old sessions.”** Not guaranteed; requires explicit lifecycle management.
8. **“403 is always an authentication error.”** False; usually an authorization failure.
9. **“The exception class should be sent to the browser for the user to handle.”** Can leak username/account status.
10. **“Authentication service failed means wrong password.”** No; operational incident assessment is needed.

### Self-Check Knowledge

**Question 1.** Account is disabled, client enters a wrong password. Does `DisabledException` prove the password was right?  
**Answer:** No. Status may be checked before the password.

**Question 2.** Why can a non-existent username appear as `BadCredentialsException`?  
**Answer:** `DaoAuthenticationProvider` usually hides `UsernameNotFoundException` to prevent user enumeration.

**Question 3.** Which exception corresponds to `isCredentialsNonExpired() == false`?  
**Answer:** `CredentialsExpiredException` in the standard checker.

**Question 4.** A user with `ROLE_USER` calls `/admin` requiring `ROLE_ADMIN` and is rejected. Is this `BadCredentialsException`?  
**Answer:** No. Login may have succeeded; this is an authorization failure.

**Question 5.** To return 401 JSON for HTTP Basic, where should you customize?  
**Answer:** Basic's `AuthenticationEntryPoint`, while preserving the appropriate Basic challenge.

**Question 6.** Why should you avoid returning the exact `LockedException` type to every unauthenticated client?  
**Answer:** Because it can reveal that the account exists and its current status.

**Question 7.** A user is locked after already having a login session. Are old sessions guaranteed to be invalidated automatically?  
**Answer:** No. You need a session/token management strategy, cache controls, and status-update policies.

## 12. Core Takeaways

`AuthenticationException` describes **why a request could not be authenticated**. `AccountStatusException` subclasses distinguish **disabled, locked, expired account, or expired credentials**. `BadCredentialsException` typically reports invalid proof; `AuthenticationServiceException` reflects processing failures; `AccessDeniedException` belongs to a different group because it concerns permissions after identification.

Proper design has three layers of responsibility: **a trusted status source**, **a provider verifying and emitting the right `Authentication`/exception**, and **web handlers returning appropriate responses without leaking user info**. In addition, existing sessions/tokens and account recovery flows must be managed. A properly named exception alone cannot substitute for an entire security policy.

### Official Documentation

- [Spring Security — AuthenticationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationManager.html)
- [Spring Security — AccountStatusException API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AccountStatusException.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html)
- [Spring Security — Security Filters/ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Security — Authentication Events](https://docs.spring.io/spring-security/reference/servlet/authentication/events.html)