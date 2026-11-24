# @Controller, @RestController, and Handler Registration in Spring WebFlux

In Spring WebFlux, an HTTP request must be mapped to a handler method, values from the URL, headers, and body must be converted into Java parameters, and the method's result must then be written as an HTTP response. **@Controller** and **@RestController** are two ways to declare request-handling components in the annotated controller model. Mapping annotations such as **@RequestMapping**, **@GetMapping**, and **@PostMapping** describe the conditions Spring uses to find the right handler.

You need to understand both parts: **the controller is registered as a Spring bean**, while **the handler methods are discovered and have their mappings registered** during application initialization. When a request arrives, WebFlux selects the matching handler, invokes the method using the reactive model, and converts the result into a response. The controller does not call subscribe or block by itself to execute a publisher.

This lesson belongs to the **Controller** group, with the topic **@Controller, @RestController, and handler registration** in Spring Framework - reactive.

## 1. Learning Objectives

After this lesson, you can:

- Distinguish the roles of **@Controller**, **@RestController**, and **@ResponseBody**.
- Explain why a controller must be managed by Spring as a bean for the handler mapping to discover it.
- Describe the lifecycle of handler registration and invocation through **DispatcherHandler**, **HandlerMapping**, **HandlerAdapter**, and **HandlerResultHandler**.
- Combine class-level and method-level mapping using **@RequestMapping**, **@GetMapping**, **@PostMapping**, **@PutMapping**, **@PatchMapping**, and **@DeleteMapping**.
- Declare route conditions using path, HTTP method, params, headers, consumes, and produces.
- Receive data through **@PathVariable**, **@RequestParam**, **@RequestHeader**, **@RequestBody**, **@ModelAttribute**, and argument resolvers.
- Return **Mono**, **Flux**, **ResponseEntity**, or **Mono<Void>** with the correct reactive semantics.
- Distinguish the response body from the view name in a controller that uses view resolution.
- Test mapping registration using **WebTestClient**.
- Avoid route conflicts, calling subscribe/block in a handler, and component scan configuration errors.

## 2. What Is a Controller in WebFlux?

A controller is the component that receives requests at the web layer and coordinates calls to a service or use case. A controller should focus on the HTTP protocol: paths, methods, status, headers, request/response content, and data conversion at the web boundary.

A WebFlux controller is usually a Spring bean annotated with **@Controller** or **@RestController**. Handler methods are marked with mapping annotations. For example:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/{id}")
    public Mono<Product> findById(@PathVariable String id) {
        return productService.findById(id);
    }
}
~~~

This is an illustrative snippet; **Product** and **ProductService** must be declared. The class mapping sets the prefix **/api/products**; the method mapping adds **/{id}** and accepts only GET. Spring discovers the method, creates the mapping metadata, and invokes the method when a request matches.

A controller should not manage the subscription lifecycle itself. When a method returns **Mono<Product>**, WebFlux takes over the publisher and manages subscribing, writing the response, handling errors, and cancellation according to the request lifecycle.

## 3. @Controller and @RestController Differ in Return Semantics

### @Controller

**@Controller** is a Spring stereotype for a web-handling component. It is also recognized as a component so that component scanning registers the bean. In the annotated controller model, a method can return a view name, a ModelAndView, or a response body depending on the return type and annotations.

Example of a controller serving a page:

~~~java
@Controller
@RequestMapping("/pages")
public class PageController {

    @GetMapping("/welcome")
    public String welcome(Model model) {
        model.addAttribute("title", "Welcome");
        return "welcome";
    }
}
~~~

With a suitable view resolver configuration and a template named **welcome**, the returned string is interpreted as a **view name** to render. It is not, by default, text sent directly in the HTTP body.

If a method in a **@Controller** needs to return data directly, you can use **@ResponseBody**:

~~~java
@Controller
@RequestMapping("/api/status")
public class StatusController {

    @GetMapping
    @ResponseBody
    public Mono<Map<String, String>> status() {
        return Mono.just(Map.of("status", "UP"));
    }
}
~~~

