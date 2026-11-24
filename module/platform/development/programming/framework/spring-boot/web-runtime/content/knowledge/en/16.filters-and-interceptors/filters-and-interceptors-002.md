# FilterRegistrationBean, Filter Ordering, and URL Scope in Spring Boot

## 1. Context and Objectives

In a Spring Boot **Servlet/Spring MVC** application, an HTTP request passes through a chain of `jakarta.servlet.Filter` instances managed by the Servlet container before reaching `DispatcherServlet`. A Filter can inspect or modify the request/response, short-circuit the request early, add headers, or record metrics. Implementing `doFilter` properly is **not enough**: if registered incorrectly, a filter may run on every URL, run in an unfavorable order relative to encoding/security, or be invoked multiple times.

`FilterRegistrationBean` directly addresses three questions:

1. **Scope:** Does the filter run on `/api/ping`, `/public/ping`, `/error`, or other servlets?
2. **Order:** When two filters match the same request, which filter runs first and which runs second?
3. **Dispatch types and lifecycle:** Which `REQUEST`, `ASYNC`, or `ERROR` dispatches does the filter handle, and is it accidentally auto-registered twice?

After this lesson, you will be able to use `addUrlPatterns("/api/*")`, `setOrder(...)`, and `setDispatcherTypes(...)`, avoid confusing Servlet `/api/*` with Spring MVC `/api/**`, distinguish Filters from Interceptors and Spring Security, and verify behavior on a real embedded HTTP server.

The examples use **Spring Boot 3.5.16 + Java 17+ + Spring MVC** with embedded Tomcat. The examples form a complete Maven application and `@SpringBootTest(RANDOM_PORT)` test suite. Spring Boot 3.5.16 is the final OSS release of the 3.5 branch; production workloads should use a supported release line with security patches.

## 2. Where Does Servlet Filter Sit?

~~~text
HTTP client
    |
    v
Servlet container (Tomcat, Jetty, Undertow)
    |
    +-- Filter A: before
    |      |
    |      +-- Filter B: before
    |      |      |
    |      |      +-- DispatcherServlet
    |      |              |
    |      |              +-- HandlerMapping
    |      |              +-- MVC HandlerInterceptor.preHandle
    |      |              +-- Controller
    |      |              +-- MVC afterCompletion
    |      |
    |      +-- Filter B: after
    |
    +-- Filter A: after
    |
    v
HTTP response
~~~

Servlet `Filter` declares `doFilter`. Example:

~~~java
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain) throws IOException, ServletException {

    // Logic before downstream filters/Servlet.
    chain.doFilter(request, response);
    // Logic after downstream completes normally.
}
~~~

The snippet above is an **illustrative method**, requiring the interface, imports, and enclosing class to compile. Key points:

- `chain.doFilter` forwards the request to the next filter or servlet; if not called, downstream logic is blocked. A Filter can intentionally return an error, provided it sets an appropriate status/body.
- With two nested filters, logic before `chain.doFilter` runs in order A→B; logic after `chain.doFilter` runs B→A if downstream completes normally.
- If downstream throws an exception, code after `chain.doFilter` does not automatically run; use `try/finally` when cleanup is required.
- A Filter can be invoked for requests that do not match a controller, static resources, or error dispatches, **provided** the URL mapping and dispatcher type match.
- A Filter can wrap `ServletRequest`/`ServletResponse`, but must properly preserve encoding, input streams, and async lifecycle.

### Filter vs. HandlerInterceptor and WebFilter

| Component | Execution Layer | Matching and Ordering | Typical Usage |
|---|---|---|---|
| Servlet `Filter` | Servlet container, before `DispatcherServlet` | Servlet URL/servlet-name/dispatcher mapping; registration order | Headers, request wrappers, cross-cutting concerns before MVC |
| MVC `HandlerInterceptor` | Spring MVC handler chain | `InterceptorRegistration` path patterns/order | Logic tied to an MVC handler |
| Spring Security servlet filter | `FilterChainProxy` inside Servlet filter chain | Security `RequestMatcher`, `HttpSecurity` filter order | Authentication, authorization, CSRF |
| WebFlux `WebFilter` | Reactive WebFlux | `WebFilterChain`, `Ordered` | Reactive filters; **do not** use FilterRegistrationBean |

