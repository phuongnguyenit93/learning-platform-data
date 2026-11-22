# Reading method, URI, headers, and request body

## 1. HttpExchange: the entry point of a request in the JDK HTTP server

Java 17's **jdk.httpserver** module provides **HttpServer, HttpContext, HttpHandler, HttpExchange**, and **Headers** in the **com.sun.net.httpserver** package. For a server running HTTP/1.1, when a request arrives, the server selects the matching HttpContext and invokes the handler according to the interface:

~~~java
// Snippet: an HttpContext has been registered.
void handle(HttpExchange exchange) throws IOException {
    String method = exchange.getRequestMethod();
    URI uri = exchange.getRequestURI();
    Headers requestHeaders = exchange.getRequestHeaders();
    InputStream requestBody = exchange.getRequestBody();
    // Inspect the request, build the response, then close the exchange.
}
~~~

**HttpExchange** encapsulates a single request and its corresponding response. It should not be treated as a reusable session object across multiple requests.

Overall flow:

~~~text
Client sends HTTP request
       |
       v
HttpServer listens on socket and parses HTTP framing
       |
       v
Selects HttpContext by path prefix
       |
       v
HttpHandler.handle(exchange)
       |
       +-- exchange.getRequestMethod()   -> GET/POST/...
       +-- exchange.getRequestURI()      -> URI path, query...
       +-- exchange.getRequestHeaders()  -> Headers (read-only)
       +-- exchange.getRequestBody()     -> InputStream bytes
       |
       v
Validate method, path, query, header, body size, charset
       |
       +-- responseHeaders.set(...)
       +-- sendResponseHeaders(status, byteLength)
       +-- getResponseBody().write(bytes)
       |
       v
Close response stream and HttpExchange
~~~

The key point of this lesson is that **request metadata is distinct from body bytes**: the method is not in the query, the URI is not automatically JSON, the Content-Type header only describes the content rather than parsing it automatically, and the InputStream does not automatically convert into a String or Java object.

### An illustrative HTTP request

~~~http
POST /inspect?name=Lan+Anh HTTP/1.1
Host: 127.0.0.1:12345
X-Trace-Id: p-1
Content-Type: text/plain; charset=UTF-8
Content-Length: 15

Xin chào Java!
~~~

The handler will see method **POST**, raw query **name=Lan+Anh**, Content-Type specifying UTF-8 text/plain, and **15 UTF-8 bytes** in the request body. Because Vietnamese characters take more than one UTF-8 byte, **byte count is not equivalent to String.length()**.

**Scope of JDK HttpServer:** suitable for learning, testing, and controlled-scope endpoints; it is not a full production framework providing JSON validation, database pooling, authentication, CSRF, CORS, uploads, DoS protection, TLS reverse proxy, and rate limiting.

## 2. APIs and responsibilities

| API | Responsibility | What to avoid |
| --- | --- | --- |
| **HttpServer.create(address, backlog)** | Creates the server; can bind loopback and port 0 for tests | Do not accidentally bind a test service to a public network |
| **HttpServer.createContext(path, handler)** | Registers a context with prefix-based path matching | Do not assume this is exact routing |
| **HttpServer.setExecutor(executor)** | Chooses the executor to run request callbacks | Do not run unbounded blocking work in a small pool |
| **HttpHandler.handle(exchange)** | Parses the request and sends the response | Must clean up the exchange even on error |
| **HttpExchange.getRequestMethod()** | Returns the method String | Do not blindly treat every method as GET |
| **HttpExchange.getRequestURI()** | Returns java.net.URI | Do not naively split the URL string when percent-encoding is present |
| **HttpExchange.getRequestHeaders()** | Returns read-only Headers | Do not modify request headers with set(...) |
| **HttpExchange.getRequestBody()** | Returns the request payload InputStream | Do not read unboundedly into RAM |
| **HttpExchange.getResponseHeaders()** | Mutable map for adding response headers | Set before sendResponseHeaders |
| **HttpExchange.sendResponseHeaders(...)** | Sends status and defines response body framing | Distinguish length >0, 0, and -1 |
| **HttpExchange.getResponseBody()** | Response OutputStream | Write the exact byte count and close the stream |
| **HttpExchange.close()** | Ends request/response streams | Do not skip cleanup |

**HttpsServer** is the HTTPS variant, configured with an SSL/TLS policy; HTTPS is not enabled by default when creating a plaintext **HttpServer**. If user authentication is needed, the Authenticator/HttpPrincipal APIs exist but must be actively configured; merely having an Authorization header does not mean the sender has been verified.

## 3. Reading the method properly

~~~java
String method = exchange.getRequestMethod();

if ("GET".equals(method)) {
    // Handle read query.
} else if ("POST".equals(method)) {
    // Verify body and perform business logic.
} else {
    exchange.getResponseHeaders().set("Allow", "GET, POST");
    // Return 405 Method Not Allowed for this route.
}
~~~

HTTP methods are **case-sensitive**. Common methods and contracts:

| Method | Common purpose | Notes |
| --- | --- | --- |
| **GET** | Read a resource | Do not use GET for actions with dangerous side effects; GET content has no guaranteed general semantics |
| **POST** | Submit data to create/process | Validate media type, byte length, data, and permissions |
| **PUT** | Update/replace a resource per contract | Check idempotency and authorization |
| **PATCH** | Partial update | Validate patch representation |
| **DELETE** | Delete a resource | Authorization and CSRF protection depending on the auth mechanism |
| **HEAD** | Headers corresponding to GET, without sending response content | Must ensure no-response-body |
| **OPTIONS** | Route capabilities, can serve CORS preflight | Do not allow arbitrary origins/methods just because OPTIONS is used |

