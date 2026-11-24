# @RequestMapping and the HTTP-Method-Specific Annotations

In **Spring WebFlux**, a controller uses annotations to declare which URL is handled by which Java method. `@RequestMapping` is the general-purpose annotation: it can match on **path, HTTP method, query parameter, request header, and media type**. The specialized annotations such as `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping`, and `@DeleteMapping` are shorthand forms that declare an endpoint for a specific HTTP method.

A controller usually puts `@RequestMapping` at the class level to define the shared part of the URL, then uses an HTTP-method annotation on each method. This keeps the API contract clear and prevents a handler from accidentally accepting HTTP methods it does not support.

## 1. Learning Objectives

After this lesson, you can:

1. Explain the role of `@RequestMapping` at the class level and the method level.
2. Choose the right one of `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping`, or `@DeleteMapping`.
3. Combine path, `@PathVariable`, `@RequestParam`, and the `params` and `headers` conditions.
4. Use `consumes` to restrict the request content type and `produces` to declare the response type.
5. Understand how Spring WebFlux selects a handler when there are multiple mappings and recognize mapping conflicts.
6. Write a reactive controller that returns `Mono`/`Flux` and receives the body as `Mono<T>`.
7. Test mappings with `WebTestClient` and verify the method, path, status, headers, and media type.
8. Distinguish HTTP behaviors such as GET, POST, PUT, PATCH, DELETE, HEAD, and OPTIONS in endpoint design.

## 2. What Is `@RequestMapping`?

`@RequestMapping` marks a controller or controller method so that Spring can map an HTTP request to the corresponding handler.

It supports these commonly used attributes:

| Attribute | Purpose |
| --- | --- |
| `path` / `value` | One or more URI path patterns. These two attributes are aliases of each other. |
| `method` | Restricts by HTTP method, using the `RequestMethod` enum. |
| `params` | A condition based on query parameters: present, absent, or equal/not equal to a value. |
| `headers` | A condition based on request headers. |
| `consumes` | Restricts the media type of the request body, usually matched against `Content-Type`. |
| `produces` | Declares the media type the handler can return, usually matched against `Accept`. |
| `name` | An identifying name for the mapping, useful in some mapping-management scenarios. |

General example:

~~~java
@RequestMapping(
    path = "/api/products",
    method = RequestMethod.GET,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public Flux<Product> listProducts() {
    // ...
}
~~~

Here the handler accepts only GET for the declared path and represents the response as JSON. Because most endpoints serve only one specific HTTP method, Spring provides specialized shorthand annotations to make the code more readable.

**Important note:** if `@RequestMapping` does not declare `method`, it can by default match all HTTP methods. For regular APIs, prefer `@GetMapping`, `@PostMapping`, and so on, to avoid accidentally exposing an endpoint to unwanted methods.

## 3. Mapping at the Class Level and the Method Level

A common way to organize them:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    @GetMapping
    public Flux<Product> list() {
        // GET /api/products
    }

    @GetMapping("/{id}")
    public Mono<Product> find(@PathVariable("id") String id) {
        // GET /api/products/{id}
    }

    @PostMapping
    public Mono<Product> create(@RequestBody Mono<CreateProduct> body) {
        // POST /api/products
    }
}
~~~

This is a **controller illustration snippet**; you need to declare the `Product` and `CreateProduct` types and the corresponding handling in the application. The path-combining rules:

- The class-level mapping `/api/products` is the shared part.
- `@GetMapping("/{id}")` adds the `/{id}` part.
- The final endpoint is `GET /api/products/{id}`.
- `@PostMapping` has no additional path, so it uses the class-level path exactly: `POST /api/products`.

You can also place a URI variable at the class level:

~~~java
@RestController
@RequestMapping("/tenants/{tenantId}/products")
class TenantProductController {

    @GetMapping("/{productId}")
    Mono<Product> get(
            @PathVariable("tenantId") String tenantId,
            @PathVariable("productId") String productId) {
        // ...
    }
}
~~~

Both `tenantId` and `productId` are taken from the URI. Spring performs type conversion for simple types such as `long`, `int`, `UUID`, or types with a suitable converter; if conversion fails, the request cannot be bound as desired and goes through the corresponding error-handling mechanism.

