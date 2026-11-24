# Saving Context on Custom Login and Before the Response Commits

Suppose a Java/Spring Security application has a custom login API `POST /api/login`. The controller receives username/password, calls `AuthenticationManager.authenticate(...)` successfully, puts the result into `SecurityContextHolder`, and returns HTTP 200. Immediately afterward, the browser sends the session cookie to `GET /api/me` — yet the server returns 401 or treats the request as anonymous. Why did the **just-succeeded login request** fail to **preserve login on the next request**?

The very common cause in Spring Security 6 Servlet: **placing `Authentication` into `SecurityContextHolder` only affects the currently executing context; to retain it across another HTTP request, custom authentication must save via `SecurityContextRepository.saveContext(context, request, response)`.** Saving must happen **before `HttpServletResponse` is committed** (sending headers/body/redirect or flushing so the response completes at the HTTP level), especially when the repository must create an `HttpSession` and send `Set-Cookie` carrying the new session ID. Once the response has committed, the application may no longer be able to create or send the session cookie in time, and subsequent requests cannot restore the context.

This is a Knowledge lesson in the **Servlet Context** group of *Spring Security - authentication*. It distinguishes **authenticate — set context — save context — send response — load context on the next request**, implements a Spring Boot 3.x / Java 17+ example with custom REST login, session fixation protection, CSRF, and MockMvc tests, and explains response-commit races, default repositories, session strategies, and common pitfalls.

**Quick rule to remember:** After `AuthenticationManager` verifies credentials, create a **new `SecurityContext`**, place the trusted `Authentication` inside it, call `setContext` for the current request, and call **`saveContext` on the right repository before returning or committing the response**. Never expect a `ThreadLocal` variable to turn into a login session on its own. With JWT/stateless flows, the workflow differs: the client must present a token on subsequent requests rather than relying on saving `HttpSession`.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish `SecurityContextHolder`, `SecurityContextHolderStrategy`, `SecurityContext`, `Authentication`, `SecurityContextRepository`, and `HttpSession`.
2. Explain **explicit save** behavior in Spring Security 6: `SecurityContextHolderFilter` primarily loads context; custom auth must save if persistence across requests is required.
3. Recognize when `HttpServletResponse` commits, and the consequences of calling `sendRedirect`, `sendError`, `flushBuffer`, writer flushing, or streaming before `saveContext`.
4. Write a login controller/filter that verifies credentials via `AuthenticationManager`, constructs a new context, and calls `setContext` and `saveContext` in the proper order.
5. Configure **the exact same `SecurityContextRepository`** for the security filter chain and custom login; understand the differences among `HttpSessionSecurityContextRepository`, `RequestAttributeSecurityContextRepository`, `DelegatingSecurityContextRepository`, and `NullSecurityContextRepository`.
6. Avoid omitting session fixation protection, CSRF, and session authentication strategies merely because you wrote a custom login endpoint.
7. Run Spring Boot/MockMvc to prove: valid login creates a session → another request is authenticated; omitting save → session is not persisted; wrong login / missing CSRF is rejected; an authenticated user lacking permissions still gets 403.
8. Check remaining boundaries: async responses, multiple filter chains, request cache, logout, remember-me, stale authorities, and multiple servers.

## 2. Three Boundaries: Authentication, Thread-Local Storage, Cross-Request Persistence

| Component | Responsibility | Does NOT Guarantee on Its Own |
| --- | --- | --- |
| `AuthenticationManager` | Accepts an unauthenticated `Authentication`, calls providers to verify credentials, and returns a valid result or throws an exception. | Does not automatically save the result into `HttpSession` when called directly from a controller. |
| `Authentication` | Holds principal, credentials, authorities, and authentication status. | Does not become an HTTP session on its own. |
| `SecurityContext` | Container holding the `Authentication` for the execution/request. | Does not send session cookies itself. |
| `SecurityContextHolder` / `SecurityContextHolderStrategy` | Binds the context to the current thread/execution (default ThreadLocal in Servlet). | Does not save context for other requests; does not verify passwords itself. |
| **`SecurityContextRepository`** | Reads/saves context per HTTP lifecycle: session, request attribute, or another mechanism. | Does not verify credentials; not every repo persists across multiple requests. |
| `SecurityContextHolderFilter` | Loads/defer-loads context from repository into holder and cleans up the request scope. | In explicit-save configurations, does not watch `setContext` and auto-persist. |
| `HttpServletResponse` | Delivers status, headers, cookies, and body to the client. | Does not guarantee `Set-Cookie` can be added after commit. |

There are **two completely separate storage locations**:

- **Within the current execution:** `SecurityContextHolderStrategy.setContext(context)` lets downstream code in *this request* read `Authentication`.
- **Across a new HTTP request:** `SecurityContextRepository.saveContext(context, request, response)` lets the repository write to a session or appropriate store; the filter on the next request reloads it from the client's cookie/session ID.

A controller can call `SecurityContextHolder.getContext().getAuthentication()` right after `setContext` and see Alice, yet that only proves the **running request's ThreadLocal** has a value. The real test is whether **a new request carrying the cookie** restores Alice.

### 2.1 Login Request and Subsequent Request Diagram

```text
REQUEST A: POST /api/login
    |
    v
CSRF/filter chain (if using cookie session)
    |
    v
Custom controller / authentication filter
    |
    +--> UsernamePasswordAuthenticationToken.unauthenticated(...)
    +--> AuthenticationManager.authenticate(...)
    |        +--> ProviderManager / DaoAuthenticationProvider
    |        +--> UserDetailsService + PasswordEncoder + status
    |
    +--> SessionAuthenticationStrategy (fixation, CSRF... if custom)
    |
    +--> SecurityContext context = createEmptyContext()
    +--> context.setAuthentication(verified)
    +--> SecurityContextHolderStrategy.setContext(context)
    +--> SecurityContextRepository.saveContext(context, req, resp)
    |        +--> HttpSession writes SPRING_SECURITY_CONTEXT
    |        +--> if session creation needed: sends Set-Cookie/JSESSIONID
    |
    +--> Returns 200 / redirect / response body; response commits
    |
    v
Servlet security filter cleans up ThreadLocal

REQUEST B: GET /api/me (browser carries session cookie)
    |
    v
SecurityContextHolderFilter / SecurityContextRepository
    |
    +--> looks up HttpSession by session ID
    +--> loads SecurityContext containing Alice
    |
    v
Authorization: authenticated?
    |
    v
Controller receives Authentication Alice
```

All steps can occur on **two different physical threads**. The repository/session handles persistence; there is no need to enable `MODE_GLOBAL` or `MODE_INHERITABLETHREADLOCAL` to "pass" a principal across requests.

### 2.2 Successful Authentication Does Not Mean the Session Was Saved

In a custom endpoint, these two lines:

```java
Authentication verified = manager.authenticate(loginToken);
SecurityContextHolder.getContext().setAuthentication(verified);
```

are not enough to guarantee the next request is authenticated. You must also account for `SecurityContextRepository`, session creation policy, cookie path/domain/SameSite/Secure, response commit timing, and client token mechanisms.

Spring Security officially recommends creating a **new context** instead of mutating a context retrieved from the holder to reduce races when contexts are shared across sessions/threads:

```java
SecurityContext context = strategy.createEmptyContext();
context.setAuthentication(verified);
strategy.setContext(context);
repository.saveContext(context, request, response);
```

