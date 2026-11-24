# Temporary Locking, Disabling, and Deleting Accounts in Spring Security

## 1. Goal and Context

A user enters wrong passwords repeatedly, an employee leaves the company, an account is suspected of compromise, or a user requests data deletion. All four situations may result in **preventing the account from signing in**, yet their causes, durations, recovery policies, and data impacts differ.

Spring Security supports checking basic account states on `UserDetails` such as `isAccountNonLocked()` and `isEnabled()`. However, the framework **does not decide on its own** what “temporarily lock after five wrong attempts” means, who may disable an account, which database tables to purge, or how to revoke every previously issued session and token. Those belong to business policy, the identity store, session/token infrastructure, and application security workflows.

After this lesson, you should be able to:

1. Distinguish **temporary lock**, **disable/suspend**, **account deletion/termination**, credential lock, and credential expiration.
2. Map application lifecycle policies onto the four `UserDetails` methods: `isAccountNonLocked`, `isEnabled`, `isAccountNonExpired`, and `isCredentialsNonExpired`.
3. Build a state model tracking lock duration, reason, actor, and version; handle controlled unlocking without trusting a frontend “Unlock” button.
4. Integrate Spring Security Servlet/JDBC or reactive stacks with account-status checks and **avoid assuming a DB flag automatically invalidates active sessions**.
5. Design brute-force defenses without creating user enumeration or account-lockout DoS.
6. Coordinate account state with HTTP sessions, remember-me, OAuth2 access/refresh tokens, API keys, passkeys, OIDC SSO, and downstream services.
7. Execute deletion **with tombstones, retention, cleanup, auditing, and backup-restore safety**, rather than just calling `repository.deleteById(...)`.
8. Write tests covering status, concurrency, existing sessions, caches, authorization, and recovery.

**Code baseline:** Java 17+, Spring Boot 3.x, Spring Security 6.x (Servlet stack); concepts still apply to newer versions, though APIs should be verified on upgrades. WebFlux uses `ServerHttpSecurity` separately. Do not treat this lesson as legal advice: deletion and retention must follow the laws, contracts, and security policies governing your product.

## 2. Three States Frequently Conflated

| State | Purpose | Reversible? | User data kept? | Who/what decides reopening? |
| --- | --- | --- | --- | --- |
| **Temporary lock** | Block authentication temporarily or pending review/step-up | Usually **yes** | Yes | Expiration of `lockedUntil` per policy, or secure unlock flow |
| **Disabled** | Halt access due to offboarding, departure, policy violation, suspected compromise | May or may not be, depending on reason | Usually yes during hold/retention | Authorized admin/IdP/HR/policy owner |
| **Deleted** | Terminate account and process related data/credentials | May be **irreversible** after purge | Depends on retention, tombstones, legal holds, and purge schedule | Deletion/retention workflow, not flipping an `enabled` flag |

**Temporary lock** is usually time-bounded: e.g., `lockUntil=2026-12-01T10:00:00Z`. Before that timestamp, login is blocked; afterward, policy may automatically treat the lock as expired even if cleanup has not updated the row yet.

**Disabling** reflects a decision that the account must not be used, typically independent of `lockedUntil`. For example, when an employee leaves, even with the right password token, the account must be denied per organizational policy.

**Deletion** involves far more than authentication: identifiers, permissions, user-generated data, secrets, sessions, audits, and database relations. You can apply a “pending deletion” grace period, but that is a **distinct business state**, not erasing every byte immediately. If law requires retaining transactions for a period, data retention and deletion workflows must model that explicitly.

### 2.1. Lock, Disable, Expire: Exact Terminology

An account may also enter:

- **Account expired**: a contract or subscription passed its end date; typically mapped to `isAccountNonExpired() = false` in DAO authentication.
- **Credentials expired**: a password or credential must be rotated; typically `isCredentialsNonExpired() = false` when supported by the provider.
- **Authenticator suspended/revoked**: only one factor (passkey, TOTP, API key) is revoked; other credentials may remain valid.
- **Administratively suspended**: subject to investigation or approval; distinct from automatic lockout from wrong passwords.

A single `enabled=false` flag cannot explain the reason, duration, actor, policy, restoration conditions, and security consequences. Persist a **business lifecycle state** and derive the Spring flags from it.

## 3. Big Picture: Account ≠ Credential ≠ Session ≠ Token

```text
                  Account / identity record
                    stable user ID, status, version
                            |
          +-----------------+--------------------+
          |                 |                    |
   Authenticators       HTTP sessions       OAuth grants/tokens
   password, passkey,    session cookie,     access/refresh,
   OTP, security key     SecurityContext     API keys, devices
          |                 |                    |
          v                 v                    v
  Can login again?    Can use old session?  Can use old Bearer token?
          |                 |                    |
          +------- each requires policy / enforcement ----------+
```

Three questions must be kept separate:

1. “User cannot start new logins” → enforce account status at **authentication**.
2. “Already logged-in user loses access” → **invalidate sessions** and/or re-check status per request where strictness demands it.
3. “Already issued tokens can no longer call APIs” → enforce revocation at the **Authorization Server**, and cache invalidation, introspection, denylists, or short TTLs at the **Resource Server**.

**Setting `users.enabled=false` does not destroy existing `HttpSession` instances.** Once a session holds an earlier `Authentication`, subsequent requests may never re-run `UserDetailsService`/`DaoAuthenticationProvider`. The same holds for JWT access tokens verified offline by a Resource Server: `UserDetails.isEnabled()` on the issuer app does not automatically block already-issued JWTs.

A dangerous design flaw is reporting “account successfully locked” after flipping a DB flag while leaving active sessions, valid refresh tokens, and active API keys untouched.

## 4. Spring Security UserDetails: Four Essential Checks

Spring Security's `UserDetails` represents user attributes needed by certain authentication mechanisms, especially `DaoAuthenticationProvider` in form/username-password logins.

| `UserDetails` method | Returning `false` means | Typical exception in DAO flow |
| --- | --- | --- |
| `isAccountNonLocked()` | Account is locked | `LockedException` |
| `isEnabled()` | Account is disabled | `DisabledException` |
| `isAccountNonExpired()` | Account has expired | `AccountExpiredException` |
| `isCredentialsNonExpired()` | Password/credential has expired | `CredentialsExpiredException` |

In `AbstractUserDetailsAuthenticationProvider`, default pre-authentication checks evaluate **locked**, **disabled**, and **account expired**; post-authentication checks handle **credentials expired**. Exact exceptions can depend on overlapping states, check order, user caching, or custom providers.

Example using Spring Security's `User` builder:

```java
UserDetails details = User.withUsername("alice")
        .password(passwordHash)
        .roles("USER")
        .accountLocked(accountIsLocked)
        .disabled(accountIsDisabled)
        .accountExpired(accountHasExpired)
        .credentialsExpired(credentialsHaveExpired)
        .build();
```

