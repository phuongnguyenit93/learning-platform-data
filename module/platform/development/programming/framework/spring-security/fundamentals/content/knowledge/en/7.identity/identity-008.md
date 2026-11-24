# Account Locked, Disabled, and Expired States

A user may enter the **correct password** and still not be allowed to log in. For example, Mai enters the exact password into an internal system; however, her account is temporarily locked due to multiple wrong login attempts, disabled by an administrator, or past its allowed usage period. Another case: the account is still active, yet the **password has expired** according to the organization's policy.

Spring Security distinguishes these situations using status attributes on `UserDetails`. Those statuses are not simply "right or wrong login" and do not mean roles or data access permissions.

This lesson helps you clearly understand **account locked**, **disabled**, **account expired**, and **credentials expired**; how Spring Security checks them; how to map business data; how to handle already-logged-in sessions; and common security mistakes.

The examples use **Java 17+** and real classes from Spring Security 7.1.2. For Spring Boot projects, use the starters and Spring Security versions managed by the Boot BOM rather than pinning standalone versions separately.

## 1. Four Different Questions About the Same User

Suppose the database has an account `mai`. Before allowing a username/password authentication attempt, the system may need to answer:

1. **Is the account enabled?** An unverified account or one suspended by an administrator may be in a disabled state.
2. **Is the account currently locked?** A temporary lock or anti-brute-force defense may leave the account locked.
3. **Is the account still within its valid lifetime?** A seasonal account or contract-based access may expire at a stored timestamp.
4. **Are the login credentials still accepted?** A password may have expired or be required to change after a security incident.

All four are **separate rules**. An account can be both disabled and locked; an expired account can still have a valid password; an active account can still have expired credentials.

| Situation | Interpretation | Typical management action |
| --- | --- | --- |
| Locked | Temporarily or conditionally prevents login | Unlock upon expiry, after verification, or by administrative decision |
| Disabled | Subject is not permitted to use the account | Enable after verification; or prohibit by administrative decision |
| Account expired | Account usage period has passed | Extend usage period if approved |
| Credentials expired | Password or equivalent evidence must be changed/renewed | Verified password-change/reset workflow |
| Active, no restrictions | None of the status conditions above block login | Still must verify password and access permissions |

Names like `LOCKED`, `DISABLED`, and `EXPIRED` are **concepts**; Spring Security does not automatically create SQL tables or update statuses for you. The application must define the data source, state transition timing, and appropriate re-enable rules.

## 2. UserDetails Has Four Negated Flags

In Spring Security, `org.springframework.security.core.userdetails.UserDetails` describes a user's data used by certain username/password authentication providers. Four key methods:

~~~java
boolean isAccountNonLocked();
boolean isEnabled();
boolean isAccountNonExpired();
boolean isCredentialsNonExpired();
~~~

Read the **Non** in the method names carefully: three of the four flags express the **negation of an adverse condition**. Therefore, a `true` value normally means that condition **allows** authentication to proceed.

| `UserDetails` method | `true` means | `false` means | Related status exception |
| --- | --- | --- | --- |
| `isAccountNonLocked()` | Account is not locked | Account is locked | `LockedException` |
| `isEnabled()` | Account is enabled | Account is disabled | `DisabledException` |
| `isAccountNonExpired()` | Account has not expired | Account has expired | `AccountExpiredException` |
| `isCredentialsNonExpired()` | Login credentials have not expired | Credentials have expired | `CredentialsExpiredException` |

All four exceptions belong to the `AuthenticationException` family, specifically the `AccountStatusException` group. They help the authentication component express the rejection reason **internally inside the system**; **it does not mean** the application should return raw exception names to external clients.

A custom `UserDetails` implementation does not automatically infer status from a database. If you do not override them, in recent Spring Security versions these status methods **default to returning `true`**; meaning locking/expiration logic will have no effect unless your adapter maps domain state into them.

### Do Not Confuse isEnabled with isAuthenticated

- `userDetails.isEnabled()`: **account status property** supplied by the data source.
- `authentication.isAuthenticated()`: **state of the Authentication object** according to the authentication mechanism.
- `authentication.getAuthorities()`: **granted permissions** evaluated by policies at the authorization step.

An enabled user is not necessarily logged in. An `Authentication` created when a user was enabled does not guarantee the account is still enabled **at the current moment**.

## 3. Locked, Disabled, and Expired Differ in Cause and Lifecycle

### 3.1. Locked — Account Lockout

