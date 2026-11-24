# Building Secure Form Login, Sessions, and Logout

## 1. Objectives of the Capstone Exercise

This exercise builds a **Spring Boot + Spring MVC + Spring Security (Servlet)** application with an HTML form login screen, HTTP session state persistence, CSRF protection on state-changing requests, session ID rotation after authentication, and proper logout. After completing this lesson, the reader should be able to explain **why a request is considered logged in**, **what cookies and sessions store**, and **how to verify that logout genuinely revokes access for the current session**.

Acceptance criteria:

1. Unauthenticated guests can view the public page but are redirected to the login page when opening a protected resource.
2. The `POST /login` form sends `username`, `password`, and a CSRF token; a valid password establishes an authenticated session, while a wrong password does not.
3. The session ID rotates upon successful authentication to reduce the risk of **session fixation**; subsequent requests are recognized via the session cookie.
4. The protected page displays the authenticated username retrieved from the `Authentication` provided by Spring Security.
5. The logout button sends **POST + CSRF token** to `/logout`, invalidates the session, and prevents further access to the protected page with the old session.
6. Automated tests cover successful/failed login, CSRF, anonymous access, session reuse, and logout.

The example is pinned to **Java 17, Spring Boot 3.5.0, Spring Security 6.5.x**, Maven, and Thymeleaf. These are specific versions for reproducibility; in real projects, keep up to date with supported Boot/Security patch releases. Spring Boot 4/Spring Security 7 have differences that require consulting migration guides. The exercise uses `InMemoryUserDetailsManager` and a demo password; the final sections explain what must replace them in real deployments.

## 2. Distinguishing Concepts Before Writing Code

| Concept | Role in this exercise | What not to confuse it with |
|---|---|---|
| **Authentication** | Result of identity verification; Spring Security places principal and authorities into `Authentication` | Not synonymous with session |
| **SecurityContext** | Holds the `Authentication` for the current request | Not a cookie interpreted directly by the browser |
| **HTTP session** | Server-side data tied to a session ID | Not a store for raw passwords |
| **`JSESSIONID`** | Standard cookie used by the browser to send the session ID back to the server | The cookie does not contain the raw `Authentication` or password |
| **CSRF token** | Value preventing forged requests when the browser automatically sends cookies | Does not replace password authentication or TLS |
| **Session fixation** | Attacker tricks the victim into logging in with an already-known session ID | Different from session hijacking / stealing a cookie |
| **Logout** | Revokes the authentication state of the current session and clears security context and related data | Simply redirecting to the login page is not enough |
| **Session timeout** | Session ceases to be valid after a configured period of inactivity | Does not guarantee the cookie disappears from every browser |
| **Authorization** | Decides whether an authenticated user has permission to access a resource | Authenticating successfully does not grant all permissions |

**Conceptual flow:**

```text
A. First access
Browser -> GET /dashboard
        -> SecurityFilterChain sees unauthenticated
        -> 302 /login
        -> GET /login -> render form and CSRF token

B. Login
Browser -> POST /login (username, password, _csrf)
        -> CsrfFilter validates token
        -> UsernamePasswordAuthenticationFilter
        -> AuthenticationManager / DaoAuthenticationProvider
        -> UserDetailsService + PasswordEncoder
        -> success: create Authentication, session fixation protection,
                    save SecurityContext into session, redirect
        -> failure: clear attempt context, redirect /login?error

C. Post-login request
Browser -> GET /dashboard + Cookie: JSESSIONID=...
        -> container looks up HTTP session
        -> Spring Security loads SecurityContext for request
        -> AuthorizationFilter allows
        -> Controller receives Authentication

D. Logout
Browser -> POST /logout + CSRF token + session cookie
        -> CsrfFilter verifies
        -> LogoutFilter invokes LogoutHandlers
        -> invalidate session + clear authentication/context + CSRF cleanup
        -> 302 /login?logout
        -> subsequent GET /dashboard must log in again
```

Two key points:

