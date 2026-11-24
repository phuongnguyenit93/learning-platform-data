# ServerLogoutHandler, ServerLogoutSuccessHandler, and Clearing Context in Spring Security WebFlux

## Learning Objectives

After completing this lesson, you will be able to:

1. Explain how `LogoutWebFilter` handles logout requests in **Spring Security reactive/WebFlux**, separating two responsibilities: **state cleanup** via `ServerLogoutHandler` and **success response** via `ServerLogoutSuccessHandler`.
2. Understand the differences between clearing `SecurityContext` from `ServerSecurityContextRepository`, invalidating the entire `WebSession`, handling CSRF tokens, expiring browser cookies, and revoking tokens/sessions at an identity provider.
3. Use `SecurityContextServerLogoutHandler`, `WebSessionServerLogoutHandler`, and `DelegatingServerLogoutHandler` properly; avoid replacing the default handler and accidentally omitting context cleanup.
4. Choose `RedirectServerLogoutSuccessHandler` for browsers, or `HttpStatusReturningServerLogoutSuccessHandler` for APIs wanting only an HTTP status code; distinguish cleanup handlers from response-producing handlers.
5. Configure safe `POST /logout` with CSRF, demonstrated with Java 17+ / Spring Boot 3.x, and verify via `WebTestClient` and a real browser.
6. Recognize fake-logout bugs: the response reports "success" while the session, `SecurityContext`, token, or client data remains usable.

> This lesson covers **Spring Security reactive**. Servlet interfaces `LogoutHandler`, `LogoutSuccessHandler`, and `SecurityContextLogoutHandler` have similar names but different signatures and APIs. In WebFlux, you must use **`ServerLogoutHandler`**, **`ServerLogoutSuccessHandler`**, `ServerHttpSecurity`, and `SecurityWebFilterChain`.

## 1. Logout Is Not Simply Redirecting to an HTML Page

For session-based login applications, the goal of logout is to guarantee that **subsequent requests can no longer access protected resources** using the logged-out session state. Returning a "You are logged out" page or redirecting to login is only the **UI** part; if `SecurityContext` remains in the repository, the next request can still be authenticated.

A logout flow typically requires the following layers:

| Layer | Question to resolve | Related reactive tools |
| --- | --- | --- |
| HTTP request | Which request actually requests logout? | `LogoutWebFilter`, `logoutUrl`/`requiresLogout` |
| CSRF | Is this a POST genuinely initiated by the user? | `CsrfWebFilter`, `ServerCsrfTokenRepository` |
| Security context | Does `Authentication` remain stored in the repository? | `SecurityContextServerLogoutHandler` |
| WebSession | Should the **entire** server-side session be invalidated? | `WebSessionServerLogoutHandler` |
| Side effects | What audit logging or application-state cleanup is needed? | Custom `ServerLogoutHandler` |
| HTTP response | Redirect the user to login or return 204? | `ServerLogoutSuccessHandler` |
| Client/IdP | Are session cookies/tokens or external SSO sessions still alive? | Cookie policy, token revocation, OIDC logout per architecture |

**Core definition:** application-side logout succeeds when authentication state is removed per policy; a successful HTTP redirect does not prove that by itself. After logout, verify with a **new request** reusing the old cookie to access a protected resource.

## 2. Processing Flow of LogoutWebFilter

Spring Security WebFlux orders `WebFilter`s according to `SecurityWebFiltersOrder`. In standard configurations, logout is handled by `LogoutWebFilter` before final exchange authorization. When a request matches the logout matcher, the filter executes handlers instead of invoking a normal logout controller.

```text
Browser / client
    |
    | POST /logout + session Cookie + valid CSRF token
    v
Security WebFilter chain
    |
    +--> CsrfWebFilter: validates token for POST
    |       |
    |       +--> Missing/invalid: usually 403; logout not executed
    |
    +--> LogoutWebFilter: does matcher match POST /logout?
            |
            +--> No: continue chain -> authorization/controller
            |
            +--> Yes: obtain Authentication from current context
                    |
                    v
            ServerLogoutHandler.logout(exchange, authentication)
                    |
                    +--> Clear SecurityContext from repository
                    +--> Optional per config: invalidate WebSession
                    +--> Optional per config: audit/other cleanup
                    |
                    v
            ServerLogoutSuccessHandler.onLogoutSuccess(...)
                    |
                    +--> 302/303 redirect to target page
                    |    or
                    +--> 200/204 for API
                    |
                    v
            Request complete
```

