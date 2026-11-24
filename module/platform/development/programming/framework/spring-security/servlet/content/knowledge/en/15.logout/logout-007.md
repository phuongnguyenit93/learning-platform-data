# Custom Logout Endpoints and Using `SecurityContextLogoutHandler` in Spring Security Servlet

## Learning Objectives

In a Spring Security Servlet application using form login and `HttpSession`, **logout** is not simply returning HTTP 200 or redirecting to the login page. The server must terminate the current session's authentication state, handle `SecurityContext` properly, and—depending on configuration—clean up CSRF tokens, remember-me tokens, cookies, or publish logout events.

Spring Security already provides **`LogoutFilter`** and `HttpSecurity.logout(...)` configuration. That is normally the recommended approach. Sometimes, however, an application needs a **custom MVC controller-handled endpoint** to integrate business logic or a bespoke HTTP contract. In that case, **`SecurityContextLogoutHandler`** is the key component for clearing the security context and invalidating `HttpSession` appropriately, rather than poking at `SecurityContextHolder` piecemeal.

After this lesson, you will be able to:

1. Describe the default logout flow of `LogoutFilter`, `LogoutHandler`s, and `LogoutSuccessHandler`.
2. Distinguish changing the logout URL via the DSL from genuinely writing `@PostMapping`/`@DeleteMapping` in MVC.
3. Know exactly what `SecurityContextLogoutHandler.logout(request, response, authentication)` does and does not do.
4. Write a `POST /account/logout` endpoint with `SecurityContextLogoutHandler` when a custom controller is needed.
5. Maintain CSRF protection, disallow arbitrary GET logout, and verify authorization and session fixation.
6. Know why logging out a Servlet session **does not equal** destroying JWTs, revoking all devices, immediately erasing browser cookies, or aborting in-flight requests.
7. Build and test a Spring Boot 3.x / Spring Security 6.x / Java 17+ application with `MockMvc`.
8. Choose the right extension point for auditing, cookie deletion, remember-me, token revocation, or API responses.

Scope: Spring Security **Servlet stack**, a stateful application using `HttpSession`/`formLogin`. OAuth2/OIDC, SAML, WebFlux, or stateless JWT mechanisms have their own logout contracts and cannot be replaced by calling a single Servlet handler.

## 1. How Is Logging Out Different from Returning a Response?

After a successful form login, the app typically stores `Authentication` in `SecurityContext` and saves `SecurityContext` into `HttpSession` via `SecurityContextRepository`. The browser keeps the session ID in a cookie (named per config, such as `JSESSIONID` or `SESSION`).

If a user merely clicks a link leading to `/logged-out` and the UI displays “Logged out,” the server-side session **may still be valid**. The browser resends the session cookie on the next request and Spring Security can still restore `Authentication`.

Distinguish clearly:

| Action | Is it genuine logout? | Notes |
| --- | --- | --- |
| Frontend hides login button | No | Only changes the UI |
| Returning HTTP 200 “logout ok” | Not necessarily | Must inspect server-side session/security context |
| Clearing a JavaScript variable in browser | Not necessarily | `HttpOnly` session cookies usually cannot be read by JavaScript |
| Deleting browser cookies | Insufficient | Server-side session may still exist |
| Standalone `HttpSession.invalidate()` | Partial | Still need to handle `SecurityContext` and other handlers |
| Standalone `SecurityContextHolder.clearContext()` | Partial | Does not ensure the old session was destroyed or context saved properly |
| `LogoutFilter` running standard `LogoutHandler` chain | Yes, per configured contract | Supports multi-step cleanup and success response |
| MVC endpoint manually calling `SecurityContextLogoutHandler` | Yes for current session if wired right | Additional cleanups must be handled explicitly as required |

A proper logout must produce an observable outcome: **new requests to authenticated resources must not reuse the just-logged-out session**. If the session persists or an old `SecurityContext` is re-saved after the request, the logout UI is just a facade.

## 2. `LogoutFilter` and the Default Pipeline

In Servlet apps, Spring Security supplies `LogoutFilter`. When a request matches the logout `RequestMatcher`, the filter invokes registered `LogoutHandler`s and hands response rendering to `LogoutSuccessHandler`.

A high-level diagram:

~~~text
Browser: POST /logout + session cookie + CSRF token
    |
Servlet FilterChainProxy / SecurityFilterChain
    |
CsrfFilter validates token for protected POST
    |
LogoutFilter: does request match logout matcher?
    |
    +-- no match -> subsequent filters, MVC...
    |
    +-- match:
           |
           +-- LogoutHandler #1
           +-- LogoutHandler #2
           +-- SecurityContextLogoutHandler
           +-- additionally configured handlers
           |
           +-- LogoutSuccessHandler
                  |
                  +-- redirect or HTTP response
~~~

The exact order and list of handlers depend on configuration/version. Normally they handle `SecurityContext` and the session; conditionally there may be CSRF cleanup, remember-me cleanup, and logout success events. Do not assume one specific handler always runs once in every custom setup.

**`LogoutFilter` runs before `AuthorizationFilter` in the typical chain.** Thus, letting the filter handle the logout URL processes the request under logout logic before controller `authorizeHttpRequests` decisions apply. Conversely, when writing your own MVC endpoint and disabling `LogoutFilter`, that URL must live in the right security chain and be authorized per application policy.

