# Filters Running Twice, Wrong Order, and Exceptions Not Reaching Handlers — Spring Security Servlet

## 1. Three Symptom Groups to Distinguish

In Spring MVC using Spring Security Servlet, an HTTP request passes through container Servlet filters, `DelegatingFilterProxy`, `FilterChainProxy`, `SecurityFilterChain`, and finally `DispatcherServlet`/controllers. When adding a custom filter, failures usually stem from **registration**, **ordering**, or **exception-handling boundaries**.

Typical symptoms:

- A filter emits two logs for one operation, yet it is unclear whether it truly ran twice.
- JWT/cookie validation logic runs in the servlet container and runs again inside the Spring Security chain.
- A filter tries to read `Authentication`, yet `SecurityContext` still has no principal.
- A filter populates `Authentication` too late, after authorization has already denied the request.
- A filter throws `AuthenticationException`, yet it never reaches `ExceptionTranslationFilter`.
- `@RestControllerAdvice` catches errors from controllers yet misses errors thrown from filters.
- One chain is configured properly, yet the actual URL enters a different chain.
- A request is re-dispatched under `DispatcherType.ERROR` or `ASYNC`.

This guide builds a layer-by-layer diagnostic mindset, fixes actual causes of duplication and misordering, routes exceptions to the right handlers, and provides Java 17+, Spring Boot 3.x, Spring Security 6.x, and MockMvc examples. This covers the **Servlet stack**, not WebFlux `WebFilter`.

## 2. Diagram: Servlet Filter Chain vs. Spring Security Filter Chain

~~~text
HTTP request
   |
   v
Servlet container
   |
   +--> Servlet Filter A
   |
   +--> DelegatingFilterProxy("springSecurityFilterChain")
   |          |
   |          v
   |       FilterChainProxy
   |          |
   |          +--> Select FIRST SecurityFilterChain matching request
   |          |
   |          +--> SecurityContext-related filters
   |          +--> CSRF/Authentication filters
   |          +--> ExceptionTranslationFilter
   |          +--> AuthorizationFilter
   |          |
   |          v
   |       Return to Servlet chain
   |
   +--> Servlet Filter B
   |
   v
DispatcherServlet
   |
   +--> MVC HandlerMapping/HandlerAdapter
   +--> Controller/Service
   +--> HandlerExceptionResolver/@ControllerAdvice
~~~

**Servlet filters** can be registered with the container via `FilterRegistrationBean`, `@WebFilter`, a Servlet initializer, or Spring Boot's auto-registration of `Filter` beans. **Security filters** are managed inside `FilterChainProxy` via `HttpSecurity` configuration or `addFilterBefore`/`addFilterAfter`/`addFilterAt`.

Spring Security can define **multiple `SecurityFilterChain` beans**, yet `FilterChainProxy` selects **the first chain** whose request matcher matches. It never accumulates filters across all matching chains.

Therefore ask: does a filter belong to the container chain, the security chain, or both? Does `@Order` apply to chain selection or container registration? Did an exception occur before or after `DispatcherServlet`?

## 3. “Twice” Means Twice of What?

Never conclude solely from log line counts. Several distinct scenarios exist:

1. The filter logs before and after `filterChain.doFilter`, emitting **two logs for one invocation**.
2. The client sent an `OPTIONS` preflight followed by `POST`, or the HTTP client retried.
3. The Servlet container dispatched the request to `ERROR` after an exception.
4. An async servlet request triggered an additional `ASYNC` dispatch.
5. Two separate filter instances were created via two `@Bean`s or `new`.
6. A `Filter` bean auto-registered with the container and was also passed to `addFilterBefore` in the security chain.
7. A plain `Filter` (not `OncePerRequestFilter`) has two registrations.
8. Filter code calls `filterChain.doFilter` twice, or both calls `sendError` and continues the chain.

Record safe diagnostic fields:

~~~text
requestId
dispatcherType = REQUEST / ERROR / ASYNC / ...
filterClass
filterInstanceIdentity
invocationStage
selectedChain
httpMethod
outcomeCode
~~~

Never log `Authorization` headers, `Cookie`, Bearer tokens, raw queries, or bodies just to prove how many times a filter ran.