Here **@ResponseBody** tells Spring to write the return value into the response body through the message writer/codec system. View resolution is not used for that result.

### @RestController

**@RestController** is a composed annotation that combines **@Controller** and **@ResponseBody** at the class level. Therefore, the class's handler methods write their results to the HTTP response body by default.

~~~java
@RestController
@RequestMapping("/api/status")
public class ApiStatusController {

    @GetMapping
    public Mono<Map<String, String>> status() {
        return Mono.just(Map.of("status", "UP"));
    }
}
~~~

As a result, the response body is encoded, typically as JSON if content negotiation and the codec select JSON.

### Comparison

| Criterion | @Controller | @RestController |
| --- | --- | --- |
| Is a Spring component stereotype | Yes | Yes, through @Controller |
| Default semantics of the return value | Can take part in view/model resolution | Writes the result to the response body |
| Needs @ResponseBody to return JSON directly | Usually yes, or use the annotation at method level | Not needed |
| Suitable for | MVC-style views, templates, or methods that selectively return a body | REST APIs, JSON, XML, streaming responses |
| Can return Mono/Flux | Yes; interpretation depends on return-value handling | Yes; the publisher is written to the response body |

**Choose based on the HTTP contract:** APIs that return data usually use **@RestController**. Applications with HTML pages can use **@Controller** for views and add **@ResponseBody** on the methods that provide APIs. You can mix views and APIs in one **@Controller** class if the semantics of each method are declared clearly.

## 4. A Controller Must Be Registered as a Spring Bean

Mapping annotations do not work automatically just because a class exists in the source code. Spring needs to discover the controller and manage it as a bean.

Common approaches:

1. **Component scanning:** place the controller in a package that is component-scanned.
2. **Explicit bean registration:** declare the bean through configuration when there is a specific reason.
3. **Import configuration:** import the configuration or bean class according to the application's structure.

With Spring Boot, **@SpringBootApplication** is usually placed in the root package. This annotation includes component scanning configuration based on the package of the application class and its sub-packages. For example:

~~~text
com.example.app
├── Application.java
├── controller
│   └── BookController.java
├── service
│   └── BookService.java
└── repository
    └── BookRepository.java
~~~

If Application is located in **com.example.app**, a controller in **com.example.app.controller** is normally scanned. If a controller is outside that package tree, you need to adjust the scan scope or register the bean appropriately.

Example of a startup class:

~~~java
@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Do not create a controller with **new BookController(...)** somewhere arbitrary and expect the handler mapping to discover that object automatically. The handler mapping works with beans managed in the ApplicationContext.

### Dependency Injection in Controllers

Prefer constructor injection to clearly declare the services the controller needs:

~~~java
@RestController
@RequestMapping("/api/books")
public class BookController {

    private final BookService service;

    public BookController(BookService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<Book> findById(@PathVariable String id) {
        return service.findById(id);
    }
}
~~~

Spring finds a suitable **BookService** bean and injects it into the controller. If there is no matching bean, or there are multiple beans that cannot be resolved, the application may fail at startup. A controller should not create a repository itself, open connections itself, or keep mutable request state in fields shared between requests.

## 5. How Are Handlers Registered and Invoked?

In annotated WebFlux, the annotations on the controller are read during ApplicationContext initialization. The overall flow can be pictured as:

~~~text
ApplicationContext starts
       |
       v
Component scanning finds @Controller / @RestController
       |
       v
RequestMappingHandlerMapping
  detects methods that have mappings
       |
       v
Register RequestMappingInfo -> HandlerMethod
       |
       v
HTTP request arrives
       |
       v
DispatcherHandler
       |
       v
HandlerMapping selects the matching HandlerMethod
       |
       v
RequestMappingHandlerAdapter invokes the method
       |
       v
HandlerResultHandler + HttpMessageWriter / ViewResolver
       |
       v
HTTP response
~~~

Main components:

- **DispatcherHandler:** the front controller of WebFlux, coordinating handler lookup and result handling.
- **HandlerMapping:** finds the handler that matches the request. For annotated controllers, **RequestMappingHandlerMapping** detects the mapping methods.
- **HandlerMethod:** describes the method and the bean to be invoked.
- **RequestMappingHandlerAdapter:** invokes the handler method, resolves parameters, and adapts the return type.
- **HandlerResultHandler:** handles the handler's result; for example, writing the response body or rendering a view.
- **HttpMessageReader/HttpMessageWriter and codecs:** read/write content such as JSON, text, or streaming data.
- **ViewResolver:** participates if the controller returns a result that needs to render a view.

This is a generalized model; an actual request also passes through WebFilter, the security chain, exception handlers, and the server adapter depending on the application configuration.

### Mapping Registration Is Not Per-Request Registration

Spring usually discovers mappings when the application starts. When a request arrives, the framework compares the request against the registered mappings to select a handler. You should not create new mappings manually on each controller call.

If two methods register the same indistinguishable mapping, the application may report an ambiguous mapping error at initialization or when handling a request, depending on the type of conflict. Designing routes clearly by path, method, and conditions helps avoid the problem.

## 6. @RequestMapping at Class Level and Method Level

**@RequestMapping** can be placed on a class, a method, or both. Class-level mapping creates a shared path; method-level mapping defines the specific endpoint.

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping
    public Flux<OrderDto> findAll() {
        return orderService.findAll();
    }