This pattern is **only used after `verified` has actually been verified by a trusted provider**. Never create a token with `authenticated=true` from a client-supplied username/roles.

## 3. Spring Security 5 vs. Spring Security 6: Why Does Explicit Save Matter?

### 3.1 History of the Auto-Save Mechanism

In Spring Security 5 setups using `SecurityContextPersistenceFilter`, the filter could load the context at request start and try to save it back at request end. It also used response wrappers to write before commit if the response finished early. That allowed some custom code that only called `setContext` to still be saved in the session.

However, guessing "did the context change and does it need saving?" caused redundant writes and unpredictable timing scenarios. Spring Security 6 switched the default to `SecurityContextHolderFilter` and requires **explicit saving** when custom authentication wants persistence across requests.

| Aspect | Common Legacy Mechanism | Spring Security 6 Default |
| --- | --- | --- |
| Primary filter | `SecurityContextPersistenceFilter` | `SecurityContextHolderFilter` |
| Role with repository | Loads and auto-handles saving when appropriate | Mainly loads/defer-loads context |
| Custom code calling `setContext` | Could be auto-saved depending on config | **Must call `saveContext`** to persist |
| Write timing | End of request or before response commit via wrapper | Explicitly decided by authentication mechanism |
| SessionAuthenticationStrategy | Legacy configs could rely on `SessionManagementFilter` | Authentication mechanism must run relevant strategies itself |
| Migration risk | Relying on a side effect that no longer exists | Subsequent request becomes anonymous if save is missing |

Never register **both `SecurityContextHolderFilter` and `SecurityContextPersistenceFilter`** in the same chain as a fix. Spring Security 6 documentation emphasizes using only one of the two. For new applications, keep explicit-save and implement the flow properly.

### 3.2 `requireExplicitSave(true)`

In Spring Security 6, `requireExplicitSave(true)` is the default in typical configurations. You can write it explicitly to make intent clear:

```java
http.securityContext(context -> context
        .requireExplicitSave(true)
        .securityContextRepository(repository));
```

**This is only a configuration snippet.** It does not save authentication for you; you must still call `repository.saveContext(...)` in custom login. For code ported from Spring Security 5, search all places calling `SecurityContextHolder.setContext` that previously relied on auto-save, and update the flow properly. Do not revert the entire app to `requireExplicitSave(false)` as a default solution.

### 3.3 How Do Built-In Login and Custom Login Differ?

