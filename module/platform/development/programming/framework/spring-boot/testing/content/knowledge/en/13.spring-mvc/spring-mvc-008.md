# Filters, Interceptors, Argument Resolvers, and Custom MVC Configuration in Spring Boot

> **Module:** Spring Boot – testing  
> **Group:** Spring MVC  
> **Goal:** Understand entry points, execution order, and responsibilities of Servlet `Filter`, Spring MVC `HandlerInterceptor`, `HandlerMethodArgumentResolver`, and `WebMvcConfigurer`; register them safely; and write tests proving correct behavior in both an MVC slice and the application context. Examples use Java 17+, Spring Boot 3.5, Jakarta Servlet, JUnit Jupiter, and MockMvc.

## 1. Big Picture: Which Layers Does an HTTP Request Pass Through?

In Spring MVC, not all extensions live at the same boundary. When a Servlet application receives a request, the basic processing pipeline is:

```text
HTTP client
   │
   ▼
Servlet container (Tomcat/Jetty/Undertow)
   │
   ▼
Servlet Filter chain                  ← before/after DispatcherServlet
   │
   ▼
DispatcherServlet
   │
   ├── HandlerMapping selects controller/handler
   │
   ├── HandlerInterceptor.preHandle   ← after handler is resolved
   │       ├── false → short-circuits handler invocation
   │       └── true  → continues
   │
   ├── HandlerAdapter
   │       ├── HandlerMethodArgumentResolver
   │       ├── Controller method
   │       └── ReturnValueHandler/HttpMessageConverter
   │
   ├── HandlerInterceptor.postHandle  ← normal synchronous success path
   │
   └── HandlerInterceptor.afterCompletion
   │
   ▼
Servlet Filter finishes code after chain.doFilter(...)
   │
   ▼
HTTP response
```

This diagram illustrates the **typical synchronous path**. With exceptions, async requests, error dispatches, static resources, or a short-circuiting Filter, certain callbacks behave differently. Do not treat it as an invariant call sequence for every request.

Four concepts:

| Component | Scope | Timing | Typical Responsibilities |
| --- | --- | --- | --- |
| **Servlet Filter** | Servlet container/filter chain, can span multiple servlets | Before and after `chain.doFilter` | Correlation IDs, encoding, request/response wrappers, CORS/security filter integration, safe logging |
| **HandlerInterceptor** | Spring MVC `HandlerMapping`, after handler lookup | `preHandle`, `postHandle`, `afterCompletion` | Checking handler-level conditions, setting request attributes, timing MVC handling |
| **HandlerMethodArgumentResolver** | Controller handler method parameters only | Right before Spring invokes the controller | Converting request/context into typed parameters like `TenantId`, `CurrentUser`, paging context |
| **WebMvcConfigurer** | Spring MVC configuration | When building MVC infrastructure | Registering interceptors, resolvers, converters, formatters, CORS, resource handlers, etc. |

**Key takeaway:** Filters operate at the Servlet layer; Interceptors operate at the MVC layer; Argument Resolvers supply **parameter values** to controllers; `WebMvcConfigurer` **registers extensions** without processing individual requests itself.

## 2. Servlet Filter: Broader Than MVC and Positioned Before DispatcherServlet

### 2.1. What Does a Filter Do?

Filters are managed by the Servlet filter chain. In a Spring Boot Servlet application, a bean implementing `jakarta.servlet.Filter` can be registered by Spring Boot with the embedded Servlet container. When a request flows through the chain:

```java
doSomethingBefore(request, response);
chain.doFilter(request, response);
doSomethingAfter(request, response);
```

This is **illustrative pseudocode**, not a standalone compilable Java class.

Appropriate use cases:

- Generating/propagating a request ID and storing it in a request attribute/header.
- Wrapping requests/responses when safely capturing or caching bodies.
- Setting and clearing MDC/tracing context in a `try/finally`.
- Cross-cutting Servlet-level configuration such as `CharacterEncodingFilter`.
- Security filters inside `SecurityFilterChain` managed by Spring Security.

**A Filter can block a request from reaching `DispatcherServlet`** by not calling `chain.doFilter`—for instance, rejecting oversized requests or missing foundational headers (if contracted). This differs from an interceptor returning `false` after `DispatcherServlet` has already matched a handler.

### 2.2. `OncePerRequestFilter` and Its Limits

Spring provides `OncePerRequestFilter` to ensure filter logic runs once per request dispatch using an internal request marker. This base class conveniently prevents duplicate execution across dispatches where the filter applies.

```java
public final class RequestIdFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {
        // Validate or generate request ID...
        chain.doFilter(request, response);
    }
}
```

This is an **abbreviated skeleton**; the complete runnable class is in Section 6.

Understand its limits accurately:

- "Once" refers to the **request dispatch** lifecycle, not a guarantee that a business action occurs only once across the system.
- `ASYNC`/`ERROR` dispatches follow separate rules; `shouldNotFilterAsyncDispatch()` and `shouldNotFilterErrorDispatch()` let you customize behavior when required.
- When wrapping streams, ensure you do not consume the request body so the controller can still read it.
- Writing response headers **after** `chain.doFilter` risks the response already being committed; set headers before continuing the chain if they must always appear.
- Filters do not automatically know which controller method will be chosen, making them unsuitable for logic tied to specific handler annotations.

### 2.3. Registering a Filter in Spring Boot

Common options:

1. Annotate the Filter with `@Component` or declare a `@Bean Filter` so Spring Boot registers it via Servlet filter bean auto-registration.
2. Use `FilterRegistrationBean<SomeFilter>` when you need explicit URL patterns, dispatcher types, ordering, enabled flags, or registration control.
3. With Spring Security, configure filters inside `SecurityFilterChain` at the right position; **avoid accidentally registering the same Filter instance twice** (both auto-registered as a Servlet Filter and added to the security chain).

Example when scoping URLs:

```java
@Bean
FilterRegistrationBean<RequestIdFilter> requestIdRegistration() {
    FilterRegistrationBean<RequestIdFilter> registration =
            new FilterRegistrationBean<>();
    registration.setFilter(new RequestIdFilter());
    registration.addUrlPatterns("/api/*");
    registration.setOrder(10);
    return registration;
}
```

This is a **standalone alternative config option**; do not add it to the Section 6 project alongside `@Bean RequestIdFilter`, because you should not register two filter paths for one responsibility. If using this pattern, import `org.springframework.boot.web.servlet.FilterRegistrationBean`, `org.springframework.context.annotation.Bean`, and `RequestIdFilter`.

