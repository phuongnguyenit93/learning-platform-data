# @RequestMapping at Class and Method Level; @GetMapping and @PostMapping in Spring MVC

## 1. Goal: Turning URLs and HTTP Methods into Endpoints

In Spring MVC, a controller can expose multiple endpoints. **`@RequestMapping`** describes the conditions for an HTTP request to be dispatched to a controller method, such as path, HTTP method, query parameters, headers, incoming media type, and response media type. The **`@GetMapping`** and **`@PostMapping`** annotations are specialized forms that explicitly express whether a request uses GET or POST.

After this lesson, you will be able to:

- Place `@RequestMapping` at the **class level** to declare a common prefix, then place `@GetMapping` or `@PostMapping` at the **method level** to declare specific endpoints.
- Write the equivalent syntax using `@RequestMapping(method = RequestMethod.GET/POST)` and understand why specialized annotations are preferred.
- Distinguish **URL path**, **HTTP method**, **URI variable**, **query parameter**, **request body**, and the `params`, `headers`, `consumes`, `produces` conditions.
- Distinguish a successfully mapped route from Spring resolving arguments, executing business code, and producing a response.
- Build a runnable Java 17/Spring Boot MVC example, verify it with `curl` and `MockMvc`, and recognize 404, 405, 400, 406, and 415 scenarios.

The scope here is **Spring MVC on the Servlet stack**. Spring WebFlux also has many similarly named annotations, but uses a reactive web runtime and its own dispatching mechanism. This lesson describes MVC mapping; it does not require detailed knowledge of WebFlux.

## 2. Where Mapping Sits in the MVC Processing Flow

When an application has an active `DispatcherServlet`, the typical flow is:

```text
Client sends GET /api/books/42
                 |
           Servlet container
                 |
           DispatcherServlet
                 |
      RequestMappingHandlerMapping
      - Is HTTP method GET?
      - Does path /api/books/42 match?
      - Do params, headers, consumes, produces match?
                 |
           select HandlerMethod
                 |
       RequestMappingHandlerAdapter
       - resolve @PathVariable, @RequestBody...
       - invoke controller method
                 |
       return value / message converters
                 |
           HTTP response
```

**`@RequestMapping` does not directly send an HTTP response.** It provides metadata for `RequestMappingHandlerMapping` to identify the appropriate handler method. Only after the handler is selected does `HandlerAdapter` prepare arguments, invoke the method, and process the return type.

Example:

```java
@RestController
@RequestMapping("/api/books")
public class BookController {

    @GetMapping("/{id}")
    public String byId(@PathVariable long id) {
        return "book:" + id;
    }
}
```

This is a **fragment** (without imports or a runnable application). When receiving `GET /api/books/42`, Spring combines both mappings into one endpoint, extracts `id=42`, and calls `byId(42)`. Converting the string `"42"` to `long` belongs to the argument resolution phase, after mapping has selected the handler.

## 3. `@RequestMapping` at Class Level and Method Level

### 3.1. Class Level: Grouping Endpoints with a Shared Prefix

Placing `@RequestMapping("/api/books")` on a class gives every method inside a shared URL prefix, avoiding repeating `/api/books`:

```java
@RestController
@RequestMapping("/api/books")
public class BookController {

    @GetMapping
    public String list() {
        return "list";
    }

    @GetMapping("/{id}")
    public String detail(@PathVariable String id) {
        return "book:" + id;
    }

    @PostMapping
    public String create() {
        return "created";
    }
}
```

This is a **standalone example for reading syntax**, not the class from the complete project in section 8.

| Class declaration | Method declaration | Resulting HTTP endpoint |
| --- | --- | --- |
| `@RequestMapping("/api/books")` | `@GetMapping` | `GET /api/books` |
| `@RequestMapping("/api/books")` | `@GetMapping("/{id}")` | `GET /api/books/42` |
| `@RequestMapping("/api/books")` | `@PostMapping` | `POST /api/books` |

**Class level alone does not generate handlers.** Even though the class has a prefix, only properly registered handler methods become endpoints. Without `@GetMapping` on a method, declaring a prefix at the class level does not implicitly create `GET /api/books`.

