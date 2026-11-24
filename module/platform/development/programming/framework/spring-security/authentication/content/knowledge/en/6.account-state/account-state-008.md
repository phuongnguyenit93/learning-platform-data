# Post-Login State Changes and the Limits of Login-Only Checks

A user logs in successfully at 09:00. At 09:05, an administrator **locks the account**, **disables the user**, **revokes the ADMIN role**, or **resets the password**. At 09:06, the browser still sends the cookie of the just-issued session, or a mobile app sends an access token issued earlier. Will the new request be rejected?

**You cannot conclude that from "Spring Security checked the account at login."** Verifying login credentials at T0 and preserving permission to use a session/token at T1 are two distinct decisions. With a stateful HTTP session, `SecurityContext` usually holds the `Authentication` and authorities authenticated **at an earlier time**. Unless the application has a mechanism to re-check, refresh, or revoke, changing state in the database does not necessarily alter the principal sitting inside the session. With a self-contained JWT, a valid signature and unexpired `exp` **do not prove** the account is still enabled or roles have not been revoked.

This lesson belongs to the **Account State** section in *Spring Security - authentication*, focusing on the **post-login** lifecycle: limits of status checks, session snapshots, bearer tokens, revocation and security versioning, choosing re-check points, and testing on Java 17+/Spring Boot 3.x.

## 1. Objectives

After this lesson, you will:

1. Distinguish **account status**, **credential status**, **authentication/session status**, and **authorization state** at any given moment.
2. Explain when `UserDetails` flags are checked by `DaoAuthenticationProvider` and why they do not automatically "push" changes into a stored `SecurityContext`.
3. Predict the impact of disablement, locking, password resets, role removal, account expiry, user deletion, and tenant membership removal on issued sessions/tokens.
4. Distinguish form login + `HttpSession`, HTTP Basic, remember-me, JWTs, opaque tokens, and refresh tokens.
5. Choose re-check strategies: session invalidation, version/epoch, per-request revalidation, short TTLs, online introspection, and checking permissions close to sensitive operations.
6. Run a Java 17+ example for version checking, along with a Spring Security integration test proving **post-login state changes** block subsequent requests.
7. Design tests for caches, multiple nodes, revocation latency, and in-flight requests.

## 2. Fundamentals: checking credentials at login differs from checking state on later requests

### 2.1 Typical username/password authentication flow

```text
POST /login: username + raw password
     |
     v
UsernamePasswordAuthenticationFilter
     |
     v
AuthenticationManager / ProviderManager
     |
     v
DaoAuthenticationProvider
     +--> UserDetailsService.loadUserByUsername(username)
     |       -> password hash, account flags, authorities
     +--> Check account status
     +--> PasswordEncoder.matches(raw, encoded)
     +--> Check credentials still valid
     |
     v
Authentication succeeded
     +--> resolved principal + authorities
     |
     v
SecurityContext stored in HttpSession (if stateful)
     |
     v
GET /api/report with old session cookie
     -> retrieve stored SecurityContext
     -> apply authorization from existing Authentication
     -> DOES NOT BY DEFAULT re-query UserDetailsService every time
```

The user's database record is only **the data source at the moment the provider loads it**. An `Authentication` is marked authenticated after verifying credentials; `authentication.isAuthenticated()` does not run new SQL queries on its own. When subsequent requests arrive with a session cookie, Spring Security can retrieve the object/serialized snapshot from the session. Without extra status checks, a value like `ROLE_ADMIN` can persist even after an admin deletes the role in the DB.

### 2.2 Meaning of the four UserDetails flags

| Method | If returning `false` | Effect when the matching provider authenticates |
| --- | --- | --- |
| `isEnabled()` | Account disabled | Typically rejects with `DisabledException`. |
| `isAccountNonLocked()` | Account locked | Typically rejects with `LockedException`. |
| `isAccountNonExpired()` | Account expired | Typically rejects with `AccountExpiredException`. |
| `isCredentialsNonExpired()` | Credentials expired | Typically rejects with `CredentialsExpiredException`. |

These methods can be checked by `DaoAuthenticationProvider`/account status checkers when running **an authentication attempt**. They do not automatically invalidate every already-issued session. If `UserDetailsService` has a stale cache, even a new authentication attempt may use old state; cache freshness must be considered.

In particular, `isAccountNonLocked()==false` means **locked** (the name is negated); do not invert the semantics when mapping from a `locked` column in the DB.

### 2.3 Timeline and questions to answer

