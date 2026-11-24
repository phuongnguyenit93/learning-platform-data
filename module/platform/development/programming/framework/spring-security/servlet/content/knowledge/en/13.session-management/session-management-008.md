# SessionAuthenticationStrategy in built-in and custom authentication mechanisms

> **Scope:** Spring Security on the **Servlet stack**, Java 17+, Spring Boot 3.x, and Spring Security 6.x. This lesson explains the role, invocation point, and execution order of `SessionAuthenticationStrategy` upon successful login; compares the built-in form login flow against an application-written custom authentication filter; and covers configuring and testing session fixation, session limits, saving `SecurityContext`, CSRF, and distinguishing stateful vs. stateless. The Spring example below is code for **a Spring Boot project**, not a program runnable with `javac` alone; the final section includes a standalone Java 17 example with exact stdout.

## 1. What problem does SessionAuthenticationStrategy solve?

After a user supplies valid credentials, producing an authenticated `Authentication` only answers *who just authenticated?*. A web application using **HTTP sessions** must also decide:

- Should this account be allowed to open a new session if the concurrent session limit has already been reached?
- Must the **session ID** change to prevent session fixation?
- Should the new session be registered with the session manager to enforce concurrent-session policy?
- Must authentication-related tokens—such as an old CSRF token—be cleared or rotated?
- If a strategy rejects the login, should the application still save `SecurityContext` or return a success redirect?

`org.springframework.security.web.authentication.session.SessionAuthenticationStrategy` is the contract for executing **tasks tied to a successful authentication event and the session**, typically before the authentication success handler sends the response.

Minimal API signature:

~~~java
public interface SessionAuthenticationStrategy {
    void onAuthentication(
            Authentication authentication,
            HttpServletRequest request,
            HttpServletResponse response)
            throws SessionAuthenticationException;
}
~~~

This is a **condensed library signature**, not an interface you need to recreate. `SessionAuthenticationException` is a subclass of `AuthenticationException`, so a strategy's rejection can route to the **authentication failure flow** instead of returning a logged-in session.

**Incorrect belief:** “`UserDetailsService` or `AuthenticationProvider` automatically registers the session.” Those two components verify identity/credentials; session management is a separate responsibility.

## 2. Identifying components accurately in the system

| Component | Role | Do not confuse with |
| --- | --- | --- |
| `AuthenticationProvider` | Verifies credentials and creates an authenticated `Authentication`. | Does not own session cookies. |
| `AuthenticationManager`, typically `ProviderManager` | Selects providers and coordinates authentication. | Not `SecurityContextRepository`. |
| `SessionAuthenticationStrategy` | Applies policies when **authentication succeeds**: session count, fixation, registration, token lifecycle. | Not the cross-request principal store. |
| `SecurityContextHolder` | Lets current code access context; defaults to binding to the processing thread. | Not DB/session persistence. |
| `SecurityContextRepository` | Loads and saves `SecurityContext` across requests, per session policy. | Does not automatically invoke session strategy when credentials are verified. |
| `RequestCache` / `SavedRequest` | Remembers the pre-login request for post-login navigation. | Does not control login session count. |
| `AuthenticationSuccessHandler` | Decides response/redirect after login. | Does not replace session fixation protection. |
| `SessionRegistry` | Tracks sessions and principals for concurrency management. | Not the servlet container session store. |
| `HttpSessionEventPublisher` | Publishes session creation/destruction/change events from the servlet container to Spring Security listeners. | Does not verify credentials itself. |

**Ask questions at the right layer:** “Did the session ID change after POST `/login`?” belongs to the session strategy; “Does the next GET `/me` request still have a principal?” belongs to the repository/session cookie; “Was the password on POST `/login` right?” belongs to the provider; “Is GET `/admin` allowed?” belongs to authorization.

## 3. When is the strategy called in built-in form login?

In common **Servlet form login** setups, `UsernamePasswordAuthenticationFilter` extends `AbstractAuthenticationProcessingFilter`. The filter's high-level sequence is:

~~~text
POST /login + valid CSRF token
        |
        v
CsrfFilter (checks request before login filter)
        |
        v
UsernamePasswordAuthenticationFilter
  |  attemptAuthentication(request, response)
  |     -> AuthenticationManager.authenticate(...)
  |     -> AuthenticationProvider verifies credentials
  |     -> returns verified Authentication
  |
  |  sessionAuthenticationStrategy.onAuthentication(
  |      authResult, request, response)
  |     -> session limit / session ID / registration / CSRF policies
  |     -> may throw SessionAuthenticationException
  |
  |  successfulAuthentication(...)
  |     -> creates/sets SecurityContext
  |     -> saves via SecurityContextRepository
  |     -> remember-me, events, success handler per configuration
  v
302 Location per success handler (or other success response)
~~~

If `attemptAuthentication` throws `AuthenticationException` due to a wrong password, **the strategy is not called to register a new session**. If the strategy throws `SessionAuthenticationException`, the authentication flow must be treated as a failure; no success redirect is sent and no newly authenticated context is saved.

Distinguish **an authentication request** from requests using an existing session:

~~~text
Attempt 1: POST /login -> valid credentials -> invokes strategy -> saves context
Attempt 2: GET /profile -> loads saved context -> NOT a new login
Attempt 3: GET /orders  -> loads saved context -> does NOT invoke strategy again
~~~

Calling the session strategy on **every request** instead of only on new authentication can continuously rotate the session ID, double-register sessions, trigger abnormal logouts, and break concurrent-session enforcement.

### Spring Security 6 and SessionManagementFilter

