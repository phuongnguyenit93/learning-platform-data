# Servlet Container, Filter Chain, and the DispatcherServlet Entry Point in Spring Web MVC

## 1. Goals and Scope

When a browser calls `GET /api/hello?name=Lan`, the `@GetMapping` method is not the first component to receive the request. In a Spring Web MVC application running on the Servlet stack, the **Servlet container** accepts the request; matching registered **Servlet Filters** get a chance to process it; only then does the request reach **`DispatcherServlet`** so Spring MVC can locate the controller and produce a response.

After this lesson, you will be able to:
- Accurately describe the boundary between the HTTP server/Servlet container, the Filter chain, and Spring MVC.
- Trace the flow `client → container → filters → DispatcherServlet → handler → response`, including both short-circuited and error branches.
- Distinguish a Servlet `Filter` from a Spring MVC `HandlerInterceptor` and the Spring Security filter chain.
- Register a filter yourself using `FilterRegistrationBean` in Spring Boot, controlling URL patterns, order, and dispatcher types.
- Understand why `OncePerRequestFilter` does not simply mean running strictly once across *every* dispatch of an entire request.
- Verify the flow using an executable Java 17 + Spring MVC application and MockMvc tests.

This lesson focuses on **Jakarta Servlet-based Spring Web MVC** (Spring Framework 6.x / Spring Boot 3.x), and does not cover the WebFlux reactive pipeline. The runnable examples use Spring Boot to start embedded Tomcat; the Servlet/Filter/DispatcherServlet principles still apply if you deploy Spring MVC as a WAR to a standalone container.

## 2. Who Owns Which Part of the Request?

```text
             +------------------- HTTP client --------------------+
             | GET /api/hello?name=Lan                          |
             +----------------------------+----------------------+
                                          |
                               (reverse proxy if any)
                                          |
                                          v
           +------------ Servlet container (Tomcat) ------------+
           |  HTTP connection, parse request, select Servlet map|
           |                                                     |
           |  Servlet Filter chain for the current dispatch      |
           |    Filter A: before chain.doFilter(...)             |
           |      Filter B: before chain.doFilter(...)           |
           |        +-------------------------------------+      |
           |        | DispatcherServlet                  |      |
           |        |  HandlerMapping finds route         |      |
           |        |  HandlerInterceptor.preHandle      |      |
           |        |  HandlerAdapter invokes controller |      |
           |        |  Convert return value to body      |      |
           |        |  (or ViewResolver renders view)    |      |
           |        +-------------------------------------+      |
           |      Filter B: after chain.doFilter(...)            |
           |    Filter A: after chain.doFilter(...)              |
           +----------------------------+------------------------+
                                        |
                                        v
                                 HTTP response
```

The diagram illustrates the **successful, synchronous** path of a request allowed through by the filters. It is not a fixed sequence for every configuration: a filter may return a response early, the servlet may be something other than `DispatcherServlet`, an exception may trigger an error dispatch, and async processing may add subsequent dispatches.

| Layer | Managed by | Role | What information does it know beforehand? |
|---|---|---|---|
| Servlet container | Tomcat, Jetty, a compliant Jakarta Servlet container | Accepts HTTP, manages Servlets/Filters, mapping, dispatching, request/response objects, threads, or async lifecycle. | URI, method, headers, mappings, and container configuration. |
| Servlet `Filter` | Servlet container | Wraps request/response, applies cross-cutting policies, passes through via `chain.doFilter`, or terminates early. | `HttpServletRequest` and `HttpServletResponse`; does not yet need to know the Spring MVC handler. |
| `DispatcherServlet` | Spring MVC; registered as a Servlet with the container | Central entry point (front controller) of Spring MVC; dispatches to Spring components. | Spring `WebApplicationContext`, mappings, and MVC configuration. |
| `HandlerMapping` | Spring MVC | Finds the handler matching the request; may also return an interceptor chain. | Registered mappings; method/path/headers/params per mapping conditions. |
| `HandlerAdapter` | Spring MVC | Invokes the selected handler, resolves arguments, and handles the return value. | Controller/method signature along with adapters, resolvers, and converters. |
| `HandlerInterceptor` | Spring MVC | Hooks around handling of a Spring MVC-mapped handler, e.g., `preHandle`, `postHandle`, `afterCompletion`. | The selected handler; does not replace Servlet container filters. |

