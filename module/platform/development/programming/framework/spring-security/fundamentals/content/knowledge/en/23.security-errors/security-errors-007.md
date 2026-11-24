# Errors Occurring in Filters Do Not Automatically Pass Through @ControllerAdvice

> **Scope:** **Spring MVC applications on the Servlet stack**, Spring Boot 3.x / Spring Security 6.x, and Java 17+. Parent topic: **Security Errors**. The focus is why exceptions thrown inside a `Filter` or `OncePerRequestFilter` are not automatically caught by `@ControllerAdvice`, how to choose an appropriate handling mechanism, and how this differs from Spring Security authentication/authorization errors.

## 1. Common Problem

You have a `@RestControllerAdvice` with `@ExceptionHandler` to standardize error JSON. When a controller throws `IllegalArgumentException` or a business exception, the API returns the expected structure. However, when a **Servlet Filter** throws the same exception, the `@ExceptionHandler` is never invoked; the application may return Spring Boot's `/error` page/JSON, HTTP 500, or another response handled by the container/gateway.

This does not mean `@ControllerAdvice` is "not global". Here "global" applies to **Spring MVC's exception-handling mechanism**, rather than creating a `try/catch` wrapping the entire Servlet Filter Chain.

Three questions to determine whenever you see an error:

1. **Where did the error occur?** Container, servlet filter, security filter, handler/controller, or async task?
2. **Which handler wraps that point of origin?** MVC's `HandlerExceptionResolver`, Security's `ExceptionTranslationFilter`, an authentication failure handler, a request-rejection handler, or the container's error page?
3. **Has the response already been written/committed?** Once headers/body are committed, you cannot arbitrarily change the HTTP status code or append a new error body.

### Lesson Goals

- Read the `FilterChain.doFilter(...)` flow and the `DispatcherServlet` boundary.
- Explain why `@ExceptionHandler` does not automatically catch exceptions thrown **before** MVC starts processing.
- Distinguish application errors in filters from `AuthenticationException`, `AccessDeniedException`, and `RequestRejectedException`.
- Choose one of three sound handling approaches: **respond directly in the filter**, **delegate a controlled application error to `HandlerExceptionResolver`**, or **use Spring Security's dedicated handlers**.
- Write tests proving whether a request goes through advice while avoiding leaking sensitive information.

## 2. Execution Boundary: Filters Run Before MVC

A typical flow in a **Servlet application**:

```text
HTTP client
   |
   v
Servlet container (parse request)
   |
   +--> Servlet Filter A
   |      |
   |      +--> DelegatingFilterProxy
   |               |
   |               +--> Spring Security FilterChainProxy
   |                         |
   |                         +--> authentication/CSRF/authorization filters
   |                         +--> ExceptionTranslationFilter (only certain Security errors)
   |               |
   +--> Servlet Filter B (if any, by registration order)
   |      |
   |      +--> DispatcherServlet
   |               |
   |               +--> HandlerMapping / HandlerAdapter
   |               +--> Controller / Service
   |               |
   |               +--> HandlerExceptionResolver
   |                         |
   |                         +--> @ExceptionHandler in controller
   |                         +--> @ControllerAdvice / @RestControllerAdvice
   |
   +--> Servlet container error processing / /error (for remaining unhandled errors)
```

*This figure is a conceptual diagram*: the actual positions of Filter A/B and security filters depend on configuration; the ordering of `ExceptionTranslationFilter` relative to other filters also matters. `HandlerExceptionResolver` is not an outermost filter; it is invoked by `DispatcherServlet` during MVC processing when an exception falls within that servlet's responsibility.

### Why Doesn't `@ControllerAdvice` Catch the Error Automatically?

- `@ControllerAdvice` contains `@ExceptionHandler` methods discovered and invoked by `ExceptionHandlerExceptionResolver` as part of the `HandlerExceptionResolver` system.
- `DispatcherServlet` invokes these resolvers for exceptions occurring while it maps, invokes, or processes a handler.
- A custom filter can throw an exception **before calling** `chain.doFilter(...)`. At that point the request has not entered `DispatcherServlet`, so MVC has no opportunity to invoke resolvers automatically.
- Even if a filter throws an exception **after** `chain.doFilter(...)` returns, that moment is also outside `DispatcherServlet`'s internal exception-handling scope.
- If a filter invokes `HandlerExceptionResolver` itself, that is an **explicit forwarding written by the developer**, not default annotation behavior.

