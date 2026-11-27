# Official HttpClient and HTTP/1.1, HTTP/2 Support in Java 17

Since Java 11, the JDK has provided an official HTTP Client API in the `java.net.http` package. This API supports sending HTTP requests synchronously or asynchronously, manages requests and responses in an immutable style, and supports both **HTTP/1.1** and **HTTP/2**. Java 17 includes this API out of the box, so applications can use it directly without external HTTP libraries for common HTTP needs.

The central class is `HttpClient`. You configure the client once, build an `HttpRequest` for each request, and call `send()` or `sendAsync()` to receive an `HttpResponse`. The client can prefer HTTP/2 or restrict itself to HTTP/1.1; the actual protocol used must be checked from the response because negotiation with the server can result in a different version than the preferred one.

This lesson covers how to use `HttpClient` in Java 17, the differences between HTTP/1.1 and HTTP/2, how to configure the version, send GET/POST requests, handle bodies, timeouts, redirects, errors, and asynchronous requests.

## 1. Java's Official HTTP Client API

Before Java 11, developers typically used `HttpURLConnection` or third-party HTTP libraries to send requests. Starting in Java 11, `java.net.http.HttpClient` became a standard JDK API. Java 17 continues to support this API.

Key classes:

| Class / Type | Role |
| --- | --- |
| `HttpClient` | Configures and executes HTTP requests; can be reused across multiple requests. |
| `HttpClient.Builder` | Configures the HTTP version, connect timeout, redirects, proxy, TLS, and other client options. |
| `HttpRequest` | Describes a request: URI, method, headers, timeout, and body publisher. |
| `HttpRequest.Builder` | Builds a request step by step. |
| `HttpResponse<T>` | The response result containing status, headers, URI, HTTP version, and a body of type `T`. |
| `HttpResponse.BodyHandler<T>` | Determines how to receive and process the response body. |
| `HttpResponse.BodyHandlers` | Built-in body handlers such as `ofString`, `ofByteArray`, `ofFile`, and `ofInputStream`. |
| `HttpRequest.BodyPublisher` | Supplies request body data. |
| `HttpRequest.BodyPublishers` | Built-in publishers such as `ofString`, `ofByteArray`, `ofFile`, and `noBody`. |
| `HttpClient.Version` | Constants representing HTTP/1.1 or HTTP/2. |

These types reside in the `java.net.http` module, which is part of the JDK. When compiling and running a standard Java application on the classpath, no separate HTTP client dependency needs to be installed.

Example imports:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
```

## 2. How Do HTTP/1.1 and HTTP/2 Differ?

`HttpClient` supports two protocol versions:

- **HTTP/1.1:** the traditional HTTP protocol, exchanging text-formatted requests and responses over a TCP connection. Connections can be reused; when handling multiple concurrent requests, the client can manage multiple connections.
- **HTTP/2:** uses binary framing, supports multiplexing multiple request/response streams over a single connection, and compresses headers. This reduces the cost of opening many connections and avoids having a slow request on the same connection completely block other requests as in simple sequential processing.

Comparison table:

| Feature | HTTP/1.1 | HTTP/2 |
| --- | --- | --- |
| Protocol format | Text-based message syntax, transmitted over TCP. | Binary framing over TCP. |
| Handling multiple requests | Typically uses persistent connections and may open multiple connections. | Multiplexes multiple streams over a single connection. |
| Headers | Headers are repeated per request. | Uses HPACK header compression. |
| Request ordering | Can suffer from HTTP-level head-of-line blocking when requests are queued on a connection. | Multiplexed at the HTTP layer; can still be affected by packet loss at the TCP layer. |
| Support in Java 17 | Yes. | Yes. |
| Selection in `HttpClient` | `HttpClient.Version.HTTP_1_1` | `HttpClient.Version.HTTP_2` |

HTTP/2 does not automatically make every request faster. Effectiveness depends on network latency, payload size, number of requests, the server, proxies, and how the application uses connections.

### How is HTTP/2 negotiated?

For HTTPS connections, HTTP/2 is typically negotiated over TLS using **ALPN** (Application-Layer Protocol Negotiation). The client and server agree on the application protocol during the TLS handshake. If the server or intermediate infrastructure does not support HTTP/2 on that connection, the client can fall back to HTTP/1.1.

Therefore, distinguish between:

- The **preferred** version configured on the client.
- The **actual** version used for a response.

You should not look solely at the client configuration and conclude that every request ran over HTTP/2.

## 3. Creating an HttpClient and Choosing the HTTP Version

### 3.1. Creating the default client

You can create a client using the factory method:

```java
HttpClient client = HttpClient.newHttpClient();
```

The default client prefers HTTP/2. If the server or connection cannot use HTTP/2, the HTTP client can use HTTP/1.1 based on negotiation.

A single `HttpClient` should be reused across multiple requests rather than repeatedly creating new instances. The client manages connection resources and can reuse established connections for subsequent requests.

### 3.2. Configuring HTTP/2 preference

Use the builder when you need to declare the version explicitly:

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
```

