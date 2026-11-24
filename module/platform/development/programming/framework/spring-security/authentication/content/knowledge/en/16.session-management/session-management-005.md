# Limiting Concurrent Sessions with maximumSessions

> Scope: **Spring Security - authentication → Session Management**. This lesson uses **Spring Boot 3.x / Spring Security 6.x (Servlet) / Java 17+**, with form login persisting state in `HttpSession`. The goal is to limit the number of authenticated sessions per account with `maximumSessions`; distinguish "new session replaces old session" from "block new login," understand `SessionRegistry`, test with two truly separate HTTP sessions, and handle the session lifecycle.

## 1. maximumSessions Is a Per-Principal Session Limit

The shortest configuration:

```java
http.sessionManagement(session -> session
    .maximumSessions(1)
);
```

`maximumSessions(1)` means each **authenticated principal** may have at most **one session considered active**. This is not a quota allowing only one user across the whole application, nor is it a limit on browser tabs, concurrent requests, or devices detected by IP.

| Component | Role |
| --- | --- |
| `Principal` | Authenticated identity; the registry must recognize that two logins belong to the same account |
| `HttpSession` | Server-side state, usually referenced by the browser via the `JSESSIONID` cookie |
| `SessionRegistry` | Maps principals to session IDs, last request timestamps, and expiration status |
| `ConcurrentSessionControlAuthenticationStrategy` | Upon successful authentication, decides whether a new session can be registered or an old one must expire/be blocked |
| `RegisterSessionAuthenticationStrategy` | Registers the accepted session |
| `ConcurrentSessionFilter` | Checks requests using sessions marked `expired` |
| `HttpSessionEventPublisher` | Publishes session-destroyed/ID-changed events so the registry can stay synchronized |
| `maximumSessions` | Session limit; `1` is one session, `-1` represents unlimited |

An example: `student` has session A in browser profile A. When logging in from profile B, the server can either let B replace A or reject B. `reviewer`, as a different account, still has its own quota and does not affect `student`.

**Two tabs in the same profile usually do not create two sessions.** They share the session cookie. Opening a new tab is not enough to test concurrent sessions; you need two separate browser profiles/cookie jars or two independent `MockHttpSession` instances.

## 2. Two Modes When Quota Is Reached

### 2.1. Default: Allow New Login and Expire the Old Session

```java
.sessionManagement(session -> session
    .maximumSessions(1)
    .maxSessionsPreventsLogin(false)
);
```

`maxSessionsPreventsLogin(false)` is the default. After A logs in, B logging in with the same principal is accepted; A is **marked `expired`** in the registry. `ConcurrentSessionFilter` will typically invalidate A **when the next request from A passes through**, and then run the expired session handling strategy. Do not confuse the `expired` flag with immediately closing every connection on device A.

If you add `expiredUrl("/session-expired")`, A's next request is redirected to `/session-expired`:

```text
Client A: POST /login     --> server registers session A --> A succeeds
Client A: GET /me         --> 200 student
Client B: POST /login     --> server marks A expired, registers B
Client B: GET /me         --> 200 student
Client A: GET /me         --> ConcurrentSessionFilter handles expired A
                           <-- 302 /session-expired
```

### 2.2. Optional: Keep the Old Session and Reject the New Login

```java
.sessionManagement(session -> session
    .maximumSessions(1)
    .maxSessionsPreventsLogin(true)
);
```

While A is still active, B logging in even with the correct password is blocked by the session strategy. With standard `formLogin`, `SessionAuthenticationException` is routed through the failure handler; the default behavior is usually a redirect to `/login?error`. A continues using the old session.

| When `student` logs in a second time | `false` (default) | `true` |
| --- | --- | --- |
| Session A | Marked expired, next request is blocked | Kept active |
| Session B | Login succeeds | Login rejected |
| Form B | Redirect on success | Redirect to failure URL |
| `expiredUrl` | For A's subsequent request after being expired | Not for B that was just rejected |
| Trade-off | User can switch devices; anyone with the password can kick the old device out | Keeps the active session; an abandoned old session can block new logins |

