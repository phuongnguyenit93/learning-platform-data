# Testing Form Login, Session Cookies, and Logout

## 1. Why must we test the **entire** login → session → logout journey?

A Spring WebFlux application using Spring Security form login can pass `@WithMockUser` tests yet still fail in a real browser: the form POST is missing CSRF, the response fails to issue a session cookie, the cookie is not sent back on the next request, the session lacks `SecurityContext`, or `POST /logout` redirects successfully while the old session can still access resources.

This lesson belongs to the **HTTP Testing** group in the **Spring Security - reactive** module. The focus is not just asserting a single authenticated request, but verifying the **sequential chain of HTTP requests**:

~~~text
Browser / WebTestClient           Spring WebFlux + Spring Security
          |                                   |
          | GET /login                        |
          |---------------------------------->|
          | 200 HTML login form + CSRF        |
          |<----------------------------------|
          |                                   |
          | POST /login (username,password)   |
          | + SESSION cookie + CSRF token     |
          |---------------------------------->|
          | Password verification, save       |
          | SecurityContext in WebSession     |
          |<----------------------------------|
          | 302 redirect + Set-Cookie SESSION |
          |                                   |
          | GET /me + SESSION                 |
          |---------------------------------->|
          | 200 authenticated principal       |
          |<----------------------------------|
          |                                   |
          | POST /notes + SESSION + CSRF      |
          |---------------------------------->|
          | 200 if authorized                 |
          |<----------------------------------|
          |                                   |
          | POST /logout + SESSION + CSRF     |
          |---------------------------------->|
          | Clear context / invalidate        |
          | WebSession per logout policy      |
          |<----------------------------------|
          | 302 redirect, cookie retired      |
          |                                   |
          | GET /me + OLD SESSION             |
          |---------------------------------->|
          | 302 to /login (no auth)           |
          |<----------------------------------|
~~~

At a minimum, tests must prove:
1. Unauthenticated callers cannot access protected routes.
2. `GET /login` displays the form (under the default configuration).
3. `POST /login` missing or with an invalid CSRF token returns 403.
4. Wrong username/password does not create an authenticated session.
5. Valid credentials + valid CSRF create authentication and issue/maintain the session cookie.
6. A **subsequent request** carrying the preserved/updated cookie receives the right principal.
7. A request without a cookie or with a forged cookie cannot borrow the previous request's authentication.
8. A logged-in user lacking the required role still receives 403 on a protected admin endpoint.
9. Unsafe requests while logged in still require CSRF.
10. `GET /logout` does not log out; `POST /logout` without CSRF is blocked.
11. A valid `POST /logout` invalidates/clears state according to policy.
12. **Even when a client intentionally replays the old session ID**, the backend no longer accepts it as an active login.

**A test that only calls `mockUser()` and GETs a protected route returning 200 does not verify forms, cookies, passwords, session fixation, or logout.** You must use `WebTestClient` with a real sequence of cookies and CSRF tokens, and distinguish what is being mocked.

## 2. Spring Security Reactive components to understand

| Component | Role in form login/session/logout |
| --- | --- |
| `ServerHttpSecurity` | Reactive Security DSL |
| `SecurityWebFilterChain` | WebFilter chain for HTTP requests |
| `AuthenticationWebFilter` | Handles authentication requests, e.g. username/password |
| `ReactiveAuthenticationManager` | Verifies credentials via the appropriate provider |
| `ReactiveUserDetailsService` | Loads users, password hashes, and authorities |
| `PasswordEncoder` | Verifies passwords securely |
| `WebSession` | WebFlux session, with an ID and server-side state |
| `WebSessionServerSecurityContextRepository` | Saves/loads `SecurityContext` from `WebSession` |
| `ReactorContextWebFilter` | Reads `SecurityContext` for Reactor Context |
| `WebSessionServerCsrfTokenRepository` | By default stores the expected CSRF token in `WebSession` |
| `XorServerCsrfTokenRequestAttributeHandler` | Spring Security 6.x default masked CSRF token handler, reducing BREACH risk |
| `CsrfWebFilter` | Enforces CSRF on unsafe HTTP methods |
| `LogoutWebFilter` | Detects logout requests per matcher |
| `SecurityContextServerLogoutHandler` | Clears the stored authentication context |
| `WebSessionServerLogoutHandler` | Invalidates `WebSession` when configured |
| `WebTestClient` | Test client for Reactive HTTP handlers/filters |
| `SecurityMockServerConfigurers.springSecurity()` | Attaches Spring Security support to `WebTestClient` |
| `SecurityMockServerConfigurers.csrf()` | Test mutator supplying a valid CSRF token |
| `SecurityMockServerConfigurers.mockUser()` | Test mutator setting a mock principal, bypassing real login |

**Do not mix Servlet and WebFlux.** This lesson uses `WebSession` / the `SESSION` cookie instead of reasoning from Servlet's `HttpSession`/`JSESSIONID`. Applications may customize the cookie name and use Spring Session with a Redis backend; always check the cookie name in the actual configuration.

## 3. Form login: path, method, redirects, and passwords