Do not use Servlet `FilterRegistrationBean` to register WebFlux's `org.springframework.web.server.WebFilter`; they belong to two different stacks. Nor does `HandlerInterceptor` replace every effect of a Servlet filter across other servlets or raw bodies.

## 3. Three Ways to Register a Filter and When to Choose FilterRegistrationBean

### 3.1. Creating Only a Filter Spring Bean

~~~java
@Bean
Filter myFilter() {
    return new MyFilter();
}
~~~

This is an **illustrative method** requiring a `MyFilter` class and Spring configuration. In an embedded Servlet application, Spring Boot automatically detects `Filter` beans and registers them with the container. Without a restricted mapping, the filter is typically mapped to `/*`: every request path in the context.

Advantage: simple. Disadvantage: easy to over-apply when the filter should only handle `/api/*`. Naming the bean `apiFilter` **does not automatically create** URL scoping.

### 3.2. FilterRegistrationBean

In Boot 3.5:

~~~java
import org.springframework.boot.web.servlet.FilterRegistrationBean;
~~~

`FilterRegistrationBean<T extends Filter>` is a `ServletContextInitializer` and `Ordered`. It serves as an adapter between a Filter instance and a Servlet registration.

| API | Purpose |
|---|---|
| `new FilterRegistrationBean<>(filter)` | Select the Filter instance |
| `setFilter(filter)` | Set the instance after using the no-arg constructor |
| `setName("name")` | Name of the Servlet filter registration |
| `addUrlPatterns("/api/*")` | Restrict URLs per the Servlet specification |
| `setUrlPatterns(collection)` | Set the URL pattern collection |
| `addServletNames("name")` | Associate with a servlet by name |
| `setOrder(10)` | Registration order |
| `setDispatcherTypes(REQUEST)` | Servlet dispatch types to handle |
| `setAsyncSupported(true)` | Filter registration supports async |
| `setMatchAfter(true)` | Mapping position relative to declared mappings |
| `setEnabled(false)` | Disable Servlet registration for the filter |
| `addInitParameter("k","v")` | Provide an init parameter |

If no URL/servlet mapping is provided, the filter defaults to `/*` per its javadoc. Therefore `addUrlPatterns` is crucial when you do not want to affect the entire application.

Example configuration method:

~~~java
@Bean
FilterRegistrationBean<MyFilter> myFilterRegistration() {
    FilterRegistrationBean<MyFilter> bean =
            new FilterRegistrationBean<>(new MyFilter());
    bean.setName("myApiFilter");
    bean.addUrlPatterns("/api/*");
    bean.setOrder(50);
    bean.setDispatcherTypes(DispatcherType.REQUEST);
    return bean;
}
~~~

This is **illustrative** code, requiring imports for `jakarta.servlet.DispatcherType`, `FilterRegistrationBean`, Spring `@Bean`, and class `MyFilter`. The demo in Section 8 provides complete files.

### 3.3. Other Registration Annotations

- `@Component` on a Filter makes it a Spring bean; Boot can auto-register it by convention.
- `@WebFilter` belongs to the Servlet API; in an embedded app, `@ServletComponentScan` can be used to scan Servlet components.
- `@FilterRegistration` in Spring Boot 3.5 is an annotation-based alternative to `FilterRegistrationBean`, supporting attributes such as order, URL patterns, and dispatcher types.
- Do not combine multiple registration paths for the same Filter without verifying whether they create **two registrations**.

Use `FilterRegistrationBean` when you want explicit code-level review of URL scope and order.

## 4. Servlet URL Patterns Are Not Spring MVC Patterns

`addUrlPatterns(...)` follows the **Servlet specification**, and does not understand Ant-style `**` or Spring MVC's `PathPatternParser`.

