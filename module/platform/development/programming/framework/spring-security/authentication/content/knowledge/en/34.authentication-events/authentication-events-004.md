# Distinguishing Authentication Success Events from a Completed Login Flow

In Spring Security, **verifying authentication credentials successfully** and **a user completing the entire login journey** are two distinct milestones. An `AuthenticationSuccessEvent` may already be published when `AuthenticationManager` returns a valid `Authentication`, yet the system can still fail afterwards when handling the login session, saving `SecurityContext`, performing redirects, verifying a second factor, setting cookies, or accessing the protected resource.

Therefore, the following statements are **not equivalent**:

- "The password was verified correctly by `AuthenticationProvider`."
- "Spring Security published `AuthenticationSuccessEvent`."
- "The interactive login filter published `InteractiveAuthenticationSuccessEvent`."
- "`AuthenticationSuccessHandler` began executing."
- "The HTTP response issued a redirect or returned a token to the client."
- "The browser received the cookie, followed the redirect, sent the next request, and was authorized to access the resource."
- "The user satisfied all MFA policies, authorization checks, and application onboarding steps."

This lesson belongs to the **Authentication Events** group in **Spring Security - authentication**, focusing on **event semantics**, **the Servlet form login lifecycle order**, **which milestones can be used for auditing/metrics**, **partial-success scenarios**, and **end-to-end testing**. Code examples use **Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x (Servlet/MVC)**; differences for stateless JWT, OAuth2/OIDC, WebFlux, or MFA flows are noted explicitly.

## 1. The word "success" must always specify *success at which step*

Suppose a user requests `/private`:

1. The browser has no session, so it is redirected to the login page.
2. The user submits username/password to `POST /login`.
3. `AuthenticationManager` verifies the credentials; this is **authentication success**, but not necessarily **login journey complete**.
4. The filter handles session fixation, concurrent session limits, saving `SecurityContext`, remember-me, and the success handler.
5. The server returns 302; the browser receives the cookie/redirect and requests `/private` again.
6. Authorization checks permissions; the controller returns 200.
7. If the application requires MFA, terms acceptance, tenant selection, or onboarding, those steps must also be satisfied per policy.

Milestone distinction table:

| Milestone | Mechanism / signal | What is known | What is **not** yet known |
| --- | --- | --- | --- |
| **A — Credential verified** | `AuthenticationManager.authenticate(...)` returns a valid `Authentication`; `AuthenticationSuccessEvent` may appear | Provider accepted this specific authentication attempt | Was the session saved? MFA? HTTP response? |
| **B — Web authentication prepared** | `SessionAuthenticationStrategy` and `SecurityContextRepository` executed successfully in supporting flows | Current filter's session/context persistence steps ran | Did the browser receive the cookie? Did the handler/redirect fail? |
| **C — Interactive filter success** | `InteractiveAuthenticationSuccessEvent` inside `AbstractAuthenticationProcessingFilter` | The interactive filter reached its event emission step | Did the success handler finish? Did the browser reach the target page? |
| **D — Login response issued** | `AuthenticationSuccessHandler` executed the redirect/response successfully | The server attempted to advance the client to the next step | Did the client receive/keep the cookie? Follow the redirect? Have permission to access? |
| **E — Protected access observed** | Follow-up request restores context and protected resource succeeds | User/agent is authorized for **this specific request** | Does not prove all future requests will remain valid |
| **F — Business login complete** | Application-defined criteria, e.g., MFA/terms/tenant/session completed | The **application's** journey criteria are met | Does not imply all subsequent business operations will succeed |

There is no universal **`LoginCompletedEvent`** automatically emitted by Spring Security for every authentication method and business policy. If your system needs a "user completed login" event for analytics or billing/entitlement triggers, **define the business contract and confirmation point explicitly**; do not rename `AuthenticationSuccessEvent` to "LOGIN_COMPLETED" and misinterpret it.

## 2. Two success event types in Spring Security

### 2.1. AuthenticationSuccessEvent

`org.springframework.security.authentication.event.AuthenticationSuccessEvent` is an application event indicating that an authentication attempt **succeeded at the AuthenticationManager/provider layer** when a publisher is configured and that path emits events.

Related components:

- `AuthenticationManager` defines the `authenticate(Authentication)` operation.
- `ProviderManager` is the common implementation, delegating sequentially to `AuthenticationProvider` instances.
- `AuthenticationEventPublisher` is the event publishing contract.
- `DefaultAuthenticationEventPublisher` publishes `AuthenticationSuccessEvent` when authentication is accepted and maps failure exceptions to failure events.
- `@EventListener` in Spring receives events to write audits or metrics.

Example snippet inside a Spring `@Configuration` class:

~~~java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher publisher) {
    return new DefaultAuthenticationEventPublisher(publisher);
}
~~~

Required imports:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
~~~

In a typical Spring Boot application, a publisher may already be created via auto-configuration; declaring the bean explicitly above makes the example clear, though before going to production you should inspect existing beans to avoid duplicate configuration.

**Limitation:** a manually constructed `ProviderManager` without an `AuthenticationEventPublisher` uses a default publisher that *emits nothing*. Thus "no event seen" **does not prove** authentication failed; likewise "event seen" **does not prove** the user is fully logged into the browser.