**Definitions to distinguish:** `Filter.doFilter` calls, `OncePerRequestFilter.doFilterInternal` calls, servlet dispatches, and network requests do not necessarily have the same count.

## 4. `@Component` Filter Plus `addFilterBefore`: A Common Culprit

A suspicious configuration:

~~~java
@Component
public class CustomTokenFilter extends OncePerRequestFilter {
    // ... doFilterInternal(...)
}
~~~

Then in `SecurityConfig`:

~~~java
http.addFilterBefore(
    customTokenFilter,
    UsernamePasswordAuthenticationFilter.class
);
~~~

In Spring Boot Servlet, a `jakarta.servlet.Filter` bean **can be auto-registered** with the servlet container. Meanwhile, `addFilterBefore` adds the filter into the Spring Security chain. Without explicit control, the same filter can appear at both registration levels.

Understand carefully:

- If the same instance of `OncePerRequestFilter` is invoked **nested within one dispatch**, its already-filtered attribute can cause `doFilterInternal` to run only once.
- Two different instances, different filter names, or different dispatches can behave differently.
- Even when `doFilterInternal` runs only once, running at the **container position** instead of inside the security chain can still break `SecurityContext` or exception handling.
- A plain `Filter` implementation has no built-in already-filtered guard.

Therefore, do not claim `@Component` + `addFilterBefore` always makes `doFilterInternal` run twice. Inspect filter registrations, instance identity, and dispatcher type.

### 4.1. Fix A: Instantiate the Filter Only Inside `SecurityFilterChain`

If the filter does not need to be a `Filter` bean:

~~~java
@Bean
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().permitAll()
        )
        .addFilterBefore(
            new DiagnosticFilter(),
            UsernamePasswordAuthenticationFilter.class
        )
        .build();
}
~~~

This is an illustrative method requiring the `DiagnosticFilter` class and imports. `new DiagnosticFilter()` is created inside the chain, not as a Spring `Filter` bean auto-registered by Boot into the container. If services or counters are needed, pass dependencies via constructor; see Section 12 for a complete example.

### 4.2. Fix B: Keep the `Filter` Bean Yet Disable Servlet Registration

~~~java
@Bean
FilterRegistrationBean<CustomTokenFilter> disableContainerFilter(
        CustomTokenFilter filter) {

    FilterRegistrationBean<CustomTokenFilter> registration =
        new FilterRegistrationBean<>(filter);

    registration.setEnabled(false);
    return registration;
}
~~~

This illustrative method requires importing `org.springframework.boot.web.servlet.FilterRegistrationBean` and a matching `CustomTokenFilter` bean. The filter bean can still be passed to `addFilterBefore` in the security chain; disabling registration targets only servlet container registration.

Verify at runtime that no second registration or second filter instance exists. Never use this approach to disable infrastructure filters outside your scope.

## 5. `OncePerRequestFilter` Does Not Mean “Strictly Once Forever”

`OncePerRequestFilter` uses a request attribute (typically suffixed `.FILTERED`) to detect prior execution in certain dispatch contexts. Yet one HTTP request can undergo multiple dispatches.

| `DispatcherType` | Situation | What to Inspect |
| --- | --- | --- |
| `REQUEST` | Initial incoming request | Filter and request mapping |
| `ERROR` | Container error handling | Error dispatch mapping and `shouldNotFilterErrorDispatch` |
| `ASYNC` | Async servlet continuation | Async dispatch mapping and `shouldNotFilterAsyncDispatch` |
| `FORWARD` | Internal servlet forward | Registration mappings and filter instance |
| `INCLUDE` | Internal include | Registration mappings and context |

Hooks on `OncePerRequestFilter`:

~~~java
@Override
protected boolean shouldNotFilterAsyncDispatch() {
    return true;
}

@Override
protected boolean shouldNotFilterErrorDispatch() {
    return true;
}
~~~

These two methods are fragments inside a subclass. `OncePerRequestFilter` defaults typically skip async/error dispatches; applications may override them. These methods do not fix double registration—they only control whether the filter runs per dispatch type.

Additional questions: does `shouldNotFilter(request)` skip this route? Does `getAlreadyFilteredAttributeName` produce distinct names across instances? Does `FilterRegistrationBean` map the intended dispatcher types?

## 6. Three Kinds of Ordering

