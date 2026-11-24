# Combining Controllers and Functional Routers in One Spring Boot Application

> **Scope:** Spring Boot **3.5.x**, Spring Framework **6.2.x**, Java **17+**. The main topic is **web routing when using both annotated Controllers and functional routers simultaneously** in **a single Spring MVC application**, without requiring two separate servers. The lesson also includes a standalone WebFlux example to clearly distinguish the stack and packages. Maven examples use Spring Boot **3.5.0** and JDK **17**.

## 1. Can both routing models be mixed in the same application?

**Yes.** A Spring Boot MVC application can declare:

- Annotated controllers, such as `@RestController` with `@GetMapping`, `@PostMapping`, and `@RequestMapping`.
- `RouterFunction<ServerResponse>` beans from **WebMvc.fn**, using `RouterFunctions.route()` and `HandlerFunction` to declare functional endpoints.

Both models share the same **ApplicationContext**, beans/services, dependency injection, embedded Servlet server, and single `DispatcherServlet`. They do not need separate ports. Spring MVC provides dedicated `HandlerMapping` and `HandlerAdapter` implementations so DispatcherServlet recognizes and executes both handler forms.

Example on the same server `localhost:8080`:

~~~text
GET /api/annotated/hello?name=Lan
    -> @RestController -> GreetingService -> JSON

GET /api/functional/hello?name=Lan
    -> RouterFunction -> FunctionalApiHandler
    -> GreetingService -> JSON
~~~

Controllers and functional handlers can return **the same JSON contract** while differing in how routes are declared and requests are bound.

What matters is choosing the **right package**:

| Component | Spring MVC / Servlet | Spring WebFlux / reactive |
|---|---|---|
| Starter | `spring-boot-starter-web` | `spring-boot-starter-webflux` |
| Front controller | `DispatcherServlet` | `DispatcherHandler` |
| RouterFunction | `org.springframework.web.servlet.function.RouterFunction` | `org.springframework.web.reactive.function.server.RouterFunction` |
| ServerRequest | `org.springframework.web.servlet.function.ServerRequest` | `org.springframework.web.reactive.function.server.ServerRequest` |
| ServerResponse | `org.springframework.web.servlet.function.ServerResponse` | `org.springframework.web.reactive.function.server.ServerResponse` |
| Functional handler return | `ServerResponse` (synchronous from the API viewpoint) | `Mono<ServerResponse>` |
| Annotated controller | `@RestController` | `@RestController` is also supported |

**Do not import WebFlux.fn into Spring MVC just because both share the `RouterFunction` type name.** The two packages have identically named types, yet the framework detects and dispatches them according to separate runtime stacks.

## 2. Spring MVC HTTP flow when both handler styles exist

An HTTP request through Spring MVC follows this general flow:

~~~text
HTTP request
     |
     v
Servlet container (e.g., embedded Tomcat)
     |
     v
Servlet Filter chain (Spring Security if present)
     |
     v
DispatcherServlet
     |
     +--- HandlerMapping beans in order
     |       |
     |       +-- RouterFunctionMapping
     |       |       +-- matches RouterFunction?
     |       |
     |       +-- RequestMappingHandlerMapping
     |               +-- matches @GetMapping/@PostMapping?
     |
     +--- selected handler
     |       |
     |       +-- HandlerFunction (WebMvc.fn)
     |       |       -> HandlerFunctionAdapter
     |       |
     |       +-- HandlerMethod (Controller)
     |               -> RequestMappingHandlerAdapter
     |
     +--- produce ServerResponse/response body/view
     +--- appropriate exception resolution/interceptors
     |
     v
HTTP response
~~~

This is a simplified diagram; the actual flow also involves static resource mappings, view controllers, custom mappings, multipart processing, and async flows.

### 2.1. What does an Annotated Controller go through?

`RequestMappingHandlerMapping` builds and resolves mappings for annotated methods: `@GetMapping`, `@PostMapping`, `@RequestMapping`, etc. When a matching method is found, it returns a `HandlerMethod`.

`RequestMappingHandlerAdapter` executes that method, supporting argument resolvers for `@PathVariable`, `@RequestParam`, `@RequestBody`, `@RequestHeader`, validation, and return-value handlers. Spring MVC can use `HttpMessageConverter` to serialize JSON.

Example:

~~~java
@GetMapping("/api/annotated/hello")
public Greeting hello(@RequestParam String name) {
    return service.greet(name, "annotated");
}
~~~

This is a **fragment inside a `@RestController`**, not a standalone Java file; `Greeting` and `service` are types/beans that must be defined.

### 2.2. What does WebMvc.fn go through?

`RouterFunctionMapping` discovers `RouterFunction<?>` beans, evaluates their `RequestPredicate` conditions, and retrieves the matching `HandlerFunction`. `HandlerFunctionAdapter` invokes the handler to produce a `ServerResponse`.

Example fragment:

~~~java
@Bean
RouterFunction<ServerResponse> routes(MyHandler handler) {
    return RouterFunctions.route()
        .GET("/api/functional/hello", handler::hello)
        .build();
}
~~~

The method above belongs in a configuration class and requires imports from **`org.springframework.web.servlet.function`**. `MyHandler.hello` must have a compatible signature such as `ServerResponse hello(ServerRequest request)`.

**No `@EnableWebMvc` is needed.** With the standard Spring Boot Web starter, WebMvc.fn infrastructure beans are already configured. Adding `@EnableWebMvc` just to use functional routers is unnecessary and can alter Boot MVC auto-configuration.

## 3. Similarities and differences between the two models

| Aspect | Annotation Controller | WebMvc.fn |
|---|---|---|
| Route definition | `@GetMapping`, `@PostMapping`, class-level `@RequestMapping` | `RouterFunctions.route().GET(...).POST(...)` |
| Handler code | Method on `@Controller`/`@RestController` bean | `HandlerFunction<ServerResponse>` receiving `ServerRequest` |
| Request binding | Annotation-based argument resolvers | Explicit `ServerRequest` API reads |
| Response creation | Return POJO, `ResponseEntity`, view, etc. | `ServerResponse.ok()/status()/body(...)` |
| Sharing logic | Controller calls service/repository beans | Functional handler calls the same service/repository beans |
| Finding handler | `RequestMappingHandlerMapping` | `RouterFunctionMapping` |
| Execution | `RequestMappingHandlerAdapter` | `HandlerFunctionAdapter` |
| Route order | Within annotated mappings: selects the most specific conditions | Functional routes are evaluated in **declaration order** |
| Cross-cutting | Servlet Filter, HandlerInterceptor, controller advice per mechanism | Servlet Filter, HandlerInterceptor, router filter, and appropriate error handling |
| Runs on server | Servlet container | Same Servlet container |
| Needs WebFlux? | No | No |

Both models do not have to share the exact same parameter-binding mechanism. What should be shared are **business services, domain models, validation contracts, serialization contracts, and security policies**.

### 3.1. Why combine them?

Reasonable scenarios:

1. A project already has many healthy REST controllers and wants to add a small group of endpoints with a clear router DSL.
2. A plugin integration module provides a `RouterFunction` bean on its own while core business APIs remain in controllers.
3. Incremental migration from functional routes to annotations or vice versa without rewriting services/repositories.
4. Some endpoints benefit from predicate composition, while REST CRUD endpoints benefit from annotation binding and validation convenience.
5. Grouping a set of feature routes in one router while keeping existing controllers intact.

Using both simultaneously **does not automatically increase performance**. Both handler styles sit on the same MVC foundation; evaluating performance requires benchmarking under realistic workloads and equivalent configurations.

## 4. Avoiding URL collisions between Controllers and functional routers

This is the biggest risk when "mixing" them.

In typical Spring MVC Framework 6.2 configuration, `RouterFunctionMapping` has a lower order value (higher priority) than `RequestMappingHandlerMapping` (typically **-1** vs. **0**). DispatcherServlet checks in order and stops at the first `HandlerMapping` that returns a matching handler.

Therefore, the following is **dangerous**:

~~~java
// Fragment in @RestController:
@GetMapping("/api/status")
public String status() {
    return "annotated";
}
~~~

~~~java
// Fragment in @Configuration:
@Bean
RouterFunction<ServerResponse> statusRoute() {
    return RouterFunctions.route()
        .GET("/api/status",
            request -> ServerResponse.ok().body("functional"))
        .build();
}
~~~

Under the default order mentioned above, the functional route can be picked first; do not expect the controller method to run merely because it also matches the URL.

**Differences among conflict types:**

- Two annotated controller methods with identical mappings/conditions are normally detected as an **ambiguous mapping** at registration, which can fail startup.
- An annotation route and a functional route belong to **two separate HandlerMappings**. They do not necessarily raise the same startup error; one handler can silently shadow the other by order.
- Two functional routes with overlapping conditions: the router evaluates **top to bottom**, so the first matching route can capture requests intended for later routes.
- Custom `HandlerMapping` beans or `@Order` can alter behavior compared to standard configuration.

**Collision-avoidance strategy:**