In older models, documentation/applications could rely on `SessionManagementFilter` to **detect a newly changed context** and invoke `SessionAuthenticationStrategy`. With Spring Security 6's default approach, **the authentication mechanism is responsible for invoking the strategy** upon a new authentication; do not assume `SessionManagementFilter` is automatically in the chain to handle this for custom filters.

This matters enormously when writing your own filter:

~~~text
BROKEN CUSTOM FILTER:
  manager.authenticate(requestToken)
  SecurityContextHolder.getContext().setAuthentication(result)
  chain.doFilter(...)
  [forgot to call SessionAuthenticationStrategy]
  [forgot to save SecurityContext]
  -> session fixation/concurrency/CSRF or persistence can break
~~~

Spring Security 6 also favors **explicit save** via `SecurityContextHolderFilter` and `SecurityContextRepository` per configuration. Merely setting the result on `SecurityContextHolder` **does not guarantee** the next request restores authentication. For custom filters, either extend a standard filter class that already invokes the strategy and saves context, or implement both steps explicitly.

## 4. Common SessionAuthenticationStrategy implementations

### 4.1. `ChangeSessionIdAuthenticationStrategy`

This strategy changes the existing session's ID via `HttpServletRequest.changeSessionId()`, suited to modern Servlet APIs. Its goal is preventing **session fixation**: an attacker must not keep using a session ID known before the victim logged in.

~~~text
Before login:
  Cookie JSESSIONID=preLoginId
  Session holds pre-login data

After successful login:
  Cookie JSESSIONID=postLoginId
  preLoginId != postLoginId
  Appropriate session attributes can be preserved
~~~

Changing the session ID is **not** setting `JSESSIONID` directly from a user-supplied string, nor changing the username. `changeSessionId()` requires an existing session; the strategy only changes the session's ID when a session already exists under that mechanism—do not expect every login to create a new session if the app is configured not to create sessions.

Related options in Spring Security configuration can include:

- `sessionFixation().changeSessionId()`: rotates the ID with Servlet container support.
- `sessionFixation().migrateSession()`: creates a new session and transfers session attributes when appropriate.
- `sessionFixation().newSession()`: creates a new session with a policy not to carry over old application attributes under that mechanism.
- `sessionFixation().none()`: disables fixation protection; **not recommended** just to make a failing test pass.

Default strategy and attribute-transfer details can depend on Servlet API/version/configuration; **test actual cookies/sessions** rather than relying solely on API names.

### 4.2. `ConcurrentSessionControlAuthenticationStrategy`

This strategy checks the principal's current sessions via `SessionRegistry` and decides whether to allow the new authentication to proceed. Two policies exist:

- **Reject new login when limit reached:** configure `setExceptionIfMaximumExceeded(true)`, throwing `SessionAuthenticationException`. The old session remains the permitted one.
- **Allow new login and mark old session expired:** configure `setExceptionIfMaximumExceeded(false)`. In this case, ensure subsequent requests from the flagged session are blocked/invalidated via proper synchronization and session control—typically `ConcurrentSessionFilter` or Spring Security's `maximumSessions(...)` configuration.

The two options carry different UX/security semantics. Do not assume “maxSessions(1)” always kicks out the old session or always rejects the new login; check `maxSessionsPreventsLogin(...)` or `exceptionIfMaximumExceeded`.

`SessionRegistry` uses the **principal** to identify sessions. If an application uses a custom `UserDetails` whose principal `equals()/hashCode()` is unstable, two logins by the same user can be treated as two different principals, breaking concurrency control. This is an easily missed bug when “the session registry works yet users still open multiple sessions”.

### 4.3. `RegisterSessionAuthenticationStrategy`

Once policy permits, this strategy registers `principal + session ID` into `SessionRegistry`. It does not verify passwords, grant authorities, or replace saving `SecurityContext`.

Because registration must happen **after** session ID rotation, order matters:

~~~text
1) ConcurrentSessionControlAuthenticationStrategy
   -> checks whether creating a new session is allowed?

2) ChangeSessionIdAuthenticationStrategy
   -> changes session ID after login if needed

3) RegisterSessionAuthenticationStrategy
   -> saves principal and new ID into SessionRegistry
~~~

Moving `RegisterSessionAuthenticationStrategy` ahead of the ID change step can cause the registry to record an ID that mismatches the real session. Running the concurrency check after registration can increment the session count prematurely and mis-evaluate policy. This is why `CompositeSessionAuthenticationStrategy` should be used when combining ordered tasks.

### 4.4. `CsrfAuthenticationStrategy`

This strategy handles the **CSRF token** lifecycle when a user authenticates, preventing an old token from remaining valid across the authentication boundary. It works alongside `CsrfTokenRepository` and `CsrfFilter`, and does **not** replace checking tokens on POSTs.

With cookie/session-based form login:

- POST `/login` typically **must carry a valid CSRF token** before the auth filter runs.
- After successful authentication, the old token may be cleared/rotated per config; subsequent forms must fetch the new token.
- Never disable CSRF just to make session tests easier to write.
- When assembling custom composite/override strategies, verify the **CSRF lifecycle** and matching repository configuration so you do not accidentally drop framework protections.

### 4.5. `NullAuthenticatedSessionStrategy`

This strategy performs no session work upon successful authentication. It can suit a carefully designed **stateless** mechanism, but is **not** a fix for form login that needs session fixation protection and session limits.

If an endpoint authenticates via Bearer JWT on every request, there is normally no “successful login then save web session” step like form login. JWT validation/authorization is a different flow; do not hit a concurrency registry every time a token is decoded as if the user just created a new session.

## 5. Why processing order and strategy placement matter

