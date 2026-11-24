# ResponseEntity, Status Codes, Headers, and Empty Responses in Spring Boot

## Learning Objectives

When an HTTP endpoint is called, the returned result is not just JSON data. An **HTTP response** consists of a **status code**, **response headers**, and, when the protocol permits, a **response body**. In Spring MVC and Spring WebFlux, **ResponseEntity<T>** is the explicit way to express all three parts from a controller.

After this lesson, you will be able to:

- Distinguish status, headers, and body components and how they are constructed via ResponseEntity.
- Choose accurate status codes for GET, POST, PUT/PATCH, DELETE, and common errors.
- Use the builders ok(), created(), accepted(), noContent(), notFound(), badRequest(), status(), header(), location(), and build()/body().
- Understand the differences among **204 No Content**, **200 OK with an empty body**, **202 Accepted**, **HEAD**, and **304 Not Modified**.
- Set Location, Content-Type, Cache-Control, ETag, Retry-After, or application headers intentionally.
- Return ResponseEntity<Void> for cases needing only status/headers.
- Handle data-dependent status codes in WebFlux with Mono<ResponseEntity<T>>.
- Write and test Java 17+ controllers using MockMvc or WebTestClient; recognize content negotiation errors, committed responses, and invalid response bodies.

## 1. An HTTP response is a contract between server and client

An illustrative HTTP response:

~~~http
HTTP/1.1 201 Created
Location: /api/items/7
Content-Type: application/json
Cache-Control: no-store

{"id":7,"name":"Notebook"}
~~~

Key parts:

| Part | Example | Meaning |
|---|---|---|
| Status code | 201 Created | Outcome of the request per HTTP semantics. |
| Header | Location: /api/items/7 | Metadata/control related to the response or resource. |
| Header | Content-Type: application/json | Media type of the body if the response has a JSON representation. |
| Header | Cache-Control: no-store | Directive governing caching of the response. |
| Body | JSON of the new item | Data/representation received by the client when status and method permit. |

A response can still be valid with no body. Conversely, a JSON body saying "error" paired with status 200 can cause clients, gateways, and monitoring systems to record the request as successful. **Do not use the body as a substitute for the status code**.

Error example:

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{"type":"about:blank","title":"Not Found","status":404}
~~~

The error body here is only an example of a structured representation; an application is not forced to return this exact format on every 404. What matters is that status 404 reflects that the resource was not found.

## 2. What is ResponseEntity<T>?

**org.springframework.http.ResponseEntity<T>** is a Spring Framework type representing an HTTP status, headers, and a body of type T. It extends **HttpEntity<T>**, adding response status information.

Comparison:

| Controller return type | Status | Headers | Body |
|---|---|---|---|
| An object/record with @RestController | Chosen by framework by default, usually 200 on success | Set by framework per content negotiation/codec | Object serialized if suitable |
| String with @RestController | Usually 200 | Content-Type per converter config | String, not a view name |
| @ResponseStatus on handler | Status specified by annotation | Can still be added by framework/handler | Depends on return type |
| HttpEntity<T> | Usually default or controlled elsewhere | Yes | Yes |
| ResponseEntity<T> | Decided directly by the controller | Added or modified by the controller | Optional |
| ResponseEntity<Void> | Decided by the controller | Optional | Contains no body object |

In a `@Controller` without `@ResponseBody`, returning a String can indicate a **view name**; `ResponseEntity` is recognized as a distinct return value type. With `@RestController`, Spring applies `@ResponseBody` semantics to methods, yet `ResponseEntity` remains useful because it can specify status and headers explicitly.

`ResponseEntity` also **does not serialize JSON on its own**. Spring MVC uses `HttpMessageConverter`; WebFlux uses `HttpMessageWriter`/codecs based on the classpath, Content-Type, Accept, and Java type.

### Basic syntax

~~~java
ResponseEntity<String> ok =
    ResponseEntity.ok("ready");

ResponseEntity<String> accepted =
    ResponseEntity.status(HttpStatus.ACCEPTED)
        .body("job queued");

ResponseEntity<Void> noContent =
    ResponseEntity.noContent().build();

ResponseEntity<Void> notFound =
    ResponseEntity.notFound().build();
~~~

These snippets illustrate creating response objects, not standalone controller methods; imports for `ResponseEntity` and `HttpStatus` are required.

- **body(value)**: creates a `ResponseEntity` with a body.
- **build()**: creates a `ResponseEntity` with no body object; use for statuses needing only metadata.
- **ResponseEntity.ok(body)**: shorthand for 200 and a body.
- **ResponseEntity.status(...).body(...)**: when the status lacks a convenience builder or multiple customizations are combined.

## 3. Common status codes in REST APIs

### 2xx group: successful requests

