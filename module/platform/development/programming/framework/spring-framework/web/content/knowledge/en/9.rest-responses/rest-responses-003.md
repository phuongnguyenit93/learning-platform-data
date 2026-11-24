# @ResponseStatus, Bodyless Responses, and Null Body Cases in Spring MVC

## 1. Objective

In REST APIs, **HTTP status** and **HTTP response body** are two separate concerns. A handler can succeed with a JSON body, succeed without a body, or fail to find a resource. In Spring MVC, returning `null` from a controller **does not automatically** mean HTTP 204 or 404. This lesson explains this exact behavior, how to use `@ResponseStatus` and `ResponseEntity`, how to distinguish an *absent body* from a *JSON `null` value*, and how to test results over HTTP.

After this lesson, you will be able to:

- Attach a fixed status to a handler with `@ResponseStatus` and understand the limitations of `reason`.
- Explicitly choose HTTP 200, 201, 202, 204, and 404 for REST scenarios.
- Use `void`, `ResponseEntity<Void>`, `ResponseEntity.noContent().build()`, and `ResponseEntity.notFound().build()` appropriately.
- Distinguish `return null`, `ResponseEntity.ok().body(null)`, JSON literal `null`, and a property with a null value inside a JSON object.
- Avoid sending content in 204 responses; write MockMvc tests that verify the actual status and body.

Examples are designed for **Spring MVC Servlet stack, Java 17+, Spring Boot 3.x**. The HTTP principles themselves are framework-independent. If your project uses Spring WebFlux, reactive APIs like `Mono` and `ServerResponse` follow their own operational rules; do not apply Servlet MVC examples mechanically.

## 2. HTTP Status Is Separate from Whether a Body Exists

Consider these illustrative responses:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":1,"name":"Spring"}
~~~

~~~http
HTTP/1.1 200 OK

~~~

~~~http
HTTP/1.1 204 No Content

~~~

The second response has **200 OK, empty body**. The third response has **204 No Content**, which carries a stronger semantic message: the request succeeded and there is no response content. Two outcomes are not equivalent just because neither displays data after the headers.

| Status | Common meaning | Response body |
| --- | --- | --- |
| `200 OK` | Request succeeded; may return a representation or an empty response per specific contract | May or may not have one |
| `201 Created` | Resource was created | May contain a representation; often adds `Location` |
| `202 Accepted` | Accepted for processing, not necessarily finished | May contain progress info or be empty |
| `204 No Content` | Succeeded, no message content sent | **Must not contain a body** |
| `404 Not Found` | Resource not found or existence not disclosed | May have an error body, depending on design |
| `304 Not Modified` | Conditional/cache response, no representation returned | No message content; not an upload success |
| `205 Reset Content` | Succeeded and asks the user agent to reset the view | Must not generate content |
  
Per RFC 9110, **1xx, 204, and 304 responses have no message content**; `HEAD` requests also have no response content even though they may return metadata. Specifically, **204 must not contain `Content-Length`**. Do not produce JSON `{}`, `[]`, or `null` and then set status 204, because doing so sends a body in a status that forbids a body.

`200` with an empty body is occasionally valid, but if an endpoint promises to return a JSON object, it easily confuses clients. When a resource does not exist, APIs should usually return an explicit `404` instead of an empty `200`; when a delete completes without returning a resource, `204` usually expresses intent better.

## 3. `@ResponseStatus` Sets a Static Status for a Handler

The annotation `org.springframework.web.bind.annotation.ResponseStatus` can be placed on a handler method or an exception class. On a handler method, it declares the typical status for all successful outcomes taking that method path.

~~~java
@PostMapping("/orders")
@ResponseStatus(HttpStatus.CREATED)
public OrderView create(@RequestBody CreateOrderRequest request) {
    return new OrderView(42L, request.product());
}
~~~

This is an **illustrative snippet inside a controller**, not a standalone runnable program. If the handler succeeds, the response typically has **201 Created** and the `OrderView` JSON. `@ResponseStatus(HttpStatus.CREATED)` is equivalent to `@ResponseStatus(code = HttpStatus.CREATED)`; the `value` attribute is an alias for `code`.

