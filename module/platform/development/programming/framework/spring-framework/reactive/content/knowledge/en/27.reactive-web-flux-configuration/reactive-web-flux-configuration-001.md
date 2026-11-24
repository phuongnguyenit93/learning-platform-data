# @EnableWebFlux, WebFluxConfigurer, and Infrastructure Configuration

## 1. Goals of WebFlux Configuration

Spring WebFlux is Spring's reactive web framework. It supports two ways to build endpoints:

- **Annotated controllers:** using `@RestController`, `@Controller`, `@RequestMapping`, `@GetMapping`, `@PostMapping`, and related annotations.
- **Functional endpoints:** using `RouterFunction`, `RequestPredicate`, `HandlerFunction`, and `ServerResponse` to separate routing from handlers.

When a request enters the application, WebFlux must find the matching handler, convert the request into Java arguments, invoke the handler, and then encode the result into an HTTP response. WebFlux configuration determines which infrastructure components participate in that pipeline and how they behave.

There are three concepts to distinguish:

1. `@EnableWebFlux` enables Spring WebFlux Java configuration in a self-configured application.
2. `WebFluxConfigurer` provides callbacks to customize specific parts of WebFlux configuration.
3. Spring Boot WebFlux auto-configuration automatically registers default configuration and additionally integrates codecs, static resources, the server, and other Boot features.

In a typical Spring Boot application, the key choice is to use `WebFluxConfigurer` without adding `@EnableWebFlux` in order to preserve the customizations provided by Boot. Only use `@EnableWebFlux` when you want to take full responsibility for WebFlux configuration.

## 2. How Do @EnableWebFlux and WebFluxConfigurer Differ?

### 2.1. @EnableWebFlux

In a Spring Framework application without Spring Boot, WebFlux can be enabled with:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.EnableWebFlux;

@Configuration
@EnableWebFlux
public class WebConfig {
}
~~~

`@EnableWebFlux` imports `DelegatingWebFluxConfiguration`. This configuration registers the default WebFlux infrastructure and detects beans implementing `WebFluxConfigurer` to apply customization callbacks.

The configured infrastructure supports annotated controllers and functional endpoints, and also registers required components based on dependencies present on the classpath, such as JSON or XML codecs.

### 2.2. WebFluxConfigurer

`WebFluxConfigurer` is a callback interface. Its methods have default implementations, so you only need to override the parts you want to customize:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class WebConfig implements WebFluxConfigurer {

    // Override only the configuration hooks that are needed.
}
~~~

`WebFluxConfigurer` does not create the entire infrastructure by itself if the application has not enabled WebFlux configuration. With Spring Boot, auto-configuration already handles that part.

### 2.3. Important Rule When Using Spring Boot

In Spring Boot, write:

~~~java
@Configuration(proxyBeanMethods = false)
public class WebConfig implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
        ServerCodecConfigurer configurer
    ) {
        configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024);
    }
}
~~~

Do not add `@EnableWebFlux` to the configuration above if you want to keep Boot's auto-configured WebFlux features. Boot provides configuration for codecs, static resources, and other infrastructure components. When `@EnableWebFlux` is enabled, Boot's WebFlux configuration backs off in favor of application-controlled configuration.

Decision table:

| Environment | Common Configuration Approach |
| --- | --- |
| Plain Spring Framework, self-built application context | `@EnableWebFlux` and optional `WebFluxConfigurer` |
| Spring Boot WebFlux, only a few customizations needed | `WebFluxConfigurer`, without `@EnableWebFlux` |
| Spring Boot WebFlux, want full control over all infrastructure | `@EnableWebFlux` and take responsibility for all configuration parts |
| Need to replace deep infrastructure beans that callbacks do not cover | Advanced mode with `DelegatingWebFluxConfiguration` |

### 2.4. When to Use DelegatingWebFluxConfiguration?

Spring Framework allows extending `DelegatingWebFluxConfiguration` directly when you need to override bean declarations of the base configuration:

~~~java
@Configuration
public class AdvancedWebConfig
        extends DelegatingWebFluxConfiguration {

    // Override selected infrastructure bean declarations here.
}
~~~

This is an advanced option. It requires a solid understanding of the lifecycle and relationships between WebFlux infrastructure beans. In a typical Boot application, prefer `WebFluxConfigurer` callbacks and Boot's own extension points before replacing the base configuration.

## 3. Request Processing Lifecycle and Infrastructure Beans

### 3.1. How Does a Request Flow Through WebFlux?

`HttpHandler` is the server-level abstraction for handling HTTP requests and responses. Embedded server adapters bridge requests from Reactor Netty, Tomcat, or Jetty into Spring's HTTP model.

`DispatcherHandler` is the front controller of WebFlux. It coordinates the following components:

- `HandlerMapping` finds the handler matching the request.
- `HandlerAdapter` invokes the handler according to its handler type.
- `HandlerResultHandler` processes the return value and writes the response.
- `WebExceptionHandler` handles exceptions raised during request processing.
- `HttpMessageReader` reads and decodes the request body.
- `HttpMessageWriter` encodes and writes the response body.

