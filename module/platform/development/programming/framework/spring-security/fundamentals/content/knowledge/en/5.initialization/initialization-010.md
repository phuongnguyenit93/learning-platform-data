# Testing with Browser, curl, and Test Suites Before Expanding Configuration

> **Goal of this practice session:** Before writing dozens of `SecurityFilterChain` beans, JWT filters, or authorization rules, **observe the exact behavior Spring Security already provides**, record expectations, and build a repeatable test suite. Use a **browser** to understand login/sessions/cookies, **curl** to inspect raw HTTP statuses and headers, and **MockMvc + Spring Security Test** to verify both allowed and denied cases. Once you have a baseline, make one small change at a time and re-test immediately.

This lesson belongs to the **Initialization** group of the **Spring Security – fundamentals** module. The focus is a **Spring Boot 3.x application using Spring MVC/Servlet and default Spring Security configuration**, before extending it. WebFlux requires `WebTestClient` and `SecurityWebFilterChain` instead; do not copy all Servlet code verbatim.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Run an app with `spring-boot-starter-security` and **no custom `SecurityFilterChain` yet**; identify the `user` account and development-generated password in logs.
2. Distinguish how a browser requesting HTML (typically redirecting to `/login`) behaves vs. a client requesting JSON (typically receiving `401 Unauthorized`) against the same protected endpoint.
3. Use `curl -i`, `-H "Accept: application/json"`, and `-u user` to inspect status codes, `Location`, `WWW-Authenticate`, cookies, and response bodies.
4. Demonstrate how `401` (unauthenticated), `403` (missing permission or CSRF), `200` (allowed), and `302` (login redirect) differ, rather than judging solely by "what appears on screen."
5. Write integration tests using `@SpringBootTest`, `@AutoConfigureMockMvc`, `@WithMockUser`/`user()`, and `csrf()`; understand that mock users test authorization, **not real password verification**.
6. Distinguish a failure blocked by a security filter from a routing error or business error.
7. Add a first, well-scoped access configuration and immediately re-verify baseline behaviors after the change.

## 2. Why Measure Defaults First?

Beginners often see that right after adding the Spring Security dependency, every URL asks for login. They immediately add `.anyRequest().permitAll()` or `.csrf(csrf -> csrf.disable())` to make the API "work again." Doing that obscures the essential question: **what is protecting the request and what actually needs to change?**

In a Spring Boot 3.5 app with Spring MVC and the security starter, before you configure core security beans yourself, Spring Boot can supply:

- A default `SecurityFilterChain` protecting endpoints with authentication.
- An in-memory user with username `user` and a **random password** printed to startup logs (development only; requires appropriate logging to appear).
- Form login for browsers and HTTP Basic for suitable clients via request/content negotiation.
- CSRF protection on HTTP requests needing protection, default security headers, and corresponding security context/session management.

This is a **learning baseline**, not a production user/role/token design. Spring Security operating at the HTTP boundary does not automatically protect individual resources, SQL queries, or business operations.

**Experimentation rule:** Do not ask only "can it be accessed?" Ask:

1. Which URL, HTTP method, `Accept`, and `Content-Type` does the request carry?
2. Are valid credentials present? Is the browser holding a session cookie from an earlier run?
3. What is the actual status? What do `Location`, `WWW-Authenticate`, and `Set-Cookie` headers show?
4. Did security block the request before the controller, or did it pass security and fail in the controller?
5. Are the results reproducible in an incognito window or by re-running tests?

## 3. Three Observation Layers: Browser, curl, and Tests

| Tool | Best used to inspect | Known limitations |
| --- | --- | --- |
| **Browser** | Login page, redirects, session cookies, hidden form CSRF fields, asset loading | Browsers manage cookies, redirects, and cache automatically; easy to hide the initial request |
| **curl** | Raw status/headers/body, Basic auth, `Accept`, redirects, cookie jars, CSRF failures | Does not automatically execute browser session/form UX or JavaScript unless scripted |
| **MockMvc + Spring Security Test** | Automated tests for HTTP rules, principals, statuses, CSRF, regressions | Typically runs without opening an HTTP socket; does not verify production TLS, reverse proxies, or credentials |

These three tools complement one another. A passing MockMvc test does not prove production HTTPS is right; a successful browser login does not prove POST has CSRF protection; and `curl -k` succeeding with an invalid certificate is not proof of secure transport.

## 4. Environment Setup

Examples use **JDK 17+**, Maven 3.6.3+, and **Spring Boot 3.5.16**. Release 3.5.16 was published on June 25, 2026 and is the final OSS release of the 3.5 line; choose an actively supported Boot 4.x line with current patches when starting a new production project. Pinning this version here keeps demo syntax aligned with Spring Security 6.5.x and Spring Boot 3.5.

Verify your environment in a terminal:

```bash
java -version
mvn -version
```

