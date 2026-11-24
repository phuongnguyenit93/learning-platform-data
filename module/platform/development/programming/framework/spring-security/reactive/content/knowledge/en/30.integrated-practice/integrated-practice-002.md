# Integrated Practice: Building a WebFlux Application with Form Login, Sessions, CSRF, and Logout

## 1. Objectives, Scope, and Deliverables

This hands-on lab builds a **Spring Boot + Spring WebFlux + Spring Security** application where users sign in via an **HTML form**, maintain authentication state across requests with **`WebSession`**, perform a **CSRF-protected POST** operation, and **log out via POST**. The focus is on understanding the security flow and verifying actual behavior, not just toggling a few configuration options.

Once completed, the application supports the following capabilities:

1. Anonymous visitors can view the home page `GET /` and the custom login page `GET /login`.
2. Users submit `username`, `password`, and a CSRF token in the `POST /login` form. **Spring Security handles `POST /login`**, so you do not need to write a controller to verify passwords manually.
3. Upon successful login, the `SecurityContext` is persisted in `WebSession`. Subsequent requests use the session cookie to continue accessing `GET /dashboard`.
4. Users change a demo theme preference via `POST /preferences`. Requests without a valid CSRF token must be blocked without modifying data.
5. Users submit the `POST /logout` form with a CSRF token. Logout clears the security context, and the application is configured to **invalidate the entire `WebSession`**. Afterward, accessing protected pages requires signing in again.

**Technologies used in this example:** Java 17+ (demonstrated with JDK 21), Spring Boot 3.3.x, Spring Security 6.x, Gradle, WebFlux, and Reactor. The code uses a controller returning HTML directly so the CSRF mechanism is clearly visible; larger applications can use reactive Thymeleaf instead. Do not apply Servlet APIs such as `HttpSecurity`, `SecurityFilterChain`, `HttpSession`, `HttpServletRequest`, or `ThreadLocal`-based `SecurityContextHolder` from Spring MVC examples.

## 2. Execution Flow and Core Concepts

```text
Unauthenticated browser
    |
    | GET /dashboard
    v
SecurityWebFilterChain -> no Authentication yet
    |
    | Redirect to /login
    v
GET /login -> server generates/issues CsrfToken; WebSession binds token
    |
    | Form POST /login:
    | username + password + _csrf
    v
CsrfWebFilter validates token
    |
    v
AuthenticationWebFilter verifies credentials
    |
    +-- Invalid --> return to login page with error notice
    |
    +-- Valid --> SecurityContext stored in WebSession
                    |
                    | Session cookie accompanies subsequent requests
                    v
                GET /dashboard (authenticated)
                    |
                    +--> POST /preferences + CSRF: update demo state
                    |
                    +--> POST /logout + CSRF:
                             clear SecurityContext + invalidate WebSession
                             |
                             v
                         Return to login; previous access is gone
```

**Distinguishing the components:**

| Component | Role in the example |
| --- | --- |
| `SecurityWebFilterChain` / `ServerHttpSecurity` | Decides which routes are public, which require roles, and enables form login/CSRF/logout |
| `MapReactiveUserDetailsService` | Demo account source; replace with a repository/user service in production |
| `PasswordEncoder` (`BCryptPasswordEncoder`) | Compares passwords against hashes during authentication; never use `{noop}` in production |
| `WebSession` | Server-side session storing `SecurityContext`, CSRF token, and demo theme preference |
| Session cookie | Holds the session identifier so the browser can look up server state; the cookie itself is not a CSRF token |
| `WebSessionServerCsrfTokenRepository` | Default mechanism storing the expected CSRF token in `WebSession` |
| `CsrfWebFilter` | Verifies the token on state-changing requests; typically required for POST |
| `LogoutWebFilter` | Receives POST logout requests and delegates to `ServerLogoutHandler` |
| `WebSessionServerLogoutHandler` | Invalidates the entire `WebSession` when added to logout configuration |

Why does CSRF still matter even when the session cookie is `HttpOnly`? Browsers **automatically send cookies** according to cookie rules on same-site requests or certain cross-site navigations. A malicious page can attempt to trigger a POST action using the user's session; requiring a CSRF token that another site cannot read directly blocks that attack. `SameSite` reduces risk but does not fully replace protection on critical forms.