**Servlet Filter order:** container registration order (`FilterRegistrationBean` order, Servlet mappings, or `@Order` per auto-registration rules).

**`SecurityFilterChain` order:** `@Order` on `SecurityFilterChain` beans controls the order `FilterChainProxy` tests request matchers. Usually **only the first matching chain** runs.

**Filter order inside one `SecurityFilterChain`:** `HttpSecurity` DSL or `addFilterBefore`/`addFilterAfter`/`addFilterAt` controls relative positions of filters.

Putting `@Order` on a custom Servlet `Filter` bean is not the right way to move it inside Spring Security's chain. Likewise, changing `@Order` on a `SecurityFilterChain` does not reposition a custom filter relative to `ExceptionTranslationFilter`.

Two-chain example:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a
            .anyRequest().authenticated()
        )
        .build();
}

@Bean
@Order(2)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a
            .anyRequest().denyAll()
        )
        .build();
}
~~~

These are two illustrative methods; protecting a real API requires an authentication mechanism. An `/api/orders` request matching the `@Order(1)` chain does not additionally run filters from the fallback chain.

## 7. `securityMatcher` Differs from `requestMatchers`

The two DSL methods have different scopes:

- `http.securityMatcher("/api/**")` decides whether **the entire `SecurityFilterChain`** applies to the request.
- `authorizeHttpRequests(...requestMatchers("/api/admin/**").hasRole("ADMIN"))` decides authorization rules **inside the already-selected chain**.

If a chain only matches `/api/**`, an `/admin/**` rule inside that chain never applies to `/admin/home`. When a filter fails to run on an expected URL, check chain matchers before reordering filters.

A catch-all `@Order(1)` chain can hijack requests ahead of a specialized `@Order(2)` chain. Order specialized chains first with an explicit fallback policy, leaving no sensitive URLs outside all chains.

## 8. Filter Position Relative to `SecurityContext` and Authorization

A general functional flow:

~~~text
SecurityContext management
       |
       v
CSRF / security-related filters
       |
       v
Authentication filters (Basic / form / Bearer ...)
       |
       v
Anonymous/context/request-cache-related filters
       |
       v
ExceptionTranslationFilter
       |
       v
AuthorizationFilter
       |
       v
DispatcherServlet / Controller
~~~

This is not an immutable order across every version, but a responsibility map.

If a filter reads `Authentication` too early, it sees `null`/anonymous. If a filter builds `Authentication` too late, `AuthorizationFilter` may have already denied the request. If a filter throws `AuthenticationException` **before `ExceptionTranslationFilter`**, ETF cannot catch an upstream exception thrown before ETF wrapped downstream execution.

If a filter calls `response.sendError` or writes the body yet still calls `filterChain.doFilter`, downstream code can attempt to modify an already committed response. If a filter calls `chain.doFilter` twice, side effects can run twice.

Choose position by function. For JWT Resource Servers, use `oauth2ResourceServer` and the framework's authentication filters instead of hand-rolling a token parser missing signature, issuer, audience, or expiry checks.

## 9. `ExceptionTranslationFilter` Does Not Handle Every Error

`ExceptionTranslationFilter` (ETF) specifically translates `AuthenticationException` and `AccessDeniedException` thrown from the downstream chain it wraps into security responses.

- `AuthenticationEntryPoint` initiates authentication, typically 401 for HTTP APIs or a login redirect per config.
- `AccessDeniedHandler` handles insufficient permissions for authenticated users, typically 403.
- For anonymous requests, a downstream `AccessDeniedException` may be routed to the entry point rather than always returning 403.
- ETF does not automatically convert `RuntimeException`, `IOException`, or other programming bugs into 401/403.

Scope diagram:

~~~text
Upstream custom authentication filter
    |
    +--> throws AuthenticationException (ETF not yet invoked)
    |    => downstream ETF cannot catch backward
    |
    v
ExceptionTranslationFilter
    |
    +--> try: downstreamFilterChain.doFilter(...)
    |
    +--> catch AuthenticationException / AccessDeniedException
    |
    v
AuthorizationFilter and downstream filters
~~~

Standard authentication filters typically manage their own `FailureHandler`/`EntryPoint`. When a custom filter runs ahead of ETF, implement error handling inside that component or use the framework's built-in authentication architecture.