**Do not equate a Servlet Filter with a Spring MVC interceptor.** A filter runs at the container layer and can apply to requests that never reach a controller. An interceptor belongs to Spring MVC and attaches to the handler execution chain after mapping resolution; its callback scope and exception/async behavior also differ.

## 3. What Steps Does the Servlet Container Perform?

For an HTTP request entering a Servlet application:

1. The container accepts the connection/request, parses HTTP, manages the lifecycle of `HttpServletRequest`/`HttpServletResponse` objects, and determines the context path and Servlet mapping.
2. From the URL pattern, Servlet name, filter order, and current **dispatcher type**, the container selects the matching Filter registrations.
3. The container builds a `FilterChain` and invokes `doFilter(request,response,chain)` on the first filter. Each filter has the authority to call `chain.doFilter(...)` to pass control to the next element.
4. After the last filter, the container invokes the mapped Servlet. For Spring MVC, this is typically `DispatcherServlet.service(...)` and the associated framework processing.
5. When the Servlet finishes synchronous processing, `chain.doFilter(...)` calls unwind in stack order; code after it in each filter executes from the inside out. The container finalizes the response; the response may have already been committed earlier.

**Important:** "entering the Servlet" is the container's Servlet mapping step, which is distinct from "selecting a controller" performed by `HandlerMapping` inside Spring MVC. A filter can run before Spring even determines whether any controller matches the request. If there is no matching MVC route, Spring MVC may return 404; filters that were invoked can still execute their `finally` branches.

### Servlet Mapping and Filter Mapping

- A Servlet mapping of `/` typically lets `DispatcherServlet` handle application routes, though a configuration may use another prefix, such as `/mvc/*`.
- A filter mapping of `/*` typically covers requests across the web application. It can be scoped to `/api/*` or mapped by servlet name.
- Filter mapping is a **container** configuration, independent of `@GetMapping` or `@RequestMapping`.
- URLs have distinct context paths, servlet paths, and path info. Do not confuse `request.getRequestURI()` (which typically includes the context path, without the query string) with a Spring MVC path template or `getQueryString()`.
- Reverse proxies, load balancers, and containers may process the request target or forwarded headers before the request reaches Spring. Do not treat raw client-supplied headers as trustworthy evidence of origin/protocol if proxy trust is not properly configured.

### A Filter Chain Is a Call Stack

With two filters A then B:

```text
A: before
  B: before
    DispatcherServlet -> Controller -> Response
  B: after
A: after
```

Pseudo-code:

```java
// This is flow pseudo-code, not a standalone runnable Java file.
void doFilter(Request request, Response response, FilterChain chain) {
    before(request);
    try {
        chain.doFilter(request, response);
    } finally {
        after(response);
    }
}
```

If B **does not call** `chain.doFilter`, neither C nor `DispatcherServlet` is invoked on that branch; the container can return the response produced by B itself. This is valid when B rejects access, enforces rate limiting, or returns a CORS preflight response according to a designed policy. You must explicitly set the status and response to return, rather than simply skipping the chain and leaving the client with a confusing result.

### Short-Circuiting, Exceptions, and Response Commit

- `chain.doFilter` can throw `ServletException` or `IOException`. `finally` still runs, which does not mean the request succeeded.
- If the response has already been committed (headers/body already sent), a filter cannot arbitrarily change the status/headers or rewrite the body.
- A filter can wrap the request/response using wrappers to adjust behavior, but it must adhere to the Servlet contract, handle streams carefully, and avoid draining the request body before the controller runs.
- The `finally` block is typically suitable for clearing context/`ThreadLocal`, measuring timing, and completing instrumentation; avoid logging sensitive data.

## 4. `DispatcherServlet` — Spring MVC's Front Controller

`DispatcherServlet` is a real Servlet, invoked by the container **after filters have allowed the request to proceed**. It does not accept TCP sockets directly, does not decide the order of Servlet filters, and does not replace the container in managing the Servlet lifecycle.

Inside Spring MVC, the typical processing path for a synchronous request is:

```text
DispatcherServlet
    |
    +--> find HandlerExecutionChain via HandlerMapping
    |      |-- handler (usually a HandlerMethod)
    |      +-- interceptor(s)
    |
    +--> HandlerInterceptor.preHandle(...)
    |      |-- false: stop before invoking handler
    |      +-- true: continue
    |
    +--> HandlerAdapter.handle(...)
    |      +-- resolve @PathVariable / @RequestParam / @RequestBody ...
    |      +-- convert/bind/validate data when configured appropriately
    |      +-- invoke controller
    |      +-- handle return value
    |
    +--> Response path
    |      |-- @ResponseBody/@RestController:
    |      |      HttpMessageConverter writes JSON/text/...
    |      +-- MVC view:
    |             ModelAndView -> ViewResolver -> render
    |
    +--> postHandle/afterCompletion per lifecycle
           or HandlerExceptionResolver on exception
```

Common components:

| MVC Component | Purpose |
|---|---|
| `RequestMappingHandlerMapping` | Reads mappings such as `@GetMapping`, `@PostMapping`, `@RequestMapping` and locates the handler. |
| `RequestMappingHandlerAdapter` | Invokes annotated controller methods and uses argument/return-value resolvers. |
| `HandlerMethodArgumentResolver` | Supplies controller parameters such as `@RequestParam`, `@PathVariable`, `@RequestBody`. |
| `HttpMessageConverter` | Converts the request body into an object or a return object into an HTTP body, such as JSON. |
| `ViewResolver` | Selects a view to render in page-returning MVC; JSON-returning APIs typically do not need view resolution. |
| `HandlerExceptionResolver` | Attempts to resolve exceptions at the MVC layer; for example `@ExceptionHandler` or `@ControllerAdvice`. |
| `HandlerInterceptor` | Hooks around the MVC handler; only operates within the configured MVC handling flow. |

The actual processing path has additional steps, such as multipart, locale, conditional requests, async handling, and the case where no handler is found. **Do not assume** every request passes through every callback or always uses a `ViewResolver`. For a `@RestController` returning a `Map`, the response body is usually written directly by an `HttpMessageConverter` when the adapter handles the return value; `postHandle` is not a good place to modify an already-serialized JSON body.

### What If No Handler Is Found?

Spring MVC may return 404 or throw an exception depending on configuration and route type. However, any filter that matched and called `chain.doFilter` still wraps the request; a Spring Security filter or custom container filter may reject the request before MVC even selects a handler. Therefore, when debugging 401/403, do not jump to concluding that `@GetMapping` is wrong.

## 5. Runnable Example: Observing Filters Before and After the Controller

The example uses **Java 17**, Spring Boot **3.5.16**, Spring MVC, and Gradle. Spring Boot is used to configure embedded Tomcat and register `DispatcherServlet` automatically. In a plain Spring Framework MVC project, you must register the Servlet with the container yourself (via `web.xml`, `WebApplicationInitializer`, or an equivalent Servlet initializer).

### 5.1. Project Structure

```text
servlet-pipeline-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/pipeline/
    │   │   ├── PipelineApplication.java
    │   │   └── web/
    │   │       ├── HelloController.java
    │   │       ├── TraceFilter.java
    │   │       └── TraceFilterConfig.java
    │   └── resources/application.properties
    └── test/java/com/example/pipeline/
        └── HelloControllerTest.java
```

If creating the project from https://start.spring.io/, choose Gradle/Groovy, Java 17, Spring Boot 3.5.x, and the **Spring Web** dependency; the Gradle Wrapper is generated by Initializr. The following listings provide the complete contents for the main files; packages must match the paths under `src/main/java` or `src/test/java`.

`settings.gradle`:

```groovy
rootProject.name = 'servlet-pipeline-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-web` in Spring Boot 3.5.x pulls in Spring MVC, Jackson for JSON, and embedded Tomcat. Spring Boot manages framework/transitive dependency versions. If your application already uses a dedicated BOM/platform, follow the project's dependency management model rather than copying the example configuration verbatim.

`src/main/resources/application.properties`:

```properties
spring.application.name=servlet-pipeline-demo
server.port=8080
```

### 5.2. Bootstrap Class

`src/main/java/com/example/pipeline/PipelineApplication.java`:

```java
package com.example.pipeline;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PipelineApplication {

    public static void main(String[] args) {
        SpringApplication.run(PipelineApplication.class, args);
    }
}
```

`@SpringBootApplication` enables auto-configuration and component scanning from package `com.example.pipeline` down into subpackages. Spring Boot creates/registers `DispatcherServlet` alongside the embedded server when it detects a suitable Servlet web stack; this is why we do not have to write `web.xml` in this example.

### 5.3. Controller Located by `DispatcherServlet`

`src/main/java/com/example/pipeline/web/HelloController.java`:

```java
package com.example.pipeline.web;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/api/hello")
    public Map<String, String> hello(
            @RequestParam(name = "name", defaultValue = "friend") String name) {

        System.out.println("controller: handle name=" + name);
        return Map.of("message", "Hello, " + name + "!");
    }
}
```

For `GET /api/hello?name=Lan`, this annotated handler is selected by `RequestMappingHandlerMapping` and invoked by `RequestMappingHandlerAdapter`. The `Map` return value is serialized to JSON by a Jackson-based message converter. No `ViewResolver` is needed for this endpoint.

### 5.4. Writing a Servlet Filter to Observe the Pipeline

`src/main/java/com/example/pipeline/web/TraceFilter.java`:

```java
package com.example.pipeline.web;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

public class TraceFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String path = request.getRequestURI();
        System.out.println("filter: before " + request.getMethod()
                + " " + path + " dispatch=" + request.getDispatcherType());

        try {
            chain.doFilter(request, response);
        } finally {
            System.out.println("filter: after status=" + response.getStatus());
        }
    }
}
```

This is a complete Java class using the `jakarta.servlet.*` package compatible with Spring Framework 6.x. `OncePerRequestFilter` provides a `Filter.doFilter` implementation that handles the already-filtered marker and decides whether to skip async/error dispatches per its contract. Under normal conditions, custom code only needs to override `doFilterInternal`.

Why use `try/finally`? If the controller or a downstream filter throws an exception, the cleanup branch still gets a chance to run. However, the status visible in `finally` may not yet be the final status written by the container after exception handling or an error dispatch. Do not infer that logging `status=200` after an exception guarantees the client received HTTP 200.

### 5.5. Registering the Filter via `FilterRegistrationBean`

`src/main/java/com/example/pipeline/web/TraceFilterConfig.java`:

```java
package com.example.pipeline.web;

import jakarta.servlet.DispatcherType;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration
public class TraceFilterConfig {

    @Bean
    FilterRegistrationBean<TraceFilter> traceFilterRegistration() {
        FilterRegistrationBean<TraceFilter> registration =
                new FilterRegistrationBean<>();

        registration.setFilter(new TraceFilter());
        registration.setName("traceFilter");
        registration.addUrlPatterns("/api/*");
        registration.setDispatcherTypes(DispatcherType.REQUEST);
        registration.setOrder(Ordered.LOWEST_PRECEDENCE - 10);
        return registration;
    }
}
```

Meaning of each option:

- `setFilter(new TraceFilter())` creates the filter instance for the Servlet container to register.
- `addUrlPatterns("/api/*")` restricts the URL pattern rather than running on all requests. This pattern follows Servlet URL matching rules, not Spring MVC `PathPattern`.
- `setDispatcherTypes(DispatcherType.REQUEST)` lets the filter observe the **initial request dispatch** in the example; it does not automatically run on `ASYNC`, `ERROR`, or `FORWARD`.
- `setOrder(Ordered.LOWEST_PRECEDENCE - 10)` sets the relative priority of the filter registration within the Boot-managed group. Lower numeric values are generally ordered earlier; never assume ordering relative to every container, security, or library filter without checking the configuration.
- `setName(...)` gives the registration a clear name, convenient when inspecting logs/registrations.
- `@Bean` registers the **`FilterRegistrationBean`** itself. `TraceFilter` is instantiated here and **not annotated with `@Component`**, avoiding the risk of registering the same filter a second time via filter-bean auto-registration.

Spring Boot has auto-registration for Servlet `Filter` beans, but when you need control over order, dispatcher types, and URL patterns, `FilterRegistrationBean` is more transparent. Avoid combining `@WebFilter`, `@Component`, and `FilterRegistrationBean` for the same filter unless you clearly understand how the container handles overlapping registrations.

### 5.6. Running and Observing

If the project has a Gradle Wrapper, from the project root:

```bash
# Linux/macOS
./gradlew test
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat bootRun
```

In another terminal:

```bash
curl -i "http://localhost:8080/api/hello?name=Lan"
```

On Windows PowerShell you can use `curl.exe -i "http://localhost:8080/api/hello?name=Lan"` to make sure you invoke the curl executable.

Expected response body:

```json
{"message":"Hello, Lan!"}
```

A meaningful application log sequence during a **successful, synchronous GET request** is:

```text
filter: before GET /api/hello dispatch=REQUEST
controller: handle name=Lan
filter: after status=200
```