Expected: Java shows **17 or higher**, and Maven shows its version and active JDK. Do not rely on a verbatim stdout copy since machines, JDK vendors, and Maven versions vary.

Minimal project layout:

```text
security-baseline-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/baseline/BaselineApplication.java
    └── test/
        └── java/demo/baseline/BaselineSecurityTests.java
```

**Do not create `SecurityConfig`, `SecurityFilterChain`, custom authentication providers, or JWT filters in the initial step.** The goal is measuring the initialization baseline.

### 4.1. Create pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>security-baseline-demo</artifactId>
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
```

The first two starters run web + security. The two `test` dependencies add JUnit/MockMvc and security test helpers. Do not include `spring-boot-starter-webflux` in this Servlet demo.

### 4.2. Complete Application Code Without SecurityConfig

Create `src/main/java/demo/baseline/BaselineApplication.java`:

```java
package demo.baseline;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BaselineApplication {
    public static void main(String[] args) {
        SpringApplication.run(BaselineApplication.class, args);
    }
}

@RestController
class DemoController {

    @GetMapping("/hello")
    String hello(Authentication authentication) {
        return "Hello " + authentication.getName();
    }

    @GetMapping("/health")
    String health() {
        return "ok";
    }

    @GetMapping("/admin")
    String admin() {
        return "admin-action";
    }

    @PostMapping("/notes")
    String createNote(Authentication authentication) {
        // Illustrates a POST request only; no side effects or database.
        return "created-by-" + authentication.getName();
    }
}
```

Four routes are created **as test targets**, not because they already have distinct protections. Under default security, neither `/health` nor `/admin` is automatically public or role-restricted merely from its URL name. What is allowed right now depends on the **default** policy, not controller method names.

**Key point:** `Authentication authentication` is injected by Spring MVC once the request is authenticated. Accepting this parameter in the controller does not perform authentication; Spring Security's filters run before the controller.

### 4.3. Starting the Application

```bash
mvn spring-boot:run
```

If startup succeeds, the app normally listens on `http://localhost:8080` by default. In the startup log, look for a line beginning with:

```text
Using generated security password:
```

After the colon is the **random password for this specific run**, not a fixed value from documentation. Default username is `user`. This log appears only when Boot actually creates the default user; if you supply a `UserDetailsService`, `AuthenticationProvider`, another auth module, or altered config, behavior will differ.

**Keep this password in your study terminal; never post it to chat, Git, screenshots, or public CI logs.** Auto-generated passwords are not production user management. In Spring Boot 3.5, the line is typically logged at WARN level; overly restrictive logging configs may hide it.

## 5. Testing with a Browser: Seeing the Real Login Flow

### 5.1. Start with an Incognito Session

1. Open a private/incognito window so no cookies from previous runs are reused.
2. Open `http://localhost:8080/hello`.
3. For a browser request preferring HTML, Spring Security typically returns a `302` redirect to `/login`. The browser follows it automatically, so the address bar may display only `/login`, tempting beginners to think the original URL was unprotected.
4. The login page is generated by Spring Security when default form login is active.
5. Sign in with username `user` and the generated password from the log. On success, the browser returns to the requested resource or default URL via saved-request handling.

After login, `GET /hello` responds with:

```text
Hello user
```

This is the controller's **success body**; HTTP status is usually `200`. Returning `Hello user` in the browser does not mean every action is permitted—for example, POST still requires CSRF and later rules may enforce specific permissions.

### 5.2. Inspect Network Instead of Looking Only at the Screen

Open Developer Tools → **Network** and enable **Preserve log** to keep requests across redirects. Inspect each request:

| Request | What to Observe |
| --- | --- |
| Initial `GET /hello` (anonymous, Accept HTML) | Common `302` status; `Location: /login` header |
| `GET /login` | HTML form, status `200` when login page is valid |
| `POST /login` | Form submits credentials plus CSRF token, typically redirecting after auth |
| `GET /hello` after login | Request carries session cookie and receives `200` |
| `POST /notes` from a form lacking a CSRF token | Gets `403` when CSRF protection applies |
| `GET /health` inside the active session | `200` because authenticated, not because `/health` is public |

In **Application/Storage → Cookies**, you may see a session cookie (commonly `JSESSIONID`), depending on session and setup. **Never log or share cookie values**: they can act as a secret sufficient to impersonate the logged-in user. Check `HttpOnly`, `Secure`, and `SameSite` per environment; in a localhost HTTP demo, never treat cookie flags as production-ready.

**Trap:** Browsers automatically attach cookies to subsequent requests, so reloading `/hello` after logging in no longer tests anonymous access. Use a fresh private window or clear the session safely when comparing. A `200` inside an authenticated session does not prove an endpoint is public.

### 5.3. Why Does Logout Need CSRF Consideration?

