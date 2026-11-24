# `SessionAuthenticationStrategy` and Saving `SecurityContext` After Authentication (Spring Security Servlet)

When a user enters a valid username and password in a Spring MVC application, you have only solved **part** of logging in. The system must also decide how to handle the **HTTP session**, mitigate session fixation, decide whether multiple concurrent sessions are permitted, and most importantly: **is the `SecurityContext` holding the authenticated `Authentication` saved so subsequent requests recognize the user?**

In Spring Security Servlet, these two responsibilities are related yet **not the same**:

- **`SessionAuthenticationStrategy`**: executes policies tied to a **successful authentication event**, such as rotating the session ID against session fixation, enforcing session limits, registering sessions, or refreshing CSRF state per configuration.
- **`SecurityContextRepository`**: loads and saves the **`SecurityContext`**. In session-based form login, the repository lets a follow-up request sharing the same session restore the verified `Authentication`.

`SecurityContextHolder` only holds the context for the current processing thread; `HttpSession` holds state across multiple requests; and `SessionAuthenticationStrategy` primarily enforces **session policy when a login session is established**. Distinguishing them properly prevents bugs like "login succeeds yet refreshing loses login," improper session ID rotation, and stateless configs mixed into form login.

This lesson focuses on **Spring Security Servlet / Spring MVC**, typically Spring Security 6.x and Java 17+. The Spring Boot 3.3.5 milestone in examples simply pins a clear dependency set; it does not imply it is the latest or still-supported version at the time of reading.

## 1. Five Concepts to Identify Before Configuring

**`Authentication`.** The result of identity verification, containing principal and authorities. Before authentication, `UsernamePasswordAuthenticationToken` represents untrusted username/password input. Only after `AuthenticationManager` returns a successful result can the system treat it as an authenticated `Authentication`.

**`SecurityContext`.** The object holding `Authentication` for security processing. An empty context existing does not mean a user is logged in.

**`SecurityContextHolder`.** The API providing access to the current context, typically using a thread-bound strategy in Servlet. Web security filters populate/clear it per request; **it is not itself a cross-request login store**.

**`SecurityContextRepository`.** The contract for loading and saving context across defined boundaries. In session-based web login, an appropriate repository can use `HttpSessionSecurityContextRepository`; Spring Security also has `RequestAttributeSecurityContextRepository` and `DelegatingSecurityContextRepository`.

**`SessionAuthenticationStrategy`.** The contract receiving a successful authentication result along with `HttpServletRequest` and `HttpServletResponse` to execute session policies. It **does not replace** `PasswordEncoder`, `AuthenticationManager`, or `SecurityContextRepository`.

A primary method of the strategy:

```java
void onAuthentication(
    Authentication authentication,
    HttpServletRequest request,
    HttpServletResponse response
) throws SessionAuthenticationException;
```

This is the conceptual API signature; it is not a standalone Java file. Execution happens after obtaining a successful `Authentication` from the manager, within the configured filter flow. The strategy can throw `SessionAuthenticationException`, causing the login session to be rejected under policy even with valid credentials.

## 2. Form Login Overview: Where Does the Session Strategy Sit?

For `UsernamePasswordAuthenticationFilter` (extending `AbstractAuthenticationProcessingFilter`), the typical flow is:

```text
Browser
  |
  | POST /login (username, password, CSRF token per configuration)
  v
CsrfFilter and preceding security filters
  |
UsernamePasswordAuthenticationFilter
  |
  +-- requiresAuthentication(request)?
        |
        +-- NO  -> continue down filter chain
        |
        +-- YES -> attemptAuthentication(...)
                     |
                     v
                AuthenticationManager
                     |
                AuthenticationProvider
                     |
          Authentication succeeds / exception / null
                     |
                     +-- SUCCESS -------------------------+
                     |                                   |
                     |  SessionAuthenticationStrategy    |
                     |  .onAuthentication(...)          |
                     |                                   |
                     |  successfulAuthentication(...)   |
                     |    -> SecurityContextHolder      |
                     |    -> SecurityContextRepository  |
                     |       .saveContext(...)           |
                     |    -> remember-me/event           |
                     |    -> SuccessHandler/redirect     |
                     |                                   |
                     +-- EXCEPTION -> FailureHandler     |
                     +-- NULL -> wait for next step      |
```

