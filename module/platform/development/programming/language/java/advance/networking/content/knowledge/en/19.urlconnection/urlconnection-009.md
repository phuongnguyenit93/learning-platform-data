# Comparing the Legacy API with HttpClient When Reading or Migrating Existing Code

**Topic:** Java Advance - networking  
**Group:** URLConnection  
**Environment:** Java 17+, especially migrating from **java.net.URLConnection / HttpURLConnection / HttpsURLConnection** to **java.net.http.HttpClient** (available since Java 11).

In long-lived Java systems, an HTTP call typically starts with **new URL(...).openConnection()**, continues with **setRequestMethod()**, **setRequestProperty()**, **getInputStream()**, **getErrorStream()**, and ends with **disconnect()**. Java 11 introduced the modern **HttpClient** with **HttpRequest**, **HttpResponse**, and **BodyHandler/BodyPublisher**, supporting synchronous sending, asynchronous sending, and HTTP/2. Migrating from the legacy API to the new API **is not just renaming methods**: status/error bodies, redirects, timeouts, cookies, proxies, charsets, TLS, streaming, and resource management can all differ.

This lesson explains how to read legacy code properly, verify semantics before migrating, map out an API equivalence table, handle tricky edge cases, and provides a **standalone Java 17 program that has been compiled and run** using **both APIs** against the same loopback HTTP server. The goal is to **preserve application behavior** before optimizing for new capabilities.

## 1. The Legacy and Modern Models

### URLConnection / HttpURLConnection: a stateful object

~~~text
URL (resource identifier)
  |
  +-- openConnection()
          |
          +-- URLConnection (generic)
          |      setConnectTimeout, setReadTimeout,
          |      setRequestProperty, getInputStream...
          |
          +-- HttpURLConnection (HTTP-specific)
                 setRequestMethod, getResponseCode,
                 getErrorStream, setInstanceFollowRedirects,
                 disconnect...
~~~

**URL** is the representation of an address, while **URLConnection** is the link for accessing a resource via a URL. **HttpURLConnection** extends URLConnection and adds HTTP semantics. **HttpsURLConnection** further extends HttpURLConnection, adding TLS options.

Typical flow:

1. **openConnection()** returns a connection object but does not necessarily open a TCP connection immediately.
2. Call setters **before connecting**: method, headers, timeouts, redirects, doOutput, streaming mode.
3. Call **connect()**, **getOutputStream()**, **getResponseCode()**, or **getInputStream()** to trigger network I/O when needed.
4. Retrieve the **HTTP status** via **getResponseCode()**; read the success body via **getInputStream()** or the error body via **getErrorStream()**.
5. Close InputStream/OutputStream using try-with-resources and call **disconnect()** in finally when no longer needed.

**Do not cast every URLConnection to HttpURLConnection:**

~~~java
URLConnection connection = new URL(someUrl).openConnection();
HttpURLConnection http = (HttpURLConnection) connection;
~~~

This snippet is only valid when **someUrl** uses an appropriate HTTP/HTTPS handler. For **file:**, **jar:**, and other URL protocols, the cast can throw **ClassCastException**. During migration, keep URLConnections used for non-HTTP resources instead of mechanically converting them to HttpClient.

### HttpClient: separating client policy, request, and response

~~~text
HttpClient.Builder
    -> build() -> HttpClient [immutable configuration]
                       |
                       +--> HttpRequest.Builder
                       |         -> build() -> HttpRequest
                       |
                       +--> send(request, BodyHandler)
                       |       -> HttpResponse<T>
                       |
                       +--> sendAsync(request, BodyHandler)
                               -> CompletableFuture<HttpResponse<T>>
~~~

Once built, **HttpClient** is a configuration object that can be **reused across multiple requests**. **HttpRequest** holds the URI, method, headers, body publisher, and request timeout. **HttpResponse<T>** contains the status, headers, body, URI, HTTP version, and other response details.

**Bug-prone difference:** HttpClient **does not automatically throw IOException simply for a 404 or 500 status**. When a complete HTTP response is received according to the BodyHandler, **response.statusCode()** is still 404/500 and **response.body()** may contain the error body. Legacy getInputStream() can throw IOException on 4xx/5xx, which is why many legacy systems need **getErrorStream()**.

## 2. API Comparison Table for Code Review

