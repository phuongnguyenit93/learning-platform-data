# Logout via Redirect for Web or Status Response for API in Spring Security

## 1. Lesson Objectives

Logging out is not merely sending a user to another page or returning an HTTP status code. A cookie/session-based logout flow must **safely clear authentication state**, and only then choose a response suited to the client type.

Two common response styles:

- **Traditional web applications (server-rendered web):** after the user clicks Log out, the server returns an **HTTP 302/303 redirect** to the login page or a signed-out confirmation page. The browser automatically navigates to the new page.
- **APIs for SPAs/mobile/JavaScript:** after completing logout, the server returns **HTTP 204 No Content** (no body) or **HTTP 200 OK** with short JSON. The client updates its UI and decides whether to navigate.

Examples:

~~~http
POST /web/logout HTTP/1.1
Cookie: JSESSIONID=...
X-CSRF-TOKEN: ...

HTTP/1.1 302 Found
Location: /signed-out
~~~

~~~http
POST /api/logout HTTP/1.1
Cookie: JSESSIONID=...
X-CSRF-TOKEN: ...

HTTP/1.1 204 No Content
~~~

**Core point:** a redirect or 204 **is only the post-logout HTTP result**; they are not the session-destruction operation. In Spring Security Servlet, `LogoutFilter` and the `LogoutHandler`s handle cleanup. `LogoutSuccessHandler` only decides the response.

The hands-on lesson uses **Java 17+, Spring Boot 3.x, Spring Security 6.x, Servlet MVC**, combining an HTTP-session-based form login flow with two logout URLs to clearly illustrate the difference. If the app authenticates with stateless bearer JWTs, token revocation differs from destroying a session; section 14 analyzes that separately.

After this lesson, you will be able to:

1. Explain the distinct roles of `LogoutFilter`, `LogoutHandler`, and `LogoutSuccessHandler`.
2. Configure a fixed redirect via `logoutSuccessUrl`/`SimpleUrlLogoutSuccessHandler` for web.
3. Return HTTP 204 via `HttpStatusReturningLogoutSuccessHandler(HttpStatus.NO_CONTENT)` for APIs.
4. Understand why logout requires POST and a CSRF token in apps using browser cookies.
5. Integrate session invalidation, `SecurityContext` clearing, cookie/remember-me cleanup, and post-logout request handling.
6. Avoid open redirects, CORS/SPA errors, 204 responses with a body, and confusing session logout with JWT revocation.
7. Test these conditions with MockMvc and a runnable Spring Security project.

## 2. Which Responsibility Layers Exist in a Logout Flow?

~~~text
                  Browser or SPA
                         |
        POST /web/logout or /api/logout
                         |
                         v
                   SecurityFilterChain
                         |
                         v
          CsrfFilter checks CSRF for POST
                         |
              +----------+----------+
              |                     |
         invalid token          valid token
              |                     |
              v                     v
          403 Forbidden          LogoutFilter
                                    |
                         Does RequestMatcher match?
                                    |
                                    v
                           LogoutHandler chain
                         +----------------------+
                         | invalidate session   |
                         | clear SecurityContext|
                         | clear CSRF token     |
                         | remember-me cleanup  |
                         | custom cleanup if any|
                         +----------------------+
                                    |
                                    v
                           LogoutSuccessHandler
                               /         \
                              /           \
                             v             v
                      WEB response     API response
                       302/303         204 No Content
                       Location        (no body)
                             |             |
                             v             v
                       Browser goes    SPA updates state
                       to page         / navigates
~~~

Important ordering:

- `LogoutFilter` matches the logout URL/method and orchestrates the `LogoutHandler`s.
- `SecurityContextLogoutHandler` typically invalidates `HttpSession`, clears `Authentication` and `SecurityContextHolder`, and cleans up the context repository.
- `CsrfLogoutHandler` deletes the old CSRF token. The next state-changing request will need a token matching the new session.
- If remember-me is enabled, `RememberMeServices` can participate in cleaning up the remember-me cookie.
- `LogoutSuccessHandler#onLogoutSuccess(request, response, authentication)` runs **after** cleanup tasks; it chooses a redirect, status code, or other response.

**Do not equate "HTTP 204" with "all credentials revoked".** 204 only indicates the server reported success at the logout endpoint. Whether any JWTs remain active, whether an OAuth2/OIDC IdP is logged out, or whether the browser holds other cookies must be designed and tested separately.

### Main API of the Success Handler

~~~java
public interface LogoutSuccessHandler {
    void onLogoutSuccess(
        HttpServletRequest request,
        HttpServletResponse response,
        Authentication authentication
    ) throws IOException, ServletException;
}
~~~

`authentication` can be `null` if logout is invoked when there is no logged-in identity. A proper success handler should handle that case safely, especially for idempotent APIs.

## 3. Choosing Responses for Web and API

| Criterion | Server-rendered web | SPA / REST API |
| --- | --- | --- |
| Primary client | Browser with page navigation | `fetch`/Axios/mobile |
| Common result | `302 Found` to `/login?logout` or `/signed-out` | `204 No Content`; sometimes `200 OK` JSON |
| Mechanism in Spring Security | `logoutSuccessUrl` or `SimpleUrlLogoutSuccessHandler` | `HttpStatusReturningLogoutSuccessHandler` |
| Who decides the next screen? | Browser via `Location` | Frontend navigates/updates state itself |
| HTTP body needed? | Usually no, due to redirect | 204 must contain no body |
| CSRF when using cookies | Keep CSRF for POST logout | Keep CSRF if browser sends cookies automatically |
| Actual logout processing | `LogoutHandler` | Those exact `LogoutHandler`s, never skipped |

