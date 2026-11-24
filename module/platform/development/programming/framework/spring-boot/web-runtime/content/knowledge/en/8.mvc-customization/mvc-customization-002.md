# WebMvcConfigurer: Adding Spring MVC Configuration While Preserving Spring Boot Defaults

## 1. The Problem to Solve

Spring Boot auto-configures Spring MVC so an application can handle HTTP requests with controllers without manually building the entire MVC infrastructure. However, a project may still need an interceptor, a parameter converter, CORS rules, an extra static path, or a view controller.

**WebMvcConfigurer** is the Spring MVC configuration extension interface for such needs. The right approach with Spring Boot is to write a **@Configuration implements WebMvcConfigurer** class and override only the necessary methods, **without adding @EnableWebMvc**.

~~~java
@Configuration(proxyBeanMethods = false)
public class MvcExtensionConfiguration implements WebMvcConfigurer {
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        // Register additional application interceptors.
    }
}
~~~

This snippet only illustrates the structure and is not a standalone program. Imports, controllers, and a complete runnable example appear in later sections.

The core point: **adding configuration** is different from **taking over management of all Spring MVC configuration**. Needing one interceptor does not mean you should replace `DispatcherServlet`, handler mappings, message converters, or the defaults Boot has already prepared.

This lesson uses APIs from Spring Boot **3.5.x / Spring Framework 6.2.x**, Java 17+. Method names related to message converters and how auto-configuration is organized may change when moving to Spring Boot 4.x / Spring Framework 7.x; always consult documentation for the exact version you are running.

## 2. What Does Spring Boot Configure?

With the `spring-boot-starter-web` dependency, Spring Boot prepares a Servlet-based web application: embedded Tomcat by default, `DispatcherServlet`, MVC supporting beans, and integration with Boot options.

Typical MVC-related auto-configured utilities include:

- Handler mappings and adapters to route HTTP requests to controllers.
- `ContentNegotiatingViewResolver` and `BeanNameViewResolver`.
- `HttpMessageConverters` to read request bodies and write response bodies, such as JSON.
- `Converter`, `GenericConverter`, and `Formatter` beans supplied by the application context.
- Serving static resources from default classpath locations such as `/static` and `/public`.
- Support for `index.html` as a welcome page.
- Integrations for binding, error handling, and related configuration properties.

Boot also has dedicated configuration for Jackson, multipart, path matching, static resource chains, date/time formatting, compression, and other components, depending on version, dependencies, and properties.

Example controller:

~~~java
@RestController
@RequestMapping("/api")
public class ExampleController {

    @GetMapping("/hello")
    public Map<String, String> hello() {
        return Map.of("message", "hello");
    }
}
~~~

There is no need to manually register `MappingJackson2HttpMessageConverter` for responses to be serialized to JSON when `starter-web` includes the required dependencies. Additional configuration should preserve these capabilities.

## 3. Three Easily Confused Ways to Configure MVC

| Approach | Expected Behavior | When to Use |
|---|---|---|
| `@Configuration` + `WebMvcConfigurer` | Adds or adjusts MVC configuration through extension points while keeping Boot's MVC auto-configuration | Default choice for most applications |
| `@Configuration` + `@EnableWebMvc` | Takes over MVC configuration responsibility, causing Boot's MVC auto-configuration to no longer apply as before | When intentionally managing MVC infrastructure at the framework level |
| Declaring `WebMvcConfigurationSupport` or equivalent replacement infrastructure configuration | Causes Boot to back off and alters defaults | Advanced cases requiring full control |

### 3.1. Recommended Approach

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class AppMvcConfiguration implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        // Register only what needs to be added.
    }
}
~~~

Spring Boot can continue registering resource handlers, message converters, and its default MVC components.

### 3.2. Approach to Avoid When You Only Want to Add a Feature

~~~java
@Configuration
@EnableWebMvc
public class FullMvcConfiguration implements WebMvcConfigurer {
}
~~~

