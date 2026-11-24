# Inspecting Filter Ordering to Avoid Double Registration or Duplicate Security Processing

**Scope:** Spring Boot → web-runtime → Security Integration. This article helps you determine which filter layers a request passes through; distinguish the **Servlet container filter chain** from **Spring Security FilterChainProxy**; inspect `SecurityFilterChain` ordering and `HttpSecurity.addFilterBefore/After/At`; detect a custom filter accidentally registered **twice**; and handle `OncePerRequestFilter`, dispatcher types, CORS/CSRF, JWT, logging, and integration testing.

**Environment:** Java 17+, Maven 3.6.3+, Spring Boot **3.5.16** (Spring Security 6.5.x via Spring Boot BOM), Servlet MVC/Tomcat. The project includes compilable/runnable Java code, an endpoint returning an invocation counter, and two integration tests running against a real HTTP server. Other snippets are explicitly marked as illustrative. Spring Boot 3.5.16 is the final 3.5 release under OSS support (6/2026); in production, use a currently patched version (such as the Boot 4.x line or supported maintenance releases), rather than treating the pinned version here as a permanent production recommendation.

## 1. What Are Security Filters and Why Does Ordering Matter?

In a Servlet application, requests pass through a list of **Filters** before reaching `DispatcherServlet`/controllers. Each filter can inspect or modify the request/response, or **reject** the request with 401/403 when an issue is detected. The filter chain typically handles:

- applying security headers, handling CORS and CSRF;
- loading/restoring `SecurityContext` and the principal;
- authenticating Basic, form login, or bearer JWT/OAuth2 (depending on what is enabled);
- attaching an anonymous principal when no user is present;
- enforcing authorization: permitting, denying, or redirecting to an authentication entry point;
- adding request IDs, auditing, rate limiting, and tracing per design.

If an authentication filter runs **after** authorization, authorization will not see the user. If a custom filter runs **twice** on the same request, tokens may be verified twice, downstream services called twice, audit/metrics logged twice, or request bodies consumed before the controller reads them. If `OPTIONS` preflight is wrongly blocked, browsers report CORS errors. Hence both **ordering** and **registration count** matter.

However, **two log lines alone do not prove a filter is registered twice**. A browser may have sent two HTTP requests, a proxy may have retried, the request may have redirected, the Servlet container may have created an `ASYNC`/`ERROR` dispatch, or two filter instances may be logging the same message. Always inspect the **same request ID**, dispatcher type, filter instance, selected `SecurityFilterChain`, and Servlet registrations.

## 2. Two-Tier Architecture: Servlet Filters vs Spring Security Filters

~~~text
HTTP request
      │
      ▼