Built-in login filters (such as Spring Security's form login) already manage authentication, session strategies, success/failure handlers, and saving the context per the framework contract. If you **replace** it with a REST controller or custom servlet filter, **you become responsible** for wiring the equivalent steps properly: authenticate, security context, session fixation/CSRF, save, and response.

Do not accidentally keep another built-in login handler on the same URL or two filters with overlapping matchers. Multiple `SecurityFilterChain`s can use different repositories/managers; verify which chain each request actually traverses.

## 4. Response Commit: The Decisive Moment for Saving a Session

### 4.1 What Does Commit Mean?

An `HttpServletResponse` is committed once the container has sent the status/headers to the client (or started transmitting the response under the servlet container's buffering rules). After that point, the application cannot rely on modifying headers, such as adding `Set-Cookie: JSESSIONID=...`.

Operations that can commit a response or push it to commit:

- `response.sendRedirect("/home")` typically sends 302 + `Location` and commits.
- `response.sendError(401)` or a handler writing an error and flushing.
- `response.flushBuffer()`.
- `response.getWriter().flush()` / output stream flush; depends on buffering, status, and container.
- Streaming large bodies, `StreamingResponseBody`, file downloads, or Server-Sent Events once the first bytes are sent.
- Container auto-flushing when the response body exceeds the buffer; a controller returning `ResponseEntity` followed by completed serialization can also commit.

**Never write logic assuming "after the controller returns, I still have time to save".** Once you transition to writing the response, the window to create/send the session cookie may already be closed.

### 4.2 Wrong Order vs. Right Order

**Wrong: response first, save afterward.**

```java
// WRONG: illustrates an ordering bug, not a complete controller.
Authentication verified = manager.authenticate(loginRequest);
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

response.sendRedirect("/app"); // Response may already be committed!
repository.saveContext(context, request, response); // Too late.
```

Even if `saveContext` does not throw an exception in every container, the HTTP client may not receive the new session ID; login "succeeds" in request A while request B still gets 401. Never infer success solely from a log saying "saveContext invoked".

**Right: save before sending redirect/body.**

```java
Authentication verified = manager.authenticate(loginRequest);
sessionAuthenticationStrategy.onAuthentication(verified, request, response);

SecurityContext context = strategy.createEmptyContext();
context.setAuthentication(verified);
strategy.setContext(context);

repository.saveContext(context, request, response); // Before commit.
response.sendRedirect("/app");                      // After save.
```

This code is still an **integration pattern for an existing flow**: variables must come from actual beans/filters/controllers, credentials must be verified, the session strategy must be properly configured, and the response must be uncommitted.

### 4.3 Why Is "Session Already Written in DB" Still Not Enough?

An `HttpSession`-backed repository may need to create a session if the request does not have one yet. When creating a session, the server must send the **session ID** to the browser via a cookie (or a container-supported session mechanism). If the response is already committed, the new cookie header may never reach the browser. Some systems already have an old session/cookie, so the bug only shows up on **first login** or in an incognito tab. Therefore, test both requests **with no initial session** and requests **already having a pre-login session**.

There is also a race: if response A commits early and the client fires request B before context A is saved, B can load the old/missing context. Saving early before sending the response keeps the ordering clean.

### 4.4 `isCommitted()` Is Only a Diagnostic Tool

`response.isCommitted()` can report whether the response is committed at a given instant, yet **must not be used to defer saving until the last moment before commit**. Proper design saves **before** any step capable of committing, rather than relying on checks/polling. Once committed, do not try to "resend the cookie" by writing late headers.

### 4.5 Servlet Async and Streaming

With async/streaming responses, the body may be written on another thread or after the controller returns. If login happens on the request thread, **save before starting the async stream/redirect**. Never save `SecurityContext` for the first time inside a callback after data has already been written. Distinguish:

- **Context propagation** to an async thread: use matching integration/wrappers.
- **Context persistence** across requests: use `SecurityContextRepository.saveContext`.
- **Response commitment**: limits when headers/cookies can be sent.

A program can propagate properly yet fail to persist because it omitted save, or persist properly yet async tasks lack ThreadLocal because it omitted propagation.

## 5. Choosing the Right SecurityContextRepository for Your Goal

Spring Security provides several implementations:

| Repository | Where Is Data Stored? | Best Suited For | Limitations |
| --- | --- | --- | --- |
| `HttpSessionSecurityContextRepository` | `HttpSession`, typically key `SPRING_SECURITY_CONTEXT`. | Stateful custom login where request B uses a session cookie. | Depends on session/cookies, session creation policy, session fixation, and clustering. |
| `RequestAttributeSecurityContextRepository` | Attribute on the **same request**. | Preserving context across dispatches (e.g., error) within the same request. | Does **not** retain login for a new HTTP request. |
| `DelegatingSecurityContextRepository` | Delegates to multiple repositories, usually request attribute + HttpSession. | Common Spring Security 6 Servlet configuration. | Must know which delegates are active for save/load. |
| `NullSecurityContextRepository` | Does not persist. | Stateless authentication (per-request JWT/Basic) when no session is wanted. | Calling `saveContext` will not produce a session cookie. |
| Custom repository | Redis/DB or other security store per contract. | Cluster scale / specialized policies. | Must handle serialization, TTL, concurrency, consistency, cleanup, and error handling. |

### 5.1 Configure the Same Repository Instance for Filter Chain and Login Controller

If custom login calls `repoA.saveContext` while `SecurityContextHolderFilter` reads from a different `repoB` or `NullSecurityContextRepository`, saving may succeed in A while request B remains anonymous. The safe approach is to declare a single bean and **use that exact bean**:

```java
@Bean
SecurityContextRepository securityContextRepository() {
    return new HttpSessionSecurityContextRepository();
}

@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        SecurityContextRepository repository) throws Exception {
    return http
        .securityContext(context -> context
            .requireExplicitSave(true)
            .securityContextRepository(repository))
        // ... authorization, CSRF, session policy ...
        .build();
}
```

The controller receives the exact same `SecurityContextRepository repository` via constructor injection. This is an abbreviated configuration, **not a standalone app**; the complete example is in Section 8.

### 5.2 Default DelegatingSecurityContextRepository

In typical Spring Security 6 configurations, the default repository for Servlet is `DelegatingSecurityContextRepository`, combining `RequestAttributeSecurityContextRepository` and `HttpSessionSecurityContextRepository`. Idea: have context for servlet dispatches within the **same request**, while also allowing persistence across **multiple requests** via session when appropriate.

Explicit bean creation example:

```java
@Bean
SecurityContextRepository securityContextRepository() {
    return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository());
}
```

If you replace it with **only** `HttpSessionSecurityContextRepository` in a demo, session login still works; however, you lose some request-attribute benefits for error dispatches. That is an intentional teaching choice, not advice to replace all production defaults.

### 5.3 How Does SessionCreationPolicy Affect This?

- `IF_REQUIRED`: can create a session when needed; suits custom stateful login.
- `ALWAYS`: eagerly creates a session for every request per config; usually unnecessary.
- `NEVER`: Spring Security does not proactively create one, yet can use an existing session; if you expect a new session on first login, check the exact policy and repository.
- **`STATELESS`:** Spring Security neither creates nor uses a session to store security context, usually paired with `NullSecurityContextRepository`. **Do not expect calling `saveContext` on Null repo to create a login session.**

Decide clearly whether the API uses **stateful cookies** or **stateless tokens**, never mixing both accidentally. Browsers using session cookies need CSRF defense; bearer tokens in `Authorization` have a different lifecycle and policy.

### 5.4 The Repository Can Decline to Save Even If save Is Called

`HttpSessionSecurityContextRepository` contains logic that skips saving empty/anonymous contexts, has an option not to create sessions, and depends on session creation capability and an uncommitted response. If code constructs an anonymous/unauthenticated `Authentication` or the repo has `allowSessionCreation=false`, calling save may not create a new session. **Check the outcome on the subsequent request**, not just how many times the method was invoked.

## 6. Safe Ordered Algorithm for Custom Login

A stateful custom login should follow this minimum sequence:

1. **Request and CSRF:** if using cookie sessions for browsers, ensure the login request passes CSRF policy; validate input types/lengths; never print passwords.
2. **Create unauthenticated token:** use `UsernamePasswordAuthenticationToken.unauthenticated(username, rawPassword)`; never self-assign authorities or `authenticated=true` from client input.
3. **Verify:** call `AuthenticationManager.authenticate(...)`. Proceed only if a valid authenticated result is returned. Exception → generic rejection response; never save a fake context.
4. **Session authentication strategy:** for custom login, run the relevant policies (session fixation, CSRF token rotation/clearing, concurrent sessions if configured).
5. **New context:** `SecurityContextHolderStrategy.createEmptyContext()`, set the verified `Authentication`.
6. **Bind to current request:** `strategy.setContext(context)`.
7. **Save:** `repository.saveContext(context, request, response)` on the right repo, while the response is **uncommitted**.
8. **Send response:** return 200/204/302 along with the required cookie/session ID; never return hashes, credentials, or raw `UserDetails`.
9. **Next request:** sends the corresponding cookie, and the filter loads the context from the repository; authorization uses the restored Authentication. If no session is wanted, issue/verify bearer tokens in a separate flow.
10. **Logout/revocation:** invalidate the session and clear the context in the repository per policy; clearing ThreadLocal alone is not logout.

**Never swap steps 7 and 8.** Also never call `saveContext` **before** verifying credentials. Saving an unverified context can open an access vulnerability depending on authorization rules.

### 6.1 Concerns a Custom Flow Must Solve Itself

A custom controller performing only `authenticate + set + save` can persist a session, yet **does not automatically replicate all behavior** of `UsernamePasswordAuthenticationFilter`:

- Session fixation protection: rotating the session ID after login if a pre-auth session existed, using an appropriate `SessionAuthenticationStrategy`.
- CSRF token rotation/clearing when identity changes, if the app uses cookies + CSRF.
- Concurrent session control / `SessionRegistry` if limiting active sessions.
- Authentication success/failure events and auditing/metrics per policy.
- Login failure rate limiting, account lockout, credential-stuffing protection, and MFA/step-up if needed.
- Remember-me, saved-request redirects, request cache, and logout semantics.
- Error handling when the session store/replica fails: never return "login successful" if the session was not persisted per contract.
- Session cookie attributes: `Secure`, `HttpOnly`, `SameSite`, path/domain, and HTTPS/TLS.

In the runnable example, we implement **session fixation protection + CSRF token invalidation** via `CompositeSessionAuthenticationStrategy`, though production still requires evaluating all the policies above for your architecture.

## 7. Pure Java 17: Modeling Save/Commit Ordering

This is a **JDK 17 example without Spring** to illustrate operation ordering, not an exact simulation of every servlet container. `FakeResponse` merely demonstrates that once a response is committed, adding a cookie is no longer guaranteed.

File `SaveBeforeCommitDemo.java`:

```java
public final class SaveBeforeCommitDemo {

    static final class FakeResponse {
        boolean committed;
        boolean sessionCookieSent;

        void saveSession() {
            if (committed) {
                throw new IllegalStateException("response already committed");
            }
            sessionCookieSent = true;
        }

        void redirect() {
            committed = true;
        }
    }

    public static void main(String[] args) {
        FakeResponse correct = new FakeResponse();
        correct.saveSession();
        correct.redirect();

        System.out.println("correct-cookie=" + correct.sessionCookieSent);
        System.out.println("correct-committed=" + correct.committed);

        FakeResponse wrong = new FakeResponse();
        wrong.redirect();
        try {
            wrong.saveSession();
            System.out.println("wrong-save-rejected=false");
        } catch (IllegalStateException expected) {
            System.out.println("wrong-save-rejected=true");
        }
        System.out.println("wrong-cookie=" + wrong.sessionCookieSent);
    }
}
```

Compile and run:

```bash
javac SaveBeforeCommitDemo.java
java SaveBeforeCommitDemo
```

Exact stdout:

```text
correct-cookie=true
correct-committed=true
wrong-save-rejected=true
wrong-cookie=false
```

**Illustration limit:** `FakeResponse` intentionally throws an exception after commit so failure is visible. `HttpSessionSecurityContextRepository` and servlet containers **are not required to throw this exact exception**; they may return normally while the client never receives `Set-Cookie`. In real Spring, test with an integration test using a fresh HTTP client and real sessions/cookies.

## 8. Complete Spring Boot 3.x Example: Custom REST Login Persisting Session

Uses **Java 17+, Spring Boot 3.3.13, Spring Security 6.x**, storing demo users in memory and persisting security context via `HttpSession`. Includes:

- `POST /api/login`: custom controller performing real authentication via `AuthenticationManager`; invokes session strategy, `setContext`, and `saveContext` **before** returning the body.
- `GET /api/me`: requires authenticated, reads principal and authorities on a subsequent request.
- `GET /api/admin`: requires `ROLE_ADMIN`.
- `POST /api/logout`: uses Spring Security LogoutFilter instead of only `clearContext`.
- CSRF **not disabled**; tests use `spring-security-test` to supply valid tokens.
- Two local demo users: `alice` with `ROLE_USER`, `bob` with `ROLE_ADMIN`, with distinct passwords.

Hardcoded accounts/passwords are for localhost learning only, not production configuration. The Boot version is pinned for lesson reproducibility, **not a recommendation to run an end-of-support branch for new production systems**.

### 8.1 Layout and Gradle

```text
custom-context-save/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/CustomContextSaveApplication.java
    └── test/java/demo/CustomContextSaveTest.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'custom-context-save'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
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

No database is needed for this demo; `InMemoryUserDetailsManager` keeps verifiers only in the JVM, while `HttpSessionSecurityContextRepository` stores `SecurityContext` in the session. For multi-node production, move the session store per architecture, such as Spring Session Redis, and verify consistency.

### 8.2 Application and Spring Security Configuration

File `src/main/java/demo/CustomContextSaveApplication.java`:

```java
package demo;

import java.util.List;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.context.SecurityContextHolderStrategy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CustomContextSaveApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomContextSaveApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("local-demo-password"))
                        .roles("USER")
                        .build(),
                User.withUsername("bob")
                        .password(encoder.encode("different-demo-password"))
                        .roles("ADMIN")
                        .build());
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
        // Same bean used by both SecurityFilterChain and controller.
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    CsrfTokenRepository csrfTokenRepository() {
        return new HttpSessionCsrfTokenRepository();
    }

    @Bean
    SessionAuthenticationStrategy sessionAuthenticationStrategy(
            CsrfTokenRepository csrfRepository) {
        return new CompositeSessionAuthenticationStrategy(List.of(
                new ChangeSessionIdAuthenticationStrategy(),
                new CsrfAuthenticationStrategy(csrfRepository)));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository repository,
            CsrfTokenRepository csrfRepository) throws Exception {

        return http
                .securityContext(context -> context
                        .requireExplicitSave(true)
                        .securityContextRepository(repository))
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.IF_REQUIRED))
                .csrf(csrf -> csrf.csrfTokenRepository(csrfRepository))
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(HttpMethod.POST, "/api/login")
                            .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/me")
                            .authenticated()
                        .requestMatchers(HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .anyRequest().denyAll())
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint((request, response, e) ->
                                response.sendError(
                                        HttpServletResponse.SC_UNAUTHORIZED)))
                .formLogin(AbstractHttpConfigurer::disable)
                .httpBasic(AbstractHttpConfigurer::disable)
                .logout(logout -> logout
                        .logoutUrl("/api/logout")
                        .permitAll()
                        .logoutSuccessHandler((request, response, auth) ->
                                response.setStatus(
                                        HttpServletResponse.SC_NO_CONTENT)))
                .build();
    }
}