    @GetMapping("/{id}")
    public Mono<OrderDto> findOne(@PathVariable String id) {
        return orderService.findById(id);
    }

    @PostMapping
    public Mono<ResponseEntity<OrderDto>> create(
            @RequestBody Mono<CreateOrderRequest> request) {
        return request
            .flatMap(orderService::create)
            .map(saved -> ResponseEntity
                .created(URI.create("/api/orders/" + saved.id()))
                .body(saved));
    }
}
~~~

The combined paths:

| Class-level mapping | Method-level mapping | Endpoint |
| --- | --- | --- |
| /api/orders | @GetMapping | GET /api/orders |
| /api/orders | @GetMapping("/{id}") | GET /api/orders/{id} |
| /api/orders | @PostMapping | POST /api/orders |

The example is a fragment that requires declaring the DTO, the service, and the URI import. It illustrates how to separate routes; it is not a standalone runnable program.

### Shorthand Mapping Annotations

The following annotations are composed annotations based on **@RequestMapping** that set the corresponding HTTP method:

| Annotation | HTTP method |
| --- | --- |
| @GetMapping | GET |
| @PostMapping | POST |
| @PutMapping | PUT |
| @PatchMapping | PATCH |
| @DeleteMapping | DELETE |

You can write:

~~~java
@RequestMapping(path = "/{id}", method = RequestMethod.GET)
public Mono<Book> find(@PathVariable String id) {
    return service.findById(id);
}
~~~

Or use the concise form:

~~~java
@GetMapping("/{id}")
public Mono<Book> find(@PathVariable String id) {
    return service.findById(id);
}
~~~

In general, prefer the specialized annotations to keep the code readable. Avoid declaring multiple mapping annotations on the same method; each method should have one clear primary mapping.

## 7. Mapping Conditions: path, method, params, headers, consumes, produces

A route can be constrained by multiple conditions:

- **path/value:** the path.
- **method:** the HTTP method.
- **params:** conditions on query parameters.
- **headers:** conditions on request headers.
- **consumes:** the request content type that the handler accepts.
- **produces:** the response content type that the handler can produce.

Example:

~~~java
@PostMapping(
    path = "/import",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE,
    headers = "X-Import-Mode=validated")
public Mono<ImportResult> importData(
        @RequestBody Mono<ImportRequest> request) {
    return request.flatMap(importService::importValidated);
}
~~~

The handler matches only when the request is a POST to **/import**, the Content-Type is JSON-compatible, the **X-Import-Mode** header has the value validated, and the client can accept JSON according to the produces condition. The example requires declaring the types and services in the application.

### Content Negotiation

The client can send the **Accept** header to state the format it wants to receive. The **produces** mapping and the message writers/codecs together take part in choosing the response format. If there is no suitable representation, WebFlux may return an appropriate HTTP error such as 406 Not Acceptable.