| Status | Meaning | Common scenarios |
|---|---|---|
| 200 OK | Request succeeded; response may contain a resource representation or result | GET retrieving an object, POST processing and returning a result, PUT returning updated object |
| 201 Created | Request created one or more new resources | POST creating an item; should provide Location when the resource URI is known |
| 202 Accepted | Request accepted for processing, though processing is not yet complete | Enqueueing a task, returning job id/status endpoint |
| 204 No Content | Request completed successfully and has no response content | Successful DELETE, successful PUT/PATCH needing no returned object |
| 205 Reset Content | Server asks the client to reset an input view; no response content | Special UI cases, rarely used in standard REST |
| 206 Partial Content | Server returns a partial representation for a valid range request | Downloading resources by byte range |

**200 is not the universal default for every successful operation.** A resource-creation endpoint should consider 201; an incomplete asynchronous operation may use 202; updates/deletes returning no body typically pick 204.

### 3xx group: redirects or conditional caching

| Status | Meaning |
|---|---|
| 301 Moved Permanently | Resource has moved to a new URI permanently per HTTP semantics. |
| 302 Found | Temporary redirect with historical compatibility rules for methods. |
| 303 See Other | Directs the client to fetch another resource with GET, often useful after POST. |
| 304 Not Modified | Conditional GET/HEAD evaluation shows the cached representation can be reused, so no body is sent. |
| 307 Temporary Redirect | Temporary redirect, preserving the request method. |
| 308 Permanent Redirect | Permanent redirect, preserving the request method. |

**201 Created with Location** is not a 3xx redirect. Clients can use Location to know the new resource's URI; the server is not instructing an automatic redirect follow.

### 4xx group: request cannot be fulfilled per client contract

| Status | Common meaning |
|---|---|
| 400 Bad Request | Request is malformed, or parameters/data are invalid in a way the server considers a client error. |
| 401 Unauthorized | Valid authentication is required; HTTP authentication typically pairs with an appropriate WWW-Authenticate header. |
| 403 Forbidden | Server understands the request yet refuses to authorize the operation. |
| 404 Not Found | Resource not found or server chooses not to disclose its existence, depending on context. |
| 405 Method Not Allowed | Path has a handler but the method is unsupported; response should include Allow per HTTP semantics. |
| 409 Conflict | Current resource state conflicts with the update/create request. |
| 412 Precondition Failed | If-Match/If-Unmodified-Since condition was not met. |
| 415 Unsupported Media Type | Request media type is incompatible with the endpoint/reader. |
| 422 Unprocessable Content | Content is syntactically valid yet semantically unprocessable, when the contract chooses this status. |
| 429 Too Many Requests | Rate limit exceeded; may include Retry-After. |

Do not choose statuses solely by Java exception class. Consult the **API contract** and business cause. For instance, a missing item is 404, whereas an item that exists yet was modified by another version can be 409 or 412, depending on optimistic locking/conditional requests.

### 5xx group: server or downstream errors

500 Internal Server Error is for unexpected server failures; 502 Bad Gateway, 503 Service Unavailable, and 504 Gateway Timeout typically originate at proxies/gateways or intermediaries. Do not turn every downstream error into 400 just to "return a client error"; preserve accurate meaning and avoid leaking sensitive information.

## 4. ResponseEntity factories/builders to know

| API | Result | Notes |
|---|---|---|
| ResponseEntity.ok(body) | 200 and body | Quick for successful GETs. |
| ResponseEntity.ok().body(body) | 200 and body | Allows adding headers before body(). |
| ResponseEntity.created(uri).body(body) | 201, Location, and body | Matches resource-creation semantics. |
| ResponseEntity.created(uri).build() | 201, Location, no body | Valid when created and no representation needs returning. |
| ResponseEntity.accepted().build() | 202, no body | Job accepted for processing; consider tracking details if needed. |
| ResponseEntity.noContent().build() | 204, no body | Success case returning no content. |
| ResponseEntity.notFound().build() | 404, no body | Missing resource and API needs no error body. |
| ResponseEntity.badRequest().build() | 400, no body | Invalid request without details. |
| ResponseEntity.status(HttpStatus.CONFLICT).body(error) | 409 and body | Business conflict needing a structured representation. |
| ResponseEntity.ok().header("X-Trace-Id", id).body(body) | 200, custom header, body | Adds metadata in response headers. |
| ResponseEntity.status(code).build() | Custom status, no body | Requires understanding the code's HTTP semantics. |

Builders can be chained:

~~~java
ResponseEntity<String> response = ResponseEntity
    .ok()
    .header("X-Source", "catalog")
    .cacheControl(CacheControl.noStore())
    .body("ok");
~~~

Import **org.springframework.http.CacheControl** and **org.springframework.http.ResponseEntity** for this example.

### Do not confuse body() and build()

~~~java
ResponseEntity<String> a = ResponseEntity.ok("hello");
// Status 200, body "hello"

