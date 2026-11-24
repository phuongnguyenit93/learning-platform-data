# @RequestMapping on Interfaces and Organizing Controller Contracts

## 1. Objectives and Scope

In Spring MVC, a controller normally uses `@RestController` or `@Controller` and declares `@RequestMapping`, `@GetMapping`, `@PostMapping` directly on the class/methods. When multiple teams develop APIs together, you can **place the HTTP route declarations on a Java interface**, letting the interface express the HTTP contract while the controller class handles the implementation.

After this lesson, you will be able to:
- Understand how Spring MVC discovers mappings placed on an interface and the role of the implementing class.
- Design a consistent contract for paths, HTTP methods, parameters, bodies, media types, and return types.
- Implement, run, and test a controller whose mappings live only on an interface.
- Recognize common pitfalls when mixing annotations, having multiple implementations, or using AOP proxies.

The scope is **Spring MVC (Servlet stack)** with Java 17+ and Spring Boot 3.x / Spring Framework 6.x examples. Principles around controller interfaces also apply to other modern versions, though proxy configuration and controller scanning behavior should be tested against the specific version in use.

## 2. The Nature of `@RequestMapping` on Interfaces

`@RequestMapping` describes the mapping rules from an HTTP request to a handler method: `path`, `method`, `params`, `headers`, `consumes`, `produces`. Placed at the type level, it defines shared prefixes/conditions; placed at the method level, it defines specific endpoints. `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping`, and `@DeleteMapping` are composed annotations built on `@RequestMapping`.

A Java interface can declare annotations on the type, methods, and parameters:

~~~java
@RequestMapping("/api/books")
public interface BookApi {
    @GetMapping("/{id}")
    BookResponse get(@PathVariable("id") long id);
}
~~~

Key takeaways:
1. **The Java interface defines the method signature** (name, parameters, return type), while **Spring MVC interprets annotations across the type/method hierarchy** to build mappings. You cannot infer this behavior solely from Java's annotation inheritance rules or `@Inherited`.
2. **An interface does not automatically become a controller bean** just because it has `@RequestMapping`. A Spring-registered implementing class—usually annotated with `@RestController`—is still required.
3. A mapping on an interface is not a second endpoint. With **one implementing controller**, Spring registers the handler methods on that bean; requests are routed to the corresponding implementation.
4. The interface is a **web-layer HTTP contract**. It differs from a service interface (business contract) and from automatic HTTP client generation; declaring `@RequestMapping` alone does not create a client for sending requests.

Simplified processing diagram:

~~~text
BookApi (interface: @RequestMapping, @GetMapping, @PathVariable)
              │ implements
              ▼
BookController (@RestController: implementation logic)
              │ component scan + handler detection
              ▼
RequestMappingHandlerMapping registers GET /api/books/{id}
              │ request matches path + HTTP method + conditions
              ▼
RequestMappingHandlerAdapter resolves arguments → invokes BookController.get(...)
              │
              ▼
HttpMessageConverter writes BookResponse as JSON
~~~

Here `RequestMappingHandlerMapping` detects controllers and constructs `RequestMappingInfo`; `RequestMappingHandlerAdapter` executes the handler. Returning JSON in the example happens thanks to `@RestController` (which includes `@ResponseBody`) and an appropriate HTTP message converter, not because the interface generates JSON itself.

## 3. What Must the HTTP Contract Agree On?

| Element | Where placed in interface | Meaning |
| --- | --- | --- |
| Route prefix | `@RequestMapping("/api/books")` on interface | Groups endpoints under the same resource |
| HTTP method + path | `@GetMapping("/{id}")` / `@PostMapping` on method | Separates read/create operations and avoids overly broad mappings |
| Path variable | `@PathVariable("id")` on parameter | Binds `{id}` in the URL to a Java parameter |
| Query/header | `@RequestParam`, `@RequestHeader` if needed | Constrains request data |
| Request JSON | `@RequestBody` and `consumes = "application/json"` | Defines input data, assists media-type selection |
| Response JSON | `produces = "application/json"` | Defines the response format the endpoint produces |
| Status code | `ResponseEntity<T>` or `@ResponseStatus` | Expresses success outcomes and error scenarios clearly |

A type-level mapping combines with a method-level mapping (e.g., `/api/books` + `/{id}` becomes `/api/books/{id}`). Not all attributes "accumulate" the same way `path` does: for instance, method-level `consumes` and `produces` can **override** the corresponding type-level conditions. Therefore, verify actual effective conditions with tests.

### Why Keep Annotations in One Place?

