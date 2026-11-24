# Why `@ControllerAdvice` Does Not Automatically Handle Every Exception Thrown in a `Filter`

## 1. Core Answer

In a **Spring MVC application running on Servlet**, `@ControllerAdvice` (or `@RestControllerAdvice`) participates in **Spring MVC**'s exception-handling mechanism, primarily through `HandlerExceptionResolver` beans invoked by `DispatcherServlet` during request processing. By contrast, a Servlet `Filter` sits **outside `DispatcherServlet`'s invocation flow**. If a filter throws an exception before handing the request off to MVC, nothing automatically routes that exception into an advice's `@ExceptionHandler`.

This does not mean `@ControllerAdvice` catches only exceptions thrown directly inside a controller method: MVC can also pass resolvers exceptions from certain other stages of MVC processing. The key boundary is that **the exception must pass through MVC's resolver mechanism**. The term "global exception handler" often used for `@ControllerAdvice` means global across MVC controllers—not a global error catcher for the entire Servlet container and every filter.

`@RestControllerAdvice` is equivalent to `@ControllerAdvice` combined with `@ResponseBody` behavior; it is convenient for JSON APIs, yet **does not widen the exception-catching boundary**.

## 2. Which Layers Does a Request Pass Through?

A typical Servlet request flow:

```text
Client
  |
  v
Servlet container (Tomcat/Jetty/...)
  |
  +--> Servlet Filter A (possibly registered by the application)
  |
  +--> DelegatingFilterProxy("springSecurityFilterChain")
  |      |
  |      +--> FilterChainProxy: Spring Security filters
  |             ... -> ExceptionTranslationFilter -> AuthorizationFilter -> ...
  |
  +--> Servlet Filter B (if registered at this position)
  |
  v
DispatcherServlet (Spring MVC)
  |
  +--> HandlerMapping / HandlerAdapter
  |
  +--> Controller and MVC interceptors
  |
  +--> When MVC needs to handle an exception:
         HandlerExceptionResolverComposite
           -> ExceptionHandlerExceptionResolver
                -> @ExceptionHandler in controller / @ControllerAdvice
           -> other resolvers depending on configuration
```

The diagram illustrates **responsibility boundaries**, not a guarantee that every app has this exact Filter A/B ordering. Actual order depends on `FilterRegistrationBean` configuration, the container, `SecurityFilterChain`, and how filters are registered. `DelegatingFilterProxy` is a Servlet filter bridging to the security filter chain; it does not turn every Servlet filter into part of MVC.

### Two Different Error Flows

1. **Controller throws an exception:** the request has already entered `DispatcherServlet`; if MVC finds a matching resolver, an `@ExceptionHandler` method can produce the response. Once resolved, the exception normally does not continue bubbling out to the filter chain.
2. **Filter throws an exception before `chain.doFilter(...)`:** the request has not even reached `DispatcherServlet`. The exception exits through outer filters or to the container; Spring MVC never gets a chance to invoke advice automatically.
3. **Filter throws an exception after `chain.doFilter(...)`:** MVC may already have completed the response. An exception raised afterward still lies outside advice's automatic scope; if the response is already *committed*, changing status/headers/body is also restricted.

Call direction matters: a filter calls `chain.doFilter(...)` to descend into the next layer, then the call stack unwinds back up. A `try/catch` in an outer filter can catch exceptions unwinding from inside; `@ControllerAdvice` inside MVC cannot automatically catch exceptions raised in outer call frames.

## 3. Easily Confused Cases

| Origin / handling method | Does `@ControllerAdvice` handle it automatically? | Appropriate handling point |
| --- | --- | --- |
| Controller throws `IllegalArgumentException` and MVC has a matching `@ExceptionHandler` | **Possibly yes** | MVC `@ExceptionHandler` / `HandlerExceptionResolver` |
| MVC raises mapping, binding, or validation error during a resolver-supported stage | **Depends on error type and resolver** | MVC error-handling configuration |
| Servlet filter throws `RuntimeException` before `chain.doFilter` | **No** | The filter itself, an outer filter, or container/error dispatch |
| Servlet filter throws exception after `chain.doFilter` returns | **No** | Filter/container; check `response.isCommitted()` |
| Authentication error in Spring Security | **Not through advice by default** | Authentication filter/failure handler or `AuthenticationEntryPoint` |
| `AccessDeniedException` within the chain wrapped by `ExceptionTranslationFilter` | **Does not require advice** | `AccessDeniedHandler` or `AuthenticationEntryPoint`, depending on auth state |
| Filter calls `response.sendError(...)` without throwing an exception | **No** | Servlet container may perform an `ERROR` dispatch, e.g., to `/error` |
| Filter **explicitly calls** `HandlerExceptionResolver.resolveException(...)` | **Possibly**, if a resolver matches | Explicitly programmed bridge mechanism, not default behavior |

