# Creating Resources with HTTP 201 Created and the Location Header in Spring MVC

## 1. Scenario: A POST Request Creates a New Resource

Suppose a REST application manages books. The client sends:

```http
POST /api/books HTTP/1.1
Host: api.example.com
Content-Type: application/json
Accept: application/json

{"title":"Spring MVC thực hành"}
```

The server validates the data, creates a record with a server-assigned ID (for example `1001`), and responds:

```http
HTTP/1.1 201 Created
Location: /api/books/1001
Content-Type: application/json

{"id":1001,"title":"Spring MVC thực hành"}
```

This response communicates **three independent yet complementary things**:

1. **`201 Created`**: the HTTP request succeeded and resulted in one or more new resources being created.
2. **`Location: /api/books/1001`**: the URI of the **primary resource** created by the request; the client can use this URI in a subsequent request if the server supports retrieval at that URI.
3. **JSON response body**: a representation or summary of the new resource, such as its ID and title. A body **may or may not be present**; `201` does not require a JSON body.

A client may follow up with:

```http
GET /api/books/1001 HTTP/1.1
Host: api.example.com
Accept: application/json
```

If the API supports GET on that resource and the resource still exists, the response is typically `200 OK` with the corresponding representation. **Do not assume every `Location` is always an accessible GET URL**: permissions, state, or specific contracts may restrict it; the API should document this clearly.

Lesson goal: understand standard HTTP semantics, choose the right Spring MVC response, construct URIs properly, protect the REST contract, and write tests verifying HTTP status/headers/body.

## 2. Exact Semantics According to RFC 9110

RFC 9110, section **15.3.2 — 201 Created**, describes this status when a request succeeded and created **one or more resources**. The primary resource is identified by the `Location` header if present; otherwise, the primary resource is identified by the **target URI** of the request.

This leads to the following principles:

- `201` is a **success** response (2xx), **not a redirect** (3xx). HTTP clients **do not automatically GET `Location` merely because the status is 201**.
- `Location` should point to the newly created primary resource, such as `/api/books/1001`, not always back to the POST collection `/api/books`.
- `Location` can contain an **absolute URI** (`https://api.example.com/api/books/1001`) or a **relative URI reference** (`/api/books/1001`). RFC 9110 allows a URI-reference; clients resolve a relative Location against the request URI.
- `201` **does not require** a body; if present, the body typically describes the action outcome or the new resource. When sending JSON, ensure proper serialization and `Content-Type`.
- The server should generate meaningful, durable URIs rather than forcing the client to guess a location from an ID returned separately in the body.
- If POST creates multiple resources, `Location` represents only the **primary resource**; the body can list the other resources per the published contract.
- The `Location` header is not a guarantee that all operations on the resource are authorized or that the resource will exist forever.

**Example of a valid bodyless 201 response:**

```http
HTTP/1.1 201 Created
Location: /api/books/1001
Content-Length: 0
```

However, for `POST /api/books`, **returning `Location` is recommended** because the client needs to know the URI of the new resource. If Location is omitted, the spec's fallback to the target URI `/api/books` usually fails to identify the child record under standard REST design. This is why the header is valuable even though status 201 does not syntactically mandate Location.

### `Location` vs. `Content-Location`

| Header | Question answered | In a typical 201 |
| --- | --- | --- |
| `Location` | "Where is the URI of the created primary resource?" | `/api/books/1001` |
| `Content-Location` | "Which URI does the representation in the **current body** correspond to?" | May be `/api/books/1001` if the body is the current representation of the resource |

According to RFC 9110, for **201**, when `Content-Location` matches `Location`, the message carries the current representation of the created resource. You do not need to add `Content-Location` to every 201; use it only when representation semantics and caching/content negotiation require it.

Do not confuse `Location` in **201** with `Location` in **301/302/303/307/308**: in 3xx responses, Location specifies the redirect target; 201 does not trigger a redirect.

## 3. Choosing the Right HTTP Status for Create/Update Operations

