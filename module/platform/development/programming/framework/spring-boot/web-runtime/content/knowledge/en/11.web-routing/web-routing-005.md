# RouterFunction, HandlerFunction, and ServerResponse in WebFlux.fn

## 1. What is WebFlux.fn?

Spring WebFlux provides two styles for building HTTP APIs: annotated controllers (@RestController, @GetMapping, ...) and **functional endpoints**, called **WebFlux.fn**. Functional endpoints place routing, handling logic, and response contracts inside Java functions/objects rather than putting HTTP annotations on individual controller methods. Both use the same Spring WebFlux runtime, HTTP codecs, WebFilters, and Project Reactor reactive mechanisms.

The three pillars of WebFlux.fn:

- **RouterFunction<ServerResponse>**: receives a ServerRequest, checks conditions matching the HTTP request, and selects a HandlerFunction; if nothing matches, the routing result is empty.
- **HandlerFunction<ServerResponse>**: receives a ServerRequest and returns a **Mono<ServerResponse>**, typically calling a service/repository and then building an HTTP response.
- **ServerResponse**: describes the status, headers, cookies, media type, and body that Spring WebFlux will send back to the client.

**ServerRequest** is the handler's input object, providing the method, path, headers, query parameters, path variables, request body, and request context.

Goals after this lesson: understand the contract of the three components; design GET/POST REST endpoints; use RequestPredicate, nesting, and filters; distinguish JSON body/Publisher; handle 400/404/201; understand route ordering and duplicate route issues; run Java 17+ / Spring Boot 3.3.x; test with WebTestClient; recognize the block() and subscribe() anti-patterns inside HTTP handlers.

**Scope:** this is WebFlux.fn in package org.springframework.web.reactive.function.server. Spring MVC has a separate functional API in org.springframework.web.servlet.function; do not confuse imports or assume MVC.fn uses Mono<ServerResponse>. Examples target Spring Boot 3.3.x, Java 17+; verify documentation for the matching Spring Boot branch when applying to newer Boot versions.

## 2. Thinking in terms of separating route, handler, and response

For an HTTP request:

~~~http
GET /api/books/12 HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

Overview of steps:

~~~text
HTTP client
   |
   v
HTTP server (typically Reactor Netty)
   |
   v
HttpHandler / WebFilter
   |
   v
DispatcherHandler
   |
   v
RouterFunctionMapping: select HandlerFunction
   |
   v
HandlerFunctionAdapter: invoke handle(ServerRequest)
   |
   v
Mono<ServerResponse>
   |
   v
ServerResponseResultHandler + HTTP codec
   |
   v
HTTP response
~~~

RouterFunctionMapping collects RouterFunction beans, orders/combines them, and finds a matching route. HandlerFunctionAdapter invokes the handler function. ServerResponseResultHandler writes ServerResponse to the HTTP response. When an application uses spring-boot-starter-webflux, Spring Boot sets up this infrastructure; developers only need to register the appropriate router and handlers.

Clean separation of responsibilities: RouterFunction knows **the path**; HandlerFunction knows **how to handle**; ServerResponse knows **how to package the HTTP result**. Data access, transactions, caching, and business logic should reside in separate services/repositories, rather than stuffing everything into a single route lambda.

## 3. The RouterFunction contract

Conceptually, RouterFunction<ServerResponse> has a route method that takes a ServerRequest and returns a publisher containing a HandlerFunction when matched:

~~~java
Mono<HandlerFunction<ServerResponse>> route(ServerRequest request);
~~~

The snippet above only describes the conceptual signature, not a standalone compilable source file. In practice, Spring Framework is typically used via RouterFunctions.route():

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .GET("/api/books", bookHandler::list)
        .GET("/api/books/{id}", bookHandler::get)
        .POST("/api/books", bookHandler::create)
        .build();
~~~

bookHandler is a Bean declared in the complete project below. GET /api/books selects list; GET /api/books/12 selects get; POST /api/books selects create.

For Spring Boot to pick up the router, register it as a @Bean:

~~~java
@Bean
RouterFunction<ServerResponse> bookRouter(BookHandler handler) {
    return RouterFunctions.route()
            .GET("/api/books", handler::list)
            .GET("/api/books/{id}", handler::get)
            .POST("/api/books", handler::create)
            .build();
}
~~~

