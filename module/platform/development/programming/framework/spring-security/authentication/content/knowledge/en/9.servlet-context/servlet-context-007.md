# SecurityContextHolderFilter and Version-Specific Explicit Save

> **Scope:** Spring Security on the **Servlet stack** (Spring MVC), focusing on `SecurityContextHolderFilter`, `SecurityContextPersistenceFilter`, `SecurityContextHolder`, and `SecurityContextRepository` when user authentication must persist **across multiple HTTP requests**. Clearly presents the transition from Spring Security 5 to 6, what the filter does and does not do automatically, how to save context in custom logins, session/logout handling, default repositories, and common implementation mistakes. The full integration example uses **Java 17, Spring Boot 3.5.7 / Spring Security 6.5.x**, tested with MockMvc while keeping CSRF enabled.

## 1. Opening Scenario: Login Succeeds, Yet the Next Request Gets 401

A developer builds a custom `POST /manual/login` endpoint:

```java
Authentication result = authenticationManager.authenticate(token);
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(result);
SecurityContextHolder.setContext(context);
```

This is a **snippet**, assuming `authenticationManager` and `token` exist. It makes the user present in `SecurityContextHolder` **within the current request being processed**. However, on Spring Security 6 by default, that **does not guarantee** the next request will recognize the user as logged in.

Reason: `SecurityContextHolderFilter` **reads** the context from `SecurityContextRepository` into the holder, yet **does not automatically write** a new context from the holder back to the repository. To keep an application-performed authentication across HTTP requests, explicitly call:

```java
securityContextRepository.saveContext(context, request, response);
```

This is the `SecurityContextRepository` API; `request` and `response` are the current request's `HttpServletRequest`/`HttpServletResponse`, **before the response is committed**. Timing and repository type decide whether the context survives into the next request.

**Most common confusion:** this rule applies to **application code that manually creates/sets authentication**. When using **form login, OAuth2 login, or standard authentication filters** properly configured in Spring Security, the framework's authentication mechanism normally **already performs the required save steps** for that flow. Developers do not have to hunt for places to call `saveContext` manually after every standard Spring Security login.

## 2. Four Components: Holder, Context, Repository, and Filter

| Component | Actual Job | Does Not Handle |
| --- | --- | --- |
| `SecurityContextHolder` | Sets/reads the current `SecurityContext`, by default via `ThreadLocal` | Does not automatically save the user into HTTP session |
| `SecurityContext` | Holds the `Authentication` for the current security context | Not a password store and not a session ID |
| `SecurityContextRepository` | Reads/writes `SecurityContext` in a chosen persistence backend | Does not verify passwords itself |
| **`SecurityContextHolderFilter`** | Loads (possibly deferred) context for the request and clears the holder at the end of the chain | **Does not automatically call save when the holder changes** |
| `SecurityContextPersistenceFilter` | Legacy style: loads and auto-saves context at request end / before commit | Should not run simultaneously with HolderFilter |
| `AuthenticationManager` | Verifies credentials and returns an authenticated `Authentication` | Does not decide where the context is stored without integration |

### 2.1. SecurityContextHolder Is Current State, Not Durable Storage

`SecurityContextHolder.getContext().getAuthentication()` returns the identity currently bound to the active request/thread. By default the holder uses `ThreadLocal`, letting code in the same execution thread read authentication without passing it through every method signature.

```java
Authentication current =
        SecurityContextHolder.getContext().getAuthentication();

if (current != null && current.isAuthenticated()) {
    String name = current.getName();
}
```

This is only a **snippet**; it does not address anonymous principals or how the framework marks anonymous authentication. When checking whether a user is genuinely logged in, use meaningful rules/annotations (`authenticated()`, appropriate principal types) instead of relying solely on `isAuthenticated()` in all cases.

`SecurityContextHolder` does not create `JSESSIONID` cookies, save data to a database, or transfer data to other threads or requests. Spring Security takes care of setting and **clearing the holder per the filter chain lifecycle**, preventing identity leakage when the servlet container reuses threads. Never use `MODE_GLOBAL` as a "way to persist login" in a web app: it can expose one request's identity to another request.

### 2.2. SecurityContextRepository Is the Save/Restore Boundary

The repository defines operations such as:

```java
DeferredSecurityContext loadDeferredContext(HttpServletRequest request);

void saveContext(
        SecurityContext context,
        HttpServletRequest request,
        HttpServletResponse response);

boolean containsContext(HttpServletRequest request);
```

These are **illustrative API signatures**, not an interface to redeclare. Note `loadDeferredContext` is used instead of the deprecated legacy `loadContext(...)` API.

Familiar implementations:

- `HttpSessionSecurityContextRepository`: saves/reads context via HTTP session if policy permits. Used for session-based login.
- `RequestAttributeSecurityContextRepository`: stores context in a **request attribute**, preserving it across dispatches of the same HTTP request such as ERROR; **not persistence across subsequent requests**.
- `DelegatingSecurityContextRepository`: reads/saves through **multiple delegates** in order; in Spring Security 6, the default config typically combines request-attribute and session repositories.
- `NullSecurityContextRepository`: does not persist context across requests. Fits stateless configurations such as `SessionCreationPolicy.STATELESS`.

