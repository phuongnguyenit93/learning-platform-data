# Testing Password Upgrades and Post-Authentication Data Updates in Spring Security

## 1. Lesson Objectives

In a system that has operated for many years, passwords may be stored using different algorithms or configurations: an older bcrypt cost, PBKDF2 with older parameters, or a legacy format approved for migration. When a user **logs in successfully**, the application can take advantage of the valid password the user just entered to **re-encode it under the new policy** (*opportunistic password rehash / upgrade on login*), then save the new hash without forcing an across-the-board password reset.

This lesson addresses **two related yet distinct testing scopes**:

1. **Upgrading password encoding after valid authentication**: `PasswordEncoder.matches` must verify the credential; `upgradeEncoding` decides whether the hash needs upgrading; `UserDetailsPasswordService.updatePassword` persists the **encoded hash**, never the raw password.
2. **Updating data after authentication success**: recording `lastSuccessfulLoginAt`, login audit events, device/session state, or last-login timestamps; never recording a **success** event when authentication fails. Transaction management, idempotency, and write-failure handling are required.

The focus is **component testing**: verifying the right objects, invocations, hash values, ordering, post-authentication data, and negative branches. Distinguish `DaoAuthenticationProvider` unit tests, DB integration tests, and real login tests through Servlet filters.

Spring API examples use **Spring Security 6.5 / Spring Boot 3.x / Java 17+**. Tests containing mocked dependencies must run in a Spring project with JUnit 5, Mockito, and Spring Security. The plain Java section at the end runs directly with JDK 17.

## 2. Why Is Rehashing Different from Changing a Password?

An application changing its password storage policy from "bcrypt cost 10" to "bcrypt cost 12" does not know everyone's raw passwords. It stores only a one-way function, so it **cannot decrypt an old hash to compute a new hash**. When a user logs in with a valid password, the application temporarily has the raw credential in memory and can:

```text
POST /login
  -> UsernamePasswordAuthenticationFilter
  -> AuthenticationManager / ProviderManager
  -> DaoAuthenticationProvider
       -> UserDetailsService.loadUserByUsername()
       -> account flags: enabled, nonLocked, nonExpired
       -> PasswordEncoder.matches(raw, storedHash)
          | false -> BadCredentialsException, DO NOT write rehash
          | true
       -> check credentials nonExpired
       -> optional compromised-password check
       -> if UserDetailsPasswordService is present:
            PasswordEncoder.upgradeEncoding(storedHash)?
               | false -> keep old hash
               | true:
                    PasswordEncoder.encode(raw)
                    UserDetailsPasswordService.updatePassword(user, newHash)
       -> Authenticated Authentication (if all steps succeed)
  -> Spring Security authentication-success flow
       -> session/context handling, remember-me, events, success handler
  -> application audit/lastLoginAt policy
```

**Rehashing is not a user password change**: the logical login password remains the same; only the cryptographic representation and storage parameters change. Do not automatically send a "password changed" email or revoke all sessions solely due to a rehash unless organizational policy requires it.

**An actual password change** (the user provides a new password after appropriate verification) is a separate business flow: it must verify the current password/step-up auth, enforce password policy, update the hash, and revoke sessions/tokens per policy. Both can use `PasswordEncoder.encode`, yet their semantics and tests differ.

## 3. API Contracts You Must Know

| API | Responsibility | Where is the main assertion? |
| --- | --- | --- |
| `UserDetailsService.loadUserByUsername` | Reads account and stored encoded password | Reads the right user; never creates a new user on wrong username |
| `PasswordEncoder.matches(raw, encoded)` | Verifies submitted password against old hash | Wrong password = false; no rehash or success audit |
| `PasswordEncoder.upgradeEncoding(encoded)` | Decides whether the **existing hash** needs re-encoding | Old hash = true; current hash = false per policy |
| `PasswordEncoder.encode(raw)` | Generates a hash under the new encoder policy | Result is not raw; matches raw |
| `UserDetailsPasswordService.updatePassword(user, newEncoded)` | Persists the new encoded hash to durable storage | Called only on auth success **and** upgrade needed; DB data actually changes |
| `DaoAuthenticationProvider` | Coordinates password verification + upgrade if configured | Auth success/failure and exact update invocation branch |
| `AuthenticationSuccessHandler` | Success hook for the corresponding login filter flow | Runs only after authentication succeeds in that flow |
| `AuthenticationFailureHandler` | Failure hook for the login filter flow | Does not write lastSuccess/update success data |
| `AuthenticationSuccessEvent` | Success event from authentication infrastructure when an event publisher is configured | Appropriate listener, without double-counting interactive events |
| `InteractiveAuthenticationSuccessEvent` | Interactive authentication event emitted by login filters | Use when measuring interactive logins; do not assume it covers every authentication |

**Detail from Spring Security 6.5:** `DaoAuthenticationProvider` checks `userDetailsPasswordService != null` before calling `upgradeEncoding`. Without configuring a `UserDetailsPasswordService` on the active provider, **merely declaring a stronger encoder does not guarantee hashes automatically update**. Do not rely on a bean merely existing in `ApplicationContext` without verifying the provider is actually wired to it.

### UserDetailsPasswordService receives an already-encoded value

Signature:

```java
// Contract API, not a standalone Java file
public interface UserDetailsPasswordService {
    UserDetails updatePassword(UserDetails user, String newPassword);
}
```

The parameter name `newPassword` might lead readers to think it is a raw password, but **the contract requires this to be the encoded value** produced by `PasswordEncoder.encode`. Implementations must store it verbatim per schema and never call `encode` a second time, avoiding double-encoding.

The method must return the **updated `UserDetails`**; never return null or another account's `UserDetails`. Note that when `UserDetails` is a custom principal with extra fields/roles/tenant, the implementation must preserve those critical fields.

### Do not assume the Authentication principal was refreshed

In Spring Security 6.5's internal processing path, `AbstractUserDetailsAuthenticationProvider` prepares `principalToReturn` from the initial `UserDetails` and passes it into `createSuccessAuthentication`. `DaoAuthenticationProvider` may call `updatePassword` and use the updated `UserDetails` for **authorities**, yet the original principal is not necessarily replaced by the exact object returned from `updatePassword`.

Therefore, **rehash tests must re-read the repository and verify updater calls**, instead of merely checking whether `((UserDetails) authentication.getPrincipal()).getPassword()` equals the new hash. Never write the principal's old hash back to the DB after login. This is a special trap when sessions/caches hold stale `UserDetails`.

