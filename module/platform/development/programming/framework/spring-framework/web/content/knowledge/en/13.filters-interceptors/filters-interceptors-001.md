# Distinguishing Servlet Filter, HandlerInterceptor, AOP, and ControllerAdvice in Spring MVC

> **Scope:** Spring Web MVC on the Servlet stack, Java 17+, and Spring Boot 3.x / Spring Framework 6.x. All four mechanisms appear to “run before or after” a piece of work, but they intervene at **different layers and times**: `Servlet Filter` wraps the request/response in the Servlet chain; `HandlerInterceptor` observes the handler execution chain already mapped by Spring MVC; **Spring AOP** intercepts **Spring bean method calls through proxies**; `@ControllerAdvice` provides shared functionality for **MVC controllers**, especially error handling and binding/model customization. The four should not be treated as equivalent or interchangeable.

## 1. The Big Picture: Where Does Each Mechanism Sit?

A request enters a Spring Boot Servlet app according to the following simplified model:

```text
HTTP client
    |
Servlet container (Tomcat / Jetty / ...)
    |
    v
[ Servlet Filter 1 ] --+
    |                  | before/after FilterChain.doFilter(...)
[ Servlet Filter 2 ] --+
    |
    v
DispatcherServlet
    |
    v
HandlerMapping selects handler / HandlerExecutionChain
    |
    v
[ HandlerInterceptor.preHandle ]
    |
    v
HandlerAdapter invokes @Controller method
    |                 \
    |                  \-> @ControllerAdvice @InitBinder / @ModelAttribute
    |                                   (when resolving model/binding)
    v
Controller calls Spring bean service (proxy if present)
    |
    v
[ Spring AOP @Around / @Before / @After ... ]
    |
    v
service / repository / business logic
    |
    +------ if exception in MVC -----------------------+
    |                                                |
    v                                                v
HTTP body / view                              MVC exception resolver
    |                                           |
    |                                  local @ExceptionHandler,
    |                                  then matching @ControllerAdvice
    |
[ HandlerInterceptor.postHandle ] (successful synchronous flow)
    |
View rendering if applicable
    |
[ HandlerInterceptor.afterCompletion ]
    |
Return to filter chain (finally / logic after doFilter)
    |
HTTP response
```

The diagram intentionally omits many details: validation can happen **before the controller method starts**; Spring Security is typically a separate filter chain; JSON content from `@ResponseBody` has often already been written inside `HandlerAdapter` **before** `postHandle` is called; async requests involve additional dispatches; a successfully handled exception can cause `afterCompletion` to receive `ex = null`. Those details make the real difference in practice.

### 1.1. Quick Comparison Table

| Aspect | Servlet Filter | HandlerInterceptor | Spring AOP | ControllerAdvice |
| --- | --- | --- | --- | --- |
| Which layer? | Servlet API | Spring Web MVC | Spring Core AOP/proxy | Spring Web MVC controller infrastructure |
| Hook point | Servlet request/response dispatch | `HandlerExecutionChain` after Spring MVC selects handler | Method calls intercepted by Spring proxy | Resolvers for exceptions, binder/model, and specialized advice |
| Typical scope | Registered HTTP paths and dispatcher types, including requests not entering MVC | Registered HandlerMapping / path patterns | Methods of Spring-managed beans matching pointcut | Controllers within the advice's target scope |
| Runs before handler? | Yes, before `DispatcherServlet` | `preHandle` does | Yes if AOP pointcut covers the invoked method | Not a general “preHandle”; certain hooks apply when preparing model/binder |
| Post-processing | Code after `chain.doFilter` / `finally` | `postHandle`, `afterCompletion` | `@After`, `@AfterReturning`, `@AfterThrowing`, `@Around` | `@ExceptionHandler`, `ResponseBodyAdvice`, and specialized hooks |
| Direct HTTP request? | Yes, `ServletRequest`/`HttpServletRequest` | Yes, `HttpServletRequest` and handler | Does not require HTTP by default; can run in batch/scheduler | Has MVC context depending on method/hook |
| Can block request? | Yes, by not calling `chain.doFilter` | Yes, `preHandle` returns `false` | Can replace/skip calling `proceed()`, but only for proxied methods | Can turn an exception into an HTTP response; not a filter |
| Best suited for | Early HTTP policy, logging/correlation, encoding, security filters | Measuring/attaching metadata related to MVC handler, locale, and routing-level handling | Transactions, metrics/service logging, cross-layer policies | REST error contract, shared `@InitBinder`, shared `@ModelAttribute`, response body advice |
| Key limitation | Does not automatically know the selected controller method | Should not be used as the primary security layer | Self-invocation bypasses the proxy | Does not automatically catch every error from Servlet Filters |
| Common registration | `@Component`/`FilterRegistrationBean` | `WebMvcConfigurer#addInterceptors` | `@Aspect` + AOP auto-proxy config/starter | `@ControllerAdvice` / `@RestControllerAdvice` bean |

**Rule of thumb for choosing:** if the policy concerns **requests entering the application**, think Filter; if you need the **mapped MVC handler**, think Interceptor; if it concerns **business methods**, think AOP; if you want **unified controller errors/binding/model**, think ControllerAdvice.

## 2. Servlet Filter: Intervening at the HTTP/Servlet Boundary

`jakarta.servlet.Filter` belongs to the Servlet API, not a Spring MVC-specific annotation. Spring Boot 3.x uses the **`jakarta.servlet.*`** namespace; older Spring Boot 2.x code typically uses **`javax.servlet.*`**, and the imports cannot be mixed arbitrarily.

Interface structure:

```java
public interface Filter {
    void init(FilterConfig filterConfig) throws ServletException;
    void doFilter(ServletRequest request,
                  ServletResponse response,
                  FilterChain chain)
            throws IOException, ServletException;
    void destroy();
}
```

