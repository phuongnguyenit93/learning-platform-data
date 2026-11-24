# Request Path Through the Servlet Container, FilterChain, and DispatcherServlet in Spring MVC

An HTTP request entering a **Spring Boot application using Spring MVC** must pass through multiple layers before reaching a `@GetMapping` or `@PostMapping` method. Three components that are very easy to confuse are the **Servlet container**, the **Servlet FilterChain**, and the **DispatcherServlet**. They operate at different levels:

- The **Servlet container** (for example, embedded Tomcat, Jetty, or Undertow) accepts the connection, parses HTTP, identifies the target application and servlet, manages the request/response lifecycle, and implements Jakarta Servlet.
- The **FilterChain** is the chain of Servlet `Filter`s selected by the container for the request. Each filter can inspect, transform, pass along, or block the request before it reaches the servlet; filters can also process the response on the way back out.
- The **DispatcherServlet** is Spring MVC's **Front Controller**. It receives requests that have passed through the filters and coordinates `HandlerMapping`, `HandlerAdapter`, controllers, binding mechanisms, exception resolvers, and views or response bodies.

Understanding this exact path helps you place logging, security, CORS, authentication, request validation, and exception handling at the right layer, while explaining why a request returns 401 before the controller, 404 inside MVC, or 500 after processing.

## 1. Overall Request and Response Diagram

In a common Servlet MVC configuration, a request to `GET /api/hello?name=Lan` follows this path:

~~~text
HTTP client
    |
    v
Servlet container socket / HTTP connector
    |
    v
Container selects web application + Servlet mapping
    |
    v
Filter 1 --> Filter 2 --> ... --> Filter N
    |           |                    |
    |           |    chain.doFilter()
    |           +--------------------+
    v
DispatcherServlet (Spring MVC front controller)
    |
    +--> HandlerMapping: find handler + interceptor chain
    |
    +--> HandlerInterceptor.preHandle(...)
    |
    +--> HandlerAdapter: prepare and invoke controller
    |        +--> resolve arguments, binding, validation
    |        +--> Controller / handler method
    |        +--> process return value / HTTP body
    |
    +--> postHandle(...) if the execution path applies
    |
    +--> render view or finalize response
    |
    +--> afterCompletion(...) when processing finishes
    |
    v
Filter N finishes --> ... --> Filter 1 finishes
    |
    v
Servlet container writes response to connection
    |
    v
HTTP client
~~~

This diagram illustrates the **synchronous, successful, common** path. The exact order changes when a filter actively blocks the request, Spring Security denies access, a controller throws an exception, a Servlet error dispatch occurs, or the request switches to asynchronous processing.

**Key takeaway:** A URL does not necessarily reach a controller. A filter can return a response immediately; `DispatcherServlet` can choose a handler that serves static resources, handles an error, or ends with a 404 if no matching handler exists.

## 2. Layer One: The Servlet Container Receives the HTTP Request

Embedded Tomcat is the standard choice in `spring-boot-starter-web`; Jetty or Undertow can replace it when dependencies are configured accordingly. All three implement a Servlet runtime and run the Spring MVC model on top.

When an HTTP client connects, the container performs several steps:

1. Accepts the TCP or TLS connection on the configured listener/connector.
2. Parses the HTTP method, request target, headers, query string, and the required parts of the request body.
3. Determines the virtual host, web application context path, and servlet mapping matching the URL.
4. Creates/allocates `HttpServletRequest` and `HttpServletResponse` objects for the Servlet processing flow.
5. Selects matching filters by URL pattern, servlet name, and dispatcher type.
6. Invokes the filter chain; the last filter forwards to the mapped servlet.

Spring Boot initializes the Servlet container and registers Spring MVC's `DispatcherServlet` for the application. In a standard configuration, `DispatcherServlet` is mapped to `/`, though the mapping can be customized. The context path `server.servlet.context-path` is a prefix for the entire application, distinct from `DispatcherServlet`'s own mapping and distinct from controller paths.

For example, with context path `/shop` and controller mapping `/api/hello`, clients typically call `/shop/api/hello`. The container recognizes the context path before `DispatcherServlet` selects a handler.

