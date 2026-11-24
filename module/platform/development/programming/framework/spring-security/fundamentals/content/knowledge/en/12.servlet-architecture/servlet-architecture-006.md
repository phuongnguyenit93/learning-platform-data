# Relationship Between Security Filters and MVC HandlerInterceptor

> **Parent topic:** Servlet Architecture · **Scope:** Spring Security 6.x, Spring Framework MVC 6.x, Spring Boot 3.x, Java 17+, and the Jakarta Servlet API. This lesson clearly explains why **Spring Security operates at the Servlet Filter layer** whereas **`HandlerInterceptor` belongs to the Spring MVC layer**; the execution order when a request succeeds, when authentication/authorization fails, when an interceptor blocks a handler, and in `ERROR`/`ASYNC` dispatches. It includes a standalone Java 17 program demonstrating call order, a full-layered Spring Boot application, and MockMvc tests. Do not apply this Servlet diagram verbatim to Spring WebFlux.

## 1. Two Request-Processing Layers, Two Distinct Responsibilities

An HTTP request passes through multiple layers before reaching a `@RestController`. In a Spring Boot Servlet application with Spring Security, two extension points are frequently confused:

1. **Servlet Filters**, including Spring Security's filter chain: run inside the **Servlet container**, wrapping `DispatcherServlet`; can authenticate, protect against CSRF, manage session/security context, and reject requests before MVC even knows which handler would be invoked.
2. **MVC `HandlerInterceptor`**: applied by **Spring MVC's `HandlerMapping`/`DispatcherServlet`** to the selected `HandlerExecutionChain`; well suited for timing handler execution, recording request metadata, and cross-cutting concerns tied directly to MVC.

Core diagram:

~~~text
Client
  |
  v
Servlet container
  |
  +--> Container Filters (if present)
  |
  +--> DelegatingFilterProxy
         |
         v
      FilterChainProxy (springSecurityFilterChain)
         |
         +--> Selected SecurityFilterChain
                |
                +--> SecurityContextHolderFilter
                +--> CsrfFilter / CorsFilter / exploit protections
                +--> Authentication filters
                +--> AnonymousAuthenticationFilter
                +--> ExceptionTranslationFilter
                +--> AuthorizationFilter
                |
                v
           DispatcherServlet
                |
                +--> HandlerMapping resolves handler
                |
                +--> HandlerInterceptor.preHandle(...)
                |
                +--> HandlerAdapter invokes Controller
                |
                +--> HandlerInterceptor.postHandle(...)
                |
                +--> HandlerInterceptor.afterCompletion(...)
                |
                v
           HTTP response
  |
  +--> Filters run post-chain.doFilter(...) section
  |
  v
Client
~~~

This ordering is a **conceptual model**, not an exhaustive list of every filter in every application. A filter may not run depending on `SecurityFilterChain`, configuration, and dispatcher type. If a security filter rejects the request, execution can stop **before** `DispatcherServlet`, so neither the interceptor nor the controller runs.

**Quick rule of thumb:** *Servlet Filters sit outside MVC; HandlerInterceptors sit inside MVC*. Authentication and authorization at the application gate should use **Spring Security**, not be replaced by an ad-hoc header-checking interceptor.

## 2. Bottom-Up View: Filter and DispatcherServlet

### 2.1. `jakarta.servlet.Filter`

The Servlet container constructs a `FilterChain` according to URL/dispatcher registrations. A filter can execute logic before and after the next component:

~~~java
// Snippet inside a class implementing jakarta.servlet.Filter.
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain)
        throws IOException, ServletException {

    before(request);
    try {
        chain.doFilter(request, response);
    } finally {
        after(request);
    }
}
~~~

`before`/`after` in the snippet are user-defined methods, not Servlet APIs. The crucial point is that **`chain.doFilter` decides whether the request continues**. A filter can return a response directly without calling `chain`, in which case `DispatcherServlet`, `HandlerMapping`, and `HandlerInterceptor` are never invoked on that branch.

Servlet filters can run for:
- Requests handled by MVC.
- Another servlet in the same container, if the filter mapping covers it.
- Resource requests or matching dispatches.
- Requests blocked before reaching MVC.

However, a filter **does not automatically run for every request in the world**; it must be registered with the container with appropriate URL/dispatcher mappings. `OncePerRequestFilter` also has its own rules for async/error dispatches.

### 2.2. `DispatcherServlet`

`DispatcherServlet` is Spring MVC's front controller, receiving requests after upstream filters allow them through. It uses `HandlerMapping` to resolve a handler, such as:

~~~java
@RestController
class BookController {

    @GetMapping("/books/{id}")
    String getBook(@PathVariable long id) {
        return "book:" + id;
    }
}
~~~

This is an illustrative MVC snippet; no security step is shown yet. Only once MVC finds a `HandlerExecutionChain` can it run any `HandlerInterceptor`s applicable to that handler. If another Servlet handles the request, MVC interceptors will not automatically intervene.

### 2.3. Not Every Request Reaches HandlerInterceptor

Common branches where an MVC interceptor **may not run**:

- Spring Security rejects an invalid username/password, invalid token, or missing role.
- `CsrfFilter` rejects a POST lacking a valid CSRF token.
- `CorsFilter` handles an OPTIONS preflight before reaching the Controller.
- An upstream Servlet Filter rejects due to rate limit, request size, or headers.
- The request is handled by another servlet, or MVC `HandlerMapping` finds no matching handler.
- The MVC interceptor does not match the path, is excluded, or is not registered on the active HandlerMapping.

**Note on static resources:** In a Spring MVC application, static resources can be served by `ResourceHttpRequestHandler` via HandlerMapping. Therefore, never claim "all static resources always skip interceptors". Behavior depends on how resource handlers, filter/interceptor mappings, and CDN/proxy infrastructure are configured.

## 3. How Does Spring Security Enter the Servlet FilterChain?

Spring Security normally does not register `CsrfFilter`, `AuthorizationFilter`, and authentication filters individually with the container. Instead:

~~~text
Servlet container
   |
   v
DelegatingFilterProxy
   |
   +--> Spring Bean: springSecurityFilterChain
             |
             v
        FilterChainProxy
             |
             +--> SecurityFilterChain #1, matcher /api/**
             +--> SecurityFilterChain #2, remaining matcher
             |
             v
       Filters in the first matching chain
             |
             v
        DispatcherServlet (if not blocked)
~~~

### 3.1. `DelegatingFilterProxy`

`DelegatingFilterProxy` bridges the Servlet container and a Spring-managed bean. The typical target bean is `springSecurityFilterChain`, backed by `FilterChainProxy`. This enables Spring Security to use Spring's dependency injection, lifecycle, and configuration.

Do not confuse:
- **Servlet container filter chain**: assembled by the container.
- **Spring Security filter chain**: selected by `FilterChainProxy` from the list of `SecurityFilterChain`s.
- **MVC interceptor chain**: returned by Spring MVC `HandlerMapping` alongside the handler.

These three chains relate to each other, yet are not the same list of filters/interceptors.

### 3.2. `FilterChainProxy` and Multiple SecurityFilterChains

If configured as:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a
            .anyRequest().authenticated());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(a -> a
        .anyRequest().denyAll());
    return http.build();
}
~~~

