# Distinguishing Unit Tests, Integration Tests, and Real Browser Behavior

## 1. Three types of tests — three different kinds of evidence

In Spring Security, **a passing unit test does not prove login works**, a passing `MockMvc` integration test does not prove the browser handles cookies or forms properly, and a passing browser test does not prove every branch of service-level authorization policy is covered.

This lesson belongs to the **Testing** group and focuses on choosing the right test level for each security requirement:

- **Unit test:** tests a small function/class, such as a role mapper, validator, `AuthorizationManager`, or object-ownership check. Needs no HTTP socket or browser and runs in plain Java/JUnit. Proves **the rule under test** matches the given fixtures.
- **Integration test:** tests multiple components running together, such as `SecurityFilterChain`, `UserDetailsService`, password encoder, controller, CSRF, and endpoints. `MockMvc` uses mock Servlet requests/responses while running real security filters; `@SpringBootTest(RANDOM_PORT)` opens a real server and HTTP socket. Proves **wiring/pipeline behavior of the test context**.
- **Browser E2E / UI test:** launches Chromium, Firefox, or WebKit via Playwright/Selenium, interacts with the DOM, fills forms, follows redirects, stores/sends session cookies, and executes JavaScript and browser policies. Proves **the user journey in the chosen browser and environment**.

The three layers complement one another rather than a higher layer replacing everything below it. Browser tests are slower and more environment-sensitive, whereas unit tests are cheap, fast, and easy to debug yet cannot catch an HTML form missing its CSRF token or a misconfigured `SameSite` cookie.

### Evidence boundaries

| Question | Unit | Spring integration | Browser |
| --- | --- | --- | --- |
| Is the rule "Alice cannot read Bob's data" right? | Yes, at the policy function | Yes, if the endpoint invokes the policy | Can verify a journey |
| Are username/password really verified by the provider? | Only if testing the provider | Yes when running real auth filters and provider | Yes if the server does not mock authentication |
| Are anonymous callers redirected to login? | No | Can assert HTTP 302/`Location` | Can observe the real browser navigating |
| Does the login HTML render properly? | No | Can inspect HTML response | Can see/interact with the DOM |
| Does the form submit a valid CSRF token from real HTML? | No | `with(csrf())` only supplies a valid mock token | Yes if the test submits the form from the DOM |
| Does the browser persist cookies across reloads? | No | Only checks headers/sessions at the HTTP layer | Yes |
| JavaScript/CORS/SameSite behavior? | No | Can check server headers/policies | Yes with a real browser and origin |
| Are production TLS/proxy/IdP guaranteed right? | No | No if not connected to them | No if the browser runs only against localhost/stubs |

**Specifically:** `@WithMockUser` and `with(user("ghost"))` supply an authenticated principal for tests even if account `ghost` does not exist. That tests **authorization**, not passwords, JWT signatures, or OAuth2 login flows.

## 2. Test levels modeled along the request flow

```text
UNIT (no Spring needed)
  OwnerPolicy.canRead("alice","bob") -> false

MOCKMVC INTEGRATION (mock Servlet, real filters in test context)
  MockMvc request
    -> FilterChainProxy / SecurityFilterChain
    -> UsernamePasswordAuthenticationFilter / CsrfFilter
    -> AuthenticationManager -> UserDetailsService + PasswordEncoder
    -> AuthorizationFilter -> Controller -> OwnerPolicy
    -> MockHttpServletResponse

HTTP INTEGRATION (real server, HTTP client)
  TestRestTemplate / RestClient
    -> localhost:RANDOM_PORT -> embedded server -> security chain

BROWSER E2E (real browser engine)
  Chromium -> GET /dashboard
           -> redirect /login
           -> HTML login form + CSRF
           -> submit username/password
           -> session cookie, redirect
           -> render dashboard
           -> submit form POST + CSRF, reload, logout
```

