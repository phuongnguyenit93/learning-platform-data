# Avoiding Double Filter Registration Across Spring Boot and Spring Security

## 1. Objectives and Common Pitfall

In a Spring Boot application using the Servlet web stack and Spring Security, a custom `Filter` can enter **two different processing chains**:

- The **Servlet filters** chain managed by embedded Tomcat/Jetty/Undertow.
- The **Security filters** chain inside Spring Security's `FilterChainProxy`.

When a class implementing `jakarta.servlet.Filter` is annotated with `@Component` or declared as a `@Bean`, Spring Boot can **automatically register it as a Servlet container filter**. If that same instance is also added via `HttpSecurity.addFilterBefore/addFilterAfter/addFilterAt`, the filter can be invoked **twice** on a single request, at different positions and orders. This is a wiring/registration issue rather than necessarily a bug in `doFilter`.

Typical consequences:

- Audit logs or metrics recorded twice; events published twice.
- Downstream calls, token parsing, billing, or data updates executed repeatedly.
- Tracing headers/context set and cleared multiple times.
- Security logic running before authentication context is ready, or running outside the security matcher.
- Request/response wrappers applied in multiple layers.
- Certain requests failing only on ERROR/ASYNC dispatches, making bugs hard to reproduce.
- Developers using `OncePerRequestFilter` see `doFilterInternal` run once and assume no duplicate registration exists, even though two registrations are active.

Goals of this lesson: distinguish both chains, reproduce the root cause, fix it cleanly via `FilterRegistrationBean.setEnabled(false)` or avoiding a Filter bean, verify via HTTP integration tests, understand `OncePerRequestFilter`, `securityMatcher`, dispatcher types, and considerations for multiple `SecurityFilterChain`s.

**Example versions:** Java 17+, Spring Boot 3.3.x, Spring Security 6.x, and Servlet web stack. Spring Boot 4 / Spring Security 7 introduce some API, starter/dependency, and configuration changes; consult the official documentation for your target version before migrating code. This lesson does not cover WebFlux `SecurityWebFilterChain` except when comparing boundaries.

## 2. Two-Layer Filter Diagram

A typical request:

~~~text
Client HTTP request
        |
        v
Embedded Servlet Container (Tomcat/Jetty)
        |
        v
Servlet Filter A
        |
        v
DelegatingFilterProxy ("springSecurityFilterChain")
        |
        v
Spring Bean: FilterChainProxy
        |
        +--> First matching SecurityFilterChain
                 |
                 +--> SecurityContextHolderFilter
                 +--> authentication-related filters
                 +--> custom security filter
                 +--> AuthorizationFilter
                 +--> ...
        |
        v
Servlet Filter B
        |
        v
DispatcherServlet -> Controller
        |
        v
HTTP response
~~~

This diagram is a generalized view; exact ordering depends on configuration and enabled filters. A Servlet Filter can sit **before or after** `DelegatingFilterProxy`. It does not necessarily have the same security context as a filter inside `SecurityFilterChain`.

Three key names to remember:

- **DelegatingFilterProxy:** A Filter registered with the Servlet container that delegates calls to a named Spring-managed bean. For Spring Security, the target bean is typically `springSecurityFilterChain`.
- **FilterChainProxy:** The Spring Security bean holding the list of `SecurityFilterChain`s and selecting which chain applies to a request.
- **SecurityFilterChain:** A list of Security Filters handling requests matching that chain's `RequestMatcher`.

`SecurityFilterChain` **is not** a Servlet `FilterRegistrationBean`. Spring Boot registers standalone filter beans on the outer Servlet chain; Spring Security inserts filters into its internal chain. Thus, a class appearing in both places is not two aliases for one registration.

## 3. Why Do @Component or @Bean Cause Duplicates?

Suppose we write a filter:

~~~java
@Component
public class TokenInspectionFilter
        extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        // Read/inspect request metadata.
        chain.doFilter(request, response);
    }
}
~~~

In a Spring Boot Servlet app, `@Component` creates a Spring bean of type `Filter`. Boot detects `Filter` beans and registers them with the embedded servlet container. Meanwhile, security config adds:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        TokenInspectionFilter tokenFilter) throws Exception {

    http.authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated());

    http.addFilterBefore(
            tokenFilter,
            UsernamePasswordAuthenticationFilter.class);

    return http.build();
}
~~~

This is a **risky configuration example**, without real authentication wired. The exact same filter instance is registered once with the container and used once by `SecurityFilterChain`. Exact execution order depends on filter registration order and security chain order.

Spring Security documentation explicitly states that Filter beans (`@Component` or `@Bean`) are auto-registered with the container by Spring Boot, so also adding them to a `SecurityFilterChain` can cause them to be invoked twice. The docs recommend not declaring a Filter bean if unnecessary; if dependency injection is needed, register a `FilterRegistrationBean` with `enabled=false`.

### 3.1. Two Registrations Do Not Necessarily Mean Two Instances

When `@Component` and `HttpSecurity` share the same injected object, there is **one object** with **two entry paths** into `doFilter`. Thus, having bean count = 1 does not prove registration count = 1.

Conversely, if you both annotate `TokenInspectionFilter` with `@Component` and instantiate `new TokenInspectionFilter()` for security, **two separate objects** with the same logic exist. Disabling registration on one object will not fix the other; inspect the entire configuration.

### 3.2. Why Do Logs Sometimes Appear Only Once?

`OncePerRequestFilter` uses a request attribute to avoid calling `doFilterInternal` twice within a single matching dispatch. When **the same filter** is called twice in a nested fashion, the guard may skip the second invocation. Yet both registrations still exist, ordering can still be wrong, and behavior can diverge on ERROR/ASYNC dispatches or with filters not extending `OncePerRequestFilter`.

Never rely on the number of log lines inside `doFilterInternal` to prove a filter is registered only once. Always inspect container registrations and security chains.

## 4. Ways to Register a Filter in Spring Boot

| Approach | Who Owns Lifecycle/Registration? | When to Use |
| --- | --- | --- |
| `@Component` on Filter | Boot auto-registers with Servlet container | Broad infrastructure filter at the Servlet layer |
| `@Bean` returning Filter | Boot auto-registers with Servlet container | Same as above, instantiated via configuration |
| `@Bean FilterRegistrationBean<T> enabled=true` | Boot registers explicitly with container with URL/order/dispatcher | Servlet-only filter needing explicit mapping control |
| `@WebFilter` + `@ServletComponentScan` | Servlet component scanning / container registration | Projects using the Servlet component model |
| `HttpSecurity.addFilterBefore/After/At` | Spring Security `FilterChainProxy` | Security logic inside a `SecurityFilterChain` |
| `FilterRegistrationBean<T> enabled=false` | **Disables** container registration for a Filter bean | Filter is a Spring bean but runs only inside the security chain |
| `new CustomFilter(...)` inside `HttpSecurity` config | `FilterChainProxy` receives instance without creating a Servlet bean | Security filter needing no standalone bean |

