# @RequestMapping, HTTP Methods, consumes, and produces

When an HTTP request enters a Spring Boot application, the framework must decide **which controller method gets called**. That decision does not depend solely on the URL: the same path can be served differently depending on the **HTTP method** (`GET`, `POST`, `PUT`...), the **Content-Type of the incoming payload** (`consumes`), the **Accept header for the desired output** (`produces`), query parameters, and other headers.

In Spring Framework, `@RequestMapping` describes these routing conditions. The `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping`, and `@DeleteMapping` annotations are shortcuts that help code express a specific HTTP method. In Spring Boot, a controller method is only invoked when the request satisfies **all effective mapping conditions**.

This lesson belongs to the **Web Routing** group and focuses on **`@RequestMapping`, HTTP methods, `consumes`, and `produces`**. The examples run on **Spring Boot 3.3.13, Spring MVC, Java 21, and Gradle**. Spring WebFlux also supports the annotated request mappings model and corresponding `consumes`/`produces` concepts, though its HTTP processing runtime differs from Servlet MVC. The examples below intentionally use `spring-boot-starter-web` to clearly illustrate Servlet/Spring MVC.

## 1. Routing is matching multiple conditions

Request mapping can be pictured as a set of conditions:

~~~text
HTTP request
    |
    v
Servlet container / DispatcherServlet
    |
    v
RequestMappingHandlerMapping
    |
    +-- Path matches?              /api/items/42
    +-- HTTP method matches?       GET
    +-- Params match?              q, mode=summary...
    +-- Headers match?             X-Client=demo...
    +-- Consumes matches?          Content-Type: application/json
    +-- Produces matches?          Accept: application/json
    |
    +-- Select the best matching mapping
    |
    v
RequestMappingHandlerAdapter
    |
    v
Controller method + argument binding
    |
    v
Return value / message conversion / HTTP response
~~~

This is a conceptual description, not a rigid algorithmic order for every step. Spring has a mechanism to find and rank candidate mappings; if two mappings are equivalent to the point that the framework cannot choose uniquely, an **ambiguous mapping** error can occur.

Key point: **mapping is the step of finding the handler**, whereas `@RequestBody`, `@RequestParam`, and `@PathVariable` are the step of **passing data into method parameters** after the mapping has been chosen. `@ResponseBody` and message converters deal with **writing the response**. Do not mix these three responsibilities.

### 1.1. General annotation structure

