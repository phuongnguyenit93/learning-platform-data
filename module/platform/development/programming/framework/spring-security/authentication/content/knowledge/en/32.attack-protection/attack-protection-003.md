# Temporary lockout and avoiding turning lockout mechanisms into denial-of-service tools

> **Context:** Defending against brute-force, credential stuffing, and password spraying at a Spring Security login endpoint. A policy like "5 wrong attempts locks the account for 30 minutes" can curb password guessing, yet also lets attackers deliberately **lock out legitimate users' accounts**. This lesson explains how to balance security and availability: multi-layered login attempt limits, bounded lock durations, recoverability, distributed state, preventing username leaks, and how to integrate into Spring Boot 3.x/Spring Security 6.x with Java 17.

## 1. The core design question

User A entering wrong passwords repeatedly might simply have forgotten their password; stranger B can also submit wrong passwords for A's username. The server **cannot distinguish the two people from failure counts alone**. If it immediately hard-locks A whenever the failure threshold is reached, B gains a tool to cause **denial of service (DoS)** without knowing A's password.

We must simultaneously achieve:

1. **Reduce online password-guessing feasibility:** rate limiting, attempt caps, separating password and MFA verification.
2. **Avoid easily locking out victims:** requests from untrusted sources must not extend locks indefinitely; provide login/recovery paths backed by proven ownership.
3. **Avoid crippling infrastructure:** limiters, CAPTCHA, delays, notification delivery, and password hashing must not become unbounded consumers of CPU/DB/threads.
4. **Never grant access without verification:** any "friction-reduction" mechanism must never bypass passwords, MFA, disabled account flags, or authorization policies.

**Principle:** Account lockout is **one tool for throttling password guessing**, not an entire anti-bot system. Multi-signal limits paired with graduated responses are generally safer than a single `locked` boolean any attacker can trip.

## 2. Distinguishing attack patterns

| Attack type | Behavior | Why one limiter is not enough |
| --- | --- | --- |
| Brute-force | Many passwords for one username | Pure per-IP is evaded by rotating IPs |
| Credential stuffing | Email/password pairs from other breaches tried across many accounts | Each username may have only 1 failure |
| Password spraying | A few weak passwords across many accounts | Account-only misses the broader campaign |
| Distributed low-and-slow | Many proxies, each source sending only a few requests | Per-IP thresholds may never trip |
| Lockout DoS | Sending the exact number of wrong attempts to lock a victim's account | Username-based hard locks are attacker-controlled |
| Notification bombing | Repeatedly triggering lock or password-reset events | Unbounded emails/SMS also cause DoS and costs |
| Resource exhaustion | Sending very long/random usernames, triggering expensive password hashing | Wastes CPU, limiter memory, and Redis keys |

A common misconfiguration is having only a `username+ip` bucket. Rotating IPs still lets an attacker hit that account; rotating usernames lets one IP try thousands of accounts while keeping each pair below threshold. You need **independent** buckets for account, IP/network, and endpoint/service-wide; a pair bucket is only an auxiliary signal.

## 3. How temporary lockout differs from permanent lockout?

| State | Semantics | Allowed ways to unlock |
| --- | --- | --- |
| `ACTIVE` | Can attempt login per policy | Still requires valid password/MFA |
| `THROTTLED` | Must wait or complete an extra step to curb bots | Cooldown expires or valid challenge passed |
| `TEMP_LOCKED` | One password auth path is blocked until `lockedUntil` | Expiration or trusted recovery |
| `AUTHENTICATOR_DISABLED` | An authenticator is no longer permitted per policy | Verified rebind/reset/recovery |
| `ACCOUNT_DISABLED` | Account disabled by admin/policy | Requires an appropriate admin decision |
| `ACCOUNT_EXPIRED` | Account lifecycle ended | Does not auto-unlock when a brute-force timer expires |

**Do not use a single `locked=true` field** for all states above: when a cooldown expires, code setting `locked=false` could accidentally re-enable an admin-disabled account. Nor should `lockedUntil` auto-extend whenever additional requests arrive while already locked.

### Regulations and attempt limits

In NIST SP 800-63B-4, for applicable authenticator types, the verifier must limit consecutive failed authentication attempts with an authenticator on an account to **no more than 100**, and perform disabling/rebinding as specified by the standard. **100 is a ceiling, not a recommended default configuration.** The "lock for 2 minutes after 3 failures" rule in the Java example below only illustrates computation; by itself it **does not prove NIST compliance**. Authenticator type, assurance level, and recovery/rebind mechanisms must be evaluated separately.

