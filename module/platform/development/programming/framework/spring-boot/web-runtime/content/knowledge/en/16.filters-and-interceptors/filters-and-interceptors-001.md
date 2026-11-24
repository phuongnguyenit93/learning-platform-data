# Servlet Filter, MVC HandlerInterceptor, and WebFlux WebFilter

## 1. Learning Objectives

In Spring Boot, the same requirement—such as timing HTTP requests, issuing a correlation ID, modifying headers, or inspecting a request—can be implemented using multiple mechanisms. **Servlet Filter**, **Spring MVC's HandlerInterceptor**, and **Spring WebFlux's WebFilter** are not three interchangeable names for the same thing: they sit at **different stages of the request lifecycle** and run on **different execution models**.

This lesson belongs to the **Filters and Interceptors** group. After this lesson, you will:

1. Understand the role, lifecycle stage, and API of **jakarta.servlet.Filter**, **org.springframework.web.servlet.HandlerInterceptor**, and **org.springframework.web.server.WebFilter**.
2. Be able to diagram the before/after execution order when multiple Filters and interceptors are present.
3. Know when to use Servlet Filter for HTTP-level concerns, HandlerInterceptor for handler-level concerns, and WebFilter for the reactive HTTP pipeline.
4. Control registration, ordering, URL patterns, async/error dispatch, short-circuiting, and exceptions.
5. Avoid placing authorization in the wrong layer or registering a filter twice when using Spring Security.
6. Avoid blocking the Netty event loop, losing the reactive context, reading the body twice, and modifying an already committed response.
7. Run two separate **Java 17 + Spring Boot 3.5** projects: one Spring MVC project with Filter + Interceptor and one WebFlux project with WebFilter.
8. Write MockMvc and WebTestClient tests to verify execution scope.

The examples use **Spring Boot 3.5.x**, Spring Framework **6.2**, Java **17+**, and the Servlet API under **jakarta.servlet**. Earlier Spring Boot 2.x used **javax.servlet**; you cannot copy those imports directly into Boot 3.x.

## 2. Comparing the Three Components

| Criterion | Servlet Filter | MVC HandlerInterceptor | WebFlux WebFilter |
|---|---|---|---|
| Interface | **jakarta.servlet.Filter** | **HandlerInterceptor** | **WebFilter** |
| Stack | Servlet, typically Tomcat | Spring MVC, Servlet stack | Reactive WebFlux |
| Position | Servlet container FilterChain, before Servlet | MVC HandlerExecutionChain, after HandlerMapping | Reactive WebHandler chain |
| Inputs | ServletRequest, ServletResponse, FilterChain | HttpServletRequest, HttpServletResponse, handler | ServerWebExchange, WebFilterChain |
| Continue | **chain.doFilter(req,resp)** | **preHandle returns true** | **chain.filter(exchange)** |
| Short-circuit | Do not call chain, handle response directly | preHandle returns false and handle response | Do not call chain, return completed Mono |
| Post-processing | Code after chain.doFilter/finally | postHandle/afterCompletion | Reactor doFinally, doOnError |
| Sees selected handler? | No | Yes, via handler parameter, usually HandlerMethod | Not directly at the WebFilter layer |
| Scope | URL pattern/dispatcher type | HandlerMapping + include/exclude patterns | WebFlux WebHandler chain |
| Ordering | FilterRegistrationBean.setOrder | InterceptorRegistry.order | @Order or Ordered |
| Async | DispatcherType, asyncSupported | AsyncHandlerInterceptor, redispatch | Mono/Flux completion/cancel |
| Built-in Security | Spring Security Servlet FilterChain | Not used as primary authz layer | SecurityWebFilterChain |

**Default choice:** in Spring MVC, logic that needs to run before a controller is selected fits **Servlet Filter**; logic that needs to know which controller method is invoked fits **HandlerInterceptor**. In Spring WebFlux, **WebFilter** is the cross-cutting point along the reactive chain. For authentication and authorization, use **Spring Security** for the corresponding stack.

## 3. Request Flow in Spring MVC

~~~mermaid
flowchart TD
    A[HTTP client] --> B[Servlet Filter 1 before]
    B --> C[Servlet Filter 2 before]
    C --> D[DispatcherServlet]
    D --> E[HandlerMapping finds handler]
    E --> F[HandlerInterceptor.preHandle]
    F --> G{true?}
    G -->|Yes| H[HandlerAdapter invokes controller]
    H --> I[MessageConverter or View]
    I --> J[postHandle then afterCompletion]
    G -->|No| K[Interceptor handles response directly]
    J --> K
    K --> L[Servlet Filter 2 after]
    L --> M[Servlet Filter 1 after]
    M --> N[HTTP response]