### 2.1. A Connection Does Not Equal a Controller Thread

A keep-alive connection can serve multiple HTTP requests over time. In the traditional Servlet stack, a synchronous request typically uses a container worker thread during processing, but the number of open sockets does not necessarily equal the number of concurrently executing requests.

A filter or controller that holds a thread waiting too long on SQL or an external API can exhaust the worker pool. Therefore, stages before and inside `DispatcherServlet` both affect response latency; thread limits, timeouts, and connection pools must be measured together.

## 3. Layer Two: The Servlet FilterChain

A `Filter` implements the **Jakarta Servlet** API, not a Spring MVC–only mechanism. In Spring Boot 3.x, the package is `jakarta.servlet.*`; older examples using `javax.servlet.*` from the Spring Boot 2.x era must be updated when upgrading.

A filter typically looks like this:

~~~java
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain
) throws IOException, ServletException {
    // Logic running before the servlet
    try {
        chain.doFilter(request, response);
    } finally {
        // Logic running as the call stack unwinds, including when an exception occurs
    }
}
~~~

This is a fragment illustrating the method structure inside a class that implements `Filter`; it is not a standalone Java program. Calling `chain.doFilter(request, response)` forwards to the next filter or the final servlet. If a filter does not call this method, the request **does not continue** through the chain along the normal path.

### 3.1. What Can a Filter Do?

- Record processing time, correlation IDs, or HTTP-level request metadata.
- Inspect headers, enforce HTTP protection policies, and apply size limits.
- Wrap the request/response using `HttpServletRequestWrapper` or `HttpServletResponseWrapper`.
- Set character encoding and control certain response headers.
- Reject requests early, such as sending HTTP 400/403 and stopping the chain.
- Integrate Spring Security through filters registered with the Servlet container.

A filter does not inherently know which handler method Spring MVC will select. It runs before `DispatcherServlet`'s controller lookup and can apply even to requests not handled by any controller.

### 3.2. Filter Ordering Affects Behavior

Filters are typically ordered by registration order or `FilterRegistrationBean.setOrder(...)` in a Spring Boot application. Filters earlier in the chain execute their "before" logic first, and their "after" logic as the nested calls return:

~~~text
Filter A: before
  Filter B: before
    DispatcherServlet processing
  Filter B: after
Filter A: after
~~~

If Filter A decides to return a response without calling `chain.doFilter`, Filter B and `DispatcherServlet` will not be invoked for that pass through the chain. Therefore, a controller not being called **does not mean** the request never reached the server; it may have been blocked in a filter.

When configuring a filter, you must specify:

- The URL patterns and servlet mappings to apply to.
- The dispatcher types, such as `REQUEST`, `ASYNC`, `ERROR`, `FORWARD`.
- The filter's order relative to other filters, especially security.
- Whether it needs to run on async/error dispatches.
- Whether headers/response have already been committed when the filter wants to modify content.

### 3.3. OncePerRequestFilter

Spring provides `OncePerRequestFilter` as a convenient base class to avoid invoking filter logic multiple times within **a single dispatch**. The class name does not strictly mean the logic runs only once across the entire asynchronous lifecycle of every request. Behavior with async and error dispatches still depends on configuration and methods like `shouldNotFilterAsyncDispatch()` and `shouldNotFilterErrorDispatch()`.

This is a convenient choice for simple request logging. You should not read the entire request body inside a filter to log it without handling single-consumption stream constraints, size limits, and sensitive data protection.

### 3.4. Filters and Spring Security

With Spring Security on the Servlet stack, the container typically invokes a `DelegatingFilterProxy` linked to the Spring Security filter chain bean. `FilterChainProxy` then selects an appropriate `SecurityFilterChain` and runs the security filters in their own order.

Consequently, authentication and authorization can terminate a request **before `DispatcherServlet` looks up a controller**. A 401 or 403 response from Spring Security does not typically pass through a controller's `@ExceptionHandler` like an exception thrown inside a handler method.

