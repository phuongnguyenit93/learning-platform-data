# Filter Extension Points and the Risk of Registering the Same Filter Twice

## 1. The Problem: Adding One Filter Yet the App Invokes It in Two Places

In Servlet-based Spring Security, developers often want to add a custom Filter to attach a correlation ID, validate a tenant, verify a specialized credential, record audit events, or enforce an extra security policy.

A natural first instinct is to create a Spring bean:

~~~java
@Component
public class TenantFilter extends OncePerRequestFilter {
    // Tenant-checking logic here.
}
~~~

and then insert that filter into Spring Security configuration:

~~~java
http.addFilterBefore(tenantFilter, AuthorizationFilter.class);
~~~

These are two **illustrative snippets**, not a complete file. Together they can create a subtle bug: **Spring Boot can automatically register a Filter-typed Spring bean with the Servlet Container, while Spring Security also adds that exact same filter into SecurityFilterChain**.

As a result, a single HTTP request can traverse the filter at **two different positions**, with differing order, URL scope, dispatcher types, and SecurityContext. With a plain Filter, logic can execute twice. With `OncePerRequestFilter`, the "already filtered" mechanism may cause `doFilterInternal` to run once on certain paths, yet **the dual registration is still broken** and creates a dangerous dependency on execution order.

This lesson focuses on **filter extension points and the risk of registering the same filter twice**, in the **Servlet Architecture** group of the **Spring Security - fundamentals** module. Examples use Java 17+, Spring Boot 3.x, Spring Security 6.x, and the Jakarta Servlet API. A runnable Spring Boot lab uses two profiles to verify over real HTTP:

- **safe:** The Filter bean runs only inside Spring Security because Servlet Container registration is disabled.
- **double:** Intentionally omits disabling container registration, showing the same Filter bean invoked by both the container and Spring Security.

**End goal:** know how to pick a filter position by responsibility, register at exactly one layer, verify the real chain, and avoid breaking authentication, CSRF, authorization, or logging.

### Key Takeaways After This Lesson

1. Distinguish the Servlet Container FilterChain from FilterChainProxy/SecurityFilterChain.
2. Understand accurately which layer `addFilterBefore`, `addFilterAfter`, and `addFilterAt` operate on.
3. Choose anchor filters based on when SecurityContext is restored, credentials are verified, and authorization runs.
4. Know why a `@Component Filter` or `@Bean Filter` can be auto-registered by Spring Boot with the Servlet Container.
5. Know how to avoid double registration by instantiating with `new Filter` (non-bean), or using `FilterRegistrationBean.setEnabled(false)` when dependency injection is needed.
6. Understand the limits of `OncePerRequestFilter` when diagnosing double registration.
7. Run the lab using the same filter bean across `safe`/`double` profiles and count actual invocations per request.
8. Use embedded Servlet Container integration tests to inspect the real path instead of relying solely on MockMvc.
9. Distinguish a "twice" bug from ASYNC/ERROR dispatches, CORS preflights, extra browser requests, and multiple SecurityFilterChains.
10. Security review: filters before authentication cannot trust a principal, filters after authorization may never run, and exception mapping depends on position.

## 2. Two Independent Filter Layers in a Spring MVC App

A Servlet application typically receives requests through a Servlet Container (Tomcat/Jetty/Undertow depending on stack). The container builds a Servlet-level Filter chain, inside which Spring Security sits via a bridge called `DelegatingFilterProxy`.

~~~text
HTTP Client
    |
    v
Servlet Container
    |
    v
ContainerFilter A
    |
    v
DelegatingFilterProxy
    |  target bean: springSecurityFilterChain
    v
FilterChainProxy              (Spring Security Filter)
    |
    +-- First matching SecurityFilterChain
    |        |
    |        +-- SecurityContextHolderFilter
    |        +-- HeaderWriterFilter / CsrfFilter ...
    |        +-- Authentication filters ...
    |        +-- AnonymousAuthenticationFilter ...
    |        +-- ExceptionTranslationFilter ...
    |        +-- AuthorizationFilter ...
    |
    v
ContainerFilter B
    |
    v
DispatcherServlet
    |
    v
@RestController
~~~

This diagram is **illustrative**, not a fixed filter list for every version/configuration. ContainerFilter A/B may appear before or after the Spring Security bridge depending on registration order. Specific security filters depend on the HttpSecurity DSL, session policy, login mechanism, and selected beans.

### 2.1. Container Filter

A Servlet Container-level Filter is registered via the Servlet API, web.xml, `@WebFilter` with appropriate scanning, or Spring Boot's **FilterRegistrationBean**. It participates in the Filter chain managed by the Servlet Container, regardless of whether a URL matches any SecurityFilterChain.

Key properties:

- **URL patterns / servlet names** of the registration.
- **Dispatcher types** such as REQUEST, ASYNC, ERROR.
- **Container registration order**.
- Servlet lifecycle `init`, `doFilter`, `destroy`.
- Ability to block requests before reaching Spring Security or Controllers.

A Container Filter can operate without knowing about Authentication or SecurityContext. However, if its code reads SecurityContextHolder before Spring Security restores the context, it may observe anonymous or null.

### 2.2. DelegatingFilterProxy

`DelegatingFilterProxy` is a Spring Framework Servlet Filter. When the Container invokes it, the proxy looks up a Filter bean by target name—typically **springSecurityFilterChain**—and delegates `doFilter` to that bean.

The target bean is normally Spring Security's **FilterChainProxy**. Consequently, the Servlet Container does not need to register individual `CsrfFilter`, `AuthorizationFilter`, or `BasicAuthenticationFilter` instances. The container invokes only the bridge, while FilterChainProxy manages the security filters.

**Never manually register an extra DelegatingFilterProxy just because you defined a SecurityFilterChain bean.** In a standard Spring Boot Servlet app with `spring-boot-starter-security`, the bridge is already auto-configured.

### 2.3. FilterChainProxy and SecurityFilterChain

`FilterChainProxy` holds one or more `SecurityFilterChain` instances. Each `SecurityFilterChain` has a `RequestMatcher` and a list of Filters. Under normal operation, **the first chain matching the request is selected**; matching chains are not combined.

Therefore, a custom filter added to an `/api/**` chain will not automatically appear in an `/admin/**` chain or fallback chain. If needed across multiple chains, define its scope explicitly and register it in each relevant chain.

### 2.4. Layer Comparison Table

