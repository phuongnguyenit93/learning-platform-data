# Request–Response Cycle and HTTP Message Structure

HTTP (Hypertext Transfer Protocol) is the application protocol that browsers, mobile apps, API clients, and servers use to exchange requests and responses. In Spring Web programming, understanding HTTP is essential for reading a request accurately, choosing the right method, returning the right status code, handling headers/bodies, and pinpointing whether an error lies in the client, network, intermediary, or application.

## 1. Learning Objectives and Overview Model

After this lesson, you should be able to:
- Describe a request–response cycle from the moment the client sends a request until it receives the result.
- Break an HTTP/1.1 message down into **start-line, headers, separating blank line, and body (if present)**.
- Distinguish between request-target, method, status code, representation, media type, header, and message body.
- Read an actual HTTP exchange and explain what Spring MVC receives and returns.
- Understand the boundary between HTTP/1.1's text-based syntax and the different encodings of HTTP/2 and HTTP/3.

HTTP follows a model where the client initiates a request and the server sends a corresponding response. A single connection can serve multiple exchanges, so **one request does not mean a new TCP connection**; HTTP/2 and HTTP/3 can also handle multiple concurrent streams. HTTP is generally considered **semantically stateless**: each request is processed using the accompanying information and system-side state, and the protocol does not automatically require the server to remember an application conversation across calls. Cookies, sessions, or tokens are mechanisms used by applications to maintain context.

Example of a book lookup:

~~~text
Client                       Server / Spring Web
  |   GET /books/42             |
  |----------------------------->|
  |                              | Read URI, method, headers
  |                              | Route and process
  |   200 OK + JSON              |
  |<-----------------------------|
  | Display/use data             |
~~~

This diagram illustrates the logical exchange. Along the path, there may be DNS, TLS, proxies, load balancers, and a servlet container; those layers are not components of an HTTP message.

## 2. The Request–Response Cycle Step by Step

1. **Client builds the request:** chooses a method (for example `GET`), target (URI), query, required headers, and a body when appropriate. For instance, the client may send `Accept: application/json` to request a JSON representation supported by the server.
2. **Establish the transport channel:** the client resolves the endpoint, typically via DNS if using a hostname. For common HTTP/1.1 or HTTP/2, the connection uses TCP; HTTPS adds TLS. HTTP/3 runs over QUIC. Connections may be reused.
3. **Transmit the request:** the client sends information according to the negotiated protocol version. A reverse proxy may receive the request and forward it to the application server.
4. **Server receives and processes:** the web server/servlet container receives the request; Spring MVC may run Filters, locate the matching controller, convert data, invoke business logic, and generate a response.
5. **Server sends the response:** the status code indicates the HTTP-level outcome, headers provide metadata, and the body carries data if the response type allows it.
6. **Client interprets the response:** inspects the status and headers, parses the body according to the media type, and decides whether to display data, cache, redirect, re-authenticate, or report an error.

The request–response flow **does not guarantee** that a request always reaches the application or that a response always succeeds: DNS, TLS, timeouts, proxies, or connection resets can cause the exchange to fail before an HTTP status code is ever received.

## 3. Structure of an HTTP/1.1 Message

When examining traditional HTTP/1.1 syntax, a message takes the form:

~~~text
START-LINE\r\n
Header-Name: value\r\n
Another-Header: value\r\n
\r\n
[message body, if present]
~~~

In the template above, `\r\n` denotes the two **CRLF** bytes ending each line. Two consecutive CRLFs form the blank line separating the headers from the body. The square brackets on the body line are purely explanatory, not required bytes in the message. Headers and bodies are not restricted to plain text; the body can be JSON, form data, an image, or binary data. Empty headers mean that immediately after the start-line there is a CRLF ending the header section (though a valid HTTP/1.1 request normally requires a Host header).

