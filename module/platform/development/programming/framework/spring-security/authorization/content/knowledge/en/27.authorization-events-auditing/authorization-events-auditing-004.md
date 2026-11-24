# Registering Listeners and Verifying Where Events Are Published in Spring Security Authorization

A useful audit record must answer **which authorization decision occurred, at which layer, and at what time**. In Servlet-based Spring Security, denial events can originate from URL-based permission checks in the filter chain, from checks before invoking a service (`@PreAuthorize`), or from checks after the service returns a result (`@PostAuthorize`). Registering an `@EventListener` only solves **receiving** events; to determine **where they are published**, you must enable the right `AuthorizationEventPublisher`, inspect the event's target object, examine the call stack, and write tests for each branch.

This lesson uses **Java 17+, Spring Boot 3.5.x / Spring Security 6.5.x** with the Spring MVC/Servlet model. Package, class, and endpoint names in the example are declared in full so they can be placed into a Spring Boot Maven project with the corresponding dependencies. If using Spring Security 7.x or another branch, check the API/Javadoc for the exact version running.

## 1. Distinguishing Authorization Events from Authentication and Business Audits

| Signal | What is it used to know? | Common source | Automatically emitted in all cases? |
| --- | --- | --- | --- |
| `AuthorizationDeniedEvent` | An `AuthorizationManager` made a **deny** decision | `AuthorizationFilter`, method security interceptors | Only when a publisher is configured on that path |
| `AuthorizationGrantedEvent` | A **grant** decision | Same permission checkpoints | **Not published by default** by `SpringAuthorizationEventPublisher` on 6.5 |
| `AuthenticationSuccessEvent`, `AbstractAuthenticationFailureEvent` | Login/authentication succeeded or failed | `AuthenticationManager`/authentication provider | Requires the corresponding `AuthenticationEventPublisher` mechanism |
| `AccessDeniedException` / HTTP 403 | Request was rejected during processing | Filter, method, CSRF, or application layer | **Not synonymous** with a guaranteed `AuthorizationDeniedEvent` |
| Business audit | Who modified which data, before/after, what impact? | Business code or a dedicated audit system | Cannot be fully inferred from permission-check events |

**Do not confuse names:** `AuthorizationDeniedEvent` belongs to `org.springframework.security.authorization.event`, distinct from authentication events in `org.springframework.security.authentication.event` and legacy events in `org.springframework.security.access.event` (many APIs deprecated).

`AuthorizationEventPublisher` is the interface Spring Security uses to publish authorization events. `SpringAuthorizationEventPublisher` is the adapter forwarding to Spring's `ApplicationEventPublisher` so `@EventListener` or `ApplicationListener` can receive them. Having a listener bean **without a publisher** on the authorization path can result in receiving nothing.

## 2. At Which Exact Stage Are Events Published?

~~~text
HTTP request
  |
  v
SecurityFilterChain: authentication filters, CSRF, ...
  |
  v
AuthorizationFilter / AuthorizationManager (URL policy)
  |-- deny -----> AuthorizationEventPublisher
  |                '-- AuthorizationDeniedEvent
  |                         '-- Spring ApplicationEventPublisher -> @EventListener
  |-- grant ----> continue (grant events are not published by default)
  v
DispatcherServlet -> Controller -> Spring-proxied Service
                                  |
                                  +-- AuthorizationManagerBeforeMethodInterceptor
                                  |      @PreAuthorize: check before method
                                  |      deny -> AuthorizationDeniedEvent -> listener
                                  |      grant -> method runs
                                  |
                                  '-- method returns result
                                        |
                                        v
                                     AuthorizationManagerAfterMethodInterceptor
                                       @PostAuthorize: check after method
                                       deny -> AuthorizationDeniedEvent -> listener
                                       grant -> return result
~~~

Source verification table:

| Decision location | Class to inspect in debugger | Protected object typically in `event.getObject()` | When denied |
| --- | --- | --- | --- |
| URL check | `AuthorizationFilter#doFilter` | `HttpServletRequest` | Controller has **not** been called |
| `@PreAuthorize` | `AuthorizationManagerBeforeMethodInterceptor#invoke` | `MethodInvocation` | Target method has **not** run |
| `@PostAuthorize` | `AuthorizationManagerAfterMethodInterceptor#invoke` | Method result context, typically `MethodInvocationResult` | Target method **has** run |
| Handing event to Spring | `SpringAuthorizationEventPublisher#publishAuthorizationEvent` | The object passed by the permission checkpoint | Publisher decides whether to publish |
| Listener receiving event | `@EventListener` on a Spring bean | `AuthorizationDeniedEvent<?>` | Executes after the publish call (usually same thread if multicaster is synchronous) |

