# What Spring Boot Auto-Configures for WebFlux

## 1. Lesson Objectives and Scope

When a Spring Boot application uses **Spring WebFlux**, developers typically only need to declare `spring-boot-starter-webflux`, write a `@RestController` or `RouterFunction`, and run `@SpringBootApplication`. Spring Boot inspects the classpath, web application type, existing beans, and configuration properties, then assembles most of the reactive HTTP serving infrastructure.

This lesson clarifies:

- **Which components Spring Boot auto-configures**, which components are inherently provided by **Spring Framework WebFlux**, and which ones appear only when the appropriate dependency is present.
- The relationship between the embedded reactive web server, `HttpHandler`, `DispatcherHandler`, `HandlerMapping`, codecs, `WebFilter`, static resources, template engines, and error handling.
- How to add configuration with `WebFluxConfigurer` while preserving Boot's auto-configuration.
- Situations where using `@EnableWebFlux`, defining custom beans, or adding Spring MVC changes auto-configuration.
- How to verify the infrastructure is actually active and avoid blocking on the event loop.

**Example scope:** Spring Boot **3.5.x**, Spring Framework **6.2.x**, Java **17+**. Spring Boot 4.x may move packages, starters, or property names; check the reference/Javadoc for your exact version before copying version-dependent configuration.

## 2. What Is Auto-Configuration?

`@SpringBootApplication` includes `@EnableAutoConfiguration`, allowing Boot to import conditional configurations (`@AutoConfiguration`) based on dependencies, properties, and user-declared beans.

Common conditional annotations:

- `@ConditionalOnClass`: activates only when the required library/class is present.
- `@ConditionalOnWebApplication(type = REACTIVE)`: applies only when the ApplicationContext is of the reactive web type.
- `@ConditionalOnMissingBean`: backs off if the user has already provided a bean of the matching type.
- `@ConditionalOnProperty`: optionally enables or disables a feature based on a property.

For example, in Spring Boot 3.5, `WebFluxAutoConfiguration` requires the application to be of type `REACTIVE`, the `WebFluxConfigurer` class to be present, and no user-defined `WebFluxConfigurationSupport` to exist. It runs after several auto-configurations such as the reactive web server, codecs, and validation.

This does not mean that a bean sharing a name with a Boot class is created in every project. **Auto-configuration is conditional**, and Boot generally avoids overriding customizations that the application has explicitly provided.

## 3. Conditions for Spring Boot to Choose WebFlux

Common Maven dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

The starter brings Spring WebFlux, Project Reactor, and a default web server runtime—typically **Reactor Netty**—onto the classpath.

Key scenarios:

| Classpath / configuration | Typically selected application type | Impact |
|---|---|---|
| `spring-boot-starter-webflux` present, no MVC starter | `REACTIVE` | WebFlux server and reactive infrastructure are configured |
| `spring-boot-starter-web` present | `SERVLET` | Typically Spring MVC |
| **Both** `spring-boot-starter-web` and `spring-boot-starter-webflux` present | `SERVLET` by default | Boot prefers MVC; `WebClient` is still usable |
| No required web infrastructure present | `NONE` | Does not start an HTTP web server as a web application |
| Explicitly configured `spring.main.web-application-type=reactive` | `REACTIVE`, if dependencies support it | Forces selection of the reactive web application type |

Example of explicit selection:

```properties
spring.main.web-application-type=reactive
```

This is not a full substitute for proper dependency management. Projects intentionally choosing WebFlux should exclude unnecessary MVC starters to avoid unwanted beans and auto-configurations.

**Distinction:** Merely using `WebClient` in an MVC application **does not turn that application into a WebFlux server**. Having `spring-webflux` on the classpath and running Spring Boot with web application type `REACTIVE` are two different things.

## 4. Overview of the Reactive HTTP Flow

High-level diagram when using Reactor Netty:

