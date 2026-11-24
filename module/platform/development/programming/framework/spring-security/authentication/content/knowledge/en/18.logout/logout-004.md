# Invalidating HttpSession and Clearing Related Cookies on Logout

> **Spring Security - authentication → Logout.** This lesson uses **Spring Boot 3.x, Spring Security 6.x, Servlet, Java 17+**. The focus is two tasks that must be distinguished yet coordinated: **invalidating server-side login state (`HttpSession` and `SecurityContext`)**, and **instructing the browser to delete related cookies** (`JSESSIONID`, remember-me, additional application cookies). The example uses stateful form login; the final section highlights differences from stateless JWT, OAuth2, and multi-device logout.

## 1. What Must a Successful Logout Do?

In a session-based Spring MVC app, after a user successfully submits a username/password, Spring Security typically stores `Authentication` in `SecurityContext` and persists that context through `SecurityContextRepository`, commonly `HttpSessionSecurityContextRepository`. The browser keeps a cookie such as `JSESSIONID` to reference the server-side session.

When clicking **Log out**, the security requirement is not merely redirecting the browser to `/login`. A proper logout must ensure:

1. The current session on the server can no longer be used to retrieve the old authentication.
2. `SecurityContextHolder` for the current request/thread and the corresponding `SecurityContextRepository` are cleaned up.
3. The cookie pointing to the old session is expired or deleted in the browser where possible; remember-me cookies and related application cookies are handled according to policy.
4. Tokens/credentials **not stored in HttpSession** are handled separately: remember-me may require revocation, and JWTs/refresh tokens may have different lifecycles.
5. The browser receives an appropriate logout response; the next access to a protected resource must prompt for login again, **unless an independent valid credential** is resent.

These objects are not the same thing:

| Object | Where does it live? | Effect on proper logout |
| --- | --- | --- |
| `SecurityContextHolder` | Inside the request/thread context holder mechanism | Clears the current authentication; avoids leaving a principal after logout on the same thread |
| `HttpSession` | On the servlet container or server-side session store | `invalidate()` prevents the current session from being reused |
| `JSESSIONID` | In the browser-side cookie | Browser is told to forget the ID (expired cookie); the cookie itself is **not** the authentication data |
| `remember-me` | Persistent login cookie (and possibly server token record) | Logout handler deletes the cookie; revoking a copied token depends on the mechanism |
| JWT/refresh token | On the client and/or authorization server | **Not automatically invalidated** by `HttpSession.invalidate()` |

**Core point:** deleting a cookie in the browser is not destroying the server-side session state; conversely, invalidating the server-side session does not guarantee all cookies disappear from every device or copy. For secure authentication, the server must be the authority deciding whether an old session remains valid.

## 2. Standard Spring Security Servlet Logout Flow

When Spring Security is enabled for Servlet, `LogoutFilter` handles the logout endpoint in the filter chain. With default CSRF enabled, **`POST /logout` with a valid CSRF token** is the request that executes logout. `GET /logout` typically displays a **confirmation page** with a POST form and CSRF token; GET is not a session-deleting action.

```text
Logged in: Browser                        Server
      |                                     |
      | Cookie: JSESSIONID=SESSION_A        |
      | GET /me                             |
      |------------------------------------>|
      |                   SecurityContext from HttpSession A
      |<------------------------------------| 200 "alice"
      |                                     |
      | POST /logout + CSRF                 |
      | Cookie: JSESSIONID=SESSION_A        |
      |------------------------------------>|
      |                 CsrfFilter verifies CSRF
      |                 LogoutFilter matches logout request
      |                   + SecurityContextLogoutHandler
      |                     - invalidate HttpSession A
      |                     - clear SecurityContextHolder
      |                     - clear SecurityContextRepository
      |                   + RememberMeServices LogoutHandler
      |                     - expire browser's remember-me cookie
      |                   + CsrfLogoutHandler
      |                     - remove saved CSRF token
      |                   + CookieClearingLogoutHandler (if added)
      |                     - Set-Cookie for cookies to expire
      |                   + LogoutSuccessHandler
      |<------------------------------------| 302 /signed-out
      |                     Set-Cookie: JSESSIONID=; Max-Age=0...
      |                     Set-Cookie: remember-me=; Max-Age=0...
      |
      | GET /me (no valid session/cookie)
      |------------------------------------>|
      |<------------------------------------| 302 /login
```