- **`POST /login` and `POST /logout` are handled by Spring Security filters**; you do not write custom `@PostMapping` handlers to compare passwords or call `session.invalidate()`. Our controller only renders `GET /login` and the pages.
- After login, the browser does not re-send username/password on every session-based request; it sends the session identifier cookie, and the server reads the stored authentication state. Therefore, protecting the cookie, preventing fixation, and expiring sessions are integral parts of authentication security.

## 3. Runnable Project Structure

```text
session-login-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/sessionlogin/
    │   │   ├── SessionLoginApplication.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── PagesController.java
    │   └── resources/
    │       ├── application.properties
    │       └── templates/
    │           ├── index.html
    │           ├── login.html
    │           └── dashboard.html
    └── test/java/com/example/sessionlogin/
        └── LoginSessionLogoutTest.java
```

### 3.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>session-login-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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
```

`spring-boot-starter-web` provides Spring MVC and the embedded Servlet container; `spring-boot-starter-security` provides the filter chain and authentication components; Thymeleaf renders HTML forms and integrates CSRF tokens; the two test dependencies support MockMvc and Spring Security test matchers/helpers.

### 3.2. `src/main/java/com/example/sessionlogin/SessionLoginApplication.java`

```java
package com.example.sessionlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionLoginApplication.class, args);
    }
}
```

### 3.3. `src/main/java/com/example/sessionlogin/SecurityConfiguration.java`

```java
package com.example.sessionlogin;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .loginPage("/login")
                .loginProcessingUrl("/login")
                .defaultSuccessUrl("/dashboard", false)
                .failureUrl("/login?error")
                .permitAll()
            )
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.changeSessionId())
            )
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
                .permitAll()
            )
            .csrf(withDefaults())
            .httpBasic(AbstractHttpConfigurer::disable)
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        var learner = User.withUsername("learner")
            .password(encoder.encode("lesson-password-123"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(learner);
    }
}
```

**Analyzing each configuration choice:**

- `authorizeHttpRequests` permits guests on the public page and login page; all other URLs require authentication. If `/admin` is added later, `hasRole("ADMIN")` or an explicit business policy must be added.
- `loginPage("/login")` tells Spring Security that **the application renders its own login page**. When replacing the default form, you must provide `GET /login` in a controller, and that endpoint must allow anonymous access; otherwise, a redirect loop easily occurs.
- `loginProcessingUrl("/login")` is the URL where `UsernamePasswordAuthenticationFilter` listens for HTTP POST. Do not add `@PostMapping("/login")` to process passwords yourself.
- `defaultSuccessUrl("/dashboard", false)` redirects to the dashboard when there is no saved target page; if the user was originally intercepted at a protected URL, Spring can redirect back to that original URL after login. The `false` argument preserves saved-request behavior; `true` always forces dashboard.
- `failureUrl("/login?error")` shows only a generic error; never reveal whether the account exists. This path is illustrative; production needs rate limiting and brute-force monitoring.
- `sessionFixation(...changeSessionId())` instructs the Servlet container to rotate the session ID upon successful authentication while keeping necessary session attributes. On modern Servlet containers this is already the default strategy; specifying it explicitly makes it visible for learning.
- `logout` uses the framework's filter to invalidate the session, clear `Authentication`, and redirect. `deleteCookies("JSESSIONID")` is an extra cookie cleanup step; **server-side logout effectiveness comes from session invalidation**, while cookie deletion depends on matching Path/Domain/container settings.
- `csrf(withDefaults())` **keeps CSRF enabled** for state-changing requests. This is essential for both login and logout when using cookies/sessions.
- `httpBasic(...disable)` keeps the demo strictly form-login-based; enabling Basic alongside it can cause API clients to receive different challenge behavior.
- `PasswordEncoderFactories.createDelegatingPasswordEncoder()` stores the demo password as a hash with an algorithm prefix such as `{bcrypt}...`. In production, user passwords must be created/changed securely and stored in a DB or IdP; never embed static demo passwords in code.
- Do not set `SessionCreationPolicy.STATELESS`: it contradicts the goal of **session-backed form login**.

### 3.4. `src/main/java/com/example/sessionlogin/PagesController.java`

```java
package com.example.sessionlogin;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PagesController {

    @GetMapping("/")
    String home() {
        return "index";
    }

    @GetMapping("/login")
    String login() {
        return "login";
    }

    @GetMapping("/dashboard")
    String dashboard(Authentication authentication, Model model) {
        model.addAttribute("username", authentication.getName());
        return "dashboard";
    }
}
```

The controller does not manually inspect cookies or passwords. Security filters already enforced that `/dashboard` requires authentication, so when the controller runs, `Authentication` holds an authenticated principal. The username is added to the model so Thymeleaf outputs it with `th:text` (HTML-escaped by default).

### 3.5. `src/main/resources/templates/index.html`

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Public Page</title>
</head>
<body>
    <h1>Public Page</h1>
    <p>Anyone can view this page.</p>
    <a th:href="@{/login}">Log in</a>
    <a th:href="@{/dashboard}">Go to dashboard</a>
</body>
</html>
```

