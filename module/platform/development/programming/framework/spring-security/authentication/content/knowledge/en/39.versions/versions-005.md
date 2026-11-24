# Changes to SecurityContext Persistence and Explicit Save Responsibility

When upgrading an application from **Spring Security 5.x to Spring Security 6.x**, a familiar symptom occurs: a controller authenticates username/password itself, calls `SecurityContextHolder.setContext(...)`, the login request returns HTTP 200, yet **the next request is treated as anonymous** and redirected back to the login page. The password may be completely right, and `Authentication.isAuthenticated()` may be `true` during the first request, yet the `SecurityContext` **was never saved anywhere the next request can read it back**.

The key change in **Spring Security Servlet** is that the default shifted from `SecurityContextPersistenceFilter` — which had logic to **automatically detect and save changes** — to `SecurityContextHolderFilter` — which **only loads the context** without auto-saving. If an application has a **custom login controller/filter**, the side writing the context must **explicitly call `SecurityContextRepository.saveContext(...)`** when it wants the user to stay logged in on subsequent requests.

However, the opposite interpretation is also wrong: “Spring Security 6 no longer saves any login automatically”. **Framework-provided authentication mechanisms**, such as Servlet form login, still coordinate with the repository and perform the necessary steps to persist authentication. Explicit save responsibility matters most in **custom code that replaces/bypasses standard authentication filters** or code that modifies/clears the context expecting changes to survive across requests.

This Knowledge article belongs to the **Versions** group in **Spring Security - authentication**, focusing on **5.x → 6.x behavior (cross-checked against Spring Security 6.5)**, repository/filter concepts, migration, **Java 17+ / Spring Boot 3.5.x** examples, MockMvc tests spanning two requests, and common pitfalls across login, logout, sessions, or custom security filters.

## 1. Understanding SecurityContext: Current Thread vs. Cross-Request State

### 1.1. Three Terms That Are Not Synonymous

- **`Authentication`**: the authentication outcome (principal, authorities, status, and depending on implementation, credentials/details). It does not create an HTTP session on its own.
- **`SecurityContext`**: the object holding the `Authentication` currently used by Spring Security.
- **`SecurityContextHolder`**: how the context is accessed on the current execution thread; by default usually a `ThreadLocal` strategy, managed/cleared by a filter at the end of the request.

Example placed in a method that already has a valid `Authentication authentication`:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
~~~

Those three lines **only prove the current SecurityContext was updated**. If the context holder is cleared when the request finishes without a repository saving it, a new request **cannot automatically restore** the user from that operation.

To use the context on a subsequent request, you need an appropriate persistence mechanism — typically `HttpSessionSecurityContextRepository`/`DelegatingSecurityContextRepository` — and a **timely save call**, or a stateless authentication mechanism that re-verifies the credential/token on every request.

### 1.2. Diagram With and Without Persistence

~~~text
Request 1: POST /api/manual-login
   │
   ├─ AuthenticationManager verifies password
   ├─ Create SecurityContext and set Authentication
   ├─ SecurityContextHolder.setContext(context)
   │          │
   │          ├─ WITHOUT calling repository.saveContext(...)
   │          │      └─ HTTP 200 response then request finishes
   │          │               └─ holder is cleared
   │          │
   │          └─ WITH calling repository.saveContext(context, req, resp)
   │                 └─ repository writes to HTTP session (if appropriate)
   │                        └─ response carries session cookie (when needed)
   ▼
Request 2: GET /api/me
   │
   ├─ SecurityContextHolderFilter asks repository to load context
   │
   ├─ Not saved in request 1 → anonymous / 401 / login redirect
   └─ Saved + client sends back valid session cookie
          → context restored → authenticated / authorized
~~~

**Never store `SecurityContext` by assigning it to a `static` variable or a self-managed `ThreadLocal`.** That is not bound to a user session, can leak principals across requests/threads, fails in a cluster, and does not guarantee security context cleanup.

## 2. What Changed Across Versions?

| Stage | Common Filter/Mechanism | Responsibility of Custom Authentication Code |
| --- | --- | --- |
| **Spring Security 5.x default** | `SecurityContextPersistenceFilter` loads, tracks, and saves context as appropriate when request completes/response commits | Many legacy snippets calling only `setContext(...)` could still be saved automatically |
| **Spring Security 5.8 on upgrade path** | Can proactively enable `requireExplicitSave(true)` to adopt new semantics and fix code | Add explicit `saveContext(...)` before moving fully to 6 |
| **Spring Security 6.x default** | `SecurityContextHolderFilter` **loads** context but does not auto-write changes | When custom code manages authentication and wants cross-request persistence, it must call `SecurityContextRepository.saveContext(...)` |
| **Spring Security 6.5.x** | Continues explicit save semantics in Servlet; built-in form login still handles persistence for its own flow | Inspect custom controllers/filters, logout, and repository/session policies |

**Version 5.8 does not mean every 5.8 project has automatically switched all behavior**: it is a transition branch supporting compatible configuration. Verify the exact filter chain/config of the application rather than just reading the version number in `build.gradle`.

### 2.1. Why Did the Framework Change?

According to the Spring Security migration documentation:

1. `SecurityContextPersistenceFilter` had to track whether the context changed in order to decide whether saving was needed.
2. It had to prevent the bug of **committing a response/redirect before creating a session cookie**, requiring response-wrapper logic right before commit.
3. Automatic change detection sometimes caused **unnecessary writes** to `SecurityContextRepository`/`HttpSession`, especially under complex session management.
4. `SecurityContextHolderFilter` cleanly separates **read/restore/clear** from **save**: the component creating/modifying authentication decides when writing is needed.
5. The new approach is more predictable when code manages context directly, while requiring legacy custom code that relied on implicit save to be updated.

In return, Spring Security 6 lets applications **explicitly decide** when an authentication qualifies for persistence. Not every request that reads a context needs to re-write the session.

### 2.2. The requireExplicitSave(true/false) Option

In Spring Security 6.x Java DSL, illustrative configuration:

~~~java
http.securityContext(securityContext -> securityContext
        .requireExplicitSave(true));
~~~

`true` is the default semantics in Spring Security 6. It causes `SecurityContextHolderFilter` to be configured instead of `SecurityContextPersistenceFilter`. Since Spring Security 6 already uses this default, the line is usually **unnecessary to add**, though it helps readers see the migration target.

Temporary configuration for legacy compatibility:

~~~java
http.securityContext(securityContext -> securityContext
        .requireExplicitSave(false));
