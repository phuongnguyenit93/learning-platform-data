# Testing Post-Logout Requests and Active Sessions in Spring Security Servlet

> **Topic:** Spring Security - servlet. **Group:** Logout. Examples use Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC, and Spring Security Test.

## 1. After Logout, What Exactly Needs to Be Tested?

A user clicks **Log out**. The browser receives HTTP 302 back to the login page. Can we conclude logout is complete?

**Not yet.** A redirect only indicates that the logout endpoint produced a response. You must verify state **on the server**, **subsequent requests**, and whether **other sessions/tokens** still retain access.

There are at least three distinct questions:

1. **Current session:** did the logout request actually destroy the current `HttpSession`, clear `SecurityContext`, and stop treating the old session cookie as proof of authentication?
2. **Next request:** if a client tries reopening a protected URL after logout, does the server return the expected response (e.g., redirect to `/login` or HTTP 401) rather than continuing to serve the previous principal's data?
3. **Other sessions:** if the same account is logged in on browser B, machine C, or another device, does logging out from A **intentionally** keep or revoke those sessions? If the product promises “Log out of all devices,” are there mechanisms and tests proving full revocation?

This lesson distinguishes:

- **Current-session logout:** acts locally on the context/session of the request performing logout.
- **All-sessions logout:** requires managing the same account's other sessions, usually beyond the default scope of a single `/logout` request.
- **Remember-me / refresh token / JWT revocation:** credential lifecycles differ from `JSESSIONID` and are not completed merely by deleting the session.
- **Controller/Servlet filter testing** with `MockMvc` vs. **real browser/HTTP testing** with cookie jars and session stores.
- **Seeing an old page via the Back button** vs. **the server still serving data after logout** are two different phenomena.

**Principle:** a good test must prove **post-logout security state**, not merely check for `302 Found`.

## 2. Where Does Logout Sit in the Servlet Security Filter Chain?

In Spring Security Servlet, requests pass through `FilterChainProxy` and a matcher-selected `SecurityFilterChain`. With session-based form login, `LogoutFilter` handles requests matching the logout URL before they reach MVC controllers. It uses a chain of `LogoutHandler`s and a `LogoutSuccessHandler` to perform distinct tasks.

```text
Browser                         Spring Security Servlet
   | POST /logout
   | session cookie + valid CSRF token
   +------------------------------------>
                                    CsrfFilter
                                      |
                           LogoutFilter (matching matcher)
                                      |
                         SecurityContextLogoutHandler
                           - clear SecurityContext
                           - invalidate HttpSession
                             if configured
                                      |
                         Other LogoutHandlers (if any)
                           - RememberMeServices
                           - app-specific cleanup
                                      |
                         LogoutSuccessHandler
                           - redirect /login?logout
                             or custom response
                                      |
   <----------------------------------+
   | 302 Location: /login?logout
   |
   | GET /account, no valid session
   +------------------------------------>
                          Authorization on /account
                                      |
                          AuthenticationEntryPoint
                                      |
   <----------------------------------+
   | 302 Location: /login (web form)
```

The diagram illustrates core logic; exact ordering of logout handlers, repositories, and filters depends on config/version. **CSRF validation can block `POST /logout` before `LogoutFilter` runs.**

Points to understand:

- `LogoutFilter` matches requests via the configured `logoutRequestMatcher`/URL.
- `SecurityContextLogoutHandler` typically clears `Authentication` in the context and invalidates the HTTP session per config. With standard logout DSL, `invalidateHttpSession(true)` and `clearAuthentication(true)` are key options.
- `LogoutSuccessHandler` only creates the **HTTP result** after cleanup. A successful 302 does not prove the server erased all sessions on all devices.
- With CSRF enabled, Spring Security typically requires **POST** (or the configured method) to execute logout; `GET /logout` may show a confirmation page instead of actually logging out.
- `SecurityContextRepository` and session management govern how authentication is saved/restored across requests.

## 3. Result Matrix Needed Before Writing Tests

Assume:

- `GET /account` is only for authenticated users.
- `POST /logout` performs logout with CSRF.
- User `learner` is logged in on session A.
- An independent session B (either the same user or a different user) is also logged in.