record LoginRequest(String username, String password) {
}

record LoginResponse(String status, String username) {
}

@RestController
class CustomLoginController {

    private final AuthenticationManager authenticationManager;
    private final SecurityContextRepository repository;
    private final SessionAuthenticationStrategy sessionStrategy;
    private final SecurityContextHolderStrategy holder;

    CustomLoginController(
            AuthenticationManager authenticationManager,
            SecurityContextRepository repository,
            SessionAuthenticationStrategy sessionStrategy) {
        this.authenticationManager = authenticationManager;
        this.repository = repository;
        this.sessionStrategy = sessionStrategy;
        this.holder = SecurityContextHolder.getContextHolderStrategy();
    }

    @PostMapping("/api/login")
    ResponseEntity<LoginResponse> login(
            @RequestBody LoginRequest input,
            HttpServletRequest request,
            HttpServletResponse response) {

        if (input == null
                || input.username() == null
                || input.username().isBlank()
                || input.password() == null
                || input.password().length() > 256) {
            return ResponseEntity.badRequest().body(
                    new LoginResponse("invalid_request", ""));
        }

        try {
            // 1. Input is unverified; never self-assign roles.
            Authentication requested =
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            input.username(), input.password());

            // 2. Manager/Provider verifies username, password hash, and status.
            Authentication verified =
                    authenticationManager.authenticate(requested);

            // 3. Mitigate session fixation and clear old CSRF token
            //    per session authentication strategy configuration.
            sessionStrategy.onAuthentication(verified, request, response);

            // 4. Create a new context after authentication succeeds.
            SecurityContext context = holder.createEmptyContext();
            context.setAuthentication(verified);
            holder.setContext(context);

            // 5. SAVE BEFORE controller returns body / commits response.
            repository.saveContext(context, request, response);

            return ResponseEntity.ok(
                    new LoginResponse("ok", verified.getName()));
        } catch (AuthenticationException failure) {
            // Generic message; do not leak whether the user exists.
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(
                    new LoginResponse("rejected", ""));
        }
    }

    @GetMapping("/api/me")
    Map<String, Object> me(Authentication authentication) {
        return Map.of(
                "username", authentication.getName(),
                "authorities", authentication.getAuthorities().stream()
                        .map(granted -> granted.getAuthority())
                        .sorted()
                        .toList());
    }

    @GetMapping("/api/admin")
    String adminOnly() {
        return "admin";
    }
}
```

**Runnability:** One Java file contains a single public class `CustomContextSaveApplication`; the remaining records/controller are package-private in the same `package demo`. Gradle downloads Spring Boot Web/Security and spring-security-test; Java 17 supports records and `Stream.toList()`. The demo needs no JPA, JDBC, or external database.

### 8.3 Explaining Decisions in the Code

**A. Why is the manager declared explicitly?** So the custom controller genuinely invokes `ProviderManager` containing `DaoAuthenticationProvider`, loading `UserDetails` from `InMemoryUserDetailsManager` and using the matching `PasswordEncoder`. Never pass raw passwords into `UserDetailsService` and compare strings yourself. If adding another provider, check `supports` and ordering/fallback.

**B. Why an `unauthenticated` token?** A username/password newly arrived from the client is not proof yet. Only a succeeding provider returns a trusted `Authentication`. Never call the `authenticated(...)` factory with roles passed from the request.

**C. Why does strategy run after authenticate yet before save?** When logging in from a pre-login session, `ChangeSessionIdAuthenticationStrategy` rotates the session ID to mitigate session fixation. `CsrfAuthenticationStrategy` clears/resets the old token via the repository mechanism on identity change. If you save first and then rotate the session/commit the response, the lifecycle becomes hard to control and can produce inconsistent cookies/contexts.

**D. Why use the exact same repository bean?** The chain's `SecurityContextHolderFilter` loads using that instance; the controller also saves to that instance. This prevents "repo A saves, repo B loads" bugs when multiple chains or custom adapters exist.

**E. Why is `saveContext` before `ResponseEntity.ok`?** Spring MVC processes the body when the controller returns; saving in the controller before `return` is a clear pre-commit point. If you call `response.getWriter().println(...)`, flush, and only save at the end, timing can break.

**F. Why not disable CSRF to make the demo easier to run?** Custom REST login uses browser session cookies, so CSRF can matter on both the login endpoint and state-changing endpoints. `spring-security-test` provides helpers to send CSRF tokens in tests. If an app is pure bearer-token without cookies, evaluate CSRF differently instead of disabling CSRF app-wide mechanically.

**G. Why not use `HttpSession` directly to set `SPRING_SECURITY_CONTEXT`?** Repository is the abstraction managing save/load; manipulating raw attribute strings easily bypasses logic that skips anonymous saves, session creation policies, and other repositories. In Spring Security 6, the public API to save is `saveContext`.

**H. Why not set a JVM-wide strategy?** `SecurityContextHolder.getContextHolderStrategy()` retrieves the strategy the framework is using, typically `MODE_THREADLOCAL`. Do not switch to `MODE_GLOBAL` to keep login across requests; persistence belongs to the repository.

### 8.4 Automated Testing Through Real MockMvc HTTP Requests

File `src/test/java/demo/CustomContextSaveTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
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