Minimal WebFlux configuration:

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
            .authorizeExchange(ex -> ex
                    .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
~~~

This is a **snippet**, omitting `ReactiveUserDetailsService` and imports; the complete standalone project is in section 9. When default form login is enabled:
- Unauthenticated GET to a protected resource → normally redirects to `/login`, **not defaulting to 401 JSON** like a Bearer API.
- `GET /login` renders the default HTML login page (when no custom loginPage is configured).
- `POST /login` submits `application/x-www-form-urlencoded` with `username` and `password`.
- Before authentication, `CsrfWebFilter` checks the form POST's token.
- Valid credentials → authentication succeeds; security context is saved to the repository; success handler redirects to an appropriate URL such as the saved request or default target.
- Invalid credentials → redirects to the failure URL, typically `/login?error`, without saving an authenticated principal.
- `GET /logout` may render a confirmation page; `POST /logout` performs logout when CSRF is valid.

### 3.1. Why not hardcode every `Location` assertion to `"/"`?

Spring Security can save the requested URL before redirecting to login. If a user accesses `GET /me` while unauthenticated, after logging in they may be redirected back to that prior URL. If there is no relevant request cache, the success target may be `/`.

**Good testing practice**: assert a 3xx response that is not the error redirect when credentials are valid, and assert that a GET to a protected route using the session cookie returns the **right principal**. Only assert an exact `Location` when the application defines a strict success handler contract.

### 3.2. 401 and 302 are not equivalent

| Request | Common outcome | Explanation |
| --- | --- | --- |
| GET `/me` when anonymous, Form Login | 302 to `/login` | Unauthenticated, login-oriented entry point |
| GET `/login` | 200 HTML | Default form rendered |
| POST `/login` wrong password with valid CSRF | 302 to `/login?error` | Authentication failure |
| POST `/login` missing CSRF | 403 | CSRF blocks before password verification |
| GET `/admin` with USER session | 403 | Authenticated but lacking ADMIN |
| GET `/me` after login with valid cookie | 200 | SecurityContext restored |
| POST `/logout` missing CSRF | 403 | Logout does not happen |
| Valid POST `/logout` | Typically 302 to login page | Context/session cleaned up |
| GET `/me` with old invalidated cookie | 302 to `/login` | Authenticated state no longer exists |

These redirect/status codes reflect the **demo configuration**, not universal constants for custom success/failure handlers or JSON-returning APIs.

## 4. Session cookies: a cookie is not the whole Authentication

With WebFlux session-based login, browsers typically store a `SESSION` cookie carrying the **session ID**. The server uses that ID to look up `WebSession` and `SecurityContext`.

~~~text
Cookie: SESSION=<opaque-session-id>
              |
              v
WebSessionManager -> session store
              |
              v
WebSessionServerSecurityContextRepository
              |
              v
SecurityContext -> Authentication -> principal/roles
              |
              v
authorizeExchange -> handler
~~~

**A session cookie is not a JWT access token.** A cookie ID does not itself carry roles or passwords (in the standard WebSession model); the backend determines the user from the session store. Never decode the cookie like a JWT or trust `Cookie: SESSION=admin` as a role.

### 4.1. Do not test every request with a completely stateless WebTestClient

`WebTestClient` does not automatically maintain a browser-like cookie jar across every test/request. In the tests below, we **explicitly extract `Set-Cookie: SESSION` from the response**, then send `Cookie: SESSION=...` back in the next request. If the session ID changes after login, capture the **latest** ID rather than reusing the pre-login ID.

Test protocol:
1. GET `/csrf` to obtain a CSRF token and initialize `WebSession`.
2. Extract the `SESSION` response cookie from GET `/csrf`.
3. POST `/login` with the same `SESSION` + CSRF token + form credentials.
4. Capture the new `SESSION` from the login response if issued; if no new `Set-Cookie` is sent, keep the current ID.
5. GET `/me` with the active `SESSION`.
6. Fetch a fresh CSRF token within the post-login session before unsafe requests or logout.
7. POST `/logout` with the active session + CSRF token.
8. Use the **pre-logout ID** on GET `/me` to prove server-side invalidation.

### 4.2. Session fixation

By default, `WebSessionServerSecurityContextRepository` rotates the session ID when saving `SecurityContext` after authentication to mitigate session fixation. A test should not assume the pre-login cookie remains the session ID forever. **Keep the latest returned cookie**, and test old vs new IDs on your specific version if session-fixation rotation is an acceptance criterion.

Never claim "login returned 200" means session fixation is safe. Verify `Set-Cookie`, `WebSession` ID rotation, cookie domain/path, and behavior across proxies/sticky sessions/Redis.

### 4.3. Cookie security flags

- **HttpOnly:** JavaScript cannot read the cookie via `document.cookie`, reducing some XSS theft risk; does not prevent XSS or CSRF by itself.
- **Secure:** browsers send the cookie only over HTTPS; must be enabled in production; the local demo uses HTTP so it is not enabled yet.
- **SameSite:** Lax/Strict/None depending on SSO/cross-site flows; **does not replace CSRF tokens** when ambient cookies exist.
- **Path:** only restricts where the browser sends the cookie, not application permissions.
- **Domain:** avoid setting it overly broad across all subdomains unless needed.
- **Session timeout:** verify server-side expiry, not just cookie max-age.
- **Rotation/invalidation:** login and logout must manage session lifecycle rather than just hiding UI state.

Spring Boot 3.5 provides `server.reactive.session.cookie.*` and `server.reactive.session.timeout` for WebFlux; do not mistakenly use `server.servlet.session.*` in the Reactive stack.

## 5. CSRF with login and logout forms

A browser can automatically include the `SESSION` cookie on requests to the site. An attacker does not need to read the cookie to trick a browser into sending a cross-site POST to the application. Therefore Spring Security WebFlux enables CSRF by default; specifically, **both login and logout must be protected**.

With WebFlux defaults:
- `WebSessionServerCsrfTokenRepository` stores the **expected CSRF token** in `WebSession`.
- `CsrfWebFilter` requires the token on unsafe methods such as POST.
- The token is exposed as a request attribute of type `Mono<CsrfToken>`.
- `XorServerCsrfTokenRequestAttributeHandler` provides a **masked token** for browsers/templates in Spring Security 6.x to mitigate BREACH.
- Clients submit the token in form parameter `_csrf` or the header given by `CsrfToken.getHeaderName()`, typically `X-CSRF-TOKEN`.
- The expected token is bound to the session; if the `SESSION` cookie is missing or belongs to another session, the CSRF value is rejected.

### 5.1. Typical HTML form

~~~html
<form action="/login" method="post">
  <input type="text" name="username" autocomplete="username" />
  <input type="password" name="password" autocomplete="current-password" />
  <input type="hidden" name="_csrf" value="masked-csrf-token-from-server" />
  <button type="submit">Sign in</button>
</form>
~~~

The masked value here is an **illustrative placeholder**, not a real token. Applications can use the default login page or Thymeleaf (which auto-injects CSRF) rather than hand-coding HTML forms.

### 5.2. Why does the demo have `GET /csrf`?

To inspect cookies + CSRF cleanly at the HTTP layer, the lesson adds a **`GET /csrf`** endpoint returning the current header name and token as JSON. Subscribing to `Mono<CsrfToken>` triggers token generation/storage in the repository, letting `WebTestClient` observe the `SESSION` cookie and submit the token back in POSTs.

**This is a learning endpoint**, not mandatory for all apps. With SSR + Thymeleaf, forms embed the token automatically; SPAs need a secure token contract with tight CORS, no response caching, and XSS defenses. Never expose this endpoint cross-origin arbitrarily.

### 5.3. A 403 on missing CSRF does not prove the password is wrong

If `POST /login` returns 403, the first things to check are the session cookie and CSRF token. A wrong password **with a valid CSRF token** normally passes through `AuthenticationManager` and redirects to the error page.

Avoid "fixing" login 403s with `csrf(disable)` in apps using session cookies. CSRF and password verification are separate steps, and both need tests.

### 5.4. Successful login can invalidate the pre-login CSRF token

Authentication or logout can clear/rotate the CSRF token depending on configuration. Thus, tests should **fetch a new CSRF token after login** before posting to `/notes` or `/logout`, rather than assuming the pre-login token remains valid.

Calling `mutateWith(csrf())` helps test single requests, but does not verify the CSRF lifecycle across multiple requests and real session cookies. In this lesson, the **main test suite** uses tokens returned by the controller rather than bypassing the CSRF filter with a mutator.

## 6. Logout is more than deleting a cookie on the client

Per Spring Security Reactive documentation:
- Default logout provides `GET /logout` for confirmation and `POST /logout` to execute the action.
- On a valid POST, logout handlers can clear `ServerSecurityContextRepository` and the CSRF repository, then redirect.
- To **invalidate `WebSession`**, configure `WebSessionServerLogoutHandler` alongside `SecurityContextServerLogoutHandler`.

In the demo, we explicitly configure:

~~~java
.logout(logout -> logout.logoutHandler(
    new DelegatingServerLogoutHandler(
        new SecurityContextServerLogoutHandler(),
        new WebSessionServerLogoutHandler()
    )
))
~~~

This is a snippet; full imports are in `SecurityConfig.java`.

**Why test with the old cookie?** A 302 logout response or clearing cookies in the browser is not enough to prove the server-side session is no longer trusted. Tests must intentionally replay the **old ID** on a protected request and verify it is no longer authenticated.

### 6.1. `GET /logout` is not the logout action

A proper test:
1. Log in successfully, saving `SESSION`.
2. GET `/logout` (default confirmation page).
3. GET `/me` **still** returns 200 with the same session.
4. Only `POST /logout` + CSRF actually ends the session.
5. GET `/me` with the old cookie must not return 200.

Do not change logout to GET just to make links easier to write; GET can be triggered by prefetchers/crawlers and enables logout CSRF.

### 6.2. Logout does not guarantee revoking every token or login session

If the application also uses remember-me, JWT Bearer, OAuth2 Login, an SSO IdP session, Spring Session Redis, or multiple services, "local WebSession logout" does not automatically revoke access/refresh tokens or perform global sign-out. Design IdP logout, token revocation, client logout, cookie clearing, and distributed session invalidation explicitly per security contract.

## 7. HTTP test matrix to include

| Test case | Method/path | Cookie | CSRF | Credentials/role | Expected |
| --- | --- | --- | --- | --- | --- |
| Public home | GET `/` | None | None | Anonymous | 200 |
| Login page | GET `/login` | None | None | Anonymous | 200 HTML |
| Protected anonymous | GET `/me` | None | None | Anonymous | 302 login |
| Login missing CSRF | POST `/login` | Any | Missing | Alice valid | 403 |
| Login wrong CSRF | POST `/login` | Valid SESSION | Wrong | Alice valid | 403 |
| CSRF without matching session | POST `/login` | Missing SESSION | Other session's CSRF | Alice valid | 403 |
| Login wrong password | POST `/login` | SESSION + token | Valid | Alice wrong password | 302 error |
| Login unknown user | POST `/login` | SESSION + token | Valid | Unknown username | 302 error |
| Login success | POST `/login` | SESSION + token | Valid | Alice valid | 302, session saved |
| Follow-up request | GET `/me` | Active SESSION | Not needed | Alice | 200, name=alice |
| Missing cookie | GET `/me` | None | Not needed | Anonymous | 302 login |
| Forged session cookie | GET `/me` | Unknown | Not needed | None | 302 login |
| User lacking admin role | GET `/admin` | Alice SESSION | None | ROLE_USER | 403 |
| Real admin | GET `/admin` | Bob SESSION | None | ROLE_ADMIN | 200 |
| Unsafe missing CSRF | POST `/notes` | Alice SESSION | Missing | ROLE_USER | 403 |
| Unsafe with CSRF | POST `/notes` | Alice SESSION | Valid | ROLE_USER | 200 |
| Session A CSRF with session B | POST `/notes` | Bob SESSION | Alice's token | Bob | 403 |
| GET logout | GET `/logout` | Alice SESSION | None | Alice | Not logged out |
| POST logout missing CSRF | POST `/logout` | Alice SESSION | Missing | Alice | 403, session alive |
| POST logout with CSRF | POST `/logout` | Alice SESSION | Valid | Alice | Redirect, session ended |
| Old cookie after logout | GET `/me` | OLD SESSION | None | Unauthenticated | 302 login |

The goal is verifying **both security decisions and state transitions**. Checking only the status of POST login/logout without testing the subsequent request is incomplete testing.

## 8. Complete project: Java 17 + Spring Boot WebFlux

Uses Spring Boot 3.5.7 + Java 17 for the learning example. Production versions must receive security patches in the deployment environment. You may use your project's Gradle Wrapper; the example below does not pre-generate wrapper binaries.

Structure:

~~~text
webflux-form-session-test/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── DemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── DemoController.java
    │   └── resources/
    │       └── application.yml
    └── test/java/demo/
        ├── FormSessionFlowTest.java
        └── SecurityTestHelpersTest.java
~~~

### 8.1. `settings.gradle`

~~~groovy
rootProject.name = 'webflux-form-session-test'
~~~

### 8.2. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
~~~

Do not add `spring-boot-starter-web` since that is the Servlet MVC stack; this lesson uses Reactive WebFlux only. An OAuth2 Resource Server starter is not needed either: form login here uses username/password and `WebSession`.

### 8.3. `application.yml`

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
  reactive:
    session:
      timeout: 20m
      cookie:
        name: SESSION
        http-only: true
        same-site: lax
        path: /
        # To allow localhost HTTP to work, Secure is not forced in this demo.
        # In production HTTPS: server.reactive.session.cookie.secure=true

spring:
  application:
    name: webflux-form-session-test
~~~

This cookie configuration is strictly local; **production requires HTTPS + Secure**, reviewing Domain/Path/SameSite, proxy TLS termination, HSTS, and the session store. `SameSite=Lax` mitigates certain scenarios but **does not replace CSRF**. `HttpOnly` prevents JavaScript from reading cookies, yet XSS can still send requests within the user's context.

### 8.4. `DemoApplication.java`

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

## 9. `SecurityConfig.java` — form login, default CSRF, and session invalidation

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        // {bcrypt} encoded passwords; never store real raw passwords.
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("bob-pass"))
                .roles("USER", "ADMIN")
                .build();

        // DEMO accounts only; production uses a secure user store/IdP.
        return new MapReactiveUserDetailsService(alice, bob);
    }

    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET,
                                "/", "/login", "/logout", "/csrf")
                                .permitAll()
                        .pathMatchers(HttpMethod.POST,
                                "/login", "/logout")
                                .permitAll()
                        .pathMatchers(HttpMethod.GET, "/admin")
                                .hasRole("ADMIN")
                        .pathMatchers(HttpMethod.GET, "/me")
                                .authenticated()
                        .pathMatchers(HttpMethod.POST, "/notes")
                                .authenticated()
                        .anyExchange().denyAll())
                // Enable form login. Default login page is at /login.
                .formLogin(Customizer.withDefaults())
                // HTTP Basic not needed in this form-login test lesson.
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                // CSRF is ENABLED by default; do not call .csrf(disable).
                .logout(logout -> logout.logoutHandler(
                        new DelegatingServerLogoutHandler(
                                new SecurityContextServerLogoutHandler(),
                                new WebSessionServerLogoutHandler())))
                .build();
    }
}
~~~

