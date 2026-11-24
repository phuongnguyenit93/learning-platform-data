# Distinguishing HTTP 404, 405, 406, and 415 from Routing or Format Conditions in Spring Boot

In a Spring Boot application, a request that fails to enter a controller can return **404 Not Found**, **405 Method Not Allowed**, **406 Not Acceptable**, or **415 Unsupported Media Type**. All four belong to the 4xx family, yet they point to distinct problems: **path/resource**, **HTTP method**, **client-accepted response format**, and **server-supported request body format**.

This is not merely a difference in error messages. Each code points to a different troubleshooting direction, and fixing the wrong layer can mask the real issue. For example, when POSTing JSON returns 415, changing the URL arbitrarily usually helps nothing; inspect **Content-Type** and the **consumes** condition. When a GET returns 406, changing the request Content-Type is likely wrong because the condition relates to **Accept** for the response.

This guide is based on Spring Boot 3.5.x / Spring Framework 6.2.x and Java 17+. It focuses on Spring MVC annotated controllers, then contrasts handling in Spring WebFlux, particularly WebFlux.fn RouterFunction. It includes a runnable Spring MVC example, a request/status table, MockMvc tests, and a practical debugging workflow.

## 1. Quick differentiation table

| Status | HTTP name | Question to ask | Common scenario |
|---|---|---|---|
| **404** | Not Found | Does the path/resource requested by the client exist or have a mapping? | Wrong URL, wrong base path, ID not found, missing static resource, unmatched functional route |
| **405** | Method Not Allowed | Is this URL served, yet unwilling to accept the HTTP method sent? | Sending DELETE to an endpoint declaring only GET; path right, method wrong |
| **406** | Not Acceptable | Can the server generate a response matching the client's **Accept**? | Client demands application/xml while endpoint only **produces application/json** |
| **415** | Unsupported Media Type | Does the server accept the **request body** format declared by **Content-Type**? | POSTing text/plain to an endpoint that only **consumes application/json** |

Remember in one sentence: **404 checks URL; 405 checks method; 406 checks Accept; 415 checks Content-Type.** This is an initial triage rule, not a claim that every case in every web framework emits one automatic status.

### Comparing request and response roles

~~~text
HTTP request
  Method:       GET / POST / PUT / PATCH / DELETE ...
  Target:       /api/books/1
  Content-Type: format of the BODY being SENT (if any)
  Accept:       format of the RESPONSE the client wants to RECEIVE
                  |
                  v
Spring MVC / Spring WebFlux handler mapping
                  |
                  +-- URL/resource not found -> typically 404
                  |
                  +-- URL matches, method unsupported -> 405
                  |
                  +-- Body media type unaccepted -> 415
                  |
                  +-- No matching response representation -> 406
                  |
                  v
Bind/decode request -> handler -> encode/write response
                  |
                  v
200 / 201 / 204 ... or other errors
~~~

The diagram illustrates logical meaning, **not a guaranteed internal check order across every HandlerMapping**. If a request violates multiple conditions simultaneously, the chosen status depends on how router/handler matching handles conditions and exception resolvers. To prove a specific error, write a test where **only one condition is wrong**.

## 2. Routing conditions on @RequestMapping

An annotated controller can apply multiple condition types:

~~~java
@PostMapping(
        path = "/books",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<Book> create(@RequestBody CreateBookRequest request) {
    // ...
}
~~~

In this example:

- **path**: request must target /books (combined with any class-level @RequestMapping prefix and context/base path).
- **HTTP method**: request must be POST.
- **consumes**: request body media type must be compatible with application/json.
- **produces**: client must accept response media type application/json.
- **@RequestBody**: after selecting the mapping, Spring needs to read the body and convert it to CreateBookRequest via a message converter/codec.

Besides these, @RequestMapping supports **params**, **headers**, route versioning in supported versions, and custom conditions. Wrong params/headers do not always yield one universal status; for instance, Spring MVC may respond with 400 for an unsatisfied request parameter condition, whereas an unmatched functional route predicate can result in 404.

**Distinguish two error layers:** (1) failing to select a handler due to mapping conditions; (2) selecting a handler yet failing while reading/writing content. Both 406 and 415 can arise from mapping conditions or subsequent media type processing capabilities.

### @RequestMapping at class and method levels

~~~java
@RestController
@RequestMapping("/api")
class BookController {

    @GetMapping(path = "/books/{id}", produces = "application/json")
    public Book find(@PathVariable("id") long id) {
        return new Book(id, "Demo");
    }
}
~~~

Here the URL is **/api/books/{id}**, not `/books/{id}` alone. In Spring MVC there may also be server.servlet.context-path; in reactive Spring WebFlux there may be spring.webflux.base-path. If a client calls an external URL missing a prefix, 404 makes more sense than investigating JSON.

## 3. HTTP 404 Not Found: no matching target or no resource

404 has at least **two distinct groups of causes**.

### 3.1. No handler for the submitted URL

For example, the application only declares GET /api/books/1, yet the client calls:

~~~http
GET /api/book/1 HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

Path /api/book/1 differs from /api/books/1. With no matching mapping, the typical outcome is 404.

Real-world scenarios:

- Singular vs. plural typo, wrong hyphen, case mismatch, or path variable regex mismatch.
- Missing prefix /api/v1, server.servlet.context-path, or spring.webflux.base-path.
- Proxy/ingress stripping paths differently than expected.
- Calling actuator, static resource, or management port URLs incorrectly.
- Controller sitting outside component scanning and thus never registered.
- Route defined with query/header conditions the request fails to meet; exact status still depends on the handler mapping mechanism.

### 3.2. Route exists, yet business resource does not exist

GET /api/books/999 can match controller GET /api/books/{id}, yet no book with id=999 exists. The service/controller **intentionally returns 404**:

~~~java
return repository.findById(id)
        .map(ResponseEntity::ok)
        .orElseGet(() -> ResponseEntity.notFound().build());
~~~

This snippet illustrates a synchronous repository with an Optional<Book> API. It differs from 404 caused by having no handler. When investigating, distinguish:

- **Routing 404**: the controller was never invoked.
- **Business 404**: the controller/service ran and determined the resource does not exist.

Logs, tracing spans, the mapping registry, and repository results help determine which case occurred.

### 3.3. Static resource 404

In Spring MVC, a path matching no controller can be evaluated by the static content resource handler. If no file exists, the response is still 404; in some Spring Framework versions, the internal exception may be **NoResourceFoundException** rather than NoHandlerFoundException.

Thus, seeing a log line mentioning static resources does not mean a real CSS file was requested; a mistyped API path may simply have fallen through to the fallback resource handler.

**Never "solve" 404 by adding a wildcard route /** returning 200 for everything.** That masks API bugs, corrupts monitoring, and misleads clients into thinking failed requests succeeded.

## 4. HTTP 405 Method Not Allowed: right URL, wrong HTTP method

405 means the server knows the target resource, yet the current method is unsupported. In Spring MVC annotated controllers, a classic case:

~~~java
@GetMapping("/api/books/{id}")
public Book find(@PathVariable("id") long id) {
    return new Book(id, "Demo");
}
~~~

Request:

~~~http
DELETE /api/books/1 HTTP/1.1
Host: localhost:8080
~~~

Because the URL has a GET mapping yet no DELETE mapping, Spring MVC normally replies **405 Method Not Allowed**. Under HTTP semantics, a 405 response must include an **Allow** header listing supported methods for the target resource.

Conceptual response example:

~~~http
HTTP/1.1 405 Method Not Allowed
Allow: GET, HEAD
~~~

The exact Allow value (and other headers) must be verified from actual responses; Spring supports HEAD automatically for GET mappings, and OPTIONS handling or custom configurations can change the list.

### 4.1. Common confusions

- **POST differs from PUT and PATCH**: if a controller only has @PostMapping, a client calling PUT may receive 405.
- **GET and HEAD**: Spring MVC and WebFlux support HEAD for GET mappings; do not use HEAD to try proving that every non-GET method returns 405.
- **OPTIONS**: the framework handles OPTIONS and Allow automatically in many situations. CORS preflight OPTIONS also passes through CORS/security, so a failing preflight is not necessarily a mapping bug.
- **@RequestMapping without specifying a method** can accept multiple HTTP methods; do not assume it only accepts GET.
- **Right port but different route**: if the URL matches no path at all, it may return 404 rather than 405.

### 4.2. Checking and fixing

1. Read the exact method the client actually sent (proxies can alter or block methods).
2. Inspect the Allow response header if present.
3. Cross-check @GetMapping, @PostMapping, @PutMapping, @PatchMapping, @DeleteMapping, and @RequestMapping(method=...).
4. Check whether frontend fetch/axios, HTML forms, API gateways, or ingress rules use the right method.
5. Avoid "fixing" by allowing every method when the API contract specifies a particular method.

On the client side, fix the method to match the contract. On the server side, add a handler only if business requirements genuinely support that operation.

## 5. HTTP 406 Not Acceptable: Accept incompatible with response

**Accept** is a request header describing the **response representations** the client is willing to receive. It does not describe the request body format.

~~~http
GET /api/books/1 HTTP/1.1
Host: localhost:8080
Accept: application/xml
~~~

If the endpoint only advertises:

~~~java
@GetMapping(
        path = "/api/books/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE)
public Book find(@PathVariable("id") long id) {
    return new Book(id, "Demo");
}
~~~

and no other mapping/representation supports application/xml, Spring can return **406 Not Acceptable**. Within annotated controller mapping conditions, produces is matched against Accept; beyond matching, a response also needs a writer/codec capable of serializing the body into the selected media type.

### 5.1. Why is 406 not like 415?

- **406**: server lacks a **response format** matching what the client accepts.
- **415**: server does not support the **request body format** the client is sending.

A GET with no body can still receive 406 due to an incompatible Accept header. A JSON POST with the right Content-Type yet an incompatible Accept for the response can still receive 406. The two headers govern opposite directions.

### 5.2. Accept with wildcards and quality values

Common values:

~~~http
Accept: application/json
Accept: application/* 
Accept: */*
Accept: application/json;q=0.9, text/plain;q=0.5
~~~

- */* accepts media types in general.
- application/* accepts subtypes under application/.
- q expresses relative preference weight and does not invent support for media types the server lacks.
- A media type with q=0 is treated as not acceptable for that selection.

When a client omits Accept or sends a broad wildcard, an endpoint that only produces JSON can usually return JSON. In API tools like Postman/curl, inspect the **actual headers sent** rather than guessing from the UI.

### 5.3. 406 can involve codecs/message converters

Suppose a controller omits produces yet returns a Java object. Spring needs an HttpMessageConverter (MVC) or HttpMessageWriter (WebFlux) to serialize the object into the negotiated media type. If no writer matches the request, the framework can return 406 or another serialization error depending on stage and configuration.

Do not rush to add an @ExceptionHandler turning every 406 into 200. Instead:

- Update the client's Accept header if the response contract is JSON.
- Add XML or text/plain representations only if the API truly supports them.
- Ensure codec/converter dependencies exist and the controller returns a serializable type.
- Check produces at both class and method levels: a method-level produces **overrides** class-level produces in Spring mappings rather than automatically merging.

## 6. HTTP 415 Unsupported Media Type: body Content-Type unsupported

**Content-Type** declares the format of the **incoming request body**. For a JSON POST, the standard header is:

~~~http
POST /api/books HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json

{"title":"Reactive Spring"}
~~~

If the endpoint requires JSON:

~~~java
@PostMapping(
        path = "/api/books",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
public Book create(@RequestBody CreateBookRequest body) {
    return new Book(2, body.title());
}
~~~

then a request using **Content-Type: text/plain**—even if the body looks like JSON—can be rejected with **415 Unsupported Media Type**.

Example of an invalid request:

~~~http
POST /api/books HTTP/1.1
Host: localhost:8080
Content-Type: text/plain
Accept: application/json

{"title":"Reactive Spring"}
~~~

Spring uses consumes when picking annotated mappings and needs a matching reader/converter to decode the body. In some cases, even if the mapping omits consumes, lacking a compatible HttpMessageConverter/HttpMessageReader can also cause the application to respond with 415.

### 6.1. Missing Content-Type can also cause 415

If an endpoint only accepts application/json and a request carries a body with no Content-Type, Spring may reject the request. Exact behavior depends on mapping conditions and actual readers/codecs. For JSON APIs, always declare Content-Type explicitly rather than relying on automatic guessing.

### 6.2. Invalid JSON is typically 400, not 415

Distinguish two requests:

~~~text
A. Content-Type: text/plain
   Body: {"title":"Book"}
   -> If endpoint only consumes JSON, typically 415.

B. Content-Type: application/json
   Body: {"title": }
   -> Media type is right, JSON syntax is invalid: typically 400 Bad Request.
~~~

**415 checks the data format type**, whereas **400** usually relates to syntax, missing/invalid values, or binding/validation. A syntactically valid JSON request missing a required field can also return 400/422 depending on the system's validation contract.

### 6.3. Form data and multipart are not JSON

Different Content-Types require different decoding mechanisms:

| Request body | Common Content-Type | Appropriate handling |
|---|---|---|
| JSON object | application/json | @RequestBody DTO via JSON converter |
| URL-encoded form | application/x-www-form-urlencoded | @RequestParam / appropriate form binding |
| File upload | multipart/form-data; boundary=... | @RequestPart / MultipartFile in MVC or FilePart in WebFlux |
| Plain text | text/plain | @RequestBody String with matching mapping |
| Binary stream | application/octet-stream | Resource, byte[], or stream as needed |

If a frontend sends FormData, do not force Content-Type: application/json. With multipart/form-data, the browser normally generates the header with the boundary automatically; setting it manually without a boundary can break request parsing.

## 7. Choosing the right Accept and Content-Type per action

For a JSON-serving REST API:

| Action | Request Content-Type | Request Accept | Scenario |
|---|---|---|---|
| GET /api/books/1 | Usually unnecessary if GET has no body | application/json | Receive book as JSON |
| POST /api/books with JSON body | application/json | application/json | Create book and receive JSON |
| POST /api/books with text body | text/plain | application/json | May get 415 if server only consumes JSON |
| GET /api/books/1 | Unnecessary | application/xml | May get 406 if server only produces JSON |
| DELETE /api/books/1 | Usually unnecessary if no body | */* | May get 405 if only GET is declared |

### 7.1. Common pitfalls with curl

To send JSON, use:

~~~bash
curl -i -X POST http://localhost:8080/api/books \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"title":"Book"}'
~~~

In Unix/Linux shells, the command above works as expected. On Windows PowerShell, depending on version, `curl` can be an alias for Invoke-WebRequest; use **curl.exe** to invoke the curl executable and follow PowerShell quoting rules.

**Note:** `curl -d`/`--data` can send a default Content-Type of application/x-www-form-urlencoded if no other header is specified. Thus, a body string that looks like JSON does not mean the request had a JSON Content-Type. `curl -i` shows status and response headers; `curl -v` shows the outgoing request headers.

### 7.2. JavaScript fetch

~~~javascript
const response = await fetch("/api/books", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Accept": "application/json"
  },
  body: JSON.stringify({ title: "Book" })
});

console.log(response.status);
~~~

This is a client example, not a Java file. It clearly separates Content-Type for the outgoing body and Accept for the incoming data. If the API sits behind a context path or gateway, the URL needs the matching prefix.

## 8. Runnable Spring MVC project: producing 404, 405, 406, and 415

The following example intentionally uses only **spring-boot-starter-web**, because mapping conditions can be verified with **MockMvc**. Spring WebFlux is compared in subsequent sections. The Java classes form complete code for a minimal Spring Boot MVC project with no database needed.

Requirements: JDK 17+, Maven, Spring Boot 3.5.0.

Structure:

~~~text
http-routing-status-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/routing/
    │   ├── RoutingDemoApplication.java
    │   ├── Book.java
    │   ├── CreateBookRequest.java
    │   └── BookController.java
    └── test/java/com/example/routing/
        └── BookRoutingTest.java
~~~

### 8.1. pom.xml

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
    <artifactId>http-routing-status-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

The Maven parent manages Boot-compatible dependency versions. The plugin block is valid and allows running the app via `spring-boot:run` or packaging a JAR.

### 8.2. RoutingDemoApplication.java

~~~java
package com.example.routing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RoutingDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoutingDemoApplication.class, args);
    }
}
~~~

### 8.3. Book.java

~~~java
package com.example.routing;