ResponseEntity<Void> b = ResponseEntity.ok().build();
// Status 200, no body object

ResponseEntity<Void> c = ResponseEntity.noContent().build();
// Status 204, no response content
~~~

The last two cases **are not synonymous**: 200 describes success where content may be zero-length, whereas 204 confirms no additional content is to be sent and carries distinct HTTP framing rules.

## 5. 204 No Content: successful response containing no body

Per RFC 9110, **204 No Content** means the server fulfilled the request and **there is no response content**. The response ends after the headers; it must not carry a body or trailers. Therefore:

~~~http
HTTP/1.1 204 No Content
ETag: "item-v2"

~~~

The example illustrates headers only; headers like Date may be added automatically by the server. Never attach a JSON line, a serialized empty String, or a byte payload under status 204.

How to return 204 in Spring Boot:

~~~java
@DeleteMapping("/api/items/{id}")
public ResponseEntity<Void> delete(@PathVariable long id) {
    service.delete(id);
    return ResponseEntity.noContent().build();
}
~~~

This is an illustrative method meant for a `@RestController` backed by a real service. **Only return 204 when the operation succeeded as contracted**; if the service reports not found or unauthorized, pick the matching status.

### How does 204 differ from an empty response body?

| Case | Can it have response content? | Meaning |
|---|---|---|
| 200 OK with empty body | Can be zero-length content | Request succeeded in the 200 sense. |
| 204 No Content | No | Request succeeded and server sends no content. |
| 205 Reset Content | No | Client should reset a document/input view. |
| 304 Not Modified | No | Client can reuse cached representation after conditional request. |
| HEAD response | No | Headers matching the corresponding GET only, no content. |

Do not return 204 for "still processing, nothing ready yet"; 202 Accepted likely fits better there.

Do not set **Content-Length: 0** manually on 204. RFC 9110 imposes specific restrictions on this header in 204 responses; let the HTTP server/framework handle framing. When using `ResponseEntity.noContent().build()`, avoid interfering directly with raw bytes or HTTP framing.

### 204 in Spring WebFlux

With `Mono<Void>` in a reactive controller, the pipeline can complete without emitting a value. That **is not an automatic rule turning the status into 204**. Pick the status explicitly:

~~~java
@DeleteMapping("/api/items/{id}")
public Mono<ResponseEntity<Void>> delete(@PathVariable long id) {
    return service.deleteById(id)
        .thenReturn(ResponseEntity.noContent().build());
}
~~~

This illustrates `service.deleteById(id)` returning a Publisher representing deletion; if 404 is needed for missing IDs, the service must signal the outcome (e.g., boolean or an error mapped appropriately). Do not assume `Mono.empty()` automatically means "not found".

## 6. 201 Created and the Location header

When a POST creates a new resource, return **201 Created** and, if a URI can be determined, provide **Location**.

Example:

~~~java
@PostMapping("/api/items")
public ResponseEntity<Item> create(@RequestBody CreateItemRequest request) {
    Item created = service.create(request);

    URI location = URI.create("/api/items/" + created.id());

    return ResponseEntity.created(location).body(created);
}
~~~

The URI in the example is a **relative URI reference**. HTTP Location permits relative URI references under RFC 9110; if the API contract requires an absolute URL, construct it from trusted request/gateway configuration, especially when running behind a reverse proxy.

Do not build a public host by hardcoding `server.port` or taking an unverified `Host` header directly. Systems behind ingress can have completely different public schemes, hosts, and ports than the backend.

Use `created(location).build()` if the server wants to send 201 and Location without a body. Use `created(location).body(created)` to include the latest representation of the item.

### 201 and 202 are not the same

- **201 Created**: resource creation has completed per contract.
- **202 Accepted**: request has been accepted yet processing has not finished; the response should provide tracking info if needed.

Example submitting an async job:

~~~java
@PostMapping("/api/reports")
public ResponseEntity<JobReceipt> submit(@RequestBody ReportRequest request) {
    JobReceipt receipt = queue.submit(request);
    return ResponseEntity.accepted()
        .header("Location", "/api/jobs/" + receipt.id())
        .body(receipt);
}
~~~

This illustrates using a queue service and DTO defined in a real application. When using 202, do not claim the report has finished when it was only enqueued.

## 7. 404 Not Found and Optional: choosing status by data

A matching route does not guarantee the underlying data exists. When looking up an item by ID:

~~~java
@GetMapping("/api/items/{id}")
public ResponseEntity<Item> findOne(@PathVariable long id) {
    return repository.findById(id)
        .map(ResponseEntity::ok)
        .orElseGet(() -> ResponseEntity.notFound().build());
}
~~~

The example assumes `repository.findById(id)` returns **Optional<Item>**. If found, 200 + JSON body. If absent, 404 + no body.

