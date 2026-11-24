# BadCredentialsException, LockedException, DisabledException, and Expiration Exceptions

> **Topic:** Spring Security — authentication → **Account State**. This lesson explains how a username/password authentication system distinguishes **invalid proof** from **locked, disabled, or expired accounts** or **expired credentials**. It focuses on the `UserDetails` contract, `DaoAuthenticationProvider`'s check ordering, the `AuthenticationException` hierarchy, safe application responses, and testing account states. The example uses Java 17 and Spring Security **6.5.11** (a branch including the timing fix for account-status checks).

## 1. Learning objectives

After this lesson, you can:

1. Explain the meaning and inheritance hierarchy of `BadCredentialsException`, `LockedException`, `DisabledException`, `AccountExpiredException`, and `CredentialsExpiredException`.
2. Accurately map the four `UserDetails` properties: `isAccountNonLocked()`, `isEnabled()`, `isAccountNonExpired()`, and `isCredentialsNonExpired()`.
3. Understand why a **wrong password** is equivalent neither to a **locked account** nor to an **expired password**.
4. Trace when a provider checks status before/after password verification; avoid conflating internal outcomes with HTTP status codes.
5. Recognize that `AccountStatusException` causes `ProviderManager` to **stop immediately**, whereas `BadCredentialsException` may allow falling back to another provider.
6. Build a runnable Java 17 example using `DaoAuthenticationProvider` and `BCryptPasswordEncoder`, accurately predicting the exception type per account.
7. Design login messages, password resets, unlock operations, cache/session invalidation, and safe auditing.

## 2. Classification table: proof failures vs. status failures

In Spring Security, `AuthenticationManager.authenticate(...)` **returns an authenticated `Authentication` or throws `AuthenticationException`**. The exceptions directly relevant to this topic:

| Exception | Typical scenario | Nature | Is it an `AccountStatusException`? |
| --- | --- | --- | --- |
| `BadCredentialsException` | Wrong password, missing password, or provider masks user-not-found | Proof rejected | **No** |
| `LockedException` | `UserDetails.isAccountNonLocked() == false` | Account is locked | **Yes** |
| `DisabledException` | `UserDetails.isEnabled() == false` | Account is not enabled for login | **Yes** |
| `AccountExpiredException` | `UserDetails.isAccountNonExpired() == false` | **Account** lifetime has ended | **Yes** |
| `CredentialsExpiredException` | `UserDetails.isCredentialsNonExpired() == false` | **Credential** (e.g., password) lifetime has ended | **Yes** |

Conceptual class hierarchy:

~~~text
RuntimeException
└── AuthenticationException
    ├── BadCredentialsException
    ├── AccountStatusException
    │   ├── LockedException
    │   ├── DisabledException
    │   ├── AccountExpiredException
    │   └── CredentialsExpiredException
    └── ... other AuthenticationExceptions
~~~

`BadCredentialsException` is a kind of **`AuthenticationException`**, but it does not belong to `AccountStatusException`. The four account/credential status exceptions all belong to `AccountStatusException` and receive special handling in `ProviderManager`.

**Important:** an exception describes **the rejection reason under a specific authentication mechanism**; by itself it does not prove every factor was checked, does not prescribe a default HTTP status across all applications, and is not a message to show verbatim to end users.

### 2.1. "Wrong password" does not necessarily mean an existing user

`DaoAuthenticationProvider` relies on `UserDetailsService` and `PasswordEncoder`. If a username does not exist, `UserDetailsService` normally throws `UsernameNotFoundException`. With `hideUserNotFoundExceptions=true` (the default), the provider converts that error into `BadCredentialsException` to avoid leaking whether the username exists.

Therefore:

~~~text
Non-existent username -> UsernameNotFoundException at loadUser layer
                      -> BadCredentialsException in default provider

Existing username, wrong password -> BadCredentialsException

Existing username, right password, locked -> LockedException
~~~

**Never conclude:** seeing `BadCredentialsException` means the username definitely exists or the user definitely typed the wrong password. It is a proof-rejection error at the provider boundary; the underlying cause depends on configuration.

## 3. UserDetails contract: positive booleans, negative error states

`UserDetails`'s status methods return **true when the condition is normal/permitted**, not true when there is a problem:

~~~java
boolean isAccountNonLocked();        // true = NOT locked
boolean isEnabled();                 // true = account enabled
boolean isAccountNonExpired();       // true = account NOT expired
boolean isCredentialsNonExpired();   // true = credentials NOT expired
~~~

These are **abbreviated signatures** to explain the contract, not the full interface contents.

| Value in UserDetails | Normal | When false | Default exception |
| --- | --- | --- | --- |
| `isAccountNonLocked()` | `true` | Account locked | `LockedException` |
| `isEnabled()` | `true` | Account disabled | `DisabledException` |
| `isAccountNonExpired()` | `true` | Account expired | `AccountExpiredException` |
| `isCredentialsNonExpired()` | `true` | Password/credentials expired | `CredentialsExpiredException` |

