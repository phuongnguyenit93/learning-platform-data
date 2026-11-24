# isCredentialsNonExpired and Required Credential Changes in Spring Security

> **Context:** Spring Security → Authentication → **Account State**. This lesson analyzes the meaning of `UserDetails.isCredentialsNonExpired()`, when `DaoAuthenticationProvider` throws `CredentialsExpiredException`, how to decide a password expiration policy, and how to design a **safe forced password change / credential recovery** flow. Includes a standalone runnable Java 17+ example with Gradle + Spring Security 6.5.x, DB mapping examples, testing, HTTP handling, and risks around sessions, tokens, caches, and authorization.

## 1. The problem: the right password does not guarantee login

Suppose account `mai` has the right password, yet the organization enforces a policy:

- The password has exceeded its allowed age (e.g., 90 days).
- An administrator sets a **must change password** flag for the next login.
- The account was just issued a temporary password that is only permitted for a new-credential setup workflow.
- A leak or credential reset incident invalidated old passwords for normal login.

In situations requiring **blocking normal authentication**, Spring Security provides a status flag on `UserDetails`:

```java
boolean valid = userDetails.isCredentialsNonExpired();
```

This is an illustrative Java snippet inside a method that already has a `userDetails` variable.

- Returns **`true`**: the account's credentials have **not expired** under the policy the application mapped.
- Returns **`false`**: credentials **have expired**; with the default `DaoAuthenticationProvider` flow, the account **cannot authenticate successfully**, even if the password matches the hash.
- The method **does not compute expiration dates**, change passwords, send emails, or open a password-change page. The application must supply its own policy logic and change/recovery workflow.

**Key takeaway:** `isCredentialsNonExpired() == false` does not mean "already logged in, just restricted to the change-password page." In the default flow it is a **reason to reject authentication**. If you want a state of *identity verified yet permissions restricted until credentials are changed*, you must design a dedicated restriction mechanism rather than expecting Spring Security to create that state automatically.

## 2. Distinguishing account states and authentication errors

`UserDetails` describes multiple conditions that can reject login:

| Method | What `true` means | When `false` in standard username/password flow |
| --- | --- | --- |
| `isEnabled()` | Account is enabled | `DisabledException` |
| `isAccountNonLocked()` | Account is not locked | `LockedException` |
| `isAccountNonExpired()` | Account itself is still valid | `AccountExpiredException` |
| **`isCredentialsNonExpired()`** | **Credentials are still valid** | **`CredentialsExpiredException`** |

All four belong to the `UserDetails` contract. In Spring Security 6.5, these status methods default to `true` if an implementation does not override them. If database records have an expired-password flag yet a custom `UserDetails` fails to map it to `isCredentialsNonExpired()`, Spring Security **cannot know** the password expired.

**Differences in meaning:**

- `isAccountNonExpired() == false`: the account itself expired, such as an ended account contract. Changing the password does not make the account valid.
- `isCredentialsNonExpired() == false`: the current login proof is no longer accepted for normal login. After a valid credential-change flow, the account can continue to be used.
- `isAccountNonLocked() == false`: may be due to risk detection or repeated failed logins. Changing the password is **not allowed by default** to auto-unlock if policy requires security-team intervention.
- `BadCredentialsException`: the credentials presented by the user are invalid (or an unrevealed non-existent username); does not imply an expiration policy.
- JWT `exp` claim or OAuth2 access-token expiration: is **token lifetime**, not `UserDetails.isCredentialsNonExpired()`. Those mechanisms typically do not call `DaoAuthenticationProvider` or `UserDetailsService` per token.

### Do not invert the flag's meaning

```text
Are the user's credentials still valid?
    YES -> isCredentialsNonExpired() = true
    NO  -> isCredentialsNonExpired() = false

User builder:
    .credentialsExpired(false) -> credentialsNonExpired = true
    .credentialsExpired(true)  -> credentialsNonExpired = false
```

`User.UserBuilder.credentialsExpired(...)` takes a boolean meaning **expired**, whereas `isCredentialsNonExpired()` means **not expired**. Many configuration bugs stem from passing `credentialsExpired` straight through without inverting the logic.

## 3. When does Spring Security check expired credentials?

With username/password using `DaoAuthenticationProvider`, the basic flow is:

```text
HTTP login request
    ↓
UsernamePasswordAuthenticationToken (unauthenticated)
    ↓
AuthenticationManager / ProviderManager
    ↓
DaoAuthenticationProvider
    ├── UserDetailsService.loadUserByUsername(username)
    │      → UserDetails with password hash, authorities, account flags
    ├── account status checks (locked/enabled/account expired)
    ├── verify raw password with PasswordEncoder
    ├── post-authentication check: isCredentialsNonExpired()
    │      ├── true  → produce successful Authentication
    │      └── false → throw CredentialsExpiredException
    ↓
Authentication success or AuthenticationException
    ↓
Filter proceeds down success or failure branch
```

The description above shows **success/failure semantics**, without promising the exact internal execution order of every patch or implementation. Some Spring Security versions changed how credential checks execute to reduce timing discrepancies and information leaks; inspect the exact source of your version when debugging in detail.