`version(HTTP_2)` asks the client to prefer HTTP/2. This is not a guarantee that every response will use HTTP/2; the server, TLS ALPN, proxies, or the network environment may cause the connection to use HTTP/1.1.

### 3.3. Restricting to HTTP/1.1

If the target system requires HTTP/1.1 or compatibility with legacy infrastructure is needed, configure:

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_1_1)
        .build();
```

In this case, the client uses HTTP/1.1 for its requests. This is an explicit protocol configuration choice, useful when integrating with servers or proxies that only support HTTP/1.1.

### 3.4. Comparing the two configurations

```java
HttpClient http2Client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();

HttpClient http11Client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_1_1)
        .build();
```

You can use two separate clients if the application calls multiple services with different protocol requirements. There is no per-request HTTP version property on `HttpRequest.Builder` in Java 17; the version is configured at the `HttpClient` level.

## 4. Sending a Synchronous GET Request

The `send()` method sends a request and waits for the response. This is a straightforward way to call an HTTP API when the current thread can wait for the result.

Example:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class GetExample {
    public static void main(String[] args)
            throws Exception {

        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/"))
                .timeout(Duration.ofSeconds(10))
                .header("Accept", "text/html")
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
        );

        System.out.println("Status: " + response.statusCode());
        System.out.println("HTTP version: " + response.version());
        System.out.println("Body:");
        System.out.println(response.body());
    }
}
```

Steps:

1. Create an `HttpClient` with the preferred HTTP version and connect timeout.
2. Create an `HttpRequest` with the URI, per-request timeout, header, and GET method.
3. Call `client.send(request, BodyHandlers.ofString(...))`.
4. Read the status code, actual HTTP version, and body.

`BodyHandlers.ofString(StandardCharsets.UTF_8)` reads the response body into a `String` using UTF-8. You can choose another charset if required by the protocol or API.

In the example, `example.com` is an illustrative address. When running in practice, replace it with an accessible endpoint and an appropriate authentication policy.

## 5. Reading Information from HttpResponse

`HttpResponse<T>` provides several useful pieces of information:

| Method | Meaning |
| --- | --- |
| `statusCode()` | The HTTP status code, such as 200, 404, or 500. |
| `body()` | The response body of type `T` determined by the body handler. |
| `headers()` | The response headers. |
| `uri()` | The URI of the response. |
| `version()` | The actual HTTP version of the response. |
| `request()` | The request corresponding to the response. |
| `previousResponse()` | The previous response if a redirect chain was followed. |
| `sslSession()` | TLS session information if the connection uses SSL/TLS. |

Example of reading status and headers:

```java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString()
);

int status = response.statusCode();
String contentType = response.headers()
        .firstValue("Content-Type")
        .orElse("No Content-Type");

System.out.println("Status: " + status);
System.out.println("Content-Type: " + contentType);
System.out.println("Version: " + response.version());
```

### Distinguishing preferred version from actual version

