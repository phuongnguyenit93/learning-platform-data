# ResponseEntity: Controlling Status, Headers, and Body in Spring MVC

> **Scope:** Spring Web MVC (Servlet stack), Java 17+ examples with Spring Boot 3.x/Spring Framework 6.x. The main topic is `org.springframework.http.ResponseEntity<T>`: a controller return type representing the **HTTP status code, header set, and body** in a single value. This article covers builder methods, HTTP semantics, content negotiation, handling resource success/failure, bodyless responses, files, and caching, then applies them to a runnable REST controller.

## 1. Why Does a REST Endpoint Need Full Response Control?

An API does not only send JSON data; it also needs to tell the client whether an operation **succeeded, created a new resource, was not found, was deleted, or requires correction**. An HTTP response has three important parts:

```http
HTTP/1.1 201 Created
Location: /api/books/11
Content-Type: application/json
X-Resource-Type: book

{"id":11,"title":"Clean Code","author":"Robert Martin"}
```

- **Status** `201 Created`: indicates the server created a resource.
- **Header** `Location`: provides the URI of the newly created resource. `Content-Type` describes the body format; other headers add metadata.
- **Body**: the resource content or error message, which may be absent depending on the case.

If a method simply returns `Book` from a `@RestController`, Spring typically returns `200 OK` and serializes the object to JSON via a converter. That works well for a simple GET, but cannot sufficiently express `201`, `204`, `404`, custom headers, or cache semantics.

**`ResponseEntity<T>` bundles all three parts into a single explicit return value.** It extends `HttpEntity<T>` (which holds headers and body) and adds status. In Spring MVC, the body is typically written by an appropriate `HttpMessageConverter`; `ResponseEntity` does not serialize JSON itself by string concatenation.

## 2. Starting with Basic Syntax

```java
@GetMapping("/hello")
public ResponseEntity<String> hello() {
    return ResponseEntity.ok("Xin chào");
}
```

In a `@RestController`, this example returns `200 OK` with the string body `Xin chào`. The data can be a `String`, DTO, `List<Dto>`, `byte[]`, `Resource`, or any other type supported by a converter.

Three ways to achieve the same status + headers + body:

```java
// 1. Builder API: usually the most readable.
ResponseEntity<String> first = ResponseEntity
        .status(HttpStatus.ACCEPTED)
        .header("X-Job-Id", "j-42")
        .body("queued");

// 2. Constructor: useful when you already have HttpHeaders.
HttpHeaders headers = new HttpHeaders();
headers.set("X-Job-Id", "j-42");
ResponseEntity<String> second = new ResponseEntity<>(
        "queued", headers, HttpStatus.ACCEPTED);

// 3. Quickly create a 200 result.
ResponseEntity<String> third = ResponseEntity.ok("queued");
```

These are **illustrative statements** placed inside a Java method, not a standalone Java program. The types require importing `org.springframework.http.ResponseEntity`, `HttpHeaders`, `HttpStatus`. Both `first` and `second` have status 202, header `X-Job-Id`, and body `queued`; `third` returns 200 without that header.

Notable builder methods:

| Usage | Default or target HTTP status | Returns body? |
| --- | --- | --- |
| `ResponseEntity.ok(body)` | `200 OK` | Yes |
| `ResponseEntity.ok().header(...).body(body)` | `200 OK` | Yes |
| `ResponseEntity.status(HttpStatus.ACCEPTED).body(body)` | `202 Accepted` | Yes |
| `ResponseEntity.created(uri).body(body)` | `201 Created` and `Location` | Yes |
| `ResponseEntity.noContent().build()` | `204 No Content` | No |
| `ResponseEntity.badRequest().body(error)` | `400 Bad Request` | Yes |
| `ResponseEntity.notFound().build()` | `404 Not Found` | No |
| `ResponseEntity.status(HttpStatus.CONFLICT).body(error)` | `409 Conflict` | Yes |
| `ResponseEntity.status(HttpStatus.SEE_OTHER).location(uri).build()` | `303 See Other` and `Location` | No in example |
| `ResponseEntity.of(optional)` | `200` if present, `404` if empty | Depends on Optional |

