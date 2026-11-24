# Revoking Sessions After Account Lock, Password Change, or Security Incidents

## 1. Why Might Locking an Account or Changing a Password Not Log Out Old Devices?

An application using **Spring Security + HTTP sessions** usually authenticates username/password **once at login**. Afterward, every request carries a session cookie; Spring Security restores `Authentication` from the stored `SecurityContext`. Therefore, updating a user record in the database **does not automatically delete** sessions that have already been created.

For example:

1. Alice logs in on her laptop and phone; the server stores two authenticated sessions.
2. An administrator locks Alice's account, or Alice changes her password.
3. The system writes `locked=true` or the new password hash.
4. The laptop keeps sending the old session's cookie. If the context still exists and the application lacks a mechanism to re-check account state, requests **may continue to be accepted**.

The core point: `UserDetailsService.loadUserByUsername(...)` and `PasswordEncoder.matches(...)` typically run during **initial authentication**. An already logged-in session may carry a principal/authorities saved from earlier. Changing a password or locking an account affects **new authentications**, yet **does not automatically revoke** all previously issued authentication results.

This lesson addresses three exact requirements:

- **Account lock:** block new logins and invalidate existing sessions.
- **Password change/reset:** require users to re-authenticate per policy; if password compromise is suspected, revoke old sessions and related long-lived credentials.
- **Security incident:** revoke at the right scope (one session, all sessions of a user, a group of users, or system-wide) and ensure results hold across multiple instances.

**Technical scope:** Spring Boot 3.x, Spring Security 6.x, Spring Session 3.x, Servlet/Spring MVC, and Java 17+. The focus is **session-based authentication**. The end of the lesson distinguishes JWTs, refresh tokens, remember-me, OAuth2, and WebSockets, because those mechanisms are not automatically invalidated merely by deleting an HTTP session.

## 2. Distinguishing Four Actions Often Lumped Together as "Logout"

| Action | What Does It Do? | What Does It Not Guarantee? |
|---|---|---|
| `SecurityContextHolder.clearContext()` | Clears identity from the current execution/request scope | Does not delete all of the user's sessions on other devices |
| `request.getSession(false).invalidate()` | Invalidates the **current session** used by this request | Does not know about all other sessions of the same user |
| `SessionInformation.expireNow()` (Spring Security `SessionRegistry`) | Marks one session as expired in the registry; a matching filter can block its next request | Does not necessarily delete the session immediately from a central store or stop an in-flight request |
| `SessionRepository.deleteById(sessionId)` (Spring Session) | Deletes a specific session from the store managed by `SessionRepository` | Does not automatically revoke JWTs/access tokens/refresh tokens or abort an in-progress request |

A "log out all devices" requirement must know **all sessions to revoke** and be able to delete/invalidate them in a session store shared across all instances.

Do not use `SecurityContextHolder.clearContext()` as the sole solution to an account-lock event: that method affects only the context bound to the current thread/request. If an admin action is running inside an admin's session, it could even accidentally wipe the admin's own context for that request without touching the locked user's sessions.

### When Does a Session Actually Become Invalid in Practice?

There are at least three points in time:

- **T0 — account state changes:** the database records locked or a new password revision.
- **T1 — session records are revoked:** relevant session IDs are deleted or marked expired in the session store.
- **T2 — subsequent requests are checked:** the next request carrying an old session cookie can no longer load a valid context and is prompted to re-authenticate.

A request that already loaded its context **before T0/T1** may still be executing. Deleting a session does not "rewind time" or automatically abort a running HTTP request. Therefore, for sensitive actions such as money transfers or data deletion, re-verify account status or an **authentication version/security stamp** at the meaningful point, rather than relying solely on session deletion.

## 3. Spring Security's Default Mechanisms Do Not Replace Remote Revocation

With standard form login, `UsernamePasswordAuthenticationFilter` usually authenticates via `AuthenticationManager`, saves the result to `SecurityContextRepository`, and uses a session cookie to identify subsequent requests. `UserDetailsService` can load the password hash, `accountNonLocked` flag, and authorities at login. Changing only `UserDetailsService`/DB records without changing the session store still leaves already logged-in browsers able to load old contexts.

Spring Security provides `SessionRegistry` to track sessions and support concurrent session control, for example:

```java
List<SessionInformation> active =
    sessionRegistry.getAllSessions(principal, false);

for (SessionInformation info : active) {
    info.expireNow();
}
```

This is an **illustrative snippet inside a service holding `sessionRegistry` and `principal`**, not a standalone Java program. `expireNow()` marks sessions expired; if `ConcurrentSessionFilter` is properly configured, subsequent requests with that session are treated as expired. It is not equivalent to calling `HttpSession.invalidate()` immediately across all devices.

**Boundaries to keep in mind:**

- `SessionRegistryImpl` stores data in a single JVM's memory by default. With multiple instances, a local registry cannot see another node's sessions.
- When using `SessionRegistryImpl` with a custom principal, `equals/hashCode` must be stable to look up the right user; session destroy events and tracking must also be configured properly.
- Configuring `maximumSessions(1)` is only a concurrent-session count policy; it **does not automatically revoke all sessions after password change or account lock**.
- To delete server-side sessions immediately in a shared store, Spring Session provides `SessionRepository` and lookup by principal.