Warning: `@WebFilter` behaves according to how Servlet component scanning is enabled/deployed; never mix it with `@Component` and another `FilterRegistrationBean` for the same logic.

**Each filter should have a single primary owner.** If it is Servlet infrastructure running before security decisions, manage it via container registration. If it relies on security context and security matchers, manage it via `HttpSecurity`. Avoid combining both simply because both compile.

## 5. Option A: Security-Only Filter That Is Not a Spring Bean

The simplest approach is instantiating the filter directly when configuring `SecurityFilterChain`:

~~~java
@Configuration(proxyBeanMethods = false)
class SecurityConfig {

    @Bean
    SecurityFilterChain security(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .anyRequest().authenticated());

        http.addFilterBefore(
                new MySecurityAuditFilter(),
                AuthorizationFilter.class);

        return http.build();
    }
}
~~~

`MySecurityAuditFilter` implements `Filter` and is instantiated via `new`, with **no `@Component` and no `@Bean` returning that instance**. Because it is not a Servlet Filter bean, Boot will not auto-register it with the container. It is managed solely by the security chain configuration.

If the filter requires dependency injection, pass services via its constructor:

~~~java
@Bean
SecurityFilterChain security(
        HttpSecurity http,
        AuditService auditService) throws Exception {

    MySecurityAuditFilter audit =
            new MySecurityAuditFilter(auditService);

    http.authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated());

    http.addFilterBefore(audit, AuthorizationFilter.class);
    return http.build();
}
~~~

`AuditService` is a hypothetical dependency to define; this is an architectural snippet. Even when the filter is not a bean, the configuration method accepts Spring beans and passes them down. Avoid having filters look up `ApplicationContext` arbitrarily; explicit constructor injection makes testing easier.

**Lifecycle note:** Because the filter is not a standalone Spring bean, do not rely on `@PostConstruct`, `@PreDestroy`, `@Autowired` fields, or `@ConfigurationProperties` on the filter itself being processed by Boot as for Beans. If bean lifecycle management is required, configure explicitly or use Option B.

## 6. Option B: Filter Is a Bean, Disable Container Registration

When you need injection, metrics, or Bean lifecycle management for a security-only custom filter, Spring Security/Spring Boot recommend:

~~~java
@Bean
FilterRegistrationBean<MySecurityAuditFilter> disableAutoRegistration(
        MySecurityAuditFilter filter) {

    FilterRegistrationBean<MySecurityAuditFilter> registration =
            new FilterRegistrationBean<>(filter);
    registration.setEnabled(false);
    return registration;
}
~~~

Combined with:

~~~java
@Bean
MySecurityAuditFilter securityAuditFilter(
        AuditService auditService) {
    return new MySecurityAuditFilter(auditService);
}

@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        MySecurityAuditFilter filter) throws Exception {

    http.authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated());

    http.addFilterBefore(filter, AuthorizationFilter.class);
    return http.build();
}
~~~

In these two snippets, `MySecurityAuditFilter` and `AuditService` are hypothetical classes to define. Key semantics:

1. **One Filter Bean:** The bean exists for dependency injection.
2. **FilterRegistrationBean targets that exact instance:** Boot sees the registration wrapper for that filter with `enabled=false`, so it skips mapping that filter onto the Servlet container.
3. **HttpSecurity adds the filter to SecurityFilterChain:** The filter executes at the position defined by `addFilterBefore/After`.
4. **Do not touch Spring Security's DelegatingFilterProxy:** That proxy must remain registered with the Servlet container so `SecurityFilterChain` runs.

Disabling registration here **does not disable the security filter inside Spring Security**. It only prevents the second Servlet container registration for that custom Filter bean.

### 6.1. Why Not Use registration.setOrder(...) Instead of enabled=false?

`FilterRegistrationBean#setOrder` adjusts **Servlet filter order**. It does not remove the registration and does not change the filter's position inside `SecurityFilterChain`. If the filter remains in both places, changing order merely moves the two executions to different points.

For a security-only filter: call `setEnabled(false)` on the container registration, then use `addFilterBefore/After` for security ordering.

### 6.2. Why Must FilterRegistrationBean Point to the Exact Bean?

If you already have:

~~~java
@Bean
MySecurityAuditFilter auditFilter() {
    return new MySecurityAuditFilter();
}
~~~

but then write:

~~~java
@Bean
FilterRegistrationBean<MySecurityAuditFilter> disabled() {
    FilterRegistrationBean<MySecurityAuditFilter> registration =
            new FilterRegistrationBean<>(
                    new MySecurityAuditFilter());
    registration.setEnabled(false);
    return registration;
}
~~~

this broken configuration constructs a second object inside the registration bean. It **does not guarantee** auto-registration of the actual `auditFilter` Bean is disabled. Always inject the exact Bean into the `FilterRegistrationBean` constructor.

## 7. Hands-On Project: Proving the Filter Runs Only Once

The complete example below uses Java 17+, Spring Boot 3.3.x, Spring Security 6.x, embedded Tomcat, and a **real HTTP server**. The custom `RequestAuditFilter` intentionally extends `GenericFilterBean` instead of `OncePerRequestFilter` so the test observes exact `doFilter` invocation counts. It performs no authentication, merely recording the per-request call count in a response header.

The API exposes `GET /api/hello` publicly and requires authentication on other paths under an illustrative rule. This is purely for learning filter registration; **it is not a production security template**.

Structure:

~~~text
filter-registration-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        example/
          filters/
            FilterRegistrationDemoApplication.java
            HelloController.java
            RequestAuditFilter.java
            SecurityConfiguration.java
      resources/
        application.yml
    test/
      java/
        example/
          filters/
            FilterRegistrationDemoTests.java
~~~

### 7.1. settings.gradle

~~~groovy
rootProject.name = 'filter-registration-demo'
~~~

### 7.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '1.0.0'

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

Only the Servlet MVC starter is included; do not add `spring-boot-starter-webflux`. Boot 3.3 requires Java 17 or newer. Generate a Gradle Wrapper compatible with Boot 3.3; if an existing project has build conventions, follow your project's managed versions rather than copying the demo versions.

### 7.3. application.yml

~~~yaml
spring:
  application:
    name: filter-registration-demo

server:
  port: 8080
~~~

### 7.4. FilterRegistrationDemoApplication.java