The methods above represent **different response shapes**. Do not pick a status arbitrarily: the code must match the operation outcome and API contract.

### 2.1. `ResponseEntity<T>` Is a Generic Type

```java
ResponseEntity<BookDto> bookResponse;
ResponseEntity<List<BookDto>> booksResponse;
ResponseEntity<String> textResponse;
ResponseEntity<Void> noBodyResponse;
ResponseEntity<byte[]> binaryResponse;
```

The generic `T` describes the body type at compile time. It helps the IDE, code authors, and tests understand the return contract. `ResponseEntity<Void>` is especially useful for endpoints returning a status/headers with no body, such as `204 No Content`. If a method needs to return `BookDto` or `ApiError` depending on the branch, you can return `ResponseEntity<?>` or design a consistent exception handler/error abstraction; do not force every response into raw strings.

## 3. Status Codes and Semantically Correct REST Behavior

| Code | Typical semantics | Example |
| --- | --- | --- |
| `200 OK` | Read or update succeeded and returns a representation | GET book, PUT returning object |
| `201 Created` | A new resource was created | POST creating a book with `Location` |
| `202 Accepted` | Accepted for processing, not necessarily finished | Enqueueing a job |
| `204 No Content` | Succeeded and sends no body | Successful DELETE |
| `301/302/303/307/308` | Redirects to another URI, each with different method rules | `303 See Other` after POST |
| `304 Not Modified` | Cache condition indicates no need to send representation | Conditional GET/HEAD |
| `400 Bad Request` | Request invalid in syntax/input | Malformed JSON |
| `401 Unauthorized` | Lacks valid authentication; often includes a challenge when applicable | Authentication required |
| `403 Forbidden` | Identity is not allowed to perform the operation | Missing permissions |
| `404 Not Found` | No matching resource or existence is not disclosed | GET with nonexistent ID |
| `409 Conflict` | Resource state conflict | Duplicate unique code |
| `412 Precondition Failed` | HTTP precondition failed | `If-Match`/ETag mismatch |
| `422 Unprocessable Content` | Syntactically valid body but content cannot be processed per policy | Business validation if API chooses 422 |
| `500 Internal Server Error` | Unhandled server error not mapped to a specific response | Do not return 200 for system errors |

Note that `202` **does not mean the task has succeeded**; for asynchronous processing, return a job ID and provide a status-tracking API where appropriate. `204`/`304` have no response body per HTTP semantics: use `build()`, and do not try to add a JSON body. For input errors, standardize on returning 400 or 422 and how errors are represented; Spring has default error handling that may differ from a specific API design.

## 4. Builder API: How Are the Three Parts Configured?

### 4.1. Predefined or Arbitrary Statuses

```java
ResponseEntity<String> ok = ResponseEntity.ok("done");
ResponseEntity<String> accepted = ResponseEntity
        .status(HttpStatus.ACCEPTED)
        .body("processing");
ResponseEntity<String> limited = ResponseEntity
        .status(429)
        .header("Retry-After", "30")
        .body("try later");
```

`ResponseEntity.status(...)` accepts valid status codes; `HttpStatus` constants express intent clearly. In Spring Framework 6+, `HttpStatusCode` is the status abstraction; compatible overloads/builders vary across versions. Choose `HttpStatus` or an integer to keep illustrative code simple.

### 4.2. Custom Headers

```java
return ResponseEntity.ok()
        .header("X-Trace-Id", traceId)
        .header("X-API-Version", "1")
        .body(dto);
```

Headers must be constructed from trusted or validated data; do not arbitrarily reflect client-supplied strings into headers. `X-Trace-Id` is an example of metadata and does not serve an authentication role. If JavaScript running from another origin needs to read a custom response header, besides setting that header you must also configure CORS `Access-Control-Expose-Headers` accordingly (when policy permits).

### 4.3. Using Convenience Builders for Standard Headers

```java
return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .cacheControl(CacheControl.noStore())
        .header("X-Source", "catalog")
        .body(bookDto);
```

- `contentType(MediaType.APPLICATION_JSON)` sets `Content-Type: application/json`.
- `cacheControl(CacheControl.noStore())` instructs caches not to store this representation.
- `header("X-Source", "catalog")` adds a custom header.
- `body(bookDto)` finishes the builder and creates `ResponseEntity<BookDto>`.

