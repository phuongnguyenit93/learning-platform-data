# Testing Session Fixation, Concurrent Sessions, Remember-Me, and Logout in Spring Security Servlet

> **Learning environment:** Spring Boot 3, Spring Security 6, Java 17+, Spring MVC Servlet, JUnit 5, MockMvc, and Spring Security Test. The topic is **testing HTTP behavior and session-based authentication lifecycles**, not merely reading configuration and assuming security works. The Spring examples require a Spring Boot application with the corresponding dependencies; the standalone Java program in section 3 runs independently to practice expressing testing invariants.

## 1. Why Test All Four Mechanisms Together?

Form-based login typically creates or uses an `HttpSession` containing a `SecurityContext`. Spring Security provides related protections that are not synonymous:

1. **Session fixation protection:** changes the session identifier after login, preventing an attacker from exploiting a session ID planted before the victim authenticates.
2. **Concurrent session control:** limits the number of active sessions for the same principal, choosing either to reject new logins or to expire old sessions.
3. **Remember-me authentication:** allows a remember-me cookie to re-create an `Authentication` when the regular session is gone, carrying its own token risks.
4. **Logout:** destroys the current session's authentication state and handles cookies/context, yet may **not automatically revoke** every kind of remember-me token or every session on other devices.

**A test saying "POST /login returns 302" does not prove these four mechanisms work.** You must observe the session ID, `Authentication` state on subsequent requests, `SessionRegistry`, remember-me cookies, logout with CSRF, and the outcome when attempting to reuse old credentials.

Commonly missed bugs: the `JSESSIONID` cookie rotates yet permissions are never checked; a second login succeeds despite a max-one-session setting; logout clears the browser cookie yet a copied remember-me token still works; `GET /logout` is mistaken for a logout trigger while CSRF is enabled.

## 2. Concepts Before Writing Tests

### 2.1. SecurityContext and HttpSession

In a Servlet app using form login, `SecurityContextHolder` holds the `Authentication` during request processing; `SecurityContextRepository` can store/load the context via `HttpSession`. The browser holds the `JSESSIONID` cookie to resume the session. One user can hold multiple distinct sessions if logged in from two browsers/devices.

- **`Authentication`:** authenticated principal and authorities.
- **`SecurityContext`:** object holding `Authentication` for security filters.
- **`HttpSession`:** Servlet state store with an ID and attributes; not equivalent to an access token.
- **`SessionRegistry`:** tracks sessions managed by Spring Security to enforce concurrency policies; not an automatic replica of every session across a whole cluster.
- **Remember-me cookie:** a longer-lived credential than a regular session, usable to auto-authenticate subsequent requests.
- **`LogoutHandler` / `LogoutSuccessHandler`:** cleans up session, context, cookies/tokens, and handles post-logout navigation.

Never rely solely on `Authentication.isAuthenticated()` as proof a user is authenticated: anonymous tokens can also be represented by an `Authentication` in the framework. Use authorization rules, `SecurityContextHolderAwareRequestWrapper`/`Principal`, or `AuthenticationTrustResolver` in the right context.

### 2.2. Quick Expectations Table

| Event | HTTP request to simulate | Invariant to verify |
| --- | --- | --- |
| Successful login with existing session | `POST /login` with pre-login session and CSRF token | Session ID rotates; principal can still access authorized resources |
| Failed login | `POST /login` with wrong password | No valid `Authentication` created; no new remember-me cookie issued |
| Concurrent sessions exceed threshold | Log in same user on two different sessions | Old session expired **or** new login rejected per policy |
| Remember-me selected | Login with `remember-me=on` | Remember-me cookie sent; a request without session yet with cookie authenticates |
| Remember-me not selected | Login without the option | No new remember-me cookie issued per demo config |
| Valid logout | `POST /logout` with session/cookie and CSRF | Current session invalidated, remember-me cookie cleared at client, requests no longer logged in via that session |
| Logout missing CSRF | `POST /logout` without CSRF token when CSRF enabled | Rejected; session remains valid with no logout side effects |
| Copied remember-me cookie | Replay old cookie after logout | Depends on token-based vs persistent-token design; not automatically revoked by default |
| Logged out on one browser, another remains online | Session A logs out, session B exists | Needs an explicit logout-all policy; default logout does not destroy all sessions |

## 3. Session Fixation: What Needs Checking?

**Session fixation**: an attacker creates/knows a session ID before the victim logs in; if the server keeps the same ID after elevating the state to authenticated, the attacker can try reusing that ID to hijack the authenticated session.

