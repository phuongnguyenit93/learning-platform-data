# spring-boot-starter-web and the Servlet Model with Spring MVC

When building a traditional HTTP application with Spring Boot, the common choice is **spring-boot-starter-web**. This starter brings Spring Web MVC and an embedded Servlet server onto the classpath so the application can accept requests, map URLs to controllers, invoke business logic, and return HTTP responses. Developers primarily write controllers, services, and configurations; Spring Framework and Spring Boot handle most of the underlying infrastructure.

This lesson focuses on Spring Boot's **Servlet web stack**: which dependencies are included, how Spring Boot starts the web server, how a request travels through the Servlet container and DispatcherServlet, and how to write, run, test, and diagnose an MVC application.

## 1. What problem does the web starter solve?

An HTTP application requires multiple cooperating components:

- A web server to open a network port and accept HTTP connections.
- A Servlet container to manage Servlets, Filters, Listeners, and request/response objects.
- A web framework to locate the matching controller, bind parameters, and convert data.
- A dependency injection container to instantiate controllers, services, and dependencies.
- JSON serialization to turn Java objects into API response payloads.
- Environment configuration to control port, context path, and runtime limits.

If assembling libraries manually, developers must coordinate numerous dependencies, versions, and initialization steps. Spring Boot provides starters along with auto-configuration so common components work with minimal configuration.

**spring-boot-starter-web** is an aggregator dependency containing components that support Servlet web application development, especially **Spring MVC**. The starter is neither the web server nor the entirety of Spring Framework. It brings the required libraries into the application; Spring Boot relies on the classpath and configuration conditions to create the appropriate beans and server.

Suitable scenarios: REST APIs, HTML-rendering MVC applications, backends with JDBC/JPA and blocking calls, business applications needing synchronous request/response handling, as well as systems using Servlet Filters, Spring Security Servlet, and traditional Java libraries.

## 2. Layers of responsibility

| Component | Role | Example |
|---|---|---|
| Your application | Defines endpoints and business logic | GreetingController, OrderService |
| Spring Framework | Manages beans and handles web requests with Spring MVC | ApplicationContext, DispatcherServlet, HandlerMapping |
| Spring Boot | Bootstraps the application, auto-configures MVC and the server | SpringApplication, WebMvcAutoConfiguration |
| Servlet container | Executes the Servlet API, Filter chain, and request/response processing | Embedded Tomcat |
| Web server connector | Accepts network connections and exchanges HTTP data | Tomcat HTTP connector |

Conceptual relationship:

~~~text
Spring Boot Application
    |
    +-- Controller / Service / Repository
    |
    +-- Spring Framework
    |     +-- IoC container / ApplicationContext
    |     +-- Spring MVC / DispatcherServlet
    |
    +-- Spring Boot
    |     +-- Bootstrap
    |     +-- Auto-configuration
    |     +-- Embedded server integration
    |
    +-- Tomcat (default when using starter-web)
          +-- HTTP Connector
          +-- Servlet container
          +-- Filters -> DispatcherServlet
~~~

The diagram illustrates how the layers collaborate; it does not mean Spring Framework can only run inside Spring Boot. You can use Spring Framework without Boot; Boot is the configuration and operational layer built on top of the Framework.

**DispatcherServlet is Spring MVC's Servlet, not the web server.** Tomcat accepts HTTP connections and invokes the Servlet. Controllers, in turn, are application beans invoked by Spring MVC via handler adapters.

## 3. Key dependencies of spring-boot-starter-web

In Spring Boot 3.3.x, the standard web starter brings in these main components:

| Group | Role |
|---|---|
| spring-boot-starter | Core Spring Boot capabilities, configuration, and logging |
| spring-web | HTTP abstractions, REST support, and foundational Spring Web components |
| spring-webmvc | DispatcherServlet, controller mapping, argument resolvers, MVC infrastructure |
| spring-boot-starter-tomcat | Embedded Tomcat server and default Servlet runtime |
| spring-boot-starter-json | Jackson integration and accompanying JSON libraries |