`AuthorizationFilter` is typically near the end of the Security filter chain and runs **before** Spring MVC. With method security, Spring AOP proxies create interceptors for `@PreAuthorize`/`@PostAuthorize`; `@EnableMethodSecurity` must be enabled. Instantiating a service with `new` or self-invocation within the same class can bypass the proxy and therefore emit no method authorization events.

**Be careful about counts:** one HTTP request can pass through both URL and method checks. If the URL denies, the service is not called. If the URL grants but the service denies, the observed event comes from the method layer. With `FORWARD`, `ERROR`, or `ASYNC` dispatches and multiple interceptors, decision counts can differ from external network request counts; **do not assume "one request = one event"**.

## 3. Registering the Publisher in the Right Place

In a Spring Boot project with `spring-boot-starter-web`, `spring-boot-starter-security`, and Java 17+, use the following files, all in package `com.example.securityaudit`. `@EnableMethodSecurity` enables method security; the publisher bean serves authorization checkpoints integrated with Spring Security.

**`src/main/java/com/example/securityaudit/SecurityAuditApplication.java`**

~~~java
package com.example.securityaudit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class SecurityAuditApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityAuditApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/securityaudit/SecurityConfiguration.java`**

~~~java
package com.example.securityaudit;

import jakarta.servlet.DispatcherType;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher springEvents) {
        return new SpringAuthorizationEventPublisher(springEvents);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
            .requestMatchers("/api/admin").hasAuthority("ADMIN")
            .requestMatchers("/api/report", "/api/post")
                .hasAuthority("WEB_USER")
            .anyRequest().denyAll()
        );
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("web-only")
                .password("{noop}demo123")
                .authorities("WEB_USER")
                .build(),
            User.withUsername("reader")
                .password("{noop}reader123")
                .authorities("WEB_USER", "REPORT_READ", "RESULT_VIEW")
                .build()
        );
    }
}
~~~

In this example, `/api/admin` requires `ADMIN`, so the demo user is denied right at the filter. `/api/report` and `/api/post` require only `WEB_USER` at the filter so requests can reach the service, where finer-grained rules live. `DispatcherType.ERROR` is permitted so error handling does not turn into a new denial during error dispatch; this is a demo-specific choice, and real projects must review policies for each dispatcher type. `{noop}` is solely for illustration; never use it as a production password configuration.

**Why must `AuthorizationEventPublisher` be registered?** `SpringAuthorizationEventPublisher` is the publishing mechanism supported by Spring Security. In Spring Security 6.5, it **publishes only denials** by default, avoiding heavy publishing on every grant. When debugging, **not seeing events for 200 responses** is therefore normal; it does not prove the listener is broken.

## 4. Registering the Listener and Recording Safe Context

Create a `@Component` with `@EventListener`. Use `event.getObject()` to classify the source rather than substituting `event.getSource()`: `getObject()` is the API representing the object under permission check.

The example stores marks in memory for testing and logs **limited metadata**. In production, the in-memory store must be replaced with an audit mechanism that has appropriate retention, read access control, and data protection.

**`src/main/java/com/example/securityaudit/AuthorizationAuditListener.java`**

~~~java
package com.example.securityaudit;

import java.util.List;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import jakarta.servlet.http.HttpServletRequest;
import org.aopalliance.intercept.MethodInvocation;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.security.authorization.method.MethodInvocationResult;
import org.springframework.stereotype.Component;

@Component
public class AuthorizationAuditListener {

    private static final Logger log =
        LoggerFactory.getLogger(AuthorizationAuditListener.class);

    public record Mark(String stage, String operation) {}

    private final Queue<Mark> marks = new ConcurrentLinkedQueue<>();

    @EventListener
    public void denied(AuthorizationDeniedEvent<?> event) {
        Object target = event.getObject();
        Mark mark;

        if (target instanceof HttpServletRequest request) {
            // Demo uses fixed URLs only, with no query/PII.
            mark = new Mark(
                "HTTP",
                request.getMethod() + " " + request.getRequestURI()
            );
        } else if (target instanceof MethodInvocationResult after) {
            mark = new Mark(
                "METHOD_AFTER",
                after.getMethodInvocation().getMethod().getName()
            );
        } else if (target instanceof MethodInvocation before) {
            mark = new Mark(
                "METHOD_BEFORE",
                before.getMethod().getName()
            );
        } else {
            // Custom AuthorizationManager may use another object type.
            mark = new Mark("OTHER",
                target == null ? "unknown" : target.getClass().getSimpleName());
        }

        marks.add(mark);
        log.info("authorization.denied stage={} operation={}",
                 mark.stage(), mark.operation());
    }

    public List<Mark> snapshot() {
        return List.copyOf(marks);
    }

    public void clear() {
        marks.clear();
    }
}
~~~

This listener **does not** log `Authentication#getCredentials()`, cookies, `Authorization` headers, payloads, method return values, or raw `HttpServletRequest`/`MethodInvocation` objects. In real applications, paths containing user/tenant IDs or secrets must also be normalized before storage; here the endpoints have no ID variables, so the URI is logged directly. Inferring `METHOD_BEFORE`/`METHOD_AFTER` from the object type is an effective observation aid for the 6.5 demo; with custom publishers/managers, **inspect the actual object type and call stack** and expand the classifier accordingly.