~~~java
package example.filters;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterRegistrationDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                FilterRegistrationDemoApplication.class, args);
    }
}
~~~

### 7.5. HelloController.java

~~~java
package example.filters;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/api/hello")
    public Map<String, String> hello() {
        return Map.of("message", "hello");
    }
}
~~~

There is a single public GET endpoint. Avoid putting real tokens or secrets in the demo to prevent forming habits of logging or echoing sensitive data.

### 7.6. RequestAuditFilter.java

~~~java
package example.filters;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.GenericFilterBean;

public class RequestAuditFilter extends GenericFilterBean {

    private static final String ATTR =
            RequestAuditFilter.class.getName() + ".count";

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        Integer previous = (Integer) request.getAttribute(ATTR);
        int count = previous == null ? 1 : previous + 1;
        request.setAttribute(ATTR, count);

        if (response instanceof HttpServletResponse http) {
            http.setHeader(
                    "X-Audit-Filter-Calls", Integer.toString(count));
        }

        chain.doFilter(request, response);
    }
}
~~~

The counter is stored in a **ServletRequest attribute** rather than a singleton field. It stays isolated per request, keeping tests independent of execution order or concurrent requests. If the same filter is called a second time during the same request/dispatch, the final header normally becomes 2.

This is purely a lab observation filter, not an authentication filter or production audit system. In real apps, never trust unauthenticated client-accessible headers as security evidence. When a filter emits external events, enforce idempotency and data protection.

### 7.7. SecurityConfiguration.java

~~~java
package example.filters;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    RequestAuditFilter requestAuditFilter() {
        return new RequestAuditFilter();
    }

    @Bean
    FilterRegistrationBean<RequestAuditFilter> disableContainerAudit(
            RequestAuditFilter filter) {

        FilterRegistrationBean<RequestAuditFilter> registration =
                new FilterRegistrationBean<>(filter);

        registration.setEnabled(false);
        return registration;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RequestAuditFilter filter) throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(
                        HttpMethod.GET, "/api/hello")
                .permitAll()
                .anyRequest()
                .authenticated());

        http.addFilterBefore(
                filter,
                AuthorizationFilter.class);

        return http.build();
    }
}
~~~

This is the **correct** configuration for a security-only custom filter:

- `requestAuditFilter()` creates exactly one Filter Bean, with no `@Component`.
- `disableContainerAudit(...)` receives **that same Bean** and disables its Servlet registration.
- `securityFilterChain(...)` inserts that Bean into Spring Security before `AuthorizationFilter`.
- `springSecurityFilterChain` configured by Spring Security/Boot remains active as the Servlet proxy in the container.
- `GET /api/hello` is permitted so clients can test without credentials. Other paths require authentication; the demo omits a user store or login flow for them.

The filter sits before `AuthorizationFilter`, though since it only stamps a header, the example does not depend on a specific authentication state. For filters needing an authenticated user, position them **after authentication filters** per Security architecture and test explicitly. Never place an authentication/authorization filter arbitrarily just because a filter class name exists.

### 7.8. FilterRegistrationDemoTests.java

~~~java
package example.filters;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FilterRegistrationDemoTests {

    @Autowired
    TestRestTemplate rest;

    @Autowired
    FilterRegistrationBean<RequestAuditFilter> registration;

    @Test
    void containerRegistrationIsDisabled() {
        assertFalse(registration.isEnabled());
    }

    @Test
    void filterInvokedExactlyOnceOverHttp() {
        ResponseEntity<String> response =
                rest.getForEntity("/api/hello", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals(
                "1",
                response.getHeaders()
                        .getFirst("X-Audit-Filter-Calls"));

        String body = response.getBody();
        assertNotNull(body);
        assertTrue(body.contains("\"hello\""));
    }

    @Test
    void anotherGetStillHasOneInvocation() {
        ResponseEntity<String> response =
                rest.getForEntity("/api/hello", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals(
                "1",
                response.getHeaders()
                        .getFirst("X-Audit-Filter-Calls"));
    }
}
~~~

The first test verifies the registration wrapper has `enabled=false`. The next two tests start a **real embedded HTTP server** on a random port, send requests over TCP, and read the header set by the filter. Real HTTP tests carry far more weight than unit tests calling `doFilter` directly, because both Servlet registration and Spring Security registration must be verified.

These assertions are expected to pass with the right Spring Boot/Spring Security versions and code. If tests fail, inspect actual startup logs and exceptions rather than assuming the source proves success. This lesson provides the source and expected outcomes; it does not claim Gradle was executed in the learner's environment.

Run:

~~~bash
./gradlew test
~~~

Or on Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Start manually:

~~~bash
./gradlew bootRun
~~~

HTTP call:

~~~bash
curl -i http://localhost:8080/api/hello
~~~

Expected response: HTTP 200, JSON containing `message="hello"`, and response header:

~~~http
X-Audit-Filter-Calls: 1
~~~

No dependency on JSON key ordering or random ID values is required.

## 8. Reproducing the Double Registration Bug in a Controlled Way

On a separate lab branch, **strictly for observation and never for deployment**, temporarily remove `disableContainerAudit(...)` while keeping `RequestAuditFilter` as a `@Bean` and keeping `addFilterBefore`.

Now:

1. Spring Boot discovers the Filter Bean and auto-registers it as a Servlet Filter.
2. Spring Security `FilterChainProxy` receives the same Bean via `HttpSecurity.addFilterBefore`.
3. When `GET /api/hello` traverses both integration points, `GenericFilterBean#doFilter` can be invoked twice.
4. `X-Audit-Filter-Calls` can become `2` instead of `1`.
5. The `filterInvokedExactlyOnceOverHttp` integration test fails, confirming the bug.

Be precise: **actual runtime outcomes depend on Servlet Filter order, dispatcher types, and request routing**; do not assert every environment always produces `2` for every URI. Still, whenever two active registrations cover the same request, the risk of double invocation is real.

After experimenting, **restore `disableContainerAudit()` before further use**, re-run tests, and verify the header returns `1`. Never leave workaround skip flags in business logic just to mask the symptom.

### 8.1. Why Use GenericFilterBean in This Experiment?

`GenericFilterBean` exposes direct `doFilter` invocations. With `OncePerRequestFilter`, the already-filtered attribute guard can skip the second `doFilterInternal` call during nested executions, making logs inside `doFilterInternal` look like it ran only once. That does not mean the configuration is right.

Production filters may extend `OncePerRequestFilter` for proper once-per-dispatch semantics; infrastructure tests must verify **how many places the filter is registered**, not merely how often an internal callback executes.

## 9. OncePerRequestFilter: Helpful, but Does Not Fix Duplicate Registration

`OncePerRequestFilter` resides in `org.springframework.web.filter`. It provides `doFilterInternal(HttpServletRequest, HttpServletResponse, FilterChain)` and uses a request attribute to mark the request as already filtered within a given dispatch.

Example:

~~~java
public class RequestIdFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        response.setHeader(
                "X-Request-Id", UUID.randomUUID().toString());
        chain.doFilter(request, response);
    }
}
~~~

