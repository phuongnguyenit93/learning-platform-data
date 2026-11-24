# UserDetailsChecker and Pre-/Post-Password Verification Checks

## 1. Reading account status at the right time in Spring Security

When an application receives a username/password, the security question is not merely **"Is the password correct?"** An account may exist with the right password yet be locked, disabled, expired, or have credentials that must be changed. Spring Security splits verification into multiple stages so it does not issue a successful `Authentication` to an ineligible account.

In a `DaoAuthenticationProvider`-based username/password flow, the **`UserDetailsChecker`** interface represents a check on *the state of a `UserDetails` loaded from the account store*. The base class `AbstractUserDetailsAuthenticationProvider` uses two extension points:

- **`preAuthenticationChecks`:** checks the account **before credential matching**. Default checks cover account lock, account disablement, and account expiration.
- **`postAuthenticationChecks`:** checks after credential matching; by default it checks **expired credentials (e.g., password)**.
- Sitting **between these two points** is `DaoAuthenticationProvider.additionalAuthenticationChecks(...)`, which typically invokes `PasswordEncoder.matches(raw, encoded)` to verify the password.

These three blocks are **not** three separate logins and are not three separate interfaces. `UserDetailsChecker` has a single method that can be used at both stages.

**Lesson objectives:** explain the four status flags, check ordering, error representation, Spring Security 6.5.11 defaults, how to extend checkers without accidentally disabling built-in protections, and how to test with a Java 17 program running against a real provider.

## 2. Placing `UserDetailsChecker` correctly in the authentication machinery

Easily confused components:

| Component | Primary contract | Responsibility |
| --- | --- | --- |
| `UserDetailsService` | `loadUserByUsername(String)` | Retrieves account info, password hash, status, and authorities from the identity store. |
| **`UserDetailsChecker`** | `void check(UserDetails)` | Inspects persistent user status and throws an exception if ineligible. |
| `PasswordEncoder` | `matches(raw, encoded)` | Verifies whether the client-submitted password matches the stored hash. |
| `DaoAuthenticationProvider` | `authenticate(Authentication)` via provider interface | Coordinates checks, password matching, and building an authenticated token on success. |
| `ProviderManager` | `AuthenticationManager.authenticate(...)` | Selects providers, handles results/exceptions, and may erase credentials on success. |
| `SecurityContext` | Holds `Authentication` | Stores the authentication result for the processing context; does not replace DB transactions or user stores. |

**`UserDetailsChecker` does not receive the user-entered password, the HTTP request, a JWT, or `UsernamePasswordAuthenticationToken`.** It only receives `UserDetails`:

```java
package org.springframework.security.core.userdetails;

public interface UserDetailsChecker {
    void check(UserDetails toCheck);
}
```

The snippet above illustrates the API signature, **not** a class you need to copy into your project: the interface already exists in Spring Security. Exceptions thrown by a checker are unchecked subclasses of `AuthenticationException`, typically `LockedException` or `CredentialsExpiredException`.

By API contract, a checker should examine **stored and loaded status data**. Decisions based on the raw password/token submitted in the current login attempt belong to the credential-verification/provider step, and should not be sneaked into `UserDetailsChecker`.

## 3. The four flags on `UserDetails` and confusing negative names

By default Spring Security uses negatively named methods:

| `UserDetails` method | Value for valid account | When returning `false` | Default exception type |
| --- | --- | --- | --- |
| `isAccountNonLocked()` | `true` | Account is locked. | `LockedException` |
| `isEnabled()` | `true` | Account is disabled. | `DisabledException` |
| `isAccountNonExpired()` | `true` | Account has expired. | `AccountExpiredException` |
| `isCredentialsNonExpired()` | `true` | Credentials have expired. | `CredentialsExpiredException` |

**Do not mix these flags together.** For instance, a user locked due to repeated failed logins may still be enabled. A user with an expired password can still have an unexpired, unlocked, and enabled account.

Common mistake in JPA adapters:

```java
// WRONG when account.isLocked() == true means currently LOCKED:
@Override
public boolean isAccountNonLocked() {
    return account.isLocked();
}
```

Correct pattern matching the method name:

```java
@Override
public boolean isAccountNonLocked() {
    return !account.isLocked();
}
```

Similarly, if the entity stores `expired=true`, return `!expired` for `isAccountNonExpired()`. Flipping the boolean accidentally can allow locked accounts to log in or block normal accounts.

The four flags belong to **`UserDetails` data**. They do not automatically express failed login attempt counts, automatic unlock times, or password-reset workflows; the application must implement the corresponding data-update and business logic. `UserDetailsChecker` **reads and enforces** status; it does not manage login history itself.