~~~text
/api/annotated/**   -> controllers
/api/functional/**  -> WebMvc.fn routers

or

/api/users/**       -> UsersController
/api/reports/**     -> ReportsRouter
~~~

In production, names do not need to be `annotated`/`functional`: using **feature/domain** prefixes is even better. What matters is **clear route ownership** and avoiding overly broad fallbacks.

### 4.1. Functional routers must put specific routes first

Example of sensible order:

~~~java
return RouterFunctions.route()
    .GET("/api/files/special",
         request -> ServerResponse.ok().body("special"))
    .GET("/api/files/{name}",
         request -> ServerResponse.ok()
             .body(request.pathVariable("name")))
    .build();
~~~

If reversed, `/api/files/{name}` would swallow `/api/files/special`. In contrast, the annotation model picks a method by specificity across its mapping annotations, regardless of method order in the Java file.

The safest approach is to write tests for intersecting paths instead of relying on visual inspection.

## 5. Complete Spring Boot MVC project containing both Controller and RouterFunction

This project is **standalone and runnable** with JDK 17+, Maven, and Spring Boot 3.5.0. It shares one service and DTOs across both models.

URLs:

~~~text
GET /api/annotated/hello?name=Lan
GET /api/functional/hello?name=Lan
GET /api/annotated/items/42
GET /api/functional/items/42
~~~

All run in **one** process, one port, and one `DispatcherServlet`.

### 5.1. Directory structure

~~~text
mixed-routing-mvc/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/mixedmvc/
    MixedMvcApplication.java
    GreetingPayload.java
    ItemPayload.java
    GreetingService.java
    AnnotatedApiController.java
    FunctionalApiHandler.java
    FunctionalRoutes.java
  src/test/java/com/example/mixedmvc/
    MixedRoutingIntegrationTest.java
~~~

### 5.2. Maven POM

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
    <artifactId>mixed-routing-mvc</artifactId>
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

**Only `spring-boot-starter-web` is needed**; do not add `spring-boot-starter-webflux` to use WebMvc.fn. Maven parent manages compatible dependency versions.

`src/main/resources/application.properties`:

~~~properties
server.port=8080
~~~

### 5.3. Entry point

`src/main/java/com/example/mixedmvc/MixedMvcApplication.java`:

~~~java
package com.example.mixedmvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MixedMvcApplication {

    public static void main(String[] args) {
        SpringApplication.run(MixedMvcApplication.class, args);
    }
}
~~~

### 5.4. Shared DTOs and service

`src/main/java/com/example/mixedmvc/GreetingPayload.java`:

~~~java
package com.example.mixedmvc;

public record GreetingPayload(String message, String source) {
}
~~~

`src/main/java/com/example/mixedmvc/ItemPayload.java`:

~~~java
package com.example.mixedmvc;

public record ItemPayload(String id, String source) {
}
~~~

`src/main/java/com/example/mixedmvc/GreetingService.java`:

~~~java
package com.example.mixedmvc;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public GreetingPayload greet(String name, String source) {
        return new GreetingPayload("Hello, " + name, source);
    }

    public ItemPayload findItem(String id, String source) {
        return new ItemPayload(id, source);
    }
}
~~~

Both records are Java 17. In a real application, the service can call repositories and domain rules, while controllers/router handlers act solely as HTTP adapters. The `source` field here is only to observe which handler ran in the demo; it is not a required domain design.

### 5.5. Annotated controller

`src/main/java/com/example/mixedmvc/AnnotatedApiController.java`:

~~~java
package com.example.mixedmvc;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/annotated")
public class AnnotatedApiController {

    private final GreetingService service;

    public AnnotatedApiController(GreetingService service) {
        this.service = service;
    }

    @GetMapping(
        path = "/hello",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public GreetingPayload hello(
            @RequestParam(name = "name", defaultValue = "world")
            String name) {
        return service.greet(name, "annotated");
    }

    @GetMapping(
        path = "/items/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ItemPayload item(@PathVariable String id) {
        return service.findItem(id, "annotated");
    }
}
~~~

Here `@RequestMapping("/api/annotated")` is a class-level prefix, not a Servlet context path. `@GetMapping` and `@PathVariable` are supported by Spring MVC argument resolvers. Responses are DTO records serialized by the JSON message converter.

### 5.6. Functional handler using the same service

`src/main/java/com/example/mixedmvc/FunctionalApiHandler.java`:

~~~java
package com.example.mixedmvc;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;

@Component
public class FunctionalApiHandler {

    private final GreetingService service;

    public FunctionalApiHandler(GreetingService service) {
        this.service = service;
    }

    public ServerResponse hello(ServerRequest request) {
        String name = request.param("name")
                .filter(value -> !value.isBlank())
                .orElse("world");

        GreetingPayload body = service.greet(name, "functional");

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(body);
    }

    public ServerResponse item(ServerRequest request) {
        String id = request.pathVariable("id");
        ItemPayload body = service.findItem(id, "functional");

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(body);
    }
}
~~~

The code above is **WebMvc.fn**, because it imports `org.springframework.web.servlet.function.*`. The return type is `ServerResponse`, not `Mono<ServerResponse>`. The handler reads the query parameter with `request.param` and path variable with `request.pathVariable`, then returns the response via the `ServerResponse` builder.

### 5.7. RouterFunction bean registering two new URLs

`src/main/java/com/example/mixedmvc/FunctionalRoutes.java`:

~~~java
package com.example.mixedmvc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class FunctionalRoutes {

    @Bean
    RouterFunction<ServerResponse> apiRoutes(
            FunctionalApiHandler handler) {

        return RouterFunctions.route()
                .GET("/api/functional/hello", handler::hello)
                .GET("/api/functional/items/{id}", handler::item)
                .build();
    }
}
~~~

`@Bean` is the key: `RouterFunctionMapping` picks up RouterFunction beans from the application context. If you merely create a router in a local variable of an uncalled/unregistered method, MVC has no way to discover it automatically.

In the sample project:

- Spring Boot component-scans all Java classes under `com.example.mixedmvc`.
- `GreetingService` is a `@Service` bean.
- `AnnotatedApiController` is a `@RestController` bean.
- `FunctionalApiHandler` is a `@Component` bean.
- `FunctionalRoutes#apiRoutes` produces a `RouterFunction<ServerResponse>` bean.
- DispatcherServlet can dispatch both annotation and function endpoints.

This is **one project**, not two servers or two separate application contexts.

## 6. Run once, access both endpoint styles

In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Or package:

~~~bash
mvn clean package
java -jar target/mixed-routing-mvc-1.0.0.jar
~~~

Provided port 8080 is free, the following requests use the same base URL.

### 6.1. Request to the annotated controller

~~~bash
curl -i "http://localhost:8080/api/annotated/hello?name=Lan"
~~~

HTTP body:

~~~json
{"message":"Hello, Lan","source":"annotated"}
~~~

### 6.2. Request to the functional handler

~~~bash
curl -i "http://localhost:8080/api/functional/hello?name=Lan"
~~~

HTTP body:

~~~json
{"message":"Hello, Lan","source":"functional"}
~~~

Both endpoints execute via the same `GreetingService.greet`, differing in HTTP adapter branch. JSON property order depends on converter and serialization config; here it illustrates the two expected fields, rather than requiring exact string comparison if you customize the mapper.

### 6.3. Path variables on both branches

~~~bash
curl -i http://localhost:8080/api/annotated/items/42
curl -i http://localhost:8080/api/functional/items/42
~~~

Annotated branch body:

~~~json
{"id":"42","source":"annotated"}
~~~

Functional branch body:

~~~json
{"id":"42","source":"functional"}
~~~

With `curl -i`, the console also shows the status line and response headers. Each successful endpoint is expected to return **HTTP 200** and its corresponding JSON body.

### 6.4. Unregistered endpoint

~~~bash
curl -i http://localhost:8080/api/unknown
~~~

In the sample project there is no fallback route for `/api/unknown`, so the HTTP status is normally **404**. In real apps, static resource handlers or custom catch-all routers may alter the error path.

## 7. Integration test: proving both models are genuinely registered

Add `src/test/java/com/example/mixedmvc/MixedRoutingIntegrationTest.java`:

~~~java
package com.example.mixedmvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class MixedRoutingIntegrationTest {

    @LocalServerPort
    private int port;

    private final HttpClient client = HttpClient.newHttpClient();
    private final ObjectMapper mapper = new ObjectMapper();

    private HttpResponse<String> get(String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path))
                .GET()
                .build();

        return client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );
    }

    @Test
    void annotatedControllerIsAvailable() throws Exception {
        assertTrue(port > 0);
        HttpResponse<String> response =
                get("/api/annotated/hello?name=Lan");

        assertEquals(200, response.statusCode());

        JsonNode body = mapper.readTree(response.body());
        assertEquals("Hello, Lan", body.get("message").asText());
        assertEquals("annotated", body.get("source").asText());
    }

    @Test
    void functionalRouterIsAvailable() throws Exception {
        HttpResponse<String> response =
                get("/api/functional/hello?name=Lan");

        assertEquals(200, response.statusCode());

        JsonNode body = mapper.readTree(response.body());
        assertEquals("Hello, Lan", body.get("message").asText());
        assertEquals("functional", body.get("source").asText());
    }

    @Test
    void bothRoutesCanBindPathVariables() throws Exception {
        HttpResponse<String> annotated =
                get("/api/annotated/items/42");
        HttpResponse<String> functional =
                get("/api/functional/items/42");

        assertEquals(200, annotated.statusCode());
        assertEquals(200, functional.statusCode());

        JsonNode annotatedBody = mapper.readTree(annotated.body());
        JsonNode functionalBody = mapper.readTree(functional.body());

        assertEquals("42", annotatedBody.get("id").asText());
        assertEquals("42", functionalBody.get("id").asText());
        assertEquals("annotated", annotatedBody.get("source").asText());
        assertEquals("functional", functionalBody.get("source").asText());
    }

    @Test
    void unknownApiPathReturnsNotFound() throws Exception {
        assertEquals(404, get("/api/unknown").statusCode());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

`@SpringBootTest(RANDOM_PORT)` starts a real embedded server instead of calling Java methods directly. `@LocalServerPort` obtains the OS-assigned HTTP port, avoiding port 8080 conflicts in CI.

The test suite verifies simultaneously:

- the annotated endpoint is available;
- the functional endpoint is available;
- both handle path variables;
- both share the JSON contract while `source` identifies the processing branch;
- an unregistered URL does not accidentally fall back to a route.

`ObjectMapper` is used in the test to compare JSON structurally rather than depending on the order of the two fields, which stays resilient when serialization settings change.

**Limitation:** this test verifies route correctness and HTTP responses, not performance benchmarks, authentication, or HandlerMapping ordering under intentional collisions. When collisions exist, add dedicated tests for those URLs and inspect the active `HandlerMapping` beans.

## 8. When to use a WebMvc.fn router filter vs. a Servlet Filter?

A router can attach a `HandlerFilterFunction` to run before/after functional handlers:

~~~java
@Bean
RouterFunction<ServerResponse> filteredRoutes(
        FunctionalApiHandler handler) {

    return RouterFunctions.route()
            .GET("/api/functional/hello", handler::hello)
            .filter((request, next) -> {
                // Hook applies only to the router branch being built.
                return next.handle(request);
            })
            .build();
}
~~~

This is an **illustrative fragment** and would **collide on endpoints** with the `apiRoutes` bean of the sample project. Do not add both at once without replacing or moving the corresponding route.

Differences among extension points:

- **Router filter / HandlerFilterFunction:** attached to the functional router chain; does not automatically run on annotated controllers.
- **Servlet Filter:** runs at the Servlet layer before/after DispatcherServlet and can cover both branches if its filter mapping covers the corresponding URLs.
- **HandlerInterceptor:** hooks into the MVC HandlerExecutionChain, with scope depending on HandlerMapping configuration and path patterns.
- **Spring Security servlet filter chain:** the key place to enforce shared authentication and authorization for both endpoint styles.

If you need a shared correlation ID or security check, do not put mandatory logic solely in a functional router filter and forget the annotated endpoints. Pick an appropriate shared layer and test all URLs.

## 9. Validation, JSON, and error handling when mixing both models

### 9.1. Request binding differs

An annotated controller can use:

~~~java
@PostMapping("/orders")
public ResponseEntity<OrderView> create(
        @Valid @RequestBody CreateOrderCommand command) {
    OrderView result = service.create(command);
    return ResponseEntity.ok(result);
}
~~~

This is a **method fragment** requiring the DTO, service, Bean Validation, and appropriate imports. `@Valid` on a controller argument is supported by MVC when a matching Bean Validation provider is present.

A functional handler uses:

~~~java
public ServerResponse create(ServerRequest request)
        throws Exception {

    CreateOrderCommand command =
            request.body(CreateOrderCommand.class);

    // Validate command using appropriate validator/business rules.
    OrderView result = service.create(command);

    return ServerResponse.ok().body(result);
}
~~~

This is also a **fragment**, not part of the runnable project in section 5. It highlights the difference: the functional handler explicitly reads the body from `ServerRequest`; it does not automatically receive the same annotation-based argument resolvers as a controller method.

If both route styles handle the same order-creation logic, share **validators, services, and error contracts** so the two endpoints do not accidentally return different 400/422/500 responses.

### 9.2. Exception handling

With Controllers, Spring MVC normally uses `@ExceptionHandler`, `@ControllerAdvice`, or `@RestControllerAdvice` to standardize errors.

With WebMvc.fn, handlers can return an error `ServerResponse` directly, use a router filter, or rely on an appropriate `HandlerExceptionResolver`. **Do not assume** every `@ExceptionHandler` designed for annotated controllers will automatically apply identically to functional handlers.

Safe guidelines:

1. Define a standard error body (code, message, correlation ID, timestamp if needed).
2. Establish a single policy in the business/exception layer for both branches.
3. Write tests for 400/404/403/500 covering the errors the application actually produces.
4. Ensure error messages do not leak stack traces or internal data in production.
5. For JSON, review shared `HttpMessageConverter`/Jackson configuration so you do not end up with two different response formats.

### 9.3. Avoid confusing HTTP methods with "route priority"

For instance, a controller accepts `POST /api/orders` while a functional router has `GET /api/orders`. They can complement each other when matching conditions are compatible; yet if a functional router has an overly broad catch-all or fallback that ignores the HTTP method, a request can be routed to the wrong branch.

Declare methods, paths, `Content-Type`, and `Accept` explicitly where needed. CORS preflight `OPTIONS` must also be tested if browsers call the API cross-origin.

## 10. Spring Security and CORS when both endpoint styles exist

With Spring MVC, both annotated controllers and WebMvc.fn pass through the **Servlet Filter chain**, including Spring Security when the security starter is included. Therefore, whether a route is annotated or functional does not itself decide if an endpoint is public or private.

Suppose you have two groups:

~~~text
/api/annotated/**  -> requires login
/api/functional/** -> also requires login
~~~

If the policy only protects `/api/annotated/**` while permitting everything else, functional endpoints may be exposed. Design authorization around business resources and deny-by-default where appropriate, then test thoroughly:

- Anonymous calls to protected endpoints must be rejected appropriately (401 or login redirect, per configuration).
- Authenticated users lacking permissions must be blocked (typically 403).
- Authorized users can call both annotated and functional endpoints.
- `OPTIONS` preflight is not improperly blocked when CORS is configured.
- No wildcard/fallback route leaks information by bypassing rules.

**CORS** in Spring MVC can be configured via `WebMvcConfigurer#addCorsMappings` and `@CrossOrigin` on controllers where appropriate. However, some WebMvc.fn routes interact differently with CORS, filters, and request predicates; test preflight on both branches. CORS only governs browser response-reading permissions and does not replace authentication/authorization.

With reactive WebFlux, security uses `SecurityWebFilterChain`; do not copy Servlet MVC's `SecurityFilterChain` verbatim.

## 11. Impact of context path, servlet path, and proxies

Both routers and controllers run behind the Servlet context. Example:

~~~properties
server.servlet.context-path=/portal
~~~

Then the URLs in the MVC project become:

~~~text
/portal/api/annotated/hello
/portal/api/functional/hello
~~~

Do not add `/portal` to `@RequestMapping` or `RouterFunctions.GET(...)`, because the context path prefix is managed by the Servlet container.

If configured:

~~~properties
spring.mvc.servlet.path=/service
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
~~~

Spring Boot 3.5 has a caveat: Servlet prefix mapping via `spring.mvc.servlet.path` is incompatible with the default `PathPatternParser`; choose `ant-path-matcher` per Boot documentation. Then the MVC URLs become `/service/api/annotated/hello` and `/service/api/functional/hello`, plus any context path. **The initial sample code does not need these properties.**

Behind an ingress/proxy, public URLs can also be rewritten. If browsers call `https://example.com/v1/...` while the backend receives `/api/...`, test full paths on both sides rather than confusing rewrites with Servlet mappings.

## 12. Adding more routers while keeping Controllers: project organization

As the number of endpoints grows, you can use a feature-oriented structure:

~~~text
com.example.shop
  ShopApplication
  customers/
    CustomerController.java
    CustomerService.java
  reports/
    ReportHandler.java
    ReportRoutes.java
    ReportService.java
  inventory/
    InventoryController.java
    InventoryService.java
  shared/
    ErrorResponse.java
    SecurityConfig.java
~~~

Idea:

- Domains customers/inventory use annotated controllers because they benefit from DTO binding/validation.
- Domain reports uses a WebMvc.fn router for a specialized set of request predicates.
- All HTTP adapters call appropriate service/application layers; never embed DB queries directly inside router beans.
- Keep bean registrations within `@SpringBootApplication`'s component scan or import configurations explicitly.
- Maintain path ownership conventions and API versioning: `/api/v1/customers`, `/api/v1/reports`.

**Do not force every feature to use both handler styles.** Only combine them when there is a clear benefit; if a controller is already simple and maintainable, there is no reason to convert it to a functional router and add complexity.

### 12.1. Registering multiple RouterFunction beans

You can register multiple `RouterFunction<ServerResponse>` beans to split features, such as reports and search modules. Spring combines/routes those beans via `RouterFunctionMapping`.

Risk: beans having overlapping routes. Bean/router order can affect which handler runs. If order matters, manage it explicitly and write tests; do not rely on class names or filesystem listing order.

For a feature with specific routes and a fallback, it is easier to control if you group them into **one router builder** with specific routes placed before general ones.

### 12.2. Avoid creating RouterFunctions outside the Spring context

Some code only works if you invoke it manually:

~~~java
RouterFunction<ServerResponse> localRouter =
        RouterFunctions.route()
            .GET("/local",
                request -> ServerResponse.ok().body("local"))
            .build();
~~~

This is an **in-method fragment**: if `localRouter` is not returned from a `@Bean` or registered as a Spring-managed object, `RouterFunctionMapping` will not discover it automatically. Place bean configuration in a component-scanned class.

## 13. When do you combine annotated Controllers with WebFlux.fn?

This is the **second combination style**, intended for **REACTIVE** applications rather than Spring MVC. In WebFlux, `@RestController` and `RouterFunction` from package `org.springframework.web.reactive.function.server` run together under `DispatcherHandler`.

Key differences:

- Annotated controllers can return `Mono<T>` or `Flux<T>`.
- Functional handlers have methods taking `ServerRequest` and returning `Mono<ServerResponse>`.
- Reactor Netty is the default embedded server of `spring-boot-starter-webflux`.
- Both run inside one reactive app; do not add `spring-boot-starter-web`.
- Do not bring WebMvc.fn types into a WebFlux project: even though generic names collide, they are a separate API system.

### 13.1. Standalone WebFlux project

Structure:

~~~text
mixed-routing-webflux/
  pom.xml
  src/main/resources/application.properties
  src/main/java/com/example/mixedflux/
    MixedFluxApplication.java
    ReactiveController.java
    ReactiveRoutes.java
~~~

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
    <artifactId>mixed-routing-webflux</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

`src/main/resources/application.properties`:

~~~properties
server.port=8081
~~~

`src/main/java/com/example/mixedflux/MixedFluxApplication.java`:

~~~java
package com.example.mixedflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MixedFluxApplication {
    public static void main(String[] args) {
        SpringApplication.run(MixedFluxApplication.class, args);
    }
}
~~~

`src/main/java/com/example/mixedflux/ReactiveController.java`:

~~~java
package com.example.mixedflux;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveController {

    @GetMapping(
        path = "/api/annotated/hello",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> hello() {
        return Mono.just("hello reactive annotated");
    }
}
~~~

`src/main/java/com/example/mixedflux/ReactiveRoutes.java`:

~~~java
package com.example.mixedflux;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class ReactiveRoutes {

    @Bean
    RouterFunction<ServerResponse> reactiveApiRoutes() {
        return RouterFunctions.route()
                .GET("/api/functional/hello",
                    request -> ServerResponse.ok()
                        .contentType(MediaType.TEXT_PLAIN)
                        .bodyValue("hello reactive functional"))
                .build();
    }
}
~~~

Run inside the WebFlux project directory:

~~~bash
mvn spring-boot:run
~~~

Verify:

~~~bash
curl -i http://localhost:8081/api/annotated/hello
curl -i http://localhost:8081/api/functional/hello
~~~

Expected bodies respectively:

~~~text
hello reactive annotated
~~~

and:

~~~text
hello reactive functional
~~~

Both HTTP endpoints run on the same **reactive server**. `ReactiveController.hello()` returns `Mono<String>`; the functional handler used by the router returns `Mono<ServerResponse>` from `ServerResponse.ok().bodyValue(...)`. This is a key distinction from WebMvc.fn.

### 13.2. Do not accidentally include both starters

If a project includes both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot normally **prefers Servlet MVC** when auto-detecting the web application type. In that case, Spring WebFlux.fn routers may not run as intended. Confirm explicitly whether your app is MVC or WebFlux via the dependency graph and startup logs.

An application can use WebClient inside MVC without running a WebFlux server. `WebClient` is a reactive HTTP client; it does not determine the HTTP server stack.

## 14. Testing in a project with two routing models

Split tests into three tiers:

| Tier | Goal | Tools |
|---|---|---|
| Service unit | Test business logic independently of HTTP | JUnit, Mockito where needed |
| Web slice / route-level | Test binding, URLs, statuses, request/response at web layer | MockMvc for MVC; WebTestClient for WebFlux |
| Full integration | Prove both endpoint groups truly run together on one server/app | `@SpringBootTest(RANDOM_PORT)` + HTTP client |

With Spring MVC, `MockMvc` can test controllers and functional routes loaded in the test context. Note that `@WebMvcTest` is a slice test and not all `RouterFunction`/service beans are automatically loaded; you may need `@Import` or `@MockBean`/version-appropriate mocking. Real HTTP tests are less error-prone when confirming **both endpoint styles together**.

With WebFlux, `WebTestClient` lets you test reactive endpoints without building a manual HTTP client. When you need to prove the real server starts properly, use `@SpringBootTest(RANDOM_PORT)` and WebTestClient bound to the server or a real HTTP client.

Route collision testing should cover:

1. Whether literal and parameter endpoints overlap.
2. Whether a functional wildcard steals annotation routes or static resources.
3. Whether paths sharing a URL with different HTTP methods/Accept/Content-Type pick the right branch.
4. Whether protected endpoints can be bypassed via another route.
5. Whether error contracts stay consistent when validation or services fail.
6. Whether context paths, servlet paths, gateway rewrites, and CORS distort URLs.

## 15. Debugging when one handler branch is not selected

### 15.1. Controller works, functional router returns 404

Common causes:

- Accidentally imported `org.springframework.web.reactive.function.server.RouterFunction` in an MVC project.
- Forgot to declare `@Bean RouterFunction<ServerResponse>`.
- Config class sits outside the component-scan package.
- Router predicate is too strict, e.g., matching only GET or a specific header/Accept.
- Router has a different prefix than the URL sent by the client.
- Custom `HandlerMapping`/order or fallback intercepts the path.

Fix: check packages, bean registration, actual method/path, startup logs, and write a `@SpringBootTest(RANDOM_PORT)` test.

### 15.2. Functional route works, yet Controller is never called

One cause is a functional router sharing the same path/method or having a broader wildcard and running before `RequestMappingHandlerMapping`. Check route collisions, router order, and request predicates; prefer fixing the route contract rather than tweaking order to keep two handlers on the same URL.

Additionally, the controller might not be component-scanned, or the effective annotation mapping combining class `@RequestMapping` + method `@GetMapping` produces a different URL than expected.

### 15.3. Application fails at startup with ambiguous mapping

This typically happens with **two annotated methods** registering duplicate mappings inside the annotation mapping mechanism. It is not normally triggered by one annotated route and one functional route sharing a URL, because they belong to two different `HandlerMapping` beans.

Fix routes for clear ownership, inspect context path/version properties, and do not rely on declaration order to pick controller handlers.

### 15.4. GET works, yet POST returns 404 or 405

Router `GET(...)` does not register POST automatically. Annotation `@GetMapping` is not `@PostMapping` either. Returning 404 vs. 405 can differ depending on how allowed methods are determined and which HandlerMappings exist.

When debugging, record the exact **HTTP method, path, query, Content-Type, Accept**, and response status; do not just say "the URL failed".

### 15.5. Same DTO returns different JSON content types

Controllers have `@RestController` and converters handling returned objects, whereas functional handlers must construct a `ServerResponse` with a body and appropriate optional content type. Check message converters/serialization config, request `Accept`, response `Content-Type`, and DTOs.

If serialization fails, stack traces at the adapter/response-writer layer can differ. Do not assume every failure comes from handler mapping.

### 15.6. Spring Security or Actuator behaves unexpectedly

- Security policies must protect both branches (annotation and functional).
- If Spring Boot Actuator is present and safely exposed, `/actuator/mappings` helps inspect registered mappings. That endpoint **does not exist** in the sample project because the POM does not include Actuator.
- You can enable MVC logging in development to observe request mappings, yet avoid broad TRACE logging in production due to log volume and request metadata exposure.

Useful loggers in Spring MVC:

~~~properties
logging.level.org.springframework.web.servlet.DispatcherServlet=DEBUG
logging.level.org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping=TRACE
logging.level.org.springframework.web.servlet.function.support.RouterFunctionMapping=TRACE
~~~

Depending on version, logger names and output details may vary; verify against actual logs instead of relying on fixed log strings.

## 16. Gradual migration without breaking the API

Suppose a project currently has a controller for reports. You want to migrate to a functional router to consolidate complex predicates:

1. **Keep the service, DTOs, and error contract unchanged.** Replace only the HTTP adapter layer.
2. Create the router/functional handler on a **different** URL during testing, e.g., `/internal/reports-v2`.
3. Add tests comparing controller and functional handler outputs for equivalent requests: statuses, headers, JSON bodies, errors, and permissions.
4. Test compatibility of validation/argument binding/exception handling: annotation and functional request APIs differ.
5. Once verified, route traffic via gateway or controlled route switch; **remove or disable the old route**, avoiding keeping two handlers on the same path/method expecting priority to sort it out.
6. Monitor metrics, latency, and error rates; maintain rollback capability.
7. Finally clean up unused imports/beans and keep route conventions clear.

If you only want to **extend** rather than migrate, there is no need to touch existing controllers: simply register an additional RouterFunction bean on its own path and add tests verifying parallel operation.

## 17. Implementation checklist

- [ ] Confirm whether the application is **Spring MVC** or **WebFlux**; do not mix the two RouterFunction packages.
- [ ] For MVC, project uses `spring-boot-starter-web`, without `@EnableWebMvc` to enable WebMvc.fn.
- [ ] Annotated controllers are within component scan and use accurate path/method conditions.
- [ ] Functional routers are returned from `@Bean RouterFunction<ServerResponse>` with stack-appropriate package imports.
- [ ] Functional routes inside the same builder place **specific routes before general routes**.
- [ ] Clear path ownership exists; annotated and functional routes do not fight over the same URL.
- [ ] Services/DTOs/domain rules are shared; HTTP adapter logic is not duplicated.
- [ ] JSON content type, validation, and error contracts are tested for both branches.
- [ ] Spring Security protects both endpoint groups, and CORS/OPTIONS are tested.
- [ ] Context path/servlet path/gateway rewrites do not duplicate paths.
- [ ] At least one `RANDOM_PORT` integration test exercises both annotated and functional endpoints.
- [ ] During route migration, behavior-comparison tests exist and no route collisions remain.
- [ ] For WebFlux, functional handlers return `Mono<ServerResponse>` and annotated controllers use reactive types where appropriate.

## Official references

- [Spring Framework 6.2 — Functional Endpoints (WebMvc.fn)](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-functional.html): WebMvc.fn running on the same DispatcherServlet as annotation controllers, RouterFunction/HandlerFunction, router ordering, and bean registration.
- [Spring Framework 6.2 — Spring MVC DispatcherServlet](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet.html): dispatch flow, HandlerMapping, and HandlerAdapter.
- [Spring Framework 6.2 — Annotated Controllers](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-requestmapping.html): request mapping conditions and specificity.
- [Spring Framework 6.2 — Functional Endpoints (WebFlux.fn)](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): reactive RouterFunction/HandlerFunction and coexistence with annotated controllers.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): MVC autoconfiguration and server.
- [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): WebFlux autoconfiguration, reactive stack, and functional routes.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, random port, web slices.

**Conclusion:** You can use `@RestController` and `RouterFunction` side by side in **one Spring Boot application**, sharing the same port, Spring context, and business services. For MVC you must use **WebMvc.fn** and `DispatcherServlet`; for WebFlux you must use **WebFlux.fn** and `DispatcherHandler`. The keys to keeping the system maintainable are avoiding route collisions, keeping security/validation consistent, and having real HTTP tests proving both branches route accurately.