RouterFunctions.route() returns a builder supporting GET/POST/PUT/PATCH/DELETE and other predicates. You do not need to write a class implementing RouterFunction yourself; the builder is simpler and easier to test.

## 4. The HandlerFunction contract

HandlerFunction<T extends ServerResponse> represents a function taking a ServerRequest and returning Mono<T>:

~~~java
Mono<ServerResponse> handle(ServerRequest request);
~~~

A small handler can be a lambda:

~~~java
request -> ServerResponse.ok().bodyValue("Hello WebFlux.fn")
~~~

Standalone Bean example:

~~~java
@Bean
RouterFunction<ServerResponse> helloRoutes() {
    return RouterFunctions.route()
            .GET("/hello", request -> ServerResponse.ok()
                    .bodyValue("Hello WebFlux.fn"))
            .build();
}
~~~

When calling GET /hello, the handler produces HTTP 200 and a text body. For larger APIs, group logic into a @Component with list, get, create, update, and delete methods instead of writing a single lambda hundreds of lines long.

**Important:** Mono<ServerResponse> does not mean Spring spawns a separate thread per request. It represents a reactive processing pipeline that can complete asynchronously. Do not call subscribe() yourself inside a handler to run background work and immediately return HTTP 200, because doing so detaches execution, errors, and cancellation from the HTTP request lifecycle.

## 5. ServerRequest and input data

Commonly used APIs:

| Data | WebFlux.fn API | Notes |
| --- | --- | --- |
| Path variable | request.pathVariable("id") | String, needs parsing/validation |
| Query | request.queryParam("page") | Optional<String> |
| Header | request.headers().firstHeader("X-Request-ID") | May be null |
| HTTP method | request.method() | HttpMethod |
| URI | request.uri() | URI containing path and query |
| Single object JSON body | request.bodyToMono(CreateBookRequest.class) | Requires JSON codec, Content-Type |
| Multiple objects/body stream | request.bodyToFlux(Event.class) | Manage buffering/backpressure |
| Session | request.session() | Mono<WebSession> |
| Principal | request.principal() | Mono<Principal> |
| Lower-level exchange | request.exchange() | ServerWebExchange |

Example reading a path variable:

~~~java
long id;
try {
    id = Long.parseLong(request.pathVariable("id"));
} catch (NumberFormatException ex) {
    return ServerResponse.badRequest()
            .bodyValue(Map.of("error", "id must be numeric"));
}
~~~

The snippet is placed inside a handler returning Mono<ServerResponse>. It requires importing Map and having a request variable of type ServerRequest. If id must be positive, check id > 0. Do not assume that a URL with an {id} placeholder guarantees a valid id.

When a request has a body, use bodyToMono/bodyToFlux appropriately. Do not call bodyToMono(...).block() inside a request handler; use flatMap to chain asynchronous steps.

## 6. ServerResponse: status, headers, and body

Common factories:

~~~java
ServerResponse.ok().bodyValue(Map.of("status", "ok"));

ServerResponse.created(URI.create("/api/books/13"))
        .bodyValue(new Book(13, "WebFlux"));

ServerResponse.noContent().build();

ServerResponse.notFound().build();

ServerResponse.badRequest()
        .bodyValue(Map.of("error", "invalid input"));

ServerResponse.status(HttpStatus.CONFLICT)
        .bodyValue(Map.of("error", "duplicate"));
~~~

These are standalone illustrative expressions, not a complete main method. Appropriate imports are required. bodyValue(...) and build() return Mono<ServerResponse>; when the handler returns this Publisher, the framework manages writing the HTTP response.

For JSON:

~~~java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("message", "hello"));
~~~

For a Publisher:

~~~java
Flux<Book> books = store.findAll();

return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(books, Book.class);
~~~

Use **bodyValue** for an already available object. Use **body(Publisher, element type)** when the response body is emitted from a Flux/Mono; avoid passing a Publisher into bodyValue and expecting the framework to treat it as a reactive source in every case.

HTTP 201 should include Location when the new resource has a URL. HTTP 204 has no response body. 404 is used when a resource ID is valid yet does not exist; 400 is used when input is malformed. Express statuses intentionally instead of always returning 200.

## 7. RequestPredicates: matching method, path, header, and media type

