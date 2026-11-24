# UserDetails Caching and Refreshing Data After Account Changes

> **Context:** Spring Security — authentication, **User Contract** group. This lesson focuses on how `UserDetails` can be cached during username/password authentication, which data becomes stale after account changes, how to proactively refresh/evict caches, and why clearing a cache **does not mean** revoking issued sessions or access tokens. Standalone runnable examples use Java 17, Spring Security 6.3.x, and Gradle.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish `UserDetails`, `UserDetailsService`, `UserCache`, `CachingUserDetailsService`, `Authentication`, `SecurityContext`, and login tokens/sessions.
2. Accurately describe how `DaoAuthenticationProvider` and `AbstractUserDetailsAuthenticationProvider` retrieve data from cache, check credentials, and handle password mismatches.
3. Understand the `NullUserCache` default: **Spring Security does not automatically enable an effective `UserDetails` cache for every application**.
4. Predict the impact of password changes, account locks/unlocks, user deletion, role/authority updates, tenant changes, or account expiration when a stale `UserDetails` copy exists.
5. Proactively use `UserCache.removeUserFromCache(username)`, update the right cache layer post-transaction, and design multi-instance strategies.
6. Understand why cache invalidation does not automatically update `Authentication` in active sessions, remember-me tokens, or circulating JWT claims.
7. Run a Java 17 example using `DaoAuthenticationProvider` with intentional caching; observe user load counts and outcomes before/after eviction.

## 2. What Does UserDetails Contain, and Why Cache It?

In the username/password authentication model, `UserDetailsService.loadUserByUsername(username)` returns a `UserDetails` so the provider has data to verify against. `UserDetails` typically describes:

- The identifying username in the account store.
- The **encoded/hashed** password for `PasswordEncoder` to check the submitted password.
- Status flags such as `isEnabled()`, `isAccountNonLocked()`, `isAccountNonExpired()`, and `isCredentialsNonExpired()`.
- The set of `GrantedAuthority` instances representing roles/permissions per the application's mapping mechanism.

The authoritative store may live in a database, LDAP, or an identity service. Every call to `loadUserByUsername` can cost a DB query or network request. Caching `UserDetails` reduces lookup overhead when **repeated authentications** need the same account data.

However, `UserDetails` is **a snapshot of the account at load time**. If the authoritative source changes after caching, the snapshot may still hold an old password hash, lock status, or authorities. This behavior must be managed explicitly, especially when changing permissions or when admins lock accounts.

### Two-Data-Source Diagram

~~~mermaid
flowchart LR
    R["Authentication request"] --> P["DaoAuthenticationProvider"]
    P --> C{"UserCache has username?"}
    C -->|Hit| U["Cached UserDetails"]
    C -->|Miss| S["UserDetailsService"]
    S --> DB["Authoritative account store"]
    S --> U2["Fresh UserDetails"]
    U2 --> C2["May store in UserCache"]
    U --> V["Check status and password"]
    C2 --> V
    V --> A["Authentication success or exception"]
~~~

The diagram illustrates the main path. On a **cache hit with a password mismatch**, the standard provider can **reload `UserDetailsService` to retry** in case the password recently changed. That special behavior is analyzed in section 4.

## 3. Four Easily Confused State Layers

| Layer | What Does It Store? | How Long Does It Live? | Do Account Changes Auto-Update It? |
| --- | --- | --- | --- |
| **Account data store** | Authoritative username, password hash, enabled/locked, authorities, tenant | Per business transactions | This is where changes are recorded |
| **`UserCache` or `UserDetailsService` cache** | Recently loaded `UserDetails` (may hold password hash and authorities) | Until eviction, expiration/TTL, or memory failure | **No guarantee of auto-refresh** when DB changes |
| **`Authentication` in `SecurityContext`** | Principal, authentication state, chosen authorities | Typically per HTTP request or session | Does not change merely because `UserCache` was cleared |
| **Issued access token/JWT** | Claims, subject, scope/roles, issuer, audience, expiration | Per token lifetime and applied revocation controls | Self-contained JWTs do not rewrite claims when DB/cache changes |

**Four separate questions:**
1. "Has the database updated?"
2. "Does a **new** authentication fetch fresh `UserDetails`?"
3. "Do active sessions still retain old authorities?"
4. "Do APIs still accept previously issued tokens?"

Clearing `UserCache` answers **primarily question 2**. Never advertise cache eviction as "logging everyone out", "revoking tokens", or "making permission changes take effect immediately on all requests".

### `Authentication` vs. `UserDetails`

