# Testing Logout, Session Expiration, and Replay with Stale Credentials

## 1. The problem: what does "logged out" really mean?

A user logs into the application, views their account page, and clicks **Logout**. The UI redirects back to the login page and no longer displays their username. That **is not enough to prove the session was invalidated**. If the server still accepts the old session cookie, direct HTTP requests can continue accessing protected data.

Likewise, a session expired due to inactivity must be rejected when the user returns. You should not merely check that the browser showed a "Session expired" message. What must be verified is that **the server no longer accepts the old session identifier**.

This lesson belongs to the **Testing** topic of **Spring Security – fundamentals**. Primary examples use **Spring Security Servlet**, **Spring Boot 3.x / Spring Security 6.x**, and **Java 17+**, with form login and `HttpSession`. Later sections clearly contrast these outcomes with HTTP Basic, remember-me, OAuth/OIDC, bearer tokens, and JWTs, since each authentication mechanism has different revocation rules.

Five questions must be answered:

1. Can requests holding a valid session **before logout** access authorized resources?
2. Does `POST /logout` use the right HTTP method, CSRF token, and expected response?
3. After logout, does the server reject the **old cookie/session ID**, even if the client intentionally replays it?
4. After the **inactivity period** (idle timeout) elapses, is the old session ID rejected?
5. After obtaining a new session, does the new session work normally while the **old session remains invalid**?

Test both success and rejection cases. A test that only checks the login page appears after logout does not prove security.

## 2. Distinguishing logout, session expiration, and access revocation

| Scenario | What happens on the server | What must be tested |
| --- | --- | --- |
| **Explicit logout** | With `HttpSession` login, Spring Security normally invalidates the session, clears the security context, clears CSRF tokens, and cleans up integrated remember-me state. | A valid `POST /logout` succeeds; the pre-logout session cookie cannot access protected resources. |
| **Idle timeout** | The Servlet container or session repository marks the session invalid once inactivity exceeds the threshold. | After the configured duration, resending the old session ID must be rejected. |
| **Absolute lifetime** | A session lives at most a fixed window from issuance, even while the user is active, if the app enforces such a policy. | Past the absolute deadline, requests with the old session are rejected; this policy usually requires custom implementation. |
| **Session fixation protection** | Upon successful authentication, Spring Security normally changes the servlet session's ID. | The pre-login session ID does not become the authenticated session; post-login session ID differs when enabled. |
| **Re-authentication** | After a new login succeeds, the app issues fresh authentication state. | The new session is granted access; old logged-out/expired sessions remain rejected. |
| **Cookie lingering in browser** | Cookies are client-side data held by the browser; the server may have destroyed the backing session. | Even when replaying the old cookie manually via HTTP tools, the server rejects it. |
| **Log out all devices** | Requires tracking multiple sessions or tokens and revoking all of them per policy. | Every session/token in the revocation scope stops working; logging out one session does not automatically log out all. |
| **Bearer/JWT** | Issued tokens may continue to be accepted until expiry unless a revocation mechanism exists. | Test denylists/revocation/introspection, refresh-token rotation, and token lifetimes separately. |

**A key concept:** `JSESSIONID` is merely a server-side session **identifier**. Once the session is destroyed, having the browser keep the cookie or a user copying it into an HTTP tool **does not revive the session**. Therefore tests must attempt to **replay the old value**, rather than only checking the `Set-Cookie` deletion header.

## 3. Sequence of steps in a proper test scenario

Suppose there are three endpoints:

- `GET /api/public/csrf`: retrieves a CSRF token to submit login/logout forms in the example.
- `GET /api/private/me`: accessible only to authenticated callers.
- `POST /logout`: logs out via Spring Security; requires a CSRF token when CSRF is enabled.

A typical test flow:

```text
1. Client GET /api/public/csrf
   -> Server issues anonymous HttpSession and CSRF token
   -> Client saves pre-login JSESSIONID

2. Client POST /login with form + CSRF + cookie
   -> Server authenticates successfully
   -> Session ID rotates on login (common default configuration)
   -> Client saves post-login JSESSIONID

3. Client GET /api/private/me with post-login cookie
   -> 200 OK

4. Client fetches a NEW CSRF token for the authenticated session
   -> Pre-login token was cleared upon successful authentication

5. Client POST /logout with cookie + new CSRF token
   -> 204 No Content in the illustrative configuration

6. Client INTENTIONALLY reuses old JSESSIONID:
   GET /api/private/me
   -> 401 Unauthorized

7. Client logs in again to create a new session
   -> New cookie succeeds (200)
   -> Logged-out cookie is still rejected (401)
```

