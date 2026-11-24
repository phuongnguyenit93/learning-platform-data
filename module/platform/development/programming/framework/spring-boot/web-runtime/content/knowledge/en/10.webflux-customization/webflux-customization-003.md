# Impact of @EnableWebFlux and How to Customize Spring WebFlux While Keeping Spring Boot Auto-Configuration

> **Scope:** Spring Boot **3.5.x**, Spring Framework **6.2.x**, **Java 17+**, **reactive** HTTP applications using `spring-boot-starter-webflux` (examples default to Reactor Netty). The goal is to understand exactly what happens when `@EnableWebFlux` is added, why Spring Boot normally **does not need** this annotation, and when to use `WebFluxConfigurer`, application properties, `CodecCustomizer`, or `WebHttpHandlerBuilderCustomizer`. The full example uses Spring Boot **3.5.0** to keep Java code, Maven, and configuration consistent.

## 1. The Practical Question: Is Adding @EnableWebFlux to "Turn On WebFlux" Right?

In a standard Spring Boot application, you only need:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

and the entry point:

~~~java
@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

When conditions are met and no overriding configuration is present, **Spring Boot auto-configures Spring WebFlux**. You do not need to add `@EnableWebFlux` for controllers using `Mono`/`Flux` to work.

Example reactive endpoint:

~~~java
@RestController
class HelloController {
    @GetMapping("/hello")
    Mono<String> hello() {
        return Mono.just("hello webflux");
    }
}
~~~

The snippet above is an **illustrative class**, not a standalone Java file; it requires importing `Mono`, `@RestController`, and `@GetMapping`, and placing it in a project with the WebFlux starter. When running on the proper WebFlux stack, a `GET /hello` request can be handled **without `@EnableWebFlux`**.

There is an important distinction in meaning:

- **WebFlux Starter:** puts the required libraries and configuration onto the classpath so Boot recognizes and initializes a reactive application.
- **`@SpringBootApplication`:** enables Spring Boot's auto-configuration mechanism, including WebFlux when conditions are met.
- **`@EnableWebFlux`:** instructs Spring Framework to configure WebFlux directly, aimed at **taking full control of WebFlux configuration**; in a Boot application, it is **not** simply a switch to enable WebFlux.

## 2. What Does Spring Boot Auto-Configure Without @EnableWebFlux?

Spring WebFlux supplies the asynchronous HTTP processing foundation: `DispatcherHandler`, `HandlerMapping`, `HandlerAdapter`, `HttpMessageReader`, `HttpMessageWriter`, WebFlux.fn routers, conversion/validation, and more.

Spring Boot adds integrations and sensible defaults for the application. In Boot 3.5, notable groups include:

1. **HTTP codec configuration**: readers/writers for JSON, text, and other representations, along with Boot's codec and Jackson configuration.
2. **Static resources**: automatic serving of resources from classpath locations such as `/static`, `/public`, `/resources`, and `/META-INF/resources`, plus WebJars support.
3. **Resource paths and welcome page**: wiring Boot properties such as `spring.webflux.static-path-pattern` and default locations.
4. **Binding/formatting integration** with Boot properties where appropriate.
5. **Other Boot ecosystem mechanisms**: embedded reactive server, health/management, error handling, HTTP handler customizers, and per-auto-configuration settings.

Not all of these groups are created by a single configuration class. For example, the embedded Reactor Netty server and error handling have their own auto-configurations; **you must not conclude that adding `@EnableWebFlux` disables all of Spring Boot**.

### Normal Flow

~~~text
@SpringBootApplication
        |
        v
Spring Boot checks classpath + WebApplicationType.REACTIVE
        |
        v
WebFluxAutoConfiguration (+ related auto-configs)
        |
        +-- matching WebFlux infrastructure beans
        +-- Boot-managed codec integration
        +-- Boot-managed resource mappings and welcome page
        +-- applies additional WebFluxConfigurer beans
        |
        v
DispatcherHandler processes requests
        |
        +-- @RestController
        +-- WebFlux.fn RouterFunction / HandlerFunction
~~~

A critical condition is that the application actually runs **REACTIVE**. If a project includes both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot normally selects **Servlet MVC** when detecting the web application type. Having `WebClient` or `Mono` on the classpath does not prove the server is running WebFlux.

## 3. What Does @EnableWebFlux Do at the Spring Framework Layer?

Syntax:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.EnableWebFlux;

@Configuration
@EnableWebFlux
public class ManualWebFluxConfiguration {
}
~~~

`@EnableWebFlux` imports Spring Framework's `DelegatingWebFluxConfiguration`. That class builds on `WebFluxConfigurationSupport` to create the core WebFlux configuration beans and collect beans implementing `WebFluxConfigurer`.

Model:

~~~text
@Configuration + @EnableWebFlux
        |
        v