Suppose the limit is one session per principal; strategies are ordered:

~~~text
CONCURRENCY CHECK
       |
       | allowed
       v
SESSION ID ROTATION
       |
       v
SESSION REGISTRY UPDATE
       |
       v
CSRF TOKEN LIFECYCLE
       |
       v
SECURITY CONTEXT SAVE
       |
       v
SUCCESS RESPONSE
~~~

If the first strategy rejects because another session exists, the remaining steps must not run as if login succeeded. With `CompositeSessionAuthenticationStrategy`, delegates execute in list order; an exception interrupts the flow accordingly.

Two things must not be conflated:

1. **Registering a session in the registry** only supports concurrency tracking; it does not mean `SecurityContext` was saved so the next request recovers the principal.
2. **Writing `SecurityContext` to the session** only reloads the principal; forgetting protective strategies still leaves the system vulnerable to session fixation or bypassing login limits.

**Session fixation protection is not session expiration.** Rotating the session ID within the same session after login differs from marking a previously logged-in user's session expired. When an application lets a new login replace an old session, both marking/session filtering and appropriate session event handling are required.

## 6. Example 1 — Built-in form login, configuration-only

When no custom authentication filter is needed, the concise approach is configuring Spring Security's policy rather than assembling delegates manually.

~~~java
package com.example.sessionlesson;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class FormLoginPolicyExample {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.changeSessionId())
                .maximumSessions(1)
                .maxSessionsPreventsLogin(true));

        return http.build();
    }
}
~~~

**This snippet illustrates form login policy** and must not be placed alongside the full `SecurityConfig` in section 8 within the same demo app, as that would create two overlapping chains. Choose **one** appropriate configuration.

With `.maximumSessions(1).maxSessionsPreventsLogin(true)`, a user with an active session will be blocked from creating a second session; if a session is destroyed, the registry must be updated so it does not keep treating the old session as active. With Spring Boot/Servlet, registering `HttpSessionEventPublisher` as in section 8 is typically required. If choosing `maxSessionsPreventsLogin(false)`, new logins can mark old sessions expired; test that requests from the old session are handled properly.

Key takeaway: this fluent configuration lets Spring Security wire the necessary strategies into the **built-in authentication mechanism**. For a custom application-written filter, declaring a similar policy does not guarantee the new filter invokes the strategy properly.

## 7. Example 2 — Same SessionAuthenticationStrategy for form and custom filter

Demo problem: the application exposes **two username/password login endpoints** for easy comparison:

- `POST /login`: Spring Security's built-in form login mechanism.
- `POST /partner-login`: custom filter extending `AbstractAuthenticationProcessingFilter`.
- Both use the **same** `AuthenticationManager` and the **same** `SessionAuthenticationStrategy`.
- Both save into the **same** `SecurityContextRepository`.
- Policy is **at most one session per principal, rejecting the second login**, rotating the session ID after login, writing to the registry, and managing CSRF tokens.

The demo intentionally reuses username/password to highlight the **filter** difference. In real applications, if ordinary form login suffices, prefer the built-in `UsernamePasswordAuthenticationFilter` instead of rewriting it. For OTP, magic links, API-key exchanges, or specialized credentials, custom filters and providers have custom logic, yet the duty to invoke the strategy remains similar.

### 7.1. Required dependencies

Create a Spring Boot 3.x project on Java 17 with:

- `spring-boot-starter-web`
- `spring-boot-starter-security`
- `spring-boot-starter-test` (test scope)
- `spring-security-test` (test scope)

Place Java files in package `com.example.sessionlesson`. JDBC is not needed in the demo; `InMemoryUserDetailsManager` provides a learning user. **Never use hardcoded passwords in production**.

### 7.2. Custom filter — `PartnerLoginFilter.java`

~~~java
package com.example.sessionlesson;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.authentication.AbstractAuthenticationProcessingFilter;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

public final class PartnerLoginFilter
        extends AbstractAuthenticationProcessingFilter {

    public PartnerLoginFilter(
            org.springframework.security.authentication.AuthenticationManager manager) {
        super(new AntPathRequestMatcher("/partner-login", "POST"), manager);
    }

    @Override
    public Authentication attemptAuthentication(
            HttpServletRequest request, HttpServletResponse response)
            throws AuthenticationException, IOException {

        String username = request.getParameter("username");
        String password = request.getParameter("password");

        // Validate only format/size at the HTTP boundary.
        // Do not verify passwords yourself inside the filter.
        if (username == null || username.isBlank()
                || username.length() > 128
                || password == null || password.length() > 1024) {
            throw new BadCredentialsException("Invalid credentials");
        }

        UsernamePasswordAuthenticationToken submitted =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        username, password);

        return getAuthenticationManager().authenticate(submitted);
    }
}
~~~

**Explanation:**

1. `AbstractAuthenticationProcessingFilter` includes the logic to call `SessionAuthenticationStrategy` when `attemptAuthentication` returns a successful result, and only then proceeds to `successfulAuthentication`. We do not call it twice manually.
2. `UsernamePasswordAuthenticationToken.unauthenticated(...)` creates an **unauthenticated** request token. Never use the authenticated constructor or client-supplied authorities.
3. The filter bounds input; it does **not** compare passwords. Password verification belongs to `DaoAuthenticationProvider` inside the manager.
4. Do not call `trim()` on passwords because it can alter the exact secret chosen by the user. If normalizing usernames, design it consistently with the user store.
5. `AntPathRequestMatcher` is used illustratively in Spring Security 6.x; matcher APIs may be deprecated in newer 6.x releases. When upgrading major versions, use supported matchers/APIs while preserving the **POST /partner-login** constraint.
6. **Do not annotate this filter with `@Component` or `@Bean`** if you already pass it directly to `HttpSecurity`. Avoid having Spring Boot auto-register a second servlet filter outside the security chain.