The builder offers GET/POST shortcuts, while RequestPredicates provides additional conditions such as accept, contentType, queryParam, headers, and path. Predicates can be combined with and/or/negate.

Example matching GET only when the client accepts text/plain:

~~~java
RouterFunctions.route()
        .GET("/hello",
                RequestPredicates.accept(MediaType.TEXT_PLAIN),
                request -> ServerResponse.ok()
                        .contentType(MediaType.TEXT_PLAIN)
                        .bodyValue("hello"))
        .build();
~~~

**Distinguishing Accept and Content-Type:**

- Accept: which response format the client wants to receive.
- Content-Type: which body format the client is sending in the request.

If a RequestPredicate fails to match, the router may select no handler and the request returns 404 when no other route matches. Thus, adding accept(...) or contentType(...) to a route can change the outcome from 406/415 to 404 in certain combinations. If the API contract requires 406/415 error codes, test media negotiation and design error handling explicitly rather than inferring solely from predicates.

Do not attach extra predicates out of habit. A GET without a body does not need a Content-Type predicate. For JSON POSTs, you can let the router match by method/path and let the body reader/codec handle supported media types.

## 8. Route order and overlapping routes

WebFlux.fn evaluates RouterFunction entries in order; the first matching route is selected. This differs from annotated controllers, where HandlerMapping applies a mapping specificity algorithm.

Risky example:

~~~java
RouterFunctions.route()
        .GET("/api/books/{id}", handler::get)
        .GET("/api/books/search", handler::search)
        .build();
~~~

GET /api/books/search can be matched by /{id} first, causing handler get to attempt parsing "search" as a number and return 400. Better:

~~~java
RouterFunctions.route()
        .GET("/api/books/search", handler::search)
        .GET("/api/books/{id}", handler::get)
        .build();
~~~

These are two illustrative route snippets assuming handler::search exists in an extended module. The sample project below does not register a /search route. The rule is to place specific/overlapping-prefix routes before general or catch-all routes.

When multiple RouterFunction beans exist, Spring discovers, orders, and composes them. Define explicit ordering with @Order/Ordered when truly needed, and avoid overlaps so you do not depend on an order that breaks easily during refactoring. Test all special routes, ID routes, and fallback routes.

## 9. Composing and nesting routes

RouterFunctions can be composed with and(...) or Builder.add(otherRouter). Example:

~~~java
RouterFunction<ServerResponse> routes =
        booksRoutes.and(healthRoutes);
~~~

booksRoutes and healthRoutes are two routers created elsewhere. The left-hand router is evaluated first under composition.

To share a prefix:

~~~java
@Bean
RouterFunction<ServerResponse> nestedBookRouter(
        BookHandler handler) {
    return RouterFunctions.route()
            .path("/api/books", nested -> nested
                    .GET("/{id}", handler::get)
                    .GET(handler::list)
                    .POST(handler::create))
            .build();
}
~~~

This is an **alternative** to BookRoutes in the complete project; do not declare both routers with the same paths/methods in one app. Builder.path groups routes under a shared prefix. You can use Builder.nest to apply a shared predicate like Accept to a group of GETs without affecting POSTs or routes outside the group.

Nested routes improve readability for large API groups. However, overly deep nesting makes predicate/filter scope hard to trace and can cause unintended 404s. Keep structures reasonably simple and test with different headers.

## 10. Reading JSON with bodyToMono and flatMap

For request:

~~~http
POST /api/books HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{"title":"Reactive Java"}
~~~

The handler can read the body and then create a book:

~~~java
return request.bodyToMono(CreateBookRequest.class)
        .flatMap(input -> store.insert(input.title())
                .flatMap(book -> ServerResponse
                        .created(URI.create(
                                "/api/books/" + book.id()))
                        .bodyValue(book)));
~~~

This illustrative snippet requires request/store/DTO and lacks validation. The complete version in section 12 handles null/blank titles and empty bodies.

Do not use map() when the lambda itself returns Mono<ServerResponse>, as that produces Mono<Mono<ServerResponse>>. Use flatMap to flatten the Publisher. If bodyToMono returns Mono.empty() due to a missing body, use switchIfEmpty(...) to produce a 400 response. If body parsing emits an error, handle errors appropriately by type; do not turn every database exception into 400.

**Do not call subscribe() manually** to save records, because the HTTP response may complete before the actual operation finishes, losing cancellation control and error propagation.

