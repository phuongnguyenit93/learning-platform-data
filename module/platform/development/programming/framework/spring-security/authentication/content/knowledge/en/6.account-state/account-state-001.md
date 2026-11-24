# isEnabled and Enabled Account State

## Objectives and Context

Having a username that exists and a password that matches the hash is **not enough** to decide whether an account is permitted to log in. An account may not be activated yet, may be disabled by an administrator, locked, expired, or have expired credentials. In Spring Security, `UserDetails.isEnabled()` is one of the properties that describe **whether an account is permitted to be used**, alongside the other status flags.

This lesson belongs to the **Account State** group in the *Spring Security - authentication* module. The focus is on the meaning of `isEnabled()`, how `DaoAuthenticationProvider` checks this flag, how to map business domain states, and the limits of this mechanism once a login session or token already exists. The complete example uses **Java 17+, Spring Boot 3.x, Spring Security 6.x**, and Servlet HTTP Basic. Sections covering JWT, OAuth2, or WebFlux only clarify responsibility boundaries and are not full implementation guides for those mechanisms.

After this lesson, you can:

1. Explain `isEnabled() == true/false` and distinguish it from `isAccountNonLocked`, `isAccountNonExpired`, and `isCredentialsNonExpired`.
2. Identify which component loads the account, which component verifies the password and status, and which component produces the resulting authentication.
3. Predict `DisabledException`, `LockedException`, `AccountExpiredException`, and `CredentialsExpiredException` in a standard username/password flow.
4. Run a Spring Boot example with active, disabled, locked, expired, and credentials-expired accounts and compare `AuthenticationManager` results against HTTP `401/403`.
5. Map `ACTIVE`, `PENDING_VERIFICATION`, `DISABLED`, `SUSPENDED`, and `DELETED` states into the Spring Security contract without mixing in authorities or MFA.
6. Understand why changing an account to disabled does not automatically revoke every already-issued session/JWT, and how to test the requirement to block access after disabling.

**Key takeaway:** `isEnabled()` is **a condition checked during authentication using UserDetails**; it does not by itself prove the user has logged in, and it is not a comprehensive session or token revocation mechanism.

## 1. Which contract does isEnabled belong to?

`org.springframework.security.core.userdetails.UserDetails` represents account information returned by `UserDetailsService` or a data source used by a provider. The contract provides the username, password hash, authorities, and status flags. The relevant API surface looks like this:

~~~java
public interface UserDetails extends java.io.Serializable {
    String getUsername();
    String getPassword();
    Collection<? extends GrantedAuthority> getAuthorities();

    boolean isEnabled();
    boolean isAccountNonLocked();
    boolean isAccountNonExpired();
    boolean isCredentialsNonExpired();
}
~~~

This is an **abbreviated snippet for illustration**, not a full source file and not runnable on its own. In newer Spring Security 6.x versions, the interface's status methods may have default implementations returning `true`. Therefore, a custom `UserDetails` class that fails to map `isEnabled()` from the actual state may accidentally treat every account as active. Check the API of the version you are using and write tests for every flag.

The `isEnabled()` contract returns:

- `true`: the account is not marked disabled according to the data loaded into `UserDetails`; it **must still** pass credential checks and the other flags.
- `false`: the account is marked disabled and cannot complete authentication through the standard mechanism that checks `UserDetails` status, typically `DaoAuthenticationProvider`.

`isEnabled() == true` is **not** `Authentication.isAuthenticated() == true`. The first is a property of a user record; the second is the state of an authentication token after a flow. Simply finding a user in the database or receiving `UserDetails` from a service is not enough to grant access.

### 1.1. The four common flags

| UserDetails API | What `true` means | What `false` means | Typical exception |
| --- | --- | --- | --- |
| `isEnabled()` | Account is enabled | Account is disabled | `DisabledException` |
| `isAccountNonLocked()` | Not locked | Currently locked | `LockedException` |
| `isAccountNonExpired()` | Account is still valid | Account has expired | `AccountExpiredException` |
| `isCredentialsNonExpired()` | Password/credentials are still valid | Credentials have expired | `CredentialsExpiredException` |

The three names containing **Non** easily cause inverted logic bugs. `isAccountNonLocked() == false` means *locked*, not unlocked. In the built-in `User` class, the methods of `User.UserBuilder` use the opposite naming convention:

~~~java
UserDetails disabled = User.withUsername("bob")
    .password(encodedHash)
    .roles("USER")
    .disabled(true)
    .build();