This is an **in-service code snippet** assuming `passwordHash` and booleans were loaded from a trusted repository; it is not a standalone program. Builder methods take **“locked/disabled/expired”** in the positive sense, whereas getters like `isAccountNonLocked()` and `isEnabled()` express negated or active checks. Inverting the boolean is a classic bug:

```java
// WRONG: passing "nonLocked" to a method expecting "accountLocked".
.accountLocked(accountNonLocked) // inverted state!

// RIGHT: pass whether the account is currently locked.
.accountLocked(accountLocked)
```

### 4.1. Not All Authentication Mechanisms Read UserDetails

- `DaoAuthenticationProvider` calls `UserDetailsService` and enforces account flags in standard username/password flows.
- A custom `AuthenticationProvider` may **ignore** those flags unless you explicitly enforce them.
- OAuth2/OIDC login authenticates via an IdP and produces principals that need not be local `UserDetails`; map to internal accounts and enforce lifecycle policy explicitly.
- A Resource Server validating Bearer JWTs may never consult `UserDetailsService`; use token revocation, claims, or account-state lookups per architecture.
- X.509 pre-authenticated, passkey, OTT, API key, and custom logins must each specify **where** disabled/deleted/locked policies are enforced.

Never register one `UserDetailsService` bean and assume every login path now honors the same account policy. Test each actual login mechanism.

### 4.2. Error Handling Must Not Leak Account Existence

Internally, record `LockedException` or `DisabledException` for auditing; **public responses**, however, should avoid clear differences between “unknown username,” “wrong password,” “locked,” and “disabled.” The OWASP Authentication Cheat Sheet recommends generic messages to prevent user enumeration, including avoiding status and response-time differences.

Generic UI example:

> Unable to sign in with the provided details. If you need assistance, please use the account recovery process.

Once the user is verified via a trusted channel, a dedicated flow can explain the reason and next steps in detail. Never tell anyone holding only an email address “the account for email X is suspended for disciplinary review.”

## 5. Designing a Clear State Machine Before Writing Code

A business model might define:

```text
               +------------------+
               | ACTIVE           |
               +------------------+
                     |       |
      too many wrong |       | admin/HR/risk decision
             attempts|       v
                     |   +------------------+
                     v   | DISABLED         |
           +--------------+                 |
           | TEMP_LOCKED  |                 |
           +--------------+-----------------+
             |         ^        |
     TTL done |         |        | user delete request / policy
  or approved |         |        v
        unlock|         |  +------------------+
             v          |  | PENDING_DELETION |
           ACTIVE       |  +------------------+
                        |        |
                        |        | verified purge/retention workflow
                        |        v
                        |  +------------------+
                        +--| DELETED/TOMBSTONE|
                           +------------------+
```

The diagram shows **one design option**: other organizations may include `SUSPENDED_REVIEW`, `LOCKED_COMPROMISE`, `DELETION_CANCELLED`, or `ARCHIVED`. Not every system needs all states in one enum; what matters is that **transition rules** are explicit and cannot be bypassed.

Example decision table:

| From → To | Reason | Who is authorized | Conditions | Mandatory or policy-driven side effects |
| --- | --- | --- | --- | --- |
| ACTIVE → TEMP_LOCKED | Failed logins exceed threshold | Risk/anti-abuse engine | Defined rate limiter, threshold, window | Block new auth; alert on elevated risk |
| TEMP_LOCKED → ACTIVE | Expiration or unlock | Policy engine or verified admin | No disable, deletion, or incident hold | Reset counter per policy, audit |
| ACTIVE → DISABLED | Offboarding/abuse/compromise | Admin/IdP/HR workflow | Approval/trusted source | Block new auth, revoke sessions/tokens if required |
| DISABLED → ACTIVE | Reactivation | Authorized actor + verification | Not deleted; risk review | Re-verify recovery channels/credentials, re-issue sessions |
| ACTIVE/DISABLED → PENDING_DELETION | User request/contract/legal | Verified user or privacy admin | Check retention/legal hold; idempotent | Block auth, revoke credentials, start cleanup |
| PENDING_DELETION → DELETED | Retention/purge workflow | Authorized service | No remaining retention blockers | Purge/anonymize, delete dependent records, audit completion |
| DELETED → ACTIVE | Not allowed by default | Never via simple “unlock” | Only if policy defines reversible tombstone | New onboarding workflow; never resurrect old credentials |

**Never** let a temporary lock's `lockedUntil` expire and accidentally reopen an account that is `DISABLED` or `PENDING_DELETION`. Temporary locks and administrative disables can be modeled as two independent fields with explicit precedence and combined evaluation logic.

### 5.1. Mapping Lifecycle State to Spring UserDetails

One transparent mapping:

```text
accountLocked =
    currentTime < lockedUntil
    OR manualSuspensionRequiresLock

disabled =
    state in {DISABLED, PENDING_DELETION, DELETED}

UserDetails.isAccountNonLocked = !accountLocked
UserDetails.isEnabled = !disabled
```

This is an **application convention**, not a Spring Security default. For `DELETED` accounts, the service should throw **`UsernameNotFoundException`** or fail closed equivalently rather than recreating a deleted record. If a legal hold requires keeping a minimal stub record, make sure a credential-less stub can never be logged into.

## 6. Temporary Lockout: Stopping Brute Force Without Enabling DoS

### 6.1. The Problem

With password login, attackers can try thousands of guesses. An anti-abuse policy usually combines:

- Attempt limits per **canonicalized account identifier**.
- Limits per IP, device, ASN, or source group (accounting for NAT/shared IPs).
- Increasing delays or backoff after failures; counters resetting on a sliding window.
- Step-up challenges, bot detection, and risk-based controls on anomalous traffic.
- Temporarily locking an authenticator or account for a bounded duration.
- Logging, alerting, and abuse metrics that exclude passwords and tokens.

**Never adopt “5 wrong tries → permanent lock” as a universal default.** Attackers can deliberately submit wrong passwords for known usernames to cause **account-lockout denial of service**. OWASP advises balancing lockout thresholds, observation windows, lock durations, and DoS risk. NIST SP 800-63B-4 sets upper bounds on consecutive failed attempts for certain authenticators to prevent online guessing, without prescribing a single rigid configuration for every app.

### 6.2. Timing and Reset Policy

Define explicitly:

- `failedAttemptWindow`: e.g., a 15-minute rolling window.
- `threshold`: number of failures for an identity/credential before intervention.
- `lockedUntil`: UTC `Instant`; expiration checked at authentication time.
- `maxLockDuration` and backoff/cooldown to prevent unbounded locks.
- `resetOnSuccess`: reset only the counter for the authenticator/method that succeeded per policy.
- `manualUnlock`: allowed only for authorized actors with reason, ticket, and audit.
- **Never** clear `DISABLED` or `PENDING_DELETION` simply because another credential succeeded.