The declaration above is a **counterexample not to apply** when the goal is to preserve Boot defaults. `@EnableWebMvc` activates Spring Framework's standalone MVC configuration path; Boot's MVC auto-configuration is no longer applied in the usual way. MVC does not stop working, but many utilities the application previously received from Boot may need to be reconfigured manually.

A common mistake is adding `@EnableWebMvc` from a plain Spring Framework example and then discovering that CSS/JS or `index.html` is no longer served as before. The cause is not `WebMvcConfigurer`, but switching to manual MVC management.

### 3.3. Do Not Confuse with WebFlux

`WebMvcConfigurer` is for the **Spring MVC / Servlet stack**. It is not the customization mechanism for Spring WebFlux. WebFlux has its own extension points such as `WebFluxConfigurer`.

If you include both `spring-boot-starter-web` and `spring-boot-starter-webflux` just to use `WebClient`, Boot usually prioritizes the MVC model for the server. Having `WebClient` present does not automatically turn a `WebMvcConfigurer` into WebFlux configuration.

## 4. Key Methods of WebMvcConfigurer

| Method | Used For | Notes |
|---|---|---|
| `addInterceptors` | Adding `HandlerInterceptor` by path | Does not replace Spring Security |
| `addFormatters` | Registering `Converter` and `Formatter` | Useful for `@RequestParam`, `@PathVariable`, binding |
| `addCorsMappings` | Adding CORS mappings | CORS is not an authentication mechanism |
| `addViewControllers` | Mapping simple URLs to views or redirects | Avoids writing controller logic |
| `addResourceHandlers` | Adding static resources by path | Check resource location and caching |
| `configurePathMatch` | Adjusting path matching behavior | Easily affects all endpoints |
| `configureContentNegotiation` | Adjusting content negotiation strategy | Can change representation selection |
| `addArgumentResolvers` | Adding resolvers for custom parameters | New resolvers do not replace all built-in resolvers |
| `addReturnValueHandlers` | Adding handlers for custom return types | Use only when specialized extensions are needed |
| `configureMessageConverters` | Controlling the converter list | Be very careful with default converters |
| `extendMessageConverters` | Adjusting the list after configuration | Usually safer when only adding/tweaking part of it |
| `configureAsyncSupport` | Configuring async request processing | Does not replace HTTP client/upstream timeouts |
| `configureDefaultServletHandling` | Delegating resources to the default servlet | Use only when the container architecture requires it |

You do not need to override every method. `WebMvcConfigurer` provides default methods, so a class only needs to implement the exact hooks it uses.

## 5. A Runnable Project: Extending MVC While Keeping Defaults

Problem statement:

1. Every request to `/api/**` receives the response header `X-MVC-Extension: enabled` via an interceptor.
2. The parameter `priority=high` or `priority=normal` is converted to the `Priority` enum.
3. `/welcome` redirects to `/api/status` without needing a separate controller.
4. `/guides/**` serves additional content from `classpath:/public-guides/`.
5. Origin `https://app.example.com` is allowed to call the API under the specified CORS policy.
6. `/index.html` in the default static directory and JSON responses continue working: this is an important check that the application did not accidentally drop all Boot MVC defaults.

Structure:

~~~text
mvc-extension-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/mvcdemo/
    │   │   ├── MvcDemoApplication.java
    │   │   ├── Priority.java
    │   │   ├── DemoHeaderInterceptor.java
    │   │   ├── MvcEnhancements.java
    │   │   └── DemoController.java
    │   └── resources/
    │       ├── static/index.html
    │       └── public-guides/start.txt
    └── test/java/com/example/mvcdemo/
        └── MvcDemoTest.java
~~~

### 5.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mvc-extension-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>mvc-extension-demo</name>

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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugins>
    </build>
</project>
~~~

Version `3.5.16` is used to pin the example APIs. This is the final OSS-supported release of the 3.5.x branch; for new production projects, choose a supported branch and adapt examples to the corresponding APIs.

### 5.2. MvcDemoApplication.java

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

`@SpringBootApplication` enables auto-configuration and component scanning. Place the file in the `com.example.mvcdemo` package so the remaining classes are scanned.

### 5.3. Priority.java

~~~java
package com.example.mvcdemo;