## 10. Runnable Java 17: The `try`/`catch` Boundary

This is a pure-JDK program **simulating a call stack**, not Spring Security internal code.

File `FilterBoundaryDemo.java`:

~~~java
public class FilterBoundaryDemo {

    interface Chain {
        void run();
    }

    static void upstream(boolean fail, Chain next) {
        if (fail) {
            throw new IllegalStateException("UPSTREAM");
        }
        next.run();
    }

    static void translate(Chain downstream) {
        System.out.println("translator:enter");

        try {
            downstream.run();
        } catch (IllegalStateException ex) {
            System.out.println(
                "translator:caught=" + ex.getMessage()
            );
        }
    }

    public static void main(String[] args) {
        System.out.println("CASE_DOWNSTREAM");

        upstream(false, () ->
            translate(() -> {
                throw new IllegalStateException("DOWNSTREAM");
            })
        );

        System.out.println("CASE_UPSTREAM");
        try {
            upstream(true, () ->
                translate(() -> System.out.println("never"))
            );
        } catch (IllegalStateException ex) {
            System.out.println("outer:caught=" + ex.getMessage());
        }
    }
}
~~~

Compile and run:

~~~bash
javac FilterBoundaryDemo.java
java FilterBoundaryDemo
~~~

Exact stdout:

~~~text
CASE_DOWNSTREAM
translator:enter
translator:caught=DOWNSTREAM
CASE_UPSTREAM
outer:caught=UPSTREAM
~~~

In `CASE_DOWNSTREAM`, the exception is thrown inside the call wrapped by `translate`, so the translator catches it. In `CASE_UPSTREAM`, the error happens before `translate` is called, so only the outer catch receives it. That is why `ExceptionTranslationFilter` cannot catch exceptions thrown by filters positioned before it.

## 11. `@ControllerAdvice` Does Not Automatically Catch Servlet Filter Errors

`@RestControllerAdvice` and `@ExceptionHandler` are Spring MVC mechanisms operating through `DispatcherServlet` and `HandlerExceptionResolver`. A Servlet filter can throw an exception **before the request ever reaches `DispatcherServlet`**.

~~~text
Servlet Filter throws RuntimeException
    |
    +--> DispatcherServlet has not handled the request yet
         @ControllerAdvice typically never sees the error

Servlet Filter lets request proceed
    |
    v
DispatcherServlet -> Controller throws RuntimeException
    |
    v
HandlerExceptionResolver / @ControllerAdvice can handle it
~~~

Never assume two exceptions of the same class are handled identically regardless of where they were thrown.

Classification:

| Error | Appropriate Handling Location |
| --- | --- |
| Authentication failure inside an authentication filter | `AuthenticationFailureHandler` or `AuthenticationEntryPoint` |
| Authorization failure downstream of ETF | `ExceptionTranslationFilter` / `AccessDeniedHandler` |
| `RequestRejectedException` from `HttpFirewall` | `RequestRejectedHandler` on `FilterChainProxy` |
| Missing/invalid CSRF token | `CsrfFilter`'s access-denied handling |
| Exception inside a controller | `HandlerExceptionResolver` / `@ControllerAdvice` |
| `RuntimeException` in a Servlet filter outside MVC | Filter/container error handling or an explicitly designed adapter |

A filter can deliberately invoke `HandlerExceptionResolver` if designed and tested to do so; it does not happen automatically and is not a universal fix for security exceptions.

## 12. Spring Boot Demo: `DiagnosticFilter` Only Inside the Security Chain

Java 17+ Spring Boot 3.x project dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Place the classes in package `demo.filterdiagnostics` in a project with a matching Spring Boot plugin/BOM and Gradle wrapper.

### 12.1. Main Class

File `FilterDiagnosticsApplication.java`:

~~~java
package demo.filterdiagnostics;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterDiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(FilterDiagnosticsApplication.class, args);
    }
}
~~~

### 12.2. Counter Bean

File `ProbeCounter.java`:

~~~java
package demo.filterdiagnostics;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Component;

@Component
public class ProbeCounter {

    private final AtomicInteger count = new AtomicInteger();

    public void mark() {
        count.incrementAndGet();
    }

    public int get() {
        return count.get();
    }

    public void reset() {
        count.set(0);
    }
}
~~~