What is certain with the default provider: when credentials are determined to be expired and no custom override replaces it, **no successful Authentication is returned**. `CredentialsExpiredException` is an `AccountStatusException`; `ProviderManager` handles account-status errors by **stopping attempts with further providers**, preventing a weaker provider from automatically "rescuing" an account with expired credentials.

**Consequence with form login:** `AuthenticationSuccessHandler` **does not run** for an authentication rejected by `CredentialsExpiredException`. If UI navigation is needed, handle it appropriately in `AuthenticationFailureHandler` or provide a dedicated workflow for accounts requiring a credential change. However, redirecting to a password-change page **does not make that request authenticated**.

### getCredentials() vs. isCredentialsNonExpired()

- `Authentication.getCredentials()`: the proof submitted by the request (password, token, etc.), which may be erased after successful authentication.
- `UserDetails.getPassword()`: typically the **stored hash** checked by `PasswordEncoder.matches(...)`.
- `UserDetails.isCredentialsNonExpired()`: **policy flag** indicating whether the credentials remain valid.

Do not infer expired credentials from `Authentication.getCredentials() == null`; null may simply reflect post-login secret erasure. Likewise, do not treat the mere existence of a hash as proof that the password is still within its validity period.

## 4. Expiration policy: defined by the application, not the getter

A system may choose the following account table fields:

| Field in account table | Meaning | Usually needed? |
| --- | --- | --- |
| `password_hash` | Current password hash; never store plaintext | Yes for password login |
| `password_changed_at` | Timestamp when credentials were last changed | Needed if validity is measured from last change |
| `password_expires_at` | Computed or explicitly assigned expiration timestamp | Useful for per-account policies |
| `must_change_password` | Force change immediately in the next workflow | Yes for temporary/admin-reset passwords |
| `enabled`, `locked` | Account states independent of password expiry | Per organization policy |
| `security_version` / `credentials_version` | Version used to detect stale sessions/tokens | Useful for revocation; requires check mechanism |
| `password_history` (if present) | Prevents password reuse per policy | Separate design, protect the hashes |

Two common implementation approaches:

1. **Store `password_expires_at`:** expiration relies on an explicit timestamp; update the timestamp on password change or policy change. If null, explicitly define whether it means "never expires" or "unconfigured."
2. **Compute from `password_changed_at`:** e.g., a 90-day lifetime. If no password-change timestamp exists yet, apply a clear rule — some systems force a change, others migrate data with an explicit timestamp.

Do not use `account.updated_at` if it changes whenever the user updates an avatar or email; doing so can accidentally **extend password lifetime** without the user ever changing their password.

### Time-based expiration formula

Given current time `now`, credentials are expired when:

```text
credentialsExpired =
    mustChangePassword
    OR (
        passwordExpiresAt is not null
        AND now >= passwordExpiresAt
    )
```

In Java 17:

```java
boolean expired = account.isMustChangePassword()
        || (account.getPasswordExpiresAt() != null
            && !clock.instant().isBefore(account.getPasswordExpiresAt()));

boolean credentialsNonExpired = !expired;
```

This snippet assumes the entity and `Clock` are already declared, not a standalone program. `!now.isBefore(expiresAt)` includes **the exact expiration instant**, avoiding drift where `now.isAfter(expiresAt)` only rejects slightly past the deadline.

**Use `Instant`/UTC** for storage and comparison, and inject `Clock` to test boundary instants. Do not compare date strings in browser timezones or use `LocalDateTime.now()` without clear conventions. For "until end of day" rules, specify the business timezone and convert to a single `Instant`.

### Is "must change password" the same as "expired"?

Not always. `must_change_password=true` may represent an obligation to fulfill, while the application must choose the **behavior**:

- If **disallowing normal authenticated login**: map it to `isCredentialsNonExpired() == false`, then guide the user to a **separate recovery/credential-change flow**.
- If wanting **identity verified, yet access restricted only to the password-change endpoint**: design an intentionally **separate authentication workflow**, such as a provider/challenge that verifies the password and returns a restricted state with a dedicated authority, short expiry, and deny-by-default policy. Simply flipping the flag to false **does not create** a limited session in the default provider.

Mixing these two approaches easily creates vulnerabilities: the UI shows "please change your password" while the backend still permits sensitive API access because an old `Authentication` remains or another manager succeeded.

## 5. Mapping properly with UserDetails or the built-in User class

### 5.1. Using org.springframework.security.core.userdetails.User

If using built-in `User`:

```java
UserDetails userDetails = User.withUsername(account.getUsername())
        .password(account.getPasswordHash())
        .authorities(account.getGrantedAuthorities())
        .disabled(!account.isEnabled())
        .accountLocked(account.isLocked())
        .accountExpired(account.isAccountExpired())
        .credentialsExpired(account.isMustChangePassword()
                || passwordExpiryPolicy.isExpired(account))
        .build();
```