In particular, HTTP `401` and `403` are typically produced by the security layer; never assume a missing `@ExceptionHandler` method is the cause of all security error responses.

## 4. Spring Boot 3.3.x + Java 17+ Example: Same Exception, Different Outcomes

The following example is a self-contained Spring Boot app in a single Java file. The goal is to compare an `IllegalStateException` thrown in a controller against the same exception type thrown in a Servlet filter. You need a Spring Boot project with the Gradle wrapper and these dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Create `src/main/java/demo/FilterAdviceApplication.java`:

```java
package demo;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.core.Ordered;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class FilterAdviceApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterAdviceApplication.class, args);
    }

    // Allow all GETs in the example to observe the MVC/Filter boundary in isolation.
    @Bean
    SecurityFilterChain securityChain(HttpSecurity http) throws Exception {
        return http.authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
                   .build();
    }

    @Bean
    FilterRegistrationBean<OncePerRequestFilter> demoFilter() {
        var registration = new FilterRegistrationBean<OncePerRequestFilter>();
        registration.setFilter(new OncePerRequestFilter() {
            @Override
            protected void doFilterInternal(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    FilterChain chain) throws ServletException, IOException {
                if ("/demo/filter".equals(request.getRequestURI())) {
                    throw new IllegalStateException("from filter");
                }
                chain.doFilter(request, response);
            }
        });
        registration.addUrlPatterns("/demo/*");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE);
        return registration;
    }

    @RestController
    public static class DemoController {
        @GetMapping("/demo/controller")
        public String controllerFailure() {
            throw new IllegalStateException("from controller");
        }

        @GetMapping("/demo/filter")
        public String filterFailure() {
            return "This method is never reached.";
        }

        @GetMapping("/demo/ok")
        public String ok() {
            return "ok";
        }
    }

    @RestControllerAdvice
    public static class ApiAdvice {
        @ExceptionHandler(IllegalStateException.class)
        public ResponseEntity<ApiError> onIllegalState(
                IllegalStateException exception) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(new ApiError("advice", exception.getMessage()));
        }
    }

    public record ApiError(String source, String message) {}
}
```

Run via `./gradlew bootRun` (Windows: `.\gradlew.bat bootRun`), then call:

```bash
curl -i -H "Accept: application/json" http://localhost:8080/demo/ok
curl -i -H "Accept: application/json" http://localhost:8080/demo/controller
curl -i -H "Accept: application/json" http://localhost:8080/demo/filter
```

Results to observe:

- `/demo/ok` returns HTTP `200`, body `ok`: the filter continues the chain and the controller runs normally.
- `/demo/controller` returns HTTP `500`, JSON body from advice equivalent to `{"source":"advice","message":"from controller"}` (JSON property order is insignificant).
- `/demo/filter` fails before MVC and is normally converted by the container/Spring Boot into HTTP `500` via the default error flow. **The body is not the `ApiError` object created by `ApiAdvice`.** The exact shape of the default error response depends on Spring Boot, content negotiation, and `/error` configuration, so do not assume an exact body for this endpoint.

In the example, `registration.setOrder(Ordered.HIGHEST_PRECEDENCE)` places the demo filter very early. The intent is deliberately to throw outside MVC. It is not a recommendation to use this order for security filters in real applications.

### Verifying via HTTP Integration Test

With `spring-boot-starter-test` above, create `src/test/java/demo/FilterAdviceApplicationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FilterAdviceApplicationTest {
    @Autowired
    TestRestTemplate http;

    @Test
    void mvcAdviceDoesNotAutomaticallyHandleFilterExceptions() {
        ResponseEntity<String> mvc =
                http.getForEntity("/demo/controller", String.class);
        assertThat(mvc.getStatusCode()).isEqualTo(HttpStatus.INTERNAL_SERVER_ERROR);
        assertThat(mvc.getBody()).contains("\"source\":\"advice\"");
        assertThat(mvc.getBody()).contains("from controller");

        ResponseEntity<String> filter =
                http.getForEntity("/demo/filter", String.class);
        assertThat(filter.getStatusCode()).isEqualTo(HttpStatus.INTERNAL_SERVER_ERROR);
        assertThat(String.valueOf(filter.getBody()))
                .doesNotContain("\"source\":\"advice\"");
    }
}
```

