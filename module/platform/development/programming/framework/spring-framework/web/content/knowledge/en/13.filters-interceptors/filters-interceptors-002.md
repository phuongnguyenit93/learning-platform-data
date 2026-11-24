# Filter Chain, Registration Order, and Dispatcher Types in Spring MVC

## 1. Why Can a Filter Run Out of Order or Run Multiple Times?

In a Spring MVC application running on a **Servlet container**, an HTTP request passes through a **Servlet Filter chain** before reaching `DispatcherServlet`. A filter can perform work before and after the next component, such as normalizing encoding, reading trusted forwarded headers, authenticating, setting a correlation ID, or observing processing time.

Common incidents:

- A body-decoding filter runs before the character encoding filter, causing Unicode data to be misread.
- A CORS or proxy headers filter is placed after Spring Security, causing preflight requests to be rejected or URLs to be built incorrectly.
- A filter is accidentally registered **twice**, once with the Servlet container and once inside `SecurityFilterChain`.
- A filter works for the initial request but does not run on a `forward`, when the Servlet container handles an error, or when an async dispatch completes.
- A developer thinks `OncePerRequestFilter` means “only once from the start of the request through all subsequent dispatches,” whereas it guarantees once **per request dispatch in a request thread**, depending on async/error configuration and the already-filtered rules.
- Putting `@Order` on an interceptor and expecting it to change the Servlet Filter order.

This article explains **two independent configuration dimensions**:

1. **Where is the filter registered, which URLs/Servlets does it apply to, and in what position?**
2. **Does the filter participate in the current Servlet dispatch type?**

It then presents runnable Spring Boot 3.x / Java 17+ code and HTTP tests through an embedded Servlet container to observe the actual order, including normal requests and `FORWARD`.

## 2. Servlet Filter Chain: The Before/After Model

Each Servlet Filter implements `doFilter(request, response, chain)`. Calling `chain.doFilter(...)` forwards to the next filter or the target servlet. When that call completes, the code after it in the current filter executes in **reverse** order.

```text
Browser
  |
  v
[Filter A] before chain.doFilter         A-before
  |
  v
[Filter B] before chain.doFilter         B-before
  |
  v
[Filter C] before chain.doFilter         C-before
  |
  v
DispatcherServlet -> Spring MVC controller
  |
  v
[Filter C] after chain.doFilter           C-after
  ^
  |
[Filter B] after chain.doFilter           B-after
  ^
  |
[Filter A] after chain.doFilter           A-after
  |
  v
HTTP response
```

In source form:

```java
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain)
        throws IOException, ServletException {

    // Prepare request, context, or wrapper.
    before(request);

    try {
        chain.doFilter(request, response);
    } finally {
        // Clean up resources, measure duration, clear ThreadLocal...
        cleanup();
    }
}
```

This is a **fragment of a class implementing `jakarta.servlet.Filter`**, without the definitions of `before` and `cleanup`; it is not a standalone runnable Java file. The key significance of `finally`: cleanup still executes if downstream throws an exception. It is not always still possible to **modify status/headers/body** after `chain.doFilter`, because the response may already be committed.

If a filter **does not call `chain.doFilter`**, the request stops at the filter. This is valid when the filter intentionally sends 401/403/429 or handles the complete response, but it is a bug if it accidentally skips the chain and causes the controller never to be invoked.

### 2.1. Distinguishing Servlet Filter and MVC Interceptor

| Criterion | Servlet `Filter` | Spring MVC `HandlerInterceptor` |
| --- | --- | --- |
| Execution level | Servlet container/filter chain, before the target servlet | Inside `DispatcherServlet` after handler selection |
| Scope | Can apply to other servlets, resources, and dispatch types by mapping | Applies to matching MVC handlers |
| Target selection | URL patterns, servlet registrations, `DispatcherType` | `InterceptorRegistry`, handler, and include/exclude paths |
| Ordering | Filter registration/order in container | Order interceptors are added to the MVC chain |
| Request/response wrapping | Can wrap ServletRequest/ServletResponse | Not a Servlet Filter; uses `preHandle`/`postHandle`/`afterCompletion` |
| Input data | Operates at Servlet boundary, suited for encoding/security/logging | Suited for handler-attached metadata and MVC request timing |
| Replaces Security filter? | Spring Security has its own chain based on Servlet filters | Not sufficient to protect all servlet paths |

`HandlerInterceptor` has no `DispatcherType` mapping mechanism equivalent to registering a Servlet Filter. Therefore, placing mandatory security logic only in an interceptor and assuming it protects the entire application is usually incorrect.

## 3. Two Meanings of “Chain” When Using Spring Security

In Spring MVC you may encounter:

**A. Servlet container filter chain** — The Servlet specification orders registrations matching the URL, servlet name, and dispatcher type.

```text
Request
  |
  v
EncodingFilter
  |
  v
springSecurityFilterChain (DelegatingFilterProxy)
  |
  v
TraceFilter
  |
  v
DispatcherServlet
```

**B. Spring Security `FilterChainProxy` and `SecurityFilterChain`** — located **inside** the filter commonly named `springSecurityFilterChain`. `FilterChainProxy` selects a `SecurityFilterChain` matching the request; the security filters inside that chain have their own order.

```text
DelegatingFilterProxy (Servlet filter)
  |
  v
FilterChainProxy
  |
  +-- matching SecurityFilterChain
        |
        +-- SecurityContext...
        +-- Authentication...
        +-- Authorization...
  |
  v
returns to outer Servlet chain
```

Therefore:

- `FilterRegistrationBean#setOrder(...)` adjusts the **Servlet filter registration position**.
- `HttpSecurity#addFilterBefore` / `addFilterAfter` / `addFilterAt` adjusts the **filter position inside the Spring Security filter chain**.
- The two orders are **not interchangeable**. A custom filter that needs to participate in authentication/authorization must be configured in the right place; do not simply set a low order number to act as a security filter.
- If a custom filter is both a `Filter` bean that Boot auto-registers with the container **and** added to `HttpSecurity`, it can run twice. To prevent double registration, consider disabling Servlet registration for a security-only bean (see Section 11).

This article does not re-implement Spring Security; it only clarifies where to place filters and how to verify behavior.

## 4. Servlet `DispatcherType` Values

`jakarta.servlet.DispatcherType` is an enum for the **current dispatch type**, not the HTTP method. A single HTTP request can involve **more than one dispatch**.

| `DispatcherType` | When It Occurs | Important Notes |
| --- | --- | --- |
| **`REQUEST`** | Initial request dispatched by the container to the target servlet | Most common type |
| **`FORWARD`** | Server invokes `RequestDispatcher.forward(...)` or Spring view `forward:...` | Same server-side request; target URL/servlet may differ |
| **`INCLUDE`** | Server performs `RequestDispatcher.include(...)` | Includes another resource's content into the response; response rules differ from forward |
| **`ASYNC`** | An async request is redispatched from the async context into the servlet chain | May run on a different thread; not like a new HTTP client request |
| **`ERROR`** | Container dispatches to error page/error handler | Usually goes through error mapping; may involve nested error dispatches |

A filter only runs in a dispatch if **both conditions** hold:

1. The filter registration **maps to the target resource**: matching URL pattern/servlet name.
2. The registration **includes the current dispatcher type**.

Afterward, the filter code may still actively skip the request based on path, request attributes, or `OncePerRequestFilter` logic. A filter mapped only to `REQUEST` will not automatically receive `ERROR` just because it saw the initial request.

### 4.1. Example: A Request Can Pass Through a Filter a Second Time on Forward

```text
GET /api/demo/forward           dispatcher=REQUEST
       |
       +-- Filter A [REQUEST]    runs
       +-- Filter B [REQUEST]    runs
       +-- MVC handler returns "forward:/api/demo/echo"
                         |
                         v
  server FORWARD to /api/demo/echo      dispatcher=FORWARD
       |
       +-- Filter A [FORWARD]    runs if registration includes FORWARD
       +-- Filter B [REQUEST]    DOES NOT run on FORWARD
       +-- MVC handler echo
```

This is a **server-side forward**, not a `302/303` redirect. The browser does not receive a new request URL, because the container dispatches internally. If the handler returns `"redirect:/api/demo/echo"`, the client initiates a new HTTP request, whose dispatcher is typically **`REQUEST`**, not `FORWARD`.

### 4.2. `ERROR` and the `/error` Path

An error can trigger this flow:

```text
GET /api/orders/1 (REQUEST)
   |
  unhandled error / sendError
   |
Servlet container ERROR dispatch -> /error
   |
BasicErrorController / error view (depending on Spring Boot)
```

**A filter that wants to see `ERROR` must register `DispatcherType.ERROR` and its mapping must match the error dispatch target.** For example, a filter mapped only to `/api/orders/*` may **not** run on the error target `/error` even if its registration includes `ERROR`. A filter mapped to `/*` can see both, though it may still be skipped by `OncePerRequestFilter` if that class's default configuration skips ERROR.

Not every 4xx/5xx error response creates an ERROR dispatch: `@ControllerAdvice` or a handler can return `ResponseEntity`/`ProblemDetail` directly within the **same REQUEST dispatch**. Conversely, filters/security/container can trigger error handling before MVC runs. Verify empirically rather than guessing from the status code.

### 4.3. `ASYNC` Dispatch

In Spring MVC, a handler returning `Callable<T>`, `DeferredResult<T>`, or another async mechanism can start async processing. The initial request-serving thread may exit; the async result is redispatched back to the Servlet container to complete the HTTP response.

```text
HTTP request (REQUEST)
   |
Filter A -> DispatcherServlet
                 |
                 +-- controller returns Callable
                 +-- request startAsync
   |
REQUEST thread may exit
   |
worker thread computes result
   |
Servlet ASYNC dispatch
   |
Filter A [ASYNC] if mapped and not self-skipped
   |
DispatcherServlet renders/writes response
```

A filter using `ThreadLocal` must manage setting/clearing **for each appropriate thread/dispatch**, rather than trusting context to propagate automatically to worker threads. When a Servlet Filter needs to participate in async requests, check **`setAsyncSupported(true)`**, dispatcher mappings, the Servlet and all filters in the entire chain, and the filter class logic. “Having `ASYNC` in the mapping” does not enable async for a filter if async support across the chain is invalid.

### 4.4. `INCLUDE`

`RequestDispatcher.include(...)` causes a resource to contribute output to the running request's response. A Servlet Filter can participate in **INCLUDE** when its registration maps that type. Status/header modifications inside an included resource are restricted by Servlet semantics; do not use an INCLUDE filter as a replacement for the main controller response. Modern template engines typically use their own fragment mechanisms, which **do not imply a Servlet INCLUDE dispatch**.

## 5. Ways to Register a Servlet Filter in Spring Boot

### 5.1. Declaring a `Filter` Bean for Boot Auto-Registration

In a Boot app with an embedded Servlet container, a `Filter` bean is detected and typically auto-registered by Boot into the `ServletContext`:

```java
@Bean
Filter simpleFilter() {
    return (request, response, chain) -> {
        // Before downstream...
        chain.doFilter(request, response);
        // After downstream...
    };
}
```

This is a **bean factory method fragment** in a `@Configuration` class, requiring imports for `jakarta.servlet.Filter` and `org.springframework.context.annotation.Bean`. By default, Boot maps the filter bean according to filter registration rules, typically `/*`.