### Using Spring Session to Find a User's Sessions

`FindByIndexNameSessionRepository<S extends Session>` extends `SessionRepository`:

```java
Map<String, ? extends Session> sessions =
    repository.findByPrincipalName("alice");

for (String sessionId : sessions.keySet()) {
    repository.deleteById(sessionId);
}
```

This illustrative snippet assumes `repository` has a type compatible with `FindByIndexNameSessionRepository`. Key APIs:

- `findByPrincipalName(username)` returns a map `sessionId → Session` matching the indexed principal name.
- `deleteById(id)` deletes the session by ID from the repository. Subsequent requests carrying the old cookie can no longer restore that session.
- When Spring Session integrates with Spring Security in the standard flow, the principal name is typically indexed from `SPRING_SECURITY_CONTEXT`.
- With custom authentication that does not save the standard context, verify that the **principal index is actually populated**; otherwise `findByPrincipalName(...)` can return an empty map even when sessions exist.

Index-capable implementations include `JdbcIndexedSessionRepository` and `RedisIndexedSessionRepository`. Not every `SessionRepository` supports lookup by principal. In a cluster, you need a shared session store and consistent behavior across nodes.

**Choose a stable identifier:** if email/username can change, relying solely on the username string in old sessions can miss sessions. Production should use an immutable account ID in the principal/index or consistent mapping on account rename; verify the actual mapping rather than trusting field names alone.

## 4. Revocation Policy by Event Type

| Event | Account Data Update | Session Handling | Other Credentials to Review |
|---|---|---|---|
| Admin locks account | Persist locked/disabled state | Revoke **all** sessions of the account; block new logins | API keys, refresh tokens, remember-me, service credentials |
| User changes own password | New password hash, increment security revision | Usually revoke other sessions, or all per policy and risk level | Refresh tokens/remember-me, devices with saved credentials |
| Password reset due to suspected leak | New password hash, increment revision; verify user | **Revoke all** sessions, require re-login | Revoke refresh tokens, rotate API keys if in the same incident |
| Stolen session cookie detected | Flag incident, lock account depending on severity | Revoke suspected session or all user sessions | Inspect IP/device, tokens, and anomalous activity |
| Credential store/issuer compromised | Rotate keys/configs, assess blast radius | Revoke sessions across affected scope | JWT signing keys, introspection, refresh-token families |
| Normal logout | Does not necessarily change password/account status | Invalidate **current** session | If the user wants "logout all," a broader revocation command is needed |

**Do not use a single "logout all" button to claim every token type was handled.** HTTP sessions, refresh tokens, bearer JWTs, OAuth2 access tokens, and WebSocket connections have different lifecycles. Identify what the system actually issued to clients.

### Why Must State Be Updated Before Deleting Sessions?

When locking an account, **persist the locked state first**, then request session revocation. New logins are rejected immediately even if finding/deleting sessions takes extra time. For password changes, write the new hash and increment the security revision first, then revoke old sessions.

However, this is not a single atomic transaction spanning the account DB and session store. If the account write succeeds while the session store fails, old sessions remain. You need failure handling: bounded retries, auditing, post-commit events/outbox, alerts, and **request-level revision/status checks** to narrow the risk window.

## 5. Practical Example: Revoking All Sessions with Spring Session JDBC

We will build a demo application with two accounts:

- `alice / alice-secret`: regular user, role `ROLE_USER`, able to log in from multiple browsers.
- `admin / admin-secret`: role `ROLE_ADMIN`, allowed to call two admin endpoints simulating lock or password reset events.

These are **local sample accounts**; never use these passwords outside a learning machine. Standard form login creates sessions, and Spring Session JDBC stores sessions in H2 and indexes principals. An admin service uses `FindByIndexNameSessionRepository` to find and delete Alice's sessions.

To demonstrate blocking requests using stale contexts, the principal carries `credentialRevision`. Every lock/reset increments the revision; a filter running after session restoration checks the principal's revision against current account state and rejects mismatches. **The demo uses an in-memory account store**, suitable only for **a single process**; in production, the revision must come from a shared database/cache with a proper synchronization strategy.

### 5.1. Project Structure

```text
src/
  main/
    java/com/example/revoke/
      RevokeApplication.java
      AccountDirectory.java
      SessionRevoker.java
      AccountEvents.java
      AccountRevisionFilter.java
      SecurityConfig.java
      ApiController.java
      AdminController.java
    resources/application.properties
  test/
    java/com/example/revoke/SessionRevocationHttpTest.java
```

Uses Java 17, Spring Boot **3.5.x**, and Spring Security/Spring Session versions managed by Spring Boot. In a Gradle project with the Boot plugin and wrapper, dependencies are:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.session:spring-session-jdbc'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The Spring Boot plugin/BOM must be configured in the existing build to resolve versions. Do not mix Spring Boot 4.x/Spring Security 7.x into a 3.x project when using this example verbatim; APIs change across versions.

