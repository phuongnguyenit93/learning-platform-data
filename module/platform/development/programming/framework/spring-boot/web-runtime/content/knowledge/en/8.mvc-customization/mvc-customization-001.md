# What Spring Boot Auto-Configures for Spring MVC

An application using `spring-boot-starter-web` can declare `@RestController`, `@GetMapping`, and return JSON right at startup, even though we have not manually created `DispatcherServlet`, `RequestMappingHandlerMapping`, or `HttpMessageConverter`. The reason is that **Spring Framework provides the Spring MVC mechanism**, while **Spring Boot detects runtime conditions and assembles the appropriate default configuration**. Understanding this boundary clearly helps you extend MVC at the right point without accidentally disabling the conveniences Boot provides.

This lesson focuses on **Servlet/Spring MVC applications on Spring Boot 3.3.x, Java 17+**: the components that are prepared, their roles in the HTTP flow, auto-configuration conditions, the default replacement mechanism, and how to customize safely. Some components only appear when the corresponding dependency or property is present; "auto-configured" does not mean every bean always exists in every project.

## 1. Three Layers of Responsibility

| Layer | Responsibility | Examples |
|---|---|---|
| **Spring Framework MVC** | Defines contracts and HTTP processing mechanisms | `DispatcherServlet`, `HandlerMapping`, `HandlerAdapter`, `HandlerExceptionResolver`, `HttpMessageConverter`, `ViewResolver` |
| **Spring Boot auto-configuration** | Selects default configuration based on classpath, properties, application type, and existing beans | `WebMvcAutoConfiguration`, `DispatcherServletAutoConfiguration`, `ErrorMvcAutoConfiguration`, `HttpMessageConvertersAutoConfiguration` |
| **Application code** | Defines endpoints and custom policies, or adds/replaces configuration | `@RestController`, `@ControllerAdvice`, `WebMvcConfigurer`, `spring.mvc.*` configuration |

Spring MVC is not a servlet container. A servlet container such as Tomcat accepts connections and dispatches requests into servlets; in an MVC application, the entry-point servlet is `DispatcherServlet`. Inside it, Spring MVC looks up the matching handler, invokes the controller, converts parameters, and processes the result.

Spring Boot reduces configuration boilerplate by registering the servlet, wiring MVC strategies, and configuring static resources/error handling when conditions are met. Writing business logic remains the application's responsibility.

## 2. Conditions for Spring Boot to Auto-Configure Spring MVC

When adding the Gradle dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

This starter typically brings in Spring MVC, Jackson for JSON, and embedded Tomcat. At runtime, Boot detects a **Servlet web application** environment and evaluates the corresponding auto-configurations.

Conceptually, `WebMvcAutoConfiguration` is activated when:
- The required Servlet and Spring MVC classes are on the classpath.
- The application is running with `WebApplicationType.SERVLET`.
- The application has not provided a full MVC configuration such as `WebMvcConfigurationSupport` that forces Boot to yield control.

Conditional mechanisms are typically expressed using `@ConditionalOnClass`, `@ConditionalOnWebApplication`, `@ConditionalOnMissingBean`, and related conditions. Auto-configuration only creates the appropriate beans after evaluating those conditions.

**Back-off** is an important rule: if the application already provides a bean at a Boot-supported extension point, the corresponding auto-configuration may skip creating the default bean or use the application's bean instead. However, the level of back-off varies by configuration; you should not assume that declaring any bean implementing an interface will cause all MVC auto-configuration to disappear.

If only `spring-boot-starter-webflux` is present and the runtime is Reactive, the application uses the WebFlux processing chain; equivalent concepts such as WebFlux codecs/handlers are not Servlet MVC configuration. When both MVC and WebFlux are present, Boot usually selects Servlet by default. You should verify the actual web stack before modifying configuration.

## 3. Request Processing Flow Map

A typical MVC request passes through the following layers:

~~~text
HTTP Client
     |
Embedded servlet container (Tomcat / Jetty / Undertow)
     |
Servlet Filter chain
     |
DispatcherServlet
     |
HandlerMapping  -> finds controller/handler
     |
