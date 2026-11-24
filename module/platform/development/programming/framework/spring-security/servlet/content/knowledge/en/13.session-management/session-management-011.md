# Permission changes, account locking, and revoking logged-in sessions in Spring Security Servlet

In a Spring Security Servlet application, a user logs in via form login, the system authenticates via `AuthenticationManager`, and then saves a `SecurityContext` containing `Authentication` into `HttpSession`. Later, an administrator may **downgrade roles**, **lock the account**, **disable the user**, **change the password**, or require **logging out of all devices**.

An important security question arises: **if account details in the database change, do previously logged-in sessions automatically pick up the changes and lose access right away?**

**You should not assume yes by default.** The `Authentication` stored in a session typically carries principal/authority information created at login time. Spring Security has no global built-in guarantee that every session on every server is refreshed or revoked merely because a row in the user database changed.

This lesson explains three layers of responsibility that must work together:

1. **Source-of-truth account state:** is the account locked, disabled, deleted, or flagged for password reset, and what are its current roles/permissions?
2. **Stored authentication state:** which `SecurityContext`, principal, and authorities still reside inside each HTTP session?
3. **Revocation and revalidation mechanisms:** how to invalidate old sessions, refresh/recheck permissions before use, and test across distributed systems.

Scope is **Spring Security Servlet / Spring MVC**, typical in Spring Security 6.x with form login and server-side HTTP sessions. Illustrative code uses Java 17+ and Spring Boot 3.x. Versions must be checked against real APIs and support policies; examples do not claim the sample version is the newest.

## 1. SecurityContext in a session is a state snapshot, not a live database query

The basic flow:

```text
POST /login
    |
UsernamePasswordAuthenticationFilter
    |
AuthenticationManager -> AuthenticationProvider
    |
UserDetailsService reads user / roles / status from DB
    |
Verified Authentication
    |
SecurityContextHolder <- SecurityContext(Authentication)
    |
SecurityContextRepository.saveContext(...)
    |
HttpSession holds saved context
    |
GET /account in another request with the same session ID
    |
Repository loads SecurityContext from session
    |
AuthorizationFilter checks Authentication.getAuthorities()
```

After a user logs in successfully, `SecurityContextRepository` can save the context in the session. When subsequent requests use the same session, the framework can restore the old `Authentication` **without calling `UserDetailsService.loadUserByUsername` or password-checking providers again**. This is what creates the gap between **current account state** and **permissions active inside the session**.

Example:

```text
10:00: alice logs in -> Authentication has ROLE_ADMIN -> session S1
10:05: administrator removes ROLE_ADMIN from alice in the database
10:06: alice sends GET /admin with session S1
       without revalidation/revocation, Authentication in S1 may
       still hold ROLE_ADMIN from 10:00.
```

**Do not infer that `authorizeHttpRequests().hasRole("ADMIN")` re-reads the DB on every request.** It normally decides based on authorities already present in the current request's `SecurityContext`. Method security also typically uses the `Authentication` supplied for the invocation, unless the application explicitly revalidates live data.

### How do different changes at the user source affect sessions?

| Change at user source | Behavior on **new** login | Risk for **existing** sessions |
|---|---|---|
| Role/authority change | New login usually receives new permission set | Old session may retain prior authorities |
| `accountNonLocked=false` (lock user) | Corresponding provider usually rejects new login | Old context does not vanish automatically without checks/revocation |
| `enabled=false` or account deleted | New login usually rejected / user not found | Old session may still hold principal without revalidation |
| Password changed or marked compromised | New login must use current credentials | Old session can keep working; changing password is not automatically “logout everywhere” |
| User removed from group/tenant | Re-authentication receives updated permissions | Old request may use stale tenant permissions or cached data |
| MFA reset or account takeover detected | New auth flow may require MFA | Sessions trusted prior to the incident need dedicated revocation policies |

Not every system must invalidate all sessions when **granting higher privileges**; however, avoid retaining inaccurate permissions and avoid silently elevating an older session that has not met higher authentication assurance requirements. For **privilege reduction/account locking** or security incidents, revocation requirements are typically stricter.

## 2. Distinguishing three tasks: blocking new logins, downgrading active permissions, revoking sessions

A system can implement **one** correctly while missing the other two:

- **Blocking future logins:** `DaoAuthenticationProvider` or an appropriate provider checks user status; flags like `UserDetails.isAccountNonLocked()`, `isEnabled()`, and `isAccountNonExpired()` are evaluated in that flow. This **does not automatically signal already authenticated sessions**.
- **Evaluating permissions per request:** authorization uses authorities inside `Authentication` or a policy service fetching live data. Without refreshing context or checking security status, old sessions can keep old permissions.
- **Revoking issued sessions:** invalidating server sessions, marking expired, deleting session entries in the store, incrementing a security version, or forcing re-authentication on the next request. Each approach differs in latency and guarantee scope.