import org.springframework.security.web.context
        .HttpSessionSecurityContextRepository;
import org.springframework.security.core.context.SecurityContext;

@SpringBootTest
@AutoConfigureMockMvc
class CustomContextSaveTest {

    @Autowired
    MockMvc mvc;

    private MvcResult login(
            String username, String password) throws Exception {
        return mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"username":"%s","password":"%s"}
                        """.formatted(username, password)))
                .andReturn();
    }

    @Test
    void correctLoginIsSavedAndAvailableInNextRequest()
            throws Exception {
        MvcResult result = login("alice", "local-demo-password");
        assertEquals(200, result.getResponse().getStatus());

        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);

        Object saved = session.getAttribute(
                HttpSessionSecurityContextRepository
                        .SPRING_SECURITY_CONTEXT_KEY);
        assertNotNull(saved);
        SecurityContext context = (SecurityContext) saved;
        assertEquals("alice", context.getAuthentication().getName());

        // A NEW MockMvc request sharing the same server session.
        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"));

        mvc.perform(get("/api/admin").session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void wrongPasswordDoesNotSaveAuthenticatedContext()
            throws Exception {
        MvcResult failed = login("alice", "wrong-password");
        assertEquals(401, failed.getResponse().getStatus());

        MockHttpSession session =
                (MockHttpSession) failed.getRequest().getSession(false);
        if (session != null) {
            assertNull(session.getAttribute(
                    HttpSessionSecurityContextRepository
                            .SPRING_SECURITY_CONTEXT_KEY));
        }

        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void loginRequiresCsrfTokenForCookieBasedFlow()
            throws Exception {
        mvc.perform(post("/api/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"alice",
                                 "password":"local-demo-password"}
                                """))
                .andExpect(status().isForbidden());
    }

    @Test
    void existingPreLoginSessionChangesIdAfterAuthentication()
            throws Exception {
        MockHttpSession preLoginSession = new MockHttpSession();
        String oldId = preLoginSession.getId();

        MvcResult response = mvc.perform(post("/api/login")
                .session(preLoginSession)
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"username":"bob",
                         "password":"different-demo-password"}
                        """))
                .andExpect(status().isOk())
                .andReturn();

        MockHttpSession newSession =
                (MockHttpSession) response.getRequest().getSession(false);
        assertNotNull(newSession);
        assertNotEquals(oldId, newSession.getId());

        mvc.perform(get("/api/admin").session(newSession))
                .andExpect(status().isOk());
    }
}
```

**On wrapped long imports:** Java permits line breaks between tokens as formatted above, though to minimize formatter/IDE friction, you may write the test's `import static` and `import` statements as **one line per import** by convention. Never leave a dot at the end of a line followed by whitespace/comments that break tokenization; here the line breaks sit before the `.` so the compiler treats them as contiguous tokens.

To avoid any ambiguity when typing manually, the **standard single-line imports** for the wrapped lines are:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.core.context.SecurityContext;
```

The imports already appearing in the test refer to the same classes/members; **never keep duplicates when assembling the file**. The test code already uses the exact names; IDEs/formatters simply normalize import lines if desired.

### 8.5 Running

Using the included Gradle wrapper:

```bash
./gradlew test
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat bootRun
```

If there is no wrapper yet and a compatible Gradle is installed, use `gradle test` / `gradle bootRun`. Do not run `javac CustomContextSaveApplication.java` standalone because the project requires Spring Boot/Web/Security dependencies.

**Expected:** `./gradlew test` runs all four MockMvc tests successfully when the project is set up properly. These are **expected results based on the code**, not stdout captured in the reader's environment. Spring/Gradle logs vary by machine and version.

| Case | Expected HTTP | Evidence |
| --- | --- | --- |
| Alice valid login, valid CSRF | 200, body `status=ok` | AuthenticationManager verified; controller saved context. |
| New `GET /api/me` request with Alice's session | 200, username `alice` | Repository persisted it, filter loaded it. |
| Alice `GET /api/admin` | 403 | Authenticated, yet lacks ROLE_ADMIN. |
| Login with wrong password | 401 | No authenticated success context created. |
| POST login missing CSRF | 403 | CSRF filter blocks before custom controller. |
| Bob login with pre-login session | 200, session ID changed | Session fixation protection invoked in custom flow. |
| Bob `GET /api/admin` with new session | 200 | Context saved properly and ADMIN role valid. |

With browsers or manual curl, you must fetch the real CSRF token along with the session cookie before sending POST JSON. The demo does not expose a separate `/api/csrf` endpoint; therefore, **use the MockMvc tests** rather than disabling CSRF or forging an arbitrary token string. In production, an SPA can obtain a CSRF token via a dedicated endpoint/cookie by design while preserving origin/session boundaries.

### 8.6 Do Not Claim Tests Prove Everything

MockMvc proves that Spring Security filters/controllers and mock requests/sessions interact properly in the configuration above. It is **not yet** a test with real browser cookies, HTTPS reverse proxies, Tomcat response buffering, or a Spring Session Redis cluster. For production, add integration/E2E tests through a real HTTP client, cookie jar, and multiple nodes; specifically verify **`Set-Cookie` before response commit** and that request B is authenticated. Never assume load balancer/session store configs are always right just because MockMvc passed.

## 9. Comparing the Missing-Save Bug

Suppose a custom login only has:

```java
Authentication verified = authenticationManager.authenticate(requested);
SecurityContext context = holder.createEmptyContext();
context.setAuthentication(verified);
holder.setContext(context);

return ResponseEntity.ok(new LoginResponse("ok", verified.getName()));
```

The login request returns 200 and code in the **same request** can read Alice from `SecurityContextHolder`. Yet if `SecurityContextHolderFilter` uses explicit save, `HttpSessionSecurityContextRepository` **was never told to save**. After filter cleanup, request B reloads from the repository and finds no context; `/api/me` can return 401.

**Right fix:** add `repository.saveContext(context, request, response)` before `return`, ensuring the chain and login share the exact same repo. Never replace it with:

```java
request.getSession().setAttribute("user", verified.getName());
```

That line only saves an arbitrary attribute, not the `SecurityContext` that Spring Security loads. Writing the session attribute yourself under the key `SPRING_SECURITY_CONTEXT` is also discouraged: it bypasses the abstraction, save conditions, and other repositories.

### 9.1 Why Can the First Controller Be Authenticated While the Next Request Gets 401?

Because the current context resides in request A's holder. Downstream authorization in that same request A can use it. Once the request completes, the filter clears ThreadLocal; request B loads context from the repo. If the repo has no data, B does not know Alice. The same symptom can also occur if the client fails to send/receive cookies, or if the session expired; inspect both server-side and HTTP layers.

### 9.2 Why Is Putting Save in `finally` Wrong?

`finally` typically runs after the body/redirect has already been written or the response has committed, depending on code structure. At that point, session cookies are no longer guaranteed. **Do not treat persistence as cleanup.** Save on the **authentication success** path, after the session strategy, **before** writing the response; ThreadLocal cleanup at the request boundary belongs to the filter.

### 9.3 Login Succeeds, Yet `saveContext` Fails

If the session store suffers an outage/quota error or the repo throws an exception, the app must not return an "ok" body and emit a half-baked state under a stateful login policy. Proper exception handling, metrics/auditing, and a safe error response (e.g., 503) are required, avoiding claiming login succeeded when the client cannot use the session. Never catch all errors and silently proceed.

## 10. Logout, Deleting Context, and Response Timing

Saving `Authentication` at login is only half of the lifecycle. Logout must remove the context from where it was persisted, invalidate the session, and handle cookies/tokens per policy.

Using Spring Security logout support is usually better than writing it yourself:

```java
http.logout(logout -> logout
        .logoutUrl("/api/logout")
        .permitAll());
```

With cookie-session APIs, keep CSRF on POST logout. Standard logout filters/handlers handle `SecurityContext` and sessions per configuration. If writing a custom logout controller, you must:

- Check user/session scope and CSRF.
- Clear `SecurityContextHolder`/strategy for the current execution.
- Remove context from `SecurityContextRepository` per its contract (not just clearing ThreadLocal).
- Invalidate `HttpSession` or clear session state properly, handling cookie expiration per container.
- If remember-me/refresh tokens/JWTs exist, revoke them per policy; logging out a session **does not automatically revoke bearer tokens**.
- Send the response after state has been revoked; never send a "logout success" body first and clean up afterward.

Never call `SecurityContextHolder.clearContext()` alone and assume you "logged out all devices". Old session IDs/cookies may still map to saved contexts.

## 11. Session Fixation and CSRF in Custom Login

### 11.1 Why Must the Session ID Change on Login?

An attacker can trick a victim into using a pre-login session ID known to the attacker. If the same session ID remains after login, the attacker may try to reuse the elevated session (*session fixation*). Spring Security's built-in authentication includes session fixation protection, whereas **custom controllers do not automatically run all strategies by default**. With Servlet 3.1+, `ChangeSessionIdAuthenticationStrategy` asks the container to rotate the current session's ID after authentication.

In the example, the strategy runs **after** `AuthenticationManager.authenticate` succeeds and **before** `saveContext`/response. Do not rotate the session ID on every wrong password, and do not arbitrarily call `request.changeSessionId()` on a non-existent session. With concurrent sessions or a session registry, substitute a policy-appropriate `CompositeSessionAuthenticationStrategy` and test the full lifecycle.

### 11.2 CSRF on the Login Endpoint

Even though login is not a business-data CRUD operation, **login CSRF** can force a browser to log into an attacker-controlled account, skewing user actions and attribution. For cookie-based applications, CSRF protection must be evaluated on login too. The demo keeps the default filter and uses `CsrfAuthenticationStrategy` to clear old tokens upon identity change.

When integrating an SPA or frontend, CSRF tokens must typically be fetched through a pre-designed flow alongside cookies/sessions; do not disable `csrf()` app-wide just because a JSON POST lacked a token. For APIs using only bearer headers and no cookies for authentication, CSRF evaluation differs, yet CORS, token storage, and credential forwarding must still be verified.

### 11.3 SessionAuthenticationStrategy Is Not Called Automatically Just Because a Bean Exists

Spring Security 6 by default does not rely on `SessionManagementFilter` to detect every new authentication. Custom authentication mechanisms must **invoke** the required session strategies themselves or use built-in abstractions that already support them. Declaring a `SessionAuthenticationStrategy` bean and calling only `setContext` does not guarantee session fixation protection/concurrency ran.

If enforcing `maximumSessions` or registering a `SessionRegistry`, additional strategies and authentication success flows must also be configured; the demo code only illustrates fixation + CSRF and does not claim complete concurrent-session control.

## 12. Authentication Success Handler in a Custom Filter

When writing a custom Servlet filter instead of a controller, the principle is identical. Ordering pattern inside `successfulAuthentication` / custom success branch:

```java
// After the filter has obtained a verified Authentication from the manager.
sessionAuthenticationStrategy.onAuthentication(
        verified, request, response);

SecurityContext context = strategy.createEmptyContext();
context.setAuthentication(verified);
strategy.setContext(context);

securityContextRepository.saveContext(
        context, request, response);

// Only now write body, redirect, or invoke a success handler
// that may commit the response.
successHandler.onAuthenticationSuccess(
        request, response, verified);
```

**This pattern is only a fragment plugged into a custom filter with appropriate context.** If you extend `AbstractAuthenticationProcessingFilter`, the superclass/built-in success flow may already manage context/saving; read its implementation to avoid double-saving or double-redirecting. In particular, `AuthenticationSuccessHandler` may call `sendRedirect` and commit immediately, so it must run **after saving** if your flow controls it manually.

If a custom filter extends `OncePerRequestFilter` and performs authentication itself, consider filter ordering, exception handling, session strategy, context repository, CSRF, request/response wrappers, and avoid registering the filter **twice** (both as a `@Component` servlet filter and via `addFilterBefore`). Never use a static global `Authentication` across requests.

## 13. Multiple SecurityFilterChains and Two Repo Configuration Mistakes

### 13.1 Two-Chain Example

Suppose:

```text
Chain A: /api/**    STATELESS + NullSecurityContextRepository
Chain B: /web/**    IF_REQUIRED + HttpSessionSecurityContextRepository

Custom login lives at /api/login yet wants a session for /web/home.
```

This is a risky situation: login executes on stateless Chain A, saves to a different repo or creates no cookie per policy, while request B enters Chain B. Just because the controller uses `HttpSessionSecurityContextRepository` does not prove security chain and cookie policies align. Pick one clear flow (cookie session or bearer token) and align matchers, repositories, and session policies consistently. If two chains must cooperate, configure intentionally and test end-to-end.

### 13.2 Saving to Request Attribute Does Not Persist to a New Request

`RequestAttributeSecurityContextRepository.saveContext` helps with error dispatches/forwards within a single request, yet does not give a new request a login session. If set as the sole repository and returning 200, the client remains anonymous on request B. Use a session repo or a session-backed delegate when cross-request persistence is needed.

### 13.3 Stateless Does Not Mean No Context Within the Request

A JWT/bearer resource server typically sets `Authentication` into `SecurityContextHolder` when verifying the token on each request, without persisting a cookie session. `NullSecurityContextRepository` can be the right choice. Do not "fix" a stateless API by forcing `HttpSession` creation when the product requires token-only auth.

### 13.4 Cookies Not Reaching the Browser

Even when the server saves `SPRING_SECURITY_CONTEXT` properly, the client may fail to send cookies due to:

- `Secure` cookie while requests travel over insecure HTTP.
- `SameSite`, `Domain`, or `Path` mismatched with the frontend/API origin.
- Wrong CORS credentials mode; browser neither sends nor accepts cross-origin credentials.
- Proxy/load balancer rewriting host/path/scheme or stripping `Set-Cookie`.
- Node A's session store not shared with node B; sticky sessions or Spring Session misconfigured.
- Cookie never sent because the response committed before session creation.

**Inspect `Set-Cookie` and `Cookie` headers in real HTTP tests**, while never logging full cookies/session IDs in production logs.

## 14. Anti-Patterns to Avoid

### A. Creating an Authenticated Authentication Directly from the Request

```java
// WRONG: client-declared, never checked by manager/provider.
Authentication forged =
        UsernamePasswordAuthenticationToken.authenticated(
                usernameFromRequest,
                null,
                AuthorityUtils.createAuthorityList("ROLE_ADMIN"));

SecurityContextHolder.getContext().setAuthentication(forged);
```

Even if the repository saves it, it only saves a **forged identity**. The most critical step remains verifying valid credentials/tokens before creating a privileged principal.

### B. Saving After Redirect

```java
// WRONG:
response.sendRedirect("/app");
repository.saveContext(context, request, response);
```

The client may never receive the session cookie. Always save **before** redirecting.

### C. Calling Only setContext and Assuming Persistence

```java
// WRONG if login must survive across requests in Spring Security 6:
SecurityContextHolder.setContext(context);
return ResponseEntity.ok().build();
```

The context is cleaned up by filters after the request. A repository save is required.

### D. Saving Through a Different Repo Than the One Loading

```text
Controller saves: HttpSessionSecurityContextRepository A
Filter chain loads: NullSecurityContextRepository B
Next request: anonymous
```

Use a consistent repository/chain; never test only the login request.

### E. Disabling CSRF or Session Fixation Protection to "Fix 403"

An HTTP 403 on POST login may be due to CSRF, not a wrong password. Disabling protections without analyzing the credential/cookie model opens vulnerabilities. With custom session logins, handle fixation after authentication.

### F. Storing a Plain Username String Instead of SecurityContext

```java
request.getSession().setAttribute("username", authentication.getName());
```

That is just arbitrary data. Security filters do not turn it into an `Authentication`. Use the repository.

### G. Saving After Writing StreamingResponseBody

Once the response stream sends the first bytes, a new `Set-Cookie` may not go out. Custom login should never be placed at the end of a stream; authenticate and save pre-commit.

### H. Thinking HTTP 200 on Login Is Sufficient Testing

No. Without a request B sending the cookie and verifying the principal, tests can miss persistence bugs completely. Check both the session repository and network cookies.

## 15. Boundary Test Matrix

| Scenario | Action | Result to Prove |
| --- | --- | --- |
| Valid custom login, no prior session | POST login with valid CSRF/credentials | 200 and session/context saved; client receives cookie. |
| Request B with issued cookie | GET protected | 200, principal from repository matches the user. |
| Request B without cookie | GET protected | 401/redirect per entry point, no mistaken principal. |
| Login with wrong password | POST login | 401, no authenticated context created. |
| Login missing CSRF in cookie flow | POST login without token | 403; custom controller does not bypass it. |
| Login disabled/locked user | Manager authenticates | Rejected, context not persisted. |
| Login Alice, call ADMIN URL | GET admin | 403 even though Alice is authenticated. |
| Login Bob with ADMIN | GET admin | 200 with proper principal/authority. |
| Missing `saveContext` | Login returns local success | Subsequent request anonymous: caught by integration test. |
| Save after `sendRedirect` | Response already committed | New cookie/session not guaranteed; fails fresh HTTP client test. |
| Save before `sendRedirect` | Response uncommitted | Client receives session/cookie and request B is authenticated. |
| Save after `flushBuffer` | Response committed | `Set-Cookie` cannot be guaranteed; never use this pattern. |
| Pre-login session | Login succeeds | Session ID rotated per fixation policy. |
| Custom repo RequestAttribute-only | Save locally then new request | Must not assume cross-request persistence. |
| Null repo / stateless | Verify token per request | No login session created; next request must carry token. |
| Multiple filter chains | Login and API on different chains | Authentication persistence/policy consistent with design. |
| Session expiry | Send old cookie | Expired session must not be restored. |
| Logout | POST logout with CSRF | Old session/context no longer usable. |
| Session store outage | POST login when store cannot write | Do not falsely report success; handle error safely. |
| Proxy / cookie flags | Browser HTTPS/SameSite/cross-origin | Cookies sent/received properly, no cross-origin leak. |
| Async/streaming login | Start writing body then save | Must catch wrong commit timing. |
| Concurrent requests | Request B runs right at login time | Does not see pre-save state; no login race. |
| Cross-user sessions | Alice and Bob in two sessions | Contexts never mix across thread pool or shared mutable objects. |
| Role revoked after login | Send old cookie | Authorization/freshness per policy; do not assume role stays valid. |
| Built-in form login | Login via standard filter | Framework runs appropriate success flow; no arbitrary double-save. |

Good tests check **both server-side repository state** and **client-side cookies and HTTP statuses**. Some HTTP clients auto-follow redirects, showing only the final status and hiding when `Set-Cookie` was emitted; when debugging, disable auto-follow or inspect every response individually.

## 16. Symptom-Based Debugging

| Symptom | Suggested Cause | How to Investigate |
| --- | --- | --- |
| POST login returns 200, yet next GET is 401 | Missing `saveContext`, or cookie/session not stored. | Check controller saved before return, right repo, session key, and cookies. |
| POST login never enters controller, returns 403 | CSRF filter blocked before MVC. | Check CSRF token, cookie/session, and origin policy. |
| Login handler runs, yet response lacks JSESSIONID | Null/non-creating repo, early response commit, stateless policy, or stripped cookie. | Check `SessionCreationPolicy`, repo implementation, `response.isCommitted()`, and safe headers. |
| Session ID present, yet next request is anonymous | Session lacks `SPRING_SECURITY_CONTEXT`, different repo, or different node session store. | Inspect server session attribute, chain/repository, and cluster. |
| First request right, second request wrong user | Shared static context, mutated shared object, uncleaned thread pool, or misbound cookie. | Use fresh contexts, default ThreadLocal, inspect session ID per client. |
| Login lost after redirect | `sendRedirect` before `saveContext` or response-commit race. | Fix ordering, inspect 302 `Set-Cookie` separately. |
| Login broke after Spring Security 5 → 6 upgrade | Code relied on `SecurityContextPersistenceFilter` auto-save. | Add explicit repository save in custom auth. |
| Logout returns 204, yet old cookie still grants access | Only cleared ThreadLocal without invalidating session/repository. | Use LogoutFilter/handlers, test old cookie on another request. |
| New login keeps attacker-known old session ID | Custom login skipped SessionAuthenticationStrategy. | Call fixation protection before save; test ID change. |
| Different role/authority on request B | Custom auth hit wrong provider/user store or stale Session/Cache. | Check principal after authenticate and after reload, plus revalidation policy. |
| Async response sent before save | Saved inside future/callback after writer flush. | Save on request thread pre-commit, propagate context separately. |
| Multiple chains include Null repo | Different filter chain between login and endpoint. | Log matcher/chain, repo, and session policy per request. |

### Production Incident Checklist

1. Is there evidence `AuthenticationManager.authenticate` actually returned a valid result? Never log passwords/hashes.
2. Does any custom controller/filter call `setContext` without `saveContext`?
3. What repo/strategy is active; is it Null or RequestAttribute-only?
4. Was `saveContext` called **before** body/redirect/flush?
5. Had the response already committed before save; was `Set-Cookie` present on the original response?
6. Did the client send the Cookie on the next request; are path/domain/SameSite/Secure/CORS valid?
7. Does the session store hold the context with the right TTL and key; which node handled the request?
8. Is there a `SessionAuthenticationStrategy` to rotate the session ID, handle CSRF, and manage concurrent sessions?
9. Which `SecurityFilterChain` ran for each URL; are there overlapping matchers or double-registered custom filters?
10. Do logs contain raw passwords, `Set-Cookie`, JWTs, or full `Authentication`? If so, redact/reduce them.

## 17. Self-Check Exercises with Answers

**Question 1.** A controller calls `AuthenticationManager.authenticate(...)` successfully, then `SecurityContextHolder.setContext(context)`, without calling `saveContext`. On the second request, is the user guaranteed to stay logged in?

**Answer:** No. In Spring Security 6's explicit-save configuration, the holder only retains the current execution's context; the next request needs a repository/session and cookie. You must call `SecurityContextRepository.saveContext(context, request, response)` before commit.

**Question 2.** Why does `SecurityContextHolder.getContext().getAuthentication()` returning Alice right after login not prove persistence?

**Answer:** Because code is still running in the current thread/request where the context was just placed. After filter cleanup, ThreadLocal loses its association; the next request must reload from the repository.

**Question 3.** When should `response.sendRedirect("/app")` execute?

**Answer:** After the manager has verified credentials, the session authentication strategy has run, the new context has been set, and the repository has saved it. A redirect can commit headers, so never save after it.

**Question 4.** If an app uses `NullSecurityContextRepository` in a stateful login and still calls `saveContext`, will it get a session?

**Answer:** No. The Null repository does not persist. You must choose a repository with session persistence or design a proper token-only stateless flow.

**Question 5.** Does `RequestAttributeSecurityContextRepository` help browsers keep login on a new HTTP request?

**Answer:** No. It keeps context within the scope of one request, helpful across dispatches, and does not replace an HttpSession repo or tokens.

**Question 6.** Why is replacing `MODE_THREADLOCAL` with `MODE_GLOBAL` wrong when wanting login to persist across requests?

**Answer:** GLOBAL shares one context across the JVM for all threads, easily leaking identities between users. Persistence across requests belongs to `SecurityContextRepository`/sessions.

**Question 7.** A custom login validates the CSRF token yet does not rotate the session ID. What is the risk?

**Answer:** Session fixation. If an attacker controls a pre-login session ID, the victim's login elevates that session. Custom login must invoke session fixation protection per policy.

**Question 8.** Session attribute `"username"="alice"` is present; why does `GET /api/me` still return 401?

**Answer:** Spring Security does not automatically convert arbitrary attributes into a `SecurityContext`. You must save a proper context via `SecurityContextRepository`.

**Question 9.** A login request returns 200 and the HTTP response includes a cookie, yet a protected API on another node still returns 401. Is it definitely a bug where the controller forgot to save?

**Answer:** No. Check shared session store, cookie domain/path, session ID, the other chain's repository, node routing, and TTL. Having a cookie does not prove the context exists where request B reads.

**Question 10.** A custom POST login app returns 403 before the manager is ever invoked. Is it a wrong password?

**Answer:** Not necessarily; CSRF may reject the POST before the controller, or an authorization filter/matcher blocked it. Inspect status, filter ordering, and CSRF tokens.

**Question 11.** After `saveContext` succeeds, can you skip role/resource checks on subsequent requests?

**Answer:** No. Authentication persistence only preserves verified identity/authorities; authorization must still check each endpoint, tenant, and object, along with freshness policies when roles change.

**Question 12.** Why is a custom filter with an `AuthenticationSuccessHandler` prone to timing bugs?

**Answer:** A success handler can redirect/commit the response. If the filter invokes the handler before `saveContext`, cookies/sessions are not guaranteed. With built-in filters, check superclass logic to avoid double-saving.

## 18. Implementation Checklist and Scope Limitations

**Custom login:**

- Inputs validated/rate-limited, passwords sent over TLS, credentials never printed/logged.
- Manager/provider verifies credentials, account status, and trusted tenant/authority sources.
- Only use `UsernamePasswordAuthenticationToken.unauthenticated` when receiving requests.
- Session fixation and CSRF handled in the custom flow without expecting beans to run magically.
- New `SecurityContext` contains verified Authentication.
- `SecurityContextHolderStrategy.setContext` applied for the active request.
- **`SecurityContextRepository.saveContext` runs explicitly, using the chain's exact repo, before response commit.**
- Response includes minimal data; never serialize `UserDetails.getPassword()`.
- Client stores/sends session cookie properly per app HTTPS/SameSite/Secure/HttpOnly rules.
- Subsequent request confirms context loads and authorization works normally.
- Logout/revocation clears state per repository/session/token lifecycle.

**Limitations:**

- In Spring Security 6, built-in login filters and custom authentication differ in responsibilities; inspect the corresponding source/filter contracts.
- The demo uses in-memory users and local sessions, without simulating password rotation, databases, Spring Session Redis, or JWTs.
- `HttpSessionSecurityContextRepository` is used standalone intentionally to show stateful persistence; production may retain the default `DelegatingSecurityContextRepository` for request/error dispatches.
- Spring Security 7.x may change APIs/configurations; code snippets here target Spring Security 6.x / Boot 3.x and do not replace version-specific migration guidance.
- MockMvc tests framework logic, not real browser `Set-Cookie` behavior across proxies/containers.
- Never let the reminder "save before response" become an excuse to self-issue authentication from client data. **Authentication is a prerequisite before saving.**

## 19. Official Documentation

- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): custom controllers/filters needing `SecurityContextRepository.saveContext`; `SecurityContextHolderFilter` and `requireExplicitSave`; session policies, strategies, and fixation.
- [Spring Security 6.5 — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html): context repositories, response-commit race, `HttpSession`/`RequestAttribute`/`Null`/`DelegatingSecurityContextRepository`.
- [Spring Security 6.5 — Session Management Migrations](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html): moving from auto-save to explicit save in Spring Security 6.
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `SecurityContextHolder`, and the principle of creating a new context.
- [Spring Security 6.5 — SecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html): `loadDeferredContext`, `saveContext`, and `containsContext`.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): verifying username/password via UserDetailsService and PasswordEncoder.
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): cookie-based requests, CSRF token lifecycle, and login/logout.
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc.html): MockMvc security integration support and CSRF request post-processors.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session fixation, cookie flags, TTL, invalidation, and protecting session IDs.

**Conclusion:** In Spring Security Servlet custom login, **`AuthenticationManager.authenticate(...)` verifies**, **`SecurityContextHolder.setContext(...)` lets the current request see the user**, and **`SecurityContextRepository.saveContext(...)` is what preserves context across requests when session persistence is chosen**. Always save after authentication and the session strategy finish, **before `sendRedirect`, `sendError`, flushing, or returning a body that triggers commit**. Verify using a second request carrying the cookie rather than only checking status 200 on the login request; while keeping CSRF/session fixation, authorization, and logout lifecycles intact.