Class-level `@RequestMapping` is optional: you can write the full path on each method. It is especially useful for a group of resources sharing a prefix, such as `/api/users` or `/admin/reports`.

### 3.2. Method Level: Specifying the Concrete Operation

At the method level, you can write:

```java
@RequestMapping(path = "/{id}", method = RequestMethod.GET)
public String read(@PathVariable String id) {
    return id;
}
```

Or more concisely:

```java
@GetMapping("/{id}")
public String read(@PathVariable String id) {
    return id;
}
```

Both forms express HTTP GET for `/{id}` within the same class context. Similarly:

```java
@RequestMapping(path = "", method = RequestMethod.POST)
public String create() {
    return "created";
}
```

Can be written as:

```java
@PostMapping
public String create() {
    return "created";
}
```

These snippets are **method fragments placed inside a controller**, not standalone runnable Java files.

### 3.3. What Does Omitting the HTTP Method Mean?

`@RequestMapping("/ping")` **does not restrict** requests to GET or POST. Spring MVC can match multiple HTTP methods for that mapping given the remaining conditions. This behavior can cause an endpoint to unintentionally accept unintended operations.

Example:

```java
@RequestMapping("/ping")
public String ping() {
    return "pong";
}
```

Do not assume it is a "GET route". If the purpose is a read-only status endpoint, use `@GetMapping("/ping")`. If a method **genuinely** supports multiple HTTP methods, declare them explicitly:

```java
@RequestMapping(
    path = "/shared",
    method = {RequestMethod.GET, RequestMethod.POST}
)
public String shared() {
    return "shared";
}
```

Using multiple methods must be intentional: GET is expected to be **safe/read-only**, whereas POST is typically used to trigger an action or create a resource. Do not use GET for write/state-changing operations merely because the URL is convenient to call.

## 4. `@GetMapping`: Expressing Read Operations

`@GetMapping` is a composed annotation built on `@RequestMapping(method = RequestMethod.GET)`. It accepts most key mapping attributes such as `path`/`value`, `params`, `headers`, and `produces`.

Example:

```java
@GetMapping(path = "/{id}", produces = "application/json")
public Book getBook(@PathVariable("id") long id) {
    return new Book(id, "Java");
}
```

When using `@RestController` with a JSON converter such as Jackson, Spring can convert `Book` into JSON. The `@PathVariable` type and `Book` record must exist appropriately; this snippet is not a standalone program.

Properties to keep in mind:

- GET is typically used to **retrieve resources**. By HTTP semantics, GET is a safe method; avoid designing endpoints that intentionally mutate system state on GET.
- `@GetMapping("/{id}")` matches a path with **one segment** captured into `id`; a path variable is not a query parameter.
- HTTP GET may include `Accept` to select the response format; `produces` describes the media types the handler can generate.
- Spring MVC also supports HTTP **HEAD** via GET mappings: HEAD returns metadata/headers like GET but omits the response body.
- For HTTP **OPTIONS**, Spring MVC typically synthesizes valid HTTP methods into an `Allow` header automatically; applications can customize this behavior.

### 4.1. `@PathVariable` and `@RequestParam`

Two different requests:

```text
GET /api/books/42        -> id is in the URI path
GET /api/books?id=42     -> id is a query parameter
```

Two ways to extract the data:

```java
@GetMapping("/{id}")
public String byPath(@PathVariable("id") long id) {
    return "path:" + id;
}

@GetMapping(params = "id")
public String byQuery(@RequestParam("id") long id) {
    return "query:" + id;
}
```

These are methods inside a controller with `@RequestMapping("/api/books")`. They represent **two different mapping styles**. In the second example, `params = "id"` participates in **handler selection**; `@RequestParam("id")` handles **reading and converting the value** afterward.

A `@GetMapping` with `@RequestParam` **without** `params` can still be selected before the framework detects the missing parameter and returns a binding error. Distinguish handler-matching conditions from required-argument conditions during argument resolution.

### 4.2. Multiple Paths for the Same Handler

When two URLs share the same behavior, an array can be used:

```java
@GetMapping(path = {"/status", "/health"})
public String status() {
    return "ok";
}
```