This approach is convenient when you do not need deep customization of URL patterns, dispatchers, or ordering. However, if the application requires **exact** ordering/dispatchers/URLs, use `FilterRegistrationBean` or an appropriate registration API.

### 5.2. `FilterRegistrationBean<T>`: Explicit Configuration

`org.springframework.boot.web.servlet.FilterRegistrationBean<T>` registers a filter with the embedded Servlet container and allows:

- `setFilter(filter)` or constructor taking the filter.
- `setOrder(int)` to specify registration order.
- `addUrlPatterns(...)` / `setUrlPatterns(...)` to restrict URLs.
- `setDispatcherTypes(DispatcherType...)` or `setDispatcherTypes(EnumSet<DispatcherType>)`.
- `setAsyncSupported(boolean)`.
- `setName(...)`, init parameters, servlet names, and several other mapping details.

Example:

```java
@Bean
FilterRegistrationBean<AuditFilter> auditRegistration() {
    FilterRegistrationBean<AuditFilter> registration =
            new FilterRegistrationBean<>(new AuditFilter());

    registration.setName("auditFilter");
    registration.addUrlPatterns("/api/*");
    registration.setDispatcherTypes(
            DispatcherType.REQUEST, DispatcherType.ERROR);
    registration.setOrder(100);
    registration.setAsyncSupported(true);
    return registration;
}
```

This is a **fragment**: `AuditFilter` is a filter class the application must define. The idea is to register **one filter instance via one registration bean**. Do not simultaneously annotate the filter class itself with `@Component`/`@WebFilter` and also register it separately in a way that causes double registration.

### 5.3. `@WebFilter` and `@ServletComponentScan`

The Servlet API has `@WebFilter` to declare a filter and URL/dispatcher mappings via annotation. In a Spring Boot embedded container, to automatically scan Servlet components accordingly, `@ServletComponentScan` is typically used (with Boot 3 using `jakarta.servlet.annotation.WebFilter`).

```java
@WebFilter(
    filterName = "legacyAudit",
    urlPatterns = "/legacy/*",
    dispatcherTypes = {
        DispatcherType.REQUEST, DispatcherType.FORWARD
    }
)
public class LegacyAuditFilter implements Filter {
    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {
        chain.doFilter(request, response);
    }
}
```

This is a **class fragment** requiring imports, which must be placed in `LegacyAuditFilter.java` with Servlet component scanning configured when using a Boot executable JAR. Newer Spring Boot versions offer additional Boot-provided registration annotation options; always check the exact version before copying.

Do not assume `@WebFilter` automatically receives full Spring dependency injection like `@Component` in all deployment models. Distinguish who manages the filter instance's lifecycle.

### 5.4. `web.xml` / `ServletContext#addFilter`

In a WAR or traditional Servlet application, you can register filters in `web.xml` or programmatically via `ServletContext`. They follow the Servlet specification and operate outside Boot's `FilterRegistrationBean` mechanism. When migrating a WAR to embedded Boot, avoid letting a filter be registered via **both paths** unintentionally.

## 6. FilterRegistrationBean Order, @Order, and Priority Numbers

When using Boot registration, **lower order numbers run first** among filters whose order is managed by Spring Boot. For example:

| Filter | Order | On the Way In | On the Way Out |
| --- | ---: | --- | --- |
| Filter A | `10` | Before B | After B |
| Filter B | `20` | After A | Before A |
| Filter C | `100` | After B | Before B and A |

If two filters share the same order, **do not rely on an unspecified order** between them. Assign distinct order values and test whenever ordering affects semantics. Framework-added filters (encoding, form content, Security, forwarded headers...) also have orders, so an application order of `10` does not guarantee “runs first among all filters.”

According to Boot 3.5 documentation, distinguish three approaches:

- Put `@Order` on the **Filter class** or implement `Ordered` for auto-registered filter beans.
- Call `setOrder(int)` on **`FilterRegistrationBean`** when you want certainty for a registration.
- **Do not rely on `@Order` solely on a `@Bean` method** returning a Filter to set the Servlet filter registration order; Boot recommends `FilterRegistrationBean` or ordering on the Filter class/instance itself.

A filter wrapping the request (to adjust headers, read a cached body, forwarded data...) may need to run very early. However, do not arbitrarily put a body-reading filter at `Ordered.HIGHEST_PRECEDENCE`: per Spring Boot, it may run **even before character encoding configuration**. Balance the order against existing filters, especially Security, CORS, body wrappers, and encoding.

### 6.1. Registration Order Differs from `addFilterBefore` Order in Spring Security

If you define:

```java
http.addFilterBefore(myFilter, UsernamePasswordAuthenticationFilter.class);
```

This is a **Spring Security configuration fragment**, not the global order of all Servlet filters. It defines the position **inside** a `SecurityFilterChain`; Spring Security's Servlet filter registration sits at an outer layer. Do not put `@Order(1)` on a custom security filter and assume it precedes Spring Security's authentication filter.

## 7. Filter Order Does Not Decide Whether a Filter Runs

A filter may **not run** even with an early order because:

1. The request/dispatch URL **does not match the URL pattern** or servlet name mapping.
2. The registration **does not include the current dispatcher type**.
3. The filter class **actively skips** via its own condition, e.g., `OncePerRequestFilter#shouldNotFilter(...)`.
4. For async/error, `OncePerRequestFilter` has `shouldNotFilterAsyncDispatch()` and `shouldNotFilterErrorDispatch()`.
5. `OncePerRequestFilter` detects an **already-filtered attribute** in the same dispatch/context and avoids executing `doFilterInternal` again.
6. An earlier filter did not call `chain.doFilter(...)`.
7. Spring Security `FilterChainProxy` selects a different security chain, or the custom filter was not added to the chain matching the request.
8. The filter failed to register, the registration is disabled, or the application uses a different Servlet context/route.