When using Spring Security's `User` builder, builder parameter names usually express the **abnormal state** (opposite boolean direction from the interface):

~~~java
User.withUsername("linh")
    .password(encodedPassword)
    .roles("USER")
    .accountLocked(true)       // isAccountNonLocked() == false
    .disabled(false)           // isEnabled() == true
    .accountExpired(false)     // isAccountNonExpired() == true
    .credentialsExpired(false) // isCredentialsNonExpired() == true
    .build();
~~~

This is an **integration snippet creating UserDetails**, requiring `encodedPassword` and importing `org.springframework.security.core.userdetails.User`. Lock/disable/expiry properties are normally mapped from account records in a database, LDAP, or identity service.

### Do not equate the flags

**Locked** is typically a state triggered by an anti-brute-force policy, an admin, or a risk event. **Disabled** can represent a departed employee, an unactivated account, or a policy-halted account. **Account expired** generally reflects an account's usage term ending. **Credentials expired** focuses on password/credential lifecycles without necessarily terminating the account.

Do not use a single `enabled=false` flag to represent all states if your system has distinct recovery flows. Conversely, you do not need four separate DB columns if business logic does not require them: what matters is that mapping to `UserDetails` and accompanying policies stay clear and consistent.

## 4. Default processing flow of DaoAuthenticationProvider

`DaoAuthenticationProvider` extends `AbstractUserDetailsAuthenticationProvider`. It receives a `UsernamePasswordAuthenticationToken` from a filter or caller, loads `UserDetails` (or cache), checks account status and password, and produces an `Authentication` result.

A conceptual flow:

~~~mermaid
flowchart TD
    A["Unauthenticated UsernamePasswordAuthenticationToken"] --> B["ProviderManager / DaoAuthenticationProvider"]
    B --> C{"UserDetails found?"}
    C -->|Not found| D["Default BadCredentialsException"]
    C -->|Store error| E["Service error, do not fake BadCredentials"]
    C -->|Found| F{"Pre-authentication checks"}
    F -->|Locked| L["LockedException"]
    F -->|Disabled| X["DisabledException"]
    F -->|Account expired| Y["AccountExpiredException"]
    F -->|Passed checks| G["PasswordEncoder.matches(...)"]
    G -->|Mismatch| H["BadCredentialsException"]
    G -->|Match| I{"Post-authentication check"}
    I -->|Credential expired| J["CredentialsExpiredException"]
    I -->|Valid| K["Authenticated Authentication"]
~~~

**Special note for patched builds from 6.5.10 onward:** during status checks, the provider may **still execute an additional password check** even when pre-checks already raised an error, in order to reduce account-status timing leaks. This does not mean the account is granted access; **the original status exception remains the rejection outcome**. The diagram above illustrates **policy decision ordering**, not every auxiliary check performed to mitigate timing differences.

### 4.1. Pre-authentication checks: locked → disabled → account expired

In the default implementation, `DefaultPreAuthenticationChecks` checks statuses in this order:

1. `!user.isAccountNonLocked()` → `LockedException`.
2. `!user.isEnabled()` → `DisabledException`.
3. `!user.isAccountNonExpired()` → `AccountExpiredException`.

If a user is **both locked and disabled**, the default chosen status error is **`LockedException`** because the lock check comes first. This is the order of the default implementation, not a business standard forcing every provider (LDAP, OIDC, JWT, custom) to behave identically.

Pre-checks happen **before the decision to accept the password**, yet in patched builds they may include an auxiliary credential check to reduce timing side channels. Therefore, never infer from the exception whether the submitted password was right or wrong.

### 4.2. Password verification: BadCredentialsException

`DaoAuthenticationProvider.additionalAuthenticationChecks(...)` uses `PasswordEncoder.matches(rawPassword, encodedPassword)`. For missing/null or non-matching credentials, the provider throws `BadCredentialsException`.

Password hashes in `UserDetails` must be generated by an appropriate `PasswordEncoder`, never stored in plaintext. BCrypt is an easy-to-understand choice for examples. In production systems, pick algorithms/cost factors per security policy, manage hash upgrades, and benchmark performance; never commit demo passwords into real repositories.

### 4.3. Post-authentication checks: CredentialsExpiredException

After a valid password match, `DefaultPostAuthenticationChecks` checks `isCredentialsNonExpired()`. When proof is valid yet credentials are marked expired, it throws **`CredentialsExpiredException`**. This differs from `AccountExpiredException` (account expiration in pre-check).

If the password is **both wrong** and credentials are also expired, the normal password-check path throws `BadCredentialsException` **before** reaching post-check. Hence the returned exception may be bad credentials, not credentials expired. User status exceptions reflect **check order**, not a list of every simultaneous cause.

### 4.4. Cache hits and stale account data

If `UserCache` is enabled, an authentication attempt may hit a `UserDetails` holding stale status. Spring Security has a mechanism to reload the user when a check against a cached user fails in certain branches, yet that is **no guarantee of automatic revocation** for a newly locked account or newly changed password.