| Purpose | Legacy URLConnection / HttpURLConnection | Java 17 HttpClient | What to Verify |
| --- | --- | --- | --- |
| Resource URI | **new URL(text)** | **URI.create(text)** | URL and URI differ in parsing/encoding |
| Open handle | **url.openConnection()** | **HttpRequest.newBuilder(uri)** | Builder does not perform network I/O yet |
| GET | **setRequestMethod("GET")** | **.GET()** | Method and query are preserved |
| POST | **setRequestMethod("POST"); setDoOutput(true)** | **.POST(BodyPublishers.ofString(...))** | Content-Type, charset, body bytes |
| PUT | **setRequestMethod("PUT")** | **.PUT(BodyPublisher)** | Side effects and idempotency |
| DELETE | **setRequestMethod("DELETE")** | **.DELETE()** | Status/body contract |
| Custom method | **setRequestMethod(...)** (implementation-limited) | **.method(name,publisher)** | PATCH/custom verb, server behavior |
| Request header | **setRequestProperty(name,value)** | **.header(name,value)** or **.setHeader(name,value)** | Duplicate headers and restricted headers |
| Connect timeout | **setConnectTimeout(milliseconds)** | **HttpClient.Builder.connectTimeout(Duration)** | Not a total deadline |
| Read timeout | **setReadTimeout(milliseconds)** | **HttpRequest.Builder.timeout(Duration)** | **Not a 1:1 equivalent** |
| Status | **getResponseCode()** | **response.statusCode()** | Separate HTTP status from transport failure |
| Success body | **getInputStream()** | **BodyHandlers.ofString/ofByteArray/ofInputStream** | Choose handler based on size/content |
| Error body | **getErrorStream()** | **response.body()** for 4xx/5xx status | Legacy error stream can be null |
| Response header | **getHeaderField("Name")** | **response.headers().firstValue("Name")** | Optional and multi-value headers |
| Redirect | **setInstanceFollowRedirects(...)** | **followRedirects(Redirect...)** | Different defaults |
| Cookies | **CookieHandler.setDefault(...)** or manual Cookie | **cookieHandler(CookieHandler)** | Session state is not transferred automatically |
| Proxy | **openConnection(proxy)** / system proxy | **proxy(ProxySelector)** | Proxy routing and credentials |
| TLS | **HttpsURLConnection** | **sslContext(...)**, default TLS | Cert chain, hostname, mTLS |
| Async | Run blocking code on an executor manually | **sendAsync(...)** | Future, cancellation, backpressure |
| HTTP version | Built-in HTTP connection is mainly HTTP/1.1 | HTTP/1.1 and HTTP/2 | Preferred vs actual version |
| Resource cleanup | Close stream + disconnect() | Close streaming response body; manage client lifecycle | Do not treat close/disconnect as the same thing |

**Do not remove HttpURLConnection just because the API is old.** It still works in Java 17; migration decisions depend on goals, JDK compatibility, HTTP scope, and testability. Use a checklist to preserve behavior first, optimize later.

## 3. Reading Legacy URLConnection Code Properly

Minimal legacy code:

~~~java
URL url = new URL("https://service.example/data");
URLConnection conn = url.openConnection();
try (InputStream in = conn.getInputStream()) {
    byte[] bytes = in.readAllBytes();
    String text = new String(bytes, StandardCharsets.UTF_8);
}
~~~

This is **not a standalone program**: it needs imports, exception handling, and usage of the `text` variable. It is only suitable when the URL handler/response fits, the body is bounded, and the UTF-8 charset matches the contract. With HTTP 404, **getInputStream()** can throw **FileNotFoundException** instead of returning an error body; to read the status/error body, you must work directly with **HttpURLConnection**.

### Legacy pattern for handling HTTP status and error body

