# UserDetails Caching and Handling Authority Changes and Account Locks in Spring Security Servlet

## 1. Why Is This a Security Concern, Not Just a Performance Optimization?

In Spring Security on the **Servlet stack** (Spring MVC, Servlet container, `SecurityFilterChain`), `UserDetailsService.loadUserByUsername(username)` typically reads account information from a database or an identity store. Repeatedly calling the data store carries a cost; caching can reduce login latency and query load.

However, cached data is not limited to a display name. A `UserDetails` typically contains a **hashed password, authorities/roles, enabled/locked flags, and account or credential expiration states**. When an administrator revokes privileges, locks an account, or a user changes their password, the cached copy can become **stale**. If the authentication pipeline still relies on the old copy, the system may permit an authentication attempt that ought to be blocked.

There is an additional independent issue: even after the `UserDetails` cache is cleared, **`Authentication` sitting in the `SecurityContext` of an already-logged-in session may still retain old authorities**. Therefore, you must distinguish:

1. Canonical account data (database / identity provider).
2. `UserDetails` and caches used during **authentication**.
3. `Authentication` already created and saved/restored via **session / security context**.
4. Self-contained access tokens (e.g., JWT), if the application also exposes stateless APIs.
5. Policies that check authorities or account locks **at request time**.

**Core thesis:** clearing the cache ensures **subsequent** data loads and authentications see the updated state. It **does not automatically revoke active login sessions or issued access tokens**.

After this lesson, you will be able to decide when to cache `UserDetails`, design consistent invalidation for role/lock/password changes, understand the consequences of multi-layer caching, and test updated permissions for both **next login** and **already-authenticated sessions**.

## 2. How Do `UserDetailsService`, `UserDetails`, and `Authentication` Differ?

On the Servlet stack with username/password, a common flow is:

```text
POST /login or request with HTTP Basic credentials
                  |
                  v
        Authentication filter
                  |
          AuthenticationManager
                  |
           DaoAuthenticationProvider
                  |
       UserCache (if configured)
          | miss           | hit
          v                |
   UserDetailsService      |
          |                |
   database/identity store |
          |                |
          +-------+--------+
                  |
        UserDetails + password hash
        + authorities + account status
                  |
     password verification + account status checks
                  |
           Authentication succeeded
                  |
           SecurityContextHolder
                  |
     session / request lifecycle (depends on config)
                  |
           AuthorizationFilter
```

The diagram shows the **functional flow**, without claiming every filter behaves identically across all mechanisms. `DaoAuthenticationProvider` is the familiar provider for `UserDetailsService`; OAuth2, JWT, or other authentication mechanisms have their own pipelines.

Distinguishing the objects:

| Object | Function | What can it contain? | When does it easily go stale? |
| --- | --- | --- | --- |
| Account in canonical data store | Source of truth | Enabled/locked states, password hash, roles, tenant, version | When replicas or uncommitted transactions exist |
| `UserDetailsService` | Loads user info by username | Returns `UserDetails`, may use repository or cache | If using `@Cacheable`, custom cache, or lagging read replicas |
| `UserCache` on provider | Reuses `UserDetails` across authentications | Previously loaded `UserDetails` | After role changes, account locks, password changes |
| `Authentication` | Authentication result of a principal | Principal and authorities snapshotted at authentication time | When account is modified after login |
| `SecurityContext` | Holds active `Authentication` | Request/session principal and authorities | Session stays alive without revalidation |
| Self-contained token | Attests state at issuance time | Claims such as `sub`, roles, `exp` | While old claims stay valid until expiry/revocation |

With session-based form login, Spring Security can restore `Authentication` from the session on the next request **without re-running `UserDetailsService`**. With HTTP Basic, each request typically resends credentials and authentication runs according to filter/context configuration; caching is a separate decision. Do not jump from "UserDetails is cached" to "every request reads the cache".

## 3. Where Are Account Status and Authorities Checked?

`UserDetails` describes not only identity but also account status:

```java
interface UserDetails {
    String getUsername();
    String getPassword();
    Collection<? extends GrantedAuthority> getAuthorities();

    boolean isEnabled();
    boolean isAccountNonLocked();
    boolean isAccountNonExpired();
    boolean isCredentialsNonExpired();
}
```

The snippet above is a **minimal learning signature**, not the full interface definition of a specific Spring Security version. When `DaoAuthenticationProvider` authenticates username/password, pre/post account checks in the `AbstractUserDetailsAuthenticationProvider` family can reject accounts failing these flags.