These are two paths pointing to the same method. However, multiple URLs for one resource can complicate API documentation and caching; only use them when aliases or backward compatibility are genuinely needed.

## 5. `@PostMapping`: Sending Data to Process or Create Resources

`@PostMapping` is equivalent to `@RequestMapping(method = RequestMethod.POST)`. POST is commonly used when a client sends a body for the server to execute an action or create a new resource.

A typical example:

```java
@PostMapping(
    consumes = "application/json",
    produces = "application/json"
)
public ResponseEntity<Book> create(
        @RequestBody CreateBookRequest request) {
    Book created = service.create(request);
    return ResponseEntity
            .created(URI.create("/api/books/" + created.id()))
            .body(created);
}
```

The snippet above is **illustrative code**, assuming `service`, `Book`, `CreateBookRequest`, and imports exist. It does not run standalone. The complete project in section 8 replaces `service` with an in-memory store so learners can run it directly.

Each part carries a distinct meaning:

| Part | Role |
| --- | --- |
| `@PostMapping` | Restricts the handler to HTTP POST |
| `consumes = "application/json"` | Requires request `Content-Type` to support JSON |
| `@RequestBody` | Reads the body and uses a message converter to convert it into a Java object |
| `produces = "application/json"` | Declares the response format the handler can produce |
| `ResponseEntity.created(uri)` | Returns **201 Created** with a `Location` header |
| `body(created)` | Places the representation of the newly created resource into the response body |

Do not confuse **`@PostMapping`** with **`@RequestBody`**: POST is the HTTP method, whereas `@RequestBody` specifies reading input data from the body. POST can also receive form data or multipart payloads depending on the controller; JSON is not the only format.

For a successful operation, whether to return 200, 201, or 204 depends on the API contract. `@PostMapping` **does not automatically set status to 201**: if you return a plain Java object from `@RestController` without configuring status, the success response is normally 200. Use `@ResponseStatus(HttpStatus.CREATED)` or `ResponseEntity.created(...)` if you specifically want 201.

## 6. Attributes of `@RequestMapping` and Specialized Annotations

| Attribute | Example form | Used to |
| --- | --- | --- |
| `value` or `path` | `"/books/{id}"` | Combine HTTP paths |
| `method` | `RequestMethod.GET` | Restrict HTTP method; fixed by `@GetMapping`/`@PostMapping` |
| `params` | `"view=compact"`, `"!debug"` | Query parameter condition |
| `headers` | `"X-Client=mobile"` | Header condition |
| `consumes` | `"application/json"` | Media type the handler accepts from the request body |
| `produces` | `"application/json"` | Response media type the handler can produce |
| `name` | `"books.detail"` | Name the mapping for reference/inspection |

**`value` and `path` are aliases** representing the same path part, not two separate prefixes. With specialized annotations, `method` is already fixed: do not write `@GetMapping(method = ...)` because that attribute does not exist on `@GetMapping`.

### 6.1. Combining Class-Level and Method-Level Conditions

Normally, class paths combine with method paths, while conditions such as HTTP method, params, and headers combine according to `RequestMappingInfo` semantics. Specifically, **`consumes` and `produces` at the method level override the corresponding class-level declarations**, rather than simply accumulating.

Example:

```java
@RestController
@RequestMapping(
    path = "/api/documents",
    produces = "application/json"
)
public class DocumentController {

    @GetMapping("/{id}")
    public DocumentDto detail(@PathVariable long id) {
        return new DocumentDto(id, "doc");
    }

    @GetMapping(path = "/plain", produces = "text/plain")
    public String plain() {
        return "doc";
    }

    public record DocumentDto(long id, String name) {}
}
```

This is an **illustrative class**, requiring Spring configuration and a JSON converter when executed:

- `GET /api/documents/42`: the method inherits `produces=application/json`.
- `GET /api/documents/plain`: the method declares `produces=text/plain`, **overriding** the class value.
- The literal pattern `/plain` is typically more specific than `/{id}` when both can match.

If you restrict the HTTP method at the class level (e.g., GET only), method-level mappings underneath cannot freely expand to POST via `@PostMapping`; keep the shared prefix on the class and specific HTTP methods on each method to avoid confusion.

