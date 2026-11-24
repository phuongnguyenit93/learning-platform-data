# Investigating an Authentication Failure from Request to Provider, Context, and Response

When a user reports **"my password is right yet I still cannot log in"**, do not immediately assume `PasswordEncoder` or `DaoAuthenticationProvider` is broken. A request can be blocked **before** password checking due to CSRF; authentication can succeed yet fail to save `SecurityContext`; a valid session may lack authority for the target page; or the server may send a redirect while the browser fails to retain the cookie.

The goal of this **Capstone Practical Exercise** is learning how to investigate **an authentication failure from request to provider, context, and response**, pinpoint the **first failing boundary**, and prove the fix with tests. The exercise uses **Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, Servlet/MVC, JUnit Jupiter, and MockMvc**. The lab covers form login, HTTP Basic, authentication events, safe stage auditing, second requests, and logout.

**Guiding principle:** rely strictly on directly observed facts; never guess from a single HTTP status code. Never log, attach to tickets, or share raw passwords, hashes, OTPs, access/refresh tokens, API keys, recovery codes, session IDs, `Cookie`/`Authorization` headers, full `Authentication` objects, or request bodies.

## 1. View the Entire Chain Before Fixing One Component

~~~text
Client / browser
   │  HTTP method + path + content type + credentials + CSRF + cookies
   ▼
Proxy / ingress / servlet container
   │
   ▼
FilterChainProxy selects the first SecurityFilterChain matching request
   │
   ├── SecurityContextHolderFilter: loads context from repository
   ├── CsrfFilter: POST without valid token → 403
   │
   ▼
UsernamePasswordAuthenticationFilter (POST /login, form)
   or BasicAuthenticationFilter (HTTP Basic)
   │
   ▼
AuthenticationManager, typically ProviderManager
   │
   ├── Select AuthenticationProvider supporting the token
   ▼
DaoAuthenticationProvider for username/password
   │
   ├── UserDetailsService.loadUserByUsername(...)
   ├── PasswordEncoder.matches(raw, storedEncoded)
   ├── account status / policies
   └── Authentication succeeds or AuthenticationException
   │
   ▼
If successful: SessionAuthenticationStrategy
   │
   ├── Create/set SecurityContext
   ├── Save via SecurityContextRepository if stateful
   └── Success handler → response / redirect
   │
   ▼
Browser receives response, cookie, navigates
   │
   ▼
Second request → restore context → authorization
   │
   ├── Anonymous → entry point (login redirect or 401)
   ├── Authenticated missing role/scope/MFA → 403
   └── Authenticated + authorized → controller/HTTP 200
~~~

This is a **reference flow for Servlet form login**, not a rigid sequence for all mechanisms. JWT Resource Servers, HTTP Basic, OAuth2 Login, custom filters, and multiple `SecurityFilterChain` beans follow different paths. A `ProviderManager` can hold multiple providers and optionally a parent manager; never assume the provider you are reading in source code is the exact one handling live requests.

### 1.1. Order of Questions to Answer

| Stage | Diagnostic Question | Evidence |
| --- | --- | --- |
| **Request** | Did it reach the right host/path/method/proxy/service? | Route category, HTTP status, ingress telemetry |
| **Security chain** | Did the request match the right chain/filters? | Security config, matchers, integration tests |
| **CSRF** | Did a session-based POST carry a valid CSRF token? | Negative/positive CSRF tests, 403 before provider |
| **Authentication filter** | Did POST `/login` or Basic header actually reach the filter? | Handler/provider events and scrubbed method/path |
| **Manager/provider** | Does a provider support `UsernamePasswordAuthenticationToken`? | `AuthenticationSuccessEvent`/failure category, canary tests |
| **User store/encoder** | Was the right account loaded? Are hash/encoder compatible? | Controlled fixtures/metadata, never printing hashes |
| **Account policy** | Enabled/locked/expired/MFA? | Account state category, policy tests |
| **Session/context** | Did the repository save and the next request restore? | Two requests sharing one session in MockMvc |
| **Authorization** | Does the principal hold sufficient authorities at target URL? | 403 vs. authenticated, role tests |
| **Response/client** | Did the handler emit redirect/401/403? Did the browser keep the cookie? | HTTP response + scrubbed browser E2E |

There is no single universal `LoginCompletedEvent` across all authentication mechanisms. A manager's `AuthenticationSuccessEvent` indicates only that authentication was accepted **at that layer**; it does not prove a session persisted or the client reached the destination page.

## 2. Distinguishing Four Commonly Conflated Symptoms

### 2.1. CSRF 403 Before Password Checking

Cookie/session-backed form login POSTs typically require a CSRF token. `CsrfFilter` can reject before `UsernamePasswordAuthenticationFilter` ever runs; therefore:

~~~text
POST /login, right username/password, missing CSRF
→ HTTP 403
→ AuthenticationManager was never called
→ Cannot conclude whether password is right or wrong from this request
~~~

In `MockMvc`, Spring Security Test's `formLogin()` builds a login POST with valid CSRF automatically, whereas raw `post("/login")` without `with(csrf())` is blocked. **Never disable CSRF globally to "fix" login errors**; fix the handshake or client token submission.