**Note:** Filter URL patterns (`/api/*`) follow Servlet rules, which differ from Spring MVC interceptor patterns (`/api/**`). Never blindly apply identical pattern syntax across both APIs.

## 3. HandlerInterceptor: Lifecycle Tied to the MVC Handler

`HandlerInterceptor` is invoked by Spring MVC around the handler selected by `HandlerMapping`:

- **`preHandle(request,response,handler)`:** runs before the controller. Return `true` to continue; return `false` to stop handler execution. When returning `false`, the interceptor itself is responsible for producing an appropriate response (such as setting the status) without waiting for the controller.
- **`postHandle(request,response,handler,modelAndView)`:** runs after the handler completes normally on a synchronous path, before view rendering. For `@ResponseBody`/`@RestController`, the body may already have been written via `HttpMessageConverter` before this callback, so do not rely on `postHandle` to modify JSON bodies or headers after commit.
- **`afterCompletion(request,response,handler,exception)`:** completion callback after normal processing; useful for MVC metrics/cleanup. If this interceptor's own `preHandle` returned `false`, it **does not receive `afterCompletion` for that handler invocation** as it would after a full run. Async and error paths have separate rules.

Interceptors registered in order execute return callbacks in **reverse order**. If business logic relies on exact ordering, verify behavior with tests rather than assuming from source order.

### 3.1. When Should You Use an Interceptor?

Good fits: normalizing request-scoped metadata after mapping, timing controller execution, enforcing API-path-specific guards, or application-level routing checks that are not core authorization.

Poor fit: replacing **Spring Security authentication and authorization**. Spring documentation warns against using interceptors as the primary security layer due to path-matching differences compared to the security filter chain. In multi-tenant systems, **a self-declared header never proves tenant identity or access rights**. When tenant ID governs authorization, validate it against the authenticated principal, JWT claims, and access rules at the security/service layer. The example below **validates only header format to illustrate the mechanism**, not real multi-tenant authorization.

### 3.2. URL Matching Patterns

Inside `WebMvcConfigurer`:

```java
@Override
public void addInterceptors(InterceptorRegistry registry) {
    registry.addInterceptor(new TenantInterceptor())
            .addPathPatterns("/api/**")
            .excludePathPatterns("/api/public/**");
}
```

This snippet illustrates pattern syntax only. Spring MVC path matching depends on framework/version settings; when protecting routes, verify patterns against real endpoints and write tests for both included and excluded paths. Interceptors added via Java MVC config apply to the `HandlerMapping` configured by that MVC setup; `MappedInterceptor` beans can apply more broadly across matching handler mappings.

## 4. HandlerMethodArgumentResolver: Turning Request Context into Typed Parameters

Avoid repeating this in every controller:

```java
String tenant = request.getHeader("X-Tenant-Id");
// Validate, normalize, map to domain object...
```

With a custom `@CurrentTenant TenantId tenant`, Spring MVC can resolve the value before invoking the controller method.

The `HandlerMethodArgumentResolver` interface has two methods:

```java
boolean supportsParameter(MethodParameter parameter);

Object resolveArgument(
        MethodParameter parameter,
        ModelAndViewContainer mavContainer,
        NativeWebRequest webRequest,
        WebDataBinderFactory binderFactory)
        throws Exception;
```

This is an illustrative API signature, not a standalone source file.

- `supportsParameter` must be **narrow and exact**—for instance, matching only parameters annotated with `@CurrentTenant` and typed as `TenantId`; matching every `String` would interfere with built-in parameter binding.
- `resolveArgument` extracts the validated/normalized value from the request or security context and builds the typed domain object.
- Avoid querying a DB or remote service on every request inside a resolver unless deliberately designed; it makes binding slow, unpredictable, and hard to test.
- Resolvers supply arguments; they **do not replace business validation, security policies, or data authorization**.
- Resolvers added via `WebMvcConfigurer#addArgumentResolvers` **supplement** standard resolvers without disabling `@RequestBody`, `@RequestParam`, or `@PathVariable`.
- To alter a built-in resolver's behavior, deeper `RequestMappingHandlerAdapter` configuration may be required; do not expect a custom resolver to automatically override built-in ones.

### 4.1. Why Are Typed Values Better Than Raw Strings?

A `TenantId` record makes controller contracts explicit:

```java
public record TenantId(String value) {}

@GetMapping("/api/context")
public ContextPayload inspect(@CurrentTenant TenantId tenant,
                              HttpServletRequest request) {
    // tenant was resolved from request-scoped data.
}
```

This is an abbreviated snippet; the complete app is in Section 6. A domain wrapper like `TenantId` reduces the chance of mixing up a tenant ID with a request ID, order ID, or arbitrary strings. Still, having a `TenantId` type **does not mean the tenant's identity was authenticated**; that remains a separate responsibility.

## 5. Configuring MVC with `WebMvcConfigurer`

`WebMvcConfigurer` lets an application extend MVC behavior in Spring Boot while preserving Boot's MVC auto-configuration. Common callbacks:

| Method | Purpose |
| --- | --- |
| `addInterceptors` | Register `HandlerInterceptor`s and URL patterns |
| `addArgumentResolvers` | Add custom handler method argument resolvers |
| `addFormatters` | Converters/Formatters for request data |
| `addCorsMappings` | MVC-layer CORS policy |
| `addResourceHandlers` | Static resources and cache controls |
| `addViewControllers` | Simple mappings to views |
| `extendMessageConverters` | Extend or adjust existing converters |
| `configureMessageConverters` | Configure converters; may replace defaults depending on mechanism |
| `configureAsyncSupport` | MVC async configuration, timeouts, executor |
| `configurePathMatch` | Customize path matching |

**Important:** in Spring Boot, a single `@Configuration` implementing `WebMvcConfigurer` is usually all you need. **Do not add `@EnableWebMvc` unless you intentionally want full manual control over MVC configuration**, as it alters how Boot's MVC auto-configuration applies. Many broken JSON, static resource, or custom converter setups stem from adding `@EnableWebMvc` merely to register one interceptor.

Distinctions:

- `@Configuration + WebMvcConfigurer`: extends/customizes on top of Boot's MVC infrastructure.
- `@EnableWebMvc`: use only when intentionally taking over all Spring MVC configuration.
- `@Import(MvcSupportConfiguration.class)` in a slice test: guarantees the custom MVC config under test is loaded, even when a slice skips arbitrary `@Configuration` classes.
- `@AutoConfigureMockMvc`: supplies `MockMvc` under `@SpringBootTest(MOCK)` with Spring MVC; **does not** open an embedded HTTP listener.

## 6. Runnable Maven Project: Filter → Interceptor → Resolver → Controller

The complete example uses **Java 17, Spring Boot 3.5.0, Spring MVC/Servlet**, requiring no database, cloud account, or external services. The API returns JSON containing the tenant and request ID, allowing tests for every extension point.

### 6.1. API Contract

Endpoint: `GET /api/context`.

- The request must include header `X-Tenant-Id` matching `[a-z][a-z0-9-]{2,15}` (e.g., `tenant-a` is valid).
- `TenantInterceptor` checks the **format** and stores the checked value in request attribute `validatedTenant`. Missing/invalid format → **400 Bad Request**, controller is never called.
- `TenantArgumentResolver` reads `validatedTenant` and creates a `TenantId` for the `@CurrentTenant` parameter.
- `RequestIdFilter` accepts `X-Request-Id` when matching `[A-Za-z0-9-]{1,64}`. If missing or invalid → generates a new UUID. The filter sets request attribute `requestId` and response header `X-Request-Id`.
- `InspectionController` calls `InspectionService` to build a greeting; the JSON response contains `tenant`, `requestId`, and `greeting`.
- The interceptor sets response header `X-Tenant-Checked=true` inside `preHandle`.

Valid request example:

```http
GET /api/context HTTP/1.1
Host: localhost:8080
X-Tenant-Id: tenant-a
X-Request-Id: req-42
```

Expected response from the **real application**:

```http
HTTP/1.1 200 OK
X-Request-Id: req-42
X-Tenant-Checked: true
Content-Type: application/json

{"tenant":"tenant-a","requestId":"req-42","greeting":"Hello, tenant-a"}
```

This **illustrates the response contract**, without claiming exact HTTP header/JSON key ordering or omitting other default headers. When tenant is missing, expect status 400; `sendError` bodies can vary across MockMvc/server modes, so tests avoid locking onto fixed error JSON.

### 6.2. Directory Structure

```text
mvc-extension-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/mvcext/
    │   │   ├── MvcExtensionApplication.java
    │   │   ├── TenantId.java
    │   │   ├── CurrentTenant.java
    │   │   ├── RequestIdFilter.java
    │   │   ├── TenantInterceptor.java
    │   │   ├── TenantArgumentResolver.java
    │   │   ├── MvcSupportConfiguration.java
    │   │   ├── InspectionService.java
    │   │   ├── ContextPayload.java
    │   │   └── InspectionController.java
    │   └── resources/
    │       └── application.yml
    └── test/
        ├── java/com/example/mvcext/
        │   ├── InspectionMvcSliceTest.java
        │   ├── InspectionFullContextTest.java
        │   └── InspectionHttpServerTest.java
        └── resources/
            └── application-test.yml
```

Place each public type in its matching file under package `com.example.mvcext`. Filter/interceptor/resolver configuration is declared **in a single place** to prevent duplicate registration.

### 6.3. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mvc-extension-lab</artifactId>
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
```

`spring-boot-starter-web` provides Spring MVC and the Jakarta Servlet API via an embedded server (Tomcat by default for the standard starter). `spring-boot-starter-test` brings JUnit Jupiter, MockMvc, Mockito, and Spring Test. In MockMvc tests, **no** embedded HTTP socket listens; the `RANDOM_PORT` test opens a real server.

### 6.4. Application Entrypoint, Records, and Annotation

```java
// src/main/java/com/example/mvcext/MvcExtensionApplication.java
package com.example.mvcext;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcExtensionApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcExtensionApplication.class, args);
    }
}
```

```java
// src/main/java/com/example/mvcext/TenantId.java
package com.example.mvcext;

public record TenantId(String value) {}
```

```java
// src/main/java/com/example/mvcext/CurrentTenant.java
package com.example.mvcext;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
public @interface CurrentTenant {}
```

```java
// src/main/java/com/example/mvcext/ContextPayload.java
package com.example.mvcext;

public record ContextPayload(
        String tenant, String requestId, String greeting) {}
```

`@CurrentTenant` targets method parameters only and uses runtime retention so `HandlerMethodArgumentResolver` can inspect it. `TenantId` and `ContextPayload` are Java records, giving deterministic JSON serialization and Mockito equality.

### 6.5. Filter Generating Request ID

```java
// src/main/java/com/example/mvcext/RequestIdFilter.java
package com.example.mvcext;

import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public final class RequestIdFilter extends OncePerRequestFilter {

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9-]{1,64}");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String incoming = request.getHeader("X-Request-Id");

        String id = incoming != null
                && SAFE_ID.matcher(incoming).matches()
                ? incoming
                : UUID.randomUUID().toString();

        request.setAttribute("requestId", id);
        response.setHeader("X-Request-Id", id);

        chain.doFilter(request, response);
    }
}
```

The filter sets the response header **before** continuing the chain so downstream controller/exception handling sees the correlation ID. When `X-Request-Id` is absent, the random UUID means tests **must not hardcode an expected ID**; instead verify valid UUID format and consistency between header and JSON.

The regex here is a basic guard against malformed log/header values; real systems should review length, standard formats, trust in client-supplied trace IDs, log-injection defense, and distributed tracing integration. **A Request ID is not an access token.**

### 6.6. Interceptor Validating the Tenant Header and Blocking Before the Controller

```java
// src/main/java/com/example/mvcext/TenantInterceptor.java
package com.example.mvcext;

import java.io.IOException;
import java.util.regex.Pattern;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.servlet.HandlerInterceptor;

public final class TenantInterceptor implements HandlerInterceptor {