Spring Security Servlet uses `SessionAuthenticationStrategy` for interactive login; on Servlet 3.1+, the typical `changeSessionId()` policy rotates the ID upon authentication without losing existing session attributes. Related strategies:

| Strategy | Meaning | Testing notes |
| --- | --- | --- |
| `changeSessionId()` | Uses Servlet `HttpServletRequest.changeSessionId()` | Before/after IDs must differ; attributes are usually preserved |
| `migrateSession()` | Creates a new session, copies session attributes | Verify new ID and that required attributes were preserved |
| `newSession()` | Creates a new session, limits carrying over old attributes | Do not expect all custom session attributes to survive |
| `none()` | Does not rotate session ID | Avoid in standard form login unless a very specific threat model dictates |

On modern Servlet apps, **ID rotation at successful login** is the most important check. Never assume an HTTP 302 redirect means the ID changed; custom controller/logic could redirect without invoking an authentication strategy.

### 3.1. Test Flow

```text
Request 1: GET /login
     -> receives HttpSession/S1 (if the app creates one)
Request 2: POST /login [username, password, CSRF] with S1
     -> login succeeds
     -> server rotates session ID: S1 -> S2
Request 3: GET /private with S2
     -> right principal, allowed
Request 4: handcrafted request reusing ID S1 against real container
     -> must not inherit the authenticated session
```

**Important:** `MockHttpSession` in Spring Test can **mutate the ID in place on the same object** when `changeSessionId()` is called. Therefore `assertNotEquals(beforeId, session.getId())` is useful for checking rotation in MockMvc, yet **does not fully prove** a real Servlet container rejects the old ID over an independent HTTP connection. The "old cookie cannot be replayed" invariant needs an integration test against a **real container** with a browser/HTTP client managing separate cookies.

### 3.2. Standalone Java 17: Session Lifecycle Invariants

This is purely a Java exercise to model the conditions, **not a Servlet container simulation**. File `SessionInvariantDemo.java`:

```java
import java.util.Objects;

public final class SessionInvariantDemo {
    static void assertRotated(String before, String after) {
        if (Objects.equals(before, after)) {
            throw new IllegalStateException("Session ID was not rotated");
        }
    }

    static boolean needsNewAuthentication(
            boolean authenticatedSession, boolean rememberMeCookiePresent) {
        return !authenticatedSession && !rememberMeCookiePresent;
    }

    public static void main(String[] args) {
        assertRotated("S1", "S2");
        System.out.println("rotated=true");
        System.out.println("reauth=" + needsNewAuthentication(false, false));
        System.out.println("reauth=" + needsNewAuthentication(false, true));
    }
}
```

Run:

```bash
javac SessionInvariantDemo.java
java SessionInvariantDemo
```

Exact stdout:

```text
rotated=true
reauth=true
reauth=false
```

`needsNewAuthentication` in this example **checks only cookie presence to illustrate test-case selection**; it never implies "cookie present means the token is valid". Real systems must **verify the remember-me credential** before creating an `Authentication`. Never use this modeling helper as authentication logic.

## 4. Concurrent Sessions: Reject New or Expire Old?

Spring Security supports **maximum sessions** for session-based authentication. There are two policies:

- `maximumSessions(1).maxSessionsPreventsLogin(false)`: when the same user logs into a new session, the old session can be marked **expired**; when the old session sends another request, `ConcurrentSessionFilter` handles it as configured (for example redirecting to `/session-expired`). The new session continues working.
- `maximumSessions(1).maxSessionsPreventsLogin(true)`: rejects the new authentication once the user reaches the limit; the existing session stays active. Depending on the login flow, the failure handler may redirect back to the login form with an error flag rather than returning HTTP 403 directly.

**Do not verify the policy solely from the status of the second login.** In expire-old mode, the second login still succeeds; you must issue a new request with the old session to prove it gets blocked.

### 4.1. SessionRegistry and HttpSessionEventPublisher

In an in-memory Servlet setup, `SessionRegistryImpl` tracks sessions by principal. `HttpSessionEventPublisher` bridges Servlet lifecycle events to Spring Security, cleaning up the registry when sessions are destroyed (logout/invalidation/timeout per container and events). Without a proper listener or registry, timed-out sessions can remain marked active in the registry, wrongly rejecting new logins or skewing session counts.

Notes:

- With multiple application instances, in-memory `SessionRegistryImpl` **is not a distributed registry**. Integrate **Spring Session** with an appropriate session-repository-backed registry (such as `SpringSessionBackedSessionRegistry` per version/integration) or design centralized session management.
- `SessionRegistry` relies on consistent principal `equals`/`hashCode`. A mutable custom principal or one loaded with inconsistent equality can prevent the same user from being counted as one principal.
- Session timeouts, invalidation, logout, and expiration policies must be tested in a real container/cluster, not only with mocks.