### 2.2. Wrong Credentials or Account State

`DaoAuthenticationProvider` uses `UserDetailsService` and `PasswordEncoder`. Invalid passwords typically trigger `BadCredentialsException` and form failure handlers redirect to `/login?error`. Yet login failures can also stem from disabled/locked accounts, wrong tenant lookups, corrupted hash metadata, or the wrong provider being selected.

Never return public messages like "username exists but password is wrong" or "account locked" when that leaks account existence. Internal audits can record bounded, approved codes without logging raw usernames, passwords, hashes, or exception chains.

### 2.3. Authentication Succeeds Yet SecurityContext Does Not Persist

In Spring Security 6, `SecurityContextHolderFilter` loads the context, **without automatically saving every mutation** when the request ends. Built-in form login handles saving cleanly; custom controllers/filters that manually create a context and call only `SecurityContextHolder.setContext(...)` make the first request authenticated while leaving the second request anonymous.

Diagnose using **two HTTP requests**, rather than inspecting only the login response:

~~~text
POST /login           → 302 /private
GET /private (session)→ 200          [principal restored]
GET /private (no session) → redirect [no credential]
~~~

If the form redirect fires yet the browser loops back to `/login`, inspect cookie `SameSite`/`Secure`/`Domain`/`Path`, cross-replica session stores, repository/explicit save calls, and the post-redirect URL. Never reset passwords when the fault lies in session handling.

### 2.4. Authentication Succeeds Yet Authorization Fails

A user with `ROLE_USER` logs in cleanly yet `GET /admin` returns 403 because the route requires `ROLE_ADMIN`. That is not a password check failure:

~~~text
Basic learner /api/me       → 200, authenticated
Basic learner /admin        → 403, missing ROLE_ADMIN
Basic admin /admin          → 200, sufficient authority
~~~

Verify `authorizeHttpRequests`/`hasRole`, authority mapping, and MFA policies rather than granting every role just to turn requests green.

## 3. Useful Signals and Their Limits

| Signal | What You May Infer | What You Must Not Infer |
| --- | --- | --- |
| `AuthenticationSuccessEvent` | Manager/provider accepted an authentication | Browser login completed |
| `AuthenticationFailureBadCredentialsEvent` | Publisher recorded a failure mapped as BadCredentials | Every login failure is a wrong password |
| `InteractiveAuthenticationSuccessEvent` | Interactive auth filter reached event emission | Response, cookie, browser, or protected GET succeeded |
| Form `AuthenticationSuccessHandler` ran | Handler processed the success response | Client received the redirect |
| HTTP 302 `/private` | Server emitted a redirect | Session/cookie definitely works |
| HTTP 302 `/login?error` | Form failure handler ran | Cause is definitely the encoder |
| HTTP 401 with Basic | API request entry point / challenge | All other requests on that account fail |
| HTTP 403 | Access denied | `PasswordEncoder` definitely ran |
| `SecurityContextHolder.getContext()` in request | Principal exists in current thread context | Context persisted to session |
| Second protected request returns 200 | Principal/authorization valid for that request | All future requests are valid |

When using `DefaultAuthenticationEventPublisher` and `@EventListener`, name the audit stage `PROVIDER_ACCEPTED` or `PROVIDER_REJECTED` rather than `LOGIN_COMPLETED`. On Bearer APIs, a valid token can be re-verified on **every request**, so counting each event as a fresh user login is inaccurate.

### 3.1. Response Handlers and Entry Points Are Not the Same

- `AuthenticationFailureHandler`: typically called by an authentication filter after a failed login POST; default form login redirects to `/login?error`.
- `AuthenticationSuccessHandler`: decides the response after successful authentication, usually emitting a redirect.
- `AuthenticationEntryPoint`: invoked by `ExceptionTranslationFilter` when an unauthenticated client requests a protected resource, e.g., redirecting to `/login` or returning HTTP 401.
- `AccessDeniedHandler` / `AuthorizationFilter`: rejects actions by an authenticated principal lacking permissions, typically returning 403.

Thus, `GET /private → /login` alone does not prove `POST /login` failed; it could be a follow-up request arriving without a session cookie.

## 4. Decision Tree by First Failing Boundary

~~~text
START: "Cannot reach page after logging in"
│
├─ Did HTTP request fail to reach service?
│   └─ ROUTING / PROXY / NETWORK / TLS
│
├─ Wrong URL/method or SecurityFilterChain?
│   └─ FILTER_CHAIN / LOGIN_PROCESSING_URL / MATCHERS
│
├─ Was POST blocked by CSRF?
│   └─ CSRF_DENIED (provider never ran)
│
├─ Did AuthenticationManager fail to process it?
│   └─ FILTER_ORDER / UNSUPPORTED_TOKEN / PROVIDER_CONFIG
│
├─ Did Provider reject it?
│   ├─ USER_LOOKUP / ACCOUNT_STATUS
│   ├─ ENCODER_ID / HASH_INTEGRITY / PASSWORD_NORMALIZATION
│   └─ POLICY / MFA / EXTERNAL_IDP
│
├─ Provider accepted yet session strategy rejected?
│   └─ SESSION_POLICY
│
├─ Context set yet not persisted?
│   └─ SECURITY_CONTEXT_REPOSITORY / EXPLICIT_SAVE
│
├─ Server redirected yet client lost session?
│   └─ COOKIE / SESSION_STORE / PROXY
│
├─ Authenticated yet protected endpoint returns 403?
│   └─ AUTHORIZATION / ROLES / MFA
│
└─ All above succeeded yet controller returns 500?
    └─ APPLICATION_ERROR / RESPONSE_HANDLING
