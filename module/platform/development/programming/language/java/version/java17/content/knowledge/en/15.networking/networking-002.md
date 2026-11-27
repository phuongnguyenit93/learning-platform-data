# Creating HttpRequest and Choosing BodyPublisher and BodyHandler in Java 17

Java 17 includes the HTTP Client API in the `java.net.http` package. When sending an HTTP request, two important decisions are:

- **`HttpRequest.BodyPublisher`:** describes how to supply the body sent to the server.
- **`HttpResponse.BodyHandler<T>`:** determines how to receive and process the returned body, as well as the response data type `T`.

Choosing the right publisher and handler helps avoid loading large files into memory, preserves the correct charset, manages I/O streams, and clarifies types on the caller side. This lesson uses the official HTTP Client API standardized in Java 11 and continued in Java 17; no external HTTP libraries or preview features are required.

## 1. The Role of HttpRequest in the HTTP Client API

An HTTP call typically consists of the following components:

1. `HttpClient` manages connections, TLS configuration, proxies, redirects, and request execution.
2. `HttpRequest` describes the target URI, method, headers, timeout, and body publisher.
3. `HttpClient.send(...)` or `sendAsync(...)` executes the request.
4. `HttpResponse<T>` holds the status code, headers, final URI, HTTP version, and body of type `T`.
5. `BodyHandler<T>` chooses how to receive the body; the handler supplies a body subscriber to consume response data.

Diagram:

~~~text
HttpClient
   |
   | send(request, BodyHandler<T>)
   v
HttpRequest --------------------> Server
   |                                |
   | BodyPublisher                  | response status + headers + body
   | (request body)                 v
   |                           BodyHandler<T>
   |                                |
   +-------------------------- HttpResponse<T>
~~~

`BodyPublisher` handles the **outgoing** direction; `BodyHandler` handles the **incoming** direction. These two types serve different purposes even though both deal with bodies.

## 2. Creating HttpClient and HttpRequest

`HttpClient` should be reused across multiple requests sharing the same configuration. The client can manage and reuse connections internally; there is no need to create a new client for every small request.

~~~java
import java.net.http.HttpClient;
import java.time.Duration;

HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();
~~~

Common configurations:

- `connectTimeout` limits the time allowed to establish a connection.
- `followRedirects` selects the redirect handling policy: `NEVER`, `NORMAL`, or `ALWAYS`.
- `version` sets the preferred HTTP version, such as HTTP/1.1 or HTTP/2. The actual version still depends on server and connection capabilities.
- `proxy` configures a proxy when required by the environment.
- `authenticator` configures client-level authentication when appropriate.

`HttpRequest` is created via a builder:

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.time.Duration;

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/api/items"))
        .timeout(Duration.ofSeconds(10))
        .header("Accept", "application/json")
        .GET()
        .build();
~~~

A request typically specifies:

| Component | API | Meaning |
| --- | --- | --- |
| URI | `uri(URI)` | Resource address |
| HTTP method | `GET()`, `POST(...)`, `PUT(...)`, `DELETE()`, `method(...)` | Requested action |
| Header | `header(name, value)`, `setHeader(name, value)` | Request metadata |
| Timeout | `timeout(Duration)` | Time limit for the request |
| Body | `GET()`, `POST(BodyPublisher)`, `PUT(BodyPublisher)`, `method(...)` | How content is sent |

The builder produces an immutable `HttpRequest` when `build()` is called. To create a different request, use a new builder or `request.newBuilder()` to start from an existing request.

### 2.1. GET and requests without a body

`GET()` creates a GET request with no body:

~~~java
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/status"))
        .GET()
        .build();
~~~

You can explicitly represent a request with no body using `BodyPublishers.noBody()` with `method`:

~~~java
HttpRequest request = HttpRequest.newBuilder(uri)
        .method("GET", HttpRequest.BodyPublishers.noBody())
        .build();
~~~

Normally, use `GET()` for GET and `DELETE()` for DELETE when there is no body. There is no need to create an empty string just to represent a bodyless request.