If the interface declares `@GetMapping` while the implementation adds `@PostMapping` or alters `@RequestMapping`, each location describes only part of the contract. That increases the risk of unexpected mappings, depending on how Spring merges annotations across the type hierarchy and how proxies expose types at runtime. **Safe convention: once you choose a controller interface, consistently keep mapping annotations (and related contract annotations like `@SessionAttributes` if used) on the interface; the implementation should mainly hold `@RestController` and implementation logic.**

Also never put `@RequestMapping` and `@GetMapping` together on the **same method** as two independent mappings. They belong to the same mapping annotation family; Spring logs a warning and may only use the first annotation.

## 4. Complete Example: Contract → Controller → HTTP Request

Suppose a Spring Boot 3.x application with Java 17+ has `spring-boot-starter-web` and `spring-boot-starter-test` (for testing) dependencies. The example below uses in-memory storage to focus on request mapping without database dependencies.

File structure:

~~~text
src/main/java/com/example/demo/
├── DemoApplication.java
├── api/
│   ├── BookApi.java
│   ├── BookResponse.java
│   └── CreateBookRequest.java
└── web/
    └── BookController.java
src/test/java/com/example/demo/web/
└── BookControllerMappingTest.java
~~~

### 4.1. Contract Interface

`src/main/java/com/example/demo/api/BookApi.java`

~~~java
package com.example.demo.api;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;

@RequestMapping(path = "/api/books", produces = MediaType.APPLICATION_JSON_VALUE)
public interface BookApi {

    @GetMapping("/{id}")
    ResponseEntity<BookResponse> get(@PathVariable("id") long id);

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<BookResponse> create(@RequestBody CreateBookRequest input);
}
~~~

- `@RequestMapping` on the interface defines the `/api/books` prefix and shared JSON response media type.
- `@GetMapping("/{id}")` accepts only GET and extracts `id` from the URL; naming `@PathVariable("id")` explicitly avoids depending on whether the Java compiler preserves parameter names.
- `@PostMapping` accepts only POST at `/api/books`; `consumes` requires `Content-Type: application/json`.
- `ResponseEntity` lets the implementation decide status codes and bodies (e.g., `200`, `201`, `404`), without mixing status logic into the interface signature.

### 4.2. Request and Response DTOs

`src/main/java/com/example/demo/api/BookResponse.java`

~~~java
package com.example.demo.api;

public record BookResponse(long id, String title) {}
~~~

`src/main/java/com/example/demo/api/CreateBookRequest.java`

~~~java
package com.example.demo.api;

public record CreateBookRequest(String title) {}
~~~

Java records suit concise, immutable DTOs. Spring Boot 3.x (with Jackson from the web starter) serializes/deserializes JSON to and from these records.

### 4.3. Implementation: Do Not Repeat Mappings

`src/main/java/com/example/demo/web/BookController.java`

~~~java
package com.example.demo.web;

import com.example.demo.api.BookApi;
import com.example.demo.api.BookResponse;
import com.example.demo.api.CreateBookRequest;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BookController implements BookApi {

    private final AtomicLong nextId = new AtomicLong();
    private final ConcurrentMap<Long, BookResponse> books = new ConcurrentHashMap<>();

    @Override
    public ResponseEntity<BookResponse> get(long id) {
        BookResponse book = books.get(id);
        return book == null
                ? ResponseEntity.notFound().build()
                : ResponseEntity.ok(book);
    }

    @Override
    public ResponseEntity<BookResponse> create(CreateBookRequest input) {
        long id = nextId.incrementAndGet();
        BookResponse book = new BookResponse(id, input.title());
        books.put(id, book);
        return ResponseEntity.status(HttpStatus.CREATED).body(book);
    }
}
~~~

This class has `@RestController` so it is scanned as a web bean and writes response bodies; the `get` and `create` methods **do not need to repeat `@GetMapping`, `@PostMapping`, `@RequestBody`, or `@PathVariable`**. Spring MVC reads request metadata from the implemented interface. `@Override` is a Java compiler check that catches signature mismatches against the contract.

`ConcurrentHashMap` and `AtomicLong` merely provide an example safe for multiple concurrent demo requests, not a production persistence pattern. This demo does not enforce non-null or non-blank `title`; if validation is needed, add Bean Validation (`@Valid`, Jakarta constraints, and `spring-boot-starter-validation`) along with appropriate error handling.

### 4.4. Application Entry Point

