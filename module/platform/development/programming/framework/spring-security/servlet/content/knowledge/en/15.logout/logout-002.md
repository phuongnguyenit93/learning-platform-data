# `logoutUrl`, HTTP Method, and CSRF Requirements for Logout

> **Learning scope:** Spring Security **Servlet stack**, Java 17+, Spring Boot 3.x, and Spring Security 6.x. The focus is on configuring `logoutUrl`, which HTTP method is actually allowed to trigger a logout event, the role of `CsrfFilter`, and how to test so that **GET does not alter authentication state**, **POST without a valid CSRF token is not allowed to log out**, and **POST with a valid token clears the session/security context per policy**. The Spring example requires a Boot project with the right dependencies; there is a standalone Java 17 program at the end to practice the rule.

## 1. Why Is a “Log Out” Button a Security Issue?

In a Servlet application using form login and `HttpSession`, a successful login typically stores a `SecurityContext` so subsequent requests carrying the session cookie can be recognized as authenticated. Logging out is a **state-changing** operation: it removes authentication, may invalidate the session, cleans up cookies/tokens, and directs the user to an appropriate page.

If an application allows logging out via just `GET /logout`, an external website could cause a logged-in user's browser to load that URL automatically (via a link, image, redirect, or embedded content, depending on browser policies). The user is forced to log out without actively requesting it. This is a form of **logout CSRF**; it usually affects availability/UX and can become more severe in flows involving account switching or authentication confusion.

Risk example:

~~~html
<!-- Example of behavior to PREVENT, not how to implement logout -->
<img src="https://app.example.test/logout" alt="">
~~~

`GET` should mean **reading a resource**; a GET merely to view a logout confirmation page should not invalidate the session by itself. For cookie-based websites, the common safe rule is **logout via POST with a valid CSRF token**.

Note: CSRF is not a cure-all for every session issue. It does not replace HTTPS, `Secure`/`HttpOnly` cookies, XSS prevention, session fixation protection, session limits, external token management, or identity-provider refresh-token handling.

## 2. Three Configurations to Distinguish

In Spring Security's `HttpSecurity.logout(...)`:

- `logoutUrl("/signout")`: specifies the **path that `LogoutFilter` processes to execute logout**, not the destination redirected to after logout.
- `logoutSuccessUrl("/login?logout")`: specifies the **redirect destination after a successful logout**; it belongs to the response, not triggering logout.
- `logoutRequestMatcher(...)`: replaces the logout-request matching mechanism, including method/path; this is an advanced setting where you must be very careful not to accept unintended HTTP methods.

Basic example:

~~~java
http.logout(logout -> logout
    .logoutUrl("/signout")
    .logoutSuccessUrl("/login?logout")
    .permitAll());
~~~

In a session-based application with **CSRF enabled** under the standard configuration, `POST /signout` with a valid token is the logout action; merely visiting `GET /signout` does **not** mean the user has logged out. Do not equate `logoutUrl` with `logoutSuccessUrl`.

| Option | Question it answers | Example |
| --- | --- | --- |
| `logoutUrl` | Which request triggers logout? | `POST /signout` when CSRF is enabled and the corresponding default matcher applies. |
| `logoutSuccessUrl` | Where does the browser go on success? | `/login?logout`. |
| `logoutSuccessHandler` | Want a custom post-logout response? | Return 204 for a SPA/API instead of 302. |
| `logoutRequestMatcher` | Want special path/method matching control? | Match only `POST /signout`. |
| `invalidateHttpSession` | Should the current `HttpSession` be invalidated? | Usually enabled for stateful form login. |
| `clearAuthentication` | Should `Authentication` in the context be cleared? | Usually enabled. |
| `deleteCookies` | Should cookie deletion instructions be sent for specified cookies? | Only part of cookie cleanup; path/domain must match. |

**Attention:** the matching method and behavior of `logoutUrl` depend on CSRF configuration and Spring Security version. In Spring Security 6 Servlet, when CSRF is enabled, the logout matcher created by the configurer usually requires `POST`; when CSRF is disabled, the default configuration may accept multiple HTTP methods, including GET. Do not treat merely changing the URL path as a security control. Always **test the actual HTTP method** against the deployed security chain.

## 3. Where Does `LogoutFilter` Sit in the Filter Chain?

A request passes through `FilterChainProxy` and the matching `SecurityFilterChain`. When the request matches the logout endpoint, `LogoutFilter` is the central component that recognizes it, runs the `LogoutHandler` instances, and then runs `LogoutSuccessHandler`.

Logical diagram:

~~~text
Browser holds JSESSIONID cookie
  |
  | POST /signout + valid CSRF token
  v
