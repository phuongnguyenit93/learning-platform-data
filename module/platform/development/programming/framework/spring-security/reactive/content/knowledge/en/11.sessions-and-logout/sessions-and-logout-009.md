# Coordinating Cookie Deletion, Session Invalidation, and CSRF Handling on Logout

## 1. Learning Objectives

In Spring Security **reactive/WebFlux**, logging out is not simply deleting a cookie in the browser. An application using **form login and `WebSession`** typically has three related groups of state:

- `SecurityContext` / `Authentication` saved in `ServerSecurityContextRepository`;
- `WebSession` on the server, including the session ID, user data, CSRF token, and business state;
- client-side cookies, including the session ID cookie and any custom cookies set by the application.

Additionally, **CSRF protection** controls who can trigger the logout action. If the app allows another website to force the browser to issue a logout via GET, users can be logged out unwillingly. With Spring Security WebFlux, **POST `/logout`** and a CSRF token form the important default mechanism.

This lesson helps you:

1. Distinguish clearing `SecurityContext`, invalidating `WebSession`, and expiring cookies; understand why these steps must be coordinated.
2. Understand `LogoutWebFilter`, `SecurityContextServerLogoutHandler`, `WebSessionServerLogoutHandler`, `CsrfServerLogoutHandler`, and `DelegatingServerLogoutHandler`.
3. Use `ServerHttpSecurity.logout(...)` to configure POST logout, cleanup, and an HTTP 204 result.
4. Send an expired cookie with matching name/`Path`/`Domain` and `Max-Age=0`.
5. Understand how browsers obtain/send CSRF tokens, invalidation of old tokens, and session timeout issues.
6. Run a Java 17+ Spring Boot WebFlux project, practice with a browser, and verify with `WebTestClient`.
7. Distinguish local session logout from revoking JWTs, refresh tokens, or logging out all devices.

**Scope:** logging out when the application **uses cookies and server-side sessions**. HTTP Basic has no session; OIDC SSO and stateless JWTs have separate revocation requirements that cannot be solved solely by `WebSession.invalidate()`.

## 2. Why Does "Deleting a Cookie" Not Equal "Logging Out"?

Typical model:

```text
Browser                                        Spring WebFlux
  |                                                 |
  | Cookie: SESSION=<id>                            |
  +------------------------------------------------>|
  |                                                 |
  |                      WebSession with that ID? --+
  |                                    |
  |                                    v
  |                           SecurityContext
  |                                    |
  |                                    v
  |                           Principal/Authorities
  |<------------------------------------------------+
  |                    response                     |
```

The `SESSION` cookie is primarily a **reference key**, not the entire session data. The server uses that ID to look up `WebSession`, then looks up `SecurityContext` or other state.

**Scenario A — only deleting the cookie:** the browser stops sending the cookie on new requests, yet the session ID may still live in the server's session store. If an attacker holds a copy of the ID, the attacker can use it until the session expires.

**Scenario B — only invalidating the server session:** the old session ID is no longer accepted by the server, which is the primary security safeguard. However, the browser may still retain the old cookie or auxiliary cookies; an SPA UI might still display user data from memory.

**Scenario C — only clearing `SecurityContext`:** new requests no longer use the saved authentication context; however, some business attributes in `WebSession` may remain. If logout requires destroying the entire session, you must invalidate it.

Therefore, logout must achieve **two independent goals**: (1) the server no longer recognizes the old session, and (2) the client does not retain or resend old state. With form login, the CSRF token must also be managed appropriately.

### Components

| Component | Responsibility | Notes |
| --- | --- | --- |
| `SecurityContext` | Holds `Authentication` and authenticated identity | In WebFlux, propagated via Reactor Context |
| `ServerSecurityContextRepository` | Saves/loads security context across requests | Can use `WebSessionServerSecurityContextRepository` |
| `WebSession` | Stores server-side session and attributes | Invalidate so the session ID is no longer valid |
| `WebSessionIdResolver` | Binds session ID to request/response | Default cookie name is usually `SESSION` |
| `ServerCsrfTokenRepository` | Generates/saves/reads/clears CSRF tokens | Default typically uses `WebSession` |
| `LogoutWebFilter` | Matches logout requests per matcher | Default logout is POST |
| `ServerLogoutHandler` | Performs cleanup on logout | Returns `Mono<Void>` |
| `ServerLogoutSuccessHandler` | Decides the post-logout response | Redirects or returns 200/204 per config |