## 11. Spring Boot Java 17+ project layout

The following example uses **Spring Boot 3.3.0 + Java 17+**, Gradle Groovy DSL, the WebFlux starter, and the default embedded Reactor Netty. It is a simple book management API needing no database. Data lives only in a ConcurrentHashMap and is lost on restart.

Structure:

~~~text
webflux-fn-books/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/fn/
        BookApiApplication.java
        Book.java
        CreateBookRequest.java
        BookStore.java
        BookHandler.java
        BookRoutes.java
      resources/
        application.yml
    test/
      java/example/fn/
        BookApiApplicationTests.java
~~~

Every public class/record must reside in a file of the same name. Requires JDK 17+, a Gradle Wrapper compatible with Spring Boot 3.3, and access to Maven Central.

### 11.1. settings.gradle

~~~groovy
rootProject.name = 'webflux-fn-books'
~~~

### 11.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Do not add spring-boot-starter-web because Spring Boot normally prefers MVC when both MVC and WebFlux starters coexist. If a real project already has dependency management, follow the project's version set rather than copying plugin versions from a sample article.

### 11.3. application.yml

~~~yaml
spring:
  application:
    name: webflux-fn-books

server:
  port: 8080
~~~

To run on a different port: java -jar ... --server.port=9090 or pass SERVER_PORT via environment configuration.

### 11.4. BookApiApplication.java

~~~java
package example.fn;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BookApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(BookApiApplication.class, args);
    }
}
~~~

### 11.5. Book.java

~~~java
package example.fn;

public record Book(long id, String title) {
}
~~~

### 11.6. CreateBookRequest.java

~~~java
package example.fn;

public record CreateBookRequest(String title) {
}
~~~

Standard Jackson in the WebFlux starter can deserialize JSON into the CreateBookRequest record and serialize Book records back to JSON.

### 11.7. BookStore.java

~~~java
package example.fn;

import java.util.Comparator;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Repository;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Repository
public class BookStore {

    private final ConcurrentMap<Long, Book> books =
            new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong();

    public Flux<Book> findAll() {
        return Flux.defer(() ->
                Flux.fromIterable(books.values())
                        .sort(Comparator.comparingLong(Book::id)));
    }

    public Mono<Book> findById(long id) {
        return Mono.defer(() ->
                Mono.justOrEmpty(books.get(id)));
    }

    public Mono<Book> insert(String title) {
        return Mono.fromSupplier(() -> {
            long id = sequence.incrementAndGet();
            Book book = new Book(id, title);
            books.put(id, book);
            return book;
        });
    }
}
~~~

AtomicLong issues concurrent IDs within one JVM. ConcurrentHashMap is safer than HashMap under concurrent requests yet provides no transactions/durability. Flux.defer/Mono.defer defers execution until subscription. sort collects items before emitting, so it is **not suitable for large datasets**. This in-memory demo does not prove that wrapping JDBC in Mono makes it non-blocking.

### 11.8. BookHandler.java

~~~java
package example.fn;

import java.net.URI;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Mono;

@Component
public class BookHandler {

    private final BookStore store;

    public BookHandler(BookStore store) {
        this.store = store;
    }

    public Mono<ServerResponse> list(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(store.findAll(), Book.class);
    }

    public Mono<ServerResponse> get(ServerRequest request) {
        long id;

        try {
            id = Long.parseLong(request.pathVariable("id"));
        } catch (NumberFormatException exception) {
            return ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(Map.of(
                            "error", "id must be an integer"));
        }

        if (id <= 0) {
            return ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(Map.of(
                            "error", "id must be positive"));
        }

        return store.findById(id)
                .flatMap(book -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(book))
                .switchIfEmpty(ServerResponse.notFound().build());
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateBookRequest.class)
                .flatMap(input -> {
                    String title = input.title();

                    if (title == null || title.isBlank()) {
                        return ServerResponse.badRequest()
                                .contentType(
                                        MediaType.APPLICATION_JSON)
                                .bodyValue(Map.of(
                                        "error", "title is required"));
                    }

                    return store.insert(title.trim())
                            .flatMap(book -> ServerResponse
                                    .created(URI.create(
                                            "/api/books/" + book.id()))
                                    .contentType(
                                            MediaType.APPLICATION_JSON)
                                    .bodyValue(book));
                })
                .switchIfEmpty(ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(Map.of(
                                "error", "JSON body is required")));
    }
}
~~~