**Changing passwords, changing roles, locking accounts, and logging out may share triggers, but none automatically replaces all the others.**

Distinction:

| Question | Required mechanism |
|---|---|
| Can a locked user start a new login? | Status check in the authentication provider |
| Can an old session of a locked user still call APIs? | Revalidation, revocation, or status checks during authorization |
| Are sessions on another server revoked? | Shared session store/registry or distributed mechanism |
| Is a request that already loaded context before locking halted immediately? | Concurrency control and recheck at sensitive execution points; not just deleting the session |
| What if clients use JWTs instead of server-side sessions? | Appropriate token revocation/short TTL/version/introspection; deleting `HttpSession` does not affect independent JWTs |

## 3. Principles for safely updating permissions and account state

When an administrator modifies permissions or locks an account, an operational workflow should define:

1. **Authenticate and authorize the actor making the change.** Only authorized admins may edit roles, lock users, reset credentials, or revoke sessions. Even admins must be scoped to allowed targets/tenants.
2. **Persist changes to a trusted data source.** Use transactions/optimistic locking/versioning as needed so concurrent edits do not overwrite each other.
3. **Update revocation signals.** Increment user `securityVersion`/`sessionEpoch`, publish post-commit events, delete sessions by principal, or combine approaches.
4. **Enforce policy before the next request.** Old sessions must be rejected or re-authenticated before using revoked permissions. For high security, do not allow nodes to rely on overly stale caches.
5. **Write minimal audit logs.** Who changed what, which account, when, outcome, and correlation ID; never log raw session IDs, passwords, tokens, or reset secrets.
6. **Verify multi-node cluster impact.** Never treat one instance's in-memory session registry as the system-wide session list.

**Update order matters.** Deleting sessions before the role-update transaction commits lets the user log back in with old permissions during the window. For high-risk revocations, define the effective cutover moment, handle rollbacks, and ensure late events cannot restore stale permissions.

### Recommended policies by sensitivity

- **Privilege downgrade or group removal:** invalidate/revalidate affected sessions so old authorities are no longer used. For sensitive financial or administrative actions, recheck live status/permissions at action execution time.
- **Lock/disable account:** block new logins and revoke all known server-side sessions; optionally combine with per-request `isAccountNonLocked`/`isEnabled` checks to cover session-store misses or races.
- **User-initiated password change:** decide whether the current session stays alive and whether other sessions are logged out. After suspected password compromise, broader revocation is usually required.
- **MFA or sensitive privilege change:** review the authentication assurance of old sessions; require step-up authentication rather than merely appending authorities to an old context.
- **User deletion or tenant removal:** ensure context, object-level policies, and data caches all stop granting unauthorized access.

## 4. Approach 1: SessionRegistry and marking sessions expired

Spring Security Servlet provides the `SessionRegistry` interface and in-memory `SessionRegistryImpl` to support concurrent session management and tracking registered sessions.

Key APIs:

- `getAllPrincipals()`: list of principals tracked by the registry.
- `getAllSessions(principal, includeExpiredSessions)`: list of session information entries for that principal.
- `SessionInformation.expireNow()`: marks the session expired **inside the registry**.

**Illustrative Java snippet** inside a service with `SessionRegistry registry` and `String targetUsername`, where the principal is `UserDetails`:

```java
for (Object principal : registry.getAllPrincipals()) {
    if (principal instanceof UserDetails user
            && user.getUsername().equals(targetUsername)) {
        for (SessionInformation info
                : registry.getAllSessions(principal, false)) {
            info.expireNow();
        }
    }
}
```

Requires imports `org.springframework.security.core.userdetails.UserDetails`, `org.springframework.security.core.session.SessionRegistry`, and `SessionInformation`. This snippet is **not a standalone runnable class**, and the principal-matching strategy must match how your application identifies users (usernames can change, tenant IDs can collide, and principals do not always implement `UserDetails`).

### expireNow is not immediate session deletion

**`SessionInformation.expireNow()` only updates session state in the registry.** With concurrent session control properly wired, `ConcurrentSessionFilter` can detect the expired session on **a subsequent request**, invoke the expired-session strategy, and perform logout/invalidation per configuration. It does not remotely signal browsers to kill an already running request instantly.

For this approach to work properly:

- Target sessions must **already be registered in the registry**. An app without session tracking enabled may lack the expected session list.
- Expired-session handling must be wired into the security filter chain.
- Registration cleanup/session lifecycle must work properly (with `SessionRegistryImpl`, `HttpSessionEventPublisher` is usually needed to observe session destruction).
- Multi-instance registry management/synchronization is required when running in a cluster.