Other convenience builders include `location(URI)`, `contentLength(long)`, `allow(HttpMethod...)`, `eTag(String)`, `lastModified(...)`, and `headers(HttpHeaders)` as needed. Do not guess `Content-Length` for converter-generated JSON because serialization can produce a different byte count than character length; let the server determine it where appropriate.

### 4.4. HTTP Body Still Needs a Converter

`ResponseEntity<String>` typically uses `StringHttpMessageConverter`; `ResponseEntity<BookDto>` typically uses the Jackson JSON converter when the media type is JSON; `ResponseEntity<byte[]>` uses the byte array converter; `ResponseEntity<Resource>` uses the appropriate resource converter. Writing:

```java
ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body("not valid JSON");
```

does not turn the string `not valid JSON` into valid JSON. The media type is a **format declaration**, not an instruction to re-serialize a String. Return a DTO object instead of concatenating JSON strings so the converter serializes it properly.

## 5. Creating a Resource: `201 Created` and `Location`

A POST that creates a book typically follows this flow:

1. Receive a request DTO containing fields the client is allowed to send.
2. Validate input and creation permissions.
3. Generate a new ID and save successfully.
4. Return `201 Created`; the `Location` header points to the book's URI; the body can be the newly created representation.

Example method:

```java
@PostMapping("/books")
public ResponseEntity<BookDto> create(@RequestBody CreateBookRequest input) {
    BookDto saved = service.create(input); // Service provided by the application
    URI uri = URI.create("/books/" + saved.id());

    return ResponseEntity.created(uri).body(saved);
}
```

This is an **illustrative** method depending on undeclared `BookDto`, `CreateBookRequest`, and `service`; see the standalone program in section 10 to run immediately. In this example, `Location` is a valid relative reference. If an absolute URL is needed or the app has a context path/proxy, build the URI using trusted configuration and external base URL policy rather than blindly trusting forwarded headers from the client.

Do not return 201 when the resource has not been created yet, such as when a job is only queued: consider `202 Accepted` and a tracking URI. Do not equate `Location` with an internal file path on the server.

## 6. GET: 200 with Body, 404 When Absent

For a GET that returns an object when present and 404 when absent:

```java
@GetMapping("/books/{id}")
public ResponseEntity<BookDto> get(@PathVariable long id) {
    return service.findById(id)
            .map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
}
```

This is also an **illustrative method**. `service.findById(id)` is assumed to return `Optional<BookDto>`. A shorter option:

```java
@GetMapping("/books/{id}")
public ResponseEntity<BookDto> get(@PathVariable long id) {
    return ResponseEntity.of(service.findById(id));
}
```

`ResponseEntity.of(Optional<T>)` returns status 200 with the body when the Optional has a value, otherwise 404 with no body. This approach is simple, though it does not return a custom error DTO for 404. In a real API, choose a consistent error strategy (exception handler, `ProblemDetail`, or a dedicated error body) instead of inventing a different shape per endpoint.

### 6.1. When Does 404 Have a Body?

```java
if (book == null) {
    return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(new ApiError("Book not found"));
}
```

Returning a JSON body describing the error is valid as long as the status remains 404. When a method has two different body types, declare `ResponseEntity<?>` or use a unified error response model. Never return `200 OK` with `{"error":"not found"}` for a situation that should be 404 just to "avoid errors" on the client side.

## 7. PUT, PATCH, DELETE: Choosing 200, 204, 404 by Outcome

For an update operation:

```java
@PutMapping("/books/{id}")
public ResponseEntity<BookDto> replace(
        @PathVariable long id,
        @RequestBody UpdateBookRequest input) {
    Optional<BookDto> updated = service.replace(id, input);
    return updated.map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
}
```

This is a non-standalone service example. Return `200` if you want to send the representation after updating; `204` if the update succeeded and no body is needed; `404` if the record does not exist and the API chooses not to create it via PUT.

DELETE:

```java
@DeleteMapping("/books/{id}")
public ResponseEntity<Void> delete(@PathVariable long id) {
    boolean existed = service.deleteIfExists(id);
    return existed
            ? ResponseEntity.noContent().build()
            : ResponseEntity.notFound().build();
}
```

An API can choose idempotent DELETE semantics by policy: repeating a delete causes no unintended side effects, while the status on subsequent calls **may be 204 or 404** depending on the contract. Do not treat those two statuses as semantically identical; document the choice clearly to clients.

**Be strict with `204`:** the body must be empty. Do not write `ResponseEntity.noContent().build()` and then try to attach a JSON success message. If a body is needed, use an appropriate status such as 200.

## 8. Structured Error Information: `ProblemDetail` and Status

Spring Framework 6 provides `org.springframework.http.ProblemDetail` for Problem Details error responses (now RFC 9457):

```java
@GetMapping("/inventory/{id}")
public ResponseEntity<ProblemDetail> inventory(@PathVariable long id) {
    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "Không tìm thấy sản phẩm " + id);
    problem.setTitle("Product not found");
    return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(problem);
}
```

This is an **illustrative method** inside a controller and will not run with the demo unless copied into an appropriate class. In Spring MVC ecosystems supporting `ProblemDetail`, the response can be rendered as `application/problem+json`. Ensure the HTTP status and `problem.status` are consistent; do not set body status 404 and return HTTP 200. Do not expose stack traces, SQL, API keys, or internal details in error bodies sent to clients.

If Spring MVC and the application already use `@RestControllerAdvice` / `@ExceptionHandler` to standardize errors, not every method needs to build an error body manually. With validation, Spring may throw an exception before the controller method runs; handle it in an appropriate advice rather than assuming every error passes through the method's `if` branches.

## 9. Important Headers in REST Responses

### 9.1. `Content-Type` and `Accept`

The request header `Accept: application/json` indicates the client wants JSON. `@GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)` restricts the representation the route allows. If the client only accepts XML and the server has no XML representation, it typically returns **406 Not Acceptable**.

The response header `Content-Type: application/json` indicates the **actual body** is JSON formatted. Use the proper DTO/converter rather than changing the header to "trick" the client. Request `Content-Type`, by contrast, describes the **incoming body**, e.g., POST `application/json`; if the route's `consumes` does not match, it may return **415 Unsupported Media Type**.

### 9.2. `Location`

`Location` is common with `201 Created` or redirect responses. With `201` it denotes the URI related to the new resource; with `303 See Other` it directs the client to another resource per HTTP semantics. Construct URIs from normalized data and a trusted host policy to prevent open redirects or host-header injection.

### 9.3. `Cache-Control`, `ETag`, `Last-Modified`

A resource GET can return:

```java
return ResponseEntity.ok()
        .cacheControl(CacheControl.maxAge(60, TimeUnit.SECONDS).cachePrivate())
        .eTag("\"book-v7\"")
        .body(book);
```

This is an **illustrative snippet**: it requires `java.util.concurrent.TimeUnit` and `org.springframework.http.CacheControl`; `book` must be declared. `ETag` is a validator for a **specific representation version**, so do not set a fixed tag if the content can change. The `eTag(...)` builder accepts valid quoted values or handles quoting per the Spring version's rules.

When a client sends a conditional request with `If-None-Match` or `If-Modified-Since`, Spring MVC can evaluate the validator and return **304 Not Modified** (no body) if conditions match, depending on how the request is handled. `ETag` optimizes network transfer; `Cache-Control` defines caching policy. `Cache-Control: no-store` suits sensitive responses that must not be stored; `private` does not guarantee absolute data security.

For conditional updates, `If-Match` and `412 Precondition Failed` can prevent lost updates, but **putting an ETag on GET alone does not automatically guarantee concurrency**. You must handle preconditions/versions on PUT/PATCH/DELETE and test conflict cases. Spring supports HTTP conditional requests at the MVC layer; persistence still needs its own concurrency mechanism.

### 9.4. `Content-Disposition` for Files

```java
return ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .header(HttpHeaders.CONTENT_DISPOSITION,
                "attachment; filename=\"example.txt\"")
        .body(resource);
```