**Content-Type** describes the format of the request body; **Accept** describes the response format the client accepts. These two concepts do not replace each other.

### Avoid Overly Broad Routes

A method that declares only an overly broad path can be hard to understand and can easily compete with other routes. Prefer specific paths, specific HTTP methods, and clear conditions. If several handlers nearly match, Spring applies specificity rules; an ambiguous mapping should be fixed rather than relying on the declaration order in the source code.

## 8. Reading Request Data into Method Parameters

Spring WebFlux uses argument resolvers to convert request information into method parameters. Some common annotations:

| Annotation | Data source | Example |
| --- | --- | --- |
| @PathVariable | A segment of the URL path | /books/{id} |
| @RequestParam | Query parameter or form parameter depending on configuration | ?page=2 |
| @RequestHeader | HTTP header | Authorization, X-Request-Id |
| @CookieValue | Cookie | session |
| @RequestBody | The decoded request body | JSON object |
| @ModelAttribute | Model/form data and binding | form fields |
| @RequestPart | A part of a multipart request | file upload, metadata |

Example:

~~~java
@GetMapping("/search")
public Flux<Book> search(
        @RequestParam("q") String query,
        @RequestParam(defaultValue = "0") int page,
        @RequestHeader(name = "X-Request-Id", required = false)
            String requestId) {
    return bookService.search(query, page, requestId);
}
~~~

**required=false** allows the header to be absent; in that case the parameter can be null if the declared type allows it. For production applications, consider using Optional or an appropriate data type/validation to avoid arbitrary null handling.

### @RequestBody with Mono and Flux

In WebFlux, the request body can be represented reactively:

~~~java
@PostMapping("/one")
public Mono<Book> createOne(@RequestBody Mono<CreateBookRequest> body) {
    return body.flatMap(bookService::create);
}