~~~

A **synchronous, successful** call flow can be illustrated as:

~~~text
Filter A before
  Filter B before
    DispatcherServlet
      HandlerMapping selects handler
      Interceptor 1 preHandle
        Interceptor 2 preHandle
          Controller
        Interceptor 2 postHandle
      Interceptor 1 postHandle
      Interceptor 2 afterCompletion
      Interceptor 1 afterCompletion
  Filter B after
Filter A after
~~~

This is a **conceptual diagram**, not a fixed stdout sequence for every request. When an exception occurs, an interceptor returns false, a Servlet ASYNC/ERROR redispatch happens, or a response is streamed, some callbacks may not run in the exact positions shown in the example.

**Key distinction:** Filters run **before DispatcherServlet**; Interceptors run **after HandlerMapping has selected a handler**. If Spring Security already rejects a request inside the Servlet filter chain, HandlerInterceptor is usually never invoked.

## 4. Servlet Filter

The **jakarta.servlet.Filter** interface has the conceptual method:

~~~java
void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain)
        throws IOException, ServletException;
~~~

This is an illustrative API signature; you must implement Filter or a concrete base class to make a runnable class.

### 4.1. Before, After, Exceptions, and Short-Circuiting

Processing pattern:

~~~java
try {
    // Perform steps before Servlet.
    chain.doFilter(request, response);
} finally {
    // Cleanup when the chain call finishes.
}
~~~

**chain.doFilter** proceeds to the next Filter or the Servlet. If you omit calling chain and write the response yourself, the request is short-circuited. For example, in maintenance mode, you can return **503 Service Unavailable**, and the controller will not run.

**Do not assume** a Filter's finally block always equals "the HTTP request has completed down to the last byte." With MVC asynchronous processing, the chain call may return before the response body has finished streaming.

### 4.2. GenericFilterBean and OncePerRequestFilter

- **GenericFilterBean** integrates a Filter with the Spring bean lifecycle.
- **OncePerRequestFilter** helps ensure single execution per request dispatch under Spring's contract and provides options to control **ASYNC**/**ERROR** dispatches.

Do not interpret OncePerRequestFilter as "at most once across the entire request lifecycle regardless of redirect, forward, or async." A Servlet request can span multiple dispatcher phases and threads, while the filter registration also governs which dispatcher types are permitted.

### 4.3. FilterRegistrationBean

Registration example assuming a MyFilter class exists:

~~~java
@Bean
FilterRegistrationBean<MyFilter> registration() {
    FilterRegistrationBean<MyFilter> bean =
            new FilterRegistrationBean<>(new MyFilter());
    bean.addUrlPatterns("/api/*");
    bean.setDispatcherTypes(DispatcherType.REQUEST);
    bean.setOrder(10);
    return bean;
}
~~~

This snippet requires the corresponding class/imports and is only a registration example; runnable applications are in Section 8.

**Note the two pattern systems:** Servlet **"/api/*"** is not the same as Spring MVC **"/api/**"**. They can cover similar paths, but they do not share a parser and are not interchangeable in every situation.

Spring Boot 3.5 can automatically register a Filter bean with the Servlet container. If a Filter is both annotated with **@Component** and declared via a **FilterRegistrationBean** or added directly to a Spring Security chain, check for the risk of executing **twice**. If a Filter bean is only meant for SecurityFilterChain, configure it so it does not auto-register with the container, for example via registration **setEnabled(false)**.

### 4.4. Filter and Spring Security

The Spring Security Servlet stack uses **DelegatingFilterProxy**, **FilterChainProxy**, and **SecurityFilterChain** instances inside the Servlet filter chain. Authentication, CSRF, security headers, and authorization are handled in a defined order.

Configure Spring Security properly instead of checking roles by URL strings in a HandlerInterceptor. An interceptor can match paths differently from Spring Security, causing URL variants to receive unexpected access behavior.

### 4.5. Errors Raised Before DispatcherServlet

If a custom Servlet Filter throws an exception **before** entering DispatcherServlet, MVC's **@ControllerAdvice** and HandlerExceptionResolver will not automatically handle that error. The error may be handled by another filter, the Servlet container, or Boot's **/error**, depending on configuration.