| Aspect | Servlet Container Filter | Spring Security Chain Filter |
| --- | --- | --- |
| Where registered | web.xml, ServletContext, FilterRegistrationBean, auto-registered Filter bean | HttpSecurity or SecurityFilterChain |
| Who invokes it? | Servlet Container | FilterChainProxy |
| Ordering | Container filter registration order | Spring Security filter ordering |
| URL scope | URL/servlet mapping and dispatcher types | SecurityFilterChain RequestMatcher |
| SecurityContext | May run before context is created/restored | Can be placed after context/auth steps as needed |
| Common way to add | FilterRegistrationBean | addFilterBefore/addFilterAfter/addFilterAt |
| Duplicate registration risk | Same bean is also in SecurityFilterChain | Same bean is also auto-registered by Boot |
| Good fit for | Identity-independent tracing, servlet diagnostics | Authentication, authorization, tenant checks needing Authentication |

## 3. Three Extension APIs in HttpSecurity

Spring Security provides methods to place a custom filter at an intentional position inside `SecurityFilterChain`:

~~~java
http.addFilterBefore(customFilter, ExistingFilter.class);
http.addFilterAfter(customFilter, ExistingFilter.class);
http.addFilterAt(customFilter, ExistingFilter.class);
~~~

These are **three alternative choices illustrating the API**, not advice to call all three for one filter. `ExistingFilter` must be a filter class whose order is known to Spring Security; the placeholder class in the snippet is not a real class.

### 3.1. addFilterBefore

Places the custom Filter **before the order slot** of the anchor filter inside `SecurityFilterChain`.

~~~java
http.addFilterBefore(
    tenantAuthorizationFilter,
    AuthorizationFilter.class
);
~~~

For a custom tenant/ownership check that needs verified Authentication and needs `ExceptionTranslationFilter` upstream to translate `AccessDeniedException` into an HTTP response, placing it before `AuthorizationFilter` **can make sense** in a standard setup. Always inspect the chain's actual filter list.

Do not assume `addFilterBefore(..., AuthorizationFilter.class)` behaves identically with every custom DSL or in a chain that removed `AuthorizationFilter`. When depending on a specific filter being present, verify the built chain.

### 3.2. addFilterAfter

Places the filter **after the position** of the anchor filter:

~~~java
http.addFilterAfter(
    customObservationFilter,
    BasicAuthenticationFilter.class
);
~~~

This snippet illustrates placement only. If `BasicAuthenticationFilter` receives invalid Basic credentials and **halts the request without continuing the chain**, a filter placed after it **will not run** on failed requests. Do not choose a "post-auth" position for failure auditing if you actually need to record requests rejected by the auth filter.

A filter placed after `BasicAuthenticationFilter` also does not guarantee every authentication type has finished: a chain might use `BearerTokenAuthenticationFilter`, form login, or another mechanism.

### 3.3. addFilterAt

Places a custom filter **at the order slot of a known filter**:

~~~java
http.addFilterAt(
    customAuthenticationFilter,
    UsernamePasswordAuthenticationFilter.class
);
~~~

**This is not guaranteed to be a safe "replace object" operation in every situation.** Reference docs sometimes use "replace" colloquially to describe intent, yet `HttpSecurity` Javadoc explains that filters at the same order do not automatically overwrite one another; ordering between them can be undefined. Some configurations or versions also detect collisions/duplicates and refuse to build the chain.

**Practical rule:** if you intentionally replace an old mechanism, **do not enable the DSL that creates the old filter** (or disable that mechanism properly) and configure your custom filter with all required auth/exception/session wiring. Never rely on `addFilterAt` to "override" an already-registered `BasicAuthenticationFilter`/`UsernamePasswordAuthenticationFilter`.

### 3.4. addFilter Differs from the APIs Above

`HttpSecurity.addFilter(...)` generally accepts only a filter whose class/subclass already has a framework-registered order. For brand-new custom filters, `addFilterBefore`/`After`/`At` are easier to control.

Passing a filter with no registered order to `addFilter` can throw an error; never solve that by picking an arbitrary order slot with no security meaning.

### 3.5. Do Not Use @Order on a Filter Bean Expecting It to Affect Order Inside SecurityFilterChain

**`@Order`/Ordered on a Filter bean** or `FilterRegistrationBean` normally governs container registration order. Inside `SecurityFilterChain`, Spring Security uses its own ordering table and `HttpSecurity` APIs.

If the requirement is "run before `AuthorizationFilter` yet after Authentication", configure **`HttpSecurity`**, not **`FilterRegistrationBean.order`**.

## 4. Choosing Placement by Which Security Event Must Happen First

Instead of asking "before class X or after class Y?" first, ask **what does my filter need to trust on the request?**

A typical chain has these stages:

~~~text
[Load SecurityContext]
          |
[Exploit protection: headers, CSRF, CORS ...]
          |
[Authentication: verify credentials]
          |
[Anonymous fallback if not logged in]
          |
[Translate security exceptions]
          |
[Authorization]
          |
[Servlet / Controller]
~~~

Real configurations have many additional filters. Order depends on version and authentication mechanism. Do not treat this diagram as an exhaustive hardcoded list.

### 4.1. Reference Placement Table

| Need | Depends On | Approach |
| --- | --- | --- |
| Attach request ID without needing Authentication | Servlet request | Container filter or pre-security filter, protecting sensitive data |
| Handle a custom authentication mechanism | Credential format, AuthenticationManager, context | Authentication stage slot; consider built-in DSL/provider |
| Check current user's tenant | Verified Principal | After authentication and before authorization in the real chain |
| Block wrong resource owner | Authentication + trusted resource ID | Prefer authorization/service method; if filter, ensure proper exception handling |
| Record metrics on every response, including 401 | Wraps entire pipeline | Outer filter or proven early position covering all branches; never log tokens/bodies |
| Add security headers | Response | Prefer `headers` DSL; avoid unnecessary custom filters |
| Check CSRF | Session/cookie/form state | Use standard `csrf` DSL/`CsrfFilter` |
| Endpoint authorization | Granted authorities | Use `authorizeHttpRequests`, method security before writing custom filters |
| Analyze processing latency | Pre/post invocation | Watch position and short-circuiting by earlier filters |
| Run on ERROR/ASYNC dispatches | Dispatcher type/context propagation | Configure registration explicitly and test each dispatch type |

**There is no "single right position for every custom filter".** Placement depends on what data the filter reads, when Authentication becomes available, and which layer's errors the filter must wrap or sit inside.

### 4.2. When Needing Authentication, Do Not Run Too Early

Example code reading `SecurityContextHolder`:

~~~java
Authentication current =
    SecurityContextHolder.getContext().getAuthentication();
~~~