Locking is typically used when there is a security risk or temporary pause: too many wrong login attempts, anomalous activity detected, or an administrator temporarily locking an account for investigation.

Variants:

- **Temporary lock:** has a `lockedUntil` field; once that time passes, login is allowed again if other conditions hold.
- **Manual lock:** has a `manuallyLocked` flag or status requiring an authorized person to unlock.
- **Conditional lock:** unlocked only upon completing identity verification, MFA, or a support workflow.

For example, `lockedUntil=2026-11-05T10:00:00Z` does not mean the system must run a job at that exact timestamp. An implementation can compute `isAccountNonLocked()` by comparing `Instant.now(clock)` against `lockedUntil`; once current time reaches or passes the deadline, the time-based lock condition no longer blocks.

**Locking does not mean deleting the password hash, changing roles, or deleting the account.** If poorly designed, automatic locking based solely on username can become a denial-of-service vector: an attacker intentionally submits wrong passwords to lock legitimate users out. Combine multi-signal rate limiting, anomaly alerts, and proper recovery policies.

### 3.2. Disabled — Account Deactivation

This is usually a business or administrative decision: not yet activated, employee offboarding, user-requested pause, policy violation, or workflow-driven account closure.

Example:

~~~text
account_id = 101
username   = "mai"
enabled    = false
reason     = "ADMIN_SUSPENSION"
updated_at = "2026-11-04T08:20:00Z"
~~~

`reason` is business data you design, not a standard `UserDetails` property. You may also need to record who decided, the request source, timestamp, and recovery path. Never return internal reasons or investigation details to unauthenticated callers.

**Disabled is usually a longer-term intentional state than temporary lock**, though not an immutable rule: organizations may use different names. What matters is having a clear mapping from domain `AccountStatus` to `isEnabled()` or the corresponding policy.

### 3.3. Account Expired — Account Lifetime Ended

For example, a contractor's account only stays active until the contract end date; or an account granted product access for a fixed window.

Distinguish:

- **Account expiration:** authentication eligibility of the **identity/account** by policy.
- **Subscription expiration:** eligibility to use a **service plan**. Subscription expiration does not always forbid login. Some apps still let users log in to renew billing or export their own data.
- **Membership expiration:** membership **within a tenant/project** has expired; the user may still log in and access other tenants.

Therefore **do not automatically map** every `planExpiresAt` to `isAccountNonExpired=false`. Choose the right business boundary: should it block **all authentication**, or only deny certain permissions/resources?

### 3.4. Credentials Expired — Login Credentials Expired

This occurs when a password or authentication credential is no longer accepted by policy. For example, an organization forces a password reset after detecting a breach or at the end of a configured rotation period.

Things to distinguish:

- Expired password **differs from** expired account.
- Expired password **differs from** a JWT access token expiring after 15 minutes. JWT expiration (`exp`) is a token check, and does not automatically map to `UserDetails.isCredentialsNonExpired()`.
- Expired password **differs from** wrong password. `PasswordEncoder.matches` may succeed cryptographically, yet policy still rejects completing login.
- Required password change **differs from** the user already having changed the password. A verified change/reset flow is required.

A common trap: setting `isCredentialsNonExpired=false` blocks the normal password login flow. **Do not assume** the user still holds a full `Authentication` to visit `/change-password` if it requires `authenticated()`. Design a password-change/reset path with appropriate proof or a separately verified restricted authentication mechanism, avoiding locking out all flows with no way to recover.

## 4. Where Does Spring Security Check These Flags?

In the common username/password flow with `DaoAuthenticationProvider`:

~~~text
Request submits username + password
            |
            v
UsernamePasswordAuthenticationToken (unauthenticated)
            |
            v
AuthenticationManager / ProviderManager
            |
            v
DaoAuthenticationProvider
            |
            +--> UserDetailsService.loadUserByUsername(username)
            |       -> UserDetails (username, hash, flags, authorities)
            |
            +--> Account status checks
            |       locked / disabled / account expired
            |
            +--> PasswordEncoder verifies password
            |
            +--> Credentials expired status check
            |
        +---+---+
        |       |
     Success  Failure
        |       -> AuthenticationException
        |
        v
Authenticated Authentication
        |
        v
Authorization per request/resource
~~~

The diagram above is a **logical flow model**, not an exact execution sequence across every patch/provider. Timing-leak mitigation patches may execute additional password comparisons even when an account status is disallowed. Never rely on check order or response timing to infer account existence/status.