**Put the shared path on the class, and the specific method/path on the method.** Avoid repeating the prefix on every method, and do not create overly broad mappings such as `/**` if the controller manages only one group of resources.

## 4. Annotations by HTTP Method

The specialized annotations are composed annotations built on `@RequestMapping`:

| Annotation | HTTP method | Typical use |
| --- | --- | --- |
| `@GetMapping` | GET | Read a resource or query data. |
| `@PostMapping` | POST | Create a resource or perform an action that is not modeled by another method. |
| `@PutMapping` | PUT | Replace the entire representation of a resource at a known URI. |
| `@PatchMapping` | PATCH | Partially update a resource. |
| `@DeleteMapping` | DELETE | Request deletion of the resource at the URI. |

Example:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping
    Flux<OrderView> list() {
        // GET /api/orders
    }

    @GetMapping("/{id}")
    Mono<OrderView> get(@PathVariable("id") String id) {
        // GET /api/orders/{id}
    }

    @PostMapping
    Mono<OrderView> create(@RequestBody Mono<CreateOrder> body) {
        // POST /api/orders
    }

    @PutMapping("/{id}")
    Mono<OrderView> replace(
            @PathVariable("id") String id,
            @RequestBody Mono<ReplaceOrder> body) {
        // PUT /api/orders/{id}
    }

    @PatchMapping("/{id}")
    Mono<OrderView> patch(
            @PathVariable("id") String id,
            @RequestBody Mono<PatchOrder> body) {
        // PATCH /api/orders/{id}
    }

    @DeleteMapping("/{id}")
    Mono<Void> delete(@PathVariable("id") String id) {
        // DELETE /api/orders/{id}
    }
}
~~~

This is an **illustrative skeleton**, not a standalone runnable Java program. The request/response types and the business logic need to be implemented.

### 4.1. HTTP Semantics the API Should Reflect

- **GET**: reads a resource and should not create business side effects. GET is defined as *safe* and *idempotent* by HTTP semantics.
- **POST**: usually creates a subordinate resource or performs an action; it is not idempotent by default. If a client retries after a timeout, the server may have already created the record before the connection dropped.
- **PUT**: replaces the representation at the target URI. PUT is defined as idempotent in terms of its intended effect; sending the same request multiple times should not create additional distinct records.
- **PATCH**: applies a partial change; idempotency depends on the patch content and the API contract.
- **DELETE**: requests deletion of a resource. DELETE is defined as idempotent in effect, even though the response of the first and later calls may differ (for example 204 and then 404).

Do not just swap annotations without considering semantics. For example, updating a status field may be a PATCH; replacing the entire representation usually fits PUT. If POST creates a resource, the response usually returns 201 Created and may include a `Location` header pointing to the new resource.

### 4.2. HEAD and OPTIONS

Spring WebFlux supports HEAD through the GET mapping for request-mapping purposes; the application does not necessarily need to create a separate HEAD handler in the usual case. The server adapter handles the HEAD response so that it does not send a response body like GET.

By default, OPTIONS can be handled by Spring with an `Allow` header listing the HTTP methods supported for the corresponding path. Declare a separate OPTIONS handler only when the application needs custom behavior. CORS preflight also uses OPTIONS but requires appropriate CORS configuration; do not confuse having an OPTIONS handler with having configured CORS.

## 5. Path Patterns, PathVariable, and RequestParam

### 5.1. URI Path Patterns

Spring WebFlux uses `PathPattern` to match URIs. Commonly used forms:

| Pattern | Meaning | Example |
| --- | --- | --- |
| `/products` | Fixed path | `/products` |
| `/products/{id}` | A named segment | `/products/p-10` |
| `/files/*` | Wildcard within one segment | `/files/a.txt` |
| `/files/**` | Multiple segments at the end of the pattern | `/files/images/a.png` |
| `/{id:\d+}` | A segment with a regex constraint | `/123` |

Example of capturing a path variable:

~~~java
@GetMapping("/orders/{orderId}/items/{itemId}")
Mono<ItemView> getItem(
        @PathVariable("orderId") String orderId,
        @PathVariable("itemId") String itemId) {
    // ...
}
~~~