```text
09:00     Valid login: enabled=true, role=ADMIN
  |
09:01     Server stores Authentication for session S with ROLE_ADMIN
  |
09:05     Admin sets enabled=false or removes ROLE_ADMIN in DB
  |
09:06     Client sends session S cookie to call /api/admin
           |
           +-- Check only at login?  May remain authenticated + old role
           +-- Session revoked?  Session S can no longer be used
           +-- Revalidate every request?  Sees new state and rejects
           +-- JWT checking only exp?  Can still be used until token expires
```

Updating a row in the DB at 09:05 is **not** equivalent to "deleting every browser's session, revoking every access token, updating every cache, and halting every in-flight request." Those effects must be built intentionally.

## 3. Four types of state that must be defined separately

**Account state:** whether the account exists, is enabled, locked, non-expired, and retains tenant membership.

**Credential state:** whether the password was reset, password hash compromised, MFA changed, or API key / refresh token remains valid.

**Authentication/session state:** whether the cookie/session ID is still valid, whether the version at issuance is still accepted, whether the token expired or was revoked, and whether the user reauthenticated when required.

**Authorization state:** whether the principal is still permitted to perform this action on **the specific object and tenant**; when the role/permission was granted, and whether a live source lookup is needed.

A user may be **authenticated yet unauthorized**; a validly signed JWT may still violate account policy; an expired session may force re-login even while the account stays enabled. Never collapse all of these into a single `loggedIn` boolean.

### 3.1 Post-login event matrix

| Change | New login | Old session without revocation/freshness | Self-contained JWT checking only signature/exp | What to consider |
| --- | --- | --- | --- | --- |
| `enabled=false` | Usually blocked by provider | May keep working | May work until `exp` | Revoke/invalidate or check enabled/version. |
| `accountLocked=true` | Provider with status checker rejects | Not necessarily affected | Not necessarily affected | Define whether locks apply to active sessions too. |
| `accountExpired=true` | Provider usually rejects | Snapshot may not be updated | Claims remain unexpired | Check account expiry at the appropriate point. |
| Password/credential expired | Login with old password may be blocked | Old session may remain | JWT typically unaware of password age | Force reauthentication/rotation per policy. |
| Incident password reset | Old hash replaced | Issued cookies do not vanish | JWT does not auto-invalidate | Revoke sessions, refresh grants, tokens per policy. |
| Removed ADMIN role | New login gets updated authorities | Old session may retain `ROLE_ADMIN` | Old permission claims persist | Permission versioning, refresh principal, live authorization checks. |
| Deleted account from DB | New lookup finds no user | Old principal object may remain | Old JWT still verifies | Reject missing accounts and revoke sessions. |
| Removed tenant membership | New login/tenant switch must reject | Old tenant session may remain | Old tenant claim may remain | Membership check/revocation per tenant + account. |
| Re-enabled after disable | Can log in fresh | Revoked sessions **must not resurrect** | Revoked tokens must not resume working | Monotonically increasing security version/epoch. |

**Operational requirements must specify which events trigger "logout all," which only alter permissions, and how fast changes must take effect.** A low-risk internal info system may accept short TTLs; financial administration actions generally require fresher permission sources.

## 4. Distinguishing session/token mechanisms

### 4.1 Form login + HttpSession

After form login, Spring Security can store `SecurityContext` in `HttpSession` via `SecurityContextRepository`. Subsequent requests carry the session cookie and restore the context. In typical configurations, **this path does not re-run `PasswordEncoder.matches` or reload `UserDetails` on every request**.

- Session timeout checks **session age**, not current account status.
- Server-side logout/invalidation voids the revoked session ID; deleting cookies on the client **does not invalidate a stolen copy of the cookie**.
- `SessionCreationPolicy` and `SecurityContextRepository` govern storage; custom logins must save the context via the proper API, especially in Spring Security 6.
- Session fixation/CSRF/XSS protections remain essential, yet do not fix stale role snapshots.
- With Spring Session/Redis or clusters, invalidation must target the shared store; do not assume sessions live solely inside one JVM's memory.

### 4.2 HTTP Basic

HTTP Basic typically sends `Authorization: Basic ...` on **every request**. In an appropriate stateless flow, the provider has a chance to check credentials and account status repeatedly, unlike an already-created form-login session. However, if the system uses stale caches, custom managers, or persists authentication across requests, you cannot promise "HTTP Basic always reads the latest DB." HTTP Basic is only Base64 encoding, **not secure without HTTPS**.

### 4.3 Remember-me

A remember-me cookie can provide a re-login mechanism once a session expires. Should disabling or resetting a password revoke persistent remember-me tokens? You must inspect your configuration; invalidating a single session **does not guarantee** the remember-me cookie will not restore access afterward. For credential incidents, revocation procedures should cover sessions, remember-me, refresh grants, and SSO.

### 4.4 JWT bearer