| Scenario | Expected result | What to observe |
| --- | --- | --- |
| A calls `GET /account` before logout | HTTP 200 | A still has authentication |
| A calls `POST /logout` with valid CSRF | 302 to login/logout result page | Logout request matched filter and handlers ran |
| A after logout calls `GET /account` **without auth session** | Redirect to login or HTTP 401 per chain | No protected content leaked |
| Browser tries resending old session A cookie | Server does not restore destroyed authentication | Old cookie no longer represents a valid session |
| B calls `GET /account` after A logs out | HTTP 200 **if policy only logs out A** | Other sessions are not accidentally destroyed |
| B after “logout all devices” | No longer considered authenticated past revoke SLA | Global revocation mechanism actually works |
| `POST /logout` missing CSRF | Typically HTTP 403 | Session A was not logged out by that request |
| `GET /logout` with default CSRF | Does not destroy session if only a confirmation page | GET causes no unintended state mutation |
| Pressing Back after logout | May see cached UI; server must not issue fresh protected data | Check network/reload and cache policy |
| Remember-me cookie still present | May restore auth if unrevoked | Must test remember-me separately |
| JWT issued before logout | May remain valid if unrevoked/unexpired | Do not treat session deletion as JWT revocation |

**Picking one policy** for session B is not enough: document the exact product scope (“log out on this device” vs. “all devices”) and design tests matching that promise.

## 4. `Authentication`, `SecurityContext`, `HttpSession`, and Browser Cookies Are Not One Object

Understanding these four layers prevents flawed tests:

| Layer | Where is it held? | What does normal logout affect? |
| --- | --- | --- |
| `Authentication` | Inside `SecurityContext` | `clearAuthentication` clears context identity |
| `SecurityContext` | Per request and `SecurityContextRepository` | Cleared/removed per logout handling |
| `HttpSession` | Servlet container or shared session store | `invalidateHttpSession` destroys current session |
| `JSESSIONID` cookie | Client browser | May be cleared via `Set-Cookie`, yet **destroying the server session is decisive** |
| Remember-me cookie | Browser; optionally matched against server token store | Logout services must handle separately |
| Access/refresh tokens | Browser/mobile/SDK, token store, or issuer | Local logout does not automatically revoke all tokens |

A session cookie may still sit in browser storage, or a client may deliberately send an old ID, yet the server **must not** treat it as a valid session once invalidated. Conversely, deleting the browser cookie without invalidating the server session may fail to stop someone who copied the session ID from continuing to use it.

**Do not test by seeing `Set-Cookie: JSESSIONID=...; Max-Age=0` and concluding server-side revocation is complete.** Cookie deletion helps, yet does not replace checking the server-side session.

## 5. Default Logout Differs from Logout-All

When a browser calls `POST /logout` under standard form-login configuration, Spring Security focuses on the **current security context/session**. It does not scan every active `HttpSession` for the same username across all JVMs and invalidate them.

Example:

```text
t0: learner logs in on Chrome -> session A
t1: learner logs in on Firefox -> session B
t2: Chrome sends POST /logout with session A + valid CSRF
t3: session A is invalidated
t4: Firefox holds session B -> can still view /account
```

This is usually the **right behavior** for a per-session “Log out” button. If the UI says “Log out of all devices,” a different capability is needed: tracking sessions per account, flagging/expiring/invalidating related sessions via an appropriate store/registry, revoking remember-me and refresh tokens, and defining how still-unexpired JWTs are handled.

Spring Security offers supporting mechanisms such as `SessionRegistry`, concurrent session control, `SessionInformation.expireNow()`, Spring Session, and centralized session stores. However, **`expireNow()` primarily marks a session for the corresponding mechanism to detect**, rather than immediately deleting every server-side session across all nodes. With distributed session storage, you need a revocation policy and tests tailored to your deployment architecture.

### Do Not Confuse Concurrent Sessions with Forced Global Logout

`.maximumSessions(1)` is a policy limiting concurrent sessions (and handling old/new sessions) via a session registry. It **does not** mean there is a built-in `logoutAllDevices()` API automatically handling every credential type. The registry must genuinely track sessions, events/session stores must work properly, and subsequent requests must pass through expiration-handling mechanisms.

## 6. Complete Example: Spring Boot 3.x and Spring Security 6.x

We create a small Servlet app using form login, sessions, and `/account`. Two users `learner` and `reviewer` allow testing two independent sessions. The example keeps **CSRF enabled** and uses the default logout pipeline to clearly show the difference between the logout request and subsequent requests.

### 6.1. Gradle Dependencies

In a Spring Boot 3.x project with the appropriate Gradle plugin and dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### 6.2. File `src/main/java/example/logouttests/LogoutTestsApplication.java`