**405 Method Not Allowed** is the appropriate status when the route exists but does not allow a method; the response should include **Allow** listing the route's methods. **501 Not Implemented** has a different meaning: the HTTP method is not supported by the server in general.

**Whether a body is present must not be inferred solely from the method.** A client can send an empty POST, a GET with a body, or a POST using chunked transfer-encoding. If a GET route specifies no body, it can reject a GET body per contract, as shown in the runnable program in section 8.

## 4. Parsing the URI: path, raw path, query, and encoding

~~~java
URI uri = exchange.getRequestURI();
String rawPath = uri.getRawPath();
String path = uri.getPath();
String rawQuery = uri.getRawQuery();
String decodedQuery = uri.getQuery();
~~~

Example request target:

~~~text
/inspect?name=Ada%20Lovelace&tag=red&tag=blue
~~~

**getRawPath()** preserves encodings such as %2F; **getPath()** interprets percent escapes; **getRawQuery()** preserves %xx sequences so the application decides how to decode; **getQuery()** is already percent-decoded by Java URI, though it does not apply all form decoding rules.

### Repeated query parameters

In the string above, **tag** appears twice. Do not use Map<String,String> if you want to preserve both values. One design:

~~~java
Map<String, List<String>> query = parseQuery(uri.getRawQuery());
List<String> names = query.getOrDefault("name", List.of());
List<String> tags = query.getOrDefault("tag", List.of());
~~~

If a required field must have only one value (like name), **reject when names.size()!=1** instead of arbitrarily picking the first or last value. You should also limit raw query length, the number of keys, and the length of each value.

### URLDecoder and the plus sign

**java.net.URLDecoder** is the decoder for **application/x-www-form-urlencoded**. In this format, **+** means a space, and **%2B** is a literal plus sign:

~~~java
String a = URLDecoder.decode(
        "Lan+Anh", StandardCharsets.UTF_8); // "Lan Anh"
String b = URLDecoder.decode(
        "C%2B%2B", StandardCharsets.UTF_8); // "C++"
~~~

**An arbitrary URI query does not inherently imply form-urlencoded**, and URI.getQuery() does not automatically turn + into a space. Only apply **URLDecoder** when the API contract uses form-query semantics. **Do not percent-decode twice:** for example, %252F can be turned into / if code decodes repeatedly, causing path/query confusion.

### HttpContext is longest-prefix routing

According to the **HttpServer** Javadoc, a request selects a context based on the **longest matching literal path prefix**, compared case-sensitively. If you register:

~~~java
server.createContext("/inspect", handler);
~~~

a request to **/inspect-other** can still reach the handler because the **/inspect** prefix matches. If the route only accepts exact **/inspect**, you must check:

~~~java
if (!"/inspect".equals(exchange.getRequestURI().getRawPath())) {
    // Return 404 Not Found.
}
~~~

Avoid turning path prefixes into authorization rules. For path variables and encoded slashes, choose a router and normalization with clear rules; test **/users**, **/users-admin**, **/users/42**, **/Users**, %2F, and double encoding. Do not allow clients to alter data paths via unvalidated ../ sequences.

### Query and body can coexist

A **POST /inspect?name=Lan+Anh** request has name in the URI and a separate body. Do not automatically merge query and body into the same map if key collisions are possible; the contract must define which source is authoritative for each field, especially user ID, role, token, or resource identifier fields.

## 5. Headers: case-insensitive, multi-valued, read-only

~~~java
Headers headers = exchange.getRequestHeaders();
String trace = headers.getFirst("x-trace-id");
String contentType = headers.getFirst("Content-Type");
List<String> tags = headers.get("X-Tag");
~~~

**Headers** is a **Map<String,List<String>>** with **case-insensitive** keys. **X-Trace-Id**, **x-trace-id**, and **X-TRACE-ID** are the same header name under HTTP semantics. If a header is sent multiple times, the list can contain multiple elements.

| Call | Result |
| --- | --- |
| **getFirst("Content-Type")** | First value if present, or null |
| **get("Accept")** | List of values if present |
| **getRequestHeaders()** | Request metadata as a read-only map |
| **getResponseHeaders()** | Mutable response headers map to set before sending |
| **Headers.set(name,value)** | Writes a single value, replacing old values on the response |
| **Headers.add(name,value)** | Appends a value to the response header |

**Do not call set(...) on getRequestHeaders()**: the Javadoc defines it as read-only. To set the response **Content-Type**, call **getResponseHeaders().set(...)**.

### When is getFirst not enough?

For headers related to **authentication, message framing, routing, and request signatures**, multiple duplicate or inconsistent values require an explicit policy. Taking only getFirst and ignoring remaining values can create ambiguity when a reverse proxy and backend interpret them differently. Either inspect the entire list or let the HTTP parser/gateway reject invalid requests.

**Do not naively split every header by comma**: the grammars of Cookie, Set-Cookie, Authorization, Accept, and Cache-Control differ. Only parse according to each header's specific grammar.

### Content-Type, Accept, Content-Length, Transfer-Encoding