### `LogoutHandler` vs. `LogoutSuccessHandler`

- **`LogoutHandler.logout(request, response, authentication)`:** performs cleanup, e.g., invalidating the session, clearing remember-me tokens, or deleting cookies.
- **`LogoutSuccessHandler.onLogoutSuccess(request, response, authentication)`:** picks the post-cleanup response: redirect, status code, JSON, etc.

Never use a success handler alone in place of cleanup: returning 200/302 does not mean `Authentication` was removed. Conversely, `LogoutHandler` is generally not responsible for choosing the final response.

Default logout handlers are designed for cleanup actions. If writing a custom handler capable of throwing exceptions, consider logging, retries, transactions, and the legal/security meaning of logout; never expose credentials or session IDs.

## 3. Prefer the Simplest Approach: Change the URL via `HttpSecurity.logout(...)`

If the requirement is simply “change `POST /logout` to `POST /account/logout` and redirect users to `/logged-out`,” **you do not need `@PostMapping`**.

In `SecurityFilterChain` configuration:

~~~java
http.logout(logout -> logout
        .logoutUrl("/account/logout")
        .logoutSuccessUrl("/logged-out")
        .permitAll());
~~~

This is an excerpt to be placed inside a complete `SecurityConfig` file when applied. With this approach:

1. `LogoutFilter`, **not an MVC controller**, handles requests matching the logout path.
2. Relevant `LogoutHandler`s are invoked automatically; no manual `new SecurityContextLogoutHandler()` is needed.
3. The configured `LogoutSuccessHandler` redirects to `/logged-out`.
4. `/logged-out` must remain accessible after the session is invalidated, e.g., `requestMatchers("/logged-out").permitAll()`.
5. When CSRF is enabled, POST is the appropriate logout method under standard config; HTML forms need a valid CSRF token.
6. **Do not create an MVC `@PostMapping` at the same URL** expecting the controller to run first: `LogoutFilter` can intercept the request, execute logout, and finish the response straight from the filter chain.

A short configuration (Spring Security DSL portion only):

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/logged-out").permitAll()
        .anyRequest().authenticated());

http.formLogin(withDefaults());

http.logout(logout -> logout
        .logoutUrl("/account/logout")
        .logoutSuccessUrl("/logged-out")
        .permitAll());
~~~

If JSON is needed instead of a redirect after logout, check a custom `LogoutSuccessHandler` or the DSL's `logoutSuccessHandler`. That still preserves the standard pipeline instead of immediately writing a logout controller and reimplementing the entire security lifecycle.

## 4. When Is a Custom MVC Endpoint Genuinely Needed?

A logout controller can have valid reasons:

- The app has a specialized URL/method/response contract and wants orchestration centralized in MVC.
- Business tasks must combine with logout in an explicit sequence, such as recording session termination or sending notifications.
- You want to implement a custom legacy-designed endpoint while retaining full control over filter and session configuration.
- You want to demonstrate the logout lifecycle explicitly in code rather than only via DSL.

However, if you only need to change the URL, delete cookies, or return JSON, you can use **`logoutUrl`, `addLogoutHandler`, `deleteCookies`, `logoutSuccessHandler`** on `LogoutConfigurer` without an MVC endpoint.

Decide who “owns” the request:

| Approach | Who receives `POST /account/logout`? | Who calls `SecurityContextLogoutHandler`? |
| --- | --- | --- |
| `HttpSecurity.logout().logoutUrl("/account/logout")` | `LogoutFilter` | Spring Security's configured logout pipeline |
| MVC `@PostMapping("/account/logout")` and logout filter does not match URL | `DispatcherServlet` → controller | Controller must invoke it explicitly |
| Both `LogoutFilter` matching URL and `@PostMapping` on same URL | Normally `LogoutFilter` handles first | Controller may never run |
| MVC controller only returns `"redirect:/login"` | Controller | Nobody if you forget to call a logout handler |

In section 6's MVC sample, we **explicitly disable the default `LogoutFilter`** for clarity. That means we assume responsibility for other cleanups normally handled by the logout DSL, so the example is strictly for learning or apps with verified requirements. Never mix both alternatives in one project without deciding request routing.

## 5. `SecurityContextLogoutHandler`: Contract and Actual Effects

`SecurityContextLogoutHandler` belongs to package `org.springframework.security.web.authentication.logout`. It implements `LogoutHandler` and exposes:

~~~java
void logout(
        HttpServletRequest request,
        HttpServletResponse response,
        Authentication authentication);
~~~

This is an illustrative API signature, not a standalone Java file. When invoking the handler in a stateful Servlet app:

- By default, the handler **invalidates the current `HttpSession` if present**, via `request.getSession(false)` and `session.invalidate()`.
- It **removes `Authentication` from `SecurityContext` and clears `SecurityContextHolder`** per Spring Security's strategy.
- In modern Spring Security versions, the handler coordinates with its `SecurityContextRepository` to save an empty context or ensure the old context is not reused per handler config. If the app uses a custom `SecurityContextRepository`, verify specific wiring/contracts.
- It **does not redirect** to a logout success URL; the controller/`LogoutSuccessHandler` must decide the response.
- It **does not automatically destroy issued JWTs**, guarantee refresh-token revocation, delete custom cookies, or clear sessions on other devices.
- It **does not replace `CsrfLogoutHandler`, `RememberMeServices`, or audit/event handlers** if your app relies on those cleanups and you dropped `LogoutFilter`.