This diagram is a learning model, not a guarantee that every filter always runs: chains, matchers, CSRF repositories, authentication mechanisms, and handlers can all be customized. If the cleanup handler returns `Mono.error(...)`, do not assume the success handler still runs; observe and handle errors properly.

### Three primary methods

```java
// Spring Security WebFlux API signatures, illustrative only:

Mono<Void> ServerLogoutHandler.logout(
        WebFilterExchange exchange,
        Authentication authentication);

Mono<Void> ServerLogoutSuccessHandler.onLogoutSuccess(
        WebFilterExchange exchange,
        Authentication authentication);

// Configuration:
http.logout(logout -> logout
        .logoutHandler(myCleanupHandler)
        .logoutSuccessHandler(myResponseHandler));
```

- `WebFilterExchange` carries `ServerWebExchange` and the corresponding filter chain.
- `Authentication` may be present or absent depending on context. Audit code must not call `getName()` when `authentication == null`.
- `Mono<Void>` signals **completion or error** of an operation with no data value; you must **return the publisher**, never call `subscribe()` to run "in the background" and report success early.
- `ServerLogoutHandler` is responsible for handling **state**. `ServerLogoutSuccessHandler` is responsible for the HTTP response once cleanup finishes.
- `ServerLogoutSuccessHandler` does not mean "every cookie/token in the ecosystem was deleted"; it only reflects the completion of tasks the application logout flow actually performs.

**Do not accidentally write the Servlet API:**

```java
// Wrong stack in WebFlux, illustrating anti-pattern only:
// void logout(HttpServletRequest req, HttpServletResponse res, Authentication auth)
// void onLogoutSuccess(HttpServletRequest req, HttpServletResponse res, Authentication auth)
```

Servlet signatures using `HttpServletRequest` and `HttpServletResponse` are not the contract of `ServerLogoutHandler` in WebFlux.

## 3. WebFlux Default: Clears SecurityContext, Not Implying Whole WebSession Is Destroyed

Spring Security 6.5 reactive logout documentation describes:

- Spring Security provides a default logout endpoint. When logged in, `GET /logout` may render a **confirmation page**; `POST /logout` executes logout.
- The default flow clears state in `ServerCsrfTokenRepository` and `ServerSecurityContextRepository`, then redirects back to the login page.
- If the app wants to **invalidate the entire `WebSession`**, add `WebSessionServerLogoutHandler` to the logout configuration.

The last point is crucial: **clearing the security context does not automatically mean full session invalidation**. Distinguish the operations rather than taking Servlet's `SecurityContextLogoutHandler` behavior and assuming it applies to WebFlux.

| Operation | Affected target | What it does NOT guarantee |
| --- | --- | --- |
| `SecurityContextServerLogoutHandler` | `SecurityContext` stored in `ServerSecurityContextRepository` | Destroying all `WebSession` attributes; revoking JWT/refresh tokens |
| `WebSessionServerLogoutHandler` | Current server-side `WebSession` | Revoking tokens at identity providers; clearing `localStorage` data |
| Default logout flow's CSRF cleanup | Token in `ServerCsrfTokenRepository` | Deleting arbitrary client cookies/resources |
| Browser cookie expiration | Browser cookie carrying session ID (if response configured properly) | Invalidating server-side session if server did not clean up |
| Success redirect | HTTP message/destination | Running missing cleanup |

### Why is clearing SecurityContext mandatory?

Suppose `WebSession` holds an attribute containing the logged-in `SecurityContext`. If you only redirect to `/login?logout` while the repository still returns `Authentication` when the browser sends the old cookie, the next request can still be authenticated. `SecurityContextServerLogoutHandler` calls the `ServerSecurityContextRepository` method to remove the saved state; by default, the handler uses `WebSessionServerSecurityContextRepository`. If the app swaps the context repository, ensure logout uses a repository with **matching semantics** to where authentication was saved.

### Why is invalidating WebSession also needed?