**Valid 200 JSON case:** the product needs to return `{"status":"logged_out"}` for the app to display a message. Use a custom `LogoutSuccessHandler` writing status 200 and `Content-Type: application/json`. If only indicating success is needed, 204 is usually cleaner and avoids designing a JSON contract.

**Do not create a server-side redirect for an API just because web uses a redirect.** Many HTTP clients auto-follow 302s, causing the logout call to end up receiving the login HTML page; SPAs calling `response.json()` will fail. Conversely, returning 204 to a plain HTML logout form can leave users staring at a blank page instead of returning to an appropriate screen.

## 4. Concise Approach: Web Redirect with logoutSuccessUrl

If the app only has web session login, a concise configuration is:

~~~java
// Place inside SecurityFilterChain, not a standalone runnable file.
http.logout(logout -> logout
    .logoutUrl("/logout")
    .logoutSuccessUrl("/login?logout")
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .permitAll()
);
~~~

When POST `/logout` carries a valid CSRF token, Spring Security runs the logout handler chain then redirects to `/login?logout`. This is a **fixed URL configured by the server**. `/login?logout` only serves as a page displaying a logged-out message, not the cleanup operation itself.

By default Spring Security supports `/logout`, typically redirecting to `/login?logout` on success. With CSRF enabled, `GET /logout` serves a confirmation screen rather than an immediate logout method; the real action should be performed via `POST /logout` with a CSRF token.

### Why Not Use GET to Log Out?

GET is expected to be safe/idempotent in HTTP semantics regarding not intentionally causing state changes. If `GET /logout` destroys the session on its own, an auto-loaded image/link, prefetch, crawler, or external page can log the user out unexpectedly. Moreover, browser cookies can be attached automatically to cross-site requests.

**Recommendation:** use POST with CSRF protection when browsers authenticate via cookies. Do not strip CSRF protection globally just to switch logout to GET.

## 5. Concise Approach: API Logout Returning Status

For an API based on session cookies, you can use:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.security.web.authentication.logout
    .HttpStatusReturningLogoutSuccessHandler;

// Configuration snippet inside SecurityFilterChain:
http.logout(logout -> logout
    .logoutUrl("/api/logout")
    .logoutSuccessHandler(
        new HttpStatusReturningLogoutSuccessHandler(
            HttpStatus.NO_CONTENT))
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .permitAll()
);
~~~

In real Java code, imports must be **on a single line**:

~~~java
import org.springframework.security.web.authentication.logout.HttpStatusReturningLogoutSuccessHandler;
~~~

The no-arg constructor of `HttpStatusReturningLogoutSuccessHandler` defaults to returning **HTTP 200 OK**. To return **204**, explicitly pass `HttpStatus.NO_CONTENT`. Do not mistake the default instance as returning 204.

A 204 success handler must not write JSON:

~~~java
LogoutSuccessHandler noContent = (request, response, authentication) -> {
    response.setStatus(HttpServletResponse.SC_NO_CONTENT);
    // Do not call getWriter().write(...).
};
~~~

**HTTP 204 has no message body.** If the frontend calls `await response.json()` on a 204 response, it may hit a parse error. Instead check `response.status === 204` or `response.ok` and do not read a body.

Depending on the system, 200 JSON can be chosen, for example:

~~~java
LogoutSuccessHandler jsonSuccess = (request, response, authentication) -> {
    response.setStatus(HttpServletResponse.SC_OK);
    response.setContentType("application/json");
    response.getWriter().write("{\"status\":\"logged_out\"}");
};
~~~

This is an illustrative handler snippet and does not clean up the session itself; it only changes how the response is returned **after** the logout handler chain.

## 6. What Does Default Logout Configuration Actually Clear?

In Spring Security 6.5 Servlet, on successful logout, the configured handlers typically execute:

1. **Invalidate the HTTP session** so the session is no longer valid.
2. **Clear `SecurityContextHolderStrategy`** and clean up `SecurityContextRepository`.
3. **Clean up the remember-me cookie** if a corresponding remember-me mechanism was configured.
4. **Remove the CSRF token** bound to the session or repository.
5. **Publish `LogoutSuccessEvent`** so other components can observe it when appropriate.

An application can add a custom `LogoutHandler` for other caches/server-side state. However, logout handlers should focus on cleanup and **avoid throwing exceptions** during cleanup whenever possible; the success handler is the proper place to decide the redirect/response.

**Note on `JSESSIONID`:** once `HttpSession` is invalidated, the old session ID can no longer regain authenticated content. The browser may still show a `JSESSIONID` cookie in some environments until updated/deleted. The cookie's presence does not prove the server-side session is still valid. Spring Security docs also note it is not strictly necessary to configure `deleteCookies("JSESSIONID")` when the session is invalidated; if custom cookies exist, delete them with matching domain/path.

**Stateless remember-me:** deleting the remember-me cookie on the current browser does not revoke **a stolen copy of the signed cookie**. When per-token or per-device revocation is needed, look into a persistent-token/revocation mechanism.

**Clear-Site-Data:** you can add a `HeaderWriterLogoutHandler` with `ClearSiteDataHeaderWriter` to ask the browser to clear cookies/site data. Consider scope (especially `Directive.ALL`, which can wipe app caches/storage) and browser support; do not treat this header as a way to revoke tokens on other devices.

## 7. Complete Example: One Application with Both Web Redirect and API 204