Spring Framework also supports creating ResponseEntity from Optional in versions with matching factories, yet the `map`/`orElseGet` style above makes both branches clear and lets you customize error headers/bodies.

Do not assume:

- `Optional.empty()` becomes HTTP 404 unless the controller converts it to the proper status.
- Returning `null` from a controller becomes HTTP 204.
- HTTP 404 must always have a JSON body or never have a body.

Both 404 with a structured error body and 404 without a body can be valid; what matters is consistency with the API contract.

## 8. ResponseEntity<Void>, Void, void, and empty return types

### ResponseEntity<Void>

Use when you only need status and headers:

~~~java
@PutMapping("/api/items/{id}")
public ResponseEntity<Void> update(
        @PathVariable long id,
        @RequestBody UpdateItemRequest request) {

    service.update(id, request);

    return ResponseEntity.noContent().build();
}
~~~

**Void** is the generic type expressing "no body object", making the contract clear to readers and the compiler.

### A void method with @ResponseStatus

You can return 204 with:

~~~java
@DeleteMapping("/api/items/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
public void delete(@PathVariable long id) {
    service.delete(id);
}
~~~

This fits when the status is always fixed and errors are handled via exception handlers. When status, headers, or body vary by outcome, `ResponseEntity` is usually clearer.

### Returning null is not a design solution

Returning `null` in a controller does not express HTTP semantics clearly and can depend on return-value handlers/framework behavior. When an endpoint has no body, return `ResponseEntity.noContent().build()` or intentionally use `@ResponseStatus(HttpStatus.NO_CONTENT)`.

### Error status codes without a body

You can also return:

~~~java
return ResponseEntity.badRequest().build();
~~~

This differs from 204: it is status **400**, not a successful execution. Never use an "empty body" to distinguish success from failure.

## 9. Setting response headers properly

ResponseEntity lets you add headers using its builder:

~~~java
ResponseEntity<String> response = ResponseEntity
    .ok()
    .header("X-Trace-Id", "req-123")
    .header("X-Source", "web-runtime")
    .body("done");
~~~

Or build `HttpHeaders` and pass `headers(...)`:

~~~java
HttpHeaders headers = new HttpHeaders();
headers.set("X-Trace-Id", "req-123");

ResponseEntity<String> response =
    ResponseEntity.ok().headers(headers).body("done");
~~~

Imports for `HttpHeaders` and `ResponseEntity` are required.

### Common headers

| Header | Purpose | Notes |
|---|---|---|
| Content-Type | Media type of the body | Usually best left to HTTP message converters/codecs when possible. |
| Location | URI pointing to new resource or redirect target | Match 201/3xx semantics; may be a relative reference. |
| Cache-Control | Caching policy | `no-store` is typically appropriate for data that must not be stored. |
| ETag | Representation validator | Works with conditional requests to avoid re-fetching or prevent lost updates. |
| Last-Modified | Last modification timestamp of the resource | Use when a reliable timestamp source exists. |
| Vary | Tells caches which request headers alter the representation | E.g., `Vary: Accept-Language` when responses differ by language. |
| Retry-After | Suggests retry time/delay | Can pair with 429/503; does not replace rate-limiting policy. |
| WWW-Authenticate | HTTP authentication challenge info | Important for certain 401 responses. |
| Content-Disposition | Suggests download behavior/filename | Sanitize any filenames derived from input safely. |
| Allow | List of supported methods when returning 405 | Typically managed by the framework per route. |

**Do not set Content-Length manually** when using JSON serialization, compression, transfer encoding, or streaming; actual size may only be known at write time. Let the framework/server control framing.

### Special headers and safety

- Do not reflect client-supplied headers into Location/Content-Disposition without validation.
- Do not put access tokens, session cookies, or personal data into trace headers or logs.
- Do not assemble a CORS policy from ad-hoc response headers if the application already uses Spring Security/CORS config; preflight requests have dedicated handling.
- Do not return status 200 with an error header expecting HTTP clients to treat it as an error.

## 10. Cache-Control, ETag, and 304 Not Modified

Caching can reduce bandwidth and latency when a client already holds a valid representation. Two key concepts:

- **Cache-Control** directs caching policy.
- **ETag** is a validator for a representation; clients can send **If-None-Match** to check whether the resource has changed.

A GET response with ETag:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "item-7-v3"
Cache-Control: private, max-age=60

{"id":7,"name":"Notebook"}
~~~

Next time, the client can send:

~~~http
GET /api/items/7 HTTP/1.1
If-None-Match: "item-7-v3"
~~~

When HTTP cache validation conditions are met, the server can respond **304 Not Modified** with appropriate headers and **no body**. The client reuses its cached representation.

**304 does not mean the resource was updated successfully.** It belongs to conditional requests, primarily GET/HEAD. Never return 304 in place of 204 for a successful DELETE/PUT.

Example 200 ResponseEntity with ETag:

~~~java
ResponseEntity<Item> response = ResponseEntity
    .ok()
    .eTag("\"item-7-v3\"")
    .cacheControl(CacheControl.maxAge(Duration.ofSeconds(60)))
    .body(item);
~~~

In Java, imports for **java.time.Duration** and **org.springframework.http.CacheControl** are required. Spring MVC and WebFlux support HTTP conditional requests at appropriate points; to emit 304 properly, verify the conditions and lifecycle of your framework rather than returning 304 solely because an ETag exists.

### If-Match and 412 Precondition Failed

For updates with optimistic concurrency, clients can send `If-Match` to allow writes only if the current ETag matches. When the condition fails, **412 Precondition Failed** is usually the right status. That serves a different purpose from `If-None-Match` used to save GET bandwidth.

Do not fake an ETag as a static ID that never changes across edits if your goal is representation version checking. An ETag must reflect the data or representation version according to your API strategy.

## 11. Complete Spring Boot MVC example, Java 17+

Runnable example with **Spring Boot 3.x, Java 17+**, the **spring-boot-starter-web** dependency, and starter-provided JSON support. For Spring Boot 4.x, the corresponding MVC starter may be named **spring-boot-starter-webmvc**; pick according to your actual major version.

To keep focus on ResponseEntity, data is stored in an in-memory `ConcurrentHashMap`. This is not a production persistence layer.

### 11.1. Application class

File: src/main/java/com/example/responses/ResponseApplication.java

~~~java
package com.example.responses;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResponseApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResponseApplication.class, args);
    }
}
~~~