~~~

Depending on version, the compatibility setting can revert to semantics based on `SecurityContextPersistenceFilter`. **Do not choose `false` as a permanent workaround just to avoid fixing custom login**. Plan the transition to explicit save, test login/logout paths, and phase out implicit persistence.

**Never place both `SecurityContextHolderFilter` and `SecurityContextPersistenceFilter` in the same filter chain just to “be sure it saves”.** Spring Security 6 docs stress that an application/chain should use **only one of the two** filters.

### 2.3. Do Not Confuse with SessionManagementFilter Changes

Spring Security 6 also shifted several other session responsibilities:

- `SessionManagementFilter` **is not configured by default** as it was in some Spring Security 5 setups.
- With the newer authentication filters, the authentication mechanism itself must invoke the appropriate `SessionAuthenticationStrategy` after authentication succeeds.
- Therefore, custom login needs more than `saveContext`: it may also need session fixation protection, concurrent session rules, remember-me, CSRF, MFA, success/failure handling, and auditing.
- Some legacy DSL options tied to `SessionManagementFilter` do not behave as before or may be rejected depending on version/config; check migration docs.
- **`SecurityContextRepository` and `SessionAuthenticationStrategy` are two separate responsibilities:** the repository saves/restores context; the strategy enforces session policies upon authentication.

`saveContext(...)` can make the next request recover the principal, yet **does not perform the full form login workflow on its own**. For typical web applications, always prefer standard login filters unless there is a compelling reason to write your own.

## 3. SecurityContextRepository: Where Is It Saved?

| Implementation | Characteristics | Limits to Remember |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Uses `HttpSession` to retain context across HTTP requests of the same session | Requires a valid session/cookie; unsuitable if the project is truly stateless |
| `RequestAttributeSecurityContextRepository` | Stores context in a request attribute; useful across dispatches within the **same request** such as ERROR | **Does not** retain authentication across the next independent HTTP request |
| `DelegatingSecurityContextRepository` | Delegates read/write to multiple repositories; Spring Security 6 default usually pairs RequestAttribute + HttpSession | Must verify delegates/exact chain instance; do not mistake it for request-attribute-only |
| `NullSecurityContextRepository` | Does not save context and normally returns no saved context | Unsuitable when browsers need persistent login sessions |
| Custom repository | Can use cache/DB or distributed storage | Must uphold contract, concurrency, invalidation, TTL, and security |

### 3.1. Default 5.x vs. 6.x

In the migration guide:

- Spring Security 5 default was usually `HttpSessionSecurityContextRepository`.
- Spring Security 6 default is usually `DelegatingSecurityContextRepository`, combining `RequestAttributeSecurityContextRepository` and `HttpSessionSecurityContextRepository`.

One reason is that an ERROR dispatch can run after the request context holder has been cleared; the request-attribute repository keeps context available **within the same request** without forcing everything onto a session.

**Important:** “default DelegatingSecurityContextRepository” does not mean Spring auto-saves every change in every request; it only defines **where saving goes when `saveContext` is called**.

### 3.2. Example Sharing One Repository Between Custom Controller and Filter Chain

Inside a Spring configuration method with appropriate imports:

~~~java
SecurityContextRepository repository =
        new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository());

http.securityContext(context -> context
        .securityContextRepository(repository)
        .requireExplicitSave(true));
~~~

These classes belong to `org.springframework.security.web.context`. If custom code uses a different repository instance than the filter reads from, you can end up **writing in one place and reading in another**. In the lab in section 7, the repository is registered as **the exact same bean** and injected into both `SecurityFilterChain` and the controller.

### 3.3. When Is an HttpSession Created?

`HttpSessionSecurityContextRepository` tries to avoid creating unnecessary sessions:

- Merely loading context from an existing session **does not** create a session immediately.
- When `saveContext` needs to store an authenticated context and policy permits, the repository can create a session if none exists.
- If the context is empty or anonymous per `AuthenticationTrustResolver`, it may neither save nor create a session.
- `setAllowSessionCreation(false)` prevents the repository from creating new sessions itself, yet does not stop other components from creating sessions, and the repo can still write to an existing session.
- `SessionCreationPolicy.IF_REQUIRED` (usually appropriate for form login) differs from `STATELESS`.
- The `JSESSIONID` cookie must be stored and sent back by the client with matching Host/Path/SameSite/Secure, HTTPS reverse proxy, and working session store.

Hence testing “calling `saveContext` throws no exception” **is insufficient**; test a follow-up request with the same session/cookie and the right user. With only `RequestAttributeSecurityContextRepository`, same-request tests may pass while the next request turns anonymous.

### 3.4. STATELESS Is Not an Explicit Save Bug

If an API design uses `SessionCreationPolicy.STATELESS` and `NullSecurityContextRepository`, not preserving context for the next request is usually **intentional**: every request must carry a Bearer token/API key/HTTP Basic or re-authenticate.

~~~java
http.sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
~~~

This snippet requires importing `org.springframework.security.config.http.SessionCreationPolicy`. **Do not “fix login” on a stateless API by enabling HTTP sessions** when the contract specifies JWT/Bearer. Verify that clients actually send tokens, validate signature/issuer/audience/expiration, and verify the right `SecurityFilterChain` runs.

## 4. Legacy Mechanism: SecurityContextPersistenceFilter and Implicit Save

Under legacy semantics (conceptual view):

~~~text
SecurityContextPersistenceFilter
   │
   ├─ loads SecurityContext from SecurityContextRepository
   ├─ places it into SecurityContextHolder
   ▼
Controller / authentication filter:
   └─ sets Authentication into SecurityContextHolder
   ▼
SecurityContextPersistenceFilter:
   ├─ detects context changed
   ├─ saves if needed, including handling before response commit/redirect
   └─ clears SecurityContextHolder
~~~

Because of this, the following legacy code **could once work**:

~~~java
// Legacy code; insufficient to sustain login under default Spring Security 6.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
return ResponseEntity.ok().build();
~~~

If no other component saves, the subsequent request in Spring Security 6 will not restore the context. Note that an **OK response** does not prove the context was persisted; a user can receive HTTP 200 “login succeeded” and then get redirected to login on the very next request.

### 4.1. Response Commit and Redirects

When a browser receives a 302 redirect, the response can commit early. If the context needs to create an HTTP session and `Set-Cookie`, saving **after response commit** can be too late. Legacy implicit logic used response wrappers to intercept early, whereas the new explicit save requires the **auth component to call `saveContext(...)` before the response commits**.

