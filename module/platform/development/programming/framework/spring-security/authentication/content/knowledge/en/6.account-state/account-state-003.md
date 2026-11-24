# isAccountNonExpired and Account Expiration

In Spring Security, **`UserDetails.isAccountNonExpired()`** is a status flag answering the question: **"At authentication time, is this account still permitted to be used in terms of validity period?"** A value of **`true`** means *not expired*; a value of **`false`** means *expired* and normally leads to **`AccountExpiredException`** in `DaoAuthenticationProvider`'s standard username/password authentication flow.

Crucially: Spring Security **does not automatically infer an account's expiration date from the database, a JWT, or an HTTP session**. `isAccountNonExpired()` is only a boolean contract. The application must decide what counts as expired, store the necessary rules and data, compute the flag accurately when building `UserDetails`, and also handle sessions/tokens issued prior to the account's expiration time.

This lesson belongs to the **Account State** group in Spring Security Authentication. It covers the flag's semantics, boundaries with other states, expiration date design and time rules, entity → UserDetails mapping, provider behavior, a runnable Java 17 example, common mistakes, testing, and production concerns.

## 1. The isAccountNonExpired() contract

`org.springframework.security.core.userdetails.UserDetails` defines the method:

~~~java
boolean isAccountNonExpired();
~~~

This is **a Spring Security API signature**, not a standalone program. Under the contract:

- Returns **`true`** when the account is still valid and *not expired*.
- Returns **`false`** when the account has expired and cannot be authenticated through the standard username/password flow using that flag.
- The method name uses double negation: **`NonExpired`** means *not yet expired*. Do not invert the semantics when mapping from an `expired` or `expiresAt` column.
- The method itself states no date/time, performs no DB query, decides no grace period, and knows no subscription policy; all such logic belongs to the application.
- In modern `UserDetails` versions, the method has a default implementation returning `true` if a custom class does not override it. If your business has an expiration policy, **do not rely on that default** to treat accounts as valid.

In Spring Security's `org.springframework.security.core.userdetails.User` class, you can build `UserDetails` with the builder:

~~~java
UserDetails user = User.withUsername("linh")
        .password(encodedPassword)
        .authorities("notes:read")
        .accountExpired(false)
        .build();
~~~

This is an **illustrative integration snippet**; `encodedPassword` and imports must be supplied. Common confusion:

| Value passed to builder | `isAccountNonExpired()` value | Meaning |
|---|---|---|
| `.accountExpired(false)` | `true` | Account has not expired |
| `.accountExpired(true)` | `false` | Account has expired |

The builder setter is **`accountExpired(boolean)`**, whereas the `UserDetails` getter is **`isAccountNonExpired()`**. Their meanings are *inverted relative to each other*. A sign-inversion bug can let expired accounts log in or wrongly lock out all users.

### 1.1. This flag checks the "account", not just the password

Suppose a company leases a system account until November 30. The user still remembers the right password and the password has not expired, yet once account usage rights end, `isAccountNonExpired()` must return `false` per the corresponding policy. A right password is **necessary but not sufficient**.

Conversely, a user has an account valid until next year, yet the organization enforces password rotation every 90 days: that is **`isCredentialsNonExpired()`**, not account expiration. The system must distinguish them to guide the user to the appropriate action.

## 2. Comparing the four UserDetails flags

| Method | When returning `false` | Typical exception in `DaoAuthenticationProvider` | Business remediation |
|---|---|---|---|
| `isEnabled()` | Account not yet activated or disabled | `DisabledException` | Activate, verify conditions, manage status |
| `isAccountNonLocked()` | Account currently locked | `LockedException` | Unlock per policy, anti-brute-force |
| `isAccountNonExpired()` | **Account** usage term has ended | **`AccountExpiredException`** | Renew / change plan / re-approve usage rights |
| `isCredentialsNonExpired()` | Password/credentials have expired | `CredentialsExpiredException` | Change/reset credentials via a secure flow |

