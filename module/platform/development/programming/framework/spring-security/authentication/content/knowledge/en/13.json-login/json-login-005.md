# Saving SecurityContext When a JSON Endpoint Creates a Login Session (Spring Security Servlet)

## 1. The Problem: JSON Login Returns 200, Yet the Next Request Is Unauthenticated

In a Spring MVC application, clients often send JSON to `POST /auth/login`:

```http
POST /auth/login HTTP/1.1
Content-Type: application/json

{"username":"alice","password":"alice-secret"}
```

The controller verifies username/password successfully and returns JSON. However, if you only do:

```java
Authentication authentication = authenticationManager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(username, password)
);
SecurityContextHolder.getContext().setAuthentication(authentication);
```

then the **current request** may see the authenticated user, yet the next request may still be rejected. The reason: `SecurityContextHolder` holds the context for the current execution flow; it **does not automatically ensure** that the context is written to a store readable by subsequent requests.

This lesson focuses on a **JSON endpoint that authenticates manually and creates an HTTP-session-based login**, using Java 17+, Spring Boot 3.x / Spring Security 6.x on the Servlet stack. This is **session login**: the browser holds a session cookie while the server holds the `SecurityContext`. It differs from stateless JWT/bearer-token auth, HTTP Basic, or OAuth2 login handled by built-in filters.

By the end of this lesson, you should be able to explain and implement:

1. Creating a verified `Authentication` via `AuthenticationManager`.
2. Creating a new `SecurityContext`, setting `Authentication` on it, and attaching it to `SecurityContextHolder`.
3. Calling `SecurityContextRepository.saveContext(context, request, response)` **before the response is committed** so the next request restores login.
4. Ensuring the client stores and resends the session cookie; distinguishing this from storing passwords/tokens directly in a cookie.
5. Handling concerns accompanying manual login: session fixation, CSRF, failed logins, logout, multi-instance environments, and testing.

## 2. Components That Hold and Restore Login State

| Component | Responsibility | Persists login across multiple requests? |
|---|---|---|
| Unauthenticated `UsernamePasswordAuthenticationToken` | Carries username/password into the authentication process | No |
| `AuthenticationManager` | Invokes authentication providers to verify credentials | Does not save session itself |
| Authenticated `Authentication` | Holds principal, authorities, and authenticated flag | Insufficient unless persisted |
| `SecurityContext` | Wraps `Authentication` | The context alone does not create a session |
| `SecurityContextHolder` | Holds the active context for the current request/thread | Not a cross-request store |
| `SecurityContextRepository` | Reads/writes `SecurityContext` across the request lifecycle | Yes, if the repo supports persistence |
| `HttpSessionSecurityContextRepository` | Stores context in the server's `HttpSession` | Yes, keyed by session ID |
| `RequestAttributeSecurityContextRepository` | Keeps context within the same request, including some dispatches | Within the request only |
| `DelegatingSecurityContextRepository` | Coordinates multiple repositories | Can combine both |
| `SecurityContextHolderFilter` | Reads context from repo, places it in holder, and clears holder after request | **Does not auto-save** new contexts in Spring Security 6 |

In Spring Security 6, the default mechanism uses `SecurityContextHolderFilter` and requires **explicit saving** when authenticating manually outside Spring Security's managed authentication filters. The older `SecurityContextPersistenceFilter` used to support automatic saving; do not build new solutions relying on that expectation.

Typically, `DelegatingSecurityContextRepository` combines:

- `RequestAttributeSecurityContextRepository` to serve dispatches within a single request.
- `HttpSessionSecurityContextRepository` to attach the context to the session, restoring it on subsequent requests.

**Essential condition:** the repository used for `saveContext(...)` in the controller must be compatible with the repository the filter chain uses to `load`. Using two repositories that store in different places causes the "login succeeded but session was forgotten" symptom.

### Request Flow Over Time