## 4. Key policy parameters

A policy must clearly specify:

- **Threshold (`threshold`):** how many failures in the window trigger an action; choose per threat model, do not blindly copy 3 or 5 from a demo.
- **Observation window (`observationWindow`):** e.g., 5, 10, or 15 minutes; use sliding windows/token buckets to avoid fixed-window boundary bursts.
- **Slowdown/lock duration (`cooldown`):** must be finite, capped, and not grow merely from requests arriving while already locked.
- **Graduated response (`escalation`):** source-scoped throttle, challenge, step-up, investigation, or authenticator disablement per policy; not synonymous with infinitely long account lockouts.
- **Reset/decay:** when the password is genuinely right, when the observation window expires, when cooldown ends, and after recovery.
- **Notification throttling:** an account under spam must not generate hundreds of identical emails/SMS.
- **Recovery conditions:** no "unlock" endpoint needing only an email address, and no bypass via client headers.

| Limiting approach | Where it is strong | Potential design flaw |
| --- | --- | --- |
| Fixed-window count | Simple | Bursts at boundary between two intervals |
| Sliding-window count | Sees attempts across a moving interval | Must be atomic across multiple nodes |
| Token bucket | Caps average rate and burst | Burst capacity can be set too large |
| Capped exponential backoff | Raises guessing cost | Waiting via `Thread.sleep` exhausts threads |
| Soft account cooldown | Stops a rapid burst of attempts | Can be repeatedly re-locked to DoS victims |
| Hard account lock | Blocks all password attempts | Attackers actively lock out legitimate users |
| Conditional CAPTCHA | Increases automation cost | Fails against solving services and hurts accessibility |
| Adaptive MFA/step-up | Adds proof of possession | Only safe with enrolled, server-verified factors |

**Locking after 5 failures for 15 minutes is not enough against DoS.** An attacker can send five failures right when the lock expires, turning a 15-minute penalty into multi-hour denial of access.

## 5. Illustrative attack: before and after

**Flawed design — username-only hard lock:**

~~~text
09:00  Attacker learns username "an" from a public page.
09:01  Attacker sends 5 wrong passwords for "an".
09:01  Server locks account "an" for 30 minutes.
09:05  Account owner enters the right password -> still rejected.
09:31  Lock expires. Attacker sends 5 wrong passwords again.
09:32  Account owner is blocked again.
~~~

No password guess needs to succeed to break service availability. If the UI returns "Account an exists, locked until 09:31", the attacker also gains an **oracle to probe identities and schedule the next lock wave**.

**Improved design — multi-layered with bounded blast radius:**

~~~text
Internet traffic
  |
  +-- Gateway/WAF: global + IP/network burst + request cost limits
  |
  +-- Login guard: independent account bucket, source bucket,
  |                account-risk/tenant signals, adaptive challenge
  |
  +-- Decision:
  |       ALLOW -> verify password
  |       THROTTLE_SOURCE -> reject source for a short time
  |       STEP_UP -> independent evidence available
  |       TEMP_ACCOUNT_LOCK -> only if policy deems appropriate
  |
  +-- DaoAuthenticationProvider: UserDetailsService + PasswordEncoder
  |
  +-- Success: reset password counter properly, continue MFA if needed
  +-- Wrong password: update counter atomically
  +-- Backend error: infrastructure error, do not count as wrong password
~~~

This **does not guarantee** attackers can never inconvenience users, but reduces the ability of an untrusted source to directly hard-lock a victim and creates clear incident handling paths. Never assume CAPTCHA proves a legitimate owner; it only curbs automation.

## 6. Designing a multi-dimensional limiter

| Bucket | Key value | Rationale |
| --- | --- | --- |
| **Account** | Stable account ID, normalized identically to login repository | Stops multi-IP distributed brute-force |
| **Source** | IP verified by trusted reverse proxy, subnet/ASN if appropriate | Stops scanning many usernames from one source |
| **Endpoint/global** | Login, reset, OTP verification, and total capacity | Prevents high-volume traffic from overloading the system |
| **Tenant** | Trusted tenant from server context | Limits campaigns targeting an organization |
| **Session/device** | Bound and verified token when available | Detects automation; never trust fingerprints absolutely |