```text
HTTP client
    |
    v
Reactor Netty (embedded reactive web server)
    |
    v
HttpHandler / WebHttpHandlerBuilder
    |-- WebFilter chain
    |-- WebExceptionHandler chain
    |-- WebSessionManager / locale / codec-related context
    |
    v
DispatcherHandler (WebFlux front controller)
    |
    +--> HandlerMapping
    |      |-- annotated @RequestMapping/@GetMapping
    |      |-- RouterFunction functional endpoints
    |      |-- resource handler mappings
    |
    v
HandlerAdapter -> Controller/HandlerFunction
    |
    v
HandlerResultHandler
    |-- ResponseBodyResultHandler
    |-- ServerResponseResultHandler
    |-- ViewResolutionResultHandler
    |
    v
HttpMessageWriter / View render
    |
    v
HTTP response
```

A request can be decoded by an `HttpMessageReader`, processed by a controller or functional handler, and then written to the response via an `HttpMessageWriter`. For HTML responses, `ViewResolutionResultHandler` and a template engine may participate.

**`DispatcherHandler` is the front controller of Spring WebFlux**, whereas `DispatcherServlet` belongs to Spring MVC. WebFlux uses `ServerWebExchange` instead of requiring applications to work directly with `HttpServletRequest`/`HttpServletResponse` in standard WebFlux APIs.

## 5. Component Groups: Boot Auto-Configured vs. Framework-Provided

| Group | Typical components | Source of responsibility | Conditions / notes |
|---|---|---|---|
| ApplicationContext | Reactive web application context | Spring Boot integration | `REACTIVE` application type |
| Embedded web server | `ReactiveWebServerFactory`, default typically `NettyReactiveWebServerFactory` | Spring Boot | Depends on server runtime on classpath |
| HTTP handler adaptation | `HttpHandler`, `WebHttpHandlerBuilder` | Provided by Framework; assembled/customized by Boot | Integrates the server with WebFlux |
| Front controller | `DispatcherHandler` | Spring WebFlux infrastructure | Created via WebFlux configuration |
| Request routing | `RequestMappingHandlerMapping`, `RouterFunctionMapping`, resource mapping | Spring WebFlux infrastructure | Annotated and functional styles |
| Handler execution | `RequestMappingHandlerAdapter`, `HandlerFunctionAdapter` | Spring WebFlux infrastructure | Invokes the matching handler |
| Result writing | `ResponseBodyResultHandler`, `ServerResponseResultHandler`, `ViewResolutionResultHandler` | Spring WebFlux infrastructure | Chooses how to write the response |
| Data conversion | `HttpMessageReader`, `HttpMessageWriter`, `ServerCodecConfigurer` | Framework defaults; Boot adds codecs/Jackson customization | Depends on JSON/XML libraries on classpath |
| Static resources | `ResourceWebHandler` and resource mapping | WebFlux + Boot properties/configuration | Serves `/static`, `/public`, WebJars if present |
| Template engine | Thymeleaf, FreeMarker, Mustache view integrations | Boot provides auto-config if starter is present | Not present in every REST project |
| Error response | `WebExceptionHandler`, `ErrorWebExceptionHandler`, error attributes | Boot provides default error handling on top of Framework | Customizable |
| Web filters | `WebFilter`, `WebFilterChain` | Framework; Boot picks up beans and may add filters | Security filters appear only with matching dependency/config |
| HTTP client | `WebClient.Builder` prototype, connector customization | Spring Boot client-side auto-configuration | WebFlux on classpath; does not prove a reactive server |
| Security, Actuator | Reactive security chain, metrics, health, observations | Conditional auto-config from related starters | Not present by default unless dependencies are added |

This table distinguishes **configuration creation responsibility** from **API origin**. Not all listed beans are declared directly inside `WebFluxAutoConfiguration`; many are initialized by Spring Framework's `WebFluxConfigurationSupport`, while Boot supplies conditions, property binding, and customization.

## 6. Embedded Reactive Server: Reactor Netty and Other Options

`spring-boot-starter-webflux` typically selects Reactor Netty as the default HTTP server. Boot uses `ReactiveWebServerFactoryAutoConfiguration` to set up the corresponding factory and expose common server options.

Configuration via `application.properties`:

```properties
server.port=8080
server.address=127.0.0.1
server.compression.enabled=true
```

When `server.address=127.0.0.1` is set, the application listens only on loopback; for containers or deployment environments requiring external access, do not copy this setting without adjusting it.

Web server features can include:

- Port and bind address: `server.port`, `server.address`.
- TLS/HTTPS with `server.ssl.*` when TLS terminates at the application.
- Compression: `server.compression.*`.
- HTTP/2: `server.http2.enabled`, provided the transport/server supports it.
- Server-specific settings, such as `server.netty.*` when using Reactor Netty.

Spring Boot also supports other embedded reactive servers such as Tomcat or Jetty in appropriate setups, by **swapping the server dependency**, not simply changing a property.

If deeper customization is needed:

- `WebServerFactoryCustomizer<...>` for the matching factory.
- `NettyReactiveWebServerFactory` and Netty customization hooks when supported by the current runtime.
- `ReactorResourceFactory` for HTTP resources such as event loops and connection pools; resources can be shared between the server and Boot-configured Reactor Netty `WebClient` instances.

Factory customizers are invoked **before the server is created**, not as an API to change the listening HTTP port at runtime. Prefer standard properties before reaching for low-level APIs.

## 7. DispatcherHandler and Routing Components

WebFlux infrastructure is provided by Spring Framework through `WebFluxConfigurationSupport` / `DelegatingWebFluxConfiguration`, and activated/tuned by Spring Boot when auto-configuration conditions are met.

Key components:

- **`DispatcherHandler`**: receives `ServerWebExchange` and coordinates handler mappings, adapters, and result handlers.
- **`RequestMappingHandlerMapping`**: resolves `@Controller`, `@RestController`, `@RequestMapping`, `@GetMapping`, etc.
- **`RequestMappingHandlerAdapter`**: invokes annotated controller methods.
- **`RouterFunctionMapping`**: finds handlers for `RouterFunction` functional routes.
- **`HandlerFunctionAdapter`**: executes a `HandlerFunction`.
- **`ResponseBodyResultHandler`**: selects writers for `@ResponseBody` or `@RestController`.
- **`ResponseEntityResultHandler`**: handles `ResponseEntity` return values.
- **`ServerResponseResultHandler`**: writes `ServerResponse` for functional endpoints.
- **`ViewResolutionResultHandler`**: dispatches views when rendering server-side UI.
- **`ResourceWebHandler`**: serves static content.

An application can use **both annotated controllers and functional endpoints**. Mappings and route order should be managed clearly to avoid conflicts, but you do not need to manually define the infrastructure beans above just to build basic APIs.

## 8. HTTP Codecs: HttpMessageReader, HttpMessageWriter, and Jackson

WebFlux does not use Spring MVC's `HttpMessageConverter` for reactive bodies in the usual way. The primary interfaces are:

- `HttpMessageReader<T>`: reads/decodes the request body.
- `HttpMessageWriter<T>`: encodes and writes the response body.
- `CodecConfigurer` / `ServerCodecConfigurer`: organizes and customizes codecs.
- Jackson JSON codecs, string codecs, byte codecs, and others, selected according to dependencies.

Spring Boot adds codec auto-configuration, combining libraries on the classpath with `CodecCustomizer` beans. Several Jackson settings from `spring.jackson.*` are applied to the JSON codec.

**Property for Spring Boot 3.5:**

```properties
spring.http.codecs.max-in-memory-size=512KB
```

This property adjusts the memory limit when a codec needs to buffer incoming data and applies to **the WebFlux server and Boot-auto-configured WebClient instances**. If unset, each codec uses its own default limit—often around 256KB for many codecs. It is **not a limit on total upload size or total HTTP request bytes on the wire**.

If a decoder attempts to buffer beyond the limit in a case where it applies, an error such as `DataBufferLimitException` may occur. Do not raise the threshold to gigabytes instead of considering streaming, pagination, file uploads, or off-memory storage.

Example of using `WebFluxConfigurer` to configure codecs conceptually:

```java
@Override
public void configureHttpMessageCodecs(
        ServerCodecConfigurer configurer) {
    configurer.defaultCodecs().maxInMemorySize(512 * 1024);
}
```

The snippet above is an **illustrative method inside a class implementing `WebFluxConfigurer`**, requiring an import of `org.springframework.http.codec.ServerCodecConfigurer`. For simple needs, use the `spring.http.codecs.max-in-memory-size` property to avoid redundant configuration.

**Do not call `registerDefaults(false)` indiscriminately.** Disabling all default codecs can cause JSON, text, or other previously working body formats to stop encoding/decoding; use it only when managing codecs manually under a verified architecture.