Spring Security Resource Server JWT can verify signatures and `iss`/`exp`/`nbf` conditions as configured. That is **token validity checking**; it does not query the DB by default to see whether the user was just disabled or a role was revoked. Permissions inside a JWT are an issuance-time snapshot until expiration or rejection by an API's additional mechanism.

- Short access tokens **shrink the stale window**, rather than providing immediate revocation.
- `jti` denylists, grant revocation, or auth-version checks require a trusted status source that APIs actually query.
- `aud`, tenant, and scope/permissions need proper validators; Base64 decoding is not verification.
- Revoking a refresh token prevents issuing new tokens, yet **does not automatically cancel** an old access JWT if APIs only check signature/exp.

### 4.5 Opaque tokens and introspection

An opaque token is usually checked by the resource server querying the authorization server to see if it is `active`. Revoking at the issuer **can** take effect quickly if the resource server uses sufficiently fresh introspection. However, introspection caches, timeouts, and issuer policies determine actual latency. Never assume opaque tokens guarantee 0-second revocation across every cluster.

## 5. Designing freshness and revocation policies

### 5.1 A measurable commitment

Example testable requirement:

> Once an account-disable operation commits to the authoritative state store, any request **starting after the new state is observable at the trusted check source** must be rejected. For requests already past the check point before commit, the system defines separate bounds and mechanisms.

Another example: "Revoking the ADMIN role takes effect within at most 10 seconds across all APIs; money transfers require a live permission check inside the transaction." Specify when measurement starts, node/cache scope, and how to test. **"Immediate" is an architectural requirement, not a default property of `UserDetails`.**

### 5.2 Options and trade-offs

| Option | Mechanism | Strengths | Limits |
| --- | --- | --- | --- |
| Login-time check only | Provider loads user/status and creates session snapshot | Minimal post-login queries | DB changes may not affect active sessions. |
| Short session timeout | Idle/absolute expiry | Bounds lifetime | Does not react immediately on role revocation. |
| Push session invalidation | Admin change events destroy/expire sessions | Low latency | Requires full-coverage session registry/shared store, event retries. |
| Per-request state check | Every request reads trusted enabled/locked/version | Sees changes on next check | Costs I/O; cache staleness/outage and in-flight races. |
| Auth version/epoch | Session/token carries issued version; compared to current version | One consistent revocation mechanism across events | Must bump version on **every** revocable event; needs fresh source. |
| Refresh authorities | Rebuild principal or re-check permissions | Avoids mandatory logout on role changes | May grant unexpected privileges; needs reauth/step-up policy. |
| Short JWT + refresh revoke | Access expires quickly, stops new tokens | Good scale and latency | Old JWTs continue until `exp`. |
| Online token introspection | API queries issuer/grant status | Centralized revocation | Increases network/cache dependency and failure modes. |
| Service-layer authorization | Checks account/tenant/object right at execution time | Protects sensitive business logic | Needs clear transaction/consistency and race design. |

A practical combination is often **appropriate TTLs + account `authVersion` + invalidation events + checks close to sensitive transactions**. No single filter solves every login mechanism and every resource.

### 5.3 Auth version is not a password

Each account has an `auth_version` (or `sessions_valid_after`):

```text
At login:
  accountId=101 enabled=true auth_version=7
  session.authVersion=7

Admin disables:
  accountId=101 enabled=false auth_version=8

Old request:
  version in session = 7
  authoritative version = 8
  -> reject, invalidate session per policy.

Admin re-enables:
  accountId=101 enabled=true auth_version=9
  old session still version 7 -> reject.
```

Version does not re-verify the raw password. It is simply **the condition for whether an already-issued authentication result is still trusted**. Comparing `enabled` alone is insufficient to prevent "resurrecting" old cookies after disable → enable. In multi-tenant systems, role/membership versions can be scoped by `(tenantId, accountId)`; use stable IDs, not mutable display emails.

### 5.4 Atomic updates and source of truth

If an admin removes a role and forgets to bump the version, sessions holding the old role may keep working. If the version bumps successfully while the permission update fails, users may be logged out needlessly. Update status, roles, and epochs in a **consistent transaction**:

```sql
-- Illustrative for an accounts(account_id,enabled,auth_version) schema
UPDATE accounts
SET enabled = FALSE,
    auth_version = auth_version + 1
WHERE account_id = ?;
```

For role removal, update the role table and bump the version in the same transaction per your dialect/infrastructure. Use unique/foreign keys, optimistic locking, or an outbox when publishing events to other nodes. Commit points and replica/cache lag must be factored into SLAs; never treat a published event as already received by every API.

## 6. Standalone Java 17+: illustrating versioning and non-resurrection of sessions

The snippet below **runs with JDK 17+ alone**, with no Spring dependency. It is not real authentication functionality; it validates security version logic.