**Separate account buckets and source buckets**: never replace them with a single `login:{username}:{ip}` bucket. Check at the edge before password hashing because BCrypt/Argon2id are intentionally resource-heavy; a bot flooding random usernames can saturate CPU if every request reaches hashing.

### IPs are untrustworthy if read from arbitrary headers

If an app directly reads `X-Forwarded-For` as the IP without source verification, attackers can send a new IP on every request. Only trust forwarded headers set by **managed** reverse proxies/gateways; configure trusted proxies, handle IPv4/IPv6/NAT, and never blindly pick the first element in the chain without a trust model.

Overly strict IP limits also lock out schools, corporate networks, carrier NATs, or VPN users. IP is a **signal**, not definitive identity. Never force everyone in an ASN to share an "account lock".

### Non-existent usernames

Unknown usernames can still be probing targets. If you create Redis keys for arbitrary usernames without TTLs, attackers sending millions of random strings will fill memory. Require consistent normalization, policy-based length/charset bounds, TTLs, bounded cardinality, and optionally HMAC fingerprints instead of storing plaintext emails. Responses for unknown usernames must match existing usernames with wrong passwords.

## 7. Graduated response policies instead of locking everything

| Signal | Suggested response | Blast-radius limit |
| --- | --- | --- |
| A few typos from a familiar source | Allow retry; reset after successful auth | Do not lock account too early |
| One source bursting over limit | Return 429/cooldown by source, skip further password hashing | Do not penalize the whole account broadly |
| Many sources guessing one account | Account budget + risk scoring + challenge/step-up | Do not turn a few errors into permanent lock |
| One source trying thousands of accounts | Global/source quota and spraying detection | Do not inspect per-user counts alone |
| Suspected account takeover | Restrict risky actions, require strong reauth | Preserve trusted recovery path |
| Authenticator reaches standard disable threshold | Disable/rebind that authenticator | Recover per standard, not by merely clearing a timer |

You can slow attempts by **risk level** rather than "N failures locks everything". Never rely solely on client-controlled geolocation, user-agent, or device fingerprints; combine backend signals and avoid unfairly penalizing traveling users or assistive technology users.

**Important:** A source can *repeatedly re-lock* an account by waiting out each cooldown and retrying. Merely forbidding lock extension **while locked** does not solve the entire DoS; you must detect repeated re-locks, throttle sources/automation, and provide suitably assured recovery/step-up paths.

## 8. State and time model

Suggested stored fields:

| Field | Purpose |
| --- | --- |
| `account_key` | Safe identifier, consistent with UserDetailsService |
| `window_started_at` / sliding-window events | Observed failure window |
| `fail_count` | Failures within window, independent of standard counter if needed |
| `consecutive_failure_count` | Consecutive per-authenticator count if required by policy |
| `locked_until` | Temporary lock expiration timestamp, UTC |
| `version` / `lock_generation` | Prevents stale writes and lost updates |
| `last_success_at`, `last_failed_at` | Reset, telemetry, and auditing |
| `risk_state` | State derived from source/device signals |
| `account_status` | Admin-disabled/expired separated from temp lock |
| `last_notification_at` | Curbs email/SMS bombing |

Clear invariants:

~~~text
isTemporaryLocked(now) = now < lockedUntil
canTryPassword = accountEnabled
             AND not authenticatorDisabled
             AND not temporaryLocked
             AND sourceAndGlobalBudgetsAllow
~~~

When `now == lockedUntil`, the temporary lock **expires**. Never clear admin-disabled or authenticator-disabled flags just because a deadline passed. The server uses `Instant`/UTC with synchronized clocks; never trust timestamps sent by browsers.

## 9. Standalone Java 17: finite lock, spam does not extend

This program demonstrates a 5-minute sliding window, threshold 3, 2-minute lock. These numbers are **for testing only** and should not be used directly in production. `synchronized` only protects within **one JVM**; distributed systems need atomic Redis/DB operations.

Create `TemporaryLockDemo.java`:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayDeque;
import java.util.Deque;

public final class TemporaryLockDemo {

    static final class Guard {
        private static final int LIMIT = 3;
        private static final Duration WINDOW = Duration.ofMinutes(5);
        private static final Duration LOCK = Duration.ofMinutes(2);

        private final Deque<Instant> failures = new ArrayDeque<>();
        private Instant lockedUntil = Instant.EPOCH;

        synchronized String check(Instant now) {
            return now.isBefore(lockedUntil) ? "TEMP_LOCKED" : "ALLOW";
        }