The resulting `Authentication` can hold `UserDetails` as `principal` and keep a **copy of authorities** from authentication time. Even when a later authentication returns new authorities, an old `Authentication` saved in a session is not necessarily replaced. In apps using `SessionCreationPolicy.STATELESS` and HTTP Basic, credentials are sent on every request so `DaoAuthenticationProvider` usually runs repeatedly, making `UserDetails` caching have a more direct impact.

## 4. Spring Security Default: Caching Is Not Enabled Automatically

`AbstractUserDetailsAuthenticationProvider` (the superclass of `DaoAuthenticationProvider`) integrates the `UserCache` interface to look up/store/remove `UserDetails`. **The default is `NullUserCache`**, meaning lookups never produce an effective cache hit; each username/password authentication through the provider typically queries `UserDetailsService`. The reason: in session-based web apps, `SecurityContext` is normally restored from the session without re-verifying passwords on every request.

Key APIs:

~~~java
public interface UserCache {
    UserDetails getUserFromCache(String username);
    void putUserInCache(UserDetails user);
    void removeUserFromCache(String username);
}
~~~

This is a **simplified API signature** (not the library's full source).

- `getUserFromCache(username)`: returns the cached snapshot or `null` if absent/expired.
- `putUserInCache(user)`: stores a snapshot typically keyed by `user.getUsername()`.
- `removeUserFromCache(username)`: removes the matching snapshot; does not alter the DB and does not touch sessions.

To enable real caching, explicitly configure `provider.setUserCache(...)` with a cache implementation—for instance, `SpringCacheBasedUserCache` delegates operations to Spring Cache (`Cache`). Spring Cache supports various backends, each offering different guarantees around TTL, eviction, consistency, and multi-node behavior.

**Do not confuse `CachingUserDetailsService` with the provider's `UserCache`:**

- `CachingUserDetailsService` wraps a `UserDetailsService` and has its own `setUserCache(...)`; by default this wrapper also starts with `NullUserCache`.
- `AbstractUserDetailsAuthenticationProvider.setUserCache(...)` caches at **the provider step** before needing to call `UserDetailsService`.
- If an app configures **both cache layers**, know exactly which layer holds snapshots and invalidate **all relevant layers** when an account changes. Evicting at the provider while the `CachingUserDetailsService` wrapper retains an old snapshot can still return stale data on reload.

**Learning architecture recommendation:** start with **one cache with clear ownership**. Only add a second cache after measuring performance and designing a consistent state-sync strategy.

## 5. Cache Lifecycle During an Authentication

Below is the common flow with `DaoAuthenticationProvider` and an active cache:

~~~text
1. Filter creates an unauthenticated UsernamePasswordAuthenticationToken.
2. Provider checks UserCache by username.
3. Cache miss:
   - loadUserByUsername(username) from data source;
   - check account status flags and credentials;
   - if successful, may call putUserInCache(UserDetails).
4. Cache hit:
   - use UserDetails snapshot from cache;
   - check status and password against snapshot;
   - if credentials mismatch, standard provider has a path to reload user and retry.
5. If authentication succeeds, return Authentication result with authorities.
6. ProviderManager may call eraseCredentials() on result after success.
7. Filter/caller decides whether to save result into SecurityContext.
~~~

### 5.1. A Cache Hit Does Not Mean Skipping Password Checks

Caching `UserDetails` **is not "already logged in"**. Under `DaoAuthenticationProvider`, whenever a new authentication runs, `PasswordEncoder.matches(rawPassword, cachedEncodedPassword)` must still succeed. Never write a custom provider that merely checks "username exists in cache" and returns authenticated.

### 5.2. Cache Miss and Wrong Password

The provider can load `UserDetails` and then detect a wrong password. Authentication fails and emits no authenticated result. Never treat caching a password hash as proof of authentication.

### 5.3. Cache Hit with Credential Mismatch: Reload May Happen

`AbstractUserDetailsAuthenticationProvider` has a mechanism **to retry loading the user via `UserDetailsService`** when an `AuthenticationException` occurs during checks using a cached `UserDetails`. A key goal is avoiding falsely rejecting a **recently changed password** solely because of a stale cached hash.

For example:

- Cache still holds the hash for the **old** password.
- The authoritative store just updated to the hash of the **new** password.
- The user tries the **new** password → fails against the old cached hash → the provider can load the fresh authoritative record and check again → succeeds if status and policy are valid.

**However, the reverse direction is unsafe without invalidation:**

- Cache still holds the old hash.
- The user tries the **old** password → immediately matches the hash in the cache → the provider can authenticate successfully **without hitting the DB**.
- Therefore, reloading on cache mismatch **does not replace** evicting the cache when a password changes.

This nuance is easy to miss if you only test "new password logs in" without testing "old password is definitely rejected".

### 5.4. Cache Hit and Newly Locked Account

If the old snapshot still has `enabled=true` while the authoritative store has set `enabled=false`, a request with cache-matching credentials can pass checks on **stale status**. The provider has no way to know the DB changed while the snapshot remains valid in cache.

Thus, sensitive updates such as **disabling, locking, revoking, changing roles, and changing passwords** require invalidation paths or a fresher status-check layer matching the desired assurance level.

## 6. How Should Account Changes Be Handled?

| Change in Authoritative Store | Risk with Cached UserDetails | Mandatory or Recommended Action |
| --- | --- | --- |
| Password change | Cache keeps old hash; old password may continue being accepted | Evict stale snapshot immediately; define policy for existing sessions/tokens |
| Account lock (`accountNonLocked=false`) | New requests may still see account unlocked | Evict; consider revoking sessions/tokens if lock must take effect immediately |
| Disable (`enabled=false`) | Cache may still show enabled | Evict; check active sessions and resources to block |
| Role/authority change | New logins may receive old roles | Evict; update policies for active sessions/tokens |
| Tenant permission removal | Cache or old `Authentication` may carry invalid tenant access | Evict cache, add trusted resource-level checks; handle sessions/tokens |
| Account deletion | Cache retains user copy despite deletion from store | Evict and invalidate related access states |
| Username/key rename | Old entry stays under old username key | Evict **both old and new keys** per actual identity logic; avoid confusing two identities |
| MFA reset or assurance change | Cached UserDetails cannot represent full MFA evidence | Revoke/step-up across sessions, IdP, and policy; do not merely evict UserDetails |
| Display-only profile edits | May display old name/email | Decide whether to tolerate brief delay or refresh on display |

**Change ownership matters:** if admin UIs, background jobs, LDAP syncs, and IdP webhooks can all modify accounts, every write path must have matching invalidation rules. If only the "change password" controller evicts the cache while a role-sync job does not, the system still has a stale-data window.

## 7. Invalidation Is Part of Account Update Business Logic

A useful rule of thumb:

> **Once an account update is confirmed at the authoritative source, new authentications must be designed to observe state consistent with the system's security guarantees.**

### 7.1. Why Does "Write DB → Evict Cache" Order Matter?

Suppose code deletes the cache **before** the change commits, and a concurrent request loads the user with old data from the DB and repopulates the cache. Then the new commit finishes while the cache holds the stale version. This is a classic race condition.

A straightforward path with a transactional store:

~~~text
BEGIN TRANSACTION
  UPDATE account SET enabled = false WHERE id = ...
COMMIT succeeds
  -> evict/refresh account cache entry
  -> notify relevant cache instances/regions if any
  -> enforce session/token revocation policy as required
~~~

**Note:** issuing eviction **after commit** reduces the chance of repopulating the cache with uncommitted data. Still, a brief window exists between commit and eviction, and events can be lost or delayed. For systems requiring immediate locking, stronger guarantees are needed (such as per-request version/revocation checks, reliable distributed mechanisms, and fail-closed policies), rather than relying solely on best-effort events.

### 7.2. Centralized Cache Updates in Application Services

Pseudocode style (not a standalone Java program):

~~~java
@Transactional
public void changeUserRole(String username, String newRole) {
    repository.updateRole(username, newRole);
    domainEvents.publish(new AccountChanged(username));
}

// Post-commit listener running in the same application:
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(AccountChanged event) {
    userCache.removeUserFromCache(event.username());
}
~~~

Variables `repository`, `domainEvents`, and `userCache` are configured dependencies; `AccountChanged` is an application-defined event. This snippet **illustrates timing**; it needs imports, constructors/DI, transactional event publication, and tests. `@TransactionalEventListener` runs after commit when the event is published inside an active transaction; **it does not build a durable distributed event bus** and does not guarantee other processes have evicted.

If updates occur in external systems (IdP/LDAP) without a shared DB transaction, design event/outbox pipelines, retries/idempotency, and separate reconciliation. For strong security demands, access state may need syncing via a consistent version/revocation source on every request.

### 7.3. Evict or Update Cache Directly?

- **Evict** is usually easier to keep safe: on the next authentication, the provider reloads the canonical record from `UserDetailsService`.
- **Direct update** can reduce cache misses, yet you must ensure the new snapshot carries **all** accurate account state and older events cannot overwrite newer ones.
- **TTL** is a second line of defense, not a substitute for active eviction on password changes or account locks.
- **Version stamps** (e.g., `accountVersion`/`securityVersion`) help detect stale data; merely storing a version in cache without checking an authoritative version does **not** guarantee freshness.

### 7.4. Multiple Replicas/Microservices

With JVM-local caches, `removeUserFromCache` on instance A **does not clear entries on B and C**. Common options:

1. Use a distributed cache with proper invalidation and protected access controls.
2. Broadcast account-changed/revoked events to all instances, with retries, idempotency, and missed-event detection.
3. Use short lifetimes, version checks, or revocation status from a trusted source for sensitive operations.
4. Reduce or disable caching on authentication paths demanding strong consistency.

Even shared caches require understanding consistency, replication lag, cache stampedes, and update races. Never claim "invalidated" if only one instance received the event. Monitor metrics for cache hits/misses, evictions, and time-to-effect for new state.

## 8. Java 17 Demo: Cache Hit, Stale Role, Account Lock, Password Change

This example runs as a **Java console** program, using a real `DaoAuthenticationProvider` to verify BCrypt hashes, `SpringCacheBasedUserCache`, and `ConcurrentMapCache`. It **omits Spring MVC/SecurityFilterChain** because the goal is observing the `UserDetails` contract at the provider in isolation.

Notably, we call `provider.setForcePrincipalAsString(true)` so the `Authentication` result uses a **String username** as principal in the demo, avoiding holding a direct reference to the cached `UserDetails` object when `ProviderManager` erases credentials. That is an intentional experimental choice; real apps often want `UserDetails` as the principal and need proper copying/credential-erasure handling.

### 8.1. Project Structure

~~~text
user-details-cache-lab/
├── settings.gradle
├── build.gradle
└── src/main/java/example/usercache/
    └── UserCacheLab.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'user-details-cache-lab'
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
    implementation 'org.springframework.security:spring-security-core:6.3.5'
    implementation 'org.springframework.security:spring-security-crypto:6.3.5'
    implementation 'org.springframework:spring-context:6.1.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.usercache.UserCacheLab'
}
~~~