According to Spring Security documentation, the default logout chain includes `SecurityContextLogoutHandler`, the remember-me handler if configured, `CsrfLogoutHandler`, event publishing, and `LogoutSuccessHandler`. `SecurityContextLogoutHandler` by default **invalidates HttpSession** and clears the context. Cleanup actions are the responsibility of `LogoutHandler`s; redirecting or returning an HTTP status is performed afterward by **`LogoutSuccessHandler`**.

### 2.1. Why Shouldn't GET /logout Directly Destroy the Session?

GET is normally considered a safe method and can be triggered by browsers, prefetching, crawlers, or external links. If a GET automatically logs out, the app is exposed to **logout CSRF** and unpredictable UX. Enabling CSRF makes Spring Security require **POST /logout with a token**; when receiving `GET /logout`, the framework can show a confirmation form so the user intentionally submits POST.

Do not disable CSRF globally just to make a `<a href="/logout">Log out</a>` link work. Use a POST form with a token, or JavaScript sending a POST with a token from a safe source. A logout request rejected due to missing CSRF must not destroy the session.

### 2.2. LogoutFilter and Controllers Are Different

`LogoutFilter` sits before `AuthorizationFilter` in the filter chain; a logout endpoint configured via the DSL generally needs no separate MVC controller. You only need:

```java
http.logout(logout -> logout
    .logoutUrl("/logout")
    .logoutSuccessUrl("/signed-out")
    .permitAll()
);
```

If `/signed-out` needs to be rendered by MVC after the redirect, that endpoint must allow public access. `logout.permitAll()` helps add the logout URLs to the permitted list; the example still declares `/signed-out` explicitly for readability.

**Do not** write a `@PostMapping("/logout")` that merely calls `request.getSession().invalidate()` and consider logout complete. A controller can miss the context repository, CSRF token, remember-me, and cleanup handlers. Prefer using `logout(...)` to integrate with the framework mechanism. When a custom MVC logout is truly needed, invoke the appropriate `LogoutHandler`s—at minimum `SecurityContextLogoutHandler`—and ensure the endpoint is accessible. Do not create a new session just to destroy it.

## 3. HttpSession.invalidate(), SecurityContext, and Session ID

### 3.1. State Lives on the Server; the Cookie Is Only a Reference

After login, suppose Spring Security stores the context in session A. When the browser sends cookie `JSESSIONID=A`, the servlet container uses the ID to look up the session. At logout time:

```java
// This is the basic Servlet idea, not a full replacement for
// Spring Security's LogoutFilter/LogoutHandlers.
HttpSession session = request.getSession(false);
if (session != null) {
    session.invalidate();
}
```

`getSession(false)` matters: when there is no session, it returns `null` rather than creating a new session. `invalidate()` renders the session invalid; session attributes cannot be reused afterward. Spring Security's `SecurityContextLogoutHandler` does the same (along with clearing `SecurityContext`) during the logout flow.

**Do not confuse with `session.setMaxInactiveInterval(0)`**: this is not the primary API to immediately end the current login under the logout contract. Use standard invalidation/handlers, rather than just changing the timeout or overwriting a session attribute with `null`.

### 3.2. Why Must SecurityContext Also Be Cleared?

In Servlet, `SecurityContextHolder` lets filters and application code access `Authentication` for the current request. If you only invalidate the session while keeping an `Authentication` in the holder or in a custom `SecurityContextRepository` with separate state, a request or internal processing step may still see the authenticated principal.

`SecurityContextLogoutHandler` handles cleaning these places. Spring Security DSL example:

```java
.logout(logout -> logout
    .invalidateHttpSession(true)
    .clearAuthentication(true)
);
```