    private static final Pattern TENANT =
            Pattern.compile("[a-z][a-z0-9-]{2,15}");

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) throws IOException {

        String rawTenant = request.getHeader("X-Tenant-Id");

        if (rawTenant == null
                || !TENANT.matcher(rawTenant).matches()) {
            response.sendError(HttpServletResponse.SC_BAD_REQUEST,
                    "Invalid X-Tenant-Id");
            return false;
        }

        request.setAttribute("validatedTenant", rawTenant);
        response.setHeader("X-Tenant-Checked", "true");
        return true;
    }
}
```

Because `preHandle` returns `false` when the tenant header is missing or invalid, MVC skips both the controller and `TenantArgumentResolver` on the error path. **This is format validation only**; it is insufficient to protect multi-tenant data. For authorization, verify the tenant against an authenticated principal at the security/business layer.

`TenantInterceptor` is not annotated `@Component` in this project. It is registered by `MvcSupportConfiguration`, avoiding two competing registration paths.

### 6.7. Resolver Reading the Validated Value

```java
// src/main/java/com/example/mvcext/TenantArgumentResolver.java
package com.example.mvcext;

import org.springframework.core.MethodParameter;
import org.springframework.web.bind.support.WebDataBinderFactory;
import org.springframework.web.context.request.NativeWebRequest;
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.method.support.ModelAndViewContainer;

public final class TenantArgumentResolver
        implements HandlerMethodArgumentResolver {

    @Override
    public boolean supportsParameter(MethodParameter parameter) {
        return parameter.hasParameterAnnotation(CurrentTenant.class)
                && TenantId.class.equals(parameter.getParameterType());
    }

    @Override
    public Object resolveArgument(
            MethodParameter parameter,
            ModelAndViewContainer mavContainer,
            NativeWebRequest webRequest,
            WebDataBinderFactory binderFactory) {

        Object value = webRequest.getAttribute(
                "validatedTenant", RequestAttributes.SCOPE_REQUEST);

        if (!(value instanceof String tenant)) {
            throw new IllegalStateException(
                    "TenantInterceptor did not validate tenant");
        }

        return new TenantId(tenant);
    }
}
```

The resolver keeps `supportsParameter` **narrow**: it ignores ordinary `String` parameters or `TenantId` parameters without `@CurrentTenant`. It reads only the **request attribute set by the interceptor** rather than trusting raw headers directly. If configuration omits the interceptor, the resolver fails loudly instead of silently passing an empty tenant.

In general, `resolveArgument` runs for requests that match an appropriate handler; it **does not process every HTTP request** and never takes on a Filter's responsibilities.

### 6.8. Explicit MVC Configuration Without `@EnableWebMvc`

```java
// src/main/java/com/example/mvcext/MvcSupportConfiguration.java
package com.example.mvcext;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcSupportConfiguration implements WebMvcConfigurer {

    private final TenantInterceptor tenantInterceptor =
            new TenantInterceptor();

    private final TenantArgumentResolver tenantArgumentResolver =
            new TenantArgumentResolver();

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(tenantInterceptor)
                .addPathPatterns("/api/**");
    }

    @Override
    public void addArgumentResolvers(
            List<HandlerMethodArgumentResolver> resolvers) {
        resolvers.add(tenantArgumentResolver);
    }

    @Bean
    RequestIdFilter requestIdFilter() {
        return new RequestIdFilter();
    }
}
```

This design is **intentional**:

- `MvcSupportConfiguration` is a Spring configuration class; in a full application context it is discovered by component scanning.
- `WebMvcConfigurer#addInterceptors` registers `TenantInterceptor` for `/api/**`.
- `WebMvcConfigurer#addArgumentResolvers` adds `TenantArgumentResolver` to Spring MVC argument handling.
- `@Bean RequestIdFilter` registers the filter in the Spring context; Boot and MockMvc test auto-configuration register it in the appropriate Servlet/test filter chain.
- There is no `@EnableWebMvc`, so Boot's MVC auto-configuration remains intact.
- The interceptor and resolver are **stateless** instances held directly in the config. They do not need to be exposed as extra beans here; if they ever need injected collaborators in a real app, declare them as beans and inject via constructors cleanly.

When running `@WebMvcTest`, we add `@Import(MvcSupportConfiguration.class)` so the custom MVC configuration under test is included in the test context. Seeing this class in `src/main/java` is no proof the slice loads it automatically.

### 6.9. Service and Controller Using the Typed Argument

```java
// src/main/java/com/example/mvcext/InspectionService.java
package com.example.mvcext;

import org.springframework.stereotype.Service;

@Service
public class InspectionService {
    public String greet(TenantId tenant) {
        return "Hello, " + tenant.value();
    }
}
```

```java
// src/main/java/com/example/mvcext/InspectionController.java
package com.example.mvcext;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class InspectionController {

    private final InspectionService service;

    public InspectionController(InspectionService service) {
        this.service = service;
    }

    @GetMapping("/context")
    public ContextPayload inspect(
            @CurrentTenant TenantId tenant,
            HttpServletRequest request) {

        String requestId =
                (String) request.getAttribute("requestId");

        return new ContextPayload(
                tenant.value(),
                requestId,
                service.greet(tenant));
    }
}
```

The controller never calls `request.getHeader("X-Tenant-Id")`; it receives `TenantId` created by the resolver. The service uses the tenant solely as data for an illustrative greeting. In production, **never treat a tenant taken from a client header as authorization to access data**, even after regex validation.

### 6.10. Isolated Test Configuration

```yaml
# src/main/resources/application.yml
spring:
  application:
    name: mvc-extension-lab
```

```yaml
# src/test/resources/application-test.yml
app:
  test-marker: isolated
```

Spring-context tests use `@ActiveProfiles("test")`. The `app.test-marker=isolated` property only proves test config was loaded; it does not by itself isolate outbound connections. The sample project has no database or remote clients, so no credentials are needed.

## 7. Testing with `@WebMvcTest`: Mock Service, Custom MVC Runs for Real

`@WebMvcTest(InspectionController.class)` loads only the MVC slice and auto-configures `MockMvc`. `InspectionService` is not loaded automatically since it is an out-of-slice `@Service`, so we use `@MockitoBean`. Custom MVC configuration is brought in via `@Import`.