### 4.2. Concurrent Cases for QA

| Test case | Expected under expire-old | Expected under prevent-new |
| --- | --- | --- |
| Alice logs in on browser A | A works | A works |
| Alice logs in on browser B | B gets a new session; A marked expired | B login rejected; A continues working |
| A calls endpoint after B logs in | A handled as expired | A still authenticated |
| B calls endpoint after B logs in | B succeeds | B unauthenticated per rejected login |
| A logs out / times out | Registry drops A when lifecycle event fires | Slot freed for a new login |
| Bob logs in separately | Does not consume Alice's quota | Does not consume Alice's quota |
| Two simultaneous logins | Does not exceed limit per deployment/registry capability | Race conditions require controlled integration tests |
| Multi-node A/B | Consistent behavior across nodes per design | Must not rely on isolated per-node registries |

## 5. Remember-Me: Not a Long-Lived Session

Remember-me supports automatic re-login when the browser no longer has a valid `HttpSession` yet still sends a remember-me cookie. In Spring Security Servlet, two options are common:

### 5.1. Token-Based Remember-Me

`TokenBasedRememberMeServices` uses a cookie protected by a signature built from username, expiry, algorithm, and the server's **secret key**, along with fields like password hash per the implementation protocol. No separate database token record is needed, yet:

- If the token was **copied**, clearing the browser cookie on logout **does not guarantee** the copied token immediately becomes invalid.
- Tokens expire over time or fail verification if the secret key/signing inputs change.
- Changing passwords can affect token-based credential validity depending on implementation/format; **do not** treat this as selective per-device revocation.
- The key must be a strong secret stored outside source code/in a secret manager and kept consistent across replicas if tokens must work across nodes. Changing the key invalidates old tokens.
- A remember-me token grants the user's `Authentication` upon automatic login, yet Spring Security distinguishes `isRememberMe()` from `isFullyAuthenticated()`. Sensitive actions should require **reauthentication** instead of remember-me alone.

### 5.2. Persistent-Token Remember-Me

`PersistentTokenBasedRememberMeServices` uses a `PersistentTokenRepository` such as a JDBC repository to store **series/token** pairs and manage rotation per implementation behavior. State no longer lives solely in the browser. Benefit: **server-side token series revocation**, especially on logout, credential reset, or compromise response.

With persistent tokens, when a user logs out and `RememberMeServices.logout` deletes the series from the repository, a copied cookie **is no longer accepted** in a proper architecture. Test both the response cookie and the **server-side lookup after logout**, because checking `Max-Age=0` on the cookie does not prove the token was invalidated.

Example Spring Security JDBC persistent remember-me schema (columns vary slightly by version/DB):

```sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
```

This is a **reference schema** for common JDBC token repositories; check the official DDL for your app's version, dialect, and migrations before applying. For apps needing audit/retention, a custom repository can be used; protect the DB, never log raw tokens, restrict access, and test rotation/races.

### 5.3. Remember-Me Is Not Equivalent to an OAuth2 Access Token

A remember-me cookie is a credential for Spring Security **web authentication**, not a Resource Server JWT, OAuth2 refresh token, or `JSESSIONID` cookie. Do not use the word "token" to conflate distinct lifecycles:

| Credential | How is it sent? | Who verifies it? | What does default logout affect? |
| --- | --- | --- | --- |
| `JSESSIONID` | Auto-sent browser cookie | Servlet session store + Spring Security context | Can invalidate the current session |
| Token-based remember-me cookie | Auto-sent longer-lived browser cookie | `RememberMeServices` + secret/password state | Clears client cookie; copies may remain valid |
| Persistent remember-me cookie | Browser sends series/token cookie | `RememberMeServices` + repository record | Can delete server-side series/tokens per implementation |
| OAuth2 bearer access token | `Authorization: Bearer ...` sent by client | JWT decoder / token introspector | Session logout does not revoke access tokens |
| OAuth2 refresh token | Held/sent by OAuth2 client to token endpoint | Authorization Server | Needs separate revocation/rotation policy |

## 6. Logout: Test State, Not Just the Redirect

When CSRF protection is enabled, Spring Security by default protects logout with **POST `/logout` plus a CSRF token**. `GET /logout` may render a confirmation page instead of logging out (depending on UI/framework config). Therefore a test saying "GET `/logout` is enough" can misjudge behavior.

Logout typically performs:

1. Clears `Authentication` and `SecurityContext` for the request via `SecurityContextLogoutHandler`.
2. Invalidates the current `HttpSession` (if present), preventing that session ID from staying authenticated.
3. Invokes `RememberMeServices` logout/cookie deletion when configured.
4. May delete the `JSESSIONID` cookie via delete-cookie policy; note cookie path/domain must match so the browser actually deletes the right cookie.
5. May redirect to a confirmation page or target URL (such as `/login?logout`).
6. **Does not by default log out all devices**, wipe all browser storage, revoke OAuth access tokens, or invalidate copied tokens.

### 6.1. Testing Logout with CSRF

| Request | Expectation |
| --- | --- |
| POST `/logout` + valid session + CSRF token | Logout executes, session invalidated, cookies cleared, redirect succeeds |
| POST `/logout` + valid session yet missing CSRF | Typically 403 and **does not invalidate** session |
| POST `/logout` + remember-me cookie | Remember-me cookie cleared in response; persistent series may be revoked |
| GET `/private` after logout, without remember-me | No longer authenticated via session; redirected to login or 401 per API/web |
| Reusing old session ID in real container | Must not access as the logged-out user |
| Reusing copied token-based remember-me | May still work: assess risk and implement proper revocation |
| Logout at A while B holds a separate session | B can still operate unless a logout-all rule exists |
| Logout success handler fails | Must not leave session/auth valid just because the redirect response failed |

If using **cookie-based authentication**, CSRF still applies even when controllers return JSON. Remember-me cookies are auto-sent by browsers, so CSRF must still be evaluated for sensitive endpoints.

## 7. Sample Spring Boot 3 / Spring Security 6 App for Testing

The configuration below is for a **Spring Boot Servlet app with `@SpringBootApplication`**, with matching dependencies:

- `spring-boot-starter-web`, `spring-boot-starter-security`.
- `spring-boot-starter-test` and `spring-security-test` in test scope.
- Java 17+. Java code cannot run via plain `javac` without Spring dependencies and bootstrapping classes.
- Demo users `alice`/`bob`; passwords are BCrypt-hashed at startup. **Never use demo users or sample passwords in production environments.**

### 7.1. SecurityConfig.java

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
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
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("test-password"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("test-password"))
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
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SessionRegistry registry,
            UserDetailsService users,
            @Value("${app.security.remember-me-key}") String rememberMeKey)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/session-expired").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .defaultSuccessUrl("/private", true))
            .rememberMe(remember -> remember
                .key(rememberMeKey)
                .tokenValiditySeconds(60 * 60 * 24)
                .userDetailsService(users))
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.changeSessionId())
                .maximumSessions(1)
                .maxSessionsPreventsLogin(false)
                .expiredUrl("/session-expired")
                .sessionRegistry(registry))
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID"));

        return http.build();
    }
}
```

Default `formLogin` handles `POST /login` with `username`/`password` fields, CSRF is enabled by default, and the form uses the default `remember-me` parameter. `maximumSessions(1)` caps session authentication, and `maxSessionsPreventsLogin(false)` marks the old session expired. `expiredUrl` specifies where the next request from an expired concurrent session redirects.

`rememberMe(...)` here uses **token-based remember-me**, not JDBC persistent. That is why **logout clears the cookie yet does not perform server-side revocation of every copy**. `rememberMeKey` must come from a secret store consistent across nodes; never hard-code production keys.

Example configuration in `application.yml`:

```yaml
app:
  security:
    remember-me-key: ${REMEMBER_ME_KEY}
