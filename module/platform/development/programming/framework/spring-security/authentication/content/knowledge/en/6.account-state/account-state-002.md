# isAccountNonLocked and Account Lockout Policy

> **Topic:** Account state in Spring Security – authentication (Servlet). This lesson explains the meaning of `UserDetails.isAccountNonLocked()`, how Spring Security rejects logins with `LockedException`, how to build a safe lock/unlock policy, how to distinguish account lockout from throttling, and how to test on Java 17+.

## 1. A valid password does not guarantee login permission

Suppose account An has username `an` and a valid password. If suspicious login activity is detected, the system may decide to temporarily lock the account for a period of time. On the next login attempt, even if An enters the correct password, the server must still refuse to create a new authenticated session for the locked account.

That is the meaning of **account lock state**: the account exists and may have a valid password, yet current policy does not permit it to participate in a new authentication session.

Three separate questions need answers:

1. **State:** is the account currently locked or not?
2. **Policy:** what condition locks it, for how long, who has permission to unlock it, and how are incidents handled?
3. **Enforcement:** during authentication, what does the framework do with the state supplied by the user store?

Spring Security handles the third question through `UserDetails.isAccountNonLocked()` and status checks inside `AuthenticationProvider`; the framework **does not automatically provide all** of the second question merely because you implement that interface.

For example: "three wrong attempts within a time window → temporary 60-second lock" is **the demo application's policy**, not Spring Security's default behavior.

## 2. The isAccountNonLocked() contract: true means NOT locked

`isAccountNonLocked()` is a method on `org.springframework.security.core.userdetails.UserDetails`:

```java
boolean isAccountNonLocked();
```

The method returns **`true` if the account is not locked** and **`false` if it is currently locked**. The method name carries a negative sense; avoid flipping the sign.

| Business state | `isAccountNonLocked()` | Typical pre-authentication check result |
| --- | --- | --- |
| Normal account | `true` | Continue remaining checks |
| Currently locked account | `false` | Throws `LockedException`, does not issue successful authentication |
| Unlock deadline reached and policy cleared lock | `true` | Can attempt authentication again |
| Status database unavailable | Cannot determine reliably | Fail safely; do not default to `true` |

**`true` does not yet mean login succeeds.** The provider still has to check username/password, disabled/account-expired/credentials-expired states, and other conditions. `false` also **does not mean the password is wrong**.

### Mapping lock state from the database in the right direction

Suppose the database stores a `locked` column (`true` means **currently locked**). If you implement `UserDetails` yourself, you must invert it:

```java
@Override
public boolean isAccountNonLocked() {
    return !account.isLocked();
}
```

This is an **illustrative code snippet**, requiring a `UserDetails` class and an appropriate `account` variable.

When using the `org.springframework.security.core.userdetails.User` builder, you can pass the flag directly:

```java
UserDetails details = User.withUsername(account.username())
        .password(account.encodedPassword())
        .authorities("ROLE_USER")
        .accountLocked(account.locked())
        .build();
```

The snippet above is also an **illustrative Java fragment** with an assumed `account`. The builder's `accountLocked(true)` means lock the account; the resulting `UserDetails` object has `isAccountNonLocked() == false`. Do not pass `!account.locked()` into the builder, as that double-negates it.

### Account lock differs from the other states

| UserDetails method | When returning `false` | Typical exception |
| --- | --- | --- |
| `isAccountNonLocked()` | Account is currently locked | `LockedException` |
| `isEnabled()` | Account is disabled | `DisabledException` |
| `isAccountNonExpired()` | Account has expired | `AccountExpiredException` |
| `isCredentialsNonExpired()` | Credentials have expired | `CredentialsExpiredException` |

These states should not be substituted for one another arbitrarily. For example, an account permanently closed by administrative decision differs from an account automatically locked for 60 seconds after consecutive wrong passwords. An expired subscription might still be allowed to log in to pay for renewal, so `AccountExpiredException` is not necessarily appropriate.

## 3. At which step does Spring Security check lock state?

With username/password and `DaoAuthenticationProvider`:

```text
Request: untrusted username + password
                   |
                   v
          Authentication Filter
                   |
                   v
          AuthenticationManager
                   |
                   v
          DaoAuthenticationProvider
                   |
                   +-- UserDetailsService.loadUserByUsername(...)
                   |         |
                   |         +-- password hash
                   |         +-- authorities
                   |         +-- isAccountNonLocked()
                   |
                   +-- Account status check
                   |         |
                   |         +-- false -> LockedException
                   |
                   +-- PasswordEncoder / credential verification
                   |
                   +-- Post-credential status check
                   |
                   +-- Only if valid: successful Authentication
                   |
                   v
            SecurityContext + authorization
```

`AbstractUserDetailsAuthenticationProvider` has **pre-authentication checks**. In the standard DAO mechanism, the `isAccountNonLocked()` check runs before accepting the authentication result. When the account is locked, it throws `LockedException`, a subclass of `AccountStatusException` and `AuthenticationException`.

Key distinctions:

- `UserDetailsService` **reads state** and returns `UserDetails`; it does not complete login itself.
- `DaoAuthenticationProvider` **checks status and credentials**; it prevents a locked account from becoming an authenticated principal.
- `SecurityContext` **is not a state database**. It holds the authentication result of a request/session, which may be a snapshot.
- `LockedException` **does not increment a counter**, does not write `locked_until` to the database, and does not unlock after some duration.
- `AuthenticationEntryPoint`/failure handlers can translate the error into an HTTP response; Java exceptions and HTTP status/body are two distinct layers.

In Spring Security releases patched against timing attacks, the provider may still perform additional credential checks to reduce timing leaks even when a pre-check fails; this **does not** turn a locked account into an authenticated one. Never treat `PasswordEncoder` call ordering as a "password was right" signal or as a basis for unlocking.

### LockedException does not prove the password was right

A locked account can be rejected **before** the password is confirmed. If the backend logs `LockedException`, you cannot conclude "the user entered the right password while locked." A public response revealing "this account is locked" can also help an attacker enumerate valid usernames.

Conversely, if an account simply enters the wrong password and is not yet locked, the provider normally throws `BadCredentialsException`. The application can listen for this event to **decide** whether to increment a failure counter and transition to a locked state.

## 4. Lock state vs. lockout policy

**Lock state** is already-decided data: `locked=true`, `lockedUntil` in the future, or a status code set by an administrator.

**Lockout policy** is the set of rules deciding state transitions. For example:

- Counting window: 10 minutes.
- Threshold: 5 invalid credential checks against one account.
- Action: temporarily lock for 15 minutes or apply a step-up challenge.
- Unlock: lock expiry, administrative action, or a trusted recovery flow.
- On success: reset the consecutive failure counter, depending on policy.
- On non-existent identity: do not create fake account records just because of user input.
- On authentication system error: do not count it as a user-entered mistake.
- Rate limits: control by IP/device/user to mitigate credential stuffing and abuse.

**Counting failures, persisting state, and unlocking belong to the application/identity platform.** Spring Security provides the contract to **enforce** the state received from that source.

### Reference state machine

```text
           +----------------------+
           | ACTIVE (unlocked)    |
           | failedAttempts < N   |
           +----------+-----------+
                      |
                 Bad credentials
                      |
           +----------v-----------+
           | Record one failure   |
           | per window/lock      |
           +----------+-----------+
                      |
                 Threshold met?
              no /          \ yes
                v              v
             ACTIVE       +------------------+
                          | LOCKED_UNTIL(t)  |
                          | Auth rejected    |
                          +--------+---------+
                                   |
                        t reached / valid unlock
                                   |
                                   v
                                ACTIVE
```

This model is **minimal**. Production may require a separate `ADMIN_LOCKED` state (which does not auto-unlock over time), `DISABLED` (account deactivation), account-owner verification, and dedicated policies for privileged accounts.

### Time-bounded lock

If storing `locked_until` as a UTC timestamp:

```text
isAccountNonLocked(now):
    locked_until = NULL     -> true
    now < locked_until      -> false
    now >= locked_until     -> true
```

Here `now` must come from a trusted/standardized clock, such as `Clock`/`Instant`, not from the client. The rule **at the exact expiry boundary** must be consistent: in this example, `now >= locked_until` means unlocked.

If there is also a manual lock flag, the formula can be:

```text
nonLocked = !manuallyLocked
            && (lockedUntil == null || now >= lockedUntil)
```

Do not mix temporary locks and manual locks into a single timestamp and accidentally auto-unlock a permanent lock after 60 seconds.

## 5. Choosing a policy that resists brute force without causing self-DoS

Locking an account sounds like stronger security, yet it has a downside: an attacker only needs a public username and enough wrong password attempts to **lock out the victim's account**. If permanent lockout triggers after 3 wrong tries, the service can suffer widespread disruption.

Therefore, policy should usually combine multiple layers:

| Measure | What does it protect? | Notes |
| --- | --- | --- |
| Rate limiting by IP / device / ASN | Slows down automated password guessing | Avoid penalizing all users behind NAT |
| Account-level throttling | Limits attempts per account | Must guard against attackers continuously locking accounts |
| Temporary lock with TTL | Blocks further attempts past threshold | Can be abused to cause denial of service |
| Progressive backoff | Slows adaptive adversaries | Requires upper bounds and clear policy |
| MFA / step-up verification | Limits damage from a single compromised factor | MFA also needs anti-spam/code-guessing protection |
| Password hashing and breached-password checks | Reduces impact of leaked credentials | Does not replace rate limiting |
| Alerts and verified self-service recovery | Helps legitimate users | Do not offer an overly easy bypass channel |
| Credential stuffing detection | Tracks distributed behavior | Requires telemetry and tuned thresholds |

**There is no universal "3 tries / 60 seconds" threshold for every application.** The demo uses small numbers for easy testing, not as a production recommendation. Financial products, admin systems, and public services have different risks and account lifecycles; final decisions should rely on threat modeling, UX, and recoverability.

### What to count and under which key?

