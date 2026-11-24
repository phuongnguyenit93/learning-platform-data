# UserDetailsPasswordService and Post-Login Hash Upgrades

**Module:** Spring Security – authentication. **Knowledge group:** Password upgrades.

## 1. The Problem: Legacy Passwords Verify, Yet You Should Not Keep Storing Legacy Hashes

A running system may hold multiple password generations:

- An older account stores its password as `{noop}...`, legacy SHA/MD5, or a low-parameter PBKDF2/scrypt/bcrypt hash. `{noop}` and fast digests are **not safe enough** for production password storage.
- Newer accounts already use a stronger encoder, such as bcrypt with an appropriate work factor.
- The system replaced `PasswordEncoder` to **read legacy hashes while generating new hashes under the current policy**.
- The user logs in with the **correct original password**; this is one of the rare moments when the server receives a valid raw password to recompute a safe hash.

The goal is: **after a successful login**, if the current hash needs an upgrade, the application generates a new hash from the verified raw password and saves it to the account store without forcing the user to manually change their password.

Spring Security provides three components that fit together:

1. `PasswordEncoder`, especially `DelegatingPasswordEncoder`, **verifies the password** and reports `upgradeEncoding(storedHash)`.
2. `DaoAuthenticationProvider` **orchestrates username/password authentication** and provides a hook to trigger the upgrade on the success branch.
3. `UserDetailsPasswordService` **writes the new hash** to the user store and returns the updated `UserDetails`.

This technique is **rehash-on-login**, not a mechanism that can decrypt stored hashes. If a user never logs in again, the server does not know the raw password and cannot derive it to rehash; when overly weak hashes must be eliminated, a verified password reset workflow may be necessary.

> **Principle:** Hash upgrades must occur **after valid credentials and account authorization checks pass**. Never use data from an unauthenticated request to write a new password. Never let an upgrade overwrite a password that was just reset in another transaction.

## 2. Concepts to Distinguish

| Component | Primary contract | Role in the upgrade process |
| --- | --- | --- |
| `UserDetailsService` | `loadUserByUsername(username)` | **Reads** username, password hash, status, and authorities for authentication |
| `PasswordEncoder` | `matches(raw, stored)`, `encode(raw)`, `upgradeEncoding(stored)` | Checks legacy hashes; decides if an upgrade is needed; creates hashes per new policy |
| `DaoAuthenticationProvider` | `authenticate(...)` | Verifies password and status, and triggers the upgrade hook only on the success path |
| `UserDetailsPasswordService` | `updatePassword(user, encodedNewPassword)` | **Persists** the new hash value; returns the updated `UserDetails` |
| `ProviderManager` | `authenticate(...)` | Coordinates providers and normally erases credentials from the authenticated result |
| `UserDetailsManager` | `createUser`, `updateUser`, `changePassword`,... | Account administration; **different purpose** from the hash-upgrade hook |
| Domain repository/DAO | Transactional/versioned save operations | Executes durable updates, prevents race conditions, and handles cache invalidation |

**Do not conflate:**

- `UserDetailsService` only knows how to **read** data; it cannot automatically save a new hash unless you provide a write mechanism.
- `UserDetailsPasswordService` does not take a raw password to verify itself; it receives a **new hash already created by the encoder**.
- `UserDetailsManager.changePassword(old, new)` is a user-initiated password change, typically tied to the current user in `SecurityContext`; it is not the same contract as the provider-triggered hash upgrade.
- `PasswordEncoder.upgradeEncoding(...) == true` is only a **signal**. Without a write adapter or configured hook, the database will not change at all.

## 3. The UserDetailsPasswordService Contract

Package: `org.springframework.security.core.userdetails`. The interface has a single method:

~~~java
public interface UserDetailsPasswordService {
    UserDetails updatePassword(UserDetails user, String newPassword);
}
~~~

According to Spring Security 6.5 Javadoc:

- Parameter `user`: the account information to update. In multi-tenant applications, ensure the user identifier here points to the exact verified account/tenant.
- `newPassword`: **the password already encoded by the configured PasswordEncoder**, such as `{bcrypt}$2a$...`; **not the raw password**.
- Effect: replaces the hash in the account store (database, directory, or equivalent store).
- Returns: **the updated `UserDetails`** containing the new hash.

An example implementation often mentioned is `InMemoryUserDetailsManager`, which implements both `UserDetailsManager` and `UserDetailsPasswordService`. It is handy for demos/tests, but it is not a durable database store.

**Several rules when implementing it yourself:**

1. Do not call `encoder.encode(newPassword)` again inside `updatePassword`, because `newPassword` is already a **hash**; double hashing prevents the user from logging in with their original raw password.
2. Never accept an arbitrary client-supplied username/tenant as the update target. The target must be the account verified by the provider.
3. Only replace **the password hash and related metadata**. Do not accidentally reset authorities, lock state, flags, tenant membership, or profile fields.
4. Return a valid `UserDetails` consistent with the new hash and authorities policy; do not return `null`.
5. Implement a strategy to prevent concurrent overwrites by password reset/password change, along with transaction handling, auditing, and cache invalidation.
6. Never write raw passwords, new hashes, or full `UserDetails` objects to logs, traces, or API responses.

### What Does the Return Value Mean?

