# Creating GET, POST, PUT, and Custom Methods with Proper Headers Using Java HttpClient

Java 11 and later provide a standard HTTP client in the `java.net.http` module, which continues to be supported on **Java 17+**. With `HttpClient` and `HttpRequest.Builder`, applications can create `GET`, `POST`, `PUT`, `DELETE`, or custom HTTP method requests such as `PATCH`, send requests synchronously/asynchronously, and read the response status, headers, and body.

The most error-prone part is not calling the right method name, but **accurately coordinating the HTTP method, URI, request body, and headers** according to the server-side API contract. For example: `Content-Type` describes **the body being sent**, `Accept` describes **the response type desired**; `BodyPublishers.ofString(...)` does not automatically convert a Java object to JSON and does not automatically select `Content-Type: application/json`; `Content-Length` is usually managed automatically by HttpClient/body publisher. A request that is valid on the Java side can still be semantically wrong in HTTP or rejected by the server.

This lesson progresses from creating requests to configuring headers, handling responses and practical errors, and then provides a **standalone Java 17+ program running on loopback**, using an in-memory HTTP server to verify all four methods **GET, POST, PUT, PATCH** without needing to call an Internet API.

## 1. Components and Workflow

A basic HTTP exchange:

~~~text
          HttpClient (reused across multiple requests)
                         |
HttpRequest.Builder     |     HttpResponse.BodyHandler<T>
  URI                   |              |
  method                |              v
  headers               |        decode/consume
  BodyPublisher         |        response body
        |                |
        +--- build() ----+
                 |
          Immutable HttpRequest
                 |
         client.send(request, handler)
                  or
         client.sendAsync(request, handler)
                 |
                 v
       HTTP request over TCP/TLS
                 |
             HTTP server
                 |
                 v
       status + headers + body
                 |
                 v
           HttpResponse<T>
~~~

Related classes:

| Component | Role |
| --- | --- |
| `java.net.http.HttpClient` | Shared client: connections, proxy, HTTP version, redirects, connect timeout, TLS… |
| `HttpRequest` | Built request: URI, method, headers, body publisher, request timeout |
| `HttpRequest.Builder` | Mutable builder to configure the request; `build()` returns an immutable request |
| `HttpRequest.BodyPublishers` | Outgoing byte sources: `ofString`, `ofByteArray`, `ofFile`, `noBody`… |
| `HttpResponse.BodyHandlers` | How to receive the response: `ofString`, `ofByteArray`, `ofFile`, `discarding`… |
| `HttpResponse<T>` | Result information: `statusCode()`, `headers()`, `body()`, `uri()`, `version()` |

**Builder vs. request:** `HttpRequest.Builder` is not guaranteed to be safe for concurrent modification by multiple threads; `HttpRequest` after `build()` is immutable. A single `HttpClient` can be shared across multiple requests; there is no need to instantiate a new client for each GET/POST.

Creating an HTTP client:

~~~java
// Java 17+ fragment; requires importing java.net.http.*, java.time.Duration.
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .followRedirects(HttpClient.Redirect.NEVER)
        .version(HttpClient.Version.HTTP_1_1)
        .build();
~~~

HTTP/1.1 is chosen here to connect to the demo server. In real services, HTTP/2 can be used, checking `response.version()` to know the actual version; the version configuration is a **preference**, not necessarily the final version in every environment. `followRedirects(NEVER)` is useful when you need to control redirects and prevent accidentally forwarding credentials to another host.

## 2. GET — Reading Resources, Typically Without a Request Body

GET is typically used to read a resource list/detail. `HttpRequest.Builder.GET()` sets the GET method; if you do not specify any method, the builder also defaults to GET. In common REST APIs, GET does not use a body, and query parameters belong to the URI.

~~~java
// Java 17+ fragment; requires importing URI, HttpRequest, Duration.
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/items?limit=10"))
        .timeout(Duration.ofSeconds(5))
        .header("Accept", "application/json")
        .GET()
        .build();
~~~

**Header explanation:** `Accept: application/json` tells the server that the client expects a **JSON response**. This is not a declaration that the request body is JSON. For a GET without a body, you typically **do not need to set `Content-Type`**. If the server only supports another type, it may return an error (for example, 406 Not Acceptable), or respond according to the API policy.

### Encoding Query Parameters Properly

Do not concatenate user-input strings directly into a URI, especially when there are spaces, `&`, `=`, Vietnamese diacritics, or reserved characters:

~~~java
// Fragment using form-encoding convention for query parameter VALUES.
String keyword = "Cà phê & sách";
String encoded = java.net.URLEncoder.encode(
        keyword, java.nio.charset.StandardCharsets.UTF_8);
URI uri = URI.create("https://example.com/items?q=" + encoded);
~~~

`URLEncoder` is an encoder for `application/x-www-form-urlencoded`, suitable for **query values when the server decodes according to this convention**: spaces may be written as `+`. It is **not a general-purpose encoder to turn any URL into a valid URL**, and should not be used to encode an entire path/URI. For path segments containing dynamic data, use a URI-building/percent-encoding approach specific to paths and clarify the contract with the server.

GET is defined as **safe** in HTTP semantics: the client requests to view data, without intentionally creating side effects. Therefore, APIs should not use GET to update business state, process payments, or delete data. GET is also an **idempotent** method in HTTP semantics; this does not mean every read returns the exact same content because the resource may change.

