# Applying SessionAuthenticationStrategy in a Custom JSON Login Flow

## Goals and Context

Suppose a **Spring Boot Servlet** application exposes the `POST /api/login` endpoint accepting JSON with `username` and `password`. When a user logs in successfully, the browser sends the session cookie on subsequent requests, and the server recognizes the logged-in user. To implement this flow safely with Spring Security, calling `AuthenticationManager.authenticate(...)` alone is **not enough**.

After this lesson, you will be able to:

1. Explain the role of **SessionAuthenticationStrategy**, when to call it, and how it differs from `AuthenticationManager` and `SecurityContextRepository`.
2. Proactively apply **session fixation** protection upon successful authentication in a controller or JSON filter you write.
3. Understand why concurrent session limits and CSRF token rotation also need to be addressed in a custom flow.
4. Write and test a **Java 17+ / Spring Boot 3.x / Spring Security 6.x** example that persists authentication via `HttpSession`, with CSRF and logout.
5. Spot mistakes such as saving context before checking the session strategy, only setting `SecurityContextHolder` while forgetting to save, or expecting the session strategy to run automatically.

## 1. Problems That Arise When Building Custom JSON Login

A minimal JSON login flow is often written like this:

~~~java
// INCOMPLETE illustrative snippet, not a standalone endpoint.
Authentication authentication = authenticationManager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(username, password)
);
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
~~~

This snippet can verify the password correctly and establish identity **within the current request**, yet it misses two groups of responsibilities:

- **Handling session policy when a new login session is established:** rotating the session ID against **session fixation**, checking concurrent session counts, registering the session, invalidating old CSRF tokens, etc. This is where **SessionAuthenticationStrategy** comes in.
- **Saving authentication state for subsequent requests:** you must call `SecurityContextRepository.saveContext(...)` if you want to restore `Authentication` from the session. `SecurityContextHolder` normally only holds the context for the current request thread.

In Spring Security 6, `SecurityContextHolderFilter` typically **reads** the context from the repository; it does not automatically persist every change you make. `SessionManagementFilter` is also **no longer a default filter** that detects a newly authenticated request and invokes the session strategy. Therefore, with a custom JSON mechanism, **your authentication mechanism must explicitly run the required steps**.

Responsibility comparison:

| Component | What does it do? | What does it NOT do automatically? |
| --- | --- | --- |
| `AuthenticationManager` | Verifies credentials and returns an authenticated `Authentication` or throws `AuthenticationException` | Does not guarantee session ID rotation or saving context for a controller |
| `SessionAuthenticationStrategy` | Runs session-related rules **right after authentication succeeds** | Does not verify passwords and does not implicitly save `SecurityContext` |
| `SecurityContextHolder` | Lets code in the current request access `Authentication` | Not a cross-request state store |
| `SecurityContextRepository` | Saves/loads `SecurityContext` across requests, e.g., from `HttpSession` | Does not decide whether to accept a new login session under concurrency policy |
| `SessionCreationPolicy` | Guides Spring Security on creating/using sessions | Does not replace calling `SessionAuthenticationStrategy.onAuthentication(...)` |

**Rule:** If login creates a long-lived trusted session, treat `authenticate`, **session strategy**, **set context**, and **save context** as distinct steps running in the exact right order.

## 2. The SessionAuthenticationStrategy Contract

The main interface resides in package:

`org.springframework.security.web.authentication.session.SessionAuthenticationStrategy`

Method:

~~~java
void onAuthentication(
    Authentication authentication,
    HttpServletRequest request,
    HttpServletResponse response
) throws SessionAuthenticationException;
~~~

In a real application:

- `authentication` must be a **successfully authenticated** result, such as from `AuthenticationManager.authenticate(...)`; do not pass an unauthenticated username/password token.
- `request` and `response` are the servlet pair of the **actual login request**. The strategy may need `HttpSession` or change the session ID/cookie.
- Call **once per successful login**, after credential verification and **before saving the context or returning a success response**.
- `SessionAuthenticationException` indicates the new session is not accepted, such as exceeding the session limit. In that case **do not save the new `Authentication`**, and do not return a "login succeeded" response. Map the exception to an appropriate API response while avoiding leaking internal details.