```java
// src/test/java/com/example/mvcext/InspectionMvcSliceTest.java
package com.example.mvcext;

import java.util.UUID;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(InspectionController.class)
@Import(MvcSupportConfiguration.class)
@ActiveProfiles("test")
class InspectionMvcSliceTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @MockitoBean
    InspectionService service;

    @Test
    void runsFilterInterceptorAndResolverBeforeController()
            throws Exception {
        TenantId tenant = new TenantId("tenant-a");
        when(service.greet(tenant)).thenReturn("stub-tenant-a");

        mvc.perform(get("/api/context")
                        .header("X-Tenant-Id", "tenant-a")
                        .header("X-Request-Id", "req-42"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Request-Id", "req-42"))
                .andExpect(header().string("X-Tenant-Checked", "true"))
                .andExpect(jsonPath("$.tenant").value("tenant-a"))
                .andExpect(jsonPath("$.requestId").value("req-42"))
                .andExpect(jsonPath("$.greeting").value("stub-tenant-a"));

        verify(service).greet(tenant);
    }

    @Test
    void missingTenantStopsBeforeController() throws Exception {
        mvc.perform(get("/api/context")
                        .header("X-Request-Id", "req-43"))
                .andExpect(status().isBadRequest())
                .andExpect(header().string("X-Request-Id", "req-43"));

        verifyNoInteractions(service);
    }

    @Test
    void malformedTenantIsRejected() throws Exception {
        mvc.perform(get("/api/context")
                        .header("X-Tenant-Id", "tenant_invalid")
                        .header("X-Request-Id", "req-44"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void missingRequestIdGeneratesUuidAndEchoesIt() throws Exception {
        TenantId tenant = new TenantId("tenant-a");
        when(service.greet(tenant)).thenReturn("stub-tenant-a");

        MvcResult result = mvc.perform(get("/api/context")
                        .header("X-Tenant-Id", "tenant-a"))
                .andExpect(status().isOk())
                .andReturn();

        String requestId =
                result.getResponse().getHeader("X-Request-Id");

        assertNotNull(requestId);
        assertEquals(requestId,
                UUID.fromString(requestId).toString());

        String body = result.getResponse().getContentAsString();
        assertEquals(requestId,
                mapper.readTree(body)
                        .path("requestId").asText());
    }
}
```

**What do these assertions protect?**

1. The happy-path test checks **three milestones**: the filter sets the request ID, the interceptor sets the checked header, and the resolver builds the `TenantId` so the mock service receives the exact argument.
2. When tenant is missing or malformed, `preHandle` returns `false`; status 400 and `verifyNoInteractions(service)` prove the controller never invoked the service.
3. When request ID is missing, the filter generates a UUID. The test **does not hardcode** a random ID; it verifies it parses as a canonical UUID string and that the JSON echoes the exact value from the response header.
4. The service here is a **Mockito mock**; the string `stub-tenant-a` deliberately differs from real output so you never mistake the slice test for testing `InspectionService`'s real business logic.
5. `@Import` brings extension configuration into test scope. If you omit `@Import` and the slice does not pick up the config automatically, header/tenant assertions turn red, revealing missing wiring.

**What the test does not prove:** that an embedded HTTP server is listening, that the servlet container handles network I/O, real production config, or tenant authorization. `MockMvc.perform` executes inside Spring MVC test infrastructure without opening a TCP socket.

## 8. `@SpringBootTest(MOCK)`: Real MVC Config and Real Business Service

To verify the integration of **real** MVC → interceptor → resolver → controller → service, do not mock the service. `@SpringBootTest` loads the application context under active conditions; in this project, both `MvcSupportConfiguration` and `InspectionService` are scanned.

```java
// src/test/java/com/example/mvcext/InspectionFullContextTest.java
package com.example.mvcext;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.Mockito.mockingDetails;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@ActiveProfiles("test")
class InspectionFullContextTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    InspectionService service;

    @Autowired
    Environment environment;

    @Test
    void appContextUsesRealServiceAndCustomMvcComponents()
            throws Exception {
        assertFalse(mockingDetails(service).isMock());
        assertEquals("isolated",
                environment.getProperty("app.test-marker"));

        mvc.perform(get("/api/context")
                        .header("X-Tenant-Id", "tenant-a")
                        .header("X-Request-Id", "req-99"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Request-Id", "req-99"))
                .andExpect(header().string("X-Tenant-Checked", "true"))
                .andExpect(jsonPath("$.tenant").value("tenant-a"))
                .andExpect(jsonPath("$.greeting")
                        .value("Hello, tenant-a"));
    }

    @Test
    void invalidTenantStillFailsInFullContext() throws Exception {
        mvc.perform(get("/api/context"))
                .andExpect(status().isBadRequest());
    }
}
```

**Comparison with the slice:**

- Same `/api/context` endpoint, same configured Filter/Interceptor/Resolver.
- The slice uses a **mock** `InspectionService` and expects `stub-tenant-a`.
- The full context uses the **real** `InspectionService` and expects `Hello, tenant-a`.
- Both use `MockMvc`, so neither starts an embedded listener. `MOCK` in `webEnvironment` does **not** mean services are Mockito mocks.
- Full contexts may initialize extra beans unrelated to the test if a real project has many dependencies; use test-only profiles, sandbox databases, and stub/fake outbound ports.

## 9. `@SpringBootTest(RANDOM_PORT)`: Also Verifying the Real HTTP Server

If your goal includes verifying Filter registration inside the embedded Servlet container and real HTTP transport, start the server on a random port and use Java 17's `HttpClient` over loopback:

```java
// src/test/java/com/example/mvcext/InspectionHttpServerTest.java
package com.example.mvcext;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class InspectionHttpServerTest {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    @Test
    void httpRequestPassesThroughRealServletContainer()
            throws Exception {

        assertTrue(port > 0);

        URI uri = URI.create(
                "http://127.0.0.1:" + port + "/api/context");

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest request = HttpRequest.newBuilder(uri)
                .header("X-Tenant-Id", "tenant-a")
                .header("X-Request-Id", "req-net-1")
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("req-net-1",
                response.headers()
                        .firstValue("X-Request-Id").orElseThrow());
        assertEquals("true",
                response.headers()
                        .firstValue("X-Tenant-Checked").orElseThrow());

        JsonNode body = mapper.readTree(response.body());
        assertEquals("tenant-a", body.path("tenant").asText());
        assertEquals("req-net-1", body.path("requestId").asText());
        assertEquals("Hello, tenant-a",
                body.path("greeting").asText());
    }
}
```

The difference is that `HttpClient` **actually opens a TCP connection** to the embedded server, whereas `MockMvc` constructs internal mock Servlet request/response objects. Both verify custom MVC logic; the HTTP test additionally covers embedded server startup and Filter registration inside the Servlet container.

**Never hardcode `localhost:8080` in `RANDOM_PORT` tests.** The port is allocated by the OS and is known only after context startup via `@LocalServerPort`.

### 9.1. Why Verify Filters at Two Levels?