Across all three layers, claim only behavior the test **actually exercises**. For example, if you use `@MockitoBean JwtDecoder` and stub it to always return a valid JWT, a Bearer integration test cannot verify token signatures even though it traverses part of the security chain.

## 3. End-to-end scenario and test matrix

Suppose the application has these requirements:

- `GET /` is open to anonymous callers.
- `GET /dashboard` is restricted to logged-in users.
- `POST /preferences` lets a logged-in user change their nickname and requires a CSRF token.
- `GET /documents/{owner}` allows only a principal matching `owner`.
- Demo account `alice` has password `correct-password`, while `ghost` does not exist.

| Requirement to verify | Primary layer | Negative cases required |
| --- | --- | --- |
| Owner rule | Unit | Alice reads Bob's document, missing principal |
| Dashboard endpoint protection | MockMvc | Anonymous redirects to login |
| Form authentication | MockMvc via real provider | Wrong password, non-existent username |
| CSRF filter | MockMvc | POST missing token gets 403 |
| Controller calls owner policy | MockMvc | Logged-in user still gets 403 for another owner |
| Login form renders and submits properly | Browser | Wrong password cannot enter dashboard |
| Session cookie works | Browser | Fresh browser context remains anonymous |
| CSRF field from real template | Browser | Form without token cannot complete update |
| Production HTTPS/cookies/cross-origin | Staging browser + config tests | Wrong `Secure`/`SameSite` cookies, CORS preflight failure |

A single browser test should not absorb the entire system's authorization logic; complex service branches belong in finer-grained unit/integration tests.

## 4. Java 17+ example project with all three test groups

The code below uses **Spring Boot 3.5.7, Spring Security 6.x, Spring MVC, Thymeleaf, JUnit 5, and Playwright Java 1.64.0**. Accounts and nickname state live in memory so the example is easy to repeat; they do not substitute for production databases, secrets, and clustered sessions.

Structure:

```text
security-test-levels/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/SecurityTestLevelsApplication.java
    │   ├── java/demo/OwnerPolicy.java
    │   └── resources/templates/dashboard.html
    └── test/java/demo/
        ├── OwnerPolicyTest.java
        ├── SecurityIntegrationTest.java
        └── BrowserFlowTest.java
```

### 4.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>security-test-levels</artifactId>
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
        <dependency>
            <groupId>com.microsoft.playwright</groupId>
            <artifactId>playwright</artifactId>
            <version>1.64.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Maven `<plugins>` contains **two complete `<plugin>` elements with opening and closing tags**. The exec plugin installs browser binaries; Playwright is in `test` scope, so the CLI command uses `exec.classpathScope=test`.

### 4.2. Unit under test: `src/main/java/demo/OwnerPolicy.java`

```java
package demo;

public final class OwnerPolicy {
    private OwnerPolicy() {}

    public static boolean canRead(String principal, String owner) {
        return principal != null && principal.equals(owner);
    }
}
```

This policy is intentionally simple to highlight the difference between **correct logic** and **correct wiring**. In real systems, compare stable user IDs, tenants, and DB-backed object permissions, never trusting client-supplied `owner` values.

### 4.3. Spring application: `src/main/java/demo/SecurityTestLevelsApplication.java`