A direct call to `AuthenticationManager.authenticate` from a service/CLI/background job can succeed and publish an event even when **there is no HTTP request, cookie, session-stored SecurityContext, or redirect**. Conversely, another mechanism may establish Authentication without emitting this exact event type due to a different setup/publisher.

### 2.2. InteractiveAuthenticationSuccessEvent

`org.springframework.security.authentication.event.InteractiveAuthenticationSuccessEvent` is an event in the **interactive login** branch, emitted by `AbstractAuthenticationProcessingFilter` inside `successfulAuthentication(...)`. It exposes `getGeneratedBy()` to identify the filter class that generated the event.

Per Spring Security 6.5 Javadoc, after the filter obtains an authentication result and runs the session strategy:

1. Sets `Authentication` into `SecurityContextHolder`.
2. With an appropriately configured security context repository, saves `SecurityContext` so it can be restored on future requests.
3. Notifies `RememberMeServices.loginSuccess` if applicable.
4. Publishes `InteractiveAuthenticationSuccessEvent`.
5. Invokes `AuthenticationSuccessHandler` to issue the redirect or HTTP response.

**Consequence:** when listening to `InteractiveAuthenticationSuccessEvent`, you **still cannot guarantee** that the success handler sent the response cleanly, the user received the cookie, or they are authorized on the next page. It is simply a later milestone in that **specific interactive filter flow** than the AuthenticationManager event.

Important: `InteractiveAuthenticationSuccessEvent` **does not extend** `AuthenticationSuccessEvent`. Javadoc intentionally keeps them as two distinct classes so an `AuthenticationSuccessEvent` listener does not receive duplicates via inheritance. To listen for both, register listeners for both; **never sum the two events into two user logins**.

### 2.3. AuthenticationSuccessHandler is not an event

`org.springframework.security.web.authentication.AuthenticationSuccessHandler` is an **HTTP processing callback** receiving `HttpServletRequest`, `HttpServletResponse`, and `Authentication`. It typically redirects to a saved request or default URL.

`SavedRequestAwareAuthenticationSuccessHandler` can use `RequestCache` to return to the URL the user requested prior to login. `SimpleUrlAuthenticationSuccessHandler` redirects to a configured URL.

Key differences:

- `AuthenticationSuccessEvent`: **authentication manager** event, independent of the Servlet API.
- `InteractiveAuthenticationSuccessEvent`: **interactive filter** event.
- `AuthenticationSuccessHandler`: callback **controlling the HTTP response**; do not treat "callback invoked" as proof that the browser followed the redirect.
- Target page controller: confirms a specific protected request passed authorization; it does not emit a default built-in event named "login completed."

If you replace the success handler with a lambda and forget to invoke the default redirect handler, the system may authenticate successfully yet leave the browser with nowhere to go—or even leave the HTTP response in an unintended state. Hence, a custom success handler must handle the response **accurately and completely**.

## 3. Standard order of form login (Servlet) in Spring Security 6.5

Diagram illustrating **a typical `POST /login`** through `UsernamePasswordAuthenticationFilter` (subclass of `AbstractAuthenticationProcessingFilter`):

~~~text
Browser                       Spring Security
   │
   ├── GET /private ──────────────► authorization requires login
   ◄── redirect /login ──────────┤
   │
   ├── POST /login + CSRF ───────► UsernamePasswordAuthenticationFilter
   │                                      │
   │                                      ▼
   │                              AuthenticationManager
   │                                      │
   │                              AuthenticationProvider
   │                                      │ correct password
   │                                      ▼
   │                          [AuthenticationSuccessEvent]  ── A
   │                                      │
   │                                      ▼
   │                           SessionAuthenticationStrategy
   │                         (fixation, max sessions, policy)
   │                                      │ can fail
   │                                      ▼
   │                             SecurityContextHolder
   │                                      │
   │                             SecurityContextRepository
   │                                      │ save context
   │                                      ▼
   │                             RememberMeServices (if enabled)
   │                                      │
   │                     [InteractiveAuthenticationSuccessEvent] ── C
   │                                      │
   │                                      ▼
   │                           AuthenticationSuccessHandler ── D
   ◄── 302 /private + cookie ─────────────┤
   │
   ├── GET /private + cookie ─────► context restored / authorization
   ◄── 200 page content ──────────┤                           ── E
~~~

**Notes on the diagram:**

- `AuthenticationSuccessEvent` is emitted by the **publisher** in the `AuthenticationManager` branch; if no publisher is configured, no event appears. Do not assume every custom `AuthenticationProvider` uses the same publisher.
- `SessionAuthenticationStrategy` is invoked immediately after authentication succeeds in `AbstractAuthenticationProcessingFilter` and **can reject** the session by policy. This is a crucial case: **A succeeded, yet C/D/E never occurred**.
- `SecurityContextHolder` is the current thread's context, **not** a guarantee that the session will persist into the next request. Cross-request persistence depends on `SecurityContextRepository`, session policy, cookies, and filters.
- `InteractiveAuthenticationSuccessEvent` is emitted **before** the default filter's `AuthenticationSuccessHandler`.
- After the server sends 302, the browser might not store the cookie, might not follow the redirect, might hit a network error, or might receive `AccessDeniedException` on the target page. Thus 302 and 200 must be observed separately.
- A default application event listener runs **synchronously** under the default publisher/multicaster, though an app may configure async execution; do not rely on log timestamp ordering to infer a permanent universal order across all deployments.