- `MockMvc` can load Filter beans from the application context when auto-configured with `addFilters=true` (default), but it **does not** verify all real Servlet container mapping/dispatcher-type/ordering behavior.
- An HTTP server test catches filter registration bugs, URL pattern mismatches, and real container behavior.
- If production sits behind a reverse proxy or API gateway, loopback tests still do not prove proxy/TLS/ingress behavior. Add E2E/staging tests based on risk.

## 10. Running the Project and Verifying Results

Use JDK 17+ and Maven with dependency resolution enabled. From the directory containing `pom.xml`:

```bash
java -version
mvn -version

mvn test

mvn -Dtest=InspectionMvcSliceTest test
mvn -Dtest=InspectionFullContextTest test
mvn -Dtest=InspectionHttpServerTest test
```

**The sample test suite has 7 `@Test` methods**: `InspectionMvcSliceTest` has 4, `InspectionFullContextTest` has 2, `InspectionHttpServerTest` has 1, totaling **4 + 2 + 1 = 7**. If you add more tests, invocation counts will change.

Expected result is that all assertions pass; Maven prints `BUILD SUCCESS` when everything passes. Spring logs, build times, test ordering, and `RANDOM_PORT` ports vary across machines, so there is **no fixed stdout**.

Run the real application with:

```bash
mvn spring-boot:run
```

In another terminal, once the server starts on the default port without overrides:

```bash
curl -i \
  -H "X-Tenant-Id: tenant-a" \
  -H "X-Request-Id: req-42" \
  http://localhost:8080/api/context
```

Expect status 200, the two response headers from the contract, and a JSON body with tenant, request ID, and greeting. `curl` targets the **running application**; `mvn test` in MockMvc mode needs no listening server. If port 8080 is already taken by another process, pick another port via runtime configuration.

## 11. Choosing Between Filter, Interceptor, and Resolver for Common Needs

| Requirement | Where Does It Belong? | Why |
| --- | --- | --- |
| Assign a correlation ID to every Servlet request | Filter | Runs before `DispatcherServlet`, including paths that never reach a controller |
| Validate header format only for `/api/**` | Interceptor (as shown) or scoped filter | Tied to API handlers; scope must be bounded |
| Inject `TenantId` into `@CurrentTenant` parameters | `HandlerMethodArgumentResolver` | Proper responsibility is argument binding |
| Configure interceptor patterns and resolvers | `WebMvcConfigurer` | Centralizes MVC configuration |
| Authorization/roles/tenant permissions | Spring Security + service policy | Never trust raw headers and interceptor path matching as a security boundary |
| Modify request body before controller | Filter + controlled wrapper, or `HttpMessageConverter`/`RequestBodyAdvice` | Depends on target and layer |
| Customize JSON serialization/deserialization | Jackson module, `HttpMessageConverter` config | Do not abuse interceptors to rewrite JSON strings |
| Format/parse dates or domain IDs from query/path | `Converter`/`Formatter`, `@InitBinder` per case | Built-in MVC binding pipeline |
| Produce standardized error JSON | `@RestControllerAdvice`/`@ExceptionHandler` | Translates exceptions into HTTP error contracts |
| Control CORS | Spring MVC CORS and/or Security CORS config | Avoid writing inconsistent custom CORS responses in interceptors |
| End-to-end Servlet logging/timing | Filter + `try/finally`/observability | Wraps before/after MVC and guarantees cleanup |
| Handler-specific logging/timing | `HandlerInterceptor` | Knows which handler and annotations were matched |

**Not every use case needs a custom implementation.** Correlation IDs can be handled by Micrometer/OpenTelemetry instead of a custom Filter. In systems with existing observability/tracing, prefer official integrations over inventing a conflicting ID scheme.

## 12. Specific Pitfalls in Design and Testing

### 12.1. `@WebMvcTest` Might Not Automatically Load Custom Config as Expected

A regular `@Configuration` in the application is not guaranteed to appear in the MVC slice. Consequently, a controller test might fail to resolve `@CurrentTenant` or miss an interceptor. **Solution in the sample project:** declare `@Import(MvcSupportConfiguration.class)` on the slice test.

By contrast, `@SpringBootTest` loads broader app config and normally scans that class. Never guess the bean graph from annotation names alone; verify endpoint behavior or the bean registry.

### 12.2. Forgetting `@AutoConfigureMockMvc` in `@SpringBootTest`

`@SpringBootTest` builds a context without automatically providing an injectable `MockMvc`. For Spring MVC with `webEnvironment=MOCK`, add:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ExampleTest {
    @Autowired
    MockMvc mvc;
}
```

This snippet shows the annotations and field; it needs imports and test methods to form a complete test. `@WebMvcTest` auto-configures `MockMvc` on its own.

### 12.3. Registering a Filter Twice

For example, putting `@Component` on `RequestIdFilter` while also instantiating `new RequestIdFilter()` inside a `FilterRegistrationBean`, or adding a Filter to the Security chain while it also auto-registers as a Servlet filter. This can run header/log/filter logic twice or in unexpected order. Choose **one registration path** per responsibility and cover it with tests.

### 12.4. Using an Interceptor to Replace Spring Security

Header `X-Tenant-Id=tenant-a` does not prove the caller has permission to access `tenant-a`. Regex validation checks only **syntax**. For auth, use authenticated principals/claims, verify memberships/roles, and enforce data access at the service/repository layer. Never rely on an interceptor that might not cover every `HandlerMapping` or dispatch path for access control.

### 12.5. Expecting `afterCompletion` to Always Run

If `preHandle` returns `false`, that interceptor's completion callback does not run as on a completed handler path. With async processing, lifecycle callbacks differ (`AsyncHandlerInterceptor#afterConcurrentHandlingStarted` and subsequent dispatch). For `ThreadLocal`/MDC cleanup across all Servlet invocations, a Filter using `try/finally` with appropriate dispatcher types is easier to control, though async/error dispatches still need careful handling.

### 12.6. Assuming a Filter Always Runs for Every URL

Filter registrations have URL patterns, dispatcher types, and ordering. MVC interceptors also run only when a handler matches; errors before `HandlerMapping` or requests bypassing `DispatcherServlet` may skip them. Test all protected endpoints and paths, including unmatched routes and async/error dispatches when applicable.

### 12.7. Writing Response Headers/Body Too Late in an Interceptor

With `@RestController`, the response body may already be committed before `postHandle`. Do not rely on `postHandle` to modify serialization or headers after commit. Use `ResponseBodyAdvice`, an exception handler, or a wrapper at the appropriate layer.

