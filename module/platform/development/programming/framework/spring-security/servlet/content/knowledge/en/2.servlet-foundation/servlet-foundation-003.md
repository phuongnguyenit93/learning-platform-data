# DispatcherServlet and the Position of Servlet Filters Before HandlerInterceptor

> **Scope:** Spring MVC running on the Servlet stack (Spring Boot 3.x, Spring Security 6.x), under the **Servlet Foundation** topic. This lesson explains execution order on a single HTTP request, especially why Spring Security's layer can handle or reject a request before MVC selects a controller. Spring WebFlux uses WebFilter/WebFilterChain and a different dispatch mechanism.

## 1. Three Components at Three Different Positions

When an HTTP request arrives, the **Servlet container** (for example, Tomcat) runs the `jakarta.servlet.Filter` chain. If the request continues to the MVC servlet, **`DispatcherServlet`** acts as the front controller: finding the handler, selecting the execution adapter, and coordinating result handling. **`HandlerInterceptor`** belongs exclusively to Spring MVC and is attached to the `HandlerExecutionChain` after MVC resolves the matching handler.

| Component | Who invokes it? | When does it run? | Suitable responsibilities |
| --- | --- | --- | --- |
| `Filter` (`jakarta.servlet.Filter`) | Servlet container and `FilterChain` | **Outside, before entering `DispatcherServlet`**; often has post-processing when the response returns | CORS, request/response normalization, correlation ID, logging, security at the web boundary |
| `DispatcherServlet` | Servlet container invokes it as an `HttpServlet` | After filters have successfully called `chain.doFilter` to forward | `HandlerMapping`, `HandlerAdapter`, MVC exception handling, response rendering/writing |
| `HandlerInterceptor` | Spring MVC via `HandlerExecutionChain` | **Inside MVC dispatch**, after handler selection and before the controller runs | Attaching handler-specific data, MVC timing, non-core UI/routing checks |

**Rule of thumb:** Filters can block a request *before MVC even knows which controller would handle it*. An MVC interceptor is only invoked once the request has entered `DispatcherServlet` and been mapped to a handler with that interceptor attached.

## 2. Normal Request Flow and Return Path

```text
HTTP client
  |
  v
Servlet container
  |
  v
Filter A.doFilter(...)      <-- runs "before" section
  |
  +-- Filter B.doFilter(...) <-- may be Spring Security's DelegatingFilterProxy
  |     |
  |     +-- ... security filters ... --> may return 401/403 here
  |     |
  |     +-- chain.doFilter(...) if allowed to proceed
  |              |
  |              v
  |        DispatcherServlet
  |              |
  |        HandlerMapping -> handler + HandlerInterceptors
  |              |
  |        interceptor.preHandle()       (in registration order)
  |              |
  |        HandlerAdapter -> Controller
  |              |
  |        interceptor.postHandle()      (in reverse order)
  |              |
  |        result handling / rendering if needed
  |              |
  |        interceptor.afterCompletion() (in reverse order)
  |              |
  |              v
  |          returns to filter B
  |
  v
returns to filter A         <-- runs "after" / finally section
  |
  v
HTTP response
```

The diagram shows a synchronous request completing normally. The names and order of **actual filters** depend on registration configuration and container ordering. `DelegatingFilterProxy` is itself a servlet filter; the security filters it invokes sit *inside* the security chain, not as `HandlerInterceptor`s.

With two nested filters, the snippet below illustrates the “enter in order, exit in reverse order” model:

```java
public void doFilter(ServletRequest request, ServletResponse response,
                     FilterChain chain) throws IOException, ServletException {
    System.out.println("A: before");
    try {
        chain.doFilter(request, response);
    } finally {
        System.out.println("A: after");
    }
}
```

This is an **illustrative method body** of a filter, not a standalone Java class. `chain.doFilter` invokes the next filter or target servlet. If downstream succeeds, `finally` executes on the return path; if downstream throws an exception, `finally` still runs. If the filter **does not call** `chain.doFilter`, `DispatcherServlet` and interceptors will not receive that request on that execution branch.

## 3. What Does DispatcherServlet Do Once a Request Passes the Filters?

In a typical MVC flow:

1. The container selects the servlet by URL mapping and executes matching servlet filters; each filter decides whether to forward or terminate the request.
2. `DispatcherServlet` receives the request. `HandlerMapping` resolves the handler and builds a `HandlerExecutionChain` containing the interceptors applicable to that handler/path.
3. MVC calls each `preHandle(request, response, handler)`. If all return `true`, `HandlerAdapter` invokes the handler (for example, a controller method).
4. For successful synchronous processing, MVC calls `postHandle` in reverse order, then handles the result/rendering if needed.
5. MVC calls `afterCompletion` in reverse order for interceptors whose `preHandle` returned `true`, then finishes the dispatch; only then do the outer filters finish their code after `chain.doFilter`.