A `WebSession` can hold data besides `SecurityContext`: shopping carts, UI preferences, saved requests, CSRF tokens, or application-stored attributes. When policy requires keeping no session after logout, `WebSessionServerLogoutHandler` triggers session invalidation. This renders the old session invalid on the server side and removes session attributes per the session store mechanism.

Not every app wants to wipe all auxiliary session data, so **adding session invalidation** is a design decision. However, if security policy states "logout deletes the entire session", do not call only `SecurityContextServerLogoutHandler` and assume it suffices.

### Clearing Session != deleting browser cookies

`WebSession.invalidate()` invalidates state on the server; the browser can still resend the old session ID cookie if the response has not expired the cookie. Once the server-side session is invalid, the old cookie must not count as proof of login. If UX/privacy requirements call for immediate cookie deletion, configure an expiring `Set-Cookie` with the **matching name, path, domain, `Secure`, and `SameSite`** per infrastructure, and verify in a browser. WebFlux normally uses the `SESSION` cookie, though name/path are customizable—not Servlet's default `JSESSIONID`.

### Reactor Context differs from SecurityContext repository

`ReactiveSecurityContextHolder` carries authentication in the Reactor Context of the **current subscription**. `ServerSecurityContextRepository` governs whether a security context can be loaded in the **next request**. Therefore:

- Do not "log out" by calling Servlet thread-local `SecurityContextHolder.clearContext()`.
- Do not merely insert `ReactiveSecurityContextHolder.clearContext()` into an arbitrary pipeline and treat that as deleting a session; that operator affects pipeline context, **not replacing removal of durable data** from the repository.
- After logout, the decisive criterion is that a new request using the old cookie no longer sees an authorized `Authentication`.

## 4. Three Handlers to Remember

### 4.1. SecurityContextServerLogoutHandler

Class: `org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler`.

It implements `ServerLogoutHandler`, primarily removing `SecurityContext` via `ServerSecurityContextRepository`. Its default constructor works with `WebSessionServerSecurityContextRepository`. When using a custom repository, attach the corresponding repo:

```java
// Illustrative snippet given an existing ServerSecurityContextRepository repository:
SecurityContextServerLogoutHandler clear =
        new SecurityContextServerLogoutHandler();
clear.setSecurityContextRepository(repository);
```

No custom repo configuration is needed for a demo using default form login. Avoid clearing only `Authentication` in a local variable: state for the next request may still remain in the repository.

### 4.2. WebSessionServerLogoutHandler

Class: `org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler`.

It implements `ServerLogoutHandler` and invalidates the current `WebSession`. Use it when logout requires deleting the entire session, especially in browser/session-based apps. Do not use it to revoke stateless JWTs, database refresh tokens, or Identity Provider SSO sessions; those tasks require separate mechanisms.

### 4.3. DelegatingServerLogoutHandler

Class: `org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler`.

It allows combining multiple `ServerLogoutHandler`s into a single handler wired into the DSL:

```java
ServerLogoutHandler cleanup = new DelegatingServerLogoutHandler(
        new SecurityContextServerLogoutHandler(),
        new WebSessionServerLogoutHandler()
);
```

This is the exact structure Spring Security uses in its **official reactive logout example** when session invalidation is needed.

**Caution:** `logout.logoutHandler(custom)` in Spring Security 6.5 **replaces previously configured logout handlers** rather than guaranteeing it merely appends a side effect to the default. If you assign a custom handler to log events and omit `SecurityContextServerLogoutHandler`, you can cause the HTTP redirect to "succeed" while failing to clear the context properly. When multiple tasks are needed, compose them and test.

Furthermore, if strict ordering between business operations is required, **do not infer completion order solely from the delegate list**. Check the implementation behavior for your exact version or explicitly build a handler returning a publisher composed with `then(...)` to express the desired sequence. Security cleanup must stay primary, unobstructed by peripheral side effects.

## 5. ServerLogoutSuccessHandler: Response After Cleanup

The `ServerLogoutSuccessHandler` interface takes `WebFilterExchange` and `Authentication`, returning `Mono<Void>`. It runs **after the logout handler completes successfully** in `LogoutWebFilter`'s flow; it does not replace clearing the session/context.

Two common implementations:

| Handler | Response | When appropriate |
| --- | --- | --- |
| `RedirectServerLogoutSuccessHandler` | Redirects the browser to a chosen URL; default is typically `/login?logout` | Form-login apps with UI navigation |
| `HttpStatusReturningServerLogoutSuccessHandler` | Returns HTTP status; defaults to 200, configurable to 204 | APIs/SPAs handling navigation client-side |

Redirect to a **fixed, internal** URL:

```java
RedirectServerLogoutSuccessHandler success =
        new RedirectServerLogoutSuccessHandler();
success.setLogoutSuccessUrl(URI.create("/signed-out"));

// Used inside ServerHttpSecurity configuration:
http.logout(logout -> logout.logoutSuccessHandler(success));
```

The snippet above assumes imports for `java.net.URI` and an `http` builder. Never pass a redirect URL taken directly from an unvalidated query string without an allowlist (open-redirect risk).

APIs not wanting a redirect can use:

```java
new HttpStatusReturningServerLogoutSuccessHandler(HttpStatus.NO_CONTENT)
```

This snippet requires importing `org.springframework.http.HttpStatus` and the reactive success handler class. 204 carries no response body; if the client must clear local UI data, the client still needs to perform that step. Do not confuse Servlet `LogoutSuccessHandler` with reactive `ServerLogoutSuccessHandler`.

### An audit handler should be a cleanup side effect, not fake success

You can use a custom `ServerLogoutHandler` to record audit/metrics after a valid logout request; log minimal data (e.g., event type, correlation ID), never cookies, access tokens, session IDs, CSRF tokens, or passwords. If auditing targets an unreliable secondary system, consider timeout/failure policies so it does not hang logout or introduce races. When attaching an audit handler, **preserve context cleanup**.

## 6. Runnable Java 17+ WebFlux Example: Clearing SecurityContext and Invalidating WebSession

This Spring Boot 3.x example uses default form login, a local user, a protected URL, and upon logout:

1. `SecurityContextServerLogoutHandler` clears the saved authentication context.
2. `WebSessionServerLogoutHandler` invalidates the server-side session.
3. `RedirectServerLogoutSuccessHandler` sends the user to the public `/signed-out` page.

### 6.1. Dependencies

In a Gradle project already configured with the Spring Boot plugin and dependency management:

**`build.gradle`** (dependencies section):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Do not add `spring-boot-starter-web` to this demo: when both MVC and WebFlux are present, Spring Boot normally selects Servlet by default.

File structure:

```text
src/
  main/
    java/example/logout/
      LogoutDemoApplication.java
      ReactiveLogoutSecurityConfig.java
      SiteController.java
  test/
    java/example/logout/
      LogoutFlowTest.java
```

### 6.2. Main class

**`src/main/java/example/logout/LogoutDemoApplication.java`**:

```java
package example.logout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LogoutDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LogoutDemoApplication.class, args);
    }
}
```

### 6.3. SecurityWebFilterChain and logout handlers

**`src/main/java/example/logout/ReactiveLogoutSecurityConfig.java`**:

```java
package example.logout;

import java.net.URI;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.RedirectServerLogoutSuccessHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.ServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class ReactiveLogoutSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails member = User.withUsername("member")
                .password(encoder.encode("local-demo-pass"))
                .roles("USER")
                .build();

        return new MapReactiveUserDetailsService(member);
    }

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        ServerLogoutHandler cleanup = new DelegatingServerLogoutHandler(
                new SecurityContextServerLogoutHandler(),
                new WebSessionServerLogoutHandler()
        );

        RedirectServerLogoutSuccessHandler success =
                new RedirectServerLogoutSuccessHandler();
        success.setLogoutSuccessUrl(URI.create("/signed-out"));

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/", "/signed-out", "/favicon.ico")
                            .permitAll()
                        .anyExchange().authenticated()
                )
                .formLogin(Customizer.withDefaults())
                .httpBasic(basic -> basic.disable())
                .logout(logout -> logout
                        .logoutHandler(cleanup)
                        .logoutSuccessHandler(success)
                )
                .build();
    }
}
```

### 6.4. Protected endpoint and post-logout destination page

**`src/main/java/example/logout/SiteController.java`**:

```java
package example.logout;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class SiteController {

    @GetMapping("/")
    public Mono<String> home() {
        return Mono.just("Welcome");
    }

    @GetMapping("/private")
    public Mono<String> privatePage() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context -> "Hello " +
                        context.getAuthentication().getName());
    }

    @GetMapping("/signed-out")
    public Mono<String> signedOutPage() {
        return Mono.just("Signed out");
    }
}
```