SecurityFilterChain
  |
  | CsrfFilter
  |  -> missing/wrong token? 403; DOES NOT reach LogoutFilter
  |  -> valid token? continue
  |
  v
LogoutFilter
  | matches logout URL + HTTP method
  |
  +-- No match:
  |      forwards request down the filter chain
  |
  +-- Match:
         1. LogoutHandlers clean up state (SecurityContext,
            authentication, HttpSession, CSRF token, ...)
         2. LogoutSuccessHandler builds response
            e.g. 302 Location: /login?logout
  |
  v
Browser receives redirect / logout result
~~~

**Ordering matters:** `LogoutFilter` in the standard chain processes logout before controller-level authorization is evaluated, so logout should not depend on a `@PostMapping` in an MVC controller as though it were login business logic. If you build a custom controller logout endpoint that bypasses `LogoutFilter`, you must ensure all handlers and state cleanup yourself; that approach is error-prone.

`CsrfFilter` must block invalid requests before they cause side effects. For `POST /signout`, it is essential that the request **enters the right chain with CSRF enabled** and is not inadvertently exempted via `ignoringRequestMatchers(...)`.

### `LogoutHandler` vs. `LogoutSuccessHandler`

`LogoutHandler` performs work before the response: for example, `SecurityContextLogoutHandler` clears the context/authentication and may invalidate `HttpSession`, alongside configured CSRF/remember-me handlers. Handlers should fail safely without carelessly throwing errors that leave partial state exposed.

`LogoutSuccessHandler` only decides the HTTP response **after** the handler chain: redirecting to `/login?logout`, returning `204 No Content`, or returning a response matching the frontend contract. Do not use a success handler to replace session cleanup, and do not take an arbitrary `returnUrl`/`next` parameter for redirecting to avoid open redirects.

### `LogoutFilter` Does Not Mean Every Token Is Revoked

Logging out an HTTP session may invalidate the session cookie, yet an already-issued **self-contained JWT access token** can remain valid until expiration if another resource server continues accepting it without a revocation mechanism. With OAuth2/OIDC, refresh tokens, SSO sessions, and provider logout, you must design a dedicated workflow if logout across multiple components is required. Do not claim `http.logout(...)` automatically revokes every token across all services.

## 4. GET, POST, and CSRF: Behavior Matrix

Assume:

- A stateful application using session cookies.
- CSRF enabled, with no matcher exempting logout.
- Custom logout configured with `logoutUrl("/signout")` and success URL `/login?logout`.
- No other MVC controller intentionally handling `GET /signout`.

| Request | Valid CSRF token? | Security expectation |
| --- | --- | --- |
| `GET /signout` | No token needed for safe GET | **Does not log out**. May return 404, a confirmation page, or a route-specific response. |
| `POST /signout` | None | **403** due to CSRF; login session remains valid. |
| `POST /signout` | Invalid token | **403**, logout handlers do not run. |
| `POST /signout` | Valid token | Runs logout handlers; typically **302** to `/login?logout` in the example config. |
| `PUT /signout` | None | Typically blocked by CSRF if not exempted; must not log out. |
| `DELETE /signout` | Valid token | Does not match default POST method of `logoutUrl` when CSRF is enabled; must not log out. |
| `POST /wrong-path` | Valid token | Does not match logout URL; handled by other routing/authorization rules. |
| `POST /signout` with unauthenticated session | Valid token | Logout handlers may still finish and produce a success response; does not prove a user was previously logged in. |

This is a **policy matrix** for the example, not a guarantee of identical status codes in every application. Status codes for requests that **do not match logout** depend on routes, the dispatcher, entry points, and remaining authorization rules. The most important assertion for tests: **the session has not been invalidated and the context has not been cleared by a GET**.

### `GET /logout` “Confirmation Page” in the Default Configuration

When using the default login/logout configuration where Spring Security can generate default UI pages, **`GET /logout` may render a confirmation page** containing a POST form with a CSRF token instead of executing logout immediately. If you have custom logout pages, changed URLs, multiple security chains, or disabled default page generation, GET behavior may differ or return 404. Do not assume every Spring Security app automatically serves a GET confirmation page.

Example of a semantically safe form:

~~~html
<form action="/logout" method="post">
  <!-- CSRF hidden field must be injected by the framework/template -->
  <button type="submit">Log out</button>
</form>
~~~

The HTML snippet above is **incomplete for a CSRF-enabled app** without a hidden input containing the actual CSRF token. The Spring Boot example below uses Thymeleaf to render the form token properly.

### Why Not Choose GET for Logout?

GET requests can be prefetched, loaded by a browser when a user hovers/previews a link, embedded by another website, or hit by crawlers. Even if an application uses `SameSite` and cookie restrictions, those measures do not turn state-changing GET into a reliable design. Using POST + CSRF token remains the baseline for browser sessions.