- `invalidateHttpSession(true)`: requests destroying the current session if present. This is the default for the standard logout handler.
- `clearAuthentication(true)`: clears authentication/context via the handler. This is also the default in typical configurations.
- The handler also interacts with `SecurityContextRepository` according to the framework version's behavior. Therefore logout should not be replaced by a standalone `SecurityContextHolder.clearContext()`: clearing only the thread-local does not invalidate the server-side session.

If using a special repository such as a Redis-backed session or custom `SecurityContextRepository`, verify that clearing/invalidating actually affects the backend. Practical differences can arise from how the container, session store, or filter chain is configured.

### 3.3. Session Fixation, Rotation, and Logout

On login, Spring Security can change the session ID (e.g., `changeSessionId`) to protect against session fixation. On logout, whichever ID belongs to the **current** session must be invalidated. Do not try to hardcode an old ID for cookie deletion.

For example:

```text
Before login:      JSESSIONID=GUEST_ID
After login:       JSESSIONID=LOGIN_ID   (may be rotated)
POST /logout:      invalidates session LOGIN_ID
Next access:       cannot use LOGIN_ID to retrieve old Authentication
```

Returning the login page or seeing the cookie vanish in DevTools **is not the sole proof**; test both the `HttpSession` state and access control after logout.

### 3.4. Logging Out One Session Differs from Logging Out All Sessions

`invalidateHttpSession(true)` applies to the **current HTTP session**. If the same account still has session B on another device, logging out session A **does not automatically destroy B**. A "log out all devices" feature must be designed separately: a distributed session registry/store, session revocation mechanisms, remember-me, access/refresh tokens, and long-lived connections. Do not assume logging out A destroys all other sessions.

## 4. Deleting Cookies: The Cookie Name Alone Is Not Enough

Browsers store cookies by attributes such as **Name, Domain, and Path**; to make the browser delete a cookie, the response must set a cookie with matching name/scope and an expired time or `Max-Age=0`. Illustrative example:

```http
HTTP/1.1 302 Found
Location: /signed-out
Set-Cookie: JSESSIONID=; Max-Age=0; Path=/; HttpOnly
Set-Cookie: ui-hint=; Max-Age=0; Path=/
Set-Cookie: remember-me=; Max-Age=0; Path=/; HttpOnly
```

This is only an **illustrative response**: the Servlet container, Spring Security, reverse proxy, and cookie config can change the count, order, or attribute values of `Set-Cookie`.

A cookie named `JSESSIONID` issued with `Path=/app` will **not** be deleted merely by setting a cookie of the same name with `Path=/`. If a cookie has `Domain=.example.com`, deleting it with a host-only cookie of a different Domain may miss the original. Therefore, inspect the **actual Name/Path/Domain in DevTools** and configure deletion to match; especially with multiple apps on the same domain, proxy rewrites, or context-path deployments.

### 4.1. Spring Security Supports deleteCookies

```java
http.logout(logout -> logout
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("JSESSIONID", "ui-hint")
);
```

`deleteCookies(...)` adds `CookieClearingLogoutHandler`, including the named cookies in the response with expiration. In the example, `ui-hint` is a UI state cookie managed by the **application itself** that should be deleted at logout. Do not use wildcards to delete all cookies on a domain with this API.

**Note:** Spring Security docs mention it is usually unnecessary to list `JSESSIONID`, as invalidating the session lets the container handle it; moreover, deleting `JSESSIONID` via `deleteCookies` is **not strictly guaranteed across all Servlet containers**. Configuring cookie deletion by name alone does not replace `invalidateHttpSession(true)`. When browser behavior must be guaranteed, test with the target container/proxy, context path, and specific cookie attributes.

### 4.2. Remember-Me Cookies Have Their Own Handler

If `rememberMe(...)` is enabled, the standard `TokenBasedRememberMeServices` or `PersistentTokenBasedRememberMeServices` integrates a `LogoutHandler` to **delete the remember-me cookie** on logout. Thus in the runnable example, we do not need to add `"remember-me"` to `deleteCookies(...)` again; if you change the name/Path/Domain or use a custom `RememberMeServices`, verify the handler actually deletes the active cookie.

Distinguish clearly:

- **Deleting the remember-me cookie in the browser:** a normal user stops sending it after logout.
- **Revoking a token on the server:** exists only if the mechanism is stateful/stores tokens and performs revocation. With simple hash-based remember-me, a **cookie copy captured before logout can still be replayed** until expiration or a password/secret change. `clear cookie` does not delete copies on an attacker's device.
- **Persistent remember-me:** keeps a token series/token in a repository, supporting policy-based control and cleanup; verify logout/rotation/revocation according to the implementation.
- **Remember-me can auto-log back in:** if the browser still sends a valid cookie after the session is destroyed, `RememberMeAuthenticationFilter` can create a `RememberMeAuthenticationToken` for the next request. That is why deleting only `JSESSIONID` is often **insufficient** for a "complete logout" experience.

### 4.3. Clear-Site-Data: A Broad-Impact Alternative

Spring Security supports `HeaderWriterLogoutHandler` with `ClearSiteDataHeaderWriter`:

```java
import org.springframework.security.web.authentication.logout.HeaderWriterLogoutHandler;
import org.springframework.security.web.header.writers.ClearSiteDataHeaderWriter;

HeaderWriterLogoutHandler clearCookies =
    new HeaderWriterLogoutHandler(
        new ClearSiteDataHeaderWriter(
            ClearSiteDataHeaderWriter.Directive.COOKIES));

http.logout(logout -> logout
    .addLogoutHandler(clearCookies)
);
```

The `Clear-Site-Data: "cookies"` header instructs the browser to clear site-scoped cookies per browser rules, useful when handling many cookies and reducing dependence on specific paths. However, it can affect **other applications on the same site/domain**, and browser support, HTTPS/secure context, and proxies must be tested. Do not blindly enable `Directive.ALL` (which can also clear caches/storage) just to solve one cookie, as the UX impact can be large.

Practice **right-sized scoping**: for application cookies, delete the exact name/path/domain; if broader deletion is desired, document the reason, test on target browsers, and evaluate cross-app impact. Do not imagine `Clear-Site-Data` revokes bearer tokens stored on client machines or third-party servers.

## 5. Spring Boot 3 / Spring Security 6 / Java 17+ Example

The example includes default form login, a demo account, opt-in remember-me, and logout that invalidates the session and cleans up cookies. `/me` is a protected endpoint; `/signed-out` is a public page confirming logout. In production applications, replace the in-memory user store, remember-me key, and cookie policy with secure configuration.

### 5.1. Dependencies

In an app with the Spring Boot Gradle plugin and Java 17:

```groovy
// build.gradle (dependencies section)
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### 5.2. Main

**`src/main/java/example/logoutdemo/LogoutDemoApplication.java`**

```java
package example.logoutdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LogoutDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LogoutDemoApplication.class, args);
    }
}
```

### 5.3. SecurityConfig

**`src/main/java/example/logoutdemo/SecurityConfig.java`**

```java
package example.logoutdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

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
            User.withUsername("alice")
                .password(encoder.encode("study-pass"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            UserDetailsService users,
            Environment environment) throws Exception {

        String rememberKey =
            environment.getRequiredProperty("app.remember-me.key");

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/signed-out").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .defaultSuccessUrl("/me", true)
                .permitAll())
            .rememberMe(remember -> remember
                .key(rememberKey)
                .userDetailsService(users)
                .rememberMeParameter("remember-me")
                .tokenValiditySeconds(7 * 24 * 60 * 60))
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/signed-out")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID", "ui-hint")
                .permitAll());

        // CSRF is ENABLED by default, so POST /logout requires a CSRF token.
        // RememberMeServices is registered as a LogoutHandler.
        return http.build();
    }
}
```

**Line-by-line explanation related to logout:**

1. `.logoutUrl("/logout")` registers the endpoint handled by `LogoutFilter`. No need to write a POST `/logout` MVC controller.
2. `.logoutSuccessUrl("/signed-out")` only controls the post-cleanup redirect. It **does not** perform cleanup in place of `LogoutHandler`.
3. `.invalidateHttpSession(true)` requests destroying the existing session. This is a stateful policy and does not delete sessions on other devices.
4. `.clearAuthentication(true)` along with the handler ensures the current context has no authentication left. Keep this default so you never end up with deleted cookies while `SecurityContext` can still be reloaded.
5. `.deleteCookies("JSESSIONID", "ui-hint")` issues expiring cookies; `JSESSIONID` still needs to be invalidated server-side first. `ui-hint` illustrates an application cookie that can be cleared alongside logout, even though it holds no credentials.
6. `.rememberMe(...)` enables the `remember-me` cookie when login includes `remember-me=on`; the standard remember-me mechanism participates in logout to clear that cookie. The example uses a hash-based token for demo purposes, with no per-token server revocation.
7. `.permitAll()` ensures logout-related URLs are accessible per policy. `/signed-out` is explicitly declared permitted.
8. There is no `.csrf(AbstractHttpConfigurer::disable)`: form login/logout use cookies so they must be protected by CSRF.
9. The remember-me key must not live in production source code; across multiple instances, use a consistent key for the same app or design an appropriate token store.

### 5.4. Controller

**`src/main/java/example/logoutdemo/AccountController.java`**

```java
package example.logoutdemo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/signed-out")
    String signedOut() {
        return "signed-out";
    }
}
```

When logged in, `GET /me` returns the body:

```text
alice
```

After logout, `GET /signed-out` returns:

```text
signed-out
```

Those are the **expected bodies** of the endpoints, not stdout produced by running the documentation. `GET /me` without valid authentication left redirects to the default login page.

### 5.5. application.yml

**`src/main/resources/application.yml`**

```yaml
app:
  remember-me:
    # String for local demo only; replace with a real secret from environment.
    key: local-demo-key-not-for-real-deployments-2026

server:
  servlet:
    session:
      timeout: 20m
      cookie:
        http-only: true
        same-site: lax
