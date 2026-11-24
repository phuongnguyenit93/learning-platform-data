# Explicit Save Mechanism and Context Persistence Responsibilities in Custom Login

> **Scope:** Spring Security 6 on the **Servlet stack** (Spring Boot 3.x, Java 17+). Topic under **Security Context**: why putting `Authentication` into `SecurityContextHolder` only authenticates the current request, how `SecurityContextRepository` persists context across requests, and the responsibilities introduced when building a custom login flow. WebFlux uses `ReactiveSecurityContextHolder` and reactive repositories, so this Servlet pattern does not apply verbatim.

## 1. The Problem: Login Succeeds in One Request, but the Next Request Loses the Session

Suppose an application has a custom endpoint `POST /custom-login` that accepts a username and password and runs:

```java
// Illustrative snippet; must be placed in a controller/service with required dependencies.
Authentication auth = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(username, password));

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(auth);
SecurityContextHolder.setContext(context);
```

Immediately afterwards in the **same request**, calling `SecurityContextHolder.getContext().getAuthentication()` may return the newly authenticated user. However, the **next** HTTP request enters a new thread/request; when Spring Security uses **explicit save**, nothing guarantees this context was written to the session or a cross-request durable store.

That is why the following failure commonly appears:

```text
POST /custom-login  -> 200 OK ("login succeeded")
GET  /me            -> 401 Unauthorized
```

The cause may be that the controller **set the context but forgot to call `saveContext(...)`**, or the application uses a stateless/no-session policy. Success of `AuthenticationManager.authenticate(...)` and persisting authentication across multiple requests are **two separate steps**.

**Key statement to remember:** `SecurityContextHolder.setContext(...)` changes the access state within the current request flow; `SecurityContextRepository.saveContext(...)` is what requests saving the context to the configured repository. `authenticate(...)` alone does not save the context simply because it returned a valid `Authentication`.

## 2. Participating Objects and Responsibilities

| Component | Function | What does it NOT do automatically? |
| --- | --- | --- |
| `AuthenticationManager` | Verifies credentials via an appropriate provider and returns `Authentication` | Does not automatically attach authentication to the holder/session for arbitrary custom calls |
| `SecurityContext` | Holds the security context's `Authentication` | Does not create an HTTP session by itself |
| `SecurityContextHolder` | Exposes context to the current request/thread via `SecurityContextHolderStrategy` | Not a database/session repository; changes here do not persist across requests by default |
| `SecurityContextHolderFilter` | Loads context (potentially deferred) from repository for the request, binds it to the holder, and clears the holder when the request finishes | In explicit-save mode, **does not auto-save** modified context when the response ends |
| `SecurityContextRepository` | Reads and saves context via `loadDeferredContext`/`saveContext` | Does not verify passwords or enforce authorization decisions |
| `HttpSessionSecurityContextRepository` | Stores context in `HttpSession` when configuration and conditions permit | Does not act as cross-request persistence when the application uses a stateless policy |
| `RequestAttributeSecurityContextRepository` | Keeps context in request attributes, supporting related dispatches in the same request | Not used to persist login across independent HTTP requests |
| `DelegatingSecurityContextRepository` | Delegates to multiple repositories, usually combining request attributes and HTTP session | Does not turn `SecurityContextHolder` into an automatic store |

On the Servlet stack, Spring Security 6 typically uses `SecurityContextHolderFilter` with **explicit save required**. Legacy behavior based on `SecurityContextPersistenceFilter` could auto-write the context at request end; do not rely on legacy behavior when writing custom authentication flows for current configurations.

### How Is Context Restored on the Next Request?

```text
Request 1: POST /custom-login
    |
    +-- SecurityContextHolderFilter obtains initial context
    +-- Controller calls AuthenticationManager.authenticate(...)
    +-- Creates new SecurityContext, sets verified Authentication
    +-- SecurityContextHolderStrategy.setContext(context)
    +-- SecurityContextRepository.saveContext(context, request, response)
    |      |
    |      +-- HttpSessionSecurityContextRepository writes to session
    |      +-- Response may emit Set-Cookie session ID
    |
    +-- response completes; request's holder is cleared

Request 2: GET /me + session cookie
    |
    +-- SecurityContextHolderFilter uses repository to load context
    +-- AuthorizationFilter receives saved Authentication
    +-- Controller sees valid user
```