~~~java
HttpURLConnection conn = (HttpURLConnection) url.openConnection();
conn.setConnectTimeout(2_000);
conn.setReadTimeout(3_000);
conn.setInstanceFollowRedirects(false);
conn.setRequestMethod("GET");
try {
    int status = conn.getResponseCode();
    InputStream source = status >= 400
            ? conn.getErrorStream()
            : conn.getInputStream();

    String body = "";
    if (source != null) {
        try (InputStream in = source) {
            body = new String(
                    in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
    System.out.println(status + " " + body);
} finally {
    conn.disconnect();
}
~~~

**getErrorStream() can be null** when there is no error content, when not yet connected, or when there is no applicable error. **getErrorStream() does not initiate a connection itself**; read the status via **getResponseCode()** first. **getInputStream()** can return empty data on 204/304. Do not attempt to parse JSON on statuses that have no response body.

Do not interpret a generic IOException as **HTTP 500**. DNS failure, TLS handshake failure, connection reset, or timeout can occur **without any HTTP response existing**. Conversely, HTTP 500 is a response that the server/gateway actually sent.

## 4. Equivalent GET with HttpClient

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://service.example/data"))
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

int status = response.statusCode();
String body = response.body();
~~~

The snippet requires imports and catching **IOException/InterruptedException**. **BodyHandlers.ofString(StandardCharsets.UTF_8)** uses UTF-8 per the API contract. If the server declares a different charset, you must read Content-Type and use the appropriate decoder; **Content-Encoding: gzip** is not a text charset.

The new API can return response.statusCode()==404 with response.body() containing the error message. **BodyHandlers.ofString() does not automatically treat 4xx/5xx as exceptions.** You should usually parse the error schema based on the status rather than just returning the body and treating it as success.

### Proper status classification

~~~java
int code = response.statusCode();
if (code >= 200 && code < 300) {
    // HTTP success; check the specific code and business contract.
} else if (code >= 300 && code < 400) {
    // Redirect/conditional response; e.g., 304.
} else if (code >= 400 && code < 500) {
    // Validation/auth/not found/rate limit...
} else if (code >= 500 && code < 600) {
    // HTTP server/gateway error.
}
~~~

**HTTP 202 Accepted** does not guarantee the job has finished; **204 No Content** has no body; **304 Not Modified** is used in caching; **404 Not Found** can be a valid outcome when looking up a resource; **429** may require backing off according to Retry-After. **Business success is not equivalent to every 2xx**.

### Error mapping table

| Outcome | Legacy | HttpClient |
| --- | --- | --- |
| 200 with body | getInputStream | response.body() |
| 201 + Location | getResponseCode + getHeaderField | statusCode + headers().firstValue |
| 204 with no content | getResponseCode, empty body | statusCode, empty body |
| 302 Location | Depends on redirect flag | Depends on Redirect.NEVER/NORMAL/ALWAYS |
| 404/500 with error body | getErrorStream may have data | HttpResponse contains status and body |
| DNS/connection/TLS failure | IOException/subtype | IOException/subtype; no complete HttpResponse |
| Timeout | SocketTimeoutException or IOException depending on phase | HttpTimeoutException/subtype or IOException |
| Request interrupted | Thread blocking/IOException depending on location | send may throw InterruptedException |

**Migration principle:** keep HTTP status in **response**, transport errors in **exception**, and business errors in **domain result**. Do not assign a fake status 0 or 500 as an HTTP response when only an IOException occurred.

## 5. Redirects: Different Defaults

**HttpURLConnection** has a redirect-following mechanism and auto-follow is generally enabled by default; per-instance control uses **setInstanceFollowRedirects(false)**. **HttpClient.newHttpClient()** defaults to **HttpClient.Redirect.NEVER**. If legacy code previously received 200 after automatically following a 302, the modern default may only return 302.

~~~java
// Legacy: disable auto-follow to observe 302.
conn.setInstanceFollowRedirects(false);

// Modern: disable auto-follow to preserve the behavior above.
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

// When you actually want to follow according to a policy:
HttpClient followed = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();
~~~

**Redirect.NORMAL** does not allow HTTPS → HTTP downgrades in the built-in client; **ALWAYS** has a broader policy. For POST, 301/302/303 may change the method according to rules/historical behavior, while 307/308 require preserving the method; **test endpoints with side effects** instead of assuming the client always preserves the POST body.

**Do not lose credential protection**: redirecting to another origin can involve Authorization/Cookie headers. Only enable auto-follow if domain, protocol, and method transitions are controlled according to the contract.

## 6. Timeouts Cannot Be Converted by Simple Arithmetic

Legacy:

~~~java
conn.setConnectTimeout(2000); // ms.
conn.setReadTimeout(3000);    // ms.
~~~

**setConnectTimeout** limits waiting to establish a connection per its contract. **setReadTimeout** is the timeout for a blocking **read** waiting for data; it is not a total deadline for an HTTP request covering all bytes. In URLConnection, **0** typically represents an infinite timeout per the Javadoc, not an immediate timeout.

Modern:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(5))
        .GET().build();
~~~

**connectTimeout** only applies when a new connection is needed; a reused connection does not perform a TCP connect again. **HttpRequest.timeout(Duration)** bounds the request per the API, **not equivalent to each individual read()** as in legacy. In particular, when using **BodyHandlers.ofInputStream**, send or sendAsync may return the response once headers arrive even while the body is still open; the application needs **body idle timeout, size limit, total deadline, and close/cancel** if required.

When migrating, document the **actual SLA**: connect deadline, time to headers, body idle timeout, total operation deadline. Do not simply convert milliseconds to Duration and assume behavior remains identical.

When catching **InterruptedException** from **send()**, call **Thread.currentThread().interrupt()** and propagate cancellation/error to the caller layer. Cancellation does not guarantee the server rolls back if the request was already sent.

## 7. POST: OutputStream vs BodyPublisher

Legacy POST:

~~~java
HttpURLConnection conn = (HttpURLConnection) url.openConnection();
conn.setRequestMethod("POST");
conn.setDoOutput(true);
byte[] bytes = "ping".getBytes(StandardCharsets.UTF_8);
conn.setFixedLengthStreamingMode(bytes.length);
conn.setRequestProperty("Content-Type", "text/plain; charset=UTF-8");
try (OutputStream out = conn.getOutputStream()) {
    out.write(bytes);
}
int code = conn.getResponseCode();
~~~

The snippet needs handling for closing response streams, finally disconnect, and imports. **setFixedLengthStreamingMode** uses the **byte count**, not **String.length()** (the number of UTF-16 code units). Using **setChunkedStreamingMode** instead when the length is unknown can affect auto-auth/redirects in legacy code; streaming mode can trigger **HttpRetryException** in cases where automatic replay is needed.

Modern POST:

~~~java
HttpRequest request = HttpRequest.newBuilder(uri)
        .header("Content-Type", "text/plain; charset=UTF-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                "ping", StandardCharsets.UTF_8))
        .build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
~~~

Appropriate **BodyPublishers** include:

| Publisher | When to use |
| --- | --- |
| **noBody()** | Request with no body |
| **ofString(text, charset)** | Existing JSON or text |
| **ofByteArray(bytes)** | Small binary data |
| **ofFile(path)** | File upload |
| **ofInputStream(supplier)** | Stream source that can be created when sending |
| **fromPublisher(...)** | Reactive Flow.Publisher<ByteBuffer> |

**Do not manually set the Content-Length header** for every publisher. The built-in HttpClient has restricted headers and manages framing automatically based on the publisher/protocol; translating legacy **setRequestProperty("Content-Length", ...)** to modern **.header("Content-Length", ...)** may be rejected. When sending Unicode, Content-Length is in UTF-8 bytes, not the number of Java characters.

**Replayability:** The supplier in **ofInputStream** may need to create a fresh stream if the client has to resend the content when handling authentication/retries. Do not return the same already-consumed InputStream; the subsequent request may send missing bytes.

**Idempotency:** If a POST that creates an order was committed on the server but the client timed out waiting for the response, an automatic retry can create a second order. Changing the HTTP client API does not solve that problem: you need an idempotency key/business transaction ID per the API contract, or a status lookup before retrying.

## 8. Headers, Charset, Content-Encoding, and Cookies

### Charsets do not align automatically

~~~java
String textLegacy = new String(bytes, StandardCharsets.UTF_8);
HttpResponse<String> textModern = client.send(
        request, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));
~~~

The two patterns are equivalent **if the endpoint's contract is UTF-8**. If the server declares a different charset, you need to parse **Content-Type**; do not rely on the OS default charset. **Content-Encoding** such as gzip is compression/content coding, distinct from text **charset**; **Content-Length** is the byte count, not Java String.length().

For binary responses, use **BodyHandlers.ofByteArray()**, **ofInputStream()**, or **ofFile(path)**. Do not convert JPEG/ZIP into a String and back to bytes, as that can corrupt data. **ofByteArray** holds the entire body in RAM so it needs a size limit; **ofFile** can save the **404/500 error body** into the file if used directly, so you must check the status.

### Multiple headers

Legacy **getHeaderField("Set-Cookie")** may return only one value. Modern **response.headers().allValues("Set-Cookie")** retrieves the full list; do not join all Set-Cookie values with commas. **HttpRequest.Builder.header(...)** appends a header value; **setHeader(...)** replaces previous values. This differs from legacy setRequestProperty replacing a single value.

### Cookies

Legacy code may use CookieManager via **CookieHandler.setDefault(...)** JVM-wide or set the Cookie header manually. Modern code can configure it specifically per client:

~~~java
CookieManager cookies = new CookieManager();
cookies.setCookiePolicy(CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient client = HttpClient.newBuilder()
        .cookieHandler(cookies)
        .build();
~~~

The snippet requires imports. Do not expect every HttpClient to retain session cookies automatically without configuring an appropriate handler. Only accept cookies according to domain/path/security policy; avoid logging secret cookies.

### Authentication and proxy

Legacy code may use **Authenticator.setDefault(...)**, **url.openConnection(proxy)**, JVM system properties, or headers. Modern code has **HttpClient.Builder.authenticator(...)** and **proxy(ProxySelector)**. Verify proxy credentials, HTTP 401/407, Cookie, Authorization, cross-origin redirects, and DNS/TLS. Do not hard-code passwords in source code and do not forward sensitive Authorization headers arbitrarily across redirects.

## 9. HttpsURLConnection and HttpClient HTTPS

**HttpsURLConnection** extends HttpURLConnection and provides configuration for SSL socket factory/hostname verifier. **HttpClient** uses the default SSLContext or **HttpClient.Builder.sslContext(...)**, and can provide SSLParameters for appropriate requirements.

When migrating, check:

- Are truststores/trust anchors still correct?
- Are certificate chains, SAN/hostname, and TLS versions/ciphers compatible?
- Is mutual TLS required and is a matching KeyManager configured?
- Does proxy CONNECT tunneling change the network path?
- Does legacy code use an accept-all TrustManager or an always-true HostnameVerifier?

**Do not preserve trust-all configurations or disabled hostname verification** just to "ensure equivalence." If legacy code fails to validate certificates properly, that is a security vulnerability to fix, not behavior worth keeping.

**An HTTPS handshake failure is different from an HTTP 5xx status.** If a TLS certificate is rejected, the client may throw SSLHandshakeException without any HttpResponse. Log the root cause and do not assign 500/503 yourself.

## 10. Connection Reuse, Resources, and Streaming Responses

**HttpURLConnection** is a request handle, though the underlying persistent connection may be shared. The Javadoc states **disconnect()** indicates that other requests to the server are unlikely in the near future; it may close idle sockets, without guaranteeing immediate closure of all connections. Reading/closing InputStream/OutputStream with **try-with-resources** and calling disconnect in finally is good ownership hygiene.

Once built, **HttpClient** can be shared and reused. In **Java 17**, HttpClient **does not yet implement AutoCloseable**, so code compiled with **--release 17** cannot wrap HttpClient in try-with-resources; Java 21+ added close/shutdown APIs. On Java 17, manage long-lived clients and body resources according to the handler.

### BodyHandlers ofInputStream: responsibility shifts to the caller

~~~java
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream input = response.body()) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = input.read(buffer)) != -1) {
        // Process with size limit/backpressure.
    }
}
~~~

