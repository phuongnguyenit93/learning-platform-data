# Servlet Dispatch Types: REQUEST, FORWARD, INCLUDE, ERROR, and ASYNC

> **Context:** Spring Security on the Servlet stack (Jakarta Servlet, Java 17+). A single HTTP request from a browser can be sent by the Servlet container through multiple **dispatches** within the same processing lifecycle. Understanding `DispatcherType` helps analyze servlet flows, write filters properly, and avoid authorization bugs during forwards, error handling, or async processing.

## 1. What Is a Dispatch and How Does It Differ from a New HTTP Request?

When a client sends `GET /demo`, the container selects the appropriate servlet or resource and creates a processing pass where `request.getDispatcherType() == DispatcherType.REQUEST`. During processing, the application can forward internally (`forward`), include content (`include`), enter an error page (`error dispatch`), or resume asynchronous processing (`async dispatch`).

`jakarta.servlet.DispatcherType` has **exactly five values**: `REQUEST`, `FORWARD`, `INCLUDE`, `ERROR`, and `ASYNC`. This represents the **type of the current dispatch**, not an HTTP method, HTTP status, thread type, or URL.

```text
Client --HTTP--> [REQUEST /entry]
                    |-- RequestDispatcher.forward(...) --> [FORWARD /target]
                    |-- RequestDispatcher.include(...) --> [INCLUDE /fragment] --> back to /entry
                    |-- error/sendError + error page ----> [ERROR /error-page]
                    |-- startAsync + AsyncContext.dispatch(...) --> [ASYNC /resumed]
```

The branches above illustrate **possibilities**, not that every request goes through all five types. `forward` and `include` are **in-server** dispatches and do not originate a new HTTP request from the client. `response.sendRedirect(...)` is different: the server returns a redirect status (typically 302) with a `Location` header so the **client sends a new request**; that new request normally has type `REQUEST`.

To observe it in practice, read it directly inside a servlet or filter:

```java
DispatcherType type = request.getDispatcherType();
System.out.println(type); // For example: REQUEST, FORWARD, INCLUDE, ERROR, or ASYNC
```

## 2. Distinguishing the Five Dispatch Types

| Type | When it occurs | Defining characteristics |
| --- | --- | --- |
| `REQUEST` | The container receives a normal HTTP request and routes it to the initial servlet. | Request entry point; the default type when a servlet filter mapping does not declare dispatcher types. |
| `FORWARD` | Code calls `RequestDispatcher.forward(request, response)`. | The container transfers response-generation authority to an internal target, logically with the same request/response; forward must happen before the response commits. |
| `INCLUDE` | Code calls `RequestDispatcher.include(request, response)`. | The target resource appends content into the caller's response and returns control to the caller; the included target must not dictate the response status/headers. |
| `ERROR` | The container dispatches to a configured error page after an error/exception or eligible `sendError`. | Carries `jakarta.servlet.error.*` attributes; merely setting an error status or catching an exception yourself does not necessarily trigger an ERROR dispatch. |
| `ASYNC` | `AsyncContext.dispatch(...)` resumes the request after `startAsync()`. | A re-entry pass through the pipeline for async dispatch; `startAsync()` alone **does not** turn the current pass into ASYNC. |

### 2.1. REQUEST — the initial entry pass

Example: a client sends `GET /orders/42`. The servlet receiving the request on the first pass sees `DispatcherType.REQUEST`. The container selects matching servlet and filter mappings by URL and dispatcher type.

A filter declared with `@WebFilter(urlPatterns = "/*")` that **does not specify** `dispatcherTypes` is mapped only for `REQUEST` per Servlet rules. Consequently, a subsequent forward or error dispatch for the same request can pass through another servlet without that filter being invoked again. Do not assume every filter runs on every dispatch pass.

### 2.2. FORWARD — transferring processing to an internal resource

