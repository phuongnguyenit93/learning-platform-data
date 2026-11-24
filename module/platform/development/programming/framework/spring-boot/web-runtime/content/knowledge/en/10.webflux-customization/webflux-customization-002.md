# WebFluxConfigurer: Adding Configuration While Keeping Spring Boot Defaults

## 1. Lesson Goal

In a Spring Boot application using **Spring WebFlux**, many HTTP processing components are already auto-configured by Boot: registering annotated controllers and functional routes, HTTP message readers/writers, static resources, WebJars, the welcome page, and integrations for libraries on the classpath. Most projects only need to **add** a few rules such as CORS, formatters, static resource paths, or codec memory limits, rather than rebuilding the entire WebFlux infrastructure from scratch.

**WebFluxConfigurer** is the extension point designed for this case. The single most important rule in Spring Boot:

> Create a **@Configuration implements WebFluxConfigurer** bean, override only the methods you actually need, and **do not add @EnableWebFlux** if you want to keep Spring Boot's WebFlux auto-configuration features.

This guidance is stated directly in the Spring Boot Reactive Web Applications documentation. @EnableWebFlux is meant for intentionally taking full control of Spring WebFlux configuration; adding that annotation just for a CORS mapping or static handler is an unnecessary architectural shift.

This lesson uses **Spring Boot 3.5.x, Spring Framework 6.2.x, Java 17+** as the baseline for packages and APIs. For Spring Boot 4.x or other versions, re-check the documentation, especially if module/package layouts have changed.

## 2. The Big Picture: Boot Auto-Configuration and WebFluxConfigurer

Typical flow:

~~~text
spring-boot-starter-webflux on the classpath
                 |
                 v
Spring Boot resolves WebApplicationType.REACTIVE
                 |
                 v
WebFluxAutoConfiguration is evaluated conditionally
                 |
                 +--> Creates / tunes WebFlux infrastructure
                 |    (HandlerMapping, HandlerAdapter, codecs...)
                 |
                 +--> Static resource mapping, WebJars,
                 |    welcome page, and Boot-specific conventions
                 |
                 +--> Picks up application-provided WebFluxConfigurer beans
                                 |
                                 v
                 addCorsMappings, addFormatters,
                 addResourceHandlers, configureHttpMessageCodecs...
                                 |
                                 v
                 HTTP server uses the combined configuration
~~~

WebFluxConfigurer is an **interface with default methods**. You only override the points you want to customize; unoverridden methods keep standard framework and Spring Boot behavior.

Correct configuration example for Spring Boot:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
class ReactiveWebConfiguration implements WebFluxConfigurer {
    // Override only the callbacks you need.
}
~~~

The snippet above illustrates the structure of a configuration class; complete runnable code is shown in section 7.

### Three Configuration Choices and Their Consequences

| Approach | What happens? | When to use? |
|---|---|---|
| @Configuration + WebFluxConfigurer, **no @EnableWebFlux** | Adds to the WebFlux infrastructure auto-configured by Boot | **Default choice** when you only need CORS, codecs, resources, formatters, etc. |
| @Configuration + @EnableWebFlux | Activates framework-managed WebFlux configuration, causing Boot's WebFlux auto-configuration to back off | When you intentionally want full control of WebFlux configuration and accept recreating Boot-provided parts |
| Extending WebFluxConfigurationSupport / DelegatingWebFluxConfiguration | Deep control over foundational WebFlux beans; requires understanding bean order and conditions | When framework extension APIs are insufficient—very rare in typical applications |

**Do not assume @EnableWebFlux turns off all of Spring Boot**: Boot can still initialize the ApplicationContext and embedded server. The main effect is that Boot stops applying certain framework-level WebFlux settings via standard auto-configuration. That can manifest as changes to static-resource mappings, codecs, view handling, or familiar conventions.

## 3. Verifying the Application Actually Runs WebFlux

For the examples to apply properly, the project should use spring-boot-starter-webflux and the reactive web application type.

Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

This starter typically brings Reactor Netty in as the embedded reactive HTTP server. WebFlux can run with other supported servers; **WebFluxConfigurer** configures WebFlux request handling rather than directly selecting the HTTP server or listening port.