## 9. Auto-Configured Static Resources and WebJars

Spring Boot supports WebFlux serving static resources from default classpath directories, typically:

```text
src/main/resources/static/
src/main/resources/public/
src/main/resources/resources/
src/main/resources/META-INF/resources/
```

For example, place `src/main/resources/static/hello.txt`:

```text
Hello from static
```

Once the application is running, you can test it:

```bash
curl -i http://localhost:8080/hello.txt
```

If the resource is packaged and the default mapping has not been changed, the response body contains `Hello from static`.

Spring WebFlux uses `ResourceWebHandler`; Boot adds path and resource location configuration. Properties:

```properties
# Change URL prefix from /** to /assets/**
spring.webflux.static-path-pattern=/assets/**
```

Then the corresponding URL becomes `/assets/hello.txt` instead of `/hello.txt`, provided no other route claims that path and the file exists.

```properties
# Replace the default static locations list
spring.web.resources.static-locations=classpath:/custom-static/
```

The `static-locations` property **replaces** the default locations rather than appending to them. If you use a new location, place resources in the right directory and verify welcome page mapping.

Spring Boot also supports WebJars under the configured path pattern; this does not mean every frontend library automatically exists on the classpath. Without a WebJar dependency, there are no resources from it to serve.

This is why you should not add `@EnableWebFlux` just to change a static path: doing so can cause Boot's static resource auto-configuration to stop applying.

## 10. HTML Template Engines and View Resolution

WebFlux does not serve only JSON APIs; it can also render HTML via a reactive `ViewResolver`.

Spring Boot supports auto-configuration for template engines when the corresponding dependency is added:

- Thymeleaf.
- FreeMarker.
- Mustache.

Templates are typically looked up in:

```text
src/main/resources/templates/
```

Example WebFlux controller returning a view name:

```java
@Controller
public class WelcomePageController {

    @GetMapping("/welcome")
    public String welcome(Model model) {
        model.addAttribute("name", "Lan");
        return "welcome";
    }
}
```

With a compatible reactive template engine and `templates/welcome.html`, the system renders HTML for the view name. The Java snippet only illustrates controller logic and requires imports for `org.springframework.stereotype.Controller`, `org.springframework.web.bind.annotation.GetMapping`, and `org.springframework.ui.Model`.

**Do not confuse `@RestController` with `@Controller`.** `@RestController` writes the response body instead of resolving a standard view name. `@EnableWebFlux` also does not install Thymeleaf or create HTML templates; you need the proper dependency and resources.

Some FreeMarker features in WebFlux differ from the Servlet stack. When using HTML templates, check the reactive support of the engine and version in use.

## 11. Error Handling: WebExceptionHandler, ErrorAttributes, and Problem Details

Spring Boot provides default error handling for WebFlux built on the `WebExceptionHandler` system. Components may include:

- `ErrorAttributes`: gathers error details for rendering.
- `ErrorWebExceptionHandler`: handles errors at the reactive web exchange level.
- `DefaultErrorWebExceptionHandler`: Boot's default implementation in matching configurations.
- `AbstractErrorWebExceptionHandler`: base class for building custom error handling.
- `@RestControllerAdvice` and `@ExceptionHandler`: handles errors close to controllers, for errors within supported handler scopes.

When a request is unmapped or an exception occurs, Boot can produce a JSON response for API clients or an HTML error page for browsers depending on the request and content negotiation. Exact default error bodies are not guaranteed stable across all Boot versions; do not write application tests that rely solely on default error message strings.

Spring Boot 3.5 supports enabling RFC 9457 Problem Details:

```properties
spring.webflux.problemdetails.enabled=true
```

When enabled, eligible errors can return `application/problem+json` with fields such as `type`, `title`, `status`, `detail`, and `instance`. Never expose stack traces, SQL queries, tokens, or operational secrets in client error responses.

To customize default error attributes, consider an `ErrorAttributes` bean. Write a custom `ErrorWebExceptionHandler` only if you need full control over the error flow. Registering multiple global handlers in the wrong order can break standard response formatting or silently swallow errors without monitoring.

## 12. WebFilter and the HttpHandler Chain