This snippet uses `org.springframework.core.io.Resource` and `HttpHeaders`; Spring picks an appropriate resource converter. Do not use a client-supplied filename directly in the header without safe sanitization. Do not load huge files entirely into a byte array when `Resource`/streaming can be used and download authorization can be enforced.

## 10. Complete Example: Runnable REST Book API with Java 17+ and Spring Boot 3.x

This example uses **in-memory storage** so you can observe exact statuses, headers, and bodies without depending on a database or security setup. Data resets on restart. Create a Spring Boot 3.x project on [Spring Initializr](https://start.spring.io/) with Java 17+ and the **Spring Web** dependency. Use the Maven wrapper generated by Initializr.

Put all of the code below into `src/main/java/com/example/demo/DemoApplication.java`. The file has one public class and top-level package-private types, valid on Java 17:

```java
package com.example.demo;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.Resource;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

record Book(long id, String title, String author) {
}

record BookInput(String title, String author) {
}

record ApiError(String message) {
}

@RestController
@RequestMapping("/api/books")
class BookController {

    private final Map<Long, Book> books = new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong(11);

    BookController() {
        books.put(10L, new Book(10, "Java Basics", "Minh"));
    }

    @GetMapping(path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> get(@PathVariable("id") long id) {
        Book book = books.get(id);
        if (book == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(new ApiError("Book " + id + " not found"));
        }

        return ResponseEntity.ok()
                .header("X-Book-Id", Long.toString(id))
                .cacheControl(CacheControl.noStore())
                .body(book);
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Book> create(@RequestBody BookInput input) {
        long id = nextId.getAndIncrement();
        Book saved = new Book(id, input.title(), input.author());
        books.put(id, saved);

        URI location = URI.create("/api/books/" + id);
        return ResponseEntity.created(location)
                .header("X-Resource-Type", "book")
                .body(saved);
    }

    @PutMapping(path = "/{id}",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Book> replace(
            @PathVariable("id") long id,
            @RequestBody BookInput input) {

        if (!books.containsKey(id)) {
            return ResponseEntity.notFound().build();
        }

        Book saved = new Book(id, input.title(), input.author());
        books.put(id, saved);
        return ResponseEntity.ok(saved);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable("id") long id) {
        if (books.remove(id) == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.noContent().build();
    }

    @GetMapping(path = "/text",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> text() {
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(
                        "text/plain;charset=UTF-8"))
                .body("Book API ready");
    }

    @GetMapping(path = "/download",
            produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public ResponseEntity<Resource> download() {
        Resource file = new ByteArrayResource(
                "BOOK\n".getBytes(StandardCharsets.UTF_8));

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"book.txt\"")
                .body(file);
    }

    @GetMapping("/redirect")
    public ResponseEntity<Void> redirect() {
        return ResponseEntity.status(HttpStatus.SEE_OTHER)
                .location(URI.create("/api/books/10"))
                .build();
    }
}
```

**Design explanation:**

- `get` returns 200/JSON + `X-Book-Id` and `Cache-Control: no-store` when found; returns 404 + `ApiError` if absent.
- `create` allocates a new ID, stores it in the map, and returns 201 + `Location` + `X-Resource-Type` + JSON body. `URI.create("/api/books/" + id)` uses a **relative URI** suitable for a demo with an empty context path; apps with a prefix/proxy should build URIs accordingly.
- `replace` only updates existing IDs, returning 200 + the new representation or 404 with no body.
- `delete` returns 204 with no body when deleted; calling it again receives 404 per the demo's policy.
- `text` demonstrates that `ResponseEntity<String>` can return text/plain; `download` uses `ResponseEntity<Resource>` to send a file; `redirect` returns 303 + Location.
- `ConcurrentHashMap` and `AtomicLong` serve a **single-process demo**; they are not persistence, transactions, authorization, or a production concurrency solution.
- The demo lacks input validation; real code needs request DTOs with constraints, Bean Validation, authorization checks, and domain exception handling.

### 10.1. Running the Program

From the Maven project root generated by Spring Initializr:

```bash
# Linux / macOS
./mvnw spring-boot:run

# Windows PowerShell or Command Prompt
mvnw.cmd spring-boot:run
```

When the application starts, the server listens on `http://localhost:8080` by default (unless `server.port` or context path was changed). Run each group of requests in order on a freshly started state to compare results accurately.

### 10.2. Successful GET: 200 + JSON + Headers

```bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/books/10
```

Important parts of the response:

```http
HTTP/1.1 200
Content-Type: application/json
X-Book-Id: 10
Cache-Control: no-store

{"id":10,"title":"Java Basics","author":"Minh"}
```

Header order, spacing, and container-added headers may differ; the JSON body is expected to have three fields matching the record structure. `-i` shows status and headers; `Content-Length` may be decided by the server.

### 10.3. Nonexistent GET: 404 + Error JSON

```bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/books/999
```

Status **404 Not Found**; body from `ApiError`:

```json
{"message":"Book 999 not found"}
```

If the client sends an `Accept` header incompatible with `produces=application/json`, Spring may handle 406 before calling the controller; do not assume 404 is guaranteed for every header.

### 10.4. POST Creation: 201 + Location + JSON

```bash
curl -i -X POST http://localhost:8080/api/books \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data-binary '{"title":"Clean Code","author":"Robert Martin"}'
```

On the first POST after startup, the server assigns ID `11` and returns:

```http
HTTP/1.1 201
Location: /api/books/11
X-Resource-Type: book
Content-Type: application/json

{"id":11,"title":"Clean Code","author":"Robert Martin"}
```

Fields/headers may be formatted/ordered differently depending on runtime; status, Location, custom headers, and JSON content are what to verify. Next, `GET /api/books/11` can return the newly created object. If you POST again, the ID increments; do not assume the ID is always `11`.

### 10.5. PUT Replacement: 200 or 404

```bash
curl -i -X PUT http://localhost:8080/api/books/10 \
  -H 'Content-Type: application/json' \
  --data-binary '{"title":"Spring MVC","author":"Lan"}'
```

Status **200 OK**, body:

```json
{"id":10,"title":"Spring MVC","author":"Lan"}
```

If you PUT to ID `999` (not yet created), the demo returns **404 with no body**. This is the endpoint's policy: many APIs may choose to have PUT create a resource at the target URI if the contract allows; in that case logic and status must be designed differently.

### 10.6. DELETE: 204 Completely Without a Body

```bash
curl -i -X DELETE http://localhost:8080/api/books/10
```

First delete while book `10` exists: status **204 No Content**, no body. Second delete: **404 Not Found**, no body per the demo code. Running GET `/api/books/10` again after DELETE returns 404 with `ApiError`.

### 10.7. Text, File, and Redirect

Text:

```bash
curl -i http://localhost:8080/api/books/text
```

Status 200; header `Content-Type: text/plain;charset=UTF-8`, body:

```text
Book API ready
```

File:

```bash
curl -i http://localhost:8080/api/books/download
```

Status 200; `Content-Type: application/octet-stream`, `Content-Disposition: attachment; filename="book.txt"`, body is exactly **5 bytes** consisting of `BOOK` and a newline. Save with `curl -o book.txt http://localhost:8080/api/books/download` to inspect the file separately instead of using `-i` when you want clean binary content.

Redirect:

```bash
curl -i http://localhost:8080/api/books/redirect
```

Status **303 See Other**, header `Location: /api/books/10`, no body. Do not use `curl -L` when you want to observe the initial redirect response because `-L` makes cURL follow the target URI.

In Windows PowerShell, use `curl.exe` and put each command on one line (Bash's `\` line continuation does not work the same way in PowerShell).

## 11. Comparing `ResponseEntity` with Other Ways to Return Responses

| Return style | Status control | Header control | Body | Suitable for |
| --- | --- | --- | --- | --- |
| DTO directly from `@RestController` | Usually 200 default | Usually depends on another layer | Yes | Simple GETs |
| `@ResponseStatus(HttpStatus.CREATED)` | Status typically **fixed** by annotation | Not directly via this annotation | May have one | Methods always returning one status |
| `ResponseEntity<T>` | Flexible per branch outcome | Yes | Yes/no | REST endpoints |
| `HttpEntity<T>` | Does not declare a separate status itself | Yes | Yes | Responses needing only headers/body |
| `HttpServletResponse` | Yes, low-level control | Yes | Manually written or framework-handled by pattern | Servlet streaming/integration |
| Throwing exception + `@ExceptionHandler` | Via error handler | Configurable | May have one | API-wide error standardization |

Annotation example:

```java
@ResponseStatus(HttpStatus.CREATED)
@PostMapping("/simple")
public BookDto create(@RequestBody BookInput input) {
    return service.create(input);
}
```

This is **illustrative** code requiring an application-defined `service`. `@ResponseStatus` is convenient when the whole method always returns the same status, but when a single handler may return 201, 400, or 409 depending on state, `ResponseEntity` or exception mapping is more flexible.

**Note:** `ResponseEntity` can be returned from a regular `@Controller`; the class does not have to be annotated with `@RestController`. Spring recognizes the return type and writes the HTTP response accordingly without treating it as a model/view name.

## 12. Testing Real Status + Headers + Body with MockMvc

In a Spring MVC application, `MockMvc` lets you test HTTP results without starting a real network server. Spring Boot tests typically need the `spring-boot-starter-test` dependency. Example testing GET endpoints from the application in section 10:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getBookReturnsStatusHeaderAndBody() throws Exception {
        mvc.perform(get("/api/books/10")
                        .accept("application/json"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Book-Id", "10"))
                .andExpect(jsonPath("$.id").value(10))
                .andExpect(jsonPath("$.title").value("Java Basics"));
    }

    @Test
    void missingBookReturns404() throws Exception {
        mvc.perform(get("/api/books/999")
                        .accept("application/json"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.message")
                        .value("Book 999 not found"));
    }
}
```

Save in `src/test/java/com/example/demo/BookControllerTest.java`. This is a **separate JUnit 5 test file**; do not place it inside `DemoApplication.java`. Run:

```bash
# macOS / Linux
./mvnw test

# Windows
mvnw.cmd test
```

Both tests read fresh state from the controller inside the Spring test context without calling DELETE; they do not depend on cURL operations run in another process. If security configuration is added later, tests must handle the corresponding security filters/tokens/roles.

When testing create/delete endpoints, verify branches for `201` + `Location`, `204` + empty body, `404`, and `406/415` when using consumes/produces. Testing headers and body together prevents cases where JSON is right but the status is wrong.

## 13. Common Mistakes When Using ResponseEntity

| Mistake | Problem | Fix |
| --- | --- | --- |
| Returning `ResponseEntity.ok(errorDto)` on error | Client sees 200 even though operation failed | Choose an appropriate 4xx/5xx status |
| POST creates a resource but always returns 200 | Loses the Created signal for the client | `ResponseEntity.created(location).body(saved)` |
| Returning `204` with JSON | Violates no-content semantics | Use `build()` or choose 200 if a body is returned |
| Concatenating JSON strings manually | Escaping/schema bugs, hard to test | Return a DTO via a converter |
| Setting `Content-Type: application/json` for invalid String | Client fails to parse | Use a JSON object or valid formatting |
| Manually filling `Content-Length` using `String.length()` | Character count does not equal UTF-8 byte count | Let the framework compute it where appropriate |
| `Location` header using host from untrusted input | Risk of open redirect/host injection | Build URIs from trusted base URL/forwarded-header policy |
| Response caches private content by mistake | Can be stored/shared unintentionally | `CacheControl.noStore()` or appropriate private policy |
| Assigning a fixed ETag to mutable data | Client receives stale 304 or wrong state | Compute validator from version/representation |
| Using `ResponseEntity<?>` everywhere needlessly | Body contract becomes hard to read | Prefer `ResponseEntity<Dto>` and an error handler |
| Returning 404 for every exception | Hides bugs and misleads clients | Distinguish business, validation, and system errors |
| Mixing manual response writing with converters | Double-written body, headers already committed | Choose one clear response strategy per method |

## 14. Key Points for Production Deployment

- **Separate request DTOs and response DTOs:** `ResponseEntity` does not filter sensitive fields. Do not return entities directly containing password hashes, tenant secrets, or internal notes just because the serializer is convenient.
- **Check authorization before constructing the body:** 403/404 status per policy must not be decided solely from client-sent data. Ownership and authorization still belong in the service/security layer.
- **HTTP headers are part of the API contract:** `Location`, `ETag`, `Retry-After`, `Cache-Control`, and `Content-Disposition` must serve their exact purpose. Custom headers may be affected by proxies, caching, or CORS policies.
- **Pay attention to HEAD and conditional GET:** do not assume HEAD has a body; `304` likewise carries no representation body.
- **Do not mutate an already-committed response:** writing directly to `HttpServletResponse` and then changing status/headers after flush may have no effect; with `ResponseEntity`, let Spring handle body serialization.
- **Avoid overly large responses:** `ResponseEntity<byte[]>` holds data in RAM; use `Resource`/streaming or pagination where appropriate.
- **Synchronize status and error payload:** if an RFC 9457 body includes `status`, that field must match the HTTP status; do not leak stack traces or sensitive data.

### Checklist for Choosing a Handler Result

1. Is the request valid and authorized? If not, choose the right 4xx status and error contract.
2. Does the resource exist / has it finished being created? GET can be 200/404; POST that created it can be 201/Location; an unfinished job can be 202.
3. Is there a useful body? If not, choose a bodyless response like 204 when semantics fit.
4. Which media type did the client request via `Accept`? Do `produces` and converters support it?
5. Are standard headers like `Location`, `Cache-Control`, `ETag`, or `Content-Disposition` needed?
6. Do tests check **status + headers + body (or empty body)** as well as error branches?

## 15. Self-Check

**Question 1.** In a `@RestController`, you need to return 201, header `Location: /api/orders/5`, and JSON object `OrderDto`. How do you write it?

```java
return ResponseEntity
        .created(URI.create("/api/orders/5"))
        .body(orderDto);
```

This assumes `orderDto` was created/saved successfully. `created` automatically sets status 201 and Location; the DTO goes through a converter.

**Question 2.** When DELETE succeeds without returning content, should you use `ResponseEntity.ok("deleted")` or `ResponseEntity.noContent().build()`?

**Answer:** Use `noContent().build()` if the API intends to indicate bodyless success, i.e., 204. You can choose 200 with a representation under a different contract, but never attach a body to 204.

**Question 3.** Why is `ResponseEntity.status(404).body(error)` different from `ResponseEntity.ok(error)`?

**Answer:** The body may be identical, but the HTTP status determines how clients, caches, proxies, and monitoring interpret the result. Returning 200 for a 404 error is semantically wrong.

**Question 4.** Do `ResponseEntity<String>` and `ResponseEntity<MyDto>` necessarily use the same converter?

**Answer:** No. The converter depends on the Java type and media type; strings usually use the string converter, while JSON DTOs usually use the Jackson converter.

**Question 5.** If POST returns 201 when the resource has not been created yet and was only queued, which code is better to consider?

**Answer:** `202 Accepted` along with appropriate job tracking metadata, because processing is not yet complete.

**Question 6.** Does simply attaching `eTag("v1")` to GET make PUT automatically prevent overwriting an older version?

**Answer:** No. You must handle HTTP preconditions such as `If-Match`/`412` or concurrency control at the service/database layer; a GET ETag alone does not lock updates.

## 16. Official Documentation

- [Spring Framework — `ResponseEntity`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html): builder syntax, status/header/body, Resource, and async.
- [Spring Framework — Controller Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html): `ResponseEntity`, `HttpEntity`, `@ResponseBody`, and other return types.
- [Spring Framework — HTTP Caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html): `Cache-Control`, `ETag`, and conditional HTTP.
- [Spring Framework — HTTP Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): how converters serialize bodies by Java type/media type.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail` and error handling in REST.
- [Spring Framework — Request Mapping](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): `consumes`, `produces`, and content negotiation.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): definitions of standard HTTP statuses/headers.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): structured error body format.

**Core takeaway:** in Spring MVC, `ResponseEntity<T>` is the explicit way to declare **status + headers + body** for each REST response branch. Pick the status based on actual outcome, use builders for standard headers, let converters write the proper representation of `T`, and verify all three parts with HTTP/MockMvc tests.