        synchronized void badPassword(Instant now) {
            if (now.isBefore(lockedUntil)) {
                // Requests during a lock must not extend the deadline.
                return;
            }
            if (!lockedUntil.equals(Instant.EPOCH)) {
                lockedUntil = Instant.EPOCH;
                failures.clear();
            }

            Instant cutoff = now.minus(WINDOW);
            while (!failures.isEmpty()
                    && !failures.peekFirst().isAfter(cutoff)) {
                failures.removeFirst();
            }
            failures.addLast(now);
            if (failures.size() >= LIMIT) {
                lockedUntil = now.plus(LOCK);
                failures.clear();
            }
        }

        synchronized void realSuccess(Instant now) {
            if (!now.isBefore(lockedUntil)) {
                failures.clear();
                lockedUntil = Instant.EPOCH;
            }
        }

        synchronized Instant deadline() {
            return lockedUntil;
        }
    }

    public static void main(String[] args) {
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-06T00:00:00Z"), ZoneOffset.UTC);
        Instant t = clock.instant();
        Guard guard = new Guard();

        System.out.println("initial: " + guard.check(t));
        guard.badPassword(t.plusSeconds(1));
        guard.badPassword(t.plusSeconds(2));
        System.out.println("after 2 failures: " +
                guard.check(t.plusSeconds(2)));

        guard.badPassword(t.plusSeconds(3));
        System.out.println("after 3 failures: " +
                guard.check(t.plusSeconds(3)));

        Instant firstDeadline = guard.deadline();
        guard.badPassword(t.plusSeconds(4));
        System.out.println("attack extended lock: " +
                !guard.deadline().equals(firstDeadline));

        System.out.println("before deadline: " +
                guard.check(t.plusSeconds(122)));
        System.out.println("at deadline: " +
                guard.check(t.plusSeconds(123)));

        guard.badPassword(t.plusSeconds(124));
        System.out.println("first new failure: " +
                guard.check(t.plusSeconds(124)));

        guard.realSuccess(t.plusSeconds(125));
        System.out.println("after real success: " +
                guard.check(t.plusSeconds(126)));
    }
}
~~~

Run with JDK 17+:

~~~bash
javac TemporaryLockDemo.java
java TemporaryLockDemo
~~~

**Exact** stdout:

~~~text
initial: ALLOW
after 2 failures: ALLOW
after 3 failures: TEMP_LOCKED
attack extended lock: false
before deadline: TEMP_LOCKED
at deadline: ALLOW
first new failure: ALLOW
after real success: ALLOW
~~~

Explanation: Three failures occur at 00:00:01–00:00:03Z so the deadline is **00:02:03Z**. The wrong request at 00:00:04Z is ignored without extending; 00:02:02Z is still locked and 00:02:03Z is unlocked. A failure after lock expiration starts a new window; `realSuccess` must only be called from a real password verification result, never when the client claims "success".

The example's window is `(now-5 minutes, now]`: a failure right on the left boundary is dropped. Always test boundaries rather than assuming behavior from rounded minute intervals.

**Mandatory limitation reminder:** This is a **lock state simulation**, not protection against attackers continually re-locking right after each 2-minute expiration. It lacks shared storage, multiple sources/IPs, MFA, NIST controls, recovery, username-enumeration defense, real-scale lockout DoS mitigation, and password-hash CPU protection. **Do not use standalone in production**.

## 10. Atomicity and multiple instances: do not use in-RAM counters

If two wrong requests hit two pods, both may read `fail_count=4` and write `5`. One attempt is lost; conversely, a success could also double-count or race with a lock. Put state in a shared store with transactions/atomic scripts and TTLs.

### SQL inside a transaction

~~~sql
BEGIN;

SELECT fail_count, window_started_at, locked_until, version
FROM login_throttle
WHERE account_key = :account_key
FOR UPDATE;

-- Server code checks trusted time:
--   still locked -> do not extend locked_until;
--   old window expired -> reset window per policy;
--   if password is actually wrong -> update counter;
--   threshold reached -> set finite locked_until.

UPDATE login_throttle
SET fail_count = :updated_count,
    window_started_at = :updated_window,
    locked_until = :updated_deadline,
    version = version + 1
WHERE account_key = :account_key;

COMMIT;
~~~