### Should DELETE Be Allowed for Logout?

In some REST APIs, `DELETE /session/current` may signify deleting a session. However, for a browser UI using **cookie authentication**, DELETE is also an unsafe method requiring equivalent CSRF protection; furthermore, HTML forms cannot submit DELETE directly without method overriding. If the requirement is simply logout, a plain POST consistent with Spring Security's default is usually easier to use and test.

## 5. Where Does the CSRF Token Come From?

**CSRF** exploits the fact that browsers can automatically send a site's cookies/credentials on requests initiated by another origin. When a **state-changing** operation relies solely on cookies, the server needs a way to verify the request originated from a site-authorized flow. An unpredictable CSRF token properly bound to the session/request policy is a common defense.

In Spring Security Servlet:

- `CsrfFilter` decides whether a request requires token verification, then compares the token from the request against the token provided by the repository.
- `CsrfTokenRepository` stores/reads tokens per policy; `HttpSessionCsrfTokenRepository` and `CookieCsrfTokenRepository` have different characteristics.
- Forms typically send the token in a hidden field named according to `CsrfToken.getParameterName()`, commonly `_csrf`.
- JS frontends typically send the token in a header named per repository, such as `X-CSRF-TOKEN` or `X-XSRF-TOKEN`; **do not** guess one universal name across all apps.
- In Spring Security 6, token handling may involve **deferred tokens** and token masking/encoding to help protect against BREACH. When building a SPA, follow the exact token-request handler and repository guidance for your Spring Security version.

HTTP example (values are illustrative; real tokens are generated by the framework):

~~~http
POST /signout HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=opaque-session-id
Content-Type: application/x-www-form-urlencoded

_csrf=generated-csrf-token
~~~

A CSRF token is **not a password** and not an access token. Do not log tokens/session cookies or place them in URL query strings, emails, or referrers. Tokens may be rotated/cleared after authentication/logout; cached forms holding an old token may need to refresh before the next operation.

### Token in a Hidden Form Field

A server-rendered form can generate an input from the `_csrf` request attribute. With Thymeleaf integrated with Spring MVC, using `th:action` on a POST form usually enables the framework to add a hidden CSRF field via `RequestDataValueProcessor`, depending on template/request-handler configuration. When rendering HTML manually or using an unsupported frontend, you must fetch the server-issued token and add the proper parameter/header.

Do not hard-code tokens and do not use `csrf().disable()` to “fix” a 403 on POST. On a 403 error, investigate: is the token present, is the parameter/header name right, does the token belong to the current session, was the form rendered after login/logout, is the browser sending the right cookie, and did the endpoint pass through the right `SecurityFilterChain`?

## 6. Complete Spring Boot Example: `POST /signout` with CSRF

The example uses an in-memory user **for learning only**, default form login, a custom logout URL, a fixed success URL, and a Thymeleaf page with a logout button. Project structure:

~~~text
src/main/java/com/example/logoutlesson/
  LogoutLessonApplication.java
  SecurityConfig.java
  PagesController.java
src/main/resources/templates/
  signout-form.html
src/test/java/com/example/logoutlesson/
  LogoutFlowIntegrationTest.java
~~~

Corresponding Maven/Gradle dependencies: `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-thymeleaf`; for testing, `spring-boot-starter-test` and `spring-security-test`. Source files must reside in the same package or be properly component-scanned.

### 6.1. `SecurityConfig.java`

~~~java
package com.example.logoutlesson;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails demo = User.withUsername("student")
                .password(encoder.encode("training-only"))
                .roles("USER")
                .build();

        return new InMemoryUserDetailsManager(demo);
    }

    @Bean
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/signout")
                .logoutSuccessUrl("/login?logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .permitAll());

        // Do not call csrf(AbstractHttpConfigurer::disable):
        // Default CSRF still applies to the logout POST.
        return http.build();
    }
}
~~~

This is a typical configuration for **stateful browser login**:

1. `formLogin(...)` enables session-based login; no stateless Bearer JWT API is used here.
2. `logoutUrl("/signout")` changes the request path that triggers logout without altering the safe POST method when CSRF is enabled.
3. `logoutSuccessUrl("/login?logout")` uses a server-fixed relative URL, accepting no external URL from the client.
4. `invalidateHttpSession(true)` requests invalidation of the HTTP session; this can affect other data stored in the session, so understand the business scope.
5. `clearAuthentication(true)` clears the authentication. The security context and related tokens are also handled by the framework's configured logout handlers.
6. `permitAll()` makes the logout endpoint and success URL accessible in a strict authorization model; it does not mean bypassing CSRF.
7. The configuration does **not** disable CSRF. If you get 403 after clicking the logout button, inspect token/session handling rather than disabling CSRF by default.