**Important note:** `/signed-out` is a **public** route. Without `permitAll()` on this URL, the logout handler could redirect to a URL requiring authentication and immediately get redirected onward to `/login`. The controller returns only a demo string, while a real logout confirmation page can be HTML/a template.

### 6.5. Step-by-step in the example

1. User `member` has a password hashed via `DelegatingPasswordEncoder`. Hardcoded sample passwords are for local demos only; never use this account in public deployments.
2. `formLogin(Customizer.withDefaults())` enables Spring Security's default login page rendered at `GET /login`, processes the POST form, and persists authentication state in the session.
3. `httpBasic(...disable())` disables only HTTP Basic to avoid entry-point confusion; it does not disable CSRF or logout.
4. `POST /logout` matches the default matcher and is protected by CSRF. There is no `@PostMapping("/logout")` controller because `LogoutWebFilter` handles it directly.
5. `DelegatingServerLogoutHandler` combines clearing `SecurityContext` and invalidating `WebSession`. **Always retain `SecurityContextServerLogoutHandler` when using a custom `logoutHandler`**, avoiding replacing it with a plain audit side effect.
6. `RedirectServerLogoutSuccessHandler` runs after cleanup, sending the browser to `/signed-out`; it does not verify passwords or execute session cleanup itself.
7. Controller `/private` reads the principal via `ReactiveSecurityContextHolder`. After logout, a **new request** can no longer access the controller using the old session.

There is no `block()` or manual `subscribe()` in `WebFilter`s/controllers. Every reactive operation returns `Mono` so the framework manages subscriptions.

### 6.6. Running and testing with a browser

In a project with Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

On localhost, default port 8080:

1. Open `http://localhost:8080/`: body `Welcome`.
2. Open `http://localhost:8080/private` while not logged in: the browser redirects to `/login`.
3. Enter user `member` and password `local-demo-pass` in the default form, keeping the session cookie returned by the app.
4. Open `/private`: see `Hello member`.
5. Open `/logout` in the browser while logged in: when using the default confirmation page, submit **POST** from the form containing CSRF. Do not confuse viewing the confirmation page via GET with the logout action.
6. Follow the redirect to `/signed-out`: see `Signed out`.
7. Reopen `/private` **in the same browser**: prompted to log in again, because the prior context/session is no longer valid.

The crucial step is **step 7**. Merely seeing `Signed out` in step 6 does not prove cleanup worked properly.

If sending POST manually via `curl`, first GET the page containing the token, save the cookie jar, and then send the matching form-encoded `_csrf`; never copy token strings from documentation. For WebFlux sessions, the cookie name is usually `SESSION`, though it can be configured differently.

## 7. CSRF and Logout Method: Why Use POST?

Spring Security WebFlux enables CSRF by default, and `LogoutWebFilter` handles **POST /logout** by default. This prevents third parties from triggering logout merely by placing a GET link/image on another website. `GET /logout` can display only a confirmation page offering a POST form with a CSRF token.

Example form in a Thymeleaf template (assuming the CSRF token is exposed in the model or integrated with Thymeleaf per app configuration):

```html
<form th:action="@{/logout}" method="post">
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <button type="submit">Log out</button>
</form>
```

This is a template fragment, **not standalone HTML with an auto-generated token**. In templates using `th:action`, Spring/Thymeleaf integration may inject the hidden CSRF input automatically; if auto-injected, avoid duplicating the manual input. Inspect rendered HTML and validate tokens against the matching cookie/session.

**Do not turn GET into an actual logout** just to use an `<a href="/logout">` link. If a custom `requiresLogout(...)` accepts any HTTP method, browsers can be logged out via cross-site GETs, violating the principle that safe methods do not mutate state. Use a POST button/form or JS triggering a POST with a valid token.

### Missing CSRF differs from logout handler failure