`client.version()` returns the client's preferred version. `response.version()` tells you the HTTP version used for that specific response.

For example, the client may be configured with `HTTP_2`, yet the response reports `HTTP_1_1`. This can happen when HTTP/2 is not negotiated or when the server or infrastructure only supports HTTP/1.1.

When you need to confirm the actual protocol used, check `response.version()` instead of checking only `client.version()`.

## 6. Sending a POST Request with a Body

To send data in a request body, use `HttpRequest.BodyPublishers`.

Example of sending JSON:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class PostExample {
    public static void main(String[] args)
            throws Exception {

        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .build();

        String json = """
                {
                    "name": "Lan",
                    "role": "developer"
                }
                """;

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.example.com/users"))
                .timeout(Duration.ofSeconds(15))
                .header("Content-Type", "application/json; charset=UTF-8")
                .header("Accept", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        json,
                        StandardCharsets.UTF_8
                ))
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
        );

        System.out.println(response.statusCode());
        System.out.println(response.body());
    }
}
```

`BodyPublishers.ofString(json, UTF_8)` creates a request body from a string with the UTF-8 charset. The `Content-Type` header informs the server that the body is sent as JSON with the corresponding charset.

The text block in the example makes multiline JSON easier to read. It does not automatically validate that the JSON is valid; for dynamic data, use an appropriate JSON library to serialize objects instead of manually concatenating strings.

### Sending a byte array

If the request body is already binary data, you can use `ofByteArray`:

```java
byte[] payload = {0x01, 0x02, 0x03};

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/upload"))
        .header("Content-Type", "application/octet-stream")
        .POST(HttpRequest.BodyPublishers.ofByteArray(payload))
        .build();
```

### Sending a file

You can use `ofFile`:

```java
import java.nio.file.Path;

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/upload"))
        .header("Content-Type", "application/octet-stream")
        .POST(HttpRequest.BodyPublishers.ofFile(Path.of("upload.bin")))
        .build();
```

`ofFile` reads data from a file to create the request body. The file must exist and be readable; file access errors may be reported when creating the publisher or during sending, depending on the operation and implementation.

## 7. Choosing an Appropriate BodyHandler

A response body can be text, a byte array, a file, or a stream. Choose the body handler based on the data type and content size.

| Body handler | Body type | When appropriate |
| --- | --- | --- |
| `BodyHandlers.ofString()` | `String` | JSON, HTML, XML, or moderately sized text. |
| `BodyHandlers.ofByteArray()` | `byte[]` | Binary data that needs to be kept in memory. |
| `BodyHandlers.ofFile(path)` | `Path` | Downloading a file to disk. |
| `BodyHandlers.ofInputStream()` | `InputStream` | Streaming data when you need to control reading. |
| `BodyHandlers.discarding()` | `Void` | When the response body is not needed. |
| `BodyHandlers.replacing(value)` | Replacement value | Discards the body and returns a specified value. |

### Reading the body as a String

```java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
);
```

This is a convenient choice for APIs returning JSON or reasonably sized text. For very large responses, reading the entire body into a `String` can consume a lot of memory.

### Downloading the body to a file

```java
import java.nio.file.Path;

HttpResponse<Path> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofFile(Path.of("download.bin"))
);

System.out.println("Saved to: " + response.body());
```

The body handler writes the response content to the specified file, and the response body is the file path. Choose a writable save location and validate the file name if the name comes from an external source.

### Receiving an InputStream

```java
import java.io.InputStream;

HttpResponse<InputStream> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofInputStream()
);

try (InputStream input = response.body()) {
    byte[] buffer = input.readNBytes(4096);
    System.out.println("Read bytes: " + buffer.length);
}
```

When using `ofInputStream()`, the application must close the body stream after reading. Otherwise, related resources may be held longer than necessary. The `readNBytes(4096)` example reads only up to the first 4096 bytes; a real application must loop until EOF or pass the stream to an appropriate processor.

## 8. Configuring Timeouts

There are two types of timeouts to distinguish:

- **Connect timeout:** limits the time to establish a connection.
- **Request timeout:** limits the time to wait for the request to complete as configured on the request.

Example:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/data"))
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();
```