Therefore, to standardize JSON error responses across Security, Filters, and controllers, design the error contract at the appropriate layer.

## 5. Spring MVC HandlerInterceptor

The primary interface is **org.springframework.web.servlet.HandlerInterceptor**, with three callbacks:

~~~java
boolean preHandle(HttpServletRequest request,
                  HttpServletResponse response,
                  Object handler);

void postHandle(HttpServletRequest request,
                HttpServletResponse response,
                Object handler,
                ModelAndView modelAndView);

void afterCompletion(HttpServletRequest request,
                     HttpServletResponse response,
                     Object handler,
                     Exception ex);
~~~

These signatures omit nullability annotations and throws Exception for clarity; the real interface defines default methods.

### 5.1. preHandle

Runs after HandlerMapping and before handler execution:

~~~java
@Override
public boolean preHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) {

    request.setAttribute("intercepted", true);
    return true;
}
~~~

If it returns **true**, the chain continues. If it returns **false**, DispatcherServlet assumes you have already handled the response and skips invoking the handler. **afterCompletion** of the interceptor that returned false is not invoked by default; if you allocated resources in preHandle, clean them up immediately in the false branch.

The handler parameter may be a **HandlerMethod**, allowing access to the class/method name:

~~~java
if (handler instanceof HandlerMethod method) {
    String name = method.getMethod().getName();
    // Log/metrics for the selected handler.
}
~~~

This snippet requires importing HandlerMethod and belongs inside a method that has a handler variable.

### 5.2. postHandle

For server-side rendered MVC views, postHandle can modify **ModelAndView** before view rendering. For **@ResponseBody/ResponseEntity**, the body may already be written and the response already committed **before postHandle**, so this is not a reliable place to alter a JSON body or add response headers.

To modify a REST body, look at **ResponseBodyAdvice**. To add headers early, use a Servlet Filter, controller, or ResponseEntity as appropriate.

### 5.3. afterCompletion

Callback invoked when DispatcherServlet finishes processing and the interceptor passed preHandle; suitable for cleanup and logging. If an exception interrupts the handler, postHandle may be skipped, while afterCompletion can still be called for interceptors that were already applied, according to the MVC exception lifecycle.

For **Callable**, **DeferredResult**, or Servlet async requests, callbacks on the initial dispatch can differ. **AsyncHandlerInterceptor.afterConcurrentHandlingStarted** supports handling the moment concurrent handling starts; additional callbacks on WebAsyncManager help track timeouts, errors, or client disconnects.

### 5.4. Registration

~~~java
@Configuration
class MvcConfig implements WebMvcConfigurer {
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new MyInterceptor())
                .addPathPatterns("/api/**")
                .excludePathPatterns("/api/public/**")
                .order(10);
    }
}
~~~

This is an illustrative snippet requiring the MyInterceptor class and imports. **Lower order values generally run first** in the interceptor chain; post/after phases run in reverse order during normal completion. **InterceptorRegistry.order** and **FilterRegistrationBean.setOrder** manage two separate chains and do not establish a single shared order.

If no matching HandlerMapping exists, the interceptor may not run. However, a request with no controller **can** be matched by a static resource handler, so do not claim that every 404 bypasses interceptors.

## 6. Spring WebFlux WebFilter

WebFlux has the contract:

~~~java
Mono<Void> filter(ServerWebExchange exchange,
                  WebFilterChain chain);
~~~

**ServerWebExchange** holds the request, response, attributes, session/principal APIs, and reactive request context data.

### 6.1. Continuing the Chain and Measuring Completion

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange,
                         WebFilterChain chain) {
    long start = System.nanoTime();
    return chain.filter(exchange)
            .doFinally(signal -> {
                long elapsedMs =
                        (System.nanoTime() - start) / 1_000_000;
                // Record metric, do not perform blocking I/O.
            });
}
~~~

This is illustrative code inside a class implementing WebFilter. **chain.filter(exchange)** returns a Mono<Void> signaling completion of the request pipeline.

Useful operators:

| Operator | Role |
|---|---|
| **doOnSubscribe** | Observe subscription |
| **doOnError** | Observe errors in the pipeline at this point |
| **doOnSuccess** | Observe successful completion of the Mono |
| **doFinally** | Observe complete, error, or cancel |
| **contextWrite** | Write to Reactor Context for downstream reactive operators |
| **onErrorResume** | Transform an error into an alternative publisher, only with a clear policy |