These flags are **conceptually independent**. An account can simultaneously be locked and past its expiration date; the system must define and prioritize the corresponding policy. `DaoAuthenticationProvider` typically checks lock/disabled/account expiry during pre-authentication, and credential expiry during post-authentication. When multiple states are invalid at once, do not build business logic assuming which exception is "guaranteed to be thrown first" across every provider or version.

More importantly, **`isAuthenticated()` on a successful `Authentication` does not mean the account stays valid forever**. It describes the result of a single authentication event; account status can change afterward.

### 2.1. Account expiration vs. session expiration and JWT expiration

~~~text
Account expiresAt = 2026-11-10T00:00:00Z
Session timeout  = 30 minutes of inactivity
JWT exp          = 2026-11-12T00:00:00Z
Password expiry  = 2026-12-01T00:00:00Z
~~~

These are **four different clocks/policies**:

- **Account expiration:** permission to use the account ends per the business model.
- **Session expiration:** lifetime/inactivity limit of a server-side session.
- **JWT expiration (`exp`):** token acceptance window under JWT validation; an unexpired token **does not prove the internal account is still unexpired**.
- **Credential expiration:** lifetime of a password or login credential.

A JWT that remains unexpired after an account expires can still be accepted by a resource server **if the server only checks signature/issuer/audience/exp without checking account status**. Likewise, a session created before the expiration date can persist until its own lifetime ends without separate checks or revocation.

**Blocking new logins does not automatically revoke existing sessions and tokens.** This is the most critical distinction when bringing `isAccountNonExpired()` to production.

## 3. Time rules: define "expired at which exact instant?"

A clear policy should store **the instant validity ceases** as an `Instant` (UTC instant), such as `account_expires_at`. We choose the rule:

- `expiresAt == null`: **no expiration**, if allowed by policy.
- `now.isBefore(expiresAt)`: **not yet expired**, account is still valid with respect to time.
- `now.equals(expiresAt)`: **expired**.
- `now.isAfter(expiresAt)`: **expired**.

Equivalently:

~~~java
boolean accountNonExpired =
        expiresAt == null || clock.instant().isBefore(expiresAt);
~~~

This is an **illustrative Java expression**, with `expiresAt` as `Instant` and `clock` as `Clock`; it does not check `enabled`, `locked`, or permissions. Choosing the half-open interval **`[start, expiresAt)`** avoids disputes at the exact expiration millisecond/nanosecond.

### 3.1. Concrete boundary table

Assuming `expiresAt = 2026-11-10T00:00:00Z`:

| Check time (UTC) | `now.isBefore(expiresAt)` | `isAccountNonExpired()` |
|---|---|---|
| 11/09 23:59:59.999 | `true` | `true` |
| 11/10 00:00:00.000 | `false` | **`false`** |
| 11/10 00:00:00.001 | `false` | `false` |

The "exact expiration instant" row must be specified in business documentation. If a plan advertises "valid through the end of November 10 Vietnam time," do not arbitrarily store `2026-11-10T00:00:00Z`, because that instant is morning in Vietnam, **not the end of the local day**. Convert from the defined `LocalDate` and `ZoneId` to the start of the next day, then store `Instant`:

~~~java
LocalDate lastAllowedDay = LocalDate.of(2026, 11, 10);
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant expiresAt = lastAllowedDay.plusDays(1)
        .atStartOfDay(businessZone)
        .toInstant();
~~~

This is an **illustrative Java JDK 17 snippet**; it does not build a Spring Security user. If a business spans multiple time zones, choose the zone per organization/plan contract rather than arbitrarily taking it from the client browser. For regions with DST, use `ZoneId` to handle calendar transitions; avoid blindly adding `24h` to every local date.

### 3.2. Use Instant and Clock instead of string or server-date comparisons

- Persist in the DB using a timestamp type with clear semantics, such as PostgreSQL `TIMESTAMPTZ`; it stores the actual instant rather than preserving a display time zone name.
- Use `Instant`/`Clock` for validity policies. Injecting `Clock` lets you test before, at, and after the boundary without depending on wall-clock time.
- Never compare dates as `String`s, and never rely on each pod's default `ZoneId.systemDefault()`.
- Define DB storage precision: if the database keeps microseconds while Java has nanoseconds, test boundaries at the actual precision.
- Synchronize system clocks across nodes and monitor clock skew. If policy demands an exact cutoff instant, consider centralized time calculation or bounding clock drift.