### 6.2. The `params` Condition

```java
@GetMapping(path = "/reports", params = "view=compact")
public String compact() {
    return "compact";
}

@GetMapping(path = "/reports", params = "!view")
public String defaultView() {
    return "default";
}
```

These are **two methods in the same controller**:

- `GET /reports?view=compact` selects `compact()`.
- `GET /reports` without `view` selects `defaultView()`.
- `GET /reports?view=full` satisfies neither condition; Spring may report a parameter condition error (usually 400) depending on configuration and other mappings.

`params="debug"` requires the parameter to be present; `params="!debug"` requires it to be absent; `params="mode=fast"` requires a specific value. This is a **routing condition**, not full validation of every Java argument value.

### 6.3. The `headers` Condition

```java
@GetMapping(
    path = "/client-info",
    headers = "X-Client=mobile"
)
public String mobileInfo() {
    return "mobile";
}
```

The handler matches only when the request includes the `X-Client` header satisfying the declared condition. For `Content-Type` and `Accept`, prefer `consumes`/`produces` because they express media types more clearly.

### 6.4. `Content-Type` vs `Accept`

| Header | Describes | Related condition |
| --- | --- | --- |
| `Content-Type: application/json` | Format of the **body sent by the client** | `consumes="application/json"` |
| `Accept: application/json` | Format of the **response the client accepts** | `produces="application/json"` |

A POST request with a JSON body generally needs a matching `Content-Type` for `@RequestBody` to parse it. When the client asks for an unsupported response format, `produces` or content negotiation can lead to HTTP 406. When the request body media type is unsupported, it can lead to HTTP 415.

Do not assume that sending `Accept: application/json` means the request body is JSON: `Accept` and `Content-Type` govern two opposite sides.

## 7. URL Matching and Selecting Specific Methods

### 7.1. Literals, URI Variables, and Wildcards

Suppose inside the same controller:

```java
@GetMapping("/featured")
public String featured() { return "featured"; }

@GetMapping("/{id}")
public String byId(@PathVariable String id) { return id; }
```

For `GET /api/books/featured`, the literal `/featured` takes precedence over the variable `/{id}` regardless of their declaration order in the Java file. For `GET /api/books/42`, the `/{id}` handler matches.

Spring MVC 6.x uses `PathPatternParser` by default. Some typical patterns:

- `/items/{id}`: captures one segment into variable `id`.
- `/items/{id:[0-9]+}`: matches only numeric segments per the declared regex.
- `/assets/*.png`: wildcard within a single segment.
- `/assets/**`: matches multiple segments at the **end** of a pattern.

With `PathPatternParser`, `**` and `{*variable}` may only appear at the end of a pattern. Do not use patterns like `/a/**/b` assuming they are always valid.

### 7.2. Do Not Rely on Method Order in Source Code

Spring MVC chooses mappings based on request conditions and specificity comparison rules. A method declared earlier does not automatically "win". If multiple methods have essentially identical mappings, the application may fail on startup; if two distinct mappings compete without resolving a single handler, ambiguous handler methods can occur.

An **intentionally invalid** example—do not put this into the runnable app in section 8:

```java
@GetMapping("/books/{id}")
public String one(@PathVariable String id) { return id; }

@GetMapping("/books/{id}")
public String two(@PathVariable String id) { return "other:" + id; }
```

Both methods have the exact same mapping. Renaming the Java methods will not resolve the conflict: you must change the API contract (path, HTTP method, or another meaningful condition).

### 7.3. Context Path Is Not Put in Annotations

When deploying the application under context path `/catalog`:

```text
External URL:   http://localhost:8080/catalog/api/books/42
Context path:                        /catalog
Class @RequestMapping:                       /api/books
Method @GetMapping:                                    /{id}
```

Controllers do not manually prepend `/catalog` to `@RequestMapping`. The context path is determined by deployment/HTTP server configuration. Adding that prefix into annotations can accidentally produce wrong URLs.

### 7.4. Trailing Slash Behavior