### 12.8. `@EnableWebMvc` Disabling Desired Boot Configuration

`@EnableWebMvc` hands over full Spring MVC configuration control to Framework defaults, which can turn off helpful Boot MVC auto-configuration. To add Filters/Interceptors/Resolvers, `WebMvcConfigurer` is enough. If you must use `@EnableWebMvc`, manage those configurations explicitly and back them with clear integration tests.

### 12.9. Custom Resolver Matching Too Broadly

A resolver whose `supportsParameter` returns `true` for every `String` causes unintended interference. Match both a dedicated annotation **and** a specific type, such as `@CurrentTenant TenantId`. Include a test case for an ordinary endpoint using `@RequestParam String` to ensure it stays unaffected when needed.

### 12.10. Treating Raw Request Headers as Trusted Context

In the sample, the interceptor sets `validatedTenant` after regex matching. The name "validated" means only format-checked; it does **not** mean authorized. In production, if a resolver reads principals or signed claims, make that contract explicit and test mismatches/cross-tenant denials.

### 12.11. Only Counting Filter Invocations Without Checking Output

`verify(filter).doFilter(...)` can verify one invocation while the request ID is wrong, headers are missing, or the resolver reads bad data. Tests should assert **response headers, request-derived JSON, 400/200 status, and service interactions** per contract, rather than counting internal callbacks unnecessarily.

### 12.12. Over-Relying on Slice Tests for Container Behavior

`MockMvc` simulates Servlet requests/responses in-process. When you must prove `FilterRegistrationBean` URL patterns/dispatcher types inside a container, network sockets, or TLS, use `RANDOM_PORT` tests or staging environments resembling production. Never infer an active network listener from a MockMvc 200 response.

## 13. Advanced Testing: Order, Async, Error Dispatches, and Observability

### 13.1. Filter and Interceptor Ordering

When an application has multiple Filters, ordering can govern MDC, security, request wrappers, or CORS. You can use `@Order` on Filter beans or `FilterRegistrationBean#setOrder`, but **never assume** where framework filters sit without inspecting the actual filter chain config.

In Spring Security, the security filter chain has its own internal ordering behind `DelegatingFilterProxy` at the Servlet layer. A custom Servlet Filter outside the security chain behaves differently from a custom Spring Security Filter inside the chain. Tests should verify effects at the intended boundary, not just order numbers.

### 13.2. Verifying Callback Lifecycle

When verifying exact callback ordering, you can introduce a `TraceRecorder` capturing milestones:

```text
filter.before
interceptor.preHandle
resolver.resolveArgument
controller.handle
interceptor.postHandle
interceptor.afterCompletion
filter.after
```

This is the **expected order for a properly instrumented synchronous MVC success case**, not stdout of the sample project. Use a per-request/correlation-ID recording fake rather than a global static list when tests run in parallel. Avoid coupling tests to internal callbacks that are not part of the contract under protection.

### 13.3. `preHandle=false` and Exceptions

If an interceptor sets status 400 and returns `false`, the controller and resolver never run. When a controller throws an exception, `postHandle` normally does not run; `afterCompletion` runs after dispatcher cleanup under normal lifecycle rules. For stable JSON error mapping, use `@ControllerAdvice` or `@RestControllerAdvice` instead of trying to write error bodies from an interceptor.

In the sample project, assert only status 400 for `sendError` instead of tying tests to container/framework-specific error JSON.

### 13.4. Async Requests

`Callable`, `DeferredResult`, or async processing can trigger additional dispatches:

- `OncePerRequestFilter` manages `ASYNC`/`ERROR` dispatches and requires attention to filter registration.
- Interceptors can receive `afterConcurrentHandlingStarted` by implementing `AsyncHandlerInterceptor`, followed by callbacks on subsequent dispatches.
- `MockMvc` async tests may require `asyncDispatch` after `asyncStarted`.
- State held in `ThreadLocal`/MDC must be cleared/propagated properly across threads; request attributes work well for request-scoped data shared across threads.

Never test async behavior solely with fixed `Thread.sleep` calls. Use Spring's completion/lifecycle testing primitives.

### 13.5. CORS, Converters, and Resource Handlers in the Same Config

`WebMvcConfigurer` also provides:

```java
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/api/**")
            .allowedOrigins("https://frontend.example.test")
            .allowedMethods("GET");
}
```

This is an illustrative snippet (requiring `CorsRegistry` import); **do not add it to the runnable project unless CORS is required**. If Spring Security is present, integrate with Security's CORS config so preflight requests succeed.

For Jackson JSON, prefer Spring Boot-managed modules/converters instead of replacing the entire `HttpMessageConverter` list and losing defaults. For static assets, configure `addResourceHandlers` deliberately and test real URLs/resources. Each callback is an independent extension point—avoid cramming unrelated request logic into one giant `WebMvcConfigurer`.

## 14. Common Pitfalls When Testing Custom MVC

| Symptom | Possible Cause | Verification and Fix |
| --- | --- | --- |
| `@CurrentTenant TenantId` is not resolved | Resolver not added via `addArgumentResolvers`, or config omitted from slice | `@Import` config into `@WebMvcTest`, assert tenant in JSON |
| Missing tenant still returns 200 | Interceptor unregistered or URL pattern mismatch | Assert 400 status and verify service not called |
| Request ID missing from header | Filter bean unregistered or MockMvc skips filters | Ensure `@Bean Filter`, `@AutoConfigureMockMvc(addFilters=true)` as needed |
| Controller returns 200 in slice but fails at runtime | Service was `@MockitoBean` | Add unit/full-context tests for the real service |
| Filter runs twice | Multiple registration paths or async/error dispatches | Inspect bean registrations, dispatcher types, test behavior |
| HTTP client calling 8080 under `@SpringBootTest(MOCK)` gets connection refused | `MOCK` opens no listener | Use MockMvc or switch to `RANDOM_PORT`/`@LocalServerPort` |
| Enabling `@EnableWebMvc` breaks JSON/CORS/resource mappings | Boot MVC auto-config bypassed | Remove annotation if extending via `WebMvcConfigurer` suffices |
| Security returns 401/403 before interceptor | Security filter chain runs first | Configure Spring Security test users/CSRF per contract |
| Arbitrary header contains newlines or oversized text | Missing input validation | Validate against allowlist/size; guard against log injection |
| `afterCompletion` skipped when `preHandle=false` | Lifecycle short-circuited | Place cleanup in the right lifecycle hook; don't rely on that callback |
| Flaky test from generated UUID | Asserting hardcoded UUID or shared state | Parse/compare header against body; never hardcode random values |
| Test affects production data | Full context creates real outbound beans | Use test profiles, fake adapters, sandbox DBs, CI egress controls |