### 11.2. Models

File: src/main/java/com/example/responses/Item.java

~~~java
package com.example.responses;

public record Item(long id, String name) {
}
~~~

File: src/main/java/com/example/responses/CreateItemRequest.java

~~~java
package com.example.responses;

public record CreateItemRequest(String name) {
}
~~~

### 11.3. Controller returning multiple statuses

File: src/main/java/com/example/responses/ItemController.java

~~~java
package com.example.responses;

import java.net.URI;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    private final Map<Long, Item> items = new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong();

    @PostMapping
    public ResponseEntity<Item> create(
            @RequestBody CreateItemRequest request) {

        if (request.name() == null || request.name().isBlank()) {
            return ResponseEntity.badRequest().build();
        }

        long id = sequence.incrementAndGet();
        Item created = new Item(id, request.name().trim());
        items.put(id, created);

        URI location = URI.create("/api/items/" + id);

        return ResponseEntity
            .created(location)
            .body(created);
    }

    @GetMapping("/{id}")
    public ResponseEntity<Item> get(@PathVariable long id) {
        Item found = items.get(id);

        if (found == null) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity
            .ok()
            .header("X-Source", "in-memory-demo")
            .body(found);
    }

    @PutMapping("/{id}")
    public ResponseEntity<Void> update(
            @PathVariable long id,
            @RequestBody CreateItemRequest request) {

        if (!items.containsKey(id)) {
            return ResponseEntity.notFound().build();
        }
        if (request.name() == null || request.name().isBlank()) {
            return ResponseEntity.badRequest().build();
        }

        items.put(id, new Item(id, request.name().trim()));

        return ResponseEntity.noContent().build();
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable long id) {
        Item removed = items.remove(id);

        if (removed == null) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.noContent().build();
    }

    @GetMapping("/ping")
    public ResponseEntity<Void> ping() {
        return ResponseEntity
            .status(HttpStatus.OK)
            .header("X-Health", "ready")
            .build();
    }
}
~~~

The controller demonstrates these cases:

- POST with valid body: **201 Created**, **Location: /api/items/{id}**, JSON body of the new item.
- POST with blank/null name: **400 Bad Request**, no body in this example.
- GET existing item: **200 OK**, X-Source header, JSON body.
- GET non-existent item: **404 Not Found**, no body.
- PUT existing item: **204 No Content**, no body.
- PUT non-existent item: **404 Not Found**.
- DELETE existing item: **204 No Content**.
- DELETE non-existent item: **404 Not Found**.
- GET /api/items/ping: **200 OK**, X-Health header, no body — to contrast with 204.

This application has a non-atomic update check between `containsKey` and `put`, suitable only for demonstration. In real projects, use transactions and optimistic locking when concurrency can cause conflicts.

### 11.4. Calling the API and inspecting responses

Run Maven Wrapper from the project root:

~~~bash
./mvnw spring-boot:run
~~~

On Windows with Maven Wrapper:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Create a resource:

~~~bash
curl -i -X POST http://localhost:8080/api/items -H "Content-Type: application/json" -d '{"name":"Notebook"}'
~~~

With a freshly started app, the first item has id 1. Expected response has status 201, header **Location: /api/items/1**, and JSON equivalent to:

~~~json
{"id":1,"name":"Notebook"}
~~~