**Do not assume fixed HTTP status codes across all applications.** Form login usually uses redirects for both success and failure. With custom filters, JSON APIs, or other authentication mechanisms, statuses/handlers can differ; check `Authentication`, `SessionRegistry`, and access outcomes on subsequent requests.

## 3. Components Coordinating Upon Successful Login

```text
POST /login + username/password + CSRF
             |
             v
UsernamePasswordAuthenticationFilter
             |
             v
AuthenticationManager
      verifies credentials
             |
             v
SessionAuthenticationStrategy
  1. ConcurrentSessionControlAuthenticationStrategy
     - counts active sessions of the principal
     - expires old session or rejects new session
  2. Session fixation strategy (changeSessionId)
     - rotates ID if appropriate
  3. RegisterSessionAuthenticationStrategy
     - records session ID and principal in registry
             |
             v
SecurityContext is saved in session
             |
             '-- redirect per success/failure handler

GET /me with session A marked expired
             |
             v
ConcurrentSessionFilter -> handles expired session
             |
             '-- 302 /session-expired (if configured)
```

- `SessionRegistryImpl` tracks `SessionInformation`, including session ID, principal, `lastRequest`, and `isExpired()`. It stores data **in the memory of each application instance** when using the default implementation.
- `HttpSessionEventPublisher` translates Servlet session events into Spring events so the registry can clean up sessions that logged out, timed out, or changed IDs. Without this lifecycle mechanism, dead sessions can still count toward the quota.
- `SessionFixationProtectionStrategy` or `changeSessionId` protects the session ID during authentication; this is a **different** concern from session limits. Rotating the ID on the same session does not mean there is an extra device.
- In Spring Security 6, `SessionManagementFilter` is not added by default to infer every login automatically. Standard form login participates in the session strategy; if you write a custom authentication controller/filter, you must wire the strategy and persist `SecurityContext` properly. Simply calling `SecurityContextHolder.setContext(...)` is not enough to enforce concurrency limits.

**Expired**, **destroyed**, and **invalid session** are distinct: `expireNow()` marks a session as no longer allowed to continue due to quota; `HttpSession.invalidate()`/timeout destroys the session; a client sending a non-existent ID is an invalid session. `expiredUrl` relates to concurrency expiration, whereas `invalidSessionUrl` relates to invalid IDs and requires checking the active filters/session management setup.

## 4. Runnable Spring Boot Example

The example has two demo accounts to prove per-principal quotas: `student` / `study-pass` and `reviewer` / `review-pass`. It uses default form login without writing a custom authentication filter, because Spring Security already integrates the session concurrency strategy. The `demo.sessions.reject-new` property toggles the two modes without duplicating code.

### 4.1. Dependencies

In a Spring Boot 3.x project (Gradle/Java 17), add:

```groovy
// build.gradle - dependencies section
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### 4.2. Application

**`src/main/java/example/sessionlimit/SessionLimitApplication.java`**

```java
package example.sessionlimit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionLimitApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionLimitApplication.class, args);
    }
}
```

### 4.3. Security Configuration

**`src/main/java/example/sessionlimit/SecurityConfig.java`**

```java
package example.sessionlimit;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("study-pass"))
                .roles("USER")
                .build(),
            User.withUsername("reviewer")
                .password(encoder.encode("review-pass"))
                .roles("USER")
                .build()
        );
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
    SecurityFilterChain filterChain(
            HttpSecurity http, SessionRegistry registry, Environment env)
            throws Exception {

        boolean rejectNew = env.getProperty(
            "demo.sessions.reject-new", Boolean.class, false);

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/session-expired").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/me", true)
                .permitAll()
            )
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
                .sessionFixation(fixation -> fixation.changeSessionId())
                .maximumSessions(1)
                    .maxSessionsPreventsLogin(rejectNew)
                    .expiredUrl("/session-expired")
                    .sessionRegistry(registry)
            );

        return http.build();
    }
}
```

Explanation of choices:

1. `SessionRegistry` is a single bean passed into the concurrency config, allowing tests to inspect `SessionInformation` directly.
2. `HttpSessionEventPublisher` tracks the lifecycle (destroyed and ID changed); omitting it can leave stale slots after logout/timeout, especially with `maxSessionsPreventsLogin(true)`.
3. `SessionCreationPolicy.IF_REQUIRED` fits form login that stores `SecurityContext` in the session. `SessionCreationPolicy.STATELESS` is not for this scenario.
4. `changeSessionId` prevents session fixation upon authentication; the quota still counts authenticated sessions, not ID changes.
5. `defaultSuccessUrl("/me", true)` makes successful redirects predictable for tests; otherwise, form login may redirect to a saved request.
6. `expiredUrl("/session-expired")` applies to A after being marked expired; if B is rejected due to reject-new, the form failure handler redirects B to `/login?error`.
7. CSRF **remains enabled by default** for POST `/login` and `/logout`; there is no need to disable CSRF to run tests.

**`src/main/java/example/sessionlimit/WhoAmIController.java`**

```java
package example.sessionlimit;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/session-expired")
    String expired() {
        return "This session has been replaced";
    }
}
```

GET `/me` with `student`'s session returns the exact body:

```text
student
```

If A is marked expired, the next call to a protected endpoint with A redirects to `/session-expired`. This URL is permitted without authentication to avoid creating a redirect loop.

### 4.4. Switching Modes via application.yml

**`src/main/resources/application.yml`**

```yaml
demo:
  sessions:
    reject-new: false # false: new login replaces old session
server:
  servlet:
    session:
      timeout: 20m
      cookie:
        http-only: true
        same-site: lax
```

Set `demo.sessions.reject-new=true` to enable rejecting new logins. `server.servlet.session.timeout` adjusts the container's session idle timeout, **not** the concurrent session limit. Production needs HTTPS and `Secure` cookies, plus proper timeout/rotation/audit policies. The two in-memory accounts and demo passwords are for learning only.

## 5. MockMvc Testing: Two Truly Separate Sessions

Do not use `@WithMockUser` to test `maximumSessions`, because that utility places a mocked Authentication on the request without going through the full form login/session strategy. The two classes below use real `POST /login` requests (with CSRF). Each call to the `login()` helper **does not attach the previous session**, simulating two independent cookie jars.

### 5.1. Default: B Succeeds, A Is Expired

**`src/test/java/example/sessionlimit/ReplaceOldSessionTest.java`**

```java
package example.sessionlimit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = "demo.sessions.reject-new=false")
@AutoConfigureMockMvc
class ReplaceOldSessionTest {
    @Autowired MockMvc mvc;
    @Autowired SessionRegistry registry;

    private MockHttpSession login(String username, String password)
            throws Exception {
        MvcResult response = mvc.perform(post("/login")
                .with(csrf())
                .param("username", username)
                .param("password", password))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/me"))
            .andExpect(authenticated().withUsername(username))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) response.getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    @Test
    void secondLoginExpiresFirstSession() throws Exception {
        MockHttpSession first = login("student", "study-pass");

        mvc.perform(get("/me").session(first))
            .andExpect(status().isOk())
            .andExpect(content().string("student"));

        // A new POST /login, without passing session A.
        MockHttpSession second = login("student", "study-pass");
        assertNotEquals(first.getId(), second.getId());

        SessionInformation oldInfo =
            registry.getSessionInformation(first.getId());
        assertNotNull(oldInfo);
        assertTrue(oldInfo.isExpired());

        // A is blocked on its next request.
        mvc.perform(get("/me").session(first))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/session-expired"));

        // B can still access the protected resource.
        mvc.perform(get("/me").session(second))
            .andExpect(status().isOk())
            .andExpect(content().string("student"));
    }

    @Test
    void limitIsPerPrincipal() throws Exception {
        MockHttpSession student = login("student", "study-pass");
        MockHttpSession reviewer = login("reviewer", "review-pass");

        mvc.perform(get("/me").session(student))
            .andExpect(status().isOk())
            .andExpect(content().string("student"));

        mvc.perform(get("/me").session(reviewer))
            .andExpect(status().isOk())
            .andExpect(content().string("reviewer"));
    }