This is an illustrative Servlet API signature (the `init`/`destroy` methods may have default implementations depending on the API version). The key part is `chain.doFilter(request,response)`: the filter hands control to the next component. If a filter does **not** call `chain.doFilter`, the request can stop at that filter (if it provides an appropriate response itself).

### 2.1. How Does a Filter Wrap a Request?

```java
@Override
public void doFilter(ServletRequest request,
                     ServletResponse response,
                     FilterChain chain)
        throws IOException, ServletException {

    long started = System.nanoTime();
    try {
        chain.doFilter(request, response);
    } finally {
        long duration = System.nanoTime() - started;
        System.out.println("request nanos=" + duration);
    }
}
```

This is an **illustrative method**, which must be placed inside a class implementing `Filter` with Servlet classes imported. Code before `doFilter` runs before the downstream chain; code in `finally` runs when the chain returns control or throws an exception. If the response is already committed, modifying status/headers in `finally` may be too late.

**Requests a Filter can see:** MVC routes, static resources, other servlet endpoints, and certain error/async dispatches depending on filter registration. Do not claim that every Filter is guaranteed to run for **every dispatcher type**; URL pattern registration and `DispatcherType.REQUEST`, `ASYNC`, `ERROR`, `FORWARD`, `INCLUDE` determine the scope.

### 2.2. Using Spring's `OncePerRequestFilter`

In a Spring MVC app, it is common to use:

```java
@Component
class CorrelationFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        request.setAttribute("traceId", "demo-trace");
        response.setHeader("X-Trace-Id", "demo-trace");
        chain.doFilter(request, response);
    }
}
```

This is a class snippet; it requires importing `org.springframework.web.filter.OncePerRequestFilter`, `org.springframework.stereotype.Component`, and the Jakarta HTTP/Servlet API. `OncePerRequestFilter` helps prevent unintended repeated execution within a single **dispatch** via a request-marking mechanism; do not interpret it as “strictly once across all threads and async/error dispatches.” For async/error dispatches, check the `shouldNotFilterAsyncDispatch()` and `shouldNotFilterErrorDispatch()` hooks and dispatcher registration.

### 2.3. Filter Registration and Ordering

Spring Boot can register a `Filter` bean (for example `@Component`) with the servlet container. When explicit path restrictions or priority are needed, use `FilterRegistrationBean`:

```java
@Bean
FilterRegistrationBean<MyFilter> myFilterRegistration(MyFilter filter) {
    FilterRegistrationBean<MyFilter> bean = new FilterRegistrationBean<>();
    bean.setFilter(filter);
    bean.addUrlPatterns("/api/*");
    bean.setOrder(10);
    return bean;
}
```

This is a configuration snippet, requiring class `MyFilter` and imports for `FilterRegistrationBean`, `@Bean`; do **not** declare multiple independent registrations for the same filter at the same time unless duplication is intended. `setOrder` expresses relative registration order among Boot filters under applicable conditions. Absolute ordering also depends on the Security filter chain, Servlet registration, and dispatcher types: use integration tests rather than guessing from numbers alone.

### 2.4. When to Choose a Filter?

Suitable for:
- Generating a trace/correlation ID before MVC; logging requests and total latency.
- Standardizing encoding/request wrappers and response headers that need to be set early.
- Policies applying to static resources or non-MVC servlets in a servlet application.
- Rate limiting and HTTP boundary protection when designed at the appropriate filter/gateway layer.
- Spring Security uses `FilterChainProxy` in the Servlet filter chain, because authentication/authorization must occur early enough.

**Not suitable for:** directly accessing the selected `HandlerMethod` to inspect controller annotations, unless deeply integrated manually or left to an Interceptor. A Filter runs **before** `DispatcherServlet` selects an MVC handler, so it does not know by default which controller method will be invoked.

## 3. HandlerInterceptor: Intervening in the MVC Execution Chain

`org.springframework.web.servlet.HandlerInterceptor` runs in Spring MVC when `HandlerMapping` identifies a handler and builds a `HandlerExecutionChain`. Core API:

```java
public interface HandlerInterceptor {
    boolean preHandle(HttpServletRequest request,
                      HttpServletResponse response,
                      Object handler) throws Exception;

    void postHandle(HttpServletRequest request,
                    HttpServletResponse response,
                    Object handler,
                    ModelAndView modelAndView) throws Exception;

    void afterCompletion(HttpServletRequest request,
                         HttpServletResponse response,
                         Object handler,
                         Exception ex) throws Exception;
}
```

This is a summarized signature (the interface has default methods in modern Spring MVC). Meaning:

- `preHandle`: called **before the handler is invoked**. Return `true` to continue; return `false` to stop the rest of the chain and skip the handler. When stopping, the interceptor itself is responsible for providing an appropriate response.
- `postHandle`: called after the handler finishes **successfully in a synchronous flow**, before traditional view rendering. With `@ResponseBody` / `ResponseEntity`, the body may already have been written to the response by the converter at this point.
- `afterCompletion`: called when request processing completes for interceptors whose `preHandle` succeeded, including many exception cases. Useful for cleaning up thread-locals/metrics; the `ex` parameter **does not necessarily** reflect every exception already handled by a resolver.

### 3.1. Registering an Interceptor in Spring Boot MVC

```java
@Configuration
class WebConfiguration implements WebMvcConfigurer {

    private final TraceInterceptor traceInterceptor;

    WebConfiguration(TraceInterceptor traceInterceptor) {
        this.traceInterceptor = traceInterceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(traceInterceptor)
                .addPathPatterns("/api/**")
                .excludePathPatterns("/api/public/**");
    }
}
```

This snippet requires `TraceInterceptor` as a Spring bean and imports for `Configuration`, `WebMvcConfigurer`, `InterceptorRegistry`. Path patterns here apply to MVC handler mappings belonging to the MVC configuration; it does not turn the interceptor into a container-wide Filter. Whichever controller matches the corresponding MVC handler mapping gets the interceptor applied.