Test every unlock path with a mock clock (`Clock.fixed`), multiple nodes, and concurrent requests. If storing locks in Redis with TTLs, ensure state/ban policies are durable: Redis cache eviction must never erase a critical security suspension.

### 6.3. Counting Failures at the Right Point

In Spring Security form login, `AuthenticationFailureHandler` and authentication events surface failure signals. However, **do not increment the failed-password counter for every failure**: locked/disabled accounts, network errors, bad CSRF, missing second factor, and integration errors have different meanings. Persist counts in a shared store and normalize usernames to avoid case/confusable/canonicalization bypasses.

Illustrative logic inside a failure handler:

```java
// Servlet snippet - not a standalone runnable file.
AuthenticationFailureHandler delegate =
        new SimpleUrlAuthenticationFailureHandler("/login?error");

AuthenticationFailureHandler monitored = (request, response, ex) -> {
    if (ex instanceof BadCredentialsException) {
        String suppliedUsername = request.getParameter("username");
        // attempts.recordFailure(...) must normalize, rate-limit,
        // use a shared/atomic store, and handle missing accounts
        // per anti-user-enumeration policy.
        attempts.recordFailure(suppliedUsername, request.getRemoteAddr());
    }
    delegate.onAuthenticationFailure(request, response, ex);
};
```

`attempts` is an application abstraction not defined in the snippet. A production implementation must defend against spoofed `X-Forwarded-For` headers (trust headers only from controlled proxies) and prevent attackers from turning huge strings or Unicode variants into millions of keys. Failures from external IdPs must not be counted as local password failures.

### 6.4. Transactions and Concurrency

Two failed login requests can arrive simultaneously. A naive `SELECT failed_count; failed_count++; UPDATE` without transactions or conditional updates can lose increments. Use atomic increments/transactions, compare sliding windows, and ensure an older successful callback cannot clear a newer lock. Lock records should carry a `version` or transition event ID.

## 7. Disabling: Offboarding, Suspended Review, and Security Incidents

### 7.1. Why Randomizing the Password Is Not Enough

If you only randomize or clear `passwordHash`, other authentication paths may keep working: passkeys, OIDC SSO, remembered sessions, client certificates, OAuth refresh tokens, or API keys. Disabling an account requires a unified policy **across every authentication path**.

Example when an employee leaves:

```text
HR/IdP event (source verified)
  -> account status = DISABLED (persisted/versioned)
  -> block new authentication across methods
  -> terminate active sessions and refresh grants
  -> remove privileged roles/API keys/credentials as policy
  -> notify dependent services; reconcile asynchronously
  -> audit, monitor propagation; retain required records
```

If a user is disabled in the identity provider while the local app caches `OidcUser` and holds an active session, you need state synchronization or session/refresh termination. If permissions live inside a JWT, Resource Servers will not automatically check the local account DB for `enabled`. Document effective propagation latency at every hop.

### 7.2. Temporary Disable vs Permanent Disable

Some products use `SUSPENDED_REVIEW` with an investigation window/condition, and `DISABLED` for offboarding or policy violations. Separate `reasonCode`, `caseId`, `effectiveAt`, `actorId`, and `reactivationPolicy`. Never put an automatic expiration timer on a disable mandated by legal/organizational orders.

### 7.3. Never Allow Unprivileged "Self-Service Reenable"

A disabled user must never have a `POST /enable-me` endpoint that reopens the account with just a username, email, or standalone OTP. Administrative reactivation requires a dedicated role, verification from the original decision source (HR/IdP/anti-fraud), and auditing. When disabling followed suspected takeover, reactivation should require trusted credential reset/re-binding and revoking suspicious sessions/tokens before restoring access.

## 8. Account Deletion: State Transitions Plus Data Lifecycle

### 8.1. Logical Account Deletion Is Not Full Data Purge

Calling `repository.deleteById(id)` affects only one table/entity. Account traces can also live in:

- Authenticator bindings: password hashes, passkey credential IDs/public keys, TOTP secrets, recovery codes.
- HTTP sessions, persistent remember-me tokens, refresh/access token grant records.
- Profiles, contacts, preferences, addresses, uploaded files, private messages.
- Orders/payment invoices, shipping/tax records, subscriptions, support tickets.
- Authorization roles, organization memberships, admin grants, API keys, webhooks.
- Search indexes, Redis caches, analytics exports, data warehouses, object storage, CDNs.
- Logs, backups/snapshots, and async job queues.
- External identity providers, directory/SCIM syncs, partner systems.

Not all data may or should be deleted immediately: accounting or transaction records may carry legal retention mandates. Classify data under **delete**, **anonymize**, **pseudonymize**, **retain with legal basis**, **deny access**, and **backup expiry**. Never promise “instantly erased from all backups” when your technology and retention policy cannot deliver that.

### 8.2. Recommended Deletion Lifecycle

```text
ACTIVE / DISABLED
        |
        | authenticated delete request or verified admin/contract trigger
        v
PENDING_DELETION
        |  block login / reissue, revoke sessions/tokens
        |  check ownership, retention & legal holds
        |  freeze or anonymize sensitive relationships as policy
        v
DELETION_IN_PROGRESS
        |  durable workflow jobs across services
        |  idempotent cleanup, retry, evidence & reconciliation
        v
DELETED / PURGED
        |  minimal tombstone/audit retained only if justified
        |  ensure old account IDs/credentials never revive
        v
Complete / notify
```

You may offer a **cancellation window** if permitted by law and product design, but delaying purge must never allow the user to continue normal access. Cancelling deletion requires verifying the true account owner and policy; never accept an unbounded old email link or raw query `accountId`.

### 8.3. Tombstones and Preventing Identifier Reuse

A tombstone can retain minimal `accountId`, deleted state, timestamp, coded reason, and version to prevent stale events or backup re-imports from reactivating the account. **Do not** retain raw emails, hashes, or tokens in a tombstone without a lawful basis and retention bound.

If usernames or emails can be re-registered later, never use email as the primary owner key in transaction history or authorization; a stable, non-reusable `accountId` prevents linking old data to a new user. If username reuse is allowed, audit how JWT `sub`, SCIM IDs, Kafka events, and audit logs map identities.

### 8.4. Soft Delete vs Hard Delete

| Technique | Benefit | Risk |
| --- | --- | --- |
| `deletedAt` / soft delete | Supports grace periods and controlled restore | Queries forgetting to filter deleted rows leak data or restore accidentally |
| Minimal tombstone | Blocks stale re-creation; keeps processing proof | Can retain excessive PII if poorly designed |
| Hard delete / purge | Removes physical records/credentials once permitted | Breaks relationships/foreign keys or loses legally required retention proof |
| Pseudonymize/anonymize | Keeps aggregate/legal records where allowed | Pseudonymized data may still be PII and re-identifiable |
| Crypto-erasure | Destroys data encryption keys where supported | Works only if every copy uses that key and no plaintext copy exists |

