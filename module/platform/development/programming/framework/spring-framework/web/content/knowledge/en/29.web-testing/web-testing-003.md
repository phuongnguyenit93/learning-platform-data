# Verifying Mapping, Parameters, Headers, Status, and JSON Content in Spring Web

## 1. Goals of testing an HTTP endpoint

A correct Spring Web endpoint is not merely a Java method returning the right object. It must accept **the right HTTP method and URL**, map **path variables, query parameters, request headers, and request body** into Java parameters, and produce the **status code**, **response headers**, and **JSON body** matching the contract. Web testing verifies these through HTTP requests/responses at the Spring MVC or Spring WebFlux layer.

Example contract to protect:

~~~http
GET /api/books/7?lang=en
X-Tenant: school
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json
X-Tenant-Echo: school

{"id":7,"title":"Spring","language":"en"}
~~~

You do not necessarily test every line in a separate test, but across the test suite you must verify:

1. **Mapping:** does a GET /api/books/7 request route to the right controller method, and do wrong methods/paths return appropriate statuses?
2. **Parameters:** does **7** become parameter **@PathVariable long id**, does **lang=en** go into **@RequestParam**, and does header **X-Tenant** go into **@RequestHeader**?
3. **Request contract:** does the client send the right **Content-Type**, **Accept**, and JSON body, or if missing/malformed, how does the server handle it?
4. **Response contract:** is the status 200/201/400/404/405/415/406 per case, and are **Location**, **Content-Type**, and custom business headers correct?
5. **JSON:** are the fields, values, object/array structure, and number/string types right? Is an error object accidentally returned with HTTP 200?

In Spring, test both the **happy path** and **negative paths**. Do not stop at **status().isOk()**: a controller with a wrong mapping or wrong JSON schema can still return 200.

## 2. Choosing tools and testing levels

Spring supports two prominent tools:

- **MockMvc** is for **Spring MVC** (Servlet stack). It runs through Spring MVC infrastructure and creates mock requests/responses **without opening a real HTTP server**. It is especially useful for verifying controller mapping, argument resolvers, validation, message converters, exception handlers, response status, and JSON.
- **WebTestClient** is an HTTP test client with a fluent API; it works with **Spring WebFlux** and can also test **Spring MVC** (via **MockMvcWebTestClient**), or run end-to-end against a real server. It checks responses using **expectStatus**, **expectHeader**, and **expectBody**.

| Testing level | Initialization | What is verified | What is not covered |
| --- | --- | --- | --- |
| Controller unit test via Java method call | new Controller(...).method(...) | Pure Java logic | Real HTTP mapping, binding, converters, status/headers |
| **MockMvc standalone** | MockMvcBuilders.standaloneSetup(controller) | Mapping/binding/response with locally configured MVC | Does not auto-load all app filters, advice, custom converters |
| **@WebMvcTest** + MockMvc | Spring Boot MVC slice | Controller, MVC infrastructure, and slice configuration | Does not load all application services/repositories |
| **@SpringBootTest** + MockMvc | Full ApplicationContext + mock servlet | Broad integration including beans/filters/application wiring | Does not verify real HTTP networking |
| **WebTestClient.bindToController** | WebFlux mock setup | WebFlux routers/controllers and reactive responses | Real network/proxy |
| **MockMvcWebTestClient.bindToController** | MVC mock setup | MVC using WebTestClient syntax | Real network |
| **WebTestClient.bindToServer** | Connect to running server | End-to-end HTTP, network stack | Slower, requires server/test environment |

**Recommendation for this lesson:** use **@WebMvcTest + MockMvc** to learn each MVC assertion, then use **WebTestClient** if the project uses WebFlux or wants to test through a unified HTTP client API. Do not replace HTTP-level tests with direct controller method calls: **@GetMapping**, **@PathVariable**, **@RequestBody**, and JSON conversion are not executed then.

## 3. Designing the controller and contract before writing tests

Suppose an application provides two endpoints:

- **GET /api/books/{id}?lang=...** requires header **X-Tenant**. Only book id=7 exists, language can be selected, and the server echoes tenant via a response header.
- **POST /api/books** requires **Content-Type: application/json** with body **{"title":"..."}**, returns **201 Created**, **Location: /api/books/8**, and a body describing the created book.