**Important:** a custom filter does not automatically receive `SecurityContextRepository` and `SessionAuthenticationStrategy` like filters built by standard configurers. You must **inject them into the filter via setters** in the chain configuration below.

### 7.3. Full configuration — `SecurityConfig.java`

~~~java
package com.example.sessionlesson;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationSuccessHandler;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.ConcurrentSessionControlAuthenticationStrategy;
import org.springframework.security.web.authentication.session.RegisterSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.security.web.session.HttpSessionEventPublisher;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails user = User.withUsername("student")
                .password(encoder.encode("local-example-only"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(user);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(provider);
    }

    @Bean
    SessionRegistry sessionRegistry() {
        return new SessionRegistryImpl();
    }

    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }

    @Bean
    CsrfTokenRepository csrfTokenRepository() {
        return new HttpSessionCsrfTokenRepository();
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository());
    }

    @Bean
    SessionAuthenticationStrategy sessionAuthenticationStrategy(
            SessionRegistry registry, CsrfTokenRepository csrfTokens) {

        var concurrency =
                new ConcurrentSessionControlAuthenticationStrategy(registry);
        concurrency.setMaximumSessions(1);
        concurrency.setExceptionIfMaximumExceeded(true);

        var fixation = new ChangeSessionIdAuthenticationStrategy();
        var registration =
                new RegisterSessionAuthenticationStrategy(registry);
        var csrf = new CsrfAuthenticationStrategy(csrfTokens);

        return new CompositeSessionAuthenticationStrategy(
                List.of(concurrency, fixation, registration, csrf));
    }

    @Bean
    SecurityFilterChain webChain(
            HttpSecurity http,
            AuthenticationManager manager,
            SessionAuthenticationStrategy sessionStrategy,
            SecurityContextRepository contextRepository,
            CsrfTokenRepository csrfTokens) throws Exception {

        // Spring Security's formLogin filter and the custom filter share the same
        // AuthenticationManager, session policy, and context repository.
        http.authenticationManager(manager);

        http
            .securityContext(context -> context
                .securityContextRepository(contextRepository))
            .csrf(csrf -> csrf.csrfTokenRepository(csrfTokens))
            .sessionManagement(session -> session
                .sessionAuthenticationStrategy(sessionStrategy))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/partner-login").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .defaultSuccessUrl("/private", true)
                .permitAll());

        PartnerLoginFilter partner = new PartnerLoginFilter(manager);
        partner.setSessionAuthenticationStrategy(sessionStrategy);
        partner.setSecurityContextRepository(contextRepository);
        partner.setAuthenticationSuccessHandler(
                new SimpleUrlAuthenticationSuccessHandler("/private"));
        partner.setAuthenticationFailureHandler(
                new SimpleUrlAuthenticationFailureHandler("/login?error"));

        http.addFilterBefore(
                partner, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
~~~

### Analyzing the configuration accurately

- `sessionAuthenticationStrategy(...)` is the **exact same instance** passed to the form-login chain and the custom `PartnerLoginFilter`; both login mechanisms enforce an equivalent policy.
- The composite order is **concurrency → fixation → registration → CSRF lifecycle**. If concurrency rejects, subsequent steps are not treated as successful.
- In the demo, `exceptionIfMaximumExceeded=true` causes the second login to be blocked. It does not rely on “allow new login then expire old session”, so do not assume registering the strategy automatically adds every expired-session handling filter.
- `HttpSessionEventPublisher` ensures expiration/destruction events are published so the registry can purge entries; otherwise the registry easily retains dead sessions and users get unexpectedly rejected at login. In distributed systems, proper session-tracking infrastructure is needed rather than assuming a single-JVM `SessionRegistryImpl` suffices.
- `CsrfTokenRepository` is a shared bean so the CSRF filter and `CsrfAuthenticationStrategy` reference **the same token storage policy**. When overriding session/CSRF settings in real apps, verify nothing is omitted or duplicated inadvertently.
- `SecurityContextRepository` is declared explicitly and shared, enabling subsequent requests to load the principal from the session. `RequestAttributeSecurityContextRepository` supports context within the same request across dispatches, while `HttpSessionSecurityContextRepository` supports cross-request session storage.
- `PartnerLoginFilter` is an **object created with `new`**, so Boot does not register it outside `FilterChainProxy`.
- `.formLogin(...defaultSuccessUrl("/private", true))` only controls post-authentication redirect. It is not a session-count or fixation strategy.
- `DaoAuthenticationProvider` may have constructor/deprecation changes depending on the exact 6.x version. Using the no-arg constructor + setters fits many Spring Security 6 releases; if using a newer version with different recommended APIs, adapt to your version without changing semantics.
- `local-example-only` is a learning password; never use it in any real account.

**Note on composite policies:** When Spring Security auto-configures form login/CSRF/concurrency, the framework can assemble matching strategies itself. Here we **pass an explicit session strategy** to clarify sharing the same policy with a custom filter; do not copy this exact config verbatim into an app that already has multiple chains/managers/strategies. Read the actual chain configuration, verify CSRF token rotation, and prevent custom code from invoking the strategy twice.

### 7.4. Controller — `DemoController.java`

~~~java
package com.example.sessionlesson;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/private")
    public String privateEndpoint(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

### 7.5. Main class — `SessionLessonApplication.java`

~~~java
package com.example.sessionlesson;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionLessonApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionLessonApplication.class, args);
    }
}
~~~