The strategy is not something to invoke on every authenticated request. If called again on every `GET /api/me`, the session ID could rotate continuously, and session counting/registration logic would execute at the wrong time.

### Success Sequence

~~~text
POST /api/login + JSON credentials + valid CSRF token
    |
    +--> SecurityFilterChain / CsrfFilter checks request
    |
    +--> Controller or custom authentication filter
           |
           +--> AuthenticationManager.authenticate(...)
           |      |
           |      +-- INVALID --> AuthenticationException --> 401, do not save new context
           |      |
           |      +-- VALID --> Authenticated Authentication
           |
           +--> SessionAuthenticationStrategy.onAuthentication(...)
           |      |
           |      +-- REJECTED --> SessionAuthenticationException --> do not save new context
           |      |
           |      +-- ACCEPTED --> apply session rules
           |
           +--> create new SecurityContext
           +--> set Authentication into SecurityContext
           +--> SecurityContextHolder.setContext(context)
           +--> SecurityContextRepository.saveContext(context, request, response)
           +--> return success JSON, client keeps session cookie
~~~

Using a **new context** after successful authentication avoids mutating an old context loaded from a prior session directly. Especially when a session already exists, attaching a new principal to a shared context before checking session limits could accidentally persist the wrong identity if the request fails.

## 3. Important SessionAuthenticationStrategy Implementations

### 3.1. Session Fixation Protection

**Session fixation** occurs when an attacker knows or controls a session ID before the victim logs in, and exploits the server continuing to use that same ID after authentication.

With modern Servlet containers, the standard approach is:

~~~java
SessionAuthenticationStrategy fixation =
    new ChangeSessionIdAuthenticationStrategy();
~~~

Upon successful login, the strategy uses the container's **`HttpServletRequest.changeSessionId()`** capability to replace the session's ID **if a valid session already exists**. Session attributes remain intact when the ID changes; the session cookie must be received by the client and sent on subsequent requests.

Conditions to remember:

- If **no HttpSession existed** before login, there may be no old ID to rotate. The repository may create a new session when saving the context. Therefore, do not assert a rigid rule that "every login request must emit two session IDs".
- If a pre-login session cookie exists, compare the session ID before/after authentication: the ID must have changed when the strategy actually protects an existing session.
- Do not confuse `changeSessionId` with `invalidate()`: manual invalidation can wipe session data and the CSRF token in unintended ways.
- `SessionFixationProtectionStrategy` is an alternative that can create a new session/migrate attributes. `ChangeSessionIdAuthenticationStrategy` suits Servlet 3.1+; Spring Boot 3.x uses modern Jakarta Servlet.

**Note:** The DSL configuration `sessionManagement(session -> session.sessionFixation(...))` is normally integrated for standard authentication filters managed by Spring Security; a custom-written JSON controller is not guaranteed to run that action automatically. The controller must invoke the strategy configured for it.

### 3.2. Controlling Concurrent Login Sessions

Three classes typically work together:

- `ConcurrentSessionControlAuthenticationStrategy`: checks the principal's session quota based on `SessionRegistry`; can reject the new session or mark an old session as expired.
- `ChangeSessionIdAuthenticationStrategy` or `SessionFixationProtectionStrategy`: protects the session ID once authentication is permitted.
- `RegisterSessionAuthenticationStrategy`: records the new session in `SessionRegistry` after the final ID is established.

The proper order inside **CompositeSessionAuthenticationStrategy** is:

~~~text
[Check session limit] -> [Session fixation protection] -> [Register session]
~~~

Reason: if rejected for exceeding the session count, do not rotate/create a session only to reject afterward. When registering, register the ID **after** fixation protection.