**Version caveat:** this is the *HTTP/1.x* representation. HTTP/2 and HTTP/3 preserve most method, status, header, and body semantics, but use binary/frame encoding on the wire instead of a text-based request/status start-line. Therefore, you should not claim that "every HTTP packet contains a `GET /... HTTP/1.1` line". In HTTP/2/3, the equivalent information is represented via pseudo-headers such as `:method`, `:path`, `:scheme`, `:authority`, and responses via `:status`; the body resides in data frames.

### 3.1. Request start-line

An HTTP/1.1 request-line has the form:

~~~text
METHOD SP request-target SP HTTP-version CRLF
~~~

Example:

~~~http
GET /books/42?view=summary HTTP/1.1
Host: api.example.test
Accept: application/json

~~~

- `GET` is the **method**, expressing the intent to retrieve a representation of the resource.
- `/books/42?view=summary` is the **request-target** in origin-form: path `/books/42` plus query string `view=summary`. Fragments such as `#intro` are not sent in the HTTP request-target.
- `HTTP/1.1` is the version in the request-line.
- `Host: api.example.test` specifies the authority/virtual host for the HTTP/1.1 request. The Host header is mandatory in HTTP/1.1 and must match the target URI's authority.
- `Accept: application/json` indicates that the client prefers receiving content in the JSON media type.

The request-target has other forms for certain situations, such as absolute-form when sending through a forward proxy or authority-form for `CONNECT`. Most standard HTTP APIs use origin-form as shown in the example.

Distinguish three easily confused parts:
- **Path** `/books/42` helps route to a resource or endpoint.
- **Query** `?view=summary` passes selection/filter parameters; it is part of the URI, not the body.
- **Body** is the data following the blank line that ends the headers; for example, JSON used to create an order.

### 3.2. Response status-line

An HTTP/1.1 response begins with a status-line:

~~~text
HTTP-version SP status-code SP [reason-phrase] CRLF
~~~

Example of an illustrative response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 15

{"status":"ok"}
~~~

- `HTTP/1.1` is the response version.
- `200` is the machine-interpretable **status code**; `OK` is a human-readable reason phrase and should not be used as the basis for business logic.
- `Content-Type: application/json` describes the media type of the representation in the body.
- `Content-Length: 15` indicates the body is **15 bytes** long, not 15 Vietnamese letters or the character count of JSON in general. The example body is pure ASCII, so it is 15 bytes.
- The blank line marks the end of headers; `{"status":"ok"}` is the body.

HTTP/2/3 do not use HTTP/1.1-style reason phrases. API clients should rely on the status code and the application payload/contract, rather than trying to match strings like `OK` or `Not Found`.

### 3.3. Headers

A header consists of a field name and value, such as `Content-Type: application/json`. Header names are **case-insensitive** semantically; `content-type` and `Content-Type` refer to the same field. HTTP/2 requires field names to be encoded in lowercase in the header block. Values have field-specific syntax and semantics, so you should not automatically merge all headers sharing the same name.

| Header | Common Role |
| --- | --- |
| `Host` | Specifies the host/authority in an HTTP/1.1 request. |
| `Accept` | Response media types the client can accept. |
| `Content-Type` | Media type of the accompanying content (request or response). |
| `Content-Length` | Length of the content in **bytes**, where permitted. |
| `Authorization` | Authentication credentials, such as a `Bearer` token. |
| `Cache-Control` | Directives for caching behavior. |
| `Location` | Target URI communicated, commonly used upon resource creation or redirects. |
| `Set-Cookie` / `Cookie` | Server sets a cookie; client sends cookies on subsequent matching requests. |

**`Accept` is not synonymous with `Content-Type`:** a request with `Content-Type: application/json` means the request body is JSON; `Accept: application/json` means the client wants a JSON response. Both can appear at the same time and serve different roles.

Headers can strongly influence behavior. Do not log `Authorization` values, session cookies, or personal data. Do not concatenate unvalidated user input containing CR/LF directly into headers, as this can create HTTP response splitting vulnerabilities.

### 3.4. Message body and determining boundaries