`connectTimeout` belongs to `HttpClient.Builder`, whereas `timeout` belongs to `HttpRequest.Builder`.

Omitting timeouts can cause operations to wait longer than expected when the server or network is unresponsive. Appropriate values depend on the operation: a small data read request can use a shorter timeout than a large file download request.

When a timeout occurs, the request may complete exceptionally with `HttpTimeoutException` (a subtype of `IOException`). Handle the exception and decide whether to retry or return an error to the caller.

Client-side timeouts do not replace business deadlines, body size limits, or server-side processing time limits.

## 9. Handling Redirects

An HTTP server may return redirect codes such as 301, 302, 303, 307, or 308 along with a `Location` header. By default, `HttpClient` does not follow redirects automatically.

You can configure the policy:

```java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();
```

Options:

| Value | Behavior |
| --- | --- |
| `HttpClient.Redirect.NEVER` | Never follow redirects automatically. This is the default. |
| `HttpClient.Redirect.NORMAL` | Follow redirects, except when downgrading from HTTPS to HTTP. |
| `HttpClient.Redirect.ALWAYS` | Follow all redirects, including from HTTPS to HTTP. |

For sensitive data, be careful when following redirects because the new target may have a different host or scheme. In particular, do not downgrade from HTTPS to HTTP when transmitting credentials. Choose a policy aligned with security requirements and control over the destination.

You can inspect the previous response via `previousResponse()` if the client followed a redirect chain.

## 10. Handling Errors and Status Codes

`client.send()` does not automatically throw an exception just because the server returns status 404 or 500. At the protocol level, these are valid HTTP responses; the application must read `statusCode()` and decide their business meaning.

Example:

```java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString()
);

if (response.statusCode() >= 200
        && response.statusCode() < 300) {
    System.out.println("Request succeeded");
    System.out.println(response.body());
} else {
    System.err.println("HTTP error: " + response.statusCode());
    System.err.println(response.body());
}
```

Common status groups:

| Group | Meaning |
| --- | --- |
| 2xx | The request was processed successfully. |
| 3xx | Redirection or another navigation behavior is needed. |
| 4xx | There is a problem with the request or access permissions, e.g., 400, 401, 403, 404. |
| 5xx | The server or gateway encountered an error, e.g., 500, 502, 503. |

Client/network-layer failures can throw exceptions:

- `IOException`: I/O, connection, or data read/write errors.
- `HttpTimeoutException`: the request exceeded its timeout.
- `InterruptedException`: the waiting thread was interrupted.
- `IllegalArgumentException`: may be thrown when configuring an invalid URI or request.

### Preserving the interrupt status

If a synchronous call is interrupted, restore the interrupt status when handling or propagating the error:

```java
try {
    HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString()
    );

    System.out.println(response.statusCode());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("HTTP request was interrupted", ex);
} catch (java.io.IOException ex) {
    throw new IllegalStateException("Could not call HTTP endpoint", ex);
}
```

Calling `Thread.currentThread().interrupt()` preserves the interrupt signal for the caller or higher-level thread management. Never swallow `InterruptedException` and continue running as if nothing happened.

## 11. Sending Asynchronous Requests with sendAsync()

`send()` blocks the current thread until the response completes. When an application needs to process multiple concurrent requests or avoid holding a thread waiting on I/O, use `sendAsync()`.

This method returns a `CompletableFuture<HttpResponse<T>>`.

Example:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

public class AsyncGetExample {
    public static void main(String[] args) {
        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        CompletableFuture<HttpResponse<String>> future =
                client.sendAsync(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8
                        )
                );