With form login and CSRF enabled, logout is a state-changing operation. `GET /logout` may render a confirmation page containing a form; the actual `POST` performs logout under the configured mechanism. Do not assume calling `GET /logout` via curl always ends the session; that depends on logout/CSRF configuration. After logging out, test `GET /hello` to confirm the session returned to unauthenticated.

## 6. Testing with curl: Inspecting Status, Headers, and Basic Auth Directly

### 6.1. Choosing the Right Invocation

The commands below target a terminal on the same host as the running server. On Linux/macOS/Git Bash use `curl`; on PowerShell use `curl.exe` to avoid the legacy `curl` alias. `-i` prints response headers and body; `-v` reveals detailed network exchanges but **can leak credentials/cookies** if you share logs.

**A. Client requesting JSON with no credentials:**

```bash
curl -i -H "Accept: application/json" http://localhost:8080/hello
```

Typical response:

```http
HTTP/1.1 401
WWW-Authenticate: Basic realm="Realm"
```

Response body, secondary headers, and status-line formatting can vary by server/config. **What to verify is `401`**, not every byte of the headers; API clients receive a challenge rather than a browser redirect.

**B. Client requesting HTML with no credentials:**

```bash
curl -i -H "Accept: text/html" http://localhost:8080/hello
```

Typically expects `302` with a `Location` header pointing to `/login`. By default curl does **not** follow redirects unless `-L` is passed, letting you see the step browsers hide automatically.

**C. Authenticating via HTTP Basic without putting the password on the command line:**

```bash
curl -i -u user -H "Accept: application/json" http://localhost:8080/hello
```

Curl prompts interactively for the password; enter the random value from the log. When correct, expect status `200` and body:

```text
Hello user
```

With a wrong password, expect unauthenticated rejection (typically `401`) and **not** `Hello user`. Base64 encoding in HTTP Basic does **not** protect passwords over a network: use HTTP on `localhost` only for labs; production must use HTTPS.

**D. A path that sounds public is still protected:**

```bash
curl -i -H "Accept: application/json" http://localhost:8080/health
```

In the baseline without `permitAll`, `/health` also requires authentication; expect `401`. This gives you data to decide later which exact endpoints to open without turning off security everywhere.

**E. Testing POST with a valid user yet no CSRF token:**

```bash
curl -i -u user -X POST http://localhost:8080/notes
```

Even after entering the right password, the request **can still receive `403 Forbidden`** because `CsrfFilter` requires a token on POST. That rejection differs from `401` caused by missing/wrong credentials. In Servlet stacks, the CSRF filter often runs before Basic authentication, so a 403 on POST does not prove the user was authenticated; to isolate both checks, test with both valid credentials and a valid token.

**F. Inspecting headers without following redirects:**

```bash
curl -I -H "Accept: text/html" http://localhost:8080/hello
```

`-I` sends **HEAD**, not GET. HEAD and GET often share authorization handling yet are not identical in handler/body behavior; to test true GET while seeing headers, prefer `curl -i` or `curl -D - -o /dev/null` (on POSIX). Never use `-I` to draw exact conclusions about GET without noting the HTTP method difference.

### 6.2. Understanding Each Status Code

| Status | Useful meaning in the lab | Do not jump to conclusions |
| --- | --- | --- |
| `200 OK` | Request reached handler and returned success | Every endpoint and every user is authorized |
| `302 Found` | Redirect, often to login when browser wants HTML | "Server error" or data was already returned |
| `401 Unauthorized` | Authentication needed / credentials rejected, often with challenge | Merely missing a role; that is a 403 authorization case |
| `403 Forbidden` | Request denied, possibly due to missing privilege **or CSRF** | Authentication succeeded; CSRF can reject early |
| `404 Not Found` | Handler/resource not found or policy intentionally hides existence | Whether Spring Security ran or not |
| `405 Method Not Allowed` | Path has a handler but method is unsupported (subject to earlier rules) | Proof of authorization rules |
| `500 Internal Server Error` | Server exception | Adding `permitAll` will fix the bug |

Final response codes also depend on the security chain, controllers, Spring MVC error handling, reverse proxies, and other filters. Tests should assert only statuses **guaranteed by the lesson's contract**.

### 6.3. When You Need to Simulate a Browser Session with curl

Form login differs from Basic Auth. For form login, you must manage:

1. Cookie jar received from `GET /login`.
2. CSRF token from the form/token repository and matching request.
3. `POST /login` with exact username/password/token fields and session cookie.
4. Subsequent requests carrying the issued cookie.

`curl -c cookies.txt` saves cookies from a response and `curl -b cookies.txt` sends them back; **neither automatically extracts nor attaches CSRF tokens**. Never copy a token from one session into another and expect it to work.

For basic baseline verification, use a browser for form sessions and `curl -u` for Basic; writing a custom form/CSRF curl script makes more sense once you understand filters and token storage.

## 7. Writing Your First Automated Test Suite with MockMvc

Browser/curl exploration discovers behavior. `mvn test` turns discoveries into **repeatable rules that run whenever code changes**.