Spring Boot manages dependency versions via its dependency management/BOM. Applications typically do not need to specify individual versions for libraries provided by the starter.

Common misconceptions to avoid:

- **Starter web does not automatically add Spring Security.** If authentication and authorization are needed, you must add and configure the appropriate security capability.
- **Starter web does not automatically provide the full Bean Validation API/provider.** In Spring Boot 3.x, applications typically add spring-boot-starter-validation to use @Valid, @NotBlank, and constraints for request validation.
- **Jackson is included in the default JSON dependency**, though conversion depends on content type, message converters, and application configuration.
- **Tomcat is the default embedded server choice**, though it can be replaced with another Servlet server supported by Spring Boot.
- **The starter only determines part of the classpath.** Which beans are actually created also depends on auto-configuration conditions and current configuration.

Use Gradle to inspect your application's dependency graph:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

When diagnosing library conflicts, examine the actual dependency graph rather than inferring solely from the starter name.

## 4. Why does starter-web lead to a Servlet application?

Spring Boot determines the web application type based on the classpath and configuration. When the Spring MVC/Servlet stack is present without a conflicting override, Boot typically chooses **WebApplicationType.SERVLET**. It creates the appropriate web application context and configures the web server.

High-level startup steps:

~~~text
JVM runs main()
    |
SpringApplication.run(...)
    |
Read Environment and configuration sources
    |
Create ServletWebServerApplicationContext
    |
Component scan + Bean definitions
    |
Spring Boot auto-configuration
    |
Refresh ApplicationContext
    |
Create/start embedded Servlet web server
    |
Register DispatcherServlet, Filters, Listeners
    |
Application is ready to receive HTTP requests
~~~

This is a conceptual diagram of the startup lifecycle; exact callback ordering and internal context refresh details depend on the Spring Boot version.

Key auto-configurations to know:

- **ServletWebServerFactoryAutoConfiguration** prepares Servlet web server integration and the corresponding factory when conditions match.
- **DispatcherServletAutoConfiguration** creates and registers DispatcherServlet if the application has not provided a replacement configuration.
- **WebMvcAutoConfiguration** provides default MVC configuration, such as handler mappings, message conversion, static resources, and many MVC settings.

Auto-configurations are typically conditional—for instance, requiring specific classes, a Servlet web application, the absence of user-defined beans, or an enabled property. Therefore, auto-configuration should not be understood as "always creating every bean."

The @SpringBootApplication annotation also serves three main roles: marking Boot configuration, enabling auto-configuration, and enabling component scanning. The package location of the main class affects the scan scope for controllers and services. Typically, place the main class in a parent package of the application packages that need scanning.

## 5. How does a request flow through the Servlet container and Spring MVC?

Common synchronous HTTP processing flow:

~~~text
HTTP client
    |
    v
Tomcat Connector: accepts connection, reads HTTP request
    |
    v
Servlet container: HttpServletRequest / HttpServletResponse
    |
    v
Servlet Filter chain (logging, encoding, security... if configured)
    |
    v
DispatcherServlet (Spring MVC front controller)
    |
    +--> HandlerMapping: finds handler by URL, HTTP method...
    |
    +--> HandlerAdapter: invokes handler/controller method
    |      +--> argument resolvers / data binding
    |      +--> conversion and validation when configured
    |
    +--> Controller -> Service -> Repository
    |
    +--> Return value handling / HttpMessageConverter
    |
    v
Servlet container -> HTTP response -> Client
~~~

Specific terminology:

- **HttpServletRequest/HttpServletResponse:** Jakarta Servlet abstractions for request/response data.
- **Servlet Filter:** handles requests/responses at the Servlet boundary; for example logging, correlation IDs, security. A Filter can reject a request before it reaches a controller.
- **DispatcherServlet:** Spring MVC's central front controller.
- **RequestMappingHandlerMapping:** locates the matching controller method based on request mappings.
- **RequestMappingHandlerAdapter:** executes that method, supporting binding and return value handling.
- **HandlerMethodArgumentResolver:** maps path variables, query params, headers, principals, request bodies, etc. into Java parameters.
- **HttpMessageConverter:** reads the request body or writes the response body according to data type, such as JSON.
- **HandlerExceptionResolver / @ExceptionHandler:** allows converting MVC exceptions into HTTP responses according to policy.