### 3.1. If SessionAuthenticationStrategy rejects

Suppose an application limits concurrent sessions, uses session fixation protection, and configures a custom session strategy. `AuthenticationManager` just verified the username/password; `AuthenticationSuccessEvent` was published. Then `SessionAuthenticationStrategy` throws `SessionAuthenticationException`, causing the filter to take the failure branch and display a login error instead of a success response.

Audit classification should reflect:

~~~text
authentication.check=ACCEPTED
login.session_policy=REJECTED
login.response=FAILURE
login.completed=false
~~~

The four lines above are an **interpretive model** of milestones, not keys automatically emitted by Spring. Counting `AuthenticationSuccessEvent` alone as completed logins would **overcount** in this scenario.

### 3.2. If the success handler fails

A success handler can:

- Attempt to redirect to an invalid or disallowed URL.
- Call an external service that times out or throws an exception.
- Write to the response twice.
- Forget to send 200/302 to the client.
- Use a stale saved request or OAuth2 state.

Even when events A and C have fired, an error in handler D can prevent the user from completing the flow. Furthermore, **SecurityContext may already have been saved** before the handler error. If policy requires rollback or logout when a handler fails, design it explicitly rather than expecting events to revoke the session.

### 3.3. If the user never reaches the target page

HTTP 302 is an **instruction to the client**. The browser may block cookies, the cookie may have mismatched `SameSite/Secure/Domain/Path`, the session repository may not be shared across replicas, or a proxy may return 502. A redirected request can still:

- Bounce back to `/login` because `SecurityContext` could not be restored.
- Receive HTTP 403 due to missing authority.
- Receive an MFA/step-up challenge.
- Receive 404/500 from the application even while authenticated.
- Be abandoned when the user closes the tab before following the redirect.

Therefore, if your goal is to measure **login reaching a usable state**, observe the **subsequent protected request** or an application-defined checkpoint, rather than counting only provider-level events.

## 4. Does an event confirm login when calling AuthenticationManager directly?

No. Here is an **illustrative Java snippet inside a service injected with `AuthenticationManager`**, not a standalone class:

~~~java
Authentication verified = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, rawPassword));
~~~

Relevant imports are `org.springframework.security.authentication.AuthenticationManager`, `org.springframework.security.authentication.UsernamePasswordAuthenticationToken`, and `org.springframework.security.core.Authentication`.

If the provider accepts, `verified.isAuthenticated()` may be `true` and an `AuthenticationSuccessEvent` may be emitted. However:

- The code has not decided whether `SecurityContextHolder` holds the new authentication.
- It has not invoked an HTTP filter's `SessionAuthenticationStrategy`.
- It has not saved `SecurityContext` into `SecurityContextRepository`.
- It has not set cookies, redirected, or issued access tokens.
- It has not checked MFA/authorization for subsequent resources.

If you build a custom REST login controller that only calls `authenticate(...)` and returns HTTP 200 "login succeeded," you have **not built a complete login mechanism**. In Spring Security 6, when creating a `SecurityContext` manually that must be restored on future requests, you must save it via the appropriate `SecurityContextRepository.saveContext(context, request, response)`; you must also apply session strategy, CSRF, cookies, session fixation, and relevant authentication policies. Never copy a bare `SecurityContextHolder.setContext(...)` snippet and treat it as a complete solution.

## 5. Different authentication flows have different meanings of "completed"

### 5.1. Session-based form login

A practical set of criteria is:

1. User completes credentials/MFA per policy.
2. Session/context has been processed and is restorable.
3. Login response was sent properly.
4. Follow-up request carries the valid cookie and is accepted by `AuthorizationFilter` at the target URL.

With form login, the success handler performs the HTTP redirect/forward. Yet it does not know whether the user actually followed the redirect, and a session could expire immediately afterward.

### 5.2. OAuth2 Login / OIDC

There can be multiple milestones: redirecting to the authorization server, receiving the authorization code, exchanging the code for tokens, verifying OIDC ID token/userinfo, creating a local principal, saving the session, redirecting to the original URL, and authorization. **Credential verification at the IdP** does not prove the RP application completed the callback and established a session.

**Do not treat one side's `AuthenticationSuccessEvent` as automatic proof of the entire cross-system journey.** Different filter/publisher implementations may or may not emit similar events; always verify your exact version and integration behavior.

### 5.3. JWT Bearer / stateless APIs

A Resource Server can **verify a Bearer token on every request**, build a valid `JwtAuthenticationToken`, and enforce authorization. This is not a session-and-redirect browser login flow. If the authentication manager's publisher emits `AuthenticationSuccessEvent`, the event count can approximate the **number of authenticated requests**, not "number of user logins."

Therefore:

~~~text
100 successful Bearer token verifications
       != 100 new user logins
       != 100 browser sessions
~~~

Never build "login success count" analytics solely from this event in a stateless API. To measure token issuance/logins at the authorization server, collect events from the actual OAuth2 grant/authorization flow and verify responses, rather than resource-server per-request token checks.