**Important:** which repository is chosen heavily affects the outcome of `saveContext`. Calling `saveContext` on `NullSecurityContextRepository` does not turn a stateless app into a session-login app.

### 2.3. SecurityContextHolderFilter

In Spring Security 6 with explicit-save defaults, this filter:

1. Receives the incoming HTTP request.
2. Asks the repository for a `DeferredSecurityContext` or corresponding context.
3. Binds the context to the holder for the rest of the filter/Servlet chain.
4. Lets authentication/authorization filters and controllers do their work.
5. Clears the holder state when the request finishes.

**The filter does not watch every change in `SecurityContextHolder` and call `saveContext` automatically.** If a custom controller only calls `setContext(...)`, the next request's read still sees the old repository state.

```text
HTTP request #1                         HTTP request #2
      │                                       │
      ▼                                       ▼
SecurityContextHolderFilter            SecurityContextHolderFilter
      │ load from repo                        │ load from repo
      ▼                                       ▼
SecurityContextHolder                   SecurityContextHolder
      │                                       │
Custom login verifies                  Is a saved context present?
      │                                       │
      ├─ setContext(...)                      ├─ if saved -> authenticated
      ├─ saveContext(...)  [REQUIRED          └─ if not saved -> anonymous/unauthenticated
      │   if persistence is wanted]
      ▼
Response / clear holder
```

### 2.4. SecurityContextPersistenceFilter

The legacy filter used in auto-saving mode: loads context at the start, checks for changes, and saves to the repository when appropriate at request end or before response commit. It had to handle early redirects, response wrappers, and commit-ordering edge cases, making the automatic mechanism both complex and prone to unnecessary repository writes.

In Spring Security 6, `SecurityContextPersistenceFilter` **is no longer the default filter**; systems normally use `SecurityContextHolderFilter`. Spring Security recommends **each security chain use only one of the two mechanisms**, never placing both filters into the same chain.

## 3. Changes Across Versions: Spring Security 5 → 6

| Version / Configuration | Primary Filter | Who Saves Context When Authentication Changes? |
| --- | --- | --- |
| Spring Security 5 historical default | `SecurityContextPersistenceFilter` | Auto-save mechanism via repository during request lifecycle |
| Spring Security 5.8 opting in to `requireExplicitSave(true)` | `SecurityContextHolderFilter` | Code/authentication mechanism must call save when persistence is needed |
| Spring Security 6 by default | `SecurityContextHolderFilter` | **Explicit save** for code modifying holder manually; standard auth filters handle saving in their flows |
| Spring Security 6 legacy opt-in `requireExplicitSave(false)` | Legacy-style persistence filter, where supported in the branch | Intended mainly for migration, not recommended as a long-term default |

**Do not confuse configuration with the filter's role.** In Spring Security 6, `requireExplicitSave(true)` is the default behavior; adding that line in code helps reviewers read intent without necessarily changing behavior. Spring Security 5.8 introduced this flag to prepare migrations before upgrading to 6.

Example Servlet configuration in Spring Security 6:

```java
@Bean
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http.securityContext(security -> security
            .requireExplicitSave(true));
    return http.build();
}
```

This is only a **configuration snippet**, needing imports, authorization rules, and an authentication mechanism for a real application. It does not create a login endpoint or save a new `Authentication` by itself.

**Related changes to watch for:**

- Spring Security 6 uses `DelegatingSecurityContextRepository` as the default choice instead of `HttpSessionSecurityContextRepository` alone, per the migration guide.
- `SessionManagementFilter` is not registered by default. Standard authentication mechanisms usually invoke `SessionAuthenticationStrategy` themselves when needed, rather than relying on SessionManagementFilter to detect authentication changes after every request.
- Some session-management DSL options in legacy code have different mechanisms or execution timing; do not copy Spring Security 5 configs mechanically.
- When moving to Spring Security 7 or using a custom filter chain, check the exact documentation for the running version and configured filters. This lesson follows Spring Security 6.5 APIs and behavior.

### Why Does Explicit Save Make Things Clearer?

The older mechanism had to detect whether the context changed, when the response committed, and how to save cleanly on redirects. The new mechanism moves persistence responsibility to the **authentication path known for certain to have succeeded**. This reduces redundant writes and makes it clear when the session actually needs updating.

However, there is a consequence: legacy custom code relying on "the filter auto-saves at request end" can become a bug where **login works for one request and disappears on the next**. Test end-to-end instead of only asserting `SecurityContextHolder.getContext().getAuthentication() != null` inside the same controller.

## 4. Proper Explicit-Save Rule: Create New Context, Set, and Save

Standard pattern for **manual authentication**:

```java
UsernamePasswordAuthenticationToken unauthenticated =
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, rawPassword);

// Must verify credentials first.
Authentication authenticated =
        authenticationManager.authenticate(unauthenticated);

// Create a NEW context; never mutate a reused context from an old session.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);

// Identity applies only to the current request if you stop here.
SecurityContextHolder.setContext(context);

// To allow the next request to restore it, save explicitly.
securityContextRepository.saveContext(context, request, response);
```

This is a snippet inside a controller/filter with existing dependencies, not a standalone class. Proper order:

1. Read credentials from the request through a protected channel.
2. Use `AuthenticationManager.authenticate(...)` to verify; proceed only on success.
3. Create a new `SecurityContext`; attach the verified result.
4. Place the context in `SecurityContextHolder` for the remainder of the request.
5. **Before redirecting, returning the response, or committing**, call `SecurityContextRepository.saveContext(context,request,response)`.
6. Let Spring Security clear the holder at the end of the filter chain; never try to hold it on the thread for the next request.

**Never call `saveContext` before credentials are verified.** Never construct `UsernamePasswordAuthenticationToken.authenticated(...)` with client-sent authorities and treat it as a valid login. That is an authentication bypass.

### 4.1. Why Create a New SecurityContext?

Not preferred:

```java
// Prone to side effects when the prior context is a reused object.
SecurityContextHolder.getContext().setAuthentication(authenticated);
```

If the context loaded from the repository/session already exists and is referenced elsewhere, mutating it directly can affect the same object before you intentionally save. Calling `SecurityContextHolder.createEmptyContext()` makes object boundaries clearer and reduces shared mutable-state bugs.

Note the flip side: **"not calling save yet" is not a contract guaranteeing mutations to a shared object will roll back**. That is why you should avoid mutating old contexts in place and write tests.

### 4.2. Both Sides Must Use the Same Repository

If the filter uses `DelegatingSecurityContextRepository` while the controller constructs its own separate `HttpSessionSecurityContextRepository` or `NullSecurityContextRepository`, unexpected behavior occurs. Actively inject **the same bean** or configure a consistent repository for both the security chain and manual code.

Example:

```java
@Bean
SecurityContextRepository securityContextRepository() {
    return new HttpSessionSecurityContextRepository();
}

@Bean
SecurityFilterChain web(
        HttpSecurity http,
        SecurityContextRepository repository) throws Exception {
    http.securityContext(security -> security
            .requireExplicitSave(true)
            .securityContextRepository(repository));
    return http.build();
}
```

This snippet explains repository sharing; it is not a complete web security configuration. `HttpSessionSecurityContextRepository` and `SecurityContextRepository` reside in `org.springframework.security.web.context`.

### 4.3. When Does Save Not Create a Session?

Even when you call `saveContext`, the result depends on the repository and session policy:

- `HttpSessionSecurityContextRepository` can create an HTTP session when saving an authenticated context, if session creation is permitted.
- `SessionCreationPolicy.IF_REQUIRED` allows creating a session when needed.
- `SessionCreationPolicy.NEVER` does not proactively create a session for Spring Security, yet can use an existing session; other parts of the app may still create sessions.
- `SessionCreationPolicy.STATELESS` chooses not to use HTTP sessions for obtaining Spring Security context, commonly paired with `NullSecurityContextRepository`.
- `RequestAttributeSecurityContextRepository` stores within the same request/dispatch and does not carry identity to another HTTP request.
- For custom repositories, read their exact `saveContext` contract and persistence policy; do not guess behavior from the class name.

**Never simply call `request.getSession(true)` and assume authentication is saved.** Having a session and having a valid `SPRING_SECURITY_CONTEXT` are two different things; the framework/repository manages the proper storage location.

## 5. Spring Boot 3.5 + Java 17 Example: How Setting Context Alone Differs from Explicit Save

The example runs **two POST endpoints** using the same `AuthenticationManager`:

- `POST /manual/unsaved`: verifies password properly, sets holder, yet **does not save to repository**.
- `POST /manual/saved`: verifies password properly, sets holder, **and saves to repository**.
- `GET /whoami`: allowed only for authenticated users; sharing the same session decides what is returned.

The application intentionally **does not use the form login filter** to isolate the effect of `saveContext`. CSRF **remains enabled**, and POST tests supply `csrf()`. Demo accounts/passwords are for internal testing only.

> **Safety boundary:** this is an example for learning **persistence semantics**, not a production-ready custom login system. A real custom login must also handle `SessionAuthenticationStrategy` (session fixation, concurrent sessions), authentication events, remember-me/MFA if applicable, rate limiting, CSRF, error handling, and logout. Whenever possible, prefer Spring Security's standard login mechanisms.

### 5.1. Directory Structure

```text
explicit-save-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/ExplicitSaveApplication.java
    └── test/java/demo/ExplicitSaveApplicationTests.java
```

`settings.gradle`:

```groovy
rootProject.name = 'explicit-save-demo'
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

Spring Boot manages compatible Spring Security dependency versions; do not override another version over the starter without good reason. The project requires JDK 17+ and a Gradle version compatible with Spring Boot 3.5.

### 5.2. Complete Java Application

Create `src/main/java/demo/ExplicitSaveApplication.java`:

```java
package demo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ExplicitSaveApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExplicitSaveApplication.class, args);
    }
}

@Configuration
class DemoSecurityConfiguration {

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
    AuthenticationManager authenticationManager(
            UserDetailsService users,
            PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        // Choose session repository to clearly observe saving across HTTP requests.
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository repository) throws Exception {

        http.securityContext(security -> security
                .requireExplicitSave(true)
                .securityContextRepository(repository));

        http.sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED));

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/manual/unsaved", "/manual/saved")
                .permitAll()
                .requestMatchers("/whoami").authenticated()
                .anyRequest().denyAll());

        http.exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint(
                        new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)));

        // Disable other login mechanisms ONLY to isolate the manual login lesson.
        // Default CSRF REMAINS ENABLED for POST.
        http.formLogin(AbstractHttpConfigurer::disable);
        http.httpBasic(AbstractHttpConfigurer::disable);
        http.requestCache(AbstractHttpConfigurer::disable);

        return http.build();
    }
}

