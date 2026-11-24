# SessionAuthenticationStrategy After Successful Authentication

In a Spring Security Servlet application, verifying username/password **is not the entire secure login process**. After `AuthenticationManager` returns a verified `Authentication`, the system may also need to **rotate the session ID** to defend against *session fixation*, **enforce concurrent session limits**, **register the session in a registry**, and **reset the CSRF token** when identity changes.

This is the job of the `SessionAuthenticationStrategy` contract. With Spring Security's built-in login filters, the corresponding strategy is normally triggered within the standard authentication flow. However, if a developer writes a **custom login filter** that simply calls `authenticate(...)` and returns 200, session protections can be skipped even when the password is checked properly.

This lesson belongs to the **Filter Integration** group of the *Spring Security - authentication* topic; the focus is **when and why to invoke `SessionAuthenticationStrategy.onAuthentication(...)` after successful authentication** in Spring Security 6.x, how to compose strategies, ordering with `SecurityContextRepository.saveContext(...)` and response commits, plus runnable Java 17+/Spring Boot 3.x examples and tests.

**Core rule:** For a *custom authentication mechanism* creating a stateful login session, let `AuthenticationManager`/provider verify credentials first; upon success, invoke the appropriate session strategy **exactly once**; only if accepted, create/set/save `SecurityContext`; finally invoke the success handler/redirect/write response. **Never call the strategy on failed requests, on every already-authenticated request, or a second time inside a success handler when the framework already invoked it.**

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the `SessionAuthenticationStrategy` contract and distinguish it from `AuthenticationManager`, `SecurityContextHolder`, `SecurityContextRepository`, and `SessionManagementFilter`.
2. State the authentication success sequence: `attemptAuthentication` → `SessionAuthenticationStrategy` → `successfulAuthentication` → context/save → success handler, inside `AbstractAuthenticationProcessingFilter`.
3. Understand the change from Spring Security 5 to 6: authentication mechanisms **invoke the strategy themselves**, rather than relying on `SessionManagementFilter` to detect authentication by default.
4. Choose `ChangeSessionIdAuthenticationStrategy`, `SessionFixationProtectionStrategy`, `ConcurrentSessionControlAuthenticationStrategy`, `RegisterSessionAuthenticationStrategy`, `CsrfAuthenticationStrategy`, or `NullAuthenticatedSessionStrategy` as needed.
5. Build a `CompositeSessionAuthenticationStrategy` with a **controlled order** and understand why, if one delegate throws `SessionAuthenticationException`, remaining delegates must not run.
6. Configure a custom filter extending `AbstractAuthenticationProcessingFilter` with `SessionAuthenticationStrategy` and `SecurityContextRepository`; avoid registering the filter twice.
7. Run Java 17+ and Spring Boot/MockMvc demos proving: session ID changes on successful login, wrong password does not elevate the session, CSRF is enforced, the session is persisted, and subsequent requests receive the right principal.
8. Recognize limitations: absent pre-login sessions, session cookies, multi-node clusters, registries, and stateless tokens cannot be "fixed" by a strategy alone.

## 2. One Interface Name, Multiple Session-Protection Responsibilities

`SessionAuthenticationStrategy` belongs to the package:

```java
org.springframework.security.web.authentication.session.SessionAuthenticationStrategy
```

Core Java contract:

```java
void onAuthentication(
        Authentication authentication,
        HttpServletRequest request,
        HttpServletResponse response)
        throws SessionAuthenticationException;
```

**Interpretation:** When a fresh authentication succeeds, the strategy is invoked with the trusted `Authentication` result and the current HTTP request/response to perform session-related actions. `SessionAuthenticationException` signals that proceeding with authentication on this session is unacceptable, e.g., session limit reached.

The method is NOT responsible for:

- Checking passwords, OTPs, or JWT signatures.
- Granting `ROLE_ADMIN`, building a principal from client input, or resolving tenants.
- Saving `Authentication` into `SecurityContext` for subsequent requests.
- Guaranteeing all sessions/JWTs across every server are revoked.
- Running on every `GET` request of an already logged-in user.
- Replacing `CsrfFilter`, session-cookie policies, or resource authorization.

### 2.1 Surrounding Components

| Component | Question it answers | Example |
| --- | --- | --- |
| `AuthenticationManager` / `AuthenticationProvider` | Are credentials/tokens valid, who is the principal, what authorities? | `DaoAuthenticationProvider`, `PasswordEncoder`. |
| **`SessionAuthenticationStrategy`** | Right after authentication succeeds, what session actions are needed? | Rotate session ID, limit concurrent sessions, CSRF token cleanup. |
| `SecurityContextHolderStrategy` | How is context bound to the current execution/thread? | `MODE_THREADLOCAL` default in Servlet. |
| `SecurityContextRepository` | Where is `SecurityContext` saved/loaded across HTTP requests? | `HttpSessionSecurityContextRepository`. |
| `AuthenticationSuccessHandler` | Which response/redirect to send upon success? | HTTP 204, redirect to original page. |
| `AuthenticationFailureHandler` | How to respond when credentials or session policy are rejected? | HTTP 401, generic message. |
| `SessionRegistry` | Which sessions are associated with a principal? | `SessionRegistryImpl` or distributed solution. |
| `ConcurrentSessionFilter` | Handles sessions marked expired on subsequent requests. | Blocks exceeded sessions when concurrency is configured. |

**Password authentication succeeding** does not mean **another session is allowed**: `ConcurrentSessionControlAuthenticationStrategy` can reject after the password is already verified, in which case the new session's `SecurityContext` must not be saved.

### 2.2 Do Not Confuse Different Types of "Sessions"

- **Servlet `HttpSession`**: server-side HTTP session, typically referenced by the browser via the `JSESSIONID` cookie. `SessionAuthenticationStrategy` mainly operates on this.
- **Security authentication state**: `Authentication` in `SecurityContext`, which may live inside `HttpSession` or be rebuilt from a bearer token on every request.
- **OAuth2/OIDC session/authorization grant**: has its own lifecycle at the IdP/authorization server and is not automatically governed by Servlet session strategies.
- **Spring Session distributed store**: replaces the backing store for `HttpSession`; it does not automatically make every `SessionRegistryImpl` cluster-wide.

## 3. Timing of onAuthentication in the Filter Chain

With a filter based on Spring Security 6.x's `AbstractAuthenticationProcessingFilter`, the baseline flow is:

```text
POST /api/login
    |
    v
Spring Security FilterChainProxy
    |
    +--> CsrfFilter (before login POST processing when CSRF is enabled)
    |
    v
Custom authentication filter / UsernamePasswordAuthenticationFilter
    |
    v
attemptAuthentication(request, response)
    |
    +--> Unauthenticated token from username/password
    +--> AuthenticationManager.authenticate(token)
    |
    +---- FAILURE ---> unsuccessfulAuthentication(...)
    |                    -> failure handler, DO NOT call success strategy
    |
    +---- INCOMPLETE (null) ---> end current step
    |
    +---- SUCCESS: verified Authentication
                              |
                              v
            sessionStrategy.onAuthentication(verified, req, resp)
                    |                     |
                    | success              +--> SessionAuthenticationException
                    v                              |
            successfulAuthentication(...)          v
                    |                       failure handler
                    +--> new context           DO NOT save authenticated context
                    +--> setContext
                    +--> SecurityContextRepository.saveContext(...)
                    +--> RememberMeServices.loginSuccess (if any)
                    +--> success event/handler
                    +--> status/body/redirect
```

**This order applies to subclasses adhering to `AbstractAuthenticationProcessingFilter`'s contract**; it does not mean Spring automatically invokes the strategy for arbitrary custom `OncePerRequestFilter`s. If you write your own password-handling filter, you must implement and test equivalent steps yourself.

### 3.1 Why Must the Strategy Run After Authentication?

Before authentication succeeds, client-sent username/password/roles are **untrusted data**. If you rotate session IDs, create registry entries, or issue sessions on every wrong-password request, attackers can flood session creation and cause resource exhaustion, or unnecessarily mutate a victim's session.

`SessionAuthenticationStrategy.onAuthentication` must receive a **provider-verified `Authentication`**, strictly after `AuthenticationManager.authenticate` succeeds. A session policy error must be treated as **login rejected**, not treated as a successful login with a "fix later" note.

### 3.2 Why Must the Strategy Run Before the Success Handler?

`AuthenticationSuccessHandler` may send a redirect, HTTP 200/204, flush a body, or start streaming. Those actions can **commit the response**. The session strategy may need to call `request.changeSessionId()`, create a session, invalidate the CSRF token, or attach session registry state before the response finalizes.