    @Test
    void loginStillRequiresCsrf() throws Exception {
        mvc.perform(post("/login")
                .param("username", "student")
                .param("password", "study-pass"))
            .andExpect(status().isForbidden());
    }
}
```

The first test observes two moments: immediately after B logs in, A already has `SessionInformation.isExpired()==true`; when A sends its next request, `ConcurrentSessionFilter` handles it and redirects. The second test proves the quota is not one session for the whole application; two different principals still operate concurrently.

### 5.2. Reject-New: B Is Rejected, A Continues Operating

**`src/test/java/example/sessionlimit/RejectSecondLoginTest.java`**

```java
package example.sessionlimit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = "demo.sessions.reject-new=true")
@AutoConfigureMockMvc
class RejectSecondLoginTest {
    @Autowired MockMvc mvc;
    @Autowired SessionRegistry registry;

    @Test
    void newLoginRejectedAndExistingSessionPreserved() throws Exception {
        MvcResult firstLogin = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "study-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/me"))
            .andExpect(authenticated().withUsername("student"))
            .andReturn();

        MockHttpSession first =
            (MockHttpSession) firstLogin.getRequest().getSession(false);
        assertNotNull(first);

        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "study-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andExpect(unauthenticated());

        SessionInformation firstInfo =
            registry.getSessionInformation(first.getId());
        assertNotNull(firstInfo);
        assertFalse(firstInfo.isExpired());

        mvc.perform(get("/me").session(first))
            .andExpect(status().isOk())
            .andExpect(content().string("student"));
    }
}
```

Expected outcome: B cannot log in despite valid credentials and is redirected to `/login?error`; A remains active. This differs from a wrong-password error even though it shares the same failure URL. In a real system, do not rely on user-facing messages to classify the cause; use proper server auditing and avoid disclosing security details.

### 5.3. Running and Understanding Test Limitations

In the Spring Boot project root containing the Gradle wrapper:

```bash
./gradlew test --tests example.sessionlimit.ReplaceOldSessionTest
./gradlew test --tests example.sessionlimit.RejectSecondLoginTest
./gradlew bootRun
```

On Windows use `gradlew.bat`. The example has a total of **4 `@Test` methods**; this is the **expected behavior of the code**, not a claim that Gradle was run inside this document. MockMvc simulates Servlet requests/sessions and verifies the filter chain; it does not fully test real cookies, container timeouts, or distributed session stores.

Tests may share a cached ApplicationContext. When writing a large suite with the same username, sessions registered in an earlier test can affect a later test. Clean up the registry or intentionally isolate contexts when needed, especially with reject-new mode. Do not use `Thread.sleep` to simulate timeouts: test that logic using a real container/session store or reliable lifecycle control APIs.

## 6. Manual Testing with Two Browsers

With `demo.sessions.reject-new=false`:

1. Open profile A, go to `http://localhost:8080/login`, and log in as `student` / `study-pass`. `GET /me` returns `student`.
2. Open a different profile B (or an incognito browser with a separate cookie store), and log in with the same account. `GET /me` on B returns `student`.
3. Return to A and reload `/me`. A's request should now redirect to `/session-expired`.
4. If you only open two tabs in the same profile, they normally share one `JSESSIONID` cookie and one session, so do not conclude `maximumSessions` is broken.

With `demo.sessions.reject-new=true`, after resetting the test environment:

1. A logs in successfully. B logs in with the same account and receives a failure redirect.
2. A can still view `/me`. B cannot view `/me` with an unauthenticated session.
3. A logs out **properly** via POST `/logout` with CSRF. Once the Servlet container and registry receive the session-destroyed event, the slot must be freed so B can log in. Simply closing the tab does not guarantee logout is called; the server may have to wait for idle timeout.
4. If B cannot log in after logout/timeout, inspect the publisher, session registry, and session store; do not arbitrarily raise the quota to mask a stale registry bug.

Never put real `JSESSIONID` cookies, CSRF tokens, or raw passwords into logs, issues, or shared screenshots. Production requires HTTPS, `HttpOnly` and `Secure` cookies, appropriate `SameSite`, timeout management, and session revocation mechanisms.