Demo goals:
- Standard form login `POST /login` using in-memory username/password, BCrypt, and HTTP session.
- `GET /web/home` page containing a `POST /web/logout` form with CSRF token.
- `POST /web/logout` invalidates the session and redirects to fixed `/signed-out`.
- `POST /api/logout` invalidates the session via the **same cleanup mechanism**, returning `204 No Content`.
- `GET /api/me` serves only logged-in users; without a session it returns **401** instead of an HTML redirect.
- `GET /api/csrf` returns the CSRF token for frontend/API session clients.
- `POST /api/logout` with missing/invalid CSRF token returns **403** before reaching the logout handlers.

Both logout paths use **a single `LogoutFilter`** with a matcher covering both paths. The success handler routes based on the **server-configured path**, not on client-supplied `next` query params or `Referer`.

### 7.1. Project Structure

~~~text
dual-logout-demo/
├── pom.xml
└── src/
    ├── main/java/demo/logout/DualLogoutApplication.java
    └── test/java/demo/logout/DualLogoutApplicationTests.java
~~~

`pom.xml` for Java 17 and Spring Boot 3.5.7 (managing Spring Security 6.5.x):

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>dual-logout-demo</artifactId>
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
~~~

When building a real product, use a maintained Spring Boot/Spring Security branch with appropriate patches. The example pins a version to illustrate Spring Security 6.x APIs; never use demo passwords in production.

### 7.2. Application Code

Create `src/main/java/demo/logout/DualLogoutApplication.java`:

~~~java
package demo.logout;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.HttpStatusReturningLogoutSuccessHandler;
import org.springframework.security.web.authentication.logout.LogoutSuccessHandler;
import org.springframework.security.web.authentication.logout.SimpleUrlLogoutSuccessHandler;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.security.web.util.matcher.OrRequestMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DualLogoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(DualLogoutApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        // For web forms: redirect to a FIXED URL.
        SimpleUrlLogoutSuccessHandler webRedirect =
            new SimpleUrlLogoutSuccessHandler();
        webRedirect.setDefaultTargetUrl("/signed-out");
        webRedirect.setAlwaysUseDefaultTargetUrl(true);

        // For APIs: HTTP 204, strictly no body.
        HttpStatusReturningLogoutSuccessHandler apiNoContent =
            new HttpStatusReturningLogoutSuccessHandler(
                HttpStatus.NO_CONTENT);

        // Single LogoutFilter for both URLs. Route based on
        // known servlet path, NOT client-supplied next/returnUrl.
        LogoutSuccessHandler responseByRoute =
            (request, response, authentication) -> {
                String path = request.getServletPath();

                if ("/api/logout".equals(path)) {
                    apiNoContent.onLogoutSuccess(
                        request, response, authentication);
                } else if ("/web/logout".equals(path)) {
                    webRedirect.onLogoutSuccess(
                        request, response, authentication);
                } else {
                    response.sendError(
                        HttpServletResponse.SC_NOT_FOUND);
                }
            };

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/login", "/signed-out", "/api/csrf"
                ).permitAll()
                .requestMatchers(
                    HttpMethod.POST, "/login", "/web/logout", "/api/logout"
                ).permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                // Default login page GET /login generated by Spring Security.
                .defaultSuccessUrl("/web/home", true)
                .permitAll()
            )
            // Unauthenticated API request -> 401 instead of HTML redirect.
            .exceptionHandling(ex -> ex.defaultAuthenticationEntryPointFor(
                (request, response, error) ->
                    response.sendError(
                        HttpServletResponse.SC_UNAUTHORIZED),
                new AntPathRequestMatcher("/api/**")
            ))
            .requestCache(cache ->
                cache.requestCache(new NullRequestCache()))
            .logout(logout -> logout
                .logoutRequestMatcher(new OrRequestMatcher(
                    new AntPathRequestMatcher(
                        "/web/logout", "POST"),
                    new AntPathRequestMatcher(
                        "/api/logout", "POST")
                ))
                // Cleanup managed by Spring Security LogoutHandlers.
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .logoutSuccessHandler(responseByRoute)
                .permitAll()
            );
        // Do not disable CSRF: enabled by default for POST login/logout.
        return http.build();
    }

    @RestController
    static class DemoController {

        @GetMapping("/api/csrf")
        Map<String, String> csrf(HttpServletRequest request) {
            // CsrfFilter stores the token as a request attribute.
            CsrfToken token = (CsrfToken) request.getAttribute(
                CsrfToken.class.getName());

            return Map.of(
                "headerName", token.getHeaderName(),
                "token", token.getToken());
        }

        @GetMapping("/api/me")
        Map<String, String> me(
                org.springframework.security.core.Authentication auth) {
            return Map.of("username", auth.getName());
        }

        @GetMapping(
            value = "/web/home",
            produces = MediaType.TEXT_HTML_VALUE
        )
        String webHome(HttpServletRequest request) {
            CsrfToken token = (CsrfToken) request.getAttribute(
                CsrfToken.class.getName());

            // Demo runs at context path "/".
            // Production should render forms via an escaping template engine.
            return "<!doctype html><html><body>"
                + "<h1>Logged in</h1>"
                + "<form action='/web/logout' method='post'>"
                + "<input type='hidden' name='"
                + token.getParameterName()
                + "' value='"
                + token.getToken()
                + "'>"
                + "<button type='submit'>Log out</button>"
                + "</form></body></html>";
        }

        @GetMapping(
            value = "/signed-out",
            produces = MediaType.TEXT_HTML_VALUE
        )
        String signedOut() {
            return "<!doctype html><html><body>"
                + "<h1>You have been logged out</h1>"
                + "<a href='/login'>Log in again</a>"
                + "</body></html>";
        }
    }
}
~~~