This is an illustrative snippet; import `jakarta.servlet.*`, `jakarta.servlet.http.*`, `java.io.IOException`, `UUID`, and `OncePerRequestFilter`.

**Two separate questions:**

- Is the filter **registered in exactly one place**? Check Servlet registrations and `SecurityFilterChain`.
- Does the filter execute its logic **once per request/dispatch as intended**? Check `OncePerRequestFilter` and async/error dispatch behavior.

Never answer the first question using the second. `OncePerRequestFilter` helps guard logic across dispatches, yet it neither disables auto-registration nor fixes ordering relative to authentication/authorization.

### 9.1. Already-Filtered Marker and Multiple Instances

`OncePerRequestFilter` typically builds an attribute tied to the filter's name to avoid re-running. When multiple filter instances, classes, or bean names exist—or requests span different dispatches—the guard can behave unexpectedly. Never design a system relying on two broken duplicate registrations coincidentally sharing the same marker.

If two distinct objects perform the same job with different attribute names, `doFilterInternal` runs on both. Keeping a single owner/registration is always the right fix.

### 9.2. ASYNC and ERROR Dispatches

A Servlet request can generate `REQUEST`, `ASYNC`, `ERROR`, `FORWARD`, or `INCLUDE` dispatches depending on container/config. `OncePerRequestFilter` offers `shouldNotFilterAsyncDispatch()` and `shouldNotFilterErrorDispatch()`; `FilterRegistrationBean` also configures dispatcher types.

A filter can legitimately run on two dispatches **without double registration**. Therefore, when observing >1 invocations, also log dispatcher type and request identity (never secrets) to distinguish:

- Invoked twice in the same dispatch due to duplicate registration.
- Invoked once in `REQUEST` and once in `ASYNC`/`ERROR` as configured.
- Two distinct HTTP requests (e.g., browser requesting a favicon).
- Internal forwards or error routing.

Never use an un-scoped global static counter to prove duplicate registration.

## 10. What Does FilterRegistrationBean#setEnabled(false) Actually Do?

Its purpose is preventing the **Servlet container from automatically adding the custom Filter Bean**. It does not alter:

- Spring Security creating `FilterChainProxy`.
- `DelegatingFilterProxy` invoking `FilterChainProxy`.
- `HttpSecurity.addFilterBefore/After` ordering.
- Matching of a `SecurityFilterChain`.
- `doFilter` logic inside the Filter Bean.
- Authorization policies.
- `FilterRegistrationBean`s for any other filters.

If Spring Security does not add that Filter to any chain, setting `enabled=false` ensures the filter **runs neither on the Servlet container nor anywhere else**. Always verify both halves of the configuration.

Conversely, if a filter only belongs at the Servlet layer and has nothing to do with security, **do not** set `enabled=false`; let Boot register it or use an `enabled=true` `FilterRegistrationBean`, and **do not** add it to `SecurityFilterChain`.

### 10.1. When You Need FilterRegistrationBean enabled=true

Example Servlet-only filter scoped to specific URLs:

~~~java
@Bean
FilterRegistrationBean<CorrelationFilter> correlationRegistration() {
    FilterRegistrationBean<CorrelationFilter> registration =
            new FilterRegistrationBean<>(new CorrelationFilter());

    registration.addUrlPatterns("/api/*");
    registration.setOrder(10);
    return registration;
}
~~~

`CorrelationFilter` is a hypothetical class; this snippet only illustrates container-level registration. For this kind of filter, do not also call `HttpSecurity.addFilterBefore/After`. If a separate `@Bean CorrelationFilter` exists, prevent Boot from auto-registering that extra instance too. Manage instance creation consistently from one source.

### 10.2. Different setOrder Methods Are Not Equivalent

- `FilterRegistrationBean#setOrder`: position in the **Servlet chain** for a registration.
- `@Order` on a `SecurityFilterChain` bean: evaluation priority among multiple **SecurityFilterChains**.
- `HttpSecurity.addFilterBefore/After/At`: position **inside one SecurityFilterChain**.
- `@Order` on a Servlet Filter class/Bean per Boot rules: influences Boot's container registration order, not security chain position.

Using the wrong "coordinate system" for ordering will never fix duplicate registration.

## 11. Choosing Where to Place Custom Filters in Spring Security

Spring Security maintains an ordered sequence of filters by role. Use:

~~~java
http.addFilterBefore(myFilter, AuthorizationFilter.class);
http.addFilterAfter(myFilter, AnonymousAuthenticationFilter.class);
http.addFilterAt(myFilter, SomeKnownFilter.class);
~~~

These lines show **independent alternatives**, not three calls to combine on the same filter. `SomeKnownFilter` is a placeholder for a known framework-supported filter class; do not use that literal name in code.

Guidelines:

- Need authentication context: place the filter after the relevant authentication filters per your design. Placing before `AuthorizationFilter` alone does not guarantee an authenticated user if authentication filters never ran.
- Need custom token validation/parsing: consider built-in Spring Security mechanisms (`OAuth2 Resource Server`, HTTP Basic, form login) before writing a bespoke token filter.
- Need authorization checks: prefer `authorizeHttpRequests` and `AuthorizationManager` rather than returning 403 manually inside a custom filter.
- Need tracing/correlation across all routes: a Servlet Filter or standard observability integration is often more appropriate.
- Need security-only auditing with user info: use a custom security filter placed after authentication, with container registration disabled.
- Handling security error codes: understand `ExceptionTranslationFilter` and where exceptions are thrown; do not assume throwing `AccessDeniedException` from any filter is caught everywhere identically.

**Caution with `addFilterAt`:** it does not always "replace the default filter." Inserting a filter at the same slot while the default filter remains active can cause conflicts or unspecified relative order. Use Spring Security's DSL to enable/disable/configure built-in filters, or verify replacement semantics in your version.

## 12. Should You Manually Register springSecurityFilterChain?

Usually **no**. In a Spring Boot Servlet app with `spring-boot-starter-security`, Boot/Spring Security wires `DelegatingFilterProxy` for the `springSecurityFilterChain` bean automatically. Adding another manual `DelegatingFilterProxyRegistrationBean` for the same target can execute **the entire security chain** twice or alter its order.