@RestController
class ManualLoginController {
    private final AuthenticationManager manager;
    private final SecurityContextRepository repository;

    ManualLoginController(
            AuthenticationManager manager,
            SecurityContextRepository repository) {
        this.manager = manager;
        this.repository = repository;
    }

    @PostMapping("/manual/unsaved")
    String unsaved(
            @RequestParam String username,
            @RequestParam String password) {

        authenticateAndSetHolder(username, password);
        // Authentication exists only in the current request.
        return "current=mai";
    }

    @PostMapping("/manual/saved")
    String saved(
            @RequestParam String username,
            @RequestParam String password,
            HttpServletRequest request,
            HttpServletResponse response) {

        SecurityContext context =
                authenticateAndSetHolder(username, password);

        // THE STEP THAT MAKES THE DIFFERENCE:
        repository.saveContext(context, request, response);

        return "current=mai";
    }

    private SecurityContext authenticateAndSetHolder(
            String username, String password) {
        Authentication authenticated = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, password));

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authenticated);
        SecurityContextHolder.setContext(context);

        return context;
    }

    @GetMapping("/whoami")
    String whoami(Authentication authentication) {
        return authentication.getName();
    }
}
```

The two manual-login methods in the example return a fixed `current=mai` body because there is only one test account; in a real product, never hardcode responses per user or expose unnecessary account details. If the password is wrong, `AuthenticationManager` throws `AuthenticationException` and never reaches `saveContext`.

**How to read the configuration:**

1. `securityContextRepository()` returns an `HttpSessionSecurityContextRepository` bean.
2. `SecurityFilterChain` uses that exact bean via `.securityContextRepository(repository)`.
3. The controller also injects **that same repository bean**.
4. `requireExplicitSave(true)` guarantees the HolderFilter/explicit-save model, even though in Spring Security 6 it is already the default.
5. `SessionCreationPolicy.IF_REQUIRED` permits a session when needed to save the context.
6. `/manual/unsaved` only sets the holder; `/manual/saved` also calls `saveContext`.
7. Default CSRF remains enabled. The lesson does not introduce a state-changing GET login endpoint, nor does it disable CSRF "to make POST work".
8. A 401 entry point is intentionally configured so integration tests receive deterministic responses for unauthenticated requests; form login and HTTP Basic are intentionally disabled so other filters do not authenticate automatically.

### 5.3. MockMvc Test Proving Persistence

Create `src/test/java/demo/ExplicitSaveApplicationTests.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

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
class ExplicitSaveApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void setContextOnlyDoesNotSurviveNextRequest() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/manual/unsaved")
                        .session(session)
                        .with(csrf())
                        .param("username", "mai")
                        .param("password", "demo-pass-123"))
                .andExpect(status().isOk())
                .andExpect(content().string("current=mai"));

        // SAME SESSION but no SecurityContext was saved.
        mvc.perform(get("/whoami").session(session))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void explicitlySavedContextSurvivesNextRequest() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/manual/saved")
                        .session(session)
                        .with(csrf())
                        .param("username", "mai")
                        .param("password", "demo-pass-123"))
                .andExpect(status().isOk())
                .andExpect(content().string("current=mai"));

        // SAME SESSION has context: 200 and right principal.
        mvc.perform(get("/whoami").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("mai"));

        // DIFFERENT SESSION does not inherit mai's authentication.
        mvc.perform(get("/whoami").session(new MockHttpSession()))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void manualLoginRequiresCsrfToken() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/manual/saved")
                        .session(session)
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

If using Gradle Wrapper, run `./gradlew test` (macOS/Linux) or `gradlew.bat test` (Windows). Expected results:

| Case | POST manual login | Subsequent GET /whoami |
| --- | --- | --- |
| `setContext` only, no save | 200 on current login request | **401**, even with the same session |
| Set + `repository.saveContext(...)` | 200 on login request | **200**, returns `mai` with the same session |
| Request from another session | No saved context | **401** |
| POST login without CSRF token | **403** | Does not run valid authentication |

This test suite runs the **real Spring Security filter chain** inside MockMvc and sends the same `MockHttpSession` across separate requests. It is far more reliable than a test that merely invokes a controller method and asserts the holder has authentication in the same stack frame.

**Execution note:** the example is designed to compile and run on Java 17 with Spring Boot 3.5.7; the results above are expectations derived from the stated configuration, not output from an actual test run in this document. When running in a project environment, if tests differ, check versions, security chain ordering, CSRF, session repository, custom middleware, and request cache before changing code.

## 6. Why Does Standard Form Login Still "Auto-Save" Even Though HolderFilter Does Not Save?

Because the **context-management filter** and the **authentication mechanism** are two different layers of responsibility.

In standard form login, when a user submits a valid username/password, `UsernamePasswordAuthenticationFilter` (extending `AbstractAuthenticationProcessingFilter`) uses the manager to verify, runs the required session strategy, puts `Authentication` in the context, saves via the repository per Spring Security's configured flow, and invokes the success handler. Developers only need to configure `formLogin` and session behavior properly; they do not write a controller calling `saveContext` manually.