A filter may **run twice** even with a “correct” order when:

- One instance (or two instances with the same logic) is registered independently in both the Servlet chain and Security chain.
- A plain `implements Filter` is mapped to multiple dispatch types; each dispatch is another pass through the chain.
- `REQUEST` triggers a `FORWARD`; a filter mapped to both runs on both.
- Error handling creates a new `ERROR` dispatch; a filter mapped to ERROR runs again.
- An async request redispatches multiple times; if the filter maps ASYNC and its logic allows, extra executions occur.

**“Order” and “execution count” are two separate questions**: diagnosing the cause requires logging the filter name, dispatcher type, request URI, thread, and request correlation ID.

## 8. `OncePerRequestFilter`: What Does “Once” Mean?

`org.springframework.web.filter.OncePerRequestFilter` is Spring's base class implementing `Filter`, primarily providing `doFilterInternal(HttpServletRequest,HttpServletResponse,FilterChain)`. It uses an **already-filtered request attribute** to avoid duplicate processing in nested request dispatch scenarios.

```java
class RequestTagFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        request.setAttribute("serverTag", "from-filter");
        try {
            chain.doFilter(request, response);
        } finally {
            request.removeAttribute("serverTag");
        }
    }
}
```

This is a **class fragment**, requiring Jakarta Servlet and `OncePerRequestFilter` imports along with registration config. When the filter runs, downstream receives `serverTag`; after downstream returns, the attribute is cleaned up.

Common misconceptions:

- `OncePerRequestFilter` **does not auto-register itself** with the Servlet container. A Filter bean/FilterRegistrationBean/other registration is still needed.
- The base class **skips async dispatches** by default via `shouldNotFilterAsyncDispatch() == true` and **skips error dispatches** via `shouldNotFilterErrorDispatch() == true`.
- Override `shouldNotFilterAsyncDispatch()` to return `false` if you want `doFilterInternal` to participate in relevant `ASYNC` dispatches, **and** the Servlet Filter registration must also include `DispatcherType.ASYNC`.
- Override `shouldNotFilterErrorDispatch()` to return `false` if you want to handle `ERROR`; the registration also needs `DispatcherType.ERROR` and a URL/Servlet mapping matching the error target.
- For **nested error dispatches**, some Servlet containers may process a nested `ERROR` inside `REQUEST` before the original filter chain completely unwinds. Spring provides `doFilterNestedErrorDispatch(...)` to handle this case; the behavior cannot be summarized as “always once forever.”
- `FORWARD` can reuse the same request and hit the already-filtered marker. Thus, a `OncePerRequestFilter` registered for both REQUEST/FORWARD **does not necessarily invoke `doFilterInternal` a second time** when the forward is nested inside the initial `chain.doFilter`.
- The base class uses a request attribute marking execution per **filter instance/name**; avoid manually tampering with the marker name/key without understanding the impact.

Example when observing both async and error is needed:

```java
class AsyncErrorContextFilter extends OncePerRequestFilter {

    @Override
    protected boolean shouldNotFilterAsyncDispatch() {
        return false;
    }

    @Override
    protected boolean shouldNotFilterErrorDispatch() {
        return false;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {
        try {
            // Set per-thread context if needed.
            chain.doFilter(request, response);
        } finally {
            // Clear ThreadLocal/MDC if set.
        }
    }
}
```

This is an **illustrative class**, without concrete ThreadLocal logic. It still needs a registration such as:

```java
registration.setDispatcherTypes(
        DispatcherType.REQUEST,
        DispatcherType.ASYNC,
        DispatcherType.ERROR);
registration.setAsyncSupported(true);
```

Overriding the methods alone while forgetting the registration → async/error is never seen. Having the registration alone while keeping the default skip behavior → `doFilter(...)` may be entered, but `doFilterInternal(...)` will not run on those dispatches.

## 9. Java 17+ Spring Boot 3.x Example via Embedded Servlet Container

This example intentionally uses a **plain `Filter`** instead of `OncePerRequestFilter` to clearly show two executions across `REQUEST` and `FORWARD`. Both filters are instantiated directly inside `FilterRegistrationBean` and are **not** marked `@Component` to avoid accidental duplicate registration.

In a Spring Boot 3.x (Servlet MVC) project that already has the Boot plugin, repositories, and dependency management, add dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **`build.gradle` fragment**, not a complete build file. `spring-boot-starter-web` in Boot 3 includes the embedded Servlet stack container. The imports below use `jakarta.servlet.*`, not Boot 2's older `javax.servlet.*`.

Create **`src/main/java/demo/filterchain/FilterChainApplication.java`**:

```java
package demo.filterchain;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import java.io.IOException;
import java.util.EnumSet;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class FilterChainApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterChainApplication.class, args);
    }

    @Bean
    FilterRegistrationBean<RecordingFilter> firstRegistration() {
        FilterRegistrationBean<RecordingFilter> registration =
                new FilterRegistrationBean<>(new RecordingFilter("A"));

        registration.setName("demoFilterA");
        registration.addUrlPatterns("/api/filters/*");
        registration.setOrder(10);
        registration.setDispatcherTypes(EnumSet.of(
                DispatcherType.REQUEST,
                DispatcherType.FORWARD,
                DispatcherType.INCLUDE,
                DispatcherType.ASYNC,
                DispatcherType.ERROR));
        registration.setAsyncSupported(true);
        return registration;
    }

    @Bean
    FilterRegistrationBean<RecordingFilter> secondRegistration() {
        FilterRegistrationBean<RecordingFilter> registration =
                new FilterRegistrationBean<>(new RecordingFilter("B"));

        registration.setName("demoFilterB");
        registration.addUrlPatterns("/api/filters/*");
        registration.setOrder(20);
        registration.setDispatcherTypes(DispatcherType.REQUEST);
        registration.setAsyncSupported(true);
        return registration;
    }
}

class RecordingFilter implements Filter {
    static final String EVENTS_KEY = "demo.filter.events";

    private final String label;

    RecordingFilter(String label) {
        this.label = label;
    }

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        HttpServletRequest http = (HttpServletRequest) request;

        @SuppressWarnings("unchecked")
        List<String> previous =
                (List<String>) http.getAttribute(EVENTS_KEY);

        List<String> events = previous;
        if (events == null) {
            events = new CopyOnWriteArrayList<>();
            http.setAttribute(EVENTS_KEY, events);
        }

        // Record on the way in; "before" runs in ascending order.
        events.add(label + ":" + http.getDispatcherType().name());

        // Always forward to the next filter/servlet in this example.
        chain.doFilter(request, response);
    }

    static List<String> events(HttpServletRequest request) {
        @SuppressWarnings("unchecked")
        List<String> result =
                (List<String>) request.getAttribute(EVENTS_KEY);

        if (result == null) {
            return List.of();
        }
        return List.copyOf(result);
    }
}

@RestController
class EchoController {

    @GetMapping(
            path = "/api/filters/echo",
            produces = MediaType.TEXT_PLAIN_VALUE)
    String echo(HttpServletRequest request) {
        List<String> events = new java.util.ArrayList<>(
                RecordingFilter.events(request));

        events.add("handler:" + request.getDispatcherType().name());
        return String.join(" | ", events);
    }

    @GetMapping(
            path = "/api/plain",
            produces = MediaType.TEXT_PLAIN_VALUE)
    String plain() {
        return "plain";
    }
}

@Controller
class ForwardController {
    @GetMapping("/api/filters/forward")
    String forwardToEcho() {
        return "forward:/api/filters/echo";
    }
}
```

**Compilability:** this is a valid Java 17 file when built with Spring Boot 3.x + Servlet dependencies, because only `FilterChainApplication` is `public`. `RecordingFilter` and both controllers are package-private; Spring Boot component scanning from `demo.filterchain` still discovers the controllers. Do not run `javac FilterChainApplication.java` without the Spring/Servlet classpath; use the project's build tool.

### 9.1. Why Do Filters A and B Run in That Order?

- Both registrations map `/api/filters/*` and participate in **`REQUEST`**.
- A has `order=10`, B has `order=20`; on entry: **A before B**.
- B **maps only `REQUEST`**. A maps `REQUEST` and `FORWARD` along with the other dispatcher types.
- `EchoController#echo` reads the event list **before the response body is written**; it reflects the filter entry steps that have already occurred. If filters perform cleanup/logging after `chain.doFilter`, those subsequent events **do not appear in the already-rendered body**.
- `CopyOnWriteArrayList` is used to avoid races when reading the event list if async handling occurs; this is an observability demo, not an optimal high-throughput logging design.

### 9.2. Normal Request

```bash
./gradlew bootRun
curl -i 'http://localhost:8080/api/filters/echo'
```

With the registrations above and a typical embedded Servlet container, status is **200 OK**, `Content-Type` compatible with `text/plain`, body:

```text
A:REQUEST | B:REQUEST | handler:REQUEST
```

`/api/plain` does not match the URL pattern `/api/filters/*`, so its body is only:

```text
plain
```

Spring Boot may still have **other framework filters** running on both endpoints; the example records only the two custom filters A/B. Do not infer that the entire application's filter chain consists strictly of A and B.

### 9.3. Server-Side Forward

```bash
curl -i 'http://localhost:8080/api/filters/forward'
```

In a Servlet container supporting MVC forward as in this example, the recorded flow is:

```text
A:REQUEST | B:REQUEST | A:FORWARD | handler:FORWARD
```

Reason:

1. The initial request `/api/filters/forward` passes through A and B (both map REQUEST).
2. MVC `ForwardController` returns `forward:/api/filters/echo`; the server executes `FORWARD` within the same HTTP request.
3. On the forward dispatch, A still maps `FORWARD` and the target `/api/filters/echo`; B does **not** map `FORWARD`.
4. `EchoController` is invoked with dispatcher type `FORWARD` and reads the accumulated request attribute list.

The example uses a **plain Filter**, so there is no `OncePerRequestFilter` already-filtered marker blocking A a second time. Actual behavior also depends on URL mappings and the container. In the next testing section, use a real server via `@SpringBootTest(RANDOM_PORT)` rather than only simulating with MockMvc.

### 9.4. Intentional Limitations of the Example

- Only directly observes REQUEST/FORWARD. Registering `ASYNC`/`ERROR`/`INCLUDE` on A **does not generate** those dispatches by itself; testing them requires an async handler, error mapping, or Servlet include respectively.
- `ERROR` typically targets `/error` in Boot. Because A only maps `/api/filters/*`, it **may not see an ERROR dispatch to `/error`** even with ERROR registered. To observe error dispatches, map the error target appropriately (typically `/*` or `/error`).
- `FilterRegistrationBean#setAsyncSupported(true)` allows the registration to participate in async, but actual async execution requires the Servlet and all involved filters to support it.
- The app uses an embedded container without custom Spring Security; adding security adds more filters to the chain.
- Avoid using `CopyOnWriteArrayList` to accumulate large volumes of request logs in production; use structured logs/tracing, cleanup, and bounded data instead.
- The example does not record “after chain” events so that the response body always reflects the exact state at the moment the handler runs.

## 10. Integration Testing with an Embedded Container, Not Just MockMvc