**Do not assume merely declaring a `SessionRegistryImpl` bean manages all sessions and checks expiration on every request.** Inspect the actual `SecurityFilterChain`, session management configuration, and integration tests.

### In-memory sessions across multiple nodes

If node A calls `registry.getAllPrincipals()` on an A-local in-memory registry, the list will not contain sessions created by node B. Use shared session infrastructure or proper distributed session tracking; never promise system-wide “logout all devices” when session data lives on only one node.

## 5. Approach 2: Spring Session and deleting sessions by principal

In systems storing HTTP sessions centrally via Spring Session (depending on Redis/JDBC or another repository), you can use principal indexing if supported by the repository.

API-level example using `FindByIndexNameSessionRepository`:

```java
// Illustrative snippet inside a service with a matching Spring Session repository.
FindByIndexNameSessionRepository<? extends Session> repository = sessions;
Map<String, ? extends Session> byUser =
    repository.findByPrincipalName(username);

for (String sessionId : byUser.keySet()) {
    repository.deleteById(sessionId);
}
```

Requires Spring Session imports `FindByIndexNameSessionRepository`, `Session`, and `Map`. Variables `sessions` and `username` must be injected/passed into the service; this is **not a standalone Java file**.

Meaning:

1. Query session IDs by indexed principal.
2. Delete matching sessions in the store, so subsequent accesses no longer find context in those sessions.
3. Force the client to perform a fresh authentication when accessing protected resources.

**Prerequisites:** the session repository supports `findByPrincipalName`; principal indexing is configured/populated properly by Spring Security/Spring Session; and apps/nodes genuinely share the same session store and matching namespace. Without indexing or for sessions created outside the managed mechanism, queries may miss sessions.

### Deleting sessions also has timing boundaries

A request that loaded `Authentication` from the session **before the session was deleted** may still be executing in memory. Deleting the session from the store does not roll back an in-flight transaction or strip context from every active processing thread. For sensitive actions, **revalidate at the execution point** or compare live security version/state before committing business changes.

Additionally, “list then delete” is not inherently atomic against a request creating a new session. If a user is logging in at the exact moment an admin locks the account, the authentication flow must also check current status before issuing a session; under strict policies, security versions or transactional checks prevent sessions from slipping through the gap.

## 6. Approach 3: Request-time revalidation to reject stale context

Another option is maintaining the **source of truth** for account/permission state and **rechecking when requests arrive**. For small apps, you can load fresh `UserDetails` and compare against the context's `Authentication`. At larger scale, a `securityVersion`/`permissionsVersion`/`sessionEpoch` field can be cleaner and leaner.

Idea:

```text
POST /login:
  current user version=12 -> principal/session records version=12

Admin locks user or changes permissions:
  update database, version=13, locked=true

GET /account with session version=12:
  revalidation filter reads current version=13
  -> mismatch / locked
  -> clear current SecurityContext, invalidate session
  -> return 401 / require re-authentication

POST /login again:
  provider reads locked=true -> rejects login
```

**Benefits:** does not depend solely on enumerating session IDs; requests carrying old `Authentication` are rejected when passing through the appropriate checkpoint.

**Trade-offs:** extra database/cache reads, stale data risks, infrastructure errors, consistency issues, and races with in-flight requests. Decide whether to check every sensitive request or only when versions change, how long caches live (TTL), and ensure store errors **fail closed** on high-security endpoints.

Do not compare only `getAuthorities()` in every application: a password change or forced logout may **not alter roles**, so a session-revocation signal such as a security version is needed. Conversely, a privilege upgrade may require stronger authentication; never silently add `ROLE_ADMIN` into an old session just because the DB gained it.

### Why not check the DB only in controllers?

Checking status inside one controller while missing other URLs leaves gaps users can still hit. For application-wide requirements, place checks in a reliable central point such as a filter or `AuthorizationManager`; meanwhile, object-level authorization still belongs near business services/data.

A filter does not automatically protect code invoked outside HTTP Servlets (background jobs, messaging, gRPC). Identify every entry point carrying sensitive privileges.

## 7. Runnable Spring Boot 3.x example: locking/role changes reject old sessions

This example focuses on **verifiable behavior** rather than building a public “admin endpoint” to lock or elevate users. Account state changes are performed **inside JUnit tests** via an in-memory store to demonstrate stale-session bugs and the protection mechanism.

Stack: Java 17+, Spring Boot **3.3.5** (a learning milestone, not claimed to be the latest/supported release), Boot-managed Spring Security 6, Maven, MockMvc. We keep standard form login and HTTP sessions like a typical Servlet application, adding a `OncePerRequestFilter` that reloads user state before the request reaches authorization.

**Transparency limits:** the demo does not implement distribution, transactions, or millions of users. Direct authority comparison suits explaining the mechanism; production should use security versions, a session store/revocation service, caching policies, and load testing.