A `MappedInterceptor` bean can be declared when sharing across multiple `HandlerMapping` instances is needed. If there are custom handler mappings or secondary frameworks, verify the scope of the Java config registration. A `HandlerInterceptor` can also run for a resource handler if the pattern matches; it **does not necessarily run only for `@RequestMapping` methods**.

### 3.2. HandlerMethod and Controller Information

```java
@Override
public boolean preHandle(HttpServletRequest request,
                         HttpServletResponse response,
                         Object handler) {

    if (handler instanceof HandlerMethod hm) {
        String methodName = hm.getMethod().getName();
        request.setAttribute("controllerMethod", methodName);
    }
    return true;
}
```

The snippet above is just a method. `HandlerMethod` lets you inspect the method/controller selected by Spring MVC. However, `handler` is declared as `Object` because some handlers are not `HandlerMethod` (such as resource handlers). Always check with `instanceof`.

### 3.3. Multiple Interceptors: Callback Ordering

If interceptor A is registered before B, a synchronous error-free request where both `preHandle` calls return `true` typically follows this sequence:

```text
A.preHandle
B.preHandle
@Controller handler
B.postHandle
A.postHandle
View render (if applicable)
B.afterCompletion
A.afterCompletion
```

This resembles a “wrapping” structure: `pre` in registration order; `post`/`after` in reverse order. If B returns `false`, the handler does not run, and `afterCompletion` callbacks apply only to preceding interceptors that completed `preHandle=true`; do not assume B's `afterCompletion` will run when B itself rejects the request.

### 3.4. Why Not Add Headers in `postHandle` for REST JSON?

With `@ResponseBody`, `HandlerAdapter` may already have written/committed the response before `postHandle` runs. Therefore:

```java
// Unreliable for an already-written REST response:
@Override
public void postHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        ModelAndView modelAndView) {
    response.setHeader("X-Late", "may-not-be-sent");
}
```

This is an illustrative anti-pattern. If a header is needed before the body is written, set it in `preHandle`, in a Filter before `chain.doFilter`, or in `ResponseEntity`. If the goal is to **modify/wrap the JSON body structure** or add logic before the converter writes, look at `ResponseBodyAdvice` instead of assuming `postHandle` always works.

### 3.5. Security Considerations

Official Spring MVC documentation **does not recommend interceptors as the primary security layer** because mismatches can occur between interceptor path matching and annotated controller mappings. Use **Spring Security** or an equivalent layer operating early in the Servlet filter chain. Interceptors are reasonable for supplementing handler-related logging/metrics, localization, or auxiliary checks that do not replace primary authorization.

## 4. Spring AOP: Intercepting Spring Bean Method Calls

Spring AOP follows **aspect-oriented programming**: applying cross-cutting logic across multiple method calls without duplicating the same code into every service.

Terminology:

| Concept | Example | Meaning |
| --- | --- | --- |
| **Aspect** | `@Aspect` class | Where cross-cutting logic is declared |
| **Advice** (AOP) | `@Around` / `@Before` | Code executed at a matching join point |
| **Join point** | Method call on a proxied bean | Point where interception can occur |
| **Pointcut** | `execution(* com.example.demo..service..*(..))` | Expression selecting methods |
| **Proxy** | JDK dynamic proxy or CGLIB | Intermediary object executing advice |
| **ProceedingJoinPoint** | `pjp.proceed()` | Allows the target method to continue from `@Around` |

**Do not confuse the AOP term “Advice”** with `@ControllerAdvice`: one is aspect/proxy method interception, while the other is Web MVC controller infrastructure.

### 4.1. An Aspect Around a Service Method

```java
@Aspect
@Component
class ServiceTimingAspect {

    @Around("execution(* com.example.demo.GreetingService.greet(..))")
    Object time(ProceedingJoinPoint joinPoint) throws Throwable {
        long started = System.nanoTime();
        try {
            return joinPoint.proceed();
        } finally {
            long elapsed = System.nanoTime() - started;
            System.out.println("service nanos=" + elapsed);
        }
    }
}
```

This snippet requires class `GreetingService` and imports for AspectJ annotations, Spring component, and `ProceedingJoinPoint`. With Spring Boot 3.x, add the starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
```

Spring Boot auto-configures AOP when the appropriate dependency is present; manual `@EnableAspectJAutoProxy` is not always needed. An aspect only runs when the call **goes through the proxy** and matches the pointcut; it is not HTTP middleware. Methods invoked from a scheduled task or message consumer can also be intercepted by AOP if invoked through a proxied bean.

### 4.2. What Is Self-Invocation?

```java
@Service
class OrderService {

    public void outer() {
        inner(); // internal call on 'this', does not go through proxy
    }