- **Content-Type**: media type of the request body, e.g., text/plain; charset=UTF-8 or application/json.
- **Accept**: response format the client wants to receive, not the request Content-Type.
- **Content-Length**: framing/body length information measured in **bytes**, not Java chars.
- **Transfer-Encoding: chunked**: transfers the HTTP/1.1 body in chunks; the handler receives the body payload through InputStream without manually reading chunk markers.
- **Content-Encoding: gzip**: encoding of the representation; if the app supports decompression, it must also cap the **decompressed** size.

**Every request header is peer-supplied data, not proof of safety.** The **X-Trace-Id** header in the example is only accepted if it matches **[A-Za-z0-9-]{1,32}**, to avoid reflecting control characters. It does not replace authentication. For Authorization/Cookie, never log raw tokens/sessions.

### Content-Type must be checked before parsing

If an endpoint only accepts **text/plain; charset=UTF-8**, the server can return **415 Unsupported Media Type** for POST application/json. In the demo, an **exact Content-Type string comparison (case-insensitive)** is used to keep the code concise and tests deterministic. This is a **very narrow lab format**, not a general MIME parser; real services should parse normalized media types/parameters and decide which charsets are supported.

## 6. Request body: an InputStream requiring a byte cap and charset

~~~java
InputStream body = exchange.getRequestBody();
~~~

According to the **HttpExchange** Javadoc, multiple calls to **getRequestBody()** return **the same InputStream**; consumed bytes do not rewind automatically. For example:

~~~java
byte[] one = exchange.getRequestBody().readAllBytes();
byte[] two = exchange.getRequestBody().readAllBytes();
// two is typically 0 bytes because the stream has already been read to EOF.
~~~

The snippet above illustrates stream state, **not a pattern for handling bodies from untrusted clients**: **unbounded readAllBytes()** can cause OOM when a client sends a large payload.

### Practical byte limit

In the example, **MAX_BODY = 32** bytes for testing; the handler reads at most 33 bytes and returns **413** if the limit is exceeded:

~~~java
static byte[] readLimited(InputStream input, int max)
        throws IOException {
    ByteArrayOutputStream out = new ByteArrayOutputStream();
    byte[] block = new byte[16];

    while (out.size() <= max) {
        int allowed = Math.min(
                block.length, max + 1 - out.size());
        int n = input.read(block, 0, allowed);
        if (n == -1) return out.toByteArray();
        if (n == 0) continue;
        out.write(block, 0, n);
    }
    return null; // Body exceeds max.
}
~~~

**Do not trust Content-Length as the only limit**: a request can use chunked encoding and omit Content-Length. You must **count the bytes actually read**. If Content-Length was already validated by a gateway/server and exceeds quota, you can reject early, but you still need a streaming cap and **timeout**.

**A byte cap does not stop slow clients**: a client sending one byte very slowly still holds the handler waiting. For public systems, you need read timeouts, connection limits, concurrency limits, rate limits, and rejection policies at the edge/gateway.

### UTF-8 has multiple bytes per character

The example body **Xin chào Java!** has **15 UTF-8 bytes**. Do not compute Content-Length using String.length() or Unicode code point count. When strict UTF-8 decoding is required, use:

~~~java
String text = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(bytes)).toString();
~~~

If the UTF-8 bytes are invalid, you can return **400 Bad Request**. **new String(bytes, UTF_8)** can substitute invalid data with replacement characters, which is not always appropriate for protocols requiring strict validation. Do not use the host's default charset.

### Body can be chunked

With HTTP/1.1, a client can stream a request body without knowing its length upfront. In the test:

~~~java
HttpRequest.BodyPublishers.ofInputStream(
        () -> new ByteArrayInputStream(
                "Hi".getBytes(StandardCharsets.UTF_8)))
~~~

An HttpClient publisher without a known length can use chunked transfer encoding over HTTP/1.1. **HttpServer already handles the framing**, and getRequestBody() lets the handler read the exact bytes **Hi**. The handler **does not manually parse Transfer-Encoding chunk sizes**, but it must still cap bytes, validate charset, and verify Content-Type just as with a fixed-length body.

### Invalid body cases

| Error | Handling approach |
| --- | --- |
| **Body exceeds quota** | 413, clean up exchange/connection per policy |
| **Unsupported Content-Type** | 415, do not attempt to parse as a supported type |
| **Malformed UTF-8** | 400 per strict contract |
| **Invalid JSON schema** | 400 or appropriate business status; JSON parser must be configured separately |
| **Client disconnects while reading** | IOException, clean up resources, do not send a false success response |
| **Gzip too large after decompression** | Block with a decompression limit, not just compressed length |
| **Ambiguous Content-Length/Transfer-Encoding** | Let the HTTP parser/edge enforce consistent framing rules to prevent request smuggling |

## 7. Sending the response and closing HttpExchange with the proper lifecycle

Standard sequence per the Javadoc:

1. Read **getRequestMethod**, **getRequestURI**, **getRequestHeaders**.
2. Read **getRequestBody** when the contract requires it; process the body with a bounded parser.
3. Set **getResponseHeaders().set(...)** before sending.
4. Call **sendResponseHeaders(status, responseLength)**.
5. Call **getResponseBody()**, write response bytes if any.
6. Close the response OutputStream and **HttpExchange**.

**sendResponseHeaders** has three JDK17-specific rules:

| responseLength | Meaning | Usage |
| --- | --- | --- |
| **> 0** | Exact number of **bytes** in the body | Write the exact declared byte count |
| **0** | Uses **chunked transfer encoding** for the response body | Write as needed then close the stream |
| **-1** | **No response body** | For 204, 304, or no-body branches per contract |