Specifically: if a cached record still has `accountNonLocked=true` and the old password matches, the provider may authenticate using the stale snapshot without loading fresh state. Database state changes must be paired with invalidation and session/token checks per policy. `UserCache` defaults to `NullUserCache`, though many applications configure caches or maintain sessions outside the provider.

## 5. Outcomes when multiple errors occur simultaneously

A request need not have only one issue. Read **the check mechanism** rather than picking an exception at random.

| UserDetails + credential condition | Exception under default logic | Explanation |
| --- | --- | --- |
| Normal account, wrong password | `BadCredentialsException` | Password does not match |
| Non-existent username, hideUserNotFoundExceptions=true | `BadCredentialsException` | Avoids exposing username difference |
| Account locked, right password | `LockedException` | Pre-check lock |
| Account disabled, right password | `DisabledException` | Pre-check enabled |
| Account expired, right password | `AccountExpiredException` | Pre-check account expiry |
| Credentials expired, right password | `CredentialsExpiredException` | Post-check credential expiry |
| Locked **and** disabled | `LockedException` | Lock is evaluated first |
| Disabled **and** account expired | `DisabledException` | Enabled is evaluated before account expiry |
| Account expired **and** credentials expired | `AccountExpiredException` | Pre-check account expiry precedes post-check |
| Credentials expired **and** wrong password | `BadCredentialsException` | Password fails so post-check is never reached |
| Account locked, wrong password (patched default provider) | `LockedException` | Lock state still fails authentication; auxiliary password check does not alter original exception |
| Account store unreachable | Usually service error like `InternalAuthenticationServiceException` | Must not guess user-not-found or wrong password |

The rows above assume **standard `DaoAuthenticationProvider`** and a `UserDetailsService` returning accurate status flags. If a custom `AuthenticationProvider` or custom `UserDetailsChecker` changes rules, order and outcomes may differ. For a username not found, there is no object on which to check locked/expired flags.

## 6. Standalone Java 17 demo: seven outcomes and precedence

This is a **console program** using Spring Security's real `DaoAuthenticationProvider` with no servlet server needed. It creates account data in memory, hashes passwords with BCrypt, and passes requests to `ProviderManager`. It never constructs an "authenticated" result directly from client input.

**Version:** Spring Security **6.5.11**, released as a 6.5 version containing the fix for account-status timing. This version reproduces the example; it is **not guidance to stay pinned on this version forever in production** — real applications should stay updated on maintained versions and new advisories.

### 6.1. Project structure

~~~text
account-state-exceptions-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/accountstate/
    └── AccountStateExceptionsDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'account-state-exceptions-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework.security:spring-security-crypto:6.5.11'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.accountstate.AccountStateExceptionsDemo'
}
~~~

### 6.2. Complete Java file

Create `src/main/java/example/accountstate/AccountStateExceptionsDemo.java`:

~~~java
package example.accountstate;