### 3.3. Grace period and renewal

Some products offer a 3-day grace period, auto-renewal, or a read-only phase. **That is a domain decision, not built into isAccountNonExpired.**

For example:

~~~text
Until 11/10: ACTIVE
11/10–11/13: GRACE_READ_ONLY (can log in, but actions are restricted)
From 11/13: EXPIRED
Payment renewal confirmed: ACTIVE with new expiresAt
~~~

If logins are permitted during the grace period, `isAccountNonExpired()` can remain `true` during that window **by policy**, while enforcing **read-only** constraints in the authorization/domain layer. If all access must stop on 11/10, the flag flips to `false` immediately. Do not use a single boolean to express multiple permission tiers; store explicit state/grace policy and map accurately.

## 4. Storage model and responsibility boundaries

Illustrative PostgreSQL schema:

~~~sql
CREATE TABLE accounts (
    id                 UUID PRIMARY KEY,
    login_name         TEXT NOT NULL UNIQUE,
    password_hash      TEXT NOT NULL,
    enabled            BOOLEAN NOT NULL DEFAULT TRUE,
    locked             BOOLEAN NOT NULL DEFAULT FALSE,
    account_expires_at TIMESTAMPTZ,
    password_expires_at TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

`account_expires_at` is the **account expiration date/time**, and `password_expires_at` is the credential expiration date/time. Both may be null if policy allows non-expiring accounts; the schema does not require every product to allow null. For systems using OIDC without internal passwords, `password_hash` may need to be nullable and linked via an identity table; the schema here illustrates only password-based authentication.

An entity/repository fetches the data, while **the policy mapping into UserDetails lives in the security service**:

~~~java
boolean accountNonExpired = account.getAccountExpiresAt() == null
        || clock.instant().isBefore(account.getAccountExpiresAt());

UserDetails details = User.withUsername(account.getLoginName())
        .password(account.getPasswordHash())
        .authorities(account.getAuthorities())
        .disabled(!account.isEnabled())
        .accountLocked(account.isLocked())
        .accountExpired(!accountNonExpired)
        .credentialsExpired(!credentialsNonExpired)
        .build();
~~~

This is an **integration snippet** (requiring `account`, `clock`, `credentialsNonExpired`, imports, and authorities policy), **not a standalone program**. The idea is to load the current account, compute **accountNonExpired**, and pass `.accountExpired(!accountNonExpired)` to the builder. `credentialsNonExpired` must be computed from the separate password policy, not copied from the account flag.

### 4.1. UserDetailsService is not a scheduler

`UserDetailsService.loadUserByUsername(...)` is typically called to load user data for `DaoAuthenticationProvider` during password login. It is **not automatically invoked at the exact moment an account expires**. If an account row has `account_expires_at` set to tomorrow, the service returns valid today; no timer automatically re-calls the service at 00:00 tomorrow and deletes every session.

Policy enforcement has two separate parts:

1. **New authentications**: when the provider loads `UserDetails`, validity is checked at authentication time.
2. **Active sessions/tokens**: middleware/authorization or session invalidation, token revocation, introspection, versioning, or access-token TTLs must satisfy business requirements on cutoff timing.

If the application uses stateless bearer tokens, `UserDetailsService` might **not even participate in requests**. Thus changing `isAccountNonExpired` in one class does not guarantee every login mechanism or API is protected.

### 4.2. Using caches can make flags stale

If the service caches a `UserDetails` instance computed today with `accountNonExpired=true`, tomorrow the cache may still return `true` unless refreshed. Never treat a boolean stored inside a cached principal as a self-updating time expression.

Options:

- Do not cache `UserDetails` results when exact status at login time is required.
- Cache source data containing `expiresAt`, but **recompute** the flag with `Clock` on every authentication; watch out for password hash/credential erasure on shared objects.
- Set a maximum TTL **not exceeding the time remaining until the account expires**, plus invalidation when an admin renews or locks.
- If policy requires blocking every request immediately, check expiration in a dedicated request/token layer or revoke sessions upon expiration.
- Test before/after boundaries, multi-node updates, and concurrency.

Do not disable `ProviderManager.eraseCredentialsAfterAuthentication` just to keep a mutable `UserDetails` containing a password hash in cache. Prefer separating the security principal from cached records and designing safe object ownership.

## 5. How does the provider handle expired accounts?

In standard username/password authentication:

~~~text
UsernamePasswordAuthenticationToken (request)
  -> ProviderManager
     -> DaoAuthenticationProvider
        -> UserDetailsService returns UserDetails
        -> pre-credential status checks
             locked? disabled? account expired?
        -> password verification
        -> credential expiration check
        -> returns successful Authentication
  -> SecurityContext managed by filter
~~~

If `UserDetails.isAccountNonExpired()==false`, the default pre-authentication checker of `AbstractUserDetailsAuthenticationProvider` throws **`AccountExpiredException`**. It belongs to the `AccountStatusException` / `AuthenticationException` family; therefore, the request **receives no successful Authentication** from that provider.

Do not confuse with:

- `CredentialsExpiredException`: password/credentials expired; the account itself may still be unexpired.
- `LockedException`: account is locked, usually due to a protective policy.
- `DisabledException`: account is not activated or is turned off.
- `BadCredentialsException`: wrong credentials or certain masked user-not-found cases.
- `ExpiredJwtException` or JWT `exp` checks: the token expired, which does **not** mean the account expired.

**Exceptions do not dictate HTTP status codes on their own.** HTTP Basic may respond with 401; form login may redirect; custom JSON login may return a generic error code. Do not assume "expired account" becomes HTTP 403 or 410 merely from the exception name.

### 5.1. Showing accurate errors without enabling user enumeration

Internally, you may want to distinguish `account_expired` from `password_wrong` to assist with renewal. However, differing public responses between existing and non-existent accounts can enable **account enumeration**. Decide based on your threat model:

- For public login: normally return a sufficiently generic message without revealing whether an email/account exists.
- For callers who have proved account ownership via an appropriate verification step: renewal instructions can be displayed.
- For support staff: log internal audit reasons with access control, minimize PII in logs, and never log raw passwords.
- Never allow clients to update `expiresAt` merely via a request field; all renewals must be verified through a trusted billing/admin workflow.

## 6. Runnable example — Java 17, Spring Security 6.3

The console example below **has no web server dependency**, yet uses Spring Security's real `DaoAuthenticationProvider` and `ProviderManager` to demonstrate `isAccountNonExpired`. Instead of the wall clock, it uses `Clock.fixed(...)` at `2026-11-05T00:00:00Z`, so results do not change depending on when you run it.

Cases include an unexpired account, an account with no expiration, an expired account, an account expiring **right at check time**, disabled, locked, expired password, non-existent username, and wrong password.

### 6.1. Project structure and Gradle

~~~text
account-expiry-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/AccountExpiryDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'account-expiry-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.3.8'
    implementation 'org.springframework.security:spring-security-crypto:6.3.8'
}