### 7.6. Successful login progression

~~~text
Browser has pre-login HttpSession id=S1
  |
  +-- POST /login or POST /partner-login, valid CSRF token
  |
  v
Credentials verified by DaoAuthenticationProvider
  |
  v
CompositeSessionAuthenticationStrategy
  1. Concurrent control: user has no session yet -> allowed
  2. Change session ID: S1 -> S2
  3. Register: principal=student, sessionId=S2
  4. CSRF lifecycle: old token handled per policy
  |
  v
successfulAuthentication:
  SecurityContext.authentication = authenticated student
  SecurityContextRepository.saveContext(...)
  |
  v
302 Location: /private
  |
  v
GET /private + session S2
  -> Repository loads context
  -> Authentication.getName() == "student"
  -> 200, body "student"
~~~

What to observe in logs/tests is not the literal ID value, but the relation **S1 differs from S2** when a pre-login session existed and the session ID rotation policy applied. Once the browser updates the `JSESSIONID` cookie from the response, subsequent requests use that session.

### 7.7. Progression when the account already has one session

~~~text
Tab/device A:
  POST /login valid -> registered session A

Device B:
  POST /partner-login valid credentials
    -> concurrency strategy sees principal reached maxSessions=1
    -> throws SessionAuthenticationException
    -> authentication failure handler
    -> not granted a second login session

Session A remains permitted to operate.
~~~

**Do not confuse valid password with completely successful login.** `AuthenticationProvider` already verified the password as correct, yet the strategy can still reject an authentication due to session policy. That is why the strategy runs **between the authentication result and the success handler**.

## 8. MockMvc testing: form login and custom filter

In a project with `spring-security-test`, use `MockMvc` to run the real **Servlet SecurityFilterChain** rather than calling a mocked method alone. The tests below assume the exact classes and configuration from section 7.

Create `src/test/java/com/example/sessionlesson/SessionStrategyIntegrationTest.java`:

~~~java
package com.example.sessionlesson;

import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class SessionStrategyIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void builtinFormLoginRotatesIdAndSavesSecurityContext()
            throws Exception {
        MockHttpSession session = new MockHttpSession();
        String before = session.getId();

        mvc.perform(post("/login")
                    .session(session)
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "local-example-only"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/private"))
            .andExpect(authenticated().withUsername("student"));

        assertNotEquals(before, session.getId());

        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("student"));
    }

    @Test
    void customFilterAlsoRotatesIdAndPersistsContext()
            throws Exception {
        MockHttpSession session = new MockHttpSession();
        String before = session.getId();

        mvc.perform(post("/partner-login")
                    .session(session)
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "local-example-only"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/private"))
            .andExpect(authenticated().withUsername("student"));

        assertNotEquals(before, session.getId());

        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("student"));
    }

    @Test
    void secondSessionIsRejectedWhenLimitReached()
            throws Exception {
        MockHttpSession first = new MockHttpSession();
        MockHttpSession second = new MockHttpSession();
        String secondBefore = second.getId();

        mvc.perform(post("/login")
                    .session(first)
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "local-example-only"))
            .andExpect(authenticated().withUsername("student"));

        mvc.perform(post("/partner-login")
                    .session(second)
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "local-example-only"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andExpect(unauthenticated());

        assertEquals(secondBefore, second.getId());

        mvc.perform(get("/private").session(first))
            .andExpect(status().isOk())
            .andExpect(content().string("student"));
    }

    @Test
    void invalidPasswordDoesNotRotateSessionOrSaveAuthentication()
            throws Exception {
        MockHttpSession session = new MockHttpSession();
        String before = session.getId();

        mvc.perform(post("/partner-login")
                    .session(session)
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "wrong"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andExpect(unauthenticated());

        assertEquals(before, session.getId());
    }

    @Test
    void loginWithoutCsrfIsDeniedBeforeAuthentication()
            throws Exception {
        mvc.perform(post("/partner-login")
                    .param("username", "student")
                    .param("password", "local-example-only"))
            .andExpect(status().isForbidden());
    }
}
~~~

**Why is `@DirtiesContext` needed in the demo tests?** The registry tracks sessions per principal; if tests shared an application context, a login in an earlier test could leave registry entries behind and cause later tests to be rejected flakily. Using a fresh context after each test prioritizes isolation here, even though it makes the suite slower. A larger project can replace this with careful session fixture management/cleanup.

**What the assertions actually measure:**

- `authenticated()`: Spring Security produced a valid result during the request.
- `assertNotEquals(before, session.getId())`: the session existing before login changed its ID (assuming the mock request/container supports `changeSessionId()` per the demo config).
- `GET /private` in the same session: `SecurityContext` was saved and reloaded; setting only the holder without saving to the repository easily fails this check.
- Two-session test: the strategy **rejects the new login** per policy; the old session retains access.
- Wrong password: does not enter the session authentication success branch; the ID is unchanged because the provider result was invalid.
- Missing CSRF: the request is blocked before authentication; this is **not** a test verifying the session strategy.

Note that MockMvc is a simulated servlet request/session environment. In real deployments, test via HTTP/browser with `JSESSIONID` cookies, Spring Session (if used), the actual container, and the reverse proxy. Do not claim simulated tests sufficiently verify cookie domain/path/SameSite/Secure in production.

### 8.1. Separating strategy tests from HTTP filters

Beyond integration tests, a unit test suite can invoke `onAuthentication(...)` directly with `MockHttpServletRequest`, `MockHttpServletResponse`, `SessionRegistryImpl`, and a simulated authenticated `Authentication` to check delegate order, registration calls, and exception branches. However, direct tests **do not prove** the custom filter actually calls the strategy, so they cannot replace integration tests.