Do not copy Servlet logout patterns (`HttpSession`, `SecurityContextLogoutHandler`) into WebFlux: reactive uses `WebSession` and `ServerLogoutHandler`.

## 3. How Does a Logout Request Travel Through the Pipeline?

With a browser holding a session cookie:

```text
POST /logout
Cookie: SESSION=...
X-CSRF-TOKEN: <current session token>
             |
             v
      CsrfWebFilter
      - method needs CSRF?
      - valid token present?
             |
       +-----+------+
       |            |
      no           yes
       |            |
       v            v
   403 Forbidden  LogoutWebFilter
                    |
                    v
                ServerLogoutHandler
                    |
        +-----------+----------+-----------+
        |           |          |           |
  clear context clear CSRF invalidate  expire app
                           WebSession   cookies
        |           |          |           |
        +-----------+----------+-----------+
                    |
                    v
            LogoutSuccessHandler
                    |
                    v
               204 / redirect
                    |
                    v
          Client clears UI state
```

The diagram shows the **logical flow**, without promising the exact ordering of every internal `WebFilter` across all versions. In the hands-on section, we explicitly declare the required logout handlers so you know exactly which steps execute.

### Why must it be POST?

Logout mutates state. GET should be reserved for reading; browsers, crawlers, link previews, or external pages can trigger GETs unintentionally. A GET endpoint that performs logout creates a **logout CSRF** risk.

According to Spring Security WebFlux documentation, `LogoutWebFilter` handles **HTTP POST `/logout`** by default to integrate with CSRF checks. `GET /logout` may render a confirmation page for the user, but it is not the way to execute logout.

Do not switch to GET or disable `csrf` merely because you see **403** on POST: 403 usually signals a **missing, invalid, or expired token**, not proof that the logout framework is broken.

## 4. Logout Handlers That Must Coordinate

### 4.1. `SecurityContextServerLogoutHandler`

Class `org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler` clears the saved `SecurityContext` via `ServerSecurityContextRepository`. This step ensures the old security context is not reloaded on the next request.

If the application uses a custom `ServerSecurityContextRepository`, logout must clear **that exact repository**. Do not use Servlet's `SecurityContextHolder.clearContext()` as the primary mechanism in WebFlux: reactive pipelines are not pinned to a single thread.

### 4.2. `WebSessionServerLogoutHandler`

Class `org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler` invalidates the current `WebSession`. It removes server-side session state rather than merely deleting the `Authentication` attribute.

Spring Security reactive docs note that you normally need to configure this handler explicitly if you want to **invalidate the entire `WebSession`** on logout; do not assume the default handler always cleans up every session attribute.

### 4.3. `CsrfServerLogoutHandler`

Class `org.springframework.security.web.server.csrf.CsrfServerLogoutHandler` uses `ServerCsrfTokenRepository` to clear the old CSRF token. When defining a combined custom logout handler, make sure this step is not accidentally omitted.

Important: if the app configures repository A for CSRF verification while the logout handler clears repository B, you may fail to remove the right token. Use the **same repository bean** for both.

### 4.4. `DelegatingServerLogoutHandler`

Class `org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler` executes multiple `ServerLogoutHandler`s through a single unified interface.

```java
ServerLogoutHandler coordinated =
        new DelegatingServerLogoutHandler(
                new SecurityContextServerLogoutHandler(),
                new WebSessionServerLogoutHandler());
```

This is an **illustrative snippet inside a configuration class**, requiring imports for the types. The runnable example below adds `CsrfServerLogoutHandler` and a dedicated cookie-clearing handler. Reactive handlers return `Mono<Void>`; never call `block()` inside a `WebFilter`.

### 4.5. Logout success

