# Functional Routing with WebMvc.fn and API Differences with WebFlux.fn

## 1. Goal: HTTP routing with functions instead of annotations

Spring Framework offers two programming models alongside @Controller and @RequestMapping:

- **WebMvc.fn**: functional endpoints in **Spring Web MVC**, running on the Servlet stack and DispatcherServlet. A handler is a function that takes a ServerRequest and returns a ServerResponse **directly**, following a synchronous contract.
- **WebFlux.fn**: functional endpoints in **Spring WebFlux**, running on the reactive stack and DispatcherHandler. A handler is a function that takes a ServerRequest and returns a **Mono<ServerResponse>**, following a reactive contract.

Both APIs intentionally share very similar conceptual names: RouterFunction, HandlerFunction, ServerRequest, ServerResponse, RequestPredicates, and RouterFunctions. However, the types belong to **different packages**, have different return contracts, and cannot be swapped merely by changing a dependency.

In WebMvc.fn, a developer declares paths and HTTP methods as a RouterFunction, then assigns a HandlerFunction to receive matching requests. Spring MVC automatically detects RouterFunction beans in the ApplicationContext and integrates them into normal request dispatching.

Conceptual example:

~~~text
GET /api/items/42
    |
    v
RouterFunction: find matching predicate
    |
    v
HandlerFunction: process ServerRequest
    |
    v
ServerResponse: write status, headers, and body
~~~

With WebFlux.fn, the conceptual sequence is similar, except handler lookup and response creation are tied to Publisher/Mono and the reactive request pipeline.

This lesson uses **Spring Boot 3.5.x, Spring Framework 6.2.x, and Java 17+** for examples. The code for WebMvc.fn and WebFlux.fn resides in **two separate projects** to avoid mixing web stacks. When moving to another version, check the corresponding package and API documentation.

## 2. Quick comparison table: WebMvc.fn vs. WebFlux.fn

| Aspect | WebMvc.fn | WebFlux.fn |
|---|---|---|
| Framework | Spring Web MVC | Spring WebFlux |
| Typical Boot starter | spring-boot-starter-web | spring-boot-starter-webflux |
| Root package | org.springframework.web.servlet.function | org.springframework.web.reactive.function.server |
| HTTP dispatch | DispatcherServlet | DispatcherHandler |
| Route description API | RouterFunction<ServerResponse> | RouterFunction<ServerResponse> in the reactive package |
| HandlerFunction contract | ServerResponse handle(ServerRequest) | Mono<ServerResponse> handle(ServerRequest) |
| Reading request body | request.body(Type.class), normally synchronous | request.bodyToMono(Type.class), reactive |
| Building simple response body | ServerResponse.ok().body(value) | ServerResponse.ok().bodyValue(value), returns Mono<ServerResponse> |
| Fit for blocking libraries | Works in the Servlet model, requires thread and timeout management | Do not block the event loop; prefer reactive I/O, isolate blocking if unavoidable |
| Typical test suite | MockMvc | WebTestClient |
| Boot integration | MVC auto-configuration | WebFlux auto-configuration |
| Typical security | Servlet Spring Security FilterChain | Reactive SecurityWebFilterChain |

The same snippet like RouterFunctions.route().GET(...) can exist in both models. **Do not identify the stack by the RouterFunctions name**; inspect package imports, ApplicationContext type, and the active starter.

WebMvc.fn is neither an "older version" of WebFlux.fn nor a way to run reactive code on Servlets. It is Spring MVC's functional programming model, using functional-friendly request and response types while remaining inside the Servlet lifecycle.

## 3. Core components

### RouterFunction

RouterFunction takes a ServerRequest and finds a matching HandlerFunction using RequestPredicate. It mirrors the responsibility of mapping URLs and HTTP methods, expressed in Java code rather than annotations.

In WebMvc.fn, conceptually:

~~~java
Optional<HandlerFunction<ServerResponse>> route(ServerRequest request);
~~~

In WebFlux.fn, conceptually:

~~~java
Mono<HandlerFunction<ServerResponse>> route(ServerRequest request);
~~~

These signatures illustrate the return type difference, not two custom interfaces to define yourself. In application code, you normally use the RouterFunctions.route() builder instead of manually implementing RouterFunction.

### HandlerFunction

HandlerFunction takes a ServerRequest and produces a response:

~~~java
// WebMvc.fn: synchronous signature illustration
ServerResponse handle(ServerRequest request) throws Exception;
~~~

~~~java
// WebFlux.fn: reactive signature illustration
Mono<ServerResponse> handle(ServerRequest request);
~~~