Actual invocation snippet:

~~~java
SecurityContextLogoutHandler handler =
        new SecurityContextLogoutHandler();

Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

handler.logout(request, response, authentication);
~~~

Explanation:

- `Authentication` is the object bound to the request just processed by Spring Security; the controller reads it from `SecurityContextHolder` at request time.
- The handler receives the actual Servlet request/response. Never pass someone else's request or a fabricated cookie to log out on another's behalf.
- No need to grab `HttpSession` and manually call `setAttribute("SPRING_SECURITY_CONTEXT", null)` when using the handler per contract. Hardcoding attribute names depends on implementation details and skips other cleanups.
- Never use `SecurityContextHolder.clearContext()` as the sole logout step; it only affects the context bound to current execution without ensuring persisted session state is removed.

You can customize the handler with `setInvalidateHttpSession(false)` or `setClearAuthentication(false)`, yet **do not** toggle these flags merely to “keep the shopping cart” without a security review. If preserving the session after logout, you must have a strategy to clear `Authentication` in the backing repository and manage session fixation, CSRF tokens, and sensitive attributes.

### What About the Session ID After Logout?

Once a session is invalidated, the old ID no longer references a valid session. The browser may **still hold the old cookie**; new requests carrying that cookie will not be treated as logged in if the server properly removed/invalidated the session.

Deleting the cookie from the browser as well requires an expired `Set-Cookie` response with matching name/path/domain. Exact configuration varies across `JSESSIONID`, Spring Session's `SESSION` cookie, reverse proxies, and context paths. So never hardcode deleting `"JSESSIONID"` and claim every Spring Session environment is fully logged out. **Server-side** session invalidation is the core requirement; cookie deletion supplements UX and defense.

## 6. Practice: Custom MVC `POST /account/logout` Endpoint

We build a Spring Boot Servlet app with:

- Spring Security default form login: `GET /login` and `POST /login`.
- Mock account `student`, password `local-demo-only` hashed with `PasswordEncoder`.
- `GET /private` returning user info, requiring authentication.
- `POST /account/logout` handled by an **MVC controller** invoking `SecurityContextLogoutHandler`.
- `GET /logged-out` public after logout.
- Default CSRF retained; POST logout missing a token is rejected.
- `MockMvc` tests verifying login, calling the endpoint, and session invalidation.

### 6.1. Structure and Dependencies

Uses Java 17+, Spring Boot 3.3.x, and Spring Security 6.x managed by Boot's BOM. Create a Gradle Groovy DSL project:

~~~text
manual-logout-demo/
  settings.gradle
  build.gradle
  gradlew / gradlew.bat    (Gradle Wrapper if present)
  src/main/java/dev/example/manuallogout/
    ManualLogoutApplication.java
    SecurityConfig.java
    AccountLogoutController.java
    PagesController.java
  src/test/java/dev/example/manuallogout/
    ManualLogoutIntegrationTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'manual-logout-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

You can generate the Gradle Wrapper with a compatible Gradle version or initialize the project via Spring Initializr. Because the Java files depend on Spring libraries, you **cannot** run `javac` on individual files without supplying the project classpath. The `./gradlew` command requires the wrapper to exist.

### 6.2. Spring Boot Application

File `src/main/java/dev/example/manuallogout/ManualLogoutApplication.java`:

~~~java
package dev.example.manuallogout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ManualLogoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(ManualLogoutApplication.class, args);
    }
}
~~~

### 6.3. `SecurityFilterChain` and Demo Account

File `src/main/java/dev/example/manuallogout/SecurityConfig.java`:

~~~java
package dev.example.manuallogout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("student")
                        .password(encoder.encode("local-demo-only"))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/logged-out").permitAll()
                .anyRequest().authenticated());

        http.formLogin(withDefaults());

        // This example intentionally routes POST /account/logout to the MVC controller.
        // Do not run the default LogoutFilter simultaneously.
        http.logout(logout -> logout.disable());

        return http.build();
    }
}
~~~

Analysis:

- `requestMatchers("/logged-out").permitAll()`: after the session is destroyed, the browser can still view the confirmation page. Do not guard it with `authenticated()` if redirecting there post-logout.
- `anyRequest().authenticated()`: `GET /private` and `POST /account/logout` require an authenticated user. The default login page supplied by `formLogin` remains open per its configuration.
- `formLogin(withDefaults())` uses the default login filter, creating/saving `SecurityContext` via Spring Security's mechanism.
- `logout(...disable())` **removes the standard `LogoutConfigurer`/`LogoutFilter`** from the chain so `POST /account/logout` can reach the controller. That choice is **strictly for demonstrating a custom endpoint**. In production, if remember-me cleanup, logout events, custom cookies, or token handling are still needed, implement them completely or prefer `LogoutFilter` with `logoutUrl`.
- `CsrfFilter` stays active. Disabling `LogoutConfigurer` **does not disable CSRF**.

