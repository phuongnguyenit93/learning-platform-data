# Changing Permissions or Locking an Account When a User Already Has an Active Session

> **Scope:** Spring Security Servlet/Spring MVC, Java 17+, Spring Boot 3.x, and Spring Security 6.x. This lesson explains why changing roles or `enabled/locked` in the database **does not automatically update the `Authentication` already stored in `HttpSession`**, how to revoke sessions using `SessionRegistry`, why `SessionInformation.expireNow()` takes effect when a request returns, limitations with JWTs, remember-me, Redis/clusters, and how to test permissions before/after changes. The illustrative source code uses form login and sessions so the issue can be observed directly.

## 1. The Problem: The Database Changed, Yet the Browser Still Has Access?

Alice logs in at 09:00. The app verifies her password via `DaoAuthenticationProvider`/`UserDetailsService` and creates an `Authentication` with `ROLE_ADMIN`. The framework may store the `SecurityContext` holding this `Authentication` in **HttpSession**.

At 09:05, an administrator revokes Alice's `ADMIN` role in the database. However, Alice's session may still contain:

~~~text
SecurityContext in HttpSession:
    Authentication.name          = "alice"
    Authentication.authenticated = true
    Authentication.authorities   = ["ROLE_ADMIN"]

Database after modification:
    account.username             = "alice"
    account.enabled              = true
    account.roles                = ["ROLE_USER"]
~~~

If an endpoint only uses `.hasRole("ADMIN")` based on the current `Authentication`, the next request **may still be allowed**, because the old permission remains in the session. This is the difference between **persistent account source data** and an **authentication state snapshot** taken at login time.

Similarly, if an admin sets `enabled=false` or `locked=true` in the database, `DaoAuthenticationProvider` can block the **next login attempt**. However, it **is not automatically invoked again on every request** of an already-authenticated session. The old session may keep working until it expires, is revoked, or another status-checking mechanism runs.

**Three principles:**

1. **Changing account data** does not automatically mean **revoking all issued sessions**.
2. `UserDetailsService.loadUserByUsername()` is used during authentication, not as an automatic permission query on every HTTP request.
3. For permission changes/account locks to take effect quickly, you must decide the **check point**, **revocation mechanism**, **acceptable latency**, and **scope across multiple servers**.

## 2. Why Do Old Permissions Remain?

A typical form login flow looks like this:

~~~text
POST /login
   |
   v
UsernamePasswordAuthenticationFilter
   |
   v
AuthenticationManager / DaoAuthenticationProvider
   |
   +--> UserDetailsService.loadUserByUsername("alice")
   +--> PasswordEncoder.matches(raw, storedHash)
   +--> enabled, locked, accountExpired, credentialsExpired
   |
   v
Authenticated Authentication, containing authorities at login
   |
   v
SecurityContext saved via SecurityContextRepository
   |
   v
HttpSession holds SecurityContext
   |
   | Browser resends session cookie
   v
GET /admin
   |
   v
SecurityContextRepository restores old Authentication
   |
   v
AuthorizationFilter: hasRole("ADMIN")?
   |
   +--> Evaluates authorities in the active Authentication
   +--> Has old ROLE_ADMIN -> may ALLOW
~~~

As the user keeps browsing, Spring Security can **restore `Authentication` from the session** instead of repeating username/password authentication. The `isEnabled` and `isAccountNonLocked` flags on the old `UserDetails` instance do not automatically sync with the database either.

Here there are two kinds of **state**:

| Source | What data does it hold? | When does it usually change? |
| --- | --- | --- |
| Database/identity store | Roles, permissions, account locked/disabled, password hash, `securityVersion` | When an admin or system modifies the account |
| `Authentication` in `SecurityContext` | Principal, `GrantedAuthorities`, authentication state at creation/restoration | On login, reauthentication, refreshing/replacing `SecurityContext`, or session revocation |
| Session registry | Tracked sessions and invalidation status | On login/logout/session destroyed or an explicit expire command |
| Issued JWT | Claims, scope, expiry signed at issuance | Payload **does not change** after token issuance; must expire, revoke, or use server-side checks |

Never treat `getAuthorities()` as a live query to the role database. Authorities can become stale until the authentication context is refreshed.

### 2.1. Distinguishing password changes, permission changes, and account locks

| Event | New Authentication | Already-logged-in session | Risk |
| --- | --- | --- | --- |
| Revoke ROLE_ADMIN | New logins usually receive new roles | May still hold old ROLE_ADMIN | Allowed to continue admin operations |
| Grant ROLE_ADMIN | New logins receive new roles | May still lack ROLE_ADMIN | User denied even though DB granted it |
| Disable account | New logins rejected | May stay active | Disabled account retains access |
| Brute-force lock | New logins rejected | May stay active | Lockout bypassed by existing session |
| Password change/reset | New password effective on re-auth | Old sessions may remain open | Attacker with hijacked session keeps access |
| Revoke tenant/resource permission | New policy in DB | URL role rule may rely on stale roles | Risk of out-of-scope data access |
| Lock OAuth2 client | New tokens may be rejected | Issued access tokens may stay valid | Needs token revocation/expiry or live checks |

**Not every event requires immediate logout under the exact same policy.** Changing a display name may not require revoking sessions; revoking admin privileges or locking a compromised account usually needs fast enforcement and blocking residual access.

## 3. Does UserDetailsService Solve Permission Changes Automatically?

`UserDetailsService` defines only one core duty:

~~~java
UserDetails loadUserByUsername(String username)
    throws UsernameNotFoundException;
~~~

With form login or HTTP Basic, a provider can call this method to load the user, encoded password, authorities, and account status. However, a request whose `Authentication` is restored from a session may **never call that method again**.

### 3.1. Do not rely on loadUserByUsername being called on every request

An easy misunderstanding:

~~~java
@Service
public class MyUserDetailsService implements UserDetailsService {
    @Override
    public UserDetails loadUserByUsername(String username) {
        // Query latest DB roles...
    }
}
~~~

A good implementation only guarantees that **whenever the method is called, it returns accurate data at query time**. It does not guarantee `SecurityContextHolder` automatically updates `getAuthorities()` across all logged-in sessions.