### 5.4. HTTP Basic, X.509, pre-authentication, remember-me

These mechanisms can establish `Authentication` on a request **without an interactive login form**. Several paths do not use `AbstractAuthenticationProcessingFilter`, so they **do not emit `InteractiveAuthenticationSuccessEvent` the way form login does**. Never conclude "no interactive event means unauthenticated."

### 5.5. MFA and step-up

If policy requires password + OTP/passkey or additional conditions, **passing the password step** is insufficient. Even when the current `Authentication` has `isAuthenticated()=true`, an endpoint may still require additional authorities/factors and block or redirect to the next step.

Example scenario:

~~~text
Password factor succeeded
    │
    ├─ AuthenticationSuccessEvent (depends on path)
    │
    ▼
MFA challenge required
    │
    ├─ User abandons                 -> business login incomplete
    ├─ Wrong OTP/passkey            -> business login incomplete
    └─ Valid second factor
           │
           ▼
  Policy required factors satisfied
           │
           ▼
  Authorized access to intended resource
~~~

Do not assume `AuthenticationSuccessEvent` guarantees two factors are done. If using MFA features of a newer Spring Security version, check authorities and authorization rules for **that exact version**; do not copy 7.x documentation APIs into a 6.5 project without verifying.

## 6. Spring Boot 3.5 / Spring Security 6.5 example: listening to events and handling the success handler

The following Servlet demo distinguishes **three observation points**:

- `AuthenticationSuccessEvent`: provider/manager accepted.
- `InteractiveAuthenticationSuccessEvent`: interactive filter reported success.
- `AuthenticationSuccessHandler`: handler began redirecting.

It **intentionally does not log "LOGIN_COMPLETED"** because the browser request after redirect has not yet been observed. The `/private` endpoint illustrates that next step. The project uses Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, and a test password supplied via environment variable rather than a production secret.

### 6.1. Dependencies

In `build.gradle` (Groovy DSL) of a Spring Boot project whose versions are managed by the plugin/BOM:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Starter Security brings in the required modules for form login, ProviderManager, and auth events. An OAuth2 starter is unnecessary for a password-login example.

### 6.2. Environment configuration

File `src/main/resources/application.properties`:

~~~properties
# Test-only secret provided by the runner outside source code.
demo.password=${DEMO_PASSWORD}

# Do not enable request logging containing usernames/passwords.
spring.mvc.log-request-details=false
logging.level.org.springframework.security=INFO
~~~

Locally, supply `DEMO_PASSWORD` via your environment/IDE/secret manager. Never place real passwords in source code, exercises, shell history, or CI logs.

### 6.3. Complete Java code

File `src/main/java/example/loginstages/LoginStagesApplication.java`:

~~~java
package example.loginstages;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.authentication.event.InteractiveAuthenticationSuccessEvent;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationSuccessHandler;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LoginStagesApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginStagesApplication.class, args);
    }
}

enum LoginMilestone {
    PROVIDER_ACCEPTED,
    INTERACTIVE_FILTER_SUCCEEDED,
    SUCCESS_HANDLER_ENTERED
}

@Component
class LoginJourneyAudit {
    private static final Logger LOG =
            LoggerFactory.getLogger(LoginJourneyAudit.class);

    @EventListener
    public void authenticationAccepted(AuthenticationSuccessEvent ignored) {
        record(LoginMilestone.PROVIDER_ACCEPTED);
    }

    @EventListener
    public void interactiveAccepted(
            InteractiveAuthenticationSuccessEvent ignored) {
        record(LoginMilestone.INTERACTIVE_FILTER_SUCCEEDED);
    }

    void record(LoginMilestone milestone) {
        // Do not log password, session ID, JWT, Authentication, or token.
        LOG.info("authentication_stage={}", milestone.name());
    }
}

@Configuration(proxyBeanMethods = false)
class LoginSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.password}") String rawLabPassword) {
        UserDetails student = User.withUsername("student")
                .password(encoder.encode(rawLabPassword))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(student);
    }

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher applicationEvents) {
        return new DefaultAuthenticationEventPublisher(applicationEvents);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            LoginJourneyAudit audit) throws Exception {

        SimpleUrlAuthenticationSuccessHandler redirect =
                new SimpleUrlAuthenticationSuccessHandler("/private");

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/private").authenticated()
                .anyRequest().permitAll());

        http.formLogin(form -> form
                .successHandler((request, response, authentication) -> {
                    audit.record(LoginMilestone.SUCCESS_HANDLER_ENTERED);
                    redirect.onAuthenticationSuccess(
                            request, response, authentication);
                })
                .permitAll());

        // Do not disable CSRF; form login uses a CSRF token by default.
        return http.build();
    }
}

@RestController
class PrivatePage {
    @GetMapping("/private")
    String privatePage(Authentication authentication) {
        // This endpoint proves the current request passed authorization.
        return "private:" + authentication.getName();
    }
}
~~~

**API QA and significance:**