## 4. PasswordEncoder and Storage Formats

Spring Security recommends adaptive one-way password hashing and `DelegatingPasswordEncoder` to manage multiple formats:

```text
{bcrypt}$2a$10$...
{pbkdf2@SpringSecurity_v5_8}...
{scrypt@SpringSecurity_v5_8}...
{argon2@SpringSecurity_v5_8}...
```

The `{id}` prefix selects the verification implementation. Typically:

```java
PasswordEncoder encoder =
        PasswordEncoderFactories.createDelegatingPasswordEncoder();

boolean valid = encoder.matches(rawPassword, storedEncodedPassword);
boolean shouldRehash = encoder.upgradeEncoding(storedEncodedPassword);
String newEncoded = encoder.encode(rawPassword);
```

This is a **snippet** for a class that has imported `org.springframework.security.crypto.factory.PasswordEncoderFactories` and `org.springframework.security.crypto.password.PasswordEncoder`. The current default should be verified against your **actual version** rather than hardcoding an ID assumption forever.

`DelegatingPasswordEncoder` supports verifying explicitly configured legacy formats, but it **never guesses** the algorithm when a hash lacks a prefix. Hashes without an ID or with an unmapped ID can throw `IllegalArgumentException`; migrate in a controlled manner rather than enabling `NoOpPasswordEncoder` across production.

### UpgradeEncoding may not mean a "different id"

- Changing IDs such as `{pbkdf2}` to `{bcrypt}` can cause `DelegatingPasswordEncoder.upgradeEncoding` to request a rehash.
- **Same ID** with too-weak parameters (e.g., a bcrypt cost lower than current policy) can also require an upgrade if the encoder implementation supports checking it.
- The default `PasswordEncoder.upgradeEncoding` method returns **false** if the implementation does not override it. For custom encoders, implement this policy explicitly and test it.

Real test example using `BCryptPasswordEncoder`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import static org.junit.jupiter.api.Assertions.*;