In modern Spring MVC, do not assume `/api/books` and `/api/books/` are always treated as the same path. Behavior depends on version and path-matching configuration. If an API must support both, decide on an explicit policy—redirect, alias definitions, or appropriate configuration—and verify it with tests.

## 8. Complete Example: GET and POST on the Same Resource

A Java 17 + Spring Boot **3.3.5** example using Spring MVC, embedded Tomcat, and Jackson via `spring-boot-starter-web`. Data is stored **in memory inside the controller** for easy experimentation; restarting the application loses books added after startup. This is a learning example, not a production persistence model.

### 8.1. File Structure

```text
book-routing-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/example/routing/
    │       ├── RoutingApplication.java
    │       └── BookController.java
    └── test/
        └── java/example/routing/
            └── BookControllerTest.java
```

### 8.2. Maven `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>book-routing-demo</artifactId>
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
```

The Spring Boot parent manages related dependency versions. You need JDK 17+ and Maven; the `mvn` commands below run in the directory containing `pom.xml`. Do not add `spring-boot-starter-webflux` to run this example.

### 8.3. Application Entry Point

File `src/main/java/example/routing/RoutingApplication.java`:

```java
package example.routing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RoutingApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoutingApplication.class, args);
    }
}
```

`@SpringBootApplication` enables auto-configuration and component scanning. Since the controller resides in the same `example.routing` package, Spring detects the bean when the application starts.

### 8.4. Complete Controller

File `src/main/java/example/routing/BookController.java`:

```java
package example.routing;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

    private final Map<Long, Book> books = new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong(2);

    public BookController() {
        books.put(1L, new Book(1L, "Java Fundamentals"));
        books.put(2L, new Book(2L, "Spring MVC"));
    }

    // GET /api/books
    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public List<Book> list() {
        return books.values().stream()
                .sorted(Comparator.comparingLong(Book::id))
                .toList();
    }

    // GET /api/books/featured
    @GetMapping(path = "/featured",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Book featured() {
        return books.get(1L);
    }

    // GET /api/books/{id}
    @GetMapping(path = "/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Book> find(@PathVariable("id") long id) {
        Book book = books.get(id);
        return book == null
                ? ResponseEntity.notFound().build()
                : ResponseEntity.ok(book);
    }

    // POST /api/books
    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Book> create(@RequestBody CreateBook request) {
        long id = nextId.incrementAndGet();
        Book book = new Book(id, request.title());
        books.put(id, book);

        return ResponseEntity
                .created(URI.create("/api/books/" + id))
                .body(book);
    }

    public record Book(long id, String title) {}
    public record CreateBook(String title) {}
}
```

**Routes registered by Spring:**

| HTTP request | Handler method | Typical result |
| --- | --- | --- |
| `GET /api/books` | `list()` | JSON array of books, sorted by ID |
| `GET /api/books/featured` | `featured()` | JSON for book ID 1 |
| `GET /api/books/1` | `find(1)` | HTTP 200, JSON for book ID 1 |
| `GET /api/books/999` | `find(999)` | HTTP 404 because business logic finds no book |
| `POST /api/books` with JSON | `create(...)` | HTTP 201, `Location` and JSON for the new book |

Mapping analysis:

- The `/api/books` prefix comes from the **class**, while `/featured` and `/{id}` come from **methods**.
- `@GetMapping` and `@PostMapping` distinguish **two behaviors on the same path `/api/books`**.
- `/featured` has higher specificity than `/{id}`; requests do not attempt to parse `"featured"` as a `long`.
- For `/api/books/999`, the handler **is found**, but the business method returns 404; this differs from a missing route error.
- `create` reads a JSON body via `@RequestBody` and returns `201 Created` with `Location: /api/books/3` for the first creation request.
- `ConcurrentHashMap` and `AtomicLong` help the example avoid basic concurrent data-access issues when multiple requests arrive simultaneously; they do **not** replace real persistence, transactions, validation, or business rules.

### 8.5. Run the App and Send Requests

In `book-routing-demo`, run tests first, then start the web server:

```bash
mvn test
mvn spring-boot:run
```

The second command keeps the terminal running; open another terminal. With default configuration and port 8080 free, send:

```bash
curl -s http://localhost:8080/api/books
```

Expected body:

```json
[{"id":1,"title":"Java Fundamentals"},{"id":2,"title":"Spring MVC"}]
```

Look up by ID:

```bash
curl -s http://localhost:8080/api/books/1
```

Body:

```json
{"id":1,"title":"Java Fundamentals"}
```

Check the literal path `/featured`:

```bash
curl -s http://localhost:8080/api/books/featured
```

The body is also book ID 1. This example shows Spring picks `featured()` instead of trying to convert `featured` into a `long` for `find(...)`.

Send POST to create a book (POSIX shell syntax):

```bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"title":"HTTP and REST"}'
```

Expected response status and headers (omitting server-dependent headers):

```http
HTTP/1.1 201
Location: /api/books/3
Content-Type: application/json