@PostMapping(
    path = "/bulk",
    consumes = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<Book> createMany(
        @RequestBody Flux<CreateBookRequest> body) {
    return body.concatMap(bookService::create);
}
~~~

**Mono<CreateBookRequest>** represents a body decoded into a single object. **Flux<CreateBookRequest>** suits a request body with multiple elements under a supported media type/codec, for example NDJSON. For write operations that need ordering, for example use concatMap; if the business logic allows concurrent processing, choose an appropriate operator and concurrency limit.

Do not use block to read the body in a controller. Decoding the body and throttling the data are managed by WebFlux.

## 9. Return Types of Annotated Controllers in WebFlux

A handler method can return many types. Choose the type based on the amount of data, the HTTP status, and the lifecycle of the work.

| Return type | Common meaning |
| --- | --- |
| T | A synchronous result, not the default choice for reactive I/O |
| Mono<T> | 0 or 1 asynchronous result |
| Flux<T> | 0 to many elements |
| Mono<Void> | Asynchronous work that only needs to signal completion |
| ResponseEntity<T> | Synchronous status/header/body |
| Mono<ResponseEntity<T>> | Status/header/body determined asynchronously |
| ResponseEntity<Flux<T>> | Response metadata can be determined up front, the body is a stream |
| Flux<ServerSentEvent<T>> | A stream of SSE events |

### Mono and Not-Found Results

A reactive repository can return **Mono.empty()** when nothing is found. The controller can map that to 404:

~~~java
@GetMapping("/{id}")
public Mono<ResponseEntity<Book>> findById(@PathVariable String id) {
    return bookService.findById(id)
        .map(ResponseEntity::ok)
        .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

This is a clear pattern: if there is data, 200; if the publisher completes empty, 404. If the repository emits an error, the error goes to the exception handling mechanism instead of automatically becoming a 404.

### ResponseEntity and Status/Header

**Mono<ResponseEntity<T>>** is useful when the status or header depends on an asynchronous result. For example, creating a resource can return 201 Created and a Location header. When the status can be determined up front and the body is a stream, **ResponseEntity<Flux<T>>** may be appropriate.

### Flux and Streaming

For a normal JSON response, **Flux<T>** is usually encoded as a JSON array. If you want the client to receive each event over time, choose an appropriate streaming media type and protocol:

- **text/event-stream:** Server-Sent Events.
- **application/x-ndjson:** line-delimited JSON objects if the codec/configuration supports it.
- **application/json:** usually represents a single JSON document/array, and does not by default carry SSE semantics.

SSE example:

~~~java
@GetMapping(
    value = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
        .map(index -> ServerSentEvent.builder("tick-" + index)
            .event("heartbeat")
            .id(Long.toString(index))
            .build());
}
~~~

The example is a fragment that requires importing Duration, ServerSentEvent, and Reactor. The interval source keeps emitting until the subscriber cancels; when the client closes the connection, cancellation must be propagated upstream to stop any cancellable work.

## 10. @ResponseBody, Codecs, and Writing the Response

When a method or class has **@ResponseBody**, Spring does not treat the return value as a view name. The result is converted into the HTTP response body by the corresponding **HttpMessageWriter**s and codecs.

Example:

~~~java
@RestController
public class GreetingController {

    @GetMapping(
        value = "/greeting",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Greeting> greeting() {
        return Mono.just(new Greeting("Hello", "Reactive"));
    }
}
~~~

With a serializable **Greeting** class, the JSON codec writes the corresponding response. The codec selection is based on the data type, content negotiation, codec configuration, and media type. If the client sends an incompatible Accept, the response may fail at the negotiation step.

You do not need to convert an object into a JSON string yourself using Jackson in the controller. Return the object/Mono/Flux and let the message writer serialize it; this approach preserves content negotiation and handles codec errors at the right layer.

### Responses Without a Body

For operations that only need to report completion:

~~~java
@DeleteMapping("/{id}")
public Mono<Void> delete(@PathVariable String id) {
    return bookService.deleteById(id);
}
~~~

**Mono<Void>** completes when the operation finishes successfully. The default HTTP status depends on the mapping/return handling; if you need a specific status such as 204, use **@ResponseStatus** or an appropriate **ResponseEntity**. Do not expect Mono<Void> to emit a body object.

## 11. Error Handling in Controllers

You should not wrap the whole publisher in a synchronous try/catch and assume it will catch errors emitted later. Reactive errors can appear at subscription time and while the publisher is running.

You can handle them at several layers:

- **In the service/pipeline:** use operators such as onErrorMap, onErrorResume when it makes business sense.
- **At the controller:** convert the result to a ResponseEntity if that is the endpoint's decision.
- **@ExceptionHandler:** handle exceptions in the controller/advice.
- **@ControllerAdvice / @RestControllerAdvice:** apply an error-handling policy across multiple controllers.

Example of advice for REST responses:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(BookNotFoundException.class)
    public ResponseEntity<Map<String, String>> notFound(
            BookNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(Map.of("error", exception.getMessage()));
    }
}
~~~

This is a fragment that requires declaring BookNotFoundException and the imports. In a reactive flow, an exception emitted as onError can still be handled by the exception handler mechanism at the web layer. Do not use onErrorResume(error -> Mono.empty()) everywhere just to avoid HTTP 500; doing so can hide errors and turn failures into empty responses that violate the contract.

## 12. Annotated Controllers and Functional Endpoints

WebFlux supports both ways of defining endpoints:

| Approach | Declaration | Strengths |
| --- | --- | --- |
| Annotated controller | @Controller, @RestController, and mapping annotations | Familiar, close to the MVC model, easy to use argument resolvers and annotations |
| Functional endpoint | RouterFunction and HandlerFunction | Declares routes and handlers via the Java API, easy to organize routes by module |

Example of a functional route:

~~~java
@Bean
RouterFunction<ServerResponse> routes(BookHandler handler) {
    return RouterFunctions.route(
        RequestPredicates.GET("/functional/books"),
        handler::findAll);
}
~~~

This is a fragment; **BookHandler** needs to have a method that returns **Mono<ServerResponse>**. A functional endpoint does not need **@RestController** to register a route; the route is created from a RouterFunction bean.

The two models can coexist in one application. Avoid registering the same path/method in both places unless it is intentional, because route resolution can become hard to understand. Choose one consistent style for each module.

## 13. Complete Java 17+ Example with Spring Boot WebFlux

The following example creates a simple REST controller with endpoints to list, find by ID, and create books. The data lives in a fixed list to focus on mapping and response handling; this is a demo, not production persistence.

Project structure:

~~~text
webflux-controller-demo/
├── pom.xml
└── src
    ├── main
    │   └── java
    │       └── com/example/demo
    │           ├── ControllerDemoApplication.java
    │           ├── BookController.java
    │           ├── Book.java
    │           └── CreateBookRequest.java
    └── test
        └── java
            └── com/example/demo
                └── BookControllerTests.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>webflux-controller-demo</artifactId>
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

Spring Boot parent manages compatible versions of Spring Framework, Reactor, and test dependencies. In a real application, prefer Spring Boot's dependency management instead of setting your own reactor-core version.

### ControllerDemoApplication.java

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ControllerDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ControllerDemoApplication.class, args);
    }
}
~~~