### 2.2. POST, PUT, and custom methods

`POST` and `PUT` take a `BodyPublisher`:

~~~java
HttpRequest post = HttpRequest.newBuilder(uri)
        .POST(HttpRequest.BodyPublishers.noBody())
        .build();

HttpRequest put = HttpRequest.newBuilder(uri)
        .PUT(HttpRequest.BodyPublishers.ofString("content"))
        .build();
~~~

For methods without a dedicated convenience method, use `method(name, publisher)`:

~~~java
HttpRequest patch = HttpRequest.newBuilder(uri)
        .method(
                "PATCH",
                HttpRequest.BodyPublishers.ofString("{\"active\":true}"))
        .header("Content-Type", "application/json")
        .build();
~~~

The method name must follow HTTP rules and the server must support that method. Do not assume every server supports PATCH or extension methods.

### 2.3. header and setHeader

`header(name, value)` adds a header value; calling it multiple times can add multiple values under the same name. `setHeader(name, value)` replaces any previous values for that header.

~~~java
HttpRequest request = HttpRequest.newBuilder(uri)
        .header("Accept", "application/json")
        .header("Accept", "text/plain")
        .setHeader("X-Request-Source", "java17-demo")
        .GET()
        .build();
~~~

HTTP header names are case-insensitive. Whether multiple values are allowed or values should be replaced depends on the header's semantics and the API contract.

Do not set `Content-Length` manually. The HTTP Client determines the length from the `BodyPublisher` when possible and manages request framing. Certain headers are restricted by the client because they must be managed by the protocol or separate configuration.

## 3. What Is a BodyPublisher?

`HttpRequest.BodyPublisher` is a `Flow.Publisher<ByteBuffer>` that supplies body data to the HTTP Client. It describes how chunks of data are emitted for sending, along with the content length if known.

Built-in publishers are in `HttpRequest.BodyPublishers`:

| Factory | When to use |
| --- | --- |
| `noBody()` | Request has no content |
| `ofString(String)` | Sending text |
| `ofString(String, Charset)` | Sending text with a specified charset |
| `ofByteArray(byte[])` | Sending binary data already in memory |
| `ofByteArray(byte[], offset, length)` | Sending a slice of a byte array |
| `ofFile(Path)` | Sending file contents |
| `ofInputStream(Supplier<InputStream>)` | Supplying data via an InputStream created when the publisher needs to read |

Choose the publisher based on the actual data source. Do not convert a large file into a `byte[]` just to use `ofByteArray` when you can send it directly with `ofFile`.

## 4. Sending Text with ofString

For JSON, XML, form text, or small text payloads, `ofString` is a simple choice:

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;

String json = """
        {
          "name": "An",
          "active": true
        }
        """;

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://example.com/api/users"))
        .header("Content-Type", "application/json; charset=UTF-8")
        .header("Accept", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(
                json, StandardCharsets.UTF_8))
        .build();
~~~

`ofString(String)` uses UTF-8. The overload taking a `Charset` makes the body encoding explicit and avoids relying on implicit assumptions when reading the code.

`Content-Type` describes the content type being sent; `Accept` describes the response type the client wants. These two headers do not replace each other.

Do not concatenate user data into JSON using ad-hoc string concatenation. In real applications, use a JSON serializer to escape characters properly and handle data types.

## 5. Sending a Byte Array with ofByteArray

If the content is already in memory as bytes, use `ofByteArray`:

~~~java
byte[] payload = {
        0x01, 0x02, 0x03, (byte) 0xFE
};

HttpRequest request = HttpRequest.newBuilder(uri)
        .header("Content-Type", "application/octet-stream")
        .POST(HttpRequest.BodyPublishers.ofByteArray(payload))
        .build();
~~~

To send a slice of an array:

~~~java
byte[] buffer = new byte[1024];
// Assume valid data lies in buffer from offset to offset + length.
int offset = 100;
int length = 200;