Compare an illustrative snippet:

```java
@Override
protected void doFilterInternal(HttpServletRequest request,
                                HttpServletResponse response,
                                FilterChain chain)
        throws ServletException, IOException {

    if (isInvalid(request)) {
        throw new InvalidRequestException("Invalid request"); // Thrown inside Filter
    }

    chain.doFilter(request, response); // MVC is only invoked if the request reaches the servlet
}
```

The `isInvalid` function and exception above are *illustrative pseudocode*, not a standalone program. Placing `@ExceptionHandler(InvalidRequestException.class)` in advice does not make the first exception automatically pass through MVC.

### Distinguishing from MVC Interceptors

A `HandlerInterceptor` is invoked by `DispatcherServlet` inside the handler execution chain. Therefore, exceptions from `preHandle`/handlers usually have the opportunity to go through MVC's `HandlerExceptionResolver`, depending on timing and response state. A **Servlet Filter** operates outside `DispatcherServlet`, with a different error-handling scope.

## 3. Matrix: Where Is Each Exception Type Handled?

| Error Source | Appropriate Handler | Automatically Passes Through `@ControllerAdvice`? |
| --- | --- | --- |
| Controller or service called by controller throws an exception during an MVC request | `HandlerExceptionResolver`, `@ExceptionHandler` | **Usually yes**, when the advice applies and a resolver can handle it. |
| `@RequestBody` validation in MVC | MVC exception resolver / `ResponseEntityExceptionHandler` | Possible, if the handler is configured accordingly. |
| Servlet `Filter`/`OncePerRequestFilter` throws a runtime exception directly | Local handler in the filter, or explicit call to MVC resolver; if left unhandled, container/error processing | **Not automatically.** |
| `AuthenticationException` from a relevant Security branch | `AuthenticationEntryPoint` or authentication failure handler mechanism | **Does not need to go through advice.** |
| `AccessDeniedException` occurring *after* `ExceptionTranslationFilter` in the chain segment it wraps | `AccessDeniedHandler` or `AuthenticationEntryPoint` depending on authentication state | **Not by default.** |
| `RequestRejectedException` from `HttpFirewall` rejecting a request | `RequestRejectedHandler` / `FilterChainProxy` | **Not automatically.** |
| Request rejected by Tomcat/proxy before the application | Container / reverse proxy | No. |
| Remaining exception dispatched by container to `/error` | Container / Spring Boot error handling (usually `BasicErrorController`) | No guarantee the original endpoint's advice is invoked. |
| Exception from `@Async`, background thread, standalone job | Async/job handler, logger, result/future | No; no longer synchronous MVC request processing. |

**Subtle point:** `ExceptionTranslationFilter` does not "catch every Security error". It mainly translates `AuthenticationException` and `AccessDeniedException` thrown from the **downstream chain segment** it wraps into HTTP responses. A custom filter throwing an error **before** reaching `ExceptionTranslationFilter` may fall outside its `try/catch` scope. Exceptions like `IllegalArgumentException` or `NullPointerException` also do not become 401/403 errors merely because they occurred inside the security chain.

An `AccessDeniedException` thrown deep from method security during a controller call can be handled **first** by an MVC resolver if advice catches that error type; only when the error propagates up to `ExceptionTranslationFilter` does that filter get to handle it. Therefore, avoid overly broad handlers that accidentally turn access-control errors into HTTP 500 or 200.

## 4. Demo Reproducing the Difference: Controller 400 vs. Filter Bypassing Advice

The example uses **a Spring Boot MVC application**, with dependencies `spring-boot-starter-web` and `spring-boot-starter-security`; tests also use `spring-boot-starter-test`. The classes below live in package `com.example.filtererrors`, with each code block as **a separate Java file**. The program runs inside a Spring Boot application with Java 17+, rather than running each class standalone with `java`.