`ApplicationListener<AuthorizationDeniedEvent<?>>` can be used instead of `@EventListener`; both must be Spring-managed beans. `@EventListener` is convenient when one or a few specialized handlers are needed. Note that Spring's default `ApplicationEventMulticaster` delivers events synchronously on the same thread; if the project configures an executor/`@Async`, listeners may run asynchronously, so timing, ordering, and `SecurityContextHolder` on the new thread will differ.

## 5. Creating Three Scenarios to Verify the Publishing Layer

**`src/main/java/com/example/securityaudit/ReportService.java`**

~~~java
package com.example.securityaudit;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    private final AtomicInteger beforeCalls = new AtomicInteger();
    private final AtomicInteger afterCalls = new AtomicInteger();

    @PreAuthorize("hasAuthority('REPORT_READ')")
    public String readReport() {
        beforeCalls.incrementAndGet();
        return "REPORT-42";
    }

    @PostAuthorize("hasAuthority('RESULT_VIEW')")
    public String readSensitiveResult() {
        afterCalls.incrementAndGet();
        return "SENSITIVE";
    }

    public int beforeCalls() {
        return beforeCalls.get();
    }

    public int afterCalls() {
        return afterCalls.get();
    }
}
~~~

**`src/main/java/com/example/securityaudit/AuditController.java`**

~~~java
package com.example.securityaudit;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class AuditController {

    private final ReportService reports;

    public AuditController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/admin")
    public String admin() {
        return "ADMIN";
    }

    @GetMapping("/report")
    public String report() {
        return reports.readReport();
    }

    @GetMapping("/post")
    public String post() {
        return reports.readSensitiveResult();
    }
}
~~~

Cases when using `web-only/demo123`:

1. `GET /api/admin`: the user has `WEB_USER` but lacks `ADMIN`. `AuthorizationFilter` denies; the controller does not run. The listener is expected to see `Mark("HTTP", "GET /api/admin")`.
2. `GET /api/report`: the URL allows because `WEB_USER` is present, but `@PreAuthorize` requires `REPORT_READ` and denies **before** `readReport()`. The listener is expected to see `Mark("METHOD_BEFORE", "readReport")`.
3. `GET /api/post`: the URL allows; `readSensitiveResult()` executes; `@PostAuthorize` requires `RESULT_VIEW` and denies **after** the method. The listener is expected to see `Mark("METHOD_AFTER", "readSensitiveResult")`.

When using `reader/reader123`, both `/api/report` and `/api/post` return their normal content. Because the default publisher emits only denials, the listener records no grant events for these two paths.

At denial points, publishing an event and returning an HTTP status are two separate responsibilities. `AuthorizationDeniedEvent` is published when the authorization manager/interceptor decides to deny; `AccessDeniedException` (or the corresponding exception) is translated to 403/challenge by the security exception-handling mechanism. A successful listener **does not** itself determine the HTTP status; a controller directly returning `ResponseEntity.status(403)` also does not automatically publish an authorization event.

## 6. Automated Testing of Event Origin with MockMvc and Listener

Add `spring-boot-starter-test` and `spring-security-test` in `test` scope; application dependencies remain as before. Use `@WithMockUser` to simulate the exact authorities and `@Autowired` beans through Spring proxies. Counters in the service prove whether the method **did/did not** run; `AuthorizationAuditListener.snapshot()` proves the listener received the event.