~~~

The **first failing boundary** is the earliest point where observed behavior diverges from contract, not whichever class sits last in a stack trace. If the failure occurred at `CsrfFilter`, explanations about `BCryptPasswordEncoder` are irrelevant.

## 5. Safety Standards When Collecting Traces

A clean audit emits:

~~~text
audit_id=<random-server-uuid>
security_stage=HTTP_ENTER  route=LOGIN method=POST
security_stage=PROVIDER_ACCEPTED
security_stage=FORM_SUCCESS_HANDLER
security_stage=HTTP_EXIT status=302
~~~

These lines are a custom design, **not Spring's default full event format**. Never use session IDs or tokens as correlation IDs, because they are themselves credentials. Across multiple requests, use a separate server-generated, protected flow ID when correlating across redirects; a per-request audit ID connects only the stages of that single request.

**Strictly forbidden in logs:**

- `request.getParameter("password")`, login DTOs, `UserDetails.getPassword()`, or full hashes;
- `Authorization`/`Cookie`/`Set-Cookie`/`X-API-Key` headers and request/response bodies holding secrets;
- raw `Authentication`, `SecurityContext`, JWTs, OTPs, and recovery/reset codes;
- unvetted exception messages, `FieldError.getRejectedValue()`, and stack traces containing raw request data;
- query strings/URLs containing `code` or `token`, and unsanitized user-controlled `Request-ID`/`User-Agent` values;
- real passwords in test cases, command lines, CI logs, or error reporting/APM.

Log only **allowlisted stage/route/outcome codes**, server-generated random UUIDs, and HTTP statuses. Clear `MDC` in `finally` to prevent context bleeding across thread-pool requests; reactive/async pipelines require explicit context propagation. Also audit log collectors/proxies/APMs—a safe Java logger **does not guarantee** the whole pipeline leaks zero secrets.

## 6. Standalone Java 17: Classifying an Incident Trace

The Java 17 program below **uses no Spring** and holds zero credentials. Given which steps succeeded, it determines which layer to investigate next.

File `AuthBoundaryClassifier.java`:

~~~java
public class AuthBoundaryClassifier {
    record Trace(boolean requestArrived,
                 boolean filterMatched,
                 boolean csrfAccepted,
                 boolean providerAccepted,
                 boolean contextRestored,
                 int lastStatus) {
    }

    static String diagnose(Trace t) {
        if (!t.requestArrived()) return "PROXY_OR_ROUTING";
        if (!t.filterMatched()) return "FILTER_CHAIN";
        if (!t.csrfAccepted()) return "CSRF";
        if (!t.providerAccepted()) return "AUTHENTICATION_PROVIDER";
        if (!t.contextRestored()) return "SECURITY_CONTEXT_OR_SESSION";
        if (t.lastStatus() == 403) return "AUTHORIZATION";
        if (t.lastStatus() >= 500) return "APPLICATION_OR_RESPONSE";
        return "NO_FAILURE_IN_OBSERVED_STAGES";
    }

    public static void main(String[] args) {
        System.out.println(diagnose(
                new Trace(false, false, false, false, false, 502)));
        System.out.println(diagnose(
                new Trace(true, true, false, false, false, 403)));
        System.out.println(diagnose(
                new Trace(true, true, true, false, false, 302)));
        System.out.println(diagnose(
                new Trace(true, true, true, true, false, 302)));
        System.out.println(diagnose(
                new Trace(true, true, true, true, true, 403)));
        System.out.println(diagnose(
                new Trace(true, true, true, true, true, 200)));
    }
}
~~~

Command:

~~~bash
javac --release 17 AuthBoundaryClassifier.java
java AuthBoundaryClassifier
~~~

Exact stdout:

~~~text
PROXY_OR_ROUTING
CSRF
AUTHENTICATION_PROVIDER
SECURITY_CONTEXT_OR_SESSION
AUTHORIZATION
NO_FAILURE_IN_OBSERVED_STAGES
~~~

**Classifier limits:** in real life, stages can be "unobserved" rather than strictly true/false; provider execution, context restoration, and response status can span **two separate HTTP requests**. Use this program to practice forming hypotheses, not as an automated production root-cause tool.

## 7. Spring Boot 3.5 / Spring Security 6.5 Lab: From Filter to Response