| What happened | Appropriate code | Meaning |
| --- | --- | --- |
| POST successfully created a new resource | **201 Created** | Creation completed; usually includes Location |
| POST performed an action without creating a new resource | **200 OK** or **204 No Content** | Depends on contract and whether a body is returned |
| POST accepted request, processing asynchronously, not finished | **202 Accepted** | Accepted for processing, creation not yet guaranteed |
| PUT at a nonexistent URI, successfully created resource | **201 Created** | Resource created at target URI |
| PUT replaced/updated an existing resource | **200 OK** or **204 No Content** | Depends on whether content is returned |
| Resource not created due to data error | **400 Bad Request** or **422 Unprocessable Content** | Choose per how the API categorizes errors |
| Creation conflicts with existing resource/state | **409 Conflict** | For example, duplicate unique key |
| Client unauthenticated or unauthorized | **401 Unauthorized** / **403 Forbidden** | Must not be treated as created |
| Created, but wants to direct client to GET another resource | **303 See Other**, depending on use case | This is an intentional redirect choice, distinct from 201 |

**Especially for PUT:** RFC 9110 specifies that if PUT succeeds and the target resource **did not previously have a current representation**, the server reports **201 Created**. If the target already existed and was updated, 200/204 is typically used. Do not equate every HTTP PUT with 200 or every HTTP POST with 201.

**For asynchronous processing:** return 201 only when resource creation is confirmed complete per the contract. If the request was merely queued and might fail later, normally return 202 along with a job status checking mechanism. `Location` in 202 (if present) may point to a processing-status resource; do not assume it is already the final result resource as in 201.

## 4. Which Spring MVC APIs Return 201 + Location?

The common, explicit approach is **`ResponseEntity.created(URI location)`** in `org.springframework.http.ResponseEntity`:

```java
URI location = URI.create("/api/books/1001");

return ResponseEntity
        .created(location)
        .body(new BookResponse(1001L, "Spring MVC thực hành"));
```

This is a **fragment inside a controller method**. When called, the builder produces:

- `HttpStatus.CREATED` = 201.
- A `Location` header from the passed `java.net.URI` object.
- A body serialized by an appropriate `HttpMessageConverter`, such as Jackson JSON.

This builder exists in Spring Framework 5, 6, and 7; it is a stable API and should be preferred over manually setting status and headers each time.

Other valid options:

```java
// Return only status 201 + Location; no body:
return ResponseEntity.created(location).build();

// Specify status and header explicitly:
return ResponseEntity.status(HttpStatus.CREATED)
        .location(location)
        .body(response);
```

For a method returning `ResponseEntity<BookResponse>`, the two snippets above are **alternatives**, not placed together in the same method. The `build()` form is used when the API specifies a bodyless 201.

**Note on `@ResponseStatus(HttpStatus.CREATED)`**:

```java
@PostMapping
@ResponseStatus(HttpStatus.CREATED)
public BookResponse create(@RequestBody BookRequest body) {
    return service.create(body);
}
```

This annotation sets **status 201**, and **does not automatically derive a URI or `Location` header**. If Location is needed, you must set the header another way or return `ResponseEntity.created(uri)`. Also do not use `ResponseEntity.ok(...)` after creation unless the contract intentionally specifies 200.

## 5. Complete Spring Boot 3.x + Java 17 Example

The following example API provides **POST create book** and **GET by ID** to verify that `Location` actually points to a new resource. In-memory `ConcurrentHashMap` storage is used for learning purposes; a production application requires a proper repository/database and transactions.

Baseline:

- Java 17 or higher.
- Spring Boot 3.x, Spring Framework 6.x, Spring MVC Servlet.
- Spring Boot starters: `spring-boot-starter-web`, `spring-boot-starter-validation`, `spring-boot-starter-test`.
- Namespace `jakarta.validation.*` (Boot 3), Jackson configured by the web starter.

### 5.1. Dependencies

In a Gradle project already configured with the Boot plugin, repository, and Java toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The snippet above is a **`build.gradle` fragment**, not a complete standalone Gradle file. With Maven, use the corresponding starters managed by the Spring Boot BOM.

### 5.2. Controller to Create and Read Books

Create **`src/main/java/demo/created/CreatedApplication.java`**:

```java
package demo.created;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.net.URI;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class CreatedApplication {

    public static void main(String[] args) {
        SpringApplication.run(CreatedApplication.class, args);
    }
}

record CreateBookRequest(@NotBlank String title) {}

record BookResponse(long id, String title) {}

@RestController
@RequestMapping("/api/books")
class BookController {

    private final AtomicLong nextId = new AtomicLong(1000);
    private final ConcurrentMap<Long, BookResponse> books =
            new ConcurrentHashMap<>();

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<BookResponse> create(
            @Valid @RequestBody CreateBookRequest request) {

        long id = nextId.incrementAndGet();
        BookResponse saved = new BookResponse(id, request.title());
        books.put(id, saved);

        URI location = URI.create("/api/books/" + id);
        return ResponseEntity.created(location).body(saved);
    }

    @GetMapping(
            path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    BookResponse findById(@PathVariable long id) {
        BookResponse result = books.get(id);
        if (result == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Book not found");
        }
        return result;
    }
}
```

This is a **single valid Java file** with exactly one public class (`CreatedApplication`). The two records and controller lack `public` so they can be declared in the same file; Spring Boot component scanning from package `demo.created` will pick up the controller.

Design choices in the example:

1. `@NotBlank` and `@Valid` prevent POST with `title=null`, `""`, or whitespace only. This is syntax/input validation, not full business rules.
2. `AtomicLong` provides distinct IDs within a single JVM across concurrent requests; IDs may repeat after restart because the example stores data in memory.
3. `books.put(id, saved)` writes the resource **before returning 201**. Status 201 is only meaningful when the server has actually succeeded in creating it per the chosen model.
4. `URI.create("/api/books/" + id)` builds a **Location relative to the origin root**. Because the ID is a server-generated number, no unencoded string input is injected directly into the URI.
5. `ResponseEntity.created(location).body(saved)` returns exact `201` + `Location` + JSON DTO. The API does not return an internal JPA Entity.
6. `GET /api/books/{id}` returns 200 if the book exists, or throws `ResponseStatusException(404)` if absent. Clients can rely on Location to query it.
7. The example assumes the web app is deployed at the **root context path**; if running under `/myapp` or behind a prefix-rewriting gateway, adjust the URI-building policy per section 8.

**Do not treat `ConcurrentHashMap` as a database:** there is no persistence, transaction, system-wide uniqueness, auditing, backup, or cross-instance state sharing. With a DB, save transactionally first and then construct Location from the actual ID.

### 5.3. Running and Testing with curl

Start the Gradle project:

```bash
./gradlew bootRun
```

Send POST:

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"title":"Spring MVC thực hành"}'
```

In a freshly started demo application with no prior POSTs, typical response:

```http
HTTP/1.1 201
Location: /api/books/1001
Content-Type: application/json

{"id":1001,"title":"Spring MVC thực hành"}
```

Other headers such as `Date`, `Connection`, `Content-Length`, or charset are omitted from the example. **ID 1001 is only accurate if no prior create request ran**; JSON field order is not guaranteed. In practice, read Location from the response rather than guessing the ID.

Read the resource:

```bash
curl -i 'http://localhost:8080/api/books/1001'
```

Typical output:

```http
HTTP/1.1 200
Content-Type: application/json

{"id":1001,"title":"Spring MVC thực hành"}
```

Test an invalid body:

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":"   "}'
```

Typically returns **400 Bad Request** due to `@NotBlank`; no book is created and **no new Location is returned**. The specific JSON error body depends on `@ControllerAdvice`/Boot error configuration and is not a fixed part of the example.

If using Postman, Bruno, or browser `fetch`, inspect the **status and Location response header** directly. A `201` does not automatically navigate the tool to a new page.

## 6. Properly Testing the POST → 201 + Location → GET Contract

Tests should verify simultaneously:

- Valid POST returns `201 Created`.
- A properly formatted `Location` header is present.
- Body contains saved data and the server-generated ID.
- GET to the URI obtained from Location returns the new resource.
- Invalid POST returns an error and **does not report success**.

In the Boot 3 project from section 5, create **`src/test/java/demo/created/CreatedApplicationTests.java`**:

```java
package demo.created;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CreatedApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void createsResourceAndCanRetrieveAtLocation() throws Exception {
        MvcResult created = mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"title":"Spring MVC"}
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.title").value("Spring MVC"))
            .andReturn();

        String location =
                created.getResponse().getHeader(HttpHeaders.LOCATION);
        assertNotNull(location);
        assertTrue(location.matches("/api/books/[0-9]+"));

        mvc.perform(get(location).accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Spring MVC"));
    }

    @Test
    void invalidInputDoesNotCreateResource() throws Exception {
        MvcResult invalid = mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"title":"   "}
                    """))
            .andExpect(status().isBadRequest())
            .andReturn();

        String location =
                invalid.getResponse().getHeader(HttpHeaders.LOCATION);
        org.junit.jupiter.api.Assertions.assertNull(location);
    }

    @Test
    void absentResourceReturns404() throws Exception {
        mvc.perform(get("/api/books/9223372036854775807"))
            .andExpect(status().isNotFound());
    }
}
```

Run:

```bash
./gradlew test
```

With a Boot 3 demo using `spring-boot-starter-test` and `spring-boot-starter-validation` as described, **all three tests are expected to pass**. This is an expectation from the code, not output from a specific run. The tests do not depend on fixed IDs across tests; therefore they can run repeatedly even as `AtomicLong` continues incrementing.

Limitation of `MockMvc`: it runs through Spring MVC with Spring test mock requests/responses, **not through a real reverse proxy or network browser**. To verify absolute URLs/forwarded headers, add integration tests in an environment with a trusted proxy and production base URL.

### Testing When Not Returning a Body

If the API intentionally chooses a bodyless 201, change the method to:

```java
ResponseEntity<Void> create(...) {
    URI location = ...;
    return ResponseEntity.created(location).build();
}
```

This is another design fragment; `...` is only a signature/logic placeholder, **not standalone compilable Java**. When testing, remove JSON body assertions; keep `status().isCreated()` and the `Location` header assertion. You can use `content().string("")` if the contract strictly requires an empty body.

## 7. Building the Location URI: Relative Path or Absolute URL?

### 7.1. Relative Location

```java
URI location = URI.create("/api/books/" + saved.id());
return ResponseEntity.created(location).body(saved);
```

This is a simple option when the API has a fixed root path on the same origin. RFC 9110 allows `Location` to be a **URI-reference**, without requiring a scheme/host. A client sending POST to `https://api.example.com/api/books` can resolve `/api/books/1001` to `https://api.example.com/api/books/1001`.

Advantage: it does not take a hostname from an untrusted header, reducing HTTP/HTTPS issues behind proxies. Risk: a URI starting with `/` resolves against the **host root**, so if the API has a context path `/catalog` or a gateway exposes prefix `/v1`, Location must include the appropriate public prefix (e.g., `/catalog/api/books/1001`). If you want a URL under **the current URI directory itself**, understand relative path resolution rules like `1001` vs. trailing-slash paths; avoid arbitrary string concatenation.

### 7.2. Application-Known Absolute Location

If the API is published on a fixed canonical hostname, it can be constructed from managed configuration:

```java
// Illustrative only: this value should come from trusted config.
URI location = URI.create(
        "https://api.example.com/api/books/" + saved.id());
```

This option is useful when the service runs behind a reverse proxy and must ensure Location points to the public hostname. Do not hardcode dev/staging hostnames in business logic; put the base URL in configuration. Do not use unvalidated request `Host` or `X-Forwarded-Host` headers to build an absolute Location, as doing so can inject malicious links in responses (*host-header poisoning*).

### 7.3. Using `ServletUriComponentsBuilder` in Spring MVC

In a Servlet application, when building a URL based on the current request:

```java
import java.net.URI;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

URI location = ServletUriComponentsBuilder
        .fromCurrentRequestUri()
        .pathSegment("{id}")
        .buildAndExpand(saved.id())
        .toUri();
```

This is a **fragment inside a request-handling method**, assuming the current request is `POST /api/books` with no special trailing slash/prefix and `saved` already exists. When invoked, the builder uses scheme/host/path from the request and appends the ID path segment, so the URL might look like `http://localhost:8080/api/books/1001`. This approach usually preserves the context path provided by the Servlet container.