```

The `REMEMBER_ME_KEY` environment variable must be supplied when running the app. In tests, we supply a test-specific property. Never commit production secrets into source control.

**`SessionRegistryImpl` suits only a single-node example.** When serving multiple replicas, design a shared session registry and backend session store; test through a load balancer and verify session timeouts. This configuration also **does not provide a built-in revoke-all-devices mechanism**.

### 7.2. Dedicated Controller for Testing

File `PrivateController.java`:

```java
import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PrivateController {

    @GetMapping("/private")
    String privateEndpoint(Principal principal) {
        return principal.getName();
    }

    @GetMapping("/session-expired")
    String expired() {
        return "session-expired";
    }
}
```

Accessing `GET /private` with Alice's valid session returns body `alice`; Bob returns `bob`. When anonymous, the security chain redirects to login instead of invoking the controller. In real apps, never check only principal name: enforce authorization/ownership and data permissions.

### 7.3. Test Environment

The tests below assume component scanning covers `SecurityConfig` and `PrivateController`, a `@SpringBootApplication` class exists in a matching parent package, and the stated test dependencies are present. Tests use MockMvc to pass through servlet filters and mock session lifecycles; real Servlet container/browser cookie behavior still requires independent integration tests.

## 8. MockMvc: Login, Session ID Rotation, and Post-Login Access

File `SessionSecurityTests.java`, using JUnit 5:

```java
import jakarta.servlet.http.Cookie;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties =
    "app.security.remember-me-key=unit-test-only-secret-replace-for-real-use")
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class SessionSecurityTests {

    @Autowired
    MockMvc mvc;

    private MvcResult login(
            MockHttpSession session, String username,
            boolean rememberMe) throws Exception {
        MockHttpServletRequestBuilder request = post("/login")
            .session(session)
            .with(csrf())
            .param("username", username)
            .param("password", "test-password");

        if (rememberMe) {
            request.param("remember-me", "on");
        }

        return mvc.perform(request)
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/private"))
            .andReturn();
    }

    @Test
    void changesSessionIdAfterSuccessfulLogin() throws Exception {
        MockHttpSession session = new MockHttpSession();
        String before = session.getId();

        login(session, "alice", false);

        assertNotEquals(before, session.getId());
        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void secondLoginExpiresFirstSession() throws Exception {
        MockHttpSession first = new MockHttpSession();
        MockHttpSession second = new MockHttpSession();

        login(first, "alice", false);
        login(second, "alice", false);

        mvc.perform(get("/private").session(first))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/session-expired"));

        mvc.perform(get("/private").session(second))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void rememberMeCookieAuthenticatesWithoutOldSession()
            throws Exception {
        MockHttpSession session = new MockHttpSession();
        MvcResult loggedIn = login(session, "alice", true);

        Cookie rememberCookie =
            loggedIn.getResponse().getCookie("remember-me");
        assertNotNull(rememberCookie);

        // Do not send JSESSIONID or the old MockHttpSession:
        // re-authenticate using the remember-me cookie.
        mvc.perform(get("/private").cookie(rememberCookie))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void logoutRequiresCsrfAndClearsCurrentSession()
            throws Exception {
        MockHttpSession session = new MockHttpSession();
        MvcResult loggedIn = login(session, "alice", true);
        Cookie rememberCookie =
            loggedIn.getResponse().getCookie("remember-me");
        assertNotNull(rememberCookie);

        // Missing CSRF: request rejected, session not logged out.
        mvc.perform(post("/logout").session(session)
                .cookie(rememberCookie))
            .andExpect(status().isForbidden());

        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));

        MvcResult loggedOut = mvc.perform(post("/logout")
                .session(session)
                .cookie(rememberCookie)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        assertTrue(session.isInvalid());

        Cookie deletion =
            loggedOut.getResponse().getCookie("remember-me");
        assertNotNull(deletion);
        assertEquals(0, deletion.getMaxAge());

        // Fresh request without old cookie or session:
        mvc.perform(get("/private"))
            .andExpect(status().is3xxRedirection());
    }
}
```

**Detailed explanation and limitations:**

- `MockHttpSession` is a test object; when `changeSessionId()` is called, this object can have its ID updated *in place*. Check before/after IDs, yet **do not use it as absolute proof against replay with an old cookie ID**.
- `csrf()` from `spring-security-test` generates a CSRF token for the simulated request. The CSRF session per test must align; if the app replaces `CsrfTokenRepository`, update tests accordingly.
- Logging in twice as the same user tests the **expire-old** policy in the configuration. The second test must hit endpoints with **both the old session and the new session**, rather than only checking post-login redirects.
- The remember-me test **sends no old session**, distinguishing remembered authentication from continuing to use `JSESSIONID`. It still creates a new session/context if the filter chain is configured that way; that does not invalidate that the remember-me cookie was tested.
- The logout test only confirms the browser is told to **delete the remember-me cookie** and the current session is invalidated. **Do not claim** that a token-based remember-me cookie copied by an attacker will be rejected by the server after logout.
- `@DirtiesContext(AFTER_EACH_TEST_METHOD)` isolates registry and session/authentication state across tests for the lesson. In large suites, recreating `ApplicationContext` per test is costly; replace with explicit fixtures/resets to optimize.

**Note on runnability:** these classes must sit in proper packages with a real Spring Boot startup class; controller/test are not standalone Java files. Spring Security 6.x version and test Servlet container differences can affect exact statuses/headers; verify against your dependencies and run the tests rather than inferring from code unexecuted.

### 8.1. Additional Cases Needed for Session Fixation

Beyond `assertNotEquals`, also verify:

1. Login with wrong password **does not** create an authenticated session for Alice or issue remember-me.
2. Session attributes expected to survive still exist after `changeSessionId`, such as valid flow-state values.
3. The `JSESSIONID` received by the browser after login reflects the new session; cookie path/domain/SameSite/Secure context matches policy.
4. Use a **real HTTP client** with two cookie jars: one holding the pre-login ID, one holding the post-login ID. The cookie jar with the old ID must not access `/private` as Alice.
5. Logout with the new ID destroys the session; the **old pre-login ID** must not "come back to life".
6. If Spring MVC/controllers rotate sessions manually or custom auth bypasses Spring Security, add tests proving the strategy still runs at login.

If the auth flow uses **OAuth2 login, SAML2 login, or a custom authentication filter**, verify that flow's actual session authentication strategy; do not assume it behaves identically to the sample form login.

## 9. Testing Concurrent Sessions Under Prevent-New Policy

The second mode changes configuration to:

```java
// Illustrative DSL snippet inside sessionManagement configuration:
.sessionManagement(session -> session
    .maximumSessions(1)
    .maxSessionsPreventsLogin(true)
    .sessionRegistry(registry))
```

This is a **snippet**, not a complete class. When `maxSessionsPreventsLogin(true)`:

- Alice logs into session A successfully.
- Alice tries logging into session B while A is still valid: the new authentication **is rejected**; the form-login handler may redirect to `/login?error` or a configured error route.
- A keeps working.
- After A logs out/times out and the registry updates properly, B can log in on a new attempt.

Tests should verify:
- Login B does not issue an authenticated session (not just checking status).
- A can still access `/private`.
- Once A is destroyed/logged out and the event publisher/registry receives the lifecycle event, the user can create a new session.
- No cross-user interference: Alice's quota does not affect Bob.
- When two logins arrive simultaneously, the policy is enforced consistently enough; stress/race tests are more valuable than a single sequential MockMvc test.

Do not conclude "concurrent sessions are just two tabs in the same browser". Two tabs in the same browser profile normally share the `JSESSIONID` cookie, so they do not necessarily create **two independent sessions**. Use two browser profiles, cookie jars, or separate `MockHttpSession` instances to test.

## 10. Remember-Me: More Negative Tests and Revocation Checks

### 10.1. Not Selecting Remember-Me

Test a successful login without sending `remember-me=on`, then confirm the response **issues no new remember-me cookie**. Note that a remember-me cookie from an earlier login may still sit in a browser; tests need a clean cookie jar rather than assuming daily browser state.

### 10.2. Tampered or Expired Cookies

Test altering part of the cookie value, expiring it, rotating the key, or using a token for a disabled user. Protected endpoints must not authenticate with a bad cookie. With MockMvc, build a fresh request **carrying only the fake cookie** and no `HttpSession`; distinguish the filter clearing an invalid cookie from the final HTTP status (web form login usually redirects to `/login`, while APIs may return 401).

Other crucial tests:
- Remember-me cookie has `HttpOnly`/`Secure` per settings/environment; note `Secure` depends on HTTPS requests and cookie options.
- Cookie path/domain are scoped tightly to avoid unnecessary exposure.
- Because `remember-me` is auto-sent by browsers, unsafe actions still need CSRF protection when using cookie auth.
- Sensitive endpoints requiring `fullyAuthenticated()`/recent authentication may reject remember-me while accepting interactive login. Test per policy rather than assuming a remembered user holds every privilege of a freshly logged-in session.

### 10.3. Why Checking Cookie Deletion Is Not Enough

Consider **token-based remember-me**:

```text
Alice's browser has cookie C
Attacker copied C before Alice logged out
Alice POST /logout:
   -> server invalidates HttpSession
   -> returns Set-Cookie clearing remember-me in Alice's browser
Attacker still holds copy C
   -> if C has not expired and still verifies: it may still be valid
```

Thus `logoutRequiresCsrfAndClearsCurrentSession` above proves **browser/session state**, not server-side revocation of a copied token. If business requirements demand **logout must revoke remember-me immediately**, use a persistent token store/revocation design and write database integration tests: the token series is deleted, old cookie C can no longer log in, and other browsers/devices are handled per policy scope.

**Do not "fix" this by logging raw tokens** or storing remember-me cookies like plaintext passwords. Review lifecycle, TTL, rotation, theft detection, and require reauthentication on critical actions.

## 11. Logout All Devices: A Separate Feature Requiring Separate Tests

Default logout applies mainly to the **current session**. If the product offers a "Log out of all devices" button:

1. Strongly verify the user, considering recent reauthentication.
2. Query all sessions for the principal in the distributed registry or session store.
3. Invalidate/expire every session properly; ensure nodes enforce consistently.
4. Revoke persistent remember-me tokens for the user or per device per policy.
5. If the app holds separate OAuth2 refresh/access tokens, invoke the Authorization Server's revocation/token management protocol; never use `session.invalidate()` to claim OAuth tokens were revoked.
6. Test from **at least two independent cookie jars**, confirming both A and B lose authentication.
7. Ensure auditing: who requested logout-all, when, and execution outcome, without leaking tokens/cookies.

Logout-all may be asynchronous. If results across nodes are eventually consistent, specify that eventual consistency and ensure users are not falsely told all credentials are immediately dead.

## 12. How Does MockMvc Differ from a Real Browser/Container?

MockMvc is extremely helpful for the security filter chain, yet has limits:

| Goal | Verifiable in MockMvc | Requires container/browser tests |
| --- | --- | --- |
| Filter chain accepts `POST /login`, CSRF | Yes | Helpful extra check for cookie/path and UX |
| Session ID rotates on login | Yes via `MockHttpSession` | Yes, to prove old ID cannot be replayed |
| `ConcurrentSessionFilter` handles expired | Yes with registry in test context | Needed for multi-node/shared sessions |
| `HttpSessionEventPublisher` receives timeout events | Hard to simulate full timeout lifecycle | Yes, with real session expiration/store |
| Remember-me cookie issued and read | Yes, inject cookie into MockMvc request | Yes, to check domain/path/SameSite/Secure and browser persistence |
| Server-side revocation of persistent remember-me | Yes with real repository integration | Valuable for races/replication and real cookie jars |
| POST logout missing CSRF | Yes | Yes when integrating frontend |
| Actual browser deletion of `JSESSIONID`/remember-me cookie | Checks only `Set-Cookie` headers/response cookies | Yes, requires exact domain/path |
| Old session ID no longer authenticated | MockMvc does not simulate full container cookie lookup | Yes |
| Logout-all behind a load balancer | Insufficient with a single mock JVM | Mandatory multi-node/session-store tests |

For end-to-end tests, use an HTTPS test environment where possible, two HTTP clients/cookie jars, and keep full exchanges as **redacted** logs. Never put raw passwords, remember-me tokens, or `JSESSIONID` into public CI artifacts.

### 12.1. Illustrative cURL Without Leaking Secrets

```bash
# GET login page to obtain the form and CSRF token.
curl -i -c jar-a.txt http://localhost:8080/login

# Sending POST login needs a valid CSRF token taken from the form/cookie
# per the actual CsrfTokenRepository; the syntax below is only a skeleton:
curl -i -b jar-a.txt -c jar-a.txt \
  -X POST http://localhost:8080/login \
  --data-urlencode 'username=alice' \
  --data-urlencode 'password=test-password' \
  --data-urlencode '_csrf=TOKEN_FROM_FORM'

# Read protected endpoint using cookie jar A.
curl -i -b jar-a.txt http://localhost:8080/private
```

**Do not run the skeleton with a fake CSRF token and conclude login failed.** You must extract the session's real `_csrf`, protect cookie jar files, use test credentials, and delete jars when finished. Avoid putting secrets into shell history; for automation, use a secret manager and artifact redaction.

## 13. QA Matrix: Organizing the Test Suite to Avoid False Positives

### 13.1. Split Test Classes or Contexts by Configuration

Session concurrency `expire-old` and `prevent-new` are **two mutually exclusive policies**, not two states active simultaneously in the same bean in one test. Use separate test profiles/configs so each class has clear expectations.

Similarly, token-based and persistent-token remember-me should have separate test classes/fixtures, with DB tests for persistent mode. If sharing a context with multiple `SecurityFilterChain` or `SessionRegistry` beans, select the right chain and registry.

### 13.2. Minimum CI Test Case Set

| ID | Test | PASS condition |
| --- | --- | --- |
| SF-01 | Session ID rotated on successful login | Before ID != after ID, auth valid |
| SF-02 | Failed login does not elevate `Authentication` | Protected requests remain unusable after failed login |
| SF-03 | Replay pre-login ID against real container | Old cookie jar is not authenticated |
| CC-01 | User logs into two sessions under expire-old | A expired, B works |
| CC-02 | Prevent-new | B denied, A works |
| CC-03 | Session A times out / logs out | Registry frees slot properly |
| CC-04 | Two independent users | Session quotas do not bleed across users |
| RM-01 | Opt-in remember-me | `Set-Cookie` present |
| RM-02 | No opt-in | No new cookie issued |
| RM-03 | No session + valid remember-me cookie | Remembered auth established |
| RM-04 | Tampered/expired cookie | Not authenticated |
| RM-05 | Persistent-token logout | Series revoked; stolen cookie C invalid |
| LO-01 | POST logout with CSRF | Session invalidated + cookie cleared |
| LO-02 | POST logout missing CSRF | Request blocked, not logged out |
| LO-03 | No session/cookie after logout | Cannot access protected resources |
| LO-04 | Logout-all with two browsers | Both sessions invalidated per policy |
| LO-05 | OAuth tokens if present | Revocation tested separately |

### 13.3. Test Isolation

- Each test case uses **independent** sessions and cookies; never reuse another test's `MockHttpSession`.
- Never assume test execution order from method names.
- If `SessionRegistryImpl` is a singleton in the test context, clean state or use an isolated `ApplicationContext`; `@DirtiesContext` illustrates this.
- For concurrent tests, simulate **two real sessions**, not two tabs sharing one cookie.
- Never use `@WithMockUser` in place of login when testing **session fixation** or **remember-me issuance**. `@WithMockUser` bypasses credential checks and the login filter.
- When testing remember-me, never accidentally send the logged-in session too; otherwise a successful response does not prove the remember-me cookie was used.
- For logout, verify both cookie deletion and session invalidation, and test "copied cookie still valid" separately depending on implementation.
- Check route CSRF rules; disabling CSRF globally just to make tests easier strips away real behavior.
- Evaluate status codes according to web flows (302 form-login redirect) vs APIs (401/403), rather than forcing one status across every architecture.

## 14. Common Mistakes

1. **Asserting only 302 after login:** misses whether session ID changed, auth is valid, or remember-me was issued.
2. **Using the same session across two tabs to test concurrency:** fails to create two independent sessions.
3. **Forgetting `HttpSessionEventPublisher`:** the registry may never decrement session counts on timeout/destroy.
4. **Relying on in-memory `SessionRegistry` across multiple nodes:** each node only knows a fraction of sessions.
5. **Thinking `maxSessionsPreventsLogin(false)` makes the second login fail:** in fact, expire-old allows the new session and expires the old one.
6. **Testing only the second login without calling the old session:** fails to verify `ConcurrentSessionFilter` handles expiration.
7. **Sending `JSESSIONID` in a remember-me test:** may be authenticating via session rather than remember-me.
8. **Equating deleting the remember-me cookie with revoking the token:** especially false for copied token-based cookies.
9. **Using `GET /logout` as the logout action when CSRF is enabled:** may only render the confirmation page.
10. **Disabling CSRF for the suite:** tests no longer reflect real web/form logout.
11. **Using `@WithMockUser` to prove session fixation protection:** skips the real login authentication strategy.
12. **Assuming logout terminates every device:** default is current session only, unless logout-all is implemented.
13. **Forgetting session fixation on OAuth2/SAML/custom logins:** those flows need dedicated checks.
14. **Skipping account-lock/reauth checks with remember-me:** remembered auth may be too weak for payments/password changes.
15. **Logging full `Set-Cookie`, `JSESSIONID`, or remember-me values:** turns test logs into a credential theft source.

## 15. Acceptance Checklist

- [ ] Successful login on an existing session rotates the ID per the chosen strategy.
- [ ] Old session ID cannot be replayed against a real container, not only on a `MockHttpSession` object.
- [ ] Failed login creates no authenticated session and issues no new remember-me cookie.
- [ ] Concurrency policy is verified: expire-old **or** prevent-new; both A and B tested.
- [ ] `SessionRegistry` and session lifecycle events / cluster deployment work properly.
- [ ] Remember-me opt-in actually issues a cookie; a no-session request with the new cookie proves auto-login.
- [ ] Bad/expired cookies are rejected; remembered auth cannot pass steps requiring `fullyAuthenticated` if policy mandates.
- [ ] Logout runs via POST + CSRF; missing CSRF does not log out.
- [ ] Logout invalidates the current session and clears cookies with matching path/domain; follow-up requests are no longer authenticated via session.
- [ ] Token-based vs persistent-token remember-me revocation are clearly distinguished; cookie deletion is never called revocation.
- [ ] Logout-all has independent tests if provided by the product; OAuth token revocation is handled separately.
- [ ] HTTP integration tests cover browsers/cookie jars/HTTPS and multi-node if required by architecture.
- [ ] Test suites never write raw session/remember-me secrets into logs.

**Summary:** Session-based security testing in Spring Security Servlet must traverse **the real HTTP flow**, checking session ID rotation at login, behavior across multiple sessions, remember-me **independent of the old session**, and logout actually destroying/clearing the right state. MockMvc verifies filter-chain logic; browser/container tests prove cookies, session lookup, and real replay scenarios. With remember-me, always distinguish **clearing a client cookie** from **revoking a server-side credential**.