`src/main/java/com/example/demo/DemoApplication.java`

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` resides in parent package `com.example.demo`, so component scan discovers `web.BookController`. This avoids the pitfall of defining a valid interface while the app fails to detect the implementation.

Example dependencies needed in a Gradle Boot project:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

The dependency snippet assumes the project already configures the Spring Boot plugin, Maven Central repository, and Java toolchain. Run in the project directory containing the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Test the API from a bash/WSL/macOS terminal:

~~~bash
curl -i -X POST http://localhost:8080/api/books -H 'Content-Type: application/json' -H 'Accept: application/json' -d '{"title":"Spring MVC"}'
curl -i http://localhost:8080/api/books/1 -H 'Accept: application/json'
curl -i http://localhost:8080/api/books/999 -H 'Accept: application/json'
~~~

If the app starts fresh with empty memory and no other book-creation requests intervene, the expected responses respectively are:

~~~text
POST /api/books          -> 201 Created, body {"id":1,"title":"Spring MVC"}
GET  /api/books/1        -> 200 OK,      body {"id":1,"title":"Spring MVC"}
GET  /api/books/999      -> 404 Not Found
~~~

The statuses and bodies above are reliable outcomes of the sample code; exact header order, HTTP error payload format, and logs depend on runtime configuration. Sending POST with the wrong `Content-Type` (e.g., `text/plain`) can return `415 Unsupported Media Type` because `consumes` is unsatisfied; sending an undeclared HTTP method on the same path typically returns `405 Method Not Allowed`.

## 5. Verifying Mappings with MockMvc

`src/test/java/com/example/demo/web/BookControllerMappingTest.java`

~~~java
package com.example.demo.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(BookController.class)
class BookControllerMappingTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void interfaceMappingIsUsedByController() throws Exception {
        mockMvc.perform(post("/api/books")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Spring MVC\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(1))
                .andExpect(jsonPath("$.title").value("Spring MVC"));

        mockMvc.perform(get("/api/books/1")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Spring MVC"));

        mockMvc.perform(get("/api/books/999")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound());

        mockMvc.perform(delete("/api/books/1"))
                .andExpect(status().isMethodNotAllowed());
    }
}
~~~

Run `./gradlew test` in a project with proper JUnit Platform test configuration. Because the test puts no mapping annotations on the implementation yet verifies the routes work, it directly confirms that **Spring reads the interface metadata**. For projects with Spring Security or extra global MVC configuration, set up the test slice appropriately (e.g., configuring authentication or mocks) so results are not affected by external filters.

Add test cases matching your real contract: invalid path variables, missing bodies, wrong `Content-Type`, unsupported `Accept`, required query/header params, and error statuses. After upgrading Spring, re-verify registration with tests or Spring Boot Actuator `/actuator/mappings` (only when Actuator is enabled and that endpoint is permitted).

## 6. Package Organization and Responsibilities

A practical structure for a small API might look like:

~~~text
com.example.catalog
├── api/                 # HTTP contract and request/response DTOs
│   ├── BookApi.java
│   └── dto/...
├── web/                 # @RestController implements BookApi, HTTP error translation
│   └── BookController.java
├── application/         # Use cases/services, business logic
│   └── BookService.java
└── domain/              # Entities/value objects, business rules
~~~

The `BookApi` contract should describe **what the HTTP client observes**: routes, methods, request/response shapes, status codes, and necessary communication constraints. `BookController` receives requests, calls services, and translates outcomes to HTTP. `BookService` needs no knowledge of `@GetMapping` or the Servlet API.

If splitting the API contract into a library module, the implementing module must depend on the module containing the interface and DTOs; the web module needs Spring MVC dependencies for annotations. Creating a separate module is unnecessary for small apps: the value of a contract is clear boundaries and reuse, weighed against extra files and dependencies.

**Change rule:** modifying `/api/books/{id}`, renaming a `@PathVariable`, adding a required header, or altering a DTO are all HTTP contract changes that can impact clients and tests. Update API documentation, integration tests, and compatibility policies accordingly. Never treat renaming a Java method (when route and signature remain compatible) as equivalent to changing an HTTP endpoint.

## 7. AOP Proxy Pitfalls: Easy-to-Miss Bugs

AOP (such as advice from `@Transactional` or custom aspects) can wrap a controller in a proxy. There are two common kinds:

| Proxy type | How the controller is exposed | Points to watch |
| --- | --- | --- |
| Class-based proxy (CGLIB) | Proxy subclasses the controller class | Generally works better with interface-based controllers and interface annotations; note `final` class/method limitations |
| Interface-based proxy (JDK dynamic proxy) | Proxy exposes only the interfaces | Controller detection and annotation discovery depend on proxy type and Spring version |

**Version warning:** starting with Spring Framework 6.0, when using an *interface-based proxy*, Spring MVC **no longer detects a controller solely from type-level `@RequestMapping` on the interface**. Spring documentation recommends using a **class-based proxy** or, if an interface proxy must be used, annotating the interface with `@Controller` as well. This is a specific rule about *controller detection*, not a statement that all `@RequestMapping`s on interfaces stopped working in Spring 6.

In typical applications, keep `@RestController` on the implementation class and prefer placing transactions on services. If AOP is applied directly to a controller and endpoints suddenly return `404` after adding advice, inspect the proxy type, controller annotations, component scan, and registered mappings. Whenever changing proxy mechanisms, re-run MockMvc/smoke tests rather than relying only on the Java compiler.

## 8. Common Errors and How to Resolve Them

| Symptom | Possible cause | How to inspect and fix |
| --- | --- | --- |
| `404` on all routes despite `BookApi` | No implementing bean, controller outside component scan, or proxy detection issue | Ensure implementation has `@RestController`, scan the right package, inspect proxy/mappings |
| `404` on one specific URL | Wrong type-level prefix, path variable, or context path | Compare interface `@RequestMapping` with `@GetMapping` and the request URL |
| `405 Method Not Allowed` | URL has a mapping, but HTTP method does not match | Use accurate `@GetMapping`/`@PostMapping` and send the right method |
| `415 Unsupported Media Type` | `Content-Type` fails `consumes` | Send JSON with the right content type or intentionally revise the contract |
| `406 Not Acceptable` | `Accept` is incompatible with `produces` | Check media types, message converters, and Accept |
| `400` during parameter binding | Mismatched `@PathVariable` name or invalid JSON shape/types | Name variables explicitly, check DTO and body |
| Startup reports ambiguous mapping | Two controllers register identical path, method, and conditions | Ensure only one owner per endpoint or design clearly distinct routes |
| Annotations behave unexpectedly | Mixing mappings across interface/implementation or putting multiple mapping annotations on one element | Consolidate contract on interface, remove duplicate mapping annotations, write tests |
| Documentation/codegen missing endpoints | Documentation tool does not scan hierarchy annotations the same way Spring MVC does | Check tool configuration and version, compare docs against runtime mappings |

Do not "fix" a `404` by copying every annotation down to the implementation before checking component scan/proxies: doing so splits the contract across two places and invites drift.

### Can Two Implementations of the Same Interface Share a Route?

In Java syntax, multiple classes can `implement BookApi`. However, when **both are controller beans** with identical HTTP mappings, Spring MVC can fail with ambiguous mapping at startup because multiple handlers claim the same request. If you need two API versions or channels, design **separate paths/mapping conditions right in the contract**, or register only one implementation via appropriate profiles/conditions; never assume Spring picks one implementation like dependency injection.

### Should Interfaces Be Used for Every Controller?

Not necessarily. For a simple controller, placing `@GetMapping` directly on the class can be easier to read. Interfaces shine when sharing contracts between API and implementation teams, governing changes, generating contract-driven docs/tests, or splitting packages/modules. Avoid creating interfaces merely to mirror every method verbatim when no clear boundary need exists.

### How Does This Differ from `@HttpExchange`?

`@HttpExchange` and annotations like `@GetExchange` can define HTTP interfaces for Spring to generate **client** proxies; Spring MVC also supports these contracts in certain server scenarios. However, `@RequestMapping` is the flexible server-side mapping contract with a richer set of conditions. Do not assume `BookApi` with `@GetMapping` creates an HTTP client automatically, and do not switch to `@HttpExchange` solely to separate a controller contract.

## 9. Checklist When Designing Controller Contracts

1. Identify which HTTP boundary the interface serves and who owns each endpoint.
2. Put the `@RequestMapping` prefix on the interface; use specific HTTP-method annotations for each operation.
3. Explicitly write `@PathVariable`/`@RequestParam` names when helpful for clarity/operations; define stable request/response DTOs.
4. Keep all mapping metadata consistently on the interface; the `@RestController` class implements logic without duplicating mappings.
5. Verify the controller bean is scanned, has a single mapping owner, and AOP does not break controller detection.
6. Write MockMvc tests for routes, verbs, body/media types, response statuses, and key error scenarios.
7. When changing the contract, treat it as an API change requiring compatibility review and doc updates.

**Remember:** the interface states "which HTTP requests are accepted and under what contract"; the implementation states "how they are handled". Spring MVC connects the two by scanning mapping annotations across the controller hierarchy. This boundary pays off when kept consistent and continuously verified through the actual HTTP dispatcher.

## 10. Official References

- [Spring Framework — Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): `@RequestMapping`, composed mappings, request conditions, `@HttpExchange`.
- [Spring Framework — Controller Declaration / AOP Proxies](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann.html): controller registration, proxy notes from Spring 6.0.
- [Spring Framework — Handler Methods](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods.html): handler signatures, parameter/return handling.
- [`@RequestMapping` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/annotation/RequestMapping.html): recommendation for consistent mapping annotations when using controller interfaces.
