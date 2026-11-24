# Authentication Success/Failure Events and Extension Points in Spring Security Servlet

## Objectives

In Spring Security Servlet, a single authentication attempt may pass through `AuthenticationFilter` or `UsernamePasswordAuthenticationFilter`, `AuthenticationManager`, `AuthenticationProvider`, `SecurityContext`, and finally the HTTP response. Beyond returning a valid `Authentication` or throwing `AuthenticationException`, the system also offers **authentication events** and **extension points** for logging, metrics, user redirection, or error responses.

After this lesson, you will be able to:

1. Trace the path of successful and failed authentication in form login using Spring Security 6.
2. Distinguish `AuthenticationSuccessEvent`, subclasses of `AbstractAuthenticationFailureEvent`, and `InteractiveAuthenticationSuccessEvent`.
3. Understand the role of `AuthenticationEventPublisher`/`DefaultAuthenticationEventPublisher` versus `AuthenticationSuccessHandler`/`AuthenticationFailureHandler`.
4. Register listeners with `@EventListener` or `ApplicationListener` and choose the right place to handle HTTP responses.
5. Write a Spring Boot + Java 17 example with form login, an audit listener, success/failure handlers, and MockMvc tests with CSRF.
6. Distinguish **authentication** errors, **authorization** errors, CSRF rejections, and cases that do not emit the event you might expect.
7. Design logging, telemetry, and extension logic without leaking credentials or disrupting the login flow.

Scope: Spring Boot 3.x, Spring Security 6.x on the **Servlet stack** (Spring MVC), Java 17+. Examples use modern `SecurityFilterChain`/`HttpSecurity`; they do not use the removed `WebSecurityConfigurerAdapter` configuration and do not apply directly to WebFlux.

## 1. Where Are Authentication Success and Failure Defined?

Spring Security defines **authentication** as verifying an identity or credentials. An `Authentication` in `SecurityContext` represents the user/principal accepted by the security framework. **Authorization** is the subsequent step: deciding whether the authenticated principal may perform an action or access an endpoint.

Examples:

- Valid username and password on `POST /login`: authentication succeeds.
- Wrong password on `POST /login`: authentication fails, typically associated with `BadCredentialsException`.
- Logged-in user lacking the `ADMIN` role calling `/admin`: authentication may have succeeded, yet **authorization fails**. This is not necessarily an `AuthenticationFailureEvent`.
- `POST /login` missing a CSRF token when CSRF protection is enabled: the request may be blocked by `CsrfFilter` **before** `AuthenticationManager` is ever invoked. This is not a password failure and does not necessarily emit an authentication failure event.
- `GET /private` when unauthenticated: may redirect to `/login` without any credential-based authentication attempt having occurred.

Therefore, do not equate every HTTP 401/403/302 with an authentication failure count. Events carry specific meaning at the layer where they are published.

## 2. Flow Diagram for Form Login

With `formLogin` and `UsernamePasswordAuthenticationFilter`, a typical flow is:

~~~text
Browser: POST /login (username, password, CSRF token)
    |
Servlet container / FilterChainProxy / SecurityFilterChain
    |
CsrfFilter: validate token if method requires
    |
UsernamePasswordAuthenticationFilter: read credentials
    |
AuthenticationManager (usually ProviderManager)
    |
AuthenticationProvider (e.g., DaoAuthenticationProvider)
    |                                |
    | SUCCESS                        | FAILURE
    v                                v
Valid Authentication              AuthenticationException
    |                                |
AuthenticationEventPublisher      AuthenticationEventPublisher
    |                                |
AuthenticationSuccessEvent (*)    AuthenticationFailure...Event (*)
    |                                |
Filter completes success steps    unsuccessfulAuthentication(...)
per configuration                    |
    |                             AuthenticationFailureHandler
SecurityContext / session, etc.      |
    |                             HTTP 401 or redirect /login?error
AuthenticationSuccessHandler         |
    |                             Does not reach target controller
HTTP 200 or redirect
~~~

The asterisk (*) highlights that event emission depends on the **actual `AuthenticationManager`/`AuthenticationEventPublisher`** and configuration. Never assume every `AuthenticationManager`, provider, or custom filter publishes the exact same events. The example depicts the common path through `ProviderManager` with a configured publisher.

Exact ordering of session strategy, `SecurityContextRepository`, Remember-Me, interactive events, and handlers depends on the current filter and configuration. Point to remember: **events are published at the authentication layer**, whereas **handlers decide the HTTP response for that login attempt**. Logging inside an event listener is not what creates `SecurityContext` or logs the user in.

### Quick Comparison Table