If `saveContext(...)` is omitted in the first request, the context only exists for that request; the subsequent request has no saved `Authentication` in the session to reload.

## 3. Explicit Save in Spring Security 6

With `HttpSecurity`, explicit save mode can be expressed as:

```java
http.securityContext(security -> security
        .requireExplicitSave(true)
        .securityContextRepository(securityContextRepository));
```

This snippet is **only part of a configuration** and must sit inside a valid `HttpSecurity` configuration. In Spring Security 6, `requireExplicitSave(true)` is the common default mode of the context-management filter. When upgrading from older versions, inspect the actual configured chain and filters.

In this mode:

1. **Request start:** `SecurityContextHolderFilter` prepares the context from the repository; loading can be deferred until code actually accesses the holder.
2. **During the request:** a filter, controller, or authentication mechanism may replace the `Authentication` in the context.
3. **On successful authentication:** the **party performing custom authentication** must decide how to persist and call `SecurityContextRepository.saveContext(...)` when state should continue into future requests.
4. **Request end:** the filter clears the context from the holder/strategy to avoid state leakage when threads are reused. This cleanup **is not equivalent** to deleting data already saved in the session.

This does not mean every Spring Security 6 application must manually call `saveContext` in controllers. Standard framework mechanisms like form login are built with authentication filters that **save the context themselves after successful authentication**. The extra responsibility arises when you **write custom** authentication logic outside mechanisms that already handle it.

### Why Not Mutate the Existing SecurityContext and Expect Auto-Save?

For example:

```java
// Not a complete login procedure:
SecurityContextHolder.getContext().setAuthentication(auth);
```

That call provides no guarantee that the repository will write the context. When switching a request's identity, create a fresh `SecurityContext`, attach the valid `Authentication`, place it in the holder, and **save via the repository**. Creating a new context also reduces the risk of mutating an accidentally shared context object.

## 4. How to Call saveContext Properly

Core pattern when handling login manually in Servlet:

```java
// Illustrative snippet inside HTTP processing flow,
// after CSRF checks and completing session policies.
Authentication authentication = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(username, password));

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(context, request, response);
```

The three parameters of `saveContext` are the **context to save**, the current `HttpServletRequest`, and `HttpServletResponse`. Passing the response matters when the repository may need to create/update a session cookie before the response commits.

**Ideal execution order:** authentication succeeds → execute required session authentication strategies → create/set context → save context → write response or redirect. Never call `sendRedirect`, flush the body, or commit the response **before** the repository has a chance to save, as headers/cookies may no longer be modifiable afterwards.

If authentication fails, **do not save** a context holding an invalid authentication as though login succeeded. For flows switching an already logged-in account, define how to handle the existing context, clear stale state as needed, and return appropriate errors.

## 5. Runnable Example: Custom Login with Explicit Save and HTTP Session

This exercise uses **Java 17+, Spring Boot 3.3.5, Spring Security 6.x, Gradle 8.5**. We deliberately use a **custom login controller**, rather than the standard form-login filter, to highlight the manual responsibilities required.

The application provides:

- `GET /csrf`: issues a valid CSRF token for clients to use when calling POST.
- `POST /custom-login`: verifies credentials, applies session authentication strategies, and saves `SecurityContext` explicitly.
- `GET /me`: callable only by authenticated users, proving session persistence across requests.
- CSRF stays **enabled** for POST; never disable CSRF application-wide just to make a login demo "easier to run".
- Session fixation is handled by rotating the session ID; the old CSRF token is refreshed after login.

### 5.1. File Tree and Build

```text
explicit-save-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    SecurityConfig.java
    LoginController.java
  src/test/java/demo/
    LoginFlowTest.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'explicit-save-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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
```

A compatible Gradle wrapper can be used to pin the build environment. Spring WebFlux is not needed.

### 5.2. Bootstrap Class