File `src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:sessiondemo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.session.jdbc.initialize-schema=always
server.servlet.session.timeout=30m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

`spring.session.jdbc.initialize-schema=always` creates Spring Session tables for the H2 demo. **Do not blindly enable `always` or use in-memory H2 like this in production**: use a durable DB, schema/migration management, proper timeouts/TTLs, connection pools, and backup policies. Spring Session typically uses a cookie named `SESSION` instead of the servlet container's default `JSESSIONID`.

### 5.2. Spring Boot Entrypoint

File `src/main/java/com/example/revoke/RevokeApplication.java`:

```java
package com.example.revoke;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RevokeApplication {
    public static void main(String[] args) {
        SpringApplication.run(RevokeApplication.class, args);
    }
}
```

### 5.3. Accounts and Credential Revision

File `src/main/java/com/example/revoke/AccountDirectory.java`:

```java
package com.example.revoke;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

@Component
public class AccountDirectory implements UserDetailsService {

    private record Account(
        String passwordHash,
        String role,
        boolean locked,
        long revision
    ) {}

    // Demo only: account state is not persistent and is not shared across nodes.
    private final Map<String, Account> accounts =
        new ConcurrentHashMap<>();
    private final PasswordEncoder encoder;

    public AccountDirectory(PasswordEncoder encoder) {
        this.encoder = encoder;
        accounts.put("alice", new Account(
            encoder.encode("alice-secret"), "USER", false, 1L));
        accounts.put("admin", new Account(
            encoder.encode("admin-secret"), "ADMIN", false, 1L));
    }

    public static final class VersionedUser extends User {
        private static final long serialVersionUID = 1L;
        private final long revision;

        VersionedUser(String username, Account account) {
            super(
                username,
                account.passwordHash(),
                true,  // enabled
                true,  // accountNonExpired
                true,  // credentialsNonExpired
                !account.locked(),
                AuthorityUtils.createAuthorityList("ROLE_" + account.role())
            );
            this.revision = account.revision();
        }

        public long revision() {
            return revision;
        }
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        Account data = accounts.get(username);
        if (data == null) {
            throw new UsernameNotFoundException("Unknown account");
        }
        return new VersionedUser(username, data);
    }

    public boolean isCurrent(VersionedUser principal) {
        Account current = accounts.get(principal.getUsername());
        return current != null
            && !current.locked()
            && current.revision() == principal.revision();
    }

    public void lock(String username) {
        accounts.compute(username, (name, current) -> {
            if (current == null) {
                throw new IllegalArgumentException("Unknown account");
            }
            return new Account(
                current.passwordHash(), current.role(), true,
                current.revision() + 1);
        });
    }

    public void resetPassword(String username, String rawPassword) {
        if (rawPassword == null || rawPassword.length() < 12) {
            throw new IllegalArgumentException(
                "A demo password needs at least 12 characters");
        }
        String newHash = encoder.encode(rawPassword);
        accounts.compute(username, (name, current) -> {
            if (current == null) {
                throw new IllegalArgumentException("Unknown account");
            }
            return new Account(
                newHash, current.role(), current.locked(),
                current.revision() + 1);
        });
    }
}
```

Why is the revision valuable?

- `DaoAuthenticationProvider` loads `VersionedUser` at login; it verifies the hash, checks account status, and returns an authentication with a trusted principal.
- `VersionedUser.revision()` is the version number at **login time**.
- Upon lock or password reset, the new state increments the revision. An old authentication no longer matches the new state.
- The filter below compares revisions on each request. Even if session deletion lags or a registry/index has not synchronized yet, the stale context can be rejected.

**Never use the password hash as a security stamp** and never put passwords or secrets into cookies/responses. The demo uses a simple `long revision` for clarity; production should use an immutable account ID and a revision stored durably in the DB, with proper indexing/cache invalidation.

### 5.4. Finding and Deleting Principal Sessions

File `src/main/java/com/example/revoke/SessionRevoker.java`:

```java
package com.example.revoke;

import java.util.List;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.stereotype.Service;

@Service
public class SessionRevoker {

    private final FindByIndexNameSessionRepository<? extends Session> sessions;

    public SessionRevoker(
            FindByIndexNameSessionRepository<? extends Session> sessions) {
        this.sessions = sessions;
    }