HandlerAdapter  -> reads parameters, binder/converter, invokes handler
     |
Controller/handler
     |
     +--> @ResponseBody / ResponseEntity
     |       -> HttpMessageConverter -> JSON/text/bytes
     |
     +--> view name / ModelAndView
             -> ViewResolver -> View -> HTML
     |
HTTP response

If an exception occurs:
HandlerExceptionResolver / @ExceptionHandler / @ControllerAdvice
     or the container's error dispatch mechanism -> /error
~~~

This is a diagram of **processing responsibilities**, not an indication that Boot writes every bean itself. Implementations such as `RequestMappingHandlerMapping` and `RequestMappingHandlerAdapter` are Spring MVC infrastructure; Boot initializes and wires them through the appropriate configuration.

## 4. DispatcherServlet and Servlet Container Registration

`DispatcherServlet` is the front controller of Spring MVC. Every request entering this servlet is routed through the MVC strategies: finding a mapping, invoking the handler, and processing results and exceptions.

Spring Boot provides `DispatcherServletAutoConfiguration` to supply `DispatcherServlet` and its servlet registration bean when appropriate. In a typical MVC application:
- `DispatcherServlet` is the central servlet.
- `DispatcherServletRegistrationBean` registers the servlet with the container.
- `ServletWebServerApplicationContext` coordinates with the embedded server factory to start the Servlet environment.

By default, Boot registers `DispatcherServlet` at the root mapping `/` of the servlet context. This differs from the actual public URL when `server.servlet.context-path` or `spring.mvc.servlet.path` is configured.

Example:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /shop

spring:
  mvc:
    servlet:
      path: /
~~~

With a controller mapping `@GetMapping("/api/items")`, the external URL will start with `/shop/api/items`. The context path property belongs to the Servlet container; the servlet path property adjusts the mapping of `DispatcherServlet`. You should not change these values without considering reverse proxies, static asset paths, and the path matching strategy.

When a second servlet is needed, register it deliberately with `ServletRegistrationBean` or a Boot-supported mechanism. An application-created servlet does not automatically replace the `DispatcherServlet` managing MVC.

## 5. HandlerMapping: Selecting the Right Handler

`HandlerMapping` selects the handler for a request. The most common component for annotation-based controllers is `RequestMappingHandlerMapping`.

It relies on metadata:
- HTTP method: `@GetMapping`, `@PostMapping`, ...
- URL path and path variables.
- `params` and `headers` conditions.
- `consumes`: accepted request formats.
- `produces`: response formats the handler can provide.

Example:

~~~java
@RestController
@RequestMapping("/api/items")
class ItemController {

    @GetMapping(path = "/{id}", produces = "application/json")
    ItemResponse find(@PathVariable long id) {
        return new ItemResponse(id, "Book");
    }
}

record ItemResponse(long id, String name) {}
~~~

Spring MVC builds mappings from annotations; when `GET /api/items/7` arrives, it selects the corresponding method and delegates method invocation to `HandlerAdapter`.

In Boot 3.3, the default path matching strategy is `PathPatternParser`. Keep in mind:
- Path patterns have specific rules; some older Ant-style patterns are incompatible.
- By default, it does **not** rely on a `.json` suffix in the URL to automatically choose a handler/media type.
- You can configure `spring.mvc.pathmatch.matching-strategy=ant-path-matcher` when legacy compatibility behavior is genuinely needed.
- Boot documentation warns that using `PathPatternParser` together with a servlet path prefix (`spring.mvc.servlet.path`) has compatibility limitations.

Do not change the entire strategy just to fix a single misconfigured endpoint. Verify the URL, HTTP method, annotations, and server context path first.

## 6. HandlerAdapter: Invoking the Controller and Converting Parameters

After locating the handler, `HandlerAdapter` is responsible for knowing how to invoke it. For annotation-based controllers, the primary component is `RequestMappingHandlerAdapter`.