- Count provider-confirmed credential failures, not generic HTTP 401s (401 can also come from missing credentials or expired tokens).
- For non-existent usernames, avoid creating `accounts["arbitrary-name"]` records for every input, or attackers can exhaust memory/tables.
- An account should use an immutable internal account ID as its state key once resolved from a trusted source.
- When multiple login methods exist (password, SSO, magic link, API key), decide whether counters are separate or unified by policy; do not lock SSO accounts due to failures in another mechanism unless required.
- Auditing should record lock state changes, triggering actor, and reason within permitted data scope; never log plaintext passwords or bearer tokens.

## 6. Runnable example: locking after three failures with Spring Security events

The example below uses **Java 17+**, a **Spring Boot Servlet** application with **Spring Web** and **Spring Security** dependencies. Create the project from Spring Initializr with a Spring Boot/Spring Security version **patched for the relevant advisories** (see the version security section below).

We have one demo account:

- Username `an`, password `demo-password`.
- When unlocked, a valid login is permitted.
- Three consecutive wrong entries lock the account for **60 seconds**.
- A subsequent request with the right password is still rejected during the lock window.
- After 60 seconds expire, a valid request can log in again.
- One valid login before reaching the threshold resets the failure count.

**Goal:** illustrate that lock state is managed by the domain layer, `UserDetailsService` reflects it via `accountLocked(...)`, and `DaoAuthenticationProvider` enforces it. This is an **in-memory, single-process** demo; it is not a multi-node-safe or DoS-hardened lockout system.

Create **`src/main/java/com/example/lockdemo/AccountLockDemoApplication.java`**:

```java
package com.example.lockdemo;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.authentication.event.AuthenticationFailureBadCredentialsEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AccountLockDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AccountLockDemoApplication.class, args);
    }
}

// State lives only in a single demo instance.
// Synchronized methods guard mutations on this account.
final class DemoAccount {
    private static final int MAX_FAILURES = 3;
    private static final Duration LOCK_DURATION = Duration.ofSeconds(60);

    private final String username;
    private final String encodedPassword;
    private int failures = 0;
    private Instant lockedUntil;

    DemoAccount(String username, String encodedPassword) {
        this.username = username;
        this.encodedPassword = encodedPassword;
    }

    String username() {
        return username;
    }

    String encodedPassword() {
        return encodedPassword;
    }

    synchronized boolean isNonLocked(Instant now) {
        if (lockedUntil != null && !now.isBefore(lockedUntil)) {
            lockedUntil = null;
            failures = 0;
        }
        return lockedUntil == null;
    }

    synchronized void recordBadCredentials(Instant now) {
        if (!isNonLocked(now)) {
            return; // Do not increment counter while still locked.
        }
        failures++;
        if (failures >= MAX_FAILURES) {
            lockedUntil = now.plus(LOCK_DURATION);
            failures = 0;
        }
    }

    synchronized void recordSuccess() {
        failures = 0;
    }
}

// Record store: contains only one trusted server-managed account.
final class DemoAccounts {
    private final Map<String, DemoAccount> accounts;

    DemoAccounts(PasswordEncoder encoder) {
        this.accounts = Map.of(
                "an", new DemoAccount(
                        "an", encoder.encode("demo-password")));
    }

    DemoAccount findByUsername(String username) {
        return accounts.get(username);
    }

    void badCredentials(String username, Instant now) {
        DemoAccount account = findByUsername(username);
        if (account != null) {
            account.recordBadCredentials(now);
        }
    }

    void success(String username) {
        DemoAccount account = findByUsername(username);
        if (account != null) {
            account.recordSuccess();
        }
    }
}

@Configuration(proxyBeanMethods = false)
class DemoSecurityConfig {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    DemoAccounts demoAccounts(PasswordEncoder encoder) {
        return new DemoAccounts(encoder);
    }

    @Bean
    UserDetailsService userDetailsService(
            DemoAccounts accounts, Clock clock) {

        return username -> {
            DemoAccount account = accounts.findByUsername(username);
            if (account == null) {
                throw new UsernameNotFoundException("Unknown username");
            }

            boolean locked = !account.isNonLocked(clock.instant());
            return User.withUsername(account.username())
                    .password(account.encodedPassword())
                    .authorities("ROLE_USER")
                    .accountLocked(locked)
                    .build();
        };
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users,
            PasswordEncoder encoder,
            ApplicationEventPublisher publisher) {

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);

        ProviderManager manager = new ProviderManager(provider);
        // When constructing ProviderManager manually, configure the publisher explicitly.
        manager.setAuthenticationEventPublisher(
                new DefaultAuthenticationEventPublisher(publisher));
        return manager;
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            AuthenticationManager manager) throws Exception {

        return http
                .authenticationManager(manager)
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/ping").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

// Track credential failures only, not every error/401.
@Component
class LockoutEvents {

    private final DemoAccounts accounts;
    private final Clock clock;

    LockoutEvents(DemoAccounts accounts, Clock clock) {
        this.accounts = accounts;
        this.clock = clock;
    }

    @EventListener
    void badCredentials(AuthenticationFailureBadCredentialsEvent event) {
        // The username in a failure event is still caller-supplied data.
        // The demo store only updates existing real accounts.
        accounts.badCredentials(
                event.getAuthentication().getName(), clock.instant());
    }

    @EventListener
    void authenticated(AuthenticationSuccessEvent event) {
        // Only successful authentication resets the failure streak.
        accounts.success(event.getAuthentication().getName());
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
}
```