| Component | What Does It Receive? | When Is It Used? | Responsibility |
| --- | --- | --- | --- |
| `AuthenticationProvider` | Authentication request handed off by `AuthenticationManager` | Whenever the provider participates in authentication | Verify credentials; return `Authentication` or throw `AuthenticationException` |
| `AuthenticationEventPublisher` | Success/failure outcome passed by the manager | When invoked by the publisher caller | Publish application events |
| `AuthenticationSuccessEvent` | Successful `Authentication` | When published by the publisher | Observe authentication success at the manager layer |
| `AbstractAuthenticationFailureEvent` | `Authentication` and `AuthenticationException` | When the publisher maps an error to an event | Observe authentication failure |
| `AuthenticationSuccessHandler` | `HttpServletRequest`, `HttpServletResponse`, `Authentication` | When the login filter invokes the handler after success | Choose redirect, status, response body |
| `AuthenticationFailureHandler` | `HttpServletRequest`, `HttpServletResponse`, `AuthenticationException` | When the login filter invokes the handler after error | Return status, redirect, or safe error message |
| `AuthenticationEntryPoint` | Request, response, reason authentication is needed | When accessing a resource requiring login/challenge | Start the login flow or return a challenge |
| `AccessDeniedHandler` | Request/response and `AccessDeniedException` | When the principal lacks sufficient permissions | Return access-denied response, usually 403 |

These components answer **different questions**. An event is not an HTTP handler; an HTTP handler does not automatically become an event listener.

## 3. Authentication Events You Should Know

### 3.1. AuthenticationSuccessEvent

`AuthenticationSuccessEvent` comes from `AuthenticationEventPublisher`. It carries the `Authentication` just accepted by the manager. Listeners can inspect the `Authentication` type, authorities, or an internal identifier consistent with security policy.

**Never use events to log passwords, raw tokens, or sensitive principal details.** An `Authentication` may contain credentials or `details` added by a provider or filter. In some mechanisms, credentials have already been erased by the time the event arrives, yet you must not rely on that assumption for safety.

A single successful login may trigger additional events from filters or the application. Do not blindly count every event containing "Success" as separate user logins.

### 3.2. InteractiveAuthenticationSuccessEvent

In interactive authentication flows, `AbstractAuthenticationProcessingFilter` can publish `InteractiveAuthenticationSuccessEvent` when the filter finishes a successful authentication. This is a **different event type** from `AuthenticationSuccessEvent`, reflecting the login filter's context rather than just the `AuthenticationManager` outcome.

In standard form login, application listeners may observe both `AuthenticationSuccessEvent` and `InteractiveAuthenticationSuccessEvent` for the same action. **Counting both events as two logins** produces skewed metrics. Define your metric clearly: successful manager authentications, completed form logins, or active user sessions.

### 3.3. AbstractAuthenticationFailureEvent and Subtypes

`AbstractAuthenticationFailureEvent` is the superclass for authentication failure events. Common subtypes include:

- `AuthenticationFailureBadCredentialsEvent`: invalid credentials.
- `AuthenticationFailureDisabledEvent`: account marked disabled per provider logic.
- `AuthenticationFailureLockedEvent`: account is locked.
- `AuthenticationFailureExpiredEvent`: account has expired.
- `AuthenticationFailureCredentialsExpiredEvent`: credentials have expired.
- `AuthenticationFailureServiceExceptionEvent`: authentication service-related error, depending on exception mapping.

Do not use subtypes to display specific user-facing messages like "account exists but is locked" if doing so creates an account-enumeration risk. For public users, a generic message may be appropriate; internal logs still need protection.

Not every `AuthenticationException` is guaranteed to have a failure event subtype: `DefaultAuthenticationEventPublisher` maps **specific exception classes**. Custom exceptions or subclasses may need additional exception mappings configured to emit the desired events. Do not assume that merely extending `BadCredentialsException` always makes the publisher map it identically to the superclass.

### 3.4. Authorization, Logout, and Session Events Differ from Authentication Events

`AuthorizationDeniedEvent` (when enabled via the corresponding publisher) relates to **authorization**. `LogoutSuccessEvent` relates to **logout** in an appropriate configuration. `SessionDestroyedEvent` or `HttpSession` events relate to **session lifecycle**. None of these are synonymous with `AuthenticationSuccessEvent`/`AuthenticationFailureEvent`.

If you need to audit allowed/denied API actions, look into `AuthorizationEventPublisher` or authorization integrations; to track logouts, use logout events/handlers. Do not force everything into form login success/failure handlers.

## 4. AuthenticationEventPublisher and Event Publication Mechanics

The `AuthenticationEventPublisher` interface represents publishing authentication outcomes:

~~~java
// Illustrative method sketches for reading the API,
// not a complete Spring Security source file.
void publishAuthenticationSuccess(Authentication authentication);
void publishAuthenticationFailure(
        AuthenticationException exception,
        Authentication authentication);