### 3.6. `src/main/resources/templates/login.html`

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Log in</title>
</head>
<body>
    <h1>Log in</h1>

    <p th:if="${param.error}" role="alert">
        Invalid login credentials.
    </p>
    <p th:if="${param.logout}" role="status">
        You have been logged out.
    </p>

    <form th:action="@{/login}" method="post">
        <div>
            <label for="username">Username</label>
            <input id="username" type="text" name="username"
                   autocomplete="username" required>
        </div>
        <div>
            <label for="password">Password</label>
            <input id="password" type="password" name="password"
                   autocomplete="current-password" required>
        </div>
        <button type="submit">Log in</button>
    </form>
</body>
</html>
```

The form must submit `POST /login` with exact field names `username` and `password`. When using Thymeleaf with Spring Security, `th:action` on a POST form automatically injects the CSRF token as a hidden input in the rendered HTML, equivalent to:

```html
<!-- Illustrates the rendered markup only; the actual token changes -->
<input type="hidden" name="_csrf" value="a-real-token-generated-by-server">
```

**Never hardcode** a CSRF token value. Use DevTools → Elements/Network to inspect the token issued by the server; because CSRF is tied to the session and request, reusing a token from another window or from before session rotation is usually invalid. If building a pure JavaScript UI, you need a mechanism to read/send the corresponding token and account for token refresh after authentication/logout.

### 3.7. `src/main/resources/templates/dashboard.html`

```html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Dashboard</title>
</head>
<body>
    <h1>Authenticated Dashboard</h1>
    <p>Hello, <strong th:text="${username}">user</strong>.</p>

    <form th:action="@{/logout}" method="post">
        <button type="submit">Log out</button>
    </form>
</body>
</html>
```

**Why a form instead of `<a href="/logout">`?** With CSRF enabled, Spring Security requires a POST request with a CSRF token to perform logout; `GET /logout` may show a default confirmation page, but GET should never mutate state. Thymeleaf generates the hidden CSRF input for the POST form above automatically. There is no `@PostMapping("/logout")` in the controller: `LogoutFilter` intercepts the request before it reaches MVC.

### 3.8. `src/main/resources/application.properties`

```properties
spring.application.name=session-login-lab

# Idle duration before the session expires
server.servlet.session.timeout=20m

# Session cookie cannot be read via document.cookie
server.servlet.session.cookie.http-only=true

# Suitable for standard same-origin web login flows
server.servlet.session.cookie.same-site=lax
```

**For local HTTP**, `Secure=true` is not forced so browsers can send the cookie over `http://localhost:8080`. **For production HTTPS**, set `server.servlet.session.cookie.secure=true` via environment configuration, ensuring traffic genuinely traverses TLS and any reverse proxy is trusted and configured properly. `SameSite=Lax` reduces certain cross-site cookie-sending scenarios but **does not replace CSRF tokens**; if a product has real cross-site requirements, align SameSite, CSRF, CORS, SSO, and cookie policies together.