## 7. Important Misconceptions and Limitations

### 7.1. Number of Tabs Is Not Number of Sessions

Two tabs sharing cookies are usually the same session; one user can also have multiple browser profiles or app clients creating different sessions on a single device. `maximumSessions` relies on session IDs and the principal; it **does not identify hardware devices**, and does not lock by IP or User-Agent.

### 7.2. A Session Marked Expired Is Not Destroyed Immediately

In default mode, B logging in causes the registry to mark A expired. A may still remain in memory until its next request is handled by `ConcurrentSessionFilter`. The browser might still display cached content until it calls the server. Do not use this mechanism to claim "all of A's WebSocket connections were instantly severed."

### 7.3. equals/hashCode of Custom Principals Must Be Consistent

`SessionRegistryImpl` uses a principal-keyed map. If a custom `UserDetails`/principal does not override `equals()` and `hashCode()` properly, two objects for the same account can be treated as two different users, breaking the quota. Use a stable account ID; avoid including mutable state such as roles/displayName/lastLogin in equality. Spring Security's `User` is sufficient for the demo.

### 7.4. HttpSessionEventPublisher Must Be Actually Registered

The registry must know when a session is destroyed or its ID changes. Without the right listener, sessions that logged out or timed out can still count as active; `maxSessionsPreventsLogin(true)` can easily lock users out due to stale records. A `@Bean HttpSessionEventPublisher` in a Spring Boot Servlet app or the corresponding listener in `web.xml` is the standard setup. Test lifecycle behavior on a real container because MockMvc has limitations regarding event scheduling.

### 7.5. Concurrent-Session Quotas Do Not Replace Timeouts or Session Fixation

`server.servlet.session.timeout` defines inactivity timeout, `maximumSessions` counts authenticated sessions, `changeSessionId` protects against session fixation, and `expiredUrl` specifies where to redirect when concurrency expiration is handled. Do not infer one configuration from another.

### 7.6. Multiple JVMs Require a Distributed Registry

The default `SessionRegistryImpl` is in-JVM memory; if there are three instances behind a load balancer, each node may not know about sessions on other nodes. With Spring Session (Redis/JDBC), you can use a compatible registry solution such as `SpringSessionBackedSessionRegistry` and verify lifecycle, TTL, sticky routing, expiration events, and races between login requests. Do not assume merely adding the Spring Session dependency guarantees cluster-wide quotas; multi-node integration testing and atomicity evaluation are required.

### 7.7. Custom Login and Other Authentication Mechanisms

In Spring Security 6, standard form login applies the session strategy after authentication. A custom controller/filter that only calls `AuthenticationManager.authenticate(...)` and `SecurityContextHolder.setContext(...)` **without** invoking the session strategy can bypass `maximumSessions` limits. You must integrate the strategy, fixation protection, session registration, and `SecurityContextRepository.saveContext(...)` per contract. Remember-me/OAuth2 logins have their own hooks; always test the real flow.

### 7.8. Stateless JWTs Are Not Limited by HttpSession Quotas

`SessionCreationPolicy.STATELESS` + Bearer JWT does not bind each token to an `HttpSession` or `SessionRegistryImpl`. `maximumSessions(1)` does not limit how many JWTs are issued or revoke old JWTs. If a product needs "only one token/device," design it at the authorization server via refresh-token rotation, grant tracking, introspection, or an appropriate revocation list.

### 7.9. Role-Based Limits Can Be Configured Dynamically

Spring Security 6.5 provides an overload accepting a limit computed from `Authentication`; for example, if USER gets only one session while ADMIN gets two sessions:

```java
.sessionManagement(session -> session
    .maximumSessions(authentication ->
        authentication.getAuthorities().stream()
            .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()))
                ? 2 : 1
    )
);
```

This is a **different illustrative approach**, not a direct addition to the fixed `maximumSessions(1)` configuration in section 4. Authorities must be verified from a server source; never trust client-supplied roles. When permissions change while an old session is still alive, define a refresh/re-authentication policy and test dynamic quotas.