### 7.3. Code Details to Notice

**Do not create a `@PostMapping("/api/logout")` endpoint to manually clear a few variables.** Both `POST /web/logout` and `POST /api/logout` are handled by `LogoutFilter` **before the request reaches a Spring MVC controller**. Using the DSL keeps standard LogoutHandlers such as session/context and CSRF cleanup.

**Matcher accepts only POST.** `OrRequestMatcher` contains exactly two `AntPathRequestMatcher`s with method `POST`. Hence `GET /api/logout` or `GET /web/logout` are not logout operations. Paths must be tightly controlled rather than relying on `Referer` or `Accept` to decide whether to destroy the session.

**Post-logout responses are separated.** `responseByRoute` only runs once the logout handler chain finishes. For `/api/logout` it calls `apiNoContent`, and for `/web/logout` it calls `webRedirect`. One `LogoutFilter` performs the same cleanup, differing only in how it responds.

**Fixed redirect:** `webRedirect.setDefaultTargetUrl("/signed-out")` and `setAlwaysUseDefaultTargetUrl(true)`. The target is not read from `next` or `returnUrl` query parameters. `/signed-out` is a server-controlled page and must remain accessible after the session is deleted.

**Dedicated 401 for API:** `exceptionHandling.defaultAuthenticationEntryPointFor` handles unauthenticated requests to `/api/**` with HTTP 401. Without this configuration, `formLogin` could send API clients a redirect to the HTML login screen, which is awkward for SPAs.

**Form page:** `/web/home` renders the POST/logout form and hidden CSRF field; this example assumes the app runs at the root context path. For production web apps, use an escaping template engine, handle context path/locale, display proper messages, and never concatenate HTML from untrusted user input.

**CSRF token must remain valid on logout:** POST logout uses the token freshly fetched from the active session. After logout, the old CSRF token/session are cleared so that token should not be reused on subsequent POSTs.

**HTTP 204:** the handler only writes the status code and writes no JSON body. For SPAs, clear client-side state/cache yourself and navigate via the router if needed.

**Do not rely on immediate Set-Cookie deletion.** Server-side session invalidation is enough to strip privileges from the old session ID. In multi-instance environments, use a shared session store or sticky routing; avoid assuming a `JSESSIONID` cookie can regain context after logout.

## 8. Manual Walkthrough

### 8.1. Startup

In the project directory (with Java 17+ and Maven installed):

~~~bash
mvn test
mvn spring-boot:run
~~~

`mvn test` runs the integration tests below. `mvn spring-boot:run` starts the server, defaulting to `http://localhost:8080` unless reconfigured. Do not run `javac DualLogoutApplication.java` standalone without the Spring Security/Spring Boot/Jakarta Servlet classpath.

### 8.2. Browser Login (Web Flow)

Open:

~~~text
http://localhost:8080/login
~~~

Spring Security automatically renders the default login page. Log in with:
- Username: `student`
- Password: `demo-password`

On success, the browser is sent to `/web/home`. This page contains a `POST /web/logout` form with a server-issued CSRF token. Click **Log out**; the browser receives a `302` redirect (exact status depends on redirect strategy) to `/signed-out` and sees the signed-out message.

Try opening `/web/home` again after logout: because the old session no longer has authentication, Spring Security prompts for login again.

### 8.3. API Session Login and Logout via curl

First fetch a CSRF token and session cookie:

~~~bash
curl -i -c cookies.txt http://localhost:8080/api/csrf
~~~

The JSON response looks like:

~~~json
{"headerName":"X-CSRF-TOKEN","token":"<actual-token>"}
~~~

This is just an example structure. Use the **actual token value** from the server, not the literal bracketed text.

Submit form login, preserving cookies:

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'X-CSRF-TOKEN: <actual-token>' \
  --data-urlencode 'username=student' \
  --data-urlencode 'password=demo-password' \
  http://localhost:8080/login
~~~

If credentials are valid, the login filter returns a redirect to `/web/home` and the session cookie is set/updated. Because the demo uses a shared form flow, an API client can log in via form and then call the API with the same session cookie.

Verify the session before logout:

~~~bash
curl -i -b cookies.txt http://localhost:8080/api/me
~~~

Expected:

~~~json
{"username":"student"}
~~~

**Fetch a fresh CSRF token after logging in** using the active cookie:

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  http://localhost:8080/api/csrf
~~~

The pre-login token may have been cleared/rotated by the session strategy. Send API logout:

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -X POST http://localhost:8080/api/logout \
  -H 'X-CSRF-TOKEN: <actual-new-token>'
~~~

Expected status:

~~~http
HTTP/1.1 204 No Content
~~~

No body. Next request using the old session:

~~~bash
curl -i -b cookies.txt http://localhost:8080/api/me
~~~

Expected **HTTP 401 Unauthorized** (or the session cookie is meaningless and the endpoint requires re-authentication). Do not assert that the browser must physically delete every cookie immediately solely based on this response; checking the auth state is what matters.

### 8.4. Comparing Web Redirect

With a logged-in session and current CSRF token, if you send:

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -X POST http://localhost:8080/web/logout \
  -H 'X-CSRF-TOKEN: <current-token>'
~~~

Expect `302 Found` (or appropriate 3xx redirect) and:

~~~http
Location: /signed-out
~~~

`curl -i` does not follow `Location` by default; browsers usually do. Do not run both logouts sequentially on **the same already-destroyed session** and treat it as a comparison from the same state. To test web logout independently, log in again/create a new session.