~~~text
Client
  |
  v
Reactive Web Server
(Reactor Netty / Tomcat / Jetty)
  |
  v
HttpHandler
  |
  v
WebFilter chain
  |
  v
DispatcherHandler
  |
  +--> HandlerMapping
  |       |
  |       v
  |    Handler
  |
  +--> HandlerAdapter
  |       |
  |       v
  |    Mono / Flux / result
  |
  +--> HandlerResultHandler
  |       |
  |       v
  |    HttpMessageWriter / View
  |
  +--> WebExceptionHandler (error path)
  |
  v
HTTP Response
~~~

### 3.2. HandlerMapping

`HandlerMapping` maps a request to a handler. WebFlux can use multiple mapping types, for example:

- `RequestMappingHandlerMapping` finds methods in `@Controller` or `@RestController`.
- `RouterFunctionMapping` finds routes declared with `RouterFunction`.
- Resource handler mapping serves static resources.
- Other mappings can be added for WebSocket or specialized integrations.

The order among HandlerMappings matters when multiple mappings can handle the same URL. Avoid creating overlapping routes without clear precedence rules.

### 3.3. HandlerAdapter and HandlerResultHandler

`HandlerAdapter` knows how to invoke a specific kind of handler. For example, the adapter for annotated controllers understands how to bind path variables, request parameters, headers, bodies, and validation.

`HandlerResultHandler` knows how to write the result. The result can be:

- `ResponseEntity<T>` or `Mono<ResponseEntity<T>>`.
- `@ResponseBody` or an object to be serialized.
- `Flux<T>` for response streaming.
- `Rendering` or a view name for HTML.
- `ServerResponse` from functional endpoints.

### 3.4. Codecs and ReactiveAdapterRegistry

`ReactiveAdapterRegistry` allows WebFlux to work with different reactive abstractions. Codecs convert between byte streams and Java objects.

`ServerCodecConfigurer` manages default readers/writers and custom codecs. The appropriate codec is selected based on data type, media type, and dependencies on the classpath.

### 3.5. WebFilter and WebExceptionHandler

`WebFilter` intercepts the HTTP exchange before/after the handler. It fits cross-cutting concerns such as security, correlation ID, request logging, and header checks.

`WebExceptionHandler` handles errors at the WebFlux layer. In Spring Boot, auto-configured error handling usually provides an appropriate error response already. It can be extended via Error Attributes, Problem Details, or a custom handler when needed.

Note: `WebFluxConfigurer` customizes infrastructure configuration; `WebFilter` participates in each request/response exchange. The two mechanisms serve different roles.

## 4. Important Callbacks of WebFluxConfigurer

Common callback methods in Spring Framework 6.2:

| Callback | Purpose |
| --- | --- |
| `configureHttpMessageCodecs` | Add or customize readers/writers for request and response bodies |
| `addFormatters` | Register Converters and Formatters for binding |
| `getValidator` | Provide a global Validator |
| `getMessageCodesResolver` | Customize message codes for data binding |
| `addCorsMappings` | Configure global CORS |
| `configureContentTypeResolver` | Customize how media type is resolved from the request |
| `configurePathMatching` | Customize path matching rules |
| `configureArgumentResolvers` | Add resolvers for custom controller parameters |
| `configureViewResolvers` | Configure view resolvers |
| `addResourceHandlers` | Register static resource handlers |
| `configureBlockingExecution` | Configure an executor for controller methods identified as blocking |
| `getWebSocketService` | Customize the WebSocket handshake service |
| `addErrorResponseInterceptors` | Add interceptors for RFC 9457 Problem Details |

These callbacks have default implementations. Only override what the application truly needs.

`configureApiVersioning` belongs to Spring Framework 7.0; do not include that method in Spring Boot 3.5.x sample code that uses Spring Framework 6.2.

## 5. Configuring HTTP Message Codecs

### 5.1. What Do Codecs Do?

WebFlux uses:

- `HttpMessageReader` to read the request body and decode it into a Java object.
- `HttpMessageWriter` to encode a Java object and write the response body.

For example, a request has `Content-Type: application/json` and a JSON body. The Jackson decoder can convert JSON into a record or DTO. When returning an object with `produces = application/json`, the Jackson encoder converts the object into a JSON response.

### 5.2. Limiting In-Memory Size When Decoding

Some codecs need to aggregate data into memory before creating an object. You can limit the size using `ServerCodecConfigurer`:

~~~java
@Configuration(proxyBeanMethods = false)
public class CodecConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
        ServerCodecConfigurer configurer
    ) {
        configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024);
    }
}
~~~

The example sets a 2 MiB limit for default codecs that perform aggregation.

This limit helps prevent some large request bodies from causing unexpected memory growth. It is not a general size limit for all streaming uploads or all data passing through the server. Large files should be processed in streams/chunks with dedicated limit policies at the business, server, or gateway layer.