Versions are pinned solely for the demo environment. In real Spring Boot apps, prefer compatible dependency management/BOMs and proper security patches rather than arbitrarily mixing framework versions.

### 8.2. Complete UserCacheLab.java

`src/main/java/example/usercache/UserCacheLab.java`:

~~~java
package example.usercache;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserCache;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.core.userdetails.cache.SpringCacheBasedUserCache;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

public class UserCacheLab {

    // Immutable snapshot simulating a database row.
    record Account(
            String username, String encodedPassword, boolean enabled,
            List<String> authorities) {}

    static final class AccountStore implements UserDetailsService {
        private final Map<String, Account> accounts =
                new ConcurrentHashMap<>();
        private final AtomicInteger loads = new AtomicInteger();
        private final PasswordEncoder encoder;

        AccountStore(PasswordEncoder encoder) {
            this.encoder = encoder;
            accounts.put("lan", new Account(
                    "lan", encoder.encode("old-pass"), true,
                    List.of("reports.read")));
        }

        @Override
        public UserDetails loadUserByUsername(String username)
                throws UsernameNotFoundException {
            loads.incrementAndGet();
            Account account = accounts.get(username);
            if (account == null) {
                throw new UsernameNotFoundException("Unknown user");
            }
            return User.withUsername(account.username())
                    .password(account.encodedPassword())
                    .disabled(!account.enabled())
                    .authorities(account.authorities()
                            .toArray(String[]::new))
                    .build();
        }