Because filters and MVC have distinct responsibilities, a request failing to reach a controller does not prove the controller is broken. The request might have been blocked by a filter, the path might not match DispatcherServlet, the request mapping might not match, or the data might fail binding.

### 5.1. Path of a GET request

Suppose a client calls GET /api/greetings/Linh. Tomcat accepts the request; the filter chain runs if present; DispatcherServlet selects the method annotated with @GetMapping matching the pattern; Spring MVC binds the string Linh to the parameter; the controller returns a Java object; Jackson serializes the object to JSON; Tomcat sends the response.

### 5.2. Path of a POST JSON request

For POST /api/echo with Content-Type: application/json, Spring MVC uses a message converter to read JSON into the Java type declared by @RequestBody. The controller processes it and returns an object or ResponseEntity. If the body is invalid JSON, the type cannot be read, or the content type is unsupported, the request may be rejected before invoking the controller method.

### 5.3. Request-processing threads

In the common synchronous Spring MVC model, Tomcat uses a thread pool to handle multiple requests. If a service queries a database via JDBC or waits on a blocking HTTP client, the handling thread is typically occupied during the wait. As concurrent requests grow, thread exhaustion, queueing, timeouts, and throughput degradation can occur.

Servlet also supports asynchronous processing; Spring MVC provides Callable, DeferredResult, streaming, and other mechanisms. Therefore, you should not conclude that every MVC request always uses a single thread from start to finish. When estimating load capacity, examine the actual handler model and I/O dependencies.

## 6. Runnable example: Spring Boot 3.3 + Java 21 + Gradle

The example below creates a minimal HTTP Servlet application with GET and JSON POST endpoints. No separate Tomcat installation is needed; embedded Tomcat is started by starter-web and Spring Boot.

Directory structure:

~~~text
mvc-servlet-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/webdemo/
    │   ├── WebDemoApplication.java
    │   └── GreetingController.java
    └── test/java/com/example/webdemo/
        └── GreetingControllerTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'mvc-servlet-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The Spring Boot plugin provides the bootRun and bootJar tasks. The dependency-management plugin lets you use versions managed by Spring Boot; for example, you do not have to specify a version for spring-boot-starter-web.

**src/main/java/com/example/webdemo/WebDemoApplication.java**

~~~java
package com.example.webdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebDemoApplication.class, args);
    }
}
~~~

**src/main/java/com/example/webdemo/GreetingController.java**

~~~java
package com.example.webdemo;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class GreetingController {

    @GetMapping("/greetings/{name}")
    public Map<String, String> greet(@PathVariable String name) {
        return Map.of("message", "Hello, " + name);
    }

    @PostMapping("/echo")
    public ResponseEntity<Map<String, String>> echo(
            @RequestBody EchoRequest request) {
        if (request.text() == null || request.text().isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "text must not be blank");
        }
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(Map.of("echo", request.text()));
    }

    public record EchoRequest(String text) {
    }
}
~~~

In this example:

- @RestController marks a controller bean with response body serialization.
- @RequestMapping("/api") sets the prefix for endpoints.
- @GetMapping and @PostMapping bind HTTP methods and paths.
- @PathVariable extracts a URL path segment.
- @RequestBody instructs Spring MVC to read the JSON body into the EchoRequest record.
- ResponseEntity sets the HTTP status to 201 Created for a successful POST request.
- ResponseStatusException returns 400 Bad Request when text is blank; invalid JSON bodies are also typically rejected by Spring MVC during body reading.
- Each Map contains only one key per response, so the sample JSON below has predictable contents.

The example uses a simulated POST echo operation without saving data to a database. In a real application, 201 Created should correspond to creating a new resource; if only processing and returning a result without creating a resource, status 200 OK may be more appropriate.

### 6.1. Running the application

If the project already has the Gradle wrapper, run inside the mvc-servlet-demo directory:

~~~bash
./gradlew bootRun
~~~

In PowerShell on Windows, the corresponding command is .\gradlew.bat bootRun. If creating a project without a wrapper yet, generate the Gradle wrapper or use an installed Gradle; the example fits Gradle 8.5 and JDK 21.

Spring Boot typically logs Tomcat starting on port 8080, after which the application is ready. The default port can change if environment configuration or properties override it.

In another terminal (Bash syntax), test GET:

~~~bash
curl -i http://localhost:8080/api/greetings/Linh
~~~

Expected result: status **200 OK**, JSON response body:

~~~json
{"message":"Hello, Linh"}
~~~

Test POST JSON:

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
    -H "Content-Type: application/json" \
    -d '{"text":"Hello MVC"}'
~~~

Expected result: status **201 Created**, response body:

~~~json
{"echo":"Hello MVC"}
~~~

Try an empty string:

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
    -H "Content-Type: application/json" \
    -d '{"text":""}'
~~~

Expected result: status **400 Bad Request** because the controller throws ResponseStatusException. The error body depends on exception handling configuration, so do not assume it always has a fixed JSON schema.

Response headers and header ordering are not fixed; verify the status codes and JSON bodies noted above. These are expected results derived from the code, not a transcript of an actual execution.

### 6.2. Packaging an executable JAR

~~~bash
./gradlew clean bootJar
java -jar build/libs/mvc-servlet-demo-1.0.0.jar
~~~

In the example configuration, Boot packages the application along with runtime dependencies and the appropriate launcher. When running the JAR, the JVM initializes Spring Boot and then embedded Tomcat; there is no need to deploy a WAR into an external Tomcat.

## 7. Testing Spring MVC with MockMvc

Distinguish between testing MVC handlers and testing a real HTTP connection. **MockMvc** runs requests through the Spring MVC infrastructure in a test context without opening a network socket. It is very useful for testing routes, JSON conversion, validation, and status codes.

**src/test/java/com/example/webdemo/GreetingControllerTest.java**

~~~java
package com.example.webdemo;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(GreetingController.class)
class GreetingControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void getReturnsJson() throws Exception {
        mvc.perform(get("/api/greetings/Linh"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("Hello, Linh"));
    }