This snippet depends on `account`, `passwordExpiryPolicy`, and domain-model getters. Note that the builder takes `.credentialsExpired(true)` when credentials **have expired**, opposite to the getter `isCredentialsNonExpired()`. Only use authorities from trusted database sources, never roles sent by the client.

### 5.2. Custom UserDetails implementation

A custom principal must genuinely override the method:

```java
@Override
public boolean isCredentialsNonExpired() {
    return !mustChangePassword
            && (passwordExpiresAt == null
                || clock.instant().isBefore(passwordExpiresAt));
}
```

The snippet above is **a method inside a custom class**, assuming the three fields exist and `clock` is a valid dependency. When creating a user snapshot for a session, do not let `isCredentialsNonExpired()` query the DB on every getter call. It is usually better to **compute the boolean at load time** in `UserDetailsService`, store it on the principal, and keep policy logic in a separate testable class.

In Spring Security 6.5, if you do not override custom status methods, the default value can be `true`; an expired password in the DB cannot alter authentication behavior on its own. Write explicit tests for every status, especially when migrating legacy accounts or changing expiry calculations.

### 5.3. A service method loading users from DB

```java
@Service
public final class DbUserDetailsService implements UserDetailsService {
    private final AccountRepository accounts;
    private final PasswordExpiryPolicy policy;

    public DbUserDetailsService(
            AccountRepository accounts, PasswordExpiryPolicy policy) {
        this.accounts = accounts;
        this.policy = policy;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        AccountEntity account = accounts.findByUsername(username)
                .orElseThrow(() -> new UsernameNotFoundException(
                        "Account not found"));

        boolean expired = policy.isExpired(account);

        return User.withUsername(account.getUsername())
                .password(account.getPasswordHash())
                .authorities(account.getAuthorities())
                .disabled(!account.isEnabled())
                .accountLocked(account.isLocked())
                .credentialsExpired(expired)
                .build();
    }
}
```

This is an **integration pattern** requiring your own `AccountRepository`, `AccountEntity`, `PasswordExpiryPolicy`, and imports. It is not standalone. The goal is to clearly show the data source, where policy is evaluated, and where mapping to default `User` occurs. `DaoAuthenticationProvider` remains the place that checks the password hash via `PasswordEncoder`; do not call `matches(...)` inside `UserDetailsService` to "bypass" the expired flag.

## 6. Runnable Java 17+ example: expiration, failure, and after password change

This demo uses Spring Security **core** with no web server required. It simulates an in-memory account store, a **90-day** rule, and uses **real `DaoAuthenticationProvider` + `ProviderManager`**. The output shows that a right but expired old password still fails; after **simulating an externally verified recovery flow**, the old password no longer works, and the new password authenticates successfully.

**Safety boundary:** the simulated account update function **does not verify identity or a one-time recovery token**. In production, call the update only after verifying proof via the secure workflow in Section 8; never expose the update function as a public endpoint accepting only username and new password.

### 6.1. Project structure

```text
credentials-expired-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/CredentialsExpiredDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'credentials-expired-demo'
```

`build.gradle`:

```groovy
plugins {
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
}

application {
    mainClass = 'demo.CredentialsExpiredDemo'
}
```

Create `src/main/java/demo/CredentialsExpiredDemo.java`:

```java
package demo;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Collectors;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.CredentialsExpiredException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public class CredentialsExpiredDemo {

    private static final PasswordEncoder ENCODER = new BCryptPasswordEncoder();

    // Fixed clock so running in any year yields identical results.
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-11-05T00:00:00Z"), ZoneOffset.UTC);

    // Replace DB with an in-memory store for demo purposes only.
    private static final AtomicReference<StoredAccount> ACCOUNT =
            new AtomicReference<>(new StoredAccount(
                    "mai",
                    ENCODER.encode("old-pass-123"),
                    Instant.parse("2026-07-01T00:00:00Z"),
                    false,
                    true));

    private record StoredAccount(
            String username,
            String passwordHash,
            Instant passwordChangedAt,
            boolean mustChangePassword,
            boolean enabled) {}

    private static final UserDetailsService USERS = username -> {
        StoredAccount account = ACCOUNT.get();
        if (!account.username().equals(username)) {
            throw new UsernameNotFoundException("Account not found");
        }

        Instant expiresAt = account.passwordChangedAt()
                .plus(Duration.ofDays(90));

        boolean expired = account.mustChangePassword()
                || !CLOCK.instant().isBefore(expiresAt);

        // User.UserBuilder takes "expired"; getter returns "non-expired".
        return User.withUsername(account.username())
                .password(account.passwordHash())
                .roles("READER")
                .disabled(!account.enabled())
                .credentialsExpired(expired)
                .build();
    };

    public static void main(String[] args) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(USERS);
        provider.setPasswordEncoder(ENCODER);

        AuthenticationManager manager = new ProviderManager(provider);

        login(manager, "before", "old-pass-123");
        login(manager, "wrong", "wrong-password");

        // Simulates an action ONLY AFTER recovery proof is verified.
        // This example does NOT implement a password recovery endpoint.
        simulateVerifiedRecoveryUpdate();

        login(manager, "old", "old-pass-123");
        login(manager, "after", "new-pass-456");
    }

    private static void login(
            AuthenticationManager manager,
            String label,
            String rawPassword) {
        try {
            Authentication result = manager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "mai", rawPassword));

            String authorities = result.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .collect(Collectors.joining(","));

            String credentialsState =
                    result.getCredentials() == null ? "absent" : "present";

            System.out.printf(
                    "%s: authenticated=%s; name=%s; authorities=%s;"
                            + " credentials=%s%n",
                    label,
                    result.isAuthenticated(),
                    result.getName(),
                    authorities,
                    credentialsState);
        } catch (CredentialsExpiredException ex) {
            System.out.println(label + ": CredentialsExpiredException");
        } catch (BadCredentialsException ex) {
            System.out.println(label + ": BadCredentialsException");
        }
    }

    private static void simulateVerifiedRecoveryUpdate() {
        StoredAccount original = ACCOUNT.get();

        StoredAccount replacement = new StoredAccount(
                original.username(),
                ENCODER.encode("new-pass-456"),
                CLOCK.instant(),
                false, // must clear the required credential change flag
                original.enabled());

        ACCOUNT.set(replacement);
    }
}
```