`ServerLogoutSuccessHandler` produces the response after cleanup. For normal browsers, it can redirect to login; for SPAs/APIs, it can return `204 No Content`. Class `HttpStatusReturningServerLogoutSuccessHandler` accepts `HttpStatus.NO_CONTENT` to accomplish this.

**HTTP 204 only confirms the success handler returned a response.** To prove logout is secure, you must still test a subsequent request with the old session ID.

## 5. Cookies: Expiring the Right Name, Path, and Domain

A cookie is identified by the browser according to a scope comprising its name and domain/path scope. To delete a cookie, the server typically sends an expiring `Set-Cookie` with **the exact matching name, `Path`, and `Domain`**, setting `Max-Age=0` or a past `Expires`.

Example:

```http
Set-Cookie: demo-pref=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax
```

This is a readable example; attribute ordering in responses can differ. In WebFlux, you can write:

```java
ResponseCookie expired = ResponseCookie.from("demo-pref", "")
        .path("/")
        .maxAge(Duration.ZERO)
        .httpOnly(true)
        .sameSite("Lax")
        .build();

exchange.getResponse().addCookie(expired);
```

This is a **fragment**, requiring a `ServerWebExchange exchange` variable and imports for `ResponseCookie` and `Duration`.

If the original cookie used `Path=/app` while logout uses `Path=/`, the browser may retain the old cookie; similarly, host-only cookies and cookies with `Domain=example.com` may require matching expiration attributes. Two cookies with the same name but different `Path`/`Domain` are not the same cookie.

- `HttpOnly` prevents JavaScript from reading the session cookie; it does not protect against all attack vectors.
- `Secure` requires transmitting the cookie over HTTPS; enable it for production session/auth cookies. Local HTTP demos need matching configuration to test.
- `SameSite` reduces certain cross-site request scenarios; it does not replace CSRF tokens in all architectures.
- `Max-Age=0` tells the browser to delete the cookie; it **does not revoke** active access tokens or server-side sessions.

### WebFlux session cookie differs from `JSESSIONID`

`CookieWebSessionIdResolver` defaults to the name **`SESSION`**. This is a key difference from Servlet examples that typically use `JSESSIONID`. With Spring Session or a custom `WebSessionIdResolver`, the name/`Path`/`SameSite` can be customized.

To clear the session cookie, prefer letting the **session infrastructure** handle it upon invalidation and verify the actual response. Do not hardcode `Set-Cookie: JSESSIONID=...` in a WebFlux app using `SESSION`. If you need to expire custom cookies created by your app, use a dedicated handler with the matching scope.

### Should you delete every cookie?

Not necessarily. Consent cookies, theme, locale, or identity provider cookies have different ownership and policies. Deleting all browser cookies can break user preferences or fail across domains. Maintain an inventory and delete only the cookies that truly need clearing on logout.

If considering `Clear-Site-Data`, verify browser support, scope, and impact on caches/offline storage. That header does not replace server-side invalidation.

## 6. CSRF Tokens Before, During, and After Logout

### 6.1. Tokens belong to the session

Spring Security WebFlux enables CSRF by default; `WebSessionServerCsrfTokenRepository` is the standard choice to store the expected token in `WebSession`. `CsrfWebFilter` exposes `Mono<CsrfToken>` in a `ServerWebExchange` attribute keyed by `CsrfToken.class.getName()`.

With forms, the token goes into the hidden `_csrf` input. With AJAX/fetch, clients can send a header, such as `X-CSRF-TOKEN` under the default repository. The token must belong to the **active session**, not a token from before login.

In Spring Security 6.x, the exposed token may be masked for BREACH mitigation, so a token string changing across renders is not necessarily an error.

### 6.2. Correct sequence

1. The browser already holds a session cookie from login.
2. The browser obtains the CSRF token bound to that session via a form or same-origin endpoint.
3. The browser sends **POST `/logout`**, the session cookie, and the CSRF token.
4. The CSRF filter validates the token; if wrong or missing, the request is blocked before logout succeeds.
5. Logout handlers clear context/token, invalidate the session, and expire required cookies.
6. The server returns 204 or redirects per the UI.
7. The frontend clears UI state and caches holding authenticated data.
8. If the user logs in again, a new session and CSRF token are required.