### 9.1. Role of each option

- `formLogin` enables form POST username/password; Spring Security configures the default login page/entry point when no custom page is set.
- `ReactiveUserDetailsService` loads users; `PasswordEncoder` verifies password hashes according to the configured algorithm.
- `permitAll` on `POST /login` **does not skip CSRF**: `CsrfWebFilter` still applies.
- `GET /admin` requires `ROLE_ADMIN`; Alice with only `USER` gets 403.
- `POST /notes` is protected by both authentication and CSRF.
- `anyExchange().denyAll()` blocks unreviewed URLs/methods.
- `SecurityContext` is saved/restored using the default WebSession repository in the form-login path; do **not** configure `NoOpServerSecurityContextRepository` like a Bearer-only API.
- `SecurityContextServerLogoutHandler` clears stored authentication; `WebSessionServerLogoutHandler` makes the session unusable after logout.
- **Do not use** `.csrf(ServerHttpSecurity.CsrfSpec::disable)` because this app uses session cookies.

### 9.2. Successful login requires no custom `POST /login` controller

Spring Security handles `POST /login` via filters. The controller only declares protected routes and the endpoint returning a CSRF token for testing. Writing a manual `@PostMapping("/login")` that calls `ReactiveUserDetailsService.findByUsername` and sets the session context directly easily breaks session fixation protection, exception/failure handlers, and CSRF.

### 9.3. Pitfalls with `User.withDefaultPasswordEncoder` or `{noop}`

This lesson uses `PasswordEncoderFactories.createDelegatingPasswordEncoder()` and encoded passwords (typically `{bcrypt}...`). Accounts/passwords are **demo data in instructional code**; these credentials must never be used in production.

Avoid `{noop}productionPassword` or storing raw passwords in config. In production, use bcrypt/argon2/pbkdf2 per policy, salting/rehashing, and a secure user store/IdP rather than a static `MapReactiveUserDetailsService`.