Naming explicitly in the annotation keeps the code from depending on the compiler retaining parameter names via `-parameters`. If the parameter name and the URI variable name are the same, you can shorten `@PathVariable`, but explicit declaration is usually easier to read when the project has many modules.

### 5.2. Query Parameters

`@RequestParam` takes values from the query string or from supported form parameters:

~~~java
@GetMapping("/search")
Flux<Product> search(
        @RequestParam(name = "q") String keyword,
        @RequestParam(name = "page", defaultValue = "0") int page,
        @RequestParam(name = "size", defaultValue = "20") int size) {
    // ...
}
~~~

Example URL: `GET /api/products/search?q=keyboard&page=0&size=20`.

- `required` defaults to true.
- `defaultValue` makes the parameter no longer mandatory in the sense of having to be present; if it is absent or empty, the default value is used.
- The data type is converted from a string; input that cannot be converted to `int` can lead to a binding error.
- `@RequestParam` **binds a value to a Java parameter**. The `params` attribute of `@RequestMapping` is a **condition for selecting the handler**; the two are related but not the same.

### 5.3. The params Condition

You can define multiple handlers on the same path but with different query conditions:

~~~java
@GetMapping(path = "/reports", params = "format=full")
Mono<Report> fullReport() {
    // GET /reports?format=full
}

@GetMapping(path = "/reports", params = "!format")
Mono<Report> defaultReport() {
    // GET /reports when there is no format query parameter
}
~~~

Common expressions:

- `"mode"`: the parameter must exist.
- `"!mode"`: the parameter must not exist.
- `"mode=full"`: the parameter must equal the specified value.
- `"mode!=full"`: the parameter must differ from the specified value.

If multiple mappings match, Spring compares their specificity to choose the best match. Do not create two handlers with the same condition or with overlapping conditions that are hard to distinguish; an unclear mapping can cause a registration error or an ambiguous error when handling a request.

## 6. The headers, consumes, and produces Conditions

### 6.1. Request Header Conditions

You can select a handler by a header:

~~~java
@GetMapping(path = "/reports", headers = "X-Client=admin")
Mono<Report> adminReport() {
    // Matches only when X-Client has the value admin.
}
~~~

Header conditions also support checking for presence, absence, or value. However, for content negotiation, use `consumes` and `produces` instead of writing conditions directly on `Content-Type` or `Accept`.

### 6.2. `consumes`: Request Content Type

`consumes` restricts the request body by the request's media type, usually based on the `Content-Type` header:

~~~java
@PostMapping(
    path = "/products",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
Mono<Product> create(@RequestBody Mono<CreateProduct> body) {
    // ...
}
~~~

The client must send a JSON body with an appropriate Content-Type. If it sends a media type the handler does not support, Spring usually returns 415 Unsupported Media Type.

You can accept multiple media types:

~~~java
@PostMapping(
    path = "/imports",
    consumes = {
        MediaType.APPLICATION_JSON_VALUE,
        "text/csv"
    }
)
Mono<ImportResult> importData(@RequestBody Mono<String> body) {
    // ...
}
~~~

This is only a mapping illustration; to parse CSV and JSON correctly, the application needs the corresponding logic/codec. Declaring `consumes` does not automatically convert the body into the desired format.

### 6.3. `produces`: Response Type

`produces` restricts the response media type according to what the client requests through `Accept`:

~~~java
@GetMapping(
    path = "/products/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE
)
Mono<Product> get(@PathVariable("id") String id) {
    // ...
}
~~~

If the client requests an incompatible response type, Spring may return 406 Not Acceptable.

With WebFlux, a `Flux<T>` returned together with `application/json` is usually encoded as a single JSON array. If you want to stream events via Server-Sent Events, you can use `text/event-stream` and the `Flux<ServerSentEvent<T>>` type or a suitable publisher. Do not assume that every `Flux` response is SSE.

### 6.4. Class Level and Method Level

You can put shared `consumes`/`produces` on the class and override them on the method. For these attributes, a declaration on the method **overrides** the same kind of condition at the class level, rather than always adding to it. This matters if a controller defaults to JSON but has one endpoint that returns SSE or accepts CSV.

## 7. A Complete Mapping Example in Spring WebFlux

The small project below implements a simple order API. It illustrates mapping by HTTP method, path variable, query condition, request body, and reactive response.

### 7.1. Creating a Gradle Project

The `build.gradle` file:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Create the file `src/main/java/demo/RequestMappingDemoApplication.java`:

~~~java
package demo;

import java.net.URI;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class RequestMappingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequestMappingDemoApplication.class, args);
    }
}