A Java 17 controller implementation:

~~~java
package demo;

import java.net.URI;

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
@RequestMapping(path = "/api/books",
                produces = MediaType.APPLICATION_JSON_VALUE)
public class BookController {
    public record BookView(long id, String title, String language) {}
    public record CreateBook(String title) {}

    @GetMapping("/{id}")
    public ResponseEntity<BookView> getBook(
            @PathVariable("id") long id,
            @RequestParam(name = "lang", defaultValue = "vi") String lang,
            @RequestHeader("X-Tenant") String tenant) {

        if (id != 7L) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok()
            .header("X-Tenant-Echo", tenant)
            .body(new BookView(7, "Spring", lang));
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<BookView> create(
            @RequestBody CreateBook request) {
        return ResponseEntity.created(URI.create("/api/books/8"))
            .body(new BookView(8, request.title(), "vi"));
    }
}
~~~

**Points to prove through tests:**

- **@RequestMapping(path=..., produces=...)** sets the shared path and output media type. The two method annotations add GET/POST conditions and paths.
- **@PathVariable("id") long** validates the path and converts the string to a number. A string that cannot be parsed as long causes a binding error, usually HTTP 400.
- **@RequestParam(name="lang", defaultValue="vi")** uses "vi" when the query parameter is omitted; if **lang=en** is provided, it must receive "en".
- **@RequestHeader("X-Tenant")** defaults to **required=true**; omitting the header usually returns 400 handled by Spring MVC before business code runs.
- **@PostMapping(consumes="application/json")** only matches requests with a compatible content type. Sending **text/plain** usually returns HTTP 415.
- **ResponseEntity** specifies status and headers explicitly. **created(...)** sets HTTP 201 and Location; the body record is serialized to JSON by Jackson.
- **@RestController** writes the response body automatically via converters. If using plain **@Controller** without **@ResponseBody**, a String return value may be interpreted as a view name.

This example uses fixed state so tests are deterministic. In a real system, controllers usually call a service/repository; in that case mock the service in the MVC slice and also verify the inputs passed to the service.

## 4. MockMvc: anatomy of a proper assertion

How to read a MockMvc test:

~~~java
mockMvc.perform(
        get("/api/books/{id}", 7)
            .param("lang", "en")
            .header("X-Tenant", "school")
            .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(handler().handlerType(BookController.class))
    .andExpect(handler().methodName("getBook"))
    .andExpect(header().string("X-Tenant-Echo", "school"))
    .andExpect(content().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.id").value(7))
    .andExpect(jsonPath("$.title").value("Spring"))
    .andExpect(jsonPath("$.language").value("en"));
~~~

Here **get(...)** is a request builder from **MockMvcRequestBuilders**, not a direct Java method call.

- **perform(...)** sends the mock HTTP request through the MVC infrastructure.
- **status().isOk()** verifies the response status is 200.
- **handler().handlerType(...)** and **handler().methodName(...)** verify the **handler selected by Spring**. This is direct evidence of mapping when using MockMvc.
- **header().string(...)** reads a **response header**, unlike **.header(...)** on the request builder which sets a **request header**.
- **content().contentTypeCompatibleWith(APPLICATION_JSON)** checks that the response media type is JSON-compatible; useful if the server adds a charset parameter.
- **jsonPath("$.title").value(...)** extracts a value from the JSON response. **$** is the root of the JSON document.

If a test only checks **jsonPath("$.title")**, it can miss status or header errors. If a test only checks **handler().methodName("getBook")**, it does not know if the returned content is right. Assert the parts that form the contract, not every internal implementation detail.

### Mapping is a combination of multiple conditions

A Spring MVC mapping can depend on:

- HTTP method: GET, POST, PUT, PATCH, DELETE.
- URL path, template variables, **params** and **headers** conditions in the annotation.
- **consumes** (request Content-Type) and **produces** (compatibility with client Accept).
- The application's content negotiation, trailing slash, and path matching configuration.

Example:

~~~java
@GetMapping(path = "/reports",
            params = "format=summary",
            headers = "X-Report-Client=web",
            produces = MediaType.APPLICATION_JSON_VALUE)
public Report summary() {
    return new Report("ready");
}
~~~

A request missing **format=summary** or missing the header may **fail to match the mapping**, because those conditions live on **@GetMapping** itself. Do not confuse this with a method that already matched but lacks **@RequestHeader(required=true)**, in which case Spring raises a binding error before the method runs. Exact statuses may differ depending on configuration/custom error handlers; assert according to the application's contract.

## 5. Verifying path variables, query parameters, and headers

### 5.1 Path variables

Suppose **@GetMapping("/{id}")** with **@PathVariable long id**:

~~~java
mockMvc.perform(get("/api/books/{id}", 7)
        .header("X-Tenant", "school"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(7));
~~~

Cases to include:

- **/api/books/7** → id=7, HTTP 200.
- **/api/books/100** → mapping still matches, but the controller returns HTTP 404 because the resource is absent.
- **/api/books/not-a-number** → path still has a segment, but converting String to long fails, returning HTTP 400 under default MVC behavior.
- **/api/books** without an id segment → does not match GET /{id}; for a controller that has POST /api/books, GET /api/books may return 405, depending on other mappings. Do not assume every case is 404.

**Do not conflate a business 404 with a missing-route 404**. For id=100 you can verify handler **getBook** was selected and still returned 404; for a non-existent route, that handler is not selected.

### 5.2 Query parameters

~~~java
mockMvc.perform(get("/api/books/{id}", 7)
        .param("lang", "en")
        .header("X-Tenant", "school"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.language").value("en"));

mockMvc.perform(get("/api/books/{id}", 7)
        .header("X-Tenant", "school"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.language").value("vi"));
~~~

**.param("lang", "en")** adds a request parameter to the mock request; for GET it tests Spring MVC binding of query-like request parameters. If you need to verify raw query strings/URI encoding, pass a URL with an actual query via **get("/api/books?lang=en")** or use **.queryParam(...)** appropriately rather than testing only post-binding data.

With **@RequestParam(required=true)** and no default, omitting the parameter usually makes Spring MVC return 400. For a list, use **.param("tag","java","spring")** and Java parameter **List<String>**; check both count and order per the API contract.

### 5.3 Request headers and response headers

~~~java
mockMvc.perform(get("/api/books/7")
        .header("X-Tenant", "school")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andExpect(header().string("X-Tenant-Echo", "school"));
~~~

Setting a request header and asserting a response header are two different actions. HTTP header names are **case-insensitive**, although conventions typically show them as **Content-Type**, **X-Tenant**. Custom business headers must be tested for exact values, especially authentication policy, correlation ID, cache metadata, ETag, and Location when part of the contract.

Testing a missing header:

~~~java
mockMvc.perform(get("/api/books/7")
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isBadRequest());
~~~

Status 400 in this example occurs because **@RequestHeader("X-Tenant")** is required by default. With **@RequestHeader(value="X-Tenant",required=false)**, the contract may allow omitting it; test the corresponding behavior. **Accept** expresses the desired response representation; **Content-Type** expresses the sent request body representation. Do not assert a request header with **header().string(...)** (that is a response matcher).

## 6. Verifying status codes in the right context

| Scenario | Expected status in demo | Additional checks needed |
| --- | --- | --- |
| GET /api/books/7, with headers | **200 OK** | Mapping getBook, lang, tenant echo, JSON |
| GET /api/books/100, with headers | **404 Not Found** | Controller explicitly reports missing book |
| GET /api/books/not-a-number, with headers | **400 Bad Request** | Path variable conversion error to long |
| GET /api/books/7 missing X-Tenant | **400 Bad Request** | Argument resolver rejects missing header |
| POST /api/books with valid JSON | **201 Created** | Location and newly created JSON |
| POST /api/books with malformed JSON | **400 Bad Request** | JSON converter cannot read body |
| POST /api/books with text/plain | **415 Unsupported Media Type** | consumes only accepts JSON |
| PUT /api/books/7 | **405 Method Not Allowed** | Path pattern exists, method unsupported |
| GET /api/books/7 with Accept rejecting JSON | **406 Not Acceptable** | produces only declares JSON |

**Status note:** the table above ties to the demo controller and default configuration. A **@ControllerAdvice**, security filter, or error handler can change status/body. Tests should reflect the actual chosen contract. HTTP 401/403 must be produced by actual authentication/authorization mechanisms if security is being verified; missing an ordinary business header like **X-Tenant** does not automatically imply HTTP 401.

Shortcuts in MockMvcResultMatchers:

~~~java
.andExpect(status().isOk());            // 200
.andExpect(status().isCreated());       // 201
.andExpect(status().isBadRequest());    // 400
.andExpect(status().isUnauthorized());  // 401
.andExpect(status().isForbidden());     // 403
.andExpect(status().isNotFound());      // 404
.andExpect(status().isMethodNotAllowed()); // 405
.andExpect(status().isUnsupportedMediaType()); // 415
~~~

The lines above are **independent illustrative statements** and cannot all be chained onto one request. For any arbitrary status, use **status().is(422)** or the corresponding matcher; do not hard-code 200 for every route.

## 7. Verifying JSON: JSONPath and structural matching

A JSON response is typically an object:

~~~json
{
  "id": 7,
  "title": "Spring",
  "language": "en",
  "meta": {
    "source": "catalog",
    "flags": ["popular", "featured"]
  }
}
~~~

With MockMvc, JSONPath expressions:

~~~java
.andExpect(jsonPath("$.id").value(7))
.andExpect(jsonPath("$.title").value("Spring"))
.andExpect(jsonPath("$.meta.source").value("catalog"))
.andExpect(jsonPath("$.meta.flags[0]").value("popular"))
.andExpect(jsonPath("$.meta.flags").isArray())
.andExpect(jsonPath("$.meta.flags.length()").value(2));
~~~

**$** is the root; **.id** accesses an object field; **[0]** is the first array element (0-based). When the response is a **root array**, use **$[0].title** instead of **$.title**.

### JSON types and missing vs. null

- **jsonPath("$.id").value(7)** checks the numeric value 7. A string **"7"** differs from JSON number **7**.
- **jsonPath("$.title").isString()** or **isNotEmpty()** checks data type/non-emptiness when you do not want to hard-code exact text.
- **jsonPath("$.meta.flags").isArray()** checks array type. Other APIs include isMap(), isNumber(), isBoolean(), isEmpty(), exists(), doesNotExist().
- A missing field and a field with **null** differ. **exists()** requires a non-null value; **hasJsonPath()** checks that the path exists even if null; **doesNotHaveJsonPath()** checks that the path is absent. Pick the matcher matching the JSON contract to protect.

To compare JSON structure without caring about whitespace or key order:

~~~java
.andExpect(content().json(
    "{\"id\":7,\"title\":\"Spring\",\"language\":\"en\"}"));
~~~

This JSON comparison is structural. By default in some Spring versions, **content().json(...)** uses lenient comparison for unspecified fields; to reject extra fields or mismatched array sizes, use strict JSON comparison supported by your version and add extra tests. Do not compare raw JSON strings when only field values matter: key ordering and whitespace can change while the API remains valid.

**When to use JSONPath?** Use it when you only need to assert a few stable fields while other metadata may vary. **When to check the whole body?** For error response contracts or small payloads with tight schemas where all fields, types, and arrays must be guaranteed.

### Volatile data

For timestamps, randomly generated IDs, or request IDs:
- Assert that the field **exists/matches the expected format**, rather than hard-coding unstable values.
- For fields that can be made deterministic via test fixtures, create fixed data or control the clock.
- Do not use **Thread.sleep()** to guess async outcomes; use appropriate async/timeout test APIs.
- Do not assert the order of a collection when the contract does not guarantee order. If the API guarantees ordering, assert each element and count.

## 8. Runnable Maven + JUnit 5 + @WebMvcTest example (Java 17)

Spring Boot **3.5.0** project, Java 17, Spring MVC, and spring-boot-starter-test. This demo focuses on testing mapping/params/headers/status/JSON, needing no DB or external HTTP server.

File structure:

~~~text
web-contract-test/
├── pom.xml
├── src/main/java/demo/
│   ├── WebContractApplication.java
│   └── BookController.java
└── src/test/java/demo/
    └── BookControllerTest.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>web-contract-test</artifactId>
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
</project>
~~~

**src/main/java/demo/WebContractApplication.java**:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebContractApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebContractApplication.class, args);
    }
}
~~~

**src/main/java/demo/BookController.java**:

~~~java
package demo;

import java.net.URI;

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
@RequestMapping(path = "/api/books",
                produces = MediaType.APPLICATION_JSON_VALUE)
public class BookController {
    public record BookView(long id, String title, String language) {}
    public record CreateBook(String title) {}

    @GetMapping("/{id}")
    public ResponseEntity<BookView> getBook(
            @PathVariable("id") long id,
            @RequestParam(name = "lang", defaultValue = "vi") String lang,
            @RequestHeader("X-Tenant") String tenant) {
        if (id != 7L) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok()
            .header("X-Tenant-Echo", tenant)
            .body(new BookView(id, "Spring", lang));
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<BookView> create(
            @RequestBody CreateBook request) {
        return ResponseEntity.created(URI.create("/api/books/8"))
            .body(new BookView(8, request.title(), "vi"));
    }
}
~~~

**src/test/java/demo/BookControllerTest.java**:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(BookController.class)
class BookControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getMapsPathQueryHeaderAndResponseJson() throws Exception {
        mvc.perform(get("/api/books/{id}", 7)
                .param("lang", "en")
                .header("X-Tenant", "school")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(handler().handlerType(BookController.class))
            .andExpect(handler().methodName("getBook"))
            .andExpect(header().string("X-Tenant-Echo", "school"))
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(7))
            .andExpect(jsonPath("$.title").value("Spring"))
            .andExpect(jsonPath("$.language").value("en"));
    }

    @Test
    void missingQueryUsesDefaultLanguage() throws Exception {
        mvc.perform(get("/api/books/7")
                .header("X-Tenant", "school"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.language").value("vi"));
    }

    @Test
    void missingRequiredHeaderReturns400() throws Exception {
        mvc.perform(get("/api/books/7"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void invalidPathVariableReturns400() throws Exception {
        mvc.perform(get("/api/books/not-a-number")
                .header("X-Tenant", "school"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void missingBookReturns404() throws Exception {
        mvc.perform(get("/api/books/100")
                .header("X-Tenant", "school"))
            .andExpect(handler().methodName("getBook"))
            .andExpect(status().isNotFound())
            .andExpect(content().string(""));
    }

    @Test
    void postJsonReturns201LocationAndJsonBody() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {"title":"Java Testing"}
                    """))
            .andExpect(status().isCreated())
            .andExpect(header().string("Location", "/api/books/8"))
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.id").value(8))
            .andExpect(jsonPath("$.title").value("Java Testing"))
            .andExpect(jsonPath("$.language").value("vi"));
    }

    @Test
    void malformedJsonReturns400() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void wrongRequestContentTypeReturns415() throws Exception {
        mvc.perform(post("/api/books")
                .contentType(MediaType.TEXT_PLAIN)
                .content("Java Testing"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void unsupportedMethodReturns405() throws Exception {
        mvc.perform(put("/api/books/7"))
            .andExpect(status().isMethodNotAllowed());
    }
}
~~~

### Running the example

In the directory containing **pom.xml**, with Maven/JDK 17+:

~~~bash
mvn test
~~~

When the environment downloads dependencies normally, Maven Surefire runs **9 @Test methods** in **BookControllerTest**. Passing criteria are Maven finishing with **BUILD SUCCESS** and **Tests run: 9, Failures: 0, Errors: 0, Skipped: 0** (excluding any extra tests added manually). This describes the expected result of the test suite, not a log captured from a run in this document.

Why doesn't the test need to start a server? **@WebMvcTest(BookController.class)** loads the MVC slice and creates MockMvc, sending requests through DispatcherServlet, handler mapping, argument resolvers, message converters, and exception resolvers using mock servlet requests/responses. It does not open port 8080 and does not call the Internet.

### What does each test actually verify?

- **getMapsPathQueryHeaderAndResponseJson**: tests a request with path, query, and request header; verifies MVC selects method getBook, status 200, response header, media type, and three JSON fields.
- **missingQueryUsesDefaultLanguage**: actually exercises default binding of **@RequestParam(defaultValue="vi")**.
- **missingRequiredHeaderReturns400**: proves a missing header rejects the request at the binding step, without controller code checking it manually.
- **invalidPathVariableReturns400**: proves String → long conversion failure.
- **missingBookReturns404**: the same mapping works, but the data does not exist; distinct from route not found.
- **postJsonReturns201LocationAndJsonBody**: verifies JSON request decoding, HTTP 201, Location header, and JSON response.
- **malformedJsonReturns400**: verifies invalid JSON syntax in the body.
- **wrongRequestContentTypeReturns415**: verifies the **consumes** condition.
- **unsupportedMethodReturns405**: verifies PUT is not among the methods declared for /api/books/7.

If a controller implementation differs from the example code or adds Spring Security, statuses may change due to filters/security policy. In that case declare explicit security expectations, such as mock identity and CSRF token, rather than removing all security filters just to pass the test.

## 9. Verifying request body, Location header, and structured JSON responses

Three aspects need to be distinguished:

**(a) Setting the request body**: use **.contentType(APPLICATION_JSON).content(json)** with MockMvc POST/PUT/PATCH. Calling **.content(...)** without setting Content-Type may cause a mapping with a consumes condition to return 415.

~~~java
mvc.perform(post("/api/books")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"title\":\"Refactoring\"}"))
    .andExpect(status().isCreated())
    .andExpect(header().string("Location", "/api/books/8"))
    .andExpect(jsonPath("$.title").value("Refactoring"));
~~~

**(b) Distinguishing the Location header from body fields**: status 201 + valid JSON without **Location** can still violate a resource creation contract. In the example the server returns a relative path in Location; real API systems may also return an absolute URI. Tests must follow the rule defined by the API.

**(c) Response body is an array or nested object**: apply JSONPath matching the structure:

~~~json
{
  "data": {
    "items": [
      {"id":7,"title":"Spring"},
      {"id":8,"title":"Java"}
    ]
  },
  "total": 2
}
~~~

Matchers can be:

~~~java
.andExpect(jsonPath("$.total").value(2))
.andExpect(jsonPath("$.data.items").isArray())
.andExpect(jsonPath("$.data.items[0].id").value(7))
.andExpect(jsonPath("$.data.items[1].title").value("Java"));
~~~

This snippet is a **fragment for an API returning a nested structure like the sample JSON**, and must not be pasted verbatim into the demo BookController test because the demo controller returns a flat BookView. Contract tests must reflect the real JSON of each endpoint.

For error bodies returning **application/problem+json** per RFC 9457, JSONPath can check **type**, **title**, **status**, **detail**, and **instance** per the contract; do not assume every Spring app automatically returns those exact fields unless ProblemDetail is enabled/configured.

## 10. WebTestClient: same contract, different verification API

For WebFlux, MockMvc does not run the Spring WebFlux pipeline. Use **WebTestClient**, which supports either a mock server or a real server.

WebFlux controller example:

~~~java
@RestController
@RequestMapping("/api/greetings")
class GreetingController {
    record Greeting(String text) {}

    @GetMapping("/{name}")
    Mono<Greeting> greet(
            @PathVariable String name,
            @RequestHeader("X-Lang") String language) {
        return Mono.just(new Greeting(
            language.equals("vi") ? "Xin chào " + name : "Hello " + name));
    }
}
~~~

This is a **fragment**: you need to import **Mono**, **@RestController**, **@RequestMapping**, **@GetMapping**, **@PathVariable**, and **@RequestHeader**. With WebFlux infrastructure, mock test:

~~~java
WebTestClient client =
    WebTestClient.bindToController(new GreetingController()).build();

client.get()
    .uri("/api/greetings/{name}", "An")
    .header("X-Lang", "en")
    .accept(MediaType.APPLICATION_JSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.text").isEqualTo("Hello An");
~~~

**WebTestClient.bindToController(...)** sets up a mock pipeline for **WebFlux**. If you want to use WebTestClient syntax to test a **Spring MVC** controller without starting a server, use:

~~~java
WebTestClient client =
    MockMvcWebTestClient.bindToController(new BookController()).build();
~~~

Import **org.springframework.test.web.servlet.client.MockMvcWebTestClient**; WebTestClient belongs to **org.springframework.test.web.reactive.server.WebTestClient**. The two bindToController calls above are not equivalent: one sets up WebFlux, the other sets up MVC. For an MVC controller with bean dependencies, pass constructed instances or use an appropriate ApplicationContext.

In Spring Boot you can use **@WebFluxTest** for a WebFlux slice, or **@SpringBootTest(webEnvironment = RANDOM_PORT)** combined with WebTestClient to run integration tests against a real HTTP server. When testing through a mock pipeline, status/headers/JSON are verified, but external networking, TLS, and proxies/load balancers remain uncovered.

### Checking JSON, status, and headers with WebTestClient

~~~java
client.get()
    .uri("/api/greetings/An")
    .header("X-Lang", "vi")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
    .expectBody()
    .jsonPath("$.text").isEqualTo("Xin chào An");
~~~

You can use **expectBody(Greeting.class)** to decode into a DTO, **expectBodyList(Greeting.class)** for a list, or **expectBody().json(...)** for structural JSON comparison. For complex generics, use the overload taking **ParameterizedTypeReference<T>**.

For empty responses like HTTP 204, use **expectStatus().isNoContent().expectBody().isEmpty()**. For SSE/NDJSON streams, verify status/headers first, then obtain **FluxExchangeResult** and use **StepVerifier** to inspect data over time; do not try to collect an infinite stream to check a JSON body like a finite response.

## 11. Integrating services, validation, security, and error handlers

An MVC controller typically uses a service:

~~~java
@RestController
class PurchaseController {
    private final PurchaseService service;

    PurchaseController(PurchaseService service) {
        this.service = service;
    }

    @GetMapping("/api/purchases/{id}")
    Purchase find(@PathVariable long id) {
        return service.find(id);
    }
}
~~~

When using **@WebMvcTest(PurchaseController.class)**, the service is not automatically present as in a full application context. With Spring Boot 3.4+/Spring Framework 6.2, use **@MockitoBean** in the test:

~~~java
@WebMvcTest(PurchaseController.class)
class PurchaseControllerTest {
    @Autowired MockMvc mvc;

    @MockitoBean PurchaseService service;

    @Test
    void mapsIdAndSerializesResponse() throws Exception {
        given(service.find(3L)).willReturn(new Purchase(3L));

        mvc.perform(get("/api/purchases/3"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(3));

        then(service).should().find(3L);
    }
}
~~~

Import **org.springframework.test.context.bean.override.mockito.MockitoBean**; **given/then** are from Mockito BDD (static imports). The **PurchaseService/Purchase** types here are illustrative in a pre-declared project; this is **not part of the standalone demo in section 8**.

Use this test to check both directions: the HTTP request bound id properly and the controller called the service with id 3; the JSON response has id 3. Do not mock **DispatcherServlet**, **HandlerMapping**, or **Jackson** when the goal is to verify Spring MVC mapping and converters.

### Validation

When a controller uses **@Valid @RequestBody RequestDto**, test:
- valid body → success (200/201);
- missing required field/constraint failure → status and error JSON per the defined **@ControllerAdvice**;
- malformed JSON syntax → 400 at the converter step, distinct from Bean Validation errors;
- request with no body when **@RequestBody(required=true)** → 400.

Add **spring-boot-starter-validation** if a Spring Boot app relies on Jakarta Bean Validation without an implementation yet. Do not assume simply putting **@NotBlank** on a DTO will work without a validation provider.

### Security

If using Spring Security:
- **@WebMvcTest** may load security filters; anonymous requests may return 401/403, and POST requests may require CSRF depending on configuration.
- For authorized route tests, use **spring-security-test** and **@WithMockUser** or an appropriate request post-processor (if dependencies are present).
- Test anonymous, missing-role, and valid-role cases separately; do not disable filters just to achieve status 200 in a test suite expected to verify policy.
- Sending an **Authorization** request header into MockMvc is not enough to assume authentication succeeded if the app has no filter handling that header.

### When a test truly needs end-to-end

A test with **@SpringBootTest(webEnvironment = RANDOM_PORT)** and an HTTP client connecting to **http://localhost:{port}** passes through the HTTP network and the running app. It is useful when verifying the servlet container, custom filters, full-config serialization, and integrated layers. It carries higher startup and dependency-state costs than a slice test. Do not write every controller test as end-to-end when mapping/JSON assertions can be verified quickly and reliably with MockMvc.

## 12. Common pitfalls when verifying HTTP contracts

| Symptom | Common cause | How to fix |
| --- | --- | --- |
| Calling controller method directly passes even with wrong URL | Skips HandlerMapping | Use MockMvc/WebTestClient to send mock HTTP requests |
| Status 200 but wrong method mapped | Only asserting status | Add MockMvc **handler().methodName(...)** when needed |
| Asserting request header with header().string | Confusing request builder with response matcher | Request uses **.header(...)**, response uses **header().string(...)** |
| POST test returns 415 | Forgot request Content-Type or wrong consumes | Use **.contentType(APPLICATION_JSON)** with JSON body |
| Test receives 406 | Accept incompatible with produces | Check **.accept(...)** and server-supported media types |
| Expected 404 but got 400 | Path variable cannot convert to Java type | Distinguish binding errors from missing data |
| Missing X-Tenant header → 400 | @RequestHeader required | Send header or intentionally design required=false |
| JSONPath $.items[0] fails | Actual response is a different object or root array | Inspect actual response and choose right JSONPath |
| Raw JSON string comparison fails on whitespace | Comparing bytes instead of JSON structure | Use JSONPath or content().json |
| Null JSON field and missing field conflated | Wrong existence matcher | Distinguish exists, hasJsonPath, doesNotHaveJsonPath |
| @WebMvcTest fails to create context | Controller depends on unmocked service bean | Use @MockitoBean or suitable test config |
| POST request in Security-enabled app returns 403 | CSRF/security filter enforces policy | Use proper test security, keep policy intact |
| Tests relying on timestamp/random ID are flaky | Clock/seed not controlled | Inject Clock, create deterministic fixtures |
| Tests pass individually but fail in suite | Tests depend on DB/time/static mutable state | Isolate fixtures, clean data, remove order coupling |
| MVC test does not reflect WebFlux | Using MockMvc with WebFlux pipeline | Use WebTestClient for WebFlux |

### Checklist before accepting an endpoint

1. Send the right method and path, and verify handler/route when mapping is the goal.
2. Check **@PathVariable**, **@RequestParam**, **@RequestHeader**, defaults, and missing/wrong-type cases.
3. For POST/PUT/PATCH, send the right **Content-Type**, request body, and test malformed/mismatched media types.
4. Assert **status** per contract; distinguish success, binding errors, media negotiation errors, and domain errors.
5. Assert key response **headers** such as Content-Type, Location, Cache-Control, ETag, or correlation ID.
6. Assert the **JSON** body via JSONPath or structural comparison; check types, values, nested arrays/objects, and null/missing per schema.
7. Check negative cases (400/404/405/415/406) and security policies if applicable.
8. Use slice tests for controller contracts; add integration tests when full wiring and HTTP networking need coverage.

## 13. Practice exercises

**Exercise 1 – Mapping and negative statuses.** Add **GET /api/books/8** returning another book while keeping GET /api/books/7. Write tests expecting 200 for id=8 and 404 for id=99. Add GET /api/books/abc and verify 400. Explain the difference between a business 404 and a non-existent route.

**Exercise 2 – Query and header.** Add **@RequestParam(defaultValue="10") int limit** and a required **X-Client-Version** header. Write tests where missing limit defaults to 10, limit=5 parses to integer 5, limit=oops → 400, and missing header → 400. When the header has a value, return an echo response header and assert its value.

**Exercise 3 – JSON request and response.** Extend CreateBook with title and author, returning BookView containing a nested author object. Test 201, Location, and **$.author.name**; test malformed JSON, Content-Type text/plain, and a missing field after adding @Valid/@NotBlank with a validation provider.

**Exercise 4 – Arrays and data types.** Create GET /api/books returning a list of two BookViews. Assert the body is an array, its length, **$[0].id** is a number, **$[1].title** is a String, and check ordering if guaranteed by the contract.

**Exercise 5 – WebFlux.** Write a controller returning **Mono<BookView>** and test it with **WebTestClient.bindToController**. Compare fluent expectations and explain why this test should not use MockMvc to test a WebFlux pipeline.

## Official documentation

- [Spring Framework 6.2 – MockMvc](https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework.html)
- [Spring Framework 6.2 – MockMvc defining expectations](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/hamcrest/expectations.html)
- [Spring Framework 6.2 – WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [Spring Boot 3.5 – Testing Spring MVC applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework – @MockitoBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html)
