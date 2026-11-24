# Servlet Filter, FilterChain, and DispatcherServlet in the Request Flow

In a **Spring MVC on Servlet stack** application, an HTTP request does not go straight from the client into a `@RestController`. Before the controller is invoked, the **Servlet container** selects the matching `jakarta.servlet.Filter` instances, executes them in order within a `FilterChain`, and only then invokes the **target Servlet**. With Spring MVC, the typical target Servlet is **`DispatcherServlet`**. Spring Security leverages this mechanism to perform authentication, authorization checks, CSRF protection, and many other security layers **before** the business controller processes the request.

If you only remember one diagram, remember this one:

```text
Client (HTTP)
   |
   v
Servlet container (Tomcat / Jetty / Undertow)
   |
   v
Servlet Filter A (before)
   |
   v
DelegatingFilterProxy("springSecurityFilterChain")
   |
   v
FilterChainProxy
   |
   +-- Select the FIRST matching SecurityFilterChain
   |      |
   |      +-- SecurityContext / exploit protection
   |      +-- Authentication
   |      +-- Authorization
   |      +-- Other security filters depending on configuration
   |
   v
Servlet Filter B (if present and registered at that position)
   |
   v
DispatcherServlet (Spring MVC Servlet)
   |
   +-- HandlerMapping -> resolve controller/handler
   +-- HandlerAdapter -> invoke handler per contract
   +-- HandlerInterceptor -> preHandle/postHandle/afterCompletion per flow
   +-- Controller -> Service -> Repository
   +-- HttpMessageConverter / ViewResolver / HandlerExceptionResolver
   |
   v
HTTP response
   |
   +-- Filter B (post-chain.doFilter section)
   +-- Spring Security filters (unwind)
   +-- Filter A (post-chain.doFilter section)
   |
   v
Client
```

This diagram describes **a typical request path**; the actual order depends on filter registrations, `DispatcherType`, the list of security filters, security matchers, and Spring Boot configuration. In particular, Spring Security can **block a request** before `DispatcherServlet`, so the controller is not always invoked. Certain requests already handled by MVC/the controller may trigger a separate `ERROR` or `ASYNC` dispatch.

This lesson targets **Java 17+, Spring Boot 3, Spring Security 6.x, and Spring MVC/Servlet**. The core APIs are based on Jakarta Servlet (`jakarta.servlet.*`), not the `javax.servlet.*` imports found in older documentation. At the end of the lesson are a **standalone Java 17 program**, a Spring Boot project demonstrating two filter layers, and MockMvc tests.

## 1. Accurately Distinguishing the Concepts

| Concept | Layer | Role | Directly invokes Controller? |
| --- | --- | --- | --- |
| `jakarta.servlet.Filter` | Servlet API/container | Intercept, wrap, or process request/response before/after downstream | Does not need to know about controllers; calls `chain.doFilter` |
| `jakarta.servlet.FilterChain` | Servlet API/container | Represents the remaining filter chain and target Servlet | Proceeds to the Servlet when filters are exhausted |
| `DispatcherServlet` | Spring MVC | Front controller of Spring MVC; resolves and invokes handlers | Yes, via HandlerMapping and HandlerAdapter |
| `HandlerMapping` | Spring MVC | Selects a handler by path, HTTP method, and other criteria | Only resolves handler/interceptors |
| `HandlerAdapter` | Spring MVC | Executes the resolved handler according to the appropriate contract | Yes |
| `HandlerInterceptor` | Spring MVC | Intervenes during handler processing inside MVC | Related to handlers, but not a Servlet Filter |
| `DelegatingFilterProxy` | Spring Web/Servlet bridge | A Filter invoked by the container that delegates to a Spring bean | Not directly |
| `FilterChainProxy` | Spring Security | Filter managing one or more `SecurityFilterChain` instances | Not directly; continues the original chain if permitted |
| `SecurityFilterChain` | Spring Security | Matcher and list of filters protecting a request | Not a container FilterChain |
| `SecurityContextHolder` | Spring Security | Exposes the Authentication of the current context | Not a filter/servlet |
| `@ControllerAdvice` | Spring MVC | Handles MVC errors/logic within its applicable scope | Does not automatically catch errors thrown before MVC |

**Do not conflate:** `FilterChain` (Servlet API interface), `SecurityFilterChain` (Spring Security contract), and Spring MVC's "chain of HandlerInterceptors" are three distinct concepts in three different places.

### 1.1. What Is the Servlet Container Responsible For?

For example, Tomcat receives a request. The container selects the target Servlet from servlet mappings and selects the registered Filters matching the URL pattern/Servlet name/dispatcher type. It constructs the `Filter -> Filter -> ... -> Servlet` path, invokes the first Filter, and supplies a `FilterChain` so each filter decides whether to proceed.

In Spring Boot with embedded Tomcat by default (when using the common Web starter), `DispatcherServlet` is auto-registered by Boot. You rarely need to create this Servlet manually in a standard MVC application.

### 1.2. DispatcherServlet Is Not a Filter

`DispatcherServlet` extends `HttpServlet`; it is the **target Servlet**, not a `jakarta.servlet.Filter`. It only starts processing once upstream filters allow the request to proceed. MVC's responsibility covers mapping/handler binding, controllers, request/response conversion, and resolving exceptions per the MVC contract; it does not replace Spring Security's FilterChainProxy.

### 1.3. FilterChain Is Not a "List of Filters for You to Loop Over"

In `Filter.doFilter`, the `chain` parameter is the **remaining processing pipeline** provided by the container:

```java
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain) throws IOException, ServletException {

    // Before the request goes to the next Filter or Servlet.
    chain.doFilter(request, response);
    // After downstream has returned (if no exception escaped).
}
```

If you **do not call** `chain.doFilter`, downstream filters and the Servlet are not invoked in the current branch. If you call `chain.doFilter`, code after the call only runs when downstream returns normally; use `finally` if you need to guarantee resource cleanup/completion logging when downstream throws an exception.

## 2. The "Enter and Unwind" Mechanism of FilterChain

Suppose there are two filters A, B and an MVC servlet:

```text
request --> A.before --> B.before --> DispatcherServlet --> Controller
                     <-- B.after <-- A.after <-- response
```

This is a **nested calls** structure, not "run A, then B, then controller, then terminate immediately". If code uses `try/finally`:

```java
public void doFilter(ServletRequest request, ServletResponse response,
                     FilterChain chain)
        throws IOException, ServletException {
    logBefore(request);
    try {
        chain.doFilter(request, response);
    } finally {
        logAfter(request);
    }
}
```

then `logAfter` still executes when downstream throws an error, but **that does not mean the HTTP response has not been committed**. Never assume you can always modify headers/status/body in `finally`: the application may already have flushed/committed the response from the controller or a downstream filter.