**Do not treat 0 as a way to write Content-Length: 0**. In the **HttpExchange** API, 0 selects chunked encoding. For payloads with content, compute the length from **byte[]**:

~~~java
byte[] bytes = responseText.getBytes(StandardCharsets.UTF_8);
exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=UTF-8");
exchange.sendResponseHeaders(200, bytes.length);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(bytes);
}
~~~

Writing **fewer or more bytes** than a fixed responseLength can cause an IOException and abort the exchange. Therefore, do not use String.length() to determine a fixed-length HTTP response containing Unicode.

### Closing streams and exchange

**HttpExchange implements AutoCloseable**. Java 17 code can use:

~~~java
static void handle(HttpExchange exchange) throws IOException {
    try (exchange) {
        // Request -> response -> close streams/exchange.
    }
}
~~~

When closing the exchange, the JDK closes the request InputStream and response OutputStream according to the lifecycle. If the input has not been fully read, the implementation may drain/discard a portion of remaining bytes to attempt TCP reuse; if that fails, the connection may be closed. **Do not assume exchange.close will drain unboundedly at zero cost**. When rejecting large bodies, you need a body cap, timeout, and connection-close policy.

**Forgetting to close** can leave the client hanging, leak resources, or prevent proper connection reuse. When a handler throws an exception before sending a response, do not attempt to send 500 if headers are already committed; log and close the exchange to avoid a double-response.

## 8. Complete Java 17 example: GET/POST, URI, headers, body, and errors

**JdkHttpRequestDemo.java** creates an HttpServer on **127.0.0.1** with an OS-chosen port, then creates a Java 17 HttpClient to run tests directly in the same JVM. No Internet, Maven, JSON framework, or HTTPS certificate is needed.

Handler functionality:

- Reads method, raw path, raw query, and Headers.
- Accepts only the exact path **/inspect** even though the HttpContext prefix is broader.
- Allows only GET/POST, returning **405 + Allow** for other methods.
- Validates the **X-Trace-Id** header as alphanumeric/hyphen, up to 32 characters.
- Decodes form-style query; **name** must appear exactly once, **tag** may repeat (up to four).
- POST accepts only **text/plain; charset=UTF-8**.
- Reads at most 32 actual bytes, returning 413 if exceeded.
- POST decodes UTF-8 strictly, returning 400 on invalid byte sequences.
- Sets response headers, sends exact byte length, and cleans up the exchange.

Seven tests in order: GET query with repeated tag; POST Unicode text; POST unknown-length streaming (chunked over HTTP/1.1); wrong Content-Type 415; body too large 413; PUT 405; prefix-matching but non-exact path 404. Client authentication is not handled in the demo; real-world use must add separate protection.

### File JdkHttpRequestDemo.java