**Never call block(), Thread.sleep, or blocking JDBC on the Netty event loop.** A reactive WebFilter must return a Publisher and must not call subscribe itself in a way that detaches it from the request lifecycle.

### 6.2. Short-Circuiting a WebFlux Request

Short illustrative code:

~~~java
exchange.getResponse().setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
return exchange.getResponse().setComplete();
~~~

If chain.filter(exchange) is not called, subsequent filters and handlers do not execute. Apply timeout/rate/security policies in the appropriate component; do not build a custom WebFilter as primary authorization when Spring Security is available.

### 6.3. Per-Request State Must Not Be an Instance Field

A WebFilter is normally a singleton. Do not store per-request **currentUser**, **traceId**, or **startNanos** in a mutable instance variable. Concurrent requests will overwrite one another's data.

Use **exchange.getAttributes()**, **Reactor Context**, or Micrometer context propagation as appropriate. Do not rely on standard ThreadLocal/MDC as a dependable data carrier across **publishOn/subscribeOn** because a reactive pipeline can execute across multiple threads.

### 6.4. Headers and Committed Responses

Set headers before invoking the chain:

~~~java
exchange.getResponse().getHeaders().set("X-Trace-Id", traceId);
return chain.filter(exchange);
~~~

If you need to set something right before commit, you can use **ServerHttpResponse.beforeCommit** with a callback returning Mono<Void>. Setting headers inside **doFinally** is usually too late because the HTTP response may already be committed.

### 6.5. WebFilter vs. HandlerFilterFunction and WebClient Filters

- **WebFilter**: server-side cross-cutting filter across the entire WebFlux WebHandler chain.
- **HandlerFilterFunction**: filter at the **WebFlux.fn RouterFunction/HandlerFunction** level, scoped to functional routes.
- **ExchangeFilterFunction**: filter for **outbound WebClient** calls to other servers, not inbound requests.

With reactive Spring Security, **SecurityWebFilterChain** and **ServerHttpSecurity** are used to configure authentication/authorization; do not copy Servlet HttpSecurity into WebFlux.

### 6.6. WebExceptionHandler

WebFlux provides **WebExceptionHandler** wrapping processing in the reactive WebHandler/WebFilter chain. **@RestControllerAdvice** applies to annotated controller exception handling; it does not mean it will catch every error thrown from a WebFilter before the controller.

Streaming also introduces the committed response constraint: if an error occurs after data has already been flushed, you cannot arbitrarily change the status or body into a fresh error JSON.

## 7. Selection Matrix by Requirement

| Requirement | Suitable Mechanism | Notes |
|---|---|---|
| Trace ID for MVC HTTP as soon as request arrives | Servlet Filter | Can set header before DispatcherServlet |
| Log MVC controller method name | HandlerInterceptor | Has HandlerMethod after HandlerMapping |
| Add ModelAndView data before HTML render | HandlerInterceptor | postHandle is intended for views |
| Modify JSON REST response | ResponseBodyAdvice | Interceptor postHandle may be too late |
| CORS, auth, CSRF in MVC | Spring Security/Servlet Filter integration | Place security in the filter chain |
| CORS, auth, CSRF in WebFlux | SecurityWebFilterChain | Reactive-specific |
| Correlation ID in WebFlux | WebFilter | Exchange attributes + Reactor Context |
| Measure complete/error/cancel in WebFlux | WebFilter + doFinally | Matches reactive subscription lifecycle |
| Middleware for specific WebFlux.fn routes | HandlerFilterFunction | Scoped to functional routes |
| Outbound HTTP WebClient request tracing | ExchangeFilterFunction | Do not use server WebFilter |
| Servlet async completion | AsyncHandlerInterceptor + Filter async mapping | Do not rely on a simple finally block alone |

## 8. Safety and Body Lifecycle

### 8.1. Single-Read Body

In Servlet, **ServletInputStream** is a stream; if a Filter consumes the body first, **@RequestBody** in the controller may have no bytes left to read. **ContentCachingRequestWrapper** caches data as it is consumed, but **it does not automatically turn every request into a replayable stream**. Use wrappers/reading judiciously and enforce RAM bounds.