The counter illustrates sequential test counts. Under concurrent production traffic, a global counter cannot prove per-request execution counts; use request-correlated context or metrics instead.

### 12.3. `DiagnosticFilter` Without Being a Spring Bean

File `DiagnosticFilter.java`:

~~~java
package demo.filterdiagnostics;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public class DiagnosticFilter extends OncePerRequestFilter {

    private final ProbeCounter counter;

    public DiagnosticFilter(ProbeCounter counter) {
        this.counter = counter;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        counter.mark();

        // Do not log Authorization/Cookie or raw query for debugging.
        filterChain.doFilter(request, response);
    }
}
~~~

Do not annotate `DiagnosticFilter` with `@Component`, `@WebFilter`, or register a `FilterRegistrationBean` in this demo. It is instantiated via `new` inside `SecurityFilterChain` so Boot does not auto-register it as a container `Filter` bean. The filter invokes `chain.doFilter` **exactly once**.

### 12.4. `SecurityConfig`: Two Chains

File `SecurityConfig.java`:

~~~java
package demo.filterdiagnostics;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(
            HttpSecurity http,
            ProbeCounter counter) throws Exception {

        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().permitAll()
            )
            .addFilterBefore(
                new DiagnosticFilter(counter),
                UsernamePasswordAuthenticationFilter.class
            )
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallback(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().permitAll()
            )
            .build();
    }
}
~~~

`/api/ping` matches the `@Order(1)` chain and runs `DiagnosticFilter`; `/status` enters the fallback chain without `DiagnosticFilter`. `permitAll` serves only to demonstrate chain selection and filter counting, **not production policy**.

### 12.5. Controller

File `ProbeController.java`:

~~~java
package demo.filterdiagnostics;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {

    @GetMapping("/api/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/status")
    public String status() {
        return "ok";
    }
}
~~~

### 12.6. MockMvc Tests Asserting Filter Execution Count

File `src/test/java/demo/filterdiagnostics/DiagnosticFilterIntegrationTest.java`:

~~~java
package demo.filterdiagnostics;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DiagnosticFilterIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ProbeCounter counter;

    @BeforeEach
    void resetCount() {
        counter.reset();
    }

    @Test
    void apiRequestInvokesFilterOnce() throws Exception {
        mvc.perform(get("/api/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));

        assertEquals(1, counter.get());
    }

    @Test
    void fallbackRequestDoesNotInvokeApiFilter() throws Exception {
        mvc.perform(get("/status"))
            .andExpect(status().isOk())
            .andExpect(content().string("ok"));

        assertEquals(0, counter.get());
    }
}
~~~

Run with Gradle wrapper:

~~~bash
./gradlew test --tests demo.filterdiagnostics.DiagnosticFilterIntegrationTest
~~~

In the sample configuration, both tests are expected to pass; no fixed verbatim Gradle stdout is claimed. This test measures ordinary GET requests in MockMvc, not proof that every `ERROR`/`ASYNC` dispatch or production proxy produces the same invocation count.

## 13. When a Filter Must Be a Spring Bean

When a custom filter needs injected services, you can define it as a bean and **disable servlet registration**:

~~~java
@Bean
MyTokenFilter myTokenFilter(MyDependency dependency) {
    return new MyTokenFilter(dependency);
}

@Bean
FilterRegistrationBean<MyTokenFilter> filterRegistration(
        MyTokenFilter filter) {

    FilterRegistrationBean<MyTokenFilter> registration =
        new FilterRegistrationBean<>(filter);

    registration.setEnabled(false);
    return registration;
}

@Bean
SecurityFilterChain chain(
        HttpSecurity http,
        MyTokenFilter filter) throws Exception {

    return http
        .authorizeHttpRequests(a -> a
            .anyRequest().authenticated()
        )
        .addFilterBefore(
            filter,
            UsernamePasswordAuthenticationFilter.class
        )
        .build();
}
~~~

These are fragments requiring `MyTokenFilter`/`MyDependency` types, imports, and authentication configuration, not a standalone runnable program. Goal: the bean can be injected into the security chain without also being registered as a Servlet filter outside `FilterChainProxy`.

Never try to work around duplicate runs with a `static boolean` already-ran flag: shared mutable state across requests causes race conditions and can skip authentication for other users.

## 14. How Should Custom Authentication Filters Handle Errors?

A custom authentication filter upstream of `ExceptionTranslationFilter` needs proper failure handling; within `SecurityFilterChain`, prefer Spring Security's built-in authentication filters.

The following Java pseudocode fragment shows **catching only authentication-step errors** without swallowing downstream failures:

~~~java
Authentication authenticated;

try {
    authenticated =
        authenticationManager.authenticate(inputAuthentication);
} catch (AuthenticationException ex) {
    SecurityContextHolder.clearContext();
    entryPoint.commence(request, response, ex);
    return;
}

SecurityContext context =
    SecurityContextHolder.createEmptyContext();

context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);