Certain filter registration details such as dispatcher types, URL patterns, and forward/error mappings are **enforced by the Servlet container**. `MockMvc` is very useful for controller testing, but it may not fully reproduce dynamic filter registration or container forward/error dispatches like real runtime execution.

With Boot 3's `spring-boot-starter-test`, create **`src/test/java/demo/filterchain/FilterChainApplicationTests.java`**:

```java
package demo.filterchain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FilterChainApplicationTests {

    @Autowired
    TestRestTemplate http;

    @Test
    void requestDispatchRunsAThenBThenController() {
        ResponseEntity<String> response = http.getForEntity(
                "/api/filters/echo", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals(
                "A:REQUEST | B:REQUEST | handler:REQUEST",
                response.getBody());
    }

    @Test
    void servletForwardDispatchRunsOnlyAAgain() {
        ResponseEntity<String> response = http.getForEntity(
                "/api/filters/forward", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals(
                "A:REQUEST | B:REQUEST | A:FORWARD | handler:FORWARD",
                response.getBody());
    }

    @Test
    void customFiltersDoNotMatchOtherUrlPattern() {
        ResponseEntity<String> response = http.getForEntity(
                "/api/plain", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("plain", response.getBody());
    }
}
```

Run:

```bash
./gradlew test
```

**All three tests are expected to pass** with an embedded Servlet Spring Boot 3.x configuration like the example, assuming no extra security/filters alter routes or responses. This is the expected outcome from the source logic; **it is not a captured execution log**. If your environment uses a different servlet container or custom filters, inspect dispatching/registration on the actual server rather than forcing test assertions to mask discrepancies.

The advantage of `RANDOM_PORT`: the app boots a Servlet container and receives HTTP over a real port, exercising filter registration. It is slower than `MockMvc`, but appropriate for verifying URL mappings/dispatcher types. In Spring Boot 4, test infrastructure/modules and `TestRestTemplate` APIs may change; this example uses Boot 3 as its baseline.

### 10.1. Testing ASYNC and ERROR Requires Dedicated Scenarios

To verify `ASYNC`:

- Create an MVC handler returning `Callable<String>` or `DeferredResult<String>` and ensure async is enabled across the entire servlet/filter chain.
- Register the filter for `DispatcherType.REQUEST` and `ASYNC`.
- If using `OncePerRequestFilter`, explicitly decide whether to override `shouldNotFilterAsyncDispatch()`.
- Log dispatcher type, thread ID, and request correlation ID per phase; assert the exact invocation count per the filter's contract.
- Test against a real embedded server and avoid relying on arbitrary timing.

To verify `ERROR`:

- Create an error scenario that goes through the **container error dispatch**, such as a Servlet with an appropriate error mapping.
- Ensure the filter maps `DispatcherType.ERROR` and the matching **error target URL**.
- If the filter extends `OncePerRequestFilter`, configure `shouldNotFilterErrorDispatch()`; verify the container's nested ERROR behavior.
- Do not rely solely on a `@RestControllerAdvice` returning 400/500 directly and conclude the container ran an ERROR dispatch.

To verify `INCLUDE`, use `RequestDispatcher.include(...)` per the Servlet API and verify filter registration/URL mapping; do not use Thymeleaf fragment inclusion expecting `DispatcherType.INCLUDE` to appear.

## 11. Spring Security Filter Chain and the Risk of Double Registration

In an application with Spring Security, the container typically sees one Servlet filter proxy (`DelegatingFilterProxy`) delegating to the `springSecurityFilterChain` bean. Inside `FilterChainProxy`, there are one or more `SecurityFilterChain` instances matching URLs according to Spring Security rules.

An example configuration (Java fragment for Spring Security 6.x):

```java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        ApiAuditFilter audit) throws Exception {

    http.securityMatcher("/api/**")
        .authorizeHttpRequests(registry ->
                registry.anyRequest().authenticated())
        .addFilterBefore(
                audit, UsernamePasswordAuthenticationFilter.class);

    return http.build();
}
```

This is a **fragment**, requiring the Spring Security dependency, corresponding imports, and an `ApiAuditFilter` bean. `addFilterBefore` operates inside the Spring Security chain, **not** via `FilterRegistrationBean#setOrder`.

If `ApiAuditFilter` is a Spring bean and implements `Filter`, Spring Boot may **auto-register** it as a Servlet filter. In that case, the same audit logic could execute:

1. Once in the container chain auto-registered by Boot.
2. Once inside the Spring Security chain via `addFilterBefore`.

A technique to prevent Servlet auto-registration when a filter is used **only inside Spring Security**:

```java
@Bean
FilterRegistrationBean<ApiAuditFilter> disableServletRegistration(
        ApiAuditFilter filter) {

    FilterRegistrationBean<ApiAuditFilter> registration =
            new FilterRegistrationBean<>(filter);
    registration.setEnabled(false);
    return registration;
}
```

This is a fragment inside `@Configuration`, requiring an application-defined `ApiAuditFilter`. When filters have custom registrations or multiple contexts, verify actual auto-registration behavior and ensure you do not disable an intended registration of your own.

**CORS consideration:** `OPTIONS` preflight requests may not carry session cookies/credentials, so CORS must be handled **before the relevant security authorization layer**. In an app with Spring Security, use Security and MVC's built-in CORS support (or a properly ordered CORS filter) and avoid conflicting sources of CORS headers.

**CSRF consideration:** the Servlet filter chain and security chain affect state-changing HTTP methods; do not arbitrarily disable CSRF protection just because a custom filter encounters a 403.

## 12. Request/Response Wrappers and Filter Order

A filter can wrap the request/response:

```java
HttpServletRequest wrapped =
        new HttpServletRequestWrapper(originalRequest) {
            // Override methods as needed for the use case.
        };

chain.doFilter(wrapped, response);
```

