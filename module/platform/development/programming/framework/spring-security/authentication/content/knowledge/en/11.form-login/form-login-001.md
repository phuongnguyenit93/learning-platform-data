# Protected Resource Access Flow and Redirect to the Login Page

> **Context:** Spring Security – Authentication → **Form Login** on the Servlet stack (Spring MVC). This lesson follows a real access attempt: an unauthenticated user opens a protected page, Spring Security blocks access, saves the original URL (when allowed by policy), redirects to the login form, verifies username/password, establishes a session, and sends the browser back to the resource. It also distinguishes **302 redirect**, **401 Unauthorized**, **403 Forbidden**, `AuthenticationEntryPoint`, `ExceptionTranslationFilter`, `RequestCache`, and `SavedRequestAwareAuthenticationSuccessHandler`. The integration example uses **Java 17+, Spring Boot 3.5.7, Spring Security Servlet 6.5.x, Gradle, MockMvc**.

## 1. An End-to-End Request Story

Suppose the system has the following paths:

- `GET /public`: public, no login required.
- `GET /reports/42`: only users with the `READER` role can read it.
- `GET /admin`: only the `ADMIN` role can view it.
- `GET /login`: the login page.
- `POST /login`: submits username, password, and CSRF token for Spring Security verification.

An **unauthenticated** user types `http://localhost:8080/reports/42` into the browser. With standard form login, the result is typically:

```text
Browser                           Spring Security / App
   |                                       |
   | GET /reports/42                       |
   |-------------------------------------->|
   |                              AuthorizationFilter:
   |                              no suitable Authentication
   |                              -> AccessDeniedException
   |                              ExceptionTranslationFilter:
   |                              save request via RequestCache
   |                              call AuthenticationEntryPoint
   | 302 Location: /login                  |
   |<--------------------------------------|
   |                                       |
   | GET /login                            |
   |-------------------------------------->|
   | 200 HTML login form (+ CSRF token)    |
   |<--------------------------------------|
   |                                       |
   | POST /login username/password/CSRF    |
   |-------------------------------------->|
   |                              UsernamePasswordAuthenticationFilter
   |                              -> AuthenticationManager
   |                              -> DaoAuthenticationProvider
   |                              -> PasswordEncoder.matches(...)
   |                              -> SecurityContext/session per policy
   |                              -> AuthenticationSuccessHandler
   | 302 Location: /reports/42?continue    |
   |<--------------------------------------|
   |                                       |
   | GET /reports/42?continue              |
   |-------------------------------------->|
   |                              restore SecurityContext
   |                              verify READER role
   |                              RequestCacheAwareFilter handles
   |                              saved request if applicable
   | 200 report content                    |
   |<--------------------------------------|
```

**Key points to get right:**

1. The URL `/reports/42` never returned its content before the user was authorized. The **authorization filter** prevented the request from reaching the controller.
2. `ExceptionTranslationFilter` **does not verify the password itself**. It coordinates the response when authentication needs to start, via `AuthenticationEntryPoint`.
3. The `AuthenticationEntryPoint` for browser form login is usually `LoginUrlAuthenticationEntryPoint`, which issues an HTTP redirect to `/login`.
4. `RequestCache` can store the original request before the redirect, usually in the session via `HttpSessionRequestCache`.
5. `GET /login` and `POST /login` are two separate operations: GET displays the form; POST is handled by the authentication filter.
6. After a successful login, `SavedRequestAwareAuthenticationSuccessHandler` can choose the **saved address** as the redirect target. It does not execute the report endpoint directly inside the login POST itself.
7. **The browser issues a new GET** to the redirected URL; Spring Security checks the session and permissions again for that new request.
8. `?continue` is a detail of the request-cache optimization in Spring Security 6 when using the default `HttpSessionRequestCache`; the exact URL depends on configuration/version.
9. The session cookie must be sent back by the browser and the session policy must allow saving/restoring `SecurityContext`. Without a cookie or when using a stateless chain, you cannot assume the same outcome as in the diagram.
10. Logging in successfully does not automatically grant all permissions. The `READER` role still cannot access `/admin`.

## 2. How Do Authentication and Authorization Differ?

- **Authentication:** "Who are you?" For example, `UsernamePasswordAuthenticationFilter` receives username/password and `AuthenticationManager` verifies them, returning an authenticated `Authentication`.
- **Authorization:** "Are you allowed to read this resource?" For example, `AuthorizationFilter` applies the `hasRole("READER")` rule for `/reports/**`.
- **Security filter chain exception handling:** "If requirements are not met, what HTTP response should be returned?" For example, an anonymous user is sent to login, while an authenticated user lacking a role usually receives 403.

Some common outcomes:

| Scenario | With default browser form login | Meaning |
| --- | --- | --- |
| Anonymous accesses `/public` | 200 | Public path |
| Anonymous accesses `/reports/42` | **302 → /login** | Authentication required before reading |
| Anonymous GET `/login` | 200 | Login page is publicly accessible |
| Wrong username/password on POST `/login` | **302 → /login?error** | Authentication failure; no new session granted |
| Valid login, with saved request | **302 → original URL** | Success handler chooses target |
| Valid login, without saved request | **302 → /home** in example | Uses configured default success URL |
| User `ROLE_READER` accesses `/reports/42` | 200 | Permitted |
| User `ROLE_READER` accesses `/admin` | **403** | Authenticated but insufficient privileges |
| API client without token and 401 entry point | **401** | API requires credentials; no HTML redirect |
| POST request missing CSRF token | **403** with CSRF enabled | May be blocked before the authentication filter |

**Do not equate HTTP 302 with successful authentication.** The redirect from `/reports/42` to `/login` happens because **the user is unauthenticated**, whereas the redirect from `POST /login` to the target page happens after a successful authentication. Both use a 3xx status code, but they have different meanings.

**Do not equate 403 with a wrong password.** If an account has `ROLE_READER` but needs `ROLE_ADMIN`, repeating login with the right password does not grant a new role. Obtaining permissions must follow the server-controlled authorization policy.

## 3. How Does the Spring Security Filter Chain Process a Request?