**`src/test/java/com/example/securityaudit/AuthorizationAuditTests.java`**

~~~java
package com.example.securityaudit;

import jakarta.servlet.http.HttpServletRequest;
import org.aopalliance.intercept.MethodInvocation;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.event.ApplicationEvents;
import org.springframework.boot.test.context.event.RecordApplicationEvents;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@RecordApplicationEvents
class AuthorizationAuditTests {

    @Autowired MockMvc mvc;
    @Autowired ReportService service;
    @Autowired AuthorizationAuditListener listener;
    @Autowired ApplicationEvents publishedEvents;

    @BeforeEach
    void clearAudit() {
        listener.clear();
    }

    @Test
    @WithMockUser(authorities = "WEB_USER")
    void requestDenialComesFromHttpLayer() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isForbidden());

        assertTrue(listener.snapshot().stream().anyMatch(m ->
            m.stage().equals("HTTP")
                && m.operation().equals("GET /api/admin")));

        assertTrue(publishedEvents.stream(AuthorizationDeniedEvent.class)
            .anyMatch(e -> e.getObject() instanceof HttpServletRequest));
    }

    @Test
    @WithMockUser(authorities = "WEB_USER")
    void preAuthorizeDenialOccursBeforeServiceCall() throws Exception {
        int calls = service.beforeCalls();
        mvc.perform(get("/api/report"))
            .andExpect(status().isForbidden());

        assertEquals(calls, service.beforeCalls());
        assertTrue(listener.snapshot().stream().anyMatch(m ->
            m.stage().equals("METHOD_BEFORE")
                && m.operation().equals("readReport")));

        assertTrue(publishedEvents.stream(AuthorizationDeniedEvent.class)
            .anyMatch(e -> e.getObject() instanceof MethodInvocation));
    }

    @Test
    @WithMockUser(authorities = "WEB_USER")
    void postAuthorizeDenialOccursAfterServiceCall() throws Exception {
        int calls = service.afterCalls();
        mvc.perform(get("/api/post"))
            .andExpect(status().isForbidden());

        assertEquals(calls + 1, service.afterCalls());
        assertTrue(listener.snapshot().stream().anyMatch(m ->
            m.stage().equals("METHOD_AFTER")
                && m.operation().equals("readSensitiveResult")));
    }

    @Test
    @WithMockUser(authorities = {
        "WEB_USER", "REPORT_READ", "RESULT_VIEW"
    })
    void approvedCallsDoNotCreateDeniedEvents() throws Exception {
        mvc.perform(get("/api/report"))
            .andExpect(status().isOk())
            .andExpect(content().string("REPORT-42"));

        mvc.perform(get("/api/post"))
            .andExpect(status().isOk())
            .andExpect(content().string("SENSITIVE"));

        assertTrue(listener.snapshot().isEmpty());
        assertFalse(publishedEvents.stream(AuthorizationDeniedEvent.class)
            .findAny().isPresent());
    }
}
~~~

Execute in a Maven project with the Spring Boot plugin and dependencies listed above:

~~~bash
./mvnw test
~~~

On Windows, run `mvnw.cmd test`. Four tests are **expected** to pass. `publishedEvents` data comes from Spring Boot's `@RecordApplicationEvents`, verifying that real events passed through the Spring application event bus; `listener.snapshot()` verifies that the listener handled them. A real project has synchronous events and sequential tests by default like the example. If you enable an async event multicaster or JUnit parallel test execution, add await mechanisms/test isolation instead of immediate assertions and a shared queue.

**Why not just check 403?** All three denied tests can return the same 403. Status alone **does not distinguish** URL filter, `@PreAuthorize`, and `@PostAuthorize`. The pair of evidence `event.getObject()` + service counter pinpoints the emission source without guessing from the status code.

## 7. Self-Verifying When Running the Application

Start in the Maven project:

~~~bash
./mvnw spring-boot:run
~~~

Then call each endpoint, for example with `curl`:

~~~bash
# URL path: denied at AuthorizationFilter
curl -s -o /dev/null -w '%{http_code}\n' \
  -u web-only:demo123 http://localhost:8080/api/admin

# @PreAuthorize path: denied before readReport()
curl -s -o /dev/null -w '%{http_code}\n' \
  -u web-only:demo123 http://localhost:8080/api/report