        int loadCount() {
            return loads.get();
        }

        // Each simulated change committed to the authoritative store.
        void changeAuthority(String username, String authority) {
            accounts.computeIfPresent(username, (key, old) ->
                    new Account(old.username(), old.encodedPassword(),
                            old.enabled(), List.of(authority)));
        }

        void setEnabled(String username, boolean enabled) {
            accounts.computeIfPresent(username, (key, old) ->
                    new Account(old.username(), old.encodedPassword(),
                            enabled, old.authorities()));
        }

        void changePassword(String username, String rawNewPassword) {
            String encoded = encoder.encode(rawNewPassword);
            accounts.computeIfPresent(username, (key, old) ->
                    new Account(old.username(), encoded,
                            old.enabled(), old.authorities()));
        }
    }

    static void attempt(
            String label, AuthenticationManager manager,
            AccountStore store, String password) {
        Authentication input =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        "lan", password);

        try {
            Authentication result = manager.authenticate(input);
            List<String> authorities = result.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList();
            System.out.println(label + " => OK "
                    + authorities + " loads=" + store.loadCount());
        }
        catch (AuthenticationException ex) {
            System.out.println(label + " => "
                    + ex.getClass().getSimpleName()
                    + " loads=" + store.loadCount());
        }
    }

    public static void main(String[] args) {
        PasswordEncoder encoder = new BCryptPasswordEncoder();
        AccountStore store = new AccountStore(encoder);
        UserCache cache = new SpringCacheBasedUserCache(
                new ConcurrentMapCache("user-details"));

        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider();
        provider.setUserDetailsService(store);
        provider.setPasswordEncoder(encoder);
        provider.setUserCache(cache);

        // Demo only: principal is username String to avoid sharing the
        // same UserDetails instance with the cache when manager erases credentials.
        provider.setForcePrincipalAsString(true);

        AuthenticationManager manager =
                new ProviderManager(List.of(provider));

        attempt("first-login", manager, store, "old-pass");
        attempt("cached-login", manager, store, "old-pass");

        store.changeAuthority("lan", "reports.admin");
        attempt("role-changed-without-evict",
                manager, store, "old-pass");

        cache.removeUserFromCache("lan");
        attempt("role-after-evict",
                manager, store, "old-pass");

        store.setEnabled("lan", false);
        attempt("disabled-without-evict",
                manager, store, "old-pass");

        cache.removeUserFromCache("lan");
        attempt("disabled-after-evict",
                manager, store, "old-pass");

        store.setEnabled("lan", true);
        store.changePassword("lan", "new-pass");
        cache.removeUserFromCache("lan");
        attempt("old-password-after-evict",
                manager, store, "old-pass");
        attempt("new-password",
                manager, store, "new-pass");

        store.changePassword("lan", "latest-pass");
        attempt("previous-password-with-stale-cache",
                manager, store, "new-pass");

        cache.removeUserFromCache("lan");
        attempt("previous-password-after-evict",
                manager, store, "new-pass");
        attempt("latest-password",
                manager, store, "latest-pass");
    }
}
~~~