**HttpResponse<InputStream>** can be returned as soon as headers are read; **the body is still streaming**. The caller must **read to EOF or close the stream** if it is no longer needed. If forgotten, HTTP connections/resources may be held and not reused properly. Similarly, **BodyHandlers.ofLines()** requires consuming/closing the Stream<String>, and **ofPublisher()** requires subscribing/requesting or canceling the subscription.

**Do not always use readAllBytes()** for large/unbounded responses. Enforce max bytes, read timeouts, idle deadlines, decompression limits, and cleanup. **Closing early** may prevent an HTTP/1.1 connection from being reused, but it is still the right thing to do when the caller has canceled the download.

### HTTP/2

Traditional built-in **HttpURLConnection** primarily uses HTTP/1.1; **HttpClient** supports HTTP/1.1 and HTTP/2. Java 17 HttpClient **prefers HTTP/2 by default**, though the actual version depends on the server, proxy, and TLS. To test migration while keeping protocol equivalence, you can use:

~~~java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_1_1)
        .build();
~~~

Then inspect **response.version()** instead of inferring it from client.version(). Once parity is achieved, enabling HTTP/2 preference is a separate change requiring benchmarking/observability.

## 11. Async: sendAsync Does Not Solve Business Logic Automatically

Legacy code might invoke HttpURLConnection on an executor to run asynchronously. HttpClient provides:

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