## 4. Default ordering: before password – password – after password

In Spring Security **6.5.11**, the username/password flow of `AbstractUserDetailsAuthenticationProvider` and `DaoAuthenticationProvider` can be summarized as:

```text
UsernamePasswordAuthenticationToken (authenticated=false)
                         |
                         v
AuthenticationManager / ProviderManager
                         |
                         v
DaoAuthenticationProvider
                         |
                         +--> Fetch UserDetails from cache or UserDetailsService
                         |
                         v
           preAuthenticationChecks.check(user)
                 1. accountNonLocked?  [LockedException]
                 2. enabled?           [DisabledException]
                 3. accountNonExpired? [AccountExpiredException]
                         |
                  when pre-checks pass
                         v
           additionalAuthenticationChecks(user, request)
                 PasswordEncoder.matches(rawPassword, storedHash)
                 [BadCredentialsException if invalid]
                         |
                  when credentials pass
                         v
           postAuthenticationChecks.check(user)
                 4. credentialsNonExpired?
                 [CredentialsExpiredException]
                         |
                         v
           Create authenticated Authentication
                         |
                         v
           SecurityContext (handled by filter in web apps)
```

This is the **logical** order to understand roles. There is an **important exception** regarding executing password matching when pre-checks fail, covered in Section 5; do not infer from the diagram that `matches(...)` never runs when a user is locked.

### Pre-checks: three account states

Default checks run in order:

1. `!user.isAccountNonLocked()` → `LockedException`.
2. `!user.isEnabled()` → `DisabledException`.
3. `!user.isAccountNonExpired()` → `AccountExpiredException`.

If an account is simultaneously locked and disabled, the first error in the sequence above is typically `LockedException`. Do not treat **exception ordering** as a long-term public contract of a login API; client-facing response policies may differ from internal audit reasons.

### Credential verification: not `UserDetailsChecker`'s job

`DaoAuthenticationProvider.additionalAuthenticationChecks(...)` verifies credentials are present and calls:

```java
passwordEncoder.matches(presentedPassword, userDetails.getPassword())
```

`presentedPassword` is the password submitted by the user, and `userDetails.getPassword()` is the stored/encoded hash from the identity store. Never compare two passwords with `equals`, never call `encode(raw).equals(stored)` for BCrypt because of random salts, and never pull credentials from outside inside `UserDetailsChecker`.

On failure, the provider normally throws `BadCredentialsException`. If the user does not exist, the provider also **masks `UsernameNotFoundException`** as a generic credentials error by default to reduce account-existence disclosure.

### Post-check: expired credentials

After the password matches, the default calls:

```java
if (!user.isCredentialsNonExpired()) {
    throw new CredentialsExpiredException("Credentials expired");
}
```

This snippet **conveys the idea** (the actual message comes from a message source and may differ). The meaning: a right password is still **not enough to create a successful login** if credentials have expired. The application must design a secure password-change/recovery flow; Spring Security does not automatically generate a change-password UI just because this flag is false.

### Quick decision table

| Account locked | Disabled | Account expired | Password | Credentials expired | Typical outcome |
| --- | --- | --- | --- | --- | --- |
| No | No | No | Right | No | Successful `Authentication`. |
| **Yes** | Any | Any | Right or wrong | Any | `LockedException` per default pre-check. |
| No | **Yes** | Any | Right or wrong | Any | `DisabledException`. |
| No | No | **Yes** | Right or wrong | Any | `AccountExpiredException`. |
| No | No | No | **Wrong** | Any | `BadCredentialsException`. |
| No | No | No | **Right** | **Yes** | `CredentialsExpiredException`. |

This table assumes a compatible default provider, no custom checkers/providers altering policy, no database errors, and no caching causing stale data.

## 5. Important Spring Security 6.5.11 detail: failed pre-checks may still run password verification

Looking at the basic diagram, it is tempting to write:

> "If the account is locked, the provider stops immediately, so BCrypt definitely does not run."

That is **not entirely true** in Spring Security 6.5.11. `AbstractUserDetailsAuthenticationProvider` has the setting:

```java
setAlwaysPerformAdditionalChecksOnUser(boolean);
```

In the **6.5.11 source code**, this property defaults to **`true`**. When `preAuthenticationChecks.check(user)` throws an `AuthenticationException`, the implementation can **still invoke `additionalAuthenticationChecks(user, request)`** inside a separate catch block, then **rethrow the pre-check exception**. Any exception raised by that extra credential check is discarded to preserve the original account-status reason.

Consequences:

- **Locked** user with **right** password: the final error is still `LockedException`, even though the password check ran.
- **Locked** user with **wrong** password: the final error can still be `LockedException`, not turned into `BadCredentialsException`.
- **Disabled** or **account expired** user: the same idea applies.
- For accounts without pre-check errors: the credential check runs normally; **post-check only runs if this step throws no error**.
- With `credentialsNonExpired=false` and **wrong** password: normally returns `BadCredentialsException` first, because execution never reaches post-check.
- With `credentialsNonExpired=false` and **right** password: post-check throws `CredentialsExpiredException`.

**Why this design choice?** To reduce processing-time disparity between valid accounts and accounts blocked before password verification. It **does not guarantee constant-time behavior across the whole HTTP request**, since databases/caches, exception handling, and application code can still introduce differences. Do not blindly disable this mechanism merely to save BCrypt calls.

### What if changed to `false`?

`setAlwaysPerformAdditionalChecksOnUser(false)` allows a failing pre-check to stop before additional checks. That choice alters timing, hash computations, and whether custom checks run, so it requires threat modeling and testing. Do not flip this option merely under the assumption that "pre-check" means strictly never touching the password.

**Extension warning:** if you override `additionalAuthenticationChecks` to perform side effects (counting events, calling external services, writing data), it may execute **even when pre-checks already failed**, or execute repeatedly if the provider reloads the user from cache. Keep this step safe/idempotent; auditing should live in a mechanism aligned with authentication events.

## 6. Runnable Java 17+ example: verifying both exceptions and `matches` calls

This console demo uses **Spring Security 6.5.11**, Java 17+, and Gradle. It runs a real `DaoAuthenticationProvider` with `InMemoryUserDetailsManager` and `BCryptPasswordEncoder`. A `CountingEncoder` wrapper records calls to `matches(...)`, letting you observe the difference between **the returned exception type** and **whether password matching executed**.

### 6.1. Project structure

```text
user-details-checker-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/CheckerDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'user-details-checker-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
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
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

application {
    mainClass = 'demo.CheckerDemo'
}
```

### 6.2. File `src/main/java/demo/CheckerDemo.java`

```java
package demo;

import org.springframework.security.authentication.AccountExpiredException;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.CredentialsExpiredException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public final class CheckerDemo {

    private static final String PASSWORD = "DemoPass123!";

    // Counter for console demonstration only; do not use as a production encoder.
    static final class CountingEncoder implements PasswordEncoder {
        private final PasswordEncoder delegate = new BCryptPasswordEncoder();
        private int matchesCalls;

        @Override
        public String encode(CharSequence rawPassword) {
            return delegate.encode(rawPassword);
        }

        @Override
        public boolean matches(CharSequence rawPassword,
                               String encodedPassword) {
            matchesCalls++;
            return delegate.matches(rawPassword, encodedPassword);
        }

        int matchesCalls() {
            return matchesCalls;
        }
    }

    private static UserDetails account(
            String username,
            CountingEncoder encoder,
            boolean locked,
            boolean disabled,
            boolean accountExpired,
            boolean credentialsExpired) {

        return User.withUsername(username)
                .password(encoder.encode(PASSWORD))
                .roles("READER")
                .accountLocked(locked)
                .disabled(disabled)
                .accountExpired(accountExpired)
                .credentialsExpired(credentialsExpired)
                .build();
    }

    private static void attempt(
            AuthenticationManager manager,
            CountingEncoder encoder,
            String label,
            String username,
            String password) {

        int before = encoder.matchesCalls();
        String outcome;

        try {
            Authentication result = manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            username, password));
            outcome = result.isAuthenticated()
                    ? "AUTHENTICATED" : "NOT_AUTHENTICATED";
        } catch (AuthenticationException ex) {
            outcome = ex.getClass().getSimpleName();
        }

        int matchCount = encoder.matchesCalls() - before;
        System.out.println(label + "=" + outcome
                + ", passwordMatchesCalled=" + matchCount);
    }

    public static void main(String[] args) {
        CountingEncoder encoder = new CountingEncoder();

        InMemoryUserDetailsManager users = new InMemoryUserDetailsManager(
                account("good", encoder,
                        false, false, false, false),
                account("locked", encoder,
                        true, false, false, false),
                account("disabled", encoder,
                        false, true, false, false),
                account("accountExpired", encoder,
                        false, false, true, false),
                account("credentialsExpired", encoder,
                        false, false, false, true));

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        AuthenticationManager manager = new ProviderManager(provider);

        // Run successful login last so the demo does not depend on
        // ProviderManager erasing credentials after success.
        attempt(manager, encoder, "wrongPassword",
                "good", "bad-password");
        attempt(manager, encoder, "lockedCorrectPassword",
                "locked", PASSWORD);
        attempt(manager, encoder, "lockedWrongPassword",
                "locked", "bad-password");
        attempt(manager, encoder, "disabled",
                "disabled", PASSWORD);
        attempt(manager, encoder, "accountExpired",
                "accountExpired", PASSWORD);
        attempt(manager, encoder, "credentialsExpired",
                "credentialsExpired", PASSWORD);
        attempt(manager, encoder, "expiredCredentialsWrongPassword",
                "credentialsExpired", "bad-password");
        attempt(manager, encoder, "unknownUsername",
                "missing", PASSWORD);
        attempt(manager, encoder, "good",
                "good", PASSWORD);
    }
}
```