File `src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 5.3. SecurityConfig: Selecting Repository and Security Policy

File `src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import java.util.List;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository());
    }

    @Bean
    CsrfTokenRepository csrfTokenRepository() {
        return new HttpSessionCsrfTokenRepository();
    }

    @Bean
    SessionAuthenticationStrategy sessionAuthenticationStrategy(
            CsrfTokenRepository csrfTokens) {
        return new CompositeSessionAuthenticationStrategy(List.of(
                new ChangeSessionIdAuthenticationStrategy(),
                new CsrfAuthenticationStrategy(csrfTokens)));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository contexts,
            CsrfTokenRepository csrfTokens) throws Exception {
        http.securityContext(security -> security
                .requireExplicitSave(true)
                .securityContextRepository(contexts));

        http.csrf(csrf -> csrf.csrfTokenRepository(csrfTokens));

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/csrf", "/custom-login").permitAll()
                .anyRequest().authenticated());

        // Use consistent HTTP 401 for easier verification when unauthenticated.
        http.exceptionHandling(errors -> errors
                .authenticationEntryPoint((request, response, exception) ->
                        response.sendError(HttpServletResponse.SC_UNAUTHORIZED)));

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails user = User.withUsername("learner")
                .password(encoder.encode("study123"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(user);
    }

    @Bean
    AuthenticationManager authenticationManager(
            AuthenticationConfiguration config) throws Exception {
        return config.getAuthenticationManager();
    }
}
```

**Explanation of choices:**

- `DelegatingSecurityContextRepository` stores in both request attributes and HTTP session. `RequestAttributeSecurityContextRepository` helps related dispatches in the same request; `HttpSessionSecurityContextRepository` serves subsequent requests via the session cookie.
- `securityContext(...requireExplicitSave(true))` makes the contract explicit: custom authentication code must invoke the repository.
- `HttpSessionCsrfTokenRepository` and `CsrfAuthenticationStrategy` maintain CSRF protection for state-changing requests while refreshing the CSRF token after login. `ChangeSessionIdAuthenticationStrategy` protects against session fixation by rotating the existing session's ID.
- `/custom-login` is `permitAll` because unauthenticated users must be able to reach the login endpoint; **permitAll does not bypass CSRF**.
- The sample uses development account `learner/study123` strictly for local practice. The password is BCrypt-hashed in memory; real products must manage secrets and accounts outside source code, use HTTPS, and enforce brute-force/rate limiting.

**Why is there a separate `SessionAuthenticationStrategy`?** When using built-in authentication filters, Spring Security executes session strategies inside that filter's lifecycle. A controller calling `AuthenticationManager` directly will not trigger those steps automatically. Therefore the example invokes the strategy explicitly. If your project enforces concurrent session limits, uses a session registry, saved requests, or remember-me, the custom flow must also integrate those mechanisms per their contracts; `saveContext` alone does not replace them.

### 5.4. LoginController: Handling Requests and Saving Context

File `src/main/java/demo/LoginController.java`:

```java
package demo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LoginController {

    private final AuthenticationManager authenticationManager;
    private final SecurityContextRepository securityContextRepository;
    private final SessionAuthenticationStrategy sessionStrategy;

    public LoginController(AuthenticationManager authenticationManager,
                           SecurityContextRepository securityContextRepository,
                           SessionAuthenticationStrategy sessionStrategy) {
        this.authenticationManager = authenticationManager;
        this.securityContextRepository = securityContextRepository;
        this.sessionStrategy = sessionStrategy;
    }

    @GetMapping("/csrf")
    public String csrfToken(HttpServletRequest request) {
        // CsrfFilter places this attribute on the request.
        CsrfToken token = (CsrfToken) request.getAttribute(
                CsrfToken.class.getName());
        return token.getToken();
    }

    @PostMapping("/custom-login")
    public ResponseEntity<String> login(@RequestParam String username,
                                        @RequestParam String password,
                                        HttpServletRequest request,
                                        HttpServletResponse response) {
        try {
            Authentication authentication = authenticationManager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            username, password));

            // Custom authentication must apply session strategy manually.
            sessionStrategy.onAuthentication(authentication, request, response);

            SecurityContext context = SecurityContextHolder.createEmptyContext();
            context.setAuthentication(authentication);
            SecurityContextHolder.setContext(context);

            // Key step: save before the response is committed.
            securityContextRepository.saveContext(context, request, response);
            return ResponseEntity.ok("login-ok");
        } catch (AuthenticationException exception) {
            SecurityContextHolder.clearContext();
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .body("invalid-credentials");
        }
    }

    @GetMapping("/me")
    public String me() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();
        return authentication.getName();
    }
}
```

**Reading the exact sequence of `login(...)`:** (1) `authenticate` verifies the password; (2) strategy performs session fixation/CSRF work; (3) creates a fresh context holding the verified result; (4) sets it in the holder for the running request; (5) **`saveContext(context, request, response)`** writes the context to the repository; (6) returns the body. Removing step (5) alone will cause the cross-request persistence test to fail under explicit-save mode.

In the example, an `AuthenticationException` such as a wrong password results in HTTP 401 without calling `saveContext` for that authentication. Real applications must govern failed login retries by an already logged-in account per policy; if forced logout or session revocation is required, perform an explicit logout/invalidation procedure.

**Security note:** `ResponseEntity.ok(...)` does not create a session on behalf of the repository. The client must store and resend the session cookie. If the API is strictly stateless, design per-request authentication instead of session persistence as in this example.

### 5.5. Test: Proving Explicit Save with Two Independent HTTP Requests

File `src/test/java/demo/LoginFlowTest.java`:

```java
package demo;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousRequestToProtectedEndpointIsUnauthorized() throws Exception {
        mvc.perform(get("/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void customLoginSavesContextForNextRequest() throws Exception {
        MvcResult result = mvc.perform(post("/custom-login")
                        .with(csrf())
                        .param("username", "learner")
                        .param("password", "study123"))
                .andExpect(status().isOk())
                .andExpect(content().string("login-ok"))
                .andReturn();

        HttpSession session = result.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/me").session((MockHttpSession) session))
                .andExpect(status().isOk())
                .andExpect(content().string("learner"));
    }

    @Test
    void invalidPasswordDoesNotAuthenticate() throws Exception {
        mvc.perform(post("/custom-login")
                        .with(csrf())
                        .param("username", "learner")
                        .param("password", "incorrect"))
                .andExpect(status().isUnauthorized())
                .andExpect(content().string("invalid-credentials"));
    }

    @Test
    void missingCsrfTokenRejectsPost() throws Exception {
        mvc.perform(post("/custom-login")
                        .param("username", "learner")
                        .param("password", "study123"))
                .andExpect(status().isForbidden());
    }
}
```

`customLoginSavesContextForNextRequest` is the crucial proof: the first request writes the context to the session; the second request passes only that same session **without resending username/password**, yet `/me` still returns `learner`. Do not use `@WithMockUser` to prove persistence, because that annotation injects test authentication directly and hides missing context persistence in the application.

### 5.6. Run Commands and Expected Results

From the `explicit-save-demo` directory:

```bash
gradle test
gradle bootRun
```

If a Gradle wrapper is present, use `./gradlew test` or `.\gradlew.bat test` on Windows.

Expected result: 4 tests **PASS** (each test independent, unauthenticated in the anonymous test), and `/me` requires authentication when a request lacks a valid session.

Test manually in a terminal with `curl`. The first command creates a cookie jar and fetches the token from `/csrf`:

```bash
curl -i -c cookies.txt -b cookies.txt http://localhost:8080/csrf
```

Copy **the exact token value from the returned body**. Then replace `TOKEN_FROM_CSRF` with the received token:

```bash
curl -i -c cookies.txt -b cookies.txt \
  -H 'X-CSRF-TOKEN: TOKEN_FROM_CSRF' \
  -d 'username=learner' -d 'password=study123' \
  http://localhost:8080/custom-login

curl -i -b cookies.txt http://localhost:8080/me
```

Here `curl -c` writes updated cookies (including a potentially rotated session ID after login), and `curl -b` sends saved cookies. Ensure the client uses the same cookie jar.

| Action | Expected HTTP status | Response body |
| --- | --- | --- |
| `GET /me` without valid session | **401** | Server-dependent |
| `GET /csrf` | **200** | A CSRF token (dynamic value) |
| `POST /custom-login` wrong password, valid token | **401** | `invalid-credentials` |
| `POST /custom-login` right password, valid token | **200** | `login-ok` |
| `GET /me` carrying saved session cookie | **200** | `learner` |
| `POST /custom-login` without valid token | **403** | Server-dependent |

Do not predict exact session IDs, CSRF tokens, cookie names, or `Set-Cookie` headers in output: those are runtime values. After login, `CsrfAuthenticationStrategy` invalidates the old token; clients must fetch `GET /csrf` again before a subsequent POST.

## 6. When Should You NOT Persist to an HTTP Session?

### 6.1. Session-Based vs. Stateless Differences

| Mode of operation | How Authentication is restored on next request | Role of `saveContext` |
| --- | --- | --- |
| Stateful Servlet + session | Session cookie → `HttpSession` → `HttpSessionSecurityContextRepository` | **Required** in custom login when context must persist across requests |
| Stateless API + bearer token | Every request carries token; security filter validates and establishes fresh context | Do not use HTTP session to store login; re-authenticate via token on each request |
| Current request only | Custom authentication sets context in holder and finishes | Context does not persist to other requests by default |

When using `SessionCreationPolicy.STATELESS`, do not expect `saveContext` to create a durable login session. Stateless policies are normally paired with a non-persisting repository (`NullSecurityContextRepository`) or dedicated storage. Never fix bugs by forcing session creation if the architecture requires statelessness.

### 6.2. RequestAttributeSecurityContextRepository Does Not Replace HttpSession

`RequestAttributeSecurityContextRepository` is helpful so security context remains visible across dispatches tied to **the same Servlet request** (such as an error dispatch), but it does not restore an account in an independent subsequent HTTP request. For session-based login, the repository must actually persist into `HttpSession` or an appropriately durable store.

`DelegatingSecurityContextRepository` can write to both. When configuring custom repositories, ensure **the exact same contract/repository** is used by the context-loading filter and the `saveContext`-calling code; if each side uses a different store, saving succeeds in store A while the next request loads from store B.

## 7. Other Responsibilities of Custom Authentication Beyond Explicit Save

**`saveContext` is only one part of the login lifecycle.** Spring Security's standard login mechanisms coordinate multiple components; when implementing login manually in a controller, consider each of the following:

1. **Session fixation protection:** rotate the session ID or apply an equivalent strategy after authentication. For example, use `ChangeSessionIdAuthenticationStrategy` so the same session identifier is not kept before and after login.
2. **CSRF protection:** with session-cookie login, keep CSRF protection for state-changing requests; rotate/refresh the token after login, as `CsrfAuthenticationStrategy` does in the example.
3. **Session concurrency and session registry:** if the application limits concurrent sessions, custom login must integrate the corresponding policies. `ChangeSessionIdAuthenticationStrategy` alone does not enforce concurrency limits.
4. **Remember-me, event publishing, success/failure handlers:** if the system requires them, implement equivalent logic or leverage standard authentication filters. Calling `AuthenticationManager` does not trigger all callbacks of a login filter automatically.
5. **Saved requests and redirects:** redirecting unauthenticated users to login and returning them to their original URL requires a request cache/success handler for interactive web apps; JSON APIs may not need this.
6. **Proper logout:** clear/revoke the saved context, invalidate the session if policy requires, and handle cookies/CSRF properly. Calling `SecurityContextHolder.clearContext()` alone clears state in the current holder, not necessarily the authentication saved in the session.
7. **Secrets and login errors:** never log passwords, avoid overly detailed error responses that leak account existence, enforce retry throttling, and use HTTPS to protect credentials and session cookies.

For typical login features, prefer `formLogin`, OAuth2 login, or an appropriate authentication filter because those components already integrate many of these responsibilities. Roll your own only when protocol/application requirements are clear enough to govern the entire lifecycle.

## 8. Real-World Bugs and How to Diagnose Them

### 8.1. "Authentication Exists in Controller, but Next Request Gets 401"

Check sequentially:

- Was `securityContextRepository.saveContext(context, request, response)` actually called after successful authentication?
- Are the request-start filter and the context-saving controller using the exact same repository?
- Did the client store and resend the session cookie, especially after session ID rotation?
- Is `SessionCreationPolicy.STATELESS`, `NullSecurityContextRepository`, or another filter clearing the session/context?
- Is the `Authentication` of a kind the repository persists (as opposed to anonymous/empty context)?
- Did `saveContext` execute **before the response was committed**? Did any redirect/exception branch skip it?

Do not conclude the bug is in the password encoder if the login request already produced a valid `Authentication`.

### 8.2. "Should We Call `session.setAttribute("SPRING_SECURITY_CONTEXT", context)` Directly?"

Do not treat writing the session attribute manually as the primary integration API. Use `SecurityContextRepository.saveContext(...)` to preserve policy, lifecycle, request wrapping, and Spring Security's repository setup. Manual writes can skip request-attribute handling, diverge from the reading repository, or bypass session policies.

### 8.3. "Seeing `SecurityContextHolder.getContext()` Return Authentication Means Login Persists?"

It proves state only in the **current request/thread**. The holder typically uses a thread-bound strategy; once the filter finishes, it is cleared. A second request carrying the session cookie is needed to verify the context was saved and reloaded.

### 8.4. "Spring Security 6 Not Auto-Saving Means Every Filter Must Save Manually?"

No. Standard framework authentication filters call save automatically upon successful login. Only custom code implementing its own authentication must take on this step. Do not scatter save calls across every controller to paper over a poorly designed authentication flow.

### 8.5. "Switching to `requireExplicitSave(false)` Fixes Everything?"

That changes the contract back to legacy behavior rather than resolving the responsibility to design a clear custom flow. New applications should understand explicit save, ensure success/failure/session paths are tested, and call the proper repository. Use legacy mode only for specific compatibility reasons and with full understanding of its impact.

### 8.6. "Why Is the Session Still Lost After Saving Following a Redirect?"

Issuing a redirect or committing the response before saving can prevent the repository from creating/updating the cookie in time. Save the context once authentication and session strategies finish, **before** `sendRedirect`/flush/response commit. For custom authentication filters, use success handlers in the proper order or framework-supported hooks.

### 8.7. "Session Exists, Why Are Authorities Missing in Async or Error Dispatches?"

Do not assume the context automatically propagates to all asynchronous threads. For tasks running outside the request thread, consider `DelegatingSecurityContextRunnable`/`DelegatingSecurityContextExecutor` or equivalent APIs to pass the context intentionally when truly needed. `RequestAttributeSecurityContextRepository` supports request/dispatch scope, not arbitrary propagation to background threads.

### 8.8. "Can Saving Context Accidentally Retain Expired Authentication Info?"

The repository stores the authentication state at save time; the application must still enforce logout, session timeout, account disable/revocation, permission changes, and re-authentication requirements. An active session does not guarantee external account state stays updated instantaneously.

## 9. Checklist for Implementing a Custom Login Flow

| Check | Criterion |
| --- | --- |
| Authentication | `AuthenticationManager.authenticate` succeeds and returns a valid identity |
| Context | Fresh context created, `Authentication` placed in the request's holder |
| Session policy | Proper stateful/stateless choice; if stateful, handles session fixation and related strategies |
| Persistence | Uses `SecurityContextRepository.saveContext` **before response commit** |
| Repository consistency | Context-loading filter and context-saving code use the same repository configuration |
| CSRF | Login POST and state-changing operations have CSRF protection when using session cookies |
| Cookie | Client receives session ID after authentication and resends it on subsequent requests |
| Failure | Bad credentials are never saved as authenticated; 401/403 responses are distinct |
| Logout | Clears/disconnects saved context, session, and cookies per policy |
| Tests | Second request without resending credentials succeeds with valid session; sessionless request is blocked |

To avoid misleading tests, **separate the login request from the verification request** while reusing the session cookie. Also test a completely fresh request without cookies to confirm the endpoint is not accidentally `permitAll`.

## 10. Self-Check

1. **Why is `SecurityContextHolder.setContext(context)` insufficient to keep a login?** Because the holder stores state only within the request/thread scope; explicit-save mode does not auto-write the context to the repository at request end.
2. **Who is responsible for calling `saveContext` in custom login?** The code performing successful authentication, unless delegated to a filter/framework mechanism that already handles saving.
3. **Why must `saveContext` be called before redirecting?** The repository may need to create a session and update cookies/response; once the response is committed, doing so is no longer reliable.
4. **Does `RequestAttributeSecurityContextRepository` persist across two different HTTP requests?** No; it is meant for request/dispatch scope. Use `HttpSessionSecurityContextRepository` or a suitable store for cross-request persistence.
5. **Do custom logins only need `authenticate`, `setContext`, and `saveContext`?** Not enough in many apps: session fixation, CSRF, logout, concurrency, callbacks, and other auth policies also apply.
6. **For stateless APIs, should SecurityContext be saved in the session?** Typically no; each request should be authenticated from appropriate credentials/tokens.
7. **What is the most important test to prove explicit save works?** Log in successfully on the first request, send a second request with the same session **without resending credentials**, and verify the protected endpoint receives the right `Authentication`.

**Key takeaway:** In Spring Security 6 Servlet, `SecurityContextHolderFilter` uses the repository to **load** the context and clears the holder; **explicit save** places **saving** responsibility on the authentication mechanism. When writing custom login, authenticate successfully → apply session strategies → create/set `SecurityContext` → call `SecurityContextRepository.saveContext(context, request, response)` **before response commit**. Only when repository, session policy, and cookies are properly aligned will the user stay logged in on the next request.