CompletableFuture<String> result =
        future.thenApply(response -> {
            if (response.statusCode() != 200) {
                throw new IllegalStateException(
                        "HTTP " + response.statusCode());
            }
            return response.body();
        });
~~~

This is a snippet requiring imports and client/request variables. **CompletableFuture** can complete exceptionally, and **join()** may wrap the cause in **CompletionException**. Run heavy background transformations on a separate bounded executor instead of blocking callbacks/network executors uncontrollably.

**Cancellation** is best-effort: canceling a future does not guarantee the server has not received the request or has rolled it back. If the HTTP exchange already returned a streaming InputStream, canceling the outer future after completion **does not replace input.close()**. With high request volumes, you need bounded concurrency/rate limits; async does not automatically create business-level backpressure.

**Do not switch from sync to async at the same time as changing cookies, auth, redirects, HTTP version, and retries**, as it becomes hard to pinpoint the cause if a regression occurs. A safe strategy is to migrate sync first with behavior parity, then optimize async later.

## 12. Complete Java 17 Example: Legacy and Modern Return the Same Results

The standalone example below creates a local HTTP server using **com.sun.net.httpserver.HttpServer** (module **jdk.httpserver**), bound to **127.0.0.1** on an OS-assigned port, requiring no Internet access. Each endpoint is called via both **HttpURLConnection** and **HttpClient**:

- GET **/ok** → **200 OK** and text **OK**.
- GET **/missing** → **404** and error body **NOT_FOUND**.
- GET **/redirect** → **302** and **Location: /ok**, **no follow** on either client.
- GET **/empty** → **204** with an empty body.
- POST **/echo** with body **ping** → **201** with **RECEIVED:ping**.