The imports `AccountExpiredException`, `BadCredentialsException`, `CredentialsExpiredException`, `DisabledException`, and `LockedException` in the file above are included to help readers connect the exception types; they are **not required by the current logic** since the code prints exception names via `getSimpleName()`. In projects with strict linting/Checkstyle forbidding unused imports, you can remove those five imports and the program still works.

### 6.3. Run command

From `user-details-checker-demo`, using JDK 17+ and a Java 17-compatible Gradle/Gradle Wrapper:

```bash
gradle run --quiet
```

**Stdout lines printed by the program in order**, excluding any logs from Gradle or libraries:

```text
wrongPassword=BadCredentialsException, passwordMatchesCalled=1
lockedCorrectPassword=LockedException, passwordMatchesCalled=1
lockedWrongPassword=LockedException, passwordMatchesCalled=1
disabled=DisabledException, passwordMatchesCalled=1
accountExpired=AccountExpiredException, passwordMatchesCalled=1
credentialsExpired=CredentialsExpiredException, passwordMatchesCalled=1
expiredCredentialsWrongPassword=BadCredentialsException, passwordMatchesCalled=1
unknownUsername=BadCredentialsException, passwordMatchesCalled=1
good=AUTHENTICATED, passwordMatchesCalled=1
```

This output assumes **exact Spring Security 6.5.11**, the example configuration, default cache, a single provider, and no custom checkers. In other versions, especially if additional-check execution policies change, **do not assume the same `matches` call counts**.

### 6.4. Read the output carefully

**`wrongPassword`:** `good`'s pre-checks pass; BCrypt compares hashes and returns false, and the provider throws `BadCredentialsException`.

**`lockedCorrectPassword`:** pre-check sees the account is locked and captures `LockedException`. With the default `alwaysPerformAdditionalChecksOnUser=true`, the provider still runs password matching and then rethrows `LockedException`.

**`lockedWrongPassword`:** the password is also wrong; `matches` runs, yet the resulting exception remains `LockedException` because the locked status already failed pre-check.

**`disabled` and `accountExpired`:** pre-checks block creating an authenticated token even when the password genuinely matches.

**`credentialsExpired`:** the password is right so it passes additional checks; post-check detects the expired password and throws `CredentialsExpiredException`.

**`expiredCredentialsWrongPassword`:** the password is wrong so it stops at credential comparison; post-check is never called, yielding `BadCredentialsException`.

**`unknownUsername`:** `UserDetailsService` finds no user. With the default provider, user-not-found is masked as `BadCredentialsException`; `DaoAuthenticationProvider` also compares against a dummy hash to mitigate timing leaks for missing users. The `matches` counter observes that comparison, yet **no user is authenticated**.

**`good`:** all pre-checks, password verification, and post-checks pass, and the manager returns an authenticated `Authentication`. The example creates no HTTP session; a real login in a Servlet filter also sets up `SecurityContext` per configuration.

**Note on the counter:** `CountingEncoder` only counts Java calls into `matches`; it does not prove constant-time execution, nor is it a security benchmark tool. Never use sample usernames/passwords in production.

## 7. Custom `UserDetailsChecker`: how to preserve default protections

`AbstractUserDetailsAuthenticationProvider` exposes two setters:

```java
provider.setPreAuthenticationChecks(customPreChecker);
provider.setPostAuthenticationChecks(customPostChecker);
```

**These two setters replace the existing checker**, rather than automatically appending new logic. If you write:

```java
provider.setPreAuthenticationChecks(user -> {
    // Only checks a product-specific condition.
});
```

you can accidentally **bypass all three default checks** for locked, disabled, and account expired. That is a severe bug if business code assumes Spring Security still checks full account status.

### Safer extension pattern: wrap the original checker

Because `getPreAuthenticationChecks()` is `protected`, a subclass can capture the default checker and chain additional conditions:

```java
// Snippet in a project where AccountUserDetails implements UserDetails.
// Requires imports: DaoAuthenticationProvider, UserDetailsService,
// UserDetailsChecker, DisabledException.
public final class ApprovedAccountDaoProvider
        extends DaoAuthenticationProvider {

    public ApprovedAccountDaoProvider(UserDetailsService users) {
        super(users);

        // Capture the default checker before setting the extended checker.
        UserDetailsChecker builtIn = getPreAuthenticationChecks();

        setPreAuthenticationChecks(user -> {
            builtIn.check(user);

            if (user instanceof AccountUserDetails account
                    && !account.isApproved()) {
                throw new DisabledException(
                        "Account awaiting approval");
            }
        });

        // Do NOT setPostAuthenticationChecks: preserve the provider's
        // default credentialsNonExpired check.
    }
}
```

This is **illustrative integration code**, not independently compilable without `AccountUserDetails` and the corresponding beans. A real project must have a clear policy for `approved` status, prefer generic client-facing login messages to prevent account enumeration, and ensure data is loaded consistently during authentication.

Advantages of **delegating to the built-in checker**:

1. Avoids duplicating locked/disabled/account-expired logic order and drifting on framework upgrades.
2. Every time the provider runs pre-checks, default logic still executes.
3. The new checker only adds business conditions already present on `UserDetails`; it needs neither raw passwords nor HTTP requests.
4. The default post-check for expired credentials remains intact.

If you need to add a post-check, apply the same pattern with `getPostAuthenticationChecks()` in a subclass and replace the checker **only after capturing the original delegate**. Write tests for all four default flags plus the new condition.

### Does `AccountStatusUserDetailsChecker` replace both default checkers?

Spring Security includes an `AccountStatusUserDetailsChecker` implementation. It checks `UserDetails` statuses, including credential status. **Do not plug it into pre-check assuming the pre/post password order stays identical.** This lesson keeps the boundary clear: account checks before credential matching, and `isCredentialsNonExpired()` checked afterward per `AbstractUserDetailsAuthenticationProvider`'s default configuration. When using another checker, understand exactly which flags it checks and when.

### Cases that do not belong in a checker

`UserDetailsChecker` takes no `Authentication` parameter. Thus it is unsuitable for:

- Comparing the entered password against a hash.
- Checking TOTP/OTP codes or bearer token signatures.
- Reading `HttpServletRequest` to decide login conditions.
- Performing IP/browser rate limiting.
- Replacing access checks on an invoice, document, or business resource.
- Writing sessions or setting `SecurityContextHolder` itself.

Those conditions belong in filters, providers, security policies, or appropriate business services. Mixing them into a checker makes testing harder, breaks purity, and makes it easy to bypass standard authentication mechanisms.

## 8. How should account status be stored in the database?

An account entity commonly has fields such as:

```text
account_id          (internal immutable key)
username_key        (unique per policy)
password_hash       (BCrypt/Argon2/...)
enabled             (boolean)
locked_until        (nullable timestamp)
account_expires_at  (nullable timestamp)
password_expires_at (nullable timestamp)
roles               (relation or separate table)
```

This is a **suggested model**, not a default Spring Security schema. `UserDetails` must derive status results from the data:

```java
// Snippet inside a user-store adapter, not a standalone class.
Instant now = clock.instant();

boolean nonLocked = account.lockedUntil() == null
        || !account.lockedUntil().isAfter(now);
boolean accountNonExpired = account.accountExpiresAt() == null
        || account.accountExpiresAt().isAfter(now);
boolean credentialsNonExpired =
        account.passwordExpiresAt() == null
        || account.passwordExpiresAt().isAfter(now);
```

In this example, `lockedUntil` is considered unlocked once `now >= lockedUntil`. The expiration rule also uses `now < expiresAt` to remain valid. **This is application policy**, not a built-in formula inside `UserDetailsChecker`. Handle timezones/clocks, multi-server sync, transactions, concurrent updates, and lock-duration calculations per business requirements.

If there is a separate `locked=true` column, do not ignore it when computing `isAccountNonLocked`. If multiple lock reasons exist (indefinite admin lock vs. temporary auto-lock), prefer a state model representing all reasons rather than inferring from a single context-free timestamp.

### Converting entities to `UserDetails` without ORM session coupling

In Spring Data JPA, flags and authorities should be **materialized inside a read transaction**, then converted into an independent `UserDetails`, for example:

```java
// Snippet inside a @Service bean with repository, clock, and policy.
// Requires Spring Security UserDetails/User, transaction imports...
@Transactional(readOnly = true)
public UserDetails loadUserByUsername(String username) {
    Account account = accounts.findForAuthentication(username)
            .orElseThrow(() ->
                    new UsernameNotFoundException("Account not found"));

    return User.withUsername(account.getUsername())
            .password(account.getPasswordHash())
            .roles(account.getRoleCodes().toArray(String[]::new))
            .disabled(!account.isEnabled())
            .accountLocked(account.isLocked())
            .accountExpired(account.isAccountExpired())
            .credentialsExpired(account.isPasswordExpired())
            .build();
}
```