Embedded Servlet container (Tomcat)
      │
      ├── Optional container Filter A
      │
      ├── DelegatingFilterProxy ("springSecurityFilterChain")
      │         │
      │         ▼
      │      FilterChainProxy (Spring Security)
      │         │
      │         ├─ SecurityFilterChain 1: matcher /api/**
      │         └─ SecurityFilterChain 2: matcher any request
      │                       │
      │                  PICKS FIRST MATCHING CHAIN
      │                       ▼
      │            [SecurityContextHolderFilter,
      │             HeaderWriterFilter, CsrfFilter,
      │             BasicAuthenticationFilter,
      │             AnonymousAuthenticationFilter,
      │             CustomFilter, AuthorizationFilter]
      │                       │
      │                       ▼
      │                servlet chain.doFilter(...)
      │
      ├── Optional container Filter B
      │
      ▼
DispatcherServlet → @Controller/@RestController → response
~~~

### 2.1. `DelegatingFilterProxy` and `FilterChainProxy`

**`DelegatingFilterProxy`** is a Servlet `Filter` bridging the Servlet container and the Spring ApplicationContext. In Spring Security configuration, it delegates to the Spring bean named **`springSecurityFilterChain`**, which is normally **`FilterChainProxy`**.

**`FilterChainProxy`** holds the list of `SecurityFilterChain` beans. It finds the **first chain matching the request** and invokes that chain's security filters; it does not run all chains sequentially. It also integrates shared mechanisms such as security context cleanup and `HttpFirewall`. Filter order inside a chain is managed by the framework depending on enabled DSLs/features.

Spring Boot/Spring Security auto-configuration normally **registers `DelegatingFilterProxy` already**. Never add another registration bean or declare `web.xml` for the same `springSecurityFilterChain` without fully understanding its lifecycle; registering two proxies can run the pipeline twice or cause hard-to-trace errors.

### 2.2. Servlet Container Filters and Spring Security Filters Do Not Share the Same “Order”

| Object | Where Is It Registered? | Order Controlled By |
| --- | --- | --- |
| `jakarta.servlet.Filter` via `FilterRegistrationBean` | Servlet container | `FilterRegistrationBean#setOrder`, URL patterns, dispatcher types |
| Regular `Filter` bean in a Boot Servlet app | May be auto-registered in container by Boot | Auto-registration / `@Order` / registration config |
| `DelegatingFilterProxy` | Servlet container, delegates to security bean | Position of the proxy within the container chain |
| `SecurityFilterChain` | `FilterChainProxy` | Matcher + `@Order` across chain beans |
| Filter added via `HttpSecurity.addFilterBefore/After/At` | Inside a `SecurityFilterChain` | Position relative to the specified security filter |
| `OncePerRequestFilter` | Can sit in both tiers if misconfigured | Request attribute guard, not a registration policy |

**Example distinction:** putting `@Order(1)` on a `@Bean SecurityFilterChain` method makes that chain evaluate before other chains. It **does not** move a custom filter to the start of the chain. Conversely, `FilterRegistrationBean#setOrder(1)` only controls Servlet filter ordering in the container; it **does not** control the position of a custom filter added via `HttpSecurity`.

### 2.3. `chain.doFilter` Must Be Called Exactly Once When Continuing

~~~java
@Override
public void doFilter(ServletRequest request, ServletResponse response,
                     FilterChain chain)
        throws IOException, ServletException {
    // Pre-processing before handler/downstream.
    chain.doFilter(request, response);
    // Post-processing after downstream.
}
~~~

This is an **illustrative code snippet**. If a filter needs to reject a request, it can write the status/response directly and **not** invoke the rest of the chain. When continuing normally, invoke `chain.doFilter` strictly **once** along the normal path. Calling it twice thinking it “ensures next runs” can invoke downstream filters/controllers twice or fail on committed responses. Forgetting to call it stops the request from ever reaching the controller.

## 3. Logical Order of Security Filters

Security filters execute in an order ensuring prerequisites are ready before authentication and authorization. Illustrative list (exact filters depend on `HttpSecurity` config and version):

| Filter | Responsibility |
| --- | --- |
| `DisableEncodeUrlFilter` | Adjusts URL encoding behavior in certain scenarios |
| `WebAsyncManagerIntegrationFilter` | Integrates security context with Servlet MVC async |
| `SecurityContextHolderFilter` | Prepares/loads security context using the configured strategy |
| `HeaderWriterFilter` | Writes security response headers |
| `CorsFilter` | Handles CORS/preflight if configured |
| `CsrfFilter` | Enforces CSRF checks on applicable requests |
| `LogoutFilter` | Handles logout |
| `UsernamePasswordAuthenticationFilter` | Form login when enabled |
| `BasicAuthenticationFilter` | HTTP Basic when enabled |
| `BearerTokenAuthenticationFilter` | Bearer tokens when OAuth2 resource server is enabled |
| `AnonymousAuthenticationFilter` | Populates anonymous principal if unauthenticated |
| `ExceptionTranslationFilter` | Translates authentication/access-denied errors into HTTP responses |
| `AuthorizationFilter` | Checks endpoint access permissions |

**Not every app has all of these filters.** A project enabling HTTP Basic differs from form login. An app without resource server config does not have `BearerTokenAuthenticationFilter`. Spring Security's internal order is managed via `FilterOrderRegistration`; do not copy a fixed list and manually instantiate core filters when `httpBasic`, `formLogin`, `oauth2ResourceServer`, `authorizeHttpRequests`, `csrf`, or `cors` DSLs suffice.

Custom filter design rules:
1. If you need an existing `SecurityContext`, do not place it before the filter that loads the security context.
2. If **authenticating** a new mechanism, the filter must complete authentication **before `AuthorizationFilter`**. Spring Security documentation suggests placing custom authentication filters after `LogoutFilter` or at a mechanism-appropriate anchor.
3. If merely reading the already-authenticated user, place it after the relevant authentication filters—such as `addFilterAfter(..., AnonymousAuthenticationFilter.class)` or `addFilterBefore(..., AuthorizationFilter.class)`—and test.
4. Prefer `addFilterBefore(Filter, Class<?>)`/`addFilterAfter(...)` over guessing numeric orders. `addFilterAt(...)` registers at the same slot as a standard filter, yet **should not be assumed to remove the standard filter** if the DSL still adds it; inspect the resulting chain.
5. Never reimplement JWT logic already provided by `oauth2ResourceServer().jwt()` just to “add logging”: use authentication converters/filter hooks and appropriate tracing instead.

## 4. Does Having Multiple `SecurityFilterChain` Beans Run Security Twice?

**No, not by default.** `FilterChainProxy` selects the **first matching chain**. For example:

~~~text
@Order(1) securityMatcher("/api/**") → API chain
No @Order, matches any request → fallback chain

GET /api/hello  → API chain
GET /public     → fallback chain
GET /admin      → fallback chain
~~~

This does not mean `GET /api/hello` goes through the API chain and **then** through the fallback chain. Duplicate execution usually comes from **the same filter sitting in both the Servlet container chain and the Spring Security chain**, or custom logic invoked across multiple components—not merely from having two `SecurityFilterChain` beans.

**Critical mistake:** putting `@Order(1)` on a broad fallback matcher `/**` before a specific `/api/**` chain. The broad chain matches first, so the API chain may **never be chosen**. If the fallback is overly permissive, sensitive APIs receive the wrong policy; this is chain **shadowing**, not necessarily double registration.

### 4.1. `securityMatcher` vs `requestMatchers`

- `http.securityMatcher("/api/**")`: selects whether **this entire chain** applies to the request.
- `authorizeHttpRequests(auth -> auth.requestMatchers("/api/admin/**").hasRole("ADMIN"))`: an **authorization rule** inside the already-selected chain.

If the chain does not match, `requestMatchers` inside that chain are never evaluated. If **no chain matches**, the request can go unprotected by Spring Security. Use a fallback chain with an appropriate `denyAll()`/`authenticated()` policy rather than leaving security gaps.

## 5. Runnable Java 17 Project: Counting Custom Filter Invocations

This example deliberately uses plain `jakarta.servlet.Filter` rather than `OncePerRequestFilter` for the counter. That way, if the filter is also registered on the container and executes nested with security, the test observes 2 invocations. Using `OncePerRequestFilter` introduces a request attribute guard that can hide duplicate registrations inside `doFilterInternal`.

**Correct design:** the `AuditFilter` is instantiated with `new AuditFilter()` **only inside the security chain**, with no `@Bean`, `@Component`, or `@WebFilter`.

Directory tree:

~~~text
filter-order-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/filterdemo/
    │   │   ├── FilterOrderApplication.java
    │   │   ├── AuditFilter.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── DemoController.java
    │   └── resources/application.properties
    └── test/java/com/example/filterdemo/
        └── FilterOrderIntegrationTest.java
~~~

### 5.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>filter-order-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 5.2. `src/main/java/com/example/filterdemo/FilterOrderApplication.java`

~~~java
package com.example.filterdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterOrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterOrderApplication.class, args);
    }
}
~~~

### 5.3. `src/main/java/com/example/filterdemo/AuditFilter.java`

~~~java
package com.example.filterdemo;

import java.io.IOException;
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class AuditFilter implements Filter {
    public static final String COUNT =
            AuditFilter.class.getName() + ".invocations";
    private static final Logger log =
            LoggerFactory.getLogger(AuditFilter.class);

    @Override
    public void doFilter(ServletRequest request,
                         ServletResponse response,
                         FilterChain chain)
            throws IOException, ServletException {

        HttpServletRequest http = (HttpServletRequest) request;
        Object previous = http.getAttribute(COUNT);
        int count = (previous instanceof Integer n ? n : 0) + 1;
        http.setAttribute(COUNT, count);

        log.info("AUDIT count={} dispatcher={} method={} uri={}",
                 count,
                 http.getDispatcherType(),
                 http.getMethod(),
                 http.getRequestURI());

        chain.doFilter(request, response);
    }
}
~~~

**Explanation:** the `COUNT` request attribute lives only for the request and is for diagnostics only—not a JVM-wide counter, and never used for authentication/authorization. Each time `doFilter(...)` runs on the same Servlet request, `COUNT` increments. This is an **observational filter** that makes no security decisions, so it does not touch JWTs or credentials.

If the filter is registered in both the container and the security chain, the count increments twice. If there is a new `ERROR`/`ASYNC` dispatch or two separate HTTP requests, check `DispatcherType` and request identity before concluding the cause.

### 5.4. `src/main/java/com/example/filterdemo/SecurityConfiguration.java`

~~~java
package com.example.filterdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/**")
            .authorizeHttpRequests(auth ->
                auth.anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .addFilterBefore(new AuditFilter(),
                             AuthorizationFilter.class);
        return http.build();
    }

    @Bean
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/public").permitAll()
            .anyRequest().denyAll());
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
            .password("{noop}demo-only")
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }
}
~~~

`apiChain` is evaluated **first** because of `@Order(1)`; it matches only `/api/**` and requires Basic authentication. A custom `AuditFilter` is added **before `AuthorizationFilter`**. `fallbackChain` covers other routes, permitting only `/public` and denying everything else. `FilterChainProxy` selects **one** of the two chains.

**Never copy `{noop}demo-only` passwords into production.** It exists solely for the local lab; production systems must use strong password hashing, identity providers, secret management, and TLS. **This example does not disable CSRF**; it only exposes GET endpoints. When adding POSTs using cookies/sessions, apply an appropriate CSRF policy.

### 5.5. `src/main/java/com/example/filterdemo/DemoController.java`

~~~java
package com.example.filterdemo;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/hello")
    public String hello(HttpServletRequest request) {
        return "hello; auditCount="
                + request.getAttribute(AuditFilter.COUNT) + "\n";
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public\n";
    }
}
~~~

The controller returns the counter in the response **purely for learning and testing**; never expose debug endpoints or internal diagnostics like this in production. With `@RestController`, returning a `String` writes the response body directly rather than resolving a logical view name.

### 5.6. `src/main/resources/application.properties`

~~~properties
server.port=8080
spring.application.name=filter-order-demo

# Enable verbose logging only in development/staging while diagnosing.
logging.level.org.springframework.security.web.DefaultSecurityFilterChain=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
logging.level.com.example.filterdemo.AuditFilter=INFO
~~~

`DefaultSecurityFilterChain` at DEBUG prints the filter list at startup; `FilterChainProxy` at TRACE lets you trace which chain matched and which security filters ran per request. Exact log entries vary by Spring Security version/configuration; do not hardcode full log output as expected stdout.

### 5.7. Running the Project and Testing HTTP

Inside the `filter-order-demo` directory:

~~~bash
java -version
mvn spring-boot:run
~~~

In another terminal:

~~~bash
# Fallback chain, public endpoint:
curl -i http://localhost:8080/public

# API chain, unauthenticated:
curl -i http://localhost:8080/api/hello

# API chain, with demo HTTP Basic:
curl -i -u learner:demo-only http://localhost:8080/api/hello
~~~

**Expected with the exact project above and no external Security config:**
- `GET /public`: **200 OK**, response body `public\n`.
- `GET /api/hello` without Basic credentials: **401 Unauthorized** and `WWW-Authenticate` header supplied by the Basic entry point.
- `GET /api/hello` with valid username/password: **200 OK**, response body **`hello; auditCount=1\n`**. One `AuditFilter` log shows `count=1 dispatcher=REQUEST method=GET uri=/api/hello`.
- With wrong credentials, `BasicAuthenticationFilter` can reject the request **before** the custom `AuditFilter`, so the absence of the custom filter log does not prove the chain did not apply.
- `GET /admin` enters the fallback chain and hits `denyAll()`; response 401/403 depends on entry point/exception handling. Crucially, the route is not publicly exposed.

Bodies end with a newline because the Java controller returns `"\n"`. `curl -i` also prints HTTP headers, server date, and connection metadata depending on the container. Do not treat full curl output as a fixed string during verification.

### 5.8. Integration Test with a Real Embedded Servlet Container

Create **`src/test/java/com/example/filterdemo/FilterOrderIntegrationTest.java`**:

~~~java
package com.example.filterdemo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FilterOrderIntegrationTest {
    @LocalServerPort
    private int port;

    @Test
    void authenticatedApiPassesAuditFilterExactlyOnce() {
        String body = RestClient.create().get()
                .uri("http://localhost:" + port + "/api/hello")
                .headers(h -> h.setBasicAuth("learner", "demo-only"))
                .retrieve()
                .body(String.class);

        assertEquals("hello; auditCount=1\n", body);
    }

    @Test
    void publicPageDoesNotNeedApiFilter() {
        String body = RestClient.create().get()
                .uri("http://localhost:" + port + "/public")
                .retrieve()
                .body(String.class);

        assertEquals("public\n", body);
    }
}
~~~

Run:

~~~bash
mvn test
~~~

With source matching the example, **both tests are designed to PASS**; this is an expected outcome based on the code, not a guarantee across every host. `RANDOM_PORT` starts a real embedded server, so the test observes **real Servlet filter registrations**, unlike `MockMvc` standalone setups or MVC-only test slices.

If a test fails, inspect server logs and build/HTTP errors before touching security policy. Never switch everything to `permitAll` just to stop 401/403 failures.

## 6. Reproducing Double Registration and Fixing It Properly

### 6.1. Anti-Example: `@Component` and `addFilterBefore` on the Same Filter

When a custom `Filter` is annotated with `@Component` or declared via `@Bean`, it becomes a Spring Bean. In Servlet Spring Boot, **Filter beans are auto-registered with the container by Boot**. Referencing that same bean in `HttpSecurity.addFilterBefore(...)` triggers execution at both tiers.

**WRONG** configuration snippet (for recognizing the bug only; do not paste into the clean Section 5 project):

~~~java
@Component
public class MyAuditFilter implements Filter {
    // doFilter(...)
}

@Bean
SecurityFilterChain apiChain(HttpSecurity http,
                             MyAuditFilter myAuditFilter)
        throws Exception {
    http.securityMatcher("/api/**")
        .addFilterBefore(myAuditFilter, AuthorizationFilter.class);
    return http.build();
}
~~~

With a plain `Filter` counting a request attribute, the same request shows two invocations. With `OncePerRequestFilter`, `doFilterInternal` may skip the second nested pass due to its guard and **hide the duplicate symptom**, leaving the registration wrong and effective ordering unreliable. Worse, if **two separate instances** are created, their markers differ and both run the logic.

**Do not confuse a single filter injected into two bean methods with two security chains:** one request runs only the first matching chain; what to catch is container auto-registration or duplicated logic across distinct filters or duplicated security proxies.

### 6.2. Solution A: Do Not Make the Filter a Bean

In the sample project, the filter is instantiated with:

~~~java
.addFilterBefore(new AuditFilter(), AuthorizationFilter.class)
~~~

Do not add `@Component`, do not declare `@Bean AuditFilter`, and do not use `@WebFilter` on the same class. When the filter needs no dependency injection, this is the most direct way to ensure it **lives solely inside the SecurityFilterChain**.

If the filter needs a service/repository, inject the service into the `@Bean SecurityFilterChain` method and pass it via constructor **without declaring a filter bean**. This snippet is illustrative and not standalone:

~~~java
@Bean
SecurityFilterChain chain(HttpSecurity http, AuditService service)
        throws Exception {
    AuditFilter audit = new AuditFilter(service);
    // Requires constructor AuditFilter(AuditService) in implementation.
    http.addFilterBefore(audit, AuthorizationFilter.class);
    // Still requires configuring authentication/authorization per business rules.
    return http.build();
}
~~~

If adopting this approach, modify the appropriate class rather than pasting it on top of `apiChain` in the sample project; it only illustrates constructor injection.

### 6.3. Solution B: If a Filter Bean Is Needed, Disable Servlet Registration

When a filter must be a Spring Bean for reuse, DI, or test configuration, use `FilterRegistrationBean` with **`setEnabled(false)`**, as recommended in Spring Security/Spring Boot docs:

~~~java
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class AuditFilterBeanConfig {

    @Bean
    AuditFilter auditFilter() {
        return new AuditFilter();
    }

    @Bean
    FilterRegistrationBean<AuditFilter> noServletRegistration(
            AuditFilter auditFilter) {
        FilterRegistrationBean<AuditFilter> reg =
                new FilterRegistrationBean<>(auditFilter);
        reg.setEnabled(false);
        return reg;
    }
}
~~~

**This is an alternative approach.** If you apply it, update the API chain factory method to accept `AuditFilter auditFilter` as a parameter and use:

~~~java
.addFilterBefore(auditFilter, AuthorizationFilter.class)
~~~

Do not keep `new AuditFilter()` alongside the bean if you want strictly **one instance**. `setEnabled(false)` disables registration in the **Servlet container** only; Spring Security still invokes the filter bean added via `HttpSecurity`. Never call `setEnabled(false)` on `springSecurityFilterChain`/the security proxy—that would disable security.

If using `@Component` instead of `@Bean` to declare the filter, you can still pass that bean into a disabled `FilterRegistrationBean`, yet **never create a second bean** with the same role. Verify the filter disappears from Servlet registrations while appearing exactly once in the security chain.

### 6.4. Solution C: Filters Needed Only in the Servlet Container

Pure request ID, compression, or tracing filters that do not need an authenticated `SecurityContext` can live in the container chain. Register **once** via `FilterRegistrationBean` with chosen URL patterns, dispatcher types, and order, and **do not** add that filter to `HttpSecurity`.

Illustrative snippet (requires `RequestIdFilter` implementation and imports):

~~~java
@Bean
FilterRegistrationBean<RequestIdFilter> requestIdRegistration(
        RequestIdFilter filter) {
    FilterRegistrationBean<RequestIdFilter> reg =
            new FilterRegistrationBean<>(filter);
    reg.setUrlPatterns(java.util.List.of("/*"));
    reg.setOrder(org.springframework.core.Ordered.HIGHEST_PRECEDENCE);
    return reg;
}
~~~

**Do not** think `FilterRegistrationBean#setOrder` places a filter after `BasicAuthenticationFilter`: it controls **container ordering**, not whether the security context has been authenticated. If a filter needs to read authentication, design it as a Spring Security filter positioned after authentication occurs.

## 7. `OncePerRequestFilter` and Servlet Dispatcher Types

`OncePerRequestFilter` is a Spring Framework base class offering the `doFilterInternal` hook. It uses an **already-filtered request attribute** to avoid re-running internal logic within a dispatch for that filter's name/marker.

~~~java
public class MyOnceFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {
        // Executed at most once within dispatch scope per contract.
        chain.doFilter(request, response);
    }
}
~~~

This snippet is **not standalone**: it requires importing `OncePerRequestFilter`, `HttpServletRequest`, `HttpServletResponse`, `FilterChain`, `ServletException`, and `IOException`.

### 7.1. “Once” Does Not Mean “Registered Once”

- The same filter instance/marker in a **nested invocation** skips the second `doFilterInternal` execution.
- Two different **instances** or names/markers will both execute their logic.
- `OncePerRequestFilter` does not remove an extra Servlet registration; it only guards execution via a request attribute.
- A single HTTP request can involve multiple **Servlet dispatcher types**: `REQUEST`, `FORWARD`, `INCLUDE`, `ASYNC`, `ERROR`.
- By default `shouldNotFilterAsyncDispatch()` and `shouldNotFilterErrorDispatch()` return **true**, skipping subsequent async/error dispatches; override to false only when you genuinely need to process those dispatches.
- Some containers trigger **nested ERROR dispatches** when sending error responses; Spring provides `doFilterNestedErrorDispatch(...)` for special cases. Do not assume every `ERROR` dispatch is a fresh request.
- Browser/proxy retries are **new HTTP requests**; a per-request guard does not suppress retries.

**Never use a global static boolean** to skip subsequent requests: that can bypass authentication/authorization for other requests. Never use `OncePerRequestFilter` to mask two broken registrations—fix the registration itself.

### 7.2. Logging to Distinguish Dispatches

In diagnostic filters, useful fields include:
- a request/correlation ID (if reliably generated by proxy/app);
- `HttpServletRequest#getDispatcherType()`;
- method and path;
- filter instance name/identity;
- entry/exit trace around `chain.doFilter`;
- HTTP status (if safely observable) and elapsed time.

If logs show the same path with two different request IDs, they may be **two independent HTTP requests**. If the same request ID shows `REQUEST` followed by `ERROR`, inspect error dispatch configuration rather than assuming duplicate registration. If the same request ID and `REQUEST` dispatch hit the custom filter twice independently, inspect Servlet registrations and the security chain.

## 8. Inspecting the Security Chain via Logs

Spring Security officially recommends logging to inspect filter lists and ordering:

~~~properties
logging.level.org.springframework.security.web.DefaultSecurityFilterChain=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

At startup, `DefaultSecurityFilterChain` DEBUG typically prints `Will secure ... with [...]` for each security matcher and filter list. `FilterChainProxy` TRACE shows matching decisions and invoked security filters per request.

**Seeing many logs from multiple security filters on one request is normal.** Your job is to verify:
1. Each chain contains only the needed filters with no duplicate copies of the same logic.
2. Chain `@Order` and matchers are right.
3. Custom filters appear in the **intended** chain at the right relative position.
4. If a custom filter also appears in the Servlet container registry, remove the unintended registration.
5. There are no **two security proxy registrations** routing the same request into `FilterChainProxy` multiple times.

In practice, you can use Spring Actuator mappings, `ServletContext.getFilterRegistrations()`, or startup inspection code to see container registrations separately. **Security chain debug logs do not automatically list all container filter registrations**, so do not treat them as sole proof.

### 8.1. Inspecting Servlet Filter Registrations

Illustrative snippet you can temporarily add to a development `@Configuration` class:

~~~java
@Bean
ApplicationRunner listServletFilters(ServletContext context) {
    return args -> context.getFilterRegistrations().forEach((name, reg) ->
        System.out.println("SERVLET FILTER: " + name
                + " -> " + reg.getClassName()));
}
~~~

Imports: `org.springframework.boot.ApplicationRunner`, `jakarta.servlet.ServletContext`, `org.springframework.context.annotation.Bean`. This snippet **is not part of the complete Section 5 project**; use it only while debugging if needed.

In a properly configured project, a container registration for `springSecurityFilterChain`/the proxy is **valid**. There should be no separate container registration named `auditFilter`. If you find two entries with the same filter logic or two proxies, check `@Component`, `@Bean`, `@WebFilter`/`@ServletComponentScan`, `FilterRegistrationBean`, library registrations, and `web.xml`.

**Never expose mappings/debug endpoints to the public internet**, as that reveals security topology. Never leave TRACE enabled long-term in production; time-box debug logging and keep tokens, cookies, and sensitive data out of logs.

### 8.2. Distinguishing Filter Identity from Class Name

A `JwtFilter` class can have **two instances**:
- one created by `@Bean`;
- another created by `new JwtFilter()` inside the chain.

Logs showing only the class name will not reveal that two separate instances ran. While debugging in test environments, log identity (such as `System.identityHashCode(this)`), bean/registration name, and dispatcher type. Never use identity hash codes as unique security identifiers; they only help distinguish instances within a single JVM.

## 9. MockMvc Does Not Replace Full Integration Tests

**Filter unit tests** can verify that a `doFilter` branch calls next exactly once. **MockMvc** effectively tests Spring MVC + Spring Security integration. However, `MockMvcBuilders.standaloneSetup(...)` does not boot the **full Servlet container**, missing Boot's auto-registration of Filter beans. A bug in real Tomcat might never appear in standalone tests.

| Test | Verifies Well | Does Not Fully Prove |
| --- | --- | --- |
| Filter unit test | Logic branches, `chain.doFilter`, error handling | Container registrations, actual security chain |
| `@WebMvcTest`/`@AutoConfigureMockMvc` | Routing, security policy, 401/403 responses | All container filter registrations and dispatcher lifecycle |
| **`@SpringBootTest(webEnvironment=RANDOM_PORT)`** | Real HTTP server, Boot auto-registration, security chain, real responses | External proxies/ingress, production retries/config differences |

The Section 5 example uses `RANDOM_PORT` to catch duplicate filter registration. A solid test checks more than status 200: it verifies **invocation counts**, 401/403 policies, CORS/CSRF where applicable, and chain matching.

**Additional tests worth adding** in real systems:
- API missing authorization returns 401; authenticated without role returns 403 on role-protected routes;
- fallback denies all sensitive unlisted endpoints;
- `/api/**` is not shadowed by the fallback chain;
- custom filter executes exactly once on successful requests and never invokes services twice;
- `OPTIONS` CORS preflight is handled properly;
- POSTs enforce CSRF tokens or explicit stateless policy;
- `ASYNC`/`ERROR` dispatches cause no surprises;
- when deploying as a WAR/external Tomcat, also inspect `web.xml` and `@WebFilter` registrations;
- proxy retries/redirects are not mistaken for duplicate in-app filters.

## 10. CORS and CSRF: Wrong Ordering Can Cause 401/403

### 10.1. CORS Preflight

Browsers may send:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: Authorization, Content-Type
~~~

Preflight requests generally **carry no session cookies** like the main request. If authentication logic runs before CORS and demands credentials, responses easily become 401/403. Spring Security provides `http.cors(Customizer.withDefaults())` and integrates with `CorsConfigurationSource`/MVC CORS config.

**Do not** register the same `CorsFilter` once in the container and once inside Spring Security without an explicit design; doing so can duplicate `Access-Control-Allow-*` headers or break preflight handling.

**Illustrative** configuration snippet (omits allowed origins and full imports):

~~~java
http.cors(Customizer.withDefaults())
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated());
~~~

CORS **is not authorization**. It only governs whether browsers allow a frontend origin to read cross-origin responses. `Origin` policies must use explicit allowlists and proper credential rules; never reflect arbitrary origins just to avoid 403.

### 10.2. CSRF

`CsrfFilter` protects state-changing requests per security policy. In session/cookie web apps, form POSTs without tokens return 403. Never disable CSRF app-wide to “fix a filter running twice”: verify whether the right chain was selected, the HTTP method, CSRF token, session, repository, and which filters ran.

Stateless APIs receiving only bearer tokens in `Authorization` headers may use a different CSRF policy, grounded in a clear threat model and separate chain configuration. Do not assume every SPA, cookie, or cross-site credential flow is safe with `csrf.disable()`.

### 10.3. JWT Decoded Twice

If you already enabled:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
~~~

Spring Security installs `BearerTokenAuthenticationFilter` and its authentication pipeline. Adding a separate `CustomJwtFilter` that also reads `Authorization: Bearer ...`, parses the JWT, calls upstream verification, and sets `SecurityContext` again creates **duplicate authentication logic** even without duplicate Servlet filter registration. Use proper extension points such as `JwtDecoder`/`JwtAuthenticationConverter`/AuthenticationProvider or a post-authentication audit filter instead of adding a redundant token-parsing filter unnecessarily.

**Never log Authorization headers, passwords, or JWTs** while debugging, as that leaks secrets. Logging filter name, request ID, dispatcher type, status, and policy outcome is sufficient for most cases.

## 11. Wrong Ordering and Double Registration in Other Patterns

### 11.1. Filter Using SecurityContext Registered in the Container Before the Security Proxy

A servlet filter with `@Order(HIGHEST_PRECEDENCE)` running before `DelegatingFilterProxy` will **not automatically see authentication created by Spring Security**. If it needs the logged-in user ID, place it inside the Spring Security chain after the authentication filters per security architecture. Do not “fix” it by manually parsing raw JWTs in that filter when Spring Security already has a decoder.

### 11.2. Filter Using `OncePerRequestFilter` Yet Running Again on Error Dispatch

When a controller throws an exception, the servlet container may dispatch to `/error`. If a second log appears with `DispatcherType.ERROR`, that is likely the error path rather than duplicate registration. Inspect `shouldNotFilterErrorDispatch()`, filter mappings, and the error endpoint. Some nested error dispatches have distinct lifecycles; never use global guards that make failing requests skip authentication.

### 11.3. Async Controllers and WebAsyncManager

Controllers returning `Callable`/`DeferredResult` or using Servlet async can trigger `ASYNC` dispatches. `WebAsyncManagerIntegrationFilter` assists with context propagation in Spring MVC. When a custom filter must run on every async dispatch, make it thread-safe and explicitly configure `shouldNotFilterAsyncDispatch()`, servlet dispatcher types, and context propagation. **Do not confuse logs from two threads with two Servlet registrations.**

### 11.4. Reverse Proxies and Retries

CDNs/ingress may retry GETs on upstream failures or issue HTTP↔HTTPS redirects. Two requests arriving at the app run two full passes of Servlet filters; “once per request” does not mean “once per browser action”. Use correlation IDs from a trusted ingress and distributed traces to distinguish two real HTTP requests.

## 12. WebFlux: Use WebFilter, Never Directly Apply Servlet Filters

In **Spring WebFlux/Netty**, Spring Security uses a different ecosystem:

| MVC/Servlet | WebFlux/Reactive |
| --- | --- |
| `jakarta.servlet.Filter` | `org.springframework.web.server.WebFilter` |
| `FilterChainProxy` | `WebFilterChainProxy` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpSecurity` | `ServerHttpSecurity` |
| `addFilterBefore/After` | `addFilterAt(WebFilter, SecurityWebFiltersOrder)` |
| Servlet container registration | Reactive web filter configuration |
| `OncePerRequestFilter` | Does not apply directly to reactive WebFilter |

Illustrative WebFlux configuration snippet (does not belong in the MVC project; requires WebFlux Security dependencies/imports):

~~~java
@Bean
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Inspect `SecurityWebFilterChain` ordering and `SecurityWebFiltersOrder` for custom reactive filters. If a `WebFilter` is registered both in the outer reactive chain and inside the Spring Security chain, logic can run multiple times just like in Servlet, though Servlet's `FilterRegistrationBean` is not the fix in Netty.

If a project includes both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot normally favors the Servlet MVC application type. Never assume WebFlux is active merely because `Mono` or `WebClient` appears. And never rely on ThreadLocal security context as if a reactive stream always executes on one thread.

## 13. Anti-Patterns and Quick Fixes

| Anti-pattern | Flaw | Fix |
| --- | --- | --- |
| `@Component Filter` + `addFilterBefore(bean, ...)` | Boot auto-registers in container, Security also invokes filter | Avoid making it a bean or disable Servlet registration |
| `@WebFilter`/`@ServletComponentScan` + filter bean | Two Servlet registrations can duplicate execution | Pick only one registration mechanism |
| Manually registering two `DelegatingFilterProxy` beans | Spring Security pipeline can run twice | Let Boot register the proxy once |
| `/**` chain `@Order(1)` before `/api/**` | Specific chain gets shadowed | Narrow chains first, fallback last |
| Thinking `requestMatchers` selects the chain | Confusing authorization matcher with chain matcher | `securityMatcher` selects the chain |
| Using `FilterRegistrationBean#setOrder` to order a custom security filter | `setOrder` affects only the container chain | Use `HttpSecurity.addFilterBefore/After` |
| `OncePerRequestFilter` hiding symptoms | Duplicate registration still exists | Fix root cause and audit both registries |
| Static boolean “alreadyFiltered” | Subsequent requests get skipped | Guard only per request/dispatch per contract |
| Calling `chain.doFilter(...)` twice | Downstream can execute twice | Continue strictly once when appropriate |
| Verifying JWT in two filters | Extra CPU and overwritten auth context | Use built-in bearer support and extension points |
| Disabling CORS/CSRF or setting `permitAll` to fix 401/403 | Creates new security vulnerabilities | Keep policies and fix filter ordering/config |
| Logging credentials to debug | Leaks passwords/tokens/cookies | Log only safe metadata |
| Testing only standalone MockMvc | Misses Boot Servlet auto-registration | Add `RANDOM_PORT` integration tests |

## 14. Immediate Debugging Workflow

1. Record HTTP method, path, request ID, dispatcher type, and response status. Count per real request, not merely per URL.
2. Enable `DefaultSecurityFilterChain=DEBUG` to view chains/matchers/filters at startup, and `FilterChainProxy=TRACE` in staging to watch route selection.
3. Inspect actual Servlet registrations via container registry/logs. Do not mistake the valid `springSecurityFilterChain` proxy for an extra custom filter registration.
4. Search all filter sources: `@Component`, `@Bean Filter`, `@WebFilter`, `@ServletComponentScan`, `FilterRegistrationBean`, manual `ServletContext.addFilter`, and library auto-config.
5. Check whether the custom filter has **one** instance or multiple instances, and which security/container chains hold it.
6. Verify chain `@Order`, `securityMatcher`, fallback, and authorization `requestMatchers`. Prevent broad chains from shadowing narrow ones.
7. Check custom filter placement relative to authn, authz, CORS/CSRF, and `SecurityContextHolderFilter`. Watch especially for custom JWT parsers alongside resource server.
8. Separate `REQUEST` from `ERROR`/`ASYNC`; account for browser redirects, favicons, preflights, and proxy retries.
9. Run full HTTP container integration tests checking 401/403/200, filter counts, routes, anonymous/authenticated callers, and CSRF/CORS.
10. Fix **the root cause**: remove the second registration, disable `FilterRegistrationBean` for a Security-managed bean, or fix `@Order`/matchers. Never disable Spring Security as a “fix”.
11. Re-run tests, turn off TRACE, remove temporary debug endpoints, and keep secrets out of logs.

### Symptom → Suspected Cause

| Symptom | Possible Explanation | Verification |
| --- | --- | --- |
| Custom filter appears in both servlet registry and security DEBUG | Double registration | Compare classes/instances and bean/registration sources |
| `auditCount=2` after adding `@Component` | Container added another filter pass | Remove `@Component`; use `new` or disabled registration |
| Filter logs once yet HTTP response shows two traces | Two requests/dispatches or guard hid nested pass | Request ID, dispatcher type, servlet registry |
| `/api/**` handled by fallback chain | Broad chain came first or wrong matcher | TRACE first matching, `@Order` |
| OPTIONS returns 401 | CORS preflight blocked by auth | CORS config and filter ordering |
| POST returns 403 | Missing CSRF token or authorization | Log selected chain, CSRF, authentication |
| Filter sees no user | Positioned before authentication or context loading | Check relative order and auth provider |
| MockMvc passes, prod calls twice | Test did not start real container auto-registration | `SpringBootTest RANDOM_PORT` |
| Duplicate JWT verification | Built-in resource server + custom parser | Filter chain list and decoder metrics |
| Error happens only on `/error` | `ERROR` dispatch | `DispatcherType`, filter mappings |
| Added `setOrder(-100)` yet custom security filter position unchanged | Adjusted container order by mistake | Use `addFilterBefore/After` |
| Sensitive endpoint unprotected | No security chain matched or fallback `permitAll` | Chain matchers and deny-by-default |

## 15. Self-Check Questions

1. How do `DelegatingFilterProxy` and `FilterChainProxy` differ in responsibility?
2. Does having two `SecurityFilterChain` beans mean a request runs through both?
3. How do `@Order(1)` on a security chain and `addFilterBefore` differ?
4. Why can a `Filter` with `@Component` also passed to `http.addFilterBefore(bean, ...)` run twice?
5. How do you keep a Filter bean running only inside the Spring Security chain without Boot auto-registering it in the container?
6. Does `OncePerRequestFilter` prove there is only one Servlet registration?
7. How does `securityMatcher("/api/**")` differ from `requestMatchers(...)` inside `authorizeHttpRequests`?
8. Why can a catch-all chain placed first create a vulnerability?
9. Should a user-authenticating filter run before or after `AuthorizationFilter`?
10. When a URL is logged twice, which dispatcher types and client behaviors should you inspect?
11. Why is `@SpringBootTest(webEnvironment=RANDOM_PORT)` needed to catch duplicate Servlet registrations?
12. Does `FilterRegistrationBean#setOrder` position a filter inside a `SecurityFilterChain`?
13. Why can a CORS preflight get 401 right before login even when the browser has a session?
14. With `oauth2ResourceServer().jwt()`, why does a separate custom JWT filter cause double-auth?
15. If a filter needs dependency injection, what ways avoid container auto-registration?
16. Should you switch all endpoints to `permitAll` when hitting duplicate filters or 403s?
17. In the sample project, is `AuditFilter.COUNT` a request attribute or a static global counter?
18. Why do two logs with different request IDs not prove a single request was processed twice?
19. Spring WebFlux uses `WebFilterChainProxy` and which security chain type?
20. Why is `OncePerRequestFilter#doFilterInternal` running only once insufficient to prove there is no duplicate registration?

**Key answers:** (1) Servlet proxy looks up the Spring bean; `FilterChainProxy` selects the matching security chain. (2) No, first match only. (3) `@Order` orders chains; `addFilterBefore` orders internal filters. (4) Boot may auto-register the Servlet Filter bean while Spring Security also invokes the bean. (5) `FilterRegistrationBean#setEnabled(false)`. (6) No. (7) Selects the chain vs authorization rule within a chain. (8) Specific chains get shadowed or wrong policies apply. (9) Before. (10) `REQUEST`/`ERROR`/`ASYNC`/`FORWARD`, redirects/retries/OPTIONS. (11) It runs the real embedded server/registrations. (12) No. (13) Preflights typically carry no authentication cookies. (14) Two processors parse/verify tokens and set context. (15) Instantiate a non-bean receiving services via constructor, or use a bean + disabled registration. (16) No, fix the root cause. (17) Request attribute. (18) They may be two separate HTTP requests. (19) `SecurityWebFilterChain`. (20) The guard can hide a nested invocation while registration remains broken.

## 16. Official Sources

- Spring Security 6.5 — Servlet architecture, DelegatingFilterProxy, FilterChainProxy, Filter order, custom filter bean registration: https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security 6.5 — Multiple HttpSecurity, `securityMatcher` vs `requestMatchers`, and first-matching chain: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Boot 3.5 — Embedded Web Servers, disable Servlet/Filter bean registration: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Framework 6.2 — OncePerRequestFilter API, ASYNC/ERROR dispatch: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- Spring Security 6.5 — Reactive Security/`SecurityWebFilterChain`: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 — Reactive architecture/`WebFilterChainProxy`: https://docs.spring.io/spring-security/reference/6.5/reactive/architecture.html
- Spring Boot 3.5.16, System Requirements (Java 17+): https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Boot 3.5.16, release announcement and end of OSS support: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/