If the filter sits before `SecurityContextHolderFilter` or before the authentication mechanism that verifies credentials, `current` may be null or stale/unverified. A request carrying an `Authorization` header does not mean the header has already been verified.

If your goal is checking user permissions, never manually parse JWTs, Basic headers, or client-supplied usernames to grant authority. Use the `Authentication` verified by a provider/token verifier.

### 4.3. ExceptionTranslationFilter Affects How 401/403 Are Produced

`ExceptionTranslationFilter` normally converts matching `AuthenticationException`/`AccessDeniedException` from **downstream in the security chain** into entry point / access denied handler actions.

If a custom filter throws `AccessDeniedException` **before** `ExceptionTranslationFilter`, that exception may not be caught by the filter's standard handler because it originated **upstream**. You may see a 500 error or error dispatch depending on configuration.

Hence determine where an authorization-checking filter sits relative to `ExceptionTranslationFilter` and `AuthorizationFilter`. For complex business authorization, an `AuthorizationManager` or method security is usually cleaner than a hand-written Servlet filter.

### 4.4. Authentication Filters Need More Than Just a Slot

A filter performing real authentication may need to:

- Parse credentials safely.
- Delegate credentials to a trusted `AuthenticationManager`/provider.
- Create and populate `SecurityContext` after successful authentication.
- Execute session strategy if required by a session-based architecture.
- Save context if using Spring Security 6 explicit-save and persistence is needed.
- Handle authentication failures and security exceptions.
- Never log raw passwords, tokens, cookies, or entire `Authentication` objects.
- Apply rate limiting and mitigate user-enumeration/timing risks.

Therefore, do not replace built-in `UsernamePasswordAuthenticationFilter` just to rename a form field when a DSL option already exists.

### 4.5. Observing Failures Differs from Blocking Requests

An audit filter placed before `BasicAuthenticationFilter` sees incoming requests, yet **does not automatically know the authentication outcome** without integrating with events/handlers. Placed after `BasicAuthenticationFilter`, it may see only successful requests. For authentication auditing, `AuthenticationSuccessEvent`/`AuthenticationFailureEvent`, handlers, or proper observability integrations are more accurate than guessing from filter position.

## 5. Where Does the Risk of Registering the Same Filter Twice Start?

In a Spring Boot Servlet application, a Spring bean implementing `jakarta.servlet.Filter` is considered by Boot for **automatic registration with the Servlet Container**.

Example:

~~~java
@Bean
TenantFilter tenantFilter(TenantService service) {
    return new TenantFilter(service);
}
~~~

or:

~~~java
@Component
public class TenantFilter extends OncePerRequestFilter {
    // ...
}
~~~

When the same instance is later passed into `HttpSecurity`:

~~~java
@Bean
SecurityFilterChain security(
        HttpSecurity http, TenantFilter tenantFilter) throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .addFilterBefore(tenantFilter, AuthorizationFilter.class)
        .build();
}
~~~

These three snippets illustrate declaration and usage, not a complete project. **If a Filter is a Spring bean without a registration override**, Boot can put the bean into the **Servlet Container FilterChain** while `HttpSecurity` puts the same bean into **`SecurityFilterChain`**.

### 5.1. Request Path in the Broken Configuration

~~~text
HTTP GET /private
      |
      v
Servlet Container FilterChain
      |
      v
DelegatingFilterProxy
      |
      v
FilterChainProxy
      |
      +-- TenantFilter [doFilter pass 1: added by HttpSecurity]
      |
      v
Container FilterChain continues
      |
      +-- TenantFilter [doFilter pass 2: Boot auto-registered bean]
      |
      v
DispatcherServlet
      |
      v
Controller
~~~

This is an **illustrative ordering**; the container is not guaranteed to always call it in that exact spot. Under another registration order, the container pass may happen before the security pass. The invariant in this bug is **two registration paths exist**, so a single HTTP request can hit the same filter twice.

If the Filter has side effects—incrementing retry counters, writing audit logs, publishing messages, mutating sessions, or altering responses—running twice can cause severe bugs.

### 5.2. Security Impact of Running Twice

- **Wrong timing for permission checks:** the container pass runs before Authentication is established, seeing null/anonymous.
- **Doubled rate-limit counters:** a single login counts twice or throttles users prematurely.
- **Doubled side effects:** audit/tracing/billing/event-bus emissions fire twice.
- **Overwritten cookies/headers:** the second pass overwrites the first pass's result.
- **Unexpected response commits:** a custom filter emits 401/403 at the container layer before the security entry point handles it.
- **Bypass across multiple chains:** the container filter still runs on requests outside `securityMatcher`, while the security filter does not.
- **Skewed request metrics:** request counts/latency get doubled or measure two different phases.
- **Sensitive data in logs:** a container pass accidentally logs Authorization/Cookies outside Spring Security's guards.

The program may still appear to "run", yet permissions and telemetry are untrustworthy. Fix registration ownership rather than hiding symptoms in logs.

## 6. How to Avoid It: Two Valid Approaches

### 6.1. Option A — Instantiate Directly Inside HttpSecurity

If the filter has few Spring bean dependencies, instantiate it directly inside `SecurityFilterChain`:

~~~java
@Bean
SecurityFilterChain security(HttpSecurity http)
        throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .addFilterBefore(
            new TenantFilter(),
            AuthorizationFilter.class)
        .build();
}
~~~

This is a snippet inside a `@Configuration` class; `TenantFilter` is application-defined, not a standalone file.

Because `new TenantFilter()` is **not declared as `@Bean`/`@Component`** and is not registered as a Servlet Filter elsewhere, Spring Boot does not auto-register this instance with the container.

Pros: minimal config, zero risk of Spring-bean auto-registration. Cons: if the filter needs many dependencies, you must pass them via constructor or use Option B.

### 6.2. Option B — Keep the Filter as a Spring Bean, Disable Container Registration

If the filter needs dependency injection, declare the bean and a `FilterRegistrationBean` with `enabled=false`:

~~~java
@Bean
TenantFilter tenantFilter(TenantService service) {
    return new TenantFilter(service);
}

@Bean
FilterRegistrationBean<TenantFilter> disableTenantFilterRegistration(
        TenantFilter filter) {

    FilterRegistrationBean<TenantFilter> registration =
        new FilterRegistrationBean<>(filter);

    registration.setEnabled(false);
    return registration;
}

@Bean
SecurityFilterChain security(HttpSecurity http,
        TenantFilter filter) throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .addFilterBefore(filter, AuthorizationFilter.class)
        .build();
}
~~~