In a Servlet application, `DelegatingFilterProxy` routes the request into `FilterChainProxy`. `FilterChainProxy` selects the **first `SecurityFilterChain` that matches the request** and runs the corresponding filters.

A simplified processing path:

```text
HTTP GET /reports/42
    |
    v
FilterChainProxy / SecurityFilterChain
    |
    +-- SecurityContextHolderFilter
    |       reads SecurityContext from SecurityContextRepository
    |
    +-- Authentication filters
    |       form-login filter only handles matching URL/method
    |
    +-- AnonymousAuthenticationFilter
    |       if no identity, may set anonymous token
    |
    +-- ExceptionTranslationFilter
    |       wraps the rest of the chain to catch security exceptions
    |
    +-- AuthorizationFilter
            hasRole("READER") rule
            |
            +-- GRANTED -> controller /reports/42
            |
            +-- DENIED  -> AccessDeniedException
                             |
                             v
                         ExceptionTranslationFilter
                         -> entry point or access denied handler
```

The diagram illustrates roles, not a guarantee that every application has the exact same filters or order. Custom filters, multiple chains, and Spring Security configuration can change the pipeline. When debugging, inspect the actual `FilterChainProxy` instead of guessing.

### 3.1. What Does AuthorizationFilter Do?

`AuthorizationFilter` is responsible for enforcing `AuthorizationManager`/authorization rules. If a request does not satisfy the requirements, it can throw `AccessDeniedException`.

Example:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public").permitAll()
        .requestMatchers("/reports/**").hasRole("READER")
        .requestMatchers("/admin").hasRole("ADMIN")
        .anyRequest().authenticated());
```

This is a **snippet inside a `SecurityFilterChain`**, not a complete login configuration. These rules describe permissions; they do not choose the login page by themselves.

- `hasRole("READER")` looks for the `ROLE_READER` authority under Spring Security's default convention.
- `hasAuthority("documents:read")` checks the exact required authority.
- `permitAll()` allows access without requiring authentication.
- `authenticated()` requires an authenticated principal but **does not implicitly** require a specific role.
- `denyAll()` blocks requests that are not permitted by an explicit allowlist.

### 3.2. ExceptionTranslationFilter Converts "Security Exception → HTTP Response"

`ExceptionTranslationFilter` catches and handles security exceptions thrown by the portion of the filter chain it wraps. Two main paths:

1. `AuthenticationException` or an insufficiently authenticated user when denied → **starts authentication** via `AuthenticationEntryPoint`.
2. An authenticated user encountering `AccessDeniedException` due to missing permissions → delegates to `AccessDeniedHandler`; by default this usually returns **403 Forbidden**.

Pseudo-flow:

```text
Authorization/security exception
          |
          v
ExceptionTranslationFilter
          |
          +-- needs authentication?
          |      |
          |      +-- clear context if appropriate
          |      +-- RequestCache.saveRequest(...) per policy
          |      +-- AuthenticationEntryPoint.commence(...)
          |             -> 302 /login (form)
          |             -> 401 (API/Basic/Bearer depending on entry point)
          |
          +-- authenticated but lacks authority?
                 |
                 +-- AccessDeniedHandler.handle(...)
                        -> 403 or customized response
```

`ExceptionTranslationFilter` does not implement business authorization itself, nor does it turn every Java exception into a redirect. It handles **the corresponding security exceptions within the security chain**. Exceptions thrown by controllers outside the security processing contract may go through different error handling.

## 4. AuthenticationEntryPoint and LoginUrlAuthenticationEntryPoint

`AuthenticationEntryPoint` is the interface representing **how to prompt the client to begin authentication**:

```java
public interface AuthenticationEntryPoint {
    void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException authException)
            throws IOException, ServletException;
}
```

This is the **API signature for illustration**; you do not need to redeclare this interface in your project.

Common entry points:

| Entry point | Behavior | Suitable for |
| --- | --- | --- |
| `LoginUrlAuthenticationEntryPoint` | HTTP redirect to login page | Browser form login |
| `BasicAuthenticationEntryPoint` | 401 + `WWW-Authenticate: Basic ...` | HTTP Basic |
| `BearerTokenAuthenticationEntryPoint` | 401 and Bearer challenge | OAuth2 Resource Server |
| `HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)` | Returns status 401 | API clients expecting JSON/status, not HTML redirect |
| `DelegatingAuthenticationEntryPoint` | Selects entry point by request matcher | Systems serving multiple client types |

### 4.1. Who Decides the /login URL?

Standard `formLogin(...)` configuration registers an entry point for browsers, usually `LoginUrlAuthenticationEntryPoint`. If no custom login page is specified, Spring Security can generate a default `GET /login` page.

```java
http.formLogin(Customizer.withDefaults());
```

This is a snippet and requires importing `org.springframework.security.config.Customizer`. When running a Spring Boot application with web/security starters and an appropriate chain, Spring Security can automatically generate the login page and handle `POST /login`.

**You do not need to write a `GET /login` controller** if you use the auto-generated page. However, if you configure a custom login page, **your application must provide the controller/view that returns HTML**.

### 4.2. The Entry Point Is Not the Filter That Handles POST /login

`LoginUrlAuthenticationEntryPoint` only **directs the client to the login URL**. It does not validate form credentials.

`UsernamePasswordAuthenticationFilter` is what receives `POST /login` in the standard configuration, creates an unauthenticated `UsernamePasswordAuthenticationToken`, and calls `AuthenticationManager`. Then the provider and password encoder verify the credentials.

If you write a `@PostMapping("/login")` controller while standard form login is enabled, the authentication filter will typically **intercept POST /login before the controller**. Do not mix the two mechanisms or register two filters handling the same path.

## 5. How Does RequestCache Preserve the Original Destination?

### 5.1. Why Save the Original Request?

Without saving it, a user opening `/reports/42` would be redirected to login and after signing in might always be sent to `/home`, losing their original context.

`RequestCache` solves this UX problem:

- Saves information about the request that required authentication.
- After successful authentication, the success handler can retrieve the `SavedRequest` to choose the destination.
- When the browser returns to the saved URL, `RequestCacheAwareFilter` can retrieve/reconstruct supported parts of the saved request via a wrapper.

Key components:

| Component | Responsibility |
| --- | --- |
| `RequestCache` | Contract for saving, retrieving, removing, and matching requests |
| `HttpSessionRequestCache` | Common implementation storing `DefaultSavedRequest` in the session |
| `DefaultSavedRequest` | Metadata snapshot needed for redirect/request reconstruction, not an indefinitely live `HttpServletRequest` |
| `ExceptionTranslationFilter` | Calls `saveRequest(...)` when initiating authentication if policy allows |
| `SavedRequestAwareAuthenticationSuccessHandler` | Prefers the saved URL upon login success, depending on options |
| `RequestCacheAwareFilter` | Matches the returning HTTP request against the saved request and wraps it |
| `NullRequestCache` | Does not save requests; useful for stateless APIs |

### 5.2. A Session Used for RequestCache Is Not the Same as an Authenticated Session

When an anonymous user accesses `/reports/42`, `HttpSessionRequestCache` may create a session **solely to hold the saved request**. At that point, the user is still unauthenticated.

```text
Session after anonymous protected GET:
    SPRING_SECURITY_SAVED_REQUEST = DefaultSavedRequest(...)
    no authenticated SecurityContext for "mai" yet