| Value | When `false` | Key meaning to remember |
| --- | --- | --- |
| `isEnabled()` | Account is disabled; typically raises `DisabledException` | Not `hasRole`; this is **account status** |
| `isAccountNonLocked()` | Account is locked; typically raises `LockedException` | Locks to block new authentications, not necessarily active sessions |
| `isAccountNonExpired()` | Account has expired; typically raises `AccountExpiredException` | Needs explicit expiry policy and re-activation flow |
| `isCredentialsNonExpired()` | Credentials expired; typically raises `CredentialsExpiredException` | Distinct from account expiration |
| `getAuthorities()` | Authority list changes | Not synonymous with account lock flag; authorities are evaluated during authorization |

In Spring Security, `hasRole("ADMIN")` usually checks authority `ROLE_ADMIN`; `hasAuthority("ROLE_ADMIN")` matches the authority string directly. When editing permissions, synchronize the **source data, caches, and authentication/sessions that need the new permissions**. When locking an account, also decide whether active sessions must lose access immediately or only starting at the next login.

Do not put a `locked=true` flag into a system that **only** stores roles expecting `DaoAuthenticationProvider` to know automatically. The provider needs `UserDetailsService` to return a `UserDetails` carrying the accurate status flags.

## 4. What Caches Exist?

### 4.1. `UserCache` on `DaoAuthenticationProvider`

The `AbstractUserDetailsAuthenticationProvider` family has a `UserCache` concept to store and retrieve `UserDetails` between authentication calls. Key interface operations:

```java
UserDetails getUserFromCache(String username);
void putUserInCache(UserDetails user);
void removeUserFromCache(String username);
```

These are **reference signatures**; only use them in code after importing `org.springframework.security.core.userdetails.UserCache`. Two implementations worth knowing:

- **`NullUserCache`**: stores nothing; this is the default choice of `AbstractUserDetailsAuthenticationProvider` in typical configurations.
- **`SpringCacheBasedUserCache`**: bridges `UserCache` with Spring's `org.springframework.cache.Cache` abstraction so a real cache implementation can be used.

If you want `DaoAuthenticationProvider` to cache `UserDetails`, you must explicitly configure a backing `UserCache`. Never claim "Spring Security always caches `UserDetails`" merely because you see `UserDetailsService` in the code.

Do not confuse the **provider's UserDetails cache** with **service/repository caching** or database caching. If two independent caches exist, clearing one cache **does not guarantee** the other cache returns fresh data.

### 4.2. Caching at `UserDetailsService`

An application can use `@Cacheable` or manual caching:

```java
// Illustrative fragment inside a Spring bean.
@Cacheable(cacheNames = "accountDetails", key = "#username")
public UserDetails loadUserByUsername(String username) {
    return accountRepository.findByUsername(username)
        .map(this::toUserDetails)
        .orElseThrow(() -> new UsernameNotFoundException("Not found"));
}
```

This requires a repository, caching configuration (`@EnableCaching` and `CacheManager` or equivalent), and calling the bean through a Spring proxy. This is **not a standalone program**. With Spring AOP caching, calling a `@Cacheable` method from another method in the **same bean** may bypass the proxy and not apply caching as expected.

Specifically, usernames should be **consistently normalized** before serving as cache keys if account policies are case-insensitive. Multi-tenant applications must include **tenant identity** in the key; caching solely by username `"admin"` when two tenants both have that user risks returning another tenant's `UserDetails`.

### 4.3. Caches on the Identity Provider or Persistence Layer

LDAP, distributed caches, DB second-level caches, or intermediate services can have their own synchronization delays. If multiple layers store user data, map out every layer, key, TTL, owner, and invalidation event. A `removeUserFromCache(username)` in JVM A does not automatically make fresh data appear in JVM B when using independent local caches.

## 5. Why Does Bad Caching Cause Real Incidents?

Suppose data in the database changes:

```text
t0: alice, ROLE_ADMIN, enabled=true, accountNonLocked=true
t1: Alice logs in successfully; UserDetails has ROLE_ADMIN.
t2: Admin revokes ROLE_ADMIN in the database.
t3: Alice logs in again, provider gets stale UserDetails from cache.
t4: Alice is still seen as having ROLE_ADMIN if stale data is used.
```

Or a similar scenario:

```text
t0: bob, accountNonLocked=true
t1: Bob logs in and has an active HTTP session.
t2: System locks bob, accountNonLocked=false.
t3: UserDetails cache is not evicted -> new authentications may read the old flag.
t4: Even after cache eviction, the session from t1 may still retain a valid Authentication.
```

Therefore, you must ask **two independent questions**:

1. *Do new authentication attempts receive updated data?* -> Ensure source-of-truth commits and invalidate/reload `UserDetails` properly.
2. *Are already-issued sessions/tokens subject to the new policy?* -> Design session revocation, token revocation, account-state re-checks, or request-time authorization policies.

