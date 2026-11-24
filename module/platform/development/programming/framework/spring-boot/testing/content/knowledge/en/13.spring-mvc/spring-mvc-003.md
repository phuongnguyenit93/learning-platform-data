# Sending Requests with Path Variables, Query Parameters, Headers, and Body in Spring MVC Testing

## 1. Goal and Scope

A Spring MVC endpoint receives HTTP data from several places: **path variables** in the URL path, **query parameters** after `?`, request **headers**, and a **body** containing JSON or other data. When testing a controller, we need to prove that Spring MVC **maps the URL correctly, converts types, validates data, and passes the right arguments to business logic**, then returns the HTTP status, headers, and response body specified by the contract.

Example request to create a book:

```http
POST /api/books?source=mobile HTTP/1.1
Host: localhost
X-Tenant-Id: tenant-a
Content-Type: application/json
Accept: application/json

{"title":"Spring MVC","pages":240}
```

And a request to fetch a book:

```http
GET /api/books/42?lang=vi HTTP/1.1
Host: localhost
X-Tenant-Id: tenant-a
Accept: application/json
```

The subject under test in this lesson is **Spring MVC request binding**: `@PathVariable`, `@RequestParam`, `@RequestHeader`, and `@RequestBody`, along with sending requests via **MockMvc**. At the end of the lesson, there is also a test running an embedded server on a random port to clarify the difference between simulated MVC testing and real HTTP.

**Expected outcomes:** be able to read a MockMvc test and identify which HTTP input becomes which Java parameter; write both happy-path and 400/415 error tests; set `Content-Type` separately from `Accept`; and understand when to use `@WebMvcTest` versus `@SpringBootTest`.

## 2. Four Sources of HTTP Request Data

| Source | Example in Request | Received by Spring MVC via | Sent in MockMvc via |
| --- | --- | --- | --- |
| Path variable | `/api/books/42` | `@PathVariable("id") long id` | `get("/api/books/{id}", 42)` |
| Query parameter | `?lang=vi&page=2` | `@RequestParam("lang") String lang` | `.queryParam("lang", "vi")` or `.param(...)` |
| Header | `X-Tenant-Id: tenant-a` | `@RequestHeader("X-Tenant-Id") String tenantId` | `.header("X-Tenant-Id", "tenant-a")` |
| JSON body | `{"title":"Java","pages":220}` | `@Valid @RequestBody BookRequest body` | `.contentType(APPLICATION_JSON).content(json)` |

The same name `id` may appear in the path, query, header, or JSON, but **does not automatically become a single unified value**. Each annotation dictates where Spring MVC must read the data from.

Do not equate an **HTTP request** with a **Java method call**: when calling `controller.getBook(42, "vi", "tenant-a")` directly, you **bypass** route matching, header resolvers, JSON converters, validation, and most of Spring MVC infrastructure. To test Spring MVC binding, send requests via `MockMvc.perform(...)` or an HTTP client.

### Visualizing the Processing Flow

```text
MockMvc.perform(...)
    |
    v
DispatcherServlet
    |
    +--> HandlerMapping: selects @GetMapping / @PostMapping
    |
    +--> HandlerAdapter / ArgumentResolvers
    |      @PathVariable     -> Long
    |      @RequestParam     -> String, int, List<String>, ...
    |      @RequestHeader    -> String / HttpHeaders / ...
    |      @RequestBody      -> HttpMessageConverter -> Java object
    |                                   |
    |                                @Valid
    v
BookController
    |
    v
BookService (mocked in @WebMvcTest)
    |
    v
ResponseEntity / Java object
    |
    v
HttpMessageConverter -> JSON response
```

Tests should observe **both the inbound contract** (request parsed properly and right method selected) and the **outbound contract** (status/JSON/headers returned properly). Mockito `verify(...)` can prove the controller passed the right arguments to the service, but assertions on the HTTP response are still required.

## 3. Choosing the Right Spring MVC Testing Level

There are three common options:

| Test Level | Configuration | What Is Real? | When to Use |
| --- | --- | --- | --- |
| MVC slice | `@WebMvcTest(BookController.class)` + `MockMvc` | `DispatcherServlet`, binding, converters, validation, and slice-compatible MVC config; service usually mocked | Fast, focused controller/HTTP contract checks |
| Full Spring context + MockMvc | `@SpringBootTest` + `@AutoConfigureMockMvc` | Broader application context; requests still go through mock servlet | Testing multiple beans without needing a TCP server |
| Real HTTP server | `@SpringBootTest(webEnvironment = RANDOM_PORT)` + `TestRestTemplate`/HTTP client | Embedded server and socket, servlet stack, controller, beans | HTTP integration tests over a real port |