The provider may use the returned `UserDetails` when finishing authentication. However, do not build business logic assuming **every `Authentication.getPrincipal()` implementation is guaranteed to retain the new hash**: principal creation also depends on `AbstractUserDetailsAuthenticationProvider`, `forcePrincipalAsString` settings, and credential erasure in `ProviderManager`.

**The source of truth for verifying a successful save is reading back from the account store after the transaction**, not `principal.getPassword()` after login. The password inside the principal may have been erased to protect credentials.

## 4. Exactly When Does DaoAuthenticationProvider Trigger an Upgrade?

Sample flow for a username/password request in Spring Security Servlet:

~~~text
POST /login
    |
    v
UsernamePasswordAuthenticationFilter
    |
    v
AuthenticationManager -> ProviderManager
    |
    v
DaoAuthenticationProvider
    |
    +--> UserDetailsService.loadUserByUsername(username)
    |        -> UserDetails(passwordHash, flags, authorities)
    |
    +--> account status check (pre-check)
    |
    +--> PasswordEncoder.matches(raw, storedHash)
    |          | false
    |          v
    |      BadCredentialsException -> login FAILED
    |
    +--> credential/account check (post-check)
    |          | failed
    |          v
    |      AuthenticationException -> login FAILED
    |
    +--> branch creating successful authentication
               |
               +--> compromised password checker if configured
               |
               +--> has UserDetailsPasswordService?
               |          |
               |          +--> upgradeEncoding(storedHash)?
               |                      |
               |                      +--> false: keep hash
               |                      |
               |                      +--> true:
               |                           encode(verified raw)
               |                           updatePassword(user, newEncoded)
               |
               v
         authenticated Authentication
               |
               v
      ProviderManager eraseCredentials()
               |
               v
         SecurityContext/session
~~~

**Technical hook:** In Spring Security 6.5's `DaoAuthenticationProvider` implementation, upgrade logic runs inside `createSuccessAuthentication(...)`. The provider uses the just-verified raw credentials, calls `PasswordEncoder.upgradeEncoding(existingEncodedPassword)` when a password service is configured, generates the new hash via `encode(raw)`, and calls `userDetailsPasswordService.updatePassword(user, newHash)`.

Important conditions that must all hold together:

- The request is processed by **that `DaoAuthenticationProvider`**, with `UserDetailsService` and `PasswordEncoder` matching the data format.
- The password **verified successfully**, the account passed checks, and login reached the success branch. If a compromised password check is configured and fails, it does not enter the rehash branch either.
- The old password hash can be evaluated by `upgradeEncoding`.
- The provider **has attached** a real `UserDetailsPasswordService` that persists data, not a no-op stub.
- `upgradeEncoding(stored)` returns `true` under the current encoder policy.

**This does not mean** every `AuthenticationManager.authenticate(...)` call rehashes. When a hash already meets policy, the provider does not need to generate a new salt/hash. When the password is wrong, the account is locked/disabled, or a custom provider does not use this hook, no upgrade should occur from this branch.

### Things That Do Not Happen Automatically

- Spring cannot rehash accounts that never log in because it lacks their raw passwords.
- The hook does not infer custom repository schemas, columns, or transactions on its own.
- `PasswordEncoder` does not write to the database itself.
- Not every `AuthenticationProvider`—such as JWT/OIDC/LDAP or a custom provider—uses `UserDetailsPasswordService`.
- Rehashing does **not automatically** revoke sessions, refresh tokens, or JWTs, nor re-verify roles on every request.
- Replacing a hash does **not automatically** increase bcrypt cost or change algorithms if the encoder policy itself did not change.

## 5. How Is PasswordEncoder.upgradeEncoding Interpreted?

### 5.1. Three Distinct Operations

~~~java
String stored = "{noop}old-password"; // Legacy example ONLY, unsafe

boolean correct = encoder.matches("old-password", stored);
boolean outdated = encoder.upgradeEncoding(stored);

String encodedNew = encoder.encode("old-password");
~~~

This is an **illustrative snippet**, without declarations/imports for `encoder`. With `PasswordEncoderFactories.createDelegatingPasswordEncoder()` in Spring Security 6.5, `{noop}...` can match, is marked as needing an upgrade because its ID differs from the `bcrypt` creation standard, and the encoder produces a new hash starting with `{bcrypt}`.

| Method | Verifies the password? | Generates a new hash? | Writes to the database? |
| --- | --- | --- | --- |
| `matches(raw, stored)` | **Yes** | No | No |
| `upgradeEncoding(stored)` | **No** | No | No |
| `encode(raw)` | Does not check whether raw is valid for the account | **Yes** | No |
| `updatePassword(user, encodedNew)` | Does not replace provider verification | Does not need to encode again | **Yes**, if adapter persists properly |

**Do not use `upgradeEncoding` as proof of a valid password.** Anyone can submit any raw password and a stored hash may still evaluate as "needs upgrade". The decision to rehash must occur only after `matches` succeeds and account checks pass.

### 5.2. DelegatingPasswordEncoder and {id}

Hash data has the form:

~~~text
{id}encodedPassword
~~~

In Spring Security 6.5's factory, `idForEncode` defaults to `bcrypt`. Older accounts with other IDs (e.g., `{noop}`, `{pbkdf2}`, `{scrypt}`) can be matched via compatibility mappings, while `upgradeEncoding` requests changing to the current encode standard whenever the ID differs.