**Why does this code accurately reflect cache behavior?**

- `AccountStore` is the simulated **source of truth**: every `loadUserByUsername` increments the `loads` counter.
- Every `loadUserByUsername` call returns a **fresh `UserDetails` snapshot** matching the current `Account`, rather than an object silently mutable from elsewhere.
- `SpringCacheBasedUserCache` stores snapshots in `ConcurrentMapCache`. This is a **local demo cache**, without TTL/multi-node/transactions or production security guarantees.
- Real `DaoAuthenticationProvider` checks BCrypt and account status. No fake "accept all" provider.
- `ProviderManager` erases credentials in the resulting `Authentication` by default if supported; `setForcePrincipalAsString(true)` prevents the cached `UserDetails` instance itself from sitting in the demo's result principal.
- Role/disable/password changes are **intentionally run without eviction** in several steps to demonstrate the risk, followed by `removeUserFromCache("lan")` to retry.

### 8.3. Running the Program

From the `user-details-cache-lab` directory, using Java 17+ and compatible Gradle (or Gradle Wrapper):

~~~bash
gradle run --quiet
~~~

With Gradle Wrapper, use `./gradlew run --quiet`; on Windows you can use `.\gradlew.bat run --quiet`.

**Output of the `System.out.println` lines in `main`** (authoritative store loads measured via `loadCount`):

~~~text
first-login => OK [reports.read] loads=1
cached-login => OK [reports.read] loads=1
role-changed-without-evict => OK [reports.read] loads=1
role-after-evict => OK [reports.admin] loads=2
disabled-without-evict => OK [reports.admin] loads=2
disabled-after-evict => DisabledException loads=3
old-password-after-evict => BadCredentialsException loads=4
new-password => OK [reports.admin] loads=5
previous-password-with-stale-cache => OK [reports.admin] loads=5
previous-password-after-evict => BadCredentialsException loads=6
latest-password => OK [reports.admin] loads=7
~~~

**Interpreting each group of results:**

1. `first-login` loads the store once. `cached-login` uses the cached snapshot, yet **still checks the password against the cached hash**.
2. Changing the role in the store without touching the cache makes `role-changed-without-evict` still receive `reports.read` (the old role). After eviction, the new request gets `reports.admin`.
3. Disabling the account in the store without evicting lets `disabled-without-evict` still authenticate using the `enabled=true` snapshot. After eviction, `DaoAuthenticationProvider` throws `DisabledException`.
4. Changing password to `new-pass` and evicting: `old-pass` is rejected; `new-pass` is accepted.
5. Changing again to `latest-pass` **without evicting**, the snapshot still holds the `new-pass` hash. `new-pass` is still accepted on a new authentication; after eviction, the old password is rejected and `latest-pass` is accepted.

**Observation for learning:** counting loads measures cache hits/misses, **not** total BCrypt checks. With a right password on a cache hit, the provider may still verify the password. With a wrong password on a cache hit, the provider may reload from the authoritative store and re-check. Do not claim every failed attempt increments loads by exactly one across all configurations/custom providers.