### 2.1. When a Filter Refuses to Proceed

A filter can terminate a request by returning an error and calling `return`:

```java
if (!allowed) {
    httpResponse.sendError(HttpServletResponse.SC_FORBIDDEN);
    return; // Do not call chain.doFilter.
}

chain.doFilter(request, response);
```

If Filter A blocks, Filter B and DispatcherServlet do not run. If a security filter blocks due to missing credentials or insufficient permissions, the controller may likewise not run. When debugging the question "why isn't my controller breakpoint being hit?", start with container filters and security filters.

### 2.2. Request/Response Wrappers

A filter can wrap `HttpServletRequest` or `HttpServletResponse` and pass the wrapper downstream. For example, a request wrapper supports reading the body multiple times, or a response wrapper captures content for compression or caching. However, reading the request body ahead of time can **consume the input stream**; if the wrapper does not cache/replay properly, `@RequestBody` in the controller will read empty data.

Do not indiscriminately log request bodies containing passwords, access tokens, or session cookies. For security, tracing should record request ID, method, normalized path, status, and latency rather than secrets.

### 2.3. Filter Order Matters Greatly

A set of filters only works properly when the order makes sense. In a security flow, context/authentication must exist before authorization steps that depend on identity. A logging filter outside the security chain may see an unauthenticated request; a filter after authentication can read the verified principal.

Order must be designed at the **right layer**: servlet filter registration order is not the same as filter order inside a `SecurityFilterChain`.

## 3. How Spring Security Enters the Servlet FilterChain

Servlet-based Spring Security does not replace the Servlet container. It integrates via a filter registered in the container called `DelegatingFilterProxy`, which typically delegates to a Spring bean named `springSecurityFilterChain`; this bean is usually `FilterChainProxy`.

```text
Servlet container FilterChain
   |
   +-- Servlet Filter 1
   |
   +-- DelegatingFilterProxy
   |       |
   |       +-- Spring Bean: springSecurityFilterChain
   |                   |
   |                   +-- FilterChainProxy
   |                           |
   |                           +-- Select matching SecurityFilterChain
   |                           +-- Run list of Spring Security filters
   |                           +-- Return to container FilterChain if not blocked
   |
   +-- Next Servlet Filter (if registered)
   |
   +-- DispatcherServlet
```

**`DelegatingFilterProxy` acts as a lifecycle bridge:** the Servlet container knows about the registered Filter, while the Spring ApplicationContext manages the Spring bean. This allows security filter beans to use dependency injection and security configuration without declaring dozens of filters in `web.xml`.

### 3.1. FilterChainProxy Selects a SecurityFilterChain

`FilterChainProxy` receives a list of `SecurityFilterChain` instances, each with a matcher and security filters. For the current request, it selects the **first matching chain in configured order**. Other chains whose paths also match are **not combined**.

Example:

```text
@Order(1): API chain      securityMatcher("/api/**")
                         -> API authentication + authorization

@Order(2): website chain  match any request
                         -> form login + browser protections

GET /api/orders -> selects API chain (first match)
GET /home       -> selects website chain
```

This illustrates rule matching; the actual Spring Boot sample below uses only **one** chain to keep the lesson's logic focused.

**Important:** If no chain matches a request, the request may be **unprotected by Spring Security** even though it still passes through the container/DispatcherServlet. Unless there is a specific reason, always have a fallback chain protecting all appropriate requests.

### 3.2. securityMatcher vs. requestMatchers

- `http.securityMatcher("/api/**")`: decides whether **this SecurityFilterChain itself** applies to the request.
- `authorizeHttpRequests(auth -> auth.requestMatchers("/api/admin").hasRole("ADMIN"))`: is an **authorization rule inside** the already selected chain.
- `.anyRequest().authenticated()`: applies to the remaining requests **within the scope of the chain**.
- `permitAll()`: allows access at the **authorization step**, but the request **still passes through the security chain** and can be processed by other security filters (e.g., CSRF, headers, CORS).
- `web.ignoring()`: excludes requests from the Spring Security filter chain, unlike permitAll, and may skip security headers/other filters as well. Only use when you understand the impact.

**Anti-pattern:**

```java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated()
    );
```

If this is the **only chain**, a path like `/admin` outside `/api/**` may have no chain protecting it at all. Do not infer from `anyRequest().authenticated()` that the entire site is secured.

### 3.3. What Do the Security Filters Do?

Depending on the chain, common filter categories include:

| Category | Representative Component | Responsibility |
| --- | --- | --- |
| Context | `SecurityContextHolderFilter`, related repository | Load/manage SecurityContext for the request |
| Exploit protection | `HeaderWriterFilter`, `CsrfFilter`, CORS config | Add headers, handle CSRF/CORS per configuration |
| Login/authentication | `UsernamePasswordAuthenticationFilter`, `BasicAuthenticationFilter`, appropriate bearer token filter | Create/verify Authentication |
| Anonymous/context | `AnonymousAuthenticationFilter` | Populate an anonymous Authentication when no principal is present |
| Exception translation | `ExceptionTranslationFilter` | Translate downstream AuthenticationException/AccessDeniedException into appropriate handling |
| Authorization | `AuthorizationFilter` | Decide whether the request is allowed to proceed |
| Logout/session | `LogoutFilter`, session-related filters | Handle logout/session security per flow |

This is not a **mandatory, fixed-order** list for every configuration. The filter list varies by form login, HTTP Basic, JWT, CSRF, version, and application. Read startup logs or enable DEBUG/TRACE in a controlled manner to inspect the actual chain.

### 3.4. FilterChainProxy Has Responsibilities You Should Not Bypass

`FilterChainProxy` is the central entry point of Servlet Spring Security, handling `SecurityContext` clearing and `HttpFirewall`. Do not bypass FilterChainProxy by registering a handful of standalone "security filters" yourself and assuming you get all the framework's guarantees.

## 4. DispatcherServlet: Front Controller of Spring MVC

Once the Servlet container finishes running filters and calls the target Servlet, `DispatcherServlet` handles the Spring MVC part:

```text
DispatcherServlet
   |
   +-- HandlerMapping
   |       resolve handler and HandlerExecutionChain
   |
   +-- HandlerAdapter
   |       resolve method args, invoke @Controller/@RestController
   |           |
   |           +-- HandlerInterceptor.preHandle()
   |           +-- Business Service / Repository
   |           +-- Return value
   |           +-- HandlerInterceptor.postHandle() (when applicable)
   |
   +-- Message converters / View resolvers
   |
   +-- HandlerExceptionResolver if an MVC error is handled
   |
   +-- HandlerInterceptor.afterCompletion() per lifecycle
   |
   +-- HTTP response returns to Servlet filters
```