This **is not a complete program**, since `Account`/`accounts`/domain methods are project-defined. The goal is to build a snapshot with hash, flags, and authorities **already read/checked inside the transaction**, rather than returning an entity with lazy collections that fails when the provider calls `getAuthorities()` outside the transaction.

Do not force every relation to `EAGER` just to make login work; use appropriate fetch plans or projections. Account status changes after login **do not automatically** update an `Authentication` already held in a session; design a policy for refreshing or revoking authentication.

## 9. After a status check fails, what does HTTP return?

`UserDetailsChecker` throws `AuthenticationException` to signal **authentication failure**. It **does not directly choose** the HTTP status, redirect, or JSON response.

Depending on the mechanism:

- **Form login:** authentication filter/failure handler may redirect to the login page with a generic message.
- **HTTP Basic:** authentication entry point typically returns `401` and `WWW-Authenticate`; do not assume a locked exception produces a distinct HTTP code.
- **Authenticated user lacking permissions:** typically handled by authorization and `AccessDeniedHandler`, which may return `403`; this is a **different step** from rejecting credentials/accounts before login.
- **Custom REST login:** must handle failures consistently and never issue successful tokens/sessions when a checker throws an exception.

You can record the true error category in an appropriately access-controlled audit system, yet avoid returning full details like "username exists, locked until 10:00" to unauthenticated callers. That helps attackers enumerate valid accounts. Messaging and account-recovery policies must balance UX with anti-enumeration.

**A testing caveat:** never hard-assert HTTP 403 for all locked/disabled cases. On the authentication path, behavior flows through entry points/failure handlers; test your specific filter configuration. Java exceptions in providers and HTTP statuses at clients are two distinct layers of responsibility.

## 10. Caching and login sessions: checkers do not run on every request

`AbstractUserDetailsAuthenticationProvider` has a `UserCache`; by default it is typically `NullUserCache`. If an application configures another cache, the provider may use cached `UserDetails` instead of querying the account store immediately.

In the 6.5.11 implementation, when a check involving a cached user fails, the provider can **reload the user from the source** and run the checks once more. This helps when cached data is stale, yet it is **not a guarantee that every account state is always re-checked against the database on every request**.

Distinguish:

- **Provider's UserCache:** speeds up repeated `authenticate` calls; tied to user load timing and status/cache invalidation.
- **SecurityContext in session:** after login, many HTTP requests reuse the stored authentication **without calling `DaoAuthenticationProvider` again**.
- **Self-contained JWT:** when a resource server verifies a JWT, it may not load `UserDetails` from the DB at all; `UserDetailsChecker` flags are not automatically invoked.
- **Remember-me:** has its own authentication mechanism; pre/post checks for username/password cannot be assumed universally across every mechanism.

If an admin locks a user while they already hold a valid session, you must design **session invalidation, authority/version checks, reauthentication, or live status policies** according to risk. `UserDetailsChecker` does not automatically "sign out all devices" just because `locked=true` in the DB.

If a user cache holds password hashes or mutable `UserDetails`, erasing credentials on the authentication object may affect cached data when sharing the same instance; avoid caching entities/proxies or caching without a refresh strategy. Test directly with your provider and `UserDetails` construction/copying strategy.

## 11. Testing must separate three types of behavior

### A. Unit tests for `UserDetailsChecker`

When using a custom checker, pass `UserDetails` with combinations of flags and verify:

- Locked accounts are rejected.
- Disabled accounts are rejected.
- Expired accounts are rejected.
- Custom policy states like pending approval are rejected.
- Valid users pass through.
- The checker **needs no raw password** to evaluate status.

Unit tests need neither HTTP filters nor a database when account snapshots are constructed cleanly.

### B. Integration tests through `DaoAuthenticationProvider`

This is where **actual ordering and outcomes** are verified:

| Case | Password | Expected exception under 6.5.11 defaults |
| --- | --- | --- |
| Account enabled/unlocked/not expired | Right, credentials valid | Authenticated token |
| Account locked | Right | `LockedException` |
| Account locked | Wrong | `LockedException`, encoder may still be called |
| Account disabled | Right | `DisabledException` |
| Account expired | Right | `AccountExpiredException` |
| Credentials expired | Right | `CredentialsExpiredException` |
| Credentials expired | Wrong | `BadCredentialsException` |
| Non-existent username | Any | `BadCredentialsException` by default |
| Wrong password, otherwise valid account | Wrong | `BadCredentialsException` |