The sample app enables both **form login** and **HTTP Basic** for comparison. `SafeAuthRequestProbe` observes **before `CsrfFilter`** (though it cannot observe components sitting ahead of it at ingress). An `AuthenticationEventPublisher` bean emits manager/provider events. Success/failure handlers record stage codes and perform configured default redirects.

**Lab-only login credentials:**

| Username | Public Dummy Password | Role |
| --- | --- | --- |
| `learner` | `lab-only-password-2026` | `ROLE_USER` |
| `admin` | `lab-only-admin-2026` | `ROLE_ADMIN` |

Never copy lab passwords onto public Internet hosts. Production requires a real account repository, unique securely managed passwords, HTTPS, rate limiting, threat-model-aligned MFA/session policies, and scrubbed audits.

### 7.1. Gradle Dependencies

In a Spring Boot 3.5.x project `build.gradle` with the Boot Gradle plugin/BOM and Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Never add a `spring-security-test` version differing in major/minor from runtime; rely on Boot's dependency management.

### 7.2. Single Java File with App, Filter Probe, Provider Event Listeners, and Endpoints

File `src/main/java/example/authdiag/AuthenticationDiagnosisApplication.java`:

~~~java
package example.authdiag;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.authentication.event.AuthenticationFailureBadCredentialsEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationSuccessHandler;
import org.springframework.security.web.csrf.CsrfFilter;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class AuthenticationDiagnosisApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthenticationDiagnosisApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class DiagnosticSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("lab-only-password-2026"))
                .roles("USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("lab-only-admin-2026"))
                .roles("ADMIN")
                .build();
        return new InMemoryUserDetailsManager(learner, admin);
    }

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher events) {
        return new DefaultAuthenticationEventPublisher(events);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, SafeAuthenticationAudit audit)
            throws Exception {

        SimpleUrlAuthenticationSuccessHandler success =
                new SimpleUrlAuthenticationSuccessHandler("/private");
        SimpleUrlAuthenticationFailureHandler failure =
                new SimpleUrlAuthenticationFailureHandler("/login?error");

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated());

        http.formLogin(form -> form
                .successHandler((request, response, authentication) -> {
                    audit.stage("FORM_SUCCESS_HANDLER");
                    success.onAuthenticationSuccess(
                            request, response, authentication);
                })
                .failureHandler((request, response, exception) -> {
                    audit.stage("FORM_FAILURE_HANDLER");
                    failure.onAuthenticationFailure(
                            request, response, exception);
                })
                .permitAll());

        http.httpBasic(Customizer.withDefaults());
        http.logout(Customizer.withDefaults());

        // Inside the security chain: before CSRF to observe CSRF blocks.
        http.addFilterBefore(new SafeAuthRequestProbe(audit),
                CsrfFilter.class);
        return http.build();
    }
}

@Component
class SafeAuthenticationAudit {
    private static final Logger LOG =
            LoggerFactory.getLogger(SafeAuthenticationAudit.class);

    void stage(String code) {
        LOG.info("security_stage={} audit_id={}", code, auditId());
    }

    void enter(String route, String method) {
        LOG.info("security_stage=HTTP_ENTER audit_id={} route={} method={}",
                auditId(), route, method);
    }

    void exit(int status) {
        LOG.info("security_stage=HTTP_EXIT audit_id={} status={}",
                auditId(), status);
    }

    private String auditId() {
        String id = MDC.get("audit_id");
        return id == null ? "NO_HTTP_CONTEXT" : id;
    }

    @EventListener
    void providerAccepted(AuthenticationSuccessEvent ignored) {
        stage("PROVIDER_ACCEPTED");
    }

    @EventListener
    void badCredentials(AuthenticationFailureBadCredentialsEvent ignored) {
        stage("PROVIDER_BAD_CREDENTIALS");
    }
}

final class SafeAuthRequestProbe extends OncePerRequestFilter {
    private final SafeAuthenticationAudit audit;

    SafeAuthRequestProbe(SafeAuthenticationAudit audit) {
        this.audit = audit;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        // Never read request IDs from clients, never log URL/query/headers.
        String old = MDC.get("audit_id");
        MDC.put("audit_id", UUID.randomUUID().toString());
        try {
            audit.enter(route(request), method(request));
            chain.doFilter(request, response);
        }
        finally {
            audit.exit(response.getStatus());
            if (old == null) MDC.remove("audit_id");
            else MDC.put("audit_id", old);
        }
    }

    private String route(HttpServletRequest request) {
        return switch (request.getServletPath()) {
            case "/login" -> "LOGIN";
            case "/private" -> "PRIVATE";
            case "/api/me" -> "ME";
            case "/admin" -> "ADMIN";
            default -> "OTHER";
        };
    }

    private String method(HttpServletRequest request) {
        return switch (request.getMethod()) {
            case "GET" -> "GET";
            case "POST" -> "POST";
            default -> "OTHER";
        };
    }
}

@RestController
class DiagnosticEndpoints {
    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/private")
    String privatePage(Authentication authentication) {
        return "private:" + authentication.getName();
    }