This is a **configuration snippet** assuming the application provides the classes/imports, not a complete Java file. A **disabled** `FilterRegistrationBean` does not delete the bean from `ApplicationContext`; it simply instructs Boot **not to register this Filter bean with the Servlet Container**.

The filter still executes inside `SecurityFilterChain` via `HttpSecurity.addFilterBefore`. This cleanly separates responsibilities:

- **Spring bean:** manages dependencies/lifecycle.
- **Disabled FilterRegistrationBean:** suppresses Servlet Container registration.
- **HttpSecurity:** registers the filter once at the desired security stage.

### 6.3. When You Genuinely Want a Filter at the Servlet Container Layer

For a tracing/diagnostics filter independent of Spring Security, you can deliberately register it via `FilterRegistrationBean` on the container with explicit URL patterns, order, and dispatcher types. In that case, **do not also add the same instance to `HttpSecurity`**.

This is also a valid design: not every Servlet Filter belongs inside `FilterChainProxy`.

### 6.4. Decision Table

| Scenario | Registration Approach |
| --- | --- |
| Custom filter doing authn/authz inside Spring Security only | `HttpSecurity.addFilterBefore/After`, no container registration |
| Custom filter needing Spring DI and running only in security chain | `@Bean` + `FilterRegistrationBean.setEnabled(false)` + `HttpSecurity` |
| Tracing filter meant to run outside security chain | `FilterRegistrationBean` with `enabled=true`, do not add to `HttpSecurity` |
| Standard Basic/Csrf/Cors/Headers filters | Corresponding Spring Security DSL |
| Filter needed across multiple SecurityFilterChains | Configure per matching chain; watch shared state and filter instances |
| Checking permissions on individual entities/records | `AuthorizationManager`/method security/service rather than a generic filter when appropriate |

## 7. Does OncePerRequestFilter Solve Double Registration?

**No.** `OncePerRequestFilter` helps prevent duplicate `doFilterInternal` execution in certain cases, yet it is not a fix for wrong registration.

To see why, trace the request-attribute marker idea:

~~~text
Filter entry #1
   |
   +-- No already-filtered marker yet
   +-- Set marker on request
   +-- Invoke doFilterInternal
   |        |
   |        +-- chain.doFilter to downstream
   |                 |
   |                 +-- Filter entry #2
   |                       |
   |                       +-- Sees marker: skip doFilterInternal
   |
   +-- End of entry #1, clear marker
~~~

In a nested path like this, the same `OncePerRequestFilter` instance may run **`doFilterInternal` once** even with two registrations. A developer checks a log line inside `doFilterInternal` and wrongly concludes the filter was registered only once.

### 7.1. Why "Once" Is Not an Absolute Once-Ever Guarantee Across All Cases

- The marker uses a request attribute; behavior can depend on filter name and instance.
- With two distinct instances or different filter names, markers can differ.
- `ERROR`/`ASYNC` dispatches have their own lifecycle and skip hooks.
- One HTTP request can undergo multiple dispatches rather than a single `REQUEST`.
- Filters registered at two layers occupy different positions even if inner logic is skipped.
- If an earlier filter blocks the request, one of the two registrations may never be reached.

Therefore, **never rely solely on log counts inside `doFilterInternal` to prove there is no duplicate registration**.

### 7.2. Using a Plain Filter to Prove It Precisely in the Lab

The hands-on lab uses a **plain `jakarta.servlet.Filter`**, not extending `OncePerRequestFilter`, to count every `doFilter` call. This cleanly exposes **two registrations → two invocations** in the broken setup.

In real products, a filter may extend `OncePerRequestFilter` for Servlet API convenience and async/error semantics, yet it must still have a single, intentional registration path.

## 8. Lab: Two Profiles (safe and double) with One Filter Bean

We build a single Spring Boot Servlet application with:

1. **CountingProbeFilter:** a plain `Filter` and Spring bean that increments a request attribute on every `doFilter` call.
2. **SecurityFilterChain:** always adds this bean **before `AuthorizationFilter`**.
3. **Profile `safe`:** provides `FilterRegistrationBean<CountingProbeFilter>` with `setEnabled(false)`, leaving only the Spring Security registration.
4. **Profile `double`:** omits the disabled registration, so Boot auto-registers the Filter bean on the Servlet Container while `HttpSecurity` adds a second call path.
5. **ContainerMarkerFilter:** a separate container-only filter (not reusing the probe bean) adding a header to show the container layer.
6. **GET `/inspect`:** returns how many times `CountingProbeFilter` was invoked on that request.
7. **`/private`, `/admin`:** verifies authentication and authorization still work properly.

**Profile `double` is intentionally broken for learning only. Never use it in production.**

### 8.1. Project Creation

Use Spring Initializr to generate a Java 17+, Spring Boot 3.x, Gradle Groovy DSL project with Gradle Wrapper, selecting Spring Web, Spring Security, and Spring Boot Starter Test.