**Never reuse an old CSRF token** for a new session. After login or logout, the token may be rotated per security configuration; SPAs should fetch a fresh token before the next POST.

### 6.3. Session already timed out before logout

When a session expires, the old CSRF token is no longer in the repository. The browser may still hold stale data in memory and send POST `/logout` with the expired token; the result can be `403 Forbidden`. This is not a valid reason to switch to GET logout or disable CSRF.

The app should report that the session expired, clear client-side UI state, and request a fresh token/session if needed. This differs from a successful logout of an active session.

### 6.4. `CookieServerCsrfTokenRepository`

If the app uses a separate CSRF cookie—commonly `XSRF-TOKEN` with header `X-XSRF-TOKEN`—storage and deletion behavior differ from the `WebSession` repository. Logout must clear the token in the active repository and also consider deleting the token cookie with matching `Path`/`Domain`. `withHttpOnlyFalse()` lets JS read the **CSRF token cookie**, which does not mean letting JS read the **session ID cookie**.

CSRF, cookie `SameSite`, and CORS are complementary mechanisms; none of them replaces real authentication/authorization.

## 7. Runnable Project: Spring Boot 3.3.5 + WebFlux + Form Login

Example for **Java 17+** and compatible Gradle (e.g., 8.5). Spring Security 6.x is managed via the Spring Boot BOM.

Structure:

```text
reactive-logout-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/dev/example/logout/
    │   ├── LogoutApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/dev/example/logout/
        └── LogoutSecurityTests.java
```

### 7.1. Build files

`settings.gradle`:

```groovy
rootProject.name = 'reactive-logout-demo'
```

`build.gradle`:

```groovy
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Do not add `spring-boot-starter-web` when targeting pure WebFlux: Spring Boot normally prefers Servlet if both starters are declared.

### 7.2. Main class

`src/main/java/dev/example/logout/LogoutApplication.java`:

```java
package dev.example.logout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LogoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(LogoutApplication.class, args);
    }
}
```

### 7.3. Spring Security with coordinated logout

`src/main/java/dev/example/logout/SecurityConfig.java`:

```java
package dev.example.logout;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseCookie;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.HttpStatusReturningServerLogoutSuccessHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.ServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;
import org.springframework.security.web.server.csrf.CsrfServerLogoutHandler;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRepository;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;

import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        return new MapReactiveUserDetailsService(
                User.withUsername("reader")
                        .password(encoder.encode("reader-pass"))
                        .roles("USER")
                        .build());
    }

    @Bean
    ServerCsrfTokenRepository csrfTokenRepository() {
        return new WebSessionServerCsrfTokenRepository();
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ServerCsrfTokenRepository csrfRepository) {

        ServerLogoutHandler expireAppCookie = (filterExchange, auth) -> {
            ResponseCookie expired = ResponseCookie.from("demo-pref", "")
                    .path("/")
                    .maxAge(Duration.ZERO)
                    .httpOnly(true)
                    .sameSite("Lax")
                    .build();
            filterExchange.getExchange()
                    .getResponse().addCookie(expired);
            return Mono.empty();
        };

        ServerLogoutHandler coordinated =
                new DelegatingServerLogoutHandler(
                        new SecurityContextServerLogoutHandler(),
                        new CsrfServerLogoutHandler(csrfRepository),
                        new WebSessionServerLogoutHandler(),
                        expireAppCookie);

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/", "/public", "/login", "/csrf")
                            .permitAll()
                        .anyExchange().authenticated())
                .csrf(csrf -> csrf.csrfTokenRepository(csrfRepository))
                .formLogin(Customizer.withDefaults())
                .logout(logout -> logout
                        .logoutUrl("/logout")
                        .logoutHandler(coordinated)
                        .logoutSuccessHandler(
                                new HttpStatusReturningServerLogoutSuccessHandler(
                                        HttpStatus.NO_CONTENT)))
                .build();
    }
}
```

**Meaning of each part:**

- Sample user `reader / reader-pass` is for the local demo, with password BCrypt-encoded when creating `UserDetails`. Never use demo passwords on public servers.
- The CSRF filter and `CsrfServerLogoutHandler` share the same `csrfTokenRepository` bean.
- `formLogin` enables login that saves the security context into `WebSession`, unlike pure HTTP Basic which sends credentials on every request.
- `SecurityContextServerLogoutHandler` clears saved authentication; `CsrfServerLogoutHandler` clears the CSRF token; `WebSessionServerLogoutHandler` invalidates the session; the final lambda expires the `demo-pref` cookie.
- `logoutUrl("/logout")` keeps the **POST** flow; do not expose GET logout or disable CSRF.
- `HttpStatusReturningServerLogoutSuccessHandler(NO_CONTENT)` returns `204` instead of redirecting to the login page.
- `anyExchange().authenticated()` protects endpoints outside the public list. The logout filter handles logout requests via its own matcher.
- If you swap `ServerSecurityContextRepository` or `ServerCsrfTokenRepository` in your project, keep the logout handlers aligned with the repositories in use.

**On duplicate cleanup:** when replacing `logoutHandler`, know which handlers remain in your framework version and do not drop CSRF/session cleanup. The example above explicitly declares every step to execute. Never assume custom handlers are automatically appended to default handlers.

### 7.4. WebFlux Controller

`src/main/java/dev/example/logout/DemoController.java`:

```java
package dev.example.logout;