## 3. Initializing the Gradle Project

You can generate a Spring Boot Gradle project with Spring Initializr using the **Spring Reactive Web** and **Spring Security** dependencies. If creating an empty project manually, match this structure:

```text
webflux-form-session-demo/
├── settings.gradle
├── build.gradle
├── gradlew                 # if Gradle Wrapper has been generated
├── gradlew.bat             # if Gradle Wrapper has been generated
└── src/main/java/demo/
    └── WebfluxFormSessionApplication.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'webflux-form-session-demo'
```

**`build.gradle` (Gradle Groovy DSL):**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
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

If an existing project already uses Spring Boot 3.3.x, keep the plugin/Gradle versions managed by the project and add only the required starters; do not inject custom plugin/dependency versions into a multi-module build that already has dependency management. The sample above uses JDK 21; the core APIs work on Java 17+ with the toolchain adjusted accordingly.

**Demo password:** the application requires the `DEMO_PASSWORD` environment variable at startup, encodes it with BCrypt, and then creates the `learner` account. Do not hardcode real passwords or shared hashes across systems in source control. Use sample accounts strictly for local learning.

## 4. Complete Java Application

Place all of the code below into **`src/main/java/demo/WebfluxFormSessionApplication.java`**. This is a self-contained Java file with `main`, security configuration, a demo user, and an HTML controller. No templates or JavaScript are needed.

```java
package demo;

import java.security.Principal;
import java.util.Set;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.util.HtmlUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebSession;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class WebfluxFormSessionApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebfluxFormSessionApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        String password = System.getenv("DEMO_PASSWORD");
        if (password == null || password.isBlank()) {
            throw new IllegalStateException(
                    "Set DEMO_PASSWORD before running the local demo");
        }
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode(password))
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(learner);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        var logoutHandlers = new DelegatingServerLogoutHandler(
                new SecurityContextServerLogoutHandler(),
                new WebSessionServerLogoutHandler());

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/", "/login").permitAll()
                        .pathMatchers(HttpMethod.GET, "/dashboard")
                        .hasRole("USER")
                        .pathMatchers(HttpMethod.POST, "/preferences")
                        .hasRole("USER")
                        .anyExchange().denyAll())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.loginPage("/login"))
                .csrf(Customizer.withDefaults())
                .logout(logout -> logout.logoutHandler(logoutHandlers))
                .build();
    }

    @RestController
    static class Pages {

        @GetMapping(value = "/", produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> home() {
            return Mono.just("""
                    <!doctype html>
                    <html lang="en"><head><meta charset="UTF-8">
                    <title>Home</title></head><body>
                      <h1>WebFlux Security Demo</h1>
                      <p><a href="/dashboard">Open dashboard</a></p>
                      <p><a href="/login">Sign in</a></p>
                    </body></html>
                    """);
        }

        @GetMapping(value = "/login",
                produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> loginPage(ServerWebExchange exchange) {
            return csrf(exchange).map(token -> """
                    <!doctype html>
                    <html lang="en"><head><meta charset="UTF-8">
                    <title>Sign in</title></head><body>
                      <h1>Sign in</h1>
                      <form method="post" action="/login">
                        <label>Username
                          <input name="username" autocomplete="username"
                                 required>
                        </label>
                        <label>Password
                          <input type="password" name="password"
                                 autocomplete="current-password" required>
                        </label>
                        %s
                        <button type="submit">Sign in</button>
                      </form>
                      <p><a href="/">Back to home</a></p>
                    </body></html>
                    """.formatted(hiddenCsrf(token)));
        }

        @GetMapping(value = "/dashboard",
                produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> dashboard(ServerWebExchange exchange) {
            Mono<Principal> currentUser = exchange.getPrincipal();
            return Mono.zip(currentUser, csrf(exchange),
                    exchange.getSession()).map(values -> {
                String user = HtmlUtils.htmlEscape(
                        values.getT1().getName());
                CsrfToken token = values.getT2();
                WebSession session = values.getT3();
                String preference = session.getAttributeOrDefault(
                        "theme", "light");
                String hidden = hiddenCsrf(token);

                return """
                        <!doctype html>
                        <html lang="en"><head><meta charset="UTF-8">
                        <title>Dashboard</title></head><body>
                          <h1>Dashboard</h1>
                          <p>Signed in as: %s</p>
                          <p>Session theme: %s</p>
                          <form method="post" action="/preferences">
                            <label>Choose theme
                              <select name="theme">
                                <option value="light">light</option>
                                <option value="dark">dark</option>
                              </select>
                            </label>
                            %s
                            <button type="submit">Save</button>
                          </form>
                          <form method="post" action="/logout">
                            %s
                            <button type="submit">Sign out</button>
                          </form>
                        </body></html>
                        """.formatted(user,
                        HtmlUtils.htmlEscape(preference),
                        hidden, hidden);
            });
        }

        @PostMapping(value = "/preferences",
                produces = MediaType.TEXT_PLAIN_VALUE)
        Mono<String> savePreference(ServerWebExchange exchange) {
            return exchange.getFormData().flatMap(form -> {
                String theme = form.getFirst("theme");
                if (theme == null || !Set.of("light", "dark").contains(theme)) {
                    return Mono.error(new ResponseStatusException(
                            HttpStatus.BAD_REQUEST, "Invalid theme"));
                }
                return exchange.getSession().map(session -> {
                    session.getAttributes().put("theme", theme);
                    return "Saved theme: " + theme;
                });
            });
        }

        private static Mono<CsrfToken> csrf(
                ServerWebExchange exchange) {
            Mono<CsrfToken> token = exchange.getAttribute(
                    CsrfToken.class.getName());
            if (token == null) {
                return Mono.error(new IllegalStateException(
                        "CSRF request attribute unavailable"));
            }
            return token;
        }

        private static String hiddenCsrf(CsrfToken token) {
            return "<input type=\"hidden\" name=\""
                    + HtmlUtils.htmlEscape(token.getParameterName())
                    + "\" value=\""
                    + HtmlUtils.htmlEscape(token.getToken()) + "\">";
        }
    }
}
```