With the standard form login filter, **the session strategy usually runs before `successfulAuthentication(...)`**, and the save-context call occurs during success handling via the filter's repository. This makes sense because rotating the session ID, checking session limits, or registering the session must normally complete before redirecting the user to the post-login page.

Other authentication flows (HTTP Basic, OAuth2, Resource Server, custom filters) have different mechanisms and invocation points. Do not assume every authentication filter extends `AbstractAuthenticationProcessingFilter` or automatically invokes the same strategy. This lesson covers **form login on Servlet**.

### Three Distinct Moments

| Moment | Primary component | Question answered |
|---|---|---|
| Credential verification | `AuthenticationManager` / provider | Are the username/password valid? |
| Session policy enforcement | `SessionAuthenticationStrategy` | Should the current session be kept / rotated / registered / limited? |
| Auth state persistence | `SecurityContextRepository` | How will the context be loaded on the next request? |

**A new session ID does not mean `SecurityContext` was saved.** And **`SecurityContextHolder.setContext(...)` does not mean the strategy ran fixation protection.** Both duties must succeed together, without assuming one completes the other.

## 3. Why Is Session Fixation a Major Post-Login Concern?

**Session fixation** occurs when an attacker forces a victim to use a known session identifier and then exploits the victim logging in successfully under that session. If the session ID is not changed when elevating state from anonymous to authenticated, the old identifier may still represent the logged-in session.

Conceptual attack steps:

1. A session identifier exists before the victim logs in.
2. The attacker gets the victim's browser to adopt that identifier.
3. The victim completes login.
4. If the session ID remains unchanged in the authenticated session and the attacker knows it, session hijacking risk rises.

**Critical defense:** rotate the session identifier upon successful authentication and apply proper session management controls. `Secure`/`HttpOnly` cookies, TLS, reverse proxy setup, `SameSite`, timeouts, and logout are also independent defense layers.

Spring Security Servlet provides related strategies:

- **`ChangeSessionIdAuthenticationStrategy`:** uses the Servlet API to change the existing session's ID, usually the right choice on modern Servlet containers (Servlet 3.1+) and the common default for session fixation protection today.
- **`SessionFixationProtectionStrategy`:** handles creating a new session and migrating/evaluating session attributes; useful to understand when maintaining older apps or containers.
- **`NullAuthenticatedSessionStrategy`:** performs no session change during `onAuthentication`. Not a safe default replacement for a session-based website just to avoid integration bugs.

In Spring Security configuration, options like `sessionFixation().changeSessionId()`, `migrateSession()`, `newSession()`, and `none()` have different consequences. Never treat "skipping session ID rotation" as a performance optimization. When needing to preserve HTTP session attributes, test exactly which attributes exist before/after login; changing sessions can affect bound objects and Servlet lifecycle hooks.

### Changing the Session ID Does Not Create New Credentials

Credentials are still verified by `AuthenticationManager`. The strategy only updates management of the issued **session**. After rotating the session ID, the browser must receive and send back the valid session identifier on the next request; if proxies, cookie path/domain, or clients drop the cookie, the app can still revert to anonymous even after successful auth.

**Never log or put session IDs into URLs.** A session ID acts like a credential while the session is active; placing it in logs/analytics/URLs creates a new leak path.

## 4. Choosing the Right `SessionAuthenticationStrategy`

| Implementation | Responsibility | Practical notes |
|---|---|---|
| `ChangeSessionIdAuthenticationStrategy` | Rotates session ID after auth | Commonly used with Servlet session fixation protection on modern containers |
| `SessionFixationProtectionStrategy` | Replaces session and handles attribute migration per config | Watch out for session-scoped beans, attribute migration, and callbacks |
| `ConcurrentSessionControlAuthenticationStrategy` | Enforces max concurrent sessions per user | Can reject new login or expire old sessions depending on policy |
| `RegisterSessionAuthenticationStrategy` | Registers the post-auth session into `SessionRegistry` | Useful in concurrent session management setups |
| `CompositeSessionAuthenticationStrategy` | Invokes a list of strategies in order | Order matters greatly; do not reorder arbitrarily |
| `CsrfAuthenticationStrategy` | Refreshes CSRF token state during authentication | Relates to CSRF defense, not long-term `Authentication` storage |
| `NullAuthenticatedSessionStrategy` | Leaves session unchanged | Consider only when the session design doesn't need it and other defenses exist |

In a concurrency-control setup, a composite can run **check session count first**, **rotate/establish session**, and then **register session**. That avoids recording a new session in the registry when policy rejects the login. Spring Security builds composite strategies from the DSL, so **do not build a custom composite to replace the default** if DSL options already cover your needs.

### Concurrent Sessions Are More Than Just a Number

With a rule like "at most one session per user," you must clearly define:

- Is a new login allowed while expiring the old session?
- Or is the new login rejected while an old session remains active?
- How are sessions cleared/released from the registry after logout, timeout, or server restart?
- In multi-instance environments, are the registry and session store synchronized/consistent?

In-memory `SessionRegistryImpl` behaves differently from a distributed session registry/store; never assume two independent servers share awareness of a user's sessions. Test session limits using separate browsers or isolated cookie jars; opening another tab in **the same browser session** is usually not an independent session.

## 5. Where Is `SecurityContext` Saved After the Strategy Runs?

Spring Security uses `SecurityContextRepository` to load/save context. In Spring Security 6, common servlet configs use a `DelegatingSecurityContextRepository` combining:

```java
SecurityContextRepository repository =
    new DelegatingSecurityContextRepository(
        new RequestAttributeSecurityContextRepository(),
        new HttpSessionSecurityContextRepository()
    );
```

This is an **illustrative Java snippet**, requiring proper dependencies and imports; not a standalone application.

The two delegates cover two scopes:

- **`RequestAttributeSecurityContextRepository`:** stores context on the current `HttpServletRequest`. Useful across dispatches (such as `ERROR`) within the same request when the security chain handles them properly.
- **`HttpSessionSecurityContextRepository`:** stores context in the HTTP session so subsequent requests sharing the valid session can reload it.
- **`DelegatingSecurityContextRepository`:** combines loading and saving capabilities across delegates. It is not a distributed store and does not grant infinite sessions.

`SecurityContextHolder` holds info during current processing and is typically cleared by a filter at the request boundary. Seeing the holder empty after a response **does not by itself prove** login was lost. Check the repository and whether a new request reloads the context.

### Example Post-Form-Login Timeline

```text
REQUEST #1: POST /login
  - AuthenticationManager verifies valid username/password
  - SessionAuthenticationStrategy applies fixation / concurrency policy
  - SecurityContext is created and populated with Authentication
  - SecurityContextRepository.saveContext(context, request, response)
  - SuccessHandler returns redirect (e.g., /account)
  - Response may send Set-Cookie session ID

REQUEST #2: GET /account, client sends the same valid session cookie
  - SecurityContextHolderFilter / repository loads context
  - Authorization receives authenticated Authentication
  - Controller processes request
  - Request ends: holder is cleared per lifecycle

REQUEST #3: same URL without the session cookie
  - No context found in old session
  - Application may prompt for login again
```

**A 302 result from POST login is not enough to prove context persistence.** You must issue a follow-up protected request with the newly created session and verify the actual `Authentication`.

### HTTP Sessions Do Not Mean Cookies Hold Passwords

Session cookies normally carry a **session identifier**, not raw passwords or the full `SecurityContext` by default. The context lives server-side in the session repository. When using a custom session store, check serialization, persistence, session expiration, and cluster policies rather than assuming "cookies are already safe."

## 6. Key Shift in Spring Security 6: Explicit Save

In many Spring Security 6 configurations, `SecurityContextHolderFilter` loads or provides deferred loading of context into the holder, then clears it when the request ends. **This filter does not automatically save every mutation in the holder back to the repository** as older examples with `SecurityContextPersistenceFilter` might lead readers to expect.

In a custom login flow, the following snippet **is not enough** to persist login state to the next request:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);
```

Here `authenticated` must be a result verified by the manager/provider. The snippet is a **fragment inside a handler with valid variables**, not something that authenticates credentials or registers filters itself.

If a custom flow must persist state, it must ensure an appropriate call to the repository:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
```

Still, this **is not the whole login flow**: there are also session strategies, session fixation protection, remember-me, failure handling, CSRF, responses, and design-specific duties. When using Spring Security's `UsernamePasswordAuthenticationFilter`, **let the filter/framework handle** that standard plumbing instead of repeating `saveContext` in controllers or success handlers.

**In particular:** `SessionAuthenticationStrategy.onAuthentication(...)` is not the API that saves `SecurityContext`. A strategy may rotate the session ID successfully while custom code forgets to save the context; the browser receives a new session yet still lacks `Authentication` on the next request. Conversely, writing context to the session while skipping session fixation policy introduces its own risks.

### Save Before the Response Is Committed

When creating an HTTP session and sending a cookie to the client, `saveContext` must happen before the response commits or redirects when required by the flow. Once a response has been flushed, the server may be unable to add `Set-Cookie` or update metadata properly. Reordering into "redirect first, save later" in custom filters causes subtle bugs.

## 7. Do You Need to Define a `SessionAuthenticationStrategy` Bean for Form Login?

**Usually no.** The `formLogin(...)` DSL coordinates `sessionManagement(...)`, the security context repository, and standard filters automatically in Spring Security. Declaring a `SessionAuthenticationStrategy` bean yourself does not guarantee every authentication filter automatically picks it up; DSL-configured filters obtain strategies from shared objects/configurers.

If you only need session fixation protection, concurrency caps, or policy selection, **start with the DSL**. Only implement a custom strategy for concrete business needs with thorough HTTP path tests.

Example Java bean configuration in a Spring Boot 3.x **Servlet** project:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public").permitAll()
            .anyRequest().authenticated())
        .formLogin(form -> form
            .defaultSuccessUrl("/account", true)
            .permitAll())
        .sessionManagement(session -> session
            .sessionFixation(fixation -> fixation.changeSessionId()))
        .build();
}
```

This is a **method fragment** needing Spring Security imports; a runnable project is in section 9. On Servlet containers supporting session ID rotation, the config above explicitly states session fixation protection intent. Never add `sessionFixation().none()` just to make tests "pass easily."

### `SessionCreationPolicy` Differs from `SessionAuthenticationStrategy`

| Policy | Purpose | Practical semantics |
|---|---|---|
| `ALWAYS` | Spring Security actively uses/creates a session | Suits apps intentionally using sessions |
| `IF_REQUIRED` | Creates a session only when a component needs one | Common for form-login websites |
| `NEVER` | Security does not actively create a new session, yet may use an existing one | Not an absolute stateless mode |
| `STATELESS` | Does not create sessions and does not use sessions to load `SecurityContext` | Usually fits bearer-token APIs, unsuitable if persisting form login via sessions |

`SessionCreationPolicy` governs **how Spring Security uses sessions**, not the session ID rotation algorithm. Nor does it stop other servlet components from creating sessions or automatically disable CSRF. In default form login, configuring `STATELESS` while expecting browsers to stay logged in via `HttpSession` after a 302 is a design contradiction.

You can use multiple `SecurityFilterChain` beans: one stateful web form-login chain and one stateless API chain. Check matchers and ordering carefully so login URLs do not fall into the wrong chain.

## 8. Notes on Session Fixation and Session Attributes

At the moment of successful login, the browser may already have a session holding pre-login data: CSRF tokens, request caches, flash attributes, anonymous carts, language preferences, etc. Session replacement requires considering which data should be kept.

- `changeSessionId()` generally preserves the existing session and attributes while rotating the ID; this is the suitable choice in modern Servlet environments.
- `migrateSession()` or `newSession()` have different session-creation/attribute-migration policies. Read your exact version's documentation and test lifecycle callbacks on session-scoped components.
- Never blindly copy sensitive attributes from an anonymous session to an authenticated session without understanding trust boundaries. An attribute created during an anonymous request could influence post-login behavior.
- Ensure reverse proxies, cookie domain/path, HTTPS, and session tracking align so clients receive the new ID; when cookies fail to return, it looks like a lost session.

Do not conclude session fixation protection ran solely from seeing a `JSESSIONID`. Compare the session identifier **before and after** authentication in a controlled test environment, or use proper integration tests. Avoid printing real IDs into logs/reports; test assertions suffice.

## 9. Hands-On Spring Boot MVC Example: Session and `SecurityContext` Survive Redirect

The example uses **Java 17+, Maven, Spring Boot 3.3.5**, and Spring Security managed by Boot. This is a reproducible lesson baseline, not a support lifecycle guarantee; real products must choose current supported versions.

Test goals:

1. Visiting `/account` unauthenticated redirects to the login page.
2. Valid login POST with CSRF token redirects via success handler to `/account`.
3. The **post-redirect** request using the saved session reads the principal.
4. A new request without the corresponding session remains unauthenticated.
5. Wrong-password login does not result in authenticated access.
6. Login POST missing CSRF token is blocked before credential verification.

### 9.1. Project Structure

```text
session-login-demo/
├── pom.xml
└── src/
    ├── main/java/example/sessionlogin/
    │   ├── SessionLoginApplication.java
    │   ├── WebSecurityConfig.java
    │   └── AccountController.java
    └── test/java/example/sessionlogin/
        └── SessionLoginTest.java
```

### 9.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>session-login-demo</artifactId>
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

Do not declare independent Spring Security versions per module: the Spring Boot parent aligns compatible dependency versions.

### 9.3. Spring Boot Entry Point

Create `src/main/java/example/sessionlogin/SessionLoginApplication.java`:

```java
package example.sessionlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionLoginApplication.class, args);
    }
}
```

### 9.4. Security Configuration

Create `src/main/java/example/sessionlogin/WebSecurityConfig.java`:

```java
package example.sessionlogin;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("demo-only-password"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .defaultSuccessUrl("/account", true)
                .failureUrl("/login?error")
                .permitAll())
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.changeSessionId()))
            .build();
    }
}
```

Explanation:

- `UserDetailsService` and `PasswordEncoder` create a **demo-only** account. Never use these credentials in real environments.
- `formLogin(...)` enables Spring Security's login POST processing; no manual `@PostMapping("/login")` is needed.
- `sessionFixation(...changeSessionId())` explicitly configures session ID rotation upon login.
- `defaultSuccessUrl("/account", true)` fixes the redirect for testing; without the `true` flag, saved requests could alter the final URL.
- `csrf` is not disabled. Form POSTs need a valid CSRF token under a session/cookie website design.
- No custom `SecurityContextRepository` is declared unnecessarily; standard integrated configuration handles context persistence.

### 9.5. Controller

Create `src/main/java/example/sessionlogin/AccountController.java`:

```java
package example.sessionlogin;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "PUBLIC_OK";
    }

    @GetMapping("/account")
    public String account(Principal principal) {
        return "Hello, " + principal.getName();
    }
}
```

The controller does not read `HttpSession` directly and contains no logic placing users into `SecurityContext`; security filters handle authentication/authorization. When logged-in users access sensitive data, add proper role-based and ownership authorization checks.

### 9.6. Integration Tests with MockMvc

Create `src/test/java/example/sessionlogin/SessionLoginTest.java`:

```java
package example.sessionlogin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionLoginTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymousAccess() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC_OK"));
    }

    @Test
    void protectedEndpointWithoutLoginRedirectsToLogin() throws Exception {
        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string("Location", containsString("/login")));
    }

    @Test
    void authenticatedSessionWorksOnFollowingRequest() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "demo-only-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/account"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello, student"));

        // A new request WITHOUT the saved session lacks the previous principal.
        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void wrongPasswordDoesNotLogUserIn() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "wrong-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void loginPostWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/login")
                .param("username", "student")
                .param("password", "demo-only-password"))
            .andExpect(status().isForbidden());
    }
}
```

Tests send requests through the **Spring Security servlet filter chain** thanks to `@SpringBootTest` and `@AutoConfigureMockMvc`. The third test does not stop at the redirect response; it checks **the follow-up request using the same `MockHttpSession`**. This gives practical proof that authentication state was saved and reloaded across two requests in the illustrative setup.

This test **does not separately measure whether the session ID changed**, since that requires creating an existing pre-login session and observing ID changes per implementation/Servlet environment. The fixation strategy is explicitly declared, yet production-grade fixation testing should include additional integration tests with an existing session, cookies, and an appropriate real container.

### 9.7. Running the Demo

In the directory containing `pom.xml`, with JDK 17+, Maven, and dependency repositories/cache:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

If source files are in the right places and dependencies resolve, **5 JUnit tests are expected to pass**. Full Maven output varies by machine, so no fixed transcript is shown; this is an expected result rather than a claim of execution here. When running the server on default port 8080, visit `http://localhost:8080/login`, log in with the fixture account, then open `/account`. The exact response body from the controller with the authenticated principal is:

```text
Hello, student
```

The default login page, headers, cookies, and HTTP redirect URLs can vary by config/dependencies and reverse proxy. Never deploy those fixture username/password credentials to a public environment.

## 10. Limiting Concurrent Sessions: Another `SessionAuthenticationStrategy` Case

If business rules require at most one active session per account, you can use Spring Security's DSL config, for example (a snippet inside `SecurityFilterChain`, not a standalone Java file):

```java
.sessionManagement(session -> session
    .maximumSessions(1)
    .maxSessionsPreventsLogin(true))
```

Typical meaning: once a tracked session exists for the user, a new login exceeding the limit can be rejected instead of evicting the old session. Under the alternative policy, the old session is marked expired and handled on its next request.

**Verify in reality:** the session registry, session registration/destruction mechanisms, servlet session lifecycle listeners, and multi-node environments. Never treat `maximumSessions(1)` as a "global account lock": if the registry runs locally on a single server, multiple instances may not share session counts. Proper distributed operation may require additional dependencies/infrastructure; consult the documentation for your Spring Security version.

Concurrency control is **a post-authentication check**; it still does not replace the context persistence repository. A user authenticated by the provider yet rejected by the session strategy can be handled as a session-policy login failure. Distinguish this from wrong-password failures for logging and user guidance without leaking session details to unauthorized parties.

## 11. Stateless APIs and Session-Based Form Login Do Not Share Assumptions

A website with form login normally relies on cookies/sessions so the browser sends subsequent requests. Conversely, a resource server validating bearer tokens normally verifies tokens **per request** without storing authentication in `HttpSession`.

Illustrative snippet **for a separate stateless API**, not an adjustment to paste into section 9's form-login demo:

```java
http
    .securityMatcher("/api/**")
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
    .oauth2ResourceServer(oauth -> oauth
        .jwt(Customizer.withDefaults()));
```

This snippet requires Resource Server dependencies and configuration of trusted issuers/JWKs, audience/claims, and proper authorization rules. Not anyone presenting a JWT string is trustworthy. For such APIs, attempting to save bearer authentication in an HTTP session contradicts the stateless goal.

When combining multiple chains:

- Web chain handles `/login`, `/account` and uses sessions.
- API chain handles `/api/**`, accepts bearer tokens, and stays stateless.
- Matchers and `@Order` must be explicit; ensure a fallback chain protects URLs outside the API.
- CSRF is designed around **how clients send credentials**, not automatically disabled simply because a chain is labeled API.

**`SessionAuthenticationStrategy` does not imply every system must use sessions.** Choose an authentication strategy matching the protocol and required statefulness.

## 12. When Hand-Writing a Login Flow: Responsibilities You Cannot Skip

A custom authentication endpoint can call `AuthenticationManager.authenticate(...)` directly, yet doing so does not automatically trigger all hooks of `UsernamePasswordAuthenticationFilter`.

Minimal conceptual ordering:

```text
1. Safely read credentials, check CSRF/trust boundaries.
2. AuthenticationManager.authenticate(untrustedCredential)
3. On success: SessionAuthenticationStrategy.onAuthentication(...)
4. Create new SecurityContext, set verified Authentication
5. SecurityContextHolder.setContext(context)
6. SecurityContextRepository.saveContext(context, request, response)
7. Remember-me/event/response handler per chosen protocol
8. Redirect/commit response and clear holder per lifecycle
```

Partial Java logic **illustrating inside a custom component with injected dependencies**:

```java
Authentication result =
    authenticationManager.authenticate(unauthenticatedRequest);

sessionAuthenticationStrategy.onAuthentication(result, request, response);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(result);
SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(context, request, response);
// Only then issue the redirect or appropriate response.
```

This **is not a standalone runnable class**: `unauthenticatedRequest` must be an untrusted `Authentication` token; `request`/`response` are Servlet objects; manager, strategy, and repository must come from one consistent security configuration. This short snippet does not yet handle exceptions, CSRF, remember-me, events, timeouts, responses, or session races; never copy it verbatim into production.

Prefer built-in authentication flows whenever possible. When writing custom code, specifically test:

- Is `SessionAuthenticationException` from the strategy translated into an appropriate failure response?
- Is the context saved **before redirecting** and reloaded on the follow-up request?
- Does the cookie/session ID rotate properly when elevating from anonymous to authenticated?
- Is authentication cleared from session/repository and client upon revocation/logout?
- Does double invocation of strategy or double saving occur from running both custom code and standard filters?

Never call `sessionAuthenticationStrategy.onAuthentication(...)` again inside the default form login success handler just to "make sure there is a session." Duplicate execution can rotate session IDs multiple times or corrupt concurrency tracking.

## 13. Logout, Session Timeout, and Permission Updates

**Saving `SecurityContext` after login does not mean permissions live forever.** A session can expire, be invalidated, rotate IDs, be rejected by concurrency policies, or become stale when user permissions change.

During Spring Security's logout flow, the framework can:

- Clear `Authentication` from `SecurityContextHolder` and the repository per configuration.
- Invalidate the HTTP session and clear cookies only when configured and supported by the actual response.
- Execute remember-me logout handlers or identity provider logout mechanisms when designed.

Calling `SecurityContextHolder.clearContext()` on one thread does not necessarily remove the context stored in the session. Conversely, deleting a cookie client-side does not always invalidate the server session; manage both sides per policy.

If a user's privileges are revoked, the `Authentication` saved in the session may still contain old authorities. Business requirements dictate reauthentication, context refresh, or session invalidation policies. The repository does not automatically sync authorities on every user-store change.

## 14. Common Errors: Diagnosing by Symptom

| Symptom | What to check | How to fix |
|---|---|---|
| Login POST returns 302 success, yet next GET to `/account` redirects to login | Forgot `SecurityContextRepository.saveContext` in custom flow, client dropped session cookie, or wrong repository | Check save/load, `Set-Cookie`/`Cookie`, response commit timing, and security chain |
| Right password yet rejected by session policy | `SessionAuthenticationStrategy` threw exception (concurrency/session) | Distinguish manager result from post-auth session check; audit `SessionRegistry` |
| Session ID does not change on login | Session fixation policy inactive, filter uses different strategy, or login missed expected chain | Identify invoked filter/strategy; test session before/after login |
| Session ID changed, yet login is still lost | Strategy ran but repository didn't save context, session didn't reach browser, or cookie path/domain wrong | Verify save call separately and test follow-up request with same session |
| Context set in holder, yet refresh loses user | `SecurityContextHolderFilter` does not auto-save custom flow contexts | Explicitly save to repository when needed and use standard auth filters where possible |
| Logging in from one browser logs out another browser | Concurrency policy caps active sessions | Inspect `maximumSessions`/`maxSessionsPreventsLogin` and registry |
| Limit of one session still allows multiple logins across nodes | Registry/session store not shared across instances | Check Spring Session, clustered session registry, and logout/expiration propagation |
| Login POST missing CSRF token returns 403 before auth | `CsrfFilter` blocked the request | Keep proper CSRF; never disable globally to mask errors |
| Still authenticated after logout | Context not removed from session, remember-me, or SSO re-logged in | Inspect logout handlers, session invalidation, cookies, and IdP |
| Stateless API unexpectedly creates sessions | Request cache, MVC layer, custom code, or another stateful web chain | Identify what created the session; check chain selection and `SessionCreationPolicy` |
| Session shows stale authorities | Context holds old authorities, lacking refresh/revocation policy | Implement appropriate invalidation/reauthentication strategy |
| Tests using `@WithMockUser` pass while production login fails | Mock user bypasses real password manager, strategy, and repository | Add MockMvc tests for `POST /login` and follow-up session requests |

Never guess solely from an HTTP status code. A `403` may be CSRF or authorization; a `302` may be a success redirect or a redirect to login; a `401` may come from an authentication entry point. Identify the active filter/handler and session state before editing code.

## 15. Testing Checklist for Session-Based Form Login

- [ ] Project uses **Servlet** and the right `SecurityFilterChain` for login POST; no reactive config mixed in.
- [ ] `AuthenticationManager` verifies credentials before any successful-login session operations occur.
- [ ] Session fixation protection uses a strategy suited to the Servlet container; pre/post-login session IDs tested when needed.
- [ ] If capping concurrency, clearly define when new logins are rejected vs. expiring old sessions.
- [ ] Context is set in the holder **and saved via the repository** when auth must persist across requests.
- [ ] The context repository used by the login filter matches the repository used to load context on subsequent requests.
- [ ] Cookies have `Secure`/`HttpOnly`/`SameSite` and domain/path matching HTTPS, reverse proxies, and the login flow.
- [ ] Login POST is protected by CSRF suitable for the browser/session model.
- [ ] After success redirect, test a follow-up request with the valid session carrying the principal; a new request without that session does not inherit auth.
- [ ] After logout, session expiry, credential reset, or permission changes, verify revocation policies work.
- [ ] Never rely on `@WithMockUser` as proof that `PasswordEncoder`, `SessionAuthenticationStrategy`, or context repository ran.
- [ ] Never log raw passwords, session IDs, CSRF tokens, or other tokens into logs or test artifacts.
- [ ] With multiple instances, test session stores/registries, routing, failover, and concurrency state.

### Self-Check Questions

**1.** `AuthenticationManager` returns a successful result. Can you redirect immediately and consider login complete?  
**Answer:** Not enough for session-based form login. You need session policy via the strategy, setting/saving the context in the right repository, and then handling the response.

**2.** The strategy rotated the session ID, yet the next request does not recognize the user. Is that contradictory?  
**Answer:** No. Rotating the session ID and saving `SecurityContext` are two separate actions; check the repository, cookies, and save timing.

**3.** In Spring Security 6, is calling `SecurityContextHolder.setContext(context)` alone in a custom controller enough?  
**Answer:** No, if login must persist across multiple requests. Explicit saving typically requires `SecurityContextRepository.saveContext(...)` when a custom flow is not handled by standard filters.

**4.** Does `SessionCreationPolicy.STATELESS` fit a website expecting browsers to send back a session cookie after form login to stay logged in?  
**Answer:** Usually no; that is a conflict between stateless policy and session-based login expectations.

**5.** Does `maximumSessions(1)` guarantee limiting a user globally across all servers when running multiple instances?  
**Answer:** You cannot assume so without checking the session store/registry and cluster synchronization mechanism.

**6.** Can `@WithMockUser` prove that `SessionAuthenticationStrategy` protected against fixation?  
**Answer:** No. That annotation constructs a mock security context without running the full `POST /login` flow. You need integration tests using real/mocked sessions through the filters and comparing session IDs.

**7.** Why should CSRF protection be kept for form login?  
**Answer:** Browsers can send cookies/sessions automatically; login POSTs and state-changing operations must be protected at the credential boundary regardless of whether the password is right or the strategy ran.

**Conclusion:** `SessionAuthenticationStrategy` handles **HTTP session policy after `AuthenticationManager` succeeds**; `SecurityContextRepository` handles **persisting and restoring `SecurityContext` across requests**. In Servlet form login, both are coordinated in order by standard filters. When customizing, verify both **session fixation/concurrency** and **explicit save, cookies, and post-redirect requests**, rather than looking at a single login response.