## 4. Running the Application and Observing the Flow Precisely

Inside the `session-login-lab` directory:

```bash
java -version
mvn -version
mvn clean test
mvn spring-boot:run
```

Ensure `java -version` shows JDK 17 or higher and Maven is recent enough for the project. Once running, visit `http://localhost:8080`.

**Hands-on browser walkthrough:**

1. Open a private/incognito window and visit `/dashboard`. Without an authenticated session, the browser is redirected to `/login`. Open Network to observe status **302** and the `Location` header.
2. Inspect the login form DOM: it has `username`, `password`, and `_csrf` inputs. Try a wrong password: `learner / wrong`. Result: redirect to `/login?error`, generic error message, no entry to dashboard.
3. Log in with `learner / lesson-password-123`. Result: redirect to `/dashboard` (or the originally saved protected URL) and see `Hello, learner`.
4. Open DevTools → Application/Storage → Cookies, inspect `JSESSIONID` and its `HttpOnly` and `SameSite` flags. This is a **session ID**, not a password. Compare the session ID before and after login if a pre-login session existed; with session fixation protection, the ID changes upon successful authentication.
5. Refresh `/dashboard`: you remain logged in because the browser sends the session cookie and the server looks up the matching `SecurityContext`. Open the same URL in a separate private window (cookies not shared): you must log in separately.
6. Click **Log out** on the dashboard. In Network, confirm the browser sends **POST /logout** with a CSRF token; the server redirects to `/login?logout`. Then revisit `/dashboard`: you must log in again.
7. Try sending **POST /logout without a CSRF token** using an HTTP tool/MockMvc: by default it returns **403**; protected resources must not be affected by such a forged request.

**Expected table when there is no saved request:**

| Request / action | Typical HTTP status | Meaning |
|---|---:|---|
| `GET /` anonymous | 200 | Public page |
| `GET /dashboard` anonymous | 302 → `/login` | Route protection |
| `GET /login` | 200 | Shows form with token |
| `POST /login` valid password + CSRF | 302 → `/dashboard` | Authentication succeeded |
| `POST /login` wrong password + CSRF | 302 → `/login?error` | Authentication failed |
| `POST /login` missing CSRF | 403 | Blocked before authentication |
| `GET /dashboard` with valid session | 200 | Server found Authentication |
| `POST /logout` with valid CSRF | 302 → `/login?logout` | Logged out, session invalidated |
| `POST /logout` missing CSRF | 403 | Blocks forged logout |
| `GET /dashboard` after logout | 302 → `/login` | Session invalidated |

The 302/200/403 codes reflect this demo application's setup. Reverse proxies, custom authentication entry points, API-oriented configs, or a pre-login saved URL can change exact behavior. Never treat this table as a rigid assumption for every Spring Security app.

## 5. HTTP Sessions, Cookies, and SecurityContext Lifecycle

### 5.1. When is a session created?

The browser may receive `JSESSIONID` as soon as the login form renders because the server needs to store state for CSRF or a saved pre-login request. That **does not mean the user is logged in**. Separate:

- *Session exists:* the server has an HTTP session bound to an ID.
- *Authenticated session:* the stored context holds a successful `Authentication` with the appropriate principal.

Upon successful login, Spring Security attaches the authentication to `SecurityContext` and uses `SecurityContextRepository` to persist state across requests. In HTTP-session-based apps, the state lives on the server; the servlet container uses the cookie to map requests back to the right session. Spring Security does not replace the Servlet container's ID management role.

### 5.2. Preventing session fixation

Example attack scenario: an attacker tricks a victim into using a session ID the attacker already knew before the victim logged in. If the app kept the same ID after login, the holder of that ID could hijack the authenticated session. With `changeSessionId()`, once the victim authenticates, the container generates a new ID; the old ID is no longer a key to that authenticated session. Session cookies should also carry `Secure` over HTTPS, `HttpOnly`, and an appropriate `SameSite` attribute.