public record Book(long id, String title) {
}
~~~

### 8.4. CreateBookRequest.java

~~~java
package com.example.routing;

public record CreateBookRequest(String title) {
}
~~~

### 8.5. BookController.java

~~~java
package com.example.routing;

import java.net.URI;

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

    @GetMapping(
            path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Book> findById(
            @PathVariable("id") long id) {

        if (id != 1L) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok(new Book(1L, "Spring"));
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Book> create(
            @RequestBody CreateBookRequest input) {

        if (input.title() == null || input.title().isBlank()) {
            return ResponseEntity.badRequest().build();
        }

        Book book = new Book(2L, input.title().trim());
        return ResponseEntity.created(
                URI.create("/api/books/" + book.id()))
                .body(book);
    }
}
~~~

Breakdown of outcomes from the mapping:

- GET /api/books/1 + Accept application/json -> 200 and JSON.
- GET /api/books/999 + Accept application/json -> 404 **by business rule**.
- GET /api/does-not-exist -> 404 **due to missing endpoint**, when no custom catch-all route exists.
- DELETE /api/books/1 -> 405 because the URL matches a GET mapping yet has no DELETE.
- GET /api/books/1 + Accept application/xml -> 406 because the endpoint only produces application/json.
- POST /api/books + Content-Type text/plain -> 415 because the endpoint only consumes application/json.
- POST /api/books + Content-Type application/json and valid JSON -> 201.
- POST /api/books + Content-Type application/json with malformed JSON syntax -> typically 400.

The app simulates book storage using fixed objects. Do not assume POST actually saves to a database or that GET /api/books/2 will automatically return the newly created book.

## 9. MockMvc tests: proving each status code

**src/test/java/com/example/routing/BookRoutingTest.java**

~~~java
package com.example.routing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookRoutingTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validGetReturnsJson() throws Exception {
        mvc.perform(get("/api/books/1")
                    .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.id").value(1))
                .andExpect(jsonPath("$.title").value("Spring"));
    }

    @Test
    void missingPathReturns404() throws Exception {
        mvc.perform(get("/api/does-not-exist"))
                .andExpect(status().isNotFound());
    }

    @Test
    void existingRouteButMissingEntityReturns404() throws Exception {
        mvc.perform(get("/api/books/999")
                    .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound());
    }

    @Test
    void wrongMethodReturns405AndAllowHeader() throws Exception {
        mvc.perform(delete("/api/books/1"))
                .andExpect(status().isMethodNotAllowed())
                .andExpect(header().string(
                        HttpHeaders.ALLOW, containsString("GET")));
    }

    @Test
    void unacceptableResponseFormatReturns406() throws Exception {
        mvc.perform(get("/api/books/1")
                    .accept(MediaType.APPLICATION_XML))
                .andExpect(status().isNotAcceptable());
    }

    @Test
    void unsupportedRequestFormatReturns415() throws Exception {
        mvc.perform(post("/api/books")
                    .contentType(MediaType.TEXT_PLAIN)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Spring\"}"))
                .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void validJsonPostReturns201() throws Exception {
        mvc.perform(post("/api/books")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Spring\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.title").value("Spring"));
    }

    @Test
    void malformedJsonReturns400Not415() throws Exception {
        mvc.perform(post("/api/books")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("{\"title\":"))
                .andExpect(status().isBadRequest());
    }
}
~~~

The tests intentionally **vary only one condition per case**. That way, when a status does not match expectations, it is clear which part—URL/method/Accept/Content-Type—needs attention.

Run in the project root directory:

~~~bash
mvn test
mvn spring-boot:run
~~~

When tests pass, Maven returns exit code 0. Log counts, timing, and error body format are not assumed fixed; QA criteria are the HTTP status, required headers, and asserted business data.

### 9.1. Corresponding curl commands

Run the server on port 8080 and try:

~~~bash
# 404: undefined URL
curl -i http://localhost:8080/api/does-not-exist

# 405: right URL, but DELETE method is undefined
curl -i -X DELETE http://localhost:8080/api/books/1

# 406: client wants XML only; server only produces JSON
curl -i http://localhost:8080/api/books/1 \
  -H 'Accept: application/xml'

# 415: body declares text/plain; server only accepts JSON
curl -i -X POST http://localhost:8080/api/books \
  -H 'Content-Type: text/plain' \
  -H 'Accept: application/json' \
  --data '{"title":"Spring"}'

# 200: right GET, URL, and Accept
curl -i http://localhost:8080/api/books/1 \
  -H 'Accept: application/json'

# 201: valid JSON POST
curl -i -X POST http://localhost:8080/api/books \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"title":"Spring"}'
~~~

The commands above use Unix shell syntax. On PowerShell, use `curl.exe` or adjust quoting. Do not combine GET with `-d` as that alters the test scenario unintentionally.

## 10. When multiple conditions fail at once: avoid rigid status assumptions

Example:

~~~http
DELETE /api/books/1 HTTP/1.1
Accept: application/xml
Content-Type: text/plain
~~~

This request simultaneously uses an undeclared method, demands an XML response, and declares a body type incompatible with the POST endpoint. **Do not claim with certainty that it must return 405, 406, or 415 without checking the implementation.**

Spring MVC's RequestMappingInfo evaluates multiple conditions to find the best match. When no complete mapping matches, the framework inspects partial-match info to decide the exception/status. With custom HandlerMappings, custom exception resolvers, or security filters, results can vary further.

An effective investigation technique breaks it into independent steps:

1. Verify the GET/POST URL with Accept */* and an appropriate body.
2. Test a wrong method while keeping media types valid.
3. Test a wrong Accept while keeping method and URL valid.
4. Test a wrong Content-Type while keeping all other conditions valid.
5. Only afterward test deliberately multi-failing requests to verify system policy.

This is also why an integration test should assert each status separately instead of cramming every error into one test.

## 11. Spring WebFlux annotated controllers: principles remain similar

Spring WebFlux supports @GetMapping, @PostMapping, consumes, and produces in annotated controllers. They likewise match URLs, HTTP methods, and media types; request/response bodies are handled by reactive codecs instead of Servlet MVC HttpMessageConverters.

Illustrative WebFlux controller example (do not place into the MVC project in section 8 without changing dependencies and web application type):

~~~java
@RestController
@RequestMapping("/reactive/books")
public class ReactiveBookController {

    @GetMapping(
            path = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Book> get(@PathVariable("id") long id) {
        return Mono.just(new Book(id, "Reactive Spring"));
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Book> create(@RequestBody Mono<CreateBookRequest> body) {
        return body.map(input -> new Book(2L, input.title()));
    }
}
~~~

To use this snippet, import annotations from org.springframework.web.bind.annotation, MediaType from org.springframework.http, and Mono from reactor.core.publisher. A real WebFlux app requires spring-boot-starter-webflux and the Book/CreateBookRequest classes. The snippet omits business validation; in production add input validation, creation status codes, and error handling.

Common response codes in WebFlux annotated routes:

| Error type | Commonly associated exception |
|---|---|
| Unsupported method | org.springframework.web.server.MethodNotAllowedException |
| No matching representation | org.springframework.web.server.NotAcceptableStatusException |
| Unsupported request body media type | org.springframework.web.server.UnsupportedMediaTypeStatusException |
| Missing or invalid input data | ServerWebInputException or appropriate validation exceptions |

Internal exception classes can vary by failure point and registered extensions; **HTTP statuses and API contracts matter more than coupling tightly to framework exception classes**.

### 11.1. WebTestClient

WebTestClient is the natural choice for testing WebFlux HTTP endpoints:

~~~java
client.get()
        .uri("/reactive/books/1")
        .accept(MediaType.APPLICATION_XML)
        .exchange()
        .expectStatus().isNotAcceptable();

client.post()
        .uri("/reactive/books")
        .contentType(MediaType.TEXT_PLAIN)
        .accept(MediaType.APPLICATION_JSON)
        .bodyValue("not-json")
        .exchange()
        .expectStatus().isEqualTo(415);
~~~

This is an illustrative snippet inside a test method, assuming **client** is a WebTestClient bound to the WebFlux application and ReactiveBookController is registered. Dependency/test setup differs from the MVC project above. Do not paste these into MockMvc tests without switching to a reactive test fixture.

## 12. An easily confused case: WebFlux.fn RouterFunction

WebFlux.fn routes using RouterFunction and RequestPredicate, for example:

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/fn/books/{id}",
                        RequestPredicates.accept(
                                MediaType.APPLICATION_JSON),
                        handler::get)
                .POST("/fn/books",
                        RequestPredicates.contentType(
                                MediaType.APPLICATION_JSON),
                        handler::create)
                .build();
~~~

This illustrative snippet requires WebFlux.fn imports, MediaType, and a handler variable with matching methods; it is not a complete Java class. The two predicates:

- accept(APPLICATION_JSON) **participates in deciding whether the route matches**.
- contentType(APPLICATION_JSON) **participates in deciding whether the route matches**.

**Crucial difference:** if a functional route fails to match because of an Accept or Content-Type predicate, RouterFunction may simply return "no handler" so the framework tries the next route. If no route matches, the result can be **404** instead of automatically producing **406** or **415** like annotated @RequestMapping partial-match handling.

Therefore, never assert the rule:

~~~text
WebFlux.fn wrong accept predicate -> always 406   (WRONG)
WebFlux.fn wrong contentType predicate -> always 415 (WRONG)
~~~

If the API contract requires returning 406 or 415 consistently in functional style, design a specific strategy: separate route matching from representation checks inside the handler, or create fallback routes/filters/error mappings that explicitly return the right status. Test missing headers, incompatible headers, and overlapping path patterns. Never catch errors globally and blindly turn every 404 into 406/415.

### 12.1. A functional handler explicitly returning 415

~~~java
public Mono<ServerResponse> create(ServerRequest request) {
    boolean json = request.headers().contentType()
            .map(type -> MediaType.APPLICATION_JSON.isCompatibleWith(type))
            .orElse(false);

    if (!json) {
        return ServerResponse.status(415).build();
    }

    return request.bodyToMono(CreateBookRequest.class)
            .flatMap(body -> ServerResponse.ok()
                    .bodyValue(new Book(2L, body.title())));
}
~~~

This illustrative snippet only compiles inside a WebFlux.fn handler class with imports for ServerRequest, ServerResponse, MediaType, Mono, and the corresponding DTOs. If the route **only** uses POST("/fn/books", handler::create) without constraining a contentType predicate beforehand, the handler has the opportunity to inspect the media type itself and return 415. In production, standardize validation, 201/Location, error details, and consistent behavior with annotated endpoints.

A route with a contentType predicate that rejects requests right at routing **will not call** this handler, so design the router accordingly if you choose in-handler checking.

## 13. params and headers conditions do not always yield 404

Spring MVC also allows:

~~~java
@GetMapping(path = "/search", params = "view=full")
public List<Book> search() {
    return List.of();
}
~~~

If the client calls /search without view=full, the mapping condition fails. In Spring MVC, a case where only a request parameter condition fails can produce **400 Bad Request** (for example, an exception related to unsatisfied request parameter conditions), not necessarily 404.

Similarly, the condition:

~~~java
@GetMapping(path = "/search", headers = "X-Mode=full")
~~~

can prevent the route from matching if the header is wrong. The final HTTP result depends on other conditions, handler mappings, and exception handling.

To express media types, use **consumes** and **produces** instead of writing headers="Content-Type=..." or headers="Accept=..." whenever possible. The dedicated attributes allow Spring to perform clear media matching and produce more accurate status codes.

## 14. Distinguishing from other commonly encountered codes

Do not turn every failed request into one of the four statuses in this lesson:

| Status | Common scenario | How it differs from 404/405/406/415 |
|---|---|---|
| **400 Bad Request** | Malformed JSON syntax, missing parameter, wrong path variable type, validation failure | Request syntax or data is invalid |
| **401 Unauthorized** | Missing valid credentials | Authentication, not a missing route |
| **403 Forbidden** | Authenticated identity lacks permission, CSRF blocked | Authorization/security |
| **409 Conflict** | Current state conflicts with the operation | Business rule |
| **413 Content Too Large** | Body exceeds upload/payload limit | Size limit, not necessarily wrong media type |
| **422 Unprocessable Content** | Syntactically valid data that cannot be processed per contract, if API uses this status | Semantic validation |
| **500 Internal Server Error** | Code bug, unhandled serialization failure | Server-side failure |
| **502/503/504** | Reverse proxy or upstream encountered an error/timeout | Dependent system or gateway |

For example, if a controller has a valid @GetMapping yet Spring Security blocks the request, the response can be 401/403 **before** controller logic runs. When investigating, never exclude the security layer or proxy from the request's path.

## 15. Observing and finding root causes in Spring Boot

An applicable workflow:

1. **Record the exact request:** method, full URL, Accept/Content-Type request headers, body, and response status/headers.
2. **Confirm port, host, prefix:** server.port, server.servlet.context-path, spring.webflux.base-path, ingress rewrites.
3. **Confirm server stack:** is the app running Spring MVC/DispatcherServlet or Spring WebFlux/DispatcherHandler; also rule out MVC.fn/WebFlux.fn confusion.
4. **Inspect registered mappings:** annotation mapping path, method, consumes, produces; or RouterFunction predicates and ordering.
5. **Check whether the failure happens before or after the handler:** tracing, logs by correlation ID, exception type, and whether the controller was entered.
6. **Check message converters/codecs:** Jackson JSON/XML dependencies, supported media types, returned Java type, custom converters.
7. **Inspect response headers:** Allow on 405; Content-Type, Vary, Accept/Accept-Post if sent by the server; do not rely solely on error bodies.
8. **Write controlled tests:** change only one condition per request.
9. **Verify error customizations:** check whether @ControllerAdvice, @ExceptionHandler, ResponseEntityExceptionHandler, ErrorWebExceptionHandler, WebFilter, or Servlet Filters intervene.
10. **Test both directly and through the gateway:** when outcomes differ, check reverse proxy/security/gateway policies first.

You can enable DEBUG logging for handler mappings in test environments, while avoiding logging tokens, session cookies, sensitive bodies, or customer data. With Actuator, the mappings endpoint can assist in inspecting registered mappings if the starter and proper exposure/security are configured. Never publicly expose all Actuator endpoints just to investigate a single request.

### 15.1. Why does changing the response Content-Type not fix 415?

Because 415 happens on the **request body receiving side**. When the server cannot read the input or select a matching handler, changing response Content-Type does not satisfy the consumes condition. Conversely, 406 is about selecting the **output format**, so changing request body Content-Type likely has no effect.

### 15.2. Why does the same URL return 404 in one environment and 405 in another?

Possible reasons:

- One environment has a route mapping on the same path for another method, while the other environment registers no mapping on that path.
- Reverse proxies strip prefixes differently so the actual target path changes.
- Application context failed to scan a controller.
- Profile/feature-flag-dependent route configuration.
- Using functional routing with a failing predicate vs. annotated mapping with partial match.
- Global exception handlers or security filters altering the outcome.

Look for differences in **registered handler mappings and actual HTTP requests**, rather than comparing controller source code alone.

## 16. API error contracts and Problem Details

For public APIs, standardize how errors are represented to clients. Spring Framework supports **ProblemDetail** per RFC 9457; Spring Boot provides options supporting Problem Details in applicable versions.

Example error response:

~~~json
{
  "type": "about:blank",
  "title": "Unsupported Media Type",
  "status": 415,
  "detail": "Request body must use application/json",
  "instance": "/api/books"
}
~~~

This is a **design example**, not the fixed default output of Spring Boot 3.5.0. Error body, message, content type, and instance field depend on actual configuration and handlers.

Notes:

- Never expose stack traces, filesystem paths, internal class names, or secret lists in responses.
- Keep the actual HTTP status consistent with the status field inside the body if present.
- On 405, keep the Allow header accurate per contract.
- On 406, you can help clients discover supported response media types.
- On 415, indicate accepted request body formats.
- On business 404, provide stable business error codes without leaking the existence of access-restricted resources.
- Never convert all 4xx into 200 with an error stuffed inside the JSON body; that breaks HTTP semantics and corrupts monitoring/caching.

## 17. Anti-patterns to avoid

**Anti-pattern 1: turning all 404s into 200.** This makes frontends or gateways think broken URLs succeeded and complicates operations.

**Anti-pattern 2: adding @RequestMapping without restricting methods just to "fix 405".** This exposes unintended API operations and can break idempotency and security.

**Anti-pattern 3: deleting consumes to "fix 415" without checking decoders.** Removing the condition does not turn text/plain into JSON; after matching, readers/converters can still fail.

**Anti-pattern 4: changing Accept to */* on every client to "fix 406" without knowing the API contract.** This hides format mismatches. Clients should declare representations they can actually process.

**Anti-pattern 5: reading Accept/Content-Type with exact string equality.** Media types can include charsets, parameters, wildcards, and quality values. Use Spring's MediaType and built-in mapping/negotiation mechanisms.

**Anti-pattern 6: writing catch(Exception) returning 404 for every error.** JSON parse errors, database timeouts, and permission denials require distinct status codes. Returning 404 for everything misleads operators via logs/metrics.

**Anti-pattern 7: assuming functional route predicates automatically turn every mismatch into 405/406/415.** RouterFunction uses predicates to decide matching; having no matching route can end in 404. If specific statuses are required, design and test for them.

## 18. Testing checklist before release

- [ ] Verified actual prefixes/context paths/ingress rewrites.
- [ ] GET/POST/PUT/PATCH/DELETE endpoints have clear method contracts.
- [ ] 404 tests exist for non-existent URLs and missing business resources (if required by API).
- [ ] 405 tests exist for unsupported methods, verifying an accurate Allow header.
- [ ] 406 tests exist when Accept is incompatible with produces/response writers.
- [ ] 415 tests exist when Content-Type is incompatible with consumes/body decoders.
- [ ] 400 tests exist for malformed JSON so it is not confused with 415.
- [ ] Happy-path 200/201 tests exist to confirm test failures are not due to missing routes.
- [ ] For WebFlux.fn, predicate mismatches and fallback routes/statuses are tested explicitly.
- [ ] Integration tests through the gateway or reverse proxy exist if production uses rewrites.
- [ ] Error bodies/correlation IDs are consistent without leaking sensitive data.
- [ ] Authentication/authorization errors are not confused with routing errors.

## 19. Takeaways

**404**: no matching endpoint/path found or specific resource does not exist. **405**: target resource supports other methods, yet the sent method is unsupported. **406**: unable to satisfy the response format requested by the client via Accept. **415**: request body format sent via Content-Type is unsupported.

In Spring MVC/WebFlux annotated mappings, path, method, consumes, and produces help the framework pick handlers and respond with appropriate statuses. In WebFlux.fn, an unmatched RequestPredicate can simply make the router report "no route found", so avoid mechanically assuming bad Accept always yields 406 or bad Content-Type always yields 415.

To debug effectively, keep URL, method, Accept, and Content-Type visible in logs/tests, and **change only one factor at a time**. These four statuses become clear once you separate **finding route → selecting method → checking request format → negotiating response format → processing body**.

## References

- [Spring Framework — Mapping Requests (Spring MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html)
- [Spring Framework — Mapping Requests (Spring WebFlux)](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html)
- [Spring Framework — Functional Endpoints (WebFlux.fn)](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework — Web MVC Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [MDN — HTTP Status Codes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status)