If the security requirement is "revoke admin privileges within at most N seconds", merely adding `@CacheEvict` and hoping active requests magically swap authorities is **not enough**.

## 6. Cache, Role Changes, and Account Locks: Effect Matrix

| Action | Needs UserDetails cache handling? | Authentication in existing session? | Self-contained token with claims? |
| --- | --- | --- | --- |
| Grant `ROLE_REPORTER` | Evict/reload so next login picks up role | New role is usually **absent** until refresh/re-auth | Old claims lack new role |
| Revoke `ROLE_ADMIN` | Evict immediately per policy | May **retain old admin role** unless revalidated | Old role claim remains usable until expiry/revocation |
| Set `accountNonLocked=false` | Evict so new auth is rejected by pre-check | Existing session is **not auto-locked** | Existing access tokens do not vanish automatically |
| Set `enabled=false` | Evict/reload | Must decide and implement request-time revoke/check | Needs revocation, introspection, short TTL, or version check |
| Change password hash | Evict so new login checks new hash | Existing session may stay valid unless revoked | Old tokens may remain valid |
| Delete account | Evict cache and dependent data | May require session/remember-me invalidation | Needs token revocation policy |
| Change UI metadata unrelated to permissions | Depends on what is cached | Does not necessarily revoke session | Does not necessarily affect token |

A solid implementation defines **consistency targets** before picking a solution. For low-sensitivity display metadata, a short TTL may be acceptable; for locks due to suspected account compromise or revocation of privileged roles, tighter measured and tested effective latency is required.

## 7. Designing Invalidation: After Commit, Across All Nodes, Right Keys

An account-update workflow typically includes:

```text
Admin or policy engine requests change
                |
        Verify authority to perform the change
                |
        Transaction modifies account/roles
                |
        Successful commit in database
                |
        Invalidate related UserDetails caches
                |
        Publish event to all instances (if local cache)
                |
        Execute session and token revoke/refresh strategy
                |
        Record audit event, monitor effective latency
```

Foundational rules:

1. **Invalidate with the exact cache key**: normalized username, tenant, and any related secondary keys. If lookups by email/ID are also cached, changing username/email must evict all corresponding keys.
2. **Place invalidation after successful transaction commit**: if you evict before commit, a concurrent request can reload the old record, then the commit finishes leaving stale data in cache. With Spring transactions, trigger invalidation after commit or via a consistent event/outbox.
3. **Ensure multi-node consistency**: a `ConcurrentMapCache` in instance A does not update B automatically. Use Redis/distributed caching or reliable invalidation messages; account for duplicates, retries, and dropped messages.
4. **TTL does not replace intentional invalidation**: TTL bounds staleness under normal conditions, not immediate revocation guarantees. For high-risk data, use read-through/revalidation or versioning.
5. **Prevent cache poisoning**: only store `UserDetails` returned from a trusted data source. Never accept `roles`, `enabled`, or `locked` from a request and cache them as verified state.
6. **Never cache plaintext passwords**: if caching password hashes, protect the cache like sensitive data, restrict access/logging, and encrypt transport for out-of-process caches.
7. **Be cautious caching mutable objects**: many `UserDetails` implementations also implement `CredentialsContainer` and can have credentials erased after authentication by `ProviderManager`. Caching the same mutable instance and returning it as the principal can wipe the cached password. Use immutable value objects/proper copies or design the cache to match the contract; never blindly disable credential erasure without a security review.
8. **Avoid long-lived negative caching**: caching "not found" results for long periods can block newly created users or cause false lockouts right after account creation; login messages must also not disclose whether an account exists.

**Do not assume cache invalidation and database commit are one atomic operation.** In distributed systems, when strict guarantees are needed, design version checks at security decision points or block requests during state transitions per explicit policy.

## 8. Plain Java 17+: Illustrating Why Cache Invalidation Is Required

Before configuring Spring, we can run a simple Java example to observe stale data. This is a **standalone program runnable with `javac`/`java`**, simulating an account copy; it is **not a real `UserDetails` implementation**.

Create `AccountCacheDemo.java`:

```java
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class AccountCacheDemo {
    record Account(Set<String> roles, boolean locked) {
        Account {
            roles = Set.copyOf(roles);
        }
    }

    public static void main(String[] args) {
        Map<String, Account> database = new ConcurrentHashMap<>();
        Map<String, Account> cache = new ConcurrentHashMap<>();

        database.put("alice", new Account(Set.of("ADMIN"), false));

        Account before = cache.computeIfAbsent("alice", database::get);
        System.out.println("before: " + before.roles().contains("ADMIN")
            + ", locked=" + before.locked());

        database.put("alice", new Account(Set.of("USER"), true));

        Account stale = cache.computeIfAbsent("alice", database::get);
        System.out.println("stale: " + stale.roles().contains("ADMIN")
            + ", locked=" + stale.locked());

        cache.remove("alice");

        Account fresh = cache.computeIfAbsent("alice", database::get);
        System.out.println("fresh: " + fresh.roles().contains("ADMIN")
            + ", locked=" + fresh.locked());
    }
}
```