UserDetails locked = User.withUsername("carol")
    .password(encodedHash)
    .roles("USER")
    .accountLocked(true)
    .build();

UserDetails expired = User.withUsername("dave")
    .password(encodedHash)
    .roles("USER")
    .accountExpired(true)
    .build();

UserDetails changePassword = User.withUsername("erin")
    .password(encodedHash)
    .roles("USER")
    .credentialsExpired(true)
    .build();
~~~

This is **illustrative code inside a method that has a `String encodedHash` variable**, not a standalone Java program. `disabled(true)` creates a record with `isEnabled()==false`; `accountLocked(true)` creates a record with `isAccountNonLocked()==false`. Do not map booleans straight across by name while forgetting to invert the meaning.

If an account is both locked and disabled, the provider may throw an exception at the first check it performs rather than returning all errors at once. To inspect full account states for administration, read the domain status directly instead of inferring everything from a single final exception.

### 1.2. Account status is not a role/authority

`GrantedAuthority` describes permissions, such as `ROLE_USER`, `ROLE_ADMIN`, or `SCOPE_read`. `isEnabled` indicates whether the account is eligible to log in under the relevant mechanism. These two layers are independent.

Alice has `enabled=true` and `ROLE_USER`: with the right password → she can be authenticated and call `/me`; however, `/admin` requires `ROLE_ADMIN` → `403 Forbidden`.

Bob has `enabled=false` but has `ROLE_ADMIN`: with `DaoAuthenticationProvider`, even the right password will not produce a successful login. Admin privileges do not override the disabled flag.

Do not "disable" an account by removing an important role while leaving `authenticated()` on every URL: the account might still access areas that do not require that role. Conversely, do not enable an account just to allow access to a recovery endpoint without a valid verification step.

## 2. Who checks isEnabled in Spring Security?

Typical username/password flow:

~~~text
Client sends username + password
   |
   v
Security filter (HTTP Basic / form login)
   |  creates unauthenticated UsernamePasswordAuthenticationToken
   v
AuthenticationManager (typically ProviderManager)
   |
   v
DaoAuthenticationProvider
   |
   +--> UserDetailsService.loadUserByUsername(username)
   |        |
   |        +--> returns UserDetails containing hash, flags, authorities
   |
   +--> UserDetailsChecker and account status checks
   |        |
   |        +--> disabled / locked / expired?
   |
   +--> PasswordEncoder.matches(rawPassword, storedHash)
   |
   +--> checks credentials expired and other policies
   |
   +--> Authenticated Authentication OR AuthenticationException
   |
   v
Filter: updates SecurityContext / handles HTTP errors
   |
   v
Authorization: checks URL/method access permissions
~~~

This diagram shows **responsibilities**, not a guarantee of the exact method invocation order across every Spring Security patch release. In updates aimed at mitigating timing attacks, the provider may perform the credential check even when a status pre-check detects an issue in order to reduce response time differences. However, the standard outcome remains that a disabled account is rejected.

- `UserDetailsService` only **loads** the record by username; it never calls `setAuthenticated(true)`.
- `DaoAuthenticationProvider` uses `UserDetails`, `PasswordEncoder`, and checkers to produce the authentication result.
- `AuthenticationManager.authenticate(...)` returns the result or throws `AuthenticationException`.
- The filter handles the request, exceptions, `SecurityContext`, and entry point/failure handler.
- Authorization decides whether an authenticated request holds a specific permission.

**Not every authentication mechanism uses `UserDetailsService`**. JWT resource servers, OAuth2/OIDC login, certificate/pre-auth, and custom providers may each read identity/status in their own way, so a local account's `isEnabled` flag does not automatically take effect across all of them.

### 2.1. Standard pre/post checks

`AbstractUserDetailsAuthenticationProvider` distinguishes checks **before** and **after** the credential verification stage:

| Group | Adverse condition | Result |
| --- | --- | --- |
| Pre-check | `!isAccountNonLocked()` | `LockedException` |
| Pre-check | `!isEnabled()` | `DisabledException` |
| Pre-check | `!isAccountNonExpired()` | `AccountExpiredException` |
| Post-check | `!isCredentialsNonExpired()` | `CredentialsExpiredException` |

The default checker typically checks locked before disabled, then account expired; credential expiry is checked afterward. A custom checker/provider may have a different policy. Do not use "the first exception thrown" to conclude that an account has only a single adverse state.

With the standard password mechanism, `DisabledException` extends `AccountStatusException`, which is an `AuthenticationException`. Keep this boundary clear: a disabled account is an **authentication failure**, not an authenticated user missing `ROLE_USER`.