```java
package example.logouttests;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LogoutTestsApplication {
    public static void main(String[] args) {
        SpringApplication.run(LogoutTestsApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/account").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form.permitAll())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
            )
            // CSRF protection remains enabled by default.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("learner-pass"))
            .roles("USER")
            .build();

        UserDetails reviewer = User.withUsername("reviewer")
            .password(encoder.encode("reviewer-pass"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(learner, reviewer);
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicPage() {
        return "Public";
    }

    @GetMapping("/account")
    String account(Authentication authentication) {
        return "Hello " + authentication.getName();
    }
}
```

Only `LogoutTestsApplication` is a public top-level class; the remaining classes are package-private, making this single Java 17 file valid. `@SpringBootApplication` scans package `example.logouttests` and picks up both the security config and MVC controller.

**Key points in the code:**

- `.formLogin(form -> form.permitAll())` enables Servlet form login; `POST /login` is handled by the authentication filter with no separate controller needed.
- `.logout(...)` configures the logout URL and outcome. `invalidateHttpSession(true)` destroys the current session; `clearAuthentication(true)` clears authentication from the security context.
- `logoutSuccessUrl("/login?logout")` only drives UI navigation. Tests must still verify session invalidation and subsequent requests.
- CSRF remains default: POST logout requires a valid CSRF token. `GET /logout` may serve a confirmation page in standard configs, not a way to trigger logout side effects.
- `anyRequest().denyAll()` exposes no routes beyond demo needs; URLs needed by `formLogin`/logout are processed by security configuration ahead of MVC authorization as appropriate.
- Passwords are encoded before adding to `InMemoryUserDetailsManager`. Accounts/passwords are for local demos only; production requires a real identity store and HTTPS.

### 6.3. Running the Application

If the project has a Gradle wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell uses `./gradlew.bat bootRun`. Once the server starts locally, open `http://localhost:8080/account` and log in with `learner` / `learner-pass`. Expected result:

```text
Hello learner
```

Click logout via a form POST with a valid CSRF token; then reopen `/account`. Expect the browser to be redirected to the login page rather than continuing to receive `Hello learner` from the server.

This is **expected behavior of the configuration**, not captured output from a live run. Browser URLs, `Location` responses, and cookie flags may vary with context paths, reverse proxies, HTTPS, and session stores.

## 7. Writing Proper Integration Tests: Using `MockMvc` and `MockHttpSession`

`MockMvc` is well suited for testing the Servlet filter chain without opening a real HTTP port. In Spring Security Test:

- `.with(csrf())` generates/attaches a valid CSRF token for POST tests.
- `.session(session)` attaches a specific `MockHttpSession` to a request, letting you test an authenticated session across calls.
- `MockHttpSession.isInvalid()` indicates whether the mock session was destroyed via `invalidate()`.
- `MockMvcResultMatchers` asserts status/body/`Location`.
- `MockMvc` **does not fully simulate a browser cookie jar or looking up an old session ID from a request cookie**; HTTP/browser integration tests are needed for that question.

### 7.1. Create File `src/test/java/example/logouttests/LogoutFlowTest.java`

```java
package example.logouttests;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LogoutFlowTest {

    @Autowired
    MockMvc mvc;

    private MockHttpSession login(String username, String password)
            throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", username)
                .param("password", password))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);

        assertNotNull(session, "Form login should have a session");
        assertFalse(session.isInvalid());
        return session;
    }

    @Test
    void logoutInvalidatesCurrentSessionAndNextAnonymousRequestIsBlocked()
            throws Exception {

        MockHttpSession session = login("learner", "learner-pass");

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello learner"));

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login?logout")));

        // Verify server-side invalidation, not just HTTP redirect.
        assertTrue(session.isInvalid());

        // After logout, a fresh request has no authenticated session.
        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login")));
    }

    @Test
    void anotherActiveSessionIsNotInvalidatedByLocalLogout()
            throws Exception {

        MockHttpSession sessionA =
            login("learner", "learner-pass");

        MockHttpSession sessionB =
            login("reviewer", "reviewer-pass");

        mvc.perform(get("/account").session(sessionA))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello learner"));

        mvc.perform(get("/account").session(sessionB))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello reviewer"));

        mvc.perform(post("/logout")
                .session(sessionA)
                .with(csrf()))
            .andExpect(status().is3xxRedirection());

        assertTrue(sessionA.isInvalid());
        assertFalse(sessionB.isInvalid());

        // Local logout of A does not revoke session B.
        mvc.perform(get("/account").session(sessionB))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello reviewer"));
    }

    @Test
    void logoutWithoutCsrfIsRejectedAndSessionRemainsAuthenticated()
            throws Exception {

        MockHttpSession session = login("learner", "learner-pass");

        mvc.perform(post("/logout").session(session))
            .andExpect(status().isForbidden());

        assertFalse(session.isInvalid());

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello learner"));
    }

    @Test
    void anonymousAccessBeforeLoginRequiresAuthentication()
            throws Exception {
        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login")));
    }

    @Test
    void publicPageIsAccessibleAfterLogout()
            throws Exception {
        MockHttpSession session = login("learner", "learner-pass");

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection());

        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("Public"));
    }
}
```