    public void inner() {
        // A pointcut matching only inner() may not run here.
    }
}
```

This is an illustrative snippet. If a bean method calls another method on the **same instance** via `this`, it does not go through the Spring AOP proxy, so advice applied to `inner()` may be bypassed. This is a prominent limitation of proxy-based Spring AOP. The usual proper fix is extracting the responsibility into another Spring bean and injecting it, rather than self-calling through a proxy or hacking with `AopContext.currentProxy()`.

Depending on proxy mode:
- **JDK dynamic proxy** typically applies via interfaces.
- **CGLIB proxy** subclasses the class, constrained by final classes/final methods and visibility.
- Spring Boot has its own defaults that may select class-based proxies; do not infer the default solely from the Java rule of whether an interface exists.

### 4.3. Spring AOP Is Not HTTP Middleware

AOP sees **method invocations**, not **every URL automatically**. It may not run if:
- The bean is not managed by the Spring container.
- The method call does not go through the proxy.
- The pointcut does not match, or the method cannot be advised due to proxy constraints.
- The object is created directly with `new` instead of being a Spring-managed bean.

AOP fits metrics/service policies, transaction boundaries, business call auditing (when adhering to security contracts), or cross-layer behaviors. Spring `@Transactional` relies on proxy/AOP infrastructure in common configurations, so self-invocation is also a hazard for transactional methods.

**Do not use AOP to hand-roll all HTTP security checks.** For web authentication/authorization, use Spring Security filters/method security; do not rely solely on custom aspect logic that misses non-proxied paths.

## 5. @ControllerAdvice: Shared Functionality for MVC Controllers

`@ControllerAdvice` is an annotation on a Spring bean used to declare methods providing shared behavior for controllers within its scope. `@RestControllerAdvice` is equivalent to `@ControllerAdvice` combined with `@ResponseBody` behavior for the associated response methods.

Three most important hook groups:

1. **`@ExceptionHandler`:** converts exceptions during MVC processing into error HTTP responses/views.
2. **`@InitBinder`:** customizes `WebDataBinder` for model binding/formatting/validation.
3. **`@ModelAttribute` methods:** contribute shared model attributes for controllers.

In addition, a `@ControllerAdvice` bean can implement `ResponseBodyAdvice<T>` to intervene right before a response body is written by a converter. This is a separate extension interface and **does not mean every `@ControllerAdvice` class automatically has a pre/post callback around every request**.

### 5.1. Shared Exception Handler

```java
@RestControllerAdvice
class ApiErrorAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> badArgument(
            IllegalArgumentException ex) {

        return ResponseEntity.badRequest()
                .body(Map.of("error", "Invalid request"));
    }
}
```

This is a class snippet; import `RestControllerAdvice`, `ExceptionHandler`, `ResponseEntity`, and `java.util.Map`. If a controller/service (within the request lifecycle visible to the MVC resolver) throws `IllegalArgumentException`, Spring chooses this handler when no higher-priority local handler applies.

**Precedence rules:** a local `@ExceptionHandler` inside the controller is considered before global handlers from `@ControllerAdvice`. When multiple advice beans match, `@Order` and root/cause exception matching also matter. Do not define a generic `@ExceptionHandler(Exception.class)` that returns HTTP 400 for every system error.

### 5.2. InitBinder to Control Form Binding

```java
@ControllerAdvice(annotations = Controller.class)
class FormBinderAdvice {

    @InitBinder("profileForm")
    void onlyPublicFields(WebDataBinder binder) {
        binder.setAllowedFields("displayName", "bio");
    }
}
```

Illustrative snippet: `@InitBinder` applies to the `profileForm` model attribute in controllers within the advice's scope. It does not create an HTTP filter by itself, nor does it apply as a JSON allowlist for Jackson `@RequestBody`. Protect data binding with dedicated DTOs and check update permissions in the service layer.

### 5.3. Shared Model Attributes

```java
@ControllerAdvice
class PageModelAdvice {

    @ModelAttribute("siteName")
    String siteName() {
        return "Demo MVC";
    }
}
```

This method provides view-rendering controllers with the `siteName` attribute if they fall within the advice's scope. Do not use it to load expensive data on every request unnecessarily; for pure REST APIs, populating a model may not be useful.

### 5.4. ResponseBodyAdvice for JSON

If you want to adjust the **response body** before the converter writes:

```java
@RestControllerAdvice
class VersionAdvice implements ResponseBodyAdvice<Object> {

    @Override
    public boolean supports(MethodParameter returnType,
            Class<? extends HttpMessageConverter<?>> converterType) {
        return true; // Demo: broad application; production must be selective.
    }

    @Override
    public Object beforeBodyWrite(Object body,
            MethodParameter returnType,
            MediaType selectedContentType,
            Class<? extends HttpMessageConverter<?>> converterType,
            ServerHttpRequest request,
            ServerHttpResponse response) {
        response.getHeaders().add("X-API-Version", "1");
        return body;
    }
}
```

This is a **standalone snippet, not to be added to the runnable example in Section 8**. It requires importing `ResponseBodyAdvice`, `MethodParameter`, `HttpMessageConverter`, `MediaType`, `ServerHttpRequest`, `ServerHttpResponse`, and `RestControllerAdvice`. This feature runs close to the moment the message converter writes the response, unlike `HandlerInterceptor.postHandle`. With `supports()=true`, carefully check text, binary, streaming, and error responses to avoid interfering with unsuitable responses. If only adding a static header, a Filter or `ResponseEntity` can be simpler.

### 5.5. What ControllerAdvice Does Not Do

- Does not cover every Servlet request like a Filter.
- Is not automatically called once before and after **every controller handler**; callbacks depend on the specific feature (error/binder/model/body).
- Does not automatically catch exceptions originating entirely from a Servlet filter **before** `DispatcherServlet` is invoked, because the error may not have entered the MVC exception resolver.
- Is not an AOP aspect: `@ControllerAdvice` does **not** handle arbitrary method calls in services/batches.
- Does not override a local `@ExceptionHandler` by default when both match.

### 5.6. Limiting the Scope of Global Advice

```java
@RestControllerAdvice(basePackages = "com.example.demo.api")
class ApiOnlyErrors {
    // ...
}
```

The annotation also supports `basePackageClasses`, `assignableTypes`, or `annotations` to target specific controller groups. Being called “global” does not mean it cannot be scoped. Use targeted selectors to avoid handling HTML view errors and REST errors with an inappropriate body contract.

## 6. Comparing Callback Order in Real Scenarios

### 6.1. Successful Synchronous JSON Request

For example, a client calls `GET /api/greet?name=Lan`:

```text
TraceFilter before chain.doFilter
  -> TraceInterceptor.preHandle
     -> Controller method starts
        -> ServiceTimingAspect.before/proceed
           -> GreetingService.greet
        <- ServiceTimingAspect.after
     <- Controller returns DTO
     -> HttpMessageConverter writes JSON
  <- TraceInterceptor.postHandle (JSON may already be written)
  <- TraceInterceptor.afterCompletion
TraceFilter finally / after chain.doFilter
```

Not every callback follows the exact same before/after structure, and async handling can alter the sequence. A `@RestControllerAdvice` declaring only `@ExceptionHandler` will **not run** in the success path above.

### 6.2. Service Throws Exception, Handled by ControllerAdvice

```text
Filter before
  -> Interceptor.preHandle
     -> Controller
        -> AOP around service
           -> service throws IllegalArgumentException
        <- AOP finally
     -> MVC catches exception
     -> @RestControllerAdvice @ExceptionHandler
     -> HTTP 400 + JSON error
  -> Interceptor.afterCompletion