Session after successful POST /login:
    SecurityContext contains authenticated principal "mai"
    saved request may still exist until the redirect request matches
```

Therefore, **having a `JSESSIONID` before logging in does not prove the user is logged in**. Creating a session for the request cache and creating one for an authenticated security context are two different things.

Similarly, session fixation protection may change the session ID on login; use the cookie received by the browser from the server and let the framework manage the session lifecycle.

### 5.3. Spring Security 6 Detail: The continue Parameter

Spring Security 6 optimizes `HttpSessionRequestCache`: instead of looking up the cache on every request, by default the matching mechanism may only query the saved request when the incoming request contains the **`continue`** parameter.

Example where the original request has no query string:

```text
GET /reports/42 (anonymous)
  -> 302 /login
POST /login (valid credentials)
  -> 302 http://localhost:8080/reports/42?continue
GET /reports/42?continue (browser follows redirect)
  -> RequestCacheAwareFilter conditionally checks saved request
  -> controller returns report if user has permission
```

The `?continue` parameter is a **technical signal for the request cache**, not an authentication token or permission. Simply appending `?continue` to a URL **cannot** bypass security; `AuthorizationFilter` still requires a valid session/authentication and authority.

If the original URL already had a query string, the cache may append `&continue`. When writing tests or handling navigation, **do not hardcode that Location after login must equal the exact string `/reports/42` without a query** across all versions. Check your cache configuration and actual URLs.

Depending on version/override, `HttpSessionRequestCache.setMatchingRequestParameterName(...)` can change this behavior. Do not strip the parameter via JavaScript and blame Spring Security for "not restoring the request". Still, application controllers should not rely on `continue` to make authorization decisions.

### 5.4. SavedRequest Is Not "Arbitrary Replay of Every POST"

The request cache is primarily designed for **browser GET navigation** to a resource requiring login. After login, the browser receives a 302 and issues a new request to the destination. This is **not** a guarantee that Spring Security will re-execute a pre-login POST/PUT with the exact same body, tokens, file uploads, and side effects.

- For write operations, you should generally return an error requiring login first, then have the client actively resubmit under the authenticated identity and a fresh valid CSRF token.
- Do not automatically replay payment or data-deletion transactions just because a `SavedRequest` exists.
- You can restrict the request cache to GET/safe navigation by policy.
- For highly sensitive endpoints, re-verify intent/action after login instead of executing implicitly.
- Do not store passwords, tokens, or sensitive request bodies in a custom request cache.

### 5.5. One Session Can Be Blocked Multiple Times

In standard session cache configurations, one saved-request slot can be **overwritten** by another protected request before the user logs in. Thus, there is no guarantee of always returning to "the very first URL the user opened".

For example, if an anonymous user visits `/reports/42` and then `/reports/99`, the saved target may become the later request depending on policy. If a product needs a shopping cart or multi-step workflow, manage workflow state separately rather than treating `RequestCache` as long-term job storage.

## 6. Form Login: GET Login Page, POST Authentication, Success/Failure Handlers

### 6.1. GET /login

When an anonymous user is redirected, the browser sends a GET to the login page. If no custom page is declared, Spring Security can generate default HTML via its login page generating filter, including the form and CSRF token matching the configuration.

If you specify a custom `.loginPage("/signin")`:

```java
http.formLogin(form -> form
        .loginPage("/signin")
        .loginProcessingUrl("/signin")
        .failureUrl("/signin?error")
        .defaultSuccessUrl("/home", false)
        .permitAll());
```

This is a **configuration snippet**; you need a controller/view for `GET /signin`, and must ensure the login page and its assets are accessible. Without a custom page, `/signin` may return 404; without `permitAll`, it easily causes a redirect loop.

### 6.2. POST /login

The default form sends parameter names `username` and `password` (unless configured otherwise) to the login processing URL, typically `POST /login`.

`UsernamePasswordAuthenticationFilter`:

1. Reads username/password and creates an unauthenticated token.
2. May attach `WebAuthenticationDetails` from the request to the token.
3. Calls `AuthenticationManager.authenticate(...)`.
4. A provider, such as `DaoAuthenticationProvider`, loads `UserDetails` and checks `PasswordEncoder.matches(...)`.
5. If authentication succeeds, runs the appropriate `SessionAuthenticationStrategy`, sets/saves `SecurityContext` via framework mechanisms, and invokes the success handler.
6. If authentication fails, clears appropriate security state and invokes the failure handler; form login typically redirects to `/login?error`.

**In Spring Security 6, `SecurityContextHolderFilter` uses explicit save.** The standard authentication filter already includes logic to save the context in the success flow. However, if you write a manual login controller that only calls `SecurityContextHolder.setContext(...)`, you cannot assume subsequent requests will have an authenticated session; you must save via `SecurityContextRepository.saveContext(...)` and invoke the necessary session strategy.

### 6.3. SavedRequestAwareAuthenticationSuccessHandler

By default, form login typically uses a success handler that supports saved requests. Key rules:

1. If `alwaysUseDefaultTargetUrl == true`, use the default target and ignore the saved request.
2. If a `targetUrlParameter` is configured and present, the handler may use that value (must validate redirect safety).
3. If a saved request exists, redirect to the saved URL.
4. If no saved request exists, fall back to the configured default target URL.

Example:

```java
http.formLogin(form -> form
        .defaultSuccessUrl("/home", false)
        .permitAll());
