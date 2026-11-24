# Configuring Logout, Logout URL, and HTTP Methods

## Goals

This lesson belongs to the **Sessions and Logout** group in **Spring Security reactive / Spring WebFlux**. After this lesson, you will be able to:

- Distinguish logging out of an HTTP session from redirecting pages, clearing browser cookies, or revoking bearer tokens.
- Explain the roles of `LogoutWebFilter`, `ServerWebExchangeMatcher`, `ServerLogoutHandler`, and `ServerLogoutSuccessHandler`.
- Configure the logout URL with `ServerHttpSecurity.logout(...).logoutUrl(...)` while keeping **POST** as the logout method.
- Use `requiresLogout(...)` when you need explicit control over both the URL **and** the HTTP method.
- Understand why **POST with a CSRF token** is the standard way to log out of a cookie/session-based application, and why **GET logout** is discouraged.
- Build a Java 17+ example running on WebFlux with form login via `WebSession`, calling logout at a custom URL, and testing status, method, CSRF, and the absence of `Authentication` after logout.

> Use only reactive APIs such as `ServerHttpSecurity`, `SecurityWebFilterChain`, and `ServerWebExchange`. Do not confuse them with `HttpSecurity`, `LogoutFilter`, `HttpSession`, and `LogoutHandler` from the Servlet stack; the syntax and handlers differ.

## 1. What Does Logout Actually Change?

With session-based form login, the server can store `SecurityContext` containing `Authentication` in `WebSession`. The client typically carries the session ID via a cookie. If logout succeeds, a subsequent request with that cookie must not restore the logged-in user.

~~~text
Log in via POST /login
    |
    +-- Valid Authentication
    +-- SecurityContext saved in WebSession
    +-- Browser keeps session cookie
    |
    v
GET /api/me -> authenticated
    |
    v
POST /account/logout + cookie + valid CSRF
    |
    v
LogoutWebFilter
    |
    +-- ServerLogoutHandler: clears SecurityContext,
    |                        optionally invalidates WebSession
    |
    +-- ServerLogoutSuccessHandler: redirects or returns 204
    |
    v
GET /api/me with old cookie -> no longer authenticated
~~~

Distinct actions must be separated:

| Action | Meaning | Equivalent to full logout? |
|---|---|---|
| Return 200/204 and "Logged out successfully" | HTTP response to the client | No, if session/context has not been cleared. |
| Redirect to `/login` | UI navigation | Does not automatically delete server-side data. |
| Clear `SecurityContext` in the repository | Next request does not load context from that repository | Useful, though `WebSession`/app state may remain. |
| Invalidate `WebSession` | Current session is no longer valid | Usually required for session-based apps. |
| Delete session cookie on the client | Stops sending the old ID | Does not replace server-side invalidation. |
| Revoke JWT/refresh token | Invalidates credentials per token policy | Does not happen automatically merely by clearing `WebSession`. |

Only a logout handler using the right repository can clear the saved `SecurityContext`. If you only clear the context from the current request's Reactor Context while the repository still keeps the saved copy in `WebSession`, the next request can recover `Authentication`. Conversely, a session invalidated on the server cannot be "restored" merely by resending the same old cookie.

## 2. Logout Components in Spring Security WebFlux

### 2.1. LogoutWebFilter

`LogoutWebFilter` receives a `ServerWebExchange` and uses a `ServerWebExchangeMatcher` to decide whether the current request is a logout request. If the matcher does not match, the request proceeds down the filter/handler chain normally. If it matches, the filter runs the logout handlers and then the success handler along the reactive pipeline; no matching `@PostMapping` controller is needed.

~~~text
Request -> SecurityWebFilterChain
                   |
                   v
             LogoutWebFilter
                   |
       +-----------+-----------+
       |                       |
   No match                 Matches
       |                       |
   next filter          ServerLogoutHandler
                               |
                               v
                        ServerLogoutSuccessHandler
                               |
                               v
                       HTTP status / redirect