This is **SQL pseudocode** for DBs supporting `SELECT ... FOR UPDATE`, not a standalone production script. You must implement `INSERT/UPSERT` for the first record with a unique constraint, handle 0 rows, isolation, retries/idempotency, disabled state, and proper resets. If using optimistic locking, add `WHERE version = :expected_version` and **never overwrite** a snapshot when the version changed.

### Redis and token buckets

A Redis Lua script/transaction can read `fail_count`, deadline, window, check `now`, and update **atomically**. While a lock is active, it must return the decision without extending the deadline. Set short appropriate TTLs and bounded cardinality. When using Redis Cluster, design hash slots for keys needing atomicity; never assume cross-slot scripts run atomically.

Never perform separate `GET` then `SET` over the network without concurrency handling. Never use long user-controlled raw emails as Redis keys without TTL. Never treat one pod's local cache as the cluster-wide lock source of truth.

### Do not create delays with sleep

Inserting `Thread.sleep(30_000)` in each rejected HTTP login request holds the Servlet thread and connection for 30 seconds. An attacker only needs to flood a few hundred requests to exhaust the thread pool. Reject early with 429/generic responses, or use non-blocking scheduling/backoff **with bounded concurrency** when truly required. Password encoders cost CPU, so limiting sources/edge traffic before password verification is essential for availability.

## 11. Built-in extension points provided by Spring Security

Spring Security 6 provides these components:

- `DaoAuthenticationProvider` verifies username/password via `UserDetailsService` and `PasswordEncoder`.
- `UserDetails.isAccountNonLocked()` with `AccountStatusUserDetailsChecker` checks account status, potentially throwing `LockedException`.
- `AuthenticationProvider`, `AuthenticationManager` to coordinate authentication.
- `AuthenticationFailureHandler`/`AuthenticationSuccessHandler` and application events to handle form-login outcomes.
- `SecurityFilterChain`, `AuthenticationEntryPoint`, `AuthorizationManager`, and session management.

The framework **does not automatically create** multi-tier account/IP/global budgets, sliding-window stores, risk engines, DoS-resistant unlock policies, or recovery. Merely overriding `isAccountNonLocked()` to return false after a few password errors does not keep the system safe from lockout DoS.

**When using `LockedException`:** This exception only means the request was rejected due to lock state; it **does not assert whether the password was right or wrong**. Therefore, do not increment the bad-password counter again. Likewise, DB/KMS/timeout errors are not `BadCredentialsException` and must not be recorded as user failures.

## 12. Integrating with AuthenticationProvider: avoiding double-counting

Suggested flow:

~~~text
Request /login
    |
    +-- gateway source/global rate limits
    |
    +-- policy.accountCooldown(login) -> if blocked, return generic error
    |
    v
AuthenticationManager -> ThrottledPasswordProvider
    |
    +-- delegate DaoAuthenticationProvider -> UserDetails + PasswordEncoder
    |
    +-- BadCredentialsException -> recordBadPassword once, atomically
    +-- LockedException -> account state error, do not increment password failures
    +-- DB outage -> infrastructure error, do not increment password failures
    +-- success -> reset password counter for the right account/factor
    |
    v
MFA if needed -> full session only after sufficient factors
~~~

Example application-implemented interface (must include a shared store and separate source/risk policies):

~~~java
package example.security;

public interface LoginAttemptPolicy {
    boolean temporaryAccountCooldown(String username);
    void recordBadPassword(String username);
    void recordPasswordSuccess(String username);
}
~~~

Provider wrapper for username/password:

~~~java
package example.security;

import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;

public final class ThrottledPasswordProvider implements AuthenticationProvider {
    private final AuthenticationProvider delegate;
    private final LoginAttemptPolicy policy;

    public ThrottledPasswordProvider(
            AuthenticationProvider delegate, LoginAttemptPolicy policy) {
        this.delegate = delegate;
        this.policy = policy;
    }

    @Override
    public Authentication authenticate(Authentication request)
            throws AuthenticationException {
        if (!(request instanceof UsernamePasswordAuthenticationToken)) {
            return null;
        }

        String username = request.getName();
        if (policy.temporaryAccountCooldown(username)) {
            throw new LockedException("Temporarily restricted");
        }

        try {
            Authentication result = delegate.authenticate(request);
            if (result != null && result.isAuthenticated()) {
                policy.recordPasswordSuccess(username);
            }
            return result;
        } catch (BadCredentialsException invalid) {
            policy.recordBadPassword(username);
            throw invalid;
        }
    }