### 4.1. Main Class — `FilterErrorDemoApplication.java`

```java
package com.example.filtererrors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterErrorDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterErrorDemoApplication.class, args);
    }
}
```

### 4.2. Shared Exception — `DemoInputException.java`

```java
package com.example.filtererrors;

public final class DemoInputException extends RuntimeException {
    public DemoInputException(String message) {
        super(message);
    }
}
```

### 4.3. Controller — `DemoController.java`

```java
package com.example.filtererrors;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/demo")
public class DemoController {

    @GetMapping("/ok")
    public String ok() {
        return "ok";
    }

    @GetMapping("/controller-failure")
    public String controllerFailure() {
        throw new DemoInputException("Invalid controller input");
    }
}
```

### 4.4. Global Advice — `ApiAdvice.java`

```java
package com.example.filtererrors;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiAdvice {

    @ExceptionHandler(DemoInputException.class)
    public ResponseEntity<Map<String, String>> handleDemoInput(DemoInputException ex) {
        return ResponseEntity.badRequest().body(Map.of(
            "code", "INVALID_INPUT",
            "message", ex.getMessage()
        ));
    }
}
```

`@RestControllerAdvice` combines `@ControllerAdvice` with `@ResponseBody` to write results to the HTTP response. Because errors from the controller are passed to MVC resolvers, this handler will return **400 Bad Request** with a JSON body. JSON formatting and key order may vary; the two fields `code` and `message` are the contract to verify.

### 4.5. Filter Throwing the Error — `DemoFailureFilter.java`

```java
package com.example.filtererrors;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public final class DemoFailureFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain)
            throws ServletException, IOException {

        if ("true".equalsIgnoreCase(request.getHeader("X-Demo-Filter-Failure"))) {
            throw new DemoInputException("Invalid filter input");
        }

        chain.doFilter(request, response);
    }
}
```

This filter intentionally throws **the same exception type** as the controller when the client sends the `X-Demo-Filter-Failure: true` header.

### 4.6. Registering the Filter and Security — `WebConfig.java`

```java
package com.example.filtererrors;

import jakarta.servlet.DispatcherType;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers("/api/demo/**").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    FilterRegistrationBean<DemoFailureFilter> demoFailureFilter() {
        FilterRegistrationBean<DemoFailureFilter> registration =
            new FilterRegistrationBean<>(new DemoFailureFilter());

        registration.addUrlPatterns("/api/demo/*");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 50);
        return registration;
    }
}
```

This is a **demo** configuration: `/api/demo/**` is `permitAll` to inspect errors without a login screen getting in the way; other requests still require authentication. `ERROR` dispatches are permitted so Boot's error view/controller has a chance to render the result. In real applications, design dispatch permissions per your specific architecture rather than simply copying demo rules.

**Avoid registering the filter twice:** `DemoFailureFilter` does not carry `@Component` or a separate `@Bean`. The `FilterRegistrationBean` above is the single servlet filter registration path. If you simultaneously create an auto-registered Filter bean and add it via `http.addFilterBefore(...)`, the filter can run in both the Servlet chain and the Security chain, making error traces confusing.

### 4.7. Testing with curl

Run from a Spring Boot project with Gradle wrapper:

```bash
./gradlew bootRun

# Normal route
curl -i http://localhost:8080/api/demo/ok

# Exception from controller: caught by advice
curl -i http://localhost:8080/api/demo/controller-failure

# Exception from filter: not automatically caught by advice
curl -i -H 'X-Demo-Filter-Failure: true' \
  http://localhost:8080/api/demo/ok
```

Expected results **by processing flow**:

| Request | Result |
| --- | --- |
| `GET /api/demo/ok` | 200, body `ok`. |
| `GET /api/demo/controller-failure` | 400, JSON containing `"code":"INVALID_INPUT"` from `ApiAdvice`. |
| `GET /api/demo/ok` with header triggering filter failure | **Does not run `ApiAdvice`**; without another handler, usually 500 from container/`/error`. Exact body and code depend on error dispatch configuration. |