Key distinction: `DispatcherServlet` does **not** manage servlet filter ordering; `WebMvcConfigurer.addInterceptors` does **not** place an interceptor ahead of filters. An interceptor cannot guarantee catching every container request (for example, requests rejected early in the security chain or routed to another servlet).

Important conditional hooks:

- `preHandle` returns `false`: MVC stops calling the handler; the interceptor returning `false` does **not** receive its corresponding `postHandle`/`afterCompletion`; preceding interceptors that returned `true` may still have `afterCompletion` called for cleanup.
- Controller/handler throws an error: `postHandle` may not run. `afterCompletion` is typically still called for interceptors with `preHandle=true` after MVC handles the dispatch/exception; do not put cleanup solely inside `postHandle`.
- `@RestController` can write the response body during handler execution; `postHandle` is not a reliable place to modify the response body afterward.
- With async MVC (`Callable`, `DeferredResult`), the initial dispatch pass can end before `postHandle`/`afterCompletion` are called; `AsyncHandlerInterceptor.afterConcurrentHandlingStarted` and the subsequent dispatch must be accounted for.

## 4. Where Does Spring Security Sit?

On the Servlet stack, Spring Security is typically integrated via a servlet filter named **`springSecurityFilterChain`**: the container invokes `DelegatingFilterProxy`, which delegates work to the `FilterChainProxy` bean. `FilterChainProxy` selects the **first matching `SecurityFilterChain`** for the request, then executes the security filters according to Spring Security's internal order.

```text
Container FilterChain
    -> [Application filters, depending on order]
    -> DelegatingFilterProxy("springSecurityFilterChain")
         -> FilterChainProxy
              -> Matching SecurityFilterChain
                   -> SecurityContext / authentication / CSRF / authorization / ...
    -> [Other container filters, depending on order]
    -> DispatcherServlet
         -> HandlerInterceptor
         -> Controller
```

This is a structural diagram; it **does not mandate** that every application filter sits before or after the security proxy. Actual ordering must be checked in the concrete configuration.

Practical consequences:

- If `AuthorizationFilter` or Spring Security's authentication/CSRF components reject the request **before calling the rest of the chain**, the controller and MVC `HandlerInterceptor` will not run for that request.
- `permitAll()` permits access under authorization rules, but the request **still goes through** the matching security filter chain. It differs from excluding a request from the security chain via `web.ignoring()`.
- `SecurityContextHolder` data is not necessarily populated inside *a container filter that runs before the security chain*. A custom filter needing user details must be placed at the proper stage in the security chain and after the relevant authentication mechanism.
- Endpoint authorization should be configured with `authorizeHttpRequests` and, where appropriate, method security. `HandlerInterceptor` is not a substitute endpoint security mechanism for Spring Security: it can be bypassed when requests do not enter MVC or are handled by another servlet.

**Two kinds of ordering that must be configured in the right place:**

| What you want to order | Mechanism |
| --- | --- |
| Servlet filter managed by the container | `FilterRegistrationBean#setOrder` or `@Order` on a Boot-registered filter |
| Filter **inside** Spring Security | `HttpSecurity.addFilterBefore/addFilterAfter/addFilterAt` with an appropriate anchor filter |
| MVC interceptor | `InterceptorRegistry#order` or registration order via `WebMvcConfigurer` |

Do not infer that `@Order` on a servlet filter changes its position *inside* `SecurityFilterChain`. Similarly, registering the same custom filter both as a container filter (for example, a `@Component` bean auto-registered by Boot) and via `http.addFilterBefore(...)` can create two unintended execution paths. When you want it only in the security chain, disable servlet container registration for that filter bean (for example via `FilterRegistrationBean#setEnabled(false)`) and add the filter at the right place in `HttpSecurity`.

## 5. Runnable Example: Filter → Security → Interceptor → Controller

Example using Java 17+, Spring Boot 3.3.x, Spring MVC, and Spring Security 6.x. The goal is to **observe the exact boundary**: `/hello` is allowed into the controller; `/private` is blocked by security before the interceptor. File structure:

```text
servlet-chain-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    TraceFilter.java
    TraceInterceptor.java
    WebConfig.java
    SecurityConfig.java
    DemoController.java
```

`settings.gradle`:

```groovy
rootProject.name = 'servlet-chain-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

`src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`src/main/java/demo/TraceFilter.java` — servlet filter registered by Boot with the container; `HIGHEST_PRECEDENCE` ensures it logs before the security proxy in this example:

```java
package demo;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class TraceFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain)
            throws ServletException, IOException {
        System.out.println("1 FILTER before " + request.getRequestURI());
        try {
            chain.doFilter(request, response);
        } finally {
            System.out.println("6 FILTER after status=" + response.getStatus());
        }
    }
}
```

`src/main/java/demo/TraceInterceptor.java` — this is an MVC component, **not** a container filter:

```java
package demo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.ModelAndView;

@Component
public class TraceInterceptor implements HandlerInterceptor {
    @Override
    public boolean preHandle(HttpServletRequest request,
                             HttpServletResponse response,
                             Object handler) {
        System.out.println("2 INTERCEPTOR preHandle");
        return true;
    }

    @Override
    public void postHandle(HttpServletRequest request,
                           HttpServletResponse response,
                           Object handler,
                           ModelAndView modelAndView) {
        System.out.println("4 INTERCEPTOR postHandle");
    }

    @Override
    public void afterCompletion(HttpServletRequest request,
                                HttpServletResponse response,
                                Object handler,
                                Exception ex) {
        System.out.println("5 INTERCEPTOR afterCompletion");
    }
}
```

`src/main/java/demo/WebConfig.java` — attaches the interceptor only to the two endpoints used in this lesson:

```java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConfig implements WebMvcConfigurer {
    private final TraceInterceptor traceInterceptor;

    public WebConfig(TraceInterceptor traceInterceptor) {
        this.traceInterceptor = traceInterceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(traceInterceptor)
                .addPathPatterns("/hello", "/private");
    }
}
```

`src/main/java/demo/SecurityConfig.java` — only `/hello` is public; all remaining endpoints require authentication:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/hello").permitAll()
                .anyRequest().authenticated());
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