**Never use `sessionFixation().none()` just to make an exercise "easier to run"; doing so removes an important defense.** In Servlet 3.1+ environments `changeSessionId` is typically the default anyway, so configuring it in the demo is primarily instructional. Rotating the ID does not fix XSS, post-login cookie theft, compromised devices, or missing TLS.

### 5.3. Session lifetime and multiple devices

`server.servlet.session.timeout=20m` is the **session** timeout, typically measured by inactivity. Do not assume the user is logged out exactly 20 minutes after clicking login, nor rely on the browser proactively deleting the cookie when the server expires the session.

Design questions to answer:

- How long may a session stay alive if the user remains continuously active? Is an absolute timeout needed in addition to an idle timeout?
- After a password change, account lock, or permission revocation, when are old sessions invalidated? Sessions must be destroyed or permissions re-checked on sensitive requests.
- Can a user log in simultaneously on multiple browsers/devices? If limiting to one concurrent session, configure concurrent session control, a suitable `SessionRegistry`, and `HttpSessionEventPublisher`/backing session infrastructure; test with two **independent** browsers, since two tabs in one browser normally share cookies.
- Are multiple app instances running? In-memory HTTP sessions on a single node can be lost or inconsistent when a load balancer routes across nodes. Consider Spring Session + Redis/JDBC, affinity, and timeout/cleanup policies depending on architecture.

Do not add `maximumSessions(1)` to the demo without specific requirements and test infrastructure: session limits affect product behavior and require testing how older sessions get evicted/expired.

### 5.4. Session policy must match application type

Common policies:

| Policy | Brief meaning | Suitable for |
|---|---|---|
| `IF_REQUIRED` | Creates an HTTP session when actually needed | Traditional web form login |
| `ALWAYS` | Creates a session when processing requests | Some web apps with explicit state needs |
| `NEVER` | Security will not create one, but may use an existing session | Architecture-dependent; understand the limits |
| `STATELESS` | Security neither creates nor uses sessions for `SecurityContext` | APIs authenticating each request via bearer token; unsuitable for this demo |

Session-based and token-based architectures have different lifecycles. You cannot simply drop `STATELESS` into the configuration above and expect form login to maintain an authenticated session across requests.

## 6. CSRF in Both Login and Logout

**CSRF (Cross-Site Request Forgery)** occurs when a browser holding a valid login cookie is tricked by another site into sending a state-changing request to your system. The server sees a valid cookie but cannot inherently tell whether the user intended that action.

In the demo, Spring Security enables CSRF by default for unsafe methods (`POST`, `PUT`, `PATCH`, `DELETE`). The form submits a token tied to the valid request context; an external site cannot obtain that valid token merely because the browser attaches cookies.

**Login needs CSRF too:** login CSRF can log a victim into an account controlled by an attacker, skewing audit trails or writing data under that account. **Logout needs CSRF too:** if GET/logout is allowed trivially, an external page can force the user's browser to log out.

Checklist:

1. Keep `csrf(withDefaults())` for cookie/session applications.
2. Use `th:action` on Thymeleaf POST forms so tokens are rendered in HTML. If using fetch/AJAX, send the token via the appropriate header; never copy static tokens into source code.
3. All state-mutating requests must use appropriate HTTP methods—never use GET to delete, change passwords, or log out.
4. CSRF tokens rotate or are cleared after authentication/logout per Spring Security's flow; AJAX clients must fetch fresh tokens when needed.
5. CORS, SameSite, CSP, XSS mitigation, and CSRF are separate layers and do not directly substitute for one another.
6. Do not disable CSRF globally because of one mobile/bearer-token API; if an app has multiple endpoint groups, separate `SecurityFilterChain`s or CSRF matchers along clear authentication boundaries and test explicitly.

**Common pitfall:** sending `POST /logout` from Postman or curl with only the cookie and no CSRF token produces **403**. That is `CsrfFilter` working as designed, not a reason to turn off CSRF. To test in a browser, use the Thymeleaf logout button; in automated tests, use `.with(csrf())`.