### 5.3. Adding or Replacing Codecs

`ServerCodecConfigurer` allows:

- Registering custom readers/writers.
- Customizing default codecs.
- Replacing the default codec set.
- Registering codecs only for a specific media type or data type.

Example illustrating adding a codec:

~~~java
@Override
public void configureHttpMessageCodecs(
    ServerCodecConfigurer configurer
) {
    configurer.customCodecs().register(new MyCustomHttpMessageReader());
    configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024);
}
~~~

`MyCustomHttpMessageReader` is an application-provided implementation; this snippet is an extension point example, not a built-in Spring class.

Do not call `registerDefaults(false)` if the goal is only to add a codec. That call disables the default codecs and forces the application to re-register the required readers/writers itself.

### 5.4. CodecCustomizer in Spring Boot

Spring Boot provides `CodecCustomizer` to customize auto-configured codecs:

~~~java
@Bean
CodecCustomizer applicationCodecCustomizer() {
    return configurer ->
        configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024);
}
~~~

Choose one configuration approach that fits your application structure. `WebFluxConfigurer.configureHttpMessageCodecs` is Spring Framework's extension point; `CodecCustomizer` is Boot's extension point.

## 6. Conversion, Formatter, and Validation

### 6.1. Conversion and Formatting

WebFlux needs to convert Strings from path variables, query parameters, or form fields into Java types. `Converter` converts one type to another; `Formatter` supports parsing/printing according to format and locale.

Example setting ISO date/time format:

~~~java
@Configuration
public class FormattingConfiguration implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        DateTimeFormatterRegistrar registrar =
            new DateTimeFormatterRegistrar();

        registrar.setUseIsoFormat(true);
        registrar.registerFormatters(registry);
    }
}
~~~

Spring WebFlux also supports annotations such as `@DateTimeFormat`, `@NumberFormat`, and `@DurationFormat` on appropriate fields or parameters.

### 6.2. Global Validator and Local Validator

If Bean Validation is on the classpath, WebFlux can register a default validator for `@Valid` and `@Validated` on controller parameters.

You can provide a global validator via `getValidator()`:

~~~java
@Override
public Validator getValidator() {
    return customValidator;
}
~~~

`customValidator` is an application-managed bean. If only one controller or one request needs custom rules, using `@InitBinder` to register a local validator is usually clearer.

Do not override the default validator just to change a single rule if it can be handled in the DTO or controller.

### 6.3. MessageCodesResolver

`MessageCodesResolver` determines the error message codes generated for data binding/validation. Customize it when the application needs custom error code conventions to map to localized messages or an API error contract.

## 7. Configuring CORS

### 7.1. What Is CORS?

CORS (Cross-Origin Resource Sharing) is a browser mechanism used to control JavaScript access to resources at another origin. An origin consists of scheme, host, and port.

WebFlux supports CORS at the `HandlerMapping` layer. When a request is mapped to a handler, HandlerMapping checks the CORS configuration. Preflight requests can be handled directly before the controller runs.

### 7.2. Global CORS with CorsRegistry

~~~java
@Configuration
public class CorsConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://frontend.example.com")
            .allowedMethods("GET", "POST", "PUT", "DELETE")
            .allowedHeaders("Content-Type", "Authorization", "X-Request-Id")
            .exposedHeaders("X-Request-Id")
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~

Meaning:

- `addMapping` specifies the URL pattern to apply.
- `allowedOrigins` restricts which origins are allowed to call.
- `allowedMethods` lists the allowed HTTP methods.
- `allowedHeaders` allows the specified request headers.
- `exposedHeaders` allows JavaScript to read the listed response headers.
- `allowCredentials` allows requests with credentials when security policy permits.
- `maxAge` is how long the browser can cache the preflight result.

When credentials are enabled, do not use `allowedOrigins("*")`. Configure explicit origins or `allowedOriginPatterns` matching security requirements.

### 7.3. Controller-Level CORS

You can use `@CrossOrigin` on a controller or method:

~~~java
@CrossOrigin(origins = "https://frontend.example.com")
@RestController
@RequestMapping("/reports")
public class ReportController {
}
~~~

Global and local configurations can be combined. If you need a consistent policy for the whole API, use global mapping; if only one endpoint has a clear exception, use the annotation on the handler.

### 7.4. CorsWebFilter and Spring Security

`CorsWebFilter` is another option, especially well suited for functional endpoints. If the application uses Spring Security, integrate CORS using the mechanism supported by Spring Security to avoid configuring it in two places, which can cause duplicate headers or wrong filter ordering.

Do not enable multiple CORS mechanisms on the same route at the same time unless intentionally designed.

## 8. Static Resources and Caching

### 8.1. Default Static Resource Locations

Spring Boot WebFlux typically serves static resources from classpath locations such as:

- `/static`
- `/public`
- `/resources`
- `/META-INF/resources`

For example, the file `src/main/resources/static/index.html` can be served as static content under the default configuration.

