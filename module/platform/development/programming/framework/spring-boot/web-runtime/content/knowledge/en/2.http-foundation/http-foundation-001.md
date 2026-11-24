# HTTP Request and Response Structure: Methods, URIs, Headers, and Body

## 1. How Does HTTP Exchange Information?

HTTP (Hypertext Transfer Protocol) is an application-layer protocol that allows clients (browsers, mobile apps, `curl`, Java programs, etc.) to communicate with a server via a **request → response** model. The client sends a request containing the action it wants to perform and the necessary information; the server processes it and returns a status, metadata, and optionally content. In Spring Boot Web, HTTP is the boundary between clients and the endpoints exposed by the application.

A typical exchange:

~~~text
Client                                   Server (Spring Boot)
  | -- HTTP request ---------------------> |
  |    method + URI + headers + body      | receive, route, process
  | <---------------------- HTTP response |
       status + headers + body
~~~

HTTP is considered **stateless** at the protocol level: each request does not inherently carry state from a previous session. An application can maintain login state or a shopping cart using cookies, tokens, sessions, or a database, but it must have an explicit mechanism to pass or look up that state.

The text-based examples below illustrate **HTTP/1.1**. HTTP/2 and HTTP/3 still have corresponding concepts of method, URI, status, headers, and content, but they transmit them using binary frames (and pseudo-headers) rather than sending a plain-text start line like HTTP/1.1.

## 2. What Parts Make Up an HTTP Request?

In HTTP/1.1, the common logical shape is:

~~~http
METHOD /path?query HTTP/1.1
Host: example.test
Header-Name: header value

optional request body
~~~

Lines on the wire are separated by CRLF (`\r\n`), and **an empty line** separates the headers section from the body (if present). Four components to distinguish:

| Component | Which question does it answer? | Example |
| --- | --- | --- |
| **Method** | What does the client want to do with the resource? | `GET`, `POST`, `PUT` |
| **URI / request target** | Which resource is the request targeting? | `/api/books/42?lang=vi` |
| **Headers** | What are the metadata and communication instructions? | `Accept`, `Content-Type`, `Authorization` |
| **Body / content** | What content data is attached? | JSON, form data, file, or binary bytes |

The HTTP/1.1 start line consists of the method, request target, and protocol version. For example, `GET /api/books/42 HTTP/1.1`. This line does not contain a status code: the status appears in the **response**.

### HTTP Methods

| Method | Typical purpose | Safe? | Idempotent? |
| --- | --- | --- | --- |
| `GET` | Retrieve a resource representation; no intentional server state change | Yes | Yes |
| `HEAD` | Retrieve metadata similar to GET, but the response has no body | Yes | Yes |
| `POST` | Send data for the server to process, often creating a resource/action | No | Not guaranteed |
| `PUT` | Create/replace the resource state at the target URI with the sent representation | No | Yes |
| `PATCH` | Request applying a partial modification | No | Not guaranteed |
| `DELETE` | Request removing the association/state of the resource at the target URI | No | Yes |
| `OPTIONS` | Query communication options; commonly seen in CORS preflight | Yes | Yes |

**Safe** means the requested action does not semantically intend to alter application state; the server may still record logs or metrics. **Idempotent** means executing the same request multiple times has the same **intended effect on server state** as executing it once—it does not mean every call always returns the same status or the same body. For example, the first DELETE may return 204 and the next 404, yet the method remains idempotent; PUT with the same representation must not automatically create an additional record each time.

Do not map CRUD mechanically: POST can trigger processing without creating a resource; PATCH *can* be designed to be idempotent, though idempotency is not guaranteed by the method itself. With GET, avoid attaching business state-changing actions such as payments or deleting records. A body in GET has no universally defined semantics and may be rejected by servers or intermediaries; typically, use the URI/query to express queries.

### URI, URL, and Request Target

Example URL:

~~~text
https://api.example.test:8443/api/books/42?lang=vi&page=2#reviews
|https| |--- authority ----| |-- path -----| |--- query -----| fragment
~~~

- **Scheme** (`https`) indicates how to access the resource; HTTPS is HTTP transmitted over a TLS-protected connection.
- **Authority** consists of the host (and optionally a port). Host + port identifies the network destination; default ports are typically 443 for HTTPS and 80 for HTTP.
- **Path** (`/api/books/42`) locates the resource within the application. In Spring MVC, the pattern `/api/books/{id}` can bind to the variable `id=42`.
- **Query** (after `?`) provides parameter pairs such as `lang=vi&page=2`; `&` separates parameters. Query keys may repeat, values may be omitted, and order can sometimes be meaningful depending on the API contract.
- **Fragment** (`#reviews`) is used by the client to navigate within a document; **it is not sent to the server in a normal HTTP request target**.

In HTTP/1.1 to an origin server, the request line typically contains only the path and query: `GET /api/books/42?lang=vi HTTP/1.1`; the host is specified via `Host: api.example.test:8443`. A forward proxy may receive a different request-target form (such as absolute-form). In HTTP/2/3, pseudo-headers such as `:method`, `:scheme`, `:authority`, and `:path` convey equivalent information.

**Path and query are not the same as body.** Path identifies the resource, query filters/adjusts how it is retrieved, while body carries a representation or data to be processed. Special characters in a URI must be properly percent-encoded (for example, a space is `%20` in a URI); never concatenate strings directly from unencoded input. URIs can appear in browser history, proxy logs, and monitoring systems, so do not put passwords, access tokens, or secret data in the query string.

## 3. HTTP Headers: Metadata and Processing Conditions

Headers are typically `Name: value` lines. **Header names are case-insensitive**; value semantics depend on the specific header. Do not equate headers with body data.

| Header | Common direction | Meaning |
| --- | --- | --- |
| `Host` | HTTP/1.1 request | Target host; required in an HTTP/1.1 request |
| `Accept` | Request | Media types the client accepts in the response, e.g. `application/json` |
| `Content-Type` | Request/response with content | Media type of the **body being sent**, e.g. `application/json` or `text/plain; charset=UTF-8` |
| `Authorization` | Request | Authentication credentials, e.g. `Bearer ...`; do not write real tokens to logs |
| `Cookie` | Request | Cookies sent by the client; may contain a session identifier |
| `Set-Cookie` | Response | Server instructs the client to store/update a cookie along with protection attributes |
| `Location` | Response | URI of a newly created resource or redirect target, depending on status |
| `Cache-Control` | Both | Caching policy, e.g. `no-store` or `max-age=60` |
| `ETag` / `If-None-Match` | Response / request | Validator and condition for efficiently re-fetching a representation |
| `Content-Length` | Both when applicable | Number of content **bytes** in the corresponding wire framing, not the count of Unicode characters |
| `Origin` | Request | Client origin; commonly appears in browser/CORS communication |
| `Access-Control-Allow-Origin` | Response | Declares which origin is permitted to access the response under CORS |

Distinguish two commonly confused headers:

~~~http
POST /api/books HTTP/1.1
Host: api.example.test
Content-Type: application/json
Accept: application/json
~~~

`Content-Type: application/json` states that **the client is sending JSON**; `Accept: application/json` states that **the client wants to receive JSON**. If the server does not support the request content type, it may return **415 Unsupported Media Type**; if it cannot produce a representation matching `Accept`, it may return **406 Not Acceptable**. The exact error choice depends on the API contract and framework.

Do not assume every header sent by a client is trustworthy, including `X-Forwarded-*` (trusted proxies must be configured properly). An `Authorization` header does not authenticate a user on its own if the application has not configured security. CORS is a browser policy governing cross-origin response sharing; **it does not replace API authorization**.

## 4. Request Body: The Payload Being Sent