| Servlet URL pattern | Interpretation | Example |
|---|---|---|
| `/*` | Every path in the web app context | `/api/a`, `/public/a` |
| `/api/*` | Path prefix `/api` and its subpaths | `/api/ping`, `/api/v1/ping` |
| `/health` | Exact path | `/health` |
| `*.json` | Extension mapping | Target paths ending with `.json` |
| `/` | Default Servlet mapping, distinct semantics | Do not treat as globally equivalent to `/*` |
| `/api/**` | **Not a standard Servlet prefix pattern** | Do not use with `addUrlPatterns` |

Use:

~~~java
registration.addUrlPatterns("/api/*");
~~~

do not use:

~~~java
// Wrong expectation: Servlet does not have Spring MVC's "**" semantics.
registration.addUrlPatterns("/api/**");
~~~

The container may reject invalid patterns or fail to interpret them as expected. Never build security rules on non-standard patterns.

### Multiple Patterns, Exact Paths, and No Exclusions

You can add multiple prefixes:

~~~java
registration.addUrlPatterns("/api/*", "/internal/*");
~~~

Or exact paths:

~~~java
registration.addUrlPatterns("/auth/login", "/auth/logout");
~~~

There is no negation syntax like `!/api/public/*` to exclude a subpath. For a Filter that wants to skip a path already matched by the container, you can use `OncePerRequestFilter.shouldNotFilter`; however, if that represents a security boundary, use Spring Security matchers rather than trusting manual `startsWith` checks.

### Context Path

If:

~~~properties
server.servlet.context-path=/shop
~~~

The external HTTP URL may be `/shop/api/ping`, yet the Servlet filter mapping within the application context is still written as `/api/*`. `request.getRequestURI()` generally includes the context path, whereas filter mappings operate relative to the application context. Do not accidentally prepend `/shop` to `addUrlPatterns`.

### HTTP Method and Query String

Patterns evaluate the path, not `?page=2` or GET/POST. Both GET `/api/ping` and POST `/api/orders` pass through `/api/*` if the dispatcher type matches. If you want the filter to act only on POST, check `HttpServletRequest.getMethod()` inside the filter, or choose another mechanism at the appropriate layer.

### By Servlet Name

`FilterRegistrationBean` also supports servlet name mapping. This is useful when an app has multiple servlets; the filter applies only to the specified servlet. Do not equate a Servlet name with an MVC controller name or a service bean name.

## 5. Filter Order: Lower setOrder Runs First

Filter A and B both match the same request:

~~~java
firstRegistration.setOrder(10);
secondRegistration.setOrder(20);
~~~

When Boot sorts registrations it manages, a lower order value has higher precedence. Typical flow:

~~~text
Request -> FIRST before -> SECOND before -> Controller
Response <- FIRST after  <- SECOND after  <- Controller
~~~

To be precise about the return path: the controller returns to SECOND first, and SECOND returns to FIRST; code after `chain.doFilter` in SECOND runs before code after `chain.doFilter` in FIRST.

**Important notes:**

1. When order matters, use distinct order numbers rather than relying on bean names or method declaration order.
2. `@Order` on the **Filter class** or `Ordered` on a filter bean can participate in ordering when Boot auto-registers it. However, Boot documentation explicitly states **`@Order` placed on a `@Bean` method creating a Filter is not used to configure Servlet filter order**.
3. When you do not control the Filter class, use `FilterRegistrationBean.setOrder(...)`.
4. `setMatchAfter(true)` affects placing the mapping after declared filter mappings on the `ServletContext`; it **does not replace** `setOrder`.
5. An application has Servlet filters coming from Boot, third parties, WAR containers, Security proxies, and `web.xml`; do not treat two order numbers as a complete guarantee of global ordering. Observe startup logs and test at runtime.

### Filter Wrappers and Character Encoding

Spring Boot warns against running a filter that reads the request body too early at `Ordered.HIGHEST_PRECEDENCE` because it may run before character encoding is configured. When wrapping requests, Boot's guidance mentions:

~~~java
OrderedFilter.REQUEST_WRAPPER_FILTER_MAX_ORDER
~~~

A wrapper filter should have an order less than or equal to this constant when appropriate. Do not place every custom filter at `HIGHEST_PRECEDENCE` just to "make sure it runs first": doing so can break encoding, CORS, security, or body handling.

In the demo, FIRST/SECOND neither wrap nor read the body; orders 10/20 simply illustrate the order **between them**.

## 6. DispatcherType and Async Lifecycle

Servlets define these dispatcher types:

| DispatcherType | Meaning |
|---|---|
| `REQUEST` | Initial request from the HTTP client |
| `FORWARD` | Forward via RequestDispatcher |
| `INCLUDE` | Include content of another servlet |
| `ASYNC` | Async redispatch, potentially on a different thread |
| `ERROR` | Servlet error dispatch to an error page/servlet |

Selecting REQUEST:

~~~java
registration.setDispatcherTypes(DispatcherType.REQUEST);
~~~

To also include ERROR:

~~~java
registration.setDispatcherTypes(
        DispatcherType.REQUEST,
        DispatcherType.ERROR);
~~~

Crucially: **both the dispatcher type and the URL mapping must match**. When an error dispatches to `/error`, a filter mapped only to `/api/*` may **not run** on the ERROR dispatch, even if `DispatcherType.ERROR` is enabled. Always verify the actual dispatch target and Servlet container behavior.

According to Boot 3.5 documentation, registrations that do not specify dispatcher types generally default to `REQUEST`, aligning with the Servlet specification.

### setAsyncSupported Does Not Automatically Add DispatcherType.ASYNC

~~~java
registration.setAsyncSupported(true);
registration.setDispatcherTypes(DispatcherType.REQUEST);
~~~

`asyncSupported(true)` only states that the registration supports async. It does not request execution during an `ASYNC` dispatch. To participate in redispatches, register `ASYNC` and design the filter for thread safety, MDC/tracing cleanup, and avoiding writing the response twice.

### OncePerRequestFilter

`org.springframework.web.filter.OncePerRequestFilter` helps guard execution via a request attribute. However, do not interpret the class name to mean the entire HTTP request runs **only once ever** under all circumstances:

- REQUEST/ASYNC/ERROR can happen at different times or on different threads.
- `shouldNotFilterAsyncDispatch()` and `shouldNotFilterErrorDispatch()` adjust behavior for those dispatch types.
- `setDispatcherTypes` on the registration remains a Servlet container condition.
- `shouldNotFilter(HttpServletRequest)` lets you skip logic for requests within a broad registration scope.
- If a filter is registered in two independent chains, `OncePerRequestFilter` is no substitute for fixing duplicate registration.

Illustrative subclass methods:

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

These two methods **do not form a standalone class**; when you want execution during ASYNC/ERROR, adjust both the registration and implementation, then test the lifecycle.

## 7. Double Registration, SecurityFilterChain, and Early Initialization

### 7.1. Avoid Unintentionally Registering a Filter in Multiple Places

For example, a `@Component` Filter can be auto-registered by Boot into the Servlet container. If you also add the same filter to Spring Security `HttpSecurity`, or use `@WebFilter` alongside Servlet component scanning, the filter can run multiple times or with the wrong scope.

A `FilterRegistrationBean` bound to that exact filter bean can be used by Boot to control the corresponding auto-registration. However, it does not automatically remove registrations from third parties or the Servlet container. When debugging, list every registration source.

The demo creates `new TraceFilter(...)` **directly inside the registration bean**, without marking TraceFilter as `@Component` or `@WebFilter`, avoiding a separate registration path.

### 7.2. Two Layers of Ordering with Spring Security

~~~text
Servlet FilterChain
    |
    +-- Custom Servlet FilterRegistrationBean
    |
    +-- DelegatingFilterProxy ("springSecurityFilterChain")
           |
           +-- FilterChainProxy
                   |
                   +-- SecurityFilterChain selected by RequestMatcher
                            |
                            +-- authentication filters
                            +-- authorization filters
                            +-- CSRF and related filters
    |
    v