In WebFlux, the request body is a **Flux<DataBuffer>**. If a WebFilter subscribes, joins, or consumes the body before calling chain.filter, downstream components may fail to read the body or encounter memory errors. When transformation is truly required, you must understand **ServerHttpRequestDecorator**, DataBuffer ownership, and release/discard semantics. Do not cache sensitive raw bodies just for logging.

### 8.2. Async, Errors, and Cancellation

- **Servlet Filter**: register DispatcherType.REQUEST/ASYNC/ERROR as needed; OncePerRequestFilter offers options to skip async/error dispatches.
- **MVC Interceptor**: callbacks differ between sync and async; AsyncHandlerInterceptor manages the concurrent phase.
- **WebFlux WebFilter**: doFinally observes completion/error/cancel of the Publisher where attached; the reactive pipeline may be cancelled if the client disconnects.

### 8.3. Ordering and Security Mismatches

Interceptors are not the primary authorization layer because MVC matchers can differ from security rules. Inside a Servlet SecurityFilterChain, filters have their own ordering; a custom filter can execute twice if it is both an auto-registered Spring bean and added to the Security chain. In WebFlux, @Order controls WebFilter ordering, while Spring Security's WebFilters follow their own rules.

### 8.4. Logging Without Exposing Secrets

Do not log Authorization, Cookie, passwords, access tokens, raw bodies, file uploads, or query strings containing sensitive data by default. TraceId should be generated by the server or validated if accepted from a trusted upstream. Use Micrometer Observation/Tracing for standard observability where appropriate.

## 9. Runnable Spring MVC Example: Servlet Filter and HandlerInterceptor

The first project uses **Java 17, Spring Boot 3.5.16, spring-boot-starter-web, and embedded Tomcat**. A Filter generates traceId early, an Interceptor confirms the selected handler, and a controller returns JSON for verification.

### 9.1. Structure

~~~text
mvc-chain-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/mvcdemo/
    │   │   ├── MvcDemoApplication.java
    │   │   ├── TraceFilter.java
    │   │   ├── TraceInterceptor.java
    │   │   ├── MvcConfig.java
    │   │   └── HelloController.java
    │   └── resources/application.yml
    └── test/java/com/example/mvcdemo/
        └── MvcChainTest.java
~~~

### 9.2. pom.xml

~~~xml
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
    <artifactId>mvc-chain-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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

### 9.3. MvcDemoApplication.java

~~~java
package com.example.mvcdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcDemoApplication.class, args);
    }
}
~~~

### 9.4. TraceFilter.java

~~~java
package com.example.mvcdemo;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.filter.OncePerRequestFilter;

public class TraceFilter extends OncePerRequestFilter {

    private static final Logger log =
            LoggerFactory.getLogger(TraceFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String traceId = UUID.randomUUID().toString();
        request.setAttribute("traceId", traceId);
        response.setHeader("X-Trace-Id", traceId);

        long start = System.nanoTime();
        log.info("Filter before path={}", request.getRequestURI());

        try {
            chain.doFilter(request, response);
        } finally {
            long elapsedMs =
                    (System.nanoTime() - start) / 1_000_000;
            log.info("Filter after status={} durationMs={}",
                    response.getStatus(), elapsedMs);
        }
    }
}
~~~

This class **does not use @Component** because it will be registered exclusively via FilterRegistrationBean. The Filter sets an attribute on the Servlet request and a header on the response before downstream processing. The finally block measures the duration of the chain call, which is **not necessarily the total async HTTP duration**.

### 9.5. TraceInterceptor.java

~~~java
package com.example.mvcdemo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.method.HandlerMethod;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.ModelAndView;

public class TraceInterceptor implements HandlerInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(TraceInterceptor.class);

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        request.setAttribute("intercepted", Boolean.TRUE);

        if (handler instanceof HandlerMethod method) {
            log.info("Interceptor preHandle {}.{}",
                    method.getBeanType().getSimpleName(),
                    method.getMethod().getName());
        }
        return true;
    }

    @Override
    public void postHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            ModelAndView modelAndView) {
        log.info("Interceptor postHandle status={}",
                response.getStatus());
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception ex) {
        log.info("Interceptor afterCompletion error={}",
                ex == null ? "none" : ex.getClass().getSimpleName());
    }
}
~~~

The Interceptor receives the selected handler, so it can log the **HandlerMethod**. For REST responses, the example only logs in postHandle; it does not add headers too late.

### 9.6. MvcConfig.java