Run commands:

```bash
javac AccountCacheDemo.java
java AccountCacheDemo
```

**Exact stdout** of the example above:

```text
before: true, locked=false
stale: true, locked=false
fresh: false, locked=true
```

This simulation shows that updating the database does not automatically update an `Account` object already sitting in the cache map. In Spring Security, `UserDetails` is likewise data loaded at a point in time, so **writes must be paired with invalidation or an appropriate versioning mechanism**. This program does not simulate sessions or JWTs; that is a separate layer of concern.

## 9. Spring Boot 3.x / Spring Security 6.x: Caching UserDetails and Evicting on Update

The following example illustrates `DaoAuthenticationProvider` with `SpringCacheBasedUserCache`. It uses a `ConcurrentHashMap`-backed "repository" for easy execution, **not replacing a production database**. `UserDetails` instances are constructed via an immutable `record` so a mutable object is never shared between the cache and the principal.

In a Spring Boot 3.x project with the Gradle plugin and dependency management, add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Create `src/main/java/example/accountcache/AccountCacheApplication.java`:

```java
package example.accountcache;

import java.util.Map;
import java.util.Set;
import java.util.Collection;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.UnaryOperator;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cache.concurrent.ConcurrentMapCache;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserCache;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.core.userdetails.cache.SpringCacheBasedUserCache;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AccountCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(AccountCacheApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserCache userCache() {
        // Local cache for illustration only, does not sync across multiple application nodes.
        return new SpringCacheBasedUserCache(
            new ConcurrentMapCache("userDetails"));
    }

    @Bean
    AuthenticationManager authenticationManager(
            AccountDirectory directory,
            PasswordEncoder encoder,
            UserCache userCache) {

        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(directory);
        provider.setPasswordEncoder(encoder);
        provider.setUserCache(userCache);

        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain chain(
            HttpSecurity http,
            AuthenticationManager authenticationManager) throws Exception {

        return http
            .authenticationManager(authenticationManager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}

@Service
class AccountDirectory implements UserDetailsService {

    private final Map<String, AccountRecord> accounts =
        new ConcurrentHashMap<>();
    private final UserCache cache;

    AccountDirectory(PasswordEncoder encoder, UserCache cache) {
        this.cache = cache;
        accounts.put("learner", new AccountRecord(
            "learner", encoder.encode("demo-pass"),
            true, true, Set.of(new SimpleGrantedAuthority("ROLE_USER"))
        ));
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        AccountRecord user = accounts.get(username);
        if (user == null) {
            throw new UsernameNotFoundException("User not found");
        }
        return user;
    }

    void grantAdmin(String username) {
        update(username, old -> new AccountRecord(
            old.username(), old.password(),
            old.enabled(), old.accountNonLocked(),
            Set.of(new SimpleGrantedAuthority("ROLE_USER"),
                   new SimpleGrantedAuthority("ROLE_ADMIN"))
        ));
    }

    void lock(String username) {
        update(username, old -> new AccountRecord(
            old.username(), old.password(),
            old.enabled(), false, old.authorities()
        ));
    }

    private void update(String username,
                        UnaryOperator<AccountRecord> change) {
        AccountRecord updated =
            accounts.computeIfPresent(username, (key, old) -> change.apply(old));

        if (updated == null) {
            throw new UsernameNotFoundException("User not found");
        }

        // Important: evict the exact key after the data source has updated.
        cache.removeUserFromCache(username);
    }

    record AccountRecord(
            String username,
            String password,
            boolean enabled,
            boolean accountNonLocked,
            Set<GrantedAuthority> authorities
    ) implements UserDetails {

        AccountRecord {
            authorities = Set.copyOf(authorities);
        }

        @Override
        public String getUsername() { return username; }

        @Override
        public String getPassword() { return password; }

        @Override
        public Collection<? extends GrantedAuthority> getAuthorities() {
            return authorities;
        }

        @Override
        public boolean isEnabled() { return enabled; }

        @Override
        public boolean isAccountNonLocked() {
            return accountNonLocked;
        }

        @Override
        public boolean isAccountNonExpired() { return true; }

        @Override
        public boolean isCredentialsNonExpired() { return true; }
    }
}

@RestController
class AccountController {

    @GetMapping("/me")
    String me(Authentication authentication) {
        return "hello " + authentication.getName();
    }

    @GetMapping("/admin")
    String admin() {
        return "admin area";
    }
}
```