### 8.2. Changing URL Mappings and Resource Locations

Use `addResourceHandlers` when you need custom static resource routes:

~~~java
@Override
public void addResourceHandlers(ResourceHandlerRegistry registry) {
    registry.addResourceHandler("/assets/**")
        .addResourceLocations("classpath:/static/assets/")
        .setCacheControl(CacheControl.maxAge(7, TimeUnit.DAYS));
}
~~~

A request to `/assets/logo.svg` will look up the corresponding file in the declared classpath directory.

### 8.3. Caching and Versioning

Resource handlers support:

- Cache-Control and Last-Modified.
- `ResourceResolver` to locate resources.
- `ResourceTransformer` to transform resources.
- `VersionResourceResolver` to generate URLs with versions or content hashes.

When using versioned assets, browsers can cache them for a long time because the URL changes when content changes. Choose a caching policy that fits your frontend build/deploy workflow.

### 8.4. Configuring via Spring Boot Properties

You can change the static path pattern with:

~~~properties
spring.webflux.static-path-pattern=/resources/**
~~~

And change resource locations with:

~~~properties
spring.web.resources.static-locations=classpath:/public/,classpath:/assets/
~~~

When replacing the locations list, the new value replaces the default list. If the directory containing the welcome page is no longer included, the default index page may not be discovered as before.

## 9. Content Negotiation and ViewResolver

### 9.1. Content Negotiation

WebFlux decides the response media type based on the requested content type resolver. By default, the `Accept` header is the primary source.

You can customize it via `configureContentTypeResolver` if the application has special media type rules, such as query parameters or an internal strategy. Avoid adding multiple format selection mechanisms unless there is a clear compatibility requirement.

### 9.2. ViewResolver

If WebFlux renders HTML templates instead of returning only JSON, `ViewResolverRegistry` is used to register view technologies such as FreeMarker or a custom ViewResolver.

Example:

~~~java
@Override
public void configureViewResolvers(ViewResolverRegistry registry) {
    registry.freeMarker();
}
~~~

To run, the project needs the corresponding FreeMarker dependency and configuration. The example above only registers the view resolver; it does not create the template engine or template files.

You can register default views based on `HttpMessageWriterView` to render other formats such as JSON/XML through codecs. For pure JSON REST APIs, configuring a view resolver is usually unnecessary.

## 10. Path Matching and Custom Argument Resolvers

### 10.1. PathMatchConfigurer

`configurePathMatching` customizes how URLs are mapped to annotated controllers. For example, adding the `/api` prefix for controllers annotated with `@RestController`:

~~~java
@Override
public void configurePathMatching(PathMatchConfigurer configurer) {
    configurer.addPathPrefix(
        "/api",
        HandlerTypePredicate.forAnnotation(RestController.class)
    );
}
~~~

If a controller has `@RequestMapping("/orders")`, the actual route will have the prefix `/api/orders`.

This prefix is applied based on the predicate. Choose a sufficiently narrow predicate if the application has controllers for health, admin, or internal routes that need different paths.

WebFlux uses a parsed `RequestPath` to handle path segments and matrix variables. WebFlux's path handling is not identical to Spring MVC; do not mechanically copy path matching settings from MVC.

### 10.2. Custom Argument Resolvers

`configureArgumentResolvers` lets you add resolvers for custom controller parameter types:

~~~java
@Override
public void configureArgumentResolvers(
    ArgumentResolverConfigurer configurer
) {
    configurer.addCustomResolver(new CurrentTenantArgumentResolver());
}
~~~

`CurrentTenantArgumentResolver` is an application-implemented class extending/implementing `HandlerMethodArgumentResolver`. The resolver can read headers, security context, or the request exchange to construct a domain object for the controller parameter.

Only add a custom resolver when a parameter type is genuinely used widely. For a few endpoints, reading a header or using built-in argument annotations is usually simpler.

## 11. Blocking Execution, WebSocket, and Error Responses

### 11.1. BlockingExecutionConfigurer

Spring Framework 6.1+ allows configuring an executor for controller methods identified as blocking via `configureBlockingExecution`.

This mechanism helps isolate certain blocking methods from the main reactive processing threads. It does not turn blocking code into non-blocking code and is not a reason to call `block()` in a pipeline. For blocking I/O, prefer reactive APIs or isolate the blocking work on an appropriate scheduler/executor.

### 11.2. WebSocketService

`getWebSocketService` allows providing a custom WebSocket service. One use case is configuring a server-specific request upgrade strategy or idle timeout for the WebSocket handshake.

If the application only uses HTTP REST and SSE, overriding this method is usually unnecessary.

### 11.3. ErrorResponse Interceptors

Spring Framework 6.2 added the `addErrorResponseInterceptors` callback to add interceptors when rendering error responses according to RFC 9457 Problem Details.

It can be used to attach common metadata such as error code, trace ID, or standardized extension properties. Do not expose stack traces, secrets, or sensitive internal data in client responses.

### 11.4. Boot Error Handling

Spring Boot WebFlux has an auto-configured `WebExceptionHandler`. You can extend error responses via Error Attributes, Problem Details, or `ErrorWebExceptionHandler` when deeper control is required.

Before writing a low-level handler yourself, check whether `@ExceptionHandler`, `@ControllerAdvice`, or Problem Details already covers the use case.

## 12. Spring Boot-Specific Extension Points

### 12.1. WebFluxAutoConfiguration

Spring Boot provides `WebFluxAutoConfiguration` when the application runs with the reactive web application type and WebFlux is on the classpath.

Auto-configuration typically adds:

- Codec defaults for `HttpMessageReader` and `HttpMessageWriter`.
- Static resources and WebJars.
- Error handling.
- Embedded reactive server configuration.
- Other Boot integrations.

Boot uses bean conditions to avoid creating the base WebFlux configuration when the application already supplies an alternative configuration. That is why adding `@EnableWebFlux` can cause Boot's auto-configured features to stop being applied in the default way.

### 12.2. CodecCustomizer

Use `CodecCustomizer` if you want to configure codecs using Boot's mechanism:

~~~java
@Bean
CodecCustomizer codecCustomizer() {
    return configurer ->
        configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024);
}
~~~

### 12.3. WebHttpHandlerBuilderCustomizer

If you need to adjust the `HttpHandler` auto-configured by Boot, you can declare a `WebHttpHandlerBuilderCustomizer` bean. This is a lower-level extension point than WebFluxConfigurer, used for HTTP exchange processing components that WebFluxConfigurer callbacks do not cover.

Do not use a low-level customizer to replace a simple setting that already has a corresponding callback.

### 12.4. Reactive Web Server

Spring Boot supports embedded reactive servers such as Reactor Netty, Tomcat, and Jetty. Common properties can be configured in `application.properties`:

~~~properties
server.port=8080
server.address=0.0.0.0
~~~

Server-specific settings such as SSL, compression, or Netty-specific settings belong to the corresponding server namespace. If programmatic customization is needed, use `WebServerFactoryCustomizer` with `ConfigurableReactiveWebServerFactory` or a specialized factory.

### 12.5. Avoid Confusing WebFlux with WebClient

`spring-boot-starter-webflux` can be added to a Spring MVC application just to use `WebClient`. If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Spring Boot defaults to Spring MVC as the server application type.

To run a reactive server, ensure the application type is REACTIVE and the appropriate dependencies/server are present. Having WebClient on the classpath does not mean the application is running a WebFlux server.

## 13. WebFluxConfigurer, WebFilter, and Spring Security

| Mechanism | Scope | Example |
| --- | --- | --- |
| `WebFluxConfigurer` | Customize infrastructure and mapping/codec policies | CORS, codecs, resource handlers, path prefix |
| `WebFilter` | Wrap each HTTP exchange | Correlation ID, security, logging, request timing |
| `@ControllerAdvice` | Error handling and binding at the controller layer | Map exceptions to API responses |
| `WebExceptionHandler` | Error handling at the WebFlux layer | Global error handling outside controllers |

`WebFilter` can be declared as a bean and automatically joins the filter chain. When filter order matters, use `Ordered` or `@Order`.

If Spring Security is used, Security's filter chain is also part of request processing. CORS, authentication, and authorization configurations must be consistent between WebFlux and Security to avoid double processing or missing preflight requests.

## 14. Complete Spring Boot 3.5.7 + Java 17 Example

The example creates a greeting API to demonstrate:

- `WebFluxConfigurer` customizing codecs and the in-memory limit.
- CORS for a specific frontend origin.
- `/api` path prefix for controllers.
- Static resource mapping.
- `WebTestClient` testing the route prefix and CORS preflight.

The example uses Spring Boot 3.5.7 and Java 17. The main configuration does not attach `@EnableWebFlux` in order to preserve Boot auto-configuration.

### 14.1. Project Structure

~~~text
webflux-config-demo/
├── pom.xml
├── src/main/resources/
│   ├── application.properties
│   └── static/assets/
│       └── app.css
├── src/main/java/example/config/
│   ├── WebFluxConfigApplication.java
│   ├── ApiWebConfiguration.java
│   ├── GreetingController.java
│   └── GreetingRequest.java
└── src/test/java/example/config/
    └── GreetingControllerTest.java
~~~

### 14.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-config-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
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
~~~

### 14.3. application.properties

~~~properties
server.port=8080
spring.http.codecs.max-in-memory-size=2MB
~~~

### 14.4. WebFluxConfigApplication.java

~~~java
package example.config;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxConfigApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFluxConfigApplication.class, args);
    }
}
~~~

### 14.5. ApiWebConfiguration.java

~~~java
package example.config;

import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.method.HandlerTypePredicate;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.PathMatchConfigurer;
import org.springframework.web.reactive.config.ResourceHandlerRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class ApiWebConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
        ServerCodecConfigurer configurer
    ) {
        configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024);
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://frontend.example.com")
            .allowedMethods("GET", "POST")
            .allowedHeaders("Content-Type", "X-Request-Id")
            .exposedHeaders("X-Request-Id")
            .allowCredentials(true)
            .maxAge(3600);
    }

    @Override
    public void configurePathMatching(PathMatchConfigurer configurer) {
        configurer.addPathPrefix(
            "/api",
            HandlerTypePredicate.forAnnotation(RestController.class)
        );
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
            .addResourceLocations("classpath:/static/assets/")
            .setCacheControl(CacheControl.maxAge(7, TimeUnit.DAYS));
    }
}
~~~

Explanation:

- Default codecs have a 2 MiB in-memory aggregation limit.
- CORS only allows the declared frontend origin, with GET and POST.
- All controllers with `@RestController` receive the `/api` prefix.
- Static assets in `classpath:/static/assets/` are served under `/assets/**` with a 7-day Cache-Control.

If you do not want the prefix applied to every RestController, replace the predicate with a narrower one, such as a package or custom annotation.

### 14.6. GreetingRequest.java

~~~java
package example.config;

import jakarta.validation.constraints.NotBlank;

public record GreetingRequest(
    @NotBlank String name
) {
}
~~~

### 14.7. GreetingController.java

~~~java
package example.config;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/greetings")
public class GreetingController {

    public record Greeting(
        String message,
        String requestId
    ) {
    }

    @GetMapping("/{name}")
    public Mono<Greeting> getGreeting(
        @PathVariable String name,
        @RequestHeader(
            value = "X-Request-Id",
            required = false
        ) String requestId
    ) {
        return Mono.just(new Greeting(
            "Hello, " + name,
            requestId
        ));
    }

    @PostMapping
    @org.springframework.web.bind.annotation.ResponseStatus(
        HttpStatus.CREATED
    )
    public Mono<Greeting> createGreeting(
        @Valid @RequestBody GreetingRequest request,
        @RequestHeader(
            value = "X-Request-Id",
            required = false
        ) String requestId
    ) {
        return Mono.just(new Greeting(
            "Hello, " + request.name(),
            requestId
        ));
    }
}
~~~

Because the configuration adds the `/api` prefix, the actual URLs are:

- `GET /api/greetings/{name}`
- `POST /api/greetings`

### 14.8. app.css

~~~css
body {
    font-family: sans-serif;
    margin: 2rem;
}
~~~

This file can be accessed at `/assets/app.css`.

### 14.9. GreetingControllerTest.java

~~~java
package example.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class GreetingControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void routePrefixAndCorsHeadersAreApplied() {
        client.get()
            .uri("/api/greetings/Linh")
            .header("Origin", "https://frontend.example.com")
            .header("X-Request-Id", "req-42")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .valueEquals(
                "Access-Control-Allow-Origin",
                "https://frontend.example.com"
            )
            .expectBody()
            .jsonPath("$.message").isEqualTo("Hello, Linh")
            .jsonPath("$.requestId").isEqualTo("req-42");
    }

    @Test
    void corsPreflightIsAccepted() {
        client.options()
            .uri("/api/greetings/Linh")
            .header("Origin", "https://frontend.example.com")
            .header("Access-Control-Request-Method", "GET")
            .header("Access-Control-Request-Headers", "X-Request-Id")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .valueEquals(
                "Access-Control-Allow-Origin",
                "https://frontend.example.com"
            )
            .expectHeader()
            .exists("Access-Control-Allow-Methods");
    }
}
~~~

The first test verifies the route prefix, JSON response, and CORS response header. The second test sends an OPTIONS preflight request to verify the CORS policy before the browser sends the actual request.

### 14.10. Running the Application and Tests

Requires JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

Call the API:

~~~bash
curl -i http://localhost:8080/api/greetings/Linh
~~~

Expected response body:

~~~json
{
  "message": "Hello, Linh",
  "requestId": null
}
~~~

Call with a request ID:

~~~bash
curl -i \
  -H "X-Request-Id: req-42" \
  http://localhost:8080/api/greetings/Linh
~~~

Expected response body:

~~~json
{
  "message": "Hello, Linh",
  "requestId": "req-42"
}
~~~

Run tests:

~~~bash
mvn test
~~~

The two tests verify route and CORS configuration at the HTTP integration level. The tests do not merely check that the controller method is called, but go through the application's WebFlux infrastructure.

## 15. Testing WebFlux Configuration

### 15.1. @WebFluxTest

`@WebFluxTest` is suitable for testing a WebFlux slice, such as controllers, controller advice, converters, formatters, and `WebFluxConfigurer`.

Example:

~~~java
@WebFluxTest(GreetingController.class)
@Import(ApiWebConfiguration.class)
class GreetingSliceTest {
    @Autowired
    WebTestClient client;
}
~~~

A slice test initializes a portion of the WebFlux infrastructure and limits which beans are scanned. If the controller depends on services, use mock beans or import the required components.

### 15.2. @SpringBootTest and WebTestClient

`@SpringBootTest(webEnvironment = RANDOM_PORT)` tests the application inside a real embedded server. It is suitable for verifying:

- Route prefixes and path matching.
- CORS preflight and actual requests.
- Codec serialization/deserialization.
- Static resource mapping.
- Security filter chain and WebFilter order.
- Integrated error handling.

### 15.3. Testing Each Configuration Meaningfully

Do not test only status 200. For infrastructure configuration, verify the behavior that the configuration is meant to guarantee:

- Codec: payload matches media type, exceeding the aggregation limit produces an appropriate error response.
- CORS: allowed origins and disallowed origins.
- Path matching: prefixed URLs work and old URLs are not mapped by mistake.
- Static resource: valid URL returns the file and expected Cache-Control.
- Validation: invalid input returns an API error matching the contract.
- Error handler: exceptions are mapped to the expected status and Problem Details.

## 16. Common Pitfalls and Fixes

**Pitfall 1 — Adding @EnableWebFlux to a Boot app just to add CORS.** Boot auto-configuration may back off and other default configurations may be lost. Implement WebFluxConfigurer without adding the annotation.

**Pitfall 2 — Thinking WebFluxConfigurer enables WebFlux by itself.** This interface only provides callbacks. A plain Spring app needs @EnableWebFlux; Boot WebFlux already has auto-configuration.

**Pitfall 3 — Confusing WebFluxConfigurer with WebMvcConfigurer.** Importing the servlet package by mistake prevents WebFlux from invoking the callbacks. Check the org.springframework.web.reactive.config package.

**Pitfall 4 — Adding both spring-boot-starter-web and spring-boot-starter-webflux and assuming the server runs reactive.** Boot defaults to MVC. Explicitly verify the application type and server stack.

**Pitfall 5 — Replacing all default codecs when only wanting to add one.** This can drop JSON, String, form, or resource readers/writers. Only disable registerDefaults(false) when intentionally registering all needed codecs yourself.

**Pitfall 6 — Setting maxInMemorySize too high.** Many concurrent requests can create memory pressure. Choose a limit based on real payloads and stream large files.

**Pitfall 7 — Assuming maxInMemorySize is an overall upload limit.** It applies to codec operations that aggregate in memory; streaming uploads and overall request limits need separate policies.

**Pitfall 8 — Using a wildcard origin with CORS credentials.** Browsers reject allow-origin wildcard configurations when allow-credentials is enabled. Declare explicit origins or appropriate origin patterns.

**Pitfall 9 — Configuring CORS at multiple layers.** CorsWebFilter, HandlerMapping, and Spring Security can produce overlapping policies/headers. Choose one primary mechanism and integrate Security in the proper order.

**Pitfall 10 — Testing only actual GET requests without testing preflight.** Browsers may send OPTIONS before the actual request. Write OPTIONS tests with Origin, Access-Control-Request-Method, and Access-Control-Request-Headers.

**Pitfall 11 — Static resources not found after changing static-locations.** The new list replaces the defaults. Check classpath paths and URL mappings.

**Pitfall 12 — Applying a path prefix too broadly.** All controllers matching the predicate may receive the prefix. Use a sufficiently narrow annotation/package predicate.

**Pitfall 13 — Custom argument resolver replacing default resolvers.** Only add custom resolvers via ArgumentResolverConfigurer; do not rebuild the entire resolver list yourself without reason.

**Pitfall 14 — Using configureBlockingExecution to justify blocking code.** The dedicated executor only isolates certain controller methods identified as blocking. Prefer non-blocking APIs and do not block the event loop.

**Pitfall 15 — Configuring ViewResolver without a template engine.** Registering a resolver does not automatically add the dependency or template loader. Check dependencies and template locations.

**Pitfall 16 — Creating WebFluxConfigurationSupport manually when Boot already auto-configures.** This can create duplicate configurations or cause auto-configuration to back off. Only use advanced mode when you clearly understand the bean graph.

**Pitfall 17 — Using WebFluxConfigurer to configure port/TLS/Netty.** Those belong to server properties or WebServerFactoryCustomizer.

**Pitfall 18 — Using WebFluxConfigurer to write per-request logging.** Use WebFilter for HTTP exchanges; keep WebFluxConfigurer for infrastructure configuration.

**Pitfall 19 — Configuring a path prefix but testing the old URL.** The actual route has changed. Check HandlerTypePredicate and the generated URL after the prefix is applied.

**Pitfall 20 — Running only controller unit tests and concluding CORS/codecs are correct.** Use WebTestClient with real infrastructure or an appropriate WebFlux test slice.

## 17. Checklist Before Deploying WebFlux Configuration to Production

1. Is the application running the right WebApplicationType: REACTIVE or SERVLET?
2. Are both starter-web and starter-webflux present at the same time?
3. If using Spring Boot, is @EnableWebFlux truly necessary?
4. Do WebFluxConfigurer implementations override only the required callbacks?
5. Do codecs have appropriate default readers/writers and a reasonable memory limit?
6. Does CORS have the required origins, methods, headers, and credentials?
7. Is CORS preflight tested?
8. Are static resource locations, URL mappings, and cache policies correct?
9. Is the path prefix applied to the right controller predicate?
10. Are custom argument resolvers added without losing default resolvers?
11. Are blocking controller methods isolated from the event loop?
12. Are WebFilter and Spring Security ordered properly?
13. Do error responses follow the API contract and avoid leaking internal data?
14. Are a WebSocket service or server-specific customizers needed?
15. Are there integration tests for routes, CORS, codecs, static resources, and error handling?
16. Are Boot property settings unintentionally overridden by custom beans?

## 18. Self-Check Exercises

1. What does `@EnableWebFlux` do? **Imports default WebFlux infrastructure configuration via DelegatingWebFluxConfiguration.**
2. What is `WebFluxConfigurer`? **A callback interface for customizing parts of WebFlux configuration.**
3. In Spring Boot, when only needing to increase max in-memory size, which approach should be used? **Implement WebFluxConfigurer without adding @EnableWebFlux, or use CodecCustomizer / the appropriate property.**
4. Why can @EnableWebFlux cause some Boot defaults to be lost? **WebFlux auto-configuration backs off when the application supplies WebFluxConfigurationSupport itself.**
5. What does HandlerMapping do? **Finds the handler matching the request.**
6. What does HandlerAdapter do? **Invokes the corresponding handler.**
7. What does HandlerResultHandler do? **Processes the return value and writes the response.**
8. How do HttpMessageReader and HttpMessageWriter differ? **Reader decodes the request; Writer encodes the response.**
9. Which callback configures codecs? **configureHttpMessageCodecs.**
10. Which callback registers global CORS? **addCorsMappings.**
11. Which callback adds static resource mappings? **addResourceHandlers.**
12. Which callback adds a prefix for controllers? **configurePathMatching.**
13. Why shouldn't CORS credentials use a wildcard origin? **Browsers reject a wildcard origin together with Access-Control-Allow-Credentials true.**
14. Is maxInMemorySize an overall upload limit? **No; it limits codec operations that require aggregating into memory.**
15. How does WebFilter differ from WebFluxConfigurer? **WebFilter participates in each HTTP exchange; WebFluxConfigurer customizes infrastructure.**
16. Why shouldn't you block the event loop? **It slows down many requests sharing the event-loop thread.**
17. Which server does WebFlux Boot choose by default? **Depends on reactive server dependencies; Reactor Netty is typically the default when the corresponding starter is present.**
18. When should WebHttpHandlerBuilderCustomizer be used? **When needing to customize the auto-configured HttpHandler at a lower level than WebFluxConfigurer.**

## 19. Key Takeaways and References

- `@EnableWebFlux` imports `DelegatingWebFluxConfiguration` and enables WebFlux infrastructure configuration.
- `WebFluxConfigurer` allows customizing codecs, CORS, conversion, validation, path matching, static resources, views, and blocking execution.
- In Spring Boot, implement `WebFluxConfigurer` without adding `@EnableWebFlux` to preserve auto-configuration when only adding customizations.
- `DispatcherHandler` coordinates HandlerMapping, HandlerAdapter, and HandlerResultHandler to process requests.
- Codec readers decode requests; codec writers encode responses. Set an appropriate in-memory aggregation limit.
- CORS needs explicit origins/methods/headers; credentials must not be paired with wildcard origins.
- Static resources can be mapped via ResourceHandlerRegistry or Boot properties.
- WebFilter processes each HTTP exchange; WebFluxConfigurer customizes infrastructure.
- Server port/TLS/Netty configuration belongs to server properties and WebServerFactoryCustomizer.
- Test configuration with WebTestClient and integration tests, especially CORS preflight, route prefixes, and codec limits.

Official documentation:

1. [Spring Framework 6.2 Reference — WebFlux Config](https://docs.spring.io/spring/reference/6.2/web/webflux/config.html): @EnableWebFlux, WebFluxConfigurer, codecs, path matching, static resources, view resolvers, and blocking execution.
2. [Spring Boot 3.5 Reference — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): WebFlux auto-configuration, codec customizer, static content, error handling, and reactive servers.
3. [Spring Framework 6.2 Reference — WebFlux CORS](https://docs.spring.io/spring/reference/6.2/web/webflux-cors.html): preflight, global CORS, @CrossOrigin, and CorsWebFilter.
4. [Spring Framework 6.2 Javadoc — WebFluxConfigurer](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/reactive/config/WebFluxConfigurer.html): callback contract and configuration methods.
5. [Spring Boot 3.5 Testing Reference — WebFlux Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): @WebFluxTest, test slices, and WebTestClient.
6. [Spring Framework 6.2 Javadoc — DelegatingWebFluxConfiguration](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/reactive/config/DelegatingWebFluxConfiguration.html): advanced configuration and the WebFluxConfigurer delegation mechanism.