    public int revokeAll(String principalName) {
        // Copy IDs before modifying the repository; do not iterate directly over a changing map.
        List<String> ids = List.copyOf(
            sessions.findByPrincipalName(principalName).keySet()
        );

        for (String id : ids) {
            sessions.deleteById(id);
        }

        // Number of records selected for deletion; not a guarantee
        // that every in-flight request has stopped.
        return ids.size();
    }
}
```

In a Boot 3.5.x + `spring-session-jdbc` setup, `JdbcIndexedSessionRepository` implements `FindByIndexNameSessionRepository`. Once Spring Security saves `SecurityContext` into the HTTP session, Spring Session can index the principal name. `findByPrincipalName("alice")` should return sessions bound to Alice, and `deleteById(...)` removes those records from the JDBC store.

Do not store session IDs in a homemade static `Map<username, sessionId>`: that fails with multiple devices, concurrent logins, restarts, and multiple application instances. Use an indexed repository or a consistently managed session inventory model.

One limitation to acknowledge: sessions created by other authentication mechanisms **without a principal index** will not be found. Revocation must be paired with tests confirming the index captures all expected sessions, rather than trusting the API name alone.

### 5.5. Combining Account Changes and Revocation

File `src/main/java/com/example/revoke/AccountEvents.java`:

```java
package com.example.revoke;

import org.springframework.stereotype.Service;

@Service
public class AccountEvents {

    private final AccountDirectory accounts;
    private final SessionRevoker sessions;

    public AccountEvents(AccountDirectory accounts, SessionRevoker sessions) {
        this.accounts = accounts;
        this.sessions = sessions;
    }

    public int lockAndRevoke(String username) {
        // Block new logins and make the revision in old sessions stale.
        accounts.lock(username);
        return sessions.revokeAll(username);
    }