HttpRequest request = HttpRequest.newBuilder(uri)
        .POST(HttpRequest.BodyPublishers.ofByteArray(
                buffer, offset, length))
        .build();
~~~

This overload avoids creating a subarray just to send a region of data. Ensure `offset` and `length` are within the array bounds.

`ofByteArray` fits moderately sized payloads already in memory. When reading a large file, prefer `ofFile` to avoid loading the entire file into a single array.

## 6. Sending a File with ofFile

`BodyPublishers.ofFile(Path)` creates a publisher that reads content from a file:

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.file.Path;

HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.com/api/upload"))
        .header("Content-Type", "application/octet-stream")
        .POST(HttpRequest.BodyPublishers.ofFile(
                Path.of("data/archive.bin")))
        .build();
~~~

The `ofFile` factory can throw `IOException` if the file cannot be opened. The file must exist and be readable when the publisher performs the send.

Benefits:

- No need to manually read the entire file into a `byte[]`.
- Better suited for large files.
- The HTTP Client can obtain the content length from the file.
- The code clearly expresses that the body source is a file.

This sends a **raw file body**. If the server requires `multipart/form-data` with boundaries and form fields, you must construct a valid multipart structure according to the protocol; merely setting `Content-Type: multipart/form-data` and sending a raw file will not produce valid multipart data.

## 7. Sending Data via ofInputStream

`BodyPublishers.ofInputStream(Supplier<? extends InputStream>)` is appropriate when the data source is provided via an `InputStream`, such as on-demand generated data or data opened from a custom source.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.net.http.HttpRequest;

HttpRequest request = HttpRequest.newBuilder(uri)
        .header("Content-Type", "application/octet-stream")
        .POST(HttpRequest.BodyPublishers.ofInputStream(() -> {
            try {
                return Files.newInputStream(Path.of("data.bin"));
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        }))
        .build();
~~~

The supplier is invoked when the publisher needs a stream to emit the body. Because reading is lazy, do not open the stream beforehand and close it right after building the request.

A good supplier should be able to provide a fresh stream if invoked again, should the publisher require a new subscription. Do not return the same `InputStream` that has already been read or closed. For regular file sources, `ofFile` is simpler and usually a clearer choice.

The stream lifecycle is managed by the publisher per its implementation contract; do not hold an external reference and concurrently read or modify it elsewhere while sending. If managing a special source, carefully review the publisher and supplier contracts.

## 8. Custom BodyPublisher and the Flow API

In advanced scenarios, you can create a publisher from a `Flow.Publisher<ByteBuffer>`:

~~~java
Flow.Publisher<ByteBuffer> publisher = obtainPublisher();

HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.fromPublisher(
                publisher,
                knownContentLength);
~~~

The `contentLength` overload requires an accurate length to be provided. If the length is not known in advance, use the overload taking only the publisher:

~~~java
HttpRequest.BodyPublisher body =
        HttpRequest.BodyPublishers.fromPublisher(publisher);
~~~

Do not declare an incorrect content length: the actual data and declared length must match. If the source cannot guarantee the length, use the lengthless overload so the HTTP Client handles transfer framing appropriately.

Implementing `Flow.Publisher` yourself requires adhering to Reactive Streams/Flow rules for backpressure, subscriptions, completion signals, and error signaling. For most applications, built-in publishers like `ofString`, `ofByteArray`, `ofFile`, or `ofInputStream` are easier and less error-prone.

## 9. BodyHandler Determines How Responses Are Received

`HttpResponse.BodyHandler<T>` receives the response metadata (status and headers) and provides a `BodySubscriber<T>` to process the body. The type `T` becomes the body type in `HttpResponse<T>`.

Example:

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString());
~~~

Here the handler returns the body as a `String`, so the response type is `HttpResponse<String>`.

Built-in handlers in `HttpResponse.BodyHandlers`:

| Handler | Body type | When to use |
| --- | --- | --- |
| `ofString()` | `String` | Small/medium text responses |
| `ofString(Charset)` | `String` | Text requiring a specific charset |
| `ofByteArray()` | `byte[]` | Small/medium binary payloads |
| `ofFile(Path)` | `Path` | Writing response body directly to a file |
| `ofInputStream()` | `InputStream` | Streaming the response body |
| `ofLines(Charset)` | `Stream<String>` | Line-oriented text responses |
| `discarding()` | `Void` | Body not needed |
| `replacing(value)` | Type of `value` | Discard the body and return a replacement value |

Handler choice directly impacts memory and resource lifecycles. If the body can be large, avoid `ofByteArray` or `ofString` when you do not need to keep all content on the heap.

## 10. Receiving Text with ofString

This is a good fit for JSON responses, error messages, or moderately sized text content:

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

System.out.println(response.statusCode());
System.out.println(response.headers().firstValue("Content-Type"));
System.out.println(response.body());
~~~

`ofString()` defaults to UTF-8; the overload accepting a charset makes the encoding contract explicit.

The response body can only be read according to the chosen handler. If the body is JSON, `String` is still just text; a JSON parser/serializer is required to map it to objects.

### 10.1. Do not assume every response is JSON

The server may return:

- JSON for a successful API call.
- HTML for an error page or proxy response.
- Plain text for a message.
- Binary data for a file or image.
- An empty body for some responses.

Use `Content-Type` and the endpoint contract to decide how to parse. Do not parse every body as JSON simply because the request sent `Accept: application/json`; the server can still return errors or other content types.

## 11. Receiving Binary Data with ofByteArray

~~~java
HttpResponse<byte[]> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofByteArray());

byte[] body = response.body();
System.out.println("bytes = " + body.length);
~~~

Use this when the response is small or you need all bytes in memory, such as a thumbnail image or a size-bounded binary payload.

For large files, `ofByteArray` can consume excessive heap. Consider `ofFile` or `ofInputStream` for streaming instead.

## 12. Writing Responses Directly to a File with ofFile

`BodyHandlers.ofFile(Path)` writes the response body to a file and returns the path:

~~~java
import java.net.http.HttpResponse;
import java.nio.file.Path;

HttpResponse<Path> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofFile(
                Path.of("downloads/report.pdf")));

System.out.println("status = " + response.statusCode());
System.out.println("saved = " + response.body());
~~~

The handler manages writing the body to the file while receiving the response. When `send` completes, the body has already been processed by the handler.

Note: the handler writes the body regardless of whether the status code indicates success or failure, unless you use a custom handler to decide based on status. A server might return an HTML error page with status 404; using `ofFile` directly could write that error content into the target file.

If you need to protect the target file from error responses, design a body handler based on `ResponseInfo.statusCode()` or receive the response in a way that checks the status before saving. Do not simply check the status afterward and assume the target file holds valid content.

## 13. Receiving an InputStream and Closing Its Lifecycle Properly

`BodyHandlers.ofInputStream()` returns an `InputStream` instead of waiting to collect the entire body into an array or string:

~~~java
HttpResponse<InputStream> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    byte[] prefix = body.readNBytes(128);
    System.out.println("read bytes = " + prefix.length);
}
~~~

This handler is useful when responses are large or the application wants to read incrementally. However, it transfers responsibility for closing the body stream to the caller. You must close the `InputStream`, ideally using try-with-resources.

`send` with `ofInputStream` may return once the headers are received and the body stream is ready; the body has not necessarily been read completely yet. Keep the stream open while processing, and close it when done reading or when abandoning the rest.

Do not read from the body stream after closing it. Also do not skip closing it when reading only part of the body; closing enables the HTTP Client to release or finalize response resources properly.

## 14. Receiving Line-Oriented Content with ofLines

If the response is multiline text and you want lazy processing, use `BodyHandlers.ofLines(Charset)`:

~~~java
HttpResponse<Stream<String>> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofLines(StandardCharsets.UTF_8));

try (Stream<String> lines = response.body()) {
    lines.filter(line -> !line.isBlank())
            .forEach(System.out::println);
}
~~~