```

This is a configuration for local learning, not a production secret. For production HTTPS, enable the `Secure` cookie flag; manage Path/Domain of both the session cookie and remember-me cookie, and check whether a proxy rewrites cookies. If using `server.servlet.context-path` or mounting the app under another path via reverse proxy, test both actual cookie issuance and deletion.

## 6. Testing with MockMvc

The goal is to test **both sides**: (A) the server has invalidated the session and subsequent requests no longer have full authentication; (B) the response instructs the browser to delete cookies. Default tests cannot fully simulate a real browser cookie jar/Servlet container, so browser instructions are provided in section 7.

**`src/test/java/example/logoutdemo/LogoutFlowTest.java`**

```java
package example.logoutdemo;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class LogoutFlowTest {

    @Autowired
    MockMvc mvc;

    private MvcResult login(boolean remember) throws Exception {
        var request = post("/login")
            .with(csrf())
            .param("username", "alice")
            .param("password", "study-pass");

        if (remember) {
            request.param("remember-me", "on");
        }

        return mvc.perform(request)
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/me"))
            .andReturn();
    }

    private MockHttpSession sessionOf(MvcResult result) {
        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    @Test
    void successfulLoginCreatesAuthenticatedSession() throws Exception {
        MockHttpSession session = sessionOf(login(false));

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void postLogoutInvalidatesSessionAndExpiresNamedCookies()
            throws Exception {
        MockHttpSession session = sessionOf(login(false));
        assertFalse(session.isInvalid());

        MvcResult result = mvc.perform(post("/logout")
                .with(csrf())
                .session(session)
                .cookie(new Cookie("ui-hint", "expanded")))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/signed-out"))
            .andReturn();

        assertTrue(session.isInvalid(), "HttpSession A must be invalidated");

        Cookie jsessionid = result.getResponse().getCookie("JSESSIONID");
        Cookie uiHint = result.getResponse().getCookie("ui-hint");
        assertNotNull(jsessionid);
        assertNotNull(uiHint);
        assertEquals(0, jsessionid.getMaxAge());
        assertEquals(0, uiHint.getMaxAge());

        mvc.perform(get("/signed-out"))
            .andExpect(status().isOk())
            .andExpect(content().string("signed-out"));

        // A new request without a valid session/cookie must log in again.
        mvc.perform(get("/me"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login"));
    }

    @Test
    void missingCsrfCannotInvalidateSession() throws Exception {
        MockHttpSession session = sessionOf(login(false));

        mvc.perform(post("/logout").session(session))
            .andExpect(status().isForbidden());

        assertFalse(session.isInvalid());
        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void getLogoutIsConfirmationNotTheLogoutAction()
            throws Exception {
        MockHttpSession session = sessionOf(login(false));

        mvc.perform(get("/logout").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("form")));

        assertFalse(session.isInvalid());
        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void rememberMeCookieIsClearedByItsLogoutHandler()
            throws Exception {
        MvcResult login = login(true);
        MockHttpSession session = sessionOf(login);
        Cookie originallyIssued =
            login.getResponse().getCookie("remember-me");
        assertNotNull(originallyIssued);

        MvcResult logout = mvc.perform(post("/logout")
                .with(csrf())
                .session(session)
                .cookie(originallyIssued))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/signed-out"))
            .andReturn();

        assertTrue(session.isInvalid());

        Cookie expired =
            logout.getResponse().getCookie("remember-me");
        assertNotNull(expired);
        assertEquals(0, expired.getMaxAge());
    }

    @Test
    void copiedHashBasedRememberCookieCanOutliveBrowserLogout()
            throws Exception {
        MvcResult loggedIn = login(true);
        MockHttpSession session = sessionOf(loggedIn);
        Cookie stolenCopy =
            loggedIn.getResponse().getCookie("remember-me");
        assertNotNull(stolenCopy);

        mvc.perform(post("/logout")
                .with(csrf())
                .session(session))
            .andExpect(status().is3xxRedirection());
        assertTrue(session.isInvalid());

        // Simulates a cookie copy existing on another client.
        // Hash-based remember-me has no per-token server revocation.
        mvc.perform(get("/me").cookie(stolenCopy))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void logoutOneSessionDoesNotInvalidateAnotherSession()
            throws Exception {
        MockHttpSession first = sessionOf(login(false));
        MockHttpSession second = sessionOf(login(false));
        assertNotEquals(first.getId(), second.getId());

        mvc.perform(post("/logout")
                .with(csrf())
                .session(first))
            .andExpect(status().is3xxRedirection());

        assertTrue(first.isInvalid());
        assertFalse(second.isInvalid());

        mvc.perform(get("/me").session(second))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void postLogoutWithoutPriorLoginRemainsSafe()
            throws Exception {
        mvc.perform(post("/logout").with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/signed-out"));

        mvc.perform(get("/me"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login"));
    }
}
```

The test suite has **8 `@Test` methods**. Expected results:

- Login creates a session sufficient for `GET /me` to return `alice`.
- POST logout with CSRF sets `MockHttpSession.isInvalid() == true` and returns `JSESSIONID`/`ui-hint` cookies with `Max-Age=0`.
- POST logout **without** CSRF is rejected, and the authenticated session is not destroyed.
- GET logout renders the confirmation page (with CSRF enabled), without losing the session.
- The standard remember-me handler expires the remember-me cookie in the response.
- **A valid copy of a hash-based remember-me cookie can still be replayed** after the original browser logs out; that is why cookie clearing must be distinguished from token revocation.
- Logging out one session does not by default log out another session of the same account.
- Logging out when unauthenticated completes safely and creates no logged-in user.

Run in the project root containing the Gradle wrapper:

```bash
./gradlew test --tests example.logoutdemo.LogoutFlowTest
./gradlew bootRun
```

On Windows use `gradlew.bat`. This is code and assertions **expected to run** in a Spring Boot 3.x / Spring Security 6.x setup, not execution output from this document. MockMvc is a server-side simulation; it does not simulate the full browser cookie jar or real session timeout events.

### 6.1. Why Must Tests Check Both the Session and Cookies Separately?

Suppose the app only sends `Set-Cookie: JSESSIONID=; Max-Age=0` without `invalidate()`: an attacker holding a copy of the session ID can keep accessing until session timeout. Conversely, if the session was destroyed yet the browser keeps the old cookie, subsequent requests can send an invalid cookie, causing inconsistent invalid-session UX or cookie cleanup. With a still-valid remember-me cookie, the user might even be automatically logged back in after the session is destroyed.

Therefore, a test that only checks HTTP 302 to the logout page **is insufficient**. You must check session state, cookie expiry, and protected requests after logout. In end-to-end tests, resend the old session ID with an independent cookie jar to a **real container** to verify the server genuinely rejects it; MockMvc does not fully simulate container cookie-ID-to-session mapping.

## 7. Testing with a Browser and DevTools

When running `bootRun`, use a browser on localhost, open `/login`, and log in as `alice` / `study-pass`.

1. **Before logout:** visit `/me` and verify body `alice`. In DevTools → Application/Storage → Cookies, inspect cookie names and Path/Domain, `Secure`, `HttpOnly`, and `SameSite` attributes. Do not copy cookie values into bug-report screenshots.
2. **Enable remember-me if testing it:** check remember-me on login. The browser may hold both `JSESSIONID` and `remember-me`. Inspect `Set-Cookie` *at the attribute level*, without sharing secrets.
3. **Perform a proper logout:** visit `GET /logout` to view the confirmation page, then submit POST via the form. Or use an application form containing the CSRF field and action `/logout`.
4. **Logout network response:** verify `302 Location: /signed-out`, and the expiring `Set-Cookie` headers with the right name/path/domain; `remember-me` is cleared by the remember-me handler if issued.
5. **After logout:** `GET /me` must redirect to `/login` instead of reusing the old session. Browser Back may display cached content; refresh/call the server to confirm authorization, and configure cache headers for sensitive data.
6. **Negative CSRF test:** in a test environment, send POST `/logout` missing the token; verify `403` and that the session was not inadvertently destroyed. Do not disable CSRF to "fix" it.
7. **Different cookie path test:** if deployed under `/app` or behind a reverse proxy, compare `Path` and `Domain` on the issued cookie and the cleared cookie. A mismatch can leave the cookie behind; test on the real target container.
8. **Two separate sessions test:** log in with the same account on two browser profiles; logging out profile A must not destroy B unless the app implements logout-all. Do not use two tabs in the same profile to simulate two sessions.

In production environments, session cookies should be `HttpOnly`/`Secure`, with appropriate `SameSite` and Path/Domain, and the site should use HTTPS. In cross-site API contexts, cookie and CSRF policies must be designed for real request patterns rather than copied verbatim from sample configs.

## 8. Common Mistakes

| Mistake | Risk / Consequence | Proper Approach |
| --- | --- | --- |
| Only redirecting to `/login` when Logout is clicked | Context and session may still remain; `/me` remains accessible | Use `LogoutFilter` + `SecurityContextLogoutHandler` |
| Only deleting `JSESSIONID` in the browser | Server may still keep the session; a copied ID can be reused | Invalidate the session on the server |
| Only calling `SecurityContextHolder.clearContext()` | Context from session/repository can be reloaded | Use standard logout handlers and invalidate HttpSession |
| Only calling `session.invalidate()` in an MVC controller | Can miss context/remember-me/CSRF/logout events | Use Spring Security's logout DSL or invoke all required handlers |
| Using GET as the logout action | Prone to logout CSRF or browser prefetch triggers | POST + CSRF; GET is only for a confirmation page |
| Assuming `deleteCookies("JSESSIONID")` always works | Different cookie Path/Domain, different container/proxy | Inspect actual cookies; server invalidation remains mandatory |
| Skipping remember-me cleanup | Session ends yet remember-me cookie auto-restores identity | Register the remember-me logout handler; check replay/revocation |
| Assuming deleting remember-me cookie revokes all copies | Hash-based token copies can stay valid until expiration | Choose persistent tokens/revocation policy when needed |
| Assuming logging out session A logs out all devices | Independent session B is not automatically destroyed | Design dedicated session revocation/logout-all |
| Assuming invalidating HttpSession revokes JWTs | Stateless JWTs do not depend on that session | Revoke refresh tokens, use denylist/introspection/token TTL per design |
| Using `Clear-Site-Data: "cookies"` without impact assessment | May wipe cookies of other apps on the same site | Check scope, browser support, real behavior |
| Logging JSESSIONID or remember-me tokens | Enables session hijacking or token replay | Redact and log only minimal audit metadata |
| Testing only for a 302 logout redirect | Does not prove server invalidation or cookie deletion | Assert session invalid + Set-Cookie expiry + subsequent request |
| Disabling CSRF to test logout in Postman | Opens vulnerabilities for browser cookie auth | Keep CSRF and use a valid token in tests |

## 9. Special Cases: OAuth2, JWT, and Multi-System Logout

**Stateless JWT Resource Server:** if requests use a bearer access token with no `HttpSession`, calling `invalidateHttpSession(true)` in the app **does not automatically destroy access tokens** everywhere. Signed JWTs remain valid until `exp` unless introspection/revocation/denylist or authorization server policies intervene. Distinguish browser session logout from OAuth2 token revocation/refresh-token rotation.

**OIDC login:** logging out the application's session is only *local logout*. To log out at the Identity Provider and other applications, use an appropriate OIDC logout mechanism (RP-initiated logout, front/back-channel as supported) with redirect URI and state validation. Deleting the app's `JSESSIONID` does not delete the SSO session cookie at an IdP on another domain; the IdP can log the user right back in without asking for a password.

**SAML/CAS:** similarly, local invalidation does not always mean single logout. Proper protocol integration and session mapping are required. Do not send `Set-Cookie` headers for another domain to attempt deleting IdP cookies not owned by your application.

**Concurrent sessions:** for logout-all, you must track the account's other sessions and invalidate them in the corresponding session store/registry; also handle remember-me and tokens. When using Spring Session Redis/JDBC, verify propagation across nodes and race conditions, rather than claiming "logged out all devices" based on a single POST `/logout`.

**WebSocket/SSE:** long-lived connections can outlive the logout request. The application needs a mechanism to close or re-authorize connections by session or user identity so sensitive data does not continue flowing over an already-open connection.

## 10. Final QA Checklist

- [ ] `POST /logout` with valid CSRF enters `LogoutFilter`; `GET /logout` does not automatically destroy the session when CSRF is enabled.
- [ ] `SecurityContextLogoutHandler` clears the context and invalidates the current `HttpSession`; does not create a new session just to destroy it.
- [ ] `LogoutSuccessHandler` only redirects/returns status after cleanup, and is not treated as a replacement for logout handlers.
- [ ] Response contains `Set-Cookie` expiry for cookies to delete; actual Name/Path/Domain were verified.
- [ ] `JSESSIONID` is destroyed on the server even if the browser/proxy fails to delete the cookie as expected.
- [ ] The remember-me cookie is deleted by its handler; understand that a copy of a hash-based token may still be replayed.
- [ ] Tests verify POST without CSRF is rejected and does not destroy the authenticated session.
- [ ] Tests verify a logged-out session cannot access protected endpoints with the old session on a real Servlet container.
- [ ] Logging out one session does not automatically mean logging out the account's remaining sessions.
- [ ] All secrets/cookies/tokens are protected, never written to audits/logs or shared in screenshots.
- [ ] End-to-end tests cover browser/container/proxy and cookie Path/Domain/Secure/SameSite.
- [ ] If using JWT, OAuth2/OIDC, or SAML, a protocol-specific revocation/SSO logout design is in place.
- [ ] Sensitive data in browser/back cache and long-lived connections are evaluated in the logout flow.

### Official Documentation

- [Spring Security 6.5 — Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Remember-Me Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html)
- [Spring Security 6.5 — SecurityContextLogoutHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/SecurityContextLogoutHandler.html)
- [Spring Security 6.5 — CookieClearingLogoutHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/CookieClearingLogoutHandler.html)
- [Spring Security 6.5 — ClearSiteDataHeaderWriter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/header/writers/ClearSiteDataHeaderWriter.html)
- [Spring Security 6.5 — CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — MockMvc Security Tests](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html)