### 7.1. Why Use @SpringBootTest + @AutoConfigureMockMvc?

- `@SpringBootTest` starts the real Spring application context with real auto-configuration.
- `@AutoConfigureMockMvc` sets up `MockMvc` to run requests through Spring MVC and the Spring Security filter chain.
- `spring-security-test` supplies `@WithMockUser`, `user()`, and `csrf()`.
- Each test asserts the expected outcome of one request and runs in CI without opening a browser.

The example below compiles alongside `pom.xml` and `BaselineApplication.java` above. Create `src/test/java/demo/baseline/BaselineSecurityTests.java`:

```java
package demo.baseline;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrlPattern;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BaselineSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousHtmlRequestIsRedirectedToLogin() throws Exception {
        mvc.perform(get("/hello").accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));

        mvc.perform(get("/login").accept(MediaType.TEXT_HTML))
            .andExpect(status().isOk());
    }

    @Test
    void anonymousApiRequestGets401InsteadOfHello() throws Exception {
        mvc.perform(get("/hello").accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());

        // Route /health exists, yet in the baseline it still requires login.
        mvc.perform(get("/health").accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice", roles = {"USER"})
    void authenticatedUserCanReadHello() throws Exception {
        mvc.perform(get("/hello"))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello alice"));

        // Before an admin policy exists, the baseline only requires authenticated.
        mvc.perform(get("/admin"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-action"));
    }

    @Test
    void postNeedsCsrfEvenWhenUserIsPresent() throws Exception {
        mvc.perform(post("/notes").with(user("alice")))
            .andExpect(status().isForbidden());

        mvc.perform(post("/notes")
                .with(user("alice"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());

        mvc.perform(post("/notes")
                .with(user("alice"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created-by-alice"));
    }

    @Test
    void securityHeadersArePresent() throws Exception {
        mvc.perform(get("/login").accept(MediaType.TEXT_HTML))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"));
    }
}
```

Test breakdown:

- **Blocking anonymous access:** HTML requests can be redirected to login, while JSON clients get `401`. These two results **do not contradict**, because the entry point is picked based on request/client.
- **Mock user:** `@WithMockUser` or `user("alice")` builds a simulated `Authentication`. Alice **does not need to exist** in a real `UserDetailsService`; this verifies filters, controllers, and policies work with that identity, **not** that Alice's password can actually log in.
- **CSRF:** `with(csrf())` attaches a valid token in MockMvc; `with(csrf().useInvalidToken())` intentionally sends an invalid token. Both an authorized user missing a token and one with a bad token are rejected.
- **Headers:** `X-Content-Type-Options: nosniff` is a standard protective response header in Spring Security defaults. Behind a proxy, verify real responses too; MockMvc does not test production infrastructure.

**Note on `@WithMockUser`:** these tests do not verify password/token validation. To test Basic authentication paths automatically, use `httpBasic()` against a configured test `UserDetailsService`; in the baseline we intentionally kept the random default password and tested it via `curl -u user` and local logs. Later, add real authentication tests once you define an identity provider.

### 7.2. Run and Evaluate

Stop the dev server if you want a clean run, then in the project directory:

```bash
mvn test
```

Maven runs JUnit and reports **BUILD SUCCESS** when the suite meets expectations. If any test fails, read the **specific test name and assertion**, rather than deleting tests or disabling Spring Security to get a green build. Check these areas:

- HTML test receives `401` instead of redirect: was `Accept: text/html` set; did another config override form login?
- JSON test receives redirect: check content negotiation, entry points, and leftover session/cookies from earlier requests.
- `POST /notes` with valid CSRF still gets `403`: was a mock user attached; is the security filter wired into MockMvc; did another URL rule block it?
- `/admin` with Alice suddenly switches to 403: was a new role rule added before completing the baseline?
- Cannot resolve `@WithMockUser`/`csrf()`: is `spring-security-test` added in `test` scope?
- `NoClassDefFoundError` or dependency download errors: check `java -version`, local Maven cache, dependency tree, and BOM; **never mix Spring Security versions arbitrarily**.

**The test suite is presented as runnable code**, though outcomes depend on matching JDK/Maven environments and compatible dependencies. Key statuses reflect standard Spring Security 6.5 behavior without custom security configuration.

### 7.3. Unit Tests, Integration Tests, and Live Network Tests

| Test Type | Scope | When to use? |
| --- | --- | --- |
| Controller/service unit test without filters | Pure logic | Validation, business rules; **does not** verify HTTP security |
| MockMvc with Spring context and filters | Servlet chain + controller | Testing authentication/authorization/CSRF/headers |
| `@WithMockUser`/`user()` | Policy with simulated identity | Testing rules without real passwords/tokens |
| `httpBasic()` + real test provider | End-to-end Basic credentials in context | Testing the app's authentication provider/encoder |
| Browser/curl against live server | HTTP headers, redirects, cookies, network | Verifying actual setup and client behavior |
| HTTPS/proxy integration test | TLS termination, headers, load balancer | Deploying behind ingress/CDN/proxies |
| Database integration test | Owner/tenant/resource policies | When real data and business authorization exist |