Notes:

- If the request path already ends with `/`, inspect the actual output to avoid a canonical URL with double or unintended slashes.
- Reverse proxies can change scheme/host/prefix; configure trusted forwarded headers and `ForwardedHeaderFilter`/container mechanisms as needed. Do not trust headers sent directly by public clients.
- `fromCurrentRequestUri()` uses the request URI without appending query strings when constructing Location; verify output if the request has `?source=...`.
- When the ID is a **slug string** taken from input rather than a server-assigned number, encode it as a **URI path segment**, avoiding raw insertion of slashes, `?`, `#`, or uncontrolled percent-encoded strings.

### 7.4. URI Path Segments with Special Characters

If the identifier is a string, prefer a URI builder with template variables:

```java
import java.net.URI;
import org.springframework.web.util.UriComponentsBuilder;

String slug = "spring mvc/advanced";
URI location = UriComponentsBuilder
        .fromPath("/api/books")
        .pathSegment("{slug}")
        .encode()
        .buildAndExpand(slug)
        .toUri();
```

In this case the slash is **inside the slug value**, so it is encoded as data of **one segment** rather than splitting into a new path level. If the system intentionally allows multi-segment slugs, that is a different route design and must be stated explicitly. The `slug` value is illustrative only; in a real API, validate format and uniqueness where identifiers are issued.

**Do not build Location by concatenating unvalidated request input**. Especially avoid embedding raw input into URLs that could contain `#`, `?`, or path-manipulating sequences.

## 8. What Must Complete Before Returning 201?

`201` has an observable meaning when the resource **has been created successfully** per the contract. With a repository or database:

1. Validate input.
2. Enforce business rules and authorization.
3. Create the new entity and persist it within an appropriate transaction.
4. Obtain the real identifier assigned by the storage system.
5. Construct the resource URI from that identifier.
6. Return `201 Created` with `Location` and body when needed.

Pseudocode:

```java
@PostMapping
ResponseEntity<BookView> create(@Valid @RequestBody CreateBookRequest dto) {
    Book saved = bookService.createBook(dto); // service manages transaction
    URI location = URI.create("/api/books/" + saved.getId());
    return ResponseEntity.created(location)
            .body(BookView.from(saved));
}
```

This is a **service/DTO design fragment**, not standalone compilable code: `Book`, `bookService`, and `BookView.from` are application components you must define. The key point is that location comes from the **assigned and committed ID**. Do not return 201 just because you *started* calling save and then run actual work in the background where it might fail.

For a standard database transaction, ensure commit errors are handled before finalizing HTTP success. If using outbox/eventual consistency, define clearly which resource was created: for example, a request/task resource may be created immediately (201 for the task) while the final artifact is still processing (202/other per design). Do not report the final resource as created if only an event was published.

### Client-Provided IDs via PUT

With `PUT /api/books/book-abc`, the URI is already specified by the client:

- If resource `book-abc` did not exist and PUT creates it: **201 Created**.
- If it already existed and PUT updates/replaces it: **200 OK** with body or **204 No Content**.
- `Location` in 201 may be the target URI `/api/books/book-abc` to clarify the newly created resource, depending on the contract.

**Do not treat POST and PUT as synonyms.** POST asks the server to process per collection/resource semantics, typically letting the server assign the URI; PUT requests state at a **known target URI** and is an idempotent method under HTTP semantics, though ancillary side effects must be designed carefully.

## 9. POST, Retries, and Duplicate Creation Risk

POST is **not idempotent by default**. If a client sends a POST to create a resource and a network timeout occurs before receiving 201, the client may not know whether the server succeeded. Resending the exact same POST can create a **second resource**, e.g., ID 1002, and return another 201.

```text
Client                          Server
  | POST /api/books              |
  |----------------------------->| creates id=1001
  |          201 Location        |
  |<----------[timeout]----------| response lost
  | POST /api/books (retry)      |
  |----------------------------->| creates id=1002 if deduplication is absent
  | 201 Location: /api/books/1002|
  |<-----------------------------|
```

Common solution: a client-generated **`Idempotency-Key`** for one creation intent, paired with an idempotency store on the server. A good design needs:

- Key scoped per user/tenant and endpoint/action, never shared indiscriminately system-wide.
- Bounded lifetime; store the key and result atomically or with appropriate coordination.
- If the same key and same payload are resent, return the recorded outcome (potentially including the same `201`, `Location`, and body) per the API contract.
- If the same key is sent with a different payload, report a conflict (`409` or appropriate error) instead of silently reusing the result.
- Keep unique/business constraints in the DB to prevent race conditions.
- Do not assume merely adding an `Idempotency-Key` header provides idempotency; the backend must implement the semantics.

This is an API design pattern, not an automatic capability of `ResponseEntity.created(...)` or Spring MVC. For high-cost creations such as payments or resource provisioning, idempotency and retry handling are critical parts of the contract.

## 10. When Is Location Not Immediately Retrievable?

Even when `201` is semantically right, a client might not be able to GET Location immediately due to factors such as:

- The API does not support GET on the newly created resource due to policy/authorization (documentation should state this clearly).
- The resource is persisted, but reads go through a replica/search index that updates with lag; this is **eventual consistency**, requiring adjusted read-after-write expectations or a consistent read endpoint.
- An API gateway has a different route prefix, causing Location to have the wrong context path or scheme/host.
- The backend created the resource in another service and returned a non-public internal URI.
- The URI has an ID with special characters that were not properly percent-encoded.
- The resource was created successfully but deleted immediately afterward, or the user lost read permission.

If the system promises "an immediate GET to Location after 201 will see the resource", you need sufficient engineering (read-your-writes) and integration tests to uphold that guarantee. In an eventually consistent system, returning 201 can still be valid if the resource truly was created, but **the contract must explain when it becomes readable and how clients track it**.

## 11. Common Mistakes in Spring MVC

### A. Using Default `ResponseEntity.ok` After Creation

```java
// Does not express "new resource created" semantics.
return ResponseEntity.ok(saved);
```

Fix for a resource-creating POST endpoint:

```java
return ResponseEntity.created(location).body(saved);
```

Not every POST needs 201; POSTs that trigger actions or queries can return 200/204. Examine the **actual operation outcome**.

### B. Returning 201 Without Location When the Server Assigns the ID

```java
@ResponseStatus(HttpStatus.CREATED)
@PostMapping
public BookResponse create(@RequestBody CreateBookRequest request) {
    // ...
}
```

This snippet does not automatically generate Location. If POST targets a collection and creates a child item, the client lacks a clear canonical URI. Switch to `ResponseEntity.created(...)` or add the header manually from the actually saved ID.

### C. Location Header Pointing to the Wrong Target

Bad example: `Location: /api/books` after the server just created `/api/books/1001`. Clients may interpret the collection as the primary resource. If you need to point clients to the collection for further reference, place a link in the response body or a `Link` header with an appropriate relation, while `201`'s `Location` identifies the primary created resource.

### D. Building the URI Before Having an ID

```java
long id = 1001L; // mistakenly hardcoded from demo docs
repository.save(entity);
return ResponseEntity.created(URI.create("/api/books/" + id)).build();
```

In production, IDs may be assigned by a DB/generator; hardcoding or predicting an ID before saving is wrong. Pass the actually persisted ID with proper persistence error handling.

### E. Using an Internal Server Address or Trusting Client Host Headers

For example, a server at `http://10.0.0.15:8080` behind public proxy `https://api.example.com` returning an internal Location: external clients cannot reach it, and topology may be leaked. Distinguish:
- A relative URI with the proper public prefix.
- An absolute URI taken from a trusted external base URL configuration.
- Forwarded headers trusted across the proper proxy chain when building URIs from the request.

### F. Returning 201 Even When Validation, Authorization, or DB Insert Failed

A transaction failure after constructing a response body can make the API report the wrong status. Do not look only at the method return in an asynchronous service; ensure creation has reached the "completed" condition defined by the contract.

### G. Confusing 201 with 303

`303 See Other` redirects the client to another URI, typically to GET a representation of a POST result (e.g., redirect-after-post). `201` describes the created resource and Location identifies its URI, without the client **automatically redirecting**. Do not mix these semantics in tests.

### H. Returning a JPA Entity Directly in the JSON Body