The body is an **optional** sequence of bytes. Depending on the API, it may contain:

- JSON (`application/json`) for object/array structures, e.g. `{"name":"Lan","active":true}`;
- form data (`application/x-www-form-urlencoded`) such as `name=Lan&active=true`;
- multipart (`multipart/form-data; boundary=...`) to combine fields and files;
- plain text (`text/plain`), XML, images, or binary data (`application/octet-stream`).

Determining what format the body has must rely on `Content-Type` and the endpoint contract; do not guess JSON just because a string looks like JSON. `Content-Length` is counted in bytes after encoding: a single Vietnamese character can occupy multiple bytes in UTF-8. HTTP/1.1 can also use `Transfer-Encoding: chunked` framing instead of a known `Content-Length`; HTTP/2/3 have their own framing. Headers, body, and message termination must be valid so the server knows the data boundaries. Do not send conflicting framing directives simultaneously.

Example of an **HTTP/1.1 POST request with exact body length** (all JSON characters here are ASCII):

~~~http
POST /api/books HTTP/1.1
Host: api.example.test
Content-Type: application/json
Accept: application/json
Content-Length: 28

{"name":"Lan","active":true}
~~~

The empty line before `{` delimits the headers and the body. The body consists of 28 ASCII bytes; the server must read the exact byte length before converting the JSON into a Java object according to its configuration.

## 5. What Parts Make Up an HTTP Response?

In HTTP/1.1, a response has a **status line**, headers, an empty line, and an optional body depending on the case:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/books/42
Content-Length: 36

{"id":42,"name":"Lan","active":true}
~~~

Assuming the POST in the previous section created book id 42, **201 Created** indicates the resource was created; `Location` points to the new resource and the body returns the JSON representation. `Content-Length` here is 36 ASCII bytes. The reason phrase `Created` is only descriptive in HTTP/1.1; applications rely on the **numeric status code**. HTTP/2/3 convey the status via the `:status` pseudo-header.

### Status Code Groups

| Group | Meaning | Practical examples |
| --- | --- | --- |
| **1xx** | Interim informational | `100 Continue` |
| **2xx** | Successful processing | `200 OK`, `201 Created`, `202 Accepted`, `204 No Content` |
| **3xx** | Redirection / cache condition | `301`, `302`, `304 Not Modified`, `307`, `308` |
| **4xx** | Request-side issue | `400`, `401`, `403`, `404`, `405`, `409`, `415`, `422`, `429` |
| **5xx** | Server or gateway failure to process | `500`, `502`, `503`, `504` |

Useful distinctions:

- **200** usually includes a result representation; **201** is used when creating a resource, typically with `Location`; **202** means accepted for processing, though processing is not yet complete; **204** succeeded with **no body**.
- **304 Not Modified** sends no new representation body; it allows the client to continue using a valid cached copy.
- **400** invalid request; **401** missing or failed authentication; **403** understood but permission denied; **404** resource/representation not found per API contract; **405** method not supported for that resource.
- **409** conflicts with current resource state; **415** unsupported input media type; **422** syntactically/media-type valid content that cannot be processed semantically; **429** request rate limit exceeded.
- **500** server-side processing error; **502/503/504** typically relate to gateways/upstream services or availability. Do not return 200 for every error outcome just because the JSON body has an `error` field.

Not every response has a body. Responses to HEAD, 1xx, 204, and 304 have rules forbidding content; 304 may contain certain cache-updating headers. For redirects, clients inspect the status together with `Location`. A status code alone does not convey full meaning without the endpoint contract and headers.

## 6. Reading a Complete Exchange End-to-End

Suppose the client sends:

~~~http
GET /api/books/42?verbose=true HTTP/1.1
Host: localhost:8080
Accept: application/json
X-Request-Id: abc-123

~~~

Reading in order: `GET` is the retrieval action; `/api/books/42` selects resource id 42; `verbose=true` is the query; `Host` identifies the server; `Accept` requests JSON; `X-Request-Id` is a custom header per the application contract. This request has no body.