Never write dozens of unit tests mocking the filter chain while skipping a real integration test: matcher bugs, filter order, sessions, and CSRF often surface only when running through Spring Security.

## 8. Write a Verification Matrix Before Editing Configuration

Record observed results so regressions stand out later. Example matrix for the **baseline** in section 4:

| # | Client, method, path | Credentials/CSRF | Initial Expectation | How to Observe |
| --- | --- | --- | --- | --- |
| 1 | Browser `GET /hello` | None | Login redirect (typically 302) | Network tab |
| 2 | curl `GET /hello`, `Accept: application/json` | None | `401` | `curl -i` |
| 3 | curl `GET /hello` | Valid Basic | `200`, `Hello user` | `curl -u user` |
| 4 | curl `GET /hello` | Wrong Basic | Not `Hello user`, typically `401` | `curl -u user` |
| 5 | Browser `GET /login` | None | Login form `200` | Browser/MockMvc |
| 6 | curl `GET /health`, JSON | None | `401`, despite "health" name | curl/MockMvc |
| 7 | MockMvc `GET /admin` | Alice mock user | `200` in baseline: no role rule yet | `@WithMockUser` |
| 8 | MockMvc `POST /notes` | Alice, no CSRF | `403` | `user()` |
| 9 | MockMvc `POST /notes` | Alice, wrong CSRF | `403` | `csrf().useInvalidToken()` |
| 10 | MockMvc `POST /notes` | Alice, valid CSRF | `200`, body `created-by-alice` | `csrf()` |

Whenever tests or browser/curl differ, pinpoint the specific cause before claiming Spring Security defaults "do not work." For instance, the request might already carry a session cookie, `application.properties` might set `spring.security.user.*`, an OAuth2 starter might be on the classpath, or another security chain might be defined elsewhere.

### 8.1. Checking Whether Defaults Are Truly Active

In the initial lab:

- Is the exact `spring-boot-starter-security` dependency present?
- Has any `SecurityFilterChain` bean been declared by the project, a library, or another auto-configuration?
- Is there a custom `UserDetailsService`, `AuthenticationProvider`, or `AuthenticationManager` bean?
- Does a Spring profile, environment variable, or test configuration set `spring.security.user.name/password`?
- Is an OAuth2 Login/Resource Server/SAML starter altering auto-configuration conditions?
- Does the browser hold an existing session cookie or auto-send Basic credentials?
- Did 401/403 come from Spring Security or an external proxy?

In Spring Boot 3.5, **adding a `SecurityFilterChain` bean makes Boot back off from default web security configuration**, yet **does not automatically disable** the default `UserDetailsService`. Changing identity or authentication methods is a separate decision. Understanding those two scopes prevents the "I customized URL rules yet the default user still exists" surprise.

## 9. After the Baseline Is Green: Add One Small Security Change

Only after confirming the table in section 8, apply the first requirement change:

- `GET /health` may be called **without logging in**.
- `GET /admin` may only be entered by someone with `ROLE_ADMIN`.
- Other endpoints continue requiring `authenticated()`, preserving form login + HTTP Basic and CSRF protection.

This is an **intentional extension**; never open every URL just to make one public endpoint work.

### 9.1. Add a SecurityFilterChain Bean

Create `src/main/java/demo/baseline/WebSecurityRules.java`:

```java
package demo.baseline;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class WebSecurityRules {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Key details to read closely:

- `requestMatchers(HttpMethod.GET, "/health").permitAll()` allows only GET on that path, not POST/DELETE or other Actuator endpoints.
- `requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")` requires authority `ROLE_ADMIN` via the default role prefix convention.
- `anyRequest().authenticated()` keeps login required for remaining paths; this does **not** block unmapped endpoints on its own, since after authentication Spring MVC decides 404/405.
- `formLogin(...)` and `httpBasic(...)` are declared explicitly, because once the app supplies its own chain you should not assume Boot's entire default web config remains active as-is.
- Without `csrf.disable()`, CSRF protection stays enabled as appropriate for Servlet form login.
- With no custom `UserDetailsService`, the default `user` may still exist. This remains a lab, not a production configuration.

With multiple chains later on, you will need `securityMatcher(...)`/`@Order` and an explicit fallback. At this starting stage, **one chain matching all requests** keeps observation straightforward and avoids exposing out-of-scope URLs. Do not split into multiple chains prematurely.

### 9.2. Add Tests for the New Policy