~~~

`ProviderManager` can call its configured publisher once an authentication outcome is known. `DefaultAuthenticationEventPublisher` is the common implementation, converting outcomes into Spring `ApplicationEventPublisher` events.

In standard Spring Boot apps, auto-configuration may provide a `DefaultAuthenticationEventPublisher` if no matching bean exists. To make the dependency explicit and avoid relying on defaults changing, the example below **declares the `AuthenticationEventPublisher` bean**:

~~~java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher events) {
    return new DefaultAuthenticationEventPublisher(events);
}
~~~

This is a snippet inside a `@Configuration` class with full imports in the sample program below, not a standalone Java program.

Important points:

1. Having a publisher bean does not prove **every `AuthenticationManager` in the system** uses it. For manually constructed `AuthenticationManager`/`ProviderManager` instances, verify `setAuthenticationEventPublisher(...)` was called or wired via proper configuration.
2. `ProviderManager` can hold multiple `AuthenticationProvider`s; only `authenticate` calls passing through a manager with a publisher will publish events accordingly.
3. `DefaultAuthenticationEventPublisher` publishes based on exception mappings, not by inferring event types from the final HTTP status code.
4. If a listener throws a runtime exception during synchronous event publication, authentication processing can be disrupted. Audit listeners should be fast, safe, and fault-tolerant.
5. Never use an event listener as a **mandatory pre-authentication blocker** (such as enforcing rate limits). Blocking rules belong in gateways, pre-auth filters, providers, or appropriate components before accepting an `Authentication`.

### Do Event Listeners Run Asynchronously?

Under Spring's standard application event mechanism, listeners run synchronously on the publisher's thread unless the app configures an appropriate multicaster/async mechanism. `@EventListener` does not automatically move execution to another thread. Using `@Async` requires enabling async support and understanding security context, transactions, retries, event ordering, and backpressure.

Offload non-essential audit telemetry to a queue or outbox when high reliability is required; avoid slow external calls inside synchronous login listeners.

## 5. AuthenticationSuccessHandler and AuthenticationFailureHandler

These two interfaces decide what happens **at the HTTP layer** after a filter-based login mechanism receives an authentication outcome.

### 5.1. Success Handler

`AuthenticationSuccessHandler` receives the request, response, and accepted `Authentication`. Common actions:

- Redirect the user back to the prior URL or a default page (saved request / redirect).
- Return a JSON response or short body if the frontend uses API-style login.
- Attach a non-sensitive header so the frontend knows the state.
- Run lightweight post-login logic without re-deciding authentication.

Default form login normally uses a redirect strategy like `SavedRequestAwareAuthenticationSuccessHandler`. When you write a custom handler returning 200, you **have changed the navigation contract**. Choose what fits your application UI.

### 5.2. Failure Handler

`AuthenticationFailureHandler` receives the `AuthenticationException` and decides the response when the authentication filter fails:

- HTML form: redirect back to the login page with a generic error flag.
- JSON/SPA login: return 401 and a safe error code, without printing stack traces.
- Record low-cardinality metrics, never printing passwords or tokens into logs.

With `SimpleUrlAuthenticationFailureHandler`, you can configure the error URL; with a custom failure handler, you manage status/body/redirects yourself.

**Not every 401 passes through `formLogin.failureHandler`.** HTTP Basic uses an entry point when issuing challenges; Bearer Token and OAuth2 Resource Server have their own filters and entry points; an unauthenticated request hitting a protected resource is usually not a form-login attempt.

### 5.3. Entry Point, Access Denied, and Handlers Are Not Interchangeable

| Symptom | Example | Typical Handling Point |
| --- | --- | --- |
| `POST /login` valid password | User authenticates successfully | Form login `AuthenticationSuccessHandler`; may emit authentication success events |
| `POST /login` wrong password | `BadCredentialsException` | Form login `AuthenticationFailureHandler`; may emit failure event |
| `GET /private` unauthenticated | No valid authentication | `AuthenticationEntryPoint` → redirect/challenge |
| `GET /admin` logged in yet lacking permission | `AccessDeniedException` | `AccessDeniedHandler`, typically HTTP 403 |
| `POST /login` missing CSRF token | `CsrfFilter` rejects | CSRF/access-denied handling, not normally `AuthenticationFailureHandler` |
| `GET /api` requiring Basic without header | No Basic credentials to process | `BasicAuthenticationEntryPoint`/exception translation, typically 401 with `WWW-Authenticate` |
| Request with invalid Bearer token | Bearer token extraction/validation fails | Resource server config and `BearerTokenAuthenticationEntryPoint`, filter-dependent |

Picking the right hook prevents misplacing logic, causing unexpected redirects, or bypassing CSRF and authorization.

## 6. Spring Boot 3.x + Spring Security 6.x + Java 17 Example