~~~text
DB before: {noop}legacy123           (example only, dangerous plaintext)
LOGIN:     raw = legacy123 -> matches = true
UPGRADE:   encoder.upgradeEncoding("{noop}...") = true
ENCODE:    encoder.encode(raw) -> {bcrypt}$2a$10$...
DB after:  {bcrypt}$2a$10$...
~~~

The `{bcrypt}$2a$10$...` value above is a **schematic**, not a concrete hash. BCrypt generates a random salt, so unit tests should never compare hashes verbatim.

Even with the same `bcrypt` ID, `BCryptPasswordEncoder.upgradeEncoding(...)` can detect when an old hash's work factor is lower than the currently configured strength. For other encoders, `upgradeEncoding` semantics depend on the implementation; **never assume** every `PasswordEncoder` detects every policy change.

### 5.3. Missing Prefix or Unmapped ID

Data like `$2a$10$...` without `{bcrypt}`, or `{unknown}payload`, can cause `DelegatingPasswordEncoder.matches(...)` to throw `IllegalArgumentException` when no encoder is mapped for that ID. Therefore, hook-based upgrades **do not automatically fix** records that the system cannot validate yet.

You must identify the exact legacy format first, prepend verified metadata prefixes or use a fallback that is **bounded, audited, and scheduled for removal**, and only then rely on rehash-on-login. Never set `NoOpPasswordEncoder` as a fallback for unknown data just to "let users log in".

## 6. Runnable Java 17 Demo: Upgrading Exactly Once After Valid Login

This demo uses **Spring Security Core 6.5.11** with `DaoAuthenticationProvider`, `ProviderManager`, `PasswordEncoderFactories`, and `InMemoryUserDetailsManager`.

It demonstrates 4 behaviors:

1. A wrong password does not trigger `updatePassword`.
2. A valid login with legacy `{noop}` hash triggers **exactly one** update to `{bcrypt}`.
3. Logging in again with the same raw password succeeds and **does not re-update** a hash that already meets policy.
4. A provider **without UserDetailsPasswordService** still allows legacy login to succeed, but **does not automatically save a new hash**.

> `{noop}` is used solely to prove migration. It represents plaintext storage and **must not be used to create new accounts in production**. The demo does not model distributed/database/HTTP layers.

### 6.1. Structure

~~~text
password-upgrade-demo/
├── build.gradle
└── src/main/java/example/PasswordUpgradeDemo.java
~~~

**File `build.gradle`:**

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

application {
    mainClass = 'example.PasswordUpgradeDemo'
}
~~~

**File `src/main/java/example/PasswordUpgradeDemo.java`:**

~~~java
package example;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsPasswordService;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

public final class PasswordUpgradeDemo {

    private static Authentication login(
            AuthenticationManager manager, String user, String password) {
        return manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        user, password));
    }

    public static void main(String[] args) {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails legacy = User.withUsername("lan")
                .password("{noop}legacy-123")
                .roles("READER")
                .build();

        // In-memory account store dedicated to the example.
        InMemoryUserDetailsManager users =
                new InMemoryUserDetailsManager(legacy);

        // Detach the UserDetails used during authentication from the stored instance.
        // This prevents eraseCredentials from accidentally wiping the store's hash.
        UserDetailsService loader = username ->
                User.withUserDetails(
                        users.loadUserByUsername(username)).build();

        AtomicInteger updates = new AtomicInteger();

        UserDetailsPasswordService updater = (user, encodedHash) -> {
            UserDetails saved = users.updatePassword(user, encodedHash);
            updates.incrementAndGet();
            // Return an isolated copy for authentication.
            return User.withUserDetails(saved).build();
        };

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(loader);
        provider.setPasswordEncoder(encoder);
        provider.setUserDetailsPasswordService(updater);

        AuthenticationManager manager = new ProviderManager(provider);

        String initialHash = users.loadUserByUsername("lan").getPassword();
        System.out.println("before.legacy="
                + initialHash.startsWith("{noop}"));
        System.out.println("before.needsUpgrade="
                + encoder.upgradeEncoding(initialHash));

        // First attempt with wrong password: must not upgrade.
        try {
            login(manager, "lan", "wrong");
            System.out.println("wrong=unexpected-success");
        } catch (BadCredentialsException expected) {
            System.out.println("wrong=BadCredentialsException");
        }
        System.out.println("afterWrong.updates=" + updates.get());

        // Correct password: provider matches, re-encodes, then calls updater.
        Authentication first = login(manager, "lan", "legacy-123");
        String migratedHash =
                users.loadUserByUsername("lan").getPassword();

        System.out.println("first.authenticated="
                + first.isAuthenticated());
        System.out.println("first.updates=" + updates.get());
        System.out.println("first.bcrypt="
                + migratedHash.startsWith("{bcrypt}"));
        System.out.println("first.matches="
                + encoder.matches("legacy-123", migratedHash));
        System.out.println("first.needsUpgrade="
                + encoder.upgradeEncoding(migratedHash));
        System.out.println("first.roleReader="
                + first.getAuthorities().stream().anyMatch(a ->
                        "ROLE_READER".equals(a.getAuthority())));

        // Next valid login does not need to re-encode.
        Authentication second = login(manager, "lan", "legacy-123");
        System.out.println("second.authenticated="
                + second.isAuthenticated());
        System.out.println("second.updates=" + updates.get());

        // WITHOUT a password service attached, the new hash is not saved.
        InMemoryUserDetailsManager noUpdaterStore =
                new InMemoryUserDetailsManager(
                        User.withUsername("mai")
                                .password("{noop}other-legacy")
                                .roles("USER")
                                .build());

        UserDetailsService noUpdaterLoader = username ->
                User.withUserDetails(
                        noUpdaterStore.loadUserByUsername(username)).build();

        DaoAuthenticationProvider withoutUpdater =
                new DaoAuthenticationProvider(noUpdaterLoader);
        withoutUpdater.setPasswordEncoder(encoder);

        AuthenticationManager noUpdaterManager =
                new ProviderManager(withoutUpdater);

        Authentication legacyLogin =
                login(noUpdaterManager, "mai", "other-legacy");
        System.out.println("withoutUpdater.authenticated="
                + legacyLogin.isAuthenticated());
        System.out.println("withoutUpdater.stillLegacy="
                + noUpdaterStore.loadUserByUsername("mai")
                        .getPassword().startsWith("{noop}"));
    }
}
~~~