**Explanation of key decisions:**

- `formLogin(form -> form.loginPage("/login"))` uses the custom HTML page. POST requests to `/login` are still processed by the **Spring Security filter**, using `username`/`password` from the form. Do not create a `@PostMapping("/login")` with custom authentication logic.
- `/login` and `/` are public; `GET /dashboard` and `POST /preferences` require `ROLE_USER`; undefined routes are blocked by `denyAll()`. Even though `/login` is `permitAll`, CSRF still checks the POST before processing it.
- `httpBasic(basic -> basic.disable())` keeps the exercise focused on form login, preventing browsers/clients from authenticating with Basic and skipping session observation.
- `csrf(Customizer.withDefaults())` protects write requests; Spring Security WebFlux enables CSRF by default, but declaring it explicitly helps learners see the configuration boundary.
- `CsrfToken.class.getName()` is the attribute name under which `CsrfWebFilter` places a `Mono<CsrfToken>` on `ServerWebExchange`. `csrf(exchange)` returns a `Mono`, and HTML rendering **subscribes** indirectly when Spring WebFlux writes the response. Never call `.block()` on the event loop.
- `hiddenCsrf(token)` outputs `<input type="hidden" name="_csrf" value="...">` with the real field name and value provided by the framework; the default field name is `_csrf`. Do not generate a random string to mimic a CSRF token.
- `HtmlUtils.htmlEscape` protects data embedded into HTML, including the username and input attribute values. Never place tokens in URLs/query strings or logs.
- `savePreference` reads the `application/x-www-form-urlencoded` body via `exchange.getFormData()`. In **WebFlux**, do not assume `@RequestParam` always reads form bodies in the same way as Spring MVC. Only `light`/`dark` are accepted. The value is stored in the current `WebSession`; this demonstrates **in-session state**, not long-term preference persistence in a database.
- `logoutHandlers` combines `SecurityContextServerLogoutHandler` and `WebSessionServerLogoutHandler`. Reactive logout by default clears the context/CSRF and redirects, but **do not assume it automatically invalidates the entire `WebSession`**: here we **explicitly add the session-invalidation handler**. Session-stored state such as `theme` is therefore also lost on logout.
- `@RestController` returns an HTML body directly so the example stays in a single Java file. In production apps with larger UIs, Thymeleaf with `th:action` forms can insert CSRF tokens automatically when properly configured; controllers do not need to concatenate HTML strings manually.