```text
Standard form login:
UsernamePasswordAuthenticationFilter
    ↓ authenticate(...)
    ↓ SessionAuthenticationStrategy (when applicable)
    ↓ SecurityContextHolder.setContext(...)
    ↓ SecurityContextRepository.saveContext(...)
    ↓ AuthenticationSuccessHandler (redirect/response)
    ↓ next request restores context

Manual login:
Controller or custom Filter
    ↓ authenticate(...)
    ↓ [you must run the required session strategy]
    ↓ setContext(...)
    ↓ [you must call saveContext(...) if persistence is wanted]
    ↓ response
```

**Therefore both statements are true:** Spring Security automatically maintains your login when using standard authentication mechanisms; whereas a custom controller that only calls `SecurityContextHolder.setContext(...)` is not automatically saved under Spring Security 6 defaults.

### How Do HTTP Basic, Bearer Token, and Stateless Differ?

A stateless API may receive `Authorization: Basic ...` or a bearer token on every request. The filter verifies the credentials/token from the current request and places authentication into the holder; many configurations do not need to save to a session. In that case, `NullSecurityContextRepository` can be a sensible choice.

Do not try to call `saveContext` into a session to "fix" an API intentionally configured as `SessionCreationPolicy.STATELESS`. Conversely, if a manual login endpoint is expected to create a browser session, configure the repository/session consistently instead of setting stateless and trying to create a session in the controller.

**Note:** HTTP Basic can be customized to save sessions via another repository per Spring Security documentation; do not define every HTTP Basic setup as strictly incapable of having a session.

## 7. Explicit Save, SessionAuthenticationStrategy, and Session Fixation

The sample in Section 5 **only demonstrates persistence** and must not be used as-is for production login. For a new login, beyond `saveContext`, you may need to handle:

- **Session fixation protection:** rotating the session ID when transitioning anonymous → authenticated. Spring Security provides `ChangeSessionIdAuthenticationStrategy` and other strategies depending on Servlet/session setup.
- **Concurrent session control:** if limiting session counts, a `SessionRegistry` and appropriate `SessionAuthenticationStrategy` are required, often combining multiple strategies.
- **Authentication failure/success behavior:** handlers, audit events, login throttling, MFA, remember-me, and logout policies.
- **CSRF and cookies:** keep CSRF protection for cookie-authenticated POSTs; `Secure`/`HttpOnly`/`SameSite`, HTTPS, session timeout, and sensitive data hygiene.
- **Saved requests and redirects:** only redirect after the session/context has been saved properly; never wait until the response commits before saving.

Snippet illustrating the **strategy step before save** when building custom login:

```java
// Assuming authentication has been verified by the manager.
sessionAuthenticationStrategy.onAuthentication(
        authentication, request, response);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
```

This is **integration pseudocode**, requiring a `SessionAuthenticationStrategy` created/configured per session policies and corresponding dependencies; do not copy it into a project without a proper strategy. With standard form login, the framework already invokes the required strategy; calling it again manually can cause double-processing.

**Do not confuse explicit save with creating a safe session.** `saveContext` is persistence; it does not perform session fixation mitigation, login throttling, or MFA on its own.

## 8. Logout: Clearing the Holder Alone Is Not Enough

A similar mistake happens on logout:

```java
SecurityContextHolder.clearContext();
```

This statement only clears the **current** holder. If the repository/session still stores an authenticated context, the next request can reload the old identity. With explicit-save, on logout you must clean up **the persisted state as well** via repository/session and related login tokens per policy.

**Prefer Spring Security's standard logout support:**

```java
http.logout(logout -> logout
        .logoutUrl("/logout")
        .logoutSuccessUrl("/login?logout"));
```

This snippet belongs in security-chain config, not a standalone class. Spring Security provides standard logout handlers (including clearing the security context/session per configuration), and browser POST logouts require a valid CSRF token. Do not create a GET logout just for testing convenience if that bypasses CSRF protection.

If you must implement custom logout, the design must:

1. Reject unauthorized logout requests or those lacking proper CSRF proof when using cookies.
2. Remove `Authentication` from the context and call `SecurityContextRepository.saveContext(emptyContext, request, response)` if required by the repository.
3. Invalidate the HTTP session / revoke cookies or session identifiers per policy.
4. Revoke remember-me/tokens/refresh tokens if used by the application.
5. Never continue processing a logged-out request with the old authentication still in the holder.

Merely clearing a `ThreadLocal` variable, or merely deleting frontend cookies, does not guarantee server-side context/sessions were removed.

## 9. DelegatingSecurityContextRepository and Request Dispatches

Spring Security 6 defaults to `DelegatingSecurityContextRepository`, typically combining:

```java
SecurityContextRepository repository =
        new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository());
```

This snippet illustrates how repositories are composed and can be used when an app wants explicit configuration. It does not replace default configuration when you have no custom needs.

**Each delegate serves a different purpose:**

- `RequestAttributeSecurityContextRepository` keeps the security context available within the **same HTTP request**, including some dispatchers transitioning to ERROR dispatches after the holder has been cleared by the filter lifecycle.
- `HttpSessionSecurityContextRepository` allows the context to be restored on the **next request** if the browser sends the right session cookie.
- `DelegatingSecurityContextRepository` reads from delegates in order and forwards saves to delegates per implementation contract.