Run `./gradlew test` (or `.\gradlew.bat test` on Windows). Testing through a real HTTP server lets you observe the Servlet container and error dispatch. When using `MockMvc` alone without a real container, exceptions from filters may propagate straight out of the test call rather than turning into `/error` JSON automatically; hence never take the behavior of a mock filter chain as a guarantee of real HTTP responses.

## 5. Which Errors Does Spring Security Handle?

In Spring Security Servlet, the key mechanism to remember is **`ExceptionTranslationFilter`**, dedicated to translating certain **security exceptions** into HTTP actions:

- `AuthenticationException`: typically invokes `AuthenticationEntryPoint` to ask the user to authenticate. For APIs, this can often lead to HTTP `401`; for form login it may be a redirect.
- `AccessDeniedException` when the user is **already authenticated** yet lacks permissions: dispatched to `AccessDeniedHandler`, typically HTTP `403`.
- `AccessDeniedException` when the request is **not yet sufficiently authenticated**, such as an anonymous principal: `ExceptionTranslationFilter` may invoke `AuthenticationEntryPoint` instead of returning `403` by default.

However, `ExceptionTranslationFilter` is **not a catch-all exception handler**. It handles exception types designed for authentication/authorization and only sees exceptions thrown inside the `chain.doFilter(...)` segment it wraps. For instance, a custom JWT filter positioned **ahead of** it that throws `AuthenticationException` will not automatically be caught by the downstream filter. Nor does a `NullPointerException` or database error automatically turn into `401`/`403` simply because the request passed through Spring Security.

Some authentication filters handle failures themselves via `AuthenticationFailureHandler` or `AuthenticationEntryPoint`; not every authentication failure goes through the exact same branch of `ExceptionTranslationFilter`.

### Configuring a Unified 401/403 API

Below is an **alternative configuration** for the `permitAll()` `securityChain` bean in the example, not a second bean added alongside it. The real authentication mechanism (JWT, session, HTTP Basic, OAuth2 Resource Server, etc.) must be configured separately to fit the application.

```java
package demo;

import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {
    @Bean
    SecurityFilterChain securityChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint((request, response, error) ->
                                writeError(response, 401, "AUTH_REQUIRED"))
                        .accessDeniedHandler((request, response, error) ->
                                writeError(response, 403, "ACCESS_DENIED")))
                .build();
    }

    private static void writeError(
            HttpServletResponse response, int status, String code)
            throws IOException {
        response.setStatus(status);
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write("{\"code\":\"" + code + "\"}");
    }
}
```

This is an illustrative configuration with two constant error codes, interpolating no user data into JSON. In a real system, use a JSON serializer or shared writer and avoid writing when the response is already committed. For HTTP Basic/Bearer, preserve authentication headers like `WWW-Authenticate` per standard/protocol; framework-provided entry points are usually the better choice when those standards are needed. Never treat `exceptionHandling(...)` as an automatic catcher for every exception thrown by every custom filter.

## 6. What Should You Do If an Error Occurs Inside Your Own Filter?

**Classify errors before choosing a mechanism:**

1. **Business errors from controllers/services:** let Spring MVC handle them via `@ExceptionHandler`, `@RestControllerAdvice`, `ResponseEntity`, or `ProblemDetail` per API design.
2. **Authentication/authorization errors:** integrate into Spring Security through appropriate extension points like `AuthenticationEntryPoint`, `AccessDeniedHandler`, `AuthenticationFailureHandler`, and the right position in the security filter chain. If a custom filter sits ahead of `ExceptionTranslationFilter`, it must handle or delegate errors per an explicit contract.
3. **Request-validation errors in a Servlet filter:** the filter can handle expected exceptions directly on the spot and write a response, or call a shared component responsible for producing the JSON body. Avoid turning unexpected internal errors into 4xx.
4. **Unexpected system errors:** allow container/app logging, monitoring, and 5xx handling to operate; never swallow exceptions silently or expose stack traces to clients.

Example of a filter checking a header and actively terminating the request before MVC (this is an **illustrative class**; register the filter in the app if used):

```java
package demo;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.web.filter.OncePerRequestFilter;

public final class ClientHeaderFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {
        if (request.getHeader("X-Client") == null) {
            response.setStatus(HttpServletResponse.SC_BAD_REQUEST);
            response.setContentType("application/json;charset=UTF-8");
            response.getWriter().write("{\"code\":\"MISSING_X_CLIENT\"}");
            return; // Do not continue the chain; the request never reaches the controller.
        }
        chain.doFilter(request, response);
    }
}
```