### 2.2. Why does the right password still fail to log in?

For example: the database contains Alice with `enabled=false` and a valid password hash. `UserDetailsService` can still return Alice's full record. The provider checks the status and rejects the attempt, even though the raw password matches. Having a record ≠ successful login.

Similarly, when an account has `enabled=true` but the password is wrong, the provider throws `BadCredentialsException` instead of succeeding. If you only call:

~~~java
UserDetails user = userDetailsService.loadUserByUsername("alice");
boolean enabled = user.isEnabled();
~~~

that is merely a **data lookup**. This snippet sits inside a method with an injected service, not a standalone program. You must never construct an authenticated token from that and place it into `SecurityContextHolder` to "skip" password verification.

### 2.3. 401 or 403 response?

In a conventionally configured HTTP Basic application:

| Case | Typical result |
| --- | --- |
| Request without credentials | HTTP `401 Unauthorized` |
| Non-existent username or wrong password | HTTP `401` |
| Account disabled, locked, expired, or credentials-expired | HTTP `401` |
| Authentication succeeded but missing required authority | HTTP `403 Forbidden` |
| Authentication succeeded with sufficient permissions | HTTP `200 OK` |

With **form login** for browsers, an authentication failure may result in a `302` redirect to the login error page; a custom API entry point or failure handler can also change the response. Do not claim that a single exception class dictates the HTTP status code in every system.

**Public login does not necessarily need to reveal "This account is locked/disabled"**. The internal reason can be audited, but public-facing messages should generally be standardized so unauthenticated actors cannot enumerate existing users.

## 3. Complete Spring Boot example: enabled, disabled, locked, expired

This example runs on Spring Boot 3.x, Spring Security 6.x, and Java 17+. We use HTTP Basic and an explicit `AuthenticationManager`, allowing us to observe the same policy via Java and HTTP. No database is needed: the demo service creates `UserDetails` directly, returning **a new instance** on every lookup to avoid bugs from reusing a mutable principal after `ProviderManager` erases credentials.

### 3.1. Create the project

Create a Maven project using Spring Initializr:

- Java **17 or 21**, Spring Boot **3.x**.
- Group `com.example`, artifact `account-status`, package `com.example.demo`.
- Dependencies **Spring Web** (`spring-boot-starter-web`) and **Spring Security** (`spring-boot-starter-security`).

Create `src/main/java/com/example/demo/AccountStatusApplication.java`:

~~~java
package com.example.demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
public class AccountStatusApplication {