    @Override
    public boolean supports(Class<?> authentication) {
        return UsernamePasswordAuthenticationToken.class
                .isAssignableFrom(authentication)
                && delegate.supports(authentication);
    }
}
~~~

**Read the code within its intended scope:** `temporaryAccountCooldown` must reflect a **lockout-DoS-mitigating policy decision**, not a hardcoded raw 3-failure threshold. The interface above does not carry IP/counters because the source/IP layer sits at the gateway or a separate service; both must be integrated. `LoginAttemptPolicy` must be a thoroughly tested, atomically updating bean.

`recordPasswordSuccess` only confirms the password factor succeeded. If the user still has MFA, MFA must be enforced before full authentication. Do not reset TOTP counters just because the password was right; do not elevate authorities based on client-sent fields.

**Avoid bypasses:** Do not register both the raw delegate and the wrapper as two independent providers supporting `UsernamePasswordAuthenticationToken`. If `ProviderManager` has another fallback path, account throttling can be bypassed. Check other login APIs, OAuth2/OIDC, remember-me, mobile APIs, and multiple `SecurityFilterChain`s as well.

### Spring Boot 3.x / Spring Security 6.5 configuration

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class LoginSecurityConfiguration {

    @Bean
    AuthenticationProvider throttledProvider(
            UserDetailsService userDetailsService,
            PasswordEncoder passwordEncoder,
            LoginAttemptPolicy attemptPolicy) {

        DaoAuthenticationProvider delegate =
                new DaoAuthenticationProvider(userDetailsService);
        delegate.setPasswordEncoder(passwordEncoder);
        return new ThrottledPasswordProvider(delegate, attemptPolicy);
    }

    @Bean
    SecurityFilterChain loginChain(
            HttpSecurity http, AuthenticationProvider throttledProvider)
            throws Exception {
        return http
                .authenticationProvider(throttledProvider)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error",
                                "/assets/**", "/account/recovery/**")
                        .permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form.failureUrl("/login?error"))
                .build();
    }
}
~~~

This is a **configuration fragment**, not a standalone `javac`-runnable example. The app must provide `UserDetailsService`, `PasswordEncoder`, policy/Redis/DB, login form, and recovery controller; source/global limits must be configured at the gateway or a separate filter. The `/login?error` URL should only display a generic message, never exposing internal status from `LockedException`.

If counters are already recorded in the wrapper, `AuthenticationFailureHandler` **must not** record another failure. The failure handler is suitable for generic responses or controlled telemetry; by itself it does not enforce pre-auth limits because it only runs **after** failure.

### Spring Security 2026 patch note

Spring published **CVE-2026-22746 (2026-04-20)** regarding **timing-based user attribute enumeration** when using `DaoAuthenticationProvider` with disabled/expired/locked accounts. For affected branches, fixes are in **6.5.10** and **7.0.5**. Run the latest supported patch in your active branch; do not assume a generic error message alone prevents username enumeration if code paths have differing execution times.

## 13. Public responses and preventing username enumeration

A login endpoint must not return noticeable differences between:

- User does not exist.
- User exists but password is wrong.
- Account is temporarily locked or disabled.
- Authenticator expired/lacks sufficient factors for a session.
- A source must wait due to risk-based policy.

Generic message example: **"Unable to complete sign in. Please check your credentials or try again later."**

Never return: "Account minh@example.test exists, failed 5 times, unlocks at 09:35" to unauthenticated callers. That information lets attackers discover usernames, time attacks, or repeatedly re-lock accounts.

Check not only the **body** but also HTTP status, differing redirects, response length, cookies, verification timing, side-channel data, and email reset events. Exact status can be shown inside a **strongly authenticated account-management channel**, not public login.

Equalizing response time with random `Thread.sleep` is not a default solution: long sleeps can cause CPU/thread DoS. Prefer timing patches, cost controls, and request limits before password hashing.

## 14. Reset, recovery, and avoiding abused unlock paths

**When real password authentication succeeds:** reset/decay password counters per policy; never clear security audits or alter `ACCOUNT_DISABLED`. **When MFA fails:** increment the MFA factor's counter, do not treat as a wrong password. **When the store fails:** do not count user password failures.

**Recovery paths must verify ownership**, for example:

1. Enrolled passkey/WebAuthn or MFA providing independent proof per policy.
2. Random, short-lived, single-use password reset tokens with quotas and permission checks; do not assume email reset alone suffices for high-MFA accounts.
3. High-entropy, rate-limited recovery codes, stored hashed and consumed atomically.
4. Procedural helpdesk identity checks, resistant to social engineering, with audit trails of who unlocked.
5. Out-of-band notifications aggregated and rate-limited to prevent email/SMS bombing.

Never create a `POST /unlock` endpoint anyone who knows a username can call to unlock. Do not invalidate all valid sessions merely because an attacker typed a few wrong passwords, unless compromise signals exist and policy dictates it; conversely, once account compromise is confirmed, you must be able to force reauth/revoke sessions.

During temporary unlocks, only modify the scoped cooldown/counter fields. Admin-disabled, revoked-factor, account-expired, and risk flags must not be overwritten by a stale "active" write. Under concurrent requests, use versioning/transactions so an older password success cannot clear a subsequent emergency lock decision.

## 15. Limiter store outages and availability

If Redis/DB for throttling becomes unavailable, there are two failure modes:

- **Uncontrolled fail open:** skips all rate limits, letting bots brute-force and overload password hashing.
- **Prolonged total fail closed:** no users can log in, turning the limiter itself into a single point of failure and DoS.

A sensible strategy must be threat-modeled, such as HA stores, short timeouts, circuit breakers, active edge quotas, risk-adaptive MFA, and **pre-approved** fallbacks by resource type. If a **mandatory** security check for an authenticator/session type is missing, never silently allow it through. During degradation, log internally, alert, and recover quickly; do not serve indefinitely stale/wrong state.

Common operational mistakes:

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `Thread.sleep` in HTTP threads | Pool exhaustion | Early reject / bounded async |
| Redis keys by raw username without TTL | RAM exhaustion | Normalization, TTL, cardinality limits |
| Single-pod in-memory counters only | Easily bypassed by switching pods | Shared atomic store |
| Rate limiting by untrusted IP headers | Header spoofing | Trusted proxy model |
| Limiting account only, not source | Password spraying | Independent source/global budgets |
| Limiting source only, not account | Distributed botnets | Independent account budget |
| Lock timer extended by every wrong request | Victim cannot unlock | Do not alter deadline while locked |
| Timer expiration re-enables admin-disabled too | Re-opens account against policy | Separate state types |
| Counting failures in both provider and handler | Account locks too early | Clear counter ownership |
| DB errors counted as wrong passwords | Victims locked out by outages | Classify infrastructure errors |
| Emailing on every wrong request | Notification bombing | Throttled notification workflow |
| Generic message but differing timing | Account enumeration | Spring patch and integration tests |

## 16. Testing matrix

### Unit tests with fixed time

- 0/1/2/3 failures per illustrative threshold, window, and deadline yield exact results.
- `now = lockedUntil.minusNanos(1)` stays locked; `now = lockedUntil` unlocks.
- Repeated failures during lock do not extend `lockedUntil`; after lock expires a new window can start.
- **Repeated re-lock** is still detected and curbed via source/risk controls, not just timer unit tests.
- Real password success resets the right counter; wrong OTP does not change password counters.
- `BadCredentialsException` counts once; `LockedException`, disabled accounts, DB outages, and timeouts are not counted as wrong passwords.
- Username normalization shares identical rules across DB lookup, limiter, and logs; case/Unicode differences do not create extra identities outside policy.
- Probing from 1 IP to 1,000 users and 1,000 IPs to 1 user: each campaign hits its respective bucket.
- Unknown usernames do not grow memory unboundedly and do not leak accounts via status/body/timing.

### Concurrency and infrastructure

- Two concurrent wrong passwords on two pods at threshold: counter, lock deadline, and version remain accurate.
- An older success arriving after admin-disable does not re-enable the user.
- Redis failover, replication lag, event loss, service timeout: no silent bypass.
- Shared NAT/IPv6/enterprise proxies: acceptable false-positive rate and valid challenge path.
- Bots sending oversized bodies, forged headers, random usernames: limiter and password hashing do not exhaust CPU/threads.
- Load test `/login`, `/account/recovery`, and `/otp/verify` with independent budgets.

### Spring Security MockMvc/integration