## 7. Secure Logout: Understanding Every Step

Spring Security provides `LogoutFilter` and `LogoutHandler` implementations. With the configuration above, a valid POST logout:

1. Checks CSRF before executing logout.
2. Invalidates the HTTP session for the current request.
3. Clears `Authentication` and related context (`SecurityContextHolder` and context repository).
4. Cleans up related state such as CSRF state and remember-me if configured.
5. Attempts to clear the named `JSESSIONID` cookie we specified and redirects to the confirmation URL.

**Key distinctions:**

- Redirecting to `/login` is only a UX response. Writing a controller returning `"redirect:/login"` without running logout handlers or invalidating the session leaves the user logged in—that is a fake logout.
- Session invalidation revokes the session **on the server**. Clearing the browser cookie is supplemental cleanup; verify Path, Domain, and reverse proxy behavior if cookies are not cleared as expected.
- Logging out **one session** does not automatically log out all devices. "Log out all devices" requires tracking and revoking other sessions; with standalone access JWTs, a separate token lifetime/revocation strategy is required.
- With SSO/OIDC, local session logout **does not automatically log out of the Identity Provider**. OIDC RP-initiated logout / front-channel / back-channel logout are separate flows that must be configured per provider.
- If `remember-me` is enabled, verify logout deletes its token/cookie properly; persistent remember-me requires a token store with safe rotation/revocation.
- Never allow GET for logout because links/prefetch/embeds can trigger it unintentionally; keep POST with CSRF.

For apps handling sensitive data, test clicking the browser Back button or browser caching after logout: stale HTML pages may still render from browser cache even though the session is dead. Responses containing personal data need appropriate HTTP cache headers; **re-displaying a cached page does not mean the API still grants access**. Only a fresh server request proves the session was revoked.

## 8. Automated Testing with MockMvc

`src/test/java/com/example/sessionlogin/LoginSessionLogoutTest.java` uses the Spring Boot test context and `spring-security-test`. It is a standalone test suite inside the Maven project above and does not require mocking `AuthenticationManager` manually.

```java
package com.example.sessionlogin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginSessionLogoutTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void anonymousCannotOpenDashboard() throws Exception {
        mvc.perform(get("/dashboard"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("http://localhost/login"));
    }

    @Test
    void publicAndLoginPagesAreAccessible() throws Exception {
        mvc.perform(get("/")).andExpect(status().isOk());
        mvc.perform(get("/login")).andExpect(status().isOk());
    }

    @Test
    void badPasswordIsRejected() throws Exception {
        mvc.perform(formLogin()
                .user("learner")
                .password("not-the-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andExpect(unauthenticated());
    }

    @Test
    void loginSessionAndLogoutWork() throws Exception {
        var login = mvc.perform(formLogin()
                .user("learner")
                .password("lesson-password-123"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/dashboard"))
            .andExpect(authenticated().withUsername("learner"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/dashboard").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("learner")));

        mvc.perform(post("/logout").session(session).with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));

        mvc.perform(get("/dashboard"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void csrfIsRequiredForLoginAndLogout() throws Exception {
        mvc.perform(post("/login")
                .param("username", "learner")
                .param("password", "lesson-password-123"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/logout"))
            .andExpect(status().isForbidden());
    }
}
```

**Helper notes:** `formLogin()` in `spring-security-test` generates a `POST /login` with a valid CSRF token, so real authentication can be tested without manually building tokens; `.with(csrf())` is used on POST logout. `@WithMockUser` and `.with(user(...))` are useful when testing authorization, but **they do not test the real login pipeline**; this exercise needs to test both password verification and sessions.

For the anonymous redirect, the absolute URL `http://localhost/login` is typical of `LoginUrlAuthenticationEntryPoint` under MockMvc; if a specific app/container returns a relative `/login` per configuration, adjust the matcher after observing the actual response. The remaining tests assert the core outcomes accurately.

**Deeper tests to add in a real project:**