### 7.1. Directory structure

```text
session-revocation-demo/
├── pom.xml
└── src/
    ├── main/java/example/revocation/
    │   ├── RevocationApplication.java
    │   ├── DemoAccountState.java
    │   ├── AccountRevalidationFilter.java
    │   ├── SecurityConfiguration.java
    │   └── DemoController.java
    └── test/java/example/revocation/
        └── RevocationFlowTest.java
```

### 7.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>session-revocation-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. Entry point

Create `src/main/java/example/revocation/RevocationApplication.java`:

```java
package example.revocation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RevocationApplication {
    public static void main(String[] args) {
        SpringApplication.run(RevocationApplication.class, args);
    }
}
```

### 7.4. Illustrative state store

Create `src/main/java/example/revocation/DemoAccountState.java`:

```java
package example.revocation;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Component;

@Component
public class DemoAccountState {

    private final AtomicBoolean locked = new AtomicBoolean(false);
    private final AtomicReference<String> role =
        new AtomicReference<>("USER");

    public boolean isLocked() {
        return locked.get();
    }

    public String getRole() {
        return role.get();
    }

    public void setLocked(boolean value) {
        locked.set(value);
    }

    public void setRole(String value) {
        if (!value.equals("USER") && !value.equals("ADMIN")) {
            throw new IllegalArgumentException("Unsupported role");
        }
        role.set(value);
    }

    public void reset() {
        locked.set(false);
        role.set("USER");
    }
}
```

This store holds **a single demo user** in memory. It is not a production user repository and has no auditing/transactions/versioning; reading lock and role from two separate atomic values also does not provide a transactionally consistent snapshot. It serves to observe post-login mutations inside MockMvc.

### 7.5. Revalidation filter before authorization

Create `src/main/java/example/revocation/AccountRevalidationFilter.java`:

```java
package example.revocation;

import java.io.IOException;
import java.util.HashSet;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.web.filter.OncePerRequestFilter;

public class AccountRevalidationFilter extends OncePerRequestFilter {

    private final UserDetailsService users;

    public AccountRevalidationFilter(UserDetailsService users) {
        this.users = users;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getServletPath();
        return path.equals("/public")
            || path.equals("/login")
            || path.equals("/logout")
            || path.equals("/error");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (authentication != null
                && authentication.isAuthenticated()
                && authentication.getPrincipal() instanceof UserDetails principal) {

            UserDetails fresh;
            try {
                fresh = users.loadUserByUsername(principal.getUsername());
            } catch (UsernameNotFoundException removedUser) {
                rejectAndInvalidate(request, response);
                return;
            }

            boolean blocked = !fresh.isEnabled()
                || !fresh.isAccountNonLocked()
                || !fresh.isAccountNonExpired()
                || !fresh.isCredentialsNonExpired();

            boolean rolesChanged = !new HashSet<>(fresh.getAuthorities())
                .equals(new HashSet<>(authentication.getAuthorities()));

            if (blocked || rolesChanged) {
                rejectAndInvalidate(request, response);
                return;
            }
        }

        chain.doFilter(request, response);
    }

    private void rejectAndInvalidate(
            HttpServletRequest request,
            HttpServletResponse response) {
        SecurityContextHolder.clearContext();
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
        // The demo intentionally returns 401 for a revoked session.
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
    }
}
```

Key design decisions:

- Place the filter **after `SecurityContextHolderFilter`** so it can read the `Authentication` loaded for the request by the repository, and **before authorization** so fresh state takes effect in time. This suits Security 6 in the example; verify actual filter order in your version when extending.
- When the principal is not `UserDetails`, the filter does not treat it as a logged-in account. `AnonymousAuthenticationToken` is not mistaken for a real account since its principal is typically not `UserDetails`; normal authorization proceeds.
- When the DB shows the account is locked/disabled/expired or roles changed, the filter clears the request context, invalidates the current HTTP session, and returns 401; the request never reaches the controller.
- Returning 401 for **a newly revoked session** is a demo response contract; ordinary anonymous requests can still be redirected to login by the form-login entry point.
- Do not overwrite session authorities with new permissions (especially during **privilege escalation**) because the session may need step-up/MFA policy checks. Forcing re-login is clearer for this exercise.
- The filter does not catch arbitrary `RuntimeException`s and turn them into “account locked”. In production, permission-store failures need explicit fail-closed/availability strategies and metrics rather than masking outages.
- `OncePerRequestFilter` prevents duplicate invocations within a single dispatch; it is not a mechanism to revoke all sessions or block retries across separate HTTP requests.

### 7.6. SecurityFilterChain config and preventing double Filter registration

Create `src/main/java/example/revocation/SecurityConfiguration.java`:

```java
package example.revocation;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.SecurityContextHolderFilter;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(DemoAccountState account, PasswordEncoder encoder) {
        String verifier = encoder.encode("demo-only-password");

        return username -> {
            if (!"alice".equals(username)) {
                throw new org.springframework.security.core.userdetails
                    .UsernameNotFoundException("Unknown user");
            }

            return User.withUsername("alice")
                .password(verifier)
                .accountLocked(account.isLocked())
                .authorities("ROLE_" + account.getRole())
                .build();
        };
    }

    @Bean
    AccountRevalidationFilter revalidationFilter(UserDetailsService users) {
        return new AccountRevalidationFilter(users);
    }

    @Bean
    FilterRegistrationBean<AccountRevalidationFilter> noContainerRegistration(
            AccountRevalidationFilter filter) {
        FilterRegistrationBean<AccountRevalidationFilter> registration =
            new FilterRegistrationBean<>(filter);
        registration.setEnabled(false);
        return registration;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AccountRevalidationFilter revalidation)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/error").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(form -> form
                .defaultSuccessUrl("/account", true)
                .failureUrl("/login?error")
                .permitAll())
            .addFilterAfter(revalidation, SecurityContextHolderFilter.class)
            .build();
    }
}
```

**Note on the class above:** for cleaner Java style, in a real file import `UsernameNotFoundException` and use the short name in the lambda. Using a wrapped fully qualified class name as illustrated must still be valid Java syntax; a complete compilable version can equivalently use the following inside `users(...)`:

```java
// Import at the top of the file:
import org.springframework.security.core.userdetails.UsernameNotFoundException;

// Inside the lambda:
throw new UsernameNotFoundException("Unknown user");
```

The snippet above is a syntax replacement instruction—**do not insert both throw branches simultaneously**. Behavior remains identical when tidied with the import per this note. All remaining components stay unchanged.

**Why is `FilterRegistrationBean.setEnabled(false)` needed?** Because a filter exposed as a `@Bean` is a Servlet `Filter`. Spring Boot can auto-register `Filter` beans with the container outside the Spring Security chain. Meanwhile `addFilterAfter` places it inside `SecurityFilterChain`. Disabling container registration prevents the same filter from running in two pipelines in an unintended order.

**There is no need to save `SecurityContext` manually inside this filter.** Standard login already saved `Authentication` via the appropriate repository; the revalidation filter only inspects the loaded session state and **invalidates** the session when staleness is detected.

In the example, `UserDetailsService` builds `UserDetails` from the live store whenever authentication or revalidation calls it; in production, replace it with a transactional database/service with `permissionsVersion` and proper error handling. Enabling verbose loggers for raw credentials in real environments is risky.

### 7.7. Controller

Create `src/main/java/example/revocation/DemoController.java`:

```java
package example.revocation;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage() {
        return "PUBLIC_OK";
    }

    @GetMapping("/account")
    public String account(Principal principal) {
        return "Hello, " + principal.getName();
    }

    @GetMapping("/admin")
    public String admin(Principal principal) {
        return "ADMIN_OK: " + principal.getName();
    }
}
```

The controller exposes no admin-mutation endpoint to the Internet. In tests, the store is mutated directly on the server side to simulate an authorized, committed administrative action. In real deployments, enforce auditing/authorization/CSRF on APIs modifying roles or locking users.

### 7.8. MockMvc integration tests

Create `src/test/java/example/revocation/RevocationFlowTest.java`:

```java
package example.revocation;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RevocationFlowTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    DemoAccountState account;

    @BeforeEach
    void resetState() {
        account.reset();
    }

    MockHttpSession login() throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-only-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/account"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session).isNotNull();
        return session;
    }

    @Test
    void publicRouteWorksWithoutAuthentication() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC_OK"));
    }

    @Test
    void anonymousRequestRedirectsToLogin() throws Exception {
        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string("Location", containsString("/login")));
    }

    @Test
    void unchangedAccountKeepsItsSession() throws Exception {
        MockHttpSession session = login();

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello, alice"));
    }

    @Test
    void lockingAccountRevokesExistingSessionAndBlocksNewLogin()
            throws Exception {
        MockHttpSession session = login();
        account.setLocked(true);

        mvc.perform(get("/account").session(session))
            .andExpect(status().isUnauthorized());

        assertThat(session.isInvalid()).isTrue();

        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo-only-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void roleDowngradeInvalidatesOldAdminSession() throws Exception {
        account.setRole("ADMIN");
        MockHttpSession oldSession = login();

        mvc.perform(get("/admin").session(oldSession))
            .andExpect(status().isOk())
            .andExpect(content().string("ADMIN_OK: alice"));

        account.setRole("USER");
        mvc.perform(get("/admin").session(oldSession))
            .andExpect(status().isUnauthorized());
        assertThat(oldSession.isInvalid()).isTrue();

        MockHttpSession newSession = login();
        mvc.perform(get("/admin").session(newSession))
            .andExpect(status().isForbidden());
    }

    @Test
    void roleUpgradeRequiresFreshAuthentication() throws Exception {
        MockHttpSession oldSession = login();
        account.setRole("ADMIN");

        mvc.perform(get("/admin").session(oldSession))
            .andExpect(status().isUnauthorized());
        assertThat(oldSession.isInvalid()).isTrue();

        MockHttpSession newSession = login();
        mvc.perform(get("/admin").session(newSession))
            .andExpect(status().isOk())
            .andExpect(content().string("ADMIN_OK: alice"));
    }

    @Test
    void loginPostWithoutCsrfTokenIsDenied() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "demo-only-password"))
            .andExpect(status().isForbidden());
    }
}
```