Filter finally
```

`postHandle` normally **does not run** when a handler throws an exception; the exception resolver may produce its own response. `afterCompletion` can still be called after MVC finishes handling, though its `ex` parameter may be `null` if the exception was handled by the resolver. Do not rely on `afterCompletion(ex != null)` as the sole source for counting all HTTP exceptions.

### 6.3. Filter Blocks Request Before MVC

```text
Filter detects invalid early request
  -> response.setStatus(400)
  -> write safe body
  -> return without chain.doFilter
     X DispatcherServlet
     X HandlerInterceptor
     X @Controller
     X @ControllerAdvice @ExceptionHandler
```

Because the request never enters MVC, local/global MVC exception handlers have no opportunity to run as usual. If a unified error contract from Filters/Spring Security is desired, use a handler/writer suited to the filter stack or explicitly delegate through a designed interface; do not assume `@RestControllerAdvice` automatically catches pre-MVC errors.

### 6.4. Request to a URL Without an MVC Handler

A properly registered Filter **can** run and see the request. An Interceptor only runs if MVC finds a matching handler mapping (note that the framework may have `ResourceHttpRequestHandler` for static resources). Spring Boot's error page or fallback handler may handle the request depending on configuration; do not assume every 404 triggers `HandlerInterceptor.preHandle` for a controller method.

## 7. Complete Runnable Example: Observing All Four Mechanisms

This is a **Spring Boot 3.x, Java 17+** application using **Spring Web** and **Spring AOP**. It omits Spring Security, databases, Thymeleaf, and WebFlux. Place the code below into a single file `src/main/java/com/example/demo/DemoApplication.java`; one public class, with the remaining classes validly package-private.

### 7.1. Dependencies

Create a Maven project at [Spring Initializr](https://start.spring.io/) with Java 17+ and the two dependencies **Spring Web** and **Spring AOP**, equivalent to:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
  </dependency>
</dependencies>
```

This is a fragment in `pom.xml`; Initializr provides the Spring Boot parent/BOM, version, plugins, and remaining project metadata. The AOP starter supplies the libraries required for `@Aspect`, and Boot auto-configures proxies under normal conditions.

### 7.2. Full Java Source

```java
package com.example.demo;

import java.io.IOException;
import java.util.Map;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

// LAYER 1: Servlet Filter. Boot registers the Filter bean.
@Component
class TraceFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        response.setHeader("X-Filter", "seen");
        System.out.println("FILTER before");
        try {
            chain.doFilter(request, response);
        } finally {
            System.out.println("FILTER after");
        }
    }
}

// LAYER 2: MVC HandlerInterceptor.
@Component
class TraceInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        response.setHeader("X-Interceptor", "seen");
        System.out.println("INTERCEPTOR preHandle");
        return true;
    }

    @Override
    public void postHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            org.springframework.web.servlet.ModelAndView modelAndView) {

        System.out.println("INTERCEPTOR postHandle");
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception ex) {

        System.out.println("INTERCEPTOR afterCompletion");
    }
}

@Configuration
class MvcConfig implements WebMvcConfigurer {

    private final TraceInterceptor interceptor;

    MvcConfig(TraceInterceptor interceptor) {
        this.interceptor = interceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(interceptor)
                .addPathPatterns("/api/**");
    }
}

// LAYER 3: Spring-managed service via AOP proxy.
@Service
class GreetingService {

    public String greet(String name) {
        System.out.println("SERVICE greet");

        if ("bad".equalsIgnoreCase(name)) {
            throw new IllegalArgumentException("invalid name");
        }
        return "Hello, " + name;
    }
}

@Aspect
@Component
class ServiceTraceAspect {

    @Around("execution(* com.example.demo.GreetingService.greet(..))")
    public Object around(ProceedingJoinPoint joinPoint)
            throws Throwable {

        System.out.println("AOP before");
        try {
            return joinPoint.proceed();
        } finally {
            System.out.println("AOP after");
        }
    }
}

// Controller only holds HTTP mapping and calls the service.
@RestController
@RequestMapping("/api")
class GreetingController {

    private final GreetingService service;

    GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/greet")
    public Map<String, String> greet(
            @RequestParam(defaultValue = "Lan") String name) {

        return Map.of("message", service.greet(name));
    }
}

// LAYER 4: Shared MVC error policy.
@RestControllerAdvice
class ApiErrors {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> invalidName(
            IllegalArgumentException ex) {

        System.out.println("ADVICE exceptionHandler");
        return ResponseEntity.badRequest()
                .body(Map.of("error", "name invalid"));
    }
}
```

**Key points to read accurately:**
- `TraceFilter` extends `OncePerRequestFilter`, runs in the Servlet filter chain, and sets `X-Filter` before the request enters MVC.
- `TraceInterceptor` is registered for `/api/**`, setting `X-Interceptor` in `preHandle` to ensure the header can be written before the body.
- `GreetingService` is a Spring `@Service`. The controller injects the Spring-provided bean; the call to `greet(...)` passes through the AOP proxy, so `ServiceTraceAspect` runs.
- `ServiceTraceAspect` logs `AOP before` and `AOP after` even when `greet(...)` throws an exception, because the trailing statement is placed in `finally`.
- `ApiErrors` is a `@RestControllerAdvice`, selecting `@ExceptionHandler(IllegalArgumentException.class)` only when a matching exception reaches the MVC exception resolver.
- The demo uses `System.out.println` strictly to observe callbacks; production code should use appropriate structured logging/tracing/metrics. Concurrent requests may interleave log lines.
- There is no `@EnableAspectJAutoProxy` because Spring Boot 3.x with the AOP starter enables the appropriate proxy infrastructure by default.

### 7.3. Running

