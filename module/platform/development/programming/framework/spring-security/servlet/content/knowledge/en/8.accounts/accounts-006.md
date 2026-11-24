# enabled, accountNonLocked, accountNonExpired, and credentialsNonExpired in Spring Security

## 1. What Are the Four Account Status Flags For?

In **Spring Security Servlet**, many applications authenticate users with username/password via a `UserDetailsService` and an appropriate `AuthenticationProvider`, typically `DaoAuthenticationProvider`. Spring Security needs to know not only **whether the password is correct** but also **whether the account/credentials are still eligible to log in**.

The `org.springframework.security.core.userdetails.UserDetails` interface provides four checks:

~~~java
boolean isEnabled();
boolean isAccountNonLocked();
boolean isAccountNonExpired();
boolean isCredentialsNonExpired();
~~~

The names can be confusing because three methods are phrased as **double negatives**: `NonLocked` means **not locked**, `NonExpired` means **not expired**. In all four cases, **`true` generally indicates a valid condition**. `false` indicates an unmet condition and typically causes `DaoAuthenticationProvider`'s username/password authentication process to reject login.

Quick reference table:

| `UserDetails` property | When `true` | When `false` | Business example |
| --- | --- | --- | --- |
| `isEnabled()` | Account is enabled | Account is disabled | Email unverified, administrator disabled account |
| `isAccountNonLocked()` | Account is not locked | Account is currently locked | Security lock due to repeated failed logins |
| `isAccountNonExpired()` | Account has not expired | Account has expired | Contractor/employee account past validity period |
| `isCredentialsNonExpired()` | Credentials have not expired | Credentials have expired | Password must be changed per policy |

**Important:** These are four conditions for **account authentication eligibility** under the `UserDetails` model. They are **not** roles/authorities and do not replace `hasRole`, `hasAuthority`, resource ownership checks, or tenant permissions.

For example, a user with `ROLE_ADMIN` but `isEnabled() == false` can still be rejected right at the authentication step. Conversely, an account with all four flags `true` that authenticates successfully is still not automatically granted access to admin-only endpoints.

## 2. Why Are the Names NonLocked and NonExpired?

There are two common data-storage styles:

- In **business databases**, developers prefer columns expressing "bad states": `locked`, `accountExpired`, `credentialsExpired`, or `disabled`. When the value is `true`, the problem exists.
- In **`UserDetails`**, three methods express "good states": `isAccountNonLocked()`, `isAccountNonExpired()`, and `isCredentialsNonExpired()`. When the value is `true`, that condition holds.

Therefore, the mapping is usually:

~~~java
// Example mapping from a "bad"-state storage model to UserDetails.
boolean enabled = !account.disabled();
boolean accountNonLocked = !account.locked();
boolean accountNonExpired = !account.accountExpired();
boolean credentialsNonExpired = !account.credentialsExpired();
~~~

This is an illustrative snippet: the `account` type/accessors represent a hypothetical model, not standalone runnable Java.

**Inversion bugs are very dangerous:** storing `locked = true` and then writing `isAccountNonLocked() { return locked; }` causes a locked account to be treated as **not locked**. Clearly document the polarity of column names and test both `true/false` states when building a custom `UserDetails`.

### How to Read the Four Expressions When Debugging

~~~text
isEnabled()                  == true  -> enabled
isAccountNonLocked()         == true  -> not locked
isAccountNonExpired()        == true  -> account not expired
isCredentialsNonExpired()    == true  -> credentials not expired

If a condition is enforced by the provider and returns false:
the username/password authentication process typically fails.
~~~

Do not collapse the four flags into a single `active` column if business logic needs to distinguish reasons and remediation steps. A temporarily locked account can be unlocked; an expired contract account requires different handling; an expired password may require a secure password-change workflow.

## 3. Distinguishing Each Flag with Real Scenarios

### 3.1. enabled: Is the Account Allowed to Log In?