filterChain.doFilter(request, response);
~~~

This belongs inside a filter with configured `authenticationManager`, `inputAuthentication`, `entryPoint`, `request`, `response`, and `filterChain`. It is **not a complete JWT verifier**. Never write a custom provider that accepts tokens without verifying signature, issuer, audience, and expiry.

Never wrap `filterChain.doFilter` carelessly inside the `try/catch AuthenticationException`, or you risk catching downstream errors not owned by your custom filter. After `entryPoint.commence`, always `return` instead of continuing the chain once the response has been handled.

## 15. Why Do Exceptions Fail to Reach the Expected Handler?

Checklist of causes to inspect:

1. The filter threw the error **before ETF**, so ETF never wrapped it.
2. The exception is a generic `RuntimeException` or `IOException`, outside ETF's handled types.
3. The filter caught/swallowed the exception and wrote its own status.
4. The filter wrote a 401/403 response yet still invoked downstream, causing committed-response conflicts.
5. The failure happened in a Servlet filter outside `FilterChainProxy`.
6. `HttpFirewall` rejected the request before the chain started, requiring a `RequestRejectedHandler`.
7. `DispatcherServlet` never ran, so `@ControllerAdvice` never participated.
8. The wrong `SecurityFilterChain` was selected due to matcher or `@Order`.
9. The filter called `chain.doFilter` twice or failed to call it on a required branch.
10. The exception occurred during an `ERROR`/`ASYNC` dispatch with different filter mappings from the initial request.

HTTP 401/403/500 are only symptoms; determine **which component actually produced the response**. With CSRF, `CsrfFilter` handles `AccessDeniedException` on its own and may return 403 before ETF. For an anonymous request hitting `AccessDeniedException` downstream, the entry point may be invoked; 403 is not always the sole outcome.

## 16. Controlled Chain Debugging

In test environments, you can temporarily enable:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
logging.level.org.springframework.security=DEBUG
~~~

Never enable broad TRACE/DEBUG in production without auditing what gets logged—especially tokens, `Cookie`, principals, and paths/queries. Log only server-generated request IDs, dispatcher types, filter classes, event codes, and selected chains where needed.

Helpful breakpoints:

- `DelegatingFilterProxy.doFilter`: inspect servlet registration.
- `FilterChainProxy.doFilter`: inspect matchers and selected chain.
- `OncePerRequestFilter.doFilter`/`doFilterInternal`: inspect anti-duplication attributes.
- `ExceptionTranslationFilter.doFilter`: verify the `try`/`catch` boundary.
- `AuthorizationFilter.doFilter`: inspect access decisions.
- `AuthenticationEntryPoint.commence` / `AccessDeniedHandler.handle`.
- `DispatcherServlet.doDispatch` and `HandlerExceptionResolver`.
- `HttpFirewall`/`RequestRejectedHandler` if rejected up front.

In MockMvc, check whether `springSecurityFilterChain` was manually attached **a second time** alongside auto-configuration. Never draw root-cause conclusions from a test setup that diverges from production.

## 17. Regression Testing Matrix