Depending on the product, **hard delete** is often the final workflow step after blocking authentication upfront, rather than deleting the primary row first and only then notifying downstream services.

## 9. Sample Database Schema for Lifecycle

For clarity, store a stable ID, status enum, lock timestamp, actor, reason, version, and deletion timestamps:

```sql
-- PostgreSQL example: application-managed schema, NOT Spring Security DDL.
CREATE TABLE app_accounts (
    id UUID PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT,
    lifecycle_state VARCHAR(32) NOT NULL,
    locked_until TIMESTAMPTZ,
    failed_attempts INT NOT NULL DEFAULT 0,
    status_version BIGINT NOT NULL DEFAULT 0,
    last_status_reason VARCHAR(64),
    last_status_actor UUID,
    disabled_at TIMESTAMPTZ,
    deletion_requested_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ
);
```

This schema is **illustrative only** and omits tables for sessions, roles, passkeys, tokens, contacts, audits, and retention policies. `password_hash` applies only to password authentication; passkey-only users need not carry fake passwords.

### 9.1. Conditional Updates to Prevent Overwriting Newer States

Suppose an admin reads account version 7 to enable it. Meanwhile, a risk engine disables the account for compromise at version 8. Without checking the version on write, the admin could accidentally re-enable a compromised account.

```sql
-- Illustrative optimistic concurrency in PostgreSQL.
UPDATE app_accounts
SET lifecycle_state = 'DISABLED',
    last_status_reason = 'OFFBOARDING',
    status_version = status_version + 1,
    disabled_at = CURRENT_TIMESTAMP
WHERE id = :account_id
  AND status_version = :expected_version
  AND lifecycle_state = 'ACTIVE'
RETURNING id, status_version;
```

Only if **exactly one row** updates does the transition succeed. Zero rows means the state/version changed or the account does not exist: reload and re-evaluate against current policy rather than blindly retrying. JPA can use `@Version` for optimistic locking, while session/token side effects still require durable events/outbox so nothing is dropped.

### 9.2. Temporary Lock Using Server Time

```sql
-- PostgreSQL sketch: locked_until as UTC Instant.
UPDATE app_accounts
SET locked_until = GREATEST(
        COALESCE(locked_until, CURRENT_TIMESTAMP),
        CURRENT_TIMESTAMP + INTERVAL '10 minutes'),
    status_version = status_version + 1
WHERE id = :account_id
  AND lifecycle_state = 'ACTIVE';
```

This is not complete failed-attempt counting logic; it illustrates preventing a shorter lock request from overwriting a longer existing lock. In real implementations, observation windows, thresholds, and backoff share transactions/atomic stores. Never accept browser timestamps or client-supplied `unlockAt` values.

## 10. Spring Boot Servlet Demo: Mapping Lifecycle State to UserDetails

The following Java 17 demo focuses on **authentication state** and deliberately has **no** public HTTP endpoints for locking or deleting accounts. It uses an in-memory store for a single instance and one demo user; it is **not** a production system and performs no data purging or session revocation.

### 10.1. Gradle Dependencies

In a Spring Boot 3.x Java 17 project with the Spring Boot Gradle plugin:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

### 10.2. Complete Code

Save as `src/main/java/demo/lifecycle/AccountLifecycleApplication.java`:

```java
package demo.lifecycle;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AccountLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(AccountLifecycleApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    AccountStore accountStore(PasswordEncoder encoder) {
        return new AccountStore(encoder, Clock.systemUTC());
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class Pages {
        @GetMapping("/")
        String home() {
            return "Open /private and sign in as alice.";
        }

        @GetMapping("/private")
        String privatePage(Authentication authentication) {
            return "Hello, " + authentication.getName();
        }
    }

    record Account(String username, String hash, boolean disabled,
                   boolean deleted, Instant lockedUntil) {

        Account withLockUntil(Instant until) {
            return new Account(username, hash, disabled, deleted, until);
        }

        Account withDisabled(boolean value) {
            return new Account(username, hash, value, deleted, lockedUntil);
        }

        Account asDeletedTombstone() {
            // Demo logical tombstone; production needs real data deletion.
            return new Account(username, "unusable", true, true, null);
        }
    }

    static final class AccountStore implements UserDetailsService {
        private final Map<String, Account> accounts =
                new ConcurrentHashMap<>();
        private final Clock clock;

        AccountStore(PasswordEncoder encoder, Clock clock) {
            this.clock = clock;
            accounts.put("alice", new Account(
                    "alice", encoder.encode("local-demo-only"),
                    false, false, null));
        }

        @Override
        public UserDetails loadUserByUsername(String username)
                throws UsernameNotFoundException {
            Account account = accounts.get(username);
            if (account == null || account.deleted()) {
                throw new UsernameNotFoundException("Account unavailable");
            }

            boolean locked = account.lockedUntil() != null
                    && clock.instant().isBefore(account.lockedUntil());

            return User.withUsername(account.username())
                    .password(account.hash())
                    .roles("USER")
                    .accountLocked(locked)
                    .disabled(account.disabled())
                    .build();
        }

        // Lab-internal only: DO NOT expose directly as a public controller.
        void lockFor(String username, Duration duration) {
            if (duration.isNegative() || duration.isZero()) {
                throw new IllegalArgumentException("duration");
            }
            Instant until = clock.instant().plus(duration);
            accounts.computeIfPresent(username,
                    (key, old) -> old.deleted()
                            ? old : old.withLockUntil(until));
        }

        void disable(String username) {
            accounts.computeIfPresent(username,
                    (key, old) -> old.deleted()
                            ? old : old.withDisabled(true));
        }

        void markDeleted(String username) {
            accounts.computeIfPresent(username,
                    (key, old) -> old.asDeletedTombstone());
        }
    }
}
```

Explanation:

- `AccountStore` is registered as the `UserDetailsService` Spring bean. Every username/password login via DAO authentication loads the account and computes flags from its current state.
- `.accountLocked(locked)` takes “is currently locked”; `UserDetails.isAccountNonLocked()` returns the negation.
- `.disabled(account.disabled())` blocks new logins when the account is disabled.
- `deleted=true` → `UsernameNotFoundException`; there is no automatic reactivation path in the class.
- Injecting `Clock` lets unit tests run without sleeping. `Instant` avoids timezone bugs and performs exact boundary comparisons.
- `ConcurrentHashMap.computeIfPresent` makes single-entry updates atomic across demo threads in **one process**; it is **not** a distributed transaction across nodes.
- `BCryptPasswordEncoder` hashes only demo passwords; never print or copy real passwords or hashes into responses.
- `markDeleted` is intentionally a **demo tombstone, not compliant legal deletion**. It does not delete profiles, credentials, audits, or sessions.
- Failed-login counting is omitted from the demo. Production anti-abuse engines and persistence must be built as described in Section 6, without exposing unguarded “unlock/admin” endpoints to the Internet.