This table assumes a single provider and no custom policies. The Section 6 example is an integration-style console test you can re-run to observe behavior.

### C. Filter and HTTP behavior tests

In Spring Boot MVC, configure real Spring Security filters and test:

- Sending valid HTTP Basic/form credentials → authenticated per URL policy.
- Sending wrong password → proper failure handler/entry point; no successful session.
- Locked/disabled/expired user → no successful authentication created.
- Existing authentication lacking a role → authorization denies per `hasRole`/`hasAuthority`.
- Old session after locking account → behavior matches the designed **session revocation policy**.

**Do not use `@WithMockUser` as proof that checkers work.** This annotation creates a mock identity for tests and usually bypasses `UserDetailsService`, providers, and `PasswordEncoder`. It is good for testing authorization with an assumed principal, not for proving real login paths from the user store.

## 12. Extending policy: where should checks live?

Some business requirements sound similar yet belong in different layers:

| Policy | Right place | Why |
| --- | --- | --- |
| User locked/disabled/expired | `UserDetailsChecker` or standard status logic in provider | Based on persistent `UserDetails` status data. |
| Does password hash match? | `PasswordEncoder.matches(...)` in provider | Needs client-submitted password and stored hash. |
| Credentials past DB expiry time | Compute `credentialsNonExpired` on load, post-check | Credential expiry status differs from secret matching. |
| Was OTP/MFA completed? | Appropriate authentication mechanism, step-up/authorization policy | Cannot be captured by a single password-status boolean. |
| User may only log in to current tenant | Identity layer/tenant-aware provider and verified context | `UserDetailsChecker` receives neither HTTP request nor tenant context by contract. |
| IP rate-limited | Dedicated filter/gateway/limiter | Needs request metadata and distributed counters. |
| Admin revokes role after user logged in | Session/token revocation or business authorization | Checkers do not necessarily run on every post-login request. |
| Password found in breach database | `CompromisedPasswordChecker` if configured, or password-change flow | Not the same thing as `credentialsNonExpired`. |

`DaoAuthenticationProvider` also supports `CompromisedPasswordChecker` and `UserDetailsPasswordService` during successful authentication assembly, depending on configuration. Do not confuse these extensions with **the two `UserDetailsChecker`s** (pre and post). `CompromisedPasswordChecker` handles breached passwords per policy; `UserDetailsPasswordService` helps upgrade hashes when appropriate. Their responsibilities differ from account locks/disablement or expired credentials.

## 13. Common mistakes and fixes

1. **Assuming `UserDetailsChecker` compares passwords.** Wrong: it only sees `UserDetails`, while `DaoAuthenticationProvider.additionalAuthenticationChecks` and `PasswordEncoder` verify the secret.
2. **Thinking all checks run before the password.** Wrong: `credentialsNonExpired` runs in post-check after valid credential matching by default.
3. **Thinking a failed pre-check guarantees BCrypt never runs.** False by default in 6.5.11 with `alwaysPerformAdditionalChecksOnUser=true`; the final exception remains the original status error.
4. **Treating `setPreAuthenticationChecks` as additive.** The setter replaces the checker; it can drop locked/disabled/account-expired checks. Keep the default delegate or re-verify fully.
5. **Assuming `setPostAuthenticationChecks` keeps password expiry checks.** The setter replaces it; dropping the default lets accounts with expired credentials authenticate against policy.
6. **Inverting the `isAccountNonLocked` boolean.** `false` means the account is locked; invert the sign when the entity has `isLocked`.
7. **Merging `accountExpired` and `credentialsExpired` into one flag.** The two states have distinct causes and remediation flows.
8. **Manually calling `authentication.setAuthenticated(true)` to bypass errors.** Never issue a trusted identity when pre/password/post checks fail to complete.
9. **Catching all `AuthenticationException`s and returning an authenticated token.** Violates the system's trust boundary.
10. **Using a login error message that leaks too much status.** Can enable username enumeration; separate internal audits from public responses.
11. **Claiming `@WithMockUser` proves password and status checks.** Mock tests typically skip providers.
12. **Assuming locking the DB immediately invalidates old sessions.** Requires separate invalidation/revalidation mechanisms.
13. **Reading status from detached/lazy JPA entities after the transaction closes.** Build a complete `UserDetails` snapshot while reading the DB.
14. **Enabling caching without refreshing account flags.** Can authenticate using stale data; design TTLs, invalidation, and cache tests.
15. **Abusing checkers to inspect request IP/OTP/tenant.** The contract has no request; pick the right layer.
16. **Setting `credentialsExpired=true` on an entity without mapping `isCredentialsNonExpired=false`.** The provider cannot know passwords expired if the adapter returns the wrong flag.
17. **Thinking a `readOnly` transaction locks accounts or checks passwords itself.** Transactions only read data; checkers/providers decide authentication.
18. **Allowing a right password to override disabled/locked states.** A password is one necessary condition, not the sole condition for issuing a session.
19. **Relying on exact English exception messages.** Message sources/localization can vary; test exception types/contracts rather than hardcoded text.
20. **Blindly disabling `alwaysPerformAdditionalChecksOnUser` for performance.** Carries timing/behavior trade-offs; evaluate risks first.