- Start with an anonymous session ID A, perform login, and assert the new session ID B differs from A while necessary application session data is preserved.
- Use an old browser/session after logout to send a new request and verify it is forced to log in again; do not assert only redirect success.
- After timeout, verify the session no longer carries `Authentication`; UI messaging is appropriate without leaking data.
- Log in from two independent browsers, verify concurrent session policy and "logout all" if present.
- Failed login must not distinguish nonexistent accounts from wrong passwords in public messages.
- Test repeated failed credential attempts, account lockout, rate limiting, and event auditing in a test environment.
- Check session cookies over HTTPS for `Secure`, `HttpOnly`, `SameSite`, and correct Path/Domain; verify session IDs do not leak via URLs, logs, or Referer headers.
- With reverse proxies or SSO, test redirect URIs, host/scheme forwarding, IdP-linked logout, and network failure cases.

## 9. Safe Extensions for Real Production Systems

### 9.1. Account sources and passwords

`InMemoryUserDetailsManager` is a learning tool with no mechanism to persist user changes across restarts. For production:

- Use a `UserDetailsService` backed by a database/JPA/JDBC or LDAP/OIDC as the real identity source.
- For local passwords, store salted adaptive hashes and use `PasswordEncoder.matches` via the provider; never store plaintext passwords, never use `{noop}`, and never log login inputs.
- Manage enabled/locked/expired flags and authorities from trusted data; never trust roles sent by the browser.
- Rate-limit login attempts, detect credential stuffing, and enforce MFA/step-up authentication where risk warrants it.
- Password resets require single-use tokens, expiration, identity verification, and session revocation per policy.

### 9.2. Cookies and transport

| Control | How to apply | Why |
|---|---|---|
| End-to-end HTTPS/TLS | Enforce HTTPS at the edge and configure reverse proxies properly | Prevents exposing passwords/session cookies in transit |
| `Secure` cookie | `server.servlet.session.cookie.secure=true` in production HTTPS | Browser will not send cookies over plain HTTP |
| `HttpOnly` | Keep `server.servlet.session.cookie.http-only=true` | Normal JavaScript cannot read the session cookie |
| `SameSite` | Choose Lax/Strict/None based on UX and actual cross-site needs; None requires Secure | Reduces unnecessary cookie transmission in cross-site contexts |
| Timeout | Idle timeout, consider absolute timeout and re-authentication | Limits the window for session abuse |
| Avoid session IDs in URLs | Prefer cookies, avoid URL rewriting and logging IDs | Prevents leaking session IDs in browser history, referer headers, and logs |
| Security headers & XSS prevention | Keep protective headers, escape output, apply an app-appropriate CSP | Reduces risk of session/token theft |
| Audit | Log login success/failure/logout and session revocation using safe identifiers | Provides operational trails without leaking credentials |

When behind a reverse proxy, trust `Forwarded` / `X-Forwarded-*` headers only from controlled proxies; misconfiguration can cause wrong `http://` redirects or strip the `Secure` flag. Never treat `HttpOnly` as "complete XSS immunity": malicious scripts can still issue authenticated actions on the user's behalf if XSS exists.

### 9.3. Consistency across multiple authentication mechanisms

- **Form login + HTTP session** fits traditional web apps. It requires protecting CSRF, cookies, and server-side session lifecycle.
- **OIDC login** can still create a **local HTTP session** after the IdP authenticates the user. Local logout and IdP logout are two distinct operations to design.
- **JWT Resource Servers** typically validate a bearer token on each request and may be stateless. Session logout in this demo does not revoke access tokens issued elsewhere.
- **Remember-me** extends automatic re-authentication, not an infinite session. When enabled, manage keys, token persistence, rotation, expiry, and logout cleanup.
- **Multi-instance apps** must decide how sessions are shared (e.g., Spring Session) and how deployments/restarts behave; single-node in-memory sessions do not ensure a consistent user experience.

## 10. Common Errors and How to Diagnose Them