| Scenario | Typical result | Stage |
| --- | --- | --- |
| GET `/logout` | 200 HTML confirmation (when default page is present) | Not cleaned up yet |
| POST `/logout` missing CSRF | Usually 403 | Blocked by CSRF filter; logout not run |
| POST `/logout` with valid CSRF | 3xx redirect in demo | Cleanup done, success handler |
| POST custom `/signout` with unconfigured URL | Does not match logout matcher | May fall through to authorization/404 |
| Logout handler emits error | Success handler must not be treated as having succeeded | Error must be handled/observed |
| GET `/private` in same browser after logout | Redirect to login | Old session no longer authenticated |

Spring Security 6.5 WebFlux docs specify that the default `ServerCsrfTokenRepository` stores tokens in `WebSession`. With cross-origin frontends, cookies/headers and `SameSite` may require custom configuration; CORS does not replace CSRF.

## 8. Testing with WebTestClient

Testing should verify three levels: (1) matcher and CSRF, (2) success handler produces the expected response, and (3) new requests are no longer authenticated after real logout.

### 8.1. Testing matcher/CSRF/success redirect

Use Spring Security Test to attach a mock `Authentication` to a request and inject valid CSRF. These tests **do not replace** full browser/session lifecycle tests.

**`src/test/java/example/logout/LogoutFlowTest.java`**:

```java
package example.logout;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class LogoutFlowTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void signedOutPageIsPublic() {
        client.get().uri("/signed-out")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("Signed out");
    }

    @Test
    void anonymousPrivatePageRedirectsToLogin() {
        client.get().uri("/private")
                .accept(MediaType.TEXT_HTML)
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectHeader().valueMatches("Location", ".*login.*");
    }

    @Test
    void postLogoutWithoutCsrfIsForbidden() {
        client.mutateWith(mockUser("member"))
                .post().uri("/logout")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void postLogoutWithCsrfRedirectsToCustomPage() {
        client.mutateWith(mockUser("member"))
                .mutateWith(csrf())
                .post().uri("/logout")
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectHeader().valueEquals("Location", "/signed-out");
    }
}
```

Run with Gradle Wrapper:

```bash
./gradlew test --tests example.logout.LogoutFlowTest
```

PowerShell:

```powershell
.\gradlew.bat test --tests example.logout.LogoutFlowTest
```

**Expected result:** all four tests PASS when the app matches the demo files and compatible dependencies. This is an expected result, **not** a compile/test run actually executed on your project.

Explanation:

- `springSecurity()` wires security filters into mock `WebTestClient`.
- `mockUser("member")` mocks `Authentication` for **a single test request**. It does not create a real browser session, so do not treat this redirect test as proof that an old session was deleted.
- `csrf()` supplies a valid CSRF token for the test POST. The tokenless test gets 403, proving logout requests must pass the CSRF layer.
- `Location: /signed-out` confirms the custom `ServerLogoutSuccessHandler` issued the redirect after the logout pipeline ran.
- `anonymousPrivatePageRedirectsToLogin` only proves anonymous policy; to confirm logout actually deletes the session, test the **same logged-in cookie** before and after.

### 8.2. What should a real session test look like?

A full integration test should follow the exact cookie jar steps:

```text
1. GET /private anonymous                  -> redirect /login
2. GET /login                              -> obtain CSRF + session cookie
3. POST /login with username/password/CSRF -> success redirect
4. GET /private with same cookie           -> 200; principal == member
5. GET /logout (if using confirmation form)-> fresh/valid CSRF
6. POST /logout with cookie + CSRF         -> redirect /signed-out
7. GET /private using old session cookie   -> redirect /login
```

When automating, use `WebTestClient` with an exchange filter/cookie jar, or test against a live server with a client tracking `Set-Cookie` and cookies across requests. Account for CSRF tokens being issued or rotated across login/logout. **Do not** grab a token from the prior session and assume it always works after login/logout. For HTTP Basic or stateless JWTs, design different verification: a client might still re-authenticate using old credentials/unrevoked tokens.

### 8.3. Verifying the session is invalidated

Beyond status codes, inspect in a controlled test/diagnostics environment:

- The old cookie cannot access protected endpoints after logout.
- When using Spring Session with Redis, the old session record is no longer valid per the session store mechanism.
- Sensitive session attributes, if any, are never reused after invalidation.
- Logout audits record the right event counts without logging raw passwords/tokens/session IDs.
- Error responses do not leak stack traces or security-context cookies.