A body is not always present:
- `GET` normally only retrieves data and does not send a body; you should not design APIs that rely on a GET body because general semantics are undefined and intermediaries may not support it.
- `POST` or `PUT` commonly send JSON/form/file payloads in the body, though the method itself does not force a body to be present.
- `204 No Content` and `304 Not Modified` responses must not contain message content; responses to `HEAD` also carry no content body even though certain headers describe the corresponding GET response.
- A network error can cause an incomplete body to be received even after the status-line and headers arrive.

**HTTP/1.1 body framing** must follow protocol framing rules rather than guessing by "reading until the second blank line". Depending on the case, framing uses `Content-Length`, `Transfer-Encoding: chunked`, or connection close; some message types are not permitted to have a body. `chunked` is an HTTP/1.1 transfer encoding mechanism, not a type of JSON or application body. Do not specify both `Content-Length` and `Transfer-Encoding` when manually constructing messages: framing ambiguity risks request smuggling. Let the HTTP library/server handle framing.

With UTF-8, the byte count can exceed the character count: `"Lan"` in ASCII JSON has a byte count equal to its character count, whereas `"Chào"` contains a multi-byte character. If working with raw sockets directly, length must be calculated on the encoded bytes; in normal Spring MVC usage, the framework and web server handle this.

## 4. Complete Example: Resource Creation Request

This is an *illustrative HTTP/1.1 exchange*, assuming both sides send the exact headers and body shown below.

Request:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
Accept: application/json
Content-Length: 14

{"name":"Lan"}
~~~

Response:

~~~http
HTTP/1.1 201 Created
Location: /api/orders/42
Content-Type: application/json
Content-Length: 15

{"status":"ok"}
~~~

Step-by-step explanation:
1. `POST /api/orders` asks the server to process the data and create an order according to the API design.
2. `Content-Type` tells the server how to parse the body `{"name":"Lan"}`. The sample content is 14 ASCII bytes.
3. The server completes resource creation and returns `201 Created`; this is the appropriate status for successful creation.
4. `Location: /api/orders/42` tells the client the URI of the newly created resource (here a relative URI).
5. The response body `{"status":"ok"}` is 15 bytes long and has the JSON media type.

The strings above are **fixed sample exchanges for reading the protocol** and do not claim Spring automatically produces this exact JSON/URI/headers. In a real project, status codes, serialization, headers, and error-handling policies depend on the controller, framework, server configuration, and proxies.

## 5. Methods, Status Codes, and Response Semantics

Distinguish **message syntax** from **method/status semantics**. Two requests with similar structure but different methods convey different intents.

| Method | Common Meaning | Semantic Characteristics |
| --- | --- | --- |
| `GET` | Retrieve a representation | Safe and idempotent by HTTP definition; should not cause client-requested state changes. |
| `HEAD` | Retrieve metadata corresponding to GET, without response body | Safe, idempotent. |
| `POST` | Submit data for processing by the target resource | Typically not idempotent. |
| `PUT` | Create/replace target resource state at the URI using the submitted representation | Idempotent under standard semantics. |
| `PATCH` | Apply partial modifications | Not inherently idempotent; depends on the specific patch. |
| `DELETE` | Request removal of the resource association/state at the target | Idempotent under HTTP semantics, even though responses across calls may differ. |
| `OPTIONS` | Query communication options | Safe, idempotent. |

**Safe** refers to semantics that do not request intentional state changes (ancillary logging/metrics may still occur). **Idempotent** means the *intended server-side effect* of one or multiple identical requests is the same; it does not mean byte-for-byte identical responses or that the network guarantees no duplicate delivery.