After adding `WebSecurityRules`, keep the tests for `/hello`, POST + CSRF, and headers. **Replace/adjust** the two baseline assertions that expected anonymous `/health` to return 401 and `/admin` as Alice to return 200, because policy intentionally changed. Specifically, in `BaselineSecurityTests`, remove the old expectations for those two endpoints and add the file below.

Create `src/test/java/demo/baseline/FirstRulesTests.java`:

```java
package demo.baseline;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FirstRulesTests {

    @Autowired
    MockMvc mvc;

    @Test
    void healthIsTheOnlyNewPublicGetRoute() throws Exception {
        mvc.perform(get("/health").accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().string("ok"));

        mvc.perform(get("/hello").accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void adminRequiresAdminRole() throws Exception {
        mvc.perform(get("/admin").with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin").with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-action"));
    }

    @Test
    void existingAuthenticatedRouteStillWorks() throws Exception {
        mvc.perform(get("/hello").with(user("alice").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello alice"));
    }
}
```

**Note before running `mvn test`:** `BaselineSecurityTests.java` contains two assertions valid only **before the extension** that must be updated:

1. In `anonymousApiRequestGets401InsteadOfHello()`, remove the `get("/health")` check expecting `401`. `FirstRulesTests.healthIsTheOnlyNewPublicGetRoute()` now tests that it returns `200`.
2. In `authenticatedUserCanReadHello()`, remove the `get("/admin")` check expecting `200` for Alice. `FirstRulesTests.adminRequiresAdminRole()` now verifies Alice gets `403` and admin gets `200`.

Keep all assertions for `/hello`, `/login`, CSRF, and headers intact. That way unchanged cases remain **regression tests**, while changed cases track intentional policy updates. Leaving contradictory expectations in place will fail the suite even when the new config is right.

After editing, run:

```bash
mvn test
```

Tests should pass when the new filter chain works properly. With the default `user` (typically having only `ROLE_USER`), live browser/curl access to `/admin` remains denied; `user("admin").roles("ADMIN")` in MockMvc **is a simulated principal**, not a password-authenticated admin account. To test authentication and admin role **together** with real credentials, configure a test user/provider and test `httpBasic(...)`/real login next.

### 9.3. Re-Verify with Browser and curl After the Change

Start the server again once `mvn test` passes:

```bash
mvn spring-boot:run
```

Verification commands:

```bash
curl -i -H "Accept: application/json" http://localhost:8080/health
curl -i -H "Accept: application/json" http://localhost:8080/hello
curl -i -u user -H "Accept: application/json" http://localhost:8080/hello
curl -i -u user -H "Accept: application/json" http://localhost:8080/admin
```

When prompted by curl, enter the password generated in **the new startup run**. Expected outcomes in order:

| Request | Status | Explanation |
| --- | --- | --- |
| `GET /health` anonymous | `200` | New `permitAll` rule |
| `GET /hello` anonymous JSON | `401` | `anyRequest().authenticated()` |
| `GET /hello` valid Basic `user` | `200` | Authenticated |
| `GET /admin` valid Basic `user` | `403` | `ROLE_USER` is not `ROLE_ADMIN` |

Opening `/health` in a browser requires no login; opening `/hello` anonymously still leads to the form; opening `/admin` as the logged-in default user is denied. This provides targeted **before/after** verification without changing numerous components at once.

## 10. CSRF, Cookies, and Testing POST Properly

### 10.1. Why Does POST Still Get 403 Even with Valid Basic/Password?

CSRF concerns state-changing requests automatically sent by browsers alongside existing credentials (cookies or other auto-sent credentials). A CSRF token lets the server confirm the request came from an authorized client flow. Spring Security Servlet normally enables CSRF protection by default in standard configurations.

In this lab:

- `GET /hello` is a read operation; safe requests do not need a CSRF token.
- `POST /notes` represents a state-changing operation under HTTP semantics even though the demo writes no DB, so CSRF protection blocks POST missing a token.
- `with(csrf())` in MockMvc lets you cleanly test **valid token** vs. **missing token**.
- `hasRole(...)` or `authenticated()` is not a CSRF token. Having the right permission does not protect a request against CSRF.

**Never call `csrf.disable()` just because a curl POST returned `403`.** A pure bearer-token API where scripts attach headers explicitly has a different threat model from cookie auth; assess real authentication and cookie usage before exempting specific endpoints from CSRF.

### 10.2. Form Login in the Browser

Spring Security's default form normally includes a hidden `_csrf` field; submitting the form lets the framework verify it. If you build a custom frontend form, handle tokens consistently with the configured `CsrfTokenRepository` and request handler. For cookie-backed sessions, both the session cookie and token may be required. Never grab an arbitrary token from another response or session and assume CSRF is "broken" when rejected.

### 10.3. Inspecting Cookies and Sessions

Check cookie attributes such as `HttpOnly`, `Secure`, `SameSite`, expiration, and scope in browser DevTools. Never print cookie values into public logs. Only **HTTPS** protects credentials/cookies over the network; HTTP requests in this lab are strictly for `localhost`. Once placed behind a reverse proxy, test HSTS, forwarded headers, TLS termination, and cookie flags against your real architecture.