```

- `false`: **does not force** `/home` unconditionally; the saved request takes priority when present.
- `true`: always redirects to `/home` even if a protected URL was saved before login.
- In the example in Section 8, `false` is used to test redirecting back to `/reports/42`.
- Do not build a custom `successHandler` if you only need standard behavior, because replacing the success handler improperly can accidentally drop saved-request logic.

### 6.4. AuthenticationFailureHandler

A wrong password or an account not permitted to authenticate leads to the failure branch. With default form login, redirecting to `/login?error` is the common behavior.

**Distinguish two redirects:**

```text
Anonymous GET /reports/42:
    ExceptionTranslationFilter
    -> AuthenticationEntryPoint
    -> 302 /login

Wrong POST /login:
    UsernamePasswordAuthenticationFilter
    -> AuthenticationManager rejects
    -> AuthenticationFailureHandler
    -> 302 /login?error
```

`ExceptionTranslationFilter` is not the direct handler for every wrong password attempt in form login; that error is typically caught by the authentication filter and passed to `AuthenticationFailureHandler`.

Do not log raw passwords in the failure handler; return a helpful message while avoiding leaking account existence or locked status without appropriate trust.

## 7. Runnable Java 17+ Example with Spring Boot 3.5

The demo intentionally keeps **standard form login**, without writing a custom login filter/controller, because the focus is on the redirect chain and saved request.

Endpoints:

| Method/path | Rule | Response when valid |
| --- | --- | --- |
| `GET /public` | `permitAll()` | `public` |
| `GET /home` | `authenticated()` | `home:mai` |
| `GET /reports/{id}` | `hasRole("READER")` | `report=42;user=mai` |
| `GET /admin` | `hasRole("ADMIN")` | `admin:...` |
| `GET /login` | Default form login | Login HTML |
| `POST /login` | Spring Security form filter | Redirect or failure |

There is one demo account `mai / demo-pass-123` holding only `ROLE_READER`. **Do not use sample credentials in production**.

### 7.1. Project Structure

```text
protected-page-login-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/loginflow/LoginFlowApplication.java
    └── test/java/demo/loginflow/LoginFlowApplicationTests.java
```

`settings.gradle`:

```groovy
rootProject.name = 'protected-page-login-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
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
```

Spring Boot manages compatible Spring Security versions via its BOM. When troubleshooting version issues, inspect the actual project dependency tree; do not manually force all `spring-security-*` dependencies to a patch number outside the BOM.

### 7.2. Complete Application Source Code

Create `src/main/java/demo/loginflow/LoginFlowApplication.java`:

```java
package demo.loginflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LoginFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginFlowApplication.class, args);
    }
}

@Configuration
class LoginFlowSecurity {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("mai")
                        .password(encoder.encode("demo-pass-123"))
                        .roles("READER")
                        .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/login").permitAll()
                .requestMatchers("/reports/**").hasRole("READER")
                .requestMatchers("/admin").hasRole("ADMIN")
                .requestMatchers("/home").authenticated()
                .anyRequest().denyAll());

        // GET /login: form page generated by Spring Security.
        // POST /login: handled by UsernamePasswordAuthenticationFilter.
        // "false": do not force default URL if a saved request exists.
        http.formLogin(form -> form
                .defaultSuccessUrl("/home", false)
                .permitAll());

        // Keep CSRF enabled by default; do not disable it.
        // Spring Security's session/request cache is used.
        return http.build();
    }
}

@RestController
class LoginFlowController {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/home")
    String home(Authentication auth) {
        return "home:" + auth.getName();
    }

    @GetMapping("/reports/{id}")
    String report(
            @PathVariable("id") long id,
            Authentication auth) {
        return "report=" + id + ";user=" + auth.getName();
    }