Similarly, the following code in a Controller can read stale roles:

~~~java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

Collection<? extends GrantedAuthority> authorities =
    auth.getAuthorities();
~~~

This snippet is only meaningful when a request is protected by Spring Security and an `Authentication` is present. Do not grab these authorities and treat them as a continuously live permission source if business logic demands immediate revocation.

### 3.2. DaoAuthenticationProvider checks status at authentication time

Important `UserDetails` flags:

~~~java
boolean isEnabled();
boolean isAccountNonLocked();
boolean isAccountNonExpired();
boolean isCredentialsNonExpired();
~~~

The provider can throw `DisabledException`, `LockedException`, `AccountExpiredException`, or `CredentialsExpiredException` during authentication. **Flags on a `UserDetails` saved into a session do not re-read the DB themselves.** Thus an endpoint using only `.authenticated()` can still accept an old `Authentication`.

## 4. Choosing a Strategy When Permissions or Accounts Change

Different approaches fit different requirements:

| Strategy | Mechanism | Typical latency | Pros | Limitations |
| --- | --- | --- | --- | --- |
| **Revoke tracked sessions** | Mark expired/invalidate in session system | On the session's next checked request; may have event propagation delay | Forces user to re-login, loads fresh permissions | Requires complete session tracking, cluster-aware |
| **Check account status per request** | Filter/`AuthorizationManager` reads account enabled/version | Nearly every protected request | Quickly blocks even old sessions | Extra DB/cache calls; needs fail-closed and cache strategy |
| **Session holding securityVersion** | Store version at login, compare with account version | Per version check frequency | Easy to detect role/password/status changes | Needs version store and multi-node sync |
| **Short-lived access tokens** | Tokens expire quickly; no refresh when locked | Per TTL and clock skew | Shrinks stale-token window | Not instant revocation |
| **Token introspection/revocation** | Resource Server queries token status or denylist | Per check/cache TTL | Centralized token revocation | Increases AS/network/cache dependency |
| **Fresh resource-level authorization** | Service queries latest policy/owner/tenant when handling action | At policy check time | Protects resources even with stale session roles | Does not itself replace session `Authentication` or log out |
| **Proactive Authentication refresh** | Replace `SecurityContext` with fresh principal/roles via trusted flow | On refresh/reauth | Preserves user session if policy permits | Complex, race-prone; unsuitable for urgent account locks |

**There is no single Spring Security switch that revokes every session, JWT, remember-me cookie, OAuth2 client, and distributed token.** Choose based on authentication mechanism, risk, and real infrastructure.

## 5. SessionRegistry: Marking Sessions Expired

Spring Security Servlet supports **concurrent session management** with `SessionRegistry`, `SessionRegistryImpl`, `SessionInformation`, and `ConcurrentSessionFilter`.

Example of related APIs:

~~~java
List<Object> principals = sessionRegistry.getAllPrincipals();
List<SessionInformation> infos =
    sessionRegistry.getAllSessions(principal, false);

for (SessionInformation info : infos) {
    info.expireNow();
}
~~~

This is a **snippet** inside a service with an appropriate `sessionRegistry` and `principal`. `getAllSessions(principal, false)` retrieves active sessions known to the registry, while `expireNow()` **marks** `SessionInformation` as expired.

### 5.1. Does expireNow() immediately delete the HttpSession on the client?

**No.** `SessionInformation.expireNow()` marks a session in the **registry**. When the next request arrives using that session ID, `ConcurrentSessionFilter` can read the expired flag, execute logout/invalidation, and invoke `SessionInformationExpiredStrategy` to generate the response (e.g., redirect to login).

~~~text
Admin updates role or disables account
    |
    v
AccountStore/DB updated
    |
    v
SessionRegistry: session S1 -> expired=true
    |
    | Session may still exist until the next request
    v
Browser sends Cookie: JSESSIONID=S1
    |
    v
ConcurrentSessionFilter
    |
    +--> S1 expired?
             |
             +--> YES: logout/invalidate and expired response
             +--> NO: continue filter chain normally
~~~

**Consequence:** an idle browser session can persist until container expiration or handling, and a request that already passed the checkpoint before revocation may still be executing. This is **request-boundary revocation**, not an instant kill-switch for every in-flight operation.

### 5.2. Role of HttpSessionEventPublisher

`SessionRegistryImpl` maintains the principal ↔ session ID mapping and needs to receive session destroyed/expired events. In Spring Boot, you can register:

~~~java
@Bean
HttpSessionEventPublisher httpSessionEventPublisher() {
    return new HttpSessionEventPublisher();
}
~~~

When using `maximumSessions(...)` and a tracked registry, the listener keeps the registry's session lifecycle accurate. Without events—or if a custom authentication mechanism skips registering sessions—the registry can hold stale data or miss sessions.

**Standard `SessionRegistryImpl` is in-memory**, suitable for demos and single nodes. Multi-instance deployments require Spring Session/a distributed registry or a centralized revocation system. Node A's registry does not automatically know sessions created on node B.

### 5.3. maximumSessions(...) is not only for blocking a second login

Configuration:

~~~java
.sessionManagement(session -> session
    .maximumSessions(5)
    .sessionRegistry(sessionRegistry)
    .expiredUrl("/login?expired")
)
~~~

This enables concurrent session control, uses the supplied registry, and installs a filter capable of detecting expired `SessionInformation`. `maximumSessions(5)` is **a limit of at most 5 concurrent sessions per principal**, not a rule saying "auto-logout when roles change". You must explicitly call expire in an application service when account security state changes.

`expiredUrl` is an example of browser behavior: when a session has been marked expired and the browser revisits, it is redirected to `/login?expired`. For REST APIs, replace it with a `SessionInformationExpiredStrategy` returning 401 JSON; verify UX, cookie behavior, and actual entry points.

## 6. Spring Boot 3 / Java 17 Example: Change Roles Then Revoke Sessions

Demo goals:

1. Alice has `ROLE_USER`; admin has `ROLE_ADMIN`.
2. After form login, the session holds `Authentication` with authorities at authentication time.
3. Changing Alice's roles in the repository **does not automatically update the old session**.
4. An `AccountAdministrationService` updates the account and marks all registered sessions for the user expired.
5. When Alice sends a request with the old session, `ConcurrentSessionFilter` handles the expired session. Upon logging in again, `UserDetailsService` loads the new roles.
6. If the account is disabled, new logins are rejected; old sessions are marked for revocation.

The source code uses only **in-memory repository/SessionRegistry** for a single JVM, not a multi-node deployment template. Admin actions are invoked **directly from tests or internal services**; the demo does not expose an open HTTP endpoint to change roles or disable users.

### 6.1. Dependencies and file structure

Create a Spring Boot **3.x**, Java **17+** project with appropriate Gradle plugin/Wrapper. Add to your existing `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This block **is not the entire `build.gradle`**; plugins, repositories, and versions are provided by the Spring Boot project.

~~~text
src/main/java/com/example/sessionroles/
  SessionRolesApplication.java
  MutableAccountStore.java
  AccountAdministrationService.java
  SecurityConfig.java
  DemoController.java

src/test/java/com/example/sessionroles/
  SessionRevocationTest.java
~~~

### 6.2. SessionRolesApplication.java

~~~java
package com.example.sessionroles;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionRolesApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionRolesApplication.class, args);
    }
}
~~~

### 6.3. MutableAccountStore.java — account data and user source

~~~java
package com.example.sessionroles;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class MutableAccountStore implements UserDetailsService {

    private record Account(
        String username,
        String hash,
        boolean enabled,
        Set<String> authorities
    ) {}

    private final ConcurrentMap<String, Account> accounts =
        new ConcurrentHashMap<>();

    public MutableAccountStore(PasswordEncoder encoder) {
        accounts.put("alice", new Account(
            "alice",
            encoder.encode("alice123"),
            true,
            Set.of("ROLE_USER")
        ));
        accounts.put("admin", new Account(
            "admin",
            encoder.encode("admin123"),
            true,
            Set.of("ROLE_ADMIN")
        ));
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        Account account = accounts.get(username);
        if (account == null) {
            throw new UsernameNotFoundException("Invalid credentials");
        }

        return User.withUsername(account.username())
            .password(account.hash())
            .authorities(account.authorities().toArray(String[]::new))
            .disabled(!account.enabled())
            .build();
    }

    public void replaceAuthorities(
            String username, Set<String> authorities) {
        if (authorities == null || authorities.isEmpty()) {
            throw new IllegalArgumentException(
                "Specify at least one authority for this demo"
            );
        }

        Set<String> trustedAuthorities = Set.copyOf(authorities);

        accounts.compute(username, (key, previous) -> {
            if (previous == null) {
                throw new IllegalArgumentException("Account not found");
            }
            return new Account(
                previous.username(), previous.hash(),
                previous.enabled(), trustedAuthorities
            );
        });
    }

    public void disable(String username) {
        accounts.compute(username, (key, previous) -> {
            if (previous == null) {
                throw new IllegalArgumentException("Account not found");
            }
            return new Account(
                previous.username(), previous.hash(),
                false, previous.authorities()
            );
        });
    }
}
~~~

**Analysis:**

- The in-memory store uses `ConcurrentHashMap`, not a production database. Swap to a JPA/JDBC repository in real apps.
- Passwords are hashed by the encoder when creating demo data; `loadUserByUsername` only returns the **existing hash**, without re-encoding.
- `.disabled(!account.enabled())` converts the flag direction properly. A disabled account will be rejected by `DaoAuthenticationProvider` on the **next login**.
- `replaceAuthorities` builds a new account record instead of mutating a `UserDetails` sitting in a session. The old session thus keeps its initial authorities—cleanly illustrating the problem.
- `Set.copyOf` ensures the record's permission set cannot be mutated via the caller's reference in the example; **never accept authorities from untrusted client requests**.
- The demo lacks a `locked` state; in a real database, `locked=true` maps to `UserDetails.isAccountNonLocked()==false`, usually via builder `.accountLocked(account.locked())`.

### 6.4. SecurityConfig.java — form login, SessionRegistry, and ConcurrentSessionFilter

~~~java
package com.example.sessionroles;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    DaoAuthenticationProvider daoAuthenticationProvider(
            MutableAccountStore accounts,
            PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(accounts);
        provider.setPasswordEncoder(encoder);
        return provider;
    }

    @Bean
    SessionRegistry sessionRegistry() {
        return new SessionRegistryImpl();
    }

    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            DaoAuthenticationProvider provider,
            SessionRegistry registry) throws Exception {

        http
            .authenticationProvider(provider)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/me").authenticated()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            .sessionManagement(session -> session
                .maximumSessions(5)
                .sessionRegistry(registry)
                .expiredUrl("/login?expired")
            );

        return http.build();
    }
}
~~~

**Why is it configured this way?**

1. `DaoAuthenticationProvider` verifies credentials using `MutableAccountStore` + BCrypt.
2. `formLogin` creates a **username/password + HttpSession** flow, making the `Authentication` snapshot easy to observe.
3. `SessionRegistryImpl` tracks registered sessions.
4. `HttpSessionEventPublisher` forwards session-destroyed events so the registry does not retain nonexistent sessions.
5. `maximumSessions(5)` enables concurrent session support, including `ConcurrentSessionFilter` which detects sessions marked by `expireNow()`.
6. `sessionRegistry(registry)` ensures the revocation service and the filter share the exact same registry.
7. `expiredUrl("/login?expired")` redirects browsers sending requests with sessions marked expired.
8. `.hasRole("ADMIN")` evaluates authorities **inside the active `Authentication`**, without querying the DB itself.
9. `anyRequest().denyAll()` blocks undeclared endpoints.

**Login page note:** `formLogin()` provides a generated login page via security filters. `GET /login` has no handwritten controller; the form login filter/page is handled by the framework. If a project uses a custom login page, permit the appropriate URL and related static assets.

**CSRF remains enabled.** `POST /login` in tests will use Spring Security Test to submit a valid CSRF token. Do not disable CSRF just to make the demo run.

### 6.5. AccountAdministrationService.java — changing roles/disabling and expiring sessions

~~~java
package com.example.sessionroles;

import java.util.Set;

import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.stereotype.Service;

@Service
public class AccountAdministrationService {

    private final MutableAccountStore accounts;
    private final SessionRegistry registry;

    public AccountAdministrationService(
            MutableAccountStore accounts,
            SessionRegistry registry) {
        this.accounts = accounts;
        this.registry = registry;
    }

    public void replaceAuthorities(
            String username, Set<String> authorities) {
        accounts.replaceAuthorities(username, authorities);
        expireSessions(username);
    }

    public void disable(String username) {
        accounts.disable(username);
        expireSessions(username);
    }

    public void expireSessions(String username) {
        for (Object principal : registry.getAllPrincipals()) {
            if (principal instanceof UserDetails user
                    && username.equals(user.getUsername())) {

                for (SessionInformation session :
                        registry.getAllSessions(principal, false)) {
                    session.expireNow();
                }
            }
        }
    }
}
~~~

**Distinguish three operations:**

- `accounts.replaceAuthorities(...)` changes permissions in the account source. It does not change `Authentication` stored in sessions.
- `accounts.disable(...)` causes **new logins** to be rejected by standard providers.
- `expireSessions(...)` finds **registered sessions** matching the username and marks them `expired`. When the next request uses that session, the filter handles logout/invalidation.

This method relies on `principal instanceof UserDetails` and stable usernames in a single demo. **Real products should use an immutable account ID + verified tenant ID** as the revocation key, because usernames/emails can change or collide across tenants. If the principal is an `OidcUser`/`Jwt`/custom principal, replace the identification logic with the actual type. `SessionRegistryImpl` uses `equals/hashCode` on principals, so custom `UserDetails` must implement them stably.

**This is an internal service.** Never create a public `GET /disable?user=...`. A real admin API needs `@PreAuthorize`/HTTP authorization for privileged actions, CSRF if browsers use cookies, validation, auditing, concurrency control, and DB transactions.

### 6.6. DemoController.java

~~~java
package com.example.sessionroles;

import java.util.stream.Collectors;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        String roles = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .collect(Collectors.joining(","));

        return authentication.getName() + ":" + roles;
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin-only";
    }
}
~~~

After initial login as Alice, `GET /me` is expected to return `alice:ROLE_USER`. If an admin grants Alice `ROLE_ADMIN` **without revoking her session**, the old `Authentication` may still return `alice:ROLE_USER`; after revoking the session and Alice logging in again, the response may be `alice:ROLE_ADMIN,ROLE_USER`.

**Never return raw `Authentication`/`UserDetails`** as JSON; it may contain encoded passwords, authorities, and metadata not meant to be public. The demo's response string is solely for observing roles.

## 7. MockMvc Test: Proving Stale Permissions, Fresh Permissions, and Account Locks

Create `src/test/java/com/example/sessionroles/SessionRevocationTest.java`:

~~~java
package com.example.sessionroles;

import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class SessionRevocationTest {

    @Autowired MockMvc mvc;
    @Autowired MutableAccountStore accounts;
    @Autowired AccountAdministrationService adminService;
    @Autowired SessionRegistry registry;

    private MockHttpSession login(String username, String password)
            throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", username)
                .param("password", password))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);

        assertNotNull(session);
        return session;
    }

    @Test
    void changingRolesInStoreDoesNotRefreshExistingSession()
            throws Exception {
        MockHttpSession session = login("alice", "alice123");

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("alice:ROLE_USER"));

        accounts.replaceAuthorities(
            "alice", Set.of("ROLE_USER", "ROLE_ADMIN"));

        // Not yet revoked: session retains the previous Authentication.
        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("alice:ROLE_USER"));

        mvc.perform(get("/admin").session(session))
            .andExpect(status().isForbidden());
    }

    @Test
    void changingRoleThroughServiceExpiresOldSession()
            throws Exception {
        MockHttpSession oldSession = login("alice", "alice123");

        adminService.replaceAuthorities(
            "alice", Set.of("ROLE_USER", "ROLE_ADMIN"));

        SessionInformation tracked =
            registry.getSessionInformation(oldSession.getId());

        assertNotNull(tracked);
        assertTrue(tracked.isExpired());

        mvc.perform(get("/me").session(oldSession))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?expired"));

        MockHttpSession newSession = login("alice", "alice123");

        mvc.perform(get("/admin").session(newSession))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-only"));

        mvc.perform(get("/me").session(newSession))
            .andExpect(status().isOk())
            .andExpect(content().string("alice:ROLE_ADMIN,ROLE_USER"));
    }

    @Test
    void disablingAccountExpiresOldSessionAndRejectsNewLogin()
            throws Exception {
        MockHttpSession oldSession = login("alice", "alice123");

        adminService.disable("alice");

        SessionInformation tracked =
            registry.getSessionInformation(oldSession.getId());

        assertNotNull(tracked);
        assertTrue(tracked.isExpired());

        mvc.perform(get("/me").session(oldSession))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?expired"));

        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "alice123"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void revocationTargetsOnlySpecifiedAccount()
            throws Exception {
        MockHttpSession aliceSession = login("alice", "alice123");
        MockHttpSession adminSession = login("admin", "admin123");

        adminService.replaceAuthorities(
            "alice", Set.of("ROLE_USER", "ROLE_ADMIN"));

        SessionInformation alice =
            registry.getSessionInformation(aliceSession.getId());

        SessionInformation administrator =
            registry.getSessionInformation(adminSession.getId());

        assertNotNull(alice);
        assertNotNull(administrator);
        assertTrue(alice.isExpired());
        assertFalse(administrator.isExpired());

        mvc.perform(get("/admin").session(adminSession))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-only"));
    }
}
~~~

Run tests in the Gradle project root:

~~~bash
./gradlew test
# Windows PowerShell/cmd:
gradlew.bat test
~~~

**How to read the test suite:**

1. `changingRolesInStoreDoesNotRefreshExistingSession`: changing roles only in the account store does not automatically change the old session's `Authentication`.
2. `changingRoleThroughServiceExpiresOldSession`: the service updates permissions and marks the old session expired; the next request is redirected to login; a new session gets updated permissions.
3. `disablingAccountExpiresOldSessionAndRejectsNewLogin`: disabling the account both expires tracked sessions and causes new logins to fail.
4. `revocationTargetsOnlySpecifiedAccount`: does not accidentally revoke other users' sessions.
5. `@DirtiesContext` creates a fresh context after each test so mutations in the in-memory account store/registry from earlier tests do not affect later ones.
6. `csrf()` is sent on `POST /login` because CSRF remains enabled. This is a test request postprocessor, not a reason to disable `CsrfFilter`.

**The results above are expected assertions of the example code, not a report that Gradle was executed here.** When using Spring Security 7/Boot 4 or custom login page/session strategies, check APIs and redirect behavior per version.

### 7.1. Anti-pattern: revoking ROLE_ADMIN but forgetting to expire

This is more dangerous than delayed privilege grants.

~~~text
At login:
  admin account -> Authentication authorities=[ROLE_ADMIN]

Admin adjusts DB:
  account.authorities=[ROLE_USER]

Without expiring old session:
  GET /admin from old session
      -> hasRole("ADMIN") relies on old Authentication
      -> may still ALLOW

With expiring old session and filter detecting expired:
  GET /admin from old session
      -> ConcurrentSessionFilter blocks and terminates session
      -> requires new login with ROLE_USER
      -> /admin is no longer permitted
~~~

**Permission revocation** must be treated as a security event, not merely an edited column in the account table.

## 8. When an Account Is Locked, What Must Be Done?

At the data level, locking an account can be represented by `enabled=false`, `locked=true`, or a dedicated business status. Pick a consistent policy understood by both the provider and all other access paths.

### 8.1. Handling new logins

Standard `DaoAuthenticationProvider` uses the `UserDetails` flags:

| Flag | Meaning when false | Typical authentication outcome |
| --- | --- | --- |
| `isEnabled()` | Account is disabled | `DisabledException` |
| `isAccountNonLocked()` | Account is locked | `LockedException` |
| `isAccountNonExpired()` | Account has expired | `AccountExpiredException` |
| `isCredentialsNonExpired()` | Credentials have expired | `CredentialsExpiredException` |

Internal exceptions can be mapped to a generic login error for clients to avoid revealing too much about the account. Default form login usually redirects to `/login?error`; Basic may return 401. Exact HTTP responses depend on entry points and handlers.

### 8.2. Handling active sessions

With proper session tracking, you can expire sessions tied to the locked account. However, if sessions are unknown to the registry or reside on another node, the demo's command may miss them.

For **emergency account locks due to compromise**, you should also:

- Revoke appropriate refresh tokens/grants at the IdP/Authorization Server.
- Revoke server-side sessions across all nodes/devices.
- Block issuance of new sessions/tokens during login/token refresh.
- Check alternative access paths: remember-me, magic links, API keys, service credentials, OAuth2 logins.
- For sensitive endpoints, check account status/security version at action time.
- Write audit logs with actor, target account, reason, timestamp, correlation ID, number of affected sessions, and execution outcome.

### 8.3. Should changing a password log out all devices?

It depends on intent. When a user changes their own password inside a secure session, some products keep the current session and revoke other sessions; when a password is reset due to suspected credential compromise, revoking all sessions may be required. Designs must specify clear behavior for the current session, other sessions, refresh tokens, and devices.

If code revokes the very session calling the admin action, completion responses may vary with session invalidation timing. Never assume a delete-all-sessions command is instantaneous and transactional across all systems.

## 9. The securityVersion Approach to Detect Stale Sessions

A system needing faster reaction can maintain a **`securityVersion`** or **`authzVersion`** incremented whenever roles, lock state, passwords, or tenant policies change.

~~~text
At login:
  Account.securityVersion = 42
  Session.securityVersion = 42

Admin changes permissions:
  Account.securityVersion = 43

Next request:
  Read Session.securityVersion = 42
  Read Account.securityVersion = 43
  42 != 43 -> reject / reauthenticate / invalidate
~~~

Illustrative condition:

~~~java
// Snippet with accountId/version from trusted principal and trusted store.
boolean sessionStillValid(
        long versionAtLogin, long currentAccountVersion,
        boolean accountEnabled) {

    return accountEnabled
        && versionAtLogin == currentAccountVersion;
}
~~~

Do not copy that method into a demo and assume it suffices: you need code to **load trusted accountId/version**, store the version in Authentication/session at login, integrate the checker across **all protected access paths**, and produce appropriate responses/clear `SecurityContext`.

**Benefit:** Stale sessions can be detected without knowing session IDs, even if a registry missed them. **Cost:** reading the version store/cached value per request, solving cache invalidation, outage behavior, races, and multi-region propagation.

### 9.1. Where should the version check live?

It can be an appropriate servlet filter, a custom `AuthorizationManager` applied to endpoints, or a service guard before sensitive actions. Avoid:

- Placing the guard after the business transaction already executed.
- Checking version only on `/admin` while forgetting other data-fetching endpoints.
- Reading account ID from a client-chosen `request.getParameter("userId")`.
- Failing open when the DB/cache version service errors while policy demands fail-closed.
- Caching "enabled=true" longer than the account-lock SLA.
- Relying solely on an `isAuthenticated()` boolean without checking account status/version.
- Losing version synchronization when admins edit roles across multiple systems.

For sensitive resources, checking in the service/repository right before commit narrows the gap between the request-start check and the final action. Even so, transaction isolation and race conditions still matter.

### 9.2. Let old sessions refresh permissions or require re-login?

Two policies exist:

1. **Fail closed and require re-login:** when session version differs from current version, revoke/deny. Easy to understand, suitable for demotions, locks, and credential changes.
2. **Refresh Authentication from trusted source:** load new authorities and replace `SecurityContext` in a controlled reauthentication flow; can support privilege grants without forcing logout, yet must ensure unverified permissions are never pulled in and handle concurrency.

**Never mutate `authentication.getAuthorities()` on one request assuming all other sessions updated.** `Authentication` may be immutable, principals shared/cached, sessions replicated, and authorization data baked into tokens. For high privilege elevations, require recent authentication or MFA.

## 10. Tokens and Sessions: Do Not Use the Same Revocation Method

### 10.1. Browser HttpSession

Sessions are stored on the server or a distributed session store; given session IDs and proper management APIs, the system can invalidate them. `SessionRegistryImpl` tracks sessions in one JVM; `SessionInformation.expireNow` relies on the next request hitting `ConcurrentSessionFilter`.

### 10.2. HTTP Basic

Basic requests typically carry username/password every time; the provider can call `UserDetailsService` and observe newly disabled accounts. However, **never assume every Basic deployment checks the database on every request**: caches, session policies, or custom filters/managers may behave differently. Verify the real chain and provider.

### 10.3. JWT access tokens are not HttpSessions

Signed JWTs hold claims that do not change after issuance. If `ROLE_ADMIN` is revoked from a user in the database yet an old access token still carries that role/scope, a Resource Server checking only signature, issuer, expiry, and token claims may continue accepting the token until expiration.

`SessionRegistry.expireNow()` **does not automatically invalidate JWTs**. You need one or a combination of:
- Short JWT TTLs and bounded refresh.
- A revocation list for token IDs (`jti`) or per-subject session/security versions.
- Checking account/permission status from a trusted source at the required frequency.
- Token introspection or a backend-for-frontend/session gateway when centralized revocation is needed.
- Resource-layer authorization always checking ownership/tenant/critical permissions.

Self-contained JWTs scale easily and reduce lookups, at the cost of **difficulty revoking immediately if APIs verify offline only**. Protect properly based on threat model, rather than casually using 24-hour JWTs for all sensitive permissions.

### 10.4. Opaque tokens / introspection

A Resource Server using opaque token introspection can ask the Authorization Server whether a token is still `active` and what permissions it holds. However, introspection caching and network failures can introduce revocation latency. Define clear policies for introspection failures, cache TTLs, and revoked tokens.

### 10.5. Refresh tokens and OAuth2 login

Revoking an access token while **the refresh token remains valid** can allow obtaining new access tokens if the Authorization Server does not check account status or grants. When disabling accounts or resetting passwords, revoke refresh tokens/grants per IdP capabilities; one user across multiple apps/devices may hold multiple token families.

With OAuth2 Login, the application session may stay alive after a user is disabled at the IdP. Single Logout, back-channel logout, or local session invalidation must be designed explicitly; never assume locking a user at the IdP instantly notifies the app.

### 10.6. Remember-me

A remember-me cookie/token can automatically build a fresh `Authentication` on a later request after the session expires. When locking an account or changing passwords, ensure the remember-me mechanism is invalidated and revalidated. Persistent remember-me tokens have their own store/rotation; do not expire a session only to let a remember-me cookie silently restore a new session unintentionally.

## 11. Multi-Node, Spring Session, and Distributed Registries

`SessionRegistryImpl` keeps session tracking in JVM memory. If Spring Boot runs three nodes behind a load balancer:

~~~text
Browser -> Load Balancer
              |
              +--> node A: registry A
              +--> node B: registry B
              +--> node C: registry C

Admin revokes on node A
    |
    +--> Registry A knows sessions tracked by A
    +--> Sessions handled on B/C may be absent from A
~~~

Even when using a shared session store (Redis/JDBC) for `HttpSession`, an in-memory registry **does not automatically become distributed**. Choose a session registry compatible with Spring Session, a shared revocation store, pub/sub events, or a shared security-version checking layer.

### 11.1. Spring Session

Spring Session supports centralized session stores and integrates with Spring Security. Where appropriate, use `SpringSessionBackedSessionRegistry` (per module/version) or session repository APIs to list/revoke sessions by a trusted principal.

**Never use an in-memory `SessionRegistryImpl` as the cluster-wide session source** and claim to revoke all devices. Check Redis/JDBC TTLs, expiration events, serialization, principal indexes, namespaces, and remote session deletion behavior per library version.

### 11.2. Races and latency

Critical windows:

1. Admin DB update commits, yet the revocation event is not yet emitted.
2. Revocation event is emitted, yet one node has not received it.
3. Browser started a request just before the account was locked.
4. Session is marked expired, yet the request has not reached `ConcurrentSessionFilter`.
5. Role/version cache still holds stale values.
6. Already-issued JWTs live until `exp` or until the resource server checks a denylist.

For sensitive systems, define a **revocation SLA** (e.g., new requests must be blocked within a specific bound), measure with real multi-node tests, and add **account status/version guards** for critical operations.

### 11.3. Transactions and consistency

A production workflow typically needs:

~~~text
Admin sends role-change/disable request
    |
    v
Verify actor has permission and target is valid
    |
    v
DB transaction:
    - update account roles/status
    - increment securityVersion
    - save audit/outbox event
    |
    v
Commit
    |
    v
Publish revocation event to session/token components
    |
    v
Nodes/caches update; sessions/tokens expire/revoke
    |
    v
Monitor, retry, reconcile any remaining sessions
~~~

If the DB update and registry expiration **are not in the same distributed transaction**, you need retry/outbox workflows so events are not lost. Never update account data and assume all JWTs/sessions across regions are guaranteed revoked.

**Protecting sensitive data also requires authorization inside the request itself**: a request that passed filters before revocation may still be running. For dangerous transactions, a guard close to commit time may be necessary.

## 12. Checking Updated Permissions Per Request

Sometimes the business requirement is: **revoking `invoice:approve` takes effect immediately for new transactions**, without necessarily logging the user out of the entire app. Then you can separate:

- **Authentication:** the session holds only the verified user's stable identifier.
- **Authorization:** each approval decision queries current permissions for the account/tenant/document or checks `securityVersion`.
- **Session revocation:** still used for account locks, lost credentials, compromise, or forced reauthentication policies.

Method security snippet example:

~~~java
@PreAuthorize(
    "@invoicePolicy.canApprove(authentication, #invoiceId)"
)
public void approveInvoice(long invoiceId) {
    // Update invoice inside an appropriate service/transaction.
}
~~~

This snippet needs `@EnableMethodSecurity` and an `invoicePolicy` bean you implement. `canApprove` must take the verified identity from `Authentication`, check that the account is enabled, check updated permissions, owner/tenant, and invoice status. Never treat client-sent `invoiceId` and `userId` as verified facts.

`@PreAuthorize` checks before method invocation, yet sensitive transactions may need additional domain/DB checks if state changes between check and commit. A role snapshot in the session is no excuse to skip resource-level authorization.

### 12.1. Custom AuthorizationManager

Spring Security allows plugging `AuthorizationManager<RequestAuthorizationContext>` into `.authorizeHttpRequests`. Conceptual example:

~~~java
// Snippet: accountPolicy bean must have a real implementation.
// Do not treat this snippet as a complete filter/bean.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/sensitive/**")
    .access((authentication, context) ->
        new AuthorizationDecision(
            accountPolicy.allowCurrentRequest(
                authentication.get(),
                context.getRequest()
            )
        )
    )
    .anyRequest().authenticated()
);
~~~

Ensure the policy never trusts anonymous `Authentication`, never ignores locked/version status, and handles account-store errors fail-closed. Specific Spring Security 6.x APIs may return `AuthorizationDecision` or a version-compatible contract; check your project dependencies.

### 12.2. Permission caching and invalidation

If querying DB roles on every request is too expensive, you can cache `accountId → {enabled, securityVersion, permissions}` with a short TTL and invalidation events. **Caching must be conditionally designed**: a 30-minute TTL means permission revocation can lag up to 30 minutes if the cache is not invalidated.

Define the source of truth, update ordering, fallback when Redis/DB fails, and endpoints requiring fresh checks. For dangerous permissions, never default to **fail-open** when the policy service times out.

## 13. Observing Runtime State and Troubleshooting

### 13.1. Why can a user still access /admin after their role was revoked?

Check step by step:

1. Which cookies/sessions does the browser still hold? Are there multiple subdomains, multiple session stores, or a remember-me cookie?
2. Which `SecurityFilterChain` does the request match? Is another chain using `permitAll()` or skipping authorization?
3. Was `SecurityContext` restored from an old session or created fresh? Are principal/authorities of the right type/source?
4. Did DB role changes commit, and were caches invalidated?
5. Did the admin update call the revocation service, and did the event reach all nodes?
6. Did the session registry register the right principal/session ID? Are `maximumSessions` and the event publisher configured?
7. Did the post-revocation request pass through `ConcurrentSessionFilter`?
8. Is there an unexpired old JWT/token containing `ROLE_ADMIN` or `scope=admin`?
9. Does the API actually enforce `hasRole("ADMIN")`/resource policy on that exact endpoint?
10. Was a transaction already running prior to revocation?

**Never solve this merely by shortening or lengthening session timeouts**: long timeouts extend the stale-permission window. Precise revocation/authorization is required.

### 13.2. Why did the user not receive newly granted permissions?

This can also be the session snapshot. On role upgrades, a safe option is having the user log in again or reauthenticate; with an authority refresh mechanism, ensure updates come from a trusted source and `SecurityContext` is persisted properly. Never let clients send roles or `authenticated=true` to gain new permissions.

### 13.3. SessionRegistry is empty even though users are logged in

Common causes:

- A custom authentication mechanism did not invoke the session authentication strategy / did not register the session.
- The app uses `STATELESS`, JWT/Bearer tokens, and has no server-side `HttpSession`.
- The session registry was not wired into the chain actually in use.
- Multiple registry beans/instances or multiple app nodes exist.
- Sessions expired without events/`HttpSessionEventPublisher` wired properly.
- Sessions were created before tracking was enabled.
- The principal is a custom object with unstable `equals/hashCode`.
- Login used one chain while requests hit another chain.
- Tests only injected `@WithMockUser`, skipping form login and creating no real session known to the registry.

**A session registry that does not know about a session cannot revoke it.** Test through a real authentication flow or one matching deployment.

### 13.4. Session is expired yet the endpoint still returns 200

Check:
- Does the request carry the exact `JSESSIONID` that was marked?
- Is `ConcurrentSessionFilter` present on the chain receiving the request?
- Are requests hitting the same registry/node or a shared registry?
- Is another token in a header re-authenticating via a filter and replacing `Authentication`?
- Is an endpoint bypassing the chain or served as a static resource/CDN?
- Did the request start before the expire call?

Do not conclude `expireNow()` took immediate effect merely because `SessionInformation.isExpired()` returns true. Test real requests and cutoff timing.

## 14. When Should Forced Logout Apply?

A suggested matrix for policy design (not a mandatory standard for every product):

| Event | Recommendation |
| --- | --- |
| Revoking admin role or sensitive permission | Revoke related sessions/tokens, and check live permissions on sensitive actions |
| Account disabled/locked due to security incident | Revoke across all nodes/devices, block login/refresh, audit |
| Password reset due to suspected compromise | Revoke many or all sessions/tokens per policy, force re-authentication |
| User granted new permission | May re-login/reauth to acquire new rights; avoid unverified self-escalation |
| Changing display name/avatar | Usually no logout needed if security identity is unaffected |
| Changing recovery email/phone | May need step-up/MFA, auditing, and risk-based revocation |
| JWT issued with wrong scopes | Revoke/denylist or reduce TTL; fix issuer/claims to stop re-issuance |
| Service credential leaked | Rotate/revoke client credentials and corresponding access/refresh tokens |

Do not apply "log out on every account change" if it causes unnecessary disruption. What matters is identifying **security-relevant changes** and desired enforcement speed.

## 15. Tests Needed in a Real Project

Beyond the demo tests, a production system should test:

- **Role demotion:** a user who had ADMIN can no longer perform admin actions on an old session after revocation.
- **Role promotion:** a new session or refresh mechanism picks up new roles; old sessions behave per policy.
- **Disable account:** with active sessions and tokens, after disable protected actions fail; login/refresh are rejected.
- **Lock and unlock:** test login status and policy on revoked sessions; unlocking must not resurrect already-revoked sessions.
- **Password change:** new password works, old password is rejected; session/token policy is consistent.
- **Multiple sessions/devices:** revoke all or all except current session as required; never revoke another account by mistake.
- **Multiple nodes:** revoking on node A affects requests on B/C within the revocation SLA.
- **Remember-me:** old cookies must not silently recreate access against policy.
- **JWT:** already-issued access tokens, refresh tokens, new tokens after role change, expiry, denylist/introspection.
- **Concurrent requests:** in-flight requests started before revocation, transaction commits, and authorization guards.
- **Failure modes:** DB/cache/event-bus errors, missing registry entries, duplicate revocations, and retry/outbox.
- **Audit:** actor, target ID, reason, timestamp, affected session/token count, correlation ID, and outcome.

### 15.1. Do not use mock users to prove session revocation

`@WithMockUser` or `SecurityMockMvcRequestPostProcessors.user(...)` constructs an `Authentication` for authorization testing without passing through form login/DAO provider and without registering an `HttpSession` in `SessionRegistry`.

To test session revocation, **log in via `POST /login` with a CSRF token and retain the `MockHttpSession`**, as in Section 7. Then update account data, mark expired, and send another request with **the same session ID**.

### 15.2. Do not assert only the session flag

A test that only calls:

~~~java
SessionInformation info = registry.getSessionInformation(sessionId);
assertTrue(info.isExpired());
~~~

proves the registry entry was marked, yet **does not prove real requests lose access**. The test in Section 7 also sends `GET /me` with the old session, expecting a login redirect. For JSON APIs, assert the exact 401/error body per your configured `SessionInformationExpiredStrategy`.

### 15.3. HTTP 401, 403, and 302 differ

- `401 Unauthorized` is typical when an API requires authentication or credentials fail.
- `403 Forbidden` is typical when authenticated yet lacking permissions, or blocked by CSRF.
- `302`/`3xx` redirect to login is common with form login or expired-session strategies.

Being locked in the DB does not guarantee every request returns `401`. With form login, authentication failure usually redirects; with an expired session it may redirect to `/login?expired`. Distinguish **authentication errors**, **authorization errors**, and **revoked sessions** in tests/observability.

## 16. Self-Assessment Questions

**Q1.** Alice has `ROLE_ADMIN` in her `HttpSession`; an admin revokes that role in the DB. Does `.hasRole("ADMIN")` automatically update from the DB?

**A:** Not by default. It typically evaluates authorities on the current `Authentication`, which may still hold the old role.

**Q2.** Does setting `enabled=false` immediately force every open session to log out?

**A:** Not by default. It affects new authentications via the provider; existing sessions need revocation or live checks.

**Q3.** Is `UserDetailsService.loadUserByUsername` called on every request in a session?

**A:** Not guaranteed. Spring Security can restore the saved `Authentication` from `HttpSession`.

**Q4.** Does `SessionInformation.expireNow()` immediately abort in-flight requests and delete the browser cookie?

**A:** No. It marks the session expired; `ConcurrentSessionFilter` detects it on the next request, handles logout/invalidation, and responds per strategy.

**Q5.** Why is `HttpSessionEventPublisher` needed in session tracking configs?

**A:** So session events like destroy/expire are forwarded to tracking components, keeping `SessionRegistry` lifecycle data accurate.

**Q6.** Does `maximumSessions(1)` automatically revoke a user when DB roles change?

**A:** No. It limits concurrent sessions; role changes must trigger explicit revocation if desired.

**Q7.** Can `SessionRegistryImpl` on node A automatically find node B's sessions?

**A:** Not by default. It is an in-memory registry; cluster-aware mechanisms or shared stores/events are required.

**Q8.** Does an already-issued JWT containing `ROLE_ADMIN` automatically turn into `ROLE_USER` when the DB changes?

**A:** No. Signed claims do not mutate; expiry, revocation, introspection, version checks, or live authorization are required.

**Q9.** Does changing a password automatically invalidate refresh tokens and remember-me cookies?

**A:** Not guaranteed. Token families, grants/cookies, and revocation must be managed per the actual mechanisms.

**Q10.** Can you rely solely on `authentication.isAuthenticated()` to know a user is not locked?

**A:** No. An old `Authentication` can still report true even if the DB account is disabled.

**Q11.** What does `securityVersion` solve?

**A:** It allows comparing login-time security state against current state and rejecting stale contexts right at the checkpoint, though it requires a reliable version store and cache policy.

**Q12.** When a new role is granted, is it mandatory to "mutate the Authentication object inside the session"?

**A:** No. Forcing re-login is a clear solution; refreshing `Authentication` should only happen via a trusted mechanism with proper context persistence.

**Q13.** For critical transactions, is checking roles in an HTTP filter always enough?

**A:** Not necessarily. Resource/tenant permissions are required, and re-checking close to transaction commit may be needed to reduce races.

**Q14.** Is testing with `@WithMockUser` enough to prove `SessionRegistry` revokes properly?

**A:** No. Mock users skip full form-login/session-registration flows; test with a real MockMvc session or integration test.

**Q15.** When a revocation event is lost on a message broker, what should be done?

**A:** Use transactions/outbox, retry/reconciliation or live version checks, and design sensitive actions to fail closed.

## 17. Official References

- Spring Security 6.5 — **Authentication Persistence and Session Management**: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security — **Concurrent Session Control**: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — **Authorize HTTP Requests**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — **Authentication Architecture**: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — **UserDetailsService**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html
- Spring Security 6.5 API — **SessionRegistry**: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/session/SessionRegistry.html
- Spring Security 6.5 API — **SessionInformation**: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/session/SessionInformation.html
- Spring Security 6.5 API — **ConcurrentSessionFilter**: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/session/ConcurrentSessionFilter.html
- Spring Session — **Spring Security Integration**: https://docs.spring.io/spring-session/reference/guides/boot-redis.html
- Spring Security — **OAuth2 Resource Server JWT**: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- OWASP — **Session Management Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html

**Key takeaway:** Changing roles or locking an account in the user source **does not automatically alter an `Authentication` already sitting in a session**. For session-based apps, manage and revoke tracked sessions via `SessionRegistry`/`ConcurrentSessionFilter`, or verify `securityVersion`/account status on requests. For JWTs and multi-node systems, dedicated revocation/validation is required. **Revoking sensitive permissions must be verified with real requests on old sessions or tokens**, not merely by seeing the DB updated.