Status code groups:
- **1xx – Informational:** interim responses, for example `100 Continue`.
- **2xx – Success:** `200 OK` with success content depending on the method; `201 Created` upon creation; `204 No Content` on success with no content.
- **3xx – Redirection:** the client needs to use navigation/cache information, such as `301`, `302`, `304`; 304 serves to reuse a cached representation rather than delivering a new body.
- **4xx – Client error:** `400 Bad Request` for an invalid request; `401 Unauthorized` related to authentication requirements; `403 Forbidden` when access is denied; `404 Not Found` when the representation/resource is not found in context.
- **5xx – Server error:** `500 Internal Server Error` for server-side processing failures; `502 Bad Gateway` typically involving a gateway/proxy receiving an invalid upstream response; `503 Service Unavailable` indicating temporary unavailability.

A 2xx status only confirms handling **according to the protocol and API contract**. For instance, an endpoint can return 200 with JSON `{"success":false}`; that is an application design choice, and it does not make 200 automatically mean "all business logic succeeded". Always examine both the HTTP status and the API response schema.

## 6. How Does HTTP Enter Spring Web?

The example below is an **illustrative Spring MVC controller**, using Java 17+, Spring Framework 6/Spring Boot 3, the `spring-webmvc` module, and a JSON converter such as Jackson. Place it in `GreetingController.java` inside the source set of a Spring application configured for component scanning. This snippet is *not a standalone Java program runnable with plain `javac`*, as it requires dependencies and a running web application.

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
public class GreetingController {

    @GetMapping("/{name}")
    public ResponseEntity<GreetingResponse> greet(@PathVariable String name) {
        return ResponseEntity.ok(new GreetingResponse("Hello, " + name + "!"));
    }

    public record GreetingResponse(String message) {}
}
~~~

When the Spring MVC application is running on port 8080, try:

~~~bash
curl --http1.1 -i -H "Accept: application/json" http://localhost:8080/api/greetings/Lan
~~~

In PowerShell, if `curl` is an alias for `Invoke-WebRequest`, invoke `curl.exe` to use curl CLI syntax.

Expected JSON body example (header formatting and Unicode character display may vary by environment):

~~~json
{"message":"Hello, Lan!"}
~~~

Explanation of the flow inside Spring MVC:

1. The client sends `GET /api/greetings/Lan`. The servlet container receives the HTTP request and creates request/response objects for the servlet layer.
2. Configured `Filter` instances can inspect the request or response (e.g., logging, security), and then execution reaches `DispatcherServlet`.
3. `DispatcherServlet` asks `HandlerMapping` to find a handler matching `GET` and the path; `HandlerAdapter` executes the controller method.
4. `@PathVariable` binds the `Lan` path segment to the Java variable `name`. `ResponseEntity.ok(...)` sets the HTTP status to 200.
5. Because the controller is `@RestController`, the `GreetingResponse` value is treated as the response body; an appropriate `HttpMessageConverter` (typically the Jackson JSON converter) serializes the record into JSON.
6. The servlet container sends the status, headers, and body to the client. Spring/the server may add other headers, use chunked transfer, or another valid framing mechanism; do not assume `Content-Length` if the actual response does not include it.

In the **request body** direction, an API like `@PostMapping` with `@RequestBody` typically uses a converter to deserialize the JSON request into a Java object. If the media type is unsupported, the request is malformed, or validation fails, Spring may return a 4xx error depending on error-handling configuration. A valid JSON body does not guarantee valid business data.

This is the **Spring MVC (Servlet)** pipeline. With Spring WebFlux, the dispatching layer and processing model are reactive (for example `DispatcherHandler`); do not apply the `DispatcherServlet` diagram directly to WebFlux.

## 7. Observing Requests and Responses Yourself When Debugging

Use `curl -i` to inspect the **status-line and response headers along with the body** in the output. Add `-v` to view connection details and client-side request/response information; `--http1.1` forces HTTP/1.1 for syntax experiments. In browser DevTools, the Network tab lets you inspect URL, method, status, headers, payload, and timing; the tool may display decoded UI views rather than the exact raw bytes transmitted over the wire.