1. `DefaultAuthenticationEventPublisher` takes `ApplicationEventPublisher`, not a custom `ApplicationEventMulticaster`. It emits events when the corresponding manager invokes the publisher.
2. `AuthenticationSuccessEvent` and `InteractiveAuthenticationSuccessEvent` belong to `org.springframework.security.authentication.event` and are **two distinct event classes**.
3. Event listeners log **only the milestone enum**. They never log `event.getAuthentication()`, principal, credentials, request body, cookies, or session IDs.
4. `SimpleUrlAuthenticationSuccessHandler("/private")` handles the actual redirect; the lambda wrapper simply adds an observation point and **delegates** to the standard handler without forgetting to write the response.
5. `SecurityFilterChain` requires authentication for `/private`; other endpoints are public to keep the example simple. Never use these sample authorization rules in production with sensitive endpoints.
6. `InMemoryUserDetailsManager` holds a lab account with its password from an environment variable. Production apps require persistent account storage, MFA, rate limiting, HTTPS, session/cookie policies, and access-controlled auth auditing.
7. There is no `audit.record(LOGIN_COMPLETED)` call inside the success handler: because a server-issued redirect **does not prove the browser reached the target page**.

**Logging rule:** Spring Security may erase credentials after authentication, but that does not make `Authentication` "safe to log" across all implementations. Even `toString()` on a custom principal may expose private information.

### 6.4. Running and observing

In a project with the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows use `gradlew.bat bootRun`. Open `http://localhost:8080/private` in a browser while unauthenticated; Spring Security redirects to `/login`. Enter the lab user `student` and the lab password supplied in `DEMO_PASSWORD`.

With the corresponding publisher, filter, and handler setup, the application logs stages like:

~~~text
authentication_stage=PROVIDER_ACCEPTED
authentication_stage=INTERACTIVE_FILTER_SUCCEEDED
authentication_stage=SUCCESS_HANDLER_ENTERED
~~~

These three lines are an **illustrative ordering for a standard synchronous flow**, not fixed stdout; the logger may prepend timestamps and thread names. If the multicaster is configured asynchronously or multiple authentication flows run, interpret ordering and counts via correlation IDs rather than line position in the log file.

After following the redirect, the browser opens `/private` and receives the body:

~~~text
private:student
~~~

If the user closes the tab before following the redirect or the session cookie is not sent on the next request, **the server-side events may still have fired**, while the `private:student` body is never received by that browser.

**Never use an event listener to directly call external billing, permanently grant roles, or mark a transaction complete** as soon as a provider verifies a password. Sensitive business actions must depend on the actual final state with proper idempotency and transactional safeguards per policy.

## 7. Real HTTP testing: events + redirect + session on subsequent request

To prove each milestone, test:

1. An unauthenticated request cannot enter `/private`.
2. Submitting `POST /login` with CSRF and the right password: provider/filter emit events and the handler issues a redirect.
3. Using the **same session**, make a new request to `/private`.
4. Ensure the controller is reached with the expected principal; this is the **post-redirect observation milestone**, stronger than checking events alone.
5. Test wrong password, missing CSRF, lost session, and other MFA/authorization flows.

### 7.1. Spring Boot/JUnit/MockMvc test with ApplicationEvents

File `src/test/java/example/loginstages/LoginStagesApplicationTest.java`:

~~~java
package example.loginstages;

import jakarta.servlet.http.HttpSession;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.authentication.event.InteractiveAuthenticationSuccessEvent;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = "demo.password=lab-password-only-for-tests")
@AutoConfigureMockMvc
@RecordApplicationEvents
class LoginStagesApplicationTest {

    @Autowired MockMvc mvc;
    @Autowired ApplicationEvents recordedEvents;

    @Test
    void eventsExistButNextRequestIsTheSessionProof()
            throws Exception {

        MvcResult loginResult = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "lab-password-only-for-tests"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/private"))
            .andReturn();

        // Evidence that the provider/manager accepted.
        assertTrue(recordedEvents.stream(AuthenticationSuccessEvent.class)
                .anyMatch(e ->
                        "student".equals(e.getAuthentication().getName())));

        // Evidence that the interactive filter published its event.
        assertTrue(recordedEvents.stream(
                        InteractiveAuthenticationSuccessEvent.class)
                .anyMatch(e ->
                        "student".equals(e.getAuthentication().getName())));

        // The redirect response is only an HTTP milestone.
        // The same session must be used in another request to verify further.
        HttpSession session = loginResult.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/private").session((MockHttpSession) session))
            .andExpect(status().isOk())
            .andExpect(content().string("private:student"));
    }

    @Test
    void badCredentialsDoNotCompleteLogin()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "student")
                .param("password", "wrong-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void missingCsrfDoesNotCompleteLogin()
            throws Exception {
        mvc.perform(post("/login")
                .param("username", "student")
                .param("password", "lab-password-only-for-tests"))
            .andExpect(status().isForbidden());
    }
}
~~~

Run in the Gradle project:

~~~bash
./gradlew test \
  --tests example.loginstages.LoginStagesApplicationTest
~~~

Expected result: **3 tests pass** when dependencies and configuration are correct. The first test proves **events are not equated with redirects or sessions**: it verifies each milestone and finally accesses the protected endpoint using the same session.

**Limitation of MockMvc:** this tests the Spring HTTP filter chain using mock servlet requests/responses; it does not verify that a real browser stored cookies, SameSite/Secure behavior outside the test harness, DNS, reverse proxies, distributed sessions, or network errors. Thus, real E2E browser tests in an integration environment are still necessary.