    public int resetPasswordAndRevoke(
            String username, String newPassword) {
        accounts.resetPassword(username, newPassword);
        return sessions.revokeAll(username);
    }
}
```

This is security-event orchestration, not an automatic callback from `PasswordEncoder`. Real applications must invoke this logic from authorized workflows (account lock, password change, reset, incident response) with actor authentication/authorization, auditing, retries when the session store fails, and race handling against new logins.

**About ordering:** update state/revision first, delete sessions second. In the example, if JDBC deletion fails, the revision guard still rejects stale contexts **on subsequent requests** within the same JVM. In production, store revisions in a shared store, read/sync consistently across all nodes, and never ignore revocation failures.

### 5.6. Blocking Stale Principals on Every Request

File `src/main/java/com/example/revoke/AccountRevisionFilter.java`:

```java
package com.example.revoke;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class AccountRevisionFilter extends OncePerRequestFilter {

    private final AccountDirectory accounts;

    public AccountRevisionFilter(AccountDirectory accounts) {
        this.accounts = accounts;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (authentication != null && authentication.isAuthenticated()
                && authentication.getPrincipal()
                    instanceof AccountDirectory.VersionedUser user
                && !accounts.isCurrent(user)) {

            SecurityContextHolder.clearContext();

            HttpSession session = request.getSession(false);
            if (session != null) {
                session.invalidate();
            }

            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        chain.doFilter(request, response);
    }
}
```

This filter is placed **before `AuthorizationFilter`** in the configuration below. By that point Spring Security has had a chance to load `SecurityContext` from the session, so the filter can verify the principal's revision before deciding whether to enter protected endpoints.

It is not a token-revocation filter for every principal type: the example only inspects `AccountDirectory.VersionedUser` from the demo form login. If another filter creates a different principal type, define an explicit policy and verify there is no bypass. Ensure sensitive flows use a trusted revision source.

For particularly critical actions, **do not rely solely on a once-at-request-start filter**: a long-running operation could pass the filter right before the account gets locked. Business services should re-verify account status/revision immediately before committing high-risk actions or use appropriate transactional/authorization checks.

### 5.7. Configuring SecurityFilterChain and Spring Security Form Login

File `src/main/java/com/example/revoke/SecurityConfig.java`:

```java
package com.example.revoke;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    AuthenticationManager authenticationManager(
            AccountDirectory accounts, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(accounts);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager manager,
            AccountDirectory accounts) throws Exception {

        http
            .authenticationManager(manager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/csrf", "/login", "/error").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/admin/accounts/**")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .exceptionHandling(errors -> errors
                .defaultAuthenticationEntryPointFor(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED),
                    new AntPathRequestMatcher("/api/**")
                )
            )
            // CSRF remains enabled by default for form login and admin POST.
            .addFilterBefore(
                new AccountRevisionFilter(accounts),
                AuthorizationFilter.class
            );

        return http.build();
    }
}
```

- Standard `formLogin` handles authentication, executing session strategies, and saving `SecurityContext`. There is no need to write custom JSON login or call `saveContext` manually here.
- `IF_REQUIRED` allows saving logins to sessions; do **not** use `STATELESS` for this demo.
- Admin endpoints require `ROLE_ADMIN`; user Alice cannot call admin HTTP POSTs herself.
- CSRF stays enabled by default. Even though admin logged in via cookie, lock/reset POSTs still require a valid CSRF token.
- For `/api/**`, unauthenticated clients receive `401` for easy testing; the `/login` form UI still serves interactive logins.
- `AccountRevisionFilter` is instantiated with `new` inside the security chain, **not** annotated with `@Component` on the filter itself, to avoid the Servlet container registering it a second time outside the security chain.
- In an application with multiple `SecurityFilterChain` beans, verify that this filter and policy exist on **every chain capable of restoring related sessions**, not just one URL group.

### 5.8. Test Endpoint and Admin Event Endpoint

File `src/main/java/com/example/revoke/ApiController.java`:

```java
package com.example.revoke;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/csrf")
    public CsrfToken csrf(CsrfToken token) {
        return token;
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }
}
```

File `src/main/java/com/example/revoke/AdminController.java`:

```java
package com.example.revoke;

import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AdminController {

    private final AccountEvents events;

    public AdminController(AccountEvents events) {
        this.events = events;
    }

    public record ResetRequest(String newPassword) {}

    @PostMapping("/admin/accounts/{username}/lock")
    public Map<String, Object> lock(@PathVariable String username) {
        int targeted = events.lockAndRevoke(username);
        return Map.of(
            "event", "account_locked",
            "sessionsTargeted", targeted
        );
    }

    @PostMapping(
        path = "/admin/accounts/{username}/reset-password",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Map<String, Object> resetPassword(
            @PathVariable String username,
            @RequestBody ResetRequest body) {

        int targeted =
            events.resetPasswordAndRevoke(username, body.newPassword());

        return Map.of(
            "event", "password_reset",
            "sessionsTargeted", targeted
        );
    }
}
```

The admin endpoints are solely for **controlled local testing**. In production, user password changes require re-authenticating the actor, MFA/rate-limiting policies, password strength checks, one-time-token reset flows, and event logging. Admins should not have arbitrary password-reset endpoints without appropriate policy/approval controls.

To avoid returning sensitive session ID lists, the demo endpoint returns only `sessionsTargeted`; this count is the number of IDs selected for deletion and **does not** prove every in-flight request stopped. For non-existent usernames, the demo throws `IllegalArgumentException`; production apps need controlled error mapping so raw errors do not leak internals.

## 6. Verifying Across Two Browsers and a Security Event

### 6.1. Before Locking: Two Sessions Remain Valid

Run the application (in a project with the Boot Gradle wrapper):

```bash
./gradlew bootRun
```

Windows PowerShell: `.\gradlew.bat bootRun`.

Open two browser windows **with independent cookie stores** (e.g., regular browser and private window). In each window:

1. Visit `http://localhost:8080/login`.
2. Log in with `alice` / `alice-secret`.
3. Call `http://localhost:8080/api/me` and confirm HTTP `200` with JSON containing `"user":"alice"`.

Each browser has its own session cookie. With Spring Session JDBC, the cookie is typically named `SESSION`; session data lives in H2's `SPRING_SESSION` and `SPRING_SESSION_ATTRIBUTES` tables. The cookie contains the session ID, not the password or the entire SecurityContext.

### 6.2. Performing Lock as Admin

Use a third browser logged in as `admin` / `admin-secret`. Because CSRF is enabled, you must send a valid token when calling admin POSTs. To test with Bash curl and a separate cookie jar:

```bash
# Fetch CSRF token + session cookie for the admin client.
curl -sS -c admin-cookies.txt -b admin-cookies.txt \
  http://localhost:8080/csrf > admin-csrf.json

TOKEN=$(jq -r '.token' admin-csrf.json)

# Standard form login, do not send JSON to /login.
curl -i -c admin-cookies.txt -b admin-cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  --data-urlencode 'username=admin' \
  --data-urlencode 'password=admin-secret' \
  http://localhost:8080/login

# After login, fetch a new CSRF token because the old token may be cleared.
TOKEN=$(curl -sS -c admin-cookies.txt -b admin-cookies.txt \
  http://localhost:8080/csrf | jq -r '.token')

curl -i -c admin-cookies.txt -b admin-cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -X POST http://localhost:8080/admin/accounts/alice/lock
```

**Expected outcome:** the admin POST returns `200`, with a body containing `"event":"account_locked"` and the targeted session count. Alice's two browsers calling `/api/me` again will no longer be recognized by their old sessions (expected `401` per the API config). Alice trying a fresh login with her previous password also fails because the account is `locked`.

With the in-memory H2 demo, all sessions disappear when the process stops; this is **not** a production session revocation method. Closing the browser or clearing cookies on the admin's device also does not revoke cookies on Alice's two devices. Only the centralized session store can delete sessions remotely.

### 6.3. Resetting Password Instead of Locking

On a fresh run of the application (to reset demo state), Alice can log in on two devices. Admin calls:

```bash
# Already logged in with admin-cookies.txt from the previous step.
TOKEN=$(curl -sS -c admin-cookies.txt -b admin-cookies.txt \
  http://localhost:8080/csrf | jq -r '.token')

curl -i -c admin-cookies.txt -b admin-cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"newPassword":"a-new-secret-password"}' \
  http://localhost:8080/admin/accounts/alice/reset-password
```

Result: hash/password revision changes, and all discovered Alice sessions are deleted. Alice's browsers using old cookies get `401` for `/api/me`; logging in again with the old password fails, while logging in with the new password succeeds (if the account is not locked). If lock was called beforehand, the account stays locked; password reset in the demo **does not auto-unlock**. This is a safe policy: password reset and unlock are two separate events.

**Why not "log out user" by deleting cookies on the admin client?** Because the server cannot use a response sent to the admin's browser to delete cookies living in Alice's browsers. What must be deleted are the **server-side sessions**, by the IDs bound to Alice.

## 7. Automated Testing Over Real HTTP: Two Clients, One Session Store

Instead of only unit-testing that `revokeAll` returns an ID count, the test below runs Spring Boot on a random port. Each `HttpClient` has its own `CookieManager`, representing a browser. Because it uses real HTTP, we can verify cookies, standard login, JDBC sessions, and post-revocation requests.

File `src/test/java/com/example/revoke/SessionRevocationHttpTest.java`:

```java
package com.example.revoke;

import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SessionRevocationHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    @Autowired
    AccountEvents events;

    private HttpClient client() {
        return HttpClient.newBuilder()
            .cookieHandler(new CookieManager(
                null, CookiePolicy.ACCEPT_ALL))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();
    }

    private URI uri(String path) {
        return URI.create("http://localhost:" + port + path);
    }

    private HttpResponse<String> get(HttpClient client, String path)
            throws Exception {
        return client.send(
            HttpRequest.newBuilder(uri(path)).GET().build(),
            HttpResponse.BodyHandlers.ofString());
    }

    private String csrf(HttpClient client) throws Exception {
        HttpResponse<String> response = get(client, "/csrf");
        assertEquals(200, response.statusCode());
        return mapper.readTree(response.body())
            .get("token").asText();
    }

    private HttpResponse<String> login(HttpClient client, String password)
            throws Exception {
        String form = "username=alice&password=" +
            URLEncoder.encode(password, StandardCharsets.UTF_8);

        return client.send(
            HttpRequest.newBuilder(uri("/login"))
                .header("Content-Type",
                    "application/x-www-form-urlencoded")
                .header("X-CSRF-TOKEN", csrf(client))
                .POST(HttpRequest.BodyPublishers.ofString(form))
                .build(),
            HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void passwordResetAndLockRevokeExistingSessions() throws Exception {
        HttpClient laptop = client();
        HttpClient phone = client();

        // Two browsers have independent session cookies.
        assertEquals(302, login(laptop, "alice-secret").statusCode());
        assertEquals(302, login(phone, "alice-secret").statusCode());
        assertEquals(200, get(laptop, "/api/me").statusCode());
        assertEquals(200, get(phone, "/api/me").statusCode());

        // Changing the password makes old sessions no longer accepted.
        int targeted = events.resetPasswordAndRevoke(
            "alice", "a-new-secret-password");
        assertTrue(targeted >= 2);

        assertEquals(401, get(laptop, "/api/me").statusCode());
        assertEquals(401, get(phone, "/api/me").statusCode());

        // New password allows creating a new session.
        HttpClient freshBrowser = client();
        assertEquals(302,
            login(freshBrowser, "a-new-secret-password").statusCode());
        assertEquals(200, get(freshBrowser, "/api/me").statusCode());

        // Locking the account also revokes the new session.
        int afterLock = events.lockAndRevoke("alice");
        assertTrue(afterLock >= 1);
        assertEquals(401, get(freshBrowser, "/api/me").statusCode());

        // When locked, new logins are rejected per form-login failure.
        HttpClient newBrowser = client();
        HttpResponse<String> failure =
            login(newBrowser, "a-new-secret-password");
        assertEquals(302, failure.statusCode());
        assertTrue(failure.headers()
            .firstValue("Location").orElse("")
            .contains("/login?error"));
        assertEquals(401, get(newBrowser, "/api/me").statusCode());
    }
}
```

Run:

```bash
./gradlew test
```

Windows: `.\gradlew.bat test`.

This test checks crucial behaviors:

- Two independent HTTP clients both obtain authenticated sessions.
- A password-reset event prevents **both clients** from using their old sessions.
- The new password can log in again while the account is not locked.
- Locking the account destroys active sessions and blocks new logins.
- The JDBC session index actually finds at least two sessions; if `findByPrincipalName` failed to index, the test catches it via `targeted`.

This is an integration test example for a Boot 3.x project with a matching build; `AccountDirectory`'s in-memory state could affect other tests if added to the same shared application context. When expanding the test suite, reset fixtures or use isolated contexts for account-mutating cases. This test has only **one** test case that mutates state in a clear sequence.

## 8. Why Deleting Sessions Alone Does Not Guarantee Every Action Stops Immediately

Suppose request A retrieved `SecurityContext` and passed `AuthorizationFilter` at 10:00:00. Then an admin locks the account at 10:00:01. A is running a service that takes 15 seconds and commits data at 10:00:15.

Calling `deleteById(sessionId)` at 10:00:01 prevents **subsequent requests** from loading the session, yet does not automatically stop A which has already started. A filter checking revision at the start of a request also cannot stop A if the revision changed **after the filter already ran**.

When strong enforcement is needed for sensitive transactions, the system must define control checkpoints:

- Re-check account status/security revision when executing business commands and right before committing high-risk operations.
- Perform consistent queries/update locks inside transactions or optimistic locking per your data model.
- During major incidents, enable transaction blocking / risk holds in the backend system rather than relying solely on the HTTP auth layer.
- Ensure revocation events fire **after** the account-state transaction commits; use retries/outbox and alerts when session deletion fails.
- In a cluster, the version guard needs **shared** data with bounded cache staleness. If caches stay stale for long, checking revisions will not provide the expected "near-instant revocation."

**Realistic guarantees to state explicitly:** "new requests are rejected once sessions are deleted or the new revision is observed" is a testable guarantee. "Every already-started request aborts instantaneously" is not a default effect of Spring Session.

## 9. Revocation When an Application Has Multiple Instances

### With In-Memory HttpSession in the Servlet Container

If each node keeps local sessions, a 3-node application may not know about sessions on other nodes. In-memory `SessionRegistryImpl` also does not share its registry globally. Deleting a session on node A does not guarantee deleting sessions belonging to node B.

### With Spring Session JDBC or Redis

Spring Session replaces `HttpSession` with a repository backed by an external datastore. When all nodes share the same repository/schema/namespace, deleting a session on node A prevents subsequent requests on node B from loading the deleted session.

Verify:

- Same datastore and namespace; not accidentally split by deployment config.
- Principal index captures all sessions and uses an immutable identifier.
- Consistent session data, serialization, and expiration/cleanup.
- How many backends issue credentials other than sessions (API gateways, auth proxies, token services).
- With Redis/eventual processing, understand index/event latency and retry mechanisms; do not assume every backend offers identical strong consistency.
- Have proper telemetry confirming sessions found, sessions deleted, store errors, and subsequent blocked requests **without** logging raw session IDs.

For domains demanding very fast revocation, **incrementing a credential revision in the shared account store** and checking it on critical requests is a valuable extra layer, since it does not depend solely on enumerating sessions once.

## 10. Differences Between SessionRegistry.expireNow and SessionRepository.deleteById

| Criterion | `SessionRegistry.expireNow` | Spring Session `deleteById` |
|---|---|---|
| Session ID source | `SessionRegistry.getAllSessions(principal, ...)` | `FindByIndexNameSessionRepository.findByPrincipalName(...)` |
| Effect | Marks expired in the registry | Deletes the session record from the repository store |
| When old requests are rejected | When a supporting filter handles the expired session on its next request | When a subsequent request fails to load the deleted session |
| Built-in cluster-wide tracking? | Default `SessionRegistryImpl` does not | Yes, if nodes share the store/index properly |
| Required accompanying config | Session tracking, event listener, `ConcurrentSessionFilter` for expire flow | Spring Session repository/filter, principal index, shared store |
| Revokes JWT/refresh tokens? | No | No |
| Aborts already-running requests? | No | No |

If you already use concurrent sessions with `maximumSessions(...)`, follow the `SessionRegistry` mechanism of your actual configuration. If the goal is remote session revocation, an index-capable Spring Session store allows direct deletion. Both approaches are not mutually exclusive, yet you should not maintain two "sources of truth for sessions" without synchronization rules.

## 11. Tokens, Remember-Me, and WebSockets Are Not Automatically Invalidated by Deleting Sessions

### HTTP Basic

The client may resend `Authorization: Basic base64(username:password)` on the next request. After a password change, the old password is rejected **if** the authentication data source was actually updated. However, if the account still holds a valid password elsewhere, Basic still logs back in. Deleting sessions does not replace updating the credential source.

### JWT Access Tokens

A validly signed, unexpired JWT with matching issuer/audience can continue to be accepted by a stateless resource server even after HTTP sessions are deleted. Immediate revocation requires an appropriate design: short-lived access tokens with revision/user-status checks, token-ID denylists, stateful token introspection, or scoped signing-key rotation. Each carries performance/latency/memory trade-offs.

**Do not assume changing a password automatically expires all old JWTs.**

### Refresh Tokens and OAuth2/OIDC

Refresh tokens are normally managed by an Authorization Server or dedicated token store. You must revoke refresh-token families/sessions on the authorization server upon events; deleting sessions on the Resource Server alone is insufficient. For OAuth2 API tokens, consider token revocation/introspection per protocol and policy.

### Remember-Me

A remember-me cookie/token can re-authenticate the user after the HTTP session is deleted. If the app uses persistent remember-me tokens, invalidate related tokens (or design security revisions/rotation). Otherwise, the browser can mint a new session from remember-me after revocation.

### WebSockets and Long-Lived Connections

A WebSocket/SSE connection authenticated during its handshake may keep operating after the HTTP session is deleted unless the app integrates connection closure, session invalidation events, or per-message re-authorization. Spring Session provides WebSocket integration; verify the actual mechanism used.

### Cookies in Browsers

You cannot directly delete cookies in another user's browser via a response sent to an admin. Deleting server-side sessions makes the old cookie **invalid** when used, while the browser may keep the cookie until it expires or is cleared. Responses to the browser owning the cookie can send `Set-Cookie` cleanup headers when it next calls the API.

## 12. Security Incident Response Workflow

A session revocation playbook should have clear steps:

1. **Identify scope:** specific session ID, user ID, tenant group, or the entire system. Record reason, actor, correlation/event ID, and timestamp.
2. **Block new credential creation where needed:** lock accounts, disable access, reset passwords, or rotate related keys per security decision.
3. **Persist state/revision durably:** this is the basis for every node to reject stale contexts.
4. **Revoke indexed sessions:** list by principal/account ID; delete from the centralized session store; handle errors with bounded retries.
5. **Revoke other tokens:** refresh tokens, remember-me, API keys, OAuth grants, bearer tokens per architecture.
6. **Notify/prompt re-authentication:** UX should explain the session is no longer valid without leaking incident details to unauthorized clients.
7. **Measure and verify:** new requests using old cookies/tokens must be rejected; locked accounts cannot log in; on password change, old credentials fail and new credentials work per policy.
8. **Post-incident monitoring:** look for surviving anomalous sessions, in-flight requests, rarely used endpoints, node sync drift, WebSockets, and unrevoked tokens.

For large-scale incidents, "revoke every session" can cause heavy load and user disruption. Design with batching/rate limiting, controlled retries, risk prioritization, and a centralized **revocation epoch** when mass invalidation is needed without deleting every ID instantaneously. Never blindly scan/wipe databases without knowing the namespace or scope.

## 13. Common Errors Table

| Symptom | Common Cause | How to Check |
|---|---|---|
| Account locked, yet old cookie still accesses API | Old session still holds `SecurityContext`; neither revoked nor version-checked | Call API again using a browser logged in before lock |
| `findByPrincipalName(...)` returns empty | Principal index not created, wrong username/account ID, different store | Inspect session store and context-indexing rules |
| Admin revoke returns 200, yet user can still log in | Account lock/password not updated, or other credentials still valid | Try new login with old and alternative mechanisms |
| Deleted session A, yet user has another browser | Only deleted current session instead of listing all sessions | Create 2 independent cookie jars and test |
| Request still finishes after revoke | Started before revocation | Check at business action/transaction boundaries |
| Multi-node app revokes inconsistently | Local session store/registry, eventual index/cache | Check routing, shared store, invalidation events |
| Changed password, yet JWT still accesses API | Resource server validates tokens independently of passwords | Check exp, introspection, revision, token revocation |
| Deleted session, yet browser logs back in automatically | Remember-me or active SSO | Revoke remember-me/OIDC sessions appropriately |
| `SessionInformation.expireNow()`, yet DB still has session | Registry only marks expired to handle on next request | Check `ConcurrentSessionFilter` and registry mechanism |
| Protected GET returns `403` instead of `401` | CSRF, missing role, or different entry point | Distinguish authentication, authorization, and filter chains |
| Password reset while locked still cannot log in | Demo reset does not auto-unlock | Verify separate unlock/approval policy |
| User kicked out, yet another request logs right back in | Revocation race with new login | Use account revision, write state first, control creation |

## 14. Checklist for Real Projects

- [ ] Clearly identify the session store (local Servlet, Redis, JDBC) and ensure all instances share one source.
- [ ] Able to look up **all** sessions by stable principal/account ID; tested indexing with two devices.
- [ ] On lock/reset, account state/security revision changes first before old sessions are revoked.
- [ ] Session list/delete failures are never swallowed; have retries/outbox, alerts, and outcome tracking.
- [ ] Block new logins when locked/disabled; new passwords are hashed with a proper encoder.
- [ ] Subsequent requests with old session cookies are rejected; do not check only the admin response.
- [ ] For sensitive actions, re-check status/revision at commit time to reduce in-flight request risks.
- [ ] Nodes share the account revision or update caches with bounded lag.
- [ ] Refresh tokens, remember-me, JWTs, API keys, and WebSockets are addressed separately.
- [ ] All lock/reset endpoints are protected by roles, actor verification, CSRF (for cookies), rate limiting, and auditing; never log session IDs or raw credentials.
- [ ] Tested multi-device, node restarts, session timeouts, races, and session-store failures.
- [ ] Notify users when re-login is required without disclosing sensitive incident details to unauthorized parties.

**Remember:** **Account locking** controls the next authentication; **session revocation** invalidates stored logins; **security revisions and checks at request/business boundaries** narrow gaps from races and stale sessions. In a real incident, also handle every active credential issuance mechanism.

### References

- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Concurrent Sessions Control](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html#_configuring_concurrent_session_control)
- [Spring Session 3.5 — Spring Boot JDBC](https://docs.spring.io/spring-session/reference/3.5/guides/boot-jdbc.html)
- [Spring Session — Find Sessions by Username](https://docs.spring.io/spring-session/reference/guides/boot-findbyusername.html)
- [FindByIndexNameSessionRepository API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/FindByIndexNameSessionRepository.html)
- [JdbcIndexedSessionRepository API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/jdbc/JdbcIndexedSessionRepository.html)