From the Maven project directory:

```bash
# Linux or macOS
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
```

By default, the server runs at `http://localhost:8080` unless `server.port` or context path has been changed. Send requests in an environment without Security/filters outside the example to observe the callback sequence.

### 7.4. Successful Request: Filter + Interceptor + AOP, No Error Advice

```bash
curl -i 'http://localhost:8080/api/greet?name=Lan'
```

The response contains:
- HTTP status **200 OK**.
- Header `X-Filter: seen`.
- Header `X-Interceptor: seen`.
- JSON body (exact values; header order is not fixed):

```json
{"message":"Hello, Lan"}
```

For a single synchronous request, console logs follow this typical sequence:

```text
FILTER before
INTERCEPTOR preHandle
AOP before
SERVICE greet
AOP after
INTERCEPTOR postHandle
INTERCEPTOR afterCompletion
FILTER after
```

There is no `ADVICE exceptionHandler` because no exception occurred. If outer filters/container logging are present, the output may include additional lines not shown in the snippet.

### 7.5. Error Request: ControllerAdvice Converts Exception to 400

```bash
curl -i 'http://localhost:8080/api/greet?name=bad'
```

The response contains HTTP status **400 Bad Request**, both headers `X-Filter: seen` and `X-Interceptor: seen`, and body:

```json
{"error":"name invalid"}
```

Typical main log sequence:

```text
FILTER before
INTERCEPTOR preHandle
AOP before
SERVICE greet
AOP after
ADVICE exceptionHandler
INTERCEPTOR afterCompletion
FILTER after
```

`INTERCEPTOR postHandle` typically **does not appear** because the controller throws an exception before completing the handler successfully, after which the MVC error resolver produces the response. `afterCompletion` remains the right cleanup place for interceptors that succeeded in `preHandle`.

### 7.6. Request Outside /api/**

```bash
curl -i http://localhost:8080/unknown
```

The Filter is registered on the application's default URL scope, so it can run. The Interceptor is mapped only to `/api/**`, so `/unknown` cannot be used to prove the Interceptor ran. The exact 404 result depends on current Spring MVC static resources/error handling; the example `@RestControllerAdvice` handles only `IllegalArgumentException` and will not generate a body for every 404.

## 8. Testing with MockMvc

To automatically verify that the Filter and Interceptor add headers, ControllerAdvice maps errors to 400, and the service/AOP is still used during processing, add the `spring-boot-starter-test` dependency and the file `src/test/java/com/example/demo/PipelineTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PipelineTest {

    @Autowired
    MockMvc mvc;

    @Test
    void successfulRequestTraversesFilterAndInterceptor()
            throws Exception {

        mvc.perform(get("/api/greet")
                        .param("name", "Lan"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Filter", "seen"))
                .andExpect(header().string("X-Interceptor", "seen"))
                .andExpect(jsonPath("$.message")
                        .value("Hello, Lan"));
    }

    @Test
    void controllerAdviceMapsServiceErrorTo400()
            throws Exception {

        mvc.perform(get("/api/greet")
                        .param("name", "bad"))
                .andExpect(status().isBadRequest())
                .andExpect(header().string("X-Filter", "seen"))
                .andExpect(header().string("X-Interceptor", "seen"))
                .andExpect(jsonPath("$.error")
                        .value("name invalid"));
    }
}
```

Run:

```bash
# macOS/Linux
./mvnw test

# Windows
mvnw.cmd test
```

**Limitation of the test above:** these assertions verify the headers and responses, but **do not directly prove that the AOP advice ran**. To verify AOP independently, you can inject the service bean into the test, use `AopUtils.isAopProxy(service)`, and use a controlled mock/spy or metric counter; do not conclude from the response body that the aspect was invoked. Logs can also be inspected in a test environment if needed, though assertions on metrics/test doubles are less brittle.

`@SpringBootTest` loads the application context; `@AutoConfigureMockMvc` configures MockMvc and filters under appropriate configuration. If Spring Security is added, auth/CSRF must be tested according to policy; this example does not enable Security.

## 9. Which Scenario Calls for Which Mechanism?

| Goal | Preferred Mechanism | Why |
| --- | --- | --- |
| Set trace ID before any HTTP endpoint | **Servlet Filter** | Present before DispatcherServlet; easy to use request/response wrappers |
| Standardize app-wide security headers | **Security Filter/Servlet Filter** | Early policy before body/handler execution |
| HTTP authentication/authorization | **Spring Security filter chain** (and method security when needed) | Consistent and early security policy |
| Know which controller method and annotations matched | **HandlerInterceptor** | Provides `handler instanceof HandlerMethod` |
| Measure MVC handler processing time | **HandlerInterceptor** | Has preHandle/afterCompletion; excludes full filter chain |
| Measure service method duration including non-HTTP calls | **Spring AOP** | Observes service bean invocations |
| Transactions on service methods | **Spring transaction abstraction / proxy AOP** | A business-layer concern, not an HTTP request concern |
| Convert domain exceptions to unified error JSON | **@RestControllerAdvice + @ExceptionHandler** | Right layer for HTTP error representation |
| Add shared model attributes for HTML controllers | **@ControllerAdvice @ModelAttribute** | Centralizes model setup |
| Constrain form binding/formatting | **@ControllerAdvice @InitBinder** | Hooks into MVC binding |
| Intervene on response body before message converter | **ResponseBodyAdvice** | Exact serialization point |
| Block unsuitable requests using handler-specific metadata | **HandlerInterceptor** for extra metadata, **not replacing security** | Runs after HandlerMapping |
| Handle errors thrown by Filters outside MVC | **Filter/security-specific error strategy** | MVC advice does not see those exceptions by default |

**You do not have to pick just one:** a production app often uses Spring Security filters, a custom trace filter, MVC interceptors for correlation metadata, AOP for service transactions, and `@RestControllerAdvice` for errors simultaneously. The key is keeping responsibilities separated and avoiding logging/writing bodies/validating the same thing across multiple layers.