To implement session limits completely, you also need session destruction/expiration event handling (typically `HttpSessionEventPublisher`), appropriate filters to handle sessions marked expired, and a session/registry sharing mechanism if the app has multiple instances. **Simply adding a strategy to a controller does not complete full concurrent session management.**

### 3.3. CSRF When Login Is Cookie/Session-Based

JSON **does not** automatically eliminate CSRF risk. If the browser sends `JSESSIONID` automatically, state-changing requests must still be protected according to the threat model.

`CsrfAuthenticationStrategy` uses `CsrfTokenRepository` to **clear the old CSRF token upon successful authentication**. After login, the client fetches a new CSRF token before the next POST/PUT/PATCH/DELETE operation. This strategy differs from `CsrfFilter`, which validates the token on **incoming requests**.

~~~java
CsrfTokenRepository tokens = new HttpSessionCsrfTokenRepository();
SessionAuthenticationStrategy csrfRotation =
    new CsrfAuthenticationStrategy(tokens);
~~~

If using this strategy in custom login, **`CsrfFilter` and `CsrfAuthenticationStrategy` must share the exact same `CsrfTokenRepository`**. Do not disable CSRF app-wide just to make a JSON login POST succeed.

### 3.4. Chaining Strategies in Order

`CompositeSessionAuthenticationStrategy` invokes delegates sequentially; if one step throws `SessionAuthenticationException`, subsequent steps do not run.

A minimal example for cookie login without concurrency limits:

~~~java
SessionAuthenticationStrategy strategy =
    new CompositeSessionAuthenticationStrategy(List.of(
        new ChangeSessionIdAuthenticationStrategy(),
        new CsrfAuthenticationStrategy(csrfTokenRepository)
    ));
~~~

The complete example below uses this exact configuration. For concurrent session limits, add the corresponding strategies in the order from section 3.2, along with the matching registry and filter infrastructure.

## 4. Java 17+ Example: JSON Login with Session Fixation Protection and CSRF

**Environment:** a **Spring Boot 3.5.x / Spring Security 6.5.x** project, Java 17+, **Servlet** stack. Create the project via Spring Initializr with the two starters `Spring Web` and `Spring Security`. If using Gradle, required dependencies are:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Place the Java file at path:

`src/main/java/com/example/jsonlogin/JsonLoginApplication.java`

~~~java
package com.example.jsonlogin;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationException;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class JsonLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(JsonLoginApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("demo")
                .password(encoder.encode("change-me"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
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
                .requestMatchers("/csrf", "/api/login").permitAll()
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
            .requestCache(cache -> cache.disable())
            .formLogin(form -> form.disable())
            .httpBasic(basic -> basic.disable())
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint((request, response, exception) ->
                    response.sendError(HttpServletResponse.SC_UNAUTHORIZED))
            )
            .logout(logout -> logout
                .logoutUrl("/api/logout")
                .logoutSuccessHandler((request, response, authentication) ->
                    response.setStatus(HttpServletResponse.SC_NO_CONTENT))
            );

        return http.build();
    }

    public record LoginRequest(String username, String password) {}
    public record LoginResponse(String username) {}
    public record MeResponse(String username) {}
    public record ErrorResponse(String error) {}

    @RestController
    public static class Api {
        private final AuthenticationManager authenticationManager;
        private final SessionAuthenticationStrategy sessionStrategy;
        private final SecurityContextRepository securityContextRepository;

        public Api(AuthenticationManager authenticationManager,
                   SessionAuthenticationStrategy sessionStrategy,
                   SecurityContextRepository securityContextRepository) {
            this.authenticationManager = authenticationManager;
            this.sessionStrategy = sessionStrategy;
            this.securityContextRepository = securityContextRepository;
        }

        @GetMapping("/csrf")
        public CsrfToken csrf(CsrfToken token) {
            return token;
        }

        @PostMapping("/api/login")
        public ResponseEntity<?> login(@RequestBody LoginRequest body,
                                       HttpServletRequest request,
                                       HttpServletResponse response) {
            try {
                Authentication authentication = authenticationManager.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                        body.username(), body.password()
                    )
                );

                // Run only after credentials have been verified.
                sessionStrategy.onAuthentication(authentication, request, response);

                SecurityContext context = SecurityContextHolder.createEmptyContext();
                context.setAuthentication(authentication);
                SecurityContextHolder.setContext(context);

                // Required to restore login on subsequent requests.
                securityContextRepository.saveContext(context, request, response);

                return ResponseEntity.ok(new LoginResponse(authentication.getName()));
            } catch (SessionAuthenticationException ex) {
                SecurityContextHolder.clearContext();
                return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .body(new ErrorResponse("session_rejected"));
            } catch (AuthenticationException ex) {
                SecurityContextHolder.clearContext();
                return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .body(new ErrorResponse("invalid_credentials"));
            }
        }

        @GetMapping("/api/me")
        public MeResponse me(Authentication authentication) {
            return new MeResponse(authentication.getName());
        }
    }
}
~~~