Declaring a status for an endpoint that does not return a resource or representation:

~~~java
@DeleteMapping("/orders/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
public void delete(@PathVariable long id) {
    // Service deletes (or ensures the resource no longer exists).
}
~~~

**Reasonable result:** 204 with an empty body, if deletion succeeds. `void` is only the Java return type; **204 is specified by `@ResponseStatus`**.

Another example:

~~~java
@PostMapping("/jobs")
@ResponseStatus(HttpStatus.ACCEPTED)
public void submitJob(@RequestBody JobRequest job) {
    // Accept and enqueue the job for later processing.
}
~~~

Status `202 Accepted` should only be used when the system **actually** has an asynchronous work-acceptance mechanism; this status does not guarantee processing has finished. This is also an illustrative snippet requiring appropriate DTOs, queueing, and error handling.

### Key Characteristics

- `@ResponseStatus` declares a **static** status. If the same endpoint sometimes returns 200 and other times returns 404 or 201, use `ResponseEntity`, `ResponseStatusException`, or an appropriate exception handler.
- The annotation can be placed at the controller class level, applying to eligible handlers in the class. However, doing so easily assigns inappropriate statuses to multiple endpoints; placing it directly on individual methods is usually preferred.
- If a handler throws an exception, the success status annotation on the method does not mean the exception still returns that status. Spring handles exceptions via exception resolvers.
- Do not use `@ResponseStatus` as a substitute for authorization checks, validation, or transactions; it is primarily response metadata.

### Avoid `reason` for JSON REST Endpoints

The following example is **only for recognizing risk and should not be applied to JSON-returning REST endpoints**:

~~~java
@ResponseStatus(
        code = HttpStatus.BAD_REQUEST,
        reason = "Invalid request")
~~~

When `reason` is non-empty, Spring MVC calls `HttpServletResponse.sendError(...)`. This can trigger the Servlet container or Spring Boot error page mechanism and prevents the handler from writing the response body normally; the final body may be HTML, error JSON, or another structure depending on error handling. **Never promise a fixed JSON body** from `reason`.

For APIs needing a clearly structured error body, use `ResponseEntity`, `ProblemDetail`, and/or `@RestControllerAdvice`. This also helps clients handle `status`, `type`, and `detail` according to an agreed contract.

### Do Not Arbitrarily Mix `@ResponseStatus` with `ResponseEntity`

`ResponseEntity` lets you actively supply status, headers, and body, whereas `@ResponseStatus` supplies a static status. In Spring Framework 6.x, the status declared on `ResponseEntity` may be applied later and take effect over the status annotation. **Do not rely on application order to build complex logic.** On methods returning `ResponseEntity`, set the status directly on that object and omit the annotation so readers understand it accurately.

## 4. `void` and Bodyless Responses

Consider three patterns:

~~~java
// Pattern A: no explicit status set.
@GetMapping("/ping")
public void ping() {
}

// Pattern B: set 204 via @ResponseStatus.
@DeleteMapping("/tasks/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
public void delete(@PathVariable long id) {
}

// Pattern C: ResponseEntity expresses status and empty body.
@GetMapping("/health-ack")
public ResponseEntity<Void> acknowledge() {
    return ResponseEntity.ok().build();
}
~~~

These are **illustrative handlers inside a `@RestController`**; imports, class declaration, and business logic are omitted. In standard Spring MVC REST:

- A: default status **200**, no body; does not automatically become 204.
- B: status **204**, no body; status 204 comes from the annotation.
- C: status **200**, no body, declared by `ResponseEntity.ok().build()`.

For a successful deletion requiring no response representation, you can choose:

~~~java
public ResponseEntity<Void> delete() {
    return ResponseEntity.noContent().build();
}
~~~

This form is useful when the same handler has different outcome branches, though the example is only an **illustrative method body**; a real controller needs mapping and deletion logic before returning. `ResponseEntity<Void>` signals that no payload is expected. If custom headers are needed despite having no body, `ResponseEntity` is convenient as well.

**Do not infer a status from the absence of a body.** The framework looks at annotations, `ResponseEntity`, exceptions, and HTTP response state. Declare statuses proactively to keep the REST contract stable.

## 5. Null Body: Four Easily Confused Cases

### 5.1. `return null` from a `@RestController` Handler

~~~java
@GetMapping("/users/{id}/naive")
public UserDto findUser(@PathVariable long id) {
    return null;
}
~~~

In standard Spring MVC with `@RestController`/`@ResponseBody`, returning `null` **does not produce the JSON text `null`**. If nothing else sets the status, the response typically remains **200 OK** with an empty body. This is a common design bug when a repository/service signals "not found" with `null` and the controller passes that result straight back to the client.

With an HTML-view `@Controller` (without `@ResponseBody`), `null`/`void` may also participate in default view name selection. Always consider the controller type and how Spring handles return values before drawing conclusions.

### 5.2. `ResponseEntity.ok().body(null)`

~~~java
@GetMapping("/users/empty")
public ResponseEntity<UserDto> emptyOk() {
    return ResponseEntity.ok().body(null);
}
~~~

This snippet also typically produces **200 OK with an absent body**, because the payload inside `ResponseEntity` is `null`. Headers may vary depending on config; the key point is that the four bytes `null` are not written out.

`ResponseEntity.ok().build()` expresses "OK with no body" more clearly, while `ResponseEntity.noContent().build()` expresses "No Content" when the contract requires 204.

**Do not return the `ResponseEntity` object itself as `null`** expecting the client to get 404. Lacking a `ResponseEntity` means you are also failing to declare status/headers explicitly.

### 5.3. JSON Literal `null`

The JSON literal `null` is a valid payload of **4 UTF-8 bytes** (`n`, `u`, `l`, `l`). That is a **non-empty body**, different from a zero-length body.

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

null
~~~

If the contract intentionally requires a JSON null literal, you can explicitly construct the `"null"` body with the JSON media type:

~~~java
@GetMapping("/literal-null")
public ResponseEntity<String> literalNull() {
    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body("null");
}
~~~

This is a simple example of payload bytes; use it in a real app **only when the API contract actually defines a JSON literal `null`**. Do not use this to hide a missing resource. For normal JSON objects, letting Jackson serialize a real DTO and testing the representation is sufficient.

### 5.4. Null Property Inside a JSON Object

~~~json
{"id":1,"name":null}
~~~

Here the response body is **not empty**: the JSON object exists, only the `name` property has a null value. For example, with Spring Boot 3.x's default Jackson settings, a DTO with `name == null` is normally written as a null JSON property. If configured with `@JsonInclude(Include.NON_NULL)` or `spring.jackson.default-property-inclusion=non_null`, that property may be omitted:

~~~json
{"id":1}
~~~

The three forms `{"name":null}`, `{}`, and **no body** are distinct contracts. Clients should inspect the status first, and only parse JSON when the response actually has a valid representation.

### Comparison Table

| Controller returns | Typical status | Body content |
| --- | --- | --- |
| `return new UserDto(...)` in `@RestController` | 200 | JSON object |
| `return null` in `@RestController` | 200 if no other status set | No body |
| `ResponseEntity.ok().body(null)` | 200 | No body |
| `ResponseEntity.ok().build()` | 200 | No body |
| `ResponseEntity.noContent().build()` | 204 | No body |
| `ResponseEntity.notFound().build()` | 404 | No body |
| `ResponseEntity.ok().contentType(APPLICATION_JSON).body("null")` | 200 | JSON literal `null` |
| DTO with null property | 200 | JSON object with `null` or property omitted depending on Jackson |

The outcomes above assume **no custom filters, advice, interceptors, or servlet response logic** alter the status/body.

## 6. When a Resource Is Not Found: Use 404, Do Not Rely on Null

For a resource-fetching API `GET /users/42`, you can obtain an `Optional<UserDto>` from the service and represent "not found" as 404:

~~~java
@GetMapping("/users/{id}")
public ResponseEntity<UserDto> find(@PathVariable long id) {
    Optional<UserDto> found = service.findById(id);
    return ResponseEntity.of(found);
}
~~~

This is illustrative code inside a controller with an injected `service` and `Optional` imported; it is not a standalone file.

`ResponseEntity.of(Optional<T>)` (in Spring Framework 6.x versions) returns 200 with the body when `Optional` contains a value, or 404 with no body when `Optional.empty()`. You can also write it explicitly:

~~~java
UserDto user = service.findByIdOrNull(id);
if (user == null) {
    return ResponseEntity.notFound().build();
}
return ResponseEntity.ok(user);
~~~

This snippet is also only illustrative, assuming a `ResponseEntity<UserDto>` return type and a `service` with an appropriate method.

If "not found" is a business exception, you can throw:

~~~java
throw new ResponseStatusException(
        HttpStatus.NOT_FOUND, "User does not exist");
~~~

Spring MVC handles this as **404** if no other handler overrides it; the error body depends on Spring Boot configuration, Problem Details, and exception handlers. Do not assume there will always be a JSON body or always no JSON body.

## 7. Runnable Spring Boot 3.x Example

Create a project with Spring Initializr: **Java 17+**, **Maven**, **Spring Boot 3.x**, dependencies `spring-boot-starter-web` and `spring-boot-starter-test`. The classes below are in package `com.example.demo`. The app illustrates fixed data so statuses can be tested deterministically; it **does not persist/delete real data** and has no Spring Security.

Structure:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/StatusController.java
src/test/java/com/example/demo/StatusControllerTest.java
~~~

### 7.1. `DemoApplication.java`

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

### 7.2. `StatusController.java`

~~~java
package com.example.demo;

import java.net.URI;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/items")
public class StatusController {

    // Mock data source: only id=1 exists.
    private Item find(long id) {
        return id == 1L ? new Item(1L, "Spring") : null;
    }

    // Intentionally poor pattern: not found -> 200 with empty body.
    @GetMapping("/{id}")
    public Item naiveFind(@PathVariable long id) {
        return find(id);
    }

    // Explicit contract: resource present -> 200; absent -> 404.
    @GetMapping("/{id}/checked")
    public ResponseEntity<Item> checkedFind(@PathVariable long id) {
        Item item = find(id);
        if (item == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(item);
    }

    // Annotation sets static status: created successfully -> 201 and body.
    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Item create(@RequestBody ItemRequest request) {
        return new Item(2L, request.name());
    }

    // Equivalent creation pattern with Location, flexible via ResponseEntity.
    @PostMapping("/with-location")
    public ResponseEntity<Item> createWithLocation(
            @RequestBody ItemRequest request) {
        Item created = new Item(2L, request.name());
        return ResponseEntity
                .created(URI.create("/api/items/2"))
                .body(created);
    }

    // Simulated successful delete -> 204, empty body.
    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable long id) {
        // Demo has no repository; production must run business logic.
    }

    // Empty body can still be 200.
    @GetMapping("/empty-ok")
    public ResponseEntity<Void> emptyOk() {
        return ResponseEntity.ok().build();
    }

    // null payload in ResponseEntity -> 200 with empty body.
    @GetMapping("/null-body")
    public ResponseEntity<Item> nullBody() {
        return ResponseEntity.ok().body(null);
    }

    // Intentionally sends JSON literal null, distinct from empty body.
    @GetMapping("/literal-null")
    public ResponseEntity<String> literalNull() {
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body("null");
    }

    // JSON object with a null property.
    @GetMapping("/null-property")
    public ItemWithNullableProperty nullProperty() {
        return new ItemWithNullableProperty(1L, null);
    }

    // A 404 branch via exception instead of ResponseEntity.
    @GetMapping("/{id}/required")
    public Item required(@PathVariable long id) {
        Item item = find(id);
        if (item == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Item does not exist");
        }
        return item;
    }

    public record Item(long id, String name) {}
    public record ItemRequest(String name) {}
    public record ItemWithNullableProperty(long id, String name) {}
}
~~~

**Points to understand:**

- `find(1)` returns a DTO; `find(99)` returns `null`. This is fake data for illustration, not a real repository.
- `GET /api/items/99` intentionally returns `null` from a `@RestController`, illustrating an **empty 200 even though the resource does not exist**. Do not use this naive pattern in a production API.
- `GET /api/items/99/checked` explicitly returns **404**. For id 1, the method returns **200 JSON** with the DTO.
- `POST /api/items` uses `@ResponseStatus(CREATED)` to set a static **201**. `POST /api/items/with-location` uses `ResponseEntity.created(...)` to set **201** and the `Location: /api/items/2` header.
- `DELETE /api/items/1` is a no-op demo: **204** response from the annotation. In a real project, only return success after the service processes properly; deleting a nonexistent ID can return 204 or 404 depending on the API contract.
- `GET /api/items/empty-ok` and `GET /api/items/null-body` both return **200, no body**. `GET /api/items/literal-null` returns **200 with the four-byte body `null`**.
- `GET /api/items/null-property` returns an object; with Boot 3.x default Jackson, the JSON has a `name` property with `null`.
- `GET /api/items/99/required` uses `ResponseStatusException` to respond with **404**; the error body depends on configuration.

**This lesson teaches response contracts.** The create/delete examples only illustrate statuses, not real database correctness, transactions, or access control.

## 8. Calling the API with curl and Reading Actual Responses

Run in the directory containing `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

On Windows use `mvnw.cmd spring-boot:run`; if you do not have the Maven Wrapper, run `mvn spring-boot:run` after installing Maven.

### 8.1. Inspecting 200 with Body and 200 Without Body

~~~bash
curl -i http://localhost:8080/api/items/1
curl -i http://localhost:8080/api/items/99
curl -i http://localhost:8080/api/items/empty-ok
curl -i http://localhost:8080/api/items/null-body
~~~

The first response is **200** with JSON:

~~~json
{"id":1,"name":"Spring"}
~~~

The next three responses are all **200** with empty bodies in the sample configuration. This is crucial proof that status 200 **does not tell you** whether the body contains JSON or not.

### 8.2. Inspecting Explicit 404 and 204

~~~bash
curl -i http://localhost:8080/api/items/99/checked
curl -i -X DELETE http://localhost:8080/api/items/1
~~~

The first line returns **404 Not Found** with an empty body due to `ResponseEntity.notFound().build()`. The second line returns **204 No Content** without sending a body. Do not try `response.json()` on a 204 fetch response because there is no JSON to parse.

### 8.3. Status 201 When Creating a Resource

~~~bash
curl -i -X POST "http://localhost:8080/api/items"   -H "Content-Type: application/json"   --data-binary '{"name":"MVC"}'
~~~

Status **201 Created**, body:

~~~json
{"id":2,"name":"MVC"}
~~~

With `/api/items/with-location`, the status is also **201**, plus header `Location: /api/items/2`. The URI in the example is a valid relative URI in the Location header; real services should point to an accessible resource rather than returning a fake link.

### 8.4. Comparing JSON `null` and an Empty Body

~~~bash
curl -i http://localhost:8080/api/items/literal-null
curl -i http://localhost:8080/api/items/null-property
~~~

The results have contents respectively:

~~~json
null
~~~

~~~json
{"id":1,"name":null}
~~~

Unlike `/api/items/null-body`, both responses above have **actual JSON payloads**. You can view them with `curl -i` or the browser's Network tab, but do not conclude anything solely from blank terminal output because newline/whitespace bytes might be present. For strict verification, test with `MockMvc` using `content().string("")` and `content().string("null")`.

The multiline commands use `\` on Linux/macOS/Git Bash. In PowerShell, use `curl.exe` and write arguments on one line or replace with PowerShell's line continuation syntax; JSON string quoting needs adjustment per shell.

## 9. MockMvc Testing: Checking Status, Body, and Location Together

Add `spring-boot-starter-test`. Create **`src/test/java/com/example/demo/StatusControllerTest.java`**:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(StatusController.class)
class StatusControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void successReturns200WithJson() throws Exception {
        mockMvc.perform(get("/api/items/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(1))
                .andExpect(jsonPath("$.name").value("Spring"));
    }

    @Test
    void naiveMissingResourceIs200WithEmptyBody() throws Exception {
        mockMvc.perform(get("/api/items/99"))
                .andExpect(status().isOk())
                .andExpect(content().string(""));
    }

    @Test
    void missingResourceHandledExplicitlyIs404() throws Exception {
        mockMvc.perform(get("/api/items/99/checked"))
                .andExpect(status().isNotFound())
                .andExpect(content().string(""));
    }

    @Test
    void deleteReturns204WithoutBody() throws Exception {
        mockMvc.perform(delete("/api/items/1"))
                .andExpect(status().isNoContent())
                .andExpect(content().string(""));
    }

    @Test
    void createReturns201AndJson() throws Exception {
        mockMvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"MVC\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(2))
                .andExpect(jsonPath("$.name").value("MVC"));
    }

    @Test
    void createWithLocationReturns201AndLocation() throws Exception {
        mockMvc.perform(post("/api/items/with-location")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"MVC\"}"))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        HttpHeaders.LOCATION, "/api/items/2"))
                .andExpect(jsonPath("$.name").value("MVC"));
    }

    @Test
    void emptyOkAndNullBodyRemain200WithNoBody() throws Exception {
        mockMvc.perform(get("/api/items/empty-ok"))
                .andExpect(status().isOk())
                .andExpect(content().string(""));

        mockMvc.perform(get("/api/items/null-body"))
                .andExpect(status().isOk())
                .andExpect(content().string(""));
    }

    @Test
    void literalNullIsFourCharactersNotEmptyBody() throws Exception {
        mockMvc.perform(get("/api/items/literal-null"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(content().string("null"));
    }

    @Test
    void nullPropertyIsStillAJsonObject() throws Exception {
        mockMvc.perform(get("/api/items/null-property"))
                .andExpect(status().isOk())
                .andExpect(content().json(
                        "{\"id\":1,\"name\":null}"));
    }

    @Test
    void responseStatusExceptionMapsTo404() throws Exception {
        mockMvc.perform(get("/api/items/99/required"))
                .andExpect(status().isNotFound());
    }
}
~~~

Run:

~~~bash
./mvnw test
~~~

The tests verify both **status** and **body**; if you only assert status 200, it is easy to miss an endpoint that should return JSON but returns empty instead. The test `literalNullIsFourCharactersNotEmptyBody` directly distinguishes the `null` payload (4 ASCII characters) from an empty string. Tests with `@WebMvcTest` only stand up an MVC test slice with this controller without opening a real server.

`responseStatusExceptionMapsTo404` only checks the 404 code because Spring Boot's error body depends on auto-configuration and Problem Details features; the test does not assume the error message will appear in a specific JSON shape.

## 10. `@ResponseStatus` on Exception Classes and REST Error Handling

You can define an exception carrying a fixed status:

~~~java
@ResponseStatus(HttpStatus.NOT_FOUND)
public class ResourceNotFoundException extends RuntimeException {
    public ResourceNotFoundException(String message) {
        super(message);
    }
}
~~~

This snippet is an **illustrative Java class**, requiring imports for `ResponseStatus` and `HttpStatus`, and a separate `ResourceNotFoundException.java` file. When a handler throws the exception, `ResponseStatusExceptionResolver` can resolve it to 404. However, `@ResponseStatus` **on an exception class** uses the `sendError` mechanism; the server or error controller may generate an error body. Therefore, do not assume "404 is always empty" or "404 always has the same JSON".

If you want consistent structured JSON, choose explicit handling:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ResourceNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleNotFound(
            ResourceNotFoundException ex) {

        ProblemDetail problem =
                ProblemDetail.forStatusAndDetail(
                        HttpStatus.NOT_FOUND, "Resource not found");
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }
}
~~~

This is a **separate illustrative class**, requiring imports for `RestControllerAdvice`, `ExceptionHandler`, `ResponseEntity`, `ProblemDetail`, `HttpStatus`, and the exception. Spring Framework 6.x supports `ProblemDetail` for representing error details per RFC 9457. Do not send stack traces, internal data, or sensitive messages in responses just because the exception contains them.

When handling dynamic statuses, choosing among `ResponseEntity`, `ResponseStatusException`, and `@ExceptionHandler` depends on API design:
- If you want an explicit local branch right inside the handler, `ResponseEntity` is usually simple.
- If a missing resource is an application exception, you can throw it and handle it centrally.
- If you only need a static status for a successful action, `@ResponseStatus` on the method is concise.

## 11. 204 Responses in HTTP Clients and Frontends

Example of a frontend calling DELETE:

~~~javascript
async function deleteItem(id) {
  const response = await fetch("/api/items/" + id, {
    method: "DELETE"
  });

  if (response.status === 204) {
    return; // Do not call response.json(): there is no body.
  }
  if (response.status === 404) {
    throw new Error("Item does not exist");
  }
  if (!response.ok) {
    throw new Error("Delete failed: " + response.status);
  }
}
~~~

Not every 2xx response contains JSON; `response.ok` in Fetch only checks the 200–299 status range. Calling `response.json()` on an empty body can throw a `SyntaxError`, even when the request succeeded. Clients can design logic around the API contract: for 204 do not parse; for 200 with a JSON body parse it; for 404 handle missing resource.

If the API contract permits `200` with an empty body, the frontend must inspect content before parsing (or better yet, standardize the contract to eliminate ambiguity). Do not rely solely on the `Content-Length` header, because HTTP has multiple ways of framing responses and that header may be absent even when a body exists.

Some client APIs use types like `Optional<T>` or `T | null` to represent "does not exist" at the application layer. **Do not automatically** map those types to an empty 200 response; at the HTTP layer, decide explicit 404/204/200 semantics.

## 12. Choosing Statuses for Update, Delete, and Create

| REST scenario | Commonly used status | Spring MVC approach |
| --- | --- | --- |
| GET finds resource | 200 with JSON | Return DTO or `ResponseEntity.ok(dto)` |
| GET not found | 404 | `ResponseEntity.notFound().build()` |
| POST creates resource immediately | 201 | `@ResponseStatus(CREATED)` or `ResponseEntity.created(uri).body(dto)` |
| POST accepts queued job | 202 | `ResponseEntity.accepted().build()` or return job info |
| PUT/PATCH updates and returns object | 200 with JSON | `ResponseEntity.ok(dto)` |
| PUT/PATCH updates, does not return object | 204 | `ResponseEntity.noContent().build()` |
| DELETE succeeds, does not return object | 204 | `@ResponseStatus(NO_CONTENT) void` or `noContent().build()` |
| DELETE absent resource | Per contract: 404 or idempotent 204 | Write intentional branch, test it |

**Idempotency** of DELETE means repeating the same operation produces the desired state effect as the first call; it does **not** require every call to return the same status. An API can return 204 on the first delete and 404 on a repeat delete, as long as the contract states this clearly and consistently. HTTP 204 may carry valid metadata like ETag in some contexts, but must never carry a body.

201 should usually include `Location` pointing to the new resource, especially when the server assigns the ID. In the demo example, data is not actually persisted; real projects must create the resource and provide a working URI.

## 13. Common Mistakes

### Mistake A: Returning `null` and Expecting Spring to Pick 404

~~~java
@GetMapping("/{id}")
public UserDto get(@PathVariable long id) {
    return service.findByIdOrNull(id);
}
~~~

If the service returns `null`, `@RestController` can produce an **empty 200**. **Fix:** switch to `ResponseEntity.notFound().build()` or an explicit 404 exception.

### Mistake B: Adding `@ResponseStatus(NO_CONTENT)` While Still Returning Data

~~~java
@ResponseStatus(HttpStatus.NO_CONTENT)
@GetMapping("/value")
public UserDto value() {
    return new UserDto(1L, "Lan");
}
~~~

This is an error-illustration snippet, not code to run: HTTP 204 **must not contain message content**. How the server layer tries to write or drop the body varies, but this design violates the contract. **Fix:** return `void`/no body for 204, or use 200 with real data.

### Mistake C: Using `@ResponseStatus(reason="...")` for JSON Errors

`reason` goes through `sendError`, which may result in an error page or an unexpected response. **Fix:** use `ResponseEntity<ProblemDetail>`, `@RestControllerAdvice`, and test the JSON error response.

### Mistake D: Confusing `200 + Empty Body` with JSON `null`

HTTP 200 with an empty body has **0 bytes**. JSON literal `null` has **4 bytes**; a body like `{"data":null}` is even longer. **Fix:** test `content().string("")` or `content().string("null")`, rather than only checking status.

### Mistake E: Calling `response.json()` After a 204 DELETE

The frontend throws a JSON parse error even though the HTTP request succeeded. **Fix:** check for status 204 and avoid parsing a payload.

### Mistake F: Returning `ResponseEntity.ok().body(null)` When Not Found

The API reports 200 success, preventing the client from distinguishing a missing resource. **Fix:** return 404 if the API defines GET for a nonexistent resource as missing.

### Mistake G: Mixing Static and Dynamic Statuses

A method having both `@ResponseStatus` and returning a `ResponseEntity` with a different status makes code confusing and dependent on return-value processing details. **Fix:** use one mechanism as the single source of truth for the endpoint's status.

### Mistake H: Tests Only Checking Status

A test that only checks `isOk()` still PASSES even if the JSON body is missing. **Fix:** check JSON schema, key properties, `Content-Type`, empty body, or `Location` accordingly.

## 14. Knowledge Self-Check

**Question 1.** A controller returns `null` for a `@GetMapping` in a `@RestController`; does the API automatically return 204?

**Answer:** No. In standard MVC configuration, if no other status is set, the response is usually **200 with an empty body**.

**Question 2.** Can `@ResponseStatus(HttpStatus.NO_CONTENT)` be used on a method returning a JSON object?

**Answer:** It should not be: 204 forbids message content. To return a JSON object, use 200 or 201 as appropriate. For 204, omit the body.

**Question 3.** How does `ResponseEntity.ok().body(null)` differ from `ResponseEntity.ok().contentType(APPLICATION_JSON).body("null")`?

**Answer:** The first gives 200 with an absent body. The second gives 200 with a four-byte JSON literal `null` payload, when using the standard String converter.

**Question 4.** What is the difference between `@ResponseStatus(CREATED)` and `ResponseEntity.created(location)`?

**Answer:** The annotation sets a static 201 status on the handler; `ResponseEntity.created(...)` expresses both status 201 and the `Location` header, optionally with a body.

**Question 5.** Why should 204 tests also inspect the body?

**Answer:** Because status and payload are separate concerns; you must confirm the API does not try to send data in a status that forbids a body and that the client does not parse JSON after 204.

## 15. Implementation Checklist

1. Define each endpoint's contract upfront: success status, not-found status, whether a body exists, and JSON shape if applicable.
2. Use `@ResponseStatus` on a handler when the success status is static; use `ResponseEntity` when status/headers/body depend on the outcome.
3. For no content: explicitly set `204` and produce no payload. For empty `200`: only use it if the contract genuinely requires it.
4. For missing data: never let `null` leak out of a `@RestController` and turn into an ambiguous 200.
5. Distinguish absent body, JSON literal `null`, and null properties in JSON; verify against Jackson configuration.
6. Use `@RestControllerAdvice`/`ProblemDetail` when standardizing errors; avoid `@ResponseStatus` `reason` for REST JSON.
7. Test **status + body + headers** plus edge cases (404, 204, empty-JSON parsing on the frontend).

## Official References

- [Spring Framework 6.2 — Controller Return Values](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/return-types.html)
- [Spring Framework 6.2 — ResponseEntity](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/responseentity.html)
- [Spring Framework — @ResponseBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/responsebody.html)
- [Spring Framework 6.2 — @ResponseStatus Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/annotation/ResponseStatus.html)
- [Spring Framework — REST Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