{"id":3,"title":"HTTP and REST"}
```

**ID 3** assumes this is the first book created since startup. If you POSTed earlier, `AtomicLong` continues incrementing, so the ID will differ. The `Location` line here uses a relative path valid for the example; with a gateway, context path, reverse proxy, or multiple domains, choose URI construction according to real deployment.

Afterward:

```bash
curl -s http://localhost:8080/api/books/3
```

Body after the first creation:

```json
{"id":3,"title":"HTTP and REST"}
```

The example does not apply bean validation to the `title` field; production needs checks for content, length, uniqueness, authorization, and durable storage as required. Do not copy the in-memory store as a real persistence layer.

### 8.6. Same Path, Different HTTP Methods

Both endpoints share **path `/api/books`**:

```text
GET  /api/books -> list()
POST /api/books -> create(...)
```

`GET /api/books` does not accidentally call `create`; `POST /api/books` does not call `list`. If you try:

```bash
curl -i -X PUT http://localhost:8080/api/books
```

In the demo, Spring MVC has a matching path but does not support PUT on that endpoint, so the result is typically **405 Method Not Allowed**. This differs from **404 Not Found**, which usually indicates no matching route for the path or a business not-found response.

Note that `HEAD` can be supported automatically when GET exists, and `OPTIONS` can be handled by Spring based on registered methods. Do not claim "strictly GET/POST only" while ignoring this HTTP infrastructure rule.

## 9. Testing Mappings with `MockMvc`

Add `src/test/java/example/routing/BookControllerTest.java`:

```java
package example.routing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(BookController.class)
class BookControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void combinesClassAndMethodMappings() throws Exception {
        mvc.perform(get("/api/books/featured"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(1))
                .andExpect(jsonPath("$.title").value("Java Fundamentals"));

        mvc.perform(get("/api/books/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(1));
    }

    @Test
    void postCreatesBookWithLocation() throws Exception {
        mvc.perform(post("/api/books")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"HTTP and REST\"}"))
                .andExpect(status().isCreated())
                .andExpect(header().string("Location", "/api/books/3"))
                .andExpect(jsonPath("$.id").value(3))
                .andExpect(jsonPath("$.title").value("HTTP and REST"));
    }

    @Test
    void rejectsUnsupportedHttpMethod() throws Exception {
        mvc.perform(put("/api/books"))
                .andExpect(status().isMethodNotAllowed());
    }
}
```

`@WebMvcTest(BookController.class)` creates an **MVC test slice**: it tests the controller, route resolution, message conversion, and required MVC configuration without starting a real TCP HTTP server. `MockMvc` sends requests through the servlet testing pipeline and asserts HTTP status, headers, and JSON responses.

Because POST is tested only once in the class, the first created ID is expected to be 3. For real tests with multiple write operations or parallel execution, do not rely on shared state across test methods; isolate state, mock services, or reset data.

Run:

```bash
mvn test
```

All three test methods are expected to pass if the project is created properly, dependencies are downloaded, and the environment does not interfere. This article states the **expected outcome based on the code**, not a claim that tests have already been run on every machine.

## 10. Common Mistakes When Using Mappings

### 10.1. Putting Multiple Mapping Annotations on the Same Method

**Wrong:**

```java
@GetMapping("/x")
@PostMapping("/x")
public String both() {
    return "x";
}
```

`@GetMapping` and `@PostMapping` are both composed `@RequestMapping` annotations. Spring does not support stacking multiple such mapping annotations on the **same element**; it may log a warning and recognize only one mapping. To support both GET and POST, use `@RequestMapping(path="/x", method={RequestMethod.GET, RequestMethod.POST})`, or split into two methods with separate contracts.

### 10.2. Assuming Class-Level Mapping Creates an Endpoint by Itself

`@RequestMapping("/api")` on a class is only **shared metadata**. You still need a corresponding method recognized by Spring; if the class is not a controller bean or lacks method mappings, no desired endpoints will exist.

### 10.3. Wrong HTTP Method

`@GetMapping("/save")` can let clients "save" via GET, but mutating data over GET violates safe HTTP expectations and can be triggered by prefetchers, caches, or crawlers. Choose `@PostMapping` for creating/processing actions, `@PutMapping` for full replacement updates, `@PatchMapping` for partial updates, and `@DeleteMapping` for deletions per your API contract.

### 10.4. Confusing `@PathVariable` and `@RequestParam`

`/books/42` differs from `/books?id=42`. Writing `@GetMapping("/{id}")` and testing `/books?id=42` will not match the path pattern. Define an endpoint matching the actual parameter style.

### 10.5. Duplicate Mappings

Two methods both having `@GetMapping("/api/books/{id}")` in the same handler registry can cause an **ambiguous mapping at application startup**. Renaming the Java method is not enough; differentiate by path, HTTP method, or meaningful request conditions.

### 10.6. 404 vs 405, 406, and 415

| Status | Typical possibility | Check |
| --- | --- | --- |
| 404 | No mapping for the path or resource does not exist | Class/method prefix, context path, path variable, controller scan, and code returning 404 |
| 405 | Path has a handler mapping, but HTTP method is not accepted | GET/POST/PUT/DELETE, `Allow` header |
| 406 | Client only accepts a response media type different from `produces` | `Accept` and message converters |
| 415 | Request body `Content-Type` is unsupported | `consumes` and message converters |
| 400 | Malformed JSON body, missing required param, type conversion, or params condition | `@RequestBody`, `@RequestParam`, `@PathVariable`, request payload |
| 500 / startup failure | Duplicate mapping registration, bean error, or handler runtime error | Startup logs and root cause |

An HTTP status **does not prove a single cause**, because exception handlers, security, and other layers can alter the outcome. Inspect the request, mapping registry, converters, and server logs together.

### 10.7. Trailing Slash Defaults and Path Matching

`GET /api/books` is not always treated identically to `GET /api/books/`. Spring 6.x changed several defaults compared to older generations. If an API needs both forms, test explicitly rather than relying on habits from older versions.

### 10.8. Putting an Overly Narrow `method` on Class-Level `@RequestMapping`

For example, putting `@RequestMapping(path="/api/books", method=GET)` on a class and then writing `@PostMapping` inside it creates conflicting HTTP method restrictions. Common practice: keep the **path prefix** on the class, and specify GET/POST on each method.

### 10.9. Mixing Up Stacks for Mappings

Spring MVC and WebFlux share some annotations from the same package, yet their dispatching runtimes differ. For example, `spring-boot-starter-web` builds a traditional MVC server, whereas `spring-boot-starter-webflux` builds a reactive web stack when configured by Boot. Seeing `@GetMapping` in source code alone is not enough to tell whether it is MVC or WebFlux.

## 11. Endpoint Design Best Practices

1. **Prefix by resource**: `/api/books`, `/api/orders`, and separate operations using HTTP methods or sensible sub-resource paths.
2. **Use specialized annotations on methods**: `@GetMapping`, `@PostMapping`… so method constraints are obvious at a glance.
3. **Do not put verbs into GET to perform writes**: e.g., `GET /createBook` is an API contract prone to unintended side effects.
4. **Return meaningful HTTP statuses**: successful GET is usually 200; resource creation via POST is usually 201 with `Location`; missing resources may return 404; mismatched bodies/methods may return 400/405/415/406.
5. **Separate routing from validation**: handlers are selected by path/method/params/headers/media type; body validation and business rules are handled afterward by their respective mechanisms.
6. **Test primary routes and edge cases**: same path different methods, literal paths alongside path variables, media type mismatches, invalid URIs, missing data.
7. **Avoid overly broad mappings**: `/**` or method-unrestricted mappings can unintentionally match extra requests; constrain them intentionally.
8. **Keep business logic out of controllers in real projects**: the in-memory demo in section 8 is for easy observation; production systems should use services/repositories, transactions, validation, and proper security.

## 12. Exercises and Self-Check

### Exercise 1 — Predict the Endpoint

Given:

```java
@RestController
@RequestMapping("/students")
class StudentController {
    @GetMapping
    String all() { return "all"; }

    @GetMapping("/{id}")
    String one(@PathVariable String id) { return id; }

    @PostMapping
    String add() { return "created"; }
}
```

Identify the handler for `GET /students`, `GET /students/15`, `POST /students`, and `PUT /students`. Answer: respectively `all()`, `one("15")`, `add()`; PUT has no supporting handler and typically receives 405.

### Exercise 2 — Convert Annotations

Rewrite `@RequestMapping(path="/products/{id}", method=RequestMethod.GET)` using the shorthand annotation. **Answer:** `@GetMapping("/products/{id}")`.

Conversely, rewrite `@PostMapping(path="/products", consumes="application/json")` as `@RequestMapping`. **Answer:**

```java
@RequestMapping(
    path = "/products",
    method = RequestMethod.POST,
    consumes = "application/json"
)
```

This is an **annotation fragment**, used on a controller method.

### Exercise 3 — Analyze Request Body

A method `@PostMapping(consumes="application/json", produces="application/json")` accepts `@RequestBody`. The client sends `Content-Type: text/plain` with a JSON-formatted string. Why is "text that looks like JSON" not enough? **Hint:** `consumes` checks the request media type, not merely the characters inside the body.

### Exercise 4 — Literal vs URI Variable

A controller has `@GetMapping("/new")` and `@GetMapping("/{id}")`. Explain why `GET /new` normally selects the literal route, even when the method for variable `id` appears earlier in the file.

### Exercise 5 — Same Path GET and POST

Design a small API:

- `GET /notes`: read the list.
- `POST /notes`: accept JSON and add a note.
- `GET /notes/{id}`: read a single note.
- Successful POST: return 201 and `Location`.

Use one `@RequestMapping("/notes")` on the class and specialized annotations on the three methods. Write a `MockMvc` test proving GET does not invoke POST and POST does not return the list.

### Review Questions

- **Where can `@RequestMapping` be placed?** — On classes and methods; class level usually provides shared prefix/conditions, method level adds endpoint-specific conditions.
- **How does `@GetMapping` differ from `@RequestMapping`?** — It is a specialized composed annotation with `method=GET`.
- **Does `@PostMapping` automatically return 201?** — No; the controller must declare the status or return an appropriate `ResponseEntity`.
- **Are two methods with the same path—one GET and one POST—valid?** — Yes, because HTTP method is part of the mapping condition.
- **Is `params` the same as `@RequestParam`?** — No; `params` restricts route selection, whereas `@RequestParam` extracts/converts arguments once the handler is invoked.
- **Which header does `consumes` rely on?** — Typically the request `Content-Type`.
- **Which header does `produces` relate to?** — `Accept` and response content negotiation.
- **Does Spring choose methods based on line position in the file?** — No; it relies on request conditions and specificity.

## 13. Official References

- Spring MVC Mapping Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring MVC Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webmvc/controller.html
- `@RequestMapping` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/bind/annotation/RequestMapping.html
- `@GetMapping` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/bind/annotation/GetMapping.html
- `@PostMapping` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/bind/annotation/PostMapping.html
- `MockMvc`: https://docs.spring.io/spring-framework/reference/testing/mockmvc.html

**Key takeaway:** Class-level `@RequestMapping` groups shared paths and conditions; method-level `@GetMapping`/`@PostMapping` indicate **which operation handles each HTTP method**. Spring MVC combines path, HTTP method, and remaining conditions to select a handler. Only after selection do binding, converters, and controller code produce the response.