## 11. Distinguishing Spring Security Errors from Controller Errors

If results differ from expectations, follow these steps:

### 11.1. Read Status Codes Before Editing Code

- `401` with `WWW-Authenticate`: unauthenticated/challenged request; check credentials or Basic entry point.
- `302` and `Location: /login`: browser sent to form login, not an endpoint returning content directly.
- `403` on POST: check **CSRF first**, then roles/authorities; do not guess from status code alone.
- `404`: endpoint may be unmapped or policy may hide resources; check whether security let the request reach a handler.
- `405`: HTTP method may not be handled by the controller; check mappings, CSRF, and method rules.
- `500`: server exception; inspect stack traces and business logic errors instead of turning off filters.

### 11.2. Enable Debugging Carefully

In a **local environment**, you can set:

```properties
logging.level.org.springframework.security=DEBUG
```

Startup/request logs can reveal security filters and paths, though details and scope vary by version. Never leave broad `TRACE`/`DEBUG` active in production, and **never log** passwords, Basic `Authorization` headers, tokens, session cookies, or sensitive data. In browsers, use DevTools Network to inspect redirects; with curl, use `-i` instead of sharing `-v` logs containing credentials.

### 11.3. Testing the "request → chain → controller" Relationship

```text
Request /hello
  |
  v
Servlet FilterChain
  |
  v
Spring Security FilterChainProxy
  |
  +--> security context / authentication
  +--> CSRF (for methods requiring verification)
  +--> authorization
  |
  +--> Blocked => 401, 302, or 403 depending on case
  |
  v
Spring MVC DispatcherServlet
  |
  v
@GetMapping / @PostMapping
  |
  v
Controller response body
```

You must test both **denial paths** and **allowed paths**. Testing only `GET /hello` with a mock user returning `200` does not prove anonymous callers are blocked. Testing only anonymous getting `401` does not prove valid users actually reach the controller.

## 12. Common Beginner Mistakes

### Mistake 1 — Failing to Distinguish Redirects from Authentication Errors

**Symptom:** Browser shows a login page while curl gets `401`, leading you to think security is "inconsistent."

**Explanation:** Spring Security's content negotiation and entry points can distinguish HTML/browser requests from service clients. Compare the exact same URL and method with and without `Accept`, inspecting `Location`/`WWW-Authenticate` headers to understand the behavior.

### Mistake 2 — Logging In and Assuming Endpoints Are Public

**Symptom:** `/health` shows `ok` in the browser, yet anonymous curl gets `401`.

**Explanation:** The browser holds a session cookie. Verify in an incognito window and with credential-free curl; in the baseline lab, `/health` is not public automatically.

### Mistake 3 — Copying Passwords from Documentation or Old Runs

**Symptom:** `curl -u user` always gets `401`.

**Explanation:** The default password can regenerate on every application startup. Use the exact value printed in **the current run's log**, never hardcoding guide values or old CI logs. Custom user providers change this behavior as well.

### Mistake 4 — Turning Off CSRF to "Fix" 403

**Symptom:** GET works, POST fails.

**Explanation:** POST undergoes CSRF checks independently of having a valid user. Use `MockMvc.with(csrf())` to prove the valid path; browser apps must integrate tokens properly.

### Mistake 5 — Using @WithMockUser and Claiming Password Authentication Works

**Symptom:** Tests stay green even when the production password encoder or token verifier is broken.

**Explanation:** Mock users are placed directly into the test `SecurityContext` without running real password checks. Add `httpBasic()`/form login/provider/JWT decoding tests if your product relies on those guarantees.

### Mistake 6 — Writing All Security Rules in One Shot

**Symptom:** After adding a custom chain, the login form disappears, 401 becomes 403, or endpoints outside `securityMatcher` leak through.

**Explanation:** A `SecurityFilterChain` bean replaces Boot's default web auto-configuration; you must declare policies and authentication mechanisms explicitly, with a catch-all fallback. Add rules incrementally and re-run the regression suite.

### Mistake 7 — Testing Too Tightly to Implementation

**Symptom:** Tests assert exact filter counts, internal class names, or log order; a minor patch breaks tests even when behavior is correct.

**Explanation:** For this lab, the contract is **statuses, meaningful headers, and responses**, plus allow/deny paths. Assert specific filter classes only in dedicated filter-architecture exercises.

### Mistake 8 — Using curl -L and Missing 302

**Symptom:** You only see the HTML login page with final status `200`, concluding `GET /hello` returns `200` anonymously.

**Explanation:** `-L` follows redirects; use `curl -i` without `-L` to see the initial response, or inspect hops with `-v` in a safe environment.

### Mistake 9 — Leaving Sensitive Data in Terminal History or Bug Reports