Entities can contain internal fields, lazy relationships, circular references, or sensitive data. Choose a response DTO (`BookResponse`) with public fields and keep the JSON output contract separate.

## 12. Designing the Response Body and Accompanying Metadata

The body in a 201 is typically a product design choice; common patterns include:

| Pattern | Example | When appropriate |
| --- | --- | --- |
| `201` + Location + full DTO | `{"id":1001,"title":"Spring MVC"}` | Client needs to use the new resource immediately |
| `201` + Location + summary DTO | `{"id":1001}` | Prefer lightweight payload; client GETs when needed |
| `201` + Location + no body | No body | Client only needs URI; API schema specifies so |
| `201` + Location + metadata | DTO with initial state or version | Creation succeeded but workflow has next steps |

Additional headers:

- **`ETag`**: if provided and reflecting the current representation, clients can use conditional requests like `If-Match` when updating, helping prevent lost updates. Not automatically generated when calling `ResponseEntity.created`.
- **`Content-Location`**: indicates the URI of the representation in the body as explained in section 2.
- **`Cache-Control`**: if the response contains sensitive data or a specific caching policy; do not assume every 201 is cacheable by default.
- **`Link`**: can advertise related resources such as collection, owner, or next action, per media type/API contract.

Example Java method with version if provided by the service:

```java
return ResponseEntity.created(location)
        .eTag("\"v1\"")
        .body(saved);
```

This is a fragment inside a controller method, valid only if `saved` and `location` are defined and the version token `"v1"` truly corresponds to the stored representation. The ETag in the example only shows syntax; **do not hardcode one ETag for all resources** in a real application.

## 13. Distinguishing HTTP Errors on POST Creation

Real applications should have a clear API error contract. Examples:

| Case | Typical HTTP status | Reason |
| --- | --- | --- |
| Malformed JSON | `400 Bad Request` | Cannot deserialize request |
| Missing required `title` | `400 Bad Request` | Validation failure during binding |
| `Content-Type: text/plain` when endpoint only consumes JSON | `415 Unsupported Media Type` | Converter/mapping does not support media type |
| `Accept: application/xml` when endpoint only produces JSON | `406 Not Acceptable` | No matching representation available |
| Book title unique key duplicated, contract forbids duplicates | `409 Conflict` | Conflicts with current state |
| User not logged in / insufficient permissions | `401` / `403` | Security rejects |
| Backing service temporarily unavailable | `503 Service Unavailable` when appropriate | Must not report creation succeeded |
| POST successfully created book | `201 Created` | Needs Location of the new book |
| POST enqueued unfinished task | `202 Accepted` | Asynchronous status tracking |

Do not "force" every case to HTTP 200/201 with `success=false` inside the body. Clients, proxies, monitoring, and SDKs rely heavily on status codes; using the right status clarifies the contract and keeps the HTTP ecosystem working properly.

### Exception Handling in Spring MVC

For REST APIs, `@RestControllerAdvice` and `@ExceptionHandler` (or `ResponseEntityExceptionHandler`/`ProblemDetail` from Spring Framework 6+) can standardize error responses. However:
- Do not add a new resource's `Location` to an error response where nothing was created.
- Do not send stack traces, SQL statements, or sensitive internal IDs to clients.
- When a unique constraint race occurs, map specific DB errors to conflict only when genuinely appropriate, rather than blindly mapping every `DataIntegrityViolationException` to 409.
- If an idempotent request already created the resource earlier and the response was lost, handle retries per contract so the client retrieves the original resource URI.

## 14. Spring Versions and API Compatibility

| Milestone | `ResponseEntity.created(URI)` | Notes |
| --- | --- | --- |
| Spring Framework 5.x, Boot 2.x | Available | Boot 2 apps typically use `javax.validation` |
| Spring Framework 6.x, Boot 3.x | Available | Full example above uses `jakarta.validation`, Java 17+ |
| Spring Framework 7.x, Boot 4.x | Available | 201 + Location builder still exists; some modules/starters and Jackson/validation ecosystems changed |