The demo filter error is an **application-thrown error**, not an authentication error. If logs show both requests returning the same JSON, check whether an external handler outside MVC has been configured; do not conclude `@ControllerAdvice` automatically covers all filters.

## 5. Approach A — Filter Returns the Error Directly (Usually Simplest)

If a filter is responsible for checking a clear condition, such as a required header, and can decide the response immediately, **write status + body once, then `return`**, without throwing an exception hoping MVC will catch it.

Here is a **replacement version** of `DemoFailureFilter.java` in the demo, using the Jackson `ObjectMapper` preconfigured by Spring Boot:

```java
package com.example.filtererrors;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.MediaType;
import org.springframework.web.filter.OncePerRequestFilter;

public final class DemoFailureFilter extends OncePerRequestFilter {

    private final ObjectMapper objectMapper;

    public DemoFailureFilter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain)
            throws ServletException, IOException {

        if ("true".equalsIgnoreCase(request.getHeader("X-Demo-Filter-Failure"))) {
            response.setStatus(HttpServletResponse.SC_BAD_REQUEST);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());

            objectMapper.writeValue(response.getOutputStream(), Map.of(
                "code", "INVALID_INPUT",
                "message", "Invalid filter input"
            ));
            return;
        }

        chain.doFilter(request, response);
    }
}
```

At the same time, **replace only the filter registration bean** in `WebConfig` with the following method, keeping the `SecurityFilterChain` bean unchanged:

```java
@Bean
FilterRegistrationBean<DemoFailureFilter> demoFailureFilter(ObjectMapper objectMapper) {
    FilterRegistrationBean<DemoFailureFilter> registration =
        new FilterRegistrationBean<>(new DemoFailureFilter(objectMapper));
    registration.addUrlPatterns("/api/demo/*");
    registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 50);
    return registration;
}
```

The second method goes inside `WebConfig` and needs `import com.fasterxml.jackson.databind.ObjectMapper;`. This is a **replacement pattern**; do not declare two beans with the same name in parallel.

After this fix, requests triggering the filter error will return **400** with the two contractually consistent JSON fields. At this point `ApiAdvice` is **still not called**: the filter handles it directly at the source.

**Important notes:**

- `response.setStatus(...)` differs from `response.sendError(...)`: `sendError` can trigger the container's error page/`ERROR` dispatch mechanism; that is not a direct call to advice. Choose based on the desired response behavior.
- Only write the body if the response has not been committed; do not attempt to keep writing after the output stream has been closed or data has already been flushed to the client.
- After handling the error, you must `return`; continuing to call `chain.doFilter(...)` can cause the controller to write a second time.
- Avoid building JSON strings by concatenating unescaped data; use a serializer. Never return `ex.getMessage()` verbatim to the client if it could contain internal details.
- Do not turn every unexpected exception into 400; programming bugs, DB connection errors, or I/O failures are usually not "bad requests".

## 6. Approach B — Explicitly Delegating to HandlerExceptionResolver

When you need to **reuse the exact same MVC error format** for an *application* exception thrown in a filter, you can call `HandlerExceptionResolver` explicitly. This is useful when a matching `@RestControllerAdvice` already exists, though you must understand the resolver's limitations.

Replace **`DemoFailureFilter.java`** with the version below (do not apply simultaneously with Approach A):

```java
package com.example.filtererrors;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerExceptionResolver;
import org.springframework.web.servlet.ModelAndView;

public final class DemoFailureFilter extends OncePerRequestFilter {

    private final HandlerExceptionResolver resolver;

    public DemoFailureFilter(HandlerExceptionResolver resolver) {
        this.resolver = resolver;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain)
            throws ServletException, IOException {

        if ("true".equalsIgnoreCase(request.getHeader("X-Demo-Filter-Failure"))) {
            DemoInputException exception =
                new DemoInputException("Invalid filter input");

            ModelAndView handled =
                resolver.resolveException(request, response, null, exception);

            if (handled == null) {
                throw exception; // Resolver could not handle it: let the error propagate
            }
            return;
        }

        chain.doFilter(request, response);
    }
}
```