### Code Analysis

- `AccountDirectory` is the `UserDetailsService`. In production, `loadUserByUsername` reads a repository/database, creating an authorities and status snapshot from committed records.
- `SpringCacheBasedUserCache` is plugged directly into `DaoAuthenticationProvider`. On each cache miss, the provider calls `loadUserByUsername`; after successful authentication, account info can be kept for subsequent requests.
- `DaoAuthenticationProvider` checks the **password hash** with `PasswordEncoder`, then checks account status; when `accountNonLocked=false`, new authentication attempts must be rejected.
- `AccountRecord` is immutable and does not implement `CredentialsContainer`. This avoids wiping the password hash on a shared cached principal during post-authentication credential erasure. With other mutable objects, design appropriate copying/caching.
- `grantAdmin` and `lock` are package-private methods **for testing only**. Never expose public endpoints allowing clients to arbitrarily invoke these two methods. For real administrative operations, enforce authorization and auditing; updates must run inside transactions and invalidation must occur at the right moment.
- `accounts.computeIfPresent` protects a single map update step within **one JVM**, without creating transactions across DB, cache, and sessions. A distributed design must separately handle races, distributed invalidation, and session revocation.
- The demo uses `HTTP Basic` locally to observe **per-request credential submission**. For browsers/production, use HTTPS and evaluate CSRF/sessions/threat models for the real mechanism; never use demo passwords in production.
- Configuration only allows GET `/me` or `/admin`, with all other endpoints set to `denyAll`. Never expose direct write APIs for outsiders to manipulate permissions.

### Running and Observing

At the project root with the Gradle wrapper, run:

```bash
./gradlew bootRun
```

Windows PowerShell: `./gradlew.bat bootRun`.

In the initial state, `learner` has `ROLE_USER` and is not locked:

```bash
curl -i -u learner:demo-pass http://localhost:8080/me
curl -i -u learner:demo-pass http://localhost:8080/admin
```

**Expected** results: GET `/me` -> 200 with body `hello learner`; GET `/admin` -> **403** due to lacking `ROLE_ADMIN`. When test code modifies the source data and invalidates the cache, new requests can receive `ROLE_ADMIN`; when locked afterward, new Basic credential submissions are rejected.

Since `grantAdmin` and `lock` are not HTTP endpoints, run the test below to execute the sequence of changes; do not try calling `POST /admin/grant` because the demo **has no such route**.

## 10. Testing with MockMvc: Granting a Role Then Locking the Account

Add test dependencies:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Create `src/test/java/example/accountcache/AccountCacheSecurityTest.java`:

```java
package example.accountcache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AccountCacheSecurityTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    AccountDirectory accounts;

    @Test
    void changesAreVisibleToNewAuthenticationAfterCacheEviction()
            throws Exception {

        // Auth succeeds but lacks ROLE_ADMIN.
        mvc.perform(get("/admin")
                .with(httpBasic("learner", "demo-pass")))
            .andExpect(status().isForbidden());

        // Change roles at the data source, evict UserDetails cache.
        accounts.grantAdmin("learner");

        // New authentication must see admin permission.
        mvc.perform(get("/admin")
                .with(httpBasic("learner", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin area"));

        // Lock account and evict UserDetails cache again.
        accounts.lock("learner");

        // New authentication with HTTP Basic is rejected.
        mvc.perform(get("/me")
                .with(httpBasic("learner", "demo-pass")))
            .andExpect(status().isUnauthorized());
    }
}
```

Run command:

```bash
./gradlew test
```

The assertions and statuses above are **expected results**, not yet executed in this document. The single test verifies permissions before/after `grantAdmin`, then confirms locking the account blocks a new authentication attempt. It **does not prove** existing sessions are revoked, nor does it verify distributed caches or JWTs.

A strongly recommended additional test for production is intentionally **omitting invalidation** in a separate fixture to prove stale state can keep being served from cache; then re-enabling invalidation to confirm the bug is fixed. Avoid running such a "failure-reproducing test" against shared environments or overwriting production configs.

## 11. Distinguishing UserDetails Cache from Logged-In Sessions

When using session-backed form login, after login `SecurityContext` is stored per repository/session policy. That session's `Authentication.getAuthorities()` is typically a **snapshot** at authentication time:

```text
t0: UserDetails = ROLE_ADMIN
    -> form login creates Authentication(ROLE_ADMIN)
    -> session S holds this Authentication

t1: Database changed to ROLE_USER
    -> invalidate UserDetails cache

t2: Browser sends session S cookie, without logging in again
    -> SecurityContext restores Authentication(ROLE_ADMIN)
    -> role may still be ROLE_ADMIN
```

Therefore, **immediate-effect revocation** needs an active-sessions policy. Depending on requirements:

- **Force re-login**: revoke/expire the user's sessions so the next request no longer has saved authentication. A locked account will fail the next login when account state is reloaded fresh.
- **Reload authorities**: on sensitive requests or inside a dedicated authorization strategy, check against a sufficiently fresh authority source. Avoid hitting the database on every URL indiscriminately; you can use versions, short-TTL caches, a policy engine, or event-push mechanisms.
- **Separate long-lived permissions from resource permissions**: `hasRole("ADMIN")` is only a coarse-grained role; ownership, tenant, and approval conditions must be checked in domain/service layers against current data.
- **Use `SessionRegistry` or a session store**: helps locate sessions and mark them expired/invalidated in suitable architectures; specifics depend on session tracking and cluster setup.

`SessionInformation.expireNow()` in session concurrency management is not an operation that deletes every cookie/token immediately. It marks the session so relevant mechanisms act on it when the next request passes through appropriate filters/session registries. With multiple nodes, reliable revocation requires a shared session store or synchronization mechanism. Do not call one `SessionRegistry` method and conclude all sessions and all tokens have been invalidated.

### Session Revocation Is a Policy, Not a Side Effect

Make explicit decisions for each kind of change:

| Change | Strategy for logged-in sessions |
| --- | --- |
| Revoke admin privilege | Revoke sessions or force permission re-evaluation before admin actions; may need immediate revocation |
| Lock due to suspected compromise | Revoke all relevant sessions, invalidate remember-me and tokens, block new credentials |
| Password change requested by user | Product-dependent: keep current session while revoking others, or revoke all |
| Grant regular role | May require re-login or authority refresh; never grant roles without re-evaluation |
| Disable account | Block both new logins and active-session access within SLA |
| Change display name | Does not necessarily require session revocation if permissions unchanged |

**Note:** Browser "logout" only deletes/invalidates a session per configured logout behavior and normally affects only the current session. Never assume logging out in one browser revokes all sessions across all devices.

## 12. Stateless Tokens and JWTs: UserDetails Cache Is Not the Only Control Point

In APIs using OAuth2 Resource Server with JWTs, requests can be authenticated by verifying signatures, issuer, audience, `exp`, and converting claims into authorities. If the system **does not use `UserDetailsService`** for this bearer flow, calling `UserCache.removeUserFromCache(username)` has nothing to do with a JWT holding `ROLE_ADMIN`.

Example:

```text
12:00 JWT issued: sub=alice, roles=[ADMIN], exp=12:15
12:02 database: roles=[USER]
12:03 evict all UserDetails caches
12:04 Old JWT may still be accepted with ADMIN claim
      if the system only verifies signature and expiration.
```

Ways to reduce revocation latency depending on architecture:

1. **Short-lived access tokens** paired with refresh token rotation and refresh token revocation policies; bounds how long stale claims live, though it is not instant revocation.
2. **Opaque tokens + introspection** or checking central token/session state to decide based on fresh status; trades off network latency/availability.
3. **Token revocation list** keyed by `jti`/session ID with TTL matching `exp`; must be designed fast and consistent across instances.
4. **Account/permission version**: tokens embed `version`, and the resource server checks the current version (or a version cache with invalidation and defined SLA). A version by itself **has no effect** if the resource server does not verify it.
5. **Request-time policy check** for sensitive actions; separate token authentication from authorizing specific operations.

Avoid rigid claims like "just lowering JWT TTL is enough" when immediate account lockout is required, or "use a blacklist" without sizing scale, read latency, and fail-closed behavior on dependency errors.

## 13. Multi-Instance, Concurrent Updates, and Transaction Boundaries

On a single local machine, `cache.removeUserFromCache(username)` right after `accounts.put` may suffice for illustration. Production usually has multiple instances:

```text
Node A (update request):
  DB COMMIT account.locked = true
  evict cache on A
  publish AccountChanged(accountId, version=13)

Message bus / distributed cache invalidation
  -> node B evict
  -> node C evict

Meanwhile:
  active sessions/tokens are handled per revoke/refresh policy
```

Risks that must be designed for:

- **"Read old then repopulate cache" race**: request B reads stale data from a replica or uncommitted transaction, then populates the cache **after** the invalidation command. You may need version checks, consistent-read sources, or revisioned cache entries.
- **At-least-once message delivery**: invalidation events may arrive more than once; `evict` must be idempotent. If messages are dropped, short TTLs and reconciliation/scans reduce risk without guaranteeing immediacy.
- **Out-of-order events**: a version 12 event can arrive after version 13. Prevent an older event from overwriting newer state.
- **Partial failure**: database commits successfully yet the message bus fails. Under strict requirements, consider a transactional outbox and retries; measure unprocessed-event rates.
- **Tenant-scoped cache keys**: identical usernames across multiple tenants must not collide. If a provider `UserCache` keys solely by username, design namespacing or provider isolation so data never mixes.
- **Account-status checks inside the authentication pipeline**: reading fresh cache after a change protects **new authentications**. Protecting active sessions requires additional checks.