~~~

This is a functional diagram; in practice, the CSRF filter may reject a POST missing a token **before** the logout handler runs. Exact ordering depends on configuration and Spring Security version.

### 2.2. ServerLogoutHandler

A handler interface returning `Mono<Void>`, used to clean up authentication data. Common classes in `org.springframework.security.web.server.authentication.logout`:

- `SecurityContextServerLogoutHandler`: clears `SecurityContext` via `ServerSecurityContextRepository`.
- `WebSessionServerLogoutHandler`: invalidates the active `WebSession`.
- `DelegatingServerLogoutHandler`: combines multiple logout handlers to clean up several scopes at once.

Spring Security reactive documentation emphasizes: default logout handles clearing context/CSRF per configuration, yet if you want to **invalidate the entire `WebSession`**, configure `WebSessionServerLogoutHandler` as well. Do not borrow Servlet defaults and assume WebFlux automatically invalidates the entire session in every case.

One way to combine them:

~~~java
ServerLogoutHandler cleanup =
    new DelegatingServerLogoutHandler(
        new SecurityContextServerLogoutHandler(),
        new WebSessionServerLogoutHandler());
~~~

This is a snippet inside a configuration class requiring the corresponding reactive imports. If calling the `logoutHandler(...)` setter yourself, explicitly keep any default logic you still need; do not assume old handlers stay chained after replacement.

### 2.3. ServerLogoutSuccessHandler

The success handler runs after the logout handler; it decides how the client receives the outcome:

- `RedirectServerLogoutSuccessHandler`: redirects to the login page or a public page.
- `HttpStatusReturningServerLogoutSuccessHandler`: returns HTTP 200 by default or a chosen status code, such as 204 No Content, often convenient for APIs.

**The success handler is not a cleanup handler.** Returning 204 does not prove the session was destroyed if cleanup logic did not run. Proper testing always includes a subsequent request with the old credential/cookie.

## 3. Default Behavior: GET /logout and POST /logout

For WebFlux security with logout enabled, Spring Security 6.5 documentation describes two default behaviors:

1. **GET /logout**: may display a framework-provided logout confirmation page. This is **viewing a confirmation page**, not a promise that GET deletes the session.
2. **POST /logout**: is the request that **performs logout**, subject to CSRF/matcher and handler conditions. On success, the default response can redirect to login, e.g., `/login?logout`.

Exact GET behavior depends on whether the confirmation/default login page is enabled and on custom configuration. If you changed the URL or wrote your own controller, do not expect every `GET /logout` to still serve a confirmation page.

**Core point:** In the WebFlux DSL, `logoutUrl(String)` specifies **the URL to which an HTTP POST triggers logout**. Changing the URL string alone does not switch it to GET.

## 4. Configuring the Logout URL

### 4.1. Changing the logout URL while keeping POST (recommended)

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .logout(logout -> logout.logoutUrl("/account/logout"))
        .build();
}
~~~

This is a configuration method requiring imports for `@Bean`, `ServerHttpSecurity`, and `SecurityWebFilterChain`. It keeps the logout trigger at **POST /account/logout**. Do not assume GET on the same URL logs out.

| HTTP request | Matches the example's logout matcher? | Explanation |
|---|---|---|
| `POST /account/logout` | Yes | Must pass the CSRF filter when CSRF is enabled. |
| `GET /account/logout` | No | May be handled by another controller/page or return 404/redirect. |
| `POST /logout` | No | Default URL no longer triggers the new matcher. |
| `DELETE /account/logout` | No | Does not trigger logout despite matching the path. |

If GET does not match the logout matcher, that **does not guarantee** 405. Depending on the router, authorization, and exception handler, the request may yield 200, 302, 401, 404, 405, etc. To verify whether logout actually occurred, test `Authentication`/session on the next request.