Never "fix" a duplicate custom filter by:

- Disabling `DelegatingFilterProxy` entirely.
- Removing `SecurityFilterChain` from the application context.
- Manually registering a second `springSecurityFilterChain` Servlet registration.
- Removing all security rules so the filter stops running.
- Using `web.ignoring()` on protected APIs just to bypass a filter.

The narrow problem is **the custom Filter Bean having two registrations**; fix the custom Bean's `FilterRegistrationBean`. Afterward, keep testing authentication and authorization to ensure the security chain remains fully intact.

### 12.1. How Do DelegatingFilterProxy and FilterChainProxy Differ?

`DelegatingFilterProxy` implements `Filter` and sits in the Servlet chain. It looks up a target Spring bean (typically `springSecurityFilterChain`) and delegates to it. Spring Security's `FilterChainProxy` selects a `SecurityFilterChain` via `RequestMatcher`, runs its security filters, and forwards down the chain.

Security DSL configuration produces `SecurityFilterChain` Beans consumed by `FilterChainProxy`. You never manually enumerate all internal Spring Security filters and register each one individually with the Servlet container.

## 13. Multiple SecurityFilterChains: Duplicate Registration or Valid Multi-Chain?

Spring Security supports multiple `SecurityFilterChain` beans:

~~~java
@Bean
@Order(1)
SecurityFilterChain adminChain(HttpSecurity http)
        throws Exception {
    http.securityMatcher("/admin/**");
    http.authorizeHttpRequests(auth ->
            auth.anyRequest().hasRole("ADMIN"));
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain defaultChain(HttpSecurity http)
        throws Exception {
    http.authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated());
    return http.build();
}
~~~

This is an alternative illustrative configuration, not part of the main demo project. Spring Security's `FilterChainProxy` selects **the first `SecurityFilterChain` whose `RequestMatcher` matches**. A request to `/admin/reports` does not run through both `adminChain` and `defaultChain` just because both have rules that could apply. If a request matches no chain, it may receive no Spring Security protection; always provide a clear fallback chain for remaining routes.

Therefore:

- Two `SecurityFilterChain` beans do not imply a filter runs twice.
- The same custom Filter Bean can be added to multiple **mutually exclusive** chains; since only one chain runs per request, multi-chain setup does not double-invoke it.
- If that Filter Bean is also auto-registered with the Servlet container, double registration still happens **regardless of which chain matches**.
- Adding the same filter multiple times **inside the same chain** is an independent configuration mistake.

### 13.1. securityMatcher and requestMatchers Are Different

- `http.securityMatcher("/api/**")` decides **whether this `SecurityFilterChain` applies to the request**.
- `authorizeHttpRequests(... requestMatchers(...))` only decides **authorization rules** for requests **already matched by this chain**.

If a custom filter is registered on the Servlet container, it can run on requests outside `"/api/**"`, even though inside `SecurityFilterChain` the filter was expected to apply only to `"/api/**"`. That is a serious security consequence of double registration.

For instance, a filter parsing JWTs and populating `SecurityContext` outside the chain could execute on URLs lacking the security matcher, producing unpredictable behavior. Never rely on a filter outside the security chain to enforce authorization.

## 14. WebSecurityCustomizer, permitAll, and Bypassing the Security Chain

A common wrong fix is using `WebSecurityCustomizer` to ignore a URL:

~~~java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring().requestMatchers("/api/public/**");
}
~~~

This illustrates an option **not to use to fix a duplicate custom filter**. Ignoring skips security protections such as security headers, CSRF, and other filters on matching paths—not just the duplicated custom filter.

When an endpoint should be public yet still pass through standard Spring Security filters, prefer:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .anyRequest().authenticated());
~~~

These snippets are not standalone complete configs. `permitAll` allows unauthenticated access under that rule without **disabling the security filter chain**. That ensures tests still verify the custom security filter runs once even on public endpoints.

Never bypass authorization to work around a filter lifecycle bug.

## 15. Tests That Detect Duplicates in the Servlet Container

### 15.1. Why Are Unit Tests Insufficient?

Calling `RequestAuditFilter.doFilter(...)` directly once only proves the method executes when called. It says nothing about whether Spring Boot auto-registers the filter or Spring Security adds it via `addFilterBefore`.

To verify both registration paths, spin up a **real embedded servlet server**:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RegistrationIntegrationTest {
    // TestRestTemplate calls over the network.
}
~~~

The Section 7 project test does exactly this. An HTTP request traverses the Servlet Filter chain, `DelegatingFilterProxy`, and the controller. Observing count = 1 and disabled container registration provides strong evidence for the tested route.

### 15.2. Can MockMvc Catch It?

MockMvc tests MVC mappings, security filter chains, and exception handling in a test context. However, it **does not boot a real embedded Servlet container**, so it is not conclusive proof of how embedded Boot auto-registers Filter Beans in production.

Still use `@AutoConfigureMockMvc` + `spring-security-test` to verify authentication/authorization logic, and **add `RANDOM_PORT` tests** when verifying duplicate Servlet container registrations.

### 15.3. Test Multiple URLs, Methods, and Dispatches

A filter may run once on `GET /api/hello` yet fail or double-execute on:

- `/api/admin/**` with a separate `SecurityFilterChain`.
- `/actuator/**` with separate filter registration or management port.
- `/error` or ERROR dispatches.
- Async servlet requests.
- `POST` requests rejected by CSRF.
- Endpoints outside `securityMatcher`.
- Static resource URLs.
- `OPTIONS`/CORS preflights.

Regression tests must cover your actual URL patterns, dispatcher types, and security policies. Never assume every request behaves like `GET /api/hello`.

## 16. Reading Logs to Verify Registration and Order

A Spring Boot Servlet app logs filter registration order and URL patterns when debug logging is enabled for the `web` group. Example config strictly for local or test environments:

~~~yaml
logging:
  level:
    web: debug
    org.springframework.security: debug
~~~

After startup, inspect the logs for:

- Which filters the Servlet container registered, their URL patterns, and order.
- How many registrations exist for `DelegatingFilterProxy`/`springSecurityFilterChain`.
- Which `SecurityFilterChain` `FilterChainProxy` selects for a URI.
- The list of Security filters inside the matching chain.
- Which chain contains your custom filter and which anchor filter it precedes/follows.

Never log access tokens, request bodies, `Authorization` headers, or raw cookies to debug routing. In production, security debug logs can expose sensitive routing/context details; enable only in controlled environments with appropriate log levels.

**Note:** A `"Securing GET /..."` log from `FilterChainProxy` alone does not prove how many times a custom filter ran. Combine registration logs, integration tests, and request-specific counters for complete evidence.