    public static void main(String[] args) {
        SpringApplication.run(AccountStatusApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        String storedHash = encoder.encode("demo-pass");

        // Each lookup generates a new UserDetails. Do not reuse a mutable
        // principal whose credentials may have been erased after authentication.
        return username -> switch (username) {
            case "active" -> User.withUsername("active")
                .password(storedHash).roles("USER")
                .build();

            case "disabled" -> User.withUsername("disabled")
                .password(storedHash).roles("ADMIN")
                .disabled(true)
                .build();

            case "locked" -> User.withUsername("locked")
                .password(storedHash).roles("USER")
                .accountLocked(true)
                .build();

            case "expired" -> User.withUsername("expired")
                .password(storedHash).roles("USER")
                .accountExpired(true)
                .build();

            case "credentials-expired" ->
                User.withUsername("credentials-expired")
                    .password(storedHash).roles("USER")
                    .credentialsExpired(true)
                    .build();

            default -> throw new UsernameNotFoundException("Unknown user");
        };
    }

    @Bean
    AuthenticationManager authenticationManager(
        UserDetailsService users,
        PasswordEncoder encoder
    ) {
        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityFilterChain security(
        HttpSecurity http,
        AuthenticationManager manager
    ) throws Exception {
        return http
            .authenticationManager(manager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(withDefaults())
            .build();
    }

    @Bean
    CommandLineRunner probe(AuthenticationManager manager) {
        return args -> {
            for (String name : List.of(
                "active", "disabled", "locked", "expired",
                "credentials-expired", "unknown"
            )) {
                try {
                    manager.authenticate(
                        UsernamePasswordAuthenticationToken
                            .unauthenticated(name, "demo-pass")
                    );
                    System.out.println("PROBE " + name + " => OK");
                }
                catch (AuthenticationException failure) {
                    System.out.println(
                        "PROBE " + name + " => "
                        + failure.getClass().getSimpleName()
                    );
                }
            }
        };
    }

    @RestController
    static class DemoController {

        @GetMapping("/public")
        String open() {
            return "public";
        }

        @GetMapping("/me")
        String me(Authentication authentication) {
            return "authenticated=" + authentication.getName();
        }

        @GetMapping("/admin")
        String admin() {
            return "admin";
        }
    }
}
~~~

This configuration explicitly wires a `DaoAuthenticationProvider` with `UserDetailsService` and `BCryptPasswordEncoder`, then attaches the manager to `HttpSecurity`. As a result, `CommandLineRunner` and HTTP Basic use **the exact same provider**. Every user shares the same raw demo password to keep the focus on status; the password is hashed with BCrypt at application startup. Do not ship demo passwords or the probe snippet to production.

**Why return a new User on every lookup?** Spring Security's `User` class can be used as the principal. The default provider manager supports erasing credentials upon successful authentication. If a service implementation repeatedly returns the same mutable instance containing the password hash, a principal with erased credentials can affect subsequent authentications. The demo intentionally creates a fresh instance to isolate state.

### 3.2. Run the application and inspect internal exceptions

In the Maven project directory generated by Initializr:

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell, run `.\mvnw.cmd spring-boot:run`. Once startup finishes, the lines **printed by the program** (excluding Boot logs) will look like:

~~~text
PROBE active => OK
PROBE disabled => DisabledException
PROBE locked => LockedException
PROBE expired => AccountExpiredException
PROBE credentials-expired => CredentialsExpiredException
PROBE unknown => BadCredentialsException
~~~

For `unknown`, `DaoAuthenticationProvider` normally converts the non-existent user error into `BadCredentialsException` to reduce account existence disclosure (the default configuration hides `UsernameNotFoundException`). These exceptions reflect standard provider/checker behavior when given the right password for existing users. Custom configurations or different versions must be re-tested.

The `disabled` account has `ROLE_ADMIN` yet still receives `DisabledException`. The disabled flag is enforced during **authentication**, before an authenticated identity exists for authorization to accept.

### 3.3. Send requests via HTTP Basic

In a second terminal:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u active:demo-pass http://localhost:8080/me
curl -i -u active:wrong http://localhost:8080/me
curl -i -u disabled:demo-pass http://localhost:8080/me
curl -i -u locked:demo-pass http://localhost:8080/me
curl -i -u expired:demo-pass http://localhost:8080/me
curl -i -u credentials-expired:demo-pass http://localhost:8080/me
curl -i -u unknown:demo-pass http://localhost:8080/me
curl -i -u active:demo-pass http://localhost:8080/admin
~~~

In PowerShell, if `curl` is an alias, use `curl.exe`. Expected results:

| Request | Status | Meaning |
| --- | --- | --- |
| `GET /public`, anonymous | `200` | Body `public` |
| `GET /me`, anonymous | `401` | Not authenticated |
| `GET /me`, `active:demo-pass` | `200` | Body **exactly** `authenticated=active` |
| `GET /me`, `active:wrong` | `401` | Wrong password |
| `GET /me`, `disabled:demo-pass` | `401` | `isEnabled() == false` |
| `GET /me`, `locked:demo-pass` | `401` | `isAccountNonLocked() == false` |
| `GET /me`, `expired:demo-pass` | `401` | Account expired |
| `GET /me`, `credentials-expired:demo-pass` | `401` | Credential expired |
| `GET /me`, `unknown:demo-pass` | `401` | Account not found |
| `GET /admin`, `active:demo-pass` | `403` | Authentication succeeded but missing `ROLE_ADMIN` |

Exact HTTP headers and error response bodies may vary by container/entry point. You do not need to disable CSRF to run these GET requests. Basic authentication must use **HTTPS** in real systems: Base64 does not protect passwords from eavesdropping.

### 3.4. What does this configuration NOT do?

- It does not create a form login page or an endpoint that issues JWTs.
- It does not persist statuses in a database; users only exist in the demo factory.
- It does not automatically send activation, unlock, or password reset emails.
- It does not guarantee that sessions or tokens issued before disabling are revoked.
- It does not automatically check the latest account status across every framework or custom provider.

The 401/403 results in the demo confirm behavior when **submitting a new authentication attempt** through the configured provider; do not overgeneralize this as "changing status in the DB immediately revokes every client's access."

## 4. Mapping status from the database: choose the policy before writing code

A real schema might look like:

~~~text
app_accounts
  id
  login_name
  password_hash
  status_code        ACTIVE | PENDING | DISABLED | SUSPENDED | DELETED
  locked_until
  account_expires_at
  credentials_expires_at
  updated_at
~~~

Spring Security does not automatically understand `status_code`. You must map business statuses to `UserDetails` flags using an intentional policy. For example:

| Domain status | Enabled under example policy | Meaning |
| --- | --- | --- |
| `ACTIVE` | `true` | Allows authentication attempts; valid credentials still required |
| `PENDING` / `PENDING_VERIFICATION` | `false` | Verification/activation not yet completed |
| `DISABLED` | `false` | Normal login permission halted |
| `SUSPENDED` | `false` or separate lock flag | Depends on semantics: disabled or locked |
| `DELETED` (soft delete) | `false` or return no record | Prevent account from being restored as active |

This is a policy example, **not** a mandatory mapping table. If `SUSPENDED` denotes a temporary lock, `isAccountNonLocked()==false` may express it more accurately. If an account is allowed to be used but must change its credentials, use `isCredentialsNonExpired()==false` instead of marking it disabled without reason.

### 4.1. Custom UserDetailsService for complex states

The example below is an **illustrative adapter snippet**, not a standalone runnable file: it assumes the domain defines `AccountRepository`, `AccountRecord`, `AccountStatus.ACTIVE`, and the methods shown, along with a `Clock` bean.

~~~java
@Service
public class AccountDetailsService implements UserDetailsService {

    private final AccountRepository repository;
    private final Clock clock;

    public AccountDetailsService(
        AccountRepository repository,
        Clock clock
    ) {
        this.repository = repository;
        this.clock = clock;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        AccountRecord account = repository.findByLogin(username)
            .orElseThrow(() ->
                new UsernameNotFoundException("Account not found"));

        Instant now = Instant.now(clock);

        boolean enabled =
            account.status() == AccountStatus.ACTIVE;

        boolean locked = account.lockedUntil() != null
            && now.isBefore(account.lockedUntil());

        boolean expired = account.accountExpiresAt() != null
            && !now.isBefore(account.accountExpiresAt());

        boolean credentialsExpired =
            account.credentialsExpiresAt() != null
            && !now.isBefore(account.credentialsExpiresAt());

        return User.withUsername(account.loginName())
            .password(account.passwordHash())
            .authorities(account.authorities())
            .disabled(!enabled)
            .accountLocked(locked)
            .accountExpired(expired)
            .credentialsExpired(credentialsExpired)
            .build();
    }
}
~~~

Required imports: `java.time.Clock`, `java.time.Instant`, `org.springframework.stereotype.Service`, and the relevant `org.springframework.security.core.userdetails.*` types; domain classes are defined by the project. `account.authorities()` is assumed to return `Collection<? extends GrantedAuthority>`; the hash must match the encoder.

Key points:

- `disabled(!enabled)` **intentionally inverts the boolean** from the enabled policy to the builder API.
- `lockedUntil`, `accountExpiresAt`, and `credentialsExpiresAt` are server-managed timestamps, so compare them consistently against `Clock` and write boundary tests.
- `accountExpiresAt == now` is treated as expired according to the `!now.isBefore(...)` rule in the example.
- If the domain needs account expiry separate from lock duration, do not reuse one column for both meanings.
- The adapter only **loads and maps data**. The provider/manager verifies the password and evaluates state.
- Define how username changes, duplicate logins across two tenants, or soft deletes are handled; looking up the wrong account is a security bug.

### 4.2. If using JdbcDaoImpl

`JdbcDaoImpl` is a JDBC-based `UserDetailsService` implementation whose `usersByUsernameQuery` can be customized. The traditional user query contract expects three columns in order: `username, password, enabled`. For a schema with `status_code`, one SQL pattern is:

~~~sql
SELECT
    login_name AS username,
    password_hash AS password,
    CASE WHEN status_code = 'ACTIVE'
         THEN TRUE ELSE FALSE END AS enabled
FROM app_accounts
WHERE login_name = ?;
~~~

This SQL snippet is only a **sample for databases supporting the corresponding CASE/BOOLEAN syntax**, not used in the DB-free demo project. The query binds via the `?` placeholder, never by concatenating client usernames directly.

`JdbcDaoImpl` reads enabled and authorities, but it does not automatically map every business flag such as locked-until or credentials expiry. If your application needs richer logic, a custom `UserDetailsService` is usually clearer than trying to cram everything into a single enabled expression.

### 4.3. Boundary test data

For time-based policies, unit tests should cover:

- Account status `ACTIVE`: `enabled=true`.
- `PENDING_VERIFICATION`, `DISABLED`, `DELETED`: `enabled=false`.
- `lockedUntil = now + 1s`: locked.
- `lockedUntil = now`: unlocked per the example rule.
- `accountExpiresAt = now`: expired.
- `credentialsExpiresAt = now`: credentials expired.
- Invalid or missing record: throws `UsernameNotFoundException`.
- Account with multiple adverse states: verify the intended semantics; do not force one flag to represent all of them.

`Clock.fixed(...)` keeps tests independent of wall-clock time and avoids flakiness when tests cross a second boundary.

## 5. isEnabled does not automatically revoke existing sessions

Suppose Alice logs in at 09:00, and Spring Security stores an authenticated `Authentication` in the session's `SecurityContext`. At 09:10, an admin changes the account to disabled in the database. At 09:15, Alice sends the same cookie to call `/dashboard`.

**There is no default guarantee that every request will call `UserDetailsService.loadUserByUsername(...)` or `DaoAuthenticationProvider` again to re-check `isEnabled`.** If a request simply restores the `Authentication` already stored in the session, it may remain treated as authenticated until the session/token is revoked or re-checked by a specifically designed mechanism.

Similarly, a signed JWT that is still unexpired and valid can be accepted by a resource server after the local account is disabled if the resource server only validates the signature, issuer, audience, expiry, and scopes from the token without querying account status.

### 5.1. Comparison by authentication type

| Mechanism | Where is `isEnabled` typically checked? | Does disabling in the DB immediately block old requests? |
| --- | --- | --- |
| Form login + session | During username/password login and when provider uses `UserDetails` | Not by default; existing sessions can be reused |
| HTTP Basic | Typically on each request performing password authentication | Not guaranteed across all cache/session/filter configurations |
| JWT resource server | Does not use `UserDetails.isEnabled` by default | No, if validating tokens standalone |
| OAuth2/OIDC login | Depends on integration with local account policy | Not automatically |
| Custom/pre-auth | Determined by the implementation | Must test the implementation |
| Per-request DB account re-check | Depends on custom filter/policy | Can achieve fast revocation, but must manage cache/races/failures |

### 5.2. Required steps when disabling must block access immediately

1. Update the account status in a transaction with authorization and auditing.
2. Invalidate the user's server-side sessions via the active session registry/session store, across multiple devices and multiple nodes if needed.
3. Revoke remember-me tokens, refresh tokens, and server-side stored tokens.
4. For JWT access tokens, consider short TTLs, revocation lists, per-user token versions, or introspection; choose based on SLA and architecture.
5. Invalidate related `UserDetails`, account status, and authorities caches.
6. Test with a **session/token that logged in before disabling**, not just a fresh login attempt.
7. When the DB or status service fails, never assume the account is enabled or let requests pass because the check could not run (fail-open).

Do not call `HttpSession.invalidate()` inside an admin request and assume another user's sessions were all invalidated. That call usually applies to the current session, not every device. `SessionRegistry` must also be properly configured and integrated with distributed storage when running multiple instances.

### 5.3. Caching and credential erasure

`UserCache`, repository-level caching, or an old authentication in the session can retain an enabled flag from before the admin changed the status. Define cache invalidation/TTL and the source of truth.

In addition, Spring Security erases credentials after successful authentication if the object implements `CredentialsContainer`. The `User` class can be mutated when its password is erased. Do not reuse a single mutable `User` instance as both a cached entry and an erased principal; return separate instances or design caching properly. Do not disable credential erasure just to mask an instance-reuse bug when a cleaner solution exists.

## 6. Account status, email verification, and MFA

`enabled=false` fits accounts that have not yet been activated or are disabled under general policy. However, the following flows must be kept distinct:

- **Email verification:** a user who has not verified their email may still access the email confirmation endpoint using a one-time/short-lived token without having access to the main application. Do not temporarily enable the account just so the user can verify.
- **Password reset:** a disabled account must not bypass its status by submitting a username and a client-crafted link. Recovery flows must verify ownership and use an appropriate secure token.
- **Lockout from wrong passwords:** `isAccountNonLocked` and `lockedUntil` can be used, but you need rate limiting and a policy to prevent attackers from deliberately locking out other users.
- **MFA:** `isEnabled=true` does not prove that an OTP, passkey, push approval, or additional factor has been completed. Design a dedicated authentication flow rather than flipping a single flag and treating multi-factor authentication as satisfied.
- **Offboarding / account revocation:** disabling an account should be paired with session/token revocation, not just flipping a boolean column.

Re-enabling an account (`enabled=true`) also does not guarantee login success: the password may be wrong, the account may still be locked, credentials may be expired, or another provider policy may fail. Each status must be checked independently.

## 7. Anti-enumeration security: do not leak detailed status

A public login API should not disclose by default whether a user exists and their exact status:

~~~json
{
  "error": "ACCOUNT_DISABLED",
  "username": "alice",
  "registeredEmail": "alice@example.com"
}
~~~

This is an **example payload that must not be returned by default to unauthenticated callers**. Attackers can use it to distinguish existing, active, and disabled accounts. The public message can be "Unable to sign in with the provided credentials", while internal auditing (with restricted access) records the actual status code.

Once the user has proved account ownership through a trusted recovery channel, the application can provide appropriate guidance, provided it does not turn public login into a user enumeration oracle. Never log raw passwords, cookies, bearer tokens, full authentication objects, or password hashes.

### 7.1. Security advisory CVE-2026-22746

On **April 20, 2026**, Spring disclosed **CVE-2026-22746**: in certain Spring Security versions, using `UserDetails#isEnabled`, `isAccountNonExpired`, or `isAccountNonLocked` with `DaoAuthenticationProvider` can weaken account enumeration protection via **response timing differences**.

The official advisory documents the affected branches and fixes, including **Spring Security 6.5.10** and **7.0.5**. See [Spring — CVE-2026-22746: User Attribute Enumeration when Using DaoAuthenticationProvider](https://spring.io/security/cve-2026-22746).

If your application uses these status flags, check the **actual resolved Spring Security version**, upgrade to a patched/compatible security release, and test timing-related behavior after upgrading. Hiding exception wording in the HTTP response alone is insufficient if a timing leak exists. Do not arbitrarily disable extra credential checks without assessing the risk.

### 7.2. Never accept isEnabled from the client

Data such as `X-Account-Enabled: true`, `X-User-Status: ACTIVE`, or `accountStatus` in a JSON request is client-modifiable input. **Never** use it to set the enabled flag. Status must come from a trusted DB, identity provider, or policy engine bound to the verified user and tenant.

If usernames are only unique per tenant, querying `WHERE username=?` without a trusted tenant can return the wrong account. This is an identity boundary issue; do not "fix" it by trusting an unverified `X-Tenant` header.

## 8. Common pitfalls

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| DB is disabled but new logins still succeed | `UserDetailsService` maps incorrectly, default `isEnabled` stays true, or provider skips status checks | Test the mapper and actual authentication manager |
| `disabled(true)` used, dev thinks account was enabled | Inverted naming in `User.UserBuilder` | `disabled(true)` → `isEnabled()==false` |
| User has `ROLE_ADMIN` but still gets 401 | Account disabled/locked or wrong password | Check authentication before authorization |
| Active user accesses /me, gets 403 on /admin | Missing authority | Expected by design; grant role only if genuinely valid |
| Account is locked but receives DisabledException | Overlapping adverse flags; checker order or policy | Design status clearly; inspect the full record |
| Disabled account still accesses with old cookie | Session/token not yet revoked | Design revocation and re-checks per SLA |
| Password changed but Basic login fails | Hash/encoder mismatch or expired credentials | Check `PasswordEncoder` and mapping |
| Re-enabled account still cannot log in | Cache holds disabled, still locked/expired, or wrong password | Invalidate cache, check every flag |
| Public login discloses account is disabled | Handler returns detailed exception | Use generic message, keep internal audit |
| App using JWT still accepts disabled account | JWT does not check local UserDetails by default | Use token policy/introspection/revocation |
| Multiple accounts share username across tenants | Lookup lacks tenant context | Separate identity namespaces, verify tenant source |
| Test only runs fresh login and claims instant revocation | Existing session/token was not tested | Write a test disabling mid-session |

## 9. Testing and exercises

### 9.1. Unit testing mapping and provider

At a minimum, verify statuses before/at timestamps:

- `ACTIVE` account → enabled true.
- `PENDING_VERIFICATION`, `DISABLED`, `DELETED` → enabled false per example policy.
- `lockedUntil == now + 1s` → locked; `lockedUntil == now` → unlocked.
- `accountExpiresAt == now` → expired.
- `credentialsExpiresAt == now` → credentials expired.
- Account not found in DB → `UsernameNotFoundException` in service, though public login may be converted to a generic error by the standard provider.
- Wrong password for active user → `BadCredentialsException`.
- Disabled status with right password → `DisabledException` in manager.

Example **illustrative test code**, not a standalone file (requires JUnit 5, Spring test configuration, and an injected manager):

~~~java
DisabledException thrown = assertThrows(
    DisabledException.class,
    () -> manager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
            "disabled", "demo-pass"
        )
    )
);
~~~

Corresponding imports come from JUnit `Assertions.assertThrows` and Spring Security `DisabledException` and `UsernamePasswordAuthenticationToken`. Do not call `UserDetailsService.loadUserByUsername(...)` and claim you tested authentication; that only tests lookup.

### 9.2. Scenario A — database record exists

`loadUserByUsername("alice")` returns a user with `isEnabled()==true` and a role. Is it allowed to construct an authenticated token and place it in `SecurityContextHolder` without checking the password?

**Answer:** no. A record existing does not prove the caller owns the credentials; it must go through a valid authentication mechanism.

### 9.3. Scenario B — disabled, yet session persists

Alice logged in this morning. An admin flips her status to disabled midday. Alice still accesses `/dashboard` with her old cookie. Is this necessarily a bug in `isEnabled`?

**Answer:** not necessarily. `isEnabled` is typically checked when authenticating via the provider, and does not automatically re-check old sessions. Verify the designed session invalidation or account re-check mechanism.

### 9.4. Scenario C — admin role

Bob has `ROLE_ADMIN` but `isEnabled()==false`. His password is correct. Can Bob access `/admin`?

**Answer:** no, with standard `DaoAuthenticationProvider`. Account status blocks authentication before authorization evaluates roles.

### 9.5. Scenario D — two simultaneous states

`isAccountNonLocked()==false` and `isEnabled()==false`. Why might code receive `LockedException` rather than `DisabledException`?

**Answer:** the standard checker evaluates lock before disabled. A single exception does not represent the entire account condition. Public login should also not expose this detail.

### 9.6. Scenario E — unexpired JWT

A JWT with `scope=read` has 15 minutes remaining. The local account is disabled, but the resource server only verifies the signature and `exp`. Will the token be rejected immediately?

**Answer:** not by default. You must have revocation, introspection, bounded TTL, or a specific account-status check mechanism.

### 9.7. Scenario F — custom UserDetails

In a version where default `isEnabled()==true`, a custom `UserDetails` class does not override `isEnabled`. Meanwhile the DB has `status=DISABLED`. Is that configuration safe?

**Answer:** no. The flag may stay true. You must explicitly map the status, write unit tests, and confirm the provider actually checks the flag.

## 10. Implementation checklist

- [ ] Clearly defined enabled/disabled, locked, expired, credentials-expired, pending verification, and deleted in the domain.
- [ ] `UserDetailsService` returns the right flags and does not accidentally fall back to default `true` when DB is disabled.
- [ ] `DaoAuthenticationProvider`, `PasswordEncoder`, and `AuthenticationManager` actually use the configured service/policy.
- [ ] Disabled accounts are rejected even with the right password, strong roles, or prior logins.
- [ ] Tested via HTTP: active with right password, wrong password, disabled, locked, expired, credentials-expired, non-existent username, and missing role.
- [ ] Did not conflate `401` from authentication failure with `403` from authorization failure.
- [ ] Have a plan to clear caches and invalidate sessions, remember-me, refresh tokens, and JWTs per the required revocation level.
- [ ] Account status comes from a trusted source, never from client-supplied flags or unverified tenant headers.
- [ ] No logging or leaking of sensitive info, detailed status messages, or timing differences enabling account enumeration.
- [ ] Checked Spring Security version against CVE-2026-22746 and upgraded per the corresponding advisory.
- [ ] Have a regression test for **sessions authenticated prior to disabling**, not just fresh logins.

**Conclusion:** `UserDetails.isEnabled()` determines whether an account is enabled or disabled. With standard `DaoAuthenticationProvider`, when the flag is false it will not produce a successful authentication and can throw `DisabledException`, even if the username exists and the password is correct. However, this flag does not replace credential checks, roles, or MFA, nor does it automatically revoke issued sessions or tokens. Comprehensive security requires proper status mapping, the right authentication provider, session revocation mechanisms, and multi-layered tests.

## References

- [Spring Security 6.5 — UserDetails API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetails.html)
- [Spring Security 6.5 — User and UserBuilder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/User.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html)
- [Spring Security 6.5 — AbstractUserDetailsAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html)
- [Spring Security 6.5 — UserDetailsChecker](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsChecker.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring — CVE-2026-22746: User Attribute Enumeration (April 20, 2026)](https://spring.io/security/cve-2026-22746)