~~~java
import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URLDecoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class JdkHttpRequestDemo {
    static final int MAX_BODY = 32;

    static Map<String, List<String>> parseQuery(String raw) {
        Map<String, List<String>> parameters = new LinkedHashMap<>();
        if (raw == null || raw.isEmpty()) return parameters;
        if (raw.length() > 256)
            throw new IllegalArgumentException("Query too long");

        for (String part : raw.split("&", -1)) {
            int i = part.indexOf('=');
            String key = URLDecoder.decode(
                    i < 0 ? part : part.substring(0, i),
                    StandardCharsets.UTF_8);
            String value = URLDecoder.decode(
                    i < 0 ? "" : part.substring(i + 1),
                    StandardCharsets.UTF_8);
            parameters.computeIfAbsent(
                    key, unused -> new ArrayList<>()).add(value);
        }
        return parameters;
    }

    static byte[] readLimited(InputStream input, int max)
            throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] block = new byte[16];

        while (out.size() <= max) {
            int allowed = Math.min(
                    block.length, max + 1 - out.size());
            int n = input.read(block, 0, allowed);
            if (n == -1) return out.toByteArray();
            if (n == 0) continue;
            out.write(block, 0, n);
        }
        return null;
    }

    static void respond(HttpExchange exchange, int code, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        exchange.getResponseHeaders().set(
                "Cache-Control", "no-store");
        exchange.sendResponseHeaders(code, bytes.length);

        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    static void handle(HttpExchange exchange) throws IOException {
        try (exchange) {
            String method = exchange.getRequestMethod();
            URI uri = exchange.getRequestURI();
            Headers headers = exchange.getRequestHeaders();

            if (!"/inspect".equals(uri.getRawPath())) {
                respond(exchange, 404, "Not Found");
                return;
            }

            if (!"GET".equals(method) && !"POST".equals(method)) {
                exchange.getResponseHeaders().set(
                        "Allow", "GET, POST");
                respond(exchange, 405, "Method Not Allowed");
                return;
            }

            String trace = headers.getFirst("x-trace-id");
            if (trace == null ||
                    !trace.matches("[A-Za-z0-9-]{1,32}")) {
                respond(exchange, 400, "Invalid X-Trace-Id");
                return;
            }

            Map<String, List<String>> query;
            try {
                query = parseQuery(uri.getRawQuery());
            } catch (IllegalArgumentException invalidQuery) {
                respond(exchange, 400, "Invalid query");
                return;
            }

            List<String> names =
                    query.getOrDefault("name", List.of());
            List<String> tags =
                    query.getOrDefault("tag", List.of());

            if (names.size() != 1 ||
                    !names.get(0).matches("[A-Za-z ]{1,40}") ||
                    tags.size() > 4 ||
                    tags.stream().anyMatch(
                            t -> !t.matches("[a-z]{1,10}"))) {
                respond(exchange, 400, "Invalid parameters");
                return;
            }

            if ("POST".equals(method)) {
                String type = headers.getFirst("Content-Type");
                if (!"text/plain; charset=UTF-8".equalsIgnoreCase(
                        type == null ? "" : type.trim())) {
                    respond(exchange, 415,
                            "Unsupported Content-Type");
                    return;
                }
            }

            byte[] bytes = readLimited(
                    exchange.getRequestBody(), MAX_BODY);

            if (bytes == null) {
                exchange.getResponseHeaders().set(
                        "Connection", "close");
                respond(exchange, 413, "Request body too large");
                return;
            }

            if ("GET".equals(method) && bytes.length != 0) {
                respond(exchange, 400, "GET body not supported");
                return;
            }

            String bodyText = "";
            if ("POST".equals(method)) {
                try {
                    bodyText = StandardCharsets.UTF_8.newDecoder()
                            .onMalformedInput(
                                    CodingErrorAction.REPORT)
                            .onUnmappableCharacter(
                                    CodingErrorAction.REPORT)
                            .decode(ByteBuffer.wrap(bytes))
                            .toString();
                } catch (CharacterCodingException invalid) {
                    respond(exchange, 400, "Invalid UTF-8 body");
                    return;
                }
            }

            String message = method +
                    " name=" + names.get(0) +
                    " tags=" + String.join(",", tags) +
                    " trace=" + trace +
                    " bytes=" + bytes.length;
            if ("POST".equals(method)) {
                message += " text=" + bodyText;
            }

            respond(exchange, 200, message);
        }
    }

    static HttpResponse<String> request(
            HttpClient client, URI base, String path,
            String method, HttpRequest.BodyPublisher body,
            String trace, String contentType) throws Exception {
        HttpRequest.Builder request = HttpRequest.newBuilder(
                URI.create(base.toString() + path))
                .timeout(Duration.ofSeconds(5));

        if (trace != null) request.header("X-Trace-Id", trace);
        if (contentType != null)
            request.header("Content-Type", contentType);
        request.method(method, body);

        return client.send(
                request.build(),
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    static void expect(
            String label, HttpResponse<String> actual,
            int expectedCode, String expectedBody) {
        if (actual.statusCode() != expectedCode ||
                !expectedBody.equals(actual.body())) {
            throw new AssertionError(
                    label + ": expected " +
                    expectedCode + "/" + expectedBody +
                    ", actual " +
                    actual.statusCode() + "/" + actual.body());
        }
        System.out.println(
                label + " status=" + expectedCode +
                " body=" + expectedBody);
    }

    public static void main(String[] args) throws Exception {
        ExecutorService workers =
                Executors.newFixedThreadPool(3);
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext(
                "/inspect", JdkHttpRequestDemo::handle);
        server.setExecutor(workers);

        try {
            server.start();
            URI base = URI.create(
                    "http://127.0.0.1:" +
                    server.getAddress().getPort());

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            expect("GET", request(client, base,
                    "/inspect?name=Ada%20Lovelace&tag=red&tag=blue",
                    "GET",
                    HttpRequest.BodyPublishers.noBody(),
                    "g-1", null),
                    200, "GET name=Ada Lovelace " +
                            "tags=red,blue trace=g-1 bytes=0");

            byte[] vietnamese = "Xin chào Java!".getBytes(
                    StandardCharsets.UTF_8);

            expect("POST", request(client, base,
                    "/inspect?name=Lan+Anh",
                    "POST",
                    HttpRequest.BodyPublishers.ofByteArray(
                            vietnamese),
                    "p-1", "text/plain; charset=UTF-8"),
                    200, "POST name=Lan Anh " +
                            "tags= trace=p-1 bytes=" +
                            vietnamese.length +
                            " text=Xin chào Java!");

            expect("CHUNKED", request(client, base,
                    "/inspect?name=Kim",
                    "POST",
                    HttpRequest.BodyPublishers.ofInputStream(
                            () -> new ByteArrayInputStream(
                                    "Hi".getBytes(
                                            StandardCharsets.UTF_8))),
                    "c-1", "text/plain; charset=UTF-8"),
                    200, "POST name=Kim tags= " +
                            "trace=c-1 bytes=2 text=Hi");

            expect("BAD_TYPE", request(client, base,
                    "/inspect?name=Kim",
                    "POST",
                    HttpRequest.BodyPublishers.ofString("{}"),
                    "m-1", "application/json"),
                    415, "Unsupported Content-Type");

            expect("TOO_LARGE", request(client, base,
                    "/inspect?name=Kim",
                    "POST",
                    HttpRequest.BodyPublishers.ofString(
                            "0123456789012345678901234567890123456789"),
                    "l-1", "text/plain; charset=UTF-8"),
                    413, "Request body too large");

            HttpResponse<String> unsupported = request(
                    client, base, "/inspect?name=Kim",
                    "PUT",
                    HttpRequest.BodyPublishers.noBody(),
                    "u-1", null);

            expect("BAD_METHOD", unsupported,
                    405, "Method Not Allowed");
            String allow = unsupported.headers()
                    .firstValue("Allow").orElse("");
            if (!"GET, POST".equals(allow)) {
                throw new AssertionError(
                        "Invalid Allow header: " + allow);
            }
            System.out.println("Allow: " + allow);

            expect("BAD_PATH", request(client, base,
                    "/inspect-other?name=Kim",
                    "GET",
                    HttpRequest.BodyPublishers.noBody(),
                    "n-1", null),
                    404, "Not Found");
        } finally {
            server.stop(0);
            workers.shutdown();
            if (!workers.awaitTermination(
                    5, TimeUnit.SECONDS)) {
                workers.shutdownNow();
                if (!workers.awaitTermination(
                        5, TimeUnit.SECONDS)) {
                    throw new AssertionError(
                            "Workers did not terminate");
                }
            }
        }

        if (!workers.isTerminated()) {
            throw new AssertionError(
                    "Executor not terminated");
        }
        System.out.println("Executor terminated: true");
    }
}
~~~

### Compile and run

Save the file **JdkHttpRequestDemo.java**, using **JDK 17 or later**:

~~~bash
javac --release 17 --add-modules jdk.httpserver -encoding UTF-8 JdkHttpRequestDemo.java
java --add-modules jdk.httpserver JdkHttpRequestDemo
~~~

**Stdout verified successfully on the JVM using Java 17-compatible source:**

~~~text
GET status=200 body=GET name=Ada Lovelace tags=red,blue trace=g-1 bytes=0
POST status=200 body=POST name=Lan Anh tags= trace=p-1 bytes=15 text=Xin chào Java!
CHUNKED status=200 body=POST name=Kim tags= trace=c-1 bytes=2 text=Hi
BAD_TYPE status=415 body=Unsupported Content-Type
TOO_LARGE status=413 body=Request body too large
BAD_METHOD status=405 body=Method Not Allowed
Allow: GET, POST
BAD_PATH status=404 body=Not Found
Executor terminated: true
~~~

**Why is this result reliable?** The test uses no Internet, communicating only over **127.0.0.1** and an OS-assigned port 0. Each response is asserted for **both status code and body string before printing**, so it does not print a false PASS merely because the server returned some content. At the end of the test, server.stop(0), pool.shutdown/awaitTermination, and isTerminated confirm that the executor has finished.

**Limitations:** The source is simplified to teach HttpExchange and lacks authentication, uploads, JSON schema, file streaming, or TLS. The 32-byte limit and ASCII name rule are for testing only; real services need byte quotas, charset/name validation, timeouts, memory policies, and concurrency tuned to business needs. If HTTPS is needed, use **HttpsServer** with a certificate/trust policy or a managed reverse proxy; do not treat a local HTTP test as proof that the server is secure for public deployment.

### 8.1. Line-by-line explanation of the 9 stdout lines

| Line | Verified behavior |
| --- | --- |
| **GET status=200** | GET reads URI raw query name=Ada%20Lovelace, repeated tag; case-insensitive X-Trace-Id; no body |
| **POST status=200** | POST receives UTF-8 text/plain, decodes strictly, reports exact **15 bytes** of Xin chào Java! |
| **CHUNKED status=200** | Unknown-length request body is still read from InputStream as **Hi** |
| **BAD_TYPE status=415** | Media type not supported by the endpoint |
| **TOO_LARGE status=413** | Request exceeding 32 bytes is rejected upon reading the 33rd byte |
| **BAD_METHOD status=405** | PUT is not GET/POST, route returns Method Not Allowed |
| **Allow: GET, POST** | Allow header accompanying 405 is tested separately |
| **BAD_PATH status=404** | /inspect-other is not treated as /inspect despite context prefix match |
| **Executor terminated: true** | Server worker pool is cleaned up after the test |

### Note on early rejection

When a handler rejects a request **before reading the entire body** (e.g., wrong content type or body too large), HttpExchange.close() may cause the JDK to attempt to **drain a portion of unread bytes**. Do not assume the connection will definitely be reused or that the server will definitely incur no extra I/O. In the oversized-body case, the demo sets Connection: close and returns 413; in real environments, edge limits and timeouts must be used to defend against Slowloris/DoS.

## 9. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| **Assuming method is an enum** | Wrong mapping or invalid cast | getRequestMethod returns String, compare explicitly |
| **Assuming Context path is exact-match** | /inspect-other enters the /inspect handler | Check rawPath exactly |
| **Calling getQuery then URLDecoder again** | Double decoding, potential path/query bypass | Decode raw components exactly once |
| **Losing repeated query params** | Information overwritten | Map<String,List<String>> |
| **Using only getFirst for sensitive headers** | Conflicting values ignored | Inspect full list or reject duplicates |
| **Calling set on request Headers** | Read-only, runtime error | Only modify response Headers |
| **Treating Content-Type as a parser** | Wrong decoding/body parsing | Check media type then parse with an appropriate library |
| **Using unbounded readAllBytes** | OOM/DoS | Streaming body cap + timeout |
| **Assuming Content-Length is always present** | Misses chunked transfer | Count bytes actually read |
| **Computing Content-Length with String.length()** | Wrong for UTF-8 Unicode | Use byte[].length |
| **Not distinguishing 0 and -1 in InputStream.read** | Wrong loop/incomplete read | Only -1 is EOF |
| **Ignoring malformed charset** | Data corruption or parser confusion | CharsetDecoder.REPORT when strict |
| **Returning 200 on unsupported Content-Type** | Parser error/unclear business logic | 415 |
| **Returning 200 for PUT on wrong route** | Violates contract | 405 + Allow |
| **Using sendResponseHeaders(code,0) for no-body** | JDK uses chunked response | -1 for no-body |
| **Not closing OutputStream/exchange** | Client hangs, resources not released | try-with-resources/finally |
| **Writing fewer bytes than fixed response length** | IOException/aborted exchange | Write exact byte count |
| **Reading/dumping entire body into logs** | Leaks tokens/PII | Redact, limit to metadata |
| **Letting clients self-assert roles via X-Forwarded headers** | Identity/network route spoofing | Trust only managed proxies |
| **Limiting only bytes without limiting time** | Workers held by slow clients | Request timeout, limits at ingress/server |
| **Using an uncontrolled ThreadPool under load** | Starvation/memory pressure | Bounded queue and concurrency policy |

## 10. Security and operations

### 10.1. Input from HTTP clients is always untrusted

- **Method:** accept only methods supported by the route.
- **URI/path:** check path segments, encoding, query length, and normalization; avoid **../**, encoded-slash, and ambiguous double decoding.
- **Query:** validate keys, values, duplicates, count, and length; do not trust roles or IDs taken directly from the query.
- **Headers:** limit count/size, detect duplicate sensitive headers, and do not log secrets.
- **Body:** limit byte count, receive time, media type, charset, parser depth, and decompressed size.
- **Response:** escape/encode according to content type, do not inject untrusted CRLF into headers, and choose appropriate statuses.

**getRemoteAddress() is only the network peer address seen by HttpServer**, which may be a reverse proxy rather than the end user. Forwarded/X-Forwarded-For is data that must be verified from a trusted proxy, not trusted from arbitrary requests.

### 10.2. Request smuggling, Content-Length, and Transfer-Encoding

When an HTTP request passes through a **reverse proxy/gateway and backend**, if the two sides interpret framing differently (especially conflicting **Content-Length** and **Transfer-Encoding** fields), **HTTP request smuggling/desynchronization** can occur. Do not try to "fix" this by manually parsing raw HTTP frames from **getRequestBody()**; HttpServer already handles framing before creating the InputStream.

The solution requires aligning rules across components, rejecting malformed/ambiguous requests, keeping servers/gateways updated, limiting connection reuse when appropriate, and testing proxy/backend together. JDK HttpServer is a lightweight HTTP server, not a replacement for a properly configured/hardened ingress for untrusted workloads.

### 10.3. Slow and small is still dangerous

A 32-byte body cap does not protect against a client sending one byte per minute. For public servers, you should have:

- Connection limits and concurrent request limits.
- Limits on header field count, header bytes, URI length, and payload bytes.
- Request receive timeout/idle timeout with clear policies.
- ThreadPoolExecutor with a bounded queue and overload policy.
- TLS/HTTPS, auth, auditing, logging redaction, and rate limiting.
- Reverse proxy/gateway protecting the HTTP parser and blocking invalid requests.

The JDK has **implementation-specific system properties** for HttpServer in some versions, such as **sun.net.httpserver.maxReqHeaders**, **sun.net.httpserver.maxReqHeaderSize**, **sun.net.httpserver.maxReqTime**, **sun.net.httpserver.drainAmount**, and **jdk.httpserver.maxConnections**. **Do not hardcode default values** without checking the corresponding JDK vendor/patch documentation. Those properties do not fully replace edge/server application-level size/time budgets.

### 10.4. Request authorization and session

**Authorization** or **Cookie** headers are client-supplied data, not proof of authentication. If using an HttpContext Authenticator, **getPrincipal()** can return the appropriate principal after auth; without an Authenticator, do not assume a principal is present. For cookie-based authentication, you also need CSRF defense, session expiration/revocation, and per-route authorization.

### 10.5. Executor lifecycle

The demo calls **setExecutor(Executors.newFixedThreadPool(3))** for a short test. In Java 17, newFixedThreadPool has an unbounded queue by default, so do not use that configuration as-is for public endpoints that may receive many requests. In production, manage threads, queues, shutdown, and overload handling.

Closing an HttpExchange and shutting down an executor are two separate actions: closing the exchange cleans up one request/response; server.stop and executor.shutdown manage the service lifecycle.

## 11. Exercises and test matrix

| Test | Request | Expected |
| --- | --- | --- |
| **Valid GET** | /inspect?name=Ada%20Lovelace&tag=red&tag=blue, X-Trace-Id g-1 | 200, preserves repeated tag, zero body |
| **POST UTF-8** | name=Lan+Anh, text/plain UTF-8, body Xin chào Java! | 200, 15 bytes, decodes accents properly |
| **POST streaming/chunked** | BodyPublisher.ofInputStream with bytes Hi | 200, reads 2 bytes from InputStream |
| **Wrong media type** | POST Content-Type application/json | 415 |
| **Body too large** | POST 40 bytes when MAX_BODY=32 | 413 |
| **Method not allowed** | PUT /inspect | 405 + Allow GET, POST |
| **Non-exact path prefix** | GET /inspect-other | 404 |
| **Missing/invalid header** | X-Trace-Id with control characters or missing | 400 or rejected earlier by HTTP parser |
| **Repeated name query key** | name=Ada&name=Lan | 400 |
| **Encoded query** | name=Lan+Anh, name=C%2B%2B | Decode once, validate per contract |
| **Invalid UTF-8** | POST body with invalid byte sequence | 400 |
| **No response body** | Route returns 204 | sendResponseHeaders(204,-1), write no body |
| **Header name case** | x-trace-id/X-TRACE-ID | Reads the same field |
| **Slow client** | Sends body byte by byte over a long period | Request timeout/ingress limit, does not hold worker indefinitely |
| **Duplicate framing** | Conflicting CL/TE through proxy | Rejected by consistent policy, no parser confusion |

For extension tests, do not send attack-shaped requests or oversized payloads to third-party systems you are not authorized to test. Use a local lab/fixture under your control.

## 12. Self-check questions

**1. What does getRequestMethod return?**  
Returns a String such as GET, POST. The handler decides which methods are allowed.

**2. Why shouldn't getRequestURI simply be converted to a String and split on the question mark?**  
Because URI has raw/decoded components, percent-encoding, and query grammar that require proper parsing.

**3. Are URI.getRawQuery and URI.getQuery the same?**  
No. Raw preserves escapes; decoded query is percent-decoded according to URI semantics.

**4. Why does URLDecoder turn Lan+Anh into Lan Anh?**  
Because URLDecoder follows form-urlencoded semantics where + is a space. For a literal plus sign, encode %2B.

**5. If a query has tag=red&tag=blue, which value should be chosen?**  
If the API allows repetition, keep both in a List; do not overwrite.

**6. Is HttpContext("/inspect") always an exact route?**  
No. It matches by prefix; /inspect-other can enter that handler.

**7. Can Headers.getFirst read content-type if the client sends Content-Type?**  
Yes, header names are case-insensitive.

**8. Why is getFirst unsuitable for all sensitive headers?**  
Some headers can have multiple values/duplicates; taking only the first can create ambiguity.

**9. Is getRequestHeaders mutable?**  
No, per HttpExchange it is read-only. getResponseHeaders is mutable.

**10. Is a 15-byte UTF-8 body guaranteed to be 15 Java chars?**  
No. Unicode can have multiple UTF-8 bytes for a single char/code point.

**11. Does getRequestBody return a parsed JSON string?**  
No. It returns an InputStream of bytes; the application must decode/parse according to Content-Type.

**12. Does calling getRequestBody twice create two new streams?**  
No. It is the same stream, and already-read data does not replay automatically.

**13. Does an absent Content-Length mean an empty body?**  
No. HTTP/1.1 chunked encoding can send a body without Content-Length.

**14. Why is readAllBytes on an untrusted request dangerous?**  
It can allocate unbounded RAM for the body, causing DoS.

**15. How many bytes at most does the demo's readLimited function read before determining it exceeds 32?**  
At most 33 bytes, i.e., MAX_BODY+1, to detect exceeding the threshold.

**16. Why use CharsetDecoder.REPORT?**  
To reject malformed UTF-8 instead of silently substituting replacement characters.

**17. What should POST Content-Type application/json return when the route only accepts text/plain?**  
415 Unsupported Media Type.

**18. What should PUT to a route supporting only GET/POST return?**  
405 Method Not Allowed with Allow: GET, POST.

**19. Does sendResponseHeaders(status,0) mean no body?**  
No. JDK HttpExchange uses 0 for a chunked response; -1 for no-body.

**20. What happens when a response length is fixed but fewer bytes are written?**  
It can throw an IOException/abort the exchange, causing the underlying connection to close.

**21. Does closing an exchange when the request is not fully read guarantee TCP reuse?**  
No. The JDK may drain some unread bytes, but if that is not enough it may close the connection.

**22. When a server is behind a proxy, is getRemoteAddress always the original client IP?**  
No. It can be the proxy; forwarded headers should only be trusted from controlled proxies.

**23. Does a byte cap completely protect against slow clients?**  
No. You also need request/read deadlines, concurrency limits, and connection limits.

**24. Does this demo verify production HTTPS?**  
No. It is a loopback HTTP/1.1 demo used to test method, URI, header, and body lifecycles on the JDK.

## Conclusion

To read HTTP requests in **JDK HttpServer**, use **HttpExchange.getRequestMethod()** for the method, **getRequestURI()** for path/query, **getRequestHeaders()** for case-insensitive multi-valued headers, and **getRequestBody()** for the body as an **InputStream of bytes**. Separate metadata from payload, decode query/UTF-8 in the proper format, do not trust Content-Length as the only limit, and do not treat HttpContext prefix matching as exact routing.

A safe handler must **validate method, path, headers, media type, and bytes**, use appropriate statuses (400/404/405/413/415), set response headers, **sendResponseHeaders with the exact byte count**, and then close the OutputStream and HttpExchange. When serving real traffic, add authentication, TLS, timeouts, rate limits, and proxy/gateway hardening.

### References

- [Java SE 17 — HttpExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): request method/URI/headers/body, response length, and close.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): createContext, literal-prefix routing, executor.
- [Java SE 17 — Headers](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Headers.html): case-insensitive multi-valued request/response headers.
- [Java SE 17 — HttpHandler](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html): handle(HttpExchange).
- [Java SE 17 — HttpContext](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html): context path, Filters, Authenticator.
- [Java SE 17 — URI](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html): raw path, raw query, URI decoding.
- [Java SE 17 — URLDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLDecoder.html): form-style percent-decoding.
- [Java SE 17 — CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html): strict UTF-8.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): local integration test client.
- [Java SE 17 — HttpsServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html): HTTPS variant.
- [Java 17 Networking Properties](https://docs.oracle.com/en/java/javase/17/core/java-networking.html): connection/headers/request limits of the JDK HttpServer implementation.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): methods, status codes, media types.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112.html): Content-Length, chunked, and request framing.
- [OWASP — HTTP Request Smuggling](https://wstg.owasp.org/latest/4-Web_Application_Security_Testing/07-Injection/16-HTTP_Request_Smuggling/): frontend/backend parsing discrepancy risks.