### 8.2. How to test that the strategy is invoked exactly once

When developing a specialized filter, you can use a test double of `SessionAuthenticationStrategy` that counts invocations; wire it into the custom filter and send a valid login POST. Expectations:

~~~text
POST login valid credentials   -> onAuthentication = 1
POST login invalid credentials -> onAuthentication = 0
GET /private from old session  -> onAuthentication = 0
~~~

Avoid calling it manually inside `attemptAuthentication` while also letting `AbstractAuthenticationProcessingFilter` call it again, which raises the count to 2. If using `AuthenticationFilter` or a custom implementation not extending `AbstractAuthenticationProcessingFilter`, check the API/lifecycle of **that exact filter** to find the invocation point.

## 9. Standalone Java 17 example: simulating order and login rejection

To clearly observe why delegate order and exceptions matter without depending on Spring, create `SessionStrategyOrderDemo.java`. This code **simulates the policy**; it does not call servlet sessions or Spring APIs directly.

~~~java
import java.util.HashSet;
import java.util.Set;

public final class SessionStrategyOrderDemo {

    private final Set<String> activeUsers = new HashSet<>();

    boolean login(String user, boolean credentialValid) {
        if (!credentialValid) {
            System.out.println("DENIED: credentials");
            return false;
        }
        if (activeUsers.contains(user)) {
            System.out.println("DENIED: concurrent session");
            return false;
        }

        System.out.println("STEP 1: concurrency allowed");
        System.out.println("STEP 2: change session id");
        activeUsers.add(user);
        System.out.println("STEP 3: register session");
        return true;
    }

    public static void main(String[] args) {
        SessionStrategyOrderDemo policy = new SessionStrategyOrderDemo();

        System.out.println("first=" + policy.login("student", true));
        System.out.println("second=" + policy.login("student", true));
        System.out.println("bad=" + policy.login("other", false));
    }
}
~~~

Run on JDK 17 or higher:

~~~bash
javac SessionStrategyOrderDemo.java
java SessionStrategyOrderDemo
~~~

**Exact** stdout:

~~~text
STEP 1: concurrency allowed
STEP 2: change session id
STEP 3: register session
first=true
DENIED: concurrent session
second=false
DENIED: credentials
bad=false
~~~

The program simulates two critical facts: invalid credentials **do not** reach the strategy, and valid credentials can still be **rejected by the concurrency policy** before changing the session ID or registering the session. The `change session id` messages are purely simulated print lines and do **not** create real HTTP sessions. To verify actual `HttpSession.changeSessionId()`, use Servlet/Spring Security tests or run against a server.

## 10. What if you do not extend AbstractAuthenticationProcessingFilter?

Some projects write a `OncePerRequestFilter` and call `AuthenticationManager.authenticate(...)` directly. When doing so, consider using a built-in authentication filter instead of managing the entire lifecycle manually. If still needed, the following **illustrative** sequence must be ensured:

~~~text
1. Match only requests that genuinely trigger login.
2. Parse input and construct an UNAUTHENTICATED Authentication token.
3. manager.authenticate(requestToken).
4. If successful:
     sessionStrategy.onAuthentication(authResult, request, response);
     create a new SecurityContext holding authResult;
     SecurityContextHolder.setContext(context);
     SecurityContextRepository.saveContext(context, request, response);
     successHandler.onAuthenticationSuccess(...).
5. If invalid credentials or strategy rejects:
     clear request context;
     failureHandler.onAuthenticationFailure(...);
     DO NOT save an authenticated result.
6. Properly clear context when request/dispatch ends.
~~~

This is an **explanatory algorithm**, not copy-pasteable code: you must handle `AuthenticationException`, CSRF, remember-me, events, IO errors, response commit, async dispatch, session fixation, session creation policy, and filter ordering. Choosing `AbstractAuthenticationProcessingFilter` avoids reimplementing delicate security logic.

**Avoid ordering bugs:**

~~~java
// ANTI-PATTERN: wrong order, do not put into production.
Authentication result = manager.authenticate(requestToken);
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(result);
repository.saveContext(context, request, response);
strategy.onAuthentication(result, request, response);
~~~

If the strategy ends up rejecting due to exceeding the session limit, `SecurityContext` has already been saved **before the policy approved it**. The risk is leaking the new authentication state into the session or a prepared response. Always invoke the strategy **before** saving the authentication result.

### Distinguishing single invocation from shared instance

An application with both built-in form login and a custom filter must simultaneously verify:

1. **When should it be called?** Only on each *new* authentication, not on every request.
2. **Which strategy is called?** Both must follow compatible session-count/fixation/CSRF policies.
3. **Is it called twice?** Do not override in the filter and also call it again in `AuthenticationSuccessHandler`.
4. **Which repository saves context?** If mechanisms use different repositories unintentionally, login succeeds yet the next request loses authentication.
5. **How are principals compared?** The registry must observe a consistent identity for the same user across both mechanisms.

## 11. Session fixation and cookie security considerations

Session fixation is not merely “swapping a random string”. A complete policy also involves:

- HTTPS for form login and all authenticated traffic.
- `Secure` cookies over HTTPS and `HttpOnly` where appropriate.
- `SameSite` tailored to the threat model and frontend/backend communication; never pick a permissive value just to “make login work” while dropping CSRF.
- Session timeout, logout invalidation, idle timeout, and renewal policies.
- Never placing session IDs in URLs or logs; prefer cookies over URL rewriting.
- Controlling session storage, session replication, and proxy stickiness in multi-node deployments.
- Preventing old session IDs from continuing to work after rotation; test both old and new cookies in realistic deployments.

