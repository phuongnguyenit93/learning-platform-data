# Handling HEAD, OPTIONS, and Distinguishing HTTP 404, 405, 406, and 415 in Spring MVC

## Objectives and Scope

After this lesson, you will be able to explain why a controller method using `@GetMapping` normally handles `HEAD`, read the `Allow` header in an `OPTIONS` response, and accurately diagnose whether a failing request is wrong in its **path**, **HTTP method**, **response media type**, or **request body media type**. Examples use Spring MVC on the Servlet stack, Java 17+, and Spring Framework 6+/Spring Boot 3.x syntax. HTTP rules form the foundation; default error bodies may differ across versions, Spring Boot configurations, filters, and servers.

## 1. Handler Selection Flow: Where the Four Error Codes Originate

With `@RequestMapping`, Spring MVC chooses a handler based on multiple conditions. To diagnose issues, check the following operational questions:

1. **Path:** Is there a controller/resource accepting this URL? If no matching resource exists, the outcome is typically `404 Not Found`.
2. **HTTP method:** Does the path match, yet it does not support `GET`, `POST`, `PUT`… sent by the client? For typical controller mappings, the result is `405 Method Not Allowed`; inspect the `Allow` header to see supported methods.
3. **Request `Content-Type`:** Does the endpoint require JSON while the client sends `text/plain`? It may return `415 Unsupported Media Type`.
4. **Request `Accept`:** Does the client only accept XML while the endpoint only provides JSON? It may return `406 Not Acceptable`.

This is a **classification model**, not a guarantee that Spring always evaluates every condition strictly in order 1→4; mapping selection, message converters, exception handlers, and filters can alter the resulting status code when a request violates multiple conditions simultaneously. In standard `RequestMappingInfoHandlerMapping` processing, `method`, `consumes`, and `produces` conditions are inspected when no full mapping match is found. Additionally, request/response bodies can still be rejected during reading/writing by `HttpMessageConverter`s.

| Code | Standard name | Diagnostic question | Common symptoms |
| --- | --- | --- | --- |
| `404` | Not Found | Does the URL/resource exist or get routed? | Wrong path, missing prefix, resource not found |
| `405` | Method Not Allowed | Is the URL right but the method wrong? | `POST` to an endpoint declaring only `GET`; response includes `Allow` |
| `406` | Not Acceptable | Does the server have a representation matching `Accept`? | Client demands `application/xml`, server only `produces = application/json` |
| `415` | Unsupported Media Type | Does the client's body have a `Content-Type` the endpoint/decoder accepts? | Sending `text/plain` to an endpoint with `consumes = application/json` |

Two headers that are very easy to confuse:

- `Content-Type` describes **the data type of the body being sent** (request) or **the data type of the body being returned** (response).
- `Accept` describes **the data types the client can receive**; e.g., `Accept: application/json`. It does not state that the request body is JSON.
- `consumes` is a condition on the **input** media type, usually for POST/PUT/PATCH with a body. `produces` is a condition on the **output** media type. Spring can still perform content negotiation and use `HttpMessageConverter`s even when these two attributes are omitted.

## 2. HTTP HEAD: Fetching Metadata Without a Response Body

In HTTP semantics, `HEAD` is identical to `GET` in asking for information about a resource, except **the response contains no message body**. Headers of a `HEAD` response should match those of `GET`, such as `Content-Type`, `ETag`, `Last-Modified`, or `Content-Length` when the server can determine it. Do not assume every server returns `Content-Length` or identical headers to `GET` in every detail.

In Spring MVC, `@GetMapping` and `@RequestMapping(method = RequestMethod.GET)` **automatically support HEAD**. Normally you do not have to write a separate `@RequestMapping(method = RequestMethod.HEAD)`; Spring/Servlet handles omitting the body. This has consequences:

- A client sending `HEAD /api/items/5` can pass through the same controller logic as `GET /api/items/5`; database reads, computations, or business errors can still occur.
- `HEAD` **does not automatically make GET cheaper**. For expensive payloads, consider caching, metadata endpoints, or a dedicated `HEAD` handler when justified by measurements.
- A proper `HEAD` must have no response body. Do not assume HEAD returns `204 No Content`: a successful HEAD for a GET typically has **status 200**, differing only by omitting the body.
- Use `curl -I` (or `curl --head`) to test; avoid `curl -X HEAD` because forcing the method manually may leave `curl` waiting for a body differently from `--head` mode.

Illustrative example:

```http
GET /api/items/5 HTTP/1.1
Host: localhost:8080
Accept: application/json
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":5,"name":"Pen"}
```

Same resource with `HEAD`:

```http
HEAD /api/items/5 HTTP/1.1
Host: localhost:8080
```

```http
HTTP/1.1 200 OK
Content-Type: application/json
```

The HTTP example intentionally shows only essential headers; many servers also add `Content-Length`, `Date`, and others. **There is no JSON/body** after a HEAD response.

When custom behavior is required, an explicit `HEAD` mapping can be declared, provided compatibility with `GET` is verified and HEAD responses do not trigger unexpected side effects. Avoid treating HEAD as a completely zero-cost URL existence check.

## 3. HTTP OPTIONS: Querying Supported Methods

`OPTIONS` queries the communication options of a resource. In Spring MVC, if no custom OPTIONS handler is defined, the framework normally responds automatically with an `Allow` header synthesized from all `@RequestMapping`s matching that URL. A mapping declaring only `GET` typically supports `GET` and `HEAD`; `OPTIONS` may appear in `Allow` due to automatic handling. If a `@RequestMapping` does not restrict `method`, the default list can be very broad (`GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS`), so **always declare methods explicitly** for APIs.

Example of a GET-only endpoint:

```http
OPTIONS /api/items/5 HTTP/1.1
Host: localhost:8080
```

Typical response:

```http
HTTP/1.1 200 OK
Allow: GET, HEAD, OPTIONS
```

Do not rely on the ordering of methods inside `Allow` in tests; values can vary by handler and environment. If the endpoint also supports PUT/DELETE, `Allow` reflects the corresponding mapping configuration.

**Standard OPTIONS differs from a CORS preflight**:

- A browser preflight is also `OPTIONS`, but typically carries `Origin` and `Access-Control-Request-Method`, and possibly `Access-Control-Request-Headers`.
- A CORS preflight asks: "Is this origin allowed to call the intended method/headers?"; the response is governed by CORS configuration, using headers such as `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, and `Access-Control-Allow-Headers`.
- An API having a `POST` mapping does not mean a browser from another origin is allowed to POST. CORS or Spring Security may reject the preflight with `403` or another response before reaching the controller.
- HTTP's `Allow` header does not replace `Access-Control-Allow-Methods`. When debugging CORS errors, check CORS/filter/security configuration rather than reading `@RequestMapping` alone.

Preflight example:

```http
OPTIONS /api/items HTTP/1.1
Origin: https://frontend.example
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
```

This is a CORS request; **do not assume** it succeeds without configuring allowed origins, methods, and headers.

## 4. Java 17+ Controller Example to Try Yourself

Use a Spring Boot 3.x application with the `spring-boot-starter-web` dependency. Place the following class at `src/main/java/com/example/demo/ItemController.java`; the package must fall inside the component scan scope of the `@SpringBootApplication` class. No separate HEAD or OPTIONS endpoints are needed for this lesson.

```java
package com.example.demo;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    @GetMapping(path = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    public Item find(@PathVariable("id") long id) {
        return new Item(id, "Pen");
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<Item> create(@RequestBody Item item) {
        return ResponseEntity.status(HttpStatus.CREATED).body(item);
    }

    public record Item(long id, String name) {}
}
```

Reading the mappings:

- `GET /api/items/5` returns JSON for `Item(5, "Pen")`.
- `HEAD /api/items/5` is supported via the GET mapping.
- `OPTIONS /api/items/5` typically returns `Allow` automatically for that resource.
- `POST /api/items` accepts a **JSON request** and returns a **JSON response** with status `201 Created`. This is only an echo demo; it does not persist to a database.
- `PUT /api/items/5` uses the wrong method. `GET /api/items/missing/child` uses the wrong path. `Accept: application/xml` mismatches GET which only produces JSON. `POST /api/items` with `Content-Type: text/plain` mismatches POST which only consumes JSON.

If creating a new project, at minimum you need a `@SpringBootApplication` class with `main`, Java 17+, the Web dependency, and Maven/Gradle. In a Maven project with the wrapper:

```bash
./mvnw spring-boot:run
```

On Windows PowerShell you can run `.\mvnw.cmd spring-boot:run`. Default port is `8080` unless `server.port` is changed. The controller code above is a **complete class compilable inside a Spring Boot project** with configured dependencies; a single standalone Java file cannot be compiled with `javac` without Spring libraries.

## 5. Practice with curl: Six Distinguishing Scenarios

Run the commands below once the app is running on `localhost:8080`. Other headers may appear depending on configuration; focus on **HTTP status**, `Allow`, `Content-Type`, and presence/absence of a body.

**(A) Successful GET, 200:**

```bash
curl -i -H "Accept: application/json" http://localhost:8080/api/items/5
```

Expected JSON body:

```json
{"id":5,"name":"Pen"}
```

**(B) Successful HEAD, 200:**

```bash
curl -I http://localhost:8080/api/items/5
```

Check status and response headers; there is no JSON body. `Content-Length` may be provided depending on the processing mechanism and server.

**(C) OPTIONS, inspecting Allow:**

```bash
curl -i -X OPTIONS http://localhost:8080/api/items/5
```

Expect `200 OK` with `Allow` containing `GET`, `HEAD` (typically also `OPTIONS`). Sending `OPTIONS` with CORS headers is a different test.

**(D) 404: Unmatched URL:**

```bash
curl -i http://localhost:8080/api/items/5/unknown
```

Expect `404 Not Found` because no mapping matches this path. Spring Boot may route the request to the static resource handler before concluding it does not exist; the final status may still be 404 while the internal exception differs.

**(E) 405: Right URL, Wrong HTTP Method:**

```bash
curl -i -X PUT http://localhost:8080/api/items/5
```

Expect `405 Method Not Allowed`; per HTTP standards, a 405 response must include an `Allow` header listing currently supported methods for the resource. On the demo controller, those are GET/HEAD and usually OPTIONS. Do not "fix" a 405 by changing the URL when the URL is already right; check the method.

**(F) 406: Client Accepts Only XML, Server Produces Only JSON:**

```bash
curl -i -H "Accept: application/xml" http://localhost:8080/api/items/5
```

Expect `406 Not Acceptable` because the GET mapping declares `produces = application/json`. Sending `Accept: */*` or `Accept: application/json` allows the JSON representation to be selected. Adding an XML-capable endpoint or changing negotiation/converter config changes this behavior.

**(G) 415: Client Sends Wrong Body Type:**

```bash
curl -i -X POST http://localhost:8080/api/items \
  -H "Content-Type: text/plain" \
  --data "hello"
```

Expect `415 Unsupported Media Type` because POST declares `consumes = application/json`. Send a valid JSON request:

```bash
curl -i http://localhost:8080/api/items \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data '{"id":9,"name":"Notebook"}'
```

Expect `201 Created` and body:

```json
{"id":9,"name":"Notebook"}
```

When running multi-line shell commands: `\` is line continuation for bash/zsh; in PowerShell, write the entire `curl` command on **one line** and invoke `curl.exe` to avoid the `Invoke-WebRequest` alias in older Windows PowerShell. Avoid turning illustrative examples into claims that every environment returns identical error JSON: only HTTP status codes and required/defined headers are the focus.

## 6. When Does Spring MVC Return These Errors?

### 404 Not Found

If no matching handler/resource is found, Spring MVC or the resource-serving layer can result in 404. In newer Spring versions, the static resource handler may raise `NoResourceFoundException`; when no handler is found, `NoHandlerFoundException` may be used depending on configuration. Do not infer the exact exception class solely from the status code.

Real-world causes: wrong `context-path`, missing class-level `@RequestMapping` prefix, trailing slash/case mismatch, proxy URL rewriting, path variable routing differently than expected, missing static file. If the path exists on the service yet returns 404 at the gateway, inspect the reverse proxy as well.

### 405 Method Not Allowed

The path matches a controller mapping, yet the HTTP method is unsupported. Spring MVC typically represents this via `HttpRequestMethodNotSupportedException`. Check `Allow`, `@GetMapping`/`@PostMapping`, and the actual method in the browser network tab; sometimes an HTML form, browser, or HTTP client alters the method. Do not forget implicit `HEAD` when GET exists.

That a URL "exists" in the app does not guarantee every request to it gets 405; filters, security, static resources, or other mapping conditions can intervene.

### 406 Not Acceptable

The client requests a representation via `Accept`, yet the server cannot provide that type. Spring MVC may raise `HttpMediaTypeNotAcceptableException` during `produces` mapping selection or negotiation/conversion when writing the response. Check `Accept`, `produces`, registered message converters, and the return object type. Returning a Java object does not guarantee support for every format; XML, for instance, requires suitable configuration/converters.

For example: `Accept: application/xml` does not mean "the request body is XML". It requests an **XML response**.

### 415 Unsupported Media Type

The request carries a `Content-Type` unsupported by the `consumes` mapping or the body-reading message converter. Spring MVC may raise `HttpMediaTypeNotSupportedException`. Check the actual sent `Content-Type` header, `consumes`, and whether a converter can read that media type into the `@RequestBody` type. Even if the body is JSON, labeling it `text/plain` can trigger 415 before parsing.

Conversely, if `Content-Type: application/json` is right yet the **JSON is malformed**, the error is usually **400 Bad Request**, e.g., `HttpMessageNotReadableException`, not 415. Do not confuse with `406`: 415 asks **what the server reads from the client**, while 406 asks **what the client accepts from the server**.

## 7. Quick Diagnostic Table on the Same Endpoint Set

| Request | Key condition | Expected status in demo |
| --- | --- | --- |
| `GET /api/items/5`, `Accept: application/json` | Matching path, method, and output | `200` |
| `HEAD /api/items/5` | GET mapping supports HEAD implicitly | `200`, no body |
| `OPTIONS /api/items/5` | Queries supported HTTP methods | Usually `200`, with `Allow` |
| `GET /api/items/5/unknown` | No matching mapping/resource | `404` |
| `PUT /api/items/5` | Path has GET but not PUT | `405`, with `Allow` |
| `GET /api/items/5`, `Accept: application/xml` | Unsatisfiable response type | `406` |
| `POST /api/items`, `Content-Type: text/plain` | Unsupported request body type | `415` |
| `POST /api/items`, `Content-Type: application/json`, bad JSON | Media type accepted, body syntax invalid | Usually `400` |
| `POST /api/items`, valid JSON and `Accept: application/json` | Input/output match | `201` |

Because `OPTIONS` also serves preflight requests and errors can be customized via `@ControllerAdvice`, this table describes the demo environment without extra security/CORS filters.

## 8. Automated Testing with MockMvc

In a Spring Boot project with `spring-boot-starter-test`, place the file at `src/test/java/com/example/demo/HttpMethodRoutingTest.java`. The test uses the demo controller and its Spring Boot environment. Assertions focus on core statuses and headers without depending on Boot-generated error JSON.

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.head;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HttpMethodRoutingTest {

    @Autowired
    MockMvc mvc;

    @Test
    void headUsesGetMappingWithoutBody() throws Exception {
        mvc.perform(head("/api/items/5"))
            .andExpect(status().isOk())
            .andExpect(content().string(""));
    }

    @Test
    void optionsReportsSupportedMethods() throws Exception {
        mvc.perform(options("/api/items/5"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ALLOW, containsString("GET")));
    }

    @Test
    void missingPathReturns404() throws Exception {
        mvc.perform(get("/api/items/5/unknown"))
            .andExpect(status().isNotFound());
    }

    @Test
    void wrongMethodReturns405() throws Exception {
        mvc.perform(put("/api/items/5"))
            .andExpect(status().isMethodNotAllowed())
            .andExpect(header().string(
                HttpHeaders.ALLOW, containsString("GET")));
    }

    @Test
    void incompatibleAcceptReturns406() throws Exception {
        mvc.perform(get("/api/items/5")
                .accept(MediaType.APPLICATION_XML))
            .andExpect(status().isNotAcceptable());
    }

    @Test
    void incompatibleContentTypeReturns415() throws Exception {
        mvc.perform(post("/api/items")
                .contentType(MediaType.TEXT_PLAIN)
                .content("hello"))
            .andExpect(status().isUnsupportedMediaType());
    }
}
```

Run `./mvnw test` (Windows: `.\mvnw.cmd test`). If the project includes Spring Security or custom CORS configuration, configure MockMvc/test security appropriately; filters may return `401`, `403`, or redirect before controller logic runs.

## 9. Practical Debugging and Common Pitfalls

1. **Verify the actual received request**: method, URL/path after reverse proxies, query, `Content-Type`, `Accept`, body. API tools in particular may auto-add `Accept: */*` or switch `Content-Type` when form-data is chosen.
2. **Read registered mappings**: check class and method annotations; Spring Boot Actuator `/actuator/mappings` (when present and enabled/exposed) shows actual mappings. Expose management endpoints only per application security policy.
3. **Use a minimal request matrix**: same URL, changing one thing at a time: method → `Accept` → `Content-Type`. Changing multiple headers/methods at once can let one error mask another.
4. **Check response status and headers before the body**: `Allow` aids 405/OPTIONS investigation; response `Content-Type` tells what content type the server returned. Error bodies may be customized by `ProblemDetail`, error controllers, or gateways.
5. **Separate CORS from mapping**: inspect `Origin`/`Access-Control-Request-Method` and CORS policy; a failed preflight does not mean the controller lacks support for the method.
6. **Separate 415 from JSON parse failure**: `415` is a media-type problem; `400` is usually malformed body/missing fields/data conversion, depending on validation.
7. **Separate 404 from 405**: 404 points to path/resource; 405 points to method. If every method returns 404, check route prefixes and deployment first.
8. **Avoid careless `@RequestMapping` without `method`**: it can unintentionally widen `Allow` and let the API accept unwanted methods.
9. **Avoid custom error handlers that strip required headers**: when catching `HttpRequestMethodNotSupportedException` to standardize error JSON, preserve `Allow`. Spring MVC provides `DefaultHandlerExceptionResolver` and `ResponseEntityExceptionHandler`; prefer preserving standard semantics in `@ControllerAdvice`.
10. **Do not assume "404 is always NoHandlerFoundException"**: resource handlers, path matching, framework versions, and custom error handlers vary. Use logs and mappings to trace the real failing step.

## 10. Self-Check Knowledge Questions

- Can `HEAD /api/items/5` enter `@GetMapping`? **Yes**, Spring MVC supports HEAD implicitly; the response has no body, though the handler may still execute work.
- Which header does `OPTIONS` return to report supported methods? **`Allow`**. For CORS preflight, also check `Access-Control-Allow-*` headers and origin configuration.
- URL has a GET mapping yet receives PUT: **405** and check `Allow`. URL has no mapping/resource: typically **404**.
- GET only `produces = application/json`, yet request sends `Accept: application/xml`: **406**.
- POST `consumes = application/json`, yet request sends `Content-Type: text/plain`: **415**.
- POST sends `Content-Type: application/json` with `{bad json}` body: normally **400**, because the media type matches yet the JSON is unreadable.
- Can `Accept` and `Content-Type` substitute for each other? **No**; one describes data the client wants to **receive**, while the other describes the body **being sent** (in the request).

## References

- Spring Framework — Mapping Requests (covering HEAD, OPTIONS, `consumes`, `produces`): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework — Error Responses and `ResponseEntityExceptionHandler`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework — MVC Exception Resolvers: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/exceptionhandlers.html
- HTTP Semantics (RFC 9110): https://www.rfc-editor.org/rfc/rfc9110.html