## 10. `DemoController.java` — CSRF endpoint and protected routes

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import java.security.Principal;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    public record CsrfView(
            String headerName,
            String parameterName,
            String token) {
    }

    public record NoteRequest(String text) {
    }

    public record NoteResult(String owner, String text) {
    }

    @GetMapping("/")
    public Mono<String> home() {
        return Mono.just("home");
    }

    @GetMapping(path = "/csrf",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<CsrfView> csrf(ServerWebExchange exchange) {
        // CsrfWebFilter exposes Mono<CsrfToken> as exchange attribute.
        Mono<CsrfToken> token =
                exchange.getAttribute(CsrfToken.class.getName());

        // Subscribing triggers lazy token generation/saving in WebSession.
        if (token == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF filter/token attribute is missing"));
        }

        return token.map(value -> new CsrfView(
                value.getHeaderName(),
                value.getParameterName(),
                value.getToken()));
    }

    @GetMapping("/me")
    public Mono<Map<String, String>> currentUser(Principal principal) {
        return Mono.just(Map.of("username", principal.getName()));
    }

    @GetMapping("/admin")
    public Mono<String> admin(Principal principal) {
        return Mono.just("admin:" + principal.getName());
    }

    @PostMapping(path = "/notes",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<NoteResult> note(
            Principal principal,
            @RequestBody Mono<NoteRequest> body) {
        return body.map(value ->
                new NoteResult(principal.getName(), value.text()));
    }
}
~~~

**Response note:** the `/notes` endpoint merely echoes test data without saving to a database. Real products need validation, quotas, ownership checks, and auditing, and must never put sensitive data into responses.

### 10.1. The CSRF token here is a masked token

In Spring Security Reactive 6.x defaults, `CsrfToken.getToken()` is exposed via XOR/masking. Clients send **the exact token received from `/csrf`** in header `CsrfView.headerName` (usually `X-CSRF-TOKEN`). Do not manually decode, unmask, or naively compare tokens across multiple GETs.

With server-side Thymeleaf login forms, the template engine provides CSRF integration; a JSON `/csrf` API is not required for all WebFlux apps.

### 10.2. Should `/csrf` be public?

If a frontend needs a token before login, the endpoint may be `permitAll` as in this example, provided you:
- Maintain **same-origin policy** and a strict CORS allowlist.
- Ensure responses are never cached by shared CDNs; consider `Cache-Control: no-store`.
- Never echo tokens into logs, tracing, or analytics.
- Never allow attacker pages to read the token via permissive CORS.
- Defend against XSS, since scripts running in the same origin can use the token to submit requests.
- Rotate/update token/session lifecycle per contract on authentication/logout.

## 11. `FormSessionFlowTest.java` — testing REAL cookies and CSRF across multiple HTTP requests

This section uses:
- `WebTestClient.bindToApplicationContext(context).apply(springSecurity())`.
- **No** `@WithMockUser`, **no** `mockUser()`, **no** `mutateWith(csrf())` in the main test suite.
- The CSRF token is read from controller `GET /csrf` through the real server pipeline.
- The `SESSION` cookie is extracted from `Set-Cookie` in the test response and sent back in subsequent requests.
- Username/password go through the real form authentication filter and `PasswordEncoder`.

That is the difference between a **session-flow integration test** and a **mock authorization-only test**.

### 11.1. Complete code

`src/test/java/demo/FormSessionFlowTest.java`:

~~~java
package demo;

import java.util.Objects;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.util.MultiValueMap;
import org.springframework.web.reactive.function.BodyInserters;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class FormSessionFlowTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    private record CsrfTicket(
            String sessionId, String headerName, String token) {
    }

    private record LoginResult(
            String sessionId, String redirect) {
    }

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    // SESSION cookie may be replaced/rotated on each transition.
    private static String latestSession(
            MultiValueMap<String, ResponseCookie> responseCookies,
            String previous) {
        ResponseCookie cookie = responseCookies.getFirst("SESSION");
        if (cookie != null && !cookie.getValue().isEmpty()) {
            return cookie.getValue();
        }
        return previous;
    }

    // Fetch a real CSRF token from the server and preserve the session cookie.
    private CsrfTicket csrf(String existingSessionId) {
        var request = client.get().uri("/csrf");
        if (existingSessionId != null) {
            request.cookie("SESSION", existingSessionId);
        }

        var response = request.exchange()
                .expectStatus().isOk()
                .expectBody(DemoController.CsrfView.class)
                .returnResult();

        DemoController.CsrfView body =
                Objects.requireNonNull(response.getResponseBody());
        String sessionId = latestSession(
                response.getResponseCookies(), existingSessionId);

        assertNotNull(sessionId,
                "Expected SESSION cookie for WebSession CSRF token");
        assertNotNull(body.token());
        return new CsrfTicket(
                sessionId, body.headerName(), body.token());
    }

    // Log in using real form + CSRF + SESSION; no mockUser().
    private LoginResult login(String username, String password) {
        CsrfTicket preLogin = csrf(null);

        var response = client.post().uri("/login")
                .cookie("SESSION", preLogin.sessionId())
                .header(preLogin.headerName(), preLogin.token())
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("username", username)
                        .with("password", password))
                .exchange()
                .expectStatus().is3xxRedirection()
                .returnResult(Void.class);

        String activeSession = latestSession(
                response.getResponseCookies(),
                preLogin.sessionId());
        assertNotNull(activeSession);

        return new LoginResult(
                activeSession,
                String.valueOf(response.getResponseHeaders()
                        .getLocation()));
    }

    @Test
    void homeIsPublic() {
        client.get().uri("/")
                .exchange().expectStatus().isOk()
                .expectBody(String.class).isEqualTo("home");
    }

    @Test
    void loginPageCanBeLoaded() {
        client.get().uri("/login")
                .exchange().expectStatus().isOk();
    }

    @Test
    void anonymousProtectedRequestRedirectsToLogin() {
        client.get().uri("/me")
                .exchange().expectStatus().is3xxRedirection()
                .expectHeader().valueMatches(
                        "Location", ".*\\/login.*");
    }

    @Test
    void loginWithoutCsrfIs403() {
        client.post().uri("/login")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData(
                        "username", "alice")
                        .with("password", "alice-pass"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void loginWithBadCsrfIs403() {
        CsrfTicket ticket = csrf(null);

        client.post().uri("/login")
                .cookie("SESSION", ticket.sessionId())
                .header(ticket.headerName(), "incorrect-csrf")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData(
                        "username", "alice")
                        .with("password", "alice-pass"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void csrfTokenWithoutItsSessionIs403() {
        CsrfTicket ticket = csrf(null);

        client.post().uri("/login")
                // Omit the CSRF token's session cookie.
                .header(ticket.headerName(), ticket.token())
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData(
                        "username", "alice")
                        .with("password", "alice-pass"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void badPasswordRedirectsToErrorAndDoesNotAuthenticate() {
        LoginResult result = login("alice", "wrong-password");
        assertTrue(result.redirect().contains("error"));

        client.get().uri("/me")
                .cookie("SESSION", result.sessionId())
                .exchange().expectStatus().is3xxRedirection();
    }

    @Test
    void unknownUsernameDoesNotCreateAuthentication() {
        LoginResult result = login("nonexistent", "whatever");
        assertTrue(result.redirect().contains("error"));

        client.get().uri("/me")
                .cookie("SESSION", result.sessionId())
                .exchange().expectStatus().is3xxRedirection();
    }

    @Test
    void correctFormLoginCreatesAuthenticatedSession() {
        LoginResult result = login("alice", "alice-pass");
        assertTrue(!result.redirect().contains("error"));

        client.get().uri("/me")
                .cookie("SESSION", result.sessionId())
                .exchange().expectStatus().isOk()
                .expectBody()
                .jsonPath("$.username").isEqualTo("alice");
    }

    @Test
    void sameSessionCookieRestoresPrincipalOnNextRequest() {
        LoginResult login = login("alice", "alice-pass");

        for (int i = 0; i < 2; i++) {
            client.get().uri("/me")
                    .cookie("SESSION", login.sessionId())
                    .exchange().expectStatus().isOk()
                    .expectBody()
                    .jsonPath("$.username").isEqualTo("alice");
        }
    }

    @Test
    void withoutSessionCookiePreviousLoginDoesNotCarryOver() {
        LoginResult loggedIn = login("alice", "alice-pass");
        assertNotNull(loggedIn.sessionId());

        client.get().uri("/me")
                .exchange().expectStatus().is3xxRedirection();
    }

    @Test
    void fabricatedSessionCookieCannotImpersonateUser() {
        client.get().uri("/me")
                .cookie("SESSION", "not-a-session-created-by-server")
                .exchange().expectStatus().is3xxRedirection();
    }

    @Test
    void userRoleCannotReadAdminPage() {
        LoginResult login = login("alice", "alice-pass");
        client.get().uri("/admin")
                .cookie("SESSION", login.sessionId())
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void adminRoleCanReadAdminPage() {
        LoginResult login = login("bob", "bob-pass");
        client.get().uri("/admin")
                .cookie("SESSION", login.sessionId())
                .exchange().expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin:bob");
    }

    @Test
    void authenticatedPostWithoutCsrfStillGets403() {
        LoginResult login = login("alice", "alice-pass");

        client.post().uri("/notes")
                .cookie("SESSION", login.sessionId())
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new DemoController.NoteRequest("hello"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void authenticatedPostWithFreshSessionCsrfSucceeds() {
        LoginResult login = login("alice", "alice-pass");
        CsrfTicket ticket = csrf(login.sessionId());

        client.post().uri("/notes")
                .cookie("SESSION", ticket.sessionId())
                .header(ticket.headerName(), ticket.token())
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new DemoController.NoteRequest("hello"))
                .exchange().expectStatus().isOk()
                .expectBody()
                .jsonPath("$.owner").isEqualTo("alice")
                .jsonPath("$.text").isEqualTo("hello");
    }

    @Test
    void csrfFromOneSessionCannotAuthorizeAnotherSessionPost() {
        LoginResult alice = login("alice", "alice-pass");
        LoginResult bob = login("bob", "bob-pass");
        CsrfTicket aliceTicket = csrf(alice.sessionId());
        CsrfTicket bobTicket = csrf(bob.sessionId());

        client.post().uri("/notes")
                .cookie("SESSION", bobTicket.sessionId())
                .header(aliceTicket.headerName(), aliceTicket.token())
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new DemoController.NoteRequest("cross-session"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void getLogoutDoesNotActuallyEndSession() {
        LoginResult login = login("alice", "alice-pass");
        client.get().uri("/logout")
                .cookie("SESSION", login.sessionId())
                .exchange().expectStatus().isOk();

        client.get().uri("/me")
                .cookie("SESSION", login.sessionId())
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.username")
                .isEqualTo("alice");
    }

    @Test
    void postLogoutWithoutCsrfDoesNotEndSession() {
        LoginResult login = login("alice", "alice-pass");

        client.post().uri("/logout")
                .cookie("SESSION", login.sessionId())
                .exchange().expectStatus().isForbidden();

        client.get().uri("/me")
                .cookie("SESSION", login.sessionId())
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.username")
                .isEqualTo("alice");
    }

    @Test
    void validPostLogoutInvalidatesOldSession() {
        LoginResult login = login("alice", "alice-pass");
        CsrfTicket ticket = csrf(login.sessionId());

        client.post().uri("/logout")
                .cookie("SESSION", ticket.sessionId())
                .header(ticket.headerName(), ticket.token())
                .exchange().expectStatus().is3xxRedirection();

        // Even when replaying the old ID intentionally, the server rejects it as logged out.
        client.get().uri("/me")
                .cookie("SESSION", ticket.sessionId())
                .exchange().expectStatus().is3xxRedirection()
                .expectHeader().valueMatches(
                        "Location", ".*\\/login.*");
    }
}
~~~

### 11.2. Detailed explanation of helper methods

`csrf(existingSessionId)`:
- GETs `/csrf`, with or without sending an existing session.
- Reads `CsrfView` from the JSON response.
- Reads `SESSION` from `response.getResponseCookies()`.
- Returns token + headerName + sessionId **in a single object**, avoiding mixing session A's token with session B's cookie.
- If no `SESSION` cookie is present when initializing the CSRF token, the test fails with a meaningful message rather than assuming the client retains sessions automatically.

`login(username, password)`:
- Fetches a pre-login CSRF token.
- Sends **form URL encoded** data like a browser, rather than JSON to the default `POST /login`.
- Sends the matching `SESSION` cookie and CSRF token.
- Asserts a redirect response.
- If login responds with a new `Set-Cookie SESSION`, captures the new ID; otherwise retains the current ID.
- Returns session ID and `Location` so assertions can verify post-login state or failure redirects.

**Note:** the `login()` helper is shared across both success and failure tests because both can return 3xx. Tests judge success by the redirect target and subsequent `GET /me`, not solely by POST returning 3xx.

### 11.3. Why assert the user via `GET /me` afterward?

If a test only checks that `POST /login` redirects, a buggy server could still redirect without saving `SecurityContext`. Calling `GET /me` with the new cookie proves the framework reloaded authentication from the session store on **another request**.

### 11.4. Why must logout be tested both ways?

- **Missing CSRF**: `POST /logout` returns 403, and **the session still accesses `/me` successfully**.
- **With CSRF**: `POST /logout` redirects, and **the old cookie is rejected** on subsequent requests.

Thus the tests prove **protection against logout CSRF** and **no authenticated session remains after logout**, rather than checking only a 302.

## 12. `SecurityTestHelpersTest.java` — distinguishing `mockUser()` and `csrf()` from real login

Spring Security Test offers convenient mutators to test controller policies without going through form login/passwords:
- `mockUser()` injects a mocked authentication into a `WebTestClient` request.
- `csrf()` supplies a valid CSRF condition in a test request.
- `@WithMockUser` serves an equivalent authorization-testing purpose where appropriate.

**What you must NOT infer:** that because `mockUser("alice")` `GET /me` returns 200, form POST/PasswordEncoder/WebSession cookies work. Nor that because `mutateWith(csrf())` POST succeeds, real CSRF tokens match the session ID or rotate properly after login.

`src/test/java/demo/SecurityTestHelpersTest.java`:

~~~java
package demo;

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
class SecurityTestHelpersTest {

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
    void mockUserCanTestAuthorizationWithoutFormLogin() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .get().uri("/me")
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.username")
                .isEqualTo("alice");
    }

    @Test
    void mockUserWithoutCsrfCannotPost() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .post().uri("/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new DemoController.NoteRequest("note"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void mockUserAndCsrfCanTestPostAuthorization() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .mutateWith(csrf())
                .post().uri("/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new DemoController.NoteRequest("note"))
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.owner")
                .isEqualTo("alice");
    }

    @Test
    void mockAdminRoleCanAccessAdminEndpoint() {
        client.mutateWith(mockUser("bob").roles("ADMIN"))
                .get().uri("/admin")
                .exchange().expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin:bob");
    }
}
~~~

These tests are helpful for isolating **authorization policies** and CSRF request validation. They **do not create real login sessions**, do not prove `SESSION` cookie/logout invalidation, and do not verify BCrypt passwords. The two test layers complement rather than replace each other.

## 13. Running Gradle and expected results

From the project root:

~~~bash
gradle test
~~~

If using the Gradle Wrapper:

~~~bash
./gradlew test
~~~

On Windows:

~~~powershell
.\gradlew.bat test
~~~

In the sample project:
- `FormSessionFlowTest` has **20 `@Test` methods** exercising real HTTP login/logout/cookie/CSRF flows inside the `WebTestClient` application context.
- `SecurityTestHelpersTest` has **4 `@Test` methods** using `mockUser()`/`csrf()`.
- Total is **24 test methods** per the source.

**These counts/targets are by code design**, not test execution output in the authoring environment. To claim `BUILD SUCCESSFUL`, you must actually run Gradle with Java 17 and downloaded dependencies and verify the results in the project.

### 13.1. What does each test prove?

| Layer | Test | Verifies | Does NOT verify |
| --- | --- | --- | --- |
| Form/CSRF | `POST /login` missing token | `CsrfWebFilter` blocks | Password encoder or live cookies |
| Credentials | Login wrong password with valid CSRF | Authentication failure | Logout |
| Session flow | `POST /login` + `GET /me` with same cookie | Credentials, `SecurityContext` persistence | Reverse proxy TLS or distributed sessions |
| Session isolation | Missing cookie / forged cookie / cross-session CSRF | No auth reuse across sessions | All specialized session-fixation attacks |
| Authorization | Alice USER vs Bob ADMIN | Route authorities | Real data ownership |
| Logout | `POST /logout` and old-cookie `GET /me` | Server-side session invalidation per config | Global IdP logout / token revocation |
| `mockUser` | `mutateWith(mockUser())` | Controller/authority logic | Form login/password/cookies |
| `csrf` mutator | `mutateWith(csrf())` | CSRF accepts one test request | Real session CSRF lifecycle |

### 13.2. When to test an actual HTTP server instead of `bindToApplicationContext`?

`bindToApplicationContext` builds an in-process mock server pipeline; it is great for WebFilters, cookies, and sessions. However, it **cannot** replace real network integration tests for:
- HTTPS and TLS termination at the Gateway.
- `Set-Cookie` Secure/Domain/Path through a reverse proxy.
- Browser SameSite/third-party cookie policies.
- Redis/Spring Session across pods and failover.
- Load balancer sticky sessions.
- Host/forwarded headers, CORS origins, and session fixation through ingress.
- Browser navigation, HTML login form rendering, redirects, and history.
- Proxy cookie rewriting, `SameSite=None;Secure`, HSTS.

For full coverage, add `@SpringBootTest(webEnvironment = RANDOM_PORT)` with `WebTestClient` hitting a real port alongside E2E browser tests or staging Gateway tests.

## 14. Testing with `curl` and a cookie jar

Start the app:

~~~bash
gradle bootRun
~~~

GET public:

~~~bash
curl -i http://localhost:8080/
~~~

Expect 200 with body `home`.

### 14.1. Fetch session cookie and CSRF token

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/csrf
~~~

Sample JSON response:

~~~json
{
  "headerName": "X-CSRF-TOKEN",
  "parameterName": "_csrf",
  "token": "masked-csrf-value-from-server"
}
~~~

This is an **illustrative string**, not a real token. Save the received token in a shell variable or copy it manually into the next command. `cookies.txt` holds sensitive session data—never commit, log, or share it.

### 14.2. Form `POST /login`

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'X-CSRF-TOKEN: <token-from-get-csrf>' \
  --data-urlencode 'username=alice' \
  --data-urlencode 'password=alice-pass' \
  http://localhost:8080/login
~~~

Expect a redirect. `-c` must be passed to save any updated `Set-Cookie: SESSION` upon login. Never use only `-b` and discard the new `Set-Cookie`.

### 14.3. GET protected route with logged-in session

~~~bash
curl -i -b cookies.txt \
  http://localhost:8080/me
~~~

Expect 200 JSON:

~~~json
{"username":"alice"}
~~~

Omitting `-b cookies.txt` sends no session and normally redirects to `/login`.

### 14.4. POST logout with a fresh CSRF token

After login, fetch the CSRF token again:

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/csrf
~~~

Use the newly received token:

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  -X POST \
  -H 'X-CSRF-TOKEN: <new-token-from-get-csrf>' \
  http://localhost:8080/logout
~~~

Expect a redirect to the login page. Subsequent requests with the cookie jar must no longer be authenticated. To strictly test server-side invalidation, save a copy of the **old session ID** before logout and retry `GET /me` afterward; it must not return 200. Be careful never to store real session IDs in CI logs.

### 14.5. You cannot use the `csrf()` mutator in `curl`

`mutateWith(csrf())` belongs to Spring Security Test, not an HTTP endpoint/cookie or a `curl` flag. Real browsers and `curl` must fetch the token from the server and send it with the matching session.

## 15. Anti-patterns that produce "false-green" tests

### 15.1. Only `@WithMockUser` without `POST /login`

~~~java
// Tests authorization only, DOES NOT prove login.
@Test
@WithMockUser(username = "alice", roles = "USER")
void wrongConclusion() {
    client.get().uri("/me")
            .exchange().expectStatus().isOk();
}
~~~

If the client lacks proper mock-authentication wiring, the snippet needs further setup; the main point is that **a mock principal skips passwords**. To test real forms, send `POST /login` with URL-encoded credentials + CSRF, then `GET /me` with the `SESSION` cookie.

### 15.2. Disabling CSRF to make login tests pass

~~~java
// WRONG for apps using cookie form login:
http.csrf(ServerHttpSecurity.CsrfSpec::disable);
~~~

If `POST /login` returned 403 beforehand, verify the request's CSRF token and session cookie rather than disabling the security control app-wide.

### 15.3. Claiming "logout succeeded" solely from 302

~~~java
// INCOMPLETE TEST: does not prove the session actually ended.
client.post().uri("/logout")
        .exchange().expectStatus().is3xxRedirection();
~~~

With CSRF enabled, the call above would even return 403; even after adding CSRF, a 302 does not prove the old session is no longer trusted. Add `GET /me` with the **old `SESSION`** after logout.

### 15.4. Confusing `JSESSIONID` with `SESSION`

Spring WebFlux defaults to the `SESSION` cookie via `CookieWebSessionIdResolver`. Servlet containers typically use `JSESSIONID`. However, a project can customize the cookie name via `server.reactive.session.cookie.name` or a Spring Session `WebSessionIdResolver`. Tests should read actual response cookies and use the configured name rather than hardcoding a Servlet name in Reactive apps.

### 15.5. Cookie presence does not prove authentication

An anonymous session can be created solely to store a CSRF token **before login**. Testing "response has a `SESSION` cookie" proves a `WebSession` exists, **not** that `SecurityContext` holds an authenticated principal. You must `GET /me` in a new request and assert the principal.

### 15.6. Correct login redirect does not prove correct roles

A user can authenticate yet lack `ROLE_ADMIN`. Tests must verify access control on `/admin`: Alice 403, Bob 200. Domain permissions also require data-ownership tests.

### 15.7. Frontend-only logout

Simply deleting browser cookies or clearing SPA state does not guarantee the old server-side session was invalidated. An attacker holding the old ID could reuse it if the session store still treats it as valid. Test with an old-cookie request to ensure invalidation.

## 16. Session fixation, timeouts, and multiple instances

### 16.1. Session fixation on login

Scenario: an attacker tricks a browser into using a known session ID before login, then waits for the victim to sign in. If the app keeps the same session ID, the attacker can hijack it. In WebFlux, `WebSessionServerSecurityContextRepository` changes the session ID when saving `SecurityContext`, reducing the risk.

Hardening test:
1. GET `/csrf` to create a pre-login `SESSION`.
2. POST `/login` with valid credentials and the old cookie.
3. Observe `Set-Cookie: SESSION` after login.
4. Verify the response/login ID transition per policy/version.
5. GET `/me` with the **old ID**: if the implementation enforces rotation/invalidation, it must not access the new user.
6. GET `/me` with the new ID: 200.

**Never write a test asserting a specific hardcoded value or UUID shape for the session ID.** Session IDs must be opaque; formats can change across `WebSessionManager`/Spring Session versions.

### 16.2. Timeouts cannot be tested with long `Thread.sleep` in CI

`server.reactive.session.timeout` controls `WebSession` timeout. A real integration test can use an appropriate session store/clock or a short test timeout configuration, and should:
- Verify expired sessions are rejected.
- Verify cleanup of session and CSRF token.
- Verify re-login issues a new session.
- Never sleep the test suite for tens of minutes.
- Never infer expiry from cookie `max-age`: server-side expiry is a separate layer.

### 16.3. Multi-instance and Spring Session

Default Spring WebFlux may use a single-instance in-memory session store; when scaling:
- Pod A handles login, Pod B handles `GET /me`.
- If sessions are not shared, Pod B cannot find the session ID -> redirects to login.
- Sticky sessions are an operational strategy with failover weaknesses.
- Spring Session supports `WebSession` with `ReactiveSessionRepository` and Redis to share state per policy.
- Tests must go through the Gateway/LB across multiple pods and simulate failover.
- Redis TTL, serialization, cleanup, security, network ACLs, and namespace isolation all matter.

**The `SESSION` cookie is a lookup handle**, not an offline-verifiable copy of the entire Authentication.

## 17. Browsers, SameSite, Secure, CORS, and reverse proxies

### 17.1. Secure cookies in production

The local project runs on `http://localhost:8080`, so `Secure` is not forced. Production must serve HTTPS and set:

~~~yaml
server:
  reactive:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

Verify `Set-Cookie` over the public HTTPS hostname. Behind TLS termination at a proxy, forwarded headers and Spring Boot configuration can affect scheme detection; test in reality instead of assuming every proxy rewrites cookies safely.

### 17.2. SameSite does not replace CSRF

`SameSite=Lax` reduces many cross-site cookie transmissions but does not block every CSRF scenario (same-site subdomains, state-changing GET bugs, browser quirks, and cross-site flows). Form POST `/login`, `/logout`, and state-changing actions still need tokens per threat model.

If SSO or embedded apps require `SameSite=None`, `Secure` and third-party cookie policies are normally required; never disable CSRF just because cookies travel cross-site.

### 17.3. CORS is not authentication

CORS governs browser cross-origin reads/requests and does not stop `curl` or server-to-server calls. For WebFlux form login:
- Avoid wildcard CORS with credentials.
- Define allowed origins explicitly.
- Allow credentials only for trusted origins.
- Test preflight/actual requests with `SESSION` and CSRF.
- Never expose `GET /csrf` via broad CORS.
- Check `Origin`/`Referer` as an additional control where appropriate.

### 17.4. Browser logout may require front-end state cleanup

After logout, redirecting to the login page does not automatically purge all UI caches, service workers, or local storage. Use appropriate `Cache-Control` headers for sensitive content, avoid caching sensitive API responses in shared caches, and consider `Clear-Site-Data` where suitable—without treating it as a substitute for server session invalidation.

## 18. Troubleshooting by HTTP response

### `GET /me` always redirects even though `POST /login` reports success

Check:
1. Did `POST /login` actually carry a valid CSRF token?
2. Did the login response include a new `Set-Cookie: SESSION`?
3. Did the client send the **latest cookie ID** on `GET /me`?
4. Do cookie Path/Domain/SameSite/Secure prevent the browser from resending it?
5. Did a proxy strip `Set-Cookie` or `Cookie`?
6. Does the app configure `NoOpServerSecurityContextRepository` instead of a session repo?
7. Did the login authentication manager save `SecurityContext` successfully?
8. Was the session store reset, expired by TTL, or unshared across pods?
9. Did the login success handler redirect to a different URL/host causing the client to drop the cookie?
10. Did `GET /me` match the expected `SecurityWebFilterChain` and scope/role rule?

Do not assume credentials are wrong solely because of a post-login redirect.

### `POST /login` returns 403

Check the `SESSION` cookie, `_csrf` or `X-CSRF-TOKEN` token, form `Content-Type`, whether the token was refreshed after login/logout, whether the session ID rotated, and whether CSP/browser caching interfered with the hidden input. A 403 before password verification differs from a failure redirect caused by a wrong password.

### `POST /logout` returns 403

Check that a fresh CSRF token tied to the current `WebSession` was fetched and sent in the right header/parameter. With default CSRF, `POST /logout` without a token **must be blocked**. Never enable GET logout just to make tests easier.

### `POST /logout` redirects yet `GET /me` with the old cookie still returns 200

This is a critical violation of the logout contract:
- Did the logout handler actually invalidate `WebSession`?
- Does `SecurityContextServerLogoutHandler` target the right repository?
- Does the session store have shared-cache/replica consistency lag?
- Did the post-logout GET carry a different cookie?
- Is a proxy misapplying session affinity or client caching?
- Is remember-me, Bearer auth, Basic, or separate gateway auth silently re-authenticating?
- Did the test actually send the **old `SESSION`** without `mockUser` interfering?
- Is the client sending another `Authorization` header alongside `SESSION`?

Never mark logout PASS until the old-session check passes.

### `WebTestClient` tests PASS yet browsers cannot log in

The mock server may not simulate TLS, cookie Secure/Domain/SameSite flags, reverse proxies, browser CSRF form generation, or cross-origin restrictions. Run E2E tests in a production-like environment, inspecting `Set-Cookie`/`Cookie` in developer tools and gateway headers **without logging raw tokens**.

## 19. Security and coverage checklist

### Form login and credentials
- [ ] Anonymous protected requests go to the login entry point, not 200.
- [ ] `GET /login` renders the form and CSRF hidden input in the real UI.
- [ ] `POST /login` missing/invalid CSRF is rejected.
- [ ] `POST /login` uses `application/x-www-form-urlencoded`, not arbitrary JSON unless a custom filter is built.
- [ ] `PasswordEncoder` is never `noop` for production credentials.
- [ ] Login with wrong username/password never creates an authenticated session.
- [ ] Login success is verified by a protected GET on a **subsequent** request.
- [ ] Different roles yield 403/200 per policy.
- [ ] Never log passwords, CSRF tokens, or session IDs in CI logs.

### Sessions and cookies
- [ ] Test `Set-Cookie: SESSION` from real responses.
- [ ] Test that the cookie is resent in a follow-up HTTP request.
- [ ] Test that missing cookies and forged cookies remain unauthenticated.
- [ ] Session ID rotation/fixation behavior is tested per repository/version.
- [ ] Session TTL/idle timeout and expiry are tested without flakiness.
- [ ] `HttpOnly`, `Secure`, `SameSite`, `Domain`, `Path`, and `HSTS` are verified over HTTPS.
- [ ] Session store preserves state across pods and failover if required by contract.
- [ ] `SESSION` cookie is never mistaken for a JWT or role carrier.
- [ ] Never trust a client-supplied `SESSION` value not found in the server store.

### CSRF
- [ ] `GET /csrf/token` bootstraps same-origin and is uncached.
- [ ] Spring 6.x masked CSRF token is sent verbatim via header/form.
- [ ] Token is bound to its `SESSION`; tokens from other sessions are rejected.
- [ ] `POST /notes`, `/login`, and `/logout` require CSRF tokens.
- [ ] Never disable CSRF app-wide when using session cookies.
- [ ] `mockUser() + csrf()` tests are classified strictly as policy tests, not session-flow tests.

### Logout
- [ ] `GET /logout` does not log the user out.
- [ ] `POST /logout` missing CSRF returns 403 and keeps the session alive.
- [ ] Valid `POST /logout` uses `ServerLogoutHandler` on the right repository.
- [ ] `WebSession` is invalidated per contract if logout must terminate the entire session.
- [ ] Protected GET with the **old session ID** after logout is no longer authenticated.
- [ ] Global SSO/remember-me/refresh-token logout has a dedicated plan.
- [ ] Logout idempotency, replay, and race conditions are considered in practice.

### Gateway and operations
- [ ] HTTPS; proxies do not strip `Cookie`/`Set-Cookie`.
- [ ] CORS with credentials is allowed only for trusted origins.
- [ ] WebFlux Reactive config only; no Servlet `HttpSession` APIs copied over.
- [ ] Spring Session/Redis TTL, encryption, and access policies configured if scaling horizontally.
- [ ] Monitoring tracks aggregate login failures, logout outcomes, and CSRF 403s without logging secrets.
- [ ] E2E browser/Gateway tests cover cookie flags, session fixation, and logout persistence.
- [ ] Tests cover session timeout and multi-pod read-after-login.

## 20. Review questions

**1. Can `@WithMockUser` test `POST /login` with a real password?**

> No. It creates a mock `Authentication` for testing authorization and does not execute the real form/password/session flow.

**2. Why might anonymous `GET /me` return 302 instead of 401?**

> Form login uses a browser redirect-to-login entry point rather than a Bearer API entry point.

**3. Does the `SESSION` cookie contain username and roles in JWT format?**

> Not in default `WebSession`. The cookie holds an opaque session ID; the server uses it to look up `SecurityContext`.

**4. When should you capture the session cookie?**

> From the response `Set-Cookie`, updating it whenever login/session ID rotation occurs; use the latest cookie on the next request.

**5. Why can a `SESSION` cookie exist before login while still anonymous?**

> An anonymous `WebSession` may be created to store the CSRF token, with no authenticated principal.

**6. Why does `POST /login` need CSRF?**

> Login CSRF can force a browser to log into an attacker-controlled account; Spring Security protects login requests by default.

**7. Can a CSRF token be used with a different session?**

> No. The expected token lives in the corresponding `WebSession`; a session mismatch must be rejected.

**8. Why can the `GET /csrf` token change across renders even when the session has not changed?**

> Spring Security 6.x applies XOR/masking to mitigate BREACH; do not rely on comparing raw masked tokens across requests.

**9. Should `POST /logout` without CSRF be allowed to log out?**

> No, under default form/session CSRF. It must return 403 and keep the current session active.

**10. Should `GET /logout` actually perform logout?**

> Not under secure defaults; GET is for the confirmation page, while logout action uses POST.

**11. Does a 302 from logout prove the session was invalidated?**

> No. You must send `GET /me` with the old cookie and confirm it is no longer authenticated.

**12. What is `WebSessionServerLogoutHandler` used for?**

> To invalidate the active `WebSession`, complementing clearing `SecurityContext` during logout.

**13. Why not use `NoOpServerSecurityContextRepository` for form session login?**

> It does not persist `Authentication` across requests, so login would not carry over to the next GET.

**14. Do `HttpOnly`/`SameSite` cookies replace CSRF tokens?**

> No. They mitigate specific risks but do not replace full CSRF protection.

**15. What HTTP body format does form login use by default?**

> `application/x-www-form-urlencoded` with username/password, plus CSRF via form parameter or header.

**16. Why do `curl` tests need both `-c` and `-b`?**

> `-c` writes updated `Set-Cookie` values and `-b` sends saved cookies on the next request, handling potential session ID rotation.

**17. How should session timeouts be tested?**

> Use an appropriate test timeout/store configuration and verify expiry rather than `Thread.sleep` for tens of minutes in CI.

**18. Does `WebTestClient` mock server replace browser/Gateway E2E tests?**

> No. It tests WebFlux filters and session flow, but lacks full TLS, proxy cookie rewriting, browser `SameSite`, and multi-pod Redis.

## 21. Summary

Testing form login in Spring Security WebFlux must follow the **exact stateful HTTP sequence**:

~~~text
GET /csrf (+ Set-Cookie SESSION)
 -> POST /login (form username/password + SESSION + CSRF)
 -> 302 success (+ new SESSION if rotated)
 -> GET /me (current SESSION) = 200, right principal
 -> POST /notes (SESSION + fresh CSRF) = 200
 -> POST /logout (SESSION + fresh CSRF)
 -> GET /me (OLD SESSION) = login redirect
~~~

Three principles:
1. **Do not confuse mock authorization with real login.** Use `mockUser()`/`csrf()` for request-level tests; use a cookie jar and real CSRF tokens to prove login/session/logout.
2. **Verify post-response state.** Login 302 is not enough; `GET` protected in a new request must succeed. Logout 302 is not enough; the old session cookie must fail.
3. **Protect the session lifecycle and CSRF.** Never disable CSRF to fix a test; verify cookie flags, session fixation, logout invalidation, distributed sessions, and Gateway E2E before production.

The Java 17/Spring Boot 3.5 sample project provides **20 HTTP session-flow tests + 4 mock policy tests**, along with runnable-structured code and Gradle/curl commands. Build/test results are confirmed only after running in a suitable environment; do not treat expected descriptions as executed build logs.

### Official references

- Spring Security 6.5 — WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 — Getting Started WebFlux (login/logout): https://docs.spring.io/spring-security/reference/6.5/reactive/getting-started.html
- Spring Security 6.5 — Reactive Logout: https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/logout.html
- Spring Security 6.5 — Reactive CSRF: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security 6.5 — WebTestClient Security Setup: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html
- Spring Security 6.5 — WebFlux Testing Authentication: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security 6.5 — WebFlux Testing with CSRF: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html
- Spring Security API — WebSessionServerSecurityContextRepository: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html
- Spring Security API — Reactive Logout Handlers: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/logout/package-summary.html
- Spring Boot 3.5 — `server.reactive.session` properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Spring Session — Reactive WebSession Integration: https://docs.spring.io/spring-session/reference/web-session.html
- Spring Session — WebFlux CookieWebSessionIdResolver: https://docs.spring.io/spring-session/reference/configuration/common.html
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP — Cross-Site Request Forgery Prevention: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html