```java
package demo;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class SecurityTestLevelsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityTestLevelsApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUser(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("correct-password"))
                        .roles("USER")
                        .build());
    }

    @Bean
    SecurityFilterChain securityChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/").permitAll()
                        .requestMatchers(
                                "/dashboard",
                                "/preferences",
                                "/documents/**").authenticated()
                        .anyRequest().denyAll())
                .formLogin(form -> form.permitAll())
                .logout(logout -> logout.permitAll())
                .build();
    }

    @Controller
    static class Pages {
        private final Map<String, String> nicknames =
                new ConcurrentHashMap<>();

        @GetMapping("/")
        @ResponseBody
        String publicPage() {
            return "Public home";
        }

        @GetMapping("/dashboard")
        String dashboard(Authentication auth, Model model) {
            String username = auth.getName();
            model.addAttribute("username", username);
            model.addAttribute(
                    "nickname",
                    nicknames.getOrDefault(username, "(none)"));
            return "dashboard";
        }

        @PostMapping("/preferences")
        String changeNickname(Authentication auth,
                              @RequestParam String nickname) {
            String cleaned = nickname.strip();
            if (cleaned.isBlank() || cleaned.length() > 50) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
            }
            nicknames.put(auth.getName(), cleaned);
            return "redirect:/dashboard";
        }

        @GetMapping("/documents/{owner}")
        @ResponseBody
        String document(Authentication auth,
                        @PathVariable String owner) {
            if (!OwnerPolicy.canRead(auth.getName(), owner)) {
                throw new ResponseStatusException(HttpStatus.FORBIDDEN);
            }
            return "Document for " + owner;
        }
    }
}
```

Explanation: `SecurityFilterChain` guards URLs, `formLogin` declares the standard login flow, and `logout` enables standard logout; **CSRF is not disabled**. Only user `alice` exists, with password hashed via `DelegatingPasswordEncoder`; wrong logins must traverse filters and the provider. `OwnerPolicy` is actually invoked by the controller when reading a document. Nicknames are stored in `ConcurrentHashMap` solely for observable state; production requires a DB and transactions.

### 4.4. Template: `src/main/resources/templates/dashboard.html`

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Security Test Dashboard</title>
</head>
<body>
    <h1 id="greeting" th:text="|Dashboard: ${username}|">
        Dashboard
    </h1>
    <p id="nickname" th:text="|Nickname: ${nickname}|">
        Nickname
    </p>

    <form id="preferences" method="post"
          th:action="@{/preferences}">
        <label for="nicknameInput">Nickname</label>
        <input id="nicknameInput" name="nickname"
               maxlength="50" required>
        <button id="save" type="submit">Save</button>
    </form>

    <form id="logoutForm" method="post" th:action="@{/logout}">
        <button id="logout" type="submit">Logout</button>
    </form>
</body>
</html>
```

`th:action` on POST forms integrates with `RequestDataValueProcessor` so Spring Security injects a hidden `_csrf` field when rendered. The browser test inspects the rendered DOM and submits the real form; `@Valid` or `with(csrf())` in separate tests cannot prove the template generated the token. `th:text` escapes text; never use `th:utext` on untrusted input.

## 5. Unit test: testing policy without Spring, HTTP, or a browser

`src/test/java/demo/OwnerPolicyTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class OwnerPolicyTest {

    @Test
    void ownerCanReadOwnDocument() {
        assertThat(OwnerPolicy.canRead("alice", "alice")).isTrue();
    }

    @Test
    void aliceCannotReadBobDocument() {
        assertThat(OwnerPolicy.canRead("alice", "bob")).isFalse();
    }

    @Test
    void missingIdentityCannotRead() {
        assertThat(OwnerPolicy.canRead(null, "alice")).isFalse();
    }
}
```

Unit tests prove `canRead` logic against selected inputs. They do not verify whether an endpoint calls the policy, create sessions, or check passwords or filters. As authorization logic grows, write unit tests for role/scope mappers, expiration validators, multi-tenant policies, object ownership, and account states including fail-closed cases.

## 6. Integration test: `MockMvc` running Spring Security filters

`src/test/java/demo/SecurityIntegrationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
class SecurityIntegrationTest {

    @Autowired MockMvc mvc;

    @Test
    void publicPageIs200() throws Exception {
        mvc.perform(get("/"))
                .andExpect(status().isOk())
                .andExpect(content().string("Public home"));
    }