import java.util.List;
import java.util.Map;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public class AccountStateExceptionsDemo {

    static final class DemoUsers implements UserDetailsService {
        private final Map<String, UserDetails> accounts;

        DemoUsers(PasswordEncoder encoder) {
            String hash = encoder.encode("correct-password");
            accounts = Map.of(
                    "active", create("active", hash,
                            false, false, false, false),
                    "locked", create("locked", hash,
                            true, false, false, false),
                    "disabled", create("disabled", hash,
                            false, true, false, false),
                    "expired", create("expired", hash,
                            false, false, true, false),
                    "credential-expired", create("credential-expired", hash,
                            false, false, false, true),
                    "locked-and-disabled", create("locked-and-disabled", hash,
                            true, true, false, false),
                    "expired-both", create("expired-both", hash,
                            false, false, true, true)
            );
        }

        private static UserDetails create(
                String username, String passwordHash,
                boolean locked, boolean disabled,
                boolean accountExpired, boolean credentialExpired) {

            return User.withUsername(username)
                    .password(passwordHash)
                    .roles("READER")
                    .accountLocked(locked)
                    .disabled(disabled)
                    .accountExpired(accountExpired)
                    .credentialsExpired(credentialExpired)
                    .build();
        }

        @Override
        public UserDetails loadUserByUsername(String username)
                throws UsernameNotFoundException {
            UserDetails account = accounts.get(username);
            if (account == null) {
                throw new UsernameNotFoundException("Account not found");
            }
            return account;
        }
    }

    private static void attempt(
            AuthenticationManager manager,
            String label, String username, String password) {

        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, password);

        try {
            Authentication result = manager.authenticate(request);
            System.out.println(label + " => SUCCESS(authenticated="
                    + result.isAuthenticated() + ")");
        }
        catch (AuthenticationException ex) {
            // Print only the exception type, never the username or credentials.
            System.out.println(label + " => "
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        UserDetailsService users = new DemoUsers(encoder);

        // Constructor accepting UserDetailsService for Spring Security 6.5.
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        AuthenticationManager manager =
                new ProviderManager(List.of(provider));

        attempt(manager, "valid", "active", "correct-password");
        attempt(manager, "wrong-password", "active", "wrong");
        attempt(manager, "unknown-user", "not-here", "correct-password");
        attempt(manager, "locked", "locked", "correct-password");
        attempt(manager, "disabled", "disabled", "correct-password");
        attempt(manager, "account-expired", "expired", "correct-password");
        attempt(manager, "credentials-expired",
                "credential-expired", "correct-password");
        attempt(manager, "locked-plus-disabled",
                "locked-and-disabled", "correct-password");
        attempt(manager, "expired-account-plus-credentials",
                "expired-both", "correct-password");
        attempt(manager, "locked-with-wrong-password",
                "locked", "wrong");
    }
}
~~~

**Why is this code trustworthy within the demo scope?**

- `DemoUsers` implements the `UserDetailsService` contract, returning real `UserDetails` instances and throwing `UsernameNotFoundException` when a username is absent.
- Passwords are stored as **BCrypt hashes**. `DaoAuthenticationProvider` verifies passwords; there is no "accept all" provider.
- Every account shares the same demo password so only **status flags** vary, clearly revealing the status-driven exceptions.
- `DaoAuthenticationProvider(users)` and `setPasswordEncoder(encoder)` match the 6.5.11 API; no deprecated no-arg constructor is used.
- `ProviderManager` has only one provider, so outcomes are never altered by a second fallback provider. When an account is locked/disabled/expired, the manager never returns success.
- `attempt` does not place the result into `SecurityContextHolder`, as this is a manager-layer console test, not an HTTP flow.
- The program prints only exception types and the `isAuthenticated` flag of **successful results**; it never prints passwords, hashes, or tokens.

### 6.3. Running with Gradle

From `account-state-exceptions-demo` with JDK 17+ and a compatible Gradle/Gradle Wrapper:

~~~bash
gradle run --quiet
~~~

If using a Wrapper, run `./gradlew run --quiet`; on Windows PowerShell run `.\gradlew.bat run --quiet`.

Output from the program's `System.out.println` lines, excluding Gradle logs:

~~~text
valid => SUCCESS(authenticated=true)
wrong-password => BadCredentialsException
unknown-user => BadCredentialsException
locked => LockedException
disabled => DisabledException
account-expired => AccountExpiredException
credentials-expired => CredentialsExpiredException
locked-plus-disabled => LockedException
expired-account-plus-credentials => AccountExpiredException
locked-with-wrong-password => LockedException
~~~

These lines depend on standard `DaoAuthenticationProvider` logic in the specified version. Output order is determined by `main`; random BCrypt hash strings are not printed, so output is deterministic. The timing patch may change how many password comparisons run compared to older releases, yet it **does not change the final status exception type** for these cases.

### 6.4. Reading three easily confused cases

**`wrong-password` and `unknown-user` both yield BadCredentialsException:** the first case has a user whose password does not match; the second has no user, and the default provider masks `UsernameNotFoundException`. You cannot infer whether a username exists solely from the returned exception type.

**`locked-plus-disabled` yields LockedException:** the default pre-check evaluates locked before disabled, so locked is reported first. Do not conclude the disabled flag is false; the code intentionally set both true on the builder.

**`locked-with-wrong-password` still yields LockedException:** with the 6.5.11 patch, the provider may perform an auxiliary credential check to mitigate timing risks while preserving the locked status decision. Never use this result to guess whether the user typed the right or wrong password.

## 7. What if an account is locked while already having an active session?

`UserDetails` holds state for **new authentication attempts**. A form login may create an `Authentication` in `SecurityContext` and store it in a session. If an admin locks the user **afterward**, the existing session does not automatically invalidate itself or re-read `UserDetails` on every request.

Likewise, an already-issued JWT bearer access token may carry scopes/roles until it expires. Changing `isEnabled` or `isAccountNonLocked` in the database, or refreshing a `UserDetails` cache, **does not rewrite signed claims inside a JWT**.

| Action | New username/password authentication | Existing session | Existing JWT |
| --- | --- | --- | --- |
| Lock account and update user store | Provider rejects with `LockedException` if reading fresh data | May stay valid until invalidated per policy | May still be accepted until token is rejected/expired |
| Disable account | Rejects with `DisabledException` | Does not expire merely from DB change | Claims do not change automatically |
| Mark password expired | Rejects with `CredentialsExpiredException` | Must decide whether to force re-authentication | Must define separate revocation/step-up policy |
| Account expired | Rejects with `AccountExpiredException` | Needs session invalidation or re-check policy | Needs separate token lifetime/revocation policy |

If the business requirement is "locking an account takes effect immediately," you must add: **evict all related caches, invalidate sessions/remember-me tokens, and enforce token checking/revocation or security-version checks on sensitive requests**. Never assume a new-login exception automatically cuts off all open access paths.

### 7.1. Why does caching need to be mentioned?

Suppose cached `UserDetails` currently holds `isAccountNonLocked=true`. An admin updates the account to locked in the database without evicting the cache. A new authentication request may read the stale user from cache and miss the status change. Handle post-commit eviction, multi-instance synchronization, and race conditions.

The provider's `UserCache` and an `Authentication` already stored in a session are **two different storage locations**. Clearing the first does not automatically update the second.

## 8. Impact on AuthenticationProvider ordering and fallback

`ProviderManager` can hold a list of `AuthenticationProvider`s. For certain error types like `BadCredentialsException`, it may try another provider that supports the request; if a later provider succeeds, that success result is used. For **`AccountStatusException`**, it short-circuits immediately to avoid trying further providers or parent managers.

Specifically:

| P1 | P2 also capable of handling | Behavior |
| --- | --- | --- |
| `BadCredentialsException` | P2 can accept credentials | **May continue** to P2 and succeed |
| `LockedException` | P2 can accept credentials | **Stops immediately**; never uses P2 to bypass locked account |
| `DisabledException` | P2 can accept credentials | **Stops immediately** |
| `AccountExpiredException` | P2 can accept credentials | **Stops immediately** |
| `CredentialsExpiredException` | P2 can accept credentials | **Stops immediately** |

**Design warning:** if an app has an LDAP provider first and a local provider second, a `BadCredentialsException` from LDAP does not automatically prevent local fallback. That may be an intentional multi-source login policy or an unintended fallback vulnerability.

Likewise, **never disguise infrastructure failures** as `BadCredentialsException` to trigger fallback without design intent. `InternalAuthenticationServiceException` also causes `ProviderManager` to stop immediately in standard flows. Throwing the right exception is part of authentication policy.

### `supports(...)` does not confirm an account is valid

`AuthenticationProvider.supports(Class<?>)` only declares whether a provider handles a given `Authentication` class; it does not check usernames, passwords, or lock state. Thus never place "account is locked" logic inside `supports` and never expect `supports=false` to mean credentials were rejected.

## 9. From Java exceptions to HTTP, login pages, and APIs

At the manager/provider layer, the outcome is **`Authentication` or `AuthenticationException`**. The Servlet Security layer (authentication filters, failure handlers, `AuthenticationEntryPoint`, `ExceptionTranslationFilter`) determines the HTTP response.

- **HTTP Basic:** many default configurations return **401 Unauthorized** for `AuthenticationException`s, including status errors. There is no default distinct HTTP status code for locked/disabled.
- **Form login:** typically redirects to a login/error page or invokes `AuthenticationFailureHandler`; it does not return JSON `{"error":"LockedException"}` by default.
- **Custom REST API:** can design public error codes and custom messages, but only after assessing **user enumeration**, reset abuse, customer support needs, and public policy.
- **403 Forbidden:** typically relates to an **authenticated principal lacking permissions**, not a mandatory code for `LockedException` at login.

**Do not oversimplify:** `LockedException == HTTP 423`, `DisabledException == HTTP 403`, or `CredentialsExpiredException == HTTP 401` in every Spring Security app. Those mappings **are not automatic rules** of `DaoAuthenticationProvider`.

### 9.1. Safe messages for users

On a public login endpoint, a uniform message such as:

> Unable to log in with the provided credentials. Please check your details or use the account recovery process.

can reduce username existence guessing. For users with an already-trusted session or who passed an appropriate verification step, the UI can display more specific guidance that a password change is required, the account awaits activation, or unlock support is needed. **Detail level must be governed by policy and channel trust**, not merely by exception class names.

For accounts disabled by administrative decision, an application may disallow self-service "re-enable" with one click. For accounts locked by failed passwords, you can design a waiting period, verification email, or security support. For expired credentials, provide a **separately protected password-change flow**, never allowing a token rejected at normal login to grant full API access.

### 9.2. Does a failed login count as an authenticated request?

No. An `AuthenticationException` indicates the provider **did not return a successful Authentication**. Even if the user object was loaded and its status known internally, protected controllers must never treat the request as authenticated. Event/failure handling can record the error class for auditing, without "keeping an old token" to let the request through.

## 10. Status policy in the database and identity system

Account tables often include fields like:

~~~text
user_id              : stable identifier
username             : login name
password_hash        : encoded hash
enabled              : true/false
locked_until         : timestamp or null
account_expires_at   : timestamp or null
password_changed_at  : timestamp
password_expires_at  : timestamp or null
failed_attempts      : failed tries within control window
security_version     : security state version
~~~

This is a **reference model**, not a mandatory default Spring Security schema.

The `UserDetails` mapping process can derive:

- `isAccountNonLocked`: true if not locked or `locked_until` has passed per trusted clock/policy.
- `isEnabled`: true when the account is enabled by the system owner.
- `isAccountNonExpired`: true if before `account_expires_at`.
- `isCredentialsNonExpired`: true if credentials have not passed `password_expires_at`.

Use a consistent time source and proper UTC/time zone handling; never compare date/time strings by locale. For "indefinite" (null) columns, document the convention explicitly. Avoid database defaults or inverted mappings that accidentally lock users en masse.

### 10.1. DaoAuthenticationProvider does not build a lockout system for you

`DaoAuthenticationProvider` reads **the status returned in `UserDetails`**; it does not automatically count failed logins, set `locked_until`, or send unlock emails just because `BadCredentialsException` occurred. The application must implement failure/lockout policies at the right layer, handle races across concurrent requests, and especially prevent attackers from locking out arbitrary users merely by submitting usernames.

Business-level workflow example:

~~~text
credential attempt
    -> provider checks evidence and status
    -> on failure, audit/rate limiter receives failure
    -> evaluate anti-brute-force policy per account/IP/device/risk
    -> if lock required, update account in source of truth
    -> evict related UserDetails cache
    -> handle existing sessions/tokens as required
    -> next authentication reads UserDetails with isAccountNonLocked=false
~~~

Never record plaintext passwords, bearer tokens, or hashes in events. When using `AuthenticationFailureBadCredentialsEvent` and Spring Security events, configure an appropriate `AuthenticationEventPublisher` and understand the difference between manager events and filter handlers. Never assume the whole system always emits all failure events unless configured.

### 10.2. Password resets and expired credentials

If `credentialsNonExpired=false`, normal login is blocked even with the right password. The **password-change** flow must require separate proof, such as a single-use reset token with clear TTL/context or step-up verification over another channel. After a successful reset, update the hash and timestamp, restore credential status to valid, invalidate `UserDetails` caches, revoke old reset tokens, and apply policy to existing sessions/tokens.

Never advise developers to "temporarily set credentialsNonExpired=true from a request" so the user passes through every endpoint before changing their password. That grants access before verifying or remediating the state.

### 10.3. Locks and expirations require different recovery rules

- **Locked:** may unlock once the lock duration expires, after verification, or via admin intervention; define which actions are allowed while locked.
- **Disabled:** typically driven by admin, HR, or unactivated flows; never auto-unlocks merely by re-entering a password.
- **Account expired:** may require contract/subscription renewal or re-provisioning.
- **Credentials expired:** may require changing passwords or re-issuing verified credentials.

A single error handler for all four cases may be appropriate for **public login responses**, yet the backend should still retain **distinct internal status codes** for auditing and workflows.

## 11. Response-timing security: 2026 advisory

Spring Security disclosed **CVE-2026-22746 — User Attribute Enumeration when Using DaoAuthenticationProvider** on **April 20, 2026**. Some pre-patch versions can leak enabled/expired/locked status via timing differences when status checks bypass a defense step.

Per the official advisory:

- Spring Security `6.5.0–6.5.9` fall within the affected range.
- **`6.5.10`** is the OSS fix in the 6.5 line.
- The example uses **`6.5.11`**, which is after the fix.
- Other branches have their own patch levels; choose a vendor-updated and actively supported version.

**Technical detail:** in patched builds, `setAlwaysPerformAdditionalChecksOnUser(...)` controls running additional checks even when pre-authentication status checks fail. The patched default prioritizes preventing timing leakage. Do not set it to `false` purely to "optimize performance" without a risk assessment, and do not assume all timing differences drop to zero.

**An exception can still leak information if returned verbatim to clients.** The timing patch does not replace public error policies, rate limiting, auditing, and user-enumeration testing.

Original advisory: https://spring.io/security/cve-2026-22746

## 12. Testing: status must be measured at the right layer

An application needs at least three test groups: **provider**, **filter/HTTP**, and **persisted state updates**.

### 12.1. Testing the provider like the console example

Every test constructs `UsernamePasswordAuthenticationToken.unauthenticated(username, password)` and calls the real manager/provider with `UserDetailsService`/`PasswordEncoder`. Assert exception types using JUnit assertions or equivalent. Demo `main` printed the key cases.

Tests should include:
- valid + right password → succeeds with `Authentication.isAuthenticated=true`;
- valid + wrong password → `BadCredentialsException`;
- unknown username → `BadCredentialsException` by default;
- locked → `LockedException`;
- disabled → `DisabledException`;
- account expired → `AccountExpiredException`;
- credentials expired → `CredentialsExpiredException`;
- locked + disabled → prioritized type is `LockedException`;
- account expired + credentials expired → `AccountExpiredException`;
- credentials expired + wrong password → `BadCredentialsException`;
- locked + wrong password → **does not** bypass lock; verify patched behavior.

### 12.2. HTTP integration tests

Using `MockMvc` with real Spring Security filters or end-to-end HTTP:

| Case | Provider expectation | HTTP expectation to verify in app |
| --- | --- | --- |
| No credentials for protected endpoint | Provider not necessarily called | Typically 401 or login redirect |
| Wrong password | `BadCredentialsException` | Form failure / Basic entry point handles |
| Locked | `LockedException` | No successful `Authentication`; public response per policy |
| Disabled | `DisabledException` | Protected controller never invoked |
| Expired account | `AccountExpiredException` | Normal endpoints denied |
| Expired password | `CredentialsExpiredException` | Only proper reset flow permitted |
| Right password, lacking authority | Authentication **succeeds** | Typically 403 at authorization |

**Note:** `@WithMockUser` sets up a mock user for authorization tests; it **does not** verify `DaoAuthenticationProvider`, BCrypt, or account-status exceptions. When testing this logic, requests must traverse the appropriate filter/provider or invoke the real manager.

### 12.3. Testing races, state changes, and old sessions

A production test suite should cover:

1. Toggling enabled/locked while a user sends concurrent login requests.
2. DB updates committed while caches still hold stale snapshots.
3. Multi-instance: node A locks user, node B still holds a cache entry.
4. Session logged in before the account was locked.
5. Bearer JWT still unexpired after the user was disabled.
6. Crossing account/credential expiration dates across UTC/time-zone boundaries.
7. Changing passwords and verifying the **old** password is no longer accepted.
8. Unlocking accounts and clearing failed-attempt counters per policy.
9. A malicious actor trying to lock someone else's account via many wrong password attempts.
10. Public responses revealing no exploitable difference between missing, locked, and disabled users.

## 13. Observability: classify internally while avoiding leaks

Separate **public messages** from **private telemetry**.

| Internal signal | Purpose | What must never be logged |
| --- | --- | --- |
| `auth.failure=BAD_CREDENTIALS` | Track guessing attacks or password typos | Plaintext passwords, password hashes |
| `auth.failure=ACCOUNT_LOCKED` | Track lockouts, assist unlocks | Raw usernames or unnecessary PII |
| `auth.failure=ACCOUNT_DISABLED` | Track disablement policies | Sensitive HR/admin details |
| `auth.failure=ACCOUNT_EXPIRED` | Track account term expirations | Unnecessary contract/customer data |
| `auth.failure=CREDENTIALS_EXPIRED` | Track credential reset/rotation requirements | Raw reset tokens, bearer tokens |
| `auth.failure=STORE_UNAVAILABLE` | Detect identity store outages | Connection strings with secrets |
| `auth.success=true` | Successful authentication counts | Full `Authentication.toString()`, session cookies |

Use only bounded-cardinality metric labels like `outcome`/`provider`; never embed usernames as metric labels. When per-account auditing is needed, use protected internal identifiers with appropriate retention. Public messages should curb user enumeration and self-service reset abuse.

### 13.1. Do not infer error codes from HTTP alone

An HTTP Basic API may return 401 for wrong password, locked, disabled, and expired alike depending on the entry point. Consequently, a dashboard counting only 401s cannot distinguish guessing attacks, account locks, policy expirations, or store outages.

Track exceptions at the manager/provider or via configured authentication failure events. When multiple providers exist, remember a later provider can supersede an earlier exception if fallback is allowed; for `AccountStatusException`, execution stops immediately.

## 14. Anti-patterns and fixes

| Anti-pattern | Problem | Fix |
| --- | --- | --- |
| Using `BadCredentialsException` for all account conditions | Loses locked/disabled/expiry semantics; may alter fallback | Return accurate `UserDetails` flags or matching exceptions |
| Inferring user exists upon seeing `BadCredentialsException` | Missing usernames may be masked into the same exception | Keep internal lookup classification; keep public responses uniform |
| Mapping DB `locked=true` to `isAccountNonLocked() == true` | Inverted boolean lets locked users in | Thoroughly test mappings and builders |
| Changing `isEnabled` in DB without handling UserCache/sessions | Account still accesses via stale snapshot/session | Invalidation and revocation per SLA |
| Throwing `LockedException` on wrong password as "anti-probing" | Breaks semantics and risks innocent lockouts | Design independent rate limiting/lockout |
| Returning exact "User linh is locked" in public APIs | Creates enumeration opportunity | Generic message or verified channel |
| Treating `CredentialsExpiredException` as "account deleted" | Incorrect: credentials expired, account may still exist | Verified reset/rotation flow |
| Treating `AccountExpiredException` like password expired | Renewal differs from changing password | Separate domain/account lifecycle from credential lifecycle |
| Building `Authentication.authenticated(...)` straight from client | Bypasses password/status checks | Use trusted manager/provider |
| Testing only `@WithMockUser` and claiming exceptions work | Skips real authentication path | Test provider/manager and HTTP filters |
| Mapping every failure to HTTP 403/423 | Not default behavior; may leak state | Design entry point/failure handler per policy |
| Ignoring CVE/timing on older releases | May leak locked/disabled/expired attributes | Upgrade to patched build and check timing/public messages |
| Using multiple providers without checking fallback | A later provider may accept credentials rejected by P1 | Define realms, order, exceptions, and trust boundaries |
| Returning raw exception messages/stack traces to browsers | Leaks internal design, usernames, or dependencies | Separate internal audits from public responses |

## 15. Self-check questions

**Question 1.** `user.isAccountNonLocked()` returns `false`, password is right. Which exception?  
**Answer:** `LockedException` in default `DaoAuthenticationProvider`.

**Question 2.** User has `isEnabled=false` and `isAccountNonExpired=false`. Which exception takes precedence?  
**Answer:** `DisabledException`, because the enabled pre-check runs before account expiry (with the default checker).

**Question 3.** User has `isCredentialsNonExpired=false` but the entered password is wrong. Which exception under standard checks?  
**Answer:** `BadCredentialsException`, because password verification fails before reaching the credentials-expiry post-check.

**Question 4.** User does not exist, yet the provider reports `BadCredentialsException`. Is that abnormal?  
**Answer:** No. `hideUserNotFoundExceptions=true` masks `UsernameNotFoundException` by default.

**Question 5.** Account is locked. Is merely swapping the session cookie enough to force a failed login?  
**Answer:** There is no single blanket answer. New password authentications reading fresh `UserDetails` will be locked. However, an **already-issued** session/token is a separate state: you need a dedicated invalidation policy rather than relying solely on new-login exceptions.

**Question 6.** Can `LockedException` cause `ProviderManager` to try another local provider?  
**Answer:** Not under standard behavior. Because it is an `AccountStatusException`, the manager stops immediately to prevent another provider from bypassing account status.

**Question 7.** Is it true that Spring Security automatically locks a username after five wrong password attempts?  
**Answer:** No such rule comes from `DaoAuthenticationProvider` alone; the application must build rate-limit/failed-attempt policies, handle concurrency, and persist valid state.

**Question 8.** Why does the demo use Spring Security 6.5.11 instead of 6.5.9?  
**Answer:** The 2026 advisory on timing when accounts are disabled/expired/locked places 6.5.9 in the affected range and 6.5.10 as the OSS fix. 6.5.11 is newer than that fix.

**Question 9.** Can you display a "Your password has expired" page on every public login request?  
**Answer:** You must assess user enumeration. A verified-identity channel can provide more detail; unverified clients should generally receive a generic message and safe recovery options.

**Question 10.** Why can a simultaneously locked account and wrong password still report `LockedException` on 6.5.11?  
**Answer:** The pre-authentication checker selects the locked status; the patch may run an auxiliary password check to reduce timing leaks, yet preserves the lock rejection decision. Never use the exception to infer whether the password was right or wrong.

**Question 11.** A user logged in before being disabled; will their next API request definitely throw `DisabledException`?  
**Answer:** Not guaranteed. If using an existing session or JWT, the request may not run `DaoAuthenticationProvider` again. A revocation/revalidation policy is required.

**Question 12.** Valid username, right password, yet missing authority `reports.read`. Is this `CredentialsExpiredException`?  
**Answer:** No. That is an **authorization failure**, typically HTTP 403, not an account-status authentication failure.

## 16. Pre-production checklist

- [ ] `UserDetails` maps all four booleans in the right direction; tests exist for lock/disable/both expirations.
- [ ] Passwords use a secure encoder, raw credentials are never logged, and tokens are never issued for invalid states.
- [ ] Using a Spring Security version patched per the latest advisory; verified BOM compatibility if using Spring Boot.
- [ ] Exceptions are classified accurately internally: bad credentials, missing user, status failure, store unavailable.
- [ ] Public login responses align with anti-user-enumeration and anti-brute-force policies.
- [ ] Lock, unlock, disable, account renewal, and password reset flows have authorization checks and auditing.
- [ ] DB updates evict `UserDetails` caches; concurrency and multi-instance behavior are handled if needed.
- [ ] Policy covers already-issued sessions/remember-me/tokens, never assuming a DB status change logs everyone out.
- [ ] Tested `ProviderManager` with multiple providers and fallback ordering.
- [ ] HTTP integration tests use real filters and verify actual responses rather than predicting from exception names alone.
- [ ] Monitoring tracks failure categories without leaking PII/secrets.

**Core message:** `BadCredentialsException` states that **the proof was rejected**; `LockedException`, `DisabledException`, `AccountExpiredException`, and `CredentialsExpiredException` represent **account/credential conditions preventing authentication from completing**. All of them prevent creating a successful `Authentication` result, yet they carry **different business semantics, check ordering, and fallback impact**. Managing accounts safely requires accurate backend exception classification, bounded public disclosures, and dedicated handling of existing sessions, tokens, and caches.

### Source references

- Spring Security 6.5 — `DaoAuthenticationProvider` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html
- Spring Security 6.5 — `AbstractUserDetailsAuthenticationProvider` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html
- Spring Security — `AccountStatusException` and subclasses: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AccountStatusException.html
- Spring Security — `CredentialsExpiredException`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/CredentialsExpiredException.html
- Spring Security — `DaoAuthenticationProvider` flow: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — `UserDetails` and user management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details.html
- Spring Security advisory **CVE-2026-22746**: https://spring.io/security/cve-2026-22746