Other Spring Boot and container logs may appear in between; these are **the three lines printed by the example code in relative order**, not the entire stdout of the program. Do not conclude from logs alone that filter A always runs before filter B when other dependencies are added or registration orders change.

Calling another endpoint that does not start with `/api/`, such as `GET /not-found`, will not trigger `TraceFilter` because the example pattern is restricted to `/api/*`. If you call `GET /api/missing`, the filter can still print `before` and `after` even though no controller matches; Spring MVC handles the 404 after the request passes through the filter.

## 6. Testing with MockMvc

`src/test/java/com/example/pipeline/HelloControllerTest.java`:

```java
package com.example.pipeline;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class HelloControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void requestPassesThroughMvcAndReturnsJson() throws Exception {
        mvc.perform(get("/api/hello").param("name", "Lan"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello, Lan!"));
    }

    @Test
    void queryParameterDefaultsWhenMissing() throws Exception {
        mvc.perform(get("/api/hello"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello, friend!"));
    }
}
```

`@SpringBootTest` loads the Spring context; `@AutoConfigureMockMvc` configures MockMvc. By default, auto-configured MockMvc also registers filter beans in the appropriate context to test requests through the web layer. This is a test **in a mock servlet request environment**, without real HTTP sockets or Tomcat. The test above does not directly assert log lines or container dispatcher mapping, so it mainly proves controller mapping + response.

If the goal is to test exact Servlet filter registration, ordering, `DispatcherType.ERROR`, or async dispatches through a real container, add an integration test starting a server on a random port with `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` and an appropriate HTTP client. The behavior of proxies, Tomcat, filter registrations, and servlet dispatcher types is only fully verified along a real request/container path.

## 7. Distinguishing Servlet Filter, MVC Interceptor, and Spring Security

| Aspect | Servlet Filter | Spring MVC HandlerInterceptor | Spring Security filter chain |
|---|---|---|---|
| Layer | Servlet container | Inside Spring MVC | Inside a Servlet Filter proxy/chain |
| Execution point | Before the mapped Servlet is invoked, for mapped dispatcher types | After MVC finds a handler and before/after handler execution per callbacks | In the Servlet filter chain, typically before MVC controllers |
| Can short-circuit request? | Yes, by not calling `chain.doFilter` | Yes, by returning `false` from `preHandle` | Yes, checks authentication/authorization and decides whether to continue or return an error |
| Sees handler method? | Not by default | `preHandle(..., Object handler)` receives the selected handler | Does not depend on MVC mapping by default, though it can integrate further |
| Typical uses | Logging, correlation IDs, request wrapping, encoding, CORS handling | Handler-specific logic, MVC timing, populating model/locale | Authentication, authorization, CSRF, and security context |

With Spring Security, the Servlet `DelegatingFilterProxy` can delegate calls to the Spring bean named `springSecurityFilterChain` (typically `FilterChainProxy`). Inside it, Spring Security selects a `SecurityFilterChain` matching the request. Thus there are **two "chain" concepts**:

```text
Container FilterChain
    |
    +-- regular filter
    +-- DelegatingFilterProxy
    |     |
    |     +-- Spring Security FilterChainProxy
    |            +-- SecurityFilterChain selected per request
    |                  +-- security filters...
    |
    +-- DispatcherServlet
          +-- Spring MVC HandlerExecutionChain
                +-- MVC interceptors
                +-- controller
```

Spring Security is not automatically present in the demo just by using `spring-boot-starter-web`; to integrate it, the project needs the corresponding security dependency and configuration.

You **should not** implement security solely via `HandlerInterceptor`: some requests never reach an MVC handler, and authentication/authorization rules often need to run before handler selection or across the entire relevant surface. Spring Security provides a dedicated filter chain model and specialized extension points.

### Interceptor Callbacks Do Not Match Filter Callbacks

A `HandlerInterceptor` has:
- `preHandle(request,response,handler)`: runs before the handler and can return `false` to stop execution.
- `postHandle(request,response,handler,modelAndView)`: follows the handler when applicable; with `@ResponseBody`, the body may already be written by the converter, so it is not a hook for arbitrary body modification.
- `afterCompletion(request,response,handler,exception)`: runs after MVC processing completes for participating interceptors under the corresponding callback semantics, typically used for cleanup; not guaranteed on every branch, for example an interceptor that returned `false` before being added to the completed execution chain.