Do not insert login or authorization filters arbitrarily by guesswork: always verify ordering and integrate properly with Spring Security to avoid executing at the wrong layer, duplicating logic, or opening security holes.

## 4. Layer Three: DispatcherServlet Orchestrates Spring MVC

`DispatcherServlet` is a real Servlet invoked by the container after matching filters. It organizes the request pipeline using Spring MVC strategies rather than containing per-endpoint business logic itself.

The main pipeline consists of these components:

| Component | Role |
|---|---|
| `DispatcherServlet` | Receives requests from the Servlet API and orchestrates the entire MVC pipeline |
| `HandlerMapping` | Determines the handler matching the method, URL, and mapping conditions; returns a `HandlerExecutionChain` |
| `HandlerExecutionChain` | Contains the selected handler and associated `HandlerInterceptor`s |
| `HandlerInterceptor` | Runs before/after the handler within the MVC scope |
| `HandlerAdapter` | Knows how to execute the type of handler that was found |
| `HandlerMethodArgumentResolver` | Prepares parameter values for the controller |
| `HttpMessageConverter` | Reads request bodies and writes response bodies for matching content types |
| `HandlerExceptionResolver` | Attempts to turn exceptions during MVC processing into a handleable response |
| `ViewResolver` and View | Serves controllers that need to render a view, such as Thymeleaf |

### 4.1. HandlerMapping Finds the Controller

Suppose we have a controller:

~~~java
@RestController
@RequestMapping("/api")
class GreetingController {

    @GetMapping("/hello")
    String hello() {
        return "Hello";
    }
}
~~~

This is a fragment that requires Spring MVC imports and an enclosing Spring Boot application class. If the application uses the default Servlet mapping and has no context path, `GET /api/hello` is typically mapped to the `hello()` method by `RequestMappingHandlerMapping`.

`HandlerMapping` can also evaluate HTTP method, `consumes`, `produces`, headers, and params. A matching URL with the wrong HTTP method can lead to 405; mismatched content type or acceptable media type conditions can lead to 415 or 406. Not every failed request is a 404.

If no matching handler is found, Spring MVC has a 404 handling mechanism; in some configurations the request may match the static-resource handler and then report a missing resource. You should not rely on a single exception type for every 404 case.

### 4.2. HandlerAdapter Invokes the Controller

After `HandlerMapping` returns a handler, `DispatcherServlet` finds a `HandlerAdapter` that supports it. For annotated controllers, `RequestMappingHandlerAdapter` typically handles invoking the method.

Before invoking the controller, the framework may:

- Read `@PathVariable`, `@RequestParam`, `@RequestHeader`.
- Bind `@ModelAttribute` from request parameters.
- Use `HttpMessageConverter` to read JSON into a Java object for `@RequestBody`.
- Perform validation if `@Valid` or a corresponding validation mechanism is present.
- Prepare `Principal`, `HttpServletRequest`, `HttpServletResponse`, or other supported parameter types.

If the JSON is malformed, a parameter is missing, or validation fails, an exception may occur **before the controller body runs**. This explains why a "controller started" log line does not always appear for a request that entered `DispatcherServlet`.

### 4.3. Controller Executes Business Logic and Produces a Result

The controller calls services/repositories, then returns a `String`, DTO, `ResponseEntity`, `ModelAndView`, or another return type.

With `@RestController`, the return value is typically handled as the response body. `HttpMessageConverter` selects how to encode a String, JSON, byte array, etc., depending on the data type and content negotiation. With MVC views, Spring MVC resolves the view name and renders the view. Both paths are orchestrated by `DispatcherServlet` and `HandlerAdapter`, though the timing of writing the response body and rendering the view differs.

**Timing note:** in a controller returning `@ResponseBody`, writing the body via a message converter can happen while `HandlerAdapter` is processing the return value, **before** the `postHandle` callback. Therefore, `postHandle` is not suitable if you assume the response has not yet been written/committed and can still be freely modified.

## 5. Where Does HandlerInterceptor Sit Relative to Filter?