This is a **fragment**, requiring `HttpServletRequestWrapper` and the `originalRequest` variable. A wrapper can add headers, cache the body, or alter how downstream views the request. If placed too late, an earlier filter has already read the raw data; if placed too early without proper encoding alignment, it can break decoding.

Key concerns:

- **Character encoding:** determine the charset **before anything reads parameters/body**; setting encoding after the body has been read does not fix already-decoded data.
- **HTTP body stream:** a normal request body can only be read once unless a proper caching wrapper is used; do not log sensitive data, and do not read the entire body unconditionally.
- **Forwarded headers:** `ForwardedHeaderFilter` can wrap the request so downstream sees the scheme/host/prefix passed by a reverse proxy. This filter must run before components that rely on the forwarded view; trust headers only from safely configured proxies.
- **`ContentCachingRequestWrapper`:** only caches bytes **after downstream reads them**; do not assume that merely wrapping immediately makes the full body available. Mind memory usage and max payload limits.
- **Async & ERROR:** wrappers may be replaced or behave differently when dispatches occur on another thread or in a nested ERROR; check base filter support for `doFilterNestedErrorDispatch` if wrapper semantics must be preserved.
- **Response wrapper:** the response may already be committed; do not attempt to read/alter bytes after `chain.doFilter` without a proper buffering design and size bounds.

A custom filter that only needs a correlation ID usually should not wrap the entire body; setting a header/request attribute or logging MDC in the right scope is sufficient.

## 13. Logging and Diagnosing the Filter Chain

To diagnose a filter running in the wrong order, log at a minimum:

- Filter name and registration order (at startup).
- Dispatcher type: `request.getDispatcherType()`.
- HTTP method, request URI, servlet path, and context path.
- Correlation ID issued by the server or trusted infrastructure.
- Thread name/ID if investigating ASYNC.
- `before`/`after` events and elapsed time.
- Categorized error details without exposing tokens/session IDs/sensitive bodies.

In Boot 3 you can enable:

```properties
logging.level.web=debug
```

Per Boot documentation, this is helpful for seeing filter registrations at startup, including order/URL mappings. Specific logger packages for the Servlet container and Spring Security may be needed to inspect runtime chain details; do not enable global DEBUG/TRACE in production due to overhead and risk of logging sensitive data.

### 13.1. Symptoms and Causes

| Symptom | Common Cause | How to Verify |
| --- | --- | --- |
| Filter never runs | Not registered, registration disabled, or wrong URL pattern | Startup logs and request to matching URL |
| Filter runs on normal GET, not on forward | Registration does not map FORWARD or `OncePerRequestFilter` skips nested dispatch | Log dispatcher type and target URL |
| Filter does not run on `/error` | Mapped only to REQUEST or URL does not match `/error` | Register ERROR + error target mapping, test container |
| Filter does not run on async completion | Missing ASYNC mapping, asyncSupported false, OncePerRequestFilter skip | Check both registration and overrides |
| Filter runs twice per request | Auto-registration + Security chain or multiple registrations | List registrations, security chains, filter IDs |
| Wrong URL written in Location behind proxy | Forwarded header filter running in wrong order/trust config | Compare external request vs internal view |
| 401/403 before controller runs | Security filter chain rejected request | Debug security matchers and authentication |
| 400 from unexpected body parsing | Body read before converter or wrong encoding | Check filter body wrappers/order |
| Request never reaches controller, client “hangs” | Filter forgot `chain.doFilter` or failed to write response | Trace before/after and breakpoints |
| ThreadLocal holds data from previous user | Not cleared in `finally` or thread reused | Audit MDC context lifetime |
| Fails only in cluster, not reproducible locally | Singleton/local filter state, different session store | Check node IDs, sticky sessions, shared state |

### 13.2. How to Isolate the Issue

1. Confirm whether the request **reached the Servlet container** or was blocked earlier by a gateway/WAF.
2. Print the list of filter registrations and URL patterns.
3. Log `DispatcherType` in the first filter rather than inferring from the HTTP method.
4. If using Spring Security, log the matching `SecurityFilterChain`.
5. If the bug happens on forward/error/async, write an integration test using the corresponding dispatch.
6. Verify the filter calls `chain.doFilter` properly and cleans up `ThreadLocal` in `finally`.
7. Inspect response status/headers/body **before deciding which layer handled the error**.
8. Compare the embedded container in dev/test with the production container/proxy if the two environments differ.

## 14. When to Use Filter, Interceptor, or ControllerAdvice?

| Problem | Usually Appropriate Choice | Explanation |
| --- | --- | --- |
| Character encoding, HTTP wrappers, request correlation at ingress | Servlet Filter | Needed before MVC handler |
| Authentication/authorization | Spring Security filter chain | Dedicated security mechanism |
| CORS | Built-in Spring MVC/Spring Security CORS or properly ordered CorsFilter | Must handle OPTIONS before auth properly |
| Supplying model attributes for views | `@ModelAttribute` method | MVC model, no filter needed |
| Decisions based on selected handler, auditing handler name | `HandlerInterceptor` | Has MVC handler context |
| Validating DTO/request body | `@Valid`/`@Validated` + controller/service validation | Should not arbitrarily deserialize JSON in a filter |
| Translating MVC/domain exceptions into HTTP errors | `@RestControllerAdvice` / `ResponseEntityExceptionHandler` | Centralizes error contract |
| Handling Security authentication failures | `AuthenticationEntryPoint` / `AccessDeniedHandler` | Lives at the appropriate filter layer |
| Passing internal context between methods | Explicit parameters or request attributes | Avoid ThreadLocal abuse |
| Tracking async/error across dispatches | Servlet Filter with appropriate dispatcher mapping + lifecycle | Not just a simple REQUEST interceptor |