## 3. POST — Sending Content, Typically Creating Resources or Triggering Actions

POST can create an item, submit a business command, log in, or perform an operation without default idempotent semantics. `POST(...)` accepts a **BodyPublisher**. If sending JSON, you must construct valid JSON and declare the appropriate media type.

~~~java
// Java 17+ fragment; JSON here is constructed manually for illustration only.
String json = "{\"name\":\"An\"}";

HttpRequest post = HttpRequest.newBuilder(
        URI.create("https://example.com/items"))
        .timeout(Duration.ofSeconds(5))
        .header("Accept", "application/json")
        .header("Content-Type", "application/json; charset=UTF-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                json, java.nio.charset.StandardCharsets.UTF_8))
        .build();
~~~

Points to distinguish:

- `BodyPublishers.ofString(json, UTF_8)` converts a **string that is already JSON** into UTF-8 bytes. It **does not** turn a Java POJO into JSON. When dealing with complex Java objects, use a suitable JSON serialization library to handle escaping, nulls, arrays, dates, etc.
- `Content-Type: application/json; charset=UTF-8` describes the body being sent. For JSON, UTF-8 is a widely compatible encoding; some APIs require exact `application/json` without parameters, so **follow the server contract**.
- `Accept: application/json` describes the response body you want to receive; completely different from `Content-Type`.
- `POST` is normally **not assumed to be idempotent**. When a request times out, the server may have already processed it successfully before the client sees the result. Automatic retries can create duplicate data; an idempotency key or deduplication protocol is needed where appropriate.

HTTP POST can return `201 Created` along with `Location` when creating a resource, though this depends on the API. Do not assume POST only succeeds with status 200; read the specific documentation.

### Not Every POST Is JSON

If the server requires a form body:

~~~java
// Java 17+ fragment.
String form = "name=" + java.net.URLEncoder.encode(
        "Nguyễn An", java.nio.charset.StandardCharsets.UTF_8)
        + "&active=true";

HttpRequest formPost = HttpRequest.newBuilder(
        URI.create("https://example.com/forms"))
        .header("Content-Type",
                "application/x-www-form-urlencoded; charset=UTF-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                form, java.nio.charset.StandardCharsets.UTF_8))
        .build();
~~~

If the server requires raw bytes or a file, use `BodyPublishers.ofByteArray(...)` or `ofFile(path)` with the exact media type. **Multipart/form-data** requires a multi-part structure and a boundary matching the body; do not just set a `multipart/form-data` header and send a JSON string. With `ofInputStream(...)`/stream-based publishers, you must consider the ability to re-read the body on retry, redirect, or authentication; do not assume a stream source is replayable.

## 4. PUT — Sending a Representation to Create/Replace Resource State

PUT typically targets a **specific resource URI** and asks the server to create or replace the representation at that URI (depending on policy). In common REST design, PUT usually sends **the entire representation to be replaced**, unlike PATCH which only applies a partial change.

~~~java
// Java 17+ fragment.
String fullItem = "{\"id\":7,\"name\":\"Binh\",\"active\":true}";

HttpRequest put = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/items/7"))
        .header("Accept", "application/json")
        .header("Content-Type", "application/json; charset=UTF-8")
        .PUT(HttpRequest.BodyPublishers.ofString(
                fullItem, java.nio.charset.StandardCharsets.UTF_8))
        .build();
~~~

PUT is **idempotent in HTTP semantics**: resending the same request with the same URI/body is intended to have the same target effect on the resource as sending it once (ignoring side effects such as logs/timestamps described separately). That **does not mean** the network guarantees exactly one request reaches the server, that the response is always identical, or that automatic retries are always safe for every custom API.

If multiple clients update the same item concurrently, use a **conditional request** when supported by the server, such as `If-Match: "etag-value"`, to prevent overwriting someone else's changes:

~~~java
// Fragment: ETag must be obtained from a previous response of the same resource.
// Do not fabricate an ETag; the value received from the server may have quotation marks.
HttpRequest conditionalPut = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/items/7"))
        .header("If-Match", "\"revision-7\"")
        .header("Content-Type", "application/json")
        .PUT(HttpRequest.BodyPublishers.ofString(
                "{\"id\":7,\"name\":\"Binh\"}"))
        .build();
~~~

This is only a header configuration pattern: `revision-7` is not a real ETag verified by a server. A server supporting preconditions may return `412 Precondition Failed` if the representation no longer matches. An endpoint that does not support ETag/If-Match may behave differently; check the contract.

## 5. Custom Methods: PATCH, OPTIONS, REPORT, and Other Verbs

`HttpRequest.Builder` has convenience methods `GET()`, `POST(publisher)`, `PUT(publisher)`, and `DELETE()`. When an API requires another method (most commonly **PATCH**), use:

~~~java
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/items/7"))
        .header("Content-Type", "application/merge-patch+json")
        .header("Accept", "application/json")
        .method("PATCH", HttpRequest.BodyPublishers.ofString(
                "{\"name\":\"Chi\"}",
                java.nio.charset.StandardCharsets.UTF_8))
        .build();
~~~

`method(String method, BodyPublisher bodyPublisher)` sets **both the method name and the body source**. The method name must be a valid HTTP token; Java does not invent semantics for the method, and **the server/proxy must support it**. For instance, a gateway might reject PATCH or REPORT even though Java builds a valid request.

Use `BodyPublishers.noBody()` when the method has no request body:

~~~java
// Fragment — the server must support OPTIONS at this endpoint.
HttpRequest options = HttpRequest.newBuilder(
        URI.create("https://example.com/items"))
        .method("OPTIONS", HttpRequest.BodyPublishers.noBody())
        .build();
~~~

`PATCH` differs from PUT in meaning: it applies **a document describing changes**, rather than necessarily replacing the entire representation. `application/merge-patch+json` is for **JSON Merge Patch** (RFC 7396); `application/json-patch+json` is for **JSON Patch** (RFC 6902), which has a different structure. You cannot swap the two media types while keeping the same body if the server distinguishes them per the standard. PATCH is **not automatically idempotent**; retry behavior depends on the patch document and API contract.

For a normal bodyless DELETE, use `DELETE()`. If a specialized API genuinely requires DELETE with a body, you can use `method("DELETE", BodyPublishers.ofString(...))`, but do not treat that as a universal rule: many servers/proxies do not support a body as expected.

### Table for Choosing a Method by Intent

| Method | Common Intent | Outgoing Body | HTTP Properties to Remember |
| --- | --- | --- | --- |
| `GET` | Read resource/list | Usually none | Safe, semantically idempotent |
| `POST` | Create, send command, process | Usually present | Not idempotent by default |
| `PUT` | Replace state at a specific URI | Usually present | Semantically idempotent |
| `PATCH` | Partial update per patch format | Usually present | Not idempotent by default |
| `DELETE` | Request resource deletion | Usually none | Semantically idempotent, response may vary |
| `OPTIONS` | Query communication capabilities/methods | Usually none | Server must support; response may contain `Allow` |
| Custom method | Agreed upon by server and client | Depends on contract | No universal semantics unless specified |

**Do not use "custom methods" to bypass permission checks.** The API server must still authenticate, authorize by method/resource, and validate the payload against the schema. Browser CORS is also a separate topic: Java HttpClient **is not a browser** and is not blocked by browser CORS policies like JavaScript running from a website.

## 6. Sending Proper Headers: Content-Type, Accept, Authorization, and Other Fields

An HTTP header consists of a **name** and a **value**; header names are case-insensitive semantically. In Java:

~~~java
// Fragment — builder calls.
HttpRequest.Builder builder = HttpRequest.newBuilder()
        .header("Accept", "application/json")
        .header("Content-Type", "application/json")
        .header("X-Request-ID", "req-42");
~~~

### Most Important Headers

| Header | Who Uses It and What For? | Notes |
| --- | --- | --- |
| `Accept` | Request: describes the response media type the client desires | Choose based on the **response** the API returns, e.g., `application/json` or `text/plain` |
| `Content-Type` | Request: describes **the outgoing body** | Match JSON/form/binary/patch, charset if required by contract; bodyless GET usually does not need it |
| `Authorization` | Request: credentials such as `Bearer <token>` per API mechanism | Do not hard-code, do not log/reveal tokens, do not send to unknown hosts |
| `If-Match` | Request: conditional update based on ETag | Helps prevent lost updates if the server supports preconditions |
| `If-None-Match` | Request: conditional retrieval/cache with ETag | Server may return `304 Not Modified` with no body |
| `Accept-Language` | Request: preferred response language | Does not guarantee the server has translations |
| `User-Agent` | Request: identifies the client when permitted | Optional per server; not proof of authentication |
| `X-Request-ID` / `traceparent` | Correlation/tracing per inter-system contract | Does not exist automatically; generate safe IDs and log for correlation |
| `Content-Length` | Number of request body bytes on the wire | Usually calculated by HttpClient/BodyPublisher, **do not set manually** |
| `Host`, `Connection`, HTTP/2 pseudo-headers | Transport/protocol headers and metadata | Let HttpClient manage them; may be on the restricted list |
| `Content-Encoding` | How the body is content-encoded, e.g., gzip | Only set when the body is **actually** encoded that way; do not confuse with charset |
| `Accept-Encoding` | Indicates response encodings the client accepts | Only advertise when an appropriate decompression handler/logic is present; per contract/client |

**Especially:** `Content-Type` is not the format **the client wants to receive**; `Accept` is not the format **the client is sending**. You can send JSON while requesting `text/plain` in response: this is completely valid if the server provides a text response. The test example below uses that exact pair of headers.

### Avoiding Invalid/Restricted Headers

Some headers are managed or restricted by HttpClient for protocol/security reasons. The `HttpRequest.Builder.header/setHeader` documentation notes that implementations may throw `IllegalArgumentException` for **invalid or restricted names/values**; `Content-Length` is an example explicitly mentioned in Javadoc.

Do not try to set `Content-Length` manually using `json.length()`: that is the number of **UTF-16 characters of the String**, not necessarily the number of UTF-8 bytes. BodyPublisher manages byte count/publishing; for stream bodies of unknown length, framing may differ. Setting an incorrect `Content-Length` manually can cause the server to read too little/too much body or encounter a protocol error.

Do not pass CR/LF or unvalidated user header data into header names/values. Header splitting/injection and invalid newlines pose risks; the builder performs syntax checks, but code must still control business values (e.g., not allowing users to overwrite Authorization).

### How Do `header()`, `headers()`, and `setHeader()` Differ?

- `header(name, value)`: **adds** a value for the header. If the same name already exists, the values are kept as multiple values.
- `headers(name1, value1, name2, value2, ...)`: adds in **name-value pairs**; the number of strings must be even and names/values must be valid.
- `setHeader(name, value)`: **replaces all previous values** of the header with the same name in the builder with a new single value.

~~~java
HttpRequest.Builder b = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/items"))
        .header("X-Trace", "temporary")
        .setHeader("X-Trace", "request-42")
        .GET();

HttpRequest request = b.build();
// Request declares X-Trace: request-42, no longer temporary.
~~~

For single-valued headers such as `Authorization` or `Content-Type`, use `setHeader` when updating so you do not accidentally create multiple values violating the contract. Some headers are validly multi-valued (such as `Accept` in many representations), but you should not append duplicates unintentionally. `HttpRequest.headers().firstValue("X-Trace")` can inspect the header configuration **set in the request**; headers automatically generated by HttpClient on the wire may not appear as user-declared values.

**Important with redirects:** if a request contains Authorization or an API key, do not automatically forward credentials to another host when the server redirects. `followRedirects(NEVER)` is an easy-to-audit choice; if enabling redirects, you must understand cross-origin rules, scheme downgrades, and trust boundaries.

## 7. Authentication and Secret Configuration

You can set a Bearer header when the API requires it:

~~~java
// Java 17+ fragment: only for trusted, configured HTTPS hosts.
String token = System.getenv("API_TOKEN");
if (token == null || token.isBlank()) {
    throw new IllegalStateException("Missing API_TOKEN");
}

HttpRequest secure = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/private/items"))
        .setHeader("Authorization", "Bearer " + token)
        .header("Accept", "application/json")
        .GET()
        .build();
~~~

This is a **fragment**, not a program runnable against the illustrative endpoint: it requires a real account/API, a valid URI, and an issued token. Do not write tokens into source code, console output, HTTP request logs, or shared files. Only send tokens over HTTPS to verified hosts and consider proxy/redirect forwarding. APIs may also use cookies, Basic authentication, OAuth, HMAC signing, or mTLS per contract; do not assume every API uses Bearer.

Note that `Authorization` in the example is a **request header**, not a header proving the HTTP server authenticated successfully. You must check the status and response. With HTTP 401, the server may return `WWW-Authenticate`; with 403, the account may be authenticated but lack permissions. Do not attribute every 401/403 to network errors or retry indefinitely.

## 8. Runnable Example: GET, POST, PUT, PATCH and Header Inspection on Java 17+

This section creates a **loopback HTTP server** using the JDK `jdk.httpserver` module to **only echo requests**. It does not store data in a database and does not actually create/modify items; response codes are chosen to illustrate how status codes are received. As a result, the output **does not depend on external APIs, DNS, credentials, or the Internet**. The client is forced to use HTTP/1.1 for compatibility with the sample server.

Single file **`HttpMethodsDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class HttpMethodsDemo {

    private static final Charset UTF8 = StandardCharsets.UTF_8;

    private static String show(String value) {
        return value == null ? "-" : value;
    }

    // Local endpoint only echoes; does not modify application data.
    private static void handle(HttpExchange ex) throws IOException {
        String requestBody;
        try (InputStream in = ex.getRequestBody()) {
            byte[] bytes = in.readAllBytes();
            requestBody = bytes.length == 0
                    ? "-" : new String(bytes, UTF8);
        }

        String result = ex.getRequestMethod()
                + " " + ex.getRequestURI()
                + " | Accept="
                + show(ex.getRequestHeaders().getFirst("Accept"))
                + " | Content-Type="
                + show(ex.getRequestHeaders().getFirst("Content-Type"))
                + " | X-Trace="
                + show(ex.getRequestHeaders().getFirst("X-Trace"))
                + " | body=" + requestBody;

        byte[] response = result.getBytes(UTF8);
        ex.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");

        // Illustrates HTTP status only, does not create a real record.
        int status = "POST".equals(ex.getRequestMethod())
                ? 201 : 200;
        ex.sendResponseHeaders(status, response.length);

        try (OutputStream out = ex.getResponseBody()) {
            out.write(response);
        }
    }

    private static void send(
            HttpClient client, HttpRequest request) throws Exception {
        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString(UTF8));

        System.out.println(
                request.method() + " -> "
                + response.statusCode()
                + " | " + response.body());
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});

        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        server.createContext("/items", HttpMethodsDemo::handle);
        server.start();

        try {
            String root = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            // GET: requests text response only, no body.
            // setHeader replaces the previously set X-Trace value.
            HttpRequest get = HttpRequest.newBuilder(
                    URI.create(root + "/items?limit=2"))
                    .timeout(Duration.ofSeconds(5))
                    .header("Accept", "text/plain")
                    .header("X-Trace", "temporary")
                    .setHeader("X-Trace", "get-1")
                    .GET()
                    .build();

            // POST: sends JSON request, receives text/plain response.
            HttpRequest post = HttpRequest.newBuilder(
                    URI.create(root + "/items"))
                    .timeout(Duration.ofSeconds(5))
                    .header("Accept", "text/plain")
                    .header("Content-Type",
                            "application/json; charset=UTF-8")
                    .header("X-Trace", "post-1")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            "{\"name\":\"An\"}", UTF8))
                    .build();

            // PUT: representation sent to a specific item URI.
            HttpRequest put = HttpRequest.newBuilder(
                    URI.create(root + "/items/7"))
                    .timeout(Duration.ofSeconds(5))
                    .header("Accept", "text/plain")
                    .header("Content-Type",
                            "application/json; charset=UTF-8")
                    .header("X-Trace", "put-1")
                    .PUT(HttpRequest.BodyPublishers.ofString(
                            "{\"name\":\"Binh\"}", UTF8))
                    .build();

            // PATCH: method() with body format for Merge Patch.
            HttpRequest patch = HttpRequest.newBuilder(
                    URI.create(root + "/items/7"))
                    .timeout(Duration.ofSeconds(5))
                    .header("Accept", "text/plain")
                    .header("Content-Type",
                            "application/merge-patch+json")
                    .header("X-Trace", "patch-1")
                    .method("PATCH",
                            HttpRequest.BodyPublishers.ofString(
                                    "{\"name\":\"Chi\"}", UTF8))
                    .build();

            send(client, get);
            send(client, post);
            send(client, put);
            send(client, patch);
        } finally {
            server.stop(0);
        }
    }
}
~~~

**Compile and run on JDK 17+:**

~~~bash
javac HttpMethodsDemo.java
java HttpMethodsDemo
~~~

On some explicit module-path configurations, you may need to add `--add-modules jdk.httpserver` when compiling/running because the demo uses the `com.sun.net.httpserver` API. With a standard JDK running on the classpath/unnamed module, this module is usually resolved automatically. **Do not** use dependencies or HTTP servers outside the JDK.

**Output verified on JDK 24 via JShell, with localhost HTTP/1.1:**

~~~text
GET -> 200 | GET /items?limit=2 | Accept=text/plain | Content-Type=- | X-Trace=get-1 | body=-
POST -> 201 | POST /items | Accept=text/plain | Content-Type=application/json; charset=UTF-8 | X-Trace=post-1 | body={"name":"An"}
PUT -> 200 | PUT /items/7 | Accept=text/plain | Content-Type=application/json; charset=UTF-8 | X-Trace=put-1 | body={"name":"Binh"}
PATCH -> 200 | PATCH /items/7 | Accept=text/plain | Content-Type=application/merge-patch+json | X-Trace=patch-1 | body={"name":"Chi"}
~~~

**Meaning of each line:**

1. **GET:** the endpoint receives `GET /items?limit=2`. Body `-` means **no body**; no request `Content-Type`. `X-Trace=get-1` proves `setHeader` replaced `temporary`. The query is preserved in the request-target.
2. **POST:** the publisher sends UTF-8 JSON `{"name":"An"}`, and the server receives `Content-Type: application/json; charset=UTF-8` and `Accept: text/plain`. Status 201 is the choice of the **demo server**, not a guarantee that a real item was created.
3. **PUT:** sends a JSON body to `/items/7`, status 200. The server only echoes rather than proving PUT replaced a representation.
4. **PATCH:** `method("PATCH", ...)` constructs the proper method and body, along with the `application/merge-patch+json` header to the local server. The demo does not actually apply JSON Merge Patch; it only verifies building/sending the HTTP request properly.

**Why doesn't the code need an external network?** `HttpServer` listens on `127.0.0.1` and port `0`; the OS picks an available port. The client retrieves the actual port via `server.getAddress().getPort()`, without hard-coding a port. `server.stop(0)` stops the server in `finally`, even if a request throws an error. In environments where opening loopback sockets is prohibited, the test may fail due to policy even though the Java code is valid.

**Safety limits of the demo:** the server reads the entire body into RAM and echoes the input directly. It should only be run with small, trusted requests on loopback. A production server must limit request size, validate schema/method, perform authentication, authorization, content negotiation, avoid reflecting sensitive data, and manage HTTP error responses. Do not open a public port or use this echo handler as an Internet service.

## 9. Reading Responses Properly: Not Just Calling `body()`

API:

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));

int status = response.statusCode();
String body = response.body();
String contentType = response.headers()
        .firstValue("Content-Type").orElse("-");
System.out.println(status + " " + contentType);
~~~

**You must check the status**, because `send()` normally **does not throw an exception just for HTTP 4xx or 5xx**: these are still valid HTTP responses. `BodyHandlers.ofString(...)` converts the body to a String; it does not parse JSON, nor does it automatically reject error statuses.

| Status Group | Common Meaning | Application Handling |
| --- | --- | --- |
| 2xx | Success at the HTTP layer | Check schema/body/side effects appropriate for the endpoint |
| 3xx | Redirection/cache/conditional | Inspect `Location`, `ETag`, `304`; do not blindly follow redirects with tokens |
| 400 | Invalid request | Check URI, method, body, validation, and Content-Type |
| 401 / 403 | Unauthorized / Forbidden | Check authentication/permission mechanisms, do not log secrets |
| 404 | Resource/route not found | Check URI, path, resource id |
| 405 | Method Not Allowed | Server does not support the method at the endpoint; check the `Allow` header if present |
| 406 / 415 | Accept cannot be satisfied / Content-Type unsupported | Check media type/contract |
| 409 / 412 | Conflict / precondition no longer true | Must reconcile version/ETag, do not overwrite blindly |
| 429 | Rate limited | Backoff based on policy and `Retry-After` if present |
| 5xx | Server-side error or gateway error | Retry only when appropriate for idempotency and retry budget |

**A resource-creating POST** usually returns 201 and may contain a `Location` header pointing to the new resource URI. A successful DELETE may return 204 No Content, so do not force every response to contain JSON. For 204/304, do not attempt to parse an empty body.

The `HttpResponse.BodyHandlers.ofString(Charset)` documentation uses the charset you specify. Parameterless `ofString()` uses the charset from the response `Content-Type` if present and supported, otherwise UTF-8. For APIs with a fixed encoding, choose an explicit charset for easier control. With JSON, a **String response is not a JSON object**; you still need to parse/validate the response before using it.

Example of checking status per contract:

~~~java
// Helper fragment inside a Java 17+ class.
static String requireSuccess(HttpResponse<String> response)
        throws java.io.IOException {
    int status = response.statusCode();
    if (status < 200 || status >= 300) {
        throw new java.io.IOException(
                "HTTP status " + status
                + ", response length="
                + response.body().length());
    }
    return response.body();
}
~~~

The example only reports the status and response length rather than logging the entire error body — the body may contain sensitive data. Real systems need more detailed API error classification and limits on the body size read into memory.

## 10. Timeouts, Exceptions, and Retries by Method

Distinguish between:

- `HttpClient.Builder.connectTimeout(Duration)`: limits the time to **establish a new connection** when needed. If the client reuses an existing connection, there is not necessarily a new connect step.
- `HttpRequest.Builder.timeout(Duration)`: configures the timeout of the **request/response exchange** per the API; if the response is not received in time, the request may throw `HttpTimeoutException`.
- `client.send(...)`: synchronous, blocks the calling thread until the response is received per `BodyHandler` or it fails.
- `client.sendAsync(...)`: returns `CompletableFuture<HttpResponse<T>>`; completes normally or exceptionally, without automatically making server operations idempotent.
- A timeout **does not prove** the server did not receive/execute the request. Especially with POST, the situation "server committed, client did not see the reply" is very important.

Catching errors with synchronous send:

~~~java
// Java 17+ fragment; request and client have already been created.
try {
    HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString(
                    StandardCharsets.UTF_8));
    System.out.println("HTTP status " + response.statusCode());
} catch (java.net.http.HttpTimeoutException timeout) {
    // Request timed out; server may still have processed it.
} catch (java.io.IOException networkOrTlsError) {
    // DNS/connection/reset/TLS/framing/transport... needs classification.
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    // Yield control and handle cleanup appropriately.
}
~~~

When using `sendAsync`:

~~~java
// Fragment: returns future immediately, does not require waiting with join().
java.util.concurrent.CompletableFuture<HttpResponse<String>> pending =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

pending.thenAccept(response -> {
    System.out.println("HTTP status " + response.statusCode());
}).exceptionally(error -> {
    // Log cause in a controlled manner, do not log credentials.
    return null;
});
~~~

If code calls `pending.join()` immediately on the current thread, you block that thread again, only changing the waiting syntax. Exceptions from asynchronous stages may be wrapped in `CompletionException`; inspect the cause. When canceling the `CompletableFuture` of an HTTP exchange, Java attempts to cancel to free resources but does not guarantee when cancellation takes effect: the server may have already received and processed the request.

### Retries: Different by Method

| Method | Can It Be Retried Immediately on Timeout? |
| --- | --- |
| `GET` | Usually safe to retry with limits/throttling, but watch out for changing data and side effects from improperly implemented APIs |
| `PUT` | By idempotent semantics, retrying **may** be reasonable; check preconditions, versions, and custom business logic |
| `POST` | **Do not retry blindly**: may create 2 orders/charges if the first request succeeded |
| `PATCH` | Depends on the patch format/operation; not idempotent by default |
| `DELETE` | Idempotent regarding intended state, but a retry may receive 404 after a successful deletion; handle per contract |

A good retry policy has a bounded number of attempts, backoff + jitter, an overall deadline, considers 429/503 along with `Retry-After`, and detects unrecoverable errors. If business logic requires an exactly-once effect, there must be server-side mechanisms such as idempotency keys, conditional updates, or deduplication; HTTP method/idempotency is only part of the problem.

## 11. Headers and Sensitive Data: Security and Proper Scope

Setting headers properly also relates to security, not just protocol:

1. **Do not store Bearer/API keys in source code or logs.** Use secure configuration, a secret manager, or environment variables in internal demos. If logs need to be shared, redact `Authorization`, `Cookie`, and token values in queries.
2. **HTTPS in real environments.** The demo uses loopback HTTP because it wants to test the API without depending on certificates; do not send Bearer tokens over plain-text HTTP outside controlled environments.
3. **Do not accept arbitrary URIs from input to forward requests with credentials.** Validate scheme, host allowlist, port, redirects, and paths to prevent SSRF/exfiltration.
4. **Do not assume 2xx means the body is the right type.** A server may return an HTML/error page even if the client sent Accept JSON; check Content-Type and parse/validate the response.
5. **Do not allow Host, Content-Length, Connection, or HTTP/2 pseudo-headers via user data.** Those belong to the transport layer managed by HttpClient; they may be rejected or cause protocol mismatches.
6. **Do not mix up headers and body.** With `application/json` the body must be valid JSON; with a form body it must be properly encoded; with multipart it needs boundaries and part formatting.
7. **Do not abuse `Expect: 100-continue`.** If you need to optimize sending large bodies, use `expectContinue(true)` when supported by the server/proxy and understand the interim response round; do not conclude the server processed the request solely from status 100.
8. **Do not share mutable request builders across threads.** Create a builder per request or coordinate safely; only the built `HttpRequest` is immutable.

Proxy, load balancer, CDN, or API gateway environments may also enforce header size limits, strip hop-by-hop headers, block custom methods, and rewrite URIs. When 405/415 occurs, you must check both the upstream endpoint and the API gateway, not just client code.

## 12. Common Mistakes When Building GET/POST/PUT/PATCH

**Mistake A — POSTing JSON but the server says the body format is invalid.**  
Check whether the body is valid JSON, whether the serializer properly escaped Unicode characters and quotation marks, whether `Content-Type` is exact `application/json` per contract, and whether the byte charset matches. `BodyPublishers.ofString` does not parse or validate JSON.

**Mistake B — Setting only Accept and forgetting Content-Type.**  
`Accept` describes the **response**, not how to teach the server to parse the request. For POST/PUT/PATCH with a body, declare the media type of the request body when required by the API.

**Mistake C — GET sending an unnecessary body.**  
GET should normally carry queries in the URI; servers/proxies/caches do not agree on the meaning of a GET request with a body. Do not use `method("GET", ofString(...))` as a default workaround just to avoid query encoding.

**Mistake D — Encountering 415 Unsupported Media Type.**  
The server does not support the request `Content-Type` or the payload format being sent. Distinguish between Merge Patch and JSON Patch bodies; check the exact media type of the endpoint rather than changing it arbitrarily.

**Mistake E — Encountering 406 Not Acceptable.**  
The client requested a response media type not provided by the server. If you only want `text/plain`, set `Accept: text/plain`; if the server only returns JSON, set the right media type and use a JSON parser.

**Mistake F — Encountering 405 Method Not Allowed when using PATCH/custom methods.**  
Java can send the method, but the server/resource/gateway does not support it. Check `Allow` when present, the API contract, and proxy configuration. Do not secretly switch PATCH to POST if the API does not allow it.

**Mistake G — Unintended duplicate headers.**  
`header` adds a value; calling it twice with `Authorization` or `Content-Type` can create an ambiguous request. If only one value is needed, use `setHeader` and inspect `request.headers()` before sending.

**Mistake H — Manually setting Content-Length and getting an exception.**  
HttpClient manages length based on BodyPublisher and may forbid the header name. Additionally, `String.length()` is not the UTF-8 byte count. Remove that header; pass the proper body publisher.

**Mistake I — GET query has Vietnamese characters/`&` and the request is split into two parameters.**  
Encode the query **value** per server standards, do not concatenate raw input. Do not use `URLEncoder` to encode an entire URI or path segment.

**Mistake J — `client.send` returns a 401/500 response without throwing IOException.**  
Error HTTP status codes are still valid HTTP responses. Check `response.statusCode()`, headers, and body schema, then handle according to business logic.

**Mistake K — POST is sent twice due to retrying after a timeout.**  
A timeout can occur after the server has already written to the DB. You need an idempotency key, correlation ID, deduplication, or request status query instead of retrying immediately.

**Mistake L — PUT overwrites someone else's changes.**  
Use ETag/`If-Match` when supported by the backend, and handle 412/409; do not assume PUT is safe against concurrent races just because it is idempotent.

**Mistake M — Response has garbled characters due to encoding.**  
Check the Content-Type charset and byte data; `BodyHandlers.ofString(UTF_8)` assumes UTF-8. If the API returns a different charset, choose the corresponding handler/decoder per contract.

**Mistake N — Creating one HttpClient per request and experiencing slowness.**  
HttpClient is designed to reuse connections and resources. You can use one client per shared trust/proxy/timeout configuration; create a new one only when there is an isolation or configuration reason.

**Mistake O — Testing HTTP requests against a public API and not getting the same response as the demo.**  
The loopback server here **only echoes** and assigns statuses arbitrarily, with no persistence/authorization. A real API has its own URIs, permissions, schemas, and status codes; do not treat the demo output as a promise about every server.

## 13. Systematic Diagnostic Guide

When an HTTP call fails, check in order:

~~~text
1. URL/URI
   - Is the scheme http or https?
   - Are host/path/query correct? Are query values encoded?
   - Correct resource id and environment (dev/staging/prod)?

2. Method
   - Does GET / POST / PUT / PATCH match the contract?
   - Is a custom method supported by the server/gateway?
   - Does the body fit the method and endpoint?

3. Headers
   - Is Accept the expected response media type?
   - Is Content-Type the actual OUTGOING BODY media type?
   - Is Authorization/token correct and not leaked?
   - Are there unintended duplicate header() calls?
   - Are you trying to set a restricted header?

4. Transport
   - TLS certificate/hostname, DNS, proxy, firewall?
   - Connect timeout vs. request timeout?
   - Any redirects to another host/scheme?

5. Response
   - HTTP status?
   - Response Content-Type?
   - Location / Allow / ETag / Retry-After / WWW-Authenticate?
   - What structure does the error body have? Is it safe to log?

6. Retry / Side Effects
   - Could the server have processed the request before timeout?
   - Is the method idempotent per contract?
   - Is there an idempotency key or If-Match?
~~~

Safely log fields such as correlation ID, method, route template, status, latency, response Content-Type, retry count, and error category. **Do not** log raw Authorization, cookies, passwords, or entire personal bodies. To compare the request actually received by the server, an echo endpoint like the demo is a good learning tool; do not leave an uncontrolled echo endpoint on a public network.

## 14. Practice Exercises and Answers

**Question 1:** A client sends a `POST` body `{"name":"An"}` and wants to receive JSON; which headers are needed?  
**Answer:** Typically use `Content-Type: application/json` for the outgoing body and `Accept: application/json` for the response body. Charset and specific requirements follow the API contract; BodyPublisher sends bytes and does not set Content-Type automatically.

**Question 2:** A client calls `GET()` without a body. Is `Content-Type: application/json` needed?  
**Answer:** Usually not. Use `Accept: application/json` if you want a JSON response; put queries in the URI.

**Question 3:** The builder calls `header("X-Trace","a")` then `header("X-Trace","b")`; are both kept?  
**Answer:** Yes, the builder adds multiple values. If you want to replace with a single value, use `setHeader("X-Trace","b")`.

**Question 4:** Why not assign `Content-Length=json.length()` manually?  
**Answer:** The value is the number of bytes on the wire, not Java characters; it is also managed by BodyPublisher/HttpClient and may be a restricted header.

**Question 5:** Java 17 wants to send a PATCH body with JSON Merge Patch; which API should be used?  
**Answer:** `.method("PATCH", BodyPublishers.ofString(patchJson, UTF_8))` with `Content-Type: application/merge-patch+json` when required by the server. Verify PATCH support on the backend.

**Question 6:** POST returns `201 Created` and `client.send` does not throw an exception. Does a real item already exist?  
**Answer:** You only know the server returned 201. Check the API documentation, response body/Location, and business state. The local demo assigns 201 but does not store any item.

**Question 7:** `client.send` returns `415 Unsupported Media Type`. What should be fixed first?  
**Answer:** Check the request `Content-Type` and the format of the bytes actually sent; distinguish between JSON, form, Merge Patch, and JSON Patch.

**Question 8:** Does resending PUT with the same URI/body twice always create 2 resources?  
**Answer:** Per HTTP semantics, PUT is idempotent in intended effect, though custom servers may have other side effects/conditions. Do not deduce that every request is executed exactly once; check the contract and concurrency control.

**Question 9:** Does HTTP 401 cause `client.send` to automatically throw `IOException`?  
**Answer:** Not solely because of status 401. Usually you still receive an `HttpResponse` and must check `statusCode()`, headers, and body.

**Question 10:** `GET /items?q=Cà phê & sách` is concatenated directly from input; what is the risk?  
**Answer:** Invalid URI or `&` being parsed as a new query parameter. Encode query values according to the server's convention; do not encode the entire URI at once.

**Question 11:** After a POST timeout, should you retry immediately on every `IOException`?  
**Answer:** No. The server may have already processed creating the order or payment. You need an idempotency key/dedup, a bounded retry policy, and to check whether the error is recoverable.

**Question 12:** Is Java HttpClient restricted by browser CORS like JavaScript in a web page?  
**Answer:** Not by the same browser security mechanism. However, the server can still enforce permissions, origin checks, or its own policies.

**Question 13:** What should be used to send a request with a body from a large file?  
**Answer:** `BodyPublishers.ofFile(path)` if permitted by the contract, and `Content-Type` matching the format; consider replayable sources, timeouts, limits, and avoid loading large files into a String.

**Question 14:** Is it contradictory for the demo to send `Accept: text/plain` but `Content-Type: application/json` for POST?  
**Answer:** No. The request body is JSON; the desired response is text. The echo server in the demo returns `text/plain`, so this pair of headers is valid.

## 15. Official Documentation

- Java SE 17 — `HttpClient`, `send()`, `sendAsync()`, client configuration: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Java SE 17 — `HttpRequest`, immutable request and builder: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html
- Java SE 17 — `HttpRequest.Builder`: `GET/POST/PUT/DELETE/method/header/setHeader/timeout`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html
- Java SE 17 — `HttpRequest.BodyPublishers`, string, file, byte[], noBody: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html
- Java SE 17 — `HttpResponse`, status, headers, body, version: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html
- Java SE 17 — `HttpResponse.BodyHandlers`, `ofString/byteArray/ofFile`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html
- Java SE 17 — `HttpTimeoutException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html
- Java SE 17 — `com.sun.net.httpserver.HttpServer` for loopback testing: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- HTTP Semantics (IETF RFC 9110) — methods, safe/idempotent, status codes: https://www.rfc-editor.org/rfc/rfc9110
- HTTP PATCH (IETF RFC 5789): https://www.rfc-editor.org/rfc/rfc5789
- JSON Merge Patch (IETF RFC 7396): https://www.rfc-editor.org/rfc/rfc7396