This diagram is a conceptual model and **does not** guarantee the exact callback order in every scenario (especially `@ResponseBody`, async, and exceptions). Spring MVC `HandlerMapping` resolves handlers and interceptors, while `HandlerAdapter` executes the handler and handles argument binding/return values.

### 4.1. HandlerMapping and HandlerAdapter

Example:

```java
@RestController
@RequestMapping("/api")
class OrdersController {
    @GetMapping("/orders/{id}")
    Map<String, Object> getOrder(@PathVariable long id) {
        return Map.of("id", id);
    }
}
```

When `GET /api/orders/42` passes through the filters:

1. DispatcherServlet uses HandlerMapping to locate the appropriate handler.
2. HandlerAdapter invokes the method with argument `id=42` after type conversion.
3. The return value is written to the response via message conversion, such as Jackson JSON.
4. The response unwinds back through the Servlet Filters that called `chain.doFilter`.

This snippet is a fragment, not a standalone Java class: it requires Spring MVC dependencies and imports for `java.util.Map` and `org.springframework.web.bind.annotation.*`.

### 4.2. HttpMessageConverter Is Not a Servlet Filter

For `@RequestBody`, a message converter can parse JSON and pass the object to the controller; for `@ResponseBody` or `@RestController`, the converter can serialize the return value to JSON. That processing occurs **inside Spring MVC**, after security filters allow the request to continue.

Do not use `HttpMessageConverter` to replace Authorization header checks or request-level protection at the filter layer. Conversely, you do not need to manually parse every JSON body in a Servlet Filter when MVC already has proper binding/validation mechanisms.

### 4.3. MVC ExceptionResolver vs. Security Exception Translation

`@ControllerAdvice` and `HandlerExceptionResolver` handle errors occurring within MVC request processing, such as `ResponseStatusException` or business exceptions thrown by controllers.

Spring Security's `ExceptionTranslationFilter` handles **AuthenticationException** and **AccessDeniedException** thrown by **downstream** filters/logic inside the security chain under appropriate conditions. It can trigger `AuthenticationEntryPoint` (e.g., 401/login redirect) or `AccessDeniedHandler` (e.g., 403).

**Do not assume** an exception thrown from a servlet filter **before DispatcherServlet** will be caught by `@ControllerAdvice`. When an error originates before MVC, you need a handler at the appropriate layer, an error dispatch, or dedicated exception handling configuration.

## 5. Comparing Servlet Filter and HandlerInterceptor

| Scenario | Servlet Filter | HandlerInterceptor |
| --- | --- | --- |
| Runs before DispatcherServlet resolves handler? | Yes, if registered upstream | No, requires HandlerMapping to find a handler |
| Can block request before reaching controller? | Yes | Can block after a handler is selected |
| Has handler method and annotations available? | Not by default | Can inspect `handler` as `HandlerMethod` when applicable |
| Wraps HttpServletRequest/Response? | Yes | Possible, but not the universal container wrapper mechanism |
| Used for foundational authentication? | **Usually the right layer** (Spring Security Filters) | Should not replace Spring Security |
| Used for MVC-specific logic? | Possible, but lacks handler context | **Better suited**, e.g., timing a controller handler |
| Protects requests with no MVC handler? | Yes | May not run if no handler is found |
| Intercepts before static/default Servlet resources? | Depends on registration/mapping | Only for matching MVC handlers |
| Ordering | Servlet filter registration and security chain | HandlerMapping + `InterceptorRegistry` |
| Async/error dispatch | Per DispatcherType, filter policy | Per MVC async/handler mapping lifecycle |

`HandlerInterceptor` provides `preHandle`, `postHandle`, and `afterCompletion`. If you write an interceptor for authorization, you must recognize that URLs not belonging to that MVC handler may not pass through the interceptor; that is why Spring Security typically enforces request-level authentication/authorization at the Servlet filter layer.

### 5.1. Interceptor Snippet

```java
public class DurationInterceptor implements HandlerInterceptor {
    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {
        request.setAttribute("startedNanos", System.nanoTime());
        return true;
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception exception) {
        Long start = (Long) request.getAttribute("startedNanos");
        if (start != null) {
            long elapsed = System.nanoTime() - start;
            // Record metric safely; do not log credentials.
        }
    }
}
```

This is a fragment requiring Spring Web MVC/Jakarta Servlet imports. It does not run standalone on plain JDK. An interceptor must be registered through `WebMvcConfigurer.addInterceptors` or an appropriate MVC mechanism. It does not replace AuthenticationManager, SecurityFilterChain, or CSRF policies.

## 6. What Can Change Execution Order?

Influencing factors include:

1. **Servlet Filter registration order**: the order in which filters are registered with the Servlet container.
2. **URL patterns and servlet mappings**: whether the filter applies to the request.
3. **Dispatcher types**: `REQUEST`, `FORWARD`, `INCLUDE`, `ASYNC`, `ERROR`.
4. **SecurityFilterChain matchers**: FilterChainProxy picks the **first matching chain**.
5. **Filter order within a chain**: `HttpSecurity.addFilterBefore/After/At` or defaults.
6. **Whether a filter calls `chain.doFilter`**: if not, downstream stops.
7. **Async/error dispatch and container error page**: may initiate a new dispatch.
8. **HandlerMapping and MVC interceptors**: after DispatcherServlet is actually invoked.
9. **Proxy/load balancer/gateway**: may process requests before reaching the Servlet container, though not as a Servlet Filter in this JVM.

Do not draw one diagram and treat it as guaranteed identically across every request. Directly test the configured filter chain.

### 6.1. Filter Registration in Spring Boot

A container filter can be registered via `FilterRegistrationBean`:

```java
@Bean
FilterRegistrationBean<MyFilter> myFilterRegistration() {
    FilterRegistrationBean<MyFilter> bean =
        new FilterRegistrationBean<>(new MyFilter());
    bean.addUrlPatterns("/*");
    bean.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
    bean.setDispatcherTypes(DispatcherType.REQUEST);
    return bean;
}
```

This is a fragment requiring `MyFilter`, imports, and Spring Boot. `setOrder` controls **container registration order**, while `setDispatcherTypes` restricts dispatch types. A filter outside the security chain can run before or after DelegatingFilterProxy depending on the actual order.

### 6.2. Custom Security Filters Must Be Placed Correctly

For example, a filter that needs an authenticated principal and runs before authorization:

```java
http.addFilterBefore(
    new MyAuditFilter(),
    AuthorizationFilter.class
);
```

This is a fragment and the position is illustrative only. A filter needing authentication should be placed **after** the appropriate authentication step; placing it mistakenly before Basic/Bearer/login filters may observe an `AnonymousAuthenticationToken` or no Authentication yet.