If the response is sent before the strategy runs, the browser may miss the new session ID cookie and the registry may record the stale ID. Complete all session steps before the success response.

### 3.3 Why Doesn't the Strategy Replace Saving SecurityContext?

Rotating the session ID only addresses **session fixation**; it does not write the newly verified authentication into `HttpSession`. With Spring Security 6's default explicit save, you need:

```java
Authentication verified = authenticationManager.authenticate(requested);

sessionAuthenticationStrategy.onAuthentication(
        verified, request, response);

SecurityContext context = strategy.createEmptyContext();
context.setAuthentication(verified);
strategy.setContext(context);

securityContextRepository.saveContext(
        context, request, response);

// Only after this point call sendRedirect/flush/return body.
```

This is an **integration pattern**, not a standalone Java class. Inside `AbstractAuthenticationProcessingFilter`, `successfulAuthentication` can save through the repository **if `setSecurityContextRepository(...)` was configured on the filter**; do not save a second time manually. If writing a controller yourself, you are responsible for calling save.

## 4. Spring Security 5 vs. 6: Do Not Rely on Default SessionManagementFilter

### 4.1 Legacy Mechanism

In a typical Spring Security 5 flow, `SessionManagementFilter` could compare the current `SecurityContextHolder` against `SecurityContextRepository` to detect whether a new authentication had occurred. When seeing a new auth not yet saved in the repository, it invoked `SessionAuthenticationStrategy`.

In return, that approach often had to **read `HttpSession` on every request** to check whether a new authentication had occurred, even when no login event took place.

### 4.2 Spring Security 6 Mechanism

Per Spring Security 6 documentation, by default **`SessionManagementFilter` is not added** to the chain to detect fresh logins. Instead, **each authentication mechanism invokes `SessionAuthenticationStrategy` itself when appropriate**. This avoids touching `HttpSession` just to poll for login events.

At the same time, `SecurityContextHolderFilter` in the default configuration primarily **loads** context rather than auto-saving every mutation; custom auth needing context across requests requires explicit save. These two changes are related yet **are not the same responsibility**:

- `SessionAuthenticationStrategy`: performs session tasks **when a new login succeeds**.
- `SecurityContextRepository.saveContext`: persists `SecurityContext` across requests.
- `SecurityContextHolderFilter`: loads context for the incoming request.
- `AuthenticationSuccessHandler`: finalizes the HTTP response.

### 4.3 What Happens When Upgrading Old Code?

A custom filter that merely does:

```java
Authentication result = manager.authenticate(untrustedToken);
SecurityContextHolder.getContext().setAuthentication(result);
chain.doFilter(request, response);
```

might previously have relied on another filter accidentally noticing the login, triggering the strategy, or saving the context. On default Spring Security 6, this pattern is insufficient to ensure session ID rotation, session limits, context persistence, or standard success responses.

**Fix:** Use `AbstractAuthenticationProcessingFilter` with explicit strategy/repository configuration; or when writing a `OncePerRequestFilter`/controller, invoke the strategy and save in the right order, followed by explicit success/failure responses.

**Do not** manually re-add `SessionManagementFilter` and `SecurityContextPersistenceFilter` just to recreate old side effects; those filters can cause duplicate handling, unnecessary session reads, or races if misconfigured.

### 4.4 Which DSL Configuration Is Still Not Enough?

Adding:

```java
http.sessionManagement(session -> session
        .sessionFixation(fixation -> fixation.changeSessionId()));
```

helps built-in login mechanisms configured via the DSL; **it does not guarantee a custom filter you built uses that strategy**. If you instantiate an `AbstractAuthenticationProcessingFilter` with `new`, pass/set `setSessionAuthenticationStrategy(...)` directly on that filter. Spring Security 6 does not rely on `SessionManagementFilter` by default to "compensate" for custom filters.

For certain `sessionManagement` DSL options tied to `SessionManagementFilter` such as `sessionAuthenticationStrategy(...)`, Spring Security 6 changed behavior and may reject legacy usage. Consult the docs for your exact version and prefer **configuring the strategy directly on the authentication mechanism**.

## 5. SessionAuthenticationStrategy Implementations and Each Class's Job

| Class | Job | When to choose |
| --- | --- | --- |
| `ChangeSessionIdAuthenticationStrategy` | Uses Servlet 3.1+ `HttpServletRequest.changeSessionId()` to rotate the existing session's ID against fixation. | Sensible default on modern Servlet containers for stateful login. |
| `SessionFixationProtectionStrategy` | Invalidates the old session, creates a new one, and optionally migrates attributes per config. | When specific migrate/newSession policy or older containers are required. |
| `ConcurrentSessionControlAuthenticationStrategy` | Checks active session count via `SessionRegistry` against configured limits. | Limiting concurrent logins with reject or expire-old policy. |
| `RegisterSessionAuthenticationStrategy` | Registers the succeeded session in `SessionRegistry`. | Typically paired with concurrent-session control. |
| `CsrfAuthenticationStrategy` | Clears/resets the stored CSRF token when the principal authenticates, avoiding keeping pre-login tokens across identity changes. | Browser cookie-session with CSRF protection. |
| `CompositeSessionAuthenticationStrategy` | Calls child strategies sequentially in order; stops on `SessionAuthenticationException`. | Combining concurrent check, fixation, registry, and CSRF. |
| `NullAuthenticatedSessionStrategy` | Makes no session changes. | Only when policy requires no session work, or stateless flows using other mechanisms. |

**Having the class on the classpath does not mean it is wired properly.** Declaring a `SessionAuthenticationStrategy` object or bean without attaching it to **the real login filter** has no effect. Conversely, invoking the same strategy **twice** can rotate the ID twice, create extra registry entries, or clear CSRF tokens unintentionally.

### 5.1 ChangeSessionIdAuthenticationStrategy

With Servlet 3.1+, `HttpServletRequest.changeSessionId()` asks the container to swap the ID of an **existing `HttpSession`** without creating a new session and manually copying every attribute.

```text
Before login:
  HttpSession id = S1
  may hold CSRF token, saved request, shopping cart...

Login/password verified:
  ChangeSessionIdAuthenticationStrategy.onAuthentication(...)

After rotation:
  Same logical session with new ID S2
  S1 is no longer accepted as the authenticated session identifier.
```

Do not assume the strategy creates a session out of thin air. If the login request had no session yet, `ChangeSessionIdAuthenticationStrategy` **has nothing to rotate when no ID existed**. `HttpSessionSecurityContextRepository` can create the session afterwards when saving the context, depending on session-creation config; thus login still persists a session even without a "pre-login session ID change" event.

### 5.2 SessionFixationProtectionStrategy: newSession and migrateSession

An alternative is invalidating the old session and creating a new one. That raises a question: **which pre-login session attributes should be kept?** Saved requests, CSRF tokens, shopping carts, or other state may be migrated per configuration. Blindly copying every attribute can preserve pre-auth data that should not carry over after login; wiping everything can break valid UX state.

- `changeSessionId`: changes the existing session's ID without manual attribute copying; typically the modern Servlet default.
- `newSession`: creates a relatively clean new session while retaining necessary framework state.
- `migrateSession`: migrates attributes from the old session to the new session per policy.
- `none`: disables session fixation protection; **not recommended** for browser session logins.

Do not manually call `request.getSession().invalidate()` followed by `getSession(true)` after authentication unless you fully understand lifecycle, registry, and cookie interactions: the framework already provides strategies and event handling for this.

### 5.3 ConcurrentSessionControlAuthenticationStrategy

Configured with a `SessionRegistry`, this strategy checks the principal's active sessions and decides:

- When `exceptionIfMaximumExceeded=true` and the limit is reached, throws `SessionAuthenticationException` to **reject the new login**.
- When configured in expire-session mode, marks excess old sessions as expired and lets the new login proceed; old sessions are handled on subsequent requests by the corresponding filter/mechanism.
- `maximumSessions=1` does not mean opening two tabs in the same browser counts as two sessions: if both share `JSESSIONID`, the server sees **one session**.
- `SessionRegistry` must be updated on session create/destroy; an in-memory registry in one JVM does not automatically synchronize across a cluster.

**Never call `RegisterSessionAuthenticationStrategy` before the concurrent check.** Wrong ordering can count the newly created session itself against the limit and cause unexpected behavior.

### 5.4 RegisterSessionAuthenticationStrategy