**Important distinction:** for real software, the `DEMO_PASSWORD` variable is merely a way to pass a demo password into the process. Accounts should reside in a proper identity store; password hashes must be managed and stored per policy, with login rate limiting and MFA as needed.

## 5. Running the Application

If you created the project with Spring Initializr, use the included Gradle Wrapper. If you only created the Gradle files manually, install a compatible Gradle version or generate the Wrapper with `gradle wrapper` first.

On Linux/macOS (Bash):

```bash
export DEMO_PASSWORD='OnlyForLocalPractice!'
./gradlew bootRun
```

On Windows PowerShell:

```powershell
$env:DEMO_PASSWORD = 'OnlyForLocalPractice!'
.\gradlew.bat bootRun
```

If using a pre-installed Gradle instead of the Wrapper, the command is `gradle bootRun`. The password above is for local testing only—do not copy it to staging/production. Once startup succeeds, open `http://localhost:8080/` in a browser.

### 5.1 Successful Login Scenario

1. Open `/dashboard` in a private/incognito window with no session cookie. The security chain detects no authentication and redirects to login (typically HTTP 302 to `/login`).
2. `GET /login` renders the form containing `username`, `password`, and a hidden CSRF field. In DevTools → Elements/Network, verify the hidden field exists, but **do not copy the token value into logs or documentation**.
3. Enter username `learner` and the password matching `DEMO_PASSWORD` set in the runtime environment. The form submits `POST /login` without needing a login POST controller.
4. On successful authentication, Spring Security redirects back to the saved request or the default target depending on the flow; navigate to `/dashboard` to observe the signed-in username.
5. Refresh `/dashboard`: you are not prompted for a password again because `SecurityContext` is restored via `WebSession` using the browser's cookie.

**Expected result:** form login works, the browser holds a session cookie (typically named `SESSION` by default in WebFlux), `/dashboard` returns HTML containing `Signed in as: learner`, and refreshing preserves state. Actual cookie/session IDs are generated dynamically, so **there is no fixed stdout or ID** to copy into notes.

### 5.2 Testing an Action Protected by CSRF

After logging in, choose `dark` on the dashboard and click **Save**. The browser sends:

```http
POST /preferences
Content-Type: application/x-www-form-urlencoded
Cookie: SESSION=(server-issued session identifier)

theme=dark&_csrf=(token bound to session)
```

This is an **illustrative HTTP structure**, not a request with a runnable token to replay verbatim. The response body in the example when valid is:

```text
Saved theme: dark
```

Reopen `/dashboard`, and the session theme line displays `dark`. If you delete/alter the hidden `_csrf` input in the form or send a direct POST without the token, `CsrfWebFilter` must reject the action (typically `403 Forbidden`), and the value in the session **does not change**.

To quickly verify that the endpoint rejects an anonymous POST without a token:

```bash
curl -i -X POST http://localhost:8080/preferences \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data 'theme=dark'
```

The command sends neither a cookie nor a CSRF token, so it cannot modify the session. Status 403 is the typical result when the CSRF filter rejects a request, though filter/handler ordering and application customizations can yield another status; the invariant to verify is **no update occurs**. When testing a POST missing CSRF **inside an authenticated session**, edit the request in DevTools or use an HTTP tool that keeps the cookie while omitting only the token.

### 5.3 Logging Out and Verifying Session Invalidation

On the dashboard, click **Sign out**. The browser sends **`POST /logout`** with CSRF. Spring Security processes it using the logout filter and both configured handlers. After the redirect, try reopening `/dashboard`: the protected page must require signing in again, and the `theme` preference from the previous session must no longer remain active.

Additional checks:

- Visiting `GET /logout` **must not be assumed to behave the same as POST logout**. In WebFlux, logout uses POST so it is CSRF-protected; a GET confirmation page may exist depending on configuration.
- A POST logout **missing or with an invalid CSRF token** must be blocked; it must not invalidate the session like a valid logout.
- Sending the old session cookie after logout must not grant access to `/dashboard` with the previous privileges.
- When signing in again with a new valid session, check that the demo state has reset to `light` (assuming no other state is stored outside `WebSession`).

**Never post real session IDs, passwords, or CSRF tokens into tickets/logs.** If taking DevTools screenshots for QA reports, redact cookie/credential/token values.

## 6. Why Both Sessions and CSRF Are Needed

### 6.1 Sessions: Server Stores SecurityContext, Browser Holds Identifier

In form login, the browser receives a session identifier cookie; the server associates `SecurityContext` with `WebSession`. When the browser sends that cookie on a later request, the framework loads the security context and evaluates `SecurityWebFilterChain` rules. Precisely because the browser attaches cookies automatically, state-changing forms require CSRF protection.

Independent states to understand:

- **Unauthenticated:** no trusted `Authentication` exists; `/dashboard` redirects to login.
- **Authenticated:** `SecurityContext` is stored in `WebSession` and the user has `ROLE_USER`.
- **Session expired:** session data expires according to the configured idle timeout; the browser must sign in again.
- **Logged out:** the security context is cleared and **`WebSession` is invalidated by the added handler**.
- **CSRF rejected:** a state-changing request missing or having an invalid token is blocked **even though the cookie is still valid** and the user is logged in.

A CSRF token is bound to the active session, yet it is **not a password** and not a bearer token used to authenticate identity. It proves that the form submission knows a token that cross-origin sites cannot obtain. The `SESSION` cookie alone does not replace the `_csrf` token.

### 6.2 How WebSession Differs from HttpSession

| Spring WebFlux / Reactive | Spring MVC / Servlet |
| --- | --- |
| `ServerHttpSecurity` | `HttpSecurity` |
| `SecurityWebFilterChain` | `SecurityFilterChain` |
| `ServerWebExchange` | `HttpServletRequest` |
| `WebSession` | `HttpSession` |
| `WebSessionServerCsrfTokenRepository` | `HttpSessionCsrfTokenRepository` |
| `SecurityContextServerLogoutHandler` | `SecurityContextLogoutHandler` |
| `WebSessionServerLogoutHandler` | `HttpSession.invalidate()` / servlet logout mechanism |

Do not bring Servlet instructions such as `SessionCreationPolicy.STATELESS`, `HttpServletRequest#getSession()`, `HttpSecurity.csrf()`, or `HttpSessionCsrfTokenRepository` into reactive examples. If an application uses stateless JWT/Bearer tokens, the mechanism and need for CSRF must be evaluated based on how the browser sends credentials; **this lab intentionally uses session-cookie-based form login**.

### 6.3 How the CSRF Token Is Issued and Verified

In Spring Security WebFlux, the expected token is stored in `WebSession` by the default repository. `CsrfWebFilter` places a `Mono<CsrfToken>` into a `ServerWebExchange` attribute; the controller renders it as a hidden input in POST forms. When the browser submits, the framework reads the `_csrf` form field and compares it against the expected token.

Diagram:

```text
GET /login or GET /dashboard
  server creates/loads CSRF token from WebSession
  renders hidden _csrf input

POST /login, /preferences, /logout
  browser sends session Cookie (automatically)
  browser sends _csrf (from the form)
  CSRF filter compares against expected token
    +-- Match: allows remaining security filters to proceed
    +-- Missing/invalid: rejects POST before business logic
```

CSRF matters for **login** (preventing login CSRF), **state changes**, and **logout** (preventing logout CSRF). Never disable CSRF application-wide with `.csrf(csrf -> csrf.disable())` just to “make a form work.” If a frontend uses AJAX/JSON, send the token via an appropriate header (such as `X-CSRF-TOKEN`) or integrate a token repository/handler designed for SPAs; for URL-encoded forms, a hidden input is the simplest approach.

### 6.4 Post-Login Redirects, Route Protection, and Status Codes