With MVC, the handler can return ServerResponse directly after finishing processing. With WebFlux, Mono represents an asynchronous response; returning Mono does not itself prove every step inside is non-blocking if the code still calls synchronous databases/JDBC on the event loop.

### ServerRequest and ServerResponse

ServerRequest provides access to path variables, query parameters, headers, and the request body. ServerResponse is the abstraction for building responses, such as HTTP 200, 201, 400, 404, Content-Type, and body.

The two pairs of ServerRequest/ServerResponse **are not the same classes**, despite sharing identical names. Their respective imports are:

~~~java
// MVC:
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;
~~~

~~~java
// WebFlux:
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
~~~

When an IDE auto-imports the wrong package, compilation errors can surface on RouterFunction, HandlerFunction, or lambda return types.

### RequestPredicates

RequestPredicates provides matching conditions on HTTP method, path, Accept, Content-Type, and other attributes. They can be combined with and(), or(), or negate(). Example of a route limited to GET requests accepting JSON:

~~~java
.GET("/api/items/{id}",
        RequestPredicates.accept(MediaType.APPLICATION_JSON),
        handler::find)
~~~

RequestPredicate inspects HTTP metadata and does not replace request body validation. A request with an incompatible Accept header may fail to match that specific route; do not assume you will always get 406 or 404 without checking all HandlerMappings and actual exception handling.

## 4. How is WebMvc.fn registered in Spring Boot?

In Spring Boot using spring-boot-starter-web, you normally just declare a RouterFunction<ServerResponse> bean inside a component-scanned @Configuration.

~~~text
Spring Boot MVC application
        |
        +--> @Configuration declares RouterFunction bean
        |
        v
RouterFunctionMapping discovers RouterFunction beans
        |
        v
HandlerFunctionAdapter executes HandlerFunction
        |
        v
DispatcherServlet continues the MVC response lifecycle
~~~

Spring MVC infrastructure recognizes RouterFunction beans. You do not need to manually create DispatcherServlet, HandlerFunctionAdapter, or a new HTTP server just to use functional routes.

You can use WebMvc.fn **alongside @RestController** in the same Spring MVC application. They are two ways of describing handlers for the same Servlet-based request pipeline. However, avoid declaring two endpoints with identical method/path and assuming Spring picks globally by specificity: multiple HandlerMappings have different ordering, and precedence between functional and annotated mappings can cause one side to win unexpectedly. Avoid duplicate routes and write integration tests.

**Do not add @EnableWebMvc just to enable WebMvc.fn** in Spring Boot. The Boot starter already integrates MVC functional endpoints; @EnableWebMvc takes over most MVC configuration and can disable helpful Boot auto-configuration defaults.

## 5. Complete example: WebMvc.fn with Spring Boot 3.5

### 5.1. Creating the MVC project

Create a Spring Boot **3.5.x, Java 17+** project with Maven dependencies:

~~~xml
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
~~~

This is the dependencies section inside a pom.xml that already has a Spring Boot parent or BOM dependency management and basic build setup. Starter web brings in Spring MVC and an embedded servlet server, typically Tomcat.

Main files:

~~~text
src/main/java/example/mvcfn/
    MvcFnApplication.java
    MvcItemHandler.java
    MvcRoutes.java
src/test/java/example/mvcfn/
    MvcRoutesTest.java
~~~

### 5.2. Application

File src/main/java/example/mvcfn/MvcFnApplication.java:

~~~java
package example.mvcfn;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcFnApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcFnApplication.class, args);
    }
}
~~~

@SpringBootApplication should be placed in the parent package so component scan discovers the @Component and @Configuration classes in the example.

### 5.3. Synchronous handler

File src/main/java/example/mvcfn/MvcItemHandler.java:

~~~java
package example.mvcfn;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;

@Component
public class MvcItemHandler {

    public ServerResponse featured(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("id", "featured",
                             "name", "Featured item"));
    }

    public ServerResponse find(ServerRequest request) {
        String id = request.pathVariable("id");

        if (!"42".equals(id)) {
            return ServerResponse.notFound().build();
        }

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("id", id, "name", "Example item"));
    }

    public ServerResponse create(ServerRequest request)
            throws Exception {

        Map<?, ?> input = request.body(Map.class);
        Object rawName = input.get("name");

        if (!(rawName instanceof String name) || name.isBlank()) {
            return ServerResponse.badRequest()
                    .body(Map.of("error", "name is required"));
        }

        return ServerResponse.status(HttpStatus.CREATED)
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("id", "43", "name", name));
    }
}
~~~

Characteristics:

- find reads id using request.pathVariable("id") and returns ServerResponse **directly**, not Mono.
- create uses request.body(Map.class) to read the JSON request body in the Servlet environment. Depending on HTTP message converter configuration, invalid JSON can be translated into a client error via MVC exception handling.
- Map is used only for brevity; real applications should use DTOs and strict validation.
- id 42 exists per simulated logic; other ids return 404. POST returns an illustrative object with id 43 yet **does not persist to a database**; therefore do not treat the endpoint as a real CRUD system.

### 5.4. RouterFunction bean

File src/main/java/example/mvcfn/MvcRoutes.java:

~~~java
package example.mvcfn;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.function.RequestPredicates;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class MvcRoutes {

    @Bean
    RouterFunction<ServerResponse> itemRoutes(
            MvcItemHandler handler) {

        return RouterFunctions.route()
                .GET("/api/items/featured",
                        RequestPredicates.accept(
                                MediaType.APPLICATION_JSON),
                        handler::featured)
                .GET("/api/items/{id}",
                        RequestPredicates.accept(
                                MediaType.APPLICATION_JSON),
                        handler::find)
                .POST("/api/items",
                        RequestPredicates.contentType(
                                MediaType.APPLICATION_JSON),
                        handler::create)
                .build();
    }
}
~~~

The handler is injected into the @Bean method. There is no need to register the handler class with @Controller or @RestController because it is a regular @Component invoked via functional routing.

The route order is intentional: **/api/items/featured before /api/items/{id}**. If the dynamic route /{id} came first, the string featured would be treated as an id and the more specific route below would never get a chance to run inside that router.

POST uses contentType(APPLICATION_JSON) to restrict the request body media type per example intent. GET uses accept(APPLICATION_JSON) to match requests expecting JSON. Both conditions are RequestPredicates, not authentication mechanisms.

### 5.5. Running and testing

Run from the project directory:

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

If the application does not override server.port, Boot normally listens on port 8080.

~~~bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/items/42
~~~

HTTP 200 response with JSON body equivalent to:

~~~json
{"id":"42","name":"Example item"}
~~~

Key order in JSON may vary because Map is used; do not rely on byte-for-byte JSON strings when testing content.

~~~bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/items/featured
~~~

Expected to return id=featured and name=Featured item, because the specific route is placed first.

~~~bash
curl -i -X POST http://localhost:8080/api/items \
  -H "Content-Type: application/json" \
  -d '{"name":"Notebook"}'
~~~

Expected status 201, JSON containing id=43 and name=Notebook. This is not a real data-persistence write.

~~~bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/items/999
~~~

Expected status 404 because handler find explicitly returns notFound when id is not 42.

## 6. Testing WebMvc.fn with MockMvc

In a servlet MVC application, MockMvc integrates smoothly with DispatcherServlet and RouterFunctionMapping. File src/test/java/example/mvcfn/MvcRoutesTest.java:

~~~java
package example.mvcfn;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class MvcRoutesTest {

    @Autowired
    MockMvc mvc;

    @Test
    void findItem() throws Exception {
        mvc.perform(get("/api/items/42")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("42"))
                .andExpect(jsonPath("$.name").value("Example item"));
    }

    @Test
    void moreSpecificRouteWins() throws Exception {
        mvc.perform(get("/api/items/featured")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("featured"));
    }

    @Test
    void missingItemReturns404() throws Exception {
        mvc.perform(get("/api/items/999")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound());
    }

    @Test
    void createItem() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Notebook\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.name").value("Notebook"));
    }

    @Test
    void blankNameReturns400() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"\"}"))
                .andExpect(status().isBadRequest());
    }
}
~~~

This test pattern boots the real MVC ApplicationContext without opening a normal HTTP socket. It is sufficient to verify that RouterFunction beans are discovered, request predicates work, and handlers return the desired statuses/bodies.

Run:

~~~bash
./mvnw test
~~~

If Spring Security is added, MockMvc requests may receive 401/403 before reaching the handler; in that case, configure test users, policies, or appropriate security instead of concluding the router is broken.

## 7. WebFlux.fn: same route expression, different execution contract

WebFlux.fn uses the same conceptual names as WebMvc.fn, but belongs to the reactive package. Do not convert an MVC handler to WebFlux simply by changing the return type to Mono while keeping servlet imports.

Differences visible immediately:

~~~java
// WebMvc.fn:
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;
~~~

~~~java
// WebFlux.fn:
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;
~~~

Reactive handler functions typically use request.bodyToMono(...), flatMap(...), ServerResponse.bodyValue(...), body(Publisher, Class), Mono.error(...), or appropriate Reactor operators to construct a pipeline.

When a handler returns Mono<ServerResponse>, producing the response value can be deferred until the publisher is subscribed. This execution model differs from an MVC handler returning ServerResponse directly. With non-blocking I/O, reactive pipelines help manage resources and downstream pressure effectively; however, a Thread.sleep or blocking JDBC call on the event loop still causes problems.