If you use **only RequestAttribute repository**, the next request will **not** recover login from the old request attribute. If you use **only HttpSession repository**, check how your application handles ERROR dispatches and responses. If you use **Null repository**, saving does not create cross-request persistence.

### Does SecurityContextHolderFilter Create HttpSession Automatically?

Not directly as HolderFilter's responsibility. Whether an HTTP session is created also depends on the repository, request cache, CSRF, login strategy, Servlet container, and other components. Therefore, never conclude "a session exists so login was saved" or "no new cookie means saveContext definitely didn't run".

### Why Must Save Occur Before Response Commit?

In Servlet HTTP, once a response is committed, adding a `Set-Cookie` header for a new session ID may no longer work. An immediate redirect after login can cause the client to send the next request **before the server saves the context** if custom code gets the ordering wrong.

Rule in a manual controller/filter:

```java
// Already have a valid Authentication and a new context.
SecurityContextHolder.setContext(context);
repository.saveContext(context, request, response);

// Only then commit the response.
response.sendRedirect(request.getContextPath() + "/dashboard");
```

This is a snippet; avoid using it to redirect to an unvalidated client-supplied path, since open redirect is another issue to prevent. Never call `saveContext` in a `finally` block after the response has already committed and expect cookies/sessions to always work.

## 10. Multiple SecurityFilterChains and Per-Chain Repositories

An application may have:

```text
/api/**      -> API chain, bearer token, STATELESS
/portal/**   -> Browser chain, form login, session-based
/other       -> Catch-all chain, separate policy
```

`FilterChainProxy` selects the **first SecurityFilterChain matching the request**. Each chain can have its own `SecurityContextRepository`/session policy:

| Chain | Authentication | Typical Repository / Scope |
| --- | --- | --- |
| API bearer token | JWT/bearer token per request | Null / no session storage |
| Browser form login | Username/password → session | Request attribute + HttpSession |
| A custom manual login endpoint | Must check selected chain | Must use a repository compatible with that chain |

**An error-prone interaction:** a controller under `/portal/**` calls `repository.saveContext(...)`, yet the next request goes to `/api/**`, entering a stateless chain with `NullSecurityContextRepository`. Not recovering the session is **correct per API policy**, not HolderFilter losing the login.

Conversely, if multiple chains accidentally share an HttpSession repository and both read the context, saved authentication can affect authorization on another chain. Separate managers per chain do not automatically create isolated session boundaries. When tenant or trust-domain isolation is required, test cross-chain session state.

### Matchers and Login Endpoints

A chain scoped only to `/portal/**` while registering default form login at `/login` can cause login requests **not to enter the expected chain**. Ensure login, callback/logout, and entry points match the configured chain, and that a catch-all chain does not intercept them unexpectedly.

## 11. Async, ThreadLocal, and Request Lifecycle

`SecurityContextHolder` defaults to `ThreadLocal`. A task running in `@Async`, `CompletableFuture`, or a thread pool **is not automatically guaranteed** to have the same context as the request thread. Wrappers like `DelegatingSecurityContextRunnable`/`DelegatingSecurityContextExecutor` or appropriate context-propagation mechanisms transfer context in a controlled way.

However, **propagating context to another thread** does not mean **persisting context across another HTTP request**. Even if a background task receives `Authentication`, that does not mean the session was saved. Never use `MODE_INHERITABLETHREADLOCAL` as a blanket way to avoid repositories; thread pools and identity lifecycles can be complex and easily leak identities.

With async Servlet dispatches or ERROR dispatches, request attributes and the security filter lifecycle involve extra details. That is why `RequestAttributeSecurityContextRepository` exists; test your application's exact dispatcher types and authentication flows when needed.

## 12. Diagnostic Checklist for "Login Succeeds, Yet Next Request Loses Access"

1. **Identify the Spring Security version** and check whether the filter chain uses `SecurityContextHolderFilter` or legacy `SecurityContextPersistenceFilter`. Never run both in one chain.
2. **Identify the authentication mechanism:** standard form login or custom controller/filter? If standard, do not blindly insert extra saves; check config/filters.
3. **Locate where Authentication is created:** was `AuthenticationManager.authenticate(...)` actually called, or was `authenticated=true` set manually?
4. **Inspect the SecurityContext object:** were `createEmptyContext()` and `setContext(context)` used, or was an old context mutated by reference?
5. **Inspect saveContext:** if manually authenticating in Spring Security 6, was `SecurityContextRepository.saveContext(context,request,response)` called?
6. **Inspect timing:** did save occur **before** `sendRedirect`, body flush, or response commit?
7. **Inspect the repository:** HttpSession, Delegating, RequestAttribute, or Null? Do controller and chain share the same repository?
8. **Inspect session policy:** `STATELESS`, `NEVER`, `IF_REQUIRED`, request cache, and session creation.
9. **Inspect cookies:** does the client send a valid session cookie on the next request? Are SameSite/Secure/Domain/Path, HTTPS, proxy, and CORS credentials right?
10. **Inspect chain matchers:** did the next request hit a different chain or get matched by an earlier catch-all?
11. **Inspect logout/session expiration:** was the session invalidated, did the cookie expire, or are session fixation logic, concurrency policy, or multi-node session store sharing involved?
12. **Check tests:** use `MockMvc` through the filter chain, sending the same `MockHttpSession` on the next request; test a different session too.
13. **Check DEBUG logs in a safe environment:** inspect filter chain and repository save/load without logging passwords, raw tokens, Authorization headers, or cookies.
14. **Compare session vs. stateless:** if the app intentionally authenticates per request, do not expect a browser-style login session.