An interceptor does not replace a filter's `try/finally` block, and a filter does not replace MVC argument/return-value processing.

## 8. Dispatcher Types: Why the Same Request Can Pass Through a Filter Multiple Times

`jakarta.servlet.DispatcherType` classifies how a Servlet dispatch is invoked. The primary values are:

| Type | When it typically occurs |
|---|---|
| `REQUEST` | Client sends a normal request to the container. |
| `FORWARD` | Server performs `RequestDispatcher.forward(...)` to another resource/Servlet. |
| `INCLUDE` | Server performs `RequestDispatcher.include(...)` to include the output of another resource. |
| `ASYNC` | Servlet async processing dispatches the request at a later stage. |
| `ERROR` | Container performs an error dispatch to an error page/Servlet mapping after certain errors or `sendError`. |

A **filter registration** must include the appropriate dispatcher type for the container to invoke the filter on that kind of dispatch. If no type is specified, per the Servlet spec the default behavior is typically `REQUEST`; Boot configuration and individual registrations may add types. For instance, `TraceFilter` explicitly sets only `REQUEST` to keep logging transparent.

`OncePerRequestFilter` adds another layer of once-per-dispatch-and-execution-flow control. It **does not automatically expand the filter registration** to receive async/error dispatches. By default:
- `shouldNotFilterAsyncDispatch()` returns `true`: skips subsequent async dispatches.
- `shouldNotFilterErrorDispatch()` returns `true`: skips corresponding error dispatches.
- If you want to handle async/error, you must check **both conditions**: whether the container registration maps that type, and whether `OncePerRequestFilter` permits internal execution.
- You cannot infer from the class name "OncePerRequestFilter" that it runs strictly *once for the entire HTTP request* when multiple dispatches or different threads are involved; the actual contract is once per dispatch matching those conditions.

Example of adding types to another filter configuration (illustrative):

```java
registration.setDispatcherTypes(
        DispatcherType.REQUEST,
        DispatcherType.ASYNC,
        DispatcherType.ERROR);
```

If the class still extends `OncePerRequestFilter` and does not override `shouldNotFilterAsyncDispatch`/`shouldNotFilterErrorDispatch`, adding dispatcher types is **not enough** to make `doFilterInternal` run for subsequent dispatches. For any async filter, you must also check async support on the filter/Servlet registration and resource lifecycles.

### Error Dispatch Differs from MVC Exception Handling

There are two scenarios:

1. A handler throws an exception and Spring MVC's `HandlerExceptionResolver` handles it (e.g., `@ExceptionHandler` returning `ResponseEntity`). The response can be written immediately during the current MVC dispatch; the container does not necessarily create an `ERROR` dispatch.
2. The exception is not handled within MVC, or the container receives an error-handling request (e.g., `sendError`). The container may perform an `ERROR` dispatch to an error mapping, such as Spring Boot's `/error`. This can be a new dispatch pass with different filter mappings.

Do not assume every HTTP 4xx/5xx goes through `DispatcherType.ERROR`. Furthermore, how containers handle nested error dispatches can vary; verify empirically when building logging/security filters.

### Async Requests

An MVC controller can return `Callable<T>`, `DeferredResult<T>`, or use a corresponding async mechanism. The initial thread may exit the filter chain while the response is **not yet complete**. Another async dispatch may occur on a different thread and re-enter the container/`DispatcherServlet`.

Consequences:
- The `finally` block of the initial filter invocation does not always mark "response finished sending" in the async case.
- Values in `ThreadLocal` do not automatically propagate to other threads; propagation/cleanup must be managed per the corresponding contract.
- Filter "before/after" logs may reflect a single dispatch rather than the full end-to-end duration of the request.
- If you need to measure actual completion of an async request, use an async lifecycle listener or compatible observability mechanism rather than simply taking the interval between two log lines of the first filter.

## 9. Configuring Filter Order and Execution Timing

When there are multiple filters, ordering is part of behavior: encoding, request wrapping, security, caching, metrics, or logging may need to run before/after others. In Spring Boot, order can be set via `FilterRegistrationBean.setOrder(...)` or supported ordering mechanisms for filter beans; which priority is appropriate depends on the functionality.

Sample:

```java
registration.addUrlPatterns("/api/*");
registration.setDispatcherTypes(DispatcherType.REQUEST);
registration.setOrder(100);
```

