# Content-Type, Accept, and Content Negotiation

## 1. Objectives and Context

When communicating over HTTP, client and server must agree on **what format the data being sent is in** and **what formats the client can receive**. Two key headers are `Content-Type` and `Accept`. In Spring Boot, selecting a handler, reading the request body, and producing the response body also involve `consumes`, `produces`, and message converters/codecs.

After this lesson, you should be able to:

- Distinguish the roles of `Content-Type` and `Accept` in requests/responses.
- Read media types, `charset` parameters, wildcards, and `q` weights.
- Explain the content negotiation process and HTTP errors 400, 406, and 415.
- Apply `consumes`, `produces`, `@RequestBody`, and `@RestController` in Spring Boot.
- Test APIs with `curl` and handle format mismatch errors systematically.

## 2. Resource Representations and Media Types

A URI identifies a resource, such as `/api/books/7`. A representation is the content sent over HTTP to describe that resource: JSON, XML, plain text, HTML, images, etc. In principle, the same resource can have multiple representations; the server only returns representations it actually supports.

A **media type** has the form `type/subtype`, optionally with parameters:

| Media type | Commonly used for |
| --- | --- |
| `application/json` | API JSON payloads |
| `text/plain; charset=UTF-8` | Plain text and character encoding |
| `text/html` | HTML documents |
| `application/xml` | XML, if supported by the server |
| `application/x-www-form-urlencoded` | Key-value form body |
| `multipart/form-data; boundary=...` | Multipart body, typically file uploads |
| `application/octet-stream` | General binary data |
| `application/problem+json` | Error representation per Problem Details (when supported by the application) |

`Content-Type: application/json` declares that the body is JSON; it does not by itself prove the body is valid JSON syntax. With `multipart/form-data`, `boundary` defines the delimiter between parts: when sending via a browser or `curl -F`, let the tool generate the appropriate header and boundary instead of manually setting a value that does not match the body.

Media type is not synonymous with file extension. A path `/books/7.json` does not automatically cause Spring to return JSON. The output format is part of the protocol and request-handling configuration.

## 3. Content-Type vs. Accept: Where Do They Differ?

| Header | Where does it appear? | Meaning | Example |
| --- | --- | --- | --- |
| `Content-Type` | Requests with a body | Describes the format of the **body sent by the client** | `Content-Type: application/json` |
| `Accept` | Requests | Lists the formats of the **response accepted by the client** | `Accept: application/json` |
| `Content-Type` | Responses with a body | Indicates the format of the **body actually returned by the server** | `Content-Type: application/json` |

Therefore, a request can simultaneously carry `Content-Type: application/json` and `Accept: text/plain`: the client sends JSON yet wants plain text back. These two requirements are independent; the server must support each side for the exchange to succeed.

Example of a simplified HTTP exchange:

~~~http
POST /api/books HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json

{"title":"HTTP Basics"}
~~~

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"id":1,"title":"HTTP Basics"}
~~~

The request sends JSON and accepts JSON; the response is actually JSON. The status code and payload illustrate a successful resource creation operation.

**Common misconceptions:**

- `Accept` **does not describe the request body**; setting `Accept: application/json` does not turn a plain-text body into JSON.
- `Content-Type` in a **response** describes the data the server actually sent, not a proposal for the client to negotiate further.
- For a normal `GET` without a request body, the request does not need `Content-Type`. Conversely, `Accept` remains useful because GET typically receives a response body.
- A request without `Accept` is interpreted as placing no format restriction at this header level; `Accept: */*` likewise accepts any media type. That **does not guarantee** the server can return every format.
- HTTP header names are case-insensitive; writing `Content-Type` and `Accept` is a readability convention.

## 4. Accept: Lists, Wildcards, and `q` Weights

A client can accept multiple formats and express relative preference weights:

~~~http
Accept: application/json, text/plain;q=0.7, */*;q=0.1
~~~

How to read it:

- `application/json` omits `q`, so it has `q=1` (default preference).
- `text/plain;q=0.7` is accepted with lower preference than JSON.
- `*/*;q=0.1` accepts remaining media types at low preference.
- `q=0` means that media range is not acceptable; `q` ranges from `0` to `1`.
- `application/*` matches subtypes of `application`; `*/*` matches more broadly. More specific media ranges determine precedence when declarations overlap.

For example, `Accept: application/json;q=0, text/plain;q=1` excludes JSON and prefers plain text. The server must consider **available representations** along with media-range matching rules; it cannot promise to return JSON just because JSON has a high weight if the endpoint only supports XML. `q` expresses client-side preference, not an absolute guarantee of every server's selection algorithm.

Distinguish `q` from a `Content-Type` parameter:

~~~http
Content-Type: text/plain; charset=UTF-8
Accept: text/plain; q=0.8, application/json; q=1
~~~

`charset=UTF-8` describes the character encoding of the text being sent; `q=0.8` describes the preference level for a representation in `Accept`. Do not put `q` into `Content-Type` to ask the server to prefer another format.

## 5. How Does Content Negotiation Happen?

**Content negotiation** is the process of choosing an appropriate response representation between what the client accepts and what the server provides. For a typical Spring Boot API, you can understand the process conceptually as follows:

1. Spring identifies candidate mappings based on the HTTP method and path.
2. If the request has a body, the `consumes` condition and media-type reader availability determine whether the handler/reader accepts the request; the body is then decoded into a Java object when needed.
3. The `produces` condition, the `Accept` header, and available writers determine a valid response representation.
4. Spring writes the response body, sets the actual `Content-Type`, and sends the appropriate status.

This is a mental model for reasoning, not a fixed execution order for every internal Spring component. Mapping selection and media-type condition checks can happen together before invoking the controller method.

~~~text
Client sends request
  |-- Content-Type: what format is the sent body?
  |            |-- unsupported --> usually 415
  |            '-- supported --> read/parse body (invalid syntax may be 400)
  |
  '-- Accept: which response format is accepted?
               |-- no matching representation --> usually 406
               '-- matched --> serialize and return actual Content-Type
~~~

When a server supports both JSON and XML for the same resource, `Accept` helps choose between them. When an endpoint **only** returns JSON, `Accept: application/xml` will not conjure up an XML converter on its own.

In Spring MVC, the default content negotiation strategy inspects the `Accept` header. You can customize the strategy via configuration, but you should not assume URL extensions like `.json` or `.xml` automatically enable format negotiation.

## 6. Usage in Spring Boot and Spring MVC

Different components have distinct roles:

- `@RestController`: declares a controller whose methods return data for the response body (equivalent to `@Controller` combined with `@ResponseBody` semantics).
- `@RequestBody`: instructs Spring to read the request body and convert it into a Java parameter using a suitable `HttpMessageConverter`.
- `@PostMapping(consumes = "...")`, `@RequestMapping(consumes = "...")`: restricts the **request** media types a mapping accepts.
- `@GetMapping(produces = "...")`, `@RequestMapping(produces = "...")`: restricts the **response** media types a mapping can produce and uses them when matching `Accept`.
- `HttpMessageConverter`: reads/writes bodies in Spring MVC; for example, the Jackson-based converter transforms JSON to Java objects and vice versa.
- `ResponseEntity<T>`: explicitly sets the response status, headers, and body.

`consumes` and `produces` are **declarative conditions**—they do not automatically install data conversion libraries. For example, declaring `produces = "application/xml"` is not enough to return XML if the application lacks an appropriate XML converter/serializer. With Spring Boot 3.x and the standard `spring-boot-starter-web` dependency, Jackson JSON is auto-configured.

In Spring WebFlux, the `@RequestBody`/`@GetMapping` annotations and `consumes`/`produces` semantics remain similar, but the reactive stack uses `HttpMessageReader`/`HttpMessageWriter` and codecs instead of the MVC `HttpMessageConverter` chain. Do not mix converter configuration details between the two stacks.

## 7. Runnable Java 17+ Example: A JSON-Only API

Create a **Spring Boot 3.x**, **Java 17 or newer** project with the **Spring Web** dependency using Spring Initializr; keep the dependencies managed by the generated project. Place the following two files in the exact package `com.example.demo`. The example runs on Spring MVC without a database.

**File `src/main/java/com/example/demo/DemoApplication.java`**

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

**File `src/main/java/com/example/demo/BookController.java`**

~~~java
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
@RequestMapping("/api/books")
public class BookController {

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<BookResponse> create(@RequestBody BookRequest request) {
        BookResponse response = new BookResponse(1L, request.title());
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping(path = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    public BookResponse find(@PathVariable long id) {
        return new BookResponse(id, "Spring HTTP");
    }

    public record BookRequest(String title) {}
    public record BookResponse(long id, String title) {}
}
~~~

Explanation:

- POST `/api/books` only accepts requests with a media type compatible with `application/json`, uses Jackson to convert JSON into `BookRequest`, and produces a JSON `BookResponse`.
- GET `/api/books/{id}` takes no body, so it needs no `consumes`; `produces` asserts a JSON response.
- The two `record` declarations are Java data types. In the example, the id is hardcoded to `1` for creation and GET data is created in memory: the purpose is testing HTTP/media types, not real data management.
- `ResponseEntity.status(HttpStatus.CREATED)` produces status 201 for POST. A `BookResponse` returned directly by GET is normally sent by the framework with status 200.

Run the application from the project root directory:

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell, you can use `.\mvnw.cmd spring-boot:run`. If you generated a Gradle project, run `./gradlew bootRun` (Windows: `.\gradlew.bat bootRun`). This example requires the Spring Boot classpath/dependencies, so it cannot be compiled with a standalone `javac` command.

### Test 1 — send JSON and receive JSON: success

~~~bash
curl -i -X POST http://localhost:8080/api/books -H "Content-Type: application/json" -H "Accept: application/json" --data '{"title":"HTTP"}'
~~~

Key parts of the response:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"id":1,"title":"HTTP"}
~~~

Other headers such as `Date`, `Content-Length`, or default error bodies may vary by environment; what to verify is status 201, a JSON-compatible `Content-Type`, and the JSON payload containing `id` and `title` shown above.

### Test 2 — GET with matching Accept: success

~~~bash
curl -i -H "Accept: application/json" http://localhost:8080/api/books/7
~~~

Expect status `200 OK`, a JSON-compatible `Content-Type`, and body:

~~~json
{"id":7,"title":"Spring HTTP"}
~~~

### Test 3 — request body with wrong media type: 415

~~~bash
curl -i -X POST http://localhost:8080/api/books -H "Content-Type: text/plain" -H "Accept: application/json" --data 'HTTP'
~~~

Expect `415 Unsupported Media Type`: POST declares `consumes = application/json`, yet the client sent `text/plain`. Even though `Accept` asks for JSON back, it cannot fix the input format.

### Test 4 — response has no format accepted by the client: 406

~~~bash
curl -i -H "Accept: application/xml" http://localhost:8080/api/books/7
~~~

Expect `406 Not Acceptable`: GET specifies `produces = application/json`, whereas the client only accepts XML. Even adding an XML library will not switch this mapping to XML because `produces` restricts it to JSON.

### Test 5 — valid Content-Type, invalid JSON syntax: 400

~~~bash
curl -i -X POST http://localhost:8080/api/books -H "Content-Type: application/json" -H "Accept: application/json" --data '{"title":'
~~~

Expect `400 Bad Request` because the JSON body syntax is invalid, preventing Spring/Jackson from reading `@RequestBody`. This differs from 415: the media type was accepted, while the **content** could not be decoded. The JSON shape of the error message may vary by Spring Boot version and configuration.

If you are using Windows PowerShell, invoke `curl.exe` to avoid aliasing to PowerShell's legacy `curl` alias. The commands above can be used in any terminal with appropriate quoting adjustments.

## 8. What If a Resource Has Multiple Representations?

You can design two handlers with the same method/URI but different `produces` conditions. The snippet below is only an **extension to `BookController` in section 7** (not a standalone Java program):

~~~java
@GetMapping(path = "/{id}", produces = MediaType.TEXT_PLAIN_VALUE)
public String findAsText(@PathVariable long id) {
    return "Book " + id;
}
~~~

When this method is added to the controller above, a client calls GET `/api/books/7` with `Accept: application/json` to hit the JSON handler, or `Accept: text/plain` to hit the plain-text handler. The second response has body `Book 7` and media type `text/plain` matching `produces`. These are **two representations of the same path**.

When multiple handlers share a URI and a client sends `Accept: */*` or states no clear preference, verify and test the handler-selection behavior; do not assume one will always win. You can designate a default format in your API design, split URIs, or apply a consistent negotiation strategy.

Beyond `application/json`, there are extended media types such as `application/vnd.example.book+json`. Do not assume every JSON declaration matches every `+json` subtype when a mapping has a specific `produces`; design media types intentionally and test the corresponding mappings/converters.

## 9. Related Error Codes and How to Tell Them Apart

| Symptom | Typical code | Where to check |
| --- | --- | --- |
| POST sends `text/plain` to an endpoint with `consumes = application/json` | `415 Unsupported Media Type` | Check request `Content-Type` and `consumes`/reader |
| GET only returns JSON, client requests `Accept: application/xml` | `406 Not Acceptable` | Check `Accept`, `produces`, and response writer capability |
| Body claims to be JSON, but JSON syntax is invalid | `400 Bad Request` | Check body, data mapping, and `@RequestBody` decoding errors |
| Valid media type, but HTTP method is unsupported at the path | `405 Method Not Allowed` | Check GET/POST/PUT/... and mappings |
| No endpoint matches the path | `404 Not Found` | Check path and routing |

These are typical results in an API configured like the example; gateways, filters, security, exception handlers, or custom negotiation strategies can alter the specific response. `415` can also relate to request encoding. `406` does not mean the resource does not exist: the problem is the acceptable response format.

Short debugging workflow:

1. Inspect the **actual request** in the Network tab, `curl -v`, or an HTTP client: method, URI, `Content-Type`, `Accept`, and the bytes/body sent.
2. On **415**, compare `Content-Type` against `consumes` and verify a converter can read that format. For example, `curl --data` defaults to form data if `Content-Type` is omitted; JSON requires the header and valid JSON.
3. On **406**, compare `Accept` against `produces` and writable data types/codecs. Only add `produces = application/xml` when real XML conversion is supported.
4. On **400**, inspect decoding/validation errors and JSON structure rather than immediately changing `Accept`.
5. When serving multiple representations for one URL behind an intermediary cache, consider the `Vary: Accept` response header so caches distinguish variants. `Vary` does not solve negotiation automatically; it documents which request header affected response selection.

## 10. Takeaways for API Design

- For JSON-only APIs, define the contract clearly: requests with a JSON body use `Content-Type: application/json`, clients wanting JSON send `Accept: application/json`, and the server returns responses with a matching `Content-Type`.
- Use `consumes` to constrain the **input** format and `produces` to declare the **output** format; do not swap them.
- Do not think setting `Content-Type` lets you ignore body structure, or that declaring `produces` gives Spring a converter automatically.
- Avoid relying on URL extensions, accidental handler ordering, or browser default `Accept` headers.
- When a resource has multiple representations, test at least three cases: exact media type match, mismatched media type, and broad/missing `Accept`.

**Self-check:**

1. A POST request has `Content-Type: application/json` and `Accept: text/plain`. Which header governs reading the body, and which governs choosing the response?
2. Why doesn't `Accept: application/json` prevent a 415 error when the body is sent as `text/plain`?
3. Why can `Content-Type: application/json` still lead to a 400?
4. How will an endpoint with only `produces = application/json` respond when a client sends `Accept: application/xml`?
5. When serving the same URI as both JSON and plain text, what must you watch out for regarding `Accept: */*` and caching?

**Guided answers:** (1) `Content-Type` for input, `Accept` for output; (2) `Accept` does not alter the request body; (3) JSON syntax/content may be invalid; (4) usually 406; (5) variant selection must be clear, test broad `Accept` cases, and consider `Vary: Accept`.

## 11. References

- HTTP Semantics (RFC 9110): https://www.rfc-editor.org/rfc/rfc9110
- Spring Framework — Mapping Requests (`consumes`/`produces`): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework — Content Types/Content Negotiation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/content-negotiation.html
- MDN — HTTP Content Negotiation: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Content_negotiation