## 10. Security: Why Interceptors Do Not Replace Spring Security

Spring Framework warns that `HandlerInterceptor` may be unsuitable as a security layer due to discrepancies between interceptor path patterns and annotation/controller mappings. For instance, an interceptor may match `/admin/**`, yet MVC mappings, forwards, dispatcher types, and controller method selection can be more complex. Authorization is a property that must apply **accurately and consistently** to every entry path and cannot rely on simple string path-matching assumptions.

The right approach:
- Use Spring Security `SecurityFilterChain`, `authorizeHttpRequests(...)`, authentication providers, and CSRF/session policies as needed.
- Apply **method security** on sensitive business methods when required by the domain (e.g., `@PreAuthorize` with proper configuration).
- Verify ownership/tenant in the service layer using the authenticated identity.
- Use HandlerInterceptor only for supplementary checks that are not the sole security barrier.

**Note:** A hand-written Servlet Filter is not automatically as secure as Spring Security either. Spring Security provides an entire model of authentication, authorization, error handling, exception translation, and lifecycle. Simply checking a client-supplied `request.getHeader("X-Role")` inside a Filter still **does not make it trustworthy authentication**.

## 11. Async and ERROR Dispatch: Advanced Branches Not to Overlook

### 11.1. Servlet Filters and Dispatcher Types

Filter registration can be configured for dispatcher types `REQUEST`, `ASYNC`, `ERROR`, `FORWARD`, and `INCLUDE`. A Filter does not necessarily run on every dispatcher; behavior depends on container/Boot registration.

`OncePerRequestFilter` provides hooks:
- `shouldNotFilter(HttpServletRequest)` to skip inapplicable requests.
- `shouldNotFilterAsyncDispatch()` to opt into or avoid async dispatches.
- `shouldNotFilterErrorDispatch()` to choose logic around error dispatches.

When using ThreadLocal or MDC:
- Set context before `chain.doFilter`.
- Clean up in `finally` on the current dispatch/thread.
- With async, do not assume ThreadLocal automatically transfers to another worker thread; configure explicit propagation.
- Do not log tokens/cookies/passwords or full raw request bodies without a data protection policy.

### 11.2. HandlerInterceptor and Async MVC

If a handler starts async processing (e.g., `Callable`, `DeferredResult`), Spring MVC may **not** initially invoke `postHandle` / `afterCompletion` when the handler switches to async. Instead, `AsyncHandlerInterceptor.afterConcurrentHandlingStarted(...)` provides a callback when the request transitions to concurrent handling; after the async dispatch to complete, the interceptor chain may run again for that dispatch cycle.

Therefore:
- Do not compute total async duration from a single `preHandle`/`postHandle` pair without understanding the lifecycle.
- Clean up ThreadLocal properly across callbacks and threads, using async-aware tracing when needed.
- Do not claim “Filter runs strictly once per whole request, Interceptor runs strictly once” across all async scenarios.

### 11.3. Exceptions in a Filter Before DispatcherServlet

If a filter throws an exception before `chain.doFilter`, `@RestControllerAdvice` usually cannot catch it because MVC has not taken control yet. If an exception originates **inside** a controller/service and reaches the MVC exception resolver, advice can handle it. Avoid writing an error body in a Filter after the response is committed; maintain a layer-appropriate exception handling policy.

### 11.4. Committed Responses

Every mechanism at different stages must account for `HttpServletResponse.isCommitted()`. Specifically:
- A Filter early in the chain can usually set headers first.
- Interceptor `preHandle` is usually still in time to set headers.
- Interceptor `postHandle` may be too late for `@ResponseBody` JSON.
- Service-layer AOP should not write directly to the Servlet response unless the design genuinely requires it; services should return results or throw domain exceptions.
- `ResponseBodyAdvice` runs in Spring MVC's body-handling path and is better suited for intercepting converter output.

## 12. Performance and Measuring Latency at the Right Layer

An app has three distinct latency measurements:

1. **Server-side HTTP end-to-end**: measured in a Filter, typically including downstream servlet filters/`DispatcherServlet` **behind it**, plus wait/sync time within the dispatch scope. For full async end-to-end timing, an async-aware mechanism is needed, not just a single `doFilter` call.
2. **MVC handler processing**: measured in an Interceptor, covering handler/controller logic after `preHandle` and MVC rendering/cleanup steps per callback.
3. **Service method latency**: measured in AOP, covering only method calls matching the pointcut through the proxy.

If `GET /api/orders` takes 250 ms while the service takes only 30 ms, the difference may lie in security, parameter conversion, network I/O, JSON serialization, view rendering, or thread scheduling. Do not use AOP service metrics to conclude whether overall HTTP responses are fast or slow.

For larger apps, consider Micrometer Observation/tracing integrated with Spring Boot rather than writing countless manual Filters/Aspects. Avoid metric tags containing user IDs, raw URLs with dynamic values, exception messages, or tokens due to cardinality and sensitive data concerns.

## 13. Common Pitfalls and Remedies