Read the item:

~~~bash
curl -i http://localhost:8080/api/items/1
~~~

Expected response is 200 with header X-Source: in-memory-demo and the item's JSON body.

Update the item:

~~~bash
curl -i -X PUT http://localhost:8080/api/items/1 -H "Content-Type: application/json" -d '{"name":"Updated Notebook"}'
~~~

Expected response is 204, **with no response body**.

Delete the item:

~~~bash
curl -i -X DELETE http://localhost:8080/api/items/1
~~~

The first delete returns 204; deleting again or calling GET /api/items/1 afterward returns 404 per controller logic.

Compare with an empty 200:

~~~bash
curl -i http://localhost:8080/api/items/ping
~~~

Status 200 and header X-Health: ready, with no body object. There is no need to change it to 204 if the endpoint contract intends status 200.

**Do not compare all response headers verbatim** in examples because Date, Server, transfer/caching headers, or proxy info can differ across runtimes/versions.

## 12. Testing MVC with MockMvc

In Spring Boot 3.x, add **spring-boot-starter-test** in test scope if not already present, then use MockMvc to verify status, headers, and body. The example below tests the POST → GET → PUT → DELETE path in **one test method**, since the demo app uses in-memory state starting empty.

File: src/test/java/com/example/responses/ItemControllerTest.java

~~~java
package com.example.responses;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ItemControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void statusHeadersAndEmptyResponses() throws Exception {
        mvc.perform(post("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Notebook\"}"))
            .andExpect(status().isCreated())
            .andExpect(header().string("Location", "/api/items/1"))
            .andExpect(jsonPath("$.id").value(1));

        mvc.perform(get("/api/items/1"))
            .andExpect(status().isOk())
            .andExpect(header().string("X-Source", "in-memory-demo"))
            .andExpect(jsonPath("$.name").value("Notebook"));

        mvc.perform(put("/api/items/1")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Updated Notebook\"}"))
            .andExpect(status().isNoContent())
            .andExpect(content().string(""));

        mvc.perform(delete("/api/items/1"))
            .andExpect(status().isNoContent())
            .andExpect(content().string(""));

        mvc.perform(get("/api/items/1"))
            .andExpect(status().isNotFound());
    }
}
~~~

This test assumes the Spring Boot context is created once and no other test generated items beforehand. In projects with multiple tests running in parallel or sharing a context, never hardcode id 1: read the ID from Location/JSON and use the actual id, or reset state properly.

You can test the empty body for 200 separately:

~~~java
mvc.perform(get("/api/items/ping"))
    .andExpect(status().isOk())
    .andExpect(header().string("X-Health", "ready"))
    .andExpect(content().string(""));
~~~

Thus the test explicitly verifies **200 with empty content** separately from **204 forbidding content**. Spring Boot 4.x has test auto-configuration package changes; use imports matching your application's BOM/major version.

## 13. ResponseEntity in Spring WebFlux

Spring WebFlux also uses ResponseEntity, while allowing status/headers/body to be determined at different points because publishers can be asynchronous.

Common return types:

| Type | When are status and headers determined? | Body |
|---|---|---|
| ResponseEntity<T> | Immediately when the controller returns the entity | Object T handled by codec |
| ResponseEntity<Mono<T>> | Entity already fixes status/headers; body is emitted later | 0 or 1 async value |
| ResponseEntity<Flux<T>> | Status/headers fixed upfront; body can stream later | Multiple values |
| Mono<ResponseEntity<T>> | Once Mono emits the entity | Status/headers/body depend on async result |
| Mono<ResponseEntity<Flux<T>>> | Entity emitted async; Flux body streams afterward | Used for advanced cases |

### Choosing status based on an asynchronous result

Example service using a reactive repository:

~~~java
@GetMapping("/api/items/{id}")
public Mono<ResponseEntity<Item>> get(@PathVariable long id) {
    return repository.findById(id)
        .map(item -> ResponseEntity.ok(item))
        .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

This is an illustrative method inside a WebFlux `@RestController`; `repository.findById` returns `Mono<Item>`.

- When Mono emits an Item, the endpoint returns 200 and the body.
- When Mono completes empty, the endpoint returns 404 and no body.

**Important:** If you replace this with `ResponseEntity.ok(repository.findById(id))`, status 200 is decided **immediately**, before knowing whether the Publisher has data. An empty Mono body does not automatically convert 200 into 404. To vary status based on an async outcome, normally return **Mono<ResponseEntity<T>>**.

### Deleting without a body in a reactive service

Suppose `service.deleteById(id)` returns `Mono<Void>` and the business rule states deletion succeeded when the Mono completes normally:

~~~java
@DeleteMapping("/api/items/{id}")
public Mono<ResponseEntity<Void>> delete(@PathVariable long id) {
    return service.deleteById(id)
        .thenReturn(ResponseEntity.noContent().build());
}
~~~

This illustrates a **success => 204** contract. If 404 is needed when id does not exist, the service must differentiate outcomes: return a boolean or emit a matching error, then map to `ResponseEntity.notFound().build()`. An empty-completing `Mono<Void>` does not carry enough information to infer 404 on its own.

### Status and committed responses when streaming

When `ResponseEntity<Flux<T>>` provides a streaming body, the server may send headers/status before the stream ends. If the stream fails after the response is already committed, the framework cannot always change status from 200 to 500 or send a fresh JSON error.

With Server-Sent Events or NDJSON, design error reporting per streaming protocol or close the connection cleanly rather than relying on changing the HTTP status at the end of the stream.

### Testing WebFlux with WebTestClient

An illustrative check:

~~~java
webTestClient.get()
    .uri("/api/items/7")
    .exchange()
    .expectStatus().isNotFound()
    .expectBody().isEmpty();
~~~

In another test, when the repository already has the item:

~~~java
webTestClient.get()
    .uri("/api/items/7")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().contentTypeCompatibleWith(
        MediaType.APPLICATION_JSON
    )
    .expectBody()
    .jsonPath("$.id").isEqualTo(7);
~~~

These two snippets require `WebTestClient`, `MediaType`, and matching mock/test fixtures; they are test method snippets, not standalone files. You can also use `WebTestClient` to verify status 204 and no body with `expectBody().isEmpty()`.

## 14. Content-Type, Accept, and content negotiation

When a controller returns a body, the framework selects a converter/codec based on the Java type, the client's **Accept** header, the mapping's **produces**, and writable media types.

Controller example:

~~~java
@GetMapping(
    path = "/api/items/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ResponseEntity<Item> get(@PathVariable long id) {
    // ...
}
~~~

The snippet above only illustrates the annotation; it cannot run standalone because the method body is omitted to focus on `produces`. If a client only accepts XML while the endpoint/codec cannot supply XML, the app may return 406 Not Acceptable.

**Content-Type** describes the request body sent by the client. A POST that consumes application/json when a client sends text/plain can return 415 Unsupported Media Type.

When a response has no body, do not manually set `Content-Type: application/json` just because the controller sits in a REST API. Status 204 sends no representation body for the client to decode; attempting to serialize an object under 204 is a contradictory design.

Headers generated by the framework can depend on Spring MVC/WebFlux, Jackson, message converters, codecs, and content negotiation config. Test status/media type/body by **contract**, rather than asserting every default auxiliary header.

## 15. Error responses: use status codes, not just JSON fields

A bad pattern:

~~~java
return ResponseEntity.ok(
    Map.of("success", false, "error", "Not found")
);
~~~

This returns **HTTP 200**, even though the body reports an error. To standard HTTP clients, 200 is normally treated as a successful response.

A semantically clearer pattern:

~~~java
return ResponseEntity
    .status(HttpStatus.NOT_FOUND)
    .body(Map.of(
        "code", "ITEM_NOT_FOUND",
        "message", "Item not found"
    ));
~~~

This snippet illustrates usage with `Map` and `HttpStatus`. To keep the API consistent, define an error DTO or use **ProblemDetail** per RFC 9457 and Spring Framework 6+. Do not invent arbitrary ad-hoc error body formats in every controller.

In projects with many endpoints, centralized error handling is usually cleaner:

- **@RestControllerAdvice** and **@ExceptionHandler** for business errors.
- **ResponseStatusException** in MVC/WebFlux when emitting statuses inside reactive chains or service adapters.
- Error-handling infrastructure provided by Spring Boot, configured to mask sensitive information.

Pick 401/403 per security semantics, 404 for missing resources, 409 for conflicts, and 500 for server errors. Never catch `Throwable` and return 200, and never expose stack traces in production responses.

## 16. Common mistakes when using ResponseEntity

### Returning JSON under status 204

Status 204 must contain no response content. Use `noContent().build()` instead of trying to send an empty JSON object or success message.

### Returning 200 for resource creation when the contract specifies 201

Clients may rely on `Location` and status to fetch the new resource. Use `created(location)` when creation completes, if appropriate for the API design.

### Using 202 for a job that completed immediately

202 expresses accepted and incomplete processing. If creation succeeded and the resource already exists, 201 or 200 is more appropriate.

### Confusing an empty response body with 404 in WebFlux

`Mono.empty()` merely means completion without a value; it does not automatically signal a missing resource. Use `switchIfEmpty`/`map`/`defaultIfEmpty` and return `Mono<ResponseEntity<T>>` or an appropriate HTTP error.

### Overusing new ResponseEntity<>(...)

`ResponseEntity` constructors still have uses, yet builders like `ok()`, `created()`, `noContent()`, and `status()` are usually more readable and reduce mistakes with status/header/body arguments.

### Sending a Location that mismatches the actual route

For example, the resource lives at `/api/items/{id}` yet the server sets Location to `/items/{id}`. Clients will follow the wrong path. With context paths or gateway prefixes, build URIs following the public routing contract rather than concatenating internal hostnames.

### Setting Content-Length manually on JSON/streaming responses

The framework may compress, encode, or stream a different byte count than you expect. Do not set Content-Length manually unless you truly control the representation and framing.

### Thinking 304 is a successful DELETE response

304 is for conditional retrieval/caching. Successful DELETE/PUT without a body typically uses 204.

### Calling HEAD while expecting a JSON body

HEAD returns headers without response content. If you need JSON, call GET per the API contract.

### Setting status after the response is committed

Once headers/body have been sent, changing the status cannot be guaranteed. In WebFlux streaming, distinguish errors before commit from errors after commit.

### Failing to test 404/409/400 branches

A single 200 happy-path test is not enough. Before deploying, test every used status group, media types, empty bodies, Location, caching, validation errors, retries, and security.

### Inserting raw user input into response headers

Header values follow formatting rules and can feed into redirects, caching, or logs. Validate input, prevent CR/LF injection, and never leak tokens or sensitive info.

## 17. API design checklist

When adding a new endpoint, answer:

1. Which HTTP method fits: GET, POST, PUT, PATCH, or DELETE?
2. Was the resource created/modified/deleted completely, or only accepted for processing?
3. Is the success status 200, 201, 202, or 204? Is a body truly needed?
4. If creating a resource, is `Location` set to the accurate resource URI?
5. If not found, does the 404 response need a `ProblemDetail`/consistent error body?
6. If concurrent updates can collide, are `ETag`/`If-Match` and 412 used?
7. Do `Content-Type`/`Accept` match actual converters/codecs?
8. Does the response need `Cache-Control`, `ETag`, `Vary`, `Retry-After`, or trace headers?
9. Do proxies/gateways alter host, scheme, port, or prefix?
10. If returning streaming `Flux`, could headers/status commit before the stream finishes?
11. Do tests assert the response body is **actually empty** when returning 204?
12. Do tests cover status codes on error branches and header safety?

A good API does not need to use every status/header type, yet every type chosen must have a consistent meaning, documentation, and tests.

## 18. Self-check questions

**Question 1:** Which components does `ResponseEntity<T>` control explicitly that a plain returned object cannot control directly via its return type?  
**Question 2:** POST created a new item and you want to return Location and a JSON body: which builder do you choose?  
**Question 3:** Successful DELETE with no body: choose 200 or 204?  
**Question 4:** Is 200 with a zero-length body the same as 204?  
**Question 5:** Are HEAD and 304 allowed to send a response body?  
**Question 6:** WebFlux `repository.findById` returns `Mono.empty()`. Does `ResponseEntity.ok(mono)` automatically turn into 404?  
**Question 7:** What is the difference between `ResponseEntity<Mono<Item>>` and `Mono<ResponseEntity<Item>>`?  
**Question 8:** Which header should carry the URI of the newly created resource after a 201 POST?  
**Question 9:** Which header relates to cache validation using `If-None-Match`?  
**Question 10:** Why shouldn't you manually set `Content-Length` when writing JSON/Flux?  
**Question 11:** Under optimistic concurrency, which status can an unmatched `If-Match` lead to?  
**Question 12:** Once a `Flux` has transmitted part of the body and then errors, can you change the already-sent HTTP status?

### Answers

1. Status, response headers, and body intentionally.
2. `ResponseEntity.created(location).body(created)`.
3. Normally 204 No Content when the contract specifies success returns no content.
4. No; 204 forbids content and conveys distinct semantics.
5. No; HEAD and 304 carry no response content.
6. No; the `ResponseEntity` status is already 200. Map data into `Mono<ResponseEntity<Item>>` or handle missing results explicitly.
7. The first fixes status/headers immediately with an async body; the second determines status/headers based on the async result.
8. `Location`.
9. `ETag`.
10. Codecs/compression/streaming may determine bytes at write time; wrong framing breaks clients.
11. 412 Precondition Failed.
12. Committed headers cannot be retracted; handle streaming errors via an appropriate mechanism.

## 19. Official references

- [Spring Framework — ResponseEntity in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html): handling status, headers, and body in Servlet MVC.
- [Spring Framework — ResponseEntity in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html): `ResponseEntity<Publisher>` and `Publisher<ResponseEntity>` types.
- [Spring Framework — ResponseEntity API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseEntity.html): builders, factory methods, and getters.
- [Spring Framework — HttpHeaders API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/HttpHeaders.html): header API and related values.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`, `ErrorResponse`, and exception handling.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): testing status, headers, and response content.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): testing HTTP in WebFlux.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): meanings of 200/201/202/204/205/304, HEAD, Location, ETag, and conditions with no response content.