The body has type `Stream<String>`, so the caller must close the stream after consumption. This is a resource-backed stream: a terminal operation does not automatically close the underlying response source.

Use `ofLines` when line-based content is large and you do not need the entire body in a single `String`. If you just need to parse a small JSON object, `ofString` is usually simpler.

## 15. Discarding the Response Body

If you only need the status and headers, use `BodyHandlers.discarding()`:

~~~java
HttpResponse<Void> response = client.send(
        request,
        HttpResponse.BodyHandlers.discarding());

System.out.println(response.statusCode());
System.out.println(response.headers().map());
~~~

The body is discarded; the response body type is `Void`. This is useful when calling endpoints whose response content is unneeded, or operations where only the status result matters.

`BodyHandlers.replacing(value)` also discards the body while returning a replacement value:

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.replacing("body ignored"));

System.out.println(response.body()); // body ignored
~~~

The replacement value is not data sent by the server; it is specified by the application.

## 16. Choosing a BodyHandler Based on Status and Headers

`BodyHandler<T>` is invoked once response headers are available. Thus you can choose how to consume the body based on the status code or headers.

The example below uses a common result type `byte[]`: 2xx responses are read as bytes; non-2xx responses are also read as bytes so the caller can inspect the error body:

~~~java
HttpResponse.BodyHandler<byte[]> handler = info -> {
    String contentType = info.headers()
            .firstValue("Content-Type")
            .orElse("unknown");

    System.out.println("status = " + info.statusCode());
    System.out.println("content-type = " + contentType);

    return HttpResponse.BodySubscribers.ofByteArray();
};
~~~

Because both branches must return `BodySubscriber<byte[]>`, the response type stays uniform. Then the caller checks the status:

~~~java
HttpResponse<byte[]> response = client.send(request, handler);

if (response.statusCode() >= 200 && response.statusCode() < 300) {
    // Process success body.
} else {
    // Parse error body or translate to a business error.
}
~~~

This example still keeps the entire body in memory. For large responses, you can design a specialized subscriber/handler to write to a file or limit data; ensure every branch returns a subscriber with the same result type `T`.

`BodyHandler` does not itself decide whether a response succeeded or failed. It chooses how to read the body. Interpreting the status code belongs to application logic.

## 17. Sending Synchronous Requests with send

`HttpClient.send(request, handler)` executes the request synchronously and returns `HttpResponse<T>`:

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
~~~

This method can throw:

- `IOException` when an I/O error occurs during sending or receiving.
- `InterruptedException` if the waiting thread is interrupted.

Complete example:

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class GetTextDemo {
    public static void main(String[] args)
            throws IOException, InterruptedException {

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/"))
                .timeout(Duration.ofSeconds(15))
                .header("Accept", "text/html")
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        System.out.println("status = " + response.statusCode());
        System.out.println("version = " + response.version());
        System.out.println("final URI = " + response.uri());
        System.out.println("body length = " + response.body().length());
    }
}
~~~

Compilation:

~~~bash
javac --release 17 -encoding UTF-8 GetTextDemo.java
java GetTextDemo
~~~

The example depends on network connectivity and an external endpoint. The status code may vary depending on time or server policy; what matters is how the request and handler are combined.

## 18. Sending Asynchronous Requests with sendAsync

`sendAsync` returns `CompletableFuture<HttpResponse<T>>`, enabling follow-up processing when the response completes without blocking the calling thread during I/O:

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

future.thenApply(HttpResponse::statusCode)
        .thenAccept(System.out::println);
~~~

Or waiting for the result in a simple example:

~~~java
HttpResponse<String> response = client.sendAsync(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
        .join();
~~~

`join()` waits for the result and can throw `CompletionException` if the task completes exceptionally. If using `get()`, handle `InterruptedException` and `ExecutionException`.

`sendAsync` does not change the roles of `BodyPublisher` or `BodyHandler`: the request still needs a publisher for the outgoing body, and the response still needs a handler for the incoming body. If the handler returns an `InputStream` or `Stream<String>`, the caller must still close that resource after the future completes and the body is consumed.

## 19. Timeouts, Status Codes, and HTTP Errors

Two timeouts are commonly configured:

- `HttpClient.Builder.connectTimeout` limits connection establishment time.
- `HttpRequest.Builder.timeout` limits the duration for the request.

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();
~~~

A request timeout does not mean the server returned a special status code; the request can fail with an exception when the wait exceeds the limit.

### 19.1. HTTP 404 or 500 does not automatically become an exception

`HttpClient.send` still returns `HttpResponse<T>` when the server sends status 404, 500, or any non-2xx status. The application must inspect it:

~~~java
int status = response.statusCode();

if (status >= 200 && status < 300) {
    System.out.println("Request succeeded");
} else {
    System.out.println("HTTP error: " + status);
}
~~~

This is the distinction between **transport/protocol errors** (unable to connect, timeout, I/O failure) and **HTTP responses carrying an error status**. A 404 response is still a valid response at the HTTP layer.

### 19.2. Distinguishing error categories

| Situation | Common indicator |
| --- | --- |
| DNS, socket, TLS, or I/O error | `IOException` or subtype |
| Waiting thread interrupted | `InterruptedException` |
| Request timeout | `HttpTimeoutException` (subclass of `IOException`) |
| Server returns 4xx/5xx | `HttpResponse.statusCode()` |
| Body does not match expected format | Application-level parsing error |
| Async future completes exceptionally | `CompletionException` or exception when retrieving result |

Do not treat every status other than 200 as a failure: many APIs use 201, 202, or 204 for successful results. Check the status range appropriate to the endpoint contract.

## 20. Content-Type, Charset, and Accept

Three easily confused concepts:

- Request `Content-Type`: the type of data being sent.
- Request `Accept`: the type of data the client wants to receive.
- Response `Content-Type`: the type of data the server actually returned.

JSON example:

~~~java
HttpRequest request = HttpRequest.newBuilder(uri)
        .header("Content-Type", "application/json; charset=UTF-8")
        .header("Accept", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(
                json, StandardCharsets.UTF_8))
        .build();
~~~

When receiving the response, check the header before parsing:

~~~java
String contentType = response.headers()
        .firstValue("Content-Type")
        .orElse("");

if (contentType.toLowerCase(Locale.ROOT)
        .contains("application/json")) {
    // Parse JSON.
} else {
    // Handle another content type or report a contract error.
}
~~~

The snippet above shows basic content-type checking; applications with stricter requirements should parse media types according to full rules rather than relying only on substring matching.

Do not assume every response uses UTF-8 if the server does not adhere to the contract. In modern APIs, UTF-8 is a common choice; both sides should still agree on the encoding.

## 21. Choosing BodyPublisher and BodyHandler Pairs by Scenario

| Use case | BodyPublisher | BodyHandler | Notes |
| --- | --- | --- | --- |
| GET small JSON data | `noBody()` or `GET()` | `ofString(UTF_8)` | Parse JSON after receiving |
| POST JSON | `ofString(json, UTF_8)` | `ofString(UTF_8)` | Set appropriate Content-Type/Accept |
| Send small image or byte payload | `ofByteArray(bytes)` | `ofString` or `ofByteArray` depending on response | Suitable for data already in memory |
| Upload large file | `ofFile(path)` | Per response, typically `ofString` or `discarding` | Avoids loading the entire file onto the heap |
| Send an InputStream source | `ofInputStream(supplier)` | Per response | Supplier must provide a stream with a valid lifecycle |
| Download file | `noBody()` or GET | `ofFile(path)` | Check status before treating the file as valid |
| Download/read body incrementally | `noBody()` or GET | `ofInputStream()` | Caller must close the InputStream |
| Process text response line by line | `noBody()` or GET | `ofLines(UTF_8)` | Close `Stream<String>` |
| Only need status/headers | Per request | `discarding()` | Body is discarded |

The right choice depends on data size, format, consumption pattern, and resource-closing responsibilities.

## 22. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Garbled non-ASCII / accented text in body | Mismatched charset | Use `ofString(text, UTF_8)` and a handler with an explicit charset |
| Uploading large files spikes heap | Reading the whole file into `byte[]` | Use `BodyPublishers.ofFile` |
| Large responses spike heap | Unbounded `ofByteArray` or `ofString` | Consider `ofFile` or `ofInputStream` |
| Response stream leaks | Not closing `InputStream` or `Stream<String>` | Use try-with-resources |
| POST lacks expected body | Mistakenly using `noBody` or an empty publisher | Pick the appropriate publisher and check `Content-Type` |
| Server reports wrong Content-Length | Manually setting the header or wrong length in a custom publisher | Let the client manage it or supply an accurate length |
| Server returns 404 but catch block is skipped | HTTP status does not automatically throw | Check `statusCode()` |
| File download fails yet file exists | `ofFile` wrote the error response body | Check status and design an appropriate handler |
| Async task fails silently in callback | Exception lives inside `CompletableFuture` | Handle via `exceptionally`, `handle`, or when retrieving the result |
| Reusing the same InputStream multiple times | Supplier returns an already-read/closed stream | Create a fresh stream on each invocation |
| Setting Accept yet server returns another type | Accept is negotiation preference, not a guarantee | Check actual `Content-Type` |
| Creating an HttpClient per request | Failing to reuse the client | Share a client with an appropriate configuration |

## 23. Practice Exercises

### Exercise 1 — GET text

Create an `HttpClient` and a GET `HttpRequest` to a text endpoint. Use `BodyHandlers.ofString(UTF_8)`, and print the status, Content-Type, and body length.

### Exercise 2 — POST JSON

Create a JSON payload with two fields, use `BodyPublishers.ofString`, and set `Content-Type` and `Accept`. Send the request to a test endpoint you control; check the status and response body.

### Exercise 3 — Upload a file

Use `BodyPublishers.ofFile` to send a binary file. Observe how the request is built without manually reading the entire file into a byte array.

### Exercise 4 — Download a file

Use `BodyHandlers.ofFile` to write the response to a path. Check the status before the application treats the file as a successful download.

### Exercise 5 — Reading an InputStream

Use `BodyHandlers.ofInputStream`, read byte chunks, and close the stream with try-with-resources. Compare this with `ofByteArray`.

### Exercise 6 — Line-oriented body

Use `BodyHandlers.ofLines(StandardCharsets.UTF_8)` to filter lines containing a keyword. Ensure the stream is closed after the terminal operation finishes.

### Exercise 7 — Synchronous vs. asynchronous

Send the same request using `send` and `sendAsync`. Compare exception handling, results, and thread waiting behavior.

### Exercise 8 — Status codes and errors

Test endpoints returning 2xx, 404, and 500. Explain why `statusCode()` must be checked even when `send` does not throw an exception.

## 24. Design Principles

When working with HTTP Client in Java 17:

- Reuse a shared `HttpClient` for requests with similar configurations.
- Build immutable `HttpRequest` instances via the builder; declare the URI, method, headers, and timeout explicitly.
- Choose `BodyPublisher` based on the data source: text, byte array, file, or InputStream.
- Choose `BodyHandler<T>` based on how the application consumes the response: String, bytes, file, stream, or discarded.
- Use explicit charsets when sending and receiving text.
- Do not set `Content-Length` manually when HTTP Client can manage it; custom publishers must supply an accurate length if provided.
- Check both status code and `Content-Type`; HTTP 4xx/5xx are still responses and do not automatically throw exceptions.
- Close body resources such as `InputStream` and `Stream<String>` when a handler returns those types.
- For large data, prefer file-based or streaming transfer to avoid holding the entire body in memory.
- Distinguish I/O errors, timeouts, interrupts, HTTP statuses, and application-level parsing errors.

`BodyPublisher` and `BodyHandler` form the two ends of the data transfer contract. Choosing them appropriately based on size, format, and resource lifecycle enables Java 17 code to send clear requests, receive responses efficiently, and manage bodies safely.