## 17. Checklist for Finding a Filter's Registration Sources

When a custom filter runs twice, audit these sources:

1. Does the class have `@Component`, `@Service`, `@Configuration`, or another stereotype?
2. Is there a `@Bean` method returning this Filter instance?
3. Are `@WebFilter` and `@ServletComponentScan` active?
4. Is there an `enabled=true` `FilterRegistrationBean` or manual registration?
5. Does an `enabled=false` `FilterRegistrationBean` point to the **exact** Filter Bean in use?
6. Is `HttpSecurity.addFilterBefore/After/At` called?
7. Does a second `SecurityFilterChain` also register it on a matching chain?
8. Is a second `DelegatingFilterProxy` manually registered?
9. Does an external library/starter auto-provide a similar Filter bean?
10. Does a gateway/proxy or internal forward generate a second real HTTP request?
11. Does the request traverse ERROR/ASYNC/FORWARD dispatches?
12. Does the filter extend `OncePerRequestFilter` with custom marker/skip behavior?

Audit the entire project and dependencies rather than reading only the filter class file. Two configurations in separate packages creating the same class can double-execute even when each file looks "syntactically valid."

## 18. Distinguishing Servlet Filters from HandlerInterceptors

Both Filters and HandlerInterceptors handle cross-cutting concerns, but at different layers:

| Component | Where Does It Run? | Replaces Security Chain? |
| --- | --- | --- |
| Servlet Filter | Before/outside `DispatcherServlet`, managed by Servlet container | No |
| Spring Security Filter | Inside `FilterChainProxy` via `DelegatingFilterProxy` | Part of Spring Security |
| HandlerInterceptor | Spring MVC `HandlerExecutionChain`, before/after controller | No |
| `@ControllerAdvice` | Exception/model handling at the web layer | No |
| WebFilter | Spring WebFlux reactive web stack | Not a Servlet Filter |
| SecurityWebFilterChain | Spring Security WebFlux | Not a Servlet `SecurityFilterChain` |

If you only need controller metrics or handler-aware metadata, `HandlerInterceptor` can work well. If you need to inspect HTTP requests before `DispatcherServlet`, a Servlet Filter is the right boundary. For authentication/authorization, use Spring Security mechanisms rather than building a standalone Interceptor as the sole guard.

Adopting `HandlerInterceptor` will not fix auto-registration of a leftover Filter bean still sitting in the application context. Remove unused filter configs explicitly.

## 19. Filter Position Relative to SecurityContext

A custom audit filter needing `Principal` must run after the relevant authentication filters. Yet chains vary across sessions, form login, HTTP Basic, bearer tokens, opaque tokens, and custom authentication. There is no single identical "after all auth" slot for every configuration.

Spring Security docs show `addFilterAfter(customFilter, AnonymousAuthenticationFilter.class)` when a filter expects the user (authenticated or anonymous) to be established in the chain; you must still understand each filter's role and your actual authentication mechanism.

Illustrative snippet:

~~~java
http.addFilterAfter(
        new TenantAccessFilter(accessService),
        AnonymousAuthenticationFilter.class);
~~~

`TenantAccessFilter` and `accessService` are illustrative dependencies not present in the test project. Tenant checks must rely on authenticated `SecurityContext` and trusted authorization—**never** trust a client-supplied `X-Tenant-Id` header for data access. In production, prefer `AuthorizationManager` or tightly designed policies.

If a custom filter runs once in the Servlet chain **outside** the security chain, it can miss `SecurityContext` timing and execute on URLs outside `securityMatcher`. Fixing registration is far more important than patching log counters.

## 20. Do Not Replace Built-In Security Filters Unnecessarily

Spring Security provides DSLs for HTTP Basic, form login, OAuth2 resource servers, CSRF, CORS, logout, session management, and exception handling. Prefer the DSL over copying internal filter code for standard behaviors.

Example:

~~~java
http.httpBasic(Customizer.withDefaults());
~~~

This snippet enables HTTP Basic via the DSL; it requires importing `Customizer` and a complete `SecurityFilterChain`. Do not enable HTTP Basic while also manually registering a second `BasicAuthenticationFilter` at the same position just to tweak an error message. Spring Security may reject or conflict on such configs depending on version.

For JWT bearer tokens, prefer `oauth2ResourceServer(...).jwt(...)` when appropriate, with proper issuer/JWK/validation config, rather than hand-parsing raw JWTs in a custom filter.

**Wrong target:** Double registration of a custom filter is never a reason to disable CSRF, authentication, or authorization. Fix the custom filter registration itself.

## 21. Configuring Filters Used by Only One SecurityFilterChain

Suppose there is an API chain and a web chain, and custom auditing applies only to the API:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(
        HttpSecurity http,
        RequestAuditFilter filter) throws Exception {

    http.securityMatcher("/api/**");
    http.authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated());
    http.addFilterBefore(filter, AuthorizationFilter.class);
    return http.build();
}
~~~

A default chain may protect `/ui/**` under a different policy. If the filter is a Bean, you must still disable Servlet registration via `FilterRegistrationBean` for that same instance. Otherwise, the filter will still run on non-`/api/**` requests because the container maps it to `/*`.

Never assume "setting `securityMatcher` stops Boot from auto-registering the filter globally." Those operate on two independent layers.

### 21.1. Can a Filter Bean Be Reused Across Two Chains?

Technically yes in Java if only one chain matches any given request, though consider:

- Does the filter hold mutable state or unsafe caches across requests/chains?
- Does the filter need different config across API/admin/UI?
- Does the filter expect different ordering or exception handling per chain?
- Wouldn't two distinct filters with clearer responsibilities be cleaner if policies truly differ?

Never store global mutable request state in a singleton Filter Bean. Request data must travel via request attributes, `SecurityContext`, or lifecycle-scoped APIs.

## 22. Common Misconceptions About @Order

### 22.1. @Order on a Filter Bean Method Is Not Filter Registration Order

Spring Boot 3.3 docs state you can annotate the Filter class with `@Order` or implement `Ordered`; when you cannot modify the class, use `FilterRegistrationBean#setOrder` to adjust Servlet registration. Do not assume placing `@Order` on **every `@Bean` method returning a Filter** yields the same ordering effect.

If a filter is security-only and container registration is disabled, Servlet filter `@Order` does not control its position inside `SecurityFilterChain` either. Position inside the security chain is governed by `HttpSecurity.addFilterBefore/After/At`.

### 22.2. @Order on a SecurityFilterChain Bean

`@Order(1)` on a `SecurityFilterChain` bean prioritizes that chain over other chains during matching. It does not move a custom filter to the start of a security chain or prevent container auto-registration.