### 8.4. Changing One Step to Test the Reload-on-Password-Mismatch Branch

After `new-password` succeeds and the cache holds the `new-pass` hash, you can run a scenario **changing the password to `latest-pass` without evicting**, then **trying `latest-pass` first** (unlike the current `main` order):

~~~java
store.changePassword("lan", "latest-pass");
// Not calling removeUserFromCache(...) yet
attempt("new-password-on-stale-cache",
        manager, store, "latest-pass");
~~~

The provider sees a cache hit, yet the old hash does not match `latest-pass`. Under standard `AbstractUserDetailsAuthenticationProvider`, it can load fresh data via `UserDetailsService` and authenticate with the new hash; thus the new password can work before eviction. **This does not prove the old cache was safely invalidated.** An essential follow-up test is retrying the old password to check whether revocation policy actually took effect.

The branch above is **a partial replacement snippet inside `main`**, not a second standalone program. Exact cache behavior depends on version and provider; if a custom provider alters the contract, re-verify.

## 9. Subtle Issue: eraseCredentials() Can Affect the Cache

`ProviderManager` defaults to `eraseCredentialsAfterAuthentication=true`. Upon receiving a successful result, it asks to erase credentials if the result implements `CredentialsContainer`. If the `Authentication` result has as its principal **the exact `UserDetails` instance sitting in the cache**, and the principal implements credential erasure, the snapshot's password hash can get wiped.

Easily overlooked scenario:

~~~text
UserDetailsService -> UserDetails instance U with passwordHash
UserCache stores the exact reference U
DaoAuthenticationProvider returns Authentication(principal = U)
ProviderManager calls eraseCredentials() on Authentication result
  -> may clear passwordHash inside U
Next authentication hits cache U with no hash left to check password
~~~

**Never solve this by disabling credential erasure by default in production.** Several strategies exist depending on needs:

- Skip caching `UserDetails` when lookup cost is acceptable; keep `NullUserCache`.
- Cache a separate snapshot and return **an appropriate copy** as the `Authentication` result's principal, so credential erasure does not touch the cached instance.
- When only the username string is needed, configure `setForcePrincipalAsString(true)` as in the demo; this **changes the principal type**, so do not apply it blindly in apps expecting `@AuthenticationPrincipal UserDetails`.
- If you truly must alter `eraseCredentialsAfterAuthentication`, thoroughly evaluate the risk of retaining credentials in memory, logs, and sessions; this is not the default choice.

Even though caches store hashes rather than raw passwords, hashes remain sensitive data. Protect cache memory/servers, operational access, and transport channels; avoid logging full `UserDetails` objects.

## 10. Sessions and JWTs Can Still Hold Stale Data After Eviction

### 10.1. Session-Based Applications

Browsers log in via form/OIDC, and sessions store `SecurityContext`. After an admin changes a role, clearing `UserCache` **does not automatically alter** authorities inside an existing session's `Authentication`. Subsequent requests can be served from the session without calling `UserDetailsService` again.

Approaches depending on needs:

- Invalidate/revoke the user's sessions after sensitive changes.
- Check `securityVersion` or latest account status on critical requests.
- Require re-login/step-up before sensitive actions.
- Decouple resource-level permission decisions from stale session roles.

A session management scheme must enforce revocation across **all relevant nodes or session stores**. Never promise "clearing UserCache logs out all sessions".

### 10.2. APIs Using JWT Bearer Access Tokens

A Resource Server can validate a JWT by signature, issuer, audience, and expiration **without calling `UserDetailsService` on every request**. Thus evicting `UserCache` may have **no effect whatsoever** on signed permissions inside an unexpired JWT.

If near-instant revocation is needed, consider short token lifetimes, introspection/opaque tokens, token revocation/denylist mechanisms, or checking `securityVersion` against a trusted status source on critical requests. Never assume `exp` means "revoked immediately when roles change".

### 10.3. Remember-Me and New Authentications

Remember-me uses cookies/tokens and can reload users when restoring logins, yet exact behavior depends on the remember-me service type, token store, and configuration. Invalidating the `UserDetails` cache only addresses **part of the data path**; you must also inspect remember-me revocation, session revocation, and credential reset mechanisms.

### 10.4. Role of Authorization

`UserDetails.getAuthorities()` is only one authority source at authentication time. Complex business rules often require checking permissions against resources, tenants, ownership, or the latest entitlements. A stale cached "ADMIN" role should never be the sole basis for high-impact decisions.

## 11. Cache Design: TTL, Consistency, Ownership, and Metrics

### 11.1. When Should You Enable It?

**May fit:** APIs receiving username/password on every request, slow remote/LDAP user sources, high lookup costs, and applications with clear invalidation paths.