```java
request.setAttribute("orderId", 42L);
request.getRequestDispatcher("/internal/order-view")
       .forward(request, response);
return; // Avoid writing further content after forward.
```

The container invokes `/internal/order-view` in a `FORWARD` pass. Request attributes set by the caller remain accessible. When forwarding from a normal request, the API provides attributes holding original path details, for instance:

```java
Object originalUri =
    request.getAttribute(RequestDispatcher.FORWARD_REQUEST_URI);
```

In the target servlet, path accessors like `getRequestURI()` typically reflect the **forward target**, whereas `FORWARD_REQUEST_URI` holds the original URI of the first forward dispatch. When forwarding before commit, the container clears any buffered response body so the target can produce the response; if the response has already committed, `forward(...)` can throw `IllegalStateException`.

**When used:** transferring from an intermediary controller/servlet to a server-side resource that renders content. Avoid using forward to fake a browser redirect: the URL shown on the client does not automatically change to the forward target URL.

### 2.3. INCLUDE — inserting partial output into the current response

```java
response.getWriter().print("Before|");
request.getRequestDispatcher("/parts/header").include(request, response);
response.getWriter().print("|After");
```

Suppose `/parts/header` writes `Header`; the final body is `Before|Header|After`. The caller resumes after `include(...)`. The included servlet can write to the body, but its attempts to change HTTP status or response headers must not dictate the caller's response.

**Unlike forward:** during an `INCLUDE` pass, many path accessors on the request continue reflecting the **including** resource—the caller; the included resource's path is provided via `jakarta.servlet.include.*` attributes, for example:

```java
Object includedUri =
    request.getAttribute(RequestDispatcher.INCLUDE_REQUEST_URI);
```

Therefore, do not look only at `request.getRequestURI()` and assume the current servlet was called directly by the client. The runnable example below logs the included URI using that dedicated attribute.

### 2.4. ERROR — the container's error-page handling pass

When a servlet calls `response.sendError(500)` or an unhandled exception triggers the error-page mechanism, the container **may** dispatch to a registered error-handling resource. Inside the target servlet:

```java
Object code = request.getAttribute(RequestDispatcher.ERROR_STATUS_CODE);
Object source = request.getAttribute(RequestDispatcher.ERROR_REQUEST_URI);
Object exception = request.getAttribute(RequestDispatcher.ERROR_EXCEPTION);
DispatcherType type = request.getDispatcherType(); // ERROR
```

For example, `code` is `500` and `source` is the failing URL. Other attributes can include `ERROR_MESSAGE`, `ERROR_EXCEPTION_TYPE`, and `ERROR_SERVLET_NAME`. Not every attribute is populated in all cases: `sendError` does not necessarily carry an exception; an exception might be handled by the framework into a normal response before the container ever triggers an error dispatch.

**Distinction:** `response.setStatus(500)` only sets the status and does not itself ask the container to dispatch to an error page. A controller that catches an exception and writes error JSON within the initial pass can also stay in `REQUEST`. Frameworks like Spring Boot typically provide an error endpoint; do not assume every error becomes `ERROR`.

When a filter is mapped for `ERROR`, it can run again for the error dispatch. Depending on the container and error timing, an error dispatch can interleave while an earlier filter chain is still unwinding. Filter code should therefore be re-entry safe; do not treat log ordering as a rigid contract.

### 2.5. ASYNC — resuming processing after releasing the initial request thread

A servlet can request asynchronous processing:

```java
AsyncContext async = request.startAsync();
async.start(() -> {
    // Perform work and then ask the servlet container to dispatch back.
    async.dispatch("/result");
});
```

Requirement: the servlet and all filters participating in that request path must support async (`asyncSupported=true`); otherwise, `startAsync()` can throw `IllegalStateException`. In the snippet above, the initial pass remains `REQUEST`; when the container executes the dispatch to `/result`, that pass is `ASYNC`. After that dispatch, the container completes the response if no new async cycle starts; in another flow, `async.complete()` may be called **without** dispatching.