File `StateVersionDemo.java`:

```java
public final class StateVersionDemo {

    record State(boolean enabled, long version) {}

    static boolean accepts(State current, long sessionVersion) {
        return current.enabled()
                && current.version() == sessionVersion;
    }

    public static void main(String[] args) {
        State atLogin = new State(true, 1);
        long oldVersion = atLogin.version();

        System.out.println("before-change=" + accepts(atLogin, oldVersion));

        State disabled = new State(false, 2);
        System.out.println("after-disable=" + accepts(disabled, oldVersion));

        State enabledAgain = new State(true, 3);
        System.out.println("old-session-after-enable="
                + accepts(enabledAgain, oldVersion));
        System.out.println("new-session-after-enable="
                + accepts(enabledAgain, enabledAgain.version()));
    }
}
```

Commands:

```bash
javac StateVersionDemo.java
java StateVersionDemo
```

Exact stdout:

```text
before-change=true
after-disable=false
old-session-after-enable=false
new-session-after-enable=true
```

**Lesson:** When the account is re-enabled, a *new* session issued at version 3 is valid, whereas the version 1 session remains rejected. This provides stronger revocation semantics than checking `"enabled=true"` alone.

## 7. Runnable Spring Boot 3.x: checking status/version on old sessions

This lab uses **Spring Boot 3.3.13, Spring Security 6.x, and Java 17+** with form login and `HttpSession`. A thread-safe in-memory account store holds `enabled`, `authVersion`, password verifier, and authorities. Upon successful login, a custom principal captures the version snapshot. A filter inside the **Spring Security chain**, running after the context is loaded and before `AuthorizationFilter`, checks the current state source:

- Account disabled or deleted: invalidate session and return HTTP 401.
- Version differs from snapshot: invalidate session and require re-login.
- State still valid: request proceeds to authorization normally.

This example **has no public endpoint to change roles or disable users**. Integration tests invoke the account-management bean directly as a trusted administrative action. In production, replace the in-memory store with a DB/shared source with transactional updates and proper consistency.

### 7.1 Project structure and Gradle

```text
session-state-lesson/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/SessionStateApplication.java
    └── test/java/demo/SessionStateTest.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'session-state-lesson'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

These versions are pinned to reproduce the example, **not a recommendation to pick end-of-life branches for new production development**. When deploying real products, use supported Spring Boot/Spring Security lines and verify API compatibility.

### 7.2 Spring Security Servlet application

File `src/main/java/demo/SessionStateApplication.java`:

```java
package demo;

import java.io.IOException;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class SessionStateApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionStateApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    AccountStore accountStore(PasswordEncoder encoder) {
        return new AccountStore(encoder);
    }

    @Bean
    UserDetailsService userDetailsService(AccountStore store) {
        return store::loadForLogin;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AccountStore store) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/api/me").authenticated()
                        .requestMatchers("/api/manage")
                            .hasAuthority("ROLE_MANAGER")
                        .anyRequest().denyAll())
                .formLogin(form -> form.permitAll())
                .logout(logout -> logout.permitAll())
                .addFilterBefore(
                        new StateRefreshFilter(store),
                        AuthorizationFilter.class)
                .build();
    }

    record AccountRow(
            String hash,
            boolean enabled,
            long authVersion,
            Set<String> authorities) {
    }

    static final class AccountStore {
        private final ConcurrentMap<String, AccountRow> rows =
                new ConcurrentHashMap<>();

        AccountStore(PasswordEncoder encoder) {
            rows.put("alice", new AccountRow(
                    encoder.encode("local-demo-password"),
                    true, 1L, Set.of("ROLE_USER")));
        }

        UserDetails loadForLogin(String username) {
            AccountRow record = rows.get(username);
            if (record == null) {
                throw new UsernameNotFoundException("Unknown user");
            }

            List<GrantedAuthority> authorities = record.authorities()
                    .stream()
                    .sorted()
                    .map(SimpleGrantedAuthority::new)
                    .map(x -> (GrantedAuthority) x)
                    .toList();

            // Fresh UserDetails every time: do not reuse a cached User
            // that may have been mutated by ProviderManager.eraseCredentials().
            return new VersionedUser(
                    username, record.hash(), record.enabled(),
                    record.authVersion(), authorities);
        }

        AccountRow current(String username) {
            return rows.get(username);
        }

        void disable(String username) {
            rows.computeIfPresent(username, (key, previous) ->
                    new AccountRow(
                            previous.hash(), false,
                            previous.authVersion() + 1,
                            previous.authorities()));
        }

        void grantManager(String username) {
            rows.computeIfPresent(username, (key, previous) -> {
                Set<String> roles = new java.util.HashSet<>(
                        previous.authorities());
                roles.add("ROLE_MANAGER");
                return new AccountRow(
                        previous.hash(),
                        previous.enabled(),
                        previous.authVersion() + 1,
                        Set.copyOf(roles));
            });
        }
    }

    static final class VersionedUser extends User {
        private static final long serialVersionUID = 1L;
        private final long authVersion;

        VersionedUser(
                String username,
                String encodedPassword,
                boolean enabled,
                long authVersion,
                Collection<? extends GrantedAuthority> authorities) {
            super(username, encodedPassword,
                    enabled, true, true, true, authorities);
            this.authVersion = authVersion;
        }

        long getAuthVersion() {
            return authVersion;
        }
    }

    static final class StateRefreshFilter
            extends OncePerRequestFilter {
        private final AccountStore store;

        StateRefreshFilter(AccountStore store) {
            this.store = store;
        }

        @Override
        protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain chain) throws ServletException, IOException {

            Authentication auth =
                    SecurityContextHolder.getContext().getAuthentication();

            if (auth != null && auth.isAuthenticated()
                    && auth.getPrincipal() instanceof VersionedUser user) {

                AccountRow current = store.current(user.getUsername());
                boolean revoked = current == null
                        || !current.enabled()
                        || current.authVersion() != user.getAuthVersion();

                if (revoked) {
                    SecurityContextHolder.clearContext();
                    HttpSession session = request.getSession(false);
                    if (session != null) {
                        session.invalidate();
                    }
                    response.sendError(
                            HttpServletResponse.SC_UNAUTHORIZED,
                            "Sign in again");
                    return;
                }
            }

            chain.doFilter(request, response);
        }
    }
}