    @Test
    void postEchoReturnsCreated() throws Exception {
        mvc.perform(post("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"Hello MVC\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.echo").value("Hello MVC"));
    }

    @Test
    void blankTextIsRejected() throws Exception {
        mvc.perform(post("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"\"}"))
            .andExpect(status().isBadRequest());
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

@WebMvcTest focuses on the MVC slice, which is useful when a controller does not depend on many business beans. For controllers that call services, you need to mock or import the dependencies required for the test. To test a real Tomcat server, you can use @SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT) and a suitable test HTTP client; that is a different integration testing layer from a MockMvc slice.

Note: the example has not added spring-boot-starter-security, so the tests do not include login or CSRF requirements imposed by Spring Security. If a project adds Security, configure test credentials, permissions, and CSRF tokens according to actual policy.

## 8. MVC annotations you should know

| Annotation/API | Role |
|---|---|
| @RestController | @Controller combined with response body serialization |
| @Controller | Controller returning a view or response as configured |
| @RequestMapping | Declares path, method, consumes, produces, and mapping conditions |
| @GetMapping, @PostMapping, @PutMapping, @DeleteMapping | HTTP method shortcuts |
| @PathVariable | Extracts a parameter from the URL path |
| @RequestParam | Extracts a parameter from the query string or appropriate form data |
| @RequestHeader | Extracts a header value |
| @RequestBody | Converts the request body into a Java object via message converters |
| @ResponseBody | Writes the return value to the response body |
| ResponseEntity | Controls status, headers, and body |
| @ExceptionHandler, @RestControllerAdvice | Defines exception handling at the MVC layer |

Controllers should stay thin: receive input, call services, and turn results into responses. They should not contain all business logic, manually create JDBC connections, or store request-specific state in mutable fields of singleton beans.

### 8.1. JSON and Content negotiation

When Jackson and Spring MVC are present, Java objects are typically serialized to JSON if the media type matches. Spring MVC uses **Content-Type** to understand the request payload type, and **Accept** to negotiate the response type the client can receive.

- **400 Bad Request:** body cannot be read/bound or data violates processing rules.
- **404 Not Found:** no matching mapping/resource found.
- **405 Method Not Allowed:** the URL may match, but the HTTP method is not supported by the handler.
- **406 Not Acceptable:** the server cannot produce a response matching Accept.
- **415 Unsupported Media Type:** the request uses a body media type not supported by the handler/converter.
- **500 Internal Server Error:** unhandled internal error.

Do not equate every 4xx with "the server is not running." Inspect the method, URL, Content-Type, Accept, and mapping logs to pinpoint the exact cause.

### 8.2. Validation requires a separate dependency

When you want to validate DTOs using @Valid and annotations like @NotBlank, Spring Boot 3.x applications typically add:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Then declare constraints on the DTO and use @Valid on the @RequestBody parameter. That is an application extension step; do **not** assume that merely adding starter-web makes all validation annotations work automatically.

## 9. Server and path configuration

Example optional configuration in src/main/resources/application.yml:

~~~yaml
server:
  port: 8081
  servlet:
    context-path: /training
~~~

With this configuration, the GET mapping /api/greetings/{name} is called via:

~~~text
http://localhost:8081/training/api/greetings/Linh
~~~

Distinguish between:

- **server.port:** the port the embedded server uses to accept connections.
- **server.servlet.context-path:** prefix for the entire Servlet web application.
- **spring.mvc.servlet.path:** can configure the path bound to DispatcherServlet in specific scenarios.
- **@RequestMapping:** paths defined by controllers in Spring MVC.
- **Reverse proxy prefix:** may exist at the gateway layer and does not necessarily match the internal context path.

When encountering 404 after changing the context path, inspect the external URL and the actual URL received by the application rather than arbitrarily modifying controllers.

Applications can also tune Tomcat limits and pools with server.tomcat.* properties. Only change these settings based on observations of load, wait times, resources, and operational goals; increasing thread counts alone does not fix a slow database or unbounded blocking calls.

## 10. Replacing Tomcat with another Servlet server

By default, spring-boot-starter-web uses embedded Tomcat. When Jetty is required, you can exclude the default Tomcat starter and add the Jetty starter matching your Boot version:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
~~~

This is a **replacement for the starter-web declaration** in build.gradle, not a snippet to append below an existing Tomcat dependency. Check runtimeClasspath after switching to avoid having multiple unintended server implementations.

Spring MVC controller code usually stays unchanged because Spring MVC programs against the Servlet abstraction. However, connector settings, thread pools, servlet versions, and operational behavior can differ between Tomcat and Jetty.

In addition to executable JARs, applications can be packaged as WARs and deployed to an external Servlet container when required by the environment. That requires configuring WAR packaging, a Servlet initializer, and appropriate dependency scopes; the external container is responsible for starting the server. You cannot simply rename a JAR extension to WAR.

## 11. MVC/Servlet vs. WebFlux

spring-boot-starter-web represents the **Spring MVC on the Servlet stack** path. Spring WebFlux is a different web model, typically selected via spring-boot-starter-webflux.

| Aspect | Spring MVC / Servlet | Spring WebFlux |
|---|---|---|
| Underlying runtime | Jakarta Servlet and Servlet container | Reactive Streams / WebFlux HTTP runtime |
| Default model | Request/response, typically synchronous | Reactive, non-blocking when the entire chain supports it |
| Common return types | DTO, ResponseEntity, ModelAndView | Mono, Flux, and reactive types |
| Blocking I/O | Fits many traditional JDBC/JPA libraries | Must avoid blocking the event loop; use non-blocking clients/drivers to gain reactive benefits |
| Infrastructure integration | Servlet Filter, Spring MVC interceptor, Security Servlet | WebFilter and Spring Security Reactive |
| When to choose | Traditional business REST/MVC, blocking dependencies | High-concurrency I/O workloads with reactive libraries and design |

WebFlux is not always faster than Spring MVC. Load capacity depends on workload, databases/clients, resources, backpressure, and code design. If an application relies primarily on blocking JDBC and an imperative model, MVC is often simpler and easier to maintain.

If both Spring MVC and WebFlux accidentally end up on the classpath, Spring Boot typically prioritizes the Servlet/MVC application type by default. Therefore, check the actual starters and WebApplicationType rather than choosing a stack based on controllers sharing similar-looking annotations.

## 12. Common errors and how to investigate

### 12.1. Application does not open a port

Check startup logs, server dependencies, WebApplicationType, server.port configuration, port conflicts, and environment variables. If the application is configured with spring.main.web-application-type=none, Boot will not launch a web server by default.

If spring-boot-starter-web is not used or all Servlet servers were excluded without providing another server, auto-configuration may fail to create the expected web runtime.

### 12.2. 404 even though the application is running

Verify the context path, HTTP URL, package scan, @RequestMapping, and DispatcherServlet mapping. If the @SpringBootApplication class is in a package that is not a parent of the controller, the controller may not be discovered by default component scanning.

### 12.3. 405, 415, or 406

Check the HTTP method, Content-Type, Accept, and consumes/produces conditions. For example, a JSON POST sent without application/json may not be handled by the converter as expected, even if a GET to the same URL works.

### 12.4. Wrong JSON output or 500

Check whether the DTO/record can be read by Jackson, nullability, constructors, exceptions, and service execution. Do not assume every exception is a Tomcat error. Controllers/services can raise business errors; exception handlers can translate them into specific status codes.

### 12.5. Adding @EnableWebMvc loses default configuration

When using Spring Boot MVC, you should usually leverage auto-configured MVC settings and customize only what is needed. Manually enabling @EnableWebMvc can prevent part of Boot's MVC auto-configuration from applying; use it only when intentionally taking full control of MVC configuration.

### 12.6. Confusing Jakarta Servlet and javax.servlet

Spring Boot 3 and Spring Framework 6 use the Jakarta namespace, such as jakarta.servlet.http.HttpServletRequest. Do not copy javax.servlet code verbatim from Spring Boot 2 applications into a Boot 3 environment without migrating APIs and dependencies.

### 12.7. Mistakenly thinking starter-web automatically secures the application

Starter-web does not enable authentication/authorization for all endpoints. When adding spring-boot-starter-security, the filter chain, login, and CSRF can change HTTP responses. Do not disable security just to get 200 in tests; configure access rules and test with the proper intent.

### 12.8. Poor performance as concurrent requests increase

Tomcat thread pools, connection timeouts, database pools, external HTTP clients, and blocking services can all be bottlenecks. Measure active requests, queues, latency, thread dumps, and query times; do not attempt to fix it by increasing threads indefinitely.

## 13. Checklist for choosing and deploying starter-web

1. Decide whether the application needs **Spring MVC/Servlet** or a reactive runtime based on processing style and dependencies.
2. Add spring-boot-starter-web and keep versions managed by Spring Boot dependency management.
3. Place the @SpringBootApplication class in an appropriate package so component scan discovers controllers and services.
4. Clearly define @RestController, request mappings, DTOs, and services.
5. Verify the embedded server, port, context path, and actual URL in the runtime environment.
6. Define Content-Type, Accept, status codes, and exception handling.
7. Add validation and security via separate dependencies/configurations when needed.
8. Test both MVC mappings with MockMvc and real HTTP server integration for critical features.
9. Evaluate threads, blocking I/O, timeouts, and connection pools under realistic load.
10. Inspect the runtime dependency graph when swapping servers or adding WebFlux/Security.

**Conclusion:** spring-boot-starter-web lets Spring Boot configure a Servlet web application using Spring MVC and a default embedded server. The server accepts HTTP, the Servlet container runs Filters and DispatcherServlet, Spring MVC routes to controllers, and the application owns business rules. Understanding the boundaries between the starter, Spring Boot, Spring Framework, the Servlet container, and controllers helps you pick the right web stack, test the right layer, and troubleshoot issues effectively.