When both spring-boot-starter-web and spring-boot-starter-webflux are present, Spring Boot normally chooses **Spring MVC (Servlet application)**. This is intentional: many MVC projects add starter-webflux solely to use WebClient. Therefore, seeing Mono/Flux on the classpath does not mean your WebFluxConfigurer is controlling an MVC runtime.

If you truly need reactive execution, prefer choosing the right starter for the purpose. When both dependencies are unavoidable, you can explicitly configure:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

Test with the other libraries in your dependency graph as well. In a reactive application, use classes under org.springframework.web.reactive.config.*; WebMvcConfigurer and servlet HandlerInterceptor are not the extension APIs for WebFlux.

## 4. Commonly Used WebFluxConfigurer Methods

| Callback | Effect | Use case |
|---|---|---|
| addCorsMappings(CorsRegistry) | Registers URL-based CORS for applicable WebFlux handler mappings | Cross-origin frontend calling the API |
| addFormatters(FormatterRegistry) | Adds Converters/Formatters for parameter binding in annotated controllers | ISO dates, custom value types |
| addResourceHandlers(ResourceHandlerRegistry) | Adds static resource serving paths | /manual-assets/** |
| configureHttpMessageCodecs(ServerCodecConfigurer) | Customizes HTTP message readers/writers and default codecs | Buffer limits, adding specialized codecs |
| configurePathMatching(PathMatchConfigurer) | Adjusts path matching or prefixes for annotated controllers | /api prefix convention for a controller group |
| configureContentTypeResolver(RequestedContentTypeResolverBuilder) | Customizes how response media types are resolved | Specialized content negotiation |
| configureViewResolvers(ViewResolverRegistry) | Configures view resolution for HTML-rendering apps | Thymeleaf, FreeMarker, and view engines |
| configureArgumentResolvers(ArgumentResolverConfigurer) | Registers custom argument resolvers for annotated controllers | Specialized request parameters |
| configureBlockingExecution(BlockingExecutionConfigurer) | Tunes execution for blocking controller methods | Integrating legacy methods requiring a suitable executor |

Callbacks have different scopes. For example, configuring a path prefix for annotated @RestController classes **does not automatically change the path of every RouterFunction**. HTTP codecs can apply to both annotated controllers and functional endpoints, whereas CORS with RouterFunction should be tested against the actual endpoint; when using functional routes, CorsWebFilter can be an appropriate option.

Adding a configurer does not magically make JDBC code or blocking I/O non-blocking. You must choose proper scheduling and non-blocking clients to preserve WebFlux's reactive characteristics.

## 5. CORS: Adding a Rule Without Replacing Boot Defaults

Suppose a web app at https://frontend.example.test needs to call an API from the browser to a different-origin server. You can register CORS in WebFluxConfigurer:

~~~java
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/api/**")
            .allowedOrigins("https://frontend.example.test")
            .allowedMethods("GET", "POST")
            .allowedHeaders("Content-Type", "Authorization")
            .maxAge(3600);
}
~~~

Meaning:

- /api/** limits CORS scope; it does not open permissions for every URL in the app.
- allowedOrigins holds **origins** including scheme, host, and port if present. This is a sample origin; replace it with the real frontend domain in deployment.
- allowedMethods specifies which HTTP methods the browser may use under CORS.
- allowedHeaders restricts headers during preflight; add headers based on actual needs.
- maxAge(3600) lets the browser cache preflight results for the configured duration, subject to browser caps.

CORS **is not authentication or authorization**. An API allowing a CORS origin still needs Spring Security or access-control logic if the data is not public. CORS is a browser policy; HTTP clients like curl do not enforce browser same-origin rules.

Never combine allowCredentials(true) with wildcard allowedOrigins("*"). When credentials are allowed, origins must be explicitly specified or use allowedOriginPatterns with strict rules. Carefully validate wildcard subdomains so untrusted hosts are not accidentally permitted.

If the project uses Spring Security WebFlux, coordinate CORS with SecurityWebFilterChain; if security handles preflight before the CORS configuration, OPTIONS requests can be rejected. Test an actual preflight containing Origin and Access-Control-Request-Method instead of testing only a plain GET without headers.

### @CrossOrigin vs. WebFluxConfigurer

@CrossOrigin fits when a policy applies only to a single controller or method. addCorsMappings fits when applying a shared policy to a URL group. Both can be combined according to Spring's CORS configuration rules; avoid conflicting or overly broad rules across multiple layers.

If using functional endpoints with RouterFunction, you can use CorsWebFilter for a broad policy. Do not assume all annotation-level configurations automatically apply to functional routes.

## 6. Formatters and Conversion: Adding to the Registry

Spring WebFlux includes a built-in conversion service for many data types, including numbers and several date/time types. When you need strict ISO formatting in annotated controllers:

~~~java
@Override
public void addFormatters(FormatterRegistry registry) {
    DateTimeFormatterRegistrar registrar = new DateTimeFormatterRegistrar();
    registrar.setUseIsoFormat(true);
    registrar.registerFormatters(registry);
}
~~~

Imports:

~~~java
import org.springframework.format.FormatterRegistry;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;
~~~

This **adds** formatters to the FormattingConversionService already used by the framework. There is no need to declare an entire ConversionService bean manually just to handle LocalDate.

Spring Boot also provides properties such as spring.webflux.format.date, spring.webflux.format.time, and spring.webflux.format.date-time. When the requirement is just a standard format pattern, prefer properties for easier management. Example:

~~~yaml
spring:
  webflux:
    format:
      date: yyyy-MM-dd
~~~

This is an alternative configuration based on needs—no need to enable it alongside a custom registrar if the two could compete. Supporting custom domain types is the most common reason to register a Formatter/Converter in Java.

Validation and JSON serialization are not the same as formatting URL parameters. A Formatter for @RequestParam LocalDate does not necessarily change the ObjectMapper used for JSON bodies. To adjust JSON serialization/deserialization, configure Jackson and codecs appropriately.

## 7. Static Resource Handlers: Adding a Path While Keeping Default Mappings

Spring Boot WebFlux provides out-of-the-box static resource support for standard classpath locations:

- classpath:/static/
- classpath:/public/
- classpath:/resources/
- classpath:/META-INF/resources/

In standard configuration, Boot maps static resources under /** and also supports WebJars. If you only need to **add** a custom path, you can use:

~~~java
@Override
public void addResourceHandlers(ResourceHandlerRegistry registry) {
    registry.addResourceHandler("/manual-assets/**")
            .addResourceLocations("classpath:/manual-assets/")
            .setCacheControl(
                    CacheControl.maxAge(Duration.ofMinutes(15)).cachePublic()
            );
}
~~~

With file src/main/resources/manual-assets/help.css, the corresponding URL is /manual-assets/help.css. A 15-minute max Cache-Control fits this illustrative example and is not mandatory for all assets.

When Boot's WebFlux auto-configuration is kept, a narrow custom handler like /manual-assets/** can coexist with the default static resource mapping. The key verification is that **both the new URL and default files continue to work**.

Example two files:

~~~text
src/main/resources/manual-assets/help.css
src/main/resources/static/default.txt
~~~

After proper startup, expected results:

~~~text
GET /manual-assets/help.css -> contents of help.css
GET /default.txt           -> contents of default.txt via Boot default mapping
~~~

If @EnableWebFlux is added without restoring Boot's static resource configuration, default behavior may change. That is a subtle regression that is especially easy to miss if you only test the new custom path.

### Related Properties

Spring Boot supports:

~~~yaml
spring:
  webflux:
    static-path-pattern: "/assets/**"
  web:
    resources:
      static-locations:
        - "classpath:/static/"
        - "classpath:/public/"
~~~

Notes:

- spring.webflux.static-path-pattern changes the URL pattern of **the default static mapping managed by Boot**.
- spring.web.resources.static-locations replaces the default static locations list with the specified list; to keep a default location, you must list it explicitly.
- Custom handlers registered separately via WebFluxConfigurer use the pattern/location specified by your application.
- Do not use spring.mvc.static-path-pattern in a reactive application; that setting belongs to Spring MVC.
- Never point a static resource handler at directories containing secrets, config files, or unvalidated upload data.

Registering /** across multiple resource handlers or overlapping API paths can cause hard-to-debug conflicts. Prefer distinct prefixes and test critical routes.

## 8. HTTP Codecs and Memory Limits

WebFlux uses HttpMessageReader/HttpMessageWriter to decode request bodies and encode response bodies. Spring Boot selects and customizes codecs based on the classpath and CodecCustomizer beans, including Jackson integration when the corresponding library is present.

If you only need to raise the limit on data aggregated in memory, customize lightly with WebFluxConfigurer:

~~~java
@Override
public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
    configurer.defaultCodecs().maxInMemorySize(512 * 1024);
}
~~~

This pattern adjusts **existing default codecs** without removing the default codec set. When specialized readers/writers are needed, you can use customCodecs().register(...) depending on the API and codec. Avoid calling registerDefaults(false) because it drops default codecs and can break JSON, String, form bodies, or other formats unless full replacements are registered.

**The maxInMemorySize limit is not a total size limit for every stream.** It matters when a decoder/reader must buffer data to build a single element, such as buffering a JSON body before parsing. For large payloads, raising the limit recklessly increases memory pressure risk. Depending on the codec and read path, exceeding the threshold can cause DataBufferLimitException.

In Spring Boot 3.5, when only configuring this value, you can prefer the HTTP codecs property:

~~~yaml
spring:
  http:
    codecs:
      max-in-memory-size: 512KB
~~~

This property applies to Boot-auto-configured WebFlux servers and WebClient instances as documented for that version. It is an **alternative** to the Java override if both only aim to change the same limit. Do not configure conflicting values in both the property and WebFluxConfigurer while assuming precedence stays identical across every version.

When tuning Jackson, use Boot configuration mechanisms such as spring.jackson.* or appropriate customizers before replacing the entire JSON reader/writer. If you drop all default codecs, you must verify support for application/json, text/plain, multipart, and every format your application uses.

## 9. Complete Spring Boot Example: Adding CORS, Formatter, Codec, and Resource

### 9.1. Dependencies and File Structure

The example uses Spring Boot **3.5.x**, Java **17+**, Maven, and three dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

This dependencies block is for a Spring Boot Maven project with a parent/BOM managing compatible versions. Do not copy it into a POM lacking Spring Boot dependency management without specifying versions.

Files:

~~~text
src/main/java/example/webflux/
    ReactiveDemoApplication.java
    ReactiveWebConfiguration.java
    DemoApiController.java
src/main/resources/
    static/default.txt
    manual-assets/help.css
src/test/java/example/webflux/
    ReactiveWebConfigurationTest.java
~~~

Source package directories match the package declarations of the classes so component scanning finds the controller and configuration.

### 9.2. Application Class

File src/main/java/example/webflux/ReactiveDemoApplication.java:

~~~java
package example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveDemoApplication.class, args);
    }
}
~~~

Do not add @EnableWebFlux. Spring Boot will evaluate auto-configuration based on the classpath and web application type.

### 9.3. ReactiveWebConfiguration

File src/main/java/example/webflux/ReactiveWebConfiguration.java:

~~~java
package example.webflux;

import java.time.Duration;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;
import org.springframework.http.CacheControl;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.ResourceHandlerRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class ReactiveWebConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://frontend.example.test")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "Authorization")
                .maxAge(3600);
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        DateTimeFormatterRegistrar registrar =
                new DateTimeFormatterRegistrar();
        registrar.setUseIsoFormat(true);
        registrar.registerFormatters(registry);
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/manual-assets/**")
                .addResourceLocations("classpath:/manual-assets/")
                .setCacheControl(
                        CacheControl.maxAge(Duration.ofMinutes(15))
                                .cachePublic()
                );
    }

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(512 * 1024);
    }
}
~~~

**The key point is the absence of @EnableWebFlux.** The four callbacks add the needed configuration and leave the WebFlux infrastructure managed by Boot in the standard way.

This example class configures both a codec limit and a formatter. In real projects, if you only need a setting that has an equivalent property, it is usually simpler to configure it in application.yaml.

### 9.4. Annotated Reactive Controller

File src/main/java/example/webflux/DemoApiController.java:

~~~java
package example.webflux;

import java.time.LocalDate;
import java.util.Map;

import reactor.core.publisher.Mono;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoApiController {

    @GetMapping("/hello")
    public Mono<Map<String, String>> hello() {
        return Mono.just(Map.of("message", "hello"));
    }

    @GetMapping("/date")
    public Mono<Map<String, String>> date(
            @RequestParam("day") LocalDate day) {
        return Mono.just(Map.of("day", day.toString()));
    }

    @PostMapping("/echo")
    public Mono<Map<String, String>> echo(
            @RequestBody Mono<Map<String, String>> requestBody) {
        return requestBody.map(payload ->
                Map.of("message", payload.getOrDefault("message", "")));
    }
}
~~~

This demonstrates three capabilities:

- GET /api/hello returns JSON handled by the default codec.
- GET /api/date?day=2026-11-07 uses conversion/formatting for the LocalDate parameter.
- POST /api/echo reads a JSON body into Mono<Map<...>> and responds with corresponding JSON.

The example has no blocking I/O. Mono.just merely creates simple data; in real business logic, database/network calls must use reactive drivers/clients or properly isolate blocking work.

### 9.5. Static Resources

File src/main/resources/manual-assets/help.css:

~~~css
body {
    color: #345678;
}
~~~

File src/main/resources/static/default.txt:

~~~text
boot-default-still-works
~~~

The first file must be served via the application-registered /manual-assets/** handler. The second must continue to be served via Boot's default static mapping. This provides direct observation that adding the configurer does not break Boot's existing static handling.

### 9.6. Running the Application

If the project has a Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

With standard default configuration, the server listens on port 8080. If the port has been overridden, adjust the curl URLs accordingly.

Check the JSON endpoint:

~~~bash
curl -i http://localhost:8080/api/hello
~~~

Expected response is HTTP 200 with JSON equivalent to:

~~~json
{"message":"hello"}
~~~

Other headers, header order, and JSON formatting may vary by runtime. Do not treat this as the entire raw HTTP response.

Check LocalDate:

~~~bash
curl -i "http://localhost:8080/api/date?day=2026-11-07"
~~~

Equivalent JSON body:

~~~json
{"day":"2026-11-07"}
~~~

Check JSON POST:

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
    -H "Content-Type: application/json" \
    -d '{"message":"sample"}'
~~~

Expected body:

~~~json
{"message":"sample"}
~~~

Check the new asset and the default asset:

~~~bash
curl -i http://localhost:8080/manual-assets/help.css
curl -i http://localhost:8080/default.txt
~~~

The custom path returns CSS; the default path returns the content boot-default-still-works. Verify both work rather than testing only the new resource handler.

### 9.7. Checking CORS Preflight

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/echo \
    -H "Origin: https://frontend.example.test" \
    -H "Access-Control-Request-Method: POST" \
    -H "Access-Control-Request-Headers: Content-Type"
~~~

With the sample configuration, a valid preflight response is expected to include Access-Control-Allow-Origin matching the given origin and allow POST. Exact HTTP status behavior and detailed headers can vary by version/server/security, so inspect the actual response.

The curl command only observes the CORS response; browsers are what enforce CORS policies when JavaScript makes cross-origin calls.

## 10. Regression Testing with WebTestClient

Spring WebFlux uses WebTestClient to test handlers and responses at the reactive HTTP layer. To verify both Boot's embedded-server configuration and your custom WebFluxConfigurer, you can run the full context on a random port.

File src/test/java/example/webflux/ReactiveWebConfigurationTest.java:

~~~java
package example.webflux;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveWebConfigurationTest {

    @Autowired
    WebTestClient client;

    @Test
    void jsonStillWorks() {
        client.get()
                .uri("/api/hello")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("hello");
    }

    @Test
    void localDateParameterIsConverted() {
        client.get()
                .uri("/api/date?day=2026-11-07")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.day").isEqualTo("2026-11-07");
    }

    @Test
    void preflightForConfiguredOriginIsAllowed() {
        client.options()
                .uri("/api/echo")
                .header(HttpHeaders.ORIGIN,
                        "https://frontend.example.test")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "Content-Type")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "https://frontend.example.test");
    }

    @Test
    void customResourceHandlerWorks() {
        client.get()
                .uri("/manual-assets/help.css")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .value(body -> assertThat(body).contains("#345678"));
    }

    @Test
    void bootDefaultStaticResourceStillWorks() {
        client.get()
                .uri("/default.txt")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .value(body -> assertThat(body)
                        .contains("boot-default-still-works"));
    }
}
~~~

With Maven Wrapper:

~~~bash
./mvnw test
~~~

From Windows PowerShell:

~~~powershell
.\mvnw.cmd test
~~~

How to read these tests:

- jsonStillWorks confirms the default JSON codec still works.
- localDateParameterIsConverted checks formatter/argument binding.
- preflightForConfiguredOriginIsAllowed checks the actual CORS policy.
- customResourceHandlerWorks confirms the new addition.
- bootDefaultStaticResourceStillWorks is a regression test for Boot's built-in feature.

If you remove the test for default.txt, the project could accidentally switch to full WebFlux control and lose default resources without the test suite noticing.

These tests are based on the Spring Boot 3.5.x project and resource files listed above. If Spring Security, custom WebFilters, or a reverse proxy are present, test those additional policies and infrastructure layers; an HTTP 401/403 from security does not by itself prove that the CORS mapping or resource handler is wrong.

## 11. WebFluxConfigurer vs. Other Extension Points

Not every adjustment in the reactive stack belongs in WebFluxConfigurer.

| Need | API/configuration to consider |
|---|---|
| URL-based CORS for annotated controllers | WebFluxConfigurer.addCorsMappings or @CrossOrigin |
| CORS across multiple handlers/functional routes | CorsWebFilter or appropriate security CORS integration |
| General filter before/after reactive requests | WebFilter, WebFilterChain |
| Authentication, authorization, CSRF | Spring Security WebFlux and SecurityWebFilterChain |
| Controller input/output formatting | Formatter/Converter, codec config, and Jackson customization |
| Custom HTTP error response | WebExceptionHandler / ErrorWebExceptionHandler or Problem Details config |
| Embedded server bind, port, threads/network | server.*, WebServerFactoryCustomizer, and Netty/Tomcat-specific config |
| Modifying auto-configured HttpHandler builder | WebHttpHandlerBuilderCustomizer bean in Spring Boot |
| Writing functional endpoints | RouterFunction, HandlerFunction, and RouterFunctions |
| Replacing MVC/Servlet configuration | Do not use WebFluxConfigurer; choose the right stack or WebMvcConfigurer if truly MVC |

For example, if you need to log every request including functional routes, WebFilter may fit better than looking for an MVC HandlerInterceptor. If you need to change the server port from 8080 to 9090, use server.port or a factory customizer; WebFluxConfigurer does not configure server sockets.

Do not use ServerWebExchange in Servlet MVC code assuming the two models share the same lifecycle. WebFlux uses reactive abstractions; MVC uses the Servlet API. This difference affects filters, exception handling, and testing.

## 12. When Can @EnableWebFlux Be Used?

@EnableWebFlux makes sense in a Spring Framework application running without Spring Boot, or in a Boot project **intentionally taking complete control of WebFlux configuration**.

Switching from:

~~~java
@Configuration
class WebConfig implements WebFluxConfigurer {
}
~~~

to:

~~~java
@Configuration
@EnableWebFlux
class WebConfig implements WebFluxConfigurer {
}
~~~

does more than simply enable one extra feature. Spring Boot's WebFlux auto-configuration conditionally backs off when @EnableWebFlux is used. Settings Boot previously provided must be reviewed or registered manually if still needed.

If @EnableWebFlux is genuinely required, list every behavior the application relies on:

1. JSON, text, multipart, and codecs actually needed.
2. Static resource mappings, WebJars, and welcome page.
3. HTTP error handling, Problem Details, and exception mappings.
4. Formatters, validators, view resolvers, CORS.
5. Spring Security integration, WebFilters, and observability.
6. Config properties in use and how auto-configuration bound them.

Choose full-control mode only when there is a concrete benefit and you have tests protecting critical behaviors. Manual reconfiguration incurs ongoing maintenance work, especially when upgrading Spring Boot.

## 13. Common Misconceptions and Pitfalls

### Pitfall 1: Adding @EnableWebFlux to "enable reactive"

Spring Boot can auto-configure WebFlux when dependencies and web application type match. Using @EnableWebFlux in Boot merely to get reactive controllers is unnecessary and can strip Boot WebFlux customizations.

**Fix:** remove @EnableWebFlux and keep @Configuration implements WebFluxConfigurer if you only want to add rules.

### Pitfall 2: Implementing WebMvcConfigurer in a WebFlux application

WebMvcConfigurer belongs to Servlet MVC. Reactive web applications do not use MVC registries for request processing.

**Fix:** choose org.springframework.web.reactive.config.WebFluxConfigurer and verify Boot actually selected WebApplicationType.REACTIVE.

### Pitfall 3: Having both starter-web and starter-webflux and assuming WebFlux is always chosen

Spring Boot normally chooses MVC when both are present. WebFluxConfigurer code may not configure the stack the developer thinks is running.

**Fix:** inspect the dependency tree, auto-configuration condition report, and application type. Pick one web stack explicitly.

### Pitfall 4: Disabling default codecs just to add one codec

Calling registerDefaults(false) and registering only a single reader can break JSON, text, or other body types that worked before.

**Fix:** prefer defaultCodecs() and customCodecs().register(...) as appropriate; disable defaults only when you have replaced the entire required set of readers/writers.

### Pitfall 5: Increasing maxInMemorySize and assuming every response stream is capped at 512KB total

Max in-memory size limits codec aggregation/buffering; it is not the total bytes transmitted across every reactive stream.

**Fix:** understand the semantics of the codec in use, test large payloads, and set separate policies for request size, proxy, multipart, and rate limits where needed.

### Pitfall 6: Overriding static-locations and losing Boot's resources

spring.web.resources.static-locations replaces the default locations. Declaring only one new folder does not implicitly retain the default folders.

**Fix:** use addResourceHandlers for a new prefix or explicitly list the old locations to keep in the property; add a regression test for /default.txt.

### Pitfall 7: Treating addCorsMappings as a security policy

CORS controls browser cross-origin behavior. It does not restrict who can read data when clients do not follow the browser same-origin policy.

**Fix:** use Spring Security WebFlux for access control and test CORS together with authentication/authorization.

### Pitfall 8: Using annotated controller path prefixes and expecting RouterFunction to change automatically

configurePathMatching applies to specific mapping scopes and does not automatically rewrite every RouterFunction URI.

**Fix:** define path prefixes for functional routes via RouterFunctions/route predicates and write tests for each handler style.

### Pitfall 9: Resources work locally but fail when packaged as a JAR

Static files are in the wrong folder, excluded from the build, or a custom resource location points to a filesystem path that does not exist in the container.

**Fix:** place resources under src/main/resources properly, inspect the JAR contents, and run integration tests against the packaged artifact.

### Pitfall 10: Ignoring the ordering of multiple WebFluxConfigurers

A large project may have several configurers and customizers modifying registries/codecs together. Overlapping rules make behavior hard to predict, especially for CORS and JSON codecs.

**Fix:** organize configuration by responsibility, avoid multiple sources controlling the same property, and verify the effective outcome with integration tests.

## 14. Practice and Verification Checklist

Before merging a WebFluxConfigurer change:

1. Verify the application runs on the reactive stack with the matching WebFlux starter.
2. Do not add @EnableWebFlux if you only want to add configuration.
3. Use properties before writing code when a property fully satisfies the requirement.
4. When adding CORS, restrict origins/methods/headers; test preflight and security.
5. When adding formatters, test both successful binding and invalid input.
6. When adjusting codecs, keep default readers/writers and test required JSON/streaming behavior.
7. When adding static handlers, use a distinct path prefix and test default static resources too.
8. When changing path matching, check the impact on annotated controllers, functional routes, and resource mappings.
9. When using WebFilter, never block the event loop with blocking I/O on the request path.
10. Use WebTestClient to verify HTTP responses and default capabilities before/after the change.
11. If multiple configurers exist, document each class's responsibility and test their combined effect.
12. When upgrading Spring Boot, read the changelog for WebFlux auto-configuration and the exact version's packages/APIs.

## 15. Official Documentation

- [Spring Boot 3.5 – Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): guidance on WebFluxConfigurer without @EnableWebFlux, codecs, static resources, and reactive servers.
- [Spring Framework 6.2 – WebFlux Config](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html): callbacks such as addFormatters, configureHttpMessageCodecs, addResourceHandlers, and configurePathMatching.
- [Spring Framework 6.2 – CORS](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-cors.html): global CORS configuration, allowed origins, and credentials.
- [Spring Framework 6.2 – WebFluxConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/web/reactive/config/WebFluxConfigurer.html): scope and signatures of configuration methods.
- [Spring Boot 3.5 – Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): spring.http.codecs.max-in-memory-size, spring.webflux.static-path-pattern, and related properties.

**Remember:** In Spring Boot WebFlux, **@Configuration implements WebFluxConfigurer without @EnableWebFlux** is the natural way to add CORS, formatters, codecs, and static resource handlers while still leveraging Boot defaults. Prove this with tests for both new features and existing auto-configured capabilities, especially JSON codecs and static resources.