@RestController
class AccountController {

    @GetMapping("/api/me")
    Map<String, Object> me(Authentication auth) {
        return Map.of(
                "username", auth.getName(),
                "authorities", auth.getAuthorities().stream()
                        .map(GrantedAuthority::getAuthority)
                        .sorted().toList());
    }

    @GetMapping("/api/manage")
    String manage() {
        return "manager";
    }
}
```

Detailed explanation:

- `UserDetailsService` returns a **new instance** of `VersionedUser` at login, carrying `enabled` and `version` from the store. When the provider authenticates, the password is verified by `PasswordEncoder`; the demo never returns passwords or hashes to controllers.
- `VersionedUser extends User` retains the `authVersion` snapshot. If `ProviderManager` erases credentials on the principal, the store still keeps the hash independently inside `AccountRow`.
- `StateRefreshFilter` is instantiated directly in `SecurityFilterChain`, not registered as a Servlet `@Component`; this prevents the filter from auto-registering a second time outside the chain.
- With stateful form login, the context is already loaded when the filter placed before `AuthorizationFilter` runs. The filter checks only authentications whose principal is `VersionedUser`. If the app also uses JWT/OIDC or other chains, corresponding checks are needed; this filter **does not protect every principal type**.
- Invalidating `HttpSession` clears the demo session's security context. Calling `SecurityContextHolder.clearContext()` alone is insufficient to remove all sessions on the server/distributed store.
- `formLogin` keeps Spring Security's default CSRF protection. The demo **does not disable CSRF** just to make tests easier; tests use the dedicated form-login helper.
- Never keep raw passwords in the session to "re-verify" on every request. Session status/version is checked against the account store, while passwords are checked only during the corresponding login flow.

### 7.3 Integration test through the Spring Security filter chain

File `src/test/java/demo/SessionStateTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class SessionStateTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    SessionStateApplication.AccountStore accounts;

    private MockHttpSession login() throws Exception {
        MvcResult result = mvc.perform(
                formLogin().user("alice").password("local-demo-password"))
                .andExpect(status().is3xxRedirection())
                .andReturn();
        return (MockHttpSession) result.getRequest().getSession(false);
    }

    @Test
    void disableAfterLoginRejectsOldSession() throws Exception {
        MockHttpSession session = login();

        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"));

        accounts.disable("alice");

        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void changingRoleInvalidatesOldSessionUntilRelogin()
            throws Exception {
        MockHttpSession previousSession = login();

        mvc.perform(get("/api/manage").session(previousSession))
                .andExpect(status().isForbidden());

        accounts.grantManager("alice"); // Bump version + update role.

        mvc.perform(get("/api/me").session(previousSession))
                .andExpect(status().isUnauthorized());

        MockHttpSession newSession = login();

        mvc.perform(get("/api/manage").session(newSession))
                .andExpect(status().isOk());
    }
}
```

`formLogin()` from `spring-security-test` submits form login through the filter chain with proper CSRF handling instead of bypassing protection. Both tests are isolated: `@DirtiesContext` reinitializes the store between methods. **Expected outcome** is passing tests if the project is created properly; this is not a claim that a build was run in the learner's environment.

### 7.4 Running and explaining the output

If the project has a Gradle wrapper:

```bash
./gradlew test
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat bootRun
```

If Gradle is installed without a wrapper in the project, use `gradle test`/`gradle bootRun`. Because the app imports Spring Boot/Security, running `javac SessionStateApplication.java` **is insufficient** without the dependency classpath. The Java demo `StateVersionDemo.java` in Section 6 is the pure-JDK example with exact stdout.

Expected progression across the integration test:

| Stage | Version/state | HTTP |
| --- | --- | --- |
| Alice logs in | Enabled, version 1, ROLE_USER | Successful login redirect. |
| `GET /api/me` with new session | Version 1 unchanged | 200, username Alice. |
| `GET /api/manage` with USER role | Missing ROLE_MANAGER | 403 (authenticated but unauthorized). |
| Admin disables post-login | Enabled=false, version bumped | Next request with old session: 401. |
| Admin grants ROLE_MANAGER, version bumped | Old session still version 1 | Request from old session: 401. |
| Alice logs in fresh after role grant | New principal has new version and role | `GET /api/manage`: 200. |

To *observe the limit of login-only checks firsthand* in a local experiment, temporarily remove **only** the `.addFilterBefore(...)` line and re-run the tests: sessions issued before the store changed may keep using the snapshotted principal/authorities. That is an observation exercise, **not a safe configuration to deploy**.

### 7.5 Intentional limitations of the demo

This is a **single JVM**: no DB, distributed cache, long-running requests, user-deletion endpoints, multi-tenancy, or bearer tokens. The filter only supports `VersionedUser` inside the form-login chain. In applications with multiple `SecurityFilterChain`s, each chain/manager needs its own corresponding policy. If an account is revoked right after a request passes the filter, downstream operations **may still execute**; see Section 8.4 on TOCTOU.

## 8. Production: turning versioning into a trustworthy data contract

### 8.1 Bind version to a stable account ID

Never rely solely on mutable display names/emails to look up state once a principal is authenticated. In the database you can store:

```sql
CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    login_name VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL,
    locked BOOLEAN NOT NULL,
    auth_version BIGINT NOT NULL
);