### 4.1. Why Does the Example Declare These Beans?

**`AuthenticationManager` and `DaoAuthenticationProvider`:** receive username/password from JSON login and use `UserDetailsService` and `PasswordEncoder` to authenticate. `InMemoryUserDetailsManager` with account `demo/change-me` is only to run the lesson. This is not a production user store.

**`HttpSessionSecurityContextRepository`:** is the repository used **both when SecurityFilterChain loads the context and when the controller saves the context**. If you use repository A to save while the filter reads from repository B, login can return 200 yet the next request stays anonymous.

**`SessionAuthenticationStrategy`:** a composite that runs fixation protection and then clears the old CSRF token. The controller **must call `onAuthentication` directly**; the bean existing by itself does not mean the controller invokes it automatically.

**`SessionCreationPolicy.IF_REQUIRED`:** suits cookie-based session login. Do not use `STATELESS` for this example, because it alters the policy for restoring `SecurityContext` via `HttpSession`.

**`CsrfTokenRepository`:** stays consistent between request verification and post-authentication CSRF token rotation. The GET `/csrf` endpoint returns the token for the client to include in the login POST header. The token is stored server-side in the session and tied to the same browser cookie.

**`formLogin(...disable())` and `httpBasic(...disable())`:** the example focuses on a single application-owned JSON endpoint. Other mechanisms can be enabled in real systems, but each mechanism's distinct policy must be kept clear.

**`requestCache(...disable())`:** avoids saving protected request URLs for post-login redirection; the example API returns 401/JSON and decides subsequent requests itself. This is an API choice, not a strict requirement of `SessionAuthenticationStrategy`.

**`logoutUrl("/api/logout")`:** uses Spring Security's logout support rather than just `SecurityContextHolder.clearContext()`. Default logout handles clearing the context and invalidating the session; logout POST still requires a valid CSRF token.

**`SecurityContextHolder`:** uses the static API in this small example for readability. In applications with custom holder strategies or multiple application contexts, you can inject `SecurityContextHolderStrategy` and use it consistently.

### 4.2. Running the Example

In the Spring Boot project directory containing `build.gradle`, run:

~~~bash
./gradlew bootRun
~~~

On Windows, use `.\gradlew.bat bootRun`; if the project was created with Maven, use `./mvnw spring-boot:run`. This Java file needs the Spring Boot/Spring Security classpath managed by the build tool, so **do not** run `javac JsonLoginApplication.java` standalone.

The example listens on `http://localhost:8080` by default. The commands below use **Bash + curl + jq**; on Windows you can use Git Bash/WSL, or use `curl.exe` and parse the JSON token with PowerShell.

**Step 1: Fetch the CSRF token and save the cookie before logging in.**

~~~bash
csrf=$(curl -sS -c cookies.txt http://localhost:8080/csrf | jq -r .token)
printf 'CSRF token loaded: %s\n' "$([ -n "$csrf" ] && echo yes || echo no)"
# CSRF token loaded: yes
~~~

`GET /csrf` accesses the token, causing the repository to create or read the token and potentially create an HttpSession; `cookies.txt` holds `JSESSIONID`. Never print tokens/credentials into production logs.

**Step 2: POST JSON login with the same cookie and CSRF token.**

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-TOKEN: $csrf" \
  --data '{"username":"demo","password":"change-me"}' \
  http://localhost:8080/api/login
~~~

The expected result is **HTTP 200** and JSON body:

~~~json
{"username":"demo"}
~~~

If a valid pre-login session ID existed, `ChangeSessionIdAuthenticationStrategy` rotates the ID upon successful login. Depending on container and cookie policy, the response may emit `Set-Cookie: JSESSIONID=...`. With curl, `-c cookies.txt` saves the updated cookie.

**Step 3: Verify the context is restored on the next request.**

~~~bash
curl -sS -b cookies.txt http://localhost:8080/api/me
# {"username":"demo"}
~~~

`/api/me` receives no username/password and does not call `authenticate` again. Spring Security loads the saved context from the session based on the cookie.

**Step 4: Without sending the cookie, no login is restored.**

~~~bash
curl -i http://localhost:8080/api/me
# HTTP/1.1 401 Unauthorized (status line excerpt)
~~~

That is the result of the configured entry point: the request lacks a valid identity.

**Step 5: Fetch a new CSRF token, then log out.**

~~~bash
csrf=$(curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/csrf | jq -r .token)

curl -i -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $csrf" \
  -X POST http://localhost:8080/api/logout
# HTTP/1.1 204 No Content (status line excerpt)

curl -i -b cookies.txt http://localhost:8080/api/me
# HTTP/1.1 401 Unauthorized (status line excerpt)
~~~

After login, the pre-login CSRF token was cleared by `CsrfAuthenticationStrategy`, so the client must fetch a new token before subsequent state-changing requests. On logout, the session is invalidated; the old cookie no longer supplies a valid Authentication.

### 4.3. Failure Cases to Distinguish

| Case | Expected response | What to verify |
| --- | --- | --- |
| Login POST **without CSRF token** | **403**, request blocked before controller | CSRF protection is working |
| Login POST with CSRF token but wrong password | **401** with `invalid_credentials` | `onAuthentication` did not run; no new context saved |
| Successful login POST | **200**, context and session cookie created/saved | Strategy ran before `saveContext` |
| Login POST rejected by strategy (when session limit is configured) | **401** with `session_rejected` in the example | No new login session created/saved |
| GET /api/me with valid session cookie | **200** | Context loaded from `HttpSession` |
| GET /api/me without cookie | **401** | No authenticated context |
| Logout POST with cookie but missing/wrong CSRF | **403** | CSRF protects logout as well |
| Valid logout POST | **204** | Session and context invalidated |

The HTTP status code for session policy errors is an API design choice; the example uses **401** for simplicity. Real APIs may use different status codes and error bodies per client contract. Distinguish credential failures from session-limit failures in internal logs, but never return details that help enumerate accounts.

## 5. Extension: Limiting to One Session per User

If only one active login session is allowed, you can build a stronger composite. The snippet below **only illustrates how to compose strategies**, not a complete application configuration:

~~~java
// Configuration component example; requires SessionRegistry and
// corresponding lifecycle/concurrency management infrastructure.
ConcurrentSessionControlAuthenticationStrategy concurrency =
    new ConcurrentSessionControlAuthenticationStrategy(sessionRegistry);
concurrency.setMaximumSessions(1);
concurrency.setExceptionIfMaximumExceeded(true);

SessionAuthenticationStrategy strategy =
    new CompositeSessionAuthenticationStrategy(List.of(
        concurrency,
        new ChangeSessionIdAuthenticationStrategy(),
        new RegisterSessionAuthenticationStrategy(sessionRegistry),
        new CsrfAuthenticationStrategy(csrfTokenRepository)
    ));
~~~

To use this, you also need to import `ConcurrentSessionControlAuthenticationStrategy` and `RegisterSessionAuthenticationStrategy` from `org.springframework.security.web.authentication.session`, along with a properly configured `SessionRegistry`. Typically `SessionRegistryImpl` is paired with `HttpSessionEventPublisher` to update when sessions expire/destroy; when using an evict-oldest-session policy, configure a filter that recognizes sessions marked expired. With multiple instances, consider session/registry synchronization and `Spring Session` or equivalent infrastructure.

If using a custom `UserDetails` as the principal for an in-memory session registry, implement `equals/hashCode` consistently so the same user is recognized properly. Do not assume `.sessionManagement(s -> s.maximumSessions(1))` suffices for a **custom-written JSON controller** unless you invoke the composite strategy properly; standard mechanisms and custom controllers have different authentication lifecycles.

**Execution order is critical:** `concurrency` can reject upfront; only when accepted do you rotate the ID, register the session, clear the old CSRF token, and then create and save the context.

## 6. If Authenticating with a Custom Filter Instead of a REST Controller

You can write your own filter that reads JSON from the request:

- If extending `AbstractAuthenticationProcessingFilter`, call `setSessionAuthenticationStrategy(...)` so the filter invokes the strategy after `attemptAuthentication` succeeds; also configure `setSecurityContextRepository(...)` to save the context on success. Define success/failure handlers returning JSON instead of redirecting.
- If writing a standalone filter directly from `OncePerRequestFilter`, you must coordinate every step yourself: read credentials, authenticate, invoke the strategy after success, set/save context, handle exceptions, return status, and terminate/continue the filter chain properly.
- Do not manually add `SessionManagementFilter` just to compensate for a missing call. In Spring Security 6, the recommended path is for the authentication mechanism to actively call the strategy; forcing the legacy filter can cause double execution or confusing behavior.

Also remember **the CSRF filter runs before the login endpoint**, and a custom login endpoint must match the right `SecurityFilterChain`. If the app has multiple chains, verify each chain's security matcher; a `permitAll()` rule does not guarantee the request flows through the chain you intended.

## 7. Session Policy, Context Persistence, and Real-World Security

| `SessionCreationPolicy` | Impact on cookie-based JSON login |
| --- | --- |
| `ALWAYS` | Spring Security proactively creates sessions; usually unnecessary for a JSON API |
| `IF_REQUIRED` | Allows creating a session when saving context; fits the example |
| `NEVER` | Spring Security does not proactively create a session but can use an existing one; hard to guarantee login creates a session when none exists |
| `STATELESS` | Spring Security does not use sessions to restore SecurityContext; incompatible with "log in once, use JSESSIONID on subsequent requests" |

`SessionAuthenticationStrategy` does not turn a stateless API into a session-based API. Choose either stateful or stateless first, then configure policy, repository, and strategy for **the same model**.

Additional controls for real systems:

- **HTTPS/TLS and cookies:** transmit credentials and session cookies only over TLS; configure `Secure`, `HttpOnly`, `SameSite`, domain/path, and cookie lifetime per client and threat model. Never expose session IDs/CSRF tokens in URLs or logs.
- **Repeated failed logins:** rate limiting, brute-force protection, and error messages that do not disclose whether a user exists. Use a strong `PasswordEncoder`; never embed real accounts in source code.
- **Logout, revocation, timeout:** distinguish clearing the request's `SecurityContextHolder` from invalidating the session. Handle session expiration, invalidation, session registry, and synchronization if deployed in a cluster.
- **CSRF:** browser-cookie-based requests must be evaluated for CSRF risk even when the request body is JSON. Clients must fetch a fresh CSRF token after login/logout when `CsrfAuthenticationStrategy` is active.
- **Invoke `SessionAuthenticationStrategy` at the right moment:** if MFA is present, treat the login session as fully established only when required steps have passed; do not mark a session complete too early.
- **Re-logging in on the same browser:** an old `Authentication` may already sit in the session. Do not mutate the old context directly before authenticating and being accepted by the strategy.
- **Error observability:** log error category, outcome, correlation ID, and session lifecycle using anonymized data; never log passwords, raw CSRF tokens, or `JSESSIONID`.

## 8. Common Mistakes

**Mistake 1 — Only setting Authentication in SecurityContextHolder.** Login request returns 200, yet a subsequent GET receives 401. Usually caused by forgetting `SecurityContextRepository.saveContext(...)` or configuring the filter to read from a different repository.

**Mistake 2 — Calling the strategy before checking the password.** This can rotate IDs/create sessions for an untrusted request. Obtain a successful `Authentication` first, then run the strategy.

**Mistake 3 — Saving context first and calling the strategy afterward.** If session limits reject the login, you risk having persisted an Authentication that should not have been allowed. Call the strategy before setting/saving the new context.

**Mistake 4 — Only configuring `sessionFixation().changeSessionId()` while the custom controller never invokes the strategy.** DSL configuration supports framework filters, not automatic injection into a controller you wrote.

**Mistake 5 — Calling `request.getSession().invalidate()` yourself after login without understanding the impact.** This can destroy the CSRF token, saved requests, or needed session data. Use the fixation strategy provided by Spring Security.

**Mistake 6 — Using `STATELESS` while expecting session cookies to restore login.** These two decisions contradict the goal of the example. Inspect the actual session policy and repository.

**Mistake 7 — Using `NullAuthenticatedSessionStrategy` and assuming fixation protection exists.** That strategy performs no action; use it only when you have a clear reason, such as a sessionless model.

**Mistake 8 — Calling `RegisterSessionAuthenticationStrategy` without pairing it with the registry/filter lifecycle.** The session registry can drift or fail to enforce eviction on expiration.

**Mistake 9 — Disabling CSRF so login POST is convenient.** Cookie-based JSON login still needs CSRF per the threat model. Obtain a valid token, and refresh it after login/logout.

**Mistake 10 — Treating `SessionAuthenticationException` as a password error.** Identify session and app policy errors separately; do not indicate login succeeded, yet do not turn it into a misleading authentication system failure.

## 9. Self-Check Exercises

1. **The user enters the right password, but the account has reached its session limit and policy rejects new sessions.** Which call do you place before `saveContext`?  
   **Answer:** `sessionAuthenticationStrategy.onAuthentication(authentication, request, response)`; if the strategy throws `SessionAuthenticationException`, do not save the new login context.

2. **The login controller returns 200, yet the next request sending `JSESSIONID` still receives 401.** First two things to check?  
   **Answer:** Was `saveContext(...)` called, and does `SecurityFilterChain` read from the same `SecurityContextRepository`?

3. **Why might the session ID not change on the initial login when no session existed beforehand?**  
   **Answer:** There is no old session ID to rotate. `ChangeSessionIdAuthenticationStrategy` acts on an existing session; the repository may create a new session when saving the context.

4. **Why is the order `ConcurrentSessionControlAuthenticationStrategy` -> fixation -> `RegisterSessionAuthenticationStrategy` important?**  
   **Answer:** Reject early before creating/modifying a session, then protect the ID, and register the final ID.

5. **Login POST carries JSON and the browser uses session cookies; can CSRF be disabled just because the request is JSON?**  
   **Answer:** No. Evaluate automatic cookie sending by the browser; usually you must keep CSRF and send the token in a header.

6. **After login, the client sends the old CSRF token and receives 403. Could this be expected behavior?**  
   **Answer:** Yes. `CsrfAuthenticationStrategy` clears the old token upon authentication; the client needs to call `GET /csrf` to receive a new token.

## Official Documentation

- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — SessionAuthenticationStrategy API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/SessionAuthenticationStrategy.html)
- [Spring Security — CompositeSessionAuthenticationStrategy API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/CompositeSessionAuthenticationStrategy.html)
- [Spring Security 6.5 — CSRF for Servlet Applications](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — SecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html)