`isEnabled()` is normally used for **account activation/deactivation**. Examples:

- A newly registered account that has not completed required verification.
- A user disabled by an administrator.
- An employee account no longer permitted to use the system.
- A test user or service account suspended per internal policy.

If `enabled == false`, `DaoAuthenticationProvider`'s status checker usually throws `DisabledException` during authentication. This differs from a **wrong password** and differs from authenticating successfully yet lacking a role for an endpoint.

Avoid overloading the single `enabled` flag to represent locking from failed password attempts, password expiration, and contract expiration. Those states have different meanings and recovery workflows.

### 3.2. accountNonLocked: Is the Account Currently Locked?

`isAccountNonLocked()` returning `false` means **locked**. A temporary lock model might have:

~~~text
failedLoginAttempts = 5
lockUntil = 2026-11-06T12:00:00Z
accountNonLocked = currentTime >= lockUntil
~~~

This is only an example of designing state; it is not an automatic built-in algorithm of Spring Security. **`UserDetails` and `DaoAuthenticationProvider` do not automatically implement a full policy of counting failed logins, applying temporary locks, and auto-unlocking** just because you have an `isAccountNonLocked()` method. The application itself must handle failure events, brute-force/rate-limiting defenses, lock-state persistence, and unlock conditions.

When the value is `false`, the default account-status checker normally throws `LockedException`. Account locking is only **one** measure; login endpoints still need throttling, MFA, and credential-stuffing defenses.

### 3.3. accountNonExpired: Account Usage Validity Period

`isAccountNonExpired()` returning `false` means the account has expired under policy. This is commonly tied to contract end dates, time-boxed access, temporary partner accounts, or employee lifecycle rules.

Example of a rule evaluated against the current time:

~~~java
boolean accountNonExpired =
    expiresAt == null || expiresAt.isAfter(clock.instant());
~~~

This is a hypothetical Java snippet with `Instant expiresAt` and `Clock clock`. It establishes the convention `expiresAt == null` means no expiration and `expiresAt <= now` means expired; real applications must standardize the convention and test time boundaries. If invalid, the default provider typically throws `AccountExpiredException`.

**An expired account is not the same as an expired password.** An account may need its usage validity renewed even if the password is still valid.

### 3.4. credentialsNonExpired: Are Passwords/Credentials Still Valid?

`isCredentialsNonExpired()` returning `false` means the credentials are considered **expired** under policy, usually because the password must be rotated or the credential was revoked.

Example:

~~~java
boolean credentialsNonExpired =
    passwordExpiresAt == null ||
    passwordExpiresAt.isAfter(clock.instant());
~~~

This illustrates a time-based condition, not an automatic feature of `UserDetailsService`. When the flag fails, default `DaoAuthenticationProvider` may throw `CredentialsExpiredException`. Key point: a **correct password** is not enough, because credentials can match by hash yet still be past due.

If the system uses API keys, JWTs, OAuth2 access tokens, or passkeys instead of username/password, do not assume this flag is automatically enforced on every token check. It only applies when **the active authentication provider actually checks `UserDetails` and those flags**.

## 4. Where Are the Four Flags Checked in the Authentication Flow?

In a common Servlet username/password setup:

~~~text
Client sends username + password
          |
          v
Authentication filter (HTTP Basic or form login)
          |
          v
AuthenticationManager (typically ProviderManager)
          |
          v
DaoAuthenticationProvider
          |
          +--> UserDetailsService.loadUserByUsername(username)
          |       -> UserDetails with password hash, authorities, 4 flags
          |
          +--> Check account status before password verification
          |       accountNonLocked / enabled / accountNonExpired
          |
          +--> Verify password via PasswordEncoder
          |
          +--> Check credentialsNonExpired
          |
          v
Authentication succeeded
          |
          v
Spring Security authorization
          -> authenticated? sufficient role/authority? resource permitted?
          |
          v
Controller and service if request is permitted
~~~