This configures **one** specific registration. There is no guarantee that your filter is the first filter in the entire container just because of the number `100`; framework and container filters may have other registrations. To inspect Spring Boot's filter registrations, enable web-related logging when checking the environment:

```properties
logging.level.web=debug
```

After diagnosing, you can turn off debug logging to reduce log volume. Interpret logs based on the active configuration and URL patterns, rather than assuming `@Order` on a `@Bean` method will always dictate filter order; in Spring Boot, when explicit filter order control is needed, set it via `FilterRegistrationBean`.

### Registering with the Plain Servlet API

Without Spring Boot, a container can register filters in `web.xml` or via the Servlet API:

```java
// Illustrative snippet at ServletContext startup, not a standalone program.
FilterRegistration.Dynamic registration =
        servletContext.addFilter("traceFilter", new TraceFilter());

registration.addMappingForUrlPatterns(
        java.util.EnumSet.of(DispatcherType.REQUEST),
        false,
        "/api/*");
```

Here `servletContext` is available in a Servlet initialization callback; this code **does not** belong in a controller and does not run automatically if pasted into an arbitrary class. In a Spring Boot embedded container, `ServletContextInitializer`/registration beans are the right integration point; do not assume Boot automatically runs every Servlet container `WebApplicationInitializer` the way a plain WAR deployment does.

## 10. Important Processing Branches

### A. Request Proceeds Successfully

```text
REQUEST → Filter.doFilter
        → chain.doFilter
        → DispatcherServlet
        → HandlerMapping / HandlerAdapter
        → Controller
        → Converter / View
        → unwinds to Filter.finally
        → response
```

The filter observes the status after downstream processing, though it may not be the final status if an async/error dispatch occurs later.

### B. Filter Actively Rejects

```text
REQUEST → Authentication/RateLimit Filter
        → check fails
        → response.setStatus(401/429)
        → write valid response
        → do not call chain.doFilter
        → end dispatch
```

Nothing requires the Spring MVC controller to be invoked on this branch. Do not place cleanup logic only in the controller if resources were allocated in a filter.

### C. MVC Handler Not Found

```text
REQUEST → Filter(s) → DispatcherServlet
                     → HandlerMapping: not found
                     → HTTP 404 or exception branch per config
        ← Filter(s) unwind
```

A filter can still log even if no controller exists. If the filter is mapped solely to `/api/*`, a 404 at `/outside` may not run that filter at all.

### D. Exception or HTTP Error

```text
REQUEST → Filter(s) → DispatcherServlet
                      → Controller throws
                      → HandlerExceptionResolver?
                           |-- handled: response produced in MVC
                           +-- unresolved / sendError:
                                    container may ERROR dispatch
```

Filters on the initial request do not automatically receive callbacks for the error dispatch; a separate filter registration mapping `ERROR` with appropriate logic may be needed.

### E. Servlet Async

```text
REQUEST dispatch → filter → Servlet/Controller starts async
                  → initial call stack returns
...
ASYNC dispatch   → a filter chain matching dispatcher types
                  → DispatcherServlet resumes result
                  → completes response
```

The diagram illustrates that a single logical request can span multiple dispatches; applications must test the right request types, containers, and filter mappings.

## 11. Common Errors and Troubleshooting

| Symptom | Possible Cause | Check / Fix |
|---|---|---|
| No `TraceFilter` logs for `/api/hello` | Filter not registered, `@Configuration` bean outside component scan, URL pattern mismatch, request hitting wrong running app. | Check `@Configuration` package, registration logs, port/context path, and dispatcher type. |
| Filter logs appear but no controller log | Upstream filter blocked; Spring Security returned 401/403; handler mapping not found; interceptor stopped before handler. | Check HTTP status, order, matchers, logs, path, and security config. |
| Multiple filter logs for one request | Duplicate filter registration, multiple dispatches, Servlet forward/error/async, logging from multiple filters. | Find all registrations, dispatcher types, and class/names; check `OncePerRequestFilter` logic. |
| `@Order` on `@Bean` method does not change expected order | Filter registration order requires specific configuration; order on bean method is not guaranteed as intended. | Use `FilterRegistrationBean.setOrder(...)` and inspect actual registrations. |
| Empty body reaches controller after filter | Filter read the input stream before the handler without proper buffering/wrapper. | Avoid consuming request body arbitrarily; use a wrapper and proper lifecycle when truly needed. |
| `after` prints status 200 even though request ends in 500 | Exception/async/error dispatch may produce the final status after the current filter exits. | Distinguish status observed at log time from the finalized response. |
| Filter does not run on async/error | Registration does not map the dispatcher type or `OncePerRequestFilter` skips it by default. | Check both `setDispatcherTypes` and `shouldNotFilterAsyncDispatch`/`shouldNotFilterErrorDispatch`. |
| `ClassNotFoundException: javax.servlet...` | Using legacy `javax.servlet` API with Spring Framework 6.x requiring `jakarta.servlet`. | Align framework/container versions and Jakarta imports. |
| Controller exists but returns HTTP 404 | Wrong Servlet mapping/context path, wrong controller route, package scan issue, application not running. | Check `DispatcherServlet` registration and Spring handler mappings. |
| Spring Security authentication does not run for a path | Filter/security matcher or dispatcher types do not cover the desired path. | Review `SecurityFilterChain` matchers, filter registrations, and dispatch types; test over real HTTP. |