The server might return:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"id":42,"name":"Lan","active":true}
~~~

The illustrative response above **intentionally omits framing headers** because it is presented at the logical level; in actual transmission, the server and HTTP version must provide valid framing. `200` is the status, `Content-Type` describes the returned JSON, `Cache-Control` instructs not to cache, and the body is the data. Based on the request/response pair, you can distinguish routing errors (method/path), content negotiation (headers), body parsing, and business logic.

## 7. Connection to Spring Boot Web (Servlet / Spring MVC)

For a Spring Boot application using `spring-boot-starter-web`, the embedded HTTP server receives the request and Spring MVC processes it through `DispatcherServlet`, selecting a handler based on mappings, parameter binding, and content conversion. This is **how the framework implements HTTP**, not a separate HTTP format.

| HTTP Part | How to declare/read in Spring MVC |
| --- | --- |
| Method and path | `@GetMapping`, `@PostMapping`, `@RequestMapping` |
| Path variable | `@PathVariable` |
| Query parameter | `@RequestParam` |
| Request header | `@RequestHeader` |
| JSON body → Java | `@RequestBody` + message converter (typically Jackson) |
| Response body Java → JSON | `@RestController` or `@ResponseBody` |
| Status and response headers | `ResponseEntity`, `@ResponseStatus` |
| Input/output media type | `consumes`, `produces` |

Runnable example in a **Spring Boot 3.x, Java 17+ project** that already has the `spring-boot-starter-web` dependency. Create `src/main/java/demo/http/HttpDemoApplication.java` with the exact package and public class name:

~~~java
package demo.http;

import java.net.URI;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
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

@SpringBootApplication
public class HttpDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpDemoApplication.class, args);
    }
}

@RestController
@RequestMapping("/api/books")
class BookController {
    private final Map<Long, BookView> books = new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong(100);

    BookController() {
        books.put(42L, new BookView(42L, "Lan", true));
    }