When debugging, verify in order: **(1)** is the bean/config loaded?, **(2)** did the request enter the expected chain?, **(3)** did the pattern match?, **(4)** did the callback run before the controller?, **(5)** was the right data passed? Never work around issues by importing the entire production config into an MVC slice.

## 15. Pre-Merge Checklist

- [ ] Filter, Interceptor, and Argument Resolver are each used at their proper boundary.
- [ ] `RequestIdFilter` is registered **once**, with explicit URL patterns/order where needed.
- [ ] `TenantInterceptor` is explicitly registered via `WebMvcConfigurer#addInterceptors` for the right routes.
- [ ] Returning `false` from `preHandle` sets an appropriate HTTP status/response.
- [ ] Resolver `supportsParameter` is narrowly scoped using annotation + type without hijacking built-in args.
- [ ] Resolver reads request-scoped values from a defined trusted source, without conflating format validation and authorization.
- [ ] `@EnableWebMvc` is not added merely to extend MVC in a Spring Boot app.
- [ ] `@WebMvcTest` imports custom configs/beans under test and mocks business dependencies intentionally.
- [ ] Full-context tests cover real service logic where required.
- [ ] Tests assert status/headers/JSON and invalid-input paths, not merely callback counts.
- [ ] For generated IDs/timestamps, tests verify format and consistency rather than hardcoding values.
- [ ] A `RANDOM_PORT` HTTP test exists if Servlet container filter registration/networking needs proof.
- [ ] Team understands `postHandle`, `afterCompletion`, and async/error dispatches do not always match synchronous execution.
- [ ] Production privileges are minimized and sensitive data protected when MVC config touches auth/tenant data.
- [ ] When Spring Security is present, filter order, CORS, and auth are verified independently.

## 16. Self-Check Exercises and Answers

**1.** When adding a request ID to both MVC routes and requests that fail before reaching a controller, what should you pick?

**Answer:** A Servlet Filter is the natural choice since it runs before `DispatcherServlet`; configure registration, mapping, and dispatcher types appropriately. An Interceptor is not guaranteed to run before a handler is matched.

**2.** For controller method `inspect(@CurrentTenant TenantId tenant)`, what creates `TenantId`?

**Answer:** A `HandlerMethodArgumentResolver` registered via `WebMvcConfigurer#addArgumentResolvers`; `supportsParameter` matches the parameter and `resolveArgument` constructs the object.

**3.** `@WebMvcTest` reports the controller is missing a service bean; does that mean the custom interceptor is broken?

**Answer:** Not necessarily. Business `@Service` beans are excluded from the slice by default; provide `@MockitoBean` for the service, and `@Import` custom MVC config if needed.

**4.** The Filter sets `X-Request-Id`, yet the response body prints a different `requestId`; how should a test catch this?

**Answer:** Assert that the header and body values are equal, not just `header().exists(...)`. When generating random UUIDs, never hardcode the expected string.

**5.** Should Spring Security belong in an interceptor or a filter chain?

**Answer:** Use `SecurityFilterChain` and business authorization. MVC interceptors are not a primary security layer due to path-matching differences and incomplete coverage of security semantics.

**6.** Can `@SpringBootTest(webEnvironment=MOCK)` test Filters and Interceptors, and does it start a TCP server?

**Answer:** It can test them via `MockMvc` when configured; it **does not** open an embedded HTTP listener. To prove real networking/registration, use `RANDOM_PORT` and an HTTP client.

**7.** Why avoid adding `@EnableWebMvc` just to register `TenantArgumentResolver`?

**Answer:** `WebMvcConfigurer` is the proper extension point. `@EnableWebMvc` takes over broad MVC configuration and can alter desired Boot auto-configuration.

**8.** `preHandle` returns `false`; does the controller still execute, and is this interceptor's `afterCompletion` guaranteed to run?

**Answer:** The controller is skipped, and `afterCompletion` does not fire along the normal completed-handler path for that interceptor as it would when `preHandle` returns `true`. Place cleanup in the appropriate lifecycle hook and account for async/error dispatches separately.

**9.** Why does a passing `@WebMvcTest` not prove production tenant authorization is secure?

**Answer:** The illustrative test verifies header format and MVC binding only; multi-tenant permissions must rely on authenticated principals/policies and be tested across security, business, and data layers.

**10.** When needing to add a response header after a JSON body has already been written, is `postHandle` suitable?

**Answer:** You cannot rely on the response still being uncommitted at that point. Set headers before the chain/controller, or use an appropriate extension such as `ResponseBodyAdvice` or a response wrapper per requirements.

## 17. References

- [Spring Framework 6.2 – Servlet Filters and HandlerInterceptor](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/filters.html): Servlet filter chain and MVC integration.
- [Spring Framework 6.2 – MVC Interceptors](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/interceptors.html): `InterceptorRegistry` and warning against using interceptors as a security layer.
- [Spring Framework – `WebMvcConfigurer`](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html): MVC extension callbacks, `addArgumentResolvers`, `addInterceptors`.
- [Spring Framework – `HandlerMethodArgumentResolver`](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/method/support/HandlerMethodArgumentResolver.html): `supportsParameter` and `resolveArgument`.
- [Spring Framework – `OncePerRequestFilter`](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html): request dispatch, async/error behavior.
- [Spring Boot 3.5 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@WebMvcTest`, `@SpringBootTest`, `MockMvc`.
- [Spring Boot 3.5 – Spring MVC Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html#web.servlet.spring-mvc.auto-configuration): `WebMvcConfigurer` and effects of `@EnableWebMvc`.

**Conclusion:** **Filters** wrap the Servlet chain, **Interceptors** wrap MVC handlers, **Argument Resolvers** supply typed parameters, and **`WebMvcConfigurer`** registers and customizes those extensions. Tests must verify **status, headers, resolved data, and short-circuiting on invalid requests**, choosing `@WebMvcTest`, `@SpringBootTest(MOCK)`, or `RANDOM_PORT` according to the actual boundary you need to protect.