### Warnings When Implementing Filters for Security and Audit

- **Do not** log raw Authorization/Cookie headers, passwords, tokens, personal data, or sensitive bodies.
- **Do not** trust `X-Forwarded-*` values directly from clients if the reverse proxy has not established a trust policy.
- **Do not** decode URIs/paths multiple times yourself in a filter to make access control decisions; proxies, containers, and MVC may interpret them differently.
- **Do not** assume controller security rules will execute if a filter returns a response earlier.
- When using `ThreadLocal`/MDC, set and clear per the appropriate lifecycle/dispatch in `try/finally`; watch out for different threads during async.
- For authentication/authorization checks, generally prefer Spring Security's extension points over writing manual header-checking filters for production.

## 12. Hands-on Exercises

1. Run the `servlet-pipeline-demo` application. Send `GET /api/hello?name=Lan` and correlate the three filter/controller/filter log lines with the JSON body.
2. Try `GET /api/missing` and explain why the filter can run while no controller runs.
3. Change `registration.addUrlPatterns("/api/*")` to `"/debug/*"`, rerun, and explain why logs do not appear for `/api/hello` even though the controller still returns JSON.
4. Add a second filter that returns HTTP `403` for a path you specify, ensuring it does not call `chain.doFilter` on the blocking branch. Observe that the controller is not invoked and explain the unwind flow.
5. Create a controller returning `Callable<String>` or `DeferredResult<String>` to examine async. Compare `REQUEST` vs `ASYNC` on a real container before and after changing the dispatcher mapping, and avoid drawing conclusions based on callback counts in MockMvc.

### Self-Check Questions

**Question 1. Does `DispatcherServlet` belong to the container or Spring MVC?**  
It is a Servlet **provided by Spring MVC**, but it must be **registered with the Servlet container**. The container invokes Servlet methods, while `DispatcherServlet` dispatches further to Spring MVC handlers.

**Question 2. Why can a filter run on an endpoint that returns 404?**  
Filters are selected by the container based on URL pattern/dispatcher type before `DispatcherServlet` searches for a handler. A filter does not need to know whether a Spring route exists.

**Question 3. After `chain.doFilter`, does status 200 guarantee the HTTP client receives 200?**  
Not always. There may be an error dispatch, an unhandled exception, or a subsequent async lifecycle. You must inspect the final status at the right observation point.

**Question 4. Does `OncePerRequestFilter` prevent every case of re-execution?**  
No. It manages execution per request dispatch/thread and duplicate-invocation avoidance; async/error dispatches together with the registration determine when internal code is invoked.

**Question 5. Are Spring Security filters MVC interceptors?**  
No. Spring Security's `FilterChainProxy` operates through a Servlet Filter and sits ahead of normal MVC controller processing.

## Official References

- Spring Framework — `DispatcherServlet`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html
- Spring Framework — Processing sequence: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/sequence.html
- Spring Framework — Special bean types (`HandlerMapping`, `HandlerAdapter`, …): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/special-bean-types.html
- Spring Framework — Exception handling: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/exceptionhandlers.html
- Spring Framework — `OncePerRequestFilter` API: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- Spring Boot — Servlet web applications, registration of filters: https://docs.spring.io/spring-boot/reference/web/servlet.html
- Spring Boot — `FilterRegistrationBean` API (3.5): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/FilterRegistrationBean.html
- Jakarta Servlet — Filter and DispatcherType contracts: https://jakarta.ee/specifications/servlet/