### WebFlux.fn diagram

~~~text
HTTP request
    |
    v
Reactive HTTP server / Reactor Netty (commonly used with Boot)
    |
    v
WebFilter chain
    |
    v
DispatcherHandler
    |
    v
RouterFunctionMapping -> HandlerFunctionAdapter
    |
    v
Mono<ServerResponse>
    |
    v
ServerResponseResultHandler writes response via Publisher
~~~

Both WebFlux.fn and WebMvc.fn can run alongside annotated controllers belonging to their respective stacks. Having functional routes does not disable the corresponding @RestController mechanism.

## 8. WebFlux.fn example in a separate Spring Boot project

### 8.1. Dependencies and structure

Create a **second project** with Spring Boot 3.5.x, Java 17+, using spring-boot-starter-webflux and spring-boot-starter-test:

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
</dependencies>
~~~

This project **does not declare spring-boot-starter-web**. If both starters are present, Spring Boot normally selects MVC per its web application type inference rules; having WebFlux.fn classes on the classpath is not enough to prove the application is running on the reactive runtime.

Files:

~~~text
src/main/java/example/fluxfn/
    FluxFnApplication.java
    FluxItemHandler.java
    FluxRoutes.java
src/test/java/example/fluxfn/
    FluxRoutesTest.java
~~~

### 8.2. Application

File src/main/java/example/fluxfn/FluxFnApplication.java:

~~~java
package example.fluxfn;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FluxFnApplication {

    public static void main(String[] args) {
        SpringApplication.run(FluxFnApplication.class, args);
    }
}
~~~

No @EnableWebFlux is needed in Spring Boot when using WebFlux.fn with default auto-configuration.

### 8.3. Reactive handler

File src/main/java/example/fluxfn/FluxItemHandler.java:

~~~java
package example.fluxfn;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Mono;

@Component
public class FluxItemHandler {

    public Mono<ServerResponse> featured(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("id", "featured",
                                  "name", "Featured item"));
    }

    public Mono<ServerResponse> find(ServerRequest request) {
        String id = request.pathVariable("id");

        if (!"42".equals(id)) {
            return ServerResponse.notFound().build();
        }

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("id", id, "name", "Example item"));
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(Map.class)
                .flatMap(input -> {
                    Object rawName = input.get("name");

                    if (!(rawName instanceof String name)
                            || name.isBlank()) {
                        return ServerResponse.badRequest()
                                .bodyValue(
                                        Map.of("error",
                                               "name is required"));
                    }

                    return ServerResponse.status(HttpStatus.CREATED)
                            .contentType(MediaType.APPLICATION_JSON)
                            .bodyValue(
                                    Map.of("id", "43", "name", name));
                })
                .switchIfEmpty(
                        ServerResponse.badRequest()
                                .bodyValue(
                                        Map.of("error",
                                               "body is required")));
    }
}
~~~

This is the reactive counterpart to the MVC simulated logic:

- find returns Mono<ServerResponse> even when data comes from memory and the result is already known.
- create reads the body with bodyToMono(Map.class) and processes it with flatMap, without calling block().
- When the body is empty and bodyToMono completes with no item, switchIfEmpty produces a 400 response instead of returning an empty Mono.empty() with no response.
- Serializing Map to JSON relies on codecs registered by WebFlux auto-configuration; spring-boot-starter-webflux provides the default infrastructure.
- In a real system, Mono should connect to reactive I/O calls like R2DBC or WebClient where appropriate; do not wrap a blocking repository in Mono.just and assume it is non-blocking.

### 8.4. Reactive RouterFunction bean

File src/main/java/example/fluxfn/FluxRoutes.java:

~~~java
package example.fluxfn;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class FluxRoutes {

    @Bean
    RouterFunction<ServerResponse> itemRoutes(
            FluxItemHandler handler) {

        return RouterFunctions.route()
                .GET("/api/items/featured",
                        RequestPredicates.accept(
                                MediaType.APPLICATION_JSON),
                        handler::featured)
                .GET("/api/items/{id}",
                        RequestPredicates.accept(
                                MediaType.APPLICATION_JSON),
                        handler::find)
                .POST("/api/items",
                        RequestPredicates.contentType(
                                MediaType.APPLICATION_JSON),
                        handler::create)
                .build();
    }
}
~~~

Compared with class MvcRoutes, the number of methods and route intent are identical, yet **the RouterFunctions, RequestPredicates, RouterFunction, and ServerResponse imports are completely different**. The method reference handler::find also returns Mono<ServerResponse>, not ServerResponse.