`src/main/java/demo/DemoController.java`:

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/hello")
    public String hello() {
        System.out.println("3 CONTROLLER hello");
        return "Hello";
    }

    @GetMapping("/private")
    public String privateArea() {
        System.out.println("3 CONTROLLER private");
        return "Private";
    }
}
```

From the project directory, run using a pre-installed Gradle or the Gradle wrapper if the project has one:

```bash
gradle bootRun
# or ./gradlew bootRun (macOS/Linux)
# or .\gradlew.bat bootRun (Windows PowerShell)
```

In another terminal:

```bash
curl -i http://localhost:8080/hello
curl -i http://localhost:8080/private
```

**Expected output for `GET /hello`:** HTTP 200, body `Hello`. The `System.out.println` lines produced by the example code appear in order:

```text
1 FILTER before /hello
2 INTERCEPTOR preHandle
3 CONTROLLER hello
4 INTERCEPTOR postHandle
5 INTERCEPTOR afterCompletion
6 FILTER after status=200
```

**Expected output for `GET /private` without credentials:** typically HTTP 401 (`httpBasic` configuration). Because Spring Security blocks it before MVC, the corresponding lines for this request are only:

```text
1 FILTER before /private
6 FILTER after status=401
```

There is no `INTERCEPTOR preHandle` or `CONTROLLER private` for the rejected request. Spring Boot/Spring Security's own logs may interleave; an `ERROR` dispatch or a differently configured environment can produce additional processing passes, without changing the boundary principle. To test the authenticated allowed path, supply valid credentials per the application's authentication setup (Spring Boot may generate a default development account when no user is defined).

**Significance of the experiment:** A filter placed at the container level sees both requests; the MVC interceptor only sees requests that entered the MVC processing cycle. In the example, `TraceFilter` is a standalone servlet filter; if you put a filter inside `SecurityFilterChain` itself, its order and execution conditions must be configured on `HttpSecurity`.

## 6. Common Misconceptions

### 6.1. “Does every filter always run before every interceptor?”

For **a single synchronous dispatch**, servlet filters applicable to the request wrap the call to `DispatcherServlet`; code before `chain.doFilter` runs before MVC hooks, and code after `chain.doFilter` normally runs after MVC finishes. However, there are multiple filters with different orders; a filter may not apply due to URL pattern/dispatcher type, may stop the chain, or the request may go to a different servlet. Do not deduce **which** filter sits ahead of the security proxy solely from the word “Filter”.

### 6.2. “Is protecting APIs with an interceptor enough?”

No. `HandlerInterceptor` only attaches to properly routed MVC handlers. Requests rejected in filters, or routed to servlets outside Spring MVC, will never reach interceptors. Authentication, authorization, CSRF, session, and HTTP security policies belong in Spring Security. Interceptors are better suited for *MVC handler-coupled* logic, such as enriching route metadata or measuring MVC handler time.

### 6.3. “If `preHandle=false` or security returns 401, does `Filter.after` run?”

Normally **yes**, if the filter uses `try/finally` around `chain.doFilter` as in the example. `preHandle=false` stops the MVC handler; security returning 401 can stop before MVC. Both can still return control to outer filters, causing `finally` to execute. Exceptions such as abrupt process termination fall outside normal Java control flow.

### 6.4. “Does `OncePerRequestFilter` guarantee once in all cases?”

Do not take it as absolute. It provides a marking mechanism to avoid duplicate execution within supported dispatch scopes; async requests and `ERROR` dispatches have their own rules, governed by `shouldNotFilterAsyncDispatch`, `shouldNotFilterErrorDispatch`, and registered dispatcher types. Do not assume “always exactly once across the entire HTTP transaction” when handling async/error dispatches or when a filter is registered in multiple ways.

### 6.5. “Where should reading bodies, catching errors, and modifying responses live?”

- Filters are well suited for wrapping `HttpServletRequest`/`HttpServletResponse`, though reading the body directly can starve the controller of the stream; if multiple reads are required, use proper wrapping/caching.
- Exceptions thrown **before** `DispatcherServlet` are generally not handled automatically by `@ControllerAdvice`/`HandlerExceptionResolver` like controller exceptions. For authentication/authorization errors, use Spring Security's mechanisms such as `AuthenticationEntryPoint` or `AccessDeniedHandler`.
- An interceptor's `postHandle` is not a general-purpose solution for altering a JSON body already written by `@ResponseBody`; response customization must target the appropriate layer (message converter, `ResponseBodyAdvice`, filter/wrapper, depending on the goal).
- CORS preflight must be handled in coordination with Spring Security; do not wait for an MVC interceptor to decide on an `OPTIONS` request already rejected by security.

### 6.6. “Why do duplicate logs appear for the same URL?”

Check `DispatcherType.REQUEST`, `ASYNC`, `ERROR`, `FORWARD`, the filter's dispatcher types configuration, async MVC, and forwards to `/error`. Also check whether a custom filter is auto-registered in the servlet container *and* simultaneously added to the Spring Security chain. Do not conclude every repeated log means the controller ran twice.

## 7. How to Inspect a Real Request

When runtime order in an application does not match expectations, determine: (1) URL and dispatcher type; (2) container filter registrations and order; (3) the `springSecurityFilterChain` proxy and `SecurityFilterChain` list/matchers; (4) whether an internal filter stops `chain.doFilter` or returns an error; (5) whether the request actually reaches `DispatcherServlet` and which handler `HandlerMapping` picks; (6) whether the interceptor matches the path/handler and `preHandle` returns `true`. Logging a request ID across layers helps trace concurrent traffic accurately.

These log checkpoints help distinguish cases:

| Symptom | First hypothesis to check |
| --- | --- |
| `Filter.before` and `Filter.after` appear, no `Interceptor.preHandle` | Blocked early in filter/security, never entered MVC, or interceptor did not match |
| `Interceptor.preHandle` appears, no controller | `preHandle=false`, exception before handler, or handler call did not complete normally |
| Controller and `afterCompletion` appear, no `postHandle` | Possibly error path or async processing; check exceptions/dispatches |
| Repeated `Filter.before` | Possibly multiple dispatch types or filter registered in multiple places; verify via request ID and `DispatcherType` |

## 8. Self-Check

1. If security returns 401 before `DispatcherServlet`, does `HandlerInterceptor.preHandle` run? **No, for requests blocked on that branch.**
2. Does `@Order` on a container filter order filters *inside* Spring Security? **No; use the `HttpSecurity` API for ordering inside the security chain.**
3. Why is `afterCompletion` better suited for resource cleanup than `postHandle`? **Because `postHandle` can be skipped on exception paths; `afterCompletion` is invoked for interceptors with `preHandle=true` after MVC finishes synchronous processing.**
4. To enforce authentication on `/private`, should you use an interceptor or `SecurityFilterChain`? **Use Spring Security; interceptors only supplement MVC-specific logic.**
5. Why does `Filter.after` appear after `Interceptor.afterCompletion`? **Servlet filters wrap the downstream call with `chain.doFilter`; MVC completes its dispatch before returning to the caller inside the filter.**

**Key takeaway:** `Filter` is the Servlet container boundary; `DispatcherServlet` is Spring MVC's front controller; `HandlerInterceptor` lives inside MVC after handler selection. Spring Security Servlet operates primarily through filters, allowing it to control requests before controllers and MVC interceptors are invoked.