**Think carefully or keep disabled:** session-based apps (which do not call the provider on every request), accounts with frequent status/permission changes, instant-revocation policies, or missing eviction hooks from all actors that can modify users.

**Measure** load counts, latency, and cache hit rates before adding a cache. Never sacrifice security state-freshness requirements just to save one query.

### 11.2. Cache Keys and Identity Scope

Standard `UserCache` looks up by `username`. In multi-tenant/realm/issuer systems where two different "alex" users can exist, design a user namespace to prevent cache collisions. Never assume a bare username string is globally unique. You may need normalized keys or a different cache layer with a composite key (`tenant, realm, subject`) and matching provider.

Never use a mutable email as a cache key without old-key migration/eviction rules. Never allow one tenant to read another tenant's `UserDetails` due to identical usernames.

### 11.3. TTL Is Not an Instant Revocation Mechanism

For example, a 5-minute TTL means snapshots can stay stale for nearly 5 minutes **without eviction**. For password resets or account disabling, that window may be unacceptable. Short TTLs bound maximum staleness under normal conditions, yet still require handling post-event cache reloads, clock sync, and failover policies.

### 11.4. Cache Observability and Security

Consider measuring:

- `user_cache_hit`, `user_cache_miss`, `user_cache_eviction`;
- `user_details_load_count` and user loading latency;
- delay from account-update commit until all critical authentication paths see the new value;
- failed invalidation events, event ordering, and cross-instance lag;
- authentication failure rates due to locked/disabled/bad credentials (preserve privacy; avoid logging raw usernames or secrets unnecessarily).

**Never log:** plaintext passwords, password hashes, bearer tokens, remember-me cookies, sensitive PII/claims, or full `UserDetails.toString()`. Caches can hold secret derivations; restrict read/write permissions and set appropriate retention limits.

## 12. Conditions That Must Not Be Missed in Testing

To ensure account updates take effect, testing only "cache misses are slower" is insufficient. Minimum cases:

| Test | Steps | Expectation |
| --- | --- | --- |
| Cache hit | Authenticate same username/password twice with cache on | `UserDetailsService` may load only once; both verify password |
| Role update **without** eviction | Cache role A, DB changes to role B, re-authenticate | May still get role A, demonstrating staleness risk |
| Role update **with** eviction | Cache role A, DB changes to B, evict, re-authenticate | Receives role B |
| Disable account | Cache enabled=true, DB disables, evict, authenticate | Rejected under new account status |
| Password reset | DB changes hash, evict, test old and new passwords | Old password rejected, new password succeeds |
| Mismatch reload branch | Cache old hash, DB changes to new hash without evict | New password may trigger reload; must still test old password |
| Concurrent update/cache fill | Simulate user load alongside commit + eviction | No stale snapshot living indefinitely; version/consistency safeguards present |
| Multi-instance | Update account on node A, authenticate on B/C | B/C also see new policy within SLA |
| Existing session | Change permissions and evict cache, use old session | Understand and test session refresh/revocation policy separately |
| Unexpired JWT | Change permissions and evict UserCache, send old JWT | Test token revocation/authorization policy separately |
| Cache credential erasure | Authenticate repeatedly in succession | Does not corrupt cached encoded password via shared principal reference |
| Key change/tenant | Rename username or same name in another tenant | Evict exact keys, no cross-realm principal confusion |

A valid cache test must actually invoke the **authentication provider with credentials**. `@WithMockUser` helps test authorization at another layer, yet bypasses `UserDetails` loading and `PasswordEncoder` so it cannot verify this cache.

## 13. Common Mistakes

1. **Assuming Spring Security always caches `UserDetails`.** Default `NullUserCache` creates no effective cache hits.
2. **Caching via `@Cacheable` without matching `@CacheEvict`.** Old roles/passwords/statuses linger after DB changes.
3. **Evicting before transaction commit.** Concurrent requests can reload stale data into the cache.
4. **Evicting on only one node.** Other replicas keep authenticating against stale cached snapshots.
5. **Thinking a new password logging in means the old password was revoked.** Fallback reload on mismatch does not secure the reverse direction.
6. **Testing only enabled accounts after clearing cache.** Forgetting to test cached `enabled=true` lingering on another node.
7. **Confusing `UserDetails` cache with sessions/JWTs.** Clearing cache does not alter saved/issued results.
8. **Caching the same principal object that undergoes `eraseCredentials`.** Can wipe the hash needed on the next authentication.
9. **Disabling `eraseCredentialsAfterAuthentication` unconditionally.** Retains credentials in objects longer than needed.
10. **Trusting TTL alone for immediate lockouts.** TTL still leaves a stale window and races.
11. **Letting two users from different tenants share the same username cache key.** Risks mixing up authorities and account status.
12. **Failing to distinguish provider cache from `UserDetailsService` cache.** Clearing one layer while the other serves stale snapshots.
13. **Caching `Authentication` as if it were a live account record.** `Authentication` holds one verification result and does not watch the DB.
14. **Updating roles while checking permissions only in the UI.** APIs must still enforce resource/tenant authorization via trusted policies.