Depending on requirements, scope the filter with URL patterns or `shouldNotFilter(...)`; the minimal example above rejects every request lacking the header if registered for all URLs. If the filter sits outside Spring Security, the `400` response is produced before authorization runs; weigh security design and actual ordering accordingly.

### Can Exceptions Be Delegated from a Filter into `HandlerExceptionResolver`?

**Yes, but it must be invoked explicitly**, with a clear grasp of its limits. For example, inside a filter's `catch` branch when the response is not yet committed:

```java
// resolver injected with @Qualifier("handlerExceptionResolver")
ModelAndView handled =
        resolver.resolveException(request, response, null, exception);
if (handled == null) {
    throw exception; // Resolver declined to handle: never swallow the error.
}
```

This is an **illustrative snippet placed inside an existing filter**, not a standalone Java program. `resolver` is `org.springframework.web.servlet.HandlerExceptionResolver`, `ModelAndView` is `org.springframework.web.servlet.ModelAndView`, and `exception` in the example is a `RuntimeException`. Passing `handler = null` reflects that the filter may not yet have selected an MVC handler. An advice scoped by controller/package/annotation may not apply when no handler exists; the resolver may also return `null`. If the response is already written/committed or the resolver does not support this error type, the bridge cannot solve it. Never invoke `DispatcherServlet` directly or trigger dispatch loops hoping advice will run.

A simpler, more controllable approach is letting **filters/security handlers** and **MVC advice** share a common error model (such as `code`, `message`, `traceId`) and a shared serialization/logging service, while each layer decides when to send the response.

## 7. `sendError`, `/error`, and Committed Responses

Three distinct operations exist:

- `throw exception`: hands control back up the call stack and can reach the container if uncaught.
- `response.setStatus(400)` then writing JSON: the filter writes the response directly; `@ControllerAdvice` is not called.
- `response.sendError(400)`: signals an error to the Servlet container; depending on container and app, may trigger an `ERROR` dispatch to an error page or Spring Boot's `/error`.

An `ERROR` dispatch request can traverse filters/security rules registered for that dispatcher type. It is a **separate dispatch**, not proof that the original exception was caught by advice. Distinguish the initial request, error dispatch, and final response in logs.

When `response.isCommitted()` is `true`, status and headers have already been sent or locked; attempting to write another body or change the status code can fail or corrupt the response. Filters that write errors must therefore check response timing, avoid duplicate handling, and never call `chain.doFilter(...)` after writing an error response.

## 8. How to Diagnose a Real Failure

Follow this order:

1. **Locate where the exception was thrown:** does the stack trace point to `Filter#doFilter`, `OncePerRequestFilter#doFilterInternal`, `AuthenticationFilter`/`AuthorizationFilter`, an interceptor, or controller/service? Do not look only at the HTTP status.
2. **Check the original exception type:** `AuthenticationException`, `AccessDeniedException`, MVC binding/validation exception, or another `RuntimeException`? `401`, `403`, `400`, and `500` have distinct mechanisms and meanings.
3. **Inspect the actual filter order:** was the filter container-registered or placed inside `SecurityFilterChain` via `http.addFilterBefore/After(...)`? Is it before or after `ExceptionTranslationFilter`? Was it registered twice (both as a `@Component` Servlet filter and inserted into the security chain)?
4. **Inspect logs of both the original request and any error dispatch:** did it dispatch to `/error`? Did a security rule block `DispatcherType.ERROR`, changing the final status from the original error?
5. **Inspect the response:** was it already committed, did the filter call `sendError` or write JSON, and did it still invoke `chain.doFilter` after writing an error?
6. **Test at the right layer:** test MVC advice via controller endpoints; test security exception handlers with realistic authenticated/anonymous requests; test filters and error dispatches with real HTTP integration tests when container behavior matters.

A common mistake is adding `@ExceptionHandler(Exception.class)` and expecting every exception from a JWT filter to become JSON like a controller exception. That handler covers many MVC exceptions, yet cannot alter the path of an exception thrown before `DispatcherServlet`. Another common mistake is collapsing every authorization failure into `401`, erasing the meaning of `403`, or returning raw JSON while dropping Bearer/Basic `WWW-Authenticate`.

## 9. Key Takeaways

**`@ControllerAdvice` belongs to the Spring MVC boundary. Servlet `Filter`s and Spring Security have their own error-handling flows.** For uniform responses, handle errors at the right layer (`@ExceptionHandler`, security handlers, filters, container/error controller) and share a common body schema where needed. Only when a filter **explicitly** forwards an exception through `HandlerExceptionResolver` does an MVC resolver get a chance to handle it; no automatic mechanism applies advice to every filter.