**Rotating the session ID after login does not automatically provide MFA, restrict permissions, or revoke all sessions when an account is disabled.** Those are separate policies requiring active session management or account-status checks.

### When is a new session created?

A pre-login request may already have created a session for a CSRF token, request cache, view state, or another component. Therefore “not logged in yet” **does not mean** “no `HttpSession` exists yet”. Session fixation protection is especially meaningful when elevating trust from anonymous to authenticated.

Conversely, if there was no pre-login session and policy permits creating a session after login, behavior may create a new session rather than “changing an old ID”; tests must distinguish these two cases. Do not assert `oldId != newId` when `oldId` never existed.

## 12. Concurrent sessions: business decisions to clarify

### Reject new session or kick old session?

| Policy | Experience | Implementation consequence |
| --- | --- | --- |
| Prevent new login | User must log out of the previous session or wait for expiration. | Strategy can throw `SessionAuthenticationException`; registry must clean up when sessions destroy. |
| Allow new login, expire old session | User on new device gets in; previous device is cut off on its next request. | Must mark old session and ensure filter/repository handles expired sessions properly. |
| Allow multiple sessions | Convenient across multiple devices. | Requires separate count/expiry/revocation policies and auditing. |

The demo chose **prevent new login**. If business rules require “logging in on a new device automatically logs out the old device”, do not just flip a single boolean and call it done; check the expired-session filter, logout handling, and session event tracking across nodes.

### Logout, timeout, and registry cleanup

`SessionRegistryImpl` tracks sessions in a single application's memory. When a session times out or is invalidated, an event must remove its corresponding entry. `HttpSessionEventPublisher` is one way to bring servlet session lifecycle events into Spring Security. In clustered environments, use suitable infrastructure such as Spring Session or a shared registry and test consistency; per-node in-memory registries do not enforce session limits cluster-wide.

**Principal warning:** Some custom principal implementations compare by object identity instead of user ID, breaking “one session per account”. For custom `UserDetails`, define stable `equals/hashCode` based on a meaningful identifier and tenant scope without including mutable password hashes.

### Re-authenticating within the same session

A user may re-authenticate or switch identity within an existing session. Policy may need special handling for the same session ID to prevent double-counting one session or corrupting the principal. Do not assume every valid form POST means a **new** session. Check `SessionRegistry` and session strategy semantics for re-login/step-up authentication.

## 13. Stateful and stateless do not share the same assumptions

### Stateful form login

- The browser holds `JSESSIONID`.
- `SecurityContextRepository` saves/restores context across requests, typically using HTTP sessions.
- Session fixation protection and concurrent session control are meaningful.
- CSRF must be considered because browsers automatically attach cookies.
- Logout typically invalidates the session and clears context; it may clear matching tokens/cookies.

### Stateless bearer token or API key

- Clients send credentials/tokens on **every request**.
- The server does not need to create a session just to record the principal after each request.
- Use `SessionCreationPolicy.STATELESS` and compatible repository/context strategies.
- Do not use `ConcurrentSessionControlAuthenticationStrategy` to increment counters every time an API key is checked.
- Session fixation does not apply directly to requests that neither create nor maintain HTTP sessions; token security covers expiry, revocation, replay, signature/secret verification, and audience/scope policies.

Example of a separate configuration fragment for a stateless API:

~~~java
http
    .securityMatcher("/api/**")
    .sessionManagement(session -> session
        .sessionCreationPolicy(
            org.springframework.security.config.http.SessionCreationPolicy.STATELESS))
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated());
~~~

**This is only a configuration fragment**, insufficient for bearer authentication without an appropriate provider/filter, and should not be dropped directly into a session-based form-login chain. When designing a JWT resource server, use `oauth2ResourceServer(...)` and standard decoders/validators rather than fabricating principals from token regexes.

## 14. When strategies fail and how to handle it

`SessionAuthenticationStrategy` can reject after credentials have already been verified, for example:

- Session limit reached and policy blocks new logins.
- Session state is no longer valid for fixation/registration.
- Session registry backend fails, is inconsistent, or fails policy requirements.
- A custom strategy checks additional security constraints on the current session.

In those situations:

1. Do not treat “correct password” as sufficient to return an authenticated response.
2. Never write a newly authenticated `SecurityContext` **before** session policies succeed.
3. Use an appropriate failure handler/entry point returning safe messages; never leak another user's session ID.
4. Emit internal events/metrics without cookies, passwords, tokens, or hashes.
5. Define UX: inform users they need to log out of another session, provide device management, or offer reliable recovery if required.
6. Never swallow exceptions into `200 OK`/login success just to reduce error counts.

**Never catch and ignore all exceptions**:

~~~java
// ANTI-PATTERN: this bypasses the session limit constraint.
try {
    sessionStrategy.onAuthentication(auth, request, response);
} catch (Exception ignored) {
    successHandler.onAuthenticationSuccess(request, response, auth);
}
~~~

The danger here is failing open on a security control. Strategy security errors must be handled safely and monitored properly.

## 15. Common integration mistakes