class BCryptUpgradePolicyTest {
    @Test
    void oldCostIsUpgradableAndNewCostIsNot() {
        // Cost 5/6 ONLY for fast unit tests, do not use in production.
        var old = new BCryptPasswordEncoder(5);
        var current = new BCryptPasswordEncoder(6);

        String oldHash = old.encode("correct-horse");
        assertTrue(current.matches("correct-horse", oldHash));
        assertTrue(current.upgradeEncoding(oldHash));

        String newHash = current.encode("correct-horse");
        assertNotEquals("correct-horse", newHash);
        assertTrue(current.matches("correct-horse", newHash));
        assertFalse(current.matches("wrong", newHash));
        assertFalse(current.upgradeEncoding(newHash));
    }
}
```

Real work-factor settings should be benchmarked on production hardware and meet security policy. Never copy cost 5/6 from tests into real applications.

## 5. Branch Test Matrix Required

| Case | Authentication | Re-encode? | Call updater? | Success audit? |
| --- | --- | --- | --- | --- |
| Right password, legacy hash, updater configured | Succeeds | **Yes** | **Once** | Per success flow |
| Right password, hash already meets policy | Succeeds | **No** | **No** | Yes |
| Wrong password, legacy hash | Fails | **No** | **No** | **No** |
| User does not exist | Fails | No | No | No |
| Account disabled/locked/expired | Fails | No | No | No |
| Credential expired or compromised per policy | Fails per mechanism | No | No | No |
| Right password, legacy but no updater | Succeeds with old hash | **No rehash via provider** | No | Yes |
| Right password, legacy but DB update fails | Handles failure per provider/DB policy | May have computed new hash | Called, not committed | Must not emit false success |
| Two logins with same password while legacy | Both may be valid per policy | May compute multiple times | **Only one write wins CAS** | Records accurate login count |
| User resets password concurrently with rehash | Depends on order and policy | Must not overwrite new password hash | CAS/version required | Must not succeed on stale credential |
| Next login after rehash | Succeeds | No | No | Each successful login has its own audit |
| Event/handler retry | Does not alter authentication result | No repeated hash changes | No repeated unwanted mutations | Idempotent by event ID |

**A test checking only `auth.isAuthenticated() == true` is insufficient.** It does not prove the DB updated, the value was encoded, or failure paths refrained from writing success data.

## 6. Direct Unit Tests on DaoAuthenticationProvider with Mockito/JUnit 5

This is a standalone test class **inside a project with Spring Security and Mockito dependencies**, not a plain Java SE program run with `javac`. It calls `DaoAuthenticationProvider.authenticate(...)` directly without `MockMvc` to eliminate HTTP/session noise.

Dependencies in a Spring Boot 3.x app with a properly versioned Gradle plugin:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

In a standard **Spring Boot test starter** project, JUnit 5/Mockito are already included; ensure the test runtime matches the Spring Security 6.x version in use.

Create **`src/test/java/demo/auth/PasswordUpgradeProviderTest.java`**:

```java
package demo.auth;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsPasswordService;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class PasswordUpgradeProviderTest {

    private static UserDetails userWithHash(String hash) {
        return User.withUsername("alice")
                .password(hash)
                .roles("USER")
                .build();
    }

    private static DaoAuthenticationProvider provider(
            UserDetailsService loader,
            PasswordEncoder encoder,
            UserDetailsPasswordService updater) {

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(loader);
        provider.setPasswordEncoder(encoder);
        provider.setUserDetailsPasswordService(updater);
        return provider;
    }

    private static UsernamePasswordAuthenticationToken attempt(String password) {
        return UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", password);
    }

    @Test
    void successfulLegacyLoginRehashesAndPersistsNewEncodedPassword() {
        UserDetails oldUser = userWithHash("{old}hash");
        UserDetails updatedUser = userWithHash("{new}hash");

        UserDetailsService loader = mock(UserDetailsService.class);
        PasswordEncoder encoder = mock(PasswordEncoder.class);
        UserDetailsPasswordService updater = mock(UserDetailsPasswordService.class);

        when(loader.loadUserByUsername("alice")).thenReturn(oldUser);
        when(encoder.matches("correct", "{old}hash")).thenReturn(true);
        when(encoder.upgradeEncoding("{old}hash")).thenReturn(true);
        when(encoder.encode("correct")).thenReturn("{new}hash");
        when(updater.updatePassword(oldUser, "{new}hash"))
                .thenReturn(updatedUser);

        DaoAuthenticationProvider provider =
                provider(loader, encoder, updater);
        Authentication result = provider.authenticate(attempt("correct"));

        assertNotNull(result);
        assertTrue(result.isAuthenticated());
        assertEquals("alice", result.getName());

        verify(encoder).matches("correct", "{old}hash");
        verify(encoder).upgradeEncoding("{old}hash");
        verify(encoder).encode("correct");
        verify(updater, times(1)).updatePassword(oldUser, "{new}hash");
        // Do not assert principal.getPassword() is the new hash;
        // check the repository in an integration test.
    }

    @Test
    void successfulLoginWithCurrentHashMustNotWrite() {
        UserDetails currentUser = userWithHash("{new}hash");
        UserDetailsService loader = mock(UserDetailsService.class);
        PasswordEncoder encoder = mock(PasswordEncoder.class);
        UserDetailsPasswordService updater = mock(UserDetailsPasswordService.class);

        when(loader.loadUserByUsername("alice")).thenReturn(currentUser);
        when(encoder.matches("correct", "{new}hash")).thenReturn(true);
        when(encoder.upgradeEncoding("{new}hash")).thenReturn(false);

        Authentication result = provider(loader, encoder, updater)
                .authenticate(attempt("correct"));

        assertTrue(result.isAuthenticated());
        verify(encoder).upgradeEncoding("{new}hash");
        verify(updater, never()).updatePassword(any(), anyString());
    }

    @Test
    void badPasswordNeverUpdatesHash() {
        UserDetails oldUser = userWithHash("{old}hash");
        UserDetailsService loader = mock(UserDetailsService.class);
        PasswordEncoder encoder = mock(PasswordEncoder.class);
        UserDetailsPasswordService updater = mock(UserDetailsPasswordService.class);

        when(loader.loadUserByUsername("alice")).thenReturn(oldUser);
        when(encoder.matches("wrong", "{old}hash")).thenReturn(false);

        assertThrows(BadCredentialsException.class,
                () -> provider(loader, encoder, updater)
                        .authenticate(attempt("wrong")));

        verify(encoder, never()).upgradeEncoding(anyString());
        verify(updater, never()).updatePassword(any(), anyString());
    }

    @Test
    void noConfiguredPasswordServiceMeansNoAutomaticUpgrade() {
        UserDetails oldUser = userWithHash("{old}hash");
        UserDetailsService loader = mock(UserDetailsService.class);
        PasswordEncoder encoder = mock(PasswordEncoder.class);

        when(loader.loadUserByUsername("alice")).thenReturn(oldUser);
        when(encoder.matches("correct", "{old}hash")).thenReturn(true);

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(loader);
        provider.setPasswordEncoder(encoder);
        // INTENTIONALLY omitted setUserDetailsPasswordService

        Authentication result = provider.authenticate(attempt("correct"));
        assertTrue(result.isAuthenticated());
        verify(encoder, never()).upgradeEncoding(anyString());
        verify(encoder, never()).encode("correct");
    }

    @Test
    void failedPersistenceMustNotReportSuccessfulAuthentication() {
        UserDetails oldUser = userWithHash("{old}hash");
        UserDetailsService loader = mock(UserDetailsService.class);
        PasswordEncoder encoder = mock(PasswordEncoder.class);
        UserDetailsPasswordService updater = mock(UserDetailsPasswordService.class);

        when(loader.loadUserByUsername("alice")).thenReturn(oldUser);
        when(encoder.matches("correct", "{old}hash")).thenReturn(true);
        when(encoder.upgradeEncoding("{old}hash")).thenReturn(true);
        when(encoder.encode("correct")).thenReturn("{new}hash");
        when(updater.updatePassword(oldUser, "{new}hash"))
                .thenThrow(new IllegalStateException("DB write failed"));

        assertThrows(IllegalStateException.class,
                () -> provider(loader, encoder, updater)
                        .authenticate(attempt("correct")));
        verify(updater, times(1)).updatePassword(oldUser, "{new}hash");
    }
}
```

Run (from the Gradle-configured project):

```bash
./gradlew test --tests demo.auth.PasswordUpgradeProviderTest
```

**Expectation:** 5 tests PASS with compatible Spring Security 6.5 and Mockito/JUnit. The `verify(...)` calls check **branch invocations**; to prove the DB committed, you must run the real datastore integration tests in the later section.

### Why not use @WithMockUser to test rehashing?

`@WithMockUser` supplies a pre-authenticated `SecurityContext`, bypassing the login filter and `DaoAuthenticationProvider`. It is great for controller authorization tests, yet **it does not trigger `matches`, `upgradeEncoding`, or `updatePassword`**.

Similarly, `SecurityMockMvcRequestPostProcessors.user(...)` injects a mock principal for request tests, **not** credential-verification tests. For this lesson's goals, you must invoke the real provider or go through the real HTTP login filter.

## 7. Production Service: Persisting Only Encoded Hashes and Protecting Concurrency

A `UserDetailsPasswordService` implementation using JDBC can update the hash conditionally on the previous value (*compare-and-set*):

```java
package demo.auth;

import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsPasswordService;