**The order above is the typical model of `AbstractUserDetailsAuthenticationProvider`/`DaoAuthenticationProvider` in Spring Security 6**, not a guarantee that every custom `AuthenticationProvider` processes things in this exact sequence.

For default `UserDetails`-based providers, status checks are implemented using `UserDetailsChecker`. Pre-password checks normally cover `isAccountNonLocked`, `isEnabled`, and `isAccountNonExpired`; post-password checks cover `isCredentialsNonExpired`. If multiple flags are invalid at once, which specific exception is thrown depends on check order; never infer from one exception that the other flags are valid.

### Common Exceptions

| Unmet condition | Typical exception | Meaning |
| --- | --- | --- |
| `isEnabled() == false` | `DisabledException` | Account is disabled |
| `isAccountNonLocked() == false` | `LockedException` | Account is locked |
| `isAccountNonExpired() == false` | `AccountExpiredException` | Account has expired |
| `isCredentialsNonExpired() == false` | `CredentialsExpiredException` | Credentials have expired |
| Wrong password | `BadCredentialsException` | Credentials do not match |
| Username does not exist | Usually masked as `BadCredentialsException` under default provider config | Avoids easily revealing user existence |

These exceptions belong to `AuthenticationException`. The HTTP-layer handler/entry point determines the response sent out. With HTTP Basic in the example below, login failures typically lead to **401 Unauthorized**. With form login, it typically redirects back to the login page with an error state; do not assume every provider always returns 401 or exposes exception details to clients.

### Authentication vs Authorization

An account with all valid flags and the right password can authenticate successfully. Afterward, `AuthorizationFilter` or method security still checks:

- `.authenticated()`: identity has been authenticated per policy.
- `.hasRole("ADMIN")`: must hold the corresponding authority (default `ROLE_ADMIN`).
- Resource-level permissions: only view/edit data belonging to an authorized user or tenant.

Similarly, having `ROLE_ADMIN` in a disabled `UserDetails` does not cause the provider to skip `isEnabled()`. **Account status** determines whether the user can authenticate via this mechanism; **authorities** determine what an authenticated user may do.

## 5. Built-In User Class and Inverted Builder Flags

Spring Security provides `org.springframework.security.core.userdetails.User`, a built-in `UserDetails` implementation constructible via a builder:

~~~java
UserDetails user = User.withUsername("alice")
    .password(encodedPassword)
    .roles("USER")
    .disabled(false)
    .accountLocked(false)
    .accountExpired(false)
    .credentialsExpired(false)
    .build();
~~~

This snippet requires `UserDetails`, `User`, and an `encodedPassword` variable inside a Java class; see the complete runnable example below. Notice **the builder names have opposite polarity from the getters**:

| User builder setter | When called with `true` | Corresponding UserDetails method |
| --- | --- | --- |
| `disabled(true)` | Disables account | `isEnabled() == false` |
| `accountLocked(true)` | Locks account | `isAccountNonLocked() == false` |
| `accountExpired(true)` | Marks account expired | `isAccountNonExpired() == false` |
| `credentialsExpired(true)` | Marks credentials expired | `isCredentialsNonExpired() == false` |

When status flags are omitted in the builder, a normal `User` object is built in an eligible state for authentication (`UserDetails` flags are `true`). When you set `accountLocked(true)`, do not misread it as `isAccountNonLocked() == true`.

If you build a custom `UserDetails` from a database entity, use clear property names or comments explaining the negated relationship. Never copy the method name and return a `locked` property while forgetting `!`.

## 6. Runnable Spring Boot 3 / Spring Security 6 Example

This example creates **five accounts with the same valid password**, differing only in their status flags. Consequently, HTTP responses show why a valid password is not enough when an account is locked, disabled, or expired.

The application uses **Java 17+, Maven, Spring MVC, HTTP Basic**, and `InMemoryUserDetailsManager`. Sample accounts are strictly for local learning; passwords are BCrypt-encoded when creating the bean. In real products, passwords must be managed and stored securely, HTTP Basic requires HTTPS, and users normally come from an appropriate identity store/database.