This is a **snippet** without an authentication mechanism, so it is not a complete application config. It highlights that `FilterChainProxy` **selects the first chain matching the request**, rather than combining filters from every chain.

- `/api/books` matches the API chain first.
- `/books` matches the fallback chain.
- If an app has only a `securityMatcher("/api/**")` chain and no fallback, other URLs **can fall outside Spring Security's protection**.

MVC interceptors are registered per HandlerMapping and are unaware of which security chain a request matched. Hence never use "having an MVC interceptor" to guarantee every URL enforces security policies.

### 3.3. What Do Security Filters Do Before MVC?

A typical flow includes:
- `SecurityContextHolderFilter` loads/prepares context for the request.
- CORS/CSRF and exploit protections inspect/handle the request per configuration.
- Authentication filters (HTTP Basic, form login, Bearer token, etc.) extract credentials.
- `AuthenticationManager`/providers verify identity.
- `AnonymousAuthenticationFilter` may populate an anonymous token.
- `ExceptionTranslationFilter` translates certain security exceptions into HTTP responses.
- `AuthorizationFilter` enforces `.permitAll()`, `.authenticated()`, `.hasRole()`, etc.
- Only after passing does the chain forward the request to MVC.

**`HandlerInterceptor.preHandle()` is not where authentication begins.** By the time preHandle runs, the security framework has usually already populated SecurityContext and authenticated/authorized the request.

## 4. HandlerInterceptor Belongs to Spring MVC

The `org.springframework.web.servlet.HandlerInterceptor` interface has three callbacks:

~~~java
public interface HandlerInterceptor {

    default boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) throws Exception {
        return true;
    }

    default void postHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            ModelAndView modelAndView) throws Exception {
    }

    default void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception ex) throws Exception {
    }
}
~~~

Above is an **abbreviated signature for study**, not a standalone file; exact interfaces/overrides depend on version. `HttpServletRequest` and `HttpServletResponse` come from **`jakarta.servlet.http`** in Spring Framework 6, not `javax.servlet.http` from legacy stacks.

### 4.1. preHandle()

`preHandle` is invoked **before the handler** once MVC has resolved a handler. It returns:

- `true`: proceed to the next interceptor or invoke the handler.
- `false`: skip the rest of `HandlerExecutionChain`; normally the interceptor handles the response itself or stopped intentionally.

An appropriate MVC-focused example:

~~~java
@Override
public boolean preHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) {

    request.setAttribute(
        "mvc.startedAt", System.nanoTime()
    );
    return true;
}
~~~

This measures when MVC handler processing began; it does not verify passwords or tokens.

### 4.2. postHandle()

`postHandle` runs when the handler succeeds along a compatible MVC path. It can inspect `ModelAndView` and adjust the model/view in traditional web MVC.

~~~java
@Override
public void postHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        ModelAndView modelAndView) {
    // Metadata attached to an MVC handler that ran.
}
~~~

**Be careful with REST:** For `@ResponseBody` or `ResponseEntity`, the response may already have been serialized/committed inside `HandlerAdapter` **before** `postHandle`. Thus `postHandle` is often **too late** to reliably add headers or alter the response body. Use `ResponseBodyAdvice`, a servlet filter, or explicit response design when modifying response payloads.

### 4.3. afterCompletion()

`afterCompletion` runs once MVC finishes processing the request in a normal synchronous lifecycle, and receives any thrown exception. It fits timing, cleaning up MVC-scoped temporary data, or recording metrics.

~~~java
@Override
public void afterCompletion(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        Exception ex) {

    Object started = request.getAttribute("mvc.startedAt");
    // Calculate elapsed time if started is valid.
}
~~~

**Never assume afterCompletion runs on every branch.** The callback applies only to interceptors whose `preHandle` completed successfully (returning true) in the execution chain. If an interceptor itself returns `false` from `preHandle`, it **does not** receive `afterCompletion` for that call; earlier interceptors that returned true still receive cleanup callbacks. With async requests, callbacks behave differently (covered below).

### 4.4. How Are Multiple Interceptors Ordered?

With two interceptors A, B and a controller:

~~~text
A.preHandle
B.preHandle
Controller
B.postHandle
A.postHandle
B.afterCompletion
A.afterCompletion
~~~

`preHandle` runs in registration order, while `postHandle`/`afterCompletion` run in reverse order within an execution chain. If `B.preHandle` returns false, neither Controller nor `postHandle` runs; only `A.afterCompletion` runs for the interceptor that succeeded.

Spring Security filters wrap around all of those callbacks. When a filter has code before/after `chain.doFilter`, it encloses the entire synchronous MVC lifecycle:

~~~text
Security Filter BEFORE
  A.pre
    B.pre
      Controller
    B.post
  A.post
    B.after
  A.after
Security Filter AFTER
~~~

This diagram illustrates order conceptually; exact filter and callback order varies on async, error/forward dispatches, or blocked responses.

## 5. Direct Comparison: Filter vs. HandlerInterceptor

| Criterion | Servlet Filter / Spring Security Filter | MVC HandlerInterceptor |
| --- | --- | --- |
| Layer | Servlet container, before/wrapping the servlet | Spring MVC HandlerExecutionChain |
| Knows `@GetMapping` handler? | Does not inherently know the selected handler | Receives `Object handler`, often a `HandlerMethod` |
| Can block before MVC? | **Yes** | No, only runs once inside MVC |
| Scope | By filter registration, SecurityFilterChain matcher, and dispatcher type | By HandlerMapping/InterceptorRegistry/path patterns |
| Chain mechanism | `doFilter` / `chain.doFilter` | `preHandle`, `postHandle`, `afterCompletion` |
| Credential authentication | Security filters/providers | Should not replace framework mechanisms |
| URL authorization | `AuthorizationFilter`/`AuthorizationManager` | Should not be the primary barrier |
| CSRF, CORS, SecurityContext | Dedicated filters and framework integrations | Unsuitable as a replacement layer |
| MVC handler metrics | Can record request-level metrics | Very well suited for handler-level metadata |
| Requests rejected by security | Can observe or handle in security/filter layer depending on placement | **Normally does not run** |
| Static resources/other servlets | Can cover via registration | Only when handled by MVC HandlerMapping |
| Async/error handling | Per Servlet dispatcher + filter rules | Per MVC async/interceptor lifecycle |
| Adding headers | Filter at the right time before response commit | `postHandle` may be too late for REST |

**Filters are not always "better" than Interceptors.** They solve different problems. For tracking controller handler names, an interceptor is purpose-built. For authentication and authorization, Spring Security's filter chain and method security are specifically designed with broader coverage and earlier execution.

## 6. Why Shouldn't You Perform Authentication in a HandlerInterceptor?

A common anti-pattern:

~~~java
// DO NOT use as the application's primary authentication layer.
@Override
public boolean preHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) {

    String apiKey = request.getHeader("X-API-Key");

    if (!"hard-coded-secret".equals(apiKey)) {
        response.setStatus(401);
        return false;
    }
    return true;
}
~~~

This snippet has numerous flaws:

1. The interceptor runs only for handlers covered by MVC mappings; requests handled by another servlet or unmatched paths can bypass it.
2. A hard-coded secret has no key rotation, replay protection, scopes, issuer, expiration, or auditing.
3. It fails to integrate properly with Spring Security's `AuthenticationManager`, `SecurityContextHolder`, and error handling.
4. If path patterns between security endpoints and MVC interceptors diverge, a new route can slip through.
5. CORS preflight, CSRF, and authentication failures can happen before the interceptor.
6. Adding an interceptor does nothing to protect `@Service`, `@Scheduled`, or code invoked outside MVC.

Spring Framework itself warns that **MVC interceptors are not an ideal security layer**, because path matching in interceptors can diverge from controller annotation mappings. Use Spring Security or integrated Servlet-filter security mechanisms instead.

### 6.1. Can HandlerInterceptor Read SecurityContext?

**Yes.** Once a request passes the security filters and enters MVC:

~~~java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
~~~

An interceptor can read `getName()`, authorities, or principal type for bounded logging/tracing. However:

- `auth == null` can occur depending on configuration or execution point.
- `AnonymousAuthenticationToken` can report `isAuthenticated()==true`.
- Never log full Authentication objects, credentials, or JWTs.
- `getAuthorities()` may be a stale snapshot; do not replace role/ownership checks at the business layer.
- Simply reading context does not make the interceptor an authentication provider.

### 6.2. What If You Need Resource-Level Permissions?

Use Spring Security URL rules combined with **method security** and domain authorization. For example:

~~~java
// Snippet: requires @EnableMethodSecurity and a real documentPolicy bean.
@PreAuthorize(
    "@documentPolicy.canRead(authentication, #documentId)"
)
public DocumentDto loadDocument(long documentId) {
    return repository.load(documentId);
}
~~~

The snippet above **does not compile standalone**: `DocumentDto`, `repository`, and `documentPolicy` must be implemented by the project. The core idea is checking a trusted `Authentication`, resource ID, owner/tenant, and current permissions rather than arbitrary headers or static checks in an MVC interceptor.

### 6.3. Security Filters and MethodInterceptors Are Not MVC HandlerInterceptors

Spring Security has classes like `AuthorizationManagerBeforeMethodInterceptor`. That interceptor serves **Spring Method Security/AOP**, not `org.springframework.web.servlet.HandlerInterceptor`. Similar names, different layers. `@PreAuthorize` on a service can protect a method even when the caller did not come through an MVC controller, provided method security is enabled and calls go through the appropriate proxy.

## 7. When a Request Fails Before MVC: 401, 403, and No preHandle

Suppose an endpoint `/admin/panel` requires `ROLE_ADMIN`:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
~~~

With a Spring Security chain using HTTP Basic:

| Request | Reaches MVC? | Common Outcome |
| --- | --- | --- |
| Anonymous `GET /admin/panel` | No | `401` from Basic AuthenticationEntryPoint |
| Authenticated Alice, only `ROLE_USER` | No | `403` from authorization |
| Admin with `ROLE_ADMIN` | Yes | Controller runs, interceptors run |
| POST missing valid CSRF when CSRF is on | Typically no | `403` from CSRF, even for admin |
| Public `GET /public/ping` | Yes | `200`, interceptors can run |
| `OPTIONS` preflight handled early by CORS | Likely no | Status depends on CORS filter config |

**Simply asserting `preHandle()` did not run is not enough to identify why.** You must identify which filter returned the response: CSRF, authentication, authorization, CORS, a custom filter, or an upstream proxy.

### 7.1. 401 vs. 403

- `401 Unauthorized`: the request lacks valid credentials or requires authentication; Basic typically returns `WWW-Authenticate`.
- `403 Forbidden`: the request is authenticated yet lacks authority, or was rejected by another protection such as CSRF.
- With form login, missing authentication can return a `302` redirect instead of 401.
- With custom entry points/AccessDeniedHandlers, body/status can differ.

`HandlerInterceptor` does not execute after security-layer rejections by default. To observe **all** cases, use logging in security filters/authorization events or properly scoped early request-level instrumentation rather than logging solely in preHandle.

## 8. Standalone Java 17 Program: Why "Before–After" Nests

To see the filter and interceptor call stack without Spring, create `CallOrderLab.java`:

~~~java
public class CallOrderLab {

    public static void main(String[] args) {
        servletFilter(() ->
            mvcInterceptor(() ->
                controller()
            )
        );
    }

    static void servletFilter(Runnable next) {
        System.out.println("filter.before");
        try {
            next.run();
        } finally {
            System.out.println("filter.after");
        }
    }

    static void mvcInterceptor(Runnable handler) {
        System.out.println("mvc.pre");
        try {
            handler.run();
            System.out.println("mvc.post");
        } finally {
            System.out.println("mvc.after");
        }
    }

    static void controller() {
        System.out.println("controller");
    }
}
~~~

Run command:

~~~bash
javac CallOrderLab.java
java CallOrderLab
~~~

**Exact stdout:**

~~~text
filter.before
mvc.pre
controller
mvc.post
mvc.after
filter.after
~~~

This is a **plain Java model** of nested calls, not the actual source code of Spring Security or `HandlerExecutionChain`. It does not yet simulate `preHandle(false)`, error handling, or async dispatches. The Spring Boot section below uses real `OncePerRequestFilter` and `HandlerInterceptor` instances to verify actual ordering.

## 9. Spring Boot 3 Application: Security Filter and MVC Interceptor Running Together

Goals of the demo:

1. Spring Security authenticates via HTTP Basic with two sample accounts: Alice (`ROLE_USER`) and admin (`ROLE_ADMIN`).
2. `AuthorizationFilter` validates the route before MVC is allowed to handle it.
3. A **trace-only custom filter** is attached **after `AuthorizationFilter`** inside `SecurityFilterChain`.
4. An MVC `TraceInterceptor` records the order of `preHandle`, `postHandle`, and `afterCompletion`.
5. An MVC `BlockInterceptor` returns `false` from `preHandle`, halting a demo controller without **pretending to be a security layer**.
6. The controller records a marker in a request attribute so tests can cross-check callbacks.
7. MockMvc proves successful requests pass through both filter and interceptor; unauthorized requests are rejected by security before the interceptor runs; and POSTs missing CSRF are blocked before MVC.

**Demo limitations:** Traces synchronous MVC methods only. Do not rely on this trace filter to capture every 401/403 or for production logging. Do not build a custom authentication filter, do not disable CSRF, and do not put real credentials in code.

### 9.1. Dependencies and File Structure