| Case | Expectation |
| --- | --- |
| `GET /api/ping` | `DiagnosticFilter.doFilterInternal` runs once |
| `GET /status` | `DiagnosticFilter` does not run |
| Two chains with overlapping matchers | First chain by `@Order` is selected |
| Filter bean + `addFilterBefore` | Redundant container registration detected |
| Non-bean filter | Exists solely in security chain |
| `REQUEST` to `ERROR` dispatch | Dispatcher types distinguished; not counted as two network requests |
| Async dispatch | Matches `shouldNotFilterAsyncDispatch` and mappings |
| Controller throws | Handled by `@ControllerAdvice` when resolver matches |
| Upstream Filter throws | Does not automatically reach MVC advice |
| `AuthenticationException` upstream of ETF | Handled by appropriate auth failure handler/entry point |
| `AccessDeniedException` downstream of ETF | ETF delegates to entry point or denied handler |
| `RequestRejectedException` | Handled by configured `RequestRejectedHandler` |
| Filter calls `sendError` then returns | Controller is not invoked |
| Filter calls `doFilter` twice | Test catches duplicate downstream execution |

Do not assert only HTTP status; verify which filters ran, which handler processed errors, and whether business data saw duplicate side effects.

## 18. Common Mistakes

**Unintentional double registration:** `@Component Filter` can auto-register with the container while `addFilterBefore` also inserts it into the security chain.

**Misunderstanding `OncePerRequestFilter`:** it does not guarantee single execution across every dispatcher type or separate instances.

**Confusing orderings:** `@Order` on `SecurityFilterChain` differs from internal security filter position and container `Filter` order.

**Confusing matchers:** `securityMatcher` selects the chain; `requestMatchers` inside the chain sets authorization rules.

**Wrong `try`/`catch` boundary:** ETF catches only matching downstream exceptions, never upstream filter errors.

**Misunderstanding `@ControllerAdvice`:** MVC handlers do not automatically wrap all filters.

**Broken response flow:** calling `sendError`/`entryPoint` and still calling `doFilter`, or calling `doFilter` twice.

**Mapping every failure to 401:** masks programming/IO bugs as authentication errors and slows debugging.

**Debugging with tokens:** logging `Authorization`/`Cookie`/JWTs to confirm a filter ran leaks credentials.

## 19. Effective Diagnostic Checklist

- [ ] Confirm whether there was one or multiple HTTP requests (retries/preflight).
- [ ] Check dispatcher type: `REQUEST`, `ERROR`, `ASYNC`, or `FORWARD`.
- [ ] Identify Servlet `Filter` beans/instances and container registrations.
- [ ] Audit `@Component`, `@WebFilter`, `FilterRegistrationBean`, and `addFilterBefore`.
- [ ] Inspect once-filter attributes, `shouldNotFilter`, and dispatcher mappings.
- [ ] Identify which `SecurityFilterChain` was selected by `@Order` and `securityMatcher`.
- [ ] Verify filter position relative to `SecurityContext`, authentication, ETF, and `AuthorizationFilter`.
- [ ] Identify the actual exception class and throw site.
- [ ] Use the right `AuthenticationEntryPoint`, `AccessDeniedHandler`, `RequestRejectedHandler`, or MVC advice.
- [ ] Never call `filterChain.doFilter` after writing a response and returning.
- [ ] Assert execution counts and actual handlers in tests, not just HTTP status.
- [ ] Log only safe diagnostic metadata and disable TRACE after investigation.

## 20. Review Questions and Conclusion

**Q1.** Why can a `Filter` bean passed to `addFilterBefore` cause wrong execution order?

Because a `Filter` bean can be auto-registered with the Servlet container in addition to joining the Spring Security chain. The two registration levels occupy different positions.

**Q2.** Does ETF catch exceptions thrown in a filter ahead of it?

Not by default. ETF only wraps its downstream chain; upstream filters need their own failure handling.

**Q3.** Does `@ControllerAdvice` catch every Servlet filter exception?

No. It belongs to Spring MVC and may not be active when an exception arises before `DispatcherServlet`.

**Q4.** Do two log lines prove a filter ran twice?

No. Distinguish before/after logging, separate network requests, dispatch types, filter instances, and `doFilterInternal` counts.

**Q5.** Does changing `@Order` on a `SecurityFilterChain` change internal filter order?

No. It changes chain evaluation order, not filter positions inside a chain.

**Conclusion:** To diagnose filters running twice, wrong order, or exceptions missing handlers, separate **Servlet registration**, **`SecurityFilterChain` selection**, **filter ordering**, **dispatcher lifecycles**, and **exception catch boundaries**. Give custom filters a single registration path, invoke the downstream chain once, delegate errors to the right authentication/authorization/MVC handlers, and verify exact invocation counts with MockMvc.