The latency from "role changed in database -> no request still uses old role" must be measured by tests across nodes, not merely by seeing `evicted userDetails` in logs.

## 14. Safe Account-State Change Workflows

### Revoking Privileges or Changing Roles

1. Authenticate and authorize the **actor commanding the change**; include auditing and tenant/ownership checks.
2. Update roles/authorities inside a transaction.
3. After commit, invalidate caches for the right account/tenant everywhere `UserDetails` is used.
4. Decide **session policy**: expire sessions, reload authorities, or check policies at request time.
5. For JWTs/opaque tokens, enforce token revocation/version checks per SLA.
6. Measure: within what maximum time must an endpoint previously allowed for `ROLE_ADMIN` start returning 403/401? Write tests accordingly.

### Locking or Disabling an Account

1. Record `locked=true` or `enabled=false` in the source of truth with reason and timestamp.
2. Invalidate all caches containing status/credentials.
3. Block subsequent authentications via fresh `UserDetails` and provider checks.
4. Revoke/expire active sessions, remember-me tokens, and refresh tokens if policy requires "immediate lock".
5. For live self-contained tokens, apply one of the revocation mechanisms or request-time checks.
6. Record audit logs without exposing passwords/tokens; verify UI, APIs, and all nodes enforce the policy uniformly.

### Changing Passwords

1. Verify permission to change password or a valid reset token; store the password hash using the right encoder.
2. Commit the new hash and invalidate the UserDetails cache.
3. Decide whether to revoke other sessions and tokens based on the threat model.
4. Test that the old password is rejected on new authentications and the new password is accepted; avoid messages confirming whether a username exists.
5. Remember persistent remember-me tokens must be managed/revoked separately, not just via UserCache.

## 15. Tests Needed Before Deployment

| Scenario | What must be proven |
| --- | --- |
| First authentication and subsequent ones | Cache hit/miss per design, never leaking hashes/tokens in logs |
| Revoking role in DB after cache warm-up | New login/auth receives updated authorities, not stale roles |
| Locking/disabling account after cache warm-up | New auth receives `LockedException`/`DisabledException` or appropriate response, never reaching resource |
| Changing password after cache warm-up | Old password rejected after change; new password accepted |
| Session logged in before privilege revocation | Meets revoke/refresh SLA and prevents unexpected admin operations |
| Multi-node A/B with local caches | Invalidation reaches B; stale window never exceeds SLA |
| Transaction rollback or event-publish failure | Never invalidates prematurely then caches stale data; retry/reconcile works |
| Usernames with tenants or case normalization | Never returns another tenant/account's UserDetails |
| Account lock concurrent with requests | Race analysis, versioning, and policy for in-flight requests |
| Remember-me / JWT / access tokens | Dedicated revocation applied, not relying solely on clearing UserDetails cache |
| Admin granting/revoking multiple roles | Authorization never uses snapshots older than allowed |
| Authentication error reporting | Does not reveal whether user exists or is locked to unauthorized outsiders |
| Cache stress test | Bounded entries, TTL, stale ratio, DB load; performance does not break security goals |

Use integration tests for authentication/authorization; isolated tests for repositories/caches; and real end-to-end tests across multiple service instances if the system is distributed. In Spring Security, the HTTP status code of an auth error also depends on entry points and access-denied handlers: never treat 401/403 as absolute conclusions if responses have been customized.

## 16. Common Misconceptions

### "Spring Security caches UserDetails by default"

Do not assume that. `AbstractUserDetailsAuthenticationProvider` normally uses `NullUserCache` unless you configure a cache. If the DB is not queried on every request, the cause may be the **session holding Authentication**, not a provider UserCache hit.

### "Evicting UserDetails immediately strips old sessions of their permissions"

False. A saved `SecurityContext` holds an `Authentication` with its own authorities. You must revoke the session or re-evaluate permissions to take effect per policy.

### "Locking an account is enough to invalidate all access tokens"

False for many stateless JWT systems. Signed, unexpired tokens may keep being accepted until revocation policies or version checks take effect.

### "A 5-minute TTL guarantees immediate lockout"

TTL only bounds entry lifetime in cache (depending on implementation). It does not enforce lockout within the first second, let alone existing sessions. For risky operations, define SLAs and apply appropriate mechanisms.

### "Successful login means permissions are updated for every request"