The tests cover:

- Public endpoint when anonymous.
- Protected endpoint before login.
- Session remains valid when the account is unchanged.
- Account lock rejects the old session on the next request; `DaoAuthenticationProvider` blocks new logins.
- Downgrading `ADMIN` to `USER` invalidates the old session; a new login keeps the user without `ADMIN` rights, returning 403.
- Upgrading privileges also forces re-authentication rather than silently elevating the old session to admin.
- CSRF protection remains active on POST login.

**Expectation:** all seven tests succeed when the project is assembled accurately with compatible Spring Boot 3.3.5 / Java 17. The code has not been built or executed inside this document; the assertions describe the behavior to verify on a real machine. These tests do not cover all edge cases of clustered sessions or races across concurrent HTTP requests.

### 7.9. Trying it out

From the directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

In the running demo server, only the test user `alice / demo-only-password` is configured. No public endpoint mutates lock/role state; state-mutation scenarios execute inside the JUnit tests. With a valid session and unlocked user, `GET /account` produces the exact body:

```text
Hello, alice
```

Never use hardcoded credentials or this in-memory store as a production design. When testing behavior in a browser, use HTTPS and proper cookie policies in a real environment.

## 8. Turning the demo into a production design: securityVersion / sessionEpoch

With many users, roles, and devices, comparing all authorities on every request is expensive and fails to cover events like password resets. A better design uses a **monotonic security version** managed in the trusted data source.

Conceptual schema example:

```text
users:
  id              UUID/long immutable
  account_status  ACTIVE / LOCKED / DISABLED
  security_version  BIGINT incremented on each event requiring revocation
  updated_at       timestamp for auditing, DO NOT replace monotonic version

session authentication:
  immutable user_id
  security_version_at_login
  granted authorities snapshot
  authentication assurance / MFA level (if applicable)
```

When an admin downgrades roles or locks an account, the transaction updates the user/roles and increments `security_version`. On requests carrying a session, a filter or `AuthorizationManager` checks:

```text
if account_status != ACTIVE -> revoke/deny
else if version_at_login != current_security_version -> revoke/reauthenticate
else -> allow proceeding to authorization
```

**No need to hash passwords or call `PasswordEncoder` again on every request.** Simply query user status/version by immutable ID or use a cache with appropriate TTL/invalidation; the version stored in the principal/session must be a trusted value attached after authentication, never accepting a client-declared version.

### Guarantees that must be agreed upon

- **Immediate revocation:** “Immediate” can mean before the next request, before any sensitive action, or halting an already running request. These three levels differ greatly.
- **Cache consistency:** a 60-second cache TTL lets a locked user remain accepted for up to that window before refreshing, unless strong invalidation is used.
- **Fail closed:** if user status cannot be read due to store failure, dangerous endpoints may need to temporarily reject rather than trusting a stale snapshot. Emit distinct error/availability signals rather than disguising every outage as a wrong password.
- **Identity lifecycle:** never reuse username as an immutable key if renames/merges/tenants exist; use stable user IDs and tenant IDs.
- **Concurrent updates:** increment `security_version` atomically alongside revocable changes so newer events do not overwrite stale versions.
- **Cluster propagation:** a session created on node A must be consistently checked/revoked on node B.
- **In-flight requests:** checking version at request start is insufficient if permissions change mid-request during long-running work. For money transfers, privilege grants, or exports, recheck at the transaction point or use strong synchronization.

If policy requires “logout all devices” after password compromise, beyond server-side sessions you must also consider remember-me tokens, refresh tokens, external IdP sessions, device tokens, and other bearer tokens. Deleting `HttpSession` addresses only one credential type.

## 9. SessionRegistry, Spring Session, and revalidation: pick one or combine?

A reliable system can **combine** them to lower latency and widen defense coverage:

| Measure | What it does well | Limitations to know |
|---|---|---|
| `SessionRegistry.expireNow` | Flags tracked sessions as expired | Registry must track sessions and chain must check expired; does not kill in-flight requests |
| Spring Session `deleteById` by principal | Deletes server sessions in a shared store | Needs principal indexing, does not halt requests with loaded context, races against session creation |
| Request-time status/roles/version revalidation | Rejects old sessions before authorization | Adds state-read cost and stale-cache/outage risks |
| Per-action authorization from live data source | Protects sensitive operations mid-execution | Must be designed inside the business layer and transactions |
| Session timeout and normal logout | Bounds lifetime and handles user-initiated logout | Insufficient for emergency revocation |
| Invalidate refresh tokens/remember-me | Stops secondary credentials from re-issuing sessions | Separate mechanism; does not happen automatically just from deleting `HttpSession` |

**Choice:** small apps can start with request-time revalidation plus session invalidation, while multi-node systems should combine a shared session store with a security version. For sensitive operations, always verify authorization at the action itself, not solely right after login.

## 10. Why permission changes can cause subtle bugs

### 10.1. Elevating authorities directly on a stored Authentication

An anti-pattern is updating a user's DB role, then having a custom filter fetch the new role and **swap authorities on the current session** without distinguishing upgrades from downgrades. If a user rises from `ROLE_USER` to `ROLE_ADMIN`, the old session may **not satisfy MFA/step-up requirements** required for the new role. Conversely, if a permission service has a stale cache, that code can reinstate old permissions.

**Choose an explicit policy:** invalidation + re-login/step-up, or a carefully evaluated authority-refresh policy. Never treat rehydrating `Authentication` as a harmless operation.

### 10.2. Locking a user affects only UserDetailsService

Configuring:

```java
User.withUsername(username)
    .password(encoded)
    .accountLocked(true)
    .build();
```

belongs to **the stage of supplying `UserDetails` for authentication**, not a command deleting all old `SecurityContext`s. Existing sessions must be handled by a revocation policy.

### 10.3. One server locks, another server does not know

A local `SessionRegistryImpl`, local user-status cache, or in-memory denylist may protect only one node. When a load balancer routes requests to another instance, stale permissions still work. Use a shared repository/invalidation or check versions from a shared store.

### 10.4. Sessions stay alive after password reset

If password reset lacks a session-revocation policy, sessions issued under the old password can retain access. **Changing a password does not necessarily log out all sessions automatically**. Especially for suspected account compromise, revoke remember-me/refresh tokens as well per product requirements.

### 10.5. Request already running before the lock timestamp

An API request starts with a valid session, and an admin locks the user while the API runs a long operation. Deleting the session does not roll back an already open transaction. For transfers, permission edits, or data exports, recheck account/permissions at commit time or use sufficiently consistent concurrency controls.

## 11. Common errors and diagnostics

| Symptom | What to check | Investigation method |
|---|---|---|
| Locked user still accesses admin pages | Old `SecurityContext` still in session; missing revocation/revalidation | Compare context authorities vs. live source; retry same session after lock |
| New logins blocked yet old session still works | Provider checks lock only at login | Add existing-session revocation or per-request check |
| `expireNow` called yet session is not kicked immediately | Only sets expired flag; filter acts on next request | Check concurrent session filter, registry, expired-session strategy |
| Cannot find session to revoke | Registry did not register session or missing principal index | Check session tracking, principal representation, shared store |
| “Logout all” works only on node A | Local-only registry/session | Check multi-node setup, shared store, event propagation |
| Deleted session yet user immediately has a session again | Remember-me, refresh token, IdP login, or racing login request | Check all credential issuers and status/revocation ordering |
| Role changed yet page still shows old role | Stale authorities/cached authorization or UI cache | Separate backend authorization from UI rendering; invalidate cache |
| Role upgraded yet user sees no new privilege | Session holds old authorities and policy forces re-login | This may be intended behavior of “step-up/re-authenticate” policy |
| User hits sudden 401 after role change | Revalidation detected version/authority mismatch and revoked | Show “Session is no longer valid” and prompt to log in again |
| `@WithMockUser` test passes yet session revocation fails | Mock authentication skips real login/session strategy | Test `POST /login`, retain session, and mutate user source |
| Session invalidated yet JWT API still works | JWT is independent of server sessions | Design separate revocation/expiry for tokens |
| Every request slows down reading user DB | Revalidation runs heavy queries or re-invokes provider | Use small security version/query, consistent cache, and benchmarks |

**Do not measure revocation effectiveness merely by watching the frontend UI change.** Re-call the protected API using the **old** cookie/session and inspect backend status and actual access. The UI might just be caching data or requests might be hitting an unexpected chain.

## 12. Integration-level and operational testing

A meaningful test suite should verify both **new login capability** and **existing sessions**.

Required test cases:

1. User logs in validly; subsequent request with the same session succeeds.
2. User is **locked**; new logins are blocked; old session can no longer execute protected requests.
3. User is **disabled/deleted**; old session is blocked even if password did not change.
4. **Role downgrade** `ADMIN` → `USER`; old session loses admin access; new login has updated role.
5. **Role upgrade** `USER` → `ADMIN`; old session is not silently elevated if policy requires re-authentication.
6. Password change or security version bump; old sessions are revoked per requirements.
7. Two browsers/devices with distinct cookies; “logout all” applies to both.
8. Multi-node: log in on A, change role on B, replay old cookie via C; never rely on fake shared memory.
9. Races: admin locks user concurrently with a sensitive request starting or a new login creating a session.
10. Store error/timeout: sensitive endpoints fail closed safely without leaking details or returning hard-to-diagnose 500s.
11. Logout, session timeout, remember-me, refresh tokens, and SSO interactions behave per policy.
12. CSRF protection is not disabled when adding role-edit/account-lock APIs or writing new filters.

In particular, distinguish **test data fixtures** from real sessions. `@WithMockUser` is helpful for authorization tests but **does not prove** credentials were verified by a provider, `SecurityContext` was saved in an HTTP session, or sessions are revoked properly. For those requirements, test `POST /login` through the filter chain followed by a request carrying the same `MockHttpSession` or real container cookie.

## 13. Design checklist for “lock account and logout all devices”

- [ ] Maintain a consistent account/permission state source; key by immutable user ID and tenant ID.
- [ ] **New login** paths reject locked/disabled/deleted users via the real provider.
- [ ] **Existing session** paths enforce revocation or revalidation rather than trusting authority snapshots forever.
- [ ] Role downgrades and tenant removals take effect before the next request uses revoked permissions.
- [ ] Role upgrades enforce step-up/MFA or require re-login when business rules demand it.
- [ ] Maintain a user→sessions index or session epoch/version for reliable “logout all devices”.
- [ ] If using `SessionRegistry`, configure both session registration and expired-session handling, not just `expireNow`.
- [ ] If using Spring Session, configure a shared repository/index and multi-instance handling.
- [ ] Define maximum acceptable propagation lag between permission changes and revocation enforcement.
- [ ] Have a plan to block sensitive in-flight operations after account locking when required by business policy.
- [ ] Role/lock updates and revocation signals use transactions/outbox or reliable fault-tolerant mechanisms.
- [ ] No independent remember-me/refresh token/JWT lets the client silently re-authenticate against policy.
- [ ] Configure HTTP session cookies/TLS, CSRF, session fixation, and logout properly.
- [ ] Never log raw passwords, cookies, session IDs, access tokens, refresh tokens, or reset secrets.
- [ ] Audits explain who locked the user, when, how many sessions were revoked, and whether any could not be processed.
- [ ] Test against **real old sessions**, not solely database state or UI output.

### Self-check questions

**1.** Spring Security loaded `UserDetails` at 09:00; at 10:00 an admin removes `ROLE_ADMIN` in the DB. Does the logged-in session lose that role immediately?  
**Answer:** Do not assume so. `Authentication` in the session can retain old authorities; a revocation or revalidation mechanism is needed.

**2.** Is setting `accountNonLocked=false` alone enough to log out an online user?  
**Answer:** No. That attribute is checked by providers in the login flow; existing sessions need separate handling.

**3.** Does calling `SessionInformation.expireNow()` immediately delete cookies and kill all running requests?  
**Answer:** No. It marks the registry; matching filters usually handle it on the next request. Cookies and in-flight requests have separate lifecycles.

**4.** If Spring Session calls `deleteById` for every session ID found by principal, are all in-flight requests stopped?  
**Answer:** Not yet. Requests that loaded context prior to deletion may still be executing; policies/checks at critical actions are needed.

**5.** Why should privilege upgrades sometimes also force re-login?  
**Answer:** Because the old session may not meet MFA/step-up requirements or new assurance levels; sensitive permissions should not be granted by silently swapping authorities.

**6.** If an API uses bearer JWTs without `HttpSession`, does deleting `HttpSession` revoke the JWT?  
**Answer:** No. Self-contained tokens have their own expiration/revocation mechanisms.

**7.** Which test proves old sessions are properly protected?  
**Answer:** Log in to create a real session, mutate role/lock in the trusted source, then send a **protected request with that exact old session** and verify 401/403 or the designed rejection behavior, while also testing a fresh login.

**Conclusion:** In Spring Security Servlet, **current account state, `Authentication` saved in `HttpSession`, and revocation policy** are three separate parts. Changing permissions or locking an account does not automatically guarantee active sessions become invalid. A sound design **blocks new logins, revokes or revalidates old sessions, handles clusters and in-flight requests, protects credentials outside `HttpSession`**, and tests after permission changes—not only before login.