Checklist order when debugging errors:
1. **No status code?** Check DNS, connectivity, TLS, timeouts, proxies, and server availability before blaming the controller.
2. **Got a 4xx?** Check method, path/query, `Content-Type`, `Accept`, authentication, authorization, JSON body, size limits, and the API contract.
3. **Got a 5xx?** Cross-check server and upstream logs/tracing; avoid exposing stack traces or credentials in public responses.
4. **Right status but client fails to parse?** Check `Content-Type`, charset/encoding, empty body (especially 204/HEAD), JSON shape, and actual received data.
5. **Only breaks through a proxy?** Check path/host rewriting, forwarding headers, header/body size limits, timeouts, and HTTP framing consistency.

An HTTP status belongs to an actual response to a request. **A timeout is not automatically an HTTP 408**: 408 is a status a server may return under specific conditions; if the connection drops or times out on the client without a response, the client only sees a transport error.

## 8. Misconceptions to Avoid

| Misconception | Accurate Understanding |
| --- | --- |
| “HTTP is just JSON APIs.” | HTTP carries many media types; the body may be absent or binary data. |
| “Every request has a body.” | No; body presence and semantics depend on message type and method/status. |
| “The query string is the body.” | The query belongs to the request-target/URI; the body comes after the headers. |
| “Content-Length counts characters.” | It counts bytes; UTF-8 has multi-byte characters. |
| “HTTPS means methods/headers/bodies are different.” | HTTPS secures HTTP in transit; HTTP semantics remain corresponding, though the transport layer or version may differ. |
| “HTTP/2 on the wire also has a 200 OK status-line.” | HTTP/2 uses frames and `:status`; start-line is HTTP/1.x syntax. |
| “200 always means business logic completed successfully.” | Both the API contract and the response body must be understood. |
| “Idempotent PUT/DELETE means no side effects.” | Idempotency describes the intended effect when repeated; logging, auditing, or responses can still change. |
| “The backend always receives the exact request-line sent by the client.” | Proxies can alter the path, host, forwarding headers, and protocol version. |

## 9. Self-Check Exercises

**Exercise 1.** Consider the request: `GET /products?sort=price HTTP/1.1`, with `Host: shop.example.test` and `Accept: application/json`. Identify the method, path, query, two headers, and whether a body is required.

**Exercise 2.** A client sends UTF-8 JSON containing Vietnamese diacritics but uses `String.length()` as `Content-Length`. What is the risk?

**Exercise 3.** The server returns `HTTP/1.1 204 No Content`. Should the client attempt to parse JSON from the body?

**Exercise 4.** A controller `@GetMapping("/api/greetings/{name}")` returns `ResponseEntity.ok(...)`. Which parts determine path mapping, status, and JSON serialization?

**Answers and Explanations**

1. The method is `GET`; the path is `/products`; the query is `sort=price`; the headers are `Host` and `Accept`; GET does not require a body and APIs should not rely on a GET body.
2. `String.length()` in Java counts UTF-16 code units; `Content-Length` counts bytes in HTTP/1.1 content. With UTF-8, these numbers can diverge, breaking framing and leading to communication/security errors; let the HTTP library calculate byte length.
3. No. A 204 response has no content; the client should handle the empty body based on the status.
4. `@GetMapping`/`HandlerMapping` determines the route and method; `ResponseEntity.ok` sets status 200; `@RestController` together with the appropriate `HttpMessageConverter` determines serialization of the response body to JSON.

## 10. Takeaways When Building Spring Web APIs

First define the **resource and HTTP behavior** (URI/method/status). Then place data properly into **path, query, headers, or body**, declare the format via `Content-Type`, and handle content negotiation when needed. When returning a response, ensure the status reflects the processing outcome, the body conforms to the status, and protocol/framing headers are left to the HTTP library. With this model, you can explain a request and response both at the raw HTTP/1.1 level and inside a Spring MVC controller without confusing the responsibilities of each layer.

**Standards for deeper reference:** RFC 9110 (HTTP Semantics), RFC 9112 (HTTP/1.1 message syntax and framing), RFC 9113 (HTTP/2), and RFC 9114 (HTTP/3).