Explanation: list returns a Publisher of books; get distinguishes 400 for invalid id from 404 for missing book; create decodes JSON, validates title, persists via Publisher, and returns 201 with Location. When malformed JSON arrives, the WebFlux codec may emit an exception; consistent error handling is needed in production applications.

### 11.9. BookRoutes.java

~~~java
package example.fn;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class BookRoutes {

    @Bean
    RouterFunction<ServerResponse> bookRouter(BookHandler handler) {
        return RouterFunctions.route()
                .GET("/api/books", handler::list)
                .GET("/api/books/{id}", handler::get)
                .POST("/api/books", handler::create)
                .build();
    }
}
~~~

This is the entire route configuration; no @RestController is needed for the endpoints in this example. Spring Boot scans package example.fn, creates BookHandler/BookStore, and registers the RouterFunction bean.

## 12. Running the application and observing HTTP responses

On Linux/macOS:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

After the server starts successfully on port 8080, run in another terminal:

~~~bash
curl -i http://localhost:8080/api/books
~~~

Expected HTTP 200 and empty JSON when the application has just started:

~~~json
[]
~~~

Create a book:

~~~bash
curl -i -X POST http://localhost:8080/api/books -H "Content-Type: application/json" -d '{"title":"Reactive Java"}'
~~~

If this is the first book-creation request, expect HTTP 201 Created, Location=/api/books/1, JSON body:

~~~json
{"id":1,"title":"Reactive Java"}
~~~

After creating book id=1:

~~~bash
curl -i http://localhost:8080/api/books/1
~~~

Expected HTTP 200 and JSON of book id=1. For a non-existent id:

~~~bash
curl -i http://localhost:8080/api/books/999999
~~~

Expected HTTP 404. For an unparseable id:

~~~bash
curl -i http://localhost:8080/api/books/not-an-id
~~~

Expected HTTP 400 with the corresponding error. For a blank title:

~~~bash
curl -i -X POST http://localhost:8080/api/books -H "Content-Type: application/json" -d '{"title":" "}'
~~~

Expected HTTP 400 with error title is required.

These example responses describe the **expected state after successful execution**, not observed output from your local machine. The id number may differ if multiple book-creation requests have been sent.

## 13. WebTestClient: testing routes and responses

File src/test/java/example/fn/BookApiApplicationTests.java:

~~~java
package example.fn;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BookApiApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void createAndRead() {
        Book created = client.post()
                .uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateBookRequest("  Reactive Java  "))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().exists("Location")
                .expectBody(Book.class)
                .returnResult()
                .getResponseBody();

        assertNotNull(created);
        assertEquals("Reactive Java", created.title());

        client.get()
                .uri("/api/books/" + created.id())
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title").isEqualTo("Reactive Java");
    }

    @Test
    void invalidIdIsBadRequest() {
        client.get()
                .uri("/api/books/no-number")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void unknownBookIsNotFound() {
        client.get()
                .uri("/api/books/999999")
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void blankTitleIsBadRequest() {
        client.post()
                .uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateBookRequest(" "))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error")
                .isEqualTo("title is required");
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

@SpringBootTest(RANDOM_PORT) starts a real HTTP server on a random port; @AutoConfigureWebTestClient creates a client capable of sending requests to that server in Spring Boot 3.3's integration configuration. Testing routes/handlers directly differs from network integration testing. If multiple tests in the same project share an in-memory singleton BookStore, do not assume id starts at 1 in every test; use the id returned from the response as shown in the example.

### WebTestClient usage modes

- bindToRouterFunction(router): tests RouterFunction and handlers on test infrastructure without opening a TCP port.
- bindToApplicationContext(context): tests the WebFlux ApplicationContext without necessarily opening a port.
- bindToServer().baseUrl(...): sends requests to a running HTTP server.
- @SpringBootTest(RANDOM_PORT) + WebTestClient: integrates a real server inside Spring Boot tests.

Pick the level matching your risk: unit/contract tests run fast, while integration tests verify the HTTP adapter and codecs too. Tests calling BookHandler.get directly with a mock ServerRequest are not sufficient to prove router matching and HTTP mapping.

## 14. Functional filters and WebFilter

A HandlerFilterFunction takes a ServerRequest, the next HandlerFunction, and returns Mono<ServerResponse>. You can use builder.filter(...) to apply shared rules to **the functional routes belonging to that builder**.

Example checking a lab-environment header:

~~~java
RouterFunction<ServerResponse> demo =
        RouterFunctions.route()
                .GET("/internal-demo", request ->
                        ServerResponse.ok().bodyValue("ok"))
                .filter((request, next) -> {
                    String mode = request.headers()
                            .firstHeader("X-Lab-Mode");
                    if (!"on".equals(mode)) {
                        return ServerResponse.badRequest()
                                .bodyValue(Map.of(
                                        "error", "X-Lab-Mode must be on"));
                    }
                    return next.handle(request);
                })
                .build();
~~~

This is a separate snippet, not part of the main sample project. It requires importing Map and WebFlux.fn classes. A filter can short-circuit and prevent invoking the handler when conditions are unmet.

**Scope distinction:**

- HandlerFilterFunction: the functional route or route group attached to that filter.
- WebFilter: cross-cutting for the WebFlux request chain, applicable to both functional and annotated endpoints.
- Servlet Filter: Servlet API, not the default middleware choice of WebFlux.
- SecurityWebFilterChain: Spring Security's reactive authentication/authorization policies.

Do not use X-Lab-Mode or any client-sent header as real authentication. For multi-tenant systems or APIs with sensitive data, use verified principals/claims and proper security rules.

### before, after, and filter

The builder supports before(request -> newRequest), after((request,response) -> newResponse), and filter((request,next) -> Mono<ServerResponse>) within the relevant route scope. Because ServerRequest/ServerResponse have immutable contracts, use builder/copy APIs to produce modified variants rather than assuming created objects can be mutated in place.

A filter inside a nested route group does not automatically apply to routes outside that group. Test requests outside the scope as well to avoid accidentally applying it too broadly.

## 15. Error handling and validation

A solid HTTP contract must distinguish:

| Scenario | Common status | Where handled |
| --- | --- | --- |
| Malformed id | 400 | Handler parse/validation |
| Malformed JSON syntax | 400 | Request body decoder/error handler |
| Required field blank | 400 | Validator or handler |
| Resource does not exist | 404 | switchIfEmpty(notFound) |
| Duplicate resource | 409 | Business validation |
| Unauthenticated | 401 | Reactive Spring Security |
| Insufficient permissions | 403 | Authorization |
| Unsupported Content-Type | 415 | Codec/media type |
| Cannot produce representation for Accept | 406 | Content negotiation |
| Real backend failure | 5xx | Error handler and logging |

In functional handlers, merely calling bodyToMono without invoking a Validator does not automatically apply @Valid annotations on a DTO. You can inject a Spring Validator/Bean Validation instance or validate explicitly before calling the repository. On validation failure, return a consistently structured error response; never let stack traces, SQL, credentials, or secret values leak to clients.

Do not use onErrorResume(error -> badRequest()) to mask all backend failures as 400. Distinguish input exceptions from system exceptions; unexpected errors must be properly logged/traced and return 5xx without leaking sensitive info.

## 16. Reactive request lifecycle and anti-patterns

Proper code typically **returns the reactive pipeline**:

~~~java
return store.findById(id)
        .flatMap(book -> ServerResponse.ok().bodyValue(book))
        .switchIfEmpty(ServerResponse.notFound().build());
~~~

Incorrect code regarding lifecycle management:

~~~java
store.insert(title).subscribe(); // execution detached from HTTP response
Book book = store.findById(id).block(); // blocks the request thread
~~~

These two lines only illustrate anti-patterns, not standalone source. Manual subscribe can cause the response to be sent before insertion completes, prevent errors from translating into HTTP statuses, and lose cancellation handling. Calling block() on a non-blocking thread may be forbidden or stall the event loop.

If you are forced to call a blocking API, you can offload the work in a bounded way:

~~~java
Mono<Book> result = Mono.fromCallable(
        () -> blockingGateway.load(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

This snippet assumes a blockingGateway dependency and requires importing Reactor Mono/Schedulers. boundedElastic has finite resources; offloading does not make JDBC or synchronous SDKs non-blocking. When much of the business logic is inherently blocking, Spring MVC may be simpler than WebFlux.

## 17. Streaming, codecs, and backpressure

ServerResponse.body(Flux, Class) lets the HTTP writer encode elements from a Publisher, yet **not every Flux streams in constant memory**. For example, BookStore.findAll uses sort, meaning it must collect items to sort them. Many codecs may buffer or encode as a JSON array; proxies may also buffer responses before clients see them.

SSE example inside a handler:

~~~java
Flux<ServerSentEvent<String>> events =
        Flux.interval(Duration.ofSeconds(1))
                .take(3)
                .map(index -> ServerSentEvent.<String>builder()
                        .data("tick-" + index)
                        .build());

return ServerResponse.ok()
        .contentType(MediaType.TEXT_EVENT_STREAM)
        .body(events,
                new ParameterizedTypeReference<
                        ServerSentEvent<String>>() {});
~~~

This snippet requires importing Duration, Flux, ServerSentEvent, MediaType, and ParameterizedTypeReference; it is not part of the complete CRUD project. An SSE-capable client is expected to receive three data events tick-0, tick-1, tick-2 and then see the stream close.

In real deployments, test cancellation, slow clients, memory, backpressure, proxy buffering, timeouts, and body limits. Do not treat Publisher as a guarantee that every database, HTTP server, and reverse proxy layer is non-blocking.

## 18. WebFlux.fn and annotated WebFlux can coexist

Yes. Spring WebFlux supports both RouterFunction beans and @RestController annotated handlers on the same reactive runtime. However, avoid having the same method/path appear in both styles unintentionally; routing conflicts are hard to maintain.

Do not confuse this with the **starter-web + starter-webflux** situation: when both starters are present, Spring Boot typically picks the MVC web application type; returning Mono in an MVC controller does not prove the HTTP app is running WebFlux. To deploy functional WebFlux, keep the classpath clean and verify a reactive ApplicationContext.

A WebFlux.fn route-level filter does not automatically cover @RestController; to apply cross-cutting logic across all WebFlux requests, consider WebFilter or reactive Spring Security. Endpoint ownership should be clearly defined so routes are not shadowed by catch-alls.

## 19. WebFlux.fn differs from Spring MVC.fn

Class names are similar, yet **packages differ**:

| Feature | WebFlux.fn | Spring MVC.fn |
| --- | --- | --- |
| RouterFunction package | org.springframework.web.reactive.function.server | org.springframework.web.servlet.function |
| HandlerFunction return | Mono<ServerResponse> | ServerResponse |
| Request model | Reactive ServerRequest | Servlet ServerRequest |
| Response handling | Reactive HTTP codecs | Servlet message conversion |
| Common default server | Reactor Netty | Tomcat |
| Cross-cutting web API | WebFilter | Servlet Filter |

If your IDE accidentally imports ServerResponse from org.springframework.web.servlet.function, generic RouterFunction and body handling will be incompatible with WebFlux.fn. Verify that RouterFunction, ServerRequest, HandlerFunction, and ServerResponse all come from web.reactive.function.server.

## 20. When to use WebFlux.fn instead of annotations?

WebFlux.fn fits when a team wants to:

- Declare routes and predicates explicitly in one place.
- Use modular routers per domain/module.
- Easily compose/nest routes and apply route-level filters by group.
- Separate HandlerFunction classes from route configuration.
- Use Java functions/lambdas for concise endpoints.

Annotated controllers have advantages in familiarity, method-level annotations, binding, and common validation. There is no universal rule that functional routes are faster or safer across every workload. Both still rely on the same reactive HTTP runtime, codecs, data layer, and security.

Choose based on your project's maintainability and testability standards; avoid changing architecture just to save a few lines of syntax.

## 21. Troubleshooting checklist

| Symptom | Likely cause to check |
| --- | --- |
| Router does not work | @Bean/@Configuration not scanned, wrong package |
| GET /search returns 400 | /{id} matched before /search |
| POST body with another media type returns 404 | contentType predicate did not match |
| POST returns 415 | Codec cannot read Content-Type |
| Response returns 406 | No representation matches Accept |
| Cannot read pathVariable | {id} name in path differs from key read |
| Handler returns Mono<Mono<ServerResponse>> | Used map instead of flatMap |
| API responds before saving | Manual subscribe instead of returning the chain |
| Unexpected empty response body | Mono.empty missing switchIfEmpty |
| 500 on invalid input | Unhandled parse exception/missing validation |
| Route filter not applied app-wide | Filter attached only to RouterFunction |
| After adding MVC starter, WebFlux routes stop running | Spring Boot selected Servlet MVC |
| Performance degrades | Blocking on event loop, data access bottleneck |
| Unit tests pass but deploy fails | Missing real HTTP/port test |
| JSON serialization differs | Codec/Jackson config or schema changed |

Investigation steps: confirm the actual runtime stack; inspect dependencies and RouterFunction beans; compare paths/methods/predicates; check route precedence; examine HTTP statuses and error logs; reproduce with WebTestClient; verify serializers and security; and only then tune server settings.

## 22. Advanced practice exercises

1. **Specific route:** add GET /api/books/search, placed before /api/books/{id}, using queryParam("q") to filter titles. Test route precedence.
2. **Nesting:** refactor BookRoutes to builder.path("/api/books", ...); do not register duplicate routers. Verify GET/POST still work.
3. **Validation:** add author or price to CreateBookRequest, apply an appropriate Validator, and return a structured 400 error.
4. **Route filter:** add a filter for the /internal-demo group and verify routes outside the group are unaffected; do not use lab headers for authentication.
5. **JSON errors:** send malformed syntax, wrong media type, and empty body; verify statuses and ensure no stack traces leak.
6. **Streaming:** add an SSE route emitting three events; test stream cancellation, proxy buffering, and memory.
7. **Database:** replace BookStore with an appropriate reactive repository, keeping Mono/Flux contracts; evaluate slow requests and backpressure.
8. **Security:** configure reactive Spring Security for POST, test 401/403; protect both functional and annotated routes.
9. **Deployment:** run the JAR on a different port, verify graceful shutdown and health/readiness probes.

Proof of completion: source code, passing Gradle tests, curl requests/responses, documented route matching and error cases. Do not fabricate latency or throughput numbers; if benchmarking, fix JDK, CPU, memory, dataset, and load level, and measure multiple runs.

## 23. Self-check questions

1. What two distinct roles do RouterFunction and HandlerFunction perform?
2. Why does HandlerFunction return Mono<ServerResponse>?
3. How does ServerRequest differ from HttpServletRequest?
4. What do RouterFunctionMapping, HandlerFunctionAdapter, and ServerResponseResultHandler do?
5. Why should static routes be placed before /{id}?
6. How does RequestPredicates.accept differ from RequestPredicates.contentType?
7. Why can an unmatched predicate cause a 404?
8. When do you use ServerResponse.bodyValue vs. body(Publisher, Class)?
9. What response should a repository Mono.empty() lead to when looking up by ID?
10. Why should you never call block() or subscribe() inside a handler?
11. Does HandlerFilterFunction cover all annotated WebFlux controllers?
12. How does WebFilter differ from Servlet Filter and route filters?
13. When does @Valid on a DTO require explicit validation inside functional handlers?
14. How do Spring WebFlux.fn and Spring MVC.fn differ in packages and return types?
15. Does WebTestClient.bindToRouterFunction open a real TCP port?
16. How do you test against a real embedded server using RANDOM_PORT?
17. Should you include both Spring MVC and WebFlux starters just to get WebClient?
18. Why does Flux not guarantee zero full-response buffering?
19. In which cases should you return 400, 404, 409, 415, or 500?
20. When do nested routes or composed RouterFunctions make code easier to maintain?

## 24. Official references

- [Spring Framework — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): routes, handlers, ServerRequest, ServerResponse, predicates, nesting, filters.
- [Spring Framework — WebFlux DispatcherHandler](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html): RouterFunctionMapping, handler invocation, and result handling.
- [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): WebFlux integration.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): WebTestClient, @SpringBootTest, and test slices.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): bindToRouterFunction/bindToServer.
- [Project Reactor](https://projectreactor.io/docs/core/release/reference/): Mono, Flux, flatMap, error handling, and schedulers.

**Conclusion:** RouterFunction selects the right HTTP handler based on predicates and order; HandlerFunction builds a reactive chain from ServerRequest; ServerResponse defines the HTTP status, headers, and body. Keeping these three boundaries clear makes WebFlux.fn easy to organize for large route sets and straightforward to test with WebTestClient, while still requiring proper validation, security, codecs, and non-blocking execution.