~~~java
@RequestMapping(
    path = "/api/items",
    method = RequestMethod.POST,
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ItemView create(@RequestBody CreateItemRequest request) {
    // ...
}
~~~

This is a **code fragment** illustrating syntax; the types `ItemView`, `CreateItemRequest`, and the method body must be defined in the application. Meaning: the handler only accepts POST requests to `/api/items` with a JSON body and can produce a JSON representation accepted by the client.

Equivalent in terms of the HTTP method condition:

~~~java
@PostMapping(
    path = "/api/items",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ItemView create(@RequestBody CreateItemRequest request) {
    // ...
}
~~~

In a real application, use only **one** of these mapping annotations on the same method; do not stack `@RequestMapping` and `@PostMapping`.

## 2. Six condition groups of @RequestMapping

| Attribute | Matches against | Example |
| --- | --- | --- |
| `path` / `value` | Request URL path | `"/api/items/{id}"` |
| `method` | HTTP request method | `RequestMethod.GET`, `RequestMethod.POST` |
| `params` | Query/form parameter conditions | `"q"`, `"mode=full"`, `"!debug"` |
| `headers` | HTTP header conditions | `"X-Client=demo"`, `"!X-Legacy"` |
| `consumes` | Media type of the **request body** via `Content-Type` | `"application/json"` |
| `produces` | Response media type the client **accepts** via `Accept` | `"application/json"`, `"text/plain"` |

The conditions work together: if a mapping requires `POST` + `Content-Type: application/json` + `Accept: application/json`, a request that only matches the URL while sending `text/plain` may not enter that handler.

Within an attribute that has multiple options, Spring supports corresponding expressions and matching rules. For example, `consumes = {"application/json", "application/xml"}` allows **either media type**, rather than requiring the body to be both JSON and XML simultaneously. With `params={"q","mode=full"}`, all expression conditions must be met together.

### 2.1. path and value

`value` is an alias for `path`. The following two forms express the same pattern:

~~~java
@GetMapping("/api/items/{id}")
@GetMapping(path = "/api/items/{id}")
~~~

These are two alternative ways to write it, **not two mappings declared together on one method**.

Common patterns:

- `/api/items`: a collection endpoint.
- `/api/items/{id}`: a path variable bound via `@PathVariable`.
- `/api/items/search`: a static path for searching.
- `/api/files/**`: a multi-level pattern subject to path matching configuration.

Do not assume all path matching treats case sensitivity, trailing slashes, or suffix extensions the same way. Spring Framework 6 uses PathPattern in its common default configuration; trailing slash handling and matcher options can differ from earlier Spring 5 applications.

### 2.2. Controller class and methods

Declare at the class level to share a common prefix:

~~~java
@RestController
@RequestMapping("/api/items")
public class ItemController {

    @GetMapping("/{id}")
    public ItemView get(@PathVariable long id) {
        // ...
    }

    @PostMapping
    public ItemView create(@RequestBody CreateItemRequest body) {
        // ...
    }
}
~~~

This is a **skeleton**. The effective mappings are `GET /api/items/{id}` and `POST /api/items`, respectively. The class-level prefix combines with the method-level path; do not read `@GetMapping("/{id}")` as a root endpoint `/{id}`.

For `consumes` and `produces`, **a method-level declaration can override rather than accumulate onto a class-level declaration**. That is an important exception when designing APIs. For instance, if the class-level has `produces="application/json"` while a method declares `produces="text/plain"`, that method can return plain text; it does not require JSON and plain text at the same time. Avoid putting class-level media restrictions if multiple endpoints intentionally serve different content types.

## 3. HTTP methods and API contract correctness

The HTTP method is part of request routing. It conveys protocol semantics, not merely syntax:

| Method | Common meaning | Mapping annotation |
| --- | --- | --- |
| `GET` | Retrieves a resource representation, normally without changing server state | `@GetMapping` |
| `HEAD` | Retrieves metadata of a GET without receiving a response body | `@RequestMapping(method=HEAD)` if declared separately |
| `POST` | Submits data for processing or creates a resource | `@PostMapping` |
| `PUT` | Replaces/sets resource state at the target URI | `@PutMapping` |
| `PATCH` | Partially updates a resource | `@PatchMapping` |
| `DELETE` | Requests deletion of a resource | `@DeleteMapping` |
| `OPTIONS` | Queries HTTP/communication options | `@RequestMapping(method=OPTIONS)` if customization is needed |

**GET** should be safe; **PUT** and **DELETE** are designed to be idempotent under HTTP semantics when implemented properly. POST is not idempotent by default. These properties depend on endpoint logic and are not automatically guaranteed solely by the annotation.

### 3.1. @RequestMapping without a method

If you write:

~~~java
@RequestMapping("/api/ping")
public String ping() {
    return "pong";
}
~~~

then the mapping **is not automatically restricted to GET only**. It can accept multiple HTTP methods (provided other conditions match), which is not necessarily desirable for a public API.

You should write:

~~~java
@GetMapping("/api/ping")
public String ping() {
    return "pong";
}
~~~

When the method is in a `@RestController`, the returned string is written as the response body. If the method is in a `@Controller` without `@ResponseBody`, the same string can be interpreted as a view name; this is **return-value handling**, not a mapping condition.

### 3.2. HEAD and OPTIONS

Spring MVC can automatically provide **HEAD** support for GET mappings and handle **OPTIONS** based on mapped methods, depending on settings and handlers. When developing an API, verify with real clients and tests rather than assuming every status/header just by looking at the @GetMapping name.

An unsupported HTTP method for a path can result in **405 Method Not Allowed** and an appropriate `Allow` header. Distinguish **a non-existent path (404)** from **a mapped path with the wrong method (405)**.

### 3.3. Avoid using HTTP methods as an authorization mechanism

`@PostMapping` does not mean an endpoint is protected; GET is not automatically public either. Authentication, authorization, and CSRF are security configuration responsibilities. Do not use "only accepts POST" as a security measure in place of Spring Security, policies, and input verification.

## 4. consumes: restricting request Content-Type

`consumes` answers the question:

> What format is this handler allowed to receive in the request body?

Example:

~~~java
@PostMapping(
    path = "/api/items",
    consumes = MediaType.APPLICATION_JSON_VALUE
)
public ItemView create(@RequestBody CreateItemRequest body) {
    // ...
}
~~~

Client calls:

~~~http
POST /api/items HTTP/1.1
Content-Type: application/json

{"name":"Notebook"}
~~~

then the mapping can match `consumes` and the JSON converter is used to read the body into a Java object.

If the client sends:

~~~http
POST /api/items HTTP/1.1
Content-Type: text/plain

Notebook
~~~

then with an endpoint that only accepts JSON, the result can be **415 Unsupported Media Type**. In many cases, the request is rejected **before the controller method runs**.

### 4.1. consumes uses Content-Type, not Accept

A common confusion:

- `Content-Type: application/json` states that **the request body contains JSON**.
- `Accept: application/json` states that **the client wants a JSON response**.

Sending the right `Accept` with the wrong `Content-Type` still fails to satisfy an endpoint with `consumes=application/json`. Conversely, sending valid JSON with `Accept: application/xml` can be rejected on the `produces` side if the endpoint only produces JSON.

### 4.2. Media types

| Media type | Common incoming payload |
| --- | --- |
| `application/json` | JSON body |
| `application/xml` | XML body, requires appropriate converter and dependencies |
| `text/plain` | Plain text string |
| `application/x-www-form-urlencoded` | URL-encoded form fields |
| `multipart/form-data` | Multipart form upload, commonly using `@RequestPart`/`MultipartFile` in MVC |
| `application/octet-stream` | Generic binary data |

**Declaring consumes does not automatically install a parser/codec.** `consumes="application/xml"` only sets a mapping condition; binding XML to an object requires a suitable message converter on the classpath and configuration. Likewise, JSON requires the right converter and a record/DTO shaped so the converter can read it.

### 4.3. Multiple consumes options and media type parameters

You can write:

~~~java
@PostMapping(
    path = "/api/import",
    consumes = {"application/json", "text/plain"}
)
~~~

This is an **annotation fragment**, allowing either request type. The controller must still design suitable parameters or choose separate methods, avoiding looking only at the mapping while overlooking binding.

`application/json;charset=UTF-8` is normally compatible with the `application/json` media type when the charset parameter is not specifically constrained in the mapping. If you declare parameters in a media type condition yourself, the value must follow matching rules; do not over-constrain with charset strings unless required.

### 4.4. Consumes does not mean a request is guaranteed to contain a body

`consumes` is a condition on the request media type, not an annotation requiring a body to be present. `@RequestBody(required=true)` (the default) is what directly governs requiring a readable body during binding. A request with the right Content-Type but an empty body can still be rejected during parameter reading.

Do not mechanically apply `consumes="application/json"` to every GET: many GET requests have no request body and send no Content-Type. Doing so can cause mappings to fail unnecessarily.

## 5. produces: restricting response media type according to Accept

`produces` answers the question:

> Which representation can this endpoint provide to the client?

Example:

~~~java
@GetMapping(
    path = "/api/items/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ItemView find(@PathVariable long id) {
    // ...
}
~~~

If the request has `Accept: application/json`, the mapping matches. If it only accepts `text/plain` while the endpoint only produces JSON, the server can return **406 Not Acceptable**.

Unlike `consumes`, `produces` **does not control how the request body is read**; it is a condition for the representation the client receives.

### 5.1. Missing Accept or */*

Many HTTP clients send `Accept: */*` or omit Accept; this means the client does not strictly restrict the representation. When there is only one JSON handler, Spring can usually return JSON based on converter capabilities.

If there are **two methods with the same path and HTTP method but different produces**, an `Accept: */*` request can make the choice ambiguous; design content negotiation or default behavior intentionally and test it. Do not rely on the declaration order of methods in the Java file to pick the default endpoint.

### 5.2. Accept with q-values

A client can express preference weights:

~~~http
Accept: application/json;q=0.9, text/plain;q=0.1
~~~

Spring applies media type matching rules and selects appropriately. `q` is a client preference weight, not a probability, and it does not automatically install any converter. A writer capable of producing the selected format is still required.

### 5.3. produces does not replace @ResponseBody

`produces="application/json"` does not automatically turn a `String` from `@Controller` into JSON. How the framework interprets the return value still depends on `@ResponseBody`, `@RestController`, `ResponseEntity`, or the view mechanism.

Example:

~~~java
@RestController
class MessageController {
    @GetMapping(path = "/message", produces = "text/plain")
    public String message() {
        return "hello";
    }
}
~~~

This is an **illustrative class snippet** that can live in a configured Spring Boot application; `@RestController` ensures the String is the response body and `text/plain` is the designated representation.

## 6. Media type routing and message conversion are two separate steps

Understand the two stages:

~~~text
Stage A: Request mapping
    POST /api/items
    Content-Type: application/json
    Accept: application/json
        |
        +-- Does @PostMapping(consumes="application/json",
                             produces="application/json")
                             match?
        |
        v
Stage B: Invoke controller and convert data
    JSON -> @RequestBody CreateItemRequest
    controller business logic
    ItemView -> JSON response body
~~~

Even when the mapping matches, a request can fail during the conversion stage:

- Invalid JSON → may return **400 Bad Request**.
- Valid JSON body but missing required fields per validation → may return **400** if validation is enabled/configured properly.
- Body/DTO type cannot be converted → body-reading error, distinct from a URL error.
- Controller throws an exception → may return 4xx/5xx depending on exception handlers.
- Converter cannot write the suitable response format → conversion or content negotiation error may occur.

In **Spring MVC**, these readers/writers normally go through `HttpMessageConverter` (Jackson JSON, String converter...). In **Spring WebFlux**, the analogous concept uses `HttpMessageReader` and `HttpMessageWriter` in a reactive pipeline. The same mapping annotations do not mean the same runtime.

### 6.1. When to add validation?

Spring Boot 3.x typically needs:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
~~~

if you want to use Jakarta Bean Validation such as `@NotBlank` or `@Valid`. Do not assume that having only `spring-boot-starter-web` makes every constraint annotation apply automatically.

## 7. Combining multiple conditions in @RequestMapping

A handler can simultaneously require path, method, params, headers, and media types:

~~~java
@RequestMapping(
    path = "/api/reports",
    method = RequestMethod.POST,
    params = "mode=summary",
    headers = "X-Client=internal",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ReportView summarize(@RequestBody ReportInput input) {
    // ...
}
~~~

This is an illustrative syntax snippet; `ReportInput` and `ReportView` are application-defined types, not built-in Spring classes.

The request must satisfy:

1. Path `/api/reports`.
2. HTTP method POST.
3. Query/form parameter `mode` with value `summary`.
4. Header `X-Client` with value `internal`.
5. Request Content-Type is application/json.
6. Accept allows application/json.

If any condition is unmet, the method is not a valid candidate. The specific error status can vary depending on which condition failed, other mappings, error handling, and configuration.

### 7.1. params: present, absent, equals value

~~~java
@GetMapping(path = "/search", params = "q")
@GetMapping(path = "/search", params = "!q")
@GetMapping(path = "/search", params = "mode=full")
@GetMapping(path = "/search", params = "mode!=full")
~~~

These are **four independent example annotations**—do not place all four on the same method. They respectively require `q` to be present, `q` to be absent, `mode=full`, or `mode` not equal to `full` per expression semantics.

If you merely want `q` to be optional, it is usually simpler to use `@RequestParam(required=false)` or `Optional<String>` on **one** handler instead of creating multiple mappings that can collide.

### 7.2. headers and media types

~~~java
@GetMapping(path = "/partner", headers = "X-Client=demo")
~~~

requires the request to have the `X-Client` header with value `demo`.

Spring recommends using `consumes` instead of trying to describe Content-Type in `headers`, and `produces` instead of describing Accept in `headers`. Those two media type attributes have specialized matching and content negotiation rules.

### 7.3. One URL can serve multiple endpoints

The same `/api/echo` can accept:

- POST JSON → handler receiving a DTO via `@RequestBody`.
- POST URL-encoded form → handler receiving `@RequestParam`.
- GET → endpoint reading data or returning guidance.

This is not an ambiguous mapping as long as the conditions are distinguishable. Conversely, two `@PostMapping(path="/api/echo",consumes="application/json")` with the same conditions usually conflict; changing the Java method name does not change the URL conditions.

## 8. Runnable example: Spring Boot 3.3 + Java 21 + Gradle

We will build a REST API demonstrating:

- `@GetMapping` by ID.
- The same `GET /representation` returning JSON or text based on `Accept`.
- The same `POST /echo` accepting JSON or URL-encoded form based on `Content-Type`.
- `@RequestMapping(method = PUT)` accepting text/plain.
- `params` and `headers` to illustrate additional conditions.
- Testing 404, 405, 406, and 415 errors with MockMvc.

The project structure:

~~~text
routing-media-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/routing/
    │   ├── RoutingDemoApplication.java
    │   └── CatalogController.java
    └── test/java/com/example/routing/
        └── CatalogControllerTest.java
~~~

### 8.1. Gradle configuration

**settings.gradle**

~~~groovy
rootProject.name = 'routing-media-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The starter-web dependency provides Spring MVC, Jackson JSON in the default starter configuration, and embedded Tomcat. Starter test supports JUnit 5 and MockMvc; you do not need to install a separate Tomcat to run the example.

### 8.2. Spring Boot main class

**src/main/java/com/example/routing/RoutingDemoApplication.java**

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

The main class package is the parent of the controller; Spring component scanning finds `CatalogController`.

### 8.3. Complete controller

**src/main/java/com/example/routing/CatalogController.java**

~~~java
package com.example.routing;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/catalog")
public class CatalogController {

    public record Item(long id, String name) {
    }

    public record CreateItemRequest(String name) {
    }

    @GetMapping(path = "/items/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Item> find(@PathVariable long id) {
        if (id != 1L) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(new Item(1L, "Notebook"));
    }

    @GetMapping(path = "/representation",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> representationJson() {
        return Map.of("message", "hello");
    }

    @GetMapping(path = "/representation",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String representationText() {
        return "hello";
    }

    @PostMapping(path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> echoJson(
            @RequestBody CreateItemRequest request) {
        if (request.name() == null || request.name().isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "name must not be blank");
        }
        return Map.of("source", "json", "name", request.name());
    }

    @PostMapping(path = "/echo",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> echoForm(@RequestParam String name) {
        if (name.isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "name must not be blank");
        }
        return Map.of("source", "form", "name", name);
    }

    @RequestMapping(path = "/manual",
            method = RequestMethod.PUT,
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String manual(@RequestBody String body) {
        return "received:" + body;
    }

    @GetMapping(path = "/search", params = "q",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> search(@RequestParam String q) {
        return Map.of("query", q);
    }

    @GetMapping(path = "/partner", headers = "X-Client=demo",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> partner() {
        return Map.of("access", "demo");
    }
}
~~~

**How to read it:**

- Class-level path `/api/catalog` is the prefix for all endpoints.
- `find` only accepts GET, returns JSON, and determines 404 itself if ID is not 1.
- Both `representationJson` and `representationText` have the same URL + method but different `produces`; chosen via `Accept`.
- Both `echoJson` and `echoForm` have the same URL + method but different `consumes`; chosen via `Content-Type`.
- `manual` illustrates `@RequestMapping(method=RequestMethod.PUT)` equivalent in HTTP method to `@PutMapping`.
- `search` is a mapping candidate only when query param `q` is present.
- `partner` only matches when header `X-Client=demo` is present.
- The body checks inside the controller take place **after mapping succeeds**.

The demo code does not use a database and does not persist POSTed objects. A POST with a body that immediately returns a result does not have to return 201 Created; for instance, `echo` returns the default **200 OK**, fitting the echo meaning without creating a resource.

## 9. Running and sending HTTP requests

With JDK 21 and a compatible Gradle version (for example 8.5), if there is no wrapper yet:

~~~bash
gradle wrapper --gradle-version 8.5
./gradlew bootRun
~~~

If the project already has a Gradle wrapper, simply run `./gradlew bootRun`. On Windows PowerShell use `.\gradlew.bat bootRun`. By default the application normally starts Tomcat on port 8080 unless configured otherwise.

### 9.1. GET JSON by path

~~~bash
curl -i \
  -H "Accept: application/json" \
  http://localhost:8080/api/catalog/items/1
~~~

Expected HTTP **200** and JSON with data:

~~~json
{"id":1,"name":"Notebook"}
~~~

For `/api/catalog/items/2`, the controller decides to return **404 Not Found**, not because path mapping failed, but because the logic did not find the resource.

### 9.2. Same GET path but two representations

JSON:

~~~bash
curl -i \
  -H "Accept: application/json" \
  http://localhost:8080/api/catalog/representation
~~~

Expected:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"message":"hello"}
~~~

Text:

~~~bash
curl -i \
  -H "Accept: text/plain" \
  http://localhost:8080/api/catalog/representation
~~~

Expected:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain

hello
~~~

These are **outlines of the significant lines**, not verbatim copies of all actual headers: Tomcat and Spring may add headers, charsets, or change order. Note that `Accept` must be sent explicitly, because in the demo there are two different endpoints sharing the same path/method.

### 9.3. Same POST /echo but two request content types

Sending JSON:

~~~bash
curl -i -X POST \
  http://localhost:8080/api/catalog/echo \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"name":"Lan"}'
~~~

Expected HTTP **200** and:

~~~json
{"source":"json","name":"Lan"}
~~~

Sending form:

~~~bash
curl -i -X POST \
  http://localhost:8080/api/catalog/echo \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Accept: application/json" \
  --data-urlencode "name=Lan"
~~~

Expected HTTP **200** and:

~~~json
{"source":"form","name":"Lan"}
~~~

Both share the same path and HTTP method, yet Spring selects **two different controller methods** thanks to `consumes`. The `name` parameter does not decide the handler here; `Content-Type` is the distinguishing condition.

### 9.4. PUT text/plain

~~~bash
curl -i -X PUT \
  http://localhost:8080/api/catalog/manual \
  -H "Content-Type: text/plain" \
  -H "Accept: text/plain" \
  --data-binary "abc"
~~~

Expected HTTP **200** with body:

~~~text
received:abc
~~~

When sending `POST` instead of PUT to `/manual`, the request is likely to return **405 Method Not Allowed** if no other POST mapping exists for the same path.

### 9.5. params and headers

~~~bash
curl -i \
  -H "Accept: application/json" \
  "http://localhost:8080/api/catalog/search?q=java"

curl -i \
  -H "Accept: application/json" \
  -H "X-Client: demo" \
  "http://localhost:8080/api/catalog/partner"
~~~

Corresponding JSON results:

~~~json
{"query":"java"}
~~~

~~~json
{"access":"demo"}
~~~

Do not use the `X-Client` header in the demo as proof of authentication. It is only a **route condition** that any client can easily forge; real internal APIs still require authentication, authorization, and gateway controls.

## 10. Testing routing with MockMvc

Do not test only 200 statuses; test **invalid methods, invalid consumes, and incompatible produces** as well. That is how you verify actual mapping conditions.

**src/test/java/com/example/routing/CatalogControllerTest.java**

~~~java
package com.example.routing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CatalogController.class)
class CatalogControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getItemReturnsJson() throws Exception {
        mvc.perform(get("/api/catalog/items/1")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("Notebook"));
    }

    @Test
    void getMissingItemReturns404() throws Exception {
        mvc.perform(get("/api/catalog/items/2")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isNotFound());
    }

    @Test
    void getSamePathWithDifferentAccept() throws Exception {
        mvc.perform(get("/api/catalog/representation")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("hello"));

        mvc.perform(get("/api/catalog/representation")
                .accept(MediaType.TEXT_PLAIN))
            .andExpect(status().isOk())
            .andExpect(content().string("hello"));
    }

    @Test
    void postJsonUsesJsonHandler() throws Exception {
        mvc.perform(post("/api/catalog/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Lan\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.source").value("json"));
    }

    @Test
    void postFormUsesFormHandler() throws Exception {
        mvc.perform(post("/api/catalog/echo")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .accept(MediaType.APPLICATION_JSON)
                .param("name", "Lan"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.source").value("form"));
    }

    @Test
    void unsupportedRequestContentTypeReturns415() throws Exception {
        mvc.perform(post("/api/catalog/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .accept(MediaType.APPLICATION_JSON)
                .content("Lan"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void unacceptableResponseTypeReturns406() throws Exception {
        mvc.perform(post("/api/catalog/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_XML)
                .content("{\"name\":\"Lan\"}"))
            .andExpect(status().isNotAcceptable());
    }

    @Test
    void wrongHttpMethodReturns405() throws Exception {
        mvc.perform(post("/api/catalog/manual")
                .contentType(MediaType.TEXT_PLAIN)
                .content("abc"))
            .andExpect(status().isMethodNotAllowed());
    }

    @Test
    void putManualReturnsText() throws Exception {
        mvc.perform(put("/api/catalog/manual")
                .contentType(MediaType.TEXT_PLAIN)
                .accept(MediaType.TEXT_PLAIN)
                .content("abc"))
            .andExpect(status().isOk())
            .andExpect(content().string("received:abc"));
    }

    @Test
    void requestParamAndHeaderConditionsMatch() throws Exception {
        mvc.perform(get("/api/catalog/search")
                .param("q", "java")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.query").value("java"));

        mvc.perform(get("/api/catalog/partner")
                .header("X-Client", "demo")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.access").value("demo"));
    }
}
~~~

Run tests:

~~~bash
./gradlew test
~~~

In `@WebMvcTest`, MockMvc runs the Spring MVC test slice without opening a real network socket; it verifies matching, argument binding, and response conversion. Since the example controller needs no service beans, no external dependencies need mocking. If the application adds Spring Security or custom web filters, test outcomes may be affected and require proper auth/CSRF configuration.

Strength of the test suite: when changing `consumes`/`produces` or adding new mappings, the 415/406/405 cases catch unintended behavior before deployment.

## 11. Four key HTTP errors when debugging mappings

| Status | Brief description | First question to ask |
| --- | --- | --- |
| **404 Not Found** | No matching mapping/resource, or controller intentionally returned 404 | Path, context path, controller scan, does resource exist? |
| **405 Method Not Allowed** | Path can be served, but HTTP method is not supported | Was GET or POST/PUT sent? |
| **415 Unsupported Media Type** | Content-Type/request representation is not accepted | Is the body JSON, form, or text? |
| **406 Not Acceptable** | No response representation matches Accept | Did the client ask for JSON, XML, or text? |

These codes are not "one error with one single cause":

- 404 can also occur because a business resource does not exist.
- 405 can occur at the web layer even before a controller runs.
- 415 can relate to mapping `consumes` or a converter unable to read the request media type.
- 406 can relate to `produces` or being unable to select a suitable writer.

### 11.1. An ordered diagnostic example

Suppose a client calls `POST /api/catalog/echo` and gets 415.

1. Check the URL, context path, and HTTP method.
2. Print the actual request headers; is `Content-Type` present?
3. If sending text/plain while the endpoint only accepts JSON/form, fix the request per contract.
4. If JSON was sent, check whether the media type has unusual parameters.
5. Check whether the mapping has multiple handlers with different `consumes`.
6. If the mapping is right yet it still fails, inspect message converters and deserialization capability.
7. Read logs/tests to distinguish a mapping error from an argument resolution error.

If the client receives 406, shift focus to `Accept` and response representation generation. Do not reflexively change `Content-Type`, as it answers a different question.

### 11.2. Avoid equating CORS with mapping

Browsers can issue an **OPTIONS preflight** before cross-origin POST/PUT requests. If CORS is not configured, the browser can block the request even though the controller `@PostMapping` is correct. Do not change an endpoint to GET to "dodge CORS"; configure the CORS policy at the right layer, verify allowed preflight methods/headers, and restrict trusted origins.

### 11.3. Reverse proxies and context paths

An external request may pass through a gateway with prefix `/service-a`, while the application receives `/api/catalog`. If the gateway rewrites the path, controller mappings match the path **after rewriting**, not necessarily the exact URL shown in the browser.

When getting 404 in production while working locally, inspect `server.servlet.context-path`, proxy rewrites, forwarded headers, route configuration, and actual logs.

## 12. Why can two mappings be ambiguous?

Spring selects the best mapping based on matching conditions. A common conflict:

~~~java
@GetMapping("/api/items")
public Object one() { ... }

@GetMapping("/api/items")
public Object two() { ... }
~~~

This is an **illustrative anti-pattern**, not source code to use. Because both methods have the same conditions, the framework can report an ambiguous mapping error when creating the application context.

Another case:

~~~java
@GetMapping(path = "/api/value", produces = "application/json")
public Object json() { ... }

@GetMapping(path = "/api/value", produces = "text/plain")
public Object text() { ... }
~~~

They are not identical because `produces` differs; however, a client sending `Accept: */*` may not provide enough information to choose as desired. Safe design approaches depend on the API:

- Use different paths when two representations carry different business semantics.
- Define a clear Accept contract and test with common Accept headers.
- Avoid declaring duplicate mappings just as a "fallback".
- If the application needs a default representation, design the priority explicitly rather than assuming Spring picks the method declared first.

When encountering ambiguous mapping at startup, examine all **mapping conditions**, not just Java method names; renaming `one()` to `oneV2()` typically will not resolve the conflict.

## 13. Annotation inheritance, composition, and edge cases

### 13.1. Shortcuts are composed annotations

`@GetMapping` is built on `@RequestMapping(method = RequestMethod.GET)`. The same applies to POST/PUT/PATCH/DELETE annotations.

Choose the shortcut when the method is clear. Only use `@RequestMapping(method=...)` when you want multiple methods to share one handler or when building controlled composed annotations.

### 13.2. Do not put multiple mapping annotations on the same element

Do not do this:

~~~java
@GetMapping("/x")
@PostMapping("/x")
public String mixed() { ... }
~~~

Multiple composed `@RequestMapping` annotations on the same method do not create a single valid mapping for two methods in the expected way; the framework may only use the first annotation and log a warning.

If you genuinely need the same implementation for multiple HTTP methods, declare it explicitly:

~~~java
@RequestMapping(
    path = "/x",
    method = {RequestMethod.GET, RequestMethod.POST}
)
public String mixed() {
    return "ok";
}
~~~

This is an **illustrative snippet**, not advice that GET and POST should always share logic. Re-check safety/idempotency semantics and security policy before merging them.

### 13.3. params and headers are not authentication

`params="apiKey"` only checks that the parameter is present, not that the API key is valid. `headers="X-Client=partner"` only checks the header string, which the client can fill in itself. Use proper security filters/configuration, token signature verification, and access policies.

### 13.4. consumes/produces do not guarantee security or data validation

`consumes="application/json"` does not automatically validate the payload or protect against attacks. You need request size limits, input validation, authentication/authorization, proper output encoding, and control over sensitive serialization.

### 13.5. Multipart and form data require matching APIs

`multipart/form-data` typically uses `MultipartFile`/`@RequestPart` in Spring MVC and `application/x-www-form-urlencoded` typically uses `@RequestParam`/form binding. Do not default to `@RequestBody MyDto` for every format because converters and binding differ.

### 13.6. Media types with versioning

Some APIs use vendor media types like `application/vnd.example.v2+json`. This can be part of content negotiation, yet it requires a clear contract and message writers capable of producing/reading the corresponding media type. Do not assign multiple media types just so clients always match; versioning needs compatible design.

## 14. Best practices for designing routing contracts

1. **Declare HTTP methods explicitly** on every endpoint, preferring `@GetMapping`/`@PostMapping`/... .
2. **Use stable, meaningful URLs**, distinguishing collection and item resources.
3. **Declare `consumes` when an endpoint accepts specific body formats**, especially when the same URL has handlers for JSON and forms.
4. **Declare `produces` when the response contract needs explicit formats**, e.g. JSON vs. text/SSE.
5. **Use `MediaType` constants** instead of arbitrary hardcoded media type strings.
6. **Separate mapping from data binding**; do not assume `@RequestBody` replaces `consumes`.
7. **Do not implicitly use `@RequestMapping` without a method** for GET-only APIs.
8. **Ensure no ambiguous mappings** exist in the same context and deployment path.
9. **Test Accept/Content-Type both positively and negatively**, including 405, 415, and 406.
10. **Do not use headers/params mappings to replace authentication and authorization**.
11. **Review class-level `consumes`/`produces`** before overriding with method-level declarations.
12. **Align gateway, context path, and CORS**, not just controller annotations.
13. **Verify empirically with integration tests** when custom converters, proxies, or special API clients are involved.
14. **Document error responses/schemas**, since the same status code can originate from multiple processing layers.

## 15. Checklist when coding or reviewing an endpoint

Before accepting a new route, ask yourself:

- Is the HTTP method declared clearly? Does it fit safe/idempotent semantics?
- Do the class-level path and method-level path combine into the right URI?
- Are `params` or `headers` conditions needed to select the route? Is there a risk of sharing conditions with another route?
- What media type is the request body sent in? Does `consumes` match and is there a converter to read it?
- What `Accept` header is the client expected to send? Does `produces` match and is there a writer to generate it?
- Have you distinguished request `Content-Type` from response `Content-Type`?
- Are `@RequestBody`, `@RequestParam`, and `@PathVariable` bound properly?
- Does the DTO have necessary validation and clear error handling?
- For invalid requests, are 400/404/405/406/415 behaviors consistent and tested?
- For `Accept: */*` or missing Accept, is behavior clearly defined and unambiguous?
- Do reverse proxy rewrites, context paths, or CORS alter the actual request?
- Does authorization use a security policy instead of assuming POST/headers are enough?
- Are JSON/form endpoints sharing the same URL tested separately?
- Are you using Spring MVC or WebFlux for the intended stack? Are both starters on the classpath?
- Does documentation or an OpenAPI contract fully describe the method and request/response media types?

**Conclusion:** `@RequestMapping` selects a controller method by **path + HTTP method + params/headers conditions + media types**. `consumes` controls which **request Content-Type** values are accepted; `produces` controls which **response** types can be served according to `Accept`. They are **routing** conditions, not substitutes for body binding, JSON conversion, input validation, or security. Understanding this exact boundary helps design clear API contracts, avoid ambiguous mappings, and properly explain 405, 415, and 406 errors.

## References

- [Spring Framework — Spring MVC Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): path, method, params, headers, consumes, produces; class/method-level conditions.
- [Spring Framework — Spring WebFlux Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html): corresponding annotated routing on the reactive stack.
- [Spring Framework 6.1 — @RequestMapping Javadoc](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/bind/annotation/RequestMapping.html): detailed attribute descriptions.
- [Spring Boot 3.3 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html): compatible Java, Gradle, and Servlet containers.
- [Spring Boot 3.3 — Gradle Plugin](https://docs.spring.io/spring-boot/3.3/gradle-plugin/): plugin, dependency management, and running applications.