**Do not place core business logic or heavy DB queries into every Servlet Filter** when only one endpoint needs them. Filters should focus on HTTP-level cross-cutting concerns; restrict their scope to avoid impacting health checks, static files, and error pages.

## 15. Spring Framework / Boot Differences by Version

| Platform | Filter Registration / Dispatch Notes |
| --- | --- |
| Spring Framework 5.x + Boot 2.x | Servlet Filter API is typically `javax.servlet.*`; `OncePerRequestFilter` and `FilterRegistrationBean` already exist |
| Spring Framework 6.x + Boot 3.x | Java 17+, Jakarta Servlet `jakarta.servlet.*`; `FilterRegistrationBean`/`OncePerRequestFilter` work as shown in examples |
| Spring Framework 7.x + Boot 4.x | Servlet filter semantics and `OncePerRequestFilter` continue to exist; Boot 4 adjusts modules, starters, registration annotations, and test infrastructure; consult the Javadoc/BOM of the exact version in use |

Across all versions, **Servlet spec dispatcher types** do not turn `REQUEST` into `ASYNC` merely because code uses `CompletableFuture`. The application must actually trigger Servlet asynchronous processing for an ASYNC redispatch to occur.

A common change when migrating Boot 2 → Boot 3: imports `javax.servlet.Filter` and `javax.servlet.DispatcherType` must change to `jakarta.servlet.*`. Changes in Jackson, validation, or Spring Security dependencies can affect other filters, so after upgrading, verify filter registration, order, URL mappings, and dispatcher types with real tests.

## 16. Production Readiness Checklist for Filters

- [ ] URL/Servlet registration scope is constrained to what is needed; do not default every filter to `/*`.
- [ ] Order is explicit when dependencies exist; do not rely on equal filter orders.
- [ ] Clear whether a filter belongs to the Servlet chain or Spring Security chain; no double registration.
- [ ] `DispatcherType.REQUEST`/`FORWARD`/`INCLUDE`/`ASYNC`/`ERROR` are chosen deliberately.
- [ ] If ASYNC is required, configure async support and `OncePerRequestFilter` policy per thread/dispatch.
- [ ] If ERROR is required, map the error dispatch target as well; verify nested error cases.
- [ ] Filter always calls `chain.doFilter` unless intentionally completing the response.
- [ ] ThreadLocals/MDC/resource cleanup uses `try/finally`, with no leaks across requests.
- [ ] Response headers are never modified after the response is committed.
- [ ] Encoding/body wrappers are placed correctly, memory-bounded, and avoid logging secrets.
- [ ] Forwarded headers are trusted only from configured proxies; auth/CORS/Security order is verified.
- [ ] Tests cover normal, forward, async, and error requests whenever those dispatches are part of the contract.
- [ ] Order/registration is verified against a real container in at least key integration tests.
- [ ] Logging/tracing allows tracing dispatcher type, filter name, and production errors.

## 17. Practice Exercises

1. In the app from Section 9, change A's `registration.setOrder(10)` to `30`. What changes in the body of `GET /api/filters/echo`? Why does the return path after the chain (if recorded) run in reverse?
2. Remove `DispatcherType.FORWARD` from A and call `/api/filters/forward`. What event sequence remains? Test on a real server.
3. Replace A with a `OncePerRequestFilter` subclass. In a nested forward inside `chain.doFilter`, why might `doFilterInternal` **not** run a second time even when the registration includes FORWARD?
4. Register A mapped only to `/api/filters/*` with ERROR mapped. An exception leads to the `/error` page. Why might A not run on the error dispatch?
5. Add a `Callable<String>` controller and an async-aware filter. Distinguish `setAsyncSupported`, ASYNC dispatcher mapping, and `shouldNotFilterAsyncDispatch()`.
6. A filter implementing `Filter` is a Spring bean and is added to `HttpSecurity.addFilterBefore`. Why is there a risk of double execution? Disable container registration while keeping the security chain.
7. Place a body-reading filter at a very low order before the character encoding filter. What bugs can appear with UTF-8 form data?
8. Test with both `MockMvc` and `@SpringBootTest(RANDOM_PORT)`. Which is better suited to prove Servlet container registration for FORWARD/ERROR? Why?
9. Add `RequestDispatcher.include(...)` in a Servlet. When will a filter mapping INCLUDE run, and how does this differ from Thymeleaf template fragments?
10. If a filter does not call `chain.doFilter`, what must it do to avoid an incomplete response? Give one valid blocking example and one bug case.
11. Distinguish `HandlerInterceptor#preHandle`, Servlet Filter `doFilter`, and Spring Security `SecurityFilterChain` in an app that has all three.
12. Design a correlation ID recorded in REQUEST and also ERROR dispatches without leaking to other threads/clients; explain cleanup via `finally`.

## 18. Official References

- [Spring Framework 6.2 — Servlet Filters](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html): filter chains, built-in filters, wrappers, forwarded headers, and dispatches.
- [Spring Framework 6.2 — OncePerRequestFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html): already-filtered marker, async/error skipping, and nested ERROR dispatches.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): Servlet filter beans, order, registration, and startup debug logging.
- [Spring Boot 3.5 — FilterRegistrationBean Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/FilterRegistrationBean.html): URL patterns, order, Servlet registrations, dispatcher types.
- [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): dispatcher type defaults and filter registration.
- [Spring Security — Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): FilterChainProxy, SecurityFilterChain, and order.
- [Spring Security — Servlet CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): ordering of CORS and Spring Security.
- [Jakarta Servlet Specification](https://jakarta.ee/specifications/servlet/6.0/): Servlet Filter, dispatcher types, request dispatch, and async handling.