# @PostAuthorize path: denied after readSensitiveResult()
curl -s -o /dev/null -w '%{http_code}\n' \
  -u web-only:demo123 http://localhost:8080/api/post

# User with sufficient permissions: no denied event
curl -s -o /dev/null -w '%{http_code}\n' \
  -u reader:reader123 http://localhost:8080/api/report
~~~

**Expected** stdout (one line per command):

~~~text
403
403
403
200
~~~

In the application logs, look for the message `authorization.denied stage=... operation=...` produced by the listener itself. Other log parts (timestamp, thread, Spring Security DEBUG...) depend on configuration and are not shown as fixed stdout. Logical traces to look for:

~~~text
authorization.denied stage=HTTP operation=GET /api/admin
authorization.denied stage=METHOD_BEFORE operation=readReport
authorization.denied stage=METHOD_AFTER operation=readSensitiveResult
~~~

The three lines above are **sample messages with logger prefixes stripped**, not actual captured run logs. If your observations differ, use `getObject().getClass()` and the debugger to identify the exact context type in your version and configuration.

## 8. Inspecting with a Debugger: Which Breakpoint Answers Which Question?

Set breakpoints in application code or Spring Security source matching your dependency version:

1. `AuthorizationFilter#doFilter`: inspect request/dispatcher and the `AuthorizationManager` invocation. If denied here, the controller has not run.
2. `AuthorizationManagerBeforeMethodInterceptor#invoke`: inspect `MethodInvocation` and the pre-method decision. When denied, the target method has not run.
3. `AuthorizationManagerAfterMethodInterceptor#invoke`: inspect the actual return value and the post-method decision. If denied, the method code has already executed.
4. `SpringAuthorizationEventPublisher#publishAuthorizationEvent`: inspect the authentication supplier, target object, and result; check whether the publisher intentionally drops grant events.
5. `ApplicationEventPublisher#publishEvent` / `SimpleApplicationEventMulticaster#multicastEvent`: verify the event left the publisher and was dispatched to application listeners.
6. `AuthorizationAuditListener#denied`: inspect the type of `event.getObject()`, the stage inferred by the listener, and the executing thread.

If a breakpoint in `AuthorizationFilter` hits but `SpringAuthorizationEventPublisher` does not, check the bean and wiring; the checkpoint may also be using another publisher or the rule may not be producing a concrete decision. If the publisher breakpoint hits but the listener does not, check `@Component`, component scanning, the subscribed event type, and Spring application event configuration. If the listener runs multiple times, check dispatcher types, number of interceptors, security filter chains, and internal request paths.

Diagnostic logging can be temporarily enabled:

~~~yaml
logging:
  level:
    org.springframework.security.web.access.intercept.AuthorizationFilter: TRACE
    org.springframework.security.authorization.method: TRACE
~~~

This is observational logging; it **does not** replace event testing, and specific log messages vary by version. Keep TRACE/DEBUG levels in test environments only for as long as needed, avoiding sensitive data exposure and excessive log volume in production.

## 9. API Versions and Conditions for Events to Appear

- `AuthorizationEventPublisher` and `SpringAuthorizationEventPublisher` have existed since Spring Security **5.7**, though overloads and result types changed across versions. In **6.4+**, the API added `AuthorizationResult`; older overloads taking `AuthorizationDecision` have been marked deprecated in newer branches. Do not copy a publisher implementation from the 7.x branch into 6.2 or 6.5 expecting compatible signatures.
- `AuthorizationDeniedEvent#getObject()` and `getAuthentication()` expose the protected object and identity supplier; `getAuthorizationResult()` was added in **6.4**. If supporting older versions, check the Javadoc. Do not log raw `Authentication`, credentials, arguments, or return values.
- In Spring Security **6.5**, `SpringAuthorizationEventPublisher` publishes denial events; grants are not published by default. In the **7.0+** branch, the publisher offers a result-publishing predicate option (`setShouldPublishResult` per the corresponding Javadoc); to audit grants in 6.5, design a **custom publisher** and bound event volume rather than merely adding `@EventListener(AuthorizationGrantedEvent.class)`.
- Method security configuration must be enabled via `@EnableMethodSecurity`, and HTTP request authorization needs `authorizeHttpRequests` flowing through `AuthorizationFilter`. With legacy security using `FilterSecurityInterceptor`/`AccessDecisionManager`, event names and emission points can differ.
- Authentication failure events require their own publisher (such as `DefaultAuthenticationEventPublisher`). A request with a wrong password rejected by an authentication filter **may never reach** `AuthorizationFilter`; thus having no `AuthorizationDeniedEvent` is expected.
- Wrong/missing CSRF tokens can be rejected before authorization; controllers/services explicitly returning 403, throwing exceptions, or routes returning 404 also do not automatically become authorization events.