**`@WebMvcTest` automatically configures `MockMvc`** when using a compatible Servlet MVC stack; there is no need to add `@AutoConfigureMockMvc` in the slice example. By contrast, `@SpringBootTest` defaults to `webEnvironment = MOCK` but **does not automatically provide a `MockMvc` bean** if `@AutoConfigureMockMvc` is missing.

If the application has Spring Security on the classpath, the MVC slice may load security filters; tests must set up authentication/CSRF per policy or use `spring-security-test` support. Simply adding `.header("Authorization", "...")` does not prove a user is logged in if no matching authentication filter is active.

In this lesson, we use Spring Boot 3.3.5 and Boot's `@MockBean` to mock the service in `@WebMvcTest`. Newer versions may prefer Spring Framework 6.2+'s `@MockitoBean`; do not mix annotations without checking the BOM.

## 4. Creating a Runnable Java 17+ Sample Application

Project structure:

```text
mvc-request-testing/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/mvc/
│   ├── MvcRequestApplication.java
│   ├── BookRequest.java
│   ├── BookView.java
│   ├── BookService.java
│   ├── InMemoryBookService.java
│   └── BookController.java
└── src/test/java/com/example/mvc/
    ├── BookControllerWebTest.java
    └── BookHttpTest.java
```

There is **an in-memory fake service** so the entire application can start when running the HTTP test. In `@WebMvcTest`, that service is excluded from the slice by default and replaced with a Mockito mock to verify binding and interactions precisely.

### 4.1. Gradle Configuration

`settings.gradle`:

```groovy
rootProject.name = 'mvc-request-testing'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

- `spring-boot-starter-web` provides Spring MVC, Jackson JSON, and the embedded servlet server.
- `spring-boot-starter-validation` provides Jakarta Bean Validation so `@Valid` on the request body takes effect.
- `spring-boot-starter-test` provides JUnit Jupiter, MockMvc, Mockito, and Spring Boot Test.
- `junit-platform-launcher` supports the test runtime under Gradle configuration.

Use a Gradle version compatible with Boot 3.3.x, JDK 17+, and repository connectivity on initial download. If the repository already includes a Gradle Wrapper, use `./gradlew`; otherwise use `gradle` from an installed Gradle distribution.

### 4.2. Application Class

`src/main/java/com/example/mvc/MvcRequestApplication.java`:

```java
package com.example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcRequestApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcRequestApplication.class, args);
    }
}
```

Package `com.example.mvc` is the parent package of the controller, service, and tests so `@WebMvcTest`/`@SpringBootTest` can automatically locate the primary configuration.

### 4.3. Request DTO and Response DTO

`src/main/java/com/example/mvc/BookRequest.java`:

```java
package com.example.mvc;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record BookRequest(
        @NotBlank String title,
        @Min(1) int pages
) {
}
```

`src/main/java/com/example/mvc/BookView.java`:

```java
package com.example.mvc;

public record BookView(
        long id,
        String title,
        int pages,
        String language,
        String tenantId
) {
}
```

Using a Java `record` gives requests/responses a constructor, accessors, `equals`, and `hashCode` based on components; Jackson in Spring Boot 3.3.x supports serializing/deserializing records. `@NotBlank` forbids null/empty/whitespace-only titles; `@Min(1)` requires at least 1 page.

Note that `record` here is solely for learning binding; returning the tenant ID in the response in this example must not be treated as a secure API design by default. A real system must enforce tenant identity from an authenticated principal rather than trusting a client-declared header.

### 4.4. Service Contract and In-Memory Service

`src/main/java/com/example/mvc/BookService.java`:

```java
package com.example.mvc;

import java.util.List;

public interface BookService {
    BookView find(long id, String language, String tenantId);

    List<BookView> search(
            String query, int page, int size,
            List<String> tags, String tenantId);

    BookView create(String tenantId, BookRequest request);
}
```

`src/main/java/com/example/mvc/InMemoryBookService.java`:

```java
package com.example.mvc;

import java.util.List;

import org.springframework.stereotype.Service;

@Service
public class InMemoryBookService implements BookService {
    @Override
    public BookView find(long id, String language, String tenantId) {
        return new BookView(
                id, "Book " + id, 100, language, tenantId);
    }

    @Override
    public List<BookView> search(
            String query, int page, int size,
            List<String> tags, String tenantId) {
        return List.of(new BookView(
                1L, "Java", 210, "vi", tenantId));
    }

    @Override
    public BookView create(String tenantId, BookRequest request) {
        return new BookView(
                1000L, request.title(), request.pages(), "vi", tenantId);
    }
}
```

This service is a **simple fixture for starting the application**, not a complete repository or pagination implementation. The `search` method intentionally returns a fixed result; the goal of this lesson is testing **query parameter binding at the controller**, not search algorithms.

### 4.5. Controller Receiving Path, Query, Header, and JSON Body

`src/main/java/com/example/mvc/BookController.java`:

```java
package com.example.mvc;