| Issue | Cause | Fix |
| --- | --- | --- |
| Filter does not run on expected endpoint | Wrong URL pattern or dispatcher type registration | Check `FilterRegistrationBean`/container mapping |
| Filter runs twice | Duplicate bean + registration, another dispatch, or nesting | Check registrations and `OncePerRequestFilter` logic |
| Interceptor does not run | Not registered via MVC config, path pattern mismatch, or no matching HandlerMapping | Check `addInterceptors`/handler mapping |
| `preHandle=false` but client gets empty response | Chain stopped without setting status/body | Write appropriate HTTP response before returning false |
| `postHandle` does not run on error | Handler threw exception and routed to resolver | Clean up in `afterCompletion`, handle error body in advice |
| Header set in `postHandle` is missing | REST converter already wrote/committed body | Set in Filter/preHandle/ResponseEntity/ResponseBodyAdvice |
| `afterCompletion(ex)` is null despite client receiving 4xx | Exception was already handled by resolver | Rely on appropriate status/metrics/error handler |
| AOP `@Around` does not run | Missing AOP starter, wrong pointcut, call bypasses proxy | Check bean/proxy/pointcut |
| `@Transactional` on internal method does not work | Self-invocation `this.inner()` bypasses proxy | Extract to another service or redesign proxy boundary |
| Advice does not catch filter error | Error occurred outside MVC | Handle at filter/security layer |
| App startup reports ambiguous exception handlers | Two `@ExceptionHandler` methods have overlapping mappings | Remove or intentionally adjust mappings |
| Exception turns into 200 | Error handler returned body without setting status | Use `ResponseEntity.status(...)` or `ProblemDetail` |
| Logs for same request lack correlation | Trace context not preserved across async/thread switch | Use proper tracing/MDC propagation and cleanup |
| Interceptor used for security gets bypassed | Handler mapping/path pattern mismatch | Use Spring Security FilterChain |
| ControllerAdvice affects unintended endpoints | Unscoped advice or generic catch-all | Use selectors and narrow error types |
| Filter overwrites controller response body | Improperly writing/flushing before or after `chain.doFilter` | Manage response wrappers and commit state carefully |

## 14. Code Review Checklist

Before adding cross-cutting logic, ask these questions:

1. Do you need the HTTP request/response **before MVC**, or only the matched handler method?
2. If a request does not enter MVC (404, static, security rejection), must the logic still run?
3. Does the logic need to run when the service is called from a scheduled task/message consumer, or only over HTTP?
4. Are you managing exceptions/status/body yourself, or do you need a unified error policy for REST controllers?
5. With an interceptor, do `preHandle`, `postHandle`, and `afterCompletion` behave properly when the handler throws, returns `false`, and runs async?
6. With AOP, does the bean/method go through a proxy? Are there self-invocations, final/private methods, or overly broad pointcuts?
7. Does it touch authentication/authorization? If so, are Spring Security and service-level permission checks used?
8. Is anything else already adding the header, logging the trace ID, handling the same exception, or modifying the body? Is there **double logging/double writing**?
9. Do tests cover successful requests, error requests, unmatched URLs, and—if async is used—the callback lifecycle?
10. Are headers set **before commit**? Are objects in the request/ThreadLocal properly cleaned up?

## 15. Self-Check Questions and Answers

**Question 1.** You want to set a correlation ID before a request enters `DispatcherServlet`, even when the request is rejected by a security filter. Which mechanism is appropriate?

**Answer:** A Servlet Filter registered with the proper URL/dispatcher order. Security-specific policies should use Spring Security infrastructure.

**Question 2.** You want to know the name of the `@GetMapping` method selected by Spring MVC. What should you use?

**Answer:** A HandlerInterceptor, checking `handler instanceof HandlerMethod` in `preHandle`.

**Question 3.** You want to log every invocation of a Spring service method, including calls from a scheduler. What should you use?

**Answer:** Spring AOP around the relevant method of the managed bean, ensuring calls go through the proxy and the pointcut is accurate.

**Question 4.** You want all REST controllers to return a consistent error JSON structure for `ProductNotFoundException`. What should you use?

**Answer:** `@RestControllerAdvice` with `@ExceptionHandler(ProductNotFoundException.class)` and an appropriate HTTP status.

**Question 5.** Does `HandlerInterceptor.postHandle` reliably add a header when a handler returns `ResponseEntity<Dto>`?

**Answer:** No. The message converter may already have written/committed the body before `postHandle`. Use `preHandle`, `ResponseEntity`, a Filter, or `ResponseBodyAdvice` depending on the goal.

**Question 6.** Why does `@Around` not run when a service calls `this.innerMethod()`?

**Answer:** A Spring AOP proxy only intercepts calls going through the proxy; self-invocation on `this` goes directly to the instance method.

**Question 7.** Does ControllerAdvice catch every exception from a Servlet Filter before `DispatcherServlet`?

**Answer:** Not by default. Exceptions outside MVC need an error strategy at the appropriate filter/security/servlet layer.

**Question 8.** Is it safe to use HandlerInterceptor for authorization instead of Spring Security?

**Answer:** Not recommended. Spring Framework warns that path/controller annotation matching can diverge; authentication/authorization belongs in security infrastructure, with business authorization in the service layer.

**Question 9.** Both Filter and Interceptor can measure request time. Will the results be identical?

**Answer:** Not necessarily. They measure different scopes, and async execution, serialization, view rendering, the filter chain, and thread scheduling affect the measurements.

## 16. Official References

- [Spring Framework 6.2 — Handler Interception](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/handlermapping-interceptor.html): `preHandle`, `postHandle`, `afterCompletion`, committed responses, and security recommendations.
- [Spring Framework 6.2 — Configure Interceptors](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/interceptors.html): `WebMvcConfigurer#addInterceptors`, mapped patterns, and `MappedInterceptor`.
- [Spring Framework 6.2 — Controller Advice](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-advice.html): `@ExceptionHandler`, `@InitBinder`, `@ModelAttribute`, and scoping.
- [Spring Framework 6.2 — Exception Handler](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-exceptionhandler.html): error handling and exception matching.
- [Spring Framework 6.2 — @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html): `@Aspect`, advice, pointcuts, and auto-proxy.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB proxies, self-invocation, and method constraints.
- [Spring Framework — OncePerRequestFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html): dispatch handling and filtering hooks.
- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): servlet filters, MVC configuration, and embedded container integration.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): `FilterChainProxy`, `SecurityFilterChain`, and web security.

**Conclusion:** these four tools do not compete over a single “before/after order.” **Servlet Filter** sits at the HTTP boundary, **HandlerInterceptor** wraps the MVC handler chain, **Spring AOP** wraps proxied bean method invocations, and **ControllerAdvice** centralizes shared MVC logic such as exception responses and binding/model customizations. Place cross-cutting logic at the layer with sufficient information and the right scope, test success/error/async paths, and never replace Spring Security with a custom interceptor.