Run with Gradle:

```bash
./gradlew test
```

**Verification level:** the results above are **expected assertions for the sample application**; no compile or test run was executed while authoring this document. `MockMvc` exercises the filter chain in a mock Servlet environment; to prove a browser sending an old cookie ID is rejected, perform additional verification against a real HTTP server/session store.

### 7.2. Why Doesn't the Test Re-Attach an Invalidated `MockHttpSession`?

After `session.invalidate()`, the `MockHttpSession` object is marked invalid. Attempting to call:

```java
// Do not use this test pattern as proof of a browser holding an old cookie:
mvc.perform(get("/account").session(invalidatedSession));
```

can fail in the mock model or conflate concepts: an already-invalidated Java session object **differs** from an HTTP request carrying an old `JSESSIONID` cookie. In a real browser, the client simply sends a cookie string; the Servlet container or session store must recognize that the session ID has expired and either create a new anonymous session or none at all per policy.

Proper testing splits into two layers:

1. **`MockMvc`**: proves `MockHttpSession.isInvalid()==true` and that a new unauthenticated request is denied access.
2. **HTTP integration**: saves the old raw session cookie, sends it on a post-logout request, and verifies the server does not restore the logged-out user.

Avoid claiming a sessionless `MockMvc` test by itself proves “a stolen `JSESSIONID` was revoked.” It is only one link in the chain of evidence.

## 8. Independently Testing Multiple Sessions of the **Same Account**

Testing session A = `learner` and session B = `reviewer` proves isolation between two different users' sessions. Yet a common requirement is **the same account logged in on multiple devices**. Add an explicit test for that case.

Add the test below into the `LogoutFlowTest` class above:

```java
@Test
void logoutOfOneOfTwoSessionsForSameUserKeepsOtherSession()
        throws Exception {

    MockHttpSession chrome =
        login("learner", "learner-pass");

    MockHttpSession firefox =
        login("learner", "learner-pass");

    mvc.perform(get("/account").session(chrome))
        .andExpect(status().isOk())
        .andExpect(content().string("Hello learner"));

    mvc.perform(get("/account").session(firefox))
        .andExpect(status().isOk())
        .andExpect(content().string("Hello learner"));

    mvc.perform(post("/logout").session(chrome).with(csrf()))
        .andExpect(status().is3xxRedirection());

    assertTrue(chrome.isInvalid());
    assertFalse(firefox.isInvalid());

    mvc.perform(get("/account").session(firefox))
        .andExpect(status().isOk())
        .andExpect(content().string("Hello learner"));
}
```

The snippet above is an **additional method** using `login`, `mvc`, and static imports from the test class above, not a standalone file. With no concurrency limit configured in the demo, two sessions for the same user can coexist.

When product policy changes to “one session per user” or “log out all devices,” **test expectations must change**. Do not treat session B staying alive as a bug if A's logout is defined as local logout.

### Watch Out for Distinct Session Identifiers

When testing independent sessions, never reuse the same `MockHttpSession` to log in twice, because that represents **one client context**. Two HTTP sessions must originate from two separate login requests sharing no session, or two independent browser contexts/cookie jars. In real deployments, use two browser profiles or two cookie jars so a new session cookie does not overwrite the old one.

## 9. Testing Old Cookies Against a Real HTTP Server

To answer “Will a client resending a pre-logout `JSESSIONID` be accepted?”, run an end-to-end test against a real Servlet container/HTTP session store.

Recommended sequence:

```text
1. Client A (cookie jar A) GET /account -> receives 302 to /login.
2. Client A GET /login -> receives HTML form and CSRF token.
3. Client A POST /login with username/password + valid CSRF token.
4. Save a copy of Cookie: JSESSIONID=<old-value> from cookie jar A.
5. Client A GET /account -> HTTP 200, expected principal.
6. Client A POST /logout with valid CSRF token.
7. Using a separate client (never reusing the active authenticated session)
   try sending Cookie: JSESSIONID=<old-value> in GET /account.
8. Expect no protected data returned:
   form login normally redirects to /login;
   REST APIs may return HTTP 401.
9. Client B with previously logged-in cookie jar B is checked per
   “local logout” or “logout all sessions” policy.
```