Once login is accepted and the final session ID is settled, this strategy records the mapping between principal and session ID in `SessionRegistry`. It does not **enforce** limits itself; pair it with `ConcurrentSessionControlAuthenticationStrategy` to enforce limits.

If registered **before** session ID rotation, the registry may retain the stale ID or depend on update events; the Javadoc-recommended composition order is **control → fixation → register**.

### 5.5 CsrfAuthenticationStrategy

An identity change is a trust boundary: pre-login CSRF tokens may need invalidation. `CsrfAuthenticationStrategy` works with `CsrfTokenRepository` to clear old tokens after authentication. It **does not replace `CsrfFilter` validating tokens on POST requests**; keep both components when browsers authenticate with session cookies.

With deferred CSRF tokens in Spring Security 6, token invalidation after login can require an SPA to fetch a **fresh** token before its next POST. Do not cache a pre-login token, reuse it forever after login, and mistake the 403 for a session registry bug.

## 6. CompositeSessionAuthenticationStrategy: Order Is Not Decorative

When fixation protection, session limits, and registry tracking are required, the standard order recommended by Spring Security Javadocs is:

```text
AuthenticationManager.authenticate(...) returns verified
                 |
                 v
ConcurrentSessionControlAuthenticationStrategy
   +-- checks max sessions; may REJECT login immediately
                 |
                 v
ChangeSessionIdAuthenticationStrategy
   +-- rotates session ID if pre-login HttpSession exists
                 |
                 v
RegisterSessionAuthenticationStrategy
   +-- records final ID and principal in SessionRegistry
                 |
                 v
CsrfAuthenticationStrategy
   +-- clears old CSRF token on identity change
                 |
                 v
SecurityContext created/set/saved, then success response
```

Example **configuration snippet** (not a standalone Java app):

```java
SessionRegistry registry = new SessionRegistryImpl();

ConcurrentSessionControlAuthenticationStrategy concurrent =
        new ConcurrentSessionControlAuthenticationStrategy(registry);
concurrent.setMaximumSessions(1);
concurrent.setExceptionIfMaximumExceeded(true);

SessionAuthenticationStrategy sessionStrategy =
        new CompositeSessionAuthenticationStrategy(List.of(
                concurrent,
                new ChangeSessionIdAuthenticationStrategy(),
                new RegisterSessionAuthenticationStrategy(registry),
                new CsrfAuthenticationStrategy(csrfTokenRepository)));
```

Running this requires imports for `SessionRegistry`, `SessionRegistryImpl`, `CsrfTokenRepository`, and the strategies inside a Servlet app with session/CSRF/registry configured. This is strictly an **ordering template**; production also needs `HttpSessionEventPublisher` or equivalent lifecycle listeners, multi-node registry management, and expired-session handling filters if using expire mode instead of reject mode.

### 6.1 Short-Circuiting When a Strategy Throws an Exception

`CompositeSessionAuthenticationStrategy` invokes delegates in the given order and **stops immediately when a delegate throws `SessionAuthenticationException`**. If the concurrent check rejects:

- Fixation strategies downstream do not run to rotate session IDs.
- No new session is registered.
- No authenticated `SecurityContext` is saved for the rejected attempt.
- The authentication mechanism switches to the failure flow/handler without sending a success response.
- Public responses must avoid leaking sensitive details about other devices if anti-enumeration policies require it.

If you write a custom wrapper that **catches all exceptions and continues**, you defeat session-limit enforcement. Always treat a session-authentication rejection as an **authentication failure** per contract—never downgrade it to a warning and return 200.

### 6.2 "Exactly Once" Matters More Than Bean Count

An application might have:

- A strategy generated by the `sessionManagement()` DSL for built-in filters.
- A `SessionAuthenticationStrategy` bean for a custom controller to call.
- A custom filter calling `onAuthentication`.
- A success handler accidentally calling `onAuthentication` again.

If uncoordinated, a single login event can rotate the session ID twice or emit duplicate registry/CSRF cleanups. Design **one owner for the authentication success lifecycle**. With `AbstractAuthenticationProcessingFilter`, attach the strategy via `setSessionAuthenticationStrategy` and **do not call it again inside `successfulAuthentication`**. With a self-authenticating MVC controller, call it once right after `authenticate`.

### 6.3 When Should You NOT Invoke Session-Creation Strategies?

If an API is completely stateless using bearer JWTs in headers on every request, creating an `HttpSession` after every JWT validation increases cookie/session overhead, hurts scalability, and contradicts `SessionCreationPolicy.STATELESS`. Never run session creation/fixation strategies on every JWT-authenticated request. `SessionAuthenticationStrategy` primarily serves **a new login event** in a stateful Servlet flow; refresh-token/JWT grant management has a separate contract.

## 7. Pure Java 17 Example: Proving Exact Order and Short-Circuiting

Before bringing in Spring, you can run a small program to verify the logic "valid credentials → control → fixation → register" and confirm rejections stop subsequent steps. This is a Java 17 **order simulation**, not a replacement for real `SessionAuthenticationStrategy`/Servlet behavior.

File `SuccessSessionOrderDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public final class SuccessSessionOrderDemo {

    static List<String> flow(boolean passwordOk, boolean sessionAllowed) {
        List<String> steps = new ArrayList<>();
        steps.add("authenticate");

        if (!passwordOk) {
            steps.add("authentication-failure");
            return steps;
        }

        steps.add("concurrent-control");
        if (!sessionAllowed) {
            steps.add("session-rejected");
            return steps;
        }

        steps.add("change-session-id");
        steps.add("register-session");
        steps.add("csrf-cleanup");
        steps.add("save-security-context");
        steps.add("success-response");
        return steps;
    }

    public static void main(String[] args) {
        System.out.println("ok=" + flow(true, true));
        System.out.println("wrong-password=" + flow(false, true));
        System.out.println("limit-rejected=" + flow(true, false));
    }
}
```

Run with JDK 17+:

```bash
javac SuccessSessionOrderDemo.java
java SuccessSessionOrderDemo
```

**Exact** stdout:

```text
ok=[authenticate, concurrent-control, change-session-id, register-session, csrf-cleanup, save-security-context, success-response]
wrong-password=[authenticate, authentication-failure]
limit-rejected=[authenticate, concurrent-control, session-rejected]
```

This program has no Spring or Servlet HTTP, so its purpose is **verifying ordering and short-circuiting logic**, not simulating cookies, real session IDs, or `SecurityContextRepository`. The Spring Boot example next tests through the real security filter chain.

## 8. Runnable Spring Boot 3.x: Custom Login Filter with SessionAuthenticationStrategy

This learning app uses Java 17+, Spring Boot 3.3.13, Spring Security 6.x, and MockMvc. Goals:

- `POST /api/login` accepts form-urlencoded `username` and `password`, handled by a **custom filter extending `AbstractAuthenticationProcessingFilter`** rather than an MVC controller.
- The filter calls `AuthenticationManager`, **the framework calls the strategy after auth succeeds**, and `successfulAuthentication` saves `SecurityContext` via the configured repository.
- The strategy is a `CompositeSessionAuthenticationStrategy` combining `ChangeSessionIdAuthenticationStrategy` and `CsrfAuthenticationStrategy`.
- `GET /api/me` proves a subsequent request loads the authenticated session.
- `GET /api/admin` requires `ROLE_ADMIN`, ensuring logged-in accounts do not automatically gain admin access.
- Tests verify the pre-login session ID changes; wrong passwords do not elevate the session; missing CSRF is rejected.

**Why doesn't the demo enable concurrent-session control yet?** Proper concurrency testing requires a registry, lifecycle event listeners, and expired-session handling. Section 10 still shows how to add it; the core demo prioritizes being cleanly runnable without claiming half-configured features.

### 8.1 Gradle Structure

```text
session-strategy-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/SessionStrategyApplication.java
    └── test/java/demo/SessionStrategyTest.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'session-strategy-lab'
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

Versions are pinned **to reproduce the lesson**, not as a recommendation to run unsupported branches in new production systems. Production apps should choose an actively supported Boot/Security line and follow its documentation and Javadocs.

### 8.2 Application, Filter, and Configuration

File `src/main/java/demo/SessionStrategyApplication.java`:

```java
package demo;