CREATE TABLE account_roles (
    account_id BIGINT NOT NULL,
    role VARCHAR(100) NOT NULL,
    PRIMARY KEY (account_id, role),
    FOREIGN KEY (account_id) REFERENCES accounts(account_id)
);
```

This is illustrative SQL for a matching dialect, not a complete production schema. Multi-tenant apps may need `tenant_id`, composite uniqueness, separate membership versions, tenant/account FKs, and object-level authorization.

At login, the principal snapshot should store the account ID (+ tenant ID if applicable), auth version, and verified authorities. The filter/policy service queries current state using **the ID from the trusted principal**:

```sql
SELECT enabled, locked, auth_version
FROM accounts
WHERE account_id = ?;
```

Never take `accountId`, `tenantId`, or `authVersion` from client headers like `X-User`/`X-Auth-Version` and treat them as truth. Even a token with a signed version claim **must still be compared against the authoritative version** if post-issuance revocation is the goal.

### 8.2 Updates and revocations must share transaction boundaries

Example disable + epoch bump in the same update:

```sql
UPDATE accounts
SET enabled = FALSE,
    auth_version = auth_version + 1
WHERE account_id = ?;
```

For role revocation, delete the role and increment the account/membership version in a single appropriate transaction. If the DB commits while an invalidation event fails, a cache node may continue serving stale state; use an outbox/retry/TTL and measure actual lag. Never treat `userExists()` or out-of-transaction cache updates as sufficient guarantees.

### 8.3 Caching and distributed state

Suppose an API caches status for 60 seconds, yet policy requires disablement to take effect in under 5 seconds. Without reliable invalidation, a 60-second TTL **fails to meet** the commitment. Define the authoritative source, maximum staleness, replication lag, and fail mode when unavailable.

Cache keys in multi-tenant systems must include the namespace, e.g., `(tenantId, accountId)`; never use `username` alone if names collide across organizations. `UserDetails` may contain password verifiers and be mutated by `ProviderManager.eraseCredentials()`; never accidentally share an erased mutable principal with a cached account verifier.

### 8.4 Request-entry filters do not solve every race

At T1 the filter sees the account is enabled. At T2 an admin revokes a role. At T3 a business service still commits a sensitive transaction. **A check at T1 alone does not prove the action at T3 is still permitted.**

For operations with strong requirements, combine authorization close to write time, transactions/optimistic locking, and data predicates:

```sql
-- Illustrates checking permissions right at execution;
-- adapt tenant/owner/transaction rules to the real system.
UPDATE approvals
SET status = 'APPROVED'
WHERE approval_id = ?
  AND EXISTS (
      SELECT 1
      FROM accounts a
      JOIN account_roles r ON r.account_id = a.account_id
      WHERE a.account_id = ?
        AND a.enabled = TRUE
        AND a.locked = FALSE
        AND r.role = 'ROLE_APPROVER'
  );