Incorrect. `Authentication` normally keeps authorities loaded at **that authentication time**. New/changed permissions are only seen when the corresponding mechanism refreshes or revalidates.

### "Calling `removeUserFromCache` on the node handling the command is enough"

Not enough when nodes use independent local caches. You must synchronize invalidation or use a shared cache with a designed consistency mechanism.

### "You can disable `eraseCredentialsAfterAuthentication` to make caching work"

That can work around an issue in some configs, yet lengthens how long credential data stays in objects. Prefer clear cache contracts, immutability/proper copying, and careful security evaluation; never disable credential cleanup just to hide a design flaw.

### "Stale-data bugs are URL authorization bugs"

Not necessarily. The URL `hasRole` policy may be completely correct while `Authentication` or `UserDetails` holds stale authorities. When debugging, check **role source**, **cache state**, **current Authentication**, **session/token**, and **authorization rules** in order.

## 17. Self-Check Exercises

**Question 1.** `DaoAuthenticationProvider` uses `SpringCacheBasedUserCache` with a 10-minute TTL. A user is locked right after logging in. Why can a request using the old session cookie still access `/me`?

**Answer:** The session can restore the `Authentication` created before the lock without reloading `UserDetails`. TTL or eviction only affects the user-details cache layer, not automatically destroying the session.

**Question 2.** An administrator revokes `ROLE_ADMIN`, commits to the database, and calls `removeUserFromCache("alice")` on node A. Node B has a separate local cache. What must be done?

**Answer:** Invalidate the cache on B (via events/distributed cache/versioning), while also handling active sessions/tokens and testing revocation latency against the SLA.

**Question 3.** A developer places `@Cacheable("users")` on `loadUserByUsername` and a `UserCache` on `DaoAuthenticationProvider`. When roles change, is clearing only the provider cache enough?

**Answer:** Not necessarily. A cache miss at the provider can still receive stale `UserDetails` from the service-level cache. Define a single cache owner or invalidate every relevant layer.

**Question 4.** When an account is locked, what value should `UserDetails.isAccountNonLocked()` return? When does that change take effect most directly?

**Answer:** Return `false`. Provider account-status checks will reject new username/password authentication attempts once updated `UserDetails` is loaded. Active sessions follow their own handling policy.

**Question 5.** Can session `Authentication.getAuthorities()` be used as the "source of truth" for permissions after an admin has modified roles?

**Answer:** Not if business rules require immediate permission updates: the session may hold a stale snapshot. You need refresh/revocation or re-evaluation against a sufficiently fresh policy source.

**Question 6.** In a multi-tenant app, both tenants A and B have username `"supervisor"`. The cache key is the bare username. What bug can happen?

**Answer:** Two records can share the same key, causing mixed-up UserDetails and roles across tenants. Keys and trust domains must include trusted tenant context; never take client-supplied tenant IDs without verification.

**Question 7.** An old JWT carries claim `roles=["ADMIN"]` with 15 minutes left before expiry. Does clearing the `UserDetails` cache invalidate the JWT?

**Answer:** No, if the resource server only verifies signature/expiry and reads role claims without re-checking account status. You need a token revocation/version/short-TTL strategy matching the SLA.

## 18. Design Checklist Before Enabling Caching

- [ ] Identify the exact **cache layer** storing `UserDetails` and who owns invalidation.
- [ ] Load `enabled`, `accountNonLocked`, `accountNonExpired`, `credentialsNonExpired`, and authorities from a trusted source.
- [ ] Normalize cache keys, including tenant namespaces when needed; zero cross-tenant collisions.
- [ ] Cache never stores plaintext credentials, never logs password hashes or full `Authentication` objects.
- [ ] After commits changing roles/locks/passwords, related caches are invalidated for the exact account.
- [ ] Multi-node/distributed invalidation and dropped-event/rollback scenarios are tested.
- [ ] Have a clear strategy for **active sessions** when privileges are revoked or accounts locked.
- [ ] Have dedicated strategies for JWTs, remember-me, and refresh tokens.
- [ ] Revocation SLA is measured, not merely claimed via "a short TTL is enough".
- [ ] Integration tests cover before/after across both new authentications and existing sessions.

## Conclusion

`UserDetails` caching improves performance when repeated authentications must load the same account. However, **stale roles, stale lock flags, and stale password hashes** are real security risks. `UserCache.removeUserFromCache(username)`, service cache invalidation, multi-node synchronization, and post-commit execution ensure **new authentication attempts** see accurate data.

For authority changes or account locks to take effect on **active sessions**, you also need session revocation/refresh, token policies, and/or request-time authorization checks per business requirements. Understanding the boundaries between **UserDetails**, **Authentication**, **SecurityContext**, and **tokens** is essential to designing it right rather than flipping on a caching annotation and calling it done.