**Double registration warning:** If you annotate a custom `Filter` with `@Component`/**`@Bean`** and also pass that same instance to `HttpSecurity.addFilterBefore`, Spring Boot can **register it directly with the Servlet container** while Spring Security also invokes it inside FilterChainProxy. As a result, the filter can run twice or in the wrong position. If you only want it inside the security chain, you can instantiate it with `new` inside the chain or disable container registration for that bean via `FilterRegistrationBean.setEnabled(false)`.

### 6.3. Does addFilterAt Replace an Existing Filter?

The API name is easily misunderstood. `addFilterAt(filter, SomeFilter.class)` places a custom filter at a framework-known order position, but you should not assume it **removes** an existing filter at that same position. Check the Javadoc/version and inspect the actual chain to avoid accidentally having two filters at the same order.

## 7. Is OncePerRequestFilter Truly "Once per Entire HTTP Request"?

Spring Web's `OncePerRequestFilter` helps implement a filter with a guard against re-execution within a single **request dispatch** according to the class policy. It does not by itself guarantee that a filter appears in only one chain or runs only once across the **entire lifecycle** involving async/error/forward dispatches.

Key methods:

- `doFilterInternal(HttpServletRequest,HttpServletResponse,FilterChain)` to implement logic;
- `shouldNotFilter(HttpServletRequest)` to skip specific requests;
- `shouldNotFilterAsyncDispatch()` to control async dispatches;
- `shouldNotFilterErrorDispatch()` to control error dispatches;
- `isAsyncDispatch(...)` and `isAsyncStarted(...)` to detect async state.

**Important:** DispatcherType and filter registration must still match. If the container does not map the filter for `ASYNC`, overriding `shouldNotFilterAsyncDispatch()` alone will not make the container invoke the filter on async dispatches.

### 7.1. DispatcherType and New Dispatches

| DispatcherType | Typical Context | Consequence |
| --- | --- | --- |
| `REQUEST` | Initial HTTP request | Filter is normally invoked here |
| `FORWARD` | Internal forward via Servlet container | Filter runs only if mapping supports that dispatch type |
| `INCLUDE` | Including another resource | Similarly, depends on mapping |
| `ASYNC` | Servlet async dispatch continuing processing | May run on a different thread; filter can execute again |
| `ERROR` | Servlet error dispatch (e.g., 500/`/error`) | May pass through filters per ERROR configuration |

Because Spring Boot can map `/error` through DispatcherServlet, when debugging errors you may see an additional pass for the ERROR dispatch. Do not simply count filter logs and conclude the controller ran twice. With async, SecurityContext and MDC `ThreadLocal` values require proper propagation/lifecycle management; never casually store shared mutable state across threads.

### 7.2. Using Filters Safely for Tracing

If you need to measure request duration, you can record the timestamp before `chain.doFilter` and record the result in `finally`. However, once the response is committed, you must not attempt to write a second JSON error body. Record appropriate logs/metrics/trace spans instead of trying to write additional body content.

## 8. HTTP Scenarios and Which Point Handles Them

| Request | Deciding Point | Illustrative Result | Does Controller Run? |
| --- | --- | --- | --- |
| `GET /public` | Authorization permits → DispatcherServlet | 200 | Yes if mapping exists |
| `GET /api/hello` without Basic credentials | Security authorization/entry point | Typically 401 with HTTP Basic | No |
| `GET /api/hello` valid Basic | Provider authenticates → authorization → MVC | 200 | Yes |
| `GET /api/admin` user only has ROLE_USER | Security AuthorizationFilter | Typically 403 | No |
| `GET /unknown` permitted via permitAll, no MVC handler | DispatcherServlet/handler lookup | 404 | No matching controller |
| `POST /public` missing CSRF token with CSRF enabled | CsrfFilter | Typically 403 | No |
| `POST /public` valid CSRF, only @GetMapping exists | MVC handler matching | 405 | GET controller does not run |
| `GET /api/fail` controller throws business error | HandlerExceptionResolver/@ControllerAdvice | Per error mapping | Yes, then error is resolved |
| URL rejected by HTTP firewall | FilterChainProxy/HttpFirewall | Status depends on request rejection handling | No |
| SecurityFilterChain does not match, no fallback | No Spring Security authorization for that URL | Depends on MVC/other filters | Potentially yes, risking bypass |

Status codes 401/403/404/405 depend on the security mechanism/entry point, exception handler, HTTP method, URL mappings, and CSRF state. **Do not infer from status alone whether the controller ran.**

## 9. Spring Boot 3 Application Demonstrating Two Filter Layers and DispatcherServlet

We will build a standalone Spring MVC application in a Boot 3 project configured with Java 17. The goal is to record an **event trace inside HttpServletRequest** to distinguish:

- A Servlet Filter registered with the container via `FilterRegistrationBean`;
- A `OncePerRequestFilter` residing **only** inside the Spring Security chain;
- `DispatcherServlet` resolving and invoking the controller;
- When authentication/authorization blocks, the controller does not execute;
- The response unwinds back through filters that called `chain.doFilter`.

**Limitations:** Tracing with `request.setAttribute` is for learning and uses `ArrayList` for **synchronous** requests. Do not store traces in a singleton bean or a shared static mutable list. The example does not prove the order of every framework filter; `TraceSecurityFilter` is placed right before `AuthorizationFilter`. Do not apply this prototype as-is to async processing or production logging containing credentials.

Structure:

```text
src/main/java/example/filterflow/
    FilterFlowApplication.java
    TraceEvents.java
    ContainerTraceFilter.java
    SecurityTraceFilter.java
    SecurityConfig.java
    DemoController.java

src/test/java/example/filterflow/
    FilterFlowTest.java
```

### 9.1. Dependencies

In a Spring Boot 3 project with the Gradle plugin, repositories, and Java 17 toolchain, add to Groovy `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is **only the dependencies block**, not a complete build file. With Maven, use the equivalent starters and `spring-security-test` in test scope. Rely on Spring Boot dependency management/BOM for compatible Spring Security versions; do not manually mix Spring Framework and Spring Security JARs from different generations.

### 9.2. FilterFlowApplication.java

```java
package example.filterflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterFlowApplication.class, args);
    }
}
```

### 9.3. TraceEvents.java: Per-Request Trace Recording

```java
package example.filterflow;

import java.util.ArrayList;
import java.util.List;

import jakarta.servlet.http.HttpServletRequest;

public final class TraceEvents {

    private static final String KEY =
        TraceEvents.class.getName() + ".events";

    private TraceEvents() {}

    @SuppressWarnings("unchecked")
    public static List<String> events(HttpServletRequest request) {
        Object current = request.getAttribute(KEY);

        if (current != null) {
            return (List<String>) current;
        }

        List<String> created = new ArrayList<>();
        request.setAttribute(KEY, created);
        return created;
    }

    public static void add(HttpServletRequest request, String event) {
        events(request).add(event);
    }
}
```

This list belongs to a single `HttpServletRequest`, not an application-wide cache. The cast in the demo assumes only `TraceEvents` writes attribute KEY; production code must avoid attribute name collisions and handle concurrency/async properly. Do not add user passwords or Authorization headers to traces.

### 9.4. ContainerTraceFilter.java: Filter at the Servlet Container

```java
package example.filterflow;

import java.io.IOException;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;

public class ContainerTraceFilter implements Filter {

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        HttpServletRequest http = (HttpServletRequest) request;
        TraceEvents.add(http, "container:before");

        try {
            chain.doFilter(request, response);
        } finally {
            TraceEvents.add(http, "container:after");
        }
    }
}
```

This filter is a **Servlet container filter**; it is not automatically a member of the Spring SecurityFilterChain. The `finally` block runs after downstream when the call stack unwinds. Because JSON bodies are typically produced in the controller **before** unwinding, `:after` events may not appear in the returned body; the integration test reads the trace attribute after the request completes.

### 9.5. SecurityTraceFilter.java: Filter Inside SecurityFilterChain

```java
package example.filterflow;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public class SecurityTraceFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        TraceEvents.add(request, "security:before");

        try {
            chain.doFilter(request, response);
        } finally {
            TraceEvents.add(request, "security:after");
        }
    }
}
```

**Do not annotate this class with `@Component`.** If it is registered with the container and also added to the Spring Security chain, there is a risk of double registration. It is instantiated solely inside `SecurityConfig`.

### 9.6. SecurityConfig.java: Registering Outer Filter and Security Filter at the Right Layers

```java
package example.filterflow;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
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
    FilterRegistrationBean<ContainerTraceFilter> containerTrace() {
        FilterRegistrationBean<ContainerTraceFilter> registration =
            new FilterRegistrationBean<>(
                new ContainerTraceFilter()
            );

        registration.addUrlPatterns("/*");
        registration.setDispatcherTypes(DispatcherType.REQUEST);
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        return registration;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-secret"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo-secret"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/unknown", "/error")
                    .permitAll()
                .requestMatchers("/api/hello")
                    .authenticated()
                .requestMatchers("/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .addFilterBefore(
                new SecurityTraceFilter(),
                AuthorizationFilter.class
            )
            .build();
    }
}
```

Explanation of each decision:

1. `containerTrace()` returns a `FilterRegistrationBean`, so Spring Boot registers `ContainerTraceFilter` with the Servlet container; it is mapped for `REQUEST` and `/*` with a very early order to easily observe the layer outside security. Other framework filters may still exist; do not assume there are literally only two filters.
2. `SecurityTraceFilter` is placed **inside** `FilterChainProxy` via `addFilterBefore`. Because it is not a standalone Filter bean, Boot does not auto-register it again on the container.
3. `AuthorizationFilter` serves as an anchor to illustrate placement; in a typical HTTP Basic configuration, the authentication filter runs before authorization. With a different architecture, you must check the actual order.
4. `httpBasic` is for localhost demo only. Base64 in Basic auth is not secure encryption; production requires HTTPS.
5. `/public` is permitAll, **yet still passes through the security filters**.
6. `/api/hello` allows any authenticated user; `/api/admin` requires `ROLE_ADMIN`.
7. `/unknown` is permitAll with no controller, illustrating MVC 404 rather than being blocked by Security; `/error` is opened so error dispatches do not suffer unnecessary denial loops.
8. `anyRequest().denyAll()` denies any other undefined URLs.
9. CSRF is not disabled. For browser/session POST requests, the security filter can return 403 if a CSRF token is missing even when the path is permitAll.

### 9.7. DemoController.java: DispatcherServlet Selects a Handler

```java
package example.filterflow;

import java.util.List;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    Map<String, Object> publicInfo(HttpServletRequest request) {
        TraceEvents.add(request, "mvc:controller");
        List<String> steps = List.copyOf(TraceEvents.events(request));

        return Map.of(
            "message", "public",
            "steps", steps
        );
    }

    @GetMapping("/api/hello")
    Map<String, Object> hello(
            HttpServletRequest request,
            Authentication authentication) {

        TraceEvents.add(request, "mvc:controller");
        List<String> steps = List.copyOf(TraceEvents.events(request));

        return Map.of(
            "username", authentication.getName(),
            "steps", steps
        );
    }

    @GetMapping("/api/admin")
    Map<String, String> admin() {
        return Map.of("message", "admin");
    }
}
```

When `/public` or `/api/hello` runs, the controller copies the event list **at the moment it is invoked**. Consequently, the JSON response contains `container:before` if the container filter applied and `security:before` if the security filter executed; the JSON need not contain `:after` events that happen when the stack unwinds. `TraceEvents.events(request)` in a test after the request finishes reveals the unwind events as well.

**Do not dump entire request/response/Authentication objects into JSON** in a real application: that can leak cookies, secrets, or sensitive metadata.

### 9.8. Running the Application with Gradle

macOS/Linux:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Assuming the app listens on `http://localhost:8080`, try:

```bash
# Anonymous public: reaches controller
curl -i http://localhost:8080/public

# Anonymous private: security blocks, typically 401
curl -i http://localhost:8080/api/hello

# Valid password: controller is invoked
curl -i -u reader:reader-demo-secret \
  http://localhost:8080/api/hello

# Wrong password: 401, does not reach controller
curl -i -u reader:wrong-secret \
  http://localhost:8080/api/hello

# Reader lacks ROLE_ADMIN: 403
curl -i -u reader:reader-demo-secret \
  http://localhost:8080/api/admin

# Admin permitted: 200
curl -i -u admin:admin-demo-secret \
  http://localhost:8080/api/admin

# Security permitAll but MVC has no handler: 404
curl -i http://localhost:8080/unknown
```

Expected JSON for `GET /public` on an embedded container during a normal `REQUEST` dispatch:

```json
{
  "message": "public",
  "steps": [
    "container:before",
    "security:before",
    "mvc:controller"
  ]
}
```

The order/presence of other events may differ if you modify the code or filter registrations. This response **only describes the events recorded by the three demo classes**, not every framework filter and callback. The HTTP statuses above are **expected** outcomes, not logs executed in this article.

Security note: HTTP Basic only uses Base64; use HTTPS with real credentials. `curl -u` places the demo password on the command line and it may be recorded in shell history/process lists, so only test with local study credentials.

## 10. Testing with Spring Security and MockMvc

Create `src/test/java/example/filterflow/FilterFlowTest.java`:

```java
package example.filterflow;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.hasItem;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FilterFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicRequestPassesThroughSecurityFilterAndMvc()
            throws Exception {

        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"))
            .andExpect(jsonPath(
                "$.steps", hasItem("security:before")));
    }

    @Test
    void anonymousPrivateRequestIsRejectedBeforeController()
            throws Exception {
        mvc.perform(get("/api/hello"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicCredentialsReachController()
            throws Exception {
        mvc.perform(get("/api/hello")
                .with(httpBasic(
                    "reader", "reader-demo-secret")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("reader"))
            .andExpect(jsonPath(
                "$.steps", hasItem("mvc:controller")));
    }

    @Test
    void invalidBasicCredentialsAreRejected() throws Exception {
        mvc.perform(get("/api/hello")
                .with(httpBasic("reader", "wrong-secret")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedReaderCannotEnterAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic(
                    "reader", "reader-demo-secret")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminWithRoleCanEnterAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic(
                    "admin", "admin-demo-secret")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("admin"));
    }

    @Test
    void permitAllDoesNotCreateAMvcHandler() throws Exception {
        mvc.perform(get("/unknown"))
            .andExpect(status().isNotFound());
    }

    @Test
    void postWithoutCsrfIsBlockedEvenOnPublicPath()
            throws Exception {
        mvc.perform(post("/public"))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfButOnlyGetMappingIsMethodNotAllowed()
            throws Exception {
        mvc.perform(post("/public").with(csrf()))
            .andExpect(status().isMethodNotAllowed());
    }

    @Test
    void downstreamReturnsThroughSecurityFilterFinally()
            throws Exception {
        MvcResult result = mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andReturn();

        List<String> completedTrace =
            TraceEvents.events(result.getRequest());

        assertThat(completedTrace).containsSubsequence(
            "security:before",
            "mvc:controller",
            "security:after"
        );
    }
}
```

Run:

```bash
./gradlew test --tests example.filterflow.FilterFlowTest
```

Windows:

```powershell
.\gradlew.bat test --tests example.filterflow.FilterFlowTest
```

**Expected:** all **10 test methods** pass on a compatible Spring Boot 3/Spring Security 6.x project when files and dependencies are assembled properly. This result **is not an executed compile/test log**; it is only expected behavior based on the code presented.

Some subtleties:

- `@AutoConfigureMockMvc` sets up a mock servlet environment and Spring Security filters to test MVC/HTTP; it is not an embedded Tomcat listening on a real socket.
- Because how the MockMvc adapter registers container filters can differ from an embedded server, the tests intentionally **do not strictly assert `container:before`** in the JSON. They rely only on the security filter and controller belonging to the test chain.
- `TraceEvents.events(result.getRequest())` lets us read the `security:after` event **after** `MockMvc.perform` completes. We assert subsequence order rather than requiring the list to contain exactly three events.
- `POST /public` without a CSRF token receives 403 before MVC. When `csrf()` is added, MVC receives a POST for a URL with only `@GetMapping` and returns 405; this demonstrates that 403 and 405 are errors from **two different layers**.
- Using only `@WithMockUser` to test authorization is insufficient to prove HTTP Basic/password authentication actually runs; here, `httpBasic(...)` tests use credentials from the demo user store.
- The 404 test proves security `permitAll` does not conjure up a controller handler.
- `SecurityTraceFilter` is placed before `AuthorizationFilter`. Since BasicAuthenticationFilter can short-circuit on invalid credentials, do not assume every bad-password request reaches custom trace filters downstream.
- These tests do not prove filter registration order, async dispatch, or error dispatch on a real server; for those needs, add integration tests using a random port/embedded server and controlled logging.

## 11. Plain Java 17: Simulating FilterChain and "Unwind"

The following program **uses neither Spring nor the Servlet API**. It simulates two Filters, a `Next` chain, and a mock DispatcherServlet so you can observe the **before → deep down → unwind up** mechanism yourself. The model is deliberately simple, yet **compiles with JDK 17 javac** and produces deterministic stdout.

Create `ServletChainModel.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ServletChainModel {

    static class Exchange {
        final boolean authenticated;
        final List<String> events = new ArrayList<>();
        int status = 200;

        Exchange(boolean authenticated) {
            this.authenticated = authenticated;
        }
    }

    @FunctionalInterface
    interface Next {
        void proceed(Exchange exchange);
    }

    @FunctionalInterface
    interface MiniFilter {
        void run(Exchange exchange, Next next);
    }

    static Next buildChain(List<MiniFilter> filters, Next target) {
        Next current = target;

        for (int i = filters.size() - 1; i >= 0; i--) {
            MiniFilter filter = filters.get(i);
            Next downstream = current;
            current = exchange -> filter.run(exchange, downstream);
        }
        return current;
    }

    public static void main(String[] args) {

        MiniFilter outer = (exchange, next) -> {
            exchange.events.add("outer:before");
            try {
                next.proceed(exchange);
            } finally {
                exchange.events.add("outer:after");
            }
        };

        MiniFilter security = (exchange, next) -> {
            exchange.events.add("security:before");
            try {
                if (!exchange.authenticated) {
                    exchange.status = 401;
                    exchange.events.add("security:deny");
                    return; // Do not call downstream.
                }
                next.proceed(exchange);
            } finally {
                exchange.events.add("security:after");
            }
        };

        Next dispatcher = exchange -> {
            exchange.events.add("dispatcher:handler-mapping");
            exchange.events.add("controller:run");
            exchange.status = 200;
        };

        Next chain = buildChain(
            List.of(outer, security), dispatcher
        );

        for (boolean allowed : new boolean[] {true, false}) {
            Exchange request = new Exchange(allowed);
            chain.proceed(request);

            System.out.println(allowed ? "ALLOWED" : "DENIED");
            for (String event : request.events) {
                System.out.println(event);
            }
            System.out.println("status=" + request.status);
        }
    }
}
```

Run:

```bash
javac ServletChainModel.java
java ServletChainModel
```

**Exact stdout per the code:**

```text
ALLOWED
outer:before
security:before
dispatcher:handler-mapping
controller:run
security:after
outer:after
status=200
DENIED
outer:before
security:before
security:deny
security:after
outer:after
status=401
```

Interpretation:

- When `authenticated=true`, the outer filter lets the security filter run; the security filter lets the dispatcher run; after the controller, execution returns to `security:after` and then `outer:after`.
- When `authenticated=false`, the security filter sets 401 and **does not call `next.proceed`**. Therefore neither `dispatcher:handler-mapping` nor `controller:run` appears in the DENIED trace.
- Both `finally` blocks still run even though the security filter returned early.
- This is only a nested-call/short-circuit simulation: there are **no real** Servlet requests, `DelegatingFilterProxy`, `FilterChainProxy`, username/password verification, CSRF, or HttpMessageConverter in this program. The Spring Boot sample demonstrates the real stack.

## 12. When to Use a Filter, Interceptor, or Another Security Layer?

| Need | Typically Appropriate Extension Point | Warning |
| --- | --- | --- |
| Logging request ID upon entering Servlet container | `Filter`/`OncePerRequestFilter` with proper registration | Do not log Authorization header/sensitive body |
| HTTP Basic, JWT bearer, form login authentication | Spring Security filter chain | Do not re-implement auth in controllers |
| Endpoint authorization | `authorizeHttpRequests` and method security | Do not rely solely on URLs; verify object/owner/tenant at service layer |
| CSRF protection for cookie-based browsers | `CsrfFilter`/Spring Security config | `permitAll` does not disable CSRF |
| CORS | Properly ordered integrated CORS config | Preflight must be handled before authentication blocks |
| Attaching correlation ID across the request | Servlet Filter | Avoid MDC leaks across threads/async |
| Inspecting specific HandlerMethod metadata | `HandlerInterceptor` or annotation/method security | Does not cover requests not mapped by MVC |
| Validating JSON request body | `@Valid`/Bean Validation + MVC | Carelessly reading body in a filter can consume the stream |
| Changing HTTP status of controller errors | `@ControllerAdvice`/HandlerExceptionResolver | Unlikely to catch errors from filters before MVC |
| Business cross-cutting logic at methods | AOP/Service layer | Does not replace servlet request security |
| API Gateway, WAF, reverse proxy | Infrastructure in front of application | Does not mean in-service security is sufficient |

### 12.1. Should a Tenant-Resolution Filter Trust X-Tenant-ID?

No. The `X-Tenant-ID` header is client-supplied data. A filter may parse/normalize it, but **must never treat it as proof that the user has access to that tenant**. It must be verified against the authenticated principal and valid server-side membership/claims. For requests querying data, the service/repository must also enforce tenant, owner, and data-level authorization constraints.

### 12.2. Where Is SecurityContext Once Inside the Controller?

In a synchronous Servlet stack, `SecurityContextHolder` typically uses `ThreadLocal` to hold the Authentication during request processing. Spring Security's filter infrastructure is responsible for clearing the context per the lifecycle. Never store SecurityContextHolder in a static global or reuse it across requests.

When async execution switches threads, never assume ThreadLocal context propagates automatically. Use Spring Security's built-in propagation mechanisms when genuinely needed, along with tests for async dispatches and thread pools.

## 13. Practical Debugging by Symptom

| Symptom | Where to Check First | Possible Cause |
| --- | --- | --- |
| Request never reaches controller, 401 | `SecurityFilterChain`, Basic/Bearer filter, entry point | Unauthenticated or wrong credentials |
| Request never reaches controller, 403 | CsrfFilter/AuthorizationFilter | Missing CSRF or insufficient permissions |
| Request has permitAll but returns 404 | HandlerMapping/DispatcherServlet | No matching handler for that path |
| `/api/**` is protected, `/admin` is not | `securityMatcher`/fallback chain | No chain matches `/admin` |
| Custom filter runs twice | Boot FilterRegistrationBean/@Component and addFilterBefore | Double registration or another dispatch |
| ControllerAdvice does not catch error | Error originates in a Filter before MVC | Never reached MVC exception resolver |
| SecurityContext is always anonymous in filter | Filter runs before authentication | Wrong filter position |
| `@RequestBody` is empty after filter | Filter read stream without replay | Request body already consumed |
| Filter before-log appears, after-log missing | Exception/response commit without finally | Control flow/exception path |
| Filter runs again on `/error` | DispatcherType.ERROR | Container initiated an error dispatch |
| Async request loses Authentication | Thread switch/context propagation | ThreadLocal does not follow threads automatically |
| Static assets return 401 | Security matcher/authorization/registration | Static route not permitAll, or different servlet mapping |
| Login test passes with @WithMockUser but Basic fails | Test bypasses credential verification | Need real HTTP Basic/form auth test |
| Response has wrong header after filter finally | Response already committed | Set header early or use a proper wrapper |
| Endpoint authorization passes but leaks another user's data | Service lacks owner/tenant checks | URL rules do not replace object-level policy |

### 13.1. Controlled Chain Logging

With Spring Security 6.x, enable logging in dev environments:

```properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
logging.level.org.springframework.web.servlet.DispatcherServlet=DEBUG
```

Do not leave TRACE enabled long-term in production if logs risk exposing sensitive data; verify the exact log format and redaction. At startup, Spring Security can log the list of filters used for each DefaultSecurityFilterChain. When debugging, cross-check **URL, HTTP method, dispatcher type, securityMatcher, requestMatcher, filter order, and selected handler**.

### 13.2. Where Can You Set Breakpoints?

Suggested points:

1. `DelegatingFilterProxy.doFilter` — does the request pass through the bridge?
2. `FilterChainProxy.doFilter` — which security chain matches?
3. Custom `OncePerRequestFilter.doFilterInternal` — does it run, and what is auth at that moment?
4. `AuthorizationFilter` — why did it allow/deny?
5. `DispatcherServlet.doDispatch` — has it entered Spring MVC yet?
6. `RequestMappingHandlerMapping` — which handler was selected?
7. `RequestMappingHandlerAdapter` — is the controller method invoked?
8. `HandlerExceptionResolver` — where are MVC errors resolved?
9. Servlet container error/async dispatch — is there another dispatch?

Never call `DispatcherServlet` "the last filter" or `FilterChainProxy` "the controller-handling Servlet"; the two names belong to two different layers.

## 14. Mistakes and Anti-Patterns to Avoid

**1. Confusing FilterChain with SecurityFilterChain.** Servlet FilterChain runs filter registrations and the Servlet; SecurityFilterChain is the list of security filters selected by FilterChainProxy.

**2. Assuming DispatcherServlet is called first.** Servlet filters normally run first; security can deny before reaching MVC.

**3. Using a Servlet Filter to implement all authorization manually.** Easy to miss SecurityContext, CSRF, exception translation, and auditing. Leverage Spring Security and service-level access policies.

**4. Placing a custom auth filter in the wrong position.** If it runs before context/authentication setup, current Authentication is unavailable or anonymous.

**5. Creating a @Component filter and calling addFilterBefore without checking registration.** Boot may additionally auto-register it with the container.

**6. Creating only one SecurityFilterChain for /api/** and forgetting a fallback.** Other URLs may remain unprotected by Spring Security.

**7. Treating permitAll the same as ignoring.** permitAll still goes through filters; ignoring can skip security headers and protections.

**8. Thinking a filter always calls chain.doFilter.** It can short-circuit with 401/403, redirect, or write a response directly.

**9. Omitting finally when cleanup is needed.** Downstream exceptions can skip code after the chain call; use try/finally, but do not modify the body if the response is already committed.

**10. Reading the request InputStream and expecting the controller to read it again.** This can leave `@RequestBody` empty; use a proper caching wrapper.

**11. Thinking ControllerAdvice catches every filter exception.** MVC exception resolution has its own scope; the security exception translator also has its own position and exception types.

**12. Mistaking 404 for Security not working.** A 404 can occur when there is no MVC handler even while security permitAll ran.

**13. Mistaking 403 for a wrong role.** CSRF also commonly returns 403 even on permitAll paths.

**14. Treating OncePerRequestFilter as "once for all dispatches forever".** Async/error/forward have separate lifecycles and registrations.

**15. Hardcoding filter order from an old article.** Version/configuration determines the filter list; inspect logs and tests.

**16. Assuming ThreadLocal SecurityContext propagates automatically across all threads.** Async/thread pools require proper propagation and cleanup.

**17. Testing controllers only with direct method calls.** This skips the filter chain, auth/CSRF, encoding, and handler mapping. Use MockMvc or real HTTP integration tests.

**18. Logging full URLs containing reset tokens/query secrets.** A correlation ID must never become a credential leak vector.

**19. Using SecurityFilterChain @Order in place of FilterRegistrationBean order.** These are two distinct selection/ordering levels.

**20. Skipping owner/tenant checks because the API already has hasRole.** Feature-level roles do not prove permission on individual resources.

## 15. Checklist When Designing a Request Flow

**Container/Servlet**

- [ ] Do you know which Servlet actually receives the URL, and what its mapping is?
- [ ] Are you aware of all FilterRegistrationBean/web.xml/Servlet filters in use?
- [ ] Do filter order and DispatcherType match your threat model?
- [ ] Which filters can short-circuit or wrap request/response?
- [ ] Are async/error dispatches and response commits handled safely?

**Spring Security**

- [ ] Is `DelegatingFilterProxy` wired properly to `FilterChainProxy`?
- [ ] Does every important URL match its intended SecurityFilterChain?
- [ ] Is there a fallback chain when configuring multiple chains?
- [ ] Are `securityMatcher` and `authorizeHttpRequests.requestMatchers` used properly?
- [ ] Are custom security filters free of double registration?
- [ ] Are filters placed after context/authentication and before authorization when appropriate?
- [ ] Do AuthenticationEntryPoint, AccessDeniedHandler, and CSRF work properly?
- [ ] Is method/object/tenant authorization enforced where required?
- [ ] Are credentials, tokens, cookies, and sensitive data kept out of logs?

**Spring MVC**

- [ ] Does `DispatcherServlet` map to the right handler/controller?
- [ ] Are 404/405 and binding/validation errors tested?
- [ ] Are MVC interceptors used only for their proper responsibilities?
- [ ] Are `@ControllerAdvice`/exception resolvers not misused for filter errors?
- [ ] Does HttpMessageConverter handle request/response bodies properly?
- [ ] Are JSON/handler mapping and security tested together with MockMvc?

**Testing and Observability**

- [ ] Are there integration tests for public, authenticated, wrong-credential, and forbidden requests?
- [ ] Is there a test comparing CSRF 403 vs. authorization 403?
- [ ] Are before/after chain traces and short-circuiting demonstrated?
- [ ] Have security startup logs/selected chains been inspected in the right environment?
- [ ] Are filter double-registration/async/ERROR cases tested if the app uses them?
- [ ] Are unexecuted expected results never claimed as actual run logs?

## 16. Self-Check Questions

**1.** In a Spring MVC Servlet stack, which component is typically invoked by the Servlet container before DispatcherServlet?  
**Answer:** The registered Servlet Filters matching the request, in filter-chain order.

**2.** What does `jakarta.servlet.FilterChain` do?  
**Answer:** Lets a filter continue invoking the remaining filters and the target Servlet via `chain.doFilter`.

**3.** What happens if a filter does not call `chain.doFilter`?  
**Answer:** Downstream filters and the Servlet do not run in that branch.

**4.** Why does the output "A before, B before, Controller, B after, A after" make sense?  
**Answer:** Due to nested calls and stack unwinding when downstream returns.

**5.** Is DispatcherServlet a Servlet or a Filter?  
**Answer:** It is a Servlet / front controller of Spring MVC.

**6.** What does `DelegatingFilterProxy` do?  
**Answer:** Bridges a container Filter to a Spring-managed Filter bean, typically springSecurityFilterChain.

**7.** How many SecurityFilterChains does `FilterChainProxy` select when multiple matchers match?  
**Answer:** The first matching chain in order; it does not merge all of them.

**8.** How does `securityMatcher` differ from `requestMatchers` inside authorizeHttpRequests?  
**Answer:** The former selects the scope of the security chain; the latter sets rules inside that chain.

**9.** Why does permitAll not mean bypassing CSRF?  
**Answer:** The permitAll authorization rule does not disable CsrfFilter/security filters.

**10.** How do `HandlerMapping` and `HandlerAdapter` differ?  
**Answer:** Mapping locates the handler; adapter uses the appropriate contract to execute it.

**11.** Does HandlerInterceptor run before or after DispatcherServlet?  
**Answer:** Inside MVC handler execution after DispatcherServlet begins processing and locates a suitable handler.

**12.** Why is ControllerAdvice not guaranteed to catch exceptions from a Filter before DispatcherServlet?  
**Answer:** It participates in MVC exception handling and does not cover Servlet filters outside MVC.

**13.** Why can a custom Filter that is both `@Component` and passed to `addFilterBefore` run twice?  
**Answer:** Spring Boot may register it directly with the Servlet container while FilterChainProxy also invokes it.

**14.** Does SecurityContext automatically propagate across all threads in async processing?  
**Answer:** No. ThreadLocal requires proper propagation and lifecycle management.

**15.** What status is typically seen for a GET URL with permitAll but no controller?  
**Answer:** 404 from MVC/container when no matching handler exists.

**16.** Why can a POST to a public endpoint return 403 even if the user does not need to log in?  
**Answer:** CSRF protection still applies to unsafe HTTP methods under the default configuration.

**17.** Should you modify headers/body in a Filter's `finally` block regardless of whether the response is committed?  
**Answer:** No; design proper response wrappers/lifecycles and avoid writing after commit.

**18.** If a Filter only runs on REQUEST, does overriding `shouldNotFilterErrorDispatch()` guarantee it runs on ERROR?  
**Answer:** No; container registration mapping must also include `DispatcherType.ERROR`.

## 17. Official References

- [Spring Security 6.5 – Servlet Architecture: FilterChain, DelegatingFilterProxy, FilterChainProxy](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 – Configuring Multiple SecurityFilterChains](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 – Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 – CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Framework 6.2 – DispatcherServlet](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet.html)
- [Spring Framework 6.2 – DispatcherServlet Request Processing](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/sequence.html)
- [Spring Framework 6.2 – Special Bean Types](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/special-bean-types.html)
- [Spring Framework 6.2 – Servlet Filters and OncePerRequestFilter](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html)
- [Spring Boot 3.5 – Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Spring Boot 3.5 – Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Jakarta Servlet 6.0 Specification](https://jakarta.ee/specifications/servlet/6.0/)