Spring WebFlux provides `WebFilter` to intercept requests and responses at the reactive exchange level. Application-declared `WebFilter` beans are discovered by Spring Boot and inserted into the appropriate HTTP handler chain.

Lightweight filter example:

```java
package com.example.webfluxdemo;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
@Order(10)
public class TraceHeaderFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {
        exchange.getResponse().getHeaders()
                .add("X-Demo-Filter", "webflux");
        return chain.filter(exchange);
    }
}
```

This class can be used in a running WebFlux project and adds the header `X-Demo-Filter: webflux` to responses. In production, adding headers must also account for security, error responses, and whether the response has already been committed.

- `@Order` / `Ordered` helps control filter order.
- A filter should return a valid `Mono<Void>` and never call `block()` on the event loop.
- Do not use `javax.servlet.Filter` or `jakarta.servlet.Filter` as a substitute for `WebFilter` in standard WebFlux APIs.

**`WebHttpHandlerBuilderCustomizer`** is Boot's hook to customize how `WebHttpHandlerBuilder`/`HttpHandler` is built when deeper adjustments than standard WebFlux config are needed. It is not the first choice for routine request logic; prefer `WebFilter` or `WebFluxConfigurer` when sufficient.

## 13. WebClient.Builder: Client-Side Configuration Is Separate

With `spring-webflux` on the classpath, Spring Boot can auto-configure a pre-configured `WebClient.Builder` bean used as a template to create `WebClient` instances.

Example:

```java
package com.example.webfluxdemo;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class UpstreamService {

    private final WebClient webClient;

    public UpstreamService(WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("https://api.example.org")
                .build();
    }

    public Mono<String> fetch(String id) {
        return webClient.get()
                .uri("/items/{id}", id)
                .retrieve()
                .bodyToMono(String.class);
    }
}
```

This example illustrates the technique only; `https://api.example.org` is a placeholder URL and must be replaced with a real upstream before calling. No fixed output is guaranteed.

Important distinctions:

- `WebClient.Builder` serves **outbound** HTTP requests.
- `ReactiveWebServerFactory` and `DispatcherHandler` serve **inbound** HTTP requests.
- Spring MVC can use `WebClient.Builder` when WebFlux is on the classpath; that **does not** switch the app to Reactive.
- Calling `WebClient.create()` directly can bypass `WebClientCustomizer` beans and Boot-applied builder customizations.
- With Reactor Netty/Jetty, a resource factory may affect both the server and Boot-configured clients, depending on the technology and how the client is constructed.

Do not call `.block()` inside a reactive WebFlux handler just to obtain a synchronous result from `WebClient`; return the publisher from the pipeline and use reactive operators.

## 14. Additional Auto-Configuration Only When Dependencies Exist

**Spring Security:** if `spring-boot-starter-security` and matching reactive security modules are added, Spring Boot/Spring Security creates or integrates the security filter chain for a reactive application. In WebFlux, typical interfaces are `SecurityWebFilterChain` and `WebFilterChainProxy`, not the Servlet `SecurityFilterChain`.

**Actuator:** if `spring-boot-starter-actuator` is added, Boot can auto-configure health, metrics, HTTP observations, and management endpoints depending on actuator version, properties, and dependencies. Do not assume all management endpoints are exposed publicly over HTTP.

**Validation:** if a Jakarta Bean Validation implementation (such as the validation starter) and appropriate configuration are present, Spring can wire a validator for reactive controller/model binding. Having only the WebFlux starter does not guarantee validation annotations will work as expected without a provider.

**WebSocket:** WebFlux and the server/runtime can support WebSocket when required modules/features are declared, but adding the starter alone does not create a WebSocket endpoint; you need handler mappings and application logic.

**Data access:** R2DBC, Spring Data Reactive, reactive Mongo repositories, and database resources are **separate** auto-configurations enabled when their dependencies are present. They are not created by `WebFluxAutoConfiguration` just because the server selects `REACTIVE`.

Rule of thumb: **"Spring Boot supports auto-configuring X" does not mean "everything is available in every WebFlux app"**. Always check starters, the auto-configuration condition report, and actual created beans.

## 15. Customizing While Keeping Auto-Configuration via WebFluxConfigurer

Spring Boot recommends creating a `@Configuration` class that **implements `WebFluxConfigurer`**, without adding `@EnableWebFlux`, to preserve Boot's auto-configured features.