This lab sets up HTML/form login, yet the **success handler returns 200 + body `LOGIN_OK`** and the failure handler returns **401 + body `LOGIN_FAILED`** for clear testing. The default configuration keeps CSRF protection active and uses sessions as needed. The app includes a listener logging `AuthenticationSuccessEvent` and `AbstractAuthenticationFailureEvent` minimally.

### 6.1. Creating the Project

A Gradle Groovy DSL project can have this structure:

~~~text
auth-events-demo/
  settings.gradle
  build.gradle
  gradlew, gradlew.bat (if generated with Gradle wrapper)
  src/main/java/dev/example/authevents/
    AuthEventsApplication.java
    SecurityConfig.java
    AuthAuditListener.java
    PagesController.java
  src/test/java/dev/example/authevents/
    AuthenticationFlowTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'auth-events-demo'
~~~

`build.gradle` (example using Spring Boot 3.3.5 and Java 17; if your project already has another setup, use compatible versions/dependencies managed by your project):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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
~~~

The Java files below must use the exact paths, packages, and class names described. You can initialize a project via Spring Initializr with the web/security starters and Gradle wrapper, then replace the sources with the code below. Since Spring libraries are used, do not invoke `javac` standalone without the classpath; build and run through Gradle/Maven.

### 6.2. Entry Point

File `src/main/java/dev/example/authevents/AuthEventsApplication.java`:

~~~java
package dev.example.authevents;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthEventsApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthEventsApplication.class, args);
    }
}
~~~

### 6.3. Authentication, Event Publisher, and HTTP Handlers Configuration

File `src/main/java/dev/example/authevents/SecurityConfig.java`:

~~~java
package dev.example.authevents;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;

@Configuration
public class SecurityConfig {

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher springEvents) {
        return new DefaultAuthenticationEventPublisher(springEvents);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("learner")
                        .password(encoder.encode("learn-pass-123"))
                        .roles("USER")
                        .build());
    }

    @Bean
    AuthenticationSuccessHandler formSuccessHandler() {
        return (request, response, authentication) -> {
            response.setStatus(200);
            response.setContentType(MediaType.TEXT_PLAIN_VALUE);
            response.setCharacterEncoding("UTF-8");
            response.getWriter().write("LOGIN_OK");
        };
    }

    @Bean
    AuthenticationFailureHandler formFailureHandler() {
        return (request, response, exception) -> {
            response.setStatus(401);
            response.setContentType(MediaType.TEXT_PLAIN_VALUE);
            response.setCharacterEncoding("UTF-8");
            response.getWriter().write("LOGIN_FAILED");
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationSuccessHandler formSuccessHandler,
            AuthenticationFailureHandler formFailureHandler)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .successHandler(formSuccessHandler)
                        .failureHandler(formFailureHandler)
                        .permitAll())
                .build();
    }
}
~~~

Points to observe:

- The sample `UserDetailsService` holds a single user `learner` whose password is encoded by an appropriate `PasswordEncoder`; never store plaintext passwords in real system configs.
- `@Bean AuthenticationEventPublisher` builds a publisher from `ApplicationEventPublisher`. When using a standard Spring Security-configured manager, this publisher can connect to the authentication lifecycle; for manually built managers, verify wiring.
- `formLogin` sets up the `POST /login` processing path and the default `GET /login` page if no custom login page is specified.
- `formSuccessHandler` and `formFailureHandler` write HTTP status/body; they are **not listeners**. Switch back to redirects in traditional web apps if the UI expects them.
- CSRF is not disabled. `POST /login` from a browser requires the CSRF token supplied by the security framework; the MockMvc tests below send the token explicitly.
- Role `USER` in `UserDetailsService` is stored as authority `ROLE_USER`. Do not confuse this prefix when checking with `hasAuthority` vs `hasRole`.

In real applications, never output separate "wrong user" vs "wrong password" messages in responses. The `LOGIN_FAILED` body here is intentionally uniform across login errors to mitigate account enumeration.

### 6.4. Listener for Both Event Groups

File `src/main/java/dev/example/authevents/AuthAuditListener.java`:

~~~java
package dev.example.authevents;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.stereotype.Component;

@Component
public class AuthAuditListener {

    private static final Logger log =
            LoggerFactory.getLogger(AuthAuditListener.class);

    @EventListener
    public void onSuccess(AuthenticationSuccessEvent event) {
        log.info("auth result=success type={}",
                event.getAuthentication().getClass().getSimpleName());
    }

    @EventListener
    public void onFailure(AbstractAuthenticationFailureEvent event) {
        log.warn("auth result=failure exceptionType={}",
                event.getException().getClass().getSimpleName());
    }
}
~~~

How the code works:

- `@Component` registers the listener as a Spring bean. `@EventListener` subscribes the method to matching event types.
- `onFailure` accepts superclass `AbstractAuthenticationFailureEvent`, so it receives subtypes emitted by the publisher, such as `AuthenticationFailureBadCredentialsEvent`.
- Logs only the class name / outcome type. Never read, serialize, or log `authentication.getCredentials()`, HTTP request passwords, `Authorization` headers, tokens, session IDs, or exception messages holding sensitive data.
- On authentication success, the log does not imply a session was created or a controller was reached; those belong to other steps in the flow.
- Listeners should stay small and avoid throwing exceptions so telemetry never breaks login. If writing audits to storage that can fail, design a queue/transaction/outbox or clear fail-open/fail-closed policy per legal requirements.

If replacing `@EventListener` with `ApplicationListener<AuthenticationSuccessEvent>`, implement `onApplicationEvent(event)`; both listen to events, so avoid registering both for the same goal or you will produce duplicate records.

### 6.5. Controller to Test Resource Protection

File `src/main/java/dev/example/authevents/PagesController.java`:

~~~java
package dev.example.authevents;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PagesController {

    @GetMapping("/public/ping")
    public String ping() {
        return "PUBLIC_OK";
    }

    @GetMapping("/private")
    public String privatePage() {
        return "PRIVATE_OK";
    }
}
~~~

`GET /public/ping` is permitted via `permitAll`; `GET /private` requires authentication. Page access control is the responsibility of `authorizeHttpRequests`, not `AuthAuditListener`.

### 6.6. MockMvc Tests with CSRF Token

File `src/test/java/dev/example/authevents/AuthenticationFlowTest.java`:

~~~java
package dev.example.authevents;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicUrlIsAvailable() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("PUBLIC_OK"));
    }

    @Test
    void privateUrlRequiresAuthentication() throws Exception {
        mvc.perform(get("/private"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void correctPasswordCallsSuccessHandlerAndSavesLogin() throws Exception {
        MvcResult login = mvc.perform(post("/login").with(csrf())
                        .param("username", "learner")
                        .param("password", "learn-pass-123"))
                .andExpect(status().isOk())
                .andExpect(content().string("LOGIN_OK"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/private").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("PRIVATE_OK"));
    }

    @Test
    void wrongPasswordCallsFailureHandler() throws Exception {
        mvc.perform(post("/login").with(csrf())
                        .param("username", "learner")
                        .param("password", "wrong-pass"))
                .andExpect(status().isUnauthorized())
                .andExpect(content().string("LOGIN_FAILED"));
    }

    @Test
    void missingCsrfTokenIsNotPasswordFailure() throws Exception {
        mvc.perform(post("/login")
                        .param("username", "learner")
                        .param("password", "learn-pass-123"))
                .andExpect(status().isForbidden());
    }
}
~~~

Run in a project with the Gradle wrapper:

~~~bash
./gradlew test
./gradlew bootRun
~~~

On Windows PowerShell, typically use `./gradlew.bat test` and `./gradlew.bat bootRun`. The `gradlew` command exists only when the wrapper is present; if you create a Gradle project without a wrapper, install Gradle or generate the wrapper first.

All tests are expected to pass with the configuration shown. Key takeaway from each test:

1. Public GET returns 200, with no password authentication attempt.
2. Private GET without a session redirects, without emitting a `BadCredentialsEvent` by default.
3. `POST /login` with valid credentials and CSRF token returns `LOGIN_OK`; the request's session succeeds on `/private`.
4. `POST /login` with wrong credentials and valid CSRF returns `LOGIN_FAILED` and 401.
5. `POST /login` without a CSRF token returns 403 before password verification runs.

**The tests above verify HTTP behavior and sessions; they do not automatically verify that the event listener was called.** To test events, add a dedicated integration test with a test listener or `ApplicationEventPublisher` probe counting exact event types per attempt; avoid collapsing both `AuthenticationSuccessEvent` and `InteractiveAuthenticationSuccessEvent` into one metric. You can also check `auth result=success/failure` logs during development, without turning logs into your only production assertion.

### 6.7. Trying with Browser and curl

When the app runs locally, try:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/private
~~~

Typical results are HTTP 200 with `PUBLIC_OK` for the public endpoint, and a 302 redirect to `/login` for private GET without a login session.

To test login manually, open `http://localhost:8080/login` in a **browser** and enter `learner` / `learn-pass-123`. Spring Security's default login page includes a hidden CSRF token when form login/CSRF are enabled. The custom handler returns body `LOGIN_OK` instead of redirecting.

Never send `POST /login` via `curl -d username=... -d password=...` without CSRF and conclude authentication failed because you got 403. For manual HTTP tests, fetch and submit the matching CSRF token and session cookie. In automated tests, `spring-security-test`'s `.with(csrf())` is cleaner and more direct.

Use sample passwords only in local apps. Real environments require TLS/HTTPS and secure secret management.

## 7. Observing Real Events and Data Semantics

In a typical default Spring Security configuration via `ProviderManager`:

- On form login with valid credentials, the publisher may emit `AuthenticationSuccessEvent`; `onSuccess` logs something like `auth result=success type=UsernamePasswordAuthenticationToken`.
- The form login filter may also emit `InteractiveAuthenticationSuccessEvent`. This example's listener **does not subscribe** to that type, avoiding double counting.
- On wrong password, the provider/manager throws `AuthenticationException`, and the publisher normally maps `BadCredentialsException` to `AuthenticationFailureBadCredentialsEvent`; `onFailure` catches it via superclass `AbstractAuthenticationFailureEvent`.
- When CSRF blocks a request before it enters `UsernamePasswordAuthenticationFilter`, no authentication attempt passes through the manager, so expect no bad-credentials event.
- When a logged-in user visits a URL without sufficient permissions, authorization denies the request; do not expect the form failure handler.

These are **expected outcomes of the sample configuration**, not a guarantee that every Spring Security app emits the exact same event counts. Event counts vary with authentication invocations, managers, filters, token strategies, session persistence, error handling, and wired publishers. Inspect actual code, config, and runtime tests before building security analytics.

### Why Do Event Listeners Sometimes Not Fire?

Typical causes:

1. No `AuthenticationEventPublisher` is wired to the active `AuthenticationManager`, especially with custom-built managers.
2. A custom filter places `Authentication` directly into `SecurityContext` without calling a manager or publisher.
3. Authentication fails before reaching the manager (CSRF, request parsing, filter URL mismatch, etc.).
4. The exception is not in `DefaultAuthenticationEventPublisher`'s mapping table for emitting a failure event subtype.
5. The listener is not a Spring bean, or the `@EventListener` method signature/event type does not match.
6. Multiple `ApplicationContext`s exist, the listener lives in a different context from the publisher, or a custom event multicaster is configured.
7. You are listening for `AuthenticationSuccessEvent` when the flow emits another event, or expecting an event on every HTTP request when it is merely reusing a session.

Debugging steps: confirm the exact `SecurityFilterChain` selected; verify the login filter matches `POST /login`; confirm which provider/manager runs; check the `AuthenticationEventPublisher` bean; add a probe listener and inspect exception types. Avoid leaving TRACE logging enabled long-term or printing sensitive details.

## 8. Extending Failure Events for Custom Exceptions

`DefaultAuthenticationEventPublisher` uses a mapping table from `AuthenticationException` classes to `AbstractAuthenticationFailureEvent` subtypes. If you write a custom `AuthenticationProvider` throwing a new `AuthenticationException`, a listener subscribed to `AbstractAuthenticationFailureEvent` may receive nothing if the publisher has no mapping for it.

When genuinely needed, you can configure **additional exception mappings** on `DefaultAuthenticationEventPublisher` using the API of your Spring Security version. The idea is to map a specific `AuthenticationException` class to a fitting `AuthenticationFailureEvent` subtype while defining fallback behavior for unmapped types. Never rely on a Java subclass automatically inheriting its superclass's mapping.

For failure monitoring, you can also keep your listener on superclass `AbstractAuthenticationFailureEvent` to catch all emitted failure subtypes without writing one listener per subtype. That **does not fix** a publisher that emits no event in the first place.

A practical rule: if a custom provider throws failures containing sensitive context, the event should carry only minimal audit data. Listeners must strictly avoid printing raw exception messages to public logs or responses.

## 9. Choosing Extension Points by Need

| Practical Need | Preferred Extension Point | Notes |
| --- | --- | --- |
| Verify username/password from a custom data source | `UserDetailsService`, `AuthenticationProvider` | Do not use a success handler to re-authenticate |
| Add pre-login blocking or rate limiting | Gateway / pre-auth filter / `AuthenticationProvider` | Post-failure events are too late to block |
| Return user to pre-login URL | `AuthenticationSuccessHandler` supporting saved requests | Default form login already has a suitable redirect strategy |
| Login API needing clean JSON 200/401 | `SuccessHandler` / `FailureHandler` on the login filter | Do not inadvertently disable CSRF if browsers use cookies |
| Audit authentication success/failure | `AuthenticationEventPublisher` + `ApplicationEvent` listener | Keep data safe, idempotent, and retention-governed |
| Emit metrics on successful logins | Define clearly which event represents one login | Basic and token flows behave differently from form login |
| Customize response when unauthenticated user hits protected URL | `AuthenticationEntryPoint` | Not the `POST /login` failure handler |
| Customize response when logged-in user lacks permission | `AccessDeniedHandler` / `AuthorizationManager` | Not `BadCredentialsEvent` |
| React to logout | `LogoutSuccessHandler` and appropriate logout events | Do not confuse with authentication failure |
| Need authorization events | `AuthorizationEventPublisher` or matching listener | Independent of `AuthenticationEventPublisher` |
| Observe steps before/after auth across filters | Custom `OncePerRequestFilter` with explicit order | Account for `SecurityFilterChain`, `@Order`, and CSRF |

Lower-level extension points are more powerful yet easier to break. Start from the business requirement and pick the API whose responsibility matches most closely.

### Custom `AuthenticationProvider` and Events Are Separate Jobs

`AuthenticationProvider.validateCredentials(...)` (implementation-dependent) returns a successful `Authentication` or throws `AuthenticationException`. The publisher connected to `AuthenticationManager` emits the corresponding event when configured. Providers need not publish events themselves when using the standard publisher; publishing the same type again can cause duplicate audit records.

If you replace `AuthenticationManager` completely, explicitly decide the rules for calling `AuthenticationEventPublisher`. Adding a listener with no publisher in a custom flow is a common observability bug.

## 10. Security and Operations: Common Mistakes

### 10.1. Writing Credentials into Event Logs

Never log passwords, credentials, `Authorization` headers, JWTs, CSRF tokens, cookies, `JSESSIONID`, or raw `Authentication.toString()` unguarded. Even exception messages can leak internal details. Log event type, exception type, a safe request correlation ID, timestamp, and only identifiers masked per data policy.

### 10.2. Returning Disclosing Errors, Enabling User Enumeration

Failure handlers should not publicly distinguish "unknown user", "wrong password", and "user locked" unless the app has strong anti-enumeration defenses. Generic responses and non-leaking timing are common safe choices. Internal audits can retain finer details with proper access controls and retention limits.

### 10.3. Equating HTTP 403 with Wrong Login

A 403 from CSRF or missing permissions is unlikely to be an authentication failure; a 401 from an entry point may not correspond to a manager event either. Build dashboards separating metrics by origin: login attempts, authentication outcomes, authorization denials, CSRF rejections, and entry-point challenges.

### 10.4. Slow or Exception-Throwing Synchronous Listeners

Event listeners usually execute on the authentication processing path; long external API/DB calls add latency and can fail logins. Persist critical audits reliably via queues/outboxes, bounded retries, timeouts, and clear failure policies when downstream degrades. Listeners must never alter an authentication outcome solely due to an unexpected telemetry failure.

### 10.5. Double-Counting Success Events

`AuthenticationSuccessEvent`, `InteractiveAuthenticationSuccessEvent`, session creation, and HTTP 200 all mean different things. Use clear metric definitions and correlation IDs when reconciling; avoid summing raw log lines into "total user logins" without deduplication.

### 10.6. Performing Redirects Inside a Listener

An `AuthenticationSuccessEvent` listener is not where you send redirects to a browser: it lacks `AuthenticationSuccessHandler`'s `HttpServletResponse` contract. Use the filter's handler for navigation or JSON responses.

### 10.7. Applying Form Login Handlers to HTTP Basic/Bearer

Each authentication style has its own filters and error flows. With Basic, authentication may repeat on every request carrying an `Authorization` header; with Bearer, token validation and the entry point are central. Never assume `formLogin.successHandler` applies to `BasicAuthenticationFilter` or `BearerTokenAuthenticationFilter`.

### 10.8. Accidentally Disabling CSRF to Test Login

If browsers rely on session cookies, keep proper CSRF protection; Spring Security protects `POST /login` by default. Test with `csrf()` to simulate standard forms. Disabling CSRF casually just to make `POST /login` run weakens application security.

### 10.9. Mutating `SecurityContext` Inside a Listener

Listeners exist to observe results; they should not create or mutate `SecurityContext` directly or rely on thread-local context when running async. Let filters/the framework save valid authentication via the right `SecurityContextRepository`/session strategy. In async processing, understand context propagation and isolation.

### 10.10. Sending Emails or "Exactly-Once" Audits from Non-Durable Events

Default `ApplicationEvent`s are not a durable message queue. Restarts, crashes, or write errors can drop or duplicate notifications. If an event has legal or billing impact, design explicit transactions, outboxes, and idempotency; never promise exactly-once delivery merely because you received `AuthenticationSuccessEvent`.

## 11. In-Depth Testing for Events and Extension Points

The behavioral suite in section 6 covers only status and session. For production apps, add three test groups:

**Group A — Accurate Event Types**

- Register a test listener/probe in the test context to capture `AuthenticationSuccessEvent` and `AbstractAuthenticationFailureEvent` with minimal metadata.
- Send a successful `POST /login` with `csrf()`; assert the success event was published by the active `AuthenticationManager`.
- Send a wrong-password POST with `csrf()`; verify the corresponding failure event.
- Send a POST missing CSRF and verify it is not mistaken for `BadCredentialsEvent`.
- When changing `AuthenticationManager`/`Provider`, rerun tests because event producers may change.

**Group B — HTTP Handlers**

- `SuccessHandler` returns the contract's expected status/redirect/body.
- `FailureHandler` leaks no account existence, stack traces, or sensitive exception messages.
- Unauthenticated protected requests enter `AuthenticationEntryPoint`.
- Unauthorized user requests enter `AccessDeniedHandler`, never reported as login failed.

**Group C — Stability and Scope**

- With multiple `SecurityFilterChain`s, verify the login processing URL hits the intended chain.
- Under concurrent tests, verify listeners hold no mutable state causing race conditions.
- Simulate listener telemetry failures/timeouts per fault-tolerance design.
- For OAuth2/Basic/Bearer, write dedicated tests for the right filters and entry points rather than blindly reusing form-login assertions.

Expected logs might look like:

~~~text
auth result=success type=UsernamePasswordAuthenticationToken
auth result=failure exceptionType=BadCredentialsException
~~~

This is an **illustrative log format**, not byte-for-byte Gradle stdout: loggers may add timestamps, thread names, and levels; actual events depend on providers and publishers. Never use sample logs as proof without testing the real manager.

## 12. Practice Scenarios and Explained Answers

**Scenario 1.** `POST /login` with a wrong password and valid CSRF returns 401 via `formFailureHandler`. What is the role of a listener receiving `AbstractAuthenticationFailureEvent`?

> The listener observes the event emitted by the publisher, such as `BadCredentialsEvent`. The handler decides the HTTP response. The two are decoupled: changing the HTTP status in the handler does not add or alter the authentication event.

**Scenario 2.** `GET /private` returns a 302 redirect to `/login` when there is no cookie. Should you increment a "wrong password" metric?

> No. This is an unauthenticated request to a protected resource; `AuthenticationEntryPoint` initiates login, and no credentials failed verification.

**Scenario 3.** `POST /login` missing CSRF receives 403. Why did `onFailure` log nothing?

> The request was likely rejected by `CsrfFilter` before `UsernamePasswordAuthenticationFilter`/`AuthenticationManager` processed credentials; therefore no manager authentication failure event occurred.

**Scenario 4.** You wrote a class implementing `ApplicationListener<AuthenticationSuccessEvent>`, yet nothing is logged. What should you check?

> Whether the class is a Spring bean, whether `AuthenticationManager` has a publisher wired, whether login actually went through that manager rather than a custom flow, which event class is published, which `ApplicationContext` holds the listener, and how the event multicaster is configured.

**Scenario 5.** One login emits two success events. Are there two sessions?

> Not necessarily. They may be `AuthenticationSuccessEvent` and `InteractiveAuthenticationSuccessEvent` from the same flow. To count sessions, track session lifecycle separately.

**Scenario 6.** You want to send users back to their original URL after login. Should you modify `AuthenticationEventPublisher`?

> No. Use an appropriate `AuthenticationSuccessHandler`, such as one supporting saved requests. The publisher is for emitting events for observation.

**Scenario 7.** A Bearer-token API returns 401 yet `formFailureHandler` does not run. Is that a Spring Security bug?

> Not necessarily. Bearer tokens have their own filter, `AuthenticationEntryPoint`, and error-handling flow. Inspect the `SecurityFilterChain` and configured token authentication mechanism.

**Scenario 8.** A custom provider throws a custom `AuthenticationException`; the user gets an error yet no failure event is emitted. Any fix?

> Check that the manager has a publisher, inspect `DefaultAuthenticationEventPublisher`'s exception mappings, and consider configuring additional exception mappings via your version's API; do not hijack the HTTP failure handler to fake events.

## Summary

In Spring Security Servlet, there are three critical observation/handling points you must **keep separate**:

1. **`AuthenticationManager`/`AuthenticationProvider`** determines the authentication outcome; `AuthenticationEventPublisher` (when configured and used) emits `AuthenticationSuccessEvent` or failure events.
2. **`AuthenticationSuccessHandler`/`AuthenticationFailureHandler`** handles HTTP responses for **the corresponding login mechanism**, such as form login. They differ from `AuthenticationEntryPoint` and `AccessDeniedHandler`.
3. **`@EventListener`/`ApplicationListener`** consumes events for auditing, telemetry, and side effects—never replacing CSRF protection, authorization, or `SecurityContext` persistence.

For every request, ask: **was authentication invoked, which manager executed, which events were published, and which filter/handler decided the response?** Test each layer independently and never let observability mechanisms leak secrets or weaken login security.