        future.thenApply(response -> {
                    System.out.println("Status: " + response.statusCode());
                    System.out.println("Version: " + response.version());
                    return response.body();
                })
                .thenAccept(body -> System.out.println(body.length()))
                .exceptionally(error -> {
                    System.err.println("Request failed: " + error);
                    return null;
                });
    }
}
```

Steps:

1. `sendAsync` sends the request and returns a future immediately.
2. `thenApply` processes the response when the future completes and transforms the result.
3. `thenAccept` consumes the result without returning a further value.
4. `exceptionally` handles errors in the future chain.

The example uses `main()` solely to demonstrate the API. When an application needs to keep the process alive until tasks complete, integrate the future into the application lifecycle or an appropriate coordination mechanism. Do not casually call `join()` immediately after `sendAsync()` in code meant to be asynchronous, as doing so blocks the current thread again.

### Combining multiple requests

You can send multiple asynchronous requests and wait for all of them to complete:

```java
CompletableFuture<HttpResponse<String>> first =
        client.sendAsync(request1, HttpResponse.BodyHandlers.ofString());

CompletableFuture<HttpResponse<String>> second =
        client.sendAsync(request2, HttpResponse.BodyHandlers.ofString());

CompletableFuture<Void> all = CompletableFuture.allOf(first, second);

all.thenRun(() -> {
    System.out.println(first.join().statusCode());
    System.out.println(second.join().statusCode());
});
```

`CompletableFuture.allOf` completes when all passed-in futures complete. If one future completes exceptionally, the combined future also completes exceptionally. Inside the callback, only call `join()` on futures guaranteed by `allOf` to have completed.

HTTP/2 multiplexing can help multiple requests share one connection, but `sendAsync` and HTTP/2 are two distinct concepts: asynchronous execution is how the application waits for results; HTTP/2 is the protocol version. You can use `sendAsync` with an HTTP/1.1 client, and you can use `send` with an HTTP/2-preferring client.

## 12. Client Configuration: Proxy, Authenticator, and TLS

`HttpClient.Builder` can configure additional connection components.

### Proxy

If the application must go through a proxy:

```java
import java.net.ProxySelector;

HttpClient client = HttpClient.newBuilder()
        .proxy(ProxySelector.getDefault())
        .build();
```

`ProxySelector.getDefault()` uses the Java environment's default proxy configuration if available. For applications needing a specific proxy, you can configure a custom `ProxySelector`.

### Authenticator

You can supply an `Authenticator` for supported HTTP authentication schemes:

```java
import java.net.Authenticator;
import java.net.PasswordAuthentication;

Authenticator authenticator = new Authenticator() {
    @Override
    protected PasswordAuthentication getPasswordAuthentication() {
        return new PasswordAuthentication(
                "api-user",
                System.getenv("API_PASSWORD").toCharArray()
        );
    }
};

HttpClient client = HttpClient.newBuilder()
        .authenticator(authenticator)
        .build();
```

The example only illustrates where to place the configuration. Scope credentials narrowly, load secrets from a secret manager or secure configuration, and avoid logging passwords or hardcoding them in source code. For Bearer token APIs, typically set the `Authorization` header according to the API contract and protect the token as confidential data.

### TLS/HTTPS

For HTTPS URIs, `HttpClient` uses the JDK's default SSL/TLS configuration unless a custom configuration is provided. In production, keep certificate and hostname verification enabled under a secure configuration.

Do not disable certificate verification or accept every hostname as a "quick fix" for TLS errors. Install the proper CA/certificate, verify the trust store, or configure `SSLContext` according to your system's security policy.

## 13. Setting Headers and Custom Methods

The request builder supports adding headers:

```java
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/items"))
        .header("Accept", "application/json")
        .header("X-Request-Id", "req-123")
        .GET()
        .build();
```

Built-in convenience methods:

- `GET()`
- `POST(BodyPublisher)`
- `PUT(BodyPublisher)`
- `DELETE()`

You can use `method(String, BodyPublisher)` for other methods or when you need to specify a body according to the API:

```java
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/items/42"))
        .header("Content-Type", "application/json")
        .method("PATCH", HttpRequest.BodyPublishers.ofString(
                "{\"name\":\"Updated\"}"
        ))
        .build();