### Explaining the flow in the demo

**`DemoAccount`** holds the username, BCrypt password hash, counter, and `lockedUntil`. The `isNonLocked(now)` method clears the lock when expired; no background job is required. `synchronized` prevents arbitrary concurrent mutations on a single account object. It **does not** provide atomicity across the entire "load state → verify password → receive event" cycle across multiple requests; production needs fuller concurrency design.

**`DemoAccounts`** only returns server-controlled records. Unknown usernames do not create new lock records. This prevents one class of memory-growth attacks in the demo, though it **does not** by itself solve all user enumeration and DoS risks.

**`UserDetailsService`** reads `isNonLocked(now)` on each call and passes it to the builder via `accountLocked(locked)`. `UserDetails` has no knowledge of how counters are managed; it only needs to reflect the **current state**. Do not mutate counters inside `loadUserByUsername` itself because this method may be invoked across multiple threads or by caching/lookup mechanisms.

**`DaoAuthenticationProvider`** enforces status and credentials per Spring Security's contract; it will never accept even a valid password when `isAccountNonLocked() == false`.

**`ProviderManager`** is constructed manually and wired with `DefaultAuthenticationEventPublisher`. If you omit `setAuthenticationEventPublisher(...)`, a manually constructed manager may use a default publisher that emits no events, and the counter in `LockoutEvents` will not work. Check the actual configuration of the manager used by the security filter chain; do not create two managers that emit duplicate events.

**`LockoutEvents`** increments the counter only on `AuthenticationFailureBadCredentialsEvent`. For a locked user, the provider throws `LockedException`; it **does not** emit another BadCredentials event just to extend the lock duration. On successful authentication, `AuthenticationSuccessEvent` resets consecutive failures. Events for non-existent usernames do not create fake accounts because the repository only updates known accounts.

**`SecurityFilterChain`** uses Basic so it is easy to test with curl. `/public/ping` is open to anonymous callers, while `/me` requires authentication. There is no public "unlock user" endpoint; any unlock operation added to a real application must be separately protected.

### Notes on Spring Security versions

To ensure account-status checks do not weaken protection against user enumeration via response timing, use a **Spring Security version patched for CVE-2026-22746**: the 7.0.x branch requires **7.0.5 or newer**, and the 6.5.x branch requires **6.5.10 or newer**; other branches follow the official advisory. Do not arbitrarily use an older Spring Boot version managing an unpatched Spring Security release. If a project cannot upgrade immediately, consult Spring's mitigation guidance rather than modifying credential checks yourself without a security review.

The sample code uses the `DaoAuthenticationProvider(UserDetailsService)` API and event publisher supported by Spring Security documentation. Choose a stable Spring Boot version compatible with Java 17+ and a patched Spring Security version; verify via your project's build dependency tree.

## 7. How to run and expected results