In the `dependencies` block of `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is the **dependencies section of a project already configured with the Spring Boot plugin, Java toolchain, and dependency management**, not a standalone `build.gradle`.

### 8.2. application.properties

Create **src/main/resources/application.properties**:

~~~properties
# Default runs the properly fixed approach.
spring.profiles.default=safe
~~~

When no active profile is specified, Spring selects `safe`. Running with **`--spring.profiles.active=double`** deactivates the default profile and drops the disabled-registration bean.

### 8.3. Complete Java File

Create **src/main/java/com/example/filterplacement/FilterPlacementApplication.java**:

~~~java
package com.example.filterplacement;

import java.io.IOException;
import java.util.Map;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.core.Ordered;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class FilterPlacementApplication {

    public static void main(String[] args) {
        SpringApplication.run(FilterPlacementApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("local-learn-only"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("local-admin-only"))
                .roles("ADMIN")
                .build()
        );
    }

    // This bean may be auto-registered by Boot at the Servlet Container level.
    @Bean
    CountingProbeFilter countingProbeFilter() {
        return new CountingProbeFilter();
    }

    // Safe profile: prevent container-level auto registration.
    @Bean
    @Profile("safe")
    FilterRegistrationBean<CountingProbeFilter> disableContainerProbe(
            CountingProbeFilter filter) {

        FilterRegistrationBean<CountingProbeFilter> registration =
            new FilterRegistrationBean<>(filter);
        registration.setEnabled(false);
        return registration;
    }

    // A filter truly intended only for the Servlet Container.
    @Bean
    FilterRegistrationBean<ContainerMarkerFilter> containerMarker() {

        FilterRegistrationBean<ContainerMarkerFilter> registration =
            new FilterRegistrationBean<>(
                new ContainerMarkerFilter());

        registration.setName("labContainerMarker");
        registration.addUrlPatterns("/*");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        return registration;
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http, CountingProbeFilter filter)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/inspect", "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/private")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .addFilterBefore(filter, AuthorizationFilter.class)
            .build();
    }
}

// Does not extend OncePerRequestFilter so every invocation is counted.
final class CountingProbeFilter implements Filter {

    static final String KEY =
        CountingProbeFilter.class.getName() + ".count";

    @Override
    public void doFilter(ServletRequest request,
            ServletResponse response, FilterChain chain)
            throws IOException, ServletException {

        Integer previous = (Integer) request.getAttribute(KEY);
        int current = previous == null ? 1 : previous + 1;

        request.setAttribute(KEY, current);
        chain.doFilter(request, response);
    }
}

// This class is not declared as a separate @Bean;
// the FilterRegistrationBean above owns the container registration.
final class ContainerMarkerFilter implements Filter {

    @Override
    public void doFilter(ServletRequest request,
            ServletResponse response, FilterChain chain)
            throws IOException, ServletException {

        ((HttpServletResponse) response)
            .setHeader("X-Lab-Container", "hit");
        chain.doFilter(request, response);
    }
}

@RestController
class LabController {

    @GetMapping("/inspect")
    Map<String, Integer> inspect(HttpServletRequest request) {
        Object number = request.getAttribute(
            CountingProbeFilter.KEY);

        int calls = number instanceof Integer value ? value : 0;
        return Map.of("filterInvocations", calls);
    }

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/private")
    String privateEndpoint(Authentication authentication) {
        return "hello " + authentication.getName();
    }

    @GetMapping("/admin")
    String adminEndpoint() {
        return "admin OK";
    }
}
~~~

This is **one complete Java file inside the generated Spring Boot project**. The public class matches the filename; `CountingProbeFilter`, `ContainerMarkerFilter`, and `LabController` are package-private classes in the same package. Java 17 supports pattern matching for `instanceof`; Spring Boot 3 uses `jakarta.servlet`.

### 8.4. Why Does the Lab Use a Request Attribute Instead of a Global AtomicInteger?

The counter is stored via **`request.setAttribute`** to count filter invocations **within a single HTTP request**. Using a static variable or an `AtomicInteger` instance field on the Filter bean would cause concurrent requests to increment the same counter, muddying results.

Filter beans are singletons serving multiple threads; never store usernames, `Authentication`, or request-specific state in instance fields. A request attribute fits a temporary lab probe and does not become a session attribute.

### 8.5. Explaining the Profiles

**Safe:**

- `CountingProbeFilter` is a Spring bean.
- Disabled `FilterRegistrationBean` targets that exact `CountingProbeFilter` instance.
- Spring Boot does not add this instance to the Servlet Container `FilterChain`.
- `HttpSecurity.addFilterBefore(filter, AuthorizationFilter.class)` places it inside the security chain.
- `GET /inspect` sees `filterInvocations=1`.

**Double (intentionally broken):**

- `CountingProbeFilter` is still a Spring bean.
- No disabled `FilterRegistrationBean` exists.
- Spring Boot auto-registers the Filter bean with the Servlet Container.
- `HttpSecurity` also adds the same bean into `SecurityFilterChain`.
- `GET /inspect` sees `filterInvocations=2` in a standard embedded Servlet setup.

**`ContainerMarkerFilter`** always runs via container registration and adds `X-Lab-Container=hit`. It is a distinct instance from `CountingProbeFilter`, showing the container layer remains active under both profiles.

### 8.6. Why Choose AuthorizationFilter as the Anchor?

In this lesson, the filter only counts invocations for observation. Placing it right before `AuthorizationFilter` makes it run inside the security chain on both `permitAll` and authenticated requests, after most authentication mechanisms in this config.

For a real business filter enforcing permissions, determine its position relative to `ExceptionTranslationFilter` and the authentication mechanism. Never copy an anchor merely because an example used it; every requirement has its own trust boundary.

### 8.7. Predicting Order and Exceptions

In the `double` profile, where Boot's auto-registered Filter bean lands in the container chain can vary if custom filter orders/registrations exist. Yet on a normal `GET /inspect` passing through both layers to the Controller, the response reports how many times `doFilter` executed.

If a security filter **short-circuits early**, a container pass scheduled after the security bridge might not run; hence never assume every 401 response will carry a count of two. Use a `permitAll` endpoint first to diagnose duplicate registration.

## 9. Running the Lab and Observing Filter Execution Counts

### 9.1. Safe Profile: Exactly One Invocation

Run in the project directory with Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

PowerShell: **.\gradlew.bat bootRun**. Per `application.properties`, when no profile is active, default profile `safe` is used.

Call:

~~~bash
curl -i http://localhost:8080/inspect
curl -i http://localhost:8080/public
~~~

Expected primary output for `/inspect`:

~~~http
HTTP/1.1 200 OK
X-Lab-Container: hit
Content-Type: application/json

{"filterInvocations":1}
~~~

Actual headers may include `Date`, security headers, and others. The body shows the expected result for `GET /inspect` under the `safe` profile, not measured output captured here.

### 9.2. Double Profile: Intentionally Registered Twice

Stop the app before switching profiles, then run:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=double'
~~~

PowerShell: **.\gradlew.bat bootRun --args='--spring.profiles.active=double'**. With `double` active, the disabled-registration bean (scoped to `safe`) is not created.

Call:

~~~bash
curl -i http://localhost:8080/inspect
~~~

Expected response:

~~~http
HTTP/1.1 200 OK
X-Lab-Container: hit
Content-Type: application/json

{"filterInvocations":2}
~~~

If your result differs, inspect **Servlet Container filter registrations** and the security chain; never tweak Controller code to "force" the counter to two. The invocation count reflects whether Boot auto-registered the bean and whether the request traversed both spots.

**The `double` profile is strictly for isolated lab environments. Never enable it in production.**

### 9.3. Checking Authentication and Authorization Remain Unchanged

Under either profile, run:

~~~bash
curl -i http://localhost:8080/private
curl -i -u learner http://localhost:8080/private
curl -i -u learner http://localhost:8080/admin
curl -i -u admin http://localhost:8080/admin
~~~

Curl prompts for the password when given only a username with `-u`; use the demo passwords from source. In Windows PowerShell you may need **`curl.exe`** instead of the `curl` alias.

| Request | Expected Status | Meaning |
| --- | --- | --- |
| GET /inspect anonymous | 200 | Probe permitted for experiment |
| GET /public anonymous | 200 | `permitAll` still passes through chain |
| GET /private anonymous | 401 | Missing Authentication |
| GET /private learner, valid demo password | 200 | Authenticated |
| GET /admin learner, valid demo password | 403 | Missing `ROLE_ADMIN` |
| GET /admin admin, valid demo password | 200 | Has `ROLE_ADMIN` |

HTTP Basic uses Base64 rather than strong encryption; always use HTTPS/TLS over a network. Demo passwords are for isolated localhost only—never reuse them on any real account.

### 9.4. Observing a Header Does Not Prove Safety

`X-Lab-Container` only shows `ContainerMarkerFilter` ran. It **does not prove** `CountingProbeFilter` ran only once. The request-attribute counter verifies that aspect in the lab.

Conversely, behind proxies or different containers, outer layers may strip or add headers. Rely on controlled internal tests to verify registrations.

## 10. Integration Tests via the Embedded Servlet Container

Because the issue under study is **Servlet Container filter registration**, MockMvc alone may be insufficient: MockMvc tests Spring MVC/Security chains per config yet does not reproduce all embedded-server auto-registration behavior.

To prove the container path, use:

- **`@SpringBootTest(webEnvironment = RANDOM_PORT)`** to launch embedded Tomcat/Servlet Container on a random port.
- **`TestRestTemplate`** to send real HTTP requests.
- Two test classes with **`@ActiveProfiles("safe")`** and **`@ActiveProfiles("double")`**.
- Comparing the same `/inspect` endpoint and container header.

### 10.1. Test for the safe Profile

Create **src/test/java/com/example/filterplacement/SafeRegistrationTest.java**:

~~~java
package com.example.filterplacement;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("safe")
class SafeRegistrationTest {

    @Autowired
    TestRestTemplate rest;

    @Test
    void probeIsRegisteredOnlyWithinSecurityFilterChain() {
        ResponseEntity<Map> response =
            rest.getForEntity("/inspect", Map.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("hit", response.getHeaders()
            .getFirst("X-Lab-Container"));

        Number calls = (Number) response.getBody()
            .get("filterInvocations");
        assertEquals(1, calls.intValue());
    }

    @Test
    void authenticationAndAuthorizationStillWork() {
        assertEquals(HttpStatus.UNAUTHORIZED,
            rest.getForEntity("/private", String.class)
                .getStatusCode());

        ResponseEntity<String> authenticated =
            rest.withBasicAuth("learner", "local-learn-only")
                .getForEntity("/private", String.class);

        assertEquals(HttpStatus.OK,
            authenticated.getStatusCode());
        assertEquals("hello learner",
            authenticated.getBody());

        assertEquals(HttpStatus.FORBIDDEN,
            rest.withBasicAuth("learner", "local-learn-only")
                .getForEntity("/admin", String.class)
                .getStatusCode());

        assertEquals(HttpStatus.OK,
            rest.withBasicAuth("admin", "local-admin-only")
                .getForEntity("/admin", String.class)
                .getStatusCode());
    }
}
~~~

### 10.2. Test for the double Profile

Create **src/test/java/com/example/filterplacement/DoubleRegistrationTest.java**:

~~~java
package com.example.filterplacement;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("double")
class DoubleRegistrationTest {

    @Autowired
    TestRestTemplate rest;

    @Test
    void beanHasTwoRegistrationPathsInTheBrokenProfile() {
        ResponseEntity<Map> response =
            rest.getForEntity("/inspect", Map.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("hit", response.getHeaders()
            .getFirst("X-Lab-Container"));

        Number calls = (Number) response.getBody()
            .get("filterInvocations");
        assertEquals(2, calls.intValue());
    }
}
~~~

Both test files have matching class/filenames per Java rules and live in the same package as the application. For each profile, Spring Boot builds a separate `ApplicationContext`; tests send real HTTP requests through the embedded server.

Run:

~~~bash
./gradlew test
~~~

PowerShell: **.\gradlew.bat test**.

### 10.3. What Do These Tests Prove?

- **Safe:** the same `CountingProbeFilter` bean is invoked once on `GET /inspect`.
- **Double:** in the lab's embedded Servlet environment, the same bean is invoked twice because two registration paths exist.
- Both profiles still pass through the container-level marker filter.
- HTTP authentication and authorization rules still function (401/200/403 in `safe`).
- The difference lies not in Controller logic, solely in bean registration.

### 10.4. What Do These Tests Not Prove?

- They do not guarantee `ERROR`/`ASYNC` dispatcher types behave identically.
- They do not simulate proxies, service meshes, load balancers, or other container vendors.
- They do not prove every filter in a production app is registered only once.
- They do not prove every request sees exactly one invocation: a request can short-circuit before the filter, or undergo multiple valid dispatches.
- They do not prove the filter is multi-thread-safe just because the request-attribute counter is accurate.
- They do not thoroughly prove CSRF/session/logout/MFA/security headers: the demo only exposes GET endpoints and HTTP Basic.
- The tests were not executed on a machine within this text; results are **code-based expectations** and must be verified with a real build.

**Never assert only that `GET /public` returns 200**: both `safe` and `double` configs can return 200. Tests must check a signal that reflects differences in filter invocations.

## 11. How to Debug When a Custom Filter Runs Twice

An effective diagnostic workflow:

### Step 1 — Check Whether the Filter Is a Spring Bean

Check whether the class has `@Component`, scanned `@WebFilter`, or a `@Bean` factory method. Any Spring bean implementing `Filter` can be auto-registered by Boot Servlet.

Do not conflate a Filter being a bean with it being added to `HttpSecurity`. Those are two decisions in two separate subsystems.

### Step 2 — Find Where HttpSecurity Adds the Filter

Search for calls to:

~~~java
http.addFilterBefore(customFilter, SomeFilter.class);
http.addFilterAfter(customFilter, SomeFilter.class);
http.addFilterAt(customFilter, SomeFilter.class);
~~~

These are placeholder snippets with a hypothetical `SomeFilter`, not standalone programs. Whenever a filter is added here, verify whether that bean also has a container registration.

### Step 3 — List Servlet Filter Registrations

In a test environment, inspect `ServletContext.getFilterRegistrations()` or registration beans, filter names, URL mappings, dispatcher types, and orders.

A servlet registration may not use the exact Spring bean name. Inspect instances/configurations rather than grepping solely for a class name string.

### Step 4 — Print the List of Security Filters

Enable controlled debugging:

~~~properties
logging.level.org.springframework.security.web.DefaultSecurityFilterChain=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=DEBUG
~~~

Spring Security typically logs the filter list when building the chain at DEBUG level, depending on version. Check which `SecurityFilterChain` matches the request, whether your custom filter is present, and its order relative to auth/authorization filters.

**Never enable request/response body logging, Authorization/Cookie headers, or blanket TRACE in production just to locate filter order.**

### Step 5 — Distinguish Two Registrations from Two HTTP Requests

Browsers automatically send:

- `GET /favicon.ico`.
- `OPTIONS` CORS preflights.
- `GET` requests for CSS/JS assets.
- HTTP redirects to another URL.
- Duplicate requests from frontend retries.
- `ERROR` dispatches after exceptions.

Never see "two log lines close together" and assume the same HTTP request ran the filter twice. Attach a secret-free server-side request ID and verify counts in a request attribute or clearly scoped instrumentation.

### Step 6 — Compare safe and double Profiles

With a similar lab or integration test, toggle **only** disabling container registration. If invocation count drops from two to one, that is strong evidence of duplicate registration in that environment.

### Step 7 — Fix Ownership and Run Regression Tests

If the filter belongs strictly to the security chain, set `setEnabled(false)` on `FilterRegistrationBean` or stop declaring it as a Filter bean. Never patch around it with a static `alreadyCalled` flag, which mixes requests and users.

## 12. Trickier Pitfalls

### 12.1. Filter Bean Added to Two SecurityFilterChains

With multiple `SecurityFilterChain` beans, **`FilterChainProxy` selects only the first matching chain** in standard configurations. Referencing one Filter instance in two different chains does not mean both chains run for one request.

However, sharing the same instance can dangerously share mutable state, configuration, or markers. If the chains serve distinct roles, consider separate filter instances, enforce statelessness, and test matchers.

### 12.2. No SecurityFilterChain Matches

If a request matches no chain, security filters are not applied. Yet a Filter bean auto-registered on the container can still run on that URL. This creates the illusion that "my security filter ran on an unmatched URL", when in reality it was the **container-level registration**.

Verify first-match semantics and ensure an appropriate fallback `SecurityFilterChain`. Never treat a logging filter's execution as proof that a URL is protected by Spring Security.

### 12.3. permitAll Does Not Skip the Security Chain

A `permitAll` URL still passes through the selected chain's security filters. A custom filter can still execute on `/public`. If that filter blocks public requests via custom logic, **`permitAll` does not guarantee the request reaches the Controller**.

Conversely, `web.ignoring` or matching no chain can skip many security filters/headers. Never use ignoring just to "stop a filter from running" if doing so strips required protections.

### 12.4. OncePerRequestFilter and ERROR/ASYNC Dispatches

`OncePerRequestFilter` exposes extension points like `shouldNotFilterAsyncDispatch` and `shouldNotFilterErrorDispatch`. The name "once" does not guarantee a single run across all Servlet dispatches in every configuration.

An `ERROR` dispatch can have its own request lifecycle; never conclude duplicate registration solely because a filter ran on both `REQUEST` and `ERROR`.

### 12.5. Does FilterRegistrationBean.enabled=false Delete the Bean?

No. The bean remains alive in the Spring `ApplicationContext` and is injected into `SecurityFilterChain` as usual. Only container registration is suppressed.

That is why this option works cleanly when a filter needs services/repositories/mappers injected and must remain a bean.

### 12.6. Container Order and Spring Security Order Are Separate

Setting a lower `FilterRegistrationBean.order` affects position in the container chain. It does not move `AuthorizationFilter` ahead of `CsrfFilter` inside `FilterChainProxy`.

Similarly, `@Order` on a `SecurityFilterChain` bean controls which chain is evaluated first; it does not alter internal filter ordering within a chain.

### 12.7. Overly Broad Default Filter Registration

An auto-registered `@Component Filter` can match far more URLs than your intended chain's `securityMatcher`. If the filter enforces tenant checks assuming "it only runs after authentication", overly broad registration can cause 401/500 errors on public endpoints or health checks.

If it exists solely for security, keep the filter **inside the appropriate `SecurityFilterChain`**. If a container filter genuinely needs a narrow scope, configure URL patterns/dispatcher types explicitly.

### 12.8. Constructing Authentication from Untrusted Data

Never use a custom filter to mint an authenticated token with roles from unverified request headers. Every trusted `Authentication` must come from a properly designed provider/token verifier/SSO flow.

Wrong filter placement can make you read the wrong principal, yet "fixing" it by granting default roles is an authentication bypass.

### 12.9. Catching or Throwing Exceptions in the Wrong Place

A custom filter placed upstream of `ExceptionTranslationFilter` that throws `AccessDeniedException` can produce HTTP 500 instead of 403 if no handler covers it. A filter intending to use standard security handling must sit inside the wrapped region or use standard authorization APIs.

Never catch all `RuntimeException`s and return 401; that masks DB outages and programming bugs, impeding incident visibility.

### 12.10. Bean Lifecycle and Filter State Management

Filter beans are normally reused across many concurrent requests. Never hold `Authentication`, `HttpServletRequest`, `HttpSession`, or mutable request counters in instance fields.

If rate limiting is required, use a thread-safe and distributed-safe store/service; never use a plain field on a singleton Filter bean as system-wide security enforcement.

## 13. Replace Hand-Written Filters with Standard Mechanisms Whenever Possible

Before using `addFilterBefore`/`After`/`At`, check whether Spring Security already offers a DSL or hook for the goal:

| Requirement | Prefer |
| --- | --- |
| HTTP Basic | `httpBasic(...)` |
| Form login | `formLogin(...)` |
| CSRF | `csrf(...)` |
| CORS | `cors(...)` and `CorsConfigurationSource` |
| Security headers | `headers(...)` |
| URL authorization | `authorizeHttpRequests(...)` |
| Method authorization | `@PreAuthorize` / `AuthorizationManager` |
| OAuth2 Resource Server | `oauth2ResourceServer(...)` |
| Logout | `logout(...)` |
| Session management | `sessionManagement(...)`, `securityContext(...)` |
| Custom AuthenticationProvider | Configure appropriate provider/`AuthenticationManager` |
| Filter observability | Micrometer/observation integration where appropriate |

A standard mechanism does not cover every requirement, yet it typically handles `SecurityContext`, exception handling, filter ordering, and session lifecycles far more reliably than a filter written from scratch.

### 13.1. When a Custom Filter Is Genuinely Needed

A well-designed custom filter should have:

- A clear responsibility grounded in the threat model.
- Explicit `RequestMatcher`/route scope.
- An anchor point justified by upstream/downstream security events.
- No unverified user data trusted as authority.
- No logging of raw credentials/tokens.
- No duplicated side effects on retries/async/error dispatches.
- Clear registration ownership: container-only or security-only.
- Automated tests for 200/401/403, CSRF if applicable, sessions, and errors.
- Safe diagnostics that never leak Authorization/Cookies.
- Verification against other `SecurityFilterChain`s and fallback chains.

## 14. Incident Troubleshooting Checklist

When a custom filter appears to "run twice", ask in order:

1. Is the Filter annotated with `@Component` or declared as `@Bean`?
2. Did Boot create a Servlet Filter auto-registration for that bean?
3. Does a `FilterRegistrationBean` exist for this bean; is `enabled=true` or `false`?
4. Did anyone pass the same instance to `http.addFilterBefore/After/At`?
5. Is it a `OncePerRequestFilter` or a plain `Filter`? Could logging inside `doFilterInternal` hide a pass?
6. Do the two log lines belong to the same HTTP request or two different requests/dispatches?
7. Are both passes at the Servlet Container, or one container pass and one `SecurityFilterChain` pass?
8. Which chain is the filter in; are `@Order` and `securityMatcher` right?
9. Does the filter need a verified `Authentication`; does its current position guarantee it?
10. Is the filter placed before `ExceptionTranslationFilter`, breaking 401/403 mapping?
11. Does a built-in DSL replace the custom filter?
12. If a bean is required, can `FilterRegistrationBean.setEnabled(false)` be used?
13. If no bean is required, can the filter be instantiated directly inside `HttpSecurity`?
14. Was it tested on an embedded server with per-request IDs/counters?
15. Are `ERROR`/`ASYNC` dispatches, redirects, browser retries, or CORS preflights involved?
16. Is mutable state shared across users in session/context?
17. After fixing, do security headers, CSRF, authentication, and authorization still work properly?
18. Is any filter inadvertently running on routes outside `securityMatcher`?

## 15. Review Questions and Answers

**Question 1.** Why can a `@Component` Filter added via `HttpSecurity` be invoked twice?  
**Answer:** Boot can auto-register the Filter bean with the Servlet Container while `HttpSecurity` also adds the same bean to `SecurityFilterChain`.

**Question 2.** Does `FilterRegistrationBean.setEnabled(false)` delete the Spring bean?  
**Answer:** No. It only disables Servlet Container registration; the filter can still be injected and used in `HttpSecurity`.

**Question 3.** Which ordering do `addFilterBefore` and `addFilterAfter` belong to?  
**Answer:** Internal ordering of Spring Security filters inside `SecurityFilterChain`, not container registration order.

**Question 4.** Does `addFilterAt` always completely replace the existing filter?  
**Answer:** Do not rely on that. Javadoc notes multiple filters at the same position do not automatically overwrite one another and order can be undefined; duplicate configs may even be rejected. To replace an old filter, omit or disable the mechanism creating it.

**Question 5.** Should you annotate `BasicAuthenticationFilter` with `@Component`?  
**Answer:** No. Use the `httpBasic` DSL so Spring Security places it at the appropriate position.

**Question 6.** Why is `OncePerRequestFilter` not enough to fix duplicate registration?  
**Answer:** Its marker may make `doFilterInternal` execute once on some paths, yet both registrations remain and can diverge across dispatches/conditions.

**Question 7.** Why does the lab use a request attribute to count filter invocations?  
**Answer:** Because the counter belongs to one request and is not corrupted by concurrent requests.

**Question 8.** Should a filter needing a verified Principal be placed before or after authentication?  
**Answer:** After the appropriate authentication mechanism and before authorization in the real chain; check context and exception handling too.

**Question 9.** Is a filter placed after `BasicAuthenticationFilter` always called when the Basic password is wrong?  
**Answer:** No. The authentication filter can reject the request without calling the rest of the chain.

**Question 10.** Is a filter that does not depend on `SecurityContext` valid to run outside the security chain?  
**Answer:** Yes. It can be registered with a container-only `FilterRegistrationBean`, provided the same filter is not also added to `HttpSecurity`.

**Question 11.** Can a Filter bean run on URLs outside the intended `SecurityFilterChain`?  
**Answer:** Yes, if Boot auto-registers it on the Servlet Container with broad URL mappings.

**Question 12.** Does `permitAll` remove all security filters?  
**Answer:** No. It is an authorization rule; filters can still execute inside the selected chain.

**Question 13.** Does `@Order` on a `SecurityFilterChain` change the order between `CsrfFilter` and `AuthorizationFilter`?  
**Answer:** No. `@Order` controls chain selection; internal filter ordering is configured via `HttpSecurity`.

**Question 14.** Why not use only MockMvc to prove container auto-registration?  
**Answer:** MockMvc may not spin up the full embedded Servlet Container; `RANDOM_PORT` tests over real HTTP are more reliable for container registration paths.

**Question 15.** What else besides duplicate registration can yield `doFilter` count = 2?  
**Answer:** Dispatcher types like `ERROR`/`ASYNC`, internal forwards, multiple HTTP requests, retries, or repeated application calls.

**Question 16.** Should a tenant-checking filter read tenant ID from a header and trust it immediately?  
**Answer:** No. Tenant ID is untrusted input; it must be verified against the authenticated principal and real permissions.

**Question 17.** If an exception occurs upstream of `ExceptionTranslationFilter`, is 403 guaranteed?  
**Answer:** No. Standard handlers may not cover that exception; inspect placement and exception translation.

**Question 18.** How do you keep a custom Filter as a Spring bean while running it solely inside the security chain?  
**Answer:** `@Bean` filter + disabled `FilterRegistrationBean` + `HttpSecurity.addFilterBefore/After` at the right position.

## 16. Official References

- Spring Security — Servlet Architecture, Adding Filters, and Declaring Your Filter as a Bean: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — HttpSecurity API, addFilterBefore/addFilterAfter/addFilterAt: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/builders/HttpSecurity.html
- Spring Security — FilterChainProxy API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/FilterChainProxy.html
- Spring Security — Authorization HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — HTTP Basic Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Boot — Embedded Web Servers, Disable Registration of a Servlet or Filter: https://docs.spring.io/spring-boot/how-to/webserver.html
- Spring Boot — Spring Security Auto-configuration: https://docs.spring.io/spring-boot/reference/web/spring-security.html
- Spring Framework — OncePerRequestFilter API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- Spring Framework — DelegatingFilterProxy API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/DelegatingFilterProxy.html