And replace the registration bean in `WebConfig`:

```java
@Bean
FilterRegistrationBean<DemoFailureFilter> demoFailureFilter(
        @Qualifier("handlerExceptionResolver") HandlerExceptionResolver resolver) {

    FilterRegistrationBean<DemoFailureFilter> registration =
        new FilterRegistrationBean<>(new DemoFailureFilter(resolver));
    registration.addUrlPatterns("/api/demo/*");
    registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 50);
    return registration;
}
```

In `WebConfig`, add imports for `org.springframework.beans.factory.annotation.Qualifier` and `org.springframework.web.servlet.HandlerExceptionResolver`.

**Mechanism:**

1. The filter detects the error condition it owns.
2. The filter creates `DemoInputException`.
3. Calling `resolver.resolveException(request, response, null, exception)` **explicitly** triggers the resolver mechanism.
4. If `@RestControllerAdvice` has a matching global `@ExceptionHandler(DemoInputException.class)`, the resolver can write the 400 JSON response, return a `ModelAndView` indicating it was handled, and the filter stops.
5. If the resolver returns `null`, meaning **unhandled**, the example rethrows the exception so the request does not silently fail with 200.

### Limitations of Approach B

- The `handler = null` argument is passed because the filter does not yet have an MVC-selected `HandlerMethod`. Controller-specific `@ExceptionHandler` methods lack context to run; `@ControllerAdvice` scoped by package, annotation, or class may also not apply when no controller is identified.
- A resolver may return a `ModelAndView` requiring **view rendering**; invoking it directly from a filter does not guarantee the entire HTML rendering lifecycle runs as inside `DispatcherServlet`. The pattern above is better suited for `@RestControllerAdvice` returning `ResponseEntity`/JSON.
- Handlers may rely on request attributes only initialized within MVC; test in practice. Do not assume every MVC handler behaves identically when called before MVC.
- Do not wrap the entire `chain.doFilter(...)` in `catch (Exception ex) { resolver.resolveException(...) }`: doing so can mistakenly intercept authentication errors, authorization errors, I/O errors, or programming bugs from downstream layers.
- Do not route `AccessDeniedException`, `AuthenticationException`, or arbitrary runtime exceptions to the resolver just for uniform JSON. 401/403 behavior, challenge headers, and security mechanisms can break.

## 7. Approach C — Using Spring Security's Error Mechanisms

`@ControllerAdvice` is not the primary place to standardize **authentication and authorization** errors arising in the Spring Security filter chain. Each error category has its own mechanism:

### 7.1. AuthenticationEntryPoint: Unauthenticated or Invalid Authentication

`AuthenticationEntryPoint` is used when the system needs to initiate an authentication flow. Depending on the application, the response may be:

- **401 Unauthorized** with an appropriate `WWW-Authenticate`, e.g. HTTP Basic or Bearer token.
- **302 Redirect** to a login page for web apps using form login.
- Another mechanism if a specialized scheme is configured.

Some authentication filters, such as the form login filter, have their own **`AuthenticationFailureHandler`** to handle authentication failures at that filter. Do not assume every `AuthenticationException` always passes through `ExceptionTranslationFilter`.

### 7.2. AccessDeniedHandler: Authenticated but Insufficient Permissions

`AccessDeniedHandler` handles `AccessDeniedException` when `ExceptionTranslationFilter` determines the request belongs to the access-denied case, usually **403 Forbidden**. For anonymous/unauthenticated principals, the filter can use `AuthenticationEntryPoint` instead of `AccessDeniedHandler`.

When customizing `http.exceptionHandling(...)`, verify the contract of each login mechanism: HTTP Basic/Bearer typically require accurate challenge headers; replacing the entry point with a bare `response.setStatus(401)` can leave clients unable to tell how to authenticate.

### 7.3. HttpFirewall and RequestRejectedHandler