~~~java
package com.example.mvcdemo;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcConfig implements WebMvcConfigurer {

    @Bean
    public FilterRegistrationBean<TraceFilter> traceRegistration() {
        FilterRegistrationBean<TraceFilter> registration =
                new FilterRegistrationBean<>(new TraceFilter());
        registration.addUrlPatterns("/api/*");
        registration.setDispatcherTypes(DispatcherType.REQUEST);
        registration.setOrder(10);
        return registration;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new TraceInterceptor())
                .addPathPatterns("/api/**")
                .order(10);
    }
}
~~~

Here, the Filter uses the **Servlet URL pattern "/api/*"**, while the interceptor uses the **Spring MVC path pattern "/api/**"**. Both order values of 10 **are not in the same ordering space**. The demo only handles REQUEST dispatches; if async/error dispatches exist in production, select dispatcher types explicitly.

### 9.7. HelloController.java

~~~java
package com.example.mvcdemo;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/api/hello")
    public HelloReply hello(HttpServletRequest request) {
        String traceId =
                (String) request.getAttribute("traceId");
        boolean intercepted = Boolean.TRUE.equals(
                request.getAttribute("intercepted"));

        return new HelloReply("hello", traceId, intercepted);
    }

    public record HelloReply(
            String message,
            String traceId,
            boolean intercepted) {
    }
}
~~~

### 9.8. application.yml

~~~yaml
server:
  port: 8080
~~~

### 9.9. Running and Inspecting Output

~~~bash
mvn spring-boot:run
curl -i http://localhost:8080/api/hello
~~~

An **illustrative** response:

~~~http
HTTP/1.1 200 OK
X-Trace-Id: 123e4567-e89b-12d3-a456-426614174000
Content-Type: application/json

{"message":"hello","traceId":"123e4567-e89b-12d3-a456-426614174000","intercepted":true}
~~~

The UUID value **is randomly generated**, not fixed stdout. The X-Trace-Id header and the traceId field in JSON must match. Logs may show Filter before, Interceptor preHandle, postHandle, afterCompletion, and Filter after, though log lines across concurrent requests can interleave.

### 9.10. MvcChainTest.java

~~~java
package com.example.mvcdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class MvcChainTest {

    @Autowired
    MockMvc mvc;

    @Test
    void servletFilterAndMvcInterceptorBothRun() throws Exception {
        MvcResult result = mvc.perform(get("/api/hello"))
                .andExpect(status().isOk())
                .andExpect(header().exists("X-Trace-Id"))
                .andExpect(jsonPath("$.message").value("hello"))
                .andExpect(jsonPath("$.intercepted").value(true))
                .andReturn();

        String traceId =
                result.getResponse().getHeader("X-Trace-Id");
        assertThat(traceId).isNotBlank();
        assertThat(result.getResponse().getContentAsString())
                .contains(traceId);
    }
}
~~~

Run:

~~~bash
mvn test
~~~

MockMvc tests filters and the MVC handler pipeline inside the test context, but **does not open a real Tomcat connection**. When you need to verify error/async dispatches, socket timeouts, or Servlet container Filter ordering with proxies, add HTTP integration tests.

## 10. Separate Spring WebFlux Example: WebFilter

Do not place MVC and WebFlux code into the same sample project. The second project uses **spring-boot-starter-webflux**, Reactor Netty, and port 8081. A WebFilter creates traceId in ServerWebExchange, adds a response header, and logs when the reactive pipeline completes.

### 10.1. Structure

~~~text
webflux-chain-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/reactivedemo/
    │   │   ├── ReactiveDemoApplication.java
    │   │   ├── TraceWebFilter.java
    │   │   └── ReactiveController.java
    │   └── resources/application.yml
    └── test/java/com/example/reactivedemo/
        └── ReactiveChainTest.java
~~~

### 10.2. pom.xml

~~~xml
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
    <artifactId>webflux-chain-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

If you add both **spring-boot-starter-web** and **spring-boot-starter-webflux**, Spring Boot usually defaults to **Spring MVC**, preventing the WebFlux demo from running under the intended architecture.

### 10.3. ReactiveDemoApplication.java

~~~java
package com.example.reactivedemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveDemoApplication.class, args);
    }
}
~~~

### 10.4. TraceWebFilter.java

~~~java
package com.example.reactivedemo;

import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 20)
public class TraceWebFilter implements WebFilter {