### Common Symptoms and Causes

| Symptom | Likely Suspects to Check | Fix Direction |
| --- | --- | --- |
| POST login returns 200, immediate GET /me returns 401 | Custom login only set holder | Save context to the right repository before response |
| Login succeeds, yet no cookie/session | Stateless policy or non-session repo | Check whether requirement is truly stateless or stateful |
| Session cookie present, yet GET /me still 401 | Context not saved; wrong cookie; different chain | Test repository, matchers, cookie policy |
| Only ERROR dispatch loses principal | Session-only repository / dispatch setup | Check RequestAttribute repo / Delegating repo |
| Old user still recognized after logout | Session/repository not cleared | Use logout support, clear and save context |
| Unlimited logins ignore session limits | Manual login bypassed SessionAuthenticationStrategy | Integrate strategy or use standard mechanism |
| One chain receives another chain's principal | Unintended shared session/context | Design trust boundaries and test cross-chain |
| `@Async` does not see Authentication | Context sits on request ThreadLocal | Use proper context propagation, never global holder |
| Default form login stops working after adding a chain | Matcher does not cover login POST | Configure login path and chain matchers |
| Code worked before Spring Security 6 upgrade, loses session after | Previously relied on implicit save | Add explicit save for custom flows or use built-in |

## 13. QA Tests to Have When Upgrading Versions or Writing Custom Login

| Test | Verification Requirement |
| --- | --- |
| Default chain uses HolderFilter | No legacy filter running simultaneously |
| Manual set without save | Only current request has authentication; next request 401 |
| Manual set + save | Subsequent request with same session has Authentication |
| Different session | Does not receive logged-in session's identity |
| POST without CSRF token | Rejected when using browser cookie auth |
| Wrong password | Does not save an authenticated SecurityContext |
| Save before redirect | Browser has valid session/cookie on the post-redirect request |
| Logout | Context in session is cleared; next request is no longer authenticated |
| Session timeout or invalidation | Context restoration fails per policy |
| Stateless API | Does not accidentally save session just from Basic/JWT authentication |
| Multiple filter chains | Repository, matchers, and context accurate per chain |
| Concurrent sessions / session fixation | Session ID rotates / limits enforced per policy |
| ERROR dispatch | Principal visibility behaves properly across dispatcher changes |
| Distributed session | Nodes share consistent policies and session store |

Testing solely with `@WithMockUser` **does not prove** the repository saved the session: annotations/post-processors pre-populate authentication for the test request. Perform HTTP login via `MockMvc` and send a **second request with the same session** as in Section 5 to verify real persistence.

When upgrading Spring Security 5 → 6, write out a clear **migration checklist**:

1. Inventory custom controllers, filters, success handlers, or services calling `SecurityContextHolder.setContext`.
2. Identify which rely on implicit save and which already call `repository.saveContext`.
3. Define official repos and session policies for each chain.
4. Migrate custom authentication flows to explicit save in the right order.
5. Verify SessionAuthenticationStrategy, session fixation, concurrent sessions, and logout.
6. Run two-request/cookie/redirect tests, stateless tests, and CSRF tests.
7. Monitor 401/403 spikes, session creation/write load, and login errors after deployment.
8. Do not keep `requireExplicitSave(false)` indefinitely just to avoid fixing code; treat it as a temporary bridge if still supported by your release branch.

## 14. Common Mistakes and How to Avoid Them

1. **Confusing holder with repository:** `SecurityContextHolder.setContext` does not mean the session was saved.
2. **Claiming HolderFilter auto-saves at the end:** it only loads and clears the holder; explicit-save puts saving in the authentication mechanism/application code.
3. **Claiming all Spring Security 6 logins require manual save:** standard authentication mechanisms already handle it.
4. **Using both HolderFilter and PersistenceFilter in one chain:** makes the lifecycle unpredictable; pick only one.
5. **Keeping `requireExplicitSave(false)` as permanent default:** it is a legacy migration path, not an excuse to skip understanding the contract.
6. **Testing Authentication in only one request:** misses missing saves between requests.
7. **Calling save after `response.sendRedirect` or response commit:** may be too late to create/update the session cookie.
8. **Using Null repository and expecting login sessions to persist:** Null does not save context across requests.
9. **Using RequestAttribute repository and expecting a new GET request to be authenticated:** request attributes do not survive across different HTTP requests.
10. **Using different repositories in controller and filter chain:** save and load never meet.
11. **Creating HttpSession manually and skipping saveContext:** having a session does not mean having a context.
12. **Mutating the old context via getter:** risks mutating a shared object and makes persistence hard to reason about.
13. **Manual login skipping SessionAuthenticationStrategy:** loses session fixation/concurrent session protection.
14. **Disabling CSRF to make manual POST login work:** exposes browser/session authentication to risk.
15. **Self-setting authenticated tokens from client data:** bypasses credential verification and grants arbitrary privileges.
16. **Only clearing ThreadLocal on logout:** persisted context in session can be restored on the next request.
17. **Assuming SecurityContextHolderFilter gives `@Async` the principal:** context propagation and persistence are two separate problems.
18. **Assuming two separate AuthenticationManagers automatically isolate sessions:** if repositories/contexts are shared, they remain coupled.
19. **Disabling sessions for an API yet testing cookies like a web browser:** tests do not match the session policy.
20. **Not testing session cookies across proxies/cross-site:** cookie Path, SameSite, Secure, and Domain can drop sessions.
21. **Logging full SecurityContext or Authentication while debugging:** risks leaking PII/credentials/tokens.
22. **Assuming 401 always means wrong password:** the password might be right while context failed to persist.
23. **Skipping logout cleanup after switching to explicit save:** clears the holder without clearing the persisted context.
24. **Upgrading versions without reading migration guides:** differences in default filters/repositories alter behavior.
25. **Storing full domain entities in principal/session:** increases serialization risk, stale roles, and unnecessary data retention.