## 14. Self-check questions

**Question 1.** What data does `UserDetailsChecker.check(user)` receive, and does it compare passwords directly?

**Answer:** It receives a `UserDetails` containing account status; it does not receive raw passwords, HTTP requests, or JWTs. Password matching belongs to the provider/encoder.

**Question 2.** Under Spring Security 6.5.11 defaults, what are the three pre-checks?

**Answer:** In order: account non-locked, enabled, and account non-expired. The corresponding exceptions are `LockedException`, `DisabledException`, and `AccountExpiredException`.

**Question 3.** If the password is right yet `credentialsNonExpired=false`, does login succeed?

**Answer:** No. Post-check throws `CredentialsExpiredException` after password matching succeeds.

**Question 4.** If the password is wrong and `credentialsNonExpired=false`, which exception is typically seen?

**Answer:** `BadCredentialsException`, because credential comparison fails before post-check runs.

**Question 5.** The user is locked and the password is wrong, yet the `matches` counter incremented. Did the framework let them log in before locking?

**Answer:** No. In 6.5.11, the default can run additional checks even after a pre-check fails to reduce timing disparities, then rethrows `LockedException`. No authenticated result is produced.

**Question 6.** Does `provider.setPreAuthenticationChecks(user -> {})` preserve default protections?

**Answer:** No. The setter replaces the checker; an empty lambda skips locked/disabled/account-expired checks. Wrap the default checker or prove full coverage with tests.

**Question 7.** Is adding `@WithMockUser` to an integration test enough to prove locked users cannot log in?

**Answer:** No. Mock users can bypass the manager/provider. Call `AuthenticationManager.authenticate(...)` or test real HTTP filters with credentials.

**Question 8.** When an admin locks a user in the DB, do subsequent requests on an existing session with an `Authentication` automatically re-run pre-checks?

**Answer:** Never assume that. You need a dedicated revalidation strategy, session revocation, or authorization policy.

**Question 9.** Can `AccountStatusUserDetailsChecker` be dropped into pre-check while guaranteeing identical default ordering?

**Answer:** No. You must know which flags that checker evaluates and when it runs; separating pre/account checks from post/credential checks has business and UX significance.

**Question 10.** Why shouldn't client responses necessarily expose exact exception names?

**Answer:** Authentication and HTTP failure handling are separate layers; detailed responses can leak account status or existence. Use failure handlers/entry points and an appropriate messaging policy.

## 15. Official reference documentation

- [Spring Security 6.5.11 — UserDetailsChecker API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsChecker.html): `check(UserDetails)` contract and purpose of checking persistent data status.
- [Spring Security 6.5.11 — AbstractUserDetailsAuthenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html): pre/post checker setters, `setAlwaysPerformAdditionalChecksOnUser`, caching, and authentication creation.
- [Spring Security 6.5.11 — AbstractUserDetailsAuthenticationProvider Source](https://github.com/spring-projects/spring-security/blob/6.5.11/core/src/main/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.java): default order locked → disabled → account expired; additional checks; post credentials expired; preserving pre-check errors while still running password checks.
- [Spring Security 6.5.11 — DaoAuthenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html): `UserDetailsService`, `PasswordEncoder`, and password authentication extension points.
- [Spring Security 6.5.11 — User.UserBuilder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/User.UserBuilder.html): `accountLocked`, `disabled`, `accountExpired`, and `credentialsExpired` in fixtures.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): path from authentication filter through manager/provider to user store.
- [Spring Security — UserDetails API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetails.html): `isAccountNonLocked`, `isEnabled`, `isAccountNonExpired`, and `isCredentialsNonExpired` flags.

**Conclusion:** `UserDetailsChecker` enables Spring Security to enforce account status at **two distinct checkpoints**: pre-check for lock/disablement/account expiry, and post-check for credential expiry. Password matching performed by the provider/encoder sits in between as the deciding step. In Spring Security 6.5.11, an additional password check may still execute after a failed pre-check, yet it can never turn an invalid account state into a successful login. Preserve default checkers when customizing, test through a real provider, and manage session revocation separately after DB state changes.