Example CORS configuration for API endpoints from a specific frontend:

File `src/main/java/com/example/webfluxdemo/WebFluxCorsConfiguration.java`:

```java
package com.example.webfluxdemo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class WebFluxCorsConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://frontend.example.org")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "Authorization");
    }
}
```

This is a complete class; `https://frontend.example.org` is an example origin and must be replaced with your system's trusted origin. If Spring Security is present, check how CORS configuration interacts with the security chain. Never copy `.allowedOrigins("*")` carelessly, especially when credentials are used.

`WebFluxConfigurer` can be used to add:

- `addCorsMappings`: URL-based CORS policy.
- `addFormatters`: conversion/formatting.
- `addResourceHandlers`: custom static resources.
- `configureHttpMessageCodecs`: codec settings/custom codecs.
- `configureViewResolvers`: view resolution.
- `configurePathMatching`: certain path handling rules.
- Other callbacks available in your Spring Framework version.

When you only need to change properties like port, static path, or codec limit, prefer `.properties`/`.yaml` configuration; avoid unnecessary Java config.

### When @EnableWebFlux Is Used

`@EnableWebFlux` activates the WebFlux configuration provided by Spring Framework while also signaling the intent to **take full control of WebFlux configuration**. It can cause Boot's `WebFluxAutoConfiguration` to back off because a `WebFluxConfigurationSupport` already exists.

This does not mean the application immediately stops working or all infrastructure disappears; Spring Framework still configures core WebFlux components. However, **Boot's additional customizations** (static resources, codecs, property bindings, welcome page, and related hooks) may change or no longer apply unless you reconfigure them.

Use `@EnableWebFlux` only when you want complete control and accept responsibility for recreating/customizing what you need. Do not add this annotation merely for CORS or registering a formatter.

## 16. Runnable Example: Annotated Endpoint + Functional Endpoint

Assume a Spring Boot 3.5 Maven project with Java 17 and Boot's parent or dependency management. Add `spring-boot-starter-webflux`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

Do not add `spring-boot-starter-web` to this example.

File structure:

```text
src/main/java/com/example/webfluxdemo/
    WebFluxDemoApplication.java
    HelloController.java
    FunctionalRoutes.java
src/main/resources/
    application.properties
    static/hello.txt
```

### 16.1. Startup Class

File `src/main/java/com/example/webfluxdemo/WebFluxDemoApplication.java`:

```java
package com.example.webfluxdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFluxDemoApplication.class, args);
    }
}
```

### 16.2. Annotated Controller

File `src/main/java/com/example/webfluxdemo/HelloController.java`:

```java
package com.example.webfluxdemo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class HelloController {

    @GetMapping("/api/hello")
    public Mono<Greeting> hello() {
        return Mono.just(new Greeting("Hello WebFlux"));
    }

    public record Greeting(String message) {
    }
}
```

Jackson auto-configuration and reactive JSON codecs serialize the record to JSON in a standard starter setup.

### 16.3. Functional Routing

File `src/main/java/com/example/webfluxdemo/FunctionalRoutes.java`:

```java
package com.example.webfluxdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RequestPredicates.GET;
import static org.springframework.web.reactive.function.server.RouterFunctions.route;

@Configuration(proxyBeanMethods = false)
public class FunctionalRoutes {

    @Bean
    RouterFunction<ServerResponse> pingRoute() {
        return route(GET("/functional/ping"), request ->
                ServerResponse.ok()
                    .contentType(MediaType.TEXT_PLAIN)
                    .bodyValue("pong"));
    }
}
```

Boot/WebFlux detects the `RouterFunction` bean and uses the functional routing infrastructure; there is no need to manually create `DispatcherHandler` or `HandlerFunctionAdapter`.

### 16.4. Configuration and Static File

File `src/main/resources/application.properties`:

```properties
server.port=8080
spring.http.codecs.max-in-memory-size=512KB
spring.webflux.problemdetails.enabled=true
```

File `src/main/resources/static/hello.txt`:

```text
Hello static WebFlux
```

In a Maven project with the Maven Wrapper:

```bash
./mvnw spring-boot:run
```

Test with `curl`:

```bash
curl -s http://localhost:8080/api/hello
curl -s http://localhost:8080/functional/ping
curl -s http://localhost:8080/hello.txt
```

Expected bodies for the three commands in order:

```text
{"message":"Hello WebFlux"}
pong
Hello static WebFlux
```

Note that each `curl -s` command may print the body without a trailing newline, so running all three sequentially in a terminal may concatenate the strings. The output above shows **one body per line for readability**, not a byte-for-byte terminal transcript.

This example demonstrates three mechanisms working together: annotated WebFlux handler → JSON codec, functional routing → String writer, and Boot static resource mapping. A real Boot project is required to run it; the Java files cannot be compiled standalone with `javac` using only the JDK because of Spring/Reactor/Jackson dependencies.

## 17. Testing WebFlux with WebTestClient

Spring Boot supports `@WebFluxTest` to create a test slice focused on WebFlux controllers, as well as `WebTestClient` to send mock requests or requests to a live server.

Add the test dependency in a Maven project that already has Boot dependency management:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Example test slice for the annotated controller, file `src/test/java/com/example/webfluxdemo/HelloControllerTest.java`:

```java
package com.example.webfluxdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(controllers = HelloController.class)
class HelloControllerTest {

    @Autowired
    private WebTestClient webTestClient;

    @Test
    void returnsGreetingAsJson() {
        webTestClient.get()
                .uri("/api/hello")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        org.springframework.http.MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello WebFlux");
    }
}
```

`@WebFluxTest` creates a scoped WebFlux test environment and does not auto-scan all `@Service` or repository beans of the application. If the controller depends on services, use appropriate mocks or test configurations. This test slice does not prove the full embedded server is listening on a real socket.

To integration-test both the server and routing, you can use `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` with `WebTestClient` configured against the embedded server; configure it appropriately for your Boot version. Choose test slices for simple mapping/codec checks, and integration tests for real TLS/server/resource behavior.

Run tests:

```bash
./mvnw test
```

There is no fixed business stdout for `mvnw test`; Maven output depends on the dependency cache, test reports, and project configuration.

## 18. Common Issues and Troubleshooting

| Symptom | Common cause | Investigation direction |
|---|---|---|
| WebFlux starter present but app runs MVC | Both `starter-web` and `starter-webflux` on classpath | Check dependency tree and `WebApplicationType` |
| `WebClient.Builder` exists so app is assumed to be a WebFlux server | Client auto-config is independent of the server stack | Verify `ReactiveWebServerApplicationContext` and embedded server |
| `@EnableWebFlux` changes static file/codec config | Boot WebFlux auto-config is partially replaced | Remove `@EnableWebFlux` if only extending; use `WebFluxConfigurer` |
| `/hello.txt` returns 404 | File in wrong directory, `static-locations` replaced defaults, static path pattern changed | Check runtime classpath and URL |
| JSON 406/415 or fails to serialize | Converter/codec, `Accept`, `Content-Type`, JSON dependencies | Check readers/writers, media types, and mappings |
| `DataBufferLimitException` | Decoder must buffer more data than the in-memory limit | Reduce payload, stream, or adjust `spring.http.codecs.max-in-memory-size` carefully |
| Slow API, blocked event loop | Calling JDBC, `Thread.sleep`, `.block()` in handler | Use non-blocking I/O; isolate blocking work on an appropriate scheduler when unavoidable |
| Servlet filter does not run as expected | Used `Filter` instead of `WebFilter` in reactive APIs | Switch to an appropriate `WebFilter` |
| Error response lacks expected details | Boot default error handler, Problem Details, or `@ExceptionHandler` | Check error configuration; do not log secrets |
| Missing auth or actuator endpoint absent | Missing security/actuator starter, property, or conflicting bean | Check dependencies, `SecurityWebFilterChain`, endpoint exposure |
| Server swapped but customizer does not apply | Generic factory hardcoded to Reactor Netty/Tomcat | Choose the matching factory type or common API |
| `@WebFluxTest` missing service bean | Test slice loads only part of the context | Provide mocks or use `@SpringBootTest` |

The easiest mistake is calling everything **"Boot auto-created"**. Many core beans are actually defined by Spring Framework WebFlux; Boot decides when to activate them, adds convenient configuration, and wires them to the runtime infrastructure.