In `AbstractUserDetailsAuthenticationProvider`, the default check groups are `DefaultPreAuthenticationChecks` (locked, disabled, account expired) and `DefaultPostAuthenticationChecks` (credentials expired). `DaoAuthenticationProvider` handles password verification and may apply extra safeguards. Custom providers do not necessarily use these status flags automatically.

### An Exception Does Not Mean the Server Must Return the Raw Reason

Example:

| Internal reason | Exception that may be created | Response for external users |
| --- | --- | --- |
| Account locked | `LockedException` | May use a unified login-failure message |
| Account disabled | `DisabledException` | May use a unified login-failure message |
| Account expired | `AccountExpiredException` | Renewal message/flow depending on trust level and business rules |
| Password expired | `CredentialsExpiredException` | Appropriate reset/verification workflow without leaking secrets |
| Wrong password | `BadCredentialsException` | Authentication failed message |

With an HTTP Basic API, failed authentication typically leads to **401 Unauthorized** via `AuthenticationEntryPoint`; with form login it may redirect to a login error page. This is a web-layer choice, **not** `UserDetails` sending HTTP statuses itself.

For an authenticated API caller lacking resource access, the result is typically **403 Forbidden**. Keep **authentication errors** and **authorization errors** cleanly separated; do not return `403` for all account states merely for coding convenience.

## 5. Inverted Flags in User.withUsername(...)

Spring Security provides a convenient builder for examples and in-memory users:

~~~java
UserDetails user = User.withUsername("mai")
        .password("{noop}demo-only")
        .roles("USER")
        .accountLocked(true)
        .disabled(false)
        .accountExpired(false)
        .credentialsExpired(false)
        .build();
~~~

Read the **builder method names** carefully:

| `User.UserBuilder` method | Setting `true` configures | `UserDetails` reads |
| --- | --- | --- |
| `.accountLocked(true)` | User **is locked** | `isAccountNonLocked() == false` |
| `.disabled(true)` | User **is disabled** | `isEnabled() == false` |
| `.accountExpired(true)` | User **is expired** | `isAccountNonExpired() == false` |
| `.credentialsExpired(true)` | Credentials **are expired** | `isCredentialsNonExpired() == false` |

The builder uses **adverse-condition** phrasing, while three of the interface methods contain **Non**. This is an easy place to invert logic by mistake:

~~~java
// WRONG: disabled=true actually disables an active account.
.disabled(account.isActive())

// RIGHT if account.isActive() truly means enabled.
.disabled(!account.isActive())
~~~

The builder in the demo intentionally uses `{noop}` to avoid setting up a full password system. **Never store production passwords with `{noop}`**; in real apps, use a proper `PasswordEncoder` and securely generated password hashes.

## 6. Standalone Java 17+ Example: Observing All Four States

This example uses real `spring-security-core` to construct `UserDetails` and uses `AccountStatusUserDetailsChecker` to inspect statuses. Each user has **exactly one disallowed status flag**, so the output is clear and does not depend on ordering when multiple errors coexist.

This is a **status-checker API lab**, not a full web login: the program receives no passwords over HTTP, does not call `AuthenticationManager`, and creates no login session.

### 6.1. Create the Gradle Project