| Symptom | Common cause | How to verify |
| --- | --- | --- |
| Custom login accepts password yet next request loses login | Custom filter only sets `SecurityContextHolder`, skipping `SecurityContextRepository`. | Test a protected GET with the same session after login. |
| Session ID does not rotate after custom login | Filter is not wired to / does not call `SessionAuthenticationStrategy`. | Test with a pre-login session and compare before/after IDs. |
| Form login caps at 1 session yet custom login allows unlimited | Two filters use different strategies or custom skips strategy. | Check injection and cross-test both flows. |
| Failed login still rotates session ID | Strategy invoked before credential check or on every request. | Spy `onAuthentication` call counts on success/failure paths. |
| Registry miscounts principals | Custom principal lacks stable `equals/hashCode`. | Check principal identity across two logins of the same user. |
| User logged out yet still hits session limit | Registry did not receive session-destroyed event. | Check `HttpSessionEventPublisher` listener and session store. |
| New login should evict old session yet old still works | Only marked in registry; missing expired-session request handling. | Check `ConcurrentSessionFilter`/concurrency config. |
| CSRF 403 on POST login | Missing/invalid CSRF token; test never reached auth filter. | Use `.with(csrf())` in MockMvc and inspect frontend. |
| Old CSRF token behaves unexpectedly after login | Custom composite omitted `CsrfAuthenticationStrategy` or mismatched repository. | Test token lifecycle across login. |
| Session ID rotates continuously on every GET | Strategy invoked on every request instead of per authentication. | Test single invocation and check filter placement. |
| Running stateless yet sessions appear | Another component creates sessions, request cache/form login still active, wrong repository. | Profile session creation and chain matchers. |
| Session limits fail across 2 nodes | `SessionRegistryImpl` tracks only one JVM. | Use shared session backend/registry and test cluster. |
| A filter runs twice per request | Added filter to security chain while letting Boot auto-register servlet filter bean. | Avoid `@Component` on custom filters added via `addFilterBefore`. |
| Valid role yet protected page returns 403 | Session persisted, but authorization policy denies access. | Distinguish authenticated principal from `GrantedAuthority`. |

## 16. Code review and QA checklist

- [ ] Requirements clearly specify whether this is **Servlet stateful login** or **stateless token requests**.
- [ ] There is an appropriate single point calling `SessionAuthenticationStrategy` when a new authentication succeeds.
- [ ] Strategy is not called before credential verification, not called on every request, and not duplicated in the success handler.
- [ ] Composite strategy follows **concurrency → fixation → registration** order; CSRF lifecycle is handled per policy.
- [ ] If limiting sessions, `SessionRegistry` and matching session lifecycle events/registry implementation are configured.
- [ ] Policy is explicit: reject new session or expire old session, with the corresponding branch tested.
- [ ] Session ID rotates after authentication when a pre-login session existed.
- [ ] If the strategy rejects, no authenticated context is saved and no login success is issued.
- [ ] Custom filters share or match the built-in flow's `SessionAuthenticationStrategy` and `SecurityContextRepository`.
- [ ] `SecurityContextRepository.saveContext` executes at the proper point for custom mechanisms.
- [ ] CSRF tests remain meaningful; CSRF is never disabled to dodge login form errors.
- [ ] Protected GET after POST login with the same session is tested to prove persistence.
- [ ] Two sessions from distinct browsers/devices and session expiration/logout cleanup are tested.
- [ ] `SecurityContext` is never leaked across threads/requests/async dispatches.
- [ ] `Secure`, `HttpOnly`, `SameSite` cookies, HTTPS, timeouts, and reverse proxies match the threat model.
- [ ] In multi-node deployments, concurrency policy does not rely solely on a local registry.
- [ ] Passwords, session IDs, CSRF tokens, and cookies never appear in logs or metrics.

## 17. Self-review questions

**Q1. Once `AuthenticationProvider` returns an authenticated result, is login guaranteed to succeed?** Not necessarily. `SessionAuthenticationStrategy` can still reject due to session policy; the success handler only runs after mandatory steps complete.

**Q2. What is the difference between `SessionAuthenticationStrategy` and `SecurityContextRepository`?** The strategy runs around **a new authentication event** to enforce session policies; the repository **loads/saves context** across requests. Both are needed in proper stateful flows.

**Q3. Why must session ID rotation precede session registration?** So the registry stores the final post-login ID rather than recording the pre-login ID.

**Q4. Should `onAuthentication` be called on every `GET /profile`?** No. A GET using an already authenticated session is not a new login.

**Q5. Why do custom filters in Spring Security 6 easily overlook session policies?** You cannot rely on `SessionManagementFilter` doing it automatically; a custom authentication mechanism must wire/call the strategy in its own lifecycle.

**Q6. If new logins must be rejected when one session already exists, what should be chosen?** Concurrent session strategy with max=1 and `exceptionIfMaximumExceeded=true`, tracking session cleanup via registry. In the configurer, `maxSessionsPreventsLogin(true)` expresses the same goal.

**Q7. Is `SessionRegistryImpl` sufficient to limit sessions across all cluster nodes?** No. It tracks state in one JVM's memory; a distributed session/registry solution or proper synchronization infrastructure is needed.

**Q8. Does rotating the session ID after login automatically accept wrong passwords?** No. The strategy must run **after** successful authentication and does not verify passwords.

**Q9. With a stateless JWT API, should a new session be registered on every request?** No. Stateless token validation does not carry web-session-creation semantics per request; use dedicated token policies.

**Q10. What signals should integration tests inspect?** Valid login + CSRF, post-login session ID differs from pre-login ID if a session existed, `SecurityContext` exists on subsequent requests, second login is rejected per policy, and failed login neither rotates ID nor saves context.

**Conclusion:** `SessionAuthenticationStrategy` bridges **newly succeeded authentication** and **HTTP session policies**. With Spring Security's standard mechanisms, use configurers so the framework wires the proper flow; with custom mechanisms, integrate the strategy and context repository **deliberately, in the right order, and exactly once**, then test both session state and security behavior.