### 4.2. Configuring an explicit matcher

`requiresLogout(...)` is used when customizing the match condition. An equivalent example for POST + path:

~~~java
http.logout(logout -> logout.requiresLogout(
    new PathPatternParserServerWebExchangeMatcher(
        "/account/logout", HttpMethod.POST)));
~~~

This is a Java configuration snippet requiring imports for `org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher` and `org.springframework.http.HttpMethod`. For a simple POST URL, `logoutUrl(...)` is shorter and less error-prone.

**Be careful when removing the HTTP method restriction:**

~~~java
// Not recommended for websites using browser cookies.
http.logout(logout -> logout.requiresLogout(
    new PathPatternParserServerWebExchangeMatcher("/account/logout")));
~~~

A path-only matcher can match GET as well. Spring Security shows this is possible while warning of the risks. This is a **security change**, not merely a shorter way to write a URL.

### 4.3. Distinguishing the matchers

| Configuration | Function |
|---|---|
| `logoutUrl(...)` | Selects the POST URL that triggers `LogoutWebFilter`. |
| `requiresLogout(...)` | Selects a custom matcher, including method if needed. |
| `securityMatcher(...)` | Selects which `SecurityWebFilterChain` covers the request. |
| `authorizeExchange().pathMatchers(...).permitAll()` | Sets authorization rules; does not create a logout endpoint or change the method. |
| `logoutSuccessHandler(...)` | Sets the response after cleanup finishes; does not change the request URL. |

With multiple `SecurityWebFilterChain` beans, the logout URL must pass through the chain configured with `LogoutWebFilter`. An `/account/logout` outside every chain may not be handled by any logout handler.

## 5. Why Use POST and CSRF Instead of GET?

HTTP GET has **read** semantics. It can be triggered by link clicks, external pages, preview bots, crawlers, prefetching, or browser navigation. Logout mutates session state and can disrupt an open workflow, so it should not be triggered directly by GET.

A logout CSRF scenario:

1. The user is logged into an app using a session cookie.
2. An external party embeds `https://app.example.test/logout` for the browser to visit.
3. If GET logs out automatically, the browser attaches the cookie and the user is logged out unwillingly.

With **POST + CSRF token**, the browser must supply an unpredictable value that an attacker cannot easily know from another site. The `SameSite` cookie attribute helps reduce risk, yet does not replace proper method, token, and origin policy design for the app.

### 5.1. What does the CSRF filter do?

By default, Spring Security WebFlux protects state-changing requests, including POST. Requests missing or sending a wrong CSRF token normally receive **403 Forbidden**. A logout POST rejected by CSRF **must not run the logout handler**.

~~~text
POST /account/logout
    |
    v
CsrfWebFilter
    | missing / invalid token ----> HTTP 403; does not log out
    |
    | valid token
    v
LogoutWebFilter
    |
    v
ServerLogoutHandler
    |
    v
ServerLogoutSuccessHandler
~~~

**Do not disable CSRF application-wide just because `POST /logout` returns 403.** Supply a valid token via a hidden form input or header per Spring Security configuration. For bearer-token APIs that do not rely on browser auto-sent cookies, the CSRF threat model differs and should be evaluated separately.

### 5.2. How to include the token in requests

In WebFlux, CSRF tokens are stored by default in `WebSession` via `WebSessionServerCsrfTokenRepository`. Spring Security can provide the token to views as a `Mono<CsrfToken>` attached to `ServerWebExchange`. Since Spring Security 6, `XorServerCsrfTokenRequestAttributeHandler` is the default to mitigate BREACH.

A typical logout form:

~~~html
<form method="post" action="/account/logout">
  <input type="hidden" name="_csrf" value="CSRF_TOKEN_FROM_SERVER">
  <button type="submit">Log out</button>
</form>
~~~