This is a **test scenario**, not a complete shell script: the client must fetch/preserve the right CSRF token, session cookie, redirects, and proxy context. Never run `curl -X POST /logout` missing a CSRF token and conclude logout succeeded.

### Can `curl` Be Used?

Yes, provided you manage cookie jars and CSRF tokens in the exact format expected by the app. If you only run:

```bash
curl -i -X POST http://localhost:8080/logout
```

with CSRF protection active, the request is typically blocked (403). That does **not** prove the session was invalidated. In automated HTTP tests, you can use `TestRestTemplate`, `WebTestClient` against a running server, or a Java HTTP client, provided the full token/cookie lifecycle is honored. In real browsers, DevTools Network shows status/`Location`, though raw session IDs should never be logged or shared.

### Observing Old Cookie IDs Through an API Gateway or Reverse Proxy

If the system runs behind a gateway or multiple service nodes, test requests carrying old cookies through the **exact public URL and shared session backend**. A passing check on node A does not prove node B knows the session was destroyed if local session stores or delayed replication are used.

## 10. Post-Logout State in a Multi-Node System

Consider servers behind a load balancer:

```text
Browser A + JSESSIONID=S1
           |
     Load balancer
       /       \
      v         v
   Node A     Node B
     |           |
     +------ shared Spring Session store (e.g., Redis)
                 |
             Session S1
```

When `POST` logout hits node A, if session state lives in a shared store and invalidation executes consistently, node B must not keep restoring authentication from S1 on subsequent requests. With unshared local `HttpSession`, sticky sessions and node failover can behave differently; testing only against node A can miss consistency flaws.

For Spring Session (e.g., Redis-backed sessions), design tests to:

- Create a session on node A, then access a protected URL via node B (per test routing).
- Log out on node A.
- Resend the old session cookie through node B after logout.
- Verify the backend does not return an authenticated principal.
- Test races between in-flight protected requests and logout; define the point by which revocation policy is guaranteed.
- Measure how long session invalidation takes to propagate across all nodes and session stores.

**Never claim “logout takes effect instantaneously cluster-wide” if the system uses asynchronous session caches.** Define SLAs and test through the public load-balancer path.

## 11. `SessionRegistry`, Concurrent Sessions, and “Logout All Devices”

A system managing multiple sessions must maintain a **mapping from user → active sessions**. Spring Security provides `SessionRegistry` and session-concurrency support, though locating/expiring sessions depends on session tracking configuration.

Conceptually:

```java
// Pseudocode: requires SessionRegistry actively tracking sessions.
for (SessionInformation session :
        sessionRegistry.getAllSessions(principal, false)) {
    session.expireNow();
}
```

This is an **illustrative fragment**, needing imports for `SessionRegistry`, `SessionInformation`, matching principals, and the right tracking strategy. It is **not** a complete logout-all implementation.

Understand that `expireNow()` in concurrent session control typically marks the session as expired; it may be detected and enforced when the next request passes through `ConcurrentSessionFilter` or an equivalent mechanism. That **differs from** immediately deleting every key from a distributed session store. For instant cross-node revocation, you may need to delete sessions directly in the session repository or use a request-time security-version check, depending on Spring Session and architecture.

### Logging Out All Devices Also Involves Other Tokens

If browser B also holds a valid `remember-me` cookie, destroying session B alone may let the remember-me filter **recreate authentication** on the next request. Logout-all must cover remember-me token revocation (appropriate persistent token repository, key/version strategy for token-based) and distinguish single-device logout from all-devices logout.

If mobile app C holds a 15-minute JWT access token, a session registry on the Servlet web chain **does not invalidate that JWT**. You need access-token expiry policies, refresh-token revocation, introspection, `jti` denylists, or token/account version checks. An SSO/OIDC IdP also has its own lifecycle: local logout does not guarantee IdP single logout.

## 12. Remember-Me Can Cause “Logged Back In After Logout”

A common product bug is deleting the HTTP session **without revoking the remember-me cookie**. Users think they logged out, then `GET /account` without session authentication passes through `RememberMeAuthenticationFilter`, the remember-me cookie validates, and the user is authenticated again.

Therefore, when remember-me is enabled, add tests:

| Request / condition | Expectation |
| --- | --- |
| Login with remember-me checkbox selected | Server issues a valid remember-me cookie |
| Session lost while cookie stays valid | App can restore remember-me per policy |
| Successful `POST` logout | Clears remember-me cookie in browser and revokes server token per implementation/policy |
| Browser resends **old cookie copy** after logout | Expectation depends on token-based vs. persistent strategy; test against exact threat model |
| Account locked or password changed | Old cookies are rejected per validity-window requirements |
| Logout-all | No active sessions or remember-me/refresh tokens remain usable outside policy |

With **token-based remember-me**, deleting the browser cookie does not destroy a stolen copy; a validly signed cookie can continue working until expiry or until key/signature inputs change. With **persistent tokens**, the repository supports revocation, though you must verify the actual logout policy and concurrency handling.

Do not write `assertNull(response.getCookie("remember-me"))` after logout assuming the token was revoked: the response may carry a cookie with an empty value and `Max-Age=0` to delete it; inspect `Set-Cookie` attributes and server-side revocation instead.

## 13. Deleting Cookies Does Not Equal Destroying the Session

Sometimes developers add to logout config:

```java
.logout(logout -> logout
    .deleteCookies("JSESSIONID")
)
```

This is a **DSL fragment**, requiring appropriate classes/config. It can send `Set-Cookie` telling the browser to drop the session cookie, yet effectiveness depends on cookie `Path`/`Domain`/`Secure` and reverse proxies. In most cases, default session invalidation is the critical foundation; `deleteCookies` is an extra layer tuning browser cookie UX or hygiene.

For strong tests, verify:

1. `HttpSession` is invalidated on the server.
2. Fresh requests cannot restore the old `Authentication`.
3. If required, the browser receives cookie deletion matching `Path` and `Domain`.
4. Copies of the old session cookie are rejected by the server.
5. Other sessions stay valid or become invalid per policy.

Avoid two kinds of “false green”:

- Tests checking only `Set-Cookie` cookie deletion while the server still keeps the session.
- Tests checking only that the browser lacks a cookie without ever resending the old session ID to confirm server-side invalidation.

## 14. CSRF: Never Skip It in Logout Tests

One of the most common mistakes when writing tests:

```java
mvc.perform(post("/logout").session(session))
    .andExpect(status().is3xxRedirection());
```

When CSRF protects POSTs, this request may return **403** instead of redirecting. That is not a logout handler bug. Spring Security Test supplies a CSRF token:

```java
mvc.perform(post("/logout")
        .session(session)
        .with(csrf()))
    .andExpect(status().is3xxRedirection());
```

This is a fragment assuming `MockMvc mvc` and `MockHttpSession session` are already present, not a standalone test.

**Never disable CSRF just to get a 302.** For browsers carrying session or remember-me cookies automatically, CSRF mitigation remains vital. Never use GET as a side-effecting logout just to “avoid CSRF tokens”: cross-site navigation can trigger GET and cause forced user logouts.

A test rejecting a POST missing CSRF must also verify **the session was not invalidated**. Checking only `status().isForbidden()` without checking the session can miss a handler running too early.

## 15. Redirected to Login After Logout, Yet Frontend Still Shows Old Data

Browser Back/Forward Cache (bfcache), HTTP caches, SPA state, and service workers can retain DOM/data rendered before logout. Pressing Back may display an old page **with no new request to the server**. That differs from a post-logout GET to a protected resource actually being served by the server.

Verification method:

1. Log out and press Back to observe the UI.
2. Open DevTools Network to see whether an actual network request fired.
3. Force reload or navigate directly to a protected URL after logout.
4. Confirm the server returns a login redirect/401, not fresh private data.
5. Inspect `Cache-Control` response headers on sensitive resources; `no-store` may be needed for non-cacheable data.
6. In SPAs, clear client-side auth state/caches, reset query stores, and avoid rendering stale user data—without replacing server authorization.
7. With service workers, verify caching strategies so private authenticated responses are never cached unintentionally.

Spring Security normally sets appropriate security headers and cache-control defaults, yet **do not treat them as automatic proof that every CDN, reverse proxy, browser cache, and service worker obeys sensitive-data policies**. Real tests along your deployment path are required.

### Example Request That Must Be Tested

```http
GET /account HTTP/1.1
Host: app.example
Cookie: JSESSIONID=<old-session-id>
```

The post-logout expectation is that **the server rejects the old session ID as valid authentication**. The HTTP status may be 302 to login (form-based), 401 for an API entry point, or a custom designed response. Never rely on one fixed status alone if a frontend/proxy could return the login page with status 200.

## 16. Logout and Concurrent In-Flight Requests