It coordinates multiple Spring MVC extension points:
- `HandlerMethodArgumentResolver`: resolves `@PathVariable`, `@RequestParam`, `@RequestHeader`, `@RequestBody`, and other argument types.
- `WebDataBinder` and `ConversionService`: binds/converts request values into Java types.
- `HttpMessageConverter`: deserializes request bodies and serializes response bodies.
- `HandlerMethodReturnValueHandler`: handles `@ResponseBody`, `ResponseEntity`, `ModelAndView`, async responses, and supported return types.
- Validation, exception handling, and other configuration depending on dependencies.

For example, `GET /api/items/7` does not send a `long` object over the wire. The path variable value `"7"` is text; the binder/conversion mechanism converts it to `long` before the method is invoked.

When a request path contains a value that cannot be converted to the target type, Spring MVC typically reports a binding/type mismatch error and returns HTTP 400 according to the default exception resolution mechanism. Conversely, when a JSON body is invalid, the body reading error relates to the message converter.

## 7. HttpMessageConverters: Reading Requests and Writing Responses

Spring MVC uses the `HttpMessageConverter<T>` interface. Spring Boot configures a sensible set of converters based on dependencies and existing beans.

Common examples:

| HTTP body | Potentially involved converter/library | Usage |
|---|---|---|
| `application/json` | Jackson JSON converter when Jackson is present | `@RequestBody` DTO; `@RestController` returning record/object |
| `text/plain` | `StringHttpMessageConverter` | Reading/writing strings |
| Binary | `ByteArrayHttpMessageConverter` | `byte[]` |
| `application/x-www-form-urlencoded` | Form converter and request parameter mechanism | Form fields |
| XML | XML converter when the corresponding dependency is present | XML DTO |

Spring MVC applies two important headers:
- `Content-Type` indicates what format the **client-sent body** is in.
- `Accept` indicates which formats the client **wants to receive**.

In addition to selecting the handler via `consumes` and `produces`, a converter must also be able to read/write the media type and Java type.

Example:

~~~java
@PostMapping(
    path = "/items",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
ItemResponse create(@RequestBody CreateItemRequest input) {
    return new ItemResponse(10L, input.name());
}
~~~

When the client sends valid JSON, Jackson typically creates `CreateItemRequest` from the body and writes `ItemResponse` as JSON. If Jackson or a suitable converter is missing, merely declaring `produces="application/json"` does not automatically grant serialization capability.

**Distinguish the two conversion systems:** Spring MVC's `ConversionService` handles values such as query/path/form parameters into Java types; `HttpMessageConverter` handles the HTTP body. The MVC conversion service is also **different** from the conversion service used to bind `application.yml` into `@ConfigurationProperties`. Do not assume that `Duration`/`DataSize` converters meant for configuration properties automatically appear in the MVC binder.

To extend converters:
- Declare an `HttpMessageConverter<?>` bean when appropriate so Boot includes it in the list.
- For changes to the overall list, you can use `WebMvcConfigurer` hooks such as `extendMessageConverters` to add/adjust within the MVC scope.
- Only use `configureMessageConverters` when you truly want to control the list, because it risks replacing default converters depending on how it is configured.

## 8. Formatter, Converter, Binding, and MessageCodesResolver

Spring Boot automatically registers `Converter`, `GenericConverter`, and `Formatter` beans into the MVC conversion service when provided through the appropriate mechanism. This helps:
- Standardize how a domain type is read from query/path parameters.
- Unify date, time, or number parsing and formatting.
- Reduce repetitive conversion code in controllers.

You can register custom formatters/converters using `WebMvcConfigurer.addFormatters`. For temporal formatting, Boot supports several `spring.mvc.format.*` properties.

Example:

~~~yaml
spring:
  mvc:
    format:
      date: iso
      date-time: iso
~~~

These two properties only affect **Spring MVC binding/formatting within their supported scope**; they do not automatically alter the Jackson serializer for JSON bodies. JSON formatting can be configured through Jackson or annotations such as `@JsonFormat` when appropriate.

`WebBindingInitializer` initializes `WebDataBinder` for requests. If the application provides a `ConfigurableWebBindingInitializer` bean, Boot has a mechanism to use that bean to configure Spring MVC.

`MessageCodesResolver` generates error codes for binding/validation, helping views or error handlers look up messages. Spring Boot can create the corresponding resolver when setting:

~~~properties
spring.mvc.message-codes-resolver-format=PREFIX_ERROR_CODE
~~~

This configures **binding error codes**, not HTTP status codes, nor does it determine what body a JSON response has.

## 9. ViewResolver: When a Controller Returns an HTML View

Not every controller returns JSON. A controller annotated with `@Controller` can return a logical view name:

~~~java
@Controller
class HomeController {

    @GetMapping("/home")
    String home() {
        return "home";
    }
}
~~~

In that case, MVC uses `ViewResolver` to find the corresponding view. Boot can configure:
- `BeanNameViewResolver`: looks up a `View` bean whose name matches the logical view.
- `ContentNegotiatingViewResolver`: coordinates other resolvers and representation negotiation based on the `Accept` header, when conditions are met.
- `InternalResourceViewResolver`: resolves resources/JSPs by prefix/suffix in supported configurations.
- Template engine resolvers such as Thymeleaf or FreeMarker when the starter/template dependency is present.

For example, add the `spring-boot-starter-thymeleaf` dependency, then create `src/main/resources/templates/home.html`:

~~~html
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Home</title></head>
<body><h1>Spring MVC</h1></body>
</html>
~~~

A controller returning `"home"` will be mapped by the Thymeleaf view resolver to the corresponding template while default configuration remains active.

**Important distinction:** `ContentNegotiatingViewResolver` is for **View**-returning mechanisms. A `@RestController` returning a JSON object typically uses `HttpMessageConverter` via a return-value handler, requiring neither a template engine nor a view resolver. Therefore, "having a view resolver" does not fully explain JSON serialization.

To customize views, you can declare an appropriate `ViewResolver` bean or use `WebMvcConfigurer.addViewControllers` for simple routes. Be careful with resolver ordering if multiple view technologies are present.

## 10. Static Resources, WebJars, Favicon, and Welcome Page

Spring Boot auto-configures static resource handling for MVC applications when default mappings are enabled.

Default supported classpath directories include:

~~~text
src/main/resources/static/
src/main/resources/public/
src/main/resources/resources/
src/main/resources/META-INF/resources/
~~~

A file `src/main/resources/static/css/site.css` is typically accessed via `GET /css/site.css`. An `index.html` file in static locations can become the welcome page. Boot also supports an `index` template as a welcome page when no static index exists and an appropriate template engine is present.

Static resources are served through Spring MVC's `ResourceHttpRequestHandler` and resource handler mapping. WebJars follow the `/webjars/**` convention when resources are packaged properly. A `favicon.ico` in static locations is also supported.

You can change the URL of static assets without replacing all of MVC:

~~~yaml
spring:
  mvc:
    static-path-pattern: /assets/**
  web:
    resources:
      static-locations:
        - classpath:/static/
~~~

After this configuration, `static/css/site.css` can be accessed at `/assets/css/site.css`. `static-locations` replaces the default location list; make sure to list all locations you want to use.

To disable automatic static mappings:

~~~properties
spring.web.resources.add-mappings=false
~~~

Do not disable mappings just because `GET /api/unknown` returns 404 without throwing `NoHandlerFoundException`. When the static handler is mapped to `/**`, it can match the URL and then throw `NoResourceFoundException` because no file was found; this behavior differs from failing to find a handler at the outset.

The welcome page is a fallback: real controller mappings, if present, take precedence in handler mapping order before the welcome page. Do not treat `index.html` as an endpoint with higher priority than a controller.

Additionally, `src/main/webapp` is not an appropriate place for static resources across all executable JARs; use the classpath locations supported by Spring Boot.

## 11. Error Handling: Exception Resolvers and /error

In an MVC request, there are two error layers:

**The Spring MVC layer** handles exceptions thrown during handler invocation:
- `HandlerExceptionResolver` is the contract for choosing how to handle an exception.
- `@ExceptionHandler` on a controller or `@ControllerAdvice` handles errors according to Spring Framework rules.
- Spring Framework provides default resolvers for many errors such as malformed bodies, validation failures, or unsupported HTTP methods or media types.

**The Spring Boot layer** adds the Servlet/application error flow:
- `ErrorMvcAutoConfiguration` configures default error handling when conditions are met.
- `BasicErrorController` handles the `/error` mapping.
- `ErrorAttributes` supplies error information according to configuration.
- The Servlet container can dispatch to the corresponding error page when an error is not handled through the normal flow.

By default, error content depends on the client and configuration; machine clients receive an appropriate representation (typically JSON), while browsers may see an HTML error page when no custom view exists. Do not assume every error response always contains a stack trace or exception details; Boot provides `server.error.*` properties to control information disclosure.

Spring Boot 3.3 supports enabling Problem Details per RFC 9457:

~~~properties
spring.mvc.problemdetails.enabled=true
~~~

When enabled, supported MVC errors can use `application/problem+json`. Applications can customize responses through `ProblemDetail` and appropriate exception handling mechanisms.

To change the error structure while keeping Boot's pipeline, you can provide a custom `ErrorAttributes` or `@RestControllerAdvice` for business errors. Only replace `ErrorController` if you genuinely want to own the entire error-handling endpoint.

**Diagnosis:** If a REST endpoint has `@ExceptionHandler` yet error responses go through `/error`, check whether the exception is handled by a resolver, whether the request was error-dispatched by the container, and whether the response had already been committed.

## 12. Multipart, Form Data, and Conditional Validation

If the application has Servlet MVC and appropriate multipart support, `MultipartAutoConfiguration` helps configure multipart handling using properties:

~~~yaml
spring:
  servlet:
    multipart:
      max-file-size: 5MB
      max-request-size: 10MB
~~~

A controller can accept files with `MultipartFile`:

~~~java
@PostMapping(path = "/files", consumes = "multipart/form-data")
String upload(@RequestParam("file") MultipartFile file) {
    return file.getOriginalFilename();
}
~~~

However, the multipart mechanism does not prove the application has enforced all upload security limits. You still need to validate the filename, actual size, format, storage location, access controls, and malicious content if the problem domain requires it.

Validation of bodies or parameters depends on the validation API and library being present. For example, `@Valid` from Jakarta Validation works when a corresponding implementation is available. Do not claim that merely having `spring-boot-starter-web` makes every `@NotBlank` constraint work; typically `spring-boot-starter-validation` is required for Bean Validation.

## 13. CORS, Interceptors, and Filters: Distinguishing Extension Points

Spring MVC supports:
- `@CrossOrigin` on controllers/methods.
- Global CORS via `WebMvcConfigurer.addCorsMappings`.
- `HandlerInterceptor` via `WebMvcConfigurer.addInterceptors`.
- Servlet `Filter` at the Servlet container layer, running before/after `DispatcherServlet` in the filter chain.

Example of global CORS restricted to one origin:

~~~java
@Configuration(proxyBeanMethods = false)
class CorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://frontend.example")
            .allowedMethods("GET", "POST");
    }
}
~~~

This is **application-specific configuration** through an extension point Boot keeps open; Boot does not know your frontend domain automatically and does not generate a CORS policy for all APIs on its own.

An interceptor runs within the MVC flow and is typically used for observability, adding request context, or cross-cutting logic tied to handlers. It does not replace full authentication/authorization from Spring Security. A Servlet `Filter` is appropriate for intervening at the HTTP/Servlet level, such as encoding or the security filter chain.

When adding a `Filter` as a bean in Boot's embedded server, the bean may be registered with the servlet container. If it is already registered via `FilterRegistrationBean` or another mechanism, check to avoid double registration and incorrect filter ordering. In particular, security filters can affect CORS preflight requests; CORS policies must align with security configuration.

## 14. Common MVC Properties

Spring Boot provides many customization points via configuration; below are some examples with clear meaning in a Servlet MVC application:

| Property | Effect |
|---|---|
| `spring.mvc.servlet.path` | Path mapping of `DispatcherServlet` |
| `spring.mvc.static-path-pattern` | URL pattern for serving static resources |
| `spring.web.resources.static-locations` | List of sources containing static resources |
| `spring.web.resources.add-mappings` | Enables/disables default resource mappings |
| `spring.mvc.pathmatch.matching-strategy` | URL matching strategy for controllers |
| `spring.mvc.contentnegotiation.favor-parameter` | Enables media type negotiation via query parameter when configured |
| `spring.mvc.contentnegotiation.parameter-name` | Query parameter name used when `favor-parameter` is enabled |
| `spring.mvc.format.date` / `date-time` | How dates/times are parsed/formatted in MVC |
| `spring.mvc.message-codes-resolver-format` | How binding message codes are formatted |
| `spring.mvc.problemdetails.enabled` | Enables Problem Details for supported MVC error handling |
| `spring.servlet.multipart.max-file-size` | Size limit for a single multipart file |
| `spring.servlet.multipart.max-request-size` | Total size limit for a multipart request |

Be careful to distinguish namespaces:
- `server.*` controls the Servlet container and web server environment.
- `spring.mvc.*` controls most Spring MVC strategies.
- `spring.web.resources.*` controls static resource support.
- `spring.servlet.multipart.*` controls multipart support.
- `spring.jackson.*` and custom Jackson configuration control JSON serialization/deserialization within their respective scopes.

These namespaces are related, but you cannot use a server-level property to replace registering an MVC converter or vice versa.

## 15. Three Levels of Customizing Spring MVC

### Level 1: Adjusting Properties

Examples include changing the static path, date format, error response configuration, or upload limits. This is the least intrusive level and normally preserves auto-configuration.

### Level 2: Adding a WebMvcConfigurer

When you want to add interceptors, converters, formatters, CORS, or view controllers, register a `WebMvcConfigurer` **without** adding `@EnableWebMvc`. Spring MVC and Boot continue managing the baseline configuration; your callbacks contribute to the extension points.

~~~java
@Configuration(proxyBeanMethods = false)
class MyMvcConfig implements WebMvcConfigurer {

    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        registry.addRedirectViewController("/old-home", "/home");
    }
}
~~~

Having a `WebMvcConfigurer` bean does not mean all default MVC beans are removed. In most cases, there is no need to extend `WebMvcConfigurationSupport` or manually declare `RequestMappingHandlerAdapter`.

### Level 3: Replacing Core Components or Taking Over MVC Completely

If you need to replace `RequestMappingHandlerMapping`, `RequestMappingHandlerAdapter`, or `ExceptionHandlerExceptionResolver` while still wanting Boot to continue customizing MVC, consider `WebMvcRegistrations` to supply instances under Boot's contract.

If you want **complete control** over MVC configuration, the application can add `@EnableWebMvc` or a configuration extending `DelegatingWebMvcConfiguration`. In that case, Boot's `WebMvcAutoConfiguration` backs off because its auto-configuration condition is no longer satisfied; you must manually restore desired behaviors such as static resources, message converters, view resolvers, formatters, and other components.

Note: `@EnableWebMvc` does not erase all of Spring Boot and does not disable the embedded web server or unrelated auto-configurations; its main impact is on how Spring MVC is configured. Therefore, if an application is working normally and you only need to add an interceptor, `@EnableWebMvc` is usually overly broad and prone to causing regressions.

## 16. Complete Example: Boot Configures MVC, Application Extends Only Where Needed

Suppose you create a Spring Boot 3.3.x / Java 17+ project with the `spring-boot-starter-web` dependency. In `src/main/java/com/example/demo/MvcAutoConfigurationDemo.java`, place all of the following code. This is **application code running inside a Spring Boot project**, requiring dependencies/framework; it is not a standalone plain Java example to compile directly with `javac`.

~~~java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@SpringBootApplication
public class MvcAutoConfigurationDemo {
    public static void main(String[] args) {
        SpringApplication.run(MvcAutoConfigurationDemo.class, args);
    }
}

record ItemId(long value) {}
record ItemResponse(long id, String name) {}
record CreateItemRequest(String name) {}

@RestController
@RequestMapping("/api/items")
class ItemController {

    @GetMapping(path = "/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public ItemResponse find(@PathVariable ItemId id) {
        return new ItemResponse(id.value(), "Book");
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public ItemResponse create(@RequestBody CreateItemRequest input) {
        return new ItemResponse(10L, input.name());
    }
}

@Configuration(proxyBeanMethods = false)
class CustomMvcConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
            String.class,
            ItemId.class,
            value -> new ItemId(Long.parseLong(value))
        );
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new HandlerInterceptor() {
            @Override
            public boolean preHandle(HttpServletRequest request,
                    HttpServletResponse response, Object handler) {
                response.addHeader("X-MVC-Demo", "enabled");
                return true;
            }
        }).addPathPatterns("/api/**");
    }
}
~~~

**Role of each part:**
- `SpringApplication.run` starts the application; Boot registers `DispatcherServlet` and wires MVC.
- `ItemController` is discovered by component scanning; Spring MVC creates handler mappings for GET/POST.
- `CustomMvcConfiguration` is the application's configuration; `addFormatters` adds a converter from a `String` path variable to `ItemId`.
- `addInterceptors` adds a header to responses for `/api/**` endpoints.
- JSON requests/responses use the Jackson converter supported by Boot when Jackson is on the classpath.
- The example does not use `@EnableWebMvc`, so Boot's MVC auto-configuration remains intact.

Run the application:

~~~bash
./gradlew bootRun
~~~

On Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Test GET:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/api/items/7
~~~

Typical response:

~~~http
HTTP/1.1 200
Content-Type: application/json
X-MVC-Demo: enabled

{"id":7,"name":"Book"}
~~~

Header order, `charset` details, and auxiliary headers may vary by server. The JSON/body structure and `X-MVC-Demo` header are what the example demonstrates.

Test POST:

~~~bash
curl -i -X POST http://localhost:8080/api/items \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"name":"Pen"}'
~~~

Expected body:

~~~json
{"id":10,"name":"Pen"}
~~~

Test type conversion error:

~~~bash
curl -i http://localhost:8080/api/items/not-a-number
~~~

The value `not-a-number` cannot be converted to `long`; Spring MVC will handle the argument conversion error and typically return **400 Bad Request**. The error body content depends on `server.error.*`, Problem Details, and custom exception handlers if configured.

To demonstrate static resource auto-configuration, create `src/main/resources/static/hello.txt` with the content `Static hello` and run:

~~~bash
curl -i http://localhost:8080/hello.txt
~~~

There is no need to create a controller manually to serve this file while default static resource mapping is enabled.

## 17. Adding Tests to Ensure Auto-Configuration Still Works

The project needs an appropriate test dependency, such as `spring-boot-starter-test`. An MVC integration test can verify the configured controller mapping, converter, and interceptor:

~~~java
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
class MvcAutoConfigurationDemoTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void shouldUseConverterControllerAndInterceptor() throws Exception {
        mockMvc.perform(get("/api/items/7"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(7))
            .andExpect(jsonPath("$.name").value("Book"))
            .andExpect(header().string("X-MVC-Demo", "enabled"));
    }
}
~~~

Place the test in `src/test/java/com/example/demo/MvcAutoConfigurationDemoTest.java`. With a Gradle project configured for JUnit Platform, run:

~~~bash
./gradlew test
~~~

A `@WebMvcTest` loads an **MVC slice** instead of the full application context. It is useful when you want to test controllers and MVC components in isolation; `@SpringBootTest` with `@AutoConfigureMockMvc` is suitable when you need to verify broader application wiring. Do not infer from a slice test alone that the entire production server configuration is necessarily identical.

## 18. How to Verify Exactly Which Beans Boot Configured

When a component behaves unexpectedly, inspect in this order:

1. **Dependencies/classpath.** Are `spring-boot-starter-web`, Jackson, validation, and the corresponding template engine present?
2. **WebApplicationType.** Is the application actually running Servlet or Reactive?
3. **Signs of MVC takeover.** Is there `@EnableWebMvc` or a `WebMvcConfigurationSupport` configuration anywhere?
4. **Custom beans.** Has any `HttpMessageConverter`, `ViewResolver`, `ErrorAttributes`, `ConfigurableWebBindingInitializer`, or `WebMvcRegistrations` bean replaced a default?
5. **Properties.** Have `spring.mvc.*`, `spring.web.resources.*`, or `server.*` been modified?
6. **Condition evaluation report.** Check why an auto-configuration was applied or excluded.
7. **Runtime request.** Use curl/MockMvc to confirm HTTP method, URL, content negotiation, response status, headers, and body.

Run Boot with debug enabled to view the condition evaluation:

~~~bash
./gradlew bootRun --args="--debug"
~~~

You can enable more detailed web logging for specific situations:

~~~properties
logging.level.org.springframework.web=DEBUG
~~~

Only enable this log level when diagnosing issues, because request logs can be verbose, especially in high-traffic environments or when sensitive data is present.

If Spring Boot Actuator is present and the beans/conditions/mappings endpoints are enabled, authorized, and exposed appropriately, they can help observe:
- `/actuator/beans`: actual beans in the context.
- `/actuator/conditions`: auto-configuration condition evaluation.
- `/actuator/mappings`: handler mappings.
Do not expose these management endpoints publicly without access control.

## 19. Common Customization Mistakes

1. **Adding `@EnableWebMvc` just to register an interceptor.** This can cause `WebMvcAutoConfiguration` to back off, losing part of Boot's defaults. Use `WebMvcConfigurer` first.
2. **Confusing Spring MVC defaults with Spring Boot auto-configuration.** The framework defines `HandlerMapping` and `HandlerAdapter`; Boot provides conditional wiring and additional behavior.
3. **Replacing all message converters to fix one format.** It is easy to lose default JSON/text converters. Prefer adding a bean or extending the list properly.
4. **Confusing MVC formatters with Jackson.** Parsing path/query parameters and serializing JSON bodies live in two different mechanisms.
5. **Assuming every template engine is available out of the box.** Thymeleaf, FreeMarker, and others only work when the appropriate dependency/configuration is present.
6. **Placing static files in the wrong location.** Classpath `/static` is a common choice for executable JARs; `src/main/webapp` is not suitable for all packaging formats.
7. **Treating every 404 as a `NoHandlerFoundException`.** The static resource handler `/**` may catch the path and throw `NoResourceFoundException`.
8. **Declaring custom error handling while forgetting the `/error` flow.** Exception resolvers and servlet error dispatches serve different cases.
9. **Configuring CORS while forgetting the security filter chain.** Preflight requests may be blocked by the security layer before reaching the controller.
10. **Expecting Boot to implement business logic automatically.** Auto-configuration does not create API routes, domain validation, CORS origins, or authorization rules for the application.

## 20. Takeaways and References

- Spring Boot auto-configures the **Spring MVC environment** based on classpath, application type, properties, and existing beans.
- `DispatcherServlet` is the front controller; `HandlerMapping` selects the handler; `HandlerAdapter` invokes the handler and coordinates binders, converters, and return value handlers.
- `HttpMessageConverter` handles HTTP bodies; MVC `Converter`/`Formatter` handles value binding; `ViewResolver` handles HTML views; resource handlers serve static assets.
- Boot provides support for view resolvers, resources, welcome pages, error controllers, and binding/formatting utilities; each part has its own conditions.
- `WebMvcConfigurer` is the standard way to **extend MVC while keeping Boot defaults**.
- `WebMvcRegistrations` is for cases where you need to replace certain core components while still keeping Boot's configuration system.
- `@EnableWebMvc` is a decision to take full ownership of MVC configuration; you must manually verify the behaviors you want to preserve.
- Verify behavior through dependencies, condition reports, mappings, bean lists, and HTTP tests rather than guessing from annotations.

**Official documentation for further reference:**
- Spring Boot 3.3, [Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): Spring MVC auto-configuration, formatters/converters, view resolvers, static content, error handling, and extending MVC.
- Spring Boot 3.3, [WebMvcAutoConfiguration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/WebMvcAutoConfiguration.html): configuration class and related components.
- Spring Framework, [Web MVC reference](https://docs.spring.io/spring-framework/reference/web/webmvc.html): contracts and mechanics of `DispatcherServlet`, mappings, adapters, and MVC configuration.

Understanding the distinction between **Spring Framework's MVC mechanisms**, **Spring Boot's generated defaults**, and **application-owned configuration** is the foundation for customizing Spring MVC in a controlled way, avoiding replacing an entire pipeline just to add a small feature.