In the project directory, run with Java 17-compatible Gradle:

```bash
gradle run
```

If using a Gradle Wrapper, run `./gradlew run` on macOS/Linux or `gradlew.bat run` on Windows.

**Main program stdout** (excluding Gradle logs):

```text
before: CredentialsExpiredException
wrong: BadCredentialsException
old: BadCredentialsException
after: authenticated=true; name=mai; authorities=ROLE_READER; credentials=absent
```

### 6.2. Why does the output look like this?

- `passwordChangedAt = 2026-07-01`, the demo clock is at `2026-11-05`, and the **90-day** limit has passed. Even the right password `old-pass-123` triggers `CredentialsExpiredException`.
- Sending `wrong-password` does not match the BCrypt hash, hence `BadCredentialsException`. An account having expired credentials does not mean every request throws only one exception; the outcome depends on which check detects a failure and provider policy.
- `simulateVerifiedRecoveryUpdate()` replaces the hash with the new password's hash, updates the timestamp, and clears the must-change flag. This is **a post-verification data step**; the method itself does not verify the user.
- The old password afterward no longer matches the hash → `BadCredentialsException`.
- The new password matches, is unexpired, and the account is enabled → the manager returns an authenticated `Authentication` with `ROLE_READER`.
- `credentials=absent` simply indicates the secret is absent from the result per the standard flow after Spring Security performs cleanup; it is not a returned or recoverable password.

Do not print raw passwords, hashes, or full `Authentication` objects to stdout. This lesson does not implement HTTP recovery, so it never auto-grants permissions to users with expired credentials.

### 6.3. Try changing conditions

1. Change `passwordChangedAt` to `2026-11-01` while keeping `mustChangePassword=false`: the `before` attempt will authenticate successfully.
2. Keep the newer timestamp but set `mustChangePassword=true`: `before` still gets `CredentialsExpiredException`.
3. Set `enabled=false`: authentication is rejected due to disabled state. When writing automated tests, assert the exact account-status branch of your provider/version.
4. Change the 90-day policy length to 30 days: the expiration date shifts. Never hardcode lifetimes across repositories or controllers; put them in a policy service/config.
5. Set `expiresAt == now` in a policy test function: the result must be expired if the rule says "expired at the deadline."

**Note:** never use `Clock.fixed(...)` in real production, or passwords will never "age" with system time; in production inject `Clock.systemUTC()` or an appropriately operated time service.

## 7. Two approaches to "must change password" and security consequences

This problem naturally leads to the question: "If credentials have expired, how can users change their password when the change-password screen itself requires authenticated login?"

There are two architectural approaches. **Do not accidentally mix them.**

### Approach A — Reject normal login and use a separate recovery flow

This is the natural fit with `isCredentialsNonExpired() == false`:

```text
User submits username + password
     ↓
DaoAuthenticationProvider verifies credentials
     ↓
CredentialsExpiredException
     ↓
AuthenticationFailureHandler (no new authenticated session)
     ↓
Page explaining recovery / password reset
     ↓
User proves account control via recovery proof
     (one-time token / MFA / verified channel, per policy)
     ↓
Server verifies token/challenge + expiry + state
     ↓
Server updates hash + sets passwordChangedAt + clears mustChangePassword
     + handles revocation of related sessions/tokens
     ↓
User logs in again with new password
```

**Advantage:** no need to issue a temporary privileged `Authentication` during primary login, keeping a clean boundary between "verified recovery rights" and "application access."

**Design requirements:** recovery tokens must be random with sufficient entropy, short-lived, single-use, stored hashed or as a non-secret representation, bound to the exact account, and invalidated upon completion. Recovery request responses must minimize leaks of "whether this username/email exists," include rate limiting, auditing, and brute-force controls. Tokens must never be logged or leaked via Referrer headers or third-party URLs. Cookie-receiving endpoints need appropriate CSRF protection.