Suppose a state-mutating request was authenticated at t0, the user logs out at t1, and the old request finishes at t2. Logging out at t1 **does not automatically roll back** an already-started transaction or abort every running thread.

```text
t0: POST /transfer enters server with session S
t1: Server checks authorization, starts transaction
t2: Browser sends POST /logout, session S is invalidated
t3: Transaction /transfer completes using already-checked data/locks
```

A requirement like “no actions occur after logout” must be defined precisely by **start time**, **authorization time**, **commit time**, and transaction type. For high-risk workflows, you may need a revocation/version check right before commit or policy-enforced transaction coordination, not just session invalidation.

Cases worth testing:

- Logout concurrent with a protected request on the same session.
- Logout on one node while a request executes on another node.
- Request arriving after session invalidation yet carrying the old cookie.
- Token revoked between request authentication and action commit.

Never claim a sequential `GET → logout → GET` test proves the system is free of race conditions.

## 17. HTTP Status Codes, Handlers, and Avoiding Misdiagnosis

| Outcome | Possible causes | What to check |
| --- | --- | --- |
| `POST` logout returns 302 | `LogoutSuccessHandler` redirect | Was the session actually invalidated? |
| `POST` logout returns 403 | Missing/invalid CSRF token, other authorization | CSRF/`LogoutFilter` matcher, is session still alive? |
| `GET /account` after logout returns 302 | `AuthenticationEntryPoint` restarts login | Is it the right `/login`? Any private data leaked? |
| `GET /account` after logout returns 401 | API/basic/bearer entry point challenges authentication | API contract, body, and headers |
| `GET /account` after logout still returns 200 | Another session/token remains valid, public endpoint, or cached response | Authentication type, cookies, remember-me, rules, proxy |
| `GET /account` returns 403 | Principal may be authenticated but lacks authority, or custom handler | Do not infer logout failed solely from status |
| `GET /logout` returns confirmation page | CSRF enabled, default logout confirmation | Does GET cause any side effects? |
| Node A rejects, node B accepts old cookie | Out-of-sync session store, stale cache | Shared store/invalidation |
| Session A lost, session B stays valid | Local logout per policy | Different mechanism needed for all-devices |
| Browser Back still shows content | bfcache/client state | Network reload and `Cache-Control` |

**Always document** client, method, URL, security chain, pre/post authentication type, **redacted** session IDs, status codes, and login entry-point behavior. Never emit raw cookies or tokens into logs or CI artifacts.

## 18. Regression Test Suite for Production Environments

An acceptance checklist by tier:

| Group | Test case | Pass criteria |
| --- | --- | --- |
| Happy path | Login form → `GET` protected → `POST` logout → `GET` protected | 200 before, no private data served after |
| Cleanup | Logout with valid CSRF | Current server session invalidated and context cleared |
| CSRF | Logout missing/wrong CSRF | 403, session stays usable if CSRF policy blocks |
| Method | `GET` logout | No automatic logout under CSRF-enabled default confirmation |
| Isolation | A logs out, another user's B stays logged in | B is unaffected |
| Same user | Same user's sessions A and B; only A logs out | B remains valid under local-logout policy |
| All devices | A triggers logout-all | A/B/C revoked within SLA |
| Replay | Reuse old `JSESSIONID` after logout | Does not restore old principal |
| Remember-me | Session destroyed while remember-me cookie remains | Per policy, does not create a post-logout bypass |
| Tokens | Issued JWT/refresh tokens | Revoked/expired per security contract |
| Cluster | Logout on node A, old-cookie request to node B | B does not restore destroyed auth |
| Proxy | HTTPS, cookie `Path`/`Domain`/`Secure` | Browser receives appropriate cookie cleanup |
| UI | Back/reload after logout | No fresh sensitive data served by server |
| Concurrency | Protected request running concurrently with logout | Behavior matches defined commit/revoke boundary |
| Audit | Logout events and revocation logs | No session IDs/tokens/passwords printed |
| Accessibility | Logout status UI | User understands which session was logged out |

Tests at the “all devices,” “cluster,” or “token revocation” tiers require **real environments and implementations**; the Boot/`MockMvc` example in this lesson proves local Servlet session behavior and does not automatically satisfy every row above.

## 19. Review Exercises with Answers

**Question 1.** Why is asserting only HTTP 302 on `POST /logout` insufficient?

**Answer:** 302 is the response built by the success handler. You must verify the session/context were erased and subsequent protected requests no longer carry the old identity.

**Question 2.** A user logs in on browsers A and B. A logs out. B can still access `/account`. Is this a bug?