**Do not use demo credentials in production.** In real deployments, use a proper user store, password hashing/secret management, and policies. The strings `student`/`training-only` are purely to make tests clear.

### 6.2. `PagesController.java`

~~~java
package com.example.logoutlesson;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class PagesController {

    @GetMapping("/public")
    @ResponseBody
    public String publicPage() {
        return "public";
    }

    @GetMapping("/private")
    @ResponseBody
    public String privatePage(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/signout-form")
    public String signoutForm() {
        return "signout-form";
    }
}
~~~

`GET /signout-form` only **displays the form**; it does not perform logout. It requires authentication because of `anyRequest().authenticated()`. `GET /private` also requires login and returns the username; tests can use it to prove whether the context remains or is gone across requests.

Do not create `@PostMapping("/signout")` in the controller: that POST URL belongs to Spring Security's `LogoutFilter`. The controller is not responsible for clearing the session or context.

### 6.3. `templates/signout-form.html`

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Secure Log out</title>
</head>
<body>
  <h1>Log out</h1>
  <p>Click the button to end your current login session.</p>
  <form th:action="@{/signout}" method="post">
    <button type="submit">Log out</button>
  </form>
</body>
</html>
~~~

**Key point:** With Thymeleaf integrated with Spring MVC/Spring Security under standard Boot configuration, `th:action` on a POST form interacts with the request-data-value processor to insert the appropriate CSRF hidden field. When using another template engine or static HTML, this feature may **not exist**; you must manually render the hidden field with the server-issued token. Always **inspect the actual rendered HTML** (confirming the token field appears) rather than assuming `method="post"` alone is enough.

A manual form-rendering pattern in another environment (this is an **illustrative snippet**, containing no real token and non-functional without server token issuance):

~~~html
<form action="/signout" method="post">
  <input type="hidden" name="_csrf" value="TOKEN_FROM_SERVER">
  <button type="submit">Log out</button>
</form>
~~~

In real code, never use the literal `TOKEN_FROM_SERVER`. The field name `_csrf` is a common default, but an app may customize the parameter/header/repository; obtain it from `CsrfToken`/template renderer. When using Thymeleaf `th:action`, avoid manually inserting a redundant second hidden token.

### 6.4. `LogoutLessonApplication.java`

~~~java
package com.example.logoutlesson;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LogoutLessonApplication {
    public static void main(String[] args) {
        SpringApplication.run(LogoutLessonApplication.class, args);
    }
}
~~~

In a project with Maven Wrapper, run:

~~~bash
./mvnw spring-boot:run
~~~

Opening `http://localhost:8080/private` while unauthenticated redirects to the login flow. After logging in with demo user `student`, open `http://localhost:8080/signout-form` and click the button. The expected outcome is a POST form submission to `/signout` with a valid CSRF token, the session being invalidated, and the response redirecting to `/login?logout`.

In applications mounted under a context path or behind a reverse proxy, use URL builder templates and verify the cookie path and actual routes; never concatenate raw client-supplied hosts.

## 7. MockMvc Testing: Don't Assert Only 302

`MockMvc` with `spring-security-test` lets you run requests through `SecurityFilterChain` instead of calling controllers directly, and verify CSRF/sessions. Specifically for logout, **a 302 response alone is not enough to prove the session was actually destroyed**, and a 403 from missing CSRF says nothing about the logout handler if the request never reached it.

Create `src/test/java/com/example/logoutlesson/LogoutFlowIntegrationTest.java`:

~~~java
package com.example.logoutlesson;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class LogoutFlowIntegrationTest {

    @Autowired
    MockMvc mvc;

    private MockHttpSession login() throws Exception {
        MvcResult result = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "training-only"))
                .andExpect(status().is3xxRedirection())
                .andExpect(authenticated().withUsername("student"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    @Test
    void postWithCsrfLogsOutAndInvalidatesSession()
            throws Exception {
        MockHttpSession session = login();

        mvc.perform(post("/signout")
                    .session(session)
                    .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"))
            .andExpect(unauthenticated());

        assertTrue(session.isInvalid());

        // Do not pass the old session into the next request.
        mvc.perform(get("/private"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void postWithoutCsrfDoesNotLogOut() throws Exception {
        MockHttpSession session = login();

        mvc.perform(post("/signout").session(session))
            .andExpect(status().isForbidden());

        assertFalse(session.isInvalid());

        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("student"));
    }

    @Test
    void invalidCsrfDoesNotLogOut() throws Exception {
        MockHttpSession session = login();

        mvc.perform(post("/signout")
                    .session(session)
                    .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());

        assertFalse(session.isInvalid());
    }

    @Test
    void getCannotPerformLogout() throws Exception {
        MockHttpSession session = login();

        MvcResult result = mvc.perform(
                    get("/signout").session(session))
                .andReturn();

        // Do not require GET to be 200 or 404 since that depends
        // on the pages/routes configured by the application.
        assertNotEquals("/login?logout",
                result.getResponse().getRedirectedUrl());
        assertFalse(session.isInvalid());

        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("student"));
    }
}
~~~

Some IDEs/tooling require the static import for `redirectedUrlPattern` when using that matcher; in the file above, add the following import alongside `redirectedUrl`:

~~~java
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrlPattern;
~~~

**Why is this test valuable?**

1. Testing `POST /signout` with `.with(csrf())` confirms the logout route works **after** token validation.
2. `session.isInvalid()` verifies the mock session was invalidated; it doesn't look solely at the redirect URL.
3. A `POST` missing a token or having an invalid token must return **403**, and the session must **remain valid**.
4. `GET /signout` does not perform logout; do not force a 404 status because an app might add a confirmation page, but it **must not invalidate the session**.
5. `GET /private` after the blocked POST still returns **200** with the old session, proving the user was not logged out against their will.
6. After a successful POST logout, a request **without a session** is redirected to login; to verify that the old cookie/session ID cannot be reused on a real server, add an HTTP integration test via a browser/container.

**Technical note:** `MockMvc` uses `MockHttpSession` and `SecurityMockMvcRequestPostProcessors.csrf()` to build requests; this is servlet-filter-level testing and does not perfectly simulate browser/proxy cookies. In apps with session fixation/concurrent sessions and custom CSRF tokens, fixtures may need to align tokens with the actual repository/session. The example assertions assume the default configuration from section 6.

Run tests in a Maven Boot project with the dependencies present:

~~~bash
./mvnw test
~~~

Do not assert specific Maven stdout or session IDs: they vary by environment. Tests should run against the same Spring Security/Boot versions you deploy.

### 7.1. Testing with Request Cache and Form Login

Logout should not be tested solely from an already-logged-in screen. Consider the full sequence:

~~~text
GET /private (anonymous)
  -> redirects to login
POST /login + CSRF + valid credentials
  -> SecurityContext saved in session
GET /signout-form
  -> HTML contains form POST /signout + valid hidden CSRF token
POST /signout + session cookie + CSRF
  -> session invalidated, context cleared
GET /private
  -> requires login again
~~~

If the application has a custom `AuthenticationSuccessHandler`, `SavedRequest`, or multiple `SecurityFilterChain` beans, those components can affect login/logout target URLs; test the actual chain and routes rather than inferring from default names.

### 7.2. Do Not “Disable Security to Pass the Test”

Common mistake: `POST /signout` returns 403, so a developer removes `csrf()` from the security chain to make the test green. Doing so strips the test of web-session security meaning.

Instead:
- Use the `csrf()` request post-processor in MockMvc or submit the site-issued token in browser tests.
- Verify the form has the hidden token, the session cookie is right, the token has not expired/rotated, and the path is right.
- Check the `CsrfTokenRepository` of the specific security chain, including SPA/cookie-based CSRF token configurations.
- Do not add `csrf.ignoringRequestMatchers("/signout")` if the goal is CSRF-protected logout.

## 8. Custom Method Matching: What Changes When Replacing the Matcher?

In Spring Security 6, to enforce an explicit policy that **only POST** performs logout, you can define a dedicated request matcher. The example below is an **alternative configuration fragment** for the `.logout(...)` block in section 6; do not use both at once:

~~~java
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

// ...

.logout(logout -> logout
    .logoutRequestMatcher(
        new AntPathRequestMatcher("/signout", "POST"))
    .logoutSuccessUrl("/login?logout")
    .permitAll())
~~~

`AntPathRequestMatcher` may be deprecated in newer Spring Security 6.x releases and replaced by other matching mechanisms in later major versions; what matters is a **request matcher binding both the path and the POST method**. When using a custom matcher, explicitly test GET/PUT/DELETE methods as well.

**Important:** restricting to POST **does not replace the CSRF token**. A form on a malicious website can still submit a POST to the target origin under certain conditions. If the app relies on cookies, CSRF protection remains necessary even if the matcher only accepts POST.

### What If CSRF Is Disabled?

Example:

~~~java
// ANTI-PATTERN for a session-based form-login application:
// Do not copy this configuration verbatim into production.
http.csrf(csrf -> csrf.disable());
~~~

When CSRF is disabled, a default URL-based `LogoutConfigurer` may match multiple methods, allowing GET logout again (exact behavior depends on version/configuration). Even if you force a POST-only matcher, a cross-origin POST can still trigger logout because there is no CSRF token. Therefore, in **browser session authentication**, do not disable CSRF just to fix an AJAX/form error.

In a **stateless API** system where credentials are only sent as Bearer tokens explicitly attached by the client in headers (never automatically via cookies), the CSRF threat model differs. You can configure CSRF separately for an API chain after full evaluation, but do not copy stateless policies onto a form-login chain.

### Can Multiple Logout URLs Be Supported?

You can configure a composite matcher combining multiple paths/methods, provided you restrict it to genuinely needed routes and test every endpoint. If an app has multiple frontends, standardize on a single server endpoint and have each frontend follow the same contract rather than creating risky GET aliases.

If using `/api/logout` and `/signout` across two different security chains, clearly define chain match order, session policies, CSRF repositories, and respective logout handlers. A POST could be intercepted by the API chain before reaching the web chain; results will differ if the matcher belongs to an unselected chain.

## 9. SPAs or `fetch()` Using Session Cookies

A SPA may call `fetch` instead of submitting a traditional HTML form. If the browser still uses session cookies for authentication, **CSRF must still be handled**. JavaScript conceptual example:

~~~javascript
async function signOut(csrfToken, csrfHeaderName) {
  const response = await fetch("/signout", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      [csrfHeaderName]: csrfToken
    },
    redirect: "follow"
  });

  if (!response.ok) {
    throw new Error("Logout failed");
  }
}
~~~

This is **client-side code**, not a complete example of obtaining the token. `csrfToken` and `csrfHeaderName` must be obtained from the server via an approved mechanism compatible with Spring Security 6's repository and CSRF request handler (including deferred/BREACH token behavior). Do not store secrets/session tokens in `localStorage` unless required and analyzed against XSS/threat models.

With `fetch`'s default redirect handling, `response.ok` may reflect the final response after a 302; the app must define UI navigation on successful logout. For SPAs/APIs wanting only a status code without a redirect, use a success handler returning `204`:

~~~java
import jakarta.servlet.http.HttpServletResponse;

// Replacement for logoutSuccessUrl(...) in the appropriate config:
.logout(logout -> logout
    .logoutUrl("/signout")
    .logoutSuccessHandler((request, response, authentication) ->
        response.setStatus(HttpServletResponse.SC_NO_CONTENT))
    .permitAll())
~~~

Note that this is an **alternative configuration fragment**; do not combine it with `logoutSuccessUrl("/login?logout")` at the same time as the two semantics conflict. With `204`, the client should clear its held UI state and navigate to an unauthenticated screen per app logic; the server must still invalidate the session/context and enforce CSRF.

### `CookieCsrfTokenRepository` and SPAs

Some apps use `CookieCsrfTokenRepository` so the frontend can read the token from a cookie, commonly sending the `X-XSRF-TOKEN` header. In Spring Security 6, pay special attention to token unmasking when pairing with a CSRF request handler, because tokens rendered in HTML and raw tokens in cookies may be handled differently. Do not blindly copy `CookieCsrfTokenRepository.withHttpOnlyFalse()` from an old tutorial and assume the app is secure; configure the policy and test for your version, considering XSS and cookie scope.

## 10. What Should a Successful Logout Clear?

Commonly involved tasks:

| Resource | Common mechanism | Notes |
| --- | --- | --- |
| `SecurityContext` in request | `SecurityContextLogoutHandler` and context holder/repository. | Do not retain an authenticated context in the next thread/dispatch. |
| `HttpSession` | `invalidateHttpSession(true)`. | May destroy other session attributes; do not confuse with deleting a DB user. |
| Session cookie | Invalidation/container response and `deleteCookies(...)` if needed. | Cookie domain/path/Secure/SameSite govern what the browser actually deletes. |
| CSRF token | `CsrfLogoutHandler` / matching repository. | Old tokens cannot be reused; subsequent forms fetch a fresh token. |
| Remember-me cookie | Remember-me logout handler if remember-me is enabled. | Do not assume the remember-me cookie is deleted under differing configs. |
| Concurrent-session registry | Session lifecycle/events and registry integration. | Verify session cleanup, especially when `maxSessions` is enforced. |
| Refresh token / OAuth2 / OIDC session | Dedicated identity/provider components. | Not automatically revoked solely by invalidating the HTTP session. |
| Frontend memory state | Client clears user state/cache and navigates. | Does not replace server-side invalidation. |

**Do not use `deleteCookies("JSESSIONID")` instead of invalidating the session.** Asking the browser to delete a cookie does not guarantee the server-side session has ended; an old session ID can remain valid if the server has not invalidated it. Conversely, an invalidated session is invalid on the server even if the old cookie remains in the browser. Cookies with a different path may not be removed by a mismatched `Set-Cookie`, so always test in a real browser.

Logging out does not delete all user data or every linked system. With SSO/multiple devices, “log out this session” and “log out all devices” are two distinct product features requiring separate business decisions.

## 11. Common Pitfalls and How to Fix Them

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Clicking `GET /logout` link does not log out | GET only opens a confirmation page or doesn't match the POST matcher. | Use a form POST with a token; do not switch to GET for convenience. |
| POST logout returns 403 | Missing/wrong CSRF token, mismatched session cookie, rotated token. | Inspect rendered form and repository; use `csrf()` in MockMvc. |
| Correct POST always returns 404 | Configured URL differs from form URL, or request enters another security chain. | Compare `logoutUrl`, method, context path, and chain order. |
| GET logs out even though CSRF is enabled on another chain | Request matches a CSRF-disabled chain or custom matcher accepts GET. | Check `securityMatcher`, csrf config, and `logoutRequestMatcher`. |
| POST logout returns 302 yet protected GET stays allowed | Session/context not invalidated, request uses another credential (remember-me/JWT), or test uses wrong session. | Assert session state, context repository, and subsequent request credentials. |
| Post-logout redirect goes to an external site | Success handler accepts arbitrary `returnUrl`. | Use a fixed relative URL or server-side destination allowlist. |
| Stale CSRF token causes 403 after login/logout | Token was cleared/rotated; frontend caches old token. | Fetch a fresh token from a valid page/endpoint. |
| Cookie deleted yet session still works | Only cleared browser cookie without invalidating server session. | Check `SecurityContextLogoutHandler` and session store. |
| Web form logout unexpectedly affects or ignores JWT API | Different threat models/token stores; confusing local session logout with JWT revocation. | Design dedicated token-invalidation/logout flows. |
| Cannot log out after session expires | UI sends stale CSRF token; session/cookie changed. | Define UX/re-login/recovery; do not bypass CSRF indiscriminately. |
| POST gets redirected by proxy before logout | HTTP→HTTPS or path canonicalization makes browser change method or drop body. | Inspect reverse proxy, TLS redirects, and request routing. |
| `GET /signout-form` has empty hidden CSRF field | Template engine lacks Spring MVC token processor integration or wrong view. | Inspect actual HTML; verify CSRF repository and token request attribute. |

### Wrong: Implementing Logout with `@GetMapping`

~~~java
// ANTI-PATTERN: causes state side effects over GET; do not put in production.
@GetMapping("/unsafe-logout")
public String unsafeLogout(HttpSession session) {
    session.invalidate();
    return "redirect:/login";
}
~~~

This snippet illustrates an error and needs MVC imports/config if compiled. Invalidating the session **directly on GET** bypasses standard logout handlers/CSRF and easily creates logout CSRF. Do not “fix” it by switching GET to PUT while browsers still attach cookies without CSRF policy.

### Wrong: Disabling All CSRF Because Logout Returns 403

~~~java
// ANTI-PATTERN for browser forms/sessions:
http.csrf(csrf -> csrf.disable());
~~~

If the app depends on cookies, this opens CSRF on actions far more dangerous than logout (transfers, email changes, password changes, etc.). Logout protection should never be solved by weakening protection across the entire web chain.

### Wrong: Checking Only That the Request Method Is POST

~~~java
// ANTI-PATTERN: a POST without CSRF can still be forged by another origin.
if ("POST".equals(request.getMethod())) {
    session.invalidate();
}
~~~

The POST method is a **necessary condition for semantically sound logout design**, not proof of user intent in cookie-based apps.

### Wrong: Redirecting to an Unvalidated `returnUrl`

~~~java
// ANTI-PATTERN post-logout open redirect:
response.sendRedirect(request.getParameter("returnUrl"));
~~~

If the application needs to route to a specific page after logout, use a fixed server destination or an approved key-to-path mapping. Never trust `Referer` or naive external domain prefixes.

## 12. Standalone Java 17: Simulating the Method + CSRF Contract

This small program is **not Spring Security**, sends no HTTP, and destroys no session; it models the logical decision of a POST-only logout endpoint. Create `LogoutRequestPolicyDemo.java`:

~~~java
public final class LogoutRequestPolicyDemo {

    record Request(String path, String method, boolean validCsrf) {}

    static String evaluate(Request request) {
        if (!"/signout".equals(request.path())
                || !"POST".equals(request.method())) {
            return "NOT_LOGOUT";
        }

        if (!request.validCsrf()) {
            return "CSRF_REJECTED";
        }

        return "LOGOUT_ALLOWED";
    }

    public static void main(String[] args) {
        System.out.println(evaluate(
            new Request("/signout", "GET", false)));
        System.out.println(evaluate(
            new Request("/signout", "POST", false)));
        System.out.println(evaluate(
            new Request("/signout", "POST", true)));
        System.out.println(evaluate(
            new Request("/private", "POST", true)));
    }
}
~~~

Run on JDK 17 or newer:

~~~bash
javac LogoutRequestPolicyDemo.java
java LogoutRequestPolicyDemo
~~~

**Exact** stdout:

~~~text
NOT_LOGOUT
CSRF_REJECTED
LOGOUT_ALLOWED
NOT_LOGOUT
~~~

Takeaway: only when **the path matches, the HTTP method matches, and CSRF is valid** does the model allow logout to proceed. In a real Spring app, `CsrfFilter` and `LogoutFilter` enforce the respective parts at different points, actual HTTP status codes also depend on authentication/authorization/routing, and session invalidation must be tested separately.

## 13. Pre-Release Checklist

- [ ] Clarify whether the application uses browser cookies/sessions or stateless tokens.
- [ ] `logoutUrl` is the exact path called by the form/client; do not confuse it with `logoutSuccessUrl`.
- [ ] For cookie sessions: **POST-only logout with CSRF enabled**, never letting GET invalidate a session.
- [ ] Do not exempt logout from CSRF just to avoid 403.
- [ ] Form POST retrieves the real token from the repository/framework; never hard-code tokens.
- [ ] Post-logout: authentication/context is absent in subsequent requests; server-side session is invalidated per policy.
- [ ] `JSESSIONID` cookie has appropriate Secure/HttpOnly/SameSite/path/domain, verified in a real browser.
- [ ] Logout success destination is fixed or allowlisted, avoiding open redirects.
- [ ] If using multiple chains, verify the right chain matches `/signout` and inspect that chain's CSRF policy.
- [ ] Test that GET logout has no side effects, POST missing/wrong CSRF returns 403, valid POST logs out, and protected endpoints require login afterward.
- [ ] Avoid double registration or custom controller logouts bypassing `LogoutFilter`.
- [ ] If using remember-me, concurrent sessions, or Spring Session/clustering, confirm handlers and registry cleanup work.
- [ ] For JWTs/refresh tokens/SSO, have a dedicated token-revocation policy if business rules require it.
- [ ] Never log session cookies, CSRF tokens, passwords, or authorization headers.
- [ ] Keep regression tests whenever changing `logoutUrl`, request matchers, proxy/context paths, or frontend forms.

## 14. Review Questions

**Q1. Is `logoutUrl("/signout")` the page displayed after logout?** No. It is the path where `LogoutFilter` receives logout requests. `logoutSuccessUrl(...)` specifies the post-success destination.

**Q2. Why should logout via GET not occur?** GET can be fetched automatically or triggered by another site and must not mutate state; it risks logout CSRF and violates HTTP semantics.

**Q3. If a form uses POST, is it automatically protected against CSRF?** No. Another origin can still submit a POST; a valid CSRF token or equivalent threat-model defense is required.

**Q4. What does a POST logout missing a token typically receive in a CSRF-enabled app?** 403 before `LogoutFilter` runs; current authentication/session should remain intact.

**Q5. Why not use `csrf.disable()` to fix a 403?** Because it weakens protection across all unsafe requests in that chain and may inadvertently allow GET logout or forged POSTs.

**Q6. Is `GET /logout` always a confirmation page?** No. It can be a confirmation page when the framework generates default UI appropriately, or 404/a custom route depending on config. The key is that GET must not log out.

**Q7. Why must you still inspect the session after receiving 302?** 302 only describes the HTTP response. You must confirm logout handlers invalidated the session/cleared authentication and protected endpoints no longer accept old credentials.

**Q8. Does deleting cookies equate to revoking a JWT/refresh token?** No. Session logout and token revocation are separate mechanisms, especially with OAuth2/OIDC or multiple services.

**Q9. For a SPA using `fetch` POST, where does the token come from?** From a server-side mechanism designed for the matching CSRF repository and request handler; send it in the properly named header/field alongside the matching session cookie. Never fabricate values or guess formats.

**Q10. When changing `logoutRequestMatcher`, what must be tested?** Test the actual matched path and **HTTP method**, verify GET has no side effects, other unsafe methods do not bypass policy, and CSRF remains enforced.

**Key takeaway:** **`logoutUrl` defines the trigger point; the HTTP method defines the operation; the CSRF token verifies the request came from an authorized flow; `LogoutHandler` cleans up state; `LogoutSuccessHandler` decides the response.** For cookie-based Servlet form login, the standard safe design is **POST logout with CSRF**, not GET logout.