    private static final Logger log =
            LoggerFactory.getLogger(TraceWebFilter.class);

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {

        String traceId = UUID.randomUUID().toString();
        exchange.getAttributes().put("traceId", traceId);
        exchange.getResponse().getHeaders()
                .set("X-Trace-Id", traceId);

        long start = System.nanoTime();

        return chain.filter(exchange)
                .doOnError(error -> log.warn(
                        "WebFilter error type={}",
                        error.getClass().getSimpleName()))
                .doFinally(signal -> {
                    long elapsedMs =
                            (System.nanoTime() - start) / 1_000_000;
                    log.info(
                            "WebFilter finished traceId={} signal={} elapsedMs={}",
                            traceId, signal, elapsedMs);
                });
    }
}
~~~

**@Component** registers the WebFilter with Spring WebFlux; **@Order** controls bean ordering. The order value is purely illustrative without Spring Security; in a real application, check the full reactive security/proxy chain.

TraceId is stored in **exchange attributes**, not in an instance variable of the singleton WebFilter. The header is set **before the response commits**. **doFinally** can receive completion, error, or cancel signals; do not assume every error handled by WebExceptionHandler reaches doOnError.

### 10.5. ReactiveController.java

~~~java
package com.example.reactivedemo;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveController {

    @GetMapping("/api/hello")
    public Mono<HelloReply> hello(ServerWebExchange exchange) {
        String traceId = exchange.getAttribute("traceId");
        return Mono.just(
                new HelloReply("hello", traceId, "WebFilter"));
    }

    @GetMapping(
            path = "/api/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events() {
        return Flux.just("one", "two")
                .delayElements(Duration.ofMillis(100))
                .map(value -> ServerSentEvent.<String>builder()
                        .event("tick")
                        .data(value)
                        .build());
    }

    public record HelloReply(
            String message,
            String traceId,
            String source) {
    }
}
~~~

The /api/hello request shows that both the header and JSON use the same traceId from ServerWebExchange. The /api/events endpoint emits **two SSE events** and then completes, allowing you to observe **doFinally** after completion.

### 10.6. application.yml

~~~yaml
server:
  port: 8081
~~~

### 10.7. Running and Testing

~~~bash
mvn spring-boot:run
curl -i http://localhost:8081/api/hello
~~~

Example response:

~~~http
HTTP/1.1 200 OK
X-Trace-Id: 123e4567-e89b-12d3-a456-426614174000
Content-Type: application/json

{"message":"hello","traceId":"123e4567-e89b-12d3-a456-426614174000","source":"WebFilter"}
~~~

UUID changes per request. To receive the finite stream:

~~~bash
curl -i -N -H "Accept: text/event-stream" \
  http://localhost:8081/api/events
~~~

The frames look like:

~~~text
event:tick
data:one

event:tick
data:two

~~~

### 10.8. ReactiveChainTest.java

~~~java
package com.example.reactivedemo;