For a custom controller, the basic correct order is:

~~~text
authenticate
   → apply required SessionAuthenticationStrategy policy
   → create context
   → set authenticated principal into context
   → set SecurityContextHolder
   → repository.saveContext(context, request, response)
   → send HTTP 200 / redirect / JSON response
~~~

Never call `sendRedirect` or write/flush the response before saving; never expect the repository to set a session cookie after headers have already been sent.

### 4.2. Why Not Mutate the Existing Context with setAuthentication?

The following makes logic harder to reason about:

~~~java
SecurityContextHolder.getContext().setAuthentication(authentication);
~~~

Beyond missing `saveContext`, **mutating a SecurityContext that might be shared/reused** can introduce races under concurrent sessions/requests. Spring Security docs recommend creating a fresh context:

~~~java
SecurityContext fresh = SecurityContextHolder.createEmptyContext();
fresh.setAuthentication(authentication);
SecurityContextHolder.setContext(fresh);
repository.saveContext(fresh, request, response);
~~~

Ensure `repository` matches the active filter chain and the session policy permits saving. When using custom `SecurityContextHolderStrategy`/multiple ApplicationContexts, inject the strategy rather than calling the global static; see `SecurityContextHolderStrategy` docs.

## 5. New Mechanism: SecurityContextHolderFilter and Explicit Save

Spring Security 6 default flow:

~~~text
Incoming request:
  SecurityContextHolderFilter
     │
     ├─ calls SecurityContextRepository.loadDeferredContext(request)
     ├─ supplies context to SecurityContextHolderStrategy
     │
     ▼
  Authentication filter / Controller / Service
     │
     ├─ reads current Authentication (if any)
     ├─ may create a new Authentication
     └─ if persistence is wanted → calls repository.saveContext(...) itself
     │
     ▼
  Response
     │
     ▼
  SecurityContextHolderFilter clears context holder
     │
     └─ DOES NOT auto-scan for changes to save at request end

Next request:
  SecurityContextHolderFilter loads from repository
  or returns anonymous if no context is found
~~~

### 5.1. What Method Does “Explicit Save” Mean?

Spring Security 6.5 signature:

~~~java
void saveContext(
        SecurityContext context,
        HttpServletRequest request,
        HttpServletResponse response);
~~~

`SecurityContextRepository.saveContext(...)` takes **the full context + request + response**; it is not storing `Authentication` alone, not `SecurityContextHolderStrategy.setContext(...)`, and not `HttpSession.setAttribute("username", ...)`.

Code example inside a controller/filter with `context`/`request`/`response` variables:

~~~java
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
~~~

Ensure the context contains a **verified Authentication**; never place a client-controlled `UsernamePasswordAuthenticationToken.authenticated(...)` without calling `AuthenticationManager.authenticate(...)`. Attackers must never send `role`/`isAuthenticated` and turn it into a session.

### 5.2. Does Built-in formLogin Still Maintain Sessions Automatically?

**Yes, under standard session-based configuration.** With `UsernamePasswordAuthenticationFilter` (extending `AbstractAuthenticationProcessingFilter`), Spring Security:

1. Builds an unauthenticated token from the request.
2. Invokes `AuthenticationManager`/`AuthenticationProvider`.
3. Executes `SessionAuthenticationStrategy` upon success, per configuration.
4. Creates `SecurityContext` and sets Authentication into the holder.
5. Saves the context via the repository configured on the authentication filter.
6. Runs remember-me/events/success handler and returns the response.

In version 6.5 docs, the authentication architecture section describes these filter steps and notes that persistence across subsequent requests requires explicit `saveContext`. The built-in filter code fulfills that responsibility; **developers using standard `formLogin(...)` do not write `saveContext` in their own controllers**.

Conversely, if a developer **writes `POST /api/login` themselves and only calls `authenticationManager.authenticate(...)`**, they have bypassed the form filter’s context and session management. That responsibility then belongs to the custom endpoint.

### 5.3. Basic/JWT/Resource Server

An `httpBasic()` or Bearer JWT request can be authenticated **independently each time**, without needing a session. When the client stops sending the Basic header/Bearer token, the next request may be anonymous. Do not conclude “explicit save is broken” when the system is intentionally stateless.

Conversely, if a system intentionally wants to save an initial authentication into a session, verify the repository and semantics of **that specific authentication filter**; merely setting a repository on `SecurityContextHolderFilter` does not make every stateless filter use it automatically.

## 6. Standalone Java 17 Illustration: Temporary Holder vs. Longer-Lived Store

This program **does not use Spring**; it is a simple analogy for the difference between in-request state and state persisted for the next request. The map store in the example exists only in one process and **is not a secure session management model**.