    @GetMapping(path = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<BookView> find(
            @PathVariable long id,
            @RequestParam(defaultValue = "false") boolean verbose,
            @RequestHeader(name = "X-Debug", defaultValue = "false") boolean debug) {

        BookView book = books.get(id);
        if (book == null) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok()
                .header("X-Debug-Enabled", Boolean.toString(verbose && debug))
                .body(book);
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<BookView> create(@RequestBody NewBook input) {
        if (input.name() == null || input.name().isBlank()) {
            return ResponseEntity.badRequest().build();
        }

        long id = nextId.getAndIncrement();
        BookView created = new BookView(id, input.name(), input.active());
        books.put(id, created);

        return ResponseEntity.created(URI.create("/api/books/" + id))
                .body(created);
    }

    public record NewBook(String name, boolean active) {}
    public record BookView(long id, String name, boolean active) {}
}
~~~

Explaining the correspondence:

1. `@GetMapping("/{id}")` handles **GET /api/books/{id}**; `@PathVariable` extracts id from the path, `@RequestParam` reads `?verbose=true`; `@RequestHeader` reads `X-Debug` if present (defaulting to false).
2. `ResponseEntity.ok()` builds a response with status 200 and header `X-Debug-Enabled`, then serializes JSON via a converter. If the id is not in the map, it returns 404.
3. `@PostMapping(consumes = "application/json")` restricts the accepted request body type. `@RequestBody NewBook` instructs Spring to convert JSON into the Java record; malformed JSON may result in 400, while an unsuitable media type may result in 415.
4. `ResponseEntity.created(...)` sets status 201 and header `Location: /api/books/{id}`; the body is the `BookView` record serialized as JSON.
5. The map in the example only stores data in memory to observe requests/responses: restarting loses the data; a real application needs persistence, validation, security, and error handling per the API contract.

In a project with the Gradle wrapper and Spring Boot plugin configured, run `./gradlew bootRun` from the project directory (Windows PowerShell: `.\gradlew.bat bootRun`). Because it depends on Spring Boot and Jackson, do **not** compile this file standalone with `javac` without the classpath. Test with `curl` in bash/macOS/Linux:

~~~bash
curl -i "http://localhost:8080/api/books/42?verbose=true" \
  -H "Accept: application/json" \
  -H "X-Debug: true"

curl -i -X POST "http://localhost:8080/api/books" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"name":"Mai","active":true}'

curl -i "http://localhost:8080/api/books/999"
~~~

Expected observations: the first GET request returns **200**, body `{"id":42,"name":"Lan","active":true}`, and `X-Debug-Enabled: true`; the first POST since startup returns **201**, `Location: /api/books/100`, and body `{"id":100,"name":"Mai","active":true}`; GET id 999 returns **404**. Header order, timestamps, system headers, and default error body details may vary by version/configuration. Subsequent POST calls increment the id; this is not a guarantee of persistence or a production API.

## 8. How to Troubleshoot When an HTTP API Behaves Incorrectly

Treat the request and response as two separate messages and inspect them sequentially:

1. **Method + path**: does the endpoint match the right `GET/POST/PUT...` and URL? `404` may be a wrong path; `405` is usually a wrong method on a path that has a handler.
2. **Path/query**: are the id, filters, and percent-encoded characters correct? Do not confuse `/books/42` with `/books?id=42` if the API only supports one form.
3. **Headers**: does `Content-Type` match the body, does `Accept` match the expected response, and are auth/session credentials sent validly? Header names are case-insensitive.
4. **Body**: is the JSON syntactically valid with the right field names/data types, charset, and within size limits? Does an empty line separate HTTP/1.1 headers and body?
5. **Status + response headers**: check the status **before** parsing the body; inspect `Location` on 201/redirects, `Content-Type` on JSON, and cache headers when relevant.
6. **Intermediaries**: is a load balancer/reverse proxy rewriting paths, modifying headers, or limiting body size? Only trust forwarded headers when proxy configuration is correct.

Common mistakes: using POST for read operations without understanding semantics; putting sensitive data in the URI; equating `Accept` with `Content-Type`; thinking every request must have a body; assuming idempotent means identical responses; measuring `Content-Length` by character count; trying to read URL fragments on the backend; returning 200 for all errors; ignoring the status code and looking only at the JSON body.

### Self-Check Scenarios

**Scenario A:** `GET /api/orders/7?detail=true`, `Accept: application/json`, no body. Which part selects the resource, which adjusts the representation, and which states the desired response format? → The path selects order 7; the query `detail=true` adjusts how it is retrieved; the `Accept` header requests JSON if supported by the server.

**Scenario B:** The client sends `Content-Type: text/plain` with a JSON string in the body, and the Spring endpoint requires `consumes = application/json`. → Even though the body *looks like* JSON, the server may return **415** because the declared media type does not match.

**Scenario C:** Sending DELETE to the same URI twice: the first returns 204, the second returns 404. → This can still satisfy **idempotency** because the goal of deleting the resource was achieved on the first call; the two status codes do not have to be identical.

**Scenario D:** A `204 No Content` response is returned, yet the client tries to parse a JSON body. → The client is making an invalid assumption; 204 contains no response content, so rely on the status code.

## 9. Key Takeaways

An HTTP exchange has two sides:

- **Request = method + URI + request headers + body (if any).** The method states the action, the URI identifies the target, headers provide metadata/conditions, and the body carries data.
- **Response = status + response headers + body (if any).** The status communicates the protocol-level outcome, headers describe the representation and policies, and the body returns content.
- In Spring Boot Web, annotations map these parts to Java handlers and `ResponseEntity` maps processing outcomes back to responses. Understanding each component accurately helps design consistent endpoints and diagnose errors from network logs more effectively.