public final class JdbcPasswordUpgradeService
        implements UserDetailsPasswordService {

    private final JdbcOperations jdbc;

    public JdbcPasswordUpgradeService(JdbcOperations jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public UserDetails updatePassword(UserDetails oldUser, String newHash) {
        // SQL illustrates app_users(username,password_hash,...) schema.
        // newHash was already generated by PasswordEncoder.encode(...); do not hash a second time.
        int changed = jdbc.update("""
                UPDATE app_users
                   SET password_hash = ?
                 WHERE username = ?
                   AND password_hash = ?
                """,
                newHash, oldUser.getUsername(), oldUser.getPassword());

        if (changed != 1) {
            // Do not overwrite another ongoing password reset/upgrade.
            // Reject or retry the ENTIRE authentication from the latest credential.
            throw new AuthenticationServiceException(
                    "Credential changed during upgrade");
        }

        // Only suitable when user is a standard Spring Security User.
        return User.withUserDetails(oldUser)
                .password(newHash)
                .build();
    }
}
```

The above is a Java class that compiles with `spring-jdbc` and Spring Security, yet **is not a self-running app** because it needs a real `DataSource`/schema. Use an immutable `accountId` instead of a mutable username if the system allows username changes. If custom `UserDetails` carries tenant/account metadata, construct a copy preserving all fields; `User.withUserDetails(...)` does not automatically copy domain-specific fields.

### Why does WHERE need the old password hash or version?

```text
T0: current hash = H1 (legacy)
A: logs in with old password; verified against H1
B: user resets password to H2 (DIFFERENT password)
A: writes H3 = encode(old password) without checking current state

If UPDATE only uses WHERE username = alice:
    A overwrites H2 with H3 -> just-completed password reset is reverted!

If UPDATE ... WHERE password_hash = H1:
    B already committed H2 -> A updates 0 rows -> cannot overwrite.
```

CAS can rely on the old `password_hash` or `credential_version`. When two valid logins using the same hash H1 both attempt to upgrade, both may compute H3/H4 with different salts, yet **only one request** succeeds in writing; the other sees 0 rows. A clear concurrency-handling policy is required:

- **Fail closed + ask to retry** is simple and avoids accidentally authenticating with a changed password.
- Alternatively, the application can **re-authenticate against the new credential version** at a sufficiently trusted layer; this requires the valid raw password, retry limits, and DoS protection. `UserDetailsPasswordService.updatePassword` receives only the new hash, not the raw password to re-verify on its own.
- Never treat every CAS miss as "just continue logging in" and never accept success with an old password right after a user reset.

**JDBC writes must have real transaction/rollback tests**, not just mocking `JdbcOperations.update(...)` and concluding persistence works. If using JPA/repositories, verify optimistic locking (`@Version`) or conditional updates against the current record.

### Explicit provider configuration for Spring Security 6.5

```java
// Configuration fragment inside Spring Boot 3.x @Configuration:
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}

@Bean
UserDetailsPasswordService passwordUpgradeService(JdbcOperations jdbc) {
    return new JdbcPasswordUpgradeService(jdbc);
}

@Bean
DaoAuthenticationProvider daoProvider(
        UserDetailsService users,
        PasswordEncoder encoder,
        UserDetailsPasswordService upgrades) {

    DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
    provider.setPasswordEncoder(encoder);
    provider.setUserDetailsPasswordService(upgrades);
    return provider;
}
```

Required imports: `org.springframework.context.annotation.Bean`, `org.springframework.jdbc.core.JdbcOperations`, `org.springframework.security.crypto.password.PasswordEncoder`, `org.springframework.security.crypto.factory.PasswordEncoderFactories`, `org.springframework.security.core.userdetails.UserDetailsService`, `org.springframework.security.core.userdetails.UserDetailsPasswordService`, `org.springframework.security.authentication.dao.DaoAuthenticationProvider`.

This is **component configuration**; whether this provider bean is actually used by `AuthenticationManager` depends on how your security chain and Boot auto-configuration are wired. Integration tests must **verify the right `ProviderManager`/`DaoAuthenticationProvider` is invoked**, not merely assert the bean exists.

## 8. DB Integration Testing: Do Not Stop at Mockito

Mockito can prove `updatePassword` was called, yet it does not prove:

- the SQL updates the right account and right column;
- the data actually commits;
- concurrency-safe CAS works;
- the new hash has the right prefix/ID/parameters;
- cached `UserDetails` and principals/authorities do not become stale or broken;
- the next login reads back the new hash and does not rehash infinitely.

An integration test using Testcontainers PostgreSQL or an equivalent test database should:

1. Seed `app_users` with user `alice`, `password_hash = legacyHash`, account enabled.
2. Use the real `PasswordEncoder` with current policy and real `UserDetailsService`.
3. Run `AuthenticationManager.authenticate(UsernamePasswordAuthenticationToken.unauthenticated(...))` through the **genuinely wired** provider.
4. Read the DB via JDBC/repository to compare `password_hash` before and after.
5. Assert `encoder.matches(raw, newHash) == true`, `upgradeEncoding(newHash) == false`, and that the new hash differs from the old hash.
6. Authenticate again with the same raw password; assert no additional password-update SQL runs.
7. Test wrong password, disabled account, locked account, and expired credentials: DB hash remains unchanged.
8. Issue two concurrent requests against the **same DB**, ensuring password resets are not overwritten and CAS policies hold.
9. If sessions/caches are used, invalidate or refresh related data properly.

Pseudocode example **illustrating integration logic**, not pretending to be a standalone test class:

```java
String oldHash = repository.findPasswordHash("alice");

Authentication auth = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "correct-password"));

assertTrue(auth.isAuthenticated());

String storedAfter = repository.findPasswordHash("alice");
assertNotEquals(oldHash, storedAfter);
assertTrue(passwordEncoder.matches("correct-password", storedAfter));
assertFalse(passwordEncoder.upgradeEncoding(storedAfter));

// Log in again; DB password_hash does not change.
authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "correct-password"));
assertEquals(storedAfter, repository.findPasswordHash("alice"));
```

`repository.findPasswordHash` is an **application abstraction** that must be implemented and injected. With randomized-salt adaptive encoders, **never compare a hash against a fixed string literal**; verify via `matches` and policy parameters. Each encode of the same password typically produces a different string.

### Checking SQL with independent transactions

A test running all steps inside a single auto-rolled-back test transaction can mask **commit**, isolation, and post-commit event/outbox issues. For production behavior, include at least one non-rolling-back test, or run two-connection/two-transaction assertions with reliable fixture cleanup. Test CAS on real PostgreSQL rather than relying on H2's concurrency semantics when production runs PostgreSQL.

## 9. Updating Data After Authentication Success Is a Separate Business Concern

Fields commonly updated when a user logs in:

| Field/behavior | When to update? | Notes |
| --- | --- | --- |
| `lastSuccessfulLoginAt` | After authentication succeeds for the chosen login type | Use server/DB clock; never put inside `loadUserByUsername` |
| `loginSuccessCount` | Per policy for each successful login event | Avoid double-counting from both handler and listener writing |
| `lastLoginIp`, `lastUserAgent` | If needed for audit/risk signals | IP from trusted proxy; minimize PII and retention |
| `failureCount`, `lockedUntil` | **After failure**, per lockout policy | Do not treat this as successful login data |
| `passwordHash` and current algorithm | During valid authentication, if `upgradeEncoding` is true | Write encoded value with CAS |
| `securityAuditEvent` | Success/failure per event type | Include correlation ID, never passwords/hashes |
| `sessionId` / session registry | After login success/rotation | Spring Security + Session management, never trust client-supplied session IDs |
| `lastAuthenticatedFactor` | After real factor verification | Never rely on client-sent `mfa=true` headers |

**Rule:** post-authentication data must reflect an event that genuinely occurred, never client-asserted claims or merely loading a user record.

### Wrong places to update

Never write `lastLoginAt = now` inside `UserDetailsService.loadUserByUsername` because that method can be called when:

- the user enters the **wrong password**;
- the password encoder needs a user record to verify against;
- a service/admin action looks up the user;
- a cache miss, re-authentication, or other lookup occurs.

Similarly, never update login success inside `PasswordEncoder.matches`. An encoder must only handle password comparison/upgrade checks, without DB audit side effects.

## 10. AuthenticationSuccessHandler for Form Login

For Servlet form login, `AuthenticationSuccessHandler` is the hook near the end of the flow after successful authentication. Configuration example **exclusively for browser form login**:

```java
// Fragment inside @Configuration, using Spring Security 6.x Servlet.
@Bean
AuthenticationSuccessHandler auditedSuccessHandler(
        LoginAuditService auditService) {

    var delegate = new SavedRequestAwareAuthenticationSuccessHandler();

    return (request, response, authentication) -> {
        auditService.recordSuccessfulLogin(
                authentication.getName(),
                java.time.Instant.now(),
                request.getRemoteAddr());
        delegate.onAuthenticationSuccess(request, response, authentication);
    };
}

