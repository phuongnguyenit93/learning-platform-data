# HandlerMapping and Selecting Controllers or Functional Handlers in Spring MVC

> **Scope:** Spring Boot 3.5.x, Java 17+, Spring Framework 6.2, and **Spring MVC on the Servlet stack**. This lesson explains how an HTTP request is routed from `DispatcherServlet` to an annotated controller or a `HandlerFunction` in WebMvc.fn, the roles of `HandlerMapping` and `HandlerAdapter`, precedence order, how to choose a programming model, a runnable Maven example, and how to test and troubleshoot issues. Do not confuse WebMvc.fn with WebFlux.fn: they share similar API names but belong to two different web stacks.

## 1. What Question Does HandlerMapping Answer?

The HTTP server has received a request, for example:

~~~http
GET /api/annotated/hello?name=Lan HTTP/1.1
Host: localhost:8080
Accept: text/plain
~~~

`DispatcherServlet` is the front controller of Spring MVC. Before calling business code, it must find **which handler is responsible for processing the request**. Spring MVC separates two concerns:

1. **Finding a matching handler:** delegated to one or more `HandlerMapping` implementations.
2. **Executing the found handler:** delegated to a `HandlerAdapter` compatible with that handler type.

Conceptually, `HandlerMapping` performs the mapping:

~~~text
HttpServletRequest
       |
       v
HandlerMapping.getHandler(request)
       |
       +-- no match => try next HandlerMapping
       |
       +-- match => HandlerExecutionChain
                        |
                        +-- handler
                        +-- HandlerInterceptor[] (if any)
~~~

`HandlerExecutionChain` holds the handler and may include interceptors. It is **not** an HTTP response. After this step, Spring MVC selects an adapter, executes the handler, processes the return value, and produces the response.

Easily confused concepts:

| Component | Question it answers | Examples |
|---|---|---|
| `HandlerMapping` | Which handler matches this request? | `RequestMappingHandlerMapping`, `RouterFunctionMapping` |
| `HandlerAdapter` | How is a handler of that type invoked? | `RequestMappingHandlerAdapter`, `HandlerFunctionAdapter` |
| Handler | The code that actually handles the request | Method in `@RestController` or `HandlerFunction<ServerResponse>` |
| `HandlerInterceptor` | Runs hooks before/after an MVC handler | Logging, flow control at the MVC layer |
| `HandlerExceptionResolver` | Converts dispatch exceptions into an HTTP result | Handling `@ExceptionHandler`, `ResponseStatusException` |
| `HttpMessageConverter` | Converts bodies between Java objects and HTTP representations | Jackson JSON, text |
| Servlet Filter | Intervenes before/after `DispatcherServlet` at the Servlet layer | Security filter chain, correlation ID |

**Do not call `HandlerMapping` the controller execution code:** it only selects the handler and interceptor chain. Likewise, do not call every handler a `@Controller`: WebMvc.fn uses function objects.

## 2. DispatcherServlet Flow and Where HandlerMapping Fits

Simplified request flow in a Spring MVC application:

~~~text
Client HTTP request
         |
         v
Embedded Servlet server (Tomcat/Jetty/Undertow)
         |
         v
Servlet Filter chain (e.g., Spring Security)
         |
         v
DispatcherServlet
         |
         +--> check multipart and request info
         |
         +--> iterate through HandlerMappings by Order
         |       |
         |       +--> RequestMappingHandlerMapping?
         |       +--> RouterFunctionMapping?
         |       +--> resource/view/default mappings?
         |       +--> ... stop at the first mapping returning a handler
         |
         +--> HandlerExecutionChain(handler, interceptors)
         |
         +--> choose HandlerAdapter supporting the handler type
         |
         +--> interceptor.preHandle(...)
         |
         +--> adapter.handle(...) invokes the handler
         |       |
         |       +--> controller method (annotated)
         |       +--> HandlerFunction (WebMvc.fn)
         |
         +--> process result / response body / view
         +--> interceptor.postHandle / afterCompletion
         +--> HandlerExceptionResolver if an applicable error occurs
         |
         v
HTTP response
~~~

This diagram omits many details such as conditional requests, async dispatches, and view completion steps. Its sole purpose is to show where Spring MVC selects the handler and adapter.

If no mapping handles the request, the application typically returns 404 or falls through the static resource serving mechanism and then returns 404. If the URL matches a controller but the HTTP method or media type is invalid, Spring MVC can return 405, 406, or 415 depending on mapping conditions. The exact status depends on the configured mappings, filters, and exception resolvers.