### 22.3. @Order on a Configuration Class

`@Order` on a `@Configuration` class does not define runtime execution order for every component inside it. Check whichever mechanism actually owns ordering: Servlet registration, chain matching, or security filter slot.

## 23. When Filter Beans Are Initialized Very Early

Spring Boot warns that Filter beans can initialize very early in the application lifecycle. If a Filter Bean depends heavily on `DataSource`/JPA/business services or unready Beans, circular dependencies, premature eager initialization, or startup overhead can occur.

Mitigations:

- Decouple filters from blocking repositories where possible.
- Avoid querying the database on every HTTP request just for simple auditing.
- Keep constructor dependencies lightweight and offload heavy work asynchronously when appropriate.
- Use explicit factory/registration lifecycles or `DelegatingFilterProxy` when delegation is genuinely needed.
- Consider event listeners or observability integrations to slim down filter responsibilities.
- Never add a second filter registration as a workaround for a lifecycle issue.

Enabling/disabling a `FilterRegistrationBean` controls **registration**, not whether a heavy dependency bean becomes lightweight. When beans initialize is a separate design concern.

## 24. Async, ERROR Dispatches, and Filters "Running Multiple Times"

One servlet request does not always mean one `doFilter` call. Async processing, error dispatches, and forwards can legitimately trigger additional filter chain invocations.

Distinguish these metrics:

- **HTTP request count:** client requests received.
- **Servlet dispatch count:** `REQUEST`, `ERROR`, `ASYNC`, `FORWARD`, ...
- **Registration paths:** container filter and security chain.
- **Filter `doFilter` calls:** how many times the filter actually ran.
- **`doFilterInternal` calls:** with `OncePerRequestFilter`, potentially fewer than `doFilter` calls due to the guard.

When investigating duplicates, record method, route template, dispatcher type, request identity (not secrets/raw IDs), and registration owner rather than looking solely at raw `doFilterInternal` counts.

For example, a `FilterRegistrationBean` may map `REQUEST` only, whereas a filter in `SecurityFilterChain` can be invoked by Spring Security on whichever dispatcher types the proxy handles. Each layer has its own dispatcher defaults; verify your version's defaults and test on a real Servlet container.

Never use `synchronized` or a static boolean to force a filter to run once globally: that creates race conditions and can lock out every request after the first.

## 25. CORS Preflight and Filter Registration

Browser `OPTIONS` preflight requests are **separate HTTP requests**, not a single request running a filter twice. A browser sending `OPTIONS` followed by `GET` produces two log entries per user action without any duplicate registration.

When using Spring Security:

- Handle CORS properly before authentication checks that would otherwise block preflights.
- Use `http.cors(...)` and `CorsConfigurationSource`/`WebMvcCorsConfiguration` per Spring Security/Boot docs rather than hand-rolling CORS header filters.
- Never disable security globally simply because preflights return 401/403.
- Use per-HTTP-request assertions to count how often a custom filter executes per request.

For API-scoped custom filters, distinguish whether `OPTIONS` preflights enter the `SecurityFilterChain` per `securityMatcher`; if the Filter Bean is still auto-registered with the Servlet container, it can run even when the security chain does not match.

## 26. Logging, Auditing, and Idempotency for Side-Effecting Filters

A doubly registered filter is especially dangerous when it produces side effects:

- Publishing duplicate Kafka events.
- Deducting rate/quota counters twice.
- Emitting duplicate billing/audit records.
- Signing or altering response headers multiple times.
- Regenerating request IDs mid-pipeline.
- Calling remote auth services twice, doubling latency and cost.
- Consuming the request stream without a safe wrapper, losing the body.

**Key point:** Registering the filter in one place is the first line of defense. Still, critical side effects should remain idempotent by request/business ID because HTTP retries, timeouts, redirects, and real repeat requests happen independently of duplicate registration.

Never log `Authorization` headers, access tokens, session cookies, or raw request bodies just to prove a filter ran. Use non-sensitive markers, structured logs, and safely designed tracing.

## 27. Pre-Production Checklist

- [ ] Filter has a single clear owner: Servlet container or `SecurityFilterChain`.
- [ ] If a Filter Bean is security-only: `FilterRegistrationBean` exists for that exact instance with `enabled=false`.
- [ ] No accidental `@Component` + `@Bean` creating two instances.
- [ ] No duplicate `@WebFilter`/`@ServletComponentScan` registration for the same logic.
- [ ] No manual duplicate `DelegatingFilterProxy` for `springSecurityFilterChain`.
- [ ] `SecurityFilterChain` matching includes a fallback and leaves no sensitive endpoints unprotected.
- [ ] `web.ignoring` is not used as a workaround for double filter registration.
- [ ] `HttpSecurity.addFilterBefore/After` placement is justified relative to authn/authz order.
- [ ] Servlet registration order is not confused with security filter order.
- [ ] For `OncePerRequestFilter`, async/error dispatches and request attributes are understood.
- [ ] `RANDOM_PORT` integration tests prove each HTTP request traverses the intended path.
- [ ] Tested public URLs, protected URLs, 401/403, `OPTIONS`, and `ERROR`/`ASYNC` if used.
- [ ] Regression tests cover authentication/authorization, not just `X-Audit-Filter-Calls`.
- [ ] No raw secrets leaked into responses, access logs, or metric labels.
- [ ] No long blocking I/O inside filters without deadlines and concurrency control.
- [ ] Inspected filter registration logs and concrete tests before and after changes.
- [ ] Have a rollback plan if request behavior changes on deployment.

## 28. Common Issues and Fixes

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Custom filter called twice | `@Component`/`@Bean` auto-register + `addFilterBefore` | Disable container registration or avoid Filter Bean |
| `doFilterInternal` logs once yet duplicate remains | `OncePerRequestFilter` guard hides second entry | Inspect registrations; test with `GenericFilterBean` lab |
| Adjusted `@Order` but filter still runs twice | Ordering does not remove registration | Use `FilterRegistrationBean.setEnabled(false)` |
| Disabled registration and filter stopped running | Filter was never added to a matching `SecurityFilterChain` | Check `addFilter...` and `securityMatcher` |
| Filter runs on non-API paths | Container auto-registered with `/*` | Disable container registration for security-only bean |
| Filter sees no authenticated user | Runs on Servlet layer or too early in security chain | Place at the right position after authentication |
| Two Filter beans of the same class exist | Both `@Component` and `@Bean` exist | Create one explicit instance only |
| Disabling `FilterRegistrationBean` has no effect | Bean wraps a `new` object, not the active Filter Bean | Inject the exact Filter Bean into the constructor |
| Multiple `SecurityFilterChain`s seem to both run | Container filter outside chains or duplicate Security proxy | Verify first-match behavior and registrations |
| `OPTIONS` request logs twice | Preflight + actual request | Count per individual HTTP request, not per UI click |
| MockMvc passes but staging duplicates filter | MockMvc does not simulate full container registration | Test `RANDOM_PORT` and production-like container |
| Filter runs again when server sends errors | `ERROR` dispatcher type | Check dispatcher types and request attributes |
| Protected API stops returning 403/401 as expected | Security bypassed or chain order altered | Keep security matchers and fallback; test auth |
| Custom auth filter conflicts with built-in | Re-added alongside DSL | Use standard DSL or configure replacement properly |
| Filter initialized too early | Servlet Filter bean early init lifecycle | Reduce dependencies; consider delegation/lazy lookup |
| Token log appears twice | Double filter logging or actual retried requests | Stop logging secrets, fix registration, check request IDs |