DispatcherServlet
~~~

`FilterRegistrationBean.setOrder` affects registration in the **Servlet container**. `HttpSecurity.addFilterBefore`, `addFilterAfter`, and `addFilterAt` affect ordering **inside SecurityFilterChain**. Some Spring Security positions are framework-defined; do not deduce that Servlet Filter order 10 means "after AuthenticationFilter" without inspecting the actual chain.

If a custom filter needs the authenticated principal, it normally belongs at an appropriate position **inside SecurityFilterChain**. If a custom Servlet Filter runs before security, `SecurityContext` may not contain a principal yet. Do not use FilterRegistrationBean URL mappings in place of an authorization policy.

### 7.3. Disabling Servlet Registration When a Filter Is Security-Only

For a `@Bean` filter meant only for Spring Security, you can disable container registration as follows:

~~~java
@Bean
FilterRegistrationBean<MySecurityFilter> disableContainerRegistration(
        MySecurityFilter filter) {
    FilterRegistrationBean<MySecurityFilter> bean =
            new FilterRegistrationBean<>(filter);
    bean.setEnabled(false);
    return bean;
}
~~~

This is an illustrative snippet, omitting `MySecurityFilter` and Spring Security configuration. `setEnabled(false)` does not remove the filter bean; it only disables its corresponding Servlet container registration. The filter can still be managed by `HttpSecurity` in the security chain.

### 7.4. Very Early Filter Initialization

Servlet filters are registered early during container startup. Injecting a DataSource, JPA repository, or service with constructor side effects can cause premature initialization and startup failures. Boot advises considering lazy lookups or `DelegatingFilterProxyRegistrationBean` for filters that collaborate with many Spring beans. Do not run database migrations or network calls inside a filter constructor.

## 8. Complete Hands-On Project: Two Filters, Ordering, and URL Scope

The project uses a single `TraceFilter` class instantiated multiple times. Two registrations are configured:

- FIRST: `setOrder(10)`, URL `/api/*`, dispatcher `REQUEST`.
- SECOND: `setOrder(20)`, same URL `/api/*`, dispatcher `REQUEST`.

The controller exposes three routes:

| Route | Expected Body | Expected X-Filter-Trace Header |
|---|---|---|
| `/api/ping` | `api:FIRST>SECOND` | `FIRST>SECOND` |
| `/api/v1/ping` | `nested:FIRST>SECOND` | `FIRST>SECOND` |
| `/public/ping` | `public:none` | Header absent |

The demo header is evidence of execution order; **do not use it** as a security token or trusted request ID in production.

### 8.1. File Structure

~~~text
servlet-filter-demo/
  pom.xml
  src/main/java/com/example/filterdemo/
    FilterDemoApplication.java
    TraceFilter.java
    FilterConfiguration.java
    PingController.java
  src/test/java/com/example/filterdemo/
    FilterRegistrationIntegrationTest.java
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>servlet-filter-demo</artifactId>
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

The Spring Boot parent manages compatible Tomcat/Jakarta Servlet/JUnit dependency versions. Spring Security is omitted from the demo so we can observe pure Servlet registration; real integrations must also check the Security chain.

### 8.3. Main Class

File `src/main/java/com/example/filterdemo/FilterDemoApplication.java`:

~~~java
package com.example.filterdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterDemoApplication.class, args);
    }
}
~~~

### 8.4. TraceFilter.java

File `src/main/java/com/example/filterdemo/TraceFilter.java`:

~~~java
package com.example.filterdemo;

import java.io.IOException;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

public final class TraceFilter implements Filter {
    private final String marker;

    public TraceFilter(String marker) {
        this.marker = marker;
    }

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain) throws IOException, ServletException {

        HttpServletRequest httpRequest = (HttpServletRequest) request;
        HttpServletResponse httpResponse = (HttpServletResponse) response;

        Object previous = httpRequest.getAttribute("filter.trace");
        String trace = previous == null
                ? marker
                : previous + ">" + marker;

        httpRequest.setAttribute("filter.trace", trace);
        httpResponse.setHeader("X-Filter-Trace", trace);

        chain.doFilter(request, response);
    }
}
~~~