Never rely on the browser client automatically sending its latest cookie to conclude the old session is dead. For replay tests, **save a copy of the pre-logout cookie** and send that **exact old value** after logout.

### 3.1. Which outcomes are right?

- For a **JSON API** using a status-based entry point like the example below, unauthenticated requests return **401**.
- For a **default form-login web app**, the same situation may return a **302 redirect to the login page**. That is a different contract, not necessarily a bug.
- **403** is typically for authenticated callers lacking permission, or POSTs missing/sending an invalid CSRF token. Therefore do not lump every security failure into "403."
- After logout, if the client submits a **valid username/password to the login endpoint again**, the app can authenticate anew. Logout does not change passwords on its own.
- If a client continues sending **Authorization: Basic** on every request, the server can re-authenticate on every request. Session-cookie tests cannot be used to claim all authentication mechanisms were revoked.

## 4. Default logout behavior in Spring Security Servlet

When Spring Security Servlet logout is enabled with CSRF active:

- `GET /logout` normally renders the Spring Security-generated logout confirmation page; **GET does not directly invalidate the session**.
- `POST /logout` with a valid CSRF token triggers `LogoutFilter`.
- Default logout handlers clear `HttpSession`, `SecurityContextHolder`/repository, CSRF tokens, and remember-me state when configured.
- Afterward, browsers are redirected to `/login?logout` by default. The example below customizes **only the success response** to `204 No Content` to make API tests straightforward to observe.

Avoid calling `GET /logout` from JavaScript or `<a href>` expecting direct logout. Accepting GET to perform logout raises the risk of external sites triggering unwanted logouts. For forms/browsers, use `POST` with a CSRF token; for APIs, follow a logout contract matching the authentication mechanism.

### 4.1. What does logout affect?

In standard `HttpSession`-based login:

- The active session is invalidated via `HttpSession.invalidate()`.
- `SecurityContext` is cleared from the current context and repository along the configured logout path.
- Associated CSRF tokens are cleared; the client must obtain a new token when starting a new session.
- The session cookie may be requested to be deleted in the browser. Still, **the primary proof remains that the server rejects the old session**.
- If remember-me is enabled with proper `RememberMeServices`, logout also cleans up remember-me state.
- If the app uses WebSockets, OAuth2 client sessions, multiple subdomains, or tokens outside the session system, dedicated revocation is needed; servlet logout does not handle all of them automatically.

Never conflate **deleting a cookie** with **invalidating a session**. Deleting the cookie client-side stops the browser from sending it, yet an attacker who copied the session ID earlier can still use it if the server did not revoke it.

## 5. Test categories you must include

| Group | Test case | Goal |
| --- | --- | --- |
| Before login | Call private endpoint with no cookie | Blocked per contract (e.g., 401). |
| Successful login | Valid credentials and valid CSRF | New session is authorized; private endpoint returns 200. |
| Session fixation | Compare session ID before and after login | Authentication does not keep the pre-existing anonymous session ID. |
| POST logout with CSRF | Send valid cookie and valid CSRF token | Logout succeeds; server invalidates session. |
| POST logout **without CSRF** | Send valid cookie but omit token | Returns 403 and **does not accidentally log out**. |
| GET logout | Open confirmation page via GET | Session is not lost merely from GET. |
| Replay old session | Use the exact cookie saved before logout | Private endpoint rejects it. |
| Replay old CSRF | After logout, use old cookie/token for a mutating POST | Request is rejected. |
| Inactivity expiration | Set a short session timeout in test env; remain idle past expiry | After timeout, old cookie cannot access resources. |
| Re-login | Log in again after logout | New cookie works; old cookie stays blocked. |
| Browser back/cache | Log out, then click Back, Reload, and use an old tab | Sensitive content cannot be reloaded from server or displayed from cache against policy. |
| Multiple devices/sessions | Two browsers logged into the same account; log out one or log out all | Behavior matches the declared revocation scope. |

Also consider **requests already in flight before logout**: logout does not necessarily cancel an already running request or queued background job. For sensitive operations, check permissions and session validity right where changes occur, adding race protections where necessary.

## 6. Spring Boot 3.x / Java 17+ example: real form login, sessions, and logout

To observe real cookies and expiration timing, tests use **real HTTP against an embedded Servlet container on a random port**, rather than simulating requests solely with MockMvc. This verifies session cookie issuance, session ID rotation, session invalidation, and session timeout.

A Spring Boot 3.x project with the Gradle plugin, Java 17+ toolchain, and dependencies:

```groovy
// Excerpt from build.gradle (Groovy DSL).
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is a **dependencies excerpt** for a Spring Boot project that already has a build script, not a standalone executable `build.gradle`. The Java classes below live in package `demo.sessiontest`. Code targets Spring Boot 3.x / Spring Security 6.x using Servlet and embedded Tomcat provided by `spring-boot-starter-web`.

### 6.1. Main class

File `src/main/java/demo/sessiontest/SessionTestApplication.java`:

```java
package demo.sessiontest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionTestApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionTestApplication.class, args);
    }
}
```

### 6.2. Authentication, API entry point, and logout configuration

File `src/main/java/demo/sessiontest/SecurityConfig.java`:

```java
package demo.sessiontest;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        AuthenticationEntryPoint apiUnauthorized =
                new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED);

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated()
            )
            // Spring Security form login:
            // GET /login renders the form, POST /login verifies credentials.
            .formLogin(Customizer.withDefaults())
            // For /api/** only: replace login redirect with HTTP 401.
            .exceptionHandling(ex -> ex
                .defaultAuthenticationEntryPointFor(
                    apiUnauthorized,
                    new AntPathRequestMatcher("/api/**")
                )
            )
            // Keep default CSRF; logout must be a POST with a CSRF token.
            .csrf(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
                .logoutSuccessHandler((request, response, authentication) ->
                    response.setStatus(HttpServletResponse.SC_NO_CONTENT)
                )
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }
}
```

**Why is this setup well-suited for learning testing?**

- It uses real form login and `HttpSession`, allowing you to capture **cookies before and after login**.
- `.csrf(Customizer.withDefaults())` enforces tokens on both login POST and logout POST without simplifying tests via `csrf.disable()`.
- The entry point returns **401** for `/api/**` instead of redirecting, making unauthenticated rejections unambiguous. `/login` continues working via Spring Security form login.
- Logout invalidates the session, clears the security context, and instructs the client to delete `JSESSIONID`. Tests still **replay the old cookie copy** to prove server-side rejection.
- `204 No Content` is a custom logout contract for this lesson. If an app uses default redirect logout, tests must check the matching status/`Location` instead of always expecting 204.
- Remember-me, JWT, and HTTP Basic are not enabled; those mechanisms have separate revocation rules and require dedicated tests.

Fixed usernames and passwords in the example are **for learning/testing environments only**. Real systems require secure identity/credential management, HTTPS, and proper cookie policies. Never deploy demo accounts to production.

### 6.3. Controller: CSRF token and private resources

File `src/main/java/demo/sessiontest/DemoController.java`:

```java
package demo.sessiontest;

import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class DemoController {

    @GetMapping("/api/public/csrf")
    public Map<String, String> csrf(CsrfToken csrfToken) {
        // Touch the token so HttpSessionCsrfTokenRepository generates/stores it.
        // Spring Security 6 also applies BREACH masking by default.
        return Map.of(
            "headerName", csrfToken.getHeaderName(),
            "token", csrfToken.getToken()
        );
    }

    @GetMapping("/api/private/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @PostMapping("/api/private/update")
    public Map<String, Boolean> update() {
        // Illustrative action proving CSRF and authentication both passed.
        return Map.of("updated", true);
    }
}
```

The `GET /api/public/csrf` endpoint lets tests fetch a valid token over HTTP without parsing the default HTML login page. It returns a masked CSRF token per Spring Security 6's default mechanism; the client submits that token in the indicated header. Because authentication or logout clears the old CSRF token, the example **fetches a fresh token** before subsequent POSTs.

This endpoint exists for the learning example. In real SPAs, token endpoint design, CORS, cookies, BREACH masking, transport headers, and refresh timing must align with frontend architecture; do not assume merely exposing a token makes every SPA flow secure. CSRF tokens are not authentication tokens and must never appear in URLs.

### 6.4. Endpoint to adjust idle timeout — placed in test sources only

To test **real** session expiration without waiting the default 30 minutes, add a controller on the **test classpath**. This file lives under `src/test/java` and is excluded from production artifacts.

File `src/test/java/demo/sessiontest/SessionExpiryProbe.java`:

```java
package demo.sessiontest;

import jakarta.servlet.http.HttpSession;
import org.springframework.context.annotation.Profile;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile("test")
public class SessionExpiryProbe {

    @PostMapping("/__test/expire-soon")
    public ResponseEntity<Void> expireSoon(HttpSession session) {
        // Only the active session in this test has its timeout shortened.
        session.setMaxInactiveInterval(1);
        return ResponseEntity.noContent().build();
    }
}
```

Reasons for this design:

- `HttpSession.setMaxInactiveInterval(1)` sets a **one-second** inactivity timeout for the active session only. The container marks the session expired based on idle time rather than the test calling `invalidate()` directly and mistaking that for timeout.
- The probe route requires authentication due to `anyRequest().authenticated()` and CSRF because it uses POST.
- `@Profile("test")` activates the controller only under the `test` profile. Placed in `src/test/java`, it never ships in the production package.
- Never expose a user-callable endpoint to alter timeouts in production just to make tests easier. This is strictly a **test-suite utility**.

For higher-precision timeout testing, check `server.servlet.session.timeout`, the session repository (e.g., Spring Session/Redis), Servlet container behavior, and last-accessed timestamp updates. Session timeout is **not** an OAuth2 access-token timeout.

## 7. Integration tests over real HTTP with intentional cookie replay

File `src/test/java/demo/sessiontest/LogoutAndExpiryIntegrationTests.java`:

```java
package demo.sessiontest;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class LogoutAndExpiryIntegrationTests {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    // Intentionally omit an automatic CookieManager:
    // the test needs to replay the exact old cookie, even after server deletion.
    private final HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .connectTimeout(Duration.ofSeconds(5))
        .build();

    @Test
    void privateResourceRequiresAuthentication() throws Exception {
        HttpResponse<String> response = get("/api/private/me", null);
        assertEquals(401, response.statusCode());
    }

    @Test
    void loginRotatesSessionIdAndOldAnonymousIdIsNotAuthenticated()
            throws Exception {
        HttpResponse<String> csrfResponse = get("/api/public/csrf", null);
        assertEquals(200, csrfResponse.statusCode());

        String beforeLogin = sessionCookie(csrfResponse);
        String csrf = csrfToken(csrfResponse);

        HttpResponse<String> login = post(
            "/login", beforeLogin, csrf,
            "username=reader&password=demo-password"
        );

        assertEquals(302, login.statusCode());
        String afterLogin = sessionCookie(login);

        // Common Spring Security Servlet config prevents session fixation.
        assertNotEquals(beforeLogin, afterLogin);
        assertEquals(200, get("/api/private/me", afterLogin).statusCode());
        assertEquals(401, get("/api/private/me", beforeLogin).statusCode());
    }

    @Test
    void logoutWithValidCsrfInvalidatesOldSession() throws Exception {
        String signedInCookie = loginAndReturnCookie();
        assertEquals(200, get("/api/private/me", signedInCookie).statusCode());

        String freshCsrf = csrfToken(
            get("/api/public/csrf", signedInCookie)
        );

        HttpResponse<String> logout = post(
            "/logout", signedInCookie, freshCsrf, ""
        );
        assertEquals(204, logout.statusCode());

        // Replay the exact pre-logout JSESSIONID value.
        assertEquals(401, get("/api/private/me", signedInCookie).statusCode());
    }

    @Test
    void logoutWithoutCsrfIsRejectedAndSessionRemainsValid()
            throws Exception {
        String signedInCookie = loginAndReturnCookie();

        HttpResponse<String> rejected = post(
            "/logout", signedInCookie, null, ""
        );
        assertEquals(403, rejected.statusCode());

        // An invalid POST must not accidentally log the user out.
        assertEquals(200, get("/api/private/me", signedInCookie).statusCode());
    }

    @Test
    void getLogoutPageDoesNotPerformLogout() throws Exception {
        String signedInCookie = loginAndReturnCookie();

        // With CSRF enabled, GET /logout is a confirmation page and does not log out.
        get("/logout", signedInCookie);
        assertEquals(200, get("/api/private/me", signedInCookie).statusCode());
    }

    @Test
    void previousCsrfTokenCannotUpdateStateAfterLogout()
            throws Exception {
        String signedInCookie = loginAndReturnCookie();
        String oldCsrf = csrfToken(get("/api/public/csrf", signedInCookie));

        assertEquals(204,
            post("/logout", signedInCookie, oldCsrf, "").statusCode());

        HttpResponse<String> replay = post(
            "/api/private/update", signedInCookie, oldCsrf, ""
        );

        // Session is gone; the old CSRF token is no longer accepted.
        assertEquals(403, replay.statusCode());
        assertFalse(replay.body().contains("updated"));
    }

    @Test
    void idleTimeoutRejectsOldSessionId() throws Exception {
        String signedInCookie = loginAndReturnCookie();
        String csrf = csrfToken(get("/api/public/csrf", signedInCookie));

        HttpResponse<String> shortened = post(
            "/__test/expire-soon", signedInCookie, csrf, ""
        );
        assertEquals(204, shortened.statusCode());

        // Stay idle on the session > 1 second so the container marks it expired.
        Thread.sleep(1600);

        // Client intentionally resends the previously valid cookie.
        assertEquals(401, get("/api/private/me", signedInCookie).statusCode());
    }

    @Test
    void newLoginWorksButLoggedOutSessionNeverWorksAgain()
            throws Exception {
        String oldCookie = loginAndReturnCookie();
        String csrf = csrfToken(get("/api/public/csrf", oldCookie));

        assertEquals(204, post("/logout", oldCookie, csrf, "").statusCode());

        String newCookie = loginAndReturnCookie();
        assertNotEquals(oldCookie, newCookie);
        assertEquals(200, get("/api/private/me", newCookie).statusCode());
        assertEquals(401, get("/api/private/me", oldCookie).statusCode());
    }

    @Test
    void protectedResponseShouldNotBeStoredInSharedCache()
            throws Exception {
        String cookie = loginAndReturnCookie();
        HttpResponse<String> response = get("/api/private/me", cookie);

        assertEquals(200, response.statusCode());
        assertTrue(
            response.headers().firstValue("Cache-Control")
                .orElse("").contains("no-store")
        );
    }

    private String loginAndReturnCookie() throws Exception {
        HttpResponse<String> issued = get("/api/public/csrf", null);
        assertEquals(200, issued.statusCode());
        String anonymousCookie = sessionCookie(issued);
        String token = csrfToken(issued);

        HttpResponse<String> login = post(
            "/login", anonymousCookie, token,
            "username=reader&password=demo-password"
        );
        assertEquals(302, login.statusCode());

        return sessionCookie(login);
    }

    private String csrfToken(HttpResponse<String> response) throws Exception {
        assertEquals(200, response.statusCode());
        JsonNode json = mapper.readTree(response.body());
        String token = json.path("token").asText();
        assertFalse(token.isBlank());
        return token;
    }

    private String sessionCookie(HttpResponse<String> response) {
        return response.headers().allValues("Set-Cookie").stream()
            .map(value -> value.split(";", 2)[0])
            .filter(value ->
                value.startsWith("JSESSIONID=")
                && value.length() > "JSESSIONID=".length()
            )
            .findFirst()
            .orElseThrow(() ->
                new AssertionError("Server did not issue JSESSIONID cookie")
            );
    }

    private HttpResponse<String> get(String path, String cookie)
            throws Exception {
        return send("GET", path, cookie, null, "");
    }

    private HttpResponse<String> post(
            String path, String cookie, String csrf, String body
    ) throws Exception {
        return send("POST", path, cookie, csrf, body);
    }

    private HttpResponse<String> send(
            String method, String path, String cookie,
            String csrf, String body
    ) throws Exception {
        HttpRequest.Builder request = HttpRequest.newBuilder(
            URI.create("http://127.0.0.1:" + port + path)
        ).timeout(Duration.ofSeconds(10));

        if (cookie != null) {
            request.header("Cookie", cookie);
        }
        if (csrf != null) {
            request.header("X-CSRF-TOKEN", csrf);
        }

        if ("POST".equals(method)) {
            request.header(
                "Content-Type", "application/x-www-form-urlencoded"
            );
            request.POST(HttpRequest.BodyPublishers.ofString(
                body, StandardCharsets.UTF_8
            ));
        } else {
            request.GET();
        }

        return client.send(
            request.build(),
            HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
        );
    }
}
```

### 7.1. Why does the test use Java `HttpClient` instead of only MockMvc?

- `@SpringBootTest(webEnvironment = RANDOM_PORT)` starts a **real Servlet container** on a random port.
- Java 17's `HttpClient` sends real HTTP requests. The test **disables `CookieManager`** and **never auto-follows redirects**, letting it capture the pre-logout cookie and intentionally replay it.
- `sessionCookie(...)` extracts `JSESSIONID=...` from server-issued `Set-Cookie` headers; it does not overwrite the old cookie copy when logout sends a delete cookie.
- `loginAndReturnCookie()` runs the real `GET CSRF → POST login → receive new session ID` lifecycle instead of fabricating an authenticated session.
- `@ActiveProfiles("test")` activates the test-only controller to set a one-second timeout on one session. `Thread.sleep(1600)` creates an idle window exceeding the setting. This short duration is strictly for integration tests; never set a one-second timeout in production.
- Each test creates its own session, so logging out in one test does not affect another test's session.
- In CI environments with noisy timing, you can increase the wait or use bounded polling with a final check after idle time clearly exceeds the threshold. Never hit protected endpoints during the wait window, as each request can refresh the session's last-accessed timestamp.

### 7.2. Expected results

When classes are placed at the right paths with a compatible container and dependencies, these tests are **designed to PASS**. Run command:

```bash
./gradlew test --tests demo.sessiontest.LogoutAndExpiryIntegrationTests
```

The test class contains **9 independent test cases**:

| Case | Expected status/state | Meaning |
| --- | --- | --- |
| No cookie | 401 | Private endpoint is protected. |
| Login / session fixation | 302 on login; 200 with new cookie; 401 with old anonymous cookie | Session ID is not fixed across authentication. |
| Logout with CSRF | 204 logout; old cookie gets 401 | Session is invalidated on the server. |
| Logout missing CSRF | 403 logout; old cookie still gets 200 | Cannot force logout via forged POST. |
| GET logout | Session still accesses 200 | GET does not perform logout automatically. |
| Replay old CSRF | Mutating POST gets 403 | Old token/session is no longer valid. |
| Real idle timeout | After 1.6s idle, old cookie gets 401 | Container rejects expired session. |
| New login | New cookie gets 200, logged-out cookie gets 401 | Previous session never revives. |
| Cache header on private | `Cache-Control` contains `no-store` | Reduces risk of sensitive responses being cached unexpectedly. |

**These are expectations of the example code, not test results executed inside this document.** Depending on Boot/Servlet container versions and CI systems, you may need to adjust timeouts, paths, or real app redirect contracts. Never treat a short sleep as the sole "proof" for every kind of distributed session repository.

## 8. When testing with MockMvc: what is and is not proven?

Spring Security provides MockMvc test helpers such as `formLogin()`, `logout()`, and `csrf()`:

```java
import static org.springframework.security.test.web.servlet
        .request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet
        .request.SecurityMockMvcRequestBuilders.logout;
import static org.springframework.security.test.web.servlet
        .request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;

// Illustrative lines inside a test that already has MockMvc mvc:
mvc.perform(formLogin().user("reader").password("demo-password"));
mvc.perform(logout()); // Helper creates POST logout with valid CSRF.
mvc.perform(post("/logout")); // Without CSRF: typically 403.
mvc.perform(post("/api/private/update").with(csrf()));
```

These lines are **in-test excerpts**, not a standalone program; `MockMvc`, the security filter chain, assertions, and session state must be wired properly. `formLogin()` prepares a form request, while `logout()` constructs a POST logout with a CSRF token.

**Common wrong-test warning:** passing an invalidated `MockHttpSession` directly into a subsequent request is not the same as a browser resending `JSESSIONID` over the network while the container checks its session store. Simulating timeout via `mockSession.invalidate()` only tests **explicit invalidation**, not Servlet container **idle timeout**.

Use MockMvc to test filter rules, status codes, CSRF, handlers, and controllers quickly. To verify **`Set-Cookie`, session ID rotation, cookie replay, idle timeout, browser redirects, and container behavior**, add real HTTP integration tests as in section 7.

## 9. Properly evaluating "re-accessing with stale credentials"

"Stale credentials" can mean several things with **different** expected outcomes:

### 9.1. Stale session ID or cookie

After logout or session timeout, the old cookie must **not** grant access to that session. Replaying the exact saved value is the direct check. If the server still returns 200 on a private endpoint, investigate session invalidation, the session store, caches, or fallback authentication mechanisms.

### 9.2. Stale CSRF token

Spring Security logout normally clears the current CSRF token, and successful authentication also clears any pre-login token. On CSRF-protected writes, replaying the old token with the old cookie must be rejected. However, a CSRF token **is not a login credential**: even a valid token grants no access without authentication. Test CSRF and authentication as **two independent conditions**.

### 9.3. Old username/password

If a user merely logged out without changing their password, valid credentials **can still be used to log in again**. That does not mean logout failed. If the policy is account lock, password reset, or revoking all access, write separate tests for disabling credentials and active sessions.

### 9.4. Remember-me cookie

When remember-me is enabled, a request without `JSESSIONID` can still authenticate via the remember-me cookie while both the cookie and server-side token remain valid. Spring Security integrates a remember-me logout handler when configured, yet you **must test it for real**:

- Before logout, the remember-me cookie restores authentication per policy.
- After logout, resending the old remember-me cookie must not restore authentication when the requirement is revoking remember-me.
- With persistent remember-me, verify repository tokens are revoked or rotated properly.
- Do not rely solely on `Set-Cookie` cookie-deletion headers; intentionally replay a saved copy.

### 9.5. JWT/access tokens and refresh tokens

An unexpired self-contained JWT can still be accepted by a resource server after a web app logs out if there is **no** denylist, token versioning, introspection, key revocation, or other stateful check. Logging out an `HttpSession` does not automatically invalidate already-issued JWTs.

For OAuth/OIDC, distinguish:

- **Application logout**: clears the local session.
- **Identity Provider logout**: ends the provider session when supported by the protocol/flow.
- **Refresh token revocation**: blocks obtaining new access tokens per token-issuance policy.
- **Still-valid access tokens**: may require short lifetimes or a matching revocation mechanism.

Acceptance tests must match **real system policy**; never claim "upon logout every token across every system is immediately dead" if the architecture does not support it. When an app allows seamless re-login via an active SSO session, a GET after logout may establish a fresh session via redirect. Tests must distinguish that from the old session ID retaining privileges.

### 9.6. Multiple tabs and multiple devices

Tabs in the same browser profile normally share session cookies. Logging out in tab A causes new requests from tab B using the old session ID to be rejected; however, UI already rendered in tab B's memory may remain visible until reload or state sync. Test both UI state and server rejection of follow-up actions.

Two browsers/devices hold two independent sessions. Logging out device A normally **invalidates only session A**, unless policy requires logging out everywhere. "Log out all devices" requires centralized session/token management and testing across each device.

## 10. Things that make logout/timeout tests "false-green"

### 10.1. Client drops its own cookie before calling the API

If you simply clear cookies in the test client, a private GET naturally returns 401. You have not proven the server destroyed the session. You must **save and resend the old cookie after logout**.

### 10.2. Test unintentionally sends Basic/Bearer credentials

An HTTP client with default `Authorization` headers or automatic token refresh may succeed again through **a new mechanism**, fooling you into thinking the session was not invalidated. Disable automatic credentials/refresh during replay tests, then test each mechanism separately.

### 10.3. Auto-following redirects hides the real status

If a client automatically follows `302 /login` and gets 200 from the login page, assertions seeing 200 lead to wrong conclusions. For API status contracts, pin the expected status; for web contracts, disable redirect following when checking status and `Location`.

### 10.4. Checking only that the cookie was deleted

`deleteCookies("JSESSIONID")` tells the browser to delete the cookie. A deleted client cookie does not prove the server revoked an earlier copy. Tests must resend the exact old ID.

### 10.5. Calling `invalidate()` and calling it "session expiration"

Invalidation is an active step. Idle timeout must test **inactivity duration**, the container, or the session repository. With Spring Session/Redis, also factor in storage TTLs, clock sync, and session cleanup.

### 10.6. Background requests refreshing the session

Periodic requests like polling, heartbeats, or data-fetch endpoints can update the session's last-accessed time and prevent timeouts from ever firing. When measuring idle timeout, ensure no background request touches that session.

### 10.7. Confusing 401 and 403

In the example, unauthenticated private GETs return 401. A POST missing CSRF can return 403 **before permissions are even checked**. Base assertions on the specific path taken instead of assuming every 403 means "logged in but lacking permission."

### 10.8. Browser Back shows a cached page

After logout, pressing Back may display a rendered snapshot even after the server destroyed the session. That does not prove the session is active, yet it poses a data-exposure risk on shared computers. Combine `Cache-Control: no-store`, reloads, and real UI testing.

### 10.9. Confusing session timeout with JWT expiry

Servlet session timeout does not expire a JWT. A backend using bearer tokens independently of sessions must test token lifetimes and revocation using its own mechanism.

### 10.10. Skipping session fixation and re-login checks

If you only test a single logout, you can miss a pre-login session ID staying unchanged or an old session somehow regaining access after a new login. Compare IDs before/after login and prove an invalidated old ID can never be reactivated.

## 11. Real browser testing and post-logout data protection

HTTP tests prove server authentication state, while users also see the UI. Test manually or with Playwright/Selenium using test accounts:

1. Log in, open a page displaying personal data, and open the same page in a second tab.
2. Log out in the first tab via the real UI flow.
3. Return to the second tab; try loading more data, performing a write, and reloading. New requests must be rejected or prompt for login.
4. Use Back/Forward: check whether sensitive data appears from cache or in-memory state. If so, design frontend state cleanup, cache headers, and shared-device policies.
5. Inspect the Network tab: logout is a POST with CSRF when using cookies, status/redirect is right, and no token/session ID appears in URLs.
6. Try leaving a request in flight when logout occurs; note that an already-accepted request may still finish.
7. Log out in one tab and log in as another user: the previous user's content/resources must not be reused from cache or stale state.
8. Verify private responses carry appropriate cache policies and clients do not persist sensitive data longer than necessary.

**Note:** `Cache-Control: no-store` reduces the chance browsers/proxies cache responses, yet does not automatically wipe the current DOM, `localStorage`, `IndexedDB`, or SPA data held in RAM. If the app stores sensitive data outside the session, frontend logout logic must clear it intentionally.

## 12. Sessions across multiple servers and Spring Session

In environments with load balancers and multiple instances:

- If sessions live only in each node's memory, routing/sticky sessions dictate which node finds the session. That causes "intermittent login drops," which must not be confused with proper logout.
- When using **Spring Session** with Redis/JDBC, verify that sessions are deleted/expired in the shared repository and requests routed to **another node** are still rejected.
- Redis TTLs and session expiration cleanup can have operational lag; base acceptance criteria on real request authentication behavior rather than watching keys disappear instantaneously.
- For session fixation, verify session ID rotation on the real deployment stack; do not assume identical behavior across all repositories and custom containers.
- For "log out all devices," the system must enumerate and revoke **every session** belonging to the account; default single-browser logout does not do this automatically.

A good distributed test logs in through node A, logs out through node B, and replays the old cookie against both node A and node B. Both must reject within the committed consistency bounds. For SSO apps, also test IdP state and automatic re-login behavior.

## 13. Reusable logout/timeout acceptance workflow

When building a test suite for your own application:

- **Define the authentication mechanism.** Session cookie, Basic, bearer JWT, remember-me, OAuth2, or a hybrid? Revocation outcomes differ.
- **Lock down the HTTP contract.** For APIs, specify 401/403/204; for browsers, specify 302 and login/confirmation pages; keep `WWW-Authenticate` if required by protocol.
- **Build valid session fixtures.** Use real login, save cookies before and after authentication, and fetch CSRF tokens at the right stage.
- **Test safe logout.** POST with CSRF succeeds; POST without token is rejected; GET does not log out automatically.
- **Replay stale data.** Resend the exact session ID and CSRF token from the prior session; the server must grant no access.
- **Test real timeout.** Configure a short timeout on the test server/session repository, let the session sit idle, and resend the old ID.
- **Prove legitimate users are not blocked.** A fresh login creates a working session; valid requests still succeed.
- **Test browsers and distributed setups.** Cache/back button, multiple tabs, remember-me, IdP, Redis, and multi-node when present in the architecture.
- **Observe the right evidence.** Status, `Set-Cookie`, `Location`, response body, session repository, and operational logs; never print real cookies/tokens into failure reports.

### Pre-production checklist

| Criterion | Expectation |
| --- | --- |
| Logout has CSRF and right method | Cannot be triggered arbitrarily by external sites via GET or tokenless POST. |
| Server-side session invalidation | Old cookie/session ID is rejected even when replayed by clients. |
| Session fixation | Pre-login and post-login IDs differ per chosen strategy. |
| Inactivity expiration | Timeout is measured via tests using a real container/repository. |
| CSRF token lifecycle | Fresh tokens are issued after login/logout; old tokens cannot mutate state. |
| Fresh login | New session works; old session never "revives." |
| Remember-me / SSO / tokens | Revocation policies are tested separately rather than assumed from servlet logout. |
| Cache / Back / multi-tab | Sensitive data cannot be viewed or acted upon against policy. |
| Multi-node | Revocation/expiration is consistent across all deployed instances. |
| CI stability | Never use production sessions, real credentials, or overly tight fixed timeouts that cause flaky tests. |

## 14. Practice scenarios

**Scenario A:** After logout, Chrome stops sending `JSESSIONID` and `GET /api/private/me` returns 401. Does that prove the server invalidated the session?

**No.** You must capture the **pre-logout cookie value** and resend it manually. If the server still returns 200, the server-side session may not have been destroyed or another auth mechanism is restoring access.

**Scenario B:** After logout, logging in again with the same username/password succeeds. Is logout broken?

**No.** Session logout does not disable valid login credentials. Changing passwords or revoking credentials requires separate workflows and tests.

**Scenario C:** After waiting one second, a test calls `mockSession.invalidate()` and gets 401. Is that enough to prove idle timeout works?

**No.** That tests explicit invalidation. Testing idle expiration requires a container/repository that actually enforces inactivity timeouts.

**Scenario D:** An API uses JWTs; servlet session logout succeeds yet the old access token can still read data. Must that be treated as a bug?

**Depends on the system's token policy.** If the contract promises immediate token revocation on logout, it is a bug to fix. If short-lived access tokens are intentionally unrevoked until expiry, document and test exact lifetimes and refresh-token revocation. Never infer self-contained token state from session-cookie test results.

**Scenario E:** After logout, pressing Back still shows account page content, while pressing Reload returns 401. What should be investigated?

The server appears to reject the old session, yet the browser may be displaying cached content. Inspect `Cache-Control`, browser back-forward cache, SPA state, local storage, and display policies for shared devices.

## 15. Official reference documentation

- Spring Security — [Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html).
- Spring Security — [Testing Logout with MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/logout.html).
- Spring Security — [Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html).
- Spring Security — [CSRF and logout](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html).
- Spring Security — [Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/).
- Spring Boot — [Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html).
- Jakarta Servlet — [HttpSession API](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/httpsession).