`HandlerInterceptor` belongs to **Spring MVC** and runs after `DispatcherServlet` has selected a matching handler. This is why an interceptor can inspect the selected handler, whereas a Servlet `Filter` generally does not know which controller will be called.

Three important callbacks:

- **preHandle(request, response, handler)** runs before `HandlerAdapter` invokes the handler. Return `true` to continue; return `false` to stop processing the handler along that branch.
- **postHandle(request, response, handler, modelAndView)** runs after the handler executes successfully in a normal synchronous flow, before rendering the view. It may not be called on certain exception or asynchronous paths.
- **afterCompletion(request, response, handler, exception)** is used for cleanup once MVC processing has finished for the request; only interceptors that passed `preHandle` appropriately receive completion callbacks according to Spring MVC's mechanism. With async, callback behavior differs and subsequent dispatches may occur.

Quick comparison:

| Criterion | Servlet Filter | HandlerInterceptor |
|---|---|---|
| Belongs to | Jakarta Servlet container | Spring MVC |
| Timing | Before `DispatcherServlet` processes, and wraps the response on the way back | After MVC finds the handler |
| Knows handler/controller? | Not via the standard Servlet API | Has the handler parameter |
| Applies to | Registered URL/servlet/dispatcher types, potentially including requests that never enter MVC | Requests belonging to a Spring MVC handler chain |
| Stopping execution | Do not call `chain.doFilter`; produce response directly | `preHandle` returns `false`; usually produces response if needed |
| Best suited for | HTTP security filters, request wrapping, Servlet-level correlation/logging | Handler-dependent logic, checks, or tracking in the MVC layer |

Do not use `HandlerInterceptor` as the sole security barrier for an application when pre-MVC authorization is required. For security, prefer the appropriate Spring Security mechanism; interceptors are more useful for logic directly tied to MVC handlers.

## 6. Runnable Java Example: Tracing Filter → Interceptor → Controller

The following example uses **Java 17+**, **Spring Boot 3.x**, **Spring MVC**, and the default embedded Tomcat from `spring-boot-starter-web`. The Java file has one public class and package-private classes so it can run from a single source file.

Gradle Groovy DSL in a Spring Boot project with plugin and dependency management configured:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Create **src/main/java/demo/flow/MvcFlowApplication.java**:

~~~java
package demo.flow;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.ModelAndView;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class MvcFlowApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcFlowApplication.class, args);
    }
}

@Component
class RequestTraceFilter extends OncePerRequestFilter {

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !"/flow".equals(request.getRequestURI());
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        System.out.println("Filter before");
        try {
            filterChain.doFilter(request, response);
        } finally {
            System.out.println("Filter after");
        }
    }
}

@Configuration(proxyBeanMethods = false)
class FlowMvcConfiguration implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new HandlerInterceptor() {

            @Override
            public boolean preHandle(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    Object handler
            ) {
                System.out.println("Interceptor pre");
                return true;
            }

            @Override
            public void postHandle(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    Object handler,
                    ModelAndView modelAndView
            ) {
                System.out.println("Interceptor post");
            }

            @Override
            public void afterCompletion(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    Object handler,
                    Exception exception
            ) {
                System.out.println("Interceptor afterCompletion");
            }
        }).addPathPatterns("/flow");
    }
}

@RestController
class FlowController {

    @GetMapping("/flow")
    public String flow() {
        System.out.println("Controller");
        return "ok";
    }
}
~~~

The main class shares the filename; the remaining classes are in the same package so they are scanned by `@SpringBootApplication`. The code uses `jakarta.servlet.*` imports, matching Spring Boot 3.x. `RequestTraceFilter` limits logging to `/flow` so other requests do not clutter the example; an empty default context path is assumed.

Start with the project's Gradle wrapper, with the main class detected or configured properly:

~~~bash
./gradlew bootRun
~~~

On Windows you can use `gradlew.bat bootRun`. Once the web server has started, call from another terminal:

~~~bash
curl -i http://localhost:8080/flow
~~~

With only the demonstration endpoint, port 8080 free, and no Spring Security or other custom filter blocking the request, the HTTP response has status **200 OK** and the exact body:

~~~text
ok
~~~

In addition to Spring Boot startup logs, the **six lines explicitly printed by the example code**, in order, are:

~~~text
Filter before
Interceptor pre
Controller
Interceptor post
Interceptor afterCompletion
Filter after
~~~

Order explanation:

1. `RequestTraceFilter` is called by the Servlet container before `DispatcherServlet`.
2. `filterChain.doFilter` proceeds into Spring MVC.
3. `DispatcherServlet` locates `FlowController.flow()`, then calls `preHandle`.
4. The controller prints `Controller` and returns the string `ok`.
5. `DispatcherServlet` completes the synchronous path, calling `postHandle`, then `afterCompletion`.
6. Control returns to the filter's `finally` block and prints `Filter after`.

Try changing `return true` in `preHandle` to `return false` **only to understand the mechanism in a test environment**: the controller will be skipped; if the interceptor does not set a status/body itself, the response may not match what the client expects. A real interceptor that blocks a request must produce a response with an appropriate status and message.

## 7. Request Body, Response Body, and Common Errors

When a request contains JSON:

~~~text
POST /api/orders
Content-Type: application/json
{"productId":10,"quantity":2}
~~~

A filter can inspect headers first, but deserializing into a Java object for `@RequestBody` is typically performed by an `HttpMessageConverter` inside Spring MVC. If the content type is unsupported, the JSON is invalid, or validation fails, the handler may not execute at all.

For JSON responses, `@RestController` or `@ResponseBody` typically triggers a return-value handler and a JSON message converter (usually Jackson when the dependency is present). This happens **inside** the MVC pipeline; the Servlet container is responsible for transmitting bytes over the HTTP connection and managing response state.

Some typical failure points:

| Scenario | Layer usually handling it | Symptom |
|---|---|---|
| Filter blocks header or rate limit | Filter in the Servlet container | Controller does not run |
| Spring Security rejects request | Security filter chain before MVC | Typically 401 or 403 depending on configuration |
| No matching mapping | `DispatcherServlet` / `HandlerMapping` / resource handler | Typically 404 |
| Matching URL, unsupported HTTP method | MVC mapping / exception resolution | Typically 405 |
| Malformed JSON request body | Argument resolution / `HttpMessageConverter` | Typically 400 |
| Controller throws a handled exception | `HandlerExceptionResolver` / `@ExceptionHandler` | HTTP status/body per handler |
| Unhandled exception | Container error handling / Spring Boot error dispatch | Typically 500 or other error depending on case |

Do not assume every 4xx or 5xx error comes from an exception thrown by a controller. Where the error originates determines which mechanism gets a chance to handle it.

## 8. Exception Handling and Error Dispatch

In Spring MVC, `HandlerExceptionResolver` is responsible for finding a way to handle exceptions thrown while resolving or invoking a handler. Familiar mechanisms include:

- `@ExceptionHandler` placed in a controller or `@ControllerAdvice`/`@RestControllerAdvice`.
- Resolvers handling exceptions raised by Spring MVC itself, such as unsupported methods or parameter errors.
- Spring Boot/container fallback mechanisms when an error is not resolved into an appropriate response.

**An exception thrown in a filter before entering `DispatcherServlet` is not automatically resolved by `@ControllerAdvice`**. Because `DispatcherServlet` has not yet taken control of dispatching the request at that point, filter error handling requires a filter/security/container mechanism or an intentional forward with purpose-built logic.

When an unhandled error occurs, the container may trigger an **ERROR dispatch** to the error path (typically `/error` in Spring Boot). This is a separate dispatch, so which filters run again depends on their registered dispatcher types and filter rules. Do not assume every filter always runs strictly once for the entirety of a request.

A **committed** response (whose headers/body have already been sent) cannot have its status or headers arbitrarily modified. For example, if part of the response has already been streamed before an error occurs, the error handler may be unable to produce a complete new JSON error body. Therefore, logging or response wrapping must account for commit timing.

### 8.1. Why Might postHandle Not Run?