// When building SecurityFilterChain:
http.formLogin(form -> form
        .successHandler(auditedSuccessHandler(auditService)));
```

Required imports: `org.springframework.security.web.authentication.AuthenticationSuccessHandler`, `org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler`, and `org.springframework.context.annotation.Bean`. `LoginAuditService` is an **application-defined service**, not a built-in Spring Security API.

This snippet is **not standalone**: it needs the session/security chain and service implementation. `getRemoteAddr()` may be the reverse proxy's IP; use only forwarded headers normalized/trusted by the edge to determine client IP, and consider not storing IPs unless needed.

If the audit service fails, you must decide explicitly:

- **Audit mandatory to complete login**: manage consistency/transactions and fail per policy, avoiding leaving a session created while the UI reports an unclear failure.
- **Audit best-effort**: use a durable event/outbox with bounded monitoring/retries, without blocking the event loop/request when analytics fails. Never silently swallow security errors that require alerts.

The form-login `AuthenticationSuccessHandler` hook does not necessarily run for **HTTP Basic**, **JWT resource servers**, or **custom `AuthenticationManager.authenticate(...)`** calls from services. To track multiple mechanisms, wire events and hooks from the exact sources.

## 11. AuthenticationSuccessEvent and InteractiveAuthenticationSuccessEvent

Spring Security emits authentication events when a suitable publisher is configured. Example:

```java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher publisher) {
    return new DefaultAuthenticationEventPublisher(publisher);
}
```

Imports: `org.springframework.security.authentication.AuthenticationEventPublisher`, `org.springframework.security.authentication.DefaultAuthenticationEventPublisher`, and `org.springframework.context.ApplicationEventPublisher`.

Then you can listen:

```java
@Component
class LoginAuditListener {
    private final LoginAuditService audit;

    LoginAuditListener(LoginAuditService audit) {
        this.audit = audit;
    }

    @EventListener
    void onSuccess(AuthenticationSuccessEvent event) {
        Authentication auth = event.getAuthentication();
        audit.recordProviderSuccess(auth.getName());
    }
}
```

Imports: `org.springframework.stereotype.Component`, `org.springframework.context.event.EventListener`, `org.springframework.security.authentication.event.AuthenticationSuccessEvent`, `org.springframework.security.core.Authentication`.

**Warning about double counting**:

- `AuthenticationSuccessEvent` is emitted by the authentication infrastructure per configuration; some flows or code paths can authenticate multiple times.
- `InteractiveAuthenticationSuccessEvent` is emitted by interactive filters at a different stage; not every mechanism emits this event.
- Attaching listeners to both events and a success handler while incrementing `loginCount` in all of them can double- or triple-count.
- A provider success event does not necessarily mean a **browser session was persisted successfully**; distinguish credential success from interactive session success.
- `@EventListener` does not guarantee exactly-once delivery across processes. For critical audits, use durable events/outbox and idempotency keys.

**Note:** calling `DaoAuthenticationProvider.authenticate(...)` directly in a unit test does not include `ProviderManager`, a publisher, or form filters by default; therefore, event/handler tests belong at the appropriate integration layer.

## 12. Designing Tests for Updating lastLoginAt and Audits

Two important kinds of tests:

**A. Component unit tests for post-authentication updates**

Mock `LoginAuditService` and invoke the handler/listener with a valid mock `Authentication`; assert the service received the right user/timestamp. For handlers, delegating redirects/cookies/sessions needs Spring Mock requests/responses, and Mockito can verify exact invocations.

**B. Login filter integration tests**

Use `MockMvc` with a real Spring Security filter chain and real user store or test DB:

```java
// Test fragment in @SpringBootTest + @AutoConfigureMockMvc,
// requires injecting MockMvc, repository, and real form login config.
mvc.perform(post("/login")
            .param("username", "alice")
            .param("password", "correct-password")
            .with(csrf()))
        .andExpect(status().is3xxRedirection());

// After request, read DB via JDBC (not a mock):
assertEquals(1, repository.countSuccessfulLogins("alice"));
assertNotNull(repository.findLastSuccessfulLoginAt("alice"));
```

Imports: `org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post`, `org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf`, `org.springframework.test.web.servlet.result.MockMvcResultMatchers.status`, `org.junit.jupiter.api.Assertions.*`. `repository` is an application fixture, not built into Spring.

Test failure:

```java
mvc.perform(post("/login")
            .param("username", "alice")
            .param("password", "wrong")
            .with(csrf()))
        .andExpect(status().is3xxRedirection());

assertEquals(1, repository.countSuccessfulLogins("alice"));
// Count remains unchanged after failure; failure counter has its own policy.
```

With default form login, failures usually redirect to `/login?error`; if an app customizes its failure handler to return JSON 401, adjust assertions accordingly. Do not rely on status 302 alone: both success and failure **can redirect**. Assert `Location`/session state and the DB.

### Testing no updates for a disabled user

Set `enabled=false`, submit login with the right password, and assert:

- Authentication is rejected (typically via failure handler).
- Password hash is unchanged, even if legacy.
- No new `lastSuccessfulLoginAt` or success event.
- Failure audit/lockout counters may update per policy, never success data.

### Testing no updates after wrong password

Compare **before/after DB snapshots**, rather than relying only on `verifyNoInteractions` with mocks. A bug updating `lastLoginAt` inside `loadUserByUsername` will slip past service unit tests yet be caught by this integration test.

## 13. Transactions and Consistency Across Multiple Updates

There can be **two groups of side effects** at two different points:

```text
A. Inside DaoAuthenticationProvider:
    - password match
    - conditional rehash + persist
    - create successful Authentication