Do not equate `ASYNC` with merely spawning a thread, calling `CompletableFuture`, or writing to the response from a callback. Only a dispatch triggered by `AsyncContext.dispatch(...)` carries `DispatcherType.ASYNC`. You must handle timeouts, exceptions, and the rule against using request/response after the async lifecycle completes.

In Spring MVC applications, async mechanisms using `Callable`, `DeferredResult`, or compatible APIs can lead to a redispatch. Thread scheduling and filter execution counts depend on filter registration and the specific async mechanism; do not assume a request traverses only one thread.

## 3. On Which Dispatches Is a Filter Invoked?

There are **two separate conditions** for the container to invoke a filter on a dispatch pass:

1. The filter's URL/servlet mapping matches the target resource of that dispatch pass.
2. The current `DispatcherType` is among the dispatcher types registered for the filter.

For example:

```java
@WebFilter(
    urlPatterns = "/*",
    dispatcherTypes = {
        DispatcherType.REQUEST,
        DispatcherType.FORWARD,
        DispatcherType.INCLUDE,
        DispatcherType.ERROR,
        DispatcherType.ASYNC
    },
    asyncSupported = true
)
public class TraceFilter implements Filter {
    @Override
    public void doFilter(ServletRequest rawRequest,
                         ServletResponse rawResponse,
                         FilterChain chain)
            throws IOException, ServletException {
        HttpServletRequest req = (HttpServletRequest) rawRequest;
        System.out.println(req.getDispatcherType());
        chain.doFilter(rawRequest, rawResponse);
    }
}
```

This is an **illustrative snippet of a filter**, meant to run inside a Servlet application with Jakarta Servlet imports and proper `@WebFilter` registration. In Spring Boot, another option is `FilterRegistrationBean` with `setDispatcherTypes(...)`, as shown in the runnable example in Section 5. Declaring `asyncSupported=true` enables async lifecycle support; it does **not** replace `DispatcherType.ASYNC` in the mapping.

If you only need to inspect the initial HTTP request, registering `REQUEST` may suffice. If you need to trace every forward, include, error, and async dispatch, select the corresponding dispatcher types. Broadening the mapping causes filter logic to run more often, so operations with side effects (audit logging, quota deduction, data mutation, billing) must have explicit rules to prevent duplicate execution on the same request.

**Note:** A single filter can commonly be called multiple times across different dispatches; invocation count does not equal the number of HTTP requests from the client. Log the dispatch type, URI, request identifier, and thread when diagnosing.

## 4. Relationship to Spring Security on the Servlet Stack

Spring Security processes HTTP via a filter chain, typically wired into the container through `DelegatingFilterProxy` and `FilterChainProxy`. There are **two distinct configuration layers** here:

- **Filter registration in the Servlet container:** determines which passes (`REQUEST`, `ERROR`, `ASYNC`, `FORWARD`, `INCLUDE`) invoke the proxy. With Spring Boot, this can be adjusted via `spring.security.filter.dispatcher-types` if genuinely needed, after verifying configuration for your version.
- **Authorization rules inside Spring Security:** `authorizeHttpRequests` can inspect the dispatch type using `dispatcherTypeMatchers(...)`, but only once the request **has entered** the Spring Security filter chain.