| Request | When unauthenticated | After login with role USER |
| --- | --- | --- |
| `GET /` | 200, public | 200, public |
| `GET /login` | 200, HTML form | App-dependent; controller remains public |
| `GET /dashboard` | Usually 302 to login | 200, dashboard HTML |
| `POST /preferences` + valid CSRF | Unauthorized, blocked/redirected to login | 200, updates theme |
| `POST /preferences` missing/invalid CSRF | Not updated | Usually 403; not updated |
| `POST /logout` + valid CSRF | Do not assume business access | Clears context and invalidates `WebSession`, redirects to login |
| `POST /logout` missing CSRF | Not treated as valid logout | Usually 403, session remains active |
| Undeclared route | Denied by `denyAll` | Still denied by `denyAll` |

Exact HTTP status codes depend on version, entry point, and custom error handlers. When seeing 403, distinguish **CSRF invalid** from **authorization denied** using logs and request tracing rather than guessing from the HTTP code alone.

## 7. Adding Automated Tests (Optional)

Testing with a browser is the best way to observe forms and cookies. In CI, you can use `WebTestClient` with Spring Security test support (`spring-security-test`) to write tests for:

- Public routes return 200; anonymous requests to dashboard redirect.
- Users with `ROLE_USER` can access the dashboard.
- Authenticated POST preferences without CSRF returns 403; session remains unchanged.
- POST preferences with a valid token updates state.
- POST logout with a valid token revokes access when reusing the old cookie.
- POST login with a wrong password does not establish an authenticated `SecurityContext`.
- After session idle timeout, protected requests require re-authentication.

When using security test mutators like `mockUser()` or `csrf()`, remember these are **test mechanisms that pre-populate context/tokens** and do not prove the browser sends cookies and forms properly in real integration. Include at least one end-to-end test that performs a real POST login through the form page, maintains a cookie jar, sends POST logout, and verifies the old session no longer has access. Never treat a test asserting only status 200 as sufficient: prove that tokenless requests cause no side effects.

A manual test script can be written as acceptance criteria:

```text
Given a clean browser and a valid learner account
When GET /dashboard
Then redirect to login

When POST /login with valid username, password, and _csrf
Then authentication succeeds and /dashboard is displayed

When POST /preferences with theme=dark and valid _csrf
Then response body is "Saved theme: dark"
And GET /dashboard displays theme dark

When POST /preferences with missing or invalid _csrf
Then request is rejected
And theme in WebSession does not change

When POST /logout with valid _csrf
Then old session no longer has access to /dashboard
And the next visit prompts to sign in again
```

## 8. Production Deployment Considerations

1. **HTTPS and cookies:** only use session-cookie form login over HTTPS. Verify `Secure`, `HttpOnly`, `SameSite`, `Path`, domain, and expiry on real browsers/proxies. `SameSite=Lax` or `Strict` should be chosen according to actual login and cross-site flows; do not assume one cookie setting fits every environment.
2. **Session fixation:** ensure the session identifier is protected when transitioning from anonymous to authenticated according to the active policy/version; inspect IDs before and after login. Do not blindly apply **Servlet** session-fixation settings to WebFlux.
3. **Timeouts and multi-node:** configure an appropriate idle timeout. Default in-memory per-node sessions are unsuitable for multiple replicas without sticky sessions or a shared store; consider Spring Session Reactive with Redis or another supported store for load balancing and consistent session invalidation. `spring.session.timeout` is a Spring Session configuration property and should not be assumed to apply uniformly to every `WebSession` storage backend.
4. **Passwords and account management:** store salted adaptive hashes (BCrypt/Argon2/PBKDF2 per policy), never log passwords, enforce brute-force protection/rate limiting, and add MFA if needed; `MapReactiveUserDetailsService` is a small example, not a real user store.
5. **Authorization:** protect business endpoints with the right roles/authorities and resource ownership conditions rather than merely hiding links in the UI. `permitAll` is strictly for approved public routes.
6. **CSRF:** require protection on POST/PUT/PATCH/DELETE whenever browsers send credentials automatically, including login and logout. GET must have no side effects; never place tokens in URLs, shared links, or access logs.
7. **Logout:** clear `SecurityContext`, CSRF tokens, and the session per policy; do not write a custom `@PostMapping("/logout")` that bypasses logout handlers. With SSO/OIDC, also evaluate IdP logout if required.
8. **Session state:** do not store card numbers, passwords, JWTs, or large/non-serializable objects in the session. The `theme` example is illustrative only; durable data belongs in a database with proper design.
9. **CSP/XSS:** escape HTML output and apply an appropriate Content Security Policy; prevent XSS because malicious same-origin scripts can read CSRF tokens and perform requests on the user's behalf.
10. **Observability:** record counts of login success/failure, session expiration, CSRF denied, logout, and authorization denied (without raw tokens or cookies). Propagate correlation IDs in WebFlux to trace across the reactive pipeline.