    @Test
    void anonymousDashboardRedirectsToLogin() throws Exception {
        mvc.perform(get("/dashboard"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    @WithMockUser(username = "ghost", roles = "USER")
    void mockGhostMaySeeDashboard() throws Exception {
        mvc.perform(get("/dashboard"))
                .andExpect(status().isOk());
    }

    @Test
    void ownerIsAllowedButOtherUserDenied() throws Exception {
        mvc.perform(get("/documents/alice")
                        .with(user("alice").roles("USER")))
                .andExpect(status().isOk())
                .andExpect(content().string("Document for alice"));

        mvc.perform(get("/documents/bob")
                        .with(user("alice").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void realFormProviderAcceptsCorrectPassword() throws Exception {
        mvc.perform(formLogin()
                        .user("alice")
                        .password("correct-password"))
                .andExpect(authenticated().withUsername("alice"));
    }

    @Test
    void wrongPasswordRejected() throws Exception {
        mvc.perform(formLogin()
                        .user("alice")
                        .password("wrong-password"))
                .andExpect(unauthenticated());
    }

    @Test
    void unknownUserRejected() throws Exception {
        mvc.perform(formLogin()
                        .user("ghost")
                        .password("anything"))
                .andExpect(unauthenticated());
    }

    @Test
    void postWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/preferences")
                        .with(user("alice").roles("USER"))
                        .param("nickname", "Invalid"))
                .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfCanUpdate() throws Exception {
        mvc.perform(post("/preferences")
                        .with(user("alice").roles("USER"))
                        .with(csrf())
                        .param("nickname", "Valid"))
                .andExpect(status().is3xxRedirection());
    }
}
```

**What these tests prove and do not prove:**

- `@WithMockUser("ghost")` supplies a principal absent from the user store without running password validation. The 200 result only verifies the `authenticated` rule.
- `with(user("alice"))` attaches a per-request mock principal to test policy/CSRF; it does not check user existence.
- `formLogin()` constructs a login POST with a valid CSRF token; when real filters are wired in the Spring context, `AuthenticationManager`/provider/encoder check username and password. Wrong-password and unknown-user tests prove something `@WithMockUser` cannot.
- `with(csrf())` supplies a test token. It checks that the filter accepts tokens, **not that HTML forms render them**.
- `@AutoConfigureMockMvc(addFilters = true)` keeps filters enabled. Disabling filters or using `standaloneSetup` without `springSecurity()` can bypass protections.
- Even without opening an HTTP port, this is an **integration** test because the Spring context, controllers, filter chain, user store, and authorization work together.

## 7. Browser test: Playwright with a real HTTP server and Chromium

`src/test/java/demo/BrowserFlowTest.java`:

```java
package demo;

import com.microsoft.playwright.Browser;
import com.microsoft.playwright.BrowserContext;
import com.microsoft.playwright.BrowserType;
import com.microsoft.playwright.Page;
import com.microsoft.playwright.Playwright;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BrowserFlowTest {

    @LocalServerPort
    int port;

    @Test
    void browserFollowsLoginAndKeepsSession() {
        String base = "http://localhost:" + port;

        try (Playwright playwright = Playwright.create()) {
            Browser browser = playwright.chromium().launch(
                    new BrowserType.LaunchOptions().setHeadless(true));
            BrowserContext signedIn = browser.newContext();
            Page page = signedIn.newPage();

            page.navigate(base + "/dashboard");
            assertThat(page.url()).contains("/login");

            // Spring Security generates the default login form.
            page.locator("input[name='username']").fill("alice");
            page.locator("input[name='password']")
                    .fill("correct-password");
            page.locator("button[type='submit']").click();
            page.waitForURL("**/dashboard");

            assertThat(page.locator("#greeting").innerText())
                    .isEqualTo("Dashboard: alice");

            // Check hidden field generated by view integration.
            assertThat(
                    page.locator("#preferences input[name='_csrf']").count())
                    .isEqualTo(1);

            // Browser sends cookie and CSRF when submitting the real form.
            page.locator("#nicknameInput").fill("Browser verified");
            page.locator("#save").click();
            page.waitForURL("**/dashboard");
            assertThat(page.locator("#nickname").innerText())
                    .isEqualTo("Nickname: Browser verified");

            page.reload();
            assertThat(page.locator("#greeting").innerText())
                    .isEqualTo("Dashboard: alice");

            // Another context is not logged in yet.
            BrowserContext anonymous = browser.newContext();
            Page newcomer = anonymous.newPage();
            newcomer.navigate(base + "/dashboard");
            assertThat(newcomer.url()).contains("/login");

            anonymous.close();
            signedIn.close();
            browser.close();
        }
    }

    @Test
    void browserRejectsWrongPassword() {
        String base = "http://localhost:" + port;

        try (Playwright playwright = Playwright.create()) {
            Browser browser = playwright.chromium().launch(
                    new BrowserType.LaunchOptions().setHeadless(true));
            Page page = browser.newPage();

            page.navigate(base + "/login");
            page.locator("input[name='username']").fill("alice");
            page.locator("input[name='password']").fill("wrong");
            page.locator("button[type='submit']").click();
            page.waitForURL("**/login?error");

            assertThat(page.url()).contains("/login?error");
            browser.close();
        }
    }
}
```

This browser test verifies what `MockMvc` cannot reproduce on its own: real login DOM, form clicks, automatic redirects, browser session cookies, HTML view hidden CSRF fields, real-page form POSTs, and isolated browser contexts. It does not prove production TLS/proxy config or all browsers, since the test app runs on localhost HTTP with an in-memory user store.

## 8. Commands to build, install Chromium, and run tests

Requires Java 17+, Maven, and Playwright-compatible OS libraries. From the directory containing `pom.xml`:

```bash
mvn -q -DskipTests test-compile
mvn -q exec:java -Dexec.mainClass=com.microsoft.playwright.CLI -Dexec.args="install chromium" -Dexec.classpathScope=test
mvn -q test
mvn -q -DskipTests package
java -jar target/security-test-levels-0.0.1-SNAPSHOT.jar
```

The Chromium install step must run before browser tests and may require system dependencies in CI/Linux. If the binary is missing, `BrowserFlowTest` will fail at launch; that is an environment failure, not evidence of broken security logic.

Run individually:

```bash
mvn -q -Dtest=OwnerPolicyTest test
mvn -q -Dtest=SecurityIntegrationTest test
mvn -q -Dtest=BrowserFlowTest test
```

After `java -jar`, opening `http://localhost:8080/dashboard` redirects to `/login`. Use user `alice` / password `correct-password`; after login you see the dashboard and nickname form. Never use demo credentials or unencrypted HTTP in production.

## 9. HTTP integration tests with `RANDOM_PORT` are still not a browser

When you only need real statuses/headers/bodies, `TestRestTemplate` or an HTTP client with `@SpringBootTest(webEnvironment = RANDOM_PORT)` is often enough and lighter than Playwright:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpStatusExample {

    @Autowired TestRestTemplate client;

    @Test
    void publicEndpointServesHttp() {
        ResponseEntity<String> response =
                client.getForEntity("/", String.class);

        assertThat(response.getStatusCode())
                .isEqualTo(HttpStatus.OK);
        assertThat(response.getBody())
                .isEqualTo("Public home");
    }
}
```

This is a **fragment** (requiring imports and project context). It sends requests to the embedded server over an HTTP socket. However, the client does not render DOM, run JavaScript, or enforce browser cookie policies. When checking 302/`Location` redirects, know whether your HTTP client follows redirects automatically and configure it explicitly. With `RANDOM_PORT`, test threads and server threads differ: `@Transactional` on the test method does not automatically roll back transactions committed by server requests; clean up data intentionally.

## 10. Scenarios that genuinely need a browser test

### Form login and cookies

Browsers enforce `SameSite`, `Secure`, `HttpOnly`, `Domain`, `Path`, session cookies, redirects, and back navigation. `MockMvc` checks `Set-Cookie` and response status without simulating full browser rules. Use staging over HTTPS with real domains when testing `Secure`/`SameSite` cookies, reverse proxies, or cross-site redirects; localhost HTTP does not behave like production.

### CSRF from HTML or SPAs

`with(csrf())` verifies the filter accepts a test token; browser tests verify the form renders the token, DOM clicks work, and the client actually sends it. SPAs may send headers instead of hidden inputs. Never disable CSRF out of habit; identify whether the app uses cookies/sessions, Basic, or Bearer tokens and how browsers send credentials automatically.

### CORS and JavaScript

CORS is enforced by browsers; `curl` does not block responses by origin. Multi-origin browser tests catch OPTIONS preflights, credentialed cookies, allowed origins, and fetch errors. CORS is not an authorization mechanism—never fix it with `permitAll("/**")`. CSP, SPA routing, WebAuthn, and script bugs also typically surface only in browsers.

### OAuth2/OIDC and SSO

`oauth2Login()` or `oidcLogin()` post-processors create mock principals without testing `state`, `nonce`, redirect URIs, token endpoints, signatures, or real sessions. Browser tests against an IdP stub are useful for callbacks/redirects; staging against a real IdP offers higher integration confidence, provided dedicated test accounts are used. Never use production privileges just to run E2E tests.

### Object-level authorization

A frontend hiding the link to `/documents/bob` does not stop Alice from requesting it directly. Server-side unit/integration tests must prove 403/404 enforcement; browser tests supplement rather than replace object-level authorization tests.

## 11. JWT and WebFlux: keeping the same layered principle

**JWT Resource Server:** unit-test `JwtAuthenticationConverter`, claims → roles/scopes, and validators; integration-test Bearer requests carrying **signed** tokens through the real `BearerTokenAuthenticationFilter`/`JwtDecoder` for valid/invalid signatures, `iss`, `exp`, `nbf`, and `aud` when audience policy applies; browser-test SPAs/OIDC if relevant UI exists.

`with(jwt())` or `jwt()` helpers normally supply a `JwtAuthenticationToken` pre-populated with authorities, **without verifying signatures**. If `JwtDecoder` is mocked to always return valid, that integration test checks no cryptography. Distinguish statuses: bad token 401; valid token lacking authority 403; valid token with sufficient permissions 200 (per application policy).

**WebFlux/reactive:** replace Servlet `SecurityFilterChain` with `SecurityWebFilterChain`, using `WebTestClient` and `mockUser()`/`mockJwt()` for policies; a reactive client test still executes no browser DOM/JS. Fragment example (not standalone):

```java
client.mutateWith(mockUser("alice").roles("USER"))
        .get().uri("/dashboard")
        .exchange()
        .expectStatus().isOk();
```

It needs `mockUser` imported from `SecurityMockServerConfigurers` and a security-configured `WebTestClient`. It proves behavior with a mock principal without checking passwords.

## 12. A testing strategy that misses nothing without overspending

| Behavior group | Unit | Integration | Browser |
| --- | --- | --- | --- |
| Role/scope/tenant/owner policies | Many edge cases | Endpoint allow/deny | Representative journey |
| Passwords and account states | Provider/encoder where needed | Valid/wrong/locked user | Login success/failure |
| CSRF | Rarely needs pure unit | POST missing/invalid/valid token | Form render/submit |
| Session/login/logout | Handlers/policies | Session creation/invalidation | Reload/new context/logout |
| JWT | Claims/validators | Signed tokens and real decoder | SPA/SSO flow if present |
| CORS | Origin policy | Preflight/headers | Cross-origin fetch |
| UI | View-models | HTML/status/redirects | DOM/clicks/navigation |
| IDOR/BOLA | Ownership logic | User A reading B's ID is blocked | Can supplement with one journey |

For most changes, run unit tests continuously, integration suites in CI, and browser smoke tests on critical journeys. For high-risk features like payments or password changes, expand staging browser/SSO tests according to risk. Whenever a browser test catches a bug, add a lower-level regression test if reproducible to reduce flakiness.

**Avoid flaky tests:** isolate browser contexts and fixtures, avoid hardcoded sleeps, use stable locators and `page.waitForURL`, match browser versions to Playwright, and never run unisolated tests modifying the same account in parallel. When capturing CI screenshots/traces/logs, redact passwords, PII, bearer tokens, session cookies, and CSRF tokens.

**Name tests by evidence:** `ownerPolicyRejectsDifferentUser`, `wrongPasswordRejectedByFormProvider`, and `browserPreservesSessionAfterReload` beat `securityWorks`. Clearly report mocked dependencies to avoid overstating coverage.

## 13. Common mistakes in code reviews and testing

1. Using only `@WithMockUser` and concluding login works: checks no credentials.
2. Disabling filters to silence 403: tests may skip all of Spring Security.
3. Treating every `@WebMvcTest` as identical to production: may miss services/providers or use mocks.
4. Calling `MockMvc` a unit test merely because no port opens: ignores its integration nature.
5. Treating a `RANDOM_PORT` HTTP client as browser E2E: runs no DOM/JS/cookie engine.
6. Assuming passing `with(csrf())` proves HTML contains the token: the post-processor injects it directly.
7. Testing only the happy path, missing wrong passwords/bad CSRF/insufficient roles/other owners.
8. Using `jwt()` with mocked roles to claim JWT signatures and issuers were verified.
9. Letting localhost browser passes imply production `Secure` cookies and proxies are right.
10. Testing only UI button hiding instead of backend authorization.
11. Relying on test-thread `@Transactional` rollback when a `RANDOM_PORT` server writes to the DB.
12. Logging screenshots/traces containing real session cookies and credentials.
13. Making browser tests order-dependent or relying on fixed `Thread.sleep`, causing flakiness.
14. Passing browser tests against a fake IdP and claiming the production IdP is fine.
15. Skipping checks on 401/403/302, headers, cookies, bodies, or real state side effects.
16. Lacking negative tests for expired tokens, wrong issuer/audience, and insufficient roles.
17. Mocking `AuthenticationManager` to accept every password and calling it an authentication integration test.
18. Testing only URL authorization while skipping service/object/tenant authorization.

## 14. Practice questions

1. A `@WithMockUser(username="ghost",roles="ADMIN")` test gets 200, yet `ghost` does not exist in the DB. What did it prove?
2. Why is `with(user("alice"))` not equivalent to `formLogin().user("alice").password("correct-password")`?
3. Which behaviors can `MockMvc` verify accurately even without opening an HTTP socket?
4. Why does a browser test catch a broken form CSRF field that `post(...).with(csrf())` misses?
5. When should you use `@SpringBootTest(RANDOM_PORT)` + an HTTP client instead of Playwright?
6. When a user logs in successfully yet refreshing returns to login, what cookie/session issues should you suspect?
7. Does the `jwt()` helper verify signatures/issuers/audiences? List the additional tests required.
8. Why is omitting links to Bob's document in the frontend insufficient to stop Alice from GETting that path?
9. If `curl` calls an API successfully while the browser reports a CORS error, which layer reproduces it for real?
10. Does `@Transactional` on the test thread automatically roll back transactions committed by a `RANDOM_PORT` server?
11. Design a matrix of 3 unit, 5 integration, and 2 browser cases for an app with form login.
12. Does a browser test against an IdP stub prove production SSO works? Why or why not?

## 15. Official references

- [Spring Security — Servlet Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html)
- [Spring Security — Running as a User](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html)
- [Spring Security — Setting Up MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security — Testing Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html)
- [Spring Security — Testing CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Playwright Java — Installation](https://playwright.dev/java/docs/intro)
- [Playwright Java — Browser binaries](https://playwright.dev/java/docs/browsers)
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html)

**In summary:** unit tests ask **is the logic right**; integration tests ask **are Spring Security and the components wired properly**; browser E2E tests ask **can a user actually complete the flow in a browser**. Never treat a single 200 test or a mock principal as proof of end-to-end security.