import java.io.IOException;
import java.util.List;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AbstractAuthenticationProcessingFilter;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
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
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SessionStrategyApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionStrategyApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("local-alice-password"))
                        .roles("USER")
                        .build(),
                User.withUsername("bob")
                        .password(encoder.encode("local-bob-password"))
                        .roles("USER", "ADMIN")
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
            CsrfTokenRepository csrfRepository) {
        // Concurrent session limiting is not enabled in this demo.
        return new CompositeSessionAuthenticationStrategy(List.of(
                new ChangeSessionIdAuthenticationStrategy(),
                new CsrfAuthenticationStrategy(csrfRepository)));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationManager manager,
            SecurityContextRepository repository,
            CsrfTokenRepository csrfRepository,
            SessionAuthenticationStrategy sessionStrategy)
            throws Exception {

        ParameterLoginFilter loginFilter = new ParameterLoginFilter(manager);

        // Important: attach strategy DIRECTLY to the custom filter.
        loginFilter.setSessionAuthenticationStrategy(sessionStrategy);

        // AbstractAuthenticationProcessingFilter needs the repository to
        // save context after successfulAuthentication in Security 6.
        loginFilter.setSecurityContextRepository(repository);

        // Handler only finalizes the response; DO NOT call strategy again.
        loginFilter.setAuthenticationSuccessHandler(
                (request, response, authentication) ->
                        response.setStatus(
                                HttpServletResponse.SC_NO_CONTENT));

        loginFilter.setAuthenticationFailureHandler(
                (request, response, failure) ->
                        response.sendError(
                                HttpServletResponse.SC_UNAUTHORIZED));

        return http
                .securityContext(context -> context
                        .requireExplicitSave(true)
                        .securityContextRepository(repository))
                .csrf(csrf -> csrf.csrfTokenRepository(csrfRepository))
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(HttpMethod.POST, "/api/login")
                            .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/me")
                            .authenticated()
                        .requestMatchers(HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .anyRequest().denyAll())
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(
                                (request, response, exception) ->
                                        response.sendError(
                                                HttpServletResponse.SC_UNAUTHORIZED)))
                .formLogin(AbstractHttpConfigurer::disable)
                .httpBasic(AbstractHttpConfigurer::disable)
                .addFilterAt(
                        loginFilter,
                        UsernamePasswordAuthenticationFilter.class)
                .build();
    }

    static final class ParameterLoginFilter
            extends AbstractAuthenticationProcessingFilter {

        ParameterLoginFilter(AuthenticationManager manager) {
            super(new AntPathRequestMatcher("/api/login", "POST"), manager);
        }

        @Override
        public Authentication attemptAuthentication(
                HttpServletRequest request,
                HttpServletResponse response) {

            String username = request.getParameter("username");
            String password = request.getParameter("password");

            if (username == null || username.isBlank()
                    || username.length() > 128
                    || password == null
                    || password.length() > 256) {
                throw new BadCredentialsException("Bad credentials");
            }

            // Client input is NOT authenticated yet; never assign roles here.
            UsernamePasswordAuthenticationToken candidate =
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            username, password);
            candidate.setDetails(
                    this.authenticationDetailsSource.buildDetails(request));

            return getAuthenticationManager().authenticate(candidate);
        }
    }
}

@RestController
class SessionStrategyController {

    @GetMapping("/api/me")
    Map<String, Object> me(Authentication authentication) {
        return Map.of(
                "name", authentication.getName(),
                "roles", authentication.getAuthorities().stream()
                        .map(authority -> authority.getAuthority())
                        .sorted()
                        .toList());
    }

    @GetMapping("/api/admin")
    String adminOnly() {
        return "admin";
    }
}
```

**Code and classes in the file:** One file has exactly one public class `SessionStrategyApplication`. `ParameterLoginFilter` is a static nested class; `SessionStrategyController` is package-private. Spring Boot discovers `@RestController` in the same `demo` package.

### 8.3 Why Is This Configuration Properly Placed?

**Filter matches only POST `/api/login`.** `AntPathRequestMatcher("/api/login","POST")` prevents login logic from running on every `GET /api/me` request. Only when `attemptAuthentication(...)` succeeds does the superclass trigger `sessionStrategy.onAuthentication(...)`.

**Unauthenticated token goes through the manager.** `UsernamePasswordAuthenticationToken.unauthenticated` grants no permissions upfront; `DaoAuthenticationProvider` loads the account, checks the password hash and status, and returns the verified result. 204 is returned only after both provider and session strategy accept.

**Same repository for chain and filter.** The chain's `SecurityContextHolderFilter` reads from the `SecurityContextRepository` bean, and `AbstractAuthenticationProcessingFilter` saves to that same bean on success. This avoids saving into repository A while subsequent requests read from repository B or `NullSecurityContextRepository`.

**Composite has two clear components.** When a pre-login `HttpSession` exists, `ChangeSessionIdAuthenticationStrategy` rotates its ID. `CsrfAuthenticationStrategy` clears the old token, preventing reuse of pre-login tokens. The demo does not enforce concurrent session limits yet: do not assume `maximumSessions=1` is active.

**Do not write the response before session policy runs.** The success handler only calls `response.setStatus(204)`; the superclass calls it after strategy/context save. Avoid calling `sendRedirect`/`flushBuffer` inside `attemptAuthentication` before session processing.

**Do not register the filter twice.** `ParameterLoginFilter` is instantiated right inside `securityFilterChain` and added via `addFilterAt`. It does **not** have `@Component` or `@Bean Filter` that would make Spring Boot register it in the Servlet container outside `FilterChainProxy`; doing both can cause double authentication or duplicate strategy invocations.

**CSRF remains enabled.** Because this is cookie-session login, `CsrfFilter` still blocks POSTs missing a token. MockMvc uses the `csrf()` helper rather than disabling security rules just to make tests pass.

### 8.4 Integration Tests for the SessionAuthenticationStrategy Flow

File `src/test/java/demo/SessionStrategyTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;

@SpringBootTest
@AutoConfigureMockMvc
class SessionStrategyTest {

    @Autowired
    MockMvc mvc;

    private MvcResult login(String username, String password)
            throws Exception {
        return mvc.perform(post("/api/login")
                        .with(csrf())
                        .param("username", username)
                        .param("password", password))
                .andReturn();
    }

    @Test
    void successPersistsContextForNextRequest() throws Exception {
        MvcResult response = login("alice", "local-alice-password");
        assertEquals(204, response.getResponse().getStatus());

        MockHttpSession session =
                (MockHttpSession) response.getRequest().getSession(false);
        assertNotNull(session);

        SecurityContext saved = (SecurityContext) session.getAttribute(
                HttpSessionSecurityContextRepository
                        .SPRING_SECURITY_CONTEXT_KEY);
        assertNotNull(saved);
        assertEquals("alice", saved.getAuthentication().getName());

        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("alice"));