```

Only use methods and bodies supported by the server API. Some methods conventionally do not carry a body or may be handled differently by servers and proxies.

## 14. Limiting Size and Reading Responses

`BodyHandlers.ofString()` and `ofByteArray()` read the entire body into memory. This is convenient for small responses, but unsuitable if the server can return very large payloads.

For large files, consider `BodyHandlers.ofFile(path)`. If using `ofInputStream()`, read in buffered chunks and close the stream when finished.

In addition, the application should control:

- Downloaded file size and available disk space.
- Request duration and body reading duration.
- Content type via `Content-Type`.
- File names and save paths, preventing path traversal when names come from the server or client.
- HTTP status before treating the body as success data.

The body handler determines how the body is received, not content validation. For example, a response declaring JSON still needs to be parsed and validated against the application's schema and data contract.

## 15. HTTP/2 and Verifying the Actual Protocol

To prefer HTTP/2:

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
```

After sending a request, inspect:

```java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString()
);

System.out.println("Preferred: " + client.version());
System.out.println("Used: " + response.version());
```

`client.version()` reports the client's preferred version; `response.version()` reports the version used for the response.

If the result is `HTTP_1_1` even though the client prefers `HTTP_2`, check:

1. Whether the server supports HTTP/2.
2. For HTTPS, whether TLS/ALPN successfully negotiated HTTP/2.
3. Whether a proxy, load balancer, or gateway intercepts and restricts the protocol.
4. Whether a specific endpoint has a different protocol support policy than another endpoint.

Do not conclude that Java 17 does not support HTTP/2 just because one endpoint responds with HTTP/1.1. Java 17 supports HTTP/2; the final protocol depends on the peer and connection capabilities.

## 16. Limitations and Caveats of Java 17 HttpClient

- `HttpClient.Version` in Java 17 provides `HTTP_1_1` and `HTTP_2`. This API does not provide HTTP/3.
- The version is configured at the client level, not as an independent option per `HttpRequest`.
- `HttpClient` and `HttpRequest` are designed to be immutable once created; use a builder to create a new configuration.
- Do not invoke terminal methods again on the same `CompletableFuture` as if the future could re-execute the request; to send a new request, build a request and call the client again.
- Error HTTP statuses do not automatically become exceptions; the application must check the status code.
- Redirects default to `NEVER`.
- `send()` can throw `IOException` and `InterruptedException`.
- `sendAsync()` returns a future, where errors are represented by exceptional completion.
- Choose a body handler suited to the data type; stream bodies must be closed.
- Do not create a new `HttpClient` per request when a configured client can be reused.

## 17. Complete Example: Configured Client with Error Handling

The example below encapsulates client configuration and a GET call into a small class:

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class ApiClient {

    private final HttpClient client;

    public ApiClient() {
        this.client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_2)
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();
    }

    public String getText(URI uri)
            throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder()
                .uri(uri)
                .timeout(Duration.ofSeconds(10))
                .header("Accept", "text/plain")
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8
                )
        );

        if (response.statusCode() < 200
                || response.statusCode() >= 300) {
            throw new IOException(
                    "HTTP request failed with status "
                            + response.statusCode()
            );
        }

        System.out.println("Protocol: " + response.version());

        return response.body();
    }
}
```

Usage:

```java
ApiClient apiClient = new ApiClient();