record CreateOrderRequest(String customer, int quantity) {}
record StatusPatch(String status) {}
record OrderView(
    String id, String customer, int quantity, String status
) {}

@RestController
@RequestMapping(
    path = "/api/orders",
    produces = MediaType.APPLICATION_JSON_VALUE
)
class OrderController {

    private final ConcurrentMap<String, OrderView> orders =
        new ConcurrentHashMap<>();

    OrderController() {
        orders.put("o-1",
            new OrderView("o-1", "An", 2, "NEW"));
        orders.put("o-2",
            new OrderView("o-2", "Binh", 1, "PAID"));
    }

    @GetMapping
    Flux<OrderView> list(
            @RequestParam(name = "status", required = false)
            String status) {
        return Flux.fromIterable(orders.values())
            .filter(order -> status == null
                || order.status().equalsIgnoreCase(status));
    }

    @GetMapping(path = "/search", params = "status")
    Flux<OrderView> searchByStatus(
            @RequestParam("status") String status) {
        return Flux.fromIterable(orders.values())
            .filter(order ->
                order.status().equalsIgnoreCase(status));
    }

    @GetMapping("/{id}")
    Mono<ResponseEntity<OrderView>> get(
            @PathVariable("id") String id) {
        return Mono.justOrEmpty(orders.get(id))
            .map(order -> ResponseEntity.ok().body(order))
            .defaultIfEmpty(
                ResponseEntity.<OrderView>notFound().build()
            );
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    Mono<ResponseEntity<OrderView>> create(
            @RequestBody Mono<CreateOrderRequest> body) {
        return body.map(request -> {
            String id = UUID.randomUUID().toString();
            OrderView created = new OrderView(
                id, request.customer(), request.quantity(), "NEW"
            );
            orders.put(id, created);
            return ResponseEntity
                .created(URI.create("/api/orders/" + id))
                .body(created);
        });
    }

    @PutMapping(
        path = "/{id}",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<ResponseEntity<OrderView>> replace(
            @PathVariable("id") String id,
            @RequestBody Mono<CreateOrderRequest> body) {
        return body.map(request -> {
            AtomicReference<OrderView> replaced =
                new AtomicReference<>();

            orders.computeIfPresent(id, (key, current) -> {
                OrderView next = new OrderView(
                    id, request.customer(), request.quantity(), "NEW"
                );
                replaced.set(next);
                return next;
            });

            OrderView result = replaced.get();
            return result == null
                ? ResponseEntity.<OrderView>notFound().build()
                : ResponseEntity.ok(result);
        });
    }

    @PatchMapping(
        path = "/{id}/status",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<ResponseEntity<OrderView>> changeStatus(
            @PathVariable("id") String id,
            @RequestBody Mono<StatusPatch> body) {
        return body.map(patch -> {
            AtomicReference<OrderView> updated =
                new AtomicReference<>();

            orders.computeIfPresent(id, (key, current) -> {
                OrderView next = new OrderView(
                    current.id(), current.customer(),
                    current.quantity(), patch.status()
                );
                updated.set(next);
                return next;
            });

            OrderView result = updated.get();
            return result == null
                ? ResponseEntity.<OrderView>notFound().build()
                : ResponseEntity.ok(result);
        });
    }

    @DeleteMapping("/{id}")
    ResponseEntity<Void> delete(
            @PathVariable("id") String id) {
        OrderView removed = orders.remove(id);
        return removed == null
            ? ResponseEntity.<Void>notFound().build()
            : ResponseEntity.noContent().build();
    }
}
~~~

This is a complete Spring Boot program at demo level; it does not use a database and the data lives in the process's memory. `ConcurrentHashMap` protects basic map operations against concurrent access, but the example does not replace transactions or persistence for a real application. `AtomicReference` in PUT/PATCH is used to capture the result of the atomic `computeIfPresent` update in order to distinguish an existing ID from a non-existing one.

Run the application:

~~~bash
gradle bootRun
~~~

If the project has a Gradle Wrapper, use `./gradlew bootRun`; on Windows use `gradlew.bat bootRun`. By default Spring Boot starts the server on port 8080 unless configured otherwise.

### 7.2. Calling the Endpoints

List all:

~~~bash
curl -i http://localhost:8080/api/orders
~~~

Filter by query parameter:

~~~bash
curl -i "http://localhost:8080/api/orders?status=PAID"
~~~

Find by path variable:

~~~bash
curl -i http://localhost:8080/api/orders/o-1
~~~

Find through the handler with the `params` condition:

~~~bash
curl -i "http://localhost:8080/api/orders/search?status=NEW"
~~~

Create an order:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"customer":"Lan","quantity":3}'
~~~

Replace an order:

~~~bash
curl -i -X PUT http://localhost:8080/api/orders/o-1 \
  -H "Content-Type: application/json" \
  -d '{"customer":"An Nguyen","quantity":4}'
~~~

Update the status:

~~~bash
curl -i -X PATCH http://localhost:8080/api/orders/o-1/status \
  -H "Content-Type: application/json" \
  -d '{"status":"PAID"}'
~~~

Delete:

~~~bash
curl -i -X DELETE http://localhost:8080/api/orders/o-1
~~~

The commands above illustrate how to call the endpoints; the actual response bodies of POST/PUT/PATCH contain a UUID and the corresponding data. There is no fixed stdout for all the commands because UUIDs are randomly generated and the map state changes according to the order of calls.

## 8. Mapping Conditions and Common Errors

### 8.1. Same Path, Different HTTP Method

The two following handlers are valid because their methods differ:

~~~java
@GetMapping("/{id}")
Mono<Product> get(@PathVariable("id") String id) {
    // ...
}

@DeleteMapping("/{id}")
Mono<Void> delete(@PathVariable("id") String id) {
    // ...
}
~~~

If a client calls POST on this path but there is no matching POST mapping, Spring may return 405 Method Not Allowed when the path exists but the HTTP method is not supported.

### 8.2. Same Path, Different params or headers

~~~java
@GetMapping(path = "/reports", params = "format=csv")
Mono<byte[]> csv() {
    // ...
}

@GetMapping(path = "/reports", params = "format=json")
Mono<Report> json() {
    // ...
}
~~~

Each handler has its own query condition. If you add a default handler with no condition, consider specificity and make sure the more specific mapping is chosen as expected. Avoid duplicate or overlapping conditions that are hard to resolve.

### 8.3. Wrong Content-Type or Accept

- Sending an XML body to a handler that only has `consumes="application/json"` can lead to 415.
- Sending `Accept: application/xml` to a handler that only has `produces="application/json"` can lead to 406.
- A missing body or invalid JSON can cause an error while reading/decoding the request body; this is not a mapping error like 415.

Distinguish **no matching handler** from **a handler exists but the body cannot be bound**. Logging/tracing mapping and codec errors separately helps find the cause.

### 8.4. Using Multiple Mapping Annotations on the Same Method

Do not write:

~~~java
@GetMapping("/items")
@PostMapping("/items")
public Mono<Void> handle() {
    // ...
}
~~~

The specialized annotations are all composed annotations of `@RequestMapping`. Spring does not merge two annotations on the same method into one mapping that has both GET and POST; when it detects multiple mapping annotations on the same element, Spring logs a warning and uses only the first mapping. If you truly need multiple HTTP methods for one handler, declare a single `@RequestMapping(path=..., method={...})` and understand the endpoint's contract clearly. Usually it is better to split the methods so that each HTTP method has its own semantics and body/response.

### 8.5. Confusing Mapping Conditions with Argument Binding

~~~java
@GetMapping(path = "/search", params = "status")
Flux<Order> search(@RequestParam("status") String status) {
    // ...
}
~~~

`params="status"` only allows the mapping when the query parameter exists; `@RequestParam` is what puts that value into the Java parameter. You can use `@RequestParam` without declaring `params` if you do not need to select the handler based on the presence of the parameter.

### 8.6. Confusing consumes and produces

- `consumes`: what type of content does the client **send**?
- `produces`: what type of content does the server **return** according to Accept negotiation?

Swapping the two attributes often causes the endpoint not to match the request or to respond with an unexpected 406/415.

## 9. How Spring Selects a Handler When Multiple Mappings Match

Spring compares the mapping conditions, not just the path. The important factors include:

1. Which path pattern is more specific.
2. Whether the HTTP method matches.
3. Query parameter and header conditions.
4. Whether the request Content-Type matches `consumes`.
5. Whether Accept is compatible with `produces`.

For example, `/orders/search` is more specific than `/orders/{id}` when both can match the path string. Spring WebFlux uses `PathPattern` and a specificity comparator to choose the better pattern. However, if two mappings have the same specificity and the same conditions, the application may hit an ambiguous mapping; do not rely on method declaration order to resolve conflicts.

When the application starts, completely duplicate mappings are usually detected at handler registration time. Different mappings that can still match the same request need to be designed clearly to avoid runtime errors.

**A useful principle:** each endpoint should have a clear contract of path + HTTP method + request conditions. Use query/header conditions when they genuinely distinguish endpoint variants; if it is merely a data filter, it is usually better to bind it with `@RequestParam` and handle it in the logic.

## 10. Reactive Request Body and Response

In Spring WebFlux, a handler can receive and return publishers:

~~~java
@PostMapping
Mono<ResponseEntity<ProductView>> create(
        @RequestBody Mono<CreateProduct> body) {
    return body.flatMap(service::create)
        .map(saved -> ResponseEntity
            .created(URI.create("/api/products/" + saved.id()))
            .body(saved));
}
~~~

This is a snippet integrated with `service.create` returning `Mono<ProductView>`. Spring WebFlux reads the body asynchronously, puts the object into the publisher, and then the handler composes the service work without blocking a thread.

Some common signature types:

| Parameter/return value | Meaning |
| --- | --- |
| `@RequestBody Mono<T>` | Receives a single body, decoded asynchronously into one object. |
| `@RequestBody Flux<T>` | Receives a body as a stream of elements when the codec and media type support it. |
| `Mono<T>` | Zero or one response value. |
| `Flux<T>` | Multiple response values; how they are encoded depends on the media type. |
| `Mono<ResponseEntity<T>>` | Response status, headers, and body decided asynchronously. |
| `Mono<Void>` | Only signals completion/error, with no value body. |

**Do not call `block()` or `subscribe()` inside a controller** to obtain the body or to launch a service. Return the composed publisher; WebFlux manages the subscription, cancellation, and response writing.

## 11. Testing Mappings with WebTestClient

WebTestClient can test a WebFlux controller without starting a real server. In the project from section 7, create the file `src/test/java/demo/OrderControllerTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

class OrderControllerTest {

    private final WebTestClient client =
        WebTestClient.bindToController(new OrderController()).build();

    @Test
    void getMappingUsesPathVariable() {
        client.get()
            .uri("/api/orders/o-1")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.id").isEqualTo("o-1");
    }

    @Test
    void queryParameterSelectsSearchMapping() {
        client.get()
            .uri("/api/orders/search?status=PAID")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$[0].status").isEqualTo("PAID");
    }

    @Test
    void postMappingCreatesResource() {
        client.post()
            .uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("Lan", 3))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().exists("Location")
            .expectBody()
            .jsonPath("$.customer").isEqualTo("Lan")
            .jsonPath("$.quantity").isEqualTo(3);
    }

    @Test
    void optionsReportsAllowedMethods() {
        client.options()
            .uri("/api/orders")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists("Allow");
    }
}
~~~

Run:

~~~bash
gradle test
~~~

Or `./gradlew test` / `gradlew.bat test`. The tests verify:

- The GET mapping receives the path variable and returns JSON.
- The query parameter is used to select the conditional handler.
- The POST mapping receives JSON and returns 201 along with the Location header.
- OPTIONS is supported by Spring and provides Allow for the path.

In the demo controller, the seed data has `o-2` with status `PAID`, so the search test has a result. If you change the fixture, update the expectations. For tests that run in parallel or for POST/PUT/PATCH/DELETE tests, create a separate controller for each test or reset the fixture to avoid depending on shared state.

## 12. Common Mistakes and How to Fix Them

| Mistake | Consequence | How to handle it |
| --- | --- | --- |
| Using `@RequestMapping` without declaring a method for an endpoint that only needs GET | The endpoint may match more HTTP methods than intended | Use `@GetMapping` or declare `method` explicitly |
| Repeating the path prefix on every method | URLs are hard to maintain and routes drift easily | Put the shared prefix at the class level |
| Using `@GetMapping` and `@PostMapping` on the same method | Spring does not merge them into one mapping; only one mapping is used | Split the handler or deliberately use a single `@RequestMapping(method={...})` |
| Thinking `params` automatically binds the query to a Java variable | The handler is selected but the variable is not bound if `@RequestParam` is missing | Use `@RequestParam` for the argument |
| Using `produces` to check the request Content-Type | Wrong direction of content negotiation | Use `consumes` for the request, `produces` for the response |
| Not declaring `consumes` for a body with multiple formats | The handler may accept requests that do not fit the codec/logic | Declare the media type and implement the corresponding parser |
| Creating two mappings with the same path/method/condition | Ambiguous error or duplicate mapping registration | Clarify the path, params, headers, or split the controller |
| Using `@PathVariable` but the path has no corresponding variable | Binding fails | Check the placeholder name and the annotation |
| Assuming `@PatchMapping` automatically merges JSON objects | The annotation only selects the HTTP method/path; the patch logic is decided by the application | Design the DTO/JSON Patch/Merge Patch and clear semantics |
| Returning `Flux` and thinking it is SSE by default | The codec may encode it as a JSON array or another form depending on the media type | Declare an appropriate `produces` such as `text/event-stream` when SSE is needed |
| Calling `block()` in a reactive controller | Blocks the event loop or is rejected by Reactor | Return `Mono`/`Flux` and compose with operators |
| Only testing status 200 | May miss a wrong path, header, content type, or body | Use WebTestClient to verify the whole HTTP contract |

## 13. Controller Mapping Design Checklist

Before adding an endpoint, check:

1. **Resource and path:** which resource does the URL represent? Does the class-level path share a sensible common part?
2. **HTTP method:** do GET/POST/PUT/PATCH/DELETE have the right semantics and retry/idempotency characteristics?
3. **Path variable and query:** identifying data goes in the path; filters/pagination usually go in the query. Do you need a `params` condition to select the handler, or just `@RequestParam`?
4. **Media type:** which types does the request body accept (`consumes`)? Which types does the response have (`produces`)?
5. **Headers:** which headers genuinely take part in selecting the mapping? Could you use a separate authentication/CORS mechanism instead of turning a header into a route condition?
6. **Mapping specificity:** are there duplicate or overlapping routes? Are literal paths and variable paths clearly distinguished?
7. **Reactive lifecycle:** does the handler return a publisher instead of subscribing/blocking itself? How can the body/response be empty, fail, or be cancelled?
8. **Status and headers:** does a create POST return 201/Location? Does a GET that finds nothing return 404? Does a successful DELETE return 204? Does the API document those cases?
9. **Tests:** has WebTestClient verified the method, URL, params, header, media type, status, and body?

**Key takeaway:** `@RequestMapping` describes the conditions for a request to be selected for a handler; `@GetMapping`/`@PostMapping`/`@PutMapping`/`@PatchMapping`/`@DeleteMapping` help declare a specific HTTP method. Combine the class-level path, method-level request conditions, correctly directed media types, and an appropriate reactive signature. A clear mapping makes the API easy to understand, easy to test, and avoids accepting the wrong request.

## References

- Spring Framework — WebFlux: Mapping Requests: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html
- Spring Framework — Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
- Spring Framework — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Framework — WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- RFC 9110 — HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110