A redirect from `AuthenticationFailureHandler` to `/account/recovery` is only **UI navigation**; it does not prove identity and must not allow immediate password changes from a self-declared username.

### Approach B — Verify password then grant a restricted access state

Some organizations require users to enter their old password and immediately change it without **using the rest of the application yet**. This requires an **intentionally designed separate authentication workflow**, such as a provider/challenge that verifies the password and returns a restricted state with a dedicated authority, short expiry, and deny-by-default policy.

```text
Input current password
    ↓
Trusted verifier checks password, account state, MFA/risk
    ↓
Create short-lived restricted session/challenge
    ↓
Allow only POST /credentials/change and logout
    ↓
Safely change credentials, destroy challenge, require re-login
```

**Design warning:** if the restricted identity still has `Authentication.isAuthenticated() == true`, any endpoint guarded only by `authenticated()` **may treat this identity as eligible**. Do not just attach `ROLE_PASSWORD_CHANGE_REQUIRED` and hope the user stays restricted. Strictly bind token type/authority, matchers, endpoints, and default-deny; test that regular APIs, token refreshes, managing other users, and sensitive resources are all denied.

Never call `setAuthenticated(true)` in a controller and stuff full user authorities into `SecurityContext`. That bypasses trust boundaries. A restricted flow requires an independently audited credential check and session/challenge issuance mechanism.

### Comparison table

| Criterion | Separate recovery | Restricted change session |
| --- | --- | --- |
| Default `DaoAuthenticationProvider` with expired credentials | Throws error as designed | Requires a custom added flow, not built-in |
| Full authenticated login before change? | No | **No**; restricted state only |
| Required proof | Trusted recovery token/challenge | Verified current password and additional factors |
| Major risk | Recovery token stolen/replayed | Restricted session accidentally passes `authenticated()` |
| After change | Consume recovery token, update DB, re-login | Destroy restricted state, re-login |
| Best suited for | Forgotten password, temporary password, post-incident reset | First-time change UX after credential check, under dedicated policy |

No single flag on `UserDetails` dictates this entire workflow. The flag only describes **credential status** to the provider.

## 8. Mandatory details of a password change/recovery flow

### 8.1. Verify the caller requesting a credential change

Depending on the flow:

- **Already logged in normally and wants to change password:** needs an appropriate reauthentication/step-up policy, usually checking current password and possibly MFA. Do not rely solely on the browser holding an old session.
- **Forgot password or credentials expired and cannot log in:** use a recovery challenge or token from a verified channel; do not require an authenticated `SecurityContext` that the user cannot obtain.
- **Forced change from temporary password:** either issue a one-time setup recovery token at account provisioning time, or implement strict restricted authentication. Never distribute a shared static temporary password across users.

Never allow `POST /reset-password` accepting only `username` and `newPassword` without trusted proof. Likewise, never trust client-submitted `userId` or `email` as proof of account ownership.

### 8.2. Validate the new password

Enforce organization-approved password policy: reasonable minimum length, block leaked passwords, encourage passphrases, support password managers, keep credentials out of logs, and never silently truncate passwords. If password history is required, compare the new password against stored historical hashes using the proper algorithm; never store plaintext for duplicate checks.

Use the configured `PasswordEncoder`; for example:

```java
String newHash = passwordEncoder.encode(newRawPassword);
// Store newHash; never write newRawPassword to DB, logs, or audit events.
```

This snippet requires a trusted `PasswordEncoder` and validated input. Never write raw SHA-256 or reversible encryption for password storage.

**`PasswordEncoder.upgradeEncoding(...)`** and `UserDetailsPasswordService` deal with **upgrading algorithms/hashes** after credentials are verified; they are **not** a "password older than 90 days" flag. Do not flip `isCredentialsNonExpired` based on whether a BCrypt cost or hash prefix is old or new.

### 8.3. Database updates must be consistent

Within a transaction or controlled update operation, you must:

1. Verify the recovery proof is still valid and unused.
2. Update `password_hash` with the new hash.
3. Update `password_changed_at = now` or `password_expires_at` per the new policy.
4. Reset `must_change_password = false` / corresponding credential-expired flag to valid.
5. Increment the security version if the system uses versioning to invalidate snapshots.
6. Mark the recovery token consumed; prevent reuse.
7. Write an audit event containing neither passwords nor recovery tokens.

Illustrative SQL (**assumed schema**, ensuring the token is verified and a transaction wraps all steps):

```sql
UPDATE app_account
SET password_hash = :new_hash,
    password_changed_at = :now_utc,
    must_change_password = FALSE,
    security_version = security_version + 1
WHERE id = :account_id
  AND enabled = TRUE;
```

This is not a complete authorization check: the `account_id` predicate only identifies the row, whereas proof of permission to change the password must be verified **before and inside the transaction**. If concurrent password changes are possible, use version/optimistic locking or row locks to avoid overwriting updates. If the account update commits while the recovery token is not marked consumed, you risk token replay.

### 8.4. Revoke or refresh old authentication states

Changing a password does not mean all sessions, remember-me tokens, JWTs, refresh tokens, or API keys are immediately revoked. Rules are needed per technology:

- Invalidate live HTTP sessions or use a distributed store such as Spring Session when needed.
- Revoke/rotate refresh tokens and remember-me tokens if policy requires.
- For self-contained JWT access tokens, you cannot force all issued tokens to become invalid immediately if APIs only verify signature + `exp` without revocation/version checks. Choose short TTLs, introspection, or appropriate denylist/version checks.
- Update/evict `UserDetails` caches if present; stale caches can still hold the expired flag and old hash.
- Never allow a restricted recovery session to be upgraded into a full session without proper authentication and session-fixation handling.

Explicitly decide "does changing password sign out other devices?" and test that exact requirement. Never claim Spring Security automatically revokes all external credentials merely because a DB column changed.

### 8.5. Responses, auditing, and preventing information leaks

Do not return detailed account status indiscriminately. For instance, normal form login should show a generic message for bad credentials, missing accounts, or locked accounts, unless policy and UI boundaries permit controlled messaging after ownership is proved.

- Rate-limit login and recovery challenges; limit token guessing attempts.
- Never log `Authorization` headers, plaintext passwords, recovery tokens, session IDs, or `Authentication.getCredentials()`.
- Store only necessary audit metadata such as internal account ID, event type, timestamp, correlation ID, and outcome.
- Use HTTPS, secure cookies, CSRF protection for state-changing browser endpoints, and referrer policies when URLs carry tokens.
- When sending "password changed successfully" emails, never embed secrets and provide a path for users who did not initiate the request.

## 9. Spring MVC integration: form login and AuthenticationFailureHandler

If you use `formLogin(...)`, a login attempt failing due to `CredentialsExpiredException` goes to the **failure handler**, not the success handler. A handler can direct the user to a page explaining how to recover.

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers(
                    "/login",
                    "/account/recovery",
                    "/account/recovery/request",
                    "/account/recovery/confirm")
            .permitAll()
            .anyRequest()
            .authenticated())
        .formLogin(form -> form
            .loginPage("/login")
            .failureHandler((request, response, exception) -> {
                if (exception instanceof CredentialsExpiredException) {
                    response.sendRedirect(
                            request.getContextPath() + "/account/recovery");
                } else {
                    response.sendRedirect(
                            request.getContextPath() + "/login?error");
                }
            }));
    return http.build();
}
```

**This is a configuration snippet**, requiring imports, `@Configuration`, recovery controllers/routes, `UserDetailsService`, password encoder, and full security policy. Do not paste it alone into a project and assume you have a working recovery flow. Redirecting to `/account/recovery` leads to **a page starting a safe public workflow**; that page must never allow changing a password solely from a client-supplied username.

**Security notes:**

- `permitAll()` on recovery endpoints **does not mean skipping proof**. The processing endpoint must verify a one-time token or challenge before changing the password.
- For browser POSTs, default CSRF protection must be kept or replaced with an equivalent justified defense; avoid disabling CSRF globally just to make a form submit.
- For APIs not using form login, filters/entry points can return HTTP 401/JSON instead of redirecting; never return a full authenticated token when expired.
- If a browser already holds an authenticated session before credentials expire, the failure handler **does not run on every request**. Design separate revalidation/revocation logic if expiration must take effect mid-session.
- Do not use `.anyRequest().authenticated()` as the sole rule for **restricted sessions** in Approach B; `authenticated()` can let a principal with only password-change authority access far too much.

### Login failure vs. password-change completion

```text
Login FAILURE due to CredentialsExpiredException
   → no new full user Authentication
   → start recovery/challenge (grant no application access)

Verified Password CHANGE
   → update hash + flags + timestamps + token consumption
   → invalidate sessions/recovery tokens
   → guide user to log in again

Login SUCCESS after change
   → provider reads fresh UserDetails
   → PasswordEncoder verifies new hash
   → isCredentialsNonExpired() == true
   → full Authentication with valid authorities
```

Never invoke a password-change controller inside `AuthenticationSuccessHandler` to "auto-fix state." Flipping the credential-expired flag to false without changing the hash or without proof breaks expiration policy.

## 10. Session state, caching, and effect of changes

### 10.1. Expired flag is not re-checked on every request by default

In session-based login:

```text
Day 1: login succeeds → SecurityContext stored in session
Day 2: passwordExpiresAt has passed
Day 2: request reuses session → may still hold old Authentication
       without calling DaoAuthenticationProvider / UserDetailsService again