In a Spring Boot Servlet project with **Spring Web** and **Spring Security**, place the file in the package above and run one of these two commands (matching your project's build tool):

```bash
./gradlew bootRun
# Or with Maven wrapper:
./mvnw spring-boot:run
```

On PowerShell, use `.\gradlew.bat bootRun` or `.\mvnw.cmd spring-boot:run`. Because the code depends on Spring, it cannot run with a standalone `javac` command without a classpath; the build tool manages dependencies.

### 7.1. Verify normal login

```bash
curl -s http://localhost:8080/public/ping
curl -s -u an:demo-password http://localhost:8080/me
```

When the demo account is unlocked, the response bodies of the two requests are:

```text
pong
principal=an
```

### 7.2. Trigger three consecutive password failures

From a fresh state (e.g., restarting the in-memory app), **send sequentially** three requests with the wrong password:

```bash
curl -i -u an:wrong http://localhost:8080/me
curl -i -u an:wrong http://localhost:8080/me
curl -i -u an:wrong http://localhost:8080/me
```

In this HTTP Basic setup, each request receives **401 Unauthorized**. On the backend, each matching wrong-password failure produces `BadCredentialsException`, the publisher emits a failure event, and the counter increments. The third failure sets `lockedUntil = now + 60 seconds`.

### 7.3. Even the right password is blocked while locked

Send immediately before 60 seconds elapse:

```bash
curl -i -u an:demo-password http://localhost:8080/me
```

The request receives **401** because `UserDetailsService` returns `accountLocked(true)`; the provider rejects authentication. Do not interpret this 401 as certainty that the password was wrong.

After **60 seconds from the lock time have elapsed**, resend the valid credentials:

```bash
curl -s -u an:demo-password http://localhost:8080/me
```

If no other lock events occurred, the body is:

```text
principal=an
```

When `isNonLocked(now)` sees the deadline has passed, it clears the lock/counter before building `UserDetails`. The provider checks the password and login succeeds. This is a **duration defined by the demo**, not an inherent property of `isAccountNonLocked`.

### 7.4. A valid login before the threshold resets the counter

Start the app fresh. Send two wrong requests, then one valid request, then two more wrong requests: in the demo, the failure streak is interrupted by success so the account has **not** reached three consecutive failures after the valid login. When testing in practice, send requests sequentially and verify events are enabled; if a client retries or the network behaves unexpectedly, event ordering may differ from expectations.

**HTTP Basic sends username/password encoded in Base64, not secret encryption.** Test only on localhost; production must use HTTPS. The `WWW-Authenticate` header and error body contents depend on configuration/version, so do not assume fixed message strings.

## 8. Why shouldn't the login UI directly set locked=true?

Some systems implement `POST /login` in a controller and increment a counter on every status 401. That approach is error-prone:

- Many kinds of 401 are not caused by a wrong password: missing credentials, expired tokens, Basic challenges.
- A single controller may not be the only entry point: form login, Basic, method authentication, or other flows.
- If any request naming `victim` can lock the account without limits, attackers can easily cause denial of service.
- Non-atomic counter writes across multiple app instances create race conditions.
- Hand-rolled password checks can bypass `PasswordEncoder`, account flags, and Spring's error handling.

Using failure events or an authentication flow with centralized control points is one approach; **however, you must verify the manager/publisher and event scope**. Some systems need to update the counter in a dedicated transaction after authentication fails rather than relying solely on asynchronous events. An event can be processed twice or arrive late; production designs need appropriate idempotency/ordering.

### Which events should increment the counter?

| Event | Should it increment the "wrong password" counter? | Reason |
| --- | --- | --- |
| `AuthenticationFailureBadCredentialsEvent` | Usually yes, for real accounts under suitable policy | Invalid credentials; may include non-existent usernames |
| `AuthenticationFailureLockedEvent` | Should not increment the wrong-password counter | Account already locked; does not imply wrong credentials |
| `AuthenticationFailureDisabledEvent` | No | Disabled account does not prove wrong password |
| `AuthenticationFailureServiceExceptionEvent` | No | Authentication service encountered an error |
| `AuthenticationSuccessEvent` | Reset per policy | Authentication succeeded |
| Any HTTP 401 | No | Too many causes of 401 other than password |

Spring Security provides `DefaultAuthenticationEventPublisher` and several failure event classes. The default publisher maps exceptions; **mapping is based on concrete exception classes**, so if a custom provider throws custom subclasses you must verify event mapping configuration. Do not assume every HTTP request emits exactly one success/failure event when multiple managers/filters exist.

## 9. Designing a lockout policy for databases and multiple nodes

The demo uses in-memory state, which is suitable for learning but not durable: restarts lose locks, two nodes hold different counters, and `synchronized` does not lock across a network. In production, use a repository/Redis/identity service with atomic update semantics or transactions.

A reference schema:

```text
users:
    id                   UUID PRIMARY KEY
    username             VARCHAR UNIQUE
    password_hash        VARCHAR
    enabled              BOOLEAN
    admin_locked         BOOLEAN

login_state:
    user_id              UUID REFERENCES users(id)
    failed_attempts      INT
    window_started_at    TIMESTAMP WITH TIME ZONE
    locked_until         TIMESTAMP WITH TIME ZONE NULL
    version              BIGINT
```

Separate `admin_locked` (manual lock) from `locked_until` (time-based auto-unlock). If a user–tenant pair uniquely identifies an account, establish the key accordingly. Store timestamps in UTC, use a consistent clock source, and define expiry boundaries clearly.

### Transaction/atomicity

A failure-recording flow should follow consistent rules:

```text
For a reliably resolved accountId:
  BEGIN TRANSACTION
    Lock the state row or use optimistic version/CAS
    Load failed_attempts, window_started_at, locked_until
    If the window has expired:
        reset failure count/window
    If currently locked:
        do not add failures just because another request arrived
    If not locked:
        increment by exactly 1 recorded credential failure
        if threshold reached: set locked_until per policy
    Write required audit record
  COMMIT
```

This is **policy pseudo-code**, not directly runnable SQL. Specific databases need proper transaction isolation, row locks, or optimistic locking; if using cache/Redis, use equivalent atomic scripts/transactions. You must define how **request and event ordering** is resolved: is a request that started before the lock was set but finishes after another request set the lock still accepted? For high-risk operations, policy may require checking the lock immediately before issuing a session.

When duplicate events or listener retries occur, a single failure must not be counted twice due to repeated processing. You can use an event ID, version, unique constraint, or perform the update right inside the authentication boundary transaction. Locking an account must be audited, while avoiding storing raw credentials.

### Fixed vs. sliding windows

- **Fixed window:** counts within a fixed interval; simple, but can allow more attempts across the boundary of two windows.
- **Sliding window:** counts within the most recent rolling interval; reflects attempt rate more accurately, requiring appropriate data storage/aggregation.
- **Exponential backoff:** increases wait times after repeated failure streaks; requires an upper cap and recovery channels.

Choose a policy based on threat model and system load; the demo simply uses "three consecutive failures, lock for 60 seconds" with **no time window on the counter**. In real systems, do not keep two failures from months ago and lock a user on a single new mistake.

### Correctness under concurrency

Even if counter updates are atomic, `UserDetailsService` reading the lock and the provider verifying credentials may run before another request updates `locked_until`. For systems requiring ultra-strict enforcement, account for eventual consistency of lock state across the **entire session/token issuance decision**. Never treat `synchronized` on an entity or a single server as sufficient protection in a multi-instance cluster.

## 10. Anti-user-enumeration and Spring Security 2026 security notes

**User enumeration** is when an attacker infers which accounts exist from different responses or latencies. If the server returns:

- `Unknown username` when no account exists.
- `Account locked` when an account exists and is locked.
- `Wrong password` when an account exists and is unlocked.

then an unauthenticated caller can classify valid usernames.

`DaoAuthenticationProvider` usually masks `UsernameNotFoundException` as `BadCredentialsException`. However, **masking the message is not enough** if processing time for locked/disabled accounts differs noticeably from non-existent or active users.

### Directly relevant advisory

Spring published **CVE-2026-22746 – User Attribute Enumeration when Using DaoAuthenticationProvider** (April 20, 2026). According to the advisory, certain Spring Security versions allow bypassing timing-attack defenses when using `UserDetails.isEnabled()`, `isAccountNonExpired()`, or `isAccountNonLocked()`. Affected branches include 7.0.0–7.0.4 and 6.5.0–6.5.9; corresponding fixes are 7.0.5 and 6.5.10. Older branches have fixes per their support timelines. See the original advisory in the references at the end.

**Therefore:** use a patched Spring Security version via the appropriate Spring Boot/dependency management version; do not arbitrarily disable `setAlwaysPerformAdditionalChecksOnUser(...)` to "optimize performance" without a security assessment. This flag relates to continuing to perform additional checks to reduce timing differences when a pre-authentication status check fails.

Even after upgrading, you still need neutral public messages, rate limiting, secure recovery channels, and appropriate timing tests; a single patch does not replace all anti-enumeration defenses.

### Public responses vs. internal information

Externally, for a Basic API, you can return a generic response when login fails or is locked: HTTP 401 with the protocol challenge. Do not automatically serialize `LockedException.getMessage()` into public JSON. Internally, logs/audits can record the account ID (once verified by a trusted source), event type, timestamp, mechanism, and correlation ID, while never logging passwords, bearer tokens, cookies, or password hashes.

A self-service flow that has **verified ownership** can inform the user that they need to wait or complete an unlock procedure. Do not turn an unauthenticated public endpoint into an account-status lookup API.

## 11. Distinguishing account lock, rate limit, disabled, 401, and 403

| Situation | Nature | Common HTTP Basic response |
| --- | --- | --- |
| Incorrect password | Authentication failure | 401 |
| Account locked via `isAccountNonLocked=false` | Authentication failure | 401 |
| Account disabled | Authentication failure due to state | 401 |
| Missing Basic credentials for protected API | Unauthenticated | 401/challenge |
| Authenticated but missing endpoint role | Authorization denied | 403 |
| Too many requests by IP | Throttling/rate limiting before or around auth | May be 429, depending on policy/API |
| Auth backend unavailable | System error | Should not be confused with wrong password; handle operationally |

**There is no 1:1 mapping from a Java exception to an HTTP status in every configuration.** Form login typically uses redirects/failure handlers; bearer tokens use protocol challenges. In the Basic demo, 401 is the common response for login errors.

Account locking and rate limiting can work together, yet they are distinct conditions. A rate limiter may reject a request **before** `UserDetailsService` is ever called; in that case `LockedException` is not necessarily thrown, and a user should not be marked locked solely because an IP exceeded its threshold.

### Do not confuse with AccessDeniedException

If an authenticated user lacks `ROLE_ADMIN`, authorization may throw `AccessDeniedException`; typically HTTP 403. That is **not** an account lock. Conversely, a locked account has not passed authentication, so there is no "successfully logged-in user" whose roles get checked for the new login attempt.

### Customizing responses

If you need generic JSON 401 responses for Basic, customize the corresponding `AuthenticationEntryPoint` and preserve `WWW-Authenticate`. For form login, use `AuthenticationFailureHandler` per that mechanism. `@RestControllerAdvice` is not a catch-all replacement for errors thrown before MVC inside the Spring Security filter chain.

Avoid displaying the exact `lockedUntil` timestamp to unauthenticated callers if that information aids account probing or security-policy mapping. Supportive details can be provided after the account owner is verified through a secure channel.

## 12. Existing logged-in sessions: does locking automatically revoke access?

A commonly missed detail: `isAccountNonLocked()` is typically evaluated **during authentication**. After a successful login, `Authentication` may live inside an HTTP session or a token. If an admin locks a user at 10:00 while the user holds a valid session from 09:00, the framework **does not automatically guarantee** that session is destroyed the moment `locked_until` changes.

Mitigation options depending on requirements:

1. **Invalidation/revocation:** revoke corresponding sessions or refresh/access tokens when applying a lock.
2. **Reasonable TTLs:** shorten how long sessions/tokens can carry stale state.
3. **Checks on sensitive operations:** policy/domain services verify the account is still active before high-risk transactions.
4. **SecurityContext refresh:** design a mechanism to reload account/permission data in the session when needed; avoid trusting a snapshot indefinitely.
5. **Cache invalidation:** if `UserDetailsService` or token introspection uses caching, define TTLs and cache eviction events.
6. **Session auditing:** track actor IDs and login sources; do not use mutable usernames instead of internal user IDs as long-term keys.

With HTTP Basic, credentials are usually re-sent on every request and may trigger a fresh authentication, yet caching/architecture can still delay updates. With self-contained JWTs, locking in the DB does not alter already-signed tokens; you need revocation/TTL/introspection or extra policy checks.

Therefore, **"locking an account" needs a defined scope of effect**: does it only block new logins or also terminate existing sessions? Policy documentation must answer this explicitly.

## 13. Safe unlocking and recovery workflows

There are at least three scenarios:

- **TTL-based auto-unlock:** once `lockedUntil` arrives, the backend treats the state as non-locked; no background timer is needed if the check runs when reading state.
- **Admin unlock:** requires RBAC, auditing, a reason, and abuse prevention. Never build a public `GET /unlock?user=an` endpoint.
- **User recovery:** verify ownership through a trusted channel, apply rate limiting, and avoid exposing user-enumeration signals.

When unlocking, decide whether to reset `failedAttempts` and the failure window. If you only clear `lockedUntil` while leaving the counter at the threshold, the very next failed request could immediately re-lock; that may be right or wrong depending on policy. The demo resets the counter upon unlock.

For manual locks, never auto-unlock them merely because a temporary lock's TTL has passed. If an account is disabled or deleted, clearing a temporary lock must not activate the account either. Status flags must be handled **independently and with a clear policy precedence**.

### User notifications

Lock notifications should go through an appropriate verified channel while minimizing user-enumeration leaks. Do not send unlimited emails/SMS for every failed request, as attackers can abuse this to spam victims. You can batch notifications, rate-limit alerts, and include self-service recovery instructions without leaking sensitive data.

## 14. Mandatory tests for isAccountNonLocked and policy

Do not test only whether the method returns a boolean. A solid test suite separates state data, provider authentication, events/counters, and HTTP/session effects.

| Case | Setup | Expected result |
| --- | --- | --- |
| Normal account | `lockedUntil=null` | `isAccountNonLocked=true`, auth proceeds |
| Active lock | `now < lockedUntil` | `isAccountNonLocked=false`, provider rejects |
| Exact unlock time | `now == lockedUntil` | `isAccountNonLocked=true` per demo policy |
| Right password, currently locked | Account locked | Does not issue authenticated `Authentication` |
| Wrong password, unlocked | State ACTIVE | `BadCredentialsException`, increments counter per policy |
| Three consecutive failures | Counter hits threshold | Sets `lockedUntil`, subsequent auth blocked |
| Valid login before threshold | 1–2 failures recorded | Resets counter |
| Unknown username | No account exists | Does not create fake lock, neutral public response |
| Disabled status | `enabled=false` | Does not use lock flag to stand in for disabled |
| Database error | Cannot read lock state | Fail closed/alert, do not default to non-locked |
| Two concurrent wrong requests | Same user | No lost increments, no arbitrary race |
| Two instances | Shared database/cache | Lock state consistent per contract |
| Manual unlock | Authorized admin | Audited and does not unlock other accounts |
| Old session after lock | Logged in beforehand | Behavior matches revocation policy |
| User enumeration | Wrong/locked/active username | Messages and timing verified |
| Already-issued token | Unexpired JWT/session | Does not assume token self-invalidates on DB change |

### Testing time logic without sleeping 60 seconds

At the domain layer, inject `java.time.Clock` or pass `Instant now` to test decisive timestamps. A simple test snippet using `DemoAccount` from the demo project (this is a **test code snippet**, not a standalone runnable file):

```java
Instant t0 = Instant.parse("2026-01-01T00:00:00Z");
DemoAccount state = new DemoAccount("test", "encoded-unused");

System.out.println(state.isNonLocked(t0));
state.recordBadCredentials(t0);
state.recordBadCredentials(t0);
state.recordBadCredentials(t0);

System.out.println(state.isNonLocked(t0.plusSeconds(59)));
System.out.println(state.isNonLocked(t0.plusSeconds(60)));
```

Exact output when running the snippet above in the same package:

```text
true
false
true
```

This snippet only tests **in-memory state**; it does not check passwords/providers, and the `"encoded-unused"` argument is not used for authentication. Its advantage is testing TTL boundaries instantaneously without waiting in real time. For complex policies, add tests right at window boundaries, for clock skew, and for unlock operations.

### Integration tests

At the HTTP/security layer, besides asserting HTTP 401, verify that no authenticated `Authentication` exists when locked. Verify that the publisher is configured properly, check failure/success event counts, duplicate-event guards, and behavior for non-existent usernames. When multi-node behavior needs testing, use a real test database/Redis or simulate concurrency; unit tests using `synchronized` do not prove cluster safety.

## 15. Common implementation mistakes

| Mistake | Impact | Fix |
| --- | --- | --- |
| Returning `locked` from `isAccountNonLocked()` | Inverted logic; normal users get rejected | Return the negation of the locked flag |
| Calling `accountLocked(!locked)` | Double negation | Builder expects `locked`, not `nonLocked` |
| Assuming Spring counts failures automatically | No state transitions happen | Use a service/event/repository managing policy |
| Incrementing counter on every HTTP 401 | Counts missing tokens, challenges, other errors | Track only appropriate authentication failure types |
| Treating `LockedException` as "password was right" | Information leak and wrong inference | Separate status checks from credential verification |
| Permanent lock after very few failures | Attackers can easily lock out mass users | Layered throttling, TTL, recovery, threat model |
| Locking arbitrary usernames without store binding | Data bloat and user enumeration | Authoritative account lookup, key by account ID |
| Keeping counters only in per-node RAM | Inconsistent lock state | Atomic DB/Redis, transactions, and cache policy |
| Auto-unlocking all locks when TTL expires | Accidentally clears admin locks | Separate manual lock state |
| Creating `ProviderManager` without publisher | Failure events are never published | Configure publisher or explicit integration point |
| Using unordered async events | Success and failure may apply out of order | Clear ordering/idempotency/transactions |
| Using Spring Security versions with timing bug | Enables user attribute enumeration | Upgrade per security advisory |
| Locking user in DB while ignoring old sessions | User continues operating on prior session | Revoke sessions/tokens or refresh policy |
| Logging raw Basic headers/passwords | Credential leak | Minimal logging, avoid secrets |
| Returning `LockedException` in public response | Leaks account state | Generic response, recovery via verified channel |
| Skipping permission checks on unlock | Privilege escalation | Dedicated authorization and auditing for admins |

## 16. Knowledge check

**Question 1.** What does `isAccountNonLocked() == true` mean?  
**Answer:** It only means the account is **not locked**. It does not guarantee the password is right or that all other states are valid.

**Question 2.** The database has `locked=true`. With a custom `UserDetails`, what must the method return?  
**Answer:** `false`. If using the `User.withUsername(...)` builder, call `accountLocked(true)`.

**Question 3.** An account is locked, yet the caller sends the right password. May the provider issue an authenticated token?  
**Answer:** No. The state check must block per contract, independent of the password result.

**Question 4.** Does Spring Security automatically lock a user after 5 `BadCredentialsException`s?  
**Answer:** No. The application/identity platform must define and persist lock state transitions, synchronizing across instances if needed.

**Question 5.** Why can permanent lockout after 3 wrong tries be dangerous?  
**Answer:** An attacker can intentionally submit wrong attempts for a victim's account to deny service to the legitimate user.

**Question 6.** Does a `BadCredentials` failure event always represent a real account?  
**Answer:** No. The provider may mask non-existent usernames as bad-credential errors; do not create user/lock records solely from self-declared usernames.

**Question 7.** Why does a manually created manager need an event publisher configured?  
**Answer:** `ProviderManager` does not guarantee publishing Spring application events by default when constructed manually; without a publisher, listeners may miss the failure/success events required by the policy.

**Question 8.** If `lockedUntil` has passed while the account still has `adminLocked=true`, does it unlock?  
**Answer:** No. A manual lock is a separate condition and is not cleared by TTL expiry.

**Question 9.** Does updating `lockedUntil` in the DB automatically invalidate all issued JWTs/sessions?  
**Answer:** No. You must implement dedicated revocation/refresh/authorization policies if locking should affect existing sessions.

**Question 10.** Does HTTP 401 automatically mean account locked?  
**Answer:** No. It can also be caused by a wrong password, missing credentials, or another authentication mechanism; do not use generic HTTP statuses as a lock counter.

**Question 11.** What must be checked for Spring Security 7.0.0–7.0.4 if using `isAccountNonLocked`?  
**Answer:** Those versions fall under CVE-2026-22746; you must upgrade the 7.0 branch to at least 7.0.5 or an appropriate patched release per the advisory.

## Conclusion

`UserDetails.isAccountNonLocked()` is **the contract representing unlocked state**. Returning `false` causes the standard DAO authentication mechanism to reject login with `LockedException`; it **does not** create a failure-counting policy, decide TTLs, or invalidate existing sessions.

A responsible account lockout policy requires a trusted state source, atomically updated counters/deadlines, rate limiting against both brute force and denial of service, verified unlock channels, session/token revocation when needed, and public messages that do not leak usernames. These measures complement `PasswordEncoder`, `UserDetailsService`, `AuthenticationProvider`, and authorization rather than replacing them.

**Rule of thumb:** *`isAccountNonLocked()` enforces lock state at authentication time; lock/unlock policy, durable updates, and abuse protection must be designed separately.*

### Official documentation

- [Spring Security — UserDetails API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetails.html)
- [Spring Security — User.UserBuilder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/User.UserBuilder.html)
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security — AuthenticationManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationManager.html)
- [Spring Security — Authentication Events](https://docs.spring.io/spring-security/reference/servlet/authentication/events.html)
- [Spring Security — HTTP Basic](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Security — CVE-2026-22746: User Attribute Enumeration when Using DaoAuthenticationProvider](https://spring.io/security/cve-2026-22746/)