### 8.5. Running and testing with curl

~~~bash
./mvnw spring-boot:run
~~~

In the simple example above, the app runs on port 8080 if unconfigured. Do not run both the MVC and WebFlux projects simultaneously on the same host/port without changing the port of one of them.

~~~bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/items/42
~~~

Expected 200, JSON containing id=42 and name=Example item.

~~~bash
curl -i -X POST http://localhost:8080/api/items \
  -H "Content-Type: application/json" \
  -d '{"name":"Notebook"}'
~~~

Expected 201, JSON containing id=43 and name=Notebook. The observed HTTP responses may look identical to the MVC example, yet **the internal processing mechanism is different**.

## 9. Testing WebFlux.fn with WebTestClient

File src/test/java/example/fluxfn/FluxRoutesTest.java:

~~~java
package example.fluxfn;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class FluxRoutesTest {

    @Autowired
    WebTestClient client;

    @Test
    void findItem() {
        client.get()
                .uri("/api/items/42")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo("42")
                .jsonPath("$.name").isEqualTo("Example item");
    }

    @Test
    void moreSpecificRouteWins() {
        client.get()
                .uri("/api/items/featured")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo("featured");
    }

    @Test
    void createItem() {
        client.post()
                .uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"name\":\"Notebook\"}")
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.name").isEqualTo("Notebook");
    }

    @Test
    void missingItem() {
        client.get()
                .uri("/api/items/999")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void blankName() {
        client.post()
                .uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"name\":\"\"}")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

WebTestClient sends requests to the reactive server inside a full Spring Boot test context with a random port, verifying statuses and JSON bodies. It does not require handlers to use blocking I/O. This test covers the same scenarios as the MockMvc test while relying on a different stack.

For purely functional routes, you can also use WebTestClient.bindToRouterFunction(routerFunction) to create a router-focused test context without booting all of Boot. That suits unit-style routing tests yet does not replace testing auto-configuration, codecs, filters, and the embedded HTTP server in a real environment.

## 10. Route declaration order and RequestPredicate specificity

Functional routing generally operates sequentially: try the first route; if it does not match, try the next route. Therefore, **place specific routes before dynamic or broader routes**.

Risky example:

~~~java
// Example of a confusing order:
return RouterFunctions.route()
        .GET("/api/items/{id}", handler::find)
        .GET("/api/items/featured", handler::featured)
        .build();
~~~

GET /api/items/featured can be matched by route /{id} first, turning featured into the id path variable and leaving the subsequent route unchosen.

Clear way to write it:

~~~java
return RouterFunctions.route()
        .GET("/api/items/featured", handler::featured)
        .GET("/api/items/{id}", handler::find)
        .build();
~~~

These snippets illustrate the structure used in each stack; the imported RouterFunctions/ServerResponse types must match your project's WebMvc.fn or WebFlux.fn stack.

Key points to remember:

- Routes composed via and(), andOther(), add(), or the builder have evaluation priority during matching.
- When multiple RouterFunction beans exist, the system may aggregate them by order. If URLs overlap, write tests and declare ordering intentionally.
- Annotation-based @RequestMapping selects handlers via mapping condition and specificity algorithms; **do not carry those rules over verbatim to functional routers**.
- Paths with a context path, servlet mapping, trailing slash, or encoded characters can affect matching; test with corresponding HTTP requests.
- Use HTTP method and media type predicates to reduce confusion between GET/POST and JSON/text.

One logical bug is placing a catch-all route /** before child routes. It can swallow requests intended for more specific handlers.

## 11. Nested routes: sharing path prefixes

When multiple endpoints start with /api/items, you can group them with nested routing to avoid repeating the prefix:

~~~java
// Structure uses the same builder syntax in WebMvc.fn and WebFlux.fn,
// with stack-appropriate RouterFunctions imports.
return RouterFunctions.route()
        .path("/api/items", builder -> builder
                .GET("/featured", handler::featured)
                .GET("/{id}", handler::find)
                .POST(handler::create))
        .build();
~~~

The example above illustrates nested paths; for POST with no subpath argument, the route maps to the group's root path per the DSL. When you want to avoid any DSL/version subtleties, the explicit .POST("/api/items", ...) form in the complete runnable code is easier to verify.

Beyond path, the builder supports adding a RequestPredicate such as accept(APPLICATION_JSON) or contentType(APPLICATION_JSON), combinable inside nest() or per route. Keep predicate scopes narrow enough not to unintentionally reject endpoints meant to accept other content.

## 12. Functional filters: cross-cutting logic around handlers

Functional endpoints support filters attached to routers. This concept differs from Servlet Filters or reactive WebFilters:

- **WebMvc.fn HandlerFilterFunction** takes the request and next handler, processing under a synchronous contract.
- **WebFlux.fn HandlerFilterFunction** takes the request and next handler, returning Mono<ServerResponse>.
- **Servlet Filter** runs at the Servlet filter chain layer and can affect many request types beyond functional routes.
- **WebFilter** handles cross-cutting concerns in the reactive pipeline across multiple handler types.

Conceptual example for MVC.fn:

~~~java
RouterFunctions.route()
        .GET("/api/ping", request ->
                ServerResponse.ok().body("pong"))
        .filter((request, next) -> {
            // Can read request metadata or log.
            return next.handle(request);
        })
        .build();
~~~

Corresponding example for WebFlux.fn:

~~~java
RouterFunctions.route()
        .GET("/api/ping", request ->
                ServerResponse.ok().bodyValue("pong"))
        .filter((request, next) -> {
            // Do not block the reactive event loop.
            return next.handle(request);
        })
        .build();
~~~

The two snippets belong to separate projects; they omit imports to highlight the difference between body() and bodyValue(). If a filter needs to measure completion time in WebFlux, place logic inside reactive operators such as doFinally rather than timing only Mono creation; Mono is subscribed to and completes later.

Security note: use Spring Security appropriate to the Servlet or reactive stack to manage authentication/authorization. Do not treat checking a custom header inside a functional filter as a security substitute for SecurityFilterChain/SecurityWebFilterChain.

## 13. When functional routes and annotated controllers coexist

Spring allows combining functional routing and annotation-based controllers **within the same web stack**:

- WebMvc.fn with Spring MVC @RestController.
- WebFlux.fn with Spring WebFlux @RestController.

For example, one module uses @RestController for legacy APIs while another adds functional RouterFunctions for new APIs. This combination suits gradual migrations or route groups that do not need annotations.

However:

1. Do not register duplicate GET /api/items/{id} in both @GetMapping and RouterFunction in the same application unintentionally.
2. Do not assume the order between controller mappings and RouterFunctionMapping is determined by Java file order.
3. A filter attached to a RouterFunction does not typically affect annotation-based controllers; to apply policies across all HTTP traffic, use stack-level filters or appropriate framework configuration.
4. WebMvcConfigurer only customizes MVC and WebFluxConfigurer only customizes WebFlux; enabling both does not mean one application processes both models simultaneously.
5. Shared behaviors like JSON serialization may be provided by Boot in both stacks, yet they rely on two distinct message conversion systems: HttpMessageConverter for MVC and HttpMessageReader/Writer for WebFlux.

Organize routes by module, establish clear URL conventions, and write regression tests for both handler types before changing configuration ordering.

## 14. Request body and response body: the biggest difference in code

### MVC.fn

~~~java
// Synchronous, inside an MVC.fn handler
Map<?, ?> input = request.body(Map.class);
return ServerResponse.ok().body(
        Map.of("received", input.get("name")));
~~~

body(Class) uses Servlet synchronous request reading and appropriate HTTP message converters. In real apps, define dedicated DTOs and handle null checks, parse errors, and validation. The Map sample here only illustrates the API.

### WebFlux.fn

~~~java
// Reactive, inside a WebFlux.fn handler
return request.bodyToMono(Map.class)
        .flatMap(input -> ServerResponse.ok()
                .bodyValue(Map.of(
                        "received", input.get("name"))));
~~~

Do not call block() to obtain the Map and return a synchronous ServerResponse from WebFlux.fn. An empty body producing Mono.empty can result in a missing response; define a policy such as switchIfEmpty or defaultIfEmpty.

For streaming multi-item responses in WebFlux.fn, you can use:

~~~java
Flux<Item> items = reactiveService.findAll();
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_NDJSON)
        .body(items, Item.class);
~~~

This snippet only illustrates returning a Publisher; it requires application-defined Item and reactiveService. NDJSON or SSE has different semantics from a buffered JSON array; choose the appropriate MediaType, test backpressure, and handle subscription cancellation.

WebMvc.fn can also serve long-lived or streaming responses via mechanisms supported by the Servlet stack, though having streaming does not automatically turn a request handler reactive and you should not assume identical backpressure behavior to WebFlux.

## 15. Blocking, concurrency, and backpressure

This is a decisive distinction when choosing between WebMvc.fn and WebFlux.fn.

**WebMvc.fn** runs on Spring MVC and Servlet infrastructure. Synchronous handlers can call JDBC or blocking libraries in the conventional way. Under high load, you still need thread pool sizing, connection pools, timeouts, and to avoid holding request threads too long. Configurations using virtual threads (if enabled) can alter the worker model, yet basic HandlerFunctions still return ServerResponse directly.

**WebFlux.fn** is designed for reactive processing. With typical Reactor Netty, event-loop threads must avoid blocking on Thread.sleep, synchronous JDBC, or slow filesystem I/O. If no reactive driver exists, blocking tasks can be isolated on an appropriate scheduler like boundedElastic, while controlling concurrency and avoiding turning everything into pseudo-reactive code.

Illustrative example isolating a blocking API inside a reactive application:

~~~java
Mono<Result> result = Mono.fromCallable(
        () -> blockingLegacyService.load())
        .subscribeOn(Schedulers.boundedElastic());
~~~

This illustrative snippet requires Result, blockingLegacyService, and Reactor Schedulers imports. It is not a full HTTP handler. Ensure the service has proper timeouts, thread pools, and resource lifecycles. Switching threads does not turn a blocking library into a non-blocking one.

Backpressure occurs when downstream signals demand to a Publisher. Do not treat it as a guarantee that every dependent system (database, proxy, browser) automatically accepts arbitrary rates or stays bounded. Test with large responses, client disconnects, and downstream flows.

**Choosing WebMvc.fn is by no means wrong** when business logic relies mainly on JDBC or blocking SDKs and the system runs well on Servlets. WebFlux.fn shines when the entire I/O chain reasonably leverages the reactive model, though complexity is higher and blocking operations demand strict care.

## 16. Security, CORS, and HTTP errors

Functional routes sit inside the same security system of the stack in which they are registered:

| Need | MVC.fn | WebFlux.fn |
|---|---|---|
| Authentication/authorization | Servlet Spring Security SecurityFilterChain | Reactive Spring Security SecurityWebFilterChain |
| Common filter layer | jakarta.servlet.Filter / OncePerRequestFilter | WebFilter |
| CORS framework config | WebMvcConfigurer or filter/security CORS config | WebFluxConfigurer or CorsWebFilter/security CORS config |
| Handler-level functional filter | HandlerFilterFunction from servlet package | HandlerFilterFunction from reactive package |
| Error handling | MVC exception resolvers, error handling | WebExceptionHandler/ErrorWebExceptionHandler and reactive error processing |

Do not put sensitive APIs under /api thinking router predicates control permissions. The router decides which handler processes a URL; security decides which users/clients are permitted to access it.

For HTTP errors, both ServerResponse APIs provide builders for common statuses: ok(), badRequest(), notFound(), and status(...). However, exception propagation differs:

- MVC.fn handlers can throw exceptions synchronously; exception handling follows MVC infrastructure and appropriate error resolvers.
- WebFlux.fn handlers can return Mono.error(exception) or a failing publisher; errors flow through the reactive error pipeline.
- Once response body/headers are committed, not every subsequent error can switch the response to a JSON 500. With long streams, the client may only see a connection close or stream error.

**Map business errors to meaningful statuses:** invalid input -> 400, not found -> 404, created -> 201. Still, design consistent error bodies, validation, and observability for each stack. Do not assume every exception automatically converts into a nicely formatted response like the examples.

## 17. Routing by HTTP method, Content-Type, and Accept

A route normally specifies at least one HTTP method and path. Media type conditions can be added:

- RequestPredicates.accept(MediaType.APPLICATION_JSON): checks the response type accepted by the client via Accept.
- RequestPredicates.contentType(MediaType.APPLICATION_JSON): checks the request payload type via Content-Type.
- RequestPredicates.headers(...) or custom predicates: apply header conditions when needed.
- RequestPredicates.queryParam(...): apply query parameter conditions in supported APIs.

With GET /api/items/42, if the route requires Accept: application/json yet the client sends Accept: text/plain, the route may not match. The final result depends on other routes and error handlers, so test instead of guessing the status.

With POST /api/items, missing Content-Type: application/json can prevent the route from matching. Reading the body and validating after matching remain the handler's responsibility. Do not use a Content-Type predicate as a substitute for JSON schema checks or Bean Validation.

For example, an endpoint supporting multiple response formats needs a clear negotiation strategy. If multiple routes share method/path with different Accept headers, order specific routes properly and test from browsers, curl, and real clients.

## 18. Organizing RouterFunctions by module

A large project can have separate RouterFunction beans per module such as catalog, orders, and health. This lets Java packages mirror URL groups, though ordering must be controlled.

Organizational patterns:

1. One RouterFunction builder per API group, keeping specific routes before general routes.
2. Compose RouterFunctions with andOther or builder.add to control ordering inside one bean.
3. If keeping multiple beans, declare and verify order with @Order or Ordered when needed.
4. Use nested routes and shared RequestPredicates for common prefixes or media types.
5. Place handlers in dedicated classes to separate orchestration from route declarations.

Example structure:

~~~text
catalog/
    CatalogRoutes.java
    CatalogHandler.java
orders/
    OrderRoutes.java
    OrderHandler.java
shared/
    HttpErrorResponses.java
~~~

Do not cram all business logic into huge lambdas inside @Bean routers. That makes mocking dependencies, writing tests, and analyzing errors difficult.

If paths overlap across modules, define clear URL conventions or add tests verifying requests route to the expected handler.

## 19. Common mistakes when switching between WebMvc.fn and WebFlux.fn

| Error | Cause | How to fix |
|---|---|---|
| IDE imports wrong ServerResponse | Both stacks have identically named classes in different packages | Check org.springframework.web.servlet.function vs. org.springframework.web.reactive.function.server |
| MVC handler returns Mono<ServerResponse> | Confusing HandlerFunction contracts | MVC.fn returns ServerResponse directly; WebFlux.fn returns Mono<ServerResponse> |
| Calling bodyValue() on MVC ServerResponse builder | Using reactive API in MVC | MVC.fn normally uses body(value) |
| Calling request.body(Map.class) in WebFlux.fn | Using synchronous MVC API | WebFlux.fn uses bodyToMono(Map.class) |
| Route /{id} swallows /featured | Dynamic route placed before specific route | Place /featured before /{id} |
| @RestController and functional routes share URL | Duplicate handler paths | Avoid method/path collisions, inspect HandlerMapping order |
| Both starter-web and starter-webflux present yet app is not reactive | Boot normally picks MVC when both exist | Choose one starter clearly, verify web application type |
| Blocking JDBC inside reactive handler | Blocks event loop or unsuitable thread | Use reactive I/O or isolate blocking on a proper scheduler |
| Mono.empty fails to produce expected response | Handler emits no ServerResponse | Define fallback via switchIfEmpty or error handling |
| Security filter on router fails to cover other endpoints | Filter scoped only to functional router | Use Spring Security FilterChain/WebFilter on the right stack |
| Default static resources or codecs disappear | Over-customizing with @EnableWebMvc/@EnableWebFlux | Keep Boot auto-configuration unless full control is needed |
| MockMvc test used on reactive-only app | Wrong test stack | Use WebTestClient for WebFlux |
| WebTestClient returns 404 even though @Bean exists | Wrong web type, route path/predicate, or bean not scanned | Check startup report and unit/integration tests |

Another notable mistake: trying to use WebFlux.fn inside an MVC app just because you added the spring-webflux dependency to use WebClient. Having the Spring WebFlux library on the classpath does not mean reactive RouterFunction beans are registered in an MVC application's DispatcherServlet.

## 20. Checklist for choosing a model for your project

Before deciding between WebMvc.fn and WebFlux.fn, answer:

1. Does the application actually run Servlet MVC or reactive WebFlux?
2. Does the project rely heavily on blocking SDKs or traditional JDBC?
3. Do HTTP clients and data access already support non-blocking I/O?
4. Do existing routes already use @RestController, and is functional style needed for part of the API?
5. Can you separate modules cleanly and control route ordering?
6. Does request/response data require streaming, SSE, or backpressure?
7. Are security filters/CORS/error handlers designed for the right stack?
8. Do you need MockMvc or WebTestClient to ensure regression coverage?
9. Do you have adequate observability/timeouts/retries for the chosen stack?
10. Does every method/path/media type combination have tests confirming which handler receives the request?

**Choose WebMvc.fn** if the app is already Spring MVC and you simply want functional-style route definitions; there is no need to convert the whole system to reactive. **Choose WebFlux.fn** if the app already actively uses the reactive stack and wants functional routing with Publisher-based processing. In both, route structure principles and API content can be nearly identical, while dependencies, imports, HandlerFunction contracts, and testing must match the stack.

## 21. Official documentation

- [Spring Framework 6.2 – WebMvc.fn functional endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-functional.html)
- [Spring Framework 6.2 – WebFlux.fn functional endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html)
- [Spring Framework 6.2 – Annotated controllers MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller.html)
- [Spring Framework 6.2 – WebFlux configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html)
- [Spring Boot 3.5 – Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Spring Boot 3.5 – Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html)

**Summary:** Both WebMvc.fn and WebFlux.fn declare RouterFunction and HandlerFunction, but WebMvc.fn belongs to Servlet MVC and returns ServerResponse synchronously, whereas WebFlux.fn belongs to reactive WebFlux and returns Mono<ServerResponse>. Distinguishing the right packages, web stack, body-reading methods, execution models, and test frameworks is the key to building accurate, maintainable functional endpoints.