```mermaid
sequenceDiagram
    participant C as Client
    participant F as Security filters
    participant L as JSON login controller
    participant A as AuthenticationManager
    participant R as SecurityContextRepository

    C->>F: POST /auth/login + JSON + CSRF + cookie
    F->>L: Allow request into login endpoint
    L->>A: authenticate(username, password)
    A-->>L: Authenticated Authentication
    L->>L: SessionAuthenticationStrategy.onAuthentication(...)
    L->>L: createEmptyContext + setAuthentication
    L->>R: saveContext(context, request, response)
    R-->>C: Save context into session; return/rotate session cookie if needed
    C->>F: GET /api/me + Cookie: JSESSIONID=...
    F->>R: load context from session
    R-->>F: alice's Authentication
    F-->>C: 200 {"username":"alice"}
```

A cookie like `JSESSIONID` normally holds only the **session identifier**. It contains neither the password nor the entire `Authentication`. The actual context lives server-side (or in a server-managed session store such as Spring Session).

## 3. Complete Example: Session-Persisting JSON Login in Spring Boot

Assume a Spring Boot 3.x project using Java 17+ with a Gradle wrapper/Boot plugin. Required dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

The application has three files under package `com.example.jsonlogin`. Paths/packages/classes below match one another. Sample passwords are for local use only; production must manage credentials via an appropriate identity store.

### 3.1. Entry Point

`src/main/java/com/example/jsonlogin/JsonLoginApplication.java`:

```java
package com.example.jsonlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonLoginApplication.class, args);
    }
}
```

### 3.2. SecurityFilterChain, SecurityContextRepository, and Session Strategy

`src/main/java/com/example/jsonlogin/SecurityConfig.java`:

```java
package com.example.jsonlogin;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
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
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository()
        );
    }

    @Bean
    CsrfTokenRepository csrfTokenRepository() {
        return new HttpSessionCsrfTokenRepository();
    }

    @Bean
    SessionAuthenticationStrategy sessionAuthenticationStrategy(
            CsrfTokenRepository csrfTokenRepository) {
        return new CompositeSessionAuthenticationStrategy(List.of(
            new ChangeSessionIdAuthenticationStrategy(),
            new CsrfAuthenticationStrategy(csrfTokenRepository)
        ));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository securityContextRepository,
            CsrfTokenRepository csrfTokenRepository) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/csrf", "/auth/login", "/error")
                    .permitAll()
                .anyRequest().authenticated()
            )
            .securityContext(context -> context
                .securityContextRepository(securityContextRepository)
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            )
            .csrf(csrf -> csrf
                .csrfTokenRepository(csrfTokenRepository)
            )
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED))
            )
            .httpBasic(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .logout(logout -> logout
                .logoutUrl("/auth/logout")
                .logoutSuccessHandler((request, response, authentication) ->
                    response.setStatus(204))
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice-secret"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    AuthenticationManager authenticationManager(
            AuthenticationConfiguration configuration) throws Exception {
        return configuration.getAuthenticationManager();
    }
}
```

Significance of the parts directly affecting this lesson:

- `securityContextRepository()` creates **one shared bean**. The filter chain receives this bean to read the context; the controller in the next section uses the same bean to write the context.
- `SessionCreationPolicy.IF_REQUIRED` allows creating a session when needed. Do not use `STATELESS` for a session login example: that mode prevents Spring Security from using `HttpSession` to retrieve `SecurityContext` and usually configures a non-saving repo.
- `.csrf(...)` preserves CSRF protection using `HttpSessionCsrfTokenRepository`. A cookie-based login POST endpoint **must** account for CSRF; a JSON body by itself does not eliminate the risk.
- `.httpBasic(...disable)` and `.formLogin(...disable)` prevent other mechanisms from taking over the login flow. `HttpStatusEntryPoint` makes unauthenticated requests receive `401` instead of redirecting to a form page.
- `sessionAuthenticationStrategy()` intentionally combines two behaviors inherent to standard login filters: rotating the session ID to prevent session fixation and clearing the old CSRF token after login. **A self-authenticating controller must call this strategy itself**; do not assume global configuration invokes it on the controller's behalf.
- `logout(...)` uses Spring Security's logout infrastructure for `POST /auth/logout`; the handler returns `204 No Content`. Because CSRF is enabled, logout POST must also send a valid CSRF token.
- `UserDetailsService` and `BCryptPasswordEncoder` serve the demo. `AuthenticationManager` obtains the manager configured by Spring Security from the user-management bean.
- Do not call `request.getSession(true)` just to force session creation on every request. `HttpSessionSecurityContextRepository` can create a session when saving an authenticated context if policy permits; a session may also already exist because of CSRF.

### 3.3. JSON Endpoint: authenticate -> session strategy -> setContext -> saveContext

`src/main/java/com/example/jsonlogin/LoginController.java`:

```java
package com.example.jsonlogin;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
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
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LoginController {

    private final AuthenticationManager authenticationManager;
    private final SecurityContextRepository securityContextRepository;
    private final SessionAuthenticationStrategy sessionAuthenticationStrategy;

    public LoginController(
            AuthenticationManager authenticationManager,
            SecurityContextRepository securityContextRepository,
            SessionAuthenticationStrategy sessionAuthenticationStrategy) {
        this.authenticationManager = authenticationManager;
        this.securityContextRepository = securityContextRepository;
        this.sessionAuthenticationStrategy = sessionAuthenticationStrategy;
    }

    public record LoginRequest(String username, String password) {}

    @GetMapping("/api/csrf")
    public CsrfToken csrf(CsrfToken csrfToken) {
        return csrfToken;
    }

    @PostMapping(
        path = "/auth/login",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<Map<String, String>> login(
            @RequestBody LoginRequest body,
            HttpServletRequest request,
            HttpServletResponse response) {

        Authentication authentication;
        try {
            authentication = authenticationManager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    body.username(), body.password()
                )
            );
        } catch (AuthenticationException ex) {
            SecurityContextHolder.clearContext();
            securityContextRepository.saveContext(
                SecurityContextHolder.createEmptyContext(), request, response
            );
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(Map.of("error", "invalid_credentials"));
        }

        // Controller logs in manually, so it must execute the session strategy.
        sessionAuthenticationStrategy.onAuthentication(
            authentication, request, response
        );

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);

        // Step that determines whether login persists on the next request.
        securityContextRepository.saveContext(context, request, response);

        return ResponseEntity.ok(Map.of(
            "username", authentication.getName()
        ));
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }
}
```

**Read the seven key operations in order:**

1. Receive JSON via `@RequestBody LoginRequest`. This is a request DTO, not a trusted `Authentication` object.
2. Call `UsernamePasswordAuthenticationToken.unauthenticated(...)`. Do not set `authenticated=true` or construct a "logged-in" token just because the client sent a username.
3. `authenticationManager.authenticate(...)` checks credentials and returns an `Authentication` accepted by the authentication provider. On failure, `AuthenticationException` is handled as JSON `401` with a generic message, without revealing "user does not exist" or "wrong password".
4. `sessionAuthenticationStrategy.onAuthentication(...)` runs session-related handling on **successful login**. In the demo, if a session exists, the ID is rotated to reduce fixation risk; the old CSRF token is cleared.
5. `SecurityContextHolder.createEmptyContext()` creates a new context; `context.setAuthentication(authentication)` attaches the verified principal.
6. `SecurityContextHolder.setContext(context)` lets code within the **current request** see the newly logged-in user.
7. `securityContextRepository.saveContext(context, request, response)` **writes the context** to the repository before the response completes. Subsequent requests can then reload the user from the session.

To handle failed logins cleanly in the example, the controller also clears/saves an empty context if `AuthenticationManager` rejects the credentials. This prevents a failed login attempt from accidentally keeping a prior logged-in session. In a real application, how an old session is handled when a user attempts to switch accounts must follow product policy.

The snippet above presents the main flow; before going to production, add input validation (non-null and non-blank username/password), rate limiting/throttling, `SessionAuthenticationException` handling, secure auditing, and session lifecycle rules per system design.

## 4. Why Must saveContext Be Called Even After setAuthentication?

Separate the **two data directions**:

- `SecurityContextHolder.setContext(context)`: updates the context of the currently running request.
- `SecurityContextRepository.saveContext(context, request, response)`: writes the context to where subsequent requests can read it.

When handling a new request, `SecurityContextHolderFilter` loads the context from the repo. At the end of the request, the context in the holder is cleared. Therefore, setting only in the holder without saving loses effect across requests under explicit-save configuration.

`HttpSessionSecurityContextRepository` typically stores the context as a session attribute named `SPRING_SECURITY_CONTEXT`. That attribute name is an implementation detail useful when debugging; application code should use the `SecurityContextRepository` interface instead of calling `session.setAttribute(...)` directly.

**Common wrong order:**

```java
SecurityContextHolder.setContext(context);
response.getWriter().write("{\"ok\":true}");
response.flushBuffer();  // response may already be committed
securityContextRepository.saveContext(context, request, response);
```

The snippet above is an example of **what not to do**: a committed response makes creating/updating the session cookie unreliable. Always save the context **before** writing or flushing the response.

**Another insufficient workaround:**

```java
request.getSession().setAttribute("loggedIn", true);
```

A custom flag like that does not turn the request into an `Authentication` recognized by Spring Security. `AuthorizationFilter` reads the security context, not a custom `loggedIn` attribute.

## 5. Testing via HTTP and Observing the Session Cookie

From the Boot project directory containing the wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell uses `.\gradlew.bat bootRun`. The commands below illustrate on **Bash with curl and jq** (to read JSON), using the demo account in `SecurityConfig`:

```bash
# 1. Fetch CSRF token; save session cookie to file.
curl -s -c cookies.txt -b cookies.txt \
  http://localhost:8080/api/csrf > csrf.json

# 2. Read token returned by the server.
TOKEN=$(jq -r '.token' csrf.json)

# 3. JSON login, send CSRF header, receive/update session cookie.
curl -i -c cookies.txt -b cookies.txt \
  -H 'Content-Type: application/json' \
  -H "X-CSRF-TOKEN: $TOKEN" \
  --data '{"username":"alice","password":"alice-secret"}' \
  http://localhost:8080/auth/login

# 4. New request: do not send username/password, only send cookie.
curl -i -b cookies.txt http://localhost:8080/api/me
```

**Expected observations:**

- Step 1: `200` with JSON containing `headerName`, `parameterName`, and `token`; the actual token varies per session/request.
- Step 3: `200` with JSON `{"username":"alice"}`. A `Set-Cookie` header may be emitted or update the session ID, especially when login rotates the session ID.
- Step 4: `200` with JSON `{"username":"alice"}` even though no password was sent in this request. This is the primary proof that the repository saved and restored the context.
- If you run step 4 **without the cookie jar**, the expected response is `401` because the server does not recognize the newly logged-in session.
- If you send a wrong password with a valid CSRF token, login returns `401 {"error":"invalid_credentials"}`; subsequent requests should not mistakenly inherit identity from the failed attempt.

The cookie name is usually `JSESSIONID` with default Servlet containers; when integrating Spring Session or a gateway layer, the name may differ. Do not infer an authenticated user merely from `Set-Cookie`: CSRF or other features can also create a session before login.

**Simulating failure due to missing CSRF:**

```bash
curl -i -c cookies.txt -b cookies.txt \
  -H 'Content-Type: application/json' \
  --data '{"username":"alice","password":"alice-secret"}' \
  http://localhost:8080/auth/login
```

With the configuration above, this POST request lacks `X-CSRF-TOKEN` and will be blocked by the CSRF filter with `403` **before** the controller runs. Do not diagnose that as a wrong password. When testing login with Postman/curl, remember to fetch the token and send the same session's cookie.

### After Login: The Old CSRF Token Is Invalidated

In the demo, `CsrfAuthenticationStrategy` clears the old token upon successful login. If the client still performs POST/PUT/DELETE operations, it must call `GET /api/csrf` again to obtain a new token after login and send the new token on state-changing requests.

Sample logout uses `POST /auth/logout` and the post-login CSRF token:

```bash
NEW_TOKEN=$(curl -s -c cookies.txt -b cookies.txt \
  http://localhost:8080/api/csrf | jq -r '.token')

curl -i -c cookies.txt -b cookies.txt \
  -X POST -H "X-CSRF-TOKEN: $NEW_TOKEN" \
  http://localhost:8080/auth/logout

curl -i -b cookies.txt http://localhost:8080/api/me
```

Expected result: logout returns `204`, and `/api/me` after logout returns `401`. Spring Security's logout is responsible for clearing the context and invalidating the session as configured; manually clearing only the holder variable is not enough to revoke a persisted session.

## 6. MockMvc Testing: Difference Between Same Request and Next Request

Add file `src/test/java/com/example/jsonlogin/JsonLoginTest.java`:

```java
package com.example.jsonlogin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
@AutoConfigureMockMvc
class JsonLoginTest {

    @Autowired
    MockMvc mvc;

    @Test
    void loginPersistsAuthenticationInSession() throws Exception {
        MvcResult loginResult = mvc.perform(post("/auth/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"alice\",\"password\":\"alice-secret\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) loginResult.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void loginSessionIsNotReusedWithoutSessionCookie() throws Exception {
        mvc.perform(post("/auth/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"alice\",\"password\":\"alice-secret\"}"))
            .andExpect(status().isOk());

        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordReturnsUnauthorized() throws Exception {
        mvc.perform(post("/auth/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"alice\",\"password\":\"wrong\"}"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("invalid_credentials"));
    }

    @Test
    void csrfIsRequiredForJsonLogin() throws Exception {
        mvc.perform(post("/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"alice\",\"password\":\"alice-secret\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void protectedApiRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }
}
```

Run:

```bash
./gradlew test
```

`.with(csrf())` is a `spring-security-test` helper for MockMvc that constructs a POST request with valid CSRF. It **does not initialize a login session**. The most important case is `loginPersistsAuthenticationInSession`: take the session from the login response and use that session in a **separate** GET request; if you only called `SecurityContextHolder.setContext(...)` and omitted `saveContext(...)`, this test exposes the cross-request authentication loss.

MockMvc simulates Servlet requests/sessions in the test process; to verify real cookies issued by the container/proxy and `Secure`/`SameSite`/`HttpOnly` attributes, add real HTTP integration tests or verify in the deployed environment.

## 7. Important Boundaries of "Saving SecurityContext"

### 7.1. Session Cookie vs Access Token

In this example, the client receives/holds a **session identifier cookie**. The server uses the cookie to locate `HttpSession` and load `SecurityContext`. You do not need to issue a JWT just to prove a post-login request; adding a JWT to the design changes the authentication model and does not belong to this session-context-saving flow.

Still, sessions need timeout policies, logout invalidation, storage when scaling horizontally, and proper cookie attributes. If the browser does not send the cookie back due to domain/path mismatches, `SameSite`, `Secure`, CORS, or `credentials`, the server cannot locate the session even if you called `saveContext`.

### 7.2. Session Fixation When Writing Your Own Login Endpoint

Standard Spring Security login filters can execute `SessionAuthenticationStrategy` after successful authentication. With a **manual controller**, you must invoke it inside the flow you own. `ChangeSessionIdAuthenticationStrategy` rotates the session ID when a session already exists (Servlet 3.1+), avoiding reuse of an identifier fixed by an attacker.

Do not confuse `sessionManagement(session -> session.sessionFixation(...))` with guaranteed execution inside a self-written controller. If the app needs concurrent session limits, you must integrate the relevant strategies (session registry, concurrent-session control, session registration) into the authentication flow; the current demo illustrates only session ID and CSRF.

### 7.3. CSRF and JSON Login

With cookie-based authentication, the browser automatically attaches cookies on matching requests. Even when login uses JSON, the application still needs a CSRF threat model, especially if used by browsers.

- Spring Security enables CSRF for unsafe HTTP methods by default.
- `permitAll()` only waives the **login requirement** for the endpoint; it **does not** waive CSRF for POSTs.
- The demo exposes `GET /api/csrf` before login; the frontend sends the returned token in `X-CSRF-TOKEN` along with the corresponding cookie.
- After login/logout, strategies/handlers may clear the old token; the client fetches a new token.
- For cross-origin SPAs, configure CORS/credentials and cookies properly; `fetch` usually needs `credentials: "include"` when sending cookies to an allowed origin. Never carelessly configure wildcard origins with credentials.

Never disable `csrf` globally just to "make POST login work" when the app uses browsers/cookies.

### 7.4. Saved Successfully, Yet the Next Request Still Returns 401

Check in order:

| Symptom | Common cause | How to verify |
|---|---|---|
| Login `200`, immediately followed by `GET /api/me` returning `401` | Forgot `saveContext` | Check whether `SecurityContextRepository.saveContext(...)` is called |
| Saved, yet still `401` | Controller and filter chain use different repositories, or `NullSecurityContextRepository` is active | Compare repository configs and which chain matches the URL |
| Other requests do not receive the session | Cookie not saved/resent, path/domain/SameSite/Secure/CORS | Inspect `Set-Cookie` and then `Cookie` on the next request |
| Session is not created | `STATELESS`, non-saving repository, or save happens too late | Check `SessionCreationPolicy` and when the response commits |
| Intermittent login loss when switching servers | Session stored locally on each instance | Use a shared session store/Spring Session or consistent routing |
| `POST /auth/login` immediately returns `403` | Missing/invalid CSRF token | Check CSRF filter and that token belongs to the same session cookie |
| Wrong password returns `403` | Request never reached controller due to CSRF | Distinguish CSRF failures from `AuthenticationException` |
| User switched, yet session ID did not change | Controller did not invoke session strategy | Invoke strategy after authentication and test session fixation |
| Still recognized after logout | Cleared holder only without invalidating session/saved context | Use the logout mechanism and verify on a subsequent request |
| Login succeeded, yet roles are wrong | `AuthenticationManager` returned wrong authorities or they were lost | Inspect authenticated `Authentication.getAuthorities()` and authorization rules |

**Never log** raw `Authorization`, JSON passwords, session IDs, CSRF tokens, or an entire `SecurityContext`. Log only safe metadata such as correlation ID, authenticated username (if policy allows), outcome category, and timestamp.

### 7.5. Where Is SecurityContext Stored Across Multiple Application Instances?

`HttpSessionSecurityContextRepository` stores in the Servlet environment's HTTP session. A single container may use local memory; when running multiple instances, ensure subsequent requests reach the corresponding session, typically via a shared session store like Spring Session with an appropriate backend or consistently designed sticky-session infrastructure.

Session login does not automatically solve revoking all sessions of a user, timeouts, rotation, concurrent-login limits, or cookie security. Those capabilities require dedicated policies and configuration.

### 7.6. Do Not Use "Manual Save" for Every Login Mechanism

When using `formLogin`, OAuth2 login, or authentication filters provided by Spring Security, the framework usually already manages context persistence and associated success/failure steps. This lesson is for **building your own JSON endpoint that calls AuthenticationManager in a controller/custom filter**. Only touch the repository directly when you clearly understand the responsibilities you are taking on.

## 8. Implementation Checklist

- [ ] `AuthenticationManager.authenticate(...)` creates a valid `Authentication` from client-supplied credentials.
- [ ] A new `SecurityContext` is created and `Authentication` is set on it.
- [ ] `SecurityContextHolder` is updated for the current request.
- [ ] The same `SecurityContextRepository` is shared between the filter chain and controller.
- [ ] `saveContext(context, request, response)` is called before the response commits.
- [ ] Session policy allows reading/writing sessions (`IF_REQUIRED` in the demo); `STATELESS` is not configured against intent.
- [ ] Manual login invokes `SessionAuthenticationStrategy` properly, covering session fixation, CSRF, and other strategies if required by the system.
- [ ] Subsequent requests with the same session cookie restore authentication; requests without the cookie are rejected.
- [ ] Login POST has appropriate CSRF protection; the client re-fetches CSRF tokens after login/logout when needed.
- [ ] Logout invalidates the session; cookies have appropriate `Secure`, `HttpOnly`, `SameSite` flags and all login traffic runs over HTTPS.
- [ ] Tests cover valid login, invalid login, missing CSRF, subsequent request with session, and subsequent request without session.

**References:**

- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