B. After Authentication succeeds in the web flow:
    - session rotation / SecurityContext persistence
    - login audit, lastLoginAt, device tracking
    - redirect or JSON response
```

Do not assume all operations above occur in **one single DB transaction**. `DaoAuthenticationProvider` is a synchronous authentication component; success handlers/event listeners and session stores can have different lifecycles, transactions, and storage systems.

### Isolating failures

- **Password update fails:** never silently treat it as upgraded; depending on policy, fail the login or safely retry authentication. Never ignore a CAS miss and overwrite.
- **Login audit fails:** distinguish mandatory vs best-effort audit requirements; never write a `"LOGIN_SUCCESS"` row when credentials were actually invalid.
- **Session creation fails after auth:** provider success differs from browser login success; if the client retries, prevent duplicate side effects.
- **Post-login event delivered repeatedly:** every consumer needs idempotency/correlation; never increment login counts multiple times for one login event.
- **DB timeout after server commit:** the response may look like a network error even though state changed; use idempotent event keys and re-verify state on retry.

### Monotonic audit timestamps

If two logins on two nodes finish at different speeds, a naive update can move `lastSuccessfulLoginAt` backward in time. PostgreSQL example:

```sql
UPDATE app_users
   SET last_successful_login_at =
       GREATEST(
           COALESCE(last_successful_login_at, :occurred_at),
           :occurred_at
       )
 WHERE user_id = :account_id;
```

`:occurred_at` must come from a trusted server/DB source after success, never sent by the browser. The query is a PostgreSQL example; other DBs may have different equivalent functions. For `loginCount`, use atomic DB increments and idempotency keys if event delivery can repeat.

## 14. Concurrency and Password-Reset Races

If two login requests with the same legacy password arrive nearly simultaneously:

```text
Request A                       Request B
load hash old                   load hash old
matches true                    matches true
upgradeEncoding true            upgradeEncoding true
encode(raw) -> hash-A           encode(raw) -> hash-B
CAS old -> hash-A: 1 row        CAS old -> hash-B: 0 row
one writer wins                 retry login from current hash,
                                or fail closed by policy
```

Without CAS/versioning, both could write hashes with different salts that still verify the same password—which might look "harmless" in tests, yet that same code can **overwrite an ongoing password reset**, creating a severe security flaw.

**Never use `synchronized` on a single JVM** to guarantee multiple pods will not overwrite each other. Test against real PostgreSQL/Redis across multiple nodes, transactions, and lock contention. If the user changed their password after a login request read the old hash, the final commit step must guard against stale state or enforce an explicit re-auth policy.

A typical safe SQL condition:

```sql
UPDATE app_users
SET password_hash = :new_hash,
    credential_version = credential_version + 1
WHERE user_id = :user_id
  AND credential_version = :expected_version
  AND password_hash = :old_hash;
```

Assert update count = 1. If 0, **never** follow up with an unconditional update. Successful rehashes may be 1 even if `encode` was called twice; tests should measure **DB commits** rather than counting encoder invocations alone.

## 15. Plain Java 17: Testing Login Branches and Atomic Rehashing

The following program runs **with no Spring dependency** and creates **randomly salted `PBKDF2WithHmacSHA256`** password hashes (never storing raw passwords in the map). It simulates:

- Wrong password: no upgrade and no `successfulLogins` update.
- Correct password + legacy hash: upgraded once.
- Correct password after rehash: no further upgrade.
- 12 concurrent logins: all 12 valid authentications are counted, yet **only 1 rehash write succeeds**.

Create **`PasswordUpgradeDemo.java`**:

```java
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.security.*;
import javax.crypto.*;
import javax.crypto.spec.*;

public class PasswordUpgradeDemo {
    // LOW round counts for fast tests. Never copy to production.
    static final int LEGACY_ROUNDS = 1600;
    static final int CURRENT_ROUNDS = 3600;
    static final SecureRandom RANDOM = new SecureRandom();

    record Account(String username, String passwordHash,
                   int successfulLogins, Instant lastLoginAt) {}

    static String hash(String raw, int rounds) {
        byte[] salt = new byte[16];
        RANDOM.nextBytes(salt);
        return "pbkdf2$" + rounds + "$" + encode64(salt) + "$"
                + encode64(derive(raw, salt, rounds));
    }

    static String encode64(byte[] data) {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(data);
    }