Errors rejected due to malformed URIs/methods/headers can arise right at `StrictHttpFirewall` as `RequestRejectedException`. `FilterChainProxy` provides the `RequestRejectedHandler` mechanism to handle them. It is **different** from `AccessDeniedException` (which already reached permission checking) and usually occurs before selecting or running MVC filters/controllers. Do not attribute every request rejection error to advice.

### 7.4. Appropriate Configuration Example

With Basic Authentication, keep the default entry point of `httpBasic(...)` (to preserve the challenge header), and customize only the access-denied response when the application genuinely needs it:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .exceptionHandling(ex -> ex
            .accessDeniedHandler((request, response, denied) -> {
                response.sendError(HttpServletResponse.SC_FORBIDDEN);
            })
        );

    return http.build();
}
```

The snippet above is **an alternative option for the `SecurityFilterChain` bean** of the demo, not an additional chain overlapping all requests. Import `jakarta.servlet.http.HttpServletResponse` if used. `sendError(403)` can lead to `/error`; this is only a status example and does not intentionally produce standardized JSON. For JWT/OAuth2 Resource Server APIs, keep or customize the resource server's entry point and denied handler for Bearer-compliant responses rather than copying this example's Basic setup.

**Ordering issue:** `ExceptionTranslationFilter` only handles exceptions from the chain segment wrapped by its `chain.doFilter` call. Placing a custom filter ahead of it (or registering it in the Servlet container outside the security chain) and throwing `AccessDeniedException` **does not guarantee** this filter will translate the error. Do not arbitrarily reorder security filters just to "fix a 500 error"; identify responsibilities and placement first.

## 8. Spring Boot /error Is Not Equivalent to @ControllerAdvice

In Servlet applications, Spring Boot typically configures the `/error` path, using `BasicErrorController` and error attributes to build responses for errors left unhandled at their origin. That is a *fallback mechanism* triggered by the container when a request ends with an error or `sendError`, distinct from `ExceptionHandlerExceptionResolver` directly handling the original controller's exceptions.

Common points of confusion:

- When an exception escapes a filter unhandled, the **container** may send an `ERROR` dispatch to `/error`. The client then receives Boot's error JSON/HTML even though `@ExceptionHandler` for the source exception never ran.
- `@ResponseStatus` or `ResponseStatusException` used in MVC are not guaranteed to be automatically interpreted by MVC resolvers when thrown from any Servlet Filter.
- `OncePerRequestFilter` has specific rules for dispatcher types. By default `shouldNotFilterErrorDispatch()` returns `true`, yet whether a filter participates in `ERROR` dispatches also depends on registration style and the servlet container. Do not assert that every filter is invoked once across all dispatches.
- If security blocks the `ERROR` dispatch or the `/error` path itself, the original error can be masked by a new 401/403. Spring Security provides `dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()` when policy permits showing error pages; place the rule before `anyRequest()`.
- If the response is already committed, the error dispatch mechanism cannot safely rewrite headers/body.

**Correct diagnosis:** if `@ExceptionHandler` logs nothing, yet `/error` returns JSON, first identify which filter/container threw the error and whether the initial request passed through `DispatcherServlet`. Do not create an overly broad `@ExceptionHandler(Exception.class)` to "cure" every 500; it does not extend scope outside MVC.

## 9. Checklist for Standard, Consistent, and Safe Error Handling

### 9.1. When Designing

| Scenario | Preferred Approach | Notes |
| --- | --- | --- |
| Controller/service throws a business exception | `@RestControllerAdvice` + specific `@ExceptionHandler` | Preserve proper status and avoid leaking internal details. |
| Filter checks header/metadata/request itself and knows the error clearly | Return status/body directly, `return` | Can use a shared serializer helper. |
| Filter has an application exception needing to reuse MVC's JSON policy | Delegate to `HandlerExceptionResolver` for defined exception types | Test the `handler=null` case and when the resolver does not handle it. |
| HTTP authentication/authorization | `AuthenticationEntryPoint`, `AuthenticationFailureHandler`, `AccessDeniedHandler` | Respect scheme, headers, and authentication state. |
| HttpFirewall rejects a request | `RequestRejectedHandler` | Do not turn malformed requests into "permission denied". |
| Background errors, non-request errors | Task/executor/job exception handler | Separate from the Servlet request lifecycle. |
| Unhandled errors | `/error`, error attributes / logs / monitoring | Do not rely on this for all business API contracts. |

If multiple layers must return the same JSON structure, create **one error model and one response-writing utility** usable by advice, entry points, and filter handlers alike. Avoid "funneling" all errors into advice by altering the Security flow recklessly.

### 9.2. When Handling Directly Inside a Filter

1. Catch and handle only errors the filter **owns**. Keep fail-fast logic predictable.
2. Check `response.isCommitted()` if the processing path may have already written data; never try to change status/body after commit.
3. Choose meaningful statuses: 400 for malformed syntax/input, 401 for missing scheme-appropriate authentication, 403 for insufficient permissions; 500 for unexpected errors. These are **guidelines**; actual behavior depends on the API's HTTP policy.
4. Return structured, stable content; never return stack traces, tokens, cookies, SQL errors, or system info.
5. Stop the filter chain after writing the error. If unable to handle an exception, do not swallow it and let the request return a false 200.
6. Do not catch all `RuntimeException` from `chain.doFilter(...)` just to return one JSON format; doing so easily hides downstream security errors.
7. Consider `REQUEST`, `ASYNC`, and `ERROR` dispatcher types when registering filters; avoid unexpected repeated filter runs.
8. Check both before and after the filter: a proxy/container may return errors before Spring Boot gets to process them.

### 9.3. When Seeing Confusing 401/403/500 Errors

- Enable selective logging for `org.springframework.security` and your filters in a test environment; inspect the exception class, stack trace, and first class throwing the error.
- Determine whether the filter belongs to the **Servlet filter chain** or **Spring Security FilterChainProxy**, how it is registered/ordered, and whether it is registered twice.
- Check which advice has a matching `@ExceptionHandler`; verify whether it is restricted by `basePackages`, `annotations`, or `assignableTypes`.
- Distinguish security errors returned by entry points, denied handlers, authentication failure handlers, and request rejection handlers from errors rendered by the container/`/error`.
- Inspect subsequent dispatches, response commits, and whether any filter/logger writes the body twice.
- Log correlation IDs and error types at appropriate levels; scrub sensitive data from logs.

## 10. Testing: Using Both MVC Tests and Real HTTP

**Testing note:** `MockMvc` helps verify controllers, advice, and many registered filters, but does not fully replace a servlet container. If a filter throws an unhandled exception, `MockMvc` may **propagate the exception up to the test** rather than simulating the exact `/error` page or 500 status that real Tomcat returns. Therefore, separate tests into three levels:

1. **MVC layer:** call the controller endpoint and assert `400` + body from `ApiAdvice`.
2. **Filter layer:** send a request through the filter and assert it returns the error / delegates to the resolver properly, or propagates the exception when unhandled.
3. **Live HTTP integration:** run Spring Boot with an embedded server, call `curl` or a real HTTP client to observe error dispatches, security headers, status, and content type.

The test example below applies **only after implementing Approach A or B**, when the filter error already has a handler returning HTTP 400:

```java
package com.example.filtererrors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FilterErrorIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void controllerExceptionIsResolvedByAdvice() throws Exception {
        mvc.perform(get("/api/demo/controller-failure"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_INPUT"));
    }

    @Test
    void filterExceptionReturnsConfiguredJson() throws Exception {
        mvc.perform(get("/api/demo/ok")
                .header("X-Demo-Filter-Failure", "true"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_INPUT"));
    }
}
```

Prerequisites: the project has `spring-boot-starter-test` and the demo application is in the same package or a parent package of the test. The second test **should not be run expecting 400 on the initial version**, because the initial filter intentionally throws an unhandled error. With Approach A, the test proves the filter returns JSON itself; with Approach B, it proves the resolver is invoked explicitly. This test **does not prove `ApiAdvice` was called in Approach A** — to verify where handling happens, use instrumentation/spies or deliberate logging.

### Scenario Matrix to Verify

| Scenario | What to Verify |
| --- | --- |
| Valid request, filter continues chain | Normal endpoint runs; no double invocation. |
| Request rejected by filter | Correct status/body; controller does not run; after writing the error, chain does not continue. |
| Exception from controller | Resolver/advice handles properly; not "swallowed" by a filter. |
| Missing authentication | Correct entry point, appropriate challenge header/redirect. |
| Authenticated but missing permissions | Correct denied handler; does not return 200 or expose resource. |
| Malformed URL rejected by firewall | Does not reach controller; proper handler and log; status depends on stack. |
| Unexpected error in filter | Not disguised as an input error; proper logging, monitoring, and 5xx response. |
| Error during `ERROR` dispatch / already committed response | No infinite loop, response is not written twice. |

## 11. Common Misconceptions

**"Adding `@ExceptionHandler(Exception.class)` catches all errors."** False. That handler still belongs to MVC. Moreover, it can mistakenly catch security exceptions passing through MVC, producing wrong statuses and hiding errors.

**"A filter throwing `ResponseStatusException(HttpStatus.BAD_REQUEST)` is guaranteed to return 400."** There is no such guarantee if the exception does not reach `ResponseStatusExceptionResolver`. The handling path depends on filters, the container, and error pages.

**"Annotating a filter with `@Component` is enough for Spring MVC to manage the filter's errors."** False. `@Component` only participates in bean creation/registration; it does not expand `DispatcherServlet`'s scope. In Spring Boot, a `Filter` bean may also be auto-registered in the servlet container.

**"`ExceptionTranslationFilter` handles every `RuntimeException` in Security."** False. It handles appropriate authentication and access-denied error types from the wrapped chain segment; arbitrary application errors need their own handlers.

**"After `response.sendError(...)`, `@ControllerAdvice` will run."** No. `sendError` typically invokes the servlet container's error handling, which can route to `/error`; that is a separate dispatch.

**"Just catch every error in the filter and call `resolver.resolveException`."** Dangerous: it interferes with unauthenticated, access-denied, I/O, and downstream application errors, especially when the response is already committed. Delegate only clearly identified errors and test the outcome.

**"If controller advice doesn't run, Spring Boot doesn't handle errors."** Incorrect. The container and `/error` can produce a fallback response, but it should not be confused with MVC's business error contract.

## 12. Self-Check Questions

1. An exception is thrown **before** `chain.doFilter` in a Servlet Filter. Why doesn't `@ControllerAdvice` catch it automatically?
2. What happens if `HandlerExceptionResolver.resolveException(...)` returns `null`?
3. When an application uses HTTP Basic, why shouldn't you arbitrarily replace `AuthenticationEntryPoint` with code that only returns status 401?
4. Why might an `AccessDeniedException` thrown inside a custom filter fail to be caught by `ExceptionTranslationFilter`?
5. What is the difference between an error response generated by `ApiAdvice` and a response from Spring Boot's `/error`?
6. How do you demonstrate that a `MockMvc` test does not fully reflect behavior on embedded Tomcat?
7. Why shouldn't you catch `Exception` around the entire `chain.doFilter(...)` and always return 400?

**Hints:** (1) hasn't entered MVC's processing area yet; (2) the error remains unresolved, so a fallback/rethrow path is needed; (3) `WWW-Authenticate` may be lost; (4) filter ordering and `ExceptionTranslationFilter`'s `chain.doFilter` scope; (5) resolver handling the source exception vs. fallback error dispatch; (6) compare with live HTTP on a real container; (7) hides Security and server errors, leading to wrong statuses or writing the response twice.

## Official Documentation

- Spring Framework — Handling exceptions with `HandlerExceptionResolver`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/exceptionhandlers.html
- Spring Framework — `@ControllerAdvice` / `@RestControllerAdvice`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html
- Spring Framework — Servlet request processing: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/sequence.html
- Spring Framework — `OncePerRequestFilter` API: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- Spring Security — Servlet architecture and exception translation: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — RequestRejectedHandler: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/firewall/RequestRejectedHandler.html
- Spring Security — HTTP authorization and ERROR dispatcher: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Boot 3.3 — Servlet web error handling: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