**Symptom:** Commands put plaintext passwords/tokens into shell history, DevTools screenshots expose cookies, or verbose logs are posted to issues.

**Explanation:** Use `curl -u user` to prompt for passwords instead of passing them inline. Sanitize logs/screenshots and use dummy data.

### Mistake 10 — Testing Only One User at a Time

**Symptom:** Alice can view her own data, yet can also view Bob's data simply by changing an ID.

**Explanation:** The baseline observes only auth + CSRF. Once real resources exist, build a multi-user/role/tenant/owner test matrix and enforce checks in services/repositories. `authenticated()` does not protect object ownership automatically.

## 13. Checklist Before Expanding Configuration

Capture each step as automated tests or technical notes:

- [ ] Confirmed the app uses Servlet/Spring MVC, along with exact dependencies and Spring Boot version.
- [ ] Identified default security signals and the generated user/password in the lab environment (or explained why if auto-config was replaced).
- [ ] Private browser: `GET /hello` redirects to login and returns expected content after valid login.
- [ ] Anonymous JSON curl: `401`; valid Basic curl: `200`; wrong password: rejected.
- [ ] Observed the difference between `Accept: text/html` and `Accept: application/json`; did not confuse redirect targets with initial statuses.
- [ ] POST without/with invalid CSRF token is blocked; POST with valid token and proper principal succeeds per policy.
- [ ] MockMvc runs anonymous/authenticated, CSRF, and header cases; test code does not depend on random passwords.
- [ ] Understood that `@WithMockUser` tests a simulated `SecurityContext`, not real providers/credentials.
- [ ] Created a before/after matrix if adding a `SecurityFilterChain`; know which new rule changes old expectations.
- [ ] Preserved unaffected regression tests when adding new rules.
- [ ] Plan HTTPS for real systems; never expose passwords/cookies/tokens in logs, history, or reports.
- [ ] Did not grant `permitAll` to every endpoint or disable CSRF just to avoid test failures.
- [ ] Ready to add owner/tenant/ACL tests once real user data exists, beyond URL access tests.

## 14. Self-Check Questions

**Question 1:** A browser visiting `/hello` sees a login page, while curl sending `Accept: application/json` gets 401. Is Spring Security applying two different authorization rules?

**Answer:** Not necessarily. Both require authentication. The entry point can pick a form redirect for browsers and an HTTP Basic challenge for service clients. Compare `Accept`, `Location`, and `WWW-Authenticate`.

**Question 2:** You called `GET /health` successfully after logging in. Can you declare `/health` public?

**Answer:** No. You must test without credentials or cookies; in Boot's baseline, that route still requires login. If the product intends it to be public, add an **explicit** `permitAll` rule and test it.

**Question 3:** Why does `POST /notes` with valid username/password still return 403?

**Answer:** CSRF protection applies to POST. In tests, use `user(...)` and `csrf()` to verify credentials/permissions independently from tokens; do not rush to disable CSRF.

**Question 4:** Does `@WithMockUser(username = "alice")` prove Alice can log in with a real password?

**Answer:** No. It creates a simulated authentication in the test. To verify passwords, test the provider/`httpBasic(...)`/form login against configured test users.

**Question 5:** Adding a `SecurityFilterChain` made the login page disappear. How do you fix it?

**Answer:** When defining a custom web security chain, explicitly declare the mechanisms you want such as `formLogin(Customizer.withDefaults())` and `httpBasic(Customizer.withDefaults())`, along with clear authorization rules. Re-run redirect/401 tests after the change.

**Question 6:** After adding `hasRole("ADMIN")`, curl with the default `user` gets 403. Is the server broken?

**Answer:** No. The default user lacks `ROLE_ADMIN`. Test with a mock admin to confirm the rule; if you need to test real login with role ADMIN, configure a matching test identity/provider and verify credentials.

## 15. Key Takeaways

1. **Measure defaults before expanding:** understand why endpoints ask for login, JSON requests get 401, and POSTs missing CSRF get 403.
2. **Browser, curl, and MockMvc answer three different questions:** user experience, raw HTTP protocol behavior, and repeatable security contract verification.
3. **Authentication, authorization, and CSRF are separate layers**; error statuses must be explained across the full processing chain.
4. **Every configuration change needs before/after tests.** When policy changes intentionally, update matching assertions while keeping regression tests for unchanged parts.
5. **Initialization security is not production security.** Continue designing identity providers, HTTPS, resource-level authorization, token/session lifecycles, negative testing, and monitoring once real data is handled.

## References

- [Spring Boot 3.5 — Spring Security auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [Spring Security — Hello Spring Security](https://docs.spring.io/spring-security/reference/6.5/servlet/getting-started.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — MockMvc Test Integration](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security — MockMvc WithMockUser/user()](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html)
- [Spring Security — MockMvc CSRF Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Security — Testing HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Boot 3.5.16 release, June 25 2026](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