| Symptom | Common cause | Check/fix |
|---|---|---|
| Visiting `/dashboard` loops to `/login` | Login page is not `permitAll`, or cookie/session is not being sent | Check matchers, HTTP 302 chain, cookie Path/Secure/SameSite |
| `POST /login` always returns 403 | Missing/invalid CSRF token, form lacks `th:action`, or stale token | Inspect hidden `_csrf`, session cookie, Spring Security logs |
| Login with right password still gives `?error` | Password hash/encoder mismatch, wrong username, or disabled account | Check `UserDetailsService`, `PasswordEncoder.matches`, and user status |
| Login succeeds but next request is still anonymous | Cookie not sent by browser, wrong domain/path, or load balancer not sharing sessions | Inspect Network, `Set-Cookie`, session store, and proxy |
| Session ID does not change on login | No pre-login session existed or strategy was misconfigured | Create a pre-login session and compare both IDs; keep `changeSessionId` |
| Clicking a `/logout` link leaves user logged in | GET does not perform actual logout when CSRF is enabled | Use a POST form + token; check `LogoutFilter` |
| Logout returns 403 | Missing/wrong CSRF token or token belongs to another session | Render a fresh form and POST with a valid token |
| Still able to access data after logout redirect | Controller only redirected without invalidating session; or another session exists | Use `LogoutFilter`, test a new request with the old cookie |
| Multiple tabs appear "all logged in" | Tabs share cookies within the same browser profile | Test with two independent browser profiles/browsers |
| First AJAX request after login fails CSRF | Token was cleared/rotated upon authentication while JS held the old token | Fetch a fresh CSRF token after login |
| Old page still visible on Back button | Browser cache displays HTML saved before logout | Configure cache headers for sensitive data, test with a fresh server request |
| No authentication inside an async task | `SecurityContext` is request/thread-bound, not propagated to arbitrary threads | Use propagation-aware integration or pass principal intentionally |

**Diagnostic principle:** capture a request/response trace including URL, method, status, redirects, cookie flags, CSRF parameter, and session state in a test environment; always mask `Cookie`, `Authorization`, passwords, session IDs, and tokens before sharing logs.

## 11. Self-Check Questions and Extension Exercises

1. Why might `GET /login` already create a session while `Authentication` is not yet an authenticated user?
2. Why should the cookie store a session ID and never a password? What happens if an attacker steals the cookie after login?
3. What is the difference between per-request `SecurityContextHolder` and `SecurityContextRepository` persisting context across requests?
4. Why is rotating the session ID after login important? What risk arises if the old ID stays usable?
5. Why should both form login and logout have CSRF protection even when the user is not yet logged in on the first request?
6. How does a plain controller redirect differ from logout via `LogoutFilter` and session invalidation?
7. What changes with OIDC SSO, multiple server instances, or a "log out all devices" requirement?
8. How does server session timeout differ from browser cookie lifetime? Why do two tabs usually share a login?

**Progressive extensions:**

- Add an `/admin` route accessible only to `ROLE_ADMIN`; write an integration test verifying 403 for a user lacking the role.
- Replace demo accounts with an account table storing BCrypt hashes, enabled/locked state, and roles; test wrong passwords, locked accounts, and reloading after restart.
- Measure session idle timeout and handle UX on expiration; warn before timeout if business requirements call for it.
- Test two browsers side by side and add a concurrent-session limit policy; provide a "log out other devices" button if required.
- Try deploying two instances with a shared session store and verify login/logout still behave properly across a load balancer and restarts.
- When integrating an IdP, separately specify local logout, token revocation, and SSO single logout.

## 12. Official Documentation

- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — Authentication Persistence & Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Testing Logout](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/logout.html)
- [Spring Security — Testing CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Boot — Servlet Web Server, Sessions and Cookies](https://docs.spring.io/spring-boot/reference/web/servlet.html)

The target outcome of this exercise is an observable, explainable, and testable path **anonymous → form login → authenticated HTTP session → CSRF-protected logout → anonymous**, where every redirect, cookie, context, and session plays a clear role and authentication and logout logic rely on Spring Security's standard mechanisms.