try {
    String body = apiClient.getText(
            URI.create("https://example.com/")
    );

    System.out.println(body);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    System.err.println("Request interrupted");
} catch (IOException ex) {
    System.err.println("Request failed: " + ex.getMessage());
}
```

In a real application, add a bounded retry policy and only retry appropriate methods/operations. Do not automatically retry every POST because the server may have already executed the request even if the response was lost in transit. For operations requiring retries, design an idempotency key or appropriate business safeguard.

## 18. Testing Applications Using HttpClient

When testing HTTP client code, separate request construction and response handling from specific endpoints so you can swap the URI or use a mock server.

Testing approaches:

- **Unit tests:** verify URI, method, headers, body construction, and status handling through a thin abstraction around the HTTP client.
- **Integration tests:** run a test HTTP server on localhost and send requests to it.
- **Testing HTTP/1.1:** a simple test server can support HTTP/1.1 to verify requests, responses, and bodies.
- **Testing HTTP/2:** use an endpoint or test server that actually supports HTTP/2, TLS, and ALPN when appropriate; check `response.version()` after the request.
- **Testing timeouts/errors:** simulate slow endpoints, unavailable servers, error statuses, or dropped connections.

`com.sun.net.httpserver.HttpServer` in the `jdk.httpserver` module is useful for a simple local HTTP server, but it is not an HTTP/2 server. Do not treat a passing test against this server as proof that HTTP/2 was tested.

For tests that verify the protocol, check `response.version()` and use a server that supports the target protocol. Do not depend on an external public website in unit tests because results can change with the network, server, and access policies.

## 19. Practice Exercises

### Exercise 1 — Send a GET with HTTP/2 preference

Create an `HttpClient` with `version(HTTP_2)`, send a GET request to an accessible HTTPS endpoint, read the status code, and print `response.version()`. Explain why the actual result might be HTTP/1.1.

### Exercise 2 — Force HTTP/1.1

Create another client with `version(HTTP_1_1)`. Send the same request and observe `response.version()`. Compare the preferred configuration and the actual protocol.

### Exercise 3 — POST JSON

Create a POST request with a JSON body using a text block. Set `Content-Type: application/json` and `Accept: application/json`. Use `BodyPublishers.ofString` with UTF-8 and handle the response status.

### Exercise 4 — Timeouts

Configure a 3-second connect timeout and a 5-second request timeout. Call a test endpoint with latency, and handle `HttpTimeoutException` or `IOException` appropriately. Explain how the two timeouts control two different phases.

### Exercise 5 — Download a file

Use `BodyHandlers.ofFile` to download content to an application-controlled path. Check the status code before using the downloaded file and ensure the target directory is writable.

### Exercise 6 — Asynchronous requests

Use `sendAsync` and `thenApply` to extract the status code, followed by `thenAccept` to process the body. Add `exceptionally` to record errors. Do not call `join()` immediately after sending if the goal is to keep processing asynchronous.

### Exercise 7 — Testing redirects

Create a client with `Redirect.NEVER` and a client with `Redirect.NORMAL`. Call a test endpoint that returns a redirect, and compare the status, final URI, and `previousResponse()` when present.

## 20. Quick Reference

| Need | API |
| --- | --- |
| Create a default HTTP client | `HttpClient.newHttpClient()` |
| Prefer HTTP/2 | `version(HttpClient.Version.HTTP_2)` |
| Use HTTP/1.1 only | `version(HttpClient.Version.HTTP_1_1)` |
| Send a synchronous request | `client.send(request, bodyHandler)` |
| Send an asynchronous request | `client.sendAsync(request, bodyHandler)` |
| Create a GET request | `HttpRequest.Builder.GET()` |
| Create a POST request | `POST(BodyPublishers.ofString(...))` |
| Add a header | `header(name, value)` |
| Connect timeout | `HttpClient.Builder.connectTimeout(duration)` |
| Request timeout | `HttpRequest.Builder.timeout(duration)` |
| Read body as text | `BodyHandlers.ofString(UTF_8)` |
| Read body as bytes | `BodyHandlers.ofByteArray()` |
| Write body to a file | `BodyHandlers.ofFile(path)` |
| Check status | `response.statusCode()` |
| Check actual protocol | `response.version()` |
| Follow redirects | `followRedirects(Redirect.NORMAL)` |
| Read headers | `response.headers()` |

**Core principle:** Java 17 includes the official HTTP Client API in `java.net.http`, supporting HTTP/1.1 and HTTP/2. Create and reuse an `HttpClient`, build an `HttpRequest` per call, choose an appropriate `BodyHandler`, and check the status and response. Configuring `HTTP_2` sets a protocol preference; inspect `response.version()` to see whether the request actually used HTTP/1.1 or HTTP/2.