## 9. Common Issues and Troubleshooting

| Symptom | Common cause | Where to check |
| --- | --- | --- |
| POST /login always returns 403 | Missing CSRF hidden input, CSRF token belongs to a different session, cookie not preserved | Inspect GET /login response for `_csrf`, confirm POST includes cookie + token |
| POST /login 302 to `/login?error` | Wrong username/password or mismatched `PasswordEncoder` configuration | Verify `DEMO_PASSWORD` in the server process and the BCrypt encoder |
| GET /dashboard always redirects to login | Browser not sending cookie, session expired, login failed, context not saved | Check cookie/session storage and authentication rules; do not rely on `ThreadLocal` |
| Preferences form does not update | CSRF rejected, missing USER role, wrong form field name, invalid theme value | Inspect POST request in DevTools; check status/body and verify GET /dashboard afterward |
| POST /logout returns 403 | Missing CSRF token or stale token from an older session | Re-render dashboard to get the current token; do not switch logout to GET |
| Clicking logout still allows access to dashboard | Context not cleared/invalidated, sending a different session's cookie, proxy caching | Verify logout filter and both logout handlers; disable caching on sensitive pages |
| `theme` state lost on restart | `WebSession` is in-memory, not a database | Expected demo behavior; use a managed shared store if persistence is required |
| Only works when CSRF is disabled | Form does not pass token or Servlet APIs used in WebFlux | Fix hidden input/handler; keep CSRF enabled |
| Broken HTML / XSS | Unescaped data inserted into HTML | Escape per context and use a standard template/view engine |
| Intermittent logins across multi-node | Session stored on one node, next request hits another | Use a shared session store or appropriate routing |

## 10. Self-Assessment Checklist

- [ ] Can compile and run the application on JDK 21 with WebFlux and Security dependencies.
- [ ] `GET /login` returns an HTML form with username, password, and a valid CSRF hidden input.
- [ ] `POST /login` is handled by Spring Security, comparing the password against a BCrypt hash.
- [ ] After successful login, `/dashboard` is accessible on subsequent requests via the session cookie.
- [ ] `POST /preferences` with valid CSRF updates state in `WebSession`.
- [ ] `POST /preferences` with missing/invalid CSRF is blocked and **does not change state**.
- [ ] `POST /logout` with valid CSRF clears `SecurityContext` and invalidates `WebSession`.
- [ ] After logout, the old cookie can no longer access protected resources.
- [ ] Unpublicized routes are denied, without opening permissions or disabling CSRF to “fix” errors.
- [ ] Production plans cover TLS, cookie flags, session timeout, session store, password policy, and logging.

## Official References

- Spring Security — WebFlux Security (`SecurityWebFilterChain` configuration, form login): https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Getting Started with WebFlux Applications: https://docs.spring.io/spring-security/reference/reactive/getting-started.html
- Spring Security — Cross Site Request Forgery in WebFlux (CSRF attribute, hidden input, login/logout): https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security — Reactive Logout (distinguishing clearing context and invalidating `WebSession`): https://docs.spring.io/spring-security/reference/reactive/authentication/logout.html
- Spring Security — WebFlux Authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Boot — Spring Session and timeout properties: https://docs.spring.io/spring-boot/3.3/reference/web/spring-session.html
- Spring Framework — WebFlux and `WebSession`: https://docs.spring.io/spring-framework/reference/web/webflux.html