## 14. Self-Check Questions

**Question 1:** Does `DaoAuthenticationProvider` cache every user through `UserCache` by default?  
**Answer:** No. `AbstractUserDetailsAuthenticationProvider` defaults to `NullUserCache`. You must configure a concrete cache to get real cache hits.

**Question 2:** After a password change, trying the new password can succeed even if the cache holds the old hash. Is eviction still required?  
**Answer:** Yes. On cache mismatch, the standard provider can load fresh data to authenticate; however, the old password **may still match the cached hash**. Evict and test rejecting the old password as well.

**Question 3:** An admin disables an account, yet a new request still logs in with the prior password. Where might the bug be?  
**Answer:** `UserCache` still holds an `enabled=true` snapshot, an instance missed eviction, or an old session/token remains valid. Check each layer and invalidation timing.

**Question 4:** After `removeUserFromCache("lan")`, a browser with an authenticated session can still view data. Is this necessarily a cache bug?  
**Answer:** No. The session may hold old `Authentication` and authorities without calling the provider again. You need session invalidation/refresh policies or fresh-state authorization checks if required.

**Question 5:** A system stores a signed JWT with role ADMIN, then changes the DB permission to USER and only evicts UserCache. Does the old JWT change roles automatically?  
**Answer:** No. Self-contained JWTs keep their signed claims until expiration or rejection by a verification/revocation mechanism; design that separately.

**Question 6:** Why must a cache hit still verify the password?  
**Answer:** Caches store account data, not proof that the caller authenticated. Every new username/password authentication must verify credentials.

**Question 7:** Does evicting cache post-commit eliminate all races?  
**Answer:** No. A window remains between commit and eviction, plus delayed/lost events, other replicas, and concurrent refills. Strict requirements need proper versioning/revocation/consistency controls.

**Question 8:** The cached principal is `UserDetails`, and post-authentication the password hash gets erased. What should you do?  
**Answer:** Inspect reference sharing and `eraseCredentials`; consider caching a separate snapshot, returning a principal copy, using a string principal when appropriate, or disabling caching. Never default to keeping raw/encoded credentials in results indefinitely.

**Question 9:** In multi-tenancy where username "alex" repeats, is caching purely by bare username enough?  
**Answer:** Not when usernames are not guaranteed unique across namespaces. Design appropriate identity/realm/tenant scoping and keys to avoid assigning the wrong authorities.

## 15. Production Application Checklist

Before enabling a `UserDetails` cache, confirm:

- **Right cache point:** at the provider, at `CachingUserDetailsService`, or both? Who owns it?
- **Right key:** is username unique across tenants/realms? Are renames supported?
- **Right data:** which hash, enabled, locked, expired, and authorities are in the snapshot?
- **Right update paths:** do all admin, user, sync, batch, and IdP flows emit invalidation signals?
- **Right commit order:** does DB commit succeed before eviction, and are races/lost events handled?
- **Right scope:** do all required cache replicas/regions see updates within the allowed SLA?
- **Right credential policy:** is the old password rejected after reset? Do account disables take effect within SLA?
- **Right session/token handling:** have you decided how existing sessions, remember-me tokens, and JWTs are handled?
- **Right lifecycle:** avoid erasing credentials on cached principals; are TTLs and eviction metrics in place?
- **Right tests:** include before/after eviction, concurrency, multi-node, session/JWT, and record-level authorization checks.

**Core takeaway:** `UserCache` optimizes **looking up user data for a new authentication**; it is not a mechanism for revoking all active access. When an account changes, update the authoritative source, actively refresh the right cache layers, and enforce appropriate session/token/resource-permission policies. A secure system must verify both questions: **"Does a new authentication see the new data?"** and **"Is existing access still permitted?"**

### Official Reference Documentation

- `UserCache` API, Spring Security 6.3: https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/core/userdetails/UserCache.html
- `AbstractUserDetailsAuthenticationProvider` (cache default, reload on mismatch): https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html
- `SpringCacheBasedUserCache`: https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/core/userdetails/cache/SpringCacheBasedUserCache.html
- `CachingUserDetailsService`: https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/authentication/CachingUserDetailsService.html
- `DaoAuthenticationProvider`: https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/passwords/dao-authentication-provider.html
- `UserDetails`: https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/passwords/user-details.html