Use live-server tests to catch differences in cookie path/domain, TLS proxies, browser `SameSite`, and distributed session stores; mock tests cannot cover everything.

## 9. Customizing the Logout URL and Response for Other Applications

### 9.1. Changing the endpoint from /logout to /signout

WebFlux 6.5 DSL allows:

```java
.logout(logout -> logout
        .logoutUrl("/signout")
        .logoutHandler(cleanup)
        .logoutSuccessHandler(success))
```

This is a **chain configuration snippet**, assuming `cleanup` and `success` were created as in section 6. `logoutUrl("/signout")` changes the default POST URL that triggers logout; it does not auto-generate a custom GET HTML confirmation form matching the old `/logout` page. If you have a "Log out" link/menu, update the form action to `/signout` and ensure CSRF is sent.

### 9.2. API needing only 204 No Content

If the client is a web app/SPA handling navigation itself:

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.web.server.authentication.logout
        .HttpStatusReturningServerLogoutSuccessHandler;

// One line inside the logout DSL:
.logoutSuccessHandler(
        new HttpStatusReturningServerLogoutSuccessHandler(
                HttpStatus.NO_CONTENT))
```

This is an **illustrative sample**, not a standalone Java file; in real code, the second import must sit **on one line** or be formatted as a valid Java import by your IDE. The handler returns 204 instead of redirecting. Clearing the security context and invalidating the session **do not change automatically with the response handler**; `ServerLogoutHandler` must still be configured.

When the client receives 204, it typically needs to actively clear UI state, in-memory tokens, and sensitive data caches. If a refresh token remains active on the server, 204 does not automatically revoke it.

### 9.3. Adding an audit handler while preserving cleanup

A reactive audit side effect can be implemented as:

```java
// Illustrative sample inside a config class that already has Logger log:
ServerLogoutHandler audit = (exchange, authentication) ->
        Mono.fromRunnable(() -> log.info(
                "Logout accepted; principalPresent={}",
                authentication != null
        ));