Do not add your own `@PostMapping("/login")`: username/password are handled by `UsernamePasswordAuthenticationFilter`. Never hardcode production usernames/passwords in source; the sample account is for localhost only.

### 6.4. Custom Logout Controller

File `src/main/java/dev/example/manuallogout/AccountLogoutController.java`:

~~~java
package dev.example.manuallogout;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.PostMapping;

@Controller
public class AccountLogoutController {

    private final SecurityContextLogoutHandler logoutHandler =
            new SecurityContextLogoutHandler();

    @PostMapping("/account/logout")
    public String logout(
            HttpServletRequest request,
            HttpServletResponse response) {

        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        logoutHandler.logout(request, response, authentication);

        return "redirect:/logged-out";
    }
}
~~~

Key points of this lesson:

1. Spring MVC handles **`POST /account/logout`** and receives the current request/response.
2. `Authentication` is retrieved **before** the logout handler clears `SecurityContext`.
3. `SecurityContextLogoutHandler` destroys the current session by default, clears authentication/context, and coordinates with its repository.
4. The controller returns a redirect to `/logged-out`. Redirecting does not replace the server-side logout step.
5. Do not call `HttpSession.invalidate()` manually again if the handler already does so. Calling invalidate twice on an invalid session can throw errors and obscure the flow.
6. Never put logout logic in GET because GET can be triggered unintentionally by browsers, crawlers, preloads, or external links.

In this example, the controller is a singleton Spring bean and the handler holds no per-request state in fields. Never store `Authentication` or `HttpServletRequest` in controller fields because multiple requests run concurrently. `SecurityContextHolder` is thread-associated per the active strategy; handling async/thread switching requires dedicated propagation/cleanup.

**Note on custom `SecurityContextRepository`:** if the app does not use `SecurityContextLogoutHandler`'s default repository, verify/set a repository matching the security chain and ensure empty context persistence honors the contract. `HttpSession` invalidation usually suffices for the default session demo, yet must not be assumed across all custom stores.

### 6.5. Verification Endpoints Before and After Logout

File `src/main/java/dev/example/manuallogout/PagesController.java`:

~~~java
package dev.example.manuallogout;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PagesController {

    @GetMapping("/private")
    public String privatePage(Authentication authentication) {
        return "PRIVATE:" + authentication.getName();
    }

    @GetMapping("/logged-out")
    public String loggedOut() {
        return "LOGGED_OUT";
    }
}
~~~

`/private` is guarded by `anyRequest().authenticated()`. `/logged-out` requires no session and returns a simple text response. In real apps, the logged-out page may be HTML or JSON depending on the client.

### 6.6. Running and Observing

In a project with the wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell, typically use:

~~~powershell
.\gradlew.bat bootRun
~~~

Open `http://localhost:8080/private` while unauthenticated: per default `formLogin`, you are normally redirected to `/login`.

The Spring Security-generated login page includes a form and matching CSRF token. Use the demo account:

~~~text
Username: student
Password: local-demo-only
~~~

After logging in, `GET /private` returns body:

~~~text
PRIVATE:student
~~~

To test `POST /account/logout` manually in a browser, you must send the **matching session cookie and CSRF token**. You cannot trigger logout via `GET /account/logout`: the controller declares only `@PostMapping`.

Example Thymeleaf form to embed in an application page (this snippet is **not part of the sample project above**; using it requires Spring MVC/Thymeleaf template integration):

~~~html
<form th:action="@{/account/logout}" method="post">
    <button type="submit">Log out</button>
</form>
~~~

With Thymeleaf and Spring Security's `RequestDataValueProcessor`, a `method=POST` form with `th:action` can automatically receive a hidden CSRF field; inspect the rendered HTML. If using plain HTML, explicitly fetch the real token from the CSRF repository/request. Never hardcode a fixed CSRF token in templates.

After a successful logout, the browser navigates to `/logged-out` and sees `LOGGED_OUT`. Visiting `/private` again no longer authenticates via the invalidated session, redirecting back to `/login` under `formLogin`.

**Never record session cookies, passwords, or CSRF tokens in docs/logs when demonstrating.** Requests with invalid tokens are typically rejected by `CsrfFilter` before the controller; HTTP status 403 in that case does not mean `SecurityContextLogoutHandler` ran.

## 7. `MockMvc` Testing for the MVC Endpoint

Add file `src/test/java/dev/example/manuallogout/ManualLogoutIntegrationTest.java`:

~~~java
package dev.example.manuallogout;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ManualLogoutIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotReadPrivatePage() throws Exception {
        mvc.perform(get("/private"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void anonymousCanReadLogoutConfirmation() throws Exception {
        mvc.perform(get("/logged-out"))
                .andExpect(status().isOk())
                .andExpect(content().string("LOGGED_OUT"));
    }

    @Test
    void customLogoutInvalidatesAuthenticatedSession() throws Exception {
        MvcResult login = mvc.perform(
                        post("/login").with(csrf())
                                .param("username", "student")
                                .param("password", "local-demo-only"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/private").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("PRIVATE:student"));

        mvc.perform(post("/account/logout")
                        .session(session)
                        .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/logged-out"));

        assertThat(session.isInvalid()).isTrue();

        mvc.perform(get("/private"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void missingCsrfDoesNotExecuteLogout() throws Exception {
        MvcResult login = mvc.perform(
                        post("/login").with(csrf())
                                .param("username", "student")
                                .param("password", "local-demo-only"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(post("/account/logout").session(session))
                .andExpect(status().isForbidden());

        assertThat(session.isInvalid()).isFalse();
    }

    @Test
    void getMethodDoesNotTriggerLogoutEndpoint() throws Exception {
        MvcResult login = mvc.perform(
                        post("/login").with(csrf())
                                .param("username", "student")
                                .param("password", "local-demo-only"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/account/logout").session(session))
                .andExpect(status().isMethodNotAllowed());

        assertThat(session.isInvalid()).isFalse();
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

The assertions verify:

- Anonymous users cannot access `/private`.
- Confirmation page `/logged-out` is public.
- Valid login creates an authenticated session and `/private` returns `PRIVATE:student`.
- `POST` logout with `csrf()` redirects to `/logged-out` and `MockHttpSession` is marked invalid.
- `POST` missing CSRF is rejected with 403 without invalidating the session.
- `GET` to the same URL does not execute logout because the controller declares only `POST`.

**Testing note:** Once `MockHttpSession` is invalidated, do not pass that exact object back into another `MockMvc` request expecting a redirect. `MockHttpSession` can throw `IllegalStateException` when touching an expired session. The test checks `session.isInvalid()` directly and then sends a fresh anonymous request to prove authorization behavior without misusing mock sessions. In integration tests on a real container, you can send the old cookie on a new request to verify the server no longer accepts that session.

The tests assume default Spring Boot/Security/Servlet without Redis or a custom `SecurityContextRepository`. With custom configurations, add tests for the respective repository/cookies; `MockMvc` passing does not automatically guarantee all cluster nodes logged out.

### Improvement: Verifying Old Cookies Are No Longer Valid

In true end-to-end HTTP testing, a stronger sequence is: log in and capture the post-session-fixation cookie; send `POST` logout with that cookie and valid CSRF; follow with `GET /private` reusing the logged-out cookie; expect unauthenticated status and a redirect/challenge. Use a real cookie jar and CSRF token flow. Never log session IDs in build logs or public screenshots.

## 8. CSRF and HTTP Methods for Logout

Logout is a state-changing action. If an app uses session cookies for authentication, requests from another site can be sent by the browser along with cookies per current cookie policies. Hence Spring Security protects logout with CSRF by default when CSRF protection is enabled.

Rules to follow:

1. For form login/cookie sessions, **POST logout with a valid CSRF token** is the standard choice.
2. GET is meant for safe operations and must not destroy sessions merely when a user opens a link. Crawlers, prefetching, or image tags can trigger GET unintentionally.
3. `requestMatchers("/account/logout").permitAll()` only governs authorization; it **does not exempt POST from CSRF**.
4. Even with a custom MVC endpoint, `CsrfFilter` still runs before `DispatcherServlet`. POST missing/invalid tokens can be rejected with 403 before the controller is invoked.
5. With SPA/`fetch`, send the token in the header/form field configured by the repository and handle cookies/`SameSite`/credentials properly per cross-origin contracts.
6. Never disable CSRF across the entire security chain just to make “`curl` logout easier.”

Raw example of a **rendered** form:

~~~html
<form action="/account/logout" method="post">
    <input type="hidden" name="_csrf"
           value="TOKEN_GENERATED_BY_SERVER_IN_REAL_REQUEST">
    <button type="submit">Log out</button>
</form>
~~~

The string `TOKEN_GENERATED_BY_SERVER_IN_REAL_REQUEST` is purely **illustrative**, not a valid token. Complete templates must retrieve tokens from Spring Security rather than hardcoding or copying from another request.

### What Is `GET /logout` in Default Configurations?

In some Spring Security setups with CSRF enabled, `GET /logout` may render a confirmation page asking the user to submit POST logout, rather than immediately ending the session. Exact behavior depends on logout handler and framework configuration. Never infer from `GET /logout` returning 200 that the session was deleted; test the next request to a protected resource directly.

If CSRF is disabled, `LogoutConfigurer` may alter how logout HTTP methods are matched and allow GET logout again, so understand the consequences before changing matchers. Never rely on an assumption that “`/logout` is always POST-only” across all configs.

## 9. Want to Return HTTP 204 or JSON Instead of Redirecting?

Many SPAs want `POST /account/logout` to return `204 No Content` instead of 302. **If `LogoutFilter` already meets your needs**, use `LogoutSuccessHandler`:

~~~java
http.logout(logout -> logout
        .logoutUrl("/account/logout")
        .logoutSuccessHandler((request, response, authentication) -> {
            response.setStatus(204);
        })
        .permitAll());
~~~

This snippet uses the standard `LogoutFilter` pipeline, making it safer than manually recreating cleanup handlers. To return JSON instead:

~~~java
http.logout(logout -> logout
        .logoutUrl("/account/logout")
        .logoutSuccessHandler((request, response, authentication) -> {
            response.setStatus(200);
            response.setContentType("application/json");
            response.setCharacterEncoding("UTF-8");
            response.getWriter().write("{\"logout\":\"ok\"}");
        })
        .permitAll());
~~~

The caller is responsible for interpreting 204/200 without expecting a redirect. If the app is a SPA using cookie authentication, proper CSRF protection is still required.

With a custom MVC controller, you can use `@RestController` and return `ResponseEntity.noContent().build()` after calling `SecurityContextLogoutHandler`. Still, understand that cleanups outside that handler (CSRF/remember-me/custom cookies) do not happen automatically just because you switched the response from a redirect to 204.

## 10. `SecurityContext`, `HttpSession`, and Cookies: Knowing the Boundaries

### 10.1. `HttpSession.invalidate()` Does Not Equal Erasing All Traces

Invalidating the server-side session is an essential part, yet the browser may retain the old cookie; the user may hold other sessions on other devices; API tokens may still be alive. Never announce “all devices logged out” if only the current request's session was deleted.

An app may use Spring Session Redis to share `HttpSession` across multiple nodes. `SecurityContextLogoutHandler` still operates at the Servlet session layer, and invalidation can remove the session from the corresponding `SessionRepository`. Still, verify TTL, consistency, cookie IDs, node failover, and concurrent requests. Never use logs from a single node as absolute proof of multi-node logout.

### 10.2. Session Fixation and ID Changes on Login

Spring Security typically rotates the session ID after authentication to prevent session fixation. The pre-login cookie and post-login cookie can differ. Logout must apply to the **currently active session**, not a pre-login ID pointing to a superseded record.

Never disable session fixation protection to test logout. In `MockMvc`, capture the session from the **successful login** request and pass that session to `POST` logout as shown in the tests.

### 10.3. Cleaning Cookies with Exact Name/Path/Domain

If you want to instruct the browser to delete cookies:

- Identify actual cookies from `Set-Cookie`, whether `JSESSIONID` or `SESSION`.
- Identify `Path`/`Domain`/context path, `Secure`, `SameSite`, and proxy scope.
- Send deletion cookies with the exact name/path/domain and `Max-Age=0` or a past `Expires`.
- Understand that cookie deletion is supplementary, not a substitute for invalidating the server session.
- With Spring Session Redis, cookie settings may reside in `CookieSerializer` and differ from container defaults.

`LogoutConfigurer.deleteCookies(...)` or `CookieClearingLogoutHandler` can assist when using `LogoutFilter`; when writing custom MVC endpoints, attach equivalent cleanup explicitly if the product requires cookie deletion. Hardcoding `response.addCookie(new Cookie("JSESSIONID", ""))` without setting `Path`/`Max-Age` properly usually fails.

### 10.4. CSRF Tokens After Logout

In default configurations using a session-based `CsrfTokenRepository`, invalidating the session also renders the old session's token invalid. However, with `CookieCsrfTokenRepository` or custom mechanisms, you must **clear/rotate the CSRF token** appropriately; the standard logout DSL includes cleanup steps that custom MVC endpoints might miss.

After logout, if `/login` needs a fresh CSRF token, ensure a new token is issued when the next login form renders. Never keep a token from the old session and submit it for a new session.

### 10.5. Remember-Me Tokens and Auxiliary Cookies

Remember-me authentication can use cookies/tokens independent of `HttpSession`. If you only invalidate the session **without clearing remember-me**, the next request may automatically re-authenticate the user via remember-me, making it appear logout failed.

With `LogoutFilter`, Spring Security can coordinate `RememberMeServices`/`LogoutHandler` per config; when writing a custom MVC endpoint, incorporate remember-me cleanup explicitly. For persistent remember-me tokens, database/token series entries may need deletion. This is a strong reason to **prefer the standard logout DSL** unless custom needs dictate otherwise.

### 10.6. In-Flight Requests and Multiple Sessions

Another request may have loaded `SecurityContext` before logout occurred. Invalidating the session does not guarantee immediate cancellation of every **in-flight** request. If strict revocation is required, add extra checks such as session versioning, revocation lists, or authorization checks on sensitive actions.

Logging out in one browser does not mean logging out all devices. To support logout-all, index/query the principal's sessions in an appropriate repository and revoke each session/token under a dedicated policy. Never scan Redis session keys haphazardly in production using guessed string patterns.

## 11. Common Extension and Integration Points

| Need | Preferred approach | Notes |
| --- | --- | --- |
| Change logout URL | `LogoutConfigurer.logoutUrl(...)` | No MVC `@PostMapping` needed |
| Redirect to notice page | `LogoutConfigurer.logoutSuccessUrl(...)` | Post-logout page must be public |
| Return 204 or JSON | `LogoutConfigurer.logoutSuccessHandler(...)` | Preserves `LogoutFilter` pipeline |
| Add custom token/cookie cleanup step | `LogoutConfigurer.addLogoutHandler(...)` | Do not modify internal `LogoutFilter` directly |
| Delete specific cookies | `deleteCookies(...)` or `CookieClearingLogoutHandler` | Cookie name/path/domain must match |
| Destroy session and clear `SecurityContext` in MVC endpoint | `SecurityContextLogoutHandler.logout(...)` | Does not automatically run remaining handlers |
| Handle OAuth2/OIDC logout | Appropriate client/resource-server/OIDC logout config | May need IdP end-session endpoint |
| Revoke bearer/refresh tokens | Token revocation/introspection or provider mechanism | Session invalidation does not revoke JWTs |
| Log out all devices | Application-designed session index/revocation store | Not equivalent to current-session logout |
| Audit logout actions | Appropriate event/`LogoutHandler`/hook | Never log credentials/session IDs |

For a custom `LogoutHandler`, the API receives request, response, and `Authentication`; the handler should clean up safely and handle retries/idempotency where needed. If cleanup depends on an external service, define behavior on failure; never let an audit timeout turn into a UI showing “logged out” while the session remains alive.

In OAuth2 Login apps, logging out of the local session does not necessarily log out of the Identity Provider; users may immediately log back in via SSO upon visiting the login page. Distinguish **local logout**, **RP-initiated logout**, and **single logout** per protocol. Never use a lone `SecurityContextLogoutHandler` to claim all SSO sessions were erased.

## 12. Common Errors and Fixes

### Error 1 — `@PostMapping` on the Same Path Matched by `LogoutFilter`

Symptom: the controller does not log/run, yet logout requests still redirect. Cause: `LogoutFilter` sits ahead of MVC and already handled the URL. Fix: if you only need behavior tweaks, use `LogoutConfigurer`; if you truly need a controller, ensure `LogoutFilter` does not match the URL or disable it **intentionally**, taking responsibility for cleanup.

### Error 2 — Only Returning `"redirect:/login"`

Symptom: the frontend reports logout succeeded, yet refreshing a private page still works. Cause: neither session invalidation nor `SecurityContext` clearing occurred. Fix: call `SecurityContextLogoutHandler` with request/response/authentication or use standard `LogoutFilter`.

### Error 3 — Only Calling `SecurityContextHolder.clearContext()`

Symptom: the current request looks anonymous, yet the next request restores `Authentication` from `HttpSession`. Cause: persisted context was never erased. Fix: use `SecurityContextLogoutHandler`, session/repository cleanup, and verify with a fresh request.

### Error 4 — POST Logout Without CSRF Returns 403

This is normally expected behavior when CSRF is enabled. Fix: have forms submit a valid CSRF token, test with `spring-security-test`'s `csrf()`; never disable CSRF app-wide just to test with `curl`.

### Error 5 — `GET /account/logout` Does Nothing

When the controller declares only `@PostMapping`, GET will not trigger logout. This is intentional to prevent logout via a safe HTTP method. Never switch to `@GetMapping` just to make links clickable; use a form POST or `fetch` with CSRF.

### Error 6 — Remember-Me Immediately Logs Back In After Logout

Invalidating `HttpSession` is insufficient if remember-me cookies/persistent tokens remain valid. Fix: use `LogoutFilter` with matching cleanup, or in an MVC endpoint delete remember-me tokens/cookies per configured mechanism.

### Error 7 — Cookie Remains After Logout

Browser cookie presence does not automatically mean the server session is alive. Fix: test a new request to a private endpoint; if you also want the cookie deleted for UX, match name/path/domain/flags and `Max-Age=0` with `CookieSerializer`.

### Error 8 — Logging Out One Session Claims “All Devices Logged Out”

A single `SecurityContextLogoutHandler` called in the current request does not delete other sessions or issued JWTs. Fix: communicate only the accurate scope, or build a session index/revocation mechanism for logout-all requirements.

### Error 9 — Disabling `LogoutFilter` and Forgetting Other Default Handlers

Symptom: CSRF cookies/remember-me tokens are not cleaned, logout events do not fire, custom cookies stay valid. Fix: inventory all required handlers, add and test each behavior, or switch back to `LogoutConfigurer`.

### Error 10 — Using a Logout Controller in a Stateless API as If It Revoked JWTs

`SecurityContextLogoutHandler` cannot invalidate already-issued JWT signatures. Fix: use appropriate access-token TTLs, revocation/introspection/blocklists per threat model, refresh-token rotation/revocation, and IdP logout if applicable.

### Error 11 — Session Restored After Logout Due to a Custom Repository

The app may use a custom `SecurityContextRepository` or end-of-request logic saving `Authentication` back. Fix: check `saveContext`/repository clearing, filter ordering, custom caches, and test using the old session ID on a new request rather than only testing thread-local state inside the controller.

### Error 12 — Losing CSRF or Cookies on Post-Logout Redirect

Once the session is invalidated, the old token is gone. The new login page needs a fresh token/session when rendered. Check the CSRF repository, cookie serializer, and reverse-proxy interaction. Never try reusing old tokens.

### Error 13 — Logout Endpoint Not Authorized as Intended

With an MVC controller, `AuthorizationFilter` can still block requests before reaching the controller if the endpoint requires authentication or another chain matches earlier. Design behavior explicitly for anonymous logout vs. authenticated endpoints. With `LogoutFilter`, the endpoint can run early before authorization; the two approaches do not share identical `permitAll` requirements.

### Error 14 — Storing Request State in Singleton Handler Fields

A controller/`LogoutHandler` can be invoked concurrently by multiple requests. Never store `HttpServletRequest`, `Authentication`, or personal cookies in mutable fields. Pass data via parameters, use thread-safe services, and prevent cross-request leaks.

## 13. Testing and Production Deployment Checklist

Before deploying custom logout:

1. **Choose the mechanism:** `LogoutFilter`/`LogoutConfigurer` vs. MVC controller. Never let both “own” the same URL.
2. **Choose the HTTP method:** prefer POST with appropriate CSRF for session-cookie web apps; avoid state-changing GET.
3. **Verify routing:** logout URL belongs to the right `SecurityFilterChain`; POST reaches the right controller or `LogoutFilter`.
4. **Clear state properly:** handler invalidates `HttpSession` and clears `SecurityContext`; custom `SecurityContextRepository` is handled too.
5. **Return contract-compliant responses:** redirect/public success page, 204/200 JSON, never “success” before minimum cleanup completes.
6. **Verify CSRF:** POST missing tokens is blocked; post-logout tokens cannot be unlawfully reused.
7. **Verify cookies:** sessions are no longer valid even when old cookies are resent; if deleting cookies, match name/path/domain.
8. **Don't forget remember-me:** clear cookies or token stores matching the app's mechanism.
9. **Check multiple sessions/devices:** current-session logout differs from logout-all; have dedicated revocation policies if required.
10. **Evaluate SSO/OIDC/tokens:** local logout does not replace IdP logout or token revocation.
11. **Protect sensitive data:** never log raw passwords, `JSESSIONID`/`SESSION`, CSRF tokens, or `Authorization` headers.
12. **Test `MockMvc` and real HTTP:** login → private 200 → logout → private redirected/challenged; test GET/POST missing CSRF and old-cookie requests.
13. **Test multi-node environments:** Spring Session Redis/JDBC/replication; new requests after logout on another node must not restore the old session.
14. **Handle cleanup errors:** account for auditing, rate limits, and observability per policy; never sacrifice session deletion due to a failing audit dependency.
15. **Verify versions:** validate behavior on the exact Spring Boot/Spring Security/Servlet container versions deployed, especially with custom repositories and CSRF token storage.

## 14. Practice Scenarios

**Question 1.** You want to change `POST /logout` to `POST /account/logout` and return 204. Do you need `@RestController`?

**Answer:** Not necessarily. You can use `logoutUrl("/account/logout")` and a `logoutSuccessHandler` returning 204 inside `LogoutConfigurer`, preserving the default `LogoutHandler`s.

**Question 2.** If you write `@PostMapping("/account/logout")` while `SecurityFilterChain` already configures `logoutUrl("/account/logout")`, will the controller run?

**Answer:** Usually not; `LogoutFilter` handles matching URLs before reaching `DispatcherServlet`. Pick a single owner for the path.

**Question 3.** Is calling `SecurityContextHolder.clearContext()` alone enough to log out?

**Answer:** Not guaranteed. `SecurityContext` may already be saved in `HttpSession`; later requests may reload it. Use `SecurityContextLogoutHandler` or the standard pipeline to handle the session/repository.

**Question 4.** `POST` logout without a CSRF token returns 403. Is that a password error?

**Answer:** No. `CsrfFilter` can reject the request before the controller/logout filter, protecting state-changing actions.

**Question 5.** After `LogoutHandler`, the `JSESSIONID` cookie remains in the browser yet `GET /private` redirects to `/login`. Is the user still logged in?

**Answer:** Not under the invalidated session. The old cookie has no valid server session; adding cookie deletion is a supplementary measure per contract.

**Question 6.** Why does refreshing after a successful logout show the user logged back in via remember-me?

**Answer:** Remember-me tokens/cookies can operate independently of `HttpSession`. If a custom endpoint skips remember-me cleanup, subsequent requests can create a new `Authentication`.

**Question 7.** Does `SecurityContextLogoutHandler` delete access JWTs across all devices?

**Answer:** No. Stateless JWTs require dedicated revocation/expiry policies, and logout-all requires multi-device session/token revocation design.

**Question 8.** Should `GET /logout` be opened to make creating hyperlinks convenient?

**Answer:** Avoid logout via GET because GET is a safe method that browsers/crawlers/prefetching can trigger. Use a form POST with a CSRF token.

**Question 9.** When using Spring Session Redis, does calling `invalidate()` on node A stop node B from accepting that session?

**Answer:** With a properly working shared `SessionRepository`, new requests on B will not find the invalidated session; still test consistency, caching, and in-flight requests.

**Question 10.** A controller returns `302 /logged-out` without anyone calling a logout handler. How do you verify the bug?

**Answer:** Log in, invoke the controller, then send `GET /private` with the old session cookie. If it still returns 200, logout failed to clear state. Add `SecurityContextLogoutHandler` or use `LogoutFilter`.

## Conclusion

**Preferred approach:** if you only need to change the URL, status code, redirect, or an extra cleanup step, use **`HttpSecurity.logout(...)`** to preserve the `LogoutFilter` pipeline and configured handlers.

**When genuinely using a custom MVC endpoint:** `POST` logout must reach the controller, CSRF must remain enforced, the controller calls **`SecurityContextLogoutHandler.logout(request, response, authentication)`** to invalidate the session and clear `SecurityContext`, and only then decides the HTTP response. Cleanups outside that handler (custom CSRF repositories, remember-me, custom cookies, tokens/IdP, other sessions) **must be handled explicitly per system architecture**.

A proper logout is judged not by a page displaying “Logout successful,” but by **new requests with old credentials/sessions no longer being granted unintended access**, across the right `SecurityFilterChain` and every required node.