## 15. Hands-On Exercises

**Exercise 1 — Draw the lifecycles:** draw two diagrams: (a) HolderFilter loading context and clearing the holder without auto-save; (b) legacy PersistenceFilter loading, tracking, and auto-saving. Explain why both must not be used in the same chain.

**Exercise 2 — Run the demo:** run `gradle test` from Section 5. Explain why, using the same `MockHttpSession`, `/manual/unsaved` still returns 401 on the next request while `/manual/saved` returns 200.

**Exercise 3 — Redirects:** modify the saved endpoint to return a redirect after calling `saveContext`; inspect cookies/sessions and the post-redirect request. Reverse the save/redirect order in an exploratory test and explain the committed-response risk.

**Exercise 4 — Repositories:** replace `HttpSessionSecurityContextRepository` with `NullSecurityContextRepository`. Predict which tests change outcomes; explain why explicit save cannot force Null repository to save sessions.

**Exercise 5 — RequestAttribute:** use `DelegatingSecurityContextRepository` with RequestAttribute + HttpSession, testing an ERROR dispatch and a new HTTP request. Distinguish the storage scopes.

**Exercise 6 — Logout:** add standard logout; send a POST with a CSRF token after manual saved login, and verify the next request is no longer authenticated. Do not just clear the holder in a controller.

**Exercise 7 — Multi-chain:** create stateless `/api/**` and stateful `/portal/**`. Identify which chain/repo applies to manual login and test that cookies are not accidentally accepted by the API.

**Exercise 8 — Migration:** simulate a Spring Security 5 custom controller that only calls `setContext`. Upgrade to 6, add a shared repository and explicit save; write a two-request integration test. Verify session fixation/concurrent sessions separately before production.

**Exercise 9 — Async:** create a task running on a separate executor after login. Explain why it lacks the principal automatically, how to use a context-propagating wrapper, and why that does not save the HTTP session.

**Exercise 10 — Security review:** list at least five ways an application can report "login succeeded" without persisting or creating a safe session, including missing `saveContext`, wrong repo, wrong cookies, skipped session strategy, and authentication bypass.

### Completion Criteria

You can answer on your own:

- Where does `SecurityContextHolderFilter` read/store context and does it call `saveContext` automatically?
- How does `SecurityContextPersistenceFilter` differ and how did the default change from Spring Security 5 to 6?
- What does `requireExplicitSave(true)` mean across versions?
- Why does standard form login still work while a manual controller missing save does not?
- What is the difference among `RequestAttribute`, `HttpSession`, `Delegating`, and `NullSecurityContextRepository`?
- When is `saveContext(context, request, response)` needed and why must it run before response commit?
- How do logout, session fixation, concurrent sessions, CSRF, and multiple filter chains relate to persistence?
- How do you write a two-request test with the same session to prove context truly persists?

## 16. Official Documentation for Reference

- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): guide to `SecurityContextRepository`, manual save, default behavior, `requireExplicitSave`, and statelessness.
- [Spring Security 6.5 — Session Management Migrations](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html): Spring Security 5 automatic-save vs. Spring Security 6 explicit-save, default repository, and SessionManagementFilter.
- [Spring Security 6.5 — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5-SNAPSHOT/servlet/authentication/persistence.html): HolderFilter/PersistenceFilter diagrams, request attribute/session delegation, and the need for explicit save. When using a released version, consult the matching versioned page.
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `SecurityContextHolder`, `Authentication`, authentication filters, and success flow.
- [Spring Security 6.5.11 — SecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html): `loadDeferredContext`, `saveContext`, and `containsContext`.
- [Spring Security 6.5 — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): `SecurityFilterChain`, `FilterChainProxy`, ordering, and debugging filters.
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): standard authentication mechanism, success/failure handlers, and security context integration.
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): protecting POSTs and cookie-based session flows.

**Version note:** the Java examples use Spring Boot 3.5.7, corresponding to the Spring Security 6.5.11 API generation. When applying to Spring Security 7 or a custom security filter stack, verify the exact documentation and source code of the running version; avoid extrapolating from behavior in another project or version.