To verify behavior parity first, HttpClient selects **HTTP_1_1** and **Redirect.NEVER**; legacy sets **setInstanceFollowRedirects(false)**. The charset is UTF-8 and response bodies are very small so the demo can read all bytes. In production, APIs need streaming/size limits.

### HttpMigrationComparisonDemo.java

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URL;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class HttpMigrationComparisonDemo {
    record Result(int status, String body, String location) {}

    static void respond(HttpExchange exchange, int code, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        if (code == 204 || code == 304 || code == 302) {
            exchange.sendResponseHeaders(code, -1);
            return;
        }
        exchange.sendResponseHeaders(code, bytes.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    static void route(HttpExchange exchange) throws IOException {
        try (exchange) {
            String path = exchange.getRequestURI().getPath();
            switch (path) {
                case "/ok" -> respond(exchange, 200, "OK");
                case "/missing" -> respond(exchange, 404, "NOT_FOUND");
                case "/redirect" -> {
                    exchange.getResponseHeaders().set("Location", "/ok");
                    respond(exchange, 302, "");
                }
                case "/empty" -> respond(exchange, 204, "");
                case "/echo" -> {
                    if (!"POST".equals(exchange.getRequestMethod())) {
                        respond(exchange, 405, "METHOD_NOT_ALLOWED");
                    } else {
                        byte[] data = exchange.getRequestBody().readNBytes(1024);
                        respond(exchange, 201, "RECEIVED:"
                                + new String(data, StandardCharsets.UTF_8));
                    }
                }
                default -> respond(exchange, 404, "NOT_FOUND");
            }
        }
    }

    static Result legacy(URI uri, String method, String content)
            throws IOException {
        URL url = uri.toURL();
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setConnectTimeout(2000);
        conn.setReadTimeout(2000);
        conn.setInstanceFollowRedirects(false);
        conn.setRequestMethod(method);
        try {
            if ("POST".equals(method)) {
                byte[] bytes = content.getBytes(StandardCharsets.UTF_8);
                conn.setDoOutput(true);
                conn.setFixedLengthStreamingMode(bytes.length);
                conn.setRequestProperty(
                        "Content-Type", "text/plain; charset=UTF-8");
                try (OutputStream output = conn.getOutputStream()) {
                    output.write(bytes);
                }
            }

            int status = conn.getResponseCode();
            InputStream bodyStream = status >= 400
                    ? conn.getErrorStream()
                    : conn.getInputStream();
            String body = "";
            if (bodyStream != null) {
                try (InputStream input = bodyStream) {
                    body = new String(input.readAllBytes(),
                            StandardCharsets.UTF_8);
                }
            }
            String location = conn.getHeaderField("Location");
            return new Result(status, body, location);
        } finally {
            conn.disconnect();
        }
    }

    static Result modern(HttpClient client, URI uri, String method,
                         String content) throws IOException, InterruptedException {
        HttpRequest.Builder builder = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(3));
        if ("POST".equals(method)) {
            builder.header("Content-Type", "text/plain; charset=UTF-8")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            content, StandardCharsets.UTF_8));
        } else {
            builder.GET();
        }
        HttpResponse<String> response = client.send(
                builder.build(),
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        return new Result(response.statusCode(), response.body(),
                response.headers().firstValue("Location").orElse(null));
    }

    static void printResult(String label, Result result) {
        String details = " status=" + result.status();
        if (result.location() != null) {
            details += " location=" + result.location();
        } else {
            details += " body=" + result.body();
        }
        System.out.println(label + details);
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/", HttpMigrationComparisonDemo::route);
        server.start();
        try {
            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();
            for (String path : new String[]{
                    "ok", "missing", "redirect", "empty", "echo"}) {
                String method = "echo".equals(path) ? "POST" : "GET";
                String content = "echo".equals(path) ? "ping" : "";
                URI uri = base.resolve(path);
                printResult("legacy " + path,
                        legacy(uri, method, content));
                printResult("modern " + path,
                        modern(client, uri, method, content));
            }
        } finally {
            server.stop(0);
        }
    }
}
~~~

### Compile and Execute

Save the contents above as **HttpMigrationComparisonDemo.java** in a temporary learning directory. Use a full JDK 17+ that includes the **jdk.httpserver** module:

~~~bash
javac --release 17 -encoding UTF-8 HttpMigrationComparisonDemo.java
java HttpMigrationComparisonDemo
~~~

**Stdout compiled with --release 17 and actually run on JDK 24.0.2:**

~~~text
legacy ok status=200 body=OK
modern ok status=200 body=OK
legacy missing status=404 body=NOT_FOUND
modern missing status=404 body=NOT_FOUND
legacy redirect status=302 location=/ok
modern redirect status=302 location=/ok
legacy empty status=204 body=
modern empty status=204 body=
legacy echo status=201 body=RECEIVED:ping
modern echo status=201 body=RECEIVED:ping
~~~