application {
    mainClass = 'example.AccountExpiryDemo'
}
~~~

This sample pins Spring Security 6.3.8 for learning purposes. Real Spring Boot projects normally rely on Boot's dependency management. Requires JDK 17+, compatible Gradle, and network access to download dependencies on the first run; no HTTP server, JPA, or PostgreSQL is required.

### 6.2. Complete Java code

Create `src/main/java/example/AccountExpiryDemo.java`:

~~~java
package example;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class AccountExpiryDemo {

    record Account(
            String username,
            String passwordHash,
            Instant accountExpiresAt,
            boolean enabled,
            boolean nonLocked,
            boolean credentialsNonExpired) {
    }

    public static void main(String[] args) {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-05T00:00:00Z"),
                ZoneOffset.UTC);
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        String passwordHash = encoder.encode("demo-pass");

        Instant future = Instant.parse("2026-11-06T00:00:00Z");
        Instant past = Instant.parse("2026-11-04T00:00:00Z");
        Instant boundary = clock.instant();

        Map<String, Account> rows = Map.of(
            "active", new Account(
                "active", passwordHash, future, true, true, true),
            "never", new Account(
                "never", passwordHash, null, true, true, true),
            "expired", new Account(
                "expired", passwordHash, past, true, true, true),
            "boundary", new Account(
                "boundary", passwordHash, boundary, true, true, true),
            "disabled", new Account(
                "disabled", passwordHash, future, false, true, true),
            "locked", new Account(
                "locked", passwordHash, future, true, false, true),
            "password-old", new Account(
                "password-old", passwordHash, future, true, true, false)
        );

        UserDetailsService users = username -> {
            Account account = rows.get(username);
            if (account == null) {
                throw new UsernameNotFoundException("Unknown account");
            }

            // At exact expiresAt boundary: account is expired.
            boolean accountNonExpired =
                    account.accountExpiresAt() == null
                    || clock.instant().isBefore(
                            account.accountExpiresAt());

            // Builder takes "expired", opposite of "nonExpired".
            return User.withUsername(account.username())
                    .password(account.passwordHash())
                    .authorities("notes:read")
                    .disabled(!account.enabled())
                    .accountLocked(!account.nonLocked())
                    .accountExpired(!accountNonExpired)
                    .credentialsExpired(
                            !account.credentialsNonExpired())
                    .build();
        };

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);

        AuthenticationManager manager =
                new ProviderManager(List.of(provider));

        attempt(manager, "active", "active", "demo-pass");
        attempt(manager, "never", "never", "demo-pass");
        attempt(manager, "expired", "expired", "demo-pass");
        attempt(manager, "boundary", "boundary", "demo-pass");
        attempt(manager, "disabled", "disabled", "demo-pass");
        attempt(manager, "locked", "locked", "demo-pass");
        attempt(manager, "password-old", "password-old", "demo-pass");
        attempt(manager, "unknown", "unknown", "demo-pass");
        attempt(manager, "active/wrong", "active", "wrong-pass");
    }

    private static void attempt(
            AuthenticationManager manager,
            String label,
            String username,
            String rawPassword) {

        Authentication request =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, rawPassword);

        try {
            Authentication result = manager.authenticate(request);
            System.out.println(label + " -> OK: "
                    + result.getName()
                    + ", authenticated=" + result.isAuthenticated());
        } catch (AuthenticationException ex) {
            System.out.println(label + " -> "
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

**Code breakdown:**

1. `Account` models a business entity. The `accountExpiresAt` field can be null to represent "no expiration date" per the agreed policy.
2. `Clock.fixed` guarantees determinism. Regardless of which year you run it, `clock.instant()` stays `2026-11-05T00:00:00Z`.
3. `UserDetailsService` loads the account, computes `accountNonExpired` from `Instant`, and passes `.accountExpired(!accountNonExpired)` into `User.UserBuilder`.
4. The disabled, locked, and credentials-expired flags are set **separately** to prove each scenario yields a distinct failure type.
5. `DaoAuthenticationProvider` checks status/password and returns a successful `Authentication` when all conditions hold.
6. `ProviderManager` coordinates the provider; the program catches `AuthenticationException` and prints only the class name to illustrate the outcome. In a real server, do not unconditionally return raw exception names in public APIs.
7. The service builds a fresh `UserDetails` per lookup instead of sharing a single mutable instance holding a password hash between cache and principal.

### 6.3. How to run and stdout

Inside the `account-expiry-demo` directory, once a compatible Gradle Wrapper is present:

~~~bash
./gradlew run
~~~

If you have no wrapper but have a compatible Gradle installed, run `gradle run`. On Windows PowerShell with a wrapper, you can run `.\gradlew.bat run`.

Output **from the program's System.out.println calls** (excluding Gradle logs):

~~~text
active -> OK: active, authenticated=true
never -> OK: never, authenticated=true
expired -> AccountExpiredException
boundary -> AccountExpiredException
disabled -> DisabledException
locked -> LockedException
password-old -> CredentialsExpiredException
unknown -> BadCredentialsException
active/wrong -> BadCredentialsException
~~~

The `boundary` line is important: at **`now == expiresAt`**, `isBefore` evaluates to `false`, so the account is already expired. The `unknown` line shows that `DaoAuthenticationProvider` by default masks a non-existent username as a bad-credentials error. BCrypt hashes use random salts so hash bytes vary across runs, but the authentication outcomes and stdout above remain consistent with the demo logic.

**Goal of the example:** observe the exact effect of `isAccountNonExpired` in a fresh authentication flow. Do not treat the demo as a full subscription management system: there is no payment renewal, transactions, database migrations, email, MFA, sessions/JWTs, auditing, or revocation.

### 6.4. Try two variations

**Variation A — wrong sign in the builder:** change `.accountExpired(!accountNonExpired)` to `.accountExpired(accountNonExpired)`. The result inverts the policy: active accounts get treated as expired, and expired accounts get treated as valid. Try this only in a learning project to recognize the bug.

**Variation B — using the wall clock:** replace `Clock.fixed(...)` with `Clock.systemUTC()` and set `accountExpiresAt` to a specific future instant; test near the boundary to see how bugs easily appear with wall-clock time. For unit tests, prefer fixing and injecting `Clock` instead of calling `Thread.sleep` to wait for the boundary.

## 7. Renewal, recovery, and state updates

When an expired account is renewed, the workflow usually includes:

1. Authenticating the actor/mechanism performing the renewal, e.g., an admin, a verified billing event, or a validly signed webhook.
2. Applying the renewal policy: compute the new date based on the plan, contract terms, grace period, or current time; **never trust `expiresAt` from an unauthorized client**.
3. Updating the record in a transaction, auditing reason/actor/timestamp, and ensuring idempotency on webhook retries.
4. Invalidating caches/sessions or re-issuing tokens per strategy so the new state takes effect; otherwise, an old principal may still appear expired even though the database was renewed.
5. Accounting for independent factors like locked/disabled accounts: renewing an account **does not automatically unlock** or re-enable a disabled account.

### 7.1. Evaluate current state rather than a pre-stored flag

If you only store `account_non_expired = true` in the database at signup, it will not flip to `false` automatically as time passes. Store `expiresAt` as the source of truth and compute validity at check time; or run a scheduler updating status **with a guarantee against lag** when policy demands it.

A domain approach:

~~~java
public boolean isAccountNonExpiredAt(Instant now) {
    return accountExpiresAt == null
            || now.isBefore(accountExpiresAt);
}
~~~

This is an **illustrative method snippet on an assumed entity/value object**, not a standalone program. Benefit: ensures time boundaries can be unit-tested. Any layer deciding current state must use the proper data source and clock, rather than blindly relying on a snapshot from yesterday's login.

### 7.2. When expiration changes access mid-use

Suppose a user logs in at 23:55 and the account expires at 00:00. If the product promises "access stops immediately at 00:00," **using `isAccountNonExpired()` only during password login is not enough**:

| Mechanism | What must be added when an account expires |
|---|---|
| Server-side session | Check account status on required requests, invalidate/revoke sessions, or apply matching timer/policy |
| Stateless JWT | Short-lived access tokens and/or account-status lookups, denylist/version/introspection per required immediacy |
| API key | Check expiry/revocation of both the key and linked account; do not infer an unexpired account from an unexpired key |
| Long-running job | Define whether permissions are snapshotted at start or re-checked before sensitive operations |
| WebSocket/streaming | Policy to close connections or re-authorize after account expiration |
| Cached UserDetails | TTL/invalidation aligned with `expiresAt`; avoid keeping stale flags past expiration |

Trade-offs between "per-request" checks and performance must be designed, load-tested, and explicitly stated in security SLAs. If a cache has a 5-minute TTL, you cannot claim instant blocking in all cases without an auxiliary revocation mechanism.

## 8. Multi-tenant design and multiple identity sources

An employee may belong to multiple organizations: **their personal account is unexpired**, yet **their membership in tenant A has expired** while tenant B remains active. If the rule applies at the membership level, do not flip the user's global `isAccountNonExpired()` to `false` for all organizations; check tenant scope in authorization/domain logic:

~~~text
User account       : ACTIVE, non-expired
Membership tenant A: EXPIRED
Membership tenant B: ACTIVE
JWT / session      : user identity
Authorization      : checks permissions within the accessed tenant
~~~

Similarly, "the organization's subscription expired" might block paid features without blocking all user logins (for instance, still allowing access to the billing page). **Account expiry** and **subscription/tenant entitlements** should be mapped via explicit policies instead of using a single boolean to solve everything.

With OAuth2/OIDC login or JWT resource servers, the default principal may be `OidcUser` or `Jwt` instead of `UserDetails`. In those cases `isAccountNonExpired()` is **not automatically called** as it is in `DaoAuthenticationProvider`. If you must block expired local accounts, map the external identity to the internal account and enforce expiry via an authentication converter/provider or appropriate authorization/checks — never rely on a method that is not in the actual flow.

## 9. Common mistakes and fixes

| Mistake | Consequence | Fix |
|---|---|---|
| Writing `return now.isAfter(expiresAt);` for `isAccountNonExpired` | Returns true when expired | Use `now.isBefore(expiresAt)` for exclusive boundary policy |
| Passing `.accountExpired(accountNonExpired)` | Inverts flag in `UserBuilder` | Pass **`!accountNonExpired`** |
| Using `LocalDate.now()` with arbitrary server timezone | Expiration drifts across nodes | Use `Instant` and `Clock`, specify `ZoneId` for business dates |
| Using `<=` instead of `<` at expiration instant | Account remains valid past cutoff | Define `[start, expiresAt)` and test right at boundary |
| Hardcoding `isAccountNonExpired=true` in custom UserDetails | Account expiry never enforced | Map from policy and current data |
| Treating expired account as expired password | Sends users to password reset when they need renewal | Keep the two flags/exceptions separate |
| Treating JWT `exp` as account expiry | Token stays valid while account is expired | Check/revoke per account policy |
| Assuming `isAccountNonExpired=false` immediately kills all sessions | Requests with old sessions can continue | Implement session/token revocation and live checks |
| Caching already-valid `UserDetails` past expiration | New logins may use stale state | Cap TTL at expiry, invalidate, or recompute state |
| Updating `expiresAt` from unauthenticated requests | Users renew themselves | Enforce authorization and billing/admin verification |
| Storing "valid through end of day" as "start of day" | Blocks users too early | Convert business date to start of next day in chosen timezone |
| Merging whole-account expiry with tenant membership | Wrongly blocks access in other organizations | Distinguish identity, membership, and entitlement |
| Printing raw `AccountExpiredException` on public login | May aid account enumeration | Controlled responses, assistance after ownership verification |

## 10. Test matrix

A production test suite should cover **exact time boundaries** and **enforcement scope**:

| Scenario | Outcome |
|---|---|
| `expiresAt=null` when policy allows non-expiring | `isAccountNonExpired()==true` |
| `now < expiresAt` | Account not yet expired |
| `now == expiresAt` | Account **expired** under `[start,expiresAt)` policy |
| `now > expiresAt` | Account expired |
| Right password, expired account | `AccountExpiredException` in standard provider |
| Right password, valid account, expired credentials | `CredentialsExpiredException` |
| Valid account, but disabled/locked | `DisabledException`/`LockedException` |
| Non-existent user | Does not accidentally leak info via public response |
| Account renewed before/after boundary | Cache and new logins reflect new expiration date |
| Logged in before expiry, request after expiry | Session/JWT handled per policy SLA |
| Nodes in different timezones | Same `Instant` yields identical outcome |
| Business date spanning DST | Local date converts to `Instant` accurately per `ZoneId` |
| Tenant A subscription expired, tenant B active | Only tenant A permissions affected if policy is membership-scoped |
| OIDC/JWT not using UserDetailsService | Account expiry still enforced in the appropriate layer |
| `expiresAt` updated concurrently with token refresh | Does not issue tokens beyond permitted policy |
| Expired account renewed by admin | Authorized/transactional/audited; does not arbitrarily unlock |

You can unit test date/time logic with `Clock.fixed`, integration test `DaoAuthenticationProvider` with active/expired users, and test HTTP with Spring Security test support. Do not use `Thread.sleep` as your primary approach: tests become slow and flaky.

### 10.1. Knowledge check

**Question 1.** Does `isAccountNonExpired()==false` mean the password has expired?  
**Answer:** No. It indicates the **account** term expired; credential expiry is in `isCredentialsNonExpired()`.

**Question 2.** What does `User.withUsername(...).accountExpired(true)` make `isAccountNonExpired()` return?  
**Answer:** `false`.

**Question 3.** If current time equals `expiresAt` exactly, what should be returned?  
**Answer:** Under the `[start, expiresAt)` validity interval policy, return `false`. The policy must be documented explicitly.

**Question 4.** Why inject `Clock`?  
**Answer:** To compute time consistently and run deterministic tests before, at, and after boundaries.

**Question 5.** Account expires today, JWT expires tomorrow. Will every request be blocked?  
**Answer:** Not automatically. You need account-status checks or token revocation/bounds per policy; JWT `exp` is a separate timer.

**Question 6.** Two tenants share one account, and only tenant A's subscription expired. Should you set `isAccountNonExpired=false` globally?  
**Answer:** Not necessarily. If expiry is at the membership/entitlement level, restrict tenant A's permissions instead of expiring the global account identity.

**Question 7.** If a cache holds a `UserDetails` created yesterday, what can happen when the expiration hour arrives?  
**Answer:** The boolean flag on the old instance may still be true. You must manage cache TTL/invalidation or recompute from `expiresAt` at check time.

**Question 8.** Should clients be allowed to write `account_expires_at` to renew?  
**Answer:** Not by default. Renewal is a privileged operation requiring workflow/billing verification and audit logging.

## 11. Project adoption checklist

- [ ] Defined whether account expiry is needed and whether it applies to users, memberships, or tenant entitlements.
- [ ] Stored expiration dates with clear semantics using `Instant` and a timezone policy for business dates.
- [ ] Defined what `expiresAt=null` means; avoid differing interpretations across services.
- [ ] Fixed the `now < expiresAt` boundary and tested `before`, `equal`, and `after`.
- [ ] Mapped `isAccountNonExpired` accurately to `User.UserBuilder.accountExpired(!nonExpired)`.
- [ ] Kept enabled, locked, account expiration, and credential expiration separate.
- [ ] Added integration tests proving `AccountExpiredException` when username/password are valid but the account is expired.
- [ ] Prevented leaking account existence in public responses; ensured safe auditing for support.
- [ ] Verified JWT/OIDC/session mechanisms actually enforce account expiry, not just form login.
- [ ] Prevented stale cached status past expiration; designed TTLs, invalidation events, or live checks.
- [ ] Ensured renewals have authorization, transactions, auditing, and idempotency; never conflated renewal with auto-unlocking.
- [ ] Tested multi-tenant, multi-node clocks, grace periods, and in-flight requests at expiration time.

**Remember:** `isAccountNonExpired()` is **a boolean answer at authentication time**. When a system must cut off access right on the expiration date, you must combine **an accurate time model**, **proper UserDetails mapping**, and **a policy for already-issued sessions/tokens**. Do not mistake a flag on `UserDetails` for an automated engine managing the entire account lifecycle.

### Official documentation

- [Spring Security — UserDetails JavaDoc](https://docs.spring.io/spring-security/site/docs/6.4.4/api/org/springframework/security/core/userdetails/UserDetails.html): semantics and values of `isAccountNonExpired()`.
- [Spring Security — User.UserBuilder JavaDoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/userdetails/User.UserBuilder.html): `accountExpired(boolean)`, `credentialsExpired(boolean)`, `disabled`, and `accountLocked`.
- [Spring Security — AbstractUserDetailsAuthenticationProvider JavaDoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html): account, password, and account-status check steps.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): loading `UserDetails` and checking passwords.
- [Spring Security — AccountExpiredException](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AccountExpiredException.html): exception for expired accounts.
- [Java SE — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): injectable/fixed clock for testing.