public enum Priority {
    LOW, NORMAL, HIGH
}
~~~

### 5.4. DemoHeaderInterceptor.java

~~~java
package com.example.mvcdemo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
public class DemoHeaderInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        response.setHeader("X-MVC-Extension", "enabled");
        return true;
    }
}
~~~

This interceptor illustrates an action that does not alter business logic. It adds a response header before the controller runs and lets the request proceed by returning `true`.

In a real project, do not use this demonstration header as proof of authentication, authorization, or a trust signal between systems.

### 5.5. MvcEnhancements.java: Main Extension Configuration

~~~java
package com.example.mvcdemo;

import java.util.Locale;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.ViewControllerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcEnhancements implements WebMvcConfigurer {

    private final DemoHeaderInterceptor interceptor;

    public MvcEnhancements(DemoHeaderInterceptor interceptor) {
        this.interceptor = interceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(interceptor)
                .addPathPatterns("/api/**");
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
                String.class,
                Priority.class,
                source -> Priority.valueOf(
                        source.trim().toUpperCase(Locale.ROOT)));
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.com")
                .allowedMethods("GET")
                .allowedHeaders("Content-Type")
                .maxAge(3600);
    }

    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        registry.addRedirectViewController(
                "/welcome", "/api/status");
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/guides/**")
                .addResourceLocations("classpath:/public-guides/");
    }
}
~~~

There is no `@EnableWebMvc` here. What the application does is register **additional** components with the registries Spring MVC already uses.

Intentional choices:

- Interceptor scope is `/api/**`, not applied to all static resources.
- The `String` → `Priority` converter lets clients pass `high`, `normal`, or `low` and still receive the enum.
- CORS allows only one specific origin and the `GET` method.
- The `/guides/**` resource mapping is a new path and does not redeclare the default `/**` mapping.
- The view controller simply redirects, without mixing in business logic.

### 5.6. DemoController.java

~~~java
package com.example.mvcdemo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {

    @GetMapping("/status")
    public Map<String, String> status() {
        return Map.of("status", "ready");
    }

    @GetMapping("/tasks")
    public Map<String, String> tasks(
            @RequestParam(defaultValue = "normal") Priority priority) {

        return Map.of(
                "status", "ready",
                "priority", priority.name());
    }
}
~~~

Without a custom converter, default enum binding typically requires matching the exact enum constant name; after registering the converter, a request with `priority=high` is converted to `Priority.HIGH`. The rest of the handler does not need to care about casing in the query string.

### 5.7. Default and Additional Static Resources

Create **src/main/resources/static/index.html**:

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>MVC defaults</title>
</head>
<body>
  <h1>Welcome from Boot static resources</h1>
</body>
</html>
~~~

Create **src/main/resources/public-guides/start.txt**:

~~~text
Guide served by custom resource handler.
~~~

`/index.html` belongs to Boot's built-in static resources mechanism. `/guides/start.txt` belongs to the mapping added by the application. Both mechanisms can coexist.

## 6. Running and Expected Results

Requires Java 17+ and Maven 3.6.3+:

~~~bash
mvn test
mvn spring-boot:run
~~~

When the application runs on the default port 8080, verify:

~~~bash
curl -i "http://localhost:8080/api/tasks?priority=high"
curl -i "http://localhost:8080/api/status"
curl -i "http://localhost:8080/welcome"
curl -i "http://localhost:8080/index.html"
curl -i "http://localhost:8080/guides/start.txt"
~~~

Key results:

- `GET /api/tasks?priority=high` returns 200, with header `X-MVC-Extension: enabled` and JSON containing `priority` equal to `HIGH` and `status` equal to `ready`. JSON field order is not a guaranteed contract.
- `GET /api/status` returns JSON with `status` equal to `ready`.
- `GET /welcome` returns a redirect (typically 302) to `/api/status`.
- `GET /index.html` returns HTML containing `Welcome from Boot static resources`: **Boot defaults still work**.
- `GET /guides/start.txt` returns `Guide served by custom resource handler.` from the new resource handler.

Example body of `/api/tasks`:

~~~json
{"priority":"HIGH","status":"ready"}
~~~

Do not assert that JSON key order or HTTP header order is always identical. Checking status, custom headers, and JSON values is sufficient.

## 7. Integration Testing with MockMvc

Add **src/test/java/com/example/mvcdemo/MvcDemoTest.java**:

~~~java
package com.example.mvcdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MvcDemoTest {

    @Autowired
    MockMvc mvc;

    @Test
    void convertsQueryParameterAndRunsInterceptor() throws Exception {
        mvc.perform(get("/api/tasks").param("priority", "high"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-MVC-Extension", "enabled"))
                .andExpect(jsonPath("$.priority").value("HIGH"))
                .andExpect(jsonPath("$.status").value("ready"));
    }

    @Test
    void preservesDefaultStaticResourceHandling() throws Exception {
        mvc.perform(get("/index.html"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        containsString("Welcome from Boot static resources")));
    }

    @Test
    void servesAdditionalResourceMapping() throws Exception {
        mvc.perform(get("/guides/start.txt"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        containsString("Guide served by custom resource handler.")));
    }

    @Test
    void mapsViewControllerRedirect() throws Exception {
        mvc.perform(get("/welcome"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/api/status"));
    }
}
~~~

This test suite verifies both the new functionality and a default behavior simultaneously. That is a better testing approach than merely confirming that the `MvcEnhancements` bean exists in the `ApplicationContext`.

Run:

~~~bash
mvn test
~~~

If all tests succeed, Maven returns exit code 0. Test count, execution time, and log text depend on the environment; do not hard-code log output as a pass/fail criterion.

## 8. Interceptors: Understanding Scope of Impact

`HandlerInterceptor` runs in Spring MVC's processing flow around a handler. Main methods:

- `preHandle` runs before the handler executes and can stop processing by returning `false`.
- `postHandle` can run after the handler when the processing model allows it; with `@ResponseBody` and async handling, do not assume you can modify the response content here.
- `afterCompletion` runs after the request completes for cleanup or observability. With async processing, there are separate considerations regarding dispatches and callbacks.

When registering an interceptor:

~~~java
registry.addInterceptor(interceptor)
        .addPathPatterns("/api/**")
        .excludePathPatterns("/api/public/**");
~~~

Include/exclude paths should be tested in the context of the servlet mapping and matching strategy. Do not use an interceptor to replace a Servlet-layer security filter or the Spring Security filter chain.

**Why not use an interceptor as the sole authorization layer?**

- Some requests may not pass through an MVC handler registered with the interceptor.
- Include/exclude rules depend on mappings.
- Security must consistently handle credentials, authentication, exceptions, CSRF, and other entry points.

Spring Security is usually better suited for authentication/authorization. Interceptors are useful for instrumentation, logging metadata, setting up request context, or cross-cutting concerns tied to controllers.

If you need processing before `DispatcherServlet` or across the entire Servlet request chain, consider `Filter`/`OncePerRequestFilter` or `FilterRegistrationBean` instead of `HandlerInterceptor`.

## 9. Converter and Formatter: Choosing the Right Tool

`addFormatters` receives a `FormatterRegistry`. Here you can register:

- `Converter<S,T>`: a conversion from type `S` to `T`.
- `ConverterFactory<S,R>`: creates converters for a family of target types.
- `Formatter<T>`: converts `String` ↔ object with locale awareness via `print`/`parse`.

For example, converting a parameter in `yyyy-MM-dd` format to a domain type. If the application only needs standard date/time formatting, prefer Boot properties such as `spring.mvc.format.date` before writing a new converter.

A `Formatter` is appropriate when locale-dependent formatting is needed. For instance, currency formatting can use `NumberFormat` or a custom `Formatter`, though malformed input must be handled and ambiguous separators avoided.

**Important note:** Spring MVC's `ConversionService` used for request binding is different from the conversion service Boot uses to bind `application.properties`/`application.yml`. A converter registered via `WebMvcConfigurer.addFormatters` does not automatically convert values in `@ConfigurationProperties`.

When you only need to change the format of a single field:

~~~java
@GetMapping("/search")
public String search(
        @RequestParam
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate date) {
    return date.toString();
}
~~~

This is an illustrative snippet; imports for `LocalDate` and `DateTimeFormat` are required when placed in a controller class. It shows that not every binding requirement needs `WebMvcConfigurer` configuration.

## 10. CORS: Adding Mappings Does Not Mean Opening All Security

`addCorsMappings` configures Cross-Origin Resource Sharing policies for requests handled through Spring MVC. With a frontend at `https://app.example.com` and a backend at `https://api.example.com`, browsers enforce origin policies and may send preflight requests.

~~~java
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST")
            .allowedHeaders("Content-Type", "Authorization")
            .exposedHeaders("X-Request-Id")
            .maxAge(1800);
}
~~~

This snippet illustrates when an application needs to add `POST` and `Authorization`; it is not part of the runnable example in Section 5.

Keep these distinctions clear:

- CORS controls whether JavaScript on another origin is permitted to read the response in a browser.
- CORS does **not** replace server-side authentication and authorization.
- CORS is **not** a complete CSRF mitigation.
- `allowCredentials` should only be enabled when sending cookies/credentials from the browser is truly needed, and origins must be restricted accordingly.
- Using wildcard origins carelessly can create data access vulnerabilities if credentials are misconfigured.

If the application uses Spring Security, CORS handling must be integrated with the security filter chain. Preflight requests usually do not carry session credentials and may be blocked by security filters before reaching MVC if not configured properly.

For a simple global CORS policy, `WebMvcConfigurer` is a common configuration point; for endpoint-specific policies, `@CrossOrigin` on a controller or method can be used when genuinely appropriate.

## 11. View Controllers and Static Resources

### 11.1. View Controllers

`addViewControllers` is useful for endpoints without business logic:

~~~java
@Override
public void addViewControllers(ViewControllerRegistry registry) {
    registry.addViewController("/about").setViewName("about");
    registry.addRedirectViewController("/legacy", "/about");
}
~~~

If returning the `"about"` view, the project must have a view resolver and corresponding template or suitable view-serving setup. For API-only applications, do not create view controllers just to return JSON data; use `@RestController`.

In the runnable project in Section 5, redirecting `/welcome` → `/api/status` avoids depending on a template engine.

### 11.2. Resource Handlers

By default, Boot serves static content from locations such as `classpath:/static/`, `classpath:/public/`, `classpath:/resources/`, and `classpath:/META-INF/resources/`. `addResourceHandlers` is appropriate when you need to add a custom location:

~~~java
registry.addResourceHandler("/docs/**")
        .addResourceLocations("classpath:/extra-docs/");
~~~

An overly broad mapping such as `/**` can overlap Boot's static resource mapping and cause unintended changes in behavior. When you only want to change the default static path or locations, first consider the `spring.mvc.static-path-pattern` or `spring.web.resources.static-locations` properties for the version you are using.

Do not serve confidential internal documents simply by placing them under static resources. Files downloadable over HTTP must be controlled in accordance with access policies.

### 11.3. Caching and Versioning Rules

Static resources in production may need cache-control and content-based versioning. Boot provides properties for static resources and resource chains depending on the version. If specific behavior is needed for `/docs/**`, caching can be configured on that exact resource handler.

However, verify caching behavior for sensitive data, frequently changing files, proxies/CDNs, and actual headers. Do not set a long `max-age` on all responses just to speed up page loads.

## 12. Message Converters: Where Defaults Are Easily Lost

Spring MVC uses `HttpMessageConverter` to read `@RequestBody` and write `@ResponseBody`. When `spring-boot-starter-web` and Jackson are present, Java objects are usually serialized to JSON without manual configuration.

In **Spring Framework 6.2**, `WebMvcConfigurer` has two easily confused hooks:

- `configureMessageConverters(List<HttpMessageConverter<?>>)`: directly configures the list of converters; in standard MVC configuration, using this hook can affect the addition of default converters. Spring Boot has its own mechanism for contributing `HttpMessageConverter` beans, so you should not oversimplify by claiming every Boot application will always lose all default converters.
- `extendMessageConverters(List<HttpMessageConverter<?>>)`: called to further adjust the converter list after it has been formed. When only small changes are needed, consider this hook.

Example of merely inspecting converters during extension:

~~~java
@Override
public void extendMessageConverters(
        List<HttpMessageConverter<?>> converters) {
    // Only add or adjust what is truly necessary.
    // Do not call clear() or replace the whole list arbitrarily.
}
~~~

The snippet above illustrates the structure and requires importing `List` and `HttpMessageConverter`.

For JSON customization, look at higher-level options first:

1. `spring.jackson.*` properties in supported Boot versions.
2. Jackson beans or customizers appropriate to the project version.
3. An `HttpMessageConverter` bean when a genuinely new format or handling mechanism is required.
4. `extendMessageConverters` when there is a clear fine-tuning requirement and converter ordering has been verified.

Do not manually create `RequestMappingHandlerAdapter` or remove default converters just to change how a JSON property is formatted.

**Version note:** Spring Framework 7 changed several message converter configuration contracts. The `List`-accepting hook shown here is for Spring Framework 6.2 / Spring Boot 3.5; when upgrading to Boot 4, review the signatures and API migration guide.

## 13. When Is WebMvcRegistrations Needed?

There are advanced requirements where you must customize how a core MVC infrastructure component is created—such as `RequestMappingHandlerMapping`, `RequestMappingHandlerAdapter`, or `ExceptionHandlerExceptionResolver`—while still keeping Boot's MVC customizations.

Spring Boot provides the **WebMvcRegistrations** extension point for such cases. It allows the application to supply custom instances of certain infrastructure beans before Spring MVC finishes initializing/configuring them.

This is **not** the default choice for an interceptor or converter. `WebMvcConfigurer` solves far more scenarios with less risk and less code coupled to internals.

Suggested order of preference:

1. Boot properties if sufficient.
2. Business-level beans or component extensions.
3. `WebMvcConfigurer` for official hooks.
4. `WebMvcRegistrations` if specialized MVC components are needed.
5. Only use `@EnableWebMvc` and full configuration when intentionally taking over MVC configuration.

Test the impact on content negotiation, static resources, exception handling, and security when replacing core components.

## 14. When to Use application.properties Instead of WebMvcConfigurer?

Not every configuration requirement needs Java code. For example:

~~~properties
server.port=8080
server.servlet.context-path=/shop
spring.mvc.static-path-pattern=/assets/**
spring.web.resources.static-locations=classpath:/static/
spring.mvc.format.date=iso
~~~

These are example properties usable under the Boot 3.5.x contract; you do not necessarily configure all of them at once. Properties have different scopes and interactions:

- `server.port` sets the embedded server port.
- `server.servlet.context-path` sets the Servlet application's context path.
- `spring.mvc.static-path-pattern` changes the pattern for static resources, not all controller mappings.
- `spring.web.resources.static-locations` changes the list of locations serving static resources; if you override the list, make sure desired locations are retained.
- `spring.mvc.format.date` configures the default format for applicable MVC date binding.

When a requirement can be solved with properties, properties are usually easier to track per environment, require less code, and have fewer API dependencies. However, when mapping selection logic depends on beans or domain behavior, `WebMvcConfigurer` can be clearer.

## 15. Multiple WebMvcConfigurer Beans Can Coexist

An application can declare multiple configuration classes implementing `WebMvcConfigurer` across different modules. Spring MVC aggregates their contributions through the framework's configuration mechanism.

Still, keep the following in mind:

- Multiple interceptors matching the same path can run sequentially; document order and scope clearly.
- Two configurations altering formatting/converters for the same type can conflict.
- Two resource mappings with overlapping patterns can make behavior hard to predict.
- CORS policies from multiple places must be evaluated according to combination and precedence rules.
- Customizing path matching or message converters has global impact and requires regression testing.

`@Order` can be used on beans or registrations where the framework supports ordering at the relevant extension point. Do not assume an unspecified order is a guaranteed contract across modules.

A maintainable organization typically names classes clearly by responsibility, such as `ApiCorsConfiguration`, `MvcFormattingConfiguration`, and `InterceptorConfiguration`, with each class owning a single group of configurations.

## 16. Common Issues and How to Resolve Them

| Symptom | Possible Cause | Resolution |
|---|---|---|
| After adding custom MVC config, CSS/JS or `index.html` returns 404 | Added `@EnableWebMvc` or replaced `WebMvcConfigurationSupport` | Remove takeover configuration if unnecessary; keep plain `WebMvcConfigurer` and test static files |
| JSON responses are no longer converted as before | Message converter list was replaced, Jackson is missing, or media type mismatches | Check dependencies and converters; use `extendMessageConverters` or Boot mechanisms when only adding |
| Interceptor does not run for expected endpoint | Path pattern does not match, endpoint is not an MVC handler, or path is excluded | Check `addPathPatterns`, servlet mapping, and actual requests |
| Interceptor is treated as security, but other endpoints slip through | `HandlerInterceptor` is not a comprehensive security filter chain | Use Spring Security and test all entry points |
| `@RequestParam` enum fails on lowercase strings | Converter not registered or converter order conflicts | Register properly via `addFormatters` and test lower/upper case |
| CORS still blocked after `addCorsMappings` | Origin/method/header mismatch or Spring Security handles it first | Inspect preflight requests and security configuration |
| New resource handler accidentally blocks old static resources | Overly broad pattern like `/**` or wrong resource location | Use a narrow namespace and test both old and new paths |
| Changing `spring.mvc.static-path-pattern` causes `/index.html` 404 | Default pattern was replaced by the new prefix | Access via the new URL or adjust the property |
| `@ConfigurationProperties` does not use the converter registered for MVC | MVC conversion service differs from Boot's binder | Customize property conversion via Boot's corresponding mechanism |
| View controller registered, but view does not render | Missing template/view resolver or confusing view with REST response | Configure view engine properly or use `@RestController` |
| Switched server stack and `WebMvcConfigurer` has no effect | Application runs WebFlux/reactive instead of MVC/Servlet | Verify starters and application type, and use `WebFluxConfigurer` if needed |
| Small customization breaks many existing tests | Accidentally replaced default infrastructure or altered global path matching | Start from the minimal hook and run regression tests per endpoint |

## 17. Pre-Merge Checklist

- [ ] Application actually runs Spring MVC/Servlet, not a Spring WebFlux server.
- [ ] Configuration class uses `@Configuration implements WebMvcConfigurer`.
- [ ] Neither `@EnableWebMvc` nor manual `WebMvcConfigurationSupport` is added if Boot auto-configuration should remain active.
- [ ] Only necessary methods are overridden; paths for interceptors/CORS/resources are clearly scoped.
- [ ] Interceptors are not used in place of authentication/authorization.
- [ ] All default message converters are not accidentally replaced.
- [ ] Boot properties were checked before writing custom Java code.
- [ ] Default static resources and JSON mappings still work.
- [ ] Error cases are tested for both new and existing endpoints.
- [ ] Any global path matching, content negotiation, formatting, or async changes have regression tests.
- [ ] API and method names are verified against the exact Spring Boot/Spring Framework branch in use.

## 18. Takeaways

**WebMvcConfigurer is an extension point, not a request to replace all of Spring MVC.** When you want to add interceptors, formatters, CORS mappings, redirects, or static resource handlers in Spring Boot, create a `@Configuration implements WebMvcConfigurer` **and do not add @EnableWebMvc**.

Only use `@EnableWebMvc` when intentionally taking over MVC infrastructure and accepting responsibility for recreating the necessary behaviors Boot previously provided. Always test both sides: the added functionality **and** the defaults that must continue working.

## Official Documentation

- [Spring Boot 3.5 — Servlet Web Applications and MVC Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Spring Framework 6.2 — Web MVC Config](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config.html)
- [Spring Framework 6.2 — Message Converters](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/message-converters.html)
- [Spring Framework 6.2 — Interceptors](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/interceptors.html)