ServerLogoutHandler combined = new DelegatingServerLogoutHandler(
        new SecurityContextServerLogoutHandler(),
        new WebSessionServerLogoutHandler(),
        audit
);
```

Here `Mono.fromRunnable(...)` runs only when the publisher is subscribed in the logout chain. `log` is a logger you must declare (e.g., SLF4J), and logout/Reactor classes must be imported; this is an **extension snippet, not a standalone program**. Never log usernames, tokens, cookie IDs, or the full `Authentication` object without an appropriate policy and data scrubbing. Never pass `audit` alone to `logoutHandler(audit)` and accidentally drop context cleanup.

If auditing requires strict ordering relative to other side effects, specify it explicitly in a composed publisher chained with `then(...)`; do not rely on constructor ordering if delegate semantics do not guarantee what you need.

## 10. Common Logout Mistakes

| Symptom / error | Cause | Fix |
| --- | --- | --- |
| Shows "Logged out" yet GET `/private` still works | Only redirected or cleared a local flag without clearing repository | Use `SecurityContextServerLogoutHandler` and test a new request with the old cookie |
| Context cleared yet session attributes remain | Did not invalidate `WebSession` | Compose `WebSessionServerLogoutHandler` when policy requires |
| Setting `logoutHandler(customAudit)` broke cleanup | Setter replaces default handlers in WebFlux 6.5 | Compose default cleanup + audit, and test |
| POST `/logout` gets 403 | Missing/wrong CSRF token or mismatched session cookie | Fetch valid token from form/session; keep CSRF |
| GET `/logout` does not log out | GET is usually only the confirmation page | Send POST + CSRF; do not arbitrarily switch matcher to GET |
| Post-logout redirect causes loop | Success URL requires authentication | `permitAll()` the public post-logout page |
| Status 204 yet client still shows username | Client cache/local UI was not cleared | Client clears state, reloads protected resource to verify |
| Browser cookie deleted yet server session remains | Only expired cookie, did not invalidate server-side | Clear session/context on server and guard ID reuse |
| Session invalidated yet bearer JWT still works | Stateless token was not revoked | Account for TTL, revocation/denylist/refresh rotation per design |
| Logged out of app only; OIDC IdP remains logged in | App logout differs from SSO single logout | Use OIDC RP-initiated logout or matching protocol when needed |
| Using Servlet `SecurityContextHolder.clearContext()` | Does not clear reactive `SecurityContext` repository | Use appropriate reactive handlers |
| Custom handler calls `subscribe()` and returns empty | Logout response may return before cleanup | Return cleanup's `Mono<Void>` properly, no fire-and-forget |
| Auxiliary cleanup throws exception, redirect never happens | Publisher errored and flow aborted | Monitor/design failure policy; never claim logged out when state is dirty |
| Logout has no audit | Missing operational event | Log minimal audit event, scrubbing secret data |
| Test uses `mockUser()` and claims session deleted | Mock user does not represent real cookies/sessions | Add login/logout integration test with real cookies |
| Multi-node sessions not shared | Node-hopping causes inconsistent behavior | Use shared store / appropriate session strategy |

### Pre-production checklist

1. Proper **WebFlux** configuration: `ServerHttpSecurity`, `SecurityWebFilterChain`, `ServerLogoutHandler`, `ServerLogoutSuccessHandler`.
2. Logout only happens on POST with valid CSRF or an evaluated equivalent safeguard. Never let GET delete sessions without compelling justification.
3. After logout, `ServerSecurityContextRepository` no longer supplies a logged-in security context for the old session.
4. If policy requires, the entire `WebSession` is invalidated; verify attributes and the session store.
5. The response handler runs only after cleanup succeeds; redirects or 204 responses are tested.
6. Cookies have appropriate `Secure`/`HttpOnly`/`SameSite`/path/domain; TLS proxy and session store are properly configured.
7. After logout, requests reusing the old cookie cannot reach protected resources.
8. For JWT, OIDC, or OAuth2, clearly separate local logout, refresh token revocation, and IdP logout as **three distinct boundaries**.
9. Audits include correlation IDs without logging passwords, tokens, raw cookies, or full principal objects.
10. Test CSRF failure, cleanup success, redirect success, session invalidation, and errors in custom handlers.

## 11. Practice Questions

1. Why can setting `logoutSuccessHandler(...)` while omitting `logoutHandler(...)` create a "fake logout"? Distinguish each interface's responsibility.
2. An app uses only `SecurityContextServerLogoutHandler`, leaving a shopping cart in `WebSession`. Is that a bug in every app or policy-dependent? When must `WebSessionServerLogoutHandler` be added?
3. Create a custom `ServerLogoutHandler` that writes an audit entry (with no sensitive data), compose it with the two cleanup handlers, and test the response.
4. Change the logout URL to `/signout`. Write a proper HTML/Thymeleaf form with `method="post"` and CSRF, and test without a token to confirm 403.
5. Replace the redirect with `HttpStatusReturningServerLogoutSuccessHandler(HttpStatus.NO_CONTENT)`. Explain the remaining work on the SPA client.
6. Run a full integration test: real form login, save cookie, POST logout, call `/private` with the old cookie. Which result proves logout succeeded?
7. Suppose the session is invalidated while a JWT access token has not expired. Why can requests carrying the old JWT still authenticate? Design a way to bound the risk.
8. If using a custom `ServerSecurityContextRepository`, explain why the context-clearing handler must be configured with the same repository and what to test.

**Conclusion:** in WebFlux, **`ServerLogoutHandler` performs state cleanup**, and **`ServerLogoutSuccessHandler` decides the HTTP response**. `SecurityContextServerLogoutHandler` clears context, `WebSessionServerLogoutHandler` invalidates the entire session when needed, and `DelegatingServerLogoutHandler` combines steps. Require POST + CSRF and re-verify with a new request; a neat redirect does not substitute for real logout.

## Official Documentation

- [Spring Security 6.5 — Reactive Logout](https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/logout.html)
- [Spring Security 6.5 — WebFlux CSRF (including logout)](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security 6.5 — ServerHttpSecurity.LogoutSpec API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.LogoutSpec.html)
- [Spring Security 6.5 — SecurityContextServerLogoutHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/logout/SecurityContextServerLogoutHandler.html)
- [Spring Security 6.5 — DelegatingServerLogoutHandler API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/logout/DelegatingServerLogoutHandler.html)
- [Spring Security 6.5 — RedirectServerLogoutSuccessHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/logout/RedirectServerLogoutSuccessHandler.html)
- [Spring Security — WebFlux Test Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