For a successful synchronous request, `postHandle` is normally called as in the example. When an exception occurs in the handler or during return-value handling, Spring MVC may jump straight to the exception resolver path, so **you cannot rely on `postHandle` as a guaranteed callback for every request**.

`afterCompletion` is more useful for cleaning up state tied to an MVC handler under the interceptor model, but it likewise should not be expected to run when a filter blocks the request before `DispatcherServlet`. A `Filter` uses `try/finally` around `chain.doFilter` when resource cleanup is needed at the Servlet layer.

## 9. Asynchronous Processing (Async Dispatch) Changes the Flow

Spring MVC supports asynchronous return types such as `Callable`, `DeferredResult`, `WebAsyncTask`, and certain streaming types. When a handler starts Servlet async processing, the initial thread can return to the container before the work and response finish.

A representative sequence:

~~~text
Initial REQUEST dispatch
  FilterChain
    DispatcherServlet
      HandlerInterceptor.preHandle
      Controller starts async task
      AsyncHandlerInterceptor.afterConcurrentHandlingStarted (if supported)
  Initial thread returns to container

Async task completes
  Container ASYNC dispatch
    FilterChain if registered for ASYNC
      DispatcherServlet resumes processing result
      MVC finalizes response and lifecycle callbacks
~~~

This is a high-level model, not a guarantee that every async form produces the exact same number of callbacks. Depending on the handler type and filter configuration, `postHandle`/`afterCompletion` might not run on the initial request thread; `AsyncHandlerInterceptor.afterConcurrentHandlingStarted` exists for this situation.

If the application needs a correlation ID, MDC, or trace context across threads, a proper context propagation mechanism is required. Simply putting data into a `ThreadLocal` on the request thread and expecting another thread to see it automatically is incorrect.

`@Async` invoking a method in the background **does not automatically mean** the HTTP request is processed via the Servlet async lifecycle. Distinguish a regular task executor from MVC async return-type mechanisms.

## 10. Filter, Interceptor, or ControllerAdvice?

Choose the extension point based on where you want to sit in the pipeline:

- **Filter** for things that must happen before Spring MVC, or apply to other Servlets and URLs: request ID, security chain, request wrapping, HTTP policies.
- **HandlerInterceptor** for things that need to know the Spring MVC handler: per-controller metrics, handler-related conditions, timing within the MVC pipeline.
- **@ControllerAdvice / @ExceptionHandler** for handling exceptions raised within Spring MVC scope: standardizing status codes and error bodies.
- **@RestController / @Controller** for HTTP endpoints, request binding, and invoking business logic.
- **Service** for testable, reusable business logic, avoiding stuffing logic into filters or interceptors.
- **Servlet container config** for connection limits, threads, TLS, HTTP connectors, and embedded server runtime properties.

For example, JWT authentication should use Spring Security at the appropriate position in the security chain; standardizing `MethodArgumentNotValidException` should use MVC exception handling; business authorization checks may require method security authorization and services.

## 11. Filter Configuration and Double-Registration Bugs

In Spring Boot, a Servlet Filter can be registered via `@Component` on a bean implementing `Filter`, or via a `FilterRegistrationBean` with specific URL patterns, order, and dispatcher types. Avoid letting the same filter auto-register as a bean while also manually registering another instance without control, as this can execute the logic twice for the same request.

Example fragment registering a filter by URL and order, used inside a `@Configuration` class that already has a `requestTraceFilter` bean:

~~~java
@Bean
FilterRegistrationBean<RequestTraceFilter> traceRegistration(
        RequestTraceFilter requestTraceFilter
) {
    FilterRegistrationBean<RequestTraceFilter> registration =
            new FilterRegistrationBean<>();
    registration.setFilter(requestTraceFilter);
    registration.addUrlPatterns("/api/*");
    registration.setOrder(10);
    return registration;
}
~~~

This is a **fragment**; it requires importing `FilterRegistrationBean`, `@Bean`, and having the corresponding filter class. If you choose this registration approach, ensure there is only one intentional registration. Note that the filter is selected by the `/api/*` URL pattern at the Servlet layer, so another MVC route that does not match that pattern will not go through this registration.