The 201/Location mechanism belongs to **HTTP semantics**, independent of Jackson 2 or Jackson 3. When migrating Boot 3 → Boot 4, update imports/dependencies per the framework, while the HTTP-level `ResponseEntity.created(location)` API continues to express the contract clearly.

Spring Framework 6.0/7.0 milestones can alter URL matching or converter behavior, so re-run tests for `Location` URIs and GET endpoints. **Do not generate URIs with a trailing slash** and assume a `@GetMapping("/api/books/{id}")` router accepts both forms when path matching configuration disallows it.

## 15. Pre-Release Checklist for a Creation Endpoint

- [ ] Endpoint actually creates the resource before returning `201`; if only enqueuing, consider `202`.
- [ ] Returns `ResponseEntity.created(location)` or equivalent; Location accurately identifies the primary resource.
- [ ] Location is a valid URI reference with encoded path segments and correct base path/public prefix.
- [ ] Location does not leak a private host and cannot be spoofed via untrusted Host/Forwarded headers.
- [ ] If the API promises GET at Location, the GET endpoint can read the resource by ID per consistency policy.
- [ ] Body contract is clear: full DTO, summary, or empty; `Content-Type` is accurate when JSON body is present.
- [ ] Validation/auth/DB conflict failures never return 201; uniqueness and transactions are protected.
- [ ] POST retries are intentionally designed, especially for payments or costly creations.
- [ ] Tests cover `POST → 201 + Location → GET`, invalid 400, conflict, auth, and proxy prefix where needed.
- [ ] Demo IDs/hosts are not hardcoded into production.
- [ ] OpenAPI/SDKs and client documentation are updated for the 201 response, Location header, body, and errors.

## 16. Exercises and Self-Assessment Questions

1. **HTTP semantics:** POST successfully creates a resource at `/api/tasks/42`. Why should `201` include Location for client usability? Does `201` require a JSON body?
2. **Distinguishing redirects:** Why does a browser not automatically GET `Location` on a `201` response, whereas it may redirect after `303`?
3. **Spring API:** Write a `create` controller returning `ResponseEntity.created(uri).body(dto)` and a matching GET. Test status, header, and body.
4. **Validation:** When `title=""` triggers 400, would a Location pointing to `/api/books/1001` be appropriate? Explain.
5. **URI encoding:** If a resource slug is `"spring web/101"`, why is concatenating it directly into the path wrong? Use a builder with `pathSegment`.
6. **Reverse proxy:** The app runs internally at `http://localhost:8080` while the public URL is `https://api.example.com/v1`. Design a consistent Location and test the forwarded-header trust policy.
7. **Retry:** A client times out after POST, resends, and creates a second record. Design an `Idempotency-Key` contract handling same key/same payload/different payload.
8. **Transaction:** The DB raises a unique conflict at commit time. If the controller already prepared a 201 response but commit fails, which status should the client receive and why?
9. **201 vs. 202:** An API accepts a report-generation request that actually takes several minutes to build. If a job resource is created immediately, which status describes the **job**? Which status describes the pending **final report**? Distinguish the two resources.
10. **PUT:** For `PUT /api/books/client-id-1`, creating on the first call and updating on the second call, choose statuses per RFC 9110 and write tests for both calls.

## 17. Official References

- [RFC 9110, `15.3.2 — 201 Created](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.3.2): 201 semantics and primary resource.
- [RFC 9110, `10.2.2 — Location](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.2): URI-reference, meaning of Location in 201 and 3xx.
- [RFC 9110, `8.7 — Content-Location](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.7): difference between Location and Content-Location.
- [RFC 9110, `9.3.4 — PUT](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.3.4): creation vs. replacement of target resource on success.
- [Spring Framework 6.x Javadoc — ResponseEntity](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/http/ResponseEntity.html): `created(URI)` and HTTP builders.
- [Spring Framework 7 Javadoc — ResponseEntity](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseEntity.html): `created(URI)` remains present.
- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html): `ResponseEntity` responses in MVC.
- [Spring Framework — ServletUriComponentsBuilder](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/servlet/support/ServletUriComponentsBuilder.html): building URIs from a Servlet request.
- [Spring Framework — UriComponentsBuilder](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/util/UriComponentsBuilder.html): template handling, path segments, and encoding.