```

Affected row counts must be checked; if 0, handle per API/business policy. Never omit tenant predicates in multi-tenant systems; the SQL above illustrates logic only, not a complete object-level policy.

## 9. SessionRegistry, logout all, and limits of invalidation

Spring Security offers session management and `SessionRegistry`, yet **`maximumSessions` does not automatically mean revoking all sessions when a user is disabled**.

- In-JVM `SessionRegistryImpl` can track principal → sessions, yet is not a cluster-wide shared registry by default.
- `HttpSessionEventPublisher` can forward lifecycle events to the registry in compatible setups.
- `SessionInformation.expireNow()` usually **marks** a session for the filter mechanism to handle on the next request; it does not immediately kill in-flight requests. Configure session concurrency/expired-session handling properly and test it.
- With Spring Session/Redis or distributed session stores, use the matching session registry/API and verify node B after node A revokes.
- Principal `equals`/`hashCode` can affect registry keys; custom principals should use stable identifiers.
- Destroying `HttpSession` and clearing `SecurityContextHolder` on the thread handles only that session, without revoking refresh tokens, JWTs, or external IdP SSO sessions.

**Two complementary strategies:** *push* events to invalidate sessions immediately upon change; *pull* per-request `authVersion`/status checks in case events are lost or delayed. When policies demand tight latency bounds, multi-node tests are required to prove compliance.

## 10. JWT/opaque tokens and controlled revocation

When using JWTs, clarify whether the system accepts any token with valid signature/issuer/audience/lifetime or requires the latest account status. A JWT can keep `roles=["ADMIN"]` until expiration after the DB removed the privilege. Options:

| Solution | Rejection scope | Trade-offs |
| --- | --- | --- |
| `jti` denylist | One specific token | Requires storing/syncing revocation state and TTL until expiration. |
| Grant/session ID revocation | One grant or token family | APIs must actually check the grant, not just token signatures. |
| `auth_version` claim vs. DB | All tokens carrying old versions | Version source must be fresh and checked at the resource server. |
| Membership version | Tokens/sessions in one tenant/membership | Needs proper subject+tenant scoping. |
| Short access JWT TTL | Limits stale window | Does not guarantee immediate revocation. |
| Opaque introspection | Status from authorization server | Depends on issuer, cache TTL, network, and failure modes. |

Refresh-token rotation/revocation prevents minting future access tokens, yet does not automatically invalidate old access JWTs at APIs that only verify signatures. For incident response, inventory **web sessions, remember-me, refresh grants, access tokens, API keys, and external IdP sessions** and define revocation policies for each.

## 11. Misconceptions to avoid

1. **"Since `isEnabled()` was checked at login, tomorrow's request is checked too."** False for standard stateful sessions: the context can just be a snapshot.
2. **"`isAuthenticated()` always re-calls `AuthenticationManager`."** False; it is a property on the object, not a re-verification operation.
3. **"Changing the password invalidates all cookies and JWTs."** False without explicit revocation.
4. **"Disabling an account in the DB instantly halts every HTTP request."** Not for requests already past checks or stale distributed caches.
5. **"Just calling `expireNow()` gives global logout."** Session markers do not guarantee immediate handling across all nodes or in-flight requests.
6. **"A validly signed JWT means the user still has that role today."** Claims can be a snapshot.
7. **"Re-enabling an account lets old cookies work again."** It should not if policy revoked them; `authVersion` must increase monotonically.
8. **"Refreshing authorities from the DB is enough for every transaction."** Object ownership/tenant scope, in-flight races, and policy authorization still need separate checks.
9. **"Adding one filter protects every authentication mechanism."** Not if principals have different types, belong to other security chains, or stateless endpoints bypass that filter.
10. **"During a DB outage, skip checks so the app stays up."** For sensitive operations, failing open can defeat the entire revocation policy.

## 12. Test matrix

| Test | Verification |
| --- | --- |
| Login while `enabled=true` | Authentication succeeds, principal/authorities accurate. |
| Disable post-login, keep old cookie | New request rejected per policy, session unusable. |
| Lock post-login | Verify whether policy blocks existing sessions. |
| Account expired post-login | Old context/token rejected or bounded per documented SLA. |
| Password reset | Old cookies and refresh grants handled per policy. |
| ADMIN role removed | Old session cannot keep using elevated privileges past freshness SLA. |
| ADMIN role granted | New privilege appears only per refresh/reauth policy, never mutating snapshots arbitrarily. |
| User deleted | Old context cannot remain usable when current account no longer exists. |
| Disable then re-enable | Revoked sessions/tokens **do not resurrect**. |
| JWT still before `exp` | Verify revocation/version/freshness if required by contract. |
| Opaque token revoked | Check introspection cache and effective cutoff time. |
| Multi-node A/B/C | Revoking on B must block requests on other nodes within SLA. |
| Cache TTL larger than SLA | Test exposes excessive lag; do not claim instant revocation. |
| Long-running request after revocation | Verify transactional authorization right before commit. |
| Status source times out | Never fail open for sensitive actions. |
| Multi-tenant user | Permissions/versions scoped per tenant; no cross-tenant role leakage. |
| Logout one browser | Copies of that cookie rejected server-side. |
| Logout all | Sessions/refresh grants/tokens within committed scope are terminated. |
| Custom `SecurityContextRepository` | Clears/persists context via right APIs, no orphaned sessions. |
| Audit/logging | Records actor/action/timestamp without leaking cookies/passwords/hashes/tokens. |

Do not only unit-test `accounts.disable(...)`. Test at least through the security filter chain and HTTP responses; when caching or clustering is present, run integration tests on production-like infrastructure to verify revocation timing.

## 13. Exercises with answers

**Question 1.** Alice logs in at 09:00 with `enabled=true`. Admin disables her at 09:05; Alice calls an endpoint with her old cookie and gets 200. Likely cause?

**Answer:** The `SecurityContext` stored in the session holds an authentication snapshot and does not re-query the database on subsequent requests. Session revocation or status/version checks are needed.

**Question 2.** `Authentication.isAuthenticated()` is true. Can you conclude the account is currently unlocked?

**Answer:** No. It does not automatically check the latest account status.

**Question 3.** The ADMIN role was revoked in the DB, yet `Authentication.getAuthorities()` in the old session still has `ROLE_ADMIN`. Is this a bug in `hasRole("ADMIN")`?

**Answer:** No. Authorization evaluates authorities stored in the context unless a refresh/revocation mechanism exists. Address freshness, not just matchers.

**Question 4.** `authVersion` at session issuance was 4; after disable it is 5; after re-enable it is 6. Does version 4 become valid again?

**Answer:** No. Only a new session issued after re-enablement with the matching version is valid.

**Question 5.** A JWT has 30 minutes left until `exp`; the user has been disabled. The resource server only verifies signature/`exp`. Will the JWT be rejected automatically?

**Answer:** No. You need a token revocation/version-check policy, or you must explicitly accept the assessed staleness window until expiration.

**Question 6.** Why does testing sessions with form login differ from testing HTTP Basic?

**Answer:** Form login typically maintains authentication via a session cookie, whereas HTTP Basic can send credentials on every request. The two flows verify credentials/accounts at different frequencies depending on configuration.

**Question 7.** Admin changes a role and bumps `authVersion` in the DB, yet the API reads from a replica lagging by 20 seconds while revocation SLA is under 5 seconds. Is the requirement met?

**Answer:** No. You must use a sufficiently fresh read source, cache invalidation, or suitable consistency design.

**Question 8.** A filter checks `enabled` before entering the controller; afterward, permission is revoked right before committing a money transfer. Was the filter enough?

**Answer:** No, if the transaction commitment forbids committing after revocation. Check permission/status close to the operation inside the transaction or an equivalent mechanism.

**Question 9.** When a user clicks "sign out all devices," is clearing the cookie in the current browser enough?

**Answer:** No. You must revoke server-side sessions and credentials that continue minting sessions/tokens across the system's committed scope.

## 14. References

- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `AuthenticationManager`, `SecurityContextHolder`.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): status/credentials during username/password authentication.
- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html): storing and restoring `SecurityContext`.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): session lifecycle, concurrent sessions, explicit-save.
- [Spring Security — UserDetails API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserDetails.html): the four account and credential states.
- [Spring Security — Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): validating JWTs and token validators.
- [Spring Security — Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html): token introspection.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session timeouts, lifecycle, and revocation.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): permission checks, least privilege, deny by default.

**Conclusion:** Successful authentication is a **point-in-time** event; account status, credentials, and permissions can change afterward. Never expect a single login-time check to invalidate every already-issued session or JWT. Choose **a trusted state source, validity windows, revocation/re-check mechanisms, and business-level authorization checkpoints**, and test old requests after the account changes — not just fresh logins.