**Explanation:**

1. **/ok:** both APIs receive the same status/body.
2. **/missing:** legacy must choose **getErrorStream()**, while modern uses **response.body()** via the BodyHandler for status 404. This is where error handling commonly breaks during migration.
3. **/redirect:** both explicitly disable following, so both see status 302 and Location. If different defaults were used, legacy might auto-follow to 200 while modern stays at 302.
4. **/empty:** status 204 has no body; do not parse JSON.
5. **/echo:** legacy uses setDoOutput + fixed-length bytes + OutputStream; modern uses BodyPublishers.ofString; the server receives the same body and returns 201.
6. **HttpClient.Version.HTTP_1_1** keeps regression tests free of H2 protocol changes. When enabling H2, test response.version(), latency, proxy, and TLS/ALPN separately.

**Demo limitations:** HttpServer is only a test fixture without TLS, does not support all HTTP versions, and does not test auth/cookies/compression/proxy. Statuses and bodies are fixed in the example so stdout is easy to compare; real systems need timeouts, limits, metrics, and broader tests.

## 13. Safe Code Migration Strategy

### Inventory behavior before rewriting

For each endpoint, document clearly:

| Group | Questions to Answer |
| --- | --- |
| URL/URI | How is the query encoded? Host, port, scheme, redirects? |
| Method | Which GET/POST/PUT/PATCH/DELETE? Any custom method? |
| Body | UTF-8, bytes, file, stream, fixed-length, chunked, replayable? |
| Headers | Content-Type, Authorization, Cookie, Accept-Encoding, duplicated values? |
| Status | Which 2xx/3xx/4xx/5xx are expected domain outcomes? |
| Error body | Does legacy code read getErrorStream? Does the body have a distinct schema? |
| Redirect | Auto-follow? Does it change method/cross-origin? |
| Timeout | Connect, read, total, idle deadline? |
| Cookies/auth | CookieManager, Authenticator, mTLS, token rotation? |
| Proxy/TLS | Proxy selector, truststore, hostname verification? |
| Resources | Who closes streams, disconnect, file handles? |
| Recovery | Retry, cancellation, idempotency, observability? |

### Recommended steps

1. **Separate HTTP-only code** from URLConnections using file:/jar:. Do not force everything onto HttpClient.
2. **Write contract tests** for the same URI/method/headers/body, status/error body, redirects, UTF-8, streaming, cookies, TLS, and timeouts.
3. **Build an HttpClient per policy** (proxy, cookie handler, auth, SSLContext, connect timeout, redirect, HTTP version); reuse the instance.
4. **Build HttpRequest explicitly**, avoiding firing multiple requests just to read an error body; choose a BodyPublisher matching content/size/replayability.
5. **Handle HttpResponse by status**, keep domain errors separate, choose the corresponding BodyHandler, and close streaming bodies.
6. **Keep redirects and HTTP_1_1 in regression tests** if you want to compare against legacy behavior before trying HTTP/2 or async.
7. **Roll out gradually with a feature flag**, logging actual status, exception/cause, actual HTTP version, latency, and redirect path; do not log secrets.
8. **Evaluate performance and HTTP/2/async** after behavior parity is established; keep rollout/rollback independent of the API change.

### Essential test cases

- **200/201/202/204/206**: body present/absent, Location, async job.
- **301/302/303/304/307/308**: redirect, caching, method preservation.
- **400/401/403/404/409/429/500/502/503/504**: error body, auth, Retry-After.
- **Unicode UTF-8, other charsets, binary, gzip**.
- **Large/slow body** and truncated response.
- **Proxy/HTTPS, mTLS, credential headers, cookie persistence**.
- **Connect timeout, request timeout, read-body idle timeout**.
- **POST committed but response lost**, verify idempotency.
- **Async cancellation** and closing resources.
- **Reused connections** and actual protocol version.

**Do not test only the 200 happy path**: the two APIs usually behave alike on simple cases; differences that cause production incidents typically appear in 404/error bodies, 302, auth, streaming, and timeouts.

## 14. Common Mistakes and How to Avoid Them