### 10.3. Running the Demo

```bash
./gradlew bootRun
```

On Windows use `gradlew.bat bootRun`. Open `http://localhost:8080/private`. Using default account `alice` and local password `local-demo-only`, signing in returns body:

```text
Hello, alice
```

However, **succeeding with form login in the demo does not mean future requests on that session are automatically revoked** if internal code calls `disable(...)`. To demonstrate lock/disable/delete, run the unit tests in Section 11 rather than adding an unprotected admin controller.

## 11. JUnit Tests for Lock, Disabled, and Logical Delete

In the Section 10 project, add `src/test/java/demo/lifecycle/AccountStoreTest.java`:

```java
package demo.lifecycle;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

import static org.junit.jupiter.api.Assertions.*;

class AccountStoreTest {

    private final Clock fixedTime = Clock.fixed(
            Instant.parse("2026-01-01T10:00:00Z"), ZoneOffset.UTC);

    @Test
    void lockBlocksNewAuthentication() {
        var store = new AccountLifecycleApplication.AccountStore(
                new BCryptPasswordEncoder(), fixedTime);

        assertTrue(store.loadUserByUsername("alice")
                .isAccountNonLocked());

        store.lockFor("alice", Duration.ofMinutes(10));

        assertFalse(store.loadUserByUsername("alice")
                .isAccountNonLocked());
    }

    @Test
    void disableBlocksEvenWithoutTemporaryLock() {
        var store = new AccountLifecycleApplication.AccountStore(
                new BCryptPasswordEncoder(), fixedTime);

        store.disable("alice");

        assertFalse(store.loadUserByUsername("alice").isEnabled());
    }

    @Test
    void deletedAccountIsNotReturnedAsLoginPrincipal() {
        var store = new AccountLifecycleApplication.AccountStore(
                new BCryptPasswordEncoder(), fixedTime);

        store.markDeleted("alice");

        assertThrows(UsernameNotFoundException.class,
                () -> store.loadUserByUsername("alice"));
    }
}
```

Run:

```bash
./gradlew test --tests demo.lifecycle.AccountStoreTest
```

Expect all three tests to **PASS** with appropriate dependencies and JDK. They test only the mapping from demo state to `UserDetails`; they **do not prove** distributed persistence, session invalidation, OAuth token revocation, or real data deletion.

To test exact lock expiration boundaries, inject a mutable mock `Clock`, advance from `t0` to `t0 + 11 minutes`, and assert `isAccountNonLocked() == true` while `isEnabled()` remains governed by disabled state. Avoid `Thread.sleep` as it makes tests slow and flaky.

## 12. How Do Locking and Disabling Affect Already Logged-In Sessions?

### 12.1. Why Checking UserDetails Only at Login Is Not Enough

Spring Security Servlet uses `SecurityContextRepository` to restore `Authentication` from the HTTP session after login. If you disable an account after a session was issued, subsequent requests **do not automatically re-invoke `DaoAuthenticationProvider`**. Evaluating `isEnabled()` at login time does not mean every request revalidates the account.

```text
t0: alice login -> Authentication valid -> HttpSession S1
t1: admin disables alice in DB
t2: alice sends S1 cookie -> RP may still restore SecurityContext
                             -> request may continue unless session
                                invalidated/rechecked by app policy
```

### 12.2. Terminating Sessions Server-Side

Common strategies:

1. **Invalidate active sessions** via Spring Session/shared store when disable/delete/incidents occur.
2. **Session registry** when using concurrent session control; calling `expireNow()` on the registry marks the session expired for a filter to enforce on the next request, rather than immediately deleting every Redis record on the spot.
3. **Version/recheck account status** on sensitive endpoints or via a request interceptor—e.g., comparing `account.statusVersion` against `session.authVersion` and failing closed on mismatch.
4. **Short session lifetimes** shrink the exposure window, though they do not replace immediate revocation when policy requires it.

With Spring Session `FindByIndexNameSessionRepository`, you can look up sessions by principal and delete them:

```java
// Snippet inside backend service, not a public controller.
// Uses Spring Session package org.springframework.session.*
Map<String, ? extends Session> sessions =
        indexedRepository.findByPrincipalName(principalName);

for (String sessionId : sessions.keySet()) {
    indexedRepository.deleteById(sessionId);
}
```

This is an illustrative snippet requiring the proper generic repository type and Spring Session dependency. Crucially, the **principal-name index must be populated correctly**; Spring Session does not automatically understand every custom authentication flow. If the index is missing or sessions span namespaces, deletions may miss sessions. Index by a stable tenant-aware internal identity, not a mutable email. In production, account for pagination/scale, races between concurrent logins and deletion, and sessions issued right before the status transition.

### 12.3. Ordering Rules

For disabling or deleting due to a security incident:

```text
Persist state: DENY NEW LOGIN FIRST
   |
   v
Invalidate / revoke sessions and credentials
   |
   v
Notify other services, reconcile pending tasks
   |
   v
Confirm effective access termination
```

If a workflow revokes sessions before persisting `disabled=true`, a new login request can slip into the window and create a fresh session. Persist the state transition durably first, then revoke sessions; for near-real-time guarantees, re-check status/version on critical requests.

## 13. Tokens and Other Authentication Paths Must Be Closed Separately

### 13.1. Remember-Me

`PersistentTokenBasedRememberMeServices` can restore authentication from a persistent token if its record still exists. When disabling or deleting an account, delete/revoke remember-me tokens and ensure the provider checks account status when restoring. Clearing only the current login session is not enough while remember-me tokens remain active.

### 13.2. OAuth2/OIDC Access & Refresh Tokens

- **OAuth refresh tokens:** while valid, clients can mint new access tokens. Revoke grants/refresh tokens at the Authorization Server or block issuance based on account status.
- **Opaque access tokens/introspection:** Resource Servers call the AS to check `active`; revocation latency depends on AS propagation and cache TTLs.
- **Self-contained JWT access tokens:** RS typically checks signature, issuer, audience, and expiry offline. Updating user status in a DB **does not automatically invalidate issued JWTs**; for rapid cutoff, use denylists, token versions/security stamps, AS events, introspection, or short lifetimes by design.
- **OIDC SSO sessions at the IdP:** disabling the local app account does not destroy the IdP session; integrate IdP lifecycle/SCIM/offboarding and logout/revocation protocols properly.

### 13.3. API Keys, Service Accounts, and Client Credentials

API keys or service-to-service credentials may not be tied to user HTTP sessions. Inspect actual ownership and permission namespaces. Disabling a human account does not necessarily delete a shared organizational service account, though it must revoke personal delegations and permissions controlled by that individual per policy.

### 13.4. Passkeys, TOTP, and Other Login Methods