| Case | Result to verify |
| --- | --- |
| Valid password, normal | Creates proper Authentication and resets password counter |
| Wrong password | Generic error, counter incremented once |
| Non-existent user | Not leaked via body/status/timing |
| Temp-locked | No new session granted, deadline not extended |
| Admin-disabled | Does not auto-unlock when timer expires |
| Passed password but missing MFA | MFA-protected resources denied |
| Unlock/recovery path lacking sufficient proof | Does not unlock or grant access |
| Store outage | Reports infrastructure failure, not counted as wrong password |
| Two filters/handlers observe one failure | No double-counting |
| Multiple AuthenticationProviders | No path bypassing throttled provider |
| Shared IP and multi-IP botnet | Limiters enforce policy accurately |
| Request blocked by WAF | Never reaches controller, matching log/metric recorded |

Verify HTTP boundaries too: a protected controller might return 404 for business logic; never assume valid auth always yields 200. Test gateway/WAF outside MockMvc because edge-blocked requests never enter Spring MVC.

## 17. Metrics and operational procedures

Track metrics affecting **both security and availability**:

- Rates of `login_attempts`: succeeded, bad credentials, throttled, locked, and infrastructure errors.
- Count of **real accounts temporarily locked**, repeated re-lock frequency, median/p95 block duration.
- Recovery success rate, time to recover, helpdesk escalation count.
- Password-spraying requests from one source and distributed attempts on one user.
- Password hashing CPU, Redis latency, DB saturation, limiter errors, and request backlog.
- CAPTCHA fail/solve rates, accessibility complaints, and false positives across legitimate network cohorts.
- Alert email/SMS volume and notification-bombing signals.
- Result discrepancies across gateways/regions and `lockedUntil` clock sync drift.

Never put raw usernames/emails/passwords/OTPs/session cookies into metric labels or HTTP access logs. Keep metric cardinality low; separate detailed audits with RBAC, redaction, and proper retention. If a new policy spikes lockouts for real users, use feature flags/canaries/controlled rollbacks rather than silently loosening all protections.

## 18. Pre-production checklist

**Policy and anti-DoS**

- [ ] Threat-modeled brute-force, stuffing, spraying, distributed attacks, and targeted lockout DoS.
- [ ] Separate account/IP/endpoint buckets; quotas tailored to user types, MFA, and compliance standards.
- [ ] Finite lock duration, never extended by blocked requests, with mitigations for repeated re-locks.
- [ ] Distinguishes temp lock, authenticator disabled, and admin-disabled; never auto-unlocks admin states.
- [ ] Verified independent-proof recovery/reauth exists; no public unlock bypass.

**Engineering**

- [ ] UTC timestamps/`Instant`, boundary tests, atomic store, unique keys/TTL, and versioning or row locking.
- [ ] Source addresses trusted only via trusted proxies; handles NAT, IPv6, and username normalization.
- [ ] Load limited before password hashing; no long blocking sleeps in servlet threads.
- [ ] Each bad password increments counters once; backend failures are not counted as wrong passwords.
- [ ] Generic error responses; never leaks account existence, locked state, or unlock time.
- [ ] Spring Security runs patched versions for relevant advisories, tested for timing and multiple security chains.
- [ ] Limiter store is HA with approved failure/degraded mode policies, no silent bypasses.

**Operations**

- [ ] Tested multi-instance, races, DB/Redis outages, botnet sources, and shared user networks.
- [ ] Password reset, OTP verification, recovery, and notifications also have anti-abuse controls.
- [ ] Monitoring tracks lockout amplification, false positives, recovery, throughput, CPU, and latency.
- [ ] Auditing and feature rollout/rollback in place, no secrets/PII written to telemetry.

**Conclusion:** If a few wrong passwords are all it takes to lock anyone's account, the system has handed attackers a DoS tool. Resilient defense combines **independent account and source limits, graduated responses, bounded lock durations, atomic state, verified recovery paths, and multi-node testing**. Spring Security handles identity verification and authorization; **DoS-resistant throttling policies, storage, recovery, and operations** must be designed by the application.

## References

- [OWASP — Authentication Cheat Sheet (Account Lockout, Login Throttling)](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP — Credential Stuffing Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html)
- [OWASP — Bot Management and Anti-Automation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Bot_Management_and_Anti-Automation_Cheat_Sheet.html)
- [NIST SP 800-63B-4 — Authentication and Authenticator Management](https://pages.nist.gov/800-63-4/sp800-63b.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security — LockedException](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/LockedException.html)
- [Spring Security — CVE-2026-22746 User Attribute Enumeration](https://spring.io/security/cve-2026-22746/)
- [Java SE 17 — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html)