```

Therefore, if policy requires "after expiration, block all operations until changed," checking `isCredentialsNonExpired` **only at login** is insufficient. You need identity version checks, session expiration, policy filters/authorization, or session revocation as designed. Querying the DB on every request increases load; consider short-TTL caches, event-driven invalidation, or version checks.

### 10.2. UserDetails caches can hold stale flags

If `UserDetailsService` is cached, after a successful recovery you must evict the account's cache entry, or `isCredentialsNonExpired()` may still return false and the cached password hash remains the old one. Conversely, when an admin sets `must_change_password=true`, a stale cache may still return true and let another login bypass the policy.

By default, `ProviderManager` erases credentials on authentication results implementing `CredentialsContainer`. If both the cache and the principal hold the same `UserDetails` object, erasure can mutate the password hash in the cached instance, breaking the next login. Establish clear rules for **independent object snapshots, cache invalidation, and secret protection**; do not disable credential erasure as a default "fix."

### 10.3. APIs/tokens do not necessarily rely on UserDetails

A Spring Security OAuth2 Resource Server receiving a JWT typically verifies the signature, issuer, audience, `exp`, and configured claims, then builds a `JwtAuthenticationToken`. It **does not by default** read `password_changed_at` and `isCredentialsNonExpired` from the DB. If policy requires password resets to invalidate tokens, tie tokens to credential timestamps/versions or use controlled revocation/introspection.

Similarly, OIDC Login, SAML, passkeys/WebAuthn, and service API keys have their own credential lifecycles. Do not apply a 90-day password expiry rule to every credential type merely because all of them reside in the Authentication module.

## 11. Edge cases and testing rules

### Primary behavior matrix

| Condition | Expected outcome in `DaoAuthenticationProvider` flow | Additional checks needed |
| --- | --- | --- |
| Right password, unexpired | Authentication succeeds if other flags are valid | Authorities, principal, and credential erasure |
| Right password, `isCredentialsNonExpired=false` | `CredentialsExpiredException` | No new full authenticated session |
| Wrong password, unexpired credentials | `BadCredentialsException` | Do not disclose account existence |
| Wrong password, expired credentials | Authentication fails; exact exception depends on check mechanism | Do not grant recovery access |
| `mustChangePassword=true` and under 90 days | Credentials still considered expired if policy ORs both conditions | Do not ignore must-change flag |
| `now == expiresAt` | Expired if policy is expired-at-deadline | Test with `Clock.fixed(...)` |
| `now` one millisecond before deadline | Not yet expired | No timezone comparison bugs |
| `passwordExpiresAt=null` | Per project policy | Never guess null means any arbitrary state |
| Account disabled/locked | Rejected per account state | Do not let reset auto-unlock if policy forbids |
| Hash changed, forgot to clear must-change | Still cannot log in | Transactional multi-field update |
| Cleared must-change, forgot to change hash | May accept old credentials, violating policy | Verify invariants in service |
| Reused recovery token | Rejected | Atomic token consumption and replay prevention |
| Session existed before password expired | May stay authenticated via session | Test session revocation/revalidation |
| JWT issued before password change | May stay valid until `exp` without revocation | Define JWT policy |
| Stale `UserDetails` cache | May fail login or accept old flags | Cache eviction/versioning |

### Testing policy with Clock

A pure Java helper can be used to test boundary timestamps:

```java
static boolean credentialsExpired(
        Instant now,
        Instant expiresAt,
        boolean mustChange) {
    return mustChange
            || (expiresAt != null && !now.isBefore(expiresAt));
}
```

**Snippet inside a Java class**, not standalone runnable. Write unit tests for `now = expiresAt.minusNanos(1)` (false), `now = expiresAt` (true), `now = expiresAt.plusNanos(1)` (true), and `mustChange=true` (true even before deadline). Timezone testing validates how **`Instant` is constructed**, not how two `Instant`s are compared.

### Real integration tests

Write tests using the real manager/provider rather than only `@WithMockUser`:

1. `UserDetailsService` returns unexpired account, right password → authentication succeeds.
2. Account has expired credentials, right password → `CredentialsExpiredException` from manager; no success handler runs.
3. Account has expired credentials, wrong password → safe failure.
4. Wrong/expired/already-used recovery token → hash unchanged.
5. Valid recovery token → hash and flags/timestamps updated transactionally; token cannot be reused.
6. Old password fails after reset, new password succeeds.
7. For browsers, test missing CSRF token and replaying reset requests.
8. With an already-authenticated session, cross the expiry timestamp and change credentials; outcome matches revalidation policy.
9. With a restricted change session, verify every endpoint outside the allowlist is denied, even endpoints requiring only `authenticated()`.
10. If caching is enabled, test after eviction and after role/password state changes.

**`@WithMockUser` does not test password hashes, `isCredentialsNonExpired`, or `DaoAuthenticationProvider`.** It simulates an already-authenticated principal; great for authorization tests, but it does not replace authentication and recovery flow tests.

## 12. Common pitfalls

1. **Inverting boolean semantics:** DB has `credentialsExpired=true` and custom `isCredentialsNonExpired()` also returns true. You must invert when mapping.
2. **Failing to override custom getter:** DB policy holds expiry data yet `UserDetails` returns default true.
3. **Assuming a false flag automatically opens a password-change screen:** the provider throws an exception; recovery requires its own flow and UI.
4. **Handling expiration inside the success handler:** the success handler never receives requests rejected by `CredentialsExpiredException`.
5. **Redirecting to a reset page and treating username as verified:** a redirect grants neither authentication nor proof of ownership.
6. **Building a recovery endpoint taking only user ID + new password:** without proof, this opens an account-takeover path.
7. **Using restricted `Authentication` but forgetting endpoints guarded by `authenticated()`:** the principal can slip past overly broad rules.
8. **Clearing `must_change_password=false` without changing the hash:** violates forced credential-rotation policy.
9. **Changing the hash without updating timestamp/flag:** the account remains treated as expired and the user cannot log in.
10. **Failing to invalidate cache/`UserDetails`:** the account can retain stale status and old password hash.
11. **Believing changing a password revokes sessions/JWTs on every device:** sessions/tokens require dedicated revocation/version/TTL mechanisms.
12. **Storing new passwords in plaintext or logging raw credentials:** always use a dedicated password encoder and keep secrets out of logs.
13. **Using profile `updated_at` as the password-change date:** changing an avatar or email accidentally extends credential lifetime.
14. **Setting expiry in client timezones:** the same credential can look valid or expired inconsistently; standardize on UTC/`Instant` and explicit policy.
15. **Confusing password expiration with JWT expiration:** `isCredentialsNonExpired` does not check `exp` claims.
16. **Mixing locked/disabled with expired:** resetting a password must not bypass lock or disable policies.
17. **Returning detailed messages before sufficient verification:** can enable enumeration/account-status probing.
18. **Disabling CSRF across all login/recovery forms for "easy submission":** design state-changing request protection matching the credential model.
19. **Keeping the old raw password in the session to change later:** unnecessary and unsafe to retain secrets that way; verify and discard.
20. **Setting an expired flag only in the frontend without backend checks:** the UI is not a security boundary; providers/policies/services decide.

## 13. Practice exercises

**Exercise 1 — Understand the getter.** Explain when `isCredentialsNonExpired()` returns true/false; compare with `isAccountNonExpired()` and `isAccountNonLocked()`. Predict the exception for a right password with expired credentials.

**Exercise 2 — Run the demo.** Build the Gradle project in Section 6, run `gradle run`, and explain all four output lines: expired, wrong password, old password after reset, and new password succeeding. Change dates/lifetimes to observe the changes.

**Exercise 3 — Write a policy.** Build a `PasswordExpiryPolicy` using an injected `Clock`, with nullable `passwordExpiresAt` and `mustChangePassword`. Test right at the expiration instant and one nanosecond prior.

**Exercise 4 — DB mapping.** Add `password_hash`, `password_changed_at`, `must_change_password`, and optional `security_version` to accounts. Write a `UserDetailsService` returning `User.withUsername(...).credentialsExpired(...)` without re-encoding existing hashes.

**Exercise 5 — Choose a flow.** Compare a separate recovery token against a restricted change session. For each flow, specify required proof, allowed endpoints, token/challenge expiry conditions, session cleanup, and where users are blocked from normal APIs.

**Exercise 6 — Security tests.** Write tests proving `AuthenticationFailureHandler` receives `CredentialsExpiredException`; calling sensitive endpoints after failure must be denied. Test wrong, expired, replayed, and concurrent reset tokens.

**Exercise 7 — Sessions/tokens.** Log in before expiration, then flip the expired flag in the DB. Explain why the user might still call APIs with an old session and propose an appropriate revalidation/credential-version mechanism.

**Exercise 8 — Incident.** An admin sets `must_change_password=true` on 100 accounts due to potential exposure. Write a safe plan covering notification, challenges, rate limits, auditing, cache invalidation, session revocation, and rollback. Do not distribute a shared temporary password.

### Completion criteria

Learners should be able to answer on their own:

- What does `isCredentialsNonExpired()` mean and why does builder `credentialsExpired(true)` make the getter false?
- When the password is right but the expired flag is set, does `DaoAuthenticationProvider` succeed or which error does it throw?
- Why can an `AuthenticationFailureHandler` guide UX yet not verify an account for a reset?
- How do you design recovery tokens or limited access without granting application permissions prior to changing the password?
- When updating a password, which fields must be updated consistently?
- Why can sessions, JWTs, and `UserDetails` caches retain stale state?
- What must be tested so a "forced password change" policy does not turn into an authentication bypass?

## 14. Official documentation

- [Spring Security 6.5.11 — UserDetails API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetails.html): `isCredentialsNonExpired()` contract and account flags.
- [Spring Security 6.5.11 — User.UserBuilder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/User.UserBuilder.html): `credentialsExpired(boolean)` and builder flags.
- [Spring Security 6.5.11 — AbstractUserDetailsAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html): pre/post authentication checks and user configuration.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): using `UserDetailsService` and `PasswordEncoder`.
- [Spring Security 6.5 — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationManager`, `ProviderManager`, and authentication state handling.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): password hashing, encoders, and hash upgrades.
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): filters, success/failure handlers, and defining login pages.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): security context, sessions, and lifecycle control.
- [Spring Security — UserDetails Caching](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/caching.html): principal caching and credential erasure.

**Version note:** the runnable example uses Spring Security Core 6.5.11/Java 17. When applications use Spring Boot 3.5, Spring Security 7, custom providers, JWT/OIDC, or WebFlux, verify the exact API/flow of the corresponding version. In particular, never mechanically tie `UserDetails` password expiration policy to token expiration or non-password authentication.