import java.security.Principal;
import java.util.Map;

import org.springframework.http.ResponseCookie;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/")
    public Mono<String> home() {
        return Mono.just("home");
    }

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/me")
    public Mono<Map<String, String>> me(
            Principal principal, ServerHttpResponse response) {

        response.addCookie(ResponseCookie.from("demo-pref", "seen")
                .path("/")
                .httpOnly(true)
                .sameSite("Lax")
                .build());

        return Mono.just(Map.of("user", principal.getName()));
    }

    @GetMapping("/csrf")
    public Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> tokenPublisher =
                exchange.getAttribute(CsrfToken.class.getName());

        if (tokenPublisher == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF filter did not expose a token"));
        }

        return tokenPublisher.map(token -> Map.of(
                "headerName", token.getHeaderName(),
                "parameterName", token.getParameterName(),
                "token", token.getToken()));
    }
}
```

`/csrf` returns a token for testing, bound to the session when the client receives and sends cookies. Spring Security 6.x exposes `Mono<CsrfToken>` as an exchange attribute, which can be subscribed to this way without calling `block()`. When moving to a production app, review same-origin policy, CORS, HTTP caching, token responses, and logging so tokens are never exposed.

`/me` sets a non-sensitive cookie `demo-pref=seen` with `Path=/` solely so there is a custom cookie for logout to delete. Production configs should enable `Secure` over HTTPS; since the demo runs on `http://localhost`, it is omitted here.

## 8. Practicing Logout from the Browser

Start:

```bash
gradle bootRun
```

If using a wrapper, run `./gradlew bootRun` or `gradlew.bat bootRun`. Assume the server runs at `http://localhost:8080`.

**Step 1 — log in:** open `http://localhost:8080/login`, log in with `reader` and demo password `reader-pass`. Spring Security can generate a default login page with a CSRF token for POST login.

**Step 2 — inspect session:** open `http://localhost:8080/me`. Expected body:

```json
{"user":"reader"}
```

In DevTools Application/Cookies, you will normally see the `SESSION` cookie created by WebFlux and `demo-pref` created by the controller. Session cookie names can be adjusted via resolver, so verify in practice.

**Step 3 — obtain current CSRF:** open `http://localhost:8080/csrf` (or use same-origin `fetch`). The JSON contains `token`, `headerName`, and `parameterName`. The token may rotate after login; do not use a token fetched before logging in.

**Step 4 — send a valid POST logout:** in the same-origin DevTools Console:

```javascript
const csrf = await fetch("/csrf", {
  credentials: "same-origin"
}).then(response => response.json());

const response = await fetch("/logout", {
  method: "POST",
  credentials: "same-origin",
  headers: { [csrf.headerName]: csrf.token }
});

console.log(response.status); // Expected 204
```

This is a POST request carrying the session cookie and CSRF token. A 204 status means the success handler returned a success status; also check the expiration of `demo-pref` and the outcome of a request using the old session.

**Step 5 — verify after logout:** reopen `/me`. With form login, the request is no longer authenticated and typically redirects to `/login`. `demo-pref` has been instructed to expire. In the browser Network tab, check `Set-Cookie` for `Max-Age=0` with the right `Path` and see how the session cookie was handled.

### Intentionally testing missing CSRF

While **still logged in**, try:

```javascript
const response = await fetch("/logout", {
  method: "POST",
  credentials: "same-origin"
});

console.log(response.status); // Expected 403
```

Without a CSRF token, the request is blocked and must not be treated as logged out. Afterward, send it again with the right token. If the session already timed out, the old token may no longer be valid; a dedicated UX flow is needed for expired sessions.

### Why not use GET logout?

`fetch("/logout")` without specifying a method sends **GET**. GET is not a CSRF-protected logout operation; Spring Security may return a confirmation page. Never build a "Log out" menu item as a state-changing GET link.

## 9. Testing with `WebTestClient`

File `src/test/java/dev/example/logout/LogoutSecurityTests.java`:

```java
package dev.example.logout;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class LogoutSecurityTests {

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
    void csrfEndpointReturnsToken() {
        client.get().uri("/csrf")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.token").exists()
                .jsonPath("$.headerName").exists();
    }

    @Test
    void authenticatedMeReturnsIdentity() {
        client.mutateWith(mockUser("reader"))
                .get().uri("/me")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.user").isEqualTo("reader");
    }

    @Test
    void postLogoutWithoutCsrfIsForbidden() {
        client.mutateWith(mockUser("reader"))
                .post().uri("/logout")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void postLogoutWithCsrfExpiresCookieAndReturns204() {
        client.mutateWith(mockUser("reader"))
                .mutateWith(csrf())
                .post().uri("/logout")
                .exchange()
                .expectStatus().isNoContent()
                .expectHeader()
                .values(HttpHeaders.SET_COOKIE, values ->
                        assertTrue(values.stream().anyMatch(cookie ->
                                cookie.startsWith("demo-pref=")
                                        && cookie.contains("Max-Age=0"))));
    }
}
```

Run:

```bash
gradle test
```

**Expected result:** 4 tests pass with the project/dependencies above. This is an expectation from the example config, **not a claim that Gradle was run in your repository**.

The tests verify the CSRF gate, logout response, mock user, and cookie expiration. **Limitation:** `mockUser` only creates a security context for a mock exchange; it does not substitute for a full **real login → browser session ID → logout → retry old ID** sequence. Therefore, a separate E2E test is needed to prove the session is truly invalidated on the server.

### Logout test matrix

| Case | Expected result | What to verify |
| --- | --- | --- |
| POST missing token | 403 | Logout handler is not treated as succeeded |
| POST with wrong token | 403 | Fabricated tokens are rejected |
| POST with valid token | 204 in demo | Logout success handler |
| `demo-pref` cookie | Expiring `Set-Cookie` with matching `Path`/`Domain` | Browser actually deletes the cookie |
| Resending old `SESSION` ID | Can no longer access `/me` as previous user | Server session invalidated |
| GET `/logout` | Does not perform logout directly | Prevents logout CSRF |
| Logout after timeout | May be 403/redirect depending on flow | UX for expired sessions |
| Re-login after logout | Fresh session and token | Old CSRF is not reused |
| Two tabs sharing a session | Other tab is no longer authenticated | UI synchronizes state |
| Two devices with distinct sessions | Scope per policy | Do not confuse current session with global logout |

Test real session invalidation using an HTTP client with a cookie jar or browser E2E: real login, keep a copy of the test ID, logout with CSRF, then resend the old ID. If the server still recognizes the user as logged in, server cleanup has a bug, even if the logout response was 204.