This HTML snippet is a **view structure sample**; the hidden input value must be server-rendered to the actual request token, never hardcoded to an example string. When using Spring Security template integration, leverage the framework's CSRF token support rather than inventing custom tokens. Never place tokens in URLs, logs, or analytics.

### 5.3. When is GET /logout useful?

GET can display a **confirmation page** containing a POST form. On that page, the user clicks the logout button, submitting a POST with the CSRF token. This cleanly separates roles: GET reads UI; POST mutates the session. If you just want a link-styled button, style a POST form like a link instead of changing logout's HTTP method to GET.

## 6. Choosing Cleanup Handlers and API Responses

When logging out of a session-based app, an explicit configuration is:

~~~java
var cleanup = new DelegatingServerLogoutHandler(
    new SecurityContextServerLogoutHandler(),
    new WebSessionServerLogoutHandler());

http.logout(logout -> logout
    .logoutUrl("/account/logout")
    .logoutHandler(cleanup)
    .logoutSuccessHandler(
        new HttpStatusReturningServerLogoutSuccessHandler(
            HttpStatus.NO_CONTENT)));
~~~

This is a snippet inside a configuration class; import the reactive classes and `HttpStatus`. It demonstrates three independent decisions:

1. **When to log out:** POST to `/account/logout`.
2. **What to clear:** saved `SecurityContext` and active `WebSession`.
3. **How to respond:** return HTTP **204 No Content**, no redirect.

In a navigational web app, replace the success handler with `RedirectServerLogoutSuccessHandler` and set the target URL if desired. Do not confuse the logout success URL (destination after logout) with the logout request URL.

Do not merely mark the session cookie deleted and call that complete security. Invalidating `WebSession` server-side is what ensures the old session ID can no longer be used to load context. When an app also holds non-authentication session data, consider the impact of invalidation on the remaining features.

## 7. Standalone Runnable Java 17 Practice Lab

The example uses **Java 17**, **Spring Boot 3.5.16**, Spring WebFlux, and Spring Security under Boot's dependency management. Boot 3.5.16 has been released; production should use a currently supported and security-patched framework line rather than treating the demo as a long-term deployment baseline.

**Demo goals:**

- Log in via the default form as user `learner`.
- `GET /csrf` displays the CSRF token for local request testing.
- `GET /api/me` returns the username from the principal when logged in.
- `GET /account/logout` only displays info and does not log out.
- `POST /account/logout` triggers `LogoutWebFilter`; wrong token yields 403, valid token yields 204.
- After a successful POST logout, the old session ID can no longer access `/api/me`.

### 7.1. Project structure and Gradle

~~~text
webflux-logout-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/WebfluxLogoutDemo.java
    └── test/java/example/LogoutMethodTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-logout-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Use a Gradle version compatible with Spring Boot 3.5 and JDK 17+. If a Gradle Wrapper is present, prefer running the wrapper so learners get consistent results.

### 7.2. Complete application

File `src/main/java/example/WebfluxLogoutDemo.java`:

~~~java
package example;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.HttpStatusReturningServerLogoutSuccessHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class WebfluxLogoutDemo {

    public static void main(String[] args) {
        SpringApplication.run(WebfluxLogoutDemo.class, args);
    }

    @Bean
    MapReactiveUserDetailsService users() {
        // Local demo only; never use {noop} passwords in production.
        UserDetails user = User.withUsername("learner")
            .password("{noop}demo-pass")
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(user);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        var cleanup = new DelegatingServerLogoutHandler(
            new SecurityContextServerLogoutHandler(),
            new WebSessionServerLogoutHandler());

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/login", "/csrf").permitAll()
                .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            // Do not disable CSRF: keep default protection.
            .logout(logout -> logout
                .logoutUrl("/account/logout")
                .logoutHandler(cleanup)
                .logoutSuccessHandler(
                    new HttpStatusReturningServerLogoutSuccessHandler(
                        HttpStatus.NO_CONTENT)))
            .build();
    }

    @RestController
    static class ApiController {

        @GetMapping("/csrf")
        Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
            // CsrfWebFilter stores Mono<CsrfToken> in an exchange attribute.
            Mono<CsrfToken> source =
                exchange.getAttribute(CsrfToken.class.getName());

            if (source == null) {
                return Mono.error(new IllegalStateException(
                    "CSRF attribute unavailable"));
            }

            return source.map(token -> Map.of(
                "headerName", token.getHeaderName(),
                "parameterName", token.getParameterName(),
                "token", token.getToken()));
        }

        @GetMapping("/api/me")
        Mono<Map<String, String>> me(ServerWebExchange exchange) {
            return exchange.getPrincipal()
                .map(principal -> Map.of(
                    "username", principal.getName()));
        }

        // This GET does NOT log out. POST to the same URL is handled by LogoutWebFilter.
        @GetMapping("/account/logout")
        Mono<Map<String, String>> logoutInfo(
            ServerWebExchange exchange) {

            return exchange.getPrincipal()
                .map(principal -> Map.of(
                    "message", "GET does not log out",
                    "username", principal.getName()));
        }
    }
}
~~~

**Explanation:**

- `@EnableWebFluxSecurity` and the `SecurityWebFilterChain` bean configure reactive security.
- `formLogin(Customizer.withDefaults())` uses the default login page/handler and saves `Authentication` via form login's session mechanism.
- `logoutUrl("/account/logout")` configures a POST logout match. GET on the same path is not treated as logout by `LogoutWebFilter`, so the example's GET controller still reads the principal.
- CSRF stays enabled; a POST request with a session cookie but missing a CSRF token is rejected before context cleanup runs.
- Cleanup includes `SecurityContextServerLogoutHandler` and `WebSessionServerLogoutHandler` to avoid leaving unnecessary `Authentication`/sessions behind.
- `HttpStatusReturningServerLogoutSuccessHandler(HttpStatus.NO_CONTENT)` returns 204 after handlers complete without sending a redirect.
- The `/csrf` endpoint exists solely so learners can observe tokens generated by WebFlux. Real applications can supply CSRF to views/templates or frontends via other mechanisms; never log tokens or expose them via CORS to untrusted origins.
- `/api/me` checks the principal from Spring Security rather than trusting client-supplied headers.

### 7.3. Running and testing with curl

In the `webflux-logout-demo` directory:

~~~bash
gradle bootRun
~~~

If using Gradle Wrapper: `./gradlew bootRun` on Linux/macOS, `gradlew.bat bootRun` on Windows. In another Bash terminal, you need `curl` and `jq` to extract the token from JSON:

~~~bash
# A. Fetch CSRF token and keep session cookie.
TOKEN=$(curl -sS -c cookies.txt -b cookies.txt \
  http://localhost:8080/csrf | jq -r '.token')

# B. Form login: username/password + CSRF token.
curl -i -b cookies.txt -c cookies.txt \
  --data-urlencode 'username=learner' \
  --data-urlencode 'password=demo-pass' \
  --data-urlencode "_csrf=$TOKEN" \
  http://localhost:8080/login

# C. Logged in: fetch username from session.
curl -i -b cookies.txt http://localhost:8080/api/me

# D. GET logout URL: returns info, does NOT log out.
curl -i -b cookies.txt http://localhost:8080/account/logout

# E. POST logout without token: expect 403.
curl -i -b cookies.txt -X POST http://localhost:8080/account/logout

# F. After login, fetch currently valid CSRF token.
TOKEN=$(curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/csrf | jq -r '.token')

# G. POST logout with CSRF: expect 204 No Content.
curl -i -b cookies.txt -c cookies.txt \
  --data-urlencode "_csrf=$TOKEN" \
  http://localhost:8080/account/logout

# H. Old cookie no longer represents Authentication.
curl -i -b cookies.txt http://localhost:8080/api/me
~~~

`-c` writes the cookie jar; `-b` sends the cookie jar; `--data-urlencode` defaults to form-urlencoded POST; `-i` prints status/headers. Do not add `-L` while inspecting redirects because it can obscure the initial 302 status. The shell example uses a local dummy password; never store real passwords in shell history or public command lines.

**Expected HTTP responses in the demo:**

| Step | Status | Meaning |
|---|---|---|
| GET /csrf | 200 | Token and header/parameter names issued for local testing. |
| POST /login valid user/password + CSRF | Usually 302 | Form login succeeded and redirected; follow with GET /api/me to verify. |
| GET /api/me while logged in | 200 | JSON contains `"username":"learner"`. |
| GET /account/logout | 200 | JSON contains `"message":"GET does not log out"`. |
| POST /account/logout missing CSRF | **403** | `CsrfWebFilter` blocked it; not logged out. |
| POST /account/logout with CSRF | **204** | Logout handlers ran; response has no body. |
| GET /api/me with old cookie after logout | Usually 302 to /login | Form-login entry point prompts to log in again. |

An unauthenticated request **does not always return 401**: with form login, Spring Security normally redirects 302 to the login page, whereas HTTP Basic or an API entry point may return 401. Session IDs, CSRF tokens, timestamps, and `Location` headers vary at runtime.

### 7.4. If testing on Windows PowerShell

Bash uses `TOKEN=$(...)`, which is not PowerShell variable syntax. You can use WSL/Git Bash or run `curl.exe` and store the token using appropriate JSON parsing. Keep the exact same cookie jar across fetching the token, logging in, logging out, and subsequent requests. Never hardcode raw tokens as constants in source code.

## 8. Testing with WebTestClient

This test simulates requests directly against `ApplicationContext`. It focuses on verifying the HTTP method and CSRF; to verify **real-world `WebSession` invalidation across multiple requests**, still run the cookie-jar test in section 7 or integration tests against the corresponding session store.

File `src/test/java/example/LogoutMethodTest.java`:

~~~java
package example;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class LogoutMethodTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void getDoesNotLogOut() {
        client.mutateWith(mockUser("learner"))
            .get().uri("/account/logout")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").isEqualTo("GET does not log out")
            .jsonPath("$.username").isEqualTo("learner");
    }

    @Test
    void postWithoutCsrfFails() {
        client.mutateWith(mockUser("learner"))
            .post().uri("/account/logout")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void postWithCsrfLogsOut() {
        client.mutateWith(mockUser("learner"))
            .mutateWith(csrf())
            .post().uri("/account/logout")
            .exchange()
            .expectStatus().isNoContent();
    }
}
~~~

Run:

~~~bash
gradle test
~~~

With the wrapper, run `./gradlew test` or `gradlew.bat test`. The tests here use mock `Authentication` per request; they verify HTTP status codes and do not replace real session persistence testing. When adding a custom `ServerLogoutHandler`, test invoking the handler and the concrete session/database store outcome.

## 9. When You Truly Want GET Logout

Spring Security allows `requiresLogout(...)` to accept a matcher that checks only the URL:

~~~java
// Can match any HTTP method, including GET: not recommended.
http.logout(logout -> logout.requiresLogout(
    new PathPatternParserServerWebExchangeMatcher("/account/logout")));
~~~

This is an **exception requiring security review**. If the app has browsers automatically sending session cookies, an external link or navigation can log out the user without an intentional valid UI action. Do not enable GET logout just to make a "Log out" button easier to write. Instead, use GET to display confirmation and a POST form with CSRF.

If business requirements force clients to use another HTTP method (e.g., DELETE), configure the method matcher explicitly, maintain appropriate CSRF/authorization controls, update the frontend, and test all entry paths. Do not assume DELETE is safer than POST when browsers auto-send cookies.

## 10. Other Boundaries to Remember

### 10.1. Session-based logout is not the same as HTTP Basic logout

With HTTP Basic, the client can send `Authorization: Basic ...` on **every request**. Even if the logout handler clears `SecurityContext`, a subsequent request resending valid Basic credentials can still authenticate. A 204 response cannot force every browser to forget cached Basic passwords. If UX requires genuine logout, consider session-based login or suitable token/revocation mechanisms.

### 10.2. WebSession logout does not automatically revoke JWTs

A signed, unexpired bearer JWT can continue authenticating API calls after you invalidate `WebSession`. Refresh-token revocation, token introspection, revocation lists, or access-token lifetimes suited to your threat model are required. Never advertise a POST logout endpoint as "invalidates all tokens" if the implementation only clears the session.

### 10.3. OIDC/SSO involves two sessions

Logging out of the application session and logging out at the Identity Provider can be two separate steps. Spring Security provides dedicated OIDC logout support; if the app needs single logout, follow the provider-appropriate flow and test callbacks/post-logout redirects rather than merely redirecting the browser to the local login page.

### 10.4. Multiple SecurityWebFilterChains

If a session website and a bearer API use two `SecurityWebFilterChain`s, each chain has its own `securityMatcher(...)`. The logout URL must match the chain carrying the desired policy/logout handler. A request matching no chain may never reach `LogoutWebFilter`. Place specific chains first, the catch-all default chain last, and test all routes.

### 10.5. Reverse proxies and cookies

If external Internet URLs live under `/service` while the app receives rewritten paths, verify how the proxy handles path prefixes and forwarded headers. Form actions, matchers, cookie `Path`/`Domain`/`Secure`/`SameSite`, and redirect `Location`s must align with the real domain/prefix. Avoid situations where a user logs out on one origin while the browser retains a session cookie for another origin.

## 11. Common Mistakes and Fixes

**1. POST logout returns 403 so CSRF is disabled.** Wrong for cookie/session apps. Send a valid token. Keep `CsrfWebFilter` as the boundary before state-changing operations.

**2. Configuring `logoutUrl("/signout")` and using a GET link.** `logoutUrl` defaults to matching **POST**. Use a POST form, and do not assume GET cleared the session.

**3. Using `requiresLogout` without an HttpMethod.** A path-only matcher can accept GET and introduce logout CSRF. Only use it if you understand and accept the risk.

**4. Only redirecting to `/login` in a controller.** Navigation does not replace clearing context or `WebSession`. Use the proper logout filter and handlers.

**5. Deleting the cookie without invalidating the session.** The old ID can still work on the server if exposed. Invalidate the session server-side when policy requires it.

**6. Clearing `SecurityContext` only for the current request.** The repository may still hold the context for the next request. Clear through the right repository.

**7. Assuming `WebSession` is always invalidated by default.** Spring Security reactive provides a separate `WebSessionServerLogoutHandler`. Configure it explicitly when needed.

**8. Assuming local logout revokes JWTs.** Standalone tokens can keep working; a revocation/expiry policy is required.

**9. Calling `subscribe()` manually inside a logout handler.** This can run cleanup outside the pipeline, drop errors, or commit the response before deletion completes. Return `Mono<Void>` to Spring.

**10. Seeing 302 after logout and treating it as an error.** Form-login websites normally redirect; APIs may choose 204. Distinguish the success handler from the authentication entry point.

**11. Testing only status 204 without retrying the old session.** That does not prove authentication was revoked. Test login -> logout -> protected request with the old cookie.

**12. Placing the logout URL outside `securityMatcher`.** If the chain does not match, the logout filter will not run as expected. Test through the real gateway.

**13. Confusing `logoutSuccessHandler` with `logoutHandler`.** The former formats the response; the latter performs state cleanup.

**14. Confusing Servlet and WebFlux APIs.** Reactive uses `WebSessionServerLogoutHandler`/`ServerLogoutHandler` and `ServerWebExchange`.

**15. Exposing CSRF/session cookies in logs.** Tokens, cookies, and credentials must be protected; audits should log only necessary scrubbed details.

## 12. Implementation Checklist

1. Does the logout URL belong to the right `SecurityWebFilterChain`?
2. Does the matcher accept only HTTP POST per policy?
3. Does the client use a CSRF-protected form POST or AJAX POST?
4. Does GET logout only display confirmation/info without deleting state?
5. Does missing/invalid CSRF return 403 without running cleanup?
6. Which repository stores `Authentication`, and does logout clear that exact repository?
7. Is invalidating `WebSession` also required, and is its handler configured?
8. Does the success HTTP response use a redirect or 200/204 per client expectations?
9. Is a post-logout request carrying the old cookie prompted to re-authenticate?
10. If multiple tabs/browsers/devices exist, is single-session vs. all-session logout clearly defined?
11. Do JWTs/refresh tokens have a revocation/expiry plan independent of the session?
12. Does OIDC require IdP logout or only local app logout?
13. Do cookies and redirects have proper `Path`/`Domain`/`SameSite`/`Secure`/TLS behind proxies?
14. Are passwords, session IDs, CSRF tokens, and `Authorization` headers kept out of logs?
15. Are there regression tests for GET, POST without CSRF, POST with CSRF, and protected requests after logout?
16. Are `block()` and manual `subscribe()` avoided in reactive logout handlers?

## 13. Self-Assessment Questions

**1.** Does changing `logoutUrl("/account/logout")` make `GET /account/logout` log out?

**Answer:** No. By default the new logout matcher accepts POST to that URL; GET may be handled by a controller/view without logging out.

**2.** `POST` logout returns 403 even though the browser has a session cookie. Should CSRF be disabled?

**Answer:** No. Inspect the server-issued token, the form/header sending the token, the session cookie, and the CSRF matcher.

**3.** Why are `WebSessionServerLogoutHandler` and `SecurityContextServerLogoutHandler` not the same?

**Answer:** One invalidates the entire `WebSession`; the other clears `SecurityContext` via the repository. Both may be needed.

**4.** `POST` logout returns 204, yet a subsequent request with the old cookie stays authenticated. What should you investigate?

**Answer:** The logout handler, the repository saving/loading security context, the session store, actual cookies, whether another authentication mechanism is re-authenticating, and whether an old token/password was actually sent on the next request.

**5.** An API using bearer JWT sends the same token after local logout. Is it guaranteed to get 401?

**Answer:** No. An unrevoked, unexpired JWT can still authenticate. Revocation or short expiry must be designed.

**6.** `GET /logout` may appear in default docs; does that mean you should trigger logout via GET?

**Answer:** No. Default GET can display a confirmation page, whereas POST changes state. Direct GET logout creates a CSRF risk.

**7.** Does `logoutSuccessHandler` clean up the session for you?

**Answer:** No. It builds the HTTP response after the logout handlers finish.

**8.** Why must you test the old cookie after logout?

**Answer:** Because status/redirect alone does not prove server-side state was invalidated. The next request is the real proof.

## Official Documentation

- Spring Security WebFlux — Logout: https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/logout.html
- Spring Security WebFlux — CSRF and POST logout: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- `ServerHttpSecurity.LogoutSpec` (`logoutUrl`, `requiresLogout`): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.LogoutSpec.html
- `LogoutWebFilter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/logout/LogoutWebFilter.html
- `DelegatingServerLogoutHandler`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/logout/DelegatingServerLogoutHandler.html
- `WebSessionServerLogoutHandler`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/logout/WebSessionServerLogoutHandler.html
- `HttpStatusReturningServerLogoutSuccessHandler`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/logout/HttpStatusReturningServerLogoutSuccessHandler.html
- Spring Security WebFlux — Testing CSRF: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- Spring Security WebFlux — WebTestClient Security Setup: https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html