### 7.2. Additional tests in staging

| Test ID | Simulation | Expected evidence |
| --- | --- | --- |
| L01 | Wrong password | No successful authentication, login fails |
| L02 | Right password, missing CSRF | Request blocked prior to login, no valid new session created |
| L03 | Right password, session strategy rejects due to max sessions | Manager success event may appear, but redirect does not succeed |
| L04 | Right password, success handler throws controlled error | Upstream events may have fired, client does not complete login |
| L05 | 302 response, browser does not accept/store cookie | Follow-up `/private` request requires login again |
| L06 | 302 response, browser holds cookie | Follow-up protected request receives matching Authentication |
| L07 | User authenticated but lacks `ROLE_ADMIN` | Login may succeed, yet `/admin` returns 403 |
| L08 | MFA required, password right, no OTP yet | Full-login access not granted; proceed to second step |
| L09 | Bearer API receives 100 calls with same access token | Not reported as 100 new user logins |
| L10 | OAuth2 IdP authenticates user, RP callback fails | RP login is not considered complete |
| L11 | Session repository fails or cluster does not share state | User gets login response, yet next request is unauthenticated |
| L12 | User opens multiple tabs, redirect abandoned | Server milestones exist, no browser completion |
| L13 | AuthenticationManager invoked from background service | AuthenticationSuccessEvent may appear without interactive login |
| L14 | Both parent ProviderManager and child publisher emit | Duplicate events detected, not counted as two logins |
| L15 | App multicaster handles events asynchronously | Do not rely on log line ordering |
| L16 | Audit logger accidentally prints Authentication/credentials | Caught in code review / canary tests |
| L17 | Server issues redirect to unintended URL | Not treated as journey success; prevent open redirects |
| L18 | Login from disabled/locked account | No usable authenticated session created |
| L19 | MFA succeeds, yet user lacks resource permission | Full factor satisfaction does not replace role/authorization |
| L20 | Logout/session expiry after login | Do not assume past success event guarantees current access |

**Important QA note:** HTTP status codes and event types must be interpreted per mechanism. A bearer API may return 401/403, form login may redirect with 302/303, and an SPA may return JSON; never hardcode an expectation that "every valid login returns HTTP 200 directly on POST /login."

## 8. Designing audits and metrics without miscounting

### 8.1. Do not derive loginSuccessCount solely from AuthenticationSuccessEvent

A common flawed dashboard pattern:

~~~java
@EventListener
public void onSuccess(AuthenticationSuccessEvent event) {
    metrics.increment("login_completed");
}
~~~

The snippet above is **semantically wrong** because the event could come from API/token verification, occur before the session strategy, or stem from a service invoking the manager directly. Never name the metric `"login_completed"` here.

You can stratify metrics into layers:

| Metric or audit event | Appropriate source | Semantics |
| --- | --- | --- |
| `authentication_attempt_accepted` | Authentication manager publisher | An authentication attempt was accepted by the manager |
| `interactive_login_filter_succeeded` | Interactive filter event | An interactive filter reached its success event milestone |
| `login_response_issued` | HTTP success handler/response observation | Server emitted the login response per contract |
| `login_session_usable` | Protected request with restored context | User has a usable session for that request |
| `mfa_policy_satisfied` | Application policy engine/MFA workflow | Context-required factors are satisfied |
| `login_journey_completed` | **Dedicated business contract** | Product-defined "complete" milestones were reached |

The names above are **application-chosen examples**, not built-in Spring Security constants/events. Include allowlisted fields `stage`, `flow_id` (random, never session/token), `outcome`, and `method`. Restrict usernames/emails and PII in metrics to avoid high cardinality and privacy risks.

### 8.2. Correlation ID is not a session ID

Across multiple steps/redirects, linking events in a "login journey" requires a correlation ID. Note:

- Never log raw `JSESSIONID`, access/refresh tokens, passwords, OTPs, authorization codes, or recovery codes.
- Use a server-issued **random flow ID**; store it in the session or signed/tamper-resistant state if the flow crosses redirects.
- Never take raw `X-Request-ID` from callers as trusted or log it verbatim; validate/normalize or generate a new one.
- A flow ID spanning requests can correlate user behavior, so apply retention and access policies.
- Attaching roles/usernames/tenants to a flow requires care against PII leaks; audits may use an access-controlled internal account ID, whereas public metrics must not.

If using Kafka/queues/event buses, each event should carry its own `event_id` for idempotency; `flow_id` is for correlation, not proof of authentication.

### 8.3. Events are not exactly-once transactions

Spring application events do not guarantee:

- Durability across process crashes.
- Exactly-once delivery on retries or across multiple ProviderManagers.
- Database transaction commit.
- Downstream consumer completion.
- Browser receipt of the response.

If you need an "account first login completed" event to trigger provisioning, consider the **transactional outbox** pattern or committing business state first and emitting an event with idempotency/unique constraints. Do not slap `@Async @EventListener` on a method and assume it provides retries, durable queues, and exactly-once guarantees. Every business side effect must consider rollback and race conditions separately.

### 8.4. What if a listener throws an exception?