### Ordering Among Multiple HandlerMappings

Spring MVC iterates over `HandlerMapping` beans according to `Ordered` or `@Order`: **smaller numbers** have higher priority. In a standard Spring Framework 6.2 Java MVC configuration, typical mappings are:

| Implementation | Typical Order | Purpose |
|---|---:|---|
| `RouterFunctionMapping` | -1 | Selects a `HandlerFunction` declared with WebMvc.fn |
| `RequestMappingHandlerMapping` | 0 | Selects methods annotated with `@RequestMapping`, `@GetMapping`, ... |
| View controller mapping | 1 | Maps a URL directly to a view name |
| `BeanNameUrlHandlerMapping` | 2 | Maps bean names to URLs |
| Static resources mapping | `Integer.MAX_VALUE - 1` | Serves static files |
| Default servlet mapping | `Integer.MAX_VALUE` | Forwards to the default servlet if configured |

**These values belong to the standard MVC configuration; developers can register additional mappings or customize the order.** Do not infer the actual order if the application defines custom `HandlerMapping` beans.

A notable consequence is that **WebMvc.fn may be evaluated before annotated controllers** because `RouterFunctionMapping` typically has order -1. If a functional route and an annotated controller register **the same method/path**, do not assume the annotated controller will definitely be called; under the standard order, the matching functional route can win. It is best to avoid overlapping routes and write tests when migrating programming models.

## 3. Annotated Controllers: RequestMappingHandlerMapping

Common annotation-based model:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{id}")
    public String getOne(@PathVariable String id) {
        return "order:" + id;
    }
}
~~~

`RequestMappingHandlerMapping` discovers matching methods at application startup, registers request mapping conditions, and resolves a `HandlerMethod` when a request arrives. `HandlerMethod` represents a bean's Java method along with its associated metadata.

`RequestMappingHandlerAdapter` knows how to invoke a `HandlerMethod`. It resolves `@PathVariable`, `@RequestParam`, `@RequestBody`, validation, other argument resolvers, and processes the return value. With `@RestController`, the return value is typically written to the HTTP body via return-value handlers and message converters.

Matching considers more than just the URL:

- HTTP method: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, ...
- Path pattern: literal paths, path variables, wildcards according to supported syntax.
- Request parameters: `params` conditions on `@RequestMapping`.
- Headers: `headers` conditions.
- `consumes`: request body format, related to `Content-Type`.
- `produces`: acceptable response format, related to `Accept`.

Example of a method that handles only JSON:

~~~java
@PostMapping(
    path = "/api/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public OrderReceipt create(@RequestBody CreateOrder request) {
    return new OrderReceipt(request.id(), true);
}
~~~

This is **illustrative code inside a controller**; `CreateOrder`/`OrderReceipt` are business DTOs that must be defined. Do not treat this snippet as a standalone Java file.

When **multiple annotated mappings match**, `RequestMappingHandlerMapping` applies specificity comparison rules across the conditions to pick the best handler. For example, a literal path is generally more specific than a matching path variable. If two handlers still tie, an ambiguous handler error can occur; two completely identical mappings can cause startup to fail immediately.

## 4. Functional Handlers with WebMvc.fn: RouterFunctionMapping

Spring MVC provides the **WebMvc.fn** model in the `org.springframework.web.servlet.function` package. This model still runs on the **same DispatcherServlet and Servlet stack** as annotated controllers.

Two main abstractions:

- `RouterFunction<ServerResponse>`: evaluates a `ServerRequest`; if it matches, returns the corresponding `HandlerFunction`. The router defines **selection conditions**.
- `HandlerFunction<ServerResponse>`: a function that takes a `ServerRequest` and returns a `ServerResponse`. The handler defines **how the request is processed**.

Dispatch mechanism:

~~~text
HttpServletRequest
    -> RouterFunctionMapping
    -> RouterFunction tests RequestPredicate
    -> HandlerFunction selected
    -> HandlerFunctionAdapter
    -> HandlerFunction.handle(ServerRequest)
    -> ServerResponse
~~~

Key parts:

1. `RouterFunctionMapping` automatically discovers Spring-managed beans of type `RouterFunction<?>`, composes them, and evaluates incoming requests.
2. `HandlerFunctionAdapter` executes the handler chosen by the router. It does not invoke `@GetMapping` methods.
3. `RouterFunctions.route()` creates a builder for declaring `GET`, `POST`, and predicates.
4. `ServerRequest` supports reading query parameters, headers, path variables, body, etc.; `ServerResponse` builds status, headers, and body.
5. Router functions can use regular Spring beans/services via dependency injection.

Example fragment defining a route:

~~~java
@Bean
RouterFunction<ServerResponse> functionalRoutes() {
    return RouterFunctions.route()
        .GET("/fn/hello",
            request -> ServerResponse.ok().body("hello functional"))
        .build();
}
~~~

This method needs to be placed inside a `@Configuration` class with the appropriate imports. Do not use the identically named classes under `org.springframework.web.reactive.function.server`: that is **WebFlux.fn**, which runs on a different reactive stack.

### Matching Order Within a RouterFunction

A key difference from annotated controllers is that **functional routes are evaluated in declaration order**. Once the first route matches, subsequent routes are not tried. Therefore, place specific paths before general paths:

~~~java
@Bean
RouterFunction<ServerResponse> catalogRoutes() {
    return RouterFunctions.route()
        .GET("/catalog/special", request ->
            ServerResponse.ok().body("special"))
        .GET("/catalog/{slug}", request ->
            ServerResponse.ok().body(request.pathVariable("slug")))
        .build();
}
~~~

If the two `GET` lines in the example were swapped, the general path `/catalog/{slug}` could capture requests for `/catalog/special`. In this example, both snippets are **illustrative code** that must be placed in a `@Configuration` class with imports.

With multiple `RouterFunction` beans, how they are ordered/composed also matters. If ordering is a business requirement, write one explicit router or order the beans deliberately and write integration tests for overlapping routes.

## 5. A Runnable Spring Boot Project Combining Both Models

The example uses **Spring Boot 3.5.0**, **Java 17**, Maven, and `spring-boot-starter-web`. Both endpoints share a service but have **separate paths**, so they do not compete for the same URL:

- Annotated: `GET /api/annotated/hello?name=Lan`.
- Functional: `GET /api/functional/hello?name=Lan`.
- Functional with path variable: `GET /api/functional/items/42`.

Directory structure:

~~~text
handler-mapping-demo/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/mappingdemo/
    MappingDemoApplication.java
    GreetingService.java
    AnnotatedGreetingController.java
    FunctionalGreetingHandler.java
    FunctionalRoutes.java
  src/test/java/com/example/mappingdemo/
    RoutingIntegrationTest.java
~~~

### 5.1. Maven POM

`pom.xml`:

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
    <artifactId>handler-mapping-demo</artifactId>
    <version>1.0.0</version>
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
~~~

Starter Web brings Spring MVC, embedded Tomcat, and common message converters onto the classpath. **You do not need to add the WebFlux starter** to use WebMvc.fn.

`src/main/resources/application.properties`:

~~~properties
server.port=8080
~~~

### 5.2. Entry Point and Shared Service

`src/main/java/com/example/mappingdemo/MappingDemoApplication.java`:

~~~java
package com.example.mappingdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MappingDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MappingDemoApplication.class, args);
    }
}
~~~

`src/main/java/com/example/mappingdemo/GreetingService.java`:

~~~java
package com.example.mappingdemo;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

### 5.3. Annotation-Based Controller

`src/main/java/com/example/mappingdemo/AnnotatedGreetingController.java`:

~~~java
package com.example.mappingdemo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/annotated")
public class AnnotatedGreetingController {

    private final GreetingService greetingService;

    public AnnotatedGreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping(
        path = "/hello",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public String hello(
            @RequestParam(name = "name", defaultValue = "world")
            String name) {
        return greetingService.greet(name);
    }
}
~~~

`RequestMappingHandlerMapping` finds the `GET /api/annotated/hello` mapping. `RequestMappingHandlerAdapter` resolves the `name` parameter and invokes the Java method. The `String` return value of `@RestController` is written as the response body, not a view name.

### 5.4. Functional Handler

`src/main/java/com/example/mappingdemo/FunctionalGreetingHandler.java`:

~~~java
package com.example.mappingdemo;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;

@Component
public class FunctionalGreetingHandler {

    private final GreetingService greetingService;