    @GetMapping("/admin")
    String admin(Authentication auth) {
        return "admin:" + auth.getName();
    }
}
```

**Configuration explanation:**

- `/reports/**` requires `ROLE_READER`, enforced by authorization rules; `ROLE_READER` is granted by a trusted user source.
- `/admin` requires `ROLE_ADMIN`; account `mai` does not have this role.
- `/home` only requires being authenticated and serves as the **default success target** if there is no saved request.
- `.formLogin(...)` registers the entry point redirecting to the login page, the login filter, handlers, and the default page per Spring Security's mechanism.
- `.permitAll()` in the form-login config makes the login page and processing/failure URLs publicly accessible as required by the flow. The `/login` rule is also declared explicitly for readability.
- There is no custom POST login controller, avoiding conflicts with `UsernamePasswordAuthenticationFilter`.
- For an unauthenticated browser, `GET /reports/42` does not enter `LoginFlowController.report`. Only after valid authentication/authorization is the controller invoked.
- Because neither `SecurityContextRepository` nor `RequestCache` is overridden, the demo uses default behavior compatible with Spring Security 6.
- Integration tests do not start with `@WithMockUser` because they need to exercise the **real redirect/login/request cache flow**.

### 7.3. MockMvc Tests: Four Important Branches

Create `src/test/java/demo/loginflow/LoginFlowApplicationTests.java`:

```java
package demo.loginflow;

import jakarta.servlet.http.HttpSession;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.web.savedrequest.HttpSessionRequestCache;
import org.springframework.security.web.savedrequest.SavedRequest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginFlowApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousProtectedGetRedirectsToLoginAndIsSaved()
            throws Exception {

        MvcResult first = mvc.perform(get("/reports/42"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        String loginRedirect = first.getResponse().getRedirectedUrl();
        assertNotNull(loginRedirect);
        assertTrue(loginRedirect.endsWith("/login"));

        HttpSession rawSession = first.getRequest().getSession(false);
        assertNotNull(rawSession);
        MockHttpSession session = (MockHttpSession) rawSession;

        SavedRequest saved = new HttpSessionRequestCache()
                .getRequest(first.getRequest(), first.getResponse());
        assertNotNull(saved);
        assertTrue(saved.getRedirectUrl().contains("/reports/42"));

        MvcResult login = mvc.perform(post("/login")
                        .session(session)
                        .with(csrf())
                        .param("username", "mai")
                        .param("password", "demo-pass-123"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        String target = login.getResponse().getRedirectedUrl();
        assertNotNull(target);
        assertTrue(target.contains("/reports/42"));

        // Browser performs a GET to the target URL with the same session.
        // In Spring Security 6, "continue" may appear
        // in Location for the request cache to match.
        mvc.perform(get("/reports/42?continue").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("report=42;user=mai"));
    }

    @Test
    void loginWithoutSavedRequestUsesDefaultTarget()
            throws Exception {

        MockHttpSession session = new MockHttpSession();

        MvcResult login = mvc.perform(post("/login")
                        .session(session)
                        .with(csrf())
                        .param("username", "mai")
                        .param("password", "demo-pass-123"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        String url = login.getResponse().getRedirectedUrl();
        assertNotNull(url);
        assertTrue(url.endsWith("/home"));

        mvc.perform(get("/home").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("home:mai"));
    }

    @Test
    void authenticatedReaderGets403ForAdminOnly()
            throws Exception {

        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                        .session(session)
                        .with(csrf())
                        .param("username", "mai")
                        .param("password", "demo-pass-123"))
                .andExpect(status().is3xxRedirection());

        mvc.perform(get("/admin").session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void wrongPasswordReturnsToLoginError()
            throws Exception {

        MockHttpSession session = new MockHttpSession();

        MvcResult result = mvc.perform(post("/login")
                        .session(session)
                        .with(csrf())
                        .param("username", "mai")
                        .param("password", "wrong-password"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        String url = result.getResponse().getRedirectedUrl();
        assertNotNull(url);
        assertTrue(url.contains("/login?error"));

        // Wrong password does not create a successful Authentication.
        mvc.perform(get("/home").session(session))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void publicPageAndLoginPageAreReachable() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));

        mvc.perform(get("/login"))
                .andExpect(status().isOk());
    }

    @Test
    void loginPostRequiresCsrf() throws Exception {
        mvc.perform(post("/login")
                        .param("username", "mai")
                        .param("password", "demo-pass-123"))
                .andExpect(status().isForbidden());
    }
}
```

Run:

```bash
gradle test
```

With the Gradle Wrapper, use `./gradlew test` on macOS/Linux or `gradlew.bat test` on Windows. Run the web app:

```bash
gradle bootRun
```

Then open `http://localhost:8080/reports/42` in your browser. The browser will be redirected to the login page; sign in with the demo account and observe the browser returning to the report.

**These assertions are constructed from the official flow and the configuration above; this lesson does not claim to have executed the tests.** In your project environment, if there is another security chain, reverse proxy, request cache override, or different session cookie policy, the tests must reflect the corresponding behavior.

### 7.4. Reading Test Results

| Test | Expectation |
| --- | --- |
| `anonymousProtectedGetRedirectsToLoginAndIsSaved` | Protected GET 302 /login; saved request exists; valid login redirects to original URL; follow-up GET 200 |
| `loginWithoutSavedRequestUsesDefaultTarget` | Valid login without saved request → 302 /home; GET /home 200 |
| `authenticatedReaderGets403ForAdminOnly` | Mai is authenticated but lacks ROLE_ADMIN → 403, **not** login redirect |
| `wrongPasswordReturnsToLoginError` | POST wrong password → 302 /login?error; no authenticated session created |
| `publicPageAndLoginPageAreReachable` | GET /public and GET /login both return 200 |
| `loginPostRequiresCsrf` | POST /login without CSRF token → 403 |

**Why reuse a single `MockHttpSession` across multiple requests?** Both the saved request and the authenticated context may live in the session. If each `mvc.perform(...)` uses a fresh session, subsequent steps will not find the saved state. In a real browser, the `JSESSIONID` cookie bridges HTTP requests; in tests, `.session(session)` simulates that.

**Why check the URL with `contains("/reports/42")`?** Because by default Spring Security 6 may append `?continue` and construct an absolute redirect URL using the server scheme/host. Assertions should not assume every redirect implementation returns a bare path with no query string.

## 8. What Happens When There Is No Saved Request?

If a user opens `/login` directly and signs in without a saved protected request, the success handler needs a fallback target. With:

```java
.formLogin(form -> form
        .defaultSuccessUrl("/home", false))
```

...the fallback destination is `/home`. If you use `.defaultSuccessUrl("/home", true)`, the default target always takes precedence and any saved request may be discarded.

**Mistakes that hurt UX:**

- Using `alwaysUseDefaultTargetUrl(true)` and still expecting users to return to the original URL.
- Configuring a custom `AuthenticationSuccessHandler` that returns JSON without handling saved URLs for browsers.
- Storing the destination only in a client-submitted hidden field `returnUrl` without validation, causing an **open redirect**.
- Disabling RequestCache for stateless APIs while sharing the same chain with browser form login and expecting saved requests to work.

If you need role-based navigation, define an explicit priority order among saved request, default URL, and role-based landing page. Do not force every admin user to `/admin` if they just opened another valid resource.

## 9. 401, 403, 302, and API Clients: Choosing an Entry Point by Use Case

A browser loading HTML typically expects **302 → login page**. However, SPAs using fetch/AJAX, mobile clients, and backend APIs usually expect **401** or an error JSON payload rather than receiving an HTML login page after redirects.

Stateless token API example:

```text
GET /api/reports/42
Authorization: (none)

HTTP/1.1 401 Unauthorized
Content-Type: application/json

{"error":"authentication_required"}
```

This is an **illustrative HTTP example**; the JSON payload depends on your application's API—Spring Security does not automatically generate that exact JSON in every configuration.

An API chain can be configured separately (this snippet requires imports and belongs in a multi-chain app):

```java
@Bean
@Order(1)
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
        .exceptionHandling(ex -> ex
                .authenticationEntryPoint(
                        new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
        .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .requestCache(cache -> cache
                .requestCache(new NullRequestCache()));

    // Decide CSRF only based on how the API issues/transports credentials:
    // bearer-only stateless and browser cookie auth have different threat models.
    return http.build();
}
```

This is **not** a complete token API system: you still need real bearer token authentication/configuration, 403 handling, and JSON responses if desired. If the application also has browser login, add a second chain for web with appropriate matchers/`@Order`. Do not disable CSRF globally just to avoid sending tokens from browsers.

**Conclusion:** `ExceptionTranslationFilter` can invoke an entry point returning 302 or 401 depending on the security chain/client. It is not true that "every unauthenticated request gets redirected to /login".

### Insufficient Permissions After Login

If a valid `Authentication` exists but lacks the required authority:

```text
GET /admin
Cookie: JSESSIONID=<valid>

AuthorizationFilter: hasRole("ADMIN") denies
ExceptionTranslationFilter: user is authenticated
AccessDeniedHandler: HTTP 403 Forbidden
```

In real systems, never print actual cookies into logs or documentation. If an unauthenticated user also hits `/admin`, the form-login entry point may still redirect to `/login`, because **authentication** is needed before evaluating permissions.

## 10. Custom Login Page, Error Page, and Redirect Loops

If you need a custom UI at `/signin`:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/signin", "/assets/**").permitAll()
        .anyRequest().authenticated())
    .formLogin(form -> form
        .loginPage("/signin")
        .loginProcessingUrl("/signin")
        .failureUrl("/signin?error")
        .defaultSuccessUrl("/home", false)
        .permitAll());
```

This is a snippet and requires a **GET /signin controller** and an actual template/page. `POST /signin` is handled by the Spring Security login filter per configuration. Render the CSRF token in the form and use `name="username"`/`name="password"`, or adjust parameter names in the config accordingly.

### Typical Errors

**Error A: /signin is protected.** An anonymous request hits a protected resource, redirects to `/signin`, and `/signin` also requires authentication → redirect loop. You need `permitAll()` for the login page and the assets required to render it.

**Error B: form action differs from loginProcessingUrl.** The form POSTs to `/signin` while the filter expects POST `/login` → request is mishandled or hits no handler. Synchronize the form action and config.

**Error C: custom form lacks a CSRF token.** Spring Security blocks the POST with 403 before checking the password. This does not mean the password is wrong.

**Error D: security chain matcher does not cover the login URL.** If a chain only matches `/portal/**` while the login page is at `/signin`, login requests may not pass through the expected chain. Check `FilterChainProxy` and chain ordering.

**Error E: custom success handler forgets saved request.** Valid login always goes to `/home`; that is a consequence of handler logic, not RequestCache "breaking" by itself.

**Error F: custom login page allows unvalidated external redirects.** Avoid using an arbitrary `returnUrl` or client-supplied `Location` header without an allowlist/local-path policy. Protect sessions/cookies and prevent open redirects.

## 11. Security Boundaries to Verify

### 11.1. CSRF and Form Login

For cookie/session-based browser authentication, CSRF protection is a critical defense layer. The demo **keeps CSRF enabled**:

- The login page GET normally includes a CSRF token in the form rendered by the framework.
- POST `/login` in MockMvc tests uses `.with(csrf())`.
- POST without a token returns 403.
- Do not add `csrf(csrf -> csrf.disable())` to a browser chain just to submit forms via cURL more easily.

Even though there is no authenticated principal prior to login, **login CSRF** remains a risk: an attacker could force a victim to log into an attacker-controlled account, attributing the victim's actions to the wrong account.

### 11.2. Session Fixation Protection

Spring Security applies an appropriate `SessionAuthenticationStrategy` on login success. For Servlet sessions, session fixation protection typically changes the session ID. The saved request and authenticated context must persist properly across ID/session migration as managed by the framework.

**Do not store the old session ID in JavaScript or URLs** and try to resend it. Let the browser accept the new cookie, and configure `Secure`, `HttpOnly`, `SameSite`, `Domain`, and `Path` to match your HTTPS/proxy boundaries.

### 11.3. Open Redirect and Host/Proxy Headers

Saved requests are usually built from the URL the client requested. If the application reads a `returnUrl` from query/body/headers or trusts untrusted proxy headers, an attacker can trigger a redirect to an external domain.

Recommendations:

- Only allow redirect targets on the same origin or in an allowlisted set of internal routes.
- Reject `javascript:`, `//evil.example`, external domains, and arbitrary URL schemes in return destinations.
- Define a trusted proxy chain and protect `Forwarded`/`X-Forwarded-Host` so the host/scheme used to build redirect URLs cannot be spoofed.
- Test login redirects with query strings, context paths, and HTTPS offloading.
- If the flow uses `targetUrlParameter`, only enable it with strict validation/restriction rules.

### 11.4. Do Not Store Sensitive Data in RequestCache

RequestCache is for **navigation**, not for storing forms, passwords, OTPs, or full request bodies. For requests that need a POST after login, redesign the app to ask the user to confirm the action.

If using a custom `RequestCache`, restrict:

- Which methods/paths are saved, preferring safe navigation.
- The size of stored data, avoiding keeping huge URLs/headers in the session.
- TTL and cleanup on login/logout/session timeout.
- Never serialize secrets or unnecessary PII.
- Avoid creating unbounded sessions under anonymous bot traffic, since creating sessions for request caching also carries cost.

### 11.5. Session State Does Not Equal Authorization

After login, the session helps the framework identify the user; **every request** must still pass through the relevant authorization policy. If roles change between requests, a cached `Authentication` may retain stale authorities; the product needs a revalidation/revocation/session invalidation policy if permission changes must take effect immediately.

Do not treat "having redirected through /login" as proof that the user is allowed to read a report. Authorization filters and object-level policies make that decision.

## 12. Important Non-Happy-Path Tests

| Test case | What to verify |
| --- | --- |
| Anonymous GET protected | 302 /login, protected controller does not run |
| Anonymous GET public | 200 |
| GET login page | 200, no redirect loop |
| POST login right password | Authentication succeeds, valid session |
| POST login wrong password | Failure handler, no full authenticated session |
| POST login missing CSRF | 403 before auth |
| Login with saved request | Redirects to valid original URL |
| Login without saved request | Uses defaultSuccessUrl |
| Login with alwaysUseDefaultTargetUrl true | Saved request is not prioritized |
| Saved URL with query | Query handled properly, accounting for `continue` |
| Login from one tab, open another protected URL | Saved-request slot policy behaves as expected |
| Authenticated but missing role | 403, no login redirect loop |
| Browser sends wrong/missing JSESSIONID | Subsequent request does not receive authenticated context |
| API request without token | 401 matching API entry point, no HTML login returned |
| API user missing scope | 403 per API authorization |
| Browser logout | Session/context cleared; next protected request requires login |
| Session timeout | Stale cached authorities not accepted outside policy |
| Session fixation | Session ID rotated/protected per strategy |
| App behind reverse proxy | Redirect uses correct scheme/host/context path |
| Client-supplied return URL | No open redirect |
| Multi-chain matchers | Form-login filter/entry point reside in the right chain |
| Sub-context path like /portal | Redirect uses correct base path |
| Protected GET vs POST | No automatic replay of side-effecting POST |
| RequestCache disabled | No saved URL, controlled fallback |

### 12.1. Why Is @WithMockUser Not Enough?

`@WithMockUser` populates an authenticated security context directly in a test. It is useful for testing authorization, but **does not prove**:

- An anonymous request produces a 302 to login.
- `ExceptionTranslationFilter` invokes RequestCache.
- `UsernamePasswordAuthenticationFilter` actually checks the password.
- `AuthenticationSuccessHandler` picks the saved URL vs. the default URL.
- The browser sends the same session cookie and the follow-up request restores authentication properly.

To test this flow, you must simulate **multiple HTTP requests in order** while keeping the same `MockHttpSession`, as in Section 7.

### 12.2. If Debugging Shows 401 Instead of 302

Check:

1. Did the request enter the web form login chain or a stateless API chain?
2. Is the actual `AuthenticationEntryPoint` `LoginUrlAuthenticationEntryPoint` or `HttpStatusEntryPoint`/Basic/Bearer?
3. Is there an `Accept` header, AJAX request matcher, or config distinguishing browser vs. API?
4. Did a custom `exceptionHandling(...)` override the form entry point?
5. Is the login URL included in the right chain?
6. Is a custom filter throwing `AuthenticationException` in a position where `ExceptionTranslationFilter` can handle it?

**Do not fix this by forcing every 401 into a /login redirect**: API clients usually need a real 401 to know credentials are missing.

### 12.3. If Debugging Shows 403 Instead of 302

Check:

1. Is the user authenticated but missing an authority, or still anonymous?
2. Is the request a POST/PUT/DELETE missing a CSRF token?
3. Is the login URL blocked by `denyAll` or a matcher mismatch?
4. Were a custom `AccessDeniedHandler` or authorization rules changed?
5. For an API, does returning 403 match the semantics of "authenticated but lacking permission"?

### 12.4. If Login Succeeds But Does Not Return to the Original URL

Check:

1. Was a protected request saved before login?
2. Is `RequestCache` using HttpSession or Null?
3. Did the browser preserve the same session ID/cookie from the anonymous request through the login POST?
4. Is `alwaysUseDefaultTargetUrl` set to `true`?
5. Does a custom success handler ignore `SavedRequest`?
6. Are the path/query/`continue` constructed properly?
7. Did another protected request overwrite the saved request?
8. Did login go through a different chain than the protected page?
9. Did a reverse proxy rewrite the redirect scheme/host incorrectly?
10. Was the session lost due to a load balancer, missing distributed session store, or misconfigured cookie?

## 13. Common Mistakes

1. **Assuming the filter blocking a protected page directly renders the login form.** Usually it sends a **redirect**, and the browser performs a GET for the login page.
2. **Confusing `ExceptionTranslationFilter` with the password verifier.** The login filter/provider verifies credentials.
3. **Confusing `AuthenticationEntryPoint` with `AuthenticationSuccessHandler`.** The entry point initiates authentication; the success handler chooses the destination afterward.
4. **Confusing `AuthenticationFailureHandler` with the entry point for anonymous protected requests.**
5. **Treating HTTP 302 as always meaning login success.** The first 302 may just be sending the user to `/login`.
6. **Treating HTTP 403 as a wrong password.** Missing roles and missing CSRF tokens can also produce 403.
7. **Treating every unauthenticated request as 401.** Browser form login usually redirects with 302.
8. **Forgetting to permitAll the custom login page.** Leads to a redirect loop.
9. **Form POST URL not matching `loginProcessingUrl`.** The authentication filter does not intercept the request.
10. **Disabling or bypassing CSRF to make form login easier.** Breaks an essential browser protection layer.
11. **Failing to keep the same session across redirect and login.** Saved request/context cannot be restored.
12. **Assuming `HttpSessionRequestCache` implies the user is authenticated.** An anonymous session can also hold a saved request.
13. **Forgetting Spring Security 6's `continue` parameter.** Causes wrong redirect URL tests or request cache mismatches.
14. **Assuming saved request automatically replays any POST.** Side effects must not be replayed blindly.
15. **Setting `defaultSuccessUrl("/home", true)` and expecting to return to the original URL.**
16. **Replacing the success handler and unintentionally dropping saved request support.**
17. **Trusting a client-supplied `returnUrl` directly as `Location`**, creating an open redirect.
18. **Using untrusted host/forwarded headers to build redirects**, enabling host-header injection.
19. **Using GET /login simultaneously in a controller and a filter without understanding precedence**, causing conflicts or broken login pages.
20. **Creating two security chains where the login endpoint belongs to neither appropriate chain.**
21. **Assuming having ROLE_READER implies having ROLE_ADMIN.** Authorization checks exact authorities.
22. **Only asserting the redirect without performing the follow-up GET to the resource**, missing cookie/context bugs.
23. **Using `@WithMockUser` as an end-to-end login test**, skipping password verification, saved request, and session handling.
24. **Writing a custom manual login that only sets the context without saving it** in Spring Security 6, losing authentication on the next request.
25. **Not testing expiry/logout/role revocation**, allowing stale sessions to retain permissions beyond policy.
26. **Logging session IDs, passwords, or saved URLs containing secrets**, leaking sensitive data.
27. **Using form-login redirects for all APIs**, causing AJAX clients to receive HTML instead of 401 JSON.
28. **Disabling RequestCache without checking UX fallback**, forcing users back to /home every time.
29. **Multiple tabs overwriting saved requests without a defined policy**, causing unexpected destinations.
30. **Assuming URL access after login means the user is authorized for every object.** Object-level authorization is still required.

## 14. Practice Exercises

**Exercise 1 – Trace the request flow.** For an anonymous user doing GET `/reports/42`, state the responsibilities of `AuthorizationFilter`, `ExceptionTranslationFilter`, `LoginUrlAuthenticationEntryPoint`, `HttpSessionRequestCache`, `UsernamePasswordAuthenticationFilter`, `AuthenticationManager`, and the success handler. Indicate at which steps 302, 200, and actual authentication success occur.

**Exercise 2 – Run the demo.** Run `gradle test` and `gradle bootRun`, then access `/reports/42` in a browser. Observe the login page, session cookie, the redirect URL that may contain `continue`, and the follow-up GET. Do not copy session cookie values into shared documents.

**Exercise 3 – Missing role.** Log in as `mai` (`ROLE_READER`) and GET `/admin`. Explain why 403 is returned instead of redirecting to login. Try an anonymous GET `/admin` and compare.

**Exercise 4 – Default URL.** Change `defaultSuccessUrl("/home", false)` to `true`. Log in after opening `/reports/42` and observe the difference. Explain whether the saved request is prioritized or ignored.

**Exercise 5 – Custom login page.** Build `GET /signin`, configure `loginPage("/signin")`, `loginProcessingUrl("/signin")`, and `failureUrl("/signin?error")`. Verify CSS/images are accessible, the form includes a CSRF token, and no redirect loop occurs.

**Exercise 6 – API 401.** Create a stateless `/api/**` chain with `HttpStatusEntryPoint(UNAUTHORIZED)` and `NullRequestCache`. Compare the same anonymous request against the browser chain (302) and the API chain (401).

**Exercise 7 – RequestCache.** Inspect the session after an anonymous protected GET. Observe the `SavedRequest` object containing the destination without an authenticated context. After login, access the URL with `continue` and observe request cache matching/removal per policy.

**Exercise 8 – POST before login.** Suppose a user tries to POST `/payments/confirm` while anonymous. Design a UX that lets them log in and then **re-confirm** the action instead of auto-replaying the POST; check CSRF, idempotency, and double-submit protection.

**Exercise 9 – Lost session.** When login succeeds but the next request bounces back to login, check for `SameSite`/`Secure`/`Domain`, path, proxy, session store, or wrong-chain bugs. Write integration tests preserving vs. dropping the session to demonstrate.

**Exercise 10 – Redirect security.** Test `returnUrl` values such as local paths, external domains, `//evil.example`, and invalid schemes. Enforce a rule permitting only validated destinations. Never use raw client input as `Location`.

**Exercise 11 – Multi-tab.** Open two protected URLs while anonymous before logging in. Note that the session may retain only the most recent saved request; propose a separate workflow-state mechanism if the product must resume multiple actions.

**Exercise 12 – Migration.** When upgrading to Spring Security 6, check `HttpSessionRequestCache` with the `continue` parameter, explicit-save context persistence, and custom success handlers. Write tests on the **exact versions** before/after upgrading to detect differences.

### Completion Criteria

Learners can explain:

- Why an anonymous protected GET usually produces **302 /login** rather than 200/401 in a browser chain?
- What `ExceptionTranslationFilter` and `AuthenticationEntryPoint` are, and how they differ from authorization and password authentication?
- Who saves `SavedRequest`, where it is stored, and when the success handler uses it?
- Why Spring Security 6 may append `?continue` to the return URL?
- How a valid login with a missing role leads to 403?
- When GET login page is auto-generated versus when a custom controller is required?
- How to use MockMvc across **multiple requests sharing a session** to test the real flow?
- Why you should not auto-replay POSTs or use an untrusted returnUrl for redirects?
- What CSRF, session fixation, cookie, open redirect, and multi-chain boundaries must be protected?

## 15. Official References

- [Spring Security 6.5 – Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): redirect flow from a protected page, `UsernamePasswordAuthenticationFilter`, success/failure handling.
- [Spring Security 6.5 – Servlet Architecture / Handling Security Exceptions](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, and the authorization filter chain.
- [Spring Security 6.5 – Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationManager`, `ProviderManager`, `AuthenticationEntryPoint`, and authentication filters.
- [Spring Security 6.5 – Session Management Migrations](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html): RequestCache and `continue` changes between Spring Security 5 and 6.
- [Spring Security 6.5.11 – SavedRequestAwareAuthenticationSuccessHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html): choosing saved/default/target URL.
- [Spring Security 6.5.11 – HttpSessionRequestCache API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/savedrequest/HttpSessionRequestCache.html): storing requests in session, matchers, and the `continue` parameter.
- [Spring Security – MockMvc Form Login Tests](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html): `formLogin` request post processor and CSRF in tests.
- [Spring Security 6.5 – CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): protecting cookie-based forms.
- [Spring Security 6.5 – Multiple SecurityFilterChains](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html#servlet-securityfilterchain): chain selection and matching.
- [OWASP – Unvalidated Redirects and Forwards Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): protecting return URLs and preventing open redirects.

**Example versions:** Java 17 / Spring Boot 3.5.7 (Spring Security 6.5.x via dependency management). For Spring Security 7, WebFlux, custom authentication mechanisms, API tokens, or custom request-cache implementations, consult the Javadoc and actual security chain; do not mechanically apply browser form-login status codes/URLs to every client type.