    static byte[] derive(String raw, byte[] salt, int rounds) {
        char[] chars = raw.toCharArray();
        PBEKeySpec spec = new PBEKeySpec(chars, salt, rounds, 256);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException(e);
        } finally {
            spec.clearPassword();
            Arrays.fill(chars, '\0');
        }
    }

    static String[] parts(String encoded) {
        String[] p = encoded.split("\\$", -1);
        if (p.length != 4 || !"pbkdf2".equals(p[0])) {
            throw new IllegalArgumentException(
                    "Unsupported hash format");
        }
        return p;
    }

    static boolean matches(String raw, String encoded) {
        String[] p = parts(encoded);
        int rounds = Integer.parseInt(p[1]);
        byte[] salt = Base64.getUrlDecoder().decode(p[2]);
        byte[] expected = Base64.getUrlDecoder().decode(p[3]);
        return MessageDigest.isEqual(
                expected, derive(raw, salt, rounds));
    }

    static boolean needsUpgrade(String encoded) {
        return Integer.parseInt(parts(encoded)[1]) < CURRENT_ROUNDS;
    }

    static final class LoginStore {
        final ConcurrentHashMap<String, Account> accounts =
                new ConcurrentHashMap<>();
        final AtomicInteger upgradeWrites = new AtomicInteger();
        final Clock clock;

        LoginStore(Clock clock) { this.clock = clock; }

        void createLegacy(String user, String raw) {
            accounts.put(user, new Account(
                    user, hash(raw, LEGACY_ROUNDS), 0, null));
        }

        boolean authenticate(String user, String raw) {
            if (user == null || raw == null) return false;
            AtomicBoolean accepted = new AtomicBoolean(false);

            accounts.computeIfPresent(user, (id, current) -> {
                // Simulation within one JVM only. Production must not run
                // slow hashing inside a ConcurrentHashMap lock.
                if (!matches(raw, current.passwordHash())) {
                    return current;
                }
                String newHash = current.passwordHash();
                if (needsUpgrade(newHash)) {
                    newHash = hash(raw, CURRENT_ROUNDS);
                    upgradeWrites.incrementAndGet();
                }
                accepted.set(true);
                return new Account(
                        current.username(), newHash,
                        current.successfulLogins() + 1,
                        clock.instant());
            });
            return accepted.get();
        }

        Account get(String user) { return accounts.get(user); }
    }

    public static void main(String[] args) throws Exception {
        Clock fixed = Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC);
        LoginStore store = new LoginStore(fixed);
        store.createLegacy("alice", "right-password");

        System.out.println("wrongAccepted="
                + store.authenticate("alice", "wrong"));
        System.out.println("failureUpgradeWrites="
                + store.upgradeWrites.get());
        System.out.println("failureLoginCount="
                + store.get("alice").successfulLogins());
        System.out.println("legacyCorrectAccepted="
                + store.authenticate("alice", "right-password"));
        System.out.println("hashNowCurrent="
                + !needsUpgrade(store.get("alice").passwordHash()));
        System.out.println("upgradesAfterFirst="
                + store.upgradeWrites.get());
        System.out.println("loginsAfterFirst="
                + store.get("alice").successfulLogins());
        System.out.println("secondAccepted="
                + store.authenticate("alice", "right-password"));
        System.out.println("upgradesAfterSecond="
                + store.upgradeWrites.get());
        System.out.println("loginsAfterSecond="
                + store.get("alice").successfulLogins());
        System.out.println("wrongAfterUpgradeAccepted="
                + store.authenticate("alice", "wrong"));

        LoginStore race = new LoginStore(fixed);
        race.createLegacy("bob", "correct");
        ExecutorService pool = Executors.newFixedThreadPool(12);
        try {
            CountDownLatch gate = new CountDownLatch(1);
            List<Future<Boolean>> results = new ArrayList<>();
            for (int i = 0; i < 12; i++) {
                results.add(pool.submit(() -> {
                    gate.await();
                    return race.authenticate("bob", "correct");
                }));
            }
            gate.countDown();
            int count = 0;
            for (Future<Boolean> result : results) {
                if (result.get()) count++;
            }
            System.out.println("concurrentAccepted=" + count);
            System.out.println("concurrentUpgradeWrites="
                    + race.upgradeWrites.get());
            System.out.println("concurrentLoginCount="
                    + race.get("bob").successfulLogins());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Compile/run:

```bash
javac PasswordUpgradeDemo.java
java PasswordUpgradeDemo
```

Stdout verified with Java 17:

```text
wrongAccepted=false
failureUpgradeWrites=0
failureLoginCount=0
legacyCorrectAccepted=true
hashNowCurrent=true
upgradesAfterFirst=1
loginsAfterFirst=1
secondAccepted=true
upgradesAfterSecond=1
loginsAfterSecond=2
wrongAfterUpgradeAccepted=false
concurrentAccepted=12
concurrentUpgradeWrites=1
concurrentLoginCount=12
```

**Why did 12 requests succeed while only 1 upgraded?** `ConcurrentHashMap.computeIfPresent` serializes read/verify/update per key within the process; the first request upgrades cost 1600 to 3600, and subsequent requests still verify the right password yet see the current hash and do not rehash. This does **not** guarantee "only one login may succeed"; that is a separate session/concurrency management problem.

**Demo limitations:**

- PBKDF2 1600/3600 rounds are **unsuitable for production**; they only keep tests fast. Choose encoder/parameters determined by current policy and benchmarks.
- `computeIfPresent` runs CPU-heavy hashing under a lock—purely for deterministic observation in Java SE. Production must verify outside locks and use durable CAS/versioning/transactions while guarding against stale resets.
- This is not Spring's `PasswordEncoder`, has no `DelegatingPasswordEncoder` ID format, and connects to no database. Spring provider tests must use Sections 6–8.
- `successfulLogins` reflects simulated method calls, not real HTTP sessions or idempotent event delivery.
- The helpers only accept well-formed hashes; production must validate malformed inputs and bound parameters to prevent DoS. Never let clients specify arbitrary `rounds`.
- Raw password `String`s remain on the heap until GC; Java cannot guarantee scrubbing every copy. Never log passwords or encoded hashes in logs/stack traces.
- `concurrentAccepted=12` is expected because all 12 used the **same valid password**, while `concurrentUpgradeWrites=1` shows only a single rehash occurred.

## 16. Common Test and Implementation Mistakes

**1. Asserting only HTTP 200/302.** Logins can redirect even on failure, and status codes do not prove the password hash changed. Check the failure URL, DB, and account state.

**2. Using `@WithMockUser` to test upgrades.** It bypasses the provider; tests stay green even if `UserDetailsPasswordService` is never wired in reality.

**3. Mocking `PasswordEncoder.matches` to always return true.** Wrong-password tests also succeed, failing to verify the boundary. Separate true/false tests.

**4. Testing encoders by comparing against a fixed output hash.** BCrypt/PBKDF2 are salted, so hashes differ each time. Use `matches` and `upgradeEncoding`, asserting properties only.

**5. Declaring a new `PasswordEncoder` bean and expecting DB hashes to migrate on their own.** Authentication with valid credentials and proper updater wiring are required; hashes never migrate from configuration alone.

**6. Treating `newPassword` in `UserDetailsPasswordService` as raw.** Storing plaintext or double-hashing both break login. Assert the persisted value is encoded and matches raw.

**7. Calling `updatePassword` inside `loadUserByUsername`.** Users entering a wrong password would trigger rehashes or mutate success metadata; wrong security ordering.

**8. Asserting the principal's password equals the newest hash.** Provider 6.5 can keep the pre-rehash principal; inspect the repository and API contract instead.

**9. Ignoring compromised password or account flags.** Unsuccessful auth paths still write hashes/audits. Test disabled/locked/expired/compromised cases.

**10. Updater returning null.** The provider may fail to create a valid `Authentication`; the service must return a valid `UserDetails`, not pretend to return void.

**11. `UPDATE` filtered by username alone.** Concurrent password resets can be overwritten by an older rehash. Use CAS/versioning and test two transactions.

**12. Treating a CAS miss as success without re-checking the new credential.** When a password just changed, continuing is dangerous; fail closed or re-verify completely.

**13. Catching `SQLException` and ignoring it silently.** Tests report login success even though the DB has no rehash; define failure policies and internal logs.

**14. Counting logins via `AuthenticationSuccessEvent` + `InteractiveAuthenticationSuccessEvent` + success handler.** One login gets counted multiple times. Pick one event source, correlation, and idempotency.

**15. Writing `lastLoginAt` when loading a user.** Users who are merely looked up or enter wrong passwords get marked "successful".

**16. Recording IPs from untrusted `X-Forwarded-For`.** Clients can spoof headers; trust only normalized proxy boundaries and apply retention limits.

**17. Testing on an in-memory DB while production uses PostgreSQL.** Isolation, locking, transactions, and SQL dialects differ; test the repository on the real engine.

**18. Running tests inside `@Transactional` that rolls back everything.** Tests fail to prove commits/outboxes; add separate tests with independent transactions.

**19. Caching stale `UserDetails` indefinitely.** Hashes change while caches hold old data; credential checks and invalidation violate policy.

**20. Logging passwords or hashes for debugging.** Hashes are sensitive credentials that enable offline attacks if DBs/logs leak. Use secret-free security metrics.

**21. Setting hash cost too high on the login path.** Upgrading hashes can spike CPU/latency into a DoS; rate-limit login attempts, plan capacity, set timeouts, and roll out carefully.

**22. Not testing rollback or lost-response outcomes.** The API reports an error even though the DB committed; retries can duplicate audits. Use idempotency keys/durable outboxes.

## 17. Recommended End-to-End Scenarios

| Scenario | Test level | What to observe |
| --- | --- | --- |
| Legacy hash, right password | Unit + DB + HTTP | Auth succeeds; new encoded hash; accurate success audit |
| Current hash, right password | Unit + DB | Auth succeeds; hash **unchanged**; audit increments accurately |
| Wrong password | Unit + DB + HTTP | Auth fails; hash and `lastLoginAt` unchanged |
| Nonexistent username | Unit + HTTP | No user existence leak, no upgrade |
| Account disabled or locked | Unit + HTTP | No auth; no success side effects |
| Credential expired/compromised | Unit + HTTP | Per policy, no "success" updates |
| No `UserDetailsPasswordService` | Unit + wiring test | No automatic rehash called |
| Service update returns null | Unit | Does not silently mark auth success |
| JDBC exception | DB integration | Clear rollback/failure policy, no false success |
| Two simultaneous upgrades | DB concurrency | Only one CAS write; no data corruption |
| Password reset mid-login | DB concurrency | Reset is not overwritten; stale credential rejected |
| Session/form login | MockMvc + DB | Success handler and session persistence accurate |
| HTTP Basic/resource server | Dedicated integration | Do not expect form success handler |
| Inactive event publisher | Unit/integration | Does not implicitly rely on unconfigured events |
| Duplicate event delivery | Consumer test | Idempotent outcome |
| Multiple instances | E2E + real DB | Consistent state and audit per policy |
| Logs/metrics | Security audit | No raw password, encoded hash, or session token leaks |

### Test data practices

- Use **dummy** users/passwords for test data; never copy production hashes or credentials as fixtures.
- Never store raw passwords in test snapshots/logs. Use protected temporary `@Test` resource fixtures or test-only secrets.
- For BCrypt, pick a low cost for fast unit tests, yet **never propagate test config to production**.
- Fix `Clock` for timestamp tests; never use `Thread.sleep` to test recent logins or time boundaries.
- Limit fakes/mocks to branch tests; a handful of real integration tests against the database/auth provider must cover safety invariants.

## 18. Lesson Completion Checklist

1. Can you explain why upgrading password hashes is only feasible during login with a valid raw password?
2. Do you know the `matches → upgradeEncoding → encode → updatePassword` sequence and the requirement that an updater exists?
3. Did you test legacy and current hashes with a real encoder rather than asserting fixed hash strings?
4. Did you test that wrong passwords, disabled/locked users, and expired/compromised credentials never write rehashes?
5. Did you verify that an encoded value is passed to `UserDetailsPasswordService` exactly once and that the service returns a valid `UserDetails`?
6. Did you separate provider unit tests from DB/HTTP integration tests, knowing `@WithMockUser` bypasses the provider?
7. Did you verify DB reads after commit and that a second login does not rehash infinitely?
8. Did you protect concurrent password resets and double-upgrades via CAS/versioning/transactions?
9. Do you have a safe policy for CAS misses and DB failures instead of "last write wins" on passwords?
10. Do `lastSuccessfulLoginAt`/audit updates run only after authenticated success on the intended event type?
11. Did you avoid double-counting between success handlers, `AuthenticationSuccessEvent`, and `InteractiveAuthenticationSuccessEvent`?
12. Did you distinguish rehashing (password unchanged) from user password changes (which may revoke sessions)?
13. Did you test the impact of `UserCache`, principal snapshots, and sessions on password upgrades?
14. Did you test multi-node, rollback/commit, lost responses, and audit/outbox idempotency where needed?
15. Are raw passwords/hashes kept out of logs and test-only parameters kept out of production defaults?

### Official documentation

- Spring Security 6.5 — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security 6.5 — Password Storage / DelegatingPasswordEncoder: https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html
- Spring Security 6.5 — PasswordEncoder API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/PasswordEncoder.html
- Spring Security 6.5 — UserDetailsPasswordService API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsPasswordService.html
- Spring Security 6.5 — Authentication Events: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html
- Spring Security 6.5 — Form Login: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html
- Spring Security 6.5.11 — DaoAuthenticationProvider source for checking the upgrade branch: https://github.com/spring-projects/spring-security/blob/6.5.11/core/src/main/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.java
- Spring Security 6.5.11 — AbstractUserDetailsAuthenticationProvider source: https://github.com/spring-projects/spring-security/blob/6.5.11/core/src/main/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.java
- OWASP — Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html

**Conclusion:** Testing "password upgrades and post-authentication data updates" is not just testing valid credentials. You must prove **new hashes are persisted durably under the right conditions**, **no writes happen on failure branches**, **concurrent password resets are never overwritten**, and **`lastLogin`/audits reflect only successful authentication events**. Combine direct tests on `DaoAuthenticationProvider`, real encoders, real database transactions, and login filters to cover every boundary.