**Answer:** No, if the feature is local logout. If the UI promises “log out all devices,” B remaining valid indicates the global revocation mechanism is incomplete.

**Question 3.** Why shouldn't you pass an invalidated `MockHttpSession` back into `MockMvc.perform(...session(...))` to simulate a stolen cookie?

**Answer:** `MockHttpSession` is an invalid server-side object; real browsers send only a cookie ID string. Test cookie replay against a real HTTP server/session store.

**Question 4.** `POST` logout missing CSRF returns 403. Should the session be invalidated?

**Answer:** With CSRF blocking ahead of `LogoutFilter`, the session should remain valid because logout never executed. Assert both status and session validity.

**Question 5.** Does deleting the `JSESSIONID` cookie with `deleteCookies` stop someone holding a copy of the old ID?

**Answer:** Not reliably. The server must invalidate the session or revoke it in the session store; cookie deletion alone is client-side hygiene.

**Question 6.** After logout, browser Back shows old content, whereas reloading the protected URL redirects to login. What does that prove?

**Answer:** The browser/client cache may hold a UI snapshot while the server already blocks new requests. Apply cache policies for sensitive data and clean client state rather than concluding the server session is alive solely from Back.

**Question 7.** Why can a remember-me cookie make a user appear “still logged in”?

**Answer:** If remember-me was not revoked, a request without an authenticated session can be restored by the remember-me filter. Logout must handle remember-me services/token policies explicitly.

**Question 8.** Does `SessionInformation.expireNow()` immediately delete all sessions from Redis or a database?

**Answer:** Do not assume so. In many setups it flags them expired for a filter to handle on the next request. Instant cluster revocation requires the corresponding session-store mechanism.

**Question 9.** A mobile app still holds an unexpired JWT after browser logout. Is that a bug in `SecurityContextLogoutHandler`?

**Answer:** No. Local Servlet session logout does not revoke JWTs/refresh tokens. If logout-all is required, add token revocation/expiry/version policies.

**Question 10.** A data-mutating request passed authorization before logout and commits after logout. Can this always be declared a vulnerability?

**Answer:** You cannot conclude solely from ordering. Define consistency/revocation policies for in-flight requests, using versioning/rechecks/transaction coordination if business rules require blocking before commit.

## 20. Logout Implementation and Testing Checklist

- [ ] Define the exact product meaning: **current-session logout** vs. **all-sessions/devices logout**.
- [ ] Verify `LogoutFilter` is in the right `SecurityFilterChain` and requests match method/path.
- [ ] For cookie/session form login, keep CSRF protection enabled and test both valid and missing-token POSTs.
- [ ] After `POST` logout, assert the session is invalidated and authentication is absent on subsequent requests.
- [ ] Test a client attempting to resend the old raw session cookie against a real HTTP server.
- [ ] Test another user's session B and the same user's session B per policy.
- [ ] If logout-all exists, test registry/session-store revocation across all nodes within the published SLA.
- [ ] Remember-me cookies/tokens are cleared or revoked appropriately; do not delete only `JSESSIONID`.
- [ ] Refresh tokens/JWTs/OIDC logout have dedicated policies; do not claim automatic invalidation.
- [ ] Never use `GET /logout` for state-changing actions out of convenience.
- [ ] Protected resources return redirects/401/403 per contract, **never private data**, after logout.
- [ ] Test browser Back, bfcache, SPA caches, service workers, and `Cache-Control`.
- [ ] Reverse proxies/shared session stores never retain revoked authentication.
- [ ] Add concurrent request/logout tests when strict revocation SLAs apply.
- [ ] Audit logs are sufficient for observability yet **never log raw cookies, session IDs, tokens, or passwords**.
- [ ] Test code uses `MockMvc` properly with `.with(csrf())` and independent `MockHttpSession` instances.
- [ ] Supplement `MockMvc` limitations with browser/HTTP integration tests.

## Conclusion

A trustworthy logout is never proven by **a single redirect**. In Spring Security Servlet, verify that `LogoutFilter` executes cleanup, the **current session** is invalidated, and **post-logout protected requests** no longer receive the old authentication. At the same time, other sessions must be preserved or revoked **according to the feature's exact definition**.

Use `MockMvc` to test the security filter chain, CSRF, `MockHttpSession.isInvalid()`, and session isolation. Use HTTP/browser integration tests to prove old cookie IDs are genuinely rejected by the server, alongside checking clusters, remember-me, and token revocation where applicable. **Distinguishing local logout, logout-all, and token revocation** is essential to avoid “green” test suites whose real-world behavior or security remains broken.