Create `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:7.1.2'
}

application {
    mainClass = 'AccountStatusDemo'
}
~~~

Spring Security 7.1.2 in the example fits Java 17+. If using Spring Boot starters, **do not pin `spring-security-core` separately** like this; let the Boot BOM manage compatible modules.

Create `src/main/java/AccountStatusDemo.java`:

~~~java
import org.springframework.security.authentication.AccountStatusUserDetailsChecker;
import org.springframework.security.authentication.AccountStatusException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;

public class AccountStatusDemo {

    private static UserDetails user(
            String username,
            boolean locked,
            boolean disabled,
            boolean accountExpired,
            boolean credentialsExpired) {
        return User.withUsername(username)
                .password("{noop}example-only")
                .roles("USER")
                .accountLocked(locked)
                .disabled(disabled)
                .accountExpired(accountExpired)
                .credentialsExpired(credentialsExpired)
                .build();
    }

    private static void check(String name, UserDetails user) {
        var checker = new AccountStatusUserDetailsChecker();
        try {
            checker.check(user);
            System.out.println(name + " -> ALLOWED");
        } catch (AccountStatusException exception) {
            System.out.println(name + " -> "
                    + exception.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        check("active", user("active", false, false, false, false));
        check("locked", user("locked", true, false, false, false));
        check("disabled", user("disabled", false, true, false, false));
        check("account-expired",
                user("account-expired", false, false, true, false));
        check("credentials-expired",
                user("credentials-expired", false, false, false, true));
    }
}
~~~

From the project directory, with JDK 17+ and a compatible Gradle version, run:

~~~bash
gradle run --quiet
~~~

Expected output of the program itself:

~~~text
active -> ALLOWED
locked -> LockedException
disabled -> DisabledException
account-expired -> AccountExpiredException
credentials-expired -> CredentialsExpiredException
~~~

Analysis:

- `active`: all four flags satisfy requirements, so `check` throws no exception. The string `ALLOWED` **only means passing status checks**; it proves neither a valid password nor all permissions.
- `locked`: `isAccountNonLocked()==false`, throwing `LockedException`.
- `disabled`: `isEnabled()==false`, throwing `DisabledException`.
- `account-expired`: `isAccountNonExpired()==false`, throwing `AccountExpiredException`.
- `credentials-expired`: `isCredentialsNonExpired()==false`, throwing `CredentialsExpiredException`.

`user.getPassword()` is never printed in the example; the source uses a mock `{noop}` password solely to construct test data. In production, password hashing and status policies are two separate layers.

**Note:** `AccountStatusUserDetailsChecker` is a `UserDetails` checking utility. `DaoAuthenticationProvider` has its own pre/post checks; do not infer that calling the checker alone performs full password authentication or replaces a provider.

## 7. Mapping Domain State to UserDetails

In a real application, data might include:

~~~text
accounts
  id
  username
  password_hash
  enabled
  manually_locked
  locked_until
  account_expires_at
  password_changed_at
  require_password_change
  tenant_id
  status_changed_at
  status_changed_by
  status_reason
~~~

This is a **suggested schema**, not a table Spring Security creates for you. Not every app needs every column. You can split `login_credentials` or `account_restrictions` to separate responsibilities cleanly.

An illustrative Java domain type:

~~~java
public record AccountState(
        long accountId,
        String username,
        boolean enabled,
        boolean manuallyLocked,
        java.time.Instant lockedUntil,
        java.time.Instant accountExpiresAt,
        java.time.Instant credentialsExpiresAt
) {}
~~~

`lockedUntil` and `accountExpiresAt` model **time-based** rules, while `enabled` reflects activation status. Prefer `Instant`/UTC for technical timestamps to avoid timezone drift, then format in the user's timezone when displaying.

A state transition policy:

~~~java
// Code fragment in service/adapter; not a standalone class.
boolean nonLocked(AccountState a, Instant now) {
    boolean temporaryLockActive =
            a.lockedUntil() != null && now.isBefore(a.lockedUntil());

    return !a.manuallyLocked() && !temporaryLockActive;
}

boolean nonExpired(Instant expiresAt, Instant now) {
    return expiresAt == null || now.isBefore(expiresAt);
}
~~~

Here, **at the exact expiration instant**, `now.isBefore(expiresAt)` is `false`. By convention `expiresAt` is the moment it **ceases** to be valid; do not confuse it with an "expiration date" encompassing the entire final day. If business rules store only dates, explicitly define the timezone and rule converting `LocalDate` to `Instant`.

Then map into `UserDetails`:

~~~java
// Code fragment in UserDetailsService, with appropriate repository and PasswordEncoder.
AccountState account = accountRepository.loadByUsername(username)
        .orElseThrow(() -> new UsernameNotFoundException("Unknown user"));

Instant now = clock.instant();

return User.withUsername(account.username())
        .password(accountRepository.passwordHashOf(account.accountId()))
        .authorities("ROLE_USER")
        .disabled(!account.enabled())
        .accountLocked(!nonLocked(account, now))
        .accountExpired(!nonExpired(account.accountExpiresAt(), now))
        .credentialsExpired(!nonExpired(account.credentialsExpiresAt(), now))
        .build();
~~~

`accountRepository`, `clock`, and these helpers are **application-supplied components**; the code is a fragment explaining the mapping, not a standalone program. Do not copy a snippet and forget to check `status` or tenant according to real business rules.

**Time boundaries:** if using `lockedUntil`, either an unlock job or dynamic calculation works, provided it aligns with any `UserDetails` caching. Never cache a `UserDetails` with stale lock flags indefinitely, and never accept flags from a request body to build trusted state.

### Account Expired and Credentials Expired Can Both Be True

If an account is both expired and marked for mandatory password change, the provider may return one status error depending on check order. **Do not treat the first thrown exception as the entire business truth.** Investigation, auditing, and recovery flows should read full status data from the repository under proper administrative permissions.

## 8. Blocking New Logins Is Not Enough to Handle Existing Sessions

This is the most important operational point.

Suppose Mai logs in at 09:00 and receives a valid session cookie. An administrator disables her account at 09:15. If the system only updates `accounts.enabled=false`, an already-authenticated session from 09:00 **does not vanish automatically** just because `UserDetailsService` would return disabled on a fresh login.

Diagram:

~~~text
09:00  Successful login
         -> Authentication stored/propagated via active mechanism
         -> session or access token is valid

09:15  Admin sets enabled=false in database
         -> New logins via DaoAuthenticationProvider are blocked
         -> Old session/token: DEPENDS on application's revocation mechanism

09:20  New request with old session/token
         -> May still carry an accepted Authentication
         -> Needs current-status checks / revocation / timeouts
~~~

Strategies to consider:

| Authentication mechanism | Approach to enforce new state | Limitations |
| --- | --- | --- |
| Server-side HTTP session | Invalidate related sessions and/or check current account on critical operations | Must find all relevant sessions across nodes/devices |
| Self-contained JWT claims | Short-lived tokens, server-side account status / revocation version check, or denylist as needed | Valid signature and `exp` **do not guarantee** the account was not locked after issuance |
| Refresh token | Revoke refresh tokens and block issuing new access tokens | Already-issued access tokens may live until expiry without extra checks |
| API key / service principal | Revoke key, update credential/identity status at verification point | Must handle caches and downstream services accepting keys |
| OIDC/SSO | Sync/check internal status, handle logout/revocation per architecture | Logging out of one system does not automatically terminate sessions in every system |

**Never promise "disabled means instant logout" unless the architecture actually implements it.** Define the maximum acceptable revocation latency for each resource type, especially financial, private data, and administrative operations.

### Why Do Sessions and JWTs Differ?

A server-side session may store a `SecurityContext` containing the `Authentication` built at login. Unless refreshed, flags and authorities can be stale snapshots. A JWT may carry `sub`, roles, and `exp` signed by the issuer; verifying the signature does not automatically query the latest account record.

An additional policy before sensitive actions can verify current state:

~~~text
ALLOWED = validAuthentication
          AND currentAccount.enabled
          AND currentAccount.notLocked
          AND currentAccount.notExpired
          AND requiredAuthority
          AND resourceOwnershipOrScope
~~~

This is a model, **not a built-in Spring Security API**. You can implement it via an authorization service, `AuthorizationManager`, or permission-scoped queries. Avoid writing a custom filter that queries the database on every request unless you have designed caching, latency, and database-failure behavior. Yet never sacrifice status checks on high-risk operations merely to save one query.

### A Logout Button Is Not a Centralized Revocation Mechanism

A user clicking logout may clear the session in their current browser; that does not prove sessions on other devices, refresh tokens, or access tokens have been revoked. When an admin locks/disables an account, the application must decide how **all related sessions** are handled.

## 9. Designing Lockout Against Brute Force Without Self-Inflicted DoS

A failed-password lockout policy usually has these variables:

- Number of failures within a time window.
- Lock duration or progressive backoff delay.
- Limits per account, IP, device, and risk signals.
- Counter reset workflow upon success.
- Safe unlock procedure and decision auditing.
- Protections against attackers intentionally locking many other accounts.

Model example:

~~~text
failedAttempts[accountId] = 0..N
lastFailureAt
lockedUntil

if failed attempts exceed threshold:
    lockedUntil = now + lockDuration
    record alert event
else:
    track time window and risk
~~~

This is **pseudocode**. Never assume `UserDetails.isAccountNonLocked()` counts failed passwords, sets `lockedUntil`, or resets counters. Spring Security only provides the integration point and certain authentication events; counters, rate limits, and concurrency protection must be built by the application or infrastructure.

Risks to address:

1. **Account enumeration:** the login screen should not expose "account does not exist", "account locked", or "email unverified" in ways that can be abused. Return safe messages and use verified channels for recovery.
2. **Timing side channel:** response-time differences between normal, locked, and non-existent accounts can leak status. Keep Spring Security patched and measure login flows.
3. **Lockout DoS:** hard-locking after a few wrong attempts lets outsiders disrupt real accounts. Consider progressive delays, rate limiting, and recovery paths.
4. **Race condition:** concurrent login requests can corrupt counters if code only loads, increments, and saves without atomic updates or proper locking.
5. **Inconsistent locks:** nodes with divergent status caches can handle logins inconsistently. Use a single source of truth and suitable TTL/cache invalidation.
6. **Secret leakage in logs:** audit events should include protected actor/account ID, event type, and timestamp; never log raw passwords, session IDs, or tokens.

### Important Security Update: CVE-2026-22746

In April 2026, Spring disclosed CVE-2026-22746 regarding potential user-attribute enumeration via response timing when `DaoAuthenticationProvider` checks locked, disabled, or expired users. Per the advisory, affected branches include Spring Security **6.5.0–6.5.9** and **7.0.0–7.0.4**. Patches were released for 6.5.10 and 7.0.5.

Therefore, when teaching and implementing lock/expiration features, **check advisories and the actual Security version from your BOM/dependency tree**, preferring patched releases rather than merely tweaking UI error messages. The demo uses 7.1.2, outside the affected ranges stated in the advisory. Never work around it by disabling status checks or arbitrarily downgrading versions.

Source: [Spring Security Advisory CVE-2026-22746](https://spring.io/security/cve-2026-22746/).

## 10. Design Separate Recovery Flows for Each Status

Not every denial reason is resolved by the same form.

| Status | Appropriate recovery flow | What to verify |
| --- | --- | --- |
| Temporary lock from wrong password | Wait for expiry; or verify identity via a trusted channel | Do not expose an endpoint bypassing locks without verification |
| Manual lock for investigation | Authorized-person unlock workflow | Audit who unlocked and why |
| Disabled due to unverified state | Email/device verification or activation step per policy | Single-use, short-lived verification token bound to the right account |
| Disabled due to offboarding/violation | Administrative decision, rarely self-recovered | Do not re-enable merely because the user knows the password |
| Account expired | Renewal or switch to restricted mode | Do not block the renewal payment page if business requires it |
| Credentials expired | Password change/reset with valid proof | Do not issue a full `Authentication` before the requirement is completed |

Especially for **credentials expired**: if the normal login flow rejects it, a password-change page requiring only `authenticated()` may become unreachable too. Common designs include a **short-lived reset token**, or a restricted verification flow granting only permission to change the password before issuing normal privileges. Protect against CSRF when using cookies and confirm the exact subject.

When a status is cleared, you do not necessarily restore all old tokens or sessions. Many systems force fresh authentication after a lockout or password reset; that is an intentional choice that must be tested.

## 11. Status Changes Require Administrative Authorization and Auditing

An endpoint like `POST /admin/accounts/101/disable` changes someone else's ability to log in. It is more than updating a boolean.

Enforce controls on:

- **Who may make changes?** Requires appropriate admin authority, tenant binding, role, or approval workflow.
- **Which accounts may be modified?** A tenant A admin must not disable a tenant B account without verified system-wide privileges.
- **Can the last administrator lock themselves out?** You may need safeguards against losing operational control; check business rules carefully.
- **Who may re-enable?** The locker may not be permitted to unlock unilaterally during investigations or dual-control workflows.
- **Should relevant parties be notified?** Notify via policy-compliant channels without exposing investigation details.
- **How are old sessions handled?** Tie status changes to session-invalidation/token-revocation strategies.
- **How are concurrent overwrites prevented?** Use transactions/optimistic locking/CAS when two admins update status simultaneously.

An illustrative service snippet:

~~~java
// Business fragment; requires dedicated beans/repositories/transactions and policies.
@Transactional
public void disableAccount(long targetAccountId, CurrentActor actor) {
    policy.requireCanManageAccount(actor, targetAccountId);

    Account account = repository.findByIdForUpdate(targetAccountId)
        .orElseThrow(AccountNotFoundException::new);

    account.disable(actor.accountId(), clock.instant());
    repository.save(account);
    audit.recordAccountDisabled(actor, account);
    sessionRevocation.requestRevokeSessions(account.id());
}
~~~

`CurrentActor`, `Account`, `policy`, `audit`, and `sessionRevocation` are **application-defined types/components**. This is only a flow outline to clarify boundaries; session revocation should coordinate properly with transaction commit and error handling—for example via an outbox/post-transaction event—to prevent half-applied states.

If you only have `@PreAuthorize("hasRole('ADMIN')")` without checking the tenant, an admin of one organization can lock users in another. Resource-level access control is always needed in multi-tenant systems.

## 12. Timing and Freshness of Status

A login may happen right on the expiration boundary:

~~~text
accountExpiresAt = 2026-11-04T12:00:00Z

now = 2026-11-04T11:59:59Z -> nonExpired = true
now = 2026-11-04T12:00:00Z -> nonExpired = false
now = 2026-11-04T12:00:01Z -> nonExpired = false
~~~

Using an injectable `Clock` makes boundary-condition tests deterministic without depending on wall-clock time. For temporary locks, at `lockedUntil` you may define the lock as lifted. If timestamps need different boundary semantics, document the contract and test to that contract.

Pay attention to the **freshest data source**:

- `UserDetailsService` may load users from the database, yet a provider or application layer might have a cache.
- Previously issued sessions/JWTs may hold stale snapshots even after the database updates `enabled`.
- A freshly committed update may not yet reach other nodes if using asynchronous caches.
- Locks/disables in an external identity provider may not yet be synced to the internal app.

Define requirements for **revocation latency** and test them. Do not merely assert that a database column flipped from `true` to `false`.

## 13. Writing Tests Across Status and Authentication Boundaries

There are three distinct test groups:

**Group A — domain-to-UserDetails mapping:** ensure enabled, locked, expired, and credentials-expired flags are computed accurately, especially `!nonExpired` logic and boundary timestamps.

**Group B — authentication flow:** use `DaoAuthenticationProvider` or real HTTP Basic/form login to confirm ineligible accounts **never produce a trusted Authentication** even with the right password. Verify external responses do not leak unnecessary status details.

**Group C — session/token lifecycle:** when an account is disabled or locked **after login**, verify subsequent requests are blocked within the security-required timeframe. Test across multiple sessions, nodes, or issuers if applicable.

A test matrix:

| Case | Expectation |
| --- | --- |
| User enabled, non-locked, non-expired, credentials valid; right password | Authentication succeeds if all other conditions hold |
| User enabled yet wrong password entered | Rejected because credentials do not match |
| Right password yet `isAccountNonLocked=false` | New login rejected |
| Right password yet `isEnabled=false` | New login rejected |
| Right password yet `isAccountNonExpired=false` | New login rejected |
| Right password yet `isCredentialsNonExpired=false` | New login rejected or routed into a dedicated recovery flow |
| Two flags disallowed simultaneously | No path grants full authentication; audit records full status |
| Temporarily locked before `lockedUntil` | Blocked |
| Exactly at `lockedUntil` | Time-based lock condition lifted per lesson convention |
| Admin disables after login | Old sessions/tokens handled per revocation policy, not only new logins |
| Admin from another tenant tries to disable account | Denied at resource-level authorization |
| Valid password reset | New hash saved, credential policy and sessions updated appropriately |
| Client probes non-existent or disabled username | No exploitable status leak via errors or response timing |

In Spring Boot Servlet apps, you can use `MockMvc`, `@SpringBootTest`, and `spring-security-test`. However, `@WithMockUser` **pre-populates a mock Authentication**, typically bypassing `UserDetailsService` and the provider's password/status checks. To test that **account lock actually blocks login**, do not just write a test with `@WithMockUser(username="locked")` and assert 200/403. Send credentials through the actual login mechanism or call `AuthenticationManager.authenticate` in an integration test.

## 14. Common Mistakes

1. **"A locked account means wrong password."** No: the password may be right while policy still forbids login.
2. **"Disabled and locked are the same boolean."** Do not merge them when business logic has distinct causes and recovery lifecycles.
3. **"Account expired is the same as JWT `exp`."** No: one is account status, the other is token lifetime.
4. **"Password expired equals account expired."** No: `isCredentialsNonExpired` and `isAccountNonExpired` are distinct.
5. **"`isAccountNonLocked=false` means not locked."** Wrong because of `Non`; `false` means currently locked.
6. **"`.disabled(true)` enables the account."** Wrong: the builder names properties for the disabled condition.
7. **"UserDetails reads the `lockedUntil` DB column automatically."** No: your application adapter must map it.
8. **"Flipping `enabled=false` immediately revokes all sessions and JWTs."** Not by default.
9. **"Non-existent accounts should return a distinct error so users spot typos."** Easily enables account enumeration.
10. **"Locking after 3 failures completely stops brute force."** Can be abused for DoS; layered defenses are needed.
11. **"Having `Authentication` in the session means permissions/status are always current."** No: it may be login-time data.
12. **"`@WithMockUser` tests account lock."** Incomplete: that test usually bypasses providers and status checks.
13. **"An admin role can disable any tenant."** Not if scope is restricted to that admin's tenant.
14. **"PasswordEncoder handles account locking itself."** Wrong: it only encodes and verifies passwords.
15. **"When `LockedException` occurs, return the exception name to every client."** No: internal exceptions and external messages are separate concerns.
16. **"Default UserDetails blocks unactivated accounts automatically."** If flags stay true, custom setups may let them through.
17. **"A JWT app only needs UserDetails flags."** JWT flows typically do not call `UserDetailsService`; a dedicated status mechanism is needed.
18. **"Expired accounts must delete all data."** No: data retention/deletion is an independent policy requiring legal and business review.
19. **"Every expiration state must block login."** Not every subscription/membership expiration should block the entire identity.
20. **"Disabling lock checks fixes timing leaks."** No: apply Security patches and safe response policies.

## 15. Self-Check Knowledge Questions

**Question 1.** A `UserDetails` has `isEnabled=true` and `isAccountNonLocked=false`. The password is correct. Does the user log in successfully?

*Answer:* In a `DaoAuthenticationProvider` using standard status checks, no. The account is locked and may throw `LockedException` inside the authentication flow.

**Question 2.** Why does `User.withUsername("mai").accountExpired(true)` result in `isAccountNonExpired()==false`?

*Answer:* The builder uses `accountExpired` in the adverse-state sense, whereas `UserDetails` uses the negated name `isAccountNonExpired`. The two booleans are inverses of each other.

**Question 3.** Does `isCredentialsNonExpired=false` automatically signal that a JWT access token has expired?

*Answer:* No. JWT `exp` is checked by token validators/decoders; the credentials-expired flag serves mechanisms using `UserDetails`, typically password login.

**Question 4.** An admin sets `enabled=false` for Mai's account at 10:00. Mai has a session from 09:00. Is a request at 10:01 guaranteed to be blocked?

*Answer:* Not guaranteed. You must inspect session revocation policies, current-status checks, caches, and authorization; a database change does not automatically destroy all old sessions.

**Question 5.** A system auto-locks after repeated wrong attempts. What risks besides brute force must be defended against?

*Answer:* Outsiders intentionally locking others' accounts (DoS), probing account existence via errors/timing, race conditions on failure counters, or stale caches across nodes.

**Question 6.** Why can you not use `@WithMockUser` alone to prove a locked account cannot log in?

*Answer:* That annotation injects a mock `Authentication` for tests and typically skips `DaoAuthenticationProvider` status checks. Tests must invoke the actual authentication mechanism.

**Question 7.** If an account is still enabled yet its service contract has expired, should `isAccountNonExpired=false` be set?

*Answer:* Depends on policy. If only the service plan expired, you may still allow login for renewal and block subscription features via authorization instead of disabling the entire account.

**Question 8.** Should `lockedUntil` be stored as `LocalDateTime` or `Instant` in a multi-timezone system?

*Answer:* For technical instants, `Instant` is usually clearer and avoids timezone ambiguity. Convert to the appropriate timezone only when displaying to users.

**Question 9.** Does `AccountStatusUserDetailsChecker.check(user)` returning normally prove the password is correct?

*Answer:* Not yet. The checker only validates `UserDetails` status flags; verifying passwords requires a provider/`PasswordEncoder` and the appropriate authentication mechanism.

**Question 10.** Which Spring Security advisory in 2026 relates to locked/expired accounts?

*Answer:* CVE-2026-22746 describes user-attribute enumeration via `DaoAuthenticationProvider` processing timing on affected versions. Upgrade to patched releases per the advisory, such as 6.5.10 or 7.0.5+ within the supported branch.

When designing account security, separate **current account status**, **new authentication conditions**, and **lifecycle of previously issued Authentication objects**. `UserDetails` flags are an essential hook for username/password login, yet revocation capability and safe access must span sessions, tokens, and data policies.

### References

- [Spring Security — UserDetails API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetails.html)
- [Spring Security — User/UserBuilder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/User.html)
- [Spring Security — AccountStatusUserDetailsChecker](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AccountStatusUserDetailsChecker.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Servlet Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — CVE-2026-22746](https://spring.io/security/cve-2026-22746/)
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