### 6.1. Project Structure

~~~text
account-flags-demo/
├── pom.xml
└── src/main/java/com/example/accountflags/
    ├── AccountFlagsApplication.java
    ├── SecurityConfig.java
    └── AccountController.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>account-flags-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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
~~~

**`src/main/java/com/example/accountflags/AccountFlagsApplication.java`**

~~~java
package com.example.accountflags;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AccountFlagsApplication {
    public static void main(String[] args) {
        SpringApplication.run(AccountFlagsApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/accountflags/SecurityConfig.java`**

~~~java
package com.example.accountflags;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        String encodedPassword = encoder.encode("demo-pass");

        return new InMemoryUserDetailsManager(
            User.withUsername("active")
                .password(encodedPassword)
                .roles("USER")
                .build(),

            User.withUsername("disabled")
                .password(encodedPassword)
                .roles("USER")
                .disabled(true)
                .build(),

            User.withUsername("locked")
                .password(encodedPassword)
                .roles("USER")
                .accountLocked(true)
                .build(),

            User.withUsername("accountExpired")
                .password(encodedPassword)
                .roles("USER")
                .accountExpired(true)
                .build(),

            User.withUsername("credentialsExpired")
                .password(encodedPassword)
                .roles("USER")
                .credentialsExpired(true)
                .build()
        );
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
~~~

**`src/main/java/com/example/accountflags/AccountController.java`**

~~~java
package com.example.accountflags;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        return "hello " + authentication.getName();
    }
}
~~~

### 6.2. Mechanics Occurring in the Example

1. The `/me` endpoint requires authentication due to `anyRequest().authenticated()`.
2. HTTP Basic reads credentials from the header and forwards them to the authentication manager.
3. The provider looks up `UserDetails` via `InMemoryUserDetailsManager`.
4. The provider checks account-state flags, BCrypt password, and credential validity according to the provider's workflow.
5. Only user `active` has all four good conditions and the correct password.
6. `disabled`, `locked`, `accountExpired`, and `credentialsExpired` are all rejected from authentication even with the right password supplied.
7. `/public` is `permitAll()` and needs no credentials; requests may still pass through the Spring Security filter chain.

At the HTTP layer, the code intentionally does not expose `DisabledException`/`LockedException` names to clients. Specific reasons can be recorded in an internal audit system with proper access control, while client responses should stay uniform and avoid leaking account details.

### 6.3. Test Run

Requires JDK 17+ and Maven; on the first run Maven needs to download dependencies. In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

By default the server runs on `http://localhost:8080`. On Windows PowerShell, use `curl.exe` instead of the `curl` alias if needed. The `# ...` comments below are **expected results from the illustrative configuration**, not measurements taken in the current environment.

~~~bash
curl -s http://localhost:8080/public
# public OK

curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/me
# 401

curl -s -u active:demo-pass http://localhost:8080/me
# hello active

curl -s -o /dev/null -w '%{http_code}\n' -u active:wrong-pass http://localhost:8080/me
# 401

curl -s -o /dev/null -w '%{http_code}\n' -u disabled:demo-pass http://localhost:8080/me
# 401

curl -s -o /dev/null -w '%{http_code}\n' -u locked:demo-pass http://localhost:8080/me
# 401

curl -s -o /dev/null -w '%{http_code}\n' -u accountExpired:demo-pass http://localhost:8080/me
# 401

curl -s -o /dev/null -w '%{http_code}\n' -u credentialsExpired:demo-pass http://localhost:8080/me
# 401
~~~

Expected results:

| Username | Password | Status | `GET /me` |
| --- | --- | --- | --- |
| `active` | right | Four flags valid | 200, body `hello active` |
| `active` | wrong | Password hash mismatch | 401 |
| `disabled` | right | `enabled = false` | 401 |
| `locked` | right | `accountNonLocked = false` | 401 |
| `accountExpired` | right | `accountNonExpired = false` | 401 |
| `credentialsExpired` | right | `credentialsNonExpired = false` | 401 |

The 401 status comes from the example using HTTP Basic. Switching to form login means the login-processing endpoint may redirect on failed authentication; do not treat 401 as the mandatory return code for every flag across all applications.

### 6.4. Checking Status Directly via UserDetails

If you want to write a controlled test, you can load each `UserDetails` and inspect it:

~~~java
UserDetails user = userDetailsService.loadUserByUsername("locked");
System.out.println(user.isEnabled());
System.out.println(user.isAccountNonLocked());
System.out.println(user.isAccountNonExpired());
System.out.println(user.isCredentialsNonExpired());
~~~

This is a snippet for a class/test that already has `UserDetailsService userDetailsService` in scope (requires importing `UserDetails`). For `locked` in the example, the expected stdout lines in order are:

~~~text
true
false
true
true
~~~

Reading flags directly is very useful when testing mapping code from the database to `UserDetails`; however, a flag being right on the object **does not by itself prove** that every type of authentication provider or every JWT request enforces that rule.

## 7. Implementing with Real Data

### 7.1. Storing Status Clearly in the Database

A business user table might store the following fields (names illustrative only):

| Data column | Usage |
| --- | --- |
| `enabled` | User is allowed to use the account |
| `locked_until` | Lockout end timestamp; null means not locked |
| `account_expires_at` | Account expiration timestamp, nullable if perpetual |
| `credentials_expires_at` | Password/credential expiration timestamp, nullable |
| `password_hash` | Password encoded with an appropriate password encoder |
| `roles` or `authorities` | Access permissions, separate from the four status flags |

Establish time-boundary conventions: if `expiresAt == now`, the state has expired. Use `Instant`/UTC or an injected `Clock` to write deterministic tests independent of machine time.

### 7.2. Mapping Flags in UserDetailsService

When using a custom entity, you can map to the default `User`. The example below is a **code fragment demonstrating the rules**, not a standalone project because `account` and `clock` must come from repository/dependency injection:

~~~java
Instant now = clock.instant();

boolean locked = account.lockedUntil() != null
    && account.lockedUntil().isAfter(now);

boolean accountExpired = account.accountExpiresAt() != null
    && !account.accountExpiresAt().isAfter(now);

boolean credentialsExpired = account.credentialsExpiresAt() != null
    && !account.credentialsExpiresAt().isAfter(now);

UserDetails details = User.withUsername(account.username())
    .password(account.passwordHash())
    .authorities(account.authorities())
    .disabled(!account.enabled())
    .accountLocked(locked)
    .accountExpired(accountExpired)
    .credentialsExpired(credentialsExpired)
    .build();
~~~

If the repository returns authorities from an untrusted or client-provided source, normalize and verify authorities server-side; never let clients assign themselves `ROLE_ADMIN`. `lockedUntil` and `expiresAt` fields also need a secure update policy with proper auditing.

When the account does not exist, `UserDetailsService` may throw `UsernameNotFoundException`; providers usually mask this error into a generic credentials message when configured accordingly. Do not use distinct public errors per username that help attackers identify valid accounts.

### 7.3. Policies Are Not Automated by Getters Alone

The four getters can **reflect** stored policies, but they do not enforce them by themselves:

- **Failed login count:** requires a system to record failures, rate-limit, and decide when to lock/unlock.
- **Automatic account expiration:** requires timestamps/rules evaluated on load or an updated status source.
- **Password expiration:** requires rotation timestamps and a secure password-change/reset workflow.
- **Account activation:** requires email/HR verification workflows ensuring only trusted sources re-enable users.
- **Session persistence:** if a user is already logged in with an active session, changing status in the database does not necessarily terminate all existing sessions immediately.

Specifically, with session-based authentication, the application typically **does not re-invoke `UserDetailsService` and the four getters on every request** once authentication is stored in `SecurityContext`. When disabling an account must take effect immediately, consider session revocation/force logout, server-side session checks, or a revalidation policy matched to the application's risk level.

## 8. Important Limitations and Misconceptions

### 8.1. Not Every AuthenticationProvider Reads UserDetails

`DaoAuthenticationProvider` relies on `UserDetailsService`, so it uses these flags. However, an application can also use:

- JWT/Bearer tokens with `JwtDecoder` and token validation policies.
- OAuth2/OIDC login via an external provider.
- Custom-written `AuthenticationProvider`s.
- API keys, mTLS, passkeys, or other mechanisms.

With these mechanisms, **do not assume `UserDetails` methods are automatically invoked** on every request. If you want a disabled account to lose use of an already-issued JWT, you need token/session revocation policies, short token lifetimes, status lookups, or appropriate controls. Updating the `enabled` column in the database alone does not guarantee every bearer token immediately stops working.

### 8.2. User Status and HTTP Status Are Two Different Layers

Inside authentication, the four invalid flags normally cause an `AuthenticationException`. HTTP status codes depend on `AuthenticationEntryPoint`, failure handlers, and the login mechanism. For example:

- HTTP Basic typically returns **401** with a `WWW-Authenticate` header.
- Form login may **302** redirect to an error login page.
- Custom REST APIs may return generic error JSON per design.

**403 Forbidden** usually appears when an authenticated principal is denied access to a resource or due to CSRF, rather than being a fixed default HTTP code for `locked`/`disabled`. Do not reverse-infer `401 == disabled` or `403 == expired`.

### 8.3. Status Errors Must Be Handled Securely

Internally, auditing can record lock, expiration, and disable events with reason codes for support. Externally, minimize response differences that let outsiders enumerate usernames, lock states, or security policies. Never write plaintext passwords, HTTP Basic headers, or access tokens to logs. Account recovery/password reset flows must require identity verification and rate limiting.

If business rules require reporting "password expired" so the user can change their password, design an **identity-verified password-change flow**. Never simply inform the client of the detail and leave an uncontrolled reset endpoint open.

### 8.4. Do Not Replace Status with Fake Authorities

Never create `ROLE_DISABLED` or `ROLE_LOCKED` expecting `DaoAuthenticationProvider` to understand and block them automatically. Roles/authorities belong to **authorization**; the four flags belong to **account state checks** for the active provider. A system may need extra business permissions, but should never swap the roles of these layers.

## 9. Common Programming Mistakes

**Mistake 1 — Inverting the boolean:**

~~~java
// Wrong if field locked=true means currently locked.
@Override
public boolean isAccountNonLocked() {
    return locked;
}

// Correct for the field model above.
@Override
public boolean isAccountNonLocked() {
    return !locked;
}
~~~

This is a snippet of a class implementing `UserDetails`, not a standalone program. Likewise: `isAccountNonExpired()` must return whether the account is **not** yet expired, and `isCredentialsNonExpired()` returns whether credentials are **not** yet expired.

**Mistake 2 — Returning `true` for all four getters when the entity has status fields:** doing so prevents the provider from knowing a user is locked/expired/disabled. If using only the `User` builder, pass flags from the entity with the right polarity.

**Mistake 3 — Thinking the provider automatically locks a user after multiple failed logins:** getters only read state; you must build components to track login failures, rate-limit, and update lock state.

**Mistake 4 — Changing `enabled=false` and assuming existing sessions/JWTs are immediately revoked:** account status does not automatically take effect on every request across every mechanism; add appropriate revocation/revalidation policies.

**Mistake 5 — Thinking expired credentials mean a wrong password:** the password can match while `isCredentialsNonExpired()` is still false; they are usually two distinct checks.

**Mistake 6 — Using `isAuthenticated()` on `Authentication` instead of account status:** that is a property of the authentication object after authentication has produced a result, not the four `UserDetails` getters, and it does not replace account-state logic.

**Mistake 7 — Granting role ADMIN to "unlock":** access permissions do not alter `isAccountNonLocked()` for the username/password provider.

**Mistake 8 — Ignoring null/timezones on expiration timestamps:** define null conventions, UTC usage, and boundary tests. If using `isAfter(now)`, exactly at the expiration instant counts as expired.

**Mistake 9 — Exposing account status to unauthenticated callers:** avoid returning "this username exists but is locked" on public endpoints if that aids enumeration. Use generic messages or identity-verified recovery flows.

**Mistake 10 — Testing only right/wrong passwords:** test each flag set to false individually as well as combinations, test after status updates, after the user has already logged in, and across other authentication types if present.

## 10. Useful Testing Checklist

When implementing status flags in the database and integrating Spring Security, verify:

1. **Four flags true, right password** -> authentication succeeds.
2. **enabled false** -> authentication fails per the active provider.
3. **accountNonLocked false** -> authentication fails due to lock.
4. **accountNonExpired false** -> authentication fails due to account expiration.
5. **credentialsNonExpired false** -> authentication fails due to credential expiration.
6. **Four flags true, wrong password** -> authentication fails.
7. **A user with multiple invalid states** -> do not rely on the first exception to conclude there is only one issue; handle recovery from real data.
8. **Changing status while a session is active** -> verify the designed session revocation/re-authentication policy.
9. **Users with JWT/API key/OAuth2** -> verify whether that mechanism checks account status; do not blindly depend on `UserDetails`.
10. **Flipping flags back to true** -> only valid authorities and credentials gain access; never skip password and authorization checks.

If you have integration tests, use `MockMvc` or an HTTP client sending real credentials in the test environment to check status/behavior, while also unit-testing the status-mapping code. When testing account status, prioritize whether access is **allowed or denied** and whether internal reasons are managed properly; avoid coupling detailed internal exceptions to public messages unless the API contract genuinely requires it.

## 11. Self-Check Your Understanding

**Question 1.** `accountLocked = true` in the builder results in what value for `isAccountNonLocked()`?

**Answer:** `false`. The builder uses the "is locked" direction, whereas the getter answers "is not locked".

**Question 2.** A user has `ROLE_ADMIN` and the right password, yet `enabled = false`; will authentication succeed with default `DaoAuthenticationProvider`?

**Answer:** Typically no. Account status is checked during authentication, before HTTP authorization policies inspect authorities.

**Question 3.** Does `isCredentialsNonExpired() == false` mean the password hash failed to match?

**Answer:** No. The password may match while credentials have expired under policy; `CredentialsExpiredException` differs from `BadCredentialsException`.

**Question 4.** Simply declaring `isAccountNonLocked()` makes Spring Security automatically lock accounts after five wrong attempts, right?

**Answer:** No. The application must design and update its failure-counting/locking policy; the provider only reads current state when a compatible authentication mechanism checks the getter.

**Question 5.** Why does disabling a user in the database not guarantee an already-issued JWT immediately stops working?

**Answer:** Bearer tokens are typically verified via a token decoder and separate rules. If requests do not load/check `UserDetails`, the four flags are not applied automatically; you need token lifetime, revocation, or revalidation policies.

**Question 6.** Why should clients not be told specifically which account is locked on a public login screen?

**Answer:** Detailed messages help enumerate usernames and account status; separate internal auditing from public responses or use identity-verified recovery flows.

**Question 7.** An account is authenticated and all four flags are valid, yet lacks `ROLE_ADMIN`; can it access `hasRole("ADMIN")`?

**Answer:** No. Account-state flags and HTTP/resource authorization are two separate control layers.

**Quick reminder:** **The four `UserDetails` getters indicate "eligible to be used for authentication" when returning `true`: enabled, non-locked, non-expired account, non-expired credentials.** They help the provider verify login eligibility; permission to perform actions is decided afterward by authorities and business policies.