## 10. Designing Reliable Auditing: Points Not to Miss

**Do not use listeners to change permission decisions.** Listeners receive events from an already-made decision, not a place to modify `AuthorizationManager`. A listener that throws exceptions or runs slowly can cause request errors/latency when executed synchronously. If sending events to a message broker or SIEM, use a delivery mechanism that does not block requests and includes retry, deduplication, and dropped-event monitoring strategies.

**Require correlation IDs and safe action identifiers.** For HTTP requests, pass request IDs/tracing context from filters. For method events, use normalized method names and operation/business keys; do not serialize the entire `MethodInvocation` or returned objects. When the multicaster runs async, MDC and `SecurityContextHolder` may not automatically follow threads: extract needed metadata at publish time or configure explicit context propagation.

**No exactly-once guarantee.** Forward/error dispatches, retries, multiple checks per request, multiple application instances, and listener failures can all cause duplicates or gaps. For legally/transactionally auditable trails, design idempotency, persistence, and a transactional outbox (when appropriate) at the business layer; the default `ApplicationEventPublisher` is an in-process event bus, not a durable audit store.

**Do not equate status codes with emission sites.** `403` can come from URL, method, CSRF, or business rules; `401` usually belongs to an authentication challenge; `200` can be a grant or a fallback from a handler masking data; `404` can be a nonexistent route or a resource-hiding policy. Only the event object, call stack, and test scenarios pinpoint the exact source.

**Include negative tests.** Test missing publisher, method security not enabled, service invoked via `new`/`this`, wrong filter chain, wrong bean scope, login failure, CSRF denial, and `ERROR` dispatch requests. There is no need to force every failure to emit the same event; the goal is to understand each layer's exact responsibility.

## 11. Implementation and Acceptance Checklist

- [ ] Verify the `spring-security-*` version present in the dependency tree and use documentation for the matching branch.
- [ ] Register the `AuthorizationEventPublisher` bean (e.g., `new SpringAuthorizationEventPublisher(applicationEventPublisher)`).
- [ ] Register a Spring bean listener via `@Component + @EventListener` or `ApplicationListener`.
- [ ] Enable `@EnableMethodSecurity` if you want to receive events from `@PreAuthorize`/`@PostAuthorize`.
- [ ] Design at least three distinct scenarios: URL deny, method-before deny, and method-after deny.
- [ ] Inspect `event.getObject()` and the call stack rather than inferring emission source solely from HTTP status.
- [ ] Test with Spring-managed proxies + `@WithMockUser` and observe method invocation counters too.
- [ ] Verify `AuthorizationGrantedEvent` does not appear by default on Spring Security 6.5.
- [ ] Separate authentication failures, CSRF denials, and domain 403/404s from authorization events.
- [ ] Redact sensitive data, bound event volume, standardize correlation IDs, and account for concurrency/dispatch.
- [ ] For mandatory durable audits: design dedicated storage, retries, deduplication, and appropriate access controls.

## Official Documentation

1. [Spring Security 6.5 — Authorization Events](https://www.springframework.org/spring-security/reference/6.5/servlet/authorization/events.html): how to register publishers, listeners, and why grants are not published by default.
2. [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `AuthorizationFilter`, request checkpoints, and dispatchers.
3. [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity`, pre/post method interceptors, and denials.
4. [Spring Security 6.5 Javadoc — AuthorizationEventPublisher](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationEventPublisher.html): event publishing contract and shift from `AuthorizationDecision` to `AuthorizationResult`.
5. [Spring Security 6.5 Javadoc — AuthorizationDeniedEvent](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authorization/event/AuthorizationDeniedEvent.html): `getObject()`, `getAuthentication()`, and decision details.
6. [Spring Security — Authentication Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html): publishers/listeners for authentication events.
7. [Spring Boot — Testing Application Events](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@RecordApplicationEvents` and `ApplicationEvents`.

When answering "where was the event published?", reliable evidence consists of the **denied rule**, the **corresponding checkpoint in the call stack**, the **type of `event.getObject()`**, and **tests proving whether the method ran**. A 403 status code or a listener log line alone is insufficient to distinguish these layers.