## 29. Practice Exercises and Verification Labs

### Exercise 1 — Trigger Double Invocation

Run the sample project and verify `X-Audit-Filter-Calls=1`. On a separate experimental branch, remove the disabled `FilterRegistrationBean` while keeping the `requestAuditFilter` Bean and `addFilterBefore`; call `GET /api/hello`. Observe filter counts/logs and explain the execution path. Restore the proper configuration before finishing.

### Exercise 2 — Non-Bean Filter

Remove `requestAuditFilter()` and `disableContainerAudit()`, and replace the `filter` parameter in `SecurityConfiguration` with `new RequestAuditFilter()` instantiated inside the `SecurityFilterChain` bean. Run HTTP tests and verify `X-Audit-Filter-Calls=1`.

### Exercise 3 — Scope of securityMatcher

Create an API `SecurityFilterChain` with `securityMatcher("/api/**")`, a fallback `SecurityFilterChain` for other URIs, and a security-only filter attached only to the API chain. Verify the filter does not run on `/public` when outside the API chain, while ensuring `/public` remains governed by the fallback policy.

### Exercise 4 — Servlet-Only Filter

Create a `CorrelationFilter` registered solely via `FilterRegistrationBean(enabled=true)` with `addUrlPatterns("/api/*")`, without adding it to `HttpSecurity`. Verify it runs on target URLs and skips others. Compare `SecurityContext` visibility.

### Exercise 5 — OncePerRequestFilter

Switch `RequestAuditFilter` to `OncePerRequestFilter`, testing `doFilterInternal` and filter registration separately. Try `ERROR`/`ASYNC` dispatches (if enabled in the app) and explain when once-per-dispatch differs from once-per-logical-request.

### Exercise 6 — Security Regression

Add `spring-security-test`/MVC tests for anonymous, authenticated, and admin users per design; verify fixing filter registration did not accidentally weaken protection on any endpoint.

### Exercise 7 — Audit Side Effects

Replace the header counter with a fake event publisher in tests (no real external calls) and verify one HTTP request does not emit two events from duplicate registration. Also design event idempotency to tolerate real HTTP retries.

### Exercise 8 — WebFlux Comparison

Create a pure WebFlux app with `WebFilter`/`SecurityWebFilterChain` and Reactor Netty, explaining why Servlet `FilterRegistrationBean` does not apply there. Never copy Servlet Filter code from this lesson into a reactive stack expecting Spring MVC behavior.

**Passing evidence:** source code, Gradle test output, HTTP headers, redacted startup logs, a table mapping registration owners, and a conclusion backed by actual request traces. Never claim benchmarks or tests passed unless actually executed in the target environment.

## 30. Self-Assessment Questions

1. How do the Servlet Filter chain and `SecurityFilterChain` differ?
2. What roles do `DelegatingFilterProxy` and `FilterChainProxy` play?
3. Why can `@Component` on a Filter cause Boot to auto-register it?
4. What happens when that same Filter Bean is passed to `HttpSecurity.addFilterBefore`?
5. Can a single Filter object have two registrations?
6. Why is `OncePerRequestFilter` not a fix for duplicate registration?
7. Which layer does `FilterRegistrationBean.setEnabled(false)` disable?
8. Why must a disabled `FilterRegistrationBean` wrap the exact Filter Bean?
9. When should you use `new MyFilter(...)` instead of a `@Bean`?
10. If a filter is API-only, does `securityMatcher` restrict Servlet auto-registration?
11. How does `@Order` on `SecurityFilterChain` differ from `FilterRegistrationBean#setOrder`?
12. How does `HttpSecurity.addFilterBefore/After` differ from `@Order`?
13. Do multiple `SecurityFilterChain` beans automatically cause a request to traverse both?
14. What is the risk if a request matches no `SecurityFilterChain`?
15. Why must you not use `web.ignoring` or disable Spring Security to fix duplicates?
16. Why is MockMvc alone insufficient to prove a filter does not auto-register?
17. When are two `doFilter` calls valid behavior due to async/error dispatches?
18. Is an `OPTIONS` preflight a duplicate registration?
19. Where should a security audit filter needing `Principal` be positioned?
20. Why prefer the built-in DSL over manually adding a second `BasicAuthenticationFilter`?
21. If a filter triggers side effects, why is idempotency still required even after fixing registration?
22. How do you conclusively verify with an integration test that a filter runs only once?

## 31. Official References

- [Spring Security — Architecture (Servlet)](https://docs.spring.io/spring-security/reference/servlet/architecture.html): `DelegatingFilterProxy`, `FilterChainProxy`, `SecurityFilterChain`, filter ordering, and warning that Filter Beans may run twice.
- [Spring Security — Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): multiple `SecurityFilterChain`s, `@Order`, `securityMatcher`, and `requestMatchers`.
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): auto-registration of Servlet/Filter beans, ordering, and Servlet context.
- [Spring Boot 3.3 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): disabling registration via `FilterRegistrationBean.enabled=false`.
- [Spring Framework — OncePerRequestFilter](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html): already-filtered attribute, async/error dispatches, and `doFilterInternal`.
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): testing security behavior.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `RANDOM_PORT` integration tests and `TestRestTemplate`.

**Conclusion:** to prevent a custom Servlet Filter from running twice, decide whether it belongs to the **Servlet container** or **Spring Security**. For a security-only Filter Bean, create a `FilterRegistrationBean` wrapping **the exact same Bean** with `enabled=false`; or omit creating a Filter Bean and instantiate it directly inside `HttpSecurity`. `OncePerRequestFilter`, `@Order`, and `securityMatcher` each serve distinct roles and do not replace fixing double registration. Verify the outcome with a real-container HTTP integration test plus authentication/authorization regression tests.