import java.time.Duration;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveChainTest {

    @LocalServerPort
    int port;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port)
                .responseTimeout(Duration.ofSeconds(5))
                .build();
    }

    @Test
    void filterSetsHeaderAndExchangeAttribute() {
        client.get().uri("/api/hello")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().exists("X-Trace-Id")
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.message").isEqualTo("hello")
                .jsonPath("$.source").isEqualTo("WebFilter")
                .jsonPath("$.traceId").isNotEmpty();
    }

    @Test
    void finiteSseStreamReturnsEventFrames() {
        client.get().uri("/api/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .expectBody()
                .consumeWith(result ->
                        assertThat(result.getResponseBody())
                                .isNotNull());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The test suite verifies JSON, X-Trace-Id, and SSE media type over real HTTP on a random port. The finite stream test does not measure **per-event flush latency** or cancellation; a subscriber receiving individual events and cancelling the stream is needed to test those aspects.

## 11. Typical Mistakes and Diagnostics

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Interceptor does not see 401/403 | Security filter blocks before MVC | Check SecurityFilterChain |
| Filter runs twice | Both auto-registered and added to Spring Security | Use only one registration, setEnabled(false) when needed |
| postHandle cannot add JSON header | ResponseBody already committed | Set early in Filter/Controller/ResponseEntity |
| afterCompletion does not run on interceptor returning false | That interceptor itself blocked the handler | Clean up immediately when preHandle returns false |
| Logged duration too small on async MVC | Filter chain finishes initial dispatch | Track ASYNC/ERROR dispatches and async callbacks |
| WebFilter blocks event loop | block(), Thread.sleep, blocking JDBC | Use non-blocking APIs/controlled offloading |
| Reactive traceId mixed across requests | Mutable singleton field/ThreadLocal | ServerWebExchange attributes or Reactor Context |
| @RequestBody is empty | Filter already consumed ServletInputStream | Do not read body early or use proper wrapper |
| WebFlux body consumed | WebFilter subscribed to Flux<DataBuffer> directly | Avoid uncontrolled consume/replay |
| WebFilter does not see server 500 error | Downstream handler mapped exception to response | Log status, observe metrics and exception handler |
| Servlet Filter does not run on WebFlux Netty | No Servlet filter chain exists | Use WebFilter |
| @ControllerAdvice misses Filter error | Error occurred before DispatcherServlet | Filter/container error handling |
| Response header missing in doFinally | Header already committed | Set before chain or in beforeCommit |
| WebFilter order skews security/CORS | Inappropriate order chosen | Use official security/CORS configuration |
| Interceptor skips unusual URLs | No HandlerExecutionChain or pattern mismatch | Check HandlerMapping/static resources |

### 11.1. Investigation Workflow

1. Identify the **application web type** and which server is actually running.
2. Inspect all Servlet Filter registrations, DispatcherType, @Order, SecurityFilterChain, and URL patterns.
3. Inspect MVC InterceptorRegistry, include/exclude patterns, handler mappings, and async callbacks.
4. For WebFlux, inspect WebFilter beans, @Order ordering, SecurityWebFilterChain, and Reactor operators.
5. Send a successful request, a security-blocked request, an unmatched request, and a request that throws an exception.
6. Check status, response headers, trace ID, log ordering, and whether the body has already committed.
7. When using async/streaming, test client disconnects to verify cleanup and cancellation.
8. Do not enable sensitive raw body logging or long-term TRACE logging in production.

## 12. Production Checklist

- [ ] Choose the mechanism matching the stack: Servlet Filter / MVC Interceptor / WebFlux WebFilter.
- [ ] Register each Filter once with an explicit order.
- [ ] Control URL patterns and DispatcherType.REQUEST/ASYNC/ERROR as required.
- [ ] Do not use an interceptor as the primary authorization layer.
- [ ] Do not use postHandle to modify a JSON body that has already been written.
- [ ] Clean up resources properly on preHandle false, exceptions, async, and cancellation.
- [ ] Never call block() inside a WebFilter or on the Netty event loop.
- [ ] Never store per-request state in singleton fields or unmanaged ThreadLocals.
- [ ] Never read the request body twice or cache it unboundedly.
- [ ] Protect sensitive data in logging, tracing, and standardized exception responses.
- [ ] Test normal/error/short-circuit/async/reactive streaming paths.
- [ ] Use Spring Security and Micrometer Observation when appropriate.
- [ ] Choose a Spring Boot version still receiving security support for production.

## 13. Official References

1. Spring Framework 6.2 – Servlet Filters/OncePerRequestFilter: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html
2. Spring Framework 6.2 – MVC HandlerInterceptor: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/handlermapping-interceptor.html
3. Spring Framework 6.2 – Configuring MVC Interceptors: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/interceptors.html
4. Spring Framework 6.2 – MVC Asynchronous Requests: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html
5. Spring Framework 6.2 – WebFlux Reactive Core and WebFilter: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
6. Spring Framework – WebFilter API: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/server/WebFilter.html
7. Spring Boot 3.5 – Embedded Web Servers, registering Filters: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
8. Spring Boot 3.5 API – FilterRegistrationBean: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/FilterRegistrationBean.html
9. Spring Security – Servlet Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
10. Spring Security – Reactive WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html

## 14. Summary

**Servlet Filter** operates at the Servlet layer, wrapping requests before DispatcherServlet. **HandlerInterceptor** operates inside the Spring MVC processing chain after HandlerMapping selects a handler, making it suitable for controller-aware and ModelAndView logic, though not as the primary security layer. **WebFilter** operates at the reactive layer of Spring WebFlux, handling ServerWebExchange and Mono<Void> with visibility into complete, error, and cancel signals.

Choose the right component based on **stack, timing, scope, request lifecycle, and security requirements**. Test not only the happy path, but also blocked requests, error/async dispatches, and committed responses.