When FIRST runs, the `filter.trace` request attribute becomes `FIRST`; when SECOND runs, it becomes `FIRST>SECOND`. The `marker` field is immutable, and per-request data is stored in a **request attribute**, not in a mutable field of a singleton Filter. Because the demo runs in a Servlet HTTP app, casting to HTTP request/response is valid.

### 8.5. FilterConfiguration.java

File `src/main/java/com/example/filterdemo/FilterConfiguration.java`:

~~~java
package com.example.filterdemo;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FilterConfiguration {

    @Bean
    FilterRegistrationBean<TraceFilter> firstTraceFilter() {
        FilterRegistrationBean<TraceFilter> registration =
                new FilterRegistrationBean<>(new TraceFilter("FIRST"));

        registration.setName("firstTraceFilter");
        registration.addUrlPatterns("/api/*");
        registration.setOrder(10);
        registration.setDispatcherTypes(DispatcherType.REQUEST);
        return registration;
    }

    @Bean
    FilterRegistrationBean<TraceFilter> secondTraceFilter() {
        FilterRegistrationBean<TraceFilter> registration =
                new FilterRegistrationBean<>(new TraceFilter("SECOND"));

        registration.setName("secondTraceFilter");
        registration.addUrlPatterns("/api/*");
        registration.setOrder(20);
        registration.setDispatcherTypes(DispatcherType.REQUEST);
        return registration;
    }
}
~~~

The two `TraceFilter` instances have different registration names. They are not `@Component`s and there is no standalone `TraceFilter` Spring bean. When a request matches `/api/*` and `REQUEST`, FIRST with order 10 runs before SECOND with order 20. Omitting `addUrlPatterns` could widen the scope to `/*`.

### 8.6. PingController.java

File `src/main/java/com/example/filterdemo/PingController.java`:

~~~java
package com.example.filterdemo;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/api/ping")
    public String api(HttpServletRequest request) {
        return "api:" + trace(request);
    }

    @GetMapping("/api/v1/ping")
    public String nested(HttpServletRequest request) {
        return "nested:" + trace(request);
    }

    @GetMapping("/public/ping")
    public String publicPing(HttpServletRequest request) {
        return "public:" + trace(request);
    }

    private static String trace(HttpServletRequest request) {
        Object value = request.getAttribute("filter.trace");
        return value == null ? "none" : value.toString();
    }
}
~~~

All three endpoints are Spring MVC routes. The `/public/ping` controller does not receive the attribute because the Servlet container **does not** invoke filters mapped exclusively to `/api/*`.

### 8.7. Running and Verifying with curl

Requires Java 17+ and Maven. In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Once the application listens on port 8080, try:

~~~bash
curl -i http://localhost:8080/api/ping
curl -i http://localhost:8080/api/v1/ping
curl -i http://localhost:8080/public/ping
~~~

Expect status **200** for all three; body and headers as in the table at the top of Section 8. `curl -i` prints both headers and body. String response bodies do not automatically include a trailing newline; do not mistake terminal line wrapping for controller behavior.

### 8.8. Testing on a Real Embedded Server — Java 17 Compatible

**Why not just MockMvc?** `MockMvc` tests the Spring MVC pipeline, not a real container. Filter auto-discovery in tests can differ from URL registration/dispatcher semantics in embedded Tomcat. Use `@SpringBootTest(RANDOM_PORT)` with real HTTP requests to verify filter order and scope.

File `src/test/java/com/example/filterdemo/FilterRegistrationIntegrationTest.java`:

~~~java
package com.example.filterdemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FilterRegistrationIntegrationTest {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newHttpClient();

    private HttpResponse<String> get(String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://127.0.0.1:" + port + path))
                .GET()
                .build();

        return client.send(request,
                HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void apiFiltersRunInOrder() throws Exception {
        HttpResponse<String> result = get("/api/ping");

        assertEquals(200, result.statusCode());
        assertEquals("api:FIRST>SECOND", result.body());
        assertEquals("FIRST>SECOND",
                result.headers()
                        .firstValue("X-Filter-Trace").orElse(""));
    }

    @Test
    void servletPrefixPatternMatchesNestedApiPath() throws Exception {
        HttpResponse<String> result = get("/api/v1/ping");

        assertEquals(200, result.statusCode());
        assertEquals("nested:FIRST>SECOND", result.body());
        assertEquals("FIRST>SECOND",
                result.headers()
                        .firstValue("X-Filter-Trace").orElse(""));
    }

    @Test
    void publicUrlIsOutsideRegisteredFilterScope() throws Exception {
        HttpResponse<String> result = get("/public/ping");

        assertEquals(200, result.statusCode());
        assertEquals("public:none", result.body());
        assertTrue(result.headers()
                .firstValue("X-Filter-Trace").isEmpty());
    }

    @Test
    void embeddedServerAllocatedPort() {
        assertTrue(port > 0);
    }
}
~~~

This code is **Java 17 compatible**: `HttpClient.newHttpClient()` is not wrapped in try-with-resources; in JDK 17, `HttpClient` does not yet implement `AutoCloseable`. All test HTTP calls target the port provided by `@LocalServerPort`, never assuming a fixed port 8080.

Run:

~~~bash
mvn test
~~~

When Maven Wrapper is present, use `./mvnw test` (Windows: `mvnw.cmd test`). The tests state expected outcomes from the sample code; in practice, run them in your project's build environment to confirm dependencies and network access.

## 9. Common Extensions

### 9.1. Specific Endpoints Only

~~~java
registration.addUrlPatterns("/auth/login", "/auth/logout");
~~~

These are exact Servlet paths. They do not restrict HTTP methods, do not support `{id}` syntax like Spring MVC, and do not replace authentication.

### 9.2. Skipping a Subpath Under /api

You can map `/api/*` broadly, and then in a `OncePerRequestFilter` subclass:

~~~java
@Override
protected boolean shouldNotFilter(HttpServletRequest request) {
    String path = request.getServletPath();
    return path.equals("/api/public")
            || path.startsWith("/api/public/");
}
~~~

This is an excerpt, not part of the `TraceFilter` demo. Skipping via manual `startsWith` is only appropriate when you understand path normalization and servlet mapping. If the feature relates to authorization, use Spring Security matchers.

### 9.3. Filtering a Specific HTTP Method

Inside a `doFilter` that already has `HttpServletRequest httpRequest`:

~~~java
if (!"POST".equals(httpRequest.getMethod())) {
    chain.doFilter(request, response);
    return;
}
~~~

The container still invokes the filter on GET requests matching the URL; the code simply skips the business logic for GET.

### 9.4. Filter for ERROR or ASYNC

When execution on `ERROR` is needed, add the dispatcher type and verify the error target path. For `ASYNC`, review `asyncSupported`, `DispatcherType.ASYNC`, `OncePerRequestFilter.shouldNotFilterAsyncDispatch`, and cleanup/thread-local contexts. Do not double-count metrics because one request can go through multiple dispatches.

## 10. Debugging on a Real System

In test/local `application.properties`, you can enable:

~~~properties
logging.level.web=debug
~~~

Spring Boot will log the registered Servlet filters (order, URL patterns) at startup. When issues arise, check in order:

1. How was the Filter registered? Bean, FilterRegistrationBean, @WebFilter, @FilterRegistration, or Spring Security?
2. Is there an unintended `/*` registration?
3. Was `/api/*` used instead of `/api/**`?
4. Have context path, servlet mapping, and reverse proxy rewrites been accounted for?
5. Does the order collide or conflict with encoding/security filters?
6. Are there async/error redispatches? What are the dispatcher types?
7. Is the Filter invoked by both the Spring Security chain and the container?
8. Was the request body already read before MVC/Jackson processed it?
9. Does the Filter log secrets or personal information?
10. Do real-server integration tests cover both in-scope and out-of-scope URLs?

Debug logging can expose credentials, bodies, or queries; enable it only in appropriate environments and never log raw Authorization headers, cookies, or passwords.

## 11. Common Mistakes

| Symptom | Common Cause | Fix |
|---|---|---|
| Filter runs on public URLs too | Filter bean auto-mapped to `/*` by default | Specify `/api/*` via proper registration |
| Filter fails to match nested API | Used exact path or `/api/**` | Use Servlet prefix `/api/*` |
| Filter runs twice | Servlet registration + Security chain or Servlet component scan | Remove redundant registration, `setEnabled(false)` when Security-only |
| `@Order` does not change filter order | Annotation placed on `@Bean` method | Use `FilterRegistrationBean.setOrder` |
| Unstable order | Filters share the same order or another registration interferes | Use distinct order values and integration tests |
| ERROR dispatch skips filter | `ERROR` not selected or error URL does not match | Check both dispatcher type and path |
| Async redispatch skips filter | Only `REQUEST` configured or OncePerRequestFilter skips it | Configure both registration dispatchers and filter implementation |
| Security principal missing | Filter runs before authentication | Move filter into Security chain at the right position |
| HTTP 500 after request wrapper | Body read too early or wrong encoding | Use standard wrapper, check stream/order |
| Filter slows down startup | Heavy dependencies injected too early | Lazy lookup/DelegatingFilterProxyRegistrationBean |
| MockMvc passes but runtime fails | Tests bypass Servlet container registration semantics | Test with `RANDOM_PORT` over HTTP |
| Tokens leaked in logs | Filter logs entire request/headers | Allowlist logging and redact |

## 12. Code Review Checklist

- **Scope:** Are all URL patterns valid Servlet syntax, with tests for nested paths and unmatched paths?
- **Order:** If order matters, do filter registrations have explicit, non-colliding order values?
- **Lifecycle:** Is there accidental `@Component` + registration or double addition to the Security chain?
- **Dispatch:** Are REQUEST/ERROR/ASYNC specified per actual need and tested?
- **Security:** Does the filter run before/after authentication as intended? Are URL mappings not used as the sole authorization rule?
- **Encoding:** Do body-reading/wrapping filters run after proper encoding is determined?
- **Thread safety:** Does the filter avoid holding per-request data in mutable singleton fields?
- **Error handling:** When blocking a request, are status/body/headers correct and is the chain not invoked unintentionally?
- **Logging:** Are tokens, passwords, request bodies, and PII kept out of logs?
- **Testing:** Are there real-server tests rather than MockMvc alone?
- **Version:** For Spring Boot 4.x, have starters, modules, and API javadocs been verified for that exact version?

**Conclusion:** `FilterRegistrationBean` does more than simply "turn on a filter." It defines **which filter**, **which URL/servlet scope**, **what order**, and **which dispatches** apply. Accurately distinguishing Servlet URL patterns `/api/*` from Spring MVC `/api/**`, separating Servlet ordering from Spring Security ordering, avoiding duplicate registrations, and writing integration tests against a real container are the key principles.

## References

- Spring Boot 3.5.16 — Servlet Web Applications, registering filters: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5.16 — Embedded Web Servers, registering filters and dispatcher types: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Boot 3.5.16 API — FilterRegistrationBean: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/FilterRegistrationBean.html
- Spring Boot 3.5.16 API — AbstractFilterRegistrationBean: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/AbstractFilterRegistrationBean.html
- Spring Boot 3.5.16 API — RegistrationBean: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/RegistrationBean.html
- Spring Boot 3.5.16 API — FilterRegistration annotation: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/FilterRegistration.html
- Spring Framework 6.2 — OncePerRequestFilter: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- Spring Framework — Spring MVC interceptors: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/interceptors.html
- Spring Security — Servlet Architecture, DelegatingFilterProxy and FilterChainProxy: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Boot 3.5.16 release and OSS support: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/