## 10. Boundaries That Must Be Distinguished

### 10.1. Old session ID vs. old browser cookie

If the server has invalidated the session while the browser still sends the old ID, the next request must no longer be authenticated. At that point server-side security is satisfied, though client state may still need cleanup.

Conversely, deleting the client cookie without deleting the server session leaves risk if the session ID was stolen. Test **reusability of the old session ID**, not merely whether the cookie disappeared.

### 10.2. Multiple tabs in the same browser

Tabs on the same origin typically share session cookies yet have separate UI state. Logging out in tab A makes tab B unauthenticated, yet tab B may still display the old username. The frontend should clear state/caches and, when needed, use a tab-sync mechanism such as `BroadcastChannel`. That is UX cleanup, not server invalidation.

### 10.3. Logging out all devices

`WebSessionServerLogoutHandler` destroys the **current session**. It does not automatically locate sessions for the same user on other devices. A "log out on all devices" feature requires a session index/registry or suitable database token revocation.

### 10.4. Spring Session / Redis

When using a distributed session store, verify invalidation reaches the shared backend so other instances reject the old session ID. Cookie name/`Path` may be customized and no longer default. Test across multiple instances rather than only a single local node.

### 10.5. HTTP Basic and JWT

If a client keeps sending `Authorization: Basic username:password` on every request, session logout cannot stop **re-authentication with those credentials**. Likewise, deleting cookies does not revoke an unexpired JWT. Stateless tokens require short expiry, refresh-token revocation, token denylists, or other mechanisms if the threat model requires them.

### 10.6. OIDC/SSO

Clearing the local session does not log out of the Identity Provider by default. With OIDC, you may need `OidcClientInitiatedServerLogoutSuccessHandler` or an IdP-supported federated logout flow. Never claim system-wide logout when only the application session was deleted.

### 10.7. HTTPS and production cookies

Production should use HTTPS with session cookies carrying `Secure`, `HttpOnly`, and `SameSite` per the threat model. With TLS-terminating proxies, trust forwarded headers only from controlled proxies; never trust client-supplied `X-Forwarded-Proto` values. CSRF and TLS address two different threats.

## 11. Common Mistakes and Fixes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Clicking "logout" does not log out | UI sent GET or only cleared frontend state | Send POST with token, inspect server handlers |
| POST logout returns 403 | Missing, wrong, mismatched-session, or expired token | Fetch current CSRF; do not disable CSRF |
| POST returns 204 yet old ID still grants access | Session not invalidated or repo mismatch | Check `WebSessionServerLogoutHandler` and session store |
| Cookie does not disappear | `Path`/`Domain` of expiring cookie mismatch | Compare `Set-Cookie` at creation and deletion |
| Mistakenly deleting `JSESSIONID` | WebFlux is using `SESSION` | Check `WebSessionIdResolver` config |
| Stale CSRF still appears in SPA | Client cached token across login/logout | Clear cache, fetch fresh token for new session |
| Logged out in one tab, other tab still shows username | UI not updated | Sync client state, let server reject old session |
| Logged out one device, other device stays logged in | Default destroys one session | Design all-session logout separately |
| JWT still works after logout | JWT not revoked | Design token lifecycle |
| Cookie deleted yet server session stays alive | Only expired cookie | Invalidate server-side and test old ID |
| Spring app uses Servlet `SecurityContextHolder` | Confused reactive Context with `ThreadLocal` | Use reactive logout handlers/repository |
| `mockUser` test passes yet E2E fails | Test did not create a real session | Test real login, cookie jar, and ID reuse |
| Disabling CSRF to "fix" 403 | Introduces logout CSRF risk | Keep POST and token |
| Custom handler dropped default cleanup | Replaced handler omitting context/token/session | Use a delegating handler with full responsibilities |

### Anti-patterns to avoid

**Only expiring the cookie:**

```java
// Illustrative only: does not invalidate server-side WebSession.
response.addCookie(ResponseCookie.from("SESSION", "")
        .path("/").maxAge(Duration.ZERO).build());
```