### 6.2. Running

From the `password-upgrade-demo` directory, using **JDK 17+** and a compatible Gradle version:

~~~bash
gradle -q run
~~~

If the project includes Gradle Wrapper, run `./gradlew -q run`; on Windows use `gradlew.bat -q run`. On the first run, Gradle may need to download dependencies from Maven Central.

**Stdout from the program** (excluding Gradle's own logs if your environment configuration prints additional messages):

~~~text
before.legacy=true
before.needsUpgrade=true
wrong=BadCredentialsException
afterWrong.updates=0
first.authenticated=true
first.updates=1
first.bcrypt=true
first.matches=true
first.needsUpgrade=false
first.roleReader=true
second.authenticated=true
second.updates=1
withoutUpdater.authenticated=true
withoutUpdater.stillLegacy=true
~~~

### 6.3. Explaining Each Output Group

- `before.legacy=true`: the store currently holds a `{noop}...` hash. This is **unsafe** sample data, used to make the upgrade visible.
- `before.needsUpgrade=true`: the encoder generates new hashes with `bcrypt`, so the `noop` format is flagged as outdated.
- `wrong=BadCredentialsException` and `afterWrong.updates=0`: a wrong password never enters the provider's upgrade branch.
- `first.authenticated=true`, `first.updates=1`: the provider verified the password, called the adapter to save the new hash, and completed login.
- `first.bcrypt=true` and `first.matches=true`: the stored record now holds a new bcrypt hash, and the raw password still verifies.
- `first.needsUpgrade=false`: the new hash satisfies the current policy's ID/cost.
- `first.roleReader=true`: authorities preserve the role granted by the store; upgrading a hash does not mean granting new permissions.
- `second.updates=1`: subsequent logins do not rewrite the hash when `upgradeEncoding` returns false.
- `withoutUpdater.stillLegacy=true`: **configuring PasswordEncoder alone is not enough** to persist new hashes after login.

**Why do loader/updater create copies?** `ProviderManager` erases credentials on successful `Authentication` by default. If the principal shares the same `UserDetails` object with the store/cache, credential erasure can wipe out the stored hash. The demo constructs `User.withUserDetails(...).build()` to avoid sharing mutable objects between the store and the principal. In production, the same principle applies to the `UserDetails` cache and objects returned to the provider.

**The demo does not prove database concurrency safety.** `InMemoryUserDetailsManager` is used single-threaded without transactional storage; the next section specifically designs conditional updates for real environments.

## 7. Spring Boot Integration: Declaring Encoder, Reader, and Password Updater

In a Spring Boot Servlet application using username/password, the following configuration example is **illustrative integration code**, not a standalone Java program: it requires repositories/services, transactions, Spring configuration, imports, and a complete `SecurityFilterChain`.

~~~java
@Configuration
class AuthenticationBeans {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    DaoAuthenticationProvider daoAuthenticationProvider(
            UserDetailsService userDetailsService,
            UserDetailsPasswordService passwordUpdater,
            PasswordEncoder passwordEncoder) {

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(userDetailsService);
        provider.setPasswordEncoder(passwordEncoder);
        provider.setUserDetailsPasswordService(passwordUpdater);
        return provider;
    }
}
~~~

Important details:

- The `passwordEncoder` bean must represent **the same policy** used to create passwords during registration, password change, and login verification.
- `userDetailsService` reads data from the account store. Do not return a full JPA entity with relationships/heavy business data as the principal just for convenience.
- `passwordUpdater` must be a real implementation of `UserDetailsPasswordService` and write to the exact source that the reader queries.
- The provider must be **registered in the right AuthenticationManager/SecurityFilterChain** handling logins. Having a bean in the application context does not prove that a different filter isn't using another bean.
- If the system has multiple managers, chains, providers, or uses OAuth2/LDAP, do not assume the DAO provider's upgrade hook runs on all login paths.

### Database Hash-Saving Service Example (Sketch)

~~~java
// ARCHITECTURAL ILLUSTRATION CODE, NOT standalone compilable.
// Assumes repository supports comparing passwordHash/version,
// and AuthUserDetails is the application's UserDetails projection.
@Service
public class DatabasePasswordUpdater implements UserDetailsPasswordService {

    private final AccountRepository accounts;

    public DatabasePasswordUpdater(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    @Transactional
    public UserDetails updatePassword(UserDetails user, String encodedNew) {
        AuthUserDetails current = (AuthUserDetails) user;

        int updated = accounts.updatePasswordIfVersionMatches(
                current.userId(),
                current.tenantId(),
                current.passwordVersion(),
                current.getPassword(),
                encodedNew);

        if (updated != 1) {
            throw new IllegalStateException(
                    "Password changed concurrently; reload required");
        }

        return current.withPasswordAndVersion(
                encodedNew, current.passwordVersion() + 1);
    }
}
~~~

In this example, `AccountRepository`, `AuthUserDetails`, and `withPasswordAndVersion` are **project-defined abstractions**, not built-in Spring Security APIs. Throwing an exception on conflict is a conservative option; production code must define auditing, retries, reauthentication prompts, and public error mapping without leaking passwords/versions.

**Do not use `updateUser` to overwrite an entire entity from stale data.** The provider cares about the password hash, whereas authorities/status/tenant fields may have been modified by another transaction. A dedicated update should **only modify the password hash and password version columns**, leaving permissions and lock flags untouched.

## 8. Conditional SQL Updates to Prevent Restoring Old Passwords

### 8.1. An Easily Missed Race Condition

Two simultaneous requests:

~~~text
Request A: user logs in with old password
   |
   +-- reads hash v7 -> matches(rawOld, v7) = true
   |
   +-- starts computing stronger hash from rawOld
                                Request B: user resets password
                                   |
                                   +-- verifies recovery
                                   +-- writes new hash of rawNew, version v8
   |
   +-- A overwrites with v7-upgraded hash from rawOld (if UPDATE is unconditional)
   |
   v
The reset password is accidentally reverted back to the old password!
~~~

This is not merely a consistency glitch—it can be a **security vulnerability**: a user resets their password in response to account compromise, only for an older login request to overwrite it.

### 8.2. Compare-and-Swap (CAS) on Version/Hash

Suppose the `accounts` table has `id`, `tenant_id`, `password_hash`, `password_version`. Illustrative SQL:

~~~sql
UPDATE accounts
SET password_hash = :newHash,
    password_version = password_version + 1
WHERE id = :userId
  AND tenant_id = :tenantId
  AND password_version = :expectedVersion
  AND password_hash = :expectedOldHash;
~~~

Only confirm the update when **affected row count = 1**. If `0`, the user may have been deleted/changed tenants, the password was reset, or another race occurred. Do not fall back to `UPDATE accounts SET password_hash = :newHash WHERE id = ...` just to "make it succeed", as that strips away concurrency protection.

**Atomic control:** `password_version` and the hash must be updated in the same transaction. Other password-changing operations (self-service change, admin reset, revocation due to compromise) must also increment the version or an equivalent security stamp to guard against stale operations.

**Version numbers and caching:** After commit, `UserDetails` cache invalidation must take effect; if replica lag or stale cache repopulation is possible, consider primary reads or version fencing. Never let a credential cache hold the same mutable `UserDetails` whose hash gets wiped by `eraseCredentials`.

### 8.3. What Outcome Should a Conflict Produce?

There is no single right handling for every application:

- **Strict policy:** reject the current login attempt and require re-authentication with the new password. Appropriate when an account reset or critical revocation just occurred.
- **Re-check policy:** load the fresh account record, re-verify the request's raw password and latest status/authorities, then decide whether to proceed. **Never** blindly retry overwriting with the old hash in a loop.
- **Accept-without-upgrade policy:** only when you can prove no security conflict exists (e.g., another request already upgraded using the exact same password/policy) and the app has enough context to verify; requires audit and race tests.

With `UserDetailsPasswordService`'s simple contract, a write failure may cause the login flow to fail or raise an internal error depending on the provider/filter. Do not silently "return user" after a failed database write and pretend "the hash was upgraded". You must align with your business consistency and security priorities.

## 9. UserDetailsPasswordService Differs from Regular Password Changes

### 9.1. Rehash-on-Login

- **Trigger:** successful username/password authentication.
- **Raw password:** just sent by the request and verified by the provider.
- **Semantics:** **keeps the same password the user knows**, merely replacing storage with a safer hash.
- **Target:** the account verified by `UserDetailsService`/provider.
- **Hook:** `UserDetailsPasswordService.updatePassword(user, encodedNew)`.
- **Experience:** users normally do not need to know a migration occurred.

### 9.2. User Self-Service Password Change

- **Trigger:** a logged-in user requests changing their password from rawOld to rawNew.
- **Safeguards:** re-verify oldPassword, MFA/step-up if needed, password policy checks, reuse prevention, CSRF/session cookies, audit.
- **Stored value:** hash computed from the **new password**, not rawOld.
- **Interface:** application-dependent; may use `UserDetailsManager.changePassword(oldPassword, encodedNew)` or a domain service.
- **Sessions/tokens:** may require invalidating other sessions and revoking refresh tokens per policy.

### 9.3. Reset Due to Forgotten Password / Compromise

- **Trigger:** recovery flow using a one-time token/verified ownership or an authorized admin.
- **Not required:** knowing the old password.
- **Requirements:** verifying recovery ownership, TTL, abuse prevention, auditing, session/refresh token revocation.
- **Caveat:** guard against races with rehash-on-login using version/CAS and strict revocation policies on account compromise.

| Criterion | Rehash-on-login | Change password | Reset password |
| --- | --- | --- | --- |
| Raw password used to encode | **Raw password from successful login** | **New raw password chosen by user** | **New raw password after recovery** |
| Does the user change their login secret? | **No** | **Yes** | **Yes** |
| Correct old password required? | Already verified at login | Usually requires reauth | No, but requires recovery proof |
| Store writer | `UserDetailsPasswordService` | `UserDetailsManager`/app service | Recovery service |
| Mandatory session/token management? | Per risk/policy | Per risk/policy | Should have explicit revocation workflow |
| Needs protection against stale overwrites? | **Crucial** | **Crucial** | **Crucial** |

Do not turn `updatePassword` logic into "self-service password change" just because of the similar method name. It is an **internal provider hook**, not a public API for clients to request password changes.

## 10. Interactions with PasswordEncoder Types and Migration Policies

### 10.1. Common Cases

| Stored data | Active encoder | Result on valid login with updater attached |
| --- | --- | --- |
| `{noop}legacy` | Default bcrypt delegating factory | Can match, signals upgrade, stores `{bcrypt}...` |
| `{pbkdf2}...` mapped format | Delegating with legacy PBKDF2 + default bcrypt | Matches if payload is valid, then rehashes to bcrypt |
| `{bcrypt}...` with configured cost | BCrypt/Delegating with same policy | `upgradeEncoding` usually false, no update |
| `{bcrypt}...` lower cost than new strength | BCrypt configured with higher strength | May return true, rehashes with new cost |
| No `{id}`, unrecognized format | Delegating without fallback | Usually fails match/throws, **does not auto-upgrade** |
| `{unknown}...` unmapped | Delegating without ID support | Must not force acceptance or bypass verification |
| Account using external IdP/LDAP | Provider other than DAO username/password | Does not run this hook by default |

Rows above depend on exact configuration/format and implementation; inspect your Spring Security version, mappings, and active encoders in the real application.

### 10.2. When Increasing bcrypt Strength

For example, `{bcrypt}` with cost 10 is stored, and you configure the bcrypt encoder with strength 12. Old BCrypt hashes embed their cost in the payload and can still be verified; BCrypt's `upgradeEncoding` can return true when the stored cost is lower than the new target.

When bumping cost, **you do not necessarily have to change the ID prefix** from `bcrypt` to a new ID. However, old and new nodes with differing configurations during a rolling deployment must understand the data and upgrade behavior without creating unnecessary rehash loops. Benchmark CPU cost under login load to prevent rehash-on-login from causing latency spikes/DoS during peak traffic.

### 10.3. Switching Algorithms

If migrating to Argon2/PBKDF2/scrypt, configure `DelegatingPasswordEncoder` with the new `idForEncode` and a map retaining legacy encoders **before** writing new hashes. Nodes in the cluster must be able to **read the new format** during the transition.

A common strategy is **dual-read, single-write**:

1. Deploy `matches` support for both old and new IDs across all nodes.
2. Once rollout is verified, switch `idForEncode` to the new ID.
3. As users log in successfully, the hook gradually stores new hashes.
4. Measure coverage; accounts that never return may need a password reset by a deadline.
5. After migration finishes and the rollback window closes, legacy encoders may be removed if policy allows.

**Never** remove old mappings while legacy accounts still rely on them unless you have a reset plan. **Never** enable `NoOpPasswordEncoder` as the policy for creating new passwords.

## 11. UserDetails Cache and Credential Erasure: A Subtle Trap

By default, `ProviderManager` executes `eraseCredentials()` on the authentication result if the object implements `CredentialsContainer`. Its goal is to strip raw credentials and sensitive secrets from authentication/session objects after login.

However, if the `UserDetails` placed into the principal **is the exact same object sitting in the cache**, credential erasure can wipe the password hash inside the cached entry. Subsequent logins with the valid raw password will then fail to match.

~~~text
Cache<UserDetails> holds object U(passwordHash)
                       |
                       +--> DaoAuthenticationProvider uses U
                                  |
                                  +--> Authentication.principal = U
                                  |
                                  v
                       ProviderManager.eraseCredentials()
                                  |
                                  v
                       U.password = null
                                  |
                                  v
                       Cache also holds U(password=null)
~~~

**During upgrades**, caching also carries the risk of holding stale hashes:

- The DB upgraded the hash, while the cache still holds the old hash and stale flags/state.
- Another login request might load the stale hash from cache and trigger a duplicate update or race with a password reset.
- If the updater returns the same cached object and the provider erases credentials, the cached hash becomes null.
- Distributed caches may retain stale copies on other nodes even after one node updates the database.

**Remediation:** Return a fresh `UserDetails` detached from the cached object, evict or version-fence the cache after commit, and design proper TTLs and transactions. In the demo, both loader and updater return fresh `User` copies to avoid losing the store's hash. Do not disable `eraseCredentialsAfterAuthentication` globally just to "fix" caching without evaluating the risk of keeping raw credentials longer in memory/sessions.

## 12. Storing Hashes in JDBC/JPA/LDAP

### JDBC/JPA

For self-managed account tables:

- Hashes are one-way data generated by `PasswordEncoder`, e.g., with the `{bcrypt}` prefix.
- The column must be wide enough for every format you plan to support, avoiding truncated hashes. `VARCHAR(255)` is just a common suggestion; size it according to formats, schema, and future needs.
- The store must guarantee `UserDetailsService` reads **the exact value** just written.
- Use a stable ID and verified tenant scope for updates; avoid display usernames that might change between login and commit.
- Implement transactions, version/CAS, conflict handling, and auditing; never log raw passwords or hashes.
- If using a JPA entity with optimistic locking (`@Version`), verify semantics: updating an older entity must not overwrite roles/flags changed concurrently; a dedicated update scoped to password version may be safer.
- If reads go to a database replica, account for replication lag so you do not re-authenticate/rehash against a stale snapshot.

### LDAP or External IdPs

Do not assume LDAP/IdPs support reading hashes out and writing them back with JDBC-like semantics. An external identity provider may not expose raw hashes to your app or allow password changes via `UserDetailsPasswordService`. When using LDAP bind or OIDC, the primary authentication path is **different from DaoAuthenticationProvider reading local password hashes**, so rehash-on-login as described here does not automatically apply.

Internal domain accounts may store an extra local password for a specific flow; clearly delineate the source of truth and avoid "copying passwords" from an IdP without authorization and proper security design.

## 13. Symptoms, Likely Causes, and Troubleshooting

| Symptom | Likely cause | What to check |
| --- | --- | --- |
| Login succeeds, `{noop}` hash remains | `UserDetailsPasswordService` not attached or another provider handled login | Inspect active provider, `setUserDetailsPasswordService` wiring, store readback |
| `upgradeEncoding` is true but no UPDATE runs | Encoder called directly without write hook, transaction error, or unused bean | Check hook wiring, SQL affected rows, commit, and runtime errors |
| New password fails login after update | `newPassword` double-encoded or hash truncated/corrupted | Confirm `newPassword` is already encoded, avoid re-encoding, check DB string integrity |
| Legacy hash lacks `{id}` prefix | Delegating encoder cannot pick an encoder | Migrate metadata with right algorithm or reset password; no arbitrary fallback |
| Unknown ID throws exception | Node lacks mapping due to unsynchronized rollout | Deploy dual-read, check version/map and stored data |
| First login works, second fails with cache | Credential erasure nulled shared object's hash | Copy `UserDetails`, invalidate cache, test repeated logins |
| After password reset, old password works again | Rehash-on-login overwrote new password from stale request | Enforce CAS/password version/transactions and conflict policy |
| Role/locked flag reverts to old state | Full entity overwritten from stale snapshot | Update only password hash/version, preserve account state |
| Login CPU/latency spikes after rollout | Algorithm/cost change triggered mass rehashing | Benchmark, monitor SLOs/capacity, tune rollout/rate limits |
| No hash upgrade during JWT login | DAO username/password flow is not invoked | Inspect the actual auth mechanism; do not apply the wrong tool to the protocol |
| Locked account fails login and hash stays unchanged | Expected behavior | Never rehash from a request that fails account checks |
| Update adapter returns null | Violates `UserDetails` return contract | Return valid object with new password hash; add integration tests |
| Migration lacks tenant scope | Wrongly updates another tenant's account with same username | Use stable userId + verified tenantId |
| Hashes remain weak for inactive users | Rehash-on-login only affects returning users | Set reset deadlines and retire legacy encoders |
| Detailed exception leaks in response | Internal password reason/format exposed | Return generic public errors, log safely for audit |

## 14. Meaningful Testing

### Unit: Encoder

- `matches(raw, storedLegacy)` succeeds for legacy formats you **genuinely** support.
- `upgradeEncoding(storedLegacy)` is true; `upgradeEncoding(newHash)` is false under the same policy/cost.
- `encode(raw)` produces the new format and `matches(raw, encode(raw))` is true.
- Missing/unmapped IDs follow policy cleanly without silently falling back to plaintext.
- `PasswordEncoder` never logs raw/hash values and never generates new hashes with fast digests.

### Integration: Provider + Password Updater

1. Seed account with legacy hash, right password, account enabled/unlocked.
2. Login with wrong password: `updatePassword` not called, hash unchanged, not authenticated.
3. Login with right password: `updatePassword` called once, new hash persisted, matches raw password, authorities/flags preserved.
4. Next login: no re-update when hash already satisfies policy.
5. Without updater attached: login may succeed but hash is not automatically saved.
6. Disabled/locked/expired account: no rehash and not authenticated.
7. Updater throws error / DB timeout: no false success; enforce failure policy.
8. Password reset racing with rehash: new hash from reset is never overwritten by hash of old password.
9. Cached user & credentials erasure: repeated logins still succeed, cache keeps valid hashes, invalidation works.
10. Multiple SecurityFilterChain/AuthenticationManager setups: verify **the intended provider** is invoked.
11. Multiple nodes: deploy support for new ID cluster-wide before creating new hashes; replica lag causes no errors.
12. Verify SQL affected rows = 1 and `password_version` increments properly.

### Operations

- Metrics for `upgradeEncoding == true` and `updatePassword` successes/failures by algorithm ID without password hashes.
- Percentage of accounts still on legacy hashes, upgrade progress, long-inactive users, mandatory resets.
- Login p95/p99 latency and encoder CPU/memory under increasing workload.
- CAS conflict counts and ability to roll back without reactivating old passwords.
- Minimal audit trail: internal accountId, upgrade reason, before/after encoder-id, version, request ID (no credentials).
- Secret hygiene tests across all environments: stdout/logs never print raw passwords, encoded hashes, session cookies, or bearer tokens.

**Test through the real login flow** (`SecurityFilterChain`/`AuthenticationManager`), not just a unit test on a service bean. If `DaoAuthenticationProvider` is wired but the filter actually runs a different provider, migration will not trigger.

## 15. Pre-Production Design Checklist

1. Identified the **primary hash store**, algorithm policy, cost, and legacy/new version IDs.
2. `PasswordEncoder` used across **registration, password change, and login** shares compatible mappings and a unified creation policy.
3. Implemented `UserDetailsPasswordService` to persist the **encoded hash** as-is without double-encoding.
4. Configured the password service on the **actual DaoAuthenticationProvider** inside the right chain/manager.
5. Locked, disabled, expired, credentials-expired, and compromised-password checks remain enforced; failures never rehash.
6. Never rely on reading `principal.getPassword()` after login; query the store back to verify persistence.
7. Hash updates use **transactions + CAS/versioning** so concurrent resets/changes are never overwritten.
8. The adapter updates only hash and metadata without overwriting roles, tenant, status, or domain profile.
9. `UserDetails` cache is invalidated after commit; principals do not share mutable credential containers with the cache.
10. Account locks, password changes, and incidents have dedicated session/token revocation policies separate from rehash-on-login.
11. Database columns are wide enough and never truncate `{id}` prefixes, salts, costs, or payloads.
12. Rolling deploy: every node can read the new format **before** any node writes the new format.
13. Auditing, metrics, rollback plan, legacy support deadlines, and resets for non-returning users are defined.
14. Benchmarked encode/matches speed under real load; costs do not exceed resources or induce DoS.
15. Never log hashes/raw passwords, and never leak algorithm details or account status in public login errors.

## 16. Self-Check Questions

**Question 1.** Why does Spring Security need `UserDetailsPasswordService` if `PasswordEncoder` already exists?  
**Answer:** The encoder only creates/verifies hashes and evaluates upgrade need; it does not know which database to write to. The password service provides the update operation against the account store.

**Question 2.** Does `updatePassword(user, newPassword)` receive a raw or encoded password?  
**Answer:** An **encoded password** created by the encoder, not raw. Never encode it again in the implementation.

**Question 3.** `upgradeEncoding("{noop}legacy")` returns true. Can you update the hash immediately before checking the password?  
**Answer:** No. The provider must verify the raw password and account status first; only rehash after credentials are valid.

**Question 4.** Login with `{noop}` succeeds, yet `{noop}` stays in the DB. Is that a contradiction?  
**Answer:** No. You may be using an encoder that understands legacy formats without configuring `UserDetailsPasswordService`, or the filter is hitting a different provider.

**Question 5.** Why is returning the new `UserDetails` useful?  
**Answer:** The contract requires the updated object; it also avoids sharing a mutable principal with the cache/store where `eraseCredentials` could wipe the hash.

**Question 6.** A login request and a password reset request run concurrently; why is an unconditional UPDATE dangerous?  
**Answer:** Rehashing the old raw password could overwrite the new hash created by the reset, reviving the old password. CAS/versioning and a conflict policy are required.

**Question 7.** Are all users upgraded immediately upon deploying the new encoder?  
**Answer:** No. Only users who log in through the hooked flow and meet conditions get upgraded; inactive users may require a reset.

**Question 8.** Can `UserDetailsManager.changePassword` completely replace this hook?  
**Answer:** They should not be equated. `changePassword` belongs to a user changing their own password; `updatePassword` is an internal hook updating **the hash of an already-verified password** after login.

**Question 9.** Can a bcrypt hash that already has the `{bcrypt}` ID still need an upgrade?  
**Answer:** Yes. When its work factor is lower than the new configuration, `BCryptPasswordEncoder.upgradeEncoding` can request a rehash even though the ID stays the same.

**Question 10.** After rehashing, must all sessions/JWTs be logged out?  
**Answer:** There is no mandatory rule from the hook itself. Rehashing only changes how the same password is stored; session/token revocation is a separate policy. If compromise/reset is suspected, separate revocation is warranted.

## 17. References

- [Spring Security 6.5 – DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): `UserDetailsService`, `PasswordEncoder`, and the username/password authentication flow.
- [DaoAuthenticationProvider API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html): `setUserDetailsPasswordService`, `createSuccessAuthentication`, and password encoder configuration.
- [UserDetailsPasswordService API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetailsPasswordService.html): `updatePassword(UserDetails,String)` method and definition of "encoded password".
- [InMemoryUserDetailsManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/provisioning/InMemoryUserDetailsManager.html): implementation supporting both `UserDetailsService` and `UserDetailsPasswordService` for demos/tests.
- [Spring Security 6.5 – Password Storage](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html): `DelegatingPasswordEncoder`, `{id}encodedPassword` format, adaptive hashing, and work factor.
- [PasswordEncoder API 6.5](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/crypto/password/PasswordEncoder.html): `encode`, `matches`, `upgradeEncoding`.
- [Spring Security – Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `ProviderManager` and credential protection.
- [OWASP – Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): password hashing, work factor, legacy migration, and algorithm upgrades.

**Takeaway:** A reliable rehash-on-login cycle requires **successful password verification → `upgradeEncoding` signaling an upgrade → `encode(valid raw)` → `UserDetailsPasswordService.updatePassword(user, encodedNew)` → conditional save/commit and proper cache invalidation**. Upgrading a hash does not change the user's password; the biggest hazards are confusing raw vs. encoded values, forgetting to attach the updater, or overwriting a newer password due to a race condition.