## 9. Testing with MockMvc

Test both the **returned response** and the **session-clearing action**, because 204/302 is only an HTTP response. The following tests run with Spring Security Test and the Spring Boot app from section 7.

File `src/test/java/demo/logout/DualLogoutApplicationTests.java`:

~~~java
package demo.logout;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DualLogoutApplicationTests {

    @Autowired
    MockMvc mvc;

    private MockHttpSession loginSession() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "demo-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/web/home"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);

        assertNotNull(session);
        return session;
    }

    @Test
    void webLogoutRedirectsToFixedPageAndInvalidatesSession()
            throws Exception {

        MockHttpSession session = loginSession();

        mvc.perform(post("/web/logout")
                .session(session)
                .with(csrf())
                .param("next", "https://evil.example"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/signed-out"));

        assertTrue(session.isInvalid());
    }

    @Test
    void apiLogoutReturns204WithNoBodyOrRedirect()
            throws Exception {

        MockHttpSession session = loginSession();

        mvc.perform(post("/api/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().isNoContent())
            .andExpect(content().string(""))
            .andExpect(header().doesNotExist("Location"));

        assertTrue(session.isInvalid());
    }

    @Test
    void apiLogoutWithoutCsrfIsRejectedBeforeCleanup()
            throws Exception {

        MockHttpSession session = loginSession();

        mvc.perform(post("/api/logout").session(session))
            .andExpect(status().isForbidden());

        assertFalse(session.isInvalid());
        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk());
    }

    @Test
    void webLogoutWithoutCsrfIsRejectedBeforeCleanup()
            throws Exception {

        MockHttpSession session = loginSession();

        mvc.perform(post("/web/logout").session(session))
            .andExpect(status().isForbidden());

        assertFalse(session.isInvalid());
    }

    @Test
    void getApiLogoutDoesNotPerformLogout() throws Exception {
        MockHttpSession session = loginSession();

        mvc.perform(get("/api/logout").session(session))
            .andExpect(status().isNotFound());

        assertFalse(session.isInvalid());
        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk());
    }

    @Test
    void afterApiLogoutNewUnauthenticatedRequestGets401()
            throws Exception {

        MockHttpSession session = loginSession();

        mvc.perform(post("/api/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().isNoContent());

        assertTrue(session.isInvalid());
        // Use a new request without carrying the old session.
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void signedOutPageIsPublic() throws Exception {
        mvc.perform(get("/signed-out"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                org.hamcrest.Matchers.containsString("logged out")));
    }

    @Test
    void csrfEndpointIsPublic() throws Exception {
        mvc.perform(get("/api/csrf"))
            .andExpect(status().isOk());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**Expectation after creating the files properly and downloading dependencies:** 8 tests pass in a compatible environment. The tests above are practice samples, **not results already executed** in the learner's environment.

### Tested Invariants

| Test | Invariant |
| --- | --- |
| `webLogoutRedirectsToFixedPageAndInvalidatesSession` | Always redirects to `/signed-out`, ignores client `next`, session destroyed |
| `apiLogoutReturns204WithNoBodyOrRedirect` | API 204 has no body and no `Location` header |
| `apiLogoutWithoutCsrfIsRejectedBeforeCleanup` | Invalid/missing CSRF must not unintentionally log out the user |
| `webLogoutWithoutCsrfIsRejectedBeforeCleanup` | Web form similarly requires CSRF |
| `getApiLogoutDoesNotPerformLogout` | GET is not misconfigured as logout |
| `afterApiLogoutNewUnauthenticatedRequestGets401` | New request without session does not auto-authenticate |
| `signedOutPageIsPublic` | Post-logout target page does not require a session |
| `csrfEndpointIsPublic` | Client can fetch a token to send a valid POST |

For stricter production testing, also test cookie domain/path, remember-me, session fixation, OIDC SSO, multi-node logout, cache state, and scenarios where the client sends a JWT alongside cookies.

**Session test limitation:** `MockHttpSession.isInvalid()` proves the session was invalidated in the MockMvc environment. To verify real cookies, CORS, redirects, and reverse proxies, run additional end-to-end tests with a browser or real HTTP client.

## 10. React, Vue, Angular, and fetch: Handling 204 Responses Properly

For an SPA authenticating via session cookies, a flow can be:

~~~javascript
async function logout() {
  // This token was fetched by the app from the /api/csrf endpoint.
  const csrfToken = getCsrfTokenFromAppState();

  const response = await fetch("/api/logout", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRF-TOKEN": csrfToken
    }
  });

  if (response.status !== 204) {
    throw new Error("Logout did not complete");
  }

  // Do not call response.json() because HTTP 204 has no body.
  clearSensitiveClientState();
  window.location.assign("/signed-out");
}
~~~

This is an **illustrative snippet**, not a standalone JS file: `getCsrfTokenFromAppState` and `clearSensitiveClientState` are SPA functions to implement in your app. In cross-origin environments, configure `credentials`, CORS, `SameSite`, and HTTPS per policy. `credentials: "include"` should only be used when needed and when the server has an accurate origin allowlist.

Clear/reset client-side state after the server confirms logout: user profile cache, UI auth flags, sensitive in-memory data, WebSocket subscriptions, or query caches holding user data. Do not treat `window.location = "/login"` on the frontend as logout itself; the server session may still remain.

**Regarding 3xx redirects:** `fetch` may follow redirects by default, so the final `response.status` could be 200 for an HTML page instead of 302 from logout. When an API expects JSON/status, configure `LogoutSuccessHandler` to return 204 instead of relying on web redirects. Avoid trying to parse an HTML response as JSON.

### When to Return 200 JSON Instead of 204?

200 can be used:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"logged_out"}
~~~

If the frontend contract needs to display a message from the server, that is a reasonable choice. However, 200 JSON does not mean cleanup differs from 204. Both must go through standard LogoutHandlers and meet the same auth/security requirements.

### Should Logout Return 401 If the User's Session Already Expired?

There is no single answer; many APIs choose **idempotent** logout: sending a valid POST after the session expired still returns 204, because the end state is "no longer authenticated". Depending on the product, authentication may be required to handle specific token revocation. With Spring Security's logout DSL, `LogoutFilter` sits before `AuthorizationFilter` and can process logout even when `Authentication` is null. Even so, CSRF for cookie-based logout still needs proper design.

Do not return account, session, or token details in the logout response if the client is not authorized to know them.

## 11. Why Use LogoutFilter Instead of Writing Your Own Logout Controller?

A seemingly simple controller:

~~~java
// Insufficient for secure logout:
@PostMapping("/api/logout")
public ResponseEntity<Void> logout() {
    return ResponseEntity.noContent().build();
}
~~~

The snippet above only returns 204—it does not invalidate `HttpSession`, clear `SecurityContextHolder`, clean up the repository, or handle remember-me and CSRF. The user may still be treated as authenticated on the next request.

If you are forced to write a custom controller, invoke the appropriate logout handlers such as `SecurityContextLogoutHandler` and handle other tasks per policy, though it is easy to miss components. Spring Security officially recommends using `http.logout(...)`, and registering `addLogoutHandler(...)` if extra cleanup actions are needed.

Example of adding your own application cleanup:

~~~java
// Illustration: serverCacheService is an application-defined service.
LogoutHandler cleanup = (request, response, authentication) -> {
    if (authentication != null) {
        serverCacheService.evictFor(authentication.getName());
    }
};

http.logout(logout -> logout
    .addLogoutHandler(cleanup)
    .logoutSuccessHandler(
        new HttpStatusReturningLogoutSuccessHandler(
            HttpStatus.NO_CONTENT))
);
~~~

This is **not a standalone code snippet**; `serverCacheService` must be implemented. A cleanup handler should not arbitrarily write a success response, nor throw runtime exceptions that prevent other handlers from running. Design behavior for when the cache backend fails.

## 12. Choosing a Fixed Redirect and Preventing Open Redirects

A user may ask to log out and return to a specific page. However, if the app trusts a `returnUrl` / `next` query parameter, an attacker can craft a link:

~~~text
https://app.example.com/web/logout?next=https://evil.example
~~~

If the server uses that value as `Location` after logout, the browser is sent to an attacker-controlled domain. This is an **open redirect (CWE-601)**, which can amplify phishing effectiveness right after logout.

Common dangerous values:
- `https://evil.example/login` — absolute URL to another host.
- `//evil.example/path` — network-path URL switching to another host.
- `https://app.example.com.evil.example/` — lookalike host that is not yours.
- URLs with userinfo or unusual encoding that bypass prefix checks.
- Path traversal and encoded-slash variants if the app concatenates paths manually.

**Best default solution:** do not let the client choose the logout destination; use `logoutSuccessUrl("/signed-out")` or a handler with `setDefaultTargetUrl("/signed-out")` and `setAlwaysUseDefaultTargetUrl(true)`. These are server-decided URLs.

If the product strictly requires dynamic redirects, allow only valid internal paths or an origin/host allowlist checked after parsing/canonicalizing the URL. Do not check `startsWith("https://app.example.com")`; the host `app.example.com.evil.example` passes weak prefix checks.

**Additional note:** using HTTP `Referer` to determine the return page is unsafe because the header can be missing, controlled, or cross-origin. Do not default to redirecting users to the `Referer` URL after logout.

## 13. CSRF, Cookies, Caching, and Easily Overlooked States

### 13.1. CSRF on POST Logout

When the browser automatically sends session cookies, another page can try to force a request that logs the user out (logout CSRF). Spring Security enables CSRF by default for unsafe methods such as POST.

- `GET /logout` in the default flow with CSRF is typically a **confirmation page**, not the action.
- `POST /logout` or custom `POST /web/logout`/`POST /api/logout` requires a valid CSRF token.
- If the token is missing: `CsrfFilter` typically returns **403 Forbidden**, and logout handlers **do not run**.
- Do not remove CSRF globally just to make APIs easier to call if the frontend relies on cookies.

If an API is truly stateless and only uses bearer tokens in `Authorization`, the CSRF policy can differ. That is not a justification to disable CSRF for cookie-based web routes.

### 13.2. Cookies and Client State

Logout may destroy the server session while the browser still holds old cookies in storage. Deleting additional custom cookies works only when `Path` and `Domain` match; otherwise the browser keeps cookies under another scope.

**Remember-me:** if `rememberMe` is enabled, logout config should include remember-me token/cookie cleanup. With signed stateless remember-me, a stolen copy can remain valid until expiry/key/password-hash changes; individual copies cannot be revoked merely via HTTP 204/302.

**CSRF token:** after logout, the old session and CSRF token may have been cleared; the app should fetch a new token before making the next POST.

### 13.3. Browser Back Button and Caching

After logout, the browser may display previous page content from history/Back-Forward Cache without contacting the server. This **does not mean** the user still has API permissions after logout. Nevertheless, sensitive content should not be cached publicly and the UI should hide/refresh state after logout.

Spring Security includes default security response headers supporting cache-control for many responses. For sensitive data, verify cache headers and reverse proxies separately, and clear client-side caches as appropriate.

### 13.4. Multiple Tabs and Race Conditions

One tab may have just logged out while another tab still shows a "logged in" UI. The next request from that tab must be blocked once the session is invalidated. For multi-tab SPAs, `BroadcastChannel` or a similar mechanism can sync UI state; this is a UX optimization, not a replacement for server-side checks.

### 13.5. Multiple Devices, Multiple Sessions

Normal logout destroys the **current session**, not necessarily every session for the account across all devices. If a "log out all devices" feature is required, you need `SessionRegistry`/shared session store/revocation or a user-session version, along with race and multi-instance testing.

## 14. Stateless APIs, Bearer JWTs, and What Logout Means

This is an important distinction:

~~~text
Session cookie authentication:
  logout -> invalidate HttpSession / clear SecurityContext
         -> requests using old session are no longer authenticated

Bearer JWT authentication:
  logout -> delete token on client?
         -> server may still accept unexpired JWT
            without revocation / introspection / other policy
~~~

With a stateless JWT Resource Server, default `http.logout(...)` cannot "delete" access tokens already issued by the authorization server merely by invalidating `HttpSession` (the app may not even use sessions).

Make explicit decisions:
- If the client uses short-lived access tokens and no refresh tokens, client-side logout may just delete the held token; a stolen token can still be used until expiration.
- If refresh tokens exist, revoke the refresh token/refresh-token family or apply another server-side mechanism per the authorization server.
- If a token must be revoked immediately, use token introspection, a TTL denylist, token versioning, or a suitable mechanism; consider load, consistency, and scalability.
- With OAuth2/OIDC SSO, logging out of the local app **does not automatically log out of the identity provider**. Design RP-initiated logout/Single Logout if policy requires it, such as `OidcClientInitiatedLogoutSuccessHandler` in Spring Security client.
- After browser logout, an active IdP session can still cause "passwordless" re-login via SSO; that is the IdP's state, not necessarily a still-alive local session.

Therefore, an API returning `204 No Content` should be understood according to the endpoint's actual contract: what local session it deleted or what token revocation it performed, never claiming "all credentials are invalidated" unless the system implements it.

## 15. Multiple SecurityFilterChains and Logout URLs

An app may use two chains:
- `/web/**`: form login, session, and redirect logout.
- `/api/**`: session-based API with status responses, or stateless bearer JWT with its own policy.

When configuring `securityMatcher`, ensure the logout URL is covered by the **right chain** and that chain's logout filter. For instance, a chain matching only `/api/**` will not process `/logout` if the URL falls outside its scope. This is a common mistake when upgrading from one chain to multiple chains.

Short example configuration for an API chain (illustrative only, lacking full beans/matchers for a standalone project):

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .logout(logout -> logout
            .logoutUrl("/api/logout")
            .logoutSuccessHandler(
                new HttpStatusReturningLogoutSuccessHandler(
                    HttpStatus.NO_CONTENT)));
    return http.build();
}
~~~

In a real environment, configure form login, csrf/exception handling, method security, and a separate web chain if needed. **Do not** apply an inappropriate `AuthenticationManager`/session policy across different mechanisms just because they share an app.

The main example uses **one chain + two logout request matchers** so learners see the same cleanup split into two response styles without needing multiple chains.

## 16. Error Handling, HTTP Statuses, and Idempotency

| Case | Typical Response | Notes |
| --- | --- | --- |
| Web POST logout with valid CSRF | 302/303 to chosen page | Handler decides redirect |
| API POST logout with valid CSRF | 204 No Content | Do not write a JSON body |
| API logout needing JSON contract | 200 OK + JSON | Use only when the client needs a body |
| Missing/invalid CSRF in cookie flow | 403 Forbidden | Usually blocked by `CsrfFilter` before LogoutFilter |
| API GET logout in the example | Does not run logout; may return 404 | Do not cause side effects via GET |
| API GET resource after logout | 401 Unauthorized | No authenticated session remaining |
| Web GET protected page after logout | Redirect to login | Handled by form login entry point |
| Logout when session already expired | Usually 204 or normal redirect | Can be idempotent, depending on contract |
| Logout via bearer JWT without revocation | Status does not prove JWT is invalid | Must verify auth server/resource server |

For APIs, many teams want **idempotent** logout: calling it twice yields the same final outcome "logged out". That makes frontend retry/reconnect handling easier. However, do not enable unbounded retries, and a request missing a CSRF token must still be handled per security policy even if the session has expired.

There is no need to return fields containing username, token, session ID, or sensitive specifics after logout. If auditing is needed, log the event using safe codes and correlation IDs, avoiding logging cookies/Authorization headers.

## 17. Common Mistakes

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Only `return "redirect:/login"` in a controller | Session and SecurityContext may remain | Use `http.logout(...)` or invoke proper LogoutHandlers |
| Only `return ResponseEntity.noContent()` | 204 without actually logging out | Ensure `LogoutFilter` handles it before the response |
| API uses default logout redirecting to login HTML | SPA follows redirect, JSON parse fails | `HttpStatusReturningLogoutSuccessHandler(NO_CONTENT)` |
| Web form logout returns 204 | Browser displays a blank page | Redirect to a valid post-logout page |
| Setting `logoutSuccessUrl` directly from `next` | Open redirect | Fixed target or server-side allowlist |
| Allowing GET to destroy the session directly | Logout CSRF, prefetch causes unintended logout | POST with CSRF |
| Disabling CSRF just because frontend uses JSON | Cookies still attach automatically in some contexts | Keep CSRF per threat model |
| Returning 204 and writing a JSON body | Breaks HTTP semantics; hard for clients | Empty body for 204, 200 when returning JSON |
| Frontend calls `response.json()` on 204 | Parse error | Do not read body for 204 |
| Calling `location.href="/login"` without POST logout | Server session stays alive | Call logout API before changing route |
| Logging `Cookie`/`Authorization` during logout | Credential leak | Redact secrets, log audit metadata |
| Assuming JS cookie deletion logs out server | Server session can remain alive | Invalidate server session |
| Assuming session-only logout covers all SSO | IdP may still hold a session | RP-initiated logout / Single Logout when needed |
| Assuming client JWT deletion revokes the token | Unexpired JWT remains usable | Token revocation/introspection/TTL per policy |
| Not permitting `/signed-out` page | Redirects to a page that demands login again | Permit the destination page |
| Wrong `securityMatcher` across multiple chains | LogoutFilter never runs on intended URL | Verify chain, URL/method, and ordering |
| Custom cookie deleted with wrong path/domain | Browser keeps sending old cookie | Use matching cookie scope |
| Not testing session invalidation | UI looks logged out yet old cookie still authenticates | Test post-logout protected request |
| SessionRegistry lives on only one node | Logout on node A fails to update node B properly | Proper shared session store/registry architecture |

## 18. Production Review Checklist

- [ ] Clear decision on whether the client receives a redirect or HTTP status, not guessed from untrusted `Accept` headers.
- [ ] Logout URL/method has an exact matcher and belongs to the right `SecurityFilterChain`.
- [ ] Logout is executed by `LogoutFilter`/LogoutHandlers, not merely returning 204/302 from a controller.
- [ ] `SecurityContextLogoutHandler` invalidates the session and clears context per policy.
- [ ] If remember-me is used, the corresponding cookie/token cleanup mechanism runs.
- [ ] For cookie-based login, POST logout requires a valid CSRF token.
- [ ] Web redirect uses a server-controlled target; no open redirect is exposed.
- [ ] Post-logout page is accessible without a session.
- [ ] API 204 contains no body/JSON and no `Location` header.
- [ ] SPA handles 204 safely and clears auth state/cache after successful logout.
- [ ] Unauthenticated APIs receive 401 per contract instead of an HTML login page where needed.
- [ ] Tests cover successful logout, CSRF 403, GET not logging out, session invalidated, and protected resources blocked after logout.
- [ ] With SSO/OIDC/SAML, separate policies exist for local logout and IdP logout.
- [ ] With JWT bearer tokens, revocation/refresh/access-token expiry policies are independent of HTTP session.
- [ ] Cookies and session stores work consistently across load balancers, proxies, and multiple instances.
- [ ] Cookies/sessions/tokens are never logged; site data/caches are cleared appropriately.
- [ ] Procedures exist for log out all devices or account compromise if required by the product.

## 19. Self-Check Questions

1. Does `LogoutSuccessHandler` invalidate `HttpSession` in place of `LogoutHandler`?
2. Why can the same logout cleanup be shared between a web redirect and an API 204?
3. How does `logoutSuccessUrl("/signed-out")` differ from `HttpStatusReturningLogoutSuccessHandler(HttpStatus.NO_CONTENT)`?
4. What status does the no-arg constructor of `HttpStatusReturningLogoutSuccessHandler` return by default?
5. Why might an SPA calling `response.json()` after 204 fail?
6. Why are POST and a CSRF token needed for logout when using session cookies?
7. Why is returning HTTP 302/204 from a controller without invoking logout handlers insufficient?
8. Why must `/signed-out` be permitted without logging in?
9. Why should `next=https://evil.example` never determine `Location` after logout?
10. After logout, does seeing `JSESSIONID` still present in the browser prove the session still exists on the server?
11. Why cannot session logout automatically revoke already-issued JWT access tokens?
12. Does local logout in OIDC automatically log out of the IdP?
13. When using two `SecurityFilterChain`s, why can `securityMatcher` cause a logout URL to stop working?
14. How do you test that a request missing a CSRF token does not accidentally log the user out?
15. In an idempotent logout API, when is returning 204 despite having no session reasonable?

## 20. References

1. Spring Security 6.5 — Handling Logouts (LogoutFilter, LogoutHandler, custom success handler, CSRF): https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
2. Spring Security 6.5 API — `LogoutSuccessHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/LogoutSuccessHandler.html
3. Spring Security 6.5 API — `HttpStatusReturningLogoutSuccessHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/HttpStatusReturningLogoutSuccessHandler.html
4. Spring Security 6.5 API — `SimpleUrlLogoutSuccessHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/SimpleUrlLogoutSuccessHandler.html
5. Spring Security 6.5 API — `SecurityContextLogoutHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/SecurityContextLogoutHandler.html
6. Spring Security 6.5 API — `LogoutConfigurer`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/LogoutConfigurer.html
7. Spring Security 6.5 — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
8. Spring Security 6.5 — MockMvc testing: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html
9. Spring Security 6.5 — Java Configuration with multiple filter chains: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
10. OWASP — Unvalidated Redirects and Forwards Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html

**Takeaway:** In Spring Security Servlet, **logout handlers clean up state**, while the **logout success handler chooses the response**. Web typically needs a fixed redirect so the browser navigates; APIs typically need a bodyless 204 so the frontend updates its UI. Both must ensure logout actually happens, preserve CSRF when using cookies, and never confuse session logout with token/SSO revocation.