Do not set an order assuming "10 definitely runs before Spring Security." Inspect the actual `FilterRegistrationBean`s, Spring Boot's default filters, and your Security configuration. The order of security filters **inside** `FilterChainProxy` is managed separately by Spring Security.

## 12. Testing the Request Lifecycle and Diagnosing Issues

### 12.1. Unit Testing at the MVC Layer

`MockMvc` helps verify controller mapping, validation, MVC interceptors, exception handling, and filters included in the test configuration. However, `MockMvc` is not a real TCP server. A passing `MockMvc` test does not prove that the Tomcat connector, TLS, socket timeouts, or native Servlet dispatches behave identically in production.

### 12.2. Testing Through a Real Embedded Server

For integration testing:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpFlowTest {
    // Send HTTP requests to the random port started by the test;
    // use TestRestTemplate, RestClient, or a suitable HTTP client.
}
~~~

This is a fragment illustrating the test setup option, not a complete test class. When integrating, use `@LocalServerPort` or Spring Boot Test utilities to obtain the actual port, call the endpoint over HTTP, and verify that filters/controllers receive the request.

### 12.3. Symptoms and Investigation Steps

**Controller is not called:**
1. Verify the URL, context path, HTTP method, and port.
2. Check the status code and filter/security logs.
3. Check whether a filter calls `chain.doFilter`.
4. Check whether `HandlerMapping` matches the request.

**Controller is called, but the response is wrong:**
1. Check the return-value handler and message converters.
2. Check `produces`/`Accept`/`Content-Type`.
3. Check whether a filter modifies response headers/body on the way out.
4. Check the exception resolver, response commit state, and error dispatch.

**Filter or interceptor runs twice:**
1. Check for duplicate bean/registration declarations.
2. Check `REQUEST`, `ASYNC`, `ERROR`, `FORWARD` dispatcher types.
3. Check whether the request triggers async processing or an error dispatch.
4. Check `OncePerRequestFilter` rules and how logs are being recorded.

**High latency even though the controller is fast:**
1. Measure time before the controller is invoked (filters, security, argument binding).
2. Measure time after the controller (serialization, view rendering, response filters).
3. Check the thread pool, HTTP connector, large request bodies, DB/client calls, and network time.
4. Correlate tracing spans, metrics, and logs by request ID, not just the duration of a controller method.

Avoid logging request bodies, cookies, `Authorization` headers, or personal data in excessive detail. With async or multiple threads, stdout printing alone is insufficient to determine multi-request ordering; request IDs, timestamps, and trace IDs are needed to correlate data accurately.

## 13. Checklist for Mastering the Spring MVC Flow

- Confirm the application runs on the **Servlet web stack**, not confusing it with the WebFlux reactive pipeline.
- Distinguish the **container/connector** (accepting HTTP), **FilterChain** (blocking or wrapping requests), and **DispatcherServlet** (orchestrating MVC).
- Know that `chain.doFilter` passes the request through the next filter toward the servlet.
- Understand that `HandlerMapping` finds the handler, and `HandlerAdapter` invokes the controller and handles binding/return values.
- Know the interceptor callbacks `preHandle`, `postHandle`, `afterCompletion` and their limits during exceptions and async processing.
- Place authorization/security properly in the Spring Security filter chain; do not expect controller advice to catch every filter exception.
- Understand that JSON deserialization/serialization happens in argument/return-value handling; the controller is not the only place where errors can arise.
- Check dispatcher types when a filter appears to run again on `ASYNC` or `ERROR` dispatches.
- Use `MockMvc` to test MVC logic, and integration tests with a real embedded server to test end-to-end behavior.
- Measure all three phases—before controller, inside controller, and after controller—when optimizing latency.

**Remember:** a request passes through the Servlet container and registered filters **before** reaching `DispatcherServlet`. `DispatcherServlet` then selects the handler, invokes interceptors and the controller, and finalizes the MVC response. On the way back out, filters continue executing the code after `chain.doFilter`. Distinguishing these layers properly is the foundation for placing HTTP logic, security, exception handling, and performance observability in the exact right spot.