Spring Framework: DelegatingWebFluxConfiguration
        |
        +-- WebFluxConfigurationSupport
        +-- RequestMappingHandlerMapping/Adapter
        +-- RouterFunctionMapping/HandlerFunctionAdapter
        +-- codecs/readers/writers, conversion, validation...
        +-- delegates to WebFluxConfigurer beans registered by the project
        |
        v
WebFlux runs with framework config + your customizations
~~~

**Key point:** In a Spring Boot application, when you declare foundational WebFlux configuration yourself via `@EnableWebFlux`, Boot's **WebFlux-specific auto-configuration** will **back off / stop applying in default mode**. As a result, some default customizations and property-based integrations provided by Boot may no longer behave identically.

The outcome is not "the app loses WebFlux." Spring Framework still registers the core components to handle reactive requests. The difference is **who owns the WebFlux configuration**:

| Mode | Component driving WebFlux configuration | Purpose |
|---|---|---|
| Boot default | Spring Boot + integrated WebFlux configuration | Common defaults, applies Boot properties |
| Boot + `WebFluxConfigurer`, **without** `@EnableWebFlux` | Boot keeps the foundation, you add callbacks | Moderate customization, minimal loss of defaults |
| `@EnableWebFlux` | Spring Framework `DelegatingWebFluxConfiguration` | Framework-level control of WebFlux |
| Extending `DelegatingWebFluxConfiguration` | Project deeply overrides beans/config | Full customization for special cases |

Do not add `@EnableWebFlux` out of habit just because the annotation name contains "Enable." It **changes the configuration ownership model**, rather than merely toggling on a disabled feature.

## 4. Observable Changes After Adding @EnableWebFlux

### 4.1. Static resources may lose Boot's automatic behavior

With Boot WebFlux auto-configuration, the file:

~~~text
src/main/resources/static/status.txt
~~~

can typically be served at `/status.txt`. Boot also allows:

~~~properties
spring.webflux.static-path-pattern=/assets/**
~~~

to serve matching static resources under `/assets/**`. In standard Boot mode, `GET /assets/status.txt` reads the file from the default static directory.

When switching to `@EnableWebFlux`-managed WebFlux configuration, resource mappings prepared by **Boot** may no longer be present, so the same URL may return 404 **if you have not configured it yourself**. To keep serving resources, you must add an explicit mapping using `WebFluxConfigurer#addResourceHandlers` or an equivalent mechanism.

This differs from whether a JSON controller `GET /api/hello` still runs: annotation handler mappings may still be configured by Spring Framework, while Boot's static file mappings have changed.

### 4.2. HTTP codecs still exist, but Boot customizations are not always intact

Spring WebFlux needs `HttpMessageReader`/`HttpMessageWriter` to read and write HTTP bodies. `@EnableWebFlux` still provides **Spring Framework's** default codec setup depending on the classpath.

What must be checked is **Spring Boot's** integration layer:

- HTTP codec buffer limits;
- JSON/Jackson customizations via `spring.jackson.*`;
- `CodecCustomizer` beans integrated by Boot;
- how the application registers specialized codecs;
- differences in how WebClient and server codecs are configured.

**Do not claim "@EnableWebFlux stops JSON from working."** If Jackson is still on the classpath, the framework can read/write JSON normally. However, **codec configuration details** may differ and must be verified with tests.

In Spring Boot 3.5, a buffer-related property is:

~~~properties
spring.http.codecs.max-in-memory-size=2MB
~~~

This property targets **auto-configured WebFlux server and WebClient instances**. You cannot assume it continues to govern every codec created under manual WebFlux configuration mode. When configuring manually, use the specific codec API to set the corresponding limit.

### 4.3. Boot WebFlux properties may need manual reconfiguration

WebFlux-related properties commonly seen in projects:

~~~properties
spring.webflux.base-path=/gateway
spring.webflux.static-path-pattern=/assets/**
spring.web.resources.static-locations=classpath:/static/
spring.webflux.format.date=dd/MM/yyyy
spring.http.codecs.max-in-memory-size=2MB
~~~

In auto-configuration mode, Boot binds and wires these properties. When enabling `@EnableWebFlux` to take control of configuration, you must **verify each property individually** rather than assuming every value is still wired by Boot into the corresponding component.

**Do not interpret this as "every Spring Boot property becomes void."** For example, `server.port` belongs to the embedded web server configuration, not solely `WebFluxAutoConfiguration`. It can continue to work even when WebFlux request mappings are configured manually.

### 4.4. Welcome page, WebJars, error handling, and integrations

Boot-related features such as the welcome page, WebJars resource locations, template engines, custom error responses, and Actuator should be tested when changing how WebFlux is configured.

However, distinguish **the conditions of each auto-configuration**. Some error handling or management components may still be managed by Boot via separate auto-configurations. Do not claim `@EnableWebFlux` definitely disables all `ErrorWebExceptionHandler` beans or stops Actuator from running.

The reliable assessment is comparing actual behavior: URLs/responses, bean configuration, and condition evaluation before and after, rather than looking solely at annotation names.

## 5. Which Customization Approach Should You Choose? A Safety Ladder

**Prefer customizing from least invasive to more control:**

| Need | Prefer using first | Need `@EnableWebFlux`? |
|---|---|---|
| Change HTTP port | `server.port` | No |
| Set WebFlux base path | `spring.webflux.base-path` | No |
| Change static URL pattern | `spring.webflux.static-path-pattern` | No |
| Change static file locations | `spring.web.resources.static-locations` | No |
| Adjust Boot HTTP codec buffer | `spring.http.codecs.max-in-memory-size` | No |
| Add CORS for reactive controllers | `WebFluxConfigurer#addCorsMappings` | No |
| Add formatters/converters | `WebFluxConfigurer#addFormatters` | No |
| Add custom static resource handler | `WebFluxConfigurer#addResourceHandlers` | No |
| Change codec details | `CodecCustomizer` or `configureHttpMessageCodecs` | No |
| Customize Boot's `HttpHandler` | `WebHttpHandlerBuilderCustomizer` | No |
| Own the entire WebFlux infrastructure | `@EnableWebFlux` + full configuration | Possibly |
| Override core Spring Framework configuration beans | Extend `DelegatingWebFluxConfiguration` when truly needed | Architecture-dependent |

The reason for this order: the deeper the control, the more you must manually recreate and maintain useful defaults that Spring Boot previously assembled for you.

## 6. Recommended Alternative: WebFluxConfigurer Without @EnableWebFlux

Create a configuration class:

~~~java
package com.example.webfluxdemo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class ApiWebFluxConfig implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://frontend.example")
                .allowedMethods("GET", "POST", "OPTIONS")
                .allowedHeaders("Content-Type", "Authorization")
                .maxAge(1800);
    }
}
~~~

In a reactive Spring Boot application, this class **adds a CORS mapping** while Boot retains the opportunity to preserve other default configurations such as codecs and static resources.

Explanation:

1. `@Configuration` declares a Spring bean; `proxyBeanMethods=false` is appropriate when the class does not use inter-bean `@Bean` method calls.
2. `implements WebFluxConfigurer` registers callbacks into the framework's WebFlux configuration mechanism.
3. `addCorsMappings` configures a CORS rule for the `/api/**` path. Here only the origin `https://frontend.example` is permitted as an example.
4. No `@EnableWebFlux`: **does not take ownership away from Boot WebFlux auto-configuration**.
5. CORS governs whether browsers allow web apps to read cross-origin responses; **it does not replace authentication or authorization**.

Restrict origins explicitly rather than allowing `*` when the application uses credentials/cookies or serves sensitive data. With reactive Spring Security, ensure CORS preflight is handled in the right order within `SecurityWebFilterChain`; adding MVC callbacks is not the way to fix WebFlux security.

## 7. Complete Spring Boot WebFlux Example with Boot Auto-Configuration Preserved

The project uses **Maven**, **Java 17**, **Spring Boot 3.5.0**, and **Reactor Netty** via `spring-boot-starter-webflux`. The app includes a reactive controller, a static file, and CORS. The goal is to demonstrate customizing CORS **without `@EnableWebFlux`**.

### 7.1. Project Structure

~~~text
webflux-custom-demo/
  pom.xml
  src/main/java/example/webflux/
    WebfluxCustomDemoApplication.java
    GreetingController.java
    ApiWebFluxConfig.java
  src/main/resources/
    application.properties
    static/status.txt
  src/test/java/example/webflux/
    WebFluxCustomDemoIntegrationTest.java
~~~

### 7.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>webflux-custom-demo</artifactId>
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

Do not add `spring-boot-starter-web` just to use `@RestController`: that same annotation is supported by WebFlux, while the Servlet Web starter can cause Boot to choose **MVC** instead of reactive when detecting the application type. This example includes only the WebFlux starter.

### 7.3. Entry Point

`src/main/java/example/webflux/WebfluxCustomDemoApplication.java`:

~~~java
package com.example.webfluxdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebfluxCustomDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebfluxCustomDemoApplication.class, args);
    }
}
~~~

No `@EnableWebFlux`. With the right starter present, `@SpringBootApplication` is sufficient for Boot to auto-configure WebFlux.

### 7.4. Reactive Controller: GET and POST JSON

`src/main/java/example/webflux/GreetingController.java`:

~~~java
package com.example.webfluxdemo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class GreetingController {

    @GetMapping(
        path = "/hello",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Message> hello(
            @RequestParam(defaultValue = "world") String name) {

        return Mono.just(new Message("Hello, " + name));
    }

    @PostMapping(
        path = "/echo",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Message> echo(@RequestBody Mono<Message> requestBody) {
        return requestBody.map(
                body -> new Message("Echo: " + body.message())
        );
    }

    public record Message(String message) {
    }
}
~~~

Explanation:

- `Mono<Message>` represents an asynchronous result (at most one element).
- For GET, `@RequestParam` binds `name`; the JSON response is encoded by the WebFlux codec without manually creating an `ObjectMapper` in the controller.
- For POST, `@RequestBody Mono<Message>` lets WebFlux read the JSON body in a reactive pipeline; processed with `map` without calling `block()`.
- `Message` is a Java 17 record; the JSON field name is `message`.
- The code performs no DB queries or blocking I/O, making it suitable for learning configuration mechanics before introducing complex logic.

**CORS config:** use the `ApiWebFluxConfig.java` file from section 6 verbatim; it is in the same `com.example.webfluxdemo` package so it is picked up by component scanning. Do not add `@EnableWebFlux` to this file in the recommended branch of the example.

### 7.5. Properties and Static Resources

`src/main/resources/application.properties`:

~~~properties
server.port=8080

# Boot WebFlux configuration for static resources.
spring.webflux.static-path-pattern=/assets/**

# Memory buffer limit for HTTP codecs auto-configured by Boot.
spring.http.codecs.max-in-memory-size=2MB
~~~

`src/main/resources/static/status.txt`:

~~~text
static-ok
~~~

The `status.txt` file contains the line `static-ok`. By default, Spring Boot knows the `classpath:/static/` location; with the pattern above, the file's URL is `/assets/status.txt`.

**There is no `spring.webflux.base-path`** in this example, keeping three factors distinct: route `/api/hello` comes from the annotation, static prefix `/assets/**` comes from the property, and CORS path `/api/**` comes from `WebFluxConfigurer`. Values do not combine ambiguously.

## 8. Running the Program and Testing HTTP

Prerequisites: JDK 17+, Maven, port 8080 free.

~~~bash
mvn spring-boot:run
~~~

Or:

~~~bash
mvn clean package
java -jar target/webflux-custom-demo-1.0.0.jar
~~~

### 8.1. Calling GET JSON

~~~bash
curl -i "http://localhost:8080/api/hello?name=Lan"
~~~

Expected response body:

~~~json
{"message":"Hello, Lan"}
~~~

Expected HTTP status `200 OK`. Other headers, timestamps, and formatting order may vary by server/client; the JSON snippet represents the body only.

### 8.2. Calling POST JSON

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/echo" \
  -H "Content-Type: application/json" \
  -d '{"message":"Hi"}'
~~~

Expected body:

~~~json
{"message":"Echo: Hi"}
~~~

The command uses Unix/Bash shell syntax. In Windows PowerShell, use `curl.exe` with PowerShell quoting syntax, or use another HTTP client; do not copy multiline `\` commands directly and expect PowerShell to parse them like Bash.

### 8.3. Static File

~~~bash
curl -i "http://localhost:8080/assets/status.txt"
~~~

Response status `200`, body contains the line:

~~~text
static-ok
~~~

This demonstrates that Boot's static resource mapping remains active **alongside** the `WebFluxConfigurer` class customizing CORS.

### 8.4. CORS Preflight

~~~bash
curl -i -X OPTIONS \
  "http://localhost:8080/api/hello" \
  -H "Origin: https://frontend.example" \
  -H "Access-Control-Request-Method: GET"
~~~

With the sample configuration, a valid preflight receives a 2xx response in which the `Access-Control-Allow-Origin` header has the value:

~~~text
https://frontend.example
~~~

When replacing `Origin` with a disallowed domain, preflight will not grant the same CORS permission. Do not assume CORS blocks requests from curl or server-to-server clients: CORS is a browser-side mechanism, not an authentication mechanism.

## 9. Real HTTP Integration Test: Verifying API, Static Resource, and CORS Together

Use the JDK `HttpClient` (built into Java 17) to send requests to a **real reactive embedded server**, rather than only invoking controller methods.

`src/test/java/example/webfluxdemo/WebFluxCustomDemoIntegrationTest.java`:

~~~java
package com.example.webfluxdemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebFluxCustomDemoIntegrationTest {

    @LocalServerPort
    private int port;

    private final HttpClient client = HttpClient.newHttpClient();

    private URI url(String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }

    @Test
    void getControllerUsesJsonCodec() throws Exception {
        assertTrue(port > 0);

        HttpRequest request = HttpRequest.newBuilder(
                url("/api/hello?name=Lan"))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals(
                "{\"message\":\"Hello, Lan\"}",
                response.body());
    }

    @Test
    void postControllerReadsJsonBody() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(url("/api/echo"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{\"message\":\"Hi\"}"))
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals(
                "{\"message\":\"Echo: Hi\"}",
                response.body());
    }

    @Test
    void bootServesStaticResource() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                url("/assets/status.txt"))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("static-ok", response.body().trim());
    }

    @Test
    void webFluxConfigurerAddsCorsRule() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                url("/api/hello"))
                .header("Origin", "https://frontend.example")
                .header("Access-Control-Request-Method", "GET")
                .method("OPTIONS", HttpRequest.BodyPublishers.noBody())
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertTrue(
                response.statusCode() >= 200 &&
                response.statusCode() < 300
        );

        assertEquals(
                "https://frontend.example",
                response.headers()
                        .firstValue("Access-Control-Allow-Origin")
                        .orElse("")
        );
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The test suite verifies four independent aspects:

1. Annotation-based controllers are routed properly by WebFlux.
2. The JSON codec reads and writes bodies correctly.
3. Spring Boot's static mapping still serves the file via `spring.webflux.static-path-pattern`.
4. `WebFluxConfigurer` applied CORS without needing `@EnableWebFlux`.

`@SpringBootTest(RANDOM_PORT)` starts a real server on a random port, and `@LocalServerPort` is injected after server startup. `mvn test` runs integration tests under Spring Boot Test, not just Mockito mocks.

**Why is this useful?** If someone later adds `@EnableWebFlux` and Boot's static mapping disappears, the `bootServesStaticResource` test will catch the change. That is far more valuable than concluding everything works just because the app starts without errors.

## 10. When @EnableWebFlux Is Truly Needed: Restoring What You Use

There may be cases where you want to design the entire WebFlux infrastructure yourself—for example, a specialized custom platform that does not use Boot's default resource mappings.

In that scenario, you **can** use `@EnableWebFlux`, but you take responsibility for the components your application actually needs. Below is **an alternative configuration**, used **in place of** `ApiWebFluxConfig.java` in section 6; **do not register both classes** in the same project.

`src/main/java/example/webflux/ManualWebFluxConfig.java`:

~~~java
package com.example.webfluxdemo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.EnableWebFlux;
import org.springframework.web.reactive.config.ResourceHandlerRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
@EnableWebFlux
public class ManualWebFluxConfig implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://frontend.example")
                .allowedMethods("GET", "POST", "OPTIONS")
                .allowedHeaders("Content-Type", "Authorization");
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/static/");
    }

    @Override
    public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(2 * 1024 * 1024);
    }
}
~~~

Characteristics of this code:

- `@EnableWebFlux` switches to Spring Framework's configuration mechanism for WebFlux.
- `addCorsMappings` re-adds the CORS rule needed by the application.
- `addResourceHandlers` serves `/assets/**` from the static classpath folder; **do not assume** Boot properties configure this mapping anymore.
- `configureHttpMessageCodecs` sets the buffer limit for **default codecs** using the Spring Framework API; do not assume Boot properties still apply to every codec once WebFlux is managed manually.
- Default JSON codecs can still work based on existing dependencies; this example **does not intentionally disable** default codec registration.

**Important:** these are only illustrative components to preserve the three contracts of the sample project: JSON, CORS, and static resources. This is **not a complete replica** of Spring Boot's WebFlux auto-configuration. If the project uses WebJars, a welcome page, template engines, error rendering, conversion, validation, multipart, or customized Jackson codecs, you must configure the appropriate beans/settings manually.

When full control over Spring WebFlux is genuinely intended, this approach can fit, provided you measure and test changes feature by feature. For most Spring Boot APIs, the solution in section 6 is much lower risk.

## 11. Advanced Mechanisms: DelegatingWebFluxConfiguration and HttpHandler

### 11.1. `DelegatingWebFluxConfiguration`

`@EnableWebFlux` imports `DelegatingWebFluxConfiguration`. This component gathers `WebFluxConfigurer` beans and provides Spring Framework's default WebFlux beans.

If you need to intervene **below** the `WebFluxConfigurer` callback level, Framework documentation allows extending it directly:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.DelegatingWebFluxConfiguration;

@Configuration
public class AdvancedWebFluxConfiguration
        extends DelegatingWebFluxConfiguration {
    // Only override beans/configuration once you understand the mechanism.
}
~~~

This is a **skeleton class illustrating advanced mode**, not a configuration to drop directly into the section 7 project. When choosing this approach, do not also place `@EnableWebFlux` on the same class as if both were needed; doing so can create duplicate or conflicting configuration definitions.

Be careful when overriding beans like `RequestMappingHandlerMapping` or `RequestMappingHandlerAdapter`. Done incorrectly, controllers may not be discovered or handlers may lack a matching adapter.

### 11.2. `WebHttpHandlerBuilderCustomizer`

For applications using Boot's auto-configured `HttpHandler` that need to insert a customization into how the handler pipeline is built, Boot supports `WebHttpHandlerBuilderCustomizer` beans. This is a specialized customizer distinct from `WebFluxConfigurer`.

Use it **when the requirement genuinely belongs at the `WebHttpHandlerBuilder` level**, such as custom integration into the HTTP processing pipeline. Do not use `@EnableWebFlux` just to modify part of the pipeline when Boot already offers a suitable extension point. Low-level customizations must be evaluated alongside Security `WebFilterChain`, exception handling, and request tracing; do not bypass protective filters.

### 11.3. `CodecCustomizer`

Boot 3.5 includes `org.springframework.boot.web.codec.CodecCustomizer`. You can register a bean to adjust the `CodecConfigurer` used by auto-configuration:

~~~java
package com.example.webfluxdemo;

import org.springframework.boot.web.codec.CodecCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CodecSettings {

    @Bean
    CodecCustomizer bufferLimit() {
        return configurer ->
                configurer.defaultCodecs()
                          .maxInMemorySize(512 * 1024);
    }
}
~~~

This is an **optional extra file** when API customization is needed; it is not required for the section 7 project. If `spring.http.codecs.max-in-memory-size` already satisfies your need, avoid setting conflicting limits in both the property and a `CodecCustomizer` without verifying override order/semantics.

**Do not disable defaults recklessly** with `configurer.registerDefaults(false)` and forget to re-register JSON/text codecs. When making deep adjustments, verify response `Content-Type`, status codes, serialization, and response body limits at the real HTTP layer.

## 12. CORS, WebFilter, Security, and RouterFunction: Choosing the Right Extension Point

### 12.1. Global CORS and Per-Handler CORS

WebFlux supports configuring CORS via `WebFluxConfigurer#addCorsMappings`, while annotated handlers can also use `@CrossOrigin`. Maintain a consistent convention between global and local rules to avoid overly permissive settings.

With WebFlux.fn functional routers, appropriate filter/router mechanisms may need separate configuration depending on architecture. Do not assume every CORS rule designed for annotated controllers will automatically cover all functional routes and WebSocket handshakes.

### 12.2. Reactive WebFilter

WebFlux uses `org.springframework.web.server.WebFilter`. This is the reactive abstraction conceptually equivalent to middleware—**not** Spring MVC's `jakarta.servlet.Filter`.

A `WebFilter` for logging, correlation IDs, or header handling can be registered as a Spring bean without `@EnableWebFlux`. Filter logic must respect the reactive execution model: avoid blocking event-loop threads with synchronous network or database calls.

### 12.3. Spring Security

Reactive Spring Security uses `SecurityWebFilterChain`. Adding or removing `@EnableWebFlux` **should never** be treated as a way to toggle authentication. CORS preflight, route policies, and authentication require tests for 401/403, CSRF (where applicable), credentials, origin whitelists, and error responses.

Do not handle security by turning every `OPTIONS` request into `200` in application code. Use proper CORS and Security mechanisms, permitting origins, methods, and headers according to policy.

## 13. WebFlux vs. Spring MVC: Avoiding Confusion Between Similarly Named Annotations

| Topic | Spring WebFlux (reactive) | Spring MVC (Servlet) |
|---|---|---|
| Common starter | `spring-boot-starter-webflux` | `spring-boot-starter-web` |
| Dispatcher | `DispatcherHandler` | `DispatcherServlet` |
| Extension callback | `WebFluxConfigurer` | `WebMvcConfigurer` |
| Full-control annotation | `@EnableWebFlux` | `@EnableWebMvc` |
| Filter | `WebFilter` | `jakarta.servlet.Filter` |
| Functional handlers | `org.springframework.web.reactive.function.server.*` | `org.springframework.web.servlet.function.*` |
| Default server in Boot | Reactor Netty | Embedded Tomcat |
| Core HTTP request/response | `ServerWebExchange` | `HttpServletRequest`/`HttpServletResponse` |

**Adding `@EnableWebFlux` to an MVC project does not convert the project to WebFlux**. Spring Boot inspects the classpath and `WebApplicationType`; when both MVC and WebFlux starters are present, Boot typically defaults to MVC.

Also do not confuse `@EnableWebFlux` with reactive Spring Security's `@EnableWebFluxSecurity`: those serve two different configuration purposes.

WebFlux supports non-blocking I/O, but **does not automatically make blocking business code non-blocking**. If a handler still invokes blocking JDBC drivers or `Thread.sleep` directly on the event loop, adding `@EnableWebFlux` will not solve thread starvation.

## 14. How to Check Whether Boot Still Applies Auto-Configuration

### 14.1. Start from Application Behavior

After changing configuration, run tests for:

- `GET` and `POST` JSON, status codes, Content-Type, conversion.
- Static resources, welcome page, WebJars URLs (if used).
- Request size/codec buffer limits and error responses when bodies exceed limits.
- CORS preflight and actual requests.
- 404/400/415/500 error handling, and Problem Details if enabled.
- Formatting/validation, query/path binding, and custom converters.
- Spring Security login/authorization, headers, and filter chain.
- Base path, proxy rewrites, WebSocket/SSE, reactive context propagation.
- Health/Actuator endpoints if the application relies on them.

For the sample project in section 7, the three most useful contracts to detect changes are: **JSON codec**, **static URL `/assets/status.txt`**, and **CORS origin `https://frontend.example`**.

### 14.2. Spring Boot's Condition Evaluation Report

You can run the app with `--debug` in development:

~~~bash
java -jar target/webflux-custom-demo-1.0.0.jar --debug
~~~

Spring Boot prints the **condition evaluation report** listing which auto-configurations matched or did not match. Look for entries related to `WebFluxAutoConfiguration` to see why Boot no longer supplies the MVC/reactive configuration you expected.

`--debug` does not prove all runtime behavior is correct: it only lets you inspect configuration conditions. Avoid enabling broad DEBUG logging in production, as it can generate heavy log volume and expose HTTP details.

If the app includes Actuator, `/actuator/conditions` can aid diagnostics, but it must be secured and never exposed publicly.

### 14.3. Inspecting the Application Type

If logs show Tomcat/Servlet MVC and `DispatcherServlet` in a project you thought was reactive Netty WebFlux, inspect the dependency graph:

~~~bash
mvn dependency:tree
~~~

Look for `spring-boot-starter-web`, `spring-boot-starter-webflux`, `spring-boot-starter-tomcat`, and `spring-boot-starter-reactor-netty`. Do not use `@EnableWebFlux` to mask an unintended web application type selection.

### 14.4. Different Test Scopes

`@WebFluxTest` is a test slice for testing controllers within WebFlux scope; it does not automatically load all `@Configuration` classes and services like a full context. Therefore, you may need `@Import` to include custom configuration in a slice test, or use `@SpringBootTest(RANDOM_PORT)` when verifying full Boot auto-configuration, resource mappings, and the network path.

Do not treat a test that merely initializes a controller as proof that Boot is serving static resources, applying customized codecs, or enforcing CORS preflight.

## 15. Common Issues and Fixes

| Symptom | Causes to check | Resolution |
|---|---|---|
| WebFlux app already ran, then `@EnableWebFlux` added because someone thought it was required | Misunderstood annotation role | Remove `@EnableWebFlux` if Boot defaults are desired |
| `GET /api/hello` works, but `/assets/status.txt` returns 404 after config change | Boot static mapping may have been displaced | Use `WebFluxConfigurer` without `@EnableWebFlux`, or register `addResourceHandlers` |
| `spring.webflux.static-path-pattern` no longer has the same effect | Managing WebFlux manually; Boot property no longer wires into resource handler | Configure explicitly in `ResourceHandlerRegistry` |
| Buffer limit differs from expectation | Boot codec customization no longer applied the same way | Check `spring.http.codecs.*` and the active `ServerCodecConfigurer` |
| JSON body 415/400 error or different encoding | Codec registrations or media types changed | Check Jackson dependency, readers/writers, request headers, codec customizers |
| CORS preflight blocked | Origin/method/header not permitted, or Security filter interferes | Configure `CorsRegistry` and `SecurityWebFilterChain`, test real OPTIONS |
| Spring Boot runs MVC despite adding WebFlux | Both web starters present or WebApplicationType remains Servlet | Review dependencies and pick the right stack; do not rely on `@EnableWebFlux` |
| `@EnableWebFlux` and custom configuration class create duplicate beans | Multiple sources configuring WebFlux infrastructure | Choose one configuration ownership model; do not combine both advanced modes |
| Error JSON or welcome page differs from before | Boot WebFlux extensions may have changed | Inspect auto-config, custom error handlers, and resource mappings |
| Slice test passes but real app returns 404 | Test did not load all components/config/static resources | Use full `@SpringBootTest(RANDOM_PORT)` |
| CORS config mistaken for authentication | CORS only restricts browsers, does not stop server clients | Apply separate authentication/authorization |
| Event loop stalls after enabling WebFlux | Blocking logic in handler/filter | Use reactive drivers or offload blocking work onto an appropriate scheduler |

### 15.1. Avoid Accidentally Duplicating WebFlux Configuration

The following two snippets **should not coexist** as two ways to "enable WebFlux":

~~~java
@Configuration
@EnableWebFlux
class FirstConfig {
}
~~~

~~~java
@Configuration
class SecondConfig extends DelegatingWebFluxConfiguration {
}
~~~

These are **two classes illustrating conflicting configuration modes**, not runnable source from the sample project. Registering multiple foundational configurations can cause bean name conflicts or unpredictable lifecycle effects. Choose one approach deliberately.

### 15.2. Do Not "Fix" Missing Static Resources with Arbitrary File-Serving Controllers

If static files disappear due to a missing `ResourceWebHandler`, the proper fix is usually restoring the resource handler. Writing `@GetMapping("/assets/**")` and reading the filesystem with unvalidated paths can introduce path traversal vulnerabilities, caching bugs, and wrong content types.

### 15.3. Do Not Apply MVC Configuration Classes to WebFlux

`WebMvcConfigurer` and `@EnableWebMvc` do not configure reactive HTTP handlers. Use the right package:

~~~java
import org.springframework.web.reactive.config.WebFluxConfigurer;
import org.springframework.web.reactive.config.EnableWebFlux;
~~~

Do not confuse them with:

~~~java
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
~~~

These two import blocks are purely for **package comparison**; do not add all four lines to the same project unless you genuinely run both stacks and understand their respective configurations.

## 16. Process for Migrating from @EnableWebFlux to Spring Boot-Compatible Configuration

If a project currently has `@EnableWebFlux` but only needs a few customizations, migrate carefully:

1. **Scope behaviors to preserve:** all controller routes, WebFlux.fn routes, CORS, codecs, static resources, error formats, WebSocket/SSE, validation, and filters/security.
2. **Identify the customizations actually needed:** for example, only `addCorsMappings`, adding a converter, or changing the static resource prefix.
3. **Move simple settings to properties:** `spring.webflux.static-path-pattern`, `spring.web.resources.static-locations`, `spring.http.codecs.max-in-memory-size`, etc., matching your Boot version.
4. **Move remaining callbacks to `WebFluxConfigurer`:** keep `@Configuration` but **remove `@EnableWebFlux`**.
5. **Migrate codec customizations if needed:** consider `CodecCustomizer` or `configureHttpMessageCodecs`; avoid rewriting all default codecs.
6. **Run regression tests before deleting manual config:** avoid losing formatters, resource handlers, global CORS, or special beans the project depends on.
7. **Inspect the condition report:** confirm Boot's WebFlux auto-configuration applies as intended and no manual bean still causes it to back off.
8. **Deploy across environments:** verify URLs behind proxy/ingress, CORS headers, error responses, and telemetry before going to production.

Do not abruptly delete `@EnableWebFlux` in a large application if it was used to override many core beans: first inventory all overrides, design their replacements, and add verification tests.

## 17. Final Selection and Verification Checklist

- [ ] The project truly uses **Spring WebFlux reactive**, not MVC merely adding WebClient.
- [ ] `spring-boot-starter-webflux` and an appropriate `@SpringBootApplication` configuration are present.
- [ ] **Do not add `@EnableWebFlux`** if you only want to use WebFlux with Boot defaults.
- [ ] Simple changes use Boot properties wherever possible.
- [ ] Additional WebFlux customization uses `WebFluxConfigurer` **without `@EnableWebFlux`**.
- [ ] Codec tuning uses `spring.http.codecs.*` properties or Boot `CodecCustomizer` when needed.
- [ ] CORS is configured specifically and does not substitute for authentication/authorization.
- [ ] Tests cover JSON controllers, static resources, CORS, and error formats.
- [ ] If `@EnableWebFlux` is used, required resources/codecs/formatters are reconfigured and you understand you manage WebFlux yourself.
- [ ] You do not assume all Spring Boot auto-configuration is disabled; evaluate only the relevant classes and beans.
- [ ] Before/after regression tests and a rollback plan exist when changing reactive configuration.

## Official Documentation

- [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): describes WebFlux auto-configuration, codecs, static resources, `WebFluxConfigurer`, and `@EnableWebFlux`.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.http.codecs.max-in-memory-size`, `spring.webflux.static-path-pattern`, `spring.web.resources.static-locations`.
- [Spring Framework 6.2 — WebFlux Config](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html): `@EnableWebFlux`, `WebFluxConfigurer`, `DelegatingWebFluxConfiguration`, CORS, codecs, and resources.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@WebFluxTest` and `@SpringBootTest`.
- [Spring Boot 3.5 — WebFluxAutoConfiguration Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/WebFluxAutoConfiguration.html): Spring Boot's specific WebFlux API/auto-configuration.
- [Spring Framework 6.2 — DispatcherHandler](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html): reactive request processing.

**Conclusion:** In Spring Boot, `@EnableWebFlux` is not a "required annotation to run reactive." It transfers ownership of WebFlux configuration from Spring Boot's convenient integrations to application-managed framework configuration. For most projects, **keeping Boot auto-configuration, adding `WebFluxConfigurer` without `@EnableWebFlux`, and using appropriate properties/extension points** achieves the goal with the lowest risk. Use `@EnableWebFlux` only when you intentionally want comprehensive control over WebFlux configuration and have re-tested all related behaviors.