    public FunctionalGreetingHandler(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    public ServerResponse hello(ServerRequest request) {
        String name = request.param("name")
                .filter(value -> !value.isBlank())
                .orElse("world");

        return ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body(greetingService.greet(name));
    }

    public ServerResponse item(ServerRequest request) {
        String id = request.pathVariable("id");

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(new ItemView(id, "functional"));
    }

    public record ItemView(String id, String source) {
    }
}
~~~

The `hello` method reads the query parameter directly from `ServerRequest`; the `item` method reads the path variable. In WebMvc.fn, parameter reading, validation, and building a `ServerResponse` are typically written explicitly inside the handler or a helper; the full `@RequestParam`/`@RequestBody` mechanism is not automatically applied to a `HandlerFunction` the way Spring invokes annotated methods.

### 5.5. RouterFunction: Routing Functional Endpoints

`src/main/java/com/example/mappingdemo/FunctionalRoutes.java`:

~~~java
package com.example.mappingdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerResponse;

@Configuration
public class FunctionalRoutes {

    @Bean
    public RouterFunction<ServerResponse> routes(
            FunctionalGreetingHandler handler) {

        return RouterFunctions.route()
                .GET("/api/functional/hello", handler::hello)
                .GET("/api/functional/items/{id}", handler::item)
                .build();
    }
}
~~~

When `RouterFunction<ServerResponse>` is a Spring bean, `RouterFunctionMapping` can discover it automatically. When an incoming request matches a predicate, Spring retrieves the corresponding `HandlerFunction`; `HandlerFunctionAdapter` executes `hello` or `item`. The two functional endpoints do not need `@RestController` and are not handled by `RequestMappingHandlerMapping`.

## 6. Run, Send Requests, and Inspect Output

From the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Or:

~~~bash
mvn clean package
java -jar target/handler-mapping-demo-1.0.0.jar
~~~

The following commands assume the application is running successfully on `localhost:8080`.

### Annotated Endpoint

~~~bash
curl -i "http://localhost:8080/api/annotated/hello?name=Lan"
~~~

Exact response body:

~~~text
Hello, Lan
~~~

### Functional Endpoint

~~~bash
curl -i "http://localhost:8080/api/functional/hello?name=Lan"
~~~

Exact response body is also:

~~~text
Hello, Lan
~~~

### Functional Endpoint with Path Variable

~~~bash
curl -i "http://localhost:8080/api/functional/items/42"
~~~

JSON response with two properties:

~~~json
{
  "id": "42",
  "source": "functional"
}
~~~

Key ordering, whitespace, and HTTP headers depend on the converter and configuration; the two JSON fields are the contract being demonstrated. With `curl -i`, the console also displays the status line and headers before the body. The bodies above are the outputs produced by the example source code itself.

### Distinguishing GET, POST, Accept

~~~bash
curl -i -X POST "http://localhost:8080/api/annotated/hello"
curl -i -H "Accept: application/json" \
  "http://localhost:8080/api/annotated/hello"
~~~

In the example app, the annotated handler only accepts GET and produces `text/plain`, so requests with the wrong method or `Accept` condition can yield status 405 or 406. The status of a functional endpoint when a predicate does not match may differ; do not assume every HTTP method mismatch on a functional route automatically becomes 405. Verify the HTTP response against the running application.

## 7. Real HTTP Integration Testing for Both HandlerMappings

Add `src/test/java/com/example/mappingdemo/RoutingIntegrationTest.java`:

~~~java
package com.example.mappingdemo;

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
class RoutingIntegrationTest {

    @LocalServerPort
    private int port;

    private final HttpClient client = HttpClient.newHttpClient();