    @GetMapping("/api/me")
    String whoAmI(Authentication authentication) {
        return "me:" + authentication.getName();
    }

    @GetMapping("/admin")
    String adminPage() {
        return "admin-only";
    }
}
~~~

**Why this code aligns with the architecture:**

1. `AuthenticationDiagnosisApplication` is the sole public class in the file; all others are package-private.
2. `UserDetailsService` supplies lab users and BCrypt hashes; `DaoAuthenticationProvider` uses the encoder in standard Spring Security config.
3. `DefaultAuthenticationEventPublisher` emits authentication events; listeners log only **event codes**. Non-BadCredentials failures may emit other event classes, so missing `PROVIDER_BAD_CREDENTIALS` does not prove the request missed the provider.
4. `SimpleUrlAuthenticationSuccessHandler("/private")` and `SimpleUrlAuthenticationFailureHandler("/login?error")` perform redirects. The lambdas record stages and **delegate to the real handlers** without dropping the HTTP response.
5. `SafeAuthRequestProbe` is instantiated directly with `new` inside the Security filter chain, avoiding a second `@Component`/servlet-filter registration that would cause double execution.
6. The probe logs only **allowlisted** methods/routes, never raw URL queries, usernames, passwords, session IDs, or auth objects.
7. The probe runs **before `CsrfFilter` inside the chain**, yet other filters and external proxies sit ahead of it. Absence of `HTTP_ENTER` does not guarantee the request never reached the server host.
8. `MDC` holds a server-generated random UUID restored/cleared in `finally`; synchronous Spring events in the lab share the same request audit ID.
9. `httpBasic` and form login coexist in the lab, though unauthenticated entry points vary by URL, `Accept` header, and config. Send explicit `Accept: application/json` for Basic negative tests.
10. `LogoutFilter` provides default session cleanup; the lab uses no custom logout controller.

**No actual compile/test run was executed in your project.** This sample requires a Boot 3.5 / Security 6.5 project with matching dependencies; production requires TLS, a real user store, rate limits, proper CSRF/frontend config, MFA/account lifecycles, and zero lab accounts.

### 7.3. Running and Reading Stage Logs

In a project with the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows use `gradlew.bat bootRun`. Open `http://localhost:8080/login` on **localhost**, and try `learner` with the lab password. With valid credentials and valid CSRF, logs look like:

~~~text
security_stage=HTTP_ENTER audit_id=<uuid> route=LOGIN method=POST
security_stage=PROVIDER_ACCEPTED audit_id=<uuid>
security_stage=FORM_SUCCESS_HANDLER audit_id=<uuid>
security_stage=HTTP_EXIT audit_id=<uuid> status=302
~~~

On a wrong password:

~~~text
security_stage=HTTP_ENTER audit_id=<uuid> route=LOGIN method=POST
security_stage=PROVIDER_BAD_CREDENTIALS audit_id=<uuid>
security_stage=FORM_FAILURE_HANDLER audit_id=<uuid>
security_stage=HTTP_EXIT audit_id=<uuid> status=302
~~~

On a POST missing CSRF:

~~~text
security_stage=HTTP_ENTER audit_id=<uuid> route=LOGIN method=POST
security_stage=HTTP_EXIT audit_id=<uuid> status=403
~~~

This is **illustrative**, not verbatim stdout: each request has a unique UUID, and loggers typically add timestamps/logger names/threads. If your project's authentication manager/publisher differs or listeners run asynchronously, ordering and event counts can vary; never rely on log line order alone as absolute proof.

## 8. MockMvc Integration Tests: HTTP Response, Provider Events, and Sessions

File `src/test/java/example/authdiag/AuthenticationDiagnosisApplicationTest.java`:

~~~java
package example.authdiag;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.authentication.event.AuthenticationFailureBadCredentialsEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@RecordApplicationEvents
class AuthenticationDiagnosisApplicationTest {
    @Autowired MockMvc mvc;
    @Autowired ApplicationEvents events;