import java.util.List;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {
    private final BookService service;

    public BookController(BookService service) {
        this.service = service;
    }

    @GetMapping(
            value = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<BookView> getById(
            @PathVariable("id") long id,
            @RequestParam(name = "lang", defaultValue = "vi")
                    String language,
            @RequestHeader("X-Tenant-Id") String tenantId) {
        return ResponseEntity.ok(
                service.find(id, language, tenantId));
    }

    @GetMapping(
            value = "/search",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public List<BookView> search(
            @RequestParam("q") String query,
            @RequestParam(name = "page", defaultValue = "0") int page,
            @RequestParam(name = "size", defaultValue = "10") int size,
            @RequestParam(name = "tag", required = false)
                    List<String> tags,
            @RequestHeader("X-Tenant-Id") String tenantId) {
        return service.search(
                query, page, size,
                tags == null ? List.of() : tags,
                tenantId);
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<BookView> create(
            @RequestHeader("X-Tenant-Id") String tenantId,
            @Valid @RequestBody BookRequest request) {
        BookView result = service.create(tenantId, request);
        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }
}
```

Key points:

- `@PathVariable("id") long id` reads the `42` segment in `/api/books/42` and converts it to `long`. If `id=abc`, MVC cannot convert the type and the default response is typically **400 Bad Request**.
- `@RequestParam(name="lang", defaultValue="vi")` uses `vi` if the client omits `lang` (and per `defaultValue` mechanics, can also apply when the value is empty).
- `@RequestParam("q")` is **required** by default; if the query parameter is missing, MVC can return **400** before calling the service.
- `@RequestParam("tag", required=false) List<String> tags` allows the client to send repeated `tag=mvc&tag=boot`. The controller normalizes the absent case to an empty list.
- `@RequestHeader("X-Tenant-Id")` is required; missing the header causes MVC to return 400 under default handling.
- `@Valid @RequestBody BookRequest` requires valid JSON and validates `title`/`pages`; an invalid request body can return 400 before entering the service.
- `consumes` declares the accepted input media type. Sending `POST` with `text/plain` instead of `application/json` causes MVC to respond with **415 Unsupported Media Type** in this sample config.
- `produces` declares the response media type; the client's `Accept` header can influence content negotiation.
- `/search` is a literal route, more specific than `/{id}`. Spring MVC selects the specific route for `/api/books/search`; method order in source code is not the priority mechanism.

## 5. Sending Requests in MockMvc

MockMvc does not make HTTP calls over a socket. It simulates a servlet request and passes it into `DispatcherServlet`/Spring MVC infrastructure. Basic API:

```java
mockMvc.perform(
        get("/api/books/{id}", 42L)
                .queryParam("lang", "vi")
                .header("X-Tenant-Id", "tenant-a")
                .accept(MediaType.APPLICATION_JSON)
)
.andExpect(status().isOk())
.andExpect(jsonPath("$.id").value(42));
```

This is a **shortened snippet**, requiring a test with injected `MockMvc`, imports from `MockMvcRequestBuilders`, `MockMvcResultMatchers`, and the controller/service in context.

### Important Builders

| API | Effect | Pitfall |
| --- | --- | --- |
| `get("/api/books/{id}", 42L)` | Creates GET, expanding path variable via URL template | Do not use `.param("id", "42")` in place of a path variable |
| `.queryParam("lang", "vi")` | Adds query parameter to the request URL | Different from a JSON body |
| `.param("lang", "vi")` | Adds a servlet request parameter directly | Might not produce the exact query string of a real HTTP client |
| `.header("X-Tenant-Id", "tenant-a")` | Adds an HTTP header | Does not replace real authentication/authorization |
| `.headers(httpHeaders)` | Attaches a constructed `HttpHeaders` | Useful when multiple headers are needed |
| `.contentType(MediaType.APPLICATION_JSON)` | Sets Content-Type of the **request body** | Not synonymous with `Accept` |
| `.accept(MediaType.APPLICATION_JSON)` | States the client accepts a **JSON response** | Does not make a JSON body appear on its own |
| `.content(json)` | Sends bytes/string as the request body | Requires matching Content-Type and valid JSON |
| `.characterEncoding("UTF-8")` | Sets the request character encoding | Needed only when encoding is the focus of the test |
| `.andExpect(status().isCreated())` | Asserts HTTP status | Does not replace asserting response content |
| `.andExpect(jsonPath("$.id").value(42))` | Asserts a JSON field | Requires the response to actually be JSON |
| `.andDo(print())` | Prints request/response for debugging | Avoid leaving on continuously in CI if logs grow noisy |

**`.param` vs. `.queryParam`:** for ordinary `@RequestParam`, both usually supply the value to the resolver; `.queryParam` also appends to the query string and is preferable when representing the URL sent by a client. Do not manually URL-encode multiple times before passing into the builder: that can cause **double-encoding**.

**`Content-Type` vs. `Accept`:** a client sending JSON needs the matching `Content-Type` so Spring picks the right converter; a client requesting a JSON response uses `Accept`. Passing only `.accept(APPLICATION_JSON)` will not make a string body parse as JSON.

## 6. Complete MVC Slice Test Suite: 10 Test Cases

Create file `src/test/java/com/example/mvc/BookControllerWebTest.java`. The test uses `@WebMvcTest` to create the MVC slice, `@MockBean` to mock the dependency, and `ObjectMapper` to build clean JSON bodies from DTOs. Each test is independent of any DB or external HTTP server.

```java
package com.example.mvc;

import java.util.List;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(BookController.class)
class BookControllerWebTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @MockBean
    BookService service;

    @Test
    void getBindsPathQueryAndHeader() throws Exception {
        BookView view = new BookView(
                42L, "Clean Code", 300, "en", "tenant-a");
        when(service.find(42L, "en", "tenant-a"))
                .thenReturn(view);

        mockMvc.perform(get("/api/books/{id}", 42L)
                        .queryParam("lang", "en")
                        .header("X-Tenant-Id", "tenant-a")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.title").value("Clean Code"))
                .andExpect(jsonPath("$.language").value("en"))
                .andExpect(jsonPath("$.tenantId").value("tenant-a"));

        verify(service).find(42L, "en", "tenant-a");
    }

    @Test
    void getUsesDefaultLangWhenQueryIsMissing() throws Exception {
        when(service.find(7L, "vi", "tenant-a"))
                .thenReturn(new BookView(
                        7L, "Java", 100, "vi", "tenant-a"));

        mockMvc.perform(get("/api/books/{id}", 7L)
                        .header("X-Tenant-Id", "tenant-a")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.language").value("vi"));

        verify(service).find(7L, "vi", "tenant-a");
    }

    @Test
    void searchBindsRepeatedTagsAndPagination() throws Exception {
        List<BookView> results = List.of(new BookView(
                1L, "Java", 210, "vi", "tenant-a"));

        when(service.search(
                "java spring", 2, 5,
                List.of("mvc", "boot"), "tenant-a"))
                .thenReturn(results);

        mockMvc.perform(get("/api/books/search")
                        .queryParam("q", "java spring")
                        .queryParam("page", "2")
                        .queryParam("size", "5")
                        .queryParam("tag", "mvc", "boot")
                        .header("X-Tenant-Id", "tenant-a")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value(1))
                .andExpect(jsonPath("$[0].title").value("Java"));

        verify(service).search(
                "java spring", 2, 5,
                List.of("mvc", "boot"), "tenant-a");
    }

    @Test
    void postReadsValidatedJsonBodyAndReturns201()
            throws Exception {
        BookRequest request = new BookRequest("Spring MVC", 240);
        BookView created = new BookView(
                100L, "Spring MVC", 240, "vi", "tenant-a");

        when(service.create("tenant-a", request))
                .thenReturn(created);

        mockMvc.perform(post("/api/books")
                        .header("X-Tenant-Id", "tenant-a")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(request)))
                .andExpect(status().isCreated())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(100))
                .andExpect(jsonPath("$.title").value("Spring MVC"))
                .andExpect(jsonPath("$.pages").value(240));

        verify(service).create("tenant-a", request);
    }

    @Test
    void rejectsNonNumericPathId() throws Exception {
        mockMvc.perform(get("/api/books/{id}", "abc")
                        .header("X-Tenant-Id", "tenant-a"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void rejectsMissingRequiredHeader() throws Exception {
        mockMvc.perform(get("/api/books/{id}", 42L))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void rejectsMissingRequiredSearchQuery() throws Exception {
        mockMvc.perform(get("/api/books/search")
                        .header("X-Tenant-Id", "tenant-a"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void rejectsInvalidJsonBodyBeforeService() throws Exception {
        BookRequest invalid = new BookRequest("", 0);

        mockMvc.perform(post("/api/books")
                        .header("X-Tenant-Id", "tenant-a")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(invalid)))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void rejectsMalformedJson() throws Exception {
        mockMvc.perform(post("/api/books")
                        .header("X-Tenant-Id", "tenant-a")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void rejectsUnsupportedRequestContentType() throws Exception {
        mockMvc.perform(post("/api/books")
                        .header("X-Tenant-Id", "tenant-a")
                        .contentType(MediaType.TEXT_PLAIN)
                        .content("title=Java"))
                .andExpect(status().isUnsupportedMediaType());

        verifyNoInteractions(service);
    }
}
```

**Expected result: 10 test methods PASS** in this class when application code and dependencies are properly configured; tests have not been automatically executed inside this guide. For invalid input tests, `verifyNoInteractions(service)` confirms errors are blocked **before the business service is called**. For valid requests, `verify(service)...` confirms final binding produced the exact arguments.

### Why Is @WebMvcTest + @MockBean a Suitable Choice?

`@WebMvcTest(BookController.class)` loads only infrastructure and beans relevant to the MVC slice and does not automatically load `InMemoryBookService` as a regular service. `@MockBean BookService` supplies a mock that Spring inserts into the context so the controller can inject it.

On Boot 3.3.x, mock beans are typically reset between tests by Spring Boot Test infrastructure, preventing stubbing or invocation history from leaking between tests. You do not need `@ExtendWith(MockitoExtension.class)` alongside `@WebMvcTest` for `@MockBean` to work.

In Spring Framework 6.2+ / Boot 3.4+, look at `@MockitoBean` when upgrading dependencies; stay aligned with your project's BOM instead of copying a new annotation into an older stack.

## 7. Reading and Analyzing Each Test Case

### 7.1. Path Variable: Right Type, Right Position

`get("/api/books/{id}", 42L)` expands the path template into `/api/books/42`. Spring MVC processes `@PathVariable("id") long id` and passes `42L` to the controller.

Do not use:

```java
get("/api/books").param("id", "42")
```

as a substitute for `/api/books/42`. These two URIs are **different**; the `@GetMapping("/{id}")` route does not match a URI lacking the ID segment.

For `/api/books/abc`, Spring MVC matches the URL pattern but cannot convert `abc` to `long`. Test `rejectsNonNumericPathId` expects `400`. This is a **conversion error**, distinct from `/api/unknown` which fails route matching and typically falls into a 404/handler-not-found case.

For path variables containing spaces or special characters, prefer URI templates/builders and check specific encoding behavior. Do not arbitrarily concatenate user input strings to construct test requests.

### 7.2. Query Parameters: Default, Required, Repeated

`@RequestParam(defaultValue="vi")` applies when the query omits `lang`, whereas `@RequestParam("q")` requires `q` to be present. With numeric queries:

```http
GET /api/books/search?q=java&page=2&size=5&tag=mvc&tag=boot
X-Tenant-Id: tenant-a
```

Spring MVC converts `page` and `size` to integers and collects `tag` into `List<String>`. The test verifies that the service receives `List.of("mvc", "boot")`.

You can also send servlet parameters via:

```java
get("/api/books/search")
        .param("q", "java spring")
        .param("page", "2")
        .param("tag", "mvc", "boot");
```

However, when testing query strings like an HTTP client, `.queryParam(...)` expresses intent more closely. When a parameter repeats, Spring receives multiple values; it does not automatically treat a comma-separated string as multiple elements unless a matching converter handles it. Parsing a single `tag=mvc,boot` value can depend on converters, so test it separately if your API supports that format.

**Invalid values:** `page=abc` cannot convert to `int`, usually resulting in `400`. If you want to constrain `page >= 0` and `size >= 1`, add explicit validation on the parameter or model rather than assuming Spring MVC rejects negative values automatically.

### 7.3. Headers: Request Metadata, Not Body

`@RequestHeader("X-Tenant-Id")` reads an HTTP header, not a query parameter or JSON field. Per HTTP, header names are case-insensitive; `X-Tenant-Id` and `x-tenant-id` denote the same header name. However, the **header value** must match the exact contract (tenant ID, correlation ID, API version, etc.).

You can send multiple headers via:

```java
HttpHeaders headers = new HttpHeaders();
headers.add("X-Tenant-Id", "tenant-a");
headers.add("X-Correlation-Id", "trace-123");

mockMvc.perform(get("/api/books/{id}", 42L)
        .headers(headers));
```

This shortened snippet needs `import org.springframework.http.HttpHeaders`, `MockMvc`, and a controller. Never treat a client-supplied tenant header as proof the user belongs to that tenant: in a real application, verify authentication/authorization from the security context and server-side policies.

If you want an optional header:

```java
@RequestHeader(name = "X-Correlation-Id", required = false)
String correlationId
```

This is illustrative annotation syntax in a method signature, not a complete method. You can use `defaultValue` when the API defines a fallback. For required headers, keep the default `required = true` and test the missing-header case.

### 7.4. Body: JSON, Content-Type, DTO, Validation

POST in the example:

```http
POST /api/books HTTP/1.1
X-Tenant-Id: tenant-a
Content-Type: application/json
Accept: application/json

{"title":"Spring MVC","pages":240}
```

`@RequestBody BookRequest` asks Jackson to convert JSON into the Java record. `@Valid` triggers configured Bean Validation; `title=""` or `pages=0` causes the request to be rejected, defaulting to `400`. Malformed JSON also fails message conversion and typically yields `400`.

In MockMvc, use:

```java
.contentType(MediaType.APPLICATION_JSON)
.content(objectMapper.writeValueAsBytes(request))
```

to avoid escaping mistakes or typos in field names when creating a JSON body. Using literal JSON is also helpful when a test wants to verify the raw payloads real clients send, especially missing fields, wrong types, unknown fields, or malformed JSON.

**`@Valid` does not replace business validation.** It validates constraints declared on the DTO. If a rule says "book code must be unique in the database," separate service/repository logic is required; an MVC slice test does not prove database constraints.

### 7.5. Media Types: 400, 415, and 406 Are Different

| Scenario | Typical Response in Sample | Cause |
| --- | --- | --- |
| `POST` with valid JSON, JSON Content-Type | 201 | Binding and validation succeeded |
| `POST` with syntactically invalid JSON | 400 | Body could not be parsed |
| `POST` with valid JSON but blank title / pages=0 | 400 | DTO validation failed |
| `POST` with `Content-Type: text/plain` | 415 | Does not satisfy `consumes=application/json` |
| `GET` without `X-Tenant-Id` | 400 | Missing required header |
| `GET /api/books/abc` | 400 | Could not convert path variable to `long` |
| Client accepts only a response other than `produces=application/json` | Possibly 406 | Content negotiation cannot satisfy `Accept` |

These statuses rely on Spring MVC's **default exception handling** in the sample project without custom `@ControllerAdvice`. If your application handles exceptions and returns custom errors, assert your application's contract rather than assuming a default status.

`.accept(APPLICATION_JSON)` states the **response** expectation; `.contentType(APPLICATION_JSON)` states the **request body** metadata. A test can send `Accept: application/json` with a `text/plain` body; with `consumes=application/json`, the request will still get 415.

## 8. Real HTTP Test via RANDOM_PORT

MockMvc suffices for routing/binding/MVC-layer checks, but opens no TCP connection. To confirm the controller works over a real HTTP server, create an additional `@SpringBootTest` class with `RANDOM_PORT`.

`src/test/java/com/example/mvc/BookHttpTest.java`:

```java
package com.example.mvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BookHttpTest {

    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void sendsGetAndPostOverRealHttp() {
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Tenant-Id", "tenant-http");
        headers.setAccept(java.util.List.of(MediaType.APPLICATION_JSON));

        HttpEntity<Void> getEntity = new HttpEntity<>(headers);

        ResponseEntity<BookView> found = restTemplate.exchange(
                "/api/books/42?lang=en",
                HttpMethod.GET,
                getEntity,
                BookView.class);

        assertEquals(HttpStatus.OK, found.getStatusCode());
        assertNotNull(found.getBody());
        assertEquals(42L, found.getBody().id());
        assertEquals("en", found.getBody().language());
        assertEquals("tenant-http", found.getBody().tenantId());

        headers.setContentType(MediaType.APPLICATION_JSON);
        BookRequest input = new BookRequest("HTTP Book", 150);

        ResponseEntity<BookView> created = restTemplate.exchange(
                "/api/books",
                HttpMethod.POST,
                new HttpEntity<>(input, headers),
                BookView.class);

        assertEquals(HttpStatus.CREATED, created.getStatusCode());
        assertNotNull(created.getBody());
        assertEquals("HTTP Book", created.getBody().title());
        assertEquals(150, created.getBody().pages());
    }
}
```

**Expected result: 1 test PASS.** `TestRestTemplate` uses an HTTP client to call the real embedded server started by Spring Boot on a random port. Because `InMemoryBookService` is `@Service` and the application root is scanned, requests run through the in-memory service rather than the MVC slice's Mockito mock.

Use relative URLs like `/api/books/42?lang=en` with the `TestRestTemplate` configured by Spring Boot Test for the embedded server. Do not hardcode port 8080. When building URIs containing special characters manually, use a URI builder and verify encoding against the contract.

**Limitation:** this test still uses the in-memory service, so it does not verify real database/transaction/business consistency. It tests HTTP ingress, binding, and responses on a real server. For tests that create real data, keep in mind that `@Transactional` on the test thread does not automatically roll back transactions committed on the server thread when using `RANDOM_PORT`.

## 9. Running Tests and Verifying Results

There are two complete test classes:

| Class | Test Methods | Scope |
| --- | ---: | --- |
| `BookControllerWebTest` | 10 | MockMvc MVC slice: path, query, header, body, and error branches |
| `BookHttpTest` | 1 | GET + POST over a real embedded HTTP server |

Total of **11 `@Test` methods** in the example. Commands:

```bash
./gradlew test --tests 'com.example.mvc.BookControllerWebTest'
./gradlew test --tests 'com.example.mvc.BookHttpTest'
./gradlew test
```

On Windows use `gradlew.bat test` or `.\gradlew.bat test` in PowerShell. If the project has no Wrapper, use `gradle test` when Gradle is installed.

Gradle output can vary by machine and version; there is no fixed business stdout. Once the suite succeeds, open:

```text
build/reports/tests/test/index.html
build/test-results/test/
```

Check the actual count of executed, failed, and skipped tests as well as any exception causes. **Do not claim the entire production application is tested** just because the 11 sample tests PASS.

## 10. Adding Test Cases When Real APIs Get More Complex

### 10.1. Repeated Query Parameters and Multiple Values

`@RequestParam("tag") List<String> tags` can accept `?tag=a&tag=b`. Use `.queryParam("tag", "a", "b")` and verify ordering/values if that is part of the contract. If the API allows comma-separated values, test `?tag=a,b` separately to check the actual converter; never assume the two encodings always behave identically.

### 10.2. Path Variables Containing Spaces or Slashes

When an ID is a slug like `"java basics"` or contains `/`, encoding and route matching are trickier than numeric IDs. Pass values through URI templates/`UriComponentsBuilder` properly rather than concatenating unencoded strings into URLs. **Encoded slashes** can be blocked or normalized differently by servers/proxies; prefer safe route designs instead of masking issues with MockMvc tests.

### 10.3. Multi-Value Headers

`@RequestHeader List<String>` or `HttpHeaders` can be used when the API allows multiple values. Test with `.header("X-Feature", "a", "b")` and assert that the resolver receives the expected list. For headers like `Authorization`, use security test infrastructure to verify identity rather than relying on manual headers as proof of authentication.

### 10.4. Multipart and Non-JSON Form Bodies

JSON `@RequestBody` is not the only way to send a body. `multipart("/upload").file(...)` works with `MultipartFile`; URL-encoded forms typically use `@RequestParam`/`@ModelAttribute` with `Content-Type: application/x-www-form-urlencoded`. Do not copy `.contentType(APPLICATION_JSON)` onto a multipart request and expect the resolver to receive a file.

### 10.5. Nested JSON and Validation

DTOs with nested objects need `@Valid` on the corresponding nested fields; lists of objects and other constraints have their own rules. Using `ObjectMapper` to serialize fixtures can hide field-name mismatches from real clients because the Java test and server share the same DTO. Supplement with some **literal JSON contract tests** for field names, optional fields, nulls, and unknown fields as required by the API.

### 10.6. Status and Error Format

In real systems, `@RestControllerAdvice` can convert binding errors into standardized JSON:

```json
{"code":"INVALID_REQUEST","message":"pages must be >= 1"}
```

This is an **example payload**, not automatic Spring Boot output. To assert `$.code` and `$.message`, you must implement the corresponding advice. Tests that only assert 400 may suffice for simple conversion errors, but public APIs usually need to protect the error schema too.

## 11. Common Mistakes When Writing MockMvc Tests

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `404 Not Found` | URL does not match `@GetMapping`/`@PostMapping` | Check `@RequestMapping` prefix, path template, HTTP method |
| `400 Bad Request` when passing id | `@PathVariable long` cannot parse string | Check URL segment/type; do not substitute a query param |
| `400 Bad Request` due to missing header | `@RequestHeader` is required by default | Pass `.header(...)` with the exact name |
| `400 Bad Request` due to missing query | `@RequestParam` is required | Pass `.queryParam(...)` with the exact key |
| `400 Bad Request` with JSON | Malformed JSON or DTO validation failed | Check request body and `@Valid` |
| `415 Unsupported Media Type` | POST `consumes=application/json` but wrong Content-Type | Add `.contentType(APPLICATION_JSON)` |
| `406 Not Acceptable` | Client `Accept` does not match `produces` | Check `.accept(...)` |
| `No qualifying bean of type BookService` | MVC slice does not load services | Add `@MockBean` of the right type for Boot 3.3 |
| `401/403` in app with Security | Filters/CSRF/authentication are active | Use `spring-security-test` and configure per policy |
| `Wanted but not invoked` from Mockito | Controller did not call service or mocked a different instance | Inspect resolved handler, arguments, and dependency wiring |
| Direct controller test misses header bug | Bypassed Spring MVC argument resolvers | Send requests via MockMvc |
| MockMvc PASSES but HTTP port is unreachable | MockMvc does not open a socket | Add a `RANDOM_PORT` integration test |
| Unexpected JSON fields | Wrong mapping/Jackson/property naming | Assert `jsonPath` or `content().json(...)` |
| Test PASSES alone but FAILS in suite | Fixture state/context cache/concurrency | Check cleanup and data isolation |

### Debugging Requests Accurately

During development, add:

```java
mockMvc.perform(get("/api/books/{id}", 42L)
        .header("X-Tenant-Id", "tenant-a"))
    .andDo(print());
```

This illustrative snippet requires static import `org.springframework.test.web.servlet.result.MockMvcResultHandlers.print`. Output usually shows the request URI, headers, resolved handler, exception, status, and response body, helping pinpoint the cause. Enable selectively; never leave tokens or sensitive data in logs.

In Spring Boot Test, when reading logs, distinguish exceptions from **HandlerMapping** (no match), **argument binding** errors, **JSON conversion/validation**, or the **service itself throwing an exception**. Until you know which step failed, do not hastily change the status assertion "to make it PASS."

## 12. QA Criteria for Request-Binding Tests

Before merging a controller test, verify:

1. Do the URL and HTTP method match the route? Are path variables passed in the URI rather than faked with query parameters?
2. Do query parameters have the exact names and types, and are default and missing-required cases tested?
3. Are required headers sent properly, and does testing a missing header verify the service is blocked?
4. Does request body `Content-Type` match `consumes`, and `Accept` match response `produces`?
5. Does the JSON have the exact field names, data types, and schema specified by the API?
6. Does `@Valid` run with the validation dependency on the classpath?
7. Do assertions check **both status and response body** rather than only verifying a method call?
8. With `@WebMvcTest`, are controller dependencies mocked or imported properly in the context?
9. Do `verify(service)...` calls verify the exact post-conversion and defaulted values?
10. Are invalid requests rejected **before calling the business service**?
11. If security is active, are authentication, authorization, and CSRF configured properly?
12. If the contract needs real TCP, is there a `RANDOM_PORT` test in addition to MockMvc?
13. Is test data independent across tests without accidentally hitting production databases or APIs?
14. After running, does the test report show the expected PASS/FAIL/SKIPPED counts?

## 13. Self-Check Exercises

Using the project in Sections 4–9:

1. Change `get("/api/books/{id}", 42L)` to `get("/api/books").param("id","42")`. Predict the failure and explain the difference between path variables and query parameters.
2. Remove `.queryParam("lang","en")` from the first test. If the service is still stubbed with language `"en"`, what happens? Fix the stub to use the default language `"vi"`.
3. Add `.queryParam("size","abc")` to the search test. Write assertions for 400 and `verifyNoInteractions(service)`.
4. Remove the `X-Tenant-Id` header in POST. Why can the status become 400 before the service is invoked?
5. Send JSON `{"title":"","pages":0}`. Why is `spring-boot-starter-validation` required to enforce these constraints?
6. Change POST `Content-Type` to `text/plain` while keeping the JSON body. Contrast the 415 error with a 400 malformed JSON error.
7. Add a test with `Accept: text/plain` against an endpoint with `produces=application/json`. Observe the 406 behavior and the role of content negotiation.
8. Add an optional field to `BookRequest`, write tests with and without the field, and verify defaulting per contract.
9. Extend `BookHttpTest` to send multi-value query parameters and verify the result through the real server.
10. If Spring Security is present, apply `@WithMockUser`/CSRF test support for protected routes instead of relying on ad-hoc headers.

## 14. References

- [Spring Framework — Testing Spring MVC Applications](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): MockMvc, request builders, response assertions.
- [Spring Framework — @PathVariable](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/uri-variables.html): URI template variables and type conversion.
- [Spring Framework — @RequestParam](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html): query parameters, defaults, multiple values.
- [Spring Framework — @RequestHeader](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestheader.html): header binding.
- [Spring Framework — @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): message converters, JSON binding, and validation.
- [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/): `@WebMvcTest`, `@SpringBootTest`, `@MockBean`, and `MockMvc`/`TestRestTemplate`.

## 15. Summary

In Spring MVC Testing, sending a request properly means letting **`DispatcherServlet`** receive the URL, method, query string, headers, and body, and observing how Spring MVC resolves each parameter. Use `get("/path/{id}", id)` for **path variables**, `.queryParam(...)`/`.param(...)` for **query parameters**, `.header(...)` for **headers**, and `.contentType(...).content(...)` for **JSON bodies**; `.accept(...)` expresses the response media type the client accepts.

For reliable tests, assert **HTTP status, JSON response, and service call arguments**, while also testing conversion, validation, and media-type error branches. `@WebMvcTest` + MockMvc enables fast, controlled MVC-layer testing; `RANDOM_PORT` adds real HTTP server evidence when needed. Keep test scope appropriate, isolate external dependencies, and never confuse a working controller method with **properly bound HTTP requests**.