## 19. Inspecting Which Auto-Configurations Actually Applied

During debugging, you can start the project with the debug flag:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
```

Or add a temporary property:

```properties
debug=true
```

Spring Boot prints the **Condition Evaluation Report** showing which auto-configurations matched or did not match and why. Look for names such as:

- `WebFluxAutoConfiguration`.
- `ReactiveWebServerFactoryAutoConfiguration`.
- `CodecsAutoConfiguration`.
- `WebClientAutoConfiguration`.
- `ErrorWebFluxAutoConfiguration`.
- Spring Security and Actuator auto-configurations if those dependencies are present.

Class names and package structures can change across Boot versions; do not build monitoring dashboards that rely solely on fixed classname strings across major versions.

If Actuator is enabled and security/exposure permits, `/actuator/conditions` can show the corresponding report. This is a diagnostic endpoint that can expose configuration details; **do not expose it publicly on the Internet**.

Command to inspect dependencies:

```bash
./mvnw dependency:tree
```

For Gradle projects:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Additionally, you can:

1. Check startup logs to see whether the embedded server is Netty or another type.
2. Check whether the `ApplicationContext` class is a reactive context.
3. Set breakpoints in controllers, functional handlers, or filters.
4. Test annotated endpoints, functional routes, static resources, and error responses.
5. Use thread dumps or metrics to detect blocking operations on the event loop.
6. Inspect effective property sources when a configuration value is not taking effect.
7. Compare auto-config conditions before and after adding a starter or `@EnableWebFlux`.

## 20. Checklist When Customizing a WebFlux Application

- [ ] Dependencies reflect intentional WebFlux usage without accidentally pulling in the MVC starter.
- [ ] The app is resolved as `WebApplicationType.REACTIVE`.
- [ ] You know which embedded server is running and which `server.*` properties take effect.
- [ ] You distinguish WebFlux's `DispatcherHandler` from MVC's `DispatcherServlet`.
- [ ] You understand annotated controllers, functional routing, codecs, and static resources.
- [ ] Lightweight customization uses `WebFluxConfigurer` **without** `@EnableWebFlux`.
- [ ] `@EnableWebFlux` is used only when deep control of WebFlux configuration is desired and you accept managing Boot-provided defaults yourself.
- [ ] You know `spring.http.codecs.max-in-memory-size` differs from total HTTP request body size.
- [ ] You use `WebFilter` and do not confuse it with a Servlet filter.
- [ ] You distinguish outbound `WebClient.Builder` from the inbound embedded web server.
- [ ] You verify conditional features such as Security, Actuator, Validation, and template engines.
- [ ] Tests exist for controllers, functional routes, error handling, and static resources if used.
- [ ] You inspect the Condition Evaluation Report instead of guessing which auto-configurations ran.
- [ ] You avoid blocking the event loop to retain the benefits of non-blocking I/O.

## 21. Conclusion

Spring Boot auto-configures a WebFlux environment by selecting a reactive web application context, an embedded reactive HTTP server, codecs, error handling, static resource mappings, template engines when dependencies are present, and additional integrations. Core infrastructure such as `DispatcherHandler`, `HandlerMapping`, `HandlerAdapter`, `HandlerResultHandler`, and `ServerCodecConfigurer` largely comes from **Spring Framework WebFlux**, while Boot activates and refines them conditionally.

The most important maintenance rule: **add `WebFluxConfigurer` to extend, and do not add `@EnableWebFlux` if you still want to keep Boot WebFlux auto-configuration**. For each feature, clearly identify whether it is a Boot default configuration, a core Framework structure, or a capability enabled only when a starter/bean is added.

## 22. References

- Spring Boot 3.5 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- Spring Boot 3.5 — Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Boot 3.5 — WebFluxAutoConfiguration Javadoc: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/WebFluxAutoConfiguration.html
- Spring Boot 3.5 — Testing WebFlux: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot — Calling REST Services / WebClient: https://docs.spring.io/spring-boot/reference/io/rest-client.html
- Spring Framework — WebFlux configuration: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Framework — WebFlux DispatcherHandler: https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html
- Spring Framework — WebFlux.fn functional endpoints: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
- Project Reactor — Reference Guide: https://projectreactor.io/docs/core/release/reference/