    @Test
    void formSuccessPersistsAuthenticationToSecondRequest()
            throws Exception {
        MvcResult login = mvc.perform(formLogin()
                .user("learner")
                .password("lab-only-password-2026"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/private"))
            .andExpect(authenticated().withUsername("learner"))
            .andReturn();

        assertTrue(events.stream(AuthenticationSuccessEvent.class)
                .anyMatch(e ->
                        "learner".equals(e.getAuthentication().getName())));

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);

        // Second GET carries no password, only the same session.
        mvc.perform(get("/private").session(session))
            .andExpect(status().isOk())
            .andExpect(authenticated().withUsername("learner"))
            .andExpect(content().string("private:learner"));
    }

    @Test
    void wrongPasswordReachesProviderAndRedirectsToFailure()
            throws Exception {
        mvc.perform(formLogin()
                .user("learner").password("incorrect"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andExpect(unauthenticated());

        assertTrue(events.stream(
                AuthenticationFailureBadCredentialsEvent.class)
                .findAny().isPresent());
    }

    @Test
    void missingCsrfStopsBeforeProvider()
            throws Exception {
        mvc.perform(post("/login")
                .param("username", "learner")
                .param("password", "lab-only-password-2026"))
            .andExpect(status().isForbidden());

        assertEquals(0,
                events.stream(AuthenticationSuccessEvent.class).count());
    }

    @Test
    void basicCorrectPasswordIs200()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("learner", "lab-only-password-2026"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(authenticated().withUsername("learner"))
            .andExpect(content().string("me:learner"));
    }

    @Test
    void basicWrongPasswordIs401() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("learner", "incorrect"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedLearnerIsDeniedAdmin()
            throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("learner", "lab-only-password-2026"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedAdminCanAccessAdmin()
            throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "lab-only-admin-2026"))
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-only"));
    }

    @Test
    void anonymousHtmlRequestIsRedirected()
            throws Exception {
        mvc.perform(get("/private")
                .accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void logoutInvalidatesRealLoggedInSession()
            throws Exception {
        MvcResult login = mvc.perform(formLogin()
                .user("learner")
                .password("lab-only-password-2026"))
            .andExpect(authenticated())
            .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));

        assertTrue(session.isInvalid());

        // Do not reuse the invalidated session.
        mvc.perform(get("/private")
                .accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

There are **9 tests**. Run:

~~~bash
./gradlew test --tests example.authdiag.AuthenticationDiagnosisApplicationTest
~~~

With matching dependencies and environment, tests are expected to pass. **This is an expected outcome, not a claim that Gradle was executed.** `@RecordApplicationEvents` captures events published during the test method; in real apps with multiple managers or custom publishers, test wiring explicitly.

### 8.1. Why Need Both Events and HTTP Assertions?

- `AuthenticationSuccessEvent` proves the manager accepted an authentication, **not that a session is usable**.
- `redirectedUrl("/private")` proves the handler emitted a redirect, **not that the browser kept the cookie**.
- `GET /private` with **the same `MockHttpSession`** proves the repository and authorization restore the principal.
- `@WithMockUser` or `with(user("learner"))` skips password verification; neither replaces form/Basic tests.
- A POST missing CSRF returning 403 must never be labeled "bad password".
- Basic 200 does not mean a browser form session was created; Basic can authenticate per request.

### 8.2. MockMvc Limitations

MockMvc exercises filters and controllers inside one application context, yet does not verify proxies, browser cookie flags (`Secure`/`SameSite`/`Domain`/`Path`), HTTPS termination, load balancers, Redis/JDBC Spring Session, network outages, OAuth2/OIDC `state`/`nonce`, or remote MFA. For incidents reproducible only in browsers/production, add staging E2E tests and scrubbed telemetry.

## 9. Diagnosing the Provider: From Username to PasswordEncoder

`DaoAuthenticationProvider` uses `UserDetailsService` and `PasswordEncoder`. A password the user recalls as "right" can fail to match the stored hash when:

1. `UserDetailsService` looks up the wrong user or tenant.
2. Legacy raw bcrypt lacks `{bcrypt}` while login uses `DelegatingPasswordEncoder` requiring `{id}`.
3. Stored hashes were truncated by a `VARCHAR(60)` column when `{bcrypt}`-prefixed hashes are 68 characters.
4. Registration encoded twice while login checks raw once.
5. Encoders/parameters/peppers differ between write and read, or nodes run mismatched config versions.
6. Client/backend applied `trim()`/lowercasing/Unicode normalization differently than at hash creation.
7. Account is disabled, locked, expired, or credentials-expired.
8. Live requests hit a different `SecurityFilterChain`/provider than tests.

**Safe experiment:** create a canary user on a test DB, register via the real path, inspect metadata format/length (without exporting hashes), test login via form/Basic, then restart/switch nodes and retry. If legacy raw hashes are verified to match a known algorithm, migrate `{id}` metadata under backups/transactions. If the hash cannot be identified, trigger secure password resets—**never enable `NoOpPasswordEncoder` or expose hashes via debug endpoints**.

~~~java
// Illustration inside a service holding rawPassword and storedEncodedPassword.
// Never log either variable.
boolean verified =
        passwordEncoder.matches(rawPassword, storedEncodedPassword);
~~~

Never do:

~~~java
// WRONG because password encoders use random salts.
boolean same = passwordEncoder.encode(rawPassword)
        .equals(storedEncodedPassword);
~~~

Even if `matches=true` in a unit test, HTTP calls can still fail at CSRF, role checks, lost sessions, or handlers. Interpret unit tests and HTTP integration tests at **two separate layers**.

## 10. SecurityContext: Why Did Redirect Succeed Yet the Next Request Is Anonymous?

In Spring Security 6, `SecurityContextHolderFilter` reads contexts from `SecurityContextRepository` without auto-saving arbitrary mutations at request end. **Built-in form login handles persistence**; custom controllers/filters own it explicitly:

~~~java
// Fragment in a custom controller after AuthenticationManager
// genuinely authenticated and session policy was applied.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verifiedAuthentication);
SecurityContextHolder.setContext(context);
repository.saveContext(context, request, response);
~~~

This snippet assumes `verifiedAuthentication`, `repository`, `request`, and `response` are properly typed and `repository` is **the exact same repository the filter reads**. Save before committing the HTTP response so session cookies are written. **Setting the holder without saving does not persist login.** Moreover, `saveContext` alone does not add session fixation protection, concurrent session limits, MFA, or remember-me; custom flows must invoke those policies or use built-in filters.

| Repository | Persists Across Independent HTTP Requests? | What to Check |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Yes, when session/cookie valid and saved | Session creation, ID rotation, expiry, backing store |
| `RequestAttributeSecurityContextRepository` | No, same request/dispatch only | Never use in place of session login |
| `DelegatingSecurityContextRepository` | Depends on delegates; 6.x default combines RequestAttribute + HttpSession | Filter and custom code share the same config |
| `NullSecurityContextRepository` | No | Fits stateless APIs; never use for session persistence |

When browsers drop cookies due to `SameSite`/`Domain`/`Path`/`Secure` or redirects hit a node lacking shared sessions, MockMvc passes while E2E fails. **Never alter stored password hashes to chase a cookie/proxy bug**.

## 11. HTTP Statuses Must Be Paired with Context

| HTTP / Redirect | Possible Cause | Does Not Prove Alone |
| --- | --- | --- |
| 200 from custom login POST | Handler wrote response body | Context restores on the next request |
| 200 from protected GET | That request authorized and controller OK | All other user actions succeed |
| 302 `/login` | Entry point prompting login | Password was rejected |
| 302 `/login?error` | Failure handler ran | Password definitely wrong (could be account/session policy) |
| 302 `/private` | Success handler redirected | Browser followed/kept cookie/has role |
| 401 HTTP Basic | Unauthenticated per API/entry point | Form login also fails for clients |
| 403 POST login | Commonly CSRF | Provider ran |
| 403 GET admin | Commonly authorization denied | Wrong password |
| 500 | Controller, filter, store, or handler exception | Issuer/encoder definitely broken |
| 502/504 at ingress | Proxy/gateway/upstream timeout | Request reached provider |

Reports must record **which request**, **authentication method**, **entry point/failure handler**, and **filter milestone**—never copy a bare status code alone.

## 12. Runbook for Five Classic Incidents

### A. Login POST Returns 403

**Observed:** `HTTP_ENTER` and `HTTP_EXIT=403`, zero provider success events. **Test:** `formLogin` helper (with CSRF) vs. raw POST without CSRF. **Fix:** ensure frontend fetches and sends the session-bound CSRF token; keep `CsrfFilter`. **Regression:** missing CSRF=403, valid CSRF+password=redirect, protected GET=200. Never disable CSRF across the chain.

### B. Right Password, POST Redirect Succeeds, Next GET Returns to /login

**Observed:** provider accepted and success handler ran. **Test:** second GET using the same `MockHttpSession`. If it passes, inspect browser cookies/proxies/session stores; if it fails inside MockMvc, check `SecurityContextRepository`, explicit save, and session policy. **Fix:** share the same repository and save properly in custom flows, or fix cookie/session backends. **Regression:** two-request test + E2E behind proxy.

### C. Login Succeeds Yet /admin Returns 403

**Observed:** user authenticated yet lacks `ROLE_ADMIN`/MFA. **Test:** same Basic credentials on `/api/me`=200 and `/admin`=403; admin account=200. **Fix:** fix role mapping or authorization policy if wrong; never grant admin arbitrarily. **Regression:** positive + negative authorization tests.

### D. A Cohort of Users Fails After Changing PasswordEncoder

**Observed:** only legacy records fail, not CSRF. **Test:** inspect encoded password IDs/lengths via secure internal metrics; run a canary account through registration→DB roundtrip→login. **Fix:** migrate verified raw bcrypt to `{bcrypt}`, map legacy encoders accurately, ensure wide columns; trigger resets if unrecoverable. **Regression:** hash cohorts and multi-node migration tests. Never use `{noop}`.

### E. HTTP Basic Returns 401 While Form UI Still Logs In

**Observed:** request hits API chain; Basic entry point. **Test:** `httpBasic(...)` with JSON `Accept`, provider events, rules/filter chains. **Fix:** fix chain/`httpBasic` config, user store, or input if evidenced; never enable sessions casually on stateless APIs. **Regression:** separate Basic 200/401/403 and browser form tests.

## 13. 30-Case Diagnostic Test Matrix

| ID | Scenario | Investigation Expectation |
| --- | --- | --- |
| D01 | Request never reaches service | Gather ingress/proxy evidence |
| D02 | Path/method misses login filter | Spot mapping mismatch |
| D03 | Multiple chains pick wrong chain | Fix matcher/order |
| D04 | POST `/login` missing CSRF | 403 before provider |
| D05 | Invalid CSRF | 403, not treated as bad password |
| D06 | Form right password | Provider accepts, handler redirects |
| D07 | Form wrong password | Failure event/handler, no authenticated session |
| D08 | Wrong username/tenant lookup | Spot user store mismatch |
| D09 | Locked/disabled account | Provider rejects even with right password |
| D10 | Stored hash missing `{id}` | Diagnose encoder metadata |
| D11 | Hash truncated/altered by DB converter | Canary roundtrip fails |
| D12 | Differing password normalization | Unicode/whitespace tests |
| D13 | Provider does not support token | `ProviderNotFound` / manager config |
| D14 | Session strategy rejects post-provider accept | Do not count login completed |
| D15 | Form success handler throws | Provider accepted yet response failed |
| D16 | Custom flow sets context without saving | Next request anonymous |
| D17 | Custom flow saves to right repository | Next request authenticated |
| D18 | Session cookie not sent back | Browser E2E login loop |
| D19 | Unshared session store across nodes | Fails when switching replicas |
| D20 | STATELESS bearer missing token next call | 401 is expected behavior |
| D21 | Valid HTTP Basic | 200 on matching endpoint |
| D22 | Invalid HTTP Basic | 401 via API entry point |
| D23 | Learner visits admin | 403 authorization |
| D24 | Admin visits admin | 200 |
| D25 | Form logout valid session | Session invalidated |
| D26 | Logout then send valid Basic | Authenticates fresh request |
| D27 | Provider success event yet browser skips redirect | Do not treat as completed login |
| D28 | Raw URL/cookie/credentials appear in logs | Security QA FAIL, remediate leak |
| D29 | `@WithMockUser` passes while form login fails | Mock skips provider testing |
| D30 | 5xx from controller/DB post-auth | Investigate app error, never reset password |

## 14. Post-Incident Report Template

| Field | Example for a CSRF Failure |
| --- | --- |
| Symptom | Browser login POST returned 403 after frontend change |
| Scope | `LOGIN` route, `POST` method, subset of browser clients |
| Observations | Filter probe recorded `HTTP_ENTER` and `HTTP_EXIT=403`, zero provider events |
| First failing boundary | `CsrfFilter` |
| Root cause | Frontend omitted the session-bound CSRF token |
| Fix | Restored CSRF handshake / request token header |
| Security checks | Kept CSRF enabled, zero raw passwords/cookies logged |
| Regression | Raw POST missing CSRF=403; `formLogin`=redirect; protected GET with session=200 |
| Residual risk | Needs browser E2E verifying proxy/cookies/sessions in staging |
| Closure | Reproduced failure before fix, tests/E2E passed after fix, stable metrics |

Reports need **stage-by-stage evidence**, exact changes made, regression tests, and residual risks. Writing "Spring Security broke" or "user mistyped password" without testing is insufficient.

## 15. Mistakes to Avoid

- **Reading only HTTP status** and editing `PasswordEncoder`: statuses may stem from CSRF, authorization, or entry points.
- **Disabling CSRF or setting `permitAll()` broadly** just to get unblocked: removes critical defenses.
- **Using `@WithMockUser`** as proof of password verification: bypasses the authentication provider.
- **Counting `AuthenticationSuccessEvent` as a completed login**: provider events prove neither session persistence nor client completion.
- **Asserting only POST login 200/302**: always follow up with a protected GET request.
- **Logging `Authentication`, requests/headers/tokens/passwords/hashes**: exposes credentials in log collectors and APMs.
- **Granting `ROLE_ADMIN` to all users** to silence 403s: breaks access control.
- **Enabling `NoOpPasswordEncoder`** to bypass hash errors: creates severe risk and hides migration bugs.
- **Confusing stateless Basic/JWT with session login**: a follow-up request without credentials is expected to be anonymous.
- **Ignoring session cookies/proxies** when MockMvc passes: run browser E2E tests.
- **Conflating app/controller 500s with provider rejections**: isolate exception stages without logging raw secrets.
- **Declaring victory after one successful request**: add regression tests and post-deploy monitoring.

## 16. Acceptance Checklist

- [ ] Verified exact request path, method, chain, CSRF, and auth mechanism.
- [ ] Stage auditing uses server-generated IDs and allowlisted routes/methods.
- [ ] Zero passwords, encoded hashes, JWTs, API keys, session IDs, recovery codes, `Cookie`, or `Authorization` values in logs.
- [ ] Provider events distinguish accepted/rejected without conflating them with business login completion.
- [ ] Tested `formLogin()`, `httpBasic()`, and CSRF for both positive and negative cases.
- [ ] Tested authenticated user lacking roles receiving HTTP 403.
- [ ] Tested a **second** protected request reusing the same `MockHttpSession`.
- [ ] Understand when custom flows require `SecurityContextRepository.saveContext`.
- [ ] Tested logout invalidates sessions without assuming Basic/JWT are revoked.
- [ ] Verified cookies, proxies, and distributed sessions via browser/staging E2E.
- [ ] Documented symptom/hypothesis/evidence table, first failing boundary, root cause, and regression tests.
- [ ] Never bypassed authentication, CSRF, MFA, or authorization to resolve errors.

## 17. References

- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — Authentication Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Testing Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html)
- [Spring Security 6.5 — Testing HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Security 6.5 — Testing Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/logout.html)
- [Spring Security 6.5 — CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