Create a Spring Boot 3.x (Spring Framework 6.x, Spring Security 6.x), Java 17+ project with Gradle Wrapper/plugin configured. Add dependencies to `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

These are only the dependencies, **not a complete `build.gradle`**. Files:

~~~text
src/main/java/com/example/mvcfilter/
  MvcFilterApplication.java
  SecurityConfig.java
  TraceEvents.java
  RequestTraceFilter.java
  TraceInterceptor.java
  BlockInterceptor.java
  MvcConfig.java
  DemoController.java

src/test/java/com/example/mvcfilter/
  FilterAndInterceptorTest.java
~~~

### 9.2. MvcFilterApplication.java

~~~java
package com.example.mvcfilter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcFilterApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcFilterApplication.class, args);
    }
}
~~~

### 9.3. TraceEvents.java — Per-Request Trace Storage

~~~java
package com.example.mvcfilter;

import java.util.ArrayList;
import java.util.List;

import jakarta.servlet.http.HttpServletRequest;

public final class TraceEvents {

    public static final String KEY =
        TraceEvents.class.getName() + ".events";

    public static final String MVC_PRINCIPAL =
        TraceEvents.class.getName() + ".mvcPrincipal";

    private TraceEvents() {}

    @SuppressWarnings("unchecked")
    public static List<String> events(
            HttpServletRequest request) {

        Object existing = request.getAttribute(KEY);

        if (existing instanceof List<?>) {
            return (List<String>) existing;
        }

        List<String> created = new ArrayList<>();
        request.setAttribute(KEY, created);
        return created;
    }

    public static void add(
            HttpServletRequest request, String event) {
        events(request).add(event);
    }
}
~~~

All traces live inside a **request attribute**, never in a shared static mutable list. `KEY` is an attribute name, not a credential. For synchronous demos, `ArrayList` suffices. If turning this into async/concurrent instrumentation, you need a thread-safe structure or separate event sink and must handle dispatcher semantics.

### 9.4. RequestTraceFilter.java — Diagnostic Filter Only

~~~java
package com.example.mvcfilter;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public class RequestTraceFilter
        extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        TraceEvents.add(
            request, "security.filter.before"
        );

        try {
            chain.doFilter(request, response);
        } finally {
            TraceEvents.add(
                request, "security.filter.after"
            );
        }
    }
}
~~~

`OncePerRequestFilter` prevents certain duplicate executions within a dispatch per the framework contract. Yet do not interpret its name as **strictly once across the entire logical HTTP request including every `ASYNC`/`ERROR` dispatch**; check hooks such as `shouldNotFilterAsyncDispatch` and `shouldNotFilterErrorDispatch` in practice.

**Do not annotate this filter class with `@Component`**, because in this demo we add **one instance directly to the Spring Security chain**. If you both register it as a container `Filter` bean and call `.addFilterAfter` on `HttpSecurity`, the filter risks being registered/invoked twice or at two different order positions.

### 9.5. TraceInterceptor.java — MVC Callbacks

~~~java
package com.example.mvcfilter;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.lang.Nullable;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.ModelAndView;

public class TraceInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        TraceEvents.add(request, "mvc.pre");

        Authentication authentication =
            SecurityContextHolder.getContext()
                .getAuthentication();

        request.setAttribute(
            TraceEvents.MVC_PRINCIPAL,
            authentication == null
                ? "none"
                : authentication.getName()
        );

        return true;
    }

    @Override
    public void postHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            @Nullable ModelAndView modelAndView) {

        TraceEvents.add(request, "mvc.post");
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception exception) {

        TraceEvents.add(request, "mvc.after");
    }
}
~~~

`@Nullable` in the import merely documents that `ModelAndView` may be null and is **not required to compile**; in Spring Framework 6.x, omitting the annotation/import leaves behavior unchanged. This interceptor makes no authorization decisions; it only logs trace events and the principal name populated by Spring Security.

**Never use raw `authentication.isAuthenticated()` as a custom security check**, because an anonymous token can have that flag set to true. Spring Security's `.authenticated()` rule distinguishes anonymous tokens through framework mechanisms.

### 9.6. BlockInterceptor.java — Demonstrating preHandle(false)

~~~java
package com.example.mvcfilter;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.servlet.HandlerInterceptor;

public class BlockInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) throws Exception {

        TraceEvents.add(request, "mvc.block");
        response.setStatus(418);
        response.getWriter().write("blocked-by-mvc");
        return false;
    }
}
~~~

`418` here is an **intentional demo status to distinguish an MVC stop from a security error**, not a status recommended for production authorization. The interceptor only stops the corresponding MVC handler method. It is **not an authentication mechanism**.

### 9.7. MvcConfig.java — Registering MVC Interceptors at the Right Layer

~~~java
package com.example.mvcfilter;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcConfig implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {

        registry.addInterceptor(new TraceInterceptor())
            .addPathPatterns("/**");

        registry.addInterceptor(new BlockInterceptor())
            .addPathPatterns("/public/blocked");
    }
}
~~~

`TraceInterceptor` is registered first, so on `/public/blocked` it returns `true` from preHandle, and then `BlockInterceptor` returns `false`. MVC invokes neither the controller nor `postHandle`, yet still invokes `TraceInterceptor.afterCompletion` because that interceptor succeeded in preHandle.

This is MVC interceptor order, **not position inside Spring Security's `FilterChainProxy`**. `InterceptorRegistry` path patterns do not become `RequestMatcher`s in the security DSL.

### 9.8. SecurityConfig.java — Authentication/Authorization Happens Before MVC

~~~java
package com.example.mvcfilter;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {

        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/user/profile")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/admin/panel")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/admin/rebuild")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .addFilterAfter(
                new RequestTraceFilter(),
                AuthorizationFilter.class
            );

        return http.build();
    }
}
~~~

Reading each point carefully:

- HTTP Basic verifies credentials on every request in this stateless example; `PasswordEncoder` uses BCrypt.
- `/public/**` permits anonymous access. The filter chain still executes with `permitAll`; `web.ignoring()` is not used.
- `/user/profile` requires an authenticated user.
- `/admin/panel` and `/admin/rebuild` require `ROLE_ADMIN`.
- `anyRequest().denyAll()` blocks unlisted endpoints/methods.
- `CsrfFilter` **remains enabled** by default. Because POST `/admin/rebuild` is a state-changing request, tests must supply a CSRF token.
- `RequestTraceFilter` is attached **after `AuthorizationFilter`**, meaning **only requests passing authorization** reach this trace filter. Therefore 401/403 rejections from earlier security filters **will not necessarily emit** trace events.
- Inside Spring Security, authentication/CSRF/authorization filters have their own ordering. `.addFilterAfter` picks an insertion point **relative to a filter class**, not "after all Servlet container Filters".

**Instrumentation lesson:** If you want to log **401/403 responses too** or measure full request latency, place instrumentation earlier or use the right tool—such as a Servlet container filter or security-specific events—rather than relying solely on a filter after `AuthorizationFilter`.

### 9.9. DemoController.java

~~~java
package com.example.mvcfilter;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public String ping(HttpServletRequest request) {
        TraceEvents.add(request, "controller");
        return "pong";
    }

    @GetMapping("/public/blocked")
    public String blocked(HttpServletRequest request) {
        TraceEvents.add(request, "controller");
        return "should-not-run";
    }

    @GetMapping("/user/profile")
    public String profile(
            HttpServletRequest request,
            Authentication authentication) {

        TraceEvents.add(request, "controller");
        return "user:" + authentication.getName();
    }

    @GetMapping("/admin/panel")
    public String panel(HttpServletRequest request) {
        TraceEvents.add(request, "controller");
        return "admin-panel";
    }

    @PostMapping("/admin/rebuild")
    public String rebuild(HttpServletRequest request) {
        TraceEvents.add(request, "controller");
        return "rebuild-accepted";
    }
}
~~~

The controller handles business logic after `SecurityFilterChain` permits the request. `Authentication` injected by Spring MVC on protected endpoints is used only for the username, **never passwords/secrets**. The code merely records the string `"controller"` into a request attribute to observe call order.

### 9.10. Running and Testing with curl

From the root directory with Gradle Wrapper:

~~~bash
./gradlew bootRun
# Windows:
gradlew.bat bootRun
~~~

Test on localhost:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/public/blocked
curl -i http://localhost:8080/user/profile
curl -i -u alice:alice123 http://localhost:8080/user/profile
curl -i -u alice:alice123 http://localhost:8080/admin/panel
curl -i -u admin:admin123 http://localhost:8080/admin/panel
curl -i -u admin:admin123 -X POST http://localhost:8080/admin/rebuild
~~~

Expected outcomes:

| Request | HTTP status | Body / Meaning |
| --- | --- | --- |
| GET `/public/ping`, anonymous | 200 | `pong`, MVC ran |
| GET `/public/blocked`, anonymous | 418 | `blocked-by-mvc`, controller did not run |
| GET `/user/profile`, anonymous | 401 | Security requires Basic auth before MVC |
| GET `/user/profile`, Basic Alice | 200 | `user:alice` |
| GET `/admin/panel`, Basic Alice | 403 | Alice lacks `ROLE_ADMIN`; interceptor did not run |
| GET `/admin/panel`, Basic admin | 200 | `admin-panel` |
| POST `/admin/rebuild`, Basic admin, **no CSRF token** | 403 | `CsrfFilter` blocked it, not missing `ROLE_ADMIN` |

**Do not disable CSRF just so POST "returns 200".** With browser/session authentication, CSRF is critical protection; even this Basic demo keeps CSRF enabled to illustrate filter-level denial clearly. The next test uses `.with(csrf())` to construct a valid POST.

**Never use `curl -u` with real passwords on shared machines**, as command history/process arguments can expose credentials. Sample code is for localhost; use TLS and proper secret handling in production.

## 10. MockMvc Tests: Proving Order and Where Requests Are Blocked

Create `src/test/java/com/example/mvcfilter/FilterAndInterceptorTest.java`:

~~~java
package com.example.mvcfilter;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FilterAndInterceptorTest {

    @Autowired
    MockMvc mvc;

    private List<String> trace(MvcResult result) {
        Object attribute =
            result.getRequest().getAttribute(TraceEvents.KEY);

        if (!(attribute instanceof List<?> list)) {
            return List.of();
        }
        return list.stream()
            .map(String::valueOf)
            .toList();
    }

    private List<String> normalOrder() {
        return List.of(
            "security.filter.before",
            "mvc.pre",
            "controller",
            "mvc.post",
            "mvc.after",
            "security.filter.after"
        );
    }

    @Test
    void successfulMvcRequestRunsFilterAroundInterceptor()
            throws Exception {

        MvcResult result = mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"))
            .andReturn();

        assertEquals(normalOrder(), trace(result));
    }

    @Test
    void authenticatedRequestRunsMvcWithTrustedPrincipal()
            throws Exception {

        MvcResult result = mvc.perform(get("/user/profile")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(content().string("user:alice"))
            .andReturn();

        assertEquals(normalOrder(), trace(result));
        assertEquals(
            "alice",
            result.getRequest()
                .getAttribute(TraceEvents.MVC_PRINCIPAL)
        );
    }

    @Test
    void anonymousIsRejectedBeforeMvcInterceptor()
            throws Exception {

        MvcResult result = mvc.perform(get("/user/profile"))
            .andExpect(status().isUnauthorized())
            .andReturn();

        assertNull(
            result.getRequest().getAttribute(TraceEvents.KEY)
        );
    }

    @Test
    void insufficientRoleIsRejectedBeforeMvcInterceptor()
            throws Exception {

        MvcResult result = mvc.perform(get("/admin/panel")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden())
            .andReturn();

        assertNull(
            result.getRequest().getAttribute(TraceEvents.KEY)
        );
    }

    @Test
    void adminRoleAllowsControllerAndMvcCallbacks()
            throws Exception {

        MvcResult result = mvc.perform(get("/admin/panel")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-panel"))
            .andReturn();

        assertEquals(normalOrder(), trace(result));
        assertEquals(
            "admin",
            result.getRequest()
                .getAttribute(TraceEvents.MVC_PRINCIPAL)
        );
    }

    @Test
    void preHandleFalseStopsControllerButOuterFilterFinishes()
            throws Exception {

        MvcResult result = mvc.perform(get("/public/blocked"))
            .andExpect(status().is(418))
            .andExpect(content().string("blocked-by-mvc"))
            .andReturn();

        assertEquals(
            List.of(
                "security.filter.before",
                "mvc.pre",
                "mvc.block",
                "mvc.after",
                "security.filter.after"
            ),
            trace(result)
        );
    }

    @Test
    void csrfRejectionHappensBeforeMvcEvenForAdmin()
            throws Exception {

        MvcResult result = mvc.perform(post("/admin/rebuild")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isForbidden())
            .andReturn();

        assertNull(
            result.getRequest().getAttribute(TraceEvents.KEY)
        );
    }

    @Test
    void validCsrfAndAdminRolePermitPost()
            throws Exception {

        MvcResult result = mvc.perform(post("/admin/rebuild")
                .with(httpBasic("admin", "admin123"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("rebuild-accepted"))
            .andReturn();

        assertEquals(normalOrder(), trace(result));
    }
}
~~~

Run:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

### 10.1. Reading the Test `successfulMvcRequestRunsFilterAroundInterceptor`

Six expected events:

~~~text
security.filter.before
mvc.pre
controller
mvc.post
mvc.after
security.filter.after
~~~

This is the **expected synchronous callback order** for a request permitted by security, matched by `HandlerMapping`, and free of exceptions/async dispatches. The filter-after entry comes last because the filter calls `chain.doFilter` and then runs `finally`.

### 10.2. What Do the 401/403 Tests Prove?

`anonymousIsRejectedBeforeMvcInterceptor` and `insufficientRoleIsRejectedBeforeMvcInterceptor` assert `TraceEvents.KEY == null`.

In this **demo configuration**, the custom `RequestTraceFilter` sits after `AuthorizationFilter`, and MVC `TraceInterceptor` runs only when MVC handles the request. Therefore:
- When the authentication entry point returns 401 or `AuthorizationFilter` denies with 403, no events are recorded.
- Never infer that **no Servlet Filter ran**! Several earlier security filters executed to reach that decision.
- Placing the custom filter at another position produces a different trace.

### 10.3. preHandle(false) and afterCompletion

`TraceInterceptor` precedes `BlockInterceptor`. Trace preHandle returns true; Block preHandle returns false. The controller **does not run**, neither `postHandle` runs; Trace `afterCompletion` still runs, and the filter's `finally` still runs. That is why the test expects neither `"controller"` nor `"mvc.post"` on the blocked branch.

**`BlockInterceptor` itself does not receive `afterCompletion`** on the `preHandle=false` branch; if the blocking interceptor allocated resources in its own `preHandle`, it must clean them up before returning false.

### 10.4. POST Missing CSRF vs. Missing Role

`csrfRejectionHappensBeforeMvcEvenForAdmin` uses valid admin credentials without a CSRF token; because default CSRF protection is enabled for unsafe methods, the request gets 403. `validCsrfAndAdminRolePermitPost` adds `.with(csrf())` for a valid request; only then do all callbacks run in order.

These two tests help distinguish:
- Authentication already succeeded.
- Authorization would permit `ROLE_ADMIN`.
- Yet **CSRF protection** is a separate check at the filter layer that can reject before MVC.

**The results above are expected assertions based on the sample code, not a report of a Gradle run in this environment.** Different Spring Boot/Security versions, filter dispatcher registrations, or custom exception handling may require adjusting the tests.

## 11. When Do preHandle, postHandle, and afterCompletion NOT Run?

### 11.1. preHandle Does Not Run

Common reasons:
- A security filter rejected the request.
- CORS preflight was handled before `DispatcherServlet`.
- Another Servlet handled the request.
- MVC `HandlerMapping` found no handler matching the interceptor, or the path was excluded.
- An earlier interceptor halted the MVC request.
- An upstream filter generated the response before MVC.

Do not jump to "interceptor registration is broken" if the request returned 401 upstream.

### 11.2. postHandle Does Not Run

Possible reasons:
- An interceptor returned false in `preHandle`.
- The controller threw an exception and control entered error resolution.
- MVC async processing started and handles callbacks differently on the initial dispatch.
- Framework conditions or an already-completed response ended early.

Even when `postHandle` runs for REST, the response body may already be written. Do not rely on `postHandle` as the sole place to edit `@ResponseBody` JSON.

### 11.3. afterCompletion Does Not Run on Interceptors Whose preHandle Did Not Succeed

`HandlerExecutionChain` invokes cleanup callbacks only for interceptors that completed `preHandle` successfully. When an interceptor returns false, MVC invokes `afterCompletion` for **earlier** interceptors that returned true. Remaining interceptors that never ran receive no completion callback.

If you need to time the entire HTTP request—including requests rejected by security—Servlet-filter-layer instrumentation is more appropriate than timing solely in `afterCompletion`.

### 11.4. ExceptionTranslationFilter and Exceptions from MVC

`ExceptionTranslationFilter` can convert downstream security exceptions into HTTP responses via entry points/handlers when those exceptions reach it. However, **never rely on an interceptor throwing a custom exception expecting it to automatically behave like `AccessDeniedException`**. Spring MVC may catch/resolve exceptions via `HandlerExceptionResolver`; understand both exception types and catch locations.

An interceptor logging in `postHandle` can miss requests throwing exceptions, whereas a filter using `try/finally` still executes its after-block when an invocation entered the filter and returned or threw upstream.

## 12. Async, ERROR/FORWARD Dispatches, and Exceptions to the Diagram

The synchronous diagram at the start is the foundation, yet real applications involve async, forward, and error dispatches.

### 12.1. MVC AsyncHandlerInterceptor

`AsyncHandlerInterceptor` extends `HandlerInterceptor` with `afterConcurrentHandlingStarted`. For async requests—for example, controllers returning `Callable`, `DeferredResult`, or `CompletableFuture`—the callback sequence can be:

~~~text
REQUEST dispatch:
  preHandle
  Controller starts async
  afterConcurrentHandlingStarted  (if interceptor supports it)
  -> Servlet thread returns to container

ASYNC dispatch when result is ready:
  preHandle may be invoked again
  Process result
  postHandle
  afterCompletion
~~~

Never assume `postHandle` and `afterCompletion` execute during the initial dispatch. An interceptor storing state in a `ThreadLocal` must clean up properly on the async branch, or it can leak when the servlet thread returns to the pool. Use request attributes or an async-aware tracing library for correlation.

### 12.2. OncePerRequestFilter and Dispatcher Types

A `OncePerRequestFilter` exposes hooks such as:
- `shouldNotFilterAsyncDispatch()`
- `shouldNotFilterErrorDispatch()`
- `shouldNotFilter(request)`

Behavior depends on dispatch registrations and flags. **"Once per request" is not a guarantee of once across the entire logical lifecycle when a request spans multiple dispatches**. Filter instrumentation may need to record one event on the initial request and another on async/error dispatches depending on goals.

### 12.3. FORWARD and ERROR May Run Authorization Again

Spring Security's `AuthorizationFilter` can evaluate multiple dispatcher types; a `FORWARD` to a view or an `ERROR` dispatch to an error endpoint can trigger another authorization decision. With default-deny rules that omit dispatchers, you can hit 403 on error pages or forwarded views.

Under an appropriate policy, you might consider:

~~~java
// Illustrative snippet, not a rule to enable indiscriminately.
http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(
        DispatcherType.FORWARD,
        DispatcherType.ERROR
    ).permitAll()
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated()
);
~~~

Requires importing `jakarta.servlet.DispatcherType`. Using `permitAll` across all `FORWARD`/`ERROR` dispatches **is a policy trade-off**—use it only if the application genuinely needs it and internal endpoints are properly controlled. Never copy it blindly assuming every forward is safe. Observe the behavior of security filter chains, MVC interceptors, and dispatcher registrations together.

### 12.4. CORS Preflight

Browsers typically send an `OPTIONS` preflight before a cross-origin request. Preflights may lack the session cookie/Authorization header of the main request. If Security demands authentication **before CORS is processed**, the browser can be wrongly blocked.

Spring Security supports CORS integration at the filter layer, for example:

~~~java
http.cors(Customizer.withDefaults());
~~~

This is a snippet; it requires an appropriate `CorsConfigurationSource` or MVC CORS configuration and an allowlist policy for origins/methods/headers. **Do not treat an MVC interceptor as a CORS preflight solution**. Never combine wildcard origins with credentials carelessly.

### 12.5. CSRF

`CsrfFilter` protects state-changing requests when policy requires CSRF, before the MVC handler runs. An interceptor checking "admin" does not replace CSRF. When browsers use session cookies, keep appropriate CSRF protection on POST/PUT/PATCH/DELETE unless another threat model has been explicitly evaluated.

### 12.6. Do Not Apply the Servlet Diagram to WebFlux

Spring WebFlux uses `WebFilter`, `SecurityWebFilterChain`, `WebFilterChain`, and `DispatcherHandler` instead of Servlet Filter/MVC `DispatcherServlet`. Reactive Security Context flows through Reactor Context. Never rename `HandlerInterceptor` into a WebFlux interceptor or apply Servlet `ThreadLocal` patterns to a reactive pipeline.

## 13. Where Should Each Piece of Logic Live?

| Requirement | Right Layer | Reason |
| --- | --- | --- |
| Username/password, Bearer JWT, or opaque token | Spring Security authentication filters/providers | Verified before Controller, integrates SecurityContext |
| Checking `ROLE_ADMIN` on a URL | `authorizeHttpRequests`/AuthorizationFilter | Prevents MVC handler invocation when unauthorized |
| Authorizing `readInvoice` by owner/tenant | Method security/domain policy | Checks resource and caller, not only URL |
| CSRF, CORS, secure headers | Security filters and filter-based integrations | Enforced early before MVC |
| Application-wide rate limiting | Gateway or Servlet Filter/infrastructure | Covers requests not handled by MVC |
| Recording controller/handler mapping metadata | MVC HandlerInterceptor | Receives `Object handler`, can inspect `HandlerMethod` |
| Timing MVC handler processing only | HandlerInterceptor + proper metrics | Starts after `HandlerMapping` selects handler |
| Measuring end-to-end HTTP latency including 401/403 | Servlet Filter/early observability framework | MVC interceptor may not run |
| Customizing JSON response bodies | `ResponseBodyAdvice` | Runs where response bodies are handled |
| Mapping business exceptions to statuses | `@ControllerAdvice`/HandlerExceptionResolver | MVC exception handling |
| Translating authn/authz failures | AuthenticationEntryPoint/AccessDeniedHandler | Spring Security's dedicated mechanism |
| Logging for `@Scheduled` or queue consumers | Job instrumentation/service layer | No MVC request/`HandlerInterceptor` exists |
| Authorizing services invoked outside HTTP | Method security/service guards | Independent of MVC entry points |

Do not cram all cross-cutting logic into one interceptor layer. Separating responsibilities across layers makes testing easier and prevents gaps from mismatched scopes.

### 13.1. An Ownership Example

Endpoint:

~~~java
@GetMapping("/documents/{id}")
DocumentDto readDocument(@PathVariable long id) {
    return documentService.readDocument(id);
}
~~~

The Security DSL can require `.authenticated()` for `/documents/**`. Yet permission to "read document id=123" must be enforced by `documentService` or a policy bean checking owner/tenant/ACL, potentially via method security.

If an MVC interceptor checks `X-User-Id` and `X-Document-Owner`, an attacker can spoof headers; path aliases, other servlet routes, async calls, and direct service calls can also bypass it. Identity must come from a verified `Authentication`; permission must come from real resource data.

### 13.2. Limits of Hand-Written Filters

A custom `OncePerRequestFilter` can read `SecurityContext`, yet must be inserted **after authentication filters** if it expects an authenticated principal. Placed before authentication, `getAuthentication()` may be null or anonymous—that is not a `UserDetailsService` bug.

If a filter enforces authorization, it must sit where `Authentication` is trustworthy and handle `AccessDeniedException`/entry points properly rather than calling `response.setStatus(403)` ad-hoc on arbitrary branches. In practice, using `AuthorizationManager` or method security is usually preferable to hand-rolling an authorization filter.

### 13.3. Servlet Filter Beans and Double Registration

An easy mistake:

~~~java
@Component
class MyTraceFilter extends OncePerRequestFilter {
    // ...
}
~~~

followed by:

~~~java
http.addFilterAfter(
    myTraceFilter, AuthorizationFilter.class
);
~~~

With Spring Boot, a `Filter` bean can be auto-registered by the container; adding it to the Security chain as well can cause it to run **twice, in two scopes, with confusing order**. If the filter belongs strictly in the security chain, instantiate it directly or disable container auto-registration (e.g., via a disabled `FilterRegistrationBean`) and insert it in the right place.

### 13.4. Request Matching Must Be Tested Alongside Controller Mappings

Spring Security and MVC use different request matcher/mapping APIs. With multiple servlets, `servletPath`, `contextPath`, HTTP methods, path variables, trailing slashes, and framework upgrades, subtle discrepancies can arise. Spring Security documentation covers request matchers tailored for Servlet/MVC; verify against your actual version.

A security rule `.requestMatchers("/admin/**")` does not guarantee an interceptor's `.addPathPatterns("/admin/**")` shares the exact same scope across every app. Protect at the security layer and test real URLs/methods.

## 14. Observing and Debugging in the Right Order

When an interceptor appears "not to run", do not tweak annotations blindly. Ask:

1. Did the request reach the app, or did a load balancer/proxy/gateway return early?
2. Which Servlet Filters are registered with the container for that URL/dispatcher?
3. Were `DelegatingFilterProxy`/`springSecurityFilterChain` invoked?
4. Which `SecurityFilterChain` did `FilterChainProxy` select?
5. Did authentication succeed, or return 401?
6. Did `AuthorizationFilter` allow it, or return 403?
7. Did a CSRF/CORS filter reject before MVC?
8. Did the request reach `DispatcherServlet`?
9. Which handler did `HandlerMapping` resolve, and is it a `HandlerMethod`?
10. Is the interceptor registered in `WebMvcConfigurer`/`MappedInterceptor` on the right `HandlerMapping`?
11. Do `addPathPatterns`/`excludePathPatterns` match the actual route?
12. Did an earlier interceptor return `false`?
13. Did an exception skip `postHandle`?
14. Did async processing substitute `afterConcurrentHandlingStarted` for normal callbacks?
15. Does the request involve an `ERROR`/`FORWARD` dispatch, different path matcher, or different filter dispatcher registration?
16. Did the MVC callback run after the response was already committed, making header/body edits ineffective?
17. Is a Filter bean double-registered on both the container and the Security chain?
18. Is a unit test calling the Controller directly or using `standaloneSetup`, thereby omitting the full `SecurityFilterChain`?

### 14.1. Enabling Logging Safely

In development, you can enable:

~~~properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.web.servlet.DispatcherServlet=DEBUG
logging.level.org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping=DEBUG
~~~

Log correlation IDs, sanitized paths, selected chain, safe principal names, and authorization decisions. **Never log passwords, Authorization headers, session cookies, access tokens, refresh tokens, or full Authentication objects.**

### 14.2. Why Standalone MockMvc Can Mislead You

`MockMvcBuilders.standaloneSetup(controller)` does not spin up the full `ApplicationContext`, `SecurityFilterChain`, and MVC interceptors of the real application. Testing with standalone without registering filters/interceptors yields a different callback flow.

Use `@SpringBootTest` and `@AutoConfigureMockMvc` as in the demo so requests pass through security filters and MVC infrastructure. When using `@WebMvcTest`, verify which `SecurityConfig`/interceptors the slice imports and add missing config; never claim a suite verified the full stack if it only ran an isolated slice.

### 14.3. Additional Tests Needed Before Production

- Anonymous, invalid credentials, valid user lacking role, admin with role.
- Missing/invalid/valid CSRF tokens on unsafe HTTP methods.
- CORS preflight and actual cross-origin requests.
- Static resources, error pages, forward routes, unmapped paths.
- Custom filter registrations verified not to double-execute.
- `HandlerInterceptor` `preHandle(false)` and multi-interceptor ordering.
- Exceptions inside Controllers and `afterCompletion`.
- Async handler return types and async/error redispatches.
- Resource-level ownership/tenant policies at the service layer.
- Multiple `SecurityFilterChain` matchers, `servletPath`, and `contextPath`.
- Endpoints not managed by MVC yet requiring security filter protection.

## 15. Common Pitfalls

### 15.1. "HandlerInterceptor is a Spring MVC Servlet Filter"

No. `HandlerInterceptor` is not invoked by the container as a `jakarta.servlet.Filter`; it is a callback applied by MVC `HandlerMapping`/`DispatcherServlet` around a handler.

### 15.2. "Writing an interceptor is enough to secure the API"

No. It may miss other servlets, path mappings, or requests processed outside MVC. Use Spring Security and proper authorization mechanisms.

### 15.3. "preHandle always runs before every security filter"

False. Security filters sit ahead of MVC. Interceptor `preHandle` normally runs only **after** the request passes authentication/authorization filters.

### 15.4. "On a 401, preHandle will still run and log it"

No. `AuthenticationEntryPoint` can return 401 before MVC. To log those requests, instrument at the appropriate security/filter layer.

### 15.5. "postHandle is ideal for editing JSON after the controller"

Not guaranteed. With `@ResponseBody`/`ResponseEntity`, the body may already be written inside `HandlerAdapter`. Use `ResponseBodyAdvice` or a dedicated response transformation mechanism.

### 15.6. "afterCompletion always runs even when preHandle returns false"

No. An interceptor returning false receives no `afterCompletion` itself on that branch; earlier interceptors whose `preHandle` returned true do receive their callback.

### 15.7. "OncePerRequestFilter runs strictly once even with async/error dispatches"

Not automatically across every dispatcher scenario. Check dispatch registrations and the implementation's async/error hooks.

### 15.8. "CsrfFilter is an interceptor"

No. It is a Spring Security Filter running before the Controller and can return 403 before `HandlerInterceptor`.

### 15.9. "Filter and interceptor matching always align"

No. Servlet mappings, Security `RequestMatcher`s, and MVC `HandlerMapping`/`InterceptorRegistry` have distinct scopes; test real endpoints.

### 15.10. "A custom Filter added before authentication can still read the user"

Not guaranteed. Filter position matters; a filter before authentication may see no `Authentication`, or an anonymous one depending on the chain.

### 15.11. "Annotating a filter with @Component and calling addFilterAfter is harmless"

It can trigger double registration, running outside the expected chain. Choose one clear registration strategy.

### 15.12. "A permitAll endpoint bypasses all security"

No. `permitAll` is an authorization decision; filters can still execute. It differs from `web.ignoring` or matching no chain.

### 15.13. "SecurityContextHolder always contains a human user"

No. It can hold an anonymous token or a service/JWT principal. Check principal type and authorization policies.

### 15.14. "Interceptors protect @Scheduled tasks and event listeners too"

No. There is no MVC `HandlerExecutionChain` for scheduled jobs. Use method security, job policies, and service identities.

### 15.15. "URL protection suffices for every resource"

No. A validly logged-in user might not own a given record. Combine Spring Security request rules with service/domain resource authorization.

## 16. Self-Assessment Questions

**Question 1.** Does a Servlet Filter or a HandlerInterceptor run first on a normal request?

**Answer:** The Servlet Filter chain; Spring Security is normally part of it. MVC interceptors run after `DispatcherServlet`/`HandlerMapping` resolves a handler.

**Question 2.** Does `HandlerInterceptor` implement `jakarta.servlet.Filter`?

**Answer:** No. It is a Spring MVC callback interface.

**Question 3.** Does a request missing Basic credentials to `/admin/panel` necessarily run `preHandle` before returning 401?

**Answer:** No. Security filters can reject it before MVC.

**Question 4.** If `preHandle` returns false, does the controller run?

**Answer:** Not for that execution chain invocation; the interceptor should handle the response appropriately.

**Question 5.** If interceptor B returns false after A returned true, who receives `afterCompletion`?

**Answer:** A can receive `afterCompletion`, while B does not on the `preHandle=false` branch.

**Question 6.** Can the CSRF filter return 403 even if the user is an admin?

**Answer:** Yes. CSRF protection operates independently of role authorization.

**Question 7.** Can `postHandle` always modify a `@ResponseBody` payload?

**Answer:** No. The response may already be written/committed inside `HandlerAdapter`.

**Question 8.** To enforce `ROLE_ADMIN` on `/admin/**`, should you write an interceptor reading headers or use `authorizeHttpRequests`?

**Answer:** Spring Security `authorizeHttpRequests`/`AuthorizationFilter`, combined with method security if needed.

**Question 9.** Does an MVC interceptor protect an API handled by a different servlet?

**Answer:** Not automatically. Protect it at the Servlet filter/gateway or appropriate layer.

**Question 10.** Does `FilterChainProxy` merge all matching `SecurityFilterChain`s into one chain?

**Answer:** No. It selects the first matching chain.

**Question 11.** What bug can a `@Component` filter passed to `addFilterAfter` cause?

**Answer:** Double registration on both the container and Security chain, causing duplicate runs or wrong ordering.

**Question 12.** How do you test real callback order in Spring Boot?

**Answer:** Use MockMvc integrated with `SecurityFilterChain`/MVC, record each stage into a request attribute, and assert the sequence.

**Question 13.** Can `Callable` async change the callback pattern?

**Answer:** Yes. `AsyncHandlerInterceptor` supports `afterConcurrentHandlingStarted`; callbacks may run again on the `ASYNC` dispatch.

**Question 14.** Why are interceptors not ideal as the primary security barrier?

**Answer:** Because their matching scope depends on MVC handlers and may diverge from controller routes/servlets; security must be enforced earlier and more broadly.

**Question 15.** Can a `permitAll` public endpoint still be processed by Filters and HandlerInterceptors?

**Answer:** Yes. `permitAll` does not bypass security filters; MVC interceptors also apply once a handler is resolved.

**Question 16.** If you need authorization to read a specific invoice of tenant A, is checking `authenticated` enough?

**Answer:** No. You need resource-level authorization by owner/tenant/action at the service/domain layer.

**Question 17.** A REST endpoint returns 200 yet a trace filter after `AuthorizationFilter` misses it—what should you inspect?

**Answer:** Filter registration, `SecurityFilterChain` matcher, dispatcher type, custom filter placement, and which chain the request entered; do not jump to blaming the MVC interceptor.

**Question 18.** Can both a Servlet Filter and an MVC HandlerInterceptor use `SecurityContextHolder`?

**Answer:** Yes, once context has been properly established. However, a filter before authentication may have no principal yet, while an interceptor after security typically sees a populated Authentication or anonymous token.

## 17. Official References

- Spring Security — **Servlet Architecture (Filter, FilterChainProxy, SecurityFilterChain)**: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security 6.5 — **Authorize HttpServletRequests**: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — **Authentication Architecture**: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — **CSRF Protection**: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — **CORS**: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security — **Method Security**: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Framework 6.2 — **MVC Interception**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/handlermapping-interceptor.html
- Spring Framework 6.2 — **Configure MVC Interceptors**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/interceptors.html
- Spring Framework — **Servlet Filters**: https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html
- Spring Framework — **Asynchronous MVC Requests**: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework API — **HandlerInterceptor**: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/HandlerInterceptor.html
- Spring Framework API — **AsyncHandlerInterceptor**: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/AsyncHandlerInterceptor.html

**Remember:** **Spring Security runs in the Servlet Filter chain, before `DispatcherServlet`; `HandlerInterceptor` is a callback inside MVC after a handler is resolved.** A Filter can block a request so the interceptor never runs. Use Spring Security for authentication, authorization, CSRF/CORS, and URL protection; use `HandlerInterceptor` for cross-cutting concerns tied to MVC handlers. Pick the right layer, verify callback order/dispatches explicitly, and add resource-permission checks at the service/domain layer.