| Anti-pattern | Consequence | Fix |
| --- | --- | --- |
| Using exceptions to catch HttpClient HTTP 404 | Never enters catch because 404 is a response | response.statusCode() |
| Skipping getErrorStream in legacy code | Lost error body | Read status then error stream if present |
| Not setting a redirect policy | Different defaults, behavior changes | Explicit NEVER/NORMAL, test 3xx |
| Treating readTimeout like request timeout | Wrong deadline | Define connect/total/body idle separately |
| Using new String(bytes) without charset | OS-dependent Unicode bugs | Charset from Content-Type/contract |
| Manually setting Content-Length regardless of body publisher | Header restricted or wrong size | Leave it to BodyPublisher |
| Using String.length as byte count | Wrong Content-Length for Unicode | Compute UTF-8 bytes |
| Keeping HTTP URLConnection cast for file: | ClassCastException | Separate protocols |
| Creating a new client per request | Fails to leverage reuse properly | Shared HttpClient |
| Expecting default cookies without configuration | Lost session | CookieHandler/cookie store |
| Porting an accept-all TrustManager | MITM vulnerability | Standard TLS validation |
| Receiving 503 and calling it IOException | Conflates HTTP and network failure | Separate status and exception |
| Reading large files with ofByteArray | Prone to OOM | Streaming handler + limits |
| Forgetting to close ofInputStream body | Resource leak | try-with-resources |
| Retrying POST on timeout without checking state | Duplicated operations | Idempotency key + status inquiry |
| Using try(HttpClient...) with --release17 | Fails to compile | Java 17 does not have AutoCloseable HttpClient |
| Fire-and-forget bulk sendAsync | Queue and resource exhaustion | Bounded concurrency/backpressure |
| Using URLEncoder for the entire URL | Broken path/query semantics | Encode URI components individually |

## 15. Self-Check Exercises

1. Why are **URLConnection** and **HttpURLConnection** not the same type? Which URL schemes fail the cast?
2. Which legacy setters must be called before **getOutputStream/getResponseCode**?
3. Compare **getInputStream/getErrorStream** with **BodyHandlers.ofString** when the server returns 404 with a JSON error body.
4. Legacy follows redirects by default, modern defaults to NEVER. What does a GET receiving 302 Location /v2 produce if defaults are kept?
5. Why is **setReadTimeout(3000)** not synonymous with **HttpRequest.timeout(3s)**?
6. Why must Content-Length be calculated in bytes when a POST body contains Vietnamese text?
7. Migrate a legacy POST using **setDoOutput(true)** to **BodyPublishers.ofByteArray** and verify Content-Type.
8. If using **BodyPublishers.ofInputStream**, what must the supplier support when a request is replayed?
9. **BodyHandlers.ofFile** writes a file when status is 404. Is that a successful download? Why or why not?
10. When should you use **HttpClient.Version.HTTP_1_1** to check parity and when should you enable HTTP/2?
11. Why should **CookieHandler.setDefault** from legacy code not be assumed to attach automatically to every new HttpClient?
12. A POST was committed, but HttpClient.send() threw IOException before receiving a response. Is retrying safe?
13. Run **HttpMigrationComparisonDemo** and compare the 10 stdout lines; try changing the redirect policy and record the differences.
14. Extend the demo to add status 503 with an error body and Retry-After. Handle it properly in both APIs.
15. Design regression tests for an application with HTTPS/mTLS, proxy, and Unicode; do not use trust-all to make tests pass.

## 16. Pre-Merge Checklist

- [ ] Only migrated URLConnections that actually use HTTP/HTTPS?
- [ ] Verified method, URL encoding, headers, charset, and request/response body?
- [ ] Handled 4xx/5xx via status and body rather than via IOException?
- [ ] Preserved redirect behavior per contract and verified method preservation?
- [ ] Distinguished connect, read, total request, and body idle timeouts?
- [ ] Configured proper CookieHandler, Authenticator, proxy, and SSLContext?
- [ ] Did not disable TLS hostname/certificate validation?
- [ ] Enforced streaming body ownership and size limits?
- [ ] Controlled retry/idempotency for requests with side effects?
- [ ] Tested 204/304/404/429/503 statuses, Unicode, and truncated responses?
- [ ] Checked response.version() when switching from HTTP/1.1 to HTTP/2?
- [ ] Added logging/tracing, regression metrics, and rollback if production differs from expectations?
- [ ] Java code compiles against the actual target version, without using Java 21+ APIs under --release 17?

**Conclusion:** **URLConnection/HttpURLConnection** combines request and connection state, with its own success/error streams, redirect, and timeout semantics. **java.net.http.HttpClient** separates client policy, request, and typed response, offering HTTP/2 and async. A proper migration must **preserve HTTP behavior and the business contract**: status, error body, redirects, charset, request bytes, timeouts, TLS, proxy, cookies, streaming resources, and idempotency. Shorter code is not enough: you need **tests and observability** to prove equivalence.

### Official Documentation

- [URLConnection — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLConnection.html)
- [HttpURLConnection — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html)
- [HttpsURLConnection — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html)
- [HttpClient — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [HttpRequest — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html)
- [HttpRequest.BodyPublishers — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html)
- [HttpResponse — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html)
- [HttpResponse.BodyHandlers — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [HttpServer — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)