When an account is disabled or pending deletion, every sign-in path—passkey, TOTP, password, OTT, or OIDC—must enforce the **same account policy**. Clearing `passwordHash` is insufficient when a bound passkey can still produce a valid WebAuthn assertion. Account-status enforcement must sit at the trust boundary invoked by every authentication mechanism.

When **deleting an account**, delete or revoke WebAuthn credential bindings, recovery codes, and authenticator records, ensuring a “passkey still on the user's device” cannot silently re-bind without new registration. Stub records retained for legal/audit purposes must never act as login principals.

## 14. WebFlux / Reactive Security: Differences to Know

With Spring WebFlux, use `ReactiveUserDetailsService` and `ServerHttpSecurity` instead of blocking `UserDetailsService` on the event loop and Servlet `HttpSecurity`:

```java
// Fragment inside a @Configuration class in a Spring Boot WebFlux project.
@Bean
SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/").permitAll()
                    .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

Reactive repository:

```java
// Fragment using custom-defined ReactiveAccountRepository.
@Bean
ReactiveUserDetailsService reactiveUsers(
        ReactiveAccountRepository repository) {
    return username -> repository.findByUsername(username)
            .filter(account -> !account.deleted())
            .map(account -> User.withUsername(account.username())
                    .password(account.passwordHash())
                    .roles("USER")
                    .accountLocked(account.isLockedNow())
                    .disabled(account.disabled())
                    .build());
}
```

`ReactiveAccountRepository` and `account.isLockedNow()` are **application abstractions**, not built-in Spring Security APIs; the snippet will not compile standalone without them. In WebFlux, read the principal from `ReactiveSecurityContextHolder`/Reactor Context rather than Servlet's thread-local `SecurityContextHolder`.

Crucially, reactive repositories must be genuinely non-blocking (e.g., R2DBC or Reactive Redis) or isolate blocking calls onto a dedicated scheduler; `Mono.just(jdbcCall())` still executes blocking JDBC before constructing the publisher. State transitions and session invalidation must integrate with `WebSession`/reactive Spring Session and tokens per architecture, not merely one `UserDetailsService` bean.

## 15. Admin APIs and Self-Service: Strict Authorization Checks

### 15.1. Why `hasRole("ADMIN")` Is Not Enough

When locking or deleting accounts, beyond checking a role, enforce:

- **Scope**: an admin for organization A cannot lock an account in organization B.
- **Object ownership**: self-service deletion affects only the authenticated user's own account; ignore `userId` in the body.
- **Separation of duties**: locking high-privilege admins or overriding legal holds may require dual approval.
- **Recent reauthentication/step-up**: never let a stale session or stolen cookie mass-delete accounts.
- **CSRF protection**: cookie-authenticated browser mutations must use POST/PATCH/DELETE + CSRF per configuration.
- **Audit**: record actor, target, reason, ticket/case, status version, and command source.
- **Rate limiting** and replay/idempotency: prevent endlessly retried failed requests from causing unexpected side effects.

DSL rules act only as an **outer perimeter**, not a substitute for target-level permission checks inside services:

```java
// Fragment inside HttpSecurity configuration of a Servlet app.
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.POST, "/admin/accounts/*/disable")
        .hasAuthority("ACCOUNT_DISABLE")
        .requestMatchers(HttpMethod.POST, "/admin/accounts/*/unlock")
        .hasAuthority("ACCOUNT_UNLOCK")
        .anyRequest().authenticated());
```

Never put `permitAll()` on unlock, reset, or delete endpoints on the grounds that “locked users can't log in.” Account recovery needs **its own dedicated flow** with narrow-scoped tokens/sessions, identity verification matching required assurance, and policy checks before re-enabling.

### 15.2. Never Delete via GET

`GET /accounts/delete?id=123` is dangerous due to browser prefetchers, crawlers, hyperlinks, CSRF, and caching. Use an appropriate mutating HTTP method, CSRF protection for cookie-based sessions, confirmation, and step-up auth; the backend must never rely on a mere JavaScript confirm dialog.

### 15.3. HTTP API Idempotency and Status

A disable API may return success if the account is already disabled, yet must never silently turn **DELETED** into **DISABLED** or recreate the user. Use conditional updates; if state or version conflicts, return `409 Conflict` or a standardized domain error. For async deletion, you may return `202 Accepted` once the workflow is durably queued alongside an operation ID; never report “deleted everywhere” while the job is still sitting in a queue.

## 16. Recovery: Unlock vs Reactivation vs Deletion Cancellation

### 16.1. Unlock After Temporary Lock

If locked for failed password attempts and the duration expires, the system can auto-unlock based on the stored `lockedUntil` timestamp without wiping profile data or `passwordHash`. However, if credential compromise is detected, letting a timer expire is insufficient: rotate/revoke authenticators, enforce step-up, and conduct a risk review.

### 16.2. Reactivate After Disable

Reactivation after offboarding or organizational actions requires verifying an **authoritative decision source** for the new state, potentially re-provisioning roles, verifying changed emails/phones, resetting credentials, or enrolling new MFA/passkeys. Never blindly restore all prior roles and admin grants by default.

If disabled due to suspected takeover, revoke old sessions, rotate recovery secrets, review suspicious activity, and verify user identity reliably before reopening. A single email link sent to an attacker-compromised mailbox may be weaker than the attacker's foothold.

### 16.3. Cancelling Deletion During Grace Period

If a pre-purge grace window exists, cancellation requires explicit policy, owner verification, and auditing; never accept an unexpiring email link. After hard purge, the account may be unrecoverable; creating a user again is **new onboarding** with a new `accountId` that must never inherit data or permissions from the deleted user.

### 16.4. Do Not Confuse Account Recovery with Password Reset

A password reset changes only a credential. It must never unlock an account disabled for legal/offboarding reasons or clear an incident hold. Recovery transitions must pass through the state-transition policy rather than blindly writing `enabled=true` in every “forgot password” code path.

## 17. Standalone Java 17 Exercise: Lock, Disable, Delete State Machine

The following example has no Spring, database, or server dependencies; it models the **distinct** behaviors of all three states. Determinism is achieved with explicit timestamps so stdout is exactly reproducible. Save as `AccountLifecycleModel.java`:

```java
import java.time.Duration;
import java.time.Instant;

public class AccountLifecycleModel {
    enum State { ACTIVE, DISABLED, PENDING_DELETION, DELETED }

    static final class Account {
        private State state = State.ACTIVE;
        private Instant lockedUntil;

        boolean mayLoginAt(Instant now) {
            boolean locked = lockedUntil != null
                    && now.isBefore(lockedUntil);
            return state == State.ACTIVE && !locked;
        }

        void lockFor(Instant now, Duration period) {
            if (state != State.ACTIVE || period.isNegative()
                    || period.isZero()) {
                throw new IllegalStateException("Cannot lock");
            }
            lockedUntil = now.plus(period);
        }

        void disable() {
            if (state == State.DELETED) {
                throw new IllegalStateException("Deleted");
            }
            state = State.DISABLED;
        }

        void requestDeletion() {
            if (state == State.DELETED) {
                return;  // idempotent
            }
            state = State.PENDING_DELETION;
        }

        void completeDeletion() {
            if (state != State.PENDING_DELETION) {
                throw new IllegalStateException("Not pending");
            }
            state = State.DELETED;
            lockedUntil = null;
        }
    }

    public static void main(String[] args) {
        Instant t0 = Instant.parse("2026-01-01T10:00:00Z");
        Account alice = new Account();

        System.out.println("active: " + alice.mayLoginAt(t0));

        alice.lockFor(t0, Duration.ofMinutes(10));
        System.out.println("during lock: " + alice.mayLoginAt(
                t0.plusSeconds(300)));
        System.out.println("lock expired: " + alice.mayLoginAt(
                t0.plusSeconds(600)));

        alice.disable();
        System.out.println("disabled: " + alice.mayLoginAt(
                t0.plusSeconds(601)));

        alice.requestDeletion();
        System.out.println("pending deletion: " + alice.mayLoginAt(
                t0.plusSeconds(602)));

        alice.completeDeletion();
        System.out.println("deleted: " + alice.mayLoginAt(
                t0.plusSeconds(603)));
    }
}
```

Run with JDK 17+:

```bash
javac AccountLifecycleModel.java
java AccountLifecycleModel
```

Exact stdout:

```text
active: true
during lock: false
lock expired: true
disabled: false
pending deletion: false
deleted: false
```

This exercise clarifies: temporary locks expire automatically, whereas **disabled/pending deletion/deleted states never automatically reopen** as time passes. The model omits HTTP sessions, OAuth tokens, transactions, legal retention, and admin authorization checks—those are handled in separate layers.

## 18. Synchronization, Race Conditions, and Outbox Across Multiple Services

A lifecycle change typically triggers multiple side effects: DB state, Redis sessions, Authorization Server grants, file-deletion jobs, search indexes, and notifications. You cannot assume all services participate in one distributed DB transaction.

### 18.1. Transactional Outbox

A reliable workflow can:

1. Inside **one DB transaction**, update account state/version and write an outbox event `ACCOUNT_DISABLED` or `ACCOUNT_DELETION_REQUESTED` with an event ID.
2. A publisher dispatches outbox events to consumers with at-least-once delivery.
3. Consumers invalidate sessions, revoke tokens, and delete data **idempotently** keyed by event ID and target version.
4. A reconciler sweeps incomplete jobs, retries with backoff, alerts on failures, and avoids marking “completed” while critical steps remain failed.
5. Admin/user UIs show **pending/in progress/partial failure** rather than a fake “success.”

### 18.2. Stale Events Must Not Reopen Accounts

Suppose `ACCOUNT_ENABLED(version=3)` arrives after `ACCOUNT_DISABLED(version=4)`. Consumers must compare versions so stale events never re-enable an account. Single-partition ordering does not replace version checks when multiple producers or consumers exist.

### 18.3. Restoring from Backup

Yesterday's backup may show an account as `ACTIVE` even though it is `DELETED` today. After a restore, replay the deletion/disable ledger or enforce tombstones/decision authorities to prevent resurrecting old credentials and PII. Test restores and migrations, not just normal deletes.

### 18.4. Cache Consistency

If each authentication node caches `UserDetails` or account status mappings, disabling on node A may not immediately take effect on node B. TTL alone cannot satisfy “disable immediately.” Use cache invalidation/events or version checks on critical actions. When the source of truth is unreachable in high-risk scenarios, **fail closed** instead of assuming enabled.

## 19. Operational Security and Auditing

A lifecycle-change audit event should record:

| Attribute | Example / purpose |
| --- | --- |
| `accountId`, `tenantId` | Stable target, avoiding email/name confusion |
| `actorId`, `actorType` | Admin, HR integration, user self-service, risk engine |
| `fromState`, `toState` | Auditable state transition |
| `reasonCode`, `caseId` | Standardized business reason, ticket reference if applicable |
| `occurredAt`, `effectiveAt` | Request timestamp and effective timestamp |
| `version`, `eventId` | Prevents stale writes/events; ensures idempotency |
| `sessionRevocation`, `tokenRevocation` | Counts, status/lag, remaining errors |
| `deletionJobId`, `retentionPolicy` | Distinguishes pending deletion from completion |
| `result` | Applied, rejected, partial, retrying; never assume full success |

Never log passwords, raw access/refresh tokens, session cookies, recovery codes, or unnecessary personal data. Deleted accounts may keep minimal audit metadata under legal retention; enforce strict access controls and retention bounds on audit logs.

When an admin locks or deletes a user, notify the previously verified channel per policy. For abuse or legal investigations, notification restrictions may apply by law—document an explicit policy rather than blindly emailing details that could tip off an investigation.

## 20. Mandatory Pre-Production Test Matrix

| Test | Scenario | Expected outcome |
| --- | --- | --- |
| 1 | ACTIVE, right password | Login succeeds, proper roles assigned |
| 2 | Repeated wrong passwords below threshold | Login denied; rate limiter/attempt count accurate |
| 3 | Lock threshold reached | Generic error returned; new auth blocked |
| 4 | Two concurrent failures | Atomic counter, no lost increments |
| 5 | Repeated failures on non-existent account | Prevents enumeration/DoS, generic response |
| 6 | Clock before/at/after `lockedUntil` | Crisp boundary behavior, timezone-independent |
| 7 | Account both locked and disabled | Lock expiry does not reopen disabled account |
| 8 | Password reset while disabled | Does not silently set `enabled=true` |
| 9 | Admin unlocks account in another tenant | 403/404 per policy; state unchanged |
| 10 | Admin has role but lacks step-up | Sensitive state change denied |
| 11 | Disable while HTTP session is active | Existing session blocked/invalidated within SLA |
| 12 | Disable while remember-me token exists | Token revoked; cannot restore login |
| 13 | Disable while refresh token exists | Cannot mint new access tokens past policy bound |
| 14 | Disable while JWT access token exists | RS enforces revoke/denylist/version/expiry within SLA |
| 15 | Disable when user has passkey/OIDC login | No bypass through alternate auth paths |
| 16 | Concurrent enable and disable | Status version/precondition blocks stale write |
| 17 | Offboarding from HR/SCIM | Idempotent event, consistent multi-node state |
| 18 | Self-service deletion request | Verified owner, CSRF, recent step-up, valid audit |
| 19 | DELETE via GET or cross-site request | Account not deleted |
| 20 | `PENDING_DELETION` user tries to log in | Rejected; no new session/token issued |
| 21 | Deletion worker retries | Never deletes wrong account, idempotent |
| 22 | Legal retention/hold | Required data minimally retained; login impossible |
| 23 | Account deletion + username reuse | Old user's tokens/history/roles never attach to new user |
| 24 | Backup restore from before deletion | Deleted user/credentials stay inactive |
| 25 | Multi-node/cache | Other nodes observe disable/revoke within SLA |
| 26 | Partial AS/Redis outage | Does not claim completion; retries/alerts, fails closed |
| 27 | Reactivation from disabled | Authoritative source, proofing, no blind role restoration |
| 28 | Public browser error messages | No disclosure of unknown/locked/disabled via text or clear timing |
| 29 | Audit logs and telemetry | Contains actor/reason/version; no credentials logged |
| 30 | Independent OAuth/OIDC logout | Local disable not confused with OP session/token revocation |

Separate **unit tests** for pure Java state machines, **Spring Security tests** for authentication/authorization/CSRF, **integration tests** for DB/Redis/AS, and **end-to-end tests** with browsers/IdPs when needed. Mocking a disabled `UserDetails` proves the DAO checker works, not that old sessions are invalidated or RS JWTs are rejected.

## 21. Symptom-Based Troubleshooting

### 21.1. `isEnabled=false` Yet the User Keeps Using the App

Check the actual authentication mechanism in use. With an existing `HttpSession`, requests may simply restore the cached `SecurityContext`. With Bearer JWTs, the RS might not query the user DB at all. Implement session invalidation/status rechecks and separate token revocation—do not try to fix it by calling `loadUserByUsername` once on the login controller.

### 21.2. Account Remains Locked Past `lockedUntil`

Check UTC time comparisons, `Instant` usage, stale caches, persisted `disabled`/incident holds, and the source-of-truth state. Lock evaluation must be `now.isBefore(lockedUntil)`, not local date strings or a sticky `locked=true` flag with no reset mechanism.

### 21.3. User Still Logs In via SSO After Deletion

The OP/IdP may still hold an active SSO session while the local app has not mapped disabled/deleted status. Audit account linkage/SCIM deprovisioning, OIDC user mapping, session invalidation, and refresh grants. Never allow SSO sign-in to recreate a deleted local user solely on email match.

### 21.4. API Traffic Continues After Admin Disable

Look for API keys, service principals, OAuth Bearer tokens, refresh grants, or caches. Trace requests by issuer, client, and account ID to find access paths missing lifecycle enforcement. Never rely on email alone to link client credentials to human accounts.

### 21.5. Account Deletion Breaks Legally Required Records

Deletions must follow a data inventory, retention/legal-hold rules, and a foreign-key strategy. Never blindly enable `ON DELETE CASCADE` on every table. Plan anonymization, scheduled hard deletion, and minimal audit retention per policy.

### 21.6. Disabled on One Node, Still Enabled in Another Node's Cache

Check event propagation, TTLs, security stamps/versions, stale Spring `UserCache`, session registries, and cross-node consistency. Write an integration test: disable on node A, then hit node B immediately afterward, measuring latency against business requirements.

### 21.7. Attackers Can Lock Other Users' Accounts

That is account-lockout DoS. Add multi-dimensional rate limiting, backoff/risk scoring, notifications, and social-engineering-resistant recovery; never let a few forged attempts permanently lock any arbitrary username.

### 21.8. Pending Deletion Rolls Back to ACTIVE

Inspect stale events/retries, default enum values, repository soft-delete filters, and backup restores. Enforce transition preconditions/versions, tombstones, and reconciliation ledgers; never let OIDC login or SCIM recreate a user without checking deleted state.

## 22. Pre-Production Design Checklist

1. **State taxonomy:** explicitly separate `TEMP_LOCKED`, `DISABLED`/`SUSPENDED`, `PENDING_DELETION`, `DELETED`, and expired credentials; document transition constraints.
2. **Spring mapping:** verify `UserDetails` flags plus custom providers, OIDC, passkey, and API-key paths; test beyond form login.
3. **Anti-brute-force:** account + IP/device rate limiting, threshold/window/backoff, lockout-DoS defenses, and generic error messages.
4. **Time consistency:** use `Instant`, `Clock`, and explicit lock boundaries; test before, at, and after expiry.
5. **Authorization:** state-changing admin endpoints enforce RBAC + tenant/object permissions, step-up, CSRF, audit, and idempotency; never delete via GET.
6. **Concurrency:** optimistic version/conditional updates so stale enables cannot overwrite security disables; atomic failure counters.
7. **Sessions:** invalidate server-side sessions, remember-me tokens, and caches with a defined cross-node SLA.
8. **Tokens:** revoke refresh grants, API keys, and access tokens per AS/RS policy; offline JWTs need an explicit strategy.
9. **Deletion inventory:** map data across DBs, files, search, analytics, downstream services, backups, and retention/legal holds.
10. **Durable workflow:** pending deletion, outbox, retries/reconciliation, completion criteria, and tombstones preventing backup resurrection.
11. **Recovery:** unlock per policy, reactivate from authoritative sources, keep distinct from password reset, and never revive deleted principals.
12. **Observability:** audit actor/reason/time/version, session/token/purge status, and partial errors; omit credentials and unnecessary PII.
13. **Tests:** test concurrency, multi-node setups, fail-closed paths, IdP/SCIM, old HTTP sessions and unexpired JWTs, backup restores, user enumeration, and self-service deletion.

**Summary:** temporary locking is a time-bounded restriction; disabling is an administrative/business suspension; account deletion is both a data-lifecycle and identity-safety workflow. **Spring Security can block new authentications via account flags, but terminating all existing access also requires handling sessions, tokens, credentials, caches, and downstream systems.**

## 23. Official Reference Documentation

- [Spring Security 6.5 — UserDetails API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetails.html): enabled, non-locked, and non-expired checks.
- [Spring Security 6.5 — User.UserBuilder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/User.UserBuilder.html): `disabled`, `accountLocked`, `accountExpired`, and `credentialsExpired`.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html): loading `UserDetails`, password verification, and account-status checks.
- [Spring Security — Servlet Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): `SecurityContext` persistence, concurrent session control, session expiration.
- [Spring Security — Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): `SecurityContextLogoutHandler`, session invalidation, and remember-me cleanup.
- [Spring Session — FindByIndexNameSessionRepository API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/FindByIndexNameSessionRepository.html): `findByPrincipalName` and principal-index considerations.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revoking tokens/grants according to AS capabilities.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): active state checked by RS via AS.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): lockout, brute-force defenses, and generic authentication errors.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session invalidation and timeouts.
- [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): credential recovery, anti-enumeration, and anti-abuse.
- [NIST SP 800-63B-4 — Authentication & Authenticator Lifecycle](https://pages.nist.gov/800-63-4/sp800-63b.html): online guessing defenses, authenticator suspension/invalidation, and recovery.
- [NIST SP 800-63A-4 — Subscriber Account Suspension or Termination](https://pages.nist.gov/800-63-4/sp800-63a/accounts/): account termination, notifications, and behavior by identity assurance.