### Book.java

~~~java
package com.example.demo;

public record Book(String id, String title) {
}
~~~

### CreateBookRequest.java

~~~java
package com.example.demo;

public record CreateBookRequest(String title) {
}
~~~

### BookController.java

~~~java
package com.example.demo;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/books")
public class BookController {

    private static final List<Book> BOOKS = List.of(
        new Book("1", "Reactive Streams"),
        new Book("2", "Spring WebFlux")
    );

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<Book> findAll() {
        return Flux.fromIterable(BOOKS);
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<Book>> findById(
            @PathVariable("id") String id) {

        return Flux.fromIterable(BOOKS)
            .filter(book -> book.id().equals(id))
            .next()
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public Mono<Book> create(
            @RequestBody Mono<CreateBookRequest> request) {

        return request.map(body ->
            new Book("new-1", body.title()));
    }
}
~~~

Points to note:

- The class is registered because it has **@RestController** and is located in a sub-package of the application class.
- **@RequestMapping("/api/books")** creates a prefix for the methods.
- **@GetMapping** handles GET for the collection; **@GetMapping("/{id}")** handles GET for a single resource.
- **@PathVariable("id")** takes the value from the URL.
- **@RequestBody Mono<CreateBookRequest>** lets WebFlux decode the body into a publisher.
- **@ResponseStatus(CREATED)** sets status 201 for the create method.
- **Mono<ResponseEntity<Book>>** lets you choose 200 or 404 based on the result.
- The controller returns a publisher; it does not call subscribe or block.

### BookControllerTests.java

~~~java
package com.example.demo;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(BookController.class)
class BookControllerTests {

    @Autowired
    private WebTestClient webTestClient;

    @Test
    void getCollectionRegistersAndInvokesHandler() {
        webTestClient.get()
            .uri("/api/books")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$[0].id").isEqualTo("1")
            .jsonPath("$[1].title").isEqualTo("Spring WebFlux");
    }

    @Test
    void missingBookReturnsNotFound() {
        webTestClient.get()
            .uri("/api/books/unknown")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void postMappingReadsBodyAndReturnsCreated() {
        webTestClient.post()
            .uri("/api/books")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("title", "Reactive Controller"))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.id").isEqualTo("new-1")
            .jsonPath("$.title").isEqualTo("Reactive Controller");
    }
}
~~~

Run the tests:

~~~bash
mvn test
~~~

Run the application:

~~~bash
mvn spring-boot:run
~~~

Call the endpoints from another terminal:

~~~bash
curl -i http://localhost:8080/api/books
curl -i http://localhost:8080/api/books/1
curl -i http://localhost:8080/api/books/unknown
curl -i -X POST http://localhost:8080/api/books -H "Content-Type: application/json" -d "{\"title\":\"Reactive Controller\"}"
~~~

The JSON response for the GET collection looks like:

~~~json
[
  {"id":"1","title":"Reactive Streams"},
  {"id":"2","title":"Spring WebFlux"}
]
~~~

The response for GET **/api/books/1** has status 200 and body:

~~~json
{"id":"1","title":"Reactive Streams"}
~~~

GET **/api/books/unknown** returns 404. POST with the sample body returns 201 Created and JSON:

~~~json
{"id":"new-1","title":"Reactive Controller"}
~~~

The ID **new-1** is fixed only for the demo. In a real application, the service/repository must create unique IDs and persist data with appropriate transaction semantics.

The test uses **@WebFluxTest(BookController.class)** to create a test slice for the controller and verify WebFlux mapping, argument binding, and response encoding through WebTestClient. This verifies that the controller is registered and the routes work in the test context; it is not a test of the database or of the entire production deployment.

## 14. Spring Boot Configuration and @EnableWebFlux

For a Spring Boot application using **spring-boot-starter-webflux**, auto-configuration usually already sets up the required WebFlux infrastructure. There is no need to add **@EnableWebFlux** just to make @RestController work.

In an application that configures WebFlux manually, **@EnableWebFlux** can be used to enable the annotated controller infrastructure and WebFlux components. However, when using Spring Boot, adding this annotation can switch the application to a user-controlled WebFlux configuration and affect some auto-configuration. Use it only when you really want to take over the configuration; if you only need custom codecs, CORS, or resource handlers, consider Boot's corresponding configuration mechanism first.

Do not confuse **spring-boot-starter-web** with **spring-boot-starter-webflux**. If both starters are present, Spring Boot may prefer the Spring MVC configuration based on classpath conditions and the application type. Choose the stack deliberately and check the dependency tree when the server does not start up as expected.

## 15. Common Mistakes

1. **Controller class is not scanned:** the controller is outside the scan package or is not registered as a bean. Place the package correctly or configure scan/import.
2. **Using @Controller but expecting a String to be the response body:** the String may be interpreted as a view name. Use @ResponseBody or @RestController for APIs.
3. **Using @RestController for a method that needs to render a view:** @RestController writes the body by default; choose @Controller for view resolution.
4. **Forgetting the class-level prefix:** a method @GetMapping("/{id}") inside a class @RequestMapping("/api/books") creates the route /api/books/{id}, not /{id}.
5. **Confusing @RequestParam and @PathVariable:** a query parameter comes after the question mark; a path variable is part of the URL path.
6. **Missing Content-Type or mismatched consumes:** the request body may not be mapped to the handler or may fail to decode.
7. **produces incompatible with Accept:** the client may receive 406 Not Acceptable.
8. **Two methods with ambiguous mappings:** clarify the path, HTTP method, and params/headers/consumes/produces conditions.
9. **Parsing JSON yourself in the controller:** let HttpMessageReader and codecs handle the body, unless there is a special requirement.
10. **Calling subscribe() in a controller:** creates a subscription outside the HTTP request lifecycle, makes error/cancel handling harder, and can run side effects detached from the response.
11. **Calling block() or blockLast():** can block the event-loop thread and reduce the ability to serve many requests.
12. **Using Flux for an operation with only one result that does not need streaming:** Mono expresses a 0..1 result more clearly.
13. **Returning an infinite Flux with application/json:** the client may wait for a JSON document that never completes. If you need streaming, use SSE or an appropriate streaming media type.
14. **Assuming @ResponseStatus handles every exception automatically:** this annotation sets the status for the handler; errors that occur need appropriate error handling.
15. **Creating mutable fields that hold per-request data:** controller beans are usually used concurrently; do not store request state in shared fields.
16. **Adding an unnecessary @EnableWebFlux in Boot:** it can change auto-configuration. Understand the configuration clearly before enabling it.
17. **Registering the same path in both annotated and functional endpoints:** avoid route conflicts or unpredictable behavior.
18. **Not testing the actual routes:** a method that compiles does not prove that the mapping is registered or that the JSON codec works.

## 16. Controller Design Checklist

Before finishing a controller, check:

- **Bean registration:** is the class within the component scan or declared as a bean?
- **Controller semantics:** do you need a view (@Controller) or a response body (@RestController/@ResponseBody)?
- **Class-level path:** is the prefix clear and consistent?
- **Method mapping:** do the HTTP method and path match the REST contract?
- **Conditions:** are params, headers, consumes, produces really necessary and free of contradictions?
- **Arguments:** does the request data use the right @PathVariable, @RequestParam, @RequestHeader, @RequestBody?
- **Reactive type:** Mono for 0..1, Flux for 0..N; does a streaming body have an appropriate media type?
- **Status and headers:** are 201, 204, 404, and the Location header represented correctly?
- **Error handling:** are exceptions handled at the right layer, not silently swallowed?
- **Threading:** is there no block, sleep, or blocking I/O on the event loop?
- **Lifecycle:** is there no nested subscribe; is the publisher composed and returned to WebFlux?
- **Tests:** does WebTestClient verify the mapping, argument binding, status, and body?
- **Configuration:** do Boot auto-configuration and the starter select the correct WebFlux stack?

## 17. Self-Check Exercises

**Exercise 1.** A class has @Controller and a method that returns a String. Is that string the HTTP body by default?  
**Answer:** No. In a view-based controller, the string can be a view name. To write the body directly, use @ResponseBody or @RestController.

**Exercise 2.** How does @RestController differ from @Controller?  
**Answer:** @RestController combines @Controller and @ResponseBody at the class level, so method results are written to the response body by default.

**Exercise 3.** A class has @RestController but is outside the component scan. Is the handler registered automatically?  
**Answer:** No. The class must be registered as a bean in the ApplicationContext.

**Exercise 4.** The class mapping is /api/books and the method mapping is /{id}. What is the full URL?  
**Answer:** /api/books/{id}.

**Exercise 5.** A client POSTs JSON but the method mapping declares consumes=text/plain. What can happen?  
**Answer:** The request does not satisfy the mapping condition or the body is not decoded as desired. The declared consumes must match the actual Content-Type.

**Exercise 6.** Should you use Mono<Book> or Flux<Book> for an endpoint that finds a single book?  
**Answer:** Mono<Book>, because the result can be empty or contain one book. If you need a 404 status based on the result, use Mono<ResponseEntity<Book>>.

**Exercise 7.** Does a Flux<Event> returned from a controller automatically become SSE?  
**Answer:** No. You need to declare the text/event-stream media type and define appropriate streaming semantics.

**Exercise 8.** Why shouldn't you call subscribe() in a controller?  
**Answer:** The framework needs to manage the subscription tied to the HTTP request, including demand, cancellation, errors, and writing the response. Manual subscribe detaches the work from that lifecycle.

**Exercise 9.** When should you use @EnableWebFlux in Spring Boot?  
**Answer:** Only when you deliberately take over the WebFlux configuration. Boot's WebFlux starter already auto-configures most of the required infrastructure.

**Exercise 10.** What problem can two controllers registering the same GET /api/books/{id} cause?  
**Answer:** The mapping can conflict or become ambiguous. Design clear paths/conditions and keep a single handler owning the route.

## 18. Key Takeaways

**@Controller** declares a web-handling component; **@RestController** adds **@ResponseBody** semantics to all methods in the class. A controller must be managed by Spring as a bean. Class-level and method-level mapping annotations are discovered by **RequestMappingHandlerMapping** to create a HandlerMethod; when a request arrives, **DispatcherHandler** coordinates, **RequestMappingHandlerAdapter** invokes the method, and the result handlers write the body or render the view.

In WebFlux, return **Mono/Flux** so the framework manages the subscription and response lifecycle. Use **@ResponseBody/@RestController** for API bodies, view resolution for pages, mapping conditions that match the HTTP contract, and WebTestClient to verify that routes are registered. Keep controllers thin, non-blocking, free of manual subscribe, and free of per-request state in shared fields.

### References

- Spring Framework, [Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html).
- Spring Framework, [Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html).
- Spring Framework, [Method Arguments](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html).
- Spring Framework, [Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html).
- Spring Framework, [WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html).
- Spring Boot, [Developing Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html).