        mvc.perform(get("/api/admin").session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void preLoginSessionIdChangesOnSuccess() throws Exception {
        MockHttpSession previous = new MockHttpSession();
        String idBefore = previous.getId();

        MvcResult response = mvc.perform(post("/api/login")
                        .session(previous)
                        .with(csrf())
                        .param("username", "bob")
                        .param("password", "local-bob-password"))
                .andExpect(status().isNoContent())
                .andReturn();

        MockHttpSession current =
                (MockHttpSession) response.getRequest().getSession(false);
        assertNotNull(current);
        assertNotEquals(idBefore, current.getId());

        mvc.perform(get("/api/admin").session(current))
                .andExpect(status().isOk());
    }

    @Test
    void wrongPasswordDoesNotCreateAuthenticatedContext()
            throws Exception {
        MvcResult response = login("alice", "wrong-password");
        assertEquals(401, response.getResponse().getStatus());

        MockHttpSession session =
                (MockHttpSession) response.getRequest().getSession(false);
        if (session != null) {
            assertNull(session.getAttribute(
                    HttpSessionSecurityContextRepository
                            .SPRING_SECURITY_CONTEXT_KEY));
        }

        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void csrfRequiredForCookieBasedLogin() throws Exception {
        mvc.perform(post("/api/login")
                        .param("username", "alice")
                        .param("password", "local-alice-password"))
                .andExpect(status().isForbidden());
    }
}
```

**These tests verify distinct boundaries:**

- `successPersistsContextForNextRequest` confirms filter/manager/strategy/success/save work together and the next request genuinely sees Alice's context, rather than merely checking the 204 login status.
- `preLoginSessionIdChangesOnSuccess` proves `ChangeSessionIdAuthenticationStrategy` rotates an existing session; Bob still receives his roles on the subsequent request. It tests with `MockHttpSession` and does not assume a change-ID event occurs if login has no prior session.
- `wrongPasswordDoesNotCreateAuthenticatedContext` confirms a failed authentication does not save Alice's principal. The CSRF helper may touch session/token state, yet **no authenticated context** is stored.
- `csrfRequiredForCookieBasedLogin` confirms missing CSRF blocks the request **before** the login filter; HTTP 403 here is not a wrong password.

**QA note:** The outcomes above are **design expectations**, not a claim that Gradle was executed in the reader's environment. If live test results differ, inspect filter registration/order, CSRF repository, mock session IDs, repositories, and Spring Security version—never remove protections just to turn tests green.

### 8.5 Running the Project

With Gradle wrapper:

```bash
./gradlew test
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat bootRun
```

If no wrapper was generated yet but compatible Gradle is installed, run `gradle test` / `gradle bootRun`. Do not run `javac SessionStrategyApplication.java` alone because the project requires the Spring Boot/Security classpath.

Expected result when running the four integration tests is **4 passing tests**. When running the app, a browser POSTing to `/api/login` needs a valid CSRF token bound to its session/cookie. The demo does not expose a public `GET /api/csrf` endpoint, so use the MockMvc tests for full verification rather than hardcoding CSRF strings or disabling CSRF globally. For a real SPA product, design an explicit token endpoint and clear `SameSite`/CORS/credentials policies.

### 8.6 Adding One Important Test for "Strategy Only on Success"

To verify unit-level invocation counts, you can attach a `SessionAuthenticationStrategy` spy in a separate test and count `onAuthentication` calls:

```text
POST login wrong password -> 0 strategy calls
POST login valid          -> 1 strategy call
GET /api/me with cookie   -> 0 new strategy calls
POST login valid again    -> 1 call for the new login event
```

This reflects **the filter's success contract**, not an expectation that per-request API authentication (JWT/Basic) treats every request as a "new login". When using a Mockito spy, ensure the filter actually holds the injected **spy instance**; spying on a bean while the filter uses a different instance makes the count meaningless.

## 9. Writing Your Own OncePerRequestFilter: Steps You Must Manage Yourself

Not every authentication mechanism extends `AbstractAuthenticationProcessingFilter`. If you choose a custom `OncePerRequestFilter`, you must manually manage:

```java
// INTEGRATION PSEUDOCODE: requires matcher, imports, catch/failure handlers,
// repository/strategy beans, and appropriate application CSRF.
if (isLoginRequest(request)) {
    Authentication candidate =
            UsernamePasswordAuthenticationToken.unauthenticated(
                    usernameFromForm, rawPasswordFromForm);

    Authentication verified = authenticationManager.authenticate(candidate);

    sessionAuthenticationStrategy.onAuthentication(
            verified, request, response);

    SecurityContext context = securityContextHolderStrategy
            .createEmptyContext();
    context.setAuthentication(verified);
    securityContextHolderStrategy.setContext(context);

    securityContextRepository.saveContext(context, request, response);

    successHandler.onAuthenticationSuccess(
            request, response, verified);
    return;
}

filterChain.doFilter(request, response);
```

**Not a standalone runnable Java file**: variables in this pseudocode must come from real configuration. Catch blocks, request parsing, and filter lifecycle are intentionally omitted to highlight **the exact ordering**. Production code must handle `AuthenticationException`/`SessionAuthenticationException` via failure handlers, protect CSRF, prevent session fixation, clear context on failure, rate-limit, and save only after the strategy accepts.

If a custom filter only validates bearer JWTs on every request without creating an `HttpSession`, **do not copy the pseudocode above verbatim** to run fixation/registry on every token. The goal is new login/session events, not every authenticated request.

### 9.1 Common Mistake with OncePerRequestFilter

```java
// WRONG: creating a session / rotating ID before checking credentials.
sessionStrategy.onAuthentication(
        userSuppliedAuthentication, request, response);
Authentication verified = manager.authenticate(candidate);
```

A wrong-password request must never trigger session-authentication success. Likewise, never pass an `Authentication` with `authenticated=true` forged from input into the strategy.

### 9.2 Strategy Rejects Yet Code Still Saves

```java
// WRONG: anti-pattern.
try {
    strategy.onAuthentication(verified, request, response);
} catch (SessionAuthenticationException ignored) {
    // "Just a session error, log in anyway" -> severe security flaw.
}
repository.saveContext(contextWithVerified, request, response);
```

If policy rejects a login due to too many sessions, continuing to save the context creates an authenticated session **beyond the limit**. On the failure path you must stop, send no success, persist no new context, and log sanitized reasons and internal metrics.

### 9.3 Calling the Strategy on Every Authenticated Protected Request

```java
// WRONG: filter runs on every URL without distinguishing login events.
Authentication current =
        SecurityContextHolder.getContext().getAuthentication();
if (current != null) {
    sessionStrategy.onAuthentication(current, request, response);
}
```

This can rotate the session ID on **every API call**, repeatedly wipe CSRF tokens, corrupt registry entries, and cause baffling session-limit behavior. The strategy runs when a *new authentication* is accepted by an authentication mechanism, not because the context already holds a principal from an existing session.

## 10. Limiting Concurrent Sessions Requires the Full Set of Parts

In the demo, the composite only contained fixation + CSRF. To enforce a limit such as one session per user, you need:

1. `SessionRegistry` tracking principal ↔ session IDs, with lifecycle cleanup.
2. `ConcurrentSessionControlAuthenticationStrategy` deciding reject/expire.
3. Fixation strategy rotating the ID before registration.
4. `RegisterSessionAuthenticationStrategy` registering the final ID.
5. `ConcurrentSessionFilter` or equivalent expiration handling when using expire-old mode.
6. `HttpSessionEventPublisher` / `HttpSessionIdListener` or corresponding Spring Session integration for destroy/ID-change events.
7. A **multi-node**-capable store/registry; local `SessionRegistryImpl` does not automatically become system-wide policy.
8. The real custom login filter must use that composite, rather than leaving an unused bean idle.

Separate config sample—**do not drop next to the demo without adapting the chain**:

```java
@Bean
SessionRegistry sessionRegistry() {
    return new SessionRegistryImpl();
}

@Bean
SessionAuthenticationStrategy sessionStrategyWithLimit(
        SessionRegistry registry,
        CsrfTokenRepository csrfRepository) {

    ConcurrentSessionControlAuthenticationStrategy concurrent =
            new ConcurrentSessionControlAuthenticationStrategy(registry);
    concurrent.setMaximumSessions(1);

    // true: reject new login once the limit is reached.
    // false: mark older sessions expired per policy.
    concurrent.setExceptionIfMaximumExceeded(true);

    return new CompositeSessionAuthenticationStrategy(List.of(
            concurrent,
            new ChangeSessionIdAuthenticationStrategy(),
            new RegisterSessionAuthenticationStrategy(registry),
            new CsrfAuthenticationStrategy(csrfRepository)));
}
```

**When applying:** replace the exact strategy bean injected into the filter; verify `SessionRegistry` and events; in multi-context apps, avoid duplicate `SessionAuthenticationStrategy` beans causing ambiguity. When requiring "one session only", test with **two independent cookie jars/session IDs**, not two tabs in the same browser session. In `reject=true` mode, a second login for the same account in a different session must be rejected; re-logging in within the same session ID may behave differently—check registry contract.

### 10.1 Why Must Registration Come After Fixation?

`ChangeSessionIdAuthenticationStrategy` can change the ID from `S1` to `S2`. If you register `S1` and the filter/session store then uses `S2`, the registry holds a stale ID. The standard order **concurrent → fixation → register** ensures the registry stores the final session ID.

### 10.2 Why Does ConcurrentSessionFilter Still Matter?

When policy chooses to expire old sessions, `ConcurrentSessionControlAuthenticationStrategy` marks the `SessionInformation` expired. That alone does not immediately abort every in-flight request. `ConcurrentSessionFilter` checks for expired sessions on subsequent requests and invokes configured logout/expired handlers. Marking without enforcement lets the old-session user keep operating unrestricted.

Even with `exceptionIfMaximumExceeded=true`, new logins are rejected before creating a session, yet registry cleanup is still essential so dead sessions do not stay counted against the quota forever.

### 10.3 Principal Identity and the Session Registry

`SessionRegistryImpl` typically uses the principal object as its map key; a custom principal lacking stable `equals/hashCode` can cause two logins of **the same account** to look like two different users, breaking limits. Use a stable identity and verify its contract, or map by appropriate account ID—never use a mutable entity or credential object carelessly as a key.

When a user belongs to multiple tenants, decide whether limits apply per **global identity**, **account within a tenant**, or **membership/session grant**. `SessionAuthenticationStrategy` does not understand tenant semantics by itself; the application defines the policy.

## 11. SessionFixationProtection Needs Deeper Understanding Than One Config Line

### 11.1 Attack Scenario

```text
Attacker knows session ID S1 before the victim logs in
           |
           v
Victim logs in successfully yet the app KEEPS S1
           |
           v
Attacker can reuse the now-authenticated S1
           |
           v
Session fixation vulnerability

Countermeasure:
  Once login is verified -> rotate ID S1 to S2
  Stop accepting S1 as an authenticated session
```

Spring Security typically enables this automatically for built-in form login. However, custom authentication flows must ensure the right strategy is active. A valid password check alone stops nothing if the pre-login cookie stays fixed and the ID never changes on login.

### 11.2 Events and Listeners to Watch

When a session ID changes, `SessionFixationProtectionEvent` and Servlet `HttpSessionIdListener` notifications may fire (depending on strategy and container). Any listener tracking state by session ID must handle these events cleanly without leaving duplicate records for old and new sessions.

If the session holds user state, saved requests, or CSRF tokens, decide whether those attributes stay or get cleared when identity changes. `ChangeSessionIdAuthenticationStrategy` primarily rotates the ID, while `CsrfAuthenticationStrategy` handles old CSRF tokens—these are **two distinct responsibilities**.

### 11.3 First Login Without an Existing Session

If the initial request carries no session cookie and no `HttpSession` exists yet, the ID-rotation strategy may do nothing. Afterwards `SecurityContextRepository.saveContext` can create a new session to persist login, sending a fresh cookie before the response commits. That is not a "failed to rotate session bug": there was no pre-login ID to rotate.

Do not "fix" this by forcing `getSession(true)` before every login if business logic doesn't need it; that increases unnecessary session allocations. When verifying session-ID security, test both **a pre-login session with an ID** and **a login without a prior session**.

## 12. CSRF on Identity Change

`CsrfFilter` validates CSRF tokens on unsafe HTTP methods per policy; `CsrfAuthenticationStrategy` handles cleaning up tokens when a new authentication succeeds. These two operate at different moments:

```text
1. POST /api/login carries a valid CSRF token.
2. CsrfFilter validates the token (if the endpoint is protected).
3. AuthenticationManager verifies the password.
4. SessionAuthenticationStrategy:
   - rotates session ID (if present)
   - clears pre-login CSRF token per CsrfAuthenticationStrategy
5. SecurityContextRepository saves context.
6. Success response.
7. SPA must fetch a NEW CSRF token before the next unsafe request
   if cookie/header has not been updated yet.
```

Never disable CSRF just because the first post-login XHR returns 403. The cause may simply be the frontend reusing a token intentionally invalidated on login. Provide an origin/session-safe token endpoint or use Spring Security's SPA integration.

For bearer APIs not relying on browser auto-sent cookies, the CSRF threat model differs; still, that does not mean "every REST app can disable CSRF" without analyzing how credentials travel.

## 13. Distinguishing Session Registration from Session Persistence

| Action | API / Mechanism | Target data | Outcome |
| --- | --- | --- | --- |
| Check session limit | `ConcurrentSessionControlAuthenticationStrategy` | `SessionRegistry` | Whether a new login is allowed. |
| Rotate session ID | `ChangeSessionIdAuthenticationStrategy` | Servlet `HttpSession` | New ID to mitigate fixation. |
| Register session | `RegisterSessionAuthenticationStrategy` | `SessionRegistry` | Tracks principal/session for concurrency. |
| Persist auth | `SecurityContextRepository.saveContext` | Session/repository | Subsequent requests can restore `Authentication`. |
| Present login success | `AuthenticationSuccessHandler` | HTTP response | 200/204/302 and cookies per repo/container. |

**Dangerous confusion:** having a session registry entry **does not prove** `SecurityContext` was saved in `HttpSession`. Conversely, having context saved in session **does not prove** the session was registered for concurrent-session control.

Tests must verify **both systems** whenever the product requires them, especially across multiple servers and after logout/timeouts.

## 14. Ordering with SecurityContextRepository and Response Commit

With Spring Security 6 explicit save, `SecurityContextHolderFilter` does not auto-persist when you mutate the context. A custom authentication mechanism must save after the strategy accepts, **before the response commits**.

Wrong:

```java
Authentication verified = manager.authenticate(candidate);
response.sendRedirect("/app");

// Too late: new session ID/cookie is not guaranteed.
sessionStrategy.onAuthentication(verified, request, response);
repository.saveContext(context, request, response);
```

Right:

```java
Authentication verified = manager.authenticate(candidate);

sessionStrategy.onAuthentication(verified, request, response);

SecurityContext context = holderStrategy.createEmptyContext();
context.setAuthentication(verified);
holderStrategy.setContext(context);
repository.saveContext(context, request, response);

response.sendRedirect("/app");
```

**Above is integration pseudocode**: variables must be defined, errors handled properly, and the strategy invoked only when verified. Never call `saveContext` in a `finally` block after the output stream has flushed. With `AbstractAuthenticationProcessingFilter` configured with a repository, the superclass handles this in the success path; your success handler does not need to save again.

A response can commit via `sendRedirect`, `sendError`, `flushBuffer`, writing a body larger than the buffer, streaming, or flushing the writer. Whenever cookies/session IDs must be sent, complete the strategy and save before any of these occur. A login test returning 204/302 **is not enough**; test a second request carrying the cookie.

## 15. SessionAuthenticationException: Must Be Handled as a Rejected Login

`onAuthentication` can throw `SessionAuthenticationException`, e.g., when exceeding maximum sessions. When that happens:

1. Do not set or save the newly verified `Authentication` into the new request's session.
2. Do not invoke `AuthenticationSuccessHandler`.
3. Route through the failure flow, returning the appropriate status/UX and sanitized internal logs.
4. Avoid overly revealing account/session state to clients if enumeration risks apply.
5. Never leave a partial new session registered after failure, especially if a custom composite has side effects.
6. Never return 200 "login OK" with a note "could not save session"—such states are misleading and can open vulnerabilities.

With `AbstractAuthenticationProcessingFilter`, the `doFilter` contract states: auth returned → strategy runs → success; exception → unsuccessful flow; `null` returned → authentication incomplete. If writing a filter that does not extend this class, preserve equivalent semantics.

### 15.1 Do Not Hard-Infer a Fixed HTTP Code from SessionAuthenticationException

A strategy may reject due to concurrency. Your `AuthenticationFailureHandler` decides the response—401, 403, or a custom page per API contract. Never claim the framework always returns one fixed HTTP code when a session strategy rejects. What matters is **never issuing an authenticated session** when policy rejects.

### 15.2 Why Not Wrap Every Exception in BadCredentialsException?

Exceeding a session quota is not a wrong password. Public responses may remain generic, yet internal audits/metrics must distinguish `bad_credentials` from `session_policy_denied`. Otherwise operations may suspect a brute-force attack when the real issue is `SessionRegistry` or quota exhaustion.

## 16. HTTP Basic, JWT, Remember-Me, MFA, and Multi-Step Login

### 16.1 HTTP Basic

HTTP Basic usually sends username/password on every request. Do not implicitly treat every Basic request as a fresh `HttpSession` creation event that rotates IDs and updates a registry. If the server uses a stateless flow, session-creating strategies are inappropriate. Match the mechanism to the product; Basic only uses Base64 so **TLS is mandatory**.

### 16.2 JWT Resource Server

Bearer JWTs are verified per request, normally without creating an `HttpSession`. Rules for `exp`, issuer, audience, revocation, and grants do not live in Servlet `SessionAuthenticationStrategy`. Never call `ChangeSessionIdAuthenticationStrategy` on every JWT. Any refresh-token login flow on the Authorization Server has its own policies.

### 16.3 Remember-Me

A remember-me cookie can authenticate a user after `HttpSession` is gone. Whether a session strategy runs depends on the authentication mechanism and config; do not equate it with browser username/password form login. If session registries/concurrent policies must govern remember-me sessions, inspect and test the exact flow rather than expecting default Spring Security 6 `SessionManagementFilter` to catch every event.

### 16.4 MFA, OTP, and Multi-Step Login

In multi-step flows, the first provider recognizing a username **is not necessarily** the final point to issue a fully authenticated session. Avoid rotating session IDs or registering authenticated sessions prematurely before MFA/step-up completes per policy. Clearly define which event counts as **an authorized login**; constrained pre-auth state may be stored separately without granting protected-resource access.

### 16.5 Re-Authentication Within the Same Session

If an already logged-in user re-authenticates to elevate privileges (step-up), define whether the strategy runs again. Rotating the session ID can make sense at a trust-level boundary, whereas concurrent session registration/counting must not create bogus duplicate entries. Do not blindly re-invoke all delegates unconditionally: verify the principal contract, session registry, and when privileges are granted.

## 17. Production Deployment: Critical Limitations

### 17.1 Cookies and HTTPS

Even if the strategy rotates the ID cleanly, if the client keeps sending the old cookie, subsequent requests can appear anonymous. Inspect `Set-Cookie` and `Cookie` over real HTTP alongside `Secure`, `HttpOnly`, `SameSite`, `Domain`, `Path`, reverse proxies, and CORS credentials. Never log full session IDs or cookies in production logs.

### 17.2 Distributed Session Stores

An in-memory `SessionRegistryImpl` knows nothing about sessions on other nodes. With Spring Session Redis or other distributed stores, use compatible registries, lifecycle events, and concurrency mechanisms. Test: log in on node A, log in on node B with the same account, log out/time out on node C, and verify quotas and old sessions are enforced per policy.

### 17.3 In-Flight Requests

Rotating a session ID or expiring an old session **does not automatically abort requests already in flight** on the old ID. If a critical operation already passed the filter, enforce authorization/freshness checks at the service/transaction boundary per risk policy. `SessionAuthenticationStrategy` governs **the login event**, not instantaneous revocation of in-progress transactions.

### 17.4 Session Timeouts and Privilege Changes

A session validly created at 09:00 can hold a snapshot of authorities after an admin revokes a role at 09:05. The session authentication strategy only runs at new login; **it is not per-request revalidation**. If the product needs rapid disablement or role revocation, implement auth versioning, session invalidation, or per-request checks.

### 17.5 Relationship to Multi-Tenancy

When a user belongs to multiple tenants, the session registry and principal equality must use the right namespace—such as a tenant-scoped account ID or a stable global identity ID. Never read `tenant_id` from a client header to "switch an authenticated session" without verifying membership and permissions. A session fixation strategy does not provide tenant isolation by itself.

### 17.6 Never Log Credentials

Debugging should record request IDs, verified principal IDs, strategy classes, success/failure outcomes, and session event types—never raw passwords, JWTs, session cookies, full serialized `SecurityContext`, or password hashes. `Authentication.getCredentials()` and session IDs are sensitive data.

## 18. Common Anti-Patterns

**A. Calling authenticate and immediately returning 200.**

```java
// WRONG if custom stateful login has session policy/persistence.
Authentication auth = manager.authenticate(candidate);
return ResponseEntity.ok("success");
```

The password check may work while fixation, concurrency, and context persistence are skipped. With `AbstractAuthenticationProcessingFilter`, wire the strategy and repo; with a controller, invoke the full lifecycle explicitly.

**B. Calling onAuthentication before authenticate.**

```java
// WRONG: user/client has not been verified yet.
sessionStrategy.onAuthentication(candidate, request, response);
Authentication verified = manager.authenticate(candidate);
```

**C. Calling twice after login.**

```java
// WRONG: superclass already runs the strategy, then success handler calls it again.
filter.setSessionAuthenticationStrategy(sessionStrategy);
filter.setAuthenticationSuccessHandler((req, resp, auth) -> {
    sessionStrategy.onAuthentication(auth, req, resp); // DOUBLE CALL
    resp.setStatus(204);
});
```

**D. Registering before rotating session ID.**

```text
WRONG: register(S1) -> change ID S1 to S2
RIGHT: concurrent check -> fixation (S2) -> register(S2)
```

**E. Swallowing the exception because the password matched.**

```java
// WRONG: session policy rejected it yet auth is still saved.
try {
    sessionStrategy.onAuthentication(auth, request, response);
} catch (SessionAuthenticationException ignored) {
}
repository.saveContext(context, request, response);
```

**F. Treating ChangeSessionId as a mandatory session creator.**

```text
Login with no HttpSession yet: no old ID exists to rotate.
When persistence is required, repository/session config decides whether to create a session.
```

**G. Using SessionRegistry alone to keep users logged in.** The registry is not a `SecurityContextRepository`; subsequent requests still need a valid persisted context or token.

**H. Running on every JWT/Basic request.** Causes session churn, CSRF token churn, and skewed quotas; strategies belong to appropriate auth events, not every time `Authentication` is seen.

**I. Annotating a filter with `@Component` and calling `http.addFilterAt` simultaneously.** Can run the filter twice in the container and chain; maintain a single registration path.

**J. Disabling CSRF or fixation to silence integration test errors.** Makes tests pass by deleting protections; instead fix the flow, tokens, and session lifecycle properly.

## 19. Debug Checklist When Custom Login Misbehaves

1. Does the request enter **the right `SecurityFilterChain`**? Do matchers/filters overlap?
2. Which custom filter handles `POST /api/login`? Does it extend `AbstractAuthenticationProcessingFilter` or roll its own `OncePerRequestFilter`?
3. Does `AuthenticationManager.authenticate` return a verified result or throw `AuthenticationException`?
4. If extending `AbstractAuthenticationProcessingFilter`, was `setSessionAuthenticationStrategy` called with the right instance? An unconfigured default may be a no-op.
5. Is the strategy invoked **twice** due to a success handler, controller, or custom `SessionManagementFilter`?
6. Are composite delegates ordered **concurrent → fixation → register → CSRF** per policy?
7. Is `SessionAuthenticationException` being swallowed or turned into success?
8. Did the pre-login request actually have an `HttpSession`? If not, no ID-rotation event can happen.
9. Does the login filter's `SecurityContextRepository` match the chain's repository? Does `saveContext` run **before response commit**?
10. Is `SecurityContext` loaded on the next request carrying the cookie? Are cookie attributes, proxy settings, and session store right?
11. Does `SessionRegistry` receive session destroy/change events, and does it span multiple nodes if clustered?
12. If `csrf()`/login POST returns 403, is `CsrfFilter` blocking it before the login filter?
13. If the CSRF token becomes invalid after login, did the client fetch the fresh token?
14. Is the filter registered twice as both a Servlet filter and a Security filter?
15. Do logs contain raw secrets or session cookies? If so, redact or suppress sensitive fields.

To verify accurately, enable security framework logging **in an isolated test environment**, trace by request ID, and inspect event order with zero credential leaks; avoid dumping full security contexts to the console.

## 20. Essential Test Matrix

| Scenario | Evidence to observe |
| --- | --- |
| Valid password with existing session | `onAuthentication` runs and session ID rotates; login succeeds. |
| Valid password with no initial session | Login still saves context if repo allows creating a session; change-ID event need not occur. |
| Wrong password | Strategy does not run, no authenticated context, failure response. |
| Disabled/locked account | Provider rejects; session strategy is not applied to a new login. |
| Missing CSRF on cookie login flow | `CsrfFilter` rejects before authentication. |
| Valid login with pre-login CSRF | Old CSRF token invalidated per policy; fresh token can be fetched. |
| Subsequent request with new session cookie | `SecurityContextRepository` loads the right principal. |
| Subsequent request without cookie | Never inherits the principal from a prior thread/request. |
| Role USER calling ADMIN | 403 despite successful login. |
| Role ADMIN calling ADMIN | 200 if authorization permits. |
| Two different users on thread pool | No mixing of principal, `HttpSession`, or authorities. |
| Max sessions reached, reject mode | `SessionAuthenticationException` blocks new login, no context saved. |
| Max sessions reached, expire-old mode | Old session marked and handled on next request by filter/policy. |
| Composite rejected by first delegate | Fixation/register/success do not continue running. |
| Rotate session ID before register | Registry records the final ID accurately. |
| Session expiration/logout | Registry cleaned up, quota freed, old requests rejected. |
| Log in node A, call API node B | Context and registry remain consistent under distributed architecture. |
| Incomplete MFA | No fully authenticated session created before policy allows. |
| Redirect sent before save | Test catches broken cookie/session persistence. |
| Stateless JWT request | Does not create sessions or rotate IDs merely for a valid token. |
| Role revoked while old session alive | Separate freshness/revalidation policy takes effect. |
| Cookie `Secure`/`SameSite`/path | Client receives/sends cookie properly, no tokens leaked in logs. |

## 21. Thought Exercises with Solutions

**Question 1.** A custom login filter calls `AuthenticationManager.authenticate` successfully, yet skips the session strategy. The user can still read `/api/me` via session. Is the system secure enough?

**Answer:** Not necessarily. Authentication and context persistence may work, yet session fixation, concurrency limits, or CSRF token rotation may be missing. Verify which strategy actually ran and test all required protections.

**Question 2.** With `AbstractAuthenticationProcessingFilter` in Spring Security 6, does the strategy run before or after `successfulAuthentication`?

**Answer:** **After** `attemptAuthentication` returns a verified `Authentication`, and **before** `successfulAuthentication`. On error or `null` return, it does not enter the completed-authentication success lifecycle.

**Question 3.** Why must a wrong-password user not get a rotated session ID merely for submitting login?

**Answer:** Session strategies are for **successful logins**. If every failed login rotated IDs or registered sessions, attackers could trigger session churn or manipulate sessions without proving identity.

**Question 4.** Does switching to `MODE_GLOBAL` to share context across requests solve `SessionAuthenticationStrategy`?

**Answer:** No. A global context risks leaking principals across users. Session strategies and repositories solve different problems; Servlets should keep the default holder strategy.

**Question 5.** A composite includes concurrent check, fixation, and register. What is the right order?

**Answer:** `ConcurrentSessionControlAuthenticationStrategy` → `ChangeSessionIdAuthenticationStrategy` (or matching fixation strategy) → `RegisterSessionAuthenticationStrategy`. CSRF cleanup can follow per policy. If the concurrent check rejects, later steps do not run.

**Question 6.** An admin sets max sessions = 1, yet a user opens two tabs in the same browser. Why isn't it necessarily blocked?

**Answer:** Two tabs can share **the same `JSESSIONID` cookie** and therefore the same `HttpSession`. To test two sessions, use two independent cookie stores, devices, or separate browsers.

**Question 7.** `ConcurrentSessionControlAuthenticationStrategy` throws `SessionAuthenticationException`, yet code catches it and saves `SecurityContext`. What is wrong?

**Answer:** The new login was rejected by policy; saving an authenticated context breaks the limit. You must abort the success flow and return a failure response.

**Question 8.** Does calling `RegisterSessionAuthenticationStrategy` alone keep the user logged in on the next HTTP request?

**Answer:** No. It only updates `SessionRegistry`; persisting `Authentication` across requests requires `SecurityContextRepository`/sessions or a token mechanism.

**Question 9.** A first login request has no `HttpSession` before auth. `ChangeSessionIdAuthenticationStrategy` does not change an ID, yet the user logs in afterwards. Is that contradictory?

**Answer:** There was no old ID to change. The repository can create a new session when saving the context, per policy; inspect cookies and follow-up requests instead of treating "no change event" as no protection.

**Question 10.** Right after logging in, the frontend sends a data-mutating POST and receives CSRF 403 even though login succeeded. Why?

**Answer:** `CsrfAuthenticationStrategy` may have cleared the pre-login CSRF token; the frontend is still sending the stale token. Fetch the new token per your SPA/cookie design after authentication state changes.

**Question 11.** A custom filter attached a strategy to the superclass, and the success handler also calls the strategy. Is that fine?

**Answer:** No. The superclass already invoked it on success, so calling it again mutates session/CSRF/registry twice. Remove the duplicate call from the success handler.

**Question 12.** Users authenticate via stateless JWTs, with `JwtAuthenticationToken` on every request. Should `ChangeSessionIdAuthenticationStrategy` run on every request?

**Answer:** No. A JWT Resource Server validates tokens as bearer credentials and normally has no login session to rotate. If there is a separate interactive OAuth2 login flow, configure its session policy separately.

**Question 13.** If a fixation strategy is already configured, is `SecurityContextRepository.saveContext` still needed?

**Answer:** Yes, if stateful login across requests is required with explicit save. Fixation handles the session ID; repository save persists the context. Built-in filters can save for you once configured with the right repository.

**Question 14.** Why must concurrency tests also cover logout and session destruction?

**Answer:** The registry tracks active sessions. Without cleanup when a session ends, users can get locked out even with zero live sessions. Wire listeners/shared registries and test the full lifecycle.

## 22. Production Rollout Checklist

1. **Identify auth events**: determine which requests genuinely create new logins; never run strategies on every authenticated request.
2. **Trusted providers**: credentials, MFA, and identity are verified before the session strategy runs.
3. **Lifecycle owner**: built-in `AbstractAuthenticationProcessingFilter` invokes the strategy; custom controllers/filters must invoke it themselves, without duplication.
4. **Fixation protection**: use `changeSessionId` on modern Servlet containers; never pick `none` casually.
5. **Composite order**: concurrent check → fixation → register → CSRF; fail short-circuits.
6. **Session registry**: stable principal ID, session lifecycle cleanup, defined reject/expire concurrency policy, clear cluster semantics.
7. **Context persistence**: same `SecurityContextRepository` on chain and login; explicit save before response commit.
8. **Cookie policy**: HTTPS, `Secure`, `HttpOnly`, `SameSite`, `Domain`/`Path`, proxy/CORS, and session timeout.
9. **CSRF**: retain `CsrfFilter` for cookie-auth and handle post-login token refresh.
10. **Errors**: neither `SessionAuthenticationException` nor password failures ever turn into success; public messages never leak secrets.
11. **Filter registration**: no double registration; exact URL/method matching; verify `CsrfFilter`/authentication ordering.
12. **Stateful vs. stateless**: never create `HttpSession` on every JWT request; OAuth grants/refresh tokens have separate policies.
13. **MFA/step-up**: define when a fully authenticated session is granted; never grant access before all required factors pass.
14. **Testing**: success/failure, pre/post session IDs, saved context, concurrent sessions, CSRF, cookies, logout, and multiple nodes.
15. **Freshness**: revoked roles or disabled accounts after login require separate reauthorization/revocation mechanisms rather than relying on the session strategy.
16. **Security review**: audit session lifecycle, never log tokens/passwords/session IDs, and monitor auth-failure/session-denial metrics.

## 23. Official References for Verification

- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): explains `SessionManagementFilter`, Spring Security 6 changes, session fixation, concurrency, and explicit save.
- [Spring Security 6.5 — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): auth success sequence, strategies, context, repositories, and success handlers.
- [Spring Security 6.5 — AbstractAuthenticationProcessingFilter Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html): strategy invoked immediately after `attemptAuthentication` succeeds; `setSessionAuthenticationStrategy`, `setSecurityContextRepository`.
- [Spring Security 6.5 — SessionAuthenticationStrategy Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/SessionAuthenticationStrategy.html): `onAuthentication` contract and `SessionAuthenticationException`.
- [Spring Security 6.5 — CompositeSessionAuthenticationStrategy Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/CompositeSessionAuthenticationStrategy.html): recommended ordering and short-circuiting.
- [Spring Security 6.5 — ChangeSessionIdAuthenticationStrategy Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/ChangeSessionIdAuthenticationStrategy.html): `HttpServletRequest.changeSessionId` and fixation.
- [Spring Security 6.5 — ConcurrentSessionControlAuthenticationStrategy Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/ConcurrentSessionControlAuthenticationStrategy.html): maximum sessions, rejecting or expiring old sessions.
- [Spring Security 6.5 — RegisterSessionAuthenticationStrategy Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/RegisterSessionAuthenticationStrategy.html): adding sessions to the registry after final ID is settled.
- [Spring Security 6.5 — CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): CSRF checking and resetting tokens after authentication.
- [Spring Security 6.5 — Session Management Migrations](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html): explicit-save and migration changes from Spring Security 5.
- [Spring Security 6.5 — MockMvc Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc.html): `csrf()` and security integration tests.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookies, fixation, timeouts, and session lifecycle.

**Conclusion:** `SessionAuthenticationStrategy` is the **session-policy step of a newly succeeded authentication event**, not a credential verifier and not the store that persists `SecurityContext` across requests. In Spring Security 6, authentication mechanisms must invoke the right strategy themselves. With `AbstractAuthenticationProcessingFilter`, configure it via `setSessionAuthenticationStrategy` so the framework invokes it **after `attemptAuthentication` and before `successfulAuthentication`**. With custom controllers/`OncePerRequestFilter`, invoke it **exactly once after credentials are verified**, honor rejections as failures, and then create/save the context before the response commits. Maintain the order **concurrent check → fixation → register → CSRF**, verify with both login requests and cookie-carrying follow-up requests, and keep session policies cleanly separated from JWT/stateless flows and authorization.