## 8. Common Errors and How to Troubleshoot

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| Opening a new tab does not trigger the quota | Same `JSESSIONID`, same session | Test with two independent cookie jars/profiles |
| B logs in successfully, yet A is not kicked out immediately | A is only marked expired, has not sent a request yet | Check `SessionInformation.isExpired()` and A's next request |
| B enters the right password, yet receives `/login?error` | `maxSessionsPreventsLogin(true)` quota is full | Check policy, session registry, failure/audit logs |
| A logs out, yet B is still rejected | Missing session event or stale registry | Verify `HttpSessionEventPublisher` and timeout cleanup |
| Quota does not work for custom principal | `equals`/`hashCode` do not recognize the same account | Use a stable account ID in `equals/hashCode` |
| Quota does not work with custom login | Session authentication strategy was not invoked | Integrate the right strategy or use standard authentication filters |
| Adding more nodes allows logins past the quota | `SessionRegistryImpl` is local to each JVM | Choose a distributed registry/session store, test multi-node |
| `expiredUrl` is not used on session timeout | Quota expiration differs from invalid ID/timeout | Separate configurations and test |
| Old JWT remains valid after a new login | Stateless JWTs have no HttpSession quota | Design token lifecycle/rotation/revocation at the issuer |
| One user causes another user to lose their session | Unstable principal mapping or shared session | Check registry principals, equality, cookies |
| A is marked expired, yet UI still shows content | Browser cache, no new HTTP request yet | Check network requests and separate push mechanisms if needed |

## 9. Operational Guidance and Security Trade-Offs

Old-session replacement mode lets users switch machines easily, but anyone with a leaked password can also kick the active session out. Reject-new mode preserves the active session, yet users can get stuck if a device is lost or a tab is closed before the server times out. Therefore, combine this with rate limiting, MFA for sensitive accounts, unusual-login alerts, a page to view and revoke sessions, account recovery flows, idle/absolute session timeouts, and auditing.

Do not use `maximumSessions` as a defense against brute-force attacks or all forms of account sharing. Changing a session quota does not prove two logins belong to the same individual, nor does it protect stolen cookies. When "sign out all devices" is required, manage session lifecycles, separate tokens, long-lived connections, and cached content outside the session.

## 10. Completion Checklist

- [ ] Real form login runs on a Servlet SecurityFilterChain with `maximumSessions(1)`.
- [ ] `HttpSessionEventPublisher` and a consistent `SessionRegistry` are present in configuration/tests.
- [ ] Understand that quotas apply **per principal**, not per tab or HTTP request.
- [ ] Created two separate HTTP sessions to test the same username.
- [ ] With `maxSessionsPreventsLogin(false)`, B logs in successfully, A is marked expired, and A is blocked on its next request.
- [ ] With `maxSessionsPreventsLogin(true)`, B is not authenticated and A remains active.
- [ ] Verified login still requires CSRF; logout uses POST with a valid token.
- [ ] Distinguished expired sessions from destroyed sessions, timeouts, and invalid session IDs.
- [ ] Custom principals implement `equals`/`hashCode` based on a stable identity.
- [ ] Verified logout/timeout/session ID change and registry cleanup on a real Servlet container.
- [ ] When deploying multiple nodes, do not rely on a single in-memory registry to claim cluster-wide quotas.
- [ ] Do not confuse HttpSession concurrency with limiting stateless JWT/Bearer tokens.
- [ ] UX and security support users when a session is replaced or a new login is rejected.

### Official Documentation

- [Spring Security 6.5 — Authentication Persistence and Session Management: Concurrent Session Control](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security — SessionRegistry API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/session/SessionRegistry.html)
- [Spring Security — SessionInformation API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/session/SessionInformation.html)
- [Spring Security — ConcurrentSessionControlAuthenticationStrategy](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/ConcurrentSessionControlAuthenticationStrategy.html)
- [Spring Security — HttpSessionEventPublisher](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/session/HttpSessionEventPublisher.html)
- [Spring Security — FAQ: browser windows and HttpSession](https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/faq.html)
- [Spring Session — Spring Security Integration](https://docs.spring.io/spring-session/reference/spring-security.html)