**Disabling CSRF so POST logout returns 2xx:**

```java
// Unsuitable for browser apps using cookies/sessions.
http.csrf(csrf -> csrf.disable());
```

**Logging out via GET:**

```http
GET /logout HTTP/1.1
Cookie: SESSION=...
```

All three patterns above can lead to security vulnerabilities or client/server state desynchronization.

## 12. Self-Check Questions

**1.** How do `SecurityContextServerLogoutHandler` and `WebSessionServerLogoutHandler` differ?  
**Answer:** One clears the saved authentication context; the other invalidates the entire `WebSession`.

**2.** Why is deleting the cookie insufficient?  
**Answer:** The old session ID can remain valid server-side and be reused if exposed.

**3.** Why must cookie handling still be considered alongside server invalidation?  
**Answer:** The browser may retain stale state/cookies and the app may have other cookies to clear.

**4.** Which method is used for logout in default WebFlux?  
**Answer:** POST `/logout`, with CSRF protection when enabled.

**5.** What happens to POST `/logout` without a token?  
**Answer:** Usually receives 403 and does not complete logout.

**6.** Should `GET /logout` be used to log out directly?  
**Answer:** No; it may serve a confirmation page and should not be designed as a state-changing logout.

**7.** Which key attributes must match when deleting a cookie?  
**Answer:** Name along with `Path` and `Domain` scope; send `Max-Age=0` or a past `Expires`.

**8.** What does default WebFlux typically name the session cookie?  
**Answer:** `SESSION` via `CookieWebSessionIdResolver`; verify if custom config is present.

**9.** Why must a fresh token be fetched after logout?  
**Answer:** The old token belonged to the prior session context; state-changing requests in a new session need a fresh valid token.

**10.** Do `mockUser` + `csrf()` prove the server session ID was invalidated?  
**Answer:** Not yet; test real login/logout and retrying the old ID.

**11.** Does local logout terminate all sessions for the same user on other machines?  
**Answer:** Not by default.

**12.** Does session logout revoke JWTs?  
**Answer:** No. Session and token lifecycles are separate mechanisms.

### Practice exercises

1. Run the demo, log in, open `/me`, POST logout with valid CSRF; verify the expiring `Set-Cookie` and that `/me` is no longer authenticated.
2. Try sending POST without CSRF while a session exists, observe 403; do not disable CSRF.
3. Create a cookie with `Path=/account`, try expiring it with `Path=/` and `Path=/account`, and compare results in DevTools.
4. Try replacing `HttpStatusReturningServerLogoutSuccessHandler` with a redirect success handler suited for browsers while keeping all cleanup steps.
5. Build an E2E test using a cookie jar: real login, save ID, logout, try sending the old ID from another client.
6. Trace why a user logged out in tab A still sees stale content in tab B; describe the UX/client/server boundaries.
7. If using a Redis session store, test requests hitting another instance after logout.
8. Draft a "log out all devices" design specifying the session registry, refresh tokens, identity provider, and revocation scope.

## 13. Official Documentation

- [Spring Security — Logout for WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/logout.html): coordinating context/session handlers.
- [Spring Security — CSRF for WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html): POST logout, tokens, and session timeout.
- [Spring Security API — ServerHttpSecurity.LogoutSpec](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.LogoutSpec.html): logout URL and handlers.
- [Spring Security API — CsrfServerLogoutHandler](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/CsrfServerLogoutHandler.html): clearing tokens.
- [Spring Security — Testing CSRF with WebTestClient](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html): `mutateWith(csrf())`.
- [Spring Framework — CookieWebSessionIdResolver](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/web/server/session/CookieWebSessionIdResolver.html): `SESSION` cookie and resolver.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): `Path`, `Domain`, `Max-Age`, and cookie security.
- [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): protecting state-changing requests.

**Key takeaway:** Logout in Spring Security reactive is a coordinated flow: **POST with valid CSRF → clear `SecurityContext` → clear CSRF token → invalidate `WebSession` → expire matching cookies → update UI**. Never confuse deleting a cookie client-side with revoking sessions/tokens on the server.