    private HttpResponse<String> get(String path) throws Exception {
        URI uri = URI.create("http://127.0.0.1:" + port + path);
        HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
        return client.send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void annotatedControllerIsMapped() throws Exception {
        assertTrue(port > 0);
        HttpResponse<String> response =
                get("/api/annotated/hello?name=Lan");

        assertEquals(200, response.statusCode());
        assertEquals("Hello, Lan", response.body());
    }

    @Test
    void functionalHandlerIsMapped() throws Exception {
        HttpResponse<String> response =
                get("/api/functional/hello?name=Lan");

        assertEquals(200, response.statusCode());
        assertEquals("Hello, Lan", response.body());
    }

    @Test
    void unknownPathIsNotAnEndpoint() throws Exception {
        HttpResponse<String> response = get("/missing-endpoint");

        assertEquals(404, response.statusCode());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

`RANDOM_PORT` starts a real web server on an OS-assigned port; `@LocalServerPort` reads the chosen port. The tests exercise both the annotation route and the functional route over the network, confirming that `DispatcherServlet` operates with both mapping types. The 404 test is only meaningful when the application has not registered any static/fallback route catching `/missing-endpoint`.

`MockMvc` can be used for most MVC unit/integration tests; however, real HTTP testing is useful when you want to verify the full servlet registration, filter chain, and server configuration.

## 8. When to Choose @RestController vs. WebMvc.fn?

Both are official Spring MVC models. The choice should depend on fit with the codebase, team, and API style, not because one model is always faster in every case.

| Criterion | Annotated controller | WebMvc.fn / functional handler |
|---|---|---|
| Route declaration | `@RequestMapping`, `@GetMapping` on methods | `RouterFunction` and `RequestPredicate` |
| Executing handler | `HandlerMethod`, adapter invokes reflected method | `HandlerFunction` receiving `ServerRequest` |
| Code organization | Classes/controllers with annotations | Router and handler can be separated |
| Parameter binding | Many annotations like `@PathVariable`, `@RequestBody`, `@Valid` | Read and convert from `ServerRequest`, handled explicitly in handler |
| Building responses | Java return value, `ResponseEntity`, annotations | `ServerResponse` builder |
| Route precedence | Selects the most specific mapping among annotations | Evaluates routes in declaration order |
| Program structure | Fits CRUD REST, common controller/service pattern | Fits explicit routers, DSLs, small endpoints, composition |
| Runs on Servlet | Yes | Yes, same `DispatcherServlet` |
| Spring WebFlux required? | No | No |
| Testing | `MockMvc`, integration tests | `MockMvc`, `RouterFunction` tests, integration tests |

**Prefer annotated controllers** when the project already uses a controller/service layer, needs extensive annotation binding and validation, or the team is familiar with `@RestControllerAdvice`, method-level OpenAPI/validation, and controller conventions.

**Choose WebMvc.fn** when you want explicit routing, grouping routes by feature, flexible predicate composition, writing functionally testable request/response handlers, or building a thin HTTP adapter layer.

**Both can be combined** in the same Spring Boot MVC app. When combining them, define clear URL prefixes and responsibility conventions to prevent route collisions and know precisely which handler serves each URL.

## 9. How Do Validation, Exceptions, and Cross-Cutting Concerns Differ?

### 9.1. Data Binding and Validation

Annotated controllers support common patterns:

~~~java
@PostMapping(
    path = "/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public ResponseEntity<OrderResult> create(
        @Valid @RequestBody CreateOrderCommand command) {
    return ResponseEntity.ok(service.create(command));
}
~~~

This is a **fragment** inside a controller that already has `service`, DTOs, and appropriate imports. Spring MVC can deserialize the body into a DTO and invoke Bean Validation when properly configured.

In WebMvc.fn, the handler usually reads the body explicitly:

~~~java
public ServerResponse create(ServerRequest request) throws Exception {
    CreateOrderCommand command =
            request.body(CreateOrderCommand.class);

    OrderResult result = service.create(command);

    return ServerResponse.ok().body(result);
}
~~~

This is also a **fragment** depending on `CreateOrderCommand`, `OrderResult`, and `service`. The handler must validate data using an appropriate mechanism; do not assume `@Valid` on functional handler parameters is processed the same way as in annotated controllers. For strict APIs, validate body content, format, and business rules and return structured errors.

### 9.2. Exceptions and HTTP Statuses

With annotated controllers, exceptions can be handled by `@ExceptionHandler`, `@RestControllerAdvice`, `ResponseStatusException`, and MVC's `HandlerExceptionResolver` chain.

With functional handlers, handle and return error `ServerResponse` objects explicitly and test actual exception behavior. WebMvc.fn provides ways to apply error handlers or functional filters, though the scope of handling can differ from annotated controllers. Do not assume every `@ExceptionHandler` on an annotated controller applies to every `HandlerFunction`. Maintain a consistent error contract and test failures for both models.

### 9.3. Filters, Interceptors, and Spring Security

- **Servlet Filter** sits outside `DispatcherServlet`: it can affect both annotated and functional endpoints if their URLs match the filter mapping.
- **HandlerInterceptor** runs inside the MVC dispatch; it can apply across mappings depending on interceptor configuration and path patterns. Interceptors are not a default replacement for authentication/authorization in Spring Security.
- **Spring Security FilterChain** is enforced at the filter layer; endpoint protection rules must be tested against actual URLs and HTTP methods.
- **Functional filters** in `RouterFunction` are a different abstraction from Servlet Filters; they typically apply only to the corresponding router branch.

Do not accidentally bypass or drop security checks just because an annotated controller was converted into a functional route.

## 10. Precedence When Routes Conflict

Suppose you intentionally register both mappings for `GET /api/status`:

~~~java
// Annotated controller
@GetMapping("/api/status")
public String status() {
    return "annotated";
}
~~~

~~~java
// Inside a RouterFunction bean
.GET("/api/status",
    request -> ServerResponse.ok().body("functional"))
~~~

In a standard Spring MVC 6.2 configuration, `RouterFunctionMapping` has order -1 and `RequestMappingHandlerMapping` has order 0; therefore the functional route can be selected first. The two snippets above are **conflict-illustration fragments**, not part of the runnable project in section 5.

Handling guidelines:

1. Never register two handlers for the exact same **method, path, and request conditions**.
2. When migrating an API from annotations to functional routes, remove the old route or change the URL explicitly.
3. If you have a wildcard fallback router, place specific routes earlier in the same router; verify whether the fallback shadows annotation routes or static resources.
4. For custom `HandlerMapping`s, inspect the actual configured `order` rather than guessing precedence.
5. Write regression tests for URLs that multiple mappings might accept.

**Note:** for **two annotated methods** with identical mappings, `RequestMappingHandlerMapping` can report an ambiguous mapping at startup; for **an annotated route + a functional route**, they are registered through two separate `HandlerMapping`s, so they will not necessarily fail at startup with the same error. This is why cross-model route collisions can be harder to spot.

## 11. Diagnosing HandlerMapping When Endpoints Behave Unexpectedly

### 11.1. Check the Actual HTTP Method, Path, and Headers First

A request might fail to match because of:

- `GET` versus `POST`;
- context path or servlet path (`server.servlet.context-path`, `spring.mvc.servlet.path`);
- controller class mapping + method mapping;
- path variable, trailing slash, or pattern mismatch;
- `Content-Type` incompatible with `consumes`;
- `Accept` incompatible with `produces`;
- handler bean outside component scan;
- `RouterFunction` not registered as a Spring bean;
- a general router matching before a specific router;
- a custom `HandlerMapping` running before the expected mapping.

### 11.2. Actuator Mappings Endpoint

When a project includes **`spring-boot-starter-actuator`** and exposes the endpoint, `GET /actuator/mappings` can show the request mappings registered by the application.

Example development configuration:

~~~properties
management.endpoints.web.exposure.include=health,info,mappings
~~~

Call:

~~~bash
curl http://localhost:8080/actuator/mappings
~~~

**Note:** the Maven project in section 5 only has `spring-boot-starter-web` and `spring-boot-starter-test`. To use this endpoint, you must add `spring-boot-starter-actuator`; otherwise `/actuator/mappings` does not exist. The mappings endpoint can expose internal URL/handler structure; only expose it when protected by appropriate security policies.

### 11.3. Diagnostic Logging

In development environments, you can temporarily increase logging:

~~~properties
logging.level.org.springframework.web.servlet.DispatcherServlet=DEBUG
logging.level.org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping=TRACE
logging.level.org.springframework.web.servlet.function.support.RouterFunctionMapping=TRACE
~~~

Logger names and detail levels can vary by framework version and code path; verify against real logs. Do not enable uncontrolled HTTP TRACE logging in production, as it can generate high log volume and expose request metadata.

If you need to inspect `HandlerMapping` beans and their `order` without digging through the whole system, in a development test you can inject the list of `HandlerMapping` beans, sort them with `AnnotationAwareOrderComparator`, and print the class/order of each mapping. That confirms whether any custom mapping has altered the standard order.

### 11.4. Error Classification

| Symptom | Common cause | How to resolve |
|---|---|---|
| 404 | No handler matched; wrong prefix or router bean | Check method, URL, context/servlet path, and beans |
| 405 | Annotated URL matched, wrong HTTP method | Check `@GetMapping`/`@PostMapping` and client method |
| 406 | `Accept` incompatible with `produces` | Fix media type condition or header |
| 415 | `Content-Type` incompatible with `consumes` | Change request body format or contract |
| Ambiguous mapping at startup | Two annotated methods have indistinguishable mappings | Adjust URLs or request conditions |
| Functional handler overrides annotation | `RouterFunctionMapping` has an earlier order | Remove duplicate route, rename path, or adjust route design |
| `@RestController` does not work | Outside component scan or missing Spring MVC setup | Check package, annotations, starter |
| Functional route does not appear | `RouterFunction` bean not registered or WebFlux.fn imported | Check bean type and `web.servlet.function` package |
| Handler selected, response conversion fails | Adapter/converter/serialization error | Check content type, DTO, exceptions |
| Unit test passes, real app fails | Missing filters/servlet mapping in test | Add real HTTP integration tests |

## 12. Extension Points and Important Limits

### Customizing HandlerMapping

You can write a custom `HandlerMapping` or register handlers via `WebMvcConfigurer` and built-in MVC configuration mechanisms. This is an advanced need, such as a plugin system or dynamic URL routing.

When doing so, decide clearly:

- Which URLs the `HandlerMapping` handles and at what `order` it runs;
- Which `HandlerAdapter` will support the returned handler object type;
- How interceptors, security, and exceptions will be applied;
- How fallback, static resources, and content negotiation are handled;
- How to test that the custom mapping does not shadow existing routes.

Returning an object from a custom mapping **is not enough**; `DispatcherServlet` needs `HandlerAdapter.supports(handler)` to find a compatible adapter. Otherwise, the request will fail even though mapping produced a handler.

### Static Resources and View Controllers Also Use HandlerMapping

Not every mapping points to a `@Controller` method. A URL may serve a resource, redirect, forward to a view, or invoke a functional handler. This is why `/api/unknown` is sometimes picked up by the resource handler before returning 404; concluding solely from a single "No mapping" log line is insufficient if the project has custom resource or fallback configurations.

### Comparison with WebFlux

WebFlux uses `DispatcherHandler` and conceptually similar abstractions, but on the **reactive stack**. WebFlux.fn uses `org.springframework.web.reactive.function.server.*`; WebMvc.fn uses `org.springframework.web.servlet.function.*`. The two packages are not drop-in replacements for each other. If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Spring Boot typically prefers MVC Servlet based on its web application type detection rules.

## 13. Checklist for Designing and Testing HandlerMapping

1. Confirm the exact **Spring MVC runtime** and `DispatcherServlet` mapping.
2. Choose annotated controllers or WebMvc.fn per API group based on request handling, validation needs, and code conventions.
3. Define clear URLs and HTTP methods; avoid route overlaps between the two models.
4. For annotated handlers, use explicit `method/path/params/headers/consumes/produces` conditions.
5. For functional routes, place **specific routes before general routes**, register `RouterFunction` as a bean, and delegate business logic to services.
6. When customizing order, check `HandlerMapping.order` and compatible adapters.
7. Test success responses, 404/405/406/415, validation, business errors, and access control for each model used.
8. Test with real HTTP or `MockMvc` as appropriate; do not rely solely on startup logs to conclude routing is correct.
9. When inspecting routes, use Actuator mappings in a controlled environment or appropriate logging.
10. After changes, verify static resources, actuator endpoints, security filters, path prefixes, and fallback routes remain unaffected.

## Official Documentation

- [Spring Framework 6.2 — DispatcherServlet](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet.html): dispatch process and processing strategies.
- [Spring Framework 6.2 — Annotated Controllers: Mapping Requests](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-requestmapping.html): request mapping conditions.
- [Spring Framework 6.2 — Functional Endpoints (WebMvc.fn)](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-functional.html): `RouterFunction`, `HandlerFunction`, route order, `ServerRequest`/`ServerResponse`.
- [Spring Framework 6.2 — WebMvcConfigurationSupport Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurationSupport.html): `HandlerMapping`s/`HandlerAdapter`s and typical ordering.
- [Spring Boot 3.5 — Actuator mappings](https://docs.spring.io/spring-boot/3.5/api/rest/actuator/mappings.html): inspecting mappings at runtime.

**Practical takeaway:** `HandlerMapping` decides which handler receives a request; `HandlerAdapter` invokes that handler type properly. `@RestController` uses `RequestMappingHandlerMapping` and `RequestMappingHandlerAdapter`, whereas WebMvc.fn uses `RouterFunctionMapping` and `HandlerFunctionAdapter`. Both run on Spring MVC's `DispatcherServlet` and can coexist, provided you avoid conflicting routes and test real paths.