With the default synchronous multicaster, an `@EventListener` performing I/O and throwing an unchecked exception can immediately disrupt the thread handling authentication. Switching listeners to async alters impact and ordering, requiring explicit reliability and error-monitoring design. Keep listeners lightweight and avoid synchronous network API calls on the login path. If auditing is mandatory, define persistence and failure policies clearly — never assume logging inside a listener equals a committed transaction.

## 9. Differences between authentication, authorization, session, and login UX

### 9.1. Authentication: who are you?

`Authentication` in Spring Security carries principal, authorities, authentication state, and depending on the implementation, credentials/details. `authentication.isAuthenticated()` indicates the state of the token/authentication object **per its implementation contract**, not that every application policy is complete. Never serialize the full `Authentication` into logs or HTTP responses.

### 9.2. Authorization: what are you allowed to do?

After login, authorization can return 403 because the user lacks `ROLE_ADMIN` or `SCOPE_X`. Getting a 403 at `/admin` does not invalidate the earlier `AuthenticationSuccessEvent` at login; it simply indicates credentials were accepted while the user lacks permission for that request.

Example:

~~~text
Authentication success: user=student, authorities=[ROLE_USER]
GET /profile           -> 200
GET /admin              -> 403 (missing ROLE_ADMIN)
~~~

These lines are a **conceptual model**, not fixed output across all apps. Never use the boolean `isAuthenticated()` as a substitute for `hasRole/hasAuthority` or MFA rules.

### 9.3. Session: cross-request state

In Spring Security 6.x, `SecurityContextHolderFilter` loads context from `SecurityContextRepository`; if custom code authenticates outside standard filters, **explicit save** is required so the context can be restored on subsequent requests. Calling `SecurityContextHolder.setContext` on the current thread alone is not enough to create durable login state.

With `SessionCreationPolicy.STATELESS`, do not expect Spring to create a browser session. With `IF_REQUIRED`/default form login, a properly configured session repository restores context. Production also requires verifying:

- Session fixation protection.
- Max concurrent sessions / expired sessions.
- Cookie attributes: `Secure`, `HttpOnly`, `SameSite`, Domain/Path.
- Reverse proxy HTTPS, stickiness, or shared session store across replicas.
- Timeout/logout/session invalidation.
- Session persistence when context is updated or privileges change.

### 9.4. UX: redirects and whether the user actually reached the destination

HTTP 302 is generated by the server before the browser sends the next request. A system can measure:

- **Login response issued**: server generated the response.
- **Navigation observed**: browser reached the post-login route.
- **Protected resource served**: an endpoint served a protected result.

All three have distinct meanings. For SPAs, the login response may return JSON while the client navigates itself, so `AuthenticationSuccessHandler` in a Spring MVC form login cannot serve as proof of an SPA's client-side flow. Design telemetry with appropriate privacy/consent instead of dragging passwords or cookies into analytics.

## 10. Common implementation pitfalls

| Mistake | Why it is wrong | Correct approach |
| --- | --- | --- |
| Treating `AuthenticationSuccessEvent` as "login completed" | Event can occur before session strategy, response, and MFA | Name metric `AUTHENTICATION_ACCEPTED`; define completion separately |
| Summing `AuthenticationSuccessEvent` + `InteractiveAuthenticationSuccessEvent` | Both events can fire during a single login | Treat each event as a **milestone**, not a unique user |
| Assuming success handler start means the browser is logged in | Redirect/cookie can still fail | Verify response and follow-up protected request |
| Treating 302 as a login error because it is not 200 | Form login normally redirects | Test per form-login protocol and UX |
| Testing only `AuthenticationManager.authenticate` | Skips session, filter, CSRF, and redirect checks | Add MockMvc/E2E tests |
| Calling `SecurityContextHolder.setContext` in a controller and returning 200 | Does not guarantee saving via `SecurityContextRepository` | Use standard mechanisms or run full persistence/session flow |
| Confusing `isAuthenticated()` with having required roles | User may lack authorities or MFA | Enforce `AuthorizationManager`/policy |
| Counting JWT success events as browser logins | Bearer tokens may be verified on every request | Track grants/logins at the proper system |
| Letting audit listeners throw exceptions | Can break login or leave partial state | Keep listeners light, set clear failure policy, use outbox if needed |
| Printing full `Authentication`/`SecurityContext` to logs | May expose credentials/session/PII | Log safe event enums/outcomes and audit IDs |
| Assuming every mechanism emits the same events | Publishers/filters differ | Verify mechanism/version with real tests |
| Omitting `.with(csrf())` from MockMvc POST /login | Request blocked by CSRF before authentication | Test with a valid CSRF token |
| Updating DB `last-login` immediately on "auth success" | Login/session/required factors may not be done yet | Pick the proper business milestone and ensure idempotency |
| Using events to open caller-supplied redirect URLs | Risks open redirect or context leakage | Allowlist safe redirects and enforce URL policy |
| Treating a missing interactive event as login failure | JWT/Basic/pre-auth do not necessarily use interactive filters | Attach audits to the actual authentication path |

## 11. Acceptance and operational workflow

### 11.1. Layered acceptance criteria

Before signing off on a "login complete" feature, QA should ask:

1. **Authentication:** which user/credential did `AuthenticationManager/AuthenticationProvider` accept?
2. **Policy:** have MFA, account status, tenant, session limits, and mandatory checks finished?
3. **Context:** was context persisted properly and restored on subsequent requests?
4. **Response:** did the server produce the response/redirect/token issuance per contract?
5. **Client:** does the browser send the cookie/token, follow redirects cleanly, and avoid loops?
6. **Authorization:** is the intended protected request permitted?
7. **Audit:** do logs/metrics reflect the exact stage without double-counting or leaking secrets?
8. **Failure:** if a milestone after credential success fails, is there proper handling and diagnostic state?

### 11.2. Implementation checklist

- [ ] Distinguish `AuthenticationSuccessEvent`, `InteractiveAuthenticationSuccessEvent`, and `AuthenticationSuccessHandler`.
- [ ] Verify `AuthenticationEventPublisher` is configured if manager events are needed.
- [ ] Never use manager-level events to confirm session/MFA/redirect/client completion.
- [ ] Account for `SessionAuthenticationStrategy` rejecting after authentication success.
- [ ] Maintain proper `SecurityContextRepository` and explicit save when building custom flows.
- [ ] Test `POST /login` with CSRF, 302, and follow-up request with session/cookie.
- [ ] Test authorization on the target resource, not just `Authentication.isAuthenticated()`.
- [ ] Test failed session restoration, failing handlers, abandoned MFA, and broken redirects.
- [ ] For JWT/OAuth2/APIs, define "login" by grant/client flow rather than per-JWT verification.
- [ ] Ensure metrics/audits use stage-specific event names, correlation IDs, idempotency, and privacy policies.
- [ ] Never log plaintext credentials, full principal/Authentication objects, session IDs, tokens, or authorization codes.
- [ ] Never treat `@EventListener` as a durable exactly-once message bus.
- [ ] Run E2E browser/canary tests in a production-like staging environment.

### 11.3. When production reports "success event fired yet user still sees login page"

Trace in order:

1. Verify `AuthenticationSuccessEvent` came from the right endpoint and flow, not another API's token check.
2. Check `SessionAuthenticationStrategy`, max sessions, and session fixation; the manager event fires before these checks.
3. Check whether `InteractiveAuthenticationSuccessEvent` actually fires for the filter in use; do not assume every auth mechanism uses that filter.
4. Check whether `AuthenticationSuccessHandler` was called and issued a valid redirect; look for custom exceptions/timeouts.
5. Check whether the browser received and returned the session cookie (`Secure`, `SameSite`, domain, HTTPS/proxy).
6. Check `SecurityContextRepository`, session store/cluster sharing, and explicit save in custom flows.
7. Check whether the post-redirect endpoint returned 401, 403, or 500; separate authentication, authorization, and business errors.
8. If MFA/step-up applies, verify all required factors and identify which step was abandoned.
9. Trace correlation IDs without printing JSESSIONID/tokens/passwords.
10. Conclude by exact milestone ("credential accepted," "context restored," "resource authorized") rather than a vague "login success" label.

## 12. Self-check questions

1. At which layer is `AuthenticationSuccessEvent` emitted, and how should the publisher be configured?
2. Why does `ProviderManager.authenticate` returning authenticated not equal creating a browser session?
3. Does `InteractiveAuthenticationSuccessEvent` fire before or after `AuthenticationSuccessHandler` in the default filter?
4. Is `InteractiveAuthenticationSuccessEvent` a subclass of `AuthenticationSuccessEvent`?
5. If the session strategy rejects due to max sessions **after a valid password**, which events/milestones may already have occurred?
6. Why does a success handler issuing a 302 not prove the browser reached the target page?
7. What must be tested on the second request to prove `SecurityContext` was restored?
8. Should a Resource Server verifying a JWT 100 times count 100 new logins?
9. If MFA is mandatory, is `isAuthenticated()=true` after the password step enough to report login complete?
10. What metric names should be used at the manager event vs. business completion?
11. How can a synchronous event listener throwing an exception affect authentication?
12. When durable, deduplicated auditing is required, should you rely on a stateless event listener?

**Suggested answers:** (1) AuthenticationManager/AuthenticationEventPublisher, e.g., DefaultAuthenticationEventPublisher; (2) authenticate only returns the result without saving context/response; (3) before the success handler; (4) no; (5) manager event may fire, while interactive/handler do not; (6) redirect is only a server response; (7) cookie/session persistence and authorized access to the protected request; (8) no; (9) not yet, factor policy is still required; (10) AUTHENTICATION_ACCEPTED and LOGIN_JOURNEY_COMPLETED per contract; (11) it can throw errors or alter the flow; (12) no, persistence/outbox/idempotency is required.

## 13. Official references

- [Spring Security 6.5 — Authentication Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — AbstractAuthenticationProcessingFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html)
- [Spring Security 6.5 — ProviderManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Spring Security 6.5 — InteractiveAuthenticationSuccessEvent API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/event/InteractiveAuthenticationSuccessEvent.html)
- [Spring Security 6.5 — AuthenticationSuccessEvent API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/event/AuthenticationSuccessEvent.html)
- [Spring Security 6.5 — SavedRequestAwareAuthenticationSuccessHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Framework — Application Events and @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events)
- [Spring Framework — TestContext Application Events](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