Example configuration in Java/Spring Security 6:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http.authorizeHttpRequests(auth -> auth
            .dispatcherTypeMatchers(
                    DispatcherType.FORWARD, DispatcherType.ERROR
            ).permitAll()
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated())
        .build();
}
```

The snippet above is only a **sample rule syntax**, not a default policy for every project. Permitting `FORWARD`/`ERROR` often lets an error page or internal view work after the original request passed security; however, you must verify that the initial entry path is protected, data access at the target is safe, and public endpoints cannot forward to sensitive resources. Never permit all `ASYNC` or `INCLUDE` dispatches blindly just to silence a 403 without analyzing the flow and policy.

Several easily overlooked points:

- `OncePerRequestFilter` has a marking mechanism to avoid duplicate execution within a processing pass, but it **must not be assumed** to mean strictly once across the entire HTTP request lifetime. By default, it skips async/error dispatches via `shouldNotFilterAsyncDispatch()` and `shouldNotFilterErrorDispatch()`; subclasses can override these, and nested error dispatches follow their own path.
- `SecurityContextHolder` is thread-bound by default. Spawning an executor/thread during async work does not automatically propagate the security context; use Spring Security's integration mechanisms or `DelegatingSecurityContext...` wrappers suited to your app's design.
- Ensure logging/tracing and security filters use dispatcher mappings fit for purpose, rather than assuming missing `FORWARD` logs mean the server never forwarded.
- With Spring Boot and Spring Security, access policy and **container filter** dispatcher types are two independent places to verify; the order of `requestMatchers` and `dispatcherTypeMatchers` in authorization also affects the outcome.

## 5. Java 17 + Spring Boot 3 Example: Observing All Five Types Yourself

This small example uses **Jakarta Servlet** directly in the Spring Boot Servlet stack alongside a `SecurityFilterChain`. Its purpose is to observe dispatcher types using a trace filter explicitly registered for all five types. No external servlet container is required: Spring Boot uses its embedded container. The `/demo/**` URIs are left public solely for this lab exercise.

Create the structure:

```text
dispatch-demo/
├── pom.xml
└── src/main/java/example/dispatch/DispatchDemoApplication.java
```

**`pom.xml`** (Java 17, Spring Boot 3.3.5):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>dispatch-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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
```

**`src/main/java/example/dispatch/DispatchDemoApplication.java`**:

```java
package example.dispatch;

import jakarta.servlet.AsyncContext;
import jakarta.servlet.DispatcherType;
import jakarta.servlet.Filter;
import jakarta.servlet.RequestDispatcher;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.server.ErrorPage;
import org.springframework.boot.web.server.ErrorPageRegistrar;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import java.io.IOException;
import java.util.EnumSet;

@SpringBootApplication
public class DispatchDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DispatchDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http.authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(
                        DispatcherType.FORWARD, DispatcherType.ERROR)
                    .permitAll()
                .requestMatchers("/demo/**").permitAll()
                .anyRequest().authenticated())
            .build();
    }

    @Bean
    FilterRegistrationBean<Filter> traceFilter() {
        Filter trace = (rawRequest, rawResponse, chain) -> {
            HttpServletRequest req = (HttpServletRequest) rawRequest;
            Object includeUri =
                    req.getAttribute(RequestDispatcher.INCLUDE_REQUEST_URI);
            String target = req.getDispatcherType() == DispatcherType.INCLUDE
                    && includeUri != null
                    ? includeUri.toString()
                    : req.getRequestURI();
            System.out.println("TRACE " + req.getDispatcherType()
                    + " " + target);
            chain.doFilter(rawRequest, rawResponse);
        };

        FilterRegistrationBean<Filter> registration =
                new FilterRegistrationBean<>(trace);
        registration.addUrlPatterns("/*");
        registration.setDispatcherTypes(
                EnumSet.allOf(DispatcherType.class));
        registration.setAsyncSupported(true);
        return registration;
    }

    @Bean
    ServletRegistrationBean<EntryServlet> entryServlet() {
        ServletRegistrationBean<EntryServlet> registration =
                new ServletRegistrationBean<>(new EntryServlet(),
                        "/demo/request", "/demo/forward",
                        "/demo/include", "/demo/error", "/demo/async");
        registration.setAsyncSupported(true);
        return registration;
    }

    @Bean
    ServletRegistrationBean<FragmentServlet> fragmentServlet() {
        return new ServletRegistrationBean<>(
                new FragmentServlet(), "/demo/fragment");
    }

    @Bean
    ServletRegistrationBean<ErrorServlet> errorServlet() {
        return new ServletRegistrationBean<>(
                new ErrorServlet(), "/demo/error-page");
    }

    @Bean
    ServletRegistrationBean<ResultServlet> resultServlet() {
        ServletRegistrationBean<ResultServlet> registration =
                new ServletRegistrationBean<>(
                        new ResultServlet(), "/demo/resumed");
        registration.setAsyncSupported(true);
        return registration;
    }

    @Bean
    ErrorPageRegistrar demoErrorPage() {
        return registry -> registry.addErrorPages(
                new ErrorPage(HttpStatus.INTERNAL_SERVER_ERROR,
                              "/demo/error-page"));
    }

    public static class EntryServlet extends HttpServlet {
        @Override
        protected void doGet(HttpServletRequest request,
                             HttpServletResponse response)
                throws ServletException, IOException {
            response.setCharacterEncoding("UTF-8");
            response.setContentType("text/plain");
            switch (request.getServletPath()) {
                case "/demo/request" ->
                        response.getWriter().print("request");
                case "/demo/forward" ->
                        request.getRequestDispatcher("/demo/fragment")
                               .forward(request, response);
                case "/demo/include" -> {
                    response.getWriter().print("before|");
                    request.getRequestDispatcher("/demo/fragment")
                           .include(request, response);
                    response.getWriter().print("|after");
                }
                case "/demo/error" ->
                        response.sendError(500, "demo error");
                case "/demo/async" -> {
                    AsyncContext async = request.startAsync();
                    async.start(() ->
                            async.dispatch("/demo/resumed"));
                }
                default -> response.sendError(404);
            }
        }
    }

    public static class FragmentServlet extends HttpServlet {
        @Override
        protected void doGet(HttpServletRequest request,
                             HttpServletResponse response)
                throws IOException {
            response.getWriter().print("fragment");
        }
    }

    public static class ErrorServlet extends HttpServlet {
        @Override
        protected void doGet(HttpServletRequest request,
                             HttpServletResponse response)
                throws IOException {
            Object status = request.getAttribute(
                    RequestDispatcher.ERROR_STATUS_CODE);
            response.getWriter().print("error:" + status);
        }
    }

    public static class ResultServlet extends HttpServlet {
        @Override
        protected void doGet(HttpServletRequest request,
                             HttpServletResponse response)
                throws IOException {
            response.getWriter().print("resumed");
        }
    }
}
```

Run inside the `dispatch-demo` directory (with JDK 17+ and Maven installed):

```bash
mvn spring-boot:run
```

In another terminal, call each endpoint:

```bash
curl -i http://localhost:8080/demo/request
curl -i http://localhost:8080/demo/forward
curl -i http://localhost:8080/demo/include
curl -i http://localhost:8080/demo/error
curl -i http://localhost:8080/demo/async
```

**Observed HTTP results** (ignoring default headers which vary by environment):

| URI | HTTP status | Response body |
| --- | --- | --- |
| `/demo/request` | 200 | `request` |
| `/demo/forward` | 200 | `fragment` |
| `/demo/include` | 200 | <code>before&#124;fragment&#124;after</code> |
| `/demo/error` | 500 | `error:500` |
| `/demo/async` | 200 | `resumed` |

With the trace filter above, each standalone command typically produces lines matching the following (exact ordering across threads and other filters depends on the environment):

```text
GET /demo/request:  TRACE REQUEST /demo/request
GET /demo/forward:  TRACE REQUEST /demo/forward
                    TRACE FORWARD /demo/fragment
GET /demo/include:  TRACE REQUEST /demo/include
                    TRACE INCLUDE /demo/fragment
GET /demo/error:    TRACE REQUEST /demo/error
                    TRACE ERROR /demo/error-page
GET /demo/async:    TRACE REQUEST /demo/async
                    TRACE ASYNC /demo/resumed
```

This is the **expected trace of the illustrative filter**, not a guarantee that every other filter or every Spring Security filter runs the same number of times. `INCLUDE` is logged using `INCLUDE_REQUEST_URI`; printing `getRequestURI()` directly during an include pass may still show the caller URI. In real applications, error page setups, other filters, and container behavior can introduce extra activity or different ordering in logs.

**Why does the example have three auxiliary servlets?** `FragmentServlet` is separated from `EntryServlet` so include/forward handling does not rely on `getServletPath()`. During include, path accessors can still reflect the caller; sharing one servlet and switching on `getServletPath()` can easily pick the wrong branch and cause recursive includes. `ErrorServlet` reads `ERROR_STATUS_CODE`, while `ResultServlet` is the dedicated target for the async redispatch.

## 6. Common Mistakes and How to Check

1. **Confusing `forward` with redirect.** The client's URL stays unchanged after forward; if you want the client to navigate to a different URL, use redirect and account for it as a new HTTP request.
2. **Assuming `getRequestURI()` is always the currently executing resource.** For `INCLUDE`, read `RequestDispatcher.INCLUDE_REQUEST_URI`; for `FORWARD`, also inspect `FORWARD_REQUEST_URI` to identify the original URI.
3. **Assuming every HTTP 500 is an `ERROR` dispatch.** Check whether a container error dispatch occurred or the framework wrote the error response directly during `REQUEST`.
4. **Assuming filters automatically re-run on forward/error/async.** Read the filter's dispatcher mapping and inspect logs on each pass; by default, Servlet filters map only `REQUEST` unless specified otherwise.
5. **Confusing `startAsync()` with an `ASYNC` dispatch.** Only when `AsyncContext.dispatch(...)` redispatches does an `ASYNC` pass occur; async support is required on the involved servlets/filters.
6. **Using `ThreadLocal`-based security data on a new async thread.** Verify whether security/tracing context is actually propagated through a supported mechanism.
7. **Running side effects multiple times because a filter is invoked on multiple dispatches.** Separate authentication, tracing, and actions meant to happen once per business operation; idempotency must be designed explicitly.
8. **Reflexively granting `permitAll()` to all internal dispatches.** Verify whether the originating request is protected and what access the target endpoint grants; check container filter registration before assuming an authorization rule takes effect.

When debugging, log at least `getDispatcherType()`, request URI, relevant `forward/include/error` attributes, request ID, thread, status/exception, and the observed filter's dispatcher mapping. Correlate dispatches belonging to the **same client request** to see whether and why a filter ran again.

## 7. Knowledge Self-Check

- Client calls `/a`, `/a` forwards to `/b`: what is the dispatch pass at `/b`? **`FORWARD`**; the client does not issue a new request.
- `/a` includes `/fragment` and keeps writing to the body: can the `/fragment` servlet change the outer response's HTTP status? **No**, its output is inserted and the caller continues.
- A controller returns JSON with status 500 directly in the initial pass: is `getDispatcherType()` guaranteed to be `ERROR`? **No**; it normally remains `REQUEST` if no error dispatch occurs.
- `startAsync()` runs a task on an executor: does an `ASYNC` dispatch happen automatically? **No**; `AsyncContext.dispatch(...)` is needed to trigger an ASYNC dispatch pass.
- Does a filter mapped only for `REQUEST` observe every forward and error pass? **No**; corresponding dispatcher mappings are required.
- Does `dispatcherTypeMatchers(ERROR).permitAll()` guarantee Spring Security filters run on every `ERROR` dispatch? **No**; it also depends on the security filter registration in the Servlet container.

**Key takeaway:** `DispatcherType` describes the **current dispatch pass**; `Filter` execution depends on **both URL mapping and dispatcher type**; Spring Security must be examined at **both container registration and filter-chain authorization**.