File `ContextLifecycleDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public class ContextLifecycleDemo {
    private static final ThreadLocal<String> CURRENT =
            new ThreadLocal<>();
    private static final Map<String, String> SAVED =
            new HashMap<>();

    private static void beginRequest(String sessionKey) {
        CURRENT.set(SAVED.get(sessionKey));
    }

    private static void authenticate(String username) {
        CURRENT.set(username);
    }

    private static void explicitSave(String sessionKey) {
        SAVED.put(sessionKey, CURRENT.get());
    }

    private static void endRequest() {
        CURRENT.remove();
    }

    public static void main(String[] args) {
        beginRequest("lab-session");
        authenticate("alice");
        System.out.println("during-first-request=" + CURRENT.get());
        endRequest();

        beginRequest("lab-session");
        System.out.println("without-save=" +
                (CURRENT.get() == null ? "anonymous" : CURRENT.get()));
        endRequest();

        beginRequest("lab-session");
        authenticate("alice");
        explicitSave("lab-session");
        endRequest();

        beginRequest("lab-session");
        System.out.println("after-explicit-save=" + CURRENT.get());
        endRequest();
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac --release 17 ContextLifecycleDemo.java
java ContextLifecycleDemo
~~~

**Exact stdout:**

~~~text
during-first-request=alice
without-save=anonymous
after-explicit-save=alice
~~~

`CURRENT` plays the role of **temporary context holder**, `SAVED` plays a simulated repository, and `beginRequest/endRequest` model restore/clear. The program has no Servlet session, cookies, CSRF, AuthenticationManager, or SecurityContext; **never copy this HashMap/ThreadLocal into a web application**.

## 7. Runnable Spring Boot 3.5 / Spring Security 6.5 Example

This example contains **two login mechanisms** in the same lab application:

- **Built-in form login:** Spring Security handles `POST /login` and persists context automatically per configuration.
- **Custom JSON login:** a controller handles `POST /api/manual-login`, calls `AuthenticationManager`, and then **calls `saveContext(...)` itself**.

The `GET /api/me` endpoint proves **the second request** restores Authentication from the session. Spring Security’s default `POST /logout` handles cleanup and invalidation. The app keeps CSRF **enabled** for both form and custom login because it is a cookie/session model. Test with `.with(csrf())`.

**Limitations:** this is a local lab with test usernames/passwords. Production systems must add rate limiting, account lifecycle, real data stores, HTTPS, appropriate session fixation/concurrent session handling, frontend CSRF wiring, auditing, MFA, and privacy policies. Custom JSON login should only be used when there is a strong reason and full policy review; standard form login is usually simpler and safer.

### 7.1. Gradle Dependencies

Place in `build.gradle` of a Spring Boot 3.5.x project with the Boot plugin/BOM, Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Do not manually add a Spring Security 7.x version to the test module alone when runtime uses 6.5. `spring-security-test` provides `formLogin()`, `csrf()`, and authentication result matchers, while `MockMvc` comes from Spring Boot test.

### 7.2. Single Java File with Configuration + Controller

Create `src/main/java/example/contextsave/ExplicitSaveApplication.java`:

~~~java
package example.contextsave;

import java.util.List;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@SpringBootApplication
public class ExplicitSaveApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExplicitSaveApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class DemoSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        // Lab password only; never reuse in a real system.
        UserDetails student = User.withUsername("student")
                .password(encoder.encode("lab-only-password-2026"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(student);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        // Use THIS EXACT bean in both filter chain and custom controller.
        return new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository());
    }

    @Bean
    SessionAuthenticationStrategy manualSessionStrategy() {
        // Demonstrates session fixation changeSessionId when a session exists.
        // Does not replace full production session strategies/MFA/rate limiting.
        return new ChangeSessionIdAuthenticationStrategy();
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http, SecurityContextRepository repository)
            throws Exception {

        http.securityContext(context -> context
                .securityContextRepository(repository)
                .requireExplicitSave(true));

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/manual-login").permitAll()
                .anyRequest().authenticated());

        http.formLogin(Customizer.withDefaults());
        http.logout(Customizer.withDefaults());

        // CSRF KEPT DEFAULT, also applies to POST /api/manual-login.
        return http.build();
    }
}

record ManualLoginRequest(
        @NotBlank String username,
        @NotBlank String password) {
}

@RestController
class ManualLoginController {
    private final AuthenticationManager authenticationManager;
    private final SecurityContextRepository repository;
    private final SessionAuthenticationStrategy sessionStrategy;

    ManualLoginController(AuthenticationManager authenticationManager,
                          SecurityContextRepository repository,
                          SessionAuthenticationStrategy sessionStrategy) {
        this.authenticationManager = authenticationManager;
        this.repository = repository;
        this.sessionStrategy = sessionStrategy;
    }

    @PostMapping("/api/manual-login")
    ResponseEntity<Map<String, String>> login(
            @Valid @RequestBody ManualLoginRequest input,
            HttpServletRequest request,
            HttpServletResponse response) {

        // Unauthenticated token; provider verifies the real password.
        Authentication candidate =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        input.username(), input.password());

        Authentication verified =
                authenticationManager.authenticate(candidate);

        // Apply configured minimal strategy before saving.
        sessionStrategy.onAuthentication(verified, request, response);

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verified);
        SecurityContextHolder.setContext(context);

        // DECISIVE step so subsequent requests still have Authentication.
        repository.saveContext(context, request, response);

        // Return generic status only; never return cookies/passwords/hashes.
        return ResponseEntity.ok(Map.of(
                "status", "AUTHENTICATED"));
    }

    @GetMapping("/api/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }
}

@RestControllerAdvice
class SafeAuthErrors {

    @ExceptionHandler(AuthenticationException.class)
    ResponseEntity<Map<String, String>> invalidCredentials(
            AuthenticationException ignored) {
        // Never print username, password, Authentication, or exception details.
        return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(Map.of("error", "INVALID_CREDENTIALS"));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<Map<String, String>> invalidInput(
            MethodArgumentNotValidException ignored) {
        // Never return FieldError.getRejectedValue() for password.
        return ResponseEntity.badRequest()
                .body(Map.of("error", "INVALID_REQUEST"));
    }
}
~~~

**Compilation conditions:** a file has only one public top-level class `ExplicitSaveApplication`; the other classes/records are package-private. In real projects, split classes into separate files. The APIs `DaoAuthenticationProvider(UserDetailsService)`, `ProviderManager(List<AuthenticationProvider>)`, `SecurityContextRepository.saveContext(...)`, `ChangeSessionIdAuthenticationStrategy`, and `HttpSecurity.securityContext(...)` belong to the Spring Security 6.5 branch.

### 7.3. Explaining the Order Inside the Controller

- `AuthenticationManager.authenticate` **actually verifies** the password using a provider with `UserDetailsService` + `PasswordEncoder`; never create an authenticated token from raw input without verification.
- `SessionAuthenticationStrategy.onAuthentication` is called before saving. `ChangeSessionIdAuthenticationStrategy` only illustrates fixation protection for an existing session; production apps may need composite strategies, concurrent session registries, and additional policies.
- `SecurityContextHolder.createEmptyContext` creates a fresh context, avoiding mutating a shared/old context.
- `SecurityContextHolder.setContext(context)` makes the Authentication available for the current request.
- `repository.saveContext(context, request, response)` is the **mandatory step in a custom controller** when preserving authentication in the session for the next request.
- `SecurityFilterChain` uses **the exact same repository bean**; if the filter reads from repo A while the controller writes to repo B, persistence tests will fail.
- CSRF stays enabled; for JSON login relying on session cookies, a valid CSRF token is required. `MockMvc` supplies it via `with(csrf())` rather than disabling CSRF to make the example run.
- `SafeAuthErrors` returns generic messages on bad credentials to avoid leaking account existence or secrets. Production needs rate limiting, lockout/abuse monitoring, and safe auditing.
- Standard `formLogin` still exists alongside it; it has its own filter/session handling and **does not call `/api/manual-login`**.
- The `/api/me` endpoint returns the lab username after authentication; real projects must decide whether returning PII is appropriate.

**Do not treat this example as a complete production login implementation.** For MFA, remember-me, concurrent session limits, login events, account policies, or distributed Spring Session, calling `ChangeSessionIdAuthenticationStrategy` alone is not enough. Use framework mechanisms and test against your threat model.

### 7.4. Trying via Browser/HTTP

In the project directory containing the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

When unauthenticated, `GET /api/me` (Accept: text/html) typically redirects to `/login`. Opening `/login` displays Spring Security’s default form with a CSRF token; signing in with the lab account `student`/`lab-only-password-2026` creates a session.

**Do not run a raw curl POST without a CSRF token and conclude explicit save is broken**. For custom JSON login, you must send the session cookie and a valid CSRF token. The MockMvc section below documents the exact test setup; real browser usage must complete the CSRF token handshake per frontend configuration.

**Never use example passwords in production.** Plain HTTP is for local labs only; real systems require HTTPS, cookie flags, secrets policies, and brute-force protection.

## 8. Spring Security Test: Proving the Second Request Restores Context

This is the crux of the lesson: **HTTP 200 right after `saveContext` is not enough**. Tests must send a second request with the same session and assert the principal is restored.

File `src/test/java/example/contextsave/ExplicitSaveApplicationTest.java`:

~~~java
package example.contextsave;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ExplicitSaveApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void customLoginExplicitlySavesForNextRequest() throws Exception {
        MvcResult login = mvc.perform(post("/api/manual-login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "username": "student",
                      "password": "lab-only-password-2026"
                    }
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("AUTHENTICATED"))
            .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);

        // Second request no longer sends password.
        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(authenticated().withUsername("student"))
            .andExpect(jsonPath("$.username").value("student"));
    }

    @Test
    void builtInFormLoginAlsoPersistsContext() throws Exception {
        MvcResult login = mvc.perform(formLogin()
                .user("student")
                .password("lab-only-password-2026"))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername("student"))
            .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("student"));
    }

    @Test
    void manualLoginWithWrongPasswordDoesNotCreateUsableLogin()
            throws Exception {
        mvc.perform(post("/api/manual-login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"username":"student","password":"wrong"}
                    """))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error")
                    .value("INVALID_CREDENTIALS"));
    }

    @Test
    void manualLoginWithoutCsrfIsRejectedBeforeAuthentication()
            throws Exception {
        mvc.perform(post("/api/manual-login")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"username":"student","password":"lab-only-password-2026"}
                    """))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousRequestHasNoPersistentAuthentication()
            throws Exception {
        mvc.perform(get("/api/me")
                .accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void builtInLogoutInvalidatesSessionSavedByManualLogin()
            throws Exception {
        MvcResult login = mvc.perform(post("/api/manual-login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"username":"student","password":"lab-only-password-2026"}
                    """))
            .andExpect(status().isOk())
            .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);
        assertFalse(session.isInvalid());

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));

        assertTrue(session.isInvalid());

        // Do not reuse an invalidated session.
        mvc.perform(get("/api/me")
                .accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

There are **6 HTTP tests** in `ExplicitSaveApplicationTest`. Cases verified:

1. Custom login: 200 response **and** a follow-up GET with the same session returns authenticated.
2. Form login: the built-in filter also saves context without controller save logic.
3. Wrong password: no usable login issued, returns generic 401.
4. Missing CSRF: 403; not a `saveContext` failure.
5. Anonymous request: still requires login.
6. Logout: session is invalidated, not merely redirected.

Run with Gradle wrapper:

~~~bash
./gradlew test --tests example.contextsave.ExplicitSaveApplicationTest
~~~

**Expected** result: 6 tests pass when environment, starters, and Spring Security 6.5 match. This article does not claim to have executed the build in a live repository.

### 8.1. Isolated Unit Test: setContext Is Not saveContext

A small test with `HttpSessionSecurityContextRepository` proves setting the holder alone does not write the session. File `src/test/java/example/contextsave/ExplicitRepositoryTest.java`:

~~~java
package example.contextsave;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;

import static org.junit.jupiter.api.Assertions.*;

class ExplicitRepositoryTest {

    @Test
    void settingHolderDoesNotWriteHttpSessionRepository() {
        HttpSessionSecurityContextRepository repo =
                new HttpSessionSecurityContextRepository();
        MockHttpServletRequest request =
                new MockHttpServletRequest();
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(new TestingAuthenticationToken(
                "student", "test-only", "ROLE_USER"));

        try {
            SecurityContextHolder.setContext(context);

            // Context exists only on the thread, not yet persisted.
            assertFalse(repo.containsContext(request));

            repo.saveContext(context, request, response);

            // Context now exists in this request's session.
            assertTrue(repo.containsContext(request));
        }
        finally {
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

This test verifies the **context-saving API**, without running the filter chain or real HTTP login; it complements the six integration tests rather than replacing them. Run:

~~~bash
./gradlew test --tests example.contextsave.ExplicitRepositoryTest
~~~

**Limitation:** `TestingAuthenticationToken` is purely a test fixture; production must use `AuthenticationManager`/providers that verify credentials. This unit test does not cover CSRF, session fixation, or authorization.

### 8.2. Do Not Use @WithMockUser to Prove Persistence

A test like:

~~~java
mvc.perform(get("/api/me").with(user("student")))
    .andExpect(status().isOk());
~~~

only supplies a mock principal for **the request under test**. It does not verify passwords, test `saveContext`, or prove a session restores on the next request. `@WithMockUser` or `with(user(...))` is useful for authorization unit tests, yet **cannot replace** two-request tests using a real session from a login flow.

### 8.3. MockMvc Cannot Test Every Browser Issue

`MockHttpSession` is a simulated session: it proves the repository/filter in the application context reads and writes across requests. It does not prove:

- Real browsers store and send `JSESSIONID` per Cookie `Secure`/`SameSite`/`Path`/`Domain`.
- Spring Session + Redis/JDBC works across multiple replicas.
- Reverse proxies/HTTPS/load balancers preserve cookies.
- Session IDs rotate properly under concurrent logins and policies.
- OAuth2/OIDC callbacks/third-party cookies/MFA also work.
- Network edge cases where responses commit early, redirects abort, or the session store is unavailable.

Therefore add E2E/browser and staging integration tests when validating end-to-end login on production infrastructure.

## 9. Manual Login: When Are Additional Steps Needed?

`SecurityContextRepository.saveContext` only solves **context persistence**. A complete login also requires:

| Component | Role | If Omitted |
| --- | --- | --- |
| `AuthenticationManager`/provider | Verifies credentials and account status | Can forge Authentication → critical |
| `SessionAuthenticationStrategy` | Fixation/concurrency/session policies | Session exists yet may violate policy |
| `SecurityContextRepository` | Saves/restores context | Subsequent requests turn anonymous |
| `RememberMeServices` (if enabled) | Handles remember-me per policy | Diverges from built-in form login behavior |
| CSRF | Blocks cross-site login/logout/state changes | Login CSRF or unprotected state changes |
| Success/failure handlers | Controls HTTP response, redirects, error mapping | Login UI loops, false 200s, or information leaks |
| MFA/step-up | Enforces required authentication factors per policy | Persists privileged sessions prematurely |
| Audit/rate limiting | Monitors abuse, prevents password guessing | Vulnerable to brute force and hard to investigate |
| Session lifecycle | Invalidation/logout/timeout/refresh | Sessions live too long or fail to revoke |
| Idempotency/transactions | Persists account updates and events durably | Partial states hard to recover |

In the lab example, `SessionAuthenticationStrategy` is only `ChangeSessionIdAuthenticationStrategy`; it does not automatically handle concurrent sessions, OAuth2, remember-me, or MFA. When an application requires those features, configure and test each strategy just like the built-in filter or use the standard filter directly.

### 9.1. Save Before or After MFA?

If policy requires 2FA, “correct password” is only **one verified factor**. Do not save an Authentication holding full authorities/roles into the session before MFA completes, unless the application intentionally models a **partial authentication** state and authorization rules block resources needing the next factor.

~~~text
Password accepted
    │
    ├─ If MFA required: create pending state ONLY allowed to perform MFA
    │                    (do not grant full business authorities)
    │
    └─ MFA completed → upgrade to full-factor Authentication
                        → save context/session per policy
                        → access protected resources
~~~

Every authentication state transition in a custom flow must decide **whether to save the new context**. Do not merely set the holder and wait for `SecurityContextHolderFilter` to auto-detect it as in version 5.

### 9.2. When Adjusting Roles After Login

If an application updates `Authentication` or authorities during a request and expects the next request to use the new roles, it must also decide how the repository/session receives the updated context. Do not unsafely mutate a shared principal across sessions or expect `@PreAuthorize` to save for you. For sensitive changes, invalidation/re-authentication may be needed instead of silently elevating the active session.

## 10. Logout and Clearing SecurityContext: Keep the Repository Synchronized

### 10.1. Default Logout Already Handles Cleanup

Spring Security Servlet provides logout support. When `POST /logout` has a valid CSRF token, default logout handlers normally:

- Invalidate the HTTP session.
- Clear `SecurityContextHolderStrategy`.
- Clear `SecurityContextRepository` per handler mechanism.
- Handle remember-me and CSRF tokens appropriately if enabled.
- Publish `LogoutSuccessEvent` and invoke the success handler (usually redirecting to `/login?logout`).

Hence **do not replace standard logout with a simple controller calling only `SecurityContextHolder.clearContext()`**. That may clear only the current request’s holder while the old session still holds the Authentication, leaving subsequent requests logged in.

### 10.2. Why clearContext() Alone Is Insufficient

~~~java
// WRONG if Authentication remains saved in the HTTP session.
SecurityContextHolder.clearContext();
return ResponseEntity.ok().build();
~~~

The next request reads from the repository again and restores the old context. For custom logout, Spring recommends `SecurityContextLogoutHandler` and appropriate cleanup configuration—or better yet—retaining `LogoutFilter`/the logout DSL.

Illustration **inside a controller that already has the handler and request/response**:

~~~java
SecurityContextLogoutHandler handler =
        new SecurityContextLogoutHandler();
handler.setSecurityContextRepository(repository);
handler.logout(request, response,
        SecurityContextHolder.getContext().getAuthentication());
~~~

This snippet needs imports for `org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler` and `SecurityContextRepository`, and is purely **illustrative**. Production must address session invalidation, remember-me, CSRF, out-of-session tokens, and notifications/auditing; do not copy the snippet and claim system-wide logout is complete.

**Do not think explicit save means you must always call `saveContext(emptyContext)` after standard `SecurityContextLogoutHandler`**: the handler/`LogoutFilter` has its own cleanup responsibilities. Avoid accidentally re-saving a logged-out context due to wrong ordering.

### 10.3. Local Logout Does Not Automatically Revoke JWT/IdP Sessions

- Clearing context from the HTTP session **does not** revoke still-valid stateless JWT access tokens.
- Deleting `JSESSIONID` on the client without invalidating the server session is insufficient.
- Local logout does not imply signing out of every OAuth2/OIDC IdP session.
- If the app uses refresh tokens, remember-me tokens, or distributed Spring Session, a dedicated revocation plan is required.
- A passing unit test for `SecurityContextHolder.clearContext()` does not prove HTTP logout works.

## 11. Common Upgrade Pitfalls

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Login POST 200 yet immediate GET redirects to /login | Custom controller only calls `setContext`, not `saveContext` | Test another protected GET with the same session |
| Standard form login still works, custom JSON login does not | Built-in filter saves; custom login omits step | Compare repository config and custom controller |
| Only one node loses login state | Session store not shared/mismatched secret/cookie | Check LB, Spring Session, sticky/shared storage |
| Session exists yet `SecurityContext` is missing | Saved to different repo, saved anonymous/empty, or wrong session | Check bean/repo chain and scrubbed session ID |
| Context works in ERROR dispatch but not next request | Using only `RequestAttributeSecurityContextRepository` | Add HttpSession repository when persistence is wanted |
| Custom filter sets Authentication then next GET is anonymous | Filter never saved or only set ThreadLocal | Add save before response commit |
| Save called yet no JSESSIONID appears | STATELESS, `NullSecurityContextRepository`, allowSessionCreation=false, proxy, cookie | Check policy and repo; avoid enabling sessions for stateless APIs |
| After POST login, request 2 returns 403 | Context may be saved, yet user lacks role/authority/MFA | Distinguish authentication vs. authorization |
| POST login returns 403 immediately | Missing/invalid CSRF | Check `CsrfFilter` before modifying repository |
| Still authenticated after logout | Only cleared holder; old context remains in session | Use `LogoutFilter`/`SecurityContextLogoutHandler`, test session invalidation |
| Basic/Bearer requests still succeed after logout | Basic/JWT re-authenticates on every request | Rotate credentials/revoke tokens if needed; not a persistence bug |
| Login suddenly creates too many sessions | Eager session policy, request cache, custom repo | Check session minimization and tracing, not just explicit save |
| Setting `requireExplicitSave(false)` temporarily hides bug | Legacy code relies on implicit save | Fix custom code before returning to default |
| Both `HolderFilter` + `PersistenceFilter` attached | Duplicate/conflicting configuration | Use only one; inspect actual chain |
| Controller returns right status yet browser loops on login | Cookie Domain/SameSite/Secure, redirect, session store | Browser/staging E2E |
| `@WithMockUser` tests pass while real login fails | Mock user bypasses authentication/persistence | Use formLogin/custom POST through filters plus follow-up GET |
| `SessionAuthenticationStrategy` not applied | Spring 6 does not rely on `SessionManagementFilter` by default | Invoke strategy inside auth mechanism at the right point |
| Context saved before MFA completes | App persists full Authentication too early | Persist partial state with limited authorities or wait for full MFA |
| Redirect occurs before save | Response commits; session cookie cannot be added | Save before `sendRedirect`/body flush |

### 11.1. When Inspecting Logs, What to Record and What to Avoid?

Record audit markers such as:

~~~text
event=MANUAL_LOGIN stage=AUTHENTICATED
event=MANUAL_LOGIN stage=CONTEXT_SAVE_ATTEMPTED
event=MANUAL_LOGIN stage=RESPONSE_SENT
event=PROTECTED_REQUEST stage=CONTEXT_RESTORED
~~~

Those four lines are **application-defined sample events**, not emitted verbatim by Spring Security. Never log raw passwords, `JSESSIONID`, `Authorization`, CSRF tokens, or full serialized `SecurityContext`/`Authentication` objects. Server-issued random correlation IDs can link steps within retention/privacy limits.

Do not conclude “save succeeded” just because a log line printed before `saveContext` — you must still handle exceptions and verify next-request behavior.

## 12. Test Matrix for 5.x → 6.x Migration

| ID | Scenario | Expected Behavior |
| --- | --- | --- |
| C01 | Custom login sets holder only, no save | Current request has Authentication; next request does not auto-restore |
| C02 | Custom login sets + saves with HttpSession repo | Next request with same session restores Authentication |
| C03 | Built-in default formLogin | Handles persistence automatically without controller save code |
| C04 | Wrong username/password | No authenticated session created |
| C05 | Missing CSRF on cookie-based POST login | 403, not an explicit save error |
| C06 | Save before redirect/response commit | Cookie/session context written in time |
| C07 | Save after response commit | Caught as a bug and fixed |
| C08 | RequestAttribute-only repository | Context available across dispatches in same request; absent in next request |
| C09 | Delegating repository with HttpSession | Context persists across requests when saved and session is valid |
| C10 | NullSecurityContextRepository | Does not store HTTP session, matching stateless policy |
| C11 | SessionCreationPolicy.STATELESS | Does not force session creation for bearer APIs |
| C12 | SessionCreationPolicy.IF_REQUIRED | Repo can create a session when login needs one |
| C13 | Custom repository reads/writes different instance/backend | Mismatch detected and config fixed |
| C14 | Logout calling only `clearContext()` | Old context may remain; test catches it |
| C15 | Built-in POST /logout with CSRF | Session invalidated and next request is anonymous |
| C16 | Custom logout with proper handler | Clears repository and session per policy |
| C17 | Basic request omitting header on next request | Does not stay authenticated via Basic automatically |
| C18 | JWT request omitting Bearer on next request | Resource server rejects if no other auth mechanism applies |
| C19 | Valid password while MFA incomplete | No full session/roles granted |
| C20 | Session fixation strategy after manual auth | Session ID rotated per strategy when appropriate |
| C21 | Concurrent session control | Custom filter calls right strategy; registry/limits work |
| C22 | Session expires before next request | Does not resurrect Authentication from ThreadLocal |
| C23 | 2 replicas / Redis Spring Session | State read consistently without user leakage |
| C24 | Wrong Secure/SameSite/Domain/Path cookie | Browser flow test catches login loop |
| C25 | `@WithMockUser` in tests | Not treated as proof of save/restore |
| C26 | MockMvc login + second GET with same MockHttpSession | Proves persistence inside application |
| C27 | Multiple SecurityFilterChains | Tests target the exact chain owning repo and auth mechanism |
| C28 | Async request / different thread | Does not mistake ThreadLocal persistence for session persistence |
| C29 | ERROR dispatch after exception | RequestAttribute repository exposes context per configured mechanism |
| C30 | Saving anonymous/empty context | Does not create an unintended authenticated session |
| C31 | Removing `requireExplicitSave(false)` post-migration | All custom auth flows still pass tests |
| C32 | User role change or logout | Old context handled per session invalidation/refresh policy |

You do not need to “test every single class in isolation” to prove migration. The highest value comes from **behavioral test suites**: real POST login → capture session → GET authenticated resource → logout → follow-up GET blocked. Also test custom, built-in, CSRF, stateless, and distributed session variants.

## 13. Zero-Downtime Migration Plan

### Phase 1 — Inventory

1. Pin exact `spring-security-web/config/test` versions and Spring Boot BOM per module; never mix 5.x/6.x/7.x arbitrarily.
2. List every `SecurityFilterChain` and active filter/context repository.
3. Locate all calls to `SecurityContextHolder.setContext`, `getContext().setAuthentication`, `clearContext`, custom `OncePerRequestFilter` implementations, custom success handlers, and login controllers.
4. Check custom `AuthenticationManager`, JWT/Basic/OIDC flows, and whether default `SessionManagementFilter` behavior was previously relied upon.
5. Inspect session policies (`ALWAYS`/`IF_REQUIRED`/`NEVER`/`STATELESS`), session registries, save strategies, remember-me, and CSRF.
6. Inspect repositories per chain: HttpSession/RequestAttribute/Delegating/Null/custom.
7. Review existing tests; separate mock-principal tests from two-request persistence tests.

### Phase 2 — Standardize the Contract

1. Label each authentication flow explicitly as **stateful** or **stateless**.
2. For stateful custom flows, define **who calls `saveContext`**, against which exact repository, and before response commit.
3. For built-in form login, rely on framework responsibility without adding redundant controller saves.
4. For custom logout, prefer standard logout DSL/handlers; if custom code is unavoidable, clear and persist the clear via the repository.
5. For MFA, define the exact point at which full Authentication is persisted.
6. For concurrent session policies, place `SessionAuthenticationStrategy` inside the auth mechanism rather than relying solely on legacy DSL defaults.

### Phase 3 — Transition to New Behavior

On systems still on Spring Security 5.8, you can enable `requireExplicitSave(true)` as a migration rehearsal, fix custom code, and then upgrade to Spring Security 6. On Spring Security 6.x projects, keep the new default; only set `false` as a short-term measure with a clear removal plan.

Verify **each URL/chain/HTTP method**. Working form login does not mean JSON login, token exchange, or custom impersonation/step-up flows are also working.

### Phase 4 — Testing and Rollout

1. Unit test repository behavior and error categories.
2. Run MockMvc integration tests for login/CSRF/session/logout.
3. Run E2E browser tests across accurate proxy/HTTPS/cookie setups.
4. Test multi-node setups when using Spring Session or session replication.
5. Ensure audits contain no raw passwords, contexts, or session IDs.
6. Use feature flags/gradual rollout; monitor both login success handlers and protected-request success rates, not just login HTTP 200s.
7. Prepare safe config/code rollback, avoiding rollbacks that cause old sessions to read incompatible state and drop user access.
8. Once stable, remove legacy compatibility settings and update ADRs/runbooks.

### Phase 5 — Post-Deployment Monitoring

Track meaningful signals without collecting secrets:

- Login endpoint 200/302 successes.
- Rate of **protected requests right after login** being authorized.
- Rate of login redirect loops.
- Valid session creations/invalidations.
- Grouped CSRF 403, unauthorized 401, and forbidden 403 rates.
- Errors from distributed repositories/stores.
- Logout/expiration counts and session policy rejections.
- Breakdown by chain/auth method and deployment version, avoiding equating user actions with every JWT verification.

**The essence of migration:** it is not “how to make `setContext` auto-save like before”, but moving to an architecture where **the component creating or removing authentication takes explicit responsibility for persistence**.

## 14. Self-Check Questions

1. How do `SecurityContextHolder.setContext` and `SecurityContextRepository.saveContext` differ?
2. Which filter by default had auto-detection/context-saving logic in Spring Security 5.x?
3. Does `SecurityContextHolderFilter` in Spring Security 6 auto-save when the request ends?
4. Does Spring Security 6 make built-in `formLogin` “stop saving sessions” by default?
5. What behavior does `requireExplicitSave(true)` express?
6. Should `requireExplicitSave(false)` be kept permanently after migration?
7. How does `HttpSessionSecurityContextRepository` differ from `RequestAttributeSecurityContextRepository`?
8. What does Spring Security 6’s default `DelegatingSecurityContextRepository` normally delegate to?
9. Why can `NullSecurityContextRepository` be the right choice for stateless APIs?
10. Why should you call `SecurityContextHolder.createEmptyContext` instead of mutating an existing context object?
11. During a custom login redirect, should `saveContext` be called before or after `sendRedirect`?
12. Does calling `saveContext` automatically provide session fixation protection, MFA, remember-me, and rate limiting?
13. Why can `SecurityContextHolder.clearContext()` alone in a logout controller be insufficient?
14. To clearly verify login persistence, how many HTTP requests are needed and how is the session attached?
15. Does a passing `@WithMockUser` test verify real persistence?
16. Why must custom auth mechanisms in Spring Security 6 pay attention to `SessionAuthenticationStrategy`?
17. When the second request returns 403, can you assume the context was not saved?
18. When a JWT/Bearer API does not keep authentication across requests, is that always a bug?
19. How do you verify that the controller and filter are using the same repository?
20. Why did Spring Security reduce implicit writes to `HttpSession`?

**Guiding answers:** (1) holder is current-request state, save writes for subsequent requests; (2) SecurityContextPersistenceFilter; (3) no; (4) no, built-in filters handle it; (5) read-only loading + explicit save semantics; (6) no, prefer fixing the code; (7) cross-request session vs. same-request attributes; (8) RequestAttribute and HttpSession; (9) re-authenticates every request; (10) avoids unintended sharing/mutation; (11) before; (12) no; (13) repo/session still retains the old context; (14) at least login followed by a protected request with the same session; (15) no; (16) old session filters no longer handle everything automatically; (17) not necessarily, roles may be missing; (18) no, stateless is by design; (19) bean/configuration wiring and tests; (20) clearer responsibility, performance, and avoiding unnecessary writes.

## 15. End-of-Lesson Checklist

- [ ] Clearly distinguished Spring Security 5 implicit save vs. Spring Security 6 explicit save.
- [ ] Did not attach both `SecurityContextPersistenceFilter` and `SecurityContextHolderFilter`.
- [ ] Repository is configured consistently between filter chain and custom auth components.
- [ ] Custom login builds Authentication via provider, applies session policy, sets context, and calls `saveContext` before response.
- [ ] Built-in form login relies on the framework to perform persistence properly.
- [ ] Did not treat `setContext`/`ThreadLocal` as proof of cross-request login.
- [ ] Cookie/session-based form/JSON logins keep CSRF per architecture; not disabled app-wide.
- [ ] Custom logout uses standard handler/filter; not merely clearing the holder.
- [ ] Stateless JWT/Basic has its own policy without saving sessions outside contract.
- [ ] Unit + MockMvc tests observe both the initial request and follow-up protected request with the same session.
- [ ] Tests cover CSRF, invalid credentials, logout, MFA, roles, and session policies.
- [ ] E2E browser tests cover cookies/proxy/HTTPS and distributed sessions when needed.
- [ ] Audits/traces contain no passwords, tokens, session IDs, or full Authentication objects.
- [ ] Compatibility `requireExplicitSave(false)` is time-boxed with a removal plan.
- [ ] Never declare “login complete” solely from a 200/302 status on the first request.

## 16. Official References

- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Session Management Migrations](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html)
- [Spring Security 6.5 — SecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html)
- [Spring Security 6.5 — HttpSessionSecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/HttpSessionSecurityContextRepository.html)
- [Spring Security 6.5 — DelegatingSecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/DelegatingSecurityContextRepository.html)
- [Spring Security 6.5 — AbstractAuthenticationProcessingFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html)
- [Spring Security 6.5 — SecurityContextHolderFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextHolderFilter.html)
- [Spring Security 6.5 — SecurityContextPersistenceFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextPersistenceFilter.html)
- [Spring Security 6.5 — Testing Servlet Authentication with MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html)
- [Spring Security 6.